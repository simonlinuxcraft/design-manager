"""App-Icons ergänzen, die einem Symbol-Paket fehlen.

Findet GNOME den Icon-Namen eines Starters weder im Paket samt Inherits-Kette
noch in hicolor oder pixmaps, zeigt es ein allgemeines Programm-Symbol. Das
Paket selbst bleibt unangetastet: daneben entsteht ein kleines Theme
<Paket>-filled, das von <Paket> erbt, nur die Originale dieser Lücken enthält
und statt des Pakets aktiviert wird. Starter mit festem Dateipfad in Icon=
kann kein Theme ändern, die werden nur gemeldet.
"""

import os
import shutil
import struct

from gi.repository import Gio, GLib


SUFFIX = "-filled"
MARKER = "X-DesignManager-Base"
ENDUNGEN = (".svg", ".png", ".xpm")

INDEX = """[Icon Theme]
Name={paket}
Comment=App icons {paket} lacks, taken from the apps themselves
Inherits={paket},hicolor
Hidden=true
{marker}={paket}
Directories={ordner}
"""


def _icon_ordner():
    # Dieselben Orte und dieselbe Reihenfolge wie GTK.
    return [os.path.join(GLib.get_user_data_dir(), "icons"),
            os.path.expanduser("~/.icons"),
            *(os.path.join(d, "icons") for d in GLib.get_system_data_dirs())]


def _keyfile(pfad):
    kf = GLib.KeyFile()
    try:
        kf.load_from_file(pfad, GLib.KeyFileFlags.NONE)
    except GLib.Error:
        return None
    return kf


def _wert(kf, schluessel, gruppe="Icon Theme"):
    try:
        return kf.get_string(gruppe, schluessel)
    except GLib.Error:
        return ""


def _index(theme):
    """index.theme eines Themes (wie GTK die zuerst gefundene), oder None."""
    for basis_ordner in _icon_ordner():
        pfad = os.path.join(basis_ordner, theme, "index.theme")
        if os.path.isfile(pfad):
            return _keyfile(pfad)
    return None


def basis(name):
    """Das Paket hinter einem Overlay, sonst name selbst."""
    kf = _index(name) if name.endswith(SUFFIX) else None
    return (_wert(kf, MARKER) if kf else "") or name


def _kette(theme, kette=None):
    """theme und alles, wovon es erbt, in GTKs Suchreihenfolge."""
    kette = [] if kette is None else kette
    kf = _index(theme) if theme not in kette else None
    if kf is not None:
        kette.append(theme)
        for eltern in _wert(kf, "Inherits").split(","):
            if eltern.strip():
                _kette(eltern.strip(), kette)
    return kette


def _ordner(theme):
    """(Ordner, Size) aller Icon-Ordner eines Themes, ohne die seiner Eltern."""
    kf = _index(theme)
    if kf is None:
        return []
    ergebnis = []
    for schluessel in ("Directories", "ScaledDirectories"):
        for unter in _wert(kf, schluessel).split(","):
            unter = unter.strip()
            if not unter:
                continue
            try:
                groesse = kf.get_integer(unter, "Size")
            except GLib.Error:
                groesse = 0
            ergebnis += [(os.path.join(b, theme, unter), groesse)
                         for b in _icon_ordner()]
    return ergebnis


def _namen_in(ordner):
    namen = set()
    for o in ordner:
        try:
            namen.update(d[:-4] for d in os.listdir(o) if d.endswith(ENDUNGEN))
        except OSError:
            pass
    return namen


def _namen(theme):
    """Alle Icon-Namen, die GTK für theme findet: Kette, hicolor, pixmaps."""
    kette = _kette(theme)
    _kette("hicolor", kette)
    return _namen_in([o for t in kette for o, _g in _ordner(t)]
                     + [os.path.join(d, "pixmaps") for d in
                        [GLib.get_user_data_dir(), *GLib.get_system_data_dirs()]])


def _png_breite(pfad):
    try:
        with open(pfad, "rb") as f:
            kopf = f.read(24)
    except OSError:
        return 0
    if len(kopf) < 24 or kopf[:8] != b"\x89PNG\r\n\x1a\n":
        return 0
    return struct.unpack(">I", kopf[16:20])[0]


def _taugt(pfad):
    return ((pfad.endswith(".svg") and os.path.isfile(pfad))
            or (pfad.endswith(".png") and _png_breite(pfad) > 0))


def _verdeckt(info):
    """Pfad-Icon eines verdeckten Starters gleicher ID, oder None.

    Lokale Kopien von Snap-Startern tragen Icon=<Name>, den kein Theme kennt;
    das Original steht im verdeckten Starter unter /var/lib/snapd/desktop.
    """
    for daten in [GLib.get_user_data_dir(), *GLib.get_system_data_dirs()]:
        kf = _keyfile(os.path.join(daten, "applications", info.get_id() or ""))
        icon = _wert(kf, "Icon", "Desktop Entry") if kf else ""
        if icon.startswith("/") and _taugt(icon):
            return icon
    return None


def _aus_theme(icon, kette):
    """Das Icon aus der ersten Theme der Kette, die es hat: SVG vor größtem PNG."""
    for theme in kette:
        treffer = []
        for n, (ordner, groesse) in enumerate(_ordner(theme)):
            for endung in (".svg", ".png"):
                pfad = os.path.join(ordner, icon + endung)
                if _taugt(pfad):
                    treffer.append((endung == ".svg", groesse, -n, pfad))
        if treffer:
            return max(treffer)[3]
    return None


