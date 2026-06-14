"""Kuratierte Komplett-Looks laden und anwenden.

Ein Look ist ein stimmiges Set aus GTK-Design, Symbolen, Akzentfarbe, Schrift
und optional einem Hintergrundbild. Die mitgelieferten Looks liegen als JSON
unter data/looks/. Jedes Feld ist optional.

Anwenden ist bewusst defensiv: Erst wird der aktuelle Stand als Profil
"vorher-<name>" gesichert (ein Klick zurück über die Sicherungsseite genügt),
dann werden nur die Teile gesetzt, die auf diesem System wirklich vorhanden
sind. Fehlende Teile werden übersprungen und zurückgemeldet, statt einen
ungültigen Wert zu setzen.
"""

import json
import os

from gi.repository import GLib

from src.core import backgrounds, backup, themes
from src.core.settings import AppSettings


# data/looks/ liegt in der Projektwurzel (src/core/looks.py -> zwei Ebenen hoch).
LOOKS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "looks")


def lade_looks():
    """Alle mitgelieferten Looks als Liste von Dicts, nach Name sortiert."""
    looks = []
    try:
        dateien = os.listdir(LOOKS_DIR)
    except OSError:
        return []
    for datei in sorted(dateien):
        if not datei.endswith(".json"):
            continue
        try:
            with open(os.path.join(LOOKS_DIR, datei)) as f:
                daten = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(daten, dict) and daten.get("name"):
            looks.append(daten)
    return sorted(looks, key=lambda look: look["name"].lower())


def _profil_wert(daten, schema, key):
    """Liest einen gesicherten String-Wert (GVariant-Text) aus Profildaten."""
    text = daten.get("einstellungen", {}).get(schema, {}).get(key)
    if not text:
        return ""
    try:
        return GLib.Variant.parse(
            GLib.VariantType.new("s"), text, None, None).get_string()
    except (GLib.Error, TypeError):
        return ""


def eigene_profile_als_looks():
    """Gespeicherte Profile als look-ähnliche Dicts für die Vorschaukarten.

    Ein Profil enthält bereits alle Werte, aus denen die Look-Karte ihre
    Vorschau baut (Akzentfarbe, Symbole, Hintergrundbild). Wir leiten sie daraus
    ab und markieren das Dict mit '_profil', damit ein Klick es als Profil
    anwendet (backup.load_profile), nicht als kuratierten Look.
    """
    ergebnis = []
    for name in backup.list_profiles():
        try:
            with open(os.path.join(backup.PROFIL_DIR, name + ".json")) as f:
                daten = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(daten, dict):
            continue
        look = {"name": name, "_profil": name, "beschreibung": "Eigenes Profil"}
        accent = _profil_wert(daten, AppSettings.INTERFACE, "accent-color")
        if accent:
            look["accent"] = accent
        icons = _profil_wert(daten, AppSettings.INTERFACE, "icon-theme")
        if icons:
            look["icons"] = icons
        uri = _profil_wert(daten, AppSettings.BACKGROUND, "picture-uri")
        if uri:
            try:
                look["wallpaper"], _ = GLib.filename_from_uri(uri)
            except (GLib.Error, TypeError):
                pass
        ergebnis.append(look)
    return ergebnis


def wende_an(settings, look):
    """Wendet einen Look an und gibt die übersprungenen Teile als Liste zurück.

    Vor der ersten Änderung wird der aktuelle Stand als Profil gesichert.
    """
    try:
        backup.save_profile(settings, "vorher-" + look["name"])
    except (ValueError, OSError):
        pass  # Sicherung ist Komfort, kein Grund das Anwenden abzubrechen

    uebersprungen = []

    gtk = look.get("gtk")
    if gtk:
        if gtk == settings.SAFE_GTK_THEME or gtk in themes.list_gtk_themes():
            settings.set_gtk_theme(gtk)
        else:
            uebersprungen.append("GTK-Design „%s“" % gtk)

    icons = look.get("icons")
    if icons:
        if icons == settings.SAFE_ICON_THEME or icons in themes.list_icon_themes():
            settings.set_icon_theme(icons)
        else:
            uebersprungen.append("Symbole „%s“" % icons)

    cursor = look.get("cursor")
    if cursor:
        if cursor == settings.SAFE_CURSOR_THEME or cursor in themes.list_cursor_themes():
            settings.set_cursor_theme(cursor)
        else:
            uebersprungen.append("Mauszeiger „%s“" % cursor)

    shell = look.get("shell")
    if shell is not None:  # "" ist gültig (GNOME-Standard-Shell)
        if shell == "" or shell in themes.list_shell_themes():
            settings.set_shell_theme(shell)
        else:
            uebersprungen.append("Shell-Design „%s“" % shell)

    accent = look.get("accent")
    if accent:
        if settings.accent_verfuegbar():
            settings.set_accent_color(accent)
        else:
            uebersprungen.append("Akzentfarbe (erst ab GNOME 47)")

    font = look.get("font")
    if font:
        settings.set_font_name(font)

    wallpaper = look.get("wallpaper")
    if wallpaper:
        pfad = os.path.expanduser(wallpaper)
        if os.path.isfile(pfad):
            backgrounds.apply_wallpaper(settings, pfad)
        else:
            uebersprungen.append("Hintergrundbild")

    return uebersprungen
