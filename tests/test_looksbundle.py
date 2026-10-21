"""Look-Paket-Export und -Import in einem Wegwerf-HOME.

    python3 tests/test_looksbundle.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile


def datei(pfad, inhalt=b"x"):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "wb") as f:
        f.write(inhalt)


def test_im_eigenen_prozess():
    # GLib legt Home- und Datenpfade beim ersten Zugriff fest.
    subprocess.run([sys.executable, os.path.abspath(__file__)], check=True)


def main():
    HOME = tempfile.mkdtemp(prefix="dm-test-look-")
    os.environ["HOME"] = HOME
    os.environ.pop("XDG_DATA_HOME", None)
    os.environ["LANGUAGE"] = "C"
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import gi
    gi.require_version("Gdk", "4.0")
    gi.require_version("GdkPixbuf", "2.0")
    from src.core import installer, looksbundle
    from src.core.settings import AppSettings

    class Einstellungen:
        INTERFACE = AppSettings.INTERFACE
        BACKGROUND = AppSettings.BACKGROUND
        USER_THEME = AppSettings.USER_THEME
        SAFE_GTK_THEME = SAFE_ICON_THEME = SAFE_CURSOR_THEME = "Adwaita"

        def gtk_theme(self):
            return "Mein"

        def shell_theme(self):
            return ""

        def icon_theme(self):
            return "Breezy"

        def cursor_theme(self):
            return ""

        def background_uri(self):
            return ""

        def export_settings(self):
            return {}

    # Icon-Design mit Ordner-Link (wie 24x24@2x bei Breeze) und Datei-Link.
    breezy = os.path.join(installer.ICONS_DIR, "Breezy")
    datei(os.path.join(breezy, "index.theme"))
    datei(os.path.join(breezy, "48x48", "apps", "a.svg"), b"<svg/>")
    os.symlink("48x48", os.path.join(breezy, "24x24@2x"))
    os.symlink("a.svg", os.path.join(breezy, "48x48", "apps", "b.svg"))
    # GTK-Design als Link auf einen Ordner mit anderem Namen (git-Checkout).
    echt = os.path.join(HOME, "git", "mein-theme")
    datei(os.path.join(echt, "gtk-3.0", "gtk.css"), b"neu")
    os.makedirs(installer.THEMES_DIR)
    os.symlink(echt, os.path.join(installer.THEMES_DIR, "Mein"))

    look = os.path.join(HOME, "x.dmlook")
    looksbundle.exportiere(Einstellungen(), look)
    namen = zipfile.ZipFile(look).namelist()
    assert "themes/Mein/gtk-3.0/gtk.css" in namen, namen
    assert "icons/Breezy/24x24@2x" in namen, namen

    # Import in ein Home, in dem schon ein anderes "Mein" liegt.
    shutil.rmtree(breezy)
    os.unlink(os.path.join(installer.THEMES_DIR, "Mein"))
    datei(os.path.join(installer.THEMES_DIR, "Mein", "gtk-3.0", "gtk.css"), b"alt")
    looksbundle.entpacke(look)
    with open(os.path.join(installer.THEMES_DIR, "Mein", "gtk-3.0", "gtk.css"), "rb") as f:
        assert f.read() == b"neu"
    papierkorb = os.path.join(HOME, ".local", "share", "Trash", "files")
    with open(os.path.join(papierkorb, "Mein", "gtk-3.0", "gtk.css"), "rb") as f:
        assert f.read() == b"alt"  # das alte liegt im Papierkorb, nicht weg
    link = os.path.join(installer.ICONS_DIR, "Breezy", "24x24@2x")
    assert os.path.islink(link) and os.readlink(link) == "48x48"
    assert os.path.isfile(os.path.join(link, "apps", "b.svg"))

    # Eine fremde Hintergrund-URI aus dem Manifest wird nie gesetzt.
    bereinigt = looksbundle._bereinige_themes(Einstellungen(), {
        AppSettings.BACKGROUND: {"picture-uri": "'file:///etc/passwd'",
                                 "picture-uri-dark": "'smb://x/y.png'",
                                 "picture-options": "'zoom'"},
        "kaputt": "kein dict"})
    assert bereinigt == {AppSettings.BACKGROUND: {"picture-options": "'zoom'"}}, bereinigt

    shutil.rmtree(HOME)
    print("looksbundle ok")


if __name__ == "__main__":
    main()
