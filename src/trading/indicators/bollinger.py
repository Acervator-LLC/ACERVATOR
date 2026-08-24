"""John Bollinger's bands: SMA(20) +/- 2 sigma.

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
    _sma_tail,
    _stdev_tail,
    _window_has_no_range,
)


# ---------------------------------------------------------------------------
# 1. Bollinger Bands
# ---------------------------------------------------------------------------
class BollingerBands:
    """
    Bollinger Bands: SMA(20) ± 2σ.
    Signals:
      - Price near lower band → bullish (oversold)
      - Price near upper band → bearish (overbought)
      - Band squeeze (narrow width) → breakout imminent
      - Band expansion → trend confirmation
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0, weight: float = 1.0):
        self.period = period
        self.std_dev = std_dev
        self.weight = weight

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        closes = [c.close for c in candles]
        if len(closes) < self.period:
            return Signal("bollinger_bands", timeframe,
                          SignalDirection.NEUTRAL, 0.0, self.weight, abstained=True)

        # v3.24.22 — suffix-only. Consumes sma[-1]/std[-1] plus the
        # widths slice over the last `period` entries, so `period` is
        # exactly the depth needed. Derived from config, not the module
        # default, so a bot configured with a longer period still gets
        # every value it reads.
        sma = _sma_tail(closes, self.period, tail=self.period)
        std = _stdev_tail(closes, self.period, tail=self.period)

        mid = sma[-1]
        upper = mid + self.std_dev * std[-1]
        lower = mid - self.std_dev * std[-1]
        price = closes[-1]
        band_width = (upper - lower) / (mid + 1e-9)

        # Squeeze detection (width below 20-period average width)
        #
        # v3.24.22 — the comprehension bound was `range(len(sma))`, i.e.
        # the ENTIRE history, while only the last `period` entries are
        # ever consumed by the `widths[-self.period:]` slice below.
        #
        # This is also the hard blocker for narrowing _sma/_stdev: it is
        # the only site that indexes sma/std across the whole range, so
        # until it is bounded, a suffix-only _sma would be read at
        # indices it never filled (TypeError: float * NoneType).
        #
        # The arithmetic expression is deliberately left VERBATIM rather
        # than simplified to `2 * std_dev * std[i]`. Every consumer of
        # these values is a threshold comparison, and changing the order
        # of float operations changes the last bits.
        #
        # v3.24.83 — DIVIDED BY sma[i]. IT WAS A UNITS MISMATCH.
        #
        # `band_width` above is `(upper - lower) / mid` — DIMENSIONLESS.
        # These historical widths were `(sma + k*std) - (sma - k*std)`;
        # the `sma[i]` terms cancel exactly, leaving `2*k*std[i]` in
        # PRICE UNITS, never normalised. Line below then compared the
        # ratio against the absolute width.
        #
        # So `squeeze` was a test on PRICE, not on volatility. Setting
        # sigma ~ sigma_avg, `band_width < 0.75 * avg_width` reduces to
        # `mid > 1.33` — an asset cheaper than about $1.33 can never
        # register a squeeze, and a dearer one almost always can.
        # MEASURED on the operator's own fleet: CHIP at $0.08 squeezed
        # 0 times in 400 candles, SPK at $0.03 zero in 402, XRP at
        # $1.44 226 of 379 (59.6%).
        #
        # It reaches trading: `confidence *= 0.7` below fires only when
        # squeezed, so the damping was applied by asset price.
        #
        # The correct form already existed twenty feet away —
        # `native_chart.py:1231-1236` averages bandwidth and compares
        # bandwidth. The chart drew squeezes the engine could not see.
        #
        # Numerator kept verbatim per the note above; only the
        # normalisation that `band_width` already had is added.
        widths = [((sma[i] + self.std_dev * std[i])
                   - (sma[i] - self.std_dev * std[i])) / (sma[i] + 1e-9)
                  for i in range(max(0, len(sma) - self.period), len(sma))]
        # `width_count` is a COUNT of windows, not a bandwidth. Naming
        # it keeps the length test out of the bandwidth comparison on
        # the next line.
        width_count = len(widths)
        avg_width = (sum(widths[-self.period:]) / self.period
                     if width_count >= self.period else band_width)
        squeeze = band_width < avg_width * 0.75

        # Position within bands (0 = lower, 1 = upper)
        #
        # %B is a position WITHIN a channel. A window whose price never
        # moved has no channel, so there is no position to report and no
        # vote to cast. Resolving 0/0 through the epsilon gave
        # bb_pos = 0.0, which the first branch below reads as hard
        # against the LOWER band and answers with confidence 1.0000 --
        # the largest vote any indicator in this engine casts, at weight
        # 1.0.
        #
        # The test is on the CLOSES, not on `upper - lower`. The band
        # width is 4*sigma out of `_stdev_tail`, and on a halted window
        # that rounds to a few ULPs rather than to zero on 154 of 599
        # measured price pegs, so a test of the width misses exactly the
        # markets this guard exists for. `upper - lower <= 0.0` is kept
        # underneath as a subordinate floor: it can only ever make this
        # abstain more often, never less.
        if (_window_has_no_range(closes[-self.period:])
                or upper - lower <= 0.0):
            return Signal("bollinger_bands", timeframe,
                          SignalDirection.NEUTRAL, 0.0, self.weight, abstained=True)

        bb_pos = (price - lower) / (upper - lower + 1e-9)

        direction = SignalDirection.NEUTRAL
        confidence = 0.0

        if bb_pos < 0.15:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, (0.15 - bb_pos) / 0.15 * 0.8 + 0.3))
        elif bb_pos > 0.85:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, (bb_pos - 0.85) / 0.15 * 0.8 + 0.3))
        elif bb_pos < 0.35:
            direction = SignalDirection.BULLISH
            confidence = 0.2
        elif bb_pos > 0.65:
            direction = SignalDirection.BEARISH
            confidence = 0.2

        if squeeze:
            confidence *= 0.7  # Less confident during squeeze

        return Signal(
            indicator="bollinger_bands",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "upper": round(upper, 6), "middle": round(mid, 6),
                "lower": round(lower, 6), "bb_position": round(bb_pos, 4),
                "band_width": round(band_width, 6), "squeeze": squeeze,
            },
        )
