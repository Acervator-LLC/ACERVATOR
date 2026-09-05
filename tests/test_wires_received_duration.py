"""The duration on `topology.09.002.postcondition.wires_received` is real.

`import_wires` is the sole emitter and its cost scales with the rows offered,
so `_fastest_import` reads the duration off the real emitter over two
workloads and `_tracks_the_import` requires the large one to be more than
twice the small one and above `LARGE_FLOOR_S`. `_warm_up` runs first: the
first `import_wires` call in a process bills interpreter warmup to the import.
"""

from __future__ import annotations

from typing import Optional

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink
from src.trading.smart_wire import SmartWireManager

EMITTER = "topology.09.002.postcondition.wires_received"

SMALL_ROWS = 1_000

#: Sized so a constant cost inside the bracket cannot invert the pair: it
#: would have to be worth 87.6 ms, and the largest measured is 3.0 ms.
LARGE_ROWS = 200_000

#: A scheduling pause only adds to an elapsed reading, so `_fastest_import`
#: takes the smallest of this many samples.
SAMPLES = 5

#: A stop clock above the work collapses every reading to under 3.0e-07 s.
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

    # A real pair off a stop clock planted above the import loop. `_tracks`
    # accepts it; `LARGE_FLOOR_S` is what rejects it.
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
