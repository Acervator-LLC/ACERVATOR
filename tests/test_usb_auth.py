"""``usb_auth`` key derivation, auth-file round trip and volume enumeration.

``_list_usb_macos`` and ``_list_usb_linux`` must resolve ``diskutil`` and
``lsblk`` through ``shutil.which`` before spawning them, and each test that
asserts no spawn is paired with one proving the recorder sees a real spawn.
"""

from __future__ import annotations

import builtins
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.core import usb_auth

FAKE_SERIAL = "TESTSERIAL0001"
FAKE_EXCHANGE = "exchange-under-test"
# The (api_key, api_secret, passphrase) triple CredentialVault.retrieve returns.
FAKE_TRIPLE = ("placeholder-one", "placeholder-two", "")
FAKE_CREDENTIALS = [
    {
        "exchange_id": FAKE_EXCHANGE,
        "api_key": FAKE_TRIPLE[0],
        "api_secret": FAKE_TRIPLE[1],
        "passphrase": FAKE_TRIPLE[2],
    }
]


class SpawnRecorder:
    """Stands in for ``subprocess.run`` and records every argv it is handed."""

    def __init__(self) -> None:
        self.argvs: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.argvs.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")


def test_app_id_fingerprint_is_sixteen_hex_characters():
    fingerprint = usb_auth._app_id_fingerprint()
    assert len(fingerprint) == 16, fingerprint
    assert all(c in "0123456789abcdef" for c in fingerprint), fingerprint


def test_derive_usb_key_returns_key_len_bytes():
    key = usb_auth._derive_usb_key(FAKE_SERIAL, b"\x00" * usb_auth.SALT_LEN)
    assert len(key) == usb_auth.KEY_LEN, len(key)


def test_a_different_serial_derives_a_different_key():
    salt = b"\x01" * usb_auth.SALT_LEN
    first = usb_auth._derive_usb_key(FAKE_SERIAL, salt)
    second = usb_auth._derive_usb_key(FAKE_SERIAL + "X", salt)
    assert first != second


def test_fallback_encrypt_round_trips_through_fallback_decrypt():
    key = b"\x02" * usb_auth.KEY_LEN
    nonce = b"\x03" * usb_auth.NONCE_LEN
    blob = usb_auth._fallback_encrypt(key, nonce, b"payload-under-test")
    body = blob[usb_auth.NONCE_LEN :]
    assert usb_auth._fallback_decrypt(key, nonce, body) == b"payload-under-test"


def test_fallback_decrypt_rejects_a_flipped_ciphertext_byte():
    key = b"\x02" * usb_auth.KEY_LEN
    nonce = b"\x03" * usb_auth.NONCE_LEN
    blob = usb_auth._fallback_encrypt(key, nonce, b"payload-under-test")
    body = bytearray(blob[usb_auth.NONCE_LEN :])
    body[0] ^= 0xFF
    with pytest.raises(ValueError, match="Authentication tag"):
        usb_auth._fallback_decrypt(key, nonce, bytes(body))


def test_write_auth_file_lays_down_the_documented_header(tmp_path):
    written = usb_auth.write_auth_file(tmp_path, FAKE_SERIAL, FAKE_CREDENTIALS)
    data = written.read_bytes()
    assert data[:8] == usb_auth.MAGIC_HEADER
    assert data[8:12] == usb_auth.FILE_VERSION
    assert int.from_bytes(data[12:16], "little") == len(FAKE_CREDENTIALS)
    assert written.name == usb_auth.AUTH_FILENAME


def test_read_auth_file_returns_what_write_auth_file_stored(tmp_path):
    written = usb_auth.write_auth_file(tmp_path, FAKE_SERIAL, FAKE_CREDENTIALS)
    assert usb_auth.read_auth_file(written, FAKE_SERIAL) == FAKE_CREDENTIALS


