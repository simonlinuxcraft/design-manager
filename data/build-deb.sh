#!/usr/bin/env bash
# Builds a .deb of Design Manager. Pure-Python GTK4/libadwaita app, so the whole
# tree goes under /usr/lib/design-manager and a small launcher lands in
# /usr/bin. Run as a normal user; fakeroot gives the packaged files root:root
# ownership (important: gdm-background.sh must NOT be user-writable, it is run
# via pkexec as root).
set -euo pipefail

APP_ID="io.github.simonlinuxcraft.DesignManager"
PKG="design-manager"

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJEKT="$(dirname "$HIER")"

# Version aus der einzigen Quelle (src/window.py) ziehen, kein zweiter Pflegeort.
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$PROJEKT/src/window.py")"
if [ -z "$VERSION" ]; then
    echo "Konnte APP_VERSION nicht aus src/window.py lesen." >&2
    exit 1
fi

ARCH="all"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

LIBDIR="$STAGE/usr/lib/$PKG"
mkdir -p "$LIBDIR" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" \
         "$STAGE/DEBIAN"

# 1. App-Code: main.py, src/, die zur Laufzeit gebrauchten data-Teile und das
#    Logo (About-Dialog/Seitenleiste laden es relativ zur Projektwurzel).
cp "$PROJEKT/main.py" "$LIBDIR/"
cp -r "$PROJEKT/src" "$LIBDIR/"
mkdir -p "$LIBDIR/data/looks"
cp "$PROJEKT"/data/looks/*.json "$LIBDIR/data/looks/"
cp "$PROJEKT/data/gdm-background.sh" "$LIBDIR/data/"
cp "$PROJEKT/design-manager-transparent-1024.png" "$LIBDIR/"

# Byte-Compiled-Reste raus, sie gehören nicht ins Paket.
find "$LIBDIR" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$LIBDIR" -name '*.pyc' -delete

# 2. Launcher in den PATH. Die .desktop-Datei ruft "design-manager".
cat > "$STAGE/usr/bin/$PKG" <<EOF
#!/bin/sh
exec python3 /usr/lib/$PKG/main.py "\$@"
EOF
chmod 755 "$STAGE/usr/bin/$PKG"

# 3. .desktop unverändert übernehmen (Exec=design-manager passt schon).
cp "$PROJEKT/data/$APP_ID.desktop" "$STAGE/usr/share/applications/"

# 4. Icons aus dem 1024er-Master skalieren.
MASTER="$PROJEKT/design-manager-transparent-1024.png"
for N in 48 64 128 256 512; do
    ZIEL="$STAGE/usr/share/icons/hicolor/${N}x${N}/apps"
    mkdir -p "$ZIEL"
    convert "$MASTER" -resize "${N}x${N}" "$ZIEL/$APP_ID.png"
done

# 5. Steuerdatei.
INSTALLED_KB="$(du -sk "$STAGE/usr" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Architecture: $ARCH
Maintainer: simonlinuxcraft <245174420+simonlinuxcraft@users.noreply.github.com>
Installed-Size: $INSTALLED_KB
Depends: python3, python3-gi, python3-gi-cairo, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-gdkpixbuf-2.0, gir1.2-pango-1.0, gsettings-desktop-schemas
Recommends: pkexec | policykit-1, libglib2.0-bin, libglib2.0-dev-bin, fontconfig, webp-pixbuf-loader
Suggests: variety
Section: x11
Priority: optional
Homepage: https://github.com/simonlinuxcraft/design-manager
Description: GNOME desktop appearance manager
 Design Manager adjusts the GNOME look from one place: GTK and shell themes,
 icons, cursor, fonts, accent colour, wallpaper, lock screen and the GDM login
 background. System changes are additive and reversible, with restore points
 and a crash-safe login-screen path.
EOF

# 6. Wartungsskripte: Icon-Cache und Desktop-DB aktualisieren.
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v gtk4-update-icon-cache >/dev/null 2>&1; then
    gtk4-update-icon-cache -f -t /usr/share/icons/hicolor || true
elif command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
EOF
cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v gtk4-update-icon-cache >/dev/null 2>&1; then
    gtk4-update-icon-cache -f -t /usr/share/icons/hicolor || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
EOF
# prerm: on real removal, undo any active GDM login-screen override before the
# package files vanish. The runtime state (gresource, guard unit/helper,
# update-alternatives pin) lives outside the package, so without this it would
# survive uninstall and freeze the greeter on a snapshot with no way back from
# the UI. Skip on upgrade. prerm already runs as root, so no pkexec. Best-effort:
# a failed reset must never block removal.
cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ]; then
    for h in /usr/local/lib/design-manager/gdm-helper.sh \
             /usr/lib/design-manager/data/gdm-background.sh; do
        if [ -x "$h" ]; then
            "$h" reset || true
            break
        fi
    done
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm" "$STAGE/DEBIAN/prerm"

# 7. Rechte: alles root-lesbar, ausführbar nur Skripte/Helfer. gdm-background.sh
#    muss root-owned und nicht nutzer-schreibbar sein (pkexec-Helfer).
find "$STAGE/usr" -type d -exec chmod 755 {} +
find "$STAGE/usr" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/usr/bin/$PKG"
chmod 755 "$LIBDIR/data/gdm-background.sh"

OUT="$PROJEKT/${PKG}_${VERSION}_${ARCH}.deb"
fakeroot dpkg-deb --build --root-owner-group "$STAGE" "$OUT"

echo "Gebaut: $OUT"
dpkg-deb --info "$OUT" | sed 's/^/  /'
