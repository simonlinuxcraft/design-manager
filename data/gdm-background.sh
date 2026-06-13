#!/bin/bash
#
# GDM-Anmeldebildschirm-Hintergrund setzen oder zuruecksetzen.
#
# Sicherer Weg: die Original-Yaru-gresource wird NIE angefasst. Stattdessen
# bauen wir eine eigene gresource (Yaru-Inhalt plus eingebettetes Bild und eine
# #lockDialogGroup-Regel) und haengen sie ueber update-alternatives als zweite
# Alternative ein. Zuruecksetzen entfernt nur unsere Alternative; die Weiche
# faellt von selbst auf das Original zurueck.
#
# Aussperr-Schutz: ein systemd-Guard laeuft vor dem Display-Manager. Bleibt eine
# frisch gesetzte gresource nach zwei Boots unbestaetigt (Greeter zeigte sie nie
# erfolgreich, weil er crasht), stellt der Guard automatisch das Original wieder
# her. Der Nutzer haengt damit nie im Recovery fest.
#
# Unterkommandos:
#   build <bild> <out>   als Nutzer: baut die gresource, gibt RESOURCE=... aus
#   install <gresource>  als root:   haengt sie ein, schaltet den Guard scharf
#   confirm              als root:   Theme bestaetigt, Guard aus
#   reset                als root:   Original wieder, Guard weg
#   guard                als root:   vom systemd-Service, Auto-Rollback-Logik
#   status               liest den Zustand (kein root noetig)
#
# SICHERHEIT: In einer echten Installation muss dieses Skript root gehoeren und
# unter /usr/lib liegen, sonst koennte es manipuliert und per pkexec als root
# ausgefuehrt werden. Im Entwicklungsbetrieb laeuft es aus dem Projektordner.

set -euo pipefail

ALT_NAME="gdm-theme.gresource"
ALT_LINK="/usr/share/gnome-shell/gdm-theme.gresource"
ALT_PRIO=99

STATE_DIR="/var/lib/design-manager"
OUR="$STATE_DIR/design-manager-gdm.gresource"
STATE="$STATE_DIR/gdm.state"

GUARD_DIR="/usr/local/lib/design-manager"
GUARD_HELPER="$GUARD_DIR/gdm-helper.sh"
GUARD_UNIT="/etc/systemd/system/design-manager-gdm-guard.service"
GUARD_NAME="design-manager-gdm-guard.service"

# Quelle der Original-Ressourcen. Nie unser eigenes Ziel (sonst baut ein zweites
# apply auf der schon gepatchten Datei auf und verschachtelt Bild plus CSS bei
# jedem Mal). Da OUR mit hoher Prioritaet eingehaengt ist, waere es sonst sogar
# der 'Best'-Eintrag, darum OUR explizit ausschliessen.
quelle_gresource() {
    local val
    val="$(readlink -f "$ALT_LINK" 2>/dev/null || true)"
    if [ -n "$val" ] && [ "$val" != "$OUR" ]; then
        echo "$val"
        return
    fi
    # Zeigt die Weiche auf OUR (oder ist leer): hoechstpriore Alternative != OUR.
    update-alternatives --query "$ALT_NAME" 2>/dev/null | awk -v our="$OUR" '
        /^Alternative: /{a=$2}
        /^Priority: /{p=$2+0; if (a!=our && p>best){best=p; sel=a}}
        END{if (sel) print sel}'
}

# --- build (als Nutzer) -----------------------------------------------------

