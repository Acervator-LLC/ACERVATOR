"""One client order id per order, held for its retry while the venue has not answered.

``IdempotencyLayer.derive_coid`` issues a ``coid`` and holds it for one bot, market and
side, and the next ``TradeIntent`` there sends the held ``coid``, which a venue will not
open twice. ``IdempotencyLayer.end_retries`` drops what it holds for one bot on one market.
``BotContainer.guarded_place_order`` calls both, and ``_reconcile_holdings`` the second.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

#: Hex characters in a hash, and ``acrv-`` beside them fits a 36-character id field.
HASH_CHARS = 16


def _short_hash(text: str) -> str:
    """The first ``HASH_CHARS`` hex characters of the SHA-256 of ``text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:HASH_CHARS]


@dataclass
class _UnansweredCoid:
    coid: str
    issued_at: float


@dataclass
class TradeIntent:
    """The exact trade the bot wants to submit, which ``fingerprint`` hashes to seed a
    new ``coid``."""

    symbol: str
    side: str  # "buy" / "sell"
    amount: float  # in base asset units
    price: Optional[float]  # None for market orders
    bot_id: str
    purpose: str = ""  # "scrum" / "fold" / "cartridge" / "manual" / etc.

    def fingerprint(self, session_nonce: str) -> str:
        """Deterministic hash. Same intent + same session = same value."""
        # Round price to 8 decimals to absorb harmless float-jitter while
        # still distinguishing genuinely different price points.
        price_str = "M" if self.price is None else f"{self.price:.8f}"
        amount_str = f"{self.amount:.10f}"
        return _short_hash(
            f"{self.bot_id}|{self.symbol}|{self.side}|{amount_str}|"
            f"{price_str}|{self.purpose}|{session_nonce}"
        )


class IdempotencyLayer:
    """Per-process record of the ``coid`` each bot, market and side has unanswered."""

    def __init__(self) -> None:
        # Not persisted, so a restart gives new coids for the same intent.
        self.session_nonce = uuid.uuid4().hex[:8]
        self._unanswered: dict[tuple[str, str, str], _UnansweredCoid] = {}
        self._issued = 0
        self._lock = threading.RLock()

    def derive_coid(self, intent: TradeIntent) -> str:
        """The ``coid`` held for this bot, market and side, or a new one no earlier
        order carried."""
        with self._lock:
            key = (intent.bot_id, intent.symbol, intent.side)
            held = self._unanswered.get(key)
            if held is not None:
                logger.info(
                    "Idempotency: reusing coid=%s for retry of "
                    "%s %s %.8f@%s (issued %.1fs ago)",
                    held.coid,
                    intent.side,
                    intent.symbol,
                    intent.amount,
                    "MKT" if intent.price is None else f"{intent.price:.8f}",
                    time.time() - held.issued_at,
                )
                return held.coid
            self._issued += 1
            fp = intent.fingerprint(self.session_nonce)
            coid = f"acrv-{_short_hash(f'{fp}|{self._issued}')}"
            self._unanswered[key] = _UnansweredCoid(coid=coid, issued_at=time.time())
            return coid

    def end_retries(self, bot_id: str, symbol: str) -> None:
        """Drop every ``coid`` held for ``bot_id`` on ``symbol``, leaving ``derive_coid``
        to issue a new one for each later ``TradeIntent``."""
        with self._lock:
            self._unanswered = {
                key: held
                for key, held in self._unanswered.items()
                if key[:2] != (bot_id, symbol)
            }


# Process-singleton
_layer: Optional[IdempotencyLayer] = None
_singleton_lock = threading.Lock()


def get_idempotency_layer() -> IdempotencyLayer:
    """Return the process-wide IdempotencyLayer (lazy-init)."""
    global _layer
    if _layer is None:
        with _singleton_lock:
            if _layer is None:
                _layer = IdempotencyLayer()
    return _layer


def reset_for_test() -> None:
    """Reset the singleton — tests only."""
    global _layer
    with _singleton_lock:
        _layer = None
