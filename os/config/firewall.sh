#!/usr/bin/env bash
# =============================================================================
#  AcervatorOS — Firewall Configuration
#  Uses ufw (Uncomplicated Firewall) with a strict default-deny policy.
#
#  Philosophy: a trading appliance should communicate with exactly three
#  categories of services — exchange APIs, time servers, and DNS.
#  Everything else is blocked by default.
#
#  Outbound allowed:
#    443/tcp  HTTPS    → Exchange APIs, CoinGecko, Yahoo Finance
#    53/udp   DNS      → Name resolution
#    53/tcp   DNS      → DNS fallback (TCP)
#    123/udp  NTP      → Time synchronisation (chrony)
#
#  Inbound allowed:
#    22/tcp   SSH      → Remote maintenance (can disable with --no-ssh)
#
#  Everything else: DENY
#
#  PORT 5901 STAYS SHUT. ON PURPOSE.
#  ---------------------------------
#  `os/install.sh --headless` starts a VNC server on :1, which is port
#  5901. Issue #95 read the closed port as defect four. It is not one.
#  The firewall is right and the printed advice was wrong. A VNC port
#  open to the internet draws continuous scanning, so the route in is
#  an SSH tunnel over port 22, which this file already permits:
#
#      vncserver :1 -geometry 1920x1080 -localhost yes
#      ssh -L 5901:localhost:5901 <user>@<machine>
#      then point the viewer at localhost:5901
#
#  `docs/guides/2026-08-23_run_acervator_in_the_cloud.md` says the same
#  and explains why. `tests/test_os_installer_suite.py` fails if any
#  rule in this file ever opens 5901.
#
#  Usage:
#    sudo bash firewall.sh
#    sudo bash firewall.sh --no-ssh
#         bash firewall.sh --dry-run    # Print actions, change nothing
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

NO_SSH=false
for arg in "$@"; do
    case "$arg" in
        --no-ssh)  NO_SSH=true ;;
        --dry-run) ACERVATOR_DRY_RUN=true ;;
    esac
done

echo "  Configuring AcervatorOS firewall..."
if acervator_dry_run; then
    echo -e "  ${GOLD}DRY RUN — no firewall rule will change${NC}"
fi

# Reset to defaults
acervator_run ufw --force reset

# Default policy: deny everything
acervator_run ufw default deny incoming
acervator_run ufw default deny outgoing
acervator_run ufw default deny routed

# ── INBOUND ───────────────────────────────────────────────────────────────────

# SSH — remote maintenance, and the only route to the VNC viewer
if [[ "$NO_SSH" = false ]]; then
    acervator_run ufw allow in 22/tcp comment "SSH remote maintenance and VNC tunnel"
    echo "  ✓ SSH (22/tcp) inbound allowed"
else
    echo "  ⚠  SSH disabled — access only via physical console"
    echo "  ⚠  With SSH off there is no route to the VNC viewer either"
fi

# ── OUTBOUND ──────────────────────────────────────────────────────────────────

# DNS — required before any hostname can resolve
acervator_run ufw allow out 53/udp  comment "DNS"
acervator_run ufw allow out 53/tcp  comment "DNS (TCP fallback)"
echo "  ✓ DNS (53) outbound allowed"

# NTP — time synchronisation (critical for exchange auth)
acervator_run ufw allow out 123/udp comment "NTP (chrony)"
echo "  ✓ NTP (123/udp) outbound allowed"

# HTTPS — exchange APIs and market data
# Using port 443 rather than specific IPs because:
#   - Exchanges use CDNs with rotating IPs (Binance, Coinbase, etc.)
#   - IP allowlists break silently when CDN changes
#   - TLS + certificate pinning (enforced by ccxt) provides auth
acervator_run ufw allow out 443/tcp comment "HTTPS — exchange APIs and market data"
echo "  ✓ HTTPS (443/tcp) outbound allowed"

# HTTP — some exchanges have HTTP fallback endpoints and CoinGecko uses http
# Only enable if needed; disabled by default for security
# ufw allow out 80/tcp comment "HTTP fallback"

# ── Loopback ──────────────────────────────────────────────────────────────────
# This is what carries the VNC session once SSH has forwarded it.
acervator_run ufw allow in  on lo
acervator_run ufw allow out on lo
echo "  ✓ Loopback allowed"

# ── Enable ────────────────────────────────────────────────────────────────────
acervator_run ufw --force enable
acervator_run ufw reload

echo ""
if ! acervator_dry_run; then
    echo "  Firewall status:"
    ufw status verbose | grep -E "Status:|To|From|Action|Default" | sed 's/^/    /'
    echo ""
fi
echo "  ✓ Firewall configured (default-deny, HTTPS + DNS + NTP outbound)"
echo "  ✓ Port 5901 is shut. Reach the VNC viewer through an SSH tunnel."
