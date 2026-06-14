"""Seite 'Mauszeiger'.

Zeigt die installierten Mauszeiger-Designs als Vorschaukarten (mit echtem
Zeiger), genau wie die Symbol-Designs. Klick setzt sofort: GTK-Programme und der
Desktop-Zeiger wechseln live. Nur schon geöffnete Nicht-GTK-Programme (manche
Terminals, Electron-Apps) behalten den alten Zeiger, bis sie neu gestartet
werden.
"""

from gi.repository import Adw, GLib, Gtk

from src.core import restorepoint, themes, uninstaller
from src.widgets.cursor_card import CursorCard
from src.widgets.dropzone import InstallDropzone


# Sicherer Rückfallwert, falls das gerade aktive Design entfernt wird. Adwaita
# liegt systemweit (/usr/share/icons/Adwaita) und hat einen Mauszeiger.
STANDARD_CURSOR = "Adwaita"


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
        self._flowbox = flowbox

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
                karte = CursorCard(
                    name, aktiv=(name == aktuell),
                    loeschbar=uninstaller.ist_loeschbar(name, "cursor"),
                    on_loeschen=self._on_loeschen)
                flowbox.append(karte)
                self._cards.append(karte)
            return True

        GLib.idle_add(baue_naechste)
        return flowbox

    def _on_karte_aktiviert(self, _flowbox, karte):
        for andere in self._cards:
            andere.set_aktiv(andere is karte)
        restorepoint.erstelle(self._settings, "vor Mauszeiger " + karte.theme_name)
        self._settings.set_cursor_theme(karte.theme_name)

    # --- Entfernen ---

    def _on_loeschen(self, karte):
        """Sicherheitsabfrage vor dem Entfernen eines Mauszeiger-Designs."""
        dialog = Adw.AlertDialog(
            heading="Mauszeiger entfernen?",
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
        # War es das aktive Design, vorher auf den sicheren Standard schalten,
        # damit kein gelöschtes Theme gesetzt bleibt.
        if self._settings.cursor_theme() == name:
            self._settings.set_cursor_theme(STANDARD_CURSOR)
            for andere in self._cards:
                andere.set_aktiv(andere.theme_name == STANDARD_CURSOR)
        if uninstaller.deinstalliere(name, "cursor"):
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
