"""The Qt Fleet Replay panel and the Qt-free surface, driven side by side.

A failure means the view model describes a different control, a different
column, a different number format, a different status line, a different
log line, a different pin or a different branch than ``FleetReplayPanel``
takes on the same input.

Nothing here starts a replay. The panel hands its run to the
application's loop, and that hand-off is stood in for on both sides.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.exchange.history_helpers import DEFAULT_START_DATE
from src.gui.main_tabs import fleet_replay_panel_surface as surface
from src.simulator.fleet.bot_state_loader import load_bot_configs_from_state
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_pictures_match,
    assert_same_skin,
    colour_count,
    sealed,
    unaltered,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

REPO_ROOT = Path(__file__).resolve().parents[1]
PANEL_SOURCE = (
    REPO_ROOT / "src" / "gui" / "simulator_tab" / "fleet" / "fleet_replay_panel.py"
)
CONNECT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

PIXEL_SIZE = (900, 700)

SHIPPED_CLASS_TOTAL = 1
SHIPPED_METHOD_TOTAL = 33
SHIPPED_FUNCTION_TOTAL = 4
SHIPPED_SIGNAL_TOTAL = 3
SHIPPED_CONNECT_TOTAL = 7
SHIPPED_TIMER_BUILD_TOTAL = 2
SHIPPED_LOCK_TOTAL = 1
SHIPPED_THREAD_START_TOTAL = 0
SHIPPED_BUS_SUBSCRIBE_TOTAL = 0
SHIPPED_PIN_TOTAL = 9
BUTTON_CONNECT_TOTAL = 5
PAYLOAD_KEY_TOTAL = 49

YTD_START_MS = 1_775_001_600_000
NOW_MS = YTD_START_MS + 122 * 86_400_000


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, default=repr).encode(
            "utf-8"
        )
    ).hexdigest()


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


# The stored fleet. Read by the real loader out of a real bot_state file,
# so neither side ever invents a topology.


STORED_LOTS = [{"units": 1200.0, "price": 0.02}, {"units": 900.0, "price": 0.021}]

STORED_FLEET = {
    "bots": {
        "04e1cafcd0f14b1e9c77": {
            "config": {
                "symbol": "CHIP/USD",
                "mode": "scrumming",
                "exchange_id": "coinbase",
                "target_balance": 250.0,
            },
            "scrumming_state": {
                "main_lots": STORED_LOTS,
                "anchor_target_balance": 250.0,
                "target_balance": 252.1391,
                "quote_to_usd": 1.0,
            },
            "stats": {"current_price": 0.0212, "position_value": 233.6},
        },
        "092428b2ab114c2d8e51": {
            "config": {
                "symbol": "SPK/USD",
                "mode": "scrumming",
                "exchange_id": "coinbase",
                "target_balance": 100.0,
            },
            "scrumming_state": {
                "main_lots": [{"units": 120.0}],
                "anchor_target_balance": 100.0,
                "target_balance": 101.5,
                "quote_to_usd": 1.0,
            },
            "stats": {"current_price": 0.0, "position_value": 0.0},
        },
        "5f21bb0ac4d64a3ea910": {
            "config": {
                "symbol": "BONK/USD",
                "mode": "scrumming",
                "exchange_id": "kraken",
                "target_balance": 1975.5,
            },
            "scrumming_state": {"main_lots": [], "quote_to_usd": 1.0},
            "stats": {"current_price": 0.00002, "position_value": 12.0},
        },
    }
}


def stored_fleet_configs(tmp_path, fleet=None) -> list:
    """The configs the real loader reads out of a stored bot_state file."""
    written = tmp_path / "bot_state.json"
    written.write_text(
        json.dumps(fleet if fleet is not None else STORED_FLEET), encoding="utf-8"
    )
    return load_bot_configs_from_state(path=written)


def fleet_with(where, key, value) -> dict:
    """The stored fleet with one stored value replaced, ready to write."""
    changed = json.loads(json.dumps(STORED_FLEET))
    first = next(iter(changed["bots"].values()))
    first[where][key] = value
    return changed


def candles(count, start_ms=YTD_START_MS, price=100.0) -> list:
    """A run of candles the tablet registry hands back for one asset."""
    return [
        [start_ms + step * 300_000, price, price * 1.01, price * 0.99, price, 10.0]
        for step in range(count)
    ]


TABLET_ROWS = {"CHIP": candles(4), "SPK": candles(2, price=7.5)}

PARITY_LINES = [
    "Parity: 1 matched | 2 live-only | 0 sim-only",
    "  CHIP/USD     matched=   1  live_only=   1",
]


# The stand-ins. One set per side, never shared.


class Swaps:
    """Every module value one side replaces, and what it was.

    ``put`` reads the current value first, so a name the holder does not
    carry raises here rather than creating a fresh attribute that resets
    nothing.
    """

    def __init__(self):
        self.taken = []

    def put(self, holder, name, value):
        self.taken.append([holder, name, getattr(holder, name)])
        setattr(holder, name, value)

    def live(self) -> list:
        return [getattr(holder, name) for holder, name, _ in self.taken]

    def original(self) -> list:
        return [was for _, _, was in self.taken]

    def restored(self) -> bool:
        return all(getattr(h, n) is w for h, n, w in self.taken)

    def restore(self):
        for holder, name, was in reversed(self.taken):
            setattr(holder, name, was)


class PinRecorder:
    """The contract pins one side emits, in the order they fire."""

    def __init__(self):
        self.rows = []
        self.durations = {}

    def emit(self, name, actual, expected=None, context=None, every=None, **rest):
        self.durations[name] = rest.get("duration") is not None
        self.rows.append([name, actual, expected, dict(context or {}), every])

    def as_payload(self) -> list:
        return [list(row) for row in self.rows]


class TelemetryRecorder:
    """The advisory counter one side reports its calls and skips to."""

    def __init__(self):
        self.calls = []
        self.skips = []
        self.exceptions = []

    def record_call(self, name, count=1):
        del count
        self.calls.append(name)

    def record_skip(self, name, reason):
        self.skips.append([name, reason])

    def record_exception(self, name, exc):
        self.exceptions.append([name, type(exc).__name__])

    def as_payload(self) -> dict:
        return {
            "calls": list(self.calls),
            "skips": [list(one) for one in self.skips],
            "exceptions": [list(one) for one in self.exceptions],
        }


class Stats:
    """The counters one sim bot keeps."""

    def __init__(self, realised=0.0, fold=0.0, scrummed=0.0, folded=0.0):
        self.realised_pnl = realised
        self.accumulated_fold = fold
        self.total_scrummed_usd = scrummed
        self.total_folded_usd = folded


class BotConfig:
    """The config one sim bot carries."""

    def __init__(self, symbol="", mode="scrumming", exchange="coinbase", target=0.0):
        self.symbol = symbol
        self.mode = mode
        self.exchange_id = exchange
        self.target_balance = target


class Bot:
    """One spawned sim bot, as the panel reads it."""

    def __init__(
        self,
        bot_id="",
        config=None,
        holdings=0.0,
        last_price=0.0,
        target=0.0,
        quote_to_usd=1.0,
        stats=None,
        gate_state=None,
        summary=None,
    ):
        self.bot_id = bot_id
        self.config = config
        self._current_holdings = holdings
        self._last_price = last_price
        self._target_balance = target
        self._quote_to_usd = quote_to_usd
        self.stats = stats
        self._last_gate_state = gate_state
        self._last_summary = summary


class Progress:
    """The controller's record of how far the replay has run."""

    def __init__(
        self,
        played=0,
        total=0,
        fired=0,
        exceptions=0,
        samples=None,
        per_symbol=None,
        started=0.0,
        finished=False,
    ):
        self.candles_played = played
        self.total_candles = total
        self.trades_fired = fired
        self.exceptions = exceptions
        self.exception_samples = dict(samples or {})
        self.per_symbol_trade_count = dict(per_symbol or {})
        self.started_at_wall = started
        self.finished = finished
        self.anchored = False


class Tape:
    """The candle tape the controller plays, and the trades it recorded."""

    def __init__(
        self,
        rows_by_symbol=None,
        balances=None,
        trade_count=0,
        my_trades=None,
        snapshot_raises=None,
        history_raises=None,
    ):
        self.rows_by_symbol = dict(rows_by_symbol or {})
        self.balances = dict(balances or {})
        self.trade_count = trade_count
        self.my_trades = list(my_trades or [])
        self.snapshot_raises = snapshot_raises
        self.history_raises = history_raises

    def has_data(self, symbol):
        return bool(self.rows_by_symbol.get(symbol))

    def history(self, symbol, count):
        if self.history_raises is not None:
            raise self.history_raises
        return list(self.rows_by_symbol.get(symbol, []))[-count:]

    def snapshot(self):
        if self.snapshot_raises is not None:
            raise self.snapshot_raises
        return {"balances": dict(self.balances), "trades": self.trade_count}

    def fetch_my_trades(self):
        return list(self.my_trades)


class Controller:
    """The replay controller the panel builds, never started from here."""

    def __init__(self, spec=None, **named):
        self.built_with = dict(named)
        spec = spec or {}
        self._bots = list(spec.get("bots") or [])
        self._tape = spec.get("tape")
        self.tape = spec.get("tape")
        self._exchange = None
        self.progress = spec.get("progress") or Progress()
        self._markers = list(spec.get("markers") or [])
        self._task = spec.get("task")
        self.stop_raises = spec.get("stop_raises")
        self.stopped = 0
        self.built_sim = 0
        self.visual_cb = None
        self.visual_every = None
        self._expected_indices = None
        self._anchor_indices = None

    def _build_sim(self):
        self.built_sim += 1

    def request_stop(self):
        if self.stop_raises is not None:
            raise self.stop_raises
        self.stopped += 1

    def drain_markers(self):
        drained = list(self._markers)
        self._markers = []
        return drained

    def set_visual_refresh_cb(self, callback, every_n_candles=None):
        self.visual_cb = callback
        self.visual_every = every_n_candles

    def start(self):
        return ["replay", id(self)]


class Registry:
    """The Stone Tablet registry, as the spawn and the start read it."""

    def __init__(
        self, rows_by_asset=None, raises=None, window_status=None, notices=None
    ):
        self.rows_by_asset = dict(rows_by_asset or {})
        self.raises = raises
        self.window_status = dict(window_status or {})
        self.notices = dict(notices or {})
        self.asked = []

    def get_candles(self, asset, since_ms, until_ms, timeframe, exchange_id):
        self.asked.append([asset, since_ms, until_ms, timeframe, exchange_id])
        if self.raises is not None:
            raise self.raises
        return list(self.rows_by_asset.get(asset, []))

    def check_window_availability(self, asset, since_ms, until_ms, exchange_id=None):
        del since_ms, until_ms, exchange_id
        return self.window_status.get(asset, surface.WINDOW_STATUS_FULL)

    def get_asset_availability(self, asset, exchange_id=None):
        del exchange_id
        notice = self.notices.get(asset)
        return Availability(notice) if notice is not None else None


class Availability:
    """What one asset's tablet says about the history the venue holds."""

    def __init__(self, notice):
        self.notice = notice

    def listing_notice(self):
        return self.notice


class Schedule:
    """Where a replay or a fetch is handed, and what it does with it."""

    def __init__(self, raises=None):
        self.raises = raises
        self.scheduled = []

    def run(self, name, loop):
        if self.raises is not None:
            raise self.raises
        self.scheduled.append([name, loop])
        return len(self.scheduled)


class Summary:
    """One bot's indicator vote, as the voting panel reads it."""

    def __init__(self, timeframe="5m", confidence=0.5):
        self.timeframe = timeframe
        self.bullish_count = 3
        self.bearish_count = 1
        self.neutral_count = 2
        self.net_score = 2
        self.consensus_confidence = confidence
        self.consensus_direction = Direction("BULLISH")
        self.signals = [Signal("RSI", "BULLISH", 0.7)]


class Direction:
    def __init__(self, name):
        self.name = name


class Signal:
    def __init__(self, indicator, direction, confidence):
        self.indicator = indicator
        self.direction = Direction(direction)
        self.confidence = confidence


class Chart:
    """The Simulator price chart, recording what the drain feeds it."""

    def __init__(self):
        self.bars = []
        self.markers = []
        self.symbols = []
        self.cleared = 0
        self.ytd_starts = []
        self.updates = 0

    def clear_data(self):
        self.cleared += 1

    def set_symbols(self, symbols):
        self.symbols = list(symbols)

    def set_ytd_start(self, symbol, start):
        self.ytd_starts.append([symbol, start])

    def append_tick(
        self, symbol, close_price, volume, ts=None, open_price=None, high=None, low=None
    ):
        self.bars.append([symbol, close_price, volume, ts, open_price, high, low])

    def mark_trade(self, symbol, ok):
        self.markers.append([symbol, ok])

    def update(self):
        self.updates += 1


