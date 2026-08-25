"""Pins the five Asset Charts emitters -- queue item #10.6, subsystem `charts`.

    charts.13.001.invariant.panels_mounted
    charts.13.002.postcondition.panel_symbols_current
    charts.13.003.postcondition.timeframe_rearmed
    charts.13.004.postcondition.panel_refreshed
    charts.13.005.invariant.panels_fresh

THE TAB IS `TradeChartsTab`, built inline in `src/gui/main_window.py`. It
holds one `ChartPanel` per qualifying bot and feeds each one from
`ChartDataFetcher`. Every pin reads the state the NEXT caller uses -- the
widgets really in the scroll layout, the symbol the fetch really hands
the exchange, the combo the fetch really reads, the candles really on the
chart, the `last_fetch` really in the dict. Not one reads `bot_statuses`
back out as though the argument were the result.

THIS IS THE FIRST INSTRUMENTED TAB WITH A CADENCE, and item #14 needs
that stated rather than inferred. `MainWindow._setup_refresh_timer`
starts a 2000 ms `QTimer` on `_refresh_dashboard`, which calls
`update_charts` on every tick with at least one bot and schedules
`fetch_chart_data` on every tick that also has exchange connectors. So
`13-001`, `13-002`, `13-004` and `13-005` fire on a loop and silence from
them means something. `13-003` alone is a toggle: the operator moves a
timeframe combo, or it never fires.
`test_the_cadence_declaration_is_what_the_source_does` holds that split
against the syntax tree.

THREE PINS CARRY `every=30.0` AND ONE DELIBERATELY DOES NOT. At 0.5 Hz an
un-throttled pin writes 1800 records an hour; three of those would push
the rest of the network out of `RETAIN_ROWS` inside a session, so
`13-001`, `13-002` and `13-005` are folded to one record per 30 s fetch
window with `count` saying how many passes it stands for. `13-004` is
the exception on purpose: the synchroniser keys on (name, site) and its
one site serves every panel, so a throttle would admit one panel per
window and drop the rest -- hiding which panel went stale, which is all
the pin is for. It is bounded already by the tab's own 30 s check.

WHAT THE TAB HIDES, AND WHY `13-004` READS THE CHART. `fetch_chart_data`
has three outcomes. Candles call `set_candles` then `set_source`; an
empty answer calls `set_error(source)`; a raise calls
`set_error(str(exc))`. NEITHER OF THE LAST TWO CLEARS THE CANDLES
ALREADY ON THE CHART, so a panel last fed hours ago paints exactly like
one fed a second ago.
`test_a_panel_left_showing_candles_by_an_empty_fetch_is_reported` stages
that exact divergence and asserts `ok` False with the source attribution
beside it.

WHAT `13-004` CANNOT SEE, AND WHY `13-005` EXISTS. Every path through the
fetch loop body sets `last_fetch`, so a panel that stopped refreshing is
one the loop SKIPPED -- and a skipped panel emits nothing at all, which
reads exactly like a healthy quiet one.
`test_a_panel_the_fetch_loop_skips_forever_is_reported` drives the tab's
own `push_synthetic_candles` to plant a `*/USDC` panel, which the
wildcard `continue` then declines for the rest of the process.

ONE PIN CARRIES A DURATION AND IT IS THE ONLY ONE THAT MAY (E8).
`13-004` is a `postcondition` behind a real network fetch; the other four
walk a dict or a layout, and a number on any of them would be fabricated.
`test_the_duration_tracks_two_different_fetch_workloads` proves the
bracket measures the await rather than reporting a constant, and
`test_only_the_fetch_pin_carries_a_duration` holds the shape at the
source.

NOTHING HERE TOUCHES `~/.acervator` OR `~/.acervator_logs`. The widget is
constructed alone -- no `MainWindow`, no settings manager, no bot manager
-- and every fetch goes to a local stand-in, so no exchange and no
network is reached. The sink is in memory and is never given a path.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

import pytest

# `tests/conftest.py` puts the repository root on `sys.path` before any
# test module is imported, so these two import normally rather than
# after a path insert. THAT IS WHY THERE IS NO `# noqa: E402` HERE: the
# imports are at the top because they belong there, not because a
# suppression was written over a real finding.
from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink

# Set before the fixture imports PySide6, which is the module's only
# route to Qt. Nothing above touches it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent

if TYPE_CHECKING:  # pragma: no cover
    # Annotation only. PySide6 must not be imported at module scope: the
    # three source-reading tests below are pure Python and have to run on
    # a box without Qt. A skipped test is not evidence, so the skip is
    # scoped to the fixture and not to the module.
    from PySide6.QtWidgets import QApplication

MOUNTED = "charts.13.001.invariant.panels_mounted"
SYMBOLS = "charts.13.002.postcondition.panel_symbols_current"
REARMED = "charts.13.003.postcondition.timeframe_rearmed"
REFRESHED = "charts.13.004.postcondition.panel_refreshed"
FRESH = "charts.13.005.invariant.panels_fresh"

CHARTS_PINS = (MOUNTED, SYMBOLS, REARMED, REFRESHED, FRESH)

# The two pins with no `every=`. `13-003` is a toggle. `13-004` serves
# every panel from one site, so folding it would drop panels.
UNTHROTTLED = (REARMED, REFRESHED)

MAIN_WINDOW = REPO / "src" / "gui" / "main_window.py"

# Substrings that must never appear in a record this tab writes. A
# context is written to disk, and a bot id is operator-chosen text the
# privacy registry masks in the bot table.
FORBIDDEN = (
    "api_key",
    "apikey",
    "secret",
    "passphrase",
    "password",
    "credential",
    "token",
    "bot_id",
)


# ── Qt fixtures ────────────────────────────────────────────────────────


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
    """The REAL `TradeChartsTab`, torn down so nothing outlives the test.

    Constructed alone. The tab reaches the network only through
    `self._fetcher`, and every test that runs a fetch replaces that one
    collaborator with a local stand-in before awaiting anything.
    """
    from src.gui.main_window import TradeChartsTab

    widget = TradeChartsTab()
    try:
        yield widget
    finally:
        widget.close()
        widget.deleteLater()
        qapp.processEvents()


# ── helpers ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Raw:
    """One OHLCV row of the shape `ChartDataFetcher.fetch` returns."""

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def _rows(count: int) -> list[_Raw]:
    return [
        _Raw(
            time=1_700_000_000 + i * 60,
            open=1.0 + i,
            high=2.0 + i,
            low=0.5 + i,
            close=1.5 + i,
            volume=10.0 + i,
        )
        for i in range(count)
    ]


class _Fetcher:
    """A stand-in for `ChartDataFetcher` that answers from a script.

    Each entry is `(rows, source)` or an exception instance to raise.
    `delay` is awaited inside `fetch`, which is the span
    `13-004`'s duration bracket claims to measure.
    """

    def __init__(self, *answers: Any, delay: float = 0.0) -> None:
        self._answers = list(answers)
        self._delay = delay
        self.calls = 0

    async def fetch(
        self, symbol: str, timeframe: str = "1h", exchange: Any = None, limit: int = 100
    ) -> Any:
        del symbol, timeframe, exchange, limit
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        answer = (
            self._answers[min(self.calls - 1, len(self._answers) - 1)]
            if self._answers
            else ([], "empty")
        )
        if isinstance(answer, BaseException):
            raise answer
        return answer


def _status(
    bot_id: str, symbol: str, mode: str = "scrumming", exchange: str = "coinbase"
) -> dict:
    """One `get_status()` snapshot of the shape `update_charts` reads."""
    return {
        "bot_id": bot_id,
        "symbol": symbol,
        "mode": mode,
        "exchange": exchange,
        "state": "running",
        "stats": {"current_price": 0.0},
    }


def _records(sink: SignalSink, name: str) -> list:
    return [r for r in sink.records() if r.name == name]


def _only(sink: SignalSink, name: str):
    """The single record under this name, or a failure that says so."""
    got = _records(sink, name)
    assert len(got) == 1, f"{name}: expected 1 record, got {len(got)}"
    return got[0]


@contextlib.contextmanager
def _collect() -> Iterator[SignalSink]:
    """Install a fresh sink and restore the PREVIOUS one, never None.

    `set_sink` is process-global; restoring None would switch the
    instrument off for whatever ran before this test. The rate-limit
    windows are cleared too, because three of these five pins carry
    `every=30.0` and a window left standing by an earlier test would
    suppress the record this one is reading.
    """
    sink = SignalSink()
    previous = sc.get_sink()
    sc.reset_throttle()
    sc.set_sink(sink)
    try:
        yield sink
    finally:
        sc.set_sink(previous)
        sc.reset_throttle()


def _chart_emit_calls() -> list[ast.Call]:
    """Every `_ch_emit(...)` call node in `main_window.py`.

    Read from the syntax tree, the way `tools/emitter_registry_check.py`
    reads them. A regex over the source would answer a different
    question.
    """
    tree = ast.parse(MAIN_WINDOW.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_ch_emit"
    ]


def _pin_name(call: ast.Call) -> str:
    first = call.args[0]
    assert isinstance(first, ast.Constant)
    return str(first.value)


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


# ── 13-001  the panels on screen are the panels the fetch iterates ─────


def test_panel_mounting_is_reported(qapp: QApplication) -> None:
    """Two qualifying bots put two panels in the layout and the dict."""
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD"), _status("bravo", "ETH/USD")])
        rec = _only(sink, MOUNTED)
    assert rec.ok is True, rec.context
    assert rec.actual == 2
    assert rec.expected == 2
    # The stretch added in `__init__` is the third layout item and has
    # no widget, which is why the pin counts widgets and not items.
    assert rec.context["layout_items"] == 3
    assert rec.context["statuses"] == 2
    assert rec.context["kept"] == 2
    assert rec.duration is None


def test_a_panel_dropped_from_the_dict_but_left_on_screen_is_reported(
    qapp: QApplication,
) -> None:
    """THE FALSIFIER for `13-001`.

    The seam is the removal pass, which does three things in order:
    `pop` from the dict, `setParent(None)`, `deleteLater()`. Losing the
    last two leaves a chart for a bot that no longer exists sitting in
    the scroll area, and the dict -- the only thing the fetch loop reads
    -- says it is gone. Counting the panels the loop created could not
    see this. Asking the layout can.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD"), _status("bravo", "ETH/USD")])
        assert len(tab._chart_panels) == 2
        tab._chart_panels.pop("bravo")  # widget deliberately kept
        tab.update_charts([_status("alpha", "BTC/USD")])
        rec = _records(sink, MOUNTED)[-1]
    assert rec.ok is False
    assert rec.actual == 2
    assert rec.expected == 1
    assert rec.context["layout_items"] == 3


