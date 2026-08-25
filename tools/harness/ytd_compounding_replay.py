"""YTD compounding-replay analyzer (v3.23.29).

Reads a Coinbase Advanced Trade YTD CSV, per-asset walks the buy/sell
timeline, detects fold-back opportunities (BUY after prior SELL at a
higher price on the same asset), and computes what the v3.23.7
surplus-drain formula WOULD have contributed to `_target_balance`
compounding at each event.

The math applied per matched buy-back event mirrors
`src/trading/scrumming_bot.py`:
    extra_asset  = matched_sell_units * (sell_price - buy_price) / buy_price
    accum_profit = extra_asset * buy_price
                 = matched_sell_units * (sell_price - buy_price)   # US$
    surplus_usd  = max(0.0, accum_profit)   # quote_to_usd assumed 1.0 (USD pair)
    growth_applied = min(surplus_usd,
                         anchor * (max_target_growth_pct/100)
                         - cycle_consumed)
    target_balance += growth_applied
    cycle_consumed += growth_applied

Cycle reset heuristic: `cycle_consumed` resets to 0 on the NEXT SELL
event per asset. This mirrors the v3.16.56 operator directive: "Cap
resets on SCRUM event OR D2-b asymmetric BB-extreme touch." Since the
CSV has no BB signal, the SELL-side reset is the honest approximation.

Honest limitations:
  - Cannot distinguish "bot fold-back BUY" from "manual fresh BUY" or
    "Extractor pool BUY" from CSV alone. Analyzer is an UPPER BOUND —
    it treats every buy-back-below-prior-sell-price as a candidate.
  - Live bot state (`_fold_tranches`, `_fold_cycle_cap_consumed`,
    `profit_folding_active`) not visible in CSV. Analyzer assumes:
      target_balance = $200, max_target_growth_pct = 1%,
      profit_folding_active = True.
  - Fees ignored (matches bot's pre-fee accum_profit).

Interpretation:
  - Upper bound > $0 → v3.23.7 fix would grow target on real data.
    Live bot's no-compound observation has a state-level cause;
    forensic on bot_state.json needed.
  - Upper bound = $0 → v3.23.7 fix is theatrical. Real trade shapes
    don't feed the code path even in theory.

FALSIFICATION: analyzer is wrong if (a) CSV parse skips rows silently
without logging, (b) FIFO matching pairs buys against wrong sells,
(c) the surplus formula diverges from scrumming_bot.py's actual math,
(d) cycle reset heuristic overstates growth by resetting more often
than the real bot would.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


_MONEY_RE = re.compile(r"[$,\s]")


def _parse_money(raw: str) -> float:
    """Coinbase CSV money field: '$0.002009' or '-$5.08679' or '' → float."""
    s = (raw or "").strip()
    if not s or s == "-":
        return 0.0
    negative = s.startswith("-")
    s = _MONEY_RE.sub("", s.lstrip("-"))
    try:
        return -float(s) if negative else float(s)
    except ValueError:
        return 0.0


def _parse_qty(raw: str) -> float:
    """Quantity Transacted: '-2532' (sell) or '2532' (buy) → float."""
    s = (raw or "").strip().replace(",", "")
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


@dataclass
class Trade:
    ts: datetime
    side: str  # "BUY" or "SELL"
    asset: str
    qty: float  # always positive (absolute)
    price: float  # USD per unit


def parse_coinbase_csv(path: Path) -> list[Trade]:
    """Skip the 3 header rows, DictReader the rest, keep only
    Advanced Trade Buy/Sell rows on USD-quoted pairs."""
    trades: list[Trade] = []
    with path.open("r", encoding="utf-8") as fh:
        for _ in range(3):
            next(fh, None)
        reader = csv.DictReader(fh)
        for row in reader:
            ttype = (row.get("Transaction Type") or "").strip()
            if ttype not in ("Advanced Trade Buy", "Advanced Trade Sell"):
                continue
            if (row.get("Price Currency") or "").strip() != "USD":
                continue
            asset = (row.get("Asset") or "").strip()
            if not asset:
                continue
            side = "BUY" if ttype.endswith("Buy") else "SELL"
            qty_raw = _parse_qty(row.get("Quantity Transacted", ""))
            qty = abs(qty_raw)
            price = _parse_money(row.get("Price at Transaction", ""))
            if qty <= 0 or price <= 0:
                continue
            ts_raw = (row.get("Timestamp") or "").strip()
            try:
                # Format: "2026-07-26 22:00:24 UTC"
                ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S UTC")
            except ValueError:
                continue
            trades.append(Trade(ts=ts, side=side, asset=asset, qty=qty, price=price))
    return trades


# ---------------------------------------------------------------------------
# Per-asset replay
# ---------------------------------------------------------------------------


@dataclass
class AssetResult:
    asset: str
    total_buys: int = 0
    total_sells: int = 0
    fold_back_events: int = 0  # matched-buy events with buy < sell
    surplus_generated_usd: float = 0.0  # sum of raw pre-cap surplus
    growth_applied_usd: float = 0.0  # sum of growth after cap
    cap_hits: int = 0  # events where cap limited the drain
    largest_single_growth_usd: float = 0.0
    final_target_balance: float = 200.0  # starts at simulated anchor
    events: list[dict] = field(default_factory=list)


def replay_asset(
    trades: list[Trade],
    initial_target: float = 200.0,
    max_target_growth_pct: float = 1.0,
) -> AssetResult:
    """FIFO-match one asset's trade stream, compute per-event surplus
    + growth per v3.23.7 formula, track running target balance."""
    if not trades:
        return AssetResult(asset="?")
    asset = trades[0].asset
    r = AssetResult(asset=asset, final_target_balance=initial_target)
    anchor = initial_target
    cycle_consumed = 0.0
    # FIFO queue of open sells: (remaining_qty, sell_price, ts)
    sell_queue: deque[tuple[float, float, datetime]] = deque()

    for trade in trades:
        if trade.side == "SELL":
            r.total_sells += 1
            sell_queue.append((trade.qty, trade.price, trade.ts))
            # Cycle-reset heuristic: SELL event resets the growth cap
            cycle_consumed = 0.0
            continue

        # BUY: FIFO-match against open sells, capturing surplus per matched slice
        r.total_buys += 1
        remaining_buy_qty = trade.qty
        event_surplus_total = 0.0
        matched_any = False
        matched_at_lower_price = False

        while remaining_buy_qty > 1e-12 and sell_queue:
            sell_qty, sell_price, sell_ts = sell_queue[0]
            match_qty = min(remaining_buy_qty, sell_qty)
            matched_any = True
            if trade.price < sell_price:
                # This slice is a fold-back candidate
                per_unit_surplus = sell_price - trade.price
                slice_surplus = match_qty * per_unit_surplus
                event_surplus_total += slice_surplus
                matched_at_lower_price = True
            # Consume from FIFO queue
            new_sell_qty = sell_qty - match_qty
            if new_sell_qty <= 1e-12:
                sell_queue.popleft()
            else:
                sell_queue[0] = (new_sell_qty, sell_price, sell_ts)
            remaining_buy_qty -= match_qty

        # Unmatched BUY (fresh entry or exceeds prior sells) — not a fold-back
        # candidate; contributes no surplus.

        if not matched_at_lower_price:
            continue

        r.fold_back_events += 1
        r.surplus_generated_usd += event_surplus_total

        # Apply the cap
        cycle_cap_growth = anchor * (max_target_growth_pct / 100.0)
        cap_remaining = max(0.0, cycle_cap_growth - cycle_consumed)
        growth_applied = min(event_surplus_total, cap_remaining)
        if event_surplus_total > cap_remaining + 1e-9:
            r.cap_hits += 1
        r.growth_applied_usd += growth_applied
        r.final_target_balance += growth_applied
        cycle_consumed += growth_applied
        if growth_applied > r.largest_single_growth_usd:
            r.largest_single_growth_usd = growth_applied

        r.events.append(
            {
                "ts": trade.ts.isoformat(),
                "buy_price": trade.price,
                "buy_qty": trade.qty,
                "raw_surplus_usd": round(event_surplus_total, 6),
                "growth_applied_usd": round(growth_applied, 6),
                "cap_remaining_before": round(cap_remaining, 6),
                "target_after": round(r.final_target_balance, 6),
            }
        )

    return r


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def analyze(
    csv_path: Path, initial_target: float = 200.0, max_target_growth_pct: float = 1.0
) -> dict:
    trades = parse_coinbase_csv(csv_path)
    per_asset: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        per_asset[t.asset].append(t)
    # Sort each asset's stream by timestamp
    for a in per_asset:
        per_asset[a].sort(key=lambda t: t.ts)

    results = [
        replay_asset(per_asset[a], initial_target, max_target_growth_pct)
        for a in sorted(per_asset)
    ]

    total_fold_events = sum(r.fold_back_events for r in results)
    total_surplus = sum(r.surplus_generated_usd for r in results)
    total_growth = sum(r.growth_applied_usd for r in results)
    total_cap_hits = sum(r.cap_hits for r in results)
    total_buys = sum(r.total_buys for r in results)
    total_sells = sum(r.total_sells for r in results)

    window_start = min((t.ts for t in trades), default=None)
    window_end = max((t.ts for t in trades), default=None)

    summary = {
        "csv_path": str(csv_path),
        "csv_rows_parsed": len(trades),
        "csv_window": {
            "start": window_start.isoformat() if window_start else None,
            "end": window_end.isoformat() if window_end else None,
        },
        "assets_traded": len(results),
        "totals": {
            "buys": total_buys,
            "sells": total_sells,
            "fold_back_events": total_fold_events,
            "surplus_generated_usd": round(total_surplus, 6),
            "growth_applied_usd": round(total_growth, 6),
            "cap_hits": total_cap_hits,
        },
        "assumptions": {
            "initial_target_balance": initial_target,
            "max_target_growth_pct": max_target_growth_pct,
            "profit_folding_active": True,
            "quote_to_usd": 1.0,
            "cycle_reset_heuristic": "reset on next SELL per asset",
            "fees_included": False,
        },
        "per_asset": [
            {
                "asset": r.asset,
                "buys": r.total_buys,
                "sells": r.total_sells,
                "fold_back_events": r.fold_back_events,
                "surplus_generated_usd": round(r.surplus_generated_usd, 6),
                "growth_applied_usd": round(r.growth_applied_usd, 6),
                "cap_hits": r.cap_hits,
                "largest_single_growth_usd": round(r.largest_single_growth_usd, 6),
                "final_target_balance": round(r.final_target_balance, 6),
            }
            for r in results
        ],
    }
    return summary, results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ytd_compounding_replay")
    p.add_argument("csv", help="Path to Coinbase Advanced Trade YTD CSV")
    p.add_argument(
        "--out",
        default="docs/audits/2026-07-25_ytd_compounding_replay",
        help="Output directory for JSON + per-asset events",
    )
    p.add_argument("--initial-target", type=float, default=200.0)
    p.add_argument("--max-growth-pct", type=float, default=1.0)
    args = p.parse_args(argv)

    csv_path = Path(args.csv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary, results = analyze(
        csv_path,
        initial_target=args.initial_target,
        max_target_growth_pct=args.max_growth_pct,
    )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (out_dir / "per_asset_events.json").write_text(
        json.dumps({r.asset: r.events for r in results if r.events}, indent=2),
        encoding="utf-8",
    )

    # Terminal summary
    t = summary["totals"]
    print(f"YTD compounding replay — v3.23.7 surplus formula")
    print(f"  CSV:            {summary['csv_path']}")
    print(
        f"  Window:         {summary['csv_window']['start']} → {summary['csv_window']['end']}"
    )
    print(f"  Assets traded:  {summary['assets_traded']}")
    print(f"  Buys:           {t['buys']:,}")
    print(f"  Sells:          {t['sells']:,}")
    print(f"  Fold-back events: {t['fold_back_events']:,}")
    print(f"  Surplus generated (pre-cap): ${t['surplus_generated_usd']:,.4f}")
    print(f"  Target growth applied:       ${t['growth_applied_usd']:,.4f}")
    print(f"  Cycle-cap hits:              {t['cap_hits']:,}")
    print()
    print(f"  Top-5 assets by growth applied:")
    top = sorted(summary["per_asset"], key=lambda x: -x["growth_applied_usd"])[:5]
    for r in top:
        print(
            f"    {r['asset']:>8s}  fb={r['fold_back_events']:>4d}  "
            f"surplus=${r['surplus_generated_usd']:>9.4f}  "
            f"growth=${r['growth_applied_usd']:>9.4f}  "
            f"target=${r['final_target_balance']:>9.4f}"
        )
    print()
    print(f"  Output: {out_dir}/summary.json")
    print(f"          {out_dir}/per_asset_events.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
