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
import re
import subprocess
import sys
import urllib.parse

import gi

# Vor dem Import der Bibliotheken muss feststehen, welche Version wir wollen.
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402  (Import erst nach require_version)

from src import i18n  # noqa: F401, E402  (initialisiert gettext vor allen anderen src-Modulen)

from src.window import MainWindow  # noqa: E402


# Pfad zum eigenen Stylesheet (silberne Optik), relativ zu dieser Datei.
STYLE_FILE = os.path.join(os.path.dirname(__file__), "src", "style.css")

ADW_STYLESHEET = "/org/gnome/Adwaita/styles/gtk.css"

# Eigene Symbolics als hicolor-Rückfall, falls das gewählte Icon-Design sie
# nicht hat und nicht von Adwaita erbt (z.B. Stylish, breeze).
ICON_DIR = os.path.join(os.path.dirname(__file__), "data", "icons")


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

        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(
            ICON_DIR)
        lade_styles(Gdk.Display.get_default())

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


def lade_styles(display):
    """Das App-Fenster gegen das gewählte GTK-Design abschirmen, dann Silber.

    GTK lädt ~/.config/gtk-4.0/gtk.css mit USER-Priorität. Genau dorthin spiegelt
    die App das gewählte GTK-Design für libadwaita-Apps, und es wirkte damit auch
    in diesem Fenster: ein helles Design wie Orchis machte es unlesbar (helle
    Flächen, dunkle Schrift auf dunklen Karten). Darum darüber, nur in diesem
    Prozess: (1) jede Eigenschaft, die das Nutzer-CSS setzt, auf "unset",
    (2) libadwaitas eigenes Stylesheet neu, (3) unser Silber-Look. Andere Apps
    bekommen das gewählte Design weiter wie gewollt.
    """
    oben = Gtk.STYLE_PROVIDER_PRIORITY_USER
    try:
        # Ab libadwaita 1.6 ein einziges Stylesheet (hell/dunkel per @media).
        Gio.resources_get_info(ADW_STYLESHEET, Gio.ResourceLookupFlags.NONE)
    except GLib.Error:
        pass  # ponytail: ältere libadwaita hat getrennte Dateien, dort scheint das Design weiter durch
    else:
        reset = Gtk.CssProvider()
        # Unbekannte Eigenschaften im Fremd-Theme hat GTK beim Original schon
        # gemeldet; beim Zurücksetzen nicht noch einmal.
        reset.connect("parsing-error",
                      lambda p, *_a: p.stop_emission_by_name("parsing-error"))
        _lade_css_text(reset, _nutzer_css_reset())
        Gtk.StyleContext.add_provider_for_display(display, reset, oben + 1)
        # Die App läuft immer dunkel: die Dunkel-Blöcke (@media prefers-color-
        # scheme: dark) zusätzlich bedingungslos anhängen. Sonst griffen für
        # Farben, die style.css nicht selbst setzt (z.B. sidebar_fg_color), die
        # hellen Grundwerte, dunkle Schrift in der Seitenleiste.
        text = Gio.resources_lookup_data(
            ADW_STYLESHEET, Gio.ResourceLookupFlags.NONE).get_data().decode()
        dunkel = "\n".join(_media_inhalte(text, "prefers-color-scheme: dark"))
        grundstil = Gtk.CssProvider()
        _lade_css_text(grundstil, text + "\n" + dunkel)
        Gtk.StyleContext.add_provider_for_display(display, grundstil, oben + 2)

    provider = Gtk.CssProvider()
    provider.load_from_path(STYLE_FILE)
    Gtk.StyleContext.add_provider_for_display(display, provider, oben + 3)


def _lade_css_text(provider, text):
    if hasattr(provider, "load_from_string"):  # GTK 4.12+
        provider.load_from_string(text)
    else:
        provider.load_from_data(text, -1)


def _nutzer_css_reset():
    """CSS, das jede vom Nutzer-CSS gesetzte Eigenschaft wieder auf unset setzt."""
    pfad = os.path.join(GLib.get_user_config_dir(), "gtk-4.0", "gtk.css")
    zeilen = []
    for selektor, namen in _css_regeln(pfad, set()):
        if namen:
            zeilen.append("%s { %s }" % (
                selektor, " ".join(n + ": unset;" for n in sorted(namen))))
    return "\n".join(zeilen)