class Readout:
    """The shared indicator voting panel, recording what it is fed."""

    def __init__(self):
        self.rows = []
        self.bot_list = []

    def update_bot_list(self, entries):
        self.bot_list = list(entries)

    def update_data(self, payload, symbol):
        self.rows.append([payload, symbol])


class Strip:
    """The Simulator header strip, recording every field pushed into it."""

    def __init__(self):
        self.fields = {}

    def set(self, name, value):
        self.fields[name] = value


class GateCell:
    """One symbol's gate row, recording every repaint."""

    def __init__(self):
        self.painted = []

    def update_gates(
        self,
        scrum_armed,
        fold_armed,
        scrum_blockers,
        fold_blockers,
        landing_strip_side,
    ):
        self.painted.append(
            [
                scrum_armed,
                fold_armed,
                list(scrum_blockers),
                list(fold_blockers),
                landing_strip_side,
            ]
        )


class GatePane:
    """The gate pane the panel owns, standing in for GateStatusPanel."""

    def __init__(self, cells=None):
        self.cells = dict(cells or {})
        self.symbols = []

    def set_symbols(self, symbols):
        self.symbols = list(symbols)

    def cell_for(self, symbol):
        return self.cells.get(symbol)


class FakeAsyncio:
    """The loop hand-off the panel makes, without a loop."""

    def __init__(self, schedule):
        self.schedule = schedule
        self.pending = []

    def run_coroutine_threadsafe(self, coro, loop):
        name = coro[0] if isinstance(coro, list) else "fetch"
        if not isinstance(coro, list):
            self.pending.append(coro)
        self.schedule.run(name, loop)
        return Future()


class Future:
    """The handle a scheduled coroutine returns."""

    def __init__(self):
        self.callbacks = []

    def add_done_callback(self, callback):
        self.callbacks.append(callback)


# One scenario is one panel, one fleet and one list of steps.


def spec_bots(spec) -> list:
    """The sim bots one scenario's controller holds."""
    return [
        Bot(
            bot_id=one.get("bot_id", ""),
            config=(
                BotConfig(
                    symbol=one.get("symbol", ""),
                    mode=one.get("mode", "scrumming"),
                    exchange=one.get("exchange", "coinbase"),
                    target=one.get("target", 0.0),
                )
                if one.get("with_config", True)
                else None
            ),
            holdings=one.get("holdings", 0.0),
            last_price=one.get("last_price", 0.0),
            target=one.get("live_target", 0.0),
            quote_to_usd=one.get("quote_to_usd", 1.0),
            stats=(Stats(**one["stats"]) if one.get("stats") is not None else None),
            gate_state=one.get("gate_state"),
            summary=(
                Summary(**one["summary"]) if one.get("summary") is not None else None
            ),
        )
        for one in spec.get("bots") or []
    ]


def spec_controller(spec):
    """The controller one scenario's panel is handed, already built."""
    holds = spec.get("controller")
    if holds is None:
        return None
    return {
        "bots": spec_bots(holds),
        "tape": (Tape(**holds["tape"]) if holds.get("tape") is not None else None),
        "progress": (
            Progress(**holds["progress"]) if holds.get("progress") is not None else None
        ),
        "markers": holds.get("markers"),
        "task": holds.get("task"),
        "stop_raises": holds.get("stop_raises"),
    }


# The shipped side: the real Qt panel, with its outward edges stood in.


def shipped_module():
    from src.gui.simulator_tab.fleet import fleet_replay_panel

    return fleet_replay_panel


def frozen_time():
    """The wall clock every drive reads, stopped so no reading moves."""
    return NOW_MS / 1000.0


def frozen_monotonic():
    """The elapsed clock every drive reads, stopped so no duration moves."""
    return 100.0


def no_live_trades(**named):
    """The live trade log, empty, so no drive reads the real one."""
    del named
    return []


def installed_sink():
    """A pin sink the panel finds already installed, so it installs none."""
    return SINK_ALREADY_THERE


def keep_sink(sink):
    """Refuse the panel's attempt to install a sink of its own."""
    del sink


SINK_ALREADY_THERE = object()


def build_sim_state(bots, source_configs=None):
    """The sim fleet's own state document, standing in for the writer."""
    del source_configs
    return {"bot_count": len(list(bots))}


def compare_to_bot_state(state):
    """How the sim fleet compares with the live one, per bot."""
    del state
    return {}


def diff_spawns(previous, current):
    """What moved between the last Load and this one."""
    del previous, current
    return {
        "first_spawn": True,
        "added": [],
        "removed": [],
        "changed": [],
        "unchanged": 0,
    }


def load_sim_state(*ignored, **named):
    """The state document the last Load left behind."""
    del ignored, named
    return {}


def save_sim_state(state, *ignored, **named):
    """Where the sim fleet's state would be written, writing nothing."""
    del state, ignored, named


class ShippedSide:
    """The Qt Fleet Replay panel, driven step by step.

    Every module the panel reaches out to is replaced for the length of
    one drive and put back by ``close``. The panel's own code runs.
    """

    def __init__(self, spec):
        self.spec = spec
        self.swaps = Swaps()
        self.pins = PinRecorder()
        self.telemetry = TelemetryRecorder()
        self.activity = []
        self.performance = []
        self.emitted = []
        self.steps = []
        self.registry = Registry(
            rows_by_asset=spec.get("tablets", TABLET_ROWS),
            raises=spec.get("registry_raises"),
            window_status=spec.get("window_status"),
            notices=spec.get("notices"),
        )
        self.schedule = Schedule(spec.get("schedule_raises"))
        self.controller_holds = spec_controller(spec)
        self.built = []
        self.chart = Chart() if spec.get("chart", False) else None
        self.readout = Readout() if spec.get("readout", False) else None
        self.strip = Strip() if spec.get("strip", True) else None
        self.gate_cells = {name: GateCell() for name in spec.get("gate_symbols") or []}
        self.anchors = list(spec.get("anchors") or [])
        self.asyncio = FakeAsyncio(self.schedule)
        self._install()
        app()
        self.panel = shipped_module().FleetReplayPanel()
        self.panel._gate_panel = GatePane(self.gate_cells)
        self.panel.set_visual_widgets(
            price_chart=self.chart,
            voting_readout=self.readout,
            stat_strip=self.strip,
        )
        if spec.get("wire_logs", True):
            self.panel.set_log_callbacks(self.activity.append, self.performance.append)
        self.panel.set_bot_manager(spec.get("bot_manager"))
        if spec.get("loop_wired", True):
            self.panel._async_loop_getter = lambda: spec.get("loop", "loop")
        self.panel._full_eval_chk.setChecked(spec.get("full_evaluation", False))
        self.panel._confirm_reset = lambda: spec.get("confirm_reset", True)
        self.panel.fleetLoaded.connect(
            lambda configs: self.emitted.append(["fleetLoaded", len(configs)])
        )
        self.panel.replayStarted.connect(
            lambda: self.emitted.append(["replayStarted", None])
        )
        self.panel.replayStopped.connect(
            lambda: self.emitted.append(["replayStopped", None])
        )
        if self.controller_holds is not None:
            self.panel._controller = Controller(self.controller_holds)
        if spec.get("configs") is not None:
            self.panel._configs = [dict(one) for one in spec["configs"]]
            self.panel._populate_fleet_table()
        if spec.get("ytd_trades") is not None:
            self.panel._ytd_trades = [dict(one) for one in spec["ytd_trades"]]

    def _compare_trades(self, live_trades, sim_trades):
        """The comparison the parity harness runs, standing in for its maths."""
        if self.spec.get("parity_raises") is not None:
            raise self.spec["parity_raises"]
        return [len(live_trades), len(sim_trades)]

    async def _fetch_history(self, manager, since_ts):
        """The venue walk the fetch awaits, standing in for the network."""
        del manager, since_ts
        return [dict(one) for one in self.spec.get("fetched") or []]

    def _stored_configs(self, *ignored, **named):
        """What the stored fleet load hands the panel, or its refusal."""
        del ignored, named
        if self.spec.get("loader_raises") is not None:
            raise self.spec["loader_raises"]
        return [dict(one) for one in self.spec.get("configs") or []]

    def _smart_wires(self, *ignored, **named):
        """The cross-bot wires the stored fleet load hands the panel."""
        del ignored, named
        return list(self.spec.get("wires") or [])

    def _anchor_indices(self, *ignored, **named):
        """The candle positions the controller says carry a live trade."""
        del ignored, named
        return list(self.anchors)

    def _clock_timestamps(self, *ignored, **named):
        """The master clock the controller builds, empty for every drive."""
        del ignored, named
        return []

    def _get_registry(self, *ignored, **named):
        """The Stone Tablet registry the panel reads its candles from."""
        del ignored, named
        return self.registry

    def _build_controller(self, **named):
        """The controller the panel builds, recorded with what it was given."""
        self.built.append(dict(named))
        return Controller(self.controller_holds, **named)

    def _get_telemetry(self, *ignored, **named):
        """The advisory counter the panel reports its calls to."""
        del ignored, named
        return self.telemetry

    def _report_lines(self, *ignored, **named):
        """The parity report lines, standing in for the harness's own."""
        del ignored, named
        return list(PARITY_LINES)

    def _install(self):
        from src.core import feature_telemetry, signal_contract
        from src.exchange import history_helpers
        from src.simulator.fleet import (
            bot_state_loader,
            fleet_replay_controller,
            simulator_bot_state,
        )
        from src.trading import live_log_reader, stone_tablets
        from src.trading.stone_tablets import fetcher, parity_harness
        from src.trading.stone_tablets import registry as registry_module

        panel = shipped_module()
        loader = bot_state_loader
        controller_module = fleet_replay_controller
        state = simulator_bot_state

        self.swaps.put(loader, "load_bot_configs_from_state", self._stored_configs)
        self.swaps.put(loader, "load_smart_wires_from_state", self._smart_wires)
        self.swaps.put(
            controller_module, "FleetReplayController", self._build_controller
        )
        self.swaps.put(controller_module, "build_anchor_indices", self._anchor_indices)
        self.swaps.put(
            controller_module, "clock_timestamps_from_candles", self._clock_timestamps
        )
        self.swaps.put(registry_module, "get_registry", self._get_registry)
        self.swaps.put(stone_tablets, "get_registry", self._get_registry)
        self.swaps.put(stone_tablets, "WindowStatus", WindowStatusStandIn)
        self.swaps.put(fetcher, "YTD_START_MS", YTD_START_MS)
        self.swaps.put(state, "build_sim_state", build_sim_state)
        self.swaps.put(state, "compare_to_bot_state", compare_to_bot_state)
        self.swaps.put(state, "diff_spawns", diff_spawns)
        self.swaps.put(state, "load_sim_state", load_sim_state)
        self.swaps.put(state, "save_sim_state", save_sim_state)
        self.swaps.put(signal_contract, "emit", self.pins.emit)
        self.swaps.put(signal_contract, "get_sink", installed_sink)
        self.swaps.put(signal_contract, "set_sink", keep_sink)
        self.swaps.put(feature_telemetry, "get_telemetry", self._get_telemetry)
        self.swaps.put(live_log_reader, "live_trades", no_live_trades)
        self.swaps.put(parity_harness, "compare_trades", self._compare_trades)
        self.swaps.put(parity_harness, "format_report_lines", self._report_lines)
        self.swaps.put(
            history_helpers, "fetch_all_history_chunked", self._fetch_history
        )
        self.swaps.put(panel, "asyncio", self.asyncio)
        self.swaps.put(time, "time", frozen_time)
        self.swaps.put(time, "monotonic", frozen_monotonic)

    def step(self, index, name, argument=None):
        """Take one step and record which one it was."""
        self.steps.append([index, name, argument])
        if name == "load":
            self.panel._on_load_clicked()
        elif name == "fetch":
            self.panel._on_fetch_ytd_clicked()
        elif name == "fetch_arrived":
            for coro in self.asyncio.pending:
                asyncio.run(coro)
            self.asyncio.pending = []
        elif name == "fetch_done":
            self.panel._on_fetch_ytd_done()
        elif name == "history":
            self.panel.on_history_refreshed(argument)
        elif name == "start":
            self.panel._on_start_clicked()
        elif name == "stop":
            self.panel._on_stop_clicked()
        elif name == "reset":
            self.panel._on_reset_clicked()
        elif name == "progress":
            self.panel._refresh_progress()
        elif name == "tick":
            self.panel._on_visual_refresh_tick(0)
        elif name == "drain":
            self.panel._drain_visual_snapshot()
        elif name == "status_error":
            self.panel._status_error(argument)
        else:
            raise AssertionError(f"no step named {name!r}")

    def payload(self) -> dict:
        return shipped_payload(self)

    def close(self):
        for coro in self.asyncio.pending:
            coro.close()
        self.asyncio.pending = []
        for timer in (
            getattr(self.panel, "_progress_timer", None),
            getattr(self.panel, "_drain_timer", None),
        ):
            if timer is not None:
                timer.stop()
        self.panel.setParent(None)
        self.panel.deleteLater()
        self.panel = None
        self.swaps.restore()


