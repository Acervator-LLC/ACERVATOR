#!/usr/bin/env bash
# AcervatorOS — Uninstall Script
# Removes all AcervatorOS components while preserving user trade data.
#
#   sudo bash uninstall.sh
#        bash uninstall.sh --dry-run   # Print actions, change nothing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

for arg in "$@"; do
    [[ "$arg" = "--dry-run" ]] && ACERVATOR_DRY_RUN=true
done

if ! acervator_dry_run; then
    [[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }
fi

echo ""
echo "  AcervatorOS Uninstall"
echo "  ════════════════════════════════════════"
echo "  This will remove Acervator and all system configuration."
echo "  Your trade data in /home/acervator/.acervator/ will be PRESERVED."
echo ""
if ! acervator_dry_run; then
    read -rp "  Continue? [y/N] " confirm
    [[ "${confirm,,}" = "y" ]] || { echo "Aborted."; exit 0; }
else
    echo -e "  ${GOLD}DRY RUN — nothing on this machine will change${NC}"
    echo ""
fi

# Stop and disable service
acervator_service_stop
acervator_service_disable
acervator_run rm -f /etc/systemd/system/acervator.service
acervator_run systemctl daemon-reload
echo "  ✓ Service removed"

# Remove install dir (preserve user data)
acervator_run rm -rf /opt/acervator
acervator_run rm -f /usr/local/bin/acervator-preflight.sh
acervator_run rm -f /usr/local/bin/acervator-display-detect
echo "  ✓ Install directory removed"

# Reset firewall to defaults
acervator_run ufw --force reset 2>/dev/null || true
echo "  ✓ Firewall reset"

# Remove LightDM autologin config
acervator_run rm -f /etc/lightdm/lightdm.conf
echo "  ✓ Display configuration removed"

echo ""
echo "  Trade data preserved at: /home/acervator/.acervator/"
echo "  To also remove user data: sudo rm -rf /home/acervator/.acervator"
echo "  To remove user account:   sudo userdel -r acervator"
echo ""
echo "  ✓ AcervatorOS uninstalled"
echo ""
