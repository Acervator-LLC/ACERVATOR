"""Z-Score Predictive Zones of price against its own N-period mean.

``ZScoreIndicator.compute`` returns the Signal.
"""

from __future__ import annotations

from typing import Optional

from .types import (
    SignalDirection,
    Signal,
)
from .helpers import (
    _window_has_no_range,
)


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


def _reversal_levels(series: list, bars: int, threshold: float, depth: int) -> tuple:
    """Mean of the last ``depth`` peaks and troughs in ``series``.

    A peak is above the ``bars`` readings each side and at or past
    ``threshold``; a trough is below them and at or past ``-threshold``.
    """
    peaks: list = []
    troughs: list = []
    for i in range(bars, len(series) - bars):
        value = series[i]
        neighbours = series[i - bars : i] + series[i + 1 : i + 1 + bars]
        if value >= threshold and all(value > other for other in neighbours):
            peaks.append(value)
        elif value <= -threshold and all(value < other for other in neighbours):
            troughs.append(value)
    held_peaks = peaks[-depth:]
    held_troughs = troughs[-depth:]
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

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        if len(candles) < self.period + 1:
            return self._abstain(timeframe)

        closes = [c.close for c in candles]
        end = len(candles)

        # `_window_zscore` reads the closes the venue sent, so a halted
        # window answers None instead of rounding `deviation` to ULPs.
        z_series: list = []
        z_volumes: list = []
        last_window = None
        for i in range(self.period - 1, end):
            found = _window_zscore(closes[i - self.period + 1 : i + 1], closes[i])
            if found is None:
                continue
            z_series.append(found[2])
            z_volumes.append(candles[i].volume)
            if i == end - 1:
                last_window = found

        if last_window is None:
            return self._abstain(timeframe)

        sma, std, z_raw = last_window

        # A venue sending no volume leaves `_vwma` None, so `z` is `z_raw`
        # and `z_volume_weighted` publishes which of the two `z` holds.
        smoothed = _vwma(z_series, z_volumes, self.smoothing_period)
        z_volume_weighted = smoothed is not None
        z = z_raw if smoothed is None else smoothed

        # A previous window with no range leaves `z_prev` at `z_raw`, which
        # holds `z_reverting` False.
        z_prev = z_raw
        if end >= self.period + 2:
            earlier = _window_zscore(closes[-self.period - 1 : -1], closes[-2])
            if earlier is not None:
                z_prev = earlier[2]

        z_reverting = (z_raw > 0 and z_raw < z_prev) or (z_raw < 0 and z_raw > z_prev)

        peak_z, trough_z, peaks_held, troughs_held = _reversal_levels(
            z_series,
            self.pivot_bars,
            self.reversal_threshold,
            self.lookback_depth,
        )
        target_z_high = self.reversal_threshold if peak_z is None else peak_z
        target_z_low = -self.reversal_threshold if trough_z is None else trough_z

        resistance_price = sma + target_z_high * std
        support_price = sma + target_z_low * std

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
