"""Zusammenspiel mit Variety, falls es als Hintergrund-Rotator läuft.

Variety merkt sich ein "aktuelles Bild" und legt es bei jedem Login wieder auf;
dabei überschreibt es picture-uri (und picture-options). Setzt man den
Hintergrund direkt über gsettings, hält die Auswahl darum nicht über den
nächsten Login.

Lösung ohne Variety abzuschalten: läuft Variety, geben wir die Bildwahl per
`variety --set <Datei>` an die laufende Instanz weiter. Dann wird unsere Wahl
Varietys aktuelles Bild, und es legt genau dieses fortan wieder auf. Läuft
Variety nicht, setzt die App den Hintergrund wie bisher direkt.
"""

import os
import shutil
import subprocess


# Varietys Autostart-Eintrag des Nutzers.
AUTOSTART = os.path.expanduser("~/.config/autostart/variety.desktop")
SYSTEM_DESKTOP = "/usr/share/applications/variety.desktop"
HISTORY = os.path.expanduser("~/.config/variety/history.txt")
TEMP_WALLPAPER = os.path.expanduser("~/.config/variety/wallpaper")


def installiert():
    """True, wenn das variety-Programm im PATH liegt."""
    return shutil.which("variety") is not None


def laeuft():
    """True, wenn eine Variety-Instanz läuft.

    Nur dann nimmt Variety Befehle wie --set an, und nur dann würde es eine
    direkte gsettings-Änderung beim nächsten Login wieder überschreiben. Geprüft
    über die volle Befehlszeile, weil Variety als 'python3 /usr/bin/variety'
    läuft, der Prozessname also nicht 'variety' ist.
    """
    if not installiert():
        return False
    try:
        ergebnis = subprocess.run(
            ["pgrep", "-f", "bin/variety"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return False  # ohne pgrep nicht prüfbar -> lieber direkt über gsettings
    return ergebnis.returncode == 0


def setze_wallpaper(pfad):
    """Übergibt das Bild an die laufende Variety-Instanz (variety --set).

    Variety verlangt einen absoluten Pfad. Gibt True bei Erfolg zurück; bei
    Fehler False, damit der Aufrufer auf den direkten gsettings-Weg zurückfallen
    kann.
    """
    try:
        ergebnis = subprocess.run(
            ["variety", "--set", os.path.abspath(pfad)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return False
    return ergebnis.returncode == 0


def aktuelles_quellbild():
    """Pfad des aktuellen Quell-Bildes laut Varietys Verlauf, oder None.

    history.txt: erste Zeile ist ein Index, danach die zuletzt gesetzten
    Bildpfade (neuestes zuerst). Wir nehmen den ersten existierenden, der nicht
    in Varietys temporärem wallpaper-Ordner liegt, damit das Bild auch erhalten
    bleibt, wenn Varietys Cache mal geleert wird.
    """
    try:
        with open(HISTORY, encoding="utf-8") as f:
            zeilen = [z.strip() for z in f]
    except OSError:
        return None
    for z in zeilen:
        if z and os.path.isabs(z) and not z.startswith(TEMP_WALLPAPER) \
                and os.path.isfile(z):
            return z
    return None


def beenden():
    """Beendet die laufende Variety-Instanz (variety --quit)."""
    try:
        subprocess.run(["variety", "--quit"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return False
    return True


def autostart_aus():
    """Deaktiviert Varietys Autostart, ohne die Datei zu löschen (reversibel).

    Setzt X-GNOME-Autostart-enabled=false. Gibt es nur eine systemweite .desktop,
    legen wir eine deaktivierte Kopie unter ~/.config/autostart an. Gibt True,
    wenn danach ein deaktivierter Eintrag existiert.
    """
    if not os.path.isfile(AUTOSTART):
        if not os.path.isfile(SYSTEM_DESKTOP):
            return False
        try:
            os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
            shutil.copyfile(SYSTEM_DESKTOP, AUTOSTART)
        except OSError:
            return False
    return _setze_autostart_flag(False)


def _setze_autostart_flag(an):
    """Schreibt X-GNOME-Autostart-enabled in die Autostart-Datei (true/false)."""
    wert = "true" if an else "false"
    try:
        with open(AUTOSTART, encoding="utf-8") as f:
            zeilen = f.readlines()
    except OSError:
        return False

    neu = []
    gesetzt = False
    for z in zeilen:
        if z.startswith("X-GNOME-Autostart-enabled"):
            neu.append("X-GNOME-Autostart-enabled=%s\n" % wert)
            gesetzt = True
        else:
            neu.append(z)

    if not gesetzt:
        # In die [Desktop Entry]-Gruppe einfügen (direkt nach der Kopfzeile),
        # damit der Schlüssel nicht in einer fremden Gruppe landet.
        ausgabe, eingefuegt = [], False
        for z in neu:
            ausgabe.append(z)
            if not eingefuegt and z.strip() == "[Desktop Entry]":
                ausgabe.append("X-GNOME-Autostart-enabled=%s\n" % wert)
                eingefuegt = True
        if not eingefuegt:
            ausgabe.append("X-GNOME-Autostart-enabled=%s\n" % wert)
        neu = ausgabe

    try:
        with open(AUTOSTART, "w", encoding="utf-8") as f:
            f.writelines(neu)
    except OSError:
        return False
    return True
