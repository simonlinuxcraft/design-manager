"""Xcursor-Dateien parsen, um eine Vorschau des Mauszeigers zu bekommen.

Cursor liegen als X11-Xcursor-Dateien (Magic "Xcur") in <icon-dir>/<theme>/
cursors/. Das Format ist einfach: ein Header, eine Inhaltsverzeichnis-Tabelle
und mehrere Bild-Chunks (eine Größe pro Eintrag) mit ARGB-Pixeldaten. Wir
suchen den Hauptzeiger, nehmen die passende Größe und bauen daraus eine
Gdk.MemoryTexture.
"""

import os
import struct

from gi.repository import Gdk, GLib

from src.core import themes


# Cursor-Namen für die Vorschau, in drei Gruppen wie die drei Beispiel-Icons der
# Symbol-Karten: Pfeil, Hand (Link), Text. Pro Gruppe mehrere Namen als Fallback,
# weil Themes denselben Zeiger unterschiedlich benennen; der erste gefundene zählt.
ZEIGER_NAMEN = ["left_ptr", "default", "arrow"]
HAND_NAMEN = ["hand2", "pointer", "hand1", "pointing_hand"]
TEXT_NAMEN = ["xterm", "text", "ibeam"]
VORSCHAU_GRUPPEN = [ZEIGER_NAMEN, HAND_NAMEN, TEXT_NAMEN]

# Chunk-Typ für Bilder im Xcursor-Format.
TYP_BILD = 0xFFFD0002


def _finde_cursor_datei(theme_name, namen):
    """Pfad zur ersten vorhandenen Cursor-Datei aus 'namen', oder None."""
    for basis in themes.ICON_DIRS:
        cursors = os.path.join(basis, theme_name, "cursors")
        if not os.path.isdir(cursors):
            continue
        for name in namen:
            pfad = os.path.join(cursors, name)
            if os.path.exists(pfad):
                # Symlinks (z.B. left_ptr -> default) auflösen.
                return os.path.realpath(pfad)
    return None


def _uint32(daten, offset):
    return struct.unpack_from("<I", daten, offset)[0]


def load_cursor_texture(theme_name, namen, size=36):
    """Gibt eine Gdk.MemoryTexture des ersten in 'namen' gefundenen Zeigers
    zurück, oder None. Wählt aus den enthaltenen Größen die zu 'size' nächste.
    """
    pfad = _finde_cursor_datei(theme_name, namen)
    if pfad is None:
        return None
    try:
        with open(pfad, "rb") as f:
            daten = f.read()
    except OSError:
        return None

    if len(daten) < 16 or daten[0:4] != b"Xcur":
        return None

    ntoc = _uint32(daten, 12)

    # Inhaltsverzeichnis: ab Byte 16, je Eintrag 12 Byte (typ, subtyp, position).
    bilder = []  # (nominale_groesse, position)
    for i in range(ntoc):
        eintrag = 16 + i * 12
        if eintrag + 12 > len(daten):
            break
        typ = _uint32(daten, eintrag)
        subtyp = _uint32(daten, eintrag + 4)
        position = _uint32(daten, eintrag + 8)
        if typ == TYP_BILD:
            bilder.append((subtyp, position))

    if not bilder:
        return None

    # Die Größe nehmen, die der gewünschten am nächsten ist.
    _, position = min(bilder, key=lambda b: abs(b[0] - size))

    # Bild-Chunk: header(4), typ(4), subtyp(4), version(4), width(4), height(4),
    # xhot(4), yhot(4), delay(4), dann width*height Pixel je 4 Byte (ARGB,
    # premultipliziert, little-endian -> Bytes in Reihenfolge B, G, R, A).
    if position + 36 > len(daten):
        return None
    breite = _uint32(daten, position + 16)
    hoehe = _uint32(daten, position + 20)
    pixel_start = position + 36
    pixel_laenge = breite * hoehe * 4
    if breite == 0 or hoehe == 0 or pixel_start + pixel_laenge > len(daten):
        return None

    pixel = daten[pixel_start:pixel_start + pixel_laenge]
    return Gdk.MemoryTexture.new(
        breite,
        hoehe,
        Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED,
        GLib.Bytes.new(pixel),
        breite * 4,
    )
