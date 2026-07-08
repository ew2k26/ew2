#!/usr/bin/env bash
# ew2 - Universal Linux tarball builder
# Usage: ./build-tarball.sh
set -euo pipefail

PKG_NAME="ew2"
PKG_VERSION="4.0.0"
PYTHON="${PYTHON:-python3}"

cd "$(dirname "$0")/.."

echo "Building executables..."
"$PYTHON" -m PyInstaller klatom.spec --clean --noconfirm
"$PYTHON" -m PyInstaller ew2mod.spec --clean --noconfirm

echo "Creating universal tarball..."
STAGING="${PKG_NAME}-${PKG_VERSION}-linux-x86_64"
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp dist/ew2 "$STAGING/ew2"
cp dist/ew2-Mod "$STAGING/ew2-Mod"
chmod 755 "$STAGING/ew2" "$STAGING/ew2-Mod"

cat > "$STAGING/README.txt" <<EOF
ew² v${PKG_VERSION} - Linux x86_64 (Universal)

Requirements:
  - Python 3.10+ (for tkinter if not bundled)
  - Debian/Ubuntu: sudo apt install python3-tk
  - Arch Linux: sudo pacman -S tk
  - Fedora: sudo dnf install python3-tkinter
  - Alpine: sudo apk add tk

Quick start:
  chmod +x ew2
  ./ew2

Or run from terminal:
  python3 ew2 --terminal

Discord: https://discord.gg/7qHmtRbSWV
EOF

TARBALL="${STAGING}.tar.gz"
tar -czf "$TARBALL" "$STAGING"

echo ""
echo "Built: $TARBALL"
sha256sum "$TARBALL"
