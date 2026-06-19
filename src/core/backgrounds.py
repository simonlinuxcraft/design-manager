"""Hintergrundbilder auflisten.

Zwei Quellen: die mit dem System gelieferten Bilder unter /usr/share/backgrounds
und die vom Nutzer selbst abgelegten unter ~/.local/share/backgrounds. Wir
sammeln nur die direkt enthaltenen Bilddateien ein, nicht rekursiv, damit die
Galerie übersichtlich bleibt.
"""

import json
import os
import sys
import threading

from gi.repository import Gdk, GdkPixbuf, Gio, GLib

from src.core import variety


SYSTEM_DIR = "/usr/share/backgrounds"
USER_DIR = os.path.expanduser("~/.local/share/backgrounds")

# Liste der Bilder, die der Nutzer aus der App ausgeblendet hat. Nur ein
# Merker, die Dateien selbst bleiben auf der Platte.
HIDDEN_FILE = os.path.expanduser("~/.config/design-manager/hidden-backgrounds.json")

# Welche Dateiendungen wir als Bild akzeptieren.
ENDUNGEN = (".jpg", ".jpeg", ".png", ".webp")

# Pro-Monitor-Hintergrund. GNOME kennt keinen Schlüssel pro Bildschirm, der
# eine picture-uri gilt für alle. Der einzige Weg sind unterschiedliche Bilder
# je Monitor ist ein einziges Composite über die gesamte Desktop-Fläche, das
# mit picture-options=spanned 1:1 auf die Monitore gelegt wird. Den Anpassungs-
# modus (Zoom/Fit/...) rechnen wir dabei selbst, weil GNOME bei spanned nur noch
# 1:1 mappt. Siehe build_composite/setze_composite.
COMPOSITE_DIR = os.path.expanduser("~/.local/share/design-manager")
PER_MONITOR_FILE = os.path.expanduser("~/.config/design-manager/per-monitor.json")

# Modi, die pro Monitor sinnvoll sind. spanned/none aus der globalen Liste
# fallen weg (im Composite ergeben sie keinen Sinn).
PER_MONITOR_MODI = ("zoom", "scaled", "stretched", "centered", "wallpaper")

# Obergrenze für die Kantenlänge des Composite. Schützt gegen OOM und gegen
# GL-Texturlimits bei vielen großen Monitoren mal HiDPI. Wird sie überschritten,
# skalieren wir das ganze Composite proportional herunter; GNOME zieht es bei
# spanned ohnehin auf die Desktop-Fläche, die Monitor-Zuordnung bleibt korrekt.
MAX_COMPOSITE_KANTE = 16384


def _versteckte():
    """Menge der ausgeblendeten Bildpfade (realpath)."""
    try:
        with open(HIDDEN_FILE) as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def hide_wallpaper(pfad):
    """Blendet ein Bild in der App aus, ohne die Datei zu löschen."""
    versteckt = _versteckte()
    versteckt.add(os.path.realpath(pfad))
    os.makedirs(os.path.dirname(HIDDEN_FILE), exist_ok=True)
    with open(HIDDEN_FILE, "w") as f:
        json.dump(sorted(versteckt), f)


def _bilder_in(ordner):
    """Pfade aller Bilddateien direkt in 'ordner', alphabetisch."""
    if not os.path.isdir(ordner):
        return []
    treffer = []
    for name in sorted(os.listdir(ordner), key=str.lower):
        if name.lower().endswith(ENDUNGEN):
            pfad = os.path.join(ordner, name)
            if os.path.isfile(pfad):
                treffer.append(pfad)
    return treffer


def list_system_wallpapers():
    """Die mit dem System gelieferten Hintergrundbilder."""
    return _bilder_in(SYSTEM_DIR)


def list_user_wallpapers():
    """Die vom Nutzer abgelegten Bilder, ohne die in der App ausgeblendeten."""
    versteckt = _versteckte()
    return [p for p in _bilder_in(USER_DIR)
            if os.path.realpath(p) not in versteckt]


def aktuelles_wallpaper(settings):
    """Dateipfad des aktuell gesetzten Hintergrunds, oder None.

    Der dconf-Wert (file://-URI) ist die erste Quelle. Bei aktivem Variety steht
    dort aber oft dessen flüchtige Zwischendatei (wallpaper-auto-rotated-*), die
    keinem Galerie-Bild entspricht und ohnehin gelöscht wird; in dem Fall führen
    wir auf Varietys echtes Quellbild zurück, damit die App das gewählte Bild
    erkennt.
    """
    uri = settings.background_uri()
    if uri:
        pfad = Gio.File.new_for_uri(uri).get_path()
        if pfad:
            real = os.path.realpath(pfad)
            if real.startswith(os.path.realpath(variety.TEMP_WALLPAPER)):
                quelle = variety.aktuelles_quellbild()
                if quelle and os.path.isfile(quelle):
                    return os.path.realpath(quelle)
            if os.path.isfile(real):
                return real
    quelle = variety.aktuelles_quellbild()
    if quelle and os.path.isfile(quelle):
        return os.path.realpath(quelle)
    return None


