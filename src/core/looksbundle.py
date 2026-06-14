"""Look-Pakete (.dmlook) exportieren und importieren.

Anders als eine Sicherung (backup.py), die nur die dconf-Auswahl merkt, bündelt
ein .dmlook auch die tatsächlich genutzten Design-Dateien und das
Hintergrundbild. So lässt sich ein kompletter Look an jemanden weitergeben, der
die Designs nicht installiert hat.

Ein .dmlook ist ein gewöhnliches ZIP:

    manifest.json          die dconf-Werte (Format wie eine Sicherung)
    themes/<name>/...       GTK- und Shell-Designs
    icons/<name>/...        Symbol- und Mauszeiger-Designs
    backgrounds/<datei>     das Hintergrundbild

Sicherheit: exportiert werden nur Ordner aus dem Home des Nutzers (Yaru/Adwaita
und alles unter /usr/share bleiben außen vor, die hat der Empfänger ohnehin).
Beim Import landet jeder Eintrag streng in seinem Zielordner; Pfade, die da
ausbrechen würden, brechen den Import ab.
"""

import json
import os
import zipfile

from src.core import backgrounds
from src.core.uninstaller import home_vorkommen


FORMAT = "design-manager-look"
FORMAT_VERSION = 1

# Zielordner je oberster ZIP-Ebene beim Import.
ZIEL_NACH_PREFIX = {
    "themes": os.path.expanduser("~/.local/share/themes"),
    "icons": os.path.expanduser("~/.local/share/icons"),
    "backgrounds": os.path.expanduser("~/.local/share/backgrounds"),
}


def _quell_ordner(name, kategorie):
    """Realer Ordner eines Designs im Home, oder None.

    home_vorkommen liefert auch Symlinks; fürs Packen wollen wir den echten
    Ordner, darum über realpath auflösen.
    """
    for pfad in home_vorkommen(name, kategorie):
        if os.path.isdir(pfad):
            return os.path.realpath(pfad)
    return None


def _zippe_ordner(z, ordner, arc_prefix):
    for wurzel, _dirs, dateien in os.walk(ordner):
        for datei in dateien:
            voll = os.path.join(wurzel, datei)
            if os.path.islink(voll) and not os.path.exists(voll):
                continue  # toter Symlink
            rel = os.path.relpath(voll, ordner)
            z.write(voll, arc_prefix + "/" + rel)


def exportiere(settings, ziel_zip):
    """Schreibt den aktiven Look als .dmlook nach ziel_zip."""
    manifest = {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "einstellungen": settings.export_settings(),
    }

    # (Designname, Kategorie, ZIP-Ebene). gtk und shell liegen beide unter
    # themes/, icon und cursor unter icons/.
    quellen = [
        (settings.gtk_theme(), "gtk", "themes"),
        (settings.shell_theme(), "shell", "themes"),
        (settings.icon_theme(), "icon", "icons"),
        (settings.cursor_theme(), "cursor", "icons"),
    ]

    with zipfile.ZipFile(ziel_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))

        gesehen = set()
        for name, kategorie, prefix in quellen:
            if not name:
                continue
            ordner = _quell_ordner(name, kategorie)
            if ordner is None:
                continue  # systemweit oder nicht gefunden -> nicht mitpacken
            arc = prefix + "/" + os.path.basename(ordner)
            if arc in gesehen:
                continue  # gtk und shell teilen oft denselben Ordner
            gesehen.add(arc)
            _zippe_ordner(z, ordner, arc)

        wallpaper = backgrounds.aktuelles_wallpaper(settings)
        if wallpaper and os.path.isfile(wallpaper):
            z.write(wallpaper, "backgrounds/" + os.path.basename(wallpaper))


def _sicheres_ziel(basis, rel):
    """Pfad innerhalb von basis, oder ValueError bei Ausbruch (Zip-Slip)."""
    basis_real = os.path.realpath(basis)
    ziel = os.path.realpath(os.path.join(basis_real, rel))
    if os.path.commonpath([basis_real, ziel]) != basis_real:
        raise ValueError("unsicherer Pfad im Look-Paket")
    return ziel


def importiere(settings, quelle_zip):
    """Installiert die Dateien aus einem .dmlook und wendet den Look an.

    Rückgabe True bei Erfolg, False wenn die Datei kein gültiges .dmlook ist.
    """
    extrahiertes_wallpaper = None
    try:
        with zipfile.ZipFile(quelle_zip) as z:
            namen = z.namelist()
            if "manifest.json" not in namen:
                return False
            manifest = json.loads(z.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
                return False
            einstellungen = manifest.get("einstellungen")
            if not isinstance(einstellungen, dict):
                return False

            for eintrag in namen:
                if eintrag.endswith("/"):
                    continue  # reiner Ordnereintrag
                kopf, _, rest = eintrag.partition("/")
                basis = ZIEL_NACH_PREFIX.get(kopf)
                if basis is None or not rest:
                    continue  # unbekannte Ebene (auch manifest.json) überspringen
                ziel = _sicheres_ziel(basis, rest)
                os.makedirs(os.path.dirname(ziel), exist_ok=True)
                with z.open(eintrag) as quelle, open(ziel, "wb") as ausgabe:
                    ausgabe.write(quelle.read())
                if kopf == "backgrounds" and extrahiertes_wallpaper is None:
                    extrahiertes_wallpaper = ziel
    except (OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
        return False

    # Erst die Dateien sind da, dann die Auswahl setzen (sonst zeigt der
    # Health-Check kurz auf ein noch fehlendes Design).
    settings.import_settings(einstellungen)
    # Das mitgelieferte Bild liegt jetzt lokal; darüber setzen, statt der evtl.
    # fremden picture-uri aus dem Manifest zu vertrauen.
    if extrahiertes_wallpaper and os.path.isfile(extrahiertes_wallpaper):
        backgrounds.apply_wallpaper(settings, extrahiertes_wallpaper)
    return True
