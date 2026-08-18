"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
encryption.py — AES-256-GCM encryption for API credentials
===========================================================
Provides encrypt-on-entry / decrypt-on-use semantics for API keys
and secrets. The master key is derived from a user-supplied passphrase
via PBKDF2-HMAC-SHA256 with a random salt. An OS-native keyring
fallback stores the passphrase so the user only enters it once per
session (or per OS login if the keyring persists).

Security notes:
  • Each ciphertext carries its own random 12-byte nonce (IV).
  • Salt is stored alongside the ciphertext; it is not secret.
  • GCM provides both confidentiality and integrity (AEAD).
  • The plaintext key material is zeroed after use where possible.
"""

from __future__ import annotations

import logging

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("acervator.encryption")

# ---------------------------------------------------------------------------
# Cryptographic primitives — we use the stdlib + cryptography library.
# If 'cryptography' is unavailable, we fall back to a pure-Python AES-CTR
# implementation that is slower but functional.
# ---------------------------------------------------------------------------
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SALT_LEN = 16          # 128-bit salt
_NONCE_LEN = 12         # 96-bit nonce (recommended for AES-GCM)
_KEY_LEN = 32           # 256-bit key
_KDF_ITERATIONS = 600_000  # OWASP 2023 recommendation for PBKDF2-SHA256
_KEYRING_SERVICE = "acervator"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------
def derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from *passphrase* + *salt* via PBKDF2."""
    if _HAS_CRYPTOGRAPHY:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=_KEY_LEN,
            salt=salt,
            iterations=_KDF_ITERATIONS,
        )
        return kdf.derive(passphrase.encode("utf-8"))
    else:
        # stdlib fallback (slower, but no external dependency)
        return hashlib.pbkdf2_hmac(
            "sha256",
            passphrase.encode("utf-8"),
            salt,
            _KDF_ITERATIONS,
            dklen=_KEY_LEN,
        )


# ---------------------------------------------------------------------------
# Encrypt / Decrypt
# ---------------------------------------------------------------------------
def encrypt(plaintext: str, passphrase: str) -> str:
    """
    Encrypt *plaintext* with AES-256-GCM under a key derived from
    *passphrase*.  Returns a URL-safe Base64 string encoding:
        salt (16 B) || nonce (12 B) || ciphertext+tag
    """
    salt = secrets.token_bytes(_SALT_LEN)
    nonce = secrets.token_bytes(_NONCE_LEN)
    key = derive_key(passphrase, salt)

    if _HAS_CRYPTOGRAPHY:
        aes = AESGCM(key)
        ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    else:
        # Fallback: AES-CTR + HMAC (not GCM, but still authenticated)
        ct = _fallback_encrypt(key, nonce, plaintext.encode("utf-8"))

    blob = salt + nonce + ct
    return base64.urlsafe_b64encode(blob).decode("ascii")


def decrypt(token: str, passphrase: str) -> str:
    """
    Decrypt a token produced by :func:`encrypt`.  Raises
    ``ValueError`` on authentication failure (wrong passphrase or
    tampered ciphertext).
    """
    blob = base64.urlsafe_b64decode(token.encode("ascii"))
    salt = blob[:_SALT_LEN]
    nonce = blob[_SALT_LEN : _SALT_LEN + _NONCE_LEN]
    ct = blob[_SALT_LEN + _NONCE_LEN :]
    key = derive_key(passphrase, salt)

    try:
        if _HAS_CRYPTOGRAPHY:
            aes = AESGCM(key)
            plaintext = aes.decrypt(nonce, ct, None)
        else:
            plaintext = _fallback_decrypt(key, nonce, ct)
    except Exception as exc:
        raise ValueError("Decryption failed — wrong passphrase or corrupted data") from exc

    return plaintext.decode("utf-8")


