"""Item 11 stage 1b — ``CCXTConnector.connect()`` must not hold its caller.

WHAT A FAILURE HERE MEANS
=========================
Every coroutine in this application runs on the Qt GUI thread (the pump
timer in ``main.py``).  ``connect()`` used to call ``sync_connect``
inline, so awaiting it yielded nothing and the caller sat inside the
whole connect — up to about 111 s across a pre-flight, three
``load_markets`` attempts and two backoff sleeps.  That is a frozen
window.

If ``test_connect_runs_the_blocking_work_off_the_calling_thread`` fails,
the blocking call is back on the caller's thread and the GUI freeze has
returned.  If ``test_connect_still_connects`` fails, connect got fast by
not connecting, which is a worse regression than the freeze.  If
``test_sync_connect_still_blocks_its_own_caller`` fails, someone made
``sync_connect`` asynchronous and broke ``api_validator``, which calls it
directly and wants a blocking connect.

NO NETWORK.  The exchange is a fake, the pre-flight table is emptied and
the history scan is replaced by a recorder.  No real credentials appear
anywhere in this file.
"""

from __future__ import annotations

import asyncio
import threading
import time
import types

import pytest

from src.exchange import ccxt_connector as CC


CALLING_THREAD_TOLERANCE_S = 0.5
FAKE_MARKETS = {"BTC/USD": {"id": "BTC-USD"}, "ETH/USD": {"id": "ETH-USD"}}


class _FakeState:
    """Records what the fake exchange saw, and on which thread."""

    def __init__(self) -> None:
        self.load_calls = 0
        self.load_threads: list[str] = []
        self.scan_thread: str | None = None
        self.scan_saw_symbols: set[str] | None = None


def _install_fake_ccxt(monkeypatch, sleep_s: float, fail_attempts: int):
    """Point ``sync_connect`` at a fake exchange that sleeps, not fetches.

    The fake's surface is taken from what ``sync_connect`` actually reads
    — ``.has``, ``load_markets()``, ``.markets``, ``.markets_by_id``,
    ``.currencies``, ``.symbols`` — not from what these assertions would
    find convenient.
    """
    state = _FakeState()
    ccxt_id = CC.SUPPORTED_EXCHANGES["coinbase"]

    class FakeSyncExchange:
        def __init__(self, config):
            self.config = config
            self.has = {"fetchCurrencies": True}
            self.markets = None
            self.markets_by_id = None
            self.currencies = None
            self.symbols = None

        def load_markets(self):
            state.load_calls += 1
            state.load_threads.append(threading.current_thread().name)
            time.sleep(sleep_s)
            if state.load_calls <= fail_attempts:
                raise RuntimeError(
                    f"fake venue refused attempt {state.load_calls}")
            self.markets = dict(FAKE_MARKETS)
            self.markets_by_id = {
                v["id"]: k for k, v in FAKE_MARKETS.items()}
            self.currencies = {"BTC": {}, "ETH": {}, "USD": {}}
            self.symbols = sorted(FAKE_MARKETS)
            return self.markets

        def fetch_balance(self):
            # api_validator reads this straight off `_ccxt_sync`.
            return {"free": {"BTC": 0.5}, "total": {"BTC": 0.5, "USD": 0.0}}

    class FakeAsyncExchange:
        def __init__(self, config):
            self.config = config
            self.has = {"fetchCurrencies": True}
            self.markets = None
            self.markets_by_id = None
            self.currencies = None
            self.symbols = None

    sync_mod = types.ModuleType("ccxt")
    setattr(sync_mod, ccxt_id, FakeSyncExchange)
    async_mod = types.ModuleType("ccxt.async_support")
    setattr(async_mod, ccxt_id, FakeAsyncExchange)
    sync_mod.async_support = async_mod

    import sys
    monkeypatch.setitem(sys.modules, "ccxt", sync_mod)
    monkeypatch.setitem(sys.modules, "ccxt.async_support", async_mod)
    # A pre-flight is a real urlopen. This suite never touches the wire.
    monkeypatch.setattr(CC, "PREFLIGHT_URLS", {})
    return state


