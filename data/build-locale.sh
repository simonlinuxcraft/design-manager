#!/bin/sh
# Compiles po/<lang>.po into build/locale/<lang>/LC_MESSAGES/design-manager.mo
# so the app can be tested from the source tree (LANGUAGE=xx python3 main.py).
set -e

PROJEKT="$(cd "$(dirname "$0")/.." && pwd)"
PO="$PROJEKT/po"
OUT="$PROJEKT/build/locale"

for po in "$PO"/*.po; do
    [ -e "$po" ] || continue
    lang=$(basename "$po" .po)
    dir="$OUT/$lang/LC_MESSAGES"
    mkdir -p "$dir"
    msgfmt "$po" -o "$dir/design-manager.mo"
    echo "built $lang"
done
