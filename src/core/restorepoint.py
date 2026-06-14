"""Automatische Sicherungspunkte vor riskanten Design-Wechseln.

Vor jedem GTK-, Shell- oder Mauszeiger-Wechsel legt die App still einen
Schnappschuss aller verwalteten dconf-Werte an. Geht ein Design kaputt (etwa
ungültiges CSS, das die Sitzung lahmlegt), führt ein Klick exakt in den
Vorzustand zurück. Format und Mechanik sind dieselben wie bei einer Sicherung
(siehe backup.py), nur an einem eigenen Ort und als Ringpuffer begrenzt.

Geschrieben wird ausschließlich in den eigenen Config-Ordner; Design-Dateien
werden nie angefasst.
"""

import json
import os
import re
import time

from src.core import backup


# Ablageort und maximale Zahl gehaltener Punkte (Ringpuffer).
PUNKTE_DIR = os.path.expanduser("~/.config/design-manager/restore-points")
MAX_PUNKTE = 5


def _slug(anlass):
    """Macht den Anlass-Text dateinamentauglich (nur für den Dateinamen)."""
    slug = re.sub(r"[^\w-]+", "-", anlass, flags=re.UNICODE).strip("-")
    return slug[:48] or "snapshot"


def _dateien():
    """Alle Sicherungspunkt-Dateien, neueste zuerst (nach Dateiname = Zeit)."""
    try:
        namen = [f for f in os.listdir(PUNKTE_DIR) if f.endswith(".json")]
    except OSError:
        return []
    return sorted(namen, reverse=True)


def _lese(datei):
    """Liest einen Punkt als Dict oder None, wenn er nicht lesbar ist."""
    try:
        with open(os.path.join(PUNKTE_DIR, datei)) as f:
            daten = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(daten, dict) or daten.get("format") != backup.FORMAT:
        return None
    return daten


def erstelle(settings, anlass):
    """Legt einen Sicherungspunkt an, falls sich der Stand seit dem letzten
    geändert hat.

    Die Dedup-Prüfung verhindert eine Flut gleicher Punkte beim Durchklicken:
    ist der aktuelle Stand identisch mit dem jüngsten Punkt, passiert nichts.
    """
    aktuell = settings.export_settings()

    juengste = _dateien()
    if juengste:
        letzter = _lese(juengste[0])
        if letzter is not None and letzter.get("einstellungen") == aktuell:
            return  # nichts Neues zu sichern

    daten = {
        "format": backup.FORMAT,
        "version": backup.FORMAT_VERSION,
        "anlass": anlass,
        "zeit": time.time(),
        "einstellungen": aktuell,
    }
    # Millisekunden im Namen halten die Sortierung stabil, auch bei zwei
    # Punkten in derselben Sekunde.
    name = "%013d-%s.json" % (int(time.time() * 1000), _slug(anlass))
    try:
        os.makedirs(PUNKTE_DIR, exist_ok=True)
        with open(os.path.join(PUNKTE_DIR, name), "w") as f:
            json.dump(daten, f, indent=2, sort_keys=True)
    except OSError:
        return  # Sicherungspunkt ist Komfort, kein kritischer Pfad

    _kuerze_ringpuffer()


def _kuerze_ringpuffer():
    """Lässt nur die MAX_PUNKTE jüngsten Punkte übrig."""
    for alt in _dateien()[MAX_PUNKTE:]:
        try:
            os.remove(os.path.join(PUNKTE_DIR, alt))
        except OSError:
            pass


def liste():
    """Alle Punkte als Dicts {datei, anlass, zeit}, neueste zuerst."""
    punkte = []
    for datei in _dateien():
        daten = _lese(datei)
        if daten is None:
            continue
        punkte.append({
            "datei": datei,
            "anlass": daten.get("anlass", "Sicherungspunkt"),
            "zeit": daten.get("zeit", 0),
        })
    return punkte


def wende_an(settings, datei):
    """Stellt einen Punkt wieder her. Rückgabe True bei Erfolg."""
    daten = _lese(datei)
    if daten is None:
        return False
    einstellungen = daten.get("einstellungen")
    if not isinstance(einstellungen, dict):
        return False
    settings.import_settings(einstellungen)
    return True


def loesche(datei):
    """Entfernt einen Punkt. Ein nicht vorhandener Punkt ist kein Fehler."""
    try:
        os.remove(os.path.join(PUNKTE_DIR, datei))
    except FileNotFoundError:
        pass