def _make_connector(monkeypatch, state: _FakeState):
    """A connector wired the way ``main_window`` wires one for a bot."""
    conn = CC.CCXTConnector("coinbase")

    def _record_scan():
        state.scan_thread = threading.current_thread().name
        state.scan_saw_symbols = set(conn._scan_symbols)

    monkeypatch.setattr(conn, "_scan_trade_history", _record_scan)
    # MEM-231: main_window.py registers the symbol BEFORE connect,
    # because the scan thread reads `_scan_symbols` at spawn time.
    conn.add_scan_symbol("BTC/USD")
    return conn


def _drive_connect_and_watch(conn):
    """Await ``connect`` while a ticker measures the calling thread.

    Returns ``(max_ticker_gap_s, tick_count, connect_wall_s)``.  The
    ticker shares the caller's thread, so a gap the size of the fake's
    sleep means the caller was held for that long.
    """
    ticks: list[float] = []

    async def _ticker(stop: asyncio.Event):
        while not stop.is_set():
            ticks.append(time.monotonic())
            await asyncio.sleep(0.01)

    async def _main():
        stop = asyncio.Event()
        watcher = asyncio.ensure_future(_ticker(stop))
        await asyncio.sleep(0.05)          # let the ticker settle
        t0 = time.monotonic()
        await conn.connect("fake-key", "fake-secret", "")
        wall = time.monotonic() - t0
        stop.set()
        await watcher
        return wall

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        wall = loop.run_until_complete(_main())
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    gaps = [ticks[i] - ticks[i - 1] for i in range(1, len(ticks))]
    return (max(gaps) if gaps else 0.0), len(ticks), wall


def test_connect_runs_the_blocking_work_off_the_calling_thread(monkeypatch):
    """The structural half: ``load_markets`` runs on the sync executor.

    Failure means ``connect()`` executed ``sync_connect`` inline again and
    the caller's thread carried the whole connect.
    """
    state = _install_fake_ccxt(monkeypatch, sleep_s=0.30, fail_attempts=0)
    conn = _make_connector(monkeypatch, state)
    caller = threading.current_thread().name

    _drive_connect_and_watch(conn)

    assert state.load_calls == 1
    assert state.load_threads == ["ccxt-coinbase_0"], state.load_threads
    assert caller not in state.load_threads


def test_connect_leaves_the_calling_thread_free_to_work(monkeypatch):
    """The timing half, read on the surface the operator feels.

    Failure means the caller could not run its own callbacks while the
    connect was in flight — on the GUI thread, a frozen window.
    """
    sleep_s = 1.0
    state = _install_fake_ccxt(monkeypatch, sleep_s=sleep_s, fail_attempts=0)
    conn = _make_connector(monkeypatch, state)

    max_gap, tick_count, wall = _drive_connect_and_watch(conn)

    assert wall >= sleep_s, "the fake did not actually sleep"
    assert max_gap < CALLING_THREAD_TOLERANCE_S, (
        f"calling thread was held {max_gap:.3f}s during a {wall:.3f}s "
        f"connect; the blocking call is back on the caller")
    assert tick_count > 20, tick_count


def test_connect_retry_path_also_stays_off_the_calling_thread(monkeypatch):
    """Three attempts plus both backoff sleeps, all off the caller.

    The pre-mortem for this unit named ``load_markets`` as the only
    blocking call.  It is not: the 2 s and 4 s ``time.sleep`` backoffs
    between attempts block too, and wrapping ``load_markets`` alone would
    have left them on the GUI thread.  Failure here means the retry path
    still freezes the caller even though the happy path does not.
    """
    state = _install_fake_ccxt(monkeypatch, sleep_s=0.05, fail_attempts=2)
    conn = _make_connector(monkeypatch, state)

    max_gap, _tick_count, wall = _drive_connect_and_watch(conn)

    assert state.load_calls == 3, state.load_calls
    assert set(state.load_threads) == {"ccxt-coinbase_0"}, state.load_threads
    # 2 s + 4 s of production backoff really elapsed.
    assert wall >= 6.0, wall
    assert max_gap < CALLING_THREAD_TOLERANCE_S, (
        f"calling thread was held {max_gap:.3f}s across the retry path")


