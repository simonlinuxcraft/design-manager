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

from src import compat
from src.core import backgrounds
from src.i18n import _


class OverviewPage(compat.PageBase):
    """Kompakte Zusammenfassung des aktiven Looks mit Sprüngen in die Bereiche."""

    def __init__(self, settings, springe_zu):
        super().__init__(title=_("Overview"))
        self._settings = settings
        self._springe_zu = springe_zu
        self._wert_zeilen = {}

        seite = Adw.PreferencesPage()
        seite.add(self._look_gruppe())
        seite.add(self._hintergrund_gruppe())

        toolbar = compat.toolbar_view(
            top_bars=[Adw.HeaderBar()], content=seite)
        self.set_child(toolbar)

        self._aktualisiere()
        # Bei jeder Rückkehr neu einlesen, da die Seite gecacht ist.
        self.connect("map", lambda _w: self._aktualisiere())

    def _look_gruppe(self):
        gruppe = Adw.PreferencesGroup(
            title=_("Current look"),
            description=_("Click a row to jump to that section."))
        gruppe.add(self._wert_zeile("gtk", _("GTK Theme"), "gtk"))
        gruppe.add(self._wert_zeile("icon", _("Icons"), "icons"))
        gruppe.add(self._wert_zeile("cursor", _("Cursor"), "cursor"))
        gruppe.add(self._wert_zeile("font", _("Font"), "fonts"))
        if self._settings.accent_verfuegbar():
            gruppe.add(self._wert_zeile("accent", _("Accent color"), "system"))
        gruppe.add(self._wert_zeile("shell", _("Shell Theme"), "shell"))
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
        gruppe = Adw.PreferencesGroup(title=_("Background"))
        zeile = Adw.ActionRow(title=_("Wallpaper"))
        zeile.set_activatable(True)
        zeile.connect("activated", lambda _z: self._springe_zu("background"))

        # Kleine Vorschau links, wird in _aktualisiere asynchron gefüllt.
        self._thumb = Gtk.Picture()
        self._thumb.set_size_request(96, 60)
        compat.set_cover(self._thumb)
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
        shell = self._settings.shell_theme() or _("Default")
        if not self._settings.user_themes_verfuegbar():
            shell = _("not available (User Themes missing)")
        self._setze(self._wert_zeilen.get("shell"), shell)

        self._aktualisiere_hintergrund()

    def _setze(self, zeile, wert):
        if zeile is not None:
            zeile.set_subtitle(wert or _("not set"))

    def _aktualisiere_hintergrund(self):
        pfad = backgrounds.aktuelles_wallpaper(self._settings)
        if pfad is None:
            self._hintergrund_zeile.set_subtitle(_("No image set"))
            self._thumb.set_paintable(None)
            return
        self._hintergrund_zeile.set_subtitle(os.path.basename(pfad))
        backgrounds.load_texture_async(pfad, 192, 120, self._thumb.set_paintable)
