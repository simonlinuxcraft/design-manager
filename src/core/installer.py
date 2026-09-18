"""Designs, Symbole, Mauszeiger, Schriften, Hintergründe und Erweiterungen
installieren.

Angenommen wird, was man typischerweise von gnome-look & Co. herunterlädt oder
schon entpackt hat: ein Archiv (.zip, .tar.gz/.xz/.bz2/.zst, .tgz, .tar), ein
entpackter Ordner, eine Schriftdatei oder ein Bild. Archive werden in einen
Arbeitsordner unter ~/.cache entpackt (nicht /tmp, das ist oft RAM), darin
wird alles Brauchbare erkannt und in die Nutzer-Ordner kopiert, nie systemweit
(kein sudo):

- GTK-/Shell-Design (gtk-3.0|4.0/gtk.css oder gnome-shell/gnome-shell.css)
  -> ~/.local/share/themes
- Symbol-Design (index.theme mit Directories) -> ~/.local/share/icons
- Mauszeiger (cursors/) -> ~/.icons, dort sucht libXcursor
- GNOME-Erweiterung (metadata.json + extension.js) -> ~/.local/share/gnome-shell/
  extensions/<uuid>, nur installiert, nie eingeschaltet
- Schriften -> ~/.local/share/fonts (Archive in einen eigenen Unterordner)
- Bilder (Wallpaper-Pakete) -> ~/.local/share/backgrounds

Bewusst NICHT: Anmeldebildschirm-Designs (GDM), Bootmenü (GRUB) und Bootlogo
(Plymouth). Die ersetzen Systemdateien als root; ein Fehler dort kann den Login
oder den Start blockieren. Die werden erkannt und mit Begründung abgelehnt.

Installiert wird nur, aktiviert nie. Jeder Ordner wird erst neben dem Ziel
fertig kopiert und dann per Umbenennen eingesetzt, damit nie ein halbes Design
auftaucht. Namen, die ein eingebautes Rückfall-Design (Adwaita, hicolor, Yaru
...) überdecken würden, werden übersprungen.
"""

import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import zipfile

from src.core import backgrounds
from src.core.uninstaller import _geschuetzt
from src.i18n import _, ngettext


THEMES_DIR = os.path.expanduser("~/.local/share/themes")
ICONS_DIR = os.path.expanduser("~/.local/share/icons")
FONTS_DIR = os.path.expanduser("~/.local/share/fonts")
# Mauszeiger gehen nach ~/.icons, NICHT ~/.local/share/icons: der X-Server
# (libXcursor) durchsucht nur ~/.icons, /usr/share/icons und /usr/share/pixmaps.
CURSORS_DIR = os.path.expanduser("~/.icons")
EXTENSIONS_DIR = os.path.expanduser("~/.local/share/gnome-shell/extensions")
SYSTEM_EXTENSIONS_DIR = "/usr/share/gnome-shell/extensions"
ARBEIT_DIR = os.path.expanduser("~/.cache/design-manager")

SCHRIFT_ENDUNGEN = (".ttf", ".otf", ".ttc", ".otc", ".pfb")
ARCHIV_ENDUNGEN = (".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2",
                   ".tar.zst", ".tar", ".zip")
WINDOWS_CURSOR_ENDUNGEN = (".cur", ".ani")

# Unterordner/Dateien, an denen wir die Wurzel eines Designs erkennen.
THEME_MARKER = {
    "index.theme", "cursors",
    "gtk-2.0", "gtk-3.0", "gtk-4.0", "gnome-shell",
}

# Ein gezogener Ordner wird nur so tief durchsucht (nicht versehentlich das
# halbe Home installieren). Ein entpacktes Design liegt in den ersten Ebenen.
ORDNER_TIEFE = 3
# Obergrenze gegen Unsinn (z.B. ein ganzer Theme-Ordner mit hunderten Designs).
# All-in-one-Pakete wie Flat-Remix (76 Varianten) liegen deutlich darunter; ab
# AUSWAHL_AB Designs fragt die Oberfläche, welche davon installiert werden.
MAX_DESIGNS = 400
AUSWAHL_AB = 6