# ── 13-002  the panel fetches the pair the status names ────────────────


def test_panel_symbols_current_is_reported(qapp: QApplication) -> None:
    """A steady fleet leaves no panel fetching a pair nobody asked for."""
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD")])
        rec = _only(sink, SYMBOLS)
    assert rec.ok is True, rec.context
    assert rec.actual == 0
    assert rec.expected == 0
    assert rec.context["panels"] == 1
    assert rec.context["mounted"] == 1
    assert rec.duration is None


def test_a_panel_holding_a_pair_the_pass_does_not_name_is_reported(
    qapp: QApplication,
) -> None:
    """THE FALSIFIER for `13-002`, rewritten by issue #46.

    IT USED TO PIN THE DEFECT. `update_charts` wrote `info["symbol"]` in
    the CREATE branch only, so two passes with two pairs left the stored
    symbol on the first one and this test asserted `actual == 1`. That
    made it a valid falsifier for the pin and an obstacle to the repair,
    which is why the issue said the two had to move together. The repair
    landed on `fix-46-chart-follows-the-symbol`; the sequence it used is
    now asserted CLEAN in
    `tests/test_asset_chart_symbol_change.py::
    test_the_drift_pin_is_clean_across_a_symbol_change`, together with
    the pair the fetch really asks for afterwards.

    THE CONDITION IS STAGED DIRECTLY INSTEAD. One bot named TWICE in one
    pass with two different pairs -- what a fleet snapshot looks like
    when it is assembled either side of a symbol change -- leaves a
    panel that can be current for at most one of the two, and the pin
    counts the one it is not current for. The falsifier's job is to
    prove the instrument still fires; the repair's proof is the fetch
    target, which is read at the consumer in the file named above.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD"), _status("alpha", "ETH/USD")])
        rec = _records(sink, SYMBOLS)[-1]
        # One bot, one panel, two pairs claimed for it in one pass. The
        # panel holds the last pair the pass named, which is the one
        # `fetch_chart_data` will ask for.
        assert len(tab._chart_panels) == 1
        assert tab._chart_panels["alpha"]["symbol"] == "ETH/USD"
    assert rec.ok is False
    assert rec.actual == 1
    assert rec.expected == 0
    assert rec.context["panels"] == 1
    assert rec.context["statuses"] == 2


# ── 13-003  a timeframe change re-arms the fetch ───────────────────────


def test_timeframe_rearm_is_reported(qapp: QApplication) -> None:
    """The operator moves the real combo and the panel is re-armed.

    Driven through `ChartPanel._tf_combo`, which is what the operator
    touches: the combo emits `currentTextChanged`, the panel forwards it
    as `timeframe_changed`, and the tab's lambda carries the bot id.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD")])
        tab._chart_panels["alpha"]["last_fetch"] = 1_700_000_000.0
        tab._chart_panels["alpha"]["panel"]._tf_combo.setCurrentText("15m")
        rec = _only(sink, REARMED)
        assert tab._chart_panels["alpha"]["last_fetch"] == 0
    assert rec.ok is True, rec.context
    assert rec.actual is True
    assert rec.expected is True
    assert rec.context["requested_tf"] == "15m"
    assert rec.context["panel_tf"] == "15m"
    assert rec.context["known_bot"] is True
    assert rec.duration is None


