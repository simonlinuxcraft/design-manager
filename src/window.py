"""Hauptfenster der App.

Nutzt Adw.NavigationSplitView: links eine Seitenleiste mit Logo und den sechs
Bereichen, rechts der Inhalt des gewählten Bereichs. Die Liste self._bereiche
beschreibt die Einträge; ein None-Eintrag wird zur Trennlinie. Jede klickbare
Zeile merkt sich ihre Seiten-Erzeuger-Funktion direkt am Objekt
(zeile.erzeuge_seite), damit Trennzeilen die Zuordnung nicht verschieben.
"""

import os
import threading

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from src import compat
from src.i18n import _, ngettext
from src.logo import logo_texture
from src.core import (gdm, gnomelook, healthcheck, installer, lockscreen,
                      looksbundle, onboarding, restorepoint, schedule,
                      theme_check, updater)
from src.core.settings import AppSettings
from src.pages.background import BackgroundPage
from src.pages.backup import BackupPage
from src.pages.cursor import CursorPage
from src.pages.dock import DockPage
from src.pages.extensions import ExtensionsPage
from src.pages.fonts import FontsPage
from src.pages.gtk_theme import GtkThemePage
from src.pages.icons import IconsPage
from src.pages.looks import LooksPage
from src.pages.overview import OverviewPage
from src.pages.shell import ShellPage
from src.pages.system import SystemPage
from src.widgets.paket_auswahl import AuswahlDialog
from src.widgets.welcome import WelcomeDialog


APP_VERSION = "0.1.1"


