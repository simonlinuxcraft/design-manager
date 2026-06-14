"""Akzentfarbe aus dem Hintergrundbild vorschlagen.

GNOME bietet ab Version 47 neun feste Akzentfarben. Diese Funktion liest das
aktuelle Wallpaper klein ein, sucht den dominanten kräftigen Farbton (graue und
dunkle Pixel zählen kaum) und gibt den Namen der nächstliegenden der neun Farben
zurück. Angewendet wird erst auf Klick (siehe pages/system.py); ein Fehlgriff
ist rein kosmetisch.
"""

import colorsys

from gi.repository import GdkPixbuf


# Die neun GNOME-Akzentfarben als RGB (0..255), gespiegelt aus src/style.css
# (.akzent-<name>). Bei einer Farbänderung dort hier mitziehen.
AKZENT_RGB = {
    "blue":   (0x35, 0x84, 0xe4),
    "teal":   (0x21, 0x90, 0xa4),
    "green":  (0x3a, 0x94, 0x4a),
    "yellow": (0xc8, 0x88, 0x00),
    "orange": (0xed, 0x5b, 0x00),
    "red":    (0xe6, 0x2d, 0x42),
    "pink":   (0xd5, 0x61, 0x99),
    "purple": (0x91, 0x41, 0xac),
    "slate":  (0x6f, 0x83, 0x96),
}

# Ab diesem Gewicht (Sättigung * Helligkeit) zählt ein Pixel als kräftig.
KRAFT_SCHWELLE = 0.15
# Anzahl Farbton-Eimer (12 = je 30°), in die wir die kräftigen Pixel sortieren.
EIMER = 12


def _dominante_farbe(pixbuf):
    """Mittlere RGB-Farbe des stärksten Farbton-Eimers, oder None.

    Statt alle kräftigen Pixel zu mitteln (was bei gegensätzlichen Farbtönen ein
    fades Grau ergäbe) sortieren wir nach Farbton in Eimer und nehmen den
    schwersten. So gewinnt die wirklich vorherrschende Farbe.
    """
    breite, hoehe = pixbuf.get_width(), pixbuf.get_height()
    kanaele = pixbuf.get_n_channels()
    rowstride = pixbuf.get_rowstride()
    pixel = pixbuf.get_pixels()

    gewicht = [0.0] * EIMER
    summe = [[0.0, 0.0, 0.0] for _ in range(EIMER)]

    for y in range(hoehe):
        zeile = y * rowstride
        for x in range(breite):
            i = zeile + x * kanaele
            r, g, b = pixel[i], pixel[i + 1], pixel[i + 2]
            if kanaele == 4 and pixel[i + 3] < 128:
                continue  # zu durchsichtig
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            w = s * v
            if w < KRAFT_SCHWELLE:
                continue
            idx = min(EIMER - 1, int(h * EIMER))
            gewicht[idx] += w
            summe[idx][0] += r * w
            summe[idx][1] += g * w
            summe[idx][2] += b * w

    best = max(range(EIMER), key=lambda k: gewicht[k])
    if gewicht[best] == 0:
        return None
    g = gewicht[best]
    return (summe[best][0] / g, summe[best][1] / g, summe[best][2] / g)


def _naechster_akzent(rgb):
    """Name der Akzentfarbe mit dem kleinsten RGB-Abstand zu rgb."""
    bester, beste_dist = None, None
    for name, (r, g, b) in AKZENT_RGB.items():
        dist = (r - rgb[0]) ** 2 + (g - rgb[1]) ** 2 + (b - rgb[2]) ** 2
        if beste_dist is None or dist < beste_dist:
            bester, beste_dist = name, dist
    return bester


def vorschlag(pfad):
    """Vorgeschlagener Akzentname für das Bild unter 'pfad', oder None."""
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(pfad, 64, 64, True)
    except Exception:
        return None
    rgb = _dominante_farbe(pixbuf)
    if rgb is None:
        return None
    return _naechster_akzent(rgb)
