#!/usr/bin/env bash
# =============================================================================
#  acervator-preflight.sh
#  Run by systemd as ExecStartPre= before starting the Acervator service.
#  Exit 0 = all checks passed, proceed to start.
#  Exit 1 = a check failed, systemd will not start the service.
# =============================================================================

set -euo pipefail

LOG_TAG="acervator-preflight"
log()   { logger -t "$LOG_TAG" "$*"; echo "  [preflight] $*"; }
fail()  { logger -t "$LOG_TAG" "FAIL: $*"; echo "  [preflight] FAIL: $*" >&2; exit 1; }
pass()  { logger -t "$LOG_TAG" "OK: $*";   echo "  [preflight] OK:   $*"; }

log "Starting pre-flight checks..."

# ── CHECK 1: NTP synchronisation ─────────────────────────────────────────────
# Exchange APIs use signed timestamps. A clock more than 5s out of sync
# will cause authentication failures on Binance, Coinbase, etc.
log "Checking NTP sync..."

NTP_STATUS=$(timedatectl show --property=NTPSynchronized --value 2>/dev/null || echo "unknown")
OFFSET_USEC=$(chronyc tracking 2>/dev/null | grep "System time" | grep -oP '[\d.]+(?= seconds)' || echo "999")

if [[ "$NTP_STATUS" != "yes" ]]; then
    # Give chrony up to 30 seconds to synchronise before failing
    log "NTP not yet synchronised — waiting up to 30s..."
    for i in $(seq 1 6); do
        sleep 5
        NTP_STATUS=$(timedatectl show --property=NTPSynchronized --value 2>/dev/null || echo "no")
        [[ "$NTP_STATUS" = "yes" ]] && break
    done
fi

if [[ "$NTP_STATUS" != "yes" ]]; then
    fail "NTP not synchronised after 30s. Check chrony: chronyc tracking"
fi

# Warn if offset is large (> 1 second) even if "synchronised"
OFFSET_INT=${OFFSET_USEC%%.*}
if (( OFFSET_INT > 1 )); then
    log "WARNING: NTP offset is ${OFFSET_USEC}s — unusually large"
fi

pass "NTP synchronised (offset: ${OFFSET_USEC}s)"

# ── CHECK 2: Network connectivity ────────────────────────────────────────────
log "Checking network connectivity..."

PING_TARGETS=("8.8.8.8" "1.1.1.1")
NET_OK=false
for target in "${PING_TARGETS[@]}"; do
    if ping -c 1 -W 3 "$target" &>/dev/null; then
        NET_OK=true
        break
    fi
done

if [[ "$NET_OK" = false ]]; then
    fail "No network connectivity. Check ethernet/wifi connection."
fi
pass "Network reachable"

# ── CHECK 3: DNS resolution ───────────────────────────────────────────────────
log "Checking DNS..."
if ! host api.binance.com &>/dev/null && ! nslookup api.binance.com &>/dev/null; then
    log "WARNING: DNS resolution for api.binance.com failed — may affect some exchanges"
fi
pass "DNS functional"

# ── CHECK 4: USB hardware key (if hardware mode is active) ───────────────────
# Read RULE_REGISTRY.json to see if any exchange is in hardware mode.
# If so, verify the USB key is present before starting.
RULE_REGISTRY="/opt/acervator/src/RULE_REGISTRY.json"
CONFIG_DIR="/home/acervator/.acervator/config"

if [[ -f "${CONFIG_DIR}/settings.json" ]]; then
    # Check if any exchange has hardware_mode=true
    HW_EXCHANGES=$(python3 -c "
import json, sys
try:
    s = json.load(open('${CONFIG_DIR}/settings.json'))
    hw = [e['exchange_id'] for e in s.get('exchanges', [])
          if e.get('hardware_mode', False)]
    if hw:
        serial = s['exchanges'][0].get('hw_volume_serial', '')
        print(f'{len(hw)}:{serial}')
    else:
        print('0:')
except: print('0:')
" 2>/dev/null || echo "0:")

    HW_COUNT="${HW_EXCHANGES%%:*}"
    HW_SERIAL="${HW_EXCHANGES##*:}"

    if [[ "$HW_COUNT" -gt "0" && -n "$HW_SERIAL" ]]; then
        log "Hardware mode active for ${HW_COUNT} exchange(s). Checking USB key (serial: ${HW_SERIAL:0:8}...)..."

        USB_FOUND=$(python3 -c "
import sys
sys.path.insert(0, '/opt/acervator/src')
try:
    from src.core.usb_auth import find_auth_volume
    v = find_auth_volume('${HW_SERIAL}')
    print('found' if v else 'missing')
except Exception as e:
    print(f'error:{e}')
" 2>/dev/null || echo "error:import_failed")

        case "$USB_FOUND" in
            found)   pass "USB hardware key present and valid" ;;
            missing) fail "USB hardware key not found. Insert the USB drive (serial: ${HW_SERIAL:0:8}...) and retry." ;;
            error:*) log "WARNING: USB key check error: ${USB_FOUND#error:}" ;;
        esac
    else
        pass "Hardware mode not active (software credentials)"
    fi
else
    pass "No settings.json — first-run mode (hardware key check skipped)"
fi

# ── CHECK 5: Python environment ───────────────────────────────────────────────
log "Checking Python environment..."
if ! /opt/acervator/venv/bin/python3 -c "import PySide6, ccxt, cryptography" &>/dev/null; then
    fail "Required Python packages missing. Re-run: sudo bash install.sh --dev"
fi
pass "Python environment OK"

# ── CHECK 6: Display server (if not headless) ─────────────────────────────────
if [[ -n "${DISPLAY:-}" ]]; then
    log "Checking display server..."
    if ! xdpyinfo -display "${DISPLAY}" &>/dev/null; then
        log "WARNING: Display server not ready on ${DISPLAY} — Acervator may start in headless mode"
    else
        pass "Display server OK (${DISPLAY})"
    fi
fi


# ── CHECK 6 (Optional): Mini display detection ────────────────────────────────
log "Checking for mini displays (optional)..."
if command -v acervator-display-detect &>/dev/null; then
    if acervator-display-detect --quiet 2>/dev/null; then
        pass "Mini display(s) detected and available"
    else
        log "No mini displays detected — continuing without display output"
    fi
else
    log "Display detection script not installed — skipping"
fi

# ── All checks passed ─────────────────────────────────────────────────────────
log "All pre-flight checks passed. Starting Acervator v$(
    python3 -c "
import sys; sys.path.insert(0, '/opt/acervator/src')
try:
    from src import __version__; print(__version__)
except: print('?')
" 2>/dev/null)..."
exit 0
