"""Silver Dock im Look: Schema aus dem Erweiterungsordner, Sicherung und Rückspielen.

Speicher-Backend und Wegwerf-HOME, dconf und die Dateien des Nutzers bleiben unberührt.

    python3 tests/test_erweiterungs_schluessel.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

HOME = tempfile.mkdtemp(prefix="dm-test-home-")
os.environ["HOME"] = HOME  # vor den src-Importen, die Pfade stehen zur Importzeit fest
os.environ["GSETTINGS_BACKEND"] = "memory"  # vor dem ersten Gio.Settings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gi.repository import Gio  # noqa: E402

from src.core import settings as modul  # noqa: E402
from src.core.settings import AppSettings  # noqa: E402

assert "Memory" in type(Gio.SettingsBackend.get_default()).__name__, "würde echte Einstellungen schreiben"

XML = """<schemalist>
  <schema id="%s" path="/org/gnome/shell/extensions/silver-dock/">
    <key name="design" type="s"><default>'silver'</default></key>
    <key name="colors" type="s"><default>'dock'</default></key>
    <key name="color" type="s"><default>'#1c1d21'</default></key>
  </schema>
</schemalist>
""" % AppSettings.SILVER_DOCK

schemas = os.path.join(HOME, "schemas")
os.makedirs(schemas)
with open(os.path.join(schemas, "x.gschema.xml"), "w") as f:
    f.write(XML)
subprocess.run(["glib-compile-schemas", schemas], check=True)

assert modul.erweiterungs_settings("x", AppSettings.SILVER_DOCK, ordner=[HOME]) is None, "ohne Schema kein Settings"
dock = modul.erweiterungs_settings("x", AppSettings.SILVER_DOCK, ordner=[schemas])
assert dock is not None, "Schema im Erweiterungsordner nicht gefunden"

modul._spiegle_libadwaita = lambda *_: None  # schreibt sonst nach ~/.config/gtk-4.0
app = AppSettings()
app._nach_schema[AppSettings.SILVER_DOCK] = dock

dock.set_string("design", "haiku")
dock.set_string("colors", "custom")
dock.set_string("color", "#d8d8d8")
look = app.export_settings()
assert look[AppSettings.SILVER_DOCK] == {"design": "'haiku'", "colors": "'custom'", "color": "'#d8d8d8'"}, look

dock.set_string("design", "silver")
dock.set_string("colors", "dock")
app.import_settings(look)
assert (dock.get_string("design"), dock.get_string("colors"), dock.get_string("color")) == \
    ("haiku", "custom", "#d8d8d8"), "Look hat das Dock nicht mitgeschaltet"

# Ein Look ohne Dock-Teil (älter oder von einem anderen System) lässt das Dock in Ruhe.
app.import_settings({"org.gnome.desktop.interface": {"icon-theme": "'Adwaita'"}})
assert dock.get_string("design") == "haiku", "Look ohne Dock-Teil hat das Dock verändert"

shutil.rmtree(HOME)
print("erweiterungs_schluessel ok")
