"""Blocker messages must state the comparison the gate actually made.

``ADXTrendSuppressionGate.evaluate`` blocks on ``adx >= adx_threshold``, so its
``GateResult.blocker_message`` may never print a bare ``>`` or round the
threshold away.
"""

import pytest

from src.trading.gate_chain import ADXTrendSuppressionGate, GateContext


def _ctx(adx: float) -> GateContext:
    return GateContext(
        symbol="BTC/USD",
        ticker_last=100.0,
        bb_pos=0.5,
        bb_upper_dt=0.875,
        bb_lower_dt=0.125,
        delta=10.0,
        delta_pct=5.0,
        below_interval=False,
        is_bullish=True,
        is_bearish=False,
        trend_hold=False,
        trend_strength=0.0,
        eff_direction_name="BULLISH",
        eff_is_bullish=True,
        eff_is_bearish=False,
        eff_trend_hold=False,
        eff_htf_blocks_scrum=False,
        eff_htf_blocks_fold=False,
        flag_require_ta_bullish=True,
        flag_hold_in_uptrend=True,
        flag_defer_to_htf=True,
        flag_fold_require_ta_bearish=True,
        flag_fold_defer_to_htf=True,
        bb_above_upper_dt=True,
        bb_below_lower_dt=False,
        scrum_ok=True,
        fold_ok_midline=False,
        target_fires=True,
        cb_blocks_scrum=False,
        cb_blocks_fold=False,
        hyst_ok_scrum_side=True,
        hyst_ok_fold_side=True,
        hyst_armed_scrum_side=False,
        hyst_armed_fold_side=False,
        hyst_ref_scrum_side=0.0,
        hyst_ref_fold_side=0.0,
        mem253_at_ceiling=False,
        mem253_smart_ceiling_usd=0.0,
        mem253_current_pos=0.0,
        has_fold_tranches=False,
        n_fold_tranches=0,
        htf_bias_name=None,
        htf_blocks_scrum=False,
        htf_blocks_fold=False,
        scrumming_interval_pct=2.0,
        trading_fee_pct=0.5,
        adx=adx,
    )


def test_adx_exactly_at_the_threshold_blocks() -> None:
    gate = ADXTrendSuppressionGate(adx_threshold=30.0)
    result = gate.evaluate(_ctx(30.0))
    assert result.passed is False, (
        "adx == adx_threshold must block, because evaluate tests >=; " f"got {result!r}"
    )


def test_adx_message_does_not_claim_a_strict_greater_than() -> None:
    gate = ADXTrendSuppressionGate(adx_threshold=30.0)
    msg = gate.evaluate(_ctx(30.0)).blocker_message
    assert "30.0>" not in msg, (
        "at equality the message must not read 'ADX=30.0>30', which is false; "
        f"got {msg!r}"
    )
    assert "≥" in msg, f"message must state the >= it tested; got {msg!r}"


def test_adx_message_keeps_a_fractional_threshold() -> None:
    gate = ADXTrendSuppressionGate(adx_threshold=27.5)
    msg = gate.evaluate(_ctx(40.0)).blocker_message
    assert "27.5" in msg, (
        "a fractional adx_threshold must not be rounded to 28 in the message; "
        f"got {msg!r}"
    )
    assert "28" not in msg, f"threshold was rounded away; got {msg!r}"


@pytest.mark.parametrize("adx", [0.0, -1.0, 29.9])
def test_adx_below_the_threshold_passes_with_no_message(adx: float) -> None:
    gate = ADXTrendSuppressionGate(adx_threshold=30.0)
    result = gate.evaluate(_ctx(adx))
    assert result.passed is True, f"adx={adx} must pass; got {result!r}"
    assert (
        result.blocker_message == ""
    ), f"a passing gate carries no message; {result!r}"
