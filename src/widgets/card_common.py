"""Gemeinsame Bausteine der Vorschaukarten.

Die Status-Zeile (Aktiv/Installiert) ist in jeder Karte gleich aufgebaut und
trägt rechts optional einen Mülleimer, über den sich ein selbst installiertes
Design entfernen lässt. Der Knopf erscheint nur für löschbare Designs.
"""

from gi.repository import Gtk

from src.i18n import _


def status_zeile(karte, loeschbar, on_loeschen):
    """Baut die Status-Zeile der Karte und hängt sie an karte._status.

    'karte' bekommt das Status-Label als Attribut _status (set_aktiv schreibt
    dort hinein). Ist das Design löschbar und ein on_loeschen-Callback gegeben,
    sitzt rechts ein Mülleimer, der on_loeschen(karte) aufruft.
    """
    karte._status = Gtk.Label(xalign=0, hexpand=True)
    karte._status.add_css_class("card-status")

    zeile = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    zeile.append(karte._status)

    if loeschbar and on_loeschen is not None:
        knopf = Gtk.Button(icon_name="user-trash-symbolic")
        knopf.add_css_class("flat")
        knopf.add_css_class("card-trash")
        knopf.set_valign(Gtk.Align.CENTER)
        knopf.set_tooltip_text(_("Remove this theme"))
        # Der Button verarbeitet seinen Klick selbst; die FlowBox wertet ihn
        # darum nicht als Auswahl der Karte.
        knopf.connect("clicked", lambda _b: on_loeschen(karte))
        zeile.append(knopf)

    return zeile