def bericht(theme, vorher=None):
    """Lücken von theme bei den sichtbaren Startern.

    quellen: {Icon-Name: Originaldatei} für Lücken, die sich füllen lassen
    (verdeckter Starter mit Pfad-Icon, sonst das vorher aktive Theme).
    ergaenzt: Apps, deren Icon ein aktives Overlay schon mitbringt; neu: Apps,
    die sich füllen lassen; fehlt: Apps ohne jedes Icon; pfad: Apps mit festem
    Icon-Pfad. Die App-Listen sind sortierte Anzeigenamen.
    """
    vorhanden = _namen(theme)
    eigene = (_namen_in(o for o, _g in _ordner(theme))
              if basis(theme) != theme else set())
    vorher_kette = _kette(vorher) if vorher else []
    b = {"quellen": {}, "ergaenzt": [], "neu": [], "fehlt": [], "pfad": []}
    for info in Gio.AppInfo.get_all():
        if not info.should_show():
            continue
        app, icon = info.get_display_name(), info.get_icon()
        if isinstance(icon, Gio.FileIcon):
            b["pfad"].append(app)
            continue
        if not isinstance(icon, Gio.ThemedIcon):
            continue
        name = icon.get_names()[0]
        if "/" in name or name.startswith("."):
            continue  # kein Theme-Icon-Name; wird unten zum Dateinamen
        if name in eigene:
            b["ergaenzt"].append(app)
        elif name in vorhanden:
            continue
        elif name in b["quellen"]:
            b["neu"].append(app)
        else:
            quelle = _verdeckt(info) or _aus_theme(name, vorher_kette)
            if quelle:
                b["quellen"][name] = quelle
                b["neu"].append(app)
            else:
                b["fehlt"].append(app)
    for k in ("ergaenzt", "neu", "fehlt", "pfad"):
        b[k] = sorted(set(b[k]), key=str.lower)
    return b


def zustand(aktiv):
    """(ergaenzt, fehlt, pfad) für den icon-theme-Wert aus dconf, ohne etwas zu schreiben.

    aktiv ist das Paket oder sein Overlay. Ein Overlay, das nur herumliegt (etwa
    nach dem Notausstieg auf Adwaita), zählt nicht.
    """
    b = bericht(aktiv)
    return b["ergaenzt"], sorted(b["neu"] + b["fehlt"], key=str.lower), b["pfad"]


def ergaenze(paket, vorher=None):
    """Legt <paket>-filled mit den Originalen der Lücken an.

    Gibt (Theme-Name für dconf, (ergaenzt, fehlt, pfad)) zurück. Ohne Lücken,
    bei einem unbekannten Paket oder wenn das Schreiben scheitert, bleibt es
    beim Paket selbst.
    """
    if not paket or _index(paket) is None:
        return paket, ([], [], [])
    b = bericht(paket, vorher)
    name = paket + SUFFIX
    icons = os.path.join(GLib.get_user_data_dir(), "icons")
    ziel = os.path.join(icons, name)
    ohne = (paket, (b["ergaenzt"], sorted(b["neu"] + b["fehlt"], key=str.lower),
                    b["pfad"]))
    # Ein fremdes Theme, das zufällig so heißt, wird nie überschrieben.
    if not b["quellen"] or (os.path.lexists(ziel) and basis(name) != paket):
        return ohne

    # Versteckt fertig bauen, dann per rename tauschen: GNOME sieht nie einen
    # halben Ordner.
    neu, alt = (os.path.join(icons, vor + name) for vor in (".dm-neu-", ".dm-alt-"))
    abschnitte = {}
    try:
        for rest in (neu, alt):
            shutil.rmtree(rest, ignore_errors=True)
        for icon, quelle in b["quellen"].items():
            if quelle.endswith(".svg"):
                unter = "scalable/apps"
                abschnitte[unter] = "Size=128\nMinSize=8\nMaxSize=512\nType=Scalable"
            else:
                breite = _png_breite(quelle)
                unter = f"{breite}x{breite}/apps"
                abschnitte[unter] = f"Size={breite}\nType=Fixed"
            os.makedirs(os.path.join(neu, unter), exist_ok=True)
            # Kopie statt Link: ein entfernter Snap hinterlässt sonst einen toten Link.
            shutil.copyfile(quelle, os.path.join(neu, unter, icon + quelle[-4:]))
        with open(os.path.join(neu, "index.theme"), "w") as f:
            f.write(INDEX.format(paket=paket, marker=MARKER,
                                 ordner=",".join(sorted(abschnitte))))
            for unter, abschnitt in sorted(abschnitte.items()):
                f.write(f"\n[{unter}]\nContext=Applications\n{abschnitt}\n")
        if os.path.lexists(ziel):
            os.rename(ziel, alt)
        os.rename(neu, ziel)
    except OSError:
        shutil.rmtree(neu, ignore_errors=True)
        return ohne
    shutil.rmtree(alt, ignore_errors=True)
    return name, (sorted(set(b["ergaenzt"] + b["neu"]), key=str.lower),
                  b["fehlt"], b["pfad"])