def test_a_timeframe_change_from_a_dropped_panel_is_reported(
    qapp: QApplication,
) -> None:
    """THE FALSIFIER for `13-003`.

    The seam is the removal pass again. It pops the entry and calls
    `deleteLater`, which is queued -- the widget and its connections are
    alive until the event loop runs it. A combo change in that window
    reaches `_on_tf_changed` for a bot id the dict no longer holds, and
    the guard there is a silent no-op: nothing is re-armed, and the pin
    is the only thing that says so.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD")])
        panel = tab._chart_panels["alpha"]["panel"]
        tab.update_charts([])  # removal pass, deleteLater
        panel._tf_combo.setCurrentText("4h")
        rec = _only(sink, REARMED)
    assert rec.ok is False
    assert rec.actual is False
    assert rec.context["known_bot"] is False
    assert rec.context["requested_tf"] == "4h"
    assert rec.context["panel_tf"] == ""


# ── 13-004  the chart holds the candles THIS fetch returned ────────────


def test_a_fetch_that_returns_candles_is_reported(qapp: QApplication) -> None:
    """The success path: chart, expectation and source all agree."""
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD")])
        tab._fetcher = _Fetcher((_rows(3), "exchange"))
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        rec = _only(sink, REFRESHED)
        assert len(tab._chart_panels["alpha"]["panel"].chart._candles) == 3
    assert rec.ok is True, rec.context
    assert rec.actual == 3
    assert rec.expected == 3
    assert rec.context["outcome"] == "candles"
    assert rec.context["source"] == "exchange"
    assert rec.context["symbol"] == "BTC/USD"
    assert rec.context["timeframe"] == "1h"
    assert rec.context["exchange_id"] == "coinbase"
    assert rec.duration is not None and rec.duration >= 0.0


def test_a_panel_left_showing_candles_by_an_empty_fetch_is_reported(
    qapp: QApplication,
) -> None:
    """THE FALSIFIER for `13-004`, and the failure the operator cannot see.

    The second fetch comes back empty. `set_error(source)` writes an
    error string and leaves `CandlestickChart._candles` exactly where it
    was, so the panel keeps painting the first fetch's tape. Reading the
    chart back out is the only way to tell that apart from a fresh one;
    the source attribution then says which answer produced it.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD")])
        tab._fetcher = _Fetcher((_rows(3), "exchange"), ([], "coingecko: rate limited"))
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        tab._chart_panels["alpha"]["last_fetch"] = 0  # clear the throttle
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        rec = _records(sink, REFRESHED)[-1]
        assert len(tab._chart_panels["alpha"]["panel"].chart._candles) == 3
    assert rec.ok is False
    assert rec.actual == 3
    assert rec.expected == 0
    assert rec.context["outcome"] == "empty"
    assert rec.context["source"] == "coingecko: rate limited"


