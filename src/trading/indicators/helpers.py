"""Scalar maths helpers shared by more than one indicator.

Every function here is stateless and returns a new list. No
indicator's OUTPUT is computed here. These are the moving
average, the deviation and the true range that several
published formulae are each built from.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations

import math
from typing import Optional

from .types import (
    Candle,
)


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------
def _ema(values: list[float], period: int) -> list[float | None]:
    """Exponential moving average, candle-aligned, NO VALUE BEFORE THE SEED.

    THE PUBLISHED DEFINITION. StockCharts, reproducing the standard
    three-step construction: "An exponential moving average (EMA) has to
    start somewhere, so a simple moving average is used as the previous
    period's EMA in the first calculation." The three steps are then
    "calculate the simple moving average for the initial EMA value",
    "calculate the weighting multiplier", and "calculate the exponential
    moving average FOR EACH DAY BETWEEN THE INITIAL EMA VALUE AND
    TODAY".

    So the series has exactly one starting point. Over ``values`` of
    length n with parameter ``period``:

        result[period - 1] = mean(values[0 : period])     the SMA seed
        result[i]          = (values[i] - result[i-1]) * k + result[i-1]
        k                  = 2 / (period + 1)

    and BELOW ``period - 1`` THERE IS NO EMA. Not zero, not the seed:
    none. Those entries are ``None``, so reading one is a TypeError at
    the point of misuse rather than a plausible wrong number. That is
    the same contract ``_sma_tail`` states below, for the same reason.

    WHAT THIS REPAIRED (issue #99). The body used to end with

        for i in range(period - 1):
            result[i] = result[period - 1]

    which BACK-FILLED every leading index with the seed. The arithmetic
    above it was right; those entries were invented. They were not a
    display convenience either -- MACD feeds one EMA output into the
    next, so ``_ema(macd_line, 9)`` seeded its signal line on nine
    manufactured constants and then recursed through sixteen more. For a
    26/9 MACD that is 25 fabricated inputs. It is a CALCULATED-FROM-THE-
    DATA-SOURCE failure, not a formula failure, and no formula audit can
    see it.

    A SHORT TAPE RETURNS NOTHING. When fewer than ``period`` values
    exist there is no seed, so every entry is ``None`` and the series
    says so. The body used to ``return values[:]`` -- handing the caller
    the RAW INPUT relabelled as its own moving average.

    LENGTH IS PRESERVED. ``len(result) == len(values)`` always, so a
    caller may still index by candle. Returning a short list instead
    would let ``zip(ema_fast, ema_slow)`` line up index 0 of a 12-EMA
    with index 0 of a 26-EMA -- two different candles, silently.
    """
    n = len(values)
    result: list[float | None] = [None] * n
    if period < 1 or n < period:
        return result
    prev = sum(values[:period]) / period      # the SMA seed
    result[period - 1] = prev
    multiplier = 2.0 / (period + 1)
    for i in range(period, n):
        # `prev` holds exactly what ``result[i - 1]`` holds. Carrying it
        # in a float local keeps the recursion off the Optional list, so
        # the arithmetic is the published one with nothing to unwrap.
        prev = (values[i] - prev) * multiplier + prev
        result[i] = prev
    return result


_TAIL_DEFAULT = 35


"""How many trailing values the suffix-only variants compute.

Set by the hungriest consumer: ``SlingshotIndicator`` reads
``sma_v[i]`` / ``std_v[i]`` for ``i in range(n - (squeeze_lookback + 5), n)``
= the last 35. ``BollingerBands`` needs 20, and ``detect_bb_proximity`` /
``detect_landing_strip_v2`` read only ``[-1]``.
"""


def _sma(values: list[float], period: int) -> list[float]:
    """Simple moving average series."""
    return _sma_tail(values, period, tail=None)


def _stdev(values: list[float], period: int) -> list[float]:
    """Rolling standard deviation."""
    return _stdev_tail(values, period, tail=None)


def _sma_tail(values: list[float], period: int,
              tail: Optional[int] = _TAIL_DEFAULT) -> list[float]:
    """Simple moving average, computing only the last ``tail`` entries.

    v3.24.22. The full-history form is O(n*period): every one of n
    outputs re-sums a window of `period` values. Consumers read at most
    the last 35 entries, so the first n-35 were computed and discarded
    on every tick, for every bot, for every candle.

    BIT-IDENTITY
    ============
    The per-element body is UNCHANGED — each output still comes from
    ``sum(values[i - period + 1 : i + 1]) / period`` over exactly the same
    slice in exactly the same order. Only the set of ``i`` narrows, so
    each computed element is bit-identical to the full-history version.

    This is deliberately NOT a rolling sum. A rolling accumulator was
    measured at 2.02e-12 max relative difference — close, but not
    identical — and every consumer here is a threshold comparison
    (``bb_pos < 0.15``, ``band_width < avg_width * 0.75``), with
    ``upper/lower = mid +/- 2*std``. A 2e-12 drift in std propagates
    straight into a live SCRUM/FOLD decision on a knife-edge candle.

    Entries before the tail are ``None``: reading one is a TypeError at
    the point of misuse rather than a plausible wrong number.
    """
    n = len(values)
    start = 0 if tail is None else max(0, n - int(tail))
    result: list = [None] * start
    for i in range(start, n):
        if i < period - 1:
            result.append(sum(values[:i + 1]) / (i + 1))
        else:
            result.append(sum(values[i - period + 1:i + 1]) / period)
    return result


def _stdev_tail(values: list[float], period: int,
                tail: Optional[int] = _TAIL_DEFAULT) -> list[float]:
    """Rolling standard deviation, last ``tail`` entries only.

    Same contract and same bit-identity argument as ``_sma_tail``: the
    per-window body is untouched, only the range of ``i`` narrows.
    """
    n = len(values)
    start = 0 if tail is None else max(0, n - int(tail))
    result: list = [None] * start
    for i in range(start, n):
        window = values[max(0, i - period + 1):i + 1]
        if len(window) < 2:
            result.append(0.0)
        else:
            mean = sum(window) / len(window)
            var = sum((x - mean) ** 2 for x in window) / len(window)
            result.append(math.sqrt(var))
    return result


def _window_has_no_range(values: list[float]) -> bool:
    """True when every value in ``values`` is the same number.

    THE SOURCE QUANTITY, NOT A DERIVED ONE. A sample has zero dispersion
    exactly when it has no range, and ``max == min`` settles that on the
    numbers as the venue sent them. No arithmetic runs, so there is
    nothing to round, and the answer is exact at every price scale.

    ``_stdev_tail`` cannot answer the same question, and testing its
    output for zero is the defect this exists to remove. It computes
    ``mean = sum(w)/len(w)`` and then ``sum((x-mean)**2)/len(w)``, and
    summing N copies of one price GENERICALLY ROUNDS. MEASURED over 599
    fully halted 60-bar tapes built from venue decimal strings, 154 left
    sigma at a few ULPs instead of 0.0 -- 40 of 100 at 118.xx, 40 of 100
    at 61234.xx, 38 of 100 at 0.031200xx, and the very first at 0.11,
    which is the operator's own CHIP scale. On those tapes a test of
    ``upper - lower <= 0.0`` does NOT fire, the 1e-9 epsilon then
    dominates a ~1e-17 band, %B rounds to 0.0, and the indicator answers
    BULLISH at confidence 1.0000 on a market that has not moved.

    An empty window has no range either, and says so rather than
    raising, because every caller here has already length-checked.
    """
    if not values:
        return True
    return max(values) == min(values)


def _true_range(candles: list[Candle]) -> list[float]:
    """True Range series, ONE bar per candle, candle-aligned.

    THE PUBLISHED DEFINITION. Wilder, *New Concepts in Technical
    Trading Systems* (1978). True Range is the greatest of:

        1. current High less current Low
        2. |current High less PREVIOUS Close|
        3. |current Low  less PREVIOUS Close|

    THE FIRST BAR. Methods 2 and 3 need a previous close, and the
    first bar of a tape has none. The published answer is method 1
    alone. StockCharts, reproducing Wilder's own ATR worksheet:
    "the first TR value is simply the High minus the Low", and the
    worked spreadsheet carries a True Range on its very first row.
    So ``_true_range(candles)[0]`` is ``high - low`` and the series
    is the same length as ``candles``.

    ONE DEFINITION, FIVE WINDOWS. Each indicator then sums this
    series over the bars ITS OWN published formula covers, and the
    slice is written at the call site:

      ATRIndicator, SupertrendIndicator -- the whole series. Wilder's
        ATR averages every TR, the first one included.
      ADXIndicator -- ``[1:]``. TR is summed against +DM and -DM,
        and directional movement needs a previous bar, so Wilder's
        DMI worksheet starts every one of its three columns on the
        second row.
      VortexIndicator -- ``[1:]``, for the same reason: VM+ and VM-
        (Botes and Siepman, 2010) each reach back one bar.
      SlingshotIndicator -- computes its own, deliberately (see that
        class's docstring and tests/test_slingshot_canonical.py). Its
        first bar is ``high - low``, so it agrees with this one.

    v3.26.x: this docstring said only "True Range series" and four
    other copies of the per-bar formula had drifted apart on the
    first bar. The arithmetic below is unchanged.
    """
    tr = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        c = candles[i]
        prev_close = candles[i - 1].close
        tr.append(max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close)))
    return tr
