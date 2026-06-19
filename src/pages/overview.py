"""Seite 'Übersicht'.

Ein kleines Dashboard: pro Bereich eine Karte mit einer Vorschau, dem Titel und
dem aktuell gesetzten Wert. Wo es billig geht, zeigt die Karte eine echte
Vorschau (Schrift im eigenen Font, Akzent als Farbpunkt, Symbole als echte
Beispiel-Icons des aktiven Designs), sonst ein thematisches Icon. Ein Klick
springt in den passenden Bereich.

Die Werte liest die Seite direkt aus den Gettern von AppSettings. Weil die
Seiten gecacht werden (window.py), liest ein 'map'-Signal bei jeder Rückkehr neu.
"""

import math

from gi.repository import Adw, Gdk, Gtk, Pango

from src import compat
from src.core import backgrounds
from src.i18n import _


# Akzentfarben-Namen (org.gnome.desktop.interface accent-color) auf Hex. Werte
# wie in libadwaita, nur für den Farbpunkt; gesetzt wird weiter der Name.
ACCENT_HEX = {
    "blue": "#3584e4", "teal": "#2190a4", "green": "#3a944a",
    "yellow": "#c88800", "orange": "#ed5b00", "red": "#e62d42",
    "pink": "#d56199", "purple": "#9141ac", "slate": "#6f8396",
}