def test_a_fetch_that_raises_is_reported(qapp: QApplication) -> None:
    """The third outcome. The handler names the exception TYPE, never its
    message: an exchange error string can carry a URL with a key in it,
    and a context is written to disk."""
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD")])
        tab._fetcher = _Fetcher(RuntimeError("coinbase 401 unauthorized"))
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        rec = _only(sink, REFRESHED)
    assert rec.ok is True, rec.context  # nothing was showing before
    assert rec.actual == 0
    assert rec.expected == 0
    assert rec.context["outcome"] == "raised"
    assert rec.context["source"] == "RuntimeError"
    assert "401" not in str(rec.context)
    assert rec.duration is not None


def test_the_duration_tracks_two_different_fetch_workloads(qapp: QApplication) -> None:
    """THE CONTROL for the duration on `13-004`.

    A number that is the same for a fast fetch and a slow one is not a
    measurement. Two runs of the same code over the same panel, with the
    only difference inside the awaited call, must differ by at least the
    sleep -- which also proves the bracket really does span the await and
    not some constant beside it.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD")])
        tab._fetcher = _Fetcher((_rows(2), "exchange"), delay=0.0)
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        tab._chart_panels["alpha"]["last_fetch"] = 0
        tab._fetcher = _Fetcher((_rows(2), "exchange"), delay=0.30)
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        quick, slow = _records(sink, REFRESHED)
    assert quick.duration is not None and slow.duration is not None
    assert (
        slow.duration >= quick.duration + 0.20
    ), f"quick={quick.duration} slow={slow.duration}"
    assert quick.duration < 0.20


# ── 13-005  no panel has quietly stopped refreshing ────────────────────


def test_panel_freshness_is_reported(qapp: QApplication) -> None:
    """After a pass, every panel carries this pass's `last_fetch`."""
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD"), _status("bravo", "ETH/USD")])
        tab._fetcher = _Fetcher((_rows(4), "exchange"))
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        rec = _only(sink, FRESH)
    assert rec.ok is True, rec.context
    assert rec.actual == 0
    assert rec.expected == 0
    assert rec.context["panels"] == 2
    assert rec.context["never_fetched"] == 0
    assert rec.context["stale_after_s"] == 90.0
    assert rec.duration is None


