"""
cross_pool.py — Cross-Pool Accumulation Advantage Engine
==========================================================
Models the price differential that exists between the same asset's
order books on different exchanges (or base-pair pools on the same
exchange) and quantifies the profiteering advantage available to
the harvest-fold accumulation cycle by routing operations to the
most favorable pool at execution time.

CORE INSIGHT (Anthony L. Brown, 2020)
--------------------------------------
Standard accumulation routes every harvest and fold to the same
price source.  The same asset simultaneously exists in N pools at
slightly different prices (BTC/USDT Binance ≠ BTC/USDT Kraken ≠
BTC/USD Coinbase at any given moment).

Cross-pool routing:
  HARVEST → sell into the HIGHEST available pool price
  FOLD    → buy from the  LOWEST  available pool price

This captures (p_high - p_low) × quantity ON EVERY CYCLE, compounding
through the profit-folding mechanism on top of the delta advantage.

MODELS PROVIDED
---------------
  CrossPoolSpreadModel   – tracks N pool prices, computes spread stats
  CrossPoolSimulator     – runs a single accumulation sim with pool routing
  CrossPoolBenchmark     – compares single-pool vs N-pool across many sims
  route_to_best_pool     – standalone routing function for live bots

"""

from __future__ import annotations

import math
import random
import logging
from dataclasses import dataclass

log = logging.getLogger("acervator.cross_pool")


# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════


@dataclass
class PoolQuote:
    """Price snapshot for one pool at one moment."""

    pool_id: str
    price: float
    bid: float
    ask: float
    fee_pct: float = 0.001  # 0.10% default maker fee


@dataclass
class PoolRoutingDecision:
    """Result of a pool routing query."""

    side: str  # "harvest" | "fold"
    best_pool: str
    best_price: float
    worst_price: float
    spread_pct: float  # (best - worst) / worst × 100
    net_advantage: float  # spread_pct − 2 × fee (net after round-trip)
    pools_checked: int
    is_profitable: bool  # True if net_advantage > 0


@dataclass
class CrossPoolCycleResult:
    """Result of one harvest-fold cycle with pool routing."""

    harvest_pool: str
    harvest_price: float
    fold_pool: str
    fold_price: float
    spread_captured: float  # USD captured from pool routing this cycle
    spread_pct: float  # spread as % of price
    base_profit: float  # profit from delta alone (single-pool equivalent)
    total_profit: float  # base_profit + spread_captured
    enhancement_pct: float  # how much pool routing improved the yield


# ═══════════════════════════════════════════════════════════════
# SPREAD MODEL — mean-reverting synthetic pool prices
# ═══════════════════════════════════════════════════════════════


