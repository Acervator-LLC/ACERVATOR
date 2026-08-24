"""Stochastic RSI -- a stochastic taken over RSI values.

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
    _sma,
)


# ---------------------------------------------------------------------------
# 4. Stochastic RSI
# ---------------------------------------------------------------------------
class StochasticRSI:
    """
    Stochastic RSI: Stochastic oscillator applied to RSI values.
    K line = smoothed StochRSI, D line = SMA of K.
    """

    def __init__(self, rsi_period: int = 14, stoch_period: int = 14,
                 k_smooth: int = 3, d_smooth: int = 3, weight: float = 1.0):
        self.rsi_period = rsi_period
        self.stoch_period = stoch_period
        self.k_smooth = k_smooth
        self.d_smooth = d_smooth
        self.weight = weight

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        closes = [c.close for c in candles]
        needed = self.rsi_period + self.stoch_period + self.d_smooth + 5
        if len(closes) < needed:
            return Signal("stochastic_rsi", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)

        # Compute RSI series
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        # WILDER'S GAIN AND LOSS, ONE SPELLING.
        #
        # StockCharts, stating Wilder's rule: "Losses are expressed as
        # positive values, not negative values." Both series are
        # NON-NEGATIVE MAGNITUDES: the up move on an up bar, the size
        # of the down move on a down bar, zero otherwise.
        #
        # The two copies of this line in the package disagreed on the
        # zero bar. ``max(0, d)`` returns the int ``0``; ``max(d, 0)``
        # on ``d = 0.0`` returns ``0.0`` but ``max(-d, 0)`` returns
        # ``-0.0`` -- Python's ``max`` keeps the FIRST argument on a
        # tie, and ``-0.0 == 0`` is True. A negative zero is not "a
        # positive value", and neither copy said in code what Wilder's
        # rule says.
        #
        # ``max(0.0, x)`` puts the FLOAT ZERO FIRST, so the tie on a
        # flat bar resolves to ``+0.0`` for both series, in both files.
        # Verified across d = 0.0, -0.0, +5.0 and -5.0: every flat-bar
        # result carries sign bit +1.
        gains = [max(0.0, d) for d in deltas]
        losses = [max(0.0, -d) for d in deltas]

        rsi_values = []
        avg_gain = sum(gains[:self.rsi_period]) / self.rsi_period
        avg_loss = sum(losses[:self.rsi_period]) / self.rsi_period

        rs_indeterminate = False
        for i in range(self.rsi_period, len(deltas)):
            avg_gain = (avg_gain * (self.rsi_period - 1) + gains[i]) / self.rsi_period
            avg_loss = (avg_loss * (self.rsi_period - 1) + losses[i]) / self.rsi_period
            # Wilder defines RS with no losses but SOME gains as an
            # infinite ratio, i.e. RSI 100. That case is defined and is
            # left exactly as it was. With neither gains nor losses the
            # ratio is 0/0 and there is no reading. The flag records the
            # state at the LAST bar, which is the reading the vote uses.
            #
            # Gains and losses are max(0, close[i] - close[i-1]) over
            # adjacent bars, exactly 0.0 on a halt, and Wilder smoothing
            # of exact zeros stays exactly 0.0, so `<= 0.0` is sound.
            rs_indeterminate = avg_gain <= 0.0 and avg_loss <= 0.0
            rs = avg_gain / (avg_loss + 1e-9)
            rsi_values.append(100 - 100 / (1 + rs))

        if rs_indeterminate or len(rsi_values) < self.stoch_period:
            return Signal("stochastic_rsi", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)

        # Stochastic of RSI
        #
        # v3.24.25 — bounded to the tail the consumers actually reach.
        # Only k_line[-1], k_line[-2], d_line[-1] and d_line[-2] are read
        # (see the K/D crossover below). Walking the dependency chain
        # backwards:
        #
        #   d_line[-2] = mean(k_line[-4:-1])   -> needs k_line[-4:]
        #   k_line[-4] = mean(stoch[-6:-3])    -> needs stoch[-6:]
        #
        # so exactly k_smooth + d_smooth trailing stoch values suffice,
        # and every k_line entry those reads touch is past _sma's
        # shorter-divisor warm-up branch, so the values are unchanged.
        #
        # Taking FEWER than k_smooth + d_smooth would silently alter
        # k_line[-2] / d_line[-2], which drive the crossover tests that
        # emit confidence-0.8 SCRUM/FOLD signals. The max() keeps the
        # original full-range behaviour on short inputs.
        _stoch_need = self.k_smooth + self.d_smooth
        _stoch_from = max(self.stoch_period - 1,
                          len(rsi_values) - _stoch_need)
        stoch_rsi = []
        stoch_indeterminate = False
        for i in range(_stoch_from, len(rsi_values)):
            window = rsi_values[i - self.stoch_period + 1:i + 1]
            low = min(window)
            high = max(window)
            # A stochastic is a position within a range. An RSI window
            # with no range has no position in it, and every value this
            # loop computes feeds the K and D lines the crossover votes
            # on -- the loop is already bounded to exactly that tail.
            #
            # `high` and `low` are the max and min of the window itself,
            # so this IS the source-quantity test, applied to the series
            # the stochastic is actually positioned in.
            if high - low <= 0.0:
                stoch_indeterminate = True
            stoch_rsi.append((rsi_values[i] - low) / (high - low + 1e-9) * 100)

        if stoch_indeterminate:
            return Signal("stochastic_rsi", timeframe,
                          SignalDirection.NEUTRAL, 0.0, self.weight)

        # K line (SMA smoothing)
        k_line = _sma(stoch_rsi, self.k_smooth)
        # D line (SMA of K)
        d_line = _sma(k_line, self.d_smooth)

        k = k_line[-1]
        d = d_line[-1]
        prev_k = k_line[-2] if len(k_line) > 1 else k
        prev_d = d_line[-2] if len(d_line) > 1 else d

        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        crossover = ""

        # K/D crossover
        if prev_k <= prev_d and k > d:
            crossover = "bullish"
            if k < 30:
                direction = SignalDirection.BULLISH
                confidence = 0.8
            elif k < 50:
                direction = SignalDirection.BULLISH
                confidence = 0.5
            else:
                direction = SignalDirection.BULLISH
                confidence = 0.25
        elif prev_k >= prev_d and k < d:
            crossover = "bearish"
            if k > 70:
                direction = SignalDirection.BEARISH
                confidence = 0.8
            elif k > 50:
                direction = SignalDirection.BEARISH
                confidence = 0.5
            else:
                direction = SignalDirection.BEARISH
                confidence = 0.25

        # Extreme zones without crossover
        if not crossover:
            if k < 15:
                direction = SignalDirection.BULLISH
                confidence = 0.5
            elif k > 85:
                direction = SignalDirection.BEARISH
                confidence = 0.5
            elif k < 30:
                direction = SignalDirection.BULLISH
                confidence = 0.2
            elif k > 70:
                direction = SignalDirection.BEARISH
                confidence = 0.2

        return Signal(
            indicator="stochastic_rsi",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={"k": round(k, 2), "d": round(d, 2), "crossover": crossover},
        )
