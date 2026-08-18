"""quarantine_sim_contamination.py — move sim-written rows out of the
live trade log.

Operator-approved 2026-08-02 after v3.24.12 identified the defect.

BACKGROUND
==========
Until v3.24.12, sim ScrummingBots shared the GLOBAL event bus with
live bots (``BotContainer.__init__`` -> ``get_event_bus()``), and
``LogManager`` is attached to that bus. Every Fleet Replay fill was
therefore written into ``~/.acervator_logs/trade/trade.log`` as if
it were a real trade.

Measured 2026-08-02: 136 of 699 rows (19.5%), from 50 bot_ids absent
from bot_state.json, all dated 2026-08-01 — the day Fleet Replay was
first exercised.

v3.24.12 stops new contamination by giving sim bots an isolated bus.
This tool removes the rows already written.

IDENTIFICATION CRITERION
========================
A row is quarantined only when BOTH hold:

    1. ``data.symbol`` is empty, AND
    2. ``bot_id`` is absent from bot_state.json

Both are required because either alone produces false positives:

  * Empty symbol alone — the v3.16.60 resolver could legitimately
    miss during a restart window for a real bot.
  * Unknown bot_id alone — a DELETED live bot is absent from
    bot_state but its trades were real. Measured: 2 such bot_ids
    exist in this log, and they carry populated symbols, so the
    conjunction correctly spares them.

SAFETY
======
  * Original file is copied to trade.log.pre_quarantine_<stamp>
    before anything is written.
  * Removed rows are written VERBATIM to a quarantine sidecar, so
    nothing is destroyed and the operation is reversible.
  * The rewrite is atomic (temp file + replace).
  * ``--dry-run`` reports the plan without touching disk.

Usage:
    python -m tools.quarantine_sim_contamination --dry-run
    python -m tools.quarantine_sim_contamination
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

TRADE_LOG = Path.home() / ".acervator_logs" / "trade" / "trade.log"
BOT_STATE = Path.home() / ".acervator" / "bot_state.json"


def _load_live_bot_ids(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
        return set()
    return set((data.get("bots") or {}).keys())


def _is_contaminated(row: dict, live_ids: set[str]) -> bool:
    """Both conditions required — see module docstring."""
    symbol = str((row.get("data") or {}).get("symbol", "") or "").strip()
    bot_id = str(row.get("bot_id", "") or "")
    return (not symbol) and (bot_id not in live_ids)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Report the plan; write nothing.")
    ap.add_argument("--trade-log", type=Path, default=TRADE_LOG)
    ap.add_argument("--bot-state", type=Path, default=BOT_STATE)
    args = ap.parse_args(argv)

    if not args.trade_log.exists():
        print(f"ERROR: {args.trade_log} not found", file=sys.stderr)
        return 2

    live_ids = _load_live_bot_ids(args.bot_state)
    if not live_ids:
        print("ERROR: no live bot_ids loaded — refusing to run, since "
              "every row would look contaminated.", file=sys.stderr)
        return 3
    print(f"live bot_ids in bot_state : {len(live_ids)}")

    keep_lines: list[str] = []
    quarantine_lines: list[str] = []
    malformed = 0
    by_day: dict[str, int] = {}
    by_bot: set[str] = set()
    by_action: dict[str, int] = {}

    with args.trade_log.open("r", encoding="utf-8",
                             errors="replace") as f:
        for raw in f:
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                # Unparseable lines are KEPT — this tool removes a
                # known contamination signature, not arbitrary junk.
                malformed += 1
                keep_lines.append(raw.rstrip("\n"))
                continue
            if _is_contaminated(row, live_ids):
                quarantine_lines.append(stripped)
                day = str(row.get("timestamp", ""))[:10]
                by_day[day] = by_day.get(day, 0) + 1
                by_bot.add(str(row.get("bot_id", "")))
                act = str((row.get("data") or {}).get("action", "?"))
                by_action[act] = by_action.get(act, 0) + 1
            else:
                keep_lines.append(stripped)

    total = len(keep_lines) + len(quarantine_lines)
    print(f"rows scanned              : {total}")
    print(f"rows to KEEP              : {len(keep_lines)}")
    print(f"rows to QUARANTINE        : {len(quarantine_lines)}")
    if malformed:
        print(f"unparseable rows (kept)   : {malformed}")

    if not quarantine_lines:
        print("\nNothing to quarantine — log is clean.")
        return 0

    print(f"\ndistinct sim bot_ids      : {len(by_bot)}")
    print("by day:")
    for d in sorted(by_day):
        print(f"   {d}  {by_day[d]:>5}")
    print("by action:")
    for a, n in sorted(by_action.items(), key=lambda kv: -kv[1]):
        print(f"   {a:<18} {n:>5}")

    if args.dry_run:
        print("\n[dry-run] no files written.")
        return 0

    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = args.trade_log.with_name(
        f"{args.trade_log.name}.pre_quarantine_{stamp}")
    quarantine = args.trade_log.with_name(
        f"sim_contamination_quarantine_{stamp}.log")

    shutil.copy2(args.trade_log, backup)
    print(f"\nbackup written     : {backup}")

    quarantine.write_text(
        "\n".join(quarantine_lines) + "\n", encoding="utf-8")
    print(f"quarantine written : {quarantine}")

    tmp = args.trade_log.with_suffix(".tmp")
    tmp.write_text("\n".join(keep_lines) + "\n", encoding="utf-8")
    os.replace(tmp, args.trade_log)
    print(f"trade.log rewritten: {args.trade_log} "
          f"({len(keep_lines)} rows)")

    # Verify the rewrite parses and no longer matches the signature.
    remaining = 0
    with args.trade_log.open("r", encoding="utf-8",
                             errors="replace") as f:
        for raw in f:
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if _is_contaminated(row, live_ids):
                remaining += 1
    print(f"\nverification: {remaining} contaminated row(s) remain "
          f"(expected 0)")
    return 0 if remaining == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