class CrossPoolSpreadModel:
    """
    Generates N correlated price series for the same asset.
    Prices are mean-reverting: they drift apart and snap back together,
    mimicking real exchange price discovery dynamics.

    Parameters
    ----------
    n_pools      : number of exchange pools to simulate
    base_price   : starting price
    max_spread   : maximum price divergence between any two pools (%)
    mean_rev_spd : how quickly the spread collapses (0.01 = slow, 0.1 = fast)
    volatility   : per-candle price volatility (std dev as %)
    """

    def __init__(
        self,
        n_pools: int = 3,
        base_price: float = 65000.0,
        max_spread: float = 0.30,  # % max between any two pools
        mean_rev_spd: float = 0.04,  # mean-reversion speed
        volatility: float = 0.004,  # hourly vol
        fee_pcts: list = None,
        seed: int = None,
    ):

        self.n_pools = n_pools
        self.base_price = base_price
        self.max_spread = max_spread / 100
        self.mean_rev_spd = mean_rev_spd
        self.volatility = volatility

        # Default fee schedule per pool (can be overridden)
        self.fee_pcts = fee_pcts or [0.001] * n_pools

        if seed is not None:
            random.seed(seed)

        # Initialise pool prices with small random offsets
        self._prices = [
            base_price * (1 + random.gauss(0, self.max_spread * 0.3))
            for _ in range(n_pools)
        ]
        self._midpoint = base_price

    def step(self) -> list[float]:
        """
        Advance one time step.  Returns current pool prices after update.
        Prices share a common random walk but drift independently;
        mean reversion pulls them back toward the shared midpoint.
        """
        # Shared market move (all pools move together most of the time)
        market_return = random.gauss(0, self.volatility)
        self._midpoint *= 1 + market_return

        new_prices = []
        for i, p in enumerate(self._prices):
            # Idiosyncratic pool noise (creates the spread)
            idio = random.gauss(0, self.volatility * 0.25)
            # Mean reversion toward shared midpoint
            rev = self.mean_rev_spd * (self._midpoint - p) / self._midpoint
            # Hard-clamp: individual pool can't deviate > max_spread from mid
            raw = p * (1 + market_return + idio + rev)
            clamped = max(
                self._midpoint * (1 - self.max_spread),
                min(self._midpoint * (1 + self.max_spread), raw),
            )
            new_prices.append(clamped)

        self._prices = new_prices
        return list(self._prices)

    def get_quotes(self) -> list[PoolQuote]:
        """Return current PoolQuote for each pool."""
        quotes = []
        for i, price in enumerate(self._prices):
            spread = price * 0.0002  # tiny bid-ask within each pool
            quotes.append(
                PoolQuote(
                    pool_id=f"pool_{i+1}",
                    price=price,
                    bid=price - spread / 2,
                    ask=price + spread / 2,
                    fee_pct=self.fee_pcts[i % len(self.fee_pcts)],
                )
            )
        return quotes

    @property
    def spread_pct(self) -> float:
        """Current max spread between any two pools (%)."""
        if len(self._prices) < 2:
            return 0.0
        return (max(self._prices) - min(self._prices)) / min(self._prices) * 100

    @property
    def midpoint(self) -> float:
        return self._midpoint


def route_to_best_pool(
    quotes: list[PoolQuote],
    side: str,  # "harvest" (sell) | "fold" (buy)
) -> PoolRoutingDecision:
    """
    Given N pool quotes, return the optimal execution pool for the
    accumulation operation.

    HARVEST → use the pool with the highest BID (sell into)
    FOLD    → use the pool with the lowest ASK (buy from)
    """
    if not quotes:
        raise ValueError("No quotes provided")

    if side == "harvest":
        best = max(quotes, key=lambda q: q.bid)
        worst = min(quotes, key=lambda q: q.bid)
        best_price = best.bid
        worst_price = worst.bid
    else:
        best = min(quotes, key=lambda q: q.ask)
        worst = max(quotes, key=lambda q: q.ask)
        best_price = best.ask
        worst_price = worst.ask

    spread_pct = abs(best_price - worst_price) / max(worst_price, 1e-9) * 100

    # Net advantage: spread minus round-trip fees on BOTH pools
    fee_cost = (best.fee_pct + worst.fee_pct) * 100  # as pct
    net_adv = spread_pct - fee_cost

    return PoolRoutingDecision(
        side=side,
        best_pool=best.pool_id,
        best_price=best_price,
        worst_price=worst_price,
        spread_pct=round(spread_pct, 5),
        net_advantage=round(net_adv, 5),
        pools_checked=len(quotes),
        is_profitable=net_adv > 0,
    )


# ═══════════════════════════════════════════════════════════════
# CORE SIMULATOR — accumulation with cross-pool routing
# ═══════════════════════════════════════════════════════════════


