"""Prüft beim Start, ob die gesetzten Designs auf der Platte noch existieren.

Wird ein Design entfernt, korrigiert GNOME den dconf-Wert nicht: der tote Name
bleibt stehen und die Sitzung läuft still mit Adwaita weiter. Dieser Check
findet solche Lücken und meldet sie, statt sie zu verstecken. Er ändert nichts,
die Korrektur passiert nur auf Knopfdruck (siehe window.py).
"""

from src.core import themes
from src.i18n import _


# Immer vorhanden: Adwaita ist in GTK eingebaut, Yaru liegt systemweit auf
# Ubuntu. Adwaita hat keine On-Disk-gtk.css und würde die Prüfung sonst
# fälschlich auslösen.
IMMER_DA = {"adwaita"}


def _fehlt(name, vorhandene):
    if not name:
        return False  # leerer Wert = GNOME-Standard, nicht kaputt
    kennung = name.lower()
    if kennung in IMMER_DA or kennung.startswith("yaru"):
        return False
    return name not in vorhandene


def pruefe(settings):
    """Liste der Lücken als (label, reset_methode)-Tupel, neueste zuerst.

    reset_methode ist der Name der reset_*-Methode auf AppSettings, mit der die
    Lücke geschlossen wird. Leere Liste = alles in Ordnung.
    """
    probleme = []
    if _fehlt(settings.gtk_theme(), themes.list_gtk_themes()):
        probleme.append((_("GTK theme"), "reset_gtk_theme"))
    if _fehlt(settings.icon_theme(), themes.list_icon_themes()):
        probleme.append((_("icon theme"), "reset_icon_theme"))
    if _fehlt(settings.cursor_theme(), themes.list_cursor_themes()):
        probleme.append((_("cursor"), "reset_cursor_theme"))
    if settings.user_themes_verfuegbar() and \
            _fehlt(settings.shell_theme(), themes.list_shell_themes()):
        probleme.append((_("shell theme"), "reset_shell_theme"))
    return probleme