# Obergrenzen fürs Entpacken (Schutz vor Zip-Bomben). Papirus mit allen
# Varianten liegt bei rund 500 MB und 100 000 Einträgen.
MAX_ENTPACKT = 4 * 1024 ** 3
MAX_EINTRAEGE = 500_000
MAX_INNERE_ARCHIVE = 100

# Bilder aus Paketen erst ab dieser Größe übernehmen, damit Vorschaubilder und
# Screenshots nicht als Hintergrund landen. Ein einzeln gezogenes Bild zählt immer.
MIN_WALLPAPER = (1280, 720)

# Eingebaute Rückfall-Designs, die nie durch eine Home-Kopie überdeckt werden
# dürfen (sonst greift "Sicheren Zustand wiederherstellen" ins Leere).
SYSTEM_NAMEN = {"adwaita", "adwaita-dark", "highcontrast",
                "highcontrastinverse", "default", "hicolor", "locolor"}

ZIELE = {
    "gtk": (THEMES_DIR, _("Theme")),
    "cursor": (CURSORS_DIR, _("Cursor")),
    "icon": (ICONS_DIR, _("Icons")),
}


class InstallFehler(Exception):
    """Datei ließ sich nicht entpacken oder enthielt nichts Passendes."""


class Fund:
    """Ein installierbarer Teil eines Pakets.

    art: "theme" (quelle = Wurzelordner, arten = gtk/cursor/icon), "extension"
    (quelle = Ordner, meta = uuid/Name/Versionen), "font" oder "bilder"
    (quelle = Dateiliste) oder "bild" (ein einzeln gezogenes Bild).
    """

    def __init__(self, art, name, quelle, arten=(), meta=None):
        self.art = art
        self.name = name
        self.quelle = quelle
        self.arten = set(arten)
        self.meta = meta or {}

    def beschreibung(self):
        """Kurzform für die Auswahlliste, z.B. "GTK + Shell" oder "Cursor"."""
        if self.art == "extension":
            return _("Extension")
        teile = []
        if "gtk" in self.arten:
            if _hat_css(self.quelle, shell=False):
                teile.append("GTK")
            if _hat_css(self.quelle, gtk=False):
                teile.append("Shell")
        if "icon" in self.arten:
            teile.append(_("Icons"))
        if "cursor" in self.arten:
            teile.append(_("Cursor"))
        return " + ".join(teile) or _("Theme")


class Paket:
    """Was in einer gezogenen Datei steckt, plus der Arbeitsordner dazu.

    Getrennt von der Installation, damit die Oberfläche bei großen
    All-in-one-Paketen erst fragen kann, welche Designs gewünscht sind.
    aufraeumen() nicht vergessen (löscht den entpackten Arbeitsordner).
    """

    def __init__(self, funde, arbeit=None):
        self.funde = funde
        self._arbeit = arbeit

    def auswaehlbar(self):
        return [f for f in self.funde if f.art in ("theme", "extension")]

    def installiere(self, auswahl=None):
        """Installiert alle Funde oder nur 'auswahl'. Liste der Beschreibungen."""
        ergebnis = []
        for fund in self.funde if auswahl is None else auswahl:
            if fund.art == "theme":
                for art in sorted(fund.arten):
                    ziel_basis, label = ZIELE[art]
                    _ersetze_ordner(fund.quelle,
                                    os.path.join(ziel_basis, fund.name))
                    ergebnis.append(label + ": " + fund.name)
            elif fund.art == "extension":
                ergebnis.append(_installiere_erweiterung(fund))
            elif fund.art == "font":
                ergebnis += _kopiere_fonts(fund.quelle, fund.name)
            elif fund.art == "bilder":
                ergebnis += _installiere_bilder(fund.quelle)
            elif fund.art == "bild":
                ergebnis.append(_installiere_bild(fund.quelle))
        return ergebnis

    def aufraeumen(self):
        if self._arbeit:
            shutil.rmtree(self._arbeit, ignore_errors=True)
            self._arbeit = None


def install(pfad):
    """Analysieren und alles Gefundene installieren (ohne Rückfrage)."""
    paket = analysiere(pfad)
    try:
        return paket.installiere()
    finally:
        paket.aufraeumen()


