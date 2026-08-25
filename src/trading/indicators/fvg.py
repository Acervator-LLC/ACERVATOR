"""Fair Value Gap -- three-candle structural imbalance zones.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""

from __future__ import annotations

# ── FVG (Fair Value Gap) — named constants (R44: no magic numbers) ────────
FVG_LOOKBACK = 24  # candles to scan for 3-candle gap patterns


FVG_PROXIMITY_PCT = 0.005  # "approaching from above": within 0.5% of FVG top


FVG_BULL_BOOST = 0.10  # fold confidence boost when in/near bullish FVG


FVG_BEAR_BOOST = 0.08  # scrum confidence boost when inside bearish FVG


class FVGIndicator:
    """Fair Value Gap detection — structural imbalance zones.

    3-candle FVG pattern:
      Bullish FVG: candles[k-1].high < candles[k+1].low  (gap up)
      Bearish FVG: candles[k-1].low  > candles[k+1].high (gap down)

    Price statistically returns to fill these gaps ~40-60% of the time
    within 48h (validated across BTC/ETH/SOL/ADA/GLD Apr24-Apr25 in Hop 3).
    When price is inside or approaching a bullish FVG from above, it acts
    as a fold magnet — accumulation confidence boost. When price is inside
    a bearish FVG, scrum confidence boost (expectation: gap fills up).

    Returns flat dict of booleans + nearest-zone bounds so downstream
    consumers (sim engine, battery engine, chart overlay) can read without
    coupling to the indicator class itself.
    """

    # sadp: R38, R42, R44
    def __init__(
        self, lookback: int = FVG_LOOKBACK, proximity_pct: float = FVG_PROXIMITY_PCT
    ):
        self.lookback = lookback
        self.proximity_pct = proximity_pct

    def compute(self, candles: list) -> dict:
        default = {
            "fvg_bull_zone": False,
            "fvg_bear_zone": False,
            "fvg_bull_count": 0,
            "fvg_bear_count": 0,
            "fvg_bull_top": 0.0,
            "fvg_bull_bot": 0.0,
            "fvg_bear_top": 0.0,
            "fvg_bear_bot": 0.0,
        }
        if len(candles) < 3:
            return default
        price = candles[-1].close
        if price <= 0:
            return default
        # Scan window: oldest index that still has k-1 and k+1 valid.
        # Use len(candles)-1 as exclusive upper bound so we never peek
        # past the last candle (it has no k+1).
        scan_end = len(candles) - 1
        scan_start = max(1, scan_end - self.lookback)
        bull_zones: list = []
        bear_zones: list = []
        for k in range(scan_start, scan_end):
            c_prev = candles[k - 1]
            c_next = candles[k + 1]
            if c_prev.high < c_next.low:
                bull_zones.append((c_next.low, c_prev.high))  # (top, bot)
            if c_prev.low > c_next.high:
                bear_zones.append((c_prev.low, c_next.high))  # (top, bot)
        # Bull trigger: price inside zone OR just above top (approaching
        # from above within proximity_pct). Pick highest-top active zone
        # (nearest to current price — fold magnet pulls downward).
        nearest_bull = None
        for top, bot in bull_zones:
            in_zone = bot <= price <= top
            approaching = (price > top) and (price <= top * (1.0 + self.proximity_pct))
            if in_zone or approaching:
                if nearest_bull is None or top > nearest_bull[0]:
                    nearest_bull = (top, bot)
        # Bear trigger: price inside zone (gap-down fill, scrum into strength).
        nearest_bear = None
        for top, bot in bear_zones:
            if bot <= price <= top:
                if nearest_bear is None or top > nearest_bear[0]:
                    nearest_bear = (top, bot)
        return {
            "fvg_bull_zone": nearest_bull is not None,
            "fvg_bear_zone": nearest_bear is not None,
            "fvg_bull_count": len(bull_zones),
            "fvg_bear_count": len(bear_zones),
            "fvg_bull_top": round(nearest_bull[0], 8) if nearest_bull else 0.0,
            "fvg_bull_bot": round(nearest_bull[1], 8) if nearest_bull else 0.0,
            "fvg_bear_top": round(nearest_bear[0], 8) if nearest_bear else 0.0,
            "fvg_bear_bot": round(nearest_bear[1], 8) if nearest_bear else 0.0,
        }
