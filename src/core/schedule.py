"""Tag/Nacht-Automatik über systemd-User-Timer.

Bindet zwei vorhandene Profile (siehe backup.py) an feste Uhrzeiten. Statt eines
eigenen Hintergrunddienstes nutzt die App die Zeitsteuerung, die der Nutzer eh
laufen hat: zwei systemd-User-Timer rufen die App im Headless-Modus
(main.py --apply-profile NAME) auf und schalten so das Profil um.

Alles bleibt im Benutzerkontext (kein root), und alle erzeugten Units tragen den
Präfix dm-, damit sich später nichts Fremdes löschen lässt. Der Stand
(Profilnamen, Zeiten, an/aus) liegt zusätzlich als JSON vor, damit die UI ihn
wieder anzeigen kann.
"""

import json
import os
import re
import subprocess
import sys


# Ablageorte. Die Unit-Dateien gehören in den User-Ordner von systemd.
UNIT_DIR = os.path.expanduser("~/.config/systemd/user")
AUTO_FILE = os.path.expanduser("~/.config/design-manager/automatik.json")

# Pfad zu main.py, relativ zu dieser Datei (src/core/schedule.py -> Projektwurzel).
# Bleibt auch im installierten Paket gültig, solange die Ordnerstruktur erhalten
# bleibt.
MAIN_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "main.py")

# Die beiden Zeitfenster. Reihenfolge nur fürs Durchlaufen.
SLOTS = ("tag", "nacht")

# Vorgabe, falls noch nichts gespeichert wurde.
STANDARD = {
    "aktiv": False,
    "tag": {"profil": "", "zeit": "08:00"},
    "nacht": {"profil": "", "zeit": "20:00"},
}


def zeit_ok(zeit):
    """True, wenn 'zeit' das Format HH:MM mit gültigen Werten hat."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", zeit or "")
    if not m:
        return False
    stunde, minute = int(m.group(1)), int(m.group(2))
    return 0 <= stunde <= 23 and 0 <= minute <= 59


# --- Konfiguration ---

def lese_konfig():
    """Gespeicherten Stand laden, mit Vorgaben aufgefüllt."""
    daten = dict(STANDARD)
    daten["tag"] = dict(STANDARD["tag"])
    daten["nacht"] = dict(STANDARD["nacht"])
    try:
        with open(AUTO_FILE) as f:
            gelesen = json.load(f)
    except (OSError, ValueError):
        return daten
    if not isinstance(gelesen, dict):
        return daten
    daten["aktiv"] = bool(gelesen.get("aktiv", False))
    for slot in SLOTS:
        eintrag = gelesen.get(slot)
        if isinstance(eintrag, dict):
            daten[slot]["profil"] = str(eintrag.get("profil", ""))
            daten[slot]["zeit"] = str(eintrag.get("zeit", daten[slot]["zeit"]))
    return daten


def schreibe_konfig(konfig):
    try:
        os.makedirs(os.path.dirname(AUTO_FILE), exist_ok=True)
        with open(AUTO_FILE, "w") as f:
            json.dump(konfig, f, indent=2, sort_keys=True)
    except OSError:
        pass


# --- systemd-Units ---

def _systemctl(*args):
    try:
        ergebnis = subprocess.run(
            ["systemctl", "--user", *args], capture_output=True, text=True)
        return ergebnis.returncode == 0
    except OSError:
        return False


def _service_text(profil):
    return (
        "[Unit]\n"
        "Description=Design Manager: Profil \"%s\" anwenden\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        # Pfade und Profilname in Anführungszeichen, da sie Leerzeichen
        # enthalten können (systemd unterstützt \"...\"-Quoting in ExecStart).
        "ExecStart=\"%s\" \"%s\" --apply-profile \"%s\"\n"
        % (profil, sys.executable, MAIN_PY, profil))


def _timer_text(slot, zeit):
    stunde, minute = zeit.split(":")
    return (
        "[Unit]\n"
        "Description=Design Manager: %s-Profil um %s\n\n"
        "[Timer]\n"
        "OnCalendar=*-*-* %02d:%02d:00\n"
        "Persistent=true\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
        % (slot, zeit, int(stunde), int(minute)))


def _schreibe(name, inhalt):
    with open(os.path.join(UNIT_DIR, name), "w") as f:
        f.write(inhalt)


def aktiviere(konfig):
    """Schreibt und startet die Timer aus der Konfig. Rückgabe True bei Erfolg.

    Nur Slots mit gültigem Profil und gültiger Zeit werden eingerichtet.
    """
    try:
        os.makedirs(UNIT_DIR, exist_ok=True)
    except OSError:
        return False

    timer = []
    for slot in SLOTS:
        eintrag = konfig.get(slot, {})
        profil = eintrag.get("profil", "")
        zeit = eintrag.get("zeit", "")
        if not profil or not zeit_ok(zeit):
            continue
        try:
            _schreibe("dm-look-%s.service" % slot, _service_text(profil))
            _schreibe("dm-look-%s.timer" % slot, _timer_text(slot, zeit))
        except OSError:
            return False
        timer.append("dm-look-%s.timer" % slot)

    if not timer:
        return False
    if not _systemctl("daemon-reload"):
        return False
    ok = _systemctl("enable", "--now", *timer)
    konfig["aktiv"] = ok
    schreibe_konfig(konfig)
    return ok


def deaktiviere():
    """Stoppt und entfernt alle dm-look-Timer und -Services."""
    _systemctl("disable", "--now", "dm-look-tag.timer", "dm-look-nacht.timer")
    for slot in SLOTS:
        for endung in (".timer", ".service"):
            try:
                os.remove(os.path.join(UNIT_DIR, "dm-look-%s%s" % (slot, endung)))
            except FileNotFoundError:
                pass
    _systemctl("daemon-reload")
    konfig = lese_konfig()
    konfig["aktiv"] = False
    schreibe_konfig(konfig)
    return True