def analysiere(pfad):
    """Findet alles Installierbare in Archiv, Ordner, Schrift oder Bild.

    Gibt ein Paket zurück (danach aufraeumen!). Wirft InstallFehler mit
    konkretem Grund, wenn nichts Passendes dabei ist.
    """
    if os.path.isdir(pfad):
        name = _sicherer_name(os.path.basename(pfad.rstrip(os.sep)))
        funde, hinweise = _finde(pfad, name, ORDNER_TIEFE)
        if funde:
            return Paket(funde)
        raise InstallFehler(_warum_nichts(pfad, hinweise))
    if not os.path.isfile(pfad):
        raise InstallFehler(_("The file was not found."))

    klein = pfad.lower()
    if klein.endswith(SCHRIFT_ENDUNGEN):
        return Paket([Fund("font", None, [pfad])])
    if klein.endswith(backgrounds.ENDUNGEN):
        return Paket([Fund("bild", os.path.basename(pfad), pfad)])
    if klein.endswith((".7z", ".rar")):
        raise InstallFehler(_("7z and rar archives are not supported. Extract "
                              "it first and drop the folder instead."))

    _raeume_alte_arbeitsordner()
    os.makedirs(ARBEIT_DIR, exist_ok=True)
    arbeit = tempfile.mkdtemp(dir=ARBEIT_DIR, prefix="install-")
    budget = {"anzahl": 0, "groesse": 0}
    try:
        _entpacke(pfad, arbeit, budget)
        funde, hinweise = _finde(arbeit, _archiv_name(pfad))
        if not funde:
            funde = _finde_in_inneren_archiven(arbeit, hinweise, budget)
        if not funde:
            raise InstallFehler(_warum_nichts(arbeit, hinweise))
    except BaseException:
        shutil.rmtree(arbeit, ignore_errors=True)
        raise
    return Paket(funde, arbeit)


def _finde(basis, name, max_tiefe=None):
    """(funde, hinweise) für alles Brauchbare unter basis.

    Designs und Erweiterungen zuerst. Schriften und Bilder nur, wenn keins von
    beiden dabei war: Theme-Pakete liegen oft Vorschaubilder bei, die keine
    Hintergründe werden sollen.
    """
    hinweise = []
    funde = _finde_erweiterungen(basis, max_tiefe, hinweise)
    wurzeln = _theme_wurzeln(basis, max_tiefe)
    if len(wurzeln) > MAX_DESIGNS:
        raise InstallFehler(_("This folder contains too many themes. Drop the "
                              "folder of the theme itself."))
    funde += _finde_themes(wurzeln, basis, name, hinweise)
    if not funde:
        schriften = _dateien(basis, SCHRIFT_ENDUNGEN, max_tiefe)
        if schriften:
            funde = [Fund("font", name, schriften)]
    if not funde:
        bilder = _wallpaper(basis, max_tiefe)
        if bilder:
            funde = [Fund("bilder", name, bilder)]
    return funde, hinweise


def _finde_in_inneren_archiven(basis, hinweise, budget):
    """Archive im Archiv (eine Ebene) entpacken und darin suchen."""
    funde = []
    innere = _dateien(basis, ARCHIV_ENDUNGEN)
    if len(innere) > MAX_INNERE_ARCHIVE:
        raise _ZuGross(_("The archive is too large to unpack safely."))
    for i, archiv in enumerate(innere):
        ziel = os.path.join(basis, ".dm-innen-%d" % i)
        os.makedirs(ziel)
        try:
            _entpacke(archiv, ziel, budget)
            innen, innen_hinweise = _finde(ziel, _archiv_name(archiv))
        except _ZuGross:
            raise
        except InstallFehler:
            continue  # eine kaputte Variante soll die anderen nicht blockieren
        funde += innen
        hinweise += innen_hinweise
    return funde


