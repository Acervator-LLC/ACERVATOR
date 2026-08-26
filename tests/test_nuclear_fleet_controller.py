"""v3.24.30 — pin tests for Nuclear Mode v2 (fleet soak).

Operator directive 2026-08-05:

    "Nuclear Mode does not run singular tapes. It runs full Stone
    Tablets in loop across the fleet loaded from bot_state."

WHAT THESE PIN
==============
The load oscillation, mostly — because it is the part that looked
correct while doing nothing, twice:

1. The sensor interface was GUESSED rather than read. The oscillator's
   monitor thread calls ``sample(now)`` then reads the
   ``current_regime`` attribute; the first sensor exposed ``regime()``
   and a property instead, so every sample raised AttributeError and
   COOLING never engaged — while the run still reported
   ``load_sensed: True``. A dead safety mechanism that reports itself
   as live is worse than an absent one.

2. ``is_cooling`` is a PROPERTY. Calling it as ``is_cooling()`` raises
   TypeError, which the surrounding guard swallowed, pinning the load
   multiplier to 1.0x for an entire soak.

3. The multiplier was reported but never applied. Measured: throughput
   held at ~25.8 c/s while the multiplier swept 0.99x -> 3.14x. Load is
   now applied as CONCURRENCY, because tick_delay only adds idle time —
   scaling it would have made a "4x load" pulse quieter, not busier.

SAFETY
======
A 4x pulse shares a machine with the live trading engine, so an
unsensed run must stay capped. That is asserted, not assumed.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.core.system_load_oscillator import (  # noqa: E402
    SystemLoadOscillator,
)
from src.simulator.nuclear_fleet_controller import (  # noqa: E402
    UNSENSED_LOAD_CAP,
    NuclearCycle,
    NuclearFleetController,
    _make_oscillator,
)

# ── the sensor contract ──────────────────────────────────────────


def test_sensor_matches_what_the_oscillator_actually_calls():
    """Regression pin for the guessed interface.

    The monitor thread calls sample(now) and then reads the
    current_regime ATTRIBUTE. A sensor missing either of those makes
    COOLING dead while still reporting sensed=True.
    """
    osc, sensed = _make_oscillator()
    if not sensed:
        return  # psutil absent on this machine; nothing to pin
    sensor = osc._sysmr
    assert hasattr(
        sensor, "sample"
    ), "oscillator calls sample(now); sensor does not provide it"
    sensor.sample(0.0)
    assert isinstance(
        sensor.current_regime, str
    ), "current_regime must be an attribute holding a string"
    assert sensor.current_regime in ("CALM", "STRESS", "CRITICAL")


def test_monitor_thread_actually_samples():
    """If the sensor interface is wrong, samples_taken stays 0 while
    the run still claims the load is sensed."""
    import time

    osc, sensed = _make_oscillator()
    if not sensed:
        return
    osc.start()
    try:
        time.sleep(0.8)
        assert (
            osc.samples_taken > 0
        ), "monitor thread took zero samples — COOLING is dead"
    finally:
        osc.stop()


def test_is_cooling_is_read_as_a_property():
    """Calling it would raise TypeError and get swallowed, pinning
    load to 1.0x for the whole soak."""
    osc = SystemLoadOscillator(None)
    assert isinstance(osc.is_cooling, bool)


# ── load application ─────────────────────────────────────────────


def test_unsensed_load_is_capped():
    """An unmonitored 4x pulse shares the machine with live trading."""
    c = NuclearFleetController(load_oscillation=True, seed=1)
    c._osc = SystemLoadOscillator(None)
    c._osc.start()
    try:
        c._sensed = False
        for _ in range(40):
            mult, _cool = c._current_load()
            assert mult <= UNSENSED_LOAD_CAP + 1e-9, (
                f"unsensed multiplier {mult} exceeds the " f"{UNSENSED_LOAD_CAP}x cap"
            )
    finally:
        c._osc.stop()


def test_load_has_a_floor():
    """A multiplier at or below zero would mean no work at all."""
    c = NuclearFleetController(seed=3)
    c._osc = SystemLoadOscillator(None)
    c._osc.start()
    try:
        c._sensed = True
        for _ in range(40):
            assert c._current_load()[0] >= 0.25
    finally:
        c._osc.stop()


def test_no_oscillator_means_flat_load():
    c = NuclearFleetController(load_oscillation=False)
    assert c._current_load() == (1.0, False)


def test_jitter_varies_between_reads():
    """Cosine supplies smoothness; jitter supplies the noise, so two
    cycles never present identical load."""
    c = NuclearFleetController(seed=5)
    c._osc = SystemLoadOscillator(None)
    c._osc.start()
    try:
        c._sensed = True
        seen = {round(c._current_load()[0], 6) for _ in range(25)}
        assert len(seen) > 1, "load multiplier never varied"
    finally:
        c._osc.stop()


# ── cycle bookkeeping ────────────────────────────────────────────


def test_cycle_reports_rate_and_workers():
    cyc = NuclearCycle(index=1)
    cyc.elapsed_s = 4.0
    cyc.candles_played = 800
    cyc.workers = 4
    d = cyc.to_dict()
    assert d["candles_per_s"] == 200.0
    assert d["workers"] == 4
    assert d["cycle"] == 1


def test_zero_elapsed_does_not_divide_by_zero():
    assert NuclearCycle(index=1).to_dict()["candles_per_s"] is None


def test_cycle_with_error_is_not_ok():
    cyc = NuclearCycle(index=2)
    assert cyc.ok
    cyc.error = "boom"
    assert not cyc.ok


# ── refusal paths ────────────────────────────────────────────────


def test_start_refuses_without_a_fleet(monkeypatch):
    """A run that cannot start must say why, not raise."""
    import src.simulator.fleet.bot_state_loader as bsl

    monkeypatch.setattr(bsl, "load_bot_configs_from_state", lambda *_args, **_kw: [])
    msgs: list = []
    c = NuclearFleetController(activity_cb=msgs.append)
    assert c.prepare() is False
    assert any("no scrumming bots" in m for m in msgs), msgs


def test_start_is_idempotent_while_running():
    c = NuclearFleetController()
    c.state.running = True
    assert asyncio.run(c.start()) is False


def test_snapshot_is_plain_data():
    """The GUI polls this on a timer; it must never carry live objects."""
    snap = NuclearFleetController().snapshot()
    allowed = (str, int, float, bool, type(None))
    for k, v in snap.items():
        assert isinstance(v, allowed), f"{k} is {type(v)!r}"
