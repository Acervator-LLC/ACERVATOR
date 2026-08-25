"""The bulk ticker refresh that unsticks the Ammo readout.

THE DEFECT
`stats.current_price` is written after the read-rate gate in
`ScrummingBot.tick`, so a bot's DISPLAYED price refreshes at its
DECISION cadence. Measured against live state 2026-08-06 with
tick_interval=5.0s: 18 of 35 bots refreshed at 60s or slower, worst
ALLO/USDC at 300s, while the dashboard repainted every 2s.

WHY THE SHARED POOL COULD NOT ALREADY FIX IT
The fleet runs 35 distinct symbols with ZERO overlap, so each cache
entry has exactly one writer -- the bot that owns it. Reading the pool
from the GUI returns the same stale value. That dead end is what makes
the bulk call necessary rather than merely nice.

WHY THIS IS CHEAPER THAN WHAT IT REPLACES
`get_all_tickers` returns every symbol for one rate-limited call; per-bot
polling spends 35 to cover the same ground. Warming the cache means bots
hit the fast path in `get_or_fetch_ticker` instead of fetching, so this
REPLACES traffic. Projection: 10,272 fetches/hour -> ~720 at a 5s batch
interval, worst-case staleness 300s -> 5s. Both axes improve; the old
design was dominated, not balanced.

THE FIELD MAPPING IS THE DANGEROUS PART
`volume_24h` comes from CCXT's `quoteVolume`, NOT `baseVolume`, and
`timestamp` is milliseconds that must be divided by 1000. Both are easy
to guess wrong and neither would raise -- it would just quietly corrupt
the cache for every consumer. `TestTheFieldMappingMatchesTheConnector`
locks them against the connector's own source.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.exchange.data_pool import (  # noqa: E402
    MarketDataPool,
    TickerEntry,
    _ticker_key,
)


class _Conn:
    """Stands in for CCXTConnector. Records whether it was called."""

    def __init__(self, payload=None, boom=None):
        self._payload = payload if payload is not None else {}
        self._boom = boom
        self.calls = 0

    async def get_all_tickers(self):
        self.calls += 1
        if self._boom is not None:
            raise self._boom
        return self._payload


def _pool_with(*entries):
    pool = MarketDataPool()
    for e in entries:
        pool._tickers[_ticker_key(e.exchange_id, e.symbol)] = e
    return pool


def _entry(symbol, exchange_id="coinbase", last=0.0, fetch_time=0.0):
    return TickerEntry(
        exchange_id=exchange_id, symbol=symbol, last=last, fetch_time=fetch_time
    )


def _row(last=None, bid=1.0, ask=2.0, quote_vol=999.0, ts_ms=1_700_000_000_000):
    return {
        "last": last,
        "bid": bid,
        "ask": ask,
        "quoteVolume": quote_vol,
        "baseVolume": 11.0,
        "timestamp": ts_ms,
    }


class TestTheInstrumentWorks:
    @pytest.mark.asyncio
    async def test_a_refresh_updates_a_cached_entry(self):
        """POSITIVE CONTROL. Every assertion below assumes a refresh can
        move a price at all. If this fails the rest are vacuous."""
        e = _entry("BTC/USD", last=100.0)
        pool = _pool_with(e)
        n = await pool.refresh_all_tickers(
            _Conn({"BTC/USD": _row(last=250.0)}), "coinbase"
        )
        assert n == 1
        assert e.last == pytest.approx(250.0)

    @pytest.mark.asyncio
    async def test_the_entry_was_stale_before_the_refresh(self):
        """NEGATIVE CONTROL on the premise: the batch is what makes it
        fresh. If the entry were already fresh there was nothing to fix."""
        e = _entry("BTC/USD", last=100.0)
        assert e.is_stale, "fetch_time=0 must read as stale"
        await _pool_with(e).refresh_all_tickers(
            _Conn({"BTC/USD": _row(last=250.0)}), "coinbase"
        )
        assert not e.is_stale


class TestTheFieldMappingMatchesTheConnector:
    """A units mismatch here corrupts the cache silently. Lock it to the
    connector's own normalisation rather than to my memory of it."""

    def _refresh_src(self):
        import src.exchange.data_pool as dp

        src = Path(dp.__file__).read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "refresh_all_tickers"
        )
        return ast.get_source_segment(src, fn) or ""

    def _connector_src(self):
        import src.exchange.ccxt_connector as cc

        src = Path(cc.__file__).read_text(encoding="utf-8")
        fn = next(
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "get_ticker"
        )
        return ast.get_source_segment(src, fn) or ""

    def test_both_read_quote_volume_not_base_volume(self):
        conn, refresh = self._connector_src(), self._refresh_src()
        assert "quoteVolume" in conn, "connector changed; re-derive the map"
        assert "quoteVolume" in refresh
        # The bulk payload carries baseVolume too. Taking it would be
        # wrong by a factor of the price.
        assert '"baseVolume"' not in refresh

    def test_both_convert_the_timestamp_from_milliseconds(self):
        conn, refresh = self._connector_src(), self._refresh_src()
        assert "/ 1000" in conn, "connector changed; re-derive the map"
        assert "/ 1000" in refresh

    @pytest.mark.asyncio
    async def test_the_mapping_holds_at_runtime(self):
        e = _entry("BTC/USD")
        await _pool_with(e).refresh_all_tickers(
            _Conn(
                {"BTC/USD": _row(last=5.0, quote_vol=777.0, ts_ms=1_700_000_000_000)}
            ),
            "coinbase",
        )
        assert e.volume_24h == pytest.approx(777.0)
        assert e.timestamp == pytest.approx(1_700_000_000.0)