def _warum_nichts(basis, hinweise=()):
    """Erklärt so konkret wie möglich, warum nichts installiert wurde."""
    if _dateien(basis, WINDOWS_CURSOR_ENDUNGEN):
        return _('This is a Windows cursor (.cur/.ani). GNOME cannot use it '
                 'directly. Download the Linux variant of the theme (a folder '
                 'with a "cursors" subfolder).')
    if _dateien(basis, (".gresource",)):
        return _("This is a login screen (GDM) theme. It replaces system files "
                 "and can lock you out, so it is not installed. For a custom "
                 "login background use Background > Login screen.")
    if _dateien(basis, (".plymouth",)):
        return _("This is a boot splash (Plymouth) theme. Installing it "
                 "rebuilds the boot image as root, so it is not supported.")
    if any(_ist_grub_theme(p) for p in _dateien(basis, ("theme.txt",))):
        return _("This is a boot menu (GRUB) theme. It changes the boot loader "
                 "as root, so it is not supported.")
    if _dateien(basis, ("dock.theme", ".layout.latte")):
        return _("This is a theme for the Plank or Latte dock. Ubuntu Dock and "
                 "Dash to Panel cannot use it.")
    if hinweise:
        return hinweise[0]
    return _("Nothing installable found (no theme, icons, cursor, font, "
             "extension or wallpaper).")


def _ist_grub_theme(pfad):
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            text = f.read(65536)
    except OSError:
        return False
    return "boot_menu" in text or "desktop-image" in text


def _dateien(basis, endungen, max_tiefe=None):
    """Alle Dateien unter basis mit einer der Endungen (optional begrenzt tief)."""
    treffer = []
    for ordner, unter, namen in os.walk(basis):
        if max_tiefe is not None and _tiefe(basis, ordner) >= max_tiefe:
            unter[:] = []
        treffer += [os.path.join(ordner, n) for n in sorted(namen)
                    if n.lower().endswith(endungen)]
    return treffer


def _raeume_alte_arbeitsordner():
    """Reste abgestürzter Installationen (älter als ein Tag) wegräumen. Ein Tag,
    weil ein Paket so lange auf die Auswahl im Dialog warten darf."""
    try:
        for name in os.listdir(ARBEIT_DIR):
            pfad = os.path.join(ARBEIT_DIR, name)
            if (name.startswith("install-")
                    and time.time() - os.path.getmtime(pfad) > 86400):
                shutil.rmtree(pfad, ignore_errors=True)
    except OSError:
        pass


# --- Entpacken (mit Schutz gegen Pfad-Ausbruch und Zip-Bomben) ---

def _entpacke(archiv_pfad, ziel, budget=None):
    """Entpackt ein .zip- oder .tar.*-Archiv nach 'ziel'.

    budget ({"anzahl", "groesse"}) zählt über mehrere Archive mit, damit ein
    Paket voller innerer Archive die Grenzen nicht Stück für Stück umgeht.
    .tar.zst geht nur, wo Python es kann (ab 3.14); sonst meldet is_tarfile
    False und es gibt die ehrliche Format-Meldung.
    """
    budget = budget if budget is not None else {"anzahl": 0, "groesse": 0}
    try:
        if zipfile.is_zipfile(archiv_pfad):
            with zipfile.ZipFile(archiv_pfad) as z:
                infos = z.infolist()
                _pruefe_groesse(len(infos), sum(i.file_size for i in infos),
                                ziel, budget)
                _pruefe_namen(z.namelist())
                _entpacke_zip(z, infos, ziel)
        elif tarfile.is_tarfile(archiv_pfad):
            with tarfile.open(archiv_pfad) as t:
                members = t.getmembers()
                _pruefe_groesse(len(members), sum(m.size for m in members),
                                ziel, budget)
                # Nur die gefahrlosen Member entpacken: Namens-Ausbrüche brechen
                # ab, unsichere Links werden übersprungen (siehe _sichere_tar_member).
                sichere = _sichere_tar_member(members)
                try:
                    t.extractall(ziel, members=sichere, filter="data")
                except TypeError:
                    t.extractall(ziel, members=sichere)  # ältere Python ohne filter
        else:
            raise InstallFehler(
                _("Format not supported. Use a .zip or .tar archive, a font, "
                  "an image or an extracted theme folder."))
        _entferne_fremde_links(ziel, [ziel])
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError) as fehler:
        raise InstallFehler(
            _("The archive could not be extracted.")) from fehler


