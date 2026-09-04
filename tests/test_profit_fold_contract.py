"""Behavioural pins for ``apply_profit_fold``.

Each test drives ``apply_profit_fold`` and asserts the returned
``(new_target, spillover)`` pair.
"""

from __future__ import annotations

from src.trading.profit_fold import apply_profit_fold


def test_a_one_percent_cap_grows_target_by_one_percent_and_spills_the_rest():
    new_target, spillover = apply_profit_fold(
        profit=10.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=10000.0,
        cap_pct=1.0,
    )
    assert abs(new_target - 101.0) < 1e-9, f"new_target={new_target}"
    assert abs(spillover - 9.0) < 1e-9, f"spillover={spillover}"


def test_a_hundred_percent_cap_applies_the_whole_profit():
    new_target, spillover = apply_profit_fold(
        profit=10.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=10000.0,
        cap_pct=100.0,
    )
    assert abs(new_target - 110.0) < 1e-9, f"new_target={new_target}"
    assert abs(spillover) < 1e-9, f"spillover={spillover}"


def test_a_profit_under_the_cap_is_applied_whole():
    new_target, spillover = apply_profit_fold(
        profit=0.005,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=10000.0,
        cap_pct=1.0,
    )
    assert abs(new_target - 100.005) < 1e-9, f"new_target={new_target}"
    assert abs(spillover) < 1e-9, f"spillover={spillover}"


def test_an_entry_price_below_the_fill_scales_the_growth_down():
    new_target, spillover = apply_profit_fold(
        profit=10.0,
        price=110.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=10000.0,
        cap_pct=100.0,
    )
    expected = 100.0 + 10.0 * 100.0 / 110.0
    assert abs(new_target - expected) < 1e-6, f"new_target={new_target}"
    assert abs(spillover) < 1e-9, f"spillover={spillover}"


def test_a_zero_entry_price_leaves_the_growth_unscaled():
    new_target, spillover = apply_profit_fold(
        profit=10.0,
        price=100.0,
        target=100.0,
        entry_price=0.0,
        portfolio_value=10000.0,
        cap_pct=100.0,
    )
    assert abs(new_target - 110.0) < 1e-9, f"new_target={new_target}"
    assert abs(spillover) < 1e-9, f"spillover={spillover}"


def test_the_portfolio_ceiling_trims_new_target_to_995_thousandths():
    new_target, spillover = apply_profit_fold(
        profit=20.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=110.0,
        cap_pct=100.0,
    )
    assert abs(new_target - 109.45) < 1e-9, f"new_target={new_target}"
    assert abs(spillover) < 1e-9, f"spillover={spillover}"


def test_the_cap_computes_spillover_before_the_ceiling_trims_applied():
    new_target, spillover = apply_profit_fold(
        profit=1000.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=110.0,
        cap_pct=100.0,
    )
    assert abs(new_target - 109.45) < 1e-9, f"new_target={new_target}"
    assert abs(spillover - 900.0) < 1e-6, f"spillover={spillover}"


def test_a_non_positive_profit_returns_the_target_unchanged():
    new_target, spillover = apply_profit_fold(
        profit=0.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=10000.0,
        cap_pct=1.0,
    )
    assert new_target == 100.0, f"new_target={new_target}"
    assert spillover == 0.0, f"spillover={spillover}"
    grew, _ = apply_profit_fold(
        profit=1.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=10000.0,
        cap_pct=100.0,
    )
    assert grew > 100.0, f"positive control did not grow the target: {grew}"


def test_a_zero_cap_pct_freezes_target():
    new_target, _ = apply_profit_fold(
        profit=1000.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=1e9,
        cap_pct=0.0,
    )
    assert new_target == 100.0, f"a 0% cap must add nothing, got {new_target}"


def test_a_zero_cap_pct_sends_the_whole_profit_to_spillover():
    _, spillover = apply_profit_fold(
        profit=1000.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=1e9,
        cap_pct=0.0,
    )
    assert abs(spillover - 1000.0) < 1e-9, f"spillover={spillover}"


def test_a_sub_cent_price_loses_no_growth_to_an_epsilon():
    new_target, _ = apply_profit_fold(
        profit=10.0,
        price=1e-10,
        target=1_000_000.0,
        entry_price=9e-11,
        portfolio_value=1e9,
        cap_pct=100.0,
    )
    growth = new_target - 1_000_000.0
    assert abs(growth - 9.0) < 1e-6, f"growth={growth}, expected 9.0 from ref/price=0.9"


def test_new_target_never_falls_below_the_input_target():
    new_target, _ = apply_profit_fold(
        profit=1.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=50.0,
        cap_pct=100.0,
    )
    assert new_target == 100.0, f"new_target={new_target}"


def test_the_target_floor_outranks_the_portfolio_ceiling():
    portfolio_value = 100.2
    new_target, _ = apply_profit_fold(
        profit=1.0,
        price=100.0,
        target=100.0,
        entry_price=100.0,
        portfolio_value=portfolio_value,
        cap_pct=100.0,
    )
    ceiling = portfolio_value * 0.995
    assert new_target > ceiling, f"new_target={new_target}, ceiling={ceiling}"
    assert new_target == 100.0, f"new_target={new_target}"