class TestItOnlyTouchesWhatItShould:
    @pytest.mark.asyncio
    async def test_uncached_symbols_are_not_adopted(self):
        """The bulk response lists every pair on the exchange. Adopting
        them would grow this dict without bound for symbols no bot
        trades."""
        pool = _pool_with(_entry("BTC/USD"))
        await pool.refresh_all_tickers(
            _Conn(
                {
                    "BTC/USD": _row(last=1.0),
                    "DOGE/USD": _row(last=2.0),
                    "SHIB/USD": _row(last=3.0),
                }
            ),
            "coinbase",
        )
        assert set(pool._tickers) == {_ticker_key("coinbase", "BTC/USD")}

    @pytest.mark.asyncio
    async def test_another_exchange_is_left_alone(self):
        other = _entry("BTC/USD", exchange_id="kraken", last=9.0)
        pool = _pool_with(_entry("BTC/USD", last=1.0), other)
        n = await pool.refresh_all_tickers(
            _Conn({"BTC/USD": _row(last=500.0)}), "coinbase"
        )
        assert n == 1
        assert other.last == pytest.approx(9.0)

    @pytest.mark.asyncio
    async def test_a_symbol_missing_from_the_payload_is_untouched(self):
        e = _entry("RARE/USD", last=42.0)
        pool = _pool_with(e)
        assert (
            await pool.refresh_all_tickers(
                _Conn({"BTC/USD": _row(last=1.0)}), "coinbase"
            )
            == 0
        )
        assert e.last == pytest.approx(42.0)


class TestItNeverMakesThingsWorse:
    @pytest.mark.asyncio
    async def test_a_junk_row_does_not_blank_a_good_price(self):
        """Reporting $0 for a live position is far worse than showing a
        price a few seconds old."""
        e = _entry("BTC/USD", last=100.0)
        await _pool_with(e).refresh_all_tickers(
            _Conn({"BTC/USD": _row(last=0.0)}), "coinbase"
        )
        assert e.last == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_a_non_dict_row_is_skipped(self):
        e = _entry("BTC/USD", last=100.0)
        await _pool_with(e).refresh_all_tickers(
            _Conn({"BTC/USD": "not-a-row"}), "coinbase"
        )
        assert e.last == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_a_newer_individual_fetch_is_not_clobbered(self):
        """A bot's own fetch can land while the batch is in flight. That
        value is newer than the batch payload; overwriting it would walk
        the price BACKWARDS."""
        import time

        e = _entry("BTC/USD", last=100.0, fetch_time=time.time() + 60)
        pool = _pool_with(e)
        assert (
            await pool.refresh_all_tickers(
                _Conn({"BTC/USD": _row(last=500.0)}), "coinbase"
            )
            == 0
        )
        assert e.last == pytest.approx(100.0)
        assert pool._ticker_batch_races == 1

    @pytest.mark.asyncio
    async def test_a_failing_connector_does_not_raise(self):
        """This runs on a background cadence. A refresher that can take
        down its caller is worse than a stale price."""
        e = _entry("BTC/USD", last=100.0)
        pool = _pool_with(e)
        assert (
            await pool.refresh_all_tickers(
                _Conn(boom=RuntimeError("exchange down")), "coinbase"
            )
            == 0
        )
        assert e.last == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_a_non_dict_response_does_not_raise(self):
        pool = _pool_with(_entry("BTC/USD", last=100.0))
        assert await pool.refresh_all_tickers(_Conn(payload=[]), "coinbase") == 0


class TestItReplacesTrafficRatherThanAddingIt:
    @pytest.mark.asyncio
    async def test_one_call_covers_every_cached_symbol(self):
        """The whole economic argument. If this ever needed one call per
        symbol the change would cost more than it saves."""
        entries = [_entry(f"C{i}/USD") for i in range(35)]
        pool = _pool_with(*entries)
        conn = _Conn({f"C{i}/USD": _row(last=float(i + 1)) for i in range(35)})
        assert await pool.refresh_all_tickers(conn, "coinbase") == 35
        assert conn.calls == 1

    @pytest.mark.asyncio
    async def test_a_warmed_entry_serves_the_bot_without_fetching(self):
        """The saving is real only if a warmed entry takes the fast path
        in get_or_fetch_ticker. A bot that fetches anyway saves nothing."""
        e = _entry("BTC/USD")
        pool = _pool_with(e)
        await pool.refresh_all_tickers(_Conn({"BTC/USD": _row(last=250.0)}), "coinbase")

        class _MustNotFetch:
            async def get_ticker(self, symbol):
                raise AssertionError("bot fetched despite a freshly warmed cache entry")

        t = await pool.get_or_fetch_ticker(_MustNotFetch(), "coinbase", "BTC/USD")
        assert t.last == pytest.approx(250.0)

    @pytest.mark.asyncio
    async def test_the_batch_is_counted_for_telemetry(self):
        pool = _pool_with(_entry("BTC/USD"), _entry("ETH/USD"))
        await pool.refresh_all_tickers(
            _Conn({"BTC/USD": _row(last=1.0), "ETH/USD": _row(last=2.0)}), "coinbase"
        )
        st = pool.get_status()
        assert st["ticker_batch_refreshes"] == 1
        assert st["ticker_batch_symbols"] == 2
