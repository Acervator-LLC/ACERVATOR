# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Cross-pool routing for the harvest-fold cycle.

``route_to_best_pool`` sends a harvest to the highest ``PoolQuote.bid`` and a
fold to the lowest ``PoolQuote.ask``, reporting the gap as ``spread_pct``.
``CrossPoolSpreadModel`` generates the correlated pool prices that
``run_cross_pool_sim`` trades against. ``run_cross_pool_benchmark`` and
``analyze_pool_configuration`` repeat that sim across pool counts and assets.
"""

from __future__ import annotations

import math
import random
import logging
from dataclasses import dataclass

log = logging.getLogger("acervator.cross_pool")


@dataclass
class PoolQuote:
    """One pool's ``bid``, ``ask`` and ``fee_pct`` at one candle."""

    pool_id: str
    price: float
    bid: float
    ask: float
    fee_pct: float = 0.001  # a fraction, not a percent: 0.001 is 0.10%


@dataclass
class PoolRoutingDecision:
    """What ``route_to_best_pool`` chose for one side.

    Nothing reads ``is_profitable`` or ``net_advantage``; ``run_cross_pool_sim``
    executes at ``best_price`` whatever they say.
    """

    side: str  # "harvest" | "fold"
    best_pool: str
    best_price: float
    worst_price: float
    spread_pct: float  # abs(best_price - worst_price) / worst_price × 100
    net_advantage: float  # spread_pct less both pools' fee_pct, in percent
    pools_checked: int
    is_profitable: bool


@dataclass
class CrossPoolCycleResult:
    """One scrum-then-fold pair recorded by ``run_cross_pool_sim``.

    ``harvest_price`` is the bid the scrum filled at and ``fold_price`` the ask
    the fold filled at.
    """

    harvest_pool: str
    harvest_price: float
    fold_pool: str
    fold_price: float
    spread_captured: float  # USD gained vs a buy at the close, never below 0
    spread_pct: float  # spread_pct of the fold routing decision
    base_profit: float  # units gained over a buyback at harvest_price, in USD
    total_profit: float
    enhancement_pct: float  # spread_captured as a percent of base_profit