class WindowStatusStandIn:
    """The tablet coverage names the availability notice reads."""

    FULL = surface.WINDOW_STATUS_FULL


def qt_table_rows(table) -> list:
    """Every cell text the fleet table holds, row by row."""
    rows = []
    for row in range(table.rowCount()):
        cells = []
        for column in range(table.columnCount()):
            item = table.item(row, column)
            cells.append(None if item is None else item.text())
        rows.append(cells)
    return rows


def shipped_payload(side) -> dict:
    """Every value the Qt panel currently draws, read off the widgets."""
    from PySide6.QtWidgets import QFrame, QLabel

    panel = side.panel
    header = panel.findChild(QFrame)
    labels = [one for one in panel.findChildren(QLabel) if one.parentWidget() is header]
    title, subtitle = labels[0], labels[1]
    table = panel._fleet_table
    return {
        "accessible_name": panel.accessibleName(),
        "header": {
            "title": title.text(),
            "subtitle": subtitle.text(),
            "subtitle_word_wrap": subtitle.wordWrap(),
        },
        "buttons": {
            "load": {
                "text": panel._load_btn.text(),
                "tooltip": panel._load_btn.toolTip(),
            },
            "fetch": {
                "text": panel._fetch_ytd_btn.text(),
                "tooltip": panel._fetch_ytd_btn.toolTip(),
                "enabled": panel._fetch_ytd_btn.isEnabled(),
            },
            "reset": {
                "text": panel._reset_btn.text(),
                "tooltip": panel._reset_btn.toolTip(),
            },
            "start": {
                "text": panel._start_btn.text(),
                "tooltip": panel._start_btn.toolTip(),
                "enabled": panel._start_btn.isEnabled(),
            },
            "stop": {
                "text": panel._stop_btn.text(),
                "tooltip": panel._stop_btn.toolTip(),
                "enabled": panel._stop_btn.isEnabled(),
            },
        },
        "full_evaluation": {
            "text": panel._full_eval_chk.text(),
            "tooltip": panel._full_eval_chk.toolTip(),
            "checked": panel._full_eval_chk.isChecked(),
        },
        "status": {"text": panel._status_lbl.text()},
        "fleet_table": {
            "title": panel._fleet_group.title(),
            "tooltip": table.toolTip(),
            "columns": [
                table.horizontalHeaderItem(one).text()
                for one in range(table.columnCount())
            ],
            "column_count": table.columnCount(),
            "row_count": table.rowCount(),
            "rows": qt_table_rows(table),
            "alternating_row_colors": table.alternatingRowColors(),
            "edit_triggers": (
                table.editTriggers().name.decode()
                if isinstance(table.editTriggers().name, bytes)
                else str(table.editTriggers().name)
            ),
            "header_resize_mode": table.horizontalHeader().sectionResizeMode(0).name,
            "stretch_last_section": table.horizontalHeader().stretchLastSection(),
        },
        "progress": {
            "text": panel._progress_lbl.text(),
            "word_wrap": panel._progress_lbl.wordWrap(),
        },
        "timers_running": {
            "progress": bool(
                panel._progress_timer is not None and panel._progress_timer.isActive()
            ),
            "drain": bool(
                panel._drain_timer is not None and panel._drain_timer.isActive()
            ),
        },
        "timer_intervals": {
            "progress": (
                panel._progress_timer.interval()
                if panel._progress_timer is not None
                else None
            ),
            "drain": (
                panel._drain_timer.interval()
                if panel._drain_timer is not None
                else None
            ),
        },
        "signals_emitted": [list(one) for one in side.emitted],
        "stat_fields": dict(side.strip.fields) if side.strip is not None else {},
        "gate_rows_drawn": sum(len(cell.painted) for cell in side.gate_cells.values()),
        "chart_bars": (
            [list(one) for one in side.chart.bars] if side.chart is not None else []
        ),
        "chart_markers": (
            [list(one) for one in side.chart.markers] if side.chart is not None else []
        ),
        "voting_rows": (
            [[one[0], one[1]] for one in side.readout.rows]
            if side.readout is not None
            else []
        ),
        "bot_statuses": panel.sim_bot_statuses(),
        "configs": panel.get_loaded_configs(),
        "ytd_trade_count": len(panel._ytd_trades),
        "activity_lines": list(side.activity),
        "performance_lines": list(side.performance),
        "telemetry": side.telemetry.as_payload(),
        "pins": side.pins.as_payload(),
        "registry_asked": [list(one) for one in side.registry.asked],
        "scheduled": [list(one) for one in side.schedule.scheduled],
        "steps": [list(one) for one in side.steps],
    }


# The new side: the surface's model, driven through the same steps.


class SurfaceSide:
    """The Qt-free model, driven step by step through the same scenario."""

    def __init__(self, spec):
        self.spec = spec
        self.swaps = Swaps()
        self.pins = PinRecorder()
        self.telemetry = TelemetryRecorder()
        self.registry = surface.TabletRegistrySource(
            rows_by_asset=spec.get("tablets", TABLET_ROWS),
            raises=spec.get("registry_raises"),
            window_status=spec.get("window_status"),
            availability={
                asset: surface.AvailabilitySource(notice)
                for asset, notice in (spec.get("notices") or {}).items()
            },
        )
        self.schedule = surface.ScheduleSink(spec.get("schedule_raises"))
        self.built = []
        self.chart = Chart() if spec.get("chart", False) else None
        self.readout = Readout() if spec.get("readout", False) else None
        self.strip = Strip() if spec.get("strip", True) else None
        self.gate_cells = {name: GateCell() for name in spec.get("gate_symbols") or []}
        self.steps = []
        holds = spec_controller(spec)
        made = self.built

        def make(**named):
            made.append(dict(named))
            return surface_controller(holds, named)

        self.model = surface.FleetReplayPanelModel(
            loader=surface.FleetLoaderSource(
                configs=[dict(one) for one in spec.get("configs") or []],
                wires=spec.get("wires"),
                raises=spec.get("loader_raises"),
            ),
            registry=self.registry,
            controller_factory=make,
            schedule=self.schedule,
            loop=spec.get("loop", "loop"),
            loop_wired=spec.get("loop_wired", True),
            telemetry=SurfaceTelemetry(self.telemetry),
            pins=SurfacePins(self.pins),
            anchors=surface.AnchorSource(spec.get("anchors")),
            chart_wired=spec.get("chart", False),
            readout_wired=spec.get("readout", False),
            strip_wired=spec.get("strip", True),
            parity=surface.ParitySource(
                lines=PARITY_LINES, raises=spec.get("parity_raises")
            ),
            activity_wired=spec.get("wire_logs", True),
        )
        self.model.set_bot_manager(spec.get("bot_manager") is not None)
        self.model.full_evaluation = spec.get("full_evaluation", False)
        self.model.confirm_reset = spec.get("confirm_reset", True)
        if holds is not None:
            self.model.controller = surface_controller(holds, {})
        if spec.get("configs") is not None:
            self.model.configs = [dict(one) for one in spec["configs"]]
            self.model.populate_table()
        if spec.get("ytd_trades") is not None:
            self.model.ytd_trades = [dict(one) for one in spec["ytd_trades"]]

    def step(self, index, name, argument=None):
        self.steps.append([index, name, argument])
        model = self.model
        if name == "load":
            model.load()
        elif name == "fetch":
            model.fetch_ytd()
        elif name == "fetch_arrived":
            model.fetch_arrived(
                [dict(one) for one in self.spec.get("fetched") or []],
                since_ts=DEFAULT_START_DATE.timestamp(),
            )
        elif name == "fetch_done":
            model.fetch_done(model.ytd_trades)
        elif name == "history":
            model.on_history_refreshed(argument)
        elif name == "start":
            model.start(now_ms=NOW_MS, ytd_start_ms=YTD_START_MS)
        elif name == "stop":
            model.stop()
        elif name == "reset":
            model.reset()
        elif name == "progress":
            model.refresh_progress(now_s=NOW_MS / 1000.0)
        elif name == "tick":
            model.visual_refresh_tick()
        elif name == "drain":
            model.drain(
                chart=self.chart is not None,
                readout=self.readout is not None,
                cells=set(self.gate_cells),
            )
        elif name == "status_error":
            model.status_error(argument)
        else:
            raise AssertionError(f"no step named {name!r}")

    def payload(self) -> dict:
        return surface_payload(self)

    def close(self):
        self.model = None
        self.swaps.restore()


class SurfaceTelemetry:
    """The surface's telemetry sink, writing into the shared recorder."""

    def __init__(self, recorder):
        self.recorder = recorder
        self.calls = recorder.calls
        self.skips = recorder.skips
        self.exceptions = recorder.exceptions

    def call(self, name):
        self.recorder.record_call(name)

    def skip(self, name, reason):
        self.recorder.record_skip(name, reason)

    def exception(self, name, exc):
        self.recorder.record_exception(name, exc)


class SurfacePins:
    """The surface's pin sink, writing into the shared recorder."""

    def __init__(self, recorder):
        self.recorder = recorder
        self.rows = recorder.rows

    def emit(self, name, actual, expected=None, context=None, every=None):
        self.recorder.emit(name, actual, expected, context, every)


def surface_controller(holds, named):
    """The surface's controller stand-in, holding one scenario's bots."""
    if holds is None:
        return surface.ControllerSource()
    del named
    return surface.ControllerSource(
        bots=holds["bots"],
        tape=holds["tape"],
        progress=(
            surface.ProgressSource(
                candles_played=holds["progress"].candles_played,
                total_candles=holds["progress"].total_candles,
                trades_fired=holds["progress"].trades_fired,
                exceptions=holds["progress"].exceptions,
                exception_samples=holds["progress"].exception_samples,
                per_symbol_trade_count=holds["progress"].per_symbol_trade_count,
                started_at_wall=holds["progress"].started_at_wall,
                finished=holds["progress"].finished,
            )
            if holds["progress"] is not None
            else None
        ),
        markers=holds["markers"],
        task=holds["task"],
        stop_raises=holds["stop_raises"],
    )


def surface_payload(side) -> dict:
    """Every value the surface currently describes, in the panel's shape."""
    model = side.model
    for symbol, close, volume, ts, open_price, high, low in model.chart_bars:
        if (
            side.chart is not None
            and [
                symbol,
                close,
                volume,
                ts,
                open_price,
                high,
                low,
            ]
            not in side.chart.bars
        ):
            side.chart.append_tick(
                symbol,
                close,
                volume,
                ts=ts,
                open_price=open_price,
                high=high,
                low=low,
            )
    built = surface.build_view_model(model, [list(one) for one in side.steps])
    return {
        "accessible_name": built["accessible_name"],
        "header": {
            "title": built["header"]["title"],
            "subtitle": built["header"]["subtitle"],
            "subtitle_word_wrap": built["header"]["subtitle_word_wrap"],
        },
        "buttons": built["buttons"],
        "full_evaluation": built["full_evaluation"],
        "status": {"text": built["status"]["text"]},
        "fleet_table": {
            "title": built["fleet_table"]["title"],
            "tooltip": built["fleet_table"]["tooltip"],
            "columns": built["fleet_table"]["columns"],
            "column_count": built["fleet_table"]["column_count"],
            "row_count": built["fleet_table"]["row_count"],
            "rows": built["fleet_table"]["rows"],
            "alternating_row_colors": built["fleet_table"]["alternating_row_colors"],
            "edit_triggers": built["fleet_table"]["edit_triggers"],
            "header_resize_mode": built["fleet_table"]["header_resize_mode"],
            "stretch_last_section": built["fleet_table"]["stretch_last_section"],
        },
        "progress": {
            "text": built["progress"]["text"],
            "word_wrap": built["progress"]["word_wrap"],
        },
        "timers_running": built["timers_running"],
        "timer_intervals": {
            "progress": (
                surface.PROGRESS_TIMER_MS if model.progress_timer_running else None
            ),
            "drain": surface.DRAIN_TIMER_MS if model.drain_timer_running else None,
        },
        "signals_emitted": built["signals_emitted"],
        "stat_fields": built["stat_fields"],
        "gate_rows_drawn": built["gate_rows_drawn"],
        "chart_bars": built["chart_bars"],
        "chart_markers": built["chart_markers"],
        "voting_rows": [[one[0], one[1]] for one in built["voting_rows"]],
        "bot_statuses": built["bot_statuses"],
        "configs": built["configs"],
        "ytd_trade_count": built["ytd_trade_count"],
        "activity_lines": built["activity_lines"],
        "performance_lines": built["performance_lines"],
        "telemetry": built["telemetry"],
        "pins": built["pins"],
        "registry_asked": [list(one) for one in side.registry.asked],
        "scheduled": [list(one) for one in side.schedule.scheduled],
        "steps": [list(one) for one in side.steps],
    }


