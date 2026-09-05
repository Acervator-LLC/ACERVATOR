"""Contract tests for the surrounding-topology helpers in triangular_swarm."""

from __future__ import annotations

import random

from src.trading.triangular_swarm import (
    TriadSpawner,
    generate_surrounding_prices,
    run_equity_surrounding_swarm,
    run_surrounding_swarm,
    score_triad,
)

FLAT = [100.0] * 5
CANDLES = [100.0 + (i % 7) - 3 for i in range(60)]
EQUITY_CANDLES = {
    "SPY": [400.0 + (i % 5) for i in range(60)],
    "GLD": [180.0 - (i % 3) for i in range(60)],
    "TLT": [90.0 + (i % 4) for i in range(60)],
}


def _global_stream(action) -> tuple[list[float], list[float]]:
    """Return the next three global draws with and without ``action`` run first."""
    random.seed(12345)
    untouched = [random.random() for _ in range(3)]
    random.seed(12345)
    action()
    touched = [random.random() for _ in range(3)]
    return untouched, touched


def test_the_global_stream_probe_sees_a_reseed() -> None:
    """Fails when the instrument the RNG-isolation tests use cannot see a reseed."""
    untouched, touched = _global_stream(lambda: random.seed(7))
    assert untouched != touched, (
        "the probe reported no change after random.seed(7), so it cannot "
        f"detect a reseed: {untouched} vs {touched}"
    )


def test_generate_surrounding_prices_leaves_the_global_random_stream_alone() -> None:
    """Fails when generate_surrounding_prices reseeds the process-wide random module."""
    untouched, touched = _global_stream(
        lambda: generate_surrounding_prices(
            CANDLES, {"USD": 0.0, "ETH": 0.005}, seed=42
        )
    )
    assert untouched == touched, (
        "generate_surrounding_prices moved the global random stream: "
        f"{untouched} vs {touched}"
    )


def test_run_surrounding_swarm_leaves_the_global_random_stream_alone() -> None:
    """Fails when run_surrounding_swarm reseeds the process-wide random module."""
    untouched, touched = _global_stream(
        lambda: run_surrounding_swarm("BTC", CANDLES, n_arms=2, verbose=False)
    )
    assert (
        untouched == touched
    ), f"run_surrounding_swarm moved the global random stream: {untouched} vs {touched}"


def test_run_equity_surrounding_swarm_leaves_the_global_random_stream_alone() -> None:
    """Fails when run_equity_surrounding_swarm reseeds the process-wide random module."""
    untouched, touched = _global_stream(
        lambda: run_equity_surrounding_swarm("MACRO", EQUITY_CANDLES, verbose=False)
    )
    assert untouched == touched, (
        "run_equity_surrounding_swarm moved the global random stream: "
        f"{untouched} vs {touched}"
    )


def test_generate_surrounding_prices_repeats_for_one_seed_and_moves_for_another() -> (
    None
):
    """Fails when the seed stops deciding the synthetic crypto quote series."""
    vols = {"USD": 0.0, "ETH": 0.005}
    first = generate_surrounding_prices(CANDLES, vols, seed=42)
    again = generate_surrounding_prices(CANDLES, vols, seed=42)
    other = generate_surrounding_prices(CANDLES, vols, seed=43)
    assert first["ETH"], "no ETH series was generated, so the comparison proves nothing"
    assert first["ETH"] == again["ETH"], "seed 42 gave two different ETH series"
    assert first["ETH"] != other["ETH"], "seeds 42 and 43 gave the same ETH series"


def test_a_zero_volatility_quote_tracks_the_base_exactly() -> None:
    """Fails when a quote pegged at volatility 0 stops reproducing base_closes."""
    out = generate_surrounding_prices(CANDLES, {"USD": 0.0}, seed=42)
    assert (
        out["USD"] == CANDLES
    ), f"USD series departed from base_closes: {out['USD'][:5]}"


def test_the_third_arm_is_the_cross_that_closes_the_loop() -> None:
    """Fails when generate_all_triads emits quote_a/quote_b instead of quote_b/quote_a."""
    triads = TriadSpawner(base="AVAX", exchange="COINBASE").generate_all_triads()
    assert triads, "no triads were generated, so the comparison proves nothing"
    for arm_a, arm_b, arm_c in triads:
        quote_a = arm_a.split("/")[1]
        quote_b = arm_b.split("/")[1]
        assert arm_c == f"{quote_b}/{quote_a}", (
            f"triad ({arm_a}, {arm_b}, {arm_c}) does not close: score_triad needs "
            f"the cross {quote_b}/{quote_a} so that arm_a == arm_b * arm_c"
        )


def test_the_avax_triads_name_the_cross_in_the_order_score_triad_reads() -> None:
    """Fails when the AVAX cross pairs come back inverted."""
    triads = TriadSpawner(base="AVAX", exchange="COINBASE").generate_all_triads()
    crosses = [c for _a, _b, c in triads]
    assert crosses == [
        "USDC/USD",
        "EUR/USD",
        "EUR/USDC",
    ], f"unexpected cross pairs for AVAX on COINBASE: {crosses}"


def test_a_short_series_still_answers_with_arm_scores() -> None:
    """Fails when score_triad's short-series answer omits a key rank_triads reads."""
    answer = score_triad(FLAT, FLAT, FLAT)
    full = score_triad(CANDLES, CANDLES, CANDLES)
    assert set(answer) == set(
        full
    ), f"short-series keys {sorted(answer)} differ from full-series keys {sorted(full)}"
    assert answer["arm_scores"] == {"a": 0.0, "b": 0.0, "c": 0.0}


def test_rank_triads_answers_when_a_cross_series_is_too_short() -> None:
    """Fails when a short cross series makes rank_triads raise instead of scoring 0."""
    spawner = TriadSpawner(base="AVAX", exchange="COINBASE")
    arm_a, arm_b, arm_c = spawner.generate_all_triads()[0]
    price_data = {arm_a: CANDLES, arm_b: CANDLES, arm_c: FLAT}
    scored = spawner.rank_triads(price_data)
    assert scored, "rank_triads returned nothing, so the comparison proves nothing"
    short = [row for row in scored if row["arm_c"] == arm_c]
    assert short, f"{arm_c} was dropped from {[r['arm_c'] for r in scored]}"
    assert short[0]["score"] == 0.0
    assert short[0]["arm_scores"] == {"a": 0.0, "b": 0.0, "c": 0.0}
