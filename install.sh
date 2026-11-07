#!/usr/bin/env bash
# Install VistaCam: the patched gspca_ov519 driver (DKMS) and the desktop app.
#
#   ./install.sh              driver + app
#   ./install.sh --driver     driver only (asks for sudo)
#   ./install.sh --app        app only (no sudo, installs for this user)
#   ./install.sh --system-qt  app only, using the distro's PyQt6 instead of
#                             downloading Qt (old CPUs, 32-bit, ARM)
#   ./install.sh --uninstall  remove both
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PKG=gspca-ov519-vistacam
VER=$(sed -n 's/^PACKAGE_VERSION="\(.*\)"/\1/p' "$HERE/driver/dkms.conf")
APPDIR="${XDG_DATA_HOME:-$HOME/.local/share}/vistacam"
BINDIR="$HOME/.local/bin"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

camera_in_use() {
    local dev
    for v in /sys/class/video4linux/video*; do
        [ -e "$v/device/../idVendor" ] || continue
        if [ "$(cat "$v/device/../idVendor"):$(cat "$v/device/../idProduct")" = "041e:4052" ]; then
            dev="/dev/$(basename "$v")"
            fuser "$dev" >/dev/null 2>&1 && return 0
        fi
    done
    return 1
}

install_driver() {
    command -v dkms >/dev/null || fail "dkms is missing. On Debian/Ubuntu: sudo apt install dkms"
    [ -d "/lib/modules/$(uname -r)/build" ] ||
        fail "kernel headers for $(uname -r) are missing. On Debian/Ubuntu: sudo apt install linux-headers-$(uname -r)"
    say "Installing driver $PKG $VER with DKMS"
    sudo dkms remove -m "$PKG" -v "$VER" --all >/dev/null 2>&1 || true
    sudo rm -rf "/usr/src/$PKG-$VER"
    sudo mkdir -p "/usr/src/$PKG-$VER"
    sudo cp "$HERE"/driver/{Makefile,dkms.conf,ov519.c,ov7670_creative.c,creative_tables.h,gspca.h,jpeg.h,w996Xcf.c} \
        "/usr/src/$PKG-$VER/"
    sudo dkms add -m "$PKG" -v "$VER"
    sudo dkms build -m "$PKG" -v "$VER"
    sudo dkms install -m "$PKG" -v "$VER" --force
    if lsmod | grep -q '^gspca_ov519'; then
        if camera_in_use; then
            say "The camera is in use; the new driver loads after you replug it or reboot."
        else
            sudo modprobe -r gspca_ov519 && sudo modprobe gspca_ov519
            say "Driver reloaded."
        fi
    fi
    if [ -e /sys/module/gspca_ov519/parameters/creative_tuning ]; then
        say "Patched driver active."
    fi
}

install_app() {
    local system_qt="${1:-}"
    command -v python3 >/dev/null || fail "python3 is missing"
    python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || fail "Python 3.10 or newer is needed"
    python3 -c 'import venv, ensurepip' 2>/dev/null ||
        fail "python3 venv support is missing. On Debian/Ubuntu: sudo apt install python3-venv"
    say "Installing the app into $APPDIR"
    rm -rf "$APPDIR/venv"
    mkdir -p "$APPDIR" "$BINDIR"
    if [ -n "$system_qt" ]; then
        python3 -c 'import PyQt6.QtWidgets, PyQt6.QtSvg, numpy' 2>/dev/null ||
            fail "PyQt6 or numpy is missing. On Debian/Ubuntu/Mint: sudo apt install python3-pyqt6 python3-pyqt6.qtsvg python3-numpy"
        python3 -m venv --system-site-packages "$APPDIR/venv"
        "$APPDIR/venv/bin/pip" install --quiet --no-deps "$HERE"
    else
        python3 -m venv "$APPDIR/venv"
        "$APPDIR/venv/bin/pip" install --quiet --upgrade pip
        # Qt 6.10+ from PyPI needs SSE4.2 and POPCNT; older x86 CPUs get 6.9.
        if [ "$(uname -m)" = x86_64 ] && ! grep -qw sse4_2 /proc/cpuinfo; then
            say "This CPU has no SSE4.2; using PySide6 6.9"
            "$APPDIR/venv/bin/pip" install --quiet "PySide6-Essentials>=6.5,<6.10"
        fi
        "$APPDIR/venv/bin/pip" install --quiet "$HERE"
    fi
    ln -sf "$APPDIR/venv/bin/vistacam" "$BINDIR/vistacam"
    install -Dm644 "$HERE/packaging/vistacam.desktop" "$DATA/applications/vistacam.desktop"
    sed -i "s|^Exec=.*|Exec=$BINDIR/vistacam|" "$DATA/applications/vistacam.desktop"
    install -Dm644 "$HERE/packaging/vistacam.svg" "$DATA/icons/hicolor/scalable/apps/vistacam.svg"
    command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA/icons/hicolor" || true
    say "Done. Start VistaCam from your menu, or run: vistacam"
    case ":$PATH:" in *":$BINDIR:"*) ;; *) say "Note: $BINDIR is not on your PATH." ;; esac
}

uninstall() {
    say "Removing app"
    rm -rf "$APPDIR" "$BINDIR/vistacam" "$DATA/applications/vistacam.desktop" \
        "$DATA/icons/hicolor/scalable/apps/vistacam.svg"
    if dkms status -m "$PKG" 2>/dev/null | grep -q .; then
        say "Removing driver (the stock gspca_ov519 comes back)"
        sudo dkms remove -m "$PKG" -v "$VER" --all || true
        sudo rm -rf "/usr/src/$PKG-$VER"
        camera_in_use || { sudo modprobe -r gspca_ov519 2>/dev/null && sudo modprobe gspca_ov519; } || true
    fi
}

[ "$(id -u)" -eq 0 ] && fail "run as your normal user; the script uses sudo where needed"

case "${1:-all}" in
    all)          install_driver; install_app ;;
    --driver)     install_driver ;;
    --app)        install_app ;;
    --system-qt)  install_app system-qt ;;
    --uninstall)  uninstall ;;
    *)            sed -n '2,9p' "$0"; exit 1 ;;
esac
