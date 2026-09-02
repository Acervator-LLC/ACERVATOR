"""The Qt Nuclear Mode panel and the Qt-free surface, side by side.

A failure means the view model describes a different fleet preview, a
different run setting, a different activity message, a different status
row, a different colour, a different screen or a different refusal than
``NuclearModePanel`` produces on the same world.

No test here reads bot_state, builds a real controller, schedules a
coroutine, starts a thread or reads the wall clock. What bot_state
answered, whether an event loop exists, what the controller did when
built, prepared, scheduled and asked for a snapshot, and what the swarm
and the Market Inspector answered are all handed in: one spec builds two
independent worlds, and no object crosses between them.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time as clock_module
import datetime as datetime_module
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import nuclear_mode_panel_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_same_skin,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SOURCE = REPO_ROOT / "src" / "gui" / "simulator_tab" / "nuclear_mode_panel.py"
SURFACE_SOURCE = (
    REPO_ROOT / "src" / "gui" / "main_tabs" / "nuclear_mode_panel_surface.py"
)

WIRING_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_SAME_NAME_A = REPO_ROOT / "src" / "gui" / "history_tab.py"
TIMER_SAME_NAME_B = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
TIMER_UNBUILT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "indicator_panel.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
ELEMENT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"
NESTED_CLASS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "stock_main_window.py"
THREAD_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "live_bot_window.py"

WIRING_NEIGHBOUR_CONNECT_TOTAL = 1
SIGNAL_NEIGHBOUR_SIGNAL_TOTAL = 3
TIMER_SAME_NAME_A_BUILD_TOTAL = 1
TIMER_NEIGHBOUR_UNBUILT_TOTAL = 5
BUS_NEIGHBOUR_SUBSCRIBE_TOTAL = 2
BUS_NEIGHBOUR_EMIT_TOTAL = 5
ELEMENT_NEIGHBOUR_BUILD_TOTAL = 3
THREAD_NEIGHBOUR_BUILD_TOTAL = 1
THREAD_NEIGHBOUR_START_TOTAL = 1

PIXEL_SIZE = (620, 640)
MISSING = object()


# ---------------------------------------------------------------------
# Reading a value the same way on both sides
# ---------------------------------------------------------------------


def as_text(value):
    """`value` with every number written as its own text.

    ``12`` and ``12.0`` are one value to a comparison and two different
    numbers to a reader, and two not-a-numbers are never equal to each
    other. Both are settled here before anything is compared.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, dict):
        return {key: as_text(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_text(inner) for inner in value]
    return value


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(
            as_text(value), sort_keys=True, ensure_ascii=True, default=repr
        ).encode("utf-8")
    ).hexdigest()


def app():
    """The one application object every render is taken against.

    The run's font choice is applied here, so every render in this file
    is taken against the fonts the run asked for rather than whatever
    the host happens to ship.
    """
    from tests.qt_pixel import ensure_app

    found = ensure_app()
    load_run_fonts()
    return found


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


# ---------------------------------------------------------------------
# The world one spec describes
# ---------------------------------------------------------------------


class Summary:
    """One indicator-voting summary, as the controller hands it over."""

    def __init__(self, timeframe="15m"):
        self.timeframe = timeframe
        self.bullish_count = 4
        self.bearish_count = 1
        self.neutral_count = 2
        self.net_score = 3
        self.consensus_confidence = 0.62
        self.consensus_direction = Direction("BULLISH")
        self.signals = [Vote("RSI", "BULLISH", 0.8), Vote("MACD", "BEARISH", 0.3)]


class Direction:
    """A consensus direction, which the panel reads by its name."""

    def __init__(self, name):
        self.name = name


class Vote:
    """One indicator's vote inside a summary."""

    def __init__(self, indicator, direction, confidence):
        self.indicator = indicator
        self.direction = Direction(direction)
        self.confidence = confidence


class Swarm:
    """The Simulator Swarm, offering the three hooks by name.

    A hook that is CALLED writes down what it was handed and refuses.
    The panel is only supposed to name these and pass them on, so a call
    is a misuse and says so rather than passing quietly.
    """

    def __init__(self):
        self.calls: list = []

    def _refuse(self, hook, handed):
        self.calls.append((hook, handed))
        raise AssertionError(f"a drive called {hook} instead of naming it")

    def register_sim_run(self, sim_id, label, cfg):
        self._refuse("register_sim_run", (sim_id, label, cfg))

    def update_sim_run(self, sim_id, pnl, trades, candle_idx):
        self._refuse("update_sim_run", (sim_id, pnl, trades, candle_idx))

    def stop_sim_run(self, sim_id, pnl, trades):
        self._refuse("stop_sim_run", (sim_id, pnl, trades))


class HalfSwarm:
    """A swarm offering only the first of the three hooks."""

    def __init__(self):
        self.calls: list = []

    def register_sim_run(self, sim_id, label, cfg):
        self.calls.append(("register_sim_run", (sim_id, label, cfg)))
        raise AssertionError("a drive called register_sim_run instead of naming it")


class Spec:
    """One world, described once and built twice."""

    def __init__(
        self,
        name,
        configs=(),
        wires=(),
        loader_error=None,
        has_loop=True,
        loop_error=None,
        build_error=None,
        prepare_result=True,
        prepare_error=None,
        schedule_error=None,
        runs_immediately=False,
        snapshots=(),
        swarm_kind=None,
        swarm_error=None,
        topologies=None,
        topology_error=None,
        has_swarm_getter=False,
        has_topology_getter=False,
        with_visuals=False,
        cycle_candles=None,
        max_cycles=None,
        noise_enabled=None,
        load_oscillation=None,
        steps=("start", "refresh_status"),
    ):
        self.name = name
        self.configs = list(configs)
        self.wires = list(wires)
        self.loader_error = loader_error
        self.has_loop = has_loop
        self.loop_error = loop_error
        self.build_error = build_error
        self.prepare_result = prepare_result
        self.prepare_error = prepare_error
        self.schedule_error = schedule_error
        self.runs_immediately = runs_immediately
        self.snapshots = list(snapshots)
        self.swarm_kind = swarm_kind
        self.swarm_error = swarm_error
        self.topologies = topologies
        self.topology_error = topology_error
        self.has_swarm_getter = has_swarm_getter
        self.has_topology_getter = has_topology_getter
        self.with_visuals = with_visuals
        self.cycle_candles = cycle_candles
        self.max_cycles = max_cycles
        self.noise_enabled = noise_enabled
        self.load_oscillation = load_oscillation
        self.steps = tuple(steps)


BOTS = [
    {"symbol": "BTC-USD", "bot_id": "one"},
    {"symbol": "ETH-USD", "bot_id": "two"},
    {"symbol": "BTC-USD", "bot_id": "three"},
]
WIRES = [{"a": 1}, {"b": 2}]

FULL_SNAPSHOT = {
    "running": True,
    "uptime_seconds": 42.5,
    "fleet_size": 3,
    "symbols": ["BTC-USD", "ETH-USD"],
    "wires_loaded": 2,
    "current_cycle": 7,
    "cycles_completed": 6,
    "noise_pct": 0.175,
    "load_multiplier": 2.25,
    "cooling": False,
    "load_sensed": True,
    "total_candles": 21000,
    "total_trades": 1408,
    "total_exceptions": 0,
    "failed_cycles": 1,
    "last_error": "",
}

STOPPED_SNAPSHOT = dict(FULL_SNAPSHOT, running=False, uptime_seconds=100.0)
ERRORED_SNAPSHOT = dict(
    FULL_SNAPSHOT, total_exceptions=3, last_error="ZeroDivisionError: division"
)
VISUAL_SNAPSHOT = dict(
    FULL_SNAPSHOT,
    symbol="BTC-USD",
    last_price=64000.5,
    last_volume=12.5,
    voting_summary=Summary(),
)

SPECS = [
    Spec("happy", BOTS, WIRES, snapshots=[FULL_SNAPSHOT]),
    Spec("no_run", BOTS, WIRES, snapshots=[FULL_SNAPSHOT], steps=()),
    Spec("part_way", BOTS, WIRES, snapshots=[FULL_SNAPSHOT], steps=("start",)),
    Spec(
        "finished",
        BOTS,
        WIRES,
        snapshots=[FULL_SNAPSHOT, STOPPED_SNAPSHOT],
        steps=("start", "refresh_status", "stop"),
    ),
    Spec("empty_fleet", (), (), snapshots=[FULL_SNAPSHOT]),
    Spec("loader_refuses", BOTS, WIRES, loader_error=RuntimeError("bot_state gone")),
    Spec("no_loop", BOTS, WIRES, has_loop=False),
    Spec("loop_getter_refuses", BOTS, WIRES, loop_error=LookupError("no loop yet")),
    Spec("build_refuses", BOTS, WIRES, build_error=ValueError("bad cycle length")),
    Spec("prepare_refuses", BOTS, WIRES, prepare_error=OSError("tablets missing")),
    Spec("prepare_says_no", BOTS, WIRES, prepare_result=False),
    Spec("schedule_refuses", BOTS, WIRES, schedule_error=RuntimeError("loop closed")),
    Spec(
        "with_swarm",
        BOTS,
        WIRES,
        swarm_kind="full",
        has_swarm_getter=True,
        snapshots=[FULL_SNAPSHOT],
    ),
    Spec("half_swarm", BOTS, WIRES, swarm_kind="half", has_swarm_getter=True),
    Spec("swarm_is_none", BOTS, WIRES, has_swarm_getter=True),
    Spec(
        "swarm_getter_refuses",
        BOTS,
        WIRES,
        swarm_error=AttributeError("no swarm tab"),
        has_swarm_getter=True,
    ),
    Spec(
        "topologies_injected",
        BOTS,
        WIRES,
        topologies=[{"pair": 1}, {"pair": 2}],
        has_topology_getter=True,
    ),
    Spec("topologies_empty", BOTS, WIRES, topologies=[], has_topology_getter=True),
    Spec(
        "topology_getter_refuses",
        BOTS,
        WIRES,
        topology_error=TypeError("proposal shape"),
        has_topology_getter=True,
    ),
    Spec(
        "snapshot_refuses",
        BOTS,
        WIRES,
        snapshots=[KeyError("state")],
    ),
    Spec("errored_run", BOTS, WIRES, snapshots=[ERRORED_SNAPSHOT]),
    Spec("visuals", BOTS, WIRES, snapshots=[VISUAL_SNAPSHOT], with_visuals=True),
    Spec(
        "visuals_without_symbol",
        BOTS,
        WIRES,
        snapshots=[FULL_SNAPSHOT],
        with_visuals=True,
    ),
    Spec(
        "settings_changed",
        BOTS,
        WIRES,
        cycle_candles=12_000,
        max_cycles=25,
        noise_enabled=False,
        load_oscillation=False,
        snapshots=[FULL_SNAPSHOT],
    ),
    Spec(
        "restart_before_the_loop_took_it",
        BOTS,
        WIRES,
        snapshots=[FULL_SNAPSHOT],
        steps=("start", "start", "refresh_status"),
    ),
    Spec(
        "restart_after_it_began",
        BOTS,
        WIRES,
        snapshots=[FULL_SNAPSHOT],
        runs_immediately=True,
        steps=("start", "start", "refresh_status"),
    ),
    Spec(
        "reload_after_stop",
        BOTS,
        WIRES,
        snapshots=[FULL_SNAPSHOT, STOPPED_SNAPSHOT],
        steps=("start", "stop", "rescan_fleet"),
    ),
]

SWARM_KINDS = {"full": Swarm, "half": HalfSwarm}

BY_NAME = {spec.name: spec for spec in SPECS}
SPEC_NAMES = [spec.name for spec in SPECS]


# ---------------------------------------------------------------------
# The shipped side
# ---------------------------------------------------------------------


