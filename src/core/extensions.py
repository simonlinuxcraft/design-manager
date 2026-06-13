"""GNOME-Shell-Erweiterungen auflisten und schalten.

Wir sprechen denselben D-Bus-Dienst an wie GNOMEs eigene Erweiterungen-App:
org.gnome.Shell.Extensions. Daraus holen wir die Liste samt Status und schalten
einzelne Erweiterungen live an oder aus. Ein globaler Schalter sitzt dagegen im
GSettings-Schlüssel org.gnome.shell/disable-user-extensions.

Hinweis: Im Snap-Strict-Confinement ist dieser D-Bus-Dienst gesperrt. Darum
prüft verfuegbar(), ob er erreichbar ist; die Seite zeigt sonst einen Hinweis
statt zu scheitern.
"""

from gi.repository import Gio, GLib

from src.core.settings import schema_vorhanden


# Zustand einer Erweiterung (ExtensionState aus der GNOME-Shell). Für die UI
# brauchen wir vor allem ENABLED und ERROR.
STATE_ENABLED = 1
STATE_ERROR = 3

# Herkunft einer Erweiterung (ExtensionType).
TYPE_SYSTEM = 1
TYPE_USER = 2


class ShellExtensions:
    """Zugriff auf die installierten Shell-Erweiterungen über D-Bus."""

    BUS = "org.gnome.Shell.Extensions"
    PATH = "/org/gnome/Shell/Extensions"
    SHELL_SCHEMA = "org.gnome.shell"

    def __init__(self):
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
                self.BUS, self.PATH, self.BUS, None)
        except GLib.Error:
            self._proxy = None

        # Master-Schalter im Shell-Schema (auf GNOME vorhanden, defensiv geprüft).
        if schema_vorhanden(self.SHELL_SCHEMA):
            self._shell = Gio.Settings.new(self.SHELL_SCHEMA)
        else:
            self._shell = None

    def verfuegbar(self):
        """True, wenn der Erweiterungs-Dienst auf dem Bus erreichbar ist."""
        return self._proxy is not None and self._proxy.get_name_owner() is not None

    # --- Auflisten ---

    def list_extensions(self):
        """Alle Erweiterungen als Liste von Dicts, nach Name sortiert."""
        if self._proxy is None:
            return []
        try:
            ergebnis = self._proxy.call_sync(
                "ListExtensions", None, Gio.DBusCallFlags.NONE, -1, None)
        except GLib.Error:
            return []

        roh = ergebnis.unpack()[0]  # {uuid: {feld: wert}}
        eintraege = [self._eintrag(uuid, info) for uuid, info in roh.items()]
        eintraege.sort(key=lambda e: e["name"].lower())
        return eintraege

    def _eintrag(self, uuid, info):
        # Zahlenfelder kommen als double über D-Bus, daher int(...).
        return {
            "uuid": uuid,
            "name": info.get("name") or uuid,
            "description": info.get("description", ""),
            "enabled": bool(info.get("enabled", False)),
            "state": int(info.get("state", 0)),
            "type": int(info.get("type", 0)),
            "can_change": bool(info.get("canChange", True)),
            "has_prefs": bool(info.get("hasPrefs", False)),
            "error": info.get("error", ""),
        }

    # --- Schalten ---

    def enable(self, uuid):
        self._call("EnableExtension", uuid)

    def disable(self, uuid):
        self._call("DisableExtension", uuid)

    def open_prefs(self, uuid):
        self._call("LaunchExtensionPrefs", uuid)

    def _call(self, methode, uuid):
        if self._proxy is None:
            return
        try:
            self._proxy.call_sync(
                methode, GLib.Variant("(s)", (uuid,)),
                Gio.DBusCallFlags.NONE, -1, None)
        except GLib.Error:
            pass

    # --- Live-Aktualisierung ---

    def connect_state_changed(self, callback):
        """Verbindet callback(uuid, info) mit dem ExtensionStateChanged-Signal."""
        if self._proxy is not None:
            self._proxy.connect("g-signal", self._on_signal, callback)

    def _on_signal(self, _proxy, _sender, signal_name, params, callback):
        if signal_name == "ExtensionStateChanged":
            uuid, info = params.unpack()
            callback(uuid, info)

    # --- Globaler Schalter ---

    def user_extensions_enabled(self):
        """True, wenn Benutzer-Erweiterungen global erlaubt sind."""
        if self._shell is None:
            return True
        return not self._shell.get_boolean("disable-user-extensions")

    def set_user_extensions_enabled(self, an):
        if self._shell is not None:
            self._shell.set_boolean("disable-user-extensions", not an)
