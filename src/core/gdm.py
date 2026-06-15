"""GDM-Anmeldebildschirm-Hintergrund (braucht root, nur ausserhalb der Sandbox).

GNOME bietet keinen Schluessel fuer den Hintergrund des Anmeldebildschirms; er
steckt in einer kompilierten gresource unter /usr/share. Statt die System-Datei
zu ueberschreiben (das hat frueher den Greeter gecrasht und zur Aussperrung
gefuehrt) haengen wir eine eigene gresource ueber update-alternatives ein. Die
Original-Datei bleibt unangetastet, ein Boot-Guard rollt bei Problemen
automatisch zurueck. Details im Helfer-Skript data/gdm-background.sh.

Vor jedem Setzen wird hart validiert: das Bild muss ladbar sein, es wird als PNG
neu kodiert (ein Format, das die Shell sicher rendert) und nach dem Bauen wird
geprueft, dass es in der gresource am erwarteten Pfad steckt und sich laden
laesst. Erst dann faesst pkexec etwas am System an.
"""

import os
import shutil
import subprocess
import tempfile

import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib  # noqa: E402


_WURZEL = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
HELFER = os.path.join(_WURZEL, "data", "gdm-background.sh")

# Muss mit den Pfaden im Helfer-Skript uebereinstimmen.
ALT_LINK = "/usr/share/gnome-shell/gdm-theme.gresource"
STATE = "/var/lib/design-manager/gdm.state"
OUR = "/var/lib/design-manager/design-manager-gdm.gresource"

# Eingebettetes Bild nicht groesser als noetig: ein Login-Hintergrund braucht
# keine Foto-Vollaufloesung, und eine kleinere gresource laedt der Greeter
# schneller.
_MAX_BREITE = 3840


def verfuegbar():
    """True, wenn alle Werkzeuge, das Helfer-Skript und die GDM-Weiche da sind."""
    werkzeuge = all(shutil.which(t) for t in
                    ("gresource", "glib-compile-resources", "pkexec",
                     "update-alternatives"))
    return werkzeuge and os.path.isfile(HELFER) and os.path.exists(ALT_LINK)


def aktiv():
    """True, wenn gerade ein eigener GDM-Hintergrund eingehaengt ist."""
    return os.path.exists(OUR) and os.path.exists(STATE)


def bestaetigung_offen():
    """True, wenn ein Hintergrund gesetzt, aber noch nicht bestaetigt ist.

    In dem Fall soll die App den Nutzer bitten, sich einmal ab- und wieder
    anzumelden und das Ergebnis zu bestaetigen, sonst rollt der Guard zurueck.
    """
    return aktiv() and _state_wert("confirmed") != "1"


def apply(bild_pfad):
    """Setzt das Bild als GDM-Hintergrund. Gibt True bei Erfolg.

    Baut und validiert die gresource als normaler Nutzer; nur das Einhaengen
    laeuft ueber pkexec als root. Eine ungueltige Datei erreicht pkexec nie.
    """
    if not bild_pfad or not os.path.isfile(bild_pfad):
        return False

    with tempfile.TemporaryDirectory(prefix="dm-gdm-") as work:
        png = os.path.join(work, "bg.png")
        if not _als_png(bild_pfad, png):
            return False

        gres = os.path.join(work, "theme.gresource")
        gebaut = _bauen(png, gres)
        if not gebaut:
            return False
        res_pfad, greeter_css = gebaut

        if not _gresource_ok(gres, res_pfad, greeter_css):
            return False

        return _pkexec("install", gres)


def confirm():
    """Bestaetigt das gesetzte Theme; schaltet den Auto-Rollback-Guard ab."""
    return _pkexec("confirm")


def reset():
    """Entfernt unsere Alternative; die Weiche faellt aufs Original zurueck."""
    return _pkexec("reset")


# --- Validierung / Bauen ----------------------------------------------------

