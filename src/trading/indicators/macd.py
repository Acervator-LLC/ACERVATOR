"""MACD -- Gerald Appel's moving-average convergence/divergence.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
    Candle,
)
from .helpers import (
    _ema,
)


# ---------------------------------------------------------------------------
# 3. MACD
# ---------------------------------------------------------------------------
class MACD:
    """
    MACD: EMA(12) - EMA(26), Signal EMA(9), Histogram.
    Enhanced with divergence detection.
    """

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9, weight: float = 1.0):
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self.weight = weight

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        closes = [c.close for c in candles]
        if len(closes) < self.slow + self.signal_period:
            return Signal("macd", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)

        ema_fast = _ema(closes, self.fast)
        ema_slow = _ema(closes, self.slow)
        macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
        signal_line = _ema(macd_line, self.signal_period)
        histogram = [m - s for m, s in zip(macd_line, signal_line)]

        curr_hist = histogram[-1]
        prev_hist = histogram[-2] if len(histogram) > 1 else 0
        curr_macd = macd_line[-1]
        curr_signal = signal_line[-1]
        prev_macd = macd_line[-2] if len(macd_line) > 1 else 0
        prev_signal = signal_line[-2] if len(signal_line) > 1 else 0

        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        crossover = False
        divergence = ""

        # Crossover detection
        if prev_macd <= prev_signal and curr_macd > curr_signal:
            direction = SignalDirection.BULLISH
            crossover = True
            confidence = max(0.0, min(
                1.0,
                abs(curr_hist) / (abs(closes[-1]) * 0.001 + 1e-9) * 0.3 + 0.5))
        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            direction = SignalDirection.BEARISH
            crossover = True
            confidence = max(0.0, min(
                1.0,
                abs(curr_hist) / (abs(closes[-1]) * 0.001 + 1e-9) * 0.3 + 0.5))
        elif curr_hist > 0 and curr_hist > prev_hist:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(
                0.6,
                abs(curr_hist) / (abs(closes[-1]) * 0.002 + 1e-9)))
        elif curr_hist < 0 and curr_hist < prev_hist:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(
                0.6,
                abs(curr_hist) / (abs(closes[-1]) * 0.002 + 1e-9)))
        elif curr_hist > 0:
            direction = SignalDirection.BULLISH
            confidence = 0.15
        elif curr_hist < 0:
            direction = SignalDirection.BEARISH
            confidence = 0.15

        # Divergence detection (price makes new low but MACD doesn't)
        if len(closes) >= 20 and len(macd_line) >= 20:
            price_low = min(closes[-20:])
            price_prev_low = min(closes[-40:-20]) if len(closes) >= 40 else price_low
            macd_low = min(macd_line[-20:])
            macd_prev_low = min(macd_line[-40:-20]) if len(macd_line) >= 40 else macd_low

            if closes[-1] <= price_low and price_low < price_prev_low and macd_low > macd_prev_low:
                divergence = "bullish"
                direction = SignalDirection.BULLISH
                confidence = min(1.0, max(confidence, 0.7))
            elif closes[-1] >= max(closes[-20:]) and max(closes[-20:]) > max(closes[-40:-20] if len(closes) >= 40 else closes[-20:]):
                macd_high = max(macd_line[-20:])
                macd_prev_high = max(macd_line[-40:-20]) if len(macd_line) >= 40 else macd_high
                if macd_high < macd_prev_high:
                    divergence = "bearish"
                    direction = SignalDirection.BEARISH
                    confidence = min(1.0, max(confidence, 0.7))

        return Signal(
            indicator="macd",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "macd_line": round(curr_macd, 6), "signal_line": round(curr_signal, 6),
                "histogram": round(curr_hist, 6), "crossover": crossover,
                "divergence": divergence,
            },
        )


    def compute_histogram_series(self, candles: list, n: int = 12) -> list:


        # sadp: R28  # indicator compute: fail-loudly(R28)
        """
        Return the last `n` MACD histogram values as a list (oldest→newest).

        Single O(N) computation — more efficient than calling compute() N times.
        Used by the simulator snapshot to populate macd_histogram_buf, which
        feeds detect_macd_taper() in the confidence gate.

        Returns [] if fewer candles than the MACD warmup period.
        """
        closes = [c.close for c in candles]
        min_len = self.slow + self.signal_period
        if len(closes) < min_len:
            return []
        ema_fast   = _ema(closes, self.fast)
        ema_slow   = _ema(closes, self.slow)
        macd_line  = [f - s for f, s in zip(ema_fast, ema_slow)]
        signal_line = _ema(macd_line, self.signal_period)
        histogram   = [m - s for m, s in zip(macd_line, signal_line)]
        return histogram[-n:]
