"""Seite 'Schriftarten'.

Oben die drei Schriften, die GNOME getrennt führt: die Oberflächenschrift
(font-name), die Schrift für Fließtext (document-font-name) und die
dicktengleiche Schrift für Terminal und Code (monospace-font-name). Jede über
einen Gtk.FontDialogButton, der eine Pango.FontDescription liefert; wir
speichern sie als Text (z.B. "Cantarell 11").

Darunter die Darstellung: die globale Schrift-Skalierung sowie Glättung
(Antialiasing) und Hinting. Unten eine Ablage zum Installieren neuer Schriften.
"""

from gi.repository import Adw, Gtk, Pango

from src.widgets.dropzone import InstallDropzone


# Enum-Werte von font-antialiasing und font-hinting mit deutschen Labels.
ANTIALIASING = [
    ("Graustufen", "grayscale"),
    ("Subpixel (RGBA)", "rgba"),
    ("Keine", "none"),
]
HINTING = [
    ("Voll", "full"),
    ("Mittel", "medium"),
    ("Leicht", "slight"),
    ("Keine", "none"),
]


class FontsPage(Adw.NavigationPage):
    """Navigationsseite zur Auswahl und Darstellung der Systemschriften."""

    def __init__(self, settings):
        super().__init__(title="Schriftarten")
        self._settings = settings

        schriften = Adw.PreferencesGroup(
            title="Schriftarten",
            description="GNOME führt drei Schriften getrennt.")
        schriften.add(self._schrift_zeile(
            "Oberfläche", self._settings.font_name,
            self._settings.set_font_name))
        schriften.add(self._schrift_zeile(
            "Dokumente", self._settings.document_font_name,
            self._settings.set_document_font_name))
        schriften.add(self._schrift_zeile(
            "Festbreite (Monospace)", self._settings.monospace_font_name,
            self._settings.set_monospace_font_name))

        darstellung = Adw.PreferencesGroup(
            title="Darstellung",
            description="Größe und Glättung des Schriftbilds.")
        darstellung.add(self._skalierung_zeile())
        darstellung.add(self._enum_zeile(
            "Glättung", ANTIALIASING,
            self._settings.font_antialiasing,
            self._settings.set_font_antialiasing))
        darstellung.add(self._enum_zeile(
            "Hinting", HINTING,
            self._settings.font_hinting,
            self._settings.set_font_hinting))

        installieren = Adw.PreferencesGroup(
            title="Schrift installieren",
            description="Eine Schriftdatei (.ttf/.otf) oder ein Archiv "
                        "hierher ziehen. Sie wird nach ~/.local/share/fonts "
                        "kopiert und der Schrift-Cache aufgefrischt.")
        installieren.add(InstallDropzone(
            "Schrift (.ttf/.otf) oder Archiv hierher ziehen",
            erwartet={"font"}))

        seite = Adw.PreferencesPage()
        seite.add(schriften)
        seite.add(darstellung)
        seite.add(installieren)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(seite)
        self.set_child(toolbar)

    # --- Schrift-Wähler ---

    def _schrift_zeile(self, titel, get_wert, set_wert):
        """Eine Zeile mit Gtk.FontDialogButton, an einen Schlüssel gebunden."""
        zeile = Adw.ActionRow(title=titel)

        button = Gtk.FontDialogButton.new(Gtk.FontDialog())
        button.set_valign(Gtk.Align.CENTER)

        aktuell = get_wert()
        if aktuell:
            button.set_font_desc(Pango.FontDescription.from_string(aktuell))

        # Erst nach dem Voreinstellen verbinden, sonst löst das schon aus.
        button.connect("notify::font-desc", self._on_schrift_changed, set_wert)

        zeile.add_suffix(button)
        zeile.set_activatable_widget(button)
        return zeile

    def _on_schrift_changed(self, button, _param, set_wert):
        desc = button.get_font_desc()
        if desc is not None:
            set_wert(desc.to_string())

    # --- Skalierung ---

    def _skalierung_zeile(self):
        """Schrift-Skalierung als Drehfeld (1.0 = Standard)."""
        zeile = Adw.SpinRow.new_with_range(0.5, 2.0, 0.05)
        zeile.set_title("Größe (Skalierung)")
        zeile.set_subtitle("1.0 ist die Standardgröße.")
        zeile.set_digits(2)
        zeile.set_value(self._settings.text_scaling_factor())
        zeile.connect("notify::value", self._on_skalierung)
        return zeile

    def _on_skalierung(self, zeile, _param):
        self._settings.set_text_scaling_factor(zeile.get_value())

    # --- Enum-Auswahl (Glättung, Hinting) ---

    def _enum_zeile(self, titel, optionen, get_wert, set_wert):
        """Eine Adw.ComboRow über 'optionen' (Label, Wert), bindet einen Enum."""
        zeile = Adw.ComboRow(title=titel)
        zeile.set_model(Gtk.StringList.new([label for label, _ in optionen]))

        aktuell = get_wert()
        for i, (_, wert) in enumerate(optionen):
            if wert == aktuell:
                zeile.set_selected(i)
                break

        zeile.connect("notify::selected", self._on_enum_changed, optionen, set_wert)
        return zeile

    def _on_enum_changed(self, zeile, _param, optionen, set_wert):
        i = zeile.get_selected()
        if 0 <= i < len(optionen):
            set_wert(optionen[i][1])
