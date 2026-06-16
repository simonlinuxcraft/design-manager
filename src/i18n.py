"""Zentrale gettext-Anbindung.

Wird beim ersten Import initialisiert. Jedes Modul holt sich `_` (und bei Bedarf
`ngettext`) hierüber. Damit Texte in Modul-Konstanten korrekt landen, muss dieses
Modul vor allen anderen src-Modulen importiert werden (siehe main.py).
"""

import gettext
import locale
import os

DOMAIN = "design-manager"

# Aus dem Quellbaum gestartet: kompilierte .mo unter build/locale/. Installiert:
# der Systempfad, in den build-deb.sh die .mo legt.
_dev = os.path.join(os.path.dirname(os.path.dirname(__file__)), "build", "locale")
_localedir = _dev if os.path.isdir(_dev) else "/usr/share/locale"

# Locale-Setup darf nie crashen, auch wenn die Systemlocale nicht erzeugt ist.
try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    pass

# fallback=True: fehlt eine Übersetzung, erscheint die englische msgid.
_t = gettext.translation(DOMAIN, _localedir, fallback=True)
_ = _t.gettext
ngettext = _t.ngettext
