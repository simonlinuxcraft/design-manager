"""Farben eines GNOME-Shell-Designs aus seiner gnome-shell.css ableiten.

Shell-Designs haben kein Standard-Vorschaubild. Was sich ableiten lässt, ist
die Farbe der Topbar (#panel) und, heuristisch, die Akzentfarbe (die häufigste
kräftige, also nicht-graue Farbe in der CSS). Daraus malt die ShellCard eine
kleine Topbar-Attrappe. Die Werte sind eine Annäherung, kein exaktes Abbild.
"""

import os
import re
from collections import Counter

from src.core import themes


# Fallback-Panel (RGB 0..1), wenn sich aus der CSS nichts lesen lässt: dunkel.
# Für die Standard-Karte (kein Theme) nutzen wir GNOME-Blau als Akzent.
PANEL_FALLBACK = (0.11, 0.11, 0.12)
GNOME_AKZENT = (0.21, 0.52, 0.89)

# Ab dieser Buntheit (max-min der Kanäle) gilt eine Farbe als Akzent, nicht grau.
AKZENT_SCHWELLE = 0.12


def _css_pfad(theme_name):
    for basis in themes.THEME_DIRS:
        pfad = os.path.join(basis, theme_name, "gnome-shell", "gnome-shell.css")
        if os.path.isfile(pfad):
            return pfad
    return None


def _parse_farbe(text):
    """'#rrggbb' oder 'rgb(a)(r,g,b,...)' -> (r,g,b) in 0..1, sonst None."""
    text = text.strip()
    m = re.match(r"#([0-9a-fA-F]{6})", text)
    if m:
        v = m.group(1)
        return (int(v[0:2], 16) / 255, int(v[2:4], 16) / 255, int(v[4:6], 16) / 255)
    m = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", text)
    if m:
        return (int(m.group(1)) / 255, int(m.group(2)) / 255, int(m.group(3)) / 255)
    return None


def _panel_block(css):
    """Inhalt des ersten '#panel { ... }'-Blocks (ohne verschachtelte Regeln)."""
    m = re.search(r"#panel\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


def _eigenschaft(block, name):
    m = re.search(name + r"\s*:\s*([^;]+);", block)
    return m.group(1) if m else None


def _buntheit(rgb):
    return max(rgb) - min(rgb)


def _akzent_farbe(css):
    """Häufigste kräftige (nicht-graue) Farbe der CSS, oder None."""
    zaehler = Counter()
    for treffer in re.findall(r"#[0-9a-fA-F]{6}|rgba?\([0-9,. ]+\)", css):
        rgb = _parse_farbe(treffer)
        if rgb and _buntheit(rgb) > AKZENT_SCHWELLE:
            zaehler[tuple(round(c, 3) for c in rgb)] += 1
    if not zaehler:
        return None
    return zaehler.most_common(1)[0][0]


def colors(theme_name):
    """Liefert {'panel','akzent'} als RGB-Tripel (akzent evtl. None).

    Die Farbe der Indikatoren bestimmt die Karte selbst per Kontrast zum Panel,
    da die color-Angabe in der CSS oft fehlt oder unbrauchbar ist. Für
    theme_name == '' (Standard-Design) nutzen wir Fallback-Panel + GNOME-Blau.
    """
    if not theme_name:
        return {"panel": PANEL_FALLBACK, "akzent": GNOME_AKZENT}

    css = _css_pfad(theme_name)
    panel, akzent = PANEL_FALLBACK, None
    if css:
        try:
            with open(css, encoding="utf-8", errors="ignore") as f:
                inhalt = f.read()
        except OSError:
            inhalt = ""
        block = _panel_block(inhalt)
        p = _parse_farbe(_eigenschaft(block, "background-color") or "")
        if p:
            panel = p
        akzent = _akzent_farbe(inhalt)
    return {"panel": panel, "akzent": akzent}
