"""Vorschaukarte für ein Hintergrundbild.

Zeigt ein Thumbnail des Bildes, darunter den Dateinamen und ob es gerade
gesetzt ist.
"""

import os

from gi.repository import Gtk

from src import compat
from src.core import backgrounds
from src.i18n import _


THUMB_BREITE = 168
THUMB_HOEHE = 96


class WallpaperCard(Gtk.FlowBoxChild):
    """Eine anklickbare Vorschaukarte für genau ein Hintergrundbild."""

    def __init__(self, pfad, aktiv, entfernbar=False, on_entfernen=None):
        super().__init__()
        self.pfad = pfad
        self.add_css_class("theme-card")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

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
        name.add_css_class("card-title")
        name.set_ellipsize(3)
        name.set_max_width_chars(20)
        box.append(name)

        self._status = Gtk.Label(xalign=0)
        self._status.add_css_class("card-status")
        box.append(self._status)

        self.set_child(box)
        self.set_aktiv(aktiv)

    def set_aktiv(self, aktiv):
        if aktiv:
            self.add_css_class("aktiv")
            self._status.set_text(_("Active"))
        else:
            self.remove_css_class("aktiv")
            self._status.set_text("")