def shipped_module():
    from src.gui.simulator_tab import nuclear_mode_panel as shipped

    return shipped


def loader_module():
    from src.simulator.fleet import bot_state_loader as loader

    return loader


class ModuleAttributeSwap:
    """Give one module its own edges for one drive, then put them back."""

    def __init__(self, module, **edges):
        self.module = module
        self.edges = edges
        self.held = {}

    def __enter__(self):
        for name, value in self.edges.items():
            self.held[name] = getattr(self.module, name)
            setattr(self.module, name, value)
        return self

    def __exit__(self, *_unused):
        for name, held in self.held.items():
            setattr(self.module, name, held)
        return False


class Recorder:
    """The one world the shipped panel is driven against.

    Every edge the panel reaches for answers from here, and every answer
    is written down so the drive can be compared value for value with the
    surface's own world.
    """

    def __init__(self, spec: Spec):
        self.spec = spec
        self.loop = object() if spec.has_loop else None
        self.activity: list = []
        self.performance: list = []
        self.built_runs: list = []
        self.callbacks_seen: list = []
        self.swarm_hooks_set: list = []
        self.topologies_set: list = []
        self.scheduled = 0
        self.stops = 0
        self.snapshot_calls = 0
        self.loader_calls = 0
        self.chart_ticks: list = []
        self.voting_updates: list = []
        self.misuses: list = []

    def load_bot_configs_from_state(self):
        self.loader_calls += 1
        if self.spec.loader_error is not None:
            raise self.spec.loader_error
        return list(self.spec.configs)

    def load_smart_wires_from_state(self):
        if self.spec.loader_error is not None:
            raise self.spec.loader_error
        return list(self.spec.wires)

    def event_loop(self):
        if self.spec.loop_error is not None:
            raise self.spec.loop_error
        return self.loop

    def resolve_swarm(self):
        if self.spec.swarm_error is not None:
            raise self.spec.swarm_error
        return SWARM_KINDS[self.spec.swarm_kind]() if self.spec.swarm_kind else None

    def resolve_topologies(self):
        if self.spec.topology_error is not None:
            raise self.spec.topology_error
        return self.spec.topologies

    def next_snapshot(self):
        answers = self.spec.snapshots
        if not answers:
            answer = {}
        elif self.snapshot_calls < len(answers):
            answer = answers[self.snapshot_calls]
        else:
            answer = answers[-1]
        self.snapshot_calls += 1
        if isinstance(answer, BaseException):
            raise answer
        return answer


class AttachedPanel:
    """A shared Simulator panel the surface only asks the presence of."""


class ChartRecorder:
    """The shared price chart, writing down every tick it is handed."""

    def __init__(self, recorder: Recorder):
        self.recorder = recorder

    def append_tick(self, symbol, close_price, volume):
        self.recorder.chart_ticks.append((symbol, close_price, volume))

    def update(self):
        return None


class VotingRecorder:
    """The shared voting readout, writing down every feed it is handed."""

    def __init__(self, recorder: Recorder):
        self.recorder = recorder

    def update_data(self, payload, symbol):
        self.recorder.voting_updates.append((payload, symbol))


class ShippedRun:
    """A stand-in Nuclear controller. Records what it is asked, runs none.

    The keyword names are written out, so a panel that calls the
    controller differently refuses here and the refusal reaches the
    compared trace rather than passing quietly.
    """

    def __init__(
        self,
        recorder: Recorder,
        *,
        cycle_candles,
        activity_cb,
        perf_cb,
        max_cycles,
        load_oscillation,
        noise_enabled,
    ):
        if recorder.spec.build_error is not None:
            raise recorder.spec.build_error
        self.recorder = recorder
        self.running = False
        recorder.built_runs.append(
            {
                "cycle_candles": cycle_candles,
                "max_cycles": max_cycles,
                "load_oscillation": load_oscillation,
                "noise_enabled": noise_enabled,
            }
        )
        recorder.callbacks_seen.append((callable(activity_cb), callable(perf_cb)))

    def is_running(self):
        return self.running

    def prepare(self):
        if self.recorder.spec.prepare_error is not None:
            raise self.recorder.spec.prepare_error
        return bool(self.recorder.spec.prepare_result)

    def set_swarm_hooks(self, register=None, update=None, stop=None):
        self.recorder.swarm_hooks_set.append((register, update, stop))

    def set_topologies(self, proposals):
        self.recorder.topologies_set.append(list(proposals))

    def start(self):
        """The awaitable the panel hands the scheduler. Nothing runs."""
        return ("nuclear-start", id(self))

    def stop(self):
        self.recorder.stops += 1
        self.running = False

    def snapshot(self):
        return self.recorder.next_snapshot()


class Scheduler:
    """The asyncio the shipped panel reaches for. It schedules nothing."""

    def __init__(self, recorder: Recorder):
        self.recorder = recorder

    def run_coroutine_threadsafe(self, awaitable, loop):
        if not (isinstance(awaitable, tuple) and awaitable[0] == "nuclear-start"):
            self.recorder.misuses.append(("scheduler", repr(awaitable)))
        if loop is not self.recorder.loop:
            self.recorder.misuses.append(("scheduler loop", repr(loop)))
        if self.recorder.spec.schedule_error is not None:
            raise self.recorder.spec.schedule_error
        self.recorder.scheduled += 1
        held = getattr(self.recorder, "last_run", None)
        if held is not None:
            held.running = bool(self.recorder.spec.runs_immediately)
        return ("scheduled", self.recorder.scheduled)


def controller_factory(recorder: Recorder):
    """The name the shipped panel builds its controller through."""

    def build(**settings):
        run = ShippedRun(recorder, **settings)
        recorder.last_run = run
        return run

    return build


def apply_settings_old(panel, spec: Spec):
    if spec.cycle_candles is not None:
        panel._cycle_candles_spin.setValue(spec.cycle_candles)
    if spec.max_cycles is not None:
        panel._max_cycles_spin.setValue(spec.max_cycles)
    if spec.noise_enabled is not None:
        panel._noise_check.setChecked(spec.noise_enabled)
    if spec.load_oscillation is not None:
        panel._load_osc_check.setChecked(spec.load_oscillation)


OLD_STEPS = {
    "rescan_fleet": lambda panel: panel._rescan_cache(),
    "start": lambda panel: panel._on_start_clicked(),
    "stop": lambda panel: panel._on_stop_clicked(),
    "refresh_status": lambda panel: panel._refresh_status(),
}


def old_state(panel, recorder: Recorder) -> dict:
    """What a reader sees on the shipped panel right now."""
    return {
        "fleet_detail": panel._fleet_detail.text(),
        "empty_text": panel._empty_label.text(),
        "empty_visible": not panel._empty_label.isHidden(),
        "start_enabled": panel._start_btn.isEnabled(),
        "stop_enabled": panel._stop_btn.isEnabled(),
        "reload_enabled": panel._refresh_btn.isEnabled(),
        "control_enabled": {
            "cycle_candles": panel._cycle_candles_spin.isEnabled(),
            "max_cycles": panel._max_cycles_spin.isEnabled(),
            "noise": panel._noise_check.isEnabled(),
            "load_oscillation": panel._load_osc_check.isEnabled(),
        },
        "timer_running": panel._refresh_timer.isActive(),
        "status_text": {key: lbl.text() for key, lbl in panel._status_labels.items()},
        "activity": list(recorder.activity),
    }


def drive_old(spec: Spec) -> dict:
    """Drive the shipped panel once and return everything it did."""
    app()
    shipped = shipped_module()
    loader = loader_module()
    recorder = Recorder(spec)
    with (
        ModuleAttributeSwap(
            shipped,
            NuclearFleetController=controller_factory(recorder),
            asyncio=Scheduler(recorder),
        ),
        ModuleAttributeSwap(
            loader,
            load_bot_configs_from_state=recorder.load_bot_configs_from_state,
            load_smart_wires_from_state=recorder.load_smart_wires_from_state,
        ),
    ):
        panel = shipped.NuclearModePanel(
            activity_log_cb=recorder.activity.append,
            perf_log_cb=recorder.performance.append,
            async_loop_getter=recorder.event_loop,
        )
        try:
            if spec.has_swarm_getter:
                panel.set_swarm_getter(recorder.resolve_swarm)
            if spec.has_topology_getter:
                panel.set_topology_getter(recorder.resolve_topologies)
            if spec.with_visuals:
                panel.set_visual_widgets(
                    price_chart=ChartRecorder(recorder),
                    voting_readout=VotingRecorder(recorder),
                    stat_strip=None,
                )
            apply_settings_old(panel, spec)
            for step in spec.steps:
                OLD_STEPS[step](panel)
            trace = old_state(panel, recorder)
        finally:
            panel._refresh_timer.stop()
    return {"screen": trace, "world": recorded(recorder), "panel": panel}


def recorded(recorder) -> dict:
    """What one drive asked of the world, on either side."""
    return {
        "built_runs": [dict(one) for one in recorder.built_runs],
        "swarm_hooks": [
            [
                None if hook is None else getattr(hook, "__name__", "bound")
                for hook in hooks
            ]
            for hooks in recorder.swarm_hooks_set
        ],
        "topologies_set": [list(one) for one in recorder.topologies_set],
        "scheduled": recorder.scheduled,
        "stops": recorder.stops,
        "snapshot_calls": recorder.snapshot_calls,
        "loader_calls": recorder.loader_calls,
        "chart_ticks": [list(one) for one in recorder.chart_ticks],
        "voting_updates": [
            [payload, symbol] for payload, symbol in recorder.voting_updates
        ],
    }


# ---------------------------------------------------------------------
# The surface side
# ---------------------------------------------------------------------


def new_world(spec: Spec) -> surface.PanelWorld:
    """The surface's own world for `spec`. It shares nothing with the old."""
    return surface.PanelWorld(
        bot_configs=spec.configs,
        smart_wires=spec.wires,
        loader_error=spec.loader_error,
        loop=object() if spec.has_loop else None,
        loop_error=spec.loop_error,
        build_error=spec.build_error,
        prepare_result=spec.prepare_result,
        prepare_error=spec.prepare_error,
        schedule_error=spec.schedule_error,
        runs_immediately=spec.runs_immediately,
        snapshots=spec.snapshots,
        swarm=SWARM_KINDS[spec.swarm_kind]() if spec.swarm_kind else None,
        swarm_error=spec.swarm_error,
        topologies=None if spec.topologies is None else list(spec.topologies),
        topology_error=spec.topology_error,
        has_swarm_getter=spec.has_swarm_getter,
        has_topology_getter=spec.has_topology_getter,
        chart=AttachedPanel() if spec.with_visuals else None,
        voting_readout=AttachedPanel() if spec.with_visuals else None,
    )


def apply_settings_new(model, spec: Spec):
    if spec.cycle_candles is not None:
        model.cycle_candles = spec.cycle_candles
    if spec.max_cycles is not None:
        model.max_cycles = spec.max_cycles
    if spec.noise_enabled is not None:
        model.noise_enabled = spec.noise_enabled
    if spec.load_oscillation is not None:
        model.load_oscillation = spec.load_oscillation


def drive_new(spec: Spec) -> dict:
    """Drive the surface once and return everything it did."""
    world = new_world(spec)
    model = surface.PanelModel(world)
    apply_settings_new(model, spec)
    surface.run_steps(model, spec.steps)
    return {"screen": model.state(), "world": recorded(world), "model": model}


def compared(trace) -> dict:
    """Only what both sides are supposed to agree on."""
    screen = dict(trace["screen"])
    return {"screen": screen, "world": trace["world"]}


# ---------------------------------------------------------------------
# Value for value, and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_the_two_sides_describe_the_same_panel(name):
    """The surface shows a different panel than the shipped one."""
    spec = BY_NAME[name]
    old = compared(drive_old(spec))
    new = compared(drive_new(spec))
    assert old["screen"] == new["screen"], (name, old["screen"], new["screen"])
    assert old["world"] == new["world"], (name, old["world"], new["world"])
    assert digest(old) == digest(new), (name, digest(old), digest(new))


