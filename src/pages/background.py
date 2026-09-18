"""Seite 'Hintergrund'.

Aufbau von oben nach unten, das Wichtigste zuerst:
- Vorschau: bei einem Monitor das aktuelle Bild, bei mehreren die Monitor-
  Anordnung mit Umschaltleiste (alle Bildschirme oder ein einzelner).
- Anpassung (Zoom, eingepasst, ...) direkt darunter, gilt für die Auswahl.
- Galerie mit zwei Reitern: eigene Bilder (mit Hinzufügen-Kachel) und die des
  Systems. Neue Bilder kommen auch per Drag & Drop ins Fenster dazu.
- Sperr- und Anmeldebildschirm eingeklappt ganz unten, beide experimentell.

Eine Auswahl wirkt sofort: das Bild wird als picture-uri (hell und dunkel)
gesetzt, der Modus über picture-options.
"""

import os
import threading

from gi.repository import Adw, Gio, GLib, Gtk

from src import compat
from src.core import backgrounds, gdm, lockscreen, variety
from src.i18n import _
from src.widgets.monitor_arrangement import MonitorArrangement
from src.widgets.wallpaper_card import HinzufuegenKachel, WallpaperCard


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


def _esc(text):
    """Adw-Zeilentitel sind Pango-Markup."""
    return GLib.markup_escape_text(text)


