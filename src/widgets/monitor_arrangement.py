"""Visuelle Monitor-Anordnung als Auswahl für den Hintergrund.

Oben ein Schalter "Alle Bildschirme", darunter die Monitore als Rechtecke in
ihrer echten räumlichen Lage. Das Widget zeigt nur an und meldet die Auswahl
über on_select("all" oder connector); die eigentliche Logik (Bild setzen,
Composite bauen) liegt in der Seite. So gibt es genau eine Galerie, die für die
hier getroffene Auswahl gilt.

Bei laufendem Variety ist die Einzelauswahl gesperrt (es würde das Composite
beim nächsten Login überschreiben); dann bleibt nur "Alle Bildschirme".
"""

import os

from gi.repository import Gtk

from src import compat
from src.core import backgrounds
from src.i18n import _


CANVAS_W = 460
CANVAS_H = 200


class MonitorArrangement(Gtk.Box):
    """Auswahl zwischen "alle Bildschirme" und einem einzelnen Monitor."""

    def __init__(self, monitore, on_select, einzeln_erlaubt=True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self._monitore = monitore
        self._on_select = on_select
        self._einzeln_erlaubt = einzeln_erlaubt
        self._kacheln = {}  # connector -> {"button", "pic"}

        self._all_button = Gtk.Button(label=_("All displays"))
        self._all_button.set_halign(Gtk.Align.START)
        self._all_button.connect("clicked", lambda _b: self._on_select("all"))
        self.append(self._all_button)

        self.append(self._anordnung())

        if einzeln_erlaubt:
            hinweis = _("Click a monitor to give it its own image. "
                        "Re-apply after changing resolution or layout.")
        else:
            hinweis = _("You have multiple monitors. To give each its own "
                        "image, remove Variety first (button above).")
        self._status = Gtk.Label(label=hinweis, xalign=0, wrap=True)
        self._status.add_css_class("dim-label")
        self.append(self._status)

    def _anordnung(self):
        rahmen = Gtk.Frame()
        rahmen.add_css_class("monitor-flaeche")
        fixed = Gtk.Fixed()
        fixed.set_size_request(CANVAS_W, CANVAS_H)
        rahmen.set_child(fixed)

        if not self._monitore:
            return rahmen
        min_x = min(m["x"] for m in self._monitore)
        min_y = min(m["y"] for m in self._monitore)
        bb_w = max(m["x"] + m["width"] for m in self._monitore) - min_x
        bb_h = max(m["y"] + m["height"] for m in self._monitore) - min_y
        if bb_w <= 0 or bb_h <= 0:
            return rahmen

        scale = min(CANVAS_W / bb_w, CANVAS_H / bb_h) * 0.88
        off_x = (CANVAS_W - bb_w * scale) / 2
        off_y = (CANVAS_H - bb_h * scale) / 2
        for m in self._monitore:
            kx = (m["x"] - min_x) * scale + off_x
            ky = (m["y"] - min_y) * scale + off_y
            kw = max(48, int(m["width"] * scale))
            kh = max(32, int(m["height"] * scale))
            fixed.put(self._kachel(m, kw, kh), int(kx), int(ky))
        return rahmen

    def _kachel(self, m, w, h):
        conn = m["connector"]
        button = Gtk.Button()
        button.add_css_class("monitor-kachel")
        button.set_size_request(w, h)
        button.set_tooltip_text("%s   %d x %d" % (conn, m["width"], m["height"]))
        button.set_sensitive(self._einzeln_erlaubt)
        button.connect("clicked", lambda _b, c=conn: self._on_select(c))

        overlay = Gtk.Overlay()
        pic = Gtk.Picture()
        compat.set_cover(pic)
        overlay.set_child(pic)
        label = Gtk.Label(label=conn)
        label.add_css_class("monitor-kachel-label")
        label.set_halign(Gtk.Align.CENTER)
        label.set_valign(Gtk.Align.CENTER)
        overlay.add_overlay(label)
        button.set_child(overlay)

        self._kacheln[conn] = {"button": button, "pic": pic}
        return button

    # --- von der Seite gesteuert ---

    def einzeln_freischalten(self):
        """Macht die Monitor-Kacheln klickbar (nach dem Entfernen von Variety)."""
        self._einzeln_erlaubt = True
        for k in self._kacheln.values():
            k["button"].set_sensitive(True)

    def set_status(self, text):
        """Setzt den Hinweistext unter der Anordnung (zeigt die aktuelle Auswahl)."""
        self._status.set_label(text)

    def set_auswahl(self, auswahl):
        """Hebt die aktuelle Auswahl hervor ("all" oder ein connector)."""
        if auswahl == "all":
            self._all_button.add_css_class("suggested-action")
        else:
            self._all_button.remove_css_class("suggested-action")
        for conn, k in self._kacheln.items():
            if conn == auswahl:
                k["button"].add_css_class("selected")
            else:
                k["button"].remove_css_class("selected")

    def set_thumbnail(self, conn, pfad):
        """Setzt das Vorschaubild einer Monitor-Kachel (None = leer)."""
        k = self._kacheln.get(conn)
        if k is None:
            return
        if pfad and os.path.isfile(pfad):
            backgrounds.load_texture_async(pfad, 320, 200, k["pic"].set_paintable)
        else:
            k["pic"].set_paintable(None)
