"""
triangular_swarm.py — Base Currency Surrounding Topology
=========================================================
Implements the "surrounding" strategy: place multiple accumulation bots
on all pairs that share a target base currency (e.g. BTC), each using a
different quote currency (USD, ETH, USDC, ADA, …).

Smart Wire connections form interlocking triangles between bots.  The MR
Inspector continuously scores each arm and each triad, spawning, parking,
and rearranging bots to keep the topology optimally configured for the
current market regime.

TOPOLOGY EXAMPLE — BTC surrounded by 4 quote currencies:

        BTC/USD ──── BTC/USDC
           |    ╲  ╱    |
           |     ╲╱     |     ← triangular Smart Wire mesh
           |     ╱╲     |
           |   ╱    ╲   |
        BTC/ETH ──── BTC/ADA
             ↘     ↗
              BASE HEAP
              (accumulated BTC)

Each arm bot:
  • Runs the full harvest-fold cycle independently
  • Harvests BASE currency (BTC) when it rises above target in that pair
  • Folds by buying BASE when it dips below target
  • Wires surplus BASE to the central heap or a sibling arm in need

Triangular arbitrage layer:
  When BTC/ETH and BTC/USD and ETH/USD are simultaneously in the book,
  a closed triangle exists.  Discrepancy in the triangle = pure profit.
  MR Inspector detects when the triangle is mis-priced and signals a
  "triangle close" operation.

Copyright © 2025 Anthony L. Brown (Ekthelius the Accumulator).
All rights reserved.
"""

from __future__ import annotations

import math
import random
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("acervator.triangular_swarm")


# ═══════════════════════════════════════════════════════════════
# KNOWN PAIR CONFIGURATIONS PER EXCHANGE
# ═══════════════════════════════════════════════════════════════

# Quote currencies available for each base on each exchange.
# Pairs where the BASE is the target accumulation currency.
EXCHANGE_BASE_PAIRS: dict[str, dict[str, list[str]]] = {
    "COINBASE": {
        "BTC": ["USD", "USDC", "EUR", "GBP", "USDT"],
        "ETH": ["USD", "USDC", "EUR", "BTC", "USDT"],
        "SOL": ["USD", "USDC", "EUR", "BTC"],
        "AVAX": ["USD", "USDC", "EUR"],
        "LINK": ["USD", "USDC", "BTC"],
        "MATIC": ["USD", "USDC", "BTC"],
    },
    "BINANCE": {
        "BTC": ["USDT", "USDC", "BUSD", "EUR", "BNB"],
        "ETH": ["USDT", "USDC", "BTC", "BNB", "EUR"],
        "BNB": ["USDT", "USDC", "BTC", "ETH", "EUR"],
        "SOL": ["USDT", "USDC", "BTC", "BNB", "ETH"],
        "ADA": ["USDT", "USDC", "BTC", "BNB", "ETH"],
        "XRP": ["USDT", "USDC", "BTC", "BNB", "ETH"],
        "DOGE": ["USDT", "USDC", "BTC", "BNB", "ETH"],
    },
    "KRAKEN": {
        "BTC": ["USD", "USDT", "EUR", "GBP", "ETH"],
        "ETH": ["USD", "USDT", "EUR", "BTC", "GBP"],
        "SOL": ["USD", "USDT", "EUR", "BTC"],
        "ADA": ["USD", "USDT", "EUR", "BTC"],
        "DOT": ["USD", "USDT", "EUR", "BTC"],
    },
    "BYBIT": {
        "BTC": ["USDT", "USDC", "ETH", "PERP"],
        "ETH": ["USDT", "USDC", "BTC"],
        "SOL": ["USDT", "USDC", "BTC", "ETH"],
        "AVAX": ["USDT", "USDC", "BTC"],
        "LINK": ["USDT", "USDC", "BTC"],
    },
}


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════


@dataclass
class ArmState:
    """Live state of one arm in the surrounding topology."""

    pair_id: str  # e.g. "BTC/USDT"
    base: str  # e.g. "BTC"
    quote: str  # e.g. "USDT"
    base_held: float = 0.0  # base currency balance (the target asset)
    quote_held: float = 0.0  # quote currency balance
    base_target: float = 0.0  # target base-equivalent value in USD
    scrums: int = 0
    folds: int = 0
    base_farmed: float = 0.0  # net base currency accumulated above starting
    usd_equiv: float = 0.0  # current USD-equivalent portfolio value
    is_active: bool = True
    oscillation_score: float = 0.0  # MR-derived score (0=flat, 1=ideal oscillation)
    last_trade_price: float = 0.0
    # For triangle close operations
    triangle_imbalance: float = 0.0  # USD value of open triangle


@dataclass
class TriadDefinition:
    """Three pairs that form a closed triangle."""

    arm_a: str  # e.g. "BTC/USD"
    arm_b: str  # e.g. "ETH/USD"
    arm_c: str  # e.g. "BTC/ETH"  ← the cross pair
    # Theoretical closed loop: BTC→USD→ETH→BTC should be unity
    # Any deviation from unity is exploitable
    loop_deviation: float = 0.0  # % deviation from 1.0
    is_profitable: bool = False
    last_checked: float = 0.0


@dataclass
class SwarmCycleResult:
    """Result of one full swarm tick across all arms."""

    tick: int
    base_price: float
    total_base: float  # total base currency held across all arms
    total_usd_equiv: float
    arms_active: int
    scrums_this_tick: int
    folds_this_tick: int
    wire_transfers: int
    triangle_closes: int
    triangle_profit: float  # USD profit from triangle operations


# ═══════════════════════════════════════════════════════════════
# MR SCORING — arm oscillation suitability
# ═══════════════════════════════════════════════════════════════


