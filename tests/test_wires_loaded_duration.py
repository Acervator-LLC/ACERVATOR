"""Pins the duration on `fleet.03.004.postcondition.wires_loaded`.

EMITTER is the sole pin in `load_smart_wires_from_state`, so there is no start
marker and no sibling to fence off. A `smart_wires` that is not a list returns
early and emits no record at all, which
`test_a_refused_load_emits_nothing_at_all` holds apart from a record carrying
no duration.
"""

from __future__ import annotations

import time
from typing import Optional

import pytest

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink
from src.simulator.fleet import bot_state_loader as bsl

EMITTER = "fleet.03.004.postcondition.wires_loaded"

SHORT_S = 0.005
LONG_S = 0.030

# Readings per workload. A scheduling pause can only add to an elapsed time,
# so the minimum of the samples is the closest estimate this machine can give.
SAMPLES = 5

# A bracket that spans no work reads under a microsecond, which `_tracks`
# accepts on ratio alone. `_tracks_the_load` adds this floor.
LONG_FLOOR_S = LONG_S / 2.0


def _busy_wait(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass


def _tracks(short: Optional[float], long_: Optional[float]) -> bool:
    if short is None or long_ is None:
        return False
    return long_ > short * 2.0


def _tracks_the_load(short: Optional[float], long_: Optional[float]) -> bool:
    """Ask `_tracks`, then put a floor under the long reading.

    This ADDS a condition and relaxes none: everything `_tracks`
    refuses is still refused here. The floor is the thing a ratio
    cannot do -- tell a real state read from a bracket that
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


def _drive(monkeypatch, burn_s: float, sink: SignalSink, payload=None) -> list:
    def _slow_read(_path):
        _busy_wait(burn_s)
        return {
            "smart_wires": (
                [{"source_id": "a", "target_id": "b", "pct": 1.0}]
                if payload is None
                else payload
            )
        }

    monkeypatch.setattr(bsl, "_read_state_file", _slow_read)
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        return bsl.load_smart_wires_from_state()
    finally:
        # Restore the PREVIOUS sink, never None — `set_sink` is process-global.
        sc.set_sink(previous)


def _durations(sink: SignalSink) -> list:
    return [r.duration for r in sink.records() if r.name == EMITTER]


def _fastest_load(monkeypatch, burn_s: float) -> Optional[float]:
    """The lowest duration `SAMPLES` real loads of cost `burn_s` record.

    Each sample is a whole real `load_smart_wires_from_state` call read
    back off the real emitter. Nothing is stubbed beyond the read the
    file already stubs, the clock is never touched and no recorded
    value is adjusted; the only thing added here is repetition. A
    `None` is returned as `None` rather than skipped, because a missing
    duration is a defect and must not be hidden by four healthy
    neighbours.
    """
    best: Optional[float] = None
    for _ in range(SAMPLES):
        sink = SignalSink()
        _drive(monkeypatch, burn_s, sink)
        got = _durations(sink)
        assert len(got) == 1, got
        if got[0] is None:
            return None
        best = got[0] if best is None else min(best, got[0])
    return best


def test_the_wires_emitter_carries_a_duration(monkeypatch):
    sink = SignalSink()
    _drive(monkeypatch, SHORT_S, sink)
    got = _durations(sink)
    assert len(got) == 1, got
    assert got[0] is not None


def test_the_duration_tracks_two_different_load_costs(monkeypatch):
    """THE control. Present-but-constant passes existence and fails this.

    Each workload is measured `SAMPLES` times and the MINIMUM of the
    samples is compared. A pause inside one bracketed region inflates
    that one sample and the minimum discards it. Nothing compared here
    is relaxed: both sides are still real durations read off the real
    emitter, and both must still clear the floor and the ratio.
    """
    short = _fastest_load(monkeypatch, SHORT_S)
    long_ = _fastest_load(monkeypatch, LONG_S)

    assert short == pytest.approx(SHORT_S, abs=0.005), short
    assert long_ == pytest.approx(LONG_S, abs=0.015), long_
    assert _tracks_the_load(short, long_), f"did not track: {short} vs {long_}"


def test_the_tracking_predicate_rejects_a_constant_duration():
    """The other half, so the control above cannot pass while measuring nothing."""
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
    assert not _tracks_the_load(
        0.01, 0.01
    ), "a constant duration must not read as tracking"
    assert not _tracks_the_load(
        None, LONG_S
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_load(
        SHORT_S, None
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_load(
        LONG_S, SHORT_S
    ), "going backwards must not read as tracking"

    # A dead-clock pair: `_tracks` accepts it and the floor rejects it.
    assert _tracks(
        0.0, 3.0e-07
    ), "the shared predicate is expected to accept a dead clock here"
    assert not _tracks_the_load(
        0.0, 3.0e-07
    ), "a bracket that spans no work must not read as tracking"

    # The honest pair measured off the real site, 2026-08-20, must
    # still read as tracking.
    assert _tracks_the_load(
        0.005000, 0.030000
    ), "the real measured pair must read as tracking"


def test_a_refused_load_emits_nothing_at_all(monkeypatch):
    """A malformed `smart_wires` returns early. No record, so no duration.

    Asserts the ABSENCE of a record rather than a None duration: those are
    different states and collapsing them would make "refused" look like
    "measured nothing".
    """
    sink = SignalSink()
    out = _drive(monkeypatch, SHORT_S, sink, payload="not-a-list")
    assert out == []
    assert _durations(sink) == [], "the refused path must not emit"
