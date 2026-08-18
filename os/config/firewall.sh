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
# =============================================================================

set -euo pipefail

NO_SSH=false
for arg in "$@"; do
    [[ "$arg" = "--no-ssh" ]] && NO_SSH=true
done

echo "  Configuring AcervatorOS firewall..."

# Reset to defaults
ufw --force reset

# Default policy: deny everything
ufw default deny incoming
ufw default deny outgoing
ufw default deny routed

# ── INBOUND ───────────────────────────────────────────────────────────────────

# SSH — remote maintenance
if [[ "$NO_SSH" = false ]]; then
    ufw allow in 22/tcp comment "SSH remote maintenance"
    echo "  ✓ SSH (22/tcp) inbound allowed"
else
    echo "  ⚠  SSH disabled — access only via physical console"
fi

# ── OUTBOUND ──────────────────────────────────────────────────────────────────

# DNS — required before any hostname can resolve
ufw allow out 53/udp  comment "DNS"
ufw allow out 53/tcp  comment "DNS (TCP fallback)"
echo "  ✓ DNS (53) outbound allowed"

# NTP — time synchronisation (critical for exchange auth)
ufw allow out 123/udp comment "NTP (chrony)"
echo "  ✓ NTP (123/udp) outbound allowed"

# HTTPS — exchange APIs and market data
# Using port 443 rather than specific IPs because:
#   - Exchanges use CDNs with rotating IPs (Binance, Coinbase, etc.)
#   - IP allowlists break silently when CDN changes
#   - TLS + certificate pinning (enforced by ccxt) provides auth
ufw allow out 443/tcp comment "HTTPS — exchange APIs and market data"
echo "  ✓ HTTPS (443/tcp) outbound allowed"

# HTTP — some exchanges have HTTP fallback endpoints and CoinGecko uses http
# Only enable if needed; disabled by default for security
# ufw allow out 80/tcp comment "HTTP fallback"

# ── Loopback ──────────────────────────────────────────────────────────────────
ufw allow in  on lo
ufw allow out on lo
echo "  ✓ Loopback allowed"

# ── Enable ────────────────────────────────────────────────────────────────────
ufw --force enable
ufw reload

echo ""
echo "  Firewall status:"
ufw status verbose | grep -E "Status:|To|From|Action|Default" | sed 's/^/    /'
echo ""
echo "  ✓ Firewall configured (default-deny, HTTPS + DNS + NTP outbound)"
