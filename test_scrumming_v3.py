#!/usr/bin/env python3
"""
Scrumming Bot v3 Simulation Test Suite
Tests targeting state machine + TA confidence across market scenarios.
"""
import math, random, time
from dataclasses import dataclass

# Import TA engine
from src.trading.ta_engine import (
    Candle, VortexIndicator, MACD, BollingerBands,
    compute_heikin_ashi, detect_bb_proximity
)

@dataclass
class SimCandle:
    time: int; open: float; high: float; low: float; close: float; volume: float

# ── Price generators ──────────────────────────────────────────
def gen_range_bound(n=500, center=100, amplitude=10, seed=42):
    """Oscillating price around center."""
    rng = random.Random(seed)
    candles = []
    price = center
    for i in range(n):
        move = rng.gauss(0, amplitude * 0.03) + math.sin(i * 0.05) * amplitude * 0.01
        o = price
        price = max(center * 0.5, price + move)
        h = max(o, price) + abs(rng.gauss(0, amplitude * 0.005))
        l = min(o, price) - abs(rng.gauss(0, amplitude * 0.005))
        candles.append(SimCandle(i * 3600, o, h, l, price, 10000 + abs(move) * 1e5))
    return candles

def gen_bull_run(n=500, start=42000, end=73000, seed=42):
    """Strong bull trend (BTC Jan-Mar 2024 style)."""
    rng = random.Random(seed)
    candles = []
    price = start
    step = (end - start) / n
    for i in range(n):
        o = price
        noise = rng.gauss(0, price * 0.008)
        price = price + step + noise
        # Occasional small pullbacks
        if rng.random() < 0.15:
            price -= step * 2
        h = max(o, price) + abs(rng.gauss(0, price * 0.003))
        l = min(o, price) - abs(rng.gauss(0, price * 0.003))
        candles.append(SimCandle(i * 3600, o, h, l, price, 10000 + abs(step) * 100))
    return candles

def gen_bear_drop(n=500, start=73000, end=55000, seed=42):
    """Bear market drop."""
    rng = random.Random(seed)
    candles = []
    price = start
    step = (end - start) / n
    for i in range(n):
        o = price
        noise = rng.gauss(0, price * 0.008)
        price = price + step + noise
        if rng.random() < 0.15:
            price -= step * 2  # Occasional bounces (negative step → positive bounce)
        h = max(o, price) + abs(rng.gauss(0, price * 0.003))
        l = min(o, price) - abs(rng.gauss(0, price * 0.003))
        candles.append(SimCandle(i * 3600, o, h, l, price, 10000))
    return candles

def gen_volatile_chop(n=500, center=65000, seed=42):
    """High volatility choppy market."""
    rng = random.Random(seed)
    candles = []
    price = center
    for i in range(n):
        o = price
        move = rng.gauss(0, center * 0.02)
        price = max(center * 0.7, min(center * 1.3, price + move))
        h = max(o, price) + abs(rng.gauss(0, center * 0.005))
        l = min(o, price) - abs(rng.gauss(0, center * 0.005))
        candles.append(SimCandle(i * 3600, o, h, l, price, 10000 + abs(move) * 100))
    return candles

