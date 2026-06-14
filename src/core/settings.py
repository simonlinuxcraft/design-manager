"""Wrapper um Gio.Settings.

Hier läuft die eigentliche Kommunikation mit GNOME. Gio.Settings schreibt
direkt in die dconf-Datenbank, also genau dorthin, wo GNOME seine
Einstellungen ablegt. Es ist kein Aufruf von "gsettings" per subprocess nötig.

Jeder Setter unten zeigt offen, welches *Schema* und welcher *Schlüssel*
hinter einer Einstellung steckt. Das ist der Kern, den die App im Grunde nur
hübsch verpackt.
"""

import os
import shutil
from datetime import datetime
from urllib.parse import quote

from gi.repository import GLib, Gio

from src.core import themes, variety


def schema_vorhanden(schema_id):
    """Prüft, ob ein GSettings-Schema auf dem System installiert ist.

    Wichtig für das Shell-Design: dessen Schema gibt es nur, wenn die
    Erweiterung "User Themes" installiert ist. Ohne diese Prüfung würde
    Gio.Settings.new() bei einem fehlenden Schema die App zum Absturz bringen.
    """
    quelle = Gio.SettingsSchemaSource.get_default()
    if quelle is None:
        return False
    # Zweites Argument True = auch in den Eltern-Schemas nachsehen.
    return quelle.lookup(schema_id, True) is not None


def _hat_schluessel(settings, key):
    """True, wenn das Schema hinter 'settings' den Schlüssel 'key' kennt.

    Manche Schlüssel gibt es erst ab einer bestimmten GNOME-Version. Die
    Akzentfarbe (accent-color) zum Beispiel existiert erst ab GNOME 47; auf
    älteren Systemen würde ein Zugriff sonst abstürzen.
    """
    if settings is None:
        return False
    return settings.props.settings_schema.has_key(key)


def _schreibe_default_cursor(name):
    """Verankert den Mauszeiger zusätzlich als geerbtes Standard-Theme.

    Der dconf-Schlüssel allein wirkt nicht überall: unter X11 bestimmen der
    Zeiger über dem Desktop und Nicht-GTK-Programme den Cursor über
    ~/.icons/default (Inherits=...), unter Wayland greifen darüber auch
    XWayland-Programme. Dieselbe Datei deckt also beide Sitzungsarten ab; eine
    Fallunterscheidung ist nicht nötig und wäre nur eine Fehlerquelle mehr.

    Defensiv: ein Symlink, ein echtes Cursor-Theme (eigener cursors/-Ordner) und
    eine fremde, nicht von uns stammende index.theme werden nicht angetastet, nur
    unser eigener Inherits-Stub wird geschrieben oder aktualisiert. Schlägt das
    Schreiben fehl, bleibt der Cursor immerhin über dconf gesetzt.
    """
    if not name:
        return
    ordner = os.path.expanduser("~/.icons/default")
    index = os.path.join(ordner, "index.theme")
    if os.path.islink(ordner) or os.path.isdir(os.path.join(ordner, "cursors")):
        return
    if os.path.isfile(index) and not _ist_unser_stub(index):
        return
    try:
        os.makedirs(ordner, exist_ok=True)
        with open(index, "w", encoding="utf-8") as f:
            f.write(_CURSOR_STUB_KOPF + "Inherits=" + name + "\n")
    except OSError:
        pass  # Cursor ist via dconf gesetzt; die Datei ist nur die Absicherung


# Kopf unseres ~/.icons/default-Stubs; die Comment-Zeile dient zugleich als
# Erkennungsmarke, damit wir nur unsere eigene Datei überschreiben.
_CURSOR_STUB_KOPF = ("[Icon Theme]\n"
                     "Name=Default\n"
                     "Comment=Default Cursor Theme\n")


def _ist_unser_stub(index_pfad):
    try:
        with open(index_pfad, encoding="utf-8") as f:
            return "Comment=Default Cursor Theme" in f.read()
    except OSError:
        return False


def _xcursor_pfade():
    """Orte, die der X-Server (libXcursor) nach Cursor-Themes durchsucht.

    Das ist der einkompilierte Default-Pfad von libXcursor. ~/.local/share/icons
    ist hier bewusst NICHT dabei: der Ordner gehört zwar zum XDG-Standard und
    GTK findet dort Symbol-Designs, aber libXcursor kennt ihn nicht.
    """
    return [
        os.path.expanduser("~/.icons"),
        "/usr/share/icons",
        "/usr/share/pixmaps",
    ]


