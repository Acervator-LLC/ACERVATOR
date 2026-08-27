"""retry.py — the one retry loop the exchange paths share.

Three call sites used to carry their own loop: the ``ccxt_connector``
decorator, the ``sync_connect`` market-load loop, and the Stone Tablet
fetcher. They disagree on attempt count, delay schedule, which
exceptions are transient, and whether exhaustion raises or is reported.
Those four are parameters here, never defaults, so a site states its
policy at the call and cannot inherit another site's.

``is_retryable``, ``delay_for`` and ``attempts`` are required keywords
for that reason. Nothing in this module may be applied to an order
submission — see TD-014 in ``src/exchange/ccxt_connector.py``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional, TypeVar, cast

logger = logging.getLogger("acervator.core.retry")

T = TypeVar("T")
AsyncMethod = TypeVar("AsyncMethod", bound=Callable[..., Awaitable[Any]])

FailureHook = Callable[[BaseException, int, bool, float], None]
"""Called on every failed attempt as ``(exc, attempt, will_retry, delay)``.
``attempt`` counts from 0. ``delay`` is 0.0 when ``will_retry`` is False."""

TRANSIENT_NAME_KEYWORDS: tuple[str, ...] = (
    "ratelimit",
    "timeout",
    "network",
    "request",
)


def is_transient(exc: BaseException) -> bool:
    """True when the exception CLASS NAME contains a transient keyword.

    Matches on the name, not the type, because ccxt raises a different
    exception hierarchy per exchange.
    """
    name = type(exc).__name__.lower()
    return any(keyword in name for keyword in TRANSIENT_NAME_KEYWORDS)


def retry_any(exc: BaseException) -> bool:
    """Retryable predicate that accepts every exception."""
    del exc
    return True


def exponential_delay(base_delay: float) -> Callable[[int], float]:
    """Schedule ``base_delay * 2 ** attempt``, attempt counted from 0."""

    def schedule(attempt: int) -> float:
        return base_delay * (2**attempt)

    return schedule


def linear_delay(step: float) -> Callable[[int], float]:
    """Schedule ``step * (attempt + 1)``, attempt counted from 0."""

    def schedule(attempt: int) -> float:
        return step * (attempt + 1)

    return schedule


def _delay_after_failure(
    exc: BaseException,
    attempt: int,
    attempts: int,
    is_retryable: Callable[[BaseException], bool],
    delay_for: Callable[[int], float],
    on_failure: Optional[FailureHook],
) -> Optional[float]:
    """Return the delay before the next attempt, or None to re-raise.

    The final attempt never yields a delay, so no caller waits for a
    retry it will not make.
    """
    retryable = is_retryable(exc)
    will_retry = retryable and attempt < attempts - 1
    delay = delay_for(attempt) if will_retry else 0.0
    if on_failure is not None:
        on_failure(exc, attempt, will_retry, delay)
    return delay if will_retry else None


def _check_attempts(attempts: int) -> None:
    """Reject an attempt budget that would call the operation zero times."""
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")


async def retry_async(
    op: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    delay_for: Callable[[int], float],
    is_retryable: Callable[[BaseException], bool],
    on_failure: Optional[FailureHook] = None,
) -> T:
    """Await ``op()`` up to ``attempts`` times, re-raising the last error.

    ``op`` is called fresh per attempt. A non-retryable exception raises
    immediately. Waits with ``asyncio.sleep``.
    """
    _check_attempts(attempts)
    attempt = 0
    while True:
        try:
            return await op()
        except Exception as exc:
            delay = _delay_after_failure(
                exc, attempt, attempts, is_retryable, delay_for, on_failure
            )
            if delay is None:
                raise
            await asyncio.sleep(delay)
            attempt += 1


def retry_sync(
    op: Callable[[], T],
    *,
    attempts: int,
    delay_for: Callable[[int], float],
    is_retryable: Callable[[BaseException], bool],
    on_failure: Optional[FailureHook] = None,
) -> T:
    """Call ``op()`` up to ``attempts`` times, re-raising the last error.

    Blocking counterpart of :func:`retry_async`; waits with ``time.sleep``.
    """
    _check_attempts(attempts)
    attempt = 0
    while True:
        try:
            return op()
        except Exception as exc:
            delay = _delay_after_failure(
                exc, attempt, attempts, is_retryable, delay_for, on_failure
            )
            if delay is None:
                raise
            time.sleep(delay)
            attempt += 1


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    log: Optional[logging.Logger] = None,
) -> Callable[[AsyncMethod], AsyncMethod]:
    """Decorator: retry an async method on transient exchange errors.

    Retries only when :func:`is_transient` accepts the exception, backs
    off ``base_delay * 2 ** attempt``, and raises the last exception.
    ``log`` receives the retry warning so the record keeps the calling
    module's logger name.
    """
    emit = log if log is not None else logger

    def decorator(func: AsyncMethod) -> AsyncMethod:
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            def note(
                exc: BaseException, attempt: int, will_retry: bool, delay: float
            ) -> None:
                if not will_retry:
                    return
                emit.warning(
                    "%s on %s (attempt %d/%d), retrying in %.1fs",
                    type(exc).__name__,
                    func.__name__,
                    attempt + 1,
                    max_retries,
                    delay,
                )

            return await retry_async(
                lambda: func(self, *args, **kwargs),
                attempts=max_retries,
                delay_for=exponential_delay(base_delay),
                is_retryable=is_transient,
                on_failure=note,
            )

        return cast(AsyncMethod, wrapper)

    return decorator