def test_connect_still_connects(monkeypatch):
    """The hiding half. A connect that returns fast by not connecting is
    a worse regression than the freeze it replaced.
    """
    state = _install_fake_ccxt(monkeypatch, sleep_s=0.05, fail_attempts=0)
    conn = _make_connector(monkeypatch, state)

    _drive_connect_and_watch(conn)

    assert conn._connected is True
    assert conn.is_connected is True
    assert conn._ccxt_sync is not None
    assert conn._ccxt_sync.markets == FAKE_MARKETS
    # The async exchange is prepared and shares the loaded markets.
    assert conn._ccxt is not None
    assert conn._ccxt is not conn._ccxt_sync
    assert conn._ccxt.markets == FAKE_MARKETS
    assert conn._ccxt.symbols == sorted(FAKE_MARKETS)

    # The history scan thread spawned, and MEM-231's ordering held: the
    # symbol registered before connect was visible to the scan thread.
    deadline = time.monotonic() + 5.0
    while state.scan_thread is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert state.scan_thread == "trade-historian", state.scan_thread
    assert state.scan_saw_symbols == {"BTC/USD"}, state.scan_saw_symbols


def test_connect_propagates_the_failure_after_three_attempts(monkeypatch):
    """All three attempts fail — the caller still sees ConnectionError.

    Failure means the executor hand-off swallowed the error and a failed
    connect now looks successful.
    """
    state = _install_fake_ccxt(monkeypatch, sleep_s=0.01, fail_attempts=99)
    conn = _make_connector(monkeypatch, state)

    async def _main():
        await conn.connect("fake-key", "fake-secret", "")

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        with pytest.raises(ConnectionError):
            loop.run_until_complete(_main())
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    assert state.load_calls == 3, state.load_calls
    assert conn._connected is False


def test_sync_connect_still_blocks_its_own_caller(monkeypatch):
    """``api_validator`` calls ``sync_connect`` directly and wants it
    synchronous.  This pins that the sync path was NOT made async.

    Failure means ``sync_connect`` stopped being a blocking call, and
    ``api_validator.validate_credentials`` would return before the
    connection exists.
    """
    sleep_s = 0.40
    state = _install_fake_ccxt(monkeypatch, sleep_s=sleep_s, fail_attempts=0)
    conn = _make_connector(monkeypatch, state)
    caller = threading.current_thread().name

    t0 = time.monotonic()
    conn.sync_connect("fake-key", "fake-secret", "")
    elapsed = time.monotonic() - t0

    assert elapsed >= sleep_s, elapsed
    assert state.load_threads == [caller], state.load_threads
    assert conn._connected is True


def test_api_validator_still_validates(monkeypatch):
    """The named downstream caller, driven end to end.

    Failure means this unit broke the credential-test path in Settings.
    """
    state = _install_fake_ccxt(monkeypatch, sleep_s=0.01, fail_attempts=0)

    # `validate_credentials` builds its own connector, so the scan is
    # neutralised on the class rather than on an instance.
    scanned: list[str] = []
    monkeypatch.setattr(
        CC.CCXTConnector, "_scan_trade_history",
        lambda self: scanned.append(self._exchange_id))

    from src.exchange import api_validator

    result = api_validator.validate_credentials(
        "coinbase", "fake-key", "fake-secret", "")

    assert result.success is True, result.message
    assert result.exchange_id == "coinbase"
    assert "2 markets" in result.message, result.message
    assert result.balances == {"BTC": {"free": 0.5, "total": 0.5}}
    assert state.load_calls == 1
