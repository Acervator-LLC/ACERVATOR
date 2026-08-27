"""v3.23.47 — MarketPairsScout pin tests.

Locks the read-only cross-pair awareness surface introduced in the
multi-base coordination cascade
(docs/engineering-notes/2026-07-28_multibase_coordination_and_cross_pair_intelligence_plan.md
§ 6, cascade #2). This module does NOT rank or route — the tests
enforce that discipline by exercising the public API and asserting
what it does and does not expose.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.market_pairs_scout import (  # noqa: E402
    DEFAULT_REFRESH_SECONDS,
    MarketPairsScout,
    PairSnapshot,
    get_scout,
    reset_scout_for_tests,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# Representative Coinbase-shaped fetch_tickers payload — three ETH
# pairs (against USD, USDC, BTC), one BTC/USD, one XRP/USDC.
def _sample_tickers():
    return {
        "ETH/USD": {
            "last": 3000.0,
            "bid": 2999.5,
            "ask": 3000.5,
            "percentage": 1.2,
            "baseVolume": 12500.0,
        },
        "ETH/USDC": {
            "last": 3001.0,
            "bid": 3000.9,
            "ask": 3001.1,
            "percentage": 1.3,
            "baseVolume": 8000.0,
        },
        "ETH/BTC": {
            "last": 0.06,
            "bid": 0.0599,
            "ask": 0.0601,
            "percentage": 0.4,
            "baseVolume": 500.0,
        },
        "BTC/USD": {
            "last": 50000.0,
            "bid": 49995.0,
            "ask": 50005.0,
            "percentage": 0.8,
            "baseVolume": 1200.0,
        },
        "XRP/USDC": {
            "last": 0.55,
            "bid": 0.549,
            "ask": 0.551,
            "percentage": -2.1,
            "baseVolume": 400000.0,
        },
    }


# -----------------------------------------------------------------
# ingest_tickers
# -----------------------------------------------------------------


class TestIngest:
    def test_records_pair_count(self):
        s = MarketPairsScout()
        n = s.ingest_tickers("coinbase", _sample_tickers())
        assert n == 5

    def test_skips_malformed_rows(self):
        s = MarketPairsScout()
        bad = {
            "ETH/USD": _sample_tickers()["ETH/USD"],
            "MALFORMED-NO-SLASH": {"last": 1.0},
            "": {"last": 2.0},
        }
        n = s.ingest_tickers("coinbase", bad)
        assert n == 1
        pairs = s.pairs_for("ETH")
        assert len(pairs) == 1
        assert pairs[0].symbol == "ETH/USD"

    def test_last_refresh_timestamp_set(self):
        s = MarketPairsScout()
        s.ingest_tickers("coinbase", _sample_tickers(), now=1_700_000_000.0)
        assert s.last_refresh("coinbase") == pytest.approx(1_700_000_000.0)

    def test_last_error_cleared_on_success(self):
        s = MarketPairsScout()
        s._last_error["coinbase"] = "old failure"
        s.ingest_tickers("coinbase", _sample_tickers())
        assert s.last_error("coinbase") is None

    def test_close_used_when_last_missing(self):
        s = MarketPairsScout()
        s.ingest_tickers(
            "coinbase", {"BONK/USD": {"close": 0.000012, "percentage": 5.0}}
        )
        pair = s.get_pair("BONK", "USD")
        assert pair is not None
        assert pair.last == pytest.approx(0.000012)


# -----------------------------------------------------------------
# pairs_for / quote_currencies_for / get_pair / has_pair
# -----------------------------------------------------------------


class TestQueryAPI:
    def _seeded(self):
        s = MarketPairsScout()
        s.ingest_tickers("coinbase", _sample_tickers())
        return s

    def test_pairs_for_returns_three_eth_pairs(self):
        s = self._seeded()
        pairs = s.pairs_for("ETH")
        assert [p.symbol for p in pairs] == ["ETH/BTC", "ETH/USD", "ETH/USDC"]

    def test_pairs_for_case_insensitive(self):
        s = self._seeded()
        assert len(s.pairs_for("eth")) == 3

    def test_pairs_for_unknown_asset_empty(self):
        s = self._seeded()
        assert s.pairs_for("DOGE") == []

    def test_quote_currencies_for_deduped_sorted(self):
        s = self._seeded()
        assert s.quote_currencies_for("ETH") == ["BTC", "USD", "USDC"]

    def test_has_pair(self):
        s = self._seeded()
        assert s.has_pair("ETH", "BTC")
        assert s.has_pair("ETH", "USD")
        assert not s.has_pair("ETH", "DOGE")

    def test_get_pair_returns_snapshot(self):
        s = self._seeded()
        p = s.get_pair("ETH", "BTC")
        assert p is not None
        assert p.last == pytest.approx(0.06)
        assert p.pct_24h == pytest.approx(0.4)

    def test_scout_does_not_rank(self):
        """Discipline: the scout MUST NOT expose a `best_pair` or
        `rank_by_*` method. Adding one shifts responsibility from a
        future routing layer into the awareness layer, contra the
        prior-art research (§3, DEX-pathfinder category error)."""
        s = MarketPairsScout()
        forbidden = ("best_pair", "rank", "rank_by", "recommend", "route_to")
        for name in forbidden:
            assert not hasattr(s, name), (
                f"MarketPairsScout should not expose {name!r} — "
                "ranking / routing belongs to a later cascade"
            )


# -----------------------------------------------------------------
# PairSnapshot properties + usd_per_base helper
# -----------------------------------------------------------------


class TestPairSnapshot:
    def _mk(self, **kw):
        base = dict(
            symbol="ETH/BTC", base="ETH", quote="BTC", last=0.06, bid=0.0599, ask=0.0601
        )
        base.update(kw)
        return PairSnapshot(**base)

    def test_spread(self):
        assert self._mk().spread == pytest.approx(0.0002)

    def test_spread_pct(self):
        # (0.0601 - 0.0599) / 0.06 × 100 ≈ 0.3333
        assert self._mk().spread_pct == pytest.approx(0.3333, rel=1e-3)

    def test_spread_zero_when_bid_missing(self):
        assert self._mk(bid=0.0).spread == 0.0
        assert self._mk(bid=0.0).spread_pct == 0.0

    def test_usd_per_base_usd_quote(self):
        p = self._mk(symbol="ETH/USD", quote="USD", last=3000.0)
        assert p.usd_per_base(btc_usd=50_000, eth_usd=3000) == 3000.0

    def test_usd_per_base_usdc_treated_as_usd(self):
        p = self._mk(symbol="ETH/USDC", quote="USDC", last=3001.0)
        assert p.usd_per_base(btc_usd=50_000, eth_usd=3000) == 3001.0

    def test_usd_per_base_btc_quote(self):
        p = self._mk(quote="BTC", last=0.06)
        # 0.06 × 50_000 = 3_000
        assert p.usd_per_base(btc_usd=50_000, eth_usd=3000) == 3_000.0

    def test_usd_per_base_eth_quote(self):
        p = self._mk(quote="ETH", last=0.02)
        # 0.02 × 3000 = 60
        assert p.usd_per_base(btc_usd=50_000, eth_usd=3000) == 60.0

    def test_usd_per_base_unknown_quote_returns_zero(self):
        p = self._mk(quote="DOGE", last=1.0)
        assert p.usd_per_base(btc_usd=50_000, eth_usd=3000) == 0.0

    def test_usd_per_base_zero_reference_returns_zero(self):
        p = self._mk(quote="BTC", last=0.06)
        assert p.usd_per_base(btc_usd=0, eth_usd=3000) == 0.0


# -----------------------------------------------------------------
# refresh_from_connectors
# -----------------------------------------------------------------


class _StubConn:
    def __init__(self, tickers, raises=None):
        self._tickers = tickers
        self._raises = raises

    async def get_all_tickers(self):
        if self._raises:
            raise self._raises
        return self._tickers


class TestRefresh:
    def test_refresh_populates(self):
        s = MarketPairsScout()
        result = _run(
            s.refresh_from_connectors({"coinbase": _StubConn(_sample_tickers())})
        )
        assert result == {"coinbase": 5}
        assert len(s.pairs_for("ETH")) == 3

    def test_refresh_skips_when_fresh(self):
        s = MarketPairsScout(refresh_seconds=100.0)
        _run(s.refresh_from_connectors({"coinbase": _StubConn(_sample_tickers())}))
        # Second call: connector's get_all_tickers should NOT be
        # invoked because is_stale() returns False.
        called = {"n": 0}

        class _CountConn:
            async def get_all_tickers(self):
                called["n"] += 1
                return _sample_tickers()

        _run(s.refresh_from_connectors({"coinbase": _CountConn()}))
        assert called["n"] == 0

    def test_refresh_force_bypasses_freshness(self):
        s = MarketPairsScout(refresh_seconds=100.0)
        _run(s.refresh_from_connectors({"coinbase": _StubConn(_sample_tickers())}))
        called = {"n": 0}

        class _CountConn:
            async def get_all_tickers(self):
                called["n"] += 1
                return _sample_tickers()

        _run(s.refresh_from_connectors({"coinbase": _CountConn()}, force=True))
        assert called["n"] == 1

    def test_failed_connector_retains_last_snapshot(self):
        s = MarketPairsScout()
        _run(s.refresh_from_connectors({"coinbase": _StubConn(_sample_tickers())}))
        first_count = len(s.pairs_for("ETH"))

        # Simulate a network error on the second refresh.
        _run(
            s.refresh_from_connectors(
                {"coinbase": _StubConn(None, raises=RuntimeError("net"))}, force=True
            )
        )
        # Previous snapshot should still be there
        assert len(s.pairs_for("ETH")) == first_count
        assert "RuntimeError" in (s.last_error("coinbase") or "")

    def test_empty_connectors_returns_empty(self):
        s = MarketPairsScout()
        assert _run(s.refresh_from_connectors({})) == {}


# -----------------------------------------------------------------
# Module singleton
# -----------------------------------------------------------------


class TestSingleton:
    def teardown_method(self):
        reset_scout_for_tests()

    def test_get_scout_returns_same_instance(self):
        s1 = get_scout()
        s2 = get_scout()
        assert s1 is s2

    def test_reset_gives_new_instance(self):
        s1 = get_scout()
        reset_scout_for_tests()
        s2 = get_scout()
        assert s1 is not s2

    def test_default_refresh_seconds_matches_research(self):
        """Prior-art research § 6.2 recommended 10 s default."""
        assert DEFAULT_REFRESH_SECONDS == 10.0


# -----------------------------------------------------------------
# ScrummingBot wiring
# -----------------------------------------------------------------


class TestScrummingBotWiring:
    """v3.23.47 — ScrummingBot exposes the read-only scout surface
    but never mutates through it. These pins hold that discipline
    plus the ergonomic ``get_target_asset_pairs`` helper."""

    def _mk_stub_bot(self, target_asset="ETH", exchange_id="coinbase"):
        from src.trading.scrumming_bot import ScrummingBot
        from types import MethodType, SimpleNamespace

        stub = SimpleNamespace()
        stub.bot_id = "bot-scout01"
        stub.config = SimpleNamespace(
            target_asset=target_asset, exchange_id=exchange_id
        )
        stub.set_market_pairs_scout = MethodType(
            ScrummingBot.set_market_pairs_scout, stub
        )
        stub.get_target_asset_pairs = MethodType(
            ScrummingBot.get_target_asset_pairs, stub
        )
        return stub

    def test_no_scout_attached_returns_empty(self):
        stub = self._mk_stub_bot()
        assert stub.get_target_asset_pairs() == []

    def test_attached_scout_returns_target_asset_pairs(self):
        stub = self._mk_stub_bot(target_asset="ETH")
        scout = MarketPairsScout()
        scout.ingest_tickers("coinbase", _sample_tickers())
        stub.set_market_pairs_scout(scout)
        pairs = stub.get_target_asset_pairs()
        assert [p.symbol for p in pairs] == ["ETH/BTC", "ETH/USD", "ETH/USDC"]

    def test_attached_scout_filters_by_exchange(self):
        """Bot on 'coinbase' must not see pairs the scout observed on
        a hypothetical other exchange for the same asset."""
        stub = self._mk_stub_bot(target_asset="ETH", exchange_id="coinbase")
        scout = MarketPairsScout()
        scout.ingest_tickers("coinbase", {"ETH/USD": _sample_tickers()["ETH/USD"]})
        scout.ingest_tickers("kraken", {"ETH/EUR": {"last": 2800.0, "percentage": 0.5}})
        stub.set_market_pairs_scout(scout)
        pairs = stub.get_target_asset_pairs()
        assert [p.symbol for p in pairs] == ["ETH/USD"]

    def test_no_target_asset_returns_empty(self):
        stub = self._mk_stub_bot(target_asset="")
        scout = MarketPairsScout()
        scout.ingest_tickers("coinbase", _sample_tickers())
        stub.set_market_pairs_scout(scout)
        assert stub.get_target_asset_pairs() == []

    def test_scout_query_error_swallowed(self):
        stub = self._mk_stub_bot()

        class _BrokenScout:
            def pairs_for(self, *_a, **_kw):
                raise RuntimeError("scout down")

        stub.set_market_pairs_scout(_BrokenScout())
        # Must not raise — best-effort read
        assert stub.get_target_asset_pairs() == []
