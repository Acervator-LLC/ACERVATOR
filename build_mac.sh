#!/bin/bash
# ============================================================================
#  Acervator — macOS Build Script
#  Produces: dist/Acervator.app
#
#  Usage:
#      chmod +x build_mac.sh
#      ./build_mac.sh              # Build .app only
#      ./build_mac.sh --dmg        # Build .app + wrap in .dmg
#      ./build_mac.sh --sign "Developer ID Application: Your Name (TEAMID)"
# ============================================================================

set -e

APP_NAME="Acervator"
# The version is derived, never written down, so there is no literal to parse.
# src/_version.py resolves it from the git tag and answers through the package.
VERSION="$(python3 -c 'import src; print(src.__version__)' 2>/dev/null || echo "unknown")"
[ -z "$VERSION" ] && VERSION="unknown"
SIGN_IDENTITY=""
MAKE_DMG=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dmg)      MAKE_DMG=true; shift ;;
        --sign)     SIGN_IDENTITY="$2"; shift 2 ;;
        *)          echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo ""
echo "  ========================================="
echo "   ${APP_NAME} v${VERSION} — macOS Build"
echo "  ========================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Install from python.org or via Homebrew."
    exit 1
fi

# Install dependencies
#
# Issue #94 - this line used to hand-copy 14 package names. It named
# `requests`, which no file in the repository imports, and it did NOT
# name `defusedxml`, which src/gui/crypto_news_ticker.py imports at
# module level. The names now come from pyproject.toml, which is the one
# source. `tools/deps.py build` answers the core set plus the `build` and
# `report` extras, which is what a PyInstaller HOST needs.
echo "[1/4] Installing dependencies..."
DEPS="$(python3 -m tools.deps requirements build)" || {
    echo "ERROR: could not read the dependency set from pyproject.toml"
    exit 1
}
[ -n "$DEPS" ] || { echo "ERROR: empty dependency set; refusing to build"; exit 1; }
# shellcheck disable=SC2086
pip3 install $DEPS --quiet

# Build the .app
echo "[2/4] Building ${APP_NAME}.app..."
pyinstaller Acervator_mac.spec --noconfirm

APP_PATH="dist/${APP_NAME}.app"

if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: .app bundle not created."
    exit 1
fi

# Codesign if identity provided
if [ -n "$SIGN_IDENTITY" ]; then
    echo "[3/4] Code signing..."
    codesign --deep --force --verify --verbose \
        --sign "$SIGN_IDENTITY" \
        --options runtime \
        "$APP_PATH"
    echo "  Signed with: $SIGN_IDENTITY"
else
    echo "[3/4] Skipping code signing (no --sign provided)"
fi

# Create DMG if requested
if [ "$MAKE_DMG" = true ]; then
    echo "[4/4] Creating DMG..."
    DMG_PATH="dist/${APP_NAME}-${VERSION}.dmg"
    rm -f "$DMG_PATH"

    # Create a staging directory with .app and Applications symlink
    STAGING=$(mktemp -d)
    cp -R "$APP_PATH" "$STAGING/"
    ln -s /Applications "$STAGING/Applications"

    hdiutil create \
        -volname "$APP_NAME" \
        -srcfolder "$STAGING" \
        -ov -format UDZO \
        -imagekey zlib-level=9 \
        "$DMG_PATH"

    rm -rf "$STAGING"
    echo "  DMG created: $DMG_PATH"
else
    echo "[4/4] Skipping DMG (use --dmg to create)"
fi

echo ""
echo "  ========================================="
echo "   OUTPUT: dist/${APP_NAME}.app"
if [ "$MAKE_DMG" = true ]; then
    echo "   DMG:    dist/${APP_NAME}-${VERSION}.dmg"
fi
echo "  ========================================="
echo ""
echo "  To run:  open \"dist/${APP_NAME}.app\""
echo "  To install: drag .app to /Applications"
echo ""