def test_read_auth_file_raises_value_error_on_a_bad_magic_header(tmp_path):
    corrupt = tmp_path / usb_auth.AUTH_FILENAME
    corrupt.write_bytes(b"NOTACERV" + b"\x00" * 64)
    with pytest.raises(ValueError, match="magic header"):
        usb_auth.read_auth_file(corrupt, FAKE_SERIAL)


def test_verify_auth_file_returns_false_for_the_wrong_serial(tmp_path):
    written = usb_auth.write_auth_file(tmp_path, FAKE_SERIAL, FAKE_CREDENTIALS)
    assert usb_auth.verify_auth_file(written, FAKE_SERIAL) is True
    assert usb_auth.verify_auth_file(written, "OTHERSERIAL") is False


def test_list_usb_macos_spawns_nothing_when_diskutil_does_not_resolve(monkeypatch):
    recorder = SpawnRecorder()
    monkeypatch.setattr(usb_auth.subprocess, "run", recorder)
    monkeypatch.setattr(usb_auth.shutil, "which", lambda name: None)
    assert usb_auth._list_usb_macos() == []
    assert recorder.argvs == [], recorder.argvs


def test_list_usb_macos_spawns_the_resolved_diskutil_path(monkeypatch):
    recorder = SpawnRecorder()
    monkeypatch.setattr(usb_auth.subprocess, "run", recorder)
    monkeypatch.setattr(usb_auth.shutil, "which", lambda name: "/resolved/" + name)
    usb_auth._list_usb_macos()
    assert recorder.argvs, "recorder saw no spawn, so the empty case proves nothing"
    assert recorder.argvs[0][0] == "/resolved/diskutil", recorder.argvs


def _serve_a_removable_mount(monkeypatch, tmp_path):
    """Redirect the ``/proc/mounts`` read to a file naming one removable mount."""
    mounts = tmp_path / "mounts"
    mounts.write_text("/dev/sdz1 /media/stick vfat rw 0 0\n", encoding="utf-8")

    def fake_open(path, *args, **kwargs):
        target = mounts if path == "/proc/mounts" else path
        return builtins.open(target, *args, **kwargs)

    monkeypatch.setattr(usb_auth, "open", fake_open, raising=False)


def test_list_usb_linux_spawns_nothing_when_lsblk_does_not_resolve(
    monkeypatch, tmp_path
):
    recorder = SpawnRecorder()
    _serve_a_removable_mount(monkeypatch, tmp_path)
    monkeypatch.setattr(usb_auth.subprocess, "run", recorder)
    monkeypatch.setattr(usb_auth.shutil, "which", lambda name: None)
    assert usb_auth._list_usb_linux() == []
    assert recorder.argvs == [], recorder.argvs


def test_list_usb_linux_spawns_the_resolved_lsblk_path(monkeypatch, tmp_path):
    recorder = SpawnRecorder()
    _serve_a_removable_mount(monkeypatch, tmp_path)
    monkeypatch.setattr(usb_auth.subprocess, "run", recorder)
    monkeypatch.setattr(usb_auth.shutil, "which", lambda name: "/resolved/" + name)
    usb_auth._list_usb_linux()
    assert recorder.argvs, "recorder saw no spawn, so the empty case proves nothing"
    assert recorder.argvs[0][0] == "/resolved/lsblk", recorder.argvs


def test_export_credentials_to_usb_ignores_its_third_argument(tmp_path):
    class Vault:
        def list_exchanges(self):
            return [FAKE_EXCHANGE]

        def retrieve(self, _exchange):
            return FAKE_TRIPLE

    volume = usb_auth.USBVolume(
        mount_point=tmp_path, label="stick", serial=FAKE_SERIAL, size_gb=1.0
    )
    first = usb_auth.export_credentials_to_usb(volume, Vault(), "one")
    second = usb_auth.export_credentials_to_usb(volume, Vault(), "two")
    assert first[0] is True, first
    assert first == second, (first, second)