@pytest.mark.parametrize("name", SPEC_NAMES)
def test_the_sample_hashes_are_reported(name):
    """The hash reader cannot answer, so no drive was ever measured."""
    spec = BY_NAME[name]
    old = digest(compared(drive_old(spec)))
    new = digest(compared(drive_new(spec)))
    print(f"{name} old={old[:16]} new={new[:16]}")
    assert len(old) == 64 and len(new) == 64


def test_the_shipped_panel_is_never_misused_by_a_drive():
    """A stand-in took a call it does not understand and stayed quiet."""
    for name in SPEC_NAMES:
        recorder_holder = drive_old(BY_NAME[name])
        del recorder_holder
    spec = BY_NAME["happy"]
    app()
    shipped = shipped_module()
    recorder = Recorder(spec)
    scheduler = Scheduler(recorder)
    scheduler.run_coroutine_threadsafe(("nuclear-start", 1), recorder.loop)
    assert recorder.misuses == []
    scheduler.run_coroutine_threadsafe("not a start", "not the loop")
    assert len(recorder.misuses) == 2, recorder.misuses
    assert shipped.NuclearModePanel is not None


def test_two_real_inputs_driven_one_through_each_side_are_told_apart():
    """The comparison passes whatever the second side answers."""
    old = digest(compared(drive_old(BY_NAME["happy"])))
    new = digest(compared(drive_new(BY_NAME["empty_fleet"])))
    assert old != new


def test_the_same_two_real_inputs_the_other_way_round_are_told_apart():
    """The comparison reports only in one direction."""
    old = digest(compared(drive_old(BY_NAME["empty_fleet"])))
    new = digest(compared(drive_new(BY_NAME["happy"])))
    assert old != new


def test_one_input_driven_through_both_sides_hashes_alike():
    """The hash moves with something other than the values compared."""
    assert digest(compared(drive_old(BY_NAME["happy"]))) == digest(
        compared(drive_new(BY_NAME["happy"]))
    )


def test_the_same_side_driven_twice_hashes_alike():
    """A drive carries something that changes between runs.

    Two separate drives of one spec, each with its own world and its own
    widgets. Nothing is compared with itself: a first run and a second
    run are different objects, and a drive that read a clock or leaned on
    what ran before it would answer differently the second time.
    """
    first_old = compared(drive_old(BY_NAME["happy"]))
    second_old = compared(drive_old(BY_NAME["happy"]))
    assert first_old is not second_old
    assert digest(first_old) == digest(second_old), (first_old, second_old)
    first_new = compared(drive_new(BY_NAME["visuals"]))
    second_new = compared(drive_new(BY_NAME["visuals"]))
    assert first_new is not second_new
    assert digest(first_new) == digest(second_new), (first_new, second_new)


def test_the_hash_tells_a_whole_number_from_a_decimal():
    """A whole number and a decimal hash alike, so a type change passes."""
    assert 12 == 12.0
    assert digest({"a": 12}) != digest({"a": 12.0})
    assert as_text(12) == "12" and as_text(12.0) == "12.0"


def test_two_not_a_numbers_read_as_one_value_before_comparing():
    """Two not-a-numbers report a difference that is not one."""
    one_nan = float("nan")
    other_nan = float("nan")
    assert one_nan != other_nan, "this platform reads two not-a-numbers as equal"
    assert digest({"a": one_nan}) == digest({"a": other_nan})
    assert digest({"a": one_nan}) != digest({"a": 0.0})


def test_a_swapped_status_row_is_reported_by_the_hash():
    """A swapped pair of rows reads as unchanged."""
    one = drive_new(BY_NAME["happy"])["screen"]["status_text"]
    swapped = dict(one)
    swapped["total_trades"], swapped["total_candles"] = (
        one["total_candles"],
        one["total_trades"],
    )
    assert one["total_trades"] != one["total_candles"]
    assert digest(one) != digest(swapped)


def test_a_refused_start_names_the_same_type_on_both_sides():
    """One side named a refusal the other did not."""
    for name in (
        "loader_refuses",
        "build_refuses",
        "prepare_refuses",
        "schedule_refuses",
        "loop_getter_refuses",
        "swarm_getter_refuses",
        "topology_getter_refuses",
        "snapshot_refuses",
    ):
        old = compared(drive_old(BY_NAME[name]))
        new = compared(drive_new(BY_NAME[name]))
        assert old == new, name


def test_the_refusal_is_read_as_a_type_and_never_as_a_wording():
    """The refusal is compared by the words the platform chose."""
    spec = BY_NAME["build_refuses"]
    said = [
        line
        for line in drive_new(spec)["screen"]["activity"]
        if line.startswith(surface.BUILD_FAILED_PREFIX)
    ]
    assert len(said) == 1, said
    assert said[0].startswith(f"{surface.BUILD_FAILED_PREFIX}ValueError: ")
    assert surface.failure_text(
        surface.BUILD_FAILED_PREFIX, ValueError("x")
    ).startswith(f"{surface.BUILD_FAILED_PREFIX}ValueError")


def test_every_spec_reaches_an_answer_or_a_refusal():
    """A spec was skipped and nothing said so."""
    reached = set()
    for name in SPEC_NAMES:
        trace = compared(drive_new(BY_NAME[name]))
        reached.add(name)
        assert isinstance(trace["screen"]["fleet_detail"], str)
    assert reached == set(SPEC_NAMES)
    assert len(SPEC_NAMES) == len(set(SPEC_NAMES))


# ---------------------------------------------------------------------
# One status value at a time, on both sides
# ---------------------------------------------------------------------

LONG_TEXT = "n" * 200
VALUE_CASES = [
    ("empty", ""),
    ("zero_int", 0),
    ("zero_float", 0.0),
    ("negative", -17),
    ("negative_float", -17.5),
    ("a_thousand_million", 1_000_000_000),
    ("one_billionth", 1e-9),
    ("unicode", "Ünïcodé — ✓ 日本"),
    ("two_hundred_characters", LONG_TEXT),
    ("markup", "<b>bold</b> & <script>x</script>"),
    ("apostrophe", "it's a bot's name"),
    ("wrong_capitals", "RuNnInG"),
    ("newline_in_a_name", "first line\nsecond line"),
    ("number_where_text_belongs", 4321),
    ("text_where_a_number_belongs", "not a number"),
    ("numeric_text", "12.7"),
    ("infinity", float("inf")),
    ("minus_infinity", float("-inf")),
    ("not_a_number", float("nan")),
    ("two_to_the_1023", 2**1023),
    ("two_to_the_1024", 2**1024),
    ("true_where_a_number_belongs", True),
    ("false_where_a_number_belongs", False),
    ("none", None),
]

STATUS_KEYS = [key for _label, key in surface.STATUS_FIELDS]


def format_both(key, value):
    """What each side makes of `value` in `key`, or the type it refused."""
    shipped = shipped_module()
    answers = []
    for render in (shipped.NuclearModePanel._fmt_status, surface.format_status):
        try:
            answers.append(("ok", render(key, value)))
        except Exception as exc:
            answers.append(("refused", type(exc).__name__))
    return answers


@pytest.mark.parametrize("case", [name for name, _ in VALUE_CASES])
def test_every_status_value_renders_the_same_on_both_sides(case):
    """The surface renders a status value differently than the panel."""
    value = dict(VALUE_CASES)[case]
    for key in STATUS_KEYS:
        old, new = format_both(key, value)
        assert old == new, (key, case, old, new)


def test_the_value_reader_reports_a_difference_between_two_values():
    """The value reader answers the same for every value it is given."""
    seen = {digest(format_both("total_trades", value)) for _n, value in VALUE_CASES}
    assert len(seen) > 1, seen
    assert format_both("running", 1) != format_both("running", 0)


@pytest.mark.parametrize("case", [name for name, _ in VALUE_CASES])
def test_a_whole_snapshot_of_one_value_reads_the_same_on_both_sides(case):
    """A status tick of this value reaches a different row on one side."""
    value = dict(VALUE_CASES)[case]
    snapshot = {key: value for key in STATUS_KEYS}
    spec = Spec(f"value_{case}", BOTS, WIRES, snapshots=[snapshot])
    old = compared(drive_old(spec))
    new = compared(drive_new(spec))
    assert old == new, (
        case,
        old["screen"]["status_text"],
        new["screen"]["status_text"],
    )


def test_a_status_value_that_refuses_leaves_the_row_it_was_written_for():
    """A refused row was overwritten instead of being left alone."""
    spec = Spec(
        "refusing_row",
        BOTS,
        WIRES,
        snapshots=[dict(FULL_SNAPSHOT, uptime_seconds="not a number")],
    )
    old = compared(drive_old(spec))["screen"]["status_text"]
    new = compared(drive_new(spec))["screen"]["status_text"]
    assert old == new
    assert old["uptime_seconds"] == surface.PLACEHOLDER, old
    assert old["fleet_size"] == "3", old
    with pytest.raises(ValueError):
        surface.format_status("uptime_seconds", "not a number")


# ---------------------------------------------------------------------
# Step sequences, including ones that refuse part way
# ---------------------------------------------------------------------

SEQUENCES = {
    "just_a_reload": ["rescan_fleet"],
    "a_whole_run": ["start", "refresh_status", "refresh_status", "stop"],
    "stop_before_start": ["stop", "start"],
    "refresh_before_start": ["refresh_status", "start", "refresh_status"],
    "reload_mid_run": ["start", "rescan_fleet", "refresh_status"],
    "a_name_the_panel_has_not": ["start", "explode", "stop"],
}


def run_old_steps(panel, recorder, steps) -> list:
    """Drive `steps` on the shipped panel and report each one."""
    report = []
    for index, name in enumerate(steps):
        refusal = None
        try:
            if name not in OLD_STEPS:
                raise LookupError(name)
            OLD_STEPS[name](panel)
        except Exception as exc:
            refusal = type(exc).__name__
        report.append(
            dict(index=index, step=name, refusal=refusal, **old_state(panel, recorder))
        )
        if refusal is not None:
            break
    return report


def drive_old_steps(spec: Spec, steps) -> list:
    app()
    shipped = shipped_module()
    loader = loader_module()
    recorder = Recorder(spec)
    with (
        ModuleAttributeSwap(
            shipped,
            NuclearFleetController=controller_factory(recorder),
            asyncio=Scheduler(recorder),
        ),
        ModuleAttributeSwap(
            loader,
            load_bot_configs_from_state=recorder.load_bot_configs_from_state,
            load_smart_wires_from_state=recorder.load_smart_wires_from_state,
        ),
    ):
        panel = shipped.NuclearModePanel(
            activity_log_cb=recorder.activity.append,
            perf_log_cb=recorder.performance.append,
            async_loop_getter=recorder.event_loop,
        )
        try:
            report = run_old_steps(panel, recorder, steps)
        finally:
            panel._refresh_timer.stop()
    return report


@pytest.mark.parametrize("name", sorted(SEQUENCES))
def test_a_step_sequence_reads_the_same_on_both_sides(name):
    """A step sequence leaves the two sides showing different panels."""
    steps = SEQUENCES[name]
    spec = Spec(f"seq_{name}", BOTS, WIRES, snapshots=[FULL_SNAPSHOT, STOPPED_SNAPSHOT])
    old = drive_old_steps(spec, steps)
    new = surface.run_steps(surface.PanelModel(new_world(spec)), steps)
    assert [one["index"] for one in old] == [one["index"] for one in new], name
    assert [one["step"] for one in old] == [one["step"] for one in new], name
    assert [one["refusal"] for one in old] == [one["refusal"] for one in new], name
    assert digest(old) == digest(new), (name, old, new)


