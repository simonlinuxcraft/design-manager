"""Seite 'Sicherung'.

Oben die Profile: benannte Sets der aktuellen Einstellungen, zwischen denen man
per Klick wechseln kann (z.B. ein "Tag"- und ein "Nacht"-Look). Darunter die
Sicherung in eine frei wählbare Datei und das Wiederherstellen daraus.

Gesichert werden in beiden Fällen die dconf-Werte, nicht die Design- oder
Bilddateien selbst.
"""

import os
import time

from gi.repository import Adw, Gtk

from src import compat
from src.core import backup, looksbundle, restorepoint, schedule
from src.i18n import _


class BackupPage(compat.PageBase):
    """Seite zum Sichern und Wiederherstellen der Einstellungen."""

    def __init__(self, settings):
        super().__init__(title=_("Backup"))
        self._settings = settings
        self._profil_zeilen = []
        self._punkt_zeilen = []
        self._auto_zeilen = []

        seite = Adw.PreferencesPage()
        seite.add(self._profil_eingabe_gruppe())
        seite.add(self._profil_liste_gruppe())
        seite.add(self._automatik_gruppe())
        seite.add(self._punkte_gruppe())
        seite.add(self._datei_gruppe())
        seite.add(self._look_paket_gruppe())

        # Toasts brauchen einen Overlay um den Seiteninhalt.
        self._toasts = Adw.ToastOverlay()
        self._toasts.set_child(seite)

        toolbar = compat.toolbar_view(
            top_bars=[Adw.HeaderBar()], content=self._toasts)
        self.set_child(toolbar)

        self._fuelle_profile()
        self._fuelle_automatik()
        self._fuelle_punkte()

    # --- Profile ---

    def _profil_eingabe_gruppe(self):
        """Eingabezeile zum Anlegen eines Profils aus dem aktuellen Stand."""
        gruppe = Adw.PreferencesGroup(
            title=_("Profiles"),
            description=_("Save the current state as a named set and reapply "
                          "it with a click. Saved profiles also appear on the "
                          "Looks page."))
        self._name_entry = compat.EntryRow(title=_("Name a new profile"))
        self._name_entry.set_show_apply_button(True)
        self._name_entry.connect("apply", self._on_profil_speichern)
        gruppe.add(self._name_entry)
        return gruppe

    def _profil_liste_gruppe(self):
        self._profil_gruppe = Adw.PreferencesGroup(title=_("Saved profiles"))
        return self._profil_gruppe

    def _fuelle_profile(self):
        """Baut die Profilliste neu auf (nach Anlegen oder Löschen)."""
        for zeile in self._profil_zeilen:
            self._profil_gruppe.remove(zeile)
        self._profil_zeilen = []

        namen = backup.list_profiles()
        if not namen:
            leer = Adw.ActionRow(
                title=_("No profiles yet"),
                subtitle=_("Enter a name above and save."))
            leer.set_sensitive(False)
            self._profil_gruppe.add(leer)
            self._profil_zeilen.append(leer)
            return

        for name in namen:
            zeile = Adw.ActionRow(title=name)

            anwenden = Gtk.Button(label=_("Apply"))
            anwenden.set_valign(Gtk.Align.CENTER)
            anwenden.add_css_class("flat")
            anwenden.connect("clicked", self._on_profil_anwenden, name)

            loeschen = Gtk.Button(icon_name="user-trash-symbolic")
            loeschen.set_valign(Gtk.Align.CENTER)
            loeschen.add_css_class("flat")
            loeschen.set_tooltip_text(_("Delete profile"))
            loeschen.connect("clicked", self._on_profil_loeschen, name)

            zeile.add_suffix(anwenden)
            zeile.add_suffix(loeschen)
            self._profil_gruppe.add(zeile)
            self._profil_zeilen.append(zeile)

    def _on_profil_speichern(self, entry):
        try:
            gespeichert = backup.save_profile(self._settings, entry.get_text())
        except ValueError:
            self._melde(_("Please enter a name."))
            return
        except OSError as fehler:
            self._melde(_("Saving failed: {error}").format(
                error=fehler.strerror or _("Error")))
            return
        entry.set_text("")
        self._fuelle_profile()
        self._fuelle_automatik()
        self._melde(_("Profile saved: {name}").format(name=gespeichert))

    def _on_profil_anwenden(self, _knopf, name):
        try:
            erfolg = backup.load_profile(self._settings, name)
        except (OSError, ValueError):
            self._melde(_("The profile could not be read."))
            return
        if not erfolg:
            self._melde(_("The profile is damaged."))
            return
        self._melde(_("Profile applied: {name}. Restart the app to refresh "
                      "the selection here.").format(name=name))

    def _on_profil_loeschen(self, _knopf, name):
        backup.delete_profile(name)
        self._fuelle_profile()
        self._fuelle_automatik()
        self._melde(_("Profile deleted: {name}").format(name=name))

    # --- Tag/Nacht-Automatik ---

    def _automatik_gruppe(self):
        self._auto_gruppe = Adw.PreferencesGroup(
            title=_("Day/night automation"),
            description=_("Bind two profiles to fixed times. Switches the "
                          "whole look automatically via a systemd timer."))
        return self._auto_gruppe

    def _fuelle_automatik(self):
        """Baut die Automatik-Zeilen neu auf (nach Profiländerung oder Refresh)."""
        for zeile in self._auto_zeilen:
            self._auto_gruppe.remove(zeile)
        self._auto_zeilen = []

        self._profil_namen = backup.list_profiles()
        if len(self._profil_namen) < 2:
            leer = Adw.ActionRow(
                title=_("Not enough profiles yet"),
                subtitle=_("Create two different profiles first (e.g. a light "
                           "\"Day\" and a dark \"Night\")."))
            leer.set_sensitive(False)
            self._auto_gruppe.add(leer)
            self._auto_zeilen.append(leer)
            return

        konfig = schedule.lese_konfig()
        self._auto_tag_combo = self._combo_zeile(
            _("Day profile"), konfig["tag"]["profil"])
        self._auto_tag_zeit = self._zeit_zeile(
            _("Day from (HH:MM)"), konfig["tag"]["zeit"])
        self._auto_nacht_combo = self._combo_zeile(
            _("Night profile"), konfig["nacht"]["profil"])
        self._auto_nacht_zeit = self._zeit_zeile(
            _("Night from (HH:MM)"), konfig["nacht"]["zeit"])

        self._auto_switch = compat.SwitchRow(title=_("Automation active"))
        self._auto_switch.set_active(konfig["aktiv"])
        self._auto_gruppe.add(self._auto_switch)
        self._auto_zeilen.append(self._auto_switch)
        # Erst nach dem Vorbelegen verbinden, sonst feuert das beim Aufbau.
        self._auto_switch.connect("notify::active", self._on_automatik_toggle)

    def _combo_zeile(self, titel, vorauswahl):
        modell = Gtk.StringList.new(self._profil_namen)
        combo = Adw.ComboRow(title=titel)
        combo.set_model(modell)
        if vorauswahl in self._profil_namen:
            combo.set_selected(self._profil_namen.index(vorauswahl))
        self._auto_gruppe.add(combo)
        self._auto_zeilen.append(combo)
        combo.connect("notify::selected", self._on_automatik_geaendert)
        return combo

    def _zeit_zeile(self, titel, wert):
        zeile = compat.EntryRow(title=titel)
        zeile.set_text(wert)
        zeile.set_show_apply_button(True)
        self._auto_gruppe.add(zeile)
        self._auto_zeilen.append(zeile)
        zeile.connect("apply", self._on_automatik_geaendert)
        return zeile

    def _on_automatik_geaendert(self, *_args):
        # Änderung an Profil oder Zeit nur übernehmen, wenn die Automatik läuft.
        if self._auto_switch.get_active():
            self._automatik_anwenden(still=True)

    def _on_automatik_toggle(self, switch, _param):
        if switch.get_active():
            self._automatik_anwenden(still=False)
        else:
            schedule.deaktiviere()
            self._melde(_("Day/night automation turned off."))

    def _automatik_anwenden(self, still):
        konfig = self._automatik_aus_ui()
        if not (schedule.zeit_ok(konfig["tag"]["zeit"])
                and schedule.zeit_ok(konfig["nacht"]["zeit"])):
            self._auto_switch_still(False)
            self._melde(_("Please enter valid times in HH:MM format."))
            return
        if konfig["tag"]["profil"] == konfig["nacht"]["profil"]:
            self._auto_switch_still(False)
            self._melde(_("Day and night profile must differ, otherwise "
                          "nothing switches."))
            return
        if schedule.aktiviere(konfig):
            if not still:
                self._melde(_("Day/night automation active."))
        else:
            self._auto_switch_still(False)
            self._melde(_("Automation could not be set up."))

    def _automatik_aus_ui(self):
        return {
            "aktiv": True,
            "tag": {"profil": self._combo_wert(self._auto_tag_combo),
                    "zeit": self._auto_tag_zeit.get_text().strip()},
            "nacht": {"profil": self._combo_wert(self._auto_nacht_combo),
                      "zeit": self._auto_nacht_zeit.get_text().strip()},
        }

    def _combo_wert(self, combo):
        idx = combo.get_selected()
        if 0 <= idx < len(self._profil_namen):
            return self._profil_namen[idx]
        return ""

    def _auto_switch_still(self, wert):
        """Setzt den Schalter, ohne den Toggle-Handler auszulösen."""
        self._auto_switch.handler_block_by_func(self._on_automatik_toggle)
        self._auto_switch.set_active(wert)
        self._auto_switch.handler_unblock_by_func(self._on_automatik_toggle)

    # --- Sicherungspunkte (automatisch vor riskanten Wechseln) ---

    def _punkte_gruppe(self):
        self._punkt_gruppe = Adw.PreferencesGroup(
            title=_("Restore points"),
            description=_("Created automatically before every theme, cursor "
                          "or shell change. Restores the state from before."))
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
            self._melde(_("Restore point applied. Restart the app to refresh "
                          "the selection here."))
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
        self._melde(_("Restored. Restart the app to refresh the selection "
                      "here."))

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
        self._fuelle_punkte()
        self._melde(_("Look package applied. Restart the app to refresh the "
                      "selection here."))

    def _melde(self, text):
        self._toasts.add_toast(Adw.Toast(title=text))