class OverviewPage(compat.PageBase):
    """Dashboard des aktiven Looks mit Sprüngen in die Bereiche."""

    def __init__(self, settings, springe_zu):
        super().__init__(title=_("Overview"))
        self._settings = settings
        self._springe_zu = springe_zu
        self._wert_labels = {}

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        box.append(self._hero())
        box.append(self._karten_grid())
        box.append(self._hintergrund_vorschau())

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)
        toolbar = compat.toolbar_view(top_bars=[Adw.HeaderBar()], content=scroll)
        self.set_child(toolbar)

        self._aktualisiere()
        self.connect("map", lambda _w: self._aktualisiere())

    # --- Aufbau ---

    def _hero(self):
        """Großer Kopf des Dashboards: Titel und kurze Einordnung."""
        kasten = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        kasten.add_css_class("dash-hero")
        titel = Gtk.Label(label=_("Your look at a glance"), xalign=0)
        titel.add_css_class("hero-titel")
        unter = Gtk.Label(
            label=_("Everything your desktop is made of. Click a card to "
                    "jump in and change it."),
            xalign=0, wrap=True)
        unter.add_css_class("hero-unter")
        kasten.append(titel)
        kasten.append(unter)
        return kasten

    def _karten_grid(self):
        """Karten in zentrierten Reihen zu je drei. So sitzt auch eine
        unvollständige letzte Reihe mittig unter der oberen, nicht linksbündig
        (das kann eine FlowBox nicht)."""
        karten = [
            self._karte("gtk", _("GTK Theme"), "gtk",
                        self._icon_vorschau(
                            "preferences-desktop-appearance-symbolic")),
            self._karte("icon", _("Icons"), "icons",
                        self._icon_vorschau("applications-graphics-symbolic")),
            self._karte("cursor", _("Cursor"), "cursor",
                        self._icon_vorschau("input-mouse-symbolic")),
            self._karte("font", _("Font"), "fonts", self._schrift_vorschau()),
            self._karte("shell", _("Shell Theme"), "shell",
                        self._icon_vorschau("video-display-symbolic")),
        ]
        if self._settings.accent_verfuegbar():
            karten.append(self._karte("accent", _("Accent color"), "system",
                                      self._akzent_vorschau()))

        spalten = 3
        aussen = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for start in range(0, len(karten), spalten):
            reihe = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            reihe.set_halign(Gtk.Align.CENTER)
            for karte in karten[start:start + spalten]:
                karte.set_size_request(210, -1)
                reihe.append(karte)
            aussen.append(reihe)
        return aussen

    def _karte(self, key, titel, ziel, vorschau):
        """Klickbare Karte: Vorschau oben, Titel, aktueller Wert."""
        inhalt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inhalt.set_halign(Gtk.Align.CENTER)

        vorschau.set_halign(Gtk.Align.CENTER)
        vorschau.set_valign(Gtk.Align.CENTER)
        rahmen = Gtk.Box()
        rahmen.set_size_request(-1, 56)
        rahmen.set_halign(Gtk.Align.CENTER)
        rahmen.set_valign(Gtk.Align.CENTER)
        rahmen.append(vorschau)
        inhalt.append(rahmen)

        t = Gtk.Label(label=titel)
        t.add_css_class("card-title")
        inhalt.append(t)

        wert = Gtk.Label()
        wert.add_css_class("card-status")
        wert.set_ellipsize(Pango.EllipsizeMode.END)
        wert.set_max_width_chars(18)
        inhalt.append(wert)
        self._wert_labels[key] = wert

        button = Gtk.Button()
        button.add_css_class("flat")
        button.add_css_class("dash-karte")
        button.set_child(inhalt)
        button.connect("clicked", lambda _b: self._springe_zu(ziel))
        return button

    # --- Vorschauen ---

    def _icon_vorschau(self, icon_name):
        img = Gtk.Image.new_from_icon_name(icon_name)
        img.set_pixel_size(44)
        img.add_css_class("dash-icon")
        return img

    def _schrift_vorschau(self):
        self._font_label = Gtk.Label(label="Aa")
        self._font_label.add_css_class("dash-font")
        return self._font_label

    def _akzent_vorschau(self):
        self._akzent_area = Gtk.DrawingArea()
        self._akzent_area.set_content_width(40)
        self._akzent_area.set_content_height(40)
        self._akzent_area.set_draw_func(self._zeichne_akzent)
        return self._akzent_area

    def _zeichne_akzent(self, _area, cr, breite, hoehe):
        name = self._settings.accent_color()
        hexv = ACCENT_HEX.get(name, "#888888").lstrip("#")
        r, g, b = (int(hexv[i:i + 2], 16) / 255 for i in (0, 2, 4))
        cr.arc(breite / 2, hoehe / 2, min(breite, hoehe) / 2 - 2, 0, 2 * math.pi)
        cr.set_source_rgb(r, g, b)
        cr.fill()

    def _hintergrund_vorschau(self):
        """Das Wallpaper als abgerundetes Bild, zentriert und klickbar, ohne
        Karten-Rahmen und ohne Beschriftung.

        Ein GestureClick statt eines Buttons, damit kein Knopf-Chrome ums Bild
        liegt; der Zeiger wird zur Hand, damit die Klickbarkeit klar ist. Die
        umschließende Box mit valign START hält die feste Bildhöhe; ein Picture
        allein zöge sich sonst auf seine natürliche Bildhöhe auf."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_halign(Gtk.Align.CENTER)
        box.set_valign(Gtk.Align.START)
        box.set_margin_top(6)

        self._hg_bild = Gtk.Picture()
        compat.set_cover(self._hg_bild)
        self._hg_bild.set_size_request(440, 132)
        self._hg_bild.add_css_class("dash-wallpaper")
        self._hg_bild.set_cursor(Gdk.Cursor.new_from_name("pointer", None))
        klick = Gtk.GestureClick()
        klick.connect("released", lambda *_: self._springe_zu("background"))
        self._hg_bild.add_controller(klick)
        box.append(self._hg_bild)
        return box

    # --- Aktualisierung ---

    def _aktualisiere(self):
        self._wert_labels["gtk"].set_label(
            self._settings.gtk_theme() or _("not set"))
        self._wert_labels["icon"].set_label(
            self._settings.icon_theme() or _("not set"))
        self._wert_labels["cursor"].set_label(
            self._settings.cursor_theme() or _("not set"))
        self._wert_labels["font"].set_label(
            self._settings.font_name() or _("not set"))
        shell = self._settings.shell_theme() or _("Default")
        if not self._settings.user_themes_verfuegbar():
            shell = _("not available (User Themes missing)")
        self._wert_labels["shell"].set_label(shell)
        if "accent" in self._wert_labels:
            self._wert_labels["accent"].set_label(
                self._settings.accent_color() or _("not set"))
            self._akzent_area.queue_draw()

        self._aktualisiere_schrift()
        self._aktualisiere_hintergrund()

    def _aktualisiere_schrift(self):
        desc = Pango.FontDescription.from_string(
            self._settings.font_name() or "Sans")
        desc.set_size(20 * Pango.SCALE)
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_font_desc_new(desc))
        self._font_label.set_attributes(attrs)

    def _aktualisiere_hintergrund(self):
        pfad = backgrounds.aktuelles_wallpaper(self._settings)
        if pfad is None:
            self._hg_bild.set_paintable(None)
            return
        backgrounds.load_texture_async(pfad, 600, 300, self._hg_bild.set_paintable)
