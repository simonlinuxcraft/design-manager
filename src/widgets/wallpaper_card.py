"""Vorschaukarte für ein Hintergrundbild.

Kompakt gehalten: ein Thumbnail mit dem Dateinamen klein darunter. Ob das Bild
gesetzt ist, zeigt der silberne Rahmen (CSS-Klasse "aktiv"), ohne zusätzliche
Textzeile, damit die Galerie übersichtlich bleibt.
"""

import os

from gi.repository import Gtk

from src import compat
from src.core import backgrounds
from src.i18n import _


THUMB_BREITE = 132
THUMB_HOEHE = 76


class WallpaperCard(Gtk.FlowBoxChild):
    """Eine anklickbare Vorschaukarte für genau ein Hintergrundbild."""

    def __init__(self, pfad, aktiv, entfernbar=False, on_entfernen=None):
        super().__init__()
        self.pfad = pfad
        self.add_css_class("theme-card")
        self.add_css_class("kompakt")
        self.set_tooltip_text(os.path.basename(pfad))

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        thumb = Gtk.Picture()
        compat.set_cover(thumb)
        thumb.set_size_request(THUMB_BREITE, THUMB_HOEHE)
        thumb.add_css_class("wallpaper-thumb")
        # Thumbnail verkleinert und nebenher laden (kein Ruckeln beim Aufbau).
        backgrounds.load_texture_async(
            pfad, THUMB_BREITE * 2, THUMB_HOEHE * 2, thumb.set_paintable)

        # Bei eigenen Bildern ein kleiner Entfernen-Knopf oben rechts. Er blendet
        # das Bild nur in der App aus; die Datei bleibt erhalten.
        if entfernbar and on_entfernen is not None:
            overlay = Gtk.Overlay()
            overlay.set_child(thumb)
            knopf = Gtk.Button(icon_name="window-close-symbolic")
            knopf.add_css_class("osd")
            knopf.add_css_class("circular")
            knopf.set_halign(Gtk.Align.END)
            knopf.set_valign(Gtk.Align.START)
            knopf.set_margin_top(4)
            knopf.set_margin_end(4)
            knopf.set_tooltip_text(_("Remove from the app (file is kept)"))
            knopf.connect("clicked", lambda _b: on_entfernen(pfad))
            overlay.add_overlay(knopf)
            box.append(overlay)
        else:
            box.append(thumb)

        name = Gtk.Label(
            label=os.path.splitext(os.path.basename(pfad))[0], xalign=0)
        name.add_css_class("wallpaper-name")
        name.set_ellipsize(3)
        name.set_max_width_chars(16)
        box.append(name)

        self.set_child(box)
        self.set_aktiv(aktiv)

    def set_aktiv(self, aktiv):
        if aktiv:
            self.add_css_class("aktiv")
        else:
            self.remove_css_class("aktiv")
