#!/usr/bin/env bash
# ew2 - Fedora RPM builder
# Usage: ./build-rpm.sh
set -euo pipefail

PKG_NAME="ew2"
PKG_VERSION="4.0.0"
PKG_RELEASE="1"
PYTHON="${PYTHON:-python3}"
TOPDIR="$(pwd)/rpm"

cd "$(dirname "$0")/.."

echo "Building executables..."
"$PYTHON" -m PyInstaller klatom.spec --clean --noconfirm
"$PYTHON" -m PyInstaller ew2mod.spec --clean --noconfirm

echo "Creating RPM..."
mkdir -p "$TOPDIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

cp dist/ew2 "$TOPDIR/SOURCES/ew2-bin"
cp dist/ew2-Mod "$TOPDIR/SOURCES/ew2-mod-bin"
chmod 755 "$TOPDIR/SOURCES/ew2-bin" "$TOPDIR/SOURCES/ew2-mod-bin"

cat > "$TOPDIR/SPECS/ew2.spec" <<EOF
Name:           $PKG_NAME
Version:        $PKG_VERSION
Release:        $PKG_RELEASE
Summary:        ew² Discord Username Checker
License:        Custom
URL:            https://production.ew2-26c.pages.dev
Source0:        ew2-bin
Source1:        ew2-mod-bin
Requires:       python3
Requires:       python3-tkinter

%description
High-performance Discord username checker with 17+ proxy sources,
speed testing, and multi-threaded checking.

%prep

%build

%install
mkdir -p %{buildroot}/usr/bin
install -m 755 %{_sourcedir}/ew2-bin %{buildroot}/usr/bin/ew2
install -m 755 %{_sourcedir}/ew2-mod-bin %{buildroot}/usr/bin/ew2-Mod

%files
/usr/bin/ew2
/usr/bin/ew2-Mod
EOF

rpmbuild -bb "$TOPDIR/SPECS/ew2.spec" \
    --define "_topdir $TOPDIR" \
    --define "_sourcedir $TOPDIR/SOURCES"

echo ""
echo "Built RPMs:"
find "$TOPDIR/RPMS" -name "*.rpm" -exec sha256sum {} \;