build() {
    local bild="$1" out="$2"
    [ -f "$bild" ] || { echo "Bild nicht gefunden: $bild" >&2; exit 2; }

    local src
    src="$(quelle_gresource)"
    [ -n "$src" ] && [ -f "$src" ] || { echo "Keine GDM-gresource gefunden" >&2; exit 2; }

    local work
    work="$(mktemp -d)"
    trap 'rm -rf "${work:-}"' EXIT

    # Laengster gemeinsamer Verzeichnis-Prefix ALLER Eintraege. dirname des
    # ersten Eintrags reicht nicht: Yaru legt die meisten Assets (checkbox-*.svg,
    # toggle-*.svg, calendar-*.svg ...) eine Ebene ueber dem .../Yaru/-Pfad ab.
    # Ein zu tiefer Prefix wuerde sie unter einen falschen Pfad verschachteln und
    # den Greeter um genau diese Assets bringen.
    local res prefix
    prefix="$(dirname "$(gresource list "$src" | head -1)")"
    while IFS= read -r res; do
        while [ "$prefix" != "/" ] && [ "${res#"$prefix"/}" = "$res" ]; do
            prefix="$(dirname "$prefix")"
        done
    done < <(gresource list "$src")

    local srcroot="$work$prefix"
    mkdir -p "$srcroot"

    local rel
    while IFS= read -r res; do
        rel="${res#"$prefix"/}"
        mkdir -p "$srcroot/$(dirname "$rel")"
        gresource extract "$src" "$res" > "$srcroot/$rel"
    done < <(gresource list "$src")

    # Bild einbetten.
    local ext bildname
    ext="${bild##*.}"
    bildname="design-manager-gdm-bg.$ext"
    cp -f "$bild" "$srcroot/$bildname"

    # Konservative Hintergrundregel an jede Shell-CSS anhaengen. background-color
    # und background-image getrennt (kein url()-Shorthand), background-size: cover
    # versteht St. Genau diese Form ist erprobt; ein Shorthand kann den Greeter
    # crashen. Die Shell-CSS liegen je nach Theme tiefer (bei Yaru unter Yaru/),
    # darum rekursiv suchen statt nur direkt unter srcroot.
    local css
    while IFS= read -r css; do
        cat >> "$css" <<EOF

/* === design-manager-gdm START === */
#lockDialogGroup {
  background-color: #000000;
  background-image: url('resource://$prefix/$bildname');
  background-size: cover;
  background-repeat: no-repeat;
  background-position: center;
}
/* === design-manager-gdm END === */
EOF
    done < <(find "$srcroot" -type f -name 'gnome-shell*.css')

    local xml="$work/dm.gresource.xml"
    {
        echo '<?xml version="1.0" encoding="UTF-8"?>'
        echo '<gresources>'
        echo "  <gresource prefix=\"$prefix\">"
        ( cd "$srcroot" && find . -type f | sed 's|^\./||' | sort ) \
            | while IFS= read -r f; do echo "    <file>$f</file>"; done
        echo '  </gresource>'
        echo '</gresources>'
    } > "$xml"

    glib-compile-resources --sourcedir="$srcroot" --target="$out" "$xml"
    gresource list "$out" >/dev/null

    # Harte Garantie: keine einzige Original-Ressource darf fehlen oder unter
    # einem anderen Pfad gelandet sein, sonst zeigt der Greeter kaputte/fehlende
    # Login-Assets. Lieber hier abbrechen als ein defektes Theme ausliefern.
    local fehlend
    fehlend="$(comm -23 <(gresource list "$src" | sort) <(gresource list "$out" | sort))"
    if [ -n "$fehlend" ]; then
        echo "Original-Ressourcen fehlen in der neuen gresource:" >&2
        echo "$fehlend" >&2
        exit 3
    fi

    # Python validiert die Datei anhand dieses Pfads weiter.
    echo "RESOURCE=$prefix/$bildname"
}

# --- install (als root) -----------------------------------------------------

