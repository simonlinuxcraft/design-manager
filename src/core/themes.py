"""Installierte Designs auflisten.

Designs sind einfach Ordner an festen Orten. Ein gültiges Design hat eine
Datei "index.theme". Wir durchsuchen die Standard-Verzeichnisse und sammeln
die Namen ein. Schritt 3 braucht davon nur die Symbol-Designs (Icons);
GTK- und Mauszeiger-Designs kommen in einem späteren Schritt dazu.
"""

import os


# Such-Orte für Symbole und Mauszeiger. Reihenfolge: zuerst die des Nutzers,
# dann systemweit. /usr/share/... ist schreibgeschützt (nur lesen).
ICON_DIRS = [
    os.path.expanduser("~/.icons"),
    os.path.expanduser("~/.local/share/icons"),
    "/usr/share/icons",
]

# Such-Orte für GTK- und Shell-Designs.
THEME_DIRS = [
    os.path.expanduser("~/.themes"),
    os.path.expanduser("~/.local/share/themes"),
    "/usr/share/themes",
]

# Technische Basis-/Fallback-Designs, die der Nutzer nicht wählen soll.
VERSTECKTE_THEMES = {"hicolor", "default", "locolor"}


def _ordner_in(suchpfade):
    """Alle direkten Unterordner (name, pfad) aus den Suchpfaden.

    Im Gegensatz zu _theme_ordner verlangt das hier keine index.theme. GTK-
    und Mauszeiger-Designs erkennt man an bestimmten Unterordnern, nicht an
    einer index.theme-Datei.
    """
    for basis in suchpfade:
        if not os.path.isdir(basis):
            continue
        for name in sorted(os.listdir(basis)):
            pfad = os.path.join(basis, name)
            if os.path.isdir(pfad):
                yield name, pfad


def _theme_ordner(suchpfade):
    """Alle Ordner mit einer index.theme-Datei aus den Suchpfaden.

    Liefert Tupel (name, pfad). Derselbe Name kann in mehreren Pfaden
    vorkommen; das Entfernen von Duplikaten passiert weiter oben.
    """
    gefunden = []
    for basis in suchpfade:
        if not os.path.isdir(basis):
            continue
        for name in sorted(os.listdir(basis)):
            pfad = os.path.join(basis, name)
            if os.path.isfile(os.path.join(pfad, "index.theme")):
                gefunden.append((name, pfad))
    return gefunden


def _ist_reines_cursor_theme(pfad):
    """True, wenn der Ordner nur einen Mauszeiger enthält, aber keine Icons.

    Mauszeiger liegen im Unterordner cursors/. Ein Symbol-Design hat zusätzlich
    Ordner mit Icon-Größen (16x16, scalable, ...). Enthält ein Ordner *nur*
    cursors/, ist es ein reines Mauszeiger-Design und gehört nicht in die
    Icon-Liste.
    """
    if not os.path.isdir(os.path.join(pfad, "cursors")):
        return False
    for name in os.listdir(pfad):
        if name == "cursors":
            continue
        if os.path.isdir(os.path.join(pfad, name)):
            return False  # noch andere Unterordner -> enthält Icons
    return True


def list_icon_themes():
    """Namen aller installierten Symbol-Designs, alphabetisch, ohne Duplikate."""
    namen = set()
    for name, pfad in _theme_ordner(ICON_DIRS):
        if name in VERSTECKTE_THEMES:
            continue
        if _ist_reines_cursor_theme(pfad):
            continue
        namen.add(name)
    return sorted(namen, key=str.lower)


def list_gtk_themes():
    """Namen aller GTK-Designs, alphabetisch, ohne Duplikate.

    Ein GTK-Design erkennt man an einem Unterordner gtk-3.0 oder gtk-4.0
    (dort liegt die gtk.css). Ordner, die nur ein gnome-shell/ enthalten, sind
    reine Shell-Designs und tauchen hier nicht auf.
    """
    namen = set()
    for name, pfad in _ordner_in(THEME_DIRS):
        hat_gtk = (
            os.path.isdir(os.path.join(pfad, "gtk-3.0"))
            or os.path.isdir(os.path.join(pfad, "gtk-4.0"))
        )
        if hat_gtk:
            namen.add(name)
    return sorted(namen, key=str.lower)


def list_cursor_themes():
    """Namen aller Mauszeiger-Designs, alphabetisch, ohne Duplikate.

    Erkennungsmerkmal ist der Unterordner cursors/ (siehe Projektnotiz).
    """
    namen = set()
    for name, pfad in _ordner_in(ICON_DIRS):
        if name in VERSTECKTE_THEMES:
            continue
        if os.path.isdir(os.path.join(pfad, "cursors")):
            namen.add(name)
    return sorted(namen, key=str.lower)


def list_shell_themes():
    """Namen aller GNOME-Shell-Designs, alphabetisch, ohne Duplikate.

    Ein Shell-Design erkennt man am Unterordner gnome-shell/ (dort liegt die
    gnome-shell.css). Das Design wird über die Erweiterung „User Themes"
    gesetzt; rein optisch wirkt es auf Topbar, Kalender und Schnelleinstellungen.
    """
    namen = set()
    for name, pfad in _ordner_in(THEME_DIRS):
        if name in VERSTECKTE_THEMES:
            continue
        if os.path.isdir(os.path.join(pfad, "gnome-shell")):
            namen.add(name)
    return sorted(namen, key=str.lower)