def _entpacke_zip(z, infos, ziel):
    """Wie extractall, aber mit Symlinks.

    zipfile legt Symlinks als kleine Textdateien an (Inhalt = Linkziel); ein
    Icon-Design mit tausenden Links wäre dann kaputt. Darum erst alle normalen
    Einträge schreiben, danach die Links anlegen: so wird nie durch einen Link
    hindurch geschrieben. Links, die aus dem Ziel hinauszeigen, fallen weg.
    """
    links = []
    for info in infos:
        if stat.S_ISLNK(info.external_attr >> 16):
            links.append(info)
        else:
            z.extract(info, ziel)
    for info in links:
        if info.file_size > 4096:
            continue  # ein Linkziel ist ein kurzer Pfad, kein Datenblock
        linkziel = z.read(info).decode("utf-8", "replace")
        pfad = os.path.join(ziel, info.filename.rstrip("/"))
        if (os.path.isabs(linkziel) or os.path.normpath(os.path.join(
                os.path.dirname(info.filename), linkziel)).startswith("..")):
            continue
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        if not os.path.lexists(pfad):
            os.symlink(linkziel, pfad)


def _entferne_fremde_links(ordner, erlaubt):
    """Entfernt jeden Symlink unter ordner, der nicht in 'erlaubt' auflöst.

    Ketten wie x -> "." plus x/x/x/y -> "../../../z" sehen Link für Link
    harmlos aus und führen trotzdem hinaus. Darum am tatsächlichen Ort gehen
    (os.walk folgt keinen Links), erst ALLE bewerten und dann löschen, und das
    wiederholen, bis nichts mehr hinauszeigt.
    """
    grenzen = [os.path.realpath(g) for g in erlaubt]

    def drin(pfad):
        real = os.path.realpath(pfad)
        return any(real == g or real.startswith(g + os.sep) for g in grenzen)

    while True:
        fremd = [os.path.join(o, n) for o, unter, dateien in os.walk(ordner)
                 for n in unter + dateien
                 if os.path.islink(os.path.join(o, n))
                 and not drin(os.path.join(o, n))]
        if not fremd:
            return
        for pfad in fremd:
            os.unlink(pfad)


class _ZuGross(InstallFehler):
    """Grenze überschritten; bricht das ganze Paket ab, nicht nur eine Variante."""


def _pruefe_groesse(anzahl, groesse, ziel, budget):
    budget["anzahl"] += anzahl
    budget["groesse"] += groesse
    if budget["anzahl"] > MAX_EINTRAEGE or budget["groesse"] > MAX_ENTPACKT:
        raise _ZuGross(_("The archive is too large to unpack safely."))
    if shutil.disk_usage(ziel).free < groesse + 200 * 1024 ** 2:
        raise InstallFehler(_("Not enough free disk space to unpack the "
                              "archive."))


def _ist_ausbruch(pfad):
    """True, wenn der Pfad absolut ist oder über '..' aus dem Ziel ausbricht."""
    return os.path.isabs(pfad) or os.path.normpath(pfad).startswith("..")


def _pruefe_namen(namen):
    """Lehnt absolute Pfade und Ausbrüche über '..' ab (Zip-Slip-Schutz)."""
    for name in namen:
        if _ist_ausbruch(name):
            raise InstallFehler(_("The archive contains unsafe paths."))


def _sichere_tar_member(members):
    """Liste der gefahrlos entpackbaren Member.

    Member, deren NAME aus dem Ziel ausbricht (absoluter Pfad oder '..'), sind ein
    echter Angriff und brechen die Installation ab. Sym-/Hardlinks auf absolute
    oder ausbrechende Ziele werden dagegen nur übersprungen: solche Links sind in
    der Praxis meist kaputte Build-Artefakte (z.B. ein absoluter Link ins Home
    des Paketbauers), das restliche Design bleibt so installierbar.
    """
    sicher = []
    for m in members:
        if _ist_ausbruch(m.name):
            raise InstallFehler(_("The archive contains unsafe paths."))
        if (m.issym() or m.islnk()) and _link_unsicher(m):
            continue
        sicher.append(m)
    return sicher


def _link_unsicher(m):
    """True, wenn das Link-Ziel absolut ist oder aus dem Ziel ausbricht."""
    if os.path.isabs(m.linkname):
        return True
    ziel = os.path.normpath(os.path.join(os.path.dirname(m.name), m.linkname))
    return ziel.startswith("..")


