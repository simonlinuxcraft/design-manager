"""Aufräumen der früheren Tag/Nacht-Automatik.

Die Automatik (zwei systemd-User-Timer dm-look-tag/nacht, die die App headless
ein Profil anwenden ließen) wurde entfernt. Wer sie einmal aktiviert hatte, hat
aber noch die Unit-Dateien und einen aktiven Timer im Benutzerkontext liegen.
Ohne den Headless-Modus würde ein solcher Timer beim Auslösen nur noch ein
leeres Fenster aufpoppen. Darum räumt entferne_alte_automatik() die Reste beim
ersten Start der neuen Version einmalig weg.

Alles bleibt im Benutzerkontext (kein root), und nur die dm-look-Units werden
angefasst, damit nichts Fremdes betroffen ist.
"""

import os
import subprocess


UNIT_DIR = os.path.expanduser("~/.config/systemd/user")
AUTO_FILE = os.path.expanduser("~/.config/design-manager/automatik.json")

# Die Units, die die alte Automatik angelegt hatte.
_ALTE_UNITS = ("dm-look-tag.timer", "dm-look-nacht.timer",
               "dm-look-tag.service", "dm-look-nacht.service")


def _systemctl(*args):
    # timeout, weil das vom Start (GLib.idle_add) auf dem GTK-Mainloop läuft:
    # ein hängendes systemctl darf die Oberfläche nicht blockieren.
    try:
        ergebnis = subprocess.run(
            ["systemctl", "--user", *args], capture_output=True, text=True,
            timeout=10)
        return ergebnis.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def entferne_alte_automatik():
    """Stoppt und löscht verwaiste dm-look-Timer/-Services, falls vorhanden.

    Tut nichts (und kostet nichts), wenn keine Reste da sind. Sicher mehrfach
    aufrufbar.
    """
    vorhanden = [u for u in _ALTE_UNITS
                 if os.path.exists(os.path.join(UNIT_DIR, u))]
    konfig_da = os.path.exists(AUTO_FILE)
    if not vorhanden and not konfig_da:
        return  # nichts aufzuräumen

    timer = [u for u in vorhanden if u.endswith(".timer")]
    if timer:
        _systemctl("disable", "--now", *timer)

    entfernt = False
    for unit in vorhanden:
        try:
            os.remove(os.path.join(UNIT_DIR, unit))
            entfernt = True
        except FileNotFoundError:
            pass

    if entfernt:
        _systemctl("daemon-reload")

    try:
        os.remove(AUTO_FILE)
    except FileNotFoundError:
        pass
