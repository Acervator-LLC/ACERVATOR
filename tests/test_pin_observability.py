"""Every repaired pin can go BOTH WAYS on the real code path.

Queue item 10.4. A pin whose verdict cannot vary is not an observation:
it is decoration that reads as evidence. Three shapes were measured
across the 40-pin network and all three are pinned here.

    ALWAYS PASSES  `actual` and `expected` were the same expression, so
                   `ok` derived True on every call for ever.
    ALWAYS FAILS   the expectation was wrong, so a HEALTHY run reported
                   ok=False on every record - 13, 13, 132 and 154 of
                   154 respectively.
    CANNOT FIRE    `emit_fit` had no caller anywhere in the tree, so
                   `gui.04.001` was dead in the Simulator AND in live.

WHY EVERY CHECK HERE IS DRIVEN TWICE. A repair that only shows the pin
passing is indistinguishable from a silenced alarm. So each repaired
check is driven to a state where it PASSES and to a state where it
FAILS, both through the production call path, and the failing state is
a defect a reader would want to hear about - not a contrived input.

WHY THE FAILING STATES SUBSTITUTE THE TAPE AND NOT THE CONTROLLER. The
defects these pins exist to catch live BELOW the controller: a tape
that serves history the master clock has not reached, a tape that
raises mid-tick, a tape that has a symbol but cannot produce its bar.
The controller's own code runs untouched in every case.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SECTIONS = "fleet.03.003.invariant.sections_imported"
CANDLES = "sim.06.001.postcondition.candles_stepped"
TICKS = "sim.06.002.postcondition.bot_ticks_did_work"
COVERAGE = "ta.07.001.postcondition.coverage_per_bot"
FED = "sim.06.011.postcondition.price_chart.fed"
MODE = "sim.06.013.state_transition.mode_selected"
LOGLINE = "sim.06.014.event.log.line"
FIT = "gui.04.001.postcondition.voting_panel.fit"
YTD_FETCHED = "ytd.10.001.gauge.trades_fetched"
YTD_COVERAGE = "ytd.10.002.postcondition.fleet_symbol_coverage"
YTD_PER_SYMBOL = "ytd.10.003.gauge.per_symbol_counts"

SYMS = ("CHIP/USD", "SPK/USD")
T0 = 1_776_778_500_000
STEP = 300_000


@pytest.fixture
def sink():
    """Collect into a sink of this test's own, and hand it back.

    `FleetReplayController._run` restores the PREVIOUS sink in its
    teardown, so the global sink is gone by the time a controller test
    reads its records. That is why the fixture yields the object rather
    than a getter: the records live on it either way.
    """
    from src.core.signal_contract import SignalSink, set_sink
    s = SignalSink(flush_every=10_000)
    set_sink(s)
    yield s
    set_sink(None)


@pytest.fixture(autouse=True)
def _destroy_widgets():
    """Delete every top-level widget after each test.

    Qt keeps a parentless widget alive for the life of the process, so
    without this the suite accumulates whole panel trees until it dies
    with a segfault and no failure summary. Copied deliberately from
    tests/test_price_chart_feed.py, which is where that was diagnosed.
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in list(app.topLevelWidgets()):
        w.hide()
        w.setParent(None)
        w.deleteLater()
    app.processEvents()


def _qapp():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        pytest.skip("PySide6 unavailable")
    return QApplication.instance() or QApplication([])


def _pump(seconds: float = 0.4) -> None:
    """Run the Qt event loop long enough for a 50 ms timer to fire."""
    app = _qapp()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def _rows(n: int = 400, px0: float = 1.0) -> list[list[float]]:
    """A synthetic tablet: n whole candles on the 5-minute grid."""
    out: list[list[float]] = []
    px = px0
    for i in range(n):
        px *= 1.0 + ((i % 7) - 3) * 0.002
        out.append([T0 + i * STEP, px, px * 1.006, px * 0.994, px, 90.0])
    return out


def _controller(rows: int = 400, max_candles: int | None = 50,
                syms: tuple[str, ...] = SYMS):
    """A built fleet, exactly as tests/test_price_chart_feed.py builds it."""
    _qapp()
    from src.gui.simulator_tab.fleet.fleet_replay_controller import (
        FleetReplayController)
    cfgs = [{"mode": "scrumming", "symbol": s,
             "target_balance": 100.0, "target_asset": s.split("/")[0],
             "base_currency": "USD", "_src_bot_id": f"bot{i:04d}"}
            for i, s in enumerate(syms)]
    ctl = FleetReplayController(
        configs=cfgs,
        candles_by_symbol={s: _rows(rows) for s in syms},
        smart_wires=[], tick_delay_s=0.0, max_candles=max_candles,
        activity_log_cb=lambda *_: None,
        performance_log_cb=lambda *_: None)
    ctl._build_sim()
    return ctl


def _controller_with_a_late_tablet(rows: int = 400,
                                   max_candles: int | None = 120,
                                   late_by: int = 60):
    """A fleet whose SECOND symbol's tablet begins `late_by` candles in.

    Not a tape skin - the DATA starts later, which is the shape the
    controller's own comment records for the real fleet: SPK's first
    candles are 2026-01-01 and CHIP's are 2026-04-21. The bot joins the
    run part-way through, which is a healthy asymmetry and must not
    read as a causality break.
    """
    _qapp()
    from src.gui.simulator_tab.fleet.fleet_replay_controller import (
        FleetReplayController)
    cfgs = [{"mode": "scrumming", "symbol": s,
             "target_balance": 100.0, "target_asset": s.split("/")[0],
             "base_currency": "USD", "_src_bot_id": f"bot{i:04d}"}
            for i, s in enumerate(SYMS)]
    late = [list(r) for r in _rows(rows)]
    for row in late:
        row[0] = int(row[0]) + late_by * STEP
    ctl = FleetReplayController(
        configs=cfgs,
        candles_by_symbol={SYMS[0]: _rows(rows), SYMS[1]: late},
        smart_wires=[], tick_delay_s=0.0, max_candles=max_candles,
        activity_log_cb=lambda *_: None,
        performance_log_cb=lambda *_: None)
    ctl._build_sim()
    return ctl


