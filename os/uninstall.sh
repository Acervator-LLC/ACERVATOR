#!/usr/bin/env bash
# AcervatorOS — Uninstall Script
# Removes all AcervatorOS components while preserving user trade data.

set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Run with sudo"; exit 1; }

echo ""
echo "  AcervatorOS Uninstall"
echo "  ════════════════════════════════════════"
echo "  This will remove Acervator and all system configuration."
echo "  Your trade data in /home/acervator/.acervator/ will be PRESERVED."
echo ""
read -rp "  Continue? [y/N] " confirm
[[ "${confirm,,}" = "y" ]] || { echo "Aborted."; exit 0; }

# Stop and disable service
systemctl stop acervator.service 2>/dev/null || true
systemctl disable acervator.service 2>/dev/null || true
rm -f /etc/systemd/system/acervator.service
systemctl daemon-reload
echo "  ✓ Service removed"

# Remove install dir (preserve user data)
rm -rf /opt/acervator
rm -f /usr/local/bin/acervator-preflight.sh
echo "  ✓ Install directory removed"

# Reset firewall to defaults
ufw --force reset 2>/dev/null || true
echo "  ✓ Firewall reset"

# Remove LightDM autologin config
rm -f /etc/lightdm/lightdm.conf
echo "  ✓ Display configuration removed"

echo ""
echo "  Trade data preserved at: /home/acervator/.acervator/"
echo "  To also remove user data: sudo rm -rf /home/acervator/.acervator"
echo "  To remove user account:   sudo userdel -r acervator"
echo ""
echo "  ✓ AcervatorOS uninstalled"
echo ""