def test_a_sequence_that_refuses_part_way_reports_the_step_it_stopped_on():
    """A refusal part way is not reported with its index and its type."""
    steps = SEQUENCES["a_name_the_panel_has_not"]
    spec = Spec("seq_refusal", BOTS, WIRES, snapshots=[FULL_SNAPSHOT])
    new = surface.run_steps(surface.PanelModel(new_world(spec)), steps)
    assert len(new) == 2, new
    assert new[0]["step"] == "start" and new[0]["refusal"] is None
    assert new[1]["step"] == "explode" and new[1]["refusal"] == "LookupError"
    assert new[1]["timer_running"] is True, new[1]
    assert new[1]["status_text"] == new[0]["status_text"]
    assert new[0]["activity"] == new[1]["activity"]
    assert len(steps) == 3, "a step after the refusal was still driven"


def test_the_step_reader_reports_a_step_that_did_not_refuse():
    """Every step reads as a refusal, so the reader cannot report one."""
    spec = Spec("seq_clean", BOTS, WIRES, snapshots=[FULL_SNAPSHOT])
    new = surface.run_steps(surface.PanelModel(new_world(spec)), ["start", "stop"])
    assert [one["refusal"] for one in new] == [None, None], new


def test_the_recorder_keeps_what_it_recorded_before_a_refusal():
    """A refusal part way threw away what the run had already recorded."""
    spec = Spec("seq_kept", BOTS, WIRES, snapshots=[FULL_SNAPSHOT])
    world = new_world(spec)
    model = surface.PanelModel(world)
    surface.run_steps(model, ["start", "refresh_status", "explode"])
    assert world.scheduled == 1, world.scheduled
    assert len(world.built_runs) == 1, world.built_runs
    assert world.snapshot_calls == 1, world.snapshot_calls
    assert model.status_text["fleet_size"] == "3"


# ---------------------------------------------------------------------
# Counting what the shipped file holds
# ---------------------------------------------------------------------


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def parsed(path):
    return ast.parse(Path(path).read_text(encoding="utf-8"))


def calls_in(tree):
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def widget_names(tree) -> set:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
            "QtWidgets"
        ):
            for alias in node.names:
                found.add(alias.asname or alias.name)
    return found


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    found = []
    for node in calls_in(parsed(path)):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "connect":
            target = node.args[0]
            found.append(
                (
                    dotted(node.func.value),
                    (
                        "lambda"
                        if isinstance(target, ast.Lambda)
                        else dotted(
                            target.func if isinstance(target, ast.Call) else target
                        )
                    ),
                )
            )
    return sorted(found)


def timers_built(path) -> list:
    """Every timer `path` CONSTRUCTS. An import line alone is not one."""
    return [
        dotted(node.func)
        for node in calls_in(parsed(path))
        if dotted(node.func).endswith("QTimer")
    ]


def timers_started(path) -> list:
    """Every timer `path` STARTS, by the name it starts it on."""
    return sorted(
        dotted(node.func)
        for node in calls_in(parsed(path))
        if isinstance(node.func, ast.Attribute)
        and node.func.attr == "start"
        and "timer" in dotted(node.func.value).lower()
    )


def timers_run_without_building(path) -> list:
    """Every timer `path` runs without holding one."""
    return sorted(
        dotted(node.func)
        for node in calls_in(parsed(path))
        if dotted(node.func).endswith("singleShot")
        or dotted(node.func).endswith("startTimer")
    )


def threads_built(path) -> list:
    """Every thread `path` CONSTRUCTS."""
    return sorted(
        dotted(node.func)
        for node in calls_in(parsed(path))
        if dotted(node.func).endswith("Thread")
    )


def threads_started(path) -> list:
    """Every thread `path` STARTS, by the name it starts it on."""
    return sorted(
        dotted(node.func)
        for node in calls_in(parsed(path))
        if isinstance(node.func, ast.Attribute)
        and node.func.attr == "start"
        and "thread" in dotted(node.func.value).lower()
    )


def subscribe_calls(source) -> list:
    """Every call to a function NAMED subscribe, alias or not.

    The function name is read, never the object it hangs off, so a bus
    imported under another name is still counted.
    """
    tree = source if isinstance(source, ast.AST) else parsed(source)
    found = []
    for node in calls_in(tree):
        name = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else getattr(node.func, "id", "")
        )
        if name == "subscribe" or name.endswith("_subscribe"):
            topic = (
                node.args[0].value
                if node.args and isinstance(node.args[0], ast.Constant)
                else None
            )
            found.append(topic)
    return found


def emit_calls(source) -> list:
    """Every call to a function NAMED emit that carries a topic.

    A Qt signal emission carries values, never a topic name, so a first
    argument that is written-down text is what tells a bus emission from
    a signal emission without reading the object it hangs off.
    """
    tree = source if isinstance(source, ast.AST) else parsed(source)
    found = []
    for node in calls_in(tree):
        name = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else getattr(node.func, "id", "")
        )
        if name in ("emit", "emit_event", "publish") and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.append(first.value)
    return found


def signals_declared(path) -> list:
    """Every signal `path` declares."""
    found = []
    for node in ast.walk(parsed(path)):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if dotted(node.value.func).endswith("Signal"):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        found.append(target.id)
    return sorted(found)


def signal_emits(path) -> list:
    """Every emission whose first argument is not a written-down topic."""
    found = []
    for node in calls_in(parsed(path)):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "emit":
            first = node.args[0] if node.args else None
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                found.append(dotted(node.func.value).rsplit(".", 1)[-1])
    return sorted(found)


def screen_elements(path) -> list:
    """Every widget `path` CONSTRUCTS, arrangers left out."""
    tree = parsed(path)
    names = widget_names(tree) | {
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.level > 0 or (node.module or "").startswith("src.gui"))
        for name in (alias.asname or alias.name for alias in node.names)
        if name[:1].isupper()
    }
    return sorted(
        made
        for node in calls_in(tree)
        for made in [dotted(node.func)]
        if made in names and not made.endswith("Layout")
    )


def arrangers(path) -> list:
    """Every layout `path` constructs."""
    tree = parsed(path)
    names = widget_names(tree)
    return sorted(
        made
        for node in calls_in(tree)
        for made in [dotted(node.func)]
        if made in names and made.endswith("Layout")
    )


def source_classes(path) -> list:
    return sorted(
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    )