def _play(ctl, total_candles: int | None = None,
          stop_after: int | None = None) -> None:
    """Play the replay the way `start()` does, minus the durable log.

    `start()` opens a `SimRunLog` under the operator's home directory
    and installs its own sink. Neither is wanted here: this suite must
    write nothing outside the repository, and the fixture's sink is the
    instrument. Everything else - the progress object, the stop event,
    the wall clock - is reproduced exactly, and `_run` itself is the
    production coroutine with the pins in its `finally`.

    `stop_after` raises the SAME flag the Stop button raises.
    `request_stop` sets `progress.stop_requested` and the loop reads it
    at the top of every iteration, so setting it from inside the tape's
    own `step` reproduces a stop arriving mid-run without touching the
    controller.
    """
    from src.gui.simulator_tab.fleet.fleet_replay_controller import (
        ReplayProgress)
    ctl.progress = ReplayProgress(
        total_candles=(ctl._total_candle_count() if total_candles is None
                       else total_candles),
        per_bot_trade_count={str(getattr(b, "bot_id", i)): 0
                             for i, b in enumerate(ctl._bots)})
    ctl.stopped_event.clear()
    ctl.progress.started_at_wall = time.time()
    if stop_after is not None:
        _original_step = ctl._tape.step
        _steps = {"n": 0}

        def _step():
            _steps["n"] += 1
            if _steps["n"] >= stop_after:
                ctl.progress.stop_requested = True
            return _original_step()
        ctl._tape.step = _step
    # RE-INSTALL THE SINK AFTERWARDS, or a second run in one test
    # records nothing. `_run`'s teardown restores `self._prior_sink`,
    # which `start()` records and this harness deliberately never calls
    # - so the first `_run` sets the global sink to None and every
    # emitter in the next one fires into a no-op. Measured: a two-run
    # test read one record and raised IndexError on the second.
    from src.core.signal_contract import get_sink, set_sink
    _held = get_sink()
    try:
        asyncio.run(ctl._run())
    finally:
        set_sink(_held)


class _TapeSkin:
    """Delegate every tape call, so a subclass bends exactly one.

    The controller keeps using its own code; only the object below it
    behaves like the defect under test.
    """

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _CursorRaises(_TapeSkin):
    """`cursor_for` raises once the allowance runs out.

    The window between `bots_ticked += 1` and the worked/throttled/
    unknown classification is where a tick can vanish. This is the only
    call in that window that can raise.
    """

    def __init__(self, inner, allow: int):
        super().__init__(inner)
        self._allow = allow

    def cursor_for(self, symbol):
        if self._allow <= 0:
            msg = "tape cursor unavailable"
            raise RuntimeError(msg)
        self._allow -= 1
        return self._inner.cursor_for(symbol)


class _CursorStuckAtZero(_TapeSkin):
    """`cursor_for` reports 0 while `history` keeps serving rows.

    A tape that serves candles the master clock has not reached. TA is
    observed on those candles while the bot was never eligible for
    them, which is the causality break `ta.07.001` now bounds.

    The allowance is counted PER SYMBOL and has to outlast the first
    replay iteration, because the tick loop evaluates the bots BEFORE
    it steps the tape: on iteration one the real cursor is 0 for every
    symbol and no bot is eligible yet. Two per symbol therefore leaves
    each bot with exactly one eligible candle to be measured against.
    """

    def __init__(self, inner, allow_per_symbol: int = 2):
        super().__init__(inner)
        self._allow = allow_per_symbol
        self._seen: dict[str, int] = {}

    def cursor_for(self, symbol):
        seen = self._seen.get(symbol, 0)
        if seen < self._allow:
            self._seen[symbol] = seen + 1
            return self._inner.cursor_for(symbol)
        return 0


class _CursorBlindForFirstAsks(_TapeSkin):
    """`cursor_for` reports 0 for one symbol's first N asks, then truth.

    A tape whose clock lags for that symbol through the whole observer
    warm-up and then catches up. The bot stays in BOTH maps, so the
    bound is evaluated the same way it always was - and it breaks,
    because observation ran on candles eligibility was withheld for.
    This is the forcing input for the bound itself, kept separate from
    the union repair so the two cannot mask each other.
    """

    def __init__(self, inner, symbol: str, asks: int):
        super().__init__(inner)
        self._symbol = symbol
        self._asks = int(asks)
        self._seen = 0

    def cursor_for(self, symbol):
        if symbol != self._symbol:
            return self._inner.cursor_for(symbol)
        self._seen += 1
        if self._seen <= self._asks:
            return 0
        return self._inner.cursor_for(symbol)


class _CursorBlindForever(_TapeSkin):
    """`cursor_for` reports 0 FOREVER for one symbol; `history` serves.

    THE WORST CASE THE PIN EXISTS TO REPORT. That bot never becomes a
    key in the eligible map at all, while the observer keeps counting
    its candles - so `observed > 0 == eligible`, the maximal violation
    of the bound.

    `_CursorStuckAtZero` above cannot reach this state: it answers
    honestly for its first asks, which puts every bot into the eligible
    map before it starts lying. This one lies from the first ask.
    """

    def __init__(self, inner, symbol: str):
        super().__init__(inner)
        self._symbol = symbol

    def cursor_for(self, symbol):
        if symbol == self._symbol:
            return 0
        return self._inner.cursor_for(symbol)


class _BotWithoutTickCounter:
    """A bot that does not expose `_tick_counter`.

    The controller classifies a tick by reading that private counter
    and says so in its own comment: a bot that does not have it is
    recorded as UNKNOWN rather than silently counted as working. This
    is that bot. Everything else delegates to a real sim bot, so the
    controller runs its own code against real behaviour.
    """

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        if name == "_tick_counter":
            raise AttributeError(name)
        return getattr(self._inner, name)


class _NoBarFor(_TapeSkin):
    """`history` returns nothing for one symbol; `has_data` is honest."""

    def __init__(self, inner, symbol: str, *, has_data: bool):
        super().__init__(inner)
        self._symbol = symbol
        self._has_data = has_data

    def history(self, symbol, count):
        if symbol == self._symbol:
            return []
        return self._inner.history(symbol, count)

    def has_data(self, symbol):
        if symbol == self._symbol:
            return self._has_data
        return self._inner.has_data(symbol)


