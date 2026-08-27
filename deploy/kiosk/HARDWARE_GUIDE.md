# AcervatorOS — Hardware Guide

## Recommended Kit (Raspberry Pi 5 Appliance)

Everything needed to build a dedicated AcervatorOS trading appliance.
Total cost: approximately $120–$150 USD.

---

### Core Hardware

| Item | Recommended Model | Notes |
|------|------------------|-------|
| **Single-board computer** | Raspberry Pi 5 (8GB RAM) | 8GB is the minimum for PySide6 + live data. The 4GB model is borderline. |
| **Storage** | Samsung 128GB USB SSD (T7 or equivalent) | Do NOT use a standard SD card for a trading OS. SD cards have high write failure rates. A USB SSD at $20 is a different reliability class entirely. |
| **Power supply** | Official Raspberry Pi 27W USB-C PSU | Trading bots run 24/7. An inadequate PSU causes undervoltage throttling. Use the official one. |
| **Enclosure** | Argon ONE V3 (NVMe edition) or Pimoroni Acrylic Case | The Argon ONE provides passive cooling and a clean form factor. Optional but recommended for 24/7 use. |
| **Display** | Any HDMI monitor or TV (optional) | If running headless, no monitor needed — manage via VNC from another device. |
| **USB Hardware Key** | Any USB 3.0 flash drive 8GB+ | Used for Acervator USB hardware authentication. A SanDisk Ultra or Samsung is fine. The trading OS storage is on the SSD, not this drive. |

---

### Optional Additions

| Item | Purpose |
|------|---------|
| **UPS (Uninterruptible Power Supply)** | Prevents trading session interruption during power outages. The CyberPower CP425SLG ($40) supports the Pi 5 easily and provides ~30 min runtime. Strongly recommended. |
| **Ethernet cable** | Wired connection is more reliable than WiFi for exchange API calls. Use ethernet if the Pi is near your router. |
| **7" Raspberry Pi touchscreen** | Compact dedicated display. Requires Qt screen scaling adjustment (`QT_SCALE_FACTOR=1.5`). |
| **Pi 5 Active Cooler** | Keeps the CPU cool under sustained trading load. Official Raspberry Pi Active Cooler is $5. |

---

## Setup: Step by Step

### 1. Flash Raspberry Pi OS

Download and flash **Raspberry Pi OS Bookworm (64-bit, Lite)** to the USB SSD using Raspberry Pi Imager.

In Imager's advanced settings before flashing:
- ✅ Set hostname: `acervator`
- ✅ Set username: `pi` (temporary install account)
- ✅ Set password (for SSH access during setup)
- ✅ Enable SSH
- ✅ Configure your WiFi (or use ethernet)

**Important:** Flash to the USB SSD, not an SD card. In Raspberry Pi Imager, select the USB SSD as the storage target.

### 2. Boot and Connect

Connect the Pi to your monitor and keyboard, or SSH in:
```
ssh pi@acervator.local
```

### 3. Run the Installer

Copy the `acervator_v3_4_0.zip` to the Pi (via USB drive, SCP, or `wget`) and extract:

```bash
# Via SCP from your main computer:
scp acervator_v3_4_0.zip pi@acervator.local:~/

# On the Pi:
cd ~
unzip acervator_v3_4_0.zip
cd acervator

# See what the installer would do, without changing anything:
bash deploy/kiosk/install.sh --dry-run

# Then install for real:
sudo bash deploy/kiosk/install.sh
```

`--dry-run` needs no root and touches nothing. It prints every command
the installer would run, and ends with `DRY RUN finished`. If it stops
before that line, do not run the real install.

The installer will:
- Create the `acervator` system user
- Install Python 3.11 or later, and all dependencies
- Configure auto-login and fullscreen display
- Set up the firewall
- Enable the systemd service
- Configure NTP with multiple time sources

### 4. Reboot

```bash
sudo reboot
```

The Pi will boot directly into Acervator. First boot takes 30–60 seconds as the display server initialises. Subsequent boots are faster.

### 5. Insert USB Hardware Key

If you exported your API keys to a USB hardware key using Acervator's USB auth system, insert the USB drive before or after the first boot. Acervator will detect it automatically.

---

## Boot to Trading in 90 Seconds

After initial setup, the full boot sequence is:

```
Power on
  └─ ~10s  Bootloader + kernel
  └─ ~20s  systemd network + NTP sync
  └─ ~15s  Pre-flight checks (NTP verified, USB key detected)
  └─ ~15s  Acervator startup + exchange connection
  └─ ~5s   GUI appears, waiting for interaction
─────────────────────────────────────────────────────
Total: ~65–90 seconds from power-on to trading-ready
```

---

## Headless Operation (No Monitor)

Run the installer with `--headless`:

```bash
sudo bash deploy/kiosk/install.sh --headless
```

Then reach Acervator through an SSH tunnel. **Do not open port 5901.**
`deploy/kiosk/config/firewall.sh` sets a deny-by-default policy and permits
inbound SSH only, so a viewer pointed straight at `acervator.local:5901`
cannot connect. A VNC port reachable from a network also draws
continuous scanning, which is why the port stays shut.

On the Pi, bind the VNC server to the machine itself:

```bash
vncserver :1 -geometry 1920x1080 -localhost yes
```

From your own computer, build the tunnel, then point the viewer at
your own machine:

```bash
ssh -L 5901:localhost:5901 pi@acervator.local
# then connect TigerVNC Viewer or RealVNC Viewer to: localhost:5901
```

