"""Seite 'Sicherung'.

Oben die Profile: benannte Sets der aktuellen Einstellungen, zwischen denen man
per Klick wechseln kann (z.B. ein "Tag"- und ein "Nacht"-Look). Darunter die
Sicherung in eine frei wählbare Datei und das Wiederherstellen daraus.

Gesichert werden in beiden Fällen die dconf-Werte, nicht die Design- oder
Bilddateien selbst.
"""

import os

from gi.repository import Adw, Gio, GLib, Gtk

from src.core import backup


class BackupPage(Adw.NavigationPage):
    """Seite zum Sichern und Wiederherstellen der Einstellungen."""

    def __init__(self, settings):
        super().__init__(title="Sicherung")
        self._settings = settings
        self._profil_zeilen = []

        seite = Adw.PreferencesPage()
        seite.add(self._profil_eingabe_gruppe())
        seite.add(self._profil_liste_gruppe())
        seite.add(self._datei_gruppe())

        # Toasts brauchen einen Overlay um den Seiteninhalt.
        self._toasts = Adw.ToastOverlay()
        self._toasts.set_child(seite)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self._toasts)
        self.set_child(toolbar)

        self._fuelle_profile()

    # --- Profile ---

    def _profil_eingabe_gruppe(self):
        """Eingabezeile zum Anlegen eines Profils aus dem aktuellen Stand."""
        gruppe = Adw.PreferencesGroup(
            title="Profile",
            description="Mehrere komplette Looks speichern und per Klick "
                        "wechseln. Ein Profil merkt sich den aktuellen Stand.")
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
        self._melde("Profil gelöscht: " + name)

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

    def _melde(self, text):
        self._toasts.add_toast(Adw.Toast(title=text))
