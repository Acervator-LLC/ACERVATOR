"""Measure the Manual Fire target-frame split against live state.

Operator directive 2026-08-06:

    "Manual fire is not re-zeroing the bot to the Target Balance as
     expected and required. I am seeing strange, intermittent and hard
     to explain amounts being transacted when a Manual Fire is
     commanded."

WHAT IT COMPARES
Two target balances are persisted per bot:

    config.target_balance            the operator's setting
    scrumming_state.target_balance   the live value compounding writes

Manual Fire re-zeros the bot to "the Target Balance". Which one it
resolves to changes the order:

    delta_cfg  = position - config.target_balance
    delta_live = position - scrumming_state.target_balance

The gap between them is the unexplained amount. Where the two have
OPPOSITE SIGNS the bot buys under one reading and sells under the other,
which is the sharpest form of the operator's symptom.

WHY IT LOOKS INTERMITTENT
The gap equals accumulated compounding growth, so it is exactly $0.00 on
bots that have never compounded and grows with the ones that have.
Measured 2026-08-06: 26 of 35 bots diverged, 9 were clean, 4 inverted
direction, worst CAP/USD at 10.83% of target. A bot that behaves
perfectly on Monday and wrongly on Friday has not changed code -- it has
compounded once.

This tool does NOT decide which frame is correct. It measures the blast
radius of the disagreement. Read-only; constructs no project classes,
whose defaults resolve into the operator's runtime tree.

    python -m tools.harness.manual_fire_frame_check [--json] [--threshold 1.0]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _state_path() -> Path:
    return Path.home() / ".acervator" / "bot_state.json"


def analyse(state: dict) -> list[dict]:
    """One row per bot. Pure function so it is testable without a file."""
    out: list[dict] = []
    for rec in (state.get("bots") or {}).values():
        rec = rec or {}
        cfg = rec.get("config") or {}
        stats = rec.get("stats") or {}
        scrum = rec.get("scrumming_state") or {}
        lots = [x for x in (scrum.get("main_lots") or []) if isinstance(x, dict)]
        units = sum(float(x.get("units", 0) or 0) for x in lots)
        price = float(stats.get("current_price", 0) or 0)
        qrate = float(scrum.get("quote_to_usd", 1.0) or 1.0)
        position = units * price * qrate
        t_cfg = float(cfg.get("target_balance", 0) or 0)
        t_live = float(scrum.get("target_balance", 0) or 0)
        d_cfg = position - t_cfg
        d_live = position - t_live
        gap = abs(d_cfg - d_live)
        out.append(
            {
                "symbol": str(cfg.get("symbol", "?")),
                "position": position,
                "target_config": t_cfg,
                "target_live": t_live,
                "delta_if_config": d_cfg,
                "delta_if_live": d_live,
                "unexplained_usd": gap,
                # A sign flip means the two readings disagree on whether to
                # buy or sell -- not merely on how much.
                "direction_inverts": (d_cfg * d_live) < 0,
                "gap_pct_of_order": (
                    (gap / abs(d_cfg) * 100.0) if abs(d_cfg) > 1e-9 else float("inf")
                ),
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--threshold",
        type=float,
        default=0.005,
        help="USD gap above which a bot counts as diverging",
    )
    ap.add_argument("--state", type=Path, default=None)
    args = ap.parse_args(argv)

    path = args.state or _state_path()
    if not path.exists():
        print(f"state file not found: {path}", file=sys.stderr)
        return 2
    rows = analyse(json.loads(path.read_text(encoding="utf-8")))
    if not rows:
        print("no bots in state; nothing to analyse", file=sys.stderr)
        return 2

    # POSITIVE CONTROL. Every bot reporting a zero position means the
    # field layout moved and this tool is measuring nothing -- which
    # would otherwise render as "no divergence, all clear".
    if not any(r["position"] > 0 for r in rows):
        print(
            "INSTRUMENT FAILURE: every position recomputed to zero. The "
            "field layout has changed and this tool is measuring "
            "nothing. Do NOT read the output below as a pass.",
            file=sys.stderr,
        )
        return 3

    if args.json:
        print(json.dumps(rows, indent=2))
        return 1 if any(r["unexplained_usd"] > args.threshold for r in rows) else 0

    live = sum(1 for r in rows if r["position"] > 0)
    print(f"positive control: {live}/{len(rows)} bots have a live position\n")
    print(
        f"{'SYMBOL':<12}{'position':>10}{'@config':>10}{'@live':>10}"
        f"{'unexplained':>13}"
    )
    for r in sorted(rows, key=lambda x: -x["unexplained_usd"]):
        flag = "  <-- INVERTS direction" if r["direction_inverts"] else ""
        print(
            f"{r['symbol']:<12}{r['position']:>10.2f}"
            f"{r['delta_if_config']:>+10.2f}{r['delta_if_live']:>+10.2f}"
            f"{r['unexplained_usd']:>13.2f}{flag}"
        )

    over = [r for r in rows if r["unexplained_usd"] > args.threshold]
    inverts = [r for r in rows if r["direction_inverts"]]
    total = sum(r["unexplained_usd"] for r in rows)
    print(f"\nbots diverging >${args.threshold:.3f}: {len(over)} of {len(rows)}")
    print(f"bots where the frames give OPPOSITE trade directions: " f"{len(inverts)}")
    for r in inverts:
        print(
            f"   {r['symbol']:<12} @config {r['delta_if_config']:+.2f} "
            f"vs @live {r['delta_if_live']:+.2f}"
        )
    print(f"total unexplained across one full-fleet Manual Fire: " f"${total:,.2f}")
    print("\nThis measures the disagreement, not which frame is correct.")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