# The scenarios. Each one is a fleet, a controller and a list of steps.


CHIP = {
    "symbol": "CHIP/USD",
    "mode": "scrumming",
    "exchange_id": "coinbase",
    "target_balance": 250.0,
}
SPK = {
    "symbol": "SPK/USD",
    "mode": "scrumming",
    "exchange_id": "coinbase",
    "target_balance": 100.0,
}
BONK = {
    "symbol": "BONK/USD",
    "mode": "scrumming",
    "exchange_id": "kraken",
    "target_balance": 1975.5,
}
TWO_BOTS = [CHIP, SPK]
THREE_BOTS = [CHIP, SPK, BONK]

GATE_STATE = {
    "scrum_armed": True,
    "fold_armed": False,
    "scrum_blockers": ["cooldown"],
    "fold_blockers": [],
    "scrum_fixture": {"landing_strip_side": "above"},
    "fold_fixture": {},
}

RUNNING_BOTS = [
    {
        "bot_id": "simulated_chip",
        "symbol": "CHIP/USD",
        "target": 250.0,
        "live_target": 252.14,
        "holdings": 1200.0,
        "last_price": 0.0212,
        "stats": {"realised": 12.5, "fold": 3.25, "scrummed": 400.0, "folded": 390.0},
        "gate_state": GATE_STATE,
        "summary": {"confidence": 0.42},
    },
    {
        "bot_id": "simulated_spk",
        "symbol": "SPK/USD",
        "target": 100.0,
        "live_target": 101.5,
        "holdings": 120.0,
        "last_price": 7.5,
        "stats": {},
        "gate_state": None,
        "summary": None,
    },
]

RUNNING_TAPE = {
    "rows_by_symbol": {
        "CHIP/USD": candles(3),
        "SPK/USD": candles(2, price=7.5),
    },
    "balances": {"USD": 99.4, "USDC": 12.0, "BTC": 3.0},
    "trade_count": 7,
    "my_trades": [{"symbol": "CHIP/USD", "timestamp": YTD_START_MS}],
}

LIVE_TRADES = [
    {"symbol": "CHIP/USD", "timestamp": YTD_START_MS / 1000.0 + 60},
    {"symbol": "CHIP/USD", "timestamp": YTD_START_MS / 1000.0 + 120},
    {"symbol": "SPK/USD", "timestamp": YTD_START_MS / 1000.0 + 180},
]


def running(**named) -> dict:
    """A controller holding two spawned bots and a tape that answers."""
    holds = {
        "bots": RUNNING_BOTS,
        "tape": dict(RUNNING_TAPE),
        "progress": {"played": 120, "total": 1000, "fired": 7, "started": 1.0},
    }
    holds.update(named)
    return holds


SCENARIOS = [
    {"name": "idle"},
    {"name": "loaded_fleet", "configs": TWO_BOTS, "steps": [("load",)]},
    {
        "name": "loaded_three_one_without_tablet",
        "configs": THREE_BOTS,
        "steps": [("load",)],
    },
    {
        "name": "load_refused",
        "configs": TWO_BOTS,
        "loader_raises": ValueError("bot_state.json is not JSON"),
        "steps": [("load",)],
    },
    {
        "name": "spawn_refused",
        "configs": TWO_BOTS,
        "registry_raises": OSError("tablet unreadable"),
        "steps": [("load",)],
    },
    {"name": "empty_fleet", "configs": [], "steps": [("load",)]},
    {
        "name": "no_tablets_at_all",
        "configs": TWO_BOTS,
        "tablets": {},
        "steps": [("load",)],
    },
    {"name": "history_trades", "steps": [("history", LIVE_TRADES)]},
    {"name": "history_empty", "steps": [("history", [])]},
    {"name": "fetch_no_loop", "loop": None, "steps": [("fetch",)]},
    {"name": "fetch_no_manager", "steps": [("fetch",)]},
    {"name": "fetch_scheduled", "bot_manager": "manager", "steps": [("fetch",)]},
    {
        "name": "fetch_schedule_failed",
        "bot_manager": "manager",
        "schedule_raises": RuntimeError("loop is closed"),
        "steps": [("fetch",)],
    },
    {
        "name": "fetch_done_empty",
        "bot_manager": "manager",
        "steps": [("fetch",), ("fetch_done",)],
    },
    {
        "name": "fetch_done_full",
        "bot_manager": "manager",
        "ytd_trades": LIVE_TRADES,
        "steps": [("fetch_done",)],
    },
    {"name": "start_no_fleet", "steps": [("start",)]},
    {
        "name": "start_busy",
        "configs": TWO_BOTS,
        "controller": running(progress={"played": 5, "total": 10, "started": 1.0}),
        "steps": [("start",)],
    },
    {"name": "start_no_loop", "configs": TWO_BOTS, "loop": None, "steps": [("start",)]},
    {
        "name": "start_no_tablets",
        "configs": TWO_BOTS,
        "tablets": {},
        "steps": [("start",)],
    },
    {
        "name": "start_no_tablets_no_log",
        "configs": TWO_BOTS,
        "tablets": {},
        "wire_logs": False,
        "steps": [("start",)],
    },
    {
        "name": "start_scheduled",
        "configs": THREE_BOTS,
        "chart": True,
        "readout": True,
        "steps": [("start",)],
    },
    {
        "name": "start_full_evaluation",
        "configs": TWO_BOTS,
        "full_evaluation": True,
        "steps": [("start",)],
    },
    {
        "name": "start_anchored",
        "configs": TWO_BOTS,
        "ytd_trades": LIVE_TRADES,
        "anchors": [0, 1, 2],
        "steps": [("start",)],
    },
    {
        "name": "start_schedule_failed",
        "configs": TWO_BOTS,
        "schedule_raises": RuntimeError("loop is closed"),
        "steps": [("start",)],
    },
    {
        "name": "start_with_availability_flag",
        "configs": TWO_BOTS,
        "window_status": {"CHIP": "PARTIAL"},
        "notices": {"CHIP": "CHIP listed 2025-11-04; no prior data exists."},
        "steps": [("start",)],
    },
    {"name": "stop_no_controller", "steps": [("stop",)]},
    {"name": "stop_ok", "controller": running(), "steps": [("stop",)]},
    {
        "name": "stop_refused",
        "controller": running(stop_raises=RuntimeError("task is gone")),
        "steps": [("stop",)],
    },
    {"name": "reset_idle", "configs": TWO_BOTS, "steps": [("reset",)]},
    {
        "name": "reset_declined",
        "configs": TWO_BOTS,
        "controller": running(progress={"played": 5, "total": 10, "started": 1.0}),
        "confirm_reset": False,
        "steps": [("reset",)],
    },
    {
        "name": "reset_running",
        "configs": TWO_BOTS,
        "controller": running(progress={"played": 5, "total": 10, "started": 1.0}),
        "steps": [("reset",)],
    },
    {
        "name": "reset_refused",
        "configs": TWO_BOTS,
        "controller": running(stop_raises=RuntimeError("task is gone")),
        "steps": [("reset",)],
    },
    {
        "name": "progress_running",
        "configs": TWO_BOTS,
        "controller": running(
            progress={
                "played": 120,
                "total": 1000,
                "fired": 7,
                "exceptions": 2,
                "samples": {"KeyError: symbol": 5, "ValueError: price": 3},
                "per_symbol": {"CHIP/USD": 4, "SPK/USD": 3},
                "started": NOW_MS / 1000.0 - 60.0,
            }
        ),
        "steps": [("progress",)],
    },
    {
        "name": "progress_eta_hours",
        "configs": TWO_BOTS,
        "controller": running(
            progress={
                "played": 10,
                "total": 1_000_000,
                "started": NOW_MS / 1000.0 - 60.0,
            }
        ),
        "steps": [("progress",)],
    },
    {
        "name": "progress_eta_seconds",
        "configs": TWO_BOTS,
        "controller": running(
            progress={"played": 900, "total": 1000, "started": NOW_MS / 1000.0 - 60.0}
        ),
        "steps": [("progress",)],
    },
    {
        "name": "progress_never_started",
        "configs": TWO_BOTS,
        "controller": running(progress={"played": 0, "total": 1000, "started": 0.0}),
        "steps": [("progress",)],
    },
    {
        "name": "progress_finished",
        "configs": TWO_BOTS,
        "controller": running(
            progress={
                "played": 1000,
                "total": 1000,
                "fired": 7,
                "per_symbol": {"CHIP/USD": 4},
                "started": NOW_MS / 1000.0 - 60.0,
                "finished": True,
            }
        ),
        "steps": [("progress",)],
    },
    {
        "name": "progress_finished_with_live_trades",
        "configs": TWO_BOTS,
        "ytd_trades": LIVE_TRADES,
        "controller": running(
            progress={
                "played": 1000,
                "total": 1000,
                "started": NOW_MS / 1000.0 - 60.0,
                "finished": True,
            }
        ),
        "steps": [("progress",)],
    },
    {
        "name": "drain_full",
        "controller": running(markers=[["CHIP/USD", True]]),
        "chart": True,
        "readout": True,
        "gate_symbols": ["CHIP/USD", "SPK/USD"],
        "steps": [("tick",), ("drain",)],
    },
    {
        "name": "drain_no_widgets",
        "controller": running(),
        "steps": [("tick",), ("drain",)],
    },
    {
        "name": "drain_no_cell",
        "controller": running(),
        "chart": True,
        "readout": True,
        "gate_symbols": ["SPK/USD"],
        "steps": [("tick",), ("drain",)],
    },
    {"name": "drain_with_no_snapshot", "controller": running(), "steps": [("drain",)]},
    {
        "name": "drain_tape_refuses_history",
        "controller": running(
            tape=dict(RUNNING_TAPE, history_raises=RuntimeError("tape is idle"))
        ),
        "chart": True,
        "gate_symbols": ["CHIP/USD"],
        "steps": [("tick",), ("drain",)],
    },
    {
        "name": "drain_tape_refuses_snapshot",
        "controller": running(
            tape=dict(RUNNING_TAPE, snapshot_raises=RuntimeError("no ledger"))
        ),
        "steps": [("tick",), ("drain",)],
    },
    {"name": "status_error_blank", "steps": [("status_error", "")]},
    {"name": "status_error_spaces", "steps": [("status_error", "   ")]},
    {"name": "status_error_text", "steps": [("status_error", "the venue said no")]},
    {
        "name": "load_then_start_then_stop",
        "configs": TWO_BOTS,
        "steps": [("load",), ("start",), ("stop",)],
    },
    {
        "name": "history_then_start",
        "configs": TWO_BOTS,
        "steps": [("history", LIVE_TRADES), ("start",)],
    },
]


SCENARIOS += [
    {
        "name": "fetch_arrived_full",
        "configs": TWO_BOTS,
        "bot_manager": "manager",
        "fetched": LIVE_TRADES,
        "steps": [("fetch",), ("fetch_arrived",), ("fetch_done",)],
    },
    {
        "name": "fetch_arrived_empty",
        "configs": TWO_BOTS,
        "bot_manager": "manager",
        "fetched": [],
        "steps": [("fetch",), ("fetch_arrived",), ("fetch_done",)],
    },
    {
        "name": "parity_report_written",
        "configs": TWO_BOTS,
        "ytd_trades": LIVE_TRADES,
        "controller": running(
            progress={
                "played": 1000,
                "total": 1000,
                "started": NOW_MS / 1000.0 - 60.0,
                "finished": True,
            }
        ),
        "steps": [("progress",)],
    },
    {
        "name": "parity_report_refused",
        "configs": TWO_BOTS,
        "ytd_trades": LIVE_TRADES,
        "parity_raises": ValueError("the trade rows are not dicts"),
        "controller": running(
            progress={
                "played": 1000,
                "total": 1000,
                "started": NOW_MS / 1000.0 - 60.0,
                "finished": True,
            }
        ),
        "steps": [("progress",)],
    },
    {
        "name": "drain_with_no_strip",
        "controller": running(),
        "strip": False,
        "steps": [("tick",), ("drain",)],
    },
]

