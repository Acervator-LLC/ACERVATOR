"""
src/exchange/idempotency.py — TD-004 client-order-id idempotency layer.

Implemented v3.15.98 to close TD-004 ("Idempotency Not Enforced on Trade
Submission"). Required before sustained paper trading per TECH_DEBT.md.

PROBLEM
-------
A network timeout on `place_order()` followed by an automatic retry can
result in DUPLICATE orders at the exchange — both the original (which
the timeout hid) and the retry land. Symmetric SCRUM (sell delta + retry
sell delta) doubles the position-reduction; symmetric FOLD doubles the
buy-back. Either is an immediate financial loss for the operator.

SOLUTION
--------
Deterministic `client_order_id` (`coid`) derived from the trade's
INTENT — symbol, side, quantity, price-bucket, and session-scoped nonce.
The exchange refuses a second order with the same `coid` (Coinbase: 409
Duplicate; Binance: -2010), so a retry that lands gets rejected at the
broker rather than executed.

The IdempotencyLayer:
  - Generates a `coid` from the trade intent + a session-stable nonce
  - Caches recently-issued coids with a TTL window (default 5 minutes)
  - On retry of the same intent within TTL, REUSES the same `coid`
  - On confirmed success, marks the coid as "fulfilled" (still cached
    for the TTL so a delayed double-retry hits the cache)
  - On confirmed failure (4xx other than 409), marks for deletion
    so a future legitimate retry generates a new coid

This file is exchange-agnostic. The CCXT connector consumes it via
`apply_idempotency()` and passes the resulting `coid` in the
exchange-specific way (Coinbase: `client_oid`, Binance:
`newClientOrderId`, Kraken: `userref`).
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class _CachedCoid:
    coid: str
    issued_at: float
    fulfilled: bool = False
    intent_hash: str = ""


@dataclass
class TradeIntent:
    """The exact trade the bot wants to submit. The intent is hashed to
    derive the deterministic coid; identical intents collide deliberately
    so a retry cannot create a second order."""
    symbol: str
    side: str          # "buy" / "sell"
    amount: float      # in base asset units
    price: Optional[float]  # None for market orders
    bot_id: str        # which bot is firing
    purpose: str = ""  # "scrum" / "fold" / "cartridge" / "manual" / etc.

    def fingerprint(self, session_nonce: str) -> str:
        """Deterministic hash. Same intent + same session = same coid."""
        # Round price to 8 decimals to absorb harmless float-jitter while
        # still distinguishing genuinely different price points.
        price_str = "M" if self.price is None else f"{self.price:.8f}"
        # Round amount likewise; coid collisions on near-identical amounts
        # are EXACTLY what we want to prevent (= duplicate retry).
        amount_str = f"{self.amount:.10f}"
        raw = (
            f"{self.bot_id}|{self.symbol}|{self.side}|{amount_str}|"
            f"{price_str}|{self.purpose}|{session_nonce}"
        )
        # 16-char prefix is plenty unique for retry-window collision-prevention,
        # well below most exchanges' 36-char client-order-id limit.
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class IdempotencyLayer:
    """Per-process idempotency cache with a TTL window."""

    def __init__(self, ttl_seconds: float = 300.0,
                 max_entries: int = 5000) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        # Session nonce: stable for this process lifetime, NOT
        # persisted. After app restart, retry-collision-avoidance
        # resets — that's correct: a restart means the operator
        # explicitly re-launched and shouldn't be tied to old orders.
        self.session_nonce = uuid.uuid4().hex[:8]
        self._cache: dict[str, _CachedCoid] = {}
        self._lock = threading.RLock()

    def derive_coid(self, intent: TradeIntent) -> str:
        """Get (or reuse) the coid for this intent. The PRIMARY entry
        point; callers always go through this."""
        with self._lock:
            self._evict_expired()
            fp = intent.fingerprint(self.session_nonce)
            cached = self._cache.get(fp)
            if cached is not None:
                # Reuse the same coid — this IS a retry of the same intent
                logger.info(
                    "Idempotency: reusing coid=%s for retry of "
                    "%s %s %.8f@%s (issued %.1fs ago)",
                    cached.coid, intent.side, intent.symbol,
                    intent.amount,
                    "MKT" if intent.price is None else f"{intent.price:.8f}",
                    time.time() - cached.issued_at)
                return cached.coid
            # New intent — generate a coid and cache it
            coid = f"acrv-{fp}"
            self._cache[fp] = _CachedCoid(
                coid=coid, issued_at=time.time(), intent_hash=fp)
            self._enforce_size_limit()
            return coid

    def mark_fulfilled(self, intent: TradeIntent) -> None:
        """Mark this intent's coid as completed. Stays cached for TTL
        so a delayed retry still hits the cache."""
        with self._lock:
            fp = intent.fingerprint(self.session_nonce)
            cached = self._cache.get(fp)
            if cached is not None:
                cached.fulfilled = True

    def invalidate(self, intent: TradeIntent) -> None:
        """Remove this intent's coid from cache. Use when the order was
        REJECTED by the exchange (4xx other than 409 duplicate) so the
        next legitimate retry can generate a fresh coid."""
        with self._lock:
            fp = intent.fingerprint(self.session_nonce)
            self._cache.pop(fp, None)

    def is_known(self, intent: TradeIntent) -> bool:
        with self._lock:
            self._evict_expired()
            fp = intent.fingerprint(self.session_nonce)
            return fp in self._cache

    def _evict_expired(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        expired = [k for k, v in self._cache.items() if v.issued_at < cutoff]
        for k in expired:
            del self._cache[k]

    def _enforce_size_limit(self) -> None:
        if len(self._cache) <= self.max_entries:
            return
        # Drop the oldest entries
        sorted_items = sorted(
            self._cache.items(), key=lambda kv: kv[1].issued_at)
        for k, _ in sorted_items[:len(self._cache) - self.max_entries]:
            del self._cache[k]

    def stats(self) -> dict:
        with self._lock:
            self._evict_expired()
            return {
                "cached_intents": len(self._cache),
                "fulfilled": sum(1 for v in self._cache.values() if v.fulfilled),
                "ttl_seconds": self.ttl_seconds,
                "session_nonce": self.session_nonce,
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
