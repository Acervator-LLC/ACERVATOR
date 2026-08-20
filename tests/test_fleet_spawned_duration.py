"""Pins the duration on `sim.06.007.postcondition.fleet_spawned`.

Fifth of the six clean owners
(docs/audits/2026-08-19_emitter_duration_classification.md).

`_spawn_sim_fleet` holds THREE emitters and only `sim.06.007` claims the
interval. `sim.06.008` and `sim.06.009` are invariants over persisted state and
carry NOTHING -- Finding 1: 32 of the 40 emitters share an enclosing function,
and if each claimed that function's elapsed time they would report the SAME
number, a fabricated distinction item 17 would read as health.

WHAT THE INTERVAL COVERS. `sim.06.007` carries `missing_tablets` in its
context, so the operation it observes includes LOADING CANDLES from the tablet
registry, not merely constructing the controller. Both knobs below -- tablet
read cost and `_build_sim` cost -- therefore move the same duration, and the
tests drive each independently to prove the bracket spans both.

BOTH EARLY RETURNS EMIT NOTHING (no configs, no candles). The test asserts the
ABSENCE of a record there, because "refused" and "measured nothing" are
different states.

Driven by calling the method UNBOUND against a stand-in. `FleetReplayPanel` is
a Qt widget; constructing one needs a QApplication, and the code under test
should be the shipping code rather than a copy of it.
"""

from __future__ import annotations

import time
from typing import Optional

import pytest

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink
from src.gui.simulator_tab.fleet import fleet_replay_controller as frc
from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel
from src.trading.stone_tablets import registry as tablet_registry

OWNER = "sim.06.007.postcondition.fleet_spawned"
SIBLINGS = ("sim.06.008.invariant.state_persisted",
            "sim.06.009.invariant.spawn_drift")

SHORT_S = 0.005
LONG_S = 0.030


def _busy_wait(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass


def _tracks(short: Optional[float], long_: Optional[float]) -> bool:
    if short is None or long_ is None:
        return False
    return long_ > short * 2.0


class _Panel:
    """The minimum surface `_spawn_sim_fleet` touches."""

    def __init__(self, configs=None) -> None:
        self._configs = configs if configs is not None else [
            {"symbol": "BTC/USD", "exchange_id": "coinbase"}]
        self._smart_wires: list = []
        self._controller = None
        self._activity_log_cb = None
        self._performance_log_cb = None


def _install(monkeypatch, read_s: float, build_s: float, rows=(1, 2, 3)):
    """Replace the two lazy imports with fakes of known cost."""

    class _Reg:
        def get_candles(self, **_kwargs):
            _busy_wait(read_s)
            return list(rows)

    class _Controller:
        def __init__(self, **_kwargs):
            self._bots = []

        def _build_sim(self):
            _busy_wait(build_s)
            self._bots = [object()]

    monkeypatch.setattr(tablet_registry, "get_registry", lambda: _Reg())
    monkeypatch.setattr(frc, "FleetReplayController", _Controller)


def _drive(monkeypatch, sink, read_s=SHORT_S, build_s=SHORT_S,
           rows=(1, 2, 3), configs=None) -> int:
    _install(monkeypatch, read_s, build_s, rows)
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        return FleetReplayPanel._spawn_sim_fleet(_Panel(configs))
    finally:
        # Restore the PREVIOUS sink, never None — `set_sink` is process-global.
        sc.set_sink(previous)


def _durations(sink: SignalSink, name: str = OWNER) -> list:
    return [r.duration for r in sink.records() if r.name == name]


def test_the_spawn_emitter_carries_a_duration(monkeypatch):
    sink = SignalSink()
    _drive(monkeypatch, sink)
    got = _durations(sink)
    assert len(got) == 1, got
    assert got[0] is not None


def test_the_duration_tracks_the_build_cost(monkeypatch):
    """THE control, moved by the spawn itself."""
    sink = SignalSink()
    _drive(monkeypatch, sink, build_s=SHORT_S)
    _drive(monkeypatch, sink, build_s=LONG_S)

    short, long_ = _durations(sink)
    assert _tracks(short, long_), f"did not track the build: {short} vs {long_}"
    assert long_ == pytest.approx(LONG_S, abs=0.020), long_


def test_the_duration_also_tracks_the_tablet_read_cost(monkeypatch):
    """The bracket spans the candle load too, not just `_build_sim`.

    `sim.06.007` reports `missing_tablets`, so the tablet read is part of what
    it observes. If the clock started after the read this would not move.
    """
    sink = SignalSink()
    _drive(monkeypatch, sink, read_s=SHORT_S)
    _drive(monkeypatch, sink, read_s=LONG_S)

    short, long_ = _durations(sink)
    assert _tracks(short, long_), f"did not track the read: {short} vs {long_}"


def test_the_tracking_predicate_rejects_a_constant_duration():
    """The other half, so the controls above cannot pass while measuring nothing."""
    assert not _tracks(0.01, 0.01)
    assert not _tracks(None, None)
    assert not _tracks(0.03, 0.005)
    assert _tracks(0.005, 0.030)


@pytest.mark.parametrize("sibling", SIBLINGS)
def test_a_sibling_never_claims_the_spawn_duration(monkeypatch, sibling):
    """Finding 1. Whether or not the sibling fires, it must never carry one."""
    sink = SignalSink()
    _drive(monkeypatch, sink)
    assert all(d is None for d in _durations(sink, sibling)), (
        f"{sibling} claimed a duration it does not own")


def test_a_spawn_with_no_configs_emits_nothing(monkeypatch):
    """An early return. No record, so no duration -- and no false silence."""
    sink = SignalSink()
    assert _drive(monkeypatch, sink, configs=[]) == 0
    assert _durations(sink) == []


def test_a_spawn_with_no_tablets_emits_nothing(monkeypatch):
    """The second early return: configs exist but no candles were found."""
    sink = SignalSink()
    assert _drive(monkeypatch, sink, rows=()) == 0
    assert _durations(sink) == []
