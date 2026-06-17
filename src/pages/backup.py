"""Seite 'Sicherung'.

Drei Bereiche: die automatisch angelegten Sicherungspunkte (vor riskanten
Design-Wechseln), das Sichern in eine frei wählbare Datei samt Wiederherstellen,
und der Export/Import eines kompletten Look-Pakets (.dmlook, inklusive der
Design- und Bilddateien).

Benannte Profile werden nicht mehr hier, sondern zentral auf der Looks-Seite
verwaltet. Gesichert werden in allen Fällen die dconf-Werte, nicht die Design-
oder Bilddateien selbst (außer beim .dmlook, das die Dateien mitnimmt).
"""

import os
import time

from gi.repository import Adw, Gtk

from src import compat
from src.core import backup, looksbundle, restorepoint
from src.i18n import _


class BackupPage(compat.PageBase):
    """Seite zum Sichern und Wiederherstellen der Einstellungen."""

    def __init__(self, settings):
        super().__init__(title=_("Backup"))
        self._settings = settings
        self._punkt_zeilen = []

        seite = Adw.PreferencesPage()
        seite.add(self._punkte_gruppe())
        seite.add(self._datei_gruppe())
        seite.add(self._look_paket_gruppe())

        # Toasts brauchen einen Overlay um den Seiteninhalt.
        self._toasts = Adw.ToastOverlay()
        self._toasts.set_child(seite)

        toolbar = compat.toolbar_view(
            top_bars=[Adw.HeaderBar()], content=self._toasts)
        self.set_child(toolbar)

        self._fuelle_punkte()

    # --- Sicherungspunkte (automatisch vor riskanten Wechseln) ---

    def _punkte_gruppe(self):
        self._punkt_gruppe = Adw.PreferencesGroup(
            title=_("Restore points"),
            description=_("Created automatically before every theme, cursor "
                          "or shell change, and before applying a look. "
                          "Restores the state from before."))
        return self._punkt_gruppe

    def _fuelle_punkte(self):
        """Baut die Liste der Sicherungspunkte neu auf."""
        for zeile in self._punkt_zeilen:
            self._punkt_gruppe.remove(zeile)
        self._punkt_zeilen = []

        punkte = restorepoint.liste()
        if not punkte:
            leer = Adw.ActionRow(
                title=_("No restore points yet"),
                subtitle=_("One is created as soon as you change a theme."))
            leer.set_sensitive(False)
            self._punkt_gruppe.add(leer)
            self._punkt_zeilen.append(leer)
            return

        for punkt in punkte:
            # Der Anlass wird beim Anlegen bereits übersetzt gespeichert.
            zeile = Adw.ActionRow(
                title=punkt["anlass"],
                subtitle=self._format_zeit(punkt["zeit"]))

            zurueck = Gtk.Button(label=_("Restore"))
            zurueck.set_valign(Gtk.Align.CENTER)
            zurueck.add_css_class("flat")
            zurueck.connect("clicked", self._on_punkt_anwenden, punkt["datei"])

            loeschen = Gtk.Button(icon_name="user-trash-symbolic")
            loeschen.set_valign(Gtk.Align.CENTER)
            loeschen.add_css_class("flat")
            loeschen.set_tooltip_text(_("Delete restore point"))
            loeschen.connect("clicked", self._on_punkt_loeschen, punkt["datei"])

            zeile.add_suffix(zurueck)
            zeile.add_suffix(loeschen)
            self._punkt_gruppe.add(zeile)
            self._punkt_zeilen.append(zeile)

    def _format_zeit(self, epoche):
        try:
            return time.strftime("%d.%m.%Y %H:%M", time.localtime(epoche))
        except (ValueError, OSError):
            return ""

    def _on_punkt_anwenden(self, _knopf, datei):
        if restorepoint.wende_an(self._settings, datei):
            self._melde_und_reload(_("Restore point applied."))
        else:
            self._melde(_("The restore point could not be read."))

    def _on_punkt_loeschen(self, _knopf, datei):
        restorepoint.loesche(datei)
        self._fuelle_punkte()
        self._melde(_("Restore point deleted."))

    # --- Sicherung in eine Datei ---

    def _datei_gruppe(self):
        gruppe = Adw.PreferencesGroup(
            title=_("Backup file"),
            description=_("Export the current state to a file or restore from "
                          "an earlier backup."))
        gruppe.add(self._zeile(
            _("Back up"), _("Export to a file"),
            "document-save-symbolic", self._on_sichern))
        gruppe.add(self._zeile(
            _("Restore"), _("Import from a file"),
            "document-open-symbolic", self._on_wiederherstellen))
        return gruppe

    def _zeile(self, titel, untertitel, icon_name, handler):
        """Eine Zeile mit Symbol, Beschriftung und Knopf rechts."""
        zeile = Adw.ActionRow(title=titel, subtitle=untertitel)
        zeile.add_prefix(Gtk.Image(icon_name=icon_name))

        knopf = Gtk.Button(label=titel + " …")
        knopf.set_valign(Gtk.Align.CENTER)
        knopf.connect("clicked", handler)
        zeile.add_suffix(knopf)
        zeile.set_activatable_widget(knopf)
        return zeile

    # --- Sichern ---

    def _on_sichern(self, _knopf):
        compat.save_file(
            self.get_root(), _("Back up settings"),
            "design-manager-backup.json", None, self._on_speicherziel)

    def _on_speicherziel(self, pfad):
        if not pfad:
            return
        try:
            backup.save_to_file(self._settings, pfad)
        except OSError as fehler:
            self._melde(_("Backup failed: {error}").format(
                error=fehler.strerror or _("Error")))
            return
        self._melde(_("Backed up: {file}").format(
            file=os.path.basename(pfad)))

    # --- Wiederherstellen ---

    def _on_wiederherstellen(self, _knopf):
        nur_json = Gtk.FileFilter()
        nur_json.set_name(_("Backups (*.json)"))
        nur_json.add_pattern("*.json")
        compat.open_file(self.get_root(), _("Restore backup"),
                         [nur_json], self._on_quelle)

    def _on_quelle(self, pfad):
        if not pfad:
            return
        try:
            erfolg = backup.load_from_file(self._settings, pfad)
        except (OSError, ValueError):
            self._melde(_("The file could not be read."))
            return
        if not erfolg:
            self._melde(_("That is not a valid backup."))
            return
        self._melde_und_reload(_("Restored."))

    # --- Look-Paket (.dmlook, inklusive Design-Dateien) ---

    def _look_paket_gruppe(self):
        gruppe = Adw.PreferencesGroup(
            title=_("Share look package"),
            description=_("Bundle the whole look as a .dmlook, including the "
                          "theme files and the wallpaper, or import such a "
                          "package."))
        gruppe.add(self._zeile(
            _("Export look"), _("Pack themes and image into a .dmlook"),
            "document-save-symbolic", self._on_look_export))
        gruppe.add(self._zeile(
            _("Import look"), _("Install and apply from a .dmlook"),
            "document-open-symbolic", self._on_look_import))
        return gruppe

    def _on_look_export(self, _knopf):
        compat.save_file(self.get_root(), _("Export look package"),
                         "my-look.dmlook", None, self._on_look_export_ziel)

    def _on_look_export_ziel(self, pfad):
        if not pfad:
            return
        try:
            looksbundle.exportiere(self._settings, pfad)
        except OSError as fehler:
            self._melde(_("Export failed: {error}").format(
                error=fehler.strerror or _("Error")))
            return
        self._melde(_("Look package saved: {file}").format(
            file=os.path.basename(pfad)))

    def _on_look_import(self, _knopf):
        nur = Gtk.FileFilter()
        nur.set_name(_("Look packages (*.dmlook)"))
        nur.add_pattern("*.dmlook")
        compat.open_file(self.get_root(), _("Import look package"),
                         [nur], self._on_look_import_quelle)

    def _on_look_import_quelle(self, pfad):
        if not pfad:
            return
        try:
            erfolg = looksbundle.importiere(self._settings, pfad)
        except OSError:
            self._melde(_("The look package could not be read."))
            return
        if not erfolg:
            self._melde(_("That is not a valid look package."))
            return
        self._melde_und_reload(_("Look package applied."))

    # --- Rückmeldung ---

    def _melde(self, text):
        self._toasts.add_toast(Adw.Toast(title=text))

    def _melde_und_reload(self, text):
        """Toast zeigen und alle Seiten neu bauen.

        Geht über das Fenster, weil ein Wiederherstellen mehrere Bereiche auf
        einmal ändert und auch diese Seite neu gebaut wird. Der Toast hängt am
        fensterweiten Overlay und überlebt den Neuaufbau; fällt das Fenster aus,
        bleibt der lokale Toast als Notnagel.
        """
        fenster = self.get_root()
        if fenster is not None and hasattr(fenster, "melde_und_reload"):
            fenster.melde_und_reload(text)
        else:
            self._melde(text)
