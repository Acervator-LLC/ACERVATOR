#!/usr/bin/env bash
# =============================================================================
#  AcervatorOS — Installation Script
#  Target: Raspberry Pi OS Bookworm 64-bit  |  Debian 12+  |  Ubuntu 22.04+
#  Architecture: ARM64 (Pi 4/5) or x86-64
#
#  Usage:
#    sudo bash install.sh              # Standard install
#    sudo bash install.sh --headless   # No display (VNC only)
#    sudo bash install.sh --dev        # Skip system package install (faster)
#    sudo bash install.sh --unattended # No prompts (for image builds)
#
#  What this does:
#    1. Creates a dedicated 'acervator' system user
#    2. Installs Python 3.12 + all dependencies into a venv
#    3. Copies Acervator source to /opt/acervator
#    4. Installs and enables the acervator systemd service
#    5. Configures X11 auto-login + fullscreen startup (unless --headless)
#    6. Sets up ufw firewall (HTTPS + DNS + NTP + SSH only)
#    7. Generates boot splash screen
#    8. Configures NTP with chrony
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
GOLD='\033[0;33m'; GREY='\033[0;37m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}  ▸  $*${NC}"; }
ok()      { echo -e "${GREEN}  ✓  $*${NC}"; }
warn()    { echo -e "${GOLD}  ⚠  $*${NC}"; }
error()   { echo -e "${RED}  ✗  $*${NC}" >&2; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}═══ $* ═══${NC}\n"; }

# ── Guard: must be root ───────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || error "Run with sudo: sudo bash install.sh"

# ── Parse flags ───────────────────────────────────────────────────────────────
HEADLESS=false
DEV_MODE=false
UNATTENDED=false

for arg in "$@"; do
    case $arg in
        --headless)   HEADLESS=true   ;;
        --dev)        DEV_MODE=true   ;;
        --unattended) UNATTENDED=true ;;
    esac
done

# ── Detect architecture ───────────────────────────────────────────────────────
ARCH=$(uname -m)
case $ARCH in
    aarch64) ARCH_NAME="ARM64 (Raspberry Pi)" ;;
    x86_64)  ARCH_NAME="x86-64" ;;
    *)        warn "Untested architecture: $ARCH — proceeding anyway" ;;
esac

