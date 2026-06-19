"""Seite 'Hintergrund'.

Aufbau: Vorschau des aktuellen Bildes, eine Galerie der Standard-Hintergründe
(und der eigenen), ein Knopf zum Wählen eines eigenen Bildes und ein Dropdown
für den Anpassungsmodus (Zoom, gestreckt, ...).

Eine Auswahl wirkt sofort: das Bild wird als picture-uri (hell und dunkel)
gesetzt, der Modus über picture-options.
"""

import os
import re
import shutil
import threading

from gi.repository import Adw, Gio, GLib, Gtk

from src import compat
from src.core import backgrounds, gdm, lockscreen, variety
from src.i18n import _
from src.widgets.monitor_arrangement import MonitorArrangement
from src.widgets.wallpaper_card import WallpaperCard


# Zielordner für selbst gewählte Bilder.
BACKGROUND_DIR = os.path.expanduser("~/.local/share/backgrounds")

# Anpassungsmodus: Label und der dazugehörige Enum-Wert von picture-options.
MODI = [
    (_("Zoom (fill screen)"), "zoom"),
    (_("Fitted"), "scaled"),
    (_("Stretched"), "stretched"),
    (_("Centered"), "centered"),
    (_("Tiled"), "wallpaper"),
    (_("Across multiple screens"), "spanned"),
    (_("None"), "none"),
]


