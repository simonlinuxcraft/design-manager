"""Einstellungen für das Dock bzw. die Taskleiste.

Steuert die auf dem System aktive Dock-Erweiterung. Zwei werden unterstützt:

  - Ubuntu Dock / Dash to Dock (Schema org.gnome.shell.extensions.dash-to-dock).
    Ubuntu Dock ist ein Dash-to-Dock-Ableger und nutzt dasselbe Schema; auf
    Ubuntu liegt es im System-Schemapfad und ist direkt ladbar.
  - Dash to Panel (Schema org.gnome.shell.extensions.dash-to-panel). Dessen
    Schema liegt anders als die GNOME-Standardschemas meist nicht im
    System-Schemapfad, sondern im schemas/-Ordner der Erweiterung. Wir laden es
    darum über eine eigene SettingsSchemaSource aus diesem Ordner.

Sind beide eingeschaltet, hat Dash to Panel Vorrang, weil es das Dock ersetzt.
Ist keine aktiv, liefert aktives_dock() None und die Seite zeigt einen Hinweis.

Nach außen reicht das Modul eine Liste einheitlicher Einstellungs-Objekte
(Schalter, Auswahl, Regler), damit die Seite sie rendern kann, ohne zu wissen,
welche Erweiterung dahinter steckt. Die unterschiedlichen Schlüssel (boolesche
Schalter, Enums, und bei Dash to Panel die JSON-codierten Pro-Monitor-Werte)
versteckt jeweils eine Lese-/Schreib-Closure.
"""

import json
import os

from gi.repository import Gio

from src.core.settings import schema_vorhanden


DASH_TO_DOCK_SCHEMA = "org.gnome.shell.extensions.dash-to-dock"
DASH_TO_PANEL_SCHEMA = "org.gnome.shell.extensions.dash-to-panel"

DASH_TO_PANEL_UUID = "dash-to-panel@jderose9.github.com"
UBUNTU_DOCK_UUID = "ubuntu-dock@ubuntu.com"
DASH_TO_DOCK_UUID = "dash-to-dock@micxgx.gmail.com"

# Orte, an denen die Schema-Dateien einer Erweiterung liegen können.
EXTENSION_DIRS = [
    os.path.expanduser("~/.local/share/gnome-shell/extensions"),
    "/usr/share/gnome-shell/extensions",
]

# Bildschirmkanten, einheitlich für beide Docks (Dash to Panel kennt keine
# eigene Reihenfolge, Dash to Dock per Enum LEFT/RIGHT/TOP/BOTTOM).
KANTEN = [("LEFT", "Links"), ("RIGHT", "Rechts"),
          ("TOP", "Oben"), ("BOTTOM", "Unten")]


# --- Einheitliches Einstellungs-Modell ---

ART_SCHALTER = "schalter"
ART_AUSWAHL = "auswahl"
ART_REGLER = "regler"


class Einstellung:
    """Ein einzelner Dock-Schalter, eine Auswahl oder ein Regler.

    'lesen' gibt den aktuellen Wert zurück, 'schreiben' setzt ihn. Bei einer
    Auswahl hält 'optionen' Paare (wert, anzeige); bei einem Regler hält
    'spanne' das Tripel (min, max, schritt).
    """

    def __init__(self, art, titel, untertitel, lesen, schreiben,
                 optionen=None, spanne=None):
        self.art = art
        self.titel = titel
        self.untertitel = untertitel
        self.lesen = lesen
        self.schreiben = schreiben
        self.optionen = optionen or []
        self.spanne = spanne


class Dock:
    """Das aktive Dock: ein Anzeigename und seine Einstellungen."""

    def __init__(self, name, einstellungen):
        self.name = name
        self.einstellungen = einstellungen


# --- Bausteine für einfache (nicht JSON-codierte) Schlüssel ---

