"""Vorschaukarte für einen kuratierten Look.

Die Karte zeigt eine kleine Collage, ohne das System anzufassen: ein
Hintergrund-Thumbnail (oder, falls kein Bild dabei ist, eine Fläche in der
Akzentfarbe des Looks) und darunter ein paar echte Beispiel-Icons des im Look
gewählten Symbol-Designs. Den Icon-Trick teilt sie sich mit der Symbol-Karte
(theme_card._icon_theme_fuer).
"""

import os

from gi.repository import Gtk

from src import compat
from src.core import backgrounds
from src.widgets.theme_card import _icon_theme_fuer


# Beispiel-Icons für die Collage, mit Fallback je Platz.
VORSCHAU_ICONS = [
    ["folder", "inode-directory"],
    ["user-home", "go-home"],
    ["text-x-generic", "text-x-preview"],
]
ICON_GROESSE = 26
FLAECHE_HOEHE = 84


class LookCard(Gtk.FlowBoxChild):
    """Anklickbare Vorschaukarte für genau einen kuratierten Look."""

    def __init__(self, look):
        super().__init__()
        self.look = look
        self.add_css_class("theme-card")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(self._flaeche(look))
        if look.get("icons"):
            box.append(self._icon_reihe(look["icons"]))

        name = Gtk.Label(label=look.get("name", ""), xalign=0)
        name.add_css_class("card-title")
        name.set_ellipsize(3)
        box.append(name)

        beschreibung = Gtk.Label(
            label=look.get("beschreibung", ""), xalign=0, wrap=True)
        beschreibung.add_css_class("card-status")
        box.append(beschreibung)

        self.set_child(box)

    def _flaeche(self, look):
        """Hintergrund-Thumbnail, oder eine Fläche in der Akzentfarbe."""
        wallpaper = look.get("wallpaper")
        pfad = os.path.expanduser(wallpaper) if wallpaper else None
        if pfad and os.path.isfile(pfad):
            bild = Gtk.Picture()
            bild.set_size_request(-1, FLAECHE_HOEHE)
            compat.set_cover(bild)
            bild.add_css_class("card")
            backgrounds.load_texture_async(pfad, 240, 150, bild.set_paintable)
            return bild

        flaeche = Gtk.Box()
        flaeche.set_size_request(-1, FLAECHE_HOEHE)
        flaeche.add_css_class("card")
        accent = look.get("accent")
        if accent:
            # Dieselbe Farbklasse wie die Akzent-Swatches (siehe style.css).
            flaeche.add_css_class("akzent-" + accent)
        return flaeche

    def _icon_reihe(self, icons):
        reihe = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        icon_theme = _icon_theme_fuer(icons)
        for namen in VORSCHAU_ICONS:
            reihe.append(self._icon_bild(icon_theme, namen))
        return reihe

    def _icon_bild(self, icon_theme, namen):
        for name in namen:
            if icon_theme.has_icon(name):
                paintable = icon_theme.lookup_icon(
                    name, None, ICON_GROESSE, 1, Gtk.TextDirection.NONE, 0)
                bild = Gtk.Image.new_from_paintable(paintable)
                bild.set_pixel_size(ICON_GROESSE)
                return bild
        bild = Gtk.Image.new_from_icon_name("image-missing")
        bild.set_pixel_size(ICON_GROESSE)
        return bild
