"""Hintergrundbilder auflisten.

Zwei Quellen: die mit dem System gelieferten Bilder unter /usr/share/backgrounds
und die vom Nutzer selbst abgelegten unter ~/.local/share/backgrounds. Wir
sammeln nur die direkt enthaltenen Bilddateien ein, nicht rekursiv, damit die
Galerie übersichtlich bleibt.
"""

import json
import os
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
    if variety.laeuft():
        variety.setze_wallpaper(pfad)
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
