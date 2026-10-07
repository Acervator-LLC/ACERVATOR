#!/bin/bash
# ============================================================================
#  Acervator — macOS Build Script
#  Produces: dist/Acervator-<version>-<variant>.app, one per variant
#
#  Usage:
#      chmod +x build_mac.sh
#      ./build_mac.sh              # Build every variant, .app only
#      ./build_mac.sh --variant qt # Build one variant
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
# hdiutil reports "Resource busy" while a volume from a prior image still detaches.
DMG_CREATE_ATTEMPTS=3
DMG_RETRY_WAIT_S=10
VARIANT_ARGS=()

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dmg)      MAKE_DMG=true; shift ;;
        --sign)     SIGN_IDENTITY="$2"; shift 2 ;;
        --variant)  VARIANT_ARGS+=(--variant "$2"); shift 2 ;;
        *)          echo "Unknown option: $1"; exit 1 ;;
    esac
done

# The environment variable the spec reads and the variant names are declared in
# src/_variant.py. Asking for them keeps no second copy here.
VARIANT_ENV_VAR="$(python3 -m tools.build_variants env-var)" || {
    echo "ERROR: could not read the build-variant environment variable"
    exit 1
}
VARIANTS="$(python3 -m tools.build_variants select "${VARIANT_ARGS[@]}")" || exit 1
[ -n "$VARIANTS" ] || { echo "ERROR: no build variant to build"; exit 1; }

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
# tools.deps prints one requirement per line, so DEP_ARGS takes one per element.
DEP_ARGS=()
while IFS= read -r REQUIREMENT; do
    DEP_ARGS+=("$REQUIREMENT")
done <<< "$DEPS"
pip3 install "${DEP_ARGS[@]}" --quiet

# Build one .app per variant. The spec names each bundle after the version and
# the variant and steps past a name already in dist, so nothing is overwritten.
echo "[2/4] Building ${APP_NAME}..."
BUILT_APPS=()
for VARIANT in $VARIANTS; do
    echo "  Building the ${VARIANT} variant..."
    BEFORE="$(ls -1 dist 2>/dev/null || true)"
    env "${VARIANT_ENV_VAR}=${VARIANT}" pyinstaller Acervator_mac.spec --noconfirm

    APP_PATH=""
    for CANDIDATE in dist/*.app; do
        [ -d "$CANDIDATE" ] || continue
        if ! printf '%s\n' "$BEFORE" | grep -qxF "$(basename "$CANDIDATE")"; then
            APP_PATH="$CANDIDATE"
        fi
    done
    if [ -z "$APP_PATH" ]; then
        echo "ERROR: the ${VARIANT} build produced no new .app bundle in dist/."
        exit 1
    fi
    echo "  Built: ${APP_PATH}"
    BUILT_APPS+=("$APP_PATH")
done

# Codesign if identity provided
if [ -n "$SIGN_IDENTITY" ]; then
    echo "[3/4] Code signing..."
    for APP_PATH in "${BUILT_APPS[@]}"; do
        codesign --deep --force --verify --verbose \
            --sign "$SIGN_IDENTITY" \
            --options runtime \
            "$APP_PATH"
        echo "  Signed: ${APP_PATH}"
    done
else
    echo "[3/4] Skipping code signing (no --sign provided)"
fi

# Create DMG if requested. The bundle basename already carries the version and
# the variant, so two DMGs never claim one path.
if [ "$MAKE_DMG" = true ]; then
    echo "[4/4] Creating DMG..."
    for APP_PATH in "${BUILT_APPS[@]}"; do
        BUNDLE_NAME="$(basename "$APP_PATH" .app)"
        DMG_PATH="dist/${BUNDLE_NAME}.dmg"
        rm -f "$DMG_PATH"

        # Create a staging directory with .app and Applications symlink
        STAGING=$(mktemp -d)
        cp -R "$APP_PATH" "$STAGING/"
        ln -s /Applications "$STAGING/Applications"

        # The volume name carries the variant too, so mounting both at once
        # gives two volumes a reader can tell apart.
        VOLUME_PATH="/Volumes/${BUNDLE_NAME}"
        DMG_WRITTEN=false
        ATTEMPT=1
        while [ "$ATTEMPT" -le "$DMG_CREATE_ATTEMPTS" ]; do
            # A volume left attached under this name is what makes the next
            # create report a busy resource, so detach it first either way.
            hdiutil detach "$VOLUME_PATH" -force || true

            if hdiutil create \
                -volname "$BUNDLE_NAME" \
                -srcfolder "$STAGING" \
                -ov -format UDZO \
                -imagekey zlib-level=9 \
                "$DMG_PATH"; then
                DMG_WRITTEN=true
                break
            fi

            echo "  hdiutil create failed on attempt ${ATTEMPT} of ${DMG_CREATE_ATTEMPTS} for ${DMG_PATH}"
            if [ "$ATTEMPT" -lt "$DMG_CREATE_ATTEMPTS" ]; then
                sleep "$DMG_RETRY_WAIT_S"
            fi
            ATTEMPT=$((ATTEMPT + 1))
        done

        if [ "$DMG_WRITTEN" != true ]; then
            rm -rf "$STAGING"
            echo "ERROR: hdiutil create failed ${DMG_CREATE_ATTEMPTS} times; ${DMG_PATH} was not written."
            exit 1
        fi

        # The next image in the loop carries a different volume name, so this
        # one is released here rather than by the next iteration's detach.
        hdiutil detach "$VOLUME_PATH" -force || true

        rm -rf "$STAGING"
        echo "  DMG created: ${DMG_PATH}"
    done
else
    echo "[4/4] Skipping DMG (use --dmg to create)"
fi

echo ""
echo "  ========================================="
echo "   ${APP_NAME} v${VERSION} — this run produced:"
for APP_PATH in "${BUILT_APPS[@]}"; do
    echo "     ${APP_PATH}"
done
echo "  ========================================="
echo ""
echo "  To run:  open \"${BUILT_APPS[0]}\""
echo "  To install: drag a .app to /Applications"
echo ""
