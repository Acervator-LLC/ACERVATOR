"""Bollinger M-Top -- the bearish double-tap of the upper band.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations

from typing import Optional


def detect_m_top(
    candles: list,
    bb_pos_history: list,
    upper_threshold: float = 0.90,
    midline_pullback: float = 0.60,
    min_separation: int = 5,
    lookback: int = 30,
) -> dict:
    """v3.19.25 -- Bollinger M-Top pattern (L2 closure, bearish half).

    Mirror of W-Bottom: two distinct highs touching the upper band, with
    the second high at LOWER absolute price AND LOWER bb_position than
    the first (support is "softening" at the upper band; sellers are
    stepping in higher).

    Args follow detect_w_bottom -- upper_threshold is the high-band test
    bound (default 0.90); midline_pullback is the recovery-down bound
    (default 0.60); rest identical.

    Returns dict matching detect_w_bottom shape but with test_1_high /
    test_2_high instead of low, and the directional inequalities flipped.

    sadp: R28 R55 R63
    """
    n = len(candles)
    if n < 2 or len(bb_pos_history) != n:
        return {"triggered": False, "name": "m_top",
                "error": "insufficient candles or misaligned bb_pos_history"}

    start = max(0, n - lookback)
    window_candles = candles[start:]
    window_bb = bb_pos_history[start:]

    test_indices = [i for i, bp in enumerate(window_bb)
                    if bp > upper_threshold]
    if len(test_indices) < 2:
        return {"triggered": False, "name": "m_top",
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
            pullback_bb = min(between)
            if pullback_bb > midline_pullback:
                continue
            pullback_idx = i_test_1 + 1 + between.index(pullback_bb)
            test_1_high = window_candles[i_test_1].high
            test_2_high = window_candles[i_test_2].high
            test_1_bb = window_bb[i_test_1]
            test_2_bb = window_bb[i_test_2]
            if not (test_2_high < test_1_high and test_2_bb < test_1_bb):
                continue
            best = {
                "triggered": True,
                "name": "m_top",
                "test_1_idx": start + i_test_1,
                "test_2_idx": start + i_test_2,
                "test_1_high": test_1_high,
                "test_2_high": test_2_high,
                "test_1_bb_pos": test_1_bb,
                "test_2_bb_pos": test_2_bb,
                "pullback_idx": start + pullback_idx,
                "pullback_bb_pos": pullback_bb,
                "components_met": 4,
            }

    if best is None:
        return {"triggered": False, "name": "m_top",
                "components_met": 1,
                "test_indices_found": len(test_indices)}
    return best
