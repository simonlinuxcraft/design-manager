"""Seite 'Mauszeiger'.

Zeigt die installierten Mauszeiger-Designs als Vorschaukarten (mit echtem
Zeiger), genau wie die Symbol-Designs. Klick setzt sofort; unter Wayland wird
der neue Zeiger teils erst nach erneuter Anmeldung überall übernommen.
"""

from gi.repository import Adw, Gtk

from src.core import themes
from src.widgets.cursor_card import CursorCard


class CursorPage(Adw.NavigationPage):
    """Navigationsseite mit Vorschaukarten der Mauszeiger-Designs."""

    def __init__(self, settings):
        super().__init__(title="Mauszeiger")
        self._settings = settings
        self._cards = []

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        untertitel = Gtk.Label(
            label="Wirkt unter Wayland teils erst nach erneuter Anmeldung.",
            xalign=0)
        untertitel.add_css_class("dim-label")
        box.append(untertitel)

        box.append(self._karten())

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(scroll)
        self.set_child(toolbar)

    def _karten(self):
        flowbox = Gtk.FlowBox()
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        flowbox.set_max_children_per_line(4)
        flowbox.set_min_children_per_line(2)
        flowbox.set_column_spacing(10)
        flowbox.set_row_spacing(10)
        flowbox.set_homogeneous(True)

        aktuell = self._settings.cursor_theme()
        for name in themes.list_cursor_themes():
            karte = CursorCard(name, aktiv=(name == aktuell))
            flowbox.append(karte)
            self._cards.append(karte)

        flowbox.connect("child-activated", self._on_karte_aktiviert)
        return flowbox

    def _on_karte_aktiviert(self, _flowbox, karte):
        for andere in self._cards:
            andere.set_aktiv(andere is karte)
        self._settings.set_cursor_theme(karte.theme_name)
