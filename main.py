#!/usr/bin/env python3
#
# Design Manager - GNOME appearance manager
# Copyright (C) 2026 simonlinuxcraft
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <https://www.gnu.org/licenses/>.
"""Einstiegspunkt der App.

Startet die Adw.Application und zeigt das Hauptfenster. Mehr passiert hier
bewusst nicht: die eigentliche Oberflaeche liegt in src/window.py.
"""

import os
import sys

import gi

# Vor dem Import der Bibliotheken muss feststehen, welche Version wir wollen.
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402  (Import erst nach require_version)

from src.window import MainWindow  # noqa: E402


# Pfad zum eigenen Stylesheet (silberne Optik), relativ zu dieser Datei.
STYLE_FILE = os.path.join(os.path.dirname(__file__), "src", "style.css")


# Eindeutige App-ID im Reverse-DNS-Stil. GNOME ordnet darüber das Fenster der
# passenden .desktop-Datei zu und zeigt deren Icon im Dock. Der Name muss zum
# Dateinamen der .desktop-Datei und zum installierten Icon passen.
APP_ID = "io.github.simonlinuxcraft.DesignManager"


class LinuxAnpassungApp(Adw.Application):
    """Die Anwendung selbst.

    Adw.Application übernimmt den App-Lebenszyklus (Start, Beenden) und bringt
    das libadwaita-Styling mit.
    """

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_startup(self):
        """Einmalig beim App-Start. Hier laden wir unser eigenes Stylesheet."""
        Adw.Application.do_startup(self)

        # Unter X11 bildet GTK die WM_CLASS aus dem Programmnamen. Ohne das hier
        # waere sie "main.py" und GNOME faende die .desktop-Datei nicht, das
        # Dock-Icon bliebe generisch. Mit der App-ID passt die Zuordnung.
        GLib.set_prgname(APP_ID)

        # Das Logo ist dunkles Anthrazit mit Chrom-Silber, dazu passt der
        # dunkle Modus. Darum fix auf dunkel, unabhaengig vom System.
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        self._load_styles()

    def _load_styles(self):
        """Liest src/style.css ein und legt es über das Standard-Theme."""
        provider = Gtk.CssProvider()
        provider.load_from_path(STYLE_FILE)

        # Knapp ÜBER USER-Priorität. GTK lädt ~/.config/gtk-4.0/gtk.css ebenfalls
        # mit USER-Priorität; das ist genau die Datei, in die der Design-Manager
        # ein gewähltes GTK-Design für libadwaita-Apps spiegelt (auch in dieses
        # Fenster). +1 sorgt dafür, dass unsere eigenen Regeln gleichrangige
        # Theme-Regeln schlagen, also überall dort, wo style.css eine Eigenschaft
        # explizit setzt (window.silber, Sidebar, Karten, Akzentpunkte). Achtung:
        # Eigenschaften, die style.css NICHT setzt (Farbe nackter Knöpfe/Labels),
        # erbt das Fenster weiter vom gespiegelten Theme. Das ist akzeptiert, rein
        # optisch; die Marke trägt über die explizit gesetzten Flächen.
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_USER + 1,
        )

    def do_activate(self):
        """Wird beim Start aufgerufen (und wenn die App erneut aktiviert wird).

        Wir verwenden ein eventuell schon offenes Fenster wieder, statt ein
        zweites aufzumachen.
        """
        window = self.props.active_window
        if not window:
            window = MainWindow(application=self)
            # Icon-Name = App-ID. Greift, sobald ein gleichnamiges Icon im
            # Theme installiert ist (siehe data/dev-install.sh). Das Dock-Icon
            # selbst zieht GNOME aus der .desktop-Datei.
            window.set_icon_name(APP_ID)
        window.present()


def _apply_profile_headless(argv):
    """Wendet ein Profil ohne Fenster an (für die Timer der Tag/Nacht-Automatik).

    Reiner dconf-Write über AppSettings, daher kein Display und kein GTK nötig.
    Ohne aktive Session-Bus-Adresse landen die Writes nicht im laufenden
    grafischen Login, darum vorher prüfen. Bei fehlendem oder kaputtem Profil
    passiert still nichts.
    """
    i = argv.index("--apply-profile")
    if i + 1 >= len(argv):
        return 2
    name = argv[i + 1]
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return 1
    from src.core import backup
    from src.core.settings import AppSettings
    try:
        backup.load_profile(AppSettings(), name)
    except (OSError, ValueError):
        return 1
    return 0


def main():
    # Headless-Modus für die Automatik-Timer, bevor irgendetwas GTK initialisiert.
    if "--apply-profile" in sys.argv:
        return _apply_profile_headless(sys.argv)
    app = LinuxAnpassungApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
