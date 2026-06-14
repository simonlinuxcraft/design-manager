"""Vorschaukarte für ein Mauszeiger-Design.

Zeigt eine Reihe echter Zeiger des Designs (Pfeil, Hand, Text; aus den
Xcursor-Dateien geparst), darunter Name und Aktiv-Status. Aufbau wie die
Symbol-Karte mit ihren Beispiel-Icons. Fehlt eine Zeiger-Art, wird der
Hauptpfeil gezeigt; fehlt auch der, ein generisches Maus-Symbol.
"""

from gi.repository import Gtk

from src.core import cursors


VORSCHAU_GROESSE = 30


class CursorCard(Gtk.FlowBoxChild):
    """Eine anklickbare Vorschaukarte für genau ein Mauszeiger-Design."""

    def __init__(self, theme_name, aktiv):
        super().__init__()
        self.theme_name = theme_name
        self.add_css_class("theme-card")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(self._zeiger_reihe(theme_name))

        name_label = Gtk.Label(label=theme_name, xalign=0)
        name_label.add_css_class("card-title")
        name_label.set_ellipsize(3)  # lange Namen kürzen
        box.append(name_label)

        self._status = Gtk.Label(xalign=0)
        self._status.add_css_class("card-status")
        box.append(self._status)

        self.set_child(box)
        self.set_aktiv(aktiv)

    def _zeiger_reihe(self, theme_name):
        """Eine waagerechte Reihe mehrerer Zeiger-Vorschauen (Pfeil, Hand, Text),
        analog zur Beispiel-Icon-Reihe der Symbol-Karten."""
        reihe = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for namen in cursors.VORSCHAU_GRUPPEN:
            reihe.append(self._zeiger_bild(theme_name, namen))
        return reihe

    def _zeiger_bild(self, theme_name, namen):
        # Erst die gewünschte Zeiger-Art versuchen, sonst den Hauptpfeil des
        # Designs (statt eines fremden Symbols); fehlt auch der, ein neutrales
        # Maus-Symbol.
        textur = cursors.load_cursor_texture(theme_name, namen, VORSCHAU_GROESSE)
        if textur is None:
            textur = cursors.load_cursor_texture(
                theme_name, cursors.ZEIGER_NAMEN, VORSCHAU_GROESSE)
        if textur is not None:
            bild = Gtk.Image.new_from_paintable(textur)
        else:
            bild = Gtk.Image.new_from_icon_name("input-mouse-symbolic")
        bild.set_pixel_size(VORSCHAU_GROESSE)
        return bild

    def set_aktiv(self, aktiv):
        if aktiv:
            self.add_css_class("aktiv")
            self._status.set_text("Aktiv")
        else:
            self.remove_css_class("aktiv")
            self._status.set_text("Installiert")