# THE OPERATOR'S OWN SECTION SET, measured read-only from
# `~/.acervator/bot_state.json` on 2026-08-15: 37 bots, and 37 of 37
# carry these seven sections plus an inner `bot_id` equal to the map
# key. Every value below is synthetic; only the SHAPE is his.
#
# This replaces a config-only fixture. That fixture had been built to
# match the assertion `set(sections) <= {"config"}` rather than to match
# the file the loader reads, so it agreed with a predicate that reported
# ok=False on all 37 live bots and could never have caught it. A fixture
# shaped like the check under test cannot falsify the check.
REAL_SECTIONS = ("config", "phantom_config", "phantoms_enabled",
                 "saved_at", "scrumming_state", "state_when_saved",
                 "stats")


def _real_entry(bot_id: str) -> dict:
    """One bot_state entry with the shape the operator's file has."""
    return {
        "bot_id": bot_id,
        "config": {"mode": "scrumming", "symbol": "BTC/USD",
                   "target_balance": 100.0, "base_currency": "USD"},
        "phantom_config": {},
        "phantoms_enabled": False,
        "saved_at": 1776778500.0,
        "scrumming_state": {"lots": [], "tranches": []},
        "state_when_saved": "RUNNING",
        "stats": {"trades": 0},
    }


def _state(tmp_path: Path, bots: int = 37,
           mutate=None) -> Path:
    """A bot_state.json of `bots` real-shaped scrumming entries.

    `mutate` receives the whole `{bot_id: entry}` map and may bend one
    entry, which is how the failing side of each check is driven.
    """
    entries = {f"bot{i:04d}": _real_entry(f"bot{i:04d}")
               for i in range(bots)}
    if mutate is not None:
        mutate(entries)
    path = tmp_path / "bot_state.json"
    path.write_text(json.dumps({"bots": entries}), encoding="utf-8")
    return path


# ===================================================================== #
# R1  fleet.03.003 - the fields were inverted                           #
# ===================================================================== #


class TestSectionsImportedReportsWhatWasSeen:
    """The pin asserts the loader's OWN carry contract now.

    It used to assert `set(sections_present) <= {"config"}`, against a
    sample of one, and reported ok=False on the operator's real state on
    every load: 37 of 37 of his bots carry seven sections. The assertion
    was true of the v3.23.72 loader and was left behind when v3.24.81
    added the `scrumming_state` and `stats` carries.

    THE SAME INVARIANT, ASSERTED HARDER. "All pieces of the fleet must
    import" is unchanged. What changed is that it is now measured
    against `CARRIED_SECTIONS` - every section the loader is built to
    forward, that the entry supplies, reaches the returned dict - over
    EVERY eligible bot rather than the first one.

    IF ANY OF THESE FAILS: the loader stopped forwarding a section it
    still claims to forward, and a Fleet Replay run would start from a
    fleet missing its lots, its tranches or its grown targets, with no
    record saying so.
    """

    def test_the_operators_real_shape_passes(self, sink, tmp_path):
        """37 bots x 4 carried sections, all landing.

        FAILURE MEANS: the pin cannot go green on his own file, so
        "Load live bots" paints red for ever and the record is noise.
        """
        from src.gui.simulator_tab.fleet.bot_state_loader import (
            load_bot_configs_from_state)
        load_bot_configs_from_state(path=_state(tmp_path, bots=37))
        rec = sink.records(SECTIONS)[0]
        assert rec.ok is True, (
            f"the operator's own section set must pass; ctx={rec.context}")
        assert rec.actual == 37 * 4
        assert rec.expected == 37 * 4
        assert rec.context["bots"] == 37
        assert rec.context["missing_total"] == 0

    def test_a_section_that_does_not_land_fails_and_is_named(
            self, sink, tmp_path):
        """THE FAILING SIDE, and it must not be silent about WHICH.

        A `scrumming_state` that is present but not a dict is skipped by
        the loader's own `isinstance` guard and vanishes. That silent
        drop is what this pin exists to expose.
        """
        from src.gui.simulator_tab.fleet.bot_state_loader import (
            load_bot_configs_from_state)

        def _corrupt(entries):
            entries["bot0011"]["scrumming_state"] = []

        load_bot_configs_from_state(
            path=_state(tmp_path, bots=37, mutate=_corrupt))
        rec = sink.records(SECTIONS)[0]
        assert rec.ok is False, "a section that vanished must not read as a pass"
        assert rec.expected - rec.actual == 1
        assert tuple(rec.context["missing"]) == ("bot0011.scrumming_state",)

    def test_a_stale_source_id_shadows_the_join_and_fails(
            self, sink, tmp_path):
        """`_src_bot_id` is stamped with `setdefault`, so a config that
        already carries one keeps the stale value and every downstream
        join addresses the wrong bot."""
        from src.gui.simulator_tab.fleet.bot_state_loader import (
            load_bot_configs_from_state)

        def _shadow(entries):
            entries["bot0007"]["config"]["_src_bot_id"] = "WRONG"

        load_bot_configs_from_state(
            path=_state(tmp_path, bots=37, mutate=_shadow))
        rec = sink.records(SECTIONS)[0]
        assert rec.ok is False
        assert "bot0007.bot_id" in rec.context["missing"]

    def test_the_observation_is_in_actual(self, sink, tmp_path):
        """FIELD ORIENTATION, read at the surface a reader sees.

        `actual` is what LANDED and `expected` is what was OFFERED. The
        old pin held the constant ["config"] in `actual`, so
        `Signal.message` printed the pair backwards on the one line
        anybody reads during a failure.
        """
        from src.gui.simulator_tab.fleet.bot_state_loader import (
            load_bot_configs_from_state)

        def _corrupt(entries):
            entries["bot0011"]["stats"] = "not-a-dict"

        load_bot_configs_from_state(
            path=_state(tmp_path, bots=37, mutate=_corrupt))
        rec = sink.records(SECTIONS)[0]
        assert rec.actual < rec.expected, (
            "the observation belongs in `actual` and it is the smaller "
            f"of the two here; got actual={rec.actual} expected={rec.expected}")
        line = rec.message()
        assert f"expected={rec.expected}" in line
        assert f"actual={rec.actual}" in line
        assert line.index("expected=") < line.index("actual=")

    def test_the_dropped_sections_are_the_ones_genuinely_dropped(
            self, sink, tmp_path):
        """F3. The old context named `scrumming_state` and `stats` as
        dropped. Both are carried, at `bot_state_loader.py`'s
        `_src_scrumming_state` and `_src_stats`, and have been since
        v3.24.81 - so a reader chased an import bug that was not there.
        """
        from src.gui.simulator_tab.fleet.bot_state_loader import (
            CARRIED_SECTIONS, load_bot_configs_from_state)
        out = load_bot_configs_from_state(path=_state(tmp_path, bots=3))
        rec = sink.records(SECTIONS)[0]
        dropped = set(rec.context["dropped"])
        assert dropped == {"phantom_config", "phantoms_enabled",
                           "saved_at", "state_when_saved"}
        assert not dropped & {"scrumming_state", "stats", "config", "bot_id"}
        assert set(rec.context["carries"]) == set(CARRIED_SECTIONS)
        # and the claim is checked against the PRODUCT, not just the
        # context: the two "dropped" sections really are on the dict.
        assert "_src_scrumming_state" in out[0]
        assert "_src_stats" in out[0]

    def test_it_reports_a_total_import_failure(self, sink, tmp_path):
        """The old guard was `if out and _eligible`, which silenced the
        pin exactly when nothing loaded at all."""
        from src.gui.simulator_tab.fleet import bot_state_loader as _loader
        original = _loader._sections_carried

        def _nothing_landed(entry, _loaded, bot_id):
            """Force the PRODUCT side absent for every bot.

            `_loaded` is deliberately discarded - that is the whole
            substitution - and the underscore says so, because a
            silently unused parameter is indistinguishable from one
            somebody forgot to wire.
            """
            return original(entry, None, bot_id)

        _loader._sections_carried = _nothing_landed
        try:
            _loader.load_bot_configs_from_state(path=_state(tmp_path, bots=5))
        finally:
            _loader._sections_carried = original
        rec = sink.records(SECTIONS)[0]
        assert rec.ok is False
        assert rec.actual == 0
        assert rec.expected == 5 * 4


