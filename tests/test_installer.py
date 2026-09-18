"""Installer-Selbsttest in einem Wegwerf-HOME.

    LANGUAGE=en python3 tests/test_installer.py
"""

import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import zipfile

HOME = tempfile.mkdtemp(prefix="dm-test-home-")
os.environ["HOME"] = HOME  # vor den src-Importen, die Pfade stehen zur Importzeit fest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi  # noqa: E402
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

from src.core import backgrounds, installer  # noqa: E402

QUELLE = tempfile.mkdtemp(prefix="dm-test-src-")
ICON_INDEX = b"[Icon Theme]\nName=X\nDirectories=16x16\n"


def datei(pfad, inhalt=b"x"):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "wb") as f:
        f.write(inhalt)


def bild(pfad, breite, hoehe, farbe=0):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, breite, hoehe)
    pb.fill(farbe)
    pb.savev(pfad, "png", [], [])
    return open(pfad, "rb").read()


def zip_aus(name, eintraege, links=None):
    pfad = os.path.join(QUELLE, name)
    with zipfile.ZipFile(pfad, "w") as z:
        for arc, inhalt in eintraege.items():
            z.writestr(arc, inhalt)
        for arc, ziel in (links or {}).items():
            info = zipfile.ZipInfo(arc)
            info.external_attr = 0o120777 << 16
            z.writestr(info, ziel)
    return pfad


def tar_aus(name, eintraege, modus="w:gz"):
    pfad = os.path.join(QUELLE, name)
    with tarfile.open(pfad, modus) as t:
        for arc, inhalt in eintraege.items():
            info = tarfile.TarInfo(arc)
            info.size = len(inhalt)
            t.addfile(info, io.BytesIO(inhalt))
    return pfad


def fehler(pfad):
    try:
        installer.install(pfad)
    except installer.InstallFehler as e:
        return str(e)
    raise AssertionError("kein Fehler bei " + pfad)


# Symbol-Design im Zip mit Wurzelordner.
r = installer.install(zip_aus("icons.zip", {
    "Papi/index.theme": ICON_INDEX, "Papi/16x16/a.png": b"x"}))
assert r == ["Icons: Papi"], r
assert os.path.isfile(os.path.join(installer.ICONS_DIR, "Papi", "index.theme"))

# Symlinks im Zip bleiben Links; eine Kette, die hinausführt, fällt weg.
installer.install(zip_aus("links.zip", {
    "Tela/index.theme": ICON_INDEX, "Tela/24/a.svg": b"x"},
    links={"Tela/24@2x": "24", "Tela/x": ".", "Tela/x/x/x/y": "../../../raus"}))
tela = os.path.join(installer.ICONS_DIR, "Tela")
assert os.path.islink(os.path.join(tela, "24@2x"))
assert os.path.isfile(os.path.join(tela, "24@2x", "a.svg"))
assert not os.path.lexists(os.path.join(tela, "y"))

# Kette über einen Link direkt in der Wurzel (x -> ".") darf auch nicht hinaus.
installer.install(zip_aus("kette.zip", {"Kette/index.theme": ICON_INDEX},
                          links={"x": ".",
                                 "x/x/x/x/Kette/y": "../../../../../MARKER"}))
kette = os.path.join(installer.ICONS_DIR, "Kette")
for ordner, _u, namen in os.walk(kette):
    for n in namen + _u:
        p = os.path.join(ordner, n)
        if os.path.islink(p):
            assert os.path.realpath(p).startswith(installer.ICONS_DIR + os.sep), p

# Update ersetzt den alten Stand komplett, keine Zwischenordner bleiben liegen.
r = installer.install(zip_aus("icons2.zip", {
    "Papi/index.theme": ICON_INDEX, "Papi/32x32/b.png": b"x"}))
assert not os.path.exists(os.path.join(installer.ICONS_DIR, "Papi", "16x16"))
assert not [n for n in os.listdir(installer.ICONS_DIR) if n.startswith(".dm-")]

