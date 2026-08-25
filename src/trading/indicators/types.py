"""The signal vocabulary and the candle domain.

Shared by every indicator: the words a vote is said in, and
the gate a candle passes before any arithmetic sees it. Data
and types only -- no indicator maths lives here.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
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
# A threshold that a RATIO is measured against has to be a ratio too.
# Bollinger's `squeeze` compared a dimensionless band width against an
# ABSOLUTE price width and the flag collapsed into a test on price:
# measured across 35 fleet symbols, every symbol at or below $0.42
# squeezed on 0.0% of windows and every symbol at or above $8.28 on
# 100.0%. The repair that landed did not add a comment -- it divided
# the other operand by the same quantity, so both sides of the `<`
# were built the same way.
#
# Thresholds that bound a ratio are therefore carried in PERCENT and
# converted down into ratio space once, through this constant, the way
# src/trading/extractor_bot.py states its rate-spike limit.
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
    confidence: float  # 0.0 – 1.0
    weight: float = 1.0  # Configurable importance
    details: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    # THE VOTER SAYS WHETHER IT VOTED
    # ------------------------------
    # True means this indicator CAST NO VOTE: it had too little history
    # to evaluate its formula, or the formula's denominator was exactly
    # zero on an admissible bar, so the quantity is undefined. It is NOT
    # the same statement as ``direction is NEUTRAL``, which means the
    # indicator MEASURED and found no direction.
    #
    # The two were numerically indistinguishable before issue #100.
    # Both produce ``direction=NEUTRAL, confidence=0.0``, so both add
    # nothing to ``VotingSummary.net_score`` -- and both still added
    # their full weight to the denominator ``VotingEngine._aggregate``
    # divides by. A voter that supplied no value from any data source
    # was therefore a term in a weighted mean, which is the one thing a
    # weighted mean's denominator may not contain.
    #
    # WHY A FIELD AND NOT AN INFERENCE. Every warm-up guard in this
    # package happens to return with no ``details``, so ``details == {}``
    # reads as an abstention today. That is a coincidence of how the
    # guards were typed, is asserted nowhere, and is ALREADY FALSE for
    # one voter: ``rsi.py`` returns a fabricated ``{"rsi": 50.0, ...}``
    # on a tape shorter than ``period + 1``, so its abstention looks
    # like a measurement. An inference that is already wrong once is not
    # a signal.
    #
    # APPENDED AFTER ``timestamp``, DELIBERATELY. ``Signal`` is built
    # positionally in this tree -- five arguments at every guard, six
    # and seven in ``tests/test_indicator_numeric_identity.py``. A field
    # inserted before ``timestamp`` would silently re-bind the seventh
    # positional argument from a wall clock to a boolean.
    abstained: bool = False

    @property
    def weighted_score(self) -> float:
        """Signed score: direction × confidence × weight."""
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
    consensus_confidence: float = 0.0  # 0.0 – 1.0
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

    Deliberately a ``ValueError``: every call site that already guards
    :func:`candles_from_raw` catches ``Exception``, so this raises
    through the handlers that exist instead of needing new ones.
    """


# THE CLOSED DOMAIN OF AN OHLC BAR
# --------------------------------
# Each constraint below is the DEFINITION of an OHLC bar. None of them
# is calibrated, so none of them invents a scale:
#
#   * every field is a real, finite number -- NaN, an infinity, a bool
#     and a string are not quantities a price can take;
#   * open/high/low/close are PRICES, and a traded price is > 0;
#   * ``low <= high``, because the two name one range;
#   * ``low <= open <= high`` and ``low <= close <= high``, because the
#     open and the close are trades that happened INSIDE that range.
#
# WHY THE DOMAIN IS THE REPAIR, AND NOT A COEFFICIENT. Measured on this
# tree: one ``close = 0.0`` in a 100-bar window moves 10 of the 12
# wired indicators, and 4 of them are still wrong 60 bars later.
# Slingshot's ``penetration * 8`` turning that bar into BULLISH at
# confidence 1.0000 is one symptom out of ten, so the coefficient is
# not the seat of the defect. Re-tuning it would fabricate a confidence
# scale no published source defines, and would leave the other nine
# exactly as exposed.
#
# WHAT IS DELIBERATELY NOT REFUSED. A bar that is internally consistent
# but absurd against its NEIGHBOURS -- a x1000 spike that lifts close
# and high together -- passes this screen. Calling that invalid needs a
# threshold; no published source supplies one; inventing one here is
# the exact fabrication this screen exists to avoid.


def _candle_field(value: object, field: str, row: int) -> float:
    """Return ``value`` as a finite float, or refuse it.

    The type test is EXACT, not ``isinstance``. ``isinstance`` admits
    subclasses, and ``bool`` is a subclass of ``int``: a price of
    ``True`` would coerce to 1.0 and read as a dollar. Nothing on the
    candle path produces a numeric subclass -- there is no numpy and no
    Decimal anywhere in it -- so exactness costs nothing here and shuts
    that door instead of naming one subclass and missing the rest.
    """
    if type(value) not in (int, float):
        raise CandleDomainError(f"row {row}: {field}={value!r} is not a number")
    number = float(value)
    if not math.isfinite(number):
        raise CandleDomainError(f"row {row}: {field}={value!r} is not finite")
    return number


def candles_from_raw(raw: Sequence[Sequence[object]]) -> list[Candle]:

    # sadp: R28  # candle conversion: fail-loudly on malformed data(R28)
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
