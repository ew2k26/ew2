#!/usr/bin/env bash
# ew2 - Debian/Ubuntu .deb builder
# Usage: sudo ./build-deb.sh
set -euo pipefail

PKG_NAME="ew2"
PKG_VERSION="4.0.0"
PKG_ARCH="amd64"
BUILD_DIR="pkg-deb"
PYTHON="${PYTHON:-python3}"

cd "$(dirname "$0")/.."

echo "Building executables..."
"$PYTHON" -m PyInstaller klatom.spec --clean --noconfirm
"$PYTHON" -m PyInstaller ew2mod.spec --clean --noconfirm

echo "Creating .deb package..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/DEBIAN"
mkdir -p "$BUILD_DIR/usr/bin"
mkdir -p "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps"
mkdir -p "$BUILD_DIR/usr/share/applications"

cp dist/ew2 "$BUILD_DIR/usr/bin/ew2"
cp dist/ew2-Mod "$BUILD_DIR/usr/bin/ew2-mod"
chmod 755 "$BUILD_DIR/usr/bin/ew2" "$BUILD_DIR/usr/bin/ew2-mod"
cp ew2.ico "$BUILD_DIR/usr/share/icons/hicolor/256x256/apps/ew2.png"

cat > "$BUILD_DIR/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $PKG_VERSION
Section: utils
Priority: optional
Architecture: $PKG_ARCH
Depends: python3 (>= 3.8), python3-aiohttp, python3-tk
Maintainer: ew2 <noreply@ew2-26c.pages.dev>
Description: ew2 - Name checker with proxy support
 Supports 17+ free proxy sources, speed testing,
 and multi-threaded name checking.
EOF

cat > "$BUILD_DIR/usr/share/applications/ew2.desktop" <<EOF
[Desktop Entry]
Name=ew2
Comment=Name checker with proxy support
Exec=ew2
Icon=ew2
Terminal=true
Type=Application
Categories=Utility;
EOF

dpkg-deb --build "$BUILD_DIR" "${PKG_NAME}_${PKG_VERSION}_${PKG_ARCH}.deb"
echo "Built: ${PKG_NAME}_${PKG_VERSION}_${PKG_ARCH}.deb"