BY_NAME = {one["name"]: one for one in SCENARIOS}

REFUSING_SCENARIOS = {
    "load_refused",
    "spawn_refused",
    "fetch_schedule_failed",
    "start_schedule_failed",
    "stop_refused",
    "reset_refused",
    "drain_tape_refuses_history",
    "drain_tape_refuses_snapshot",
}


def drive(side_class, spec) -> dict:
    """Build one side, take every step, and read what it drew."""
    side = side_class(spec)
    try:
        for index, step in enumerate(spec.get("steps") or []):
            side.step(index, step[0], step[1] if len(step) > 1 else None)
        return side.payload()
    finally:
        side.close()


def drive_old(spec) -> dict:
    return drive(ShippedSide, spec)


def drive_new(spec) -> dict:
    return drive(SurfaceSide, spec)


NAMES = [one["name"] for one in SCENARIOS]


# Both sides, value for value and by hash


@pytest.mark.parametrize("name", NAMES)
def test_the_two_sides_describe_the_same_panel(name):
    """The view model describes a different panel than the Qt one builds."""
    spec = BY_NAME[name]
    old = drive_old(spec)
    new = drive_new(spec)
    assert sorted(old) == sorted(new), (name, sorted(set(old) ^ set(new)))
    for key in sorted(old):
        assert new[key] == old[key], (name, key, old[key], new[key])
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", NAMES)
def test_the_two_sides_agree_when_the_new_side_is_driven_first(name):
    """The order the two sides run in changes what one of them reports."""
    spec = BY_NAME[name]
    new = drive_new(spec)
    old = drive_old(spec)
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", NAMES)
def test_one_input_twice_reads_the_same_on_each_side(name):
    """A side keeps state between drives, so a repeat reads differently."""
    spec = BY_NAME[name]
    assert digest(drive_old(spec)) == digest(drive_old(spec)), name
    assert digest(drive_new(spec)) == digest(drive_new(spec)), name


def test_two_different_real_inputs_are_told_apart():
    """The comparison passes whatever either side reports."""
    one = drive_old(BY_NAME["loaded_fleet"])
    other = drive_new(BY_NAME["loaded_three_one_without_tablet"])
    assert digest(one) != digest(other)
    assert one["fleet_table"]["row_count"] != other["fleet_table"]["row_count"]


def test_a_whole_number_and_a_decimal_are_told_apart():
    """A count of 12 and a count of 12.0 hash alike."""
    whole = {"count": 12}
    decimal = {"count": 12.0}
    assert whole == decimal
    assert digest(whole) != digest(decimal)


def test_two_not_a_numbers_are_told_apart_by_the_hash():
    """A not-a-number equals nothing, so a plain comparison reports noise."""
    left = {"reading": float("nan")}
    right = {"reading": float("nan")}
    assert left != right
    assert digest(left) == digest(right)
    assert digest(left) != digest({"reading": float("inf")})


# Refusals, compared by type


REFUSALS = [
    ("load", surface.FleetLoaderSource(raises=ValueError("bad json")), ValueError),
    ("load", surface.FleetLoaderSource(raises=OSError("no file")), OSError),
    ("load", surface.FleetLoaderSource(raises=KeyError("bots")), KeyError),
]


@pytest.mark.parametrize("name", sorted(REFUSING_SCENARIOS))
def test_a_refused_step_names_the_same_error_type_on_both_sides(name):
    """One side reports a refusal the other does not, or names another type."""
    spec = BY_NAME[name]
    old = drive_old(spec)
    new = drive_new(spec)
    assert old["status"]["text"] == new["status"]["text"], name
    assert old["telemetry"] == new["telemetry"], name
    assert old["activity_lines"] == new["activity_lines"], name


@pytest.mark.parametrize("kind", [ValueError, OSError, KeyError, RuntimeError])
def test_a_load_refusal_carries_its_own_type_on_both_sides(kind):
    """A refusal reads the same whatever went wrong, so the type is lost."""
    spec = dict(BY_NAME["load_refused"], loader_raises=kind("the reason"))
    old = drive_old(spec)
    new = drive_new(spec)
    assert kind.__name__ in old["status"]["text"]
    assert old["status"]["text"] == new["status"]["text"]


def test_the_refusal_comparison_tells_two_types_apart():
    """The refusal comparison passes whatever type was raised."""
    one = drive_new(dict(BY_NAME["load_refused"], loader_raises=ValueError("x")))
    other = drive_new(dict(BY_NAME["load_refused"], loader_raises=KeyError("x")))
    assert one["status"]["text"] != other["status"]["text"]


# Step sequences, including ones that refuse part way


SEQUENCES = [
    ("load_start_stop", [("load",), ("start",), ("stop",)], None),
    ("load_reset_load", [("load",), ("reset",), ("load",)], None),
    ("start_before_load", [("start",), ("load",), ("start",)], None),
    ("history_fetch_start", [("history", LIVE_TRADES), ("start",)], None),
]


@pytest.mark.parametrize("name,steps,_unused", SEQUENCES)
def test_a_step_sequence_reads_alike_on_both_sides(name, steps, _unused):
    """A step sequence leaves the two sides in different states."""
    spec = dict(BY_NAME["loaded_fleet"], name=name, steps=steps, bot_manager="manager")
    old = drive_old(spec)
    new = drive_new(spec)
    assert old["steps"] == new["steps"], name
    assert digest(old) == digest(new), name


def test_a_sequence_that_refuses_part_way_keeps_what_it_recorded():
    """A refusal in the middle threw away the steps taken before it."""
    spec = dict(
        BY_NAME["loaded_fleet"],
        name="refuse_part_way",
        steps=[("load",), ("start",), ("stop",)],
        schedule_raises=RuntimeError("loop is closed"),
    )
    old = drive_old(spec)
    new = drive_new(spec)
    assert old["steps"] == [[0, "load", None], [1, "start", None], [2, "stop", None]]
    assert old["steps"] == new["steps"]
    assert old["fleet_table"]["row_count"] == 2, "the load before the refusal was lost"
    assert "Schedule failed" in old["status"]["text"]
    assert digest(old) == digest(new)


def test_a_refused_table_refill_keeps_the_rows_it_had_already_written():
    """A refused refill left a row carrying a new label above an old reading."""
    counts = {"CHIP/USD": 4, "SPK/USD": 9}
    model = surface.FleetReplayPanelModel(
        controller_factory=lambda **named: surface.ControllerSource()
    )
    model.configs = [dict(CHIP), dict(SPK)]
    model.populate_table()
    before = [list(row) for row in model.rows]
    model.controller = surface.ControllerSource(
        progress=surface.ProgressSource(
            candles_played=1, total_candles=2, per_symbol_trade_count=counts
        )
    )
    model.refresh_progress(now_s=1.0, refill_raises_at=1)
    assert model.rows[0][surface.TRADES_COLUMN] == "4", "the first row was not written"
    assert model.rows[1] == before[1], "the second row is not the previous reading"
    assert model.rows[1][surface.TRADES_COLUMN] == surface.ZERO_TRADES_TEXT
    assert [call[0] for call in model.calls].count(surface.PROGRESS_COLUMN_FAILED) == 1
    assert surface.PROGRESS_COLUMN not in [call[0] for call in model.calls]


def test_the_refill_check_can_report_a_complete_refill():
    """The refused-refill check passes on a refill that never refused."""
    model = surface.FleetReplayPanelModel()
    model.configs = [dict(CHIP), dict(SPK)]
    model.populate_table()
    model.controller = surface.ControllerSource(
        progress=surface.ProgressSource(
            candles_played=1,
            total_candles=2,
            per_symbol_trade_count={"CHIP/USD": 4, "SPK/USD": 9},
        )
    )
    model.refresh_progress(now_s=1.0)
    assert [row[surface.TRADES_COLUMN] for row in model.rows] == ["4", "9"]
    assert surface.PROGRESS_COLUMN in [call[0] for call in model.calls]


# What the shipped panel holds, counted on the running object


def panel_class():
    return shipped_module().FleetReplayPanel


def shipped_methods() -> list:
    """Every method the shipped class declares, read off the class object."""
    from PySide6.QtCore import Signal

    return sorted(
        name
        for name, value in vars(panel_class()).items()
        if callable(value)
        and not isinstance(value, Signal)
        and (not name.startswith("__") or name == "__init__")
    )


def shipped_signals() -> list:
    """Every signal the shipped class declares, read off the class object."""
    from PySide6.QtCore import Signal

    return sorted(
        name for name, value in vars(panel_class()).items() if isinstance(value, Signal)
    )


def test_the_shipped_class_declares_the_signals_the_surface_names():
    """The panel gained or lost a signal the surface does not name."""
    assert shipped_signals() == sorted(surface.SIGNALS)
    assert len(shipped_signals()) == SHIPPED_SIGNAL_TOTAL


def test_a_signal_is_not_counted_as_a_method():
    """A signal is callable, so a loose counter reads it as a method."""
    names = shipped_methods()
    assert "fleetLoaded" not in names
    assert "replayStarted" not in names
    assert "replayStopped" not in names
    assert len(names) == SHIPPED_METHOD_TOTAL, names
    assert "__init__" in names


def test_every_shipped_method_has_a_counterpart_on_the_surface():
    """The shipped panel gained or lost a method with nothing standing for it."""
    missing = [
        name
        for name, counterpart in METHOD_COUNTERPARTS.items()
        if counterpart is not None
        and not callable(getattr(surface.FleetReplayPanelModel, counterpart, None))
        and not callable(getattr(surface, counterpart, None))
    ]
    assert missing == [], missing
    assert sorted(METHOD_COUNTERPARTS) == shipped_methods(), sorted(
        set(METHOD_COUNTERPARTS) ^ set(shipped_methods())
    )


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert not callable(getattr(surface.FleetReplayPanelModel, "invented", None))
    assert not callable(getattr(surface, "invented", None))
    assert "invented" not in METHOD_COUNTERPARTS


METHOD_COUNTERPARTS = {
    "__init__": "FleetReplayPanelModel",
    "set_async_loop_getter": None,
    "set_visual_widgets": None,
    "set_log_callbacks": None,
    "set_bot_manager": "set_bot_manager",
    "set_connectors_getter": None,
    "on_history_refreshed": "on_history_refreshed",
    "_on_load_clicked": "load",
    "_spawn_sim_fleet": "spawn",
    "_gate_cell_for": None,
    "sim_bot_statuses": "bot_statuses",
    "emit_bot_table": None,
    "_bot_status_table": None,
    "_populate_fleet_table": "populate_table",
    "_status_error": "status_error",
    "_run_in_flight": "run_in_flight",
    "_confirm_reset": None,
    "_on_reset_clicked": "reset",
    "_on_fetch_ytd_clicked": "fetch_ytd",
    "_on_fetch_ytd_done": "fetch_done",
    "_live_trade_timestamps": "trade_timestamps",
    "_compute_soft_start": None,
    "_on_start_clicked": "start",
    "_collect_stat_fields": "stat_fields",
    "_apply_stat_fields": None,
    "_on_visual_refresh_tick": "visual_refresh_tick",
    "_collect_visual_snapshot": "collect_snapshot",
    "_drain_visual_snapshot": "drain",
    "_on_stop_clicked": "stop",
    "_note_parity_state": "note_parity_state",
    "_refresh_progress": "refresh_progress",
    "_run_parity_comparison": "run_parity_comparison",
    "get_loaded_configs": "loaded_configs",
}


def bare_panel():
    """A panel with nothing wired, for counting what the product itself wires."""
    app()
    return panel_class()()


def product_buttons(panel) -> list:
    """The five buttons the panel builds, in the order the load bar holds them."""
    return [
        panel._load_btn,
        panel._fetch_ytd_btn,
        panel._reset_btn,
        panel._start_btn,
        panel._stop_btn,
    ]


def test_the_panel_wires_one_handler_to_each_button_it_builds():
    """A button the panel builds is connected to nothing, or to two handlers.

    Counted on the running panel and scoped to the buttons the product
    builds. A count taken over the whole widget tree reads the window
    frame's own connections as well.
    """
    panel = bare_panel()
    try:
        counts = [one.receivers("2clicked()") for one in product_buttons(panel)]
        assert counts == [1, 1, 1, 1, 1], counts
        assert sum(counts) == BUTTON_CONNECT_TOTAL
        assert BUTTON_CONNECT_TOTAL == len(
            [name for name in surface.ACTIONS if name.endswith(".clicked")]
        )
    finally:
        panel.setParent(None)
        panel.deleteLater()


