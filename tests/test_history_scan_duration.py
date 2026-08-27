"""Pins the duration on `history.05.001.postcondition.scan_complete`.

Second of the six emitters classified as clean owners of a bounded operation
(docs/engineering-notes/2026-08-19_emitter_duration_classification.md). It is the sole
emitter in `_scan_trade_history`, so no start marker and no double-count risk.

WHAT THE TIMER DELIBERATELY EXCLUDES, and why a test says so. The scan runs
inside `_history_scan_lock`, which makes concurrent scans QUEUE rather than
pile up. The clock starts INSIDE that lock, so a caller that waited its turn
does not report the wait as scan time. Folding lock-wait and fetch into one
number would leave a reader unable to tell "the venue was slow" from "this scan
queued" -- two causes behind one value, which is the disjunction defect this
repo has already been bitten by. `test_the_duration_excludes_time_spent_waiting_for_the_lock`
is what stops that being quietly reintroduced.

Driven through the REAL `_scan_trade_history`, with only the network call
replaced. Asserting that the argument appears in the source would not catch a
timer bracketing the emit instead of the work.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

import pytest

from src.core import signal_contract as sc
from src.core.signal_contract import SignalSink
from src.exchange.ccxt_connector import CCXTConnector

EMITTER = "history.05.001.postcondition.scan_complete"

SHORT_S = 0.005
LONG_S = 0.030
LOCK_HOLD_S = 0.060

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
# emitter: the 0.005 s scan recorded 0.005000 s to 0.005003 s and the
# 0.030 s scan recorded 0.030001 s to 0.030006 s. The lever is what the bracket is asked to see, so
# a pause of 10 ms inside the SHORT region is all it takes to close
# a gap that reads as comfortable.
SAMPLES = 5

# THE FLOOR, and the measurement that says it is not optional.
#
# Move the stop clock above the work and the bracket spans nothing:
# every reading collapses to the cost of two `time.monotonic()` calls,
# and a ratio between two numbers that small is a coin flip rather than
# a measurement. Measured 2026-08-20 with the stop clock planted above
# the work at this exact site, 120 readings: every reading fell between 0.0 s and 5.0e-07 s. The bare ratio
# ACCEPTED 4 of 30 pairs, and the minimum of five samples accepted 4 of 30.
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
    """Burn a known interval on the monotonic clock, without yielding."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass


def _tracks(short: Optional[float], long_: Optional[float]) -> bool:
    """Did the duration MOVE with the work. Driven both ways below."""
    if short is None or long_ is None:
        return False
    return long_ > short * 2.0


def _tracks_the_scan(short: Optional[float], long_: Optional[float]) -> bool:
    """Ask `_tracks`, then put a floor under the long reading.

    This ADDS a condition and relaxes none: everything `_tracks`
    refuses is still refused here. The floor is the thing a ratio
    cannot do -- tell a real scan from a bracket that
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


class _FakeConnector:
    """The minimum surface `_scan_trade_history` touches.

    Deliberately not a real `CCXTConnector`: constructing one opens a venue
    session. The method is called unbound against this stand-in, so the code
    under test is the shipping code, not a copy of it.
    """

    def __init__(self) -> None:
        self._ccxt_sync = object()  # truthy: passes the entry guard
        self._scan_symbols = {"BTC/USD"}
        self._history_scan_lock = threading.Lock()
        self._history_analyses: dict = {}
        self._min_request_interval = 0.0

    def _on_history_result(self, *_a, **_k) -> None:
        return None


def _drive(monkeypatch, burn_s: float, sink: SignalSink) -> None:
    """Run the real scan path once, with the network call replaced."""

    # `scan_on_connect` is called entirely by keyword, so the arguments
    # this stand-in does not need are collected rather than named.
    def _fake_scan(symbols=None, **_kwargs):
        _busy_wait(burn_s)
        return {s: object() for s in (symbols or [])}

    monkeypatch.setattr("src.exchange.ccxt_connector.scan_on_connect", _fake_scan)
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        CCXTConnector._scan_trade_history(_FakeConnector(), symbols=["BTC/USD"])
    finally:
        # Restore the PREVIOUS sink, never None. `set_sink` is process-global.
        sc.set_sink(previous)


def _durations(sink: SignalSink) -> list:
    return [r.duration for r in sink.records() if r.name == EMITTER]


def _fastest_scan(monkeypatch, burn_s: float) -> Optional[float]:
    """The lowest duration `SAMPLES` real scans of cost `burn_s` record.

    Each sample is a whole real `_scan_trade_history` call read back
    off the real emitter. Nothing is stubbed beyond the network call
    the file already stubs, the clock is never touched and no recorded
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