# --- Einsetzen ---

def _ersetze_ordner(quelle, ziel):
    """Kopiert quelle nach ziel, ohne dass je ein halber Ordner sichtbar ist.

    Erst versteckt neben dem Ziel fertig kopieren, dann per rename tauschen.
    Ein vorhandenes Ziel (Update) wird erst danach entfernt; ein Symlink (der
    Cursor-Spiegel in ~/.icons) nur als Verknüpfung.
    """
    if os.path.realpath(quelle) == os.path.realpath(ziel):
        return  # aus dem eigenen Theme-Ordner gezogen, liegt schon da
    basis, name = os.path.split(ziel)
    os.makedirs(basis, exist_ok=True)
    neu = os.path.join(basis, ".dm-neu-" + name)
    alt = os.path.join(basis, ".dm-alt-" + name)
    for rest in (neu, alt):
        _entferne(rest)
    shutil.copytree(quelle, neu, symlinks=True)
    # Am Zielort dürfen Links nur in den Zielordner (Varianten wie Papirus-Dark
    # verlinken auf ../Papirus) oder auf Systemdaten zeigen, sonst nirgendwohin.
    _entferne_fremde_links(neu, [basis, "/usr/share"])
    if os.path.lexists(ziel):
        os.rename(ziel, alt)
    os.rename(neu, ziel)
    _entferne(alt)


def _entferne(pfad):
    if os.path.islink(pfad) or os.path.isfile(pfad):
        os.unlink(pfad)
    elif os.path.isdir(pfad):
        shutil.rmtree(pfad)


# --- Designs ---

def _tiefe(basis, ordner):
    rel = os.path.relpath(ordner, basis)
    return 0 if rel == "." else rel.count(os.sep) + 1


def _theme_wurzeln(basis, max_tiefe=None):
    """Ordner, die eine Design-Wurzel sind, ohne verschachtelte Treffer.

    Sobald ein Ordner einen Marker enthält, gilt er als Wurzel und wir steigen
    nicht tiefer hinein. Hilfsordner für innere Archive und Erweiterungen (die
    haben eigene Icons/CSS) bleiben außen vor.
    """
    wurzeln = []
    for ordner, unterordner, dateien in os.walk(basis):
        unterordner[:] = [u for u in unterordner if not u.startswith(".dm-innen-")]
        if _ist_erweiterung(dateien):
            unterordner[:] = []
        elif THEME_MARKER & (set(unterordner) | set(dateien)):
            wurzeln.append(ordner)
            unterordner[:] = []
        elif max_tiefe is not None and _tiefe(basis, ordner) >= max_tiefe:
            unterordner[:] = []
    return wurzeln


def _hat_css(wurzel, gtk=True, shell=True):
    """Fertiges GTK- bzw. Shell-CSS vorhanden (nicht nur SCSS-Quellen)?"""
    teile = []
    if gtk:
        teile += [("gtk-3.0", "gtk.css"), ("gtk-4.0", "gtk.css")]
    if shell:
        teile.append(("gnome-shell", "gnome-shell.css"))
    return any(os.path.isfile(os.path.join(wurzel, *t)) for t in teile)


