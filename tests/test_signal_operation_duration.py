"""Pins `Signal.duration` — 10.3 phase 2, the OPERATION duration.

WHAT THIS IS NOT. `Signal.dt` already ships and is pinned by
`test_signal_timing.py`. `dt` is CADENCE, the gap BETWEEN successive emissions
of the same identity. `duration` is LATENCY, how long the observed operation
took. For item 17's health, cadence answers "on time" and "hangs"; duration is
what answers "slow downs". A record may honestly carry one, both, or neither,
and these tests hold that line so the two are never conflated again.

THE ONE CONTROL IS THAT DURATION **TRACKS**. Absent before, present after, and
two DIFFERENT known intervals producing two DIFFERENT recorded values. A
duration that is present but constant passes an existence check and fails this
one, so the tracking predicate is itself driven in both directions here — see
`test_the_tracking_predicate_rejects_a_constant_duration`. A check never shown
failing proves nothing.

WHY `None` AND NOT `0.0`. Measured 2026-08-19: 23 of the 40 emitters are
instantaneous observations where a duration would be FABRICATED, and a
fabricated duration is worse than a missing one because item 17 computes health
from it. Zero reads as "instantaneous", which is a measurement; there was none.
See docs/audits/2026-08-19_emitter_duration_classification.md.
"""

from __future__ import annotations

import json
import time
from typing import Optional

import pytest

from src.core.signal_contract import Signal, SignalSink

# Two intervals far enough apart that no plausible scheduler jitter can
# reorder them. Measured clock resolution on the target machine is 1e-07.
SHORT_S = 0.005
LONG_S = 0.030


def _busy_wait(seconds: float) -> None:
    """Burn a known interval on the monotonic clock.

    `time.sleep` yields to the scheduler and on Windows can overshoot by a
    whole tick, which would make the two intervals noisy rather than known.
    """
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass


def _tracks(short: Optional[float], long_: Optional[float]) -> bool:
    """The predicate the control turns on: did the duration MOVE with the work.

    Deliberately a named function so the same rule can be driven in both
    directions. Requiring only `!=` would pass on two values that differ by a
    float wobble, so this asks that the longer operation record a materially
    longer duration.
    """
    if short is None or long_ is None:
        return False
    return long_ > short * 2.0


# ── the field itself ──────────────────────────────────────────────────


def test_an_emitter_that_measures_nothing_records_none_not_zero():
    """The 23 instantaneous emitters must land here, and zero is a lie."""
    sink = SignalSink()
    sink.emit("probe.99.001.counter.instant", actual=1)
    rec = sink.records()[-1]
    assert rec.duration is None
    assert rec.duration != 0.0


def test_a_measured_duration_is_carried_verbatim():
    sink = SignalSink()
    sink.emit("probe.99.002.postcondition.op", actual=1, expected=1,
              duration=0.25)
    assert sink.records()[-1].duration == 0.25


def test_duration_and_dt_are_independent_fields():
    """The conflation this whole unit exists to prevent.

    A first emission has NO cadence (`dt is None`) and can still carry a real
    duration. If one field ever derives from the other, this fails.
    """
    sink = SignalSink()
    sink.emit("probe.99.003.postcondition.op", actual=1, duration=0.5)
    rec = sink.records()[-1]
    assert rec.dt is None, "first emission has no interval"
    assert rec.nth == 1
    assert rec.duration == 0.5


# ── THE CONTROL: it tracks ────────────────────────────────────────────


def test_the_duration_tracks_two_different_known_intervals():
    """THE control. Present-but-constant fails this; existence checks do not."""
    sink = SignalSink()

    t0 = time.monotonic()
    _busy_wait(SHORT_S)
    sink.emit("probe.99.010.postcondition.op", actual=1,
              duration=time.monotonic() - t0)

    t0 = time.monotonic()
    _busy_wait(LONG_S)
    sink.emit("probe.99.011.postcondition.op", actual=1,
              duration=time.monotonic() - t0)

    short, long_ = (r.duration for r in sink.records()[-2:])
    assert short == pytest.approx(SHORT_S, abs=0.004), short
    assert long_ == pytest.approx(LONG_S, abs=0.010), long_
    assert _tracks(short, long_), f"did not track: {short} vs {long_}"