def test_the_scan_emitter_carries_a_duration_at_all(monkeypatch):
    sink = SignalSink()
    _drive(monkeypatch, SHORT_S, sink)
    got = _durations(sink)
    assert len(got) == 1, got
    assert got[0] is not None, "the scan emitter recorded no duration"


def test_the_duration_tracks_two_different_scan_lengths(monkeypatch):
    """THE control. Present-but-constant passes existence and fails this.

    Each workload is measured `SAMPLES` times and the MINIMUM of the
    samples is compared. A pause inside one bracketed region inflates
    that one sample and the minimum discards it. Nothing compared here
    is relaxed: both sides are still real durations read off the real
    emitter, and both must still clear the floor and the ratio.
    """
    short = _fastest_scan(monkeypatch, SHORT_S)
    long_ = _fastest_scan(monkeypatch, LONG_S)

    assert short == pytest.approx(SHORT_S, abs=0.005), short
    assert long_ == pytest.approx(LONG_S, abs=0.015), long_
    assert _tracks_the_scan(short, long_), f"did not track: {short} vs {long_}"


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
    assert not _tracks_the_scan(
        0.01, 0.01
    ), "a constant duration must not read as tracking"
    assert not _tracks_the_scan(
        None, LONG_S
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_scan(
        SHORT_S, None
    ), "an absent duration must not read as tracking"
    assert not _tracks_the_scan(
        LONG_S, SHORT_S
    ), "going backwards must not read as tracking"

    # THE DEAD CLOCK, and the measured reason this site carries a floor
    # the shared predicate does not. This pair is a real one, harvested
    # 2026-08-20 with the stop clock planted above the work. `_tracks`
    # accepts it. The floor rejects it. That is an addition to
    # `_tracks`, never a relaxation of it.
    assert _tracks(
        0.0, 5.0e-07
    ), "the shared predicate is expected to accept a dead clock here"
    assert not _tracks_the_scan(
        0.0, 5.0e-07
    ), "a bracket that spans no work must not read as tracking"

    # The honest pair measured off the real site, 2026-08-20, must
    # still read as tracking.
    assert _tracks_the_scan(
        0.005000, 0.030001
    ), "the real measured pair must read as tracking"


def test_the_duration_excludes_time_spent_waiting_for_the_lock(monkeypatch):
    """Lock-wait is NOT scan time, and this is the test that keeps it that way.

    A second thread holds `_history_scan_lock` while the scan tries to start.
    The recorded duration must reflect the SCAN only, not the wait -- otherwise
    a queued scan reports as a slow venue and item 17 reads the wrong cause.
    """
    sink = SignalSink()

    # `scan_on_connect` is called entirely by keyword, so the arguments
    # this stand-in does not need are collected rather than named.
    def _fake_scan(symbols=None, **_kwargs):
        _busy_wait(SHORT_S)
        return {s: object() for s in (symbols or [])}

    monkeypatch.setattr("src.exchange.ccxt_connector.scan_on_connect", _fake_scan)

    conn = _FakeConnector()
    released = threading.Event()

    def _hold() -> None:
        with conn._history_scan_lock:
            released.set()
            _busy_wait(LOCK_HOLD_S)

    holder = threading.Thread(target=_hold)
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        holder.start()
        released.wait(timeout=5.0)
        # Blocks until the holder lets go, so the call really does queue.
        CCXTConnector._scan_trade_history(conn, symbols=["BTC/USD"])
    finally:
        holder.join(timeout=5.0)
        sc.set_sink(previous)

    got = _durations(sink)
    assert len(got) == 1, got
    assert got[0] == pytest.approx(SHORT_S, abs=0.010), got[0]
    assert got[0] < LOCK_HOLD_S, (
        f"duration {got[0]} includes the {LOCK_HOLD_S}s lock wait; the clock "
        f"must start inside the lock, not before it"
    )