# ===================================================================== #
# R2  sim.06.001 - expect the tape the run was ASKED to play            #
# ===================================================================== #


class TestCandlesSteppedExpectsWhatWasAsked:
    """`expected` was the whole tape while the loop stops at
    `_max_candles` by design: 13 of 13 recorded runs read FAIL."""

    def test_a_capped_run_passes(self, sink):
        ctl = _controller(rows=400, max_candles=50)
        _play(ctl)
        rec = sink.records(CANDLES)[0]
        assert rec.actual == 50
        assert rec.expected == 50
        assert rec.ok is True, (
            "a run that played every candle it was asked for must pass; "
            f"context={rec.context}")

    def test_the_whole_tape_is_still_recorded(self, sink):
        """The number that used to be `expected` is not lost."""
        ctl = _controller(rows=400, max_candles=50)
        _play(ctl)
        rec = sink.records(CANDLES)[0]
        assert rec.context["total_candles"] == 400
        assert rec.context["max_candles"] == 50

    def test_a_tape_that_under_delivers_fails(self, sink):
        """THE FAILING SIDE. The clock promised 900 ticks and the
        series ran out: `actual` falls under `expected` and the pin
        says so."""
        ctl = _controller(rows=60, max_candles=None)
        _play(ctl, total_candles=900)
        rec = sink.records(CANDLES)[0]
        assert rec.expected == 900
        assert rec.actual < 900
        assert rec.ok is False
        assert rec.context["outcome"] == "ended_before_the_ask"

    def test_a_deliberate_stop_is_not_a_shortfall(self, sink):
        """F2. The operator pressing Stop ended the run at candle 40 of
        an ask of 200, and that was reported ok=False with nothing in
        the record naming the stop.

        IF THIS FAILS: a Stop is indistinguishable from a tape that
        died, so every stopped run reads as a fault and the real faults
        stop being visible among them.
        """
        ctl = _controller(rows=400, max_candles=200)
        _play(ctl, stop_after=40)
        rec = sink.records(CANDLES)[0]
        assert rec.ok is True, (
            f"a deliberate stop is not a shortfall; ctx={rec.context}")
        assert rec.context["outcome"] == "stopped_by_operator"
        assert rec.context["stop_requested"] is True
        assert rec.actual == 40
        assert rec.expected == 200

    def test_a_stop_and_a_broken_tape_are_told_apart(self, sink):
        """Both ended early. The record must not describe them alike."""
        ctl = _controller(rows=400, max_candles=200)
        _play(ctl, stop_after=40)
        stopped = sink.records(CANDLES)[0]
        ctl2 = _controller(rows=60, max_candles=None)
        _play(ctl2, total_candles=900)
        broken = sink.records(CANDLES)[1]
        assert stopped.ok != broken.ok
        assert stopped.context["outcome"] != broken.context["outcome"]
        assert stopped.context["stop_requested"] is True
        assert broken.context["stop_requested"] is False

    def test_the_stop_path_can_still_fail(self, sink):
        """NOT A WIDENING. A stopped run that played MORE than it was
        asked for is an accounting break, and the bound catches it."""
        ctl = _controller(rows=400, max_candles=None)
        _play(ctl, total_candles=10, stop_after=40)
        rec = sink.records(CANDLES)[0]
        assert rec.context["outcome"] == "stopped_by_operator"
        assert rec.actual > rec.expected
        assert rec.ok is False


# ===================================================================== #
# R3  sim.06.002 - every entered tick is accounted for                  #
# ===================================================================== #


class TestBotTicksAreAccountedFor:
    """`expected` was every tick ENTRY while the read-rate throttle
    skips most of them by design: 13 of 13 recorded runs read FAIL."""

    def test_a_healthy_run_accounts_for_every_tick(self, sink):
        """The plain healthy run. On its own this does NOT pin the
        repair: these bots never throttle, so `throttled` and `unknown`
        are both zero and the old expectation coincides with the new
        one. `test_an_unclassifiable_bot_is_still_accounted_for` is the
        one that tells the two apart."""
        ctl = _controller(rows=400, max_candles=60)
        _play(ctl)
        rec = sink.records(TICKS)[0]
        ctx = rec.context
        assert rec.ok is True, f"unaccounted ticks on a healthy run: {ctx}"
        assert rec.actual + ctx["throttled"] + ctx["unknown"] == ctx["entered"]

    def test_an_unclassifiable_bot_is_still_accounted_for(self, sink):
        """A tick the classifier cannot name is still ACCOUNTED FOR.

        The classifier reads a private counter and records a bot that
        does not carry one as UNKNOWN "rather than silently counted as
        working". Under the old expectation every such tick read as a
        failure, because `expected` was every entry. Under the repair
        the run passes and the unknown share stays visible in context.
        """
        ctl = _controller(rows=400, max_candles=60)
        ctl._bots[0] = _BotWithoutTickCounter(ctl._bots[0])
        _play(ctl)
        rec = sink.records(TICKS)[0]
        ctx = rec.context
        assert ctx["unknown"] > 0, f"the unnameable bot never ticked: {ctx}"
        assert rec.ok is True, f"an accounted-for run must pass: {ctx}"
        assert rec.actual + ctx["throttled"] + ctx["unknown"] == ctx["entered"]

    def test_the_throttle_share_is_still_reported(self, sink):
        ctl = _controller(rows=400, max_candles=60)
        _play(ctl)
        rec = sink.records(TICKS)[0]
        assert rec.context["entered"] > 0
        assert 0.0 <= rec.context["worked_pct"] <= 100.0

    def test_a_tick_that_vanishes_mid_window_fails(self, sink):
        """THE FAILING SIDE. An exception raised after the entry count
        and before the classifier leaves ticks unexplained."""
        ctl = _controller(rows=400, max_candles=60)
        ctl._tape = _CursorRaises(ctl._tape, allow=4)
        _play(ctl)
        rec = sink.records(TICKS)[0]
        assert rec.ok is False
        assert rec.expected > rec.actual, (rec.actual, rec.expected)


