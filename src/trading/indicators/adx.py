"""``ADXIndicator``, Wilder's ADX and DMI.

``compute`` returns a ``Signal`` named ``adx`` carrying ``di_plus``,
``di_minus`` and the smoothed ADX reading. ``_wilder_smooth`` is the
smoothing that the directional movement, true range and DX series all
pass through.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)
from .helpers import (
    _true_range,
)


class ADXIndicator:
    """Wilder's ADX and DMI over ``period`` candles.

    ``compute`` reports ``ranging``, ``developing``, ``strong_trend``,
    ``parabolic``, ``di_bull_cross`` and ``di_bear_cross`` beside the
    ADX reading.
    """

    def __init__(self, period: int = 14, weight: float = 1.0):
        self.period = period
        self.weight = weight

    @staticmethod
    def _wilder_smooth(values: list, period: int) -> list:
        """Wilder's smoothing of ``values`` over ``period``.

        The leading ``period - 1`` entries are ``0.0`` padding, and a
        ``values`` shorter than ``period`` returns all zeros.
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

        # Directional movement reads a previous bar; tr_list starts at
        # candle 1.
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

        if not s_tr or s_tr[-1] < 1e-9:
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

        if len(s_tr) >= 2 and s_tr[-2] > 1e-9:
            p_dip = 100.0 * s_dmp[-2] / s_tr[-2]
            p_dim = 100.0 * s_dmm[-2] / s_tr[-2]
        else:
            p_dip = di_plus
            p_dim = di_minus

        dx_series = []
        for j in range(len(s_tr)):
            if s_tr[j] <= 0.0:
                dx_series.append(0.0)
                continue
            dip_j = 100.0 * s_dmp[j] / s_tr[j]
            dim_j = 100.0 * s_dmm[j] / s_tr[j]
            ds = dip_j + dim_j
            dx_series.append(100.0 * abs(dip_j - dim_j) / ds if ds > 1e-9 else 0.0)

        # _dx_valid drops the zero pad _wilder_smooth writes before its
        # first real value.
        _dx_valid = dx_series[self.period - 1 :]
        s_dx = self._wilder_smooth(_dx_valid, self.period)
        adx = s_dx[-1] if s_dx else 0.0
        p_adx = s_dx[-2] if len(s_dx) >= 2 else adx

        ranging = adx < 20
        developing = 20 <= adx < 35
        strong_trend = adx >= 35
        parabolic = adx >= 50
        adx_rising = adx > p_adx
        bull_dominant = di_plus > di_minus
        bear_dominant = di_minus > di_plus
        di_bull_cross = p_dip <= p_dim and di_plus > di_minus
        di_bear_cross = p_dip >= p_dim and di_plus < di_minus
        new_trend = adx_rising and p_adx < 20 and adx >= 20

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
