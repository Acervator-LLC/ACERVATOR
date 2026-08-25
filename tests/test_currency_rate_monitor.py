"""v3.23.41 — CurrencyRateMonitor pin tests.

Covers derived-rate math (satoshi + wei), snapshot lifecycle, staleness,
and the manual update entry point. Async connector refresh is exercised
with a stub connector.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.currency_rate_monitor import (  # noqa: E402
    CurrencyRateMonitor,
    CurrencyRates,
    SATOSHI_PER_BTC,
    WEI_PER_ETH,
    get_currency_monitor,
)


@dataclass
class _StubTicker:
    last: float


class _StubConnector:
    def __init__(self, prices: dict):
        self._prices = prices

    async def get_ticker(self, symbol: str):
        if symbol not in self._prices:
            raise RuntimeError(f"unknown symbol {symbol}")
        return _StubTicker(self._prices[symbol])


class TestConstants:
    def test_satoshi_per_btc(self):
        assert SATOSHI_PER_BTC == 100_000_000

    def test_wei_per_eth(self):
        assert WEI_PER_ETH == 10**18


class TestDerivedRates:
    def test_btc_100k_yields_1000_sat_per_dollar(self):
        mon = CurrencyRateMonitor()
        s = mon.update_from_prices(btc_usd=100_000.0, eth_usd=4_000.0)
        assert s.sat_per_dollar == pytest.approx(1_000.0)
        # 1 cent → 10 sat
        assert s.sat_per_cent == pytest.approx(10.0)

    def test_btc_50k_yields_2000_sat_per_dollar(self):
        mon = CurrencyRateMonitor()
        s = mon.update_from_prices(btc_usd=50_000.0, eth_usd=3_000.0)
        assert s.sat_per_dollar == pytest.approx(2_000.0)
        assert s.sat_per_cent == pytest.approx(20.0)

    def test_eth_4k_yields_2_5e14_wei_per_dollar(self):
        mon = CurrencyRateMonitor()
        s = mon.update_from_prices(btc_usd=100_000.0, eth_usd=4_000.0)
        # 1e18 / 4e3 = 2.5e14
        assert s.wei_per_dollar == pytest.approx(2.5e14)
        assert s.wei_per_cent == pytest.approx(2.5e12)

    def test_zero_price_yields_zero_derived(self):
        mon = CurrencyRateMonitor()
        s = mon.update_from_prices(btc_usd=0.0, eth_usd=0.0)
        assert s.sat_per_dollar == 0.0
        assert s.wei_per_dollar == 0.0


class TestSnapshotLifecycle:
    def test_initial_snapshot_is_empty(self):
        mon = CurrencyRateMonitor()
        s = mon.snapshot()
        assert s.btc_usd == 0.0
        assert s.eth_usd == 0.0
        assert s.last_updated == 0.0
        assert s.source == "none"
        assert s.has_btc() is False
        assert s.has_eth() is False

    def test_update_marks_ready(self):
        mon = CurrencyRateMonitor()
        mon.update_from_prices(1.0, 1.0, source="test", now=1000.0)
        s = mon.snapshot()
        assert s.has_btc() is True
        assert s.has_eth() is True
        assert s.source == "test"
        assert s.last_updated == 1000.0

    def test_is_stale_before_first_update(self):
        mon = CurrencyRateMonitor(refresh_seconds=60)
        assert mon.is_stale() is True

    def test_fresh_snapshot_not_stale(self):
        mon = CurrencyRateMonitor(refresh_seconds=60)
        mon.update_from_prices(50000, 4000, now=10_000.0)
        # 30 s after update, tolerance 2× → 120 s window
        assert mon.is_stale(now=10_030.0) is False

    def test_old_snapshot_is_stale(self):
        mon = CurrencyRateMonitor(refresh_seconds=60)
        mon.update_from_prices(50000, 4000, now=10_000.0)
        # 200 s after update → stale
        assert mon.is_stale(now=10_200.0) is True


class TestConnectorRefresh:
    def _run(self, coro):
        return (
            asyncio.get_event_loop().run_until_complete(coro)
            if False
            else asyncio.run(coro)
        )

    def test_refresh_no_connectors_records_error(self):
        mon = CurrencyRateMonitor()
        r = self._run(mon.refresh_from_connectors({}))
        assert r.error and "no exchange connectors" in r.error

    def test_refresh_pulls_first_working_connector(self):
        mon = CurrencyRateMonitor(refresh_seconds=1)
        conn = _StubConnector({"BTC/USD": 60_000.0, "ETH/USD": 3_500.0})
        r = self._run(mon.refresh_from_connectors({"coinbase": conn}))
        assert r.btc_usd == 60_000.0
        assert r.eth_usd == 3_500.0
        assert r.source == "coinbase"
        # sat_per_dollar = 1e8 / 60_000 ≈ 1666.67
        assert r.sat_per_dollar == pytest.approx(1_666.6666667, rel=1e-4)

    def test_refresh_skips_when_fresh_unless_forced(self):
        mon = CurrencyRateMonitor(refresh_seconds=60)
        mon.update_from_prices(1.0, 1.0, source="pre")
        conn = _StubConnector({"BTC/USD": 999, "ETH/USD": 999})
        # Fresh — refresh short-circuits.
        r = self._run(mon.refresh_from_connectors({"cb": conn}))
        assert r.source == "pre"
        # Force — actually polls.
        r2 = self._run(mon.refresh_from_connectors({"cb": conn}, force=True))
        assert r2.source == "cb"
        assert r2.btc_usd == 999

    def test_refresh_reports_error_when_all_connectors_fail(self):
        mon = CurrencyRateMonitor(refresh_seconds=1)

        class _BrokenConnector:
            async def get_ticker(self, sym):
                raise RuntimeError("network down")

        r = self._run(mon.refresh_from_connectors({"x": _BrokenConnector()}))
        assert r.error and "network down" in r.error
        assert r.btc_usd == 0.0


class TestSharedMonitor:
    def test_shared_singleton(self):
        a = get_currency_monitor()
        b = get_currency_monitor()
        assert a is b
        assert isinstance(a, CurrencyRateMonitor)
