"""Pins the duration on `topology.09.002.postcondition.wires_received`.

Last of the six clean owners
(docs/audits/2026-08-19_emitter_duration_classification.md). Sole emitter in
`import_wires`; `topology.09.001` lives in `attach_bot`, is a dict insert, and
is classified instantaneous -- it carries nothing.

THIS ONE TIMES REAL WORK. The other five drive their interval with an injected
delay because the operation is I/O. Here the import loop's cost scales with the
number of rows offered, so the control feeds two genuinely different workloads
and reads the duration off the real emitter. Nothing is stubbed.

WARM UP BEFORE MEASURING, AND THIS IS NOT A COURTESY. Measured 2026-08-19: the
FIRST `import_wires` call in a process cost 11.975 ms for 50 rows, while later
calls cost 0.257 ms for 500 and 5.291 ms for 8000. That first figure is import
and interpreter warmup, not work. A test that measured the small case first
would record it as SLOWER than the large one and fail for a reason unrelated to
the timer -- or, if the order were reversed, pass for the wrong reason.

THE CLOCK STOPS BEFORE THE REPORT. `n` and `offered` are final once the loop
ends; the accepted-count line, the lost-row tally and the operator warning that
follow are REPORTING. Timing those would bill the report to the import, and
making the log cheaper would read as a faster import.

2026-08-22 -- THE ACCEPTED-COUNT LINE USED TO BE INSIDE THE CLOCK, and that is
what made this control fail inside the release gate while it passed alone. See
`LARGE_ROWS` for the measurement and `src/trading/smart_wire.py` for the repair.
"""

from __future__ import annotations

from typing import Optional

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink
from src.trading.smart_wire import SmartWireManager

EMITTER = "topology.09.002.postcondition.wires_received"

SMALL_ROWS = 1_000

# THE LARGE WORKLOAD, and the measured failure that sets its size.
#
# WHAT WENT WRONG, 2026-08-22. This file passed alone and failed inside
# the release gate. The cause was not a scheduling pause. `import_wires`
# used to dispatch its "imported N wire(s)" log line INSIDE the timed
# bracket. A log dispatch is a CONSTANT: it fires once whatever the row
# count, and its price is set by how many handlers the root logger
# carries. Alone, the root logger carries none and the line is free.
# Inside the suite the GUI tests leave console handlers attached and the
# root logger sits at DEBUG; measured 2026-08-22 with 16 attached, ONE
# dispatch cost 0.001585 s, the minimum of twenty.
#
# A CONSTANT DESTROYS A RATIO. It lands on both readings, so it does not
# move their difference at all -- it moves their QUOTIENT. Measured in
# one process, same code, same machine:
#
#     handlers   small        large        ratio
#     none       0.000290 s   0.003031 s   10.4
#     16         0.001965 s   0.004853 s    2.4
#
# and 1 of 15 in-suite trials then recorded 1.898, below the 2.0 the
# predicate asks for. THE MINIMUM DEFENDS NOTHING HERE. It discards a
# pause that lands on one sample; this cost lands on every sample, so it
# moves the FLOOR. The failing trial's five small readings were
# 0.002281, 0.002426, 0.002252, 0.002292 and 0.002290 -- no outlier to
# discard, the whole distribution had shifted.
#
# THE REPAIR IS IN THE SITE, not here: the log line now sits below the
# stop clock, where the site's own comment always said the report
# belongs. Re-measured in the same 16-handler process afterwards, small
# returned to 0.000302 s and the ratio to 10.1.
#
# WHY THIS NUMBER ALSO CHANGED, and the arithmetic that sizes it. Write
# S for the small reading and L for the large one. There are two ways to
# invert the pair, and they take different amounts:
#
#   a constant C on BOTH readings breaks it at   C >= L - 2S
#   a gain on the SMALL reading alone breaks it  at  L/2 - S
#
# and the second must land on all five samples, while the first lands on
# every sample by definition.
#
# AT 10_000 ROWS THOSE NUMBERS WERE 2.45 ms AND 1.23 ms, with L =
# 0.003031 s and S = 0.000290 s. The log dispatch measured 1.585 ms
# idle. Under 48 busy processes the SAME dispatch measured 2.982 ms,
# which is above 2.45 ms -- so the pair inverts, and the observed ratio
# was 1.898. The failure was not bad luck. It was arithmetic, and the
# margin was thin enough to make it certain under load.
#
# AT 200_000 ROWS THEY ARE 87.6 ms AND 43.8 ms, with L = 0.088229 s and
# S = 0.000305 s. That is 29x the largest constant measured. The cost is
# 0.80 s of suite time and about 100 MB of transient heap, and the large
# workload is built AFTER the small readings are taken, so its
# allocation cannot reach back and inflate them.
#
# WHAT THIS DOES NOT DO. It does not make the control immune to a
# constant, and it does not make it immune to load. It moves the
# breaking constant from 2.45 ms to 87.6 ms. A stall still breaks it if
# it lands on all five small samples and is worth 43.8 ms each; the
# largest single small sample seen in a full suite run was 0.000905 s,
# and under 48 busy processes 0.118890 s -- one sample, not five. The
# real immunity came from moving the report out of the bracket in
# `src/trading/smart_wire.py`; this number is the guard band around that
# repair, so that the next constant to appear inside the bracket is
# caught by a red test rather than by a red gate.
LARGE_ROWS = 200_000

