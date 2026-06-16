"""Seite 'Schriftarten'.

Oben die drei Schriften, die GNOME getrennt führt: die Oberflächenschrift
(font-name), die Schrift für Fließtext (document-font-name) und die
dicktengleiche Schrift für Terminal und Code (monospace-font-name). Jede über
einen Gtk.FontDialogButton, der eine Pango.FontDescription liefert; wir
speichern sie als Text (z.B. "Cantarell 11").

Darunter die Darstellung: die globale Schrift-Skalierung sowie Glättung
(Antialiasing) und Hinting. Unten eine Ablage zum Installieren neuer Schriften.
"""

from gi.repository import Adw, Gtk

from src import compat
from src.i18n import _
from src.widgets.dropzone import InstallDropzone


# Enum-Werte von font-antialiasing und font-hinting mit ihren Labels.
ANTIALIASING = [
    (_("Grayscale"), "grayscale"),
    (_("Subpixel (RGBA)"), "rgba"),
    (_("None"), "none"),
]
HINTING = [
    (_("Full"), "full"),
    (_("Medium"), "medium"),
    (_("Slight"), "slight"),
    (_("None"), "none"),
]


class FontsPage(compat.PageBase):
    """Navigationsseite zur Auswahl und Darstellung der Systemschriften."""

    def __init__(self, settings):
        super().__init__(title=_("Fonts"))
        self._settings = settings

        schriften = Adw.PreferencesGroup(
            title=_("Fonts"),
            description=_("GNOME keeps three fonts separate."))
        schriften.add(self._schrift_zeile(
            _("Interface"), self._settings.font_name,
            self._settings.set_font_name))
        schriften.add(self._schrift_zeile(
            _("Documents"), self._settings.document_font_name,
            self._settings.set_document_font_name))
        schriften.add(self._schrift_zeile(
            _("Monospace"), self._settings.monospace_font_name,
            self._settings.set_monospace_font_name))

        darstellung = Adw.PreferencesGroup(
            title=_("Rendering"),
            description=_("Size and smoothing of the font rendering."))
        darstellung.add(self._skalierung_zeile())
        darstellung.add(self._enum_zeile(
            _("Smoothing"), ANTIALIASING,
            self._settings.font_antialiasing,
            self._settings.set_font_antialiasing))
        darstellung.add(self._enum_zeile(
            _("Hinting"), HINTING,
            self._settings.font_hinting,
            self._settings.set_font_hinting))

        installieren = Adw.PreferencesGroup(
            title=_("Install a font"),
            description=_("Drag a font file (.ttf/.otf) or an archive here. "
                          "It is copied to ~/.local/share/fonts and the font "
                          "cache is refreshed."))
        installieren.add(InstallDropzone(
            _("Drag a font (.ttf/.otf) or archive here"),
            erwartet={"font"}))

        seite = Adw.PreferencesPage()
        seite.add(schriften)
        seite.add(darstellung)
        seite.add(installieren)

        toolbar = compat.toolbar_view(
            top_bars=[Adw.HeaderBar()], content=seite)
        self.set_child(toolbar)

    # --- Schrift-Wähler ---

    def _schrift_zeile(self, titel, get_wert, set_wert):
        """Eine Zeile mit Schrift-Auswahlknopf, an einen Schlüssel gebunden."""
        zeile = Adw.ActionRow(title=titel)

        button = compat.font_button(get_wert(), set_wert)
        button.set_valign(Gtk.Align.CENTER)

        zeile.add_suffix(button)
        zeile.set_activatable_widget(button)
        return zeile

    # --- Skalierung ---

    def _skalierung_zeile(self):
        """Schrift-Skalierung als Drehfeld (1.0 = Standard)."""
        zeile = compat.SpinRow.new_with_range(0.5, 2.0, 0.05)
        zeile.set_title(_("Size (scaling)"))
        zeile.set_subtitle(_("1.0 is the default size."))
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
        zeile.set_model(Gtk.StringList.new([label for label, _wert in optionen]))

        aktuell = get_wert()
        for i, (_label, wert) in enumerate(optionen):
            if wert == aktuell:
                zeile.set_selected(i)
                break

        zeile.connect("notify::selected", self._on_enum_changed, optionen, set_wert)
        return zeile

    def _on_enum_changed(self, zeile, _param, optionen, set_wert):
        i = zeile.get_selected()
        if 0 <= i < len(optionen):
            set_wert(optionen[i][1])
