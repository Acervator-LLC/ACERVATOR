"""Pins the duration on `fleet.03.001.postcondition.bots_loaded`.

Third of the six clean owners
(docs/audits/2026-08-19_emitter_duration_classification.md).

THIS FUNCTION HOLDS THREE EMITTERS, AND ONLY ONE MAY CLAIM THE INTERVAL.
`fleet.03.001` owns the load; `fleet.03.002` and `fleet.03.003` fire afterwards
against the same call and carry NOTHING. That is Finding 1 of the
classification: 32 of the 40 emitters share an enclosing function, and if each
claimed that function's elapsed time they would all report the SAME number — a
fabricated distinction item 17 would read as health.

WHERE THE CLOCK STOPS, and why it is not the end of the function. `out` is
complete once the build loop finishes. What follows is the emitters' own
bookkeeping — `_eligible` is recomputed purely so each emitter can carry the
expectation it is judged against. Billing that to the load would report a
number nobody could act on: making the emitters cheaper would "speed up the
load".

A LIMIT, STATED RATHER THAN PAPERED OVER. The tests below prove the duration
tracks the READ and that the siblings stay empty. They do not prove the clock
stops before the bookkeeping, because that bookkeeping costs microseconds and
any threshold separating it from jitter would be a threshold tuned to pass.
The boundary is a design decision recorded at the call site; what is asserted
here is what can be asserted honestly.
"""

from __future__ import annotations

import time
from typing import Optional

import pytest

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink
from src.gui.simulator_tab.fleet import bot_state_loader as bsl

OWNER = "fleet.03.001.postcondition.bots_loaded"
SIBLINGS = ("fleet.03.002.invariant.bot_ids_mirror_live",
            "fleet.03.003.invariant.sections_imported")

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
# THIS SITE, MEASURED 2026-08-20, 20 single readings off the real
# emitter: the 0.005 s read recorded 0.005002 s to 0.005018 s and the
# 0.030 s read recorded 0.030002 s to 0.030020 s. The lever is what the bracket is asked to see, so
# a pause of 10 ms inside the SHORT region is all it takes to close
# a gap that reads as comfortable.
SAMPLES = 5

# THE FLOOR, and the measurement that says it is not optional.
#
# Move the stop clock above the work and the bracket spans nothing:
# every reading collapses to the cost of two `time.monotonic()` calls,
# and a ratio between two numbers that small is a coin flip rather than
# a measurement. Measured 2026-08-20 with the stop clock planted above
# the work at this exact site, 120 readings: every reading fell between 0.0 s and 4.0e-07 s. The bare ratio
# ACCEPTED 5 of 30 pairs, and the minimum of five samples accepted 8 of 30.
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
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass


def _tracks(short: Optional[float], long_: Optional[float]) -> bool:
    if short is None or long_ is None:
        return False
    return long_ > short * 2.0


def _tracks_the_load(short: Optional[float],
                       long_: Optional[float]) -> bool:
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


def _state(n_bots: int = 2) -> dict:
    """A minimal bot_state shape the loader accepts."""
    return {"bots": {f"bot{i}": {"config": {"mode": "scrumming",
                                            "symbol": f"X{i}/USD"}}
                     for i in range(n_bots)}}


def _drive(monkeypatch, burn_s: float, sink: SignalSink) -> None:
    """Run the real loader once with a read of known cost."""
    def _slow_read(_path):
        _busy_wait(burn_s)
        return _state()

    monkeypatch.setattr(bsl, "_read_state_file", _slow_read)
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        bsl.load_bot_configs_from_state()
    finally:
        # Restore the PREVIOUS sink, never None — `set_sink` is process-global.
        sc.set_sink(previous)


def _durations(sink: SignalSink, name: str) -> list:
    return [r.duration for r in sink.records() if r.name == name]


def _fastest_load(monkeypatch, burn_s: float) -> Optional[float]:
    """The lowest duration `SAMPLES` real loads of cost `burn_s` record.

    Each sample is a whole real `load_bot_configs_from_state` call read
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
        got = _durations(sink, OWNER)
        assert len(got) == 1, got
        if got[0] is None:
            return None
        best = got[0] if best is None else min(best, got[0])
    return best


def test_the_owner_carries_a_duration(monkeypatch):
    sink = SignalSink()
    _drive(monkeypatch, SHORT_S, sink)
    got = _durations(sink, OWNER)
    assert len(got) == 1, got
    assert got[0] is not None, "the load emitter recorded no duration"


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
    assert _tracks_the_load(short, long_), (
        f"did not track: {short} vs {long_}")


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
    assert not _tracks_the_load(0.01, 0.01), (
        "a constant duration must not read as tracking")
    assert not _tracks_the_load(None, LONG_S), (
        "an absent duration must not read as tracking")
    assert not _tracks_the_load(SHORT_S, None), (
        "an absent duration must not read as tracking")
    assert not _tracks_the_load(LONG_S, SHORT_S), (
        "going backwards must not read as tracking")

    # THE DEAD CLOCK, and the measured reason this site carries a floor
    # the shared predicate does not. This pair is a real one, harvested
    # 2026-08-20 with the stop clock planted above the work. `_tracks`
    # accepts it. The floor rejects it. That is an addition to
    # `_tracks`, never a relaxation of it.
    assert _tracks(0.0, 4.0e-07), (
        "the shared predicate is expected to accept a dead clock here")
    assert not _tracks_the_load(0.0, 4.0e-07), (
        "a bracket that spans no work must not read as tracking")

    # The honest pair measured off the real site, 2026-08-20, must
    # still read as tracking.
    assert _tracks_the_load(0.005002, 0.030002), (
        "the real measured pair must read as tracking")


@pytest.mark.parametrize("sibling", SIBLINGS)
def test_a_sibling_emitter_does_not_repeat_the_owners_duration(
        monkeypatch, sibling):
    """Finding 1, held in the live path.

    Both siblings fire on the same call as the owner. If either carried the
    enclosing function's elapsed time, three emitters would report one number
    and item 17 would read a fabricated distinction as health.
    """
    sink = SignalSink()
    _drive(monkeypatch, SHORT_S, sink)

    owner = _durations(sink, OWNER)
    assert owner and owner[0] is not None, "owner must carry one"

    got = _durations(sink, sibling)
    assert got, f"{sibling} did not fire; the control proves nothing"
    assert all(d is None for d in got), (
        f"{sibling} claimed a duration it does not own: {got}")
