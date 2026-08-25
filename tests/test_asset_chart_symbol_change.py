"""Issue #46 -- the Asset Charts panel follows the bot's current symbol.

THE DEFECT, AS MEASURED BEFORE THE REPAIR. `TradeChartsTab.update_charts`
wrote `info["symbol"]` in its CREATE branch alone. `fetch_chart_data`
reads that stored field and hands it to the exchange. Driving the real
tab with a recording fetcher, a bot whose pair moved BTC/USD -> ETH/USD
produced:

    asked-1  [('BTC/USD', '1h', <connector>)]
    stored   'BTC/USD'                <- after the ETH/USD status
    asked-2  [('BTC/USD', '1h', <connector>)]
    closes   [100.0, 101.0, 102.0]    <- the BTC tape, on an ETH chart

There is no error, no empty chart and no log line: the panel looks
healthy and is showing a different market from the one it names.

WHAT IS ASSERTED HERE IS THE CONSUMER, NOT THE STORE. A test that reads
`info["symbol"]` back proves only that a dict was written. Every test in
this file reads the two things downstream of that write: THE PAIR THE
FETCHER WAS ASKED FOR, and THE CANDLES THAT ENDED UP ON THE CHART. The
expected values come from the book the stand-in fetcher was handed --
a second witness -- and never from a constant typed twice.

THE OTHER THREE THINGS THAT BELONGED TO THE OLD PAIR. Re-pointing the
fetch alone leaves the chart lying in three more ways, each measured
here:
  - the 30 s throttle keeps the old pair's candles on screen for a
    whole window after the title changed;
  - an empty answer for the new pair calls `set_error` and leaves the
    old pair's candles standing, forever, which is this same defect
    wearing the new pair's name;
  - the old pair's trade markers are replaced only when the new pair
    HAS trades, so on a fresh pair they stayed drawn over it.

THE VACUOUS PASS THIS FILE REFUSES. A panel that fetches NOTHING also
never fetches the wrong pair, and a panel cleared on every 2 s pass is
always empty and never wrong either. Two controls stand against that
shape: `test_a_steady_symbol_leaves_the_panel_alone` proves an unchanged
symbol neither re-fetches nor clears, and
`test_the_panel_keeps_fetching_after_the_change` proves the panel is
still on the refresh cadence three throttle windows later. Break either
and the "never wrong" tests above are worth nothing.

NOTHING HERE TOUCHES `~/.acervator` OR `~/.acervator_logs`. The tab is
built alone -- no MainWindow, no settings manager -- and `self._fetcher`
is replaced before anything is awaited, so no exchange and no network is
reached.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterator

import pytest

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink

# Set before the fixture imports PySide6, which is this module's only
# route to Qt. Nothing above touches it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if TYPE_CHECKING:                       # pragma: no cover
    from PySide6.QtWidgets import QApplication

SYMBOLS = "charts.13.002.postcondition.panel_symbols_current"

# The two markets the tests move a bot between. The candle VALUES are
# generated per market below, so the tape a chart is holding names the
# market it came from without a pinned constant anywhere.
OLD_PAIR = "BTC/USD"
NEW_PAIR = "ETH/USD"


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """The QApplication the widget tests run against."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication as _QApplication

    running = _QApplication.instance()
    if isinstance(running, _QApplication):
        return running
    return _QApplication(sys.argv)


@contextlib.contextmanager
def _tab(qapp: QApplication) -> Iterator[Any]:
    """The REAL `TradeChartsTab`, destroyed so nothing outlives the test.

    `deleteLater` only POSTS the destruction; `sendPostedEvents` with
    `DeferredDelete` is what runs it. `setParent(None)` is not used --
    this widget never had a parent, so it would be a no-op.
    """
    from PySide6.QtCore import QCoreApplication, QEvent
    from src.gui.main_window import TradeChartsTab

    widget = TradeChartsTab()
    try:
        yield widget
    finally:
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()


@dataclass(frozen=True)
class _Raw:
    """One OHLCV row of the shape `ChartDataFetcher.fetch` returns."""

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def _tape(count: int, base: float) -> list[_Raw]:
    """A tape whose closes identify the market it came from."""
    return [_Raw(time=1_700_000_000 + i * 60, open=base + i, high=base + i + 1,
                 low=base - 1.0, close=base + i, volume=10.0 + i)
            for i in range(count)]


