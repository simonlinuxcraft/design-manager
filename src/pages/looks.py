"""Seite 'Looks'.

Zwei Galerien: oben die mitgelieferten, kuratierten Komplett-Looks (siehe
core/looks.py), darunter die selbst gespeicherten Profile (siehe core/backup.py,
angelegt auf der Sicherungsseite). Beide setzen mit einem Klick einen ganzen
Look. Bei den mitgelieferten Looks wird der aktuelle Stand vorher als Profil
gesichert; fehlende Teile werden übersprungen und im Toast genannt. Ein eigenes
Profil wird unverändert wieder angewendet.
"""

from gi.repository import Adw, Gtk

from src import compat
from src.core import backup, looks
from src.widgets.look_card import LookCard


class LooksPage(compat.PageBase):
    """Navigationsseite mit kuratierten Looks und eigenen Profilen als Karten."""

    def __init__(self, settings):
        super().__init__(title="Looks")
        self._settings = settings

        toolbar = compat.toolbar_view(
            top_bars=[Adw.HeaderBar()], content=self._inhalt())
        self.set_child(toolbar)

    def _inhalt(self):
        self._looks = looks.lade_looks()
        self._profile = looks.eigene_profile_als_looks()
        if not self._looks and not self._profile:
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
            label="Ein Klick setzt den ganzen Look. Bei den mitgelieferten Looks "
                  "wird vorher automatisch ein Profil „vorher-…“ angelegt, sodass "
                  "du zurück kannst.",
            xalign=0)
        untertitel.add_css_class("dim-label")
        untertitel.set_wrap(True)
        box.append(untertitel)

        if self._looks:
            box.append(self._ueberschrift("Mitgelieferte Looks"))
            box.append(self._galerie(self._looks, self._on_look_aktiviert))

        if self._profile:
            box.append(self._ueberschrift("Eigene Profile"))
            box.append(self._galerie(self._profile, self._on_profil_aktiviert))

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)
        return scroll

    def _ueberschrift(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("heading")
        label.set_margin_top(6)
        return label

    def _galerie(self, looks_liste, handler):
        flowbox = Gtk.FlowBox()
        flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        flowbox.set_max_children_per_line(3)
        flowbox.set_min_children_per_line(1)
        flowbox.set_column_spacing(10)
        flowbox.set_row_spacing(10)
        flowbox.set_homogeneous(True)
        flowbox.set_hexpand(True)
        flowbox.connect("child-activated", handler)
        for look in looks_liste:
            flowbox.append(LookCard(look))
        return flowbox

    # --- Mitgelieferte Looks ---

    def _on_look_aktiviert(self, _flowbox, karte):
        look = karte.look
        compat.alert(
            self,
            "Look „%s“ anwenden?" % look.get("name", ""),
            "Der aktuelle Stand wird zuerst als Profil gesichert. Nicht "
            "installierte Teile werden übersprungen.",
            [("abbrechen", "Abbrechen", ""),
             ("anwenden", "Anwenden", "suggested")],
            default="abbrechen", close="abbrechen",
            on_response=lambda antwort: self._on_look_antwort(antwort, look))

    def _on_look_antwort(self, antwort, look):
        if antwort != "anwenden":
            return
        uebersprungen = looks.wende_an(self._settings, look)
        if uebersprungen:
            self._melde("Look „%s“ angewendet. Übersprungen: %s."
                        % (look.get("name", ""), ", ".join(uebersprungen)))
        else:
            self._melde("Look „%s“ angewendet." % look.get("name", ""))

    # --- Eigene Profile ---

    def _on_profil_aktiviert(self, _flowbox, karte):
        name = karte.look.get("_profil", "")
        compat.alert(
            self,
            "Profil „%s“ anwenden?" % name,
            "Setzt den gespeicherten Stand dieses Profils.",
            [("abbrechen", "Abbrechen", ""),
             ("anwenden", "Anwenden", "suggested")],
            default="abbrechen", close="abbrechen",
            on_response=lambda antwort: self._on_profil_antwort(antwort, name))

    def _on_profil_antwort(self, antwort, name):
        if antwort != "anwenden":
            return
        try:
            erfolg = backup.load_profile(self._settings, name)
        except (OSError, ValueError):
            self._melde("Das Profil konnte nicht gelesen werden.")
            return
        if not erfolg:
            self._melde("Das Profil ist beschädigt.")
            return
        self._melde("Profil „%s“ angewendet. App neu starten, um die Auswahl in "
                    "den einzelnen Bereichen zu aktualisieren." % name)

    def _melde(self, text):
        fenster = self.get_root()
        if fenster is not None and hasattr(fenster, "zeige_toast"):
            fenster.zeige_toast(text)
