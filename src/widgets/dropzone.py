"""Ablage zum Installieren neuer Designs/Schriften per Drag & Drop.

Eine gestrichelte Fläche, auf die man ein Archiv (.tar.gz/.zip) ziehen kann;
alternativ öffnet ein Knopf einen Dateiauswahl-Dialog. Das eigentliche
Entpacken läuft in einem Hintergrund-Thread (kann bei großen Archiven dauern),
das Ergebnis meldet die Dropzone an das Hauptfenster (Toast + Liste neu laden).
"""

import threading

from gi.repository import Gdk, GLib, Gtk

from src import compat
from src.core import installer
from src.i18n import _


class InstallDropzone(Gtk.Box):
    """Drop-Ziel + Auswahl-Knopf zum Installieren von Designs und Schriften."""

    def __init__(self, hinweis=None, erwartet=None):
        if hinweis is None:
            hinweis = _("Drag an archive (.tar.gz or .zip) here")
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("dropzone")
        self.set_margin_top(6)

        # Auf welche Design-Arten diese Ablage beschränkt ist (siehe
        # installer.install). None = alles annehmen.
        self._erwartet = erwartet

        icon = Gtk.Image.new_from_icon_name("folder-download-symbolic")
        icon.set_pixel_size(24)
        icon.set_halign(Gtk.Align.CENTER)
        self.append(icon)

        self._label = Gtk.Label(label=hinweis)
        self._label.set_halign(Gtk.Align.CENTER)
        self._label.set_wrap(True)
        self._label.set_justify(Gtk.Justification.CENTER)
        self.append(self._label)

        knopf = Gtk.Button(label=_("Choose file…"))
        knopf.set_halign(Gtk.Align.CENTER)
        knopf.connect("clicked", self._on_waehlen)
        self.append(knopf)

        # Drop-Ziel für Dateien. Gdk.FileList deckt das Ziehen aus dem
        # Dateimanager ab; wir nehmen die erste Datei.
        ziel = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        ziel.connect("drop", self._on_drop)
        self.add_controller(ziel)

    # --- Eingaben ---

    def _on_drop(self, _ziel, value, _x, _y):
        dateien = value.get_files()
        if not dateien:
            return False
        pfad = dateien[0].get_path()
        if pfad:
            self._starte(pfad)
        return True

    def _on_waehlen(self, _knopf):
        archive = Gtk.FileFilter()
        archive.set_name(_("Themes and fonts"))
        for muster in ("*.tar.gz", "*.tgz", "*.tar.xz", "*.tar.bz2", "*.zip",
                       "*.ttf", "*.otf", "*.ttc"):
            archive.add_pattern(muster)
        compat.open_file(self.get_root(), _("Choose theme or font"),
                         [archive], self._on_pfad)

    def _on_pfad(self, pfad):
        if pfad:
            self._starte(pfad)

    # --- Installation im Hintergrund ---

    def _starte(self, pfad):
        self._label.set_text(_("Installing…"))

        def worker():
            try:
                ergebnis = installer.install(pfad, self._erwartet)
                GLib.idle_add(self._fertig, ergebnis, None)
            except installer.InstallFehler as fehler:
                GLib.idle_add(self._fertig, None, str(fehler))
            except Exception:
                # Die Kopierphase (Platte voll, schreibgeschützte Reste) wirft
                # rohes OSError/shutil.Error außerhalb von InstallFehler. Ohne
                # diesen Fang stürbe der Worker still und das Label bliebe für
                # immer auf "Installing…". Lieber eine ehrliche Meldung.
                GLib.idle_add(self._fertig, None,
                              _("Installation failed unexpectedly."))

        threading.Thread(target=worker, daemon=True).start()

    def _fertig(self, ergebnis, fehler):
        # Das Hauptfenster zeigt die Meldung als Toast und lädt die aktive Seite
        # neu, damit ein neues Design sofort in der Liste auftaucht.
        fenster = self.get_root()
        if fenster is not None and hasattr(fenster, "melde_installation"):
            fenster.melde_installation(ergebnis, fehler)
        else:
            # Fallback, falls die Dropzone (noch) nicht im Fenster hängt.
            self._label.set_text(
                _("Failed: {error}").format(error=fehler) if fehler
                else _("Installed: {items}").format(
                    items=", ".join(ergebnis)))
        return False
