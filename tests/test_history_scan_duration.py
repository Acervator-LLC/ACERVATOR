"""Pins the duration on `history.05.001.postcondition.scan_complete`.

Second of the six emitters classified as clean owners of a bounded operation
(docs/audits/2026-08-19_emitter_duration_classification.md). It is the sole
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


class _FakeConnector:
    """The minimum surface `_scan_trade_history` touches.

    Deliberately not a real `CCXTConnector`: constructing one opens a venue
    session. The method is called unbound against this stand-in, so the code
    under test is the shipping code, not a copy of it.
    """

    def __init__(self) -> None:
        self._ccxt_sync = object()          # truthy: passes the entry guard
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

    monkeypatch.setattr(
        "src.exchange.ccxt_connector.scan_on_connect", _fake_scan)
    previous = sc.get_sink()
    sc.set_sink(sink)
    try:
        CCXTConnector._scan_trade_history(_FakeConnector(), symbols=["BTC/USD"])
    finally:
        # Restore the PREVIOUS sink, never None. `set_sink` is process-global.
        sc.set_sink(previous)


def _durations(sink: SignalSink) -> list:
    return [r.duration for r in sink.records() if r.name == EMITTER]


def test_the_scan_emitter_carries_a_duration_at_all(monkeypatch):
    sink = SignalSink()
    _drive(monkeypatch, SHORT_S, sink)
    got = _durations(sink)
    assert len(got) == 1, got
    assert got[0] is not None, "the scan emitter recorded no duration"


def test_the_duration_tracks_two_different_scan_lengths(monkeypatch):
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

    monkeypatch.setattr(
        "src.exchange.ccxt_connector.scan_on_connect", _fake_scan)

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
        f"must start inside the lock, not before it")