# ── Scrumming Bot Simulator ──────────────────────────────────
class ScrumSim:
    """Lightweight scrumming bot simulator with TA + targeting."""

    def __init__(self, candles, investment=200, scrum_interval=2.0,
                 bb_tolerance=1.0, detect_pct=50, fire_pct=1.0):
        self.candles = candles
        self.investment = investment
        self.scrum_interval = scrum_interval
        self.bb_tolerance = bb_tolerance
        self.detect_pct = detect_pct / 100.0
        self.fire_pct = fire_pct / 100.0

        # Balances
        first_price = candles[0].close
        self.holdings = investment / first_price
        self.usd = 0.0
        self.target = investment
        self.starting_holdings = self.holdings

        # State
        self.trades = 0
        self.scrums = 0
        self.folds = 0
        self.pnl = 0.0
        self.volume = 0.0
        self.fold_queue_usd = 0.0
        self.fold_ref_price = 0.0
        self.dist_queue = 0.0

        # Targeting
        self.mode = "search"
        self.target_side = None
        self.ta_cache = None
        self.ta_cache_idx = -10

    def _compute_ta(self, idx):
        if idx - self.ta_cache_idx < 5 and self.ta_cache:
            return self.ta_cache
        window = self.candles[max(0, idx - 100):idx + 1]
        if len(window) < 26:
            return None
        ta_candles = [Candle(c.time, c.open, c.high, c.low, c.close, c.volume)
                      for c in window]
        try:
            bb = detect_bb_proximity(ta_candles, tolerance_pct=self.bb_tolerance)
            vx = VortexIndicator(14).compute(ta_candles, "1h")
            macd = MACD().compute(ta_candles, "1h")
            ha = compute_heikin_ashi(ta_candles)
            snapshot = {
                "bb": bb, "bb_position": bb.bb_position,
                "bb_near_upper": bb.near_upper, "bb_near_lower": bb.near_lower,
                "landing_strip": bb.landing_strip, "landing_side": bb.landing_strip_side,
                "ha_bullish": ha[-1].close > ha[-1].open if ha else False,
                "ha_bearish": ha[-1].close < ha[-1].open if ha else False,
                "vx_bull": vx.direction.value > 0,
                "vx_converging": abs(vx.details.get("separation", 0)) < 0.08,
                "macd_contracting": (macd.details.get("histogram", 0) > 0 and macd.confidence < 0.4),
                "macd_expanding_bull": (macd.details.get("histogram", 0) > 0 and macd.confidence >= 0.4),
            }
            self.ta_cache = snapshot
            self.ta_cache_idx = idx
            return snapshot
        except Exception:
            return None

    def run(self):
        for idx, candle in enumerate(self.candles):
            price = candle.close
            value = self.holdings * price
            delta = value - self.target
            delta_pct = abs(delta) / (self.target + 1e-9) * 100
            bullish = candle.close > candle.open
            bearish = candle.close < candle.open

            ta = self._compute_ta(idx)

            # BB for targeting
            if ta:
                bb_mid = ta["bb"].middle
                bb_upper = ta["bb"].upper
                bb_lower = ta["bb"].lower
                bb_pos = ta["bb_position"]
            else:
                bb_mid = bb_upper = bb_lower = price
                bb_pos = 0.5

            # Targeting
            above_mid = price > bb_mid
            if above_mid:
                band_range = bb_upper - bb_mid
                dist = (price - bb_mid) / (band_range + 1e-12)
                side = "upper"
                near = abs(price - bb_upper) / (bb_upper + 1e-12) <= self.fire_pct
            else:
                band_range = bb_mid - bb_lower
                dist = (bb_mid - price) / (band_range + 1e-12)
                side = "lower"
                near = abs(price - bb_lower) / (bb_lower + 1e-12) <= self.fire_pct

            if self.target_side and self.target_side != side:
                self.mode = "search"
            if self.mode == "search":
                if dist >= self.detect_pct and delta_pct >= self.scrum_interval * 0.5:
                    self.mode = "track"
                    self.target_side = side
            elif self.mode == "track":
                if near:
                    self.mode = "fire"
                elif dist < self.detect_pct * 0.5:
                    self.mode = "search"

            # Confidence
            scrum_conf = 0.50 if bullish else 0.0
            fold_conf = 0.50 if bearish else 0.0
            if ta:
                if ta["ha_bullish"] and bullish: scrum_conf += 0.10
                if bb_pos > 0.6: scrum_conf += 0.10 * min(1.0, (bb_pos - 0.5) * 4)
                if ta["bb_near_upper"]: scrum_conf += 0.10
                if ta["landing_strip"] and ta["landing_side"] == "upper": scrum_conf += 0.15
                if ta["vx_converging"]: scrum_conf += 0.05
                elif ta["vx_bull"]: scrum_conf -= 0.05
                if ta["macd_contracting"]: scrum_conf += 0.10
                elif ta["macd_expanding_bull"]: scrum_conf -= 0.05

                if ta["ha_bearish"] and bearish: fold_conf += 0.10
                if bb_pos < 0.4: fold_conf += 0.10 * min(1.0, (0.5 - bb_pos) * 4)
                if ta["bb_near_lower"]: fold_conf += 0.10
                if ta["landing_strip"] and ta["landing_side"] == "lower": fold_conf += 0.15
                if ta["macd_expanding_bull"]: fold_conf += 0.10
                if not ta["vx_bull"] and ta["vx_converging"]: fold_conf += 0.05

            scrum_conf = max(0.0, min(1.0, scrum_conf))
            fold_conf = max(0.0, min(1.0, fold_conf))

            s_thresh = 0.20 if self.mode == "fire" else 0.35
            f_thresh = 0.15 if self.mode == "fire" else 0.30

            # SCRUM
            if delta > 0 and delta_pct >= self.scrum_interval and scrum_conf >= s_thresh:
                scrum_asset = delta / price
                if self.holdings >= scrum_asset and scrum_asset > 0:
                    self.holdings -= scrum_asset
                    scrum_usd = scrum_asset * price
                    self.usd += scrum_usd
                    self.trades += 1; self.scrums += 1
                    self.volume += scrum_usd
                    self.fold_queue_usd += scrum_usd
                    self.fold_ref_price = price
                    self.mode = "search"

            # FOLD
            if self.fold_queue_usd > 0 and fold_conf >= f_thresh:
                usd_avail = min(self.fold_queue_usd, self.usd)
                if usd_avail > 0 and price < self.fold_ref_price:
                    buy = usd_avail / price
                    at_scrum = usd_avail / self.fold_ref_price
                    extra = buy - at_scrum
                    self.usd -= usd_avail
                    self.holdings += buy
                    self.pnl += extra * price
                    self.trades += 1; self.folds += 1
                    self.volume += usd_avail
                    self.fold_queue_usd = 0.0
                    self.mode = "search"

        # Final
        final_price = self.candles[-1].close
        portfolio = self.usd + self.holdings * final_price
        passive = self.starting_holdings * final_price
        return {
            "portfolio": portfolio,
            "passive_hold": passive,
            "pnl": portfolio - self.investment,
            "passive_pnl": passive - self.investment,
            "advantage": portfolio - passive,
            "trades": self.trades,
            "scrums": self.scrums,
            "folds": self.folds,
            "volume": self.volume,
            "start_price": self.candles[0].close,
            "end_price": final_price,
            "price_change": (final_price / self.candles[0].close - 1) * 100,
        }