def test_a_button_nobody_connected_reads_zero():
    """The connection counter reports one whatever it is pointed at."""
    from PySide6.QtWidgets import QPushButton

    app()
    loose = QPushButton("nothing is wired to this")
    try:
        assert loose.receivers("2clicked()") == 0
        loose.clicked.connect(lambda: None)
        assert loose.receivers("2clicked()") == 1
    finally:
        loose.deleteLater()


def test_the_panel_builds_no_timer_until_a_replay_starts():
    """The panel builds a timer before the operator asks for a run."""
    panel = bare_panel()
    try:
        assert panel._progress_timer is None
        assert panel._drain_timer is None
    finally:
        panel.setParent(None)
        panel.deleteLater()


def test_a_started_replay_runs_two_timers_at_the_declared_rates():
    """The panel polls the run at a different rate than the surface names."""
    spec = dict(BY_NAME["start_scheduled"], name="timer_rates")
    old = drive_old(spec)
    assert old["timer_intervals"] == {
        "progress": surface.PROGRESS_TIMER_MS,
        "drain": surface.DRAIN_TIMER_MS,
    }
    assert old["timers_running"] == {"progress": True, "drain": True}
    assert sorted(surface.TIMERS.values()) == sorted(
        surface.TIMER_DELAYS_MS
    ), surface.TIMERS


def test_the_timer_reader_reports_a_panel_that_never_started():
    """The timer reader reports two running timers whatever was driven."""
    old = drive_old(BY_NAME["idle"])
    assert old["timer_intervals"] == {"progress": None, "drain": None}
    assert old["timers_running"] == {"progress": False, "drain": False}


def test_the_panel_starts_no_thread_and_holds_one_lock():
    """The panel started a worker thread nothing here would ever join."""
    import threading

    before = threading.active_count()
    panel = bare_panel()
    try:
        assert threading.active_count() == before
        assert panel._snapshot_lock is not None
        assert hasattr(panel._snapshot_lock, "acquire")
    finally:
        panel.setParent(None)
        panel.deleteLater()
    assert threading.active_count() == before


def test_the_thread_counter_reports_a_thread_that_really_starts():
    """The thread counter reads the same number whatever is running."""
    import threading

    before = threading.active_count()
    started = threading.Event()
    worker = threading.Thread(target=started.wait, daemon=True)
    worker.start()
    try:
        assert threading.active_count() > before
    finally:
        started.set()
        worker.join(timeout=5)
    assert not worker.is_alive()


def test_the_panel_subscribes_to_no_bus_topic():
    """The panel listens on a topic the surface names none of."""
    panel = bare_panel()
    try:
        assert surface.BUS_TOPICS == ()
        assert not hasattr(panel, "_bus")
        assert not hasattr(panel, "_event_bus")
    finally:
        panel.setParent(None)
        panel.deleteLater()


def test_every_pin_the_panel_emits_is_one_the_surface_names():
    """The panel emits a pin the surface does not name, or misses one."""
    fired = set()
    for spec in SCENARIOS:
        fired.update(row[0] for row in drive_old(spec)["pins"])
    assert fired <= set(surface.PIN_NAMES), sorted(fired - set(surface.PIN_NAMES))
    assert fired, "no pin fired at all, so this check reads nothing"
    assert surface.SPAWN_PIN in fired
    assert surface.GATE_PIN in fired


def test_the_two_sides_emit_the_same_pins_across_every_scenario():
    """One side emits a pin the other does not."""
    for spec in SCENARIOS:
        assert drive_old(spec)["pins"] == drive_new(spec)["pins"], spec["name"]


def test_the_pin_recorder_can_report_a_missing_pin():
    """The pin comparison passes whatever either side emits."""
    one = drive_old(BY_NAME["loaded_fleet"])
    other = drive_old(BY_NAME["empty_fleet"])
    assert len(one["pins"]) > len(other["pins"])


def test_the_panel_carries_a_duration_on_exactly_the_pins_named():
    """A pin gained or lost the time it took, and no comparison saw it."""
    seen = {}
    for spec in (BY_NAME["loaded_fleet"], BY_NAME["fetch_arrived_full"]):
        side = ShippedSide(spec)
        try:
            for index, step in enumerate(spec.get("steps") or []):
                side.step(index, step[0], step[1] if len(step) > 1 else None)
            seen.update(side.pins.durations)
        finally:
            side.close()
    carried = sorted(name for name, has in seen.items() if has)
    assert carried == sorted(surface.PINS_WITH_DURATION), carried
    assert seen, "no pin was recorded, so the duration reader sees nothing"
    assert any(has is False for has in seen.values()), "every pin carried one"


# The completeness check


def surface_constants() -> dict:
    """Every value the surface exports that is not a function or a class."""
    import types

    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


def leaves(value) -> list:
    """Every value inside `value` that holds no other value.

    Dictionary keys are the payload's own naming and are left out:
    what is compared here is the readings, not where they sit.
    """
    if isinstance(value, dict):
        found = []
        for inner in value.values():
            found.extend(leaves(inner))
        return found
    if isinstance(value, (list, tuple, set)):
        found = []
        for inner in value:
            found.extend(leaves(inner))
        return found
    return [value]


def loaded_payload() -> dict:
    """The payload of a panel that has loaded a fleet and taken every step."""
    model = surface.FleetReplayPanelModel(
        loader=surface.FleetLoaderSource(configs=[dict(CHIP), dict(SPK)]),
        registry=surface.TabletRegistrySource(rows_by_asset=TABLET_ROWS),
        controller_factory=lambda **named: surface.ControllerSource(),
    )
    model.load()
    return surface.build_view_model(model)


def test_every_value_the_surface_exports_reaches_the_payload():
    """A value the surface exports reaches no payload the comparison reads."""
    payload = loaded_payload()
    carried = set()
    for one in leaves(payload):
        try:
            carried.add(one)
        except TypeError:
            continue
    unaccounted = []
    for name, value in surface_constants().items():
        if name in NOT_IN_THE_PAYLOAD:
            continue
        for one in leaves(value):
            try:
                if one not in carried:
                    unaccounted.append([name, one])
            except TypeError:
                unaccounted.append([name, repr(one)])
    assert unaccounted == [], unaccounted


NOT_IN_THE_PAYLOAD = {
    "METHOD": "the bridge method name, covered by the bridge tests",
    "ACCESSIBLE_NAME": "model state, compared side by side",
    "NO_STAT_FIELDS": "the empty strip, compared side by side",
    "ModelCall": "the shape one branch marker is recorded in",
    "PANE_MODEL": "the panel the bridge keeps between requests",
}


def test_every_payload_value_traces_to_a_value_the_surface_holds():
    """The payload grew a value nothing on the surface backs."""
    payload = loaded_payload()
    held = set()
    for value in surface_constants().values():
        for one in leaves(value):
            try:
                held.add(one)
            except TypeError:
                continue
    state = set(leaves(STATE_ONLY))
    stray = []
    for one in leaves(payload):
        try:
            if one not in held and one not in state:
                stray.append(one)
        except TypeError:
            stray.append(repr(one))
    assert stray == [], stray


STATE_ONLY = {
    "counts": [0, 1, 2, 3, 4, 250.0, 100.0, 2.0],
    "symbols": ["CHIP/USD", "SPK/USD"],
    "amounts": ["$250.00", "$100.00"],
    "composed": [
        "Loaded 2 bot(s) across 2 symbol(s) \u2014 $350 total target"
        " \u2014 NO bots spawned (no tablets?).",
        "Spawned 0 simulated bot(s) from bot_state (2 symbol(s) with tablets).",
        "simulator_bot_state saved: 0 bot(s); parity green on 0/0.",
    ],
    "flags": [True, False, None],
}


def test_the_completeness_check_can_report_a_value_that_never_arrives():
    """The completeness check passed because it looks at nothing."""
    payload = loaded_payload()
    carried = {one for one in leaves(payload) if isinstance(one, (str, int, float))}
    assert "a value nobody stored" not in carried
    assert surface.TITLE_TEXT in carried
    assert surface.START_BUSY_TEXT in carried
    assert surface.PROGRESS_FORMAT in carried
    assert "INVENTED_CONSTANT" not in surface_constants()


def test_the_payload_key_count_is_the_one_the_comparison_reads():
    """The payload grew or lost a top-level key nothing accounts for."""
    payload = loaded_payload()
    assert len(payload) == PAYLOAD_KEY_TOTAL, sorted(payload)


# The growth check: the file against the module


SURFACE_SOURCE = (
    REPO_ROOT / "src" / "gui" / "main_tabs" / "fleet_replay_panel_surface.py"
)


def names_in_the_file() -> set:
    """Every name the surface file binds at module level."""
    tree = ast.parse(SURFACE_SOURCE.read_text(encoding="utf-8"))
    found = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
    return {one for one in found if not one.startswith("_")}


def imported_names() -> set:
    """Every name the surface file takes from somewhere else."""
    tree = ast.parse(SURFACE_SOURCE.read_text(encoding="utf-8"))
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                found.add(alias.asname or alias.name.split(".")[0])
    return found


def names_on_the_module() -> set:
    """Every name the imported surface carries that it did not import."""
    taken = imported_names()
    return {
        name for name in vars(surface) if not name.startswith("_") and name not in taken
    }


def test_the_file_and_the_module_carry_the_same_names():
    """The surface grew a name in one place and not the other."""
    in_file = names_in_the_file()
    on_module = names_on_the_module()
    assert in_file - on_module == set(), sorted(in_file - on_module)
    assert on_module - in_file == set(), sorted(on_module - in_file)


def test_the_growth_check_can_report_a_name_on_one_side_only():
    """The growth check passes whatever either side carries."""
    in_file = names_in_the_file()
    assert "FleetReplayPanelModel" in in_file
    assert "TITLE_TEXT" in in_file
    assert "a_name_nobody_wrote" not in in_file
    assert "a_name_nobody_wrote" not in names_on_the_module()
    assert len(in_file) > 100, len(in_file)


# The branch markers


def test_every_branch_the_surface_declares_is_taken_by_some_scenario():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for spec in SCENARIOS:
        side = SurfaceSide(spec)
        try:
            for index, step in enumerate(spec.get("steps") or []):
                side.step(index, step[0], step[1] if len(step) > 1 else None)
            seen.update(call[0] for call in side.model.calls)
        finally:
            side.close()
    for extra in EXTRA_BRANCHES:
        seen.update(extra())
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)


def a_refused_history_payload() -> set:
    """The branch a History refresh takes when its payload cannot be listed."""

    class Unlistable:
        def __iter__(self):
            raise TypeError("this payload cannot be listed")

    model = surface.FleetReplayPanelModel()
    model.on_history_refreshed(Unlistable())
    return {call[0] for call in model.calls}


def a_refused_table_refill() -> set:
    """The branch the Sim Trades refill takes when it refuses part way."""
    model = surface.FleetReplayPanelModel()
    model.configs = [dict(CHIP)]
    model.populate_table()
    model.controller = surface.ControllerSource()
    model.refresh_progress(now_s=1.0, refill_raises_at=0)
    return {call[0] for call in model.calls}


def a_refused_spawn() -> set:
    """The branch Load takes when the fleet cannot be spawned."""

    def refuse(**named):
        del named
        raise RuntimeError("the controller could not be built")

    model = surface.FleetReplayPanelModel(
        loader=surface.FleetLoaderSource(configs=[dict(CHIP)]),
        registry=surface.TabletRegistrySource(rows_by_asset=TABLET_ROWS),
        controller_factory=refuse,
    )
    model.load()
    return {call[0] for call in model.calls}


EXTRA_BRANCHES = (
    a_refused_history_payload,
    a_refused_table_refill,
    a_refused_spawn,
)


def test_a_fleet_that_cannot_be_spawned_still_reports_its_bots():
    """A failed spawn hid the fleet the stored state really holds."""

    def refuse(**named):
        del named
        raise RuntimeError("the controller could not be built")

    model = surface.FleetReplayPanelModel(
        loader=surface.FleetLoaderSource(configs=[dict(CHIP), dict(SPK)]),
        registry=surface.TabletRegistrySource(rows_by_asset=TABLET_ROWS),
        controller_factory=refuse,
    )
    model.load()
    assert len(model.rows) == 2
    assert surface.NO_SPAWN_SUFFIX in model.status_text
    assert surface.LOAD_SPAWN_FAILED in [call[0] for call in model.calls]


def test_a_refused_history_payload_keeps_the_trades_it_already_had():
    """A payload that cannot be listed threw away the trades already loaded."""

    class Unlistable:
        def __iter__(self):
            raise TypeError("this payload cannot be listed")

    model = surface.FleetReplayPanelModel()
    model.ytd_trades = [dict(one) for one in LIVE_TRADES]
    model.on_history_refreshed(Unlistable())
    assert len(model.ytd_trades) == len(LIVE_TRADES)
    assert [call[0] for call in model.calls] == [surface.HISTORY_REFUSED]


