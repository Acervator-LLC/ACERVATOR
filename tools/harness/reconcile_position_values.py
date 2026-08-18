"""Reconcile displayed position values against their own inputs.

Operator directive 2026-08-06:

    "Among other API-dependent metrics, Target Delta (Ammo) needs to be
     compared against API inputs to ensure a miscalculation is not
     happening. The values are generally correct based on my testing."

They are generally correct, and this tool exists to keep saying so with
evidence rather than by assertion.

WHAT IT COMPARES
For every bot in the persisted state:

    cached      = stats.position_value          (written by the tick loop)
    recomputed  = sum(main_lots[].units) x stats.current_price x quote_to_usd

Both come from the platform's own record, so this is an INTERNAL
consistency check, not an exchange reconciliation. It cannot detect an
error that corrupts units and position_value identically. What it does
detect is staleness: the two fields are written at different moments, and
when they drift apart the cached one is wrong.

WHY IT MATTERS EVEN THOUGH THE AMMO IS FINE
The per-bot Ammo does NOT use the cached field except as a marked
fallback -- C10 made it recompute from holdings x price. The manual-fire
engine recomputes too (scrumming_bot.py:9246). But the FLEET AGGREGATE
does use it: bot_container.py:3382 sums stats.position_value into
crypto_position_value_usd, and :3405 adds that to wallet cash for the
headline portfolio figure. Staleness there understates the total.

READ-ONLY. Opens the state file for reading and writes nothing. It
constructs no project classes -- their defaults resolve into the
operator's runtime tree.

    python -m tools.harness.reconcile_position_values [--json] [--threshold 1.0]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _state_path() -> Path:
    return Path.home() / ".acervator" / "bot_state.json"


def reconcile(state: dict) -> list[dict]:
    """One row per bot. Pure function so it is testable without a file."""
    out: list[dict] = []
    for rec in (state.get("bots") or {}).values():
        rec = rec or {}
        cfg = rec.get("config") or {}
        stats = rec.get("stats") or {}
        scrum = rec.get("scrumming_state") or {}
        lots = [x for x in (scrum.get("main_lots") or [])
                if isinstance(x, dict)]
        units = sum(float(x.get("units", 0) or 0) for x in lots)
        price = float(stats.get("current_price", 0) or 0)
        qrate = float(scrum.get("quote_to_usd", 1.0) or 1.0)
        cached = float(stats.get("position_value", 0) or 0)
        recomputed = units * price * qrate
        diff = cached - recomputed
        out.append({
            "symbol": str(cfg.get("symbol", "?")),
            "lots": len(lots),
            "units": units,
            "price": price,
            "quote_to_usd": qrate,
            "cached_position_value": cached,
            "recomputed_position_value": recomputed,
            "divergence_usd": diff,
            "divergence_pct": (abs(diff) / cached * 100.0) if cached else 0.0,
        })
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON")
    ap.add_argument("--threshold", type=float, default=1.0,
                    help="flag divergence above this percentage")
    ap.add_argument("--state", type=Path, default=None,
                    help="state file to read (default: ~/.acervator/bot_state.json)")
    args = ap.parse_args(argv)

    path = args.state or _state_path()
    if not path.exists():
        print(f"state file not found: {path}", file=sys.stderr)
        return 2
    rows = reconcile(json.loads(path.read_text(encoding="utf-8")))
    if not rows:
        print("no bots in state; nothing to reconcile", file=sys.stderr)
        return 2

    # POSITIVE CONTROL. Every recomputed value being zero means the field
    # names moved and this tool is measuring nothing -- which would
    # otherwise render as a clean bill of health. Fail loudly instead.
    live = [r for r in rows if r["recomputed_position_value"] > 0]
    if not live:
        print("INSTRUMENT FAILURE: every recomputed value is zero. The "
              "field layout has changed and this tool is measuring "
              "nothing. Do NOT read the output below as a pass.",
              file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"positive control: {len(live)}/{len(rows)} bots recomputed "
              f"non-zero\n")
        print(f"{'SYMBOL':<12}{'lots':>5}{'cached':>12}"
              f"{'recomputed':>12}{'diverge':>11}{'pct':>8}")
        for r in sorted(rows, key=lambda x: -x["divergence_pct"]):
            flag = "  <-- stale" if r["divergence_pct"] > args.threshold else ""
            print(f"{r['symbol']:<12}{r['lots']:>5}"
                  f"{r['cached_position_value']:>12.4f}"
                  f"{r['recomputed_position_value']:>12.4f}"
                  f"{r['divergence_usd']:>+11.4f}"
                  f"{r['divergence_pct']:>7.2f}%{flag}")
        tc = sum(r["cached_position_value"] for r in rows)
        tr = sum(r["recomputed_position_value"] for r in rows)
        over = [r for r in rows if r["divergence_pct"] > args.threshold]
        print(f"\nbots diverging >{args.threshold:.1f}%: {len(over)} of {len(rows)}")
        print(f"fleet cached ${tc:,.2f} vs recomputed ${tr:,.2f} "
              f"({tr - tc:+,.2f})")
        print("\nThe cached field feeds the FLEET total via "
              "bot_container.py:3382; the per-bot Ammo and the manual-fire "
              "engine both recompute and are unaffected.")
    return 1 if any(r["divergence_pct"] > args.threshold for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
