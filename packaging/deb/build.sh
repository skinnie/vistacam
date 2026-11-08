#!/usr/bin/env bash
# Build the two Debian packages into dist/:
#   gspca-ov519-vistacam-dkms_<ver>_all.deb   driver source, built by DKMS on install
#   vistacam_<ver>_amd64.deb                  the app, with a trimmed PySide6 in /opt/vistacam
#
#   packaging/deb/build.sh [version]   (default: version from pyproject.toml)
#
# Needs python3 with pip, dpkg-deb and readelf (binutils). Works on any
# x86_64 Debian/Ubuntu; the result installs on Debian 12+, Ubuntu 22.04+ and
# Linux Mint 21+ / LMDE 6+.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VER="${1:-$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml")}"
VER="${VER#v}"
# 6.9 is the last PySide6 whose Qt runs on CPUs without SSE4.2/POPCNT (Core 2,
# Athlon 64, Phenom); 6.10+ abort on them. See issue #1.
PYSIDE_VER=6.9.3
OUT="$ROOT/dist"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT"
MAINT="VistaCam contributors <https://github.com/skinnie/vistacam/issues>"
HOME_URL="https://github.com/skinnie/vistacam"

# ---------------------------------------------------------------- driver
PKG=gspca-ov519-vistacam
D="$WORK/dkms"
SRC="$D/usr/src/$PKG-$VER"
mkdir -p "$SRC" "$D/DEBIAN" "$D/usr/share/doc/$PKG-dkms"
cp "$ROOT"/driver/{Makefile,ov519.c,ov7670_creative.c,creative_tables.h,gspca.h,jpeg.h,w996Xcf.c} "$SRC/"
sed "s/^PACKAGE_VERSION=.*/PACKAGE_VERSION=\"$VER\"/" "$ROOT/driver/dkms.conf" > "$SRC/dkms.conf"
cp "$ROOT/LICENSE" "$D/usr/share/doc/$PKG-dkms/copyright"

cat > "$D/DEBIAN/control" <<EOF
Package: $PKG-dkms
Version: $VER
Architecture: all
Section: kernel
Priority: optional
Maintainer: $MAINT
Homepage: $HOME_URL
Depends: dkms (>= 2.8)
Recommends: linux-headers-generic | linux-headers-amd64 | linux-headers
Installed-Size: $(du -sk "$D/usr" | cut -f1)
Description: gspca_ov519 webcam driver with Creative's Vista IM tuning (DKMS)
 Replaces the kernel's gspca_ov519 module with one that adds 30 fps and
 Creative's own OV7670 sensor settings for the Creative Live! Cam Vista IM
 (VF0260, 041e:4052; VF0420, 041e:4064), plus saturation, sharpness, gamma, white balance,
 exposure, gain and backlight controls. Other OV519 cameras behave as before.
 .
 DKMS rebuilds the module for every new kernel.
EOF

cat > "$D/DEBIAN/postinst" <<EOF
#!/bin/sh
set -e
PKG=$PKG
VER=$VER
EOF
cat >> "$D/DEBIAN/postinst" <<'EOF'
[ "$1" = configure ] || exit 0
dkms status -m "$PKG" -v "$VER" | grep -q . || dkms add -m "$PKG" -v "$VER"
if [ -d "/lib/modules/$(uname -r)/build" ]; then
    dkms build -m "$PKG" -v "$VER" && dkms install -m "$PKG" -v "$VER" --force || {
        echo "VistaCam: building the driver failed; the stock driver stays in use." >&2
        exit 0
    }
else
    echo "VistaCam: kernel headers for $(uname -r) are missing; install them" >&2
    echo "          (sudo apt install linux-headers-$(uname -r)) and reinstall this package." >&2
    exit 0
fi
# Swap the running module if no app has the camera open.
if lsmod | grep -q '^gspca_ov519 '; then
    if modprobe -r gspca_ov519 2>/dev/null; then
        modprobe gspca_ov519 || true
    else
        echo "VistaCam: the camera is in use; the new driver loads after you replug it." >&2
    fi
fi
exit 0
EOF

cat > "$D/DEBIAN/prerm" <<EOF
#!/bin/sh
set -e
dkms remove -m $PKG -v $VER --all >/dev/null 2>&1 || true
if [ "\$1" = remove ] && lsmod | grep -q '^gspca_ov519 '; then
    modprobe -r gspca_ov519 2>/dev/null && modprobe gspca_ov519 || true