def _css_regeln(pfad, gesehen):
    """(Selektor, Eigenschaftsnamen) aller Regeln einer CSS-Datei, samt @import."""
    real = os.path.realpath(pfad)
    if real in gesehen or not os.path.isfile(real):
        return []
    gesehen.add(real)
    try:
        with open(real, encoding="utf-8", errors="replace") as f:
            text = re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)
    except OSError:
        return []
    regeln = []
    for ziel in re.findall(r"""@import\s+(?:url\()?\s*["']?([^"')\s;]+)""", text):
        if ziel.startswith("file://"):
            ziel = urllib.parse.unquote(ziel[len("file://"):])
        elif "://" in ziel:
            continue  # resource:// u.ä. gehört nicht zum Fremd-Theme
        regeln += _css_regeln(os.path.join(os.path.dirname(real), ziel), gesehen)
    return regeln + _css_bloecke(text)


def _media_inhalte(text, bedingung):
    """Inhalt aller @media-Blöcke, deren Bedingung 'bedingung' enthält."""
    inhalte = []
    for treffer in re.finditer(r"@media[^{]*" + re.escape(bedingung) + r"[^{]*\{",
                               text):
        tiefe, zu = 1, treffer.end()
        while tiefe and zu < len(text):
            tiefe += {"{": 1, "}": -1}.get(text[zu], 0)
            zu += 1
        inhalte.append(text[treffer.end():zu - 1])
    return inhalte


def _css_bloecke(text):
    """Regeln aus CSS-Text; @media wird aufgeklappt, andere @-Blöcke übersprungen."""
    regeln, start, i = [], 0, 0
    while True:
        auf = text.find("{", i)
        if auf < 0:
            return regeln
        tiefe, zu = 1, auf + 1
        while tiefe and zu < len(text):
            tiefe += {"{": 1, "}": -1}.get(text[zu], 0)
            zu += 1
        kopf = text[start:auf].split(";")[-1].strip()
        rumpf = text[auf + 1:zu - 1]
        if kopf.startswith("@media"):
            regeln += _css_bloecke(rumpf)
        elif kopf and not kopf.startswith("@"):
            namen = {n for n in re.findall(r"(?:^|;)\s*([-\w]+)\s*:", rumpf)
                     if not n.startswith("--")}
            regeln.append((kopf, namen))
        start = i = zu


def _software_gl():
    """True, wenn die GL-Wiedergabe in Software läuft (kein Hardware-Treiber).

    Erst GL direkt fragen (genauester Hinweis: meldet der Renderer llvmpipe/
    softpipe/swrast?). Fehlt glxinfo, gilt eine VM als Software-GL-Verdacht.
    """
    try:
        ausgabe = subprocess.run(
            ["glxinfo", "-B"], capture_output=True, text=True, timeout=2).stdout
        if ausgabe:
            return any(s in ausgabe.lower()
                       for s in ("llvmpipe", "softpipe", "swrast"))
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        return subprocess.run(
            ["systemd-detect-virt", "--quiet"], timeout=2).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _waehle_renderer():
    """Auf Systemen ohne brauchbare GPU den Cairo-Renderer erzwingen.

    GTK4 nutzt ab 4.14 standardmäßig den GL-Renderer. Auf Software-GL (llvmpipe,
    typisch in VMs) hängt der oder zeichnet eigene DrawingAreas leer (etwa die
    Shell-Vorschaukarten). Cairo zeichnet rein in Software, ist dort nicht
    langsamer und immer korrekt. Echte GPUs behalten den schnellen GL-Renderer.
    Eine vom Nutzer/System gesetzte GSK_RENDERER-Wahl bleibt unangetastet.
    """
    if os.environ.get("GSK_RENDERER"):
        return
    if _software_gl():
        os.environ["GSK_RENDERER"] = "cairo"
        print("Design Manager: Software-GL erkannt, nutze GSK_RENDERER=cairo.",
              file=sys.stderr)


def main():
    # Renderer-Wahl vor dem ersten Fenster (GTK legt den Renderer beim
    # Realisieren der ersten Oberfläche an, danach wirkt GSK_RENDERER nicht mehr).
    _waehle_renderer()
    app = LinuxAnpassungApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