Use 1920 by 1080 or larger. The main window refuses to be smaller than
1400 by 900, so a smaller screen cuts it off.

Set a VNC password on first run:
```bash
sudo -u acervator vncpasswd
```

---

## Remote Management

### Check service status
```bash
ssh pi@acervator.local "systemctl status acervator"
```

### View live logs
```bash
ssh pi@acervator.local "journalctl -u acervator -f"
```

### Update Acervator remotely
```bash
# Copy new zip and update:
scp acervator_v3_4_0.zip pi@acervator.local:~/
ssh pi@acervator.local "sudo bash acervator/os/update.sh ~/acervator_v3_4_0.zip"
```

### Restart after settings change
```bash
ssh pi@acervator.local "sudo systemctl restart acervator"
```

---

## Firewall Details

AcervatorOS uses a strict default-deny firewall. The Pi can only communicate with:
- Exchange APIs (HTTPS/443 outbound)
- DNS servers (port 53)
- NTP time servers (port 123/udp)
- Your SSH session (port 22 inbound, for maintenance)

All other traffic is blocked. This means:
- No browser, no general internet access
- No inbound connections except SSH
- API keys cannot be exfiltrated by rogue processes

To see the active rules:
```bash
sudo ufw status verbose
```

---


---

## Mini Display Support

AcervatorOS can output trade alerts, bot state, price tickers, and status
messages to connected mini displays. I2C displays are auto-detected on boot.

### Supported Display Types

| Type | Model | Interface | Auto-detect | Color | Refresh |
|------|-------|-----------|-------------|-------|---------|
| OLED Mono | SSD1306 128×64 | I2C 0x3C/0x3D | ✅ | Mono | Fast |
| OLED Color | SSD1351 128×128 | SPI | Config | Color | Fast |
| TFT LCD | ST7789 / ILI9341 | SPI | Config | Color | Fast |
| Character LCD | HD44780 16×2 / 20×4 | I2C 0x27/0x3F | ✅ | None | Fast |
| e-Paper | WaveShare any size | SPI | Config | Mono/Grey | 2–30s |

### Message Compatibility

Some message types are excluded from certain displays by design:

| Message | OLED Mono | TFT Color | Char LCD | e-Paper |
|---------|-----------|-----------|----------|---------|
| Trade Alert | ✓ | ✓ | ✓ | ✓ |
| Bot State | ✓ | ✓ | ✓ | ✓ |
| Status Line | ✓ | ✓ | ✓ | ✓ |
| Price Ticker | ✓ | ✓ | ✓ | ✗ (e-ink wear) |
| Error | ✓ | ✓ | ✓ | ✓ |
| Chart Mini | ✓ | ✓ | ✗ (no pixels) | ✗ (e-ink wear) |
| Animation | ✗ | ✓ | ✗ | ✗ (too slow) |
| Rich Text | ✗ (mono) | ✓ | ✗ (ASCII only) | ✓ (stripped) |

### Quick Setup

**I2C displays (SSD1306, HD44780):** just plug in — detected automatically.

Enable I2C if not already on:
```bash
sudo raspi-config nonint do_i2c 0
```

**SPI displays (ST7789, e-Paper, SSD1351):** edit the config file:
```bash
sudo nano /home/acervator/.acervator/config/display-config.json
```
Set `"enabled": true` for the relevant display type and provide the model.

**Test detection:**
```bash
acervator-display-detect
```

**Install display libraries:**
```bash
# Auto-installed: luma.oled, RPLCD, smbus2, Pillow
# Manual for ST7789:    pip install st7789
# Manual for e-Paper:   see waveshare wiki
```

### Python Integration

```python
from src.core.mini_display import init_displays, MessageType

mgr = init_displays()          # detects and starts routing thread
mgr.notify_trade("SELL", "BTC", 0.001, 45000.0, 0.045)
mgr.notify_bot_state("TRADING", "BTC")
mgr.notify_price("ETH", 2500.0, +1.35)
mgr.notify_error("Exchange", "Rate limit hit")
```

## Troubleshooting

**Service won't start — NTP check failing**
```bash
chronyc tracking        # Check time sync status
chronyc sources -v      # Check time sources
sudo systemctl restart chrony
```

**Service won't start — USB key not found**
```bash
lsblk                   # List all block devices
# Look for your USB drive, check it appears
sudo -u acervator python3 -c "
import sys; sys.path.insert(0, '/opt/acervator/src')
from src.core.usb_auth import list_usb_volumes
for v in list_usb_volumes():
    print(v.label, v.serial, v.mount_point)
"
```

**Black screen on boot (display issue)**
```bash
# SSH in and check:
journalctl -u lightdm -n 50
journalctl -u acervator -n 50
```

**Update failed, service won't start after update**
```bash
# update.sh automatically rolls back, but if not:
ls /opt/acervator/backup_*    # Find the backup
sudo rsync -a /opt/acervator/backup_YYYYMMDD_HHMMSS/ /opt/acervator/src/
sudo systemctl start acervator
```

---

## Recommended UPS Configuration

If using a CyberPower or APC UPS with USB monitoring:

```bash
sudo apt-get install -y nut
# Configure NUT to gracefully shut down Acervator and the Pi
# on low battery rather than letting the power cut mid-trade
```

A graceful shutdown sequence:
1. NUT detects UPS battery < 20%
2. Systemd shuts down `acervator.service` cleanly (saves state)
3. Pi shuts down
4. UPS cuts power

This ensures no partial trades are left open.

---

*AcervatorOS — Visual, Tactical, Direction-Agnostic*
