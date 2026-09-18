"""Vorschaukarte für ein Hintergrundbild.

Nur das Bild, ohne Dateinamen (der steht im Tooltip): Hintergründe erkennt man
am Motiv, Namen wie "wp8981087-skyrim-4k" sind nur Rauschen. Ob das Bild gesetzt
ist, zeigt der silberne Rahmen (CSS-Klasse "aktiv").
"""

import os

from gi.repository import Gtk

from src import compat
from src.core import backgrounds
from src.i18n import _


THUMB_BREITE = 160
THUMB_HOEHE = 90


class _Thumb(Gtk.Picture):
    """Picture mit fester Wunschgröße. Ein normales Gtk.Picture meldet die
    Bildgröße als natürliche Breite; die FlowBox bräche dann nach zwei
    riesigen Karten um. Mehr Platz bekommt es trotzdem (homogene FlowBox)."""

    def do_measure(self, orientation, _for_size):
        n = THUMB_BREITE if orientation == Gtk.Orientation.HORIZONTAL else THUMB_HOEHE
        return n, n, -1, -1


class WallpaperCard(Gtk.FlowBoxChild):
    """Eine anklickbare Vorschaukarte für genau ein Hintergrundbild."""

    def __init__(self, pfad, aktiv, entfernbar=False, on_entfernen=None):
        super().__init__()
        self.pfad = pfad
        self.add_css_class("theme-card")
        self.add_css_class("kompakt")
        self.set_tooltip_text(os.path.basename(pfad))

        thumb = _Thumb()
        compat.set_cover(thumb)
        thumb.add_css_class("wallpaper-thumb")
        thumb.set_overflow(Gtk.Overflow.HIDDEN)  # runde Ecken auch am Bild
        # Thumbnail verkleinert und nebenher laden (kein Ruckeln beim Aufbau).
        backgrounds.load_texture_async(
            pfad, THUMB_BREITE * 2, THUMB_HOEHE * 2, thumb.set_paintable)

        # Bei eigenen Bildern ein kleiner Entfernen-Knopf oben rechts, sichtbar
        # beim Überfahren. Er blendet das Bild nur in der App aus; die Datei
        # bleibt erhalten.
        overlay = Gtk.Overlay()
        overlay.set_child(thumb)
        if entfernbar and on_entfernen is not None:
            knopf = Gtk.Button(icon_name="window-close-symbolic")
            knopf.add_css_class("osd")
            knopf.add_css_class("circular")
            knopf.add_css_class("wallpaper-entfernen")
            knopf.set_halign(Gtk.Align.END)
            knopf.set_valign(Gtk.Align.START)
            knopf.set_margin_top(4)
            knopf.set_margin_end(4)
            knopf.set_tooltip_text(_("Remove from the app (file is kept)"))
            knopf.connect("clicked", lambda _b: on_entfernen(pfad))
            overlay.add_overlay(knopf)

        self.set_child(overlay)
        self.set_aktiv(aktiv)

    def set_aktiv(self, aktiv):
        if aktiv:
            self.add_css_class("aktiv")
        else:
            self.remove_css_class("aktiv")


class HinzufuegenKachel(Gtk.FlowBoxChild):
    """Erste Kachel der eigenen Bilder: öffnet den Dateidialog."""

    def __init__(self):
        super().__init__()
        self.add_css_class("theme-card")
        self.add_css_class("kompakt")
        self.add_css_class("hinzufuegen-kachel")
        self.set_tooltip_text(_("Or drag images into the window"))

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(THUMB_BREITE, THUMB_HOEHE)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        icon = Gtk.Image.new_from_icon_name("list-add-symbolic")
        icon.set_pixel_size(24)
        icon.set_vexpand(True)
        icon.set_valign(Gtk.Align.END)
        box.append(icon)
        label = Gtk.Label(label=_("Add image"))
        label.set_vexpand(True)
        label.set_valign(Gtk.Align.START)
        box.append(label)
        self.set_child(box)
