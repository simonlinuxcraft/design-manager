"""Updater: Versionsvergleich und der root-Schritt (mit falschem apt-get).

    python3 tests/test_updater.py
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import updater  # noqa: E402


def test_version():
    v = updater._version_tupel
    assert v("v0.1.5-2") == (0, 1, 5)  # früher 0.1.52, schien neuer als 0.1.6
    assert v("0.2.0-rc1") == (0, 2, 0)
    assert v("v0.1.10") > v("0.1.9")
    assert v("") == (0,) and v("latest") == (0,)


def test_root_schritt():
    """Der root-Teil installiert eine eigene Kopie und nur bei passendem sha256."""
    t = tempfile.mkdtemp(prefix="dm-test-update-")
    deb = os.path.join(t, "u.deb")
    with open(deb, "wb") as f:
        f.write(b"paket")
    sha = hashlib.sha256(b"paket").hexdigest()
    os.makedirs(os.path.join(t, "bin"))
    protokoll = os.path.join(t, "apt.log")
    apt = os.path.join(t, "bin", "apt-get")
    with open(apt, "w") as f:
        f.write('#!/bin/sh\necho "$3" > %s\ncat "$3" >> %s\n' % (protokoll, protokoll))
    os.chmod(apt, 0o755)
    env = dict(os.environ, PATH=os.path.join(t, "bin") + ":" + os.environ["PATH"])

    def lauf(pruefsumme):
        return subprocess.run(["/bin/sh", "-c", updater._ALS_ROOT, "sh", deb, pruefsumme],
                              env=env, capture_output=True).returncode

    assert lauf("0" * 64) != 0 and not os.path.exists(protokoll)
    assert lauf(sha) == 0
    with open(protokoll) as f:
        kopie, inhalt = f.read().splitlines()
    assert kopie != deb and kopie.endswith("/update.deb") and inhalt == "paket"
    assert not os.path.exists(os.path.dirname(kopie))  # Kopie wieder weg
    shutil.rmtree(t)


if __name__ == "__main__":
    test_version()
    test_root_schritt()
    print("updater ok")
