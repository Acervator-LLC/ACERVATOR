"""Pins the duration on `sim.06.007.postcondition.fleet_spawned`.

Fifth of the six clean owners
(docs/engineering-notes/2026-08-19_emitter_duration_classification.md).

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

WHAT THE INTERVAL MUST NOT COVER. `_spawn_sim_fleet` imports the registry and
the controller lazily, INSIDE the function. On the first call in a process
those two imports run the interpreter's whole module-load path; on every call
after it they are served from `sys.modules` for nothing. Inside the bracket
that made record 1 incomparable to record 2 and the first spawn of a process
permanently the slow one. A test that only checks "a duration exists" cannot
see it, and a test process has already imported both modules, so the naive
version measures the cached case twice and proves nothing. The pin below makes
the re-import genuinely expensive by a known amount and asserts the duration
does not move.

BOTH EARLY RETURNS EMIT NOTHING (no configs, no candles). The test asserts the
ABSENCE of a record there, because "refused" and "measured nothing" are
different states.

Driven by calling the method UNBOUND against a stand-in. `FleetReplayPanel` is
a Qt widget; constructing one needs a QApplication, and the code under test
should be the shipping code rather than a copy of it.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from typing import Optional

import pytest

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink
from src.simulator.fleet import fleet_replay_controller as frc
from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel
from src.simulator.fleet import simulator_bot_state as sbs
from src.trading.stone_tablets import registry as tablet_registry

OWNER = "sim.06.007.postcondition.fleet_spawned"
SIBLINGS = ("sim.06.008.invariant.state_persisted", "sim.06.009.invariant.spawn_drift")

SHORT_S = 0.005
LONG_S = 0.030

# HOW MANY TIMES EACH WORKLOAD IS MEASURED, and why the figure compared
# is the MINIMUM of the samples rather than a single reading.
#
# A scheduling pause can only ADD to an elapsed-time reading. The
# operating system can take the thread away inside the bracketed region
# and hand it back later; it cannot hand back time that was never
# spent. So every sample is the true cost plus non-negative noise, and
# the smallest of several samples is the closest estimate of the true
# cost this machine can give. Averaging would not do it -- an average
# carries the noise it was given -- and raising the ratio would not do
# it either, because the ratio is not what is wrong.
#
# WHY THE CLASS NEEDED IT. On 2026-08-19 the release gate went red on
# the sibling of this test in tests/test_wires_received_duration.py:
# one failure in a 7012-test run, with the same file passing 45 times
# in isolation on the same commit. Reproduced 2026-08-20 by burning
# 1.5 ms inside the SHORT measurement, which is where a real scheduler
# pause would land. That is the whole failure: a single-sample
# measurement of a small interval, taken once, on a loaded Windows box
# with the live application trading.
#
# THIS SITE, MEASURED 2026-08-20, 60 single readings off the real
# emitter: a spawn levered at 0.005 s recorded 0.0100073 s to 0.0100317 s
# and one levered at 0.030 s recorded 0.0350065 s to 0.0350332 s.
# THIS IS THE TIGHTEST MARGIN OF THE SIX: the readings differ by
# 3.5x because BOTH carry the other lever's 0.005 s, and the
# predicate asks for 2. The lever is what the bracket is asked to see, so
# a pause of 7.5 ms inside the SHORT region is all it takes to close
# a gap that reads as comfortable.
SAMPLES = 5

# THE FLOOR, and the measurement that says it is not optional.
#
# Move the stop clock above the work and the bracket spans nothing:
# every reading collapses to the cost of two `time.monotonic()` calls,
# and a ratio between two numbers that small is a coin flip rather than
# a measurement. Measured 2026-08-20 with the stop clock planted above
# the work at this exact site, 120 readings: every reading fell between 0.0 s and 6.0e-07 s. The bare ratio
# ACCEPTED 6 of 30 pairs, and the minimum of five samples accepted 3 of 30.
#
# READ THAT SECOND FIGURE AGAIN. The minimum is the right estimator
# against a stall and it does NOT close the dead-clock hole; at some
# sites it widens it, because it drives the short reading to a hard
# zero and any positive long reading then beats twice zero. The floor
# is a SECOND rule, never an alternative to the first.
#
# Half the long lever separates the two populations by four orders of
# magnitude without standing near either.
LONG_FLOOR_S = LONG_S / 2.0

# The two modules `_spawn_sim_fleet` imports lazily, in the order it imports
# them. Named here so a rename breaks this test rather than silently turning
# the pin below into a no-op that still passes.
LAZY_IMPORTS = (
    "src.trading.stone_tablets.registry",
    "src.simulator.fleet.fleet_replay_controller",
)

# The cost this test INSTALLS on each of those imports. Chosen, not measured:
# the real figure is machine-specific (~0.48 s on the adversary's box) and an
# assertion against it would pass or fail on hardware.
IMPORT_DELAY_S = 0.120


def _busy_wait(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass


def _tracks(short: Optional[float], long_: Optional[float]) -> bool:
    if short is None or long_ is None:
        return False
    return long_ > short * 2.0


def _tracks_the_spawn(short: Optional[float], long_: Optional[float]) -> bool:
    """Ask `_tracks`, then put a floor under the long reading.

    This ADDS a condition and relaxes none: everything `_tracks`
    refuses is still refused here. The floor is the thing a ratio
    cannot do -- tell a real spawn from a bracket that
    measured two clock reads. See `LONG_FLOOR_S` for the harvested
    dead-clock readings that set it, and
    `test_the_site_predicate_rejects_a_bracket_that_spans_nothing`
    for this predicate driven in the failing direction.
    """
    if short is None or long_ is None:
        return False
    if long_ < LONG_FLOOR_S:
        return False
    return _tracks(short, long_)


class _Panel:
    """The minimum surface `_spawn_sim_fleet` touches."""

    def __init__(self, configs=None) -> None:
        self._configs = (
            configs
            if configs is not None
            else [{"symbol": "BTC/USD", "exchange_id": "coinbase"}]
        )
        self._smart_wires: list = []
        self._controller = None
        self._activity_log_cb = None
        self._performance_log_cb = None


@pytest.fixture(autouse=True)
def _sim_state_under_tmp_path(monkeypatch, tmp_path):
    """Keep the spawn's persistence off the operator's runtime tree.

    `_spawn_sim_fleet` ends by writing `simulator_bot_state.json`, and both
    `save_sim_state` and `load_sim_state` resolve that path from ONE root,
    read on every call. Redirecting that root here means every drive in this
    file persists under `tmp_path`; ~/.acervator is the operator's, and the
    suite does not write there.

    conftest already redirects the root for the whole session, so this is
    the second of two locks. It narrows the destination from one directory
    per SESSION to one per TEST, which is what this file's drives need.
    """
    monkeypatch.setenv(sbs.SIM_STATE_ROOT_ENV, str(tmp_path))


class _SlowLoader:
    """Hands back the module that was already loaded, expensively.

    Returning the ORIGINAL object is the point. A re-import that executed the
    module afresh would build a NEW module object and throw away the fakes
    `_install` patched onto the old one, so the spawn would reach the real
    registry and the real controller. This costs the delay, then yields the
    identical object the process had before -- nothing observable changes
    except the time the import took.
    """

    def __init__(self, module, delay_s: float) -> None:
        self._module = module
        self._delay_s = delay_s

    def create_module(self, _spec):
        _busy_wait(self._delay_s)
        return self._module

    def exec_module(self, _module) -> None:
        return None


class _SlowReimport:
    """Makes `_spawn_sim_fleet`'s two lazy imports genuinely expensive.

    Evicts them from `sys.modules` so the next `import` statement really goes
    through the import machinery, and fronts `sys.meta_path` so that machinery
    lands on `_SlowLoader` and pays `delay_s` per module.

    Everything it touches is process-global, so `restore` is exact and the
    fixture calls it from a `finally`.
    """

    def __init__(self, names, delay_s: float) -> None:
        self._names = tuple(names)
        self._delay_s = delay_s
        self._saved: dict = {}
        self._saved_attrs: dict = {}
        self._installed = False
        self.hits: list = []

    # -- sys.meta_path protocol ---------------------------------------
    # `_path` and `_target` are the finder protocol's second and third
    # positional arguments. The import machinery always passes them
    # positionally, and this finder answers from `fullname` alone, so they
    # are named as unused rather than silenced.
    def find_spec(self, fullname, _path=None, _target=None):
        module = self._saved.get(fullname)
        if module is None:
            return None
        self.hits.append(fullname)
        return importlib.util.spec_from_loader(
            fullname, _SlowLoader(module, self._delay_s)
        )

    # -- lifecycle ----------------------------------------------------
    def install(self) -> None:
        for name in self._names:
            module = sys.modules.get(name)
            # Not a convenience check: if the module were absent the eviction
            # would be a no-op, the import would run normally and the test
            # would measure nothing while still passing.
            assert module is not None, f"{name} is not imported; cannot evict"
            self._saved[name] = module
            self._saved_attrs[name] = (
                getattr(module, "__spec__", None),
                getattr(module, "__loader__", None),
            )
            del sys.modules[name]
        sys.meta_path.insert(0, self)
        self._installed = True

    def restore(self) -> None:
        if self._installed:
            try:
                sys.meta_path.remove(self)
            except ValueError:  # pragma: no cover
                pass
            self._installed = False
        for name, module in self._saved.items():
            sys.modules[name] = module
            # `module_from_spec` rewrote these on the way through the loader.
            spec, loader = self._saved_attrs[name]
            module.__spec__ = spec
            module.__loader__ = loader
        self._saved.clear()


@pytest.fixture()
def slow_reimport():
    """`_SlowReimport`, restored whether the test passes, fails or raises.

    The outer snapshot is belt AND braces: `install` mutates `sys.modules`
    before it touches `sys.meta_path`, so a failure part-way through would
    leave the process short a module for every test that runs after this one.
    """
    guard = _SlowReimport(LAZY_IMPORTS, IMPORT_DELAY_S)
    meta_before = list(sys.meta_path)
    mods_before = {n: sys.modules.get(n) for n in LAZY_IMPORTS}
    try:
        yield guard
    finally:
        guard.restore()
        sys.meta_path[:] = meta_before
        for name, module in mods_before.items():
            if module is None:  # pragma: no cover
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


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


def _drive(
    monkeypatch, sink, read_s=SHORT_S, build_s=SHORT_S, rows=(1, 2, 3), configs=None
) -> int:
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


def _fastest_spawn(monkeypatch, **lever) -> Optional[float]:
    """The lowest duration `SAMPLES` real spawns record at this lever.

    Each sample is a whole real `_spawn_sim_fleet` call read back off
    the real emitter. Nothing is stubbed beyond the two lazy imports
    the file already stubs, the clock is never touched and no recorded
    value is adjusted; the only thing added here is repetition. A
    `None` is returned as `None` rather than skipped, because a missing
    duration is a defect and must not be hidden by four healthy
    neighbours.
    """
    best: Optional[float] = None
    for _ in range(SAMPLES):
        sink = SignalSink()
        _drive(monkeypatch, sink, **lever)
        got = _durations(sink)
        assert len(got) == 1, got
        if got[0] is None:
            return None
        best = got[0] if best is None else min(best, got[0])
    return best


def test_the_spawn_emitter_carries_a_duration(monkeypatch):
    sink = SignalSink()
    _drive(monkeypatch, sink)
    got = _durations(sink)
    assert len(got) == 1, got
    assert got[0] is not None


def test_the_duration_tracks_the_build_cost(monkeypatch):
    """THE control, moved by the spawn itself.

    Each lever is measured `SAMPLES` times and the MINIMUM of the
    samples is compared. A pause inside one bracketed region inflates
    that one sample and the minimum discards it. Nothing compared here
    is relaxed: both sides are still real durations read off the real
    emitter, and both must still clear the floor and the ratio.
    """
    short = _fastest_spawn(monkeypatch, build_s=SHORT_S)
    long_ = _fastest_spawn(monkeypatch, build_s=LONG_S)

    assert _tracks_the_spawn(
        short, long_
    ), f"did not track the build: {short} vs {long_}"
    assert long_ == pytest.approx(LONG_S, abs=0.020), long_


def test_the_duration_also_tracks_the_tablet_read_cost(monkeypatch):
    """The bracket spans the candle load too, not just `_build_sim`.

    `sim.06.007` reports `missing_tablets`, so the tablet read is part of what
    it observes. If the clock started after the read this would not move.
    """
    short = _fastest_spawn(monkeypatch, read_s=SHORT_S)
    long_ = _fastest_spawn(monkeypatch, read_s=LONG_S)

    assert _tracks_the_spawn(
        short, long_
    ), f"did not track the read: {short} vs {long_}"


def test_the_tracking_predicate_rejects_a_constant_duration():
    """The other half, so the controls above cannot pass while measuring nothing."""
    assert not _tracks(0.01, 0.01)
    assert not _tracks(None, None)
    assert not _tracks(0.03, 0.005)
    assert _tracks(0.005, 0.030)


def test_the_site_predicate_rejects_a_bracket_that_spans_nothing() -> None:
    """The other half of the FLOOR, so it cannot pass while blind.

    A new predicate needs its own falsifier. Each line below is one way
    this site could be blinded while still handing the sink a
    `duration` field of exactly the right shape.
    """
    assert not _tracks_the_spawn(
        0.01, 0.01
    ), "a constant duration must not read as tracking"
    assert not _tracks_the_spawn(
        None, LONG_S
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_spawn(
        SHORT_S, None
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_spawn(
        LONG_S, SHORT_S
    ), "going backwards must not read as tracking"

    # THE DEAD CLOCK, and the measured reason this site carries a floor
    # the shared predicate does not. This pair is a real one, harvested
    # 2026-08-20 with the stop clock planted above the work. `_tracks`
    # accepts it. The floor rejects it. That is an addition to
    # `_tracks`, never a relaxation of it.
    assert _tracks(
        0.0, 6.0e-07
    ), "the shared predicate is expected to accept a dead clock here"
    assert not _tracks_the_spawn(
        0.0, 6.0e-07
    ), "a bracket that spans no work must not read as tracking"

    # The honest pair measured off the real site, 2026-08-20, must
    # still read as tracking.
    assert _tracks_the_spawn(
        0.0100073, 0.0350065
    ), "the real measured pair must read as tracking"


@pytest.mark.parametrize("sibling", SIBLINGS)
def test_a_sibling_never_claims_the_spawn_duration(monkeypatch, sibling):
    """Finding 1. Whether or not the sibling fires, it must never carry one."""
    sink = SignalSink()
    _drive(monkeypatch, sink)
    assert all(
        d is None for d in _durations(sink, sibling)
    ), f"{sibling} claimed a duration it does not own"


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


def _drive_cold(monkeypatch, sink, guard) -> float:
    """One spawn with both lazy imports evicted. Returns the WALL time.

    Deliberately not routed through `_drive`: the eviction has to happen
    after `_install` has patched the fakes onto the modules and immediately
    before the call, and the wall clock has to bracket the call itself.

    No Qt here. `_spawn_sim_fleet` is driven unbound against `_Panel`, so
    nothing pumps an event loop and no queued work can widen the reading.
    """
    _install(monkeypatch, SHORT_S, SHORT_S)
    previous = sc.get_sink()
    sc.set_sink(sink)
    guard.install()
    t0 = time.monotonic()
    try:
        FleetReplayPanel._spawn_sim_fleet(_Panel())
    finally:
        wall = time.monotonic() - t0
        guard.restore()
        sc.set_sink(previous)
    return wall


def test_the_duration_excludes_the_cost_of_its_own_lazy_imports(
    monkeypatch, slow_reimport
):
    """THE pin. The clock must start BELOW the two `import` statements.

    Warm spawn and cold spawn do the same amount of spawn work -- same fake
    registry, same fake controller, same `SHORT_S` on each. The ONLY
    difference is that the cold one re-runs both imports at a cost this test
    installs. If the bracket starts above them, the cold duration carries
    `2 * IMPORT_DELAY_S` that is not spawn work and that no later call in the
    process will ever pay again.
    """
    sink = SignalSink()

    _drive(monkeypatch, sink)  # warm: imports are cached
    wall = _drive_cold(monkeypatch, sink, slow_reimport)

    # POSITIVE CONTROL, before reading the durations at all. A zero here
    # would be a statement about the instrument, not about the code: if the
    # eviction or the finder silently did nothing, the two spawns are
    # identical and the assertion below passes while measuring nothing.
    assert sorted(slow_reimport.hits) == sorted(
        LAZY_IMPORTS
    ), f"the finder did not serve both imports: {slow_reimport.hits}"
    injected = IMPORT_DELAY_S * len(LAZY_IMPORTS)
    assert wall >= injected * 0.8, (
        f"the cold spawn only took {wall:.3f}s wall, so the {injected:.3f}s "
        f"of import cost was never actually paid"
    )

    warm, cold = _durations(sink)
    assert warm is not None and cold is not None
    assert cold - warm < IMPORT_DELAY_S, (
        f"the duration grew by {cold - warm:.3f}s when the only thing that "
        f"changed was {injected:.3f}s of module loading: the clock starts "
        f"above the lazy imports, so record 1 of a process is inflated and "
        f"is not comparable to record 2"
    )


def test_the_cold_spawn_still_reports_the_spawn_work(monkeypatch, slow_reimport):
    """The other half: excluding the imports must not exclude the spawn.

    A clock started after `_build_sim` would also pass the pin above -- it
    would be immune to import cost by measuring nothing. This drives the
    build knob under the SAME cold-import conditions and requires the
    duration to follow it.
    """
    sink = SignalSink()

    _install(monkeypatch, SHORT_S, LONG_S)
    previous = sc.get_sink()
    sc.set_sink(sink)
    slow_reimport.install()
    try:
        FleetReplayPanel._spawn_sim_fleet(_Panel())
    finally:
        slow_reimport.restore()
        sc.set_sink(previous)

    assert sorted(slow_reimport.hits) == sorted(
        LAZY_IMPORTS
    ), f"the finder did not serve both imports: {slow_reimport.hits}"
    (cold,) = _durations(sink)
    assert cold is not None
    assert (
        cold >= LONG_S * 0.8
    ), f"cold duration {cold:.3f}s did not contain the {LONG_S:.3f}s build"


def test_the_reimport_guard_leaves_the_process_as_it_found_it(slow_reimport):
    """The fixture's own control.

    `sys.modules` and `sys.meta_path` are process-global. If the guard leaked
    either, every test after this one in the same process would be running in
    a corrupted interpreter, and the failure would surface somewhere else.
    """
    meta_before = list(sys.meta_path)
    mods_before = {n: sys.modules[n] for n in LAZY_IMPORTS}

    slow_reimport.install()
    assert slow_reimport in sys.meta_path
    assert all(n not in sys.modules for n in LAZY_IMPORTS)

    slow_reimport.restore()
    assert sys.meta_path == meta_before
    assert {n: sys.modules[n] for n in LAZY_IMPORTS} == mods_before