def _schalter(s, key, titel, untertitel):
    return Einstellung(ART_SCHALTER, titel, untertitel,
                       lambda: s.get_boolean(key),
                       lambda w: s.set_boolean(key, bool(w)))


def _auswahl(s, key, titel, untertitel, optionen):
    return Einstellung(ART_AUSWAHL, titel, untertitel,
                       lambda: s.get_string(key),
                       lambda w: s.set_string(key, w),
                       optionen=optionen)


def _regler(s, key, titel, untertitel, spanne):
    return Einstellung(ART_REGLER, titel, untertitel,
                       lambda: s.get_int(key),
                       lambda w: s.set_int(key, int(w)),
                       spanne=spanne)


# --- Erkennung des aktiven Docks ---

def _enabled_extensions():
    if not schema_vorhanden("org.gnome.shell"):
        return set()
    return set(Gio.Settings.new("org.gnome.shell").get_strv("enabled-extensions"))


def _panel_schema_dir():
    """Ordner mit dem (kompilierten) Dash-to-Panel-Schema, oder None."""
    for basis in EXTENSION_DIRS:
        d = os.path.join(basis, DASH_TO_PANEL_UUID, "schemas")
        if os.path.isfile(os.path.join(d, "gschemas.compiled")):
            return d
    return None


def _panel_settings():
    """Gio.Settings für Dash to Panel (Schema aus dem Erweiterungsordner)."""
    d = _panel_schema_dir()
    if d is None:
        return None
    quelle = Gio.SettingsSchemaSource.new_from_directory(
        d, Gio.SettingsSchemaSource.get_default(), False)
    schema = quelle.lookup(DASH_TO_PANEL_SCHEMA, False)
    if schema is None:
        return None
    return Gio.Settings.new_full(schema, None, None)


def aktives_dock():
    """Das aktive Dock als Dock-Objekt, oder None, wenn keines erkannt wird.

    Vorrang hat die tatsächlich eingeschaltete Erweiterung, Dash to Panel vor
    Dash to Dock. Ist nichts als eingeschaltet erkennbar (z.B. enabled-extensions
    nicht lesbar), nehmen wir, was installiert vorliegt.
    """
    enabled = _enabled_extensions()
    panel_an = DASH_TO_PANEL_UUID in enabled
    dock_an = bool(enabled & {UBUNTU_DOCK_UUID, DASH_TO_DOCK_UUID})

    panel_s = _panel_settings()
    dock_da = schema_vorhanden(DASH_TO_DOCK_SCHEMA)

    if panel_an and panel_s is not None:
        return _panel_dock(panel_s)
    if dock_an and dock_da:
        return _dtd_dock(Gio.Settings.new(DASH_TO_DOCK_SCHEMA))
    # Nichts eindeutig eingeschaltet: nimm das Installierte (Panel zuerst).
    if panel_s is not None:
        return _panel_dock(panel_s)
    if dock_da:
        return _dtd_dock(Gio.Settings.new(DASH_TO_DOCK_SCHEMA))
    return None


# --- Ubuntu Dock / Dash to Dock ---

def _dtd_dock(s):
    e = [
        _auswahl(s, "dock-position", "Position",
                 "Bildschirmrand, an dem das Dock sitzt", KANTEN),
        _schalter(s, "dock-fixed", "Immer sichtbar",
                  "Dock am Rand fixieren, statt es auszublenden"),
        _schalter(s, "autohide", "Automatisch ausblenden",
                  "Dock verbergen, bis der Zeiger den Rand berührt"),
        _schalter(s, "intellihide", "Intelligent ausblenden",
                  "Nur ausblenden, wenn ein Fenster das Dock überdeckt"),
        _regler(s, "dash-max-icon-size", "Symbolgröße",
                "Maximale Größe der App-Symbole in Pixeln", (16, 64, 2)),
        _schalter(s, "extend-height", "Über volle Höhe",
                  "Dock über die ganze Bildschirmkante ziehen (Panel-Stil)"),
        _schalter(s, "show-apps-at-top", "Apps-Knopf oben",
                  "Den Anwendungen-Knopf an den Anfang setzen"),
        _schalter(s, "show-mounts", "Laufwerke zeigen",
                  "Eingehängte Datenträger im Dock anzeigen"),
        _schalter(s, "show-trash", "Papierkorb zeigen",
                  "Den Papierkorb im Dock anzeigen"),
        _schalter(s, "multi-monitor", "Auf allen Monitoren",
                  "Dock auf jedem Bildschirm anzeigen"),
    ]
    return Dock("Ubuntu Dock", e)


