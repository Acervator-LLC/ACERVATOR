"""
src/exchange/circuit_breaker.py — TD-003 closure (v3.15.98, v3.16.6 tuned).

v3.16.6 tuning (operator-reported 2026-04-28):
  Operator's CHIP/USD bot tripped the breaker on first build with 30s
  cooldown blocking real trades. Root cause: the v3.15.98 implementation
  counted ALL Exception types as outage signals, including operator-
  fixable logic errors (insufficient funds, auth, invalid order). These
  errors are NOT "exchange is down" — they're "your config is wrong" —
  but the breaker locked the bot out and hid the real error message.

  v3.16.6 fixes:
    1. Only count transient/network errors toward the breaker (timeout,
       connection error, rate-limit, gateway 5xx). Logic errors pass
       through with their original message so the operator sees the
       real failure.
    2. Default threshold raised 5 → 20 (less trip-happy on noise).
    3. Cooldown 30s → 5s (operator can resume quickly).
    4. ACERVATOR_BREAKER_DISABLE=1 env var short-circuits the breaker
       entirely as a safety valve.
    5. force-close-all on registry init so prior open state doesn't
       carry across restarts.

Three-state circuit breaker for exchange API calls:

    CLOSED      — normal operation; calls pass through; failures counted
    OPEN        — circuit is tripped; calls FAIL FAST without hitting the
                  exchange; cooldown timer is running
    HALF_OPEN   — cooldown elapsed; one probe call is allowed; success
                  closes the circuit, failure re-opens it

The breaker prevents retry storms from depleting the operator's API
rate-limit quota during exchange outages. Without it, a 30-second
exchange outage with 8 bots running 1Hz tick rate = 240 wasted calls
per outage, plus IP-ban risk on some venues (Binance: 6 strikes/minute).

Per-symbol breakers — an outage on BTC/USD shouldn't trip ETH/USD.

CONFIG (defaults; tuned for spot trading on Coinbase + Kraken):
  - failure_threshold = 5      (5 consecutive failures → OPEN)
  - cooldown_seconds  = 30.0   (wait 30s before HALF_OPEN probe)
  - success_threshold = 2      (HALF_OPEN: 2 consecutive successes → CLOSED)
  - rolling_window    = 60.0   (failures older than 60s don't count)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, TypeVar, Awaitable

logger = logging.getLogger(__name__)


# v3.16.6 — only these exception name patterns count as breaker-relevant
# failures. Everything else passes through unchanged (raised) so the
# operator sees the real error message. Match by exception class NAME
# (not isinstance) so we don't need to import every CCXT exception type.
TRANSIENT_ERROR_NAME_PATTERNS: tuple[str, ...] = (
    "Timeout",  # ccxt.RequestTimeout, asyncio.TimeoutError, socket.timeout
    "ConnectionError",  # urllib3.ConnectionError, requests.ConnectionError
    "ConnectionReset",  # connection reset by peer
    "NetworkError",  # ccxt.NetworkError
    "DDoSProtection",  # ccxt.DDoSProtection (cloudflare etc.)
    "ExchangeNotAvailable",  # ccxt.ExchangeNotAvailable
    "RateLimitExceeded",  # ccxt.RateLimitExceeded — transient, retry will work
    "OnMaintenance",  # ccxt.OnMaintenance
    "BadResponse",  # ccxt.BadResponse — usually transient
    "GatewayTimeout",
    "ServiceUnavailable",
)


def _is_transient_error(exc: BaseException) -> bool:
    """True if `exc` looks like a transient/network failure that the
    breaker should count. False for logic errors (auth, insufficient
    funds, invalid order, bad symbol) which the operator must fix —
    those should pass through with their original message."""
    name = type(exc).__name__
    return any(pat in name for pat in TRANSIENT_ERROR_NAME_PATTERNS)


def _breaker_disabled() -> bool:
    """Operator can short-circuit the breaker entirely with an env var.
    Returns True if `ACERVATOR_BREAKER_DISABLE` is set to a truthy value."""
    val = os.environ.get("ACERVATOR_BREAKER_DISABLE", "").strip().lower()
    return val in ("1", "true", "yes", "on")


class BreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class BreakerStats:
    state: BreakerState = BreakerState.CLOSED
    consecutive_failures: int = 0
    consecutive_half_open_successes: int = 0
    open_since: float = 0.0
    last_failure_at: float = 0.0
    last_success_at: float = 0.0
    total_failures: int = 0
    total_successes: int = 0
    total_short_circuits: int = 0  # calls that failed-fast while OPEN


class CircuitBreakerOpenError(Exception):
    """Raised when a call is short-circuited because the breaker is OPEN."""

    def __init__(self, key: str, cooldown_remaining: float) -> None:
        super().__init__(
            f"Circuit breaker for '{key}' is OPEN; "
            f"cooldown remaining: {cooldown_remaining:.1f}s"
        )
        self.key = key
        self.cooldown_remaining = cooldown_remaining


class CircuitBreaker:
    """Per-key (per-symbol or per-endpoint) circuit breaker."""

    def __init__(
        self,
        key: str,
        # v3.16.6 — defaults relaxed. Only transient/network errors
        # count; logic errors pass through. So the threshold can be
        # higher without missing real outages.
        failure_threshold: int = 20,
        cooldown_seconds: float = 5.0,
        success_threshold: int = 1,
        rolling_window: float = 30.0,
    ) -> None:
        self.key = key
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.success_threshold = success_threshold
        self.rolling_window = rolling_window
        self.stats = BreakerStats()
        self._lock = threading.Lock()

    # -- State queries --------------------------------------------------

    def state(self) -> BreakerState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self.stats.state

    def is_call_allowed(self) -> bool:
        """True if a call should be attempted; False = fail fast.

        v3.16.6 — env-var disable short-circuits to always-allowed.
        """
        if _breaker_disabled():
            return True
        with self._lock:
            self._maybe_transition_to_half_open()
            self._maybe_decay_failures()
            return self.stats.state in (BreakerState.CLOSED, BreakerState.HALF_OPEN)

    def cooldown_remaining(self) -> float:
        with self._lock:
            if self.stats.state != BreakerState.OPEN:
                return 0.0
            elapsed = time.time() - self.stats.open_since
            return max(0.0, self.cooldown_seconds - elapsed)

    # -- State transitions ----------------------------------------------

    def record_success(self) -> None:
        with self._lock:
            self.stats.total_successes += 1
            self.stats.last_success_at = time.time()
            if self.stats.state == BreakerState.HALF_OPEN:
                self.stats.consecutive_half_open_successes += 1
                if self.stats.consecutive_half_open_successes >= self.success_threshold:
                    self._transition_to_closed()
            elif self.stats.state == BreakerState.CLOSED:
                self.stats.consecutive_failures = 0  # success resets failure run

    def record_failure(self, exc: Optional[BaseException] = None) -> None:
        """v3.16.6 — only count transient/network errors. Logic errors
        (auth, insufficient funds, invalid order, bad symbol) are
        operator-fixable and should pass through with their original
        error message rather than locking the bot out behind a stale
        circuit-open state."""
        if exc is not None and not _is_transient_error(exc):
            # Operator-fixable error — record total but don't count
            # toward consecutive-failure trip. Caller still sees the
            # raised exception with its original message.
            with self._lock:
                self.stats.total_failures += 1
                self.stats.last_failure_at = time.time()
            return
        with self._lock:
            self.stats.total_failures += 1
            self.stats.consecutive_failures += 1
            self.stats.last_failure_at = time.time()
            if self.stats.state == BreakerState.HALF_OPEN:
                # Probe failed → re-open immediately
                self._transition_to_open(exc)
            elif self.stats.state == BreakerState.CLOSED:
                if self.stats.consecutive_failures >= self.failure_threshold:
                    self._transition_to_open(exc)

    def record_short_circuit(self) -> None:
        """Called when a caller short-circuited because the breaker was OPEN."""
        with self._lock:
            self.stats.total_short_circuits += 1

    def force_close(self) -> None:
        """Operator override: force the breaker back to CLOSED."""
        with self._lock:
            self._transition_to_closed()

    # -- Internal transitions (must hold _lock) -------------------------

    def _transition_to_open(self, exc: Optional[BaseException] = None) -> None:
        if self.stats.state != BreakerState.OPEN:
            self.stats.state = BreakerState.OPEN
            self.stats.open_since = time.time()
            self.stats.consecutive_half_open_successes = 0
            logger.warning(
                "Circuit breaker '%s' OPEN after %d failures (last: %s)",
                self.key,
                self.stats.consecutive_failures,
                f"{type(exc).__name__}: {exc}" if exc else "n/a",
            )

    def _transition_to_closed(self) -> None:
        if self.stats.state != BreakerState.CLOSED:
            self.stats.state = BreakerState.CLOSED
            self.stats.consecutive_failures = 0
            self.stats.consecutive_half_open_successes = 0
            self.stats.open_since = 0.0
            logger.info("Circuit breaker '%s' CLOSED", self.key)

    def _maybe_transition_to_half_open(self) -> None:
        if (
            self.stats.state == BreakerState.OPEN
            and time.time() - self.stats.open_since >= self.cooldown_seconds
        ):
            self.stats.state = BreakerState.HALF_OPEN
            self.stats.consecutive_half_open_successes = 0
            logger.info(
                "Circuit breaker '%s' HALF_OPEN (cooldown elapsed); "
                "next call is a probe",
                self.key,
            )

    def _maybe_decay_failures(self) -> None:
        if (
            self.stats.state == BreakerState.CLOSED
            and self.stats.consecutive_failures > 0
            and time.time() - self.stats.last_failure_at > self.rolling_window
        ):
            self.stats.consecutive_failures = 0


T = TypeVar("T")


class CircuitBreakerRegistry:
    """Per-process registry of breakers keyed by (exchange, symbol/endpoint)."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, key: str, **breaker_kwargs) -> CircuitBreaker:
        with self._lock:
            br = self._breakers.get(key)
            if br is None:
                br = CircuitBreaker(key=key, **breaker_kwargs)
                self._breakers[key] = br
            return br

    def all_keys(self) -> list[str]:
        with self._lock:
            return list(self._breakers.keys())

    def all_open(self) -> list[str]:
        with self._lock:
            return [
                k for k, b in self._breakers.items() if b.state() == BreakerState.OPEN
            ]

    def reset_all(self) -> None:
        with self._lock:
            for br in self._breakers.values():
                br.force_close()


_registry: Optional[CircuitBreakerRegistry] = None
_registry_lock = threading.Lock()


def get_breaker_registry() -> CircuitBreakerRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = CircuitBreakerRegistry()
                # v3.16.6 — at first registry use in this process, log
                # the disable state so operators can verify config.
                if _breaker_disabled():
                    logger.info(
                        "Circuit breaker DISABLED via "
                        "ACERVATOR_BREAKER_DISABLE env var"
                    )
    return _registry


def reset_for_test() -> None:
    global _registry
    with _registry_lock:
        _registry = None


async def call_with_breaker(
    key: str,
    fn: Callable[..., Awaitable[T]],
    *args,
    **kwargs,
) -> T:
    """Wrap an async exchange call with the breaker for `key`.

    Raises CircuitBreakerOpenError WITHOUT calling fn if the breaker is OPEN.
    """
    br = get_breaker_registry().get(key)
    if not br.is_call_allowed():
        br.record_short_circuit()
        raise CircuitBreakerOpenError(key, br.cooldown_remaining())
    try:
        result = await fn(*args, **kwargs)
    except Exception as exc:
        br.record_failure(exc)
        raise
    br.record_success()
    return result
