"""Seite 'Sicherung'.

Oben die Profile: benannte Sets der aktuellen Einstellungen, zwischen denen man
per Klick wechseln kann (z.B. ein "Tag"- und ein "Nacht"-Look). Darunter die
Sicherung in eine frei wählbare Datei und das Wiederherstellen daraus.

Gesichert werden in beiden Fällen die dconf-Werte, nicht die Design- oder
Bilddateien selbst.
"""

import os
import time

from gi.repository import Adw, Gio, GLib, Gtk

from src.core import backup, looksbundle, restorepoint, schedule


class BackupPage(Adw.NavigationPage):
    """Seite zum Sichern und Wiederherstellen der Einstellungen."""

    def __init__(self, settings):
        super().__init__(title="Sicherung")
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

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self._toasts)
        self.set_child(toolbar)

        self._fuelle_profile()
        self._fuelle_automatik()
        self._fuelle_punkte()

    # --- Profile ---

    def _profil_eingabe_gruppe(self):
        """Eingabezeile zum Anlegen eines Profils aus dem aktuellen Stand."""
        gruppe = Adw.PreferencesGroup(
            title="Profile",
            description="Den aktuellen Stand als benanntes Set speichern und per "
                        "Klick wieder anwenden. Gespeicherte Profile erscheinen "
                        "auch auf der Looks-Seite.")
        self._name_entry = Adw.EntryRow(title="Neues Profil benennen")
        self._name_entry.set_show_apply_button(True)
        self._name_entry.connect("apply", self._on_profil_speichern)
        gruppe.add(self._name_entry)
        return gruppe

    def _profil_liste_gruppe(self):
        self._profil_gruppe = Adw.PreferencesGroup(title="Gespeicherte Profile")
        return self._profil_gruppe

    def _fuelle_profile(self):
        """Baut die Profilliste neu auf (nach Anlegen oder Löschen)."""
        for zeile in self._profil_zeilen:
            self._profil_gruppe.remove(zeile)
        self._profil_zeilen = []

        namen = backup.list_profiles()
        if not namen:
            leer = Adw.ActionRow(
                title="Noch keine Profile",
                subtitle="Oben einen Namen eingeben und speichern.")
            leer.set_sensitive(False)
            self._profil_gruppe.add(leer)
            self._profil_zeilen.append(leer)
            return

        for name in namen:
            zeile = Adw.ActionRow(title=name)

            anwenden = Gtk.Button(label="Anwenden")
            anwenden.set_valign(Gtk.Align.CENTER)
            anwenden.add_css_class("flat")
            anwenden.connect("clicked", self._on_profil_anwenden, name)

            loeschen = Gtk.Button(icon_name="user-trash-symbolic")
            loeschen.set_valign(Gtk.Align.CENTER)
            loeschen.add_css_class("flat")
            loeschen.set_tooltip_text("Profil löschen")
            loeschen.connect("clicked", self._on_profil_loeschen, name)

            zeile.add_suffix(anwenden)
            zeile.add_suffix(loeschen)
            self._profil_gruppe.add(zeile)
            self._profil_zeilen.append(zeile)

    def _on_profil_speichern(self, entry):
        try:
            gespeichert = backup.save_profile(self._settings, entry.get_text())
        except ValueError:
            self._melde("Bitte einen Namen eingeben.")
            return
        except OSError as fehler:
            self._melde("Speichern fehlgeschlagen: " + (fehler.strerror or "Fehler"))
            return
        entry.set_text("")
        self._fuelle_profile()
        self._fuelle_automatik()
        self._melde("Profil gespeichert: " + gespeichert)

    def _on_profil_anwenden(self, _knopf, name):
        try:
            erfolg = backup.load_profile(self._settings, name)
        except (OSError, ValueError):
            self._melde("Das Profil konnte nicht gelesen werden.")
            return
        if not erfolg:
            self._melde("Das Profil ist beschädigt.")
            return
        self._melde("Profil angewendet: " + name + ". App neu starten, um die "
                    "Auswahl hier zu aktualisieren.")

    def _on_profil_loeschen(self, _knopf, name):
        backup.delete_profile(name)
        self._fuelle_profile()
        self._fuelle_automatik()
        self._melde("Profil gelöscht: " + name)

    # --- Tag/Nacht-Automatik ---

    def _automatik_gruppe(self):
        self._auto_gruppe = Adw.PreferencesGroup(
            title="Tag/Nacht-Automatik",
            description="Zwei Profile an feste Uhrzeiten binden. Schaltet den "
                        "kompletten Look per systemd-Timer automatisch um.")
        return self._auto_gruppe

    def _fuelle_automatik(self):
        """Baut die Automatik-Zeilen neu auf (nach Profiländerung oder Refresh)."""
        for zeile in self._auto_zeilen:
            self._auto_gruppe.remove(zeile)
        self._auto_zeilen = []

        self._profil_namen = backup.list_profiles()
        if len(self._profil_namen) < 2:
            leer = Adw.ActionRow(
                title="Noch nicht genug Profile",
                subtitle="Erst zwei verschiedene Profile anlegen (z.B. ein "
                         "helles „Tag“ und ein dunkles „Nacht“).")
            leer.set_sensitive(False)
            self._auto_gruppe.add(leer)
            self._auto_zeilen.append(leer)
            return

        konfig = schedule.lese_konfig()
        self._auto_tag_combo = self._combo_zeile("Tag-Profil", konfig["tag"]["profil"])
        self._auto_tag_zeit = self._zeit_zeile("Tag ab (HH:MM)", konfig["tag"]["zeit"])
        self._auto_nacht_combo = self._combo_zeile(
            "Nacht-Profil", konfig["nacht"]["profil"])
        self._auto_nacht_zeit = self._zeit_zeile(
            "Nacht ab (HH:MM)", konfig["nacht"]["zeit"])

        self._auto_switch = Adw.SwitchRow(title="Automatik aktiv")
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
        zeile = Adw.EntryRow(title=titel)
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
            self._melde("Tag/Nacht-Automatik ausgeschaltet.")

    def _automatik_anwenden(self, still):
        konfig = self._automatik_aus_ui()
        if not (schedule.zeit_ok(konfig["tag"]["zeit"])
                and schedule.zeit_ok(konfig["nacht"]["zeit"])):
            self._auto_switch_still(False)
            self._melde("Bitte gültige Uhrzeiten im Format HH:MM eingeben.")
            return
        if konfig["tag"]["profil"] == konfig["nacht"]["profil"]:
            self._auto_switch_still(False)
            self._melde("Tag- und Nacht-Profil müssen verschieden sein, sonst "
                        "schaltet sich nichts um.")
            return
        if schedule.aktiviere(konfig):
            if not still:
                self._melde("Tag/Nacht-Automatik aktiv.")
        else:
            self._auto_switch_still(False)
            self._melde("Automatik konnte nicht eingerichtet werden.")

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
            title="Sicherungspunkte",
            description="Werden automatisch vor jedem Design-, Mauszeiger- oder "
                        "Shell-Wechsel angelegt. Stellt den Stand davor wieder her.")
        return self._punkt_gruppe

    def _fuelle_punkte(self):
        """Baut die Liste der Sicherungspunkte neu auf."""
        for zeile in self._punkt_zeilen:
            self._punkt_gruppe.remove(zeile)
        self._punkt_zeilen = []

        punkte = restorepoint.liste()
        if not punkte:
            leer = Adw.ActionRow(
                title="Noch keine Sicherungspunkte",
                subtitle="Sobald du ein Design wechselst, entsteht einer.")
            leer.set_sensitive(False)
            self._punkt_gruppe.add(leer)
            self._punkt_zeilen.append(leer)
            return

        for punkt in punkte:
            zeile = Adw.ActionRow(
                title=punkt["anlass"], subtitle=self._format_zeit(punkt["zeit"]))

            zurueck = Gtk.Button(label="Zurück")
            zurueck.set_valign(Gtk.Align.CENTER)
            zurueck.add_css_class("flat")
            zurueck.connect("clicked", self._on_punkt_anwenden, punkt["datei"])

            loeschen = Gtk.Button(icon_name="user-trash-symbolic")
            loeschen.set_valign(Gtk.Align.CENTER)
            loeschen.add_css_class("flat")
            loeschen.set_tooltip_text("Sicherungspunkt löschen")
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
            self._melde("Sicherungspunkt angewendet. App neu starten, um die "
                        "Auswahl hier zu aktualisieren.")
        else:
            self._melde("Der Sicherungspunkt konnte nicht gelesen werden.")

    def _on_punkt_loeschen(self, _knopf, datei):
        restorepoint.loesche(datei)
        self._fuelle_punkte()
        self._melde("Sicherungspunkt gelöscht.")

    # --- Sicherung in eine Datei ---

    def _datei_gruppe(self):
        gruppe = Adw.PreferencesGroup(
            title="Sicherungsdatei",
            description="Den aktuellen Stand als Datei exportieren oder aus "
                        "einer früheren Sicherung wiederherstellen.")
        gruppe.add(self._zeile(
            "Sichern", "In eine Datei exportieren",
            "document-save-symbolic", self._on_sichern))
        gruppe.add(self._zeile(
            "Wiederherstellen", "Aus einer Datei importieren",
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
        dialog = Gtk.FileDialog()
        dialog.set_title("Einstellungen sichern")
        dialog.set_initial_name("design-manager-sicherung.json")
        dialog.save(self.get_root(), None, self._on_speicherziel)

    def _on_speicherziel(self, dialog, ergebnis):
        try:
            datei = dialog.save_finish(ergebnis)
        except GLib.Error:
            return  # abgebrochen
        pfad = datei.get_path()
        if not pfad:
            return
        try:
            backup.save_to_file(self._settings, pfad)
        except OSError as fehler:
            self._melde("Sichern fehlgeschlagen: " + (fehler.strerror or "Fehler"))
            return
        self._melde("Gesichert: " + os.path.basename(pfad))

    # --- Wiederherstellen ---

    def _on_wiederherstellen(self, _knopf):
        dialog = Gtk.FileDialog()
        dialog.set_title("Sicherung wiederherstellen")

        nur_json = Gtk.FileFilter()
        nur_json.set_name("Sicherungen (*.json)")
        nur_json.add_pattern("*.json")
        liste = Gio.ListStore.new(Gtk.FileFilter)
        liste.append(nur_json)
        dialog.set_filters(liste)

        dialog.open(self.get_root(), None, self._on_quelle)

    def _on_quelle(self, dialog, ergebnis):
        try:
            datei = dialog.open_finish(ergebnis)
        except GLib.Error:
            return  # abgebrochen
        pfad = datei.get_path()
        if not pfad:
            return
        try:
            erfolg = backup.load_from_file(self._settings, pfad)
        except (OSError, ValueError):
            self._melde("Die Datei konnte nicht gelesen werden.")
            return
        if not erfolg:
            self._melde("Das ist keine gültige Sicherung.")
            return
        self._melde("Wiederhergestellt. App neu starten, um die Auswahl hier "
                    "zu aktualisieren.")

    # --- Look-Paket (.dmlook, inklusive Design-Dateien) ---

    def _look_paket_gruppe(self):
        gruppe = Adw.PreferencesGroup(
            title="Look-Paket teilen",
            description="Den ganzen Look als .dmlook bündeln, inklusive der "
                        "Design-Dateien und des Hintergrundbilds, oder ein "
                        "solches Paket importieren.")
        gruppe.add(self._zeile(
            "Look exportieren", "Designs und Bild in eine .dmlook packen",
            "document-save-symbolic", self._on_look_export))
        gruppe.add(self._zeile(
            "Look importieren", "Aus einer .dmlook installieren und anwenden",
            "document-open-symbolic", self._on_look_import))
        return gruppe

    def _on_look_export(self, _knopf):
        dialog = Gtk.FileDialog()
        dialog.set_title("Look-Paket exportieren")
        dialog.set_initial_name("mein-look.dmlook")
        dialog.save(self.get_root(), None, self._on_look_export_ziel)

    def _on_look_export_ziel(self, dialog, ergebnis):
        try:
            datei = dialog.save_finish(ergebnis)
        except GLib.Error:
            return  # abgebrochen
        pfad = datei.get_path()
        if not pfad:
            return
        try:
            looksbundle.exportiere(self._settings, pfad)
        except OSError as fehler:
            self._melde("Export fehlgeschlagen: " + (fehler.strerror or "Fehler"))
            return
        self._melde("Look-Paket gespeichert: " + os.path.basename(pfad))

    def _on_look_import(self, _knopf):
        dialog = Gtk.FileDialog()
        dialog.set_title("Look-Paket importieren")

        nur = Gtk.FileFilter()
        nur.set_name("Look-Pakete (*.dmlook)")
        nur.add_pattern("*.dmlook")
        liste = Gio.ListStore.new(Gtk.FileFilter)
        liste.append(nur)
        dialog.set_filters(liste)

        dialog.open(self.get_root(), None, self._on_look_import_quelle)

    def _on_look_import_quelle(self, dialog, ergebnis):
        try:
            datei = dialog.open_finish(ergebnis)
        except GLib.Error:
            return  # abgebrochen
        pfad = datei.get_path()
        if not pfad:
            return
        try:
            erfolg = looksbundle.importiere(self._settings, pfad)
        except OSError:
            self._melde("Das Look-Paket konnte nicht gelesen werden.")
            return
        if not erfolg:
            self._melde("Das ist kein gültiges Look-Paket.")
            return
        self._fuelle_punkte()
        self._melde("Look-Paket angewendet. App neu starten, um die Auswahl "
                    "hier zu aktualisieren.")

    def _melde(self, text):
        self._toasts.add_toast(Adw.Toast(title=text))