# HOW MANY TIMES EACH WORKLOAD IS MEASURED, and why the figure compared
# is the MINIMUM of the samples rather than a single reading.
#
# A scheduling pause can only ADD to an elapsed-time reading. The
# operating system can take the thread away part way through the import
# loop and hand it back later; it cannot hand back time the loop never
# spent. Every sample is therefore the true cost plus non-negative
# noise, and the smallest of several samples is the closest estimate of
# the true cost this machine can give.
#
# WHY THIS SITE NEEDS IT, MEASURED 2026-08-20 on the target machine.
# Thirty pairs off the real emitter: 1_000 rows recorded 0.000307 s to
# 0.000456 s, 10_000 rows recorded 0.003174 s to 0.005176 s, a median
# ratio of 10.4 against a predicate asking only for 2. That margin
# reads as enormous and it is 1.3 ms wide: the SMALL reading has to
# gain 1.3 ms, once, for `_tracks` to refuse the pair. Inside a
# 7000-test run on Windows with the live application trading, a pause
# that size is ordinary, and on 2026-08-19 the release gate went red
# here on exactly that -- while the same file passed 45 times in
# isolation. Reproduced 2026-08-20 by burning 1.5 ms between two rows
# of the import loop, which is where a real pause would land: small
# 0.0018421, large 0.0035651, FAILED. One pause across five samples is
# noise on one of them, and the minimum discards it.
#
# WHAT THE MINIMUM DOES NOT COVER, and this is the correction the
# 2026-08-22 red gate forced. The paragraph above is about a PAUSE --
# something that lands on one sample. A cost that lands on EVERY sample
# moves the floor, and the minimum of a shifted distribution is shifted
# too. That is the failure this file actually suffered; `LARGE_ROWS`
# carries the measurement and the repair. Keep both defences: they
# answer different attacks and neither replaces the other.
SAMPLES = 5

# THE FLOOR, and the measurement that says it is not optional.
#
# Move the stop clock above the work and the bracket spans nothing:
# every reading collapses to the cost of two `time.monotonic()` calls,
# and a ratio between two numbers that small is a coin flip rather than
# a measurement. Measured 2026-08-20 with the stop clock planted above
# the loop, 60 pairs off this emitter: every reading fell between 0.0 s
# and 3.0e-07 s, the bare ratio ACCEPTED 16 of the 60, and the minimum
# of five samples accepted 24 of the 60. The minimum is the right
# estimator against a stall and it makes the dead clock WORSE, because
# it drives the small reading to a hard zero and any positive large
# reading then beats twice zero. So the floor is a SECOND rule, never
# an alternative to the first.
#
# 0.0005 s sits 1667x above the largest dead-clock reading and 6.3x
# below the smallest honest 10_000-row reading, so it separates the two
# populations without standing near either.
LARGE_FLOOR_S = 0.0005


def _rows(k: int) -> list[dict]:
    return [{"source_id": f"s{i}", "target_id": f"t{i}", "pct": 5.0} for i in range(k)]


def _tracks(small: Optional[float], large: Optional[float]) -> bool:
    if small is None or large is None:
        return False
    return large > small * 2.0


def _tracks_the_import(small: Optional[float], large: Optional[float]) -> bool:
    """Ask `_tracks`, then put a floor under the large reading.

    This ADDS a condition and relaxes none: everything `_tracks`
    refuses is still refused here. The floor is the thing a ratio
    cannot do -- tell a real import from a bracket that measured two
    clock reads. See `LARGE_FLOOR_S` for the 60 harvested dead-clock
    pairs that set it, and
    `test_the_site_predicate_rejects_a_bracket_that_spans_nothing` for
    this predicate driven in the failing direction.
    """
    if small is None or large is None:
        return False
    if large < LARGE_FLOOR_S:
        return False
    return _tracks(small, large)


