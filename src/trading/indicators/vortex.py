"""Vortex Indicator -- VI+ / VI- (Botes and Siepman, 2010).

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations

from .types import (
    PERCENT_PER_RATIO_UNIT,
    SignalDirection,
    Signal,
    Candle,
)
from .helpers import (
    _true_range,
)


# ---------------------------------------------------------------------------
# 2. Vortex Indicator
# ---------------------------------------------------------------------------
# Vortex extremes — empirically observed typical ceiling/floor thresholds
# VI+ and VI- are RATIOS -- a directional-movement sum over a
# true-range sum -- so 1.0 is parity and the extremes are stated as a
# percentage OF that parity, then divided back into ratio space. Both
# sides of the ceiling/floor tests below then carry the same unit by
# construction rather than by convention.
VX_CEILING_PCT = 130.0   # VI at 130% of parity = momentum exhausted


VX_FLOOR_PCT   = 70.0    # VI at  70% of parity = flat / no conviction


VX_CEILING = VX_CEILING_PCT / PERCENT_PER_RATIO_UNIT


VX_FLOOR   = VX_FLOOR_PCT / PERCENT_PER_RATIO_UNIT


class VortexIndicator:
    """
    Vortex Indicator: VI+ and VI- trend direction.

    Enhanced signals (v3.7.0):
      - Crossover: VI+ crosses VI- or vice versa (primary signal)
      - Separation expansion after crossover: confirmation of direction
      - VI+ pegged at ceiling (>= VX_CEILING): bullish momentum exhausted
      - VI- pegged at ceiling (>= VX_CEILING): bearish momentum exhausted
      - VI+ pegged at floor (<= VX_FLOOR):    bullish conviction flat
      - Both lines converging near 1.0:        consolidation / no trend
    """

    def __init__(self, period: int = 14, weight: float = 1.0):
        self.period = period
        self.weight = weight

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        if len(candles) < self.period + 1:
            return Signal("vortex", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)

        vm_plus = []
        vm_minus = []
        for i in range(1, len(candles)):
            vm_plus.append(abs(candles[i].high - candles[i - 1].low))
            vm_minus.append(abs(candles[i].low - candles[i - 1].high))

        # True Range from the module's ONE definition, sliced to the
        # window the Vortex formula sums over. Botes and Siepman
        # (2010) define VM+ = |High_t - Low_{t-1}| and
        # VM- = |Low_t - High_{t-1}|, so both reach back one bar and
        # neither exists at bar 0. VI+ and VI- divide a VM sum by a
        # TR sum over THE SAME BARS, so the TR series must start
        # where the VM series does. `[1:]` is that alignment -- not
        # a discarded value.
        tr = _true_range(candles)[1:]

        n = self.period
        if len(vm_plus) < n:
            return Signal("vortex", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)

        sum_vp = sum(vm_plus[-n:])
        sum_vm = sum(vm_minus[-n:])
        sum_tr_window = sum(tr[-n:])

        # VI+ and VI- are directional movement OVER true range. With no
        # true range across the window there is no denominator at all,
        # and the epsilon became the whole of it.
        #
        # This is not simply the halted-market case. `tr` is aligned to
        # candle i while `vm_plus[i]` reaches back to candle i-1, so at
        # the moment a halt first fills the true-range window the VM sums
        # still carry the last live bar. Measured at halt length 14 --
        # exactly the period, and every halt of 14 bars or more passes
        # through it -- VI+ reached 2.2e8 and the separation -5.5e7. That
        # separation is overwhelmingly BEARISH and the vote came out
        # BULLISH, because VI- above VX_CEILING trips the bear-exhaustion
        # branch below, which overwrites the direction. The epsilon did
        # not inflate a number here; it inverted a trade.
        #
        # True range is a max of differences between equal prices on a
        # halt, so the sum cancels to EXACTLY 0.0 and `<= 0.0` is sound.
        if sum_tr_window <= 0.0:
            return Signal("vortex", timeframe,
                          SignalDirection.NEUTRAL, 0.0, self.weight)

        sum_tr = sum_tr_window + 1e-9

        vi_plus  = sum_vp / sum_tr
        vi_minus = sum_vm / sum_tr

        # Previous period values for crossover + acceleration detection.
        # A previous window with no true range has no VI either, and this
        # module's own fallback for that is the current reading.
        prev_vp = vi_plus
        prev_vm = vi_minus
        if len(vm_plus) >= n + 1:
            prev_tr_window = sum(tr[-n-1:-1])
            if prev_tr_window > 0.0:
                prev_vp = sum(vm_plus[-n-1:-1]) / (prev_tr_window + 1e-9)
                prev_vm = sum(vm_minus[-n-1:-1]) / (prev_tr_window + 1e-9)

        separation      = vi_plus - vi_minus
        prev_sep        = prev_vp - prev_vm
        sep_acceleration = separation - prev_sep   # how fast lines are diverging

        # ── Ceiling / floor detection ─────────────────────────────────────
        vip_at_ceiling  = vi_plus  >= VX_CEILING   # bullish exhausted
        vim_at_ceiling  = vi_minus >= VX_CEILING   # bearish exhausted
        vip_at_floor    = vi_plus  <= VX_FLOOR     # no bullish conviction
        vim_at_floor    = vi_minus <= VX_FLOOR     # no bearish conviction
        both_converging = abs(separation) < 0.08   # lines near each other

        # ── Crossover ─────────────────────────────────────────────────────
        bullish_cross = prev_sep <= 0 and separation > 0
        bearish_cross = prev_sep >= 0 and separation < 0

        # ── Post-crossover divergence acceleration ────────────────────────
        # After a bullish cross, VI+ rising AND VI- falling simultaneously
        # is the strongest possible confirmation (your image arrows)
        bull_accel = (separation > 0 and sep_acceleration > 0.05
                      and vi_plus > prev_vp and vi_minus < prev_vm)
        bear_accel = (separation < 0 and sep_acceleration < -0.05
                      and vi_minus > prev_vm and vi_plus < prev_vp)

        direction  = SignalDirection.NEUTRAL
        confidence = 0.0
        crossover  = bullish_cross or bearish_cross

        if bullish_cross:
            direction  = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, abs(separation) * 3 + 0.5))
        elif bearish_cross:
            direction  = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(separation) * 3 + 0.5))
        elif bull_accel:
            # Post-crossover divergence expanding — highest-conviction bull signal
            direction  = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, abs(separation) * 2 + 0.55))
        elif bear_accel:
            direction  = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(separation) * 2 + 0.55))
        elif separation > 0.05:
            direction  = SignalDirection.BULLISH
            confidence = max(0.0, min(0.6, abs(separation) * 2))
        elif separation < -0.05:
            direction  = SignalDirection.BEARISH
            confidence = max(0.0, min(0.6, abs(separation) * 2))

        # ── Ceiling/floor confidence modifiers ───────────────────────────
        # VI+ pegged at ceiling = uptrend is exhausted — lower scrum confidence
        # VI- pegged at ceiling = downtrend is exhausted — boost fold confidence
        # Both converging near 1.0 = no trend, consolidation
        if vip_at_ceiling:
            # Bullish momentum maxed out — reduce scrum confidence signal
            confidence = max(0.0, min(confidence, 0.45))
        if vim_at_ceiling:
            # Bearish momentum maxed out — this is a strong fold signal
            confidence = min(1.0, max(confidence, 0.60))
            direction  = SignalDirection.BULLISH  # bear exhaustion = reversal coming

        return Signal(
            indicator="vortex",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "vi_plus":          round(vi_plus,  4),
                "vi_minus":         round(vi_minus, 4),
                "separation":       round(separation, 4),
                "sep_acceleration": round(sep_acceleration, 4),
                "crossover":        crossover,
                "bull_accel":       bull_accel,
                "bear_accel":       bear_accel,
                "vip_at_ceiling":   vip_at_ceiling,
                "vim_at_ceiling":   vim_at_ceiling,
                "vip_at_floor":     vip_at_floor,
                "vim_at_floor":     vim_at_floor,
                "both_converging":  both_converging,
            },
        )
