"""``ADXIndicator``, Wilder's ADX and DMI.

``lines`` answers +DI, -DI and ADX for every candle; ``compute`` reads the
last two entries of those series into a ``Signal`` named ``adx``.
``_wilder_smooth`` is the smoothing that the directional movement, true
range and DX series all pass through.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)
from .helpers import (
    _true_range,
)

#: One entry per candle, ``None`` until the smoothing window closes.
_Line = list[float | None]


class ADXIndicator:
    """Wilder's ADX and DMI over ``period`` candles.

    ``lines`` answers the three series a chart draws; ``compute`` reports
    ``ranging``, ``developing``, ``strong_trend``, ``parabolic``,
    ``di_bull_cross`` and ``di_bear_cross`` beside the ADX reading.
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

    def lines(self, candles: list) -> tuple[_Line, _Line, _Line]:
        """+DI, -DI and ADX, one entry per candle, for a chart to draw.

        Wilder (1978): DM+ and DM- from each bar's high and low against the
        previous bar's, smoothed with true range over ``period``; DI is each
        smoothed DM as a percent of the smoothed true range; DX is the
        percent difference of the two DI; ADX smooths DX over ``period``.
        DI is ``None`` before ``period`` bars and on a halted window whose
        smoothed true range is 0.0; ADX is ``None`` before ``2 * period``
        bars.
        """
        n = len(candles)
        di_plus_series: _Line = [None] * n
        di_minus_series: _Line = [None] * n
        adx_series: _Line = [None] * n
        if n < self.period + 1:
            return di_plus_series, di_minus_series, adx_series

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

        # s_tr[j] is 0.0 across the leading pad and on a halted window,
        # where DI is 0/0 and the entry stays None.
        dx_series = []
        for j in range(len(s_tr)):
            if s_tr[j] <= 0.0:
                dx_series.append(0.0)
                continue
            dip_j = 100.0 * s_dmp[j] / s_tr[j]
            dim_j = 100.0 * s_dmm[j] / s_tr[j]
            di_plus_series[j + 1] = dip_j
            di_minus_series[j + 1] = dim_j
            ds = dip_j + dim_j
            dx_series.append(100.0 * abs(dip_j - dim_j) / ds if ds > 0.0 else 0.0)

        # _dx_valid drops the zero pad _wilder_smooth writes before its
        # first real value.
        _dx_valid = dx_series[self.period - 1 :]
        s_dx = self._wilder_smooth(_dx_valid, self.period)
        # s_dx carries the same zero pad, so the ADX readings start at the
        # same offset: entry k of adx_values belongs to candle 2p - 1 + k.
        adx_values = s_dx[self.period - 1 :]
        if n >= self.period * 2:
            for k, value in enumerate(adx_values):
                adx_series[2 * self.period - 1 + k] = value
        return di_plus_series, di_minus_series, adx_series

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        n = len(candles)
        # period bars seed the smoothed TR, and period DX values seed the ADX.
        if n < self.period * 2:
            return Signal(
                "adx",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        di_plus_series, di_minus_series, adx_series = self.lines(candles)

        # The last DI is None only on a halted window, where DI is 0/0 and
        # adx abstains.
        if di_plus_series[-1] is None or di_minus_series[-1] is None:
            return Signal(
                "adx",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        di_plus = di_plus_series[-1]
        di_minus = di_minus_series[-1]

        if di_plus_series[-2] is not None and di_minus_series[-2] is not None:
            p_dip = di_plus_series[-2]
            p_dim = di_minus_series[-2]
        else:
            p_dip = di_plus
            p_dim = di_minus

        adx = adx_series[-1] if adx_series[-1] is not None else 0.0
        p_adx = adx_series[-2] if adx_series[-2] is not None else adx

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
                "adx": adx,
                "di_plus": di_plus,
                "di_minus": di_minus,
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
