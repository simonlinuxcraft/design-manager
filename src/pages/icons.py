"""Seite 'Symbole'.

Die installierten Symbol-Designs (Icons) als Vorschau-Karten mit echten
Beispiel-Icons; unten eine Ablage zum Installieren neuer Symbol-Designs. Ein
Klick auf eine Karte aktiviert das Design sofort.
"""

from gi.repository import Adw, GLib, Gtk

from src.core import themes, uninstaller
from src.widgets.dropzone import InstallDropzone
from src.widgets.theme_card import ThemeCard


# Sicherer Rückfallwert, falls das aktive Symbol-Design entfernt wird. Adwaita
# liegt systemweit und ist immer vorhanden.
STANDARD_ICON = "Adwaita"


class IconsPage(Adw.NavigationPage):
    """Navigationsseite mit den Symbol-Designs als Vorschau-Karten."""

    def __init__(self, settings):
        super().__init__(title="Symbole")
        self._settings = settings
        self._cards = []

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self._inhalt())
        self.set_child(toolbar)

    def _inhalt(self):
        """Scrollbarer Inhalt mit Karten und Installations-Ablage."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        untertitel = Gtk.Label(label="Änderungen werden sofort übernommen.",
                               xalign=0)
        untertitel.add_css_class("dim-label")
        box.append(untertitel)

        box.append(self._feld_titel("Symbol-Design (Icons)"))
        box.append(self._icon_karten())

        box.append(self._feld_titel("Neues Symbol-Design installieren"))
        box.append(InstallDropzone(
            "Symbol-Design (.tar.gz/.zip) hierher ziehen", erwartet={"icon"}))

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)
        return scroll

    # --- kleine Bausteine ---

    def _feld_titel(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("feld-titel")
        return label

    def _icon_karten(self):
        """Ein Raster aus Vorschaukarten, eine pro Symbol-Design."""
        flowbox = Gtk.FlowBox()
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        flowbox.set_max_children_per_line(4)
        flowbox.set_min_children_per_line(2)
        flowbox.set_column_spacing(10)
        flowbox.set_row_spacing(10)
        flowbox.set_homogeneous(True)
        flowbox.connect("child-activated", self._on_karte_aktiviert)
        self._flowbox = flowbox

        # Karten häppchenweise über den Idle-Handler bauen: die Icon-Lookups
        # summieren sich, das würde das Öffnen der Seite sonst spürbar
        # einfrieren. So erscheint die Seite sofort und füllt sich.
        aktuell = self._settings.icon_theme()
        namen = iter(themes.list_icon_themes())

        def baue_naechste():
            for _ in range(2):  # zwei Karten pro Durchlauf
                try:
                    name = next(namen)
                except StopIteration:
                    return False  # fertig, Idle beenden
                karte = ThemeCard(
                    name, aktiv=(name == aktuell),
                    loeschbar=uninstaller.ist_loeschbar(name, "icon"),
                    on_loeschen=self._on_loeschen)
                flowbox.append(karte)
                self._cards.append(karte)
            return True

        GLib.idle_add(baue_naechste)
        return flowbox

    def _on_karte_aktiviert(self, _flowbox, karte):
        # Genau die angeklickte Karte als aktiv markieren, die anderen nicht.
        for andere in self._cards:
            andere.set_aktiv(andere is karte)
        self._settings.set_icon_theme(karte.theme_name)

    # --- Entfernen ---

    def _on_loeschen(self, karte):
        """Sicherheitsabfrage vor dem Entfernen eines Symbol-Designs."""
        dialog = Adw.AlertDialog(
            heading="Symbol-Design entfernen?",
            body="„%s“ wird dauerhaft aus deinem Benutzerordner gelöscht. "
                 "Das lässt sich nicht rückgängig machen." % karte.theme_name)
        dialog.add_response("abbrechen", "Abbrechen")
        dialog.add_response("loeschen", "Entfernen")
        dialog.set_response_appearance(
            "loeschen", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("abbrechen")
        dialog.set_close_response("abbrechen")
        dialog.connect("response", self._on_loeschen_antwort, karte)
        dialog.present(self)

    def _on_loeschen_antwort(self, _dialog, antwort, karte):
        if antwort != "loeschen":
            return
        name = karte.theme_name
        if self._settings.icon_theme() == name:
            self._settings.set_icon_theme(STANDARD_ICON)
            for andere in self._cards:
                andere.set_aktiv(andere.theme_name == STANDARD_ICON)
        if uninstaller.deinstalliere(name, "icon"):
            self._flowbox.remove(karte)
            if karte in self._cards:
                self._cards.remove(karte)
            self._melde("Entfernt: " + name)
        else:
            self._melde("Konnte nicht entfernt werden: " + name)

    def _melde(self, text):
        fenster = self.get_root()
        if fenster is not None and hasattr(fenster, "zeige_toast"):
            fenster.zeige_toast(text)
