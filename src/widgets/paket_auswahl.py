"""Auswahl-Dialog für All-in-one-Pakete.

Pakete wie Flat-Remix bringen Dutzende Varianten mit (jede Farbe hell, dunkel,
solid ...). Alles zu installieren würde die Listen der App überfluten, darum
wählt man hier aus. Ein Suchfeld filtert ("Blue", "Dark"), "Alle sichtbaren"
hakt die gefilterten Einträge an. Abbrechen installiert nichts.
"""

from gi.repository import Adw, GLib, Gtk

from src import compat
from src.i18n import _, ngettext


class PaketAuswahl(compat.DialogBase):
    """Fragt, welche Funde eines Pakets installiert werden.

    on_fertig(auswahl) bekommt die Liste der gewählten Funde oder None bei
    Abbruch, genau einmal.
    """

    def __init__(self, dateiname, funde, on_fertig):
        super().__init__()
        compat.dialog_setup(self, _("Choose what to install"), 520, 640)
        self._on_fertig = on_fertig
        self._zeilen = []  # (zeile, haken, fund)

        info = Gtk.Label(
            label=ngettext("{file} contains {n} theme. Choose what you want.",
                           "{file} contains {n} themes. Choose what you want.",
                           len(funde)).format(file=dateiname, n=len(funde)),
            xalign=0, wrap=True)
        info.add_css_class("dim-label")

        self._suche = Gtk.SearchEntry()
        self._suche.props.placeholder_text = _("Filter, e.g. Blue or Dark")
        self._suche.connect("search-changed", self._on_suche)

        self._liste = Gtk.ListBox()
        self._liste.add_css_class("boxed-list")
        self._liste.set_selection_mode(Gtk.SelectionMode.NONE)
        self._liste.set_valign(Gtk.Align.START)  # kein leerer Kasten unter wenigen Treffern
        self._liste.set_filter_func(self._passt)
        for fund in sorted(funde, key=lambda f: f.name.lower()):
            haken = Gtk.CheckButton()
            haken.set_valign(Gtk.Align.CENTER)
            haken.connect("toggled", self._zaehle)
            zeile = Adw.ActionRow(title=GLib.markup_escape_text(fund.name),
                                  subtitle=GLib.markup_escape_text(
                                      fund.beschreibung()))
            zeile.add_prefix(haken)
            zeile.set_activatable_widget(haken)
            zeile.fund_name = fund.name.lower()
            self._liste.append(zeile)
            self._zeilen.append((zeile, haken, fund))

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_min_content_height(280)
        scroll.set_child(self._liste)

        inhalt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for rand in ("top", "bottom", "start", "end"):
            getattr(inhalt, "set_margin_" + rand)(16)
        inhalt.append(info)
        inhalt.append(self._suche)
        inhalt.append(scroll)

        alle = Gtk.Button(label=_("Select all shown"))
        alle.add_css_class("flat")
        alle.connect("clicked", self._on_alle)
        abbrechen = Gtk.Button(label=_("Cancel"))
        abbrechen.connect("clicked", lambda _b: self._beenden(None))
        self._installieren = Gtk.Button()
        self._installieren.add_css_class("suggested-action")
        self._installieren.connect("clicked", self._on_installieren)

        knoepfe = Gtk.Box(spacing=8)
        for rand in ("top", "bottom", "start", "end"):
            getattr(knoepfe, "set_margin_" + rand)(12)
        luecke = Gtk.Box(hexpand=True)
        for w in (alle, luecke, abbrechen, self._installieren):
            knoepfe.append(w)

        header = Adw.HeaderBar()
        header.add_css_class("flat")
        compat.dialog_set_content(self, compat.toolbar_view(
            top_bars=[header], content=inhalt, bottom_bars=[knoepfe]))
        self.connect("closed" if compat._DIALOG_MODERN else "close-request",
                     self._on_zu)
        self._zaehle()

    # --- Auswahl ---

    def _passt(self, zeile):
        text = self._suche.get_text().strip().lower()
        return all(teil in zeile.fund_name for teil in text.split())

    def _on_suche(self, _suche):
        self._liste.invalidate_filter()

    def _on_alle(self, _knopf):
        for zeile, haken, _fund in self._zeilen:
            if self._passt(zeile):
                haken.set_active(True)

    def _gewaehlt(self):
        return [fund for _z, haken, fund in self._zeilen if haken.get_active()]

    def _zaehle(self, *_args):
        n = len(self._gewaehlt())
        self._installieren.set_label(
            _("Install ({n})").format(n=n) if n else _("Install"))
        self._installieren.set_sensitive(n > 0)

    # --- Abschluss ---

    def _on_installieren(self, _knopf):
        self._beenden(self._gewaehlt())

    def _beenden(self, auswahl):
        melden, self._on_fertig = self._on_fertig, None
        self.close()
        if melden is not None:
            melden(auswahl)

    def _on_zu(self, *_args):
        # Schließen per X/Escape zählt als Abbruch.
        if self._on_fertig is not None:
            melden, self._on_fertig = self._on_fertig, None
            melden(None)
        return False