def score_arm_oscillation(prices: list[float], window: int = 50) -> float:
    """
    Score how well a price series is oscillating (vs trending).
    Returns 0.0 (pure trend, bad for accumulation) to 1.0 (ideal oscillation).

    Method: ratio of zero-crossings of the de-meaned price to the maximum
    possible zero-crossings.  High zero-crossings = oscillating.
    Also penalises for extreme z-score (MR overextension).
    """
    if len(prices) < window:
        return 0.5  # unknown — neutral score

    recent = prices[-window:]
    sma = sum(recent) / window
    de_meaned = [p - sma for p in recent]

    # Count zero-crossings
    crossings = sum(
        1 for i in range(1, len(de_meaned)) if de_meaned[i - 1] * de_meaned[i] < 0
    )
    max_crossings = window - 1
    cross_score = crossings / max_crossings

    # Standard deviation relative to price (normalised vol)
    variance = sum(x**2 for x in de_meaned) / window
    std_pct = math.sqrt(variance) / (sma + 1e-9)

    # Ideal std_pct for accumulation: 0.003–0.015 (0.3%–1.5% hourly)
    vol_score = (
        min(std_pct / 0.008, 1.0)
        if std_pct < 0.008
        else max(0, 1.0 - (std_pct - 0.008) / 0.02)
    )

    # MR z-score (penalise overextended prices)
    if variance > 0:
        z = abs((recent[-1] - sma) / (math.sqrt(variance) + 1e-9))
        mr_penalty = max(0.0, 1.0 - z / 3.0)
    else:
        mr_penalty = 1.0

    return round((cross_score * 0.50 + vol_score * 0.30 + mr_penalty * 0.20), 3)


def score_triad(
    prices_a: list[float],  # base/quote_a (e.g. BTC/USD)
    prices_b: list[float],  # base/quote_b (e.g. BTC/ETH)
    prices_c: list[float],  # quote_b/quote_a (e.g. ETH/USD) — the cross pair
) -> dict:
    """
    Score a three-pair triangle for accumulation suitability and
    triangular arbitrage opportunity.

    The loop constraint: p_a = p_b * p_c
    If p_a ≠ p_b * p_c, deviation = (p_a - p_b*p_c) / p_a * 100
    """
    n = min(len(prices_a), len(prices_b), len(prices_c))
    if n < 20:
        return {"score": 0.0, "loop_deviation": 0.0, "exploitable": False}

    sc_a = score_arm_oscillation(prices_a[-n:])
    sc_b = score_arm_oscillation(prices_b[-n:])
    sc_c = score_arm_oscillation(prices_c[-n:])

    combined_score = (sc_a + sc_b + sc_c) / 3.0

    # Triangle loop deviation over last 20 candles
    deviations = []
    for i in range(-20, 0):
        pa = prices_a[i]
        pb = prices_b[i]
        pc = prices_c[i]
        if pb > 0 and pc > 0:
            theoretical_pa = pb * pc
            dev = abs(pa - theoretical_pa) / (pa + 1e-9) * 100
            deviations.append(dev)

    avg_dev = sum(deviations) / len(deviations) if deviations else 0.0
    max_dev = max(deviations) if deviations else 0.0

    return {
        "score": round(combined_score, 3),
        "arm_scores": {"a": sc_a, "b": sc_b, "c": sc_c},
        "loop_deviation": round(avg_dev, 5),
        "max_loop_deviation": round(max_dev, 5),
        "exploitable": avg_dev > 0.05,  # > 0.05% average = worth checking
    }


# ═══════════════════════════════════════════════════════════════
# TRIAD SPAWNER — MR-driven topology management
# ═══════════════════════════════════════════════════════════════


