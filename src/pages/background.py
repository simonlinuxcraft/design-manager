"""Seite 'Hintergrund'.

Aufbau: Vorschau des aktuellen Bildes, eine Galerie der Standard-Hintergründe
(und der eigenen), ein Knopf zum Wählen eines eigenen Bildes und ein Dropdown
für den Anpassungsmodus (Zoom, gestreckt, ...).

Eine Auswahl wirkt sofort: das Bild wird als picture-uri (hell und dunkel)
gesetzt, der Modus über picture-options.
"""

import os
import shutil
import threading

from gi.repository import Adw, Gio, GLib, Gtk

from src.core import backgrounds, gdm, lockscreen, variety
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
        # Einmal prüfen, ob Variety läuft; steuert Hinweis und Modus-Auswahl.
        self._variety_aktiv = variety.laeuft()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        if self._variety_aktiv:
            box.append(self._variety_banner())

        box.append(self._feld_titel("Aktuelles Bild"))
        box.append(self._vorschau_bereich())
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

        box.append(self._feld_titel("Sperrbildschirm"))
        box.append(self._sperr_bereich())
        self._zeige_sperr()

        # Anmeldebildschirm nur zeigen, wenn der root-Weg überhaupt möglich ist.
        if gdm.verfuegbar():
            box.append(self._feld_titel("Anmeldebildschirm (GDM)"))
            box.append(self._gdm_bereich())

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

    def _variety_banner(self):
        """Hinweis, dass Variety den Hintergrund verwaltet, plus ein Knopf zum
        Rausnehmen (Autostart aus, beenden, Bild stabil setzen). Reversibel."""
        self._variety_label = Gtk.Label(
            label="Variety verwaltet den Hintergrund. Deine Bildauswahl wird an "
                  "Variety übergeben und bleibt über jeden Login erhalten. Den "
                  "Anpassungsmodus unten kannst du ändern, beim nächsten Login "
                  "setzt Variety aber wieder seinen eigenen. Für volle Kontrolle "
                  "über Bild und Modus kannst du Variety hier rausnehmen.",
            xalign=0, wrap=True)
        self._variety_label.add_css_class("dim-label")

        self._variety_knopf = Gtk.Button(label="Variety rausnehmen")
        self._variety_knopf.set_halign(Gtk.Align.START)
        self._variety_knopf.set_tooltip_text(
            "Variety aus dem Autostart nehmen und beenden, damit die App den "
            "Hintergrund und den Modus direkt steuert. Umkehrbar, Variety bleibt "
            "installiert.")
        self._variety_knopf.connect("clicked", self._on_variety_raus)

        self._variety_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._variety_box.append(self._variety_label)
        self._variety_box.append(self._variety_knopf)
        return self._variety_box

    def _on_variety_raus(self, _knopf):
        """Nimmt Variety aus dem Spiel: Autostart aus, beenden, Hintergrund von
        Varietys Zwischendatei auf ein stabiles Quellbild umbiegen."""
        quelle = variety.aktuelles_quellbild()  # vor dem Beenden lesen
        variety.autostart_aus()
        variety.beenden()
        self._variety_aktiv = False

        # Bild von Varietys Zwischendatei auf das echte Quellbild umbiegen, damit
        # es bleibt, falls Varietys Cache mal geleert wird.
        if quelle and os.path.isfile(quelle):
            uri = Gio.File.new_for_path(quelle).get_uri()
            self._settings.set_background_uri(uri)
            self._settings.set_background_uri_dark(uri)
            self._vorschau_setzen(quelle)

        self._variety_label.set_label(
            "Variety wurde aus dem Autostart genommen und beendet. Die App "
            "verwaltet den Hintergrund jetzt direkt, dein Anpassungsmodus bleibt "
            "erhalten. Rückgängig: Variety wieder starten und im Autostart "
            "aktivieren.")
        self._variety_box.remove(self._variety_knopf)

    def _vorschau_bereich(self):
        """Vorschau-Bild mit einem Platzhalter-Hinweis, falls kein Bild gesetzt ist."""
        self._vorschau = Gtk.Picture()
        self._vorschau.set_content_fit(Gtk.ContentFit.COVER)
        self._vorschau.set_size_request(-1, 200)
        self._vorschau.add_css_class("card")

        self._platzhalter = Gtk.Label(label="Kein Hintergrundbild gesetzt")
        self._platzhalter.add_css_class("dim-label")
        self._platzhalter.set_halign(Gtk.Align.CENTER)
        self._platzhalter.set_valign(Gtk.Align.CENTER)
        self._platzhalter.set_can_target(False)  # Klicks gehen ans Bild dahinter

        overlay = Gtk.Overlay()
        overlay.set_child(self._vorschau)
        overlay.add_overlay(self._platzhalter)
        return overlay

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
        else:
            self._platzhalter.set_visible(True)

    def _vorschau_setzen(self, pfad):
        """Setzt die Vorschau verkleinert und nebenher (kein Hängen bei großen Bildern)."""
        self._platzhalter.set_visible(False)
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
        # Variety-respektierendes Setzen liegt jetzt zentral in core/backgrounds,
        # damit auch Look-Sets denselben Weg nutzen.
        backgrounds.apply_wallpaper(self._settings, pfad)
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

    # --- Sperrbildschirm (experimentell) ---
    # GNOME hat keinen Schlüssel für ein eigenes Sperrbild. Wir schreiben es
    # über das aktive Shell-Design-CSS (#lockDialogGroup), siehe
    # core/lockscreen.py. Das geht nur mit einem eigenen, beschreibbaren
    # Shell-Design und wirkt erst nach erneutem Anmelden.

    def _sperr_bereich(self):
        """Vorschau und Knöpfe, oder ein Hinweis, falls kein eigenes
        Shell-Design aktiv ist (dann lässt sich nichts hineinschreiben)."""
        self._sperr_aktiv = lockscreen.verfuegbar(self._settings)
        if not self._sperr_aktiv:
            hinweis = Gtk.Label(
                label="Dafür zuerst unter Shell-Design ein eigenes Design "
                      "(nicht das Standard-Design) wählen. In dessen Stil "
                      "schreibt die App das Sperrbild.",
                xalign=0, wrap=True)
            hinweis.add_css_class("dim-label")
            return hinweis

        self._sperr_vorschau = Gtk.Picture()
        self._sperr_vorschau.set_content_fit(Gtk.ContentFit.COVER)
        self._sperr_vorschau.set_size_request(-1, 140)
        self._sperr_vorschau.add_css_class("card")

        self._sperr_platzhalter = Gtk.Label(label="Kein eigenes Bild gesetzt")
        self._sperr_platzhalter.add_css_class("dim-label")
        self._sperr_platzhalter.set_halign(Gtk.Align.CENTER)
        self._sperr_platzhalter.set_valign(Gtk.Align.CENTER)
        self._sperr_platzhalter.set_can_target(False)

        overlay = Gtk.Overlay()
        overlay.set_child(self._sperr_vorschau)
        overlay.add_overlay(self._sperr_platzhalter)

        eigenes = Gtk.Button(label="Eigenes Bild wählen …")
        eigenes.connect("clicked", self._on_sperr_eigenes)
        wie_hg = Gtk.Button(label="Wie Hintergrund")
        wie_hg.connect("clicked", self._on_sperr_wie_hintergrund)
        entfernen = Gtk.Button(label="Entfernen")
        entfernen.add_css_class("flat")
        entfernen.connect("clicked", self._on_sperr_entfernen)

        knoepfe = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        knoepfe.set_halign(Gtk.Align.START)
        knoepfe.append(eigenes)
        knoepfe.append(wie_hg)
        knoepfe.append(entfernen)

        hinweis = Gtk.Label(
            label="Experimentell. Wirkt erst nach erneutem Anmelden und kann "
                  "auf neueren GNOME-Versionen vom unscharfen Sperrbildschirm "
                  "überdeckt werden.",
            xalign=0, wrap=True)
        hinweis.add_css_class("dim-label")

        bereich = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        bereich.append(overlay)
        bereich.append(knoepfe)
        bereich.append(hinweis)
        return bereich

    def _zeige_sperr(self):
        if not self._sperr_aktiv:
            return
        pfad = lockscreen.aktuelles_bild(self._settings)
        if pfad and os.path.isfile(pfad):
            self._sperr_vorschau_setzen(pfad)
        else:
            self._sperr_platzhalter.set_visible(True)

    def _sperr_vorschau_setzen(self, pfad):
        self._sperr_platzhalter.set_visible(False)
        backgrounds.load_texture_async(
            pfad, 1400, 400, self._sperr_vorschau.set_paintable)

    def _sperr_setze_bild(self, quelle):
        """Legt das Bild dauerhaft ab und trägt es ins Shell-Design-CSS ein.
        Der Theme-Verweis ist ein Dateipfad, das Bild muss also bleiben."""
        ziel = self._kopiere_ins_backgrounds(quelle)
        if lockscreen.set_background(self._settings, ziel):
            self._sperr_vorschau_setzen(ziel)

    def _on_sperr_wie_hintergrund(self, _knopf):
        """Übernimmt das aktuelle Desktop-Hintergrundbild als Sperrbild."""
        pfad = self._aktueller_pfad()
        if pfad and os.path.isfile(pfad):
            self._sperr_setze_bild(pfad)

    def _on_sperr_entfernen(self, _knopf):
        lockscreen.clear_background(self._settings)
        self._sperr_vorschau.set_paintable(None)
        self._sperr_platzhalter.set_visible(True)

    def _on_sperr_eigenes(self, _knopf):
        dialog = Gtk.FileDialog()
        dialog.set_title("Sperrbildschirm-Bild wählen")

        bilder = Gtk.FileFilter()
        bilder.set_name("Bilder")
        bilder.add_mime_type("image/*")
        liste = Gio.ListStore.new(Gtk.FileFilter)
        liste.append(bilder)
        dialog.set_filters(liste)

        dialog.open(self.get_root(), None, self._on_sperr_gewaehlt)

    def _on_sperr_gewaehlt(self, dialog, ergebnis):
        try:
            datei = dialog.open_finish(ergebnis)
        except GLib.Error:
            return  # abgebrochen oder Fehler
        pfad = datei.get_path()
        if pfad:
            self._sperr_setze_bild(pfad)

    # --- Anmeldebildschirm (GDM, experimentell, braucht root) ---
    # Der Greeter-Hintergrund steckt in einer kompilierten gresource unter
    # /usr/share. Wir lassen ihn von einem Helfer-Skript über pkexec patchen
    # (siehe core/gdm.py). Reversibel über "Zurücksetzen".

    def _gdm_bereich(self):
        self._gdm_status = Gtk.Label(xalign=0, wrap=True)
        self._gdm_status.add_css_class("dim-label")

        # Erscheint nur, solange ein gesetztes Theme noch nicht durch einen
        # erfolgreichen Login bestätigt wurde.
        self._gdm_hinweis = Gtk.Label(xalign=0, wrap=True)
        self._gdm_hinweis.add_css_class("dim-label")

        self._gdm_knoepfe = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._gdm_knoepfe.set_halign(Gtk.Align.START)

        warnung = Gtk.Label(
            label="Ändert den systemweiten Anmeldebildschirm und braucht das "
                  "Administrator-Passwort. Wirkt erst beim nächsten An- und "
                  "Abmelden. Das Original wird nie überschrieben; bei einem "
                  "Problem stellt sich der Standard automatisch wieder her.",
            xalign=0, wrap=True)
        warnung.add_css_class("dim-label")

        bereich = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        bereich.append(self._gdm_status)
        bereich.append(self._gdm_hinweis)
        bereich.append(self._gdm_knoepfe)
        bereich.append(warnung)
        self._gdm_aktualisieren()
        return bereich

    def _gdm_knopf(self, label, handler, flach=False):
        knopf = Gtk.Button(label=label)
        if flach:
            knopf.add_css_class("flat")
        knopf.connect("clicked", handler)
        return knopf

    def _gdm_aktualisieren(self):
        """Setzt Status, Hinweis und die passenden Knöpfe je nach Zustand:
        Standard, gesetzt-aber-unbestätigt oder bestätigt aktiv."""
        kind = self._gdm_knoepfe.get_first_child()
        while kind is not None:
            self._gdm_knoepfe.remove(kind)
            kind = self._gdm_knoepfe.get_first_child()

        if gdm.bestaetigung_offen():
            self._gdm_status.set_label(
                "Neuer Anmeldebildschirm gesetzt, noch nicht bestätigt.")
            self._gdm_hinweis.set_label(
                "Melde dich einmal ab und wieder an. Erscheint der "
                "Anmeldebildschirm normal, klicke „Behalten“. Tust du das "
                "nicht, stellt sich beim übernächsten Start automatisch der "
                "Standard wieder her.")
            self._gdm_hinweis.set_visible(True)
            self._gdm_knoepfe.append(
                self._gdm_knopf("Behalten", self._on_gdm_confirm))
            self._gdm_knoepfe.append(
                self._gdm_knopf("Verwerfen", self._on_gdm_reset, flach=True))
            return

        self._gdm_hinweis.set_visible(False)
        if gdm.aktiv():
            self._gdm_status.set_label(
                "Eigener Anmeldebildschirm-Hintergrund ist aktiv.")
        else:
            self._gdm_status.set_label("Standard-Anmeldebildschirm.")
        self._gdm_knoepfe.append(
            self._gdm_knopf("Eigenes Bild wählen …", self._on_gdm_eigenes))
        self._gdm_knoepfe.append(
            self._gdm_knopf("Wie Hintergrund", self._on_gdm_wie_hintergrund))
        if gdm.aktiv():
            self._gdm_knoepfe.append(
                self._gdm_knopf("Zurücksetzen", self._on_gdm_reset, flach=True))

    def _on_gdm_confirm(self, _knopf):
        self._gdm_anwenden(gdm.confirm, "Wird bestätigt … ")

    def _on_gdm_eigenes(self, _knopf):
        dialog = Gtk.FileDialog()
        dialog.set_title("Anmeldebildschirm-Bild wählen")

        bilder = Gtk.FileFilter()
        bilder.set_name("Bilder")
        bilder.add_mime_type("image/*")
        liste = Gio.ListStore.new(Gtk.FileFilter)
        liste.append(bilder)
        dialog.set_filters(liste)

        dialog.open(self.get_root(), None, self._on_gdm_gewaehlt)

    def _on_gdm_gewaehlt(self, dialog, ergebnis):
        try:
            datei = dialog.open_finish(ergebnis)
        except GLib.Error:
            return
        pfad = datei.get_path()
        if pfad:
            self._gdm_anwenden(lambda: gdm.apply(pfad), "Wird gesetzt … ")

    def _on_gdm_wie_hintergrund(self, _knopf):
        pfad = self._aktueller_pfad()
        if pfad and os.path.isfile(pfad):
            self._gdm_anwenden(lambda: gdm.apply(pfad), "Wird gesetzt … ")

    def _on_gdm_reset(self, _knopf):
        self._gdm_anwenden(gdm.reset, "Wird zurückgesetzt … ")

    def _gdm_anwenden(self, aktion, meldung):
        """Führt eine GDM-Aktion (apply/reset) im Hintergrund aus. pkexec zeigt
        dabei seinen eigenen Passwort-Dialog, darum nicht im Main-Loop blockieren."""
        self._gdm_status.set_label(meldung + "(Passwort eingeben)")

        def arbeit():
            erfolg = aktion()
            GLib.idle_add(self._gdm_fertig, erfolg)

        threading.Thread(target=arbeit, daemon=True).start()

    def _gdm_fertig(self, erfolg):
        if erfolg:
            self._gdm_aktualisieren()
        else:
            self._gdm_status.set_label("Nicht geändert (abgebrochen oder Fehler).")
        return GLib.SOURCE_REMOVE

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
