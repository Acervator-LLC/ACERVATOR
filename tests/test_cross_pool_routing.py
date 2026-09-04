"""Behaviour of ``route_to_best_pool`` and the ``CrossPoolCycleResult`` it feeds."""

from __future__ import annotations

import math

from src.trading.cross_pool import PoolQuote, route_to_best_pool, run_cross_pool_sim


def _slow_wave(n: int = 600, amp: float = 0.05, period: int = 240) -> list[float]:
    """Return a series whose candle-to-candle move stays under ``max_spread``.

    A larger move clamps every pool of ``CrossPoolSpreadModel`` to one band edge
    and ``route_to_best_pool`` then sees a single price.
    """
    return [100.0 * (1.0 + amp * math.sin(2 * math.pi * i / period)) for i in range(n)]


def test_a_cycle_records_the_pool_the_harvest_filled_on() -> None:
    cycles = run_cross_pool_sim(_slow_wave(), n_pools=3, seed=7)["cycle_results"]
    assert cycles, "no fold completed, so no cycle was recorded"

    same = [c for c in cycles if c.harvest_pool == c.fold_pool]
    assert (
        not same
    ), "harvest_pool repeats fold_pool, so it carries the fold routing: " + repr(
        [(c.harvest_pool, c.fold_pool) for c in cycles]
    )


def test_a_cycle_names_a_pool_that_quoted_that_candle() -> None:
    cycles = run_cross_pool_sim(_slow_wave(), n_pools=3, seed=7)["cycle_results"]
    assert cycles, "no fold completed, so no cycle was recorded"
    valid = {"pool_1", "pool_2", "pool_3"}
    for c in cycles:
        assert c.harvest_pool in valid, f"harvest_pool={c.harvest_pool!r}"
        assert c.fold_pool in valid, f"fold_pool={c.fold_pool!r}"


def test_a_wide_spread_with_no_fee_is_profitable() -> None:
    quotes = [
        PoolQuote("pool_1", 100.0, bid=100.0, ask=100.01, fee_pct=0.0),
        PoolQuote("pool_2", 90.0, bid=90.0, ask=90.01, fee_pct=0.0),
    ]
    decision = route_to_best_pool(quotes, "harvest")
    assert decision.best_pool == "pool_1"
    assert decision.is_profitable is True, f"net_advantage={decision.net_advantage}"


def test_a_fee_larger_than_the_spread_is_not_profitable() -> None:
    quotes = [
        PoolQuote("pool_1", 100.0, bid=100.0, ask=100.01, fee_pct=0.05),
        PoolQuote("pool_2", 99.99, bid=99.99, ask=100.0, fee_pct=0.05),
    ]
    decision = route_to_best_pool(quotes, "harvest")
    assert decision.is_profitable is False, f"net_advantage={decision.net_advantage}"


def test_net_advantage_subtracts_each_pools_own_fee() -> None:
    quotes = [
        PoolQuote("pool_1", 100.0, bid=100.0, ask=100.0, fee_pct=0.002),
        PoolQuote("pool_2", 99.0, bid=99.0, ask=99.0, fee_pct=0.008),
    ]
    decision = route_to_best_pool(quotes, "harvest")
    expected = round(decision.spread_pct - (0.002 + 0.008) * 100, 5)
    assert decision.net_advantage == expected, (
        f"net_advantage={decision.net_advantage} is not spread_pct minus both "
        f"fees; twice the best fee would give "
        f"{round(decision.spread_pct - 2 * 0.002 * 100, 5)}"
    )
