#!/usr/bin/env bash
# =============================================================================
#  AcervatorOS — Installation Script
#  Target: Ubuntu 24.04 LTS  |  Debian 12+  |  Raspberry Pi OS Bookworm
#  Architecture: ARM64 (Pi 4/5) or x86-64
#
#  Usage:
#    sudo bash install.sh              # Standard install
#    sudo bash install.sh --headless   # No display (VNC over an SSH tunnel)
#    sudo bash install.sh --dev        # Skip system package install (faster)
#    sudo bash install.sh --unattended # No prompts (for image builds)
#         bash install.sh --dry-run    # Print every action, change nothing
#
#  What this does:
#    1. Creates a dedicated 'acervator' system user
#    2. Installs Python 3.11 or later + all dependencies into a venv
#    3. Copies Acervator source to /opt/acervator
#    4. Installs and enables the acervator systemd service
#    5. Configures X11 auto-login + fullscreen startup (unless --headless)
#    6. Sets up ufw firewall (HTTPS + DNS + NTP + SSH only)
#    7. Generates boot splash screen
#    8. Configures NTP with chrony
#
#  --dry-run needs no root and touches nothing. It prints each command
#  it would run. `tests/test_os_installer_suite.py` uses it to prove
#  that this script reaches its last line, which it did not do before
#  issue #95. Read os/lib/common.sh for how the dry run works.
# =============================================================================

set -euo pipefail

# ── Where this script lives ──────────────────────────────────────────────────
#
# ISSUE #95, DEFECT ONE. This assignment used to sit at line 260, and
# lines 249, 252 and 253 read the variable. `set -u` ends the shell the
# moment it expands a variable that has no value, and a trailing
# `|| true` does not rescue it, because the shell never runs the
# command. The script exited at line 249 and never installed the
# systemd unit, the VNC startup file, the firewall rules or the time
# configuration.
#
# The assignment now comes before every use, and
# `tests/test_os_installer_suite.py` fails if any variable in this
# suite is ever read above its first assignment again.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

# ── Parse flags ───────────────────────────────────────────────────────────────
HEADLESS=false
DEV_MODE=false
UNATTENDED=false

for arg in "$@"; do
    case $arg in
        --headless)   HEADLESS=true   ;;
        --dev)        DEV_MODE=true   ;;
        --unattended) UNATTENDED=true ;;
        --dry-run)    ACERVATOR_DRY_RUN=true; UNATTENDED=true ;;
    esac
done

# ── Guard: must be root ───────────────────────────────────────────────────────
# A dry run changes nothing, so it needs no privilege. Demanding root
# for a dry run would put the whole suite back out of reach of a test.
if ! acervator_dry_run; then
    [[ $EUID -eq 0 ]] || error "Run with sudo: sudo bash install.sh"
fi

# ── Detect architecture ───────────────────────────────────────────────────────
ARCH=$(uname -m)
case $ARCH in
    aarch64) ARCH_NAME="ARM64 (Raspberry Pi)" ;;
    x86_64)  ARCH_NAME="x86-64" ;;
    *)       ARCH_NAME="$ARCH"
             warn "Untested architecture: $ARCH — proceeding anyway" ;;
esac

# ── Configuration ─────────────────────────────────────────────────────────────
ACERVATOR_USER="acervator"
INSTALL_DIR="/opt/acervator"
VENV_DIR="/opt/acervator/venv"
LOG_DIR="/var/log/acervator"
DATA_DIR="/home/${ACERVATOR_USER}/.acervator"

# The banner needs a version before apt has installed anything, so it
# uses whatever interpreter the machine already has. When there is
# none, the banner says "unknown" and the install carries on.
BANNER_PYTHON="$(acervator_find_python)" || BANNER_PYTHON=""
if [[ -n "$BANNER_PYTHON" ]]; then
    ACERVATOR_VERSION="$(acervator_read_version "$BANNER_PYTHON" "$SOURCE_DIR")"
else
    ACERVATOR_VERSION="unknown"
fi

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
if acervator_dry_run; then
    echo -e "  ${GOLD}DRY RUN — nothing on this machine will change${NC}"
fi
echo ""

if [[ "$UNATTENDED" = false ]]; then
    read -rp "  Continue? [Y/n] " confirm
    [[ "${confirm,,}" =~ ^(y|)$ ]] || { echo "Aborted."; exit 0; }
fi

# ─────────────────────────────────────────────────────────────────────────────
section "1 / 8  System packages"
# ─────────────────────────────────────────────────────────────────────────────