def test_a_panel_the_fetch_loop_skips_forever_is_reported(qapp: QApplication) -> None:
    """THE FALSIFIER for `13-005`.

    `push_synthetic_candles` is the tab's own way of creating a panel
    without going through the Extractor filter, so a `*/USDC` symbol can
    land in the panel dict. The wildcard `continue` at the top of the
    fetch loop then declines that panel on this pass and on every later
    one, `last_fetch` stays 0 forever, and `13-004` never fires for it --
    the panel's silence is indistinguishable from a healthy one. Only a
    walk of the dict can see it.
    """
    with _collect() as sink, _tab(qapp) as tab:
        tab.update_charts([_status("alpha", "BTC/USD")])
        tab.push_synthetic_candles(
            "nuke", "*/USDC", _rows(5), scenario="flash", last_price=1.0
        )
        tab._fetcher = _Fetcher((_rows(4), "exchange"))
        asyncio.run(tab.fetch_chart_data({"coinbase": object()}))
        rec = _only(sink, FRESH)
        assert tab._chart_panels["nuke"]["last_fetch"] == 0
        assert len(_records(sink, REFRESHED)) == 1  # only `alpha` reported
    assert rec.ok is False
    assert rec.actual == 1
    assert rec.expected == 0
    assert rec.context["never_fetched"] == 1
    assert rec.context["panels"] == 2


# ── the shape, read off the syntax tree ────────────────────────────────


def test_only_the_fetch_pin_carries_a_duration() -> None:
    """E8 in this tab: one postcondition behind a network call, and
    nothing else. The other four walk a dict or a layout."""
    carriers = {
        _pin_name(call)
        for call in _chart_emit_calls()
        if _keyword(call, "duration") is not None
    }
    assert carriers == {REFRESHED}


def test_the_cadence_declaration_is_what_the_source_does() -> None:
    """Item #14 reads this split, so it is asserted and not narrated.

    Three pins are folded to one record per 30 s window. `13-003` is a
    toggle and carries nothing. `13-004` is deliberately un-throttled
    because its one site serves every panel.
    """
    every: dict[str, Any] = {}
    for call in _chart_emit_calls():
        node = _keyword(call, "every")
        every[_pin_name(call)] = node.value if isinstance(node, ast.Constant) else None
    assert set(every) == set(CHARTS_PINS)
    assert {name for name, value in every.items() if value is None} == set(UNTHROTTLED)
    assert {value for name, value in every.items() if name not in UNTHROTTLED} == {30.0}


def test_no_context_carries_credential_material_or_a_bot_id() -> None:
    """A context is written to disk. These contexts hold counts, ages,
    timeframes, one exchange id, one source label and one trading symbol
    -- the shape `history.05.004` already writes -- and no bot id, which
    the privacy registry masks in the bot table."""
    for call in _chart_emit_calls():
        node = _keyword(call, "context")
        assert isinstance(node, ast.Dict), _pin_name(call)
        rendered = ast.dump(node).lower()
        for banned in FORBIDDEN:
            assert banned not in rendered, (_pin_name(call), banned)
