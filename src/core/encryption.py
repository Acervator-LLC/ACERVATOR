"""AES-256-GCM encryption for API credentials.

Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights
reserved.

``encrypt`` and ``decrypt`` key AESGCM from ``derive_key``, which runs
PBKDF2-HMAC-SHA256 over a passphrase and a random salt. Each token carries its
own salt and nonce, neither secret. Without the ``cryptography`` package
``_fallback_encrypt`` substitutes a PBKDF2 keystream with an HMAC-SHA256 tag,
and KeyringManager holds the passphrase in the OS credential store.
"""

from __future__ import annotations

import logging

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("acervator.encryption")

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False


_SALT_LEN = 16  # bytes; 128-bit salt
_NONCE_LEN = 12  # bytes; 96-bit nonce, the AES-GCM size NIST SP 800-38D names
_KEY_LEN = 32  # bytes; 256-bit key
_KDF_ITERATIONS = 600_000  # OWASP PBKDF2-HMAC-SHA256 guidance
_KEYRING_SERVICE = "acervator"


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
        return hashlib.pbkdf2_hmac(
            "sha256",
            passphrase.encode("utf-8"),
            salt,
            _KDF_ITERATIONS,
            dklen=_KEY_LEN,
        )


def encrypt(plaintext: str, passphrase: str) -> str:
    """Encrypt *plaintext* with AES-256-GCM under ``derive_key(passphrase, salt)``.

    Returns URL-safe Base64 over salt (_SALT_LEN) || nonce (_NONCE_LEN) ||
    ciphertext and tag.
    """
    salt = secrets.token_bytes(_SALT_LEN)
    nonce = secrets.token_bytes(_NONCE_LEN)
    key = derive_key(passphrase, salt)

    if _HAS_CRYPTOGRAPHY:
        aes = AESGCM(key)
        ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    else:
        ct = _fallback_encrypt(key, nonce, plaintext.encode("utf-8"))

    blob = salt + nonce + ct
    return base64.urlsafe_b64encode(blob).decode("ascii")


def decrypt(token: str, passphrase: str) -> str:
    """Decrypt a token produced by :func:`encrypt`.

    Raises ``ValueError`` on a wrong *passphrase* or a tampered token.
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
        raise ValueError(
            "Decryption failed — wrong passphrase or corrupted data"
        ) from exc

    return plaintext.decode("utf-8")


def _fallback_encrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
    """XOR *data* against ``_kdf_stream`` and append an HMAC-SHA256 tag.

    This path holds no AES; the whole *key* feeds both ``_kdf_stream`` and the
    tag, and ``encrypt`` reaches it only when ``_HAS_CRYPTOGRAPHY`` is False.
    """
    import hmac as _hmac

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


class KeyringManager:
    """Stores and retrieves the master passphrase in the OS ``keyring``.

    ``_memory_store`` takes over only when ``allow_insecure_memory_fallback``
    is set; otherwise ``_require_backend_or_allowed`` raises.
    """

    def __init__(self, *, allow_insecure_memory_fallback: bool = False) -> None:
        self._memory_store: dict[str, str] = {}
        self._insecure_ok = allow_insecure_memory_fallback
        self._kr = None
        try:
            import keyring as _kr

            backend_name = type(_kr.get_keyring()).__name__.lower()
            if (
                "plaintext" in backend_name
                or "fail" in backend_name
                or "null" in backend_name
            ):
                # A named backend that stores nothing useful counts as absent.
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
            self._backend_reason = f"keyring backend check failed: {type(exc).__name__}: {exc}"

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
        # _memory_store is populated only after store() cleared the insecure opt-in.
        return self._memory_store.get(username)

    def delete(self, username: str) -> None:
        """Remove stored credentials for *username*.

        ``delete_password`` raising on an absent key is logged and swallowed.
        """
        if self._kr:
            try:
                self._kr.delete_password(_KEYRING_SERVICE, username)
            except Exception as _sf_exc:  # noqa: BLE001
                logger.debug(
                    "keyring delete for %r failed: %s",
                    username,
                    _sf_exc,
                )
        else:
            self._memory_store.pop(username, None)


@dataclass
class EncryptedCredential:
    """An encrypted API key, secret and optional passphrase for one exchange.

    ``to_dict`` and ``from_dict`` round-trip it through JSON.
    """

    exchange: str
    api_key_enc: str  # Base64 token from encrypt()
    api_secret_enc: str  # Base64 token from encrypt()
    passphrase_enc: str = ""  # Base64 token from encrypt(), empty when unused

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
    """Holds one EncryptedCredential per exchange under a single passphrase.

    ``store`` encrypts and ``retrieve`` decrypts; ``to_dict`` and
    ``load_from_dict`` move the whole set to and from JSON.
    """

    def __init__(self, passphrase: str) -> None:
        self._passphrase = passphrase
        self._credentials: dict[str, EncryptedCredential] = {}

    def store(
        self,
        exchange: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None,
    ) -> None:
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

    def to_dict(self) -> list[dict]:
        return [c.to_dict() for c in self._credentials.values()]

    def load_from_dict(self, data: list[dict]) -> None:
        for d in data:
            cred = EncryptedCredential.from_dict(d)
            self._credentials[cred.exchange] = cred
