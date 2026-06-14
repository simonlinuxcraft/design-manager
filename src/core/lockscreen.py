"""Sperrbildschirm-Hintergrund über das aktive GNOME-Shell-Design.

Experimentell. GNOME bietet keinen Schlüssel für ein eigenes Sperrbild; der
Sperrbildschirm zeigt sonst den (verblurrten) Desktop-Hintergrund. Als Umweg
schreiben wir eine CSS-Regel für #lockDialogGroup in die gnome-shell.css des
gerade aktiven Shell-Designs.

Das wirkt nur, wenn ein eigenes (beschreibbares) Shell-Design aktiv ist, die
Erweiterung User Themes eingeschaltet ist und die Shell danach neu geladen
wurde. Auf GNOME 40+ kann der verblurrte Sperrbildschirm die Regel überdecken.

Der Eingriff ist reversibel: wir schreiben einen klar markierten Block und
entfernen ihn rückstandslos wieder.
"""

import os
import re
import tempfile

from src.core import themes


MARKER_START = "/* === design-manager-lockscreen START === */"
MARKER_END = "/* === design-manager-lockscreen END === */"

# Findet den kompletten Block zwischen den Markern (inkl. Marker), auch über
# mehrere Zeilen.
_BLOCK = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END) + r"\n?",
    re.DOTALL,
)
_URL = re.compile(r'url\("file://([^"]+)"\)')


def _css_pfad(settings):
    """gnome-shell.css des aktiven Shell-Designs, oder None.

    Ein leerer Design-Name bedeutet das System-Standard-Design; das liegt
    schreibgeschützt in /usr/share und kommt hier nicht in Frage.
    """
    name = settings.shell_theme()
    if not name:
        return None
    for basis in themes.THEME_DIRS:
        css = os.path.join(basis, name, "gnome-shell", "gnome-shell.css")
        if os.path.isfile(css):
            return css
    return None


def verfuegbar(settings):
    """True, wenn ein beschreibbares Shell-Design aktiv ist (Voraussetzung)."""
    css = _css_pfad(settings)
    return css is not None and os.access(css, os.W_OK)


def aktuelles_bild(settings):
    """Pfad des aktuell eingetragenen Sperrbilds, oder None."""
    css = _css_pfad(settings)
    if css is None or not os.path.isfile(css):
        return None
    treffer = _BLOCK.search(_lies(css))
    if not treffer:
        return None
    url = _URL.search(treffer.group(0))
    return url.group(1) if url else None


def set_background(settings, bild_pfad):
    """Trägt ein Sperrbild ins aktive Shell-Design-CSS ein (reversibel).

    Ein eventuell schon vorhandener Block wird ersetzt, sodass nie mehrere
    entstehen. Rückgabe True bei Erfolg, False wenn kein beschreibbares
    Shell-Design aktiv ist.
    """
    css = _css_pfad(settings)
    if css is None or not os.access(css, os.W_OK):
        return False

    text = _BLOCK.sub("", _lies(css)).rstrip() + "\n"
    block = (
        MARKER_START + "\n"
        "#lockDialogGroup {\n"
        '  background-image: url("file://' + bild_pfad + '");\n'
        "  background-size: cover;\n"
        "  background-repeat: no-repeat;\n"
        "  background-position: center;\n"
        "}\n"
        + MARKER_END + "\n"
    )
    _schreib(css, text + block)
    return True


def clear_background(settings):
    """Entfernt den Sperrbild-Block wieder. True wenn ausgeführt."""
    css = _css_pfad(settings)
    if css is None or not os.access(css, os.W_OK):
        return False
    text = _lies(css)
    neu = _BLOCK.sub("", text).rstrip() + "\n"
    if neu != text:
        _schreib(css, neu)
    return True


def _lies(pfad):
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def _schreib(pfad, text):
    """Schreibt die Datei atomar: erst in eine temporäre Datei im selben Ordner,
    dann per os.replace an ihren Platz ziehen.

    Diese gnome-shell.css gehört zum aktiven Shell-Design und wird von der
    laufenden Shell gelesen. Ein direkter open(..,"w")-Write könnte sie bei einem
    Abbruch (Kill, volle Platte) halb geschrieben und damit unbrauchbar
    zurücklassen. os.replace ist atomar: entweder steht die komplette neue Datei
    da oder die unveränderte alte, nie ein Torso. Schlägt das Schreiben fehl,
    bleibt das Original unangetastet und die temporäre Datei wird entfernt.
    """
    ordner = os.path.dirname(pfad)
    fd, tmp = tempfile.mkstemp(dir=ordner, prefix=".dm-shell-", suffix=".css")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, pfad)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