class _Recorder:
    """A `ChartDataFetcher` stand-in that answers per market and records.

    `asked` is the evidence: every pair the tab really handed the
    fetcher, in order, with the timeframe and the connector object it
    chose for that pair.
    """

    def __init__(self, book: dict[str, list[_Raw]]) -> None:
        self.book = book
        self.asked: list[tuple[str, str, Any]] = []

    async def fetch(self, symbol: str, timeframe: str = "1h",
                    exchange: Any = None, limit: int = 100) -> Any:
        del limit
        self.asked.append((symbol, timeframe, exchange))
        rows = self.book.get(symbol)
        if rows is None:
            # What the real fetcher does with a market the venue does
            # not list: an empty answer carrying the source that
            # refused it.
            return [], f"exchange: no market {symbol}"
        return rows, f"exchange:{symbol}"

    def pairs(self) -> list[str]:
        return [asked[0] for asked in self.asked]


def _status(bot_id: str, symbol: str, price: float = 0.0,
            exchange: str = "coinbase") -> dict:
    """One `get_status()` snapshot of the shape `update_charts` reads."""
    return {"bot_id": bot_id, "symbol": symbol, "mode": "scrumming",
            "exchange": exchange, "state": "running",
            "stats": {"current_price": price}}


def _closes(chart: Any) -> list[float]:
    return [candle.close for candle in (getattr(chart, "_candles", None) or [])]


def _book_closes(book: dict[str, list[_Raw]], pair: str) -> list[float]:
    """The second witness: the closes the BOOK holds for that market."""
    return [row.close for row in book[pair]]


@contextlib.contextmanager
def _collect() -> Iterator[SignalSink]:
    """Install a fresh sink and restore the PREVIOUS one, never None."""
    sink = SignalSink()
    previous = sc.get_sink()
    sc.reset_throttle()
    sc.set_sink(sink)
    try:
        yield sink
    finally:
        sc.set_sink(previous)
        sc.reset_throttle()


# -- the fetch target, read at the consumer ----------------------------


def test_the_fetch_target_follows_the_bots_symbol(qapp: QApplication) -> None:
    """THE ISSUE. A bot's pair changes; the next fetch asks for the new
    one and the chart ends up holding the new one's tape.

    Both halves are read downstream of the repair: the pair handed to
    the fetcher, and the closes that ended up on the widget. Neither is
    `info["symbol"]`, which is the field the repair writes -- reading
    that back would prove a dict assignment and nothing else.

    NO THROTTLE IS CLEARED BY HAND ANYWHERE IN THIS TEST. Both fetches
    fall inside one 30 s window, so the second one runs only because the
    symbol change re-armed the panel itself.
    """
    book = {OLD_PAIR: _tape(3, 100.0), NEW_PAIR: _tape(7, 20.0)}
    with _tab(qapp) as tab:
        fetcher = _Recorder(book)
        tab._fetcher = fetcher
        connector = object()

        tab.update_charts([_status("alpha", OLD_PAIR)])
        asyncio.run(tab.fetch_chart_data({"coinbase": connector}))
        chart = tab._chart_panels["alpha"]["panel"].chart

        assert fetcher.pairs() == [OLD_PAIR]
        assert _closes(chart) == _book_closes(book, OLD_PAIR)

        tab.update_charts([_status("alpha", NEW_PAIR)])
        asyncio.run(tab.fetch_chart_data({"coinbase": connector}))

        # The fetch target moved ...
        assert fetcher.pairs() == [OLD_PAIR, NEW_PAIR]
        assert fetcher.asked[-1][2] is connector
        # ... and so did what the operator is looking at. The two tapes
        # share no close, so this cannot pass on stale candles.
        assert _closes(chart) == _book_closes(book, NEW_PAIR)
        assert not set(_closes(chart)) & set(_book_closes(book, OLD_PAIR))
        # The header names the market whose candles are on the chart.
        assert chart._symbol.startswith(NEW_PAIR)


def test_the_same_panel_is_reused_and_keeps_the_operators_timeframe(
        qapp: QApplication) -> None:
    """The panel is RESET, not rebuilt.

    Rebuilding the widget would answer the issue too, and would throw
    away the timeframe and the indicator toggles the operator set on
    that chart. This holds the choice: same widget object, same combo
    value, and the fetch after the change carries that timeframe.
    """
    book = {OLD_PAIR: _tape(3, 100.0), NEW_PAIR: _tape(4, 20.0)}
    with _tab(qapp) as tab:
        fetcher = _Recorder(book)
        tab._fetcher = fetcher
        tab.update_charts([_status("alpha", OLD_PAIR)])
        panel = tab._chart_panels["alpha"]["panel"]
        panel._tf_combo.setCurrentText("15m")
        panel.chart._show_macd = True

        tab.update_charts([_status("alpha", NEW_PAIR)])
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))

        assert tab._chart_panels["alpha"]["panel"] is panel
        assert panel.timeframe == "15m"
        assert panel.chart._show_macd is True
        assert fetcher.asked[-1][:2] == (NEW_PAIR, "15m")