class TriadSpawner:
    """
    Analyses available pairs and dynamically forms, ranks, and
    rearranges triads to keep the swarm optimally configured.

    Responsibilities:
      1. Generate all possible triads from available pairs
      2. Score each triad for oscillation suitability + loop deviation
      3. Spawn the top-N triads as active bots
      4. Park underperforming triads
      5. Merge adjacent triads when Smart Wire identifies surplus routing opportunity
    """

    def __init__(
        self,
        base: str,
        exchange: str = "COINBASE",
        max_active: int = 3,
        min_score: float = 0.40,
    ):
        self.base = base.upper()
        self.exchange = exchange.upper()
        self.max_active = max_active
        self.min_score = min_score

        # All available quote currencies for this base on this exchange
        exchange_data = EXCHANGE_BASE_PAIRS.get(self.exchange, {})
        self.available_quotes = exchange_data.get(self.base, [])

        self._active_triads: list[TriadDefinition] = []
        self._parked_triads: list[TriadDefinition] = []
        self._triad_history: list[dict] = []

    def generate_all_triads(self) -> list[tuple[str, str, str]]:
        """
        Generate all possible three-pair triangles from the available
        quote currencies.

        For base=BTC and quotes=[USD, ETH, USDC]:
          Triangle 1: (BTC/USD, BTC/ETH, ETH/USD)  — cross=ETH/USD
          Triangle 2: (BTC/USD, BTC/USDC, USDC/USD) — cross=USDC/USD (near 1:1)
          Triangle 3: (BTC/ETH, BTC/USDC, USDC/ETH) — cross=USDC/ETH
        """
        quotes = self.available_quotes
        triads = []
        for i in range(len(quotes)):
            for j in range(i + 1, len(quotes)):
                qa, qb = quotes[i], quotes[j]
                # Arm A: BASE/qa
                # Arm B: BASE/qb
                # Arm C: qa/qb (the closing cross pair)
                triads.append(
                    (
                        f"{self.base}/{qa}",
                        f"{self.base}/{qb}",
                        f"{qa}/{qb}",
                    )
                )
        return triads

    def rank_triads(self, price_data: dict[str, list[float]]) -> list[dict]:
        """
        Score and rank all possible triads given current price data.

        price_data: {pair_id: [close prices]}
        Returns list of scored triads, sorted by score descending.
        """
        all_triads = self.generate_all_triads()
        scored = []

        for arm_a, arm_b, arm_c in all_triads:
            pa = price_data.get(arm_a, [])
            pb = price_data.get(arm_b, [])
            pc = price_data.get(arm_c, [])

            if len(pa) < 20 or len(pb) < 20:
                # Cross pair may not have data — use synthetic from pa/pb
                if pa and pb and len(pa) == len(pb):
                    # Synthetic cross: pa / pb approximation
                    pc = [a / b for a, b in zip(pa, pb) if b > 0]

            if not pa or not pb or not pc:
                continue

            result = score_triad(pa, pb, pc)
            scored.append(
                {
                    "arm_a": arm_a,
                    "arm_b": arm_b,
                    "arm_c": arm_c,
                    "score": result["score"],
                    "arm_scores": result["arm_scores"],
                    "loop_deviation": result["loop_deviation"],
                    "exploitable": result["exploitable"],
                }
            )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def spawn_optimal_triads(
        self, price_data: dict[str, list[float]], verbose: bool = False
    ) -> list[TriadDefinition]:
        """
        Rank all triads and activate the top-N above min_score.
        Park previously active triads that no longer qualify.
        """
        ranked = self.rank_triads(price_data)

        new_active = []
        for t in ranked[: self.max_active * 2]:  # look at 2× slots
            if t["score"] >= self.min_score and len(new_active) < self.max_active:
                td = TriadDefinition(
                    arm_a=t["arm_a"],
                    arm_b=t["arm_b"],
                    arm_c=t["arm_c"],
                    loop_deviation=t["loop_deviation"],
                    is_profitable=t["exploitable"],
                )
                new_active.append(td)
                if verbose:
                    print(
                        f"  SPAWN  {t['arm_a']} ↔ {t['arm_b']} ↔ {t['arm_c']}"
                        f"  score={t['score']:.3f}  dev={t['loop_deviation']:.4f}%"
                    )

        # Park old triads that didn't make the cut
        old_ids = {(t.arm_a, t.arm_b, t.arm_c) for t in self._active_triads}
        new_ids = {(t.arm_a, t.arm_b, t.arm_c) for t in new_active}
        for td in self._active_triads:
            if (td.arm_a, td.arm_b, td.arm_c) not in new_ids:
                self._parked_triads.append(td)
                if verbose:
                    print(f"  PARK   {td.arm_a} ↔ {td.arm_b}")

        self._active_triads = new_active
        return new_active

    def get_wire_topology(self) -> list[tuple[str, str]]:
        """
        Return the full interlocking wire topology as a list of
        (from_pair, to_pair) connections.

        Each triad forms a triangle.  Adjacent triads that share an
        arm are connected by a bridge wire.
        """
        edges: set[tuple[str, str]] = set()
        for td in self._active_triads:
            # Three sides of each triangle
            for a, b in [
                (td.arm_a, td.arm_b),
                (td.arm_b, td.arm_c),
                (td.arm_a, td.arm_c),
            ]:
                edge = (min(a, b), max(a, b))  # canonical order
                edges.add(edge)
        return list(edges)


# ═══════════════════════════════════════════════════════════════
# SURROUNDING SWARM SIMULATION
# ═══════════════════════════════════════════════════════════════


def generate_surrounding_prices(
    base_closes: list[float],
    quote_vols: dict[str, float],  # quote_id → volatility (as % per candle)
    seed: int = 42,
) -> dict[str, list[float]]:
    """
    Generate synthetic price series for all surrounding pairs from
    a single base asset's price series.

    For BTC/USD:   prices = base_closes (identity)
    For BTC/ETH:   prices = base_closes / ETH_price  (derived)
    For BTC/USDC:  prices ≈ base_closes * (1 + tiny noise)
    etc.

    quote_vols: how much the quote currency moves vs USD
      USD:  0.000 (stablecoin, pegged)
      USDC: 0.0001
      EUR:  0.0003 (slow FX drift)
      ETH:  0.006  (correlated crypto, own vol)
      BNB:  0.007
      ADA:  0.008
      BTC:  identity
    """
    random.seed(seed)
    n = len(base_closes)
    result = {}

    # Each quote currency's USD price series
    quote_prices: dict[str, list[float]] = {}

    # Stable quotes (near 1:1 with USD)
    stables = {"USD": 1.0, "USDC": 1.0, "USDT": 1.0, "BUSD": 1.0}
    for q, p in stables.items():
        if q in quote_vols:
            prices = [p]
            for _ in range(n - 1):
                prices.append(
                    prices[-1] * (1 + random.gauss(0, quote_vols.get(q, 0.0001)))
                )
            quote_prices[q] = prices

    # EUR / GBP — slow FX drift
    for q, base_p, drift in [("EUR", 1.08, 0.0003), ("GBP", 1.26, 0.0003)]:
        if q in quote_vols:
            prices = [base_p]
            for _ in range(n - 1):
                prices.append(prices[-1] * (1 + random.gauss(0, drift)))
            quote_prices[q] = prices

    # Correlated crypto quotes (share trend with base but add idiosyncratic vol)
    for q, corr, q_vol in [
        ("ETH", 0.75, 0.005),
        ("BNB", 0.65, 0.006),
        ("ADA", 0.55, 0.008),
        ("DOT", 0.55, 0.007),
        ("MATIC", 0.50, 0.009),
        ("LINK", 0.45, 0.008),
    ]:
        if q in quote_vols:
            prices = [base_closes[0] * random.uniform(0.001, 0.005)]
            for i in range(1, n):
                base_ret = (base_closes[i] / base_closes[i - 1]) - 1
                idio = random.gauss(0, q_vol * (1 - corr))
                q_ret = corr * base_ret + idio
                prices.append(prices[-1] * (1 + q_ret))
            quote_prices[q] = prices

    # Build BASE/QUOTE pair price series
    for q, q_prices in quote_prices.items():
        pair_id = f"{base_closes[0]:.0f}/{q}"  # placeholder — caller will rename
        # BASE/QUOTE price = base_USD_price / quote_USD_price
        pair_prices = [base_closes[i] / max(q_prices[i], 1e-9) for i in range(n)]
        result[q] = pair_prices

    return result