def source_functions(path) -> list:
    return sorted(
        node.name
        for node in ast.walk(parsed(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def declared_members(holder) -> list:
    """Every method, property, static and class method `holder` declares."""
    from PySide6.QtCore import Signal

    found = []
    for name, value in vars(holder).items():
        if name.startswith("__") and name != "__init__":
            continue
        if isinstance(value, Signal):
            continue
        if isinstance(value, (property, staticmethod, classmethod)) or callable(value):
            found.append(name)
    return sorted(found)


SHIPPED_CONNECT_TOTAL = 4
SHIPPED_SLOT_TO_SURFACE = {
    "_rescan_cache": "rescan_fleet",
    "_on_start_clicked": "start",
    "_on_stop_clicked": "stop",
    "_refresh_status": "refresh_status",
}


def test_the_panel_wires_four_actions_and_the_surface_names_four():
    """An action was gained or lost between the two sides."""
    sites = connect_sites(SHIPPED_SOURCE)
    assert sites, "the counter found no wiring at all"
    assert len(sites) == SHIPPED_CONNECT_TOTAL, sites
    assert len(surface.ACTIONS) == len(sites), (surface.ACTIONS, sites)
    assert sites == [
        ("self._refresh_btn.clicked", "self._rescan_cache"),
        ("self._refresh_timer.timeout", "self._refresh_status"),
        ("self._start_btn.clicked", "self._on_start_clicked"),
        ("self._stop_btn.clicked", "self._on_stop_clicked"),
    ], sites
    neighbour = connect_sites(WIRING_NEIGHBOUR)
    assert len(neighbour) == WIRING_NEIGHBOUR_CONNECT_TOTAL, neighbour


def test_every_wired_slot_has_a_named_counterpart_on_the_surface():
    """A wired action reaches nothing on the surface."""
    shipped = shipped_module()
    slots = sorted(
        target.rsplit(".", 1)[-1] for _signal, target in connect_sites(SHIPPED_SOURCE)
    )
    assert slots == sorted(SHIPPED_SLOT_TO_SURFACE), slots
    assert sorted(surface.ACTIONS.values()) == sorted(SHIPPED_SLOT_TO_SURFACE.values())
    for slot, replacement in SHIPPED_SLOT_TO_SURFACE.items():
        assert hasattr(shipped.NuclearModePanel, slot), slot
        assert hasattr(surface.PanelModel, replacement), replacement


def test_the_counterpart_table_reports_a_name_neither_side_holds():
    """The counterpart table accepts a name that is on neither side."""
    shipped = shipped_module()
    assert "_invented_slot" not in SHIPPED_SLOT_TO_SURFACE
    assert not hasattr(shipped.NuclearModePanel, "_invented_slot")
    assert not hasattr(surface.PanelModel, "invented_action")


SHIPPED_CLASSES = ["NuclearModePanel"]
SHIPPED_FUNCTIONS = [
    "__init__",
    "_feed_visuals",
    "_fmt_status",
    "_mk_pair",
    "_on_start_clicked",
    "_on_stop_clicked",
    "_refresh_status",
    "_rescan_cache",
    "_resolve_topologies",
    "_section_label",
    "_swarm_hooks",
    "set_swarm_getter",
    "set_topology_getter",
    "set_visual_widgets",
]
SURFACE_CLASSES = {
    "PanelModel": "NuclearModePanel",
    "PanelWorld": "the world the panel reads, handed in",
    "SoakRun": "NuclearFleetController",
}


def test_every_shipped_class_method_and_function_has_a_counterpart():
    """The shipped panel gained or lost a class, a method or a function."""
    shipped = shipped_module()
    live = sorted(
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    )
    assert live == SHIPPED_CLASSES, live
    assert source_classes(SHIPPED_SOURCE) == SHIPPED_CLASSES
    assert source_functions(SHIPPED_SOURCE) == SHIPPED_FUNCTIONS
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    members = declared_members(shipped.NuclearModePanel)
    assert members, "the panel declares no method"
    assert "_fmt_status" in members
    for name in ("_mk_pair", "_section_label"):
        assert name not in members, name


def test_the_class_counter_finds_a_class_declared_inside_a_method():
    """A class declared inside a method is never counted."""
    from src.gui import stock_main_window

    declared = source_classes(NESTED_CLASS_NEIGHBOUR)
    live = sorted(
        name
        for name, value in vars(stock_main_window).items()
        if isinstance(value, type) and value.__module__ == stock_main_window.__name__
    )
    assert set(declared) - set(live), (declared, live)
    assert "_mk_pair" in source_functions(SHIPPED_SOURCE)


def test_the_panel_declares_no_signal_and_emits_none():
    """A signal was gained where the surface names none."""
    assert signals_declared(SHIPPED_SOURCE) == list(surface.SIGNALS) == []
    assert signal_emits(SHIPPED_SOURCE) == list(surface.EMITTED_SIGNALS) == []
    neighbour = signals_declared(SIGNAL_NEIGHBOUR)
    assert len(neighbour) == SIGNAL_NEIGHBOUR_SIGNAL_TOTAL, neighbour
    assert signal_emits(ELEMENT_NEIGHBOUR), "the emit counter found no emission at all"


def test_the_panel_builds_one_timer_starts_one_and_runs_none_unbuilt():
    """A timer was gained or lost, in either of its two forms."""
    built = timers_built(SHIPPED_SOURCE)
    started = timers_started(SHIPPED_SOURCE)
    assert built == ["QTimer"], built
    assert started == ["self._refresh_timer.start"], started
    assert len(built) == len(surface.TIMERS), (built, surface.TIMERS)
    assert timers_run_without_building(SHIPPED_SOURCE) == []
    named = SHIPPED_SOURCE.read_text(encoding="utf-8").count("QTimer")
    assert named > len(built), (named, built)
    assert len(timers_built(TIMER_SAME_NAME_A)) == TIMER_SAME_NAME_A_BUILD_TOTAL
    assert timers_built(TIMER_SAME_NAME_B) == []
    assert TIMER_SAME_NAME_A.name == TIMER_SAME_NAME_B.name
    unbuilt = timers_run_without_building(TIMER_UNBUILT_NEIGHBOUR)
    assert len(unbuilt) == TIMER_NEIGHBOUR_UNBUILT_TOTAL, unbuilt


def test_the_panel_builds_no_thread_and_starts_none():
    """A thread was gained where the surface names none."""
    assert threads_built(SHIPPED_SOURCE) == list(surface.THREADS) == []
    assert threads_started(SHIPPED_SOURCE) == []
    assert len(threads_built(THREAD_NEIGHBOUR)) == THREAD_NEIGHBOUR_BUILD_TOTAL
    assert len(threads_started(THREAD_NEIGHBOUR)) == THREAD_NEIGHBOUR_START_TOTAL


def test_the_panel_touches_no_bus_in_either_direction():
    """The panel listens or speaks on a bus the surface names none of."""
    assert subscribe_calls(SHIPPED_SOURCE) == []
    assert emit_calls(SHIPPED_SOURCE) == []
    assert surface.BUS_TOPICS == () and surface.BUS_EMITS == ()
    listened = subscribe_calls(BUS_NEIGHBOUR)
    spoken = emit_calls(BUS_NEIGHBOUR)
    assert len(listened) == BUS_NEIGHBOUR_SUBSCRIBE_TOTAL, listened
    assert len(spoken) == BUS_NEIGHBOUR_EMIT_TOTAL, spoken


ALIASED_BUS = """
from src.core.event_bus import get_event_bus as wiring
wiring().subscribe("wire.created", handler)
wiring().emit("wire.removed", {})
"""
BUS_BY_RECEIVER = """
bus.subscribe("wire.created", handler)
bus.emit("wire.removed", {})
"""


def test_the_bus_counter_still_counts_a_bus_imported_under_another_name():
    """The bus counter reads the object, so an alias hides a subscription."""
    aliased = ast.parse(ALIASED_BUS)
    plain = ast.parse(BUS_BY_RECEIVER)
    assert subscribe_calls(aliased) == ["wire.created"]
    assert emit_calls(aliased) == ["wire.removed"]
    assert subscribe_calls(plain) == ["wire.created"]
    assert emit_calls(plain) == ["wire.removed"]
    by_receiver = [
        node
        for node in calls_in(aliased)
        if isinstance(node.func, ast.Attribute)
        and node.func.attr in ("subscribe", "emit")
        and "bus" in dotted(node.func.value).lower()
    ]
    assert by_receiver == [], "a counter keyed on the receiver would find these"


def test_the_bus_counter_reports_a_subscription_that_was_added():
    """The bus counter answers nothing whatever the source holds."""
    grown = ast.parse(ALIASED_BUS + '\nwiring().subscribe("bot.log", handler)\n')
    assert (
        len(subscribe_calls(grown)) == len(subscribe_calls(ast.parse(ALIASED_BUS))) + 1
    )


def test_the_panel_builds_eighteen_elements_and_nine_arrangers():
    """A control was gained or lost from the panel."""
    built = screen_elements(SHIPPED_SOURCE)
    assert built.count("QLabel") == 7, built
    assert built.count("QFrame") == 4, built
    assert built.count("QPushButton") == 3, built
    assert built.count("QSpinBox") == 2, built
    assert built.count("QCheckBox") == 2, built
    assert len(built) == 18, built
    laid = arrangers(SHIPPED_SOURCE)
    assert laid.count("QVBoxLayout") == 5, laid
    assert laid.count("QFormLayout") == 2, laid
    assert laid.count("QHBoxLayout") == 1 and laid.count("QGridLayout") == 1, laid
    assert len(laid) == 9, laid
    named = SHIPPED_SOURCE.read_text(encoding="utf-8").count("QPushButton")
    assert named > built.count("QPushButton"), named
    neighbour = screen_elements(ELEMENT_NEIGHBOUR)
    assert len(neighbour) == ELEMENT_NEIGHBOUR_BUILD_TOTAL, neighbour


def test_the_element_counter_never_counts_a_name_inside_prose():
    """A name written in a comment is counted as a control that was built."""
    source = "from PySide6.QtWidgets import QLabel\n# QLabel()\nx = QLabel()\n"
    tree = ast.parse(source)
    assert source.count("QLabel(") == 2
    made = [
        dotted(node.func)
        for node in calls_in(tree)
        if dotted(node.func) in widget_names(tree)
    ]
    assert made == ["QLabel"], made


def test_the_neighbouring_controls_are_eight_different_files():
    """Two controls read one file, so one of the two was never measured."""
    named = [
        WIRING_NEIGHBOUR,
        SIGNAL_NEIGHBOUR,
        TIMER_UNBUILT_NEIGHBOUR,
        BUS_NEIGHBOUR,
        ELEMENT_NEIGHBOUR,
        NESTED_CLASS_NEIGHBOUR,
        THREAD_NEIGHBOUR,
        TIMER_SAME_NAME_A,
    ]
    assert len(set(named)) == len(named), named
    for path in named + [SHIPPED_SOURCE, SURFACE_SOURCE, TIMER_SAME_NAME_B]:
        assert path.is_file(), path


# ---------------------------------------------------------------------
# The completeness check
# ---------------------------------------------------------------------


def snapshot() -> dict:
    """Every value the surface exports, in one place."""
    world = surface.PanelWorld(
        bot_configs=BOTS,
        smart_wires=WIRES,
        loop=object(),
        snapshots=[FULL_SNAPSHOT, STOPPED_SNAPSHOT],
        swarm=Swarm(),
        has_swarm_getter=True,
        topologies=[{"pair": 1}],
        has_topology_getter=True,
    )
    idle = surface.PanelModel(world)
    screen_idle = idle.build()
    idle.start()
    idle.refresh_status()
    running = idle.build()
    idle.stop()
    stopped = idle.build()
    empty = surface.PanelModel(surface.PanelWorld())
    refused = surface.PanelModel(
        surface.PanelWorld(loader_error=RuntimeError("bot_state gone"))
    )
    return {
        "idle_screen": screen_idle,
        "running_screen": running,
        "stopped_screen": stopped,
        "empty_screen": empty.build(),
        "refused_screen": refused.build(),
        "status_cells": surface.status_cells(),
        "last_exception_cell": surface.last_exception_cell(),
        "status_half": surface.status_half(),
        "status_fields": [list(pair) for pair in surface.STATUS_FIELDS],
        "actions": dict(surface.ACTIONS),
        "timers": dict(surface.TIMERS),
        "signals": list(surface.SIGNALS),
        "emitted_signals": list(surface.EMITTED_SIGNALS),
        "bus_topics": list(surface.BUS_TOPICS),
        "bus_emits": list(surface.BUS_EMITS),
        "threads": list(surface.THREADS),
        "step_names": list(surface.STEP_NAMES),
        "screen_order": list(surface.SCREEN_ORDER),
        "run_control_keys": list(surface.RUN_CONTROL_KEYS),
        "fleet_card_order": list(surface.FLEET_CARD_ORDER),
        "config_card_order": list(surface.CONFIG_CARD_ORDER),
        "swarm_hook_names": list(surface.SWARM_HOOK_NAMES),
        "logger_name": surface.LOGGER_NAME,
        "method": surface.METHOD,
        "voting_keys": list(surface.VOTING_KEYS),
        "signal_keys": list(surface.SIGNAL_KEYS),
        "voting_payload": surface.voting_payload(Summary()),
        "voting_payload_default": surface.voting_payload(Summary(timeframe="")),
        "default_timeframe": surface.DEFAULT_TIMEFRAME,
        "timeframe_attribute": surface.TIMEFRAME_ATTRIBUTE,
        "boolean_status_keys": list(surface.BOOLEAN_STATUS_KEYS),
        "run_state_key": surface.RUN_STATE_KEY,
        "uptime_key": surface.UPTIME_KEY,
        "noise_key": surface.NOISE_KEY,
        "multiplier_key": surface.MULTIPLIER_KEY,
        "symbol_key": surface.SYMBOL_KEY,
        "last_price_key": surface.LAST_PRICE_KEY,
        "last_volume_key": surface.LAST_VOLUME_KEY,
        "voting_summary_key": surface.VOTING_SUMMARY_KEY,
        "last_exception_source_key": surface.LAST_EXCEPTION_SOURCE_KEY,
        "messages": [
            surface.NO_LOOP_MESSAGE,
            surface.NO_SWARM_MESSAGE,
            surface.NO_TOPOLOGY_MESSAGE,
            surface.INJECTING_PREFIX,
            surface.INJECTING_SUFFIX,
        ],
        "failures": [
            surface.failure_text(surface.BUILD_FAILED_PREFIX, ValueError("x")),
            surface.failure_text(surface.PREPARE_FAILED_PREFIX, OSError("x")),
            surface.failure_text(surface.SCHEDULE_FAILED_PREFIX, RuntimeError("x")),
            surface.failure_text(surface.LOADER_FAILURE_PREFIX, KeyError("x")),
        ],
        "fleet_summary": surface.fleet_summary(3, 2, 2),
        "fleet_summary_parts": list(surface.FLEET_SUMMARY_PARTS),
        "type_message_join": surface.TYPE_MESSAGE_JOIN,
        "failure_prefixes": [
            surface.LOADER_FAILURE_PREFIX,
            surface.BUILD_FAILED_PREFIX,
            surface.PREPARE_FAILED_PREFIX,
            surface.SCHEDULE_FAILED_PREFIX,
        ],
        "symbols_of": surface.symbols_of(BOTS),
        "empty_fleet_text": surface.EMPTY_FLEET_TEXT,
        "empty_label_text": surface.EMPTY_LABEL_TEXT,
        "placeholder": surface.PLACEHOLDER,
        "blank": surface.BLANK,
        "label_suffix": surface.LABEL_SUFFIX,
        "cell_alignment": surface.CELL_ALIGNMENT,
        "last_exception_label": surface.LAST_EXCEPTION_LABEL,
        "last_exception_key": surface.LAST_EXCEPTION_KEY,
        "column_stretch": list(surface.COLUMN_STRETCH),
        "outer_margins": list(surface.OUTER_MARGINS_PX),
        "card_margins": list(surface.CARD_MARGINS_PX),
        "styles": {
            "section": surface.section_label_style(),
            "card": surface.card_style(),
            "header_card": surface.header_card_style(),
            "title": surface.title_style(),
            "subtitle": surface.small_text_style(surface.SUBTITLE_GREY),
            "empty": surface.small_text_style(surface.EMPTY_ORANGE),
            "detail": surface.small_text_style(surface.FLEET_BLUE),
            "status_label": surface.status_label_style(),
            "status_value": surface.status_value_style(),
            "reload": surface.reload_button_style(),
            "start": surface.start_button_style(),
            "stop": surface.stop_button_style(),
        },
        "formatted": {
            f"{key}:{name}": _formatted_or_refusal(key, value)
            for key in STATUS_KEYS
            for name, value in VALUE_CASES
        },
        "spin_bounds": [
            surface.CYCLE_MIN,
            surface.CYCLE_MAX,
            surface.CYCLE_STEP,
            surface.MAX_CYCLES_MIN,
            surface.MAX_CYCLES_MAX,
            surface.MAX_CYCLES_DEFAULT,
            surface.DEFAULT_CYCLE_CANDLES,
        ],
        "defaults": [surface.NOISE_DEFAULT, surface.LOAD_DEFAULT],
        "interval_ms": surface.REFRESH_INTERVAL_MS,
        "spacings": [
            surface.OUTER_SPACING_PX,
            surface.HEADER_SPACING_PX,
            surface.FORM_SPACING_PX,
            surface.GRID_HORIZONTAL_SPACING_PX,
            surface.GRID_VERTICAL_SPACING_PX,
        ],
        "font_sizes": [
            surface.TITLE_FONT_PX,
            surface.SMALL_FONT_PX,
            surface.VALUE_FONT_PX,
            surface.BUTTON_FONT_PX,
        ],
        "radii": [
            surface.CARD_RADIUS_PX,
            surface.HEADER_RADIUS_PX,
            surface.RELOAD_RADIUS_PX,
        ],
        "paddings": [surface.RELOAD_PADDING, surface.RUN_BUTTON_PADDING],
        "numbers": [
            surface.NOISE_PERCENT_SCALE,
            surface.UPTIME_DECIMALS,
            surface.NOISE_DECIMALS,
            surface.MULTIPLIER_DECIMALS,
            surface.FLOAT_DECIMALS,
        ],
        "words": [
            surface.RUNNING_TEXT,
            surface.STOPPED_TEXT,
            surface.YES_TEXT,
            surface.NO_TEXT,
            surface.MULTIPLIER_SUFFIX,
            surface.PERCENT_SUFFIX,
            surface.UNLIMITED_TEXT,
            surface.CYCLE_SUFFIX,
        ],
        "labels": [
            surface.TITLE,
            surface.SUBTITLE,
            surface.FLEET_SECTION,
            surface.CONFIG_SECTION,
            surface.STATUS_SECTION,
            surface.FLEET_ROW_LABEL,
            surface.RELOAD_LABEL,
            surface.START_LABEL,
            surface.STOP_LABEL,
            surface.CYCLE_ROW_LABEL,
            surface.MAX_CYCLES_ROW_LABEL,
            surface.NOISE_LABEL,
            surface.LOAD_LABEL,
            surface.ACCESSIBLE_NAME,
        ],
        "tips": [
            surface.CYCLE_TIP,
            surface.MAX_CYCLES_TIP,
            surface.NOISE_TIP,
            surface.LOAD_TIP,
        ],
        "colours": [
            surface.TEAL,
            surface.GOLD,
            surface.SUBTITLE_GREY,
            surface.CARD_BG,
            surface.CARD_BORDER,
            surface.EMPTY_ORANGE,
            surface.FLEET_BLUE,
            surface.LABEL_BLUE,
            surface.VALUE_WHITE,
            surface.RELOAD_BG,
            surface.RELOAD_HOVER,
            surface.START_BG,
            surface.START_HOVER,
            surface.STOP_FG,
            surface.STOP_BG,
            surface.STOP_HOVER,
            surface.DISABLED_BG,
            surface.DISABLED_FG,
            surface.DISABLED_BORDER,
            surface.HEADER_CARD_BG,
            surface.HEADER_CARD_BORDER,
        ],
        "bridge": surface.view_model({}),
    }


def _formatted_or_refusal(key, value):
    try:
        return surface.format_status(key, value)
    except Exception as exc:
        return type(exc).__name__


def carried_values(value, seen=None) -> set:
    """Every value the snapshot carries, at every depth, as text."""
    seen = set() if seen is None else seen
    if isinstance(value, dict):
        for key, inner in value.items():
            seen.add(repr(key))
            carried_values(inner, seen)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            carried_values(inner, seen)
    else:
        seen.add(repr(value))
    return seen


def leaves(value) -> list:
    """Every value inside `value`, at every depth, keys included."""
    if isinstance(value, dict):
        found = []
        for key, inner in value.items():
            found.extend(leaves(key))
            found.extend(leaves(inner))
        return found
    if isinstance(value, (list, tuple)):
        found = []
        for inner in value:
            found.extend(leaves(inner))
        return found
    return [value]


def surface_constants() -> dict:
    """Every value the surface module exports under a shouted name."""
    return {
        name: value
        for name, value in vars(surface).items()
        if name.isupper() and not name.startswith("_")
    }


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A surface value is compared by nothing, so a change to it passes."""
    carried = carried_values(snapshot())
    missing = []
    for name, value in surface_constants().items():
        for part in leaves(value):
            if repr(part) not in carried:
                missing.append((name, part))
    assert missing == [], missing


EMPTY_BY_DESIGN = {
    "signals": surface.SIGNALS,
    "emitted_signals": surface.EMITTED_SIGNALS,
    "bus_topics": surface.BUS_TOPICS,
    "bus_emits": surface.BUS_EMITS,
    "threads": surface.THREADS,
    "empty_label_text": surface.EMPTY_LABEL_TEXT,
}


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """A snapshot key names something the surface does not have."""
    taken = snapshot()
    assert [key for key, value in taken.items() if value is None] == []
    empty = sorted(key for key, value in taken.items() if value in ("", [], {}, ()))
    assert empty == sorted(EMPTY_BY_DESIGN), empty
    for key, held in EMPTY_BY_DESIGN.items():
        assert list(held) == list(taken[key]) == []
    assert len(taken) > len(surface.ACTIONS)


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passes a value nothing reads."""
    carried = carried_values(snapshot())
    assert repr(surface.TEAL) in carried
    assert repr("a colour the surface never names") not in carried
    thinned = carried_values({"idle_screen": snapshot()["idle_screen"]})
    assert repr(surface.STOPPED_TEXT) not in thinned
    assert len(thinned) < len(carried)


def test_both_the_completeness_checks_can_report():
    """Neither completeness check can fail, so both are decoration."""
    with pytest.raises(AssertionError):
        assert [("invented", 1)] == []
    assert carried_values({"a": {"b": [1, "two"]}}) == {"'a'", "'b'", "1", "'two'"}
    assert leaves({"a": (("b", 1),)}) == ["a", "b", 1]


# ---------------------------------------------------------------------
# The growth check
# ---------------------------------------------------------------------


def names_on_disk(path) -> set:
    """Every top-level name the file DECLARES, read off the file."""
    tree = parsed(path)
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found.add(node.target.id)
    return {name for name in found if not name.startswith("_")}


def names_on_module() -> set:
    """Every name the imported surface module carries, imports left out."""
    imported = set()
    for node in ast.walk(parsed(SURFACE_SOURCE)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
    return {
        name
        for name in vars(surface)
        if not name.startswith("_") and name not in imported
    }


def test_the_surface_grew_no_name_the_file_does_not_declare():
    """A name reaches the module that the file never declares."""
    on_disk = names_on_disk(SURFACE_SOURCE)
    on_module = names_on_module()
    assert on_module - on_disk == set(), sorted(on_module - on_disk)
    assert on_disk - on_module == set(), sorted(on_disk - on_module)
    assert len(on_disk) > len(surface.ACTIONS), len(on_disk)


def test_the_growth_check_reports_a_name_on_one_side_only():
    """The growth check answers the same whatever either side holds."""
    on_disk = names_on_disk(SURFACE_SOURCE)
    assert "PanelModel" in on_disk and "METHOD" in on_disk
    assert "a_name_neither_side_declares" not in on_disk
    assert (on_disk | {"a_name_neither_side_declares"}) - on_disk == {
        "a_name_neither_side_declares"
    }
    assert "annotations" not in names_on_module(), "an import read as a declaration"


# ---------------------------------------------------------------------
# The surface writes out its own values
# ---------------------------------------------------------------------

MOVED_VALUES = {
    "_STATUS_FIELDS": (("Moved", "running"),),
}
SHARED_CONSTANTS = {
    "DEFAULT_CYCLE_CANDLES": "DEFAULT_CYCLE_CANDLES",
}


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_file():
    """The surface reads the shipped file, so a change moves both sides."""
    shipped = shipped_module()
    held = shipped._STATUS_FIELDS
    assert [list(pair) for pair in held] == [
        list(pair) for pair in surface.STATUS_FIELDS
    ]
    swap = ModuleAttributeSwap(shipped, _STATUS_FIELDS=MOVED_VALUES["_STATUS_FIELDS"])
    with swap:
        assert shipped._STATUS_FIELDS != surface.STATUS_FIELDS
        assert len(surface.STATUS_FIELDS) == 16, surface.STATUS_FIELDS
    assert shipped._STATUS_FIELDS is held


def test_the_comparison_names_exactly_which_value_moved():
    """A moved value is reported without saying which one moved."""
    shipped = shipped_module()
    from src.simulator import nuclear_fleet_controller as controller

    pairs = {
        "status_fields": (
            [list(one) for one in shipped._STATUS_FIELDS],
            [list(one) for one in surface.STATUS_FIELDS],
        ),
        "default_cycle_candles": (
            controller.DEFAULT_CYCLE_CANDLES,
            surface.DEFAULT_CYCLE_CANDLES,
        ),
    }
    assert [name for name, (old, new) in pairs.items() if old != new] == []
    with ModuleAttributeSwap(controller, DEFAULT_CYCLE_CANDLES=999):
        moved = [
            name
            for name, (old, new) in {
                "status_fields": pairs["status_fields"],
                "default_cycle_candles": (
                    controller.DEFAULT_CYCLE_CANDLES,
                    surface.DEFAULT_CYCLE_CANDLES,
                ),
            }.items()
            if old != new
        ]
    assert moved == ["default_cycle_candles"], moved
    assert controller.DEFAULT_CYCLE_CANDLES == surface.DEFAULT_CYCLE_CANDLES


def test_the_surface_does_not_lean_on_the_shipped_panel_at_all():
    """The surface imports the shipped panel, so it is not independent."""
    imported = set()
    for node in ast.walk(parsed(SURFACE_SOURCE)):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
    assert imported == {"__future__", "typing"}, imported
    assert "PySide6" not in repr(imported)


# ---------------------------------------------------------------------
# Shared state, and putting it back
# ---------------------------------------------------------------------


def test_each_side_gets_its_own_edges_and_they_are_put_back():
    """A drive leaves the shipped module holding one side's stand-ins."""
    shipped = shipped_module()
    before = (shipped.NuclearFleetController, shipped.asyncio)
    drive_old(BY_NAME["happy"])
    after = (shipped.NuclearFleetController, shipped.asyncio)
    assert after == before, (before, after)


def test_the_edges_are_put_back_after_a_refusal():
    """A refusal mid-drive leaves the swap in place for the next test."""
    shipped = shipped_module()
    before = (shipped.NuclearFleetController, shipped.asyncio)
    with pytest.raises(RuntimeError):
        with ModuleAttributeSwap(
            shipped, NuclearFleetController=object(), asyncio=object()
        ):
            assert shipped.NuclearFleetController is not before[0]
            raise RuntimeError("a refusal inside a swap")
    assert (shipped.NuclearFleetController, shipped.asyncio) == before


def test_the_swap_is_watched_while_a_drive_is_running():
    """The swap is only ever read before and after, never during."""
    app()
    shipped = shipped_module()
    loader = loader_module()
    spec = BY_NAME["happy"]
    recorder = Recorder(spec)
    seen = []
    with (
        ModuleAttributeSwap(
            shipped,
            NuclearFleetController=controller_factory(recorder),
            asyncio=Scheduler(recorder),
        ),
        ModuleAttributeSwap(
            loader,
            load_bot_configs_from_state=recorder.load_bot_configs_from_state,
            load_smart_wires_from_state=recorder.load_smart_wires_from_state,
        ),
    ):
        panel = shipped.NuclearModePanel(
            activity_log_cb=recorder.activity.append,
            perf_log_cb=recorder.performance.append,
            async_loop_getter=recorder.event_loop,
        )
        try:
            seen.append(isinstance(shipped.asyncio, Scheduler))
            panel._on_start_clicked()
            seen.append(isinstance(shipped.asyncio, Scheduler))
        finally:
            panel._refresh_timer.stop()
    seen.append(isinstance(shipped.asyncio, Scheduler))
    assert seen == [True, True, False], seen


def test_the_shipped_panel_writes_to_no_module_level_name():
    """The panel edits a name the whole process shares."""
    shipped = shipped_module()
    held = {
        name: value
        for name, value in vars(shipped).items()
        if not name.startswith("__")
    }
    drive_old(BY_NAME["happy"])
    drive_old(BY_NAME["empty_fleet"])
    now = {
        name: value
        for name, value in vars(shipped).items()
        if not name.startswith("__")
    }
    assert now == held, sorted(set(now) ^ set(held))


def test_the_surface_writes_to_no_module_level_name():
    """The surface edits a name the whole process shares."""
    held = {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("__")
    }
    for name in SPEC_NAMES:
        drive_new(BY_NAME[name])
    surface.view_model({})
    now = {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("__")
    }
    assert now == held, sorted(set(now) ^ set(held))


def test_neither_side_edits_the_fleet_it_was_handed():
    """A drive rewrote the bot list it was given."""
    configs = [dict(one) for one in BOTS]
    wires = [dict(one) for one in WIRES]
    spec = Spec("borrowed", configs, wires, snapshots=[FULL_SNAPSHOT])
    drive_old(spec)
    drive_new(spec)
    assert configs == BOTS, configs
    assert wires == WIRES, wires
    snapshot_held = dict(FULL_SNAPSHOT)
    drive_new(Spec("borrowed_snap", BOTS, WIRES, snapshots=[FULL_SNAPSHOT]))
    assert FULL_SNAPSHOT == snapshot_held


# ---------------------------------------------------------------------
# Pictures
# ---------------------------------------------------------------------

PICTURE_STATES = ("idle", "running", "stopped", "empty", "refused")
CONTROL_RULE = "QWidget { background: #7d1a4a; }"


def picture_spec(state):
    if state == "empty":
        return Spec("pic_empty", (), (), steps=())
    if state == "refused":
        return Spec(
            "pic_refused", BOTS, WIRES, loader_error=RuntimeError("bot_state"), steps=()
        )
    steps = {
        "idle": (),
        "running": ("start", "refresh_status"),
        "stopped": ("start", "refresh_status", "stop"),
    }[state]
    return Spec(
        f"pic_{state}",
        BOTS,
        WIRES,
        snapshots=[FULL_SNAPSHOT, STOPPED_SNAPSHOT],
        steps=steps,
    )


def old_panel_for(state):
    """The shipped panel after this state's driving, held alive."""
    return drive_old(picture_spec(state))["panel"]


def model_payload(state):
    """The surface's screen after the same driving, stamped."""
    spec = picture_spec(state)
    world = new_world(spec)
    model = surface.PanelModel(world)
    surface.run_steps(model, spec.steps)
    return sealed(model.build())


def widget_painted_by_the_model(payload):
    """A panel built only from the payload, never from the shipped one."""
    payload = unaltered(payload)
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QFormLayout,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )

    app()
    screen = QWidget()
    screen.setAccessibleName(payload["accessible_name"])
    outer = QVBoxLayout(screen)
    left, top, right, bottom = payload["layout"]["margins_px"]
    outer.setContentsMargins(left, top, right, bottom)
    outer.setSpacing(payload["layout"]["spacing_px"])

    def heading(part):
        label = QLabel(part["text"])
        label.setStyleSheet(part["style"])
        return label

    def card(part):
        frame = QFrame()
        frame.setStyleSheet(part["style"])
        box = QVBoxLayout(frame)
        margins = part.get("margins_px")
        if margins is not None:
            box.setContentsMargins(*margins)
        return frame, box

    header = payload["header_card"]
    header_frame = QFrame()
    header_frame.setStyleSheet(header["style"])
    header_box = QVBoxLayout(header_frame)
    header_box.setSpacing(header["spacing_px"])
    header_box.addWidget(heading(header["title"]))
    subtitle = heading(header["subtitle"])
    subtitle.setWordWrap(header["subtitle"]["word_wrap"])
    header_box.addWidget(subtitle)
    outer.addWidget(header_frame)

    fleet = payload["fleet_card"]
    fleet_frame, fleet_box = card(fleet)
    fleet_box.addWidget(heading(fleet["heading"]))
    empty = heading(fleet["empty"])
    empty.setWordWrap(fleet["empty"]["word_wrap"])
    if not fleet["empty"]["visible"]:
        empty.hide()
    fleet_box.addWidget(empty)
    fleet_form = QFormLayout()
    fleet_form.setSpacing(fleet["form_spacing_px"])
    detail = heading(fleet["detail"])
    detail.setWordWrap(fleet["detail"]["word_wrap"])
    fleet_form.addRow(fleet["detail_row_label"], detail)
    reload_button = QPushButton(fleet["reload_button"]["text"])
    reload_button.setStyleSheet(fleet["reload_button"]["style"])
    reload_button.setEnabled(fleet["reload_button"]["enabled"])
    fleet_form.addRow(fleet["reload_row_label"], reload_button)
    fleet_box.addLayout(fleet_form)
    outer.addWidget(fleet_frame)

    config = payload["config_card"]
    config_frame, config_box = card(config)
    config_box.addWidget(heading(config["heading"]))
    config_form = QFormLayout()
    config_form.setSpacing(config["form_spacing_px"])
    for name in config["order"]:
        part = config[name]
        if "checked" in part:
            control = QCheckBox(part["text"])
            control.setChecked(part["checked"])
        else:
            control = QSpinBox()
            control.setRange(part["minimum"], part["maximum"])
            if "single_step" in part:
                control.setSingleStep(part["single_step"])
            if "special_value_text" in part:
                control.setSpecialValueText(part["special_value_text"])
            control.setValue(part["value"])
            if "suffix" in part:
                control.setSuffix(part["suffix"])
        control.setToolTip(part["tooltip"])
        control.setEnabled(part["enabled"])
        config_form.addRow(part["row_label"], control)
    config_box.addLayout(config_form)
    outer.addWidget(config_frame)

    buttons = QHBoxLayout()
    for name in ("start", "stop"):
        part = payload["buttons"][name]
        button = QPushButton(part["text"])
        button.setStyleSheet(part["style"])
        button.setEnabled(part["enabled"])
        buttons.addWidget(button)
    buttons.addStretch()
    outer.addLayout(buttons)

    status = payload["status_card"]
    status_frame, status_box = card(status)
    status_box.addWidget(heading(status["heading"]))
    grid = QGridLayout()
    grid.setHorizontalSpacing(status["horizontal_spacing_px"])
    grid.setVerticalSpacing(status["vertical_spacing_px"])
    align = getattr(Qt, status["alignment"])
    for cell in status["cells"]:
        name = QLabel(cell["text"])
        name.setStyleSheet(status["label_style"])
        value = QLabel(status["values"][cell["key"]])
        value.setStyleSheet(status["value_style"])
        grid.addWidget(name, cell["row"], cell["column"], alignment=align)
        grid.addWidget(value, cell["row"], cell["column"] + 1, alignment=align)
    for column, stretch in enumerate(status["column_stretch"]):
        grid.setColumnStretch(column, stretch)
    exception = status["last_exception"]
    exception_name = QLabel(exception["text"])
    exception_name.setStyleSheet(status["label_style"])
    exception_value = QLabel(status["values"][exception["key"]])
    exception_value.setStyleSheet(status["value_style"])
    exception_value.setWordWrap(exception["word_wrap"])
    grid.addWidget(
        exception_name, exception["row"], exception["column"], alignment=align
    )
    grid.addWidget(
        exception_value,
        exception["row"],
        exception["column"] + 1,
        1,
        exception["column_span"],
        alignment=align,
    )
    status_box.addLayout(grid)
    outer.addWidget(status_frame)
    outer.addStretch()
    return screen


@pytest.mark.parametrize("state", PICTURE_STATES)
def test_the_two_sides_carry_one_skin(state):
    """The surface painted a different panel than the shipped one."""
    app()
    assert_same_skin(
        build_old_side=lambda: old_panel_for(state),
        build_new_side=lambda: widget_painted_by_the_model(model_payload(state)),
        size=PIXEL_SIZE,
        control_rule=CONTROL_RULE,
        note=state,
    )


@pytest.mark.parametrize("state", PICTURE_STATES)
def test_the_painted_panel_shows_more_than_one_colour(state):
    """The two sides matched because the panel painted one flat colour."""
    app()
    for side, widget in (
        ("old", old_panel_for(state)),
        ("new", widget_painted_by_the_model(model_payload(state))),
    ):
        found = assert_picture_can_report(
            render_offscreen(widget, PIXEL_SIZE), note=f"{state} {side}"
        )
        print(f"{state} {side} colours={found}")


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints."""
    app()
    assert_cases_paint_differently(
        old_side=render_offscreen(old_panel_for("idle"), PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload("empty")), PIXEL_SIZE
        ),
        note="an idle panel against one with no fleet",
    )


def test_the_control_rule_is_a_rule_neither_side_sets():
    """The control rule is one of the two sides' own, so it proves nothing."""
    written = [
        surface.card_style(),
        surface.header_card_style(),
        surface.start_button_style(),
        surface.stop_button_style(),
        surface.reload_button_style(),
        surface.section_label_style(),
        surface.title_style(),
        surface.status_label_style(),
        surface.status_value_style(),
        surface.small_text_style(surface.FLEET_BLUE),
    ]
    for style in written:
        assert CONTROL_RULE not in style, style
        assert "QWidget" not in style, style
    for text in (
        SHIPPED_SOURCE.read_text(encoding="utf-8"),
        SURFACE_SOURCE.read_text(encoding="utf-8"),
    ):
        assert "#7d1a4a" not in text
    assert "QWidget" in CONTROL_RULE


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on."""
    app()
    assert len(NARROW_LABEL) == len(WIDE_LABEL)
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert narrow != wide, "the host reports fonts and every glyph has one width"
    else:
        assert narrow == wide, "the host reports no fonts and the glyphs differ"


def test_the_two_sides_read_one_status_row_alike_whatever_the_host_paints():
    """A row differs, and only the picture would have said so.

    The two sides are read value for value here, never from a render, so
    the answer does not move with the host's fonts.
    """
    spec = picture_spec("running")
    old = drive_old(spec)["screen"]["status_text"]
    new = drive_new(spec)["screen"]["status_text"]
    assert old == new, (old, new)
    assert old["uptime_seconds"] == "42.5", old
    assert old["noise_pct"] == "17.5%", old
    assert old["load_multiplier"] == "2.25x", old
    assert old["total_candles"] == "21,000", old
    assert old["running"] == surface.RUNNING_TEXT, old


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload("idle")
    payload["buttons"]["start"]["text"] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(surface.build_view_model())


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def bridge_answer(params, request_id=1):
    from src.core.desktop_bridge import build_registry, handle_line

    return handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        build_registry(),
    )


def test_the_bridge_registers_the_nuclear_panel_method():
    """The renderer cannot reach the panel: nothing answers its method."""
    from src.core.desktop_bridge import build_registry

    registry = build_registry()
    assert surface.METHOD in registry, sorted(registry)
    assert registry[surface.METHOD] is surface.view_model
    assert surface.METHOD == "nuclear_mode_panel.state"


def test_the_bridge_answers_with_the_screen_the_surface_builds():
    """The bridge answers something other than the surface's own screen."""
    answered = bridge_answer({"bot_configs": BOTS, "smart_wires": WIRES})
    assert answered["ok"] is True, answered
    screen = answered["result"]["screen"]
    assert screen["fleet_card"]["detail"]["text"] == surface.fleet_summary(3, 2, 2)
    assert digest(screen) == digest(
        surface.build_view_model(bot_configs=BOTS, smart_wires=WIRES)
    )


def test_the_bridge_answer_is_json_serialisable():
    """The answer holds an object the renderer cannot read."""
    answered = bridge_answer({"bot_configs": BOTS})
    assert json.loads(json.dumps(answered))["ok"] is True


def test_the_bridge_reports_a_request_it_cannot_use():
    """A request the surface cannot use is answered as though it worked."""
    answered = bridge_answer({"cycle_candles": "not a number"})
    assert answered["ok"] is False, answered
    assert answered["error"]["type"] == "ValueError", answered


# ---------------------------------------------------------------------
# A fresh process: no Qt, no clock, no file, no thread, no connection
# ---------------------------------------------------------------------

PROBE = """
import json, os, sys, threading
sys.path.insert(0, %(repo)r)
import socket
reached = []
opened = []
_real_open = open


def _count(*a, **k):
    reached.append(a)
    return None


def _watch_open(*a, **k):
    opened.append(a[:1])
    return _real_open(*a, **k)


socket.socket.connect = _count
socket.socket.connect_ex = _count
socket.create_connection = _count
socket.getaddrinfo = _count
import builtins
builtins.open = _watch_open
%(prelude)s
opened_before = len(opened)
threads_before = threading.active_count()
from src.gui.main_tabs import nuclear_mode_panel_surface as s
world = s.PanelWorld(bot_configs=[{"symbol": "BTC-USD"}], loop=object(),
                     snapshots=[{"running": True, "uptime_seconds": 1.0}])
model = s.PanelModel(world)
s.run_steps(model, ["start", "refresh_status", "stop"])
s.view_model({})
%(extra)s
surface_qt = sorted(
    n for n in sys.modules
    if n.startswith("PySide6") and sys.modules[n] is not None
)[:1]
opened_by_surface = len(opened) - opened_before
threads_by_surface = threading.active_count() - threads_before
from src.core.desktop_bridge import build_registry, handle_line
answer = handle_line(
    json.dumps({"id": 7, "method": "nuclear_mode_panel.state", "params": {}}),
    build_registry(),
)
print(json.dumps({
    "qt": sorted(
        n for n in sys.modules
        if n.startswith("PySide6") and sys.modules[n] is not None
    )[:1],
    "surface_qt": surface_qt,
    "ok": answer["ok"],
    "title": answer["result"]["screen"]["header_card"]["title"]["text"]
        if answer["ok"] else None,
    "reached": len(reached),
    "opened": opened_by_surface,
    "threads": threads_by_surface,
    "scheduled": world.scheduled,
    "stops": world.stops,
}))
"""


def run_probe(prelude, extra=""):
    """Run one probe in a fresh process and return what it printed.

    `prelude` runs before the counters are read. `extra` runs inside the
    window they measure, which is where a planted read has to go for the
    counters to see it.
    """
    finished = subprocess.run(
        [sys.executable, "-"],
        input=(
            PROBE % {"repo": str(REPO_ROOT), "prelude": prelude, "extra": extra}
        ).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=90,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr.decode()
    return json.loads(finished.stdout.decode().strip().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """The surface pulls Qt in, so the frontend cannot run without it."""
    answered = run_probe("sys.modules['PySide6'] = None")
    assert answered["qt"] == [], answered
    assert answered["ok"] is True
    assert answered["title"] == surface.TITLE


def test_the_qt_probe_can_report_qt():
    """The probe reports no Qt whatever the process loaded."""
    answered = run_probe("import PySide6")
    assert answered["qt"] == ["PySide6"], answered


def test_a_whole_run_starts_no_thread_opens_no_file_and_runs_nothing():
    """A drive in a fresh process started a thread, a file or a real run."""
    answered = run_probe("")
    assert answered["threads"] == 0, answered
    assert answered["opened"] == 0, answered
    assert answered["scheduled"] == 1 and answered["stops"] == 1, answered
    assert answered["surface_qt"] == [], answered


def test_the_thread_counter_reports_a_thread_the_run_started():
    """The thread counter cannot see a thread, so its zero means nothing."""
    assert run_probe("")["threads"] == 0
    planted = run_probe(
        "",
        extra=(
            "import time as _t\n"
            "_held = threading.Thread(target=lambda: _t.sleep(30), daemon=True)\n"
            "_held.start()"
        ),
    )
    assert planted["threads"] == 1, planted


def test_the_file_counter_reports_a_file_the_run_opened():
    """The file counter cannot see an open, so its zero means nothing."""
    assert run_probe("")["opened"] == 0
    planted = run_probe(
        "", extra="_watch_open(%r).close()" % str(REPO_ROOT / "pyproject.toml")
    )
    assert planted["opened"] == 1, planted


def test_the_probe_counts_a_connection_the_child_tried_to_open():
    """The connection counter never reaches the child process."""
    clean = run_probe("")
    assert clean["reached"] == 0, clean
    dirty = run_probe("socket.getaddrinfo('localhost', 9)")
    assert dirty["reached"] == 1, dirty


def test_this_run_opens_no_connection_of_its_own(monkeypatch):
    """A drive reached the network.

    The counter below watches THIS process only. A connection a child
    process opened is caught by the probe above, inside that child.
    """
    reached = []

    def refuse(*args, **named):
        reached.append(args)
        raise AssertionError("this run tried to reach the network")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    for name in ("happy", "visuals", "empty_fleet", "finished"):
        assert digest(compared(drive_old(BY_NAME[name]))) == digest(
            compared(drive_new(BY_NAME[name]))
        )
    assert reached == [], reached
    with pytest.raises(AssertionError):
        refuse("a seeded call")
    assert len(reached) == 1


HOME_PROBE = """
import json, os, sys
from pathlib import Path
sys.path.insert(0, %(repo)r)
home = Path(os.environ["ACERVATOR_TEST_HOME"])
before = sorted(str(p) for p in home.rglob("*") if p.is_file())
from src.gui.main_tabs import nuclear_mode_panel_surface as s
seen = []
for configs in ([], [{"symbol": "BTC-USD"}]):
    world = s.PanelWorld(bot_configs=configs, loop=object(),
                         snapshots=[{"running": True, "uptime_seconds": 2.0}])
    model = s.PanelModel(world)
    s.run_steps(model, ["rescan_fleet", "start", "refresh_status", "stop"])
    seen.append(model.state()["fleet_detail"])
s.view_model({})
%(extra)s
after = sorted(str(p) for p in home.rglob("*") if p.is_file())
print(json.dumps({"before": len(before), "after": len(after), "seen": seen}))
"""


def run_home_probe(extra):
    """Drive the surface in a fresh process under a throwaway home."""
    home = Path(tempfile.mkdtemp(prefix="acervator-throwaway-home-"))
    environment = dict(os.environ)
    environment["ACERVATOR_TEST_HOME"] = str(home)
    finished = subprocess.run(
        [sys.executable, "-"],
        input=(HOME_PROBE % {"repo": str(REPO_ROOT), "extra": extra}).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=environment,
        timeout=90,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr.decode()
    return json.loads(finished.stdout.decode().strip().splitlines()[-1]), home


def test_a_whole_run_of_the_surface_creates_no_file():
    """The surface wrote a file, so a view model reached the disk."""
    answered, home = run_home_probe("")
    assert answered["before"] == 0
    assert answered["after"] == 0, answered
    assert answered["seen"][0] == surface.PLACEHOLDER
    assert answered["seen"][1] == surface.fleet_summary(1, 1, 0)
    assert list(home.rglob("*")) == []


def test_the_file_counter_reports_a_file_that_was_created():
    """The file counter cannot see a file, so its zero means nothing."""
    answered, home = run_home_probe('(home / "one.txt").write_bytes(b"1")')
    assert answered["before"] == 0
    assert answered["after"] == 1, answered
    assert [p.name for p in home.rglob("*")] == ["one.txt"]


class RefusingClock:
    """A clock that refuses every reading."""

    def __init__(self):
        self.asked = 0

    def __call__(self, *args, **named):
        self.asked += 1
        raise AssertionError("this run read the wall clock")

    def now(self, *args, **named):
        return self(*args, **named)


def test_neither_the_surface_nor_this_test_reads_the_wall_clock(monkeypatch):
    """A run read the clock, so its answer moves with the day."""
    trap = RefusingClock()
    monkeypatch.setattr(clock_module, "time", trap)
    monkeypatch.setattr(clock_module, "monotonic", trap)
    monkeypatch.setattr(clock_module, "perf_counter", trap)
    monkeypatch.setattr(datetime_module, "datetime", trap)
    for name in SPEC_NAMES:
        drive_new(BY_NAME[name])
    snapshot()
    surface.view_model({})
    assert trap.asked == 0, trap.asked
    with pytest.raises(AssertionError):
        clock_module.time()
    assert trap.asked == 1


def test_no_drive_leaves_a_thread_running():
    """A drive left a worker running into the next test."""
    before = threading.active_count()
    for name in ("happy", "finished", "visuals"):
        drive_old(BY_NAME[name])
        drive_new(BY_NAME[name])
    assert threading.active_count() == before, threading.enumerate()
    held = threading.Thread(target=lambda: None, daemon=True)
    held.start()
    held.join()
    assert threading.active_count() == before


# ---------------------------------------------------------------------
# The bare-reading audit
# ---------------------------------------------------------------------

AUDIT_VALUES = [
    ("true", True),
    ("not_a_number", float("nan")),
    ("infinity", float("inf")),
    ("minus_infinity", float("-inf")),
    ("text", "twelve"),
    ("numeric_text", "12.7"),
    ("decimal", 12.7),
    ("ten_to_the_400", 10**400),
]
AUDITED_KEYS = (
    "uptime_seconds",
    "noise_pct",
    "load_multiplier",
    "total_candles",
    "total_trades",
    "total_exceptions",
    "failed_cycles",
    "fleet_size",
    "wires_loaded",
    "current_cycle",
    "cycles_completed",
)


def audit_row(key, value):
    """What the shipped widget shows for `value` in `key` after one tick."""
    spec = Spec(
        f"audit_{key}", BOTS, WIRES, snapshots=[dict(FULL_SNAPSHOT, **{key: value})]
    )
    return drive_old(spec)["screen"]["status_text"][key]


def test_the_bare_reading_audit_is_reported():
    """Every number the panel reads out of stored state, with no guard."""
    rows = []
    for key in AUDITED_KEYS:
        for name, value in AUDIT_VALUES:
            shown = audit_row(key, value)
            rows.append((key, name, shown))
            print(f"audit {key:18} {name:16} -> {shown!r}")
    assert len(rows) == len(AUDITED_KEYS) * len(AUDIT_VALUES)
    shown = {row[2] for row in rows}
    assert len(shown) > 1, shown


@pytest.mark.parametrize("case", [name for name, _ in AUDIT_VALUES])
def test_the_audit_reads_the_same_on_both_sides(case):
    """The surface guards a bare reading the shipped panel does not."""
    value = dict(AUDIT_VALUES)[case]
    for key in AUDITED_KEYS:
        spec = Spec(
            f"audit_{key}_{case}",
            BOTS,
            WIRES,
            snapshots=[dict(FULL_SNAPSHOT, **{key: value})],
        )
        old = compared(drive_old(spec))
        new = compared(drive_new(spec))
        assert old == new, (key, case, old["screen"]["status_text"])


def test_a_stored_not_a_number_reaches_the_screen_as_text():
    """A stored not-a-number is silently clamped into a real-looking figure."""
    shown = audit_row("uptime_seconds", float("nan"))
    assert shown == "nan", shown
    assert audit_row("load_multiplier", float("inf")) == "infx"
    assert audit_row("total_trades", True) == "yes"
    assert audit_row("total_candles", "12.7") == "12.7"
    assert audit_row("uptime_seconds", 10**400) == surface.PLACEHOLDER
