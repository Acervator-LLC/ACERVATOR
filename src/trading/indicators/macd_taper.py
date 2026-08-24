"""MACD histogram taper and consolidation-wedge detection.

Reads a histogram LIST handed in by the caller. It never
calls MACD itself, so it computes no moving average of
its own and cannot drift from the one the caller used.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# 3b. MACD Consolidation / Taper Detection
# ---------------------------------------------------------------------------

def detect_macd_taper(histogram: list, lookback: int = 8) -> dict:
    """
    Detects MACD histogram deceleration and consolidation patterns.

    Three patterns:
      BULLISH TAPER  — negative bars shrinking toward zero (bearish momentum
                       decelerating); fold signal strengthened.
      BEARISH TAPER  — positive bars shrinking toward zero (bullish momentum
                       stalling); scrum confidence reduced.
      OSCILLATION WEDGE — alternating +/- bars with decreasing amplitude,
                       forming a converging triangle (pure consolidation /
                       indecision); breakout imminent, direction unknown.

    Args:
        histogram: list of recent MACD histogram values (newest last)
        lookback:  number of bars to analyse (default 8, ~8h on 1h TF)

    Returns dict:
        taper_type      : 'bullish' | 'bearish' | 'wedge' | 'none'
        taper_strength  : 0.0–1.0  (fraction of lookback bars tapering)
        bars_tapering   : int      (consecutive bars in taper)
        toward_cross    : bool     (MACD approaching zero line)
        consolidating   : bool     (any meaningful taper detected)
    """
    result = {
        "taper_type": "none",
        "taper_strength": 0.0,
        "bars_tapering": 0,
        "toward_cross": False,
        "consolidating": False,
    }

    if len(histogram) < lookback:
        return result

    recent = histogram[-lookback:]
    abs_vals = [abs(v) for v in recent]
    n = len(recent)

    # ── Pattern 1 & 2: directional taper ─────────────────────────────────
    # Count consecutive bars on the same side of zero, shrinking in magnitude
    def _directional_taper(bars, target_sign):
        """How many consecutive bars of target_sign are getting smaller?"""
        taper = 0
        prev_abs = None
        for v in reversed(bars):
            sign = 1 if v > 0 else (-1 if v < 0 else 0)
            if sign != target_sign:
                break
            abs_v = abs(v)
            if prev_abs is None or abs_v <= prev_abs:
                taper += 1
                prev_abs = abs_v
            else:
                break
        return taper

    bull_taper = _directional_taper(recent, -1)  # negative bars shrinking
    bear_taper = _directional_taper(recent, +1)  # positive bars shrinking

    # ── Pattern 3: oscillation wedge ─────────────────────────────────────
    # Alternating signs AND decreasing peak amplitude in both halves
    signs = [1 if v > 0 else -1 for v in recent if v != 0]
    alt_count = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i-1])
    alternating = alt_count >= len(signs) - 2 if len(signs) > 2 else False

    first_half_peak  = max(abs_vals[:n//2]) if n >= 4 else 0
    second_half_peak = max(abs_vals[n//2:]) if n >= 4 else 0
    amplitude_shrinking = second_half_peak < first_half_peak * 0.85

    # Overall bar shrinkage fraction (any direction)
    taper_count = sum(1 for i in range(1, n) if abs_vals[i] < abs_vals[i-1])
    taper_strength = taper_count / max(n - 1, 1)

    # Approaching zero line?
    toward_cross = abs_vals[-1] < abs_vals[0] * 0.5 if abs_vals[0] > 1e-9 else False

    # ── Classify ──────────────────────────────────────────────────────────
    if alternating and amplitude_shrinking and taper_strength >= 0.5:
        result.update({
            "taper_type":     "wedge",
            "taper_strength": round(taper_strength, 3),
            "bars_tapering":  taper_count,
            "toward_cross":   toward_cross,
            "consolidating":  True,
        })
    elif bull_taper >= 3:
        result.update({
            "taper_type":     "bullish",
            "taper_strength": round(bull_taper / n, 3),
            "bars_tapering":  bull_taper,
            "toward_cross":   toward_cross,
            "consolidating":  True,
        })
    elif bear_taper >= 3:
        result.update({
            "taper_type":     "bearish",
            "taper_strength": round(bear_taper / n, 3),
            "bars_tapering":  bear_taper,
            "toward_cross":   toward_cross,
            "consolidating":  True,
        })
    elif taper_strength >= 0.65:
        # General taper without clear directional bias
        dominant_sign = 1 if sum(recent) > 0 else -1
        t_type = "bearish" if dominant_sign > 0 else "bullish"
        result.update({
            "taper_type":     t_type,
            "taper_strength": round(taper_strength, 3),
            "bars_tapering":  taper_count,
            "toward_cross":   toward_cross,
            "consolidating":  True,
        })

    return result
