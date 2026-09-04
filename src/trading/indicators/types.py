"""The signal vocabulary and the candle domain.

Shared by every indicator: the words a vote is said in, and the
constraints a candle passes before any arithmetic sees it. Data and
types only -- no indicator maths lives here.
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
# A threshold that bounds a RATIO is carried in PERCENT and divided by
# this constant once, so both operands of the comparison are ratios.
PERCENT_PER_RATIO_UNIT = 100.0


# One percentage point of a candle's own high-low range: the unit
# `HACandle.body_pct` is measured in.
HA_BODY_PCT_UNIT = 1.0


# A body that did not shrink at all: norm[j] == norm[j - 1].
NO_SHRINK_RATIO = 1.0


# A volume spike is this percentage of the window's average volume.
VOLUME_SPIKE_PCT = 200.0


# ---------------------------------------------------------------------------
# Core data types
# ---------------------------------------------------------------------------
class SignalDirection(int, Enum):
    BEARISH = -1
    NEUTRAL = 0
    BULLISH = 1


@dataclass
class Signal:
    """One indicator's output at a point in time."""

    indicator: str
    timeframe: str
    direction: SignalDirection
    confidence: float  # 0.0 - 1.0
    weight: float = 1.0  # Configurable importance
    details: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    # ``True`` means this indicator CAST NO VOTE: too little history for
    # its formula, or a denominator that was exactly zero on an
    # admissible bar. ``direction is NEUTRAL`` is the other statement --
    # the indicator MEASURED and found no direction.
    #
    # ``VotingEngine._aggregate`` divides by the summed weight, so an
    # abstention has to be declared rather than inferred from an empty
    # ``details``: ``rsi.py`` returns a fabricated ``{"rsi": 50.0, ...}``
    # on a tape shorter than ``period + 1``.
    #
    # It sits AFTER ``timestamp`` because ``Signal`` is built
    # positionally in this tree; inserting it earlier would re-bind the
    # seventh positional argument from a wall clock to a boolean.
    abstained: bool = False

    @property
    def weighted_score(self) -> float:
        """Signed score: direction * confidence * weight."""
        return self.direction.value * self.confidence * self.weight


@dataclass
class VotingSummary:
    """Aggregated result of all indicator votes."""

    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    total_bullish_score: float = 0.0
    total_bearish_score: float = 0.0
    net_score: float = 0.0  # Positive = bullish consensus
    consensus_confidence: float = 0.0  # 0.0 - 1.0
    signals: list[Signal] = field(default_factory=list)
    timeframe: str = ""

    @property
    def consensus_direction(self) -> SignalDirection:
        if self.net_score > 0.1:
            return SignalDirection.BULLISH
        elif self.net_score < -0.1:
            return SignalDirection.BEARISH
        return SignalDirection.NEUTRAL


# ---------------------------------------------------------------------------
# OHLCV candle helper
# ---------------------------------------------------------------------------
@dataclass
class Candle:
    """Single OHLCV candle."""

    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleDomainError(ValueError):
    """A raw OHLCV row carried a value that is not a price.

    A ``ValueError``, so the call sites that already guard
    :func:`candles_from_raw` with ``except Exception`` catch it through
    the handlers that exist instead of needing new ones.
    """


# THE CLOSED DOMAIN OF AN OHLC BAR
# --------------------------------
# Each constraint is the DEFINITION of an OHLC bar, so none of them is
# calibrated and none invents a scale:
#
#   * every field is a real, finite number -- NaN, an infinity, a bool
#     and a string are not quantities a price can take;
#   * open/high/low/close are PRICES, and a traded price is > 0;
#   * ``low <= high``, because the two name one range;
#   * ``low <= open <= high`` and ``low <= close <= high``, because the
#     open and the close are trades that happened INSIDE that range.
#
# A bar that is internally consistent but absurd against its NEIGHBOURS
# -- a x1000 spike that lifts close and high together -- passes.
# Refusing that needs a threshold no published source supplies.


def _candle_field(value: object, field: str, row: int) -> float:
    """Return ``value`` as a finite float, or refuse it.

    The type test is EXACT, not ``isinstance``: ``bool`` is a subclass of
    ``int``, so a price of ``True`` would coerce to 1.0 and read as a
    dollar. Nothing on the candle path produces a numeric subclass --
    there is no numpy and no Decimal anywhere in it.
    """
    if type(value) not in (int, float):
        raise CandleDomainError(f"row {row}: {field}={value!r} is not a number")
    number = float(value)
    if not math.isfinite(number):
        raise CandleDomainError(f"row {row}: {field}={value!r} is not finite")
    return number


def candles_from_raw(raw: Sequence[Sequence[object]]) -> list[Candle]:
    """Convert [[ts, O, H, L, C, V], ...] to Candle list.

    Refuses any row outside the closed domain described above, so a
    value that is not a price cannot reach an indicator's arithmetic.
    A short row still raises ``IndexError`` exactly as it always has.

    Raises
    ------
    CandleDomainError
        A field is not a finite number, a price is not positive, a
        volume is negative, or the bar's own range is contradictory.
    """
    out: list[Candle] = []
    for row, r in enumerate(raw):
        timestamp = _candle_field(r[0], "timestamp", row)
        open_px = _candle_field(r[1], "open", row)
        high_px = _candle_field(r[2], "high", row)
        low_px = _candle_field(r[3], "low", row)
        close_px = _candle_field(r[4], "close", row)
        volume = _candle_field(r[5], "volume", row)

        for name, price in (
            ("open", open_px),
            ("high", high_px),
            ("low", low_px),
            ("close", close_px),
        ):
            if price <= 0.0:
                raise CandleDomainError(
                    f"row {row}: {name}={price!r} is not a positive price"
                )
        if volume < 0.0:
            raise CandleDomainError(f"row {row}: volume={volume!r} is negative")
        if low_px > high_px:
            raise CandleDomainError(
                f"row {row}: low={low_px!r} is above high={high_px!r}"
            )
        if not low_px <= open_px <= high_px:
            raise CandleDomainError(
                f"row {row}: open={open_px!r} is outside "
                f"[low={low_px!r}, high={high_px!r}]"
            )
        if not low_px <= close_px <= high_px:
            raise CandleDomainError(
                f"row {row}: close={close_px!r} is outside "
                f"[low={low_px!r}, high={high_px!r}]"
            )

        out.append(Candle(timestamp, open_px, high_px, low_px, close_px, volume))
    return out
