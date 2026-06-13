#!/usr/bin/env bash
# Installiert Icon und .desktop-Datei lokal (nur fuer den Nutzer, kein sudo),
# damit GNOME im Dock das DM-Logo zeigt. Reversibel ueber dev-uninstall.sh.
set -euo pipefail

APP_ID="io.github.simonlinuxcraft.DesignManager"

# Projektwurzel = der Ordner ueber diesem data/-Ordner.
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJEKT="$(dirname "$HIER")"

ICON_BASIS="$HOME/.local/share/icons/hicolor"
APP_DIR="$HOME/.local/share/applications"

# 1. Icons in den hicolor-Baum legen, je Groesse aus dem 1024er-Master skaliert.
MASTER="$PROJEKT/design-manager-transparent-1024.png"
for N in 48 64 128 256 512; do
    ZIEL_DIR="$ICON_BASIS/${N}x${N}/apps"
    mkdir -p "$ZIEL_DIR"
    if command -v convert >/dev/null; then
        convert "$MASTER" -resize "${N}x${N}" "$ZIEL_DIR/$APP_ID.png"
    else
        # Ohne ImageMagick wenigstens die Originaldatei ablegen.
        cp "$MASTER" "$ZIEL_DIR/$APP_ID.png"
    fi
done

# 2. .desktop installieren, dabei Exec auf den echten Dev-Start umbiegen.
mkdir -p "$APP_DIR"
sed "s|^Exec=.*|Exec=python3 \"$PROJEKT/main.py\"|" \
    "$HIER/$APP_ID.desktop" > "$APP_DIR/$APP_ID.desktop"

# 3. Caches aktualisieren, damit GNOME die neuen Dateien sofort sieht.
if command -v gtk4-update-icon-cache >/dev/null; then
    gtk4-update-icon-cache -f "$ICON_BASIS" || true
elif command -v gtk-update-icon-cache >/dev/null; then
    gtk-update-icon-cache -f "$ICON_BASIS" || true
fi
if command -v update-desktop-database >/dev/null; then
    update-desktop-database "$APP_DIR" || true
fi

echo "Installiert: $APP_ID (Icon + .desktop in ~/.local/share)"