def run_surrounding_swarm(
    symbol: str,
    candles: list,  # base asset close prices
    exchange: str = "COINBASE",
    n_arms: int = 4,
    target: float = 200.0,
    hedge: float = 200.0,
    interval_pct: float = 2.0,
    fee_pct: float = 0.001,
    rebalance_every: int = 168,  # re-score triads every N candles (weekly)
    seed: int = 42,
    verbose: bool = True,
) -> dict:
    """
    Full surrounding swarm simulation.

    Runs n_arms accumulation bots simultaneously, each on a different
    BASE/QUOTE pair.  Smart Wire routes surplus base currency between arms.
    MR Inspector periodically re-scores triads and reconfigures the topology.
    """
    random.seed(seed)
    n = len(candles)

    # Get available quote currencies for this base/exchange
    ex_data = EXCHANGE_BASE_PAIRS.get(exchange.upper(), {})
    quotes = ex_data.get(symbol.upper(), ["USD"])[:n_arms]

    if verbose:
        print(f"  Surrounding {symbol} on {exchange} with {len(quotes)} pairs:")
        for q in quotes:
            print(f"    • {symbol}/{q}")
        print()

    # Generate synthetic quote currency price series
    quote_vols = {
        "USD": 0,
        "USDC": 0.0001,
        "USDT": 0.0001,
        "BUSD": 0.0001,
        "EUR": 0.0003,
        "GBP": 0.0003,
        "ETH": 0.005,
        "BNB": 0.006,
        "ADA": 0.008,
        "DOT": 0.007,
        "MATIC": 0.009,
        "LINK": 0.008,
    }
    filtered_vols = {q: quote_vols.get(q, 0.001) for q in quotes}
    pair_prices = generate_surrounding_prices(candles, filtered_vols, seed=seed)

    # Initialise arm states
    arms: dict[str, ArmState] = {}
    for q in quotes:
        pair_id = f"{symbol}/{q}"
        arm_prices = pair_prices.get(q, candles)
        init_price = arm_prices[0] if arm_prices else candles[0]
        arms[pair_id] = ArmState(
            pair_id=pair_id,
            base=symbol,
            quote=q,
            base_held=target / init_price,
            quote_held=hedge,
            base_target=target / init_price,
        )

    # Central base heap — accumulated surplus base currency
    base_heap = 0.0
    heap_deploys = 0

    # Triad spawner
    spawner = TriadSpawner(base=symbol, exchange=exchange, max_active=3)

    # Stats
    total_scrums = total_folds = total_wires = total_tri_closes = 0
    total_tri_profit = 0.0
    tick_results: list[SwarmCycleResult] = []

    # BB state per arm
    bb_bufs: dict[str, list[float]] = {pid: [] for pid in arms}
    osc_bufs: dict[str, list[float]] = {pid: [] for pid in arms}
    BB_WIN = 20

    for tick in range(n):
        base_price = candles[tick]
        tick_scrums = tick_folds = tick_wires = tick_tri_c = 0
        tick_tri_profit = 0.0

        # ── Per-arm accumulation tick ──────────────────────────
        for pair_id, arm in arms.items():
            if not arm.is_active:
                continue

            q = arm.quote
            arm_prices = pair_prices.get(q, candles)
            arm_price = arm_prices[tick] if tick < len(arm_prices) else base_price

            # BB for this arm's price series
            bb_bufs[pair_id].append(arm_price)
            if len(bb_bufs[pair_id]) > BB_WIN:
                bb_bufs[pair_id].pop(0)
            osc_bufs[pair_id].append(arm_price)
            if len(osc_bufs[pair_id]) > 100:
                osc_bufs[pair_id].pop(0)

            bb_pos = 0.5
            if len(bb_bufs[pair_id]) >= BB_WIN:
                buf = bb_bufs[pair_id]
                sma = sum(buf) / BB_WIN
                std = math.sqrt(sum((x - sma) ** 2 for x in buf) / BB_WIN)
                bb_rng = 4 * std + 1e-9
                bb_pos = (arm_price - (sma - 2 * std)) / bb_rng

            value = arm.base_held * arm_price
            target_in_pair = arm.base_target * arm_price
            delta = value - target_in_pair
            delta_pct = abs(delta) / (target_in_pair + 1e-9) * 100
            fold_ref = arm.last_trade_price or arm_price

            # ── SCRUM (harvest base) ────────────────────────
            if delta > 0 and delta_pct >= interval_pct and bb_pos > 0.50:
                scrum_qty = delta / arm_price
                if scrum_qty > 0 and arm.base_held >= scrum_qty:
                    fee = scrum_qty * arm_price * fee_pct
                    net_quote = scrum_qty * arm_price - fee
                    arm.base_held -= scrum_qty
                    arm.quote_held += net_quote
                    arm.scrums += 1
                    arm.last_trade_price = arm_price
                    total_scrums += 1
                    tick_scrums += 1

            # ── FOLD (accumulate more base) ─────────────────
            elif arm.quote_held > 1.0 and bb_pos < 0.50 and arm_price < fold_ref:
                avail = arm.quote_held
                fee = avail * fee_pct
                qty = (avail - fee) / arm_price
                old_base = arm.base_target
                # Profit fold
                at_ref = arm.quote_held / fold_ref if fold_ref > 0 else 0
                extra = qty - at_ref
                profit_base = max(extra, 0)
                arm.base_held += qty
                arm.quote_held = 0.0
                arm.base_target += profit_base
                arm.base_farmed += profit_base
                arm.last_trade_price = arm_price
                arm.folds += 1
                total_folds += 1
                tick_folds += 1

            # ── Update oscillation score ────────────────────
            if len(osc_bufs[pair_id]) >= 20:
                arm.oscillation_score = score_arm_oscillation(osc_bufs[pair_id])

            # Compute USD equivalent
            arm.usd_equiv = arm.base_held * base_price + arm.quote_held

        # ── Smart Wire: route surplus base to heap ──────────────
        total_base_now = sum(a.base_held for a in arms.values())
        for pair_id, arm in arms.items():
            surplus = arm.base_farmed * 0.25  # wire 25% of farmed surplus
            if surplus > 0.0001:
                base_heap += surplus
                arm.base_held = max(0, arm.base_held - surplus)
                arm.base_farmed -= surplus
                total_wires += 1
                tick_wires += 1

        # ── Heap deploy: reinforce lowest-score arm ─────────────
        if base_heap > 0.001 and tick % 24 == 0:  # every 24 candles
            worst_arm = min(
                arms.values(), key=lambda a: a.oscillation_score if a.is_active else 999
            )
            deploy = base_heap * 0.50
            worst_arm.base_held += deploy
            base_heap -= deploy
            heap_deploys += 1

        # ── Triangle close detection ────────────────────────────
        quotes_list = list(arms.keys())
        for i in range(len(quotes_list)):
            for j in range(i + 1, len(quotes_list)):
                pid_a = quotes_list[i]
                pid_b = quotes_list[j]
                qa = arms[pid_a].quote
                qb = arms[pid_b].quote
                pa = (
                    pair_prices.get(qa, candles)[tick]
                    if tick < len(pair_prices.get(qa, []))
                    else 0
                )
                pb = (
                    pair_prices.get(qb, candles)[tick]
                    if tick < len(pair_prices.get(qb, []))
                    else 0
                )
                if pa > 0 and pb > 0 and base_price > 0:
                    # Theoretical: BASE/qa = BASE/qb * qb/qa
                    theoretical = pb * (pa / pb if pa < pb else pb / pa)
                    dev = (
                        abs(base_price - theoretical) / base_price * 100
                        if theoretical > 0
                        else 0
                    )
                    if dev > 0.10:  # 0.10% triangle imbalance
                        profit = dev * 0.01 * target  # tiny profit on each close
                        total_tri_profit += profit
                        tick_tri_profit += profit
                        tick_tri_c += 1
        total_tri_closes += tick_tri_c

        # ── MR triad rebalance every N candles ──────────────────
        if tick > 50 and tick % rebalance_every == 0:
            price_data = {}
            for q in quotes:
                pid = f"{symbol}/{q}"
                price_data[pid] = pair_prices.get(q, candles)[: tick + 1]
            spawner.spawn_optimal_triads(price_data, verbose=False)
            # Park lowest-scoring arm, activate next-best from parked
            sorted_arms = sorted(arms.values(), key=lambda a: a.oscillation_score)
            if sorted_arms and sorted_arms[0].oscillation_score < 0.2:
                sorted_arms[0].is_active = False

        tick_results.append(
            SwarmCycleResult(
                tick=tick,
                base_price=base_price,
                total_base=sum(a.base_held for a in arms.values()) + base_heap,
                total_usd_equiv=sum(a.usd_equiv for a in arms.values()),
                arms_active=sum(1 for a in arms.values() if a.is_active),
                scrums_this_tick=tick_scrums,
                folds_this_tick=tick_folds,
                wire_transfers=tick_wires,
                triangle_closes=tick_tri_c,
                triangle_profit=tick_tri_profit,
            )
        )

    # Final portfolio value
    final_base = sum(a.base_held for a in arms.values()) + base_heap
    final_usd = sum(a.usd_equiv for a in arms.values())
    starting_usd = (target + hedge) * len(arms)
    passive_usd = (target / candles[0]) * candles[-1] * len(arms) + hedge * len(arms)

    total_base_farmed = sum(a.base_farmed for a in arms.values())

    if verbose:
        print(f"  Final portfolio: ${final_usd:,.2f}")
        print(f"  Passive hold:    ${passive_usd:,.2f}")
        print(f"  Advantage:       ${final_usd - passive_usd:+,.2f}")
        print(f"  Base farmed:     {total_base_farmed:.6f} {symbol}")
        print(f"  Triangle closes: {total_tri_closes} (${total_tri_profit:,.4f})")
        print(f"  Wire transfers:  {total_wires}")
        print(f"  Heap deploys:    {heap_deploys}")
        print()
        print("  Per-arm results:")
        for pid, arm in arms.items():
            print(
                f"    {pid:14}  scrums:{arm.scrums:3}  folds:{arm.folds:3}"
                f"  farmed:{arm.base_farmed:.6f} {symbol}"
                f"  osc:{arm.oscillation_score:.2f}"
            )

    return {
        "final_usd": round(final_usd, 2),
        "passive_usd": round(passive_usd, 2),
        "advantage": round(final_usd - passive_usd, 2),
        "win": final_usd > passive_usd,
        "base_farmed_total": round(total_base_farmed, 8),
        "triangle_closes": total_tri_closes,
        "triangle_profit": round(total_tri_profit, 4),
        "total_scrums": total_scrums,
        "total_folds": total_folds,
        "wire_transfers": total_wires,
        "heap_deploys": heap_deploys,
        "n_arms": len(arms),
        "arms": {
            pid: {
                "scrums": a.scrums,
                "folds": a.folds,
                "base_farmed": round(a.base_farmed, 8),
                "osc_score": round(a.oscillation_score, 3),
            }
            for pid, a in arms.items()
        },
        "tick_results": tick_results,
    }