class BackgroundPage(compat.PageBase):
    """Navigationsseite zum Setzen des Hintergrundbilds und seines Modus."""

    def __init__(self, settings):
        super().__init__(title=_("Background"))
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

        # Bei mehreren Monitoren steht oben die Anordnung statt einer einzelnen
        # Vorschau; die Galerie weiter unten gilt dann für die hier gewählte
        # Auswahl ("all" oder ein bestimmter Monitor). Bei einem Monitor bleibt
        # alles wie gehabt (eine Vorschau, ein Bild für den Schirm).
        self._monitore = backgrounds.monitors()
        self._multi = len(self._monitore) >= 2
        self._auswahl = "all"
        self._modus_updating = False  # unterdrückt Dropdown-Signal beim Umstellen
        # Composite-Bauten serialisieren: schnelle Klicks dürfen nicht parallel
        # denselben a/b-Slot in dieselbe Datei schreiben.
        self._composite_busy = False
        self._composite_pending = False
        self._zuordnung = {
            k: list(v) for k, v in backgrounds.lade_zuordnung().items()}

        if self._multi:
            box.append(self._feld_titel(_("Displays")))
            self._arrangement = MonitorArrangement(
                self._monitore, self._on_auswahl,
                einzeln_erlaubt=not self._variety_aktiv)
            box.append(self._arrangement)
            self._arrangement.set_auswahl("all")
            self._arrangement.set_status(
                _("One background for all displays. Pick it from the gallery "
                  "below."))
            self._arrangement_thumbnails()
        else:
            box.append(self._feld_titel(_("Current image")))
            box.append(self._vorschau_bereich())
            self._zeige_aktuellen()

        box.append(self._galerie_aufbau())
        self._fuelle_galerie()

        box.append(self._feld_titel(_("Adjustment")))
        box.append(self._modus_dropdown())

        box.append(self._feld_titel(_("Lock screen")))
        box.append(self._sperr_bereich())
        self._zeige_sperr()

        # Anmeldebildschirm nur zeigen, wenn der root-Weg überhaupt möglich ist.
        if gdm.verfuegbar():
            box.append(self._feld_titel(_("Login screen (GDM)")))
            box.append(self._gdm_bereich())

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)

        toolbar = compat.toolbar_view(
            top_bars=[Adw.HeaderBar()], content=scroll)
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
            label=_("Variety manages the background. Your image choice is "
                    "handed to Variety, which normally keeps it across the "
                    "next login too. You can change the adjustment mode below, "
                    "but Variety may set its own image again. For full control "
                    "over image and mode you can remove Variety here."),
            xalign=0, wrap=True)
        self._variety_label.add_css_class("dim-label")

        self._variety_knopf = Gtk.Button(label=_("Remove Variety"))
        self._variety_knopf.set_halign(Gtk.Align.START)
        self._variety_knopf.set_tooltip_text(
            _("Remove Variety from autostart and quit it, so the app controls "
              "the background and mode directly. Reversible, Variety stays "
              "installed."))
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
            if self._multi:
                self._arrangement_thumbnails()
            else:
                self._vorschau_setzen(quelle)

        # Jetzt ist der Weg frei für eigene Bilder pro Monitor.
        if self._multi:
            self._arrangement.einzeln_freischalten()

        self._variety_label.set_label(
            _("Variety was removed from autostart and quit. The app now "
              "manages the background directly, your adjustment mode is kept. "
              "To undo: start Variety again and enable it in autostart."))
        self._variety_box.remove(self._variety_knopf)

    def _vorschau_bereich(self):
        """Vorschau-Bild mit einem Platzhalter-Hinweis, falls kein Bild gesetzt ist."""
        self._vorschau = Gtk.Picture()
        compat.set_cover(self._vorschau)
        self._vorschau.set_size_request(-1, 200)
        self._vorschau.add_css_class("card")

        self._platzhalter = Gtk.Label(label=_("No wallpaper set"))
        self._platzhalter.add_css_class("dim-label")
        self._platzhalter.set_halign(Gtk.Align.CENTER)
        self._platzhalter.set_valign(Gtk.Align.CENTER)
        self._platzhalter.set_can_target(False)  # Klicks gehen ans Bild dahinter

        overlay = Gtk.Overlay()
        overlay.set_child(self._vorschau)
        overlay.add_overlay(self._platzhalter)
        return overlay

    def _aktueller_pfad(self):
        """Dateipfad des aktuell gesetzten Hintergrunds, oder None.

        Über backgrounds.aktuelles_wallpaper, damit Varietys flüchtige
        Zwischendatei auf das echte Quellbild zurückgeführt wird und die Galerie
        das gewählte Bild als aktiv markiert."""
        return backgrounds.aktuelles_wallpaper(self._settings)

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

    def _galerie_aufbau(self):
        """Zwei ausklappbare Bereiche: Standard- und eigene Hintergründe. Der
        Knopf für ein eigenes Bild sitzt direkt im eigenen Bereich."""
        behaelter = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        self._galerie_system = self._neue_flowbox()
        self._exp_system = Gtk.Expander()
        self._exp_system.set_label_widget(self._feld_titel(_("Default backgrounds")))
        self._exp_system.set_expanded(True)
        self._exp_system.set_child(self._galerie_system)
        behaelter.append(self._exp_system)

        self._galerie_eigene = self._neue_flowbox()
        eigene_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        eigene_box.append(self._galerie_eigene)
        knopf = Gtk.Button(label=_("Choose your own image…"))
        knopf.set_halign(Gtk.Align.START)
        knopf.connect("clicked", self._on_eigenes)
        eigene_box.append(knopf)

        self._exp_eigene = Gtk.Expander()
        self._exp_eigene.set_label_widget(self._feld_titel(_("Your own backgrounds")))
        self._exp_eigene.set_expanded(True)
        self._exp_eigene.set_child(eigene_box)
        behaelter.append(self._exp_eigene)
        return behaelter

    def _neue_flowbox(self):
        fb = Gtk.FlowBox()
        fb.set_selection_mode(Gtk.SelectionMode.NONE)
        fb.set_max_children_per_line(6)
        fb.set_min_children_per_line(3)
        fb.set_column_spacing(8)
        fb.set_row_spacing(8)
        fb.set_homogeneous(True)
        fb.set_margin_top(8)
        fb.connect("child-activated", self._on_card_aktiviert)
        return fb

    def _fuelle_galerie(self):
        """Baut die Karten beider Bereiche neu auf und markiert das aktive Bild.

        System-Bilder sind fest, eigene Bilder bekommen einen Entfernen-Knopf.
        """
        compat.flowbox_clear(self._galerie_system)
        compat.flowbox_clear(self._galerie_eigene)
        self._cards = []
        aktuell = self._aktueller_pfad()

        def hinzufuegen(flowbox, pfad, entfernbar):
            aktiv = (aktuell is not None and os.path.realpath(pfad) == aktuell)
            karte = WallpaperCard(
                pfad, aktiv,
                entfernbar=entfernbar,
                on_entfernen=self._on_entfernen if entfernbar else None,
            )
            flowbox.append(karte)
            self._cards.append(karte)

        for pfad in backgrounds.list_system_wallpapers():
            hinzufuegen(self._galerie_system, pfad, False)
        for pfad in backgrounds.list_user_wallpapers():
            hinzufuegen(self._galerie_eigene, pfad, True)

    def _on_entfernen(self, pfad):
        # Nur in der App ausblenden, Datei bleibt erhalten.
        backgrounds.hide_wallpaper(pfad)
        self._fuelle_galerie()

    def _on_card_aktiviert(self, _flowbox, karte):
        # Die "aktiv"-Markierung der Galerie ist nur im Ein-Bild-Modus sinnvoll.
        # Im Pro-Monitor-Modus zeigt das Composite kein einzelnes Galerie-Bild,
        # die richtige Vorschau liefern die Monitor-Kacheln.
        if not (self._multi and self._auswahl != "all"):
            for andere in self._cards:
                andere.set_aktiv(andere is karte)
        self._setze_bild(karte.pfad)

    def _setze_bild(self, pfad):
        # Mehrmonitor mit gewähltem Einzelschirm: nur dessen Bild im Composite.
        # Sonst (ein Monitor, oder "alle"): klassisch für den ganzen Desktop,
        # variety-respektierend zentral über core/backgrounds.
        if self._multi and self._auswahl != "all":
            self._zuordnung.setdefault(self._auswahl, [pfad, "zoom"])[0] = pfad
            self._composite_anwenden()
            return
        backgrounds.apply_wallpaper(self._settings, pfad)
        if self._multi:
            # Von einem Composite (spanned) kommend ein einzelnes Bild auf allen
            # Schirmen: spanned würde es über beide strecken, also auf zoom zurück.
            if self._settings.picture_options() == "spanned":
                self._settings.set_picture_options("zoom")
                self._modus_updating = True
                self._setze_modus_auswahl("zoom")
                self._modus_updating = False
            self._arrangement_thumbnails()
        else:
            self._vorschau_setzen(pfad)

    def _on_eigenes(self, _knopf):
        bilder = Gtk.FileFilter()
        bilder.set_name(_("Images"))
        bilder.add_mime_type("image/*")
        compat.open_file(self.get_root(), _("Choose wallpaper"),
                         [bilder], self._on_gewaehlt)

    def _on_gewaehlt(self, pfad):
        if not pfad:
            return

        ziel = self._kopiere_ins_backgrounds(pfad)
        self._setze_bild(ziel)
        # Galerie neu aufbauen, damit das neue Bild auftaucht und aktiv ist.
        self._fuelle_galerie()

    def _kopiere_ins_backgrounds(self, quelle):
        os.makedirs(BACKGROUND_DIR, exist_ok=True)
        # CSS-empfindliche Zeichen aus dem Dateinamen nehmen: das Sperrbild landet
        # als Pfad in der Shell-CSS. lockscreen.py kodiert die URL ohnehin, das
        # hier ist die zweite Verteidigungslinie, damit auf der Platte gar kein
        # heikler Name entsteht.
        name = re.sub(r'["\\\n\r\x00-\x1f]', "_", os.path.basename(quelle)) or "bild"
        ziel = os.path.join(BACKGROUND_DIR, name)
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
                label=_("First choose a custom theme (not the default one) "
                        "under Shell Theme. The app writes the lock screen "
                        "image into that theme's style."),
                xalign=0, wrap=True)
            hinweis.add_css_class("dim-label")
            return hinweis

        self._sperr_vorschau = Gtk.Picture()
        compat.set_cover(self._sperr_vorschau)
        self._sperr_vorschau.set_size_request(-1, 140)
        self._sperr_vorschau.add_css_class("card")

        self._sperr_platzhalter = Gtk.Label(label=_("No custom image set"))
        self._sperr_platzhalter.add_css_class("dim-label")
        self._sperr_platzhalter.set_halign(Gtk.Align.CENTER)
        self._sperr_platzhalter.set_valign(Gtk.Align.CENTER)
        self._sperr_platzhalter.set_can_target(False)

        overlay = Gtk.Overlay()
        overlay.set_child(self._sperr_vorschau)
        overlay.add_overlay(self._sperr_platzhalter)

        eigenes = Gtk.Button(label=_("Choose your own image…"))
        eigenes.connect("clicked", self._on_sperr_eigenes)
        wie_hg = Gtk.Button(label=_("Same as background"))
        wie_hg.connect("clicked", self._on_sperr_wie_hintergrund)
        entfernen = Gtk.Button(label=_("Remove"))
        entfernen.add_css_class("flat")
        entfernen.connect("clicked", self._on_sperr_entfernen)

        knoepfe = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        knoepfe.set_halign(Gtk.Align.START)
        knoepfe.append(eigenes)
        knoepfe.append(wie_hg)
        knoepfe.append(entfernen)

        hinweis = Gtk.Label(
            label=_("Experimental. Takes effect only after logging in again "
                    "and may be covered by the blurred lock screen on newer "
                    "GNOME versions."),
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
        bilder = Gtk.FileFilter()
        bilder.set_name(_("Images"))
        bilder.add_mime_type("image/*")
        compat.open_file(self.get_root(), _("Choose lock screen image"),
                         [bilder], self._on_sperr_gewaehlt)

    def _on_sperr_gewaehlt(self, pfad):
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
            label=_("Changes the system-wide login screen and needs the "
                    "administrator password. Takes effect after a restart. "
                    "The original is never overwritten. If the login screen "
                    "shows a problem, the default restores itself after two "
                    "restarts; from a terminal any time with "
                    "\"sudo /usr/local/lib/design-manager/gdm-helper.sh "
                    "reset\"."),
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
                _("New login screen set, not yet confirmed."))
            self._gdm_hinweis.set_label(
                _("Restart the computer once. If the login screen appears "
                  "normally, log in and click \"Keep\". If you do not, the "
                  "default restores itself automatically after two restarts."))
            self._gdm_hinweis.set_visible(True)
            self._gdm_knoepfe.append(
                self._gdm_knopf(_("Keep"), self._on_gdm_confirm))
            self._gdm_knoepfe.append(
                self._gdm_knopf(_("Discard"), self._on_gdm_reset, flach=True))
            return

        self._gdm_hinweis.set_visible(False)
        if gdm.aktiv():
            self._gdm_status.set_label(
                _("A custom login screen background is active."))
        else:
            self._gdm_status.set_label(_("Default login screen."))
        self._gdm_knoepfe.append(
            self._gdm_knopf(_("Choose your own image…"), self._on_gdm_eigenes))
        self._gdm_knoepfe.append(
            self._gdm_knopf(_("Same as background"),
                            self._on_gdm_wie_hintergrund))
        if gdm.aktiv():
            self._gdm_knoepfe.append(
                self._gdm_knopf(_("Reset"), self._on_gdm_reset, flach=True))

    def _on_gdm_confirm(self, _knopf):
        self._gdm_anwenden(gdm.confirm, _("Confirming… "))

    def _on_gdm_eigenes(self, _knopf):
        bilder = Gtk.FileFilter()
        bilder.set_name(_("Images"))
        bilder.add_mime_type("image/*")
        compat.open_file(self.get_root(), _("Choose login screen image"),
                         [bilder], self._on_gdm_gewaehlt)

    def _on_gdm_gewaehlt(self, pfad):
        if pfad:
            self._gdm_anwenden(lambda: gdm.apply(pfad), _("Applying… "))

    def _on_gdm_wie_hintergrund(self, _knopf):
        pfad = self._aktueller_pfad()
        if pfad and os.path.isfile(pfad):
            self._gdm_anwenden(lambda: gdm.apply(pfad), _("Applying… "))

    def _on_gdm_reset(self, _knopf):
        self._gdm_anwenden(gdm.reset, _("Resetting… "))

    def _gdm_anwenden(self, aktion, meldung):
        """Führt eine GDM-Aktion (apply/reset) im Hintergrund aus. pkexec zeigt
        dabei seinen eigenen Passwort-Dialog, darum nicht im Main-Loop blockieren."""
        self._gdm_status.set_label(meldung + _("(enter password)"))

        def arbeit():
            erfolg = aktion()
            GLib.idle_add(self._gdm_fertig, erfolg)

        threading.Thread(target=arbeit, daemon=True).start()

    def _gdm_fertig(self, erfolg):
        if erfolg:
            self._gdm_aktualisieren()
        else:
            self._gdm_status.set_label(_("Not changed (canceled or error)."))
        return GLib.SOURCE_REMOVE

    def _modus_dropdown(self):
        labels = [label for label, _wert in MODI]
        self._modus_dd = Gtk.DropDown.new_from_strings(labels)
        self._modus_dd.set_hexpand(True)
        self._setze_modus_auswahl(self._settings.picture_options())
        self._modus_dd.connect("notify::selected", self._on_modus)
        return self._modus_dd

    def _setze_modus_auswahl(self, wert):
        for i, (_label, w) in enumerate(MODI):
            if w == wert:
                self._modus_dd.set_selected(i)
                return

    def _on_modus(self, dropdown, _param):
        if self._modus_updating:
            return
        index = dropdown.get_selected()
        if not (0 <= index < len(MODI)):
            return
        wert = MODI[index][1]
        if self._multi and self._auswahl != "all":
            # Modus für den gewählten Monitor im Composite. spanned/none ergeben
            # pro Monitor keinen Sinn, darum auf zoom zurückfallen.
            modus = wert if wert in backgrounds.PER_MONITOR_MODI else "zoom"
            eintrag = self._zuordnung.setdefault(self._auswahl, [None, modus])
            eintrag[1] = modus
            if eintrag[0]:
                self._composite_anwenden()
            return
        self._settings.set_picture_options(wert)

    # --- Mehrmonitor-Auswahl und Composite ---
    # Die Anordnung oben meldet die Auswahl ("all" oder ein connector). Die
    # Galerie und der Modus weiter unten wirken auf genau diese Auswahl.

    def _on_auswahl(self, auswahl):
        self._auswahl = auswahl
        self._arrangement.set_auswahl(auswahl)
        # Status und Galerie-Überschrift mitführen, damit klar ist, dass die
        # Galerie jetzt für die gewählte Sache gilt.
        if auswahl == "all":
            self._arrangement.set_status(
                _("One background for all displays. Pick it from the gallery "
                  "below."))
            wert = self._settings.picture_options()
        else:
            self._arrangement.set_status(
                _("Editing {name}. Pick its background from the gallery "
                  "below.").format(name=auswahl))
            wert = (self._zuordnung.get(auswahl) or [None, "zoom"])[1]
        self._modus_updating = True
        self._setze_modus_auswahl(wert)
        self._modus_updating = False

    def _arrangement_thumbnails(self):
        """Zeigt in jeder Kachel, was real auf dem Schirm liegt: im Composite-Fall
        (spanned) das je Monitor zugewiesene Bild, sonst überall das eine globale."""
        spanned = self._settings.picture_options() == "spanned"
        global_bild = None
        if not spanned:
            global_bild = backgrounds.aktuelles_wallpaper(self._settings)
        for m in self._monitore:
            conn = m["connector"]
            if spanned:
                eintrag = self._zuordnung.get(conn)
                bild = eintrag[0] if eintrag and eintrag[0] else None
            else:
                bild = global_bild
            self._arrangement.set_thumbnail(conn, bild)

    def _composite_anwenden(self):
        """Baut das Composite aus der aktuellen Zuordnung in einem Thread und
        setzt es danach im Main-Loop (kein Einfrieren bei großen Bildern).

        Serialisiert: läuft schon ein Bau, wird nur vorgemerkt und nach dessen
        Ende mit dem dann aktuellen Stand erneut gebaut. So greift kein zweiter
        Thread parallel denselben a/b-Slot."""
        if self._composite_busy:
            self._composite_pending = True
            return
        zuordnung = {c: (e[0], e[1]) for c, e in self._zuordnung.items() if e[0]}
        if not zuordnung:
            return
        self._composite_busy = True
        monitore = backgrounds.monitors()
        ziel = backgrounds.naechster_composite_pfad(self._settings)

        def arbeit():
            ok = backgrounds.build_composite(zuordnung, monitore, ziel)
            GLib.idle_add(self._composite_fertig, ok, ziel, zuordnung)

        threading.Thread(target=arbeit, daemon=True).start()

    def _composite_fertig(self, ok, ziel, zuordnung):
        self._composite_busy = False
        if ok:
            backgrounds.setze_composite(self._settings, ziel)
            backgrounds.speichere_zuordnung(zuordnung)
            self._arrangement_thumbnails()
        if self._composite_pending:
            self._composite_pending = False
            self._composite_anwenden()
        return GLib.SOURCE_REMOVE
