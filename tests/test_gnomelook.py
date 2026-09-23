"""gnome-look-Herkunft und Update-Erkennung, ohne Netz, im Wegwerf-HOME.

    LANGUAGE=en python3 tests/test_gnomelook.py
"""

import os
import shutil
import sys
import tarfile
import tempfile
import time
import zipfile

HOME = tempfile.mkdtemp(prefix="dm-test-home-")
os.environ["HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi  # noqa: E402
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from src.core import gnomelook, installer  # noqa: E402


def datei(name, md5=""):
    return {"name": name, "link": "https://x/" + name, "md5": md5, "version": ""}


assert gnomelook.content_id("https://www.gnome-look.org/p/1013030") == "1013030"
assert gnomelook.content_id("https://www.pling.com/s/Gnome/p/123/") == "123"
assert gnomelook.content_id("https://store.kde.org/p/77#files-panel") == "77"
assert gnomelook.content_id("https://evil.org/p/1") is None
assert gnomelook.content_id("https://gnome-look.org.evil.org/p/1") is None

e = {"datei": "01-Flat-Remix-Light-20250926.tar.xz", "md5": "a"}
aktuell = [datei("01-Flat-Remix-Light-20251119.tar.xz", "b"),
           datei("02-Flat-Remix-Light-fullPanel-20251119.tar.xz", "c")]
assert gnomelook.nachfolger(e, aktuell) == aktuell[:1]
assert gnomelook.nachfolger(e, [datei(e["datei"], "a")]) == []
assert gnomelook.nachfolger(e, [datei(e["datei"], "z")])[0]["md5"] == "z"
assert gnomelook.nachfolger(e, [datei(e["datei"], "")]) == []
assert gnomelook.nachfolger({"datei": "Nordic-v2.1.tar.xz"},
                            [datei("Nordic-v2.2.zip")])
assert len(gnomelook.nachfolger({"datei": "T-40.tar.xz"},
                                [datei("T-42.tar.xz"), datei("T-44.tar.xz")])) == 2
assert gnomelook.nachfolger({"datei": "Weg.tar.xz"}, [datei("Anders.zip")]) is None

# Merken, Ersetzen beim Update, Update nur für noch Installiertes.
fund = installer.Fund("theme", "Flat-Remix-Light", "/x", ["gtk"])
ziel = installer.ziel_pfade(fund)[0]
assert ziel == os.path.join(HOME, ".local/share/themes/Flat-Remix-Light")
paket = installer.Paket([fund])
paket.quelle = {"id": "1", "titel": "T", "datei": e["datei"], "md5": "a"}
gnomelook.merke(paket, [fund])
assert gnomelook.zustand([ziel])[0] == gnomelook.AKTUELL
gnomelook.dateien = lambda cid: ("T", aktuell)
assert gnomelook.updates() == ([], None)  # Ordner fehlt noch
os.makedirs(ziel)
[(eintrag, neu)], _netz = gnomelook.updates()
assert eintrag["pfade"] == [ziel] and neu == aktuell[:1]
assert gnomelook.zustand_fuer_name("Flat-Remix-Light")[0] == gnomelook.UPDATE

# Abgebrochenes Update: zurück auf "Update verfügbar".
paket.eintrag = eintrag
gnomelook.setze([ziel], gnomelook.LAEUFT)
gnomelook.merke(paket, [])
assert gnomelook.zustand([ziel])[0] == gnomelook.UPDATE

paket.quelle = {"id": "1", "titel": "T", "datei": aktuell[0]["name"], "md5": "b"}
gnomelook.merke(paket, [fund])
assert len(gnomelook._lade_quellen()) == 1
assert gnomelook.updates() == ([], None)
assert gnomelook.zustand([ziel])[0] == gnomelook.AKTUELL

# Datei verschwunden: Problem statt still "aktuell".
gnomelook.dateien = lambda cid: ("T", [datei("Etwas-anderes.zip")])
gnomelook.updates()
assert gnomelook.zustand([ziel])[0] == gnomelook.PROBLEM

# Ohne Netz bleibt der Zustand, wie er ist.
def offline(cid):
    raise gnomelook._NichtErreichbar("offline")
gnomelook.dateien = offline
assert gnomelook.updates() == ([], "offline")
assert gnomelook.zustand([ziel])[0] == gnomelook.PROBLEM

# Lokale Datei über denselben Ordner: nicht mehr von gnome-look.
gnomelook.merke(installer.Paket([fund]), [fund])
assert gnomelook._lade_quellen() == [] and gnomelook.zustand([ziel]) is None

# --- Vorhandene Designs zuordnen ---

assert gnomelook._kern("01-Tela.tar.xz") == gnomelook._kern("Tela") == "tela"
assert gnomelook._kern("volantes-cursors.tar.gz") == \
    gnomelook._kern("volantes_cursors")
assert gnomelook._kern("05-Flat-Remix-GTK-Red-Dark_20201129.tar.xz") == \
    gnomelook._kern("Flat-Remix-GTK-Red-Dark")
assert gnomelook._kern("kora-2-0-5.tar.gz") == "kora"
assert gnomelook._suchtexte("Juno-ocean-v40") == ["Juno ocean", "Juno"]
assert gnomelook._suchtexte("Tela") == ["Tela"]


def design(pfad, css, zeit):
    os.makedirs(os.path.join(pfad, "gtk-3.0"), exist_ok=True)
    css_pfad = os.path.join(pfad, "gtk-3.0", "gtk.css")
    with open(css_pfad, "w") as f:
        f.write(css)
    os.utime(css_pfad, (zeit, zeit))


QUELLE = tempfile.mkdtemp(prefix="dm-test-quelle-")
design(os.path.join(QUELLE, "Gleich"), "a", 1_600_000_000)
design(os.path.join(QUELLE, "Alt"), "neu", 1_600_000_000)
design(os.path.join(QUELLE, "Selbst"), "gnome-look", 1_600_000_000)
os.symlink("gtk-3.0", os.path.join(QUELLE, "Selbst", "gtk-4.0"))  # Zeit: jetzt
archiv = os.path.join(QUELLE, "01-Gleich-2025.tar.gz")
with tarfile.open(archiv, "w:gz") as t:
    for n in ("Gleich", "Alt", "Selbst"):
        t.add(os.path.join(QUELLE, n), n)
themes = installer.THEMES_DIR
design(os.path.join(themes, "Gleich"), "a", 1_700_000_000)
design(os.path.join(themes, "Alt"), "alt", 1_500_000_000)
design(os.path.join(themes, "Selbst"), "selbst geaendert", 1_700_000_000)
design(os.path.join(themes, "Unbekannt"), "x", 1_700_000_000)

paket_datei = datei("01-Gleich-2025.tar.gz", "m")
gnomelook._suche = lambda text: [
    ("7", "Icons gleichen Namens", "icon", [datei("Gleich.tar.xz")]),
    ("8", "Paket", "gtk", [paket_datei])] if text == "Gleich" else []
gnomelook._lade = lambda d, ziel: shutil.copy(archiv, ziel)
[kandidat], netz = gnomelook.kandidaten()
assert netz is None and kandidat["id"] == "8"  # Symbole passen nicht zu GTK
assert kandidat["pfade"] == [os.path.join(themes, "Gleich")]

verknuepft, anders = gnomelook.verknuepfe(kandidat)
assert verknuepft == [os.path.join(themes, n) for n in ("Alt", "Gleich")]
assert anders == [os.path.join(themes, "Selbst")]
[eintrag] = gnomelook._lade_quellen()
assert eintrag["veraltet"] and eintrag["md5"] == "m"
assert gnomelook._lade_uebersprungen() == {os.path.join(themes, "Selbst")}
assert gnomelook.kandidaten() == ([], None)
gnomelook.dateien = lambda cid: ("Paket", [paket_datei])
[(eintrag, neu)], _netz = gnomelook.updates()
assert neu == [paket_datei]
assert gnomelook.zustand_fuer_name("Gleich")[0] == gnomelook.UPDATE

# Zip-Archive behalten ihre Dateizeiten wie tar.
zip_pfad = os.path.join(QUELLE, "z.zip")
with zipfile.ZipFile(zip_pfad, "w") as z:
    z.writestr(zipfile.ZipInfo("Z/gtk-3.0/gtk.css", (2020, 5, 1, 12, 0, 0)),
               "x")
entpackt = tempfile.mkdtemp(dir=QUELLE)
installer._entpacke(zip_pfad, entpackt)
assert time.localtime(os.path.getmtime(os.path.join(
    entpackt, "Z/gtk-3.0/gtk.css")))[:3] == (2020, 5, 1)

print("ok")
