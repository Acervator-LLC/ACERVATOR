"""purge_orphan_reservations.py — drop reservations owned by bots
that no longer exist.

Operator-approved 2026-08-03.

BACKGROUND
==========
``~/.acervator/reservation_state.json`` had grown to 6.5 MB holding
16,551 reservations, of which 28 belonged to live bots. The other
16,523 were each owned by a distinct bot_id absent from
bot_state.json — 15,837 of them "Extractor chunk + hedge" entries
from Extractor bots that no longer exist. Heartbeats reached 71.8
days old against 5.9 days for the newest live bot.

Cost: CapitalReservationRegistry.effective_available() sums "others
reserved" for an asset on every call, and _ensure_capital_reservation
runs at the top of every bot tick. Thousands of dead rows per asset
are re-summed continuously, which is why sim runs emit
    "others reserved 523.13 > total_holdings 0.09 — clamping to 0"
on every tick. The registry is not merely large, it is producing
wrong availability numbers from stale state.

IDENTIFICATION CRITERION
========================
A reservation is purged when its ``bot_id`` is absent from
bot_state.json. A heartbeat is purged on the same rule.

That single condition is safe here in a way it was NOT for the trade
log: a reservation is live operational state, not history. A dead
bot's reservation has no claim on capital and no archival value. By
contrast a deleted bot's TRADES are real history, which is why the
trade.log quarantine required a second condition.

SAFETY
======
  * Backup written before any change.
  * Purged rows written verbatim to a quarantine sidecar.
  * Atomic replace (temp + os.replace).
  * ``--dry-run`` reports the plan and writes nothing.
  * Refuses to run when bot_state.json yields zero live bots, since
    every reservation would then look orphaned.

RUN WITH THE APP CLOSED. The registry is held in memory and
rewritten on save; purging underneath a running app would be undone.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

RESERVATION_STATE = Path.home() / ".acervator" / "reservation_state.json"
BOT_STATE = Path.home() / ".acervator" / "bot_state.json"


def _load_live_bot_ids(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
        return set()
    return set((data.get("bots") or {}).keys())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--state", type=Path, default=RESERVATION_STATE)
    ap.add_argument("--bot-state", type=Path, default=BOT_STATE)
    args = ap.parse_args(argv)

    if not args.state.exists():
        print(f"ERROR: {args.state} not found", file=sys.stderr)
        return 2

    live = _load_live_bot_ids(args.bot_state)
    if not live:
        print("ERROR: zero live bot_ids loaded — refusing to run, "
              "every reservation would look orphaned.",
              file=sys.stderr)
        return 3

    try:
        data = json.loads(args.state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot parse {args.state}: {exc}",
              file=sys.stderr)
        return 4

    reservations = data.get("reservations") or []
    heartbeats = data.get("heartbeats") or {}

    keep_res = [r for r in reservations
                if isinstance(r, dict) and r.get("bot_id") in live]
    drop_res = [r for r in reservations
                if not (isinstance(r, dict)
                        and r.get("bot_id") in live)]
    keep_hb = {k: v for k, v in heartbeats.items() if k in live}
    drop_hb = {k: v for k, v in heartbeats.items() if k not in live}

    size_mb = args.state.stat().st_size / 1e6
    print(f"live bots              : {len(live)}")
    print(f"file size              : {size_mb:.1f} MB")
    print(f"reservations  keep/drop: {len(keep_res):,} / "
          f"{len(drop_res):,}")
    print(f"heartbeats    keep/drop: {len(keep_hb):,} / "
          f"{len(drop_hb):,}")

    if not drop_res and not drop_hb:
        print("\nNothing to purge — registry is clean.")
        return 0

    from collections import Counter
    reasons = Counter(
        (r.get("reason", "") or "")[:44] for r in drop_res)
    print("\ntop orphan reasons:")
    for reason, n in reasons.most_common(5):
        print(f"  {n:>7,}  {reason}")

    # Per-asset view: this is what effective_available() was summing.
    by_asset = Counter(
        str(r.get("asset", "?")) for r in drop_res)
    print("\ntop assets by orphan count "
          "(these inflated 'others reserved'):")
    for asset, n in by_asset.most_common(6):
        print(f"  {n:>7,}  {asset}")

    if args.dry_run:
        print("\n[dry-run] no files written.")
        return 0

    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = args.state.with_name(
        f"{args.state.name}.pre_purge_{stamp}")
    quarantine = args.state.with_name(
        f"orphan_reservations_quarantine_{stamp}.json")

    shutil.copy2(args.state, backup)
    print(f"\nbackup written     : {backup}")

    quarantine.write_text(
        json.dumps({"purged_at": stamp,
                    "reservations": drop_res,
                    "heartbeats": drop_hb}, indent=1),
        encoding="utf-8")
    print(f"quarantine written : {quarantine}")

    data["reservations"] = keep_res
    data["heartbeats"] = keep_hb
    tmp = args.state.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, args.state)
    new_mb = args.state.stat().st_size / 1e6
    print(f"state rewritten    : {args.state} "
          f"({size_mb:.1f} MB -> {new_mb:.2f} MB)")

    # Verify the rewrite parses and holds only live owners.
    check = json.loads(args.state.read_text(encoding="utf-8"))
    bad = [r for r in check.get("reservations", [])
           if r.get("bot_id") not in live]
    bad_hb = [k for k in check.get("heartbeats", {}) if k not in live]
    print(f"\nverification: {len(bad)} orphan reservation(s), "
          f"{len(bad_hb)} orphan heartbeat(s) remain (expected 0/0)")
    return 0 if not bad and not bad_hb else 5


if __name__ == "__main__":
    sys.exit(main())