def test_an_unknown_new_pair_shows_empty_not_the_old_pairs_candles(
        qapp: QApplication) -> None:
    """THE RESURRECTION GUARD.

    An empty answer calls `set_error(source)`, which does not clear
    `CandlestickChart._candles`. Re-pointing the fetch WITHOUT clearing
    the candles therefore reproduces the whole defect the moment the new
    pair is one the venue does not list: the title says the new pair,
    the tape is still the old pair's, and the fetch is now innocent.

    The book here has no entry for the new pair, so the fetcher answers
    empty. The chart must be EMPTY, and the message on it must name the
    pair that was actually asked for.
    """
    book = {OLD_PAIR: _tape(5, 100.0)}
    with _tab(qapp) as tab:
        fetcher = _Recorder(book)
        tab._fetcher = fetcher
        tab.update_charts([_status("alpha", OLD_PAIR)])
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        chart = tab._chart_panels["alpha"]["panel"].chart
        assert _closes(chart) == _book_closes(book, OLD_PAIR)

        tab.update_charts([_status("alpha", "NOPE/USD")])
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))

        assert fetcher.pairs() == [OLD_PAIR, "NOPE/USD"]
        assert _closes(chart) == []
        assert "NOPE/USD" in chart._error_text


def test_the_old_pairs_trade_markers_do_not_survive_the_change(
        qapp: QApplication) -> None:
    """Markers are anchored to PRICES, so they belong to one market.

    `update_charts` replaces them only inside `if trades_for_bot:`, so a
    bot moving to a pair it has not traded yet kept the old market's
    markers drawn over the new market's candles. Measured before the
    repair: 1 marker on BTC/USD, still 1 after the move to ETH/USD.
    """
    class _Bot:
        bot_id = "alpha"

    class _Manager:
        def get_bot(self, bot_id: str) -> Any:
            del bot_id
            return _Bot()

    manager = _Manager()
    with _tab(qapp) as tab:
        tab._fetcher = _Recorder({OLD_PAIR: _tape(3, 100.0),
                                  NEW_PAIR: _tape(3, 20.0)})
        tab.update_charts([_status("alpha", OLD_PAIR)], bot_manager=manager)
        tab.log_trade({"bot_id": "alpha", "symbol": OLD_PAIR,
                       "ts": 1_700_000_060, "side": "buy", "price": 100.0,
                       "role": "SCRUM"})
        tab.update_charts([_status("alpha", OLD_PAIR)], bot_manager=manager)
        chart = tab._chart_panels["alpha"]["panel"].chart
        # The control: the marker really is there to be lost.
        assert len(chart._markers) == 1

        tab.update_charts([_status("alpha", NEW_PAIR)], bot_manager=manager)
        assert chart._markers == []


def test_the_change_is_announced_on_the_operators_log(
        qapp: QApplication, capture_log) -> None:
    """The issue's third complaint: no error, no empty chart, NO LOG LINE.

    `capture_log`, not `caplog`: the logging engine sets
    `propagate = False` on the `acervator` node, so `caplog` sees these
    records only when no earlier test has built the engine.
    """
    with _tab(qapp) as tab:
        tab._fetcher = _Recorder({OLD_PAIR: _tape(2, 100.0)})
        tab.update_charts([_status("alpha", OLD_PAIR)])
        with capture_log("acervator.gui", logging.INFO) as records:
            tab.update_charts([_status("alpha", NEW_PAIR)])
        lines = [record.getMessage() for record in records]
    assert any(OLD_PAIR in line and NEW_PAIR in line for line in lines), lines


# -- the controls that keep the above from passing vacuously -----------


def test_a_steady_symbol_leaves_the_panel_alone(qapp: QApplication) -> None:
    """CONTROL 1. The reset must fire on a CHANGE and on nothing else.

    `update_charts` runs every 2 s for every panel. A reset on every
    pass would leave every chart permanently empty and permanently
    re-arming -- and a chart that shows nothing is never caught showing
    the wrong pair, so every assertion above would still pass.

    Ten passes with the same symbol: the candles stay, the throttle is
    untouched, no message is written over the chart, and the fetcher is
    asked exactly once.
    """
    book = {OLD_PAIR: _tape(6, 100.0)}
    with _tab(qapp) as tab:
        fetcher = _Recorder(book)
        tab._fetcher = fetcher
        tab.update_charts([_status("alpha", OLD_PAIR)])
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        chart = tab._chart_panels["alpha"]["panel"].chart
        armed_at = tab._chart_panels["alpha"]["last_fetch"]
        assert armed_at > 0

        for _ in range(10):
            tab.update_charts([_status("alpha", OLD_PAIR, price=1.25)])
            asyncio.run(tab.fetch_chart_data({"coinbase": object()}))

        assert fetcher.pairs() == [OLD_PAIR]              # throttle held
        assert tab._chart_panels["alpha"]["last_fetch"] == armed_at
        assert _closes(chart) == _book_closes(book, OLD_PAIR)
        assert chart._error_text == ""