class BackgroundPage(compat.PageBase):
    """Navigationsseite zum Setzen des Hintergrundbilds und seines Modus."""

    def __init__(self, settings):
        super().__init__(title=_("Background"))
        self._settings = settings
        self._cards = []
        # Einmal prüfen, ob Variety läuft; steuert Hinweis und Einzelauswahl.
        self._variety_aktiv = variety.laeuft()

        # Bei mehreren Monitoren wirkt die Galerie auf die oben gewählte Sache
        # ("all" oder ein bestimmter Monitor).
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

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_margin_top(18)
        box.set_margin_bottom(24)
        box.set_margin_start(18)
        box.set_margin_end(18)

        if self._variety_aktiv:
            box.append(self._variety_banner())

        if self._multi:
            self._arrangement = MonitorArrangement(
                self._monitore, self._on_auswahl,
                einzeln_erlaubt=not self._variety_aktiv)
            box.append(self._arrangement)
            self._on_auswahl("all")
            self._arrangement_thumbnails()
        else:
            box.append(self._vorschau_bereich())
            self._zeige_aktuellen()

        box.append(self._modus_zeile())
        box.append(self._galerie())
        self._fuelle_galerie(reiter_waehlen=True)
        box.append(self._mehr_gruppe())

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)

        header = Adw.HeaderBar()
        hinzu = Gtk.Button(icon_name="list-add-symbolic")
        hinzu.set_tooltip_text(_("Add image…"))
        hinzu.connect("clicked", self._on_eigenes)
        header.pack_end(hinzu)

        self.set_child(compat.toolbar_view(top_bars=[header], content=scroll))

    # --- Bausteine ---

    def _feld_titel(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("feld-titel")
        return label

    def _melde(self, text):
        fenster = self.get_root()
        if fenster is not None and hasattr(fenster, "zeige_toast"):
            fenster.zeige_toast(text)

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
        self._variety_box.add_css_class("hinweis-karte")
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
            self._on_auswahl(self._auswahl)

        self._variety_label.set_label(
            _("Variety was removed from autostart and quit. The app now "
              "manages the background directly, your adjustment mode is kept. "
              "To undo: start Variety again and enable it in autostart."))
        self._variety_box.remove(self._variety_knopf)

    # --- Vorschau (ein Monitor) ---

    def _vorschau_bereich(self):
        """Vorschau im 16:9-Rahmen, mittig; Platzhalter, falls kein Bild gesetzt."""
        self._vorschau = Gtk.Picture()
        compat.set_cover(self._vorschau)
        self._vorschau.add_css_class("hintergrund-vorschau")

        self._platzhalter = Gtk.Label(label=_("No wallpaper set"))
        self._platzhalter.add_css_class("dim-label")
        self._platzhalter.set_can_target(False)

        overlay = Gtk.Overlay()
        overlay.set_child(self._vorschau)
        overlay.add_overlay(self._platzhalter)

        rahmen = Gtk.AspectFrame(xalign=0.5, yalign=0.5, ratio=16 / 9,
                                 obey_child=False)
        rahmen.set_size_request(-1, 240)
        rahmen.set_child(overlay)
        return rahmen

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
        backgrounds.load_texture_async(pfad, 960, 540, self._vorschau.set_paintable)

    # --- Anpassung ---

    def _modus_zeile(self):
        labels = [label for label, _wert in MODI]
        self._modus_dd = Gtk.DropDown.new_from_strings(labels)
        self._modus_dd.set_valign(Gtk.Align.CENTER)
        self._setze_modus_auswahl(
            self._modus_fuer(self._auswahl) if self._multi
            else self._settings.picture_options())
        self._modus_dd.connect("notify::selected", self._on_modus)

        titel = self._feld_titel(_("Adjustment"))
        titel.set_valign(Gtk.Align.CENTER)

        zeile = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        zeile.set_halign(Gtk.Align.CENTER)
        zeile.append(titel)
        zeile.append(self._modus_dd)
        return zeile

    def _modus_fuer(self, auswahl):
        if auswahl == "all":
            return self._settings.picture_options()
        return (self._zuordnung.get(auswahl) or [None, "zoom"])[1]

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

    # --- Galerie (eigene Bilder / System) ---

    def _galerie(self):
        self._galerie_eigene = self._neue_flowbox()
        self._galerie_system = self._neue_flowbox()

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.add_titled(self._galerie_eigene, "eigene", _("Your images"))
        self._stack.add_titled(self._galerie_system, "system", _("System"))
        # Nur die sichtbare Galerie bestimmt die Höhe, sonst bliebe unter den
        # wenigen eigenen Bildern die Lücke der langen System-Liste stehen.
        self._stack.set_vhomogeneous(False)

        umschalter = Gtk.StackSwitcher()
        umschalter.set_stack(self._stack)
        umschalter.set_halign(Gtk.Align.CENTER)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.append(umschalter)
        box.append(self._stack)
        return box

    def _neue_flowbox(self):
        fb = Gtk.FlowBox()
        fb.set_selection_mode(Gtk.SelectionMode.NONE)
        fb.set_max_children_per_line(5)
        fb.set_min_children_per_line(2)
        fb.set_column_spacing(10)
        fb.set_row_spacing(10)
        fb.set_homogeneous(True)
        fb.set_valign(Gtk.Align.START)
        fb.connect("child-activated", self._on_card_aktiviert)
        return fb

    def _fuelle_galerie(self, reiter_waehlen=False):
        """Baut beide Galerien neu auf und markiert das aktive Bild.

        System-Bilder sind fest, eigene Bilder bekommen einen Entfernen-Knopf.
        Beim ersten Aufbau wird der Reiter gewählt, in dem das aktive Bild liegt.
        """
        compat.flowbox_clear(self._galerie_system)
        compat.flowbox_clear(self._galerie_eigene)
        self._cards = []
        aktuell = self._aktueller_pfad()
        gefunden_in = None

        self._galerie_eigene.append(HinzufuegenKachel())
        eigene = backgrounds.list_user_wallpapers()
        system = backgrounds.list_system_wallpapers()
        for flowbox, liste, reiter in ((self._galerie_eigene, eigene, "eigene"),
                                       (self._galerie_system, system, "system")):
            for pfad in liste:
                aktiv = (aktuell is not None
                         and os.path.realpath(pfad) == aktuell)
                if aktiv:
                    gefunden_in = reiter
                entfernbar = reiter == "eigene"
                karte = WallpaperCard(
                    pfad, aktiv, entfernbar=entfernbar,
                    on_entfernen=self._on_entfernen if entfernbar else None)
                flowbox.append(karte)
                self._cards.append(karte)

        self._stack.get_page(self._galerie_eigene).set_title(
            _("Your images ({n})").format(n=len(eigene)))
        self._stack.get_page(self._galerie_system).set_title(
            _("System ({n})").format(n=len(system)))
        if reiter_waehlen:
            self._stack.set_visible_child_name(
                gefunden_in or ("eigene" if eigene else "system"))

    def _on_entfernen(self, pfad):
        # Nur in der App ausblenden, Datei bleibt erhalten.
        backgrounds.hide_wallpaper(pfad)
        self._fuelle_galerie()

    def _on_card_aktiviert(self, _flowbox, karte):
        if isinstance(karte, HinzufuegenKachel):
            self._on_eigenes(None)
            return
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

    def _bild_dialog(self, titel, on_pfad):
        bilder = Gtk.FileFilter()
        bilder.set_name(_("Images"))
        bilder.add_mime_type("image/*")
        compat.open_file(self.get_root(), titel, [bilder], on_pfad)

    def _uebernimm(self, pfad):
        """Kopiert ein Bild zu den eigenen; None (mit Meldung), wenn unlesbar."""
        try:
            return backgrounds.uebernehme_bild(pfad)
        except (ValueError, OSError):
            self._melde(_("The image could not be read."))
            return None

    def _on_eigenes(self, _knopf):
        self._bild_dialog(_("Choose wallpaper"), self._on_gewaehlt)

    def _on_gewaehlt(self, pfad):
        ziel = self._uebernimm(pfad) if pfad else None
        if ziel is None:
            return
        self._setze_bild(ziel)
        # Galerie neu aufbauen, damit das neue Bild auftaucht und aktiv ist.
        self._fuelle_galerie()
        self._stack.set_visible_child_name("eigene")

    # --- Mehrmonitor-Auswahl und Composite ---
    # Die Anordnung oben meldet die Auswahl ("all" oder ein connector). Die
    # Galerie und der Modus wirken auf genau diese Auswahl.

    def _on_auswahl(self, auswahl):
        self._auswahl = auswahl
        self._arrangement.set_auswahl(auswahl)
        if auswahl != "all":
            text = _("Editing {name}. Pick its background from the gallery "
                     "below.").format(name=auswahl)
        elif self._variety_aktiv:
            text = _("You have multiple monitors. To give each its own "
                     "image, remove Variety first (button above).")
        else:
            text = _("One background for all displays. Choose a display "
                     "above to give it its own image.")
        self._arrangement.set_status(text)
        if hasattr(self, "_modus_dd"):
            self._modus_updating = True
            self._setze_modus_auswahl(self._modus_fuer(auswahl))
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

    # --- Sperr- und Anmeldebildschirm (eingeklappt) ---

    def _mehr_gruppe(self):
        gruppe = Adw.PreferencesGroup(title=_("Lock and login screen"))
        gruppe.add(self._sperr_zeile())
        # Anmeldebildschirm nur zeigen, wenn der root-Weg überhaupt möglich ist.
        if gdm.verfuegbar():
            gruppe.add(self._gdm_zeile())
        return gruppe

    def _knopf(self, label, handler, flach=False):
        knopf = Gtk.Button(label=label)
        knopf.set_valign(Gtk.Align.CENTER)
        if flach:
            knopf.add_css_class("flat")
        knopf.connect("clicked", handler)
        return knopf

    # Sperrbildschirm (experimentell). GNOME hat keinen Schlüssel für ein
    # eigenes Sperrbild. Wir schreiben es über das aktive Shell-Design-CSS
    # (#lockDialogGroup), siehe core/lockscreen.py. Das geht nur mit einem
    # eigenen, beschreibbaren Shell-Design und wirkt erst nach erneutem Anmelden.

    def _sperr_zeile(self):
        self._sperr_aktiv = lockscreen.verfuegbar(self._settings)
        if not self._sperr_aktiv:
            zeile = Adw.ActionRow(
                title=_("Lock screen"),
                subtitle=_esc(_("First choose a custom theme (not the default "
                                "one) under Shell Theme. The app writes the "
                                "lock screen image into that theme's style.")))
            zeile.set_subtitle_lines(3)
            return zeile

        expander = Adw.ExpanderRow(
            title=_("Lock screen"),
            subtitle=_esc(_("Experimental. Takes effect only after logging in "
                            "again and may be covered by the blurred lock "
                            "screen on newer GNOME versions.")))

        self._sperr_vorschau = Gtk.Picture()
        compat.set_cover(self._sperr_vorschau)
        self._sperr_vorschau.set_size_request(96, 54)
        self._sperr_vorschau.set_valign(Gtk.Align.CENTER)
        self._sperr_vorschau.add_css_class("wallpaper-thumb")

        self._sperr_status = Adw.ActionRow()
        self._sperr_status.add_prefix(self._sperr_vorschau)
        self._sperr_status.add_suffix(
            self._knopf(_("Same as background"), self._on_sperr_wie_hintergrund))
        self._sperr_status.add_suffix(
            self._knopf(_("Choose…"), self._on_sperr_eigenes))
        self._sperr_entfernen = Gtk.Button(icon_name="user-trash-symbolic")
        self._sperr_entfernen.add_css_class("flat")
        self._sperr_entfernen.set_valign(Gtk.Align.CENTER)
        self._sperr_entfernen.set_tooltip_text(_("Remove"))
        self._sperr_entfernen.connect("clicked", self._on_sperr_entfernen)
        self._sperr_status.add_suffix(self._sperr_entfernen)
        expander.add_row(self._sperr_status)

        pfad = lockscreen.aktuelles_bild(self._settings)
        self._sperr_zeigen(pfad if pfad and os.path.isfile(pfad) else None)
        return expander

    def _sperr_zeigen(self, pfad):
        if pfad:
            self._sperr_status.set_title(_("Custom image set"))
            backgrounds.load_texture_async(
                pfad, 192, 108, self._sperr_vorschau.set_paintable)
        else:
            self._sperr_status.set_title(_("No custom image set"))
            self._sperr_vorschau.set_paintable(None)
        self._sperr_entfernen.set_visible(bool(pfad))

    def _sperr_setze_bild(self, quelle):
        """Legt das Bild dauerhaft ab und trägt es ins Shell-Design-CSS ein.
        Der Theme-Verweis ist ein Dateipfad, das Bild muss also bleiben."""
        ziel = self._uebernimm(quelle)
        if ziel and lockscreen.set_background(self._settings, ziel):
            self._sperr_zeigen(ziel)

    def _on_sperr_wie_hintergrund(self, _knopf):
        pfad = self._aktueller_pfad()
        if pfad and os.path.isfile(pfad):
            self._sperr_setze_bild(pfad)

    def _on_sperr_entfernen(self, _knopf):
        lockscreen.clear_background(self._settings)
        self._sperr_zeigen(None)

    def _on_sperr_eigenes(self, _knopf):
        self._bild_dialog(_("Choose lock screen image"),
                          lambda pfad: pfad and self._sperr_setze_bild(pfad))

    # Anmeldebildschirm (GDM, experimentell, braucht root). Der Greeter-
    # Hintergrund steckt in einer kompilierten gresource unter /usr/share. Ein
    # Helfer-Skript setzt ihn über pkexec (siehe core/gdm.py). Reversibel.

    def _gdm_zeile(self):
        self._gdm_expander = Adw.ExpanderRow(title=_("Login screen (GDM)"))

        self._gdm_aktion = Adw.ActionRow()
        self._gdm_aktion.set_title_lines(0)
        self._gdm_knoepfe = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._gdm_aktion.add_suffix(self._gdm_knoepfe)
        self._gdm_expander.add_row(self._gdm_aktion)

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
        warnung.set_margin_top(10)
        warnung.set_margin_bottom(10)
        warnung.set_margin_start(12)
        warnung.set_margin_end(12)
        self._gdm_expander.add_row(warnung)

        self._gdm_aktualisieren()
        return self._gdm_expander

    def _gdm_status(self, text):
        self._gdm_expander.set_subtitle(_esc(text))

    def _gdm_aktualisieren(self):
        """Setzt Status, Hinweis und die passenden Knöpfe je nach Zustand:
        Standard, gesetzt-aber-unbestätigt oder bestätigt aktiv."""
        kind = self._gdm_knoepfe.get_first_child()
        while kind is not None:
            self._gdm_knoepfe.remove(kind)
            kind = self._gdm_knoepfe.get_first_child()

        if gdm.bestaetigung_offen():
            self._gdm_status(_("New login screen set, not yet confirmed."))
            self._gdm_expander.set_expanded(True)
            self._gdm_aktion.set_title(_esc(
                _("Restart the computer once. If the login screen appears "
                  "normally, log in and click \"Keep\". If you do not, the "
                  "default restores itself automatically after two restarts.")))
            self._gdm_knoepfe.append(self._knopf(_("Keep"), self._on_gdm_confirm))
            self._gdm_knoepfe.append(
                self._knopf(_("Discard"), self._on_gdm_reset, flach=True))
            return

        self._gdm_aktion.set_title("")
        if gdm.aktiv():
            self._gdm_status(_("A custom login screen background is active."))
        else:
            self._gdm_status(_("Default login screen."))
        self._gdm_knoepfe.append(
            self._knopf(_("Same as background"), self._on_gdm_wie_hintergrund))
        self._gdm_knoepfe.append(self._knopf(_("Choose…"), self._on_gdm_eigenes))
        if gdm.aktiv():
            self._gdm_knoepfe.append(
                self._knopf(_("Reset"), self._on_gdm_reset, flach=True))

    def _on_gdm_confirm(self, _knopf):
        self._gdm_anwenden(gdm.confirm, _("Confirming… "))

    def _on_gdm_eigenes(self, _knopf):
        self._bild_dialog(_("Choose login screen image"), self._on_gdm_gewaehlt)

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
        self._gdm_status(meldung + _("(enter password)"))

        def arbeit():
            erfolg = aktion()
            GLib.idle_add(self._gdm_fertig, erfolg)

        threading.Thread(target=arbeit, daemon=True).start()

    def _gdm_fertig(self, erfolg):
        if erfolg:
            self._gdm_aktualisieren()
        else:
            self._gdm_status(_("Not changed (canceled or error)."))
        return GLib.SOURCE_REMOVE
