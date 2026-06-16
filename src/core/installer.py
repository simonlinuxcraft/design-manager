"""Designs, Symbole, Mauszeiger und Schriften aus einem Archiv installieren.

Eine heruntergeladene Datei (.tar.gz, .tar.xz, .tar.bz2 oder .zip) wird in einen
temporären Ordner entpackt. Darin suchen wir die enthaltenen Designs bzw.
Schriften und kopieren sie in die passenden Nutzer-Ordner (Designs und Symbole
nach ~/.local/share, Mauszeiger nach ~/.icons, damit der X-Server sie findet),
nie in systemweite (kein sudo).

Erkennung: ein Ordner mit gtk-*/gnome-shell ist ein GTK-/Shell-Design, einer mit
cursors/ ein Mauszeiger-Design, einer nur mit index.theme ein Symbol-Design.
Findet sich kein Design, aber Schriftdateien, wird es als Schrift-Archiv
behandelt (und danach fc-cache aufgerufen).

Jede Seite ruft install() mit 'erwartet' auf und nimmt so nur an, was zu ihr
gehört: die Mauszeiger-Seite keine GTK-Designs usw. Passt der Typ nicht, gibt es
eine Meldung mit Verweis auf die richtige Seite statt einer stillen Fehlablage.
"""

import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile

from src.i18n import _, ngettext


THEMES_DIR = os.path.expanduser("~/.local/share/themes")
ICONS_DIR = os.path.expanduser("~/.local/share/icons")
FONTS_DIR = os.path.expanduser("~/.local/share/fonts")
# Mauszeiger gehen nach ~/.icons, NICHT ~/.local/share/icons: der X-Server
# (libXcursor) durchsucht nur ~/.icons, /usr/share/icons und /usr/share/pixmaps.
# Ein nur unter ~/.local/share/icons liegendes Cursor-Theme würde unter X11 nie
# als Zeiger geladen. Symbol-Designs bleiben in ~/.local/share/icons, die findet
# die GTK-Icon-Suche dort problemlos.
CURSORS_DIR = os.path.expanduser("~/.icons")

SCHRIFT_ENDUNGEN = (".ttf", ".otf", ".ttc", ".pfb")

# Windows-Mauszeiger. Die tauchen auf gnome-look oft als "...-Windows"-Variante
# auf, lassen sich unter GNOME aber nicht nutzen (GNOME braucht XCursor). Wir
# erkennen sie, um eine hilfreiche Meldung statt "nichts gefunden" zu geben.
WINDOWS_CURSOR_ENDUNGEN = (".cur", ".ani")

# Unterordner/Dateien, an denen wir die Wurzel eines Designs erkennen.
THEME_MARKER = {
    "index.theme", "cursors",
    "gtk-2.0", "gtk-3.0", "gtk-4.0", "gnome-shell",
}

# Pro Design-Art: Zielordner und das Wort fürs Erfolgs-Label.
ZIELE = {
    "gtk": (THEMES_DIR, _("Theme")),
    "cursor": (CURSORS_DIR, _("Cursor")),
    "icon": (ICONS_DIR, _("Icons")),
}

# Pro Art: ein Satz und die Seite, auf die sie gehört. Für die Meldung, wenn
# etwas auf der falschen Seite abgelegt wird.
ART_INFO = {
    "cursor": (_("This is a cursor theme."), _("Cursor")),
    "icon": (_("This is an icon theme."), _("Icons")),
    "gtk": (_("This is a GTK theme."), _("GTK Theme")),
    "font": (_("This is a font."), _("Fonts")),
}


class InstallFehler(Exception):
    """Archiv ließ sich nicht entpacken oder enthielt nichts Passendes."""


