"""Seite 'Hintergrund'.

Aufbau: Vorschau des aktuellen Bildes, eine Galerie der Standard-Hintergründe
(und der eigenen), ein Knopf zum Wählen eines eigenen Bildes und ein Dropdown
für den Anpassungsmodus (Zoom, gestreckt, ...).

Eine Auswahl wirkt sofort: das Bild wird als picture-uri (hell und dunkel)
gesetzt, der Modus über picture-options.
"""

import os
import shutil

from gi.repository import Adw, Gio, GLib, Gtk

from src.core import backgrounds
from src.widgets.wallpaper_card import WallpaperCard


# Zielordner für selbst gewählte Bilder.
BACKGROUND_DIR = os.path.expanduser("~/.local/share/backgrounds")

# Anpassungsmodus: deutsches Label und der dazugehörige Enum-Wert von
# picture-options.
MODI = [
    ("Zoom (Vollbild)", "zoom"),
    ("Eingepasst", "scaled"),
    ("Gestreckt", "stretched"),
    ("Zentriert", "centered"),
    ("Gekachelt", "wallpaper"),
    ("Über mehrere Bildschirme", "spanned"),
    ("Keine", "none"),
]


class BackgroundPage(Adw.NavigationPage):
    """Navigationsseite zum Setzen des Hintergrundbilds und seines Modus."""

    def __init__(self, settings):
        super().__init__(title="Hintergrund")
        self._settings = settings
        self._cards = []

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        box.append(self._feld_titel("Aktuelles Bild"))
        self._vorschau = Gtk.Picture()
        self._vorschau.set_content_fit(Gtk.ContentFit.COVER)
        self._vorschau.set_size_request(-1, 200)
        self._vorschau.add_css_class("card")
        box.append(self._vorschau)
        self._zeige_aktuellen()

        box.append(self._feld_titel("Standard-Hintergründe"))
        self._galerie = Gtk.FlowBox()
        self._galerie.set_selection_mode(Gtk.SelectionMode.NONE)
        self._galerie.set_max_children_per_line(4)
        self._galerie.set_min_children_per_line(2)
        self._galerie.set_column_spacing(10)
        self._galerie.set_row_spacing(10)
        self._galerie.set_homogeneous(True)
        self._galerie.connect("child-activated", self._on_card_aktiviert)
        box.append(self._galerie)
        self._fuelle_galerie()

        knopf = Gtk.Button(label="Eigenes Bild wählen …")
        knopf.set_halign(Gtk.Align.START)
        knopf.connect("clicked", self._on_eigenes)
        box.append(knopf)

        box.append(self._feld_titel("Anpassung"))
        box.append(self._modus_dropdown())

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(scroll)
        self.set_child(toolbar)

    # --- Bausteine ---

    def _feld_titel(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("feld-titel")
        return label

    def _aktueller_pfad(self):
        """Dateipfad des aktuell gesetzten Hintergrunds, oder None."""
        uri = self._settings.background_uri()
        if not uri:
            return None
        pfad = Gio.File.new_for_uri(uri).get_path()
        return os.path.realpath(pfad) if pfad else None

    def _zeige_aktuellen(self):
        pfad = self._aktueller_pfad()
        if pfad and os.path.isfile(pfad):
            self._vorschau_setzen(pfad)

    def _vorschau_setzen(self, pfad):
        """Setzt die Vorschau verkleinert und nebenher (kein Hängen bei großen Bildern)."""
        backgrounds.load_texture_async(pfad, 1400, 400, self._vorschau.set_paintable)

    def _fuelle_galerie(self):
        """Baut die Karten der Galerie neu auf und markiert das aktive Bild.

        System-Bilder sind fest, eigene Bilder bekommen einen Entfernen-Knopf.
        """
        self._galerie.remove_all()
        self._cards = []
        aktuell = self._aktueller_pfad()

        def hinzufuegen(pfad, entfernbar):
            aktiv = (aktuell is not None and os.path.realpath(pfad) == aktuell)
            karte = WallpaperCard(
                pfad, aktiv,
                entfernbar=entfernbar,
                on_entfernen=self._on_entfernen if entfernbar else None,
            )
            self._galerie.append(karte)
            self._cards.append(karte)

        for pfad in backgrounds.list_system_wallpapers():
            hinzufuegen(pfad, False)
        for pfad in backgrounds.list_user_wallpapers():
            hinzufuegen(pfad, True)

    def _on_entfernen(self, pfad):
        # Nur in der App ausblenden, Datei bleibt erhalten.
        backgrounds.hide_wallpaper(pfad)
        self._fuelle_galerie()

    def _on_card_aktiviert(self, _flowbox, karte):
        for andere in self._cards:
            andere.set_aktiv(andere is karte)
        self._setze_bild(karte.pfad)

    def _setze_bild(self, pfad):
        uri = Gio.File.new_for_path(pfad).get_uri()
        self._settings.set_background_uri(uri)
        self._settings.set_background_uri_dark(uri)
        self._vorschau_setzen(pfad)

    def _on_eigenes(self, _knopf):
        dialog = Gtk.FileDialog()
        dialog.set_title("Hintergrundbild wählen")

        bilder = Gtk.FileFilter()
        bilder.set_name("Bilder")
        bilder.add_mime_type("image/*")
        filter_liste = Gio.ListStore.new(Gtk.FileFilter)
        filter_liste.append(bilder)
        dialog.set_filters(filter_liste)

        dialog.open(self.get_root(), None, self._on_gewaehlt)

    def _on_gewaehlt(self, dialog, ergebnis):
        try:
            datei = dialog.open_finish(ergebnis)
        except GLib.Error:
            return  # abgebrochen oder Fehler

        pfad = datei.get_path()
        if not pfad:
            return

        ziel = self._kopiere_ins_backgrounds(pfad)
        self._setze_bild(ziel)
        # Galerie neu aufbauen, damit das neue Bild auftaucht und aktiv ist.
        self._fuelle_galerie()

    def _kopiere_ins_backgrounds(self, quelle):
        os.makedirs(BACKGROUND_DIR, exist_ok=True)
        ziel = os.path.join(BACKGROUND_DIR, os.path.basename(quelle))
        if os.path.abspath(quelle) != os.path.abspath(ziel):
            shutil.copy2(quelle, ziel)
        return ziel

    def _modus_dropdown(self):
        labels = [label for label, _ in MODI]
        dropdown = Gtk.DropDown.new_from_strings(labels)
        dropdown.set_hexpand(True)

        aktuell = self._settings.picture_options()
        for i, (_, wert) in enumerate(MODI):
            if wert == aktuell:
                dropdown.set_selected(i)
                break

        dropdown.connect("notify::selected", self._on_modus)
        return dropdown

    def _on_modus(self, dropdown, _param):
        index = dropdown.get_selected()
        if 0 <= index < len(MODI):
            self._settings.set_picture_options(MODI[index][1])
