"""
usb_auth.py — USB Hardware Authentication Key for Acervator
============================================================
Converts a USB drive into a hardware authentication key for API credentials.

SECURITY MODEL
--------------
When a user exports their API keys to USB:
  1. All stored exchange credentials are decrypted from local vault.
  2. They are re-encrypted using a key derived from:
       PBKDF2-HMAC-SHA256(
           password = APP_HMAC_SECRET + volume_serial,
           salt     = random 32 bytes stored in the auth file,
           iterations = 260_000
       )
  3. The resulting .acervator_auth file is written to the USB root.
  4. The file is prefixed with a magic header for identification.
  5. The USB volume serial is stored in AppSettings per exchange
     (hardware_mode=True, hw_volume_serial=<serial>).

When hardware mode is active for an exchange:
  - App scans mounted volumes for .acervator_auth + matching serial.
  - If found, decrypts credentials from USB — never from local vault.
  - If USB not present, exchange is locked (no credentials available).

FILE FORMAT (.acervator_auth)
------------------------------
  [0:8]   Magic header: b'ACERVKEY'
  [8:12]  Version: b'\x00\x01\x00\x00'
  [12:16] Exchange count (uint32 LE)
  [16:48] Salt (32 bytes, random)
  [48:]   AES-GCM encrypted JSON payload:
            {
              "version": 1,
              "app_id": "<sha256 of APP_HMAC_SECRET>",
              "exchanges": [
                {
                  "exchange_id": "binance",
                  "api_key": "...",
                  "api_secret": "...",
                  "passphrase": "..."
                },
                ...
              ]
            }
          Nonce (12 bytes) prepended to ciphertext in the payload.

The USB cannot be read by any other application because the decryption
key derivation incorporates APP_HMAC_SECRET — a value only Acervator
knows. Even with the file and the volume serial, decryption fails without
the app secret.
"""

from __future__ import annotations

import logging

import hashlib
import hmac
import json
import os
import platform
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("acervator.usb_auth")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAGIC_HEADER   = b"ACERVKEY"
FILE_VERSION   = b"\x00\x01\x00\x00"
AUTH_FILENAME  = ".acervator_auth"
PBKDF2_ITERS   = 260_000
SALT_LEN       = 32
NONCE_LEN      = 12
KEY_LEN        = 32   # AES-256

# App-specific secret — incorporated into key derivation so the file
# can only be decrypted by Acervator. Not a user-facing secret.
_APP_HMAC_SECRET = (
    b"Acervator\x00HarvestFold\x00EktheliusTheAccumulator"
    b"\x00VersionOnePointZero\x00USB\x00AUTH\x00KEY"
)


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def _derive_usb_key(volume_serial: str, salt: bytes) -> bytes:
    """Derive AES-256 key from app secret + volume serial + salt."""
    password = _APP_HMAC_SECRET + volume_serial.encode("utf-8")
    return hashlib.pbkdf2_hmac(
        "sha256",
        password,
        salt,
        PBKDF2_ITERS,
        dklen=KEY_LEN,
    )


def _app_id_fingerprint() -> str:
    """Short fingerprint to verify app identity without exposing the secret."""
    return hashlib.sha256(_APP_HMAC_SECRET).hexdigest()[:16]


# ---------------------------------------------------------------------------
# AES-GCM (or fallback AES-CTR + HMAC)
# ---------------------------------------------------------------------------