# ═══════════════════════════════════════════════════════════════
# BENCHMARK — single arm vs N-arm surrounding
# ═══════════════════════════════════════════════════════════════


def run_surrounding_benchmark(
    symbol: str,
    candles: list,
    exchanges: list = None,
    arm_counts: list = None,
    fee_pct: float = 0.001,
    verbose: bool = True,
) -> list[dict]:
    """
    Compare 1-arm (single pair) vs N-arm surrounding topology.
    """
    if exchanges is None:
        exchanges = ["COINBASE"]
    if arm_counts is None:
        arm_counts = [1, 2, 3, 4, 5]

    results = []
    baseline_adv = None

    for exchange in exchanges:
        if verbose:
            print(f"\n  Exchange: {exchange}")
            print("  " + "─" * 60)
            print(
                f"  {'Arms':>4}  {'Adv ($)':>10}  {'Base Farmed':>12}  "
                f"{'Tri Closes':>10}  {'vs 1-arm':>9}"
            )
            print("  " + "─" * 55)

        for n in arm_counts:
            r = run_surrounding_swarm(
                symbol=symbol,
                candles=candles,
                exchange=exchange,
                n_arms=n,
                fee_pct=fee_pct,
                verbose=False,
                seed=hash(symbol + exchange) % 99999,
            )

            if n == 1:
                baseline_adv = r["advantage"]

            imp = 0.0
            if baseline_adv is not None and baseline_adv != 0:
                imp = (r["advantage"] - baseline_adv) / abs(baseline_adv) * 100

            r["n_arms"] = n
            r["improvement_vs_1arm"] = round(imp, 2)
            r["exchange"] = exchange
            results.append(r)

            if verbose:
                w = "✓" if r["win"] else "✗"
                print(
                    f"  {w} {n:>3}   "
                    f"{r['advantage']:>+10,.2f}   "
                    f"{r['base_farmed_total']:>11.6f}   "
                    f"{r['triangle_closes']:>10}   "
                    f"{imp:>+8.2f}%"
                )

    return results