def apply_wallpaper(settings, pfad):
    """Setzt ein Hintergrundbild und respektiert dabei Variety.

    Läuft Variety, übergeben wir die Wahl per --set, damit Variety sie als sein
    aktuelles Bild übernimmt und über jeden Login wieder auflegt. Den dconf-
    Schlüssel setzen wir IMMER zusätzlich auf das stabile Quellbild: zum einen
    greift das auch, wenn Variety den --set still verschluckt (z.B. dasselbe
    Bild erneut), zum anderen erkennt die App-UI (Vorschau, aktive Karte) so das
    gewählte Bild statt Varietys flüchtiger Zwischendatei. Der Desktop zeigt in
    beiden Fällen dasselbe Bild.
    """
    if variety.laeuft() and not variety.setze_wallpaper(pfad):
        # Variety lief, hat die Wahl aber nicht übernommen. Der Desktop zeigt
        # über den dconf-Wert unten trotzdem das richtige Bild; nur die vom
        # Banner versprochene Login-Persistenz hängt dann an Variety und greift
        # womöglich nicht. Nicht still verschlucken, damit es nachvollziehbar
        # ist (deckt den dokumentierten "Auswahl hält scheinbar nicht"-Effekt).
        print("Design Manager: variety --set fehlgeschlagen, "
              "Login-Persistenz des Hintergrunds nicht garantiert.",
              file=sys.stderr)
    uri = Gio.File.new_for_path(pfad).get_uri()
    settings.set_background_uri(uri)
    settings.set_background_uri_dark(uri)


def load_texture_async(pfad, breite, hoehe, callback):
    """Dekodiert ein Bild verkleinert in einem Hintergrund-Thread.

    Wichtig für die Geschwindigkeit: Wallpaper sind oft riesig (z.B. 3480x2160).
    Das Dekodieren blockiert sonst den Main-Thread und lässt die App hängen.
    Wir dekodieren daher nebenher und rufen callback(textur) anschließend im
    Main-Loop auf (bei Fehler gar nicht).
    """
    def fertig(pixbuf):
        # Textur erst hier (Main-Thread) aus dem Pixbuf bauen.
        callback(Gdk.Texture.new_for_pixbuf(pixbuf))
        return False

    def worker():
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                pfad, breite, hoehe, True)
        except Exception:
            return
        GLib.idle_add(fertig, pixbuf)

    threading.Thread(target=worker, daemon=True).start()


# --- Pro-Monitor-Hintergrund (Composite + spanned) ---

def monitors():
    """Aktuell verbundene Monitore mit Geometrie und Skalierung.

    Jeder Eintrag: connector (stabiler Name wie 'DP-1'), x/y/width/height in
    logischen Pixeln und scale (HiDPI-Faktor). Reihenfolge wie von GDK. Leere
    Liste, wenn kein Display da ist (z.B. headless).
    """
    display = Gdk.Display.get_default()
    if display is None:
        return []
    liste = display.get_monitors()
    out = []
    for i in range(liste.get_n_items()):
        m = liste.get_item(i)
        geo = m.get_geometry()
        # get_scale() (GTK 4.13+) liefert den echten Bruch-Faktor (z.B. 1.5);
        # get_scale_factor() rundet auf eine Ganzzahl. Den genaueren Wert nehmen,
        # wo vorhanden, sonst auf den ganzzahligen Faktor zurückfallen (GTK 4.6).
        scale = (m.get_scale() if hasattr(m, "get_scale")
                 else m.get_scale_factor()) or 1
        out.append({
            "connector": m.get_connector() or ("monitor-%d" % i),
            "x": geo.x, "y": geo.y,
            "width": geo.width, "height": geo.height,
            "scale": scale,
        })
    return out


def _rect_fuer(m, min_x, min_y):
    """Ziel-Rechteck eines Monitors im Composite, in physischen Pixeln.

    Logische Geometrie mal scale, sonst wird das Bild auf HiDPI matschig.
    """
    s = m["scale"]
    return (int(round((m["x"] - min_x) * s)),
            int(round((m["y"] - min_y) * s)),
            int(round(m["width"] * s)),
            int(round(m["height"] * s)))


