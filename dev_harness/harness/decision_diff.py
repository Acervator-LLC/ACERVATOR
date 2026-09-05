"""CV2 — live decision-diff harness.

WHAT THIS IS FOR
════════════════
Every cascade that touches a live trading path has the same exit gate:
prove it did not move a SCRUM or FOLD decision. Until now the only
available evidence was "the suite is green", and the suite does not
construct a live bot — so a change to an indicator could alter real gate
outcomes with nothing failing.

This replays the REAL gate chains over REAL Stone Tablet candles and
emits a decision record. Run it on a baseline tree and a candidate tree,
diff the two records, and the answer is a number rather than an opinion.

HOW IT AVOIDS RE-IMPLEMENTING THE ENGINE
════════════════════════════════════════
Nothing here reproduces trading logic. It borrows the production pieces:

  * ``TASignalProvider`` computes the TA primitives. It needs only an
    object with ``async get_ohlcv(symbol, timeframe=, limit=)``, so a
    Stone Tablet feed satisfies it and the network is never touched.
  * ``build_scrumming_scrum_chain`` / ``build_scrumming_fold_chain``
    are the real chains, evaluated on a real ``GateContext``.

If either changes, this harness changes with it — which is the point. A
differ that carries its own copy of the logic measures the copy.

WHAT VARIES AND WHAT IS PINNED
══════════════════════════════
``GateContext`` has 51 fields. Only the TA-derived ones are computed
from candles; every bot-state field is FIXED by a scenario. That is
deliberate: holding bot state constant means any decision difference is
attributable to the TA change under test and nothing else. The scenarios
exist because a single fixed state would leave most gates un-exercised —
one where SCRUM is plausible, one where FOLD is, one with the operator
toggles off.

The pinned values are visible in ``SCENARIOS`` below rather than buried,
because "what was held constant" is the first question to ask of any
differential result.

WHAT THIS DOES NOT PROVE
════════════════════════
It measures the gate CHAIN's verdict for a given context. It does not
execute ``ScrummingBot.tick()``, so anything upstream of the context —
position sizing, tranche construction, order placement — is out of
scope. A green diff here means "the gates decided the same"; it does not
mean "the bot would have behaved identically".

USAGE
─────
    python -m tools.harness.decision_diff --emit baseline.json
    # ... make the change ...
    python -m tools.harness.decision_diff --emit candidate.json
    python -m tools.harness.decision_diff --compare baseline.json candidate.json

Exit code from --compare is 0 when every decision matches, 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TabletFeed:
    """Serves one fixed candle window as if it were an exchange.

    Satisfies the only method TASignalProvider calls. Returns the SAME
    window every time, so two runs on two trees see byte-identical
    input and any difference is attributable to the code.
    """

    def __init__(self, candles: list) -> None:
        self._candles = candles

    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> list:
        return self._candles[-int(limit) :]


def _load_windows(assets: list[str], per_asset: int, window: int) -> list[dict]:
    """Cut deterministic windows out of the tablet archive.

    Windows are taken at fixed fractions through each asset's series
    rather than at random offsets or at the tail. Fixed fractions are
    reproducible across machines and across time; the tail is not,
    because the archive grows.
    """
    from src.trading.stone_tablets.storage import (
        read_manifest,
        read_tablet,
        tablet_path,
    )

    out: list[dict] = []
    entries = read_manifest()
    by_asset = {e.asset: e for e in entries}

    for asset in assets:
        entry = by_asset.get(asset)
        if entry is None:
            continue
        tab = read_tablet(
            tablet_path(
                entry.asset, entry.timeframe, entry.year, exchange_id=entry.exchange_id
            )
        )
        rows = tab.candles
        if len(rows) < window * 2:
            continue
        usable = len(rows) - window
        for i in range(per_asset):
            frac = (i + 1) / (per_asset + 1)
            start = int(usable * frac)
            out.append(
                {
                    "asset": asset,
                    "timeframe": entry.timeframe,
                    "start": start,
                    "window": window,
                    "candles": [list(r) for r in rows[start : start + window]],
                }
            )
    return out


SCENARIOS: dict[str, dict] = {
    # A position above target with the operator toggles ON: the state in
    # which a SCRUM is plausible, so the SCRUM chain is actually exercised.
    "scrum_plausible": {
        "delta": 250.0,
        "delta_pct": 5.0,
        "below_interval": False,
        "flag_require_ta_bullish": True,
        "flag_hold_in_uptrend": True,
        "flag_defer_to_htf": False,
        "flag_fold_require_ta_bearish": True,
        "flag_fold_defer_to_htf": False,
        "has_fold_tranches": True,
        "n_fold_tranches": 3,
        "target_fires": True,
        "scrum_ok": True,
        "fold_ok_midline": True,
    },
    # Below target with tranches queued: the FOLD side.
    "fold_plausible": {
        "delta": -180.0,
        "delta_pct": 4.0,
        "below_interval": False,
        "flag_require_ta_bullish": True,
        "flag_hold_in_uptrend": True,
        "flag_defer_to_htf": False,
        "flag_fold_require_ta_bearish": True,
        "flag_fold_defer_to_htf": False,
        "has_fold_tranches": True,
        "n_fold_tranches": 5,
        "target_fires": True,
        "scrum_ok": True,
        "fold_ok_midline": True,
    },
    # Isolates whether a TA change reaches a decision by a path other than the toggles.
    "toggles_off": {
        "delta": 250.0,
        "delta_pct": 5.0,
        "below_interval": False,
        "flag_require_ta_bullish": False,
        "flag_hold_in_uptrend": False,
        "flag_defer_to_htf": False,
        "flag_fold_require_ta_bearish": False,
        "flag_fold_defer_to_htf": False,
        "has_fold_tranches": True,
        "n_fold_tranches": 3,
        "target_fires": True,
        "scrum_ok": True,
        "fold_ok_midline": True,
    },
}

# Bot-state fields identical across every scenario. Pinned so a decision
# difference can only come from TA or from the scenario's own overrides.
FIXED: dict[str, Any] = {
    "eff_htf_blocks_scrum": False,
    "eff_htf_blocks_fold": False,
    "cb_blocks_scrum": False,
    "cb_blocks_fold": False,
    "hyst_ok_scrum_side": True,
    "hyst_ok_fold_side": True,
    "hyst_armed_scrum_side": False,
    "hyst_armed_fold_side": False,
    "hyst_ref_scrum_side": 0.0,
    "hyst_ref_fold_side": 0.0,
    "mem253_at_ceiling": False,
    "mem253_smart_ceiling_usd": 0.0,
    "mem253_current_pos": 0.0,
    "htf_bias_name": None,
    "htf_blocks_scrum": False,
    "htf_blocks_fold": False,
    "scrumming_interval_pct": 2.0,
    "trading_fee_pct": 1.6,
}


def build_context(snapshot: Any, scenario: dict, symbol: str, last_close: float) -> Any:
    """Compose a GateContext: TA from the snapshot, the rest pinned."""
    from src.trading.gate_chain import GateContext

    bb_pos = float(snapshot.bb_position)
    eff = dict(FIXED)
    eff.update(scenario)

    is_bull = bool(snapshot.is_bullish)
    is_bear = bool(snapshot.is_bearish)
    hold = bool(snapshot.trend_hold)

    return GateContext(
        symbol=symbol,
        ticker_last=last_close,
        bb_pos=bb_pos,
        bb_upper_dt=float(snapshot.bb_upper),
        bb_lower_dt=float(snapshot.bb_lower),
        is_bullish=is_bull,
        is_bearish=is_bear,
        trend_hold=hold,
        trend_strength=float(snapshot.trend_strength),
        eff_direction_name=str(
            getattr(snapshot.consensus_direction, "name", snapshot.consensus_direction)
        ),
        eff_is_bullish=is_bull if eff["flag_require_ta_bullish"] else True,
        eff_is_bearish=(is_bear if eff["flag_fold_require_ta_bearish"] else True),
        eff_trend_hold=hold if eff["flag_hold_in_uptrend"] else False,
        bb_above_upper_dt=bb_pos >= 1.0,
        bb_below_lower_dt=bb_pos <= 0.0,
        **eff,
    )


DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "LINK"]


async def _decide_one(win: dict, scen_name: str, scenario: dict) -> dict:
    from src.trading.ta_signal_provider import TASignalProvider
    from src.trading.gate_chain import (
        build_scrumming_scrum_chain,
        build_scrumming_fold_chain,
    )

    symbol = f"{win['asset']}/USD"
    provider = TASignalProvider(TabletFeed(win["candles"]), timeframe=win["timeframe"])
    snap = await provider.evaluate(symbol)
    if snap is None:
        return {
            "asset": win["asset"],
            "start": win["start"],
            "scenario": scen_name,
            "snapshot": None,
        }

    ctx = build_context(snap, scenario, symbol, float(win["candles"][-1][4]))
    scrum = build_scrumming_scrum_chain().evaluate(ctx)
    fold = build_scrumming_fold_chain().evaluate(ctx)
    return {
        "asset": win["asset"],
        "start": win["start"],
        "scenario": scen_name,
        "net_score": round(float(snap.net_score), 10),
        "consensus": round(float(snap.consensus_confidence), 10),
        "bb_position": round(float(snap.bb_position), 10),
        "is_bullish": bool(snap.is_bullish),
        "is_bearish": bool(snap.is_bearish),
        "trend_hold": bool(snap.trend_hold),
        "scrum_fires": bool(scrum.should_fire),
        "fold_fires": bool(fold.should_fire),
        "scrum_blockers": sorted(getattr(scrum, "blocked", []) or []),
        "fold_blockers": sorted(getattr(fold, "blocked", []) or []),
    }


async def run(assets: list[str], per_asset: int, window: int) -> dict:
    windows = _load_windows(assets, per_asset, window)
    records = []
    for win in windows:
        for name, scen in SCENARIOS.items():
            records.append(await _decide_one(win, name, scen))
    return {
        "assets": assets,
        "per_asset": per_asset,
        "window": window,
        "n_windows": len(windows),
        "n_decisions": len(records),
        "records": records,
    }


def compare(a: dict, b: dict) -> tuple[int, list[str]]:
    """Return (n_differences, human-readable lines)."""
    ka = {(r["asset"], r["start"], r["scenario"]): r for r in a["records"]}
    kb = {(r["asset"], r["start"], r["scenario"]): r for r in b["records"]}
    lines: list[str] = []
    diffs = 0

    only_a = sorted(set(ka) - set(kb))
    only_b = sorted(set(kb) - set(ka))
    for k in only_a:
        diffs += 1
        lines.append(f"  MISSING in candidate: {k}")
    for k in only_b:
        diffs += 1
        lines.append(f"  NEW in candidate:     {k}")

    for k in sorted(set(ka) & set(kb)):
        ra, rb = ka[k], kb[k]
        for field in ("scrum_fires", "fold_fires"):
            if ra.get(field) != rb.get(field):
                diffs += 1
                lines.append(
                    f"  DECISION {k} {field}: " f"{ra.get(field)} -> {rb.get(field)}"
                )
        for field in (
            "net_score",
            "consensus",
            "bb_position",
            "is_bullish",
            "is_bearish",
            "trend_hold",
        ):
            if ra.get(field) != rb.get(field):
                lines.append(
                    f"  indicator {k} {field}: " f"{ra.get(field)} -> {rb.get(field)}"
                )
    return diffs, lines


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="decision_diff",
        description="Replay live gate chains over Stone Tablet windows.",
    )
    p.add_argument("--emit", metavar="FILE", help="write a decision record")
    p.add_argument(
        "--compare", nargs=2, metavar=("BASE", "CAND"), help="diff two decision records"
    )
    p.add_argument("--assets", default=",".join(DEFAULT_ASSETS))
    p.add_argument("--per-asset", type=int, default=4)
    p.add_argument("--window", type=int, default=300)
    args = p.parse_args(argv)

    if args.compare:
        a = json.loads(Path(args.compare[0]).read_text(encoding="utf-8"))
        b = json.loads(Path(args.compare[1]).read_text(encoding="utf-8"))
        diffs, lines = compare(a, b)
        for ln in lines:
            print(ln)
        if diffs:
            print(
                f"\n[DIFF] {diffs} gate DECISION difference(s) across "
                f"{len(a['records'])} decisions"
            )
            return 1
        print(
            f"[OK] 0 gate decision differences across "
            f"{len(a['records'])} decisions"
            + (f" ({len(lines)} indicator value change(s))" if lines else "")
        )
        return 0

    assets = [a.strip() for a in args.assets.split(",") if a.strip()]
    result = asyncio.run(run(assets, args.per_asset, args.window))
    if args.emit:
        Path(args.emit).write_text(
            json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
        )
        print(
            f"wrote {args.emit}: {result['n_decisions']} decisions "
            f"across {result['n_windows']} windows"
        )
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
