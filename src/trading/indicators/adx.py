"""Wilder's ADX / DMI (1978).

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)
from .helpers import (
    _true_range,
)


# ---------------------------------------------------------------------------
# 8. ADX / DMI — Average Directional Index + Directional Movement Index
# ---------------------------------------------------------------------------
class ADXIndicator:
    """
    Wilder's ADX/DMI (1978) — the only indicator that measures TREND STRENGTH
    rather than direction or exhaustion. Answers: "how committed is this move?"

    Components:
      DM+  : Directional Movement Plus  = max(high - prev_high, 0) if > |low - prev_low|
      DM-  : Directional Movement Minus = max(prev_low - low, 0)   if > |high - prev_high|
      TR   : True Range = max(H-L, |H-prevC|, |L-prevC|)
      DI+  : 100 × Smoothed(DM+) / Smoothed(TR)    — bullish force
      DI-  : 100 × Smoothed(DM-) / Smoothed(TR)    — bearish force
      DX   : 100 × |DI+ - DI-| / (DI+ + DI-)       — directional strength
      ADX  : Wilder-smoothed DX over period          — trend strength

    Signal thresholds:
      ADX < 20           = ranging / weak trend → accumulation ideal conditions
      ADX 20-35          = developing trend
      ADX > 35           = strong trend → lean into direction aggressively
      ADX > 50           = parabolic (unsustainable)
      DI+ > DI-          = bullish pressure dominant
      DI+ crossing DI-   = trend turning bullish (Golden Cross)
      DI- crossing DI+   = trend turning bearish
      ADX rising from <20 = new trend forming = slingshot sibling signal

    For accumulation:
      Ranging (ADX<20)   → full harvest efficiency, fold every oscillation
      Strong bull (ADX>35 + DI+>DI-) → scrums more aggressive, folds lean
      Strong bear (ADX>35 + DI->DI+) → folds more aggressive, scrums lean
      Trend reversal (DI cross) → confirmation for fold or scrum entry
    """

    def __init__(self, period: int = 14, weight: float = 1.0):
        self.period = period
        self.weight = weight

    @staticmethod
    def _wilder_smooth(values: list, period: int) -> list:
        """Wilder's smoothing — not EMA. First value = sum/period.

        v3.24.83 — THIS NOW MATCHES ITS OWN DOCSTRING.

        It read "First value = sum/period" and then did
        ``first = sum(values[:period])`` with no division, and recursed
        as ``prev - prev/period + v`` — the SUM form. Every value it
        returned was `period` times Wilder's average.

        That is invisible in +DI/-DI, which divide two of its outputs
        by each other so the scale cancels. It is NOT invisible in DX,
        which is already a 0-100 percentage: the returned ADX was ~14x
        its own definitional maximum. Measured before the fix, on 1174
        records: 99.8% above 100, max 761.5.

        The averaged form is the textbook one, so the textbook
        thresholds (25 trending / 30 strong / 50 extreme) now apply as
        written. `ScrummingTrendRegimeGate.adx_threshold` was empirically
        recalibrated to 500.0 against the OLD scale and is reset to 30.0
        in the same change — its docstring required exactly that.

        ONE SPELLING, EVERYWHERE. The recursion is written as Wilder
        publishes it and as StockCharts reproduces it:

            "Subsequent ADX14 = ((Prior ADX14 x 13) + Current DX)/14"
            "Average Gain = [(previous Average Gain) x 13 + current
             Gain] / 14"            (the same recursion, Wilder's RSI)
            "Current ATR = [(Prior ATR x 13) + Current TR] / 14"

        i.e. ``(a * (period - 1) + v) / period``. This body used
        ``a + (v - a) / period`` instead. The two are the SAME identity
        in exact arithmetic and are NOT the same in IEEE 754: measured
        over 200 bars the two forms landed on 0x1.1069e657ae042p+0 and
        0x1.1069e657ae045p+0, 6.66e-16 apart. ``ATRIndicator``,
        ``SupertrendIndicator``, ``RSIIndicator`` and ``StochasticRSI``
        all already used the published spelling; this was the one
        outlier, and its output feeds a threshold comparison
        (``ADXTrendSuppressionGate``, 30.0).
        """
        if len(values) < period:
            return [0.0] * len(values)
        result = [0.0] * (period - 1)
        result.append(sum(values[:period]) / period)
        for v in values[period:]:
            result.append((result[-1] * (period - 1) + v) / period)
        return result

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:

        # sadp: R28  # indicator compute: fail-loudly(R28)
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

        # True Range comes from the module's ONE definition. The DMI
        # sums it against +DM and -DM, and directional movement reaches
        # back one bar, so Wilder's DMI worksheet starts all three
        # columns on the second row: `[1:]` is that alignment, written
        # where the formula requires it. `_true_range` computes the
        # identical per-bar expression this loop used to inline.
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

        # Previous DI for crossover
        if len(s_tr) >= 2 and s_tr[-2] > 1e-9:
            p_dip = 100.0 * s_dmp[-2] / s_tr[-2]
            p_dim = 100.0 * s_dmm[-2] / s_tr[-2]
        else:
            p_dip = di_plus
            p_dim = di_minus

        # ADX = Wilder smooth of DX history
        #
        # ONE DIVISION, NOT TWO. Wilder defines the directional
        # indicators exactly once -- StockCharts: "Divide the 14-day
        # smoothed Plus Directional Movement (+DM) by the 14-day
        # smoothed True Range ... Multiply by 100" -- and there is no
        # epsilon in that definition.
        #
        # This method used to divide two different ways in two places.
        # `di_plus` / `di_minus` above use `s_tr[-1]` bare, guarded by
        # the `s_tr[-1] < 1e-9` return above. The series below added
        # `+ 1e-9` to the SAME denominator, so the current bar's DX and
        # the last entry of the DX series were two different numbers
        # from one formula. The epsilon is removed; the `s_tr[j] <= 0.0`
        # test on the next lines is the zero guard, and it is exact for
        # the reason its own comment gives.
        #
        # A standalone `dx` local stood here as well, computed from the
        # no-epsilon pair and never read by anything. It was the second
        # implementation this repair exists to remove. The current DX is
        # `dx_series[-1]`, from the one loop below.
        dx_series = []
        for j in range(len(s_tr)):
            # No true range in this window makes DI+ and DI- both 0/0.
            # The window has no DX -- which is exactly what the `ds` test
            # four lines below has always said for the same condition.
            # `s_tr[j]` is a Wilder sum of true ranges, and a true range
            # is a max of differences between equal prices on a halt, so
            # it cancels to EXACTLY 0.0 and this test is sound on it.
            if s_tr[j] <= 0.0:
                dx_series.append(0.0)
                continue
            dip_j = 100.0 * s_dmp[j] / s_tr[j]
            dim_j = 100.0 * s_dmm[j] / s_tr[j]
            ds = dip_j + dim_j
            dx_series.append(100.0 * abs(dip_j - dim_j) / ds if ds > 1e-9 else 0.0)

        # The leading `period - 1` entries of `dx_series` come from the
        # zero pad `_wilder_smooth` writes, not from real DI readings.
        # Averaging them in would drag the first ADX toward zero, so the
        # series starts at the first genuine DX.
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