def _ist_cursor_theme(ordner):
    return os.path.isdir(os.path.join(ordner, "cursors"))


def _spiegele_cursor_in_pfad(name):
    """Verlinkt ein Cursor-Theme nach ~/.icons, falls es nur unter
    ~/.local/share/icons liegt.

    Unter X11 lädt der Zeiger nur, wenn das Theme in einem der Xcursor-Pfade
    liegt. Ein per Installer oder von Hand nach ~/.local/share/icons gelegtes
    Cursor-Theme wird dort nie gefunden, der Zeiger bleibt beim alten. Wir legen
    darum einen Symlink in ~/.icons an. Liegt das Theme schon im Suchpfad,
    passiert nichts (auch idempotent: ein bereits gesetzter Symlink zählt als
    vorhanden). Reine Absicherung; gesetzt wird der Zeiger ohnehin über dconf.
    """
    if not name:
        return
    for basis in _xcursor_pfade():
        if _ist_cursor_theme(os.path.join(basis, name)):
            return  # schon auffindbar
    quelle = os.path.join(os.path.expanduser("~/.local/share/icons"), name)
    if not _ist_cursor_theme(quelle):
        return  # nicht vorhanden oder kein Cursor-Theme
    icons = os.path.expanduser("~/.icons")
    ziel = os.path.join(icons, name)
    try:
        os.makedirs(icons, exist_ok=True)
        # Nichts Bestehendes antasten (auch keinen toten Symlink reparieren).
        if not os.path.exists(ziel) and not os.path.islink(ziel):
            os.symlink(quelle, ziel)
    except OSError:
        pass  # Cursor ist via dconf gesetzt; der Symlink ist nur die Absicherung


# --- libadwaita-Spiegel (~/.config/gtk-4.0) ---
# Moderne GNOME-Apps (Nautilus, Einstellungen, Texteditor) sind gegen libadwaita
# gelinkt und ignorieren den benannten gtk-theme-Schluessel komplett. Sie laden
# nur hell/dunkel und, falls vorhanden, ein eigenes Stylesheet unter
# ~/.config/gtk-4.0/gtk.css. Damit ein gewaehltes GTK-Design auch dort wirkt,
# spiegeln wir das gtk-4.0-CSS des Themes per kleiner @import-Stubdatei dorthin.
#
# Das ist der fragilste Eingriff der App, darum streng reversibel und defensiv:
#  - angelegt wird nur eine kleine echte gtk.css mit Markerzeile, die das
#    gtk-4.0-CSS des Themes per @import mit ABSOLUTEM file://-Pfad einbindet. So
#    loesen sich dessen relative url("../assets/..")-Pfade (Checkboxen, Radios)
#    korrekt zum Theme-Ordner auf statt gegen ~/.config; ein direkter Symlink
#    wuerde genau diese 199 Asset-Pfade zerbrechen,
#  - ein bereits vorhandener FREMDER Override (z.B. von kde-gtk-config) wird vor
#    dem Ueberschreiben einmalig in ein Backup geschoben, nie blind geloescht,
#  - Yaru und Adwaita erzwingen NIE einen Override (sie sind die sicheren
#    Standards und sehen unter libadwaita ohnehin richtig aus),
#  - reset_gtk_theme raeumt den Spiegel restlos weg, damit der Notausstieg auch
#    libadwaita-Apps garantiert auf das eingebaute Adwaita zuruecksetzt.

_GTK4_CONFIG = os.path.expanduser("~/.config/gtk-4.0")
# Diese Eintraege verwaltet die App. Beim Anlegen wird nur die gtk.css-Stubdatei
# geschrieben; gtk-dark.css und assets stehen hier mit drin, damit Eintraege aus
# einer frueheren (Symlink-)Fassung beim Aufraeumen sicher mit weggehen.
_LIBADW_EINTRAEGE = ("gtk.css", "gtk-dark.css", "assets")
_GTK4_BACKUP_BASIS = os.path.expanduser(
    "~/.local/share/design-manager/gtk-4.0-backup")
