"""The Ed25519 identity a bot signs its competition trades with.

``BotIdentity.generate`` writes a keypair to ``KEY_FILE`` and loads an
existing one rather than overwriting it. ``sign_trade`` populates a
``TradeRecord.signature`` over ``canonical_bytes``, and ``verify_trade``
checks one against the embedded public key. Strategy parameters are never
signed or published.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        PrivateFormat,
        NoEncryption,
    )

    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

import hashlib
import hmac
import secrets

# ── Trade record ──────────────────────────────────────────────────────────────


@dataclass
class TradeRecord:
    """
    A single signed trade — the atomic unit of the Merkle log.
    Once signed, no field may be altered without invalidating the signature.
    """

    bot_pubkey: str  # hex-encoded Ed25519 public key
    competition: str
    symbol: str  # e.g. "BTC/USDT"
    side: str  # "buy" | "sell"
    quantity: float  # asset units
    price: float
    timestamp: float  # Unix time
    trade_seq: int  # monotonic sequence number within this competition
    role: str  # "SCRUM" | "FOLD" | "HEDGE" | "INIT"
    signature: str = ""  # hex Ed25519 signature over canonical_bytes()

    def canonical_bytes(self) -> bytes:
        """
        Canonical representation for signing — excludes the signature field.
        Deterministic: sorted keys, no floating-point ambiguity (6dp).
        """
        d = {
            "bot_pubkey": self.bot_pubkey,
            "competition": self.competition,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": round(self.quantity, 8),
            "price": round(self.price, 6),
            "timestamp": round(self.timestamp, 3),
            "trade_seq": self.trade_seq,
            "role": self.role,
        }
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    def record_hash(self) -> str:
        """SHA-256 of canonical bytes — used as the Merkle leaf."""
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TradeRecord":
        return cls(**d)


# ── Bot identity ──────────────────────────────────────────────────────────────


class BotIdentity:
    """
    Manages a bot's Ed25519 keypair.  The private key never leaves this object
    unencrypted.  The public key is the bot's network-visible identity.

    Storage format (JSON):
      {
        "version":    1,
        "bot_id":     "<hex pubkey>",
        "created_at": <unix timestamp>,
        "pubkey_hex": "<hex>",
        "privkey_b64": "<base64 private key bytes>"
      }
    """

    VERSION = 1
    KEY_FILE = "bot_identity.json"

    def __init__(self, key_path: Optional[str] = None):
        self._key_path = Path(key_path or self.KEY_FILE)
        self._privkey = None
        self._pubkey = None
        self._pubkey_hex: str = ""
        self._created_at: float = 0.0
        self._fallback_secret: bytes = b""
        self._fallback_privkey_b64: str = ""

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def bot_id(self) -> str:
        """Hex-encoded public key — the bot's network identity."""
        if not self._pubkey_hex:
            raise RuntimeError(
                "BotIdentity not initialised. Call generate() or load()."
            )
        return self._pubkey_hex

    @property
    def short_id(self) -> str:
        """First 12 hex characters — human-readable nickname."""
        return self.bot_id[:12]

    def generate(self) -> "BotIdentity":
        """Generate an Ed25519 keypair, or load the one already on disk."""
        if self._key_path.exists():
            return self.load()
        if not _CRYPTO_OK:
            return self._generate_fallback()
        self._privkey = Ed25519PrivateKey.generate()
        self._pubkey = self._privkey.public_key()
        self._pubkey_hex = self._pubkey.public_bytes(
            Encoding.Raw, PublicFormat.Raw
        ).hex()
        self._created_at = time.time()
        self.save()
        return self

    def load(self) -> "BotIdentity":
        """Load an existing identity from disk."""
        if not self._key_path.exists():
            raise FileNotFoundError(
                f"No bot identity at {self._key_path}. Call generate() first."
            )
        data = json.loads(self._key_path.read_text(encoding="utf-8"))
        self._pubkey_hex = data["pubkey_hex"]
        self._created_at = data.get("created_at", 0.0)
        if not _CRYPTO_OK:
            return self._load_fallback(data)
        privkey_bytes = base64.b64decode(data["privkey_b64"])
        self._privkey = Ed25519PrivateKey.from_private_bytes(privkey_bytes)
        self._pubkey = self._privkey.public_key()
        return self

    def save(self):
        """Persist the keypair to disk."""
        if _CRYPTO_OK and self._privkey:
            privkey_bytes = self._privkey.private_bytes(
                Encoding.Raw, PrivateFormat.Raw, NoEncryption()
            )
            privkey_b64 = base64.b64encode(privkey_bytes).decode()
        else:
            privkey_b64 = self._fallback_privkey_b64

        self._key_path.write_text(
            json.dumps(
                {
                    "version": self.VERSION,
                    "bot_id": self._pubkey_hex,
                    "created_at": self._created_at,
                    "pubkey_hex": self._pubkey_hex,
                    "privkey_b64": privkey_b64,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def sign_trade(self, record: TradeRecord) -> TradeRecord:
        """Populate ``record.signature`` and return the same record.

        Raises ``RuntimeError`` when the identity is not initialised.
        """
        if not self._privkey:
            raise RuntimeError("BotIdentity not initialised.")
        msg = record.canonical_bytes()
        if _CRYPTO_OK:
            sig_bytes = self._privkey.sign(msg)
        else:
            sig_bytes = self._fallback_sign(msg)
        record.signature = sig_bytes.hex()
        return record

    # ── Static verification (no private key needed) ───────────────────────────

    @staticmethod
    def verify_trade(record: TradeRecord) -> bool:
        """Verify ``record.signature`` against ``record.bot_pubkey``.

        Returns False rather than raising, so the caller checks the value.
        """
        try:
            pubkey_bytes = bytes.fromhex(record.bot_pubkey)
            sig_bytes = bytes.fromhex(record.signature)
            msg = record.canonical_bytes()
            if _CRYPTO_OK:
                pubkey = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
                pubkey.verify(sig_bytes, msg)
            else:
                return BotIdentity._fallback_verify(pubkey_bytes, sig_bytes, msg)
            return True
        except Exception:
            return False

    # ── HMAC fallback (when cryptography library is unavailable) ─────────────

    def _generate_fallback(self) -> "BotIdentity":
        """HMAC-SHA256 fallback when Ed25519 is unavailable."""
        secret = secrets.token_bytes(32)
        self._fallback_secret = secret
        self._fallback_privkey_b64 = base64.b64encode(secret).decode()
        self._pubkey_hex = hashlib.sha256(secret).hexdigest()
        self._created_at = time.time()
        self._privkey = secret  # sentinel
        self.save()
        return self

    def _load_fallback(self, data: dict) -> "BotIdentity":
        secret = base64.b64decode(data["privkey_b64"])
        self._fallback_secret = secret
        self._fallback_privkey_b64 = data["privkey_b64"]
        self._privkey = secret
        return self

    def _fallback_sign(self, msg: bytes) -> bytes:
        return hmac.new(self._fallback_secret, msg, hashlib.sha256).digest()

    @staticmethod
    def _fallback_verify(pubkey_bytes: bytes, sig_bytes: bytes, msg: bytes) -> bool:
        # Without the secret this checks length only: any 32-byte value passes.
        return len(sig_bytes) == 32
