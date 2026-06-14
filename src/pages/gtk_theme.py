"""Seite 'GTK-Design'.

Das GTK-Design bestimmt das Aussehen der Programmfenster. Oben die Auswahl als
Dropdown mit einem 'Standard'-Knopf als Notausstieg, darunter eine Ablage zum
Installieren neuer GTK-Designs.

Wichtig: moderne GNOME-Apps (Nautilus, Einstellungen, Texteditor) sind
libadwaita-Apps und ignorieren benannte GTK-Designs. Die App spiegelt das
gewählte Design darum zusätzlich nach ~/.config/gtk-4.0, damit es auch dort
wirkt (siehe core/settings.py). Der 'Standard'-Knopf räumt diesen Spiegel
wieder weg.
"""

from gi.repository import Adw, Gtk

from src.core import restorepoint, theme_check, themes
from src.widgets.dropzone import InstallDropzone


class GtkThemePage(Adw.NavigationPage):
    """Navigationsseite für die Auswahl des GTK-Designs."""

    def __init__(self, settings):
        super().__init__(title="GTK-Design")
        self._settings = settings

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self._inhalt())
        self.set_child(toolbar)

    def _inhalt(self):
        """Scrollbarer Inhalt mit Auswahl und Installations-Ablage."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        untertitel = Gtk.Label(
            label="Bestimmt das Aussehen der Programmfenster. Wird sofort "
                  "übernommen und auch auf moderne Apps wie Dateien angewendet.",
            xalign=0, wrap=True)
        untertitel.add_css_class("dim-label")
        box.append(untertitel)

        box.append(self._feld_titel("GTK-Design (Fenster & Programme)"))
        box.append(self._gtk_design_zeile())

        box.append(self._feld_titel("Neues GTK-Design installieren"))
        box.append(InstallDropzone(
            "GTK-Design (.tar.gz/.zip) hierher ziehen", erwartet={"gtk"}))

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

        Der Knopf setzt das GTK-Design auf Adwaita zurück und entfernt den
        libadwaita-Spiegel. Adwaita ist in GTK eingebaut und immer gültig, also
        der schnelle Weg zurück, falls ein gewähltes Design (z.B. mit ungültigem
        CSS) die Oberfläche unbrauchbar macht.
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
        if eintrag is None:
            return
        name = eintrag.get_string()
        # Vor dem Aktivieren prüfen, ob die gtk.css wirklich da ist. Fehlt sie,
        # würde GNOME still auf Adwaita zurückfallen; lieber vorher fragen.
        ok, grund = theme_check.pruefe_gtk(name)
        if not ok:
            self._gtk_trotzdem_fragen(name, grund)
            return
        restorepoint.erstelle(self._settings, "vor GTK-Design " + name)
        setter(name)

    def _gtk_trotzdem_fragen(self, name, grund):
        dialog = Adw.AlertDialog(
            heading="Design trotzdem aktivieren?",
            body="„%s“: %s" % (name, grund))
        dialog.add_response("abbrechen", "Abbrechen")
        dialog.add_response("trotzdem", "Trotzdem aktivieren")
        dialog.set_response_appearance(
            "trotzdem", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("abbrechen")
        dialog.set_close_response("abbrechen")
        dialog.connect("response", self._on_gtk_trotzdem, name)
        dialog.present(self)

    def _on_gtk_trotzdem(self, _dialog, antwort, name):
        if antwort == "trotzdem":
            restorepoint.erstelle(self._settings, "vor GTK-Design " + name)
            self._settings.set_gtk_theme(name)
            return
        # Abbrechen: das Dropdown hat die Auswahl schon geändert, also auf das
        # tatsächlich aktive Design zurückziehen (ohne den Handler erneut
        # auszulösen).
        aktuell = self._settings.gtk_theme()
        if aktuell in self._gtk_namen:
            self._gtk_dropdown.handler_block(self._gtk_handler_id)
            self._gtk_dropdown.set_selected(self._gtk_namen.index(aktuell))
            self._gtk_dropdown.handler_unblock(self._gtk_handler_id)

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