def run_cross_pool_sim(
    candles: list,  # list of base prices (close prices)
    n_pools: int = 3,
    target: float = 200.0,
    hedge: float = 200.0,
    interval_pct: float = 2.0,
    fee_pct: float = 0.001,
    max_spread: float = 0.25,  # max pool spread %
    mean_rev_spd: float = 0.04,
    seed: int = 42,
    pool_fees: list = None,
) -> dict:
    """
    Run the accumulation cycle with cross-pool price routing.

    For each candle:
      1. Generate N pool prices from the base candle price
      2. On scrum: route harvest to highest-bid pool
      3. On fold:  route fold to lowest-ask pool
      4. Record spread captured per cycle

    Returns a results dict comparable to run_v3192 output, plus
    cross-pool specific fields.
    """
    random.seed(seed)

    # v3.19.54 FIX (sadp R28 FL): early-return on empty candles. Pre-fix
    # the spread-model constructor would index candles[0] unconditionally
    # and raise IndexError on `run_cross_pool_sim([])`. Discovered by
    # tests/test_cross_pool_coverage.py::test_run_cross_pool_sim_empty_candles.
    if not candles:
        return {
            "win": False,
            "advantage": 0.0,
            "final": 0.0,
            "passive": 0.0,
            "pnl": 0.0,
            "trades": 0,
            "scrums": 0,
            "folds": 0,
            "hedge_trades": 0,
            "fees": 0.0,
            "target_growth": 0.0,
            "max_dd": 0.0,
            "n_pools": n_pools,
            "spread_total": 0.0,
            "spread_count": 0,
            "avg_spread_pct": 0.0,
            "avg_spread_bonus_usd": 0.0,
            "spread_captures": [],
            "cycle_results": [],
        }

    # Build pool fee schedule
    if pool_fees is None:
        pool_fees = [fee_pct] * n_pools

    # State
    holdings = target / candles[0] if candles else 0.0
    usd = hedge
    fold_q = 0.0
    fold_ref = 0.0
    sim_tgt = target

    trades = scrums = folds = hedge_trades = 0
    fees_paid = 0.0
    spread_total = 0.0
    spread_count = 0
    pnl = 0.0
    target_growth = 0.0
    max_dd = 0.0
    peak_val = target + hedge

    spread_captures: list[float] = []
    cycle_results: list[CrossPoolCycleResult] = []

    # BB state
    bb_window = 20
    close_buf: list[float] = []

    # Pool spread model — initialised at first candle price
    spread_model = CrossPoolSpreadModel(
        n_pools=n_pools,
        base_price=candles[0],
        max_spread=max_spread,
        mean_rev_spd=mean_rev_spd,
        volatility=0.004,
        fee_pcts=pool_fees,
        seed=seed,
    )

    for base_price in candles:
        # Step pool spread model to this candle's level
        # Nudge model midpoint toward base candle price then step
        spread_model._midpoint = base_price
        spread_model.step()
        quotes = spread_model.get_quotes()

        close_buf.append(base_price)
        if len(close_buf) > bb_window:
            close_buf.pop(0)

        # BB bands from base price series
        bb_lower = bb_upper = None
        if len(close_buf) >= bb_window:
            sma = sum(close_buf) / bb_window
            std = math.sqrt(sum((x - sma) ** 2 for x in close_buf) / bb_window)
            bb_lower = sma - 2 * std
            bb_upper = sma + 2 * std
            bb_width = bb_upper - bb_lower + 1e-12
            bb_pos = (base_price - bb_lower) / bb_width
        else:
            bb_pos = 0.5

        value = holdings * base_price
        delta = value - sim_tgt
        delta_pct = abs(delta) / (sim_tgt + 1e-9) * 100

        # ── SCRUM (harvest) ───────────────────────────────────
        if delta > 0 and delta_pct >= interval_pct and bb_pos > 0.50:
            scrum_qty = delta / base_price
            if scrum_qty > 0 and holdings >= scrum_qty:
                # Route to best pool for sell
                harvest_dec = route_to_best_pool(quotes, "harvest")
                exec_price = harvest_dec.best_price
                fee = scrum_qty * exec_price * fee_pct
                net_usd = scrum_qty * exec_price - fee
                holdings -= scrum_qty
                usd += net_usd
                fold_q = net_usd
                fold_ref = exec_price
                fees_paid += fee
                trades += 1
                scrums += 1
                spread_captures.append(harvest_dec.spread_pct)

        # ── FOLD ──────────────────────────────────────────────
        elif fold_q > 0 and bb_pos < 0.50 and base_price < fold_ref:
            # Route to best pool for buy
            fold_dec = route_to_best_pool(quotes, "fold")
            exec_price = fold_dec.best_price

            avail = min(fold_q, usd)
            if avail > 0.10:
                fee = avail * fee_pct
                qty_bought = (avail - fee) / exec_price
                # How much would we have bought at single-pool price?
                qty_single = (avail - fee) / base_price
                spread_bonus = (qty_bought - qty_single) * exec_price
                if spread_bonus < 0:
                    spread_bonus = 0

                at_ref = fold_q / fold_ref
                extra = qty_bought - at_ref
                profit = max(extra * exec_price, 0)

                holdings += qty_bought
                usd -= avail
                fold_q = 0.0
                fees_paid += fee
                trades += 1
                folds += 1
                spread_total += spread_bonus
                spread_count += 1

                if profit > 0:
                    sim_tgt += profit
                    target_growth += profit

                # Record cycle result
                cycle_results.append(
                    CrossPoolCycleResult(
                        harvest_pool=fold_dec.best_pool,  # fold is the closing leg
                        harvest_price=fold_ref,
                        fold_pool=fold_dec.best_pool,
                        fold_price=exec_price,
                        spread_captured=round(spread_bonus, 6),
                        spread_pct=round(fold_dec.spread_pct, 4),
                        base_profit=round(profit, 6),
                        total_profit=round(profit + spread_bonus, 6),
                        enhancement_pct=(
                            round(spread_bonus / max(profit, 0.0001) * 100, 2)
                            if profit > 0
                            else 0.0
                        ),
                    )
                )

        # ── HEDGE ─────────────────────────────────────────────
        elif (
            delta < 0
            and usd > 1
            and bb_pos < 0.40
            and abs(delta) / (sim_tgt + 1e-9) > 0.01
        ):
            use = min(usd * 0.5, abs(delta))
            fold_dec = route_to_best_pool(quotes, "fold")
            exec_price = fold_dec.best_price
            fee = use * fee_pct
            qty = (use - fee) / exec_price
            holdings += qty
            usd -= use
            fees_paid += fee
            trades += 1
            hedge_trades += 1

        # Portfolio tracking
        port = holdings * base_price + usd + fold_q
        if port > peak_val:
            peak_val = port
        dd = (peak_val - port) / peak_val * 100
        if dd > max_dd:
            max_dd = dd

    final_price = candles[-1] if candles else 0
    final_port = holdings * final_price + usd + fold_q
    passive = (target / candles[0] if candles else 0) * final_price + hedge
    pnl = final_port - (target + hedge)
    adv = final_port - passive

    avg_spread = sum(spread_captures) / len(spread_captures) if spread_captures else 0.0
    avg_spread_bonus = spread_total / max(spread_count, 1)

    return {
        "win": adv > 0,
        "advantage": round(adv, 4),
        "final": round(final_port, 4),
        "passive": round(passive, 4),
        "pnl": round(pnl, 4),
        "trades": trades,
        "scrums": scrums,
        "folds": folds,
        "hedge_trades": hedge_trades,
        "fees": round(fees_paid, 4),
        "target_growth": round(target_growth, 4),
        "max_dd": round(max_dd, 2),
        "n_pools": n_pools,
        "spread_total": round(spread_total, 4),
        "spread_count": spread_count,
        "avg_spread_pct": round(avg_spread, 4),
        "avg_spread_bonus_usd": round(avg_spread_bonus, 6),
        "spread_captures": spread_captures,
        "cycle_results": cycle_results,
    }