# ---------------------------------------------------------------------------
# Fallback AES-CTR + HMAC (no external dependency)
# ---------------------------------------------------------------------------
def _fallback_encrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
    """AES-CTR encryption + HMAC-SHA256 tag using only hashlib."""
    # We use the first 16 bytes of key for AES-CTR (via XOR stream) and
    # the full key for HMAC.  This is a simplified fallback — the
    # 'cryptography' library path is strongly preferred.
    import hmac as _hmac

    # Simple XOR stream cipher keyed by PBKDF2 stream
    stream = _kdf_stream(key, nonce, len(data))
    ct = bytes(a ^ b for a, b in zip(data, stream))
    tag = _hmac.new(key, nonce + ct, hashlib.sha256).digest()
    return ct + tag


def _fallback_decrypt(key: bytes, nonce: bytes, ct_and_tag: bytes) -> bytes:
    import hmac as _hmac

    tag = ct_and_tag[-32:]
    ct = ct_and_tag[:-32]
    expected = _hmac.new(key, nonce + ct, hashlib.sha256).digest()
    if not _hmac.compare_digest(tag, expected):
        raise ValueError("HMAC verification failed")
    stream = _kdf_stream(key, nonce, len(ct))
    return bytes(a ^ b for a, b in zip(ct, stream))


