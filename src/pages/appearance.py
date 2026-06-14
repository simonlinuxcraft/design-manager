"""Seite 'Symbole & Design'.

Oben das GTK-Design als Dropdown, darunter die Symbol-Designs als Vorschau-
Karten (echte Beispiel-Icons), unten eine Ablage zum Installieren neuer
Designs. Mauszeiger und Schrift haben eigene Seiten.

Jede Auswahl wirkt sofort, weil der jeweilige Setter direkt den passenden
dconf-Schlüssel setzt.
"""

from gi.repository import Adw, GLib, Gtk

from src.core import themes
from src.widgets.dropzone import InstallDropzone
from src.widgets.theme_card import ThemeCard


class AppearancePage(Adw.NavigationPage):
    """Navigationsseite mit GTK-Design und Symbol-Vorschau."""

    def __init__(self, settings):
        # NavigationPage-Titel (AdwWindowTitle) ist reiner Text, kein Markup,
        # daher das & direkt.
        super().__init__(title="Symbole & Design")
        self._settings = settings
        self._cards = []

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self._inhalt())
        self.set_child(toolbar)

    def _inhalt(self):
        """Scrollbarer Inhalt mit allen Abschnitten untereinander."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        untertitel = Gtk.Label(label="Änderungen werden sofort übernommen.",
                               xalign=0)
        untertitel.add_css_class("dim-label")
        box.append(untertitel)

        box.append(self._feld_titel("GTK-Design (Fenster & Programme)"))
        box.append(self._gtk_design_zeile())

        box.append(self._feld_titel("Symbol-Design (Icons)"))
        box.append(self._icon_karten())

        box.append(self._feld_titel("Neues Design installieren"))
        box.append(InstallDropzone(
            "GTK- oder Symbol-Design (.tar.gz/.zip) hierher ziehen",
            erwartet={"gtk", "icon"}))

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)
        return scroll

    # --- kleine Bausteine ---

    def _feld_titel(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("feld-titel")
        return label

    def _gtk_design_zeile(self):
        """GTK-Design-Dropdown plus ein 'Standard'-Knopf als Notausstieg.

        Der Knopf setzt das GTK-Design auf Adwaita zurück. Adwaita ist in GTK
        eingebaut und immer gültig, also der schnelle Weg zurück, falls ein
        gewähltes Design (z.B. mit ungültigem CSS) die Oberfläche unbrauchbar
        macht. Adwaita steht auf diesem System ohnehin in der Liste.
        """
        self._gtk_namen = themes.list_gtk_themes()
        if self._settings.SAFE_GTK_THEME not in self._gtk_namen:
            self._gtk_namen.insert(0, self._settings.SAFE_GTK_THEME)

        self._gtk_dropdown = Gtk.DropDown.new_from_strings(self._gtk_namen)
        self._gtk_dropdown.set_hexpand(True)
        aktuell = self._settings.gtk_theme()
        if aktuell in self._gtk_namen:
            self._gtk_dropdown.set_selected(self._gtk_namen.index(aktuell))
        # Erst nach dem Vorauswählen verbinden, sonst zählt die Vorauswahl schon
        # als Änderung. Handler-ID merken, damit das Nachziehen beim Reset nicht
        # erneut als Nutzerauswahl zählt.
        self._gtk_handler_id = self._gtk_dropdown.connect(
            "notify::selected", self._on_dropdown_changed,
            self._settings.set_gtk_theme)

        standard = Gtk.Button(label="Standard")
        standard.set_valign(Gtk.Align.CENTER)
        standard.set_tooltip_text(
            "GTK-Design auf das sichere Standard-Design (Adwaita) zurücksetzen")
        standard.connect("clicked", self._on_gtk_reset)

        zeile = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        zeile.append(self._gtk_dropdown)
        zeile.append(standard)
        return zeile

    def _on_dropdown_changed(self, dropdown, _param, setter):
        eintrag = dropdown.get_selected_item()
        if eintrag is not None:
            setter(eintrag.get_string())

    def _on_gtk_reset(self, _knopf):
        """Notausstieg: GTK-Design auf Adwaita zurück und Dropdown nachziehen."""
        self._settings.reset_gtk_theme()
        name = self._settings.SAFE_GTK_THEME
        if name in self._gtk_namen:
            # Handler blockieren: das Nachziehen ist Folge des Resets, keine
            # neue Nutzerauswahl, sonst würde set_gtk_theme doppelt feuern.
            self._gtk_dropdown.handler_block(self._gtk_handler_id)
            self._gtk_dropdown.set_selected(self._gtk_namen.index(name))
            self._gtk_dropdown.handler_unblock(self._gtk_handler_id)

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

        # Karten häppchenweise über den Idle-Handler bauen: die Icon-Lookups
        # summieren sich (37 Designs), das würde das Öffnen der Seite sonst
        # spürbar einfrieren. So erscheint die Seite sofort und füllt sich.
        aktuell = self._settings.icon_theme()
        namen = iter(themes.list_icon_themes())

        def baue_naechste():
            for _ in range(2):  # zwei Karten pro Durchlauf
                try:
                    name = next(namen)
                except StopIteration:
                    return False  # fertig, Idle beenden
                karte = ThemeCard(name, aktiv=(name == aktuell))
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
