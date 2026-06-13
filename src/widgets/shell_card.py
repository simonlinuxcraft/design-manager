"""Vorschaukarte für ein GNOME-Shell-Design.

Da Shell-Designs kein echtes Vorschaubild haben, malen wir eine kleine
Topbar-Attrappe: ein Balken in der Panel-Farbe des Designs, mit angedeuteten
Elementen (Aktivitäten-Punkt links, Uhr in der Mitte, Akzent-Indikator rechts).
Die Farben kommen aus core/shell_preview; die Indikatorfarbe leiten wir per
Kontrast zum Panel ab, damit sie auf hellen wie dunklen Panels sichtbar ist.
"""

import math

from gi.repository import Gtk

from src.core import shell_preview


TOPBAR_HOEHE = 40


class ShellCard(Gtk.FlowBoxChild):
    """Anklickbare Vorschaukarte für genau ein Shell-Design."""

    def __init__(self, theme_name, anzeige_name, aktiv):
        super().__init__()
        self.theme_name = theme_name  # "" steht für das Standard-Design
        self.add_css_class("theme-card")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(self._topbar(theme_name))

        name_label = Gtk.Label(label=anzeige_name, xalign=0)
        name_label.add_css_class("card-title")
        name_label.set_ellipsize(3)  # lange Namen kürzen
        box.append(name_label)

        self._status = Gtk.Label(xalign=0)
        self._status.add_css_class("card-status")
        box.append(self._status)

        self.set_child(box)
        self.set_aktiv(aktiv)

    def _topbar(self, theme_name):
        farben = shell_preview.colors(theme_name)
        area = Gtk.DrawingArea()
        area.set_content_height(TOPBAR_HOEHE)
        area.add_css_class("shell-topbar")
        area.set_draw_func(self._zeichne, farben)
        return area

    def _zeichne(self, _area, cr, breite, hoehe, farben):
        panel = farben["panel"]
        # Indikatorfarbe per Kontrast: helle Elemente auf dunklem Panel, sonst dunkel.
        hell = 0.2126 * panel[0] + 0.7152 * panel[1] + 0.0722 * panel[2] < 0.5
        ind = (0.93, 0.93, 0.93) if hell else (0.12, 0.12, 0.12)

        self._runde_rechteck(cr, 0, 0, breite, hoehe, 8)
        cr.set_source_rgb(*panel)
        cr.fill()

        mitte_y = hoehe / 2

        # Aktivitäten-Punkt links.
        cr.set_source_rgba(ind[0], ind[1], ind[2], 0.85)
        cr.arc(15, mitte_y, 3, 0, 2 * math.pi)
        cr.fill()

        # Uhr-Balken in der Mitte.
        cr.rectangle(breite / 2 - 13, mitte_y - 2.5, 26, 5)
        cr.fill()

        # Systemmenü rechts: in Akzentfarbe, falls erkannt, sonst Indikatorfarbe.
        akzent = farben["akzent"] or ind
        cr.set_source_rgb(*akzent)
        cr.arc(breite - 17, mitte_y, 4.5, 0, 2 * math.pi)
        cr.fill()

    def _runde_rechteck(self, cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
        cr.close_path()

    def set_aktiv(self, aktiv):
        if aktiv:
            self.add_css_class("aktiv")
            self._status.set_text("Aktiv")
        else:
            self.remove_css_class("aktiv")
            self._status.set_text("Installiert")
