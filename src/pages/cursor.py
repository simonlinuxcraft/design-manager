"""Seite 'Mauszeiger'.

Zeigt die installierten Mauszeiger-Designs als Vorschaukarten (mit echtem
Zeiger), genau wie die Symbol-Designs. Klick setzt sofort: GTK-Programme und der
Desktop-Zeiger wechseln live. Nur schon geöffnete Nicht-GTK-Programme (manche
Terminals, Electron-Apps) behalten den alten Zeiger, bis sie neu gestartet
werden.
"""

from gi.repository import Adw, GLib, Gtk

from src.core import themes
from src.widgets.cursor_card import CursorCard
from src.widgets.dropzone import InstallDropzone


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
            label="GTK-Programme und der Zeiger über dem Desktop wechseln "
                  "sofort. Schon geöffnete Nicht-GTK-Programme (manche "
                  "Terminals, Electron-Apps) zeigen den alten Zeiger, bis du "
                  "sie neu startest.",
            xalign=0)
        # Umbrechen lassen, sonst fordert der lange Text seine volle Breite als
        # Mindestbreite und zieht die ganze Seite (und das Fenster) breit.
        untertitel.set_wrap(True)
        untertitel.add_css_class("dim-label")
        box.append(untertitel)

        box.append(self._karten())

        box.append(InstallDropzone(
            "Mauszeiger-Design (.tar.gz/.zip) hierher ziehen",
            erwartet={"cursor"}))

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
        # Die FlowBox auf die Fensterbreite ziehen, damit das Raster in Reihen
        # umbricht (wie auf der Symbol-Seite, deren Breite das Dropdown vorgibt)
        # und die Seite keine übergroße Mindestbreite fordert.
        flowbox.set_hexpand(True)

        flowbox.connect("child-activated", self._on_karte_aktiviert)

        # Karten häppchenweise über den Idle-Handler bauen. Jede Karte parst
        # eine Xcursor-Binärdatei; alle auf einmal würde das Öffnen der Seite
        # sonst kurz einfrieren. So erscheint die Seite sofort und füllt sich.
        aktuell = self._settings.cursor_theme()
        namen = iter(themes.list_cursor_themes())

        def baue_naechste():
            for _ in range(2):  # zwei Karten pro Durchlauf
                try:
                    name = next(namen)
                except StopIteration:
                    return False  # fertig, Idle beenden
                karte = CursorCard(name, aktiv=(name == aktuell))
                flowbox.append(karte)
                self._cards.append(karte)
            return True

        GLib.idle_add(baue_naechste)
        return flowbox

    def _on_karte_aktiviert(self, _flowbox, karte):
        for andere in self._cards:
            andere.set_aktiv(andere is karte)
        self._settings.set_cursor_theme(karte.theme_name)
