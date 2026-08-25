"""v3.23.74 — pin tests for MarketDataPool.get_or_fetch_ohlcv.

Regression fixture for the CPM saturation the operator reported on
2026-07-31: ScrummingBot bypassed the pool for OHLCV
(scrumming_bot.py:5254 + 5433 hit the exchange directly on every
action tick), so N bots on the same (exchange, symbol, TF) each
paid their own OHLCV call. v3.23.74 adds pool coalescing; these
tests pin the invariants a future refactor mustn't silently break:

    1. Fresh cache hit → zero connector calls
    2. Stale cache → exactly one connector call
    3. Concurrent requests coalesce to one fetch
    4. TTL matches the timeframe
    5. Different (exchange, symbol, TF) → separate slots
    6. Telemetry counters increment correctly
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.data_pool import (  # noqa: E402
    MarketDataPool,
    TF_SECONDS,
)


class _FakeConnector:
    """Records every get_ohlcv call and returns fabricated candles."""

    def __init__(self):
        self.calls: list[dict] = []

    async def get_ohlcv(self, symbol, timeframe, limit=100):
        self.calls.append({"symbol": symbol, "timeframe": timeframe, "limit": limit})
        # Fabricate `limit` candles, each 5m apart.
        base_ts = 1_700_000_000_000
        return [
            [base_ts + i * 300_000, 100.0 + i, 105.0 + i, 95.0 + i, 100.0 + i, 10.0]
            for i in range(limit)
        ]


def test_get_or_fetch_ohlcv_populates_cache():
    pool = MarketDataPool()
    conn = _FakeConnector()
    out = asyncio.run(
        pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "5m", limit=50)
    )
    assert len(out) == 50
    assert len(conn.calls) == 1
    assert conn.calls[0]["symbol"] == "BTC/USD"
    assert conn.calls[0]["timeframe"] == "5m"


def test_fresh_cache_hit_does_not_fetch():
    pool = MarketDataPool()
    conn = _FakeConnector()
    asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "5m", limit=50))
    # Second call within TTL → no new API call
    asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "5m", limit=50))
    assert len(conn.calls) == 1
    assert pool._ohlcv_cache_hits == 1


def test_concurrent_requests_coalesce_to_one_fetch():
    """N bots requesting the same slot concurrently → 1 API call.
    The lock ensures the first awaiter fetches and the rest read
    from cache after the lock releases."""
    pool = MarketDataPool()
    conn = _FakeConnector()

    async def run():
        # Fire 10 concurrent requests for the same slot
        results = await asyncio.gather(
            *[
                pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "5m", limit=50)
                for _ in range(10)
            ]
        )
        return results

    results = asyncio.run(run())
    assert len(results) == 10
    assert all(len(r) == 50 for r in results)
    assert len(conn.calls) == 1, f"expected 1 coalesced fetch, got {len(conn.calls)}"


def test_stale_cache_triggers_refetch(monkeypatch):
    pool = MarketDataPool()
    conn = _FakeConnector()
    asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "5m", limit=50))
    # Fast-forward time past the 5m TTL
    original_time = time.time
    monkeypatch.setattr(
        "src.exchange.data_pool.time.time",
        lambda: original_time() + TF_SECONDS["5m"] + 1,
    )
    asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "5m", limit=50))
    assert len(conn.calls) == 2


def test_ttl_matches_timeframe():
    pool = MarketDataPool()
    conn = _FakeConnector()
    for tf in ("5m", "1h", "4h"):
        pool._candles.clear()
        pool._ohlcv_fetches = 0
        asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", tf, limit=10))
        key = f"coinbase|BTC/USD|{tf}"
        entry = pool._candles[key]
        assert entry.ttl_seconds == TF_SECONDS[tf]


def test_different_slots_are_independent():
    pool = MarketDataPool()
    conn = _FakeConnector()
    asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "5m", limit=50))
    asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "ETH/USD", "5m", limit=50))
    asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "1h", limit=50))
    # 3 different slots → 3 different fetches
    assert len(conn.calls) == 3


def test_pull_rate_summary_shape():
    pool = MarketDataPool()
    conn = _FakeConnector()
    asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "5m", limit=10))
    s = pool.pull_rate_summary()
    assert s["ohlcv_slots"] == 1
    assert s["ohlcv_fetches"] == 1
    assert s["next_pull_s"] >= 0
    assert s["next_pull_s"] <= TF_SECONDS["5m"]


def test_pull_rate_summary_empty_pool_is_inf():
    pool = MarketDataPool()
    assert pool.seconds_until_next_pull() == float("inf")


def test_balance_coalescing_hits_cache_within_ttl():
    """v3.23.76 — balance coalescing mirrors the OHLCV pattern.
    Two calls within TTL → one API call + one cache hit."""
    pool = MarketDataPool()

    class _BalConn:
        def __init__(self):
            self.calls = 0

        async def get_balance(self, currency):
            self.calls += 1
            from src.exchange.base import Balance

            return Balance(
                currency=currency, free=100.0, used=0.0, total=100.0, absent=False
            )

    conn = _BalConn()
    asyncio.run(pool.get_or_fetch_balance(conn, "coinbase", "USD"))
    asyncio.run(pool.get_or_fetch_balance(conn, "coinbase", "USD"))
    assert conn.calls == 1
    assert pool._balance_cache_hits == 1


def test_balance_concurrent_requests_coalesce():
    """N concurrent get_or_fetch_balance requests for the same slot
    must produce exactly one API call."""
    pool = MarketDataPool()

    class _BalConn:
        def __init__(self):
            self.calls = 0

        async def get_balance(self, currency):
            self.calls += 1
            from src.exchange.base import Balance

            return Balance(
                currency=currency, free=100.0, used=0.0, total=100.0, absent=False
            )

    conn = _BalConn()

    async def run():
        return await asyncio.gather(
            *[pool.get_or_fetch_balance(conn, "coinbase", "USD") for _ in range(10)]
        )

    results = asyncio.run(run())
    assert len(results) == 10
    assert conn.calls == 1


def test_balance_invalidate_forces_refetch():
    """After invalidate_balance, the next call re-fetches."""
    pool = MarketDataPool()

    class _BalConn:
        def __init__(self):
            self.calls = 0

        async def get_balance(self, currency):
            self.calls += 1
            from src.exchange.base import Balance

            return Balance(
                currency=currency, free=100.0, used=0.0, total=100.0, absent=False
            )

    conn = _BalConn()
    asyncio.run(pool.get_or_fetch_balance(conn, "coinbase", "USD"))
    assert conn.calls == 1
    n = pool.invalidate_balance("coinbase", "USD")
    assert n == 1
    asyncio.run(pool.get_or_fetch_balance(conn, "coinbase", "USD"))
    assert conn.calls == 2


def test_slot_ages_reports_freshest_and_oldest(monkeypatch):
    """v3.23.76 — slot_ages replaces the misleading 'next pull'
    countdown with actionable freshest/oldest diagnostics."""
    pool = MarketDataPool()
    conn = _FakeConnector()
    # First fetch — freshest_age near 0
    asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "5m", limit=10))
    ages = pool.slot_ages()
    assert ages["fetched_slots"] == 1
    assert ages["freshest_age_s"] is not None
    assert ages["freshest_age_s"] < 1.0
    assert ages["stale_slots"] == 0
    # Fast-forward past TTL — should count as stale
    original_time = time.time
    monkeypatch.setattr(
        "src.exchange.data_pool.time.time",
        lambda: original_time() + TF_SECONDS["5m"] + 10,
    )
    ages2 = pool.slot_ages()
    assert ages2["stale_slots"] == 1


def test_slot_ages_empty_pool():
    pool = MarketDataPool()
    ages = pool.slot_ages()
    assert ages["freshest_age_s"] is None
    assert ages["oldest_age_s"] is None
    assert ages["fetched_slots"] == 0


def test_larger_limit_request_triggers_refetch():
    """Cache stores at least `limit` rows; a request for MORE rows
    than cached triggers a fresh fetch."""
    pool = MarketDataPool()
    conn = _FakeConnector()
    asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "5m", limit=50))
    asyncio.run(pool.get_or_fetch_ohlcv(conn, "coinbase", "BTC/USD", "5m", limit=200))
    assert len(conn.calls) == 2
