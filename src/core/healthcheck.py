"""Prüft beim Start, ob die gesetzten Designs auf der Platte noch existieren.

Wird ein Design entfernt, korrigiert GNOME den dconf-Wert nicht: der tote Name
bleibt stehen und die Sitzung läuft still mit Adwaita weiter. Dieser Check
findet solche Lücken und meldet sie, statt sie zu verstecken. Er ändert nichts,
die Korrektur passiert nur auf Knopfdruck (siehe window.py).

Zusätzlich erkennt er ein riskantes KDE-Relikt (colorreload-gtk-module in der
gtk-modules-Zeile der settings.ini): Auf einer GNOME-Sitzung kann dieses Modul
auf jeden Theme-Broadcast mit einer selbst-erhaltenden Reload-Kaskade über alle
GTK-Apps reagieren und die Sitzung lahmlegen. Die App bietet an, es zu entfernen.
"""

import os
import tempfile

from src.core import themes
from src.i18n import _


# Immer vorhanden: Adwaita ist in GTK eingebaut, Yaru liegt systemweit auf
# Ubuntu. Adwaita hat keine On-Disk-gtk.css und würde die Prüfung sonst
# fälschlich auslösen.
IMMER_DA = {"adwaita"}

# settings.ini der GTK-Versionen und die GTK-Module, die auf GNOME einen Theme-
# Reload-Sturm auslösen können (KDE-Relikte von kde-gtk-config).
_SETTINGS_INI = [
    os.path.expanduser("~/.config/gtk-3.0/settings.ini"),
    os.path.expanduser("~/.config/gtk-4.0/settings.ini"),
]
_RELOAD_MODULE = ("colorreload-gtk-module", "window-decorations-gtk-module")


def reload_module_gesetzt():
    """settings.ini-Pfade, deren gtk-modules-Zeile ein riskantes Reload-Modul listet."""
    treffer = []
    for pfad in _SETTINGS_INI:
        try:
            with open(pfad, encoding="utf-8") as f:
                for zeile in f:
                    if zeile.startswith("gtk-modules=") and \
                            any(m in zeile for m in _RELOAD_MODULE):
                        treffer.append(pfad)
                        break
        except OSError:
            continue
    return treffer


def entferne_reload_module():
    """Nimmt die Reload-Module aus der gtk-modules-Zeile (andere Module bleiben).

    Sichert jede geänderte Datei vorher nach <pfad>.bak-dm. Wirkt erst für neu
    gestartete Apps (eine Neuanmeldung greift es voll). Gibt True bei Änderung.
    """
    geaendert = False
    for pfad in reload_module_gesetzt():
        try:
            with open(pfad, encoding="utf-8") as f:
                zeilen = f.readlines()
        except OSError:
            continue
        neu = []
        for z in zeilen:
            if z.startswith("gtk-modules="):
                module = [m for m in z.split("=", 1)[1].strip().split(":")
                          if m and m not in _RELOAD_MODULE]
                if module:
                    neu.append("gtk-modules=" + ":".join(module) + "\n")
                # sonst: leere gtk-modules-Zeile ganz weglassen
            else:
                neu.append(z)
        try:
            with open(pfad + ".bak-dm", "w", encoding="utf-8") as f:
                f.writelines(zeilen)
            # Atomar ersetzen: erst in eine Temp-Datei im selben Ordner, dann
            # umbenennen. Ein Fehler mitten im Schreiben darf die settings.ini
            # nie abgeschnitten zurücklassen.
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(pfad),
                                       prefix=".dm-ini-", suffix=".ini")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.writelines(neu)
                os.replace(tmp, pfad)
            except OSError:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            geaendert = True
        except OSError:
            continue
    return geaendert


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
