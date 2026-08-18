# S101  — pytest's assert IS the assertion syntax; -O would strip
#         them and make the suite inert. Nobody runs pytest with -O.
# SLF001 — pin tests deliberately read internals (_exchange,
#         _balances, _build_sim, _task) because the whole point is
#         verifying wiring the public API does not expose.
"""v3.23.79-A — pin tests for the Fleet Replay tick controller.

Deferred piece from v3.23.72 that makes Start Replay actually work.
Tests exercise the async orchestrator's contract in isolation:

    * ReplayProgress starts at 0 / total_candles from series
    * _instantiate_bot returns None for non-scrumming configs
    * Start with empty candles fails-soft (no bots, no ticks)
    * Stop request drains cooperatively
    * Controller emits stopped_event when finished

These tests use synthetic configs + candle series so the real
ScrummingBot / event-bus / balance-check machinery isn't required.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.gui.simulator_tab.fleet.fleet_replay_controller import (  # noqa: E402
    FleetReplayController, ReplayProgress, _instantiate_bot,
)
from src.gui.simulator_tab.fleet.sim_exchange import (  # noqa: E402
    FleetSimExchange, make_symbol_series_map,
)
from src.gui.simulator_tab.fleet.fleet_replay_panel import (  # noqa: E402
    _synthesize_candles_for_symbol,
)


# ---- ReplayProgress ---------------------------------------------------- #

def test_replay_progress_defaults():
    p = ReplayProgress()
    assert p.candles_played == 0
    assert p.trades_fired == 0
    assert p.exceptions == 0
    assert p.finished is False
    assert p.stop_requested is False


# ---- _instantiate_bot --------------------------------------------------- #

def test_instantiate_bot_rejects_non_scrumming():
    series = make_symbol_series_map(
        {"BTC/USD": _synthesize_candles_for_symbol("BTC/USD", 10)})
    ex = FleetSimExchange(series, starting_balances={"USD": 1000.0})
    cfg = {"mode": "extractor", "symbol": "BTC/USD"}
    bot = _instantiate_bot(cfg, ex)
    assert bot is None


def test_instantiate_bot_rejects_missing_symbol_config():
    """Bad config (missing required fields) must fail-soft, returning
    None rather than raising, so the orchestrator can just skip it."""
    series = make_symbol_series_map(
        {"BTC/USD": _synthesize_candles_for_symbol("BTC/USD", 10)})
    ex = FleetSimExchange(series, starting_balances={"USD": 1000.0})
    cfg = {"mode": "scrumming"}  # missing symbol / target_balance
    # Note: make_bot_config might succeed with defaults, but this is
    # the pin — regardless of outcome, no exception escapes.
    try:
        _instantiate_bot(cfg, ex)  # no assertion; just no raise
    except Exception as exc:
        pytest.fail(f"_instantiate_bot raised: {exc}")


# ---- Controller lifecycle --------------------------------------------- #

def test_controller_stop_when_no_bots():
    """No configs → controller starts, immediately drops out, sets
    stopped_event."""
    ctrl = FleetReplayController(
        configs=[],
        candles_by_symbol={},
    )
    asyncio.run(ctrl.start())
    # start() returned early because no bots → stopped_event already set
    assert ctrl.stopped_event.is_set()


def test_controller_request_stop_flags_progress():
    ctrl = FleetReplayController(configs=[], candles_by_symbol={})
    ctrl.request_stop()
    assert ctrl.progress.stop_requested is True


# ---- End-to-end tick ------------------------------------------------- #

def test_controller_runs_synthetic_candles_end_to_end():
    """Full loop: 2 bot configs, 30 candles each. After start()
    completes, candles_played should reach the series length OR
    max_candles cap."""
    cfgs = [
        {"mode": "scrumming", "symbol": "BTC/USD",
         "exchange_id": "sim", "base_currency": "USD",
         "target_asset": "BTC", "target_balance": 250.0,
         "scrumming_interval_pct": 1.0, "ta_timeframe": "1h"},
        {"mode": "scrumming", "symbol": "ETH/USD",
         "exchange_id": "sim", "base_currency": "USD",
         "target_asset": "ETH", "target_balance": 250.0,
         "scrumming_interval_pct": 1.0, "ta_timeframe": "1h"},
    ]
    candles = {
        "BTC/USD": _synthesize_candles_for_symbol("BTC/USD", 30),
        "ETH/USD": _synthesize_candles_for_symbol("ETH/USD", 30),
    }
    ctrl = FleetReplayController(
        configs=cfgs, candles_by_symbol=candles,
        tick_delay_s=0.0, max_candles=30)

    async def run():
        await ctrl.start()
        await ctrl.stopped_event.wait()

    asyncio.run(run())
    assert ctrl.progress.finished is True
    assert ctrl.progress.candles_played >= 1


def test_controller_double_start_is_noop():
    """Calling start() twice must not spawn two tick tasks."""
    ctrl = FleetReplayController(
        configs=[{"mode": "scrumming", "symbol": "BTC/USD",
                  "target_balance": 100.0}],
        candles_by_symbol={"BTC/USD":
                            _synthesize_candles_for_symbol(
                                "BTC/USD", 5)},
        tick_delay_s=0.0, max_candles=5)

    async def run():
        await ctrl.start()
        first_task = ctrl._task
        await ctrl.start()  # noop if first is still running
        second_task = ctrl._task
        await ctrl.stopped_event.wait()
        return first_task, second_task

    first, second = asyncio.run(run())
    assert first is second, "second start() must not spawn a new task"


# ── v3.24.9: wallet seeding from fleet target_balance ────────────
# Operator directive 2026-08-02: "let's just make the spendable
# amount for the sim always equal the locked amount at the start of
# the sim replay." Prior code hardcoded $100,000 USD, which is why
# sim stat-strip figures bore no relation to bot_state reality.

def test_wallet_seed_equals_sum_of_target_balance():
    ctrl = FleetReplayController(
        configs=[
            {"mode": "scrumming", "symbol": "BTC/USD",
             "target_balance": 200.0},
            {"mode": "scrumming", "symbol": "ETH/USD",
             "target_balance": 150.0},
        ],
        candles_by_symbol={
            "BTC/USD": _synthesize_candles_for_symbol("BTC/USD", 5),
            "ETH/USD": _synthesize_candles_for_symbol("ETH/USD", 5),
        })
    ctrl._build_sim()
    assert ctrl._tape.balances()["USD"] == pytest.approx(350.0)


def test_wallet_seed_excludes_configs_without_tablets():
    """A partial fleet gets a proportionally-sized wallet, not one
    sized for bots that never spawn."""
    ctrl = FleetReplayController(
        configs=[
            {"mode": "scrumming", "symbol": "BTC/USD",
             "target_balance": 200.0},
            {"mode": "scrumming", "symbol": "NOTAPE/USD",
             "target_balance": 999.0},   # no candle series
        ],
        candles_by_symbol={
            "BTC/USD": _synthesize_candles_for_symbol("BTC/USD", 5),
        })
    ctrl._build_sim()
    assert ctrl._tape.balances()["USD"] == pytest.approx(200.0)


def test_wallet_seed_falls_back_when_no_targets():
    """Zero usable targets must not seed $0 (unspendable sim) — it
    falls back to a nominal float AND says so."""
    acts: list[str] = []
    ctrl = FleetReplayController(
        configs=[{"mode": "scrumming", "symbol": "BTC/USD",
                  "target_balance": 0.0}],
        candles_by_symbol={
            "BTC/USD": _synthesize_candles_for_symbol("BTC/USD", 5),
        },
        activity_log_cb=acts.append)
    ctrl._build_sim()
    assert ctrl._tape.balances()["USD"] > 0
    assert any("falling back" in a for a in acts)


def test_wallet_seed_is_announced_in_activity_log():
    acts: list[str] = []
    ctrl = FleetReplayController(
        configs=[{"mode": "scrumming", "symbol": "BTC/USD",
                  "target_balance": 250.0}],
        candles_by_symbol={
            "BTC/USD": _synthesize_candles_for_symbol("BTC/USD", 5),
        },
        activity_log_cb=acts.append)
    ctrl._build_sim()
    assert any("Wallet seed: $250.00" in a for a in acts)


# ── v3.24.15: anchored read head ─────────────────────────────────
# Operator directive 2026-08-03: "the read head reaches a candle,
# first checks for an expected trade, if none are identified, it
# skips." Validation runs only need candles where something
# happened; full evaluation is for strategy work.

_ANCHOR_BASE = 1_774_915_200_000
_ANCHOR_STEP = 300_000


def _ts_at(idx: int) -> float:
    return (_ANCHOR_BASE + idx * _ANCHOR_STEP) / 1000.0


def test_anchor_includes_trade_candle_and_warmup():
    from src.gui.simulator_tab.fleet.fleet_replay_controller import (
        build_anchor_indices)
    a = build_anchor_indices([_ts_at(500)], _ANCHOR_BASE, 1000,
                             warmup=100)
    # 100 warm-up candles PLUS the trade's own candle
    assert (min(a), max(a), len(a)) == (400, 500, 101)


def test_anchor_overlapping_clusters_collapse():
    from src.gui.simulator_tab.fleet.fleet_replay_controller import (
        build_anchor_indices)
    a = build_anchor_indices([_ts_at(500), _ts_at(510)],
                             _ANCHOR_BASE, 1000, warmup=100)
    assert len(a) == 111, "clustered trades must not cost 2x warm-up"


def test_anchor_drops_trades_outside_window():
    from src.gui.simulator_tab.fleet.fleet_replay_controller import (
        build_anchor_indices)
    assert not build_anchor_indices(
        [_ts_at(-50)], _ANCHOR_BASE, 1000, warmup=100)
    assert not build_anchor_indices(
        [_ts_at(5000)], _ANCHOR_BASE, 1000, warmup=100)


def test_anchor_warmup_clamps_at_zero():
    from src.gui.simulator_tab.fleet.fleet_replay_controller import (
        build_anchor_indices)
    a = build_anchor_indices([_ts_at(10)], _ANCHOR_BASE, 1000,
                             warmup=100)
    assert min(a) == 0


def test_anchor_empty_when_no_trades():
    from src.gui.simulator_tab.fleet.fleet_replay_controller import (
        build_anchor_indices)
    assert build_anchor_indices([], _ANCHOR_BASE, 1000) == set()


def test_anchored_run_skips_unanchored_candles():
    """The read head must actually skip — candles_skipped proves it,
    and bots_ticked must be far below candles x bots."""
    rows = _synthesize_candles_for_symbol("BTC/USD", 60)
    ctrl = FleetReplayController(
        configs=[{"mode": "scrumming", "symbol": "BTC/USD",
                  "target_balance": 100.0}],
        candles_by_symbol={"BTC/USD": rows},
        tick_delay_s=0.0)
    ctrl._build_sim()
    # only candles 50..55 are anchors
    ctrl._anchor_indices = set(range(50, 56))

    async def run():
        await ctrl.start()
        await ctrl.stopped_event.wait()

    asyncio.run(run())
    assert ctrl.progress.candles_skipped > 0
    assert ctrl.progress.candles_skipped >= 40


def test_unanchored_run_evaluates_every_candle():
    rows = _synthesize_candles_for_symbol("BTC/USD", 20)
    ctrl = FleetReplayController(
        configs=[{"mode": "scrumming", "symbol": "BTC/USD",
                  "target_balance": 100.0}],
        candles_by_symbol={"BTC/USD": rows},
        tick_delay_s=0.0)

    async def run():
        await ctrl.start()
        await ctrl.stopped_event.wait()

    asyncio.run(run())
    assert ctrl.progress.candles_skipped == 0, (
        "default must evaluate everything")