# Flaches tar.xz ohne Wurzelordner: Name kommt vom Archiv.
r = installer.install(tar_aus("Flach-GTK.tar.xz", {
    "gtk-3.0/gtk.css": b"", "index.theme": b""}, "w:xz"))
assert r == ["Theme: Flach-GTK"], r

# Zip voller Varianten-Archive (gnome-look-Stil): eine Ebene tiefer.
innen_a = tar_aus("Zeiger-A.tar.gz", {"Zeiger-A/cursors/left_ptr": b"x"})
innen_b = tar_aus("Zeiger-B.tar.gz", {"Zeiger-B/cursors/left_ptr": b"x"})
r = installer.install(zip_aus("pack.zip", {
    "Zeiger-A.tar.gz": open(innen_a, "rb").read(),
    "Zeiger-B.tar.gz": open(innen_b, "rb").read()}))
assert sorted(r) == ["Cursor: Zeiger-A", "Cursor: Zeiger-B"], r

# All-in-one-Paket: analysieren, nur eine Auswahl installieren, aufräumen.
paket = installer.analysiere(zip_aus("allinone.zip", {
    "pack/themes/Var-%d/gtk-4.0/gtk.css" % i: b"" for i in range(8)}))
assert len(paket.auswaehlbar()) == 8 > installer.AUSWAHL_AB
wahl = [f for f in paket.auswaehlbar() if f.name in ("Var-2", "Var-5")]
assert sorted(paket.installiere(wahl)) == ["Theme: Var-2", "Theme: Var-5"]
paket.aufraeumen()
assert sorted(n for n in os.listdir(installer.THEMES_DIR)
              if n.startswith("Var-")) == ["Var-2", "Var-5"]
assert os.listdir(installer.ARBEIT_DIR) == []

# Entpackter Ordner, und derselbe Ordner erneut aus dem Ziel gezogen.
ordner = os.path.join(QUELLE, "Ordner-Theme")
datei(os.path.join(ordner, "gnome-shell", "gnome-shell.css"))
assert installer.install(ordner) == ["Theme: Ordner-Theme"]
ziel = os.path.join(installer.THEMES_DIR, "Ordner-Theme")
assert installer.install(ziel) == ["Theme: Ordner-Theme"]  # kein SameFileError

# GNOME-Erweiterung, Schemas werden nachkompiliert.
schema = (b'<schemalist><schema id="org.test.x" path="/org/test/x/">'
          b'<key name="a" type="b"><default>true</default></key>'
          b'</schema></schemalist>')
r = installer.install(zip_aus("ext.zip", {
    "metadata.json": json.dumps({"uuid": "demo@test", "name": "Demo",
                                 "shell-version": ["45"]}).encode(),
    "extension.js": b"", "schemas/org.test.x.gschema.xml": schema}))
assert r[0].startswith("Extension: Demo"), r
ext = os.path.join(installer.EXTENSIONS_DIR, "demo@test")
assert os.path.isfile(os.path.join(ext, "schemas", "gschemas.compiled"))
assert "metadata" in fehler(zip_aus("ext-kaputt.zip", {
    "metadata.json": b'{"uuid": "../raus"}', "extension.js": b""}))

# Schrift (Archiv in eigenen Unterordner) und Einzelbild.
assert installer.install(zip_aus("Schrift.zip", {"a/Neu.ttf": b"x"})) == [
    "Font: 1 file"]
assert os.path.isfile(os.path.join(installer.FONTS_DIR, "Schrift", "Neu.ttf"))
einzel = os.path.join(QUELLE, "wand.png")
bild(einzel, 4, 4)
assert installer.install(einzel) == ["Background: wand.png"]

