"""Hintergrundbilder auflisten.

Zwei Quellen: die mit dem System gelieferten Bilder unter /usr/share/backgrounds
und die vom Nutzer selbst abgelegten unter ~/.local/share/backgrounds. Wir
sammeln nur die direkt enthaltenen Bilddateien ein, nicht rekursiv, damit die
Galerie übersichtlich bleibt.
"""

import json
import os
import threading

from gi.repository import Gdk, GdkPixbuf, GLib


SYSTEM_DIR = "/usr/share/backgrounds"
USER_DIR = os.path.expanduser("~/.local/share/backgrounds")

# Liste der Bilder, die der Nutzer aus der App ausgeblendet hat. Nur ein
# Merker, die Dateien selbst bleiben auf der Platte.
HIDDEN_FILE = os.path.expanduser("~/.config/design-manager/hidden-backgrounds.json")

# Welche Dateiendungen wir als Bild akzeptieren.
ENDUNGEN = (".jpg", ".jpeg", ".png", ".webp")


def _versteckte():
    """Menge der ausgeblendeten Bildpfade (realpath)."""
    try:
        with open(HIDDEN_FILE) as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def hide_wallpaper(pfad):
    """Blendet ein Bild in der App aus, ohne die Datei zu löschen."""
    versteckt = _versteckte()
    versteckt.add(os.path.realpath(pfad))
    os.makedirs(os.path.dirname(HIDDEN_FILE), exist_ok=True)
    with open(HIDDEN_FILE, "w") as f:
        json.dump(sorted(versteckt), f)


def _bilder_in(ordner):
    """Pfade aller Bilddateien direkt in 'ordner', alphabetisch."""
    if not os.path.isdir(ordner):
        return []
    treffer = []
    for name in sorted(os.listdir(ordner), key=str.lower):
        if name.lower().endswith(ENDUNGEN):
            pfad = os.path.join(ordner, name)
            if os.path.isfile(pfad):
                treffer.append(pfad)
    return treffer


def list_system_wallpapers():
    """Die mit dem System gelieferten Hintergrundbilder."""
    return _bilder_in(SYSTEM_DIR)


def list_user_wallpapers():
    """Die vom Nutzer abgelegten Bilder, ohne die in der App ausgeblendeten."""
    versteckt = _versteckte()
    return [p for p in _bilder_in(USER_DIR)
            if os.path.realpath(p) not in versteckt]


def load_texture_async(pfad, breite, hoehe, callback):
    """Dekodiert ein Bild verkleinert in einem Hintergrund-Thread.

    Wichtig für die Geschwindigkeit: Wallpaper sind oft riesig (z.B. 3480x2160).
    Das Dekodieren blockiert sonst den Main-Thread und lässt die App hängen.
    Wir dekodieren daher nebenher und rufen callback(textur) anschließend im
    Main-Loop auf (bei Fehler gar nicht).
    """
    def fertig(pixbuf):
        # Textur erst hier (Main-Thread) aus dem Pixbuf bauen.
        callback(Gdk.Texture.new_for_pixbuf(pixbuf))
        return False

    def worker():
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                pfad, breite, hoehe, True)
        except Exception:
            return
        GLib.idle_add(fertig, pixbuf)

    threading.Thread(target=worker, daemon=True).start()
