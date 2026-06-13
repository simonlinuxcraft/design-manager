"""Seite 'Schriftarten'.

Ein Schrift-Wähler (Gtk.FontDialogButton) für die Systemschrift. Er liefert
eine Pango.FontDescription mit Familie und Größe; wir speichern sie als Text
(z.B. "Cantarell 11") im dconf-Schlüssel font-name.
"""

from gi.repository import Adw, Gtk, Pango


class FontsPage(Adw.NavigationPage):
    """Navigationsseite zur Auswahl der Systemschrift."""

    def __init__(self, settings):
        super().__init__(title="Schriftarten")
        self._settings = settings

        gruppe = Adw.PreferencesGroup(
            title="Systemschrift",
            description="Die Schriftart der Oberfläche.",
        )

        zeile = Adw.ActionRow(title="Schriftart")

        self._button = Gtk.FontDialogButton.new(Gtk.FontDialog())
        self._button.set_valign(Gtk.Align.CENTER)

        # Aktuelle Schrift voreinstellen.
        aktuell = self._settings.font_name()
        if aktuell:
            self._button.set_font_desc(Pango.FontDescription.from_string(aktuell))

        # Erst nach dem Voreinstellen verbinden, sonst löst das Setzen schon aus.
        self._button.connect("notify::font-desc", self._on_changed)

        zeile.add_suffix(self._button)
        zeile.set_activatable_widget(self._button)
        gruppe.add(zeile)

        seite = Adw.PreferencesPage()
        seite.add(gruppe)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(seite)
        self.set_child(toolbar)

    def _on_changed(self, button, _param):
        desc = button.get_font_desc()
        if desc is not None:
            self._settings.set_font_name(desc.to_string())