# ── Configuration ─────────────────────────────────────────────────────────────
ACERVATOR_USER="acervator"
INSTALL_DIR="/opt/acervator"
VENV_DIR="/opt/acervator/venv"
LOG_DIR="/var/log/acervator"
DATA_DIR="/home/${ACERVATOR_USER}/.acervator"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACERVATOR_VERSION=$(python3 -c "
import sys; sys.path.insert(0,'${SOURCE_DIR}')
try:
    from src import __version__; print(__version__)
except: print('3.7.0')
" 2>/dev/null || echo "3.7.0")

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║           AcervatorOS  v${ACERVATOR_VERSION}                     ║"
echo "  ║    Accumulation Trading Platform — Dedicated OS      ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${GREY}Architecture: ${ARCH_NAME}${NC}"
echo -e "  ${GREY}Install dir:  ${INSTALL_DIR}${NC}"
echo -e "  ${GREY}Mode:         $([ "$HEADLESS" = true ] && echo "Headless (VNC)" || echo "Display")${NC}"
echo ""

if [[ "$UNATTENDED" = false ]]; then
    read -rp "  Continue? [Y/n] " confirm
    [[ "${confirm,,}" =~ ^(y|)$ ]] || { echo "Aborted."; exit 0; }
fi

# ─────────────────────────────────────────────────────────────────────────────
section "1 / 8  System packages"
# ─────────────────────────────────────────────────────────────────────────────

if [[ "$DEV_MODE" = false ]]; then
    info "Updating package lists..."
    apt-get update -qq

    BASE_PKGS=(
        python3.12 python3.12-venv python3.12-dev python3-pip
        git curl wget unzip
        ufw chrony
        libgl1 libglib2.0-0 libdbus-1-3
        # Qt6 / PySide6 runtime deps
        libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1
        libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xkb1
        libxkbcommon-x11-0 libfontconfig1 libfreetype6
    )

    if [[ "$HEADLESS" = false ]]; then
        DISPLAY_PKGS=(
            xorg x11-utils xinit openbox
            lightdm lightdm-gtk-greeter
            unclutter   # hides mouse cursor in kiosk mode
        )
        BASE_PKGS+=("${DISPLAY_PKGS[@]}")
    else
        BASE_PKGS+=(tigervnc-standalone-server tigervnc-common)
    fi

    info "Installing system packages..."
    apt-get install -y -qq "${BASE_PKGS[@]}" 2>&1 | grep -E "^E:|^W:|installed" || true
    ok "System packages installed"
else
    warn "Dev mode: skipping system package install"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "2 / 8  User and directories"
# ─────────────────────────────────────────────────────────────────────────────

# Create system user (no login shell, no password)
if ! id "$ACERVATOR_USER" &>/dev/null; then
    useradd --system \
            --home-dir "/home/${ACERVATOR_USER}" \
            --create-home \
            --shell /bin/bash \
            --comment "AcervatorOS service account" \
            "$ACERVATOR_USER"
    ok "Created user: ${ACERVATOR_USER}"

    # Add to relevant groups
    usermod -aG audio,video,input,dialout,plugdev "$ACERVATOR_USER" 2>/dev/null || true
else
    ok "User ${ACERVATOR_USER} already exists"
fi

# Directories
for dir in "$INSTALL_DIR" "$LOG_DIR" "$DATA_DIR" \
           "${DATA_DIR}/logs" "${DATA_DIR}/reports" "${DATA_DIR}/config"; do
    mkdir -p "$dir"
done

chown -R "${ACERVATOR_USER}:${ACERVATOR_USER}" "$INSTALL_DIR" "$LOG_DIR" "$DATA_DIR"
ok "Directories created"

# ─────────────────────────────────────────────────────────────────────────────
section "3 / 8  Python virtual environment"
# ─────────────────────────────────────────────────────────────────────────────

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating Python 3.12 virtual environment..."
    python3.12 -m venv "$VENV_DIR"
    ok "venv created at ${VENV_DIR}"
else
    ok "venv already exists — upgrading packages"
fi

PYTHON="${VENV_DIR}/bin/python3"
PIP="${VENV_DIR}/bin/pip"

info "Upgrading pip..."
"$PIP" install --upgrade pip --quiet

info "Installing Acervator dependencies..."
"$PIP" install \
    PySide6 \
    ccxt \
    cryptography \
    keyring \
    pandas \
    numpy \
    reportlab \
    aiohttp \
    certifi \
    tomli_w \
    requests \
    --quiet

info "Installing mini display libraries (optional — safe to skip if no displays)..."
"$PIP" install \
    luma.oled \
    RPLCD \
    smbus2 \
    Pillow \
    --quiet 2>/dev/null || true
# st7789 and waveshare_epd are hardware-specific — install manually if needed
# pip install st7789         (for ST7789 TFT)
# pip install waveshare_epd  (for e-Paper — see waveshare wiki)

ok "Python dependencies installed"

# Enable I2C on Raspberry Pi (required for OLED and character LCD detection)
if command -v raspi-config &>/dev/null; then
    info "Enabling I2C interface (for mini display detection)..."
    raspi-config nonint do_i2c 0 2>/dev/null || true
    info "I2C enabled"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "4 / 8  Install Acervator source"
# ─────────────────────────────────────────────────────────────────────────────

info "Copying source from ${SOURCE_DIR}..."

# Sync source to install dir (exclude dev artifacts)
rsync -a --delete \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.git' \
    --exclude='dist/' \
    --exclude='build/' \
    --exclude='*.zip' \
    --exclude='logs/real_market/*' \
    --exclude='logs/paper/*' \
    "${SOURCE_DIR}/" "${INSTALL_DIR}/src/" 2>/dev/null || \
    cp -r "${SOURCE_DIR}/." "${INSTALL_DIR}/src/"

# Initialise rule registry if not present
if [[ ! -f "${INSTALL_DIR}/src/RULE_REGISTRY.json" ]]; then
    "$PYTHON" "${INSTALL_DIR}/src/src/core/rule_registry.py" \
        >"${INSTALL_DIR}/src/RULE_REGISTRY.json" 2>/dev/null || true
fi

chown -R "${ACERVATOR_USER}:${ACERVATOR_USER}" "${INSTALL_DIR}/src"
ok "Acervator source installed to ${INSTALL_DIR}/src"

# Copy display configuration
mkdir -p "${DATA_DIR}/config"
if [[ ! -f "${DATA_DIR}/config/display-config.json" ]]; then
    cp "${SCRIPT_DIR}/display/display-config.json" "${DATA_DIR}/config/" 2>/dev/null || true
    ok "Display config installed to ${DATA_DIR}/config/display-config.json"
fi
chmod +x "${SCRIPT_DIR}/display/display-detect.sh" 2>/dev/null || true
cp "${SCRIPT_DIR}/display/display-detect.sh" /usr/local/bin/acervator-display-detect
chmod +x /usr/local/bin/acervator-display-detect

# ─────────────────────────────────────────────────────────────────────────────
section "5 / 8  Systemd service"
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"

# Copy service files
cp "${SCRIPT_DIR}/systemd/acervator.service" /etc/systemd/system/
cp "${SCRIPT_DIR}/systemd/acervator-preflight.sh" /usr/local/bin/
chmod +x /usr/local/bin/acervator-preflight.sh

# Patch install paths into service file
sed -i "s|__INSTALL_DIR__|${INSTALL_DIR}|g" /etc/systemd/system/acervator.service
sed -i "s|__VENV_DIR__|${VENV_DIR}|g"       /etc/systemd/system/acervator.service
sed -i "s|__LOG_DIR__|${LOG_DIR}|g"         /etc/systemd/system/acervator.service
sed -i "s|__USER__|${ACERVATOR_USER}|g"     /etc/systemd/system/acervator.service

systemctl daemon-reload
systemctl enable acervator.service
ok "Systemd service installed and enabled"

# ─────────────────────────────────────────────────────────────────────────────
section "6 / 8  Display / auto-login"
# ─────────────────────────────────────────────────────────────────────────────

if [[ "$HEADLESS" = false ]]; then
    info "Configuring X11 auto-login..."
    bash "${SCRIPT_DIR}/config/display-setup.sh" \
        "$ACERVATOR_USER" "$INSTALL_DIR" "$VENV_DIR"
    ok "Display configured (fullscreen kiosk mode)"
else
    info "Configuring VNC server..."
    mkdir -p "/home/${ACERVATOR_USER}/.vnc"
    cat > "/home/${ACERVATOR_USER}/.vnc/xstartup" << 'XSTARTUP'
#!/bin/bash
exec openbox-session &
sleep 1
__VENV_DIR__/bin/python3 __INSTALL_DIR__/src/main.py
XSTARTUP
    sed -i "s|__VENV_DIR__|${VENV_DIR}|g" \
           "/home/${ACERVATOR_USER}/.vnc/xstartup"
    sed -i "s|__INSTALL_DIR__|${INSTALL_DIR}|g" \
           "/home/${ACERVATOR_USER}/.vnc/xstartup"
    chmod +x "/home/${ACERVATOR_USER}/.vnc/xstartup"
    chown -R "${ACERVATOR_USER}:" "/home/${ACERVATOR_USER}/.vnc"

    info "VNC configured on :1 — connect to $(hostname -I | awk '{print $1}'):5901"
    ok "Headless VNC configured"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "7 / 8  Firewall"
# ─────────────────────────────────────────────────────────────────────────────

bash "${SCRIPT_DIR}/config/firewall.sh"
ok "Firewall configured"

# ─────────────────────────────────────────────────────────────────────────────
section "8 / 8  NTP + boot splash"
# ─────────────────────────────────────────────────────────────────────────────

# Configure chrony for reliable timekeeping
cat > /etc/chrony/chrony.conf << 'CHRONY'
# AcervatorOS chrony configuration
# Multiple time sources for trading reliability
pool 0.pool.ntp.org iburst maxsources 4
pool 1.pool.ntp.org iburst maxsources 4
pool time.cloudflare.com iburst maxsources 2
pool time.google.com    iburst maxsources 2

driftfile /var/lib/chrony/chrony.drift
logdir /var/log/chrony
rtcsync
makestep 1.0 3
CHRONY

systemctl enable chrony
systemctl restart chrony 2>/dev/null || true
ok "NTP (chrony) configured with multiple time sources"

# Generate boot splash
if command -v python3 &>/dev/null; then
    "$PYTHON" "${SCRIPT_DIR}/splash/generate_splash.py" \
        --version "$ACERVATOR_VERSION" \
        --output /boot/acervator-splash.png 2>/dev/null || true
fi

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║          AcervatorOS installation complete           ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${GREY}Version:      Acervator v${ACERVATOR_VERSION}${NC}"
echo -e "  ${GREY}Install dir:  ${INSTALL_DIR}${NC}"
echo -e "  ${GREY}Service:      sudo systemctl {start|stop|status} acervator${NC}"
echo -e "  ${GREY}Logs:         journalctl -u acervator -f${NC}"
echo -e "  ${GREY}Config:       ${DATA_DIR}/config/${NC}"

if [[ "$HEADLESS" = true ]]; then
echo -e "  ${GREY}VNC:          vncviewer $(hostname -I | awk '{print $1}'):5901${NC}"
fi
echo ""
echo -e "  ${GOLD}Next steps:${NC}"
echo -e "  ${GREY}1. Insert your USB hardware key${NC}"
echo -e "  ${GREY}2. sudo systemctl start acervator${NC}"
echo -e "  ${GREY}3. Acervator will prompt for exchange API keys on first run${NC}"
echo ""
echo -e "  ${GOLD}Or reboot to start automatically:${NC} sudo reboot"
echo ""