def _zeichne(canvas, src, mx, my, mw, mh, modus):
    """Rendert ein Quellbild gemäß Modus in das Monitor-Rechteck des Canvas.

    Erst auf die Zielgröße skalieren, dann den Überlappungsbereich mit dem
    Monitor-Rechteck hineinkopieren. So wird Überstand abgeschnitten und nicht
    gekacheltes Drumherum bleibt schwarz (Fit/Center). copy_area ist pixelgenau,
    composite() würde die Quelle stattdessen über die ganze Fläche kacheln.
    """
    sw, sh = src.get_width(), src.get_height()
    if sw <= 0 or sh <= 0:
        return

    if modus == "wallpaper":  # gekachelt, Originalgröße
        ty = my
        while ty < my + mh:
            tx = mx
            while tx < mx + mw:
                cw = min(sw, mx + mw - tx)
                ch = min(sh, my + mh - ty)
                src.copy_area(0, 0, cw, ch, canvas, tx, ty)
                tx += sw
            ty += sh
        return

    if modus == "stretched":
        new_w, new_h = mw, mh
    else:
        if modus == "centered":
            s = 1.0
        elif modus == "scaled":  # einpassen, Seitenverhältnis behalten
            s = min(mw / sw, mh / sh)
        else:  # "zoom": füllen, Seitenverhältnis behalten, Überstand schneiden
            s = max(mw / sw, mh / sh)
        new_w, new_h = max(1, round(sw * s)), max(1, round(sh * s))

    skaliert = src
    if (new_w, new_h) != (sw, sh):
        skaliert = src.scale_simple(new_w, new_h, GdkPixbuf.InterpType.BILINEAR)

    # Platzierung des skalierten Bildes (zentriert) und Schnitt mit dem Rechteck.
    px = mx + (mw - new_w) // 2
    py = my + (mh - new_h) // 2
    x0, y0 = max(px, mx), max(py, my)
    x1, y1 = min(px + new_w, mx + mw), min(py + new_h, my + mh)
    if x1 <= x0 or y1 <= y0:
        return
    skaliert.copy_area(x0 - px, y0 - py, x1 - x0, y1 - y0, canvas, x0, y0)


def build_composite(zuordnung, monitore, zielpfad):
    """Baut aus {connector: (bildpfad, modus)} ein spanned-Composite.

    Gibt True bei erfolgreichem Schreiben, sonst False. Fängt JEDEN Fehler ab
    (kaputtes Bild, zu wenig Speicher, Schreibfehler), damit ein Fehlschlag nie
    die App mitreißt: Stabilität vor Schönheit. Bei False bleibt der bisherige
    Hintergrund unangetastet, weil der Aufrufer die dconf-Werte erst nach einem
    True setzt.
    """
    if not monitore:
        return False
    try:
        return _build_composite(zuordnung, monitore, zielpfad)
    except Exception as fehler:  # bewusst breit: nichts darf nach oben crashen
        print("Design Manager: Composite fehlgeschlagen:", fehler,
              file=sys.stderr)
        return False


def _build_composite(zuordnung, monitore, zielpfad):
    """Eigentlicher Bau. Canvas ist die Bounding-Box aller Monitore in
    physischen Pixeln, schwarz vorgefüllt; pro Monitor wird sein Bild
    hineingerendert. Monitore ohne Zuordnung (oder fehlende Datei) bleiben
    schwarz. Eine zu große Fläche wird proportional gedeckelt."""
    min_x = min(m["x"] for m in monitore)
    min_y = min(m["y"] for m in monitore)
    rects = [list(_rect_fuer(m, min_x, min_y)) for m in monitore]
    breite = max(rx + rw for rx, _ry, rw, _rh in rects)
    hoehe = max(ry + rh for _rx, ry, _rw, rh in rects)
    if breite <= 0 or hoehe <= 0:
        return False

    # Schutz vor OOM/Texturlimit: extrem große Composites herunterskalieren.
    f = min(1.0, MAX_COMPOSITE_KANTE / breite, MAX_COMPOSITE_KANTE / hoehe)
    if f < 1.0:
        rects = [[int(round(v * f)) for v in r] for r in rects]
        breite = max(rx + rw for rx, _ry, rw, _rh in rects)
        hoehe = max(ry + rh for _rx, ry, _rw, rh in rects)

    canvas = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, breite, hoehe)
    canvas.fill(0x000000ff)  # Schwarz hinter Fit-/Center-Rändern

    for m, rect in zip(monitore, rects):
        eintrag = zuordnung.get(m["connector"])
        if not eintrag:
            continue
        pfad, modus = eintrag
        if not pfad or not os.path.isfile(pfad):
            continue
        try:
            src = GdkPixbuf.Pixbuf.new_from_file(pfad)
        except GLib.Error:
            continue  # einzelnes kaputtes Bild überspringen, Rest bauen
        _zeichne(canvas, src, rect[0], rect[1], rect[2], rect[3], modus)

    os.makedirs(os.path.dirname(zielpfad), exist_ok=True)
    # Atomar schreiben: erst in eine Temp-Datei, dann umbenennen. So sieht GNOME
    # nie ein halb geschriebenes PNG, selbst wenn ein zweiter Bau dazwischenfunkt.
    tmp = zielpfad + ".tmp"
    canvas.savev(tmp, "png", [], [])
    os.replace(tmp, zielpfad)
    return True