def install(archiv_pfad, erwartet=None):
    """Installiert den Inhalt eines Archivs in die passenden Nutzer-Ordner.

    'erwartet' schränkt auf bestimmte Arten ein (Teilmenge von "cursor", "icon",
    "gtk", "font"); None lässt alles zu. So nimmt jede Seite nur an, was zu ihr
    gehört, und verweist sonst auf die richtige Seite.

    Gibt eine Liste menschenlesbarer Beschreibungen zurück, z.B.
    ["Symbole: Papirus"] oder ["Schrift: 3 Datei(en)"]. Wirft InstallFehler mit
    konkretem Grund, wenn nichts Passendes gefunden wurde.
    """
    if os.path.isdir(archiv_pfad):
        raise InstallFehler(_("This is a folder, not an archive. Please "
                              "choose an archive (.tar.gz/.zip)."))
    if not os.path.isfile(archiv_pfad):
        raise InstallFehler(_("The file was not found."))

    # Eine direkt gewählte Schriftdatei (kein Archiv) gleich übernehmen.
    if archiv_pfad.lower().endswith(SCHRIFT_ENDUNGEN):
        if not _erlaubt("font", erwartet):
            raise InstallFehler(_falsche_art({"font"}))
        ergebnis = _kopiere_fonts([archiv_pfad])
        if not ergebnis:
            raise InstallFehler(_("The font could not be copied."))
        return ergebnis

    with tempfile.TemporaryDirectory() as tmp:
        _entpacke(archiv_pfad, tmp)

        wurzeln = _theme_wurzeln(tmp)
        if wurzeln:
            ergebnis, abgelehnt = _installiere_themes(
                wurzeln, erwartet, tmp, _archiv_name(archiv_pfad))
            if ergebnis:
                return ergebnis
            if abgelehnt:
                raise InstallFehler(_falsche_art(abgelehnt))

        font_dateien = _font_dateien(tmp)
        if font_dateien:
            if not _erlaubt("font", erwartet):
                raise InstallFehler(_falsche_art({"font"}))
            ergebnis = _kopiere_fonts(font_dateien)
            if ergebnis:
                return ergebnis

        raise InstallFehler(_warum_nichts(tmp))


def _erlaubt(art, erwartet):
    return erwartet is None or art in erwartet


def _falsche_art(arten):
    """Meldung, wenn nur unpassende Arten im Archiv waren (Verweis auf die
    richtige Seite)."""
    satz, seite = ART_INFO[next(iter(arten))]
    return _('{sentence} Please install it on the "{page}" page.').format(
        sentence=satz, page=seite)


def _warum_nichts(basis):
    """Erklärt, warum nichts Installierbares gefunden wurde, möglichst konkret.

    Ein Windows-Mauszeiger ist der häufige Stolperstein (falsche Variante von
    gnome-look geladen), darum dafür ein klarer Hinweis statt einer pauschalen
    Meldung.
    """
    if _enthaelt_endung(basis, WINDOWS_CURSOR_ENDUNGEN):
        return _('This is a Windows cursor (.cur/.ani). GNOME cannot use it '
                 'directly. Download the Linux variant of the theme (a folder '
                 'with a "cursors" subfolder).')
    return _("No theme and no font found in the archive.")


def _enthaelt_endung(basis, endungen):
    """True, wenn unter basis (rekursiv) eine Datei mit einer der Endungen liegt."""
    for ordner, _unter, namen in os.walk(basis):
        for n in namen:
            if n.lower().endswith(endungen):
                return True
    return False


# --- Entpacken (mit Schutz gegen Pfad-Ausbruch) ---

