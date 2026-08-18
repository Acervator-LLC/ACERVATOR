#!/usr/bin/env bash
# =============================================================================
#  AcervatorOS — Update Script
#  Updates Acervator in-place without reinstalling the OS configuration.
#  Service is stopped, source updated, service restarted.
#
#  Usage:
#    sudo bash update.sh                        # Update from current directory
#    sudo bash update.sh /path/to/acervator.zip # Update from zip file
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓  $*${NC}"; }
info() { echo -e "${CYAN}  ▸  $*${NC}"; }
fail() { echo -e "${RED}  ✗  $*${NC}" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Run with sudo: sudo bash update.sh"

INSTALL_DIR="/opt/acervator"
VENV_DIR="${INSTALL_DIR}/venv"
ZIP_SOURCE="${1:-}"

echo ""
echo -e "${CYAN}  AcervatorOS — Updating Acervator${NC}"
echo ""

# ── Stop service ─────────────────────────────────────────────────────────────
info "Stopping acervator service..."
systemctl stop acervator.service 2>/dev/null || true
sleep 2

# ── Backup current version ────────────────────────────────────────────────────
BACKUP_DIR="${INSTALL_DIR}/backup_$(date +%Y%m%d_%H%M%S)"
info "Backing up current install to ${BACKUP_DIR}..."
cp -r "${INSTALL_DIR}/src" "${BACKUP_DIR}" 2>/dev/null || true
ok "Backup created"

# ── Apply update ──────────────────────────────────────────────────────────────
if [[ -n "$ZIP_SOURCE" && -f "$ZIP_SOURCE" ]]; then
    info "Extracting from zip: ${ZIP_SOURCE}"
    TMP_DIR=$(mktemp -d)
    unzip -q "$ZIP_SOURCE" -d "$TMP_DIR"
    # Find the acervator/ or quantum_auto_trader/ directory in the zip
    SRC_DIR=$(find "$TMP_DIR" -maxdepth 2 -name "main.py" -exec dirname {} \; | head -1)
    [[ -n "$SRC_DIR" ]] || fail "Could not find main.py in zip archive"
    info "Source directory: ${SRC_DIR}"
else
    # Update from the directory containing this script
    SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    info "Updating from: ${SRC_DIR}"
fi

rsync -a --delete \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='dist/' \
    --exclude='build/' \
    --exclude='*.zip' \
    --exclude='RULE_REGISTRY.json' \
    --exclude='logs/' \
    "${SRC_DIR}/" "${INSTALL_DIR}/src/"

chown -R acervator:acervator "${INSTALL_DIR}/src"
ok "Source updated"

# ── Update Python dependencies ────────────────────────────────────────────────
info "Updating Python packages..."
"${VENV_DIR}/bin/pip" install \
    PySide6 ccxt cryptography keyring pandas numpy \
    reportlab aiohttp certifi tomli_w requests \
    --upgrade --quiet
ok "Dependencies updated"

# ── Show new version ──────────────────────────────────────────────────────────
NEW_VER=$("${VENV_DIR}/bin/python3" -c "
import sys; sys.path.insert(0, '${INSTALL_DIR}/src')
try:
    from src import __version__; print(__version__)
except: print('unknown')
" 2>/dev/null)

ok "Updated to Acervator v${NEW_VER}"

# ── Restart service ───────────────────────────────────────────────────────────
info "Starting acervator service..."
systemctl start acervator.service
sleep 3

if systemctl is-active --quiet acervator.service; then
    ok "Service running"
else
    echo ""
    echo -e "${RED}  Service failed to start. Check logs:${NC}"
    echo "  journalctl -u acervator -n 50"
    echo ""
    echo -e "${CYAN}  Rolling back...${NC}"
    rsync -a --delete "${BACKUP_DIR}/" "${INSTALL_DIR}/src/"
    systemctl start acervator.service 2>/dev/null || true
    fail "Update rolled back due to service failure"
fi

echo ""
ok "AcervatorOS updated to v${NEW_VER}"
echo ""