# ═══════════════════════════════════════════════════════════════
# BENCHMARK — single vs multi-pool comparison
# ═══════════════════════════════════════════════════════════════


def run_cross_pool_benchmark(
    candles: list,
    pool_counts: list = None,  # e.g. [1, 2, 3, 5, 10]
    fee_pct: float = 0.001,
    max_spread: float = 0.25,
    target: float = 200.0,
    hedge: float = 200.0,
    interval_pct: float = 2.0,
    seed: int = 42,
    verbose: bool = True,
) -> list[dict]:
    """
    Run the same simulation at different pool counts and compare.
    Measures how much cross-pool routing improves over single-pool baseline.

    Returns list of result dicts, one per pool count.
    """
    if pool_counts is None:
        pool_counts = [1, 2, 3, 5, 10]

    results = []
    baseline_adv = None

    for n in pool_counts:
        r = run_cross_pool_sim(
            candles=candles,
            n_pools=n,
            target=target,
            hedge=hedge,
            interval_pct=interval_pct,
            fee_pct=fee_pct,
            max_spread=max_spread,
            seed=seed,
        )

        if n == 1:
            baseline_adv = r["advantage"]

        improvement = 0.0
        if baseline_adv is not None and baseline_adv != 0:
            improvement = (r["advantage"] - baseline_adv) / abs(baseline_adv) * 100

        r["pools"] = n
        r["improvement_vs_single_pct"] = round(improvement, 2)
        results.append(r)

        if verbose:
            sym = "✓" if r["win"] else "✗"
            print(
                f"  Pools: {n:2d} | {sym} | "
                f"Adv: ${r['advantage']:>+8,.2f} | "
                f"Spread bonus: ${r['spread_total']:>6,.4f} | "
                f"Avg spread: {r['avg_spread_pct']:.4f}% | "
                f"+{improvement:+.1f}% vs 1-pool"
            )

    return results


