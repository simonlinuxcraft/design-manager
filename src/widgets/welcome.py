"""Willkommens-Dialog beim ersten Start.

Eine kurze Einführung über mehrere Karten: was die App kann und wie Profile
funktionieren. Es wird immer genau eine Karte voll angezeigt (Gtk.Stack mit
Schiebe-Übergang). Unten Fortschrittspunkte und ein Knopf, der von Karte zu
Karte führt und auf der letzten den Dialog schließt.

Bewusst kein Adw.Carousel: das gibt jeder Karte nur ihre schmale natürliche
Breite und lässt die Nachbarkarte hereinragen.
"""

import os

from gi.repository import Adw, Gdk, Gtk

from src import compat
from src.i18n import _


# Das App-Logo liegt in der Projektwurzel, zwei Ebenen über src/widgets/.
LOGO_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "design-manager-transparent-1024.png",
)

# Inhalt der Karten: Symbolname (oder None für das Logo), Titel, Beschreibung.
KARTEN = [
    (None, "Design Manager",
     _("Customize the GNOME desktop appearance in one place.")),
    ("applications-graphics-symbolic", _("Everything in one place"),
     _("Background, GTK theme, icons, cursor, fonts and the shell theme. "
       "Every change takes effect immediately.")),
    ("document-save-symbolic", _("Save looks"),
     _("Create profiles, for example day and night, and switch with one "
       "click. Or back up everything to a file.")),
    ("emblem-default-symbolic", _("Ready"),
     _("Tip: some shell themes need the User Themes extension. "
       "Have fun customizing.")),
]


class WelcomeDialog(compat.DialogBase):
    """Mehrseitige Einführung, gezeigt beim ersten Programmstart."""

    def __init__(self):
        super().__init__()
        compat.dialog_setup(self, _("Welcome"), 460, 580)
        self._index = 0

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_transition_duration(200)
        self._stack.set_vexpand(True)
        for i, (icon, titel, text) in enumerate(KARTEN):
            self._stack.add_named(self._karte(icon, titel, text), str(i))

        header = Adw.HeaderBar()
        header.add_css_class("flat")

        self._weiter = Gtk.Button(label=_("Next"))
        self._weiter.set_hexpand(True)
        self._weiter.add_css_class("pill")
        self._weiter.add_css_class("suggested-action")
        self._weiter.connect("clicked", self._on_weiter)

        knopf_box = Gtk.Box()
        knopf_box.set_margin_top(6)
        knopf_box.set_margin_bottom(12)
        knopf_box.set_margin_start(18)
        knopf_box.set_margin_end(18)
        knopf_box.append(self._weiter)

        toolbar = compat.toolbar_view(
            top_bars=[header], content=self._stack,
            bottom_bars=[self._punkt_leiste(len(KARTEN)), knopf_box])
        compat.dialog_set_content(self, toolbar)

    # --- Karten ---

    def _karte(self, icon_name, titel, text):
        """Eine Karte als zentrierte Adw.StatusPage. Der Stack gibt ihr die
        volle Breite, sodass immer genau eine Karte sichtbar ist."""
        seite = Adw.StatusPage()
        seite.set_title(titel)
        seite.set_description(text)
        if icon_name is None and os.path.isfile(LOGO_FILE):
            seite.set_paintable(Gdk.Texture.new_from_filename(LOGO_FILE))
        else:
            seite.set_icon_name(icon_name or "applications-graphics-symbolic")
        return seite

    # --- Fortschrittspunkte ---

    def _punkt_leiste(self, anzahl):
        leiste = Gtk.Box(spacing=7)
        leiste.set_halign(Gtk.Align.CENTER)
        leiste.add_css_class("onboarding-dots")

        self._punkte = []
        for i in range(anzahl):
            punkt = Gtk.Box()
            punkt.add_css_class("dot")
            if i == 0:
                punkt.add_css_class("aktiv")
            leiste.append(punkt)
            self._punkte.append(punkt)
        return leiste

    # --- Navigation ---

    def _on_weiter(self, _knopf):
        if self._index >= len(KARTEN) - 1:
            self.close()
            return
        self._index += 1
        self._stack.set_visible_child_name(str(self._index))
        self._aktualisiere()

    def _aktualisiere(self):
        for i, punkt in enumerate(self._punkte):
            if i == self._index:
                punkt.add_css_class("aktiv")
            else:
                punkt.remove_css_class("aktiv")
        letzte = self._index >= len(KARTEN) - 1
        self._weiter.set_label(_("Get started") if letzte else _("Next"))