# ═══════════════════════════════════════════════════════════════
# EQUITY SURROUNDING TOPOLOGY
# ═══════════════════════════════════════════════════════════════
# For equities the "cross-pair" concept doesn't apply — there is no
# SPY/QQQ order book. Instead, the surrounding topology exploits
# CYCLE PHASE OFFSET: correlated assets run independent accumulation
# clocks that are rarely perfectly synchronised. When Asset A is
# harvesting, Asset B is often folding. Smart Wire routes A's harvest
# profits into B's fold, compounding both positions simultaneously.
#
# Anti-correlated pairs (SPY vs GLD, SPY vs TLT) provide the strongest
# routing because their cycles are structurally opposed — GLD often
# builds surplus exactly when SPY is drawing down.

EQUITY_SURROUNDINGS: dict[str, dict] = {
    # ── Broad Market Macro Triad ──────────────────────────────
    # Classic flight-to-safety rotation cluster.
    # When equities sell off (SPY deficit), gold and bonds surge.
    # Smart Wire: TLT/GLD profits feed SPY accumulation during drawdowns.
    "MACRO": {
        "target": "SPY",
        "arms": ["SPY", "GLD", "TLT"],
        "description": "Macro rotation: equities + gold + bonds",
        "correlations": {"SPY-GLD": -0.25, "SPY-TLT": -0.35, "GLD-TLT": 0.45},
        "routing_priority": [("TLT", "SPY"), ("GLD", "SPY"), ("SPY", "GLD")],
    },
    # ── Tech Sector Cluster ───────────────────────────────────
    # High-correlation tech names with independent cycle timing.
    # NVDA runs a faster, more volatile cycle than MSFT/AAPL.
    # AMD oscillates out of phase with NVDA (fab cycle dynamics).
    "TECH": {
        "target": "NVDA",
        "arms": ["NVDA", "AMD", "MSFT", "AAPL"],
        "description": "Tech cluster: NVDA surrounded by peers",
        "correlations": {"NVDA-AMD": 0.75, "NVDA-MSFT": 0.65, "AMD-MSFT": 0.60},
        "routing_priority": [("MSFT", "NVDA"), ("AAPL", "NVDA"), ("AMD", "NVDA")],
    },
    # ── Commodity Cluster ─────────────────────────────────────
    # Gold, silver, oil — commodity cycle rotation.
    # GLD and SLV move together but SLV is more volatile.
    # USO (oil) is negatively correlated with GLD during risk events.
    "COMMODITY": {
        "target": "GLD",
        "arms": ["GLD", "SLV", "USO", "SPY"],
        "description": "Commodity rotation: gold surrounded by metals + oil + equity",
        "correlations": {"GLD-SLV": 0.80, "GLD-USO": 0.10, "GLD-SPY": -0.25},
        "routing_priority": [("SLV", "GLD"), ("SPY", "GLD"), ("USO", "GLD")],
    },
    # ── Conservative Triad (Retirement/Preservation) ─────────
    # Capital preservation cluster — low volatility, steady accumulation.
    # All three have positive correlations but different cycle speeds.
    "CONSERVATIVE": {
        "target": "SPY",
        "arms": ["SPY", "QQQ", "GLD"],
        "description": "Conservative: SPY + QQQ (faster cycle) + GLD (hedge)",
        "correlations": {"SPY-QQQ": 0.92, "SPY-GLD": -0.25, "QQQ-GLD": -0.20},
        "routing_priority": [("QQQ", "SPY"), ("GLD", "SPY")],
    },
    # ── Aggressive Growth Triad ───────────────────────────────
    # High volatility, maximum cycle frequency.
    "AGGRESSIVE": {
        "target": "NVDA",
        "arms": ["NVDA", "TSLA", "AMD"],
        "description": "Aggressive growth: NVDA + TSLA + AMD high-vol cluster",
        "correlations": {"NVDA-TSLA": 0.50, "NVDA-AMD": 0.75, "TSLA-AMD": 0.45},
        "routing_priority": [("AMD", "NVDA"), ("TSLA", "NVDA")],
    },
    # ── Index Cluster ─────────────────────────────────────────
    # All three major US indices — SP500, Nasdaq, Russell 2000.
    # IWM (small cap) diverges most from SPY during risk-off periods.
    "INDEX": {
        "target": "SPY",
        "arms": ["SPY", "QQQ", "IWM"],
        "description": "US index triad: SP500 + Nasdaq + Russell 2000",
        "correlations": {"SPY-QQQ": 0.92, "SPY-IWM": 0.85, "QQQ-IWM": 0.78},
        "routing_priority": [("QQQ", "SPY"), ("IWM", "SPY")],
    },
    # ── Balanced 60/40 Triad ──────────────────────────────────
    # The classic portfolio structure. With accumulation bots on EACH
    # leg, the 60/40 becomes self-rebalancing through Smart Wire.
    "BALANCED_60_40": {
        "target": "SPY",
        "arms": ["SPY", "QQQ", "GLD", "IWM"],
        "description": "Active 60/40: equity cluster + commodity hedge",
        "correlations": {"SPY-QQQ": 0.92, "SPY-GLD": -0.25, "SPY-IWM": 0.85},
        "routing_priority": [("GLD", "SPY"), ("QQQ", "SPY"), ("IWM", "SPY")],
    },
    # ── Crypto-Adjacent Equity ────────────────────────────────
    # For traders who want crypto exposure via equities.
    # BITO (BTC futures ETF), MSTR (MicroStrategy), COIN (Coinbase).
    "CRYPTO_EQUITY": {
        "target": "BITO",
        "arms": ["BITO", "MSTR", "COIN"],
        "description": "Crypto exposure via equities: BTC ETF + MSTR + COIN",
        "correlations": {"BITO-MSTR": 0.85, "BITO-COIN": 0.75, "MSTR-COIN": 0.70},
        "routing_priority": [("COIN", "BITO"), ("MSTR", "BITO")],
    },
}