fi
exit 0
EOF
chmod 755 "$D/DEBIAN/postinst" "$D/DEBIAN/prerm"
chmod -R u=rwX,go=rX "$D/usr"
dpkg-deb --root-owner-group --build "$D" "$OUT/${PKG}-dkms_${VER}_all.deb"

# ---------------------------------------------------------------- app
A="$WORK/app"
LIB="$A/opt/vistacam/lib"
mkdir -p "$LIB" "$A/DEBIAN" "$A/usr/bin" "$A/usr/share/doc/vistacam"
python3 -m pip install --quiet --disable-pip-version-check --no-compile --no-deps \
    --only-binary=:all: --platform manylinux_2_28_x86_64 --python-version 3.10 \
    --implementation cp --target "$LIB" \
    "PySide6-Essentials==$PYSIDE_VER" "shiboken6==$PYSIDE_VER"
python3 -m pip install --quiet --disable-pip-version-check --no-compile --no-deps \
    --upgrade --target "$LIB" "$ROOT"
python3 "$ROOT/packaging/deb/trim_pyside.py" "$LIB"
rm -rf "$LIB"/*.dist-info/RECORD
find "$LIB" -name __pycache__ -prune -exec rm -rf {} +

cat > "$A/usr/bin/vistacam" <<'EOF'
#!/bin/sh
# Bundled PySide6 first; numpy comes from the system (python3-numpy).
exec /usr/bin/python3 -s -c 'import sys; sys.path.insert(0, "/opt/vistacam/lib"); from vistacam.window import main; sys.exit(main())' "$@"
EOF
chmod 755 "$A/usr/bin/vistacam"
install -Dm644 "$ROOT/packaging/vistacam.desktop" "$A/usr/share/applications/vistacam.desktop"
sed -i 's|^Exec=.*|Exec=/usr/bin/vistacam|' "$A/usr/share/applications/vistacam.desktop"
install -Dm644 "$ROOT/packaging/vistacam.svg" "$A/usr/share/icons/hicolor/scalable/apps/vistacam.svg"
cp "$ROOT/LICENSE" "$A/usr/share/doc/vistacam/copyright"

# Libraries the bundled Qt loads from the system (X11/Wayland/GL/fonts).
chmod -R u=rwX,go=rX "$A/opt" "$A/usr"
cat > "$A/DEBIAN/control" <<EOF
Package: vistacam
Version: $VER
Architecture: amd64
Section: video
Priority: optional
Maintainer: $MAINT
Homepage: $HOME_URL
Depends: python3 (>= 3.10), python3-numpy, libc6 (>= 2.28), libstdc++6, libgcc-s1, zlib1g, libzstd1,
 libglib2.0-0t64 | libglib2.0-0, libdbus-1-3, libfontconfig1, libfreetype6, libgl1, libegl1,
 libxkbcommon0, libxkbcommon-x11-0, libx11-6, libx11-xcb1, libxcb1, libxcb-cursor0, libxcb-glx0,
 libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render0, libxcb-render-util0,
 libxcb-shape0, libxcb-shm0, libxcb-sync1, libxcb-util1, libxcb-xfixes0, libxcb-xkb1,
 libwayland-client0, libwayland-cursor0, libwayland-egl1
Recommends: gspca-ov519-vistacam-dkms (= $VER), libgtk-3-0t64 | libgtk-3-0
Installed-Size: $(du -sk "$A/opt" "$A/usr" | awk '{s+=$1} END {print s}')
Description: live view and tuning app for the Creative Live! Cam Vista IM
 Supports the VF0260 (041e:4052) and VF0420 (041e:4064).
 .
 Live view with histogram, colour-cast and clipping meters, every driver
 control, a hold-to-compare stock view and a side-by-side A/B comparison of
 Creative's tuning against the stock Linux driver. Works with the stock
 gspca_ov519 driver too, with fewer controls.
EOF
cat > "$A/DEBIAN/postinst" <<'SH'
#!/bin/sh
[ "$1" = configure ] && python3 -m compileall -q /opt/vistacam/lib/vistacam >/dev/null 2>&1
exit 0
SH
cat > "$A/DEBIAN/prerm" <<'SH'
#!/bin/sh
find /opt/vistacam/lib -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
exit 0
SH
chmod 755 "$A/DEBIAN/postinst" "$A/DEBIAN/prerm"
dpkg-deb --root-owner-group -Zxz --build "$A" "$OUT/vistacam_${VER}_amd64.deb"

ls -lh "$OUT"/*"_${VER}_"*.deb
