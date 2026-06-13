#!/usr/bin/env bash
# Entfernt die von dev-install.sh angelegten Dateien wieder.
set -euo pipefail

APP_ID="io.github.simonlinuxcraft.DesignManager"
ICON_BASIS="$HOME/.local/share/icons/hicolor"
APP_DIR="$HOME/.local/share/applications"

for N in 48 64 128 256 512; do
    rm -f "$ICON_BASIS/${N}x${N}/apps/$APP_ID.png"
done
rm -f "$APP_DIR/$APP_ID.desktop"

if command -v gtk4-update-icon-cache >/dev/null; then
    gtk4-update-icon-cache -f "$ICON_BASIS" || true
elif command -v gtk-update-icon-cache >/dev/null; then
    gtk-update-icon-cache -f "$ICON_BASIS" || true
fi
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "$APP_DIR" || true
fi

echo "Entfernt: $APP_ID (Icon + .desktop)"