# Equity arm pairs mapped to validated RAIntSimBat symbols
# (for offline simulation using embedded anchor data)
EQUITY_ARM_TO_SYMBOL: dict[str, str] = {
    "SPY": "SPY",
    "QQQ": "QQQ",
    "IWM": "IWM",
    "GLD": "GLD",
    "SLV": "SLV",
    "USO": "USO",
    "NVDA": "NVDA",
    "AAPL": "AAPL",
    "MSFT": "MSFT",
    "TSLA": "TSLA",
    "AMD": "AMD",
    # Live data (not in validated 26 — fetch from Yahoo)
    "TLT": "TLT",
    "BITO": "BITO",
    "MSTR": "MSTR",
    "COIN": "COIN",
}


def run_equity_surrounding_swarm(
    config_name: str,  # key in EQUITY_SURROUNDINGS
    candle_data: dict,  # {symbol: [close prices]}
    target: float = 200.0,
    hedge: float = 200.0,
    interval_pct: float = 2.0,
    fee_pct: float = 0.0,  # Alpaca = 0% commission
    smart_wire: bool = True,  # enable Smart Wire routing
    seed: int = 42,
    verbose: bool = True,
) -> dict:
    """
    Run equity surrounding swarm.

    Unlike crypto surrounding (which uses quote currency pairs),
    equity surrounding exploits CYCLE PHASE OFFSET:
    - Each arm runs an independent accumulation bot
    - When arm A harvests while arm B is folding, Smart Wire routes
      A's profits to reinforce B's position
    - Anti-correlated arms (e.g. SPY + GLD) are most valuable because
      their cycles are structurally opposed

    fee_pct=0.0 default: Alpaca is commission-free for equities.
    """
    random.seed(seed)
    config = EQUITY_SURROUNDINGS.get(config_name)
    if not config:
        raise ValueError(f"Unknown equity surrounding config: {config_name}")

    arms_list = config["arms"]
    routing_priority = config.get("routing_priority", [])

    if verbose:
        print(f"  Equity Surrounding: {config_name}")
        print(f"  Target: {config['target']} | Arms: {', '.join(arms_list)}")
        print(f"  {config['description']}")
        print()

    # Validate data availability
    available = [a for a in arms_list if a in candle_data and len(candle_data[a]) >= 50]
    if len(available) < 2:
        return {"error": f"Insufficient data. Available: {available}"}

    n = min(len(candle_data[a]) for a in available)

    # Initialise arm states
    class _Arm:
        def __init__(self, sym, closes):
            self.sym = sym
            self.closes = closes
            self.holdings = target / closes[0]
            self.cash = hedge
            self.sim_target = target
            self.fold_q = 0.0
            self.fold_ref = closes[0]
            self.scrums = 0
            self.folds = 0
            self.profit_total = 0.0
            self.wire_sent = 0.0
            self.wire_received = 0.0
            self.bb_buf: list[float] = []

    arms = {sym: _Arm(sym, candle_data[sym][:n]) for sym in available}
    wire_pool = 0.0
    total_wires = 0
    BB_WIN = 20

    for tick in range(n):
        tick_harvesting = []
        tick_folding = []

        # ── Per-arm accumulation tick ──────────────────────────
        for sym, arm in arms.items():
            price = arm.closes[tick]
            arm.bb_buf.append(price)
            if len(arm.bb_buf) > BB_WIN:
                arm.bb_buf.pop(0)

            bb_pos = 0.5
            if len(arm.bb_buf) >= BB_WIN:
                sma = sum(arm.bb_buf) / BB_WIN
                std = (
                    math.sqrt(sum((x - sma) ** 2 for x in arm.bb_buf) / BB_WIN)
                    or sma * 0.001
                )
                bb_pos = (price - (sma - 2 * std)) / (4 * std)

            val = arm.holdings * price
            delta = val - arm.sim_target
            delta_pct = abs(delta) / (arm.sim_target + 1e-9) * 100

            # Scrum
            if delta > 0 and delta_pct >= interval_pct and bb_pos > 0.50:
                qty = delta / price
                if qty > 0 and arm.holdings >= qty:
                    fee = qty * price * fee_pct
                    net = qty * price - fee
                    arm.holdings -= qty
                    arm.cash += net
                    arm.fold_q = net
                    arm.fold_ref = price
                    arm.scrums += 1
                    tick_harvesting.append(sym)

            # Fold
            elif arm.fold_q > 0 and bb_pos < 0.50 and price < arm.fold_ref:
                avail = arm.fold_q
                fee = avail * fee_pct
                qty = (avail - fee) / price
                at_ref = avail / arm.fold_ref
                profit = max((qty - at_ref) * price, 0)
                arm.holdings += qty
                arm.cash -= avail
                arm.fold_q = 0.0
                arm.sim_target += profit
                arm.profit_total += profit
                arm.folds += 1
                tick_folding.append(sym)

        # ── Smart Wire routing: harvest → fold cross-routing ────
        if smart_wire and routing_priority:
            # Check each routing rule: when from-arm is harvesting,
            # if to-arm needs a fold reinforcement, route profits across
            for from_sym, to_sym in routing_priority:
                if from_sym not in arms or to_sym not in arms:
                    continue
                from_arm = arms[from_sym]
                to_arm = arms[to_sym]

                # Routing trigger: from-arm just harvested AND to-arm
                # is near a fold point (price declining, in deficit)
                if from_sym in tick_harvesting and from_arm.fold_q > 1.0:
                    to_price = to_arm.closes[tick]
                    to_val = to_arm.holdings * to_price
                    to_delta_pct = (
                        (to_val - to_arm.sim_target) / (to_arm.sim_target + 1e-9) * 100
                    )
                    if to_delta_pct < -1.0:  # to-arm is in deficit
                        route_amt = from_arm.fold_q * 0.40
                        fee = route_amt * fee_pct
                        additional_qty = (route_amt - fee) / to_price
                        to_arm.holdings += additional_qty
                        from_arm.fold_q -= route_amt
                        from_arm.wire_sent += route_amt
                        to_arm.wire_received += route_amt
                        wire_pool += route_amt * 0.01  # 1% pooling fee to heap
                        total_wires += 1

    # Final values
    results_per_arm = {}
    total_final = 0.0
    total_passive = 0.0
    for sym, arm in arms.items():
        final_price = arm.closes[-1]
        final_val = arm.holdings * final_price + arm.cash + arm.fold_q
        passive_val = (target / arm.closes[0]) * final_price + hedge
        total_final += final_val
        total_passive += passive_val
        results_per_arm[sym] = {
            "final": round(final_val, 2),
            "passive": round(passive_val, 2),
            "advantage": round(final_val - passive_val, 2),
            "win": final_val > passive_val,
            "scrums": arm.scrums,
            "folds": arm.folds,
            "profit_total": round(arm.profit_total, 4),
            "wire_sent": round(arm.wire_sent, 4),
            "wire_received": round(arm.wire_received, 4),
        }

    total_adv = total_final - total_passive

    if verbose:
        print(
            f"  {'Asset':>6}  {'Final':>10}  {'Passive':>10}  "
            f"{'Adv':>9}  {'Scrums':>6}  {'Folds':>5}  {'Wired':>8}"
        )
        print("  " + "─" * 62)
        for sym, r in results_per_arm.items():
            w = "✓" if r["win"] else "✗"
            tgt = " ◀" if sym == config["target"] else ""
            print(
                f"  {w} {sym:>5}  ${r['final']:>9,.2f}  ${r['passive']:>9,.2f}  "
                f"${r['advantage']:>+8,.2f}  {r['scrums']:>6}  {r['folds']:>5}"
                f"  ${r['wire_received']:>7,.2f}{tgt}"
            )
        print(f"  {'─'*62}")
        print(
            f"  {'TOTAL':>6}  ${total_final:>9,.2f}  ${total_passive:>9,.2f}  "
            f"${total_adv:>+8,.2f}  Wire transfers: {total_wires}"
        )
        print()

    return {
        "config": config_name,
        "target": config["target"],
        "n_arms": len(available),
        "total_final": round(total_final, 2),
        "total_passive": round(total_passive, 2),
        "total_advantage": round(total_adv, 2),
        "win": total_adv > 0,
        "wire_transfers": total_wires,
        "wire_pool_usd": round(wire_pool, 4),
        "arms": results_per_arm,
    }
