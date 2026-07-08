#!/usr/bin/env bash
# ew2 - Arch Linux standalone builder
# Usage: ./build-arch.sh (without makepkg)
set -euo pipefail

PKG_NAME="ew2"
PKG_VERSION="4.0.0"
PYTHON="${PYTHON:-python3}"

cd "$(dirname "$0")/.."

echo "Building executables..."
"$PYTHON" -m PyInstaller klatom.spec --clean --noconfirm
"$PYTHON" -m PyInstaller ew2mod.spec --clean --noconfirm

echo "Creating Arch package..."
STAGING="pkg-arch"
rm -rf "$STAGING"
mkdir -p "$STAGING/usr/bin"
cp dist/ew2 "$STAGING/usr/bin/ew2"
cp dist/ew2-Mod "$STAGING/usr/bin/ew2-Mod"
chmod 755 "$STAGING/usr/bin/ew2" "$STAGING/usr/bin/ew2-Mod"

TARBALL="${PKG_NAME}-${PKG_VERSION}-x86_64.pkg.tar.zst"
tar --zstd -cf "$TARBALL" -C "$STAGING" .

echo ""
echo "Built: $TARBALL"
sha256sum "$TARBALL"

echo ""
echo "Install on Arch:"
echo "  sudo pacman -U $TARBALL"