def _drive(sink: SignalSink, wires) -> int:
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        return SmartWireManager().import_wires(wires)
    finally:
        # Restore the PREVIOUS sink, never None — `set_sink` is process-global.
        sc.set_sink(previous)


def _warm_up() -> None:
    """Pay the one-off import/interpreter cost outside any measurement."""
    SmartWireManager().import_wires(_rows(50))


def _durations(sink: SignalSink) -> list:
    return [r.duration for r in sink.records() if r.name == EMITTER]


def _fastest_import(k: int) -> Optional[float]:
    """The lowest duration `SAMPLES` real imports of `k` rows record.

    Each sample is a whole real `import_wires` call, read back off the
    real emitter. Nothing is stubbed, the clock is never touched and no
    recorded value is adjusted; the only thing added here is
    repetition. A `None` is returned as `None` rather than skipped,
    because a missing duration is a defect and must not be hidden by
    four healthy neighbours.
    """
    best: Optional[float] = None
    for _ in range(SAMPLES):
        sink = SignalSink()
        _drive(sink, _rows(k))
        got = _durations(sink)
        assert len(got) == 1, got
        if got[0] is None:
            return None
        best = got[0] if best is None else min(best, got[0])
    return best


def test_the_import_emitter_carries_a_duration():
    _warm_up()
    sink = SignalSink()
    _drive(sink, _rows(SMALL_ROWS))
    got = _durations(sink)
    assert len(got) == 1, got
    assert got[0] is not None


def test_the_duration_tracks_a_genuinely_larger_import():
    """THE control, on real work rather than an injected delay.

    Each workload is measured `SAMPLES` times and the MINIMUM of the
    samples is compared. A stall inside one bracketed region inflates
    that one sample and the minimum discards it. Nothing about what is
    compared is relaxed: both sides are still real durations read off
    the real emitter, and both must still clear the floor and the
    ratio.
    """
    _warm_up()
    small = _fastest_import(SMALL_ROWS)
    large = _fastest_import(LARGE_ROWS)

    assert _tracks_the_import(small, large), (
        f"{LARGE_ROWS} rows did not record longer than {SMALL_ROWS}: "
        f"{small} vs {large}"
    )


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
    assert not _tracks_the_import(
        0.01, 0.01
    ), "a constant duration must not read as tracking"
    assert not _tracks_the_import(
        None, 0.0032
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_import(
        0.0003, None
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_import(
        0.0032, 0.0003
    ), "going backwards must not read as tracking"

    # THE DEAD CLOCK, and the measured reason this site carries a floor
    # the shared predicate does not. This pair is a real one: it came
    # off the 2026-08-20 run with the stop clock planted above the
    # import loop. `_tracks` accepts it. The floor rejects it. That is
    # an addition to `_tracks`, never a relaxation of it.
    assert _tracks(
        0.0, 3.0e-07
    ), "the shared predicate is expected to accept a dead clock here"
    assert not _tracks_the_import(
        0.0, 3.0e-07
    ), "a bracket that spans no work must not read as tracking"

    # The honest pair measured off the real site, 2026-08-20, must
    # still read as tracking.
    assert _tracks_the_import(
        0.000307, 0.003174
    ), "the real measured pair must read as tracking"


def test_a_refused_import_emits_nothing():
    """The type guard returns early. No record, so no duration.

    Asserts the ABSENCE of a record: "refused" and "measured nothing" are
    different states and collapsing them would hide a refusal.
    """
    sink = SignalSink()
    assert _drive(sink, "not-a-list") == 0
    assert _durations(sink) == []


def test_the_sibling_emitter_never_carries_a_duration():
    """`topology.09.001` is a dict insert in `attach_bot`, classified instantaneous."""
    _warm_up()
    sink = SignalSink()
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        mgr = SmartWireManager()
        mgr.attach_bot("bot-1", object())
        mgr.import_wires(_rows(SMALL_ROWS))
    finally:
        sc.set_sink(previous)

    sibling = [
        r.duration
        for r in sink.records()
        if r.name == "topology.09.001.state_transition.bot_attached"
    ]
    assert sibling, "the sibling did not fire; the control proves nothing"
    assert all(d is None for d in sibling), sibling
