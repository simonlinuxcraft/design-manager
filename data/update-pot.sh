#!/bin/sh
# Extracts translatable strings into po/design-manager.pot and merges the
# update into every existing po/<lang>.po. Run after changing UI strings.
set -e

PROJEKT="$(cd "$(dirname "$0")/.." && pwd)"
PO="$PROJEKT/po"
POT="$PO/design-manager.pot"

mkdir -p "$PO"

# Collect all source files relative to the project root, so the #: references
# in the .pot/.po files never contain the local checkout path. Sorted for a
# stable order across machines.
cd "$PROJEKT"
find main.py src -name '*.py' | LC_ALL=C sort \
    | xgettext --files-from=- --from-code=UTF-8 \
        --language=Python \
        --keyword=_ --keyword=ngettext:1,2 \
        --package-name="Design Manager" \
        --copyright-holder="simonlinuxcraft" \
        --msgid-bugs-address="https://github.com/simonlinuxcraft" \
        -o "$POT"

echo "wrote $POT"

# Merge into existing translations so new strings appear as untranslated.
for po in "$PO"/*.po; do
    [ -e "$po" ] || continue
    msgmerge --update --backup=none "$po" "$POT"
    echo "merged $(basename "$po")"
done