# ── Run Tests ─────────────────────────────────────────────────
def run_scenario(name, candles, **kwargs):
    sim = ScrumSim(candles, **kwargs)
    r = sim.run()
    pnl_color = "\033[92m" if r["pnl"] >= 0 else "\033[91m"
    adv_color = "\033[92m" if r["advantage"] >= 0 else "\033[91m"
    reset = "\033[0m"

    print(f"\n{'═' * 60}")
    print(f"  {name}")
    print(f"  Price: ${r['start_price']:,.2f} → ${r['end_price']:,.2f} ({r['price_change']:+.1f}%)")
    print(f"{'─' * 60}")
    print(f"  Trades: {r['trades']} ({r['scrums']} scrums, {r['folds']} folds)")
    print(f"  Volume: ${r['volume']:,.2f}")
    print(f"  Portfolio: ${r['portfolio']:,.2f}  "
          f"({pnl_color}P/L: ${r['pnl']:+,.2f}{reset})")
    print(f"  Passive:   ${r['passive_hold']:,.2f}  "
          f"(P/L: ${r['passive_pnl']:+,.2f})")
    print(f"  {adv_color}Advantage: ${r['advantage']:+,.2f}{reset}")
    print(f"{'═' * 60}")
    return r


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  SCRUMMING BOT v3 — SIMULATION TEST SUITE")
    print("  TA Confidence + Targeting State Machine")
    print("=" * 60)

    results = {}

    # Test 1: Range-bound (ideal scenario)
    results["range_bound"] = run_scenario(
        "RANGE-BOUND ($90–$110, 500 candles)",
        gen_range_bound(500, center=100, amplitude=10))

    # Test 2: Strong bull run (BTC 2024 problem scenario)
    results["bull_run"] = run_scenario(
        "BULL RUN ($42K→$73K, 500 candles — BTC Jan-Mar 2024)",
        gen_bull_run(500, start=42000, end=73000))

    # Test 3: Bear drop
    results["bear_drop"] = run_scenario(
        "BEAR DROP ($73K→$55K, 500 candles)",
        gen_bear_drop(500, start=73000, end=55000))

    # Test 4: Volatile chop
    results["volatile"] = run_scenario(
        "VOLATILE CHOP (±20% around $65K, 500 candles)",
        gen_volatile_chop(500, center=65000))

    # Test 5: Bull then bear (full cycle)
    bull = gen_bull_run(250, start=42000, end=73000, seed=42)
    bear = gen_bear_drop(250, start=73000, end=58000, seed=43)
    # Adjust timestamps for bear portion
    for i, c in enumerate(bear):
        bear[i] = SimCandle(c.time + 250 * 3600, c.open, c.high, c.low, c.close, c.volume)
    cycle = bull + bear
    results["full_cycle"] = run_scenario(
        "FULL CYCLE: Bull $42K→$73K then Bear $73K→$58K (500 candles)",
        cycle)

    # Test 6: Tight range (low volatility)
    results["tight"] = run_scenario(
        "TIGHT RANGE ($99–$101, 500 candles, low vol)",
        gen_range_bound(500, center=100, amplitude=2))

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    wins = sum(1 for r in results.values() if r["advantage"] >= 0)
    total = len(results)
    print(f"  Scenarios won vs passive: {wins}/{total}")
    for name, r in results.items():
        adv = r["advantage"]
        sym = "✓" if adv >= 0 else "✗"
        print(f"    {sym} {name:20s}: advantage ${adv:+,.2f} "
              f"({r['trades']} trades, price {r['price_change']:+.1f}%)")

    total_adv = sum(r["advantage"] for r in results.values())
    print(f"\n  Total advantage across all scenarios: ${total_adv:+,.2f}")
    print("=" * 60)
