"""One client order id per order, held for its retry while the venue has not answered.

``IdempotencyLayer.derive_coid`` issues a ``coid`` and holds it, and a retry of the
same ``TradeIntent`` sends the held ``coid``, which the venue refuses to open twice.
``IdempotencyLayer.end_retries`` drops what it holds for one bot on one market.
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
    bot_id: str
    symbol: str


@dataclass
class TradeIntent:
    """The exact trade the bot wants to submit, and identical intents share one
    ``fingerprint``, which ``derive_coid`` reads to find a retry."""

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
    """Per-process record of each ``coid`` the venue has not answered."""

    def __init__(self, max_entries: int = 5000) -> None:
        self.max_entries = max_entries
        # Not persisted, so a restart gives new coids for the same intent.
        self.session_nonce = uuid.uuid4().hex[:8]
        self._unanswered: dict[str, _UnansweredCoid] = {}
        self._issued = 0
        self._lock = threading.RLock()

    def derive_coid(self, intent: TradeIntent) -> str:
        """The ``coid`` held for ``intent``, or a new one no earlier order carried."""
        with self._lock:
            fp = intent.fingerprint(self.session_nonce)
            held = self._unanswered.get(fp)
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
            coid = f"acrv-{_short_hash(f'{fp}|{self._issued}')}"
            self._unanswered[fp] = _UnansweredCoid(
                coid=coid,
                issued_at=time.time(),
                bot_id=intent.bot_id,
                symbol=intent.symbol,
            )
            self._enforce_size_limit()
            return coid

    def end_retries(self, bot_id: str, symbol: str) -> None:
        """Drop every ``coid`` held for ``bot_id`` on ``symbol``, leaving ``derive_coid``
        to issue a new one for each later ``TradeIntent``."""
        with self._lock:
            self._unanswered = {
                fp: held
                for fp, held in self._unanswered.items()
                if (held.bot_id, held.symbol) != (bot_id, symbol)
            }

    def _enforce_size_limit(self) -> None:
        if len(self._unanswered) <= self.max_entries:
            return
        # Drop the oldest entries
        by_age = sorted(self._unanswered.items(), key=lambda kv: kv[1].issued_at)
        for k, _ in by_age[: len(self._unanswered) - self.max_entries]:
            del self._unanswered[k]


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
