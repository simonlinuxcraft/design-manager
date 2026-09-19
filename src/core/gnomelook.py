"""Designs direkt von gnome-look.org laden und später aktualisieren.

Ein gezogener gnome-look-Link (…/p/<id>) wird über die OCS-API der Seite
aufgelöst: welche Dateien der Eintrag anbietet, samt md5 und Download-Link.
Die gewählte Datei wird geladen und durchläuft den normalen Installer. Danach
merkt sich die App in sources.json, was aus welcher Datei stammt. Beim Start
fragt sie die API erneut: hat sich die md5 geändert oder liegt eine neuere
Datei gleichen Namens (ohne Datum/Version) da, gibt es ein Update.

Nur HTTPS, Größengrenze, md5-Abgleich. Die API kennt jede Datei der
Pling-Familie (gnome-look, pling, store.kde.org, xfce-look), die IDs sind gleich.

Der Update-Zustand je Zielordner (aktuell, Update, läuft, Problem) lebt nur im
Speicher; sichtbare Widgets melden sich per beobachte() an und werden bei
Änderungen im Hauptthread aufgefrischt.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from gi.repository import GLib

from src.core import backgrounds, installer
from src.core.installer import InstallFehler
from src.i18n import _


API_URL = "https://api.gnome-look.org/ocs/v1/content/data/{id}"
QUELLEN_DATEI = os.path.expanduser("~/.config/design-manager/sources.json")
_TIMEOUT = 30
_KOPF = {"User-Agent": "design-manager"}
MAX_DOWNLOAD = 1024 ** 3
_LINK_RX = re.compile(
    r"^https?://(?:www\.)?(?:gnome-look\.org|pling\.com|store\.kde\.org|"
    r"xfce-look\.org)/(?:[^?#]*/)?p/(\d+)", re.I)

# Zustände, zugleich Vorrang: ein Problem überdeckt alles andere.
AKTUELL, UPDATE, LAEUFT, PROBLEM = range(4)
_zustand = {}  # zielordner -> (zustand, text)
_beobachter = set()
_geplant = False


class _NichtErreichbar(InstallFehler):
    """Netz weg: kein Problem des Designs, nur nicht prüfbar."""


def content_id(uri):
    """'1013030' aus einem gnome-look-Link, sonst None."""
    treffer = _LINK_RX.match(uri or "")
    return treffer.group(1) if treffer else None


def dateien(cid):
    """(titel, [datei]) des Eintrags; datei = dict name/link/md5/version.

    Nur Dateien, die der Installer versteht (Archive, Schriften, Bilder).
    """
    try:
        anfrage = urllib.request.Request(API_URL.format(id=cid), headers=_KOPF)
        with urllib.request.urlopen(anfrage, timeout=_TIMEOUT) as antwort:
            wurzel = ET.fromstring(antwort.read(4 * 1024 ** 2))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise InstallFehler(_("This gnome-look entry was not found.")) \
                from None
        raise _NichtErreichbar(_("gnome-look.org could not be reached.")) \
            from None
    except (urllib.error.URLError, OSError, ET.ParseError):
        raise _NichtErreichbar(_("gnome-look.org could not be reached.")) \
            from None
    inhalt = wurzel.find("data/content")
    if wurzel.findtext("meta/status") != "ok" or inhalt is None:
        raise InstallFehler(_("This gnome-look entry was not found."))
    endungen = (installer.ARCHIV_ENDUNGEN + installer.SCHRIFT_ENDUNGEN
                + backgrounds.ENDUNGEN)
    liste = []
    for i in range(1, 200):
        name = inhalt.findtext("downloadname%d" % i)
        link = inhalt.findtext("downloadlink%d" % i) or ""
        if name and link.startswith("https://") and \
                name.lower().endswith(endungen):
            liste.append({
                "name": name, "link": link,
                "md5": (inhalt.findtext("downloadmd5sum%d" % i) or "").lower(),
                "version": inhalt.findtext("download_version%d" % i) or ""})
    if not liste:
        raise InstallFehler(_("This gnome-look entry has no file the app can "
                              "install."))
    return inhalt.findtext("name") or cid, liste


def analysiere(cid, titel, datei, eintrag=None):
    """Lädt die Datei und gibt das Installer-Paket zurück (danach aufraeumen!).

    eintrag: der gemerkte Stand bei einem Update. Dann werden die Designs
    vorausgewählt, die von damals noch installiert sind.
    """
    noch_da = {p for p in (eintrag or {}).get("pfade", ())
               if os.path.lexists(p)}
    setze(noch_da, LAEUFT, _("Updating…"))
    os.makedirs(installer.ARBEIT_DIR, exist_ok=True)
    ordner = tempfile.mkdtemp(dir=installer.ARBEIT_DIR, prefix="install-")
    try:
        pfad = os.path.join(ordner, installer._sicherer_name(
            os.path.basename(datei["name"])) or "download")
        _lade(datei, pfad)
        paket = installer.analysiere(pfad)
    except BaseException as e:
        shutil.rmtree(ordner, ignore_errors=True)
        setze(noch_da, PROBLEM, str(e) if isinstance(e, InstallFehler)
              else _("Installation failed unexpectedly."))
        raise
    paket.arbeit.append(ordner)  # einzelne Schriften/Bilder liegen direkt hier
    paket.quelle = {"id": cid, "titel": titel, "datei": datei["name"],
                    "md5": datei["md5"]}
    paket.eintrag = eintrag
    if eintrag:
        paket.vorauswahl = [f for f in paket.auswaehlbar()
                            if noch_da & set(installer.ziel_pfade(f))] or None
    return paket


def _lade(datei, ziel):
    md5 = hashlib.md5(usedforsecurity=False)
    geladen = 0
    try:
        anfrage = urllib.request.Request(datei["link"], headers=_KOPF)
        with urllib.request.urlopen(anfrage, timeout=_TIMEOUT) as antwort, \
                open(ziel, "wb") as f:
            # urllib folgt Weiterleitungen auch auf http; dann nichts lesen.
            if not antwort.geturl().startswith("https://"):
                raise InstallFehler(_("The download from gnome-look.org "
                                      "failed."))
            while block := antwort.read(1024 ** 2):
                geladen += len(block)
                if geladen > MAX_DOWNLOAD:
                    raise InstallFehler(_("The download is too large."))
                md5.update(block)
                f.write(block)
    except (urllib.error.URLError, OSError):
        raise InstallFehler(_("The download from gnome-look.org failed.")) \
            from None
    if datei["md5"] and md5.hexdigest() != datei["md5"]:
        raise InstallFehler(_("The download is damaged. Try again later."))


# --- Gemerkte Herkunft ---

def _lade_quellen():
    try:
        with open(QUELLEN_DATEI, encoding="utf-8") as f:
            daten = json.load(f)
    except (OSError, ValueError):
        return []
    return [e for e in daten if isinstance(e, dict) and isinstance(
        e.get("pfade"), list) and isinstance(e.get("id"), str)] \
        if isinstance(daten, list) else []


def hat_quellen():
    return bool(_lade_quellen())


def eintraege():
    """Gemerkte Downloads, nur mit noch vorhandenen Zielordnern."""
    ergebnis = []
    for e in _lade_quellen():
        pfade = [p for p in e["pfade"] if os.path.lexists(p)]
        if pfade:
            ergebnis.append(dict(e, pfade=pfade))
    return ergebnis


def merke(paket, installiert):
    """Nach dem Installieren (auch einer lokalen Datei) festhalten, woher die
    Zielordner jetzt stammen, und die Zustände setzen.

    Jeder Ordner gehört dem zuletzt installierten Paket: ältere Einträge
    verlieren ihn. Was ein Update nicht ersetzt hat (abgewählt, abgebrochen,
    blockiert), bleibt beim alten Eintrag und damit als Update sichtbar.
    """
    pfade = sorted({p for f in installiert for p in installer.ziel_pfade(f)})
    setze(pfade, AKTUELL if paket.quelle else None,
          _("Up to date with gnome-look.org"))
    setze(_laufend(paket), UPDATE, _("Update available on gnome-look.org"))
    alt = _lade_quellen()
    liste = [dict(e, pfade=[p for p in e["pfade"] if p not in pfade])
             for e in alt]
    liste = [e for e in liste if e["pfade"]]
    if paket.quelle and pfade:
        liste.append(dict(paket.quelle, pfade=pfade))
    if liste == alt:
        return
    try:
        os.makedirs(os.path.dirname(QUELLEN_DATEI), exist_ok=True)
        tmp = QUELLEN_DATEI + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(liste, f, indent=1, ensure_ascii=False)
        os.replace(tmp, QUELLEN_DATEI)
    except OSError:
        pass  # installiert ist es trotzdem, nur ohne Update-Hinweis


def fehlgeschlagen(paket, text):
    setze(_laufend(paket), PROBLEM, text)


def _laufend(paket):
    """Ordner dieses Updates, die noch als "läuft" markiert sind."""
    return [p for p in (paket.eintrag or {}).get("pfade", ())
            if _zustand.get(p, (None,))[0] == LAEUFT]


# --- Zustand für die Anzeige ---

def setze(pfade, zustand, text=""):
    """zustand None löscht. Aus jedem Thread aufrufbar."""
    global _geplant
    for p in pfade:
        if zustand is None:
            _zustand.pop(p, None)
        else:
            _zustand[p] = (zustand, text)
    if not _geplant:  # eine Prüfung mit vielen Einträgen zeichnet nur einmal
        _geplant = True
        GLib.idle_add(_melde)


def zustand(pfade):
    """(zustand, text) mit dem höchsten Vorrang, None wenn unbekannt."""
    bekannt = _zustand.copy()
    werte = [bekannt[p] for p in pfade if p in bekannt]
    return max(werte, key=lambda w: w[0]) if werte else None


def zustand_fuer_name(name):
    """Wie zustand(), für eine Karte, die nur den Design-Namen kennt."""
    # ponytail: nach Name, nicht Kategorie; ein gleichnamiges Icon- und
    # GTK-Design aus zwei Einträgen teilt sich die Anzeige. Pfad an die Karte
    # geben, falls das je stört.
    return zustand([p for p in _zustand.copy() if os.path.basename(p) == name])


def beobachte(widget):
    """Solange das Widget eingeblendet ist, läuft widget.aktualisiere() nach
    jeder Änderung im Hauptthread. Nur solange: sonst hielte die Liste
    ausgetauschte Seiten am Leben."""
    widget.connect("map", _eingeblendet)
    widget.connect("unmap", _beobachter.discard)


def _eingeblendet(widget):
    _beobachter.add(widget)
    widget.aktualisiere()


def _melde():
    global _geplant
    _geplant = False
    for widget in list(_beobachter):
        widget.aktualisiere()
    return GLib.SOURCE_REMOVE


def _stamm(name):
    """Dateiname ohne Endung, Datum und Versionsnummern: der Vergleichskern.
    '01-Flat-Remix-Light-20250926.tar.xz' -> '#-flat-remix-light-#'."""
    name = name.lower()
    for endung in installer.ARCHIV_ENDUNGEN:
        if name.endswith(endung):
            name = name[:-len(endung)]
            break
    return re.sub(r"(?<![a-z])v?\d+(?:[._-]\d+)*", "#", name)


def nachfolger(eintrag, aktuell):
    """Die Datei(en), die das gemerkte Design jetzt ersetzen. Leer = aktuell,
    None = die Datei gibt es nicht mehr und nichts ersetzt sie.

    Gleicher Name: nur bei geänderter md5. Name verschwunden: alle Dateien mit
    gleichem Stamm (mehrere = Nutzer wählt).
    """
    gleich = [d for d in aktuell if d["name"] == eintrag.get("datei")]
    if gleich:
        neu, alt = gleich[0]["md5"], eintrag.get("md5")
        return [gleich[0]] if neu and alt and neu != alt else []
    stamm = _stamm(eintrag.get("datei") or "")
    return [d for d in aktuell if _stamm(d["name"]) == stamm] or None


def updates():
    """([(eintrag, nachfolger)], netzfehler) für noch installierte Designs.

    Setzt nebenbei den Zustand jedes Ordners. Ohne Netz bleibt er unverändert
    (kein Warnsymbol auf jeder Karte, nur weil man offline ist).
    """
    ergebnis, antworten, netzfehler = [], {}, None
    for eintrag in eintraege():
        cid = eintrag["id"]
        if cid not in antworten:
            try:
                antworten[cid] = dateien(cid)[1]
            except _NichtErreichbar as e:
                antworten[cid], netzfehler = None, str(e)
            except InstallFehler as e:
                antworten[cid] = str(e)
        antwort = antworten[cid]
        if antwort is None:
            continue
        if isinstance(antwort, str):
            setze(eintrag["pfade"], PROBLEM, antwort)
            continue
        neu = nachfolger(eintrag, antwort)
        if neu is None:
            setze(eintrag["pfade"], PROBLEM,
                  _("The file is no longer offered on gnome-look.org."))
        elif neu:
            setze(eintrag["pfade"], UPDATE,
                  _("Update available on gnome-look.org"))
            ergebnis.append((eintrag, neu))
        else:
            setze(eintrag["pfade"], AKTUELL, _("Up to date with gnome-look.org"))
    return ergebnis, netzfehler