def test_the_branch_reader_reports_a_branch_nobody_took():
    """The branch reader counts a marker no run ever appended."""
    model = surface.FleetReplayPanelModel()
    assert model.calls == []
    model.status_error("")
    assert model.calls == []
    assert surface.RESET_DECLINED in surface.CALL_NAMES
    assert "a.branch.nobody.wrote" not in surface.CALL_NAMES


# The pictures


PICTURE_CASES = ["empty", "loaded"]


def picture_configs(name) -> list:
    return [] if name == "empty" else [dict(CHIP), dict(SPK), dict(BONK)]


def panel_painted_by_the_panel(name="empty"):
    """The shipped panel, put into one case with no outward edge touched."""
    app()
    panel = panel_class()()
    configs = picture_configs(name)
    if configs:
        panel._configs = configs
        panel._populate_fleet_table()
        panel._note_parity_state()
    return panel


def model_payload(name="empty"):
    """The payload the surface produces for one case, stamped as it comes off."""
    model = surface.FleetReplayPanelModel()
    configs = picture_configs(name)
    if configs:
        model.configs = configs
        model.populate_table()
        model.note_parity_state()
    return sealed(surface.build_view_model(model))


def panel_painted_by_the_model(payload):
    """A panel built only from the payload, laid out as the shipped one is."""
    from PySide6.QtWidgets import (
        QCheckBox,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    from src.gui.simulator_tab.fleet.sim_visuals import GateStatusPanel

    payload = unaltered(payload)
    app()
    panel = QWidget()
    panel.setAccessibleName(payload["accessible_name"])
    gate = GateStatusPanel(panel)

    outer = QVBoxLayout(panel)
    outer.setContentsMargins(*([payload["outer"]["margin_px"]] * 4))
    outer.setSpacing(payload["outer"]["spacing_px"])

    header = QFrame()
    header.setStyleSheet(payload["header"]["style_sheet"])
    header_lay = QVBoxLayout(header)
    title = QLabel(payload["header"]["title"])
    title.setStyleSheet(payload["header"]["title_style"])
    header_lay.addWidget(title)
    subtitle = QLabel(payload["header"]["subtitle"])
    subtitle.setWordWrap(payload["header"]["subtitle_word_wrap"])
    subtitle.setStyleSheet(payload["header"]["subtitle_style"])
    header_lay.addWidget(subtitle)
    outer.addWidget(header)

    load_row = QHBoxLayout()
    for key in ("load", "fetch", "reset"):
        button = QPushButton(payload["buttons"][key]["text"])
        button.setToolTip(payload["buttons"][key]["tooltip"])
        if "enabled" in payload["buttons"][key]:
            button.setEnabled(payload["buttons"][key]["enabled"])
        load_row.addWidget(button)
    check = QCheckBox(payload["full_evaluation"]["text"])
    check.setChecked(payload["full_evaluation"]["checked"])
    check.setToolTip(payload["full_evaluation"]["tooltip"])
    load_row.addWidget(check)
    load_row.addStretch()
    status = QLabel(payload["status"]["text"])
    status.setStyleSheet(payload["status"]["style_sheet"])
    load_row.addWidget(status)
    outer.addLayout(load_row)

    group = QGroupBox(payload["fleet_table"]["title"])
    group_lay = QVBoxLayout(group)
    table = QTableWidget(0, payload["fleet_table"]["column_count"], group)
    table.setToolTip(payload["fleet_table"]["tooltip"])
    table.setHorizontalHeaderLabels(payload["fleet_table"]["columns"])
    table.setAlternatingRowColors(payload["fleet_table"]["alternating_row_colors"])
    table.setEditTriggers(
        getattr(QTableWidget, payload["fleet_table"]["edit_triggers"])
    )
    head = table.horizontalHeader()
    head.setSectionResizeMode(
        getattr(QHeaderView, payload["fleet_table"]["header_resize_mode"])
    )
    head.setStretchLastSection(payload["fleet_table"]["stretch_last_section"])
    table.setRowCount(payload["fleet_table"]["row_count"])
    for row, cells in enumerate(payload["fleet_table"]["rows"]):
        for column, text in enumerate(cells):
            table.setItem(row, column, QTableWidgetItem(text))
    group_lay.addWidget(table)
    outer.addWidget(group, stretch=payload["fleet_table"]["table_stretch"])

    progress = QLabel(payload["progress"]["text"])
    progress.setStyleSheet(payload["progress"]["style_sheet"])
    progress.setWordWrap(payload["progress"]["word_wrap"])
    outer.addWidget(progress)

    run_row = QHBoxLayout()
    run_row.addStretch()
    for key in ("start", "stop"):
        button = QPushButton(payload["buttons"][key]["text"])
        button.setEnabled(payload["buttons"][key]["enabled"])
        button.setToolTip(payload["buttons"][key]["tooltip"])
        run_row.addWidget(button)
    outer.addLayout(run_row)

    gate.set_symbols([row[0] for row in payload["fleet_table"]["rows"] if row[0]])
    panel.header_frame = header
    return panel


def render(widget):
    from tests.qt_pixel import render_widget

    return render_widget(widget, PIXEL_SIZE)


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different picture than the panel it replaces."""
    old_side = render(panel_painted_by_the_panel(name))
    assert_picture_can_report(old_side, note=f"old side, {name}")
    new_side = render(panel_painted_by_the_model(model_payload(name)))
    assert_picture_can_report(new_side, note=f"new side, {name}")
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)


def test_the_picture_comparison_reports_two_different_real_cases():
    """The picture comparison passes whatever the surface painted."""
    assert_cases_paint_differently(
        old_side=render(panel_painted_by_the_panel("empty")),
        new_side=render(panel_painted_by_the_model(model_payload("loaded"))),
        note="an empty panel against a loaded one",
    )


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_painted_panel_shows_more_than_one_colour(name):
    """A render painted one colour, so no comparison of it can report."""
    old_side = render(panel_painted_by_the_panel(name))
    new_side = render(panel_painted_by_the_model(model_payload(name)))
    assert assert_picture_can_report(old_side, note=name) >= 2
    assert colour_count(old_side) == colour_count(new_side), name


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, so the render measures the test."""
    payload = model_payload("loaded")
    payload["status"]["text"] = "a line nobody wrote"
    with pytest.raises(AssertionError):
        panel_painted_by_the_model(payload)


SKIN_RULES = [
    "QGroupBox { background: #3a1414; }",
    "QTableWidget { background: #3a1414; }",
    "QPushButton { background: #3a1414; }",
    "QCheckBox { background: #3a1414; }",
]


def rule_moves_a_pixel(rule) -> bool:
    """Whether one style rule changes what the new side paints."""
    from tests.fixtures.surface_pictures import _picture_digest

    plain = render(panel_painted_by_the_model(model_payload("loaded")))
    skinned_panel = panel_painted_by_the_model(model_payload("loaded"))
    skinned_panel.setStyleSheet(rule)
    return _picture_digest(plain) != _picture_digest(render(skinned_panel))


def test_at_least_one_style_rule_moves_a_pixel_on_this_panel():
    """No style rule reaches a pixel here, so a skin check cannot report."""
    moved = [rule for rule in SKIN_RULES if rule_moves_a_pixel(rule)]
    assert moved, (
        "no rule in "
        f"{SKIN_RULES} changed the render, so a skin comparison on this "
        "panel would pass whatever either side carried"
    )
    assert SKIN_CONTROL_RULE in moved, moved


SKIN_CONTROL_RULE = "QGroupBox { background: #3a1414; }"


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_carry_one_skin(name):
    """One side carries a skin the other does not."""
    assert_same_skin(
        build_old_side=lambda: panel_painted_by_the_panel(name),
        build_new_side=lambda: panel_painted_by_the_model(model_payload(name)),
        size=PIXEL_SIZE,
        control_rule=SKIN_CONTROL_RULE,
        note=name,
    )


# The bridge


@pytest.fixture()
def fresh_pane_model():
    """The bridge keeps one panel between requests; each test gets its own."""
    before = surface.PANE_MODEL
    surface.PANE_MODEL = surface.FleetReplayPanelModel()
    yield
    surface.PANE_MODEL = before


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps(
            {"id": request_id, "method": surface.METHOD, "params": params},
        ),
        desktop_bridge.build_registry(),
    )


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_registers_the_fleet_replay_method():
    """The frontend cannot reach the Fleet Replay panel."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer(
        {"reset": True, "fleet": [dict(CHIP), dict(SPK)], "steps": ["load"]}
    )
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["fleet_table"]["row_count"] == 2
    assert encoded["result"]["fleet_table"]["rows"][0] == [
        "CHIP/USD",
        "$250.00",
        "0",
    ]


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_resets_the_panel_state_on_request():
    """The panel keeps a stale fleet into the next fresh paint."""
    bridge_answer({"reset": True, "fleet": [dict(CHIP)], "steps": ["load"]})
    again = bridge_answer({"reset": True})
    assert again["result"]["fleet_table"]["row_count"] == 0
    assert again["result"]["status"]["text"] == surface.IDLE_STATUS_TEXT


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_takes_the_steps_the_request_names():
    """A step named in the request is not taken."""
    answer = bridge_answer(
        {"reset": True, "fleet": [dict(CHIP), dict(SPK)], "steps": ["load", "reset"]}
    )
    assert answer["result"]["steps"] == ["load", "reset"]
    assert answer["result"]["status"]["text"] == surface.CLEARED_STATUS_TEXT


BRIDGE_PROBE = """
import json, sys, time, threading, builtins

import src.gui.main_tabs

qt_before = [n for n in sys.modules if n.startswith("PySide6")]

CLOCK = []
OPENED = []
STARTED = []
real_time, real_monotonic = time.time, time.monotonic
real_open, real_start = builtins.open, threading.Thread.start
time.time = lambda: CLOCK.append("time") or real_time()
time.monotonic = lambda: CLOCK.append("monotonic") or real_monotonic()


def watched_open(*a, **k):
    OPENED.append(a[0] if a else "")
    return real_open(*a, **k)


def watched_start(self, *a, **k):
    STARTED.append(type(self).__name__)
    return real_start(self, *a, **k)


builtins.open = watched_open
threading.Thread.start = watched_start
PLANT
from src.gui.main_tabs import fleet_replay_panel_surface

qt_after = [n for n in sys.modules if n.startswith("PySide6")]
time.time, time.monotonic = real_time, real_monotonic
builtins.open, threading.Thread.start = real_open, real_start
from src.core import desktop_bridge

frame = desktop_bridge.handle_line(
    json.dumps(
        {
            "id": 1,
            "method": "fleet_replay_panel.state",
            "params": {
                "reset": True,
                "fleet": [
                    {
                        "symbol": "CHIP/USD",
                        "exchange_id": "coinbase",
                        "target_balance": 250.0,
                    }
                ],
                "steps": ["load"],
            },
        }
    ),
    desktop_bridge.build_registry(),
)
print(
    json.dumps(
        {
            "frame": frame,
            "qt": bool([n for n in sys.modules if n.startswith("PySide6")]),
            "qt_before": bool(qt_before),
            "qt_at_import": bool(qt_after),
            "clock": len(CLOCK),
            "opened": len(OPENED),
            "threads": len(STARTED),
        }
    )
)
"""


def run_probe(tmp_path, plant="", environment=None):
    """Run the import probe in its own process and read what it counted."""
    del tmp_path
    running = dict(os.environ)
    running.pop("QT_QPA_PLATFORM", None)
    running.update(environment or {})
    done = subprocess.run(
        [sys.executable, "-"],
        input=BRIDGE_PROBE.replace("PLANT", plant).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=running,
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    return json.loads(done.stdout.decode(errors="replace").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt(tmp_path):
    """Reaching the Fleet Replay panel pulled Qt into the backend."""
    answered = run_probe(tmp_path)
    assert answered["qt"] is False
    assert answered["qt_before"] is False
    assert answered["qt_at_import"] is False
    assert answered["frame"]["ok"] is True
    assert answered["frame"]["result"]["fleet_table"]["rows"] == [
        ["CHIP/USD", "$250.00", "0"]
    ]


def test_the_surface_reads_no_clock_no_file_and_starts_no_thread_at_import(tmp_path):
    """Importing the panel's surface touched the world.

    Counted from the moment the package chain is already loaded:
    importing the ``src`` package itself runs git in another
    process, which is a property of that package, not of this file.
    """
    answered = run_probe(tmp_path)
    assert answered["clock"] == 0, "the import read the clock"
    assert answered["opened"] == 0, "the import opened a file"
    assert answered["threads"] == 0, "the import started a thread"


def test_the_import_probe_reports_a_planted_read(tmp_path):
    """The probe counts nothing whatever the import does."""
    planted = run_probe(
        tmp_path,
        plant=(
            "time.time()\n"
            "open(sys.executable, 'rb').close()\n"
            "threading.Thread(target=lambda: None).start()\n"
        ),
    )
    assert planted["clock"] >= 1, "the clock counter is blind"
    assert planted["opened"] >= 1, "the file counter is blind"
    assert planted["threads"] >= 1, "the thread counter is blind"


def test_the_qt_probe_reports_qt_when_it_is_loaded(tmp_path):
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe(tmp_path, plant="import PySide6.QtCore\n")
    assert loaded["qt"] is True
    assert loaded["qt_before"] is False
    assert loaded["qt_at_import"] is True
    assert loaded["frame"]["ok"] is True


# The throwaway home


def files_under(root) -> list:
    return sorted(
        str(one.relative_to(root)) for one in root.rglob("*") if one.is_file()
    )


def test_answering_over_the_bridge_writes_nothing_into_the_home(tmp_path):
    """The surface wrote into the operator's home directory."""
    home = tmp_path / "home"
    home.mkdir()
    answered = run_probe(
        tmp_path,
        environment={
            "ACERVATOR_TEST_HOME": str(home),
            "HOME": str(home),
            "USERPROFILE": str(home),
        },
    )
    assert answered["frame"]["ok"] is True
    assert files_under(home) == [], files_under(home)


