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

from src.core.signal_contract import Signal, SignalSink, read_records

# Two intervals far enough apart that no plausible scheduler jitter can
# reorder them. Measured clock resolution on the target machine is 1e-07.
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
# emitter: a 0.005 s compute recorded 0.0050007 s to 0.0050099 s and a
# 0.030 s compute recorded 0.0300008 s to 0.0300244 s. The lever is what the bracket is asked to see, so
# a pause of 10 ms inside the SHORT region is all it takes to close
# a gap that reads as comfortable.
SAMPLES = 5

# THE FLOOR, and the measurement that says it is not optional.
#
# Move the stop clock above the work and the bracket spans nothing:
# every reading collapses to the cost of two `time.monotonic()` calls,
# and a ratio between two numbers that small is a coin flip rather than
# a measurement. Measured 2026-08-20 with the stop clock planted above
# the work at this exact site, 120 readings: every reading fell between 0.0 s and 3.0e-07 s. The bare ratio
# ACCEPTED 2 of 30 pairs, and the minimum of five samples accepted 6 of 30.
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


def _tracks_the_operation(short: Optional[float], long_: Optional[float]) -> bool:
    """Ask `_tracks`, then put a floor under the long reading.

    This ADDS a condition and relaxes none: everything `_tracks`
    refuses is still refused here. The floor is the thing a ratio
    cannot do -- tell a real operation from a bracket that
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


def _fastest_probe(name: str, burn_s: float) -> Optional[float]:
    """The lowest of `SAMPLES` self-timed brackets around `burn_s`.

    Every sample is written to a sink and read back, so the value
    compared still travelled through `emit`. The clock is never touched
    and no recorded value is adjusted; the only thing added here is
    repetition.
    """
    best: Optional[float] = None
    for _ in range(SAMPLES):
        sink = SignalSink()
        t0 = time.monotonic()
        _busy_wait(burn_s)
        sink.emit(name, actual=1, duration=time.monotonic() - t0)
        got = sink.records()[-1].duration
        if got is None:
            return None
        best = got if best is None else min(best, got)
    return best


def test_an_emitter_that_measures_nothing_records_none_not_zero():
    """The 23 instantaneous emitters must land here, and zero is a lie."""
    sink = SignalSink()
    sink.emit("probe.99.001.counter.instant", actual=1)
    rec = sink.records()[-1]
    assert rec.duration is None
    assert rec.duration != 0.0


def test_a_measured_duration_is_carried_verbatim():
    sink = SignalSink()
    sink.emit("probe.99.002.postcondition.op", actual=1, expected=1, duration=0.25)
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
    """THE control. Present-but-constant fails this; existence checks do not.

    Each interval is measured `SAMPLES` times and the MINIMUM of the
    samples is compared. A pause inside one bracketed region inflates
    that one sample and the minimum discards it. Nothing compared here
    is relaxed: both sides are still real durations that travelled
    through `emit`, and both must still clear the floor and the ratio.
    """
    short = _fastest_probe("probe.99.010.postcondition.op", SHORT_S)
    long_ = _fastest_probe("probe.99.011.postcondition.op", LONG_S)

    assert short == pytest.approx(SHORT_S, abs=0.004), short
    assert long_ == pytest.approx(LONG_S, abs=0.010), long_
    assert _tracks_the_operation(short, long_), f"did not track: {short} vs {long_}"


def test_the_tracking_predicate_rejects_a_constant_duration():
    """The other half. A blinded mechanism must FAIL the control above.

    Without this, `_tracks` could return True unconditionally and the test
    above would pass while measuring nothing.
    """
    assert not _tracks(0.01, 0.01), "a constant duration must not read as tracking"
    assert not _tracks(None, None), "an absent duration must not read as tracking"
    assert not _tracks(0.03, 0.005), "going backwards must not read as tracking"
    assert _tracks(0.005, 0.030), "a real increase must read as tracking"


def test_the_site_predicate_rejects_a_bracket_that_spans_nothing() -> None:
    """The other half of the FLOOR, so it cannot pass while blind.

    A new predicate needs its own falsifier. Each line below is one way
    this site could be blinded while still handing the sink a
    `duration` field of exactly the right shape.
    """
    assert not _tracks_the_operation(
        0.01, 0.01
    ), "a constant duration must not read as tracking"
    assert not _tracks_the_operation(
        None, LONG_S
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_operation(
        SHORT_S, None
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_operation(
        LONG_S, SHORT_S
    ), "going backwards must not read as tracking"

    # THE DEAD CLOCK, and the measured reason this site carries a floor
    # the shared predicate does not. This pair is a real one, harvested
    # 2026-08-20 with the stop clock planted above the work. `_tracks`
    # accepts it. The floor rejects it. That is an addition to
    # `_tracks`, never a relaxation of it.
    assert _tracks(
        0.0, 3.0e-07
    ), "the shared predicate is expected to accept a dead clock here"
    assert not _tracks_the_operation(
        0.0, 3.0e-07
    ), "a bracket that spans no work must not read as tracking"

    # The honest pair measured off the real site, 2026-08-20, must
    # still read as tracking.
    assert _tracks_the_operation(
        0.0050007, 0.0300008
    ), "the real measured pair must read as tracking"


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
    legacy = json.loads(
        Signal(name="x.00.000.counter.y", site="f:1", actual=1).to_json()
    )
    legacy.pop("duration", None)
    assert "duration" not in legacy
    restored = Signal(name=legacy["name"], site=legacy["site"], actual=legacy["actual"])
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
    sink.emit("probe.99.030.postcondition.owns_it", actual=1, duration=owner_duration)
    sink.emit("probe.99.031.postcondition.sibling", actual=1)

    owner, sibling = sink.records()[-2:]
    assert owner.duration == owner_duration
    assert (
        sibling.duration is None
    ), "a sibling in the same operation must not repeat the owner's duration"


# ── end to end through the first real emitter ─────────────────────────


def test_ta_07_003_carries_a_duration_that_tracks_the_real_compute():
    """The first of the six wired: `ta.07.003.postcondition.computed`.

    Drives the real `VotingEngine.compute_all` with stub indicators that burn
    two DIFFERENT known intervals, and reads the duration off the real record.
    A source scan proving the argument is passed would not catch a sink that
    swallowed it, or a timer bracketing the emit instead of the work.
    """
    from src.core import signal_contract as sc
    from src.trading.ta_engine import Signal as TASignal, SignalDirection, VotingEngine

    class _Burn:
        """An indicator whose only job is to take a known amount of time."""

        weight = 1.0

        def __init__(self, secs: float) -> None:
            self.secs = secs

        def compute(self, _candles, timeframe="1h"):
            _busy_wait(self.secs)
            return TASignal(
                indicator="stub",
                timeframe=timeframe,
                direction=SignalDirection.NEUTRAL,
                confidence=0.5,
            )

    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        engine = VotingEngine()
        for secs in (SHORT_S, LONG_S):
            engine._indicators = [_Burn(secs)]
            for _ in range(SAMPLES):
                engine.compute_all([], "1h")
    finally:
        # RESTORE THE PREVIOUS SINK, never None. `set_sink` is process-global
        # and ta_engine gates its whole instrumentation block on the sink
        # being installed, so leaking one silently changes the code path for
        # every test module collected afterwards.
        sc.set_sink(previous)

    computed = [
        r for r in sink.records() if r.name == "ta.07.003.postcondition.computed"
    ]
    assert len(computed) == 2 * SAMPLES, computed

    # The MINIMUM of each workload's samples, for the reason recorded
    # at `SAMPLES`: a pause can only ADD to an elapsed-time reading, so
    # the smallest sample is the closest estimate of the real compute.
    short = min(r.duration for r in computed[:SAMPLES])
    long_ = min(r.duration for r in computed[SAMPLES:])
    assert _tracks_the_operation(
        short, long_
    ), f"did not track the real compute: {short} vs {long_}"
    assert short == pytest.approx(SHORT_S, abs=0.005), short
    assert long_ == pytest.approx(LONG_S, abs=0.015), long_

    # Finding 1, held in the live path: no other emitter in that function
    # repeats the owner's interval.
    assert not [
        r
        for r in sink.records()
        if r.name != "ta.07.003.postcondition.computed" and r.duration is not None
    ]


# ── Defect A: the READER, not the dataclass default ───────────────────
#
# `test_a_record_written_before_this_field_existed_reads_back_as_none`
# above builds a `Signal(...)` by hand, so it asserts the DATACLASS
# DEFAULT and never reaches `read_records` -- which is the only code a
# record on the operator's disk actually comes back through. Measured
# 2026-08-20 on this branch: with the reader's `duration=` restore
# DELETED, and again with an absent duration restored as 0.0, every
# test in this file still passed. The writer half was pinned -- drop
# the key from `to_json` and a test fails -- and the reader half was
# not. These three hold the reader itself.


def _payload(with_key: bool, duration: Optional[float] = None) -> dict:
    """One record exactly as the writer emits it, with the key set."""
    d = json.loads(
        Signal(
            name="x.00.000.postcondition.op",
            site="f:1",
            actual=1,
            seq=7,
            ts="2026-08-20T00:00:00Z",
            duration=duration,
        ).to_json()
    )
    if not with_key:
        d.pop("duration")
    return d


def _read_back(tmp_path, payload: dict):
    """Put that record on disk and bring it back through the real reader."""
    path = tmp_path / "legacy.jsonl"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return read_records(path)


def test_the_reader_restores_a_measured_duration_off_disk(tmp_path):
    """DELETING the reader's restore must fail here.

    Without it the field falls back to the dataclass default, so every
    duration ever written reads back as None. The writer keeps its own
    pin and passes, the round trip is broken, and nothing says so.
    """
    payload = _payload(True, 0.25)
    assert payload["duration"] == 0.25, "the fixture never carried one"
    back = _read_back(tmp_path, payload)
    assert len(back) == 1
    assert back[0].duration == 0.25, "the reader dropped the field"


def test_the_reader_restores_an_absent_duration_as_none_not_zero(tmp_path):
    """ABSENT IS NOT ZERO, held at the READER this time.

    0.0 would claim every operation written before this key existed was
    instantaneous, and item 17 reads that as perfect latency.
    """
    payload = _payload(False)
    assert "duration" not in payload, "the fixture still carries the key"
    back = _read_back(tmp_path, payload)
    assert len(back) == 1
    assert back[0].duration is None
    assert back[0].duration != 0.0


def test_the_two_reader_fixtures_differ_only_in_that_one_key(tmp_path):
    """The control on the pair above.

    If both fixtures were the same record, one of those tests would be
    asserting the other's case and neither would reach the branch it
    names.
    """
    present, absent = _payload(True, 0.25), _payload(False)
    assert set(present) - set(absent) == {"duration"}
    assert set(absent) - set(present) == set()
    with_it = _read_back(tmp_path, present)[0]
    without = _read_back(tmp_path, absent)[0]
    assert (with_it.duration, without.duration) == (0.25, None)
    assert with_it.name == without.name and with_it.seq == without.seq


# ── Defect B: a duration nobody measured must not be invented ─────────


def test_a_bool_duration_does_not_become_a_one_second_latency():
    """`float(True)` is 1.0.

    A call site that passes a FLAG by mistake -- `duration=is_slow` --
    wrote a one-second latency indistinguishable on disk from a real
    measurement. `_as_float` already refuses this coercion on the way
    IN from disk; the way in from a call site had no such refusal.
    """
    sink = SignalSink()
    sink.emit("probe.99.040.postcondition.flag", actual=1, duration=True)
    rec = sink.records()[-1]
    assert rec.duration is None
    assert rec.duration != 1.0
    assert sink.health()["duration_rejected"] == 1


def test_a_negative_duration_is_refused_because_time_runs_forwards():
    """`time.monotonic()` cannot produce one.

    So it is a reversed subtraction, or a wall-clock difference taken
    across an NTP step -- a hazard this module already names for `ts`.
    Either way it is not a latency, and it was stored verbatim.
    """
    sink = SignalSink()
    sink.emit("probe.99.041.postcondition.backwards", actual=1, duration=-0.5)
    rec = sink.records()[-1]
    assert rec.duration is None
    assert sink.health()["duration_rejected"] == 1


def test_a_nan_or_infinite_duration_is_refused():
    """Both survive `float()` and neither is a measurement.

    Every comparison against NaN is False, so a health threshold reads
    it as satisfied. `json.dumps` writes the two as bare `NaN` and
    `Infinity` tokens, which Python's own decoder accepts but RFC 8259
    does not, so the operator's file stops being portable JSON.
    """
    sink = SignalSink()
    sink.emit("probe.99.042.postcondition.inf", actual=1, duration=float("inf"))
    sink.emit("probe.99.043.postcondition.nan", actual=1, duration=float("nan"))
    assert [r.duration for r in sink.records()[-2:]] == [None, None]
    assert sink.health()["duration_rejected"] == 2


def test_a_duration_that_is_not_a_number_no_longer_destroys_the_record():
    """THE WORST OF THEM, and the least visible.

    `float(object())` raises TypeError inside `emit`, where the blanket
    handler that exists so instrumentation never breaks the app
    swallowed it and returned None. The bad argument did not merely
    lose its duration -- it lost THE WHOLE OBSERVATION, and nothing
    counted it, because the record never reached the buffer.
    """
    sink = SignalSink()
    rec = sink.emit("probe.99.044.postcondition.object", actual=1, duration=object())
    assert rec is not None, "a bad duration destroyed the whole record"
    assert rec.actual == 1
    assert rec.duration is None
    assert len(sink.records()) == 1
    assert sink.health()["duration_rejected"] == 1


def test_emit_never_raises_for_any_refused_shape():
    """THE HARD CONSTRAINT, driven across every shape at once.

    `emit` runs on the live trading and GUI paths. The module docstring
    already forbids an exception thrown to report a schema nit, and a
    rejected argument is a schema nit. Every refusal degrades to "not
    measured"; none escapes, and none costs the record.
    """
    sink = SignalSink()
    refused = (
        True,
        False,
        -1.0,
        -1,
        float("nan"),
        float("inf"),
        "0.25",
        object(),
        [],
        {},
    )
    for bad in refused:
        rec = sink.emit("probe.99.045.postcondition.shapes", actual=1, duration=bad)
        assert rec is not None, bad
        assert rec.duration is None, bad
    assert sink.health()["duration_rejected"] == len(refused)


def test_the_guard_refuses_only_what_is_not_a_measurement():
    """THE OTHER HALF. A guard that refused everything would pass every
    test above while recording no latency at all -- the same blindness
    reached by the opposite route.
    """
    sink = SignalSink()
    sink.emit("probe.99.050.postcondition.quarter", actual=1, duration=0.25)
    sink.emit("probe.99.051.postcondition.whole", actual=1, duration=2)
    sink.emit("probe.99.052.postcondition.instant", actual=1, duration=0.0)
    quarter, whole, instant = sink.records()[-3:]
    assert quarter.duration == 0.25
    assert whole.duration == 2.0, "an integer count of seconds is a measurement"
    assert instant.duration == 0.0, (
        "an operation faster than the clock resolves rounds to 0.0, and "
        "that is a measurement -- None is reserved for never measured"
    )
    assert instant.duration is not None
    assert sink.health()["duration_rejected"] == 0


def test_both_emit_signatures_are_behind_the_same_gate():
    """THERE ARE TWO `emit`s IN THIS MODULE.

    `SignalSink.emit` and the module-level function. The second
    forwards to the first on BOTH its paths -- direct, and rate-limited
    through `_throttle_admit` -- so one guard at the sink covers both.
    This holds that: a second guard is not needed, and a duration that
    reaches the forwarding function cannot get to disk unjudged.
    """
    from src.core import signal_contract as sc

    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        sc.emit("probe.99.060.postcondition.direct", actual=1, duration=True)
        sc.emit(
            "probe.99.061.postcondition.throttled", actual=1, duration=-1.0, every=60.0
        )
        sc.emit("probe.99.062.postcondition.good", actual=1, duration=0.5)
    finally:
        # RESTORE THE PREVIOUS SINK, never None -- `set_sink` is
        # process-global; see the note in the end-to-end test above.
        sc.set_sink(previous)

    assert [r.duration for r in sink.records()] == [None, None, 0.5]
    assert sink.health()["duration_rejected"] == 2


# ── Defect C: the rounding `dt` gets, off the same clock ──────────────


def test_a_duration_is_rounded_like_dt_and_keeps_what_the_clock_measured():
    """BOTH DIRECTIONS, because rounding has two ways to be wrong.

    `emit` rounds `dt` to 1e-07 and did not round `duration`, though
    both come off the same `time.monotonic()`, whose resolution on the
    operator's machine is 1e-07. The eighth decimal onward is float
    representation noise, written to disk on every record that carries
    a duration. That is the first direction.

    The second is that this must be a NOISE FLOOR and never a
    tolerance: nothing the clock can actually resolve may be lost. One
    tick, 1e-07, has to survive it exactly. `dt` states the same rule.
    """
    sink = SignalSink()
    sink.emit("probe.99.070.postcondition.noisy", actual=1, duration=1 / 3)
    for value in (0.0000001, 0.1234567, 123.456789):
        sink.emit("probe.99.071.postcondition.exact", actual=1, duration=value)

    noisy, tick, seven, big = (r.duration for r in sink.records()[-4:])
    assert noisy == 0.3333333, "noise below the clock floor was written"
    assert tick == 0.0000001, "one clock tick did not survive the rounding"
    assert seven == 0.1234567
    assert big == 123.456789

    # WHAT THE ROUNDING IS FOR, in the terms `dt` argues it: the record
    # is measurably shorter on the operator's 300 MB ladder.
    written = json.dumps({"duration": noisy}, separators=(",", ":"))
    unrounded = json.dumps({"duration": 1 / 3}, separators=(",", ":"))
    assert len(written) < len(unrounded), (written, unrounded)
    assert json.loads(sink.records()[-4].to_json())["duration"] == 0.3333333


# ── Defect D: the refusal that was itself a way to raise ──────────────


def test_a_huge_int_duration_no_longer_destroys_the_record():
    """THE FOURTH ROUTE TO THE THIRD DEFECT, and it survived the fix
    for it.

    The guard judged the TYPE and then converted: `type(value) is int`
    passed, and `float(value)` was taken on trust. `float(10**400)`
    raises OverflowError -- not the TypeError `float(object())` raises,
    so no type check anywhere could have caught it. The exception left
    the guard, reached `emit`, and was swallowed by the blanket handler
    that exists so instrumentation never breaks the app. The record
    never reached the buffer, and `duration_rejected` never saw it: the
    counter that exists to make a silent degrade visible was itself
    bypassed, because the degrade killed the record on its way past.

    So this asserts the RECORD, not the duration. A `duration is None`
    check alone passes on a destroyed record, since there is no record
    to read the field from.
    """
    sink = SignalSink()
    rec = sink.emit("probe.99.046.postcondition.hugeint", actual=1, duration=10**400)
    assert rec is not None, "a huge int duration destroyed the whole record"
    assert rec.actual == 1, "the record survived but lost its observation"
    assert rec.duration is None
    assert len(sink.records()) == 1, "the record never reached the buffer"

    neg = sink.emit(
        "probe.99.047.postcondition.hugenegint", actual=2, duration=-(10**400)
    )
    assert neg is not None, "a huge negative int destroyed the whole record"
    assert neg.actual == 2
    assert neg.duration is None
    assert len(sink.records()) == 2

    # THE COUNTER IS THE OTHER HALF. A refusal nobody counted is the
    # silent degrade this counter exists to prevent, and neither of
    # these two reached it before -- the record died first.
    assert sink.health()["duration_rejected"] == 2


def test_an_int_a_float_can_hold_is_still_a_measurement():
    """THE BOUND IS A BOUND, NOT A BLANKET REFUSAL OF LARGE INTS.

    A guard that answered the test above by refusing every `int` would
    pass it and quietly destroy `duration=2`. The bound refuses exactly
    what a float cannot represent and nothing else, so an int at the
    top of the float range is still carried.
    """
    import sys as _sys

    sink = SignalSink()
    sink.emit("probe.99.048.postcondition.inbound", actual=1, duration=10**308)
    sink.emit(
        "probe.99.049.postcondition.atbound",
        actual=1,
        duration=int(_sys.float_info.max),
    )
    big, edge = sink.records()[-2:]
    assert big.duration == 1e308
    assert (
        edge.duration is not None
    ), "an int a float can hold exactly was refused as if it overflowed"
    assert sink.health()["duration_rejected"] == 0


def test_the_guard_is_total_and_no_hostile_input_costs_a_record():
    """TOTALITY, driven as one list: NO INPUT MAY MAKE `emit` RAISE.

    The previous statement of this rule -- see
    `test_emit_never_raises_for_any_refused_shape` -- enumerated the
    shapes that were known to be refused, and a value outside that
    enumeration still raised. This one is written as the property
    itself: every call returns a record, and no call raises, whatever
    was passed. Each new hostile shape belongs in this list.
    """
    hostile = (
        10**400,
        -(10**400),
        "0.25",
        object(),
        [0.25],
        True,
        -0.5,
        float("nan"),
        float("inf"),
        float("-inf"),
    )
    sink = SignalSink()
    for bad in hostile:
        try:
            rec = sink.emit("probe.99.055.postcondition.total", actual=1, duration=bad)
        except Exception as exc:  # pragma: no cover - the pin
            pytest.fail(f"emit raised {exc!r} for duration={bad!r}")
        assert rec is not None, f"duration={bad!r} destroyed the record"
        assert rec.duration is None, bad

    assert len(sink.records()) == len(
        hostile
    ), "a hostile duration cost a record on its way to the buffer"
    assert sink.health()["duration_rejected"] == len(
        hostile
    ), "a refusal degraded silently instead of being counted"


def test_the_guard_function_itself_raises_for_no_input():
    """THE SAME PROPERTY ONE LAYER DOWN, because `emit`'s blanket
    handler can hide a raise from the test above.

    `emit` catches everything. If the guard raised and `emit` returned
    None, the test above would report "destroyed the record" and not
    "raised" -- true, but it names the symptom rather than the cause.
    This drives the pure function directly, where nothing catches.
    """
    from src.core.signal_contract import _as_measured_duration

    hostile = (
        10**400,
        -(10**400),
        10**4000,
        "0.25",
        object(),
        [],
        {},
        True,
        False,
        -1,
        -0.5,
        float("nan"),
        float("inf"),
        float("-inf"),
        None,
    )
    for bad in hostile:
        assert _as_measured_duration(bad) is None, bad

    # AND THE ACCEPTED CASES ARE UNMOVED by the totality work.
    assert _as_measured_duration(0.25) == 0.25
    assert _as_measured_duration(0.0) == 0.0
    assert _as_measured_duration(3) == 3.0
    assert _as_measured_duration(1 / 3) == 0.3333333


# ── Defect E: the DISK guard was the same hole, at a worse price ──────
#
# `_as_float` is the reader's counterpart to `_as_measured_duration`,
# and it carried the identical unguarded `float(value)` on its int
# branch. The price is not the same. On the write path a refused value
# cost ONE record, because `emit`'s blanket handler caught the raise.
# `read_records` has two handlers and neither is blanket: an inner
# `except json.JSONDecodeError` around `json.loads` ONLY, and an outer
# `except OSError`. `_as_float` runs after the decode, inside the
# `Signal(...)` construction, so OverflowError is caught by neither. It
# leaves `read_records` entirely. ONE bad line therefore did not cost
# one line -- it cost the whole file, and the caller with it.
#
# Measured on this branch before the fix, over a three-line file:
#   read_records RAISED OverflowError: int too large to convert to float
# and zero of the three records came back.


def _huge(sign: str = "") -> str:
    """A JSON integer literal wider than any float, as written text.

    Built as digits rather than through `json.dumps`, so the fixture is
    an INT LITERAL in the file exactly as a corrupted writer or a
    foreign producer would leave it. `json.loads` restores it as a
    Python int of full width, which is the input under test.
    """
    return sign + "1" + "0" * 400


def _sandwich(tmp_path, key: str, bad_literal: str):
    """Write good / BAD / good, and read it back through the real reader.

    THE BAD LINE IS IN THE MIDDLE ON PURPOSE. With it first, a reader
    that aborts on the first bad line and one that recovers are
    indistinguishable by the record count alone. With a good record on
    each side, an early abort returns nothing, a late abort returns
    one, and only a reader that survives the line returns all three.
    """
    lines = [
        '{"name":"probe.before","site":"s","ok":true,"seq":1,"ts":"t",'
        '"' + key + '":0.5}',
        '{"name":"probe.bad","site":"s","ok":true,"seq":2,"ts":"t",'
        '"' + key + '":' + bad_literal + "}",
        '{"name":"probe.after","site":"s","ok":true,"seq":3,"ts":"t",'
        '"' + key + '":0.75}',
    ]
    path = tmp_path / ("sandwich_" + key + ".jsonl")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # THE FIXTURE IS ONLY A FIXTURE IF THE MIDDLE LINE REALLY CARRIES A
    # NUMBER NO FLOAT CAN HOLD. A typo that made it a string would
    # exercise the string branch and pass for the wrong reason.
    middle = json.loads(path.read_text(encoding="utf-8").splitlines()[1])
    assert type(middle[key]) is int, "the fixture is not an int literal"
    with pytest.raises(OverflowError):
        float(middle[key])
    return read_records(path)


def test_a_huge_dt_on_one_line_no_longer_costs_the_whole_file(tmp_path):
    """THE READER SURVIVES, and so do the records around the bad one.

    `read_records` returning `()` would ALSO satisfy a caller that only
    checks for an exception, and it is the wrong answer: an empty read
    is indistinguishable from an empty file, which is the exact silent
    absence a monitor exists to notice. So this asserts the neighbours
    came back, in order, carrying their own values.
    """
    back = _sandwich(tmp_path, "dt", _huge())
    assert len(back) == 3, "a single bad field cost more than its own field"
    assert [r.name for r in back] == ["probe.before", "probe.bad", "probe.after"]
    assert (back[0].dt, back[2].dt) == (
        0.5,
        0.75,
    ), "a neighbour of the bad line lost its own good value"

    # THE FIELD, AND ONLY THE FIELD. None is this module's existing
    # spelling for "not a usable number" -- what `_as_float` already
    # returns for a string, a list or a bool. An int too wide for a
    # float joins that class rather than being promoted into a
    # record-level or a file-level failure.
    assert back[1].dt is None
    assert back[1].dt != 0.0, "an unusable interval was invented as zero"
    assert (
        back[1].name == "probe.bad" and back[1].seq == 2
    ), "the record survived but lost the fields that were readable"


def test_a_huge_negative_duration_costs_only_its_own_field(tmp_path):
    """THE OTHER SIGN AND THE OTHER FIELD, driven on its own.

    `float(-(10 ** 400))` raises the same OverflowError as the positive
    case, and a bound written with only its upper half -- `value <=
    sys.float_info.max` -- passes the test above and still raises here.
    That one-sided bound is planted as a mutation for this branch.
    """
    back = _sandwich(tmp_path, "duration", _huge("-"))
    assert len(back) == 3, "a single bad field cost more than its own field"
    assert [r.name for r in back] == ["probe.before", "probe.bad", "probe.after"]
    assert (back[0].duration, back[2].duration) == (0.5, 0.75)
    assert back[1].duration is None
    assert back[1].duration != 0.0, "an unusable latency was invented as zero"


def test_the_reader_survives_both_signs_inside_one_file(tmp_path):
    """Two bad lines, both signs, still inside one read.

    A guard that closed one sign only could pass each single-sign test
    above and still abort a file that carries both.
    """
    lines = [
        '{"name":"probe.g1","site":"s","ok":true,"seq":1,"ts":"t","dt":0.5}',
        '{"name":"probe.pos","site":"s","ok":true,"seq":2,"ts":"t","dt":'
        + _huge()
        + "}",
        '{"name":"probe.g2","site":"s","ok":true,"seq":3,"ts":"t",' '"duration":0.25}',
        '{"name":"probe.neg","site":"s","ok":true,"seq":4,"ts":"t",'
        '"duration":' + _huge("-") + "}",
        '{"name":"probe.g3","site":"s","ok":true,"seq":5,"ts":"t","dt":0.75}',
    ]
    path = tmp_path / "bothsigns.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    back = read_records(path)
    assert len(back) == 5, "a bad line cost a record it did not own"
    assert [r.seq for r in back] == [1, 2, 3, 4, 5]
    assert back[1].dt is None and back[3].duration is None
    assert (back[0].dt, back[4].dt) == (0.5, 0.75)
    assert back[2].duration == 0.25


def test_an_undecodable_line_is_still_the_only_thing_skipped(tmp_path):
    """THE CONTROL ON THE DECISION, so "keep the record" is a choice.

    `read_records` already drops a line it cannot decode -- that line
    is not a record at all. A line that decodes cleanly and carries one
    unusable number IS a record: it has a name, a site, a verdict and a
    sequence, every one of them readable. Dropping it would delete a
    real emission from the census to punish a field nobody has to read.
    This holds the two behaviours apart, so a later reader cannot
    quietly fold the second into the first.
    """
    lines = [
        '{"name":"probe.ok","site":"s","ok":true,"seq":1,"ts":"t"}',
        "{ this is not json at all",
        '{"name":"probe.wide","site":"s","ok":false,"seq":2,"ts":"t","dt":'
        + _huge()
        + "}",
    ]
    path = tmp_path / "mixed.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    back = read_records(path)
    assert [r.name for r in back] == [
        "probe.ok",
        "probe.wide",
    ], "undecodable and unusable were treated as the same class"
    assert back[1].ok is False, "the verdict was lost with the number"
    assert back[1].dt is None


def test_the_disk_guard_is_total_and_no_input_makes_it_raise():
    """THE SAME PROPERTY ONE LAYER DOWN, driven where nothing catches.

    `read_records` has no blanket handler, so a raise inside the guard
    is visible in the tests above -- but they name it as a lost file
    rather than as the guard. This drives the pure function directly.

    ITS CONTRACT IS NOT THE INGRESS GUARD'S. `_as_float` reads a number
    back off DISK; `_as_measured_duration` judges a number arriving
    from a CALL SITE. The disk reader must not acquire the ingress
    rules: a negative `dt` or a NaN that a previous generation really
    did write has to read back as the value that is on the disk, or the
    reader is editing history. Only the TOTALITY is shared.
    """
    from src.core.signal_contract import _as_float

    hostile = (
        10**400,
        -(10**400),
        10**4000,
        -(10**4000),
        "0.25",
        object(),
        [],
        {},
        True,
        False,
        None,
    )
    for bad in hostile:
        assert _as_float(bad) is None, bad

    # AND EVERY VALUE IT ALREADY HANDLED IS UNMOVED. The bound refuses
    # exactly what a float cannot hold, and nothing else.
    import sys as _sys

    assert _as_float(0.25) == 0.25
    assert _as_float(0.0) == 0.0
    assert _as_float(-0.5) == -0.5, "the disk reader acquired an ingress rule"
    assert _as_float(3) == 3.0
    assert _as_float(-3) == -3.0
    assert _as_float(1 / 3) == 1 / 3, "the disk reader started rounding"
    assert _as_float(10**308) == 1e308
    assert (
        _as_float(int(_sys.float_info.max)) is not None
    ), "an int a float can hold exactly was refused as if it overflowed"
    assert _as_float(-int(_sys.float_info.max)) is not None
    assert _as_float(float("nan")) != _as_float(
        float("nan")
    ), "a NaN already on disk stopped reading back as the NaN it is"
    assert _as_float(float("inf")) == float("inf")
