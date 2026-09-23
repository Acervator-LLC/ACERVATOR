"""Z-Score Predictive Zones of price against its own N-period mean.

``ZScoreIndicator.lines`` answers one ``ZScoreBar`` per candle;
``ZScoreIndicator.compute`` reads the last two into the Signal.
"""

from __future__ import annotations

from typing import NamedTuple, Optional

from .types import (
    SignalDirection,
    Signal,
)
from .helpers import (
    _window_has_no_range,
)


class ZScoreBar(NamedTuple):
    """One candle's Z-Score reading: the smoothed score, the two projected
    prices, and the window and reversal figures they came from."""

    z: float
    resistance_price: float
    support_price: float
    sma: float
    std: float
    z_raw: float
    target_z_high: float
    target_z_low: float
    peaks_held: int
    troughs_held: int
    z_volume_weighted: bool


#: One entry per candle, ``None`` before ``period`` bars and on a window
#: with no range.
_Line = list[Optional[ZScoreBar]]


def _window_zscore(closes: list, close: float) -> Optional[tuple]:
    """Mean, deviation and ``(close - mean) / deviation`` over ``closes``.

    ``None`` when ``closes`` has no range, so no caller divides by it.
    """
    if _window_has_no_range(closes):
        return None
    count = len(closes)
    mean = sum(closes) / count
    deviation = (sum((c - mean) ** 2 for c in closes) / count) ** 0.5
    return mean, deviation, (close - mean) / deviation


def _vwma(values: list, volumes: list, period: int) -> Optional[float]:
    """Mean of the last ``period`` ``values``, each weighted by its volume.

    ``None`` when those bars carry no volume to weight by.
    """
    weighted = 0.0
    volume = 0.0
    for value, size in zip(values[-period:], volumes[-period:]):
        weighted += value * size
        volume += size
    if volume <= 0.0:
        return None
    return weighted / volume


class _ReversalLevels:
    """The ``peaks`` and ``troughs`` of a z ``series``, judged as ``push`` grows it.

    A peak is above the ``bars`` readings each side and at or past
    ``threshold``; a trough is below them and at or past ``-threshold``.
    """

    def __init__(self, bars: int, threshold: float, depth: int):
        self.bars = bars
        self.threshold = threshold
        self.depth = depth
        self.series: list = []
        self.peaks: list = []
        self.troughs: list = []

    def push(self, value: float) -> None:
        """Append ``value``, then judge the reading ``bars`` behind it."""
        series = self.series
        series.append(value)
        bars = self.bars
        i = len(series) - 1 - bars
        if i < bars:
            return
        judged = series[i]
        neighbours = series[i - bars : i] + series[i + 1 : i + 1 + bars]
        if judged >= self.threshold and all(judged > other for other in neighbours):
            self.peaks.append(judged)
        elif judged <= -self.threshold and all(judged < other for other in neighbours):
            self.troughs.append(judged)

    def levels(self) -> tuple:
        """Mean of the last ``depth`` peaks and troughs, and how many each held."""
        held_peaks = self.peaks[-self.depth :]
        held_troughs = self.troughs[-self.depth :]
        return (
            sum(held_peaks) / len(held_peaks) if held_peaks else None,
            sum(held_troughs) / len(held_troughs) if held_troughs else None,
            len(held_peaks),
            len(held_troughs),
        )


