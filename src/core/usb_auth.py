"""USB hardware key for exchange credentials.

``write_auth_file`` encrypts a credential list under a ``_derive_usb_key`` key
and writes ``AUTH_FILENAME`` at a USB mount point. The layout is
``MAGIC_HEADER``, ``FILE_VERSION``, a little-endian exchange count, a
``SALT_LEN`` salt, then ``_aes_gcm_encrypt`` output carrying its own nonce.
``find_auth_volume`` matches the volume serial ``read_auth_file`` needs to
derive the same key.
"""

from __future__ import annotations

import logging

import hashlib
import hmac
import json
import os
import platform
import re
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("acervator.usb_auth")

MAGIC_HEADER = b"ACERVKEY"
FILE_VERSION = b"\x00\x01\x00\x00"
AUTH_FILENAME = ".acervator_auth"
PBKDF2_ITERS = 260_000
SALT_LEN = 32
NONCE_LEN = 12
KEY_LEN = 32  # AES-256

# A source constant, not a user secret; _derive_usb_key prefixes it to the serial.
_APP_HMAC_SECRET = (
    b"Acervator\x00HarvestFold\x00EktheliusTheAccumulator"
    b"\x00VersionOnePointZero\x00USB\x00AUTH\x00KEY"
)


def _derive_usb_key(volume_serial: str, salt: bytes) -> bytes:
    """Return a ``KEY_LEN`` byte key over ``_APP_HMAC_SECRET`` and *volume_serial*.

    Derivation is PBKDF2-HMAC-SHA256 at ``PBKDF2_ITERS`` rounds against *salt*.
    """
    password = _APP_HMAC_SECRET + volume_serial.encode("utf-8")
    return hashlib.pbkdf2_hmac(
        "sha256",
        password,
        salt,
        PBKDF2_ITERS,
        dklen=KEY_LEN,
    )


def _app_id_fingerprint() -> str:
    """Return the first 16 hex characters of the ``_APP_HMAC_SECRET`` digest."""
    return hashlib.sha256(_APP_HMAC_SECRET).hexdigest()[:16]


