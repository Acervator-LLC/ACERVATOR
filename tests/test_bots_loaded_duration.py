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


def _busy_wait(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass


def _tracks(short: Optional[float], long_: Optional[float]) -> bool:
    if short is None or long_ is None:
        return False
    return long_ > short * 2.0


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


def test_the_owner_carries_a_duration(monkeypatch):
    sink = SignalSink()
    _drive(monkeypatch, SHORT_S, sink)
    got = _durations(sink, OWNER)
    assert len(got) == 1, got
    assert got[0] is not None, "the load emitter recorded no duration"


def test_the_duration_tracks_two_different_load_costs(monkeypatch):
    """THE control. Present-but-constant passes existence and fails this."""
    sink = SignalSink()
    _drive(monkeypatch, SHORT_S, sink)
    _drive(monkeypatch, LONG_S, sink)

    short, long_ = _durations(sink, OWNER)
    assert short == pytest.approx(SHORT_S, abs=0.005), short
    assert long_ == pytest.approx(LONG_S, abs=0.015), long_
    assert _tracks(short, long_), f"did not track: {short} vs {long_}"


def test_the_tracking_predicate_rejects_a_constant_duration():
    """The other half, so the control above cannot pass while measuring nothing."""
    assert not _tracks(0.01, 0.01)
    assert not _tracks(None, None)
    assert not _tracks(0.03, 0.005)
    assert _tracks(0.005, 0.030)


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
