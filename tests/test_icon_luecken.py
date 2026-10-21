"""Overlay für fehlende App-Icons in einem Wegwerf-HOME.

    python3 tests/test_icon_luecken.py
"""

import os
import shutil
import struct
import subprocess
import sys
import tempfile

PNG32 = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", 32, 32) + b"\x08\x06"


def datei(pfad, inhalt=b"<svg/>"):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "wb") as f:
        f.write(inhalt.encode() if isinstance(inhalt, str) else inhalt)


def theme(wurzel, inherits, ordner, icons):
    kopf = f"[Icon Theme]\nName=x\nInherits={inherits}\nDirectories={','.join(ordner)}\n"
    datei(os.path.join(wurzel, "index.theme"),
          kopf + "".join(f"\n[{o}]\nSize=48\nType=Scalable\n" for o in ordner))
    for icon in icons:
        datei(os.path.join(wurzel, icon), PNG32 if icon.endswith(".png") else b"<svg/>")


def starter(ordner, id_, name, icon, extra=""):
    datei(os.path.join(ordner, "applications", id_),
          f"[Desktop Entry]\nType=Application\nName={name}\nExec=true\nIcon={icon}\n{extra}")


def test_im_eigenen_prozess():
    # pytest sammelt alle Tests in einem Prozess, GLib und GIO haben ihre
    # Datenpfade dann schon festgelegt.
    subprocess.run([sys.executable, os.path.abspath(__file__)], check=True)