# Markerzeile am Anfang unserer Stubdatei. Daran erkennen wir beim Aufraeumen
# zweifelsfrei die eigene Datei und fassen fremde gtk.css nie an.
_MARKER = "design-manager: libadwaita-Spiegel"


def _css_spiegelbar(pfad):
    """True, wenn pfad eine echte, aus dem Dateikontext ladbare Stylesheet ist.

    Lehnt gresource-Weiterleitungen ab: manche Themes (z.B. die Yaru-Familie)
    haben als gtk-4.0/gtk.css nur einen Stub `@import url("resource://...")`, der
    eigentliche Style steckt in einer .gresource. Ueber unseren file://-Spiegel
    laesst sich diese nicht registrierte Ressource nicht laden, das Theme kaeme
    praktisch leer an. Solche Stubs haben keine CSS-Regel, also keine geschweifte
    Klammer. Bei Lesefehler konservativ False (lieber kein Override).
    """
    try:
        with open(pfad, "r", encoding="utf-8", errors="ignore") as f:
            return "{" in f.read(65536)
    except OSError:
        return False


def _theme_gtk4_quelle(name):
    """(gtk4_ordner, css_datei) des Themes oder None, wenn kein Override noetig.

    Liefert den gtk-4.0-Ordner und dessen gtk.css. Adwaita, Yaru und ein leerer
    Name brauchen keinen Override und ergeben None.
    """
    if not name:
        return None
    kennung = name.lower()
    if kennung == "adwaita" or kennung.startswith("yaru"):
        return None
    for basis in themes.THEME_DIRS:
        gtk4 = os.path.join(basis, name, "gtk-4.0")
        css = os.path.join(gtk4, "gtk.css")
        if os.path.isfile(css) and _css_spiegelbar(css):
            return gtk4, css
    return None


def _existiert(pfad):
    return os.path.islink(pfad) or os.path.exists(pfad)


def _ist_unser_override(pfad):
    """True, wenn 'pfad' unser eigener libadwaita-Spiegel ist.

    Unser Spiegel ist eine kleine echte Datei mit einer Markerzeile (siehe
    _MARKER). So trennen wir ihn sicher von echten Dateien, die der Nutzer oder
    ein anderes Werkzeug (kde-gtk-config) dort abgelegt hat: nur was den Marker
    trägt (oder ein Alt-Symlink in ein Theme-Verzeichnis aus einer früheren
    Fassung ist) wird je entfernt oder ersetzt. Fremdes bleibt unberührt.
    """
    if os.path.islink(pfad):
        ziel = os.path.realpath(pfad)
        return any(ziel.startswith(os.path.realpath(d) + os.sep)
                   for d in themes.THEME_DIRS)
    try:
        with open(pfad, "r", encoding="utf-8", errors="ignore") as f:
            return _MARKER in f.read(256)
    except OSError:
        return False


def _sichere_fremden_override():
    """Schiebt einen vorhandenen FREMDEN Override einmalig in ein Backup.

    Nur was wirklich fremd ist (echte Datei/Ordner oder ein Symlink, der nicht
    in ein Theme-Verzeichnis zeigt) wird gesichert; unsere eigenen Symlinks aus
    einem frueheren Lauf bleiben liegen und werden gleich ueberschrieben. Gelingt
    das Sichern nicht, wird nichts angefasst (lieber Override behalten als Daten
    verlieren).
    """
    fremd = [e for e in _LIBADW_EINTRAEGE
             if _existiert(os.path.join(_GTK4_CONFIG, e))
             and not _ist_unser_override(os.path.join(_GTK4_CONFIG, e))]
    if not fremd:
        return True
    ziel = _GTK4_BACKUP_BASIS + "-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        os.makedirs(ziel, exist_ok=True)
        for e in fremd:
            shutil.move(os.path.join(_GTK4_CONFIG, e), os.path.join(ziel, e))
        return True
    except OSError:
        return False


