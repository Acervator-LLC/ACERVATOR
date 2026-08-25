"""Pins the six History tab emitters -- queue item #2, subsystem `history`.

    history.05.002.postcondition.trades_stored
    history.05.003.postcondition.filter_options_built
    history.05.004.postcondition.filters_applied
    history.05.005.postcondition.page_rendered
    history.05.006.postcondition.joiner_indexes_built
    history.05.007.postcondition.csv_exported

THEY ARE TOGGLE PINS AND CARRY NO CADENCE EXPECTATION. Every one of them
fires only when the operator has the History tab open and presses
something -- Refresh, Apply, Reset, Prev, Next, Export CSV. Nothing in
this tab runs on a loop, nothing polls it on a timer, and there is no
interval at which a healthy tab must be seen emitting. A monitor that
reads silence here as a stopped pin would report every session in which
the operator did not open the tab, which is most of them. Item #14 needs
that stated rather than inferred: these six are ON DEMAND.

WHAT EACH ONE ASSERTS, AND WHY IT IS NOT THE ARGUMENT THAT WENT IN.

  `trades_stored`        counts the rows in `_all_trades` that still
                         satisfy the fetch's own two admission rules,
                         against how many rows the list holds. Echoing
                         `len(result)` would report the fetch's own claim
                         back and could never disagree with it.
  `filter_options_built` reads both dropdowns back entry by entry and
                         reports the symmetric difference against the
                         distinct values loaded. A count would agree with
                         a list of the right size holding wrong members.
  `filters_applied`      re-reads the retained rows against the COMBOS,
                         not against the locals the filter loop used, so
                         a block wired to the wrong widget is visible.
  `page_rendered`        walks the table and counts rows whose timestamp
                         cell exists, against the pagination arithmetic.
                         `rowCount()` alone returns whatever
                         `setRowCount` was handed, drawn or not.
  `joiner_indexes_built` reads the two joiner dicts back out against the
                         entries the two loops accepted. This is the
                         silent-collapse detector: the fail-soft handlers
                         empty an index, and an emptied index renders the
                         same em dash as "this bot never traded".
  `csv_exported`         counts the FILE'S own records through
                         `csv.reader`, against the rows that were handed
                         to the writer.

EVERY PIN HERE HAS A FALSIFIER, AND THE FALSIFIER IS THE EVIDENCE. A pin
seen only passing proves that it fires, not that it can fail. Each
`..._is_reported` test below drives the real widget with a real defect
staged at a real seam -- a dropdown that loses an entry, a stale filter
read, a table that stops taking cells, a log reader that throws
mid-iteration, a short write -- and asserts `ok` False with the two
halves far enough apart to name the fault.

THE DURATION RIDES ON ONE PIN ONLY. `trades_stored` is the only site in
this tab behind network I/O, and it is the only one carrying a
`duration`. The other five are counting and set arithmetic over data
already in memory; a number on any of them would be fabricated, and a
fabricated duration is worse than a missing one. See
`test_the_fetch_duration_tracks_the_real_fetch` for the two-workload
lever and `_tracks_the_fetch` for the predicate, which ADDS a floor to
the project's `_tracks` and relaxes nothing.

NOTHING HERE TOUCHES `~/.acervator_logs` OR `~/.acervator`. The joiner
reads live gate.log and voting.log through `src.trading.live_log_reader`;
`_no_live_logs` stubs both readers for every Qt test in this module, so
no test in this file can reach the operator's live logs. The CSV export
tests write only into pytest's `tmp_path`.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import os
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterator, Optional

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.core import signal_contract as sc  # noqa: E402
from src.core.signal_contract import SignalSink  # noqa: E402

# Imported, not forked. `_tracks` is the project's duration predicate and
# this module has no standing to relax it; the site rule below WRAPS it
# and only ever adds a condition.
from tests.test_signal_operation_duration import _tracks  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    # Annotation only. PySide6 must not be imported at module scope: the
    # predicate control below is pure Python and has to run on a box
    # without Qt.
    from PySide6.QtWidgets import QApplication

    from src.gui.history_tab import HistoryTab

TRADES = "history.05.002.postcondition.trades_stored"
OPTIONS = "history.05.003.postcondition.filter_options_built"
FILTERS = "history.05.004.postcondition.filters_applied"
PAGE = "history.05.005.postcondition.page_rendered"
JOINER = "history.05.006.postcondition.joiner_indexes_built"
CSV = "history.05.007.postcondition.csv_exported"

# The two workloads the duration lever drives, and the poll that quantises
# them.
#
# `_kick_async_fetch` observes its future through a `QTimer` on a 400 ms
# interval, so a recorded duration is the true fetch time plus up to one
# poll. The levers are chosen so the quantum cannot close the gap: the
# short reading cannot exceed 0.05 + 0.4 = 0.45 s and the long reading
# cannot fall below 1.60 s, which is 3.6x clear of the 2x `_tracks` asks
# for. The lever is `asyncio.sleep` on the fetch loop's own thread, which
# is where the real fetch waits on the network, and it never touches the
# clock, the emit call or the `duration` argument.
POLL_S = 0.4
LEVER_SHORT_S = 0.05
LEVER_LONG_S = 1.60


# ── the duration predicate: pure Python, runs without Qt ───────────────


def _tracks_the_fetch(short: Optional[float], long_: Optional[float]) -> bool:
    """Ask `_tracks`, then put a floor under the long reading.

    `_tracks` asks that the long reading be more than twice the short
    one. That is necessary and it is not sufficient at a site whose stop
    clock can be moved: with the bracket collapsed above the work both
    readings fall to the cost of two `time.monotonic()` calls, and two
    values that small differ by more than a factor of two on ordinary
    clock jitter, so a ratio alone accepts the blinding it exists to
    catch.

    The floor is the part a ratio cannot do. The long lever burns
    1.60 s inside the fetch, so a reading under half of that -- 0.80 s --
    is a bracket that did not span the work, whatever its ratio to the
    short reading. This ADDS that condition and relaxes none: everything
    `_tracks` refuses is still refused here.
    """
    if short is None or long_ is None:
        return False
    if long_ < LEVER_LONG_S / 2.0:
        return False
    return _tracks(short, long_)


def test_the_fetch_duration_predicate_can_fail() -> None:
    """The other half of the lever. No Qt, so it runs on any box.

    A predicate only ever driven in the passing direction is a claim
    about the predicate. Each pair below is a real blinding.
    """
    # A collapsed bracket: both readings are two clock reads apart. The
    # ratio ACCEPTS this pair; the floor is what refuses it.
    assert _tracks(1.0e-07, 4.0e-07) is True
    assert _tracks_the_fetch(1.0e-07, 4.0e-07) is False
    # A literal substituted for the measurement: no movement at all.
    assert _tracks_the_fetch(1.0, 1.0) is False
    # A missing duration is not a passing one.
    assert _tracks_the_fetch(None, 2.0) is False
    assert _tracks_the_fetch(0.05, None) is False
    # And the real shape passes, so the predicate is not simply strict.
    assert _tracks_the_fetch(0.45, 1.60) is True


# ── Qt fixtures ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """Build the QApplication the Qt tests in this module run against.

    `importorskip` is INSIDE the fixture on purpose. The predicate
    control above is pure Python and must still run on a box without
    PySide6, which a module-level skip would prevent. A skipped test is
    not evidence.
    """
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication as _QApplication

    # `instance()` is typed as the QCoreApplication base and can hand
    # back a bare QCoreApplication in a non-GUI process, which has no
    # widget machinery. Narrow it rather than assume.
    running = _QApplication.instance()
    if isinstance(running, _QApplication):
        return running
    return _QApplication(sys.argv)


@pytest.fixture(autouse=True)
def _no_live_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this module reads EMPTY live logs unless it says so.

    `_build_joiner_indexes_for_page` imports the live reader at call time
    and points it at `~/.acervator_logs`, which on the operator's machine
    is a live trading log the suite has no business reading and 262 MB
    the suite has no business parsing. Both readers are replaced here for
    the whole module; the joiner tests replace them again with their own
    fixtures.
    """
    pytest.importorskip("PySide6")
    import src.trading.live_log_reader as llr

    monkeypatch.setattr(llr, "live_gate_decisions", lambda *a, **kw: iter(()))
    monkeypatch.setattr(llr, "live_voting_panel_snapshots", lambda *a, **kw: iter(()))