# --- Dash to Panel (JSON-codierte Pro-Monitor-Werte) ---

def _json_dict(s, key):
    try:
        wert = json.loads(s.get_string(key) or "{}")
        return wert if isinstance(wert, dict) else {}
    except (ValueError, TypeError):
        return {}


def _monitor_keys(s):
    """Monitor-Bezeichner, die Dash to Panel kennt (aus seinen JSON-Schlüsseln).

    panel-positions kann leer sein; die Bezeichner stehen dann noch in
    panel-sizes/panel-lengths. Wir sammeln aus allen, um auch Schlüssel setzen
    zu können, deren eigenes JSON gerade leer ist.
    """
    keys = set()
    for key in ("panel-sizes", "panel-positions", "panel-lengths"):
        keys |= set(_json_dict(s, key).keys())
    return keys


def _json_einheitlich(s, key, default):
    """Gemeinsamer Wert über alle Monitore, sonst der erste, sonst default."""
    werte = list(_json_dict(s, key).values())
    if werte and all(w == werte[0] for w in werte):
        return werte[0]
    return werte[0] if werte else default


def _json_alle_setzen(s, key, wert):
    """Schreibt 'wert' für jeden bekannten Monitor in das JSON von 'key'."""
    monitore = _monitor_keys(s)
    if not monitore:
        return  # ohne bekannte Monitore keine sinnvolle Zuordnung
    d = _json_dict(s, key)
    for m in monitore:
        d[m] = wert
    s.set_string(key, json.dumps(d))


def _panel_position(s):
    return Einstellung(
        ART_AUSWAHL, "Position", "Bildschirmrand, an dem das Panel sitzt",
        lambda: _json_einheitlich(s, "panel-positions", "TOP"),
        lambda w: _json_alle_setzen(s, "panel-positions", w),
        optionen=KANTEN)


def _panel_hoehe(s):
    return Einstellung(
        ART_REGLER, "Panel-Höhe", "Dicke der Leiste in Pixeln",
        lambda: int(_json_einheitlich(s, "panel-sizes", 48)),
        lambda w: _json_alle_setzen(s, "panel-sizes", int(w)),
        spanne=(24, 96, 2))


def _panel_dock(s):
    e = [
        _panel_position(s),
        _panel_hoehe(s),
        _auswahl(s, "dot-position", "Indikator-Position",
                 "Wo der Punkt offener Programme sitzt",
                 [("BOTTOM", "Unten"), ("TOP", "Oben"),
                  ("LEFT", "Links"), ("RIGHT", "Rechts")]),
        _schalter(s, "group-apps", "Fenster gruppieren",
                  "Mehrere Fenster eines Programms zu einem Symbol bündeln"),
        _schalter(s, "show-favorites", "Favoriten zeigen",
                  "Angeheftete Programme in der Leiste anzeigen"),
        _schalter(s, "isolate-workspaces", "Arbeitsflächen trennen",
                  "Nur Fenster der aktuellen Arbeitsfläche anzeigen"),
        _schalter(s, "intellihide", "Automatisch ausblenden",
                  "Panel verbergen, bis es gebraucht wird"),
        _schalter(s, "multi-monitors", "Auf allen Monitoren",
                  "Panel auf jedem Bildschirm anzeigen"),
    ]
    return Dock("Dash to Panel", e)