def _schreibe_stub(css_pfad):
    """Schreibt ~/.config/gtk-4.0/gtk.css als Stub, der css_pfad per @import lädt.

    Der @import nutzt einen absoluten file://-Pfad, damit die relativen
    url("../assets/..")-Verweise in der importierten Theme-CSS sich gegen den
    Theme-Ordner auflösen, nicht gegen ~/.config. Eine etwaige eigene Datei wird
    ersetzt; eine echte Fremd-Datei (Sicherung schlug fehl) bleibt unberührt.
    """
    ziel = os.path.join(_GTK4_CONFIG, "gtk.css")
    if os.path.islink(ziel) and _ist_unser_override(ziel):
        os.unlink(ziel)  # Alt-Symlink aus früherer Fassung weg, dann neu schreiben
    elif _existiert(ziel) and not _ist_unser_override(ziel):
        return  # echte Fremd-Datei, nicht überschreiben (sollte gesichert sein)
    uri = "file://" + quote(os.path.abspath(css_pfad))
    inhalt = "/* %s */\n@import url(\"%s\");\n" % (_MARKER, uri)
    with open(ziel, "w", encoding="utf-8") as f:
        f.write(inhalt)


def _entferne_libadwaita():
    """Entfernt unseren libadwaita-Spiegel restlos (eigene Stubdatei/Alt-Symlinks).

    Fremde Dateien im selben Ordner werden nie angefasst. Danach fallen
    libadwaita-Apps auf das eingebaute Adwaita zurueck, also auf einen
    garantiert gueltigen Zustand. Traegt den Notausstieg mit.
    """
    for eintrag in _LIBADW_EINTRAEGE:
        ziel = os.path.join(_GTK4_CONFIG, eintrag)
        if _ist_unser_override(ziel):
            try:
                os.unlink(ziel)
            except OSError:
                pass


def _spiegle_libadwaita(name):
    """Spiegelt das gtk-4.0-CSS des Themes nach ~/.config/gtk-4.0/gtk.css.

    Hat das Theme kein nutzbares gtk-4.0 (oder ist es Adwaita/Yaru), wird ein
    evtl. von uns angelegter Spiegel entfernt, damit libadwaita-Apps sauber auf
    den Standard zuruckfallen, statt am alten Design zu kleben. Schlaegt das
    Sichern eines fremden Overrides fehl, wird nichts ueberschrieben.

    Bekannte (rein kosmetische) Grenze, kein Crash-Risiko: ein Theme, das fuer
    ein neueres libadwaita gebaut ist als das lokale (z.B. var(--accent-bg-color)
    aus 1.6 auf 1.5), erzeugt beim Laden Parser-Warnungen; GTK ueberspringt die
    Regeln, das Theme wirkt dort unvollstaendig. Betrifft jede Lademethode, nicht
    nur den Spiegel.
    """
    quelle = _theme_gtk4_quelle(name)
    if quelle is None:
        _entferne_libadwaita()
        return
    _gtk4, css = quelle
    try:
        if not _sichere_fremden_override():
            return
        os.makedirs(_GTK4_CONFIG, exist_ok=True)
        # Stubdatei mit @import auf die zum Modus passende Quelle (hell/dunkel).
        _schreibe_stub(css)
        # Reste aus einer früheren (Symlink-)Fassung wegräumen: gtk-dark.css und
        # assets legt die Stub-Variante nicht mehr an, der @import löst die
        # Assets selbst aus dem Theme-Ordner auf.
        for rest in ("gtk-dark.css", "assets"):
            ziel = os.path.join(_GTK4_CONFIG, rest)
            if _ist_unser_override(ziel):
                os.unlink(ziel)
    except OSError:
        pass  # gtk-theme ist via dconf gesetzt; der Spiegel ist nur Zugabe


def _stabiler_hintergrund_wert(wert):
    """Ersetzt einen Variety-Zwischendatei-URI durch das echte Quellbild.

    Variety legt in picture-uri seine flüchtige wallpaper-auto-rotated-Datei ab,
    die es später löscht. Für eine Sicherung das stabile Quellbild nehmen, sonst
    zeigt das Profil später auf eine nicht mehr existierende Datei. Ist der Wert
    kein Variety-Temp-Pfad (oder kein Quellbild bekannt), bleibt er unverändert.
    """
    uri = wert.get_string()
    if not uri:
        return wert
    pfad = Gio.File.new_for_uri(uri).get_path()
    if pfad and os.path.realpath(pfad).startswith(
            os.path.realpath(variety.TEMP_WALLPAPER)):
        quelle = variety.aktuelles_quellbild()
        if quelle:
            return GLib.Variant("s", Gio.File.new_for_path(quelle).get_uri())
    return wert