def test_the_panel_keeps_fetching_after_the_change(
        qapp: QApplication) -> None:
    """CONTROL 2. A panel that stopped fetching would pass every test in
    this file that only asks whether the OLD pair is still being asked
    for. This one asks whether anything is being asked for at all.

    Three throttle windows are crossed by winding `last_fetch` back past
    the 30 s check -- the clock is not mocked, so this is how a later
    window is reached. Each window must produce exactly one more fetch,
    and every one of them must name the new pair.
    """
    book = {OLD_PAIR: _tape(3, 100.0), NEW_PAIR: _tape(9, 20.0)}
    with _tab(qapp) as tab:
        fetcher = _Recorder(book)
        tab._fetcher = fetcher
        tab.update_charts([_status("alpha", OLD_PAIR)])
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        tab.update_charts([_status("alpha", NEW_PAIR)])
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        assert fetcher.pairs() == [OLD_PAIR, NEW_PAIR]

        for window in range(3):
            info = tab._chart_panels["alpha"]
            info["last_fetch"] = info["last_fetch"] - 31.0
            tab.update_charts([_status("alpha", NEW_PAIR)])
            asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
            assert len(fetcher.asked) == 3 + window, fetcher.pairs()

        assert set(fetcher.pairs()[1:]) == {NEW_PAIR}
        chart = tab._chart_panels["alpha"]["panel"].chart
        assert _closes(chart) == _book_closes(book, NEW_PAIR)


def test_the_panel_renders_the_new_pair_rather_than_the_old_one(
        qapp: QApplication) -> None:
    """The rendered pixels, not the model.

    Three renders of the SAME widget: the old pair's tape, the moment
    after the change, and the new pair's tape. The first and the last
    must differ -- two markets whose prices share no value cannot paint
    the same picture -- and the last must differ from the blank the
    middle one is, which is the check a chart that quietly stopped
    drawing would fail.
    """
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QWidget
    from qt_pixel import pixel_at, render_widget

    def _paint(widget: QWidget) -> list[str]:
        """Render once and read a grid of points off THAT image.

        The image is held in a local for the whole read.
        `render_widget(...).bits()` hands back a view into an image that
        is already collected, which segfaults the runner (exit 139, no
        failure summary) -- measured on this test.

        The grid is derived from the image the widget actually produced.
        The panel carries a minimum size, so a requested 640x400 comes
        back 985x300 and a fixed grid samples off the edge.
        """
        image = render_widget(widget)
        step = 8
        points = [QPoint(x, y)
                  for y in range(step, image.height() - step, step)
                  for x in range(step, image.width() - step, step)]
        assert len(points) > 1000, len(points)
        return [pixel_at(image, point) for point in points]

    book = {OLD_PAIR: _tape(40, 100.0), NEW_PAIR: _tape(40, 20.0)}
    with _tab(qapp) as tab:
        tab._fetcher = _Recorder(book)
        tab.update_charts([_status("alpha", OLD_PAIR)])
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        panel = tab._chart_panels["alpha"]["panel"]
        old_paint = _paint(panel)

        tab.update_charts([_status("alpha", NEW_PAIR)])
        blank_paint = _paint(panel)

        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        new_paint = _paint(panel)

    assert old_paint != blank_paint        # the old tape came off screen
    assert new_paint != blank_paint        # the new tape went on screen
    assert new_paint != old_paint          # and it is not the old picture
    # Not merely different -- a painted tape puts colours on the panel
    # that the cleared one does not have. A chart that stopped drawing
    # would satisfy the three inequalities above and fail these two.
    assert len(set(new_paint)) > len(set(blank_paint))
    assert len(set(old_paint)) > len(set(blank_paint))


# -- the emitter that reports this condition ---------------------------


def test_the_drift_pin_is_clean_across_a_symbol_change(
        qapp: QApplication) -> None:
    """`charts.13.002` counts panels storing a pair the status does not
    name. Before the repair the sequence below produced `actual=1`; that
    is the number the pin reports from live data, so it is asserted here
    at the change rather than waited for.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab._fetcher = _Recorder({OLD_PAIR: _tape(2, 100.0),
                                  NEW_PAIR: _tape(2, 20.0)})
        tab.update_charts([_status("alpha", OLD_PAIR)])
        tab.update_charts([_status("alpha", NEW_PAIR)])
        record = [r for r in sink.records() if r.name == SYMBOLS][-1]
    assert record.ok is True, record.context
    assert record.actual == 0
    assert record.expected == 0
    assert record.context["panels"] == 1
