"""v3.24.20 — pin tests for the sim exchange open-order index.

THE DEFECT
==========
``_sweep_open_limit_orders`` walked ``list(self._orders.values())`` on
every candle step. ``self._orders`` never shrinks — filled and cancelled
orders stay in it to serve ``get_order`` / ``get_my_trades`` — so the
sweep cost grew with every trade ever placed. Over a run that is
quadratic in trade count, plus a full list copy per step.

THE RISK THE FIX INTRODUCES
===========================
An index is only as good as its invalidation. If an order is left in
``_open_by_symbol`` after it fills, the next sweep re-settles it and the
balance moves twice — a silent accounting corruption far worse than the
performance problem being solved. The index-integrity tests below are the
ones that matter; the performance test is secondary.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.base import OrderSide, OrderStatus, OrderType  # noqa: E402
from src.gui.simulator_tab.fleet.sim_exchange import (  # noqa: E402
    FleetSimExchange, make_symbol_series_map,
)

_TS = 1_774_915_200_000


def _rows(n, lo=90.0, hi=110.0, close=100.0):
    return [[_TS + i * 300_000, 100.0, hi, lo, close, 10.0]
            for i in range(n)]


def _ex(balances=None):
    series = make_symbol_series_map({
        "BTC/USD": _rows(50),
        "ETH/USD": _rows(50),
    })
    return FleetSimExchange(
        series_map=series,
        starting_balances=balances or {"USD": 1_000_000.0,
                                       "BTC": 100.0, "ETH": 100.0})


def _open_ids(ex):
    return {i for s in ex._open_by_symbol.values() for i in s}


# ── index integrity ──────────────────────────────────────────────

def test_unfillable_limit_order_is_indexed_open():
    ex = _ex()

    async def go():
        # BUY far below the candle low -> stays OPEN
        return await ex.place_order(
            "BTC/USD", OrderSide.BUY, OrderType.LIMIT, 1.0, price=1.0)

    o = asyncio.run(go())
    assert o.status == OrderStatus.OPEN
    assert o.id in ex._open_by_symbol["BTC/USD"]


def test_filled_order_leaves_the_index():
    """A stale id here would re-settle the fill and move balances twice."""
    ex = _ex()

    async def go():
        # BUY above the candle low -> fills immediately
        return await ex.place_order(
            "BTC/USD", OrderSide.BUY, OrderType.LIMIT, 1.0, price=105.0)

    o = asyncio.run(go())
    assert o.status == OrderStatus.FILLED
    assert o.id not in _open_ids(ex)


def test_cancelled_order_leaves_the_index():
    ex = _ex()

    async def go():
        o = await ex.place_order(
            "BTC/USD", OrderSide.BUY, OrderType.LIMIT, 1.0, price=1.0)
        await ex.cancel_order(o.id, "BTC/USD")
        return o

    o = asyncio.run(go())
    assert o.status == OrderStatus.CANCELLED
    assert o.id not in _open_ids(ex)


def test_swept_fill_leaves_the_index_and_does_not_refill():
    """The regression that matters: sweep a resting order into a fill,
    then keep stepping. The balance must move exactly once."""
    ex = _ex()

    async def go():
        o = await ex.place_order(
            "BTC/USD", OrderSide.SELL, OrderType.LIMIT, 1.0, price=105.0)
        return o

    o = asyncio.run(go())
    if o.status == OrderStatus.OPEN:
        ex._sweep_open_limit_orders()
    assert o.status == OrderStatus.FILLED
    usd_after_fill = ex._balances["USD"]
    for _ in range(25):
        ex._sweep_open_limit_orders()
    assert ex._balances["USD"] == usd_after_fill, \
        "order re-settled by a later sweep — stale index entry"


def test_index_matches_get_open_orders():
    """The index and the authoritative scan must never disagree."""
    ex = _ex()

    async def go():
        await ex.place_order("BTC/USD", OrderSide.BUY,
                             OrderType.LIMIT, 1.0, price=1.0)
        await ex.place_order("ETH/USD", OrderSide.BUY,
                             OrderType.LIMIT, 1.0, price=1.0)
        c = await ex.place_order("BTC/USD", OrderSide.BUY,
                                 OrderType.LIMIT, 1.0, price=2.0)
        await ex.cancel_order(c.id, "BTC/USD")
        return await ex.get_open_orders()

    scanned = {o.id for o in asyncio.run(go())}
    assert scanned == _open_ids(ex)


def test_symbol_bucket_is_removed_when_emptied():
    """Otherwise _open_by_symbol grows one empty set per symbol
    forever — the same unbounded-growth shape being fixed."""
    ex = _ex()

    async def go():
        o = await ex.place_order("BTC/USD", OrderSide.BUY,
                                 OrderType.LIMIT, 1.0, price=1.0)
        await ex.cancel_order(o.id, "BTC/USD")

    asyncio.run(go())
    assert "BTC/USD" not in ex._open_by_symbol


def test_only_symbol_sweep_ignores_other_symbols():
    ex = _ex()

    async def go():
        return await ex.place_order(
            "ETH/USD", OrderSide.SELL, OrderType.LIMIT, 1.0, price=105.0)

    o = asyncio.run(go())
    if o.status == OrderStatus.OPEN:
        ex._sweep_open_limit_orders(only_symbol="BTC/USD")
        assert o.status == OrderStatus.OPEN, "swept the wrong symbol"
        ex._sweep_open_limit_orders(only_symbol="ETH/USD")
    assert o.status == OrderStatus.FILLED


def test_sweep_on_unknown_symbol_is_safe():
    ex = _ex()
    assert ex._sweep_open_limit_orders(only_symbol="NOPE/USD") == 0


# ── the complexity claim ─────────────────────────────────────────

def test_sweep_cost_is_independent_of_closed_order_count():
    """The actual fix. Fill 300 orders, then assert a sweep still only
    considers the handful still open."""
    ex = _ex()

    async def go():
        for _ in range(300):     # all fill immediately
            await ex.place_order("BTC/USD", OrderSide.SELL,
                                 OrderType.LIMIT, 0.01, price=95.0)
        await ex.place_order("BTC/USD", OrderSide.BUY,
                             OrderType.LIMIT, 0.01, price=1.0)

    asyncio.run(go())
    assert len(ex._orders) >= 300, "closed orders should be retained"
    assert len(_open_ids(ex)) == 1, \
        "only the unfillable order should remain indexed"

    seen = 0
    real_get = ex._series.get

    def counting_get(sym):
        nonlocal seen
        seen += 1
        return real_get(sym)

    ex._series = type("D", (), {"get": staticmethod(counting_get)})()
    ex._sweep_open_limit_orders()
    assert seen <= 2, (
        f"sweep inspected {seen} orders with 300 closed on the books; "
        "cost is still proportional to total orders")
