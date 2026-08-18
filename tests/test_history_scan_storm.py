"""Each symbol's trade history is scanned once, not N times.

Operator, 2026-08-09, on being told the rate-limit errors predated this
session: "one or more instances of Claude has done all of the coding.
Investigate and fix any and all findings regardless of how long they
have been being missed or ignored."

THE DEFECT. `CCXTConnector.refresh_history(symbol)` did this:

    orig = self._scan_symbols.copy()
    self._scan_symbols = {symbol}
    self._scan_trade_history()
    self._scan_symbols = orig

and `add_scan_symbol` calls it in a DAEMON THREAD PER SYMBOL. With 37
bots registering at startup, 37 threads race on one mutable set: each
replaces it, and `_scan_trade_history` then iterates whatever is there
at that instant -- frequently another thread's restored snapshot of
every symbol. Each thread scans up to N symbols instead of 1.

MEASURED on the operator's 3.24.94 launch:

    distinct symbols scanned   37
    total scans             1,294
    scans per symbol         35.0     (correct: 1)
    N^2 for N=37             1,369

200 fetches went out in the first 24 seconds. `TradeHistorian._fetch_sync`
calls the RAW ccxt object, bypassing the connector's `_rate_limit()`, its
single-worker `_call_sync` executor and its retry decorator -- so nothing
spaced them. Coinbase rate-limited the lot: 1,708 fetch failures logged
as `TradeHistorian.analyze_sync(...)` errors, which is the wall of red
the operator has been seeing since 2026-07-30.

THE FIX IS THREE THINGS. Symbols pass as an argument instead of through
a shared field (removes the race). A lock serialises concurrent scans.
`scan_on_connect` sleeps between symbols at the connector's own
configured interval, since the guards that would normally do that are
bypassed on this path.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SYMS = [f"SYM{i:02d}/USD" for i in range(37)]


class _CountingExchange:
    """A raw-ccxt stand-in that records every fetch, with its symbol."""

    id = "counting"

    def __init__(self):
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def fetch_my_trades(self, symbol, limit=None):
        # `limit` is part of ccxt's signature and TradeHistorian passes
        # it; accepted and ignored because this stand-in returns no
        # trades. Named so the call shape stays honest.
        del limit
        with self._lock:
            self.calls.append(str(symbol))
        return []


class TestTheScannerItself:
    def test_one_fetch_per_symbol(self):
        from src.core.trade_historian import scan_on_connect
        ex = _CountingExchange()
        scan_on_connect(exchange=ex, symbols=list(SYMS))
        assert len(ex.calls) == len(SYMS)
        assert sorted(ex.calls) == sorted(SYMS)

    def test_pacing_sleeps_between_symbols_only(self):
        """A single-symbol refresh must stay immediate -- pacing that
        sleeps before the first fetch would add latency to the one case
        that is already cheap."""
        from src.core.trade_historian import scan_on_connect
        ex = _CountingExchange()
        t0 = time.monotonic()
        scan_on_connect(exchange=ex, symbols=["ONE/USD"], pace_s=0.5)
        assert time.monotonic() - t0 < 0.4

    def test_pacing_spaces_a_multi_symbol_scan(self):
        from src.core.trade_historian import scan_on_connect
        ex = _CountingExchange()
        t0 = time.monotonic()
        scan_on_connect(exchange=ex, symbols=SYMS[:4], pace_s=0.05)
        assert time.monotonic() - t0 >= 0.15 - 0.02

    def test_no_pacing_by_default(self):
        """Existing callers must not silently get slower."""
        from src.core.trade_historian import scan_on_connect
        ex = _CountingExchange()
        t0 = time.monotonic()
        scan_on_connect(exchange=ex, symbols=SYMS[:5])
        assert time.monotonic() - t0 < 0.2


class TestTheConnectorNoLongerRaces:
    def _connector(self):
        from src.exchange.ccxt_connector import CCXTConnector
        c = CCXTConnector("coinbase")
        c._ccxt_sync = _CountingExchange()
        c._min_request_interval = 0.0
        return c

    def test_refresh_history_scans_only_its_symbol(self):
        c = self._connector()
        c._scan_symbols = set(SYMS)
        c.refresh_history("SYM07/USD")
        assert c._ccxt_sync.calls == ["SYM07/USD"]

    def test_refresh_history_does_not_mutate_the_registry(self):
        """THE RACE. The old code swapped `_scan_symbols` out and back;
        36 other threads read it in between."""
        c = self._connector()
        c._scan_symbols = set(SYMS)
        before = set(c._scan_symbols)
        c.refresh_history("SYM07/USD")
        assert c._scan_symbols == before

    def test_concurrent_refreshes_do_not_amplify(self):
        """THE REPRODUCTION. 37 threads, one per symbol, exactly as
        `add_scan_symbol` spawns them. The old code produced ~35 fetches
        per symbol; correct is exactly one."""
        c = self._connector()
        c._scan_symbols = set(SYMS)
        threads = [threading.Thread(target=c.refresh_history, args=(s,))
                   for s in SYMS]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        calls = c._ccxt_sync.calls
        assert len(calls) == len(SYMS), (
            f"{len(calls)} fetches for {len(SYMS)} symbols "
            f"({len(calls) / len(SYMS):.1f}x amplification)")
        assert sorted(calls) == sorted(SYMS)

    def test_the_race_mechanism_amplifies(self):
        """NEGATIVE CONTROL, forced rather than hoped for.

        Two earlier attempts at this control were unsound. Re-running
        the old body against the patched connector cannot race, because
        the fix also added a lock. A timing-based model did not race
        either -- without real network I/O the window between swap and
        read is a few bytecodes wide, so the interleaving essentially
        never happens in-process.

        In production the window is a live `fetch_my_trades` per symbol,
        which is why it happened on every launch. So this FORCES the
        exact interleaving with events instead of waiting for luck:

            B swaps the shared set to its own symbol
            A restores the FULL registry           <-- the collision
            B reads the shared set and sees ALL of it

        That read is the scan: B fetches 37 symbols instead of 1. Repeat
        across 37 threads and it is the 35x the operator's log recorded.
        """
        full = set(SYMS)
        shared = set(full)
        b_swapped = threading.Event()
        a_restored = threading.Event()
        seen: list[int] = []

        def thread_a():
            b_swapped.wait(timeout=10)
            shared.clear()
            shared.update(full)       # restore its snapshot
            a_restored.set()

        def thread_b():
            shared.clear()
            shared.add("SYM07/USD")   # "only my symbol"
            b_swapped.set()
            a_restored.wait(timeout=10)
            seen.append(len(shared))  # what its scan would iterate

        ta, tb = threading.Thread(target=thread_a), threading.Thread(target=thread_b)
        ta.start(); tb.start()
        ta.join(timeout=15); tb.join(timeout=15)

        assert seen and seen[0] > 1, (
            f"expected the swapped-out set to be observed as many "
            f"symbols, saw {seen}")
        assert seen[0] == len(SYMS), (
            f"B should observe the whole registry, saw {seen[0]}")

    def test_passing_by_argument_cannot_race(self):
        """The same N threads, but each scan is handed its own list.
        There is no shared value to observe, so amplification is not
        possible by construction rather than by timing."""
        c = self._connector()
        c._scan_symbols = set(SYMS)
        barrier = threading.Barrier(len(SYMS))

        def refresh(symbol):
            barrier.wait()
            c.refresh_history(symbol)

        threads = [threading.Thread(target=refresh, args=(s_,))
                   for s_ in SYMS]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert len(c._ccxt_sync.calls) == len(SYMS)
        assert sorted(c._ccxt_sync.calls) == sorted(SYMS)


class TestFullScanStillWorks:
    def test_a_full_scan_covers_every_registered_symbol(self):
        from src.exchange.ccxt_connector import CCXTConnector
        c = CCXTConnector("coinbase")
        c._ccxt_sync = _CountingExchange()
        c._min_request_interval = 0.0
        c._scan_symbols = set(SYMS)
        c.refresh_history()
        assert sorted(c._ccxt_sync.calls) == sorted(SYMS)

    def test_an_empty_registry_fetches_nothing(self):
        from src.exchange.ccxt_connector import CCXTConnector
        c = CCXTConnector("coinbase")
        c._ccxt_sync = _CountingExchange()
        c._scan_symbols = set()
        c.refresh_history()
        assert c._ccxt_sync.calls == []