def _als_png(quelle, ziel):
    """Laedt das Bild (validiert es damit) und schreibt es als PNG.

    Skaliert zu breite Bilder herunter. False, wenn die Quelle kein ladbares
    Bild ist.
    """
    # Erst die Maße ohne vollen Decode lesen, dann zu breite Bilder schon beim
    # Laden herunterskalieren. Sonst landet ein riesiges Quellbild zuerst in
    # voller Auflösung im RAM (Problem auf schwachen, RAM-armen Maschinen).
    info = GdkPixbuf.Pixbuf.get_file_info(quelle)
    if info is None or info[0] is None:
        return False
    breite = info[1]
    try:
        if breite > _MAX_BREITE:
            pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                quelle, _MAX_BREITE, -1, True)
        else:
            pix = GdkPixbuf.Pixbuf.new_from_file(quelle)
    except GLib.Error:
        return False
    if pix is None:
        return False

    try:
        pix.savev(ziel, "png", [], [])
    except GLib.Error:
        return False
    return os.path.isfile(ziel)


def _bauen(png, out):
    """Ruft 'build' im Helfer-Skript (als Nutzer, kein root).

    Gibt (resource-Pfad des Bildes, Liste der Greeter-CSS-resource-Pfade)
    zurueck, oder None. Die Greeter-CSS-Liste sind die gdm*.css, in die der
    Helfer die Hintergrundregel geschrieben hat; sie wird unten validiert."""
    try:
        erg = subprocess.run(
            ["bash", HELFER, "build", png, out],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except OSError:
        return None
    if erg.returncode != 0 or not os.path.isfile(out):
        return None
    res_pfad = None
    greeter_css = []
    for zeile in erg.stdout.splitlines():
        if zeile.startswith("RESOURCE="):
            res_pfad = zeile[len("RESOURCE="):].strip()
        elif zeile.startswith("GREETER_CSS="):
            greeter_css.append(zeile[len("GREETER_CSS="):].strip())
    if not res_pfad:
        return None
    return res_pfad, greeter_css


def _gresource_ok(gres, res_pfad, greeter_css):
    """Prueft die gebaute gresource hart, bevor pkexec etwas anfasst:

    1. das Bild steckt am erwarteten Pfad und laesst sich als Bild dekodieren,
    2. die Hintergrundregel ist wirklich in der Greeter-CSS (gdm.css) gelandet.

    Punkt 2 faengt den frueheren stillen No-Op ab: der Greeter laedt gdm.css,
    nicht gnome-shell.css. Fehlt die Regel dort, waere das Theme unsichtbar, und
    wir wollen lieber laut hier scheitern als ein bestaetigt-aber-wirkungsloses
    Theme ausliefern."""
    try:
        res = Gio.Resource.load(gres)
    except GLib.Error:
        return False
    try:
        daten = res.lookup_data(res_pfad, Gio.ResourceLookupFlags.NONE)
    except GLib.Error:
        return False

    lader = GdkPixbuf.PixbufLoader()
    try:
        lader.write(daten.get_data())
        lader.close()
    except GLib.Error:
        return False
    if lader.get_pixbuf() is None:
        return False

    if not greeter_css:
        return False
    marker = b"design-manager-gdm"
    bildname = res_pfad.rsplit("/", 1)[-1].encode()
    for css_pfad in greeter_css:
        try:
            roh = res.lookup_data(
                css_pfad, Gio.ResourceLookupFlags.NONE).get_data()
        except GLib.Error:
            continue
        if marker in roh and bildname in roh:
            return True
    return False


# --- Zustand / pkexec -------------------------------------------------------

def _state_wert(schluessel):
    try:
        with open(STATE, encoding="utf-8") as f:
            for zeile in f:
                k, _, v = zeile.partition("=")
                if k.strip() == schluessel:
                    return v.strip()
    except OSError:
        pass
    return None


def _pkexec(*args):
    try:
        erg = subprocess.run(
            ["pkexec", HELFER, *args],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return False
    return erg.returncode == 0