# ===================================================================== #
# R4  ta.07.001 - the verdict is the bound, not the equality            #
# ===================================================================== #


class TestCoverageIsBounded:
    """Equality between eligible candles and observed candles is false
    for the whole indicator warm-up: 132 of 132 records read FAIL."""

    def test_a_healthy_run_stays_inside_the_bound(self, sink):
        ctl = _controller(rows=400, max_candles=120)
        _play(ctl)
        recs = sink.records(COVERAGE)
        assert recs, "no per-bot coverage was recorded at all"
        for rec in recs:
            assert rec.ok is True, (
                f"{rec.context['bot_id']} observed {rec.actual} of "
                f"{rec.expected} eligible")

    def test_the_coverage_number_is_still_reported(self, sink):
        ctl = _controller(rows=400, max_candles=120)
        _play(ctl)
        rec = sink.records(COVERAGE)[0]
        assert rec.actual < rec.expected, (
            "warm-up means observed is below eligible; if these are "
            "equal the test is no longer measuring the interesting case")
        assert 0.0 < rec.context["pct"] < 100.0

    def test_an_observation_with_no_eligibility_fails(self, sink):
        """THE FAILING SIDE. The tape serves history the master clock
        has not reached, so TA runs on candles the bot was never
        eligible for."""
        ctl = _controller(rows=400, max_candles=120)
        ctl._tape = _CursorStuckAtZero(ctl._tape, allow_per_symbol=2)
        _play(ctl)
        recs = sink.records(COVERAGE)
        assert recs, "the eligibility map was empty, so nothing was judged"
        assert any(r.ok is False for r in recs), [
            (r.actual, r.expected) for r in recs]

    def test_a_cursor_blind_for_110_asks_still_breaks_the_bound(
            self, sink):
        """THE BOUND ITSELF, still forceable after the union repair.

        A bot that stays in BOTH maps and observes far more candles
        than it was ever eligible for. Nothing about walking the union
        touches this path, and this test is here to prove that: if it
        fails, the repair widened the verdict instead of widening the
        record set.
        """
        ctl = _controller(rows=400, max_candles=120)
        ctl._tape = _CursorBlindForFirstAsks(ctl._tape, SYMS[0], 110)
        _play(ctl)
        bad = [r for r in sink.records(COVERAGE) if r.ok is False]
        assert bad, [(r.context["bot_id"], r.actual, r.expected)
                     for r in sink.records(COVERAGE)]
        rec = bad[0]
        assert rec.actual > rec.expected, (rec.actual, rec.expected)
        assert rec.expected > 0, (
            "this input must break the bound WITH eligibility present; "
            "a zero here means it collapsed into the union case and is "
            "no longer an independent control")
        assert rec.context["state"] == "eligible_and_observed"


# ===================================================================== #
# R4b ta.07.001 - the pin must be able to report its own WORST case     #
# ===================================================================== #