class MainWindow(Adw.ApplicationWindow):
    """Das Hauptfenster mit zweispaltigem Navigations-Layout."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.set_title("Design Manager")
        self.set_default_size(1280, 840)

        # CSS-Klasse, über die unser Stylesheet (Chrom-Silber) greift.
        self.add_css_class("silber")

        # Eine gemeinsame Settings-Instanz für alle Seiten.
        self._settings = AppSettings()

        # Aktionen für das Hauptmenü (Über, Beenden) registrieren.
        self._setup_actions()

        # Die Bereiche der Seitenleiste. Pro Eintrag: ein stabiler Schlüssel
        # (für Sprünge aus der Übersicht), Titel (Pango-Markup, daher "&amp;"),
        # Icon-Name und eine Funktion, die die Seite baut.
        self._bereiche = [
            ("overview", _("Overview"), "view-grid-symbolic",
             lambda: OverviewPage(self._settings, self._springe_zu)),
            ("looks", _("Looks"), "starred-symbolic",
             lambda: LooksPage(self._settings)),
            ("background", _("Background"), "image-x-generic-symbolic",
             lambda: BackgroundPage(self._settings)),
            ("gtk", _("GTK Theme"), "preferences-desktop-appearance-symbolic",
             lambda: GtkThemePage(self._settings)),
            ("icons", _("Icons"), "applications-graphics-symbolic",
             lambda: IconsPage(self._settings)),
            ("cursor", _("Cursor"), "input-mouse-symbolic",
             lambda: CursorPage(self._settings)),
            ("fonts", _("Fonts"), "font-x-generic-symbolic",
             lambda: FontsPage(self._settings)),
            ("shell", _("Shell Theme"), "video-display-symbolic",
             lambda: ShellPage(self._settings)),
            ("dock", _("Dock"), "view-app-grid-symbolic",
             lambda: DockPage(self._settings)),
            ("extensions", _("Extensions"), "application-x-addon-symbolic",
             lambda: ExtensionsPage(self._settings)),
            ("system", _("System"), "applications-system-symbolic",
             lambda: SystemPage(self._settings)),
            ("backup", _("Backup"), "document-save-symbolic",
             lambda: BackupPage(self._settings)),
        ]
        # Schlüssel -> Listenposition, für Sprünge aus der Übersicht.
        self._index_nach_key = {
            eintrag[0]: i for i, eintrag in enumerate(self._bereiche)}

        self._split = compat.make_split()
        # Seitenleiste auf feste Breite nageln (min == max), sonst ziehen breite
        # Inhalte wie die Karten der Mauszeiger-Seite sie schmaler als anderswo.
        self._split.set_min_sidebar_width(270)
        self._split.set_max_sidebar_width(270)
        self._split.set_sidebar(self._build_sidebar())

        # Toast-Overlay um den ganzen Inhalt, damit Meldungen (z.B. nach einer
        # Installation) über jeder Seite erscheinen können.
        self._toasts = Adw.ToastOverlay()
        self._toasts.set_child(self._split)
        self._toasts.set_vexpand(True)

        # Fensterweites Banner über dem Inhalt, anfangs eingeklappt. Der
        # Health-Check (siehe core/healthcheck.py) blendet es nach dem Start ein,
        # wenn ein gesetztes Design auf der Platte fehlt und GNOME still auf
        # Adwaita zurückgefallen ist.
        self._banner = compat.Banner()
        self._banner.set_revealed(False)
        self._banner.connect("button-clicked", self._on_banner_korrektur)
        self._banner_probleme = []
        self._banner_modus = None  # None | "reload" (Reload-Modul-Risiko)

        wurzel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wurzel.append(self._banner)
        wurzel.append(self._toasts)
        self.set_content(self._drop_flaeche(wurzel))
        self._installiert_gerade = False

        # Startauswahl: erste echte Zeile, löst row-selected aus.
        self._listbox.select_row(self._erste_zeile)

        # Beim allerersten Start die Einführung zeigen. Über idle_add, damit das
        # Fenster vorher sichtbar ist (der Dialog braucht ein präsentiertes
        # Eltern-Fenster).
        if onboarding.ist_erster_start():
            GLib.idle_add(self._zeige_willkommen)

        # Nach dem ersten Frame prüfen, ob ein gesetztes Design fehlt (still auf
        # Adwaita zurückgefallen). idle_add, damit das Fenster zuerst erscheint.
        GLib.idle_add(self._pruefe_gesundheit)

        # Reste der früher vorhandenen Tag/Nacht-Automatik einmalig abräumen
        # (verwaiste systemd-User-Timer). Idempotent und billig, wenn nichts da
        # ist. Verzögert, um den Start nicht zu blockieren.
        GLib.idle_add(schedule.entferne_alte_automatik)

        # Verzögert und im Hintergrund nach einer neueren Version sehen.
        if updater.UPDATER_AKTIV and updater.werkzeuge_da():
            GLib.timeout_add_seconds(3, self._auto_update_check)

        # Nur wer schon von gnome-look installiert hat, fragt dort nach.
        if gnomelook.hat_quellen():
            GLib.timeout_add_seconds(8, self._pruefe_theme_updates, False)

    def _zeige_willkommen(self):
        compat.dialog_present(WelcomeDialog(), self)
        onboarding.als_gesehen_markieren()
        return GLib.SOURCE_REMOVE

    def _pruefe_gesundheit(self):
        """Blendet ein Banner ein. Das gefährlichere Reload-Modul-Risiko hat
        Vorrang (kann die ganze Sitzung lahmlegen), sonst fehlende Designs."""
        if healthcheck.reload_module_gesetzt():
            self._banner_modus = "reload"
            self._banner.set_title(
                _("A leftover KDE theme-reload module is active. On GNOME it can "
                  "freeze the whole session on a theme change. The app can "
                  "remove it safely (a backup is kept)."))
            self._banner.set_button_label(_("Remove it"))
            self._banner.set_revealed(True)
            return GLib.SOURCE_REMOVE

        self._banner_modus = None
        self._banner_probleme = healthcheck.pruefe(self._settings)
        if not self._banner_probleme:
            return GLib.SOURCE_REMOVE
        labels = ", ".join(label for label, _meth in self._banner_probleme)
        self._banner.set_title(
            _("Not found: {names}. GNOME falls back to Adwaita.").format(
                names=labels))
        self._banner.set_button_label(_("Set default"))
        self._banner.set_revealed(True)
        return GLib.SOURCE_REMOVE

    def _on_banner_korrektur(self, _banner):
        """Behebt das gemeldete Problem: Reload-Modul entfernen oder die
        Design-Lücken über die reset_*-Methoden schließen."""
        if self._banner_modus == "reload":
            if healthcheck.entferne_reload_module():
                self._banner_modus = None
                self._banner.set_revealed(False)
                self.zeige_toast(
                    _("Removed the theme-reload module. Fully effective after "
                      "the next login."))
            else:
                # Schreiben fehlgeschlagen: Banner offen lassen, damit der Nutzer
                # es erneut versuchen kann, statt fälschlich Erfolg zu melden.
                self.zeige_toast(_("Could not remove the module."))
            return
        for _label, methode in self._banner_probleme:
            getattr(self._settings, methode)()
        self._banner_probleme = []
        self._banner.set_revealed(False)
        self.zeige_toast(_("Reset to a safe default theme."))
        self._reload_aktive_seite()

    # --- Installieren per Drag & Drop (überall im Fenster) ---

    def _drop_flaeche(self, inhalt):
        """Das ganze Fenster nimmt Dateien an. Beim Drüberziehen erscheint ein
        silberner Rahmen mit Hinweis (rein per CSS über :drop(active))."""
        hinweis = Gtk.Label(
            label=_("Drop to install themes, icons, cursors, fonts, "
                    "wallpapers or extensions"))
        hinweis.add_css_class("drop-hinweis")
        hinweis.set_halign(Gtk.Align.CENTER)
        hinweis.set_valign(Gtk.Align.END)
        hinweis.set_margin_bottom(32)
        hinweis.set_can_target(False)

        overlay = Gtk.Overlay()
        overlay.add_css_class("install-ziel")
        overlay.set_child(inhalt)
        overlay.add_overlay(hinweis)

        ziel = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        ziel.connect("drop", lambda _z, wert, _x, _y: self.installiere_dateien(
            wert.get_files()))
        overlay.add_controller(ziel)
        return overlay

    def installiere_dateien(self, dateien):
        """Gio.Files aus einem Drop oder Dateidialog installieren."""
        links = [d.get_uri() for d in dateien
                 if d.get_uri_scheme() in ("http", "https")]
        if links:
            ids = [i for i in map(gnomelook.content_id, links) if i]
            if not ids:
                self.zeige_toast(_("Only local files and gnome-look.org links "
                                   "can be installed."))
                return False
            self._von_gnomelook(ids[0])
            return True
        pfade = [d.get_path() for d in dateien]
        if not pfade:
            return False
        if None in pfade:
            self.zeige_toast(_("Only local files can be installed. Download "
                               "the file first."))
            return False
        looks = [p for p in pfade if p.lower().endswith(".dmlook")]
        if looks:
            self._frage_look_import(looks[0])
        rest = [p for p in pfade if p not in looks]
        if rest:
            self.installiere(rest)
        return True

    def installiere(self, pfade):
        """Installiert im Hintergrund und meldet das Ergebnis.

        Zwei Phasen: erst analysieren (entpacken, erkennen), dann installieren.
        Dazwischen fragt ein Dialog bei All-in-one-Paketen mit vielen Varianten,
        welche gewünscht sind. Danach werden alle Seiten neu gebaut: was
        installiert wurde, kann zu jeder Seite gehören.
        """
        self._analysiere([(os.path.basename(p.rstrip(os.sep)),
                           lambda p=p: installer.analysiere(p)) for p in pfade])

    def _analysiere(self, auftraege):
        """auftraege: (name, funktion, die ein installer.Paket liefert)."""
        if self._installiert_gerade:
            self.zeige_toast(_("An installation is already running."))
            return
        self._installiert_gerade = True
        laeuft = Adw.Toast(title=_("Installing…"), timeout=0)
        self._toasts.add_toast(laeuft)

        def worker():
            pakete, fehler = [], []
            for name, analysiere in auftraege:
                try:
                    pakete.append((name, analysiere()))
                except installer.InstallFehler as e:
                    fehler.append("{name}: {grund}".format(name=name, grund=e))
                except Exception:
                    fehler.append("{name}: {grund}".format(
                        name=name,
                        grund=_("Installation failed unexpectedly.")))
            GLib.idle_add(self._frage_auswahl, laeuft, pakete, [], fehler)

        threading.Thread(target=worker, daemon=True).start()

    def _frage_auswahl(self, laeuft, offen, fertig, fehler):
        """Geht die analysierten Pakete durch; große bekommen den Dialog.

        fertig sammelt (name, paket, auswahl); auswahl None = alles.
        """
        while offen:
            name, paket = offen.pop(0)
            if paket.vorauswahl:
                fertig.append((name, paket, paket.vorauswahl))
                continue
            if len(paket.auswaehlbar()) <= installer.AUSWAHL_AB:
                fertig.append((name, paket, None))
                continue
            laeuft.dismiss()

            def gewaehlt(auswahl, name=name, paket=paket):
                if auswahl:
                    fertig.append((name, paket, auswahl))
                else:
                    gnomelook.merke(paket, [])  # Update abgebrochen
                    paket.aufraeumen()
                neu = Adw.Toast(title=_("Installing…"), timeout=0)
                if offen or fertig:
                    self._toasts.add_toast(neu)
                self._frage_auswahl(neu, offen, fertig, fehler)

            funde = paket.auswaehlbar()
            compat.dialog_present(AuswahlDialog(
                _("Choose what to install"),
                ngettext("{file} contains {n} theme. Choose what you want.",
                         "{file} contains {n} themes. Choose what you want.",
                         len(funde)).format(file=name, n=len(funde)),
                [(f, f.name, f.beschreibung()) for f in funde],
                _("Install ({n})"), _("Install"), gewaehlt), self)
            return GLib.SOURCE_REMOVE
        self._installiere_pakete(laeuft, fertig, fehler)
        return GLib.SOURCE_REMOVE

    def _installiere_pakete(self, laeuft, fertig, fehler):
        aktiv = self._settings.gtk_theme()

        def worker():
            ergebnis = []
            for name, paket, auswahl in fertig:
                try:
                    wahl = paket.funde if auswahl is None else auswahl
                    # Ein neues aktives GTK-Theme mit Web-CSS würde nach dem
                    # nächsten Anmelden jede App bremsen (Cyber-Dusk-Fall).
                    riskant = [f for f in wahl if f.art == "theme"
                               and f.name == aktiv and "gtk" in f.arten
                               and theme_check.fremdes_css(f.quelle)]
                    for f in riskant:
                        grund = _("The new version uses CSS that GTK does not "
                                  "understand. The active theme was left "
                                  "unchanged.")
                        fehler.append("{name}: {grund}".format(
                            name=f.name, grund=grund))
                        gnomelook.setze(installer.ziel_pfade(f),
                                        gnomelook.PROBLEM, grund)
                    wahl = [f for f in wahl if f not in riskant]
                    if wahl:
                        ergebnis += paket.installiere(wahl)
                    gnomelook.merke(paket, wahl)
                except installer.InstallFehler as e:
                    fehler.append("{name}: {grund}".format(name=name, grund=e))
                    gnomelook.fehlgeschlagen(paket, str(e))
                except Exception:
                    # Kopierphase (Platte voll, schreibgeschützte Reste) wirft
                    # rohes OSError/shutil.Error; nie still sterben lassen.
                    grund = _("Installation failed unexpectedly.")
                    fehler.append("{name}: {grund}".format(
                        name=name, grund=grund))
                    gnomelook.fehlgeschlagen(paket, grund)
                finally:
                    paket.aufraeumen()
            GLib.idle_add(self._installation_fertig, laeuft, ergebnis, fehler)

        threading.Thread(target=worker, daemon=True).start()

    def _installation_fertig(self, laeuft, ergebnis, fehler):
        self._installiert_gerade = False
        laeuft.dismiss()
        if ergebnis:
            gezeigt = ", ".join(ergebnis[:3])
            if len(ergebnis) > 3:
                gezeigt += " " + ngettext("and {n} more", "and {n} more",
                                          len(ergebnis) - 3).format(
                                              n=len(ergebnis) - 3)
            self.melde_und_reload(_("Installed: {items}").format(items=gezeigt))
        if fehler:
            compat.alert(
                self,
                _("Could not install"),
                "\n\n".join(fehler),
                [("ok", _("OK"), "")], default="ok", close="ok")
        return GLib.SOURCE_REMOVE

    def _frage_look_import(self, pfad):
        compat.alert(
            self,
            _("Apply look package?"),
            _('"{name}" installs its themes and applies the whole look. A '
              "restore point is created first.").format(
                  name=os.path.basename(pfad)),
            [("abbrechen", _("Cancel"), ""),
             ("anwenden", _("Apply"), "suggested")],
            default="anwenden", close="abbrechen",
            on_response=lambda antwort: (
                self.importiere_look(pfad) if antwort == "anwenden" else None))

    def importiere_look(self, pfad):
        """.dmlook im Hintergrund entpacken, danach im Hauptthread anwenden."""
        if self._installiert_gerade:
            self.zeige_toast(_("An installation is already running."))
            return
        self._installiert_gerade = True
        laeuft = Adw.Toast(title=_("Installing…"), timeout=0)
        self._toasts.add_toast(laeuft)

        def worker():
            try:
                ergebnis, fehler = looksbundle.entpacke(pfad), None
            except installer.InstallFehler as e:
                ergebnis, fehler = None, str(e)
            except Exception:
                ergebnis, fehler = None, _("The look package could not be read.")
            GLib.idle_add(self._look_fertig, laeuft, ergebnis, fehler)

        threading.Thread(target=worker, daemon=True).start()

    def _look_fertig(self, laeuft, ergebnis, fehler):
        self._installiert_gerade = False
        laeuft.dismiss()
        if fehler:
            self.zeige_toast(fehler)
        elif ergebnis is None:
            self.zeige_toast(_("That is not a valid look package."))
        else:
            looksbundle.wende_an(self._settings, *ergebnis)
            self.melde_und_reload(_("Look package applied."))
        return GLib.SOURCE_REMOVE

    def zeige_toast(self, text):
        """Zeigt eine kurze Meldung über dem aktuellen Inhalt.

        Die Seiten nutzen das über get_root() für Rückmeldungen (z.B. nach dem
        Entfernen eines Designs). Der Titel ist Pango-Markup, fremde Namen wie
        "Black & White" würden ihn sonst zerschießen.
        """
        self._toasts.add_toast(Adw.Toast(title=GLib.markup_escape_text(text)))

    def _reload_aktive_seite(self):
        """Baut die gerade gewählte Seite neu (verwirft ihren Cache)."""
        zeile = self._listbox.get_selected_row()
        if zeile is None:
            return
        erzeuge_seite = getattr(zeile, "erzeuge_seite", None)
        if erzeuge_seite is None:
            return
        zeile.seite = erzeuge_seite()
        self._split.set_content(zeile.seite)

    def reload_alle_seiten(self):
        """Verwirft den Cache ALLER Seiten und baut die aktive sofort neu.

        Ein Look- oder Profilwechsel betrifft mehrere Bereiche gleichzeitig
        (Design, Symbole, Mauszeiger, Hintergrund). Damit nicht nur die gerade
        sichtbare Seite stimmt und der Rest bis zum Neustart alte Werte zeigt,
        werfen wir alle zwischengespeicherten Seiten weg; jede wird beim nächsten
        Anwählen frisch gebaut.
        """
        i = 0
        while True:
            zeile = self._listbox.get_row_at_index(i)
            if zeile is None:
                break
            if hasattr(zeile, "seite"):
                zeile.seite = None
            i += 1
        self._reload_aktive_seite()

    def melde_und_reload(self, text):
        """Toast über dem Fenster zeigen und alle Seiten neu bauen.

        Der Toast hängt am fensterweiten Overlay, überlebt also den Neuaufbau
        der Seiten. Für Aktionen gedacht, die mehrere Bereiche auf einmal ändern
        (Look/Profil anwenden, Sicherung wiederherstellen, .dmlook importieren).

        Der Neuaufbau läuft über idle_add, nicht direkt: der Aufrufer steckt
        meist im Signal-Handler genau der Seite, die gleich ersetzt wird. Erst
        den Handler sauber zu Ende laufen lassen, dann die Seite austauschen.
        """
        self.zeige_toast(text)
        GLib.idle_add(self.reload_alle_seiten)

    def _build_sidebar(self):
        """Linke Spalte: flache Kopfleiste mit Marke, darunter die Liste."""
        header = Adw.HeaderBar()
        header.add_css_class("flat")  # kein eigener Hintergrund -> ein Block
        self._ohne_fenster_icon(header)
        header.pack_start(self._logo())
        header.pack_end(self._menue_knopf())
        header.set_title_widget(
            Adw.WindowTitle(title="Design Manager", subtitle="v" + APP_VERSION)
        )

        inhalt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        inhalt.append(self._caption(_("SETTINGS")))
        inhalt.append(self._bereich_liste())

        toolbar = compat.toolbar_view(top_bars=[header], content=inhalt)
        toolbar.add_css_class("sidebar-pane")  # ein durchgehender dunkler Ton
        return compat.PageBase(title="Design Manager", child=toolbar)

    def _ohne_fenster_icon(self, header):
        """Ein Knopf-Layout wie "icon:minimize,..." (KDE-Relikt) zeigt links das
        Fenster-Icon, hier direkt neben unserem Logo. Nur "icon" rausnehmen,
        die Knöpfe bleiben, auch wenn das Layout später geändert wird."""
        einstellungen = Gtk.Settings.get_default()

        def setzen(*_args):
            layout = einstellungen.props.gtk_decoration_layout or ""
            teile = [",".join(t for t in seite.split(",") if t != "icon")
                     for seite in layout.split(":")]
            header.set_decoration_layout(":".join(teile))

        setzen()
        einstellungen.connect("notify::gtk-decoration-layout", setzen)

    def _setup_actions(self):
        """Fenster-Aktionen für das Hauptmenü anlegen (win.about, win.quit)."""
        ueber = Gio.SimpleAction.new("about", None)
        ueber.connect("activate", self._on_ueber)
        self.add_action(ueber)

        beenden = Gio.SimpleAction.new("quit", None)
        beenden.connect("activate", lambda *_: self.close())
        self.add_action(beenden)

        safe = Gio.SimpleAction.new("safe-state", None)
        safe.connect("activate", self._on_safe_state)
        self.add_action(safe)

        aktualisieren = Gio.SimpleAction.new("check-updates", None)
        aktualisieren.connect("activate", self._on_check_updates)
        self.add_action(aktualisieren)

        theme_updates = Gio.SimpleAction.new("theme-updates", None)
        theme_updates.connect("activate", lambda *_: self._on_theme_updates())
        self.add_action(theme_updates)

    def _menue_knopf(self):
        """Hamburger-Menü rechts in der Kopfleiste."""
        menue = Gio.Menu()
        menue.append(_("Restore safe state"), "win.safe-state")
        menue.append(_("Check theme updates"), "win.theme-updates")
        if updater.UPDATER_AKTIV and updater.werkzeuge_da():
            menue.append(_("Check for updates"), "win.check-updates")
        menue.append(_("About Design Manager"), "win.about")
        menue.append(_("Quit"), "win.quit")

        knopf = Gtk.MenuButton()
        knopf.set_icon_name("open-menu-symbolic")
        knopf.set_menu_model(menue)
        knopf.set_tooltip_text(_("Main menu"))
        return knopf

    def _on_ueber(self, _action, _param):
        """Zeigt den Über-Dialog mit Version, Logo und Lizenz."""
        compat.show_about(
            self,
            application_name="Design Manager",
            application_icon="io.github.simonlinuxcraft.DesignManager",
            version=APP_VERSION,
            developer_name="simonlinuxcraft",
            comments=_("Customize the GNOME desktop appearance in one place: "
                       "background, themes, icons, cursor and fonts."),
            license_type=Gtk.License.GPL_3_0,
            copyright="© 2026 simonlinuxcraft",
        )

    def _on_safe_state(self, _action, _param):
        """Notausstieg: nach Sicherungspunkt alles auf sichere Standards setzen."""
        compat.alert(
            self,
            _("Restore safe state?"),
            _("First a restore point is created, then the theme, icons, cursor "
              "and shell theme are set to guaranteed working defaults "
              "(Adwaita). This helps when a theme has made the interface "
              "unusable."),
            [("abbrechen", _("Cancel"), ""),
             ("anwenden", _("Restore safe state"), "suggested")],
            default="abbrechen", close="abbrechen",
            on_response=self._on_safe_state_antwort)

    def _on_safe_state_antwort(self, antwort):
        if antwort != "anwenden":
            return
        restorepoint.erstelle(self._settings, _("before emergency reset"))
        # Die reset_*-Methoden setzen ausschließlich auf Adwaita bzw. den leeren
        # Shell-Wert, also auf garantiert vorhandene, gültige Designs. Eine
        # Whitelist-Prüfung erübrigt sich, weil die Ziele bekannt sicher sind.
        self._settings.reset_gtk_theme()
        self._settings.reset_icon_theme()
        self._settings.reset_cursor_theme()
        # Erst das Sperrbild aus der Shell-CSS nehmen, SOLANGE das alte Shell-
        # Design noch aktiv ist: clear_background findet seine gnome-shell.css
        # über das aktuell gesetzte Theme. Würde reset_shell_theme() zuerst
        # laufen, zeigte _css_pfad() ins Leere und der Sperrbild-Block bliebe
        # verwaist im alten Theme zurück (taucht bei Reaktivierung wieder auf).
        lockscreen.clear_background(self._settings)
        self._settings.reset_shell_theme()
        # Den GDM-Login-Hintergrund nur zurücksetzen, wenn überhaupt einer aktiv
        # ist. Das läuft über pkexec (Passwort-Dialog), darum nebenläufig, damit
        # die schon erledigten dconf-Resets nicht an einem Abbruch hängen.
        if gdm.aktiv() or gdm.bestaetigung_offen():
            threading.Thread(target=gdm.reset, daemon=True).start()
        self._banner.set_revealed(False)
        self.zeige_toast(_("Safe state restored (Adwaita)."))
        self._reload_aktive_seite()

    # --- gnome-look: Link installieren, Designs aktualisieren ---

    def frage_gnomelook_link(self):
        """Eingabefeld für die Adresse einer gnome-look-Seite. Liegt schon ein
        passender Link in der Zwischenablage, steht er gleich drin."""
        feld = Gtk.Entry(activates_default=True, hexpand=True,
                         placeholder_text="https://www.gnome-look.org/p/…")

        def zwischenablage(ablage, ergebnis):
            try:
                text = (ablage.read_text_finish(ergebnis) or "").strip()
            except GLib.Error:
                return
            if gnomelook.content_id(text) and not feld.get_text():
                feld.set_text(text)

        self.get_clipboard().read_text_async(None, zwischenablage)

        def antwort(rid):
            if rid != "installieren":
                return
            cid = gnomelook.content_id(feld.get_text().strip())
            if cid:
                self._von_gnomelook(cid)
            else:
                self.zeige_toast(_("That is not a link to a gnome-look.org "
                                   "page."))

        compat.alert(
            self, _("Install from gnome-look.org"),
            _("Open the theme page on gnome-look.org, copy the address from the "
              "address bar and paste it here. The app installs the theme and "
              "keeps it up to date."),
            [("abbrechen", _("Cancel"), ""),
             ("installieren", _("Install"), "suggested")],
            default="installieren", close="abbrechen", on_response=antwort,
            extra=feld)

    def _von_gnomelook(self, cid):
        self.zeige_toast(_("Looking up the gnome-look entry…"))

        def worker():
            try:
                titel, dateien = gnomelook.dateien(cid)
                GLib.idle_add(self._waehle_dateien,
                              [(cid, titel, dateien, None)], [])
            except installer.InstallFehler as e:
                GLib.idle_add(self.zeige_toast, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _waehle_dateien(self, offen, auftraege):
        """offen: (id, titel, dateien, eintrag). Bei mehreren Dateien fragen."""
        while offen:
            cid, titel, dateien, eintrag = offen.pop(0)
            if len(dateien) == 1:
                auftraege.append((cid, titel, dateien[0], eintrag))
                continue

            def gewaehlt(auswahl, cid=cid, titel=titel, eintrag=eintrag):
                auftraege.extend((cid, titel, d, eintrag) for d in auswahl or [])
                self._waehle_dateien(offen, auftraege)

            compat.dialog_present(AuswahlDialog(
                _("Choose files"),
                ngettext("{title} offers {n} file. Choose what you want.",
                         "{title} offers {n} files. Choose what you want.",
                         len(dateien)).format(title=titel, n=len(dateien)),
                [(d, d["name"], d["version"]) for d in dateien],
                _("Install ({n})"), _("Install"), gewaehlt), self)
            return GLib.SOURCE_REMOVE
        if auftraege:
            self._analysiere([
                (d["name"], lambda a=(cid, titel, d, e): gnomelook.analysiere(*a))
                for cid, titel, d, e in auftraege])
        return GLib.SOURCE_REMOVE

    def _on_theme_updates(self):
        if not gnomelook.hat_quellen():
            compat.alert(
                self, _("No themes from gnome-look.org yet"),
                _('Install a theme with the "From gnome-look.org…" button on '
                  "the theme pages. The app checks it for updates from then "
                  "on."),
                [("ok", _("OK"), "")], default="ok", close="ok")
            return
        self.zeige_toast(_("Checking theme updates…"))
        self._pruefe_theme_updates(True)

    def _pruefe_theme_updates(self, manuell):
        def worker():
            liste, netzfehler = gnomelook.updates()
            GLib.idle_add(self._theme_updates_da, liste, netzfehler, manuell)

        threading.Thread(target=worker, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _theme_updates_da(self, liste, netzfehler, manuell):
        if not liste:
            if manuell:
                self.zeige_toast(netzfehler or _(
                    "All themes from gnome-look.org are up to date."))
            return GLib.SOURCE_REMOVE
        if manuell:
            self._frage_theme_updates(liste)
            return GLib.SOURCE_REMOVE
        hinweis = Adw.Toast(title=ngettext(
            "Update available for {n} theme", "Updates available for {n} themes",
            len(liste)).format(n=len(liste)), button_label=_("Show"), timeout=0)
        hinweis.connect("button-clicked",
                        lambda _t: self._frage_theme_updates(liste))
        self._toasts.add_toast(hinweis)
        return GLib.SOURCE_REMOVE

    def _frage_theme_updates(self, liste):
        def gewaehlt(auswahl):
            if auswahl:
                self._waehle_dateien(
                    [(e["id"], e["titel"], neu, e) for e, neu in auswahl], [])

        compat.dialog_present(AuswahlDialog(
            _("Theme updates"),
            _("New versions are available on gnome-look.org. Themes in use "
              "change after the next login."),
            [((e, neu), e["titel"],
              ", ".join(sorted({os.path.basename(p) for p in e["pfade"]})))
             for e, neu in liste],
            _("Update ({n})"), _("Update"), gewaehlt, alle_an=True), self)

    # --- Updates (GitHub-Release) ---

    def _on_check_updates(self, _action, _param):
        self.zeige_toast(_("Checking for updates…"))
        self._update_thread(manuell=True)

    def _auto_update_check(self):
        self._update_thread(manuell=False)
        return GLib.SOURCE_REMOVE

    def _update_thread(self, manuell):
        """Fragt im Hintergrund nach der neuesten Version, meldet per idle_add."""
        def arbeit():
            info = updater.pruefe(APP_VERSION)
            GLib.idle_add(self._update_ergebnis, info, manuell)

        threading.Thread(target=arbeit, daemon=True).start()

    def _update_ergebnis(self, info, manuell):
        if info is None:
            if manuell:
                self.zeige_toast(_("You have the latest version."))
            return GLib.SOURCE_REMOVE
        compat.alert(
            self,
            _("Update available"),
            _("Version {new} is ready (installed: {cur}). Download and install "
              "it now? This asks for the administrator password once.").format(
                new=info["version"], cur=APP_VERSION),
            [("spaeter", _("Later"), ""),
             ("jetzt", _("Update"), "suggested")],
            default="jetzt", close="spaeter",
            on_response=lambda antwort: (
                self._starte_update(info) if antwort == "jetzt" else None))
        return GLib.SOURCE_REMOVE

    def _starte_update(self, info):
        self.zeige_toast(
            _("Downloading version {ver}… (enter password)").format(
                ver=info["version"]))

        def arbeit():
            erfolg = updater.lade_und_installiere(info)
            GLib.idle_add(self._update_fertig, erfolg)

        threading.Thread(target=arbeit, daemon=True).start()

    def _update_fertig(self, erfolg):
        if erfolg:
            self.zeige_toast(_("Updated. Please restart the app."))
        else:
            self.zeige_toast(_("Update failed or canceled."))
        return GLib.SOURCE_REMOVE

    def _logo(self):
        """Kleines App-Logo für die Kopfleiste.

        Über Gdk.Texture + Gtk.Image mit fester pixel_size. Ein Gtk.Picture
        würde die natürliche Bildgröße (1024) als Platzbedarf anmelden und die
        Kopfleiste aufblähen; Gtk.Image richtet sich nur nach pixel_size.
        """
        texture = logo_texture()
        logo = Gtk.Image.new_from_paintable(texture)
        logo.set_pixel_size(22)
        logo.set_valign(Gtk.Align.CENTER)
        return logo

    def _caption(self, text):
        """Kleine, gedämpfte Abschnitts-Überschrift über der Liste."""
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("dim-label")
        label.add_css_class("sidebar-caption")
        label.set_margin_top(10)
        label.set_margin_start(16)
        label.set_margin_bottom(4)
        return label

    def _bereich_liste(self):
        """Die anklickbare Liste der Bereiche (inkl. Trennlinie)."""
        self._listbox = Gtk.ListBox()
        self._listbox.add_css_class("navigation-sidebar")
        self._listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._listbox.connect("row-selected", self._on_row_selected)

        self._erste_zeile = None
        for _key, titel, icon_name, erzeuge_seite in self._bereiche:
            zeile = Adw.ActionRow(title=titel)
            zeile.add_prefix(Gtk.Image(icon_name=icon_name))
            # Erzeuger-Funktion direkt an der Zeile merken (siehe Modul-Doku).
            zeile.erzeuge_seite = erzeuge_seite
            self._listbox.append(zeile)

            if self._erste_zeile is None:
                self._erste_zeile = zeile

        return self._listbox

    def _springe_zu(self, key):
        """Wählt den Bereich mit diesem Schlüssel an (Sprung aus der Übersicht)."""
        index = self._index_nach_key.get(key)
        if index is None:
            return
        zeile = self._listbox.get_row_at_index(index)
        if zeile is not None:
            self._listbox.select_row(zeile)

    def _on_row_selected(self, _listbox, zeile):
        """Bei Auswahl die zur Zeile gehörende Seite rechts anzeigen."""
        if zeile is None:
            return

        # Seite einmal bauen und an der Zeile zwischenspeichern. Ein erneuter
        # Wechsel zeigt dann die fertige Seite sofort, ohne Neuaufbau (und damit
        # ohne Ruckeln).
        seite = getattr(zeile, "seite", None)
        if seite is None:
            erzeuge_seite = getattr(zeile, "erzeuge_seite", None)
            if erzeuge_seite is None:
                return
            seite = erzeuge_seite()
            zeile.seite = seite

        # Nur setzen, wenn nicht schon angezeigt. Sonst würde dieselbe (bereits
        # eingehängte) Seite erneut gesetzt -> Adwaita-Assertion (parent != NULL).
        if self._split.get_content() is not seite:
            self._split.set_content(seite)
