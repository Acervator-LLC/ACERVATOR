"""Three-state circuit breaker for exchange API calls.

``CircuitBreaker`` starts CLOSED and passes calls through, while
``record_failure`` counts transient errors and opens it at
``failure_threshold``. ``is_call_allowed`` refuses every call while OPEN and
allows one probe once ``cooldown_seconds`` elapses.
``CircuitBreakerRegistry`` holds one breaker per symbol or endpoint,
and ``ACERVATOR_BREAKER_DISABLE`` makes ``_breaker_disabled`` allow
everything.
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


# Substrings of an exception class NAME; no ccxt exception type is imported.
TRANSIENT_ERROR_NAME_PATTERNS: tuple[str, ...] = (
    "Timeout",  # ccxt.RequestTimeout, asyncio.TimeoutError, socket.timeout
    "ConnectionError",  # urllib3.ConnectionError, requests.ConnectionError
    "ConnectionReset",
    "NetworkError",
    "DDoSProtection",
    "ExchangeNotAvailable",
    "RateLimitExceeded",
    "OnMaintenance",
    "BadResponse",
    "GatewayTimeout",
    "ServiceUnavailable",
)


def _is_transient_error(exc: BaseException) -> bool:
    """True when the class name of ``exc`` contains a
    ``TRANSIENT_ERROR_NAME_PATTERNS`` entry. ``record_failure`` counts only
    these toward ``failure_threshold``."""
    name = type(exc).__name__
    return any(pat in name for pat in TRANSIENT_ERROR_NAME_PATTERNS)


def _breaker_disabled() -> bool:
    """True when ``ACERVATOR_BREAKER_DISABLE`` holds 1, true, yes or on."""
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
        """True when a call may be attempted. ``_breaker_disabled`` forces
        True; an OPEN ``stats.state`` gives False."""
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
                self.stats.consecutive_failures = 0

    def record_failure(self, exc: Optional[BaseException] = None) -> None:
        """Count one failure and open the breaker at ``failure_threshold``.

        An ``exc`` that ``_is_transient_error`` refuses raises
        ``total_failures`` only and leaves ``consecutive_failures`` alone.
        """
        if exc is not None and not _is_transient_error(exc):
            with self._lock:
                self.stats.total_failures += 1
                self.stats.last_failure_at = time.time()
            return
        with self._lock:
            self.stats.total_failures += 1
            self.stats.consecutive_failures += 1
            self.stats.last_failure_at = time.time()
            if self.stats.state == BreakerState.HALF_OPEN:
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