class TestCoverageWalksTheUnion:
    """The loop read `_ta_eligible` alone.

    A bot with observations and ZERO eligibility is not a key in that
    map, so the MAXIMAL violation of the bound - the one state the
    pin's own comment says cannot happen in a sound run - produced no
    record at all. Measured on this coroutine before the repair: 120
    candles, one symbol's cursor pinned at 0, eligible
    {bot0001: 119}, observed {bot0000: 70, bot0001: 70}, ONE record,
    ok=True. A green run with a causality break live inside it.

    Every test below is driven above the 51-row observer guard. At 50
    candles `_observe_ta` returns early for every bot and the observed
    map is empty, so the state cannot be reached and a control there
    measures the harness rather than the code.
    """

    def test_the_worst_case_emits_a_record_and_it_is_red(self, sink):
        """THE REPAIR.

        If this fails, TA ran on candles the master clock never reached
        for that bot and the pin said nothing about it - the run reads
        green while the tape is serving the future.
        """
        ctl = _controller(rows=400, max_candles=120)
        ctl._tape = _CursorBlindForever(ctl._tape, SYMS[0])
        _play(ctl)
        recs = {r.context["bot_id"]: r for r in sink.records(COVERAGE)}
        blind = ctl._bots[0].bot_id
        assert blind not in ctl._ta_eligible, (
            "the skin did not reach the state under test: this bot must "
            "have NO eligibility at all")
        assert ctl._ta_observed.get(blind, 0) > 0, (
            "the observer never ran, so there is no violation to report; "
            "check the tape is above the 51-row guard")
        assert blind in recs, (
            f"{blind} observed {ctl._ta_observed.get(blind)} candles "
            f"against eligibility 0 and emitted NOTHING")
        rec = recs[blind]
        assert rec.expected == 0
        assert rec.actual > 0
        assert rec.ok is False, (rec.actual, rec.expected)
        assert rec.context["state"] == "observed_without_eligibility"

    def test_no_percentage_is_invented_without_a_denominator(self, sink):
        """`pct` is None where eligibility is 0, never 0.0.

        If this fails, the single record that matters most reports zero
        coverage for a bot that observed every candle it could.
        """
        ctl = _controller(rows=400, max_candles=120)
        ctl._tape = _CursorBlindForever(ctl._tape, SYMS[0])
        _play(ctl)
        rec = [r for r in sink.records(COVERAGE)
               if r.expected == 0][0]
        assert rec.context["pct"] is None, rec.context["pct"]

    def test_the_record_count_reconciles_on_a_healthy_run(self, sink):
        """THE IDENTITY: records == len(set(eligible) | set(observed)).

        If this fails, a bot one of the two maps knows about carries no
        verdict, and the log cannot be reconciled against the run.
        """
        ctl = _controller(rows=400, max_candles=120)
        _play(ctl)
        recs = sink.records(COVERAGE)
        union = set(ctl._ta_eligible) | set(ctl._ta_observed)
        assert len(recs) == len(union), (
            sorted(union), [r.context["bot_id"] for r in recs])
        assert {r.context["bot_id"] for r in recs} == union
        for rec in recs:
            assert rec.context["bots_in_union"] == len(union)

    def test_the_record_count_reconciles_on_a_broken_run(self, sink):
        """THE SAME IDENTITY where it used to break.

        This is the run that produced one record for two known bots.
        """
        ctl = _controller(rows=400, max_candles=120)
        ctl._tape = _CursorBlindForever(ctl._tape, SYMS[0])
        _play(ctl)
        recs = sink.records(COVERAGE)
        union = set(ctl._ta_eligible) | set(ctl._ta_observed)
        assert len(union) == 2, sorted(union)
        assert len(recs) == len(union), (
            sorted(union), [r.context["bot_id"] for r in recs])
        assert {r.context["bot_id"] for r in recs} == union

    def test_a_bot_in_neither_map_gets_no_verdict_but_is_counted(
            self, sink):
        """STATE 4, and the union must NOT manufacture a row for it.

        A bot that never ticked with tape has nothing to bound, so
        `0 <= 0, ok=True` would be decoration reading as evidence. It
        is counted instead, so the fleet total stays accountable.

        If this fails, either a verdict was invented for a bot with no
        bound, or a bot vanished from the accounting entirely.
        """
        ctl = _controller(rows=400, max_candles=120)
        ctl._tape = _NoBarFor(ctl._tape, SYMS[0], has_data=False)
        _play(ctl)
        recs = sink.records(COVERAGE)
        absent = ctl._bots[0].bot_id
        assert absent not in ctl._ta_eligible
        assert absent not in ctl._ta_observed
        assert absent not in {r.context["bot_id"] for r in recs}
        assert len(recs) == 1, [r.context["bot_id"] for r in recs]
        assert recs[0].context["fleet_bots_with_no_record"] == 1
        assert (recs[0].context["bots_in_union"]
                + recs[0].context["fleet_bots_with_no_record"]
                == len(ctl._bots))

    def test_the_warm_up_is_green_and_says_which_state_it_is(self, sink):
        """STATE 2. Eligible from cursor 1, observable only from 50.

        Every bot spends its first 49 eligible candles here on every
        run. If this fails the pin cries wolf on healthy warm-up, which
        is the 132-of-132 false red 10.4 removed.
        """
        ctl = _controller(rows=400, max_candles=50)
        _play(ctl)
        recs = sink.records(COVERAGE)
        assert ctl._ta_observed == {}, (
            "the observer ran, so this is no longer the warm-up state")
        assert len(recs) == len(ctl._ta_eligible) == 2
        for rec in recs:
            assert rec.actual == 0
            assert rec.expected > 0
            assert rec.ok is True
            assert rec.context["state"] == "eligible_not_yet_observed"
            assert rec.context["pct"] == 0.0

    def test_a_tablet_that_starts_mid_window_is_not_a_violation(
            self, sink):
        """A LATE JOIN, from the DATA and not from a tape skin.

        If this fails, a symbol whose tablet begins after the master
        clock reads as a causality break, and the operator's real fleet
        - whose tablets start months apart - would be red every run.
        """
        ctl = _controller_with_a_late_tablet(rows=400, max_candles=120,
                                             late_by=60)
        _play(ctl)
        recs = sorted(sink.records(COVERAGE),
                      key=lambda r: r.context["bot_id"])
        assert len(recs) == 2, [r.context["bot_id"] for r in recs]
        early, late = recs
        assert late.expected < early.expected, (
            early.expected, late.expected)
        assert late.expected < 119, (
            "the second tablet did not start late; this test is not "
            "measuring a late join")
        for rec in recs:
            assert rec.ok is True, (rec.context["bot_id"], rec.actual,
                                    rec.expected)
            assert rec.context["state"] == "eligible_and_observed"


# ===================================================================== #
# R5  sim.06.011 - expect what the TAPE can feed, not the bot count     #
# ===================================================================== #


def _panel_with_run(rows: int = 400):
    """A panel wired to a controller mid-replay, as the GUI has it."""
    _qapp()
    from src.gui.simulator_tab.fleet.fleet_replay_panel import (
        FleetReplayPanel)
    ctl = _controller(rows=rows, max_candles=50)
    for _ in range(120):
        ctl._tape.step()
    panel = FleetReplayPanel()
    panel._controller = ctl
    return panel, ctl


def _drain_once(panel) -> None:
    """Collect on the worker side and apply on the GUI side."""
    panel._pending_snapshot = panel._collect_visual_snapshot()
    panel._drain_visual_snapshot()


class _LegacySeries:
    """A `get_current`-shaped series: the pre-TabletBackend feed."""

    def __init__(self, row):
        self._row = row

    def get_current(self):
        return self._row


class _LegacyHost:
    """A controller handing in a series-shaped exchange and no tape.

    `_collect_visual_snapshot` keeps that branch "for any host still
    handing in a series-shaped exchange", and reads the controller by
    getattr alone - so this shape IS that host. Without the repair the
    branch never sets `tape_has_data`, `expected` is 0 for every
    symbol, and the pin fails a run that fed the chart correctly.
    """

    def __init__(self, bots, series):
        self._bots = bots
        self._tape = None
        self._exchange = _LegacyExchange(series)

    def drain_markers(self):
        return []


class _LegacyExchange:
    """An exchange carrying `_series`, keyed by symbol."""

    def __init__(self, series):
        self._series = series