def analyze_pool_configuration(
    candle_data: dict,  # {symbol: [close prices]}
    fee_pct: float = 0.001,
    max_spread: float = 0.25,
    verbose: bool = True,
) -> dict:
    """
    Full cross-pool profitability analysis across assets.

    For each asset, runs [1, 2, 3, 5, 10] pool configurations and
    summarises the marginal advantage per additional pool.

    Returns a summary dict with per-asset and aggregate findings.
    """
    summary = {}

    if verbose:
        print("=" * 72)
        print("  CROSS-POOL ACCUMULATION ADVANTAGE ANALYSIS")
        print("  Acervator — by Anthony L. Brown (Ekthelius)")
        print("=" * 72)

    total_improvement_3pool = []
    total_improvement_5pool = []
    total_improvement_10pool = []

    for symbol, closes in candle_data.items():
        if len(closes) < 50:
            continue
        if verbose:
            print(f"\n  {symbol}  ({len(closes)} candles):")
            print("  " + "─" * 60)

        results = run_cross_pool_benchmark(
            candles=closes,
            fee_pct=fee_pct,
            max_spread=max_spread,
            verbose=verbose,
            seed=hash(symbol) % 99999,
        )

        by_pools = {r["pools"]: r for r in results}
        baseline = by_pools.get(1, {})
        three = by_pools.get(3, {})
        five = by_pools.get(5, {})
        ten = by_pools.get(10, {})

        imp3 = three.get("improvement_vs_single_pct", 0)
        imp5 = five.get("improvement_vs_single_pct", 0)
        imp10 = ten.get("improvement_vs_single_pct", 0)

        total_improvement_3pool.append(imp3)
        total_improvement_5pool.append(imp5)
        total_improvement_10pool.append(imp10)

        summary[symbol] = {
            "single_pool_adv": baseline.get("advantage", 0),
            "3_pool_adv": three.get("advantage", 0),
            "5_pool_adv": five.get("advantage", 0),
            "10_pool_adv": ten.get("advantage", 0),
            "improvement_3p": imp3,
            "improvement_5p": imp5,
            "improvement_10p": imp10,
            "avg_spread_10p": ten.get("avg_spread_pct", 0),
        }

    if total_improvement_3pool and verbose:
        print()
        print("=" * 72)
        print("  AGGREGATE FINDINGS")
        print("─" * 72)
        avg3 = sum(total_improvement_3pool) / len(total_improvement_3pool)
        avg5 = sum(total_improvement_5pool) / len(total_improvement_5pool)
        avg10 = sum(total_improvement_10pool) / len(total_improvement_10pool)
        print("  Average improvement vs single pool:")
        print(f"    3  pools: {avg3:+.2f}%")
        print(f"    5  pools: {avg5:+.2f}%")
        print(f"    10 pools: {avg10:+.2f}%")
        print("=" * 72)

    summary["_aggregate"] = {
        "avg_improvement_3p": (
            sum(total_improvement_3pool) / max(len(total_improvement_3pool), 1)
        ),
        "avg_improvement_5p": (
            sum(total_improvement_5pool) / max(len(total_improvement_5pool), 1)
        ),
        "avg_improvement_10p": (
            sum(total_improvement_10pool) / max(len(total_improvement_10pool), 1)
        ),
    }
    return summary


