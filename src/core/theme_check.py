"""Prüft, ob ein Design wirklich nutzbar ist, bevor es aktiviert wird.

themes.list_gtk_themes() meldet einen Ordner schon als GTK-Design, wenn er nur
einen Unterordner gtk-3.0/gtk-4.0 hat. Fehlt darin die eigentliche gtk.css (oder
ist sie unlesbar), fällt GNOME beim Umschalten still auf Adwaita zurück und der
tote Name bleibt in dconf stehen. Diese Prüfung fängt das vorher ab.
"""

import os

from src.core import themes
# Denselben Lookup wie die Shell-Vorschau nutzen, statt ihn zu duplizieren.
from src.core.shell_preview import _css_pfad as _shell_css_pfad
from src.i18n import _


def _lesbar(pfad):
    try:
        with open(pfad, "rb"):
            return True
    except OSError:
        return False


def _theme_ordner(name):
    for basis in themes.THEME_DIRS:
        pfad = os.path.join(basis, name)
        if os.path.isdir(pfad):
            return pfad
    return None


def pruefe_gtk(name):
    """(ok, grund): hat das GTK-Design eine lesbare gtk.css?

    Adwaita ist in GTK eingebaut und hat keine On-Disk-gtk.css, gilt also immer
    als ok. Geprüft wird gtk-4.0/gtk.css, ersatzweise gtk-3.0/gtk.css.
    """
    if not name or name == "Adwaita":
        return True, ""
    ordner = _theme_ordner(name)
    if ordner is None:
        return False, _("The theme folder was not found.")
    for unter in ("gtk-4.0", "gtk-3.0"):
        css = os.path.join(ordner, unter, "gtk.css")
        if os.path.isfile(css):
            if _lesbar(css):
                return True, ""
            return False, _("The file {sub}/gtk.css is not readable.").format(
                sub=unter)
    return False, _("The theme is missing gtk-4.0/gtk.css. GNOME would fall "
                    "back to Adwaita.")


def pruefe_shell(name):
    """(ok, grund): hat das Shell-Design eine lesbare gnome-shell.css?"""
    if not name:
        return True, ""  # leerer Wert = GNOME-Standard
    css = _shell_css_pfad(name)
    if css is None:
        return False, _("The theme is missing gnome-shell/gnome-shell.css.")
    if not _lesbar(css):
        return False, _("The file gnome-shell.css is not readable.")
    return True, ""
