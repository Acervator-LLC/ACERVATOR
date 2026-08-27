#!/usr/bin/env bash
# =============================================================================
#  AcervatorOS — Mini Display Detection Script
#  Run standalone for diagnostics, or called by acervator-preflight.sh
#
#  Usage:
#    bash display-detect.sh          # Detect and report
#    bash display-detect.sh --quiet  # Suppress output, exit 0 if any found
# =============================================================================

QUIET=false
[[ "${1:-}" = "--quiet" ]] && QUIET=true

log() { [[ "$QUIET" = false ]] && echo "  [display] $*"; }

DISPLAYS_FOUND=0
DISPLAY_SUMMARY=""

# ── I2C scan ──────────────────────────────────────────────────────────────────
if command -v i2cdetect &>/dev/null; then
    log "Scanning I2C bus 1..."

    # SSD1306 OLED (0x3C, 0x3D)
    for addr in 0x3c 0x3d; do
        result=$(i2cdetect -y 1 2>/dev/null | grep -c "${addr#0x}" || echo 0)
        if [[ "$result" -gt 0 ]]; then
            log "✓ Found SSD1306 OLED at I2C ${addr^^}"
            DISPLAY_SUMMARY="${DISPLAY_SUMMARY}oled_mono:${addr} "
            DISPLAYS_FOUND=$((DISPLAYS_FOUND + 1))
        fi
    done

    # HD44780 Character LCD with PCF8574 backpack (0x27, 0x3F)
    for addr in 0x27 0x3f; do
        result=$(i2cdetect -y 1 2>/dev/null | grep -c "${addr#0x}" || echo 0)
        if [[ "$result" -gt 0 ]]; then
            log "✓ Found HD44780 Character LCD at I2C ${addr^^}"
            DISPLAY_SUMMARY="${DISPLAY_SUMMARY}char_lcd:${addr} "
            DISPLAYS_FOUND=$((DISPLAYS_FOUND + 1))
        fi
    done
else
    log "i2cdetect not available — skipping I2C scan"
    log "  Install with: sudo apt-get install -y i2c-tools"
fi

# ── SPI check ─────────────────────────────────────────────────────────────────
if ls /dev/spidev* &>/dev/null 2>&1; then
    log "SPI devices present: $(ls /dev/spidev* 2>/dev/null | tr '\n' ' ')"
    log "  SPI displays (TFT, e-paper, color OLED) require manual config"
    log "  Edit: /opt/acervator/src/os/display/display-config.json"
fi

# ── Python driver availability ────────────────────────────────────────────────
if [[ "$QUIET" = false ]]; then
    log ""
    log "Python display library availability:"
    python3 -c "import luma.oled; print('  ✓ luma.oled')"   2>/dev/null || log "  ✗ luma.oled    (pip install luma.oled)"
    python3 -c "import RPLCD;     print('  ✓ RPLCD')"       2>/dev/null || log "  ✗ RPLCD        (pip install RPLCD)"
    python3 -c "import smbus2;    print('  ✓ smbus2')"       2>/dev/null || log "  ✗ smbus2       (pip install smbus2)"
    python3 -c "import ST7789;    print('  ✓ ST7789')"       2>/dev/null || log "  ✗ ST7789       (pip install st7789)"
    python3 -c "import waveshare_epd; print('  ✓ waveshare_epd')" 2>/dev/null || log "  ✗ waveshare_epd (see waveshare wiki)"
fi

# ── Compatibility report ──────────────────────────────────────────────────────
if [[ "$DISPLAYS_FOUND" -gt 0 && "$QUIET" = false ]]; then
    log ""
    log "Detected $DISPLAYS_FOUND display(s): $DISPLAY_SUMMARY"
    log ""
    log "Message compatibility:"
    log "  OLED_MONO : TRADE_ALERT BOT_STATE STATUS_LINE PRICE_TICKER NOTIFICATION ERROR STARTUP CHART_MINI"
    log "  CHAR_LCD  : TRADE_ALERT BOT_STATE STATUS_LINE PRICE_TICKER NOTIFICATION ERROR STARTUP (NO chart/rich/animation)"
    log "  E_PAPER   : TRADE_ALERT BOT_STATE STATUS_LINE NOTIFICATION ERROR STARTUP RICH_TEXT (NO ticker/animation/chart)"
    log "  TFT_COLOR : ALL message types supported"
    log "  OLED_COLOR: ALL message types supported"
fi

[[ "$DISPLAYS_FOUND" -gt 0 ]]   # exit 0 if found, 1 if none