class CrossPoolSpreadModel:
    """N correlated pool prices for one asset, advanced by ``step``.

    ``max_spread`` arrives as a percent and is stored as a fraction; ``mean_rev_spd``
    and ``volatility`` are fractions already.
    """

    def __init__(
        self,
        n_pools: int = 3,
        base_price: float = 65000.0,
        max_spread: float = 0.30,
        mean_rev_spd: float = 0.04,
        volatility: float = 0.004,
        fee_pcts: list = None,
        seed: int = None,
    ):

        self.n_pools = n_pools
        self.base_price = base_price
        self.max_spread = max_spread / 100
        self.mean_rev_spd = mean_rev_spd
        self.volatility = volatility

        self.fee_pcts = fee_pcts or [0.001] * n_pools

        if seed is not None:
            random.seed(seed)

        self._prices = [
            base_price * (1 + random.gauss(0, self.max_spread * 0.3))
            for _ in range(n_pools)
        ]
        self._midpoint = base_price

    def step(self) -> list[float]:
        """Advance every pool price one candle and return the new list.

        Each price takes the shared ``market_return``, its own ``idio`` noise and
        a pull ``rev`` toward ``_midpoint``.
        """
        market_return = random.gauss(0, self.volatility)
        self._midpoint *= 1 + market_return

        new_prices = []
        for i, p in enumerate(self._prices):
            idio = random.gauss(0, self.volatility * 0.25)
            rev = self.mean_rev_spd * (self._midpoint - p) / self._midpoint
            # No pool may end further than max_spread from _midpoint.
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
            spread = price * 0.0002  # 2 bps total, split either side of price
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
        """Gap between the highest and lowest of ``_prices``, in percent."""
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
    """Pick the execution pool for one leg and measure the gap to the worst.

    A ``side`` of ``"harvest"`` takes the highest ``bid``; every other value
    takes the lowest ``ask``.
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

    # Both pools' fee_pct in percent, matching the scale of spread_pct.
    fee_cost = (best.fee_pct + worst.fee_pct) * 100
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


def run_cross_pool_sim(
    candles: list,  # close prices
    n_pools: int = 3,
    target: float = 200.0,
    hedge: float = 200.0,
    interval_pct: float = 2.0,
    fee_pct: float = 0.001,
    max_spread: float = 0.25,  # percent
    mean_rev_spd: float = 0.04,
    seed: int = 42,
    pool_fees: list = None,
) -> dict:
    """Run the scrum-fold cycle over ``candles``, routing each leg to a pool.

    Every candle drives ``CrossPoolSpreadModel.step``, then at most one of the
    scrum, fold and hedge branches fires.
    """
    random.seed(seed)

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

    if pool_fees is None:
        pool_fees = [fee_pct] * n_pools

    holdings = target / candles[0] if candles else 0.0
    usd = hedge
    fold_q = 0.0
    fold_ref = 0.0
    fold_ref_pool = ""
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

    bb_window = 20
    close_buf: list[float] = []

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
        # A candle move above max_spread clamps every pool to one band edge.
        spread_model._midpoint = base_price
        spread_model.step()
        quotes = spread_model.get_quotes()

        close_buf.append(base_price)
        if len(close_buf) > bb_window:
            close_buf.pop(0)

        # Bands come from base_price, never from the routed pool prices.
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

        if delta > 0 and delta_pct >= interval_pct and bb_pos > 0.50:
            scrum_qty = delta / base_price
            if scrum_qty > 0 and holdings >= scrum_qty:
                harvest_dec = route_to_best_pool(quotes, "harvest")
                exec_price = harvest_dec.best_price
                fee = scrum_qty * exec_price * fee_pct
                net_usd = scrum_qty * exec_price - fee
                holdings -= scrum_qty
                usd += net_usd
                fold_q = net_usd
                fold_ref = exec_price
                fold_ref_pool = harvest_dec.best_pool
                fees_paid += fee
                trades += 1
                scrums += 1
                spread_captures.append(harvest_dec.spread_pct)

        elif fold_q > 0 and bb_pos < 0.50 and base_price < fold_ref:
            fold_dec = route_to_best_pool(quotes, "fold")
            exec_price = fold_dec.best_price

            avail = min(fold_q, usd)
            if avail > 0.10:
                fee = avail * fee_pct
                qty_bought = (avail - fee) / exec_price
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

                cycle_results.append(
                    CrossPoolCycleResult(
                        harvest_pool=fold_ref_pool,
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


def run_cross_pool_benchmark(
    candles: list,
    pool_counts: list = None,
    fee_pct: float = 0.001,
    max_spread: float = 0.25,
    target: float = 200.0,
    hedge: float = 200.0,
    interval_pct: float = 2.0,
    seed: int = 42,
    verbose: bool = True,
) -> list[dict]:
    """Run ``run_cross_pool_sim`` once per entry in ``pool_counts``.

    ``improvement_vs_single_pct`` stays 0.0 for every result unless
    ``pool_counts`` contains 1, since only ``n == 1`` sets the baseline.
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
    """Benchmark every symbol in ``candle_data`` that has 50 candles or more.

    The returned dict holds one entry per symbol plus ``_aggregate``, which
    averages ``improvement_3p``, ``improvement_5p`` and ``improvement_10p``.
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


class CrossPoolSwarm:
    """Pool assignment and wire queueing for several bots.

    ``_total_spread_captured`` and ``_total_cycles`` are set once in
    ``__init__``, so ``total_spread_captured`` and ``get_summary`` always
    report zero.
    """

    def __init__(self, n_bots: int = 2, fee_pct: float = 0.001):
        self.n_bots = n_bots
        self.fee_pct = fee_pct
        self._bot_balances = [{"usd": 200.0, "asset": 0.0} for _ in range(n_bots)]
        self._wire_queue: list[dict] = []
        self._total_spread_captured = 0.0
        self._total_cycles = 0

    def assign_pools(self, quotes: list[PoolQuote]) -> dict:
        """Map bot index to a ``PoolQuote``.

        Bot 0 takes the highest bid and bot 1 the lowest ask; bot ``i`` above
        that takes ``quotes[i % len(quotes)]`` in the order given.
        """
        if not quotes:
            return {}
        sorted_by_bid = sorted(quotes, key=lambda q: q.bid, reverse=True)
        sorted_by_ask = sorted(quotes, key=lambda q: q.ask)
        assignments = {}
        if self.n_bots >= 1:
            assignments[0] = sorted_by_bid[0]
        if self.n_bots >= 2:
            assignments[1] = sorted_by_ask[0]
        for i in range(2, self.n_bots):
            assignments[i] = quotes[i % len(quotes)]
        return assignments

    def route_wire(self, from_bot: int, amount_usd: float) -> bool:
        """Queue ``amount_usd`` from bot 0 to bot 1 and report whether it queued.

        Any ``from_bot`` other than 0 returns False and queues nothing.
        """
        if from_bot == 0 and self.n_bots >= 2:
            self._wire_queue.append({"from": from_bot, "to": 1, "amount": amount_usd})
            return True
        return False

    def settle_wires(self) -> float:
        """Empty ``_wire_queue`` and return the total amount it held.

        No balance in ``_bot_balances`` moves.
        """
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
