"""Seite 'Dock'.

Stellt die Einstellungen der aktiven Dock-/Taskleisten-Erweiterung dar (Ubuntu
Dock / Dash to Dock oder Dash to Panel; siehe core/dock.py). Welche Schalter,
Auswahlfelder und Regler erscheinen, gibt das Dock-Modell vor; diese Seite baut
nur die passenden Zeilen und reicht Änderungen an die Lese-/Schreib-Closures
weiter. Jede Änderung wirkt sofort. Ist keine Dock-Erweiterung aktiv, zeigt die
Seite einen Hinweis statt einer leeren Liste.
"""

from gi.repository import Adw, Gtk

from src import compat
from src.core import dock


class DockPage(compat.PageBase):
    """Navigationsseite mit den Einstellungen des aktiven Docks."""

    def __init__(self, settings):
        super().__init__(title="Dock")
        self._settings = settings
        self._dock = dock.aktives_dock()

        toolbar = compat.toolbar_view(
            top_bars=[Adw.HeaderBar()], content=self._inhalt())
        self.set_child(toolbar)

    def _inhalt(self):
        if self._dock is None:
            return Adw.StatusPage(
                title="Keine Dock-Erweiterung aktiv",
                description="Diese Seite steuert Ubuntu Dock / Dash to Dock oder "
                            "Dash to Panel. Auf diesem System ist keine davon "
                            "eingeschaltet.",
                icon_name="view-app-grid-symbolic",
            )

        seite = Adw.PreferencesPage()
        gruppe = Adw.PreferencesGroup(
            title=self._dock.name,
            description="Änderungen werden sofort übernommen.")
        for e in self._dock.einstellungen:
            gruppe.add(self._zeile(e))
        seite.add(gruppe)
        return seite

    def _zeile(self, e):
        if e.art == dock.ART_SCHALTER:
            return self._schalter_zeile(e)
        if e.art == dock.ART_AUSWAHL:
            return self._auswahl_zeile(e)
        if e.art == dock.ART_REGLER:
            return self._regler_zeile(e)
        return Adw.ActionRow(title=e.titel)

    def _schalter_zeile(self, e):
        row = compat.SwitchRow(title=e.titel, subtitle=e.untertitel)
        row.set_active(bool(e.lesen()))
        # Erst nach set_active verbinden, sonst zählt die Vorbelegung als Änderung.
        row.connect("notify::active", lambda r, _p: e.schreiben(r.get_active()))
        return row

    def _auswahl_zeile(self, e):
        werte = [w for w, _a in e.optionen]
        anzeigen = [a for _w, a in e.optionen]
        row = Adw.ComboRow(title=e.titel, subtitle=e.untertitel)
        row.set_model(Gtk.StringList.new(anzeigen))
        aktuell = e.lesen()
        if aktuell in werte:
            row.set_selected(werte.index(aktuell))
        row.connect("notify::selected",
                    lambda r, _p: e.schreiben(werte[r.get_selected()]))
        return row

    def _regler_zeile(self, e):
        lo, hi, schritt = e.spanne
        row = compat.SpinRow.new_with_range(lo, hi, schritt)
        row.set_title(e.titel)
        row.set_subtitle(e.untertitel)
        row.set_value(e.lesen())
        row.connect("notify::value", lambda r, _p: e.schreiben(r.get_value()))
        return row
