"""Z-Score of price against its own N-period mean.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)


# ---------------------------------------------------------------------------
# 10. Z-Score — Absolute statistical price deviation from mean
# ---------------------------------------------------------------------------
class ZScoreIndicator:
    """
    Z-Score of price: how many standard deviations is the current close
    from its N-period mean?

    Z = (close - SMA_N) / STD_N

    Why this is NOT redundant with Bollinger Bands:
      BB uses a 20-period window and normalises to *current* volatility.
      If volatility doubles, the bands widen — a price at bb_pos=0.95 no
      longer represents the same statistical stretch as before.
      Z-score uses a longer window (default 50) and is an absolute measure.
      It catches moves that the 20-period BB has already normalised away.

    Thresholds (empirical, robust across assets):
      |Z| < 0.5  = near mean, neutral
      Z > +1.5   = stretched high, mild scrum signal
      Z > +2.0   = statistically stretched, scrum confidence boost
      Z > +3.0   = rare extreme (top 0.13%), strong scrum
      Z < -1.5   = stretched low, mild fold signal
      Z < -2.0   = statistically stretched, fold confidence boost
      Z < -3.0   = rare extreme, very strong fold signal

    For accumulation:
      Z < -2.5 + Ichimoku below cloud + StochRSI oversold
      = three independent mathematical frameworks saying the same thing
      = maximum fold confidence convergence
    """

    def __init__(self, period: int = 50, weight: float = 1.0):
        self.period = period
        self.weight = weight

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        if len(candles) < self.period + 1:
            return Signal("zscore", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)

        closes = [c.close for c in candles[-self.period:]]
        sma    = sum(closes) / self.period
        variance = sum((c - sma)**2 for c in closes) / self.period
        std    = variance**0.5

        if std < 1e-9:
            return Signal("zscore", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)

        z = (candles[-1].close - sma) / std

        # Rate of Z change (is it moving toward or away from mean?)
        #
        # A previous window with no dispersion has no Z to compare
        # against: (close - mean) / 0 is 0/0. `z_prev = z` is this
        # module's own no-information fallback, already used when the
        # history is too short, and it leaves `z_reverting` False rather
        # than asserting a direction of travel that was never measured.
        #
        # The test is `< 1e-9`, character for character the one the
        # primary guard above applies to `std`. Reusing that threshold
        # rather than `std2 > 0.0` is deliberate: `std2` is derived and
        # rounds to ULPs rather than to zero on a halted window, so an
        # exact test would let a ~1e-17 denominator through. This
        # abstains, which is the safe direction, and invents no new
        # coefficient.
        z_prev = z
        if len(candles) >= self.period + 2:
            c_prev = [c.close for c in candles[-self.period-1:-1]]
            s2 = sum(c_prev) / self.period
            v2 = sum((c - s2)**2 for c in c_prev) / self.period
            std2 = v2**0.5
            if not std2 < 1e-9:
                z_prev = (candles[-2].close - s2) / (std2 + 1e-9)

        z_reverting = (z > 0 and z < z_prev) or (z < 0 and z > z_prev)

        # Extreme signals
        extreme_high = z >  3.0
        strong_high  = z >  2.0
        mild_high    = z >  1.5
        extreme_low  = z < -3.0
        strong_low   = z < -2.0
        mild_low     = z < -1.5

        if strong_high:
            direction  = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, (z - 2.0) / 2.0 + 0.5))
        elif strong_low:
            direction  = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, (-z - 2.0) / 2.0 + 0.5))
        elif mild_high:
            direction  = SignalDirection.BEARISH
            confidence = 0.25
        elif mild_low:
            direction  = SignalDirection.BULLISH
            confidence = 0.25
        else:
            direction  = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="zscore",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "z":            round(z, 3),
                "z_prev":       round(z_prev, 3),
                "sma":          round(sma, 6),
                "std":          round(std, 6),
                "extreme_high": extreme_high,
                "strong_high":  strong_high,
                "mild_high":    mild_high,
                "extreme_low":  extreme_low,
                "strong_low":   strong_low,
                "mild_low":     mild_low,
                "z_reverting":  z_reverting,
            },
        )
