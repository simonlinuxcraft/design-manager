"""Seite 'Übersicht'.

Zeigt den aktuellen Look auf einen Blick: GTK-Design, Symbole, Mauszeiger,
Schrift, Akzentfarbe, Shell-Design und ein Vorschaubild des Hintergrunds. Jede
Zeile springt in den passenden Bereich.

Die Werte liest die Seite direkt aus den Gettern von AppSettings. Weil die
Seiten zwischengespeichert werden (window.py), aktualisiert ein 'map'-Signal die
Anzeige jedes Mal, wenn man zur Übersicht zurückkehrt.
"""

import os

from gi.repository import Adw, Gtk

from src.core import backgrounds


class OverviewPage(Adw.NavigationPage):
    """Kompakte Zusammenfassung des aktiven Looks mit Sprüngen in die Bereiche."""

    def __init__(self, settings, springe_zu):
        super().__init__(title="Übersicht")
        self._settings = settings
        self._springe_zu = springe_zu
        self._wert_zeilen = {}

        seite = Adw.PreferencesPage()
        seite.add(self._look_gruppe())
        seite.add(self._hintergrund_gruppe())

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(seite)
        self.set_child(toolbar)

        self._aktualisiere()
        # Bei jeder Rückkehr neu einlesen, da die Seite gecacht ist.
        self.connect("map", lambda _w: self._aktualisiere())

    def _look_gruppe(self):
        gruppe = Adw.PreferencesGroup(
            title="Aktueller Look",
            description="Klick auf eine Zeile springt in den jeweiligen Bereich.")
        gruppe.add(self._wert_zeile("gtk", "GTK-Design", "appearance"))
        gruppe.add(self._wert_zeile("icon", "Symbole", "appearance"))
        gruppe.add(self._wert_zeile("cursor", "Mauszeiger", "cursor"))
        gruppe.add(self._wert_zeile("font", "Schrift", "fonts"))
        if self._settings.accent_verfuegbar():
            gruppe.add(self._wert_zeile("accent", "Akzentfarbe", "system"))
        gruppe.add(self._wert_zeile("shell", "Shell-Design", "shell"))
        return gruppe

    def _wert_zeile(self, key, titel, ziel):
        """Eine anklickbare Zeile, die in den Bereich 'ziel' springt."""
        zeile = Adw.ActionRow(title=titel)
        zeile.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        zeile.set_activatable(True)
        zeile.connect("activated", lambda _z: self._springe_zu(ziel))
        self._wert_zeilen[key] = zeile
        return zeile

    def _hintergrund_gruppe(self):
        gruppe = Adw.PreferencesGroup(title="Hintergrund")
        zeile = Adw.ActionRow(title="Hintergrundbild")
        zeile.set_activatable(True)
        zeile.connect("activated", lambda _z: self._springe_zu("background"))

        # Kleine Vorschau links, wird in _aktualisiere asynchron gefüllt.
        self._thumb = Gtk.Picture()
        self._thumb.set_size_request(96, 60)
        self._thumb.set_content_fit(Gtk.ContentFit.COVER)
        self._thumb.add_css_class("card")
        zeile.add_prefix(self._thumb)
        zeile.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        self._hintergrund_zeile = zeile

        gruppe.add(zeile)
        return gruppe

    # --- Aktualisierung ---

    def _aktualisiere(self):
        self._setze(self._wert_zeilen.get("gtk"), self._settings.gtk_theme())
        self._setze(self._wert_zeilen.get("icon"), self._settings.icon_theme())
        self._setze(self._wert_zeilen.get("cursor"), self._settings.cursor_theme())
        self._setze(self._wert_zeilen.get("font"), self._settings.font_name())
        if "accent" in self._wert_zeilen:
            self._setze(self._wert_zeilen["accent"], self._settings.accent_color())
        shell = self._settings.shell_theme() or "Standard"
        if not self._settings.user_themes_verfuegbar():
            shell = "nicht verfügbar (User Themes fehlt)"
        self._setze(self._wert_zeilen.get("shell"), shell)

        self._aktualisiere_hintergrund()

    def _setze(self, zeile, wert):
        if zeile is not None:
            zeile.set_subtitle(wert or "nicht gesetzt")

    def _aktualisiere_hintergrund(self):
        pfad = backgrounds.aktuelles_wallpaper(self._settings)
        if pfad is None:
            self._hintergrund_zeile.set_subtitle("Kein Bild gesetzt")
            self._thumb.set_paintable(None)
            return
        self._hintergrund_zeile.set_subtitle(os.path.basename(pfad))
        backgrounds.load_texture_async(pfad, 192, 120, self._thumb.set_paintable)
