"""The signal vocabulary and the candle domain.

``Signal`` and ``SignalDirection`` carry one indicator's vote, and
``VotingSummary`` carries the aggregate. ``Candle`` and ``candles_from_raw``
hold the OHLCV rows every indicator reads.
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

# PERCENT_PER_RATIO_UNIT divides a percent threshold down to a ratio.
PERCENT_PER_RATIO_UNIT = 100.0


# HA_BODY_PCT_UNIT is one percentage point of HACandle.body_pct.
HA_BODY_PCT_UNIT = 1.0


# NO_SHRINK_RATIO is the ratio an unchanged body produces.
NO_SHRINK_RATIO = 1.0


# VOLUME_SPIKE_PCT is a multiple of the window's average volume, in percent.
VOLUME_SPIKE_PCT = 200.0


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
    weight: float = 1.0
    details: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    # abstained is no vote at all; a NEUTRAL direction is a measured result.
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

    ``candles_from_raw`` raises it, and it subclasses ``ValueError``.
    """


def _candle_field(value: object, field: str, row: int) -> float:
    """Return ``value`` as a finite float, or raise ``CandleDomainError``.

    The type test is exact, not ``isinstance``: ``bool`` subclasses ``int``.
    """
    if type(value) not in (int, float):
        raise CandleDomainError(f"row {row}: {field}={value!r} is not a number")
    number = float(value)
    if not math.isfinite(number):
        raise CandleDomainError(f"row {row}: {field}={value!r} is not finite")
    return number


def candles_from_raw(raw: Sequence[Sequence[object]]) -> list[Candle]:
    """Convert [[ts, O, H, L, C, V], ...] to a ``Candle`` list.

    A row shorter than six fields raises ``IndexError``.

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
