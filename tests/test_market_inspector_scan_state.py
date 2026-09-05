"""The Market Inspector says which of three scan states it is in.

Drives ``MarketInspectorTab`` and ``MarketInspectorScreenModel`` through a
scan and reads back the note each empty table carries, the state
``scan_state`` reports, and the records ``SCAN_STARTED_TOPIC`` and
``SCAN_FINISHED_TOPIC`` leave. ``_empty_table_text`` gives an unscanned
table and a scanned-but-empty table two different sentences.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.core import event_bus as bus_module  # noqa: E402
from src.core.emit_contracts import CONTRACTS  # noqa: E402
from src.gui import market_inspector as shipped  # noqa: E402
from src.gui.main_tabs import market_inspector_surface as surface  # noqa: E402
from src.trading import market_inspector as analyzer  # noqa: E402

SHARED_INSPECTOR_NAME = "_GLOBAL_INSPECTOR"

WIDGETS_HELD: list = []


def app():
    """The process application object every widget needs."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def hold(widget):
    """Keep one widget alive so no later read reaches a collected object."""
    WIDGETS_HELD.append(widget)
    return widget


@pytest.fixture(autouse=True)
def own_shared_inspector(monkeypatch):
    """Give this test its own analyzer and restore the process one after."""
    if not hasattr(analyzer, SHARED_INSPECTOR_NAME):
        raise AssertionError(
            "src.trading.market_inspector no longer carries "
            f"{SHARED_INSPECTOR_NAME}; this guard would create that name "
            "instead of resetting the real shared analyzer."
        )
    monkeypatch.setattr(analyzer, SHARED_INSPECTOR_NAME, None)
    yield
    monkeypatch.setattr(analyzer, SHARED_INSPECTOR_NAME, None)


@pytest.fixture
def own_bus(monkeypatch):
    """Give this test its own event bus and collect what reaches it."""
    fresh = bus_module.EventBus()
    monkeypatch.setattr(bus_module, "_global_bus", fresh)
    seen: list = []
    for topic in (shipped.SCAN_STARTED_TOPIC, shipped.SCAN_FINISHED_TOPIC):
        fresh.subscribe(
            topic,
            lambda event: seen.append([event.topic, dict(event.data)]),
        )
    return seen


def seat_inspector(signals, pairs):
    """Put one analyzer stand-in in the process-wide seat."""
    setattr(
        analyzer,
        SHARED_INSPECTOR_NAME,
        surface.InspectorSource(signals=signals, pairs=pairs),
    )


def tab():
    """One built Market Inspector tab."""
    app()
    return hold(shipped.MarketInspectorTab())


def scoring_signal():
    """One market that scored, so the signals table draws a row."""
    return surface.SignalState(
        symbol="BTC",
        signal="ENTRY_LONG_HIGH",
        score=3.0,
        direction="long",
        per_tf={},
        is_active=False,
    )


class Answer:
    """What the invented fetch hands back."""

    def __init__(self, symbol_count):
        self.candles_by_symbol_by_tf = {"BTC": {"1d": []}}
        self.closes_by_symbol = {"BTC": [1.0, 2.0]}
        self.meta = {
            "source": "coingecko",
            "age_seconds": 0.0,
            "symbol_count": symbol_count,
        }


def invented_fetch(monkeypatch, symbol_count, raises=None):
    """Point the scan at one invented fetch that reaches no network.

    Returns the list each call appends its arguments to.
    """
    from src.exchange import market_inspector_fetcher

    seen: list = []

    async def answer(_connectors, active_symbols=None, progress_cb=None, **rest):
        seen.append([sorted(active_symbols or []), progress_cb, rest])
        if raises is not None:
            raise raises
        return Answer(symbol_count)

    monkeypatch.setattr(market_inspector_fetcher, "fetch_htf_universe", answer)
    return seen


def held_scheduler(taken):
    """A scheduler that takes the coroutine and closes it without running it."""

    def schedule(coro):
        taken.append(coro)
        coro.close()

    return schedule


def lines_from(work, level=logging.INFO):
    """Every line the Market Inspector logger writes while `work` runs."""
    said: list = []

    class Catch(logging.Handler):
        def emit(self, record):
            said.append(record.getMessage())

    logger = logging.getLogger(shipped.logger.name)
    handler = Catch()
    before = logger.level
    logger.addHandler(handler)
    logger.setLevel(level)
    try:
        work()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(before)
    return said


