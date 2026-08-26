"""MACD -- Gerald Appel's moving-average convergence/divergence.

Moved out of ``ta_engine.py`` for issue #73. The body below was a
verbatim line slice of that file: no arithmetic was retyped.

Issue #99 then repaired WHERE THE SIGNAL LINE STARTS. The five lines
that build the three series were duplicated in two methods; they are
now one method, ``_lines``, which carries the published definition and
its citation.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
    Candle,
)
from .helpers import (
    _ema,
)

#: One entry per candle. ``None`` where the published formula has no
#: value yet -- see ``MACD._lines``.
_Line = list[float | None]

#: ``_ema`` returns a leading run of None and a value at every index
#: after it, so the MACD line does too. A hole in the middle would mean
#: that contract broke, and the signal EMA below would silently seed on
#: the wrong bars.
_INTERIOR_GAP = (
    "MACD line has an interior gap; _ema must return a "
    "leading run of None and nothing else"
)


# ---------------------------------------------------------------------------
# 3. MACD
# ---------------------------------------------------------------------------
class MACD:
    """
    MACD: EMA(12) - EMA(26), Signal EMA(9), Histogram.
    Enhanced with divergence detection.
    """

    def __init__(
        self, fast: int = 12, slow: int = 26, signal: int = 9, weight: float = 1.0
    ):
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self.weight = weight

    def _lines(self, closes: list[float]) -> tuple[_Line, _Line, _Line]:
        """MACD Line, Signal Line and Histogram, one per candle.

        THE PUBLISHED DEFINITION. StockCharts, reproducing Appel:

            MACD Line:      (12-day EMA - 26-day EMA)
            Signal Line:    9-day EMA of MACD Line
            MACD Histogram: MACD Line - Signal Line

        WHERE EACH SERIES STARTS, and this is the whole of issue #99.
        An EMA has no value before its seed, so:

          * ``ema_slow`` starts at index ``slow - 1``; ``ema_fast``
            starts earlier. The MACD Line is their difference, so IT
            starts at ``slow - 1`` -- index 25 at the defaults.
          * The Signal Line is a ``signal``-period EMA OF THAT SERIES.
            It is not an EMA of the candles. So it seeds on the first
            ``signal`` REAL MACD-line values and its first entry sits at
            ``slow + signal - 2`` -- index 33 at the defaults.

        WHAT THIS REPAIRED. ``_ema`` used to back-fill its leading
        indices with the seed, so ``macd_line[0 .. 24]`` carried 25
        manufactured numbers. The signal line then averaged nine of them
        for its seed and recursed through the other sixteen. The
        arithmetic was right and the INPUT was invented; for those bars
        the signal line was not computed from the candles at all.

        Entries with no value are ``None``, candle-aligned. Reading one
        is a TypeError at the point of misuse rather than a plausible
        wrong number -- the contract ``helpers._sma_tail`` already
        states.

        ONE DEFINITION, TWO CALLERS. ``compute`` and
        ``compute_histogram_series`` both come here. They used to carry
        a copy of these five lines each.
        """
        ema_fast = _ema(closes, self.fast)
        ema_slow = _ema(closes, self.slow)
        macd_line: _Line = [
            None if (f is None or s is None) else f - s
            for f, s in zip(ema_fast, ema_slow)
        ]

        # ``_ema`` returns a leading run of ``None`` and then a value at
        # every remaining index, so ``macd_line`` does too and its real
        # part is a contiguous suffix. The signal EMA runs over THAT
        # suffix and its output is put back at the suffix's own indices,
        # which is what keeps every series candle-aligned.
        first = len(macd_line)
        for i, v in enumerate(macd_line):
            if v is not None:
                first = i
                break
        real: list[float] = []
        for v in macd_line[first:]:
            if v is None:
                raise ValueError(_INTERIOR_GAP)
            real.append(v)

        signal_line: _Line = [None] * first
        signal_line.extend(_ema(real, self.signal_period))
        histogram: _Line = [
            None if (m is None or g is None) else m - g
            for m, g in zip(macd_line, signal_line)
        ]
        return macd_line, signal_line, histogram

    def lines(self, candles: list[Candle]) -> tuple[_Line, _Line, _Line]:
        """``_lines`` over a candle list. The chart's series.

        The same three series ``compute`` votes on and
        ``compute_histogram_series`` trims, taken from the same
        method, so a chart cannot draw a MACD the engine did not
        compute.

        THE CANDLE CHART'S OLD COPY SEEDED EVERY EMA AT ``closes[0]``
        and back-filled from index 0, so its MACD line existed 25 bars
        before the published one and its signal line 33. Measured over
        an 80-bar tape: 47 indices carried a value in both, and NONE
        of the 47 matched; peak histogram divergence 237%. Issue #128
        R2 removed that copy.
        """
        return self._lines([c.close for c in candles])

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        closes = [c.close for c in candles]
        # THE PUBLISHED WARM-UP, EXACTLY. The signal line's first value
        # sits at index ``slow + signal - 2``, and the block below reads
        # ``[-2]``, so it needs ``n - 2 >= slow + signal - 2``, i.e.
        # ``n >= slow + signal``. That is the condition already written
        # here. It was right before this repair and it stays.
        if len(closes) < self.slow + self.signal_period:
            return Signal(
                "macd",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        macd_line, signal_line, histogram = self._lines(closes)

        curr_hist = histogram[-1]
        prev_hist = histogram[-2]
        curr_macd = macd_line[-1]
        curr_signal = signal_line[-1]
        prev_macd = macd_line[-2]
        prev_signal = signal_line[-2]
        if (
            curr_hist is None
            or prev_hist is None
            or curr_macd is None
            or curr_signal is None
            or prev_macd is None
            or prev_signal is None
        ):
            # Unreachable at any ``fast < slow``: see the guard note
            # above. An explicit abstention, not an assert, so a
            # non-default parameterisation states that it has no
            # reading instead of returning one it did not compute.
            return Signal(
                "macd",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        crossover = False
        divergence = ""

        # Crossover detection
        if prev_macd <= prev_signal and curr_macd > curr_signal:
            direction = SignalDirection.BULLISH
            crossover = True
            confidence = max(
                0.0,
                min(1.0, abs(curr_hist) / (abs(closes[-1]) * 0.001 + 1e-9) * 0.3 + 0.5),
            )
        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            direction = SignalDirection.BEARISH
            crossover = True
            confidence = max(
                0.0,
                min(1.0, abs(curr_hist) / (abs(closes[-1]) * 0.001 + 1e-9) * 0.3 + 0.5),
            )
        elif curr_hist > 0 and curr_hist > prev_hist:
            direction = SignalDirection.BULLISH
            confidence = max(
                0.0, min(0.6, abs(curr_hist) / (abs(closes[-1]) * 0.002 + 1e-9))
            )
        elif curr_hist < 0 and curr_hist < prev_hist:
            direction = SignalDirection.BEARISH
            confidence = max(
                0.0, min(0.6, abs(curr_hist) / (abs(closes[-1]) * 0.002 + 1e-9))
            )
        elif curr_hist > 0:
            direction = SignalDirection.BULLISH
            confidence = 0.15
        elif curr_hist < 0:
            direction = SignalDirection.BEARISH
            confidence = 0.15

        # Divergence detection (price makes new low but MACD doesn't)
        #
        # THE WINDOWS COUNT REAL MACD VALUES, NOT CANDLES. The test
        # compares a 20-bar MACD extreme against the 20 bars before it,
        # so it needs 20 (and 40) values the MACD line actually has.
        # The candle count is not that number: the line starts at index
        # ``slow - 1``, so a 35-candle tape carries 10 MACD values, not
        # 35. Counting candles here read back-filled entries as if they
        # were readings.
        real_macd = [v for v in macd_line if v is not None]
        n_macd = len(real_macd)
        if len(closes) >= 20 and n_macd >= 20:
            price_low = min(closes[-20:])
            price_prev_low = min(closes[-40:-20]) if len(closes) >= 40 else price_low
            macd_low = min(real_macd[-20:])
            macd_prev_low = min(real_macd[-40:-20]) if n_macd >= 40 else macd_low

            if (
                closes[-1] <= price_low
                and price_low < price_prev_low
                and macd_low > macd_prev_low
            ):
                divergence = "bullish"
                direction = SignalDirection.BULLISH
                confidence = min(1.0, max(confidence, 0.7))
            elif closes[-1] >= max(closes[-20:]) and max(closes[-20:]) > max(
                closes[-40:-20] if len(closes) >= 40 else closes[-20:]
            ):
                macd_high = max(real_macd[-20:])
                macd_prev_high = max(real_macd[-40:-20]) if n_macd >= 40 else macd_high
                if macd_high < macd_prev_high:
                    divergence = "bearish"
                    direction = SignalDirection.BEARISH
                    confidence = min(1.0, max(confidence, 0.7))

        return Signal(
            indicator="macd",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "macd_line": round(curr_macd, 6),
                "signal_line": round(curr_signal, 6),
                "histogram": round(curr_hist, 6),
                "crossover": crossover,
                "divergence": divergence,
            },
        )

    def compute_histogram_series(self, candles: list, n: int = 12) -> list[float]:

        # sadp: R28  # indicator compute: fail-loudly(R28)
        """
        Return the last `n` MACD histogram values as a list (oldest→newest).

        Single O(N) computation — more efficient than calling compute() N times.
        Used by the simulator snapshot to populate macd_histogram_buf, which
        feeds detect_macd_taper() in the confidence gate.

        Returns [] if fewer candles than the MACD warmup period.

        FEWER THAN ``n`` IS A REAL ANSWER. The histogram starts where
        the signal line does, at index ``slow + signal - 2``, so a tape
        just over the warm-up carries only a handful of bars. This
        returns the ones that exist and never pads the rest. Values that
        do not exist are dropped, not sent as zeros:
        ``detect_macd_taper`` reads ``len(histogram) < lookback`` and
        already answers "none" on a short list, which is the honest
        outcome. Before this repair the list was always ``n`` long
        because ``_ema`` back-filled it.
        """
        closes = [c.close for c in candles]
        min_len = self.slow + self.signal_period
        if len(closes) < min_len:
            return []
        histogram = self._lines(closes)[2]
        return [h for h in histogram if h is not None][-n:]
