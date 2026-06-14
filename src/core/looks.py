"""Kuratierte Komplett-Looks laden und anwenden.

Ein Look ist ein stimmiges Set aus Hell/Dunkel-Modus, GTK-Design, Symbolen,
Akzentfarbe, Schrift und optional einem Hintergrundbild. Die mitgelieferten
Looks liegen als JSON unter data/looks/. Jedes Feld ist optional.

Anwenden ist bewusst defensiv: Erst wird der aktuelle Stand als Profil
"vorher-<name>" gesichert (ein Klick zurück über die Sicherungsseite genügt),
dann werden nur die Teile gesetzt, die auf diesem System wirklich vorhanden
sind. Fehlende Teile werden übersprungen und zurückgemeldet, statt einen
ungültigen Wert zu setzen.
"""

import json
import os

from src.core import backgrounds, backup, themes


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


def wende_an(settings, look):
    """Wendet einen Look an und gibt die übersprungenen Teile als Liste zurück.

    Vor der ersten Änderung wird der aktuelle Stand als Profil gesichert.
    """
    try:
        backup.save_profile(settings, "vorher-" + look["name"])
    except (ValueError, OSError):
        pass  # Sicherung ist Komfort, kein Grund das Anwenden abzubrechen

    uebersprungen = []

    wert = look.get("color_scheme")
    if wert:
        settings.set_color_scheme(wert)

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
