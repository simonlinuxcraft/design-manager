"""Merker für das Onboarding (Willkommens-Dialog beim ersten Start).

Beim ersten Programmstart soll eine kurze Einführung erscheinen, danach nie
wieder. Wir merken uns das über eine leere Markierungsdatei im Konfigordner der
App. Kein dconf nötig, und der Nutzer kann es durch Löschen der Datei wieder
auslösen.
"""

import os


KONFIG_DIR = os.path.expanduser("~/.config/design-manager")
MARKER = os.path.join(KONFIG_DIR, "onboarding-done")


def ist_erster_start():
    """True, solange das Onboarding noch nicht gezeigt wurde."""
    return not os.path.exists(MARKER)


def als_gesehen_markieren():
    """Hält fest, dass das Onboarding gezeigt wurde. Fehler hier sind
    unkritisch: schlimmstenfalls erscheint die Einführung noch einmal."""
    try:
        os.makedirs(KONFIG_DIR, exist_ok=True)
        with open(MARKER, "w"):
            pass
    except OSError:
        pass
