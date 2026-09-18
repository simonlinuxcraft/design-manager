"""Web-CSS-Prüfung: echte Deklarationen ja, Selektoren nein.

    python3 tests/test_theme_check.py
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import theme_check  # noqa: E402

ordner = tempfile.mkdtemp()
os.makedirs(os.path.join(ordner, "gtk-4.0"))
with open(os.path.join(ordner, "gtk-4.0", "gtk.css"), "w") as f:
    f.write(".a{backdrop-filter:blur(2px)} .b { color: red; width : 3px }\n"
            "list.content:not(.x) > row.position:hover { min-width: 2px; }\n"
            "/* display: none; */")
assert theme_check.fremdes_css(ordner) == ["backdrop-filter", "width"], \
    theme_check.fremdes_css(ordner)
shutil.rmtree(ordner)
print("theme_check ok")