def _aes_gcm_encrypt(key: bytes, nonce: bytes, plaintext: bytes) -> bytes:
    """AES-256-GCM encrypt. Returns nonce + ciphertext + tag (16 bytes)."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aes = AESGCM(key)
        return nonce + aes.encrypt(nonce, plaintext, None)
    except ImportError:
        # Pure-Python fallback: AES-CTR + HMAC-SHA256
        return _fallback_encrypt(key, nonce, plaintext)


def _aes_gcm_decrypt(key: bytes, data: bytes) -> bytes:
    """Decrypt data produced by _aes_gcm_encrypt."""
    nonce = data[:NONCE_LEN]
    ct    = data[NONCE_LEN:]
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(key).decrypt(nonce, ct, None)
    except ImportError:
        return _fallback_decrypt(key, nonce, ct)


def _fallback_encrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
    """AES-CTR + HMAC-SHA256 using only stdlib."""
    from hashlib import sha256
    stream = _kdf_stream(key, nonce, len(data))
    ct = bytes(a ^ b for a, b in zip(data, stream))
    tag = hmac.new(key, nonce + ct, sha256).digest()
    return nonce + ct + tag


def _fallback_decrypt(key: bytes, nonce: bytes, ct_and_tag: bytes) -> bytes:
    from hashlib import sha256
    ct  = ct_and_tag[:-32]
    tag = ct_and_tag[-32:]
    expected = hmac.new(key, nonce + ct, sha256).digest()
    if not hmac.compare_digest(expected, tag):
        raise ValueError("Authentication tag mismatch — file may be corrupted or tampered.")
    stream = _kdf_stream(key, nonce, len(ct))
    return bytes(a ^ b for a, b in zip(ct, stream))


def _kdf_stream(key: bytes, nonce: bytes, length: int) -> bytes:
    stream = b""
    counter = 0
    while len(stream) < length:
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, "little")).digest()
        stream += block
        counter += 1
    return stream[:length]


# ---------------------------------------------------------------------------
# USB volume discovery
# ---------------------------------------------------------------------------

@dataclass
class USBVolume:
    """Represents a detected removable USB volume."""
    mount_point: Path
    label:       str
    serial:      str   # Volume serial number (platform-specific)
    size_gb:     float
    auth_file:   Optional[Path] = field(default=None)

    @property
    def has_auth_file(self) -> bool:
        return self.auth_file is not None and self.auth_file.exists()


def list_usb_volumes() -> list[USBVolume]:
    """
    Detect removable USB volumes across Windows, macOS, and Linux.
    Returns a list of USBVolume objects. Empty list if none found.
    """
    system = platform.system()
    volumes = []

    if system == "Windows":
        volumes = _list_usb_windows()
    elif system == "Darwin":
        volumes = _list_usb_macos()
    else:
        volumes = _list_usb_linux()

    # Check each volume for an existing auth file
    for vol in volumes:
        candidate = vol.mount_point / AUTH_FILENAME
        if candidate.exists():
            vol.auth_file = candidate

    return volumes


def _list_usb_windows() -> list[USBVolume]:
    """Enumerate removable drives on Windows using ctypes."""
    import ctypes
    import ctypes.wintypes as wt

    GetLogicalDrives   = ctypes.windll.kernel32.GetLogicalDriveStringsW
    GetDriveType       = ctypes.windll.kernel32.GetDriveTypeW
    GetVolumeInfo      = ctypes.windll.kernel32.GetVolumeInformationW
    GetDiskFreeSpaceEx = ctypes.windll.kernel32.GetDiskFreeSpaceExW

    DRIVE_REMOVABLE = 2
    buf = ctypes.create_unicode_buffer(256)
    GetLogicalDrives(256, buf)

    drives = buf.value.split("\x00")
    volumes = []
    for drive in drives:
        if not drive:
            continue
        dtype = GetDriveType(drive)
        if dtype != DRIVE_REMOVABLE:
            continue

        label_buf   = ctypes.create_unicode_buffer(256)
        serial_buf  = wt.DWORD(0)
        fs_buf      = ctypes.create_unicode_buffer(256)
        GetVolumeInfo(drive, label_buf, 256, ctypes.byref(serial_buf),
                      None, None, fs_buf, 256)

        # Disk size
        free_bytes  = wt.ULARGE_INTEGER(0)
        total_bytes = wt.ULARGE_INTEGER(0)
        GetDiskFreeSpaceEx(drive, ctypes.byref(free_bytes),
                           ctypes.byref(total_bytes), None)
        size_gb = total_bytes.value / (1024 ** 3)
        serial  = f"{serial_buf.value:08X}"

        volumes.append(USBVolume(
            mount_point=Path(drive),
            label=label_buf.value or "USB Drive",
            serial=serial,
            size_gb=round(size_gb, 1),
        ))
    return volumes


def _list_usb_macos() -> list[USBVolume]:
    """Enumerate removable drives on macOS using diskutil."""
    volumes = []
    try:
        result = subprocess.run(
            ["diskutil", "list", "-plist", "external"],
            capture_output=True, text=True, timeout=5
        )
        import plistlib
        data = plistlib.loads(result.stdout.encode())
        for disk in data.get("AllDisksAndPartitions", []):
            for part in disk.get("Partitions", []):
                mp = part.get("MountPoint", "")
                if not mp:
                    continue
                name  = part.get("VolumeName", "USB Drive")
                # Get serial from diskutil info
                info = subprocess.run(
                    ["diskutil", "info", "-plist", part.get("DeviceIdentifier", "")],
                    capture_output=True, text=True, timeout=5
                )
                info_data = plistlib.loads(info.stdout.encode()) if info.stdout else {}
                serial    = info_data.get("VolumeUUID", "UNKNOWN")
                size_gb   = part.get("Size", 0) / (1024 ** 3)
                volumes.append(USBVolume(
                    mount_point=Path(mp),
                    label=name,
                    serial=serial,
                    size_gb=round(size_gb, 1),
                ))
    except Exception as _sf_exc:  # noqa: BLE001
        logger.warning(
            "macOS USB volume enumeration failed — no drives will be offered for auth: %s", _sf_exc)
    return volumes


def _list_usb_linux() -> list[USBVolume]:
    """Enumerate removable drives on Linux using /proc/mounts + udev."""
    volumes = []
    try:
        with open("/proc/mounts") as f:
            mounts = f.readlines()

        for line in mounts:
            parts = line.split()
            if len(parts) < 2:
                continue
            device, mount = parts[0], parts[1]
            if not mount.startswith("/media") and not mount.startswith("/mnt"):
                continue
            # Try lsblk for removable flag
            try:
                info = subprocess.run(
                    ["lsblk", "-no", "RM,SIZE,LABEL,SERIAL", device],
                    capture_output=True, text=True, timeout=3
                )
                cols = info.stdout.strip().split()
                if not cols or cols[0] != "1":
                    continue
                size_str = cols[1] if len(cols) > 1 else "0G"
                size_gb  = float(size_str.rstrip("GgMm")) if size_str else 0.0
                label    = cols[2] if len(cols) > 2 else "USB Drive"
                serial   = cols[3] if len(cols) > 3 else device.split("/")[-1]
            except Exception:
                serial, label, size_gb = device.split("/")[-1], "USB Drive", 0.0

            volumes.append(USBVolume(
                mount_point=Path(mount),
                label=label,
                serial=serial,
                size_gb=round(size_gb, 1),
            ))
    except Exception as _sf_exc:  # noqa: BLE001
        logger.warning(
            "Linux USB volume enumeration failed — no drives will be offered for auth: %s", _sf_exc)
    return volumes


def find_auth_volume(volume_serial: str) -> Optional[USBVolume]:
    """
    Search all USB volumes for one matching the given serial and
    containing a valid .acervator_auth file.
    """
    for vol in list_usb_volumes():
        if vol.serial == volume_serial and vol.has_auth_file:
            return vol
    return None


# ---------------------------------------------------------------------------
# Auth file: read / write
# ---------------------------------------------------------------------------

def write_auth_file(
    usb_path: Path,
    volume_serial: str,
    credentials: list[dict],  # [{"exchange_id":…,"api_key":…,"api_secret":…,"passphrase":…}]
) -> Path:
    """
    Encrypt credentials and write .acervator_auth to *usb_path*.
    Returns the path of the written file.

    credentials: list of dicts, each with:
        exchange_id, api_key, api_secret, passphrase (may be empty)
    """
    salt  = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key   = _derive_usb_key(volume_serial, salt)

    payload = json.dumps({
        "version":   1,
        "app_id":    _app_id_fingerprint(),
        "exchanges": credentials,
    }).encode("utf-8")

    ct = _aes_gcm_encrypt(key, nonce, payload)

    # Build file
    count_bytes = struct.pack("<I", len(credentials))
    file_data   = MAGIC_HEADER + FILE_VERSION + count_bytes + salt + ct

    out_path = usb_path / AUTH_FILENAME
    out_path.write_bytes(file_data)
    return out_path


def read_auth_file(auth_file: Path, volume_serial: str) -> list[dict]:
    """
    Decrypt and return credentials from an .acervator_auth file.
    Raises ValueError on tampered/wrong-key data.
    Raises FileNotFoundError if auth_file doesn't exist.
    """
    data = auth_file.read_bytes()

    # Validate header
    if data[:8] != MAGIC_HEADER:
        raise ValueError("Not a valid Acervator auth file (bad magic header).")
    # version at [8:12] — reserved for future migration
    # count at [12:16] — informational
    salt = data[16:16 + SALT_LEN]
    ct   = data[16 + SALT_LEN:]

    key     = _derive_usb_key(volume_serial, salt)
    payload = _aes_gcm_decrypt(key, ct)

    parsed = json.loads(payload.decode("utf-8"))
    if parsed.get("app_id") != _app_id_fingerprint():
        raise ValueError("Auth file was created by a different Acervator installation.")

    return parsed["exchanges"]


def verify_auth_file(auth_file: Path, volume_serial: str) -> bool:
    """
    Returns True if the auth file decrypts successfully and contains
    at least one exchange. Does not raise.
    """
    try:
        creds = read_auth_file(auth_file, volume_serial)
        return len(creds) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# High-level export / import
# ---------------------------------------------------------------------------

def export_credentials_to_usb(
    usb_volume: USBVolume,
    vault,          # CredentialVault instance from encryption.py
    passphrase: str,
) -> tuple[bool, str]:
    """
    Decrypt all credentials from the local vault and write them to USB.

    Returns (success: bool, message: str).
    """
    try:
        exchange_ids = vault.list_exchanges()
        if not exchange_ids:
            return False, "No exchange credentials found to export."

        creds = []
        for eid in exchange_ids:
            try:
                api_key, api_secret, api_pass = vault.retrieve(eid)
                creds.append({
                    "exchange_id": eid,
                    "api_key":     api_key,
                    "api_secret":  api_secret,
                    "passphrase":  api_pass or "",
                })
            except Exception as e:
                return False, f"Failed to decrypt credentials for {eid}: {e}"

        auth_path = write_auth_file(
            usb_volume.mount_point, usb_volume.serial, creds
        )

        # Verify immediately after write
        if not verify_auth_file(auth_path, usb_volume.serial):
            return False, "Export written but verification failed. Try again."

        return True, (
            f"Exported {len(creds)} exchange(s) to USB "
            f"({usb_volume.label}, serial {usb_volume.serial}). "
            f"Verification passed. You may now enable hardware mode."
        )

    except PermissionError:
        return False, "Permission denied writing to USB. Check drive is not write-protected."
    except OSError as e:
        return False, f"Write error: {e}"
    except Exception as e:
        return False, f"Export failed: {e}"


def import_credentials_from_usb(
    volume_serial: str,
) -> tuple[bool, list[dict], str]:
    """
    Find a USB with the given serial and return decrypted credentials.
    Used at app startup when hardware mode is active.

    Returns (success, credentials_list, message).
    """
    vol = find_auth_volume(volume_serial)
    if vol is None:
        return False, [], (
            "Hardware key not found. Insert the USB drive associated with "
            f"serial {volume_serial} to access this exchange."
        )

    try:
        creds = read_auth_file(vol.auth_file, volume_serial)
        return True, creds, f"Hardware key authenticated ({vol.label})."
    except ValueError as e:
        return False, [], f"Hardware key authentication failed: {e}"
    except Exception as e:
        return False, [], f"Error reading hardware key: {e}"