# Wallpaper-Paket: große Bilder rein, kleine Vorschau nicht, Namenskollision
# nummeriert statt überschrieben.
gross = bild(os.path.join(QUELLE, "g.png"), 1920, 1080, 0xff0000ff)
anders = bild(os.path.join(QUELLE, "h.png"), 1920, 1080, 0x00ff00ff)
klein = bild(os.path.join(QUELLE, "k.png"), 200, 100)
r = installer.install(zip_aus("walls.zip", {"w/wand.png": gross,
                                            "w/zwei.png": anders,
                                            "w/preview.png": klein}))
assert r == ["Backgrounds: 2 images"], r
namen = sorted(os.listdir(backgrounds.USER_DIR))
assert namen == ["wand-2.png", "wand.png", "zwei.png"], namen

# Die Grenzen gelten für die Summe aller inneren Archive, nicht je Archiv.
innere = {"v%d.tar.gz" % i: open(tar_aus("v%d.tar.gz" % i, {
    "V%d/cursors/f%d" % (i, k): b"x" for k in range(40)}), "rb").read()
    for i in range(5)}
alt_max, installer.MAX_EINTRAEGE = installer.MAX_EINTRAEGE, 100
assert "too large" in fehler(zip_aus("viele.zip", innere))
installer.MAX_EINTRAEGE = alt_max

# .dmlook: Designs atomar ersetzt (kein Mischstand), hicolor tabu, Bild dabei.
from src.core import looksbundle  # noqa: E402
datei(os.path.join(installer.THEMES_DIR, "Mein-Design", "gtk-4.0", "gtk.css"),
      b"/* alt */")
look = zip_aus("mein.dmlook", {
    "manifest.json": json.dumps({"format": looksbundle.FORMAT,
                                 "einstellungen": {}}).encode(),
    "themes/Mein-Design/gtk-3.0/gtk.css": b"/* neu */",
    "icons/hicolor/index.theme": ICON_INDEX,
    "backgrounds/look.png": gross})
einstellungen, wallpaper = looksbundle.entpacke(look)
mein = os.path.join(installer.THEMES_DIR, "Mein-Design")
assert os.listdir(mein) == ["gtk-3.0"], os.listdir(mein)
assert not os.path.exists(os.path.join(installer.ICONS_DIR, "hicolor"))
assert os.path.basename(wallpaper) == "look.png" and einstellungen == {}
assert looksbundle.entpacke(zip_aus("fremd.dmlook", {"x": b"y"})) is None

# Abgelehnt mit Begründung.
assert "unsafe" in fehler(zip_aus("boese.zip", {"../../raus.txt": b"x"}))
assert not os.path.exists(os.path.join(HOME, "raus.txt"))
assert "system theme" in fehler(zip_aus("hicolor.zip", {
    "hicolor/index.theme": ICON_INDEX}))
assert "source code" in fehler(zip_aus("quelle.zip", {
    "Orchis/src/gtk-3.0/_common.scss": b"", "Orchis/src/gtk-3.0/x": b""}))
assert "GDM" in fehler(zip_aus("gdm.zip", {"gnome-shell-theme.gresource": b"x"}))
assert "Plymouth" in fehler(zip_aus("ply.zip", {"t/t.plymouth": b"x"}))
assert "GRUB" in fehler(zip_aus("grub.zip", {"g/theme.txt": b"+ boot_menu {}"}))
assert "Plank" in fehler(zip_aus("plank.zip", {"p/dock.theme": b"x"}))
assert "Windows" in fehler(zip_aus("win.zip", {"Win/arrow.cur": b"x"}))
datei(os.path.join(QUELLE, "x.7z"))
assert "7z" in fehler(os.path.join(QUELLE, "x.7z"))
datei(os.path.join(QUELLE, "kaputt.jpg"), b"kein bild")
assert "image" in fehler(os.path.join(QUELLE, "kaputt.jpg"))
assert "Nothing installable" in fehler(zip_aus("leer.zip", {"readme.txt": b"x"}))

shutil.rmtree(HOME)
shutil.rmtree(QUELLE)
print("installer ok")
