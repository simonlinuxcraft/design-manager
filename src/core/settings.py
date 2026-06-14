"""Wrapper um Gio.Settings.

Hier läuft die eigentliche Kommunikation mit GNOME. Gio.Settings schreibt
direkt in die dconf-Datenbank, also genau dorthin, wo GNOME seine
Einstellungen ablegt. Es ist kein Aufruf von "gsettings" per subprocess nötig.

Jeder Setter unten zeigt offen, welches *Schema* und welcher *Schlüssel*
hinter einer Einstellung steckt. Das ist der Kern, den die App im Grunde nur
hübsch verpackt.
"""

import os

from gi.repository import GLib, Gio


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
        (INTERFACE, "color-scheme"),
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
        self._interface.set_string("gtk-theme", name)

    def reset_gtk_theme(self):
        """Setzt das GTK-Design auf das sichere Standard-Design (Adwaita).

        Notausstieg: ein kaputtes Design (ungültiges CSS) kann die ganze Sitzung
        lahmlegen. Adwaita ist in GTK eingebaut und immer gültig, darum als
        garantierter Rückfallwert.
        """
        self._interface.set_string("gtk-theme", self.SAFE_GTK_THEME)

    # --- Symbol-Design (Icons) ---

    def icon_theme(self):
        return self._interface.get_string("icon-theme")

    def set_icon_theme(self, name):
        self._interface.set_string("icon-theme", name)

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

    # --- Systemschriftart (z.B. "Cantarell 11") ---

    def font_name(self):
        return self._interface.get_string("font-name")

    def set_font_name(self, name):
        self._interface.set_string("font-name", name)

    # --- Hell-/Dunkel-Modus ---
    # color-scheme ist ein Enum-Schluessel. Als Text sind die Werte
    # "default", "prefer-dark" und "prefer-light".

    def color_scheme(self):
        return self._interface.get_string("color-scheme")

    def set_color_scheme(self, wert):
        self._interface.set_string("color-scheme", wert)

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
            daten.setdefault(schema_id, {})[key] = settings.get_value(key).print_(True)
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
