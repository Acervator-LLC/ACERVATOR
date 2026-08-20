"""Pins the duration on `fleet.03.004.postcondition.wires_loaded`.

Fourth of the six clean owners
(docs/audits/2026-08-19_emitter_duration_classification.md). Sole emitter in
`load_smart_wires_from_state`, so no start marker and no sibling to fence off.

THE MALFORMED BRANCH IS NOT AN OMISSION. When `smart_wires` is not a list the
function returns early and emits NOTHING, so there is no record to carry a
duration. `test_a_refused_load_emits_nothing_at_all` holds that, because "no
duration" and "no record" must not be confusable — silence that means "never
ran" is the failure this network was built to remove.
"""

from __future__ import annotations

import time
from typing import Optional

import pytest

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink
from src.gui.simulator_tab.fleet import bot_state_loader as bsl

EMITTER = "fleet.03.004.postcondition.wires_loaded"

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


def _drive(monkeypatch, burn_s: float, sink: SignalSink, payload=None) -> list:
    def _slow_read(_path):
        _busy_wait(burn_s)
        return {"smart_wires": [{"source_id": "a", "target_id": "b",
                                 "pct": 1.0}] if payload is None else payload}

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


def test_the_wires_emitter_carries_a_duration(monkeypatch):
    sink = SignalSink()
    _drive(monkeypatch, SHORT_S, sink)
    got = _durations(sink)
    assert len(got) == 1, got
    assert got[0] is not None


def test_the_duration_tracks_two_different_load_costs(monkeypatch):
    """THE control. Present-but-constant passes existence and fails this."""
    sink = SignalSink()
    _drive(monkeypatch, SHORT_S, sink)
    _drive(monkeypatch, LONG_S, sink)

    short, long_ = _durations(sink)
    assert short == pytest.approx(SHORT_S, abs=0.005), short
    assert long_ == pytest.approx(LONG_S, abs=0.015), long_
    assert _tracks(short, long_), f"did not track: {short} vs {long_}"


def test_the_tracking_predicate_rejects_a_constant_duration():
    """The other half, so the control above cannot pass while measuring nothing."""
    assert not _tracks(0.01, 0.01)
    assert not _tracks(None, None)
    assert not _tracks(0.03, 0.005)
    assert _tracks(0.005, 0.030)


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