install_theme() {
    local gres="$1"
    [ -f "$gres" ] || { echo "gresource nicht gefunden: $gres" >&2; exit 2; }
    gresource list "$gres" >/dev/null || { echo "Keine gueltige gresource" >&2; exit 2; }

    mkdir -p "$STATE_DIR" "$GUARD_DIR"
    chmod 755 "$STATE_DIR" "$GUARD_DIR"
    cp -f "$gres" "$OUR"
    chmod 644 "$OUR"

    # Guard-Helfer an einen stabilen Ort auf dem Root-Dateisystem legen, damit
    # der systemd-Service ihn beim fruehen Boot sicher findet (der Projektordner
    # kann auf einer spaet gemounteten Partition liegen).
    cp -f "$(readlink -f "$0")" "$GUARD_HELPER"
    chmod 755 "$GUARD_HELPER"

    cat > "$GUARD_UNIT" <<EOF
[Unit]
Description=Design Manager GDM theme safety rollback
Before=display-manager.service
ConditionPathExists=$STATE

[Service]
Type=oneshot
ExecStart=$GUARD_HELPER guard

[Install]
WantedBy=graphical.target
EOF
    systemctl daemon-reload
    systemctl enable "$GUARD_NAME" >/dev/null 2>&1 || true

    # STATE MUSS existieren, bevor das Theme aktiv wird: der Guard laeuft nur bei
    # vorhandenem STATE (ConditionPathExists). Wuerde die Weiche zuerst gesetzt
    # und der Prozess vor dem STATE-Write sterben, bliebe ein evtl. defektes Theme
    # ohne Auto-Rollback aktiv. Reihenfolge darum: erst STATE, dann aktivieren.
    printf 'boots=0\nconfirmed=0\n' > "$STATE"
    chmod 644 "$STATE"

    update-alternatives --install "$ALT_LINK" "$ALT_NAME" "$OUR" "$ALT_PRIO"
    update-alternatives --set "$ALT_NAME" "$OUR"
    echo "installiert"
}

# --- confirm / reset / guard ------------------------------------------------

confirm() {
    [ -f "$STATE" ] || { echo "nichts zu bestaetigen"; return 0; }
    printf 'boots=0\nconfirmed=1\n' > "$STATE"
    chmod 644 "$STATE"
    systemctl disable "$GUARD_NAME" >/dev/null 2>&1 || true
    echo "bestaetigt"
}

rollback() {
    update-alternatives --remove "$ALT_NAME" "$OUR" >/dev/null 2>&1 || true
    systemctl disable "$GUARD_NAME" >/dev/null 2>&1 || true
    rm -f "$STATE" "$OUR" "$GUARD_UNIT" "$GUARD_HELPER"
    systemctl daemon-reload >/dev/null 2>&1 || true
}

reset_theme() {
    rollback
    echo "zurueckgesetzt"
}

read_state() {
    local key="$1" line
    [ -f "$STATE" ] || { echo ""; return; }
    line="$(grep -E "^$key=" "$STATE" | head -1 || true)"
    echo "${line#*=}"
}

guard() {
    [ -f "$STATE" ] || exit 0
    local confirmed boots
    confirmed="$(read_state confirmed)"
    [ "$confirmed" = "1" ] && exit 0

    boots="$(read_state boots)"
    case "$boots" in ''|*[!0-9]*) boots=0 ;; esac
    boots=$((boots + 1))

    if [ "$boots" -ge 2 ]; then
        # Zweiter Boot ohne Bestaetigung: der Greeter hat es nie zu einem
        # bestaetigten Login geschafft. Zurueck auf das Original.
        rollback
    else
        # Erster Boot mit dem neuen Theme: stehen lassen, damit es sich zeigen
        # und der Nutzer sich einloggen plus bestaetigen kann.
        printf 'boots=%s\nconfirmed=0\n' "$boots" > "$STATE"
        chmod 644 "$STATE"
    fi
}

status() {
    if [ -f "$OUR" ] && [ -f "$STATE" ]; then
        if [ "$(read_state confirmed)" = "1" ]; then echo "confirmed"; else echo "pending"; fi
    else
        echo "inaktiv"
    fi
}

case "${1:-}" in
    build)   build "${2:-}" "${3:-}" ;;
    install) install_theme "${2:-}" ;;
    confirm) confirm ;;
    reset)   reset_theme ;;
    guard)   guard ;;
    status)  status ;;
    *) echo "Aufruf: $0 {build <bild> <out>|install <gresource>|confirm|reset|guard|status}" >&2; exit 1 ;;
esac
