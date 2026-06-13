"""Einstellungen sichern und wiederherstellen.

Eine Sicherung ist eine kleine JSON-Datei mit den aktuellen Werten der von der
App verwalteten dconf-Schlüssel (Design, Symbole, Mauszeiger, Schrift,
Hintergrund). Wiederherstellen setzt diese Werte zurück. Die Design- und
Bilddateien selbst werden nicht mitgesichert, nur die Auswahl darauf (Name bzw.
URI).

Auf demselben Format bauen die Profile auf: benannte Sicherungen unter
~/.config/design-manager/profiles/, zwischen denen man per Klick wechseln kann
(z.B. ein "Tag"- und ein "Nacht"-Look).
"""

import json
import os
import re


# Kennung und Version des Dateiformats. Die Kennung dient als Plausibilitäts-
# prüfung beim Import, die Version macht spätere Formatänderungen erkennbar.
# Version 2: Werte werden typ-erhaltend als GVariant-Text abgelegt (vorher nur
# Zeichenketten), damit auch Schalter und Zahlen gesichert werden können.
FORMAT = "design-manager-backup"
FORMAT_VERSION = 2

# Ablageort der benannten Profile.
PROFIL_DIR = os.path.expanduser("~/.config/design-manager/profiles")


def save_to_file(settings, pfad):
    """Schreibt die aktuellen Einstellungen als JSON nach 'pfad'."""
    daten = {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "einstellungen": settings.export_settings(),
    }
    with open(pfad, "w") as f:
        json.dump(daten, f, indent=2, sort_keys=True)


def load_from_file(settings, pfad):
    """Liest eine Sicherung und wendet sie an.

    Gibt True bei Erfolg zurück, False wenn die Datei nicht wie eine Sicherung
    dieser App aussieht. OSError/ValueError (Datei fehlt, kein gültiges JSON)
    reicht die Funktion an den Aufrufer durch.
    """
    with open(pfad) as f:
        daten = json.load(f)

    if not isinstance(daten, dict) or daten.get("format") != FORMAT:
        return False

    einstellungen = daten.get("einstellungen")
    if not isinstance(einstellungen, dict):
        return False

    settings.import_settings(einstellungen)
    return True


# --- Profile (benannte Sicherungen) ---


def sicherer_name(name):
    """Macht aus einer Nutzereingabe einen für einen Dateinamen sicheren Namen.

    Erlaubt sind Buchstaben (auch Umlaute), Ziffern, Leerzeichen, Bindestrich
    und Unterstrich. Alles andere (Schrägstriche, Punkte) fällt weg, damit
    niemand über den Namen aus dem Profilordner ausbrechen kann. Gibt einen
    leeren String zurück, wenn nichts Brauchbares übrig bleibt.
    """
    name = re.sub(r"[^\w \-]", "", name, flags=re.UNICODE)
    return name.strip()


def _profil_pfad(name):
    return os.path.join(PROFIL_DIR, name + ".json")


def list_profiles():
    """Namen aller gespeicherten Profile, alphabetisch sortiert."""
    try:
        dateien = os.listdir(PROFIL_DIR)
    except OSError:
        return []  # Ordner gibt es noch nicht
    namen = [f[:-5] for f in dateien if f.endswith(".json")]
    return sorted(namen, key=str.lower)


def save_profile(settings, name):
    """Speichert den aktuellen Stand als Profil und gibt den bereinigten Namen
    zurück. Wirft ValueError, wenn der Name nach der Bereinigung leer ist."""
    name = sicherer_name(name)
    if not name:
        raise ValueError("leerer Profilname")
    os.makedirs(PROFIL_DIR, exist_ok=True)
    save_to_file(settings, _profil_pfad(name))
    return name


def load_profile(settings, name):
    """Wendet ein gespeichertes Profil an. Rückgabe wie load_from_file."""
    return load_from_file(settings, _profil_pfad(sicherer_name(name)))


def delete_profile(name):
    """Löscht ein Profil. Ein nicht vorhandenes Profil ist kein Fehler."""
    pfad = _profil_pfad(sicherer_name(name))
    try:
        os.remove(pfad)
    except FileNotFoundError:
        pass
