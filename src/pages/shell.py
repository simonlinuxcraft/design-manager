"""Seite 'Shell-Design'.

Setzt das GNOME-Shell-Design (Aussehen von Topbar, Kalender und Schnell-
einstellungen). Das geht nur über die Erweiterung User Themes: ist sie nicht
aktiv, gibt es das passende Schema nicht und wir zeigen statt der Auswahl einen
Hinweis. Sonst eine Galerie aus Vorschaukarten (kleine Topbar-Attrappe je
Design). Ein Klick wirkt sofort über org.gnome.shell.extensions.user-theme/name.
"""

from gi.repository import Adw, GLib, Gtk

from src.core import themes
from src.widgets.shell_card import ShellCard


class ShellPage(Adw.NavigationPage):
    """Navigationsseite zur Auswahl des GNOME-Shell-Designs."""

    def __init__(self, settings):
        super().__init__(title="Shell-Design")
        self._settings = settings
        self._cards = []

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self._inhalt())
        self.set_child(toolbar)

    def _inhalt(self):
        if not self._settings.user_themes_verfuegbar():
            return self._hinweis(
                "User Themes wird benötigt",
                "Das GNOME-Shell-Design wird über die Erweiterung User Themes "
                "gesetzt. Sie ist auf diesem System nicht installiert.")
        if not self._settings.user_themes_aktiv():
            return self._hinweis(
                "User Themes ist nicht eingeschaltet",
                "Die Erweiterung User Themes ist installiert, aber "
                "ausgeschaltet. Solange sie aus ist, wird ein gewähltes "
                "Shell-Design nicht angewendet. Schalte sie unter "
                "Erweiterungen ein, dann kannst du hier eines wählen.")
        return self._auswahl()

    def _hinweis(self, titel, beschreibung):
        return Adw.StatusPage(
            title=titel,
            description=beschreibung,
            icon_name="video-display-symbolic",
        )

    def _auswahl(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        untertitel = Gtk.Label(
            label="Wirkt auf Topbar, Kalender und Schnelleinstellungen. "
                  "Die Vorschau zeigt Panel- und Akzentfarbe (Annäherung).",
            xalign=0)
        untertitel.add_css_class("dim-label")
        untertitel.set_wrap(True)
        box.append(untertitel)

        box.append(self._feld_titel("Shell-Design"))
        box.append(self._karten())

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)
        return scroll

    def _feld_titel(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("feld-titel")
        return label

    def _karten(self):
        flowbox = Gtk.FlowBox()
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        flowbox.set_max_children_per_line(4)
        flowbox.set_min_children_per_line(2)
        flowbox.set_column_spacing(10)
        flowbox.set_row_spacing(10)
        flowbox.set_homogeneous(True)
        flowbox.connect("child-activated", self._on_karte_aktiviert)

        # Einträge (theme_name, Anzeige): "Standard" (leerer Wert) zuerst.
        aktuell = self._settings.shell_theme()
        eintraege = iter([("", "Standard")]
                         + [(n, n) for n in themes.list_shell_themes()])

        # Karten häppchenweise bauen (jede parst eine CSS), damit die Seite
        # sofort erscheint und sich füllt.
        def baue_naechste():
            for _ in range(3):
                try:
                    name, anzeige = next(eintraege)
                except StopIteration:
                    return False
                karte = ShellCard(name, anzeige, aktiv=(name == aktuell))
                flowbox.append(karte)
                self._cards.append(karte)
            return True

        GLib.idle_add(baue_naechste)
        return flowbox

    def _on_karte_aktiviert(self, _flowbox, karte):
        for andere in self._cards:
            andere.set_aktiv(andere is karte)
        self._settings.set_shell_theme(karte.theme_name)
