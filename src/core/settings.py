"""Wrapper um Gio.Settings.

Hier läuft die eigentliche Kommunikation mit GNOME. Gio.Settings schreibt
direkt in die dconf-Datenbank, also genau dorthin, wo GNOME seine
Einstellungen ablegt. Es ist kein Aufruf von "gsettings" per subprocess nötig.

Jeder Setter unten zeigt offen, welches *Schema* und welcher *Schlüssel*
hinter einer Einstellung steckt. Das ist der Kern, den die App im Grunde nur
hübsch verpackt.
"""

from gi.repository import Gio


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


class AppSettings:
    """Gebündelter Zugriff auf alle Einstellungen, die die App verändert.

    Wir halten pro Schema ein Gio.Settings-Objekt. Lesen geht über get_*,
    Schreiben über set_*; beides wirkt sofort und bleibt dauerhaft.
    """

    # Schema-Namen als Konstanten, damit sie nur an einer Stelle stehen.
    INTERFACE = "org.gnome.desktop.interface"
    BACKGROUND = "org.gnome.desktop.background"

    def __init__(self):
        # Diese beiden Schemas sind auf jedem GNOME-System vorhanden.
        self._interface = Gio.Settings.new(self.INTERFACE)
        self._background = Gio.Settings.new(self.BACKGROUND)

    # --- GTK-Design (das Aussehen der App-Fenster) ---

    def gtk_theme(self):
        return self._interface.get_string("gtk-theme")

    def set_gtk_theme(self, name):
        self._interface.set_string("gtk-theme", name)

    # --- Symbol-Design (Icons) ---

    def icon_theme(self):
        return self._interface.get_string("icon-theme")

    def set_icon_theme(self, name):
        self._interface.set_string("icon-theme", name)

    # --- Mauszeiger ---

    def cursor_theme(self):
        return self._interface.get_string("cursor-theme")

    def set_cursor_theme(self, name):
        self._interface.set_string("cursor-theme", name)

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
