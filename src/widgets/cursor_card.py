"""Vorschaukarte für ein Mauszeiger-Design.

Zeigt den echten Pfeil-Zeiger des Designs (aus der Xcursor-Datei geparst),
darunter Name und Aktiv-Status. Findet sich kein Zeiger (manche Designs erben
ihn nur), wird ein generisches Maus-Symbol gezeigt.
"""

from gi.repository import Gtk

from src.core import cursors


VORSCHAU_GROESSE = 36


class CursorCard(Gtk.FlowBoxChild):
    """Eine anklickbare Vorschaukarte für genau ein Mauszeiger-Design."""

    def __init__(self, theme_name, aktiv):
        super().__init__()
        self.theme_name = theme_name
        self.add_css_class("theme-card")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(self._zeiger_bild(theme_name))

        name_label = Gtk.Label(label=theme_name, xalign=0)
        name_label.add_css_class("card-title")
        name_label.set_ellipsize(3)  # lange Namen kürzen
        box.append(name_label)

        self._status = Gtk.Label(xalign=0)
        self._status.add_css_class("card-status")
        box.append(self._status)

        self.set_child(box)
        self.set_aktiv(aktiv)

    def _zeiger_bild(self, theme_name):
        textur = cursors.load_cursor_texture(theme_name, VORSCHAU_GROESSE)
        if textur is not None:
            bild = Gtk.Image.new_from_paintable(textur)
        else:
            bild = Gtk.Image.new_from_icon_name("input-mouse-symbolic")
        bild.set_pixel_size(VORSCHAU_GROESSE)
        bild.set_halign(Gtk.Align.START)
        return bild

    def set_aktiv(self, aktiv):
        if aktiv:
            self.add_css_class("aktiv")
            self._status.set_text("Aktiv")
        else:
            self.remove_css_class("aktiv")
            self._status.set_text("Installiert")