def test_the_tracking_predicate_rejects_a_constant_duration():
    """The other half. A blinded mechanism must FAIL the control above.

    Without this, `_tracks` could return True unconditionally and the test
    above would pass while measuring nothing.
    """
    assert not _tracks(0.01, 0.01), "a constant duration must not read as tracking"
    assert not _tracks(None, None), "an absent duration must not read as tracking"
    assert not _tracks(0.03, 0.005), "going backwards must not read as tracking"
    assert _tracks(0.005, 0.030), "a real increase must read as tracking"


# ── persistence: a field the writer does not enumerate is a lost field ──


def test_the_duration_survives_a_json_round_trip():
    """The writer enumerates keys explicitly, so a new field can be dropped."""
    sink = SignalSink()
    sink.emit("probe.99.020.postcondition.op", actual=1, duration=0.125)
    payload = json.loads(sink.records()[-1].to_json())
    assert "duration" in payload, "the writer dropped the field"
    assert payload["duration"] == 0.125


def test_a_record_written_before_this_field_existed_reads_back_as_none():
    """ABSENT IS NOT ZERO — the same discipline `dt` already holds.

    Every record already on the operator's disk was written without this key.
    Restoring them as 0.0 would claim every legacy operation was instantaneous.
    """
    legacy = json.loads(Signal(name="x.00.000.counter.y", site="f:1",
                               actual=1).to_json())
    legacy.pop("duration", None)
    assert "duration" not in legacy
    restored = Signal(name=legacy["name"], site=legacy["site"],
                      actual=legacy["actual"])
    assert restored.duration is None


# ── Finding 1: one operation, one owner ───────────────────────────────


def test_a_sibling_emitter_in_the_same_function_does_not_claim_the_duration():
    """32 of 40 emitters share a function with another.

    If each claimed its enclosing function's elapsed time they would all report
    the SAME number, which is a fabricated distinction that item 17 would read
    as health. Only the emitter that owns the operation carries it.
    """
    sink = SignalSink()
    owner_duration = 0.042
    sink.emit("probe.99.030.postcondition.owns_it", actual=1,
              duration=owner_duration)
    sink.emit("probe.99.031.postcondition.sibling", actual=1)

    owner, sibling = sink.records()[-2:]
    assert owner.duration == owner_duration
    assert sibling.duration is None, (
        "a sibling in the same operation must not repeat the owner's duration")


# ── end to end through the first real emitter ─────────────────────────


def test_ta_07_003_carries_a_duration_that_tracks_the_real_compute():
    """The first of the six wired: `ta.07.003.postcondition.computed`.

    Drives the real `VotingEngine.compute_all` with stub indicators that burn
    two DIFFERENT known intervals, and reads the duration off the real record.
    A source scan proving the argument is passed would not catch a sink that
    swallowed it, or a timer bracketing the emit instead of the work.
    """
    from src.core import signal_contract as sc
    from src.trading.ta_engine import (
        Signal as TASignal, SignalDirection, VotingEngine)

    class _Burn:
        """An indicator whose only job is to take a known amount of time."""

        weight = 1.0

        def __init__(self, secs: float) -> None:
            self.secs = secs

        def compute(self, _candles, timeframe="1h"):
            _busy_wait(self.secs)
            return TASignal(indicator="stub", timeframe=timeframe,
                            direction=SignalDirection.NEUTRAL,
                            confidence=0.5)

    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        engine = VotingEngine()
        for secs in (SHORT_S, LONG_S):
            engine._indicators = [_Burn(secs)]
            engine.compute_all([], "1h")
    finally:
        # RESTORE THE PREVIOUS SINK, never None. `set_sink` is process-global
        # and ta_engine gates its whole instrumentation block on the sink
        # being installed, so leaking one silently changes the code path for
        # every test module collected afterwards.
        sc.set_sink(previous)

    computed = [r for r in sink.records()
                if r.name == "ta.07.003.postcondition.computed"]
    assert len(computed) == 2, computed

    short, long_ = (r.duration for r in computed)
    assert _tracks(short, long_), f"did not track the real compute: {short} vs {long_}"
    assert short == pytest.approx(SHORT_S, abs=0.005), short
    assert long_ == pytest.approx(LONG_S, abs=0.015), long_

    # Finding 1, held in the live path: no other emitter in that function
    # repeats the owner's interval.
    assert not [r for r in sink.records()
                if r.name != "ta.07.003.postcondition.computed"
                and r.duration is not None]