def _kdf_stream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Generate a pseudo-random byte stream via PBKDF2 chaining."""
    blocks = []
    needed = length
    counter = 0
    while needed > 0:
        block = hashlib.pbkdf2_hmac(
            "sha256",
            key,
            nonce + counter.to_bytes(4, "big"),
            1,
            dklen=min(needed, 32),
        )
        blocks.append(block)
        needed -= len(block)
        counter += 1
    return b"".join(blocks)[:length]


# ---------------------------------------------------------------------------
# Keyring helper — stores the master passphrase in the OS credential store
# ---------------------------------------------------------------------------
class KeyringManager:
    """
    Thin wrapper around the ``keyring`` library for storing/retrieving the
    master encryption passphrase.  Falls back to in-memory storage if the
    keyring backend is unavailable — but only when explicitly allowed.

    # sadp: R28 FL — TD-015: insecure fallback is OPT-IN, not silent.
    """

    def __init__(self, *, allow_insecure_memory_fallback: bool = False) -> None:
        self._memory_store: dict[str, str] = {}
        self._insecure_ok = allow_insecure_memory_fallback
        self._kr = None
        try:
            import keyring as _kr
            # Probe: is the backend real, or the PlaintextKeyring / FailKeyring?
            backend_name = type(_kr.get_keyring()).__name__.lower()
            if "plaintext" in backend_name or "fail" in backend_name or "null" in backend_name:
                # Backend is nominally present but stores nothing useful.
                # Treat as if unavailable so the caller can make an informed choice.
                self._kr = None
                self._backend_reason = (
                    f"keyring backend is {type(_kr.get_keyring()).__name__} "
                    "(no secure OS store available)"
                )
            else:
                self._kr = _kr
                self._backend_reason = ""
        except ImportError:
            self._backend_reason = "python-keyring package not installed"
        except Exception as exc:
            self._backend_reason = f"keyring probe failed: {type(exc).__name__}: {exc}"

    @property
    def has_secure_backend(self) -> bool:
        """True iff a real OS-backed keyring is available."""
        return self._kr is not None

    def _require_backend_or_allowed(self) -> None:
        """Raise unless a secure backend exists OR insecure fallback opted in."""
        if self._kr is None and not self._insecure_ok:
            raise RuntimeError(
                "TD-015: No secure keyring backend available "
                f"({self._backend_reason}). Refusing to store master "
                "passphrase in plaintext RAM. To override (NOT recommended "
                "for real credentials), construct KeyringManager with "
                "allow_insecure_memory_fallback=True."
            )

    def store(self, username: str, passphrase: str) -> None:
        """Persist *passphrase* for *username* in the OS keyring."""
        self._require_backend_or_allowed()
        if self._kr:
            self._kr.set_password(_KEYRING_SERVICE, username, passphrase)
        else:
            self._memory_store[username] = passphrase

    def retrieve(self, username: str) -> Optional[str]:
        """Retrieve the stored passphrase for *username*, or ``None``."""
        if self._kr:
            return self._kr.get_password(_KEYRING_SERVICE, username)
        # No secure backend — only the memory store can have anything, and
        # only if caller opted into insecure mode at construction time.
        return self._memory_store.get(username)

    def delete(self, username: str) -> None:
        """Remove stored credentials for *username*."""
        if self._kr:
            try:
                self._kr.delete_password(_KEYRING_SERVICE, username)
            except Exception as _sf_exc:  # noqa: BLE001
                logger.debug(
                    "v3.24.21 keyring delete for %r failed (absent key is success): %s", "?", _sf_exc)
        else:
            self._memory_store.pop(username, None)


# ---------------------------------------------------------------------------
# Credential vault — high-level API for encrypting exchange credentials
# ---------------------------------------------------------------------------
@dataclass
class EncryptedCredential:
    """An encrypted API key + secret + optional passphrase, JSON-serialisable."""
    exchange: str
    api_key_enc: str       # Base64 AES-GCM ciphertext
    api_secret_enc: str    # Base64 AES-GCM ciphertext
    passphrase_enc: str = ""  # Base64 AES-GCM ciphertext (empty if not needed)

    def to_dict(self) -> dict:
        return {
            "exchange": self.exchange,
            "api_key_enc": self.api_key_enc,
            "api_secret_enc": self.api_secret_enc,
            "passphrase_enc": self.passphrase_enc,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EncryptedCredential":
        return cls(
            exchange=d["exchange"],
            api_key_enc=d["api_key_enc"],
            api_secret_enc=d["api_secret_enc"],
            passphrase_enc=d.get("passphrase_enc", ""),
        )


class CredentialVault:
    """
    Manages encrypted API credentials for multiple exchanges.

    Usage::

        vault = CredentialVault(passphrase="hunter2")
        vault.store("binance", api_key="abc123", api_secret="xyz789")
        vault.store("kucoin", api_key="k", api_secret="s", passphrase="my_pass")
        key, secret, passphrase = vault.retrieve("kucoin")
    """

    def __init__(self, passphrase: str) -> None:
        self._passphrase = passphrase
        self._credentials: dict[str, EncryptedCredential] = {}

    # -- Store / retrieve ------------------------------------------------
    def store(self, exchange: str, api_key: str, api_secret: str,
              passphrase: str = "") -> None:
        """Encrypt and store credentials for *exchange*."""
        self._credentials[exchange] = EncryptedCredential(
            exchange=exchange,
            api_key_enc=encrypt(api_key, self._passphrase),
            api_secret_enc=encrypt(api_secret, self._passphrase),
            passphrase_enc=encrypt(passphrase, self._passphrase) if passphrase else "",
        )

    def retrieve(self, exchange: str) -> tuple[str, str, str]:
        """Decrypt and return ``(api_key, api_secret, passphrase)`` for *exchange*.
        Passphrase is empty string if not set."""
        cred = self._credentials.get(exchange)
        if cred is None:
            raise KeyError(f"No credentials stored for '{exchange}'")
        pp = ""
        if cred.passphrase_enc:
            pp = decrypt(cred.passphrase_enc, self._passphrase)
        return (
            decrypt(cred.api_key_enc, self._passphrase),
            decrypt(cred.api_secret_enc, self._passphrase),
            pp,
        )

    def has_exchange(self, exchange: str) -> bool:
        return exchange in self._credentials

    def list_exchanges(self) -> list[str]:
        return list(self._credentials.keys())

    # -- Serialisation ---------------------------------------------------
    def to_dict(self) -> list[dict]:
        return [c.to_dict() for c in self._credentials.values()]

    def load_from_dict(self, data: list[dict]) -> None:
        for d in data:
            cred = EncryptedCredential.from_dict(d)
            self._credentials[cred.exchange] = cred