def _ist_icon_theme(wurzel):
    """index.theme nach Icon-Theme-Spezifikation (mit Directories=)."""
    try:
        with open(os.path.join(wurzel, "index.theme"), encoding="utf-8",
                  errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    return "[Icon Theme]" in text and re.search(r"^Directories\s*=\s*\S",
                                                text, re.M) is not None


def _arten(wurzel):
    """Die brauchbaren Arten dieser Wurzel (leere Menge = nichts Nutzbares).

    Ein Komplett-Theme kann zugleich GTK-Design und Mauszeiger sein; dann
    gehört es in beide Zielordner.
    """
    arten = set()
    if _hat_css(wurzel):
        arten.add("gtk")
    zeiger = os.path.join(wurzel, "cursors")
    if os.path.isdir(zeiger) and os.listdir(zeiger):
        arten.add("cursor")
    if _ist_icon_theme(wurzel):
        arten.add("icon")
    return arten


def _ist_quellcode(wurzel):
    """GTK-Ordner ohne fertiges CSS, aber mit SCSS: ungebautes Theme."""
    return any(n.endswith(".scss") for _o, _u, namen in os.walk(wurzel)
               for n in namen)


def _systemname(name):
    """True, wenn der Name ein eingebautes Rückfall-Design überdecken würde."""
    if name.lower() in SYSTEM_NAMEN:
        return True
    return _geschuetzt(name) and any(
        os.path.isdir(os.path.join(d, name))
        for d in ("/usr/share/themes", "/usr/share/icons"))


def _archiv_name(archiv_pfad):
    """Theme-Name aus dem Archiv-Dateinamen, für flache Archive ohne Wurzelordner."""
    name = os.path.basename(archiv_pfad)
    for endung in ARCHIV_ENDUNGEN:
        if name.lower().endswith(endung):
            return _sicherer_name(name[:-len(endung)])
    return _sicherer_name(os.path.splitext(name)[0])


def _sicherer_name(name):
    """Bereinigt einen Ordnernamen: keine Pfadtrenner, keine führenden Punkte."""
    name = name.strip().strip(".").strip()
    return name.replace("/", "_").replace(os.sep, "_")


def _name_fuer(wurzel, basis, default_name):
    """Zielname. Liegt die Wurzel direkt im Entpack-Ordner (flaches Archiv ohne
    umschließenden Ordner), wäre basename der zufällige tmp-Name; dann nehmen wir
    den Archivnamen."""
    if os.path.realpath(wurzel) == os.path.realpath(basis):
        return default_name
    name = _sicherer_name(os.path.basename(wurzel.rstrip(os.sep)))
    return name or default_name


def _finde_themes(wurzeln, basis, default_name, hinweise):
    """Ein Fund je brauchbarer Design-Wurzel (gleicher Name nur einmal)."""
    funde, namen = [], set()
    for wurzel in wurzeln:
        name = _name_fuer(wurzel, basis, default_name)
        arten = _arten(wurzel)
        if not name or name in namen:
            continue
        if not arten:
            if _ist_quellcode(wurzel):
                hinweise.append(_(
                    "This is the source code of a theme and has to be built "
                    "first. Download a ready-made release package instead."))
            continue
        if _systemname(name):
            hinweise.append(_('"{name}" would replace a built-in system theme '
                              "and was skipped for safety.").format(name=name))
            continue
        namen.add(name)
        funde.append(Fund("theme", name, wurzel, arten))
    return funde


# --- GNOME-Erweiterungen ---

def _ist_erweiterung(dateien):
    return "metadata.json" in dateien and "extension.js" in dateien


def _finde_erweiterungen(basis, max_tiefe, hinweise):
    """Erweiterungen (metadata.json + extension.js), schon geprüft."""
    funde = []
    for ordner, unter, dateien in os.walk(basis):
        unter[:] = [u for u in unter if not u.startswith(".dm-innen-")]
        if _ist_erweiterung(dateien):
            unter[:] = []
            meta = _erweiterungs_meta(ordner, hinweise)
            if meta:
                funde.append(Fund("extension", meta["name"], ordner, meta=meta))
        elif max_tiefe is not None and _tiefe(basis, ordner) >= max_tiefe:
            unter[:] = []
    return funde


def _erweiterungs_meta(ordner, hinweise):
    """uuid, Name und Shell-Versionen aus metadata.json, None wenn untauglich."""
    try:
        with open(os.path.join(ordner, "metadata.json"), encoding="utf-8") as f:
            meta = json.load(f)
        uuid = meta["uuid"]
    except (OSError, ValueError, KeyError, TypeError):
        hinweise.append(_("The extension has no valid metadata.json."))
        return None
    # uuid wird zum Ordnernamen: nur harmlose Zeichen, kein Pfad.
    if (not isinstance(uuid, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,127}", uuid)):
        hinweise.append(_("The extension has no valid metadata.json."))
        return None
    if os.path.isdir(os.path.join(SYSTEM_EXTENSIONS_DIR, uuid)):
        hinweise.append(_('"{name}" is a system extension and was skipped.')
                        .format(name=uuid))
        return None
    name = meta.get("name") if isinstance(meta.get("name"), str) else uuid
    angabe = meta.get("shell-version")
    versionen = [str(v) for v in angabe if isinstance(v, (str, int, float))] \
        if isinstance(angabe, list) else []
    return {"uuid": uuid, "name": name, "versionen": versionen}


def _installiere_erweiterung(fund):
    """Nach ~/.local/share/gnome-shell/extensions/<uuid>.

    Nur installiert, nie eingeschaltet: Code läuft erst, wenn der Nutzer sie
    auf der Seite Erweiterungen einschaltet. Unter Wayland sieht die Shell neue
    Erweiterungen erst nach dem nächsten Anmelden.
    """
    ziel = os.path.join(EXTENSIONS_DIR, fund.meta["uuid"])
    _ersetze_ordner(fund.quelle, ziel)
    _kompiliere_schemas(os.path.join(ziel, "schemas"))
    name, versionen = fund.meta["name"], fund.meta["versionen"]
    haupt = _shell_hauptversion()
    if haupt and versionen and haupt not in {v.split(".")[0] for v in versionen}:
        return _("Extension: {name} (made for GNOME {versions}, may not "
                 "load)").format(name=name, versions=", ".join(versionen))
    return _("Extension: {name} (enable it after the next login)").format(
        name=name)


def _kompiliere_schemas(ordner):
    """Viele Erweiterungen aus GitHub-Archiven liefern nur die .xml-Schemas."""
    if not os.path.isdir(ordner) or os.path.exists(
            os.path.join(ordner, "gschemas.compiled")):
        return
    if not any(n.endswith(".gschema.xml") for n in os.listdir(ordner)):
        return
    try:
        subprocess.run(["glib-compile-schemas", ordner], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def _shell_hauptversion():
    """'50' bei GNOME Shell 50.1, None wenn nicht ermittelbar."""
    try:
        text = subprocess.run(["gnome-shell", "--version"], capture_output=True,
                              text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    treffer = re.search(r"(\d+)\.", text)
    return treffer.group(1) if treffer else None


# --- Schriften und Bilder ---

def _kopiere_fonts(dateien, unterordner=None):
    """Kopiert Schriften nach FONTS_DIR (bei Paketen in einen eigenen
    Unterordner, dann lassen sie sich als Ganzes wiederfinden) und frischt den
    fontconfig-Cache auf."""
    if not dateien:
        return []
    ziel_dir = os.path.join(FONTS_DIR, unterordner) if unterordner else FONTS_DIR
    os.makedirs(ziel_dir, exist_ok=True)
    for quelle in dateien:
        ziel = os.path.join(ziel_dir, os.path.basename(quelle))
        if os.path.realpath(quelle) != os.path.realpath(ziel):
            shutil.copy2(quelle, ziel)
    try:
        subprocess.run(["fc-cache", "-f", FONTS_DIR], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=120)
    except (OSError, subprocess.SubprocessError):
        pass  # Schriften sind kopiert, der Cache zieht später nach
    anzahl = len(dateien)
    return [ngettext("Font: {n} file", "Font: {n} files", anzahl).format(
        n=anzahl)]


def _installiere_bild(pfad):
    try:
        ziel = backgrounds.uebernehme_bild(pfad)
    except (ValueError, OSError):
        raise InstallFehler(_("The image could not be read.")) from None
    return _("Background") + ": " + os.path.basename(ziel)


def _wallpaper(basis, max_tiefe):
    """Alle ausreichend großen Bilder unter basis (Wallpaper-Paket)."""
    treffer = []
    for pfad in _dateien(basis, backgrounds.ENDUNGEN, max_tiefe):
        groesse = backgrounds.bild_groesse(pfad)
        if (groesse is not None and groesse[0] >= MIN_WALLPAPER[0]
                and groesse[1] >= MIN_WALLPAPER[1]):
            treffer.append(pfad)
    return treffer


def _installiere_bilder(dateien):
    anzahl = 0
    for pfad in dateien:
        try:
            backgrounds.uebernehme_bild(pfad)
            anzahl += 1
        except (ValueError, OSError):
            continue
    if not anzahl:
        return []
    return [ngettext("Backgrounds: {n} image", "Backgrounds: {n} images",
                     anzahl).format(n=anzahl)]