def _entpacke(archiv_pfad, ziel):
    """Entpackt ein .zip- oder .tar.*-Archiv nach 'ziel'."""
    name = archiv_pfad.lower()
    try:
        if name.endswith(".zip") or zipfile.is_zipfile(archiv_pfad):
            with zipfile.ZipFile(archiv_pfad) as z:
                _pruefe_namen(z.namelist())
                z.extractall(ziel)
        elif tarfile.is_tarfile(archiv_pfad):
            with tarfile.open(archiv_pfad) as t:
                # Nur die gefahrlosen Member entpacken: Namens-Ausbrüche brechen
                # ab, unsichere Links werden übersprungen (siehe _sichere_tar_member).
                sichere = _sichere_tar_member(t.getmembers())
                try:
                    t.extractall(ziel, members=sichere, filter="data")
                except TypeError:
                    t.extractall(ziel, members=sichere)  # ältere Python ohne filter
        else:
            raise InstallFehler(
                _("Format not supported (only .zip and .tar.*)."))
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as fehler:
        raise InstallFehler(
            _("The archive could not be extracted.")) from fehler


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
    oder ausbrechende Ziele werden dagegen nur übersprungen, nicht abgelehnt: wir
    verfolgen Links beim Kopieren nicht (kein Datenabfluss), und solche Links sind
    in der Praxis meist kaputte Build-Artefakte (z.B. ein absoluter Link ins Home
    des Paketbauers). So lässt sich ein sonst gültiges Design trotz einzelner
    solcher Links installieren, statt es komplett abzulehnen.
    """
    sicher = []
    for m in members:
        if _ist_ausbruch(m.name):
            raise InstallFehler(_("The archive contains unsafe paths."))
        if (m.issym() or m.islnk()) and _link_unsicher(m):
            continue  # überspringen, nicht entpacken
        sicher.append(m)
    return sicher


def _link_unsicher(m):
    """True, wenn das Link-Ziel absolut ist oder aus dem Ziel ausbricht."""
    if os.path.isabs(m.linkname):
        return True
    ziel = os.path.normpath(os.path.join(os.path.dirname(m.name), m.linkname))
    return ziel.startswith("..")


# --- Designs erkennen und kopieren ---

def _theme_wurzeln(basis):
    """Ordner, die eine Design-Wurzel sind, ohne verschachtelte Treffer.

    Sobald ein Ordner einen Marker enthält, gilt er als Wurzel und wir steigen
    nicht tiefer hinein (ein Icon-Design hat index.theme oben, aber viele
    Unterordner, die wir nicht einzeln als Designs zählen wollen).
    """
    wurzeln = []
    for ordner, unterordner, dateien in os.walk(basis):
        if THEME_MARKER & (set(unterordner) | set(dateien)):
            wurzeln.append(ordner)
            unterordner[:] = []  # nicht weiter absteigen
    return wurzeln


def _ist_cursor(wurzel):
    return os.path.isdir(os.path.join(wurzel, "cursors"))


def _ist_gtk(wurzel):
    return any(
        os.path.isdir(os.path.join(wurzel, d))
        for d in ("gtk-2.0", "gtk-3.0", "gtk-4.0", "gnome-shell")
    )


def _arten(wurzel):
    """Alle Design-Arten, die die Wurzel erfüllt.

    Ein Komplett-Theme kann zugleich GTK-Design und Mauszeiger sein (gtk-*/ und
    cursors/ im selben Ordner); dann gehört es in beide Zielordner, sonst wäre
    der mitgelieferte Mauszeiger nicht auswählbar. Nur wenn nichts davon zutrifft,
    ist es ein Symbol-Design.
    """
    arten = set()
    if _ist_gtk(wurzel):
        arten.add("gtk")
    if _ist_cursor(wurzel):
        arten.add("cursor")
    if not arten:
        arten.add("icon")
    return arten


def _archiv_name(archiv_pfad):
    """Theme-Name aus dem Archiv-Dateinamen, für flache Archive ohne Wurzelordner."""
    name = os.path.basename(archiv_pfad)
    for endung in (".tar.gz", ".tar.xz", ".tar.bz2", ".tgz", ".zip"):
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


def _installiere_themes(wurzeln, erwartet, basis, default_name):
    """Kopiert jede passende Design-Wurzel in ihre Zielordner.

    Eine Wurzel kann mehrere Arten erfüllen und wird dann in jeden zutreffenden,
    erlaubten Zielordner kopiert. Gibt (ergebnis, abgelehnt) zurück; abgelehnt
    sind die Arten, die wegen 'erwartet' übersprungen wurden (für eine hilfreiche
    Meldung, falls gar nichts passte).
    """
    ergebnis = []
    abgelehnt = set()
    for wurzel in wurzeln:
        arten = _arten(wurzel)
        erlaubte = arten if erwartet is None else (arten & erwartet)
        if not erlaubte:
            abgelehnt |= arten
            continue
        name = _name_fuer(wurzel, basis, default_name)
        for art in sorted(erlaubte):
            ziel_basis, label = ZIELE[art]
            os.makedirs(ziel_basis, exist_ok=True)
            shutil.copytree(wurzel, os.path.join(ziel_basis, name),
                            dirs_exist_ok=True, symlinks=True)
            ergebnis.append(label + ": " + name)
    return ergebnis, abgelehnt


# --- Schriften kopieren und Cache aktualisieren ---

def _font_dateien(basis):
    """Alle Schriftdateien unter basis (rekursiv)."""
    dateien = []
    for ordner, _unter, namen in os.walk(basis):
        for n in namen:
            if n.lower().endswith(SCHRIFT_ENDUNGEN):
                dateien.append(os.path.join(ordner, n))
    return dateien


def _kopiere_fonts(dateien):
    """Kopiert die Schriftdateien nach FONTS_DIR und frischt den Cache auf."""
    if not dateien:
        return []

    os.makedirs(FONTS_DIR, exist_ok=True)
    for quelle in dateien:
        shutil.copy2(quelle, os.path.join(FONTS_DIR, os.path.basename(quelle)))

    _fc_cache()
    anzahl = len(dateien)
    return [ngettext("Font: {n} file", "Font: {n} files", anzahl).format(
        n=anzahl)]


def _fc_cache():
    """Aktualisiert den fontconfig-Cache, damit neue Schriften sofort auftauchen."""
    try:
        subprocess.run(
            ["fc-cache", "-f", FONTS_DIR],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass  # fc-cache fehlt; Schriften sind kopiert, Cache zieht später nach
