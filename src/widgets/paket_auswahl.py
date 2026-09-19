"""Auswahl-Dialog: eine durchsuchbare Liste mit Haken.

Genutzt für All-in-one-Pakete (welche der Dutzenden Varianten installieren?)
und zum Entfernen mehrerer Designs auf einmal. Ein Suchfeld filtert ("Blue",
"Dark"), "Alle angezeigten" hakt die gefilterten Einträge an, der Knopf zeigt
die Anzahl. Abbrechen oder Schließen liefert None.
"""

from gi.repository import Adw, GLib, Gtk

from src import compat
from src.i18n import _


class AuswahlDialog(compat.DialogBase):
    """Fragt, welche Einträge gemeint sind.

    eintraege: Liste (objekt, titel, untertitel). knopf_mit_zahl enthält {n}.
    on_fertig(liste der gewählten objekte) oder on_fertig(None) bei Abbruch,
    genau einmal. destruktiv färbt den Knopf als gefährliche Aktion, alle_an
    hakt zu Beginn alles an.
    """

    def __init__(self, titel, info, eintraege, knopf_mit_zahl, knopf_ohne_zahl,
                 on_fertig, destruktiv=False, alle_an=False):
        super().__init__()
        compat.dialog_setup(self, titel, 520, 640)
        self._on_fertig = on_fertig
        self._knopf_texte = (knopf_mit_zahl, knopf_ohne_zahl)
        self._zeilen = []  # (zeile, haken, objekt)

        info_label = Gtk.Label(label=info, xalign=0, wrap=True)
        info_label.add_css_class("dim-label")

        self._suche = Gtk.SearchEntry()
        self._suche.props.placeholder_text = _("Filter, e.g. Blue or Dark")
        self._suche.connect("search-changed", self._on_suche)

        self._liste = Gtk.ListBox()
        self._liste.add_css_class("boxed-list")
        self._liste.set_selection_mode(Gtk.SelectionMode.NONE)
        self._liste.set_valign(Gtk.Align.START)  # kein leerer Kasten unter wenigen Treffern
        self._liste.set_filter_func(self._passt)
        for objekt, name, untertitel in sorted(eintraege,
                                               key=lambda e: e[1].lower()):
            haken = Gtk.CheckButton(active=alle_an)
            haken.set_valign(Gtk.Align.CENTER)
            haken.connect("toggled", self._zaehle)
            zeile = Adw.ActionRow(title=GLib.markup_escape_text(name),
                                  subtitle=GLib.markup_escape_text(untertitel))
            zeile.add_prefix(haken)
            zeile.set_activatable_widget(haken)
            zeile.such_name = name.lower()
            self._liste.append(zeile)
            self._zeilen.append((zeile, haken, objekt))

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_min_content_height(280)
        scroll.set_child(self._liste)

        inhalt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for rand in ("top", "bottom", "start", "end"):
            getattr(inhalt, "set_margin_" + rand)(16)
        inhalt.append(info_label)
        inhalt.append(self._suche)
        inhalt.append(scroll)

        alle = Gtk.Button(label=_("Select all shown"))
        alle.add_css_class("flat")
        alle.connect("clicked", self._on_alle)
        abbrechen = Gtk.Button(label=_("Cancel"))
        abbrechen.connect("clicked", lambda _b: self._beenden(None))
        self._aktion = Gtk.Button()
        self._aktion.add_css_class(
            "destructive-action" if destruktiv else "suggested-action")
        self._aktion.connect("clicked", self._on_aktion)

        knoepfe = Gtk.Box(spacing=8)
        for rand in ("top", "bottom", "start", "end"):
            getattr(knoepfe, "set_margin_" + rand)(12)
        luecke = Gtk.Box(hexpand=True)
        for w in (alle, luecke, abbrechen, self._aktion):
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
        return all(teil in zeile.such_name for teil in text.split())

    def _on_suche(self, _suche):
        self._liste.invalidate_filter()

    def _on_alle(self, _knopf):
        for zeile, haken, _objekt in self._zeilen:
            if self._passt(zeile):
                haken.set_active(True)

    def _gewaehlt(self):
        return [objekt for _z, haken, objekt in self._zeilen
                if haken.get_active()]

    def _zaehle(self, *_args):
        n = len(self._gewaehlt())
        mit_zahl, ohne_zahl = self._knopf_texte
        self._aktion.set_label(mit_zahl.format(n=n) if n else ohne_zahl)
        self._aktion.set_sensitive(n > 0)

    # --- Abschluss ---

    def _on_aktion(self, _knopf):
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
