"""Vorschaukarte für ein Symbol-Design (Icons).

Eine Karte zeigt ein paar Beispiel-Icons direkt aus dem jeweiligen Design,
darunter den Namen und ob es gerade aktiv ist. So sieht man die Symbole, bevor
man sie auswählt (angelehnt ans Mockup).

Der Trick: Wir bauen für jedes Design ein eigenes Gtk.IconTheme und lassen es
in den Standard-Icon-Ordnern nach den Beispiel-Namen suchen. So bekommen wir
die echten Icons genau dieses Designs, ohne das System-Design zu verändern.
"""

from gi.repository import Gtk

from src.core import themes
from src.i18n import _
from src.widgets.card_common import status_zeile


# Beispiel-Icons, die in fast jedem Design vorkommen. Pro Platz mehrere Namen
# als Fallback; der erste vorhandene wird genommen.
BEISPIEL_ICONS = [
    ["folder", "inode-directory"],
    ["audio-x-generic", "folder-music", "multimedia-audio-player"],
    ["camera-photo", "camera", "accessories-camera"],
]

VORSCHAU_GROESSE = 32


def _icon_theme_fuer(name):
    """Ein Gtk.IconTheme, das gezielt im Design 'name' sucht."""
    icon_theme = Gtk.IconTheme.new()
    icon_theme.set_search_path(themes.ICON_DIRS)
    icon_theme.set_theme_name(name)
    return icon_theme


class ThemeCard(Gtk.FlowBoxChild):
    """Eine anklickbare Vorschaukarte für genau ein Symbol-Design."""

    def __init__(self, theme_name, aktiv, loeschbar=False, on_loeschen=None):
        super().__init__()
        self.theme_name = theme_name
        self.add_css_class("theme-card")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        box.append(self._beispiel_reihe(theme_name))

        name_label = Gtk.Label(label=theme_name, xalign=0)
        name_label.add_css_class("card-title")
        name_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END: lange Namen kürzen
        box.append(name_label)

        box.append(status_zeile(self, loeschbar, on_loeschen))

        self.set_child(box)
        self.set_aktiv(aktiv)

    def _beispiel_reihe(self, theme_name):
        """Eine waagerechte Reihe der Beispiel-Icons dieses Designs."""
        reihe = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        icon_theme = _icon_theme_fuer(theme_name)
        for namen in BEISPIEL_ICONS:
            reihe.append(self._beispiel_bild(icon_theme, namen))
        return reihe

    def _beispiel_bild(self, icon_theme, namen):
        """Ein Bild für den ersten der 'namen', den das Design kennt."""
        for name in namen:
            if icon_theme.has_icon(name):
                paintable = icon_theme.lookup_icon(
                    name, None, VORSCHAU_GROESSE, 1,
                    Gtk.TextDirection.NONE, 0,
                )
                bild = Gtk.Image.new_from_paintable(paintable)
                bild.set_pixel_size(VORSCHAU_GROESSE)
                return bild
        # Kein passendes Icon im Design gefunden: neutraler Platzhalter.
        bild = Gtk.Image.new_from_icon_name("image-missing")
        bild.set_pixel_size(VORSCHAU_GROESSE)
        return bild

    def set_aktiv(self, aktiv):
        """Markiert die Karte als aktiv (silberner Rahmen) oder nicht."""
        if aktiv:
            self.add_css_class("aktiv")
            self._status.set_text(_("Active"))
        else:
            self.remove_css_class("aktiv")
            self._status.set_text(_("Installed"))