def test_the_home_counter_reports_a_planted_file(tmp_path):
    """The home counter reports nothing whatever the run wrote."""
    home = tmp_path / "home"
    home.mkdir()
    run_probe(
        tmp_path,
        plant=(
            "import os, pathlib\n"
            "pathlib.Path(os.environ['ACERVATOR_TEST_HOME'], 'planted.txt')"
            ".write_text('x', encoding='utf-8')\n"
        ),
        environment={
            "ACERVATOR_TEST_HOME": str(home),
            "HOME": str(home),
            "USERPROFILE": str(home),
        },
    )
    assert files_under(home) == ["planted.txt"]


# Shared state: what each side swaps, and that it goes back


def test_a_drive_swaps_shared_values_and_puts_every_one_back():
    """A drive left a shared value pointing at the test's stand-in."""
    spec = BY_NAME["loaded_fleet"]
    side = ShippedSide(spec)
    try:
        assert side.swaps.taken, "the drive swapped nothing, so this reads nothing"
        during = side.swaps.live()
        before = side.swaps.original()
        assert during != before, "no swap actually took"
        assert not side.swaps.restored(), "a swap was already back before the drive"
        side.step(0, "load")
    finally:
        side.close()
    assert side.swaps.restored(), "a swapped value was left pointing at a stand-in"


def test_a_drive_that_refuses_part_way_still_puts_every_swap_back():
    """A refusal left a shared value pointing at the test's stand-in."""
    spec = dict(BY_NAME["load_refused"], name="refused_and_restored")
    side = ShippedSide(spec)
    try:
        side.step(0, "load")
        assert "ValueError" in side.panel._status_lbl.text()
    finally:
        side.close()
    assert side.swaps.restored()


def test_the_swap_reader_reports_a_value_left_behind():
    """The swap reader says restored whatever the holder now carries."""
    holder = SwapTarget()
    swaps = Swaps()
    swaps.put(holder, "value", "a stand-in")
    assert not swaps.restored()
    assert swaps.live() == ["a stand-in"]
    swaps.restore()
    assert swaps.restored()
    assert holder.value == "the real one"


def test_the_swap_reader_refuses_a_name_the_holder_does_not_carry():
    """A swap on a missing name creates a fresh value and resets nothing."""
    holder = SwapTarget()
    swaps = Swaps()
    with pytest.raises(AttributeError):
        swaps.put(holder, "a_name_nobody_wrote", "x")
    assert not hasattr(holder, "a_name_nobody_wrote")


class SwapTarget:
    """A holder with one value, for proving the swap reader can report."""

    def __init__(self):
        self.value = "the real one"


def test_the_shipped_panel_writes_to_no_shared_table():
    """The panel changed something every later test would inherit."""
    panel_module = shipped_module()
    before = sorted(vars(panel_module))
    drive_old(BY_NAME["loaded_fleet"])
    drive_old(BY_NAME["start_scheduled"])
    assert sorted(vars(panel_module)) == before
    assert panel_module._HAS_QT is True


def test_the_surface_writes_to_no_shared_table_but_the_bridge_panel():
    """The surface changed a module value a later request would inherit."""
    before = sorted(vars(surface))
    kept = surface.PANE_MODEL
    drive_new(BY_NAME["loaded_fleet"])
    drive_new(BY_NAME["start_scheduled"])
    assert sorted(vars(surface)) == before
    assert surface.PANE_MODEL is kept


def no_candles(*ignored, **named):
    """The panel's own candle maker, moved, so a follower would follow it."""
    del ignored, named
    return []


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_panel():
    """The surface read its values off the panel it replaces."""
    panel_module = shipped_module()
    first = panel_module._synthesize_candles_for_symbol
    before = surface.synthesize_candles("CHIP/USD", n_candles=3)
    swaps = Swaps()
    swaps.put(panel_module, "_synthesize_candles_for_symbol", no_candles)
    try:
        assert panel_module._synthesize_candles_for_symbol("CHIP/USD") == []
        assert surface.synthesize_candles("CHIP/USD", n_candles=3) == before
    finally:
        swaps.restore()
    assert panel_module._synthesize_candles_for_symbol is first


@pytest.mark.parametrize("symbol", ["CHIP/USD", "SPK/USD", "", "€é中"])
def test_the_synthetic_candles_match_the_panels_own(symbol):
    """The fallback candles the panel draws differ from the surface's."""
    panel_module = shipped_module()
    old = panel_module._synthesize_candles_for_symbol(symbol, n_candles=5)
    new = surface.synthesize_candles(symbol, n_candles=5)
    assert new == old, symbol
    assert digest(new) == digest(old), symbol


def test_the_synthetic_candle_check_tells_two_symbols_apart():
    """The candle comparison passes whatever symbol it is handed."""
    assert surface.synthesize_candles("CHIP/USD", n_candles=5) != (
        surface.synthesize_candles("SPK/USD", n_candles=5)
    )


# The bare-reading audit: what a stored value nobody checked does


HOSTILE = [
    ("a stored yes", True),
    ("not a number", float("nan")),
    ("infinity", float("inf")),
    ("minus infinity", float("-inf")),
    ("text", "not a number at all"),
    ("a number written as text", "12.7"),
    ("a plain decimal", 12.7),
    ("a thousand million", 1_000_000_000.0),
    ("one billionth", 1e-9),
    ("zero", 0.0),
    ("negative", -42.5),
    ("two to the 1023", 2.0**1023),
    ("ten to the 400", 10**400),
    ("an apostrophe", "it's"),
    ("markup", "<b>250</b>"),
    ("wrong capitals", "TwElVe"),
    ("a newline", "12\n7"),
    ("two hundred letters", "9" * 200),
    ("unicode", "€é中"),
]

HOSTILE_NAMES = [one[0] for one in HOSTILE]
BY_HOSTILE = dict(HOSTILE)


def target_reading(value):
    """What the fleet table draws for one stored dollar target."""
    app()
    panel = panel_class()()
    try:
        panel._configs = [dict(CHIP, target_balance=value)]
        panel._populate_fleet_table()
        item = panel._fleet_table.item(0, surface.TARGET_COLUMN)
        return [
            "drew",
            None if item is None else item.text(),
            panel._fleet_table.rowCount(),
        ]
    except Exception as exc:
        return ["refused", type(exc).__name__, panel._fleet_table.rowCount()]
    finally:
        panel.setParent(None)
        panel.deleteLater()


def surface_target_reading(value):
    """What the surface says the fleet table draws for the same target."""
    model = surface.FleetReplayPanelModel()
    try:
        model.configs = [dict(CHIP, target_balance=value)]
        model.populate_table()
        return ["drew", model.rows[0][surface.TARGET_COLUMN], len(model.rows)]
    except Exception as exc:
        return ["refused", type(exc).__name__, len(model.rows)]


def holdings_reading(value):
    """What the header strip shows when a bot's holdings hold one value."""
    app()
    panel = panel_class()()
    try:
        bot = Bot(config=BotConfig(symbol="CHIP/USD"), holdings=value, last_price=2.0)
        fields = panel._collect_stat_fields([bot], Tape(balances={"USD": 1.0}))
        return ["drew", fields.get("Locked"), len(fields)]
    except Exception as exc:
        return ["refused", type(exc).__name__, 0]
    finally:
        panel.setParent(None)
        panel.deleteLater()


def surface_holdings_reading(value):
    """What the surface says the strip shows for the same holdings."""
    bot = surface.BotSource(
        config=surface.BotConfigSource(symbol="CHIP/USD"),
        holdings=value,
        last_price=2.0,
    )
    try:
        fields = surface.stat_fields(
            [bot], surface.TapeSource(balances={"USD": 1.0}), 0
        )
        return ["drew", fields.get("Locked"), len(fields)]
    except Exception as exc:
        return ["refused", type(exc).__name__, 0]


READINGS = {
    "target usd in the fleet table": [target_reading, surface_target_reading],
    "holdings in the header strip": [holdings_reading, surface_holdings_reading],
}


@pytest.mark.parametrize("reading", sorted(READINGS))
@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_a_stored_value_reads_the_same_on_both_sides(reading, name):
    """One side survives a stored value the other refuses."""
    old_reader, new_reader = READINGS[reading]
    value = BY_HOSTILE[name]
    old = old_reader(value)
    new = new_reader(value)
    assert new == old, (reading, name, old, new)


def test_a_stored_yes_becomes_a_dollar_nobody_asked_for():
    """A stored yes is refused, so this reading needs no guard."""
    assert target_reading(True) == ["drew", "$1.00", 1]
    assert surface_target_reading(True) == ["drew", "$1.00", 1]


def test_a_stored_not_a_number_paints_a_target_of_nan():
    """A stored not-a-number is refused before it reaches the table."""
    assert target_reading(float("nan")) == ["drew", "$nan", 1]


def test_a_stored_number_written_as_text_is_taken_as_a_number():
    """A stored number written as text is refused by the table."""
    assert target_reading("12.7") == ["drew", "$12.70", 1]


def test_a_stored_word_stops_the_whole_fleet_table():
    """Text where a number belongs is caught, so only its row is lost."""
    outcome = target_reading("not a number at all")
    assert outcome[0] == "refused"
    assert outcome[1] == "ValueError"
    assert outcome[2] == 1, "the table kept a row it never filled"


def test_a_stored_integer_too_big_for_a_decimal_stops_the_fleet_table():
    """An oversized stored integer is caught before it reaches the table."""
    outcome = target_reading(10**400)
    assert outcome[0] == "refused"
    assert outcome[1] == "OverflowError"


def test_the_reading_audit_can_report_a_value_that_passes_untouched():
    """The audit calls every reading a refusal, so it reports nothing."""
    assert target_reading(250.0) == ["drew", "$250.00", 1]
    assert holdings_reading(3.0) == ["drew", "$6.00", 10]


def test_a_refused_target_loses_every_row_not_only_its_own():
    """A refused target lost only the row that carried it."""
    app()
    panel = panel_class()()
    try:
        panel._configs = [dict(CHIP), dict(SPK, target_balance="not a number")]
        with pytest.raises(ValueError):
            panel._populate_fleet_table()
        drawn = [
            panel._fleet_table.item(row, surface.TARGET_COLUMN)
            for row in range(panel._fleet_table.rowCount())
        ]
        assert drawn[0] is not None and drawn[0].text() == "$250.00"
        assert drawn[1] is None, "the refused row was filled after all"
        assert panel._fleet_table.rowCount() == 2
    finally:
        panel.setParent(None)
        panel.deleteLater()


def test_a_wrong_style_on_the_surface_reaches_the_picture():
    """A style the surface declares wrongly is invisible to the pictures.

    Nothing here reads a style off a live widget. The new side is built
    from the payload, so a changed style paints a different picture.
    """
    from tests.fixtures.surface_pictures import _picture_digest

    plain = render(panel_painted_by_the_model(model_payload("loaded")))
    moved = panel_painted_by_the_model(model_payload("loaded"))
    moved.header_frame.setStyleSheet("QFrame{background:#5a1414;}")
    assert _picture_digest(plain) != _picture_digest(
        render(moved)
    ), "the header style reaches no pixel, so the picture cannot report it"
