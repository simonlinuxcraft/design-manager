"""Selbst installierte Designs wieder entfernen.

Gelöscht wird nur, was in den Home-Verzeichnissen des Nutzers liegt, nie ein
systemweites Design unter /usr/share (das gehört dem System und ist ohnehin
schreibgeschützt). Vor jedem Löschen prüfen wir über realpath, dass der Ordner
wirklich direkt unter einem erlaubten Home-Verzeichnis sitzt, damit ein
verbogener Symlink im Suchpfad nicht woanders hinführt.

Ein Mauszeiger-Design kann doppelt vorliegen: der echte Ordner unter
~/.local/share/icons und ein Spiegel-Symlink unter ~/.icons (siehe
settings._spiegele_cursor_in_pfad). Beide Vorkommen werden entfernt, der Symlink
per unlink (nur die Verknüpfung), der echte Ordner per rmtree.
"""

import os
import shutil


# Home-Orte je Design-Art, in denen gelöscht werden darf. Bewusst ohne die
# systemweiten /usr/share-Pfade. Symbole und Mauszeiger teilen sich dieselben
# Icon-Ordner, GTK- und Shell-Designs die Theme-Ordner.
_ICON_DIRS = [
    os.path.expanduser("~/.icons"),
    os.path.expanduser("~/.local/share/icons"),
]
_THEME_DIRS = [
    os.path.expanduser("~/.themes"),
    os.path.expanduser("~/.local/share/themes"),
]
LOESCH_DIRS = {
    "icon": _ICON_DIRS,
    "cursor": _ICON_DIRS,
    "gtk": _THEME_DIRS,
    "shell": _THEME_DIRS,
}

# Designs, die nie zum Entfernen angeboten werden, auch wenn eine Home-Kopie
# vorliegt. Yaru ist das Ubuntu-Standarddesign (Fenster, Symbole, Shell,
# Mauszeiger) und darf nicht löschbar sein. Adwaita ist der eingebaute
# Rückfallwert, auf den wir beim Entfernen des aktiven Designs umschalten, also
# ebenfalls tabu. Erfasst auch Varianten wie "Yaru-dark" oder "Yaru-blue".
GESCHUETZT_PRAEFIXE = ("yaru", "adwaita")


def _geschuetzt(name):
    n = name.lower()
    return any(n == p or n.startswith(p + "-") for p in GESCHUETZT_PRAEFIXE)


def home_vorkommen(name, kategorie):
    """Alle löschbaren Pfade (Ordner und Symlinks) dieses Designs im Home.

    Liefert eine Liste; leer, wenn das Design nur systemweit vorliegt oder gar
    nicht. Ein leerer Name (z.B. der "Standard"-Eintrag der Shell-Seite) zählt
    nie als löschbar.
    """
    if not name:
        return []
    treffer = []
    for basis in LOESCH_DIRS.get(kategorie, []):
        pfad = os.path.join(basis, name)
        if os.path.islink(pfad) or os.path.isdir(pfad):
            treffer.append(pfad)
    return treffer


def ist_loeschbar(name, kategorie):
    """True, wenn es vom Design eine im Home liegende, entfernbare Kopie gibt.

    Geschützte Designs (Yaru, Adwaita) sind nie löschbar, egal wo sie liegen.
    """
    if _geschuetzt(name):
        return False
    return bool(home_vorkommen(name, kategorie))


def _liegt_in_home(pfad, kategorie):
    """Sicherheitsnetz: der Elternordner von 'pfad' muss ein erlaubtes Home-Dir
    sein (real, also ohne Symlink-Umweg)."""
    eltern = os.path.realpath(os.path.dirname(pfad))
    return any(eltern == os.path.realpath(d)
               for d in LOESCH_DIRS.get(kategorie, []))


def deinstalliere(name, kategorie):
    """Entfernt alle Home-Vorkommen des Designs. Gibt True bei Erfolg.

    Bricht bei der ersten OSError ab und meldet False; bereits entfernte
    Vorkommen bleiben entfernt. Pfade außerhalb der erlaubten Home-Ordner werden
    übersprungen (sollte nach der Prüfung nicht vorkommen, ist aber die letzte
    Bremse gegen ein versehentliches Löschen am falschen Ort).
    """
    if _geschuetzt(name):
        return False  # Yaru/Adwaita nie entfernen, auch nicht über Umwege
    vorkommen = home_vorkommen(name, kategorie)
    if not vorkommen:
        return False
    for pfad in vorkommen:
        if not _liegt_in_home(pfad, kategorie):
            continue
        try:
            if os.path.islink(pfad):
                os.unlink(pfad)  # nur die Verknüpfung, nicht ihr Ziel
            else:
                shutil.rmtree(pfad)
        except OSError:
            return False
    return True
