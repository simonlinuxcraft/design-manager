"""Seite 'Symbole'.

Die installierten Symbol-Designs (Icons) als Vorschau-Karten mit echten
Beispiel-Icons; unten eine Ablage zum Installieren neuer Symbol-Designs. Ein
Klick auf eine Karte aktiviert das Design sofort.
"""

from gi.repository import Adw, GLib, Gtk

from src import compat
from src.core import themes, uninstaller
from src.i18n import _
from src.widgets.dropzone import InstallDropzone
from src.widgets.theme_card import ThemeCard


# Sicherer Rückfallwert, falls das aktive Symbol-Design entfernt wird. Adwaita
# liegt systemweit und ist immer vorhanden.
STANDARD_ICON = "Adwaita"


class IconsPage(compat.PageBase):
    """Navigationsseite mit den Symbol-Designs als Vorschau-Karten."""

    def __init__(self, settings):
        super().__init__(title=_("Icons"))
        self._settings = settings
        self._cards = []

        toolbar = compat.toolbar_view(
            top_bars=[Adw.HeaderBar()], content=self._inhalt())
        self.set_child(toolbar)

    def _inhalt(self):
        """Scrollbarer Inhalt mit Karten und Installations-Ablage."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        untertitel = Gtk.Label(label=_("Changes take effect immediately."),
                               xalign=0)
        untertitel.add_css_class("dim-label")
        box.append(untertitel)

        box.append(self._feld_titel(_("Icon theme")))
        box.append(self._icon_karten())

        box.append(self._feld_titel(_("Install a new icon theme")))
        box.append(InstallDropzone(
            _("Drag an icon theme (.tar.gz/.zip) here"), erwartet={"icon"}))

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
        compat.alert(
            self,
            _("Remove icon theme?"),
            _('"{name}" will be permanently deleted from your user folder. '
              "This cannot be undone.").format(name=karte.theme_name),
            [("abbrechen", _("Cancel"), ""),
             ("loeschen", _("Remove"), "destructive")],
            default="abbrechen", close="abbrechen",
            on_response=lambda antwort: self._on_loeschen_antwort(antwort, karte))

    def _on_loeschen_antwort(self, antwort, karte):
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
            self._melde(_("Removed: {name}").format(name=name))
        else:
            self._melde(_("Could not be removed: {name}").format(name=name))

    def _melde(self, text):
        fenster = self.get_root()
        if fenster is not None and hasattr(fenster, "zeige_toast"):
            fenster.zeige_toast(text)
