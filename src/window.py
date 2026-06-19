"""Hauptfenster der App.

Nutzt Adw.NavigationSplitView: links eine Seitenleiste mit Logo und den sechs
Bereichen, rechts der Inhalt des gewählten Bereichs. Die Liste self._bereiche
beschreibt die Einträge; ein None-Eintrag wird zur Trennlinie. Jede klickbare
Zeile merkt sich ihre Seiten-Erzeuger-Funktion direkt am Objekt
(zeile.erzeuge_seite), damit Trennzeilen die Zuordnung nicht verschieben.
"""

import threading

from gi.repository import Adw, Gio, GLib, Gtk

from src import compat
from src.i18n import _
from src.logo import logo_texture
from src.core import (gdm, healthcheck, lockscreen, onboarding, restorepoint,
                      schedule, updater)
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
        self.set_content(wurzel)

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

    def melde_installation(self, ergebnis, fehler):
        """Rückmeldung der Dropzone: Toast zeigen und die Liste neu laden.

        Die Dropzone ruft das nach einer Installation auf. Bei Erfolg bauen wir
        die aktive Seite neu, damit ein neu installiertes Design sofort in ihrer
        Liste erscheint.
        """
        if fehler:
            self.zeige_toast(
                _("Installation failed: {error}").format(error=fehler))
            return
        self.zeige_toast(
            _("Installed: {items}").format(items=", ".join(ergebnis)))
        self._reload_aktive_seite()

    def zeige_toast(self, text):
        """Zeigt eine kurze Meldung über dem aktuellen Inhalt.

        Die Seiten nutzen das über get_root() für Rückmeldungen (z.B. nach dem
        Entfernen eines Designs).
        """
        self._toasts.add_toast(Adw.Toast(title=text))

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

    def _menue_knopf(self):
        """Hamburger-Menü rechts in der Kopfleiste."""
        menue = Gio.Menu()
        menue.append(_("Restore safe state"), "win.safe-state")
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
