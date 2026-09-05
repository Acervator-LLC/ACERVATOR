"""The candle chart draws the ENGINE's indicators, not its own.

Issue #128 R2. ``src/gui/native_chart.py`` carried a second full
indicator suite -- Bollinger(20,2), EMA12/26, Vortex(14), MACD(12,26,9),
StochRSI(14,14) and Ichimoku(9,26,52) -- inside a ``QWidget``. It was
148 lines, no test referenced it, and its comment "Do NOT let chart
computations diverge" had nothing enforcing it.

WHAT THE COPY GOT RIGHT, MEASURED OVER AN 80-BAR TAPE
=====================================================
Bollinger  61 of 61 drawn bars bit-identical to the engine.
Ichimoku   400 of 400 terms (80 candles x 5 lines) bit-identical.
Vortex     66 drawn, 0 identical, max absolute difference 1.456e-10.
StochRSI   52 drawn, 9 identical, max absolute difference 1.664e-08.

The last two differ only in where the zero-denominator guard sits: the
copy wrote ``sum(...) or 1e-9``, ``StochasticRSI`` writes
``(high - low + 1e-9)``, and ``VortexIndicator.window_sums`` returns
``None`` for a zero true-range total and divides by the total itself.
Both now come from the engine's spelling.

WHAT THE COPY GOT WRONG
=======================
MACD. Its EMAs seeded at ``closes[0]`` and back-filled from index 0, so
it drew a MACD line and a signal line on EVERY bar -- 80 of 80,
including index 0, where it drew ``(0.0, 0.0, 0.0)`` because both EMAs
still held the first close. The published series has NO value before
index ``slow - 1`` = 25, and no signal before ``slow + signal - 2`` =
33; that is ``helpers._ema``'s SMA seed, and issue #99 repaired the
engine for exactly this reason.

Over the 47 bars where both carried a value, NONE agreed:

    idx 33   chart hist 0.07164468   published 0.06256638
    idx 34   chart hist 0.02779588   published 0.01639981
    idx 79   chart hist -0.11573129  published -0.11666825

peak histogram divergence 237.4%. The published value is what reaches
the screen now.

EVERY ASSERTION HERE IS A VALUE, READ THROUGH A SECOND PATH. The
series methods are checked against the SAME indicator's ``compute``,
which builds its reading independently of any chart, and the widget
tests drive the real ``QWidget`` and read the pixels it paints. A
structural "the copy is gone" check would pass on a chart that no
longer drew anything at all.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.trading.ta_engine import (  # noqa: E402
    BollingerBands,
    Candle,
    IchimokuCloud,
    MACD,
    StochasticRSI,
    VortexIndicator,
)
from src.trading.indicators.helpers import _sma  # noqa: E402

#: Published warm-ups at the defaults, from the formulae themselves.
MACD_LINE_STARTS = 25  # slow - 1
MACD_SIGNAL_STARTS = 33  # slow + signal - 2


def _tape(n: int = 80) -> list[Candle]:
    """Ramp, flat window, gap, spike and zero-volume bars.

    A smooth ramp hides division-by-zero, flat-window and gap
    behaviour, which is where indicator code breaks.
    """
    closes: list[float] = []
    price = 100.0
    for i in range(40):
        price = price * (1.0 + 0.004 * math.sin(i * 0.7) + 0.001)
        closes.append(round(price, 2))
    closes += [closes[-1]] * 8
    closes.append(closes[-1] * 1.35)
    closes.append(closes[-1] * 0.72)
    for i in range(n - len(closes)):
        closes.append(round(closes[-1] * (1 + 0.006 * math.cos(i * 0.4)), 2))
    out = []
    for i, close in enumerate(closes[:n]):
        opn = closes[i - 1] if i else close
        out.append(
            Candle(
                timestamp=1700000000 + i * 3600,
                open=opn,
                high=max(opn, close) * 1.002,
                low=min(opn, close) * 0.998,
                close=close,
                volume=0.0 if i % 17 == 0 else 1000.0 + i,
            )
        )
    return out


# 1. Each series agrees with the SAME indicator's vote, which is a
#    second code path through the same published formula.
def test_bollinger_series_last_bar_matches_the_vote():
    tape = _tape()
    upper, middle, lower = BollingerBands(20, 2.0).bands(tape)[-1]
    details = BollingerBands(20, 2.0).compute(tape, "1h").details
    assert round(upper, 6) == details["upper"]
    assert round(middle, 6) == details["middle"]
    assert round(lower, 6) == details["lower"]


def test_macd_series_last_bar_matches_the_vote():
    tape = _tape()
    line, signal, hist = MACD(12, 26, 9).lines(tape)
    details = MACD(12, 26, 9).compute(tape, "1h").details
    assert round(line[-1], 6) == details["macd_line"]
    assert round(signal[-1], 6) == details["signal_line"]
    assert round(hist[-1], 6) == details["histogram"]


def test_vortex_series_last_bar_matches_the_vote():
    tape = _tape()
    vi_plus, vi_minus = VortexIndicator(14).lines(tape)
    details = VortexIndicator(14).compute(tape, "1h").details
    assert round(vi_plus[-1], 4) == details["vi_plus"]
    assert round(vi_minus[-1], 4) == details["vi_minus"]


def test_stochrsi_series_last_bars_match_the_vote():
    """The vote's K line is a 3-SMA of the ratio this series carries.

    The chart draws the raw 0-to-1 StochRSI; the vote smooths it and
    presents 0-to-100. Both come out of ``stoch_ratios``, so the K the
    vote reads must be recoverable from the drawn series.
    """
    tape = _tape()
    indicator = StochasticRSI()
    ratios = [v for v in indicator.lines(tape) if v is not None]
    k_line = _sma([r * 100 for r in ratios], 3)
    details = indicator.compute(tape, "1h").details
    assert round(k_line[-1], 2) == details["k"]

    tape_closes = [c.close for c in tape]
    rsi_values, _ = indicator.rsi_values(tape_closes)
    full_from, full, _ = indicator.stoch_ratios(rsi_values, tape_closes)
    tail_need = indicator.k_smooth + indicator.d_smooth
    tail_from, tail, _ = indicator.stoch_ratios(rsi_values, tape_closes, tail=tail_need)
    assert len(tail) == tail_need
    assert full[tail_from - full_from :] == tail


def test_ichimoku_series_last_bar_matches_the_vote():
    tape = _tape()
    tenkan, kijun, _span_a, _span_b, chikou = IchimokuCloud(9, 26, 52).lines(tape)[-1]
    details = IchimokuCloud(9, 26, 52).compute(tape, "1h").details
    assert round(tenkan, 4) == details["tenkan"]
    assert round(kijun, 4) == details["kijun"]
    assert chikou == tape[-1].close


# 2. The MACD repair, as numbers.
def test_macd_has_no_value_before_its_published_seed():
    """A failure here means an EMA is seeding on invented bars again.

    That is the whole of issue #99 and the whole of the chart copy's
    defect: back-filling the warm-up makes the signal line an average
    of numbers the candles never produced.
    """
    tape = _tape()
    line, signal, hist = MACD(12, 26, 9).lines(tape)
    assert all(v is None for v in line[:MACD_LINE_STARTS])
    assert line[MACD_LINE_STARTS] is not None
    assert all(v is None for v in signal[:MACD_SIGNAL_STARTS])
    assert signal[MACD_SIGNAL_STARTS] is not None
    assert all(v is None for v in hist[:MACD_SIGNAL_STARTS])
    assert hist[MACD_SIGNAL_STARTS] is not None


def test_the_old_chart_macd_value_no_longer_reaches_the_screen():
    """The recorded wrong numbers, and the published ones beside them.

    A failure means the chart went back to a MACD the engine did not
    compute.
    """
    tape = _tape()
    _line, _signal, hist = MACD(12, 26, 9).lines(tape)
    old_wrong = {33: 0.07164468, 34: 0.02779588, 79: -0.11573129}
    published = {33: 0.06256638, 34: 0.01639981, 79: -0.11666825}
    for index, wrong in old_wrong.items():
        assert round(hist[index], 8) == published[index]
        assert round(hist[index], 8) != wrong


# 3. The chart still RENDERS. Deleting a duplicate also stops it
#    disagreeing, so "the copy is gone" proves nothing on its own.
pytest.importorskip("PySide6")


def _chart_with_overlays():
    from src.gui import native_chart
    from tests.qt_pixel import ensure_app

    ensure_app()
    chart = native_chart.CandlestickChart()
    chart.resize(900, 700)
    tape = _tape()
    chart.set_candles(
        [
            native_chart.Candle(
                time=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
            for c in tape
        ]
    )
    chart._show_bb = True
    chart._show_macd = True
    chart._show_vortex = True
    chart._show_stochrsi = True
    chart._show_ichimoku = True
    return chart, tape


def test_the_widget_holds_the_engine_series_after_set_candles():
    chart, tape = _chart_with_overlays()
    assert len(chart._bb_data) == len(tape)
    assert len(chart._macd_data) == len(tape)
    assert len(chart._vortex_data) == len(tape)
    assert len(chart._stochrsi_data) == len(tape)
    assert len(chart._ichimoku_data) == len(tape)
    # The value on screen is the engine's, to the last bit.
    line, signal, hist = MACD(12, 26, 9).lines(tape)
    assert chart._macd_data[-1] == (line[-1], signal[-1], hist[-1])
    assert chart._macd_data[MACD_SIGNAL_STARTS - 1] is None
    upper, middle, lower = BollingerBands(20, 2.0).bands(tape)[-1]
    assert chart._bb_data[-1] == (upper, middle, lower)


def _render(show_macd: bool, empty_series: bool = False):
    from tests.qt_pixel import render_widget

    chart, _tape = _chart_with_overlays()
    chart._show_macd = show_macd
    if empty_series:
        chart._macd_data = []
    return render_widget(chart, (900, 700))


def _differing_pixels(left, right) -> int:
    return sum(
        1
        for y in range(left.height())
        for x in range(left.width())
        if left.pixelColor(x, y) != right.pixelColor(x, y)
    )


def test_the_engine_series_reaches_the_pixels():
    """THE VACUOUS-PASS CONTROL.

    Deleting a duplicate also stops it disagreeing, so every value
    assertion above would still pass on a chart that had stopped
    drawing. This reads the rendered image, which is the surface the
    operator sees.

    Three renders, and the third is the one that matters:

      * MACD on vs off -- 135,280 pixels differ, rows 60 to 651.
      * MACD on vs on  -- 0 pixels differ, so the number above is not
        render noise and the assertion has a defined meaning.
      * MACD on, but ``_macd_data`` EMPTIED -- 135,280 pixels differ,
        the same count as switching the pane off. The pane is driven
        by the SERIES, not by the toggle, so a
        ``_compute_indicators`` that produced nothing would be caught
        here.
    """
    on = _render(True)
    assert _differing_pixels(on, _render(True)) == 0, "render is not deterministic"
    off_pixels = _differing_pixels(on, _render(False))
    assert off_pixels > 10000, f"the MACD pane paints nothing: {off_pixels}"
    empty_pixels = _differing_pixels(on, _render(True, empty_series=True))
    assert empty_pixels == off_pixels, (
        "an emptied MACD series still rendered the pane, so this control "
        f"cannot see a chart that computes nothing: {empty_pixels} vs "
        f"{off_pixels}"
    )
