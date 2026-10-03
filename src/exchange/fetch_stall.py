"""Reports a fleet-wide stop in exchange fetching to the Console.

``stall_seconds`` answers how long nothing has come back, or None while
fetching is healthy. ``FetchStallReport.note`` turns that answer into one
Console line per cooling-off window, and
``MainWindow._report_fetch_stall`` calls both on the two-second dashboard
tick. ``STALL_THRESHOLD_SECONDS`` is ``APILoadMonitor``'s own rate window,
spanning ``TICKER_LIFETIMES_PER_THRESHOLD`` ticker lifetimes and
``BALANCE_LIFETIMES_PER_THRESHOLD`` balance lifetimes.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Optional

from .api_load_monitor import DEFAULT_WINDOW_SECONDS
from .data_pool import BALANCE_TTL_SECONDS, TICKER_TTL_SECONDS
from .lazy_singleton import (
    BACKOFF_FACTOR,
    DEFAULT_BASE_COOLOFF_S,
    DEFAULT_MAX_COOLOFF_S,
)

logger = logging.getLogger("acervator.fetch_stall")

#: Age the freshest pool slot must pass before a stop is reported, seconds.
#: A zero call rate is a full measurement only across this span.
STALL_THRESHOLD_SECONDS = DEFAULT_WINDOW_SECONDS

#: The threshold measured in the pool's two declared slot lifetimes.
TICKER_LIFETIMES_PER_THRESHOLD = STALL_THRESHOLD_SECONDS / TICKER_TTL_SECONDS
BALANCE_LIFETIMES_PER_THRESHOLD = STALL_THRESHOLD_SECONDS / BALANCE_TTL_SECONDS

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600


def span_words(seconds: float) -> str:
    """Render ``seconds`` as the hours, minutes and seconds a reader says.

    Zero and every negative ``seconds`` read "0 seconds".
    """
    total = max(0, int(seconds))
    hours, rest = divmod(total, SECONDS_PER_HOUR)
    minutes, secs = divmod(rest, SECONDS_PER_MINUTE)
    parts = []
    if hours:
        parts.append(f"{hours} hour" if hours == 1 else f"{hours} hours")
    if minutes:
        parts.append(f"{minutes} minute" if minutes == 1 else f"{minutes} minutes")
    if secs or not parts:
        parts.append(f"{secs} second" if secs == 1 else f"{secs} seconds")
    return " ".join(parts)


def stall_seconds(
    freshest_age_s: Optional[float],
    calls_per_minute: float,
    threshold_s: float = STALL_THRESHOLD_SECONDS,
) -> Optional[float]:
    """Seconds since the last reading arrived, None while fetching is healthy.

    Answers a span only when ``calls_per_minute`` is zero and
    ``freshest_age_s`` is past ``threshold_s``; ``freshest_age_s`` of None is a
    cold start.
    """
    if freshest_age_s is None:
        return None
    if calls_per_minute > 0:
        return None
    age = float(freshest_age_s)
    if age <= float(threshold_s):
        return None
    return age


class FetchStallReport:
    """One Console line per cooling-off window while exchange fetching is stopped.

    ``note`` carries ``ThrottledFault``'s policy — one line on the first
    stopped tick, one repeat per window widened by ``BACKOFF_FACTOR``, one line
    when it clears — and its own wording.
    """

    def __init__(
        self,
        *,
        base_cooloff_s: float = DEFAULT_BASE_COOLOFF_S,
        max_cooloff_s: float = DEFAULT_MAX_COOLOFF_S,
        clock: Callable[[], float] = time.monotonic,
        log: Optional[logging.Logger] = None,
    ) -> None:
        """``clock`` is injectable and defaults to ``time.monotonic``."""
        self._base = float(base_cooloff_s)
        self._cap = max(float(max_cooloff_s), float(base_cooloff_s))
        self._clock = clock
        self._log = log if log is not None else logger
        self._lock = threading.RLock()
        self._window = self._base
        self._next_report_at: Optional[float] = None
        self._stalled = False
        self._ticks_stalled = 0
        self._reports_total = 0
        self._lost_reports = 0

    @property
    def stalled(self) -> bool:
        """True between a reported stop and the line that clears it."""
        with self._lock:
            return self._stalled

    @property
    def reports_total(self) -> int:
        """Console lines emitted since process start."""
        with self._lock:
            return self._reports_total

    @property
    def ticks_stalled(self) -> int:
        """Ticks that saw the stop, reported or suppressed."""
        with self._lock:
            return self._ticks_stalled

    @property
    def lost_reports(self) -> int:
        """Lines the logging subsystem itself refused."""
        with self._lock:
            return self._lost_reports

    def note(self, stalled_for_s: Optional[float]) -> bool:
        """Record one tick's reading and return True when it emitted a line.

        ``stalled_for_s`` is what ``stall_seconds`` answered.
        """
        with self._lock:
            now = self._clock()
            if stalled_for_s is None:
                return self._note_healthy()
            return self._note_stalled(now, float(stalled_for_s))

    def reset(self) -> None:
        """Clear the window and every counter. Test-only."""
        with self._lock:
            self._window = self._base
            self._next_report_at = None
            self._stalled = False
            self._ticks_stalled = 0

    def _note_stalled(self, now: float, stalled_for_s: float) -> bool:
        """Count one stopped tick and emit when the window has elapsed."""
        self._ticks_stalled += 1
        if self._next_report_at is not None and now < self._next_report_at:
            return False
        if self._stalled:
            self._window = min(self._cap, self._window * BACKOFF_FACTOR)
            level = logging.WARNING
            line = self._still_stopped_line(stalled_for_s)
        else:
            self._stalled = True
            self._window = self._base
            level = logging.ERROR
            line = self._stopped_line(stalled_for_s)
        self._next_report_at = now + self._window
        self._emit(level, line)
        return True

    def _note_healthy(self) -> bool:
        """Emit the resumed line when a stop was reported, else stay silent."""
        if not self._stalled:
            return False
        self._stalled = False
        self._window = self._base
        self._next_report_at = None
        self._ticks_stalled = 0
        self._emit(logging.WARNING, self._resumed_line())
        return True

    def _emit(self, level: int, message: str) -> None:
        """Write one finished line. A logging failure must not escape."""
        self._reports_total += 1
        try:
            self._log.log(level, "%s", message)
        except Exception:  # noqa: BLE001 - logging must not break a GUI pump
            self._lost_reports += 1

    def _stopped_line(self, stalled_for_s: float) -> str:
        """The first line of a stop, naming ``stalled_for_s`` in words."""
        return (
            "EXCHANGE FETCHING STOPPED - the platform has had nothing back "
            f"from the exchange for {span_words(stalled_for_s)}. Every price, "
            "balance and ammo figure on the screen is at least that old."
        )

    def _still_stopped_line(self, stalled_for_s: float) -> str:
        """The repeat line of a stop, naming ``stalled_for_s`` in words."""
        return (
            "EXCHANGE FETCHING STILL STOPPED - the platform has had nothing "
            f"back from the exchange for {span_words(stalled_for_s)}. Every "
            "price, balance and ammo figure on the screen is at least that "
            "old."
        )

    def _resumed_line(self) -> str:
        """The line that clears a reported stop."""
        return (
            "EXCHANGE FETCHING RESUMED - the exchange is answering again and "
            "the screen is live."
        )
