"""Mehrere selbst installierte Designs auf einmal entfernen.

Ein Knopf für die Kopfleiste der Seiten GTK Theme, Symbole, Mauszeiger und
Shell Theme. Er öffnet den Auswahl-Dialog mit allen Designs, die im Home liegen
(Yaru, Adwaita und Systemdesigns tauchen nie auf, siehe uninstaller), fragt
dann noch einmal nach und löscht im Hintergrund, damit die App bei vielen
Designs nicht hängt.
"""

import threading

from gi.repository import Adw, GLib, Gtk

from src import compat
from src.core import restorepoint, themes, uninstaller
from src.i18n import _, ngettext
from src.widgets.paket_auswahl import AuswahlDialog


LISTEN = {
    "gtk": themes.list_gtk_themes,
    "icon": themes.list_icon_themes,
    "cursor": themes.list_cursor_themes,
    "shell": themes.list_shell_themes,
}


def kopfleiste(seite, settings, kategorie):
    """Kopfleiste der Seite mit dem Mülleimer-Knopf rechts."""
    b = Gtk.Button(icon_name="user-trash-symbolic")
    b.set_tooltip_text(_("Remove several themes…"))
    b.connect("clicked", lambda _b: _oeffne(seite, settings, kategorie))
    header = Adw.HeaderBar()
    header.pack_end(b)
    return header


def _aktive(settings):
    return {settings.gtk_theme(), settings.icon_theme(),
            settings.cursor_theme(), settings.shell_theme()}


def _oeffne(seite, settings, kategorie):
    namen = [n for n in LISTEN[kategorie]()
             if uninstaller.ist_loeschbar(n, kategorie)]
    if not namen:
        _melde(seite, _("Nothing to remove: only built-in themes are "
                        "installed here."))
        return
    aktiv = _aktive(settings)
    eintraege = [(n, n, _("Active") if n in aktiv else "") for n in namen]
    compat.dialog_present(AuswahlDialog(
        _("Remove themes"),
        _("Only themes in your user folder are listed. Built-in themes like "
          "Yaru and Adwaita stay."),
        eintraege, _("Remove ({n})"), _("Remove"),
        lambda wahl: wahl and _bestaetige(seite, settings, kategorie, wahl),
        destruktiv=True), seite.get_root())


def _bestaetige(seite, settings, kategorie, wahl):
    compat.alert(
        seite,
        ngettext("Remove {n} theme permanently?",
                 "Remove {n} themes permanently?", len(wahl)).format(n=len(wahl)),
        _("They are deleted from your user folder. This cannot be undone."),
        [("abbrechen", _("Cancel"), ""),
         ("loeschen", _("Remove"), "destructive")],
        default="abbrechen", close="abbrechen",
        on_response=lambda antwort: (
            _entferne(seite, settings, kategorie, wahl)
            if antwort == "loeschen" else None))


def _entferne(seite, settings, kategorie, wahl):
    # Erst im Hauptthread die Einstellungen auf sichere Standards, falls ein
    # gewähltes Design gerade aktiv ist. GTK- und Shell-Design teilen oft einen
    # Ordner, ebenso Symbole und Mauszeiger: darum jeweils beide prüfen.
    restorepoint.erstelle(settings, _("before removing themes"))
    weg = set(wahl)
    if kategorie in ("gtk", "shell"):
        if settings.gtk_theme() in weg:
            settings.reset_gtk_theme()
        if settings.shell_theme() in weg:
            settings.reset_shell_theme()
    else:
        if settings.icon_theme() in weg:
            settings.reset_icon_theme()
        if settings.cursor_theme() in weg:
            settings.reset_cursor_theme()

    fenster = seite.get_root()  # jetzt merken, die Seite wird danach neu gebaut

    def worker():
        fehler = [n for n in wahl if not uninstaller.deinstalliere(n, kategorie)]
        GLib.idle_add(_fertig, fenster, len(wahl) - len(fehler), fehler)

    threading.Thread(target=worker, daemon=True).start()


def _fertig(fenster, anzahl, fehler):
    text = ngettext("Removed {n} theme.", "Removed {n} themes.",
                    anzahl).format(n=anzahl)
    if fehler:
        text += " " + _("Could not be removed: {name}").format(
            name=", ".join(fehler))
    if fenster is not None and hasattr(fenster, "melde_und_reload"):
        fenster.melde_und_reload(text)
    return GLib.SOURCE_REMOVE


def _melde(seite, text):
    fenster = seite.get_root()
    if fenster is not None and hasattr(fenster, "zeige_toast"):
        fenster.zeige_toast(text)