# 10. Z-Score — Absolute statistical price deviation from mean
class ZScoreIndicator:
    """Z-Score Predictive Zones of the close against its own ``period`` mean.

    ``compute`` smooths ``z`` with ``_vwma``, averages the last
    ``lookback_depth`` reversals past ``reversal_threshold`` into
    ``target_z_high`` and ``target_z_low``, and projects each back to
    ``resistance_price`` and ``support_price``.
    """

    def __init__(
        self,
        period: int = 50,
        weight: float = 1.0,
        smoothing_period: int = 3,
        lookback_depth: int = 5,
        reversal_threshold: float = 2.0,
        pivot_bars: int = 1,
    ):
        self.period = period
        self.weight = weight
        self.smoothing_period = smoothing_period
        self.lookback_depth = lookback_depth
        self.reversal_threshold = reversal_threshold
        self.pivot_bars = pivot_bars

    def _abstain(self, timeframe: str) -> Signal:
        """The Signal ``compute`` returns with no z it can divide for."""
        return Signal(
            "zscore",
            timeframe,
            SignalDirection.NEUTRAL,
            0.0,
            self.weight,
            abstained=True,
        )

    def lines(self, candles: list) -> _Line:
        """One ``ZScoreBar`` per candle, for a chart to draw the score and its algo point.

        Each bar's ``z_raw`` is ``_window_zscore`` over the ``period`` closes
        ending there, ``z`` is ``_vwma`` over the last ``smoothing_period``
        readings, and ``resistance_price`` and ``support_price`` project
        ``_ReversalLevels`` back through that bar's ``sma`` and ``std``.
        """
        closes = [c.close for c in candles]
        end = len(candles)
        out: _Line = [None] * end

        # `_window_zscore` reads the closes the venue sent, so a halted
        # window answers None instead of rounding `deviation` to ULPs.
        z_series: list = []
        z_volumes: list = []
        reversals = _ReversalLevels(
            self.pivot_bars, self.reversal_threshold, self.lookback_depth
        )
        for i in range(self.period - 1, end):
            found = _window_zscore(closes[i - self.period + 1 : i + 1], closes[i])
            if found is None:
                continue
            sma, std, z_raw = found
            z_series.append(z_raw)
            z_volumes.append(candles[i].volume)
            reversals.push(z_raw)

            # A venue sending no volume leaves `_vwma` None, so `z` is
            # `z_raw` and `z_volume_weighted` publishes which `z` holds.
            smoothed = _vwma(z_series, z_volumes, self.smoothing_period)
            z = z_raw if smoothed is None else smoothed

            peak_z, trough_z, peaks_held, troughs_held = reversals.levels()
            target_z_high = self.reversal_threshold if peak_z is None else peak_z
            target_z_low = -self.reversal_threshold if trough_z is None else trough_z
            out[i] = ZScoreBar(
                z=z,
                resistance_price=sma + target_z_high * std,
                support_price=sma + target_z_low * std,
                sma=sma,
                std=std,
                z_raw=z_raw,
                target_z_high=target_z_high,
                target_z_low=target_z_low,
                peaks_held=peaks_held,
                troughs_held=troughs_held,
                z_volume_weighted=smoothed is not None,
            )
        return out

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        if len(candles) < self.period + 1:
            return self._abstain(timeframe)

        bars = self.lines(candles)
        last = bars[-1]
        if last is None:
            return self._abstain(timeframe)

        end = len(candles)
        sma, std, z_raw = last.sma, last.std, last.z_raw
        z = last.z
        z_volume_weighted = last.z_volume_weighted

        # A previous window with no range leaves `z_prev` at `z_raw`, which
        # holds `z_reverting` False.
        z_prev = z_raw
        if end >= self.period + 2 and bars[-2] is not None:
            z_prev = bars[-2].z_raw

        z_reverting = (z_raw > 0 and z_raw < z_prev) or (z_raw < 0 and z_raw > z_prev)

        peaks_held = last.peaks_held
        troughs_held = last.troughs_held
        target_z_high = last.target_z_high
        target_z_low = last.target_z_low

        resistance_price = last.resistance_price
        support_price = last.support_price

        in_resistance = z > target_z_high
        in_support = z < target_z_low

        # Extreme signals
        extreme_high = z > 3.0
        strong_high = z > 2.0
        mild_high = z > 1.5
        extreme_low = z < -3.0
        strong_low = z < -2.0
        mild_low = z < -1.5

        if in_resistance:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, (z - target_z_high) / 2.0 + 0.5))
        elif in_support:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, (target_z_low - z) / 2.0 + 0.5))
        elif mild_high:
            direction = SignalDirection.BEARISH
            confidence = 0.25
        elif mild_low:
            direction = SignalDirection.BULLISH
            confidence = 0.25
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="zscore",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "z": z,
                "z_prev": z_prev,
                "sma": sma,
                "std": std,
                "extreme_high": extreme_high,
                "strong_high": strong_high,
                "mild_high": mild_high,
                "extreme_low": extreme_low,
                "strong_low": strong_low,
                "mild_low": mild_low,
                "z_reverting": z_reverting,
                "z_raw": z_raw,
                "z_volume_weighted": z_volume_weighted,
                "target_z_high": target_z_high,
                "target_z_low": target_z_low,
                "resistance_price": resistance_price,
                "support_price": support_price,
                "peaks_held": peaks_held,
                "troughs_held": troughs_held,
                "in_resistance": in_resistance,
                "in_support": in_support,
            },
        )
