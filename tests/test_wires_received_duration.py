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
ends; the lost-row tally and the operator warning that follow are REPORTING.
Timing those would bill the report to the import, and making the log cheaper
would read as a faster import.
"""

from __future__ import annotations

from typing import Optional

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink
from src.trading.smart_wire import SmartWireManager

EMITTER = "topology.09.002.postcondition.wires_received"

SMALL_ROWS = 1_000
LARGE_ROWS = 10_000


def _rows(k: int) -> list[dict]:
    return [{"source_id": f"s{i}", "target_id": f"t{i}", "pct": 5.0}
            for i in range(k)]


def _tracks(small: Optional[float], large: Optional[float]) -> bool:
    if small is None or large is None:
        return False
    return large > small * 2.0


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


def test_the_import_emitter_carries_a_duration():
    _warm_up()
    sink = SignalSink()
    _drive(sink, _rows(SMALL_ROWS))
    got = _durations(sink)
    assert len(got) == 1, got
    assert got[0] is not None


def test_the_duration_tracks_a_genuinely_larger_import():
    """THE control, on real work rather than an injected delay."""
    _warm_up()
    sink = SignalSink()
    _drive(sink, _rows(SMALL_ROWS))
    _drive(sink, _rows(LARGE_ROWS))

    small, large = _durations(sink)
    assert _tracks(small, large), (
        f"{LARGE_ROWS} rows did not record longer than {SMALL_ROWS}: "
        f"{small} vs {large}")


def test_the_tracking_predicate_rejects_a_constant_duration():
    """The other half, so the control above cannot pass while measuring nothing."""
    assert not _tracks(0.01, 0.01)
    assert not _tracks(None, None)
    assert not _tracks(0.03, 0.005)
    assert _tracks(0.005, 0.030)


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

    sibling = [r.duration for r in sink.records()
               if r.name == "topology.09.001.state_transition.bot_attached"]
    assert sibling, "the sibling did not fire; the control proves nothing"
    assert all(d is None for d in sibling), sibling
