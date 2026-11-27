"""How old a price may be when an order starts on it or a cell draws it:
``BotContainer.order_refusal`` and ``TableCellsModel`` both read ``price_age_limit_s``.
"""

from __future__ import annotations

import math
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Optional

#: Seconds ``price_age_limit_s`` answers where ``PRICE_AGE_SETTING`` holds no usable one.
DEFAULT_PRICE_AGE_LIMIT_S = 20.0

#: The ``AppSettings`` field ``price_age_limit_s`` reads.
PRICE_AGE_SETTING = "price_age_limit_s"

#: Lifetimes of a stored price in the least limit: one served, one for the calls after.
LIFETIMES_IN_LEAST_LIMIT = 2

#: Tenths of a second in one second, the grain ``shown_age`` rounds up to.
TENTHS_PER_SECOND = 10.0

#: Decimal places of a second ``shown_age`` reads, past which a clock holds noise.
CLOCK_DECIMALS = 6


@dataclass(frozen=True)
class ReadMoment:
    """When a venue answered: ``wall_s`` on ``time.time``, and ``mono_s`` on
    ``time.monotonic`` where this run saw it."""

    wall_s: float
    mono_s: Optional[float] = None

    @classmethod
    def now(cls) -> ReadMoment:
        """This moment on both clocks."""
        return cls(time.time(), time.monotonic())

    @classmethod
    def at_monotonic(cls, mono_s: float) -> ReadMoment:
        """The moment ``time.monotonic`` read ``mono_s``."""
        return cls(time.time() - (time.monotonic() - mono_s), mono_s)

    def age_s(self) -> float:
        """Seconds since this moment: the larger of what the two clocks read, and never
        below zero."""
        ran_s = 0.0 if self.mono_s is None else time.monotonic() - self.mono_s
        return max(0.0, time.time() - self.wall_s, ran_s)

    def before(self, other: ReadMoment) -> bool:
        """True where this moment came first, read off ``mono_s`` where both hold one."""
        if self.mono_s is not None and other.mono_s is not None:
            return self.mono_s < other.mono_s
        return self.wall_s < other.wall_s


@dataclass
class LimitSource:
    """What ``price_age_limit_s`` reads ``PRICE_AGE_SETTING`` from."""

    settings: Any = None


_LIMIT_SOURCE = LimitSource()


def read_limit_from(settings: Any) -> None:
    """Read the limit from ``settings``, a ``SettingsManager``, at every later call."""
    _LIMIT_SOURCE.settings = settings


def limit_range_s() -> tuple[int, int]:
    """The least and the most whole seconds a limit takes, off ``TICKER_TTL_SECONDS`` and
    ``STALL_THRESHOLD_SECONDS``; the Settings row reads it too."""
    from ..exchange.data_pool import TICKER_TTL_SECONDS
    from ..exchange.fetch_stall import STALL_THRESHOLD_SECONDS

    least = int(LIFETIMES_IN_LEAST_LIMIT * TICKER_TTL_SECONDS)
    return least, int(STALL_THRESHOLD_SECONDS)


def is_usable_limit(held: Any) -> bool:
    """True where ``held`` is a whole number of seconds inside ``limit_range_s``."""
    least, most = limit_range_s()
    if type(held) not in (int, float) or not least <= held <= most:
        return False
    return float(held).is_integer()


def usable_limit_s(held: Any) -> float:
    """``held`` as a limit, ``DEFAULT_PRICE_AGE_LIMIT_S`` where ``is_usable_limit``
    refuses it."""
    return float(held) if is_usable_limit(held) else DEFAULT_PRICE_AGE_LIMIT_S


def price_age_limit_s() -> float:
    """Seconds a price may be old, the one figure the order path and the screen read."""
    settings = _LIMIT_SOURCE.settings
    if settings is None:
        return DEFAULT_PRICE_AGE_LIMIT_S
    return usable_limit_s(settings.get(PRICE_AGE_SETTING, DEFAULT_PRICE_AGE_LIMIT_S))


def past_age_limit(age_s: float) -> bool:
    """True where a price ``age_s`` old is past ``price_age_limit_s``, a not-a-number age
    included."""
    return not age_s <= price_age_limit_s()


def shown_age(age_s: float) -> str:
    """``age_s`` for a line the operator reads, rounded up to one tenth of a second."""
    if not math.isfinite(age_s):
        return f"{age_s}"
    tenths = math.ceil(round(age_s, CLOCK_DECIMALS) * TENTHS_PER_SECOND)
    return f"{tenths / TENTHS_PER_SECOND:,.1f}"


@dataclass(frozen=True)
class PriceRead:
    """One price a decision stands on: ``what`` it is, and ``at``, None for no read time."""

    what: str
    at: Optional[ReadMoment]

    def wait(self) -> str:
        """Why no order starts on this price now, empty while one may."""
        if self.at is None:
            return f"{self.what} carries no read time"
        age_s = self.at.age_s()
        if not past_age_limit(age_s):
            return ""
        return (
            f"{self.what} is {shown_age(age_s)}s old, past the "
            f"{price_age_limit_s():g}s limit"
        )


def first_wait(reads: Iterable[PriceRead]) -> str:
    """The first ``PriceRead.wait`` among ``reads`` that names one, else empty."""
    return next((wait for wait in (read.wait() for read in reads) if wait), "")
