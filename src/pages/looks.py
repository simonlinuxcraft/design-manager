"""Seite 'Looks'.

Eine Galerie mitgelieferter, stimmiger Komplett-Looks (siehe core/looks.py). Ein
Klick wendet einen Look an, nachdem der aktuelle Stand automatisch als Profil
gesichert wurde. Teile, die auf diesem System fehlen (z.B. ein nicht
installiertes Design), werden übersprungen und im Toast genannt.
"""

from gi.repository import Adw, Gtk

from src.core import looks
from src.widgets.look_card import LookCard


class LooksPage(Adw.NavigationPage):
    """Navigationsseite mit den kuratierten Looks als Vorschaukarten."""

    def __init__(self, settings):
        super().__init__(title="Looks")
        self._settings = settings

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(self._inhalt())
        self.set_child(toolbar)

    def _inhalt(self):
        self._looks = looks.lade_looks()
        if not self._looks:
            return Adw.StatusPage(
                title="Keine Looks gefunden",
                description="Mitgelieferte Looks liegen unter data/looks/.",
                icon_name="starred-symbolic")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        untertitel = Gtk.Label(
            label="Ein Klick setzt den ganzen Look. Vorher wird automatisch ein "
                  "Profil „vorher-…“ angelegt, sodass du zurück kannst.",
            xalign=0)
        untertitel.add_css_class("dim-label")
        untertitel.set_wrap(True)
        box.append(untertitel)

        flowbox = Gtk.FlowBox()
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        flowbox.set_max_children_per_line(3)
        flowbox.set_min_children_per_line(1)
        flowbox.set_column_spacing(10)
        flowbox.set_row_spacing(10)
        flowbox.set_homogeneous(True)
        flowbox.set_hexpand(True)
        flowbox.connect("child-activated", self._on_aktiviert)
        for look in self._looks:
            flowbox.append(LookCard(look))
        box.append(flowbox)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)
        return scroll

    def _on_aktiviert(self, _flowbox, karte):
        look = karte.look
        dialog = Adw.AlertDialog(
            heading="Look „%s“ anwenden?" % look.get("name", ""),
            body="Der aktuelle Stand wird zuerst als Profil gesichert. Nicht "
                 "installierte Teile werden übersprungen.")
        dialog.add_response("abbrechen", "Abbrechen")
        dialog.add_response("anwenden", "Anwenden")
        dialog.set_response_appearance(
            "anwenden", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("abbrechen")
        dialog.set_close_response("abbrechen")
        dialog.connect("response", self._on_antwort, look)
        dialog.present(self)

    def _on_antwort(self, _dialog, antwort, look):
        if antwort != "anwenden":
            return
        uebersprungen = looks.wende_an(self._settings, look)
        if uebersprungen:
            self._melde("Look „%s“ angewendet. Übersprungen: %s."
                        % (look.get("name", ""), ", ".join(uebersprungen)))
        else:
            self._melde("Look „%s“ angewendet." % look.get("name", ""))

    def _melde(self, text):
        fenster = self.get_root()
        if fenster is not None and hasattr(fenster, "zeige_toast"):
            fenster.zeige_toast(text)
