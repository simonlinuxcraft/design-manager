"""Seite 'Looks'.

Zwei Galerien: oben die mitgelieferten, kuratierten Komplett-Looks (siehe
core/looks.py), darunter die selbst gespeicherten Profile. Profile werden hier
zentral verwaltet: aktuellen Stand als Profil speichern, per Klick anwenden,
über den Knopf an der Karte löschen. Bei den mitgelieferten Looks wird der
aktuelle Stand vorher als Sicherungspunkt festgehalten; fehlende Teile werden
übersprungen und im Toast genannt.

Nach dem Anwenden baut das Fenster alle Seiten neu (melde_und_reload), damit die
übrigen Bereiche sofort den neuen Stand zeigen, ohne Neustart.
"""

from gi.repository import Adw, Gtk

from src import compat
from src.core import backup, looks
from src.i18n import _
from src.widgets.look_card import LookCard


class LooksPage(compat.PageBase):
    """Navigationsseite mit kuratierten Looks und eigenen Profilen als Karten."""

    def __init__(self, settings):
        super().__init__(title=_("Looks"))
        self._settings = settings

        toolbar = compat.toolbar_view(
            top_bars=[Adw.HeaderBar()], content=self._inhalt())
        self.set_child(toolbar)

    def _inhalt(self):
        self._looks = looks.lade_looks()
        self._profile = looks.eigene_profile_als_looks()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(18)
        box.set_margin_end(18)

        untertitel = Gtk.Label(
            label=_("One click applies the whole look. For bundled looks a "
                    "restore point is created first, so you can go back from "
                    "the Backup page."),
            xalign=0)
        untertitel.add_css_class("dim-label")
        untertitel.set_wrap(True)
        box.append(untertitel)

        if self._looks:
            box.append(self._ueberschrift(_("Bundled looks")))
            box.append(self._galerie(self._looks, self._on_look_aktiviert))

        box.append(self._ueberschrift(_("Your profiles")))
        box.append(self._speicher_gruppe())
        if self._profile:
            box.append(self._galerie(
                self._profile, self._on_profil_aktiviert,
                self._on_profil_loeschen))

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(box)
        return scroll

    def _ueberschrift(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("heading")
        label.set_margin_top(6)
        return label

    def _speicher_gruppe(self):
        """Eingabezeile, um den aktuellen Stand als Profil zu sichern."""
        gruppe = Adw.PreferencesGroup()
        self._name_entry = compat.EntryRow(
            title=_("Save the current look as a profile"))
        self._name_entry.set_show_apply_button(True)
        self._name_entry.connect("apply", self._on_profil_speichern)
        gruppe.add(self._name_entry)
        return gruppe

    def _galerie(self, looks_liste, handler, loesch_handler=None):
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
            flowbox.append(LookCard(look, on_loeschen=loesch_handler))
        return flowbox

    # --- Mitgelieferte Looks ---

    def _on_look_aktiviert(self, _flowbox, karte):
        look = karte.look
        compat.alert(
            self,
            _('Apply look "{name}"?').format(name=look.get("name", "")),
            _("The current state is saved as a restore point first. Parts that "
              "are not installed are skipped."),
            [("abbrechen", _("Cancel"), ""),
             ("anwenden", _("Apply"), "suggested")],
            default="abbrechen", close="abbrechen",
            on_response=lambda antwort: self._on_look_antwort(antwort, look))

    def _on_look_antwort(self, antwort, look):
        if antwort != "anwenden":
            return
        uebersprungen = looks.wende_an(self._settings, look)
        if uebersprungen:
            self._melde_und_reload(
                _('Look "{name}" applied. Skipped: {items}.').format(
                    name=look.get("name", ""),
                    items=", ".join(uebersprungen)))
        else:
            self._melde_und_reload(
                _('Look "{name}" applied.').format(name=look.get("name", "")))

    # --- Eigene Profile ---

    def _on_profil_speichern(self, entry):
        try:
            gespeichert = backup.save_profile(self._settings, entry.get_text())
        except ValueError:
            self._melde(_("Please enter a name."))
            return
        except OSError as fehler:
            self._melde(_("Saving failed: {error}").format(
                error=fehler.strerror or _("Error")))
            return
        entry.set_text("")
        # Neu aufbauen, damit die frisch gespeicherte Profil-Karte erscheint.
        self._melde_und_reload(
            _("Profile saved: {name}").format(name=gespeichert))

    def _on_profil_aktiviert(self, _flowbox, karte):
        name = karte.look.get("_profil", "")
        compat.alert(
            self,
            _('Apply profile "{name}"?').format(name=name),
            _("Applies this profile's saved state."),
            [("abbrechen", _("Cancel"), ""),
             ("anwenden", _("Apply"), "suggested")],
            default="abbrechen", close="abbrechen",
            on_response=lambda antwort: self._on_profil_antwort(antwort, name))

    def _on_profil_antwort(self, antwort, name):
        if antwort != "anwenden":
            return
        try:
            erfolg = backup.load_profile(self._settings, name)
        except (OSError, ValueError):
            self._melde(_("The profile could not be read."))
            return
        if not erfolg:
            self._melde(_("The profile is damaged."))
            return
        self._melde_und_reload(
            _('Profile "{name}" applied.').format(name=name))

    def _on_profil_loeschen(self, look):
        name = look.get("_profil", "")
        if not name:
            return
        backup.delete_profile(name)
        self._melde_und_reload(_("Profile deleted: {name}").format(name=name))

    # --- Rückmeldung ans Fenster ---

    def _melde(self, text):
        fenster = self.get_root()
        if fenster is not None and hasattr(fenster, "zeige_toast"):
            fenster.zeige_toast(text)

    def _melde_und_reload(self, text):
        """Toast zeigen und alle Seiten neu bauen.

        Geht über das Fenster (melde_und_reload), weil ein Look-/Profilwechsel
        mehrere Bereiche betrifft und auch diese Looks-Seite selbst neu gebaut
        wird (damit die Profilliste stimmt).
        """
        fenster = self.get_root()
        if fenster is not None and hasattr(fenster, "melde_und_reload"):
            fenster.melde_und_reload(text)
        else:
            self._melde(text)