class AppSettings:
    """Gebündelter Zugriff auf alle Einstellungen, die die App verändert.

    Wir halten pro Schema ein Gio.Settings-Objekt. Lesen geht über get_*,
    Schreiben über set_*; beides wirkt sofort und bleibt dauerhaft.
    """

    # Schema-Namen als Konstanten, damit sie nur an einer Stelle stehen.
    INTERFACE = "org.gnome.desktop.interface"
    BACKGROUND = "org.gnome.desktop.background"
    # Fensterverwaltung (Knöpfe in der Titelleiste). GNOME-Standard, überall da.
    WM = "org.gnome.desktop.wm.preferences"
    # Schema für das GNOME-Shell-Design. Existiert nur, wenn die Erweiterung
    # „User Themes" installiert ist, darum unten defensiv behandelt.
    USER_THEME = "org.gnome.shell.extensions.user-theme"
    # Schema und UUID der Erweiterung, über die das Shell-Design wirkt. Ein
    # gesetztes Design wird nur angewendet, wenn diese Erweiterung eingeschaltet
    # ist (steht dann in org.gnome.shell/enabled-extensions).
    SHELL = "org.gnome.shell"
    USER_THEME_UUID = "user-theme@gnome-shell-extensions.gcampax.github.com"

    # Sicheres Standard-GTK-Design für den Notausstieg-Knopf. Adwaita ist in GTK
    # fest eingebaut, existiert also immer und kann keine Parse-Fehler werfen,
    # selbst wenn ein selbstgebautes Design die Oberfläche unbrauchbar macht.
    SAFE_GTK_THEME = "Adwaita"
    # Sichere Standardwerte für Symbole und Mauszeiger. Adwaita liegt systemweit
    # in /usr/share/icons und hat sowohl Icons als auch einen Mauszeiger.
    SAFE_ICON_THEME = "Adwaita"
    SAFE_CURSOR_THEME = "Adwaita"

    # Schlüssel, die Sicherung & Wiederherstellung erfasst. Alle sind vom Typ
    # String. Jeder Eintrag ist (Schema-ID, Schlüsselname). Diese eine Liste ist
    # die Wahrheit darüber, was eine Sicherung umfasst. Fehlt ein Schema auf dem
    # System (z.B. User-Theme), wird sein Eintrag still übersprungen.
    GESICHERTE_SCHLUESSEL = [
        (INTERFACE, "gtk-theme"),
        (INTERFACE, "icon-theme"),
        (INTERFACE, "cursor-theme"),
        (INTERFACE, "font-name"),
        (INTERFACE, "document-font-name"),
        (INTERFACE, "monospace-font-name"),
        (INTERFACE, "text-scaling-factor"),
        (INTERFACE, "font-antialiasing"),
        (INTERFACE, "font-hinting"),
        (INTERFACE, "accent-color"),
        (INTERFACE, "enable-animations"),
        (INTERFACE, "show-battery-percentage"),
        (INTERFACE, "clock-show-seconds"),
        (INTERFACE, "clock-show-weekday"),
        (INTERFACE, "clock-show-date"),
        (BACKGROUND, "picture-uri"),
        (BACKGROUND, "picture-uri-dark"),
        (BACKGROUND, "picture-options"),
        (WM, "button-layout"),
        (USER_THEME, "name"),
    ]

    def __init__(self):
        # Diese Schemas gehören zum GNOME-Standard und sind überall vorhanden.
        self._interface = Gio.Settings.new(self.INTERFACE)
        self._background = Gio.Settings.new(self.BACKGROUND)
        self._wm = Gio.Settings.new(self.WM)
        # Schema-ID -> Gio.Settings, für den schlüsselweisen Zugriff bei
        # Sicherung/Wiederherstellung.
        self._nach_schema = {
            self.INTERFACE: self._interface,
            self.BACKGROUND: self._background,
            self.WM: self._wm,
        }

        # Shell-Design nur laden, wenn „User Themes" installiert ist. Sonst
        # würde Gio.Settings.new() das Programm zum Absturz bringen.
        if schema_vorhanden(self.USER_THEME):
            self._user_theme = Gio.Settings.new(self.USER_THEME)
            self._nach_schema[self.USER_THEME] = self._user_theme
        else:
            self._user_theme = None

        # Shell-Schema (für die Prüfung, ob die Erweiterung eingeschaltet ist).
        if schema_vorhanden(self.SHELL):
            self._shell = Gio.Settings.new(self.SHELL)
        else:
            self._shell = None

    # --- GTK-Design (das Aussehen der App-Fenster) ---

    def gtk_theme(self):
        return self._interface.get_string("gtk-theme")

    def set_gtk_theme(self, name):
        # Benannte GTK-Designs wirken nur auf GTK3-Apps. libadwaita-Apps
        # (Nautilus, Einstellungen, ...) lesen den Schluessel nicht; fuer die
        # spiegeln wir zusaetzlich das gtk-4.0-CSS nach ~/.config/gtk-4.0. Die
        # zum Modus passende Variante (hell/dunkel) waehlt _spiegle_libadwaita.
        self._interface.set_string("gtk-theme", name)
        _spiegle_libadwaita(name)

    def reset_gtk_theme(self):
        """Setzt das GTK-Design auf das sichere Standard-Design (Adwaita).

        Notausstieg: ein kaputtes Design (ungültiges CSS) kann die ganze Sitzung
        lahmlegen. Adwaita ist in GTK eingebaut und immer gültig, darum als
        garantierter Rückfallwert. Zusätzlich wird der libadwaita-Spiegel
        restlos entfernt, damit auch Nautilus & Co. auf Adwaita zurückfallen und
        nicht an einem kaputten gtk-4.0/gtk.css kleben bleiben.
        """
        self._interface.set_string("gtk-theme", self.SAFE_GTK_THEME)
        _entferne_libadwaita()

    # --- Symbol-Design (Icons) ---

    def icon_theme(self):
        return self._interface.get_string("icon-theme")

    def set_icon_theme(self, name):
        self._interface.set_string("icon-theme", name)

    def reset_icon_theme(self):
        """Setzt das Symbol-Design auf den sicheren Standard (Adwaita)."""
        self._interface.set_string("icon-theme", self.SAFE_ICON_THEME)

    # --- Mauszeiger ---

    def cursor_theme(self):
        return self._interface.get_string("cursor-theme")

    def set_cursor_theme(self, name):
        # Reihenfolge wichtig fürs Live-Umschalten ohne Neuanmeldung: erst das
        # Theme in den Xcursor-Pfad spiegeln, DANN den dconf-Schlüssel setzen.
        # gsd-xsettings reagiert sofort auf die Änderung und kann den Zeiger nur
        # live übernehmen, wenn das Theme zu dem Zeitpunkt schon auffindbar ist.
        _spiegele_cursor_in_pfad(name)
        self._interface.set_string("cursor-theme", name)
        _schreibe_default_cursor(name)

    def reset_cursor_theme(self):
        """Setzt den Mauszeiger auf den sicheren Standard (Adwaita).

        Geht über set_cursor_theme, damit der ~/.icons-Spiegel und der
        default-Stub mitgezogen werden.
        """
        self.set_cursor_theme(self.SAFE_CURSOR_THEME)

    # --- Systemschriftart (z.B. "Cantarell 11") ---

    def font_name(self):
        return self._interface.get_string("font-name")

    def set_font_name(self, name):
        self._interface.set_string("font-name", name)

    # --- Hintergrundbild ---
    # GNOME speichert Pfade hier als URI, also z.B. "file:///home/.../bild.jpg".

    def background_uri(self):
        return self._background.get_string("picture-uri")

    def set_background_uri(self, uri):
        self._background.set_string("picture-uri", uri)

    def background_uri_dark(self):
        return self._background.get_string("picture-uri-dark")

    def set_background_uri_dark(self, uri):
        self._background.set_string("picture-uri-dark", uri)

    # --- Anpassung des Hintergrunds (Zoom, gestreckt, ...) ---
    # picture-options ist ein Enum. Als Text: none, wallpaper, centered,
    # scaled, stretched, zoom, spanned.

    def picture_options(self):
        return self._background.get_string("picture-options")

    def set_picture_options(self, wert):
        self._background.set_string("picture-options", wert)

    # --- GNOME-Shell-Design (über die Erweiterung „User Themes") ---
    # Der Schlüssel "name" enthält den Theme-Namen; ein leerer Wert bedeutet das
    # Standard-Shell-Design von GNOME.

    def user_themes_verfuegbar(self):
        """True, wenn die Erweiterung „User Themes" installiert ist (Schema da)."""
        return self._user_theme is not None

    def user_themes_aktiv(self):
        """True, wenn „User Themes" installiert UND eingeschaltet ist.

        Nur dann wird ein gewähltes Shell-Design tatsächlich angewendet. Ist die
        Erweiterung installiert, aber ausgeschaltet, sieht man von einer Auswahl
        nichts. Geprüft über die enabled-extensions-Liste der Shell.
        """
        if self._user_theme is None:
            return False
        if self._shell is None:
            return True  # ohne Shell-Schema nicht prüfbar -> nicht warnen
        return self.USER_THEME_UUID in self._shell.get_strv("enabled-extensions")

    def shell_theme(self):
        if self._user_theme is None:
            return ""
        return self._user_theme.get_string("name")

    def set_shell_theme(self, name):
        if self._user_theme is not None:
            self._user_theme.set_string("name", name)

    def reset_shell_theme(self):
        """Setzt das Shell-Design auf den GNOME-Standard (leerer Wert)."""
        if self._user_theme is not None:
            self._user_theme.set_string("name", "")

    # --- Dokument- und Festbreitenschrift ---
    # Neben der allgemeinen Oberflächenschrift (font-name) kennt GNOME eine
    # eigene Schrift für Fließtext (document-font-name) und eine dicktengleiche
    # Schrift für Terminal/Code (monospace-font-name).

    def document_font_name(self):
        return self._interface.get_string("document-font-name")

    def set_document_font_name(self, name):
        self._interface.set_string("document-font-name", name)

    def monospace_font_name(self):
        return self._interface.get_string("monospace-font-name")

    def set_monospace_font_name(self, name):
        self._interface.set_string("monospace-font-name", name)

    # --- Schrift-Skalierung und -Glättung ---
    # text-scaling-factor ist eine Fließkommazahl (1.0 = Standard). Antialiasing
    # und Hinting sind Enums (Textwerte: none/grayscale/rgba bzw.
    # none/slight/medium/full).

    def text_scaling_factor(self):
        return self._interface.get_double("text-scaling-factor")

    def set_text_scaling_factor(self, wert):
        self._interface.set_double("text-scaling-factor", wert)

    def font_antialiasing(self):
        return self._interface.get_string("font-antialiasing")

    def set_font_antialiasing(self, wert):
        self._interface.set_string("font-antialiasing", wert)

    def font_hinting(self):
        return self._interface.get_string("font-hinting")

    def set_font_hinting(self, wert):
        self._interface.set_string("font-hinting", wert)

    # --- Akzentfarbe ---
    # Erst ab GNOME 47 (libadwaita 1.6). Vorher gibt es den Schlüssel nicht,
    # darum vor jedem Zugriff prüfen. Werte sind Textnamen wie "blue", "orange".

    def accent_verfuegbar(self):
        return _hat_schluessel(self._interface, "accent-color")

    def accent_color(self):
        if not self.accent_verfuegbar():
            return ""
        return self._interface.get_string("accent-color")

    def set_accent_color(self, wert):
        if self.accent_verfuegbar():
            self._interface.set_string("accent-color", wert)

    # --- Obere Leiste und Animationen ---
    # Boolesche Schalter im interface-Schema.

    def enable_animations(self):
        return self._interface.get_boolean("enable-animations")

    def set_enable_animations(self, an):
        self._interface.set_boolean("enable-animations", an)

    def show_battery_percentage(self):
        return self._interface.get_boolean("show-battery-percentage")

    def set_show_battery_percentage(self, an):
        self._interface.set_boolean("show-battery-percentage", an)

    def clock_show_seconds(self):
        return self._interface.get_boolean("clock-show-seconds")

    def set_clock_show_seconds(self, an):
        self._interface.set_boolean("clock-show-seconds", an)

    def clock_show_weekday(self):
        return self._interface.get_boolean("clock-show-weekday")

    def set_clock_show_weekday(self, an):
        self._interface.set_boolean("clock-show-weekday", an)

    def clock_show_date(self):
        return self._interface.get_boolean("clock-show-date")

    def set_clock_show_date(self, an):
        self._interface.set_boolean("clock-show-date", an)

    # --- Fensterknöpfe (Titelleiste) ---
    # button-layout ist ein String wie "appmenu:minimize,maximize,close". Links
    # und rechts vom Doppelpunkt stehen die Knöpfe der jeweiligen Seite.

    def button_layout(self):
        return self._wm.get_string("button-layout")

    def set_button_layout(self, layout):
        self._wm.set_string("button-layout", layout)

    # --- Sicherung & Wiederherstellung ---
    # Aufbau als verschachteltes Dict {schema: {schlüssel: wert}}, damit die
    # exportierte JSON-Datei lesbar und nach Schema gruppiert ist.

    def export_settings(self):
        """Aktuelle Werte aller gesicherten Schlüssel als Dict.

        Jeder Wert wird typ-erhaltend als GVariant-Text abgelegt (z.B. 'Yaru',
        true, 1.25). So überstehen auch Schalter (Boolean) und Zahlen (Double)
        die Sicherung, nicht nur Zeichenketten. Schlüssel, die es auf diesem
        System nicht gibt (fehlendes Schema oder eine zu alte GNOME-Version,
        etwa accent-color vor GNOME 47), werden übersprungen.
        """
        daten = {}
        for schema_id, key in self.GESICHERTE_SCHLUESSEL:
            settings = self._nach_schema.get(schema_id)
            if not _hat_schluessel(settings, key):
                continue
            wert = settings.get_value(key)
            # Hintergrund: zeigt picture-uri auf Varietys flüchtige
            # Zwischendatei, stattdessen das stabile Quellbild sichern.
            if schema_id == self.BACKGROUND and key in (
                    "picture-uri", "picture-uri-dark"):
                wert = _stabiler_hintergrund_wert(wert)
            daten.setdefault(schema_id, {})[key] = wert.print_(True)
        return daten

    def import_settings(self, daten):
        """Setzt die Schlüssel aus einem zuvor exportierten Dict.

        Fehlende oder unbekannte Einträge (und Schlüssel, die es hier nicht
        gibt) werden übersprungen, damit eine unvollständige, ältere oder von
        einem anderen System stammende Sicherung nicht scheitert.
        """
        for schema_id, key in self.GESICHERTE_SCHLUESSEL:
            settings = self._nach_schema.get(schema_id)
            if not _hat_schluessel(settings, key):
                continue
            text = daten.get(schema_id, {}).get(key)
            if text is None:
                continue
            try:
                # Mit dem erwarteten Typ parsen, damit z.B. "1.0" als Double und
                # nicht als Ganzzahl ankommt; set_value verlangt den exakten Typ.
                erwartet = settings.get_value(key).get_type()
                wert = GLib.Variant.parse(erwartet, text, None, None)
                settings.set_value(key, wert)
                # Der Mauszeiger braucht zusätzlich den ~/.icons/default-Stub,
                # damit er nach Restore/Profilwechsel überall greift (sonst zeigt
                # nur GTK das neue, der Desktop-Zeiger das alte Theme). Und er
                # muss im Xcursor-Pfad liegen, sonst lädt X11 ihn gar nicht.
                if schema_id == self.INTERFACE and key == "cursor-theme":
                    _spiegele_cursor_in_pfad(wert.get_string())
                    _schreibe_default_cursor(wert.get_string())
            except (GLib.Error, TypeError, ValueError):
                continue  # beschädigter oder unpassender Eintrag -> überspringen

        # Nach dem Wiederherstellen den libadwaita-Spiegel an das jetzt gesetzte
        # GTK-Design angleichen. Sonst zeigt Nautilus nach einem Profilwechsel
        # oder der Tag/Nacht-Automatik weiter das alte Design oder bleibt an
        # einem alten Spiegel kleben. Reiner Datei-Vorgang, läuft auch im
        # fensterlosen --apply-profile-Pfad ohne GTK.
        _spiegle_libadwaita(self.gtk_theme())

        # Lief Variety, würde es den gerade gesetzten Hintergrund beim nächsten
        # Login durch sein eigenes Bild ersetzen. Darum das Bild zusätzlich an
        # Variety übergeben, damit es dieses adoptiert und wieder auflegt.
        if variety.laeuft():
            uri = self._background.get_string("picture-uri")
            if uri:
                pfad = Gio.File.new_for_uri(uri).get_path()
                if pfad and os.path.isfile(pfad):
                    variety.setze_wallpaper(pfad)
