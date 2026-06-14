"""Hauptfenster der App.

Nutzt Adw.NavigationSplitView: links eine Seitenleiste mit Logo und den sechs
Bereichen, rechts der Inhalt des gewählten Bereichs. Die Liste self._bereiche
beschreibt die Einträge; ein None-Eintrag wird zur Trennlinie. Jede klickbare
Zeile merkt sich ihre Seiten-Erzeuger-Funktion direkt am Objekt
(zeile.erzeuge_seite), damit Trennzeilen die Zuordnung nicht verschieben.
"""

import os

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from src.core import onboarding
from src.core.settings import AppSettings
from src.pages.appearance import AppearancePage
from src.pages.background import BackgroundPage
from src.pages.backup import BackupPage
from src.pages.cursor import CursorPage
from src.pages.dock import DockPage
from src.pages.extensions import ExtensionsPage
from src.pages.fonts import FontsPage
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

        # Die Bereiche der Seitenleiste. Pro Eintrag: Titel (Pango-Markup, daher
        # "&amp;"), Icon-Name und eine Funktion, die die Seite baut.
        self._bereiche = [
            ("Hintergrund", "image-x-generic-symbolic",
             lambda: BackgroundPage(self._settings)),
            ("Symbole &amp; Design", "applications-graphics-symbolic",
             lambda: AppearancePage(self._settings)),
            ("Mauszeiger", "input-mouse-symbolic",
             lambda: CursorPage(self._settings)),
            ("Schriftarten", "font-x-generic-symbolic",
             lambda: FontsPage(self._settings)),
            ("Shell-Design", "video-display-symbolic",
             lambda: ShellPage(self._settings)),
            ("Dock", "view-app-grid-symbolic",
             lambda: DockPage(self._settings)),
            ("Erweiterungen", "application-x-addon-symbolic",
             lambda: ExtensionsPage(self._settings)),
            ("System", "applications-system-symbolic",
             lambda: SystemPage(self._settings)),
            ("Sicherung", "document-save-symbolic",
             lambda: BackupPage(self._settings)),
        ]

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
        self.set_content(self._toasts)

        # Startauswahl: erste echte Zeile, löst row-selected aus.
        self._listbox.select_row(self._erste_zeile)

        # Beim allerersten Start die Einführung zeigen. Über idle_add, damit das
        # Fenster vorher sichtbar ist (der Dialog braucht ein präsentiertes
        # Eltern-Fenster).
        if onboarding.ist_erster_start():
            GLib.idle_add(self._zeige_willkommen)

    def _zeige_willkommen(self):
        WelcomeDialog().present(self)
        onboarding.als_gesehen_markieren()
        return GLib.SOURCE_REMOVE

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

    def _menue_knopf(self):
        """Hamburger-Menü rechts in der Kopfleiste."""
        menue = Gio.Menu()
        menue.append("Über Design Manager", "win.about")
        menue.append("Beenden", "win.quit")

        knopf = Gtk.MenuButton()
        knopf.set_icon_name("open-menu-symbolic")
        knopf.set_menu_model(menue)
        knopf.set_tooltip_text("Hauptmenü")
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
        for titel, icon_name, erzeuge_seite in self._bereiche:
            zeile = Adw.ActionRow(title=titel)
            zeile.add_prefix(Gtk.Image(icon_name=icon_name))
            # Erzeuger-Funktion direkt an der Zeile merken (siehe Modul-Doku).
            zeile.erzeuge_seite = erzeuge_seite
            self._listbox.append(zeile)

            if self._erste_zeile is None:
                self._erste_zeile = zeile

        return self._listbox

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
