"""Update-Pruefung und -Installation ueber GitHub Releases.

Fragt das neueste Release im Projekt-Repo ab und installiert auf Wunsch das
mitgelieferte .deb. Die Installation laeuft ueber pkexec (apt-get loest dabei
Abhaengigkeiten auf). Netzwerk und Download liegen in einem Hintergrund-Thread;
die UI ruft pruefe()/lade_und_installiere() und bekommt das Ergebnis per Callback.

Sicherheit: HTTPS mit Zertifikatspruefung (urllib-Standardkontext). Liefert die
GitHub-API einen sha256-Digest fuer das Asset, wird er nach dem Download geprueft;
sonst dient die gemeldete Dateigroesse als einfacher Integritaetsabgleich. Das
.deb wird als root installiert, der Nutzer bestaetigt das ueber den
pkexec-Passwortdialog.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

# Aktiv seit dem öffentlichen Repo mit Releases. Vorher gab die unauthentifizierte
# GitHub-API 404, was pruefe() nicht von "kein Update" unterscheiden konnte. Bei
# Netzfehler/404 meldet pruefe() weiter None, also nie ein falsches Update-Angebot.
UPDATER_AKTIV = True

REPO = "simonlinuxcraft/design-manager"
API_URL = "https://api.github.com/repos/%s/releases/latest" % REPO
_TIMEOUT = 15
_KOPF = {"User-Agent": "design-manager-updater",
         "Accept": "application/vnd.github+json"}


def _version_tupel(text):
    """'v1.2.3' -> (1, 2, 3). Nicht-Ziffern werden ignoriert."""
    teile = []
    for stueck in text.strip().lstrip("vV").split("."):
        ziffern = "".join(c for c in stueck if c.isdigit())
        teile.append(int(ziffern) if ziffern else 0)
    return tuple(teile) or (0,)


def pruefe(aktuelle_version):
    """Fragt GitHub nach dem neuesten Release.

    Gibt ein dict (version, url, groesse, sha256, name) zurueck, wenn eine
    neuere Version mit .deb-Asset existiert, sonst None (auch bei Netzfehler).
    """
    try:
        req = urllib.request.Request(API_URL, headers=_KOPF)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        return None

    tag = daten.get("tag_name") or ""
    if not tag or _version_tupel(tag) <= _version_tupel(aktuelle_version):
        return None

    for asset in daten.get("assets", []):
        name = asset.get("name", "")
        if not name.endswith(".deb"):
            continue
        url = asset.get("browser_download_url") or ""
        if not url.startswith("https://"):
            return None
        digest = asset.get("digest") or ""  # Format "sha256:abc..."
        sha256 = digest.split(":", 1)[1] if digest.startswith("sha256:") else ""
        return {
            "version": tag.lstrip("vV"),
            "url": url,
            "groesse": asset.get("size", 0),
            "sha256": sha256,
            "name": name,
        }
    return None


def _lade_herunter(info):
    """Laedt das .deb in eine temporaere Datei und prueft seine Integritaet.

    Gibt den Pfad zurueck oder None bei Fehler/Pruefungsfehler.
    """
    url = info.get("url", "")
    if not url.startswith("https://"):
        return None

    fd, pfad = tempfile.mkstemp(suffix=".deb", prefix="design-manager-update-")
    os.close(fd)
    os.chmod(pfad, 0o600)
    try:
        req = urllib.request.Request(url, headers=_KOPF)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as antwort, \
                open(pfad, "wb") as ziel:
            shutil.copyfileobj(antwort, ziel)
    except (urllib.error.URLError, OSError):
        _entferne(pfad)
        return None

    if not _integritaet_ok(pfad, info):
        _entferne(pfad)
        return None
    return pfad


def _integritaet_ok(pfad, info):
    """Prueft sha256 (wenn vorhanden), sonst die gemeldete Dateigroesse."""
    sha256 = info.get("sha256", "")
    if sha256:
        h = hashlib.sha256()
        try:
            with open(pfad, "rb") as f:
                for block in iter(lambda: f.read(1 << 16), b""):
                    h.update(block)
        except OSError:
            return False
        return h.hexdigest().lower() == sha256.lower()

    groesse = info.get("groesse", 0)
    if groesse:
        try:
            return os.path.getsize(pfad) == groesse
        except OSError:
            return False
    # Ohne Digest und ohne Groesse keine Pruefung moeglich: lieber ablehnen.
    return False


def _installiere(deb_pfad):
    """Installiert das .deb als root ueber pkexec apt-get. True bei Erfolg."""
    try:
        erg = subprocess.run(
            ["pkexec", "apt-get", "install", "-y", "--allow-downgrades",
             os.path.abspath(deb_pfad)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        return erg.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _entferne(pfad):
    try:
        os.remove(pfad)
    except OSError:
        pass


def lade_und_installiere(info):
    """Laedt das Asset herunter und installiert es. True bei Erfolg.

    Laeuft synchron, daher vom Aufrufer in einem Thread starten. Die temporaere
    Datei wird in jedem Fall wieder entfernt.
    """
    deb = _lade_herunter(info)
    if deb is None:
        return False
    try:
        return _installiere(deb)
    finally:
        _entferne(deb)


def werkzeuge_da():
    """True, wenn pkexec und apt-get vorhanden sind (sonst kein In-App-Update)."""
    return bool(shutil.which("pkexec") and shutil.which("apt-get"))
