"""Bollinger W-Bottom -- the bullish double-tap of the lower band.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations

from typing import Optional


def detect_w_bottom(
    candles: list,
    bb_pos_history: list,
    lower_threshold: float = 0.10,
    midline_recovery: float = 0.40,
    min_separation: int = 5,
    lookback: int = 30,
) -> dict:
    """v3.19.25 -- Bollinger W-Bottom pattern (L2 closure, bullish half).

    Canonical Bollinger W-Bottom (from Bollinger on Bollinger Bands):
      The pattern is a double-tap of the lower band where:
        (a) Price makes a low touching the lower band (test 1).
        (b) Price RECOVERS toward the middle band (the pullback).
        (c) Price retests support but at a HIGHER absolute price AND a
            HIGHER bb_position than test 1 (the second test is
            "shallower" -- support is firming).
      Pattern is confirmed when price subsequently breaks above the
      pullback's high.

    This detector identifies the 4-point pattern in the most recent
    `lookback` candles. Returns triggered=True when the structural
    pattern is present, regardless of whether the break-above-pullback
    has occurred (that is a separate timing signal).

    Args:
      candles: candle history (uses .close + .low).
      bb_pos_history: per-candle bb_position values aligned with
        candles. Same length as candles. Caller must precompute.
      lower_threshold: bb_position below this counts as a "lower band
        test." Default 0.10 (canonical Bollinger).
      midline_recovery: bb_position above this counts as the "pullback
        recovery." Default 0.40.
      min_separation: minimum candles between the two tests. Default 5;
        prevents adjacent local minima from triggering.
      lookback: how many candles back to scan. Default 30.

    Returns dict with keys: triggered, name, test_1_idx, test_2_idx,
    test_1_low, test_2_low, test_1_bb_pos, test_2_bb_pos, pullback_idx,
    pullback_bb_pos, components_met.

    sadp: R28 R55 R63
    """
    n = len(candles)
    if n < 2 or len(bb_pos_history) != n:
        return {"triggered": False, "name": "w_bottom",
                "error": "insufficient candles or misaligned bb_pos_history"}

    start = max(0, n - lookback)
    window_candles = candles[start:]
    window_bb = bb_pos_history[start:]

    test_indices = [i for i, bp in enumerate(window_bb)
                    if bp < lower_threshold]
    if len(test_indices) < 2:
        return {"triggered": False, "name": "w_bottom",
                "components_met": 0,
                "test_indices_found": len(test_indices)}

    best: Optional[dict] = None
    for i_test_1 in test_indices:
        for i_test_2 in test_indices:
            if i_test_2 - i_test_1 < min_separation:
                continue
            between = window_bb[i_test_1 + 1:i_test_2]
            if not between:
                continue
            pullback_bb = max(between)
            if pullback_bb < midline_recovery:
                continue
            pullback_idx = i_test_1 + 1 + between.index(pullback_bb)
            test_1_low = window_candles[i_test_1].low
            test_2_low = window_candles[i_test_2].low
            test_1_bb = window_bb[i_test_1]
            test_2_bb = window_bb[i_test_2]
            if not (test_2_low > test_1_low and test_2_bb > test_1_bb):
                continue
            best = {
                "triggered": True,
                "name": "w_bottom",
                "test_1_idx": start + i_test_1,
                "test_2_idx": start + i_test_2,
                "test_1_low": test_1_low,
                "test_2_low": test_2_low,
                "test_1_bb_pos": test_1_bb,
                "test_2_bb_pos": test_2_bb,
                "pullback_idx": start + pullback_idx,
                "pullback_bb_pos": pullback_bb,
                "components_met": 4,
            }

    if best is None:
        return {"triggered": False, "name": "w_bottom",
                "components_met": 1,
                "test_indices_found": len(test_indices)}
    return best