# ── the three states read differently ──────────────────────────────


def test_a_screen_nobody_scanned_yet_says_no_scan_yet():
    screen = tab()
    assert screen.scan_state() == shipped.SCAN_NOT_ASKED
    assert screen._signals_empty_lbl.text() == (
        "No scan yet. Press Refresh to look for markets."
    ), screen._signals_empty_lbl.text()
    assert screen._pairs_empty_lbl.text() == (
        "No scan yet. Press Refresh to look for opposing pairs."
    ), screen._pairs_empty_lbl.text()


def test_a_running_scan_says_it_is_scanning():
    seat_inspector([], [])
    screen = tab()
    taken: list = []
    screen.set_exchange_source(lambda: {"venue": object()}, held_scheduler(taken))
    screen._start_fetch(force=True)
    assert taken, "the scheduler was never handed the scan"
    assert screen.scan_state() == shipped.SCAN_RUNNING
    assert screen._signals_empty_lbl.text() == (
        "Scanning for markets…"
    ), screen._signals_empty_lbl.text()


def test_a_finished_scan_that_found_nothing_says_the_scan_finished(monkeypatch):
    invented_fetch(monkeypatch, symbol_count=50)
    seat_inspector([], [])
    screen = tab()
    asyncio.run(screen._fetch_and_analyze({"venue": object()}))
    assert screen.scan_state() == shipped.SCAN_FINISHED
    assert screen._signals_empty_lbl.text() == (
        "Scan finished. No markets found."
    ), screen._signals_empty_lbl.text()


def test_the_three_states_never_share_a_sentence():
    """A silent empty and a real empty must not read the same."""
    said = [
        shipped._empty_table_text(state, shipped.SIGNALS_NOUN)
        for state in (
            shipped.SCAN_NOT_ASKED,
            shipped.SCAN_RUNNING,
            shipped.SCAN_FINISHED,
        )
    ]
    assert len(set(said)) == 3, said


def test_a_table_holding_rows_hides_its_note(monkeypatch):
    """POSITIVE CONTROL: the note is not always shown."""
    invented_fetch(monkeypatch, symbol_count=50)
    seat_inspector([scoring_signal()], [])
    screen = tab()
    asyncio.run(screen._fetch_and_analyze({"venue": object()}))
    assert screen._signals_tbl.rowCount() == 1
    assert screen._signals_empty_lbl.isHidden(), "a filled table still shows its note"
    assert not screen._pairs_empty_lbl.isHidden(), "the empty pairs note went missing"


# ── the records a scan leaves ──────────────────────────────────────


def test_a_scan_writes_a_line_when_it_starts():
    seat_inspector([], [])
    screen = tab()
    taken: list = []
    screen.set_exchange_source(lambda: {"venue": object()}, held_scheduler(taken))
    said = lines_from(lambda: screen._start_fetch(force=True))
    started = [one for one in said if "scan started" in one]
    assert len(started) == 1, said
    assert "forced=True" in started[0], started[0]
    assert "connectors=1" in started[0], started[0]


def test_a_finished_scan_writes_the_market_count_and_the_duration(monkeypatch):
    invented_fetch(monkeypatch, symbol_count=50)
    seat_inspector([scoring_signal()], [])
    screen = tab()
    said = lines_from(
        lambda: asyncio.run(screen._fetch_and_analyze({"venue": object()}))
    )
    finished = [one for one in said if "scan finished" in one]
    assert len(finished) == 1, said
    assert "50 market(s)" in finished[0], finished[0]
    assert "1 signal(s)" in finished[0], finished[0]
    assert "s source=coingecko" in finished[0], finished[0]


def test_a_scan_that_found_nothing_still_writes_a_finish_line(monkeypatch):
    """The scan that scored nothing is the one that used to leave no trace."""
    invented_fetch(monkeypatch, symbol_count=50)
    seat_inspector([], [])
    screen = tab()
    said = lines_from(
        lambda: asyncio.run(screen._fetch_and_analyze({"venue": object()}))
    )
    finished = [one for one in said if "scan finished" in one]
    assert len(finished) == 1, said
    assert "50 market(s)" in finished[0], finished[0]
    assert "0 signal(s)" in finished[0], finished[0]


