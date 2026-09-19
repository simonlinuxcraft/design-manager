"""gnome-look-Herkunft und Update-Erkennung, ohne Netz, im Wegwerf-HOME.

    LANGUAGE=en python3 tests/test_gnomelook.py
"""

import os
import sys
import tempfile

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

print("ok")
