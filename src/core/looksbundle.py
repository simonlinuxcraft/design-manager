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
import shutil
import tempfile
import zipfile

from gi.repository import GLib

from src.core import backgrounds, installer, restorepoint, themes
from src.core.uninstaller import home_vorkommen
from src.i18n import _


FORMAT = "design-manager-look"
FORMAT_VERSION = 1

# Zielordner je oberster ZIP-Ebene beim Import.
ZIEL_NACH_PREFIX = {
    "themes": installer.THEMES_DIR,
    "icons": installer.ICONS_DIR,
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


def _gvariant_string(text):
    """Liest einen als GVariant-Text abgelegten String-Wert, oder ''."""
    if not text:
        return ""
    try:
        return GLib.Variant.parse(
            GLib.VariantType.new("s"), text, None, None).get_string()
    except (GLib.Error, TypeError):
        return ""


def _bereinige_themes(settings, einstellungen):
    """Entfernt Design-Namen aus dem Manifest, die hier nicht installiert sind.

    Ein .dmlook bringt seine Designdateien mit, das Manifest kann aber auch auf
    Designs verweisen, die hier weder mitgeliefert noch installiert sind. Ein
    solcher Name würde GNOME auf einen ungültigen Wert setzen (Fallback auf
    Adwaita, im schlimmsten Fall eine optisch lahme Sitzung). Statt das wie
    bisher blind zu tun, lassen wir unbekannte Design-Namen weg; der jeweilige
    Bereich bleibt dann unverändert. Gibt eine bereinigte Kopie zurück.
    """
    pruefungen = [
        (settings.INTERFACE, "gtk-theme",
         set(themes.list_gtk_themes()) | {settings.SAFE_GTK_THEME}),
        (settings.INTERFACE, "icon-theme",
         set(themes.list_icon_themes()) | {settings.SAFE_ICON_THEME}),
        (settings.INTERFACE, "cursor-theme",
         set(themes.list_cursor_themes()) | {settings.SAFE_CURSOR_THEME}),
        (settings.USER_THEME, "name",
         set(themes.list_shell_themes()) | {""}),
    ]
    bereinigt = {schema: dict(werte)
                 for schema, werte in einstellungen.items()}
    for schema, key, erlaubt in pruefungen:
        werte = bereinigt.get(schema)
        if not werte or key not in werte:
            continue
        if _gvariant_string(werte[key]) not in erlaubt:
            del werte[key]
    return bereinigt


def entpacke(quelle_zip):
    """Installiert die Dateien eines .dmlook, ohne etwas anzuwenden.

    Darf im Hintergrund laufen. Nutzt denselben Weg wie der Installer:
    Größengrenzen, Pfad- und Link-Prüfung, jedes Design atomar eingesetzt (kein
    Mischstand aus alter und neuer Version), keine Namen eingebauter
    Rückfall-Designs. Gibt (einstellungen, wallpaper_pfad) zurück, None wenn
    es kein gültiges .dmlook ist. Wirft installer.InstallFehler bei zu großen
    oder kaputten Paketen.
    """
    try:
        with zipfile.ZipFile(quelle_zip) as z:
            manifest = json.loads(z.read("manifest.json"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return None
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        return None
    einstellungen = manifest.get("einstellungen")
    if not isinstance(einstellungen, dict):
        return None

    os.makedirs(installer.ARBEIT_DIR, exist_ok=True)
    arbeit = tempfile.mkdtemp(dir=installer.ARBEIT_DIR, prefix="install-")
    try:
        installer._entpacke(quelle_zip, arbeit)
        for kopf, ziel_basis in ZIEL_NACH_PREFIX.items():
            ordner = os.path.join(arbeit, kopf)
            if not os.path.isdir(ordner):
                continue
            for name in sorted(os.listdir(ordner)):
                quelle = os.path.join(ordner, name)
                if (name.startswith(".") or os.path.islink(quelle)
                        or not os.path.isdir(quelle)
                        or installer._systemname(name)):
                    continue
                installer._ersetze_ordner(quelle, os.path.join(ziel_basis, name))
        wallpaper = None
        for bild in installer._dateien(os.path.join(arbeit, "backgrounds"),
                                       backgrounds.ENDUNGEN, 1):
            try:
                wallpaper = backgrounds.uebernehme_bild(bild)
                break
            except (ValueError, OSError):
                continue
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)
    return einstellungen, wallpaper


def wende_an(settings, einstellungen, wallpaper):
    """Setzt den entpackten Look (im Hauptthread aufrufen)."""
    # Bevor irgendetwas gesetzt wird, ein Rückkehrnetz anlegen: ein fremdes
    # Paket ist nicht vertrauenswürdig, ein kaputtes Design (ungültiges CSS)
    # kann die Sitzung optisch lahmlegen. Mit dem Sicherungspunkt führt ein
    # Klick auf der Sicherungsseite in den Vorzustand zurück.
    restorepoint.erstelle(settings, _("before importing a look package"))
    # Design-Namen, die hier nicht installiert sind, aus dem Manifest nehmen,
    # statt GNOME blind auf einen ungültigen Wert zu setzen.
    einstellungen = _bereinige_themes(settings, einstellungen)
    # Erst die Dateien sind da, dann die Auswahl setzen (sonst zeigt der
    # Health-Check kurz auf ein noch fehlendes Design).
    settings.import_settings(einstellungen)
    # Das mitgelieferte Bild liegt jetzt lokal; darüber setzen, statt der evtl.
    # fremden picture-uri aus dem Manifest zu vertrauen.
    if wallpaper and os.path.isfile(wallpaper):
        backgrounds.apply_wallpaper(settings, wallpaper)