def test_a_failed_fetch_still_writes_a_finish_line_naming_the_error(monkeypatch):
    invented_fetch(monkeypatch, symbol_count=0, raises=RuntimeError("venue down"))
    seat_inspector([], [])
    screen = tab()
    said = lines_from(
        lambda: asyncio.run(screen._fetch_and_analyze({"venue": object()}))
    )
    finished = [one for one in said if "scan finished" in one]
    assert len(finished) == 1, said
    assert "error=venue down" in finished[0], finished[0]


def test_the_line_recorder_reports_nothing_when_nothing_is_written():
    """POSITIVE CONTROL for `lines_from`: it reports silence and a real line."""
    assert lines_from(lambda: None) == []
    assert lines_from(lambda: shipped.logger.info("a seeded line")) == ["a seeded line"]


# ── the emitters ───────────────────────────────────────────────────


def test_both_scan_topics_are_declared_emitters():
    declared = {one.topic for one in CONTRACTS}
    assert shipped.SCAN_STARTED_TOPIC in declared, sorted(declared)
    assert shipped.SCAN_FINISHED_TOPIC in declared, sorted(declared)


def test_a_scan_puts_a_start_and_a_finish_record_on_the_bus(monkeypatch, own_bus):
    invented_fetch(monkeypatch, symbol_count=50)
    seat_inspector([], [])
    screen = tab()
    screen.set_exchange_source(lambda: {"venue": object()}, held_scheduler([]))
    screen._start_fetch(force=True)
    asyncio.run(screen._fetch_and_analyze({"venue": object()}))
    topics = [one[0] for one in own_bus]
    assert topics == [
        shipped.SCAN_STARTED_TOPIC,
        shipped.SCAN_FINISHED_TOPIC,
    ], own_bus
    finished = own_bus[1][1]
    assert finished["market_count"] == 50, finished
    assert finished["duration_s"] >= 0.0, finished


def test_the_bus_reader_stays_empty_until_a_scan_runs(own_bus):
    """POSITIVE CONTROL: building the tab alone puts nothing on the bus."""
    assert own_bus == []
    tab()
    assert own_bus == [], "building the tab alone emitted a scan record"


def test_the_finish_record_carries_every_field_its_contract_requires(
    monkeypatch, own_bus
):
    invented_fetch(monkeypatch, symbol_count=7)
    seat_inspector([], [])
    screen = tab()
    asyncio.run(screen._fetch_and_analyze({"venue": object()}))
    contract = next(
        one for one in CONTRACTS if one.topic == shipped.SCAN_FINISHED_TOPIC
    )
    payload = own_bus[0][1]
    missing = [name for name in contract.required if name not in payload]
    assert missing == [], missing


# ── the surface answers the same three states ──────────────────────


def test_the_surface_publishes_the_scan_state_and_its_empty_notes():
    model = surface.MarketInspectorScreenModel(
        inspector_source=surface.InspectorSource(signals=[], pairs=[])
    )
    payload = surface.build_view_model(model)
    assert payload["scan_state"] == surface.SCAN_NOT_ASKED
    assert payload["empty_texts"]["signals"] == (
        "No scan yet. Press Refresh to look for markets."
    ), payload["empty_texts"]


def test_the_surface_reports_a_non_empty_view_for_a_scored_market():
    model = surface.MarketInspectorScreenModel(
        inspector_source=surface.InspectorSource(signals=[scoring_signal()], pairs=[])
    )
    model.render_signals()
    payload = surface.build_view_model(model)
    assert payload["signal_rows"], payload["signal_rows"]
    assert payload["signal_rows"][0][0][0] == "BTC", payload["signal_rows"]


def test_the_surface_separates_a_scan_that_ran_from_one_that_never_did():
    model = surface.MarketInspectorScreenModel(
        inspector_source=surface.InspectorSource(signals=[], pairs=[])
    )
    model.render_signals()
    never_ran = surface.build_view_model(model)["empty_texts"]["signals"]
    model.scan_phase = surface.SCAN_FINISHED
    model.render_signals()
    found_nothing = surface.build_view_model(model)["empty_texts"]["signals"]
    assert never_ran != found_nothing, never_ran
