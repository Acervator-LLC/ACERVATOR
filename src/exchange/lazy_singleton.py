"""Cached singleton with a cooling-off period after a construction failure.

The plain ``if _GLOBAL is None: _GLOBAL = Cls()`` retries on every call.
When construction keeps failing that is one attempt and one log line per
2 s GUI tick, without end.

``LazySingleton.get`` returns the instance, or None while the feature is
down. It never raises. ``ThrottledFault`` holds the reporting policy:
first failure at ERROR, one summary per window at WARNING, one line on
recovery. The window starts at 30 s and doubles to a 300 s ceiling —
291 attempts a day, against 43,200 at tick rate.

``has_stopped`` is the owner's own test for an instance that constructed
and then stopped updating. ``get`` rebuilds such an instance once per
window and keeps serving the cached one until the factory answers, so a
singleton that has answered once never reverts to None.

``carry_reading`` moves the stopped instance's reading onto its
replacement, so a replacement never starts empty and the screens drawing
that reading keep their last figures while the feed recovers. Each owner
supplies its own, naming what its reading is.

``note_cleared`` carries the same window over a blocked fetch path, which
no singleton owns: ``MarketDataPool._clear_wedged_lock`` calls it when it
replaces a fetch lock whose holder never finished. ``CCXTConnector`` calls
it twice more, for a leaked worker thread and for a trade-history scan
whose lock holder stopped answering.

``_describe`` guards ``str(exc)``. An exception whose ``__str__`` raises
propagates out of the logging call and into the caller. Measured.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Generic, TypeVar

logger = logging.getLogger("acervator.lazy_singleton")

#: First cooling-off window, seconds.
DEFAULT_BASE_COOLOFF_S = 30.0
#: Ceiling the window doubles up to, seconds.
DEFAULT_MAX_COOLOFF_S = 300.0
#: Window multiplier per further failure.
BACKOFF_FACTOR = 2.0

T = TypeVar("T")


def _describe(exc: BaseException) -> str:
    """Render an exception for a log line. Never raises."""
    name = type(exc).__name__
    try:
        detail = str(exc)
    except Exception:  # noqa: BLE001 - a __str__ that raises must not escape
        detail = "<the exception could not be rendered>"
    return f"{name}: {detail}"


class ThrottledFault:
    """Reports a repeating fault once per cooling-off window, never per call.

    Owns the window, so the caller that skips work and the caller that
    reports the failure read one clock.
    """

    def __init__(
        self,
        feature: str,
        impact: str,
        *,
        base_cooloff_s: float = DEFAULT_BASE_COOLOFF_S,
        max_cooloff_s: float = DEFAULT_MAX_COOLOFF_S,
        clock: Callable[[], float] = time.monotonic,
        log: logging.Logger | None = None,
    ) -> None:
        """``feature`` names what stopped. ``impact`` says what is lost.

        Both go into every line. ``clock`` is injectable for tests and
        defaults to ``time.monotonic``, so a system clock change cannot
        move a window.
        """
        self._feature = feature
        self._impact = impact
        self._base = float(base_cooloff_s)
        self._cap = max(float(max_cooloff_s), float(base_cooloff_s))
        self._clock = clock
        self._log = log if log is not None else logger
        self._lock = threading.RLock()
        self._window = self._base
        self._next_report_at: float | None = None
        self._offline = False
        self._failures = 0
        self._successes = 0
        self._suppressed = 0
        self._last_detail = ""
        self._reports_total = 0
        self._failures_total = 0
        self._suppressed_total = 0
        self._lost_reports = 0

    # -- observation ---------------------------------------------------
    @property
    def offline(self) -> bool:
        """True between a reported failure and its recovery line."""
        with self._lock:
            return self._offline

    @property
    def reports_total(self) -> int:
        """Log lines emitted since process start."""
        with self._lock:
            return self._reports_total

    @property
    def failures_total(self) -> int:
        """Failures recorded since process start."""
        with self._lock:
            return self._failures_total

    @property
    def suppressed_total(self) -> int:
        """Calls skipped inside a cooling-off window."""
        with self._lock:
            return self._suppressed_total

    @property
    def lost_reports(self) -> int:
        """Lines the logging subsystem itself refused."""
        with self._lock:
            return self._lost_reports

    def quiet(self) -> bool:
        """True while the cooling-off window runs. Callers that can skip ask."""
        with self._lock:
            return self._quiet(self._clock())

    # -- recording -----------------------------------------------------
    def note_skip(self) -> None:
        """Count a call the cooling-off refused."""
        with self._lock:
            self._suppressed += 1
            self._suppressed_total += 1

    def note_failure(self, exc: BaseException) -> None:
        """Record a failure. Emits at most one line per window."""
        with self._lock:
            now = self._clock()
            self._failures += 1
            self._failures_total += 1
            self._last_detail = _describe(exc)
            if self._quiet(now):
                return
            if not self._offline:
                self._offline = True
                self._window = self._base
                level = logging.ERROR
                line = self._offline_line()
            else:
                self._window = min(self._cap, self._window * BACKOFF_FACTOR)
                level = logging.WARNING
                line = self._still_offline_line()
            self._next_report_at = now + self._window
            self._emit(level, line)
            self._reset_counts()

    def note_success(self) -> None:
        """Record a success. Emits the recovery line if a failure was reported.

        The window floor applies, so a flapping feature cannot emit a
        line per tick.
        """
        with self._lock:
            now = self._clock()
            self._successes += 1
            if not self._offline or self._quiet(now):
                return
            line = self._restored_line()
            self._offline = False
            self._window = self._base
            self._next_report_at = now + self._base
            self._emit(logging.WARNING, line)
            self._reset_counts()

    def note_rebuild(self, *, reading_carried: bool = False) -> None:
        """Report one rebuilt instance and start the next window.

        ``reading_carried`` says whether the replacement took the stopped
        instance's reading, so the line names what the screens now draw.
        """
        with self._lock:
            self._next_report_at = self._clock() + self._window
            self._emit(logging.WARNING, self._rebuilt_line(reading_carried))
            self._window = min(self._cap, self._window * BACKOFF_FACTOR)
            self._reset_counts()

    def note_cleared(self, detail: str, held_s: float) -> bool:
        """Report one blocked path cleared, at most one line per window.

        ``detail`` names what was blocked and ``held_s`` how long for. Every
        call counts; the return says whether a line was emitted, and a
        suppressed one is carried into the next line's tally.
        """
        with self._lock:
            now = self._clock()
            self._failures += 1
            self._failures_total += 1
            self._last_detail = detail
            if self._quiet(now):
                self._suppressed += 1
                self._suppressed_total += 1
                return False
            line = self._cleared_line(held_s)
            self._next_report_at = now + self._window
            self._emit(logging.ERROR, line)
            self._window = min(self._cap, self._window * BACKOFF_FACTOR)
            self._reset_counts()
            return True

    def reset(self) -> None:
        """Clear the window and every counter. Test-only."""
        with self._lock:
            self._window = self._base
            self._next_report_at = None
            self._offline = False
            self._last_detail = ""
            self._reset_counts()

    # -- internals -----------------------------------------------------
    def _quiet(self, now: float) -> bool:
        return self._next_report_at is not None and now < self._next_report_at

    def _reset_counts(self) -> None:
        self._failures = 0
        self._successes = 0
        self._suppressed = 0

    def _emit(self, level: int, message: str) -> None:
        """Write one finished line. A logging failure must not escape."""
        self._reports_total += 1
        try:
            self._log.log(level, "%s", message)
        except Exception:  # noqa: BLE001 - logging must not break a GUI pump
            self._lost_reports += 1

    def _offline_line(self) -> str:
        return (
            f"FEATURE OFFLINE - {self._feature} has stopped working. "
            f"{self._impact} Trading and order placement are not affected. "
            f"Retrying in {self._window:.0f} s. "
            f"Cause: {self._last_detail}"
        )

    def _still_offline_line(self) -> str:
        return (
            f"FEATURE STILL OFFLINE - {self._feature} is still not working. "
            f"{self._impact} Since the last report: {self._failures} "
            f"attempt(s) failed and {self._suppressed} call(s) were "
            f"suppressed. Next retry in {self._window:.0f} s. "
            f"Cause: {self._last_detail}"
        )

    def _restored_line(self) -> str:
        return (
            f"FEATURE RESTORED - {self._feature} is working again. "
            f"Since the last report: {self._failures} attempt(s) failed "
            f"and {self._suppressed} call(s) were suppressed."
        )

    def _rebuilt_line(self, reading_carried: bool = False) -> str:
        if reading_carried:
            readings = (
                "Its last readings are held and marked until the next "
                "refresh lands new ones."
            )
        else:
            readings = (
                "Its last readings are gone and new ones start at the next refresh."
            )
        return (
            f"FEATURE REBUILT - {self._feature} had stopped updating and has "
            f"been built again. {readings} No further rebuild for "
            f"{self._window:.0f} s."
        )

    def _cleared_line(self, held_s: float) -> str:
        return (
            f"FETCH PATH CLEARED - {self._feature} was blocked for "
            f"{held_s:.0f} s and has been cleared, so fetching starts again "
            f"without a restart. {self._impact} Since the last report: "
            f"{self._failures} path(s) blocked and {self._suppressed} "
            f"clearance(s) were not reported. No further report for "
            f"{self._window:.0f} s. Blocked: {self._last_detail}"
        )


class LazySingleton(Generic[T]):
    """Caches on first use. Cools off instead of storming on a failure."""

    def __init__(
        self,
        factory: Callable[[], T],
        feature: str,
        impact: str,
        *,
        has_stopped: Callable[[T], bool] | None = None,
        carry_reading: Callable[[T, T], None] | None = None,
        base_cooloff_s: float = DEFAULT_BASE_COOLOFF_S,
        max_cooloff_s: float = DEFAULT_MAX_COOLOFF_S,
        clock: Callable[[], float] = time.monotonic,
        log: logging.Logger | None = None,
    ) -> None:
        """Wrap ``factory``. ``feature`` and ``impact`` reach every log line.

        ``has_stopped`` answers whether a cached instance has stopped
        updating, and ``get`` builds a replacement for one that has.
        ``carry_reading`` is handed the stopped instance and its
        replacement, and moves the reading from the first to the second.
        """
        self._factory = factory
        self._has_stopped = has_stopped
        self._carry_reading = carry_reading
        self._instance: T | None = None
        self._lock = threading.RLock()
        self._constructions = 0
        self._fault = ThrottledFault(
            feature,
            impact,
            base_cooloff_s=base_cooloff_s,
            max_cooloff_s=max_cooloff_s,
            clock=clock,
            log=log,
        )

    @property
    def fault(self) -> ThrottledFault:
        """The fault record behind this singleton."""
        return self._fault

    @property
    def constructions(self) -> int:
        """Factory calls made."""
        with self._lock:
            return self._constructions

    @property
    def available(self) -> bool:
        """True once an instance is cached."""
        with self._lock:
            return self._instance is not None

    def get(self) -> T | None:
        """Return the instance, or None while it is down. Never raises.

        None means skip the feature this tick. The failure is already
        reported and the next attempt is already scheduled. A cached
        instance ``has_stopped`` reports stopped is replaced, and the
        cached one is served until the factory answers. ``carry_reading``
        moves the stopped instance's reading onto the replacement before
        it is cached, so no reader is ever handed an empty replacement.
        """
        with self._lock:
            cached = self._instance
            reading_carried = False
            try:
                if cached is not None and not self._stopped(cached):
                    return cached
                if self._fault.quiet():
                    self._fault.note_skip()
                    return cached
                self._constructions += 1
                instance = self._factory()
                if cached is not None and self._carry_reading is not None:
                    self._carry_reading(cached, instance)
                    reading_carried = True
            except Exception as exc:  # noqa: BLE001 - a pump must not raise
                self._fault.note_failure(exc)
                return cached
            self._instance = instance
            if cached is None:
                self._fault.note_success()
            else:
                self._fault.note_rebuild(reading_carried=reading_carried)
            return instance

    def _stopped(self, instance: T) -> bool:
        """True when ``has_stopped`` is set and reports ``instance`` stopped."""
        return self._has_stopped is not None and self._has_stopped(instance)

    def reset(self) -> None:
        """Drop the instance and clear the cooling-off. Test-only."""
        with self._lock:
            self._instance = None
            self._constructions = 0
            self._fault.reset()
