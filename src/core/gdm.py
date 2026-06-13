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
        res_pfad = _bauen(png, gres)
        if not res_pfad:
            return False

        if not _gresource_ok(gres, res_pfad):
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
    try:
        pix = GdkPixbuf.Pixbuf.new_from_file(quelle)
    except GLib.Error:
        return False

    breite, hoehe = pix.get_width(), pix.get_height()
    if breite > _MAX_BREITE:
        neu_h = max(1, round(hoehe * _MAX_BREITE / breite))
        pix = pix.scale_simple(_MAX_BREITE, neu_h, GdkPixbuf.InterpType.BILINEAR)
    if pix is None:
        return False

    try:
        pix.savev(ziel, "png", [], [])
    except GLib.Error:
        return False
    return os.path.isfile(ziel)


def _bauen(png, out):
    """Ruft 'build' im Helfer-Skript (als Nutzer, kein root). Gibt den
    resource-Pfad des eingebetteten Bildes zurueck, oder None."""
    try:
        erg = subprocess.run(
            ["bash", HELFER, "build", png, out],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except OSError:
        return None
    if erg.returncode != 0 or not os.path.isfile(out):
        return None
    for zeile in erg.stdout.splitlines():
        if zeile.startswith("RESOURCE="):
            return zeile[len("RESOURCE="):].strip()
    return None


def _gresource_ok(gres, res_pfad):
    """Prueft, dass das Bild in der gresource am erwarteten Pfad steckt und sich
    als Bild laden laesst. Faengt fehlenden Bildverweis und kaputte Bytes ab."""
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
    return lader.get_pixbuf() is not None


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