def naechster_composite_pfad(settings):
    """Alternierender a/b-Pfad, damit GNOME den Wechsel überhaupt bemerkt.

    GNOME lädt den Hintergrund nur neu, wenn sich die picture-uri ÄNDERT, nicht
    bei gleichem Pfad mit neuem Inhalt. Darum zwei Slots im Wechsel.
    """
    a = os.path.join(COMPOSITE_DIR, "wall-composite-a.png")
    b = os.path.join(COMPOSITE_DIR, "wall-composite-b.png")
    aktuell = settings.background_uri()
    aktuell_pfad = ""
    if aktuell:
        aktuell_pfad = Gio.File.new_for_uri(aktuell).get_path() or ""
    return b if os.path.realpath(aktuell_pfad) == os.path.realpath(a) else a


def setze_composite(settings, pfad):
    """Setzt ein fertig gebautes Composite als Hintergrund (Modus spanned).

    Getrennt von build_composite, damit die UI den teuren Bau in einen Thread
    legen und nur dieses Setzen im Main-Loop ausführen kann.
    """
    uri = Gio.File.new_for_path(pfad).get_uri()
    settings.set_background_uri(uri)
    settings.set_background_uri_dark(uri)
    settings.set_picture_options("spanned")


def lade_zuordnung():
    """Gespeicherte {connector: (pfad, modus)} oder leeres Dict."""
    try:
        with open(PER_MONITOR_FILE) as f:
            daten = json.load(f)
        return {k: (v["path"], v["mode"]) for k, v in daten.items()}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def speichere_zuordnung(zuordnung):
    """Sichert die Pro-Monitor-Auswahl, damit sie nach einem Neustart (oder nach
    Auflösungsänderung zum Neu-Anwenden) wieder da ist."""
    daten = {k: {"path": p, "mode": mo} for k, (p, mo) in zuordnung.items()}
    os.makedirs(os.path.dirname(PER_MONITOR_FILE), exist_ok=True)
    with open(PER_MONITOR_FILE, "w") as f:
        json.dump(daten, f, indent=2)


def _selbsttest():
    """Compositing headless prüfen: zwei nebeneinander liegende Monitore, je ein
    einfarbiges Bild, danach an je einem Pixel die erwartete Farbe."""
    import tempfile

    def farbbild(rgb, pfad):
        buf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 64, 64)
        buf.fill(rgb)
        buf.savev(pfad, "png", [], [])

    tmp = tempfile.mkdtemp()
    rot, gruen = os.path.join(tmp, "r.png"), os.path.join(tmp, "g.png")
    farbbild(0xff0000ff, rot)
    farbbild(0x00ff00ff, gruen)
    monitore = [
        {"connector": "L", "x": 0, "y": 0,
         "width": 100, "height": 100, "scale": 1},
        {"connector": "R", "x": 100, "y": 0,
         "width": 100, "height": 100, "scale": 1},
    ]
    ziel = os.path.join(tmp, "out.png")
    assert build_composite(
        {"L": (rot, "stretched"), "R": (gruen, "stretched")}, monitore, ziel)
    erg = GdkPixbuf.Pixbuf.new_from_file(ziel)
    assert erg.get_width() == 200 and erg.get_height() == 100, "Canvas-Größe"

    def pixel(buf, x, y):
        pix = buf.get_pixels()
        stride = buf.get_rowstride()
        n = buf.get_n_channels()
        off = y * stride + x * n
        return pix[off], pix[off + 1], pix[off + 2]

    assert pixel(erg, 50, 50) == (255, 0, 0), "linker Monitor rot"
    assert pixel(erg, 150, 50) == (0, 255, 0), "rechter Monitor grün"

    # Fit lässt Ränder schwarz: hohes Bild in breites Rechteck.
    hoch = os.path.join(tmp, "h.png")
    b = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 10, 100)
    b.fill(0x0000ffff)
    b.savev(hoch, "png", [], [])
    ziel2 = os.path.join(tmp, "out2.png")
    assert build_composite({"L": (hoch, "scaled")},
                           [monitore[0]], ziel2)
    erg2 = GdkPixbuf.Pixbuf.new_from_file(ziel2)
    assert pixel(erg2, 0, 50) == (0, 0, 0), "Fit-Rand schwarz"
    assert pixel(erg2, 50, 50) == (0, 0, 255), "Fit-Mitte blau"
    print("backgrounds-Selbsttest ok")


if __name__ == "__main__":
    _selbsttest()
