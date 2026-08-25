"""Scenario exercise of the TA engine + a toy scrumming simulator.

Provenance
==========
This is the framework port of the old repo-root ``test_scrumming_v3.py``,
a print-only script that swept a handful of synthetic market shapes through
the real TA engine and a lightweight scrumming simulator, then printed a
coloured P/L table for a human to eyeball. It was never collected by pytest
(``testpaths = ["tests"]``), retained nothing, and asserted nothing — so a
regression in the TA engine surfaced only if someone happened to run the
script and read the numbers.

What this file keeps, and what it drops
=======================================
KEEP — the synthetic price generators and the toy ``ScrumSim`` are useful
scaffolding for driving the TA engine across market regimes, so they move
here as test helpers.

DROP — the printing, the ANSI colours, and any notion of a "P/L advantage"
pass/fail. ``ScrumSim`` is a *toy*: it is NOT the production
``ScrummingBot``, so pinning its dollar outcomes would pin the toy, not the
product. The dollar figures are not invariants and are not asserted.

What is actually asserted (all in memory, nothing written to disk):
  * the real TA engine computes over every regime without raising and
    returns structurally valid, finite indicator values;
  * the toy simulator runs each regime to completion and conserves the
    obvious invariants (holdings never go negative, trade count == scrums +
    folds, every reported figure is finite);
  * the whole pipeline is deterministic for a fixed seed.

If any of those breaks, this test fails — which the original script could
never do.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pytest

from src.trading.ta_engine import (
    Candle,
    MACD,
    VortexIndicator,
    compute_heikin_ashi,
    detect_bb_proximity,
)


@dataclass
class SimCandle:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


# ── Synthetic price generators (deterministic for a fixed seed) ───────────
def gen_range_bound(n=500, center=100, amplitude=10, seed=42):
    """Oscillating price around ``center``."""
    rng = random.Random(seed)
    candles = []
    price = center
    for i in range(n):
        move = rng.gauss(0, amplitude * 0.03) + math.sin(i * 0.05) * amplitude * 0.01
        o = price
        price = max(center * 0.5, price + move)
        h = max(o, price) + abs(rng.gauss(0, amplitude * 0.005))
        low = min(o, price) - abs(rng.gauss(0, amplitude * 0.005))
        candles.append(SimCandle(i * 3600, o, h, low, price, 10000 + abs(move) * 1e5))
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
        if rng.random() < 0.15:  # occasional small pullbacks
            price -= step * 2
        h = max(o, price) + abs(rng.gauss(0, price * 0.003))
        low = min(o, price) - abs(rng.gauss(0, price * 0.003))
        candles.append(SimCandle(i * 3600, o, h, low, price, 10000 + abs(step) * 100))
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
        if rng.random() < 0.15:  # occasional bounces
            price -= step * 2
        h = max(o, price) + abs(rng.gauss(0, price * 0.003))
        low = min(o, price) - abs(rng.gauss(0, price * 0.003))
        candles.append(SimCandle(i * 3600, o, h, low, price, 10000))
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
        low = min(o, price) - abs(rng.gauss(0, center * 0.005))
        candles.append(SimCandle(i * 3600, o, h, low, price, 10000 + abs(move) * 100))
    return candles


# ── Toy scrumming simulator (NOT the production ScrummingBot) ──────────────
class ScrumSim:
    """Lightweight scrumming simulator used only to drive the TA engine.

    It intentionally re-implements a small slice of scrum/fold logic so a
    scenario can be run end to end without constructing a real bot, exchange
    and event bus. Its dollar outputs are illustrative, not authoritative.
    """

    def __init__(
        self,
        candles,
        investment=200,
        scrum_interval=2.0,
        bb_tolerance=1.0,
        detect_pct=50,
        fire_pct=1.0,
    ):
        self.candles = candles
        self.investment = investment
        self.scrum_interval = scrum_interval
        self.bb_tolerance = bb_tolerance
        self.detect_pct = detect_pct / 100.0
        self.fire_pct = fire_pct / 100.0

        first_price = candles[0].close
        self.holdings = investment / first_price
        self.usd = 0.0
        self.target = investment
        self.starting_holdings = self.holdings

        self.trades = 0
        self.scrums = 0
        self.folds = 0
        self.pnl = 0.0
        self.volume = 0.0
        self.fold_queue_usd = 0.0
        self.fold_ref_price = 0.0
        self.dist_queue = 0.0

        self.mode = "search"
        self.target_side = None
        self.ta_cache = None
        self.ta_cache_idx = -10
        # Tracks the lowest holdings ever seen; asserted non-negative by tests.
        self.min_holdings = self.holdings

    def _compute_ta(self, idx):
        if idx - self.ta_cache_idx < 5 and self.ta_cache:
            return self.ta_cache
        window = self.candles[max(0, idx - 100) : idx + 1]
        if len(window) < 26:
            return None
        ta_candles = [
            Candle(c.time, c.open, c.high, c.low, c.close, c.volume) for c in window
        ]
        bb = detect_bb_proximity(ta_candles, tolerance_pct=self.bb_tolerance)
        vx = VortexIndicator(14).compute(ta_candles, "1h")
        macd = MACD().compute(ta_candles, "1h")
        ha = compute_heikin_ashi(ta_candles)
        snapshot = {
            "bb": bb,
            "bb_position": bb.bb_position,
            "bb_near_upper": bb.near_upper,
            "bb_near_lower": bb.near_lower,
            "landing_strip": bb.landing_strip,
            "landing_side": bb.landing_strip_side,
            "ha_bullish": ha[-1].close > ha[-1].open if ha else False,
            "ha_bearish": ha[-1].close < ha[-1].open if ha else False,
            "vx_bull": vx.direction.value > 0,
            "vx_converging": abs(vx.details.get("separation", 0)) < 0.08,
            "macd_contracting": (
                macd.details.get("histogram", 0) > 0 and macd.confidence < 0.4
            ),
            "macd_expanding_bull": (
                macd.details.get("histogram", 0) > 0 and macd.confidence >= 0.4
            ),
        }
        self.ta_cache = snapshot
        self.ta_cache_idx = idx
        return snapshot

    def run(self):
        for idx, candle in enumerate(self.candles):
            price = candle.close
            value = self.holdings * price
            delta = value - self.target
            delta_pct = abs(delta) / (self.target + 1e-9) * 100
            bullish = candle.close > candle.open
            bearish = candle.close < candle.open

            ta = self._compute_ta(idx)

            if ta:
                bb_mid = ta["bb"].middle
                bb_upper = ta["bb"].upper
                bb_lower = ta["bb"].lower
                bb_pos = ta["bb_position"]
            else:
                bb_mid = bb_upper = bb_lower = price
                bb_pos = 0.5

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

            scrum_conf = 0.50 if bullish else 0.0
            fold_conf = 0.50 if bearish else 0.0
            if ta:
                if ta["ha_bullish"] and bullish:
                    scrum_conf += 0.10
                if bb_pos > 0.6:
                    scrum_conf += 0.10 * min(1.0, (bb_pos - 0.5) * 4)
                if ta["bb_near_upper"]:
                    scrum_conf += 0.10
                if ta["landing_strip"] and ta["landing_side"] == "upper":
                    scrum_conf += 0.15
                if ta["vx_converging"]:
                    scrum_conf += 0.05
                elif ta["vx_bull"]:
                    scrum_conf -= 0.05
                if ta["macd_contracting"]:
                    scrum_conf += 0.10
                elif ta["macd_expanding_bull"]:
                    scrum_conf -= 0.05

                if ta["ha_bearish"] and bearish:
                    fold_conf += 0.10
                if bb_pos < 0.4:
                    fold_conf += 0.10 * min(1.0, (0.5 - bb_pos) * 4)
                if ta["bb_near_lower"]:
                    fold_conf += 0.10
                if ta["landing_strip"] and ta["landing_side"] == "lower":
                    fold_conf += 0.15
                if ta["macd_expanding_bull"]:
                    fold_conf += 0.10
                if not ta["vx_bull"] and ta["vx_converging"]:
                    fold_conf += 0.05

            scrum_conf = max(0.0, min(1.0, scrum_conf))
            fold_conf = max(0.0, min(1.0, fold_conf))

            s_thresh = 0.20 if self.mode == "fire" else 0.35
            f_thresh = 0.15 if self.mode == "fire" else 0.30

            # SCRUM — sell the excess above target
            if (
                delta > 0
                and delta_pct >= self.scrum_interval
                and scrum_conf >= s_thresh
            ):
                scrum_asset = delta / price
                if self.holdings >= scrum_asset and scrum_asset > 0:
                    self.holdings -= scrum_asset
                    scrum_usd = scrum_asset * price
                    self.usd += scrum_usd
                    self.trades += 1
                    self.scrums += 1
                    self.volume += scrum_usd
                    self.fold_queue_usd += scrum_usd
                    self.fold_ref_price = price
                    self.mode = "search"

            # FOLD — buy back more on the dip
            if self.fold_queue_usd > 0 and fold_conf >= f_thresh:
                usd_avail = min(self.fold_queue_usd, self.usd)
                if usd_avail > 0 and price < self.fold_ref_price:
                    buy = usd_avail / price
                    at_scrum = usd_avail / self.fold_ref_price
                    extra = buy - at_scrum
                    self.usd -= usd_avail
                    self.holdings += buy
                    self.pnl += extra * price
                    self.trades += 1
                    self.folds += 1
                    self.volume += usd_avail
                    self.fold_queue_usd = 0.0
                    self.mode = "search"

            self.min_holdings = min(self.min_holdings, self.holdings)

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
            "min_holdings": self.min_holdings,
            "start_price": self.candles[0].close,
            "end_price": final_price,
            "price_change": (final_price / self.candles[0].close - 1) * 100,
        }


# ── Scenario matrix ───────────────────────────────────────────────────────
def _scenarios():
    """Named market regimes → candle series. Kept as a function so each
    parametrized case regenerates its own series (no shared mutable state)."""
    bull = gen_bull_run(250, start=42000, end=73000, seed=42)
    bear = gen_bear_drop(250, start=73000, end=58000, seed=43)
    for i, c in enumerate(bear):  # stitch bear onto the tail of bull
        bear[i] = SimCandle(
            c.time + 250 * 3600, c.open, c.high, c.low, c.close, c.volume
        )
    return {
        "range_bound": gen_range_bound(500, center=100, amplitude=10),
        "bull_run": gen_bull_run(500, start=42000, end=73000),
        "bear_drop": gen_bear_drop(500, start=73000, end=55000),
        "volatile_chop": gen_volatile_chop(500, center=65000),
        "full_cycle": bull + bear,
        "tight_range": gen_range_bound(500, center=100, amplitude=2),
    }


SCENARIO_NAMES = list(_scenarios().keys())


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


@pytest.fixture(params=SCENARIO_NAMES)
def scenario(request):
    return request.param, _scenarios()[request.param]


def test_ta_engine_computes_valid_indicators_across_regimes(scenario):
    """The real TA engine must run over every regime and return finite,
    structurally valid indicator values — this is what the old script could
    only reveal by a human reading the printout."""
    name, candles = scenario
    ta_candles = [
        Candle(c.time, c.open, c.high, c.low, c.close, c.volume) for c in candles
    ]

    bb = detect_bb_proximity(ta_candles, tolerance_pct=1.0)
    assert _finite(bb.middle) and _finite(bb.upper) and _finite(bb.lower), name
    assert bb.lower <= bb.middle <= bb.upper, name
    assert _finite(bb.bb_position), name

    vx = VortexIndicator(14).compute(ta_candles, "1h")
    assert _finite(vx.details.get("separation", 0.0)), name
    assert vx.direction is not None, name

    macd = MACD().compute(ta_candles, "1h")
    assert _finite(macd.details.get("histogram", 0.0)), name
    assert _finite(macd.confidence), name

    ha = compute_heikin_ashi(ta_candles)
    assert len(ha) == len(ta_candles), name
    assert all(_finite(c.open) and _finite(c.close) for c in ha), name


def test_toy_sim_runs_and_conserves_invariants(scenario):
    """The toy simulator must complete each regime with sane invariants.

    These are properties of any correct scrum/fold bookkeeping, not claims
    about profitability: holdings never go negative, the trade count equals
    scrums plus folds, and every reported figure is finite.
    """
    name, candles = scenario
    result = ScrumSim(candles).run()

    assert result["min_holdings"] >= 0.0, f"{name}: holdings went negative"
    assert result["trades"] == result["scrums"] + result["folds"], name
    assert result["scrums"] >= 0 and result["folds"] >= 0, name
    assert result["volume"] >= 0.0, name
    for key in ("portfolio", "passive_hold", "pnl", "advantage", "price_change"):
        assert _finite(result[key]), f"{name}: {key} not finite"


def test_pipeline_is_deterministic_for_a_fixed_seed():
    """Same generator seed → identical simulator result. A drift here means
    something in the TA engine or the generators became non-deterministic."""
    candles_a = gen_volatile_chop(300, center=65000, seed=7)
    candles_b = gen_volatile_chop(300, center=65000, seed=7)
    assert ScrumSim(candles_a).run() == ScrumSim(candles_b).run()
