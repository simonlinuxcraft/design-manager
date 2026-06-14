"""Hauptfenster der App.

Nutzt Adw.NavigationSplitView: links eine Seitenleiste mit Logo und den sechs
Bereichen, rechts der Inhalt des gewählten Bereichs. Die Liste self._bereiche
beschreibt die Einträge; ein None-Eintrag wird zur Trennlinie. Jede klickbare
Zeile merkt sich ihre Seiten-Erzeuger-Funktion direkt am Objekt
(zeile.erzeuge_seite), damit Trennzeilen die Zuordnung nicht verschieben.
"""

import os

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from src.core import healthcheck, onboarding, restorepoint
from src.core.settings import AppSettings
from src.pages.appearance import AppearancePage
from src.pages.background import BackgroundPage
from src.pages.backup import BackupPage
from src.pages.cursor import CursorPage
from src.pages.dock import DockPage
from src.pages.extensions import ExtensionsPage
from src.pages.fonts import FontsPage
from src.pages.looks import LooksPage
from src.pages.overview import OverviewPage
from src.pages.shell import ShellPage
from src.pages.system import SystemPage
from src.widgets.welcome import WelcomeDialog


APP_VERSION = "0.1.0"

# Logo für die Kopfleiste (Projektwurzel liegt eine Ebene über src/). Gtk.Picture
# skaliert die hochauflösende Datei auf die kleine Header-Größe herunter.
LOGO_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "design-manager-transparent-1024.png",
)


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
            ("overview", "Übersicht", "view-grid-symbolic",
             lambda: OverviewPage(self._settings, self._springe_zu)),
            ("looks", "Looks", "starred-symbolic",
             lambda: LooksPage(self._settings)),
            ("background", "Hintergrund", "image-x-generic-symbolic",
             lambda: BackgroundPage(self._settings)),
            ("appearance", "Symbole &amp; Design", "applications-graphics-symbolic",
             lambda: AppearancePage(self._settings)),
            ("cursor", "Mauszeiger", "input-mouse-symbolic",
             lambda: CursorPage(self._settings)),
            ("fonts", "Schriftarten", "font-x-generic-symbolic",
             lambda: FontsPage(self._settings)),
            ("shell", "Shell-Design", "video-display-symbolic",
             lambda: ShellPage(self._settings)),
            ("dock", "Dock", "view-app-grid-symbolic",
             lambda: DockPage(self._settings)),
            ("extensions", "Erweiterungen", "application-x-addon-symbolic",
             lambda: ExtensionsPage(self._settings)),
            ("system", "System", "applications-system-symbolic",
             lambda: SystemPage(self._settings)),
            ("backup", "Sicherung", "document-save-symbolic",
             lambda: BackupPage(self._settings)),
        ]
        # Schlüssel -> Listenposition, für Sprünge aus der Übersicht.
        self._index_nach_key = {
            eintrag[0]: i for i, eintrag in enumerate(self._bereiche)}

        self._split = Adw.NavigationSplitView()
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
        self._banner = Adw.Banner()
        self._banner.set_revealed(False)
        self._banner.connect("button-clicked", self._on_banner_korrektur)
        self._banner_probleme = []

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

    def _zeige_willkommen(self):
        WelcomeDialog().present(self)
        onboarding.als_gesehen_markieren()
        return GLib.SOURCE_REMOVE

    def _pruefe_gesundheit(self):
        """Blendet ein Banner ein, wenn ein gesetztes Design auf der Platte fehlt."""
        self._banner_probleme = healthcheck.pruefe(self._settings)
        if not self._banner_probleme:
            return GLib.SOURCE_REMOVE
        labels = ", ".join(label for label, _ in self._banner_probleme)
        self._banner.set_title(
            "Nicht gefunden: " + labels + ". GNOME nutzt ersatzweise Adwaita.")
        self._banner.set_button_label("Standard setzen")
        self._banner.set_revealed(True)
        return GLib.SOURCE_REMOVE

    def _on_banner_korrektur(self, _banner):
        """Schließt die gemeldeten Lücken über die reset_*-Methoden."""
        for _label, methode in self._banner_probleme:
            getattr(self._settings, methode)()
        self._banner_probleme = []
        self._banner.set_revealed(False)
        self.zeige_toast("Auf sicheres Standard-Design gesetzt.")
        self._reload_aktive_seite()

    def melde_installation(self, ergebnis, fehler):
        """Rückmeldung der Dropzone: Toast zeigen und die Liste neu laden.

        Die Dropzone ruft das nach einer Installation auf. Bei Erfolg bauen wir
        die aktive Seite neu, damit ein neu installiertes Design sofort in ihrer
        Liste erscheint.
        """
        if fehler:
            self.zeige_toast("Installation fehlgeschlagen: " + fehler)
            return
        self.zeige_toast("Installiert: " + ", ".join(ergebnis))
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

    def _build_sidebar(self):
        """Linke Spalte: flache Kopfleiste mit Marke, darunter die Liste."""
        header = Adw.HeaderBar()
        header.add_css_class("flat")  # kein eigener Hintergrund -> ein Block
        header.pack_start(self._logo())
        header.pack_end(self._menue_knopf())
        header.pack_end(self._farbschema_knopf())
        header.set_title_widget(
            Adw.WindowTitle(title="Design Manager", subtitle="v" + APP_VERSION)
        )

        inhalt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        inhalt.append(self._caption("EINSTELLUNGEN"))
        inhalt.append(self._bereich_liste())

        toolbar = Adw.ToolbarView()
        toolbar.add_css_class("sidebar-pane")  # ein durchgehender dunkler Ton
        toolbar.add_top_bar(header)
        toolbar.set_content(inhalt)
        return Adw.NavigationPage(title="Design Manager", child=toolbar)

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

        # Zustands-Aktion fürs System-Farbschema (hell/dunkel/automatisch). Das
        # Menü zeigt am aktiven Wert automatisch einen Punkt, weil die Aktion
        # einen String-Zustand hat.
        schema = Gio.SimpleAction.new_stateful(
            "color-scheme", GLib.VariantType.new("s"),
            GLib.Variant.new_string(self._settings.color_scheme()))
        schema.connect("activate", self._on_color_scheme)
        self.add_action(schema)

    def _on_color_scheme(self, action, parameter):
        action.set_state(parameter)
        self._settings.set_color_scheme(parameter.get_string())

    def _menue_knopf(self):
        """Hamburger-Menü rechts in der Kopfleiste."""
        menue = Gio.Menu()
        menue.append("Sicheren Zustand herstellen", "win.safe-state")
        menue.append("Über Design Manager", "win.about")
        menue.append("Beenden", "win.quit")

        knopf = Gtk.MenuButton()
        knopf.set_icon_name("open-menu-symbolic")
        knopf.set_menu_model(menue)
        knopf.set_tooltip_text("Hauptmenü")
        return knopf

    def _farbschema_knopf(self):
        """Umschalter fürs System-Farbschema (hell/dunkel/automatisch).

        Steuert org.gnome.desktop.interface/color-scheme. Das eigene Fenster
        bleibt bewusst dunkel (die App erzwingt FORCE_DARK in main.py); der
        Umschalter wirkt auf den Rest des Systems.
        """
        menue = Gio.Menu()
        menue.append("Hell", "win.color-scheme::prefer-light")
        menue.append("Dunkel", "win.color-scheme::prefer-dark")
        menue.append("Automatisch", "win.color-scheme::default")

        knopf = Gtk.MenuButton()
        knopf.set_icon_name("display-brightness-symbolic")
        knopf.set_menu_model(menue)
        knopf.set_tooltip_text("Helligkeit (System-Farbschema)")
        return knopf

    def _on_ueber(self, _action, _param):
        """Zeigt den Über-Dialog mit Version, Logo und Lizenz."""
        dialog = Adw.AboutDialog(
            application_name="Design Manager",
            application_icon="io.github.simonlinuxcraft.DesignManager",
            version=APP_VERSION,
            developer_name="simonlinuxcraft",
            comments="Das Erscheinungsbild von GNOME zentral anpassen: "
                     "Hintergrund, Designs, Symbole, Mauszeiger und Schrift.",
            license_type=Gtk.License.GPL_3_0,
            copyright="© 2026 simonlinuxcraft",
        )
        dialog.present(self)

    def _on_safe_state(self, _action, _param):
        """Notausstieg: nach Sicherungspunkt alles auf sichere Standards setzen."""
        dialog = Adw.AlertDialog(
            heading="Sicheren Zustand herstellen?",
            body="Erst wird ein Sicherungspunkt angelegt, dann werden Design, "
                 "Symbole, Mauszeiger und Shell-Design auf garantiert lauffähige "
                 "Standardwerte (Adwaita) gesetzt. Das hilft, wenn ein Design die "
                 "Oberfläche unbrauchbar gemacht hat.")
        dialog.add_response("abbrechen", "Abbrechen")
        dialog.add_response("anwenden", "Sicheren Zustand setzen")
        dialog.set_response_appearance(
            "anwenden", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("abbrechen")
        dialog.set_close_response("abbrechen")
        dialog.connect("response", self._on_safe_state_antwort)
        dialog.present(self)

    def _on_safe_state_antwort(self, _dialog, antwort):
        if antwort != "anwenden":
            return
        restorepoint.erstelle(self._settings, "vor Notausstieg")
        # Die reset_*-Methoden setzen ausschließlich auf Adwaita bzw. den leeren
        # Shell-Wert, also auf garantiert vorhandene, gültige Designs. Eine
        # Whitelist-Prüfung erübrigt sich, weil die Ziele bekannt sicher sind.
        self._settings.reset_gtk_theme()
        self._settings.reset_icon_theme()
        self._settings.reset_cursor_theme()
        self._settings.reset_shell_theme()
        self._banner.set_revealed(False)
        self.zeige_toast("Sicherer Zustand gesetzt (Adwaita).")
        self._reload_aktive_seite()

    def _logo(self):
        """Kleines App-Logo für die Kopfleiste.

        Über Gdk.Texture + Gtk.Image mit fester pixel_size. Ein Gtk.Picture
        würde die natürliche Bildgröße (1024) als Platzbedarf anmelden und die
        Kopfleiste aufblähen; Gtk.Image richtet sich nur nach pixel_size.
        """
        texture = Gdk.Texture.new_from_filename(LOGO_FILE)
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
