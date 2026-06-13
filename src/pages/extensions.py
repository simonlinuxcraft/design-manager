"""Seite 'Erweiterungen'.

Verwaltet die installierten GNOME-Shell-Erweiterungen: ein globaler Schalter,
darunter Benutzer- und System-Erweiterungen je mit eigenem Schalter (an/aus
wirkt live) und, falls vorhanden, einem Knopf zu ihren Einstellungen.

Die Daten kommen über den D-Bus-Dienst org.gnome.Shell.Extensions (siehe
core/extensions.py). Ist er nicht erreichbar (etwa in einer Sandbox), zeigen wir
einen Hinweis statt der Liste.
"""

from gi.repository import Adw, GLib, Gtk

from src.core.extensions import (
    ShellExtensions, STATE_ERROR, TYPE_SYSTEM, TYPE_USER,
)


class ExtensionsPage(Adw.NavigationPage):
    """Navigationsseite zum Verwalten der GNOME-Shell-Erweiterungen."""

    def __init__(self, settings):
        super().__init__(title="Erweiterungen")
        self._ext = ShellExtensions()
        # Guard, damit programmatisches Setzen eines Schalters nicht den
        # Toggle-Handler auslöst (sonst Rückkopplung / unnötige D-Bus-Calls).
        self._updating = False
        self._rows = {}        # uuid -> Adw.SwitchRow
        self._user_rows = []   # (row, can_change) der Benutzer-Erweiterungen

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self._inhalt())
        self.set_child(toolbar)

    def _inhalt(self):
        if not self._ext.verfuegbar():
            return Adw.StatusPage(
                title="Hier nicht verfügbar",
                description="Die Verwaltung der Erweiterungen braucht Zugriff "
                            "auf den GNOME-Shell-Dienst, der hier nicht "
                            "erreichbar ist (etwa in einer Sandbox).",
                icon_name="application-x-addon-symbolic",
            )

        seite = Adw.PreferencesPage()
        seite.add(self._master_gruppe())

        liste = self._ext.list_extensions()
        benutzer = [x for x in liste if x["type"] == TYPE_USER]
        system = [x for x in liste if x["type"] == TYPE_SYSTEM]
        if benutzer:
            seite.add(self._ext_gruppe("Benutzer-Erweiterungen", benutzer))
        if system:
            seite.add(self._ext_gruppe("System-Erweiterungen", system))

        # Anfangszustand der Benutzer-Zeilen an den Master-Schalter anpassen.
        self._master_wirkung(self._ext.user_extensions_enabled())
        # Live mitziehen, wenn Erweiterungen anderswo umgeschaltet werden.
        self._ext.connect_state_changed(self._on_state_changed)
        return seite

    # --- Globaler Schalter ---

    def _master_gruppe(self):
        gruppe = Adw.PreferencesGroup()
        self._master = Adw.SwitchRow(
            title="Erweiterungen aktiviert",
            subtitle="Schaltet alle Benutzer-Erweiterungen gemeinsam.",
        )
        self._master.set_active(self._ext.user_extensions_enabled())
        # Erst nach set_active verbinden, sonst feuert die Vorbelegung.
        self._master.connect("notify::active", self._on_master)
        gruppe.add(self._master)
        return gruppe

    def _on_master(self, row, _param):
        if self._updating:
            return
        an = row.get_active()
        self._ext.set_user_extensions_enabled(an)
        self._master_wirkung(an)

    def _master_wirkung(self, an):
        """Benutzer-Zeilen ausgrauen, wenn der globale Schalter aus ist."""
        for row, can_change in self._user_rows:
            row.set_sensitive(an and can_change)

    # --- Erweiterungs-Zeilen ---

    def _ext_gruppe(self, titel, eintraege):
        gruppe = Adw.PreferencesGroup(title=titel)
        for x in eintraege:
            gruppe.add(self._ext_zeile(x))
        return gruppe

    def _ext_zeile(self, x):
        row = Adw.SwitchRow(title=GLib.markup_escape_text(x["name"]))
        row.set_sensitive(x["can_change"])

        # Bei Fehler die Fehlermeldung zeigen, sonst die Beschreibung.
        if x["state"] == STATE_ERROR and x["error"]:
            row.set_subtitle(GLib.markup_escape_text(x["error"]))
            row.add_css_class("error")
        elif x["description"]:
            row.set_subtitle(GLib.markup_escape_text(x["description"]))

        row.set_active(x["enabled"])
        # Erst nach set_active verbinden (Vorbelegung soll nicht auslösen).
        row.connect("notify::active", self._on_toggle, x["uuid"])

        if x["has_prefs"]:
            knopf = Gtk.Button(icon_name="emblem-system-symbolic")
            knopf.add_css_class("flat")
            knopf.set_valign(Gtk.Align.CENTER)
            knopf.set_tooltip_text("Einstellungen der Erweiterung")
            knopf.connect("clicked", self._on_prefs, x["uuid"])
            row.add_suffix(knopf)

        self._rows[x["uuid"]] = row
        if x["type"] == TYPE_USER:
            self._user_rows.append((row, x["can_change"]))
        return row

    def _on_toggle(self, row, _param, uuid):
        if self._updating:
            return
        if row.get_active():
            self._ext.enable(uuid)
        else:
            self._ext.disable(uuid)

    def _on_prefs(self, _knopf, uuid):
        self._ext.open_prefs(uuid)

    def _on_state_changed(self, uuid, info):
        row = self._rows.get(uuid)
        if row is None:
            return
        enabled = bool(info.get("enabled", row.get_active()))
        self._updating = True
        row.set_active(enabled)
        self._updating = False
