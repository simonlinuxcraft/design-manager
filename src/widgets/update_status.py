"""Dezente Update-Anzeige für Designs von gnome-look.org.

StatusSymbol sitzt in der Statuszeile der Karten: grauer Haken (aktuell),
blauer Pfeil (Update verfügbar), Spinner (wird aktualisiert), Warnsymbol
(Problem, Grund im Tooltip). Ohne bekannten Zustand bleibt es unsichtbar.
GnomeLookListe fasst auf der Übersicht alle Einträge mit Zustand zusammen.
"""

import os

from gi.repository import Adw, GLib, Gtk

from src.core import gnomelook
from src.i18n import _

# Eigene Namen (data/icons): manche Icon-Designs liefern die Originale farbig.
_SYMBOLE = {
    gnomelook.AKTUELL: ("dm-status-ok-symbolic", "ok"),
    gnomelook.UPDATE: ("dm-status-update-symbolic", "update"),
    gnomelook.PROBLEM: ("dm-status-problem-symbolic", "problem"),
}


class StatusSymbol(Gtk.Box):
    """Zustand eines Designs (per Name) oder einer Ordnerliste."""

    def __init__(self, name=None, pfade=None):
        super().__init__(valign=Gtk.Align.CENTER)
        self.add_css_class("dm-status")
        self._name, self._pfade = name, pfade
        self._bild = Gtk.Image(pixel_size=14)
        self._spinner = Gtk.Spinner()
        self.append(self._bild)
        self.append(self._spinner)
        gnomelook.beobachte(self)
        self.aktualisiere()

    def aktualisiere(self):
        wert = (gnomelook.zustand(self._pfade) if self._pfade is not None
                else gnomelook.zustand_fuer_name(self._name))
        zustand, text = wert or (None, "")
        self.set_visible(wert is not None)
        self.set_tooltip_text(text or None)
        laeuft = zustand == gnomelook.LAEUFT
        self._spinner.set_visible(laeuft)
        self._spinner.set_spinning(laeuft)
        symbol, klasse = _SYMBOLE.get(zustand, (None, None))
        self._bild.set_visible(symbol is not None)
        if symbol:
            self._bild.set_from_icon_name(symbol)
            self.set_css_classes(["dm-status", klasse])


class GnomeLookListe(Gtk.Box):
    """Abschnitt "Von gnome-look.org" für die Übersicht; leer = unsichtbar."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.set_halign(Gtk.Align.CENTER)
        self.set_size_request(650, -1)

        titel = Gtk.Label(label=_("From gnome-look.org"), xalign=0,
                          hexpand=True)
        titel.add_css_class("feld-titel")
        self._knopf = Gtk.Button(action_name="win.theme-updates")
        self._knopf.add_css_class("flat")
        kopf = Gtk.Box(spacing=8)
        kopf.append(titel)
        kopf.append(self._knopf)
        self.append(kopf)

        self._liste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._liste.add_css_class("boxed-list")
        self.append(self._liste)
        gnomelook.beobachte(self)
        self.aktualisiere()

    def aktualisiere(self):
        while (zeile := self._liste.get_row_at_index(0)) is not None:
            self._liste.remove(zeile)
        eintraege = gnomelook.eintraege()
        offen = False
        for e in sorted(eintraege, key=lambda e: e["titel"].lower()):
            wert = gnomelook.zustand(e["pfade"])
            offen |= wert is not None and wert[0] == gnomelook.UPDATE
            namen = ", ".join(sorted({os.path.basename(p) for p in e["pfade"]}))
            status = wert[1] if wert else _("Not checked yet")
            zeile = Adw.ActionRow(
                title=GLib.markup_escape_text(e["titel"]),
                subtitle=GLib.markup_escape_text(
                    "{names} · {status}".format(names=namen, status=status)))
            zeile.add_suffix(StatusSymbol(pfade=e["pfade"]))
            self._liste.append(zeile)
        self._knopf.set_label(_("Update…") if offen else _("Check now"))
        self.set_visible(bool(eintraege))
