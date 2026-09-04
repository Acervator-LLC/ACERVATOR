"""Wilder's ADX / DMI (1978)."""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)
from .helpers import (
    _true_range,
)


class ADXIndicator:
    """Wilder's ADX and DMI over one candle list, published 1978.

    ``compute`` smooths True Range and directional movement with
    ``_wilder_smooth`` and reads

        +DM = high - prev_high, when it exceeds prev_low - low and 0
        -DM = prev_low - low,   when it exceeds high - prev_high and 0
        +DI = 100 * smoothed(+DM) / smoothed(TR)
        -DI = 100 * smoothed(-DM) / smoothed(TR)
        DX  = 100 * |+DI - -DI| / (+DI + -DI)
        ADX = smoothed(DX)

    with ``direction`` set by ``bull_dominant`` against ``bear_dominant``
    and ``confidence`` stepped at ``strong_trend``.
    """

    def __init__(self, period: int = 14, weight: float = 1.0):
        self.period = period
        self.weight = weight

    @staticmethod
    def _wilder_smooth(values: list, period: int) -> list:
        """Wilder's smoothing over ``values``, seeded on the first ``period`` mean.

        StockCharts spells the recursion "Subsequent ADX14 = ((Prior ADX14 x
        13) + Current DX)/14", which this writes as ``(result[-1] * (period -
        1) + v) / period``, and a ``values`` shorter than ``period`` returns
        zeros.
        """
        if len(values) < period:
            return [0.0] * len(values)
        result = [0.0] * (period - 1)
        result.append(sum(values[:period]) / period)
        for v in values[period:]:
            result.append((result[-1] * (period - 1) + v) / period)
        return result

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        n = len(candles)
        if n < self.period * 2 + 2:
            return Signal(
                "adx",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        # Directional movement reaches back one bar, so Wilder's DMI
        # worksheet starts all three columns on the second row.
        tr_list = _true_range(candles)[1:]

        dm_plus = []
        dm_minus = []
        for i in range(1, n):
            h, l = candles[i].high, candles[i].low
            ph, pl = candles[i - 1].high, candles[i - 1].low

            up = h - ph
            down = pl - l
            dm_plus.append(up if up > down and up > 0 else 0.0)
            dm_minus.append(down if down > up and down > 0 else 0.0)

        s_dmp = self._wilder_smooth(dm_plus, self.period)
        s_dmm = self._wilder_smooth(dm_minus, self.period)
        s_tr = self._wilder_smooth(tr_list, self.period)

        # A true range is a max of differences between equal prices on a
        # halt, so `s_tr` cancels to exactly 0.0 and this test is exact at
        # every price scale. A threshold instead of the zero would abstain
        # on a live sub-cent tape whose true ranges are smaller than it.
        if not s_tr or s_tr[-1] <= 0.0:
            return Signal(
                "adx",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        di_plus = 100.0 * s_dmp[-1] / s_tr[-1]
        di_minus = 100.0 * s_dmm[-1] / s_tr[-1]

        # Previous DI for crossover
        if len(s_tr) >= 2 and s_tr[-2] > 0.0:
            p_dip = 100.0 * s_dmp[-2] / s_tr[-2]
            p_dim = 100.0 * s_dmm[-2] / s_tr[-2]
        else:
            p_dip = di_plus
            p_dim = di_minus

        # ONE DIVISION, NOT TWO. StockCharts: "Divide the 14-day smoothed
        # Plus Directional Movement (+DM) by the 14-day smoothed True Range
        # ... Multiply by 100", and there is no epsilon in that definition.
        # The current DX is `dx_series[-1]`, from the one loop below.
        dx_series = []
        for j in range(len(s_tr)):
            # No true range in this window makes DI+ and DI- both 0/0, and
            # the window has no DX.
            if s_tr[j] <= 0.0:
                dx_series.append(0.0)
                continue
            dip_j = 100.0 * s_dmp[j] / s_tr[j]
            dim_j = 100.0 * s_dmm[j] / s_tr[j]
            # `ds` sums two non-negative quotients over one positive
            # denominator, so it is 0.0 exactly when both +DM and -DM are.
            ds = dip_j + dim_j
            dx_series.append(100.0 * abs(dip_j - dim_j) / ds if ds > 0.0 else 0.0)

        # The leading `period - 1` entries of `dx_series` come from the zero
        # pad `_wilder_smooth` writes, not from real DI readings.
        _dx_valid = dx_series[self.period - 1 :]
        s_dx = self._wilder_smooth(_dx_valid, self.period)
        adx = s_dx[-1] if s_dx else 0.0
        p_adx = s_dx[-2] if len(s_dx) >= 2 else adx

        # Signals
        ranging = adx < 20
        developing = 20 <= adx < 35
        strong_trend = adx >= 35
        parabolic = adx >= 50
        adx_rising = adx > p_adx
        bull_dominant = di_plus > di_minus
        bear_dominant = di_minus > di_plus
        di_bull_cross = p_dip <= p_dim and di_plus > di_minus  # DI+ crosses above DI-
        di_bear_cross = p_dip >= p_dim and di_plus < di_minus  # DI- crosses above DI+
        new_trend = adx_rising and p_adx < 20 and adx >= 20  # ADX emerging from ranging

        # Direction and confidence
        if bull_dominant and strong_trend:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, (adx - 35) / 30 + 0.5))
        elif bear_dominant and strong_trend:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, (adx - 35) / 30 + 0.5))
        elif bull_dominant:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(0.5, adx / 70))
        elif bear_dominant:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(0.5, adx / 70))
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="adx",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "adx": round(adx, 2),
                "di_plus": round(di_plus, 2),
                "di_minus": round(di_minus, 2),
                "ranging": ranging,
                "developing": developing,
                "strong_trend": strong_trend,
                "parabolic": parabolic,
                "adx_rising": adx_rising,
                "bull_dominant": bull_dominant,
                "bear_dominant": bear_dominant,
                "di_bull_cross": di_bull_cross,
                "di_bear_cross": di_bear_cross,
                "new_trend": new_trend,
            },
        )
