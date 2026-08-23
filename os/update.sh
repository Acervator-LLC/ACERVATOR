#!/usr/bin/env bash
# =============================================================================
#  AcervatorOS — Update Script
#  Updates Acervator in-place without reinstalling the OS configuration.
#  Service is stopped, source updated, service restarted.
#
#  Usage:
#    sudo bash update.sh                        # Update from current directory
#    sudo bash update.sh /path/to/acervator.zip # Update from zip file
#         bash update.sh --dry-run              # Print actions, change nothing
#
#  The exclude set, the service calls and the dependency derivation all
#  live in os/lib/common.sh, which os/install.sh reads as well. Issue
#  #88: this script and the installer used to hold their own copies,
#  and the two exclude sets had already drifted apart.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

INSTALL_DIR="/opt/acervator"
VENV_DIR="${INSTALL_DIR}/venv"
ZIP_SOURCE=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) ACERVATOR_DRY_RUN=true ;;
        *)         ZIP_SOURCE="$arg" ;;
    esac
done

if ! acervator_dry_run; then
    [[ $EUID -eq 0 ]] || fail "Run with sudo: sudo bash update.sh"
fi

echo ""
echo -e "${CYAN}  AcervatorOS — Updating Acervator${NC}"
if acervator_dry_run; then
    echo -e "  ${GOLD}DRY RUN — nothing on this machine will change${NC}"
fi
echo ""

# ── Stop service ─────────────────────────────────────────────────────────────
info "Stopping acervator service..."
acervator_service_stop
acervator_dry_run || sleep 2

# ── Backup current version ────────────────────────────────────────────────────
BACKUP_DIR="${INSTALL_DIR}/backup_$(date +%Y%m%d_%H%M%S)"
info "Backing up current install to ${BACKUP_DIR}..."
acervator_run cp -r "${INSTALL_DIR}/src" "${BACKUP_DIR}" 2>/dev/null || true
ok "Backup created"

# ── Apply update ──────────────────────────────────────────────────────────────
if [[ -n "$ZIP_SOURCE" && -f "$ZIP_SOURCE" ]]; then
    info "Extracting from zip: ${ZIP_SOURCE}"
    TMP_DIR=$(mktemp -d)
    unzip -q "$ZIP_SOURCE" -d "$TMP_DIR"
    # Find the directory holding main.py in the zip. The systemd unit
    # runs `${INSTALL_DIR}/src/main.py`, and `acervator_sync_source`
    # below copies this directory to `${INSTALL_DIR}/src/`, so the
    # entry point of the archive must be the repository ROOT.
    SRC_DIR=$(find "$TMP_DIR" -maxdepth 2 -name "main.py" -exec dirname {} \; | head -1)
    [[ -n "$SRC_DIR" ]] || fail "Could not find main.py in zip archive"
    info "Source directory: ${SRC_DIR}"
else
    # Update from the repository root that holds this script
    SRC_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
    info "Updating from: ${SRC_DIR}"
fi

acervator_sync_source "$SRC_DIR" "${INSTALL_DIR}/src"

acervator_run chown -R acervator:acervator "${INSTALL_DIR}/src"
ok "Source updated"

# ── Update Python dependencies ────────────────────────────────────────────────
#
# Issue #94 - this list used to be hand-copied and it disagreed with
# os/install.sh, which is the script that created this venv. The names
# now come from pyproject.toml through tools/deps.py, so the update
# installs the same set the install did.
info "Updating Python packages..."
DEPS_PYTHON="${VENV_DIR}/bin/python3"
DEPS_PY="${INSTALL_DIR}/src/tools/deps.py"
# A dry run reads the tree it was launched from, because /opt is not
# there to read.
if acervator_dry_run; then
    DEPS_PYTHON="$(acervator_find_python)" || \
        fail "A dry run needs a Python ${ACERVATOR_PYTHON_MIN_MAJOR}.${ACERVATOR_PYTHON_MIN_MINOR} or later on PATH"
    DEPS_PY="${SRC_DIR}/tools/deps.py"
fi
DEPS="$(acervator_deps "$DEPS_PYTHON" "$DEPS_PY" os)" || \
    fail "Could not read the dependency set from ${DEPS_PY%/tools/deps.py}/pyproject.toml"
[[ -n "$DEPS" ]] || fail "Empty dependency set; refusing to update"
# shellcheck disable=SC2086
acervator_run "${VENV_DIR}/bin/pip" install $DEPS --upgrade --quiet
ok "Dependencies updated"

# ── Show new version ──────────────────────────────────────────────────────────
if acervator_dry_run; then
    NEW_VER="$(acervator_read_version "$DEPS_PYTHON" "$SRC_DIR")"
else
    NEW_VER="$(acervator_read_version "${VENV_DIR}/bin/python3" "${INSTALL_DIR}/src")"
fi

ok "Updated to Acervator v${NEW_VER}"

# ── Restart service ───────────────────────────────────────────────────────────
info "Starting acervator service..."
acervator_service_start
acervator_dry_run || sleep 3

if acervator_service_is_active; then
    ok "Service running"
else
    echo ""
    echo -e "${RED}  Service failed to start. Check logs:${NC}"
    echo "  journalctl -u acervator -n 50"
    echo ""
    echo -e "${CYAN}  Rolling back...${NC}"
    acervator_run rsync -a --delete "${BACKUP_DIR}/" "${INSTALL_DIR}/src/"
    acervator_service_start || true
    fail "Update rolled back due to service failure"
fi

echo ""
ok "AcervatorOS updated to v${NEW_VER}"
echo ""

if acervator_dry_run; then
    echo -e "  ${GOLD}DRY RUN finished. Nothing on this machine changed.${NC}"
    echo ""
fi