def main():
    T = tempfile.mkdtemp(prefix="dm-test-icons-")
    HOME = os.path.join(T, "home")
    LOKAL = os.path.join(HOME, ".local", "share")
    SYS = os.path.join(T, "sys")
    SNAPD = os.path.join(T, "snapd")
    os.environ.update(HOME=HOME, XDG_DATA_HOME=LOKAL,
                      XDG_DATA_DIRS=SYS + ":" + SNAPD,
                      XDG_CURRENT_DESKTOP="GNOME", LANGUAGE="C")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # erst nach dem HOME-Wechsel, themes legt seine Pfade beim Import fest
    from src.core import icon_luecken, themes

    theme(os.path.join(SYS, "icons", "Paket"), "Eltern", ["48x48/apps"], ["48x48/apps/im-paket.svg"])
    # Eltern liegt als verlinkter Ordner da, wie Papirus-Dark -> Papirus
    theme(os.path.join(SYS, "echt-eltern"), "", ["scalable/apps"], ["scalable/apps/in-eltern.svg"])
    os.symlink(os.path.join(SYS, "echt-eltern"), os.path.join(SYS, "icons", "Eltern"))
    theme(os.path.join(SYS, "icons", "hicolor"), "", ["48x48/apps"], ["48x48/apps/in-hicolor.png"])
    theme(os.path.join(SYS, "icons", "Vorher"), "", ["scalable/apps", "32x32/apps"],
          ["scalable/apps/nur-im-vorher.svg", "32x32/apps/nur-im-vorher.png"])
    theme(os.path.join(SYS, "icons", "Fremd"), "", ["scalable/apps"], [])
    theme(os.path.join(LOKAL, "icons", "Fremd-filled"), "Fremd", ["scalable/apps"], [])
    datei(os.path.join(SYS, "pixmaps", "in-pixmaps.png"), PNG32)

    for id_, name, icon, extra in [
            ("a.desktop", "A", "im-paket", ""),
            ("b.desktop", "B", "in-eltern", ""),
            ("c.desktop", "C", "in-hicolor", ""),
            ("d.desktop", "D", "in-pixmaps", ""),
            ("e.desktop", "E", "nur-im-vorher", ""),
            ("f.desktop", "F", "nirgends", ""),
            ("g.desktop", "G", os.path.join(T, "pfad.svg"), ""),
            ("h.desktop", "H", "versteckt", "NoDisplay=true\n"),
            ("i.desktop", "I", "nur-kde", "OnlyShowIn=KDE;\n"),
            # relativer Pfad statt Icon-Name: fände über Vorher eine Quelle und
            # würde beim Schreiben aus dem Overlay ausbrechen
            ("j.desktop", "J", "../../../raus", "")]:
        starter(SYS, id_, name, icon, extra)
    datei(os.path.join(SYS, "icons", "raus.svg"))
    # Lokale Kopie eines Snap-Starters mit Icon-Namen, das Original hat den Pfad.
    datei(os.path.join(T, "snap", "icon.png"), PNG32)
    starter(SNAPD, "foo_foo.desktop", "Foo", os.path.join(T, "snap", "icon.png"))
    starter(LOKAL, "foo_foo.desktop", "Foo", "foo-name")

    b = icon_luecken.bericht("Paket", "Vorher")
    assert b["quellen"] == {
        "nur-im-vorher": os.path.join(SYS, "icons", "Vorher", "scalable/apps", "nur-im-vorher.svg"),
        "foo-name": os.path.join(T, "snap", "icon.png")}, b["quellen"]
    assert (b["ergaenzt"], b["neu"], b["fehlt"], b["pfad"]) == ([], ["E", "Foo"], ["F"], ["G"]), b

    overlay = os.path.join(LOKAL, "icons", "Paket-filled")
    assert icon_luecken.ergaenze("Paket", "Vorher") == (
        "Paket-filled", (["E", "Foo"], ["F"], ["G"]))
    assert os.path.isfile(os.path.join(overlay, "scalable/apps/nur-im-vorher.svg"))
    assert os.path.isfile(os.path.join(overlay, "32x32/apps/foo-name.png"))
    with open(os.path.join(overlay, "index.theme")) as f:
        index = f.read()
    assert "Inherits=Paket,hicolor\n" in index and "[32x32/apps]\n" in index, index
    assert icon_luecken.basis("Paket-filled") == "Paket"
    assert icon_luecken.basis("Paket") == "Paket"
    assert icon_luecken.zustand("Paket-filled") == (["E", "Foo"], ["F"], ["G"])
    # Overlay liegt da, dconf nennt aber das Paket (Notausstieg): nichts ergänzt.
    assert icon_luecken.zustand("Paket") == ([], ["E", "F", "Foo"], ["G"])
    assert "Paket-filled" not in themes.list_icon_themes()
    assert "Fremd-filled" in themes.list_icon_themes()  # ohne Marker kein Overlay

    # Erneut anklicken: das Overlay ist jetzt das vorherige Theme und liefert sich selbst.
    assert icon_luecken.ergaenze("Paket", "Paket-filled")[0] == "Paket-filled"
    assert os.path.isfile(os.path.join(overlay, "scalable/apps/nur-im-vorher.svg"))
    assert not [n for n in os.listdir(os.path.join(LOKAL, "icons")) if n.startswith(".dm-")]

    # Ein fremdes Theme mit dem Overlay-Namen bleibt unangetastet.
    assert icon_luecken.ergaenze("Fremd")[0] == "Fremd"
    assert not os.path.exists(os.path.join(LOKAL, "icons", "Fremd-filled", "32x32"))
    assert icon_luecken.ergaenze("GibtsNicht") == ("GibtsNicht", ([], [], []))

    # Ein entferntes Paket nimmt sein Overlay mit, ein fremdes -filled bleibt.
    from src.core import uninstaller
    theme(os.path.join(LOKAL, "icons", "Lokal"), "", ["scalable/apps"], [])
    assert icon_luecken.ergaenze("Lokal", "Vorher")[0] == "Lokal-filled"
    assert uninstaller.deinstalliere("Lokal", "icon")
    assert not os.path.lexists(os.path.join(LOKAL, "icons", "Lokal"))
    assert not os.path.lexists(os.path.join(LOKAL, "icons", "Lokal-filled"))
    assert os.path.isdir(os.path.join(LOKAL, "icons", "Fremd-filled"))

    shutil.rmtree(T)
    print("icon_luecken ok")


if __name__ == "__main__":
    main()
