"""parity_harness.py — sim decisions vs actual live trades.

Operator directive 2026-08-01:

    "We have never been able to get the sim to match live by
    playing back Stone Tablets and checking simulator trade logic
    against historical trades that actually were initiated by the
    platform. It must be able to play the entire 5m historical
    tape for every traded asset detected in the YTD data. The
    simulated bots must replicate the historical trade logic that
    would result in the historical trade being triggered. This
    must not be a forced or tweaked result from the simulated
    bots but an actual matched response that verifies the
    strategy."

This module is the yardstick — it measures parity between sim
output and real history so we can SEE whether the strategy
actually reproduces.

Contract:

    live_trades  = fetch_all_history_chunked(bot_manager, since_ts)
                   returns list[dict] with keys:
                     {timestamp (unix sec), symbol, side, amount,
                      price, exchange, ...}

    sim_trades   = list[Trade] from FleetSimExchange._trades
                   with .symbol, .side (OrderSide enum),
                   .amount, .timestamp (unix sec from master clock)

    tolerance_s  = time window a sim trade can drift from live
                   and still count as matched. Default 300s (one
                   5m candle) — a sim decision on the same tablet
                   tick can settle up to a candle late (Coinbase
                   fills happen mid-candle in real life).

Output: ParityReport with:
    matched         : list of (live_trade, sim_trade) pairs
    live_only       : live trades with no sim match (sim UNDER-triggered)
    sim_only        : sim trades with no live match (sim OVER-triggered)
    counts          : matched / live_only / sim_only aggregates
    per_symbol      : dict[symbol] → counts

The report is deliberately structural — the operator (or a follow-on
tool) reads it to see which specific divergences deserve investigation
in the bot's gate chain vs the tablet content.

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("acervator.stone_tablets.parity_harness")

DEFAULT_TOLERANCE_S: float = 300.0  # one 5m candle


@dataclass
class ParityMatch:
    live_ts: float
    sim_ts: float
    symbol: str
    side: str
    live_amount: float
    sim_amount: float
    drift_s: float


@dataclass
class ParityReport:
    matched: list[ParityMatch] = field(default_factory=list)
    live_only: list[dict] = field(default_factory=list)  # unmatched live trades
    sim_only: list[Any] = field(default_factory=list)  # unmatched sim trades
    tolerance_s: float = DEFAULT_TOLERANCE_S
    window_since_ts: float = 0.0
    window_until_ts: float = 0.0

    @property
    def total_live(self) -> int:
        return len(self.matched) + len(self.live_only)

    @property
    def total_sim(self) -> int:
        return len(self.matched) + len(self.sim_only)

    @property
    def match_rate(self) -> float:
        """0.0-100.0 percent of live trades that had a sim match."""
        if self.total_live == 0:
            return 0.0
        return 100.0 * len(self.matched) / self.total_live

    def per_symbol_counts(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for m in self.matched:
            d = out.setdefault(m.symbol, {"matched": 0, "live_only": 0, "sim_only": 0})
            d["matched"] += 1
        for lt in self.live_only:
            sym = str(lt.get("symbol", ""))
            d = out.setdefault(sym, {"matched": 0, "live_only": 0, "sim_only": 0})
            d["live_only"] += 1
        for st in self.sim_only:
            sym = str(getattr(st, "symbol", ""))
            d = out.setdefault(sym, {"matched": 0, "live_only": 0, "sim_only": 0})
            d["sim_only"] += 1
        return out


def _live_side_str(trade: dict) -> str:
    s = str(trade.get("side", "")).upper()
    return "BUY" if "BUY" in s else "SELL" if "SELL" in s else s


def _sim_side_str(trade: Any) -> str:
    """OrderSide enum → 'BUY'/'SELL' — tolerates raw strings too."""
    side = getattr(trade, "side", None)
    val = getattr(side, "value", side)
    s = str(val).upper()
    return "BUY" if "BUY" in s else "SELL" if "SELL" in s else s


def compare_trades(
    live_trades: list[dict],
    sim_trades: list[Any],
    tolerance_s: float = DEFAULT_TOLERANCE_S,
    window_since_ts: float = 0.0,
    window_until_ts: float = 0.0,
) -> ParityReport:
    """Greedy nearest-timestamp match. For each live trade, find the
    closest-in-time unmatched sim trade on the same symbol + side
    within ``tolerance_s`` seconds. First-come-first-served; ties
    broken by earliest sim timestamp.

    Complexity: O(L * S) worst case (L=live count, S=sim count).
    Fine for YTD-scale trade counts (thousands). If it grows to
    hundreds of thousands, sort + two-pointer merge is O(L+S).
    """
    report = ParityReport(
        tolerance_s=float(tolerance_s),
        window_since_ts=float(window_since_ts),
        window_until_ts=float(window_until_ts),
    )
    # Filter to window if provided (both bounds > 0)
    if window_since_ts > 0 or window_until_ts > 0:
        live_trades = [
            t
            for t in live_trades
            if (window_since_ts <= 0 or float(t.get("timestamp", 0)) >= window_since_ts)
            and (
                window_until_ts <= 0 or float(t.get("timestamp", 0)) <= window_until_ts
            )
        ]
        sim_trades = [
            t
            for t in sim_trades
            if (
                window_since_ts <= 0
                or float(getattr(t, "timestamp", 0)) >= window_since_ts
            )
            and (
                window_until_ts <= 0
                or float(getattr(t, "timestamp", 0)) <= window_until_ts
            )
        ]

    # Index sim trades by (symbol, side) for cheap lookup + track
    # which sim trades have been consumed.
    sim_by_key: dict[tuple[str, str], list[tuple[float, Any]]] = {}
    for st in sim_trades:
        sym = str(getattr(st, "symbol", ""))
        side = _sim_side_str(st)
        ts = float(getattr(st, "timestamp", 0))
        sim_by_key.setdefault((sym, side), []).append((ts, st))
    for lst in sim_by_key.values():
        lst.sort(key=lambda p: p[0])
    consumed: set[int] = set()  # ids of consumed sim Trade objects

    for lt in live_trades:
        sym = str(lt.get("symbol", ""))
        side = _live_side_str(lt)
        live_ts = float(lt.get("timestamp", 0))
        candidates = sim_by_key.get((sym, side), [])
        best_i = -1
        best_drift = float("inf")
        for i, (sim_ts, st) in enumerate(candidates):
            if id(st) in consumed:
                continue
            drift = abs(sim_ts - live_ts)
            if drift > tolerance_s:
                continue
            if drift < best_drift:
                best_drift = drift
                best_i = i
        if best_i >= 0:
            sim_ts, st = candidates[best_i]
            consumed.add(id(st))
            report.matched.append(
                ParityMatch(
                    live_ts=live_ts,
                    sim_ts=sim_ts,
                    symbol=sym,
                    side=side,
                    live_amount=float(lt.get("amount", 0)),
                    sim_amount=float(getattr(st, "amount", 0)),
                    drift_s=sim_ts - live_ts,
                )
            )
        else:
            report.live_only.append(lt)

    # Anything not consumed = sim_only
    for (sym, side), lst in sim_by_key.items():
        for _ts, st in lst:
            if id(st) not in consumed:
                report.sim_only.append(st)

    return report


def format_report_lines(report: ParityReport, max_examples: int = 5) -> list[str]:
    """Human-readable summary — one line per top-level metric, then
    per-symbol matrix, then divergence examples. Meant to be piped
    into the Simulator Activity Log."""
    lines: list[str] = []
    lines.append(
        f"Parity: {len(report.matched):,} matched | "
        f"{len(report.live_only):,} live-only (sim under-triggered) | "
        f"{len(report.sim_only):,} sim-only (sim over-triggered)"
    )
    lines.append(
        f"Match rate: {report.match_rate:.1f}% of live trades "
        f"(tolerance ±{report.tolerance_s:.0f}s)"
    )
    if report.total_live == 0 and report.total_sim == 0:
        lines.append("(no trades in either set — nothing to compare)")
        return lines
    per_sym = report.per_symbol_counts()
    lines.append(f"Per-symbol matrix ({len(per_sym)} symbols):")
    _sorted = sorted(
        per_sym.items(), key=lambda kv: -(kv[1]["matched"] + kv[1]["live_only"])
    )
    for sym, counts in _sorted[:15]:
        lines.append(
            f"  {sym:<12} matched={counts['matched']:>4}  "
            f"live_only={counts['live_only']:>4}  "
            f"sim_only={counts['sim_only']:>4}"
        )
    if len(_sorted) > 15:
        lines.append(f"  ... and {len(_sorted) - 15} more")
    if report.live_only:
        lines.append(
            f"Live-only examples (first {min(max_examples, len(report.live_only))}):"
        )
        for lt in report.live_only[:max_examples]:
            import time as _t

            ts = float(lt.get("timestamp", 0))
            dt = _t.strftime("%Y-%m-%d %H:%M", _t.gmtime(ts)) if ts else "-"
            lines.append(
                f"  {dt}  {lt.get('symbol', ''):<10} "
                f"{_live_side_str(lt):<4} amt={float(lt.get('amount', 0)):.6f}"
            )
    return lines


__all__ = [
    "DEFAULT_TOLERANCE_S",
    "ParityMatch",
    "ParityReport",
    "compare_trades",
    "format_report_lines",
]