class TestTheChartFeedExpectsWhatTheTapeCanGive:
    """`expected` counted BOTS. A symbol whose tablet starts after the
    master clock has no candle to give and was counted as a miss: 154
    of 154 records read FAIL."""

    def test_a_fed_chart_passes(self, sink):
        panel, _ctl = _panel_with_run()
        _drain_once(panel)
        rec = sink.records(FED)[0]
        assert rec.actual == 2
        assert rec.expected == 2
        assert rec.ok is True

    def test_a_symbol_the_tape_cannot_serve_is_not_a_miss(self, sink):
        """THE REPAIR, AND THE CONTROL FOR IT. Under the old code
        `expected` was 2 here - the bot count - and the pin failed a
        correct run."""
        panel, ctl = _panel_with_run()
        ctl._tape = _NoBarFor(ctl._tape, SYMS[1], has_data=False)
        _drain_once(panel)
        rec = sink.records(FED)[0]
        assert rec.expected == 1, (
            "`expected` must be what the TAPE can feed; the bot count "
            "is 2 here and was what the old code reported")
        assert rec.actual == 1
        assert rec.ok is True
        assert rec.context["symbols"] == 2, "both bots are still counted"

    def test_a_symbol_the_tape_has_but_cannot_feed_fails(self, sink):
        """THE FAILING SIDE, and the regression this pin was written
        for: the tape holds the symbol and the feed produces no bar."""
        panel, ctl = _panel_with_run()
        ctl._tape = _NoBarFor(ctl._tape, SYMS[1], has_data=True)
        _drain_once(panel)
        rec = sink.records(FED)[0]
        assert rec.expected == 2
        assert rec.actual == 1
        assert rec.ok is False


class TestTheChartFeedOnALegacyHost:
    """The legacy series-shaped path has to carry the same expectation.

    It is unreachable in this tree - `_build_sim` creates the tape
    before it creates any bot, so `per_symbol` is empty whenever
    `_tape` is None - but the branch is kept deliberately for a host
    that supplies one, and a branch that reports every symbol as a miss
    would put back the defect this unit removed.
    """

    def _panel(self, served):
        panel, ctl = _panel_with_run()
        row = [T0, 1.0, 1.1, 0.9, 1.0, 5.0]
        panel._controller = _LegacyHost(
            ctl._bots, {s: _LegacySeries(row) for s in served})
        return panel

    def test_a_fully_served_legacy_host_passes(self, sink):
        panel = self._panel(SYMS)
        _drain_once(panel)
        rec = sink.records(FED)[0]
        assert rec.expected == 2
        assert rec.actual == 2
        assert rec.ok is True

    def test_a_partly_served_legacy_host_still_passes(self, sink):
        """THE DISCRIMINATING CASE. One symbol has no series, so the
        feed can only produce one candle and that is correct. Without
        the repair `expected` is 0 here against an `actual` of 1."""
        panel = self._panel(SYMS[:1])
        _drain_once(panel)
        rec = sink.records(FED)[0]
        assert rec.expected == 1
        assert rec.actual == 1
        assert rec.ok is True
        assert rec.context["symbols"] == 2


# ===================================================================== #
# R6  sim.06.013 - read the transition back off the widget              #
# ===================================================================== #


def _tab():
    _qapp()
    from src.gui.simulator_tab.simulator_tab import SimulatorTab
    return SimulatorTab()


def _select_mode(tab, key: str) -> None:
    """Drive the mode the way the operator does - through the combo."""
    sel = tab._mode_selector
    index = sel.findData(key)
    assert index >= 0, f"no {key!r} entry in the mode selector"
    sel.setCurrentIndex(index)


class TestModeSelectedReadsTheStackBack:
    """`actual` and `expected` were both the mode key, so `ok` derived
    True however the stack behaved."""

    def test_the_default_mode_passes(self, sink):
        tab = _tab()
        tab._on_sim_mode_changed()
        rec = sink.records(MODE)[-1]
        assert rec.actual == 0
        assert rec.expected == 0
        assert rec.ok is True
        assert rec.context["mode"] == "validation"

    def test_nuclear_moves_the_page(self, sink):
        tab = _tab()
        _select_mode(tab, "nuclear")
        rec = sink.records(MODE)[-1]
        assert rec.expected == 1
        assert rec.actual == 1
        assert rec.ok is True

    def test_a_stack_that_refuses_the_change_fails(self, sink):
        """THE FAILING SIDE. Qt treats an out-of-range
        `setCurrentIndex` as a silent no-op, and the mode hand-off
        swallows its own exception, so a refused transition was
        invisible twice over."""
        from PySide6.QtWidgets import QStackedWidget, QWidget
        tab = _tab()
        one_page = QStackedWidget()
        one_page.addWidget(QWidget())
        tab._stack = one_page
        _select_mode(tab, "nuclear")
        rec = sink.records(MODE)[-1]
        assert rec.expected == 1
        assert rec.actual == 0
        assert rec.ok is False


# ===================================================================== #
# R7  sim.06.014 - a sample, because no expectation exists here         #
# ===================================================================== #


class TestTheLogLineIsASample:
    """`actual` and `expected` were both the stream name. There is no
    independent expectation at this point and inventing one would be
    worse: `delivered` varies only because the operator paused a pane,
    so expecting it True would paint the pin red on a button press."""

    def test_it_carries_no_vacuous_verdict(self, sink):
        tab = _tab()
        tab.log_activity("fleet loaded")
        rec = sink.records(LOGLINE)[0]
        assert rec.kind == "sample"
        assert rec.ok is None
        assert rec.expected is None

    def test_the_stream_identity_still_survives(self, sink):
        """The property the pin exists for: one widget receiving
        everything looks identical to one receiving a stream twice."""
        tab = _tab()
        tab.log_activity("a1")
        tab.log_performance("p1")
        tab.log_activity("a2")
        assert [r.actual for r in sink.records(LOGLINE)] == [
            "activity", "performance", "activity"]

    def test_a_paused_pane_is_still_recorded(self, sink):
        tab = _tab()
        tab._activity_paused = True
        tab.log_activity("suppressed")
        rec = sink.records(LOGLINE)[0]
        assert rec.context["delivered"] is False
        assert rec.ok is None, (
            "a paused pane is an operator action, not a failure")


# ===================================================================== #
# R8  gui.04.001 - the pin had no caller anywhere in the tree           #
# ===================================================================== #


def _voting_panel(width: int, height: int):
    _qapp()
    from src.gui.indicator_panel import IndicatorVotingPanel
    panel = IndicatorVotingPanel()
    panel.resize(width, height)
    panel.show()
    _pump()
    return panel


