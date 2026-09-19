"""Ablage-Hinweis zum Installieren neuer Designs/Schriften.

Eine gestrichelte Fläche mit Hinweis, einem Knopf für den Dateidialog und
einem für einen gnome-look-Link (siehe MainWindow.frage_gnomelook_link). Das
Ziehen selbst nimmt das ganze Fenster an (siehe MainWindow._drop_flaeche); die
Fläche leuchtet dabei per CSS mit auf. Was installiert wird, erkennt der
Installer selbst, egal auf welcher Seite die Datei landet.
"""

from gi.repository import Gio, Gtk

from src import compat
from src.core import backgrounds, installer
from src.i18n import _


class InstallDropzone(Gtk.Box):
    """Hinweis-Fläche + Auswahl-Knopf zum Installieren."""

    def __init__(self, hinweis=None):
        if hinweis is None:
            hinweis = _("Drag an archive, a folder or a font here")
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("dropzone")
        self.set_margin_top(6)

        icon = Gtk.Image.new_from_icon_name("folder-download-symbolic")
        icon.set_pixel_size(24)
        icon.set_halign(Gtk.Align.CENTER)
        self.append(icon)

        label = Gtk.Label(label=hinweis)
        label.set_halign(Gtk.Align.CENTER)
        label.set_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        self.append(label)

        knopf = Gtk.Button(label=_("Choose file…"))
        knopf.connect("clicked", self._on_waehlen)
        gnomelook = Gtk.Button(label=_("From gnome-look.org…"))
        gnomelook.set_tooltip_text(_("Install from a link. The app then keeps "
                                     "the theme up to date."))
        gnomelook.connect("clicked", lambda _k: self.get_root()
                          .frage_gnomelook_link())
        knoepfe = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        knoepfe.append(knopf)
        knoepfe.append(gnomelook)
        self.append(knoepfe)

    def _on_waehlen(self, _knopf):
        filter_ = Gtk.FileFilter()
        filter_.set_name(_("Themes, fonts, images and look packages"))
        endungen = (installer.ARCHIV_ENDUNGEN + installer.SCHRIFT_ENDUNGEN
                    + backgrounds.ENDUNGEN + (".dmlook",))
        for endung in endungen:
            filter_.add_suffix(endung[1:])
        compat.open_file(self.get_root(), _("Choose theme or font"),
                         [filter_], self._on_pfad)

    def _on_pfad(self, pfad):
        fenster = self.get_root()
        if pfad and hasattr(fenster, "installiere_dateien"):
            fenster.installiere_dateien([Gio.File.new_for_path(pfad)])