def _aes_gcm_encrypt(key: bytes, nonce: bytes, plaintext: bytes) -> bytes:
    """Return *nonce* joined to ``AESGCM`` ciphertext and its 16-byte tag.

    Falls back to ``_fallback_encrypt`` when ``cryptography`` is not installed.
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aes = AESGCM(key)
        return nonce + aes.encrypt(nonce, plaintext, None)
    except ImportError:
        return _fallback_encrypt(key, nonce, plaintext)


def _aes_gcm_decrypt(key: bytes, data: bytes) -> bytes:
    """Decrypt data produced by _aes_gcm_encrypt."""
    nonce = data[:NONCE_LEN]
    ct = data[NONCE_LEN:]
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        return AESGCM(key).decrypt(nonce, ct, None)
    except ImportError:
        return _fallback_decrypt(key, nonce, ct)


def _fallback_encrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
    """XOR *data* against the ``_kdf_stream`` keystream, no cipher involved.

    Appends a 32-byte HMAC-SHA256 tag computed over *nonce* and the ciphertext.
    """
    from hashlib import sha256

    stream = _kdf_stream(key, nonce, len(data))
    ct = bytes(a ^ b for a, b in zip(data, stream))
    tag = hmac.new(key, nonce + ct, sha256).digest()
    return nonce + ct + tag


def _fallback_decrypt(key: bytes, nonce: bytes, ct_and_tag: bytes) -> bytes:
    """Check the trailing HMAC-SHA256 tag, then XOR against ``_kdf_stream``.

    Raises ``ValueError`` when ``hmac.compare_digest`` rejects the tag.
    """
    from hashlib import sha256

    ct = ct_and_tag[:-32]
    tag = ct_and_tag[-32:]
    expected = hmac.new(key, nonce + ct, sha256).digest()
    if not hmac.compare_digest(expected, tag):
        raise ValueError(
            "Authentication tag mismatch — file may be corrupted or tampered."
        )
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


DISKUTIL_PATHS = ("/usr/sbin/diskutil",)
LSBLK_PATHS = ("/usr/bin/lsblk", "/bin/lsblk")

_MACOS_DEVICE_IDENTIFIER = re.compile(r"^disk[0-9]+(?:s[0-9]+)*$")
_LINUX_DEVICE_NODE = re.compile(r"^/dev/[A-Za-z0-9][A-Za-z0-9._+/-]*$")


def _resolve_tool(name: str, known_paths: tuple[str, ...]) -> Optional[str]:
    """Return the first of ``known_paths`` that is a file, else the ``shutil.which`` result.

    A ``shutil.which`` result logs at WARNING and names *name*.
    """
    for candidate in known_paths:
        if Path(candidate).is_file():
            return candidate
    found = shutil.which(name)
    if found:
        logger.warning(
            "%s is not at %s; using %s from the search path, which this module "
            "does not control",
            name,
            " or ".join(known_paths),
            found,
        )
    return found


def _is_macos_device_identifier(value: str) -> bool:
    """Report whether *value* matches a diskutil identifier such as ``disk2s1``."""
    return bool(_MACOS_DEVICE_IDENTIFIER.match(value))


def _is_linux_device_node(value: str) -> bool:
    """Report whether *value* names a /dev node and cannot be read as an lsblk option."""
    return bool(_LINUX_DEVICE_NODE.match(value))


@dataclass
class USBVolume:
    """One removable volume, with ``auth_file`` set when ``AUTH_FILENAME`` is there."""

    mount_point: Path
    label: str
    # Windows volume serial hex, macOS VolumeUUID, or the Linux lsblk SERIAL.
    serial: str
    size_gb: float
    auth_file: Optional[Path] = field(default=None)

    @property
    def has_auth_file(self) -> bool:
        return self.auth_file is not None and self.auth_file.exists()


def list_usb_volumes() -> list[USBVolume]:
    """Return a ``USBVolume`` per removable drive found by the platform helper.

    ``_list_usb_windows``, ``_list_usb_macos`` and ``_list_usb_linux`` supply the
    volumes, and each gets ``auth_file`` set where ``AUTH_FILENAME`` exists.
    """
    system = platform.system()
    volumes = []

    if system == "Windows":
        volumes = _list_usb_windows()
    elif system == "Darwin":
        volumes = _list_usb_macos()
    else:
        volumes = _list_usb_linux()

    for vol in volumes:
        candidate = vol.mount_point / AUTH_FILENAME
        if candidate.exists():
            vol.auth_file = candidate

    return volumes


def _list_usb_windows() -> list[USBVolume]:
    """Enumerate removable drives on Windows using ctypes."""
    import ctypes
    import ctypes.wintypes as wt

    GetLogicalDrives = ctypes.windll.kernel32.GetLogicalDriveStringsW
    GetDriveType = ctypes.windll.kernel32.GetDriveTypeW
    GetVolumeInfo = ctypes.windll.kernel32.GetVolumeInformationW
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

        label_buf = ctypes.create_unicode_buffer(256)
        serial_buf = wt.DWORD(0)
        fs_buf = ctypes.create_unicode_buffer(256)
        GetVolumeInfo(
            drive, label_buf, 256, ctypes.byref(serial_buf), None, None, fs_buf, 256
        )

        free_bytes = wt.ULARGE_INTEGER(0)
        total_bytes = wt.ULARGE_INTEGER(0)
        GetDiskFreeSpaceEx(
            drive, ctypes.byref(free_bytes), ctypes.byref(total_bytes), None
        )
        size_gb = total_bytes.value / (1024**3)
        serial = f"{serial_buf.value:08X}"

        volumes.append(
            USBVolume(
                mount_point=Path(drive),
                label=label_buf.value or "USB Drive",
                serial=serial,
                size_gb=round(size_gb, 1),
            )
        )
    return volumes


def _list_usb_macos() -> list[USBVolume]:
    """Enumerate removable drives on macOS using ``diskutil``.

    Returns an empty list where ``_resolve_tool`` cannot resolve ``diskutil``.
    """
    volumes: list[USBVolume] = []
    diskutil = _resolve_tool("diskutil", DISKUTIL_PATHS)
    if not diskutil:
        return volumes
    try:
        result = subprocess.run(
            [diskutil, "list", "-plist", "external"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        import plistlib

        data = plistlib.loads(result.stdout.encode())
        for disk in data.get("AllDisksAndPartitions", []):
            for part in disk.get("Partitions", []):
                mp = part.get("MountPoint", "")
                if not mp:
                    continue
                name = part.get("VolumeName", "USB Drive")
                identifier = part.get("DeviceIdentifier", "")
                info_data: dict = {}
                if _is_macos_device_identifier(identifier):
                    info = subprocess.run(
                        [diskutil, "info", "-plist", identifier],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    info_data = (
                        plistlib.loads(info.stdout.encode()) if info.stdout else {}
                    )
                else:
                    logger.error(
                        "diskutil named %r as the device identifier for %s, which is "
                        "not a disk identifier; diskutil info is not asked about it "
                        "and serial reads UNKNOWN, so find_auth_volume cannot match "
                        "this volume",
                        identifier,
                        mp,
                    )
                serial = info_data.get("VolumeUUID", "UNKNOWN")
                size_gb = part.get("Size", 0) / (1024**3)
                volumes.append(
                    USBVolume(
                        mount_point=Path(mp),
                        label=name,
                        serial=serial,
                        size_gb=round(size_gb, 1),
                    )
                )
    except Exception as _sf_exc:  # noqa: BLE001
        logger.warning(
            "macOS USB volume enumeration failed — no drives will be offered for auth: %s",
            _sf_exc,
        )
    return volumes


def _list_usb_linux() -> list[USBVolume]:
    """Enumerate ``/proc/mounts`` entries under /media or /mnt on Linux.

    ``lsblk`` supplies the removable flag for a device ``_is_linux_device_node``
    accepts, and an unresolved ``lsblk`` yields an empty list.
    """
    volumes: list[USBVolume] = []
    lsblk = _resolve_tool("lsblk", LSBLK_PATHS)
    if not lsblk:
        return volumes
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            mounts = f.readlines()

        for line in mounts:
            parts = line.split()
            if len(parts) < 2:
                continue
            device, mount = parts[0], parts[1]
            if not mount.startswith("/media") and not mount.startswith("/mnt"):
                continue
            if not _is_linux_device_node(device):
                logger.error(
                    "/proc/mounts names %r mounted at %s, which is not a /dev node; "
                    "lsblk is not asked about it, so the removable flag is unchecked "
                    "and serial falls back to the name",
                    device,
                    mount,
                )
                serial, label, size_gb = device.split("/")[-1], "USB Drive", 0.0
            else:
                try:
                    info = subprocess.run(
                        [lsblk, "-no", "RM,SIZE,LABEL,SERIAL", device],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    cols = info.stdout.strip().split()
                    if not cols or cols[0] != "1":
                        continue
                    size_str = cols[1] if len(cols) > 1 else "0G"
                    size_gb = float(size_str.rstrip("GgMm")) if size_str else 0.0
                    label = cols[2] if len(cols) > 2 else "USB Drive"
                    serial = cols[3] if len(cols) > 3 else device.split("/")[-1]
                except Exception:
                    serial, label, size_gb = device.split("/")[-1], "USB Drive", 0.0

            volumes.append(
                USBVolume(
                    mount_point=Path(mount),
                    label=label,
                    serial=serial,
                    size_gb=round(size_gb, 1),
                )
            )
    except Exception as _sf_exc:  # noqa: BLE001
        logger.error(
            "/proc/mounts could NOT be read (%s: %s) — no drives are offered "
            "for auth, which is not the same as no drive being plugged in",
            type(_sf_exc).__name__,
            _sf_exc,
        )
    return volumes


def find_auth_volume(volume_serial: str) -> Optional[USBVolume]:
    """Return the ``list_usb_volumes`` entry whose ``serial`` matches.

    ``has_auth_file`` must also be true, which tests only that the file exists.
    """
    for vol in list_usb_volumes():
        if vol.serial == volume_serial and vol.has_auth_file:
            return vol
    return None


def write_auth_file(
    usb_path: Path,
    volume_serial: str,
    credentials: list[dict],
) -> Path:
    """Encrypt *credentials* under ``_derive_usb_key`` and write ``AUTH_FILENAME``.

    Each dict carries ``exchange_id``, ``api_key``, ``api_secret`` and
    ``passphrase``, and the written path under *usb_path* is returned.
    """
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = _derive_usb_key(volume_serial, salt)

    payload = json.dumps(
        {
            "version": 1,
            "app_id": _app_id_fingerprint(),
            "exchanges": credentials,
        }
    ).encode("utf-8")

    ct = _aes_gcm_encrypt(key, nonce, payload)

    count_bytes = struct.pack("<I", len(credentials))
    file_data = MAGIC_HEADER + FILE_VERSION + count_bytes + salt + ct

    out_path = usb_path / AUTH_FILENAME
    out_path.write_bytes(file_data)
    return out_path


def read_auth_file(auth_file: Path, volume_serial: str) -> list[dict]:
    """Decrypt an ``AUTH_FILENAME`` file and return its ``exchanges`` list.

    ``ValueError`` marks a bad ``MAGIC_HEADER`` or an ``_app_id_fingerprint``
    mismatch, while a wrong key surfaces as whatever ``_aes_gcm_decrypt`` raises.
    """
    data = auth_file.read_bytes()

    if data[:8] != MAGIC_HEADER:
        raise ValueError("Not a valid Acervator auth file (bad magic header).")
    # Bytes 8:16 hold FILE_VERSION and the exchange count; neither is read back.
    salt = data[16 : 16 + SALT_LEN]
    ct = data[16 + SALT_LEN :]

    key = _derive_usb_key(volume_serial, salt)
    payload = _aes_gcm_decrypt(key, ct)

    parsed = json.loads(payload.decode("utf-8"))
    if parsed.get("app_id") != _app_id_fingerprint():
        raise ValueError("Auth file was created by a different Acervator installation.")

    return parsed["exchanges"]


def verify_auth_file(auth_file: Path, volume_serial: str) -> bool:
    """Return True when ``read_auth_file`` yields at least one exchange.

    Every exception is caught and reported as False.
    """
    try:
        creds = read_auth_file(auth_file, volume_serial)
        return len(creds) > 0
    except Exception:
        return False


def export_credentials_to_usb(
    usb_volume: USBVolume,
    vault,  # encryption.CredentialVault
    _passphrase: str,  # unused; vault decrypts with the one it was built with
) -> tuple[bool, str]:
    """Write every ``vault.retrieve`` result to ``write_auth_file``.

    ``vault.list_exchanges`` selects the entries and ``verify_auth_file``
    confirms the written file.
    """
    try:
        exchange_ids = vault.list_exchanges()
        if not exchange_ids:
            return False, "No exchange credentials found to export."

        creds = []
        for eid in exchange_ids:
            try:
                api_key, api_secret, api_pass = vault.retrieve(eid)
                creds.append(
                    {
                        "exchange_id": eid,
                        "api_key": api_key,
                        "api_secret": api_secret,
                        "passphrase": api_pass or "",
                    }
                )
            except Exception as e:
                return False, f"Failed to decrypt credentials for {eid}: {e}"

        auth_path = write_auth_file(usb_volume.mount_point, usb_volume.serial, creds)

        if not verify_auth_file(auth_path, usb_volume.serial):
            return False, "Export written but verification failed. Try again."

        return True, (
            f"Exported {len(creds)} exchange(s) to USB "
            f"({usb_volume.label}, serial {usb_volume.serial}). "
            f"Verification passed. You may now enable hardware mode."
        )

    except PermissionError:
        return (
            False,
            "Permission denied writing to USB. Check drive is not write-protected.",
        )
    except OSError as e:
        return False, f"Write error: {e}"
    except Exception as e:
        return False, f"Export failed: {e}"


def import_credentials_from_usb(
    volume_serial: str,
) -> tuple[bool, list[dict], str]:
    """Return the ``read_auth_file`` credentials for the ``find_auth_volume`` match.

    A missing volume returns ``(False, [], message)`` and nothing raises.
    """
    vol = find_auth_volume(volume_serial)
    if vol is None:
        return (
            False,
            [],
            (
                "Hardware key not found. Insert the USB drive associated with "
                f"serial {volume_serial} to access this exchange."
            ),
        )

    try:
        creds = read_auth_file(vol.auth_file, volume_serial)
        return True, creds, f"Hardware key authenticated ({vol.label})."
    except ValueError as e:
        return False, [], f"Hardware key authentication failed: {e}"
    except Exception as e:
        return False, [], f"Error reading hardware key: {e}"