def _fit_record(sink, where: str, panel, timeout: float = 5.0):
    """The fit record describing the panel's CURRENT geometry.

    NOT the newest record. One `resize()` produces more than one: Qt
    sends intermediate resize events and each schedules its own
    deferred emit, so `records()[-1]` is a race. Measured on a squeeze
    to 120px, which the panel clamps to its 360px minimum: `resize
    actual=17 expected=17 ok=True` landed first and `resize actual=16
    expected=17 ok=False` second. Reading by position passed alone and
    failed inside the whole suite.

    So the record is selected by agreeing with a live
    `header_fit_report` - the property the pin asserts - and waited for
    with a deadline rather than a fixed pump.
    """
    app = _qapp()
    end = time.monotonic() + timeout
    while True:
        report = panel.header_fit_report()
        cols = sum(v["columns"] for v in report.values())
        bad = sum(len(v["truncated"]) for v in report.values())
        for rec in reversed(sink.records(FIT)):
            if ((rec.context or {}).get("where") == where
                    and rec.expected == cols
                    and rec.actual == cols - bad):
                return rec
        if time.monotonic() >= end:
            seen = [((r.context or {}).get("where"), r.actual, r.expected)
                    for r in sink.records(FIT)]
            msg = (f"no {where!r} fit record for the current geometry "
                   f"(cols={cols}, fitting={cols - bad}, "
                   f"width={panel.width()}); saw {seen}")
            raise AssertionError(msg)
        app.processEvents()
        time.sleep(0.005)


class TestTheVotingPanelFitPinFires:
    """An AST walk over 520 files found 0 calls, 0 attribute references
    and 0 string references to `emit_fit`, against controls of 7, 7 and
    2 on neighbouring methods. The measurement was adopted; the emitter
    was not."""

    def test_showing_the_panel_fires_the_pin(self, sink):
        panel = _voting_panel(900, 460)
        assert panel is not None
        recs = sink.records(FIT)
        assert recs, "the fit pin still has no caller"
        assert any(r.context["where"] == "show" for r in recs), [
            r.context["where"] for r in recs]

    def test_a_panel_with_room_passes(self, sink):
        panel = _voting_panel(900, 460)
        rec = _fit_record(sink, "show", panel)
        assert rec.expected > 0, "no columns were measured at all"
        assert rec.actual == rec.expected
        assert rec.ok is True

    def test_a_squeezed_panel_fails_and_names_the_columns(self, sink):
        """THE FAILING SIDE. This is the "omp N" in the operator's
        screenshot: the columns want more width than the viewport has.

        The overflow is forced with a header LABEL rather than with
        width alone. The panel clamps a 120px request to its own 360px
        minimum, and at 360 exactly one column overflowed by FOUR
        pixels - thin enough for another module's style, installed on
        the QApplication this suite shares, to flip it. A label this
        wide cannot fit at any width the panel can take.
        """
        from PySide6.QtWidgets import QTableWidget
        panel = _voting_panel(900, 460)
        table = panel.findChildren(QTableWidget)[0]
        table.horizontalHeaderItem(0).setText("W" * 60)
        panel.resize(120, 460)
        _pump()
        rec = _fit_record(sink, "resize", panel)
        assert rec.context["where"] == "resize"
        assert rec.actual < rec.expected, (
            f"the squeeze truncated nothing at width {panel.width()}, so "
            f"this is not measuring the failing side")
        assert rec.ok is False
        assert any(v for v in rec.context["detail"].values()), rec.context


# ===================================================================== #
# R9  ytd.10.001-003 - reachable, and the excuse was the harness's      #
# ===================================================================== #


class _StubBotManager:
    """A BotManager with no bots.

    `history_helpers._pairs_from_bot_manager` returns nothing for it, so
    `fetch_all_history_chunked` returns [] without an exchange call. The
    point of the test is REACHABILITY, and an empty fetch reaches the
    pins by the same path a full one does.
    """

    def __init__(self):
        self.bots: list = []


class TestTheYtdPinsAreReachableInTheSimulator:
    """The 10.4 audit classified these three CANNOT-FIRE-HERE because
    "a Simulator run has neither a live BotManager nor an exchange".

    That was a property of the HARNESS, not of the Simulator. The
    operator's own application injects the manager through a plain
    setter at src/gui/main_window.py, and this test performs the same
    injection. A "cannot fire here" verdict has to be a measurement.
    """

    def test_the_injection_the_main_window_performs_reaches_the_panel(self):
        tab = _tab()
        assert hasattr(tab, "set_bot_manager"), (
            "main_window.py calls set_bot_manager on the Simulator tab")
        tab.set_bot_manager(_StubBotManager())
        assert tab.fleet_replay._bot_manager is not None
        assert tab.fleet_replay._fetch_ytd_btn.isEnabled()

    def test_all_three_pins_fire_offscreen_with_no_exchange(self, sink):
        """THE MEASUREMENT THAT REPLACES THE EXCUSE."""
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        try:
            tab = _tab()
            tab.set_bot_manager(_StubBotManager())
            panel = tab.fleet_replay
            panel._configs = [{"symbol": "BTC/USD"}, {"symbol": "ETH/USD"}]
            panel._async_loop_getter = lambda: loop
            panel._on_fetch_ytd_clicked()
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if sink.count(YTD_PER_SYMBOL):
                    break
                _qapp().processEvents()
                time.sleep(0.01)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5.0)
            loop.close()
        for name in (YTD_FETCHED, YTD_COVERAGE, YTD_PER_SYMBOL):
            assert sink.count(name) == 1, f"{name} did not fire"

    def test_an_empty_fetch_is_a_verdict_not_a_silence(self, sink):
        """`ytd.10.002` becomes a live verdict the moment it is
        reachable: no trades means no reference to diff a bot against,
        and the record says which symbols are uncovered."""
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        try:
            tab = _tab()
            tab.set_bot_manager(_StubBotManager())
            panel = tab.fleet_replay
            panel._configs = [{"symbol": "BTC/USD"}]
            panel._async_loop_getter = lambda: loop
            panel._on_fetch_ytd_clicked()
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline:
                if sink.count(YTD_COVERAGE):
                    break
                _qapp().processEvents()
                time.sleep(0.01)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5.0)
            loop.close()
        rec = sink.records(YTD_COVERAGE)[0]
        assert rec.ok is False
        assert rec.actual == ()
        assert rec.expected == ("BTC/USD",)
        assert set(rec.context["uncovered"]) == {"BTC/USD"}