@pytest.fixture(scope="module")
def async_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """A real asyncio loop on its own thread, as the platform provides.

    `_kick_async_fetch` schedules onto `bot_manager._async_loop` with
    `run_coroutine_threadsafe`, so a loop that is not actually running on
    another thread would never complete the future and the pin would
    never fire. This is the real mechanism, not a stub of it.
    """
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield loop
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5.0)
    loop.close()


# ── helpers ────────────────────────────────────────────────────────────


class _FakeBotManager:
    """The two attributes the tab reads off the bot manager."""

    def __init__(
        self,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._async_loop = loop
        self._bots: dict = {}


def _tab(loop: Optional[asyncio.AbstractEventLoop] = None) -> HistoryTab:
    from src.gui.history_tab import HistoryTab

    tab = HistoryTab()
    tab.set_bot_manager(_FakeBotManager(loop))
    return tab


def _row(
    tid: str,
    symbol: str = "CHIP/USD",
    exchange: str = "coinbase",
    side: str = "BUY",
    ts: float = 0.0,
    price: float = 10.0,
    amount: float = 2.0,
) -> dict:
    """One normalized trade row, the shape `normalize_trade` returns."""
    from datetime import datetime, timezone

    return {
        "id": tid,
        "exchange": exchange,
        "symbol": symbol,
        "side": side,
        "amount": amount,
        "price": price,
        "cost": amount * price,
        "fee": 0.01,
        "fee_currency": "USD",
        "timestamp": ts,
        "datetime": (datetime.fromtimestamp(ts, tz=timezone.utc) if ts > 0 else None),
    }


def _records(sink: SignalSink, name: str) -> list:
    return [r for r in sink.records() if r.name == name]


@contextlib.contextmanager
def _collect() -> Iterator[SignalSink]:
    """Install a fresh sink and restore the PREVIOUS one, never None.

    `set_sink` is process-global. Restoring None instead of the sink that
    was there would switch the instrument off for whatever ran before
    this test, which is the shape of a suite that reports clean because
    nothing was watching.
    """
    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        yield sink
    finally:
        sc.set_sink(previous)


def _pump(app: QApplication, ready: Callable[[], bool], timeout: float = 12.0) -> bool:
    """Spin the Qt event loop until `ready()`, or until `timeout`.

    The fetch is observed by a `QTimer`, so the pin cannot fire unless
    something pumps the GUI thread. This is what the operator's running
    application does for free.
    """
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if ready():
            return True
        time.sleep(0.01)
    app.processEvents()
    return ready()


def _run_fetch(
    app: QApplication,
    loop: asyncio.AbstractEventLoop,
    monkeypatch: pytest.MonkeyPatch,
    rows_for: Callable[[float], list],
    delay_s: float = 0.0,
) -> tuple:
    """Drive the REAL `_kick_async_fetch` end to end; return the sink.

    `rows_for` is handed the `since_ts` the tab computed off its own From
    date edit, so a test can place a row deliberately outside the window
    without hard-coding the launch date.
    """
    import src.gui.history_helpers as helpers

    captured: dict = {}

    async def _fake_fetch(
        bot_manager: _FakeBotManager, since_ts: float, *a: object, **kw: object
    ) -> list:
        # The bot manager is captured, not discarded: the tab passes its
        # own `_bot_manager` positionally, and a fetch handed the wrong
        # object would return nothing and look like an empty account.
        captured["bot_manager"] = bot_manager
        captured["since_ts"] = since_ts
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        return rows_for(since_ts)

    monkeypatch.setattr(helpers, "fetch_all_history_chunked", _fake_fetch)
    tab = _tab(loop)
    with _collect() as sink:
        tab.refresh()
        got = _pump(app, lambda: bool(_records(sink, TRADES)))
    assert got, "the fetch pin never fired; the future never completed"
    return tab, sink, captured


# ── 05.002 trades_stored ───────────────────────────────────────────────


def test_the_fetch_pin_reports_the_rows_that_landed(
    qapp: QApplication,
    async_loop: asyncio.AbstractEventLoop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clean fetch: every stored row is admissible."""

    def rows(since_ts: float) -> list:
        return [
            _row("t1", ts=since_ts + 10),
            _row("t2", ts=since_ts + 20),
            _row("t3", symbol="RAVE/USD", ts=since_ts + 30),
        ]

    tab, sink, captured = _run_fetch(qapp, async_loop, monkeypatch, rows)
    assert captured["bot_manager"] is tab._bot_manager
    rec = _records(sink, TRADES)[0]
    assert rec.actual == 3
    assert rec.expected == 3
    assert rec.ok is True
    assert rec.context["distinct_keys"] == 3
    assert rec.context["since_ts"] == float(captured["since_ts"])
    # `actual` was read out of the STORED list, not off the fetch return.
    assert len(tab._all_trades) == 3


def test_a_duplicate_or_out_of_window_row_is_reported(
    qapp: QApplication,
    async_loop: asyncio.AbstractEventLoop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE ADMISSION CONTROL.

    The dedupe key is `(exchange, symbol, id)` and it is held inside
    `fetch_all_history_chunked` across the pairs it walks. A duplicate
    that survives it, or a row older than the From date, is displayed,
    graded, exported and pushed to the Simulator exactly like a good row.
    Nothing downstream re-checks either rule, so if this pin cannot see
    them, nothing can.
    """

    def rows(since_ts: float) -> list:
        return [
            _row("t1", ts=since_ts + 10),
            _row("t1", ts=since_ts + 10),  # duplicate key
            _row("t2", ts=since_ts - 5_000),  # before the window
            _row("t3", ts=since_ts + 30),
        ]

    tab, sink, _ = _run_fetch(qapp, async_loop, monkeypatch, rows)
    rec = _records(sink, TRADES)[0]
    assert rec.expected == 4  # four rows were stored
    assert rec.actual == 2  # two of them are admissible
    assert rec.ok is False
    assert rec.context["distinct_keys"] == 3
    assert len(tab._all_trades) == 4


def test_the_fetch_duration_tracks_the_real_fetch(
    qapp: QApplication,
    async_loop: asyncio.AbstractEventLoop,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE DURATION LEVER. Two known workloads, one site, no clock touched.

    The lever is `asyncio.sleep` INSIDE the fetch coroutine, on the loop
    thread where a real fetch waits on the exchange. It lengthens the
    operation the bracket spans. It never touches `start_ts`, the
    subtraction, or the `duration=` argument, so the value read back is
    the site's own measurement of work that genuinely took that long.
    """

    def rows(since_ts: float) -> list:
        return [_row("t1", ts=since_ts + 10)]

    _, sink_s, _ = _run_fetch(
        qapp, async_loop, monkeypatch, rows, delay_s=LEVER_SHORT_S
    )
    short = _records(sink_s, TRADES)[0].duration
    _, sink_l, _ = _run_fetch(qapp, async_loop, monkeypatch, rows, delay_s=LEVER_LONG_S)
    long_ = _records(sink_l, TRADES)[0].duration
    assert short is not None and long_ is not None
    # The short reading cannot exceed one lever plus one poll interval.
    assert short < LEVER_SHORT_S + POLL_S + 1.0, short
    assert _tracks_the_fetch(short, long_), (short, long_)


# ── 05.003 filter_options_built ────────────────────────────────────────


def _loaded_tab() -> HistoryTab:
    tab = _tab()
    tab._all_trades = [
        _row("a1", symbol="CHIP/USD", exchange="coinbase", ts=1_000),
        _row("a2", symbol="RAVE/USD", exchange="coinbase", ts=1_010),
        _row("a3", symbol="MOSS/USD", exchange="kraken", ts=1_020, side="SELL"),
    ]
    return tab


def test_the_dropdowns_offer_exactly_what_was_loaded(qapp: QApplication) -> None:
    tab = _loaded_tab()
    with _collect() as sink:
        tab._populate_filter_options()
    rec = _records(sink, OPTIONS)[0]
    assert rec.actual == 0
    assert rec.expected == 0
    assert rec.ok is True
    assert rec.context["symbols_offered"] == 3
    assert rec.context["exchanges_offered"] == 2
    # Read the widget itself, not the record, to confirm the record.
    offered = {tab._sym_combo.itemText(i) for i in range(tab._sym_combo.count())}
    assert offered == {"(all)", "CHIP/USD", "MOSS/USD", "RAVE/USD"}


def test_a_dropdown_that_loses_an_entry_is_reported(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE DROPDOWN CONTROL. A list of the wrong MEMBERS, not the wrong size.

    Staged at the widget boundary: one `addItem` does not land. That is
    what a rebuild behind `blockSignals` looks like when it goes wrong,
    and a `count()` check would still have to be wrong by a whole entry
    to notice. Here the entry is simply absent and the symmetric
    difference names it.
    """
    tab = _loaded_tab()
    real_add = tab._sym_combo.addItem

    def _drops_rave(text: str, *a: object, **kw: object) -> None:
        if text == "RAVE/USD":
            return None
        return real_add(text, *a, **kw)

    monkeypatch.setattr(tab._sym_combo, "addItem", _drops_rave)
    with _collect() as sink:
        tab._populate_filter_options()
    rec = _records(sink, OPTIONS)[0]
    assert rec.actual == 1
    assert rec.expected == 0
    assert rec.ok is False
    assert rec.context["symbols_offered"] == 2
    assert rec.context["symbols_loaded"] == 3


# ── 05.004 filters_applied ─────────────────────────────────────────────


def _filterable_tab() -> HistoryTab:
    tab = _loaded_tab()
    # A prior fetch exists, so Apply filters rather than kicking a fetch.
    tab._last_fetched_ts = time.time()
    tab._populate_filter_options()
    tab._from_dt.setDateTime(tab._from_dt.minimumDateTime())
    return tab


def test_every_retained_row_matches_the_selected_filters(qapp: QApplication) -> None:
    tab = _filterable_tab()
    tab._side_combo.setCurrentIndex(tab._side_combo.findText("BUY"))
    with _collect() as sink:
        tab._apply_filters()
    rec = _records(sink, FILTERS)[0]
    assert rec.actual == 0
    assert rec.expected == 0
    assert rec.ok is True
    assert rec.context["side"] == "BUY"
    assert rec.context["kept"] == 2
    assert {r["side"] for r in tab._filtered} == {"BUY"}


def test_a_row_that_beat_the_filter_is_reported(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE STALE-READ CONTROL.

    Five predicates are read off three combos and two date edits, and the
    filter loop and the operator's selection are two different reads of
    the same widgets. Staged here: the loop reads `(all)` while the
    combo holds `BUY` -- a block wired to a stale or neighbouring widget.
    Every SELL row is retained and the pin reports the ones that do not
    match what the operator actually selected.
    """
    tab = _filterable_tab()
    tab._side_combo.setCurrentIndex(tab._side_combo.findText("BUY"))
    calls = {"n": 0}
    real_text = tab._side_combo.currentText

    def _stale() -> str:
        calls["n"] += 1
        # The FIRST read is the filter loop's. Every later read -- the
        # pin's -- sees what the operator selected.
        return "(all)" if calls["n"] == 1 else real_text()

    monkeypatch.setattr(tab._side_combo, "currentText", _stale)
    with _collect() as sink:
        tab._apply_filters()
    rec = _records(sink, FILTERS)[0]
    assert rec.actual == 1  # the one SELL row that slipped
    assert rec.expected == 0
    assert rec.ok is False
    assert rec.context["side"] == "BUY"
    assert rec.context["kept"] == 3


# ── 05.005 page_rendered ───────────────────────────────────────────────


def _paged_tab(n_rows: int) -> HistoryTab:
    tab = _tab()
    tab._all_trades = [_row(f"p{i}", ts=1_000 + i) for i in range(n_rows)]
    tab._filtered = list(tab._all_trades)
    return tab


def test_the_table_draws_a_full_page_and_a_short_last_page(qapp: QApplication) -> None:
    tab = _paged_tab(250)
    with _collect() as sink:
        tab._page = 0
        tab._render_page()
        tab._page = 2
        tab._render_page()
    first, last = _records(sink, PAGE)[0], _records(sink, PAGE)[1]
    assert (first.actual, first.expected, first.ok) == (100, 100, True)
    assert (last.actual, last.expected, last.ok) == (50, 50, True)
    assert last.context["page"] == 2
    assert last.context["pages"] == 3
    # The table itself, not the record.
    assert tab._table.rowCount() == 50


def test_a_page_beyond_the_last_is_clamped_and_still_agrees(qapp: QApplication) -> None:
    """The clamp and the arithmetic are the two sides of this pin."""
    tab = _paged_tab(120)
    tab._page = 9
    with _collect() as sink:
        tab._render_page()
    rec = _records(sink, PAGE)[0]
    assert rec.context["page"] == 1  # clamped from 9
    assert (rec.actual, rec.expected, rec.ok) == (20, 20, True)


def test_a_half_drawn_table_is_reported(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE PARTIAL-RENDER CONTROL.

    `setRowCount(n)` makes `rowCount()` return `n` whether or not one
    cell was written, and the per-row work in this loop -- a grade, two
    log lookups, a `GateLightsCell` -- is where a render stops early.
    Staged here: the table stops taking timestamp cells at row 60. The
    row count still says 100.
    """
    tab = _paged_tab(250)
    real_set = tab._table.setItem

    def _stops(row: int, col: int, item: object) -> None:
        if col == 0 and row >= 60:
            return None
        return real_set(row, col, item)

    monkeypatch.setattr(tab._table, "setItem", _stops)
    with _collect() as sink:
        tab._render_page()
    rec = _records(sink, PAGE)[0]
    assert rec.actual == 60
    assert rec.expected == 100
    assert rec.ok is False
    assert rec.context["row_count"] == 100  # the table still claims 100


# ── 05.006 joiner_indexes_built ────────────────────────────────────────


def _gate_entry(bot_id: str, iso: str) -> dict:
    return {"bot_id": bot_id, "timestamp": iso, "data": {}}


ISO = "2026-08-19T12:00:0%dZ"


def test_the_joiner_buckets_every_entry_it_accepted(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.trading.live_log_reader as llr

    monkeypatch.setattr(
        llr,
        "live_gate_decisions",
        lambda *a, **kw: iter(
            [
                _gate_entry("bot-a", ISO % 1),
                _gate_entry("bot-a", ISO % 2),
                _gate_entry("bot-b", ISO % 3),
                _gate_entry("", ISO % 4),
            ]
        ),
    )
    monkeypatch.setattr(
        llr,
        "live_voting_panel_snapshots",
        lambda *a, **kw: iter(
            [_gate_entry("bot-a", ISO % 5), _gate_entry("bot-b", ISO % 6)]
        ),
    )
    tab = _tab()
    page = [_row("j1", ts=1_755_000_000.0)]
    with _collect() as sink:
        tab._build_joiner_indexes_for_page(page)
    rec = _records(sink, JOINER)[0]
    # The entry with no bot_id is not accepted and is not bucketed.
    assert rec.actual == 5
    assert rec.expected == 5
    assert rec.ok is True
    assert rec.context["gate_accepted"] == 3
    assert rec.context["voting_accepted"] == 2


def test_a_reader_that_throws_mid_iteration_is_reported(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE SILENT-COLLAPSE CONTROL, and the reason this pin exists.

    The fail-soft handler discards the WHOLE gate index on any reader
    exception. On screen that is indistinguishable from a page of trades
    with no gate history: every cell renders the same em dash. A corrupt
    line 90,000 into gate.log takes the entire Gates column down and
    nothing says so. Here the reader yields two entries and then throws.
    """
    import src.trading.live_log_reader as llr

    def _throws(*a: object, **kw: object) -> Iterator[dict]:
        yield _gate_entry("bot-a", ISO % 1)
        yield _gate_entry("bot-a", ISO % 2)
        raise ValueError("corrupt gate.log line")

    monkeypatch.setattr(llr, "live_gate_decisions", _throws)
    monkeypatch.setattr(
        llr,
        "live_voting_panel_snapshots",
        lambda *a, **kw: iter([_gate_entry("bot-b", ISO % 5)]),
    )
    tab = _tab()
    page = [_row("j1", ts=1_755_000_000.0)]
    with _collect() as sink:
        tab._build_joiner_indexes_for_page(page)
    rec = _records(sink, JOINER)[0]
    assert rec.expected == 3  # two gate entries plus one vote
    assert rec.actual == 1  # the gate index was emptied
    assert rec.ok is False
    assert rec.context["gate_accepted"] == 2
    assert rec.context["gate_buckets"] == 0
    assert tab._page_gate_index == {}


# ── 05.007 csv_exported ────────────────────────────────────────────────


def _export(tab: HistoryTab, monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    import src.gui.history_tab as hist

    class _Dialog:
        @staticmethod
        def getSaveFileName(*a: object, **kw: object) -> tuple:
            return (str(target), "CSV files (*.csv)")

    class _Box:
        @staticmethod
        def information(*a: object, **kw: object) -> None:
            return None

        @staticmethod
        def warning(*a: object, **kw: object) -> None:
            return None

    monkeypatch.setattr(hist, "QFileDialog", _Dialog)
    monkeypatch.setattr(hist, "QMessageBox", _Box)
    tab._export_csv()


def test_the_csv_holds_every_row_that_was_exported(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tab = _paged_tab(5)
    target = tmp_path / "history.csv"
    with _collect() as sink:
        _export(tab, monkeypatch, target)
    rec = _records(sink, CSV)[0]
    assert rec.actual == 5
    assert rec.expected == 5
    assert rec.ok is True
    assert rec.context["readback"] is True
    # The file itself, not the record.
    with target.open("r", newline="", encoding="utf-8") as fh:
        written = list(csv.reader(fh))
    assert len(written) == 6  # header plus five rows
    assert written[0][0] == "timestamp_utc"


def test_a_short_write_is_reported(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """THE SHORT-WRITE CONTROL.

    The message box reports `len(self._filtered)` -- the ASK -- and has
    always reported it whatever reached the disk. Staged here: the writer
    takes every row and commits every second one, which is what a partial
    flush or a row that failed to format looks like from the outside. The
    operator still sees "Wrote 6 rows".
    """
    tab = _paged_tab(6)
    target = tmp_path / "short.csv"

    real_writer = csv.writer

    class _Skips:
        def __init__(self, inner: Any) -> None:
            self._inner = inner
            self._n = 0

        def writerow(self, row: list) -> None:
            self._n += 1
            # Row 1 is the header; drop every second DATA row.
            if self._n > 1 and self._n % 2 == 0:
                return None
            return self._inner.writerow(row)

    monkeypatch.setattr(csv, "writer", lambda *a, **kw: _Skips(real_writer(*a, **kw)))
    with _collect() as sink:
        _export(tab, monkeypatch, target)
    monkeypatch.undo()
    rec = _records(sink, CSV)[0]
    assert rec.expected == 6  # six rows were handed to the writer
    assert rec.actual == 3  # three reached the file
    assert rec.ok is False
    assert rec.context["readback"] is True
    with target.open("r", newline="", encoding="utf-8") as fh:
        assert len(list(csv.reader(fh))) == 4  # header plus three