# ISSUE #95, DEFECT THREE. This list used to name `python3.12`,
# `python3.12-venv` and `python3.12-dev`. Debian 12 and Raspberry Pi OS
# Bookworm ship Python 3.11 and carry no `python3.12` package, so
# `apt-get install` failed on two of the three systems this file's own
# header named. `pyproject.toml` asks for `>=3.11`. The unversioned
# names below resolve to the system interpreter on every target, and
# section 3 then checks that interpreter against the floor.
BASE_PKGS=(
    python3 python3-venv python3-dev python3-pip
    git curl wget unzip rsync
    ufw chrony
    libgl1 libglib2.0-0 libdbus-1-3
    # Qt6 / PySide6 runtime deps.
    #
    # ISSUE #95, DEFECT TWO. `libxcb-cursor0` was missing. From Qt
    # 6.5.0 the xcb platform plugin REFUSES TO LOAD without it, and
    # `pyproject.toml` requires PySide6>=6.6.0, so no window would ever
    # open on a fresh install. The reported error names the plugin and
    # not the missing library, which is why it is hard to diagnose:
    #   "Could not load the Qt platform plugin xcb ... even though it
    #    was found."
    # `tests/test_os_installer_suite.py` fails if any name in this
    # block leaves the list.
    libxcb-cursor0
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

if [[ "$DEV_MODE" = false ]]; then
    info "Updating package lists..."
    acervator_run apt-get update -qq

    info "Installing system packages..."
    if acervator_dry_run; then
        acervator_run apt-get install -y -qq "${BASE_PKGS[@]}"
    else
        apt-get install -y -qq "${BASE_PKGS[@]}" 2>&1 | grep -E "^E:|^W:|installed" || true
    fi
    ok "System packages installed"
else
    warn "Dev mode: skipping system package install"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "2 / 8  User and directories"
# ─────────────────────────────────────────────────────────────────────────────

# Create system user (no login shell, no password)
if ! id "$ACERVATOR_USER" &>/dev/null; then
    acervator_run useradd --system \
            --home-dir "/home/${ACERVATOR_USER}" \
            --create-home \
            --shell /bin/bash \
            --comment "AcervatorOS service account" \
            "$ACERVATOR_USER"
    ok "Created user: ${ACERVATOR_USER}"

    # Add to relevant groups
    acervator_run usermod -aG audio,video,input,dialout,plugdev "$ACERVATOR_USER" \
        2>/dev/null || true
else
    ok "User ${ACERVATOR_USER} already exists"
fi

# Directories
for dir in "$INSTALL_DIR" "$LOG_DIR" "$DATA_DIR" \
           "${DATA_DIR}/logs" "${DATA_DIR}/reports" "${DATA_DIR}/config"; do
    acervator_run mkdir -p "$dir"
done

acervator_run chown -R "${ACERVATOR_USER}:${ACERVATOR_USER}" \
    "$INSTALL_DIR" "$LOG_DIR" "$DATA_DIR"
ok "Directories created"

# ─────────────────────────────────────────────────────────────────────────────
section "3 / 8  Python virtual environment"
# ─────────────────────────────────────────────────────────────────────────────

# The floor comes from `pyproject.toml`, through os/lib/common.sh.
SYSTEM_PYTHON="$(acervator_find_python)" || error \
    "Acervator needs Python ${ACERVATOR_PYTHON_MIN_MAJOR}.${ACERVATOR_PYTHON_MIN_MINOR} or later, and this machine has none. Ubuntu 24.04 LTS ships 3.12. Debian 12 and Raspberry Pi OS Bookworm ship 3.11. Ubuntu 22.04 ships 3.10 and does not meet the floor."
info "Using system interpreter: ${SYSTEM_PYTHON}"

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating the virtual environment..."
    acervator_run "$SYSTEM_PYTHON" -m venv "$VENV_DIR"
    ok "venv created at ${VENV_DIR}"
else
    ok "venv already exists — upgrading packages"
fi

PYTHON="${VENV_DIR}/bin/python3"
PIP="${VENV_DIR}/bin/pip"
# A dry run never built that venv, so the dependency derivation below
# needs an interpreter that exists. The derivation itself is not
# wrapped: a dry run has to prove that `tools/deps.py` still answers.
if acervator_dry_run; then
    PYTHON="$SYSTEM_PYTHON"
fi

info "Upgrading pip..."
acervator_run "$PIP" install --upgrade pip --quiet

# Issue #94 - these two lists used to be hand-copied. The first named
# 11 packages, of which `requests` is imported by no file in the tree,
# and it was missing `psutil`, `ta` and `defusedxml`. The names now come
# from pyproject.toml through tools/deps.py, which is the one source.
#
# A TARGET is not a build HOST. This install takes the `os` consumer,
# which is the core set plus the `report` extra. It must NOT take
# pyinstaller: AcervatorOS runs from source in this venv and never
# compiles the application.
info "Installing Acervator dependencies..."
DEPS="$(acervator_deps "$PYTHON" "${SOURCE_DIR}/tools/deps.py" os)" || \
    error "Could not read the dependency set from ${SOURCE_DIR}/pyproject.toml"
[[ -n "$DEPS" ]] || error "Empty dependency set; refusing to install"
# shellcheck disable=SC2086
acervator_run "$PIP" install $DEPS --quiet

# The mini-panel libraries are a separate step because failure is
# tolerated here: a Pi with no panel is a supported machine, and
# src/core/mini_display.py imports each of them inside a try block that
# returns False. They are the `display` extra, without the core set.
info "Installing mini display libraries (optional, safe to skip if no displays)..."
DISPLAY_DEPS="$(acervator_deps "$PYTHON" "${SOURCE_DIR}/tools/deps.py" display --extras-only)" || \
    DISPLAY_DEPS=""
if [[ -n "$DISPLAY_DEPS" ]]; then
    # shellcheck disable=SC2086
    acervator_run "$PIP" install $DISPLAY_DEPS --quiet 2>/dev/null || true
fi
# st7789 and waveshare_epd stay out of pyproject.toml on purpose: they
# are hardware-specific and this script never installed them either.
# pip install st7789         (for ST7789 TFT)
# pip install waveshare_epd  (for e-Paper - see waveshare wiki)

ok "Python dependencies installed"

# Enable I2C on Raspberry Pi (required for OLED and character LCD detection)
if command -v raspi-config &>/dev/null; then
    info "Enabling I2C interface (for mini display detection)..."
    acervator_run raspi-config nonint do_i2c 0 2>/dev/null || true
    info "I2C enabled"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "4 / 8  Install Acervator source"
# ─────────────────────────────────────────────────────────────────────────────

info "Copying source from ${SOURCE_DIR}..."

# The exclude set lives in os/lib/common.sh, and `os/update.sh` reads
# the same one. Issue #88: the two sets used to disagree, and the
# install side still excluded `sadp/RAIntSimBat/reports/*.json` from a
# subsystem that has never existed in this repository.
acervator_sync_source "$SOURCE_DIR" "${INSTALL_DIR}/src"

# Initialise rule registry if not present. `RULE_REGISTRY.json` is in
# the exclude set, so no later update deletes what this step writes.
if [[ ! -f "${INSTALL_DIR}/src/RULE_REGISTRY.json" ]]; then
    if acervator_dry_run; then
        info "[dry-run] would generate ${INSTALL_DIR}/src/RULE_REGISTRY.json"
    else
        "$PYTHON" "${INSTALL_DIR}/src/src/core/rule_registry.py" \
            >"${INSTALL_DIR}/src/RULE_REGISTRY.json" 2>/dev/null || true
    fi
fi

acervator_run chown -R "${ACERVATOR_USER}:${ACERVATOR_USER}" "${INSTALL_DIR}/src"
ok "Acervator source installed to ${INSTALL_DIR}/src"

# Copy display configuration
acervator_run mkdir -p "${DATA_DIR}/config"
if [[ ! -f "${DATA_DIR}/config/display-config.json" ]]; then
    acervator_run cp "${SCRIPT_DIR}/display/display-config.json" "${DATA_DIR}/config/"
    ok "Display config installed to ${DATA_DIR}/config/display-config.json"
fi
acervator_run chmod +x "${SCRIPT_DIR}/display/display-detect.sh"
acervator_run cp "${SCRIPT_DIR}/display/display-detect.sh" /usr/local/bin/acervator-display-detect
acervator_run chmod +x /usr/local/bin/acervator-display-detect

# ─────────────────────────────────────────────────────────────────────────────
section "5 / 8  Systemd service"
# ─────────────────────────────────────────────────────────────────────────────

# Copy service files
acervator_run cp "${SCRIPT_DIR}/systemd/acervator.service" /etc/systemd/system/
acervator_run cp "${SCRIPT_DIR}/systemd/acervator-preflight.sh" /usr/local/bin/
acervator_run chmod +x /usr/local/bin/acervator-preflight.sh

# Patch install paths into service file. `ExecStart` points at
# `${INSTALL_DIR}/src/main.py`, and section 4 copies the REPOSITORY
# ROOT into `${INSTALL_DIR}/src/`, so that path resolves to the
# repository's own main.py. Issue #89 read this as a defect. Issue #95
# corrected that: it is not one.
acervator_run sed -i "s|__INSTALL_DIR__|${INSTALL_DIR}|g" /etc/systemd/system/acervator.service
acervator_run sed -i "s|__VENV_DIR__|${VENV_DIR}|g"       /etc/systemd/system/acervator.service
acervator_run sed -i "s|__LOG_DIR__|${LOG_DIR}|g"         /etc/systemd/system/acervator.service
acervator_run sed -i "s|__USER__|${ACERVATOR_USER}|g"     /etc/systemd/system/acervator.service

acervator_service_enable
ok "Systemd service installed and enabled"

# ─────────────────────────────────────────────────────────────────────────────
section "6 / 8  Display / auto-login"
# ─────────────────────────────────────────────────────────────────────────────

DRY_RUN_FLAG=()
if acervator_dry_run; then
    DRY_RUN_FLAG=(--dry-run)
fi

if [[ "$HEADLESS" = false ]]; then
    info "Configuring X11 auto-login..."
    bash "${SCRIPT_DIR}/config/display-setup.sh" \
        "$ACERVATOR_USER" "$INSTALL_DIR" "$VENV_DIR" ${DRY_RUN_FLAG[@]+"${DRY_RUN_FLAG[@]}"}
    ok "Display configured (fullscreen kiosk mode)"
else
    info "Configuring VNC server..."
    acervator_run mkdir -p "/home/${ACERVATOR_USER}/.vnc"
    acervator_write_file "/home/${ACERVATOR_USER}/.vnc/xstartup" << XSTARTUP
#!/bin/bash
exec openbox-session &
sleep 1
${VENV_DIR}/bin/python3 ${INSTALL_DIR}/src/main.py
XSTARTUP
    acervator_run chmod +x "/home/${ACERVATOR_USER}/.vnc/xstartup"
    acervator_run chown -R "${ACERVATOR_USER}:" "/home/${ACERVATOR_USER}/.vnc"

    # ISSUE #95, DEFECT FOUR. This script used to print
    # "connect to <public address>:5901". `os/config/firewall.sh` has
    # never opened 5901 inbound, and it must not. A VNC port open to
    # the internet draws continuous scanning. The firewall was right
    # and this advice was wrong. The route in is an SSH tunnel over
    # port 22, which the firewall already permits, and the VNC server
    # must bind to the loopback interface only.
    # docs/guides/2026-08-23_run_acervator_in_the_cloud.md says the
    # same, in more detail.
    info "VNC will listen on :1 (port 5901), bound to localhost"
    info "Reach it with an SSH tunnel. Do NOT open port 5901:"
    info "    vncserver :1 -geometry 1920x1080 -localhost yes"
    info "    ssh -L 5901:localhost:5901 <user>@<this machine>"
    info "    then point your VNC viewer at localhost:5901"
    ok "Headless VNC configured"
fi

# ─────────────────────────────────────────────────────────────────────────────
section "7 / 8  Firewall"
# ─────────────────────────────────────────────────────────────────────────────

bash "${SCRIPT_DIR}/config/firewall.sh" ${DRY_RUN_FLAG[@]+"${DRY_RUN_FLAG[@]}"}
ok "Firewall configured"

# ─────────────────────────────────────────────────────────────────────────────
section "8 / 8  NTP + boot splash"
# ─────────────────────────────────────────────────────────────────────────────

# Configure chrony for reliable timekeeping
acervator_write_file /etc/chrony/chrony.conf << 'CHRONY'
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

acervator_run systemctl enable chrony
acervator_run systemctl restart chrony 2>/dev/null || true
ok "NTP (chrony) configured with multiple time sources"

# Generate boot splash
acervator_run "$PYTHON" "${SCRIPT_DIR}/splash/generate_splash.py" \
    --version "$ACERVATOR_VERSION" \
    --output /boot/acervator-splash.png 2>/dev/null || \
    warn "Boot splash was not generated"

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
echo -e "  ${GREY}VNC:          ssh -L 5901:localhost:5901 <user>@<this machine>${NC}"
echo -e "  ${GREY}              then connect your viewer to localhost:5901${NC}"
fi
echo ""
echo -e "  ${GOLD}Next steps:${NC}"
echo -e "  ${GREY}1. Insert your USB hardware key${NC}"
echo -e "  ${GREY}2. sudo systemctl start acervator${NC}"
echo -e "  ${GREY}3. Acervator will prompt for exchange API keys on first run${NC}"
echo ""
echo -e "  ${GOLD}Or reboot to start automatically:${NC} sudo reboot"
echo ""

if acervator_dry_run; then
    echo -e "  ${GOLD}DRY RUN finished. Nothing on this machine changed.${NC}"
    echo ""
fi
