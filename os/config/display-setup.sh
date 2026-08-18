#!/usr/bin/env bash
# =============================================================================
#  AcervatorOS — Display and Auto-Login Setup
#  Configures X11 + Openbox for fullscreen kiosk mode.
#  Acervator starts automatically on boot, full-screen, no window chrome.
# =============================================================================

set -euo pipefail

ACERVATOR_USER="${1:?Usage: display-setup.sh <user> <install_dir> <venv_dir>}"
INSTALL_DIR="${2:?}"
VENV_DIR="${3:?}"

HOME_DIR="/home/${ACERVATOR_USER}"

# ── LightDM auto-login ────────────────────────────────────────────────────────
cat > /etc/lightdm/lightdm.conf << LIGHTDM
[Seat:*]
autologin-user=${ACERVATOR_USER}
autologin-user-timeout=0
autologin-session=openbox
user-session=openbox
greeter-session=lightdm-gtk-greeter
xserver-command=X -nocursor
LIGHTDM

# ── Openbox config ────────────────────────────────────────────────────────────
mkdir -p "${HOME_DIR}/.config/openbox"

cat > "${HOME_DIR}/.config/openbox/rc.xml" << 'OPENBOX_RC'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <resistance><strength>10</strength><screen_edge_strength>20</screen_edge_strength></resistance>
  <focus><followMouse>no</followMouse><focusLast>yes</focusLast></focus>
  <placement><policy>UnderMouse</policy><center>yes</center></placement>
  <theme>
    <name>Clearlooks</name>
    <titleLayout>NLIMC</titleLayout>
    <keepBorder>no</keepBorder>
    <animateIconify>no</animateIconify>
  </theme>
  <desktops><number>1</number><firstdesk>1</firstdesk><names><name>Acervator</name></names></desktops>
  <resize><drawContents>yes</drawContents></resize>
  <keyboard>
    <!-- Alt+F4 to close (disabled in kiosk mode) -->
    <!-- Allow Ctrl+Alt+T for terminal if needed during setup -->
  </keyboard>
  <mouse><dragThreshold>1</dragThreshold><doubleClickTime>200</doubleClickTime></mouse>
  <margins><top>0</top><bottom>0</bottom><left>0</left><right>0</right></margins>
  <applications>
    <!-- Force Acervator to always be maximised with no decorations -->
    <application class="*" name="acervator">
      <maximized>yes</maximized>
      <fullscreen>yes</fullscreen>
      <decor>no</decor>
      <layer>normal</layer>
    </application>
    <application class="python3" name="python3">
      <maximized>yes</maximized>
      <decor>no</decor>
    </application>
  </applications>
</openbox_config>
OPENBOX_RC

# ── Openbox autostart ─────────────────────────────────────────────────────────
cat > "${HOME_DIR}/.config/openbox/autostart" << AUTOSTART
# AcervatorOS openbox autostart

# Hide cursor after 2 seconds of inactivity
unclutter -idle 2 -root &

# Set black background
xsetroot -solid black &

# Disable screen blanking and DPMS (don't want display to turn off during trading)
xset s off &
xset -dpms &
xset s noblank &

# Start Acervator (venv python, fullscreen)
${VENV_DIR}/bin/python3 ${INSTALL_DIR}/src/main.py &
AUTOSTART

# ── .xinitrc fallback (if LightDM not used) ──────────────────────────────────
cat > "${HOME_DIR}/.xinitrc" << XINITRC
#!/bin/bash
exec openbox-session
XINITRC

# ── .bash_profile auto-startx (if autologin via getty without LightDM) ────────
cat > "${HOME_DIR}/.bash_profile" << PROFILE
# AcervatorOS — auto-start display on tty1
[[ -z "\${DISPLAY}" && "\${XDG_VTNR}" -eq 1 ]] && exec startx
PROFILE

# ── Permissions ───────────────────────────────────────────────────────────────
chown -R "${ACERVATOR_USER}:${ACERVATOR_USER}" \
    "${HOME_DIR}/.config" \
    "${HOME_DIR}/.xinitrc" \
    "${HOME_DIR}/.bash_profile"

# ── Enable LightDM ────────────────────────────────────────────────────────────
systemctl enable lightdm 2>/dev/null || true

echo "  ✓ Display configured — fullscreen kiosk mode on next boot"
echo "  ✓ Auto-login: ${ACERVATOR_USER} → openbox → Acervator"
