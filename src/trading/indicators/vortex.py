"""Vortex Indicator -- VI+ / VI- (Botes and Siepman, 2010).

``VortexIndicator.window_sums`` totals VM+, VM- and true range over one
period; ``lines`` and ``compute`` each divide those totals.
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

#: One entry per candle, ``None`` where ``VortexIndicator.window_sums``
#: has no closed window.
_Line = list[float | None]

#: ``(sum VM+, sum VM-, sum TR)`` over one closed window, or ``None``.
_Window = tuple[float, float, float] | None

# ``VX_CEILING`` and ``VX_FLOOR`` bound a dimensionless ratio, and each is
# a percent of its 1.0 parity.
VX_CEILING_PCT = 130.0


VX_FLOOR_PCT = 70.0


VX_CEILING = VX_CEILING_PCT / PERCENT_PER_RATIO_UNIT


VX_FLOOR = VX_FLOOR_PCT / PERCENT_PER_RATIO_UNIT


class VortexIndicator:
    """VI+ against VI-, voting on trend direction.

    ``compute`` votes on a VI crossover or on expanding separation, and
    ``VX_CEILING`` caps confidence; ``lines`` returns both series for a
    chart to draw.
    """

    def __init__(self, period: int = 14, weight: float = 1.0):
        self.period = period
        self.weight = weight

    def window_sums(self, candles: list[Candle]) -> list[_Window]:
        """Per candle, the three window totals VI is built from.

        Botes and Siepman (2010):

            VM+ = |High_t - Low_(t-1)|
            VM- = |Low_t  - High_(t-1)|
            VI+ = sum(VM+, period) / sum(TR, period)
            VI- = sum(VM-, period) / sum(TR, period)

        Entries below index ``period`` are ``None``, and so is any window
        whose true-range total is 0.0.
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

        # ``[1:]`` aligns ``tr`` with ``vm_plus``, which starts at candle 1.
        tr = _true_range(candles)[1:]

        n = self.period
        for i in range(n, n_c):
            # ``vm_plus[j]`` and ``tr[j]`` describe candle j + 1, so window
            # ``i`` spans ``[i - n : i]``.
            lo = i - n
            sum_tr_window = sum(tr[lo:i])
            # On a halt true range is a max of differences between equal
            # prices, so ``sum_tr_window`` cancels to exactly 0.0.
            if sum_tr_window <= 0.0:
                continue
            out[i] = (sum(vm_plus[lo:i]), sum(vm_minus[lo:i]), sum_tr_window)
        return out

    def lines(self, candles: list[Candle]) -> tuple[_Line, _Line]:
        """VI+ and VI-, one entry per candle, for a chart to draw.

        Each entry divides a ``window_sums`` VM total by that window's
        true-range total, so both are dimensionless and 1.0 is parity.
        """
        windows = self.window_sums(candles)
        plus_series: _Line = [None] * len(windows)
        minus_series: _Line = [None] * len(windows)
        for i, window in enumerate(windows):
            if window is None:
                continue
            sum_vp, sum_vm, sum_tr_window = window
            plus_series[i] = sum_vp / sum_tr_window
            minus_series[i] = sum_vm / sum_tr_window
        return plus_series, minus_series

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        """One Vortex vote over ``candles`` at ``timeframe``.

        ``direction`` follows VI+ against VI-, and ``compute`` abstains when
        ``window_sums`` has no closed window.
        """
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

        # ``window_sums`` leaves a window with no true range ``None``, and
        # a VI ratio has no denominator there.
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

        vi_plus = sum_vp / sum_tr_window
        vi_minus = sum_vm / sum_tr_window

        # ``prev_vp`` and ``prev_vm`` stand in with the current reading
        # when the previous window is ``None``.
        prev_vp = vi_plus
        prev_vm = vi_minus
        previous = windows[-2] if len(windows) >= 2 else None
        if previous is not None:
            prev_sum_vp, prev_sum_vm, prev_tr_window = previous
            prev_vp = prev_sum_vp / prev_tr_window
            prev_vm = prev_sum_vm / prev_tr_window

        separation = vi_plus - vi_minus
        prev_sep = prev_vp - prev_vm
        sep_acceleration = separation - prev_sep

        vip_at_ceiling = vi_plus >= VX_CEILING
        vim_at_ceiling = vi_minus >= VX_CEILING
        vip_at_floor = vi_plus <= VX_FLOOR
        vim_at_floor = vi_minus <= VX_FLOOR
        both_converging = abs(separation) < 0.08

        bullish_cross = prev_sep <= 0 and separation > 0
        bearish_cross = prev_sep >= 0 and separation < 0

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

        if vip_at_ceiling:
            confidence = max(0.0, min(confidence, 0.45))

        return Signal(
            indicator="vortex",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "vi_plus": vi_plus,
                "vi_minus": vi_minus,
                "separation": separation,
                "sep_acceleration": sep_acceleration,
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
