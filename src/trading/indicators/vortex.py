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

#: One entry per candle. ``None`` where the published formula has no
#: value yet -- see ``VortexIndicator.window_sums``.
_Line = list[float | None]

#: ``(sum VM+, sum VM-, sum TR)`` over one closed window, or ``None``.
_Window = tuple[float, float, float] | None

# ---------------------------------------------------------------------------
# 2. Vortex Indicator
# ---------------------------------------------------------------------------
# Vortex extremes — empirically observed typical ceiling/floor thresholds
# VI+ and VI- are RATIOS -- a directional-movement sum over a
# true-range sum -- so 1.0 is parity and the extremes are stated as a
# percentage OF that parity, then divided back into ratio space. Both
# sides of the ceiling/floor tests below then carry the same unit by
# construction rather than by convention.
VX_CEILING_PCT = 130.0  # VI at 130% of parity = momentum exhausted


VX_FLOOR_PCT = 70.0  # VI at  70% of parity = flat / no conviction


VX_CEILING = VX_CEILING_PCT / PERCENT_PER_RATIO_UNIT


VX_FLOOR = VX_FLOOR_PCT / PERCENT_PER_RATIO_UNIT


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

    def window_sums(self, candles: list[Candle]) -> list[_Window]:
        """Per candle, the three window totals VI is built from.

        THE PUBLISHED DEFINITION. Botes and Siepman (2010):

            VM+ = |High_t - Low_(t-1)|
            VM- = |Low_t  - High_(t-1)|
            VI+ = sum(VM+, period) / sum(TR, period)
            VI- = sum(VM-, period) / sum(TR, period)

        This returns the three totals, candle-aligned, and NOTHING
        divides them here. ``lines`` and ``compute`` each spell the
        quotient at the point they use it, which is what keeps VI's
        dimensionless units visible to the reader beside the
        VX_CEILING / VX_FLOOR tests. The sums themselves -- the part
        that can drift -- exist once.

        WHERE THE SERIES STARTS. Both VM terms reach back one bar, so
        neither exists at bar 0 and the first window closes at index
        ``period``. Entries before it are ``None`` -- reading one is a
        TypeError at the point of misuse rather than a plausible wrong
        number, the contract ``helpers._ema`` already states.

        A WINDOW WITH NO TRUE RANGE IS ``None`` TOO. VI is a ratio
        over true range, so a halted window has no denominator at all.
        ``compute`` records the trade inversion that came from letting
        the epsilon be the whole of it.

        ONE DEFINITION, TWO CALLERS. ``compute`` reads the last two
        entries; the candle chart draws every one. The chart carried
        its own copy of these sums until issue #128 R2.
        """
        n_c = len(candles)
        out: list[_Window] = [None] * n_c
        if n_c < self.period + 1:
            return out

        vm_plus = []
        vm_minus = []
        for i in range(1, n_c):
            vm_plus.append(abs(candles[i].high - candles[i - 1].low))
            vm_minus.append(abs(candles[i].low - candles[i - 1].high))

        # True Range from the module's ONE definition, sliced to the
        # window the Vortex formula sums over. VM+ and VM- both reach
        # back one bar and neither exists at bar 0. VI+ and VI- divide
        # a VM sum by a TR sum over THE SAME BARS, so the TR series
        # must start where the VM series does. `[1:]` is that
        # alignment -- not a discarded value.
        tr = _true_range(candles)[1:]

        n = self.period
        for i in range(n, n_c):
            # ``vm_plus[j]`` and ``tr[j]`` both describe candle j + 1,
            # so the n-bar window ending AT candle i is ``[i - n : i]``
            # in list space. At i = n_c - 1 that is the same slice, in
            # the same order, that ``compute`` used to spell ``[-n:]``.
            lo = i - n
            sum_tr_window = sum(tr[lo:i])
            # True range is a max of differences between equal prices
            # on a halt, so the sum cancels to EXACTLY 0.0 and
            # ``<= 0.0`` is sound.
            if sum_tr_window <= 0.0:
                continue
            out[i] = (sum(vm_plus[lo:i]), sum(vm_minus[lo:i]), sum_tr_window)
        return out

    def lines(self, candles: list[Candle]) -> tuple[_Line, _Line]:
        """VI+ and VI-, ONE ENTRY PER CANDLE, for a chart to draw.

        A directional-movement sum OVER a true-range sum. Both carry
        price units, so each quotient is DIMENSIONLESS and 1.0 is
        parity. A window with no reading stays ``None``.
        """
        windows = self.window_sums(candles)
        plus_series: _Line = [None] * len(windows)
        minus_series: _Line = [None] * len(windows)
        for i, window in enumerate(windows):
            if window is None:
                continue
            sum_vp, sum_vm, sum_tr_window = window
            sum_tr = sum_tr_window + 1e-9
            plus_series[i] = sum_vp / sum_tr
            minus_series[i] = sum_vm / sum_tr
        return plus_series, minus_series

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        if len(candles) < self.period + 1:
            return Signal(
                "vortex",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        windows = self.window_sums(candles)
        current = windows[-1]

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
        # halt, so the sum cancels to EXACTLY 0.0 and ``window_sums``
        # leaves the entry ``None``.
        if current is None:
            return Signal(
                "vortex",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        sum_vp, sum_vm, sum_tr_window = current
        sum_tr = sum_tr_window + 1e-9

        vi_plus = sum_vp / sum_tr
        vi_minus = sum_vm / sum_tr

        # Previous period values for crossover + acceleration detection.
        # A previous window with no true range has no VI either -- it is
        # ``None`` in the series -- and this module's own fallback for
        # that is the current reading.
        prev_vp = vi_plus
        prev_vm = vi_minus
        previous = windows[-2] if len(windows) >= 2 else None
        if previous is not None:
            prev_sum_vp, prev_sum_vm, prev_tr_window = previous
            prev_vp = prev_sum_vp / (prev_tr_window + 1e-9)
            prev_vm = prev_sum_vm / (prev_tr_window + 1e-9)

        separation = vi_plus - vi_minus
        prev_sep = prev_vp - prev_vm
        sep_acceleration = separation - prev_sep  # how fast lines are diverging

        # ── Ceiling / floor detection ─────────────────────────────────────
        vip_at_ceiling = vi_plus >= VX_CEILING  # bullish exhausted
        vim_at_ceiling = vi_minus >= VX_CEILING  # bearish exhausted
        vip_at_floor = vi_plus <= VX_FLOOR  # no bullish conviction
        vim_at_floor = vi_minus <= VX_FLOOR  # no bearish conviction
        both_converging = abs(separation) < 0.08  # lines near each other

        # ── Crossover ─────────────────────────────────────────────────────
        bullish_cross = prev_sep <= 0 and separation > 0
        bearish_cross = prev_sep >= 0 and separation < 0

        # ── Post-crossover divergence acceleration ────────────────────────
        # After a bullish cross, VI+ rising AND VI- falling simultaneously
        # is the strongest possible confirmation (your image arrows)
        bull_accel = (
            separation > 0
            and sep_acceleration > 0.05
            and vi_plus > prev_vp
            and vi_minus < prev_vm
        )
        bear_accel = (
            separation < 0
            and sep_acceleration < -0.05
            and vi_minus > prev_vm
            and vi_plus < prev_vp
        )

        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        crossover = bullish_cross or bearish_cross

        if bullish_cross:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, abs(separation) * 3 + 0.5))
        elif bearish_cross:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(separation) * 3 + 0.5))
        elif bull_accel:
            # Post-crossover divergence expanding — highest-conviction bull signal
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, abs(separation) * 2 + 0.55))
        elif bear_accel:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(separation) * 2 + 0.55))
        elif separation > 0.05:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(0.6, abs(separation) * 2))
        elif separation < -0.05:
            direction = SignalDirection.BEARISH
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
            direction = SignalDirection.BULLISH  # bear exhaustion = reversal coming

        return Signal(
            indicator="vortex",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "vi_plus": round(vi_plus, 4),
                "vi_minus": round(vi_minus, 4),
                "separation": round(separation, 4),
                "sep_acceleration": round(sep_acceleration, 4),
                "crossover": crossover,
                "bull_accel": bull_accel,
                "bear_accel": bear_accel,
                "vip_at_ceiling": vip_at_ceiling,
                "vim_at_ceiling": vim_at_ceiling,
                "vip_at_floor": vip_at_floor,
                "vim_at_floor": vim_at_floor,
                "both_converging": both_converging,
            },
        )