# ═══════════════════════════════════════════════════════════════
# MULTI-BOT COORDINATION
# ═══════════════════════════════════════════════════════════════


class CrossPoolSwarm:
    """
    Coordinates multiple bots watching different pools.

    Bot A monitors pool_high → specialised for harvest operations
    Bot B monitors pool_low  → specialised for fold operations
    Smart Wire routes fold queue from A to B automatically.

    This is the multi-bot configuration Anthony described: rather than
    one bot trying to route to both sides, two dedicated bots maximise
    both legs independently.
    """

    def __init__(self, n_bots: int = 2, fee_pct: float = 0.001):
        self.n_bots = n_bots
        self.fee_pct = fee_pct
        self._bot_balances = [{"usd": 200.0, "asset": 0.0} for _ in range(n_bots)]
        self._wire_queue: list[dict] = []  # cross-bot routing queue
        self._total_spread_captured = 0.0
        self._total_cycles = 0

    def assign_pools(self, quotes: list[PoolQuote]) -> dict:
        """
        Assign bots to pools.
        Bot 0 → highest bid pool (harvest specialist)
        Bot 1 → lowest ask pool (fold specialist)
        Bot 2+ → mid pools (general purpose)
        """
        if not quotes:
            return {}
        sorted_by_bid = sorted(quotes, key=lambda q: q.bid, reverse=True)
        sorted_by_ask = sorted(quotes, key=lambda q: q.ask)
        assignments = {}
        if self.n_bots >= 1:
            assignments[0] = sorted_by_bid[0]  # harvest specialist
        if self.n_bots >= 2:
            assignments[1] = sorted_by_ask[0]  # fold specialist
        for i in range(2, self.n_bots):
            assignments[i] = quotes[i % len(quotes)]
        return assignments

    def route_wire(self, from_bot: int, amount_usd: float) -> bool:
        """Route fold queue from harvest bot to fold bot via Smart Wire."""
        if from_bot == 0 and self.n_bots >= 2:
            self._wire_queue.append({"from": from_bot, "to": 1, "amount": amount_usd})
            return True
        return False

    def settle_wires(self) -> float:
        """Process pending wire transfers between bots."""
        total = sum(w["amount"] for w in self._wire_queue)
        self._wire_queue.clear()
        return total

    @property
    def total_spread_captured(self) -> float:
        return self._total_spread_captured

    def get_summary(self) -> dict:
        return {
            "n_bots": self.n_bots,
            "cycles": self._total_cycles,
            "spread_captured_total": round(self._total_spread_captured, 4),
            "spread_per_cycle": round(
                self._total_spread_captured / max(self._total_cycles, 1), 6
            ),
        }
