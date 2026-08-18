"""The fleet-side wiring that actually makes the bulk refresh happen.

`MarketDataPool.refresh_all_tickers` is a primitive; nothing calls it on
its own. These pin the BotManager half: one connector per EXCHANGE (not
per bot), best-effort failure handling, and a refresher that cannot be
started twice or without a loop.

THE ECONOMIC CLAIM UNDER TEST
The saving depends on 35 bots on one exchange producing exactly ONE bulk
call. If `_connectors_by_exchange` ever returned one entry per bot the
change would cost more than the per-bot polling it replaces.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.bot_container import BotManager  # noqa: E402


class _Bot:
    def __init__(self, exchange_id="coinbase", conn=None):
        self.config = type("C", (), {"exchange_id": exchange_id})()
        self.exchange = conn if conn is not None else object()


class _Pool:
    def __init__(self, per_call=3, boom=None):
        self.calls = []
        self._per_call = per_call
        self._boom = boom

    async def refresh_all_tickers(self, connector, exchange_id):
        self.calls.append(exchange_id)
        if self._boom is not None:
            raise self._boom
        return self._per_call


def _mgr(bots, pool=None):
    m = object.__new__(BotManager)
    m._bots = dict(bots)
    m._data_pool = pool
    m._ticker_refresh_task = None
    m._ticker_refresh_stop = False
    m._async_loop = None
    return m


class TestOneCallPerExchange:
    def test_thirty_five_bots_on_one_exchange_yield_one_connector(self):
        """POSITIVE CONTROL for the whole economic argument."""
        m = _mgr({f"b{i}": _Bot() for i in range(35)})
        assert list(m._connectors_by_exchange()) == ["coinbase"]

    def test_distinct_exchanges_each_get_one(self):
        m = _mgr({"a": _Bot("coinbase"), "b": _Bot("kraken"),
                  "c": _Bot("coinbase")})
        assert sorted(m._connectors_by_exchange()) == ["coinbase", "kraken"]

    def test_a_bot_without_a_connector_is_skipped(self):
        bad = _Bot()
        bad.exchange = None
        assert _mgr({"a": bad})._connectors_by_exchange() == {}

    def test_a_malformed_container_does_not_blind_the_fleet(self):
        class _Boom:
            @property
            def config(self):
                raise RuntimeError("container corrupt")

        m = _mgr({"bad": _Boom(), "good": _Bot()})
        assert list(m._connectors_by_exchange()) == ["coinbase"]


class TestRefreshOnce:
    @pytest.mark.asyncio
    async def test_it_refreshes_each_exchange_once(self):
        pool = _Pool(per_call=5)
        m = _mgr({"a": _Bot("coinbase"), "b": _Bot("kraken"),
                  "c": _Bot("coinbase")}, pool)
        assert await m.refresh_all_tickers_once() == 10
        assert sorted(pool.calls) == ["coinbase", "kraken"]

    @pytest.mark.asyncio
    async def test_no_pool_is_a_no_op(self):
        assert await _mgr({"a": _Bot()}, None).refresh_all_tickers_once() == 0

    @pytest.mark.asyncio
    async def test_a_pool_without_the_method_is_a_no_op(self):
        """Guards the promote path: an older pool must not raise."""
        m = _mgr({"a": _Bot()}, object())
        assert await m.refresh_all_tickers_once() == 0

    @pytest.mark.asyncio
    async def test_a_raising_pool_does_not_propagate(self):
        m = _mgr({"a": _Bot()}, _Pool(boom=RuntimeError("exchange down")))
        assert await m.refresh_all_tickers_once() == 0

    @pytest.mark.asyncio
    async def test_one_failing_exchange_does_not_stop_the_other(self):
        class _Selective(_Pool):
            async def refresh_all_tickers(self, connector, exchange_id):
                self.calls.append(exchange_id)
                if exchange_id == "kraken":
                    raise RuntimeError("kraken down")
                return 7

        pool = _Selective()
        m = _mgr({"a": _Bot("kraken"), "b": _Bot("coinbase")}, pool)
        assert await m.refresh_all_tickers_once() == 7
        assert sorted(pool.calls) == ["coinbase", "kraken"]


class TestTheRefresherLifecycle:
    def test_it_refuses_to_start_without_a_loop(self):
        """Must not raise on a headless/test manager."""
        assert _mgr({"a": _Bot()}, _Pool()).start_ticker_refresher() is False

    def test_starting_twice_is_a_no_op(self):
        m = _mgr({"a": _Bot()}, _Pool())
        m._ticker_refresh_task = object()
        assert m.start_ticker_refresher() is False

    def test_stop_is_safe_when_never_started(self):
        m = _mgr({"a": _Bot()}, _Pool())
        m.stop_ticker_refresher()
        assert m._ticker_refresh_stop is True

    def test_stop_cancels_and_clears_the_handle(self):
        m = _mgr({"a": _Bot()}, _Pool())

        class _Task:
            cancelled = False

            def cancel(self):
                self.cancelled = True

        t = _Task()
        m._ticker_refresh_task = t
        m.stop_ticker_refresher()
        assert t.cancelled and m._ticker_refresh_task is None

    @pytest.mark.asyncio
    async def test_the_loop_exits_promptly_when_stopped(self):
        """A refresher that outlives shutdown keeps hitting the API."""
        pool = _Pool()
        m = _mgr({"a": _Bot()}, pool)
        task = asyncio.ensure_future(m._ticker_refresh_loop(0.01))
        await asyncio.sleep(0.05)
        m._ticker_refresh_stop = True
        await asyncio.wait_for(task, timeout=1.0)
        assert pool.calls, "positive control: the loop must have run at all"

    @pytest.mark.asyncio
    async def test_a_failing_cycle_does_not_kill_the_loop(self):
        """One bad cycle must not silently end fleet-wide refreshing."""
        calls = []

        m = _mgr({"a": _Bot()}, _Pool())

        async def _boom():
            calls.append(1)
            raise RuntimeError("transient")

        m.refresh_all_tickers_once = _boom
        task = asyncio.ensure_future(m._ticker_refresh_loop(0.01))
        await asyncio.sleep(0.06)
        m._ticker_refresh_stop = True
        await asyncio.wait_for(task, timeout=1.0)
        assert len(calls) > 1, "loop died after the first failure"
