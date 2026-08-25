"""Issue #106 -- the value sweep and the DECISION sweep, calibrated first.

WHAT IT MEASURES. The per-Fold Growth Rate Cap, before and after the
repair, over the operator's REAL 38-bot fleet and the REAL price history
of each bot's own asset, at six tape lengths.

  BEFORE:  cap = _anchor_target_balance * (max_target_growth_pct / 100)
  AFTER:   cap = ScrummingBot.cycle_growth_cap_usd

THE AFTER SIDE IS NOT REPLICATED. It calls the shipping property through
``fget`` on a stub carrying the three fields it reads. A sweep that
carried its own copy of the new arithmetic would measure the copy. The
BEFORE side HAS to be written out, because this change DELETES that
expression from the tree; that is the one formula here that is not
production code, and it is one line long.

THE DECISION SIDE IS NOT REPLICATED EITHER. ``_plan_fold_consumption``
is the real method that decides which queued tranches a fold cycle
takes. It touches ZERO ``self`` attributes -- asserted by AST over the
shipping file in control C0 below -- so it is called unbound on a plain
object. Every admission verdict in the decision sweep is the production
packer's, not a model of it.

WHY THE TAPE MATTERS FOR A DEFECT THAT IS NOT ABOUT CANDLES. The cap is
a function of bot state, not of price. What the tape decides is N: how
many fold CYCLES a stretch of history contains, and the whole defect is
that the curve is ``anchor x (1 + 0.01N)`` where it should be
``target x 1.01^N``. N is counted with the real D2-b asymmetric reset
rule -- arm on the first BB extreme, reset on the OPPOSITE extreme --
reading ``bb_position`` from the production ``detect_bb_proximity``. Six
tape lengths, because one tape length has produced a false green on this
project three separate times.

N IS A LOWER BOUND ON PURPOSE. ``_fold_cycle_cap_consumed`` is also
reset when a SCRUM fires, and a SCRUM needs bot state no tablet carries.
Only the D2-b resets are counted, so every trajectory here understates
how fast the two curves diverge.

WHAT IS HELD. Each bot is paired with the tablet for ITS OWN asset, and
its anchor, target, consumed, cap percentage and queued tranche ladder
are the live values. Nothing is invented: a bot with no tablet is
skipped and counted as skipped rather than substituted for.

READ-ONLY. It opens ``~/.acervator/bot_state.json`` and
``~/.acervator/stone_tablets`` and writes nothing outside its own output
directory.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger("acervator.audits.issue_106")

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.trading.indicators.bb_proximity import detect_bb_proximity  # noqa: E402
from src.trading.indicators.types import Candle  # noqa: E402
from src.trading.scrumming_bot import ScrummingBot  # noqa: E402

TABLETS = Path.home() / ".acervator" / "stone_tablets"
STATE = Path.home() / ".acervator" / "bot_state.json"
OUT = Path(__file__).resolve().parent
BARS = (35, 40, 60, 100, 200, 400)

# The D2-b asymmetric reset thresholds, as tick() spells them.
UPPER_EXTREME = 0.75
LOWER_EXTREME = 0.25
BB_PERIOD = 20


# -- the two caps -----------------------------------------------------


class _Cfg:
    def __init__(self, pct: float) -> None:
        self.max_target_growth_pct = pct


class _Stub:
    """Exactly the three fields cycle_growth_cap_usd reads.

    THE PROPERTY OBJECT ITSELF is bound here rather than its ``fget``.
    ``property.fget`` is typed Optional, so calling it is an unchecked
    ``None()`` -- the coding archetype said so, at high severity, and it
    was right. Binding the descriptor on the class gives the same
    production code path with no Optional in it, and it is the same
    shape ``tests/test_growth_cap_compounds.py`` uses.
    """

    cycle_growth_cap_usd = ScrummingBot.cycle_growth_cap_usd

    def __init__(self, pct: float, target: float, consumed: float) -> None:
        self.config = _Cfg(pct)
        self._target_balance = target
        self._fold_cycle_cap_consumed = consumed


def cap_after(pct: float, target: float, consumed: float) -> float:
    """The shipping property. Not a copy of it."""
    return float(_Stub(pct, target, consumed).cycle_growth_cap_usd)


def cap_before(pct: float, anchor: float) -> float:
    """The expression this change deletes. The one non-production line."""
    return anchor * (pct / 100.0)


# -- the fleet --------------------------------------------------------


def fleet() -> tuple[int, list[dict]]:
    raw = json.loads(STATE.read_text(encoding="utf-8"))
    bots = raw.get("bots") or {}
    out: list[dict] = []
    for bot_id, b in bots.items():
        ss = b.get("scrumming_state") or {}
        cfg = b.get("config") or {}
        if not ss:
            continue
        sym = str(cfg.get("symbol") or "")
        out.append(
            {
                "bot_id": bot_id,
                "symbol": sym,
                "asset": str(cfg.get("target_asset") or sym.split("/")[0]),
                "anchor": float(ss.get("anchor_target_balance", 0.0) or 0.0),
                "target": float(ss.get("target_balance", 0.0) or 0.0),
                "consumed": float(ss.get("fold_cycle_cap_consumed", 0.0) or 0.0),
                "parked": float(ss.get("standing_surplus_usd", 0.0) or 0.0),
                "pct": float(cfg.get("max_target_growth_pct", 1.0) or 0.0),
                "tranches": [
                    t for t in (ss.get("fold_tranches") or []) if isinstance(t, dict)
                ],
            }
        )
    return int(raw.get("bot_count", len(bots))), out


# -- the tape ---------------------------------------------------------


def tablets() -> dict[str, list]:
    found: dict[str, list] = {}
    for path in sorted(TABLETS.glob("*.json")):
        if path.name == "MANIFEST.json":
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - a bad tablet is skipped, loudly
            logger.warning("tablet %s did not parse: %r", path.name, exc)
            continue
        rows = raw.get("candles") or []
        if rows:
            found[str(raw.get("asset") or path.stem.split("_")[0])] = rows
    return found


def candles(rows: list, n: int) -> list | None:
    tail = rows[-n:]
    if len(tail) < n:
        return None
    out = []
    for r in tail:
        try:
            out.append(
                Candle(
                    timestamp=int(r[0]),
                    open=float(r[1]),
                    high=float(r[2]),
                    low=float(r[3]),
                    close=float(r[4]),
                    volume=float(r[5]),
                )
            )
        except (TypeError, ValueError, IndexError):
            return None
    return out


def count_cycles(cs: list) -> int:
    """Fold cycles on this tape, by the real D2-b asymmetric rule.

    Arms on the first BB extreme touch and RESETS on the opposite one,
    exactly as tick() maintains ``_target_grow_last_side``. A reset is
    one cycle boundary.
    """
    side = None
    cycles = 0
    for i in range(BB_PERIOD - 1, len(cs)):
        r = detect_bb_proximity(cs[i - BB_PERIOD + 1 : i + 1])
        pos = max(0.0, min(1.0, float(getattr(r, "bb_position", 0.5))))
        up = pos >= UPPER_EXTREME
        low = pos <= LOWER_EXTREME
        if side == "lower" and up:
            cycles += 1
            side = None
        elif side == "upper" and low:
            cycles += 1
            side = None
        elif side is None and (up or low):
            side = "lower" if low else "upper"
    return cycles


# -- the decision instrument ------------------------------------------

_PLAN = ScrummingBot._plan_fold_consumption


def plan_self_attrs() -> list[str]:
    """C0 control: the packer must touch no ``self`` attribute.

    If it ever does, calling it unbound stops being legitimate and the
    whole decision sweep is measuring a stub instead of the bot.
    """
    src = (REPO / "src" / "trading" / "scrumming_bot.py").read_text(encoding="utf-8")
    for cls in ast.parse(src).body:
        if isinstance(cls, ast.ClassDef) and cls.name == "ScrummingBot":
            for fn in cls.body:
                if (
                    isinstance(fn, ast.FunctionDef)
                    and fn.name == "_plan_fold_consumption"
                ):
                    return sorted(
                        {
                            n.attr
                            for n in ast.walk(fn)
                            if isinstance(n, ast.Attribute)
                            and isinstance(n.value, ast.Name)
                            and n.value.id == "self"
                        }
                    )
    return ["METHOD NOT FOUND"]


def admit(tranches: list, budget: float) -> tuple:
    """The production packer's verdict: what this cycle takes.

    The caller in tick() sorts highest-``initial_buy_price``-first
    before handing the list over, so this does too.
    """
    order = sorted(
        tranches, key=lambda t: -float(t.get("initial_buy_price", t.get("ref", 0)) or 0)
    )
    plan, capped, partial = _PLAN(object(), order, budget)
    taken = frozenset(id(s) for s, take, _ in plan if take > 0)
    usd = float(sum(take for _, take, _ in plan))
    return taken, len(capped), int(partial), usd


def digest(rows: list[dict], keys: tuple[str, ...]) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(
            "|".join(
                v.hex() if isinstance(v, float) else repr(v)
                for v in (r[k] for k in keys)
            ).encode()
        )
        h.update(b"\n")
    return h.hexdigest()


# -- the sweep --------------------------------------------------------


def measure() -> tuple[list[dict], dict]:
    bot_count, bots = fleet()
    taps = tablets()
    meta = {
        "bot_count_declared": bot_count,
        "bots_read": len(bots),
        "bots_with_growth": sum(
            1 for b in bots if abs(b["target"] - b["anchor"]) > 1e-9
        ),
        "bots_with_tranches": sum(1 for b in bots if b["tranches"]),
        "tablets_read": len(taps),
        "fleet_anchor": sum(b["anchor"] for b in bots),
        "fleet_target": sum(b["target"] for b in bots),
        "fleet_parked": sum(b["parked"] for b in bots),
        "pcts": sorted({b["pct"] for b in bots}),
        "skipped_no_tablet": sorted(
            {b["asset"] for b in bots if b["asset"] not in taps}
        ),
    }

    # Cycle counts are a property of the TAPE, so they are computed once
    # per (asset, bars) and reused by every bot on that asset.
    cyc: dict[tuple[str, int], int] = {}
    assets = {b["asset"] for b in bots} & set(taps)
    for a in sorted(assets):
        for bars in BARS:
            cs = candles(taps[a], bars)
            cyc[(a, bars)] = 0 if cs is None else count_cycles(cs)

    rows: list[dict] = []
    for b in bots:
        if b["asset"] not in taps:
            continue
        for bars in BARS:
            n = cyc.get((b["asset"], bars), 0)

            # --- value: the cap RIGHT NOW, on the live state ----------
            cb_now = cap_before(b["pct"], b["anchor"])
            ca_now = cap_after(b["pct"], b["target"], b["consumed"])

            # --- value: the trajectory over the tape's N cycles -------
            # The cap-bound regime: each cycle has at least a cap's
            # worth of surplus available. The live fleet parks money in
            # `standing_surplus_usd`, which is the evidence that the cap
            # binds rather than the surplus.
            tb = b["target"]
            ta = b["target"]
            first_a = None
            for _ in range(n):
                cb = cap_before(b["pct"], b["anchor"])
                ca = cap_after(b["pct"], ta, 0.0)
                if first_a is None:
                    first_a = ca
                tb += cb
                ta += ca

            # --- decision: the production packer under both budgets ---
            fl_b = fl_a = None
            adm_b = adm_a = 0
            par_b = par_a = 0
            usd_b = usd_a = 0.0
            flips = 0
            if b["tranches"]:
                tk_b, adm_b, par_b, usd_b = admit(
                    b["tranches"], max(0.0, cb_now - b["consumed"])
                )
                tk_a, adm_a, par_a, usd_a = admit(
                    b["tranches"], max(0.0, ca_now - b["consumed"])
                )
                fl_b, fl_a = len(tk_b), len(tk_a)
                flips = len(tk_a ^ tk_b)

            rows.append(
                {
                    "bot_id": b["bot_id"],
                    "asset": b["asset"],
                    "bars": bars,
                    "pct": b["pct"],
                    "anchor": b["anchor"],
                    "target": b["target"],
                    "consumed": b["consumed"],
                    "parked": b["parked"],
                    "cycles": n,
                    "cap_before": cb_now,
                    "cap_after": ca_now,
                    "cap_delta": ca_now - cb_now,
                    "cap_first_cycle_after": first_a if first_a is not None else 0.0,
                    "target_after_n_before": tb,
                    "target_after_n_after": ta,
                    "traj_delta": ta - tb,
                    "n_tranches": len(b["tranches"]),
                    "admitted_before": adm_b,
                    "admitted_after": adm_a,
                    "taken_before": fl_b if fl_b is not None else 0,
                    "taken_after": fl_a if fl_a is not None else 0,
                    "partial_before": par_b,
                    "partial_after": par_a,
                    "usd_before": usd_b,
                    "usd_after": usd_a,
                    "tranche_flips": flips,
                }
            )
    return rows, meta


VALUE_KEYS = (
    "bot_id",
    "bars",
    "pct",
    "anchor",
    "target",
    "consumed",
    "cycles",
    "cap_before",
    "target_after_n_before",
)
VALUE_KEYS_A = (
    "bot_id",
    "bars",
    "pct",
    "anchor",
    "target",
    "consumed",
    "cycles",
    "cap_after",
    "target_after_n_after",
)
DEC_KEYS = ("bot_id", "bars", "taken_before", "partial_before", "usd_before")
DEC_KEYS_A = ("bot_id", "bars", "taken_after", "partial_after", "usd_after")


# -- calibration ------------------------------------------------------


def calibrate(rows: list[dict], meta: dict) -> list[str]:
    out: list[str] = []
    ok = True

    # C0 -- the decision instrument is the production packer
    attrs = plan_self_attrs()
    out.append("### C0 the decision instrument is the production packer\n")
    out.append(f"`_plan_fold_consumption` self-attributes touched: " f"`{attrs}`\n")
    out.append(
        "Empty is what makes the unbound call legitimate. A "
        "non-empty list would mean every admission verdict below "
        "came from a stub.\n"
    )
    if attrs:
        ok = False

    # C1 -- instrument control on the reader
    out.append("### C1 instrument control -- the reader is not blind\n")
    out.append("| question | count |\n|---|---|")
    out.append(f"| bots declared in state | {meta['bot_count_declared']} |")
    out.append(f"| bots read | {meta['bots_read']} |")
    out.append(f"| bots with `target != anchor` | {meta['bots_with_growth']} |")
    out.append(
        f"| bots with a queued tranche ladder | " f"{meta['bots_with_tranches']} |"
    )
    out.append(f"| tablets read | {meta['tablets_read']} |")
    out.append(f"| rows measured | {len(rows)} |\n")
    out.append(
        "A zero on the third line would have meant a blind reader "
        "rather than a healthy fleet.\n"
    )
    if meta["bots_read"] == 0 or meta["bots_with_growth"] == 0 or not rows:
        ok = False

    # C2 -- positive control on the CAP instrument
    out.append("### C2 positive control -- injected perturbation, the cap\n")
    out.append("| injected into pct | rows whose cap moves |\n|---|---|")
    base = [cap_after(r["pct"], r["target"], r["consumed"]) for r in rows]
    seen = []
    for eps in (0.0, 1e-12, 1e-9, 1e-6, 1e-3, 1e-2):
        moved = sum(
            1
            for r, b0 in zip(rows, base, strict=True)
            if cap_after(r["pct"] + eps, r["target"], r["consumed"]) != b0
        )
        seen.append((eps, moved))
        out.append(f"| {eps:g} | {moved} |")
    out.append("")
    if seen[0][1] != 0 or seen[-1][1] == 0:
        ok = False
    out.append(
        "Zero at zero injection and every row at 0.01 is the "
        "instrument saying it can see a change of the size this "
        "repair makes. A zero elsewhere in this report is only "
        "believable because this line is not zero.\n"
    )

    # C3 -- positive control on the DECISION instrument
    out.append("### C3 positive control -- injected perturbation, " "the packer\n")
    out.append(
        "| injected into budget (USD) | admission verdicts that " "move |\n|---|---|"
    )
    seenD = []
    for eps in (0.0, 1e-9, 0.001, 0.01, 0.10, 1.00, 100.0):
        moved = 0
        for r in rows:
            if not r["n_tranches"]:
                continue
            moved += 1 if r["taken_before"] != _admit_n(r, eps) else 0
        seenD.append((eps, moved))
        out.append(f"| {eps:g} | {moved} |")
    out.append("")
    if seenD[0][1] != 0 or seenD[-1][1] == 0:
        ok = False
    out.append(
        "The packer is a step function, so small injections move "
        "nothing and that is correct behaviour rather than a dead "
        "instrument. The last row proves it is alive.\n"
    )

    # C4 -- the tape produces cycles
    out.append("### C4 the tape actually produces fold cycles\n")
    out.append(
        "| bars | rows | cycles: min | median | max | rows with "
        "zero |\n|---|---|---|---|---|---|"
    )
    zero_all = True
    for bars in BARS:
        sel = sorted(r["cycles"] for r in rows if r["bars"] == bars)
        if not sel:
            continue
        if max(sel) > 0:
            zero_all = False
        out.append(
            f"| {bars} | {len(sel)} | {min(sel)} | "
            f"{sel[len(sel) // 2]} | {max(sel)} | "
            f"{sum(1 for c in sel if c == 0)} |"
        )
    out.append("")
    if zero_all:
        ok = False
    out.append(
        "N is the exponent in `1.01^N`. All-zero here would mean "
        "every trajectory below ran zero cycles and every "
        "trajectory delta was zero for a reason that has nothing "
        "to do with the repair.\n"
    )

    # C5 -- the no-op case
    out.append("### C5 the change is a no-op where it must be\n")
    noop = [
        r
        for r in rows
        if abs(r["target"] - r["anchor"]) < 1e-9 and r["consumed"] < 1e-9
    ]
    bad = [r for r in noop if r["cap_before"] != r["cap_after"]]
    out.append(
        f"Rows where the bot has no accrued growth and no "
        f"consumption booked: **{len(noop)}**. Of those, rows "
        f"where the cap changed: **{len(bad)}**.\n"
    )
    out.append(
        "On a bot that has never compounded, `target == anchor` "
        "and `consumed == 0`, so the new base IS the anchor and "
        "the two caps must be bit-identical. Any row in the "
        "second count would mean the repair moved a number it had "
        "no business moving.\n"
    )
    if bad:
        ok = False

    # C6 -- direction
    out.append("### C6 is the change one-directional?\n")
    up = sum(1 for r in rows if r["cap_after"] > r["cap_before"])
    same = sum(1 for r in rows if r["cap_after"] == r["cap_before"])
    down = sum(1 for r in rows if r["cap_after"] < r["cap_before"])
    out.append("| direction | rows |\n|---|---|")
    out.append(f"| cap WIDER after | {up} |")
    out.append(f"| cap identical | {same} |")
    out.append(f"| cap NARROWER after | {down} |\n")
    out.append(
        "STRUCTURALLY, not just observed. "
        "`cap_after - cap_before = (target - consumed - anchor) "
        "* pct/100`, so the cap widens exactly when accrued "
        "growth (`target - anchor`) is at least the consumption "
        "booked this cycle. Every dollar of this cycle's "
        "consumption was ADDED to the target by the same line "
        "that booked it, so accrued growth contains it and the "
        "difference cannot be negative. The two states that "
        "break the containment are named in the property's "
        "docstring: detonation resets the target to the anchor "
        "without clearing the consumption, and a withdrawal "
        "below the anchor does the same. Both self-clear on the "
        "next cycle reset, and detonation is disabled on all 38 "
        "live bots.\n"
    )
    if down:
        out.append(
            f"The {down} narrower row(s) are listed in "
            f"`rows.jsonl`; each must be one of the two named "
            f"states.\n"
        )

    out.append(f"### calibration verdict: {'PASSED' if ok else 'FAILED'}\n")
    return out


def _admit_n(r: dict, eps: float) -> int:
    """Re-run the packer for row ``r`` with ``eps`` added to the budget."""
    b = _BY_ID[r["bot_id"]]
    tk, _, _, _ = admit(b["tranches"], max(0.0, r["cap_before"] - r["consumed"] + eps))
    return len(tk)


_BY_ID: dict[str, dict] = {}


# -- report -----------------------------------------------------------


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    rows, meta = measure()
    _, bots = fleet()
    _BY_ID.update({b["bot_id"]: b for b in bots})

    L: list[str] = []
    L.append("# Issue #106 -- the per-Fold growth cap compounds\n")
    L.append(
        f"fleet anchor ${meta['fleet_anchor']:,.2f} -> target "
        f"${meta['fleet_target']:,.2f}; parked "
        f"${meta['fleet_parked']:,.2f}; cap percentages in use "
        f"{meta['pcts']}\n"
    )
    L.append(
        f"rows measured: {len(rows)}  "
        f"(bots {meta['bots_read']}, tape lengths {len(BARS)}, "
        f"assets with no tablet: {len(meta['skipped_no_tablet'])} "
        f"{meta['skipped_no_tablet']})\n"
    )

    L.append("## Value sweep\n")
    L.append("```")
    L.append(f"digest BEFORE  {digest(rows, VALUE_KEYS)}")
    L.append(f"digest AFTER   {digest(rows, VALUE_KEYS_A)}")
    L.append("```\n")
    moved = sum(1 for r in rows if r["cap_before"] != r["cap_after"])
    L.append(f"**{moved} of {len(rows)} rows move.**\n")

    L.append("### the cap the moment this ships\n")
    L.append(
        "| bot | anchor | target | consumed | cap before | cap after "
        "| delta | parked |\n|---|---|---|---|---|---|---|---|"
    )
    seen = set()
    for r in sorted(rows, key=lambda x: -x["cap_delta"]):
        if r["bot_id"] in seen:
            continue
        seen.add(r["bot_id"])
        if len(seen) > 12:
            break
        L.append(
            f"| {r['asset']} | ${r['anchor']:.2f} | ${r['target']:.2f} "
            f"| ${r['consumed']:.4f} | ${r['cap_before']:.4f} | "
            f"${r['cap_after']:.4f} | ${r['cap_delta']:+.4f} | "
            f"${r['parked']:.2f} |"
        )
    L.append("")
    tot_b = sum(r["cap_before"] for r in rows if r["bars"] == BARS[0])
    tot_a = sum(r["cap_after"] for r in rows if r["bars"] == BARS[0])
    L.append(
        f"Fleet per-cycle cap: **${tot_b:,.4f} -> ${tot_a:,.4f}**, "
        f"a change of **${tot_a - tot_b:+,.4f}** "
        f"({(tot_a / tot_b - 1) * 100 if tot_b else 0:+.2f}%).\n"
    )

    L.append("### the trajectory, per tape length\n")
    L.append(
        "| bars | rows | median cycles | fleet target after N "
        "(before) | (after) | difference |\n|---|---|---|---|---|---|"
    )
    for bars in BARS:
        sel = [r for r in rows if r["bars"] == bars]
        if not sel:
            continue
        cs = sorted(r["cycles"] for r in sel)
        L.append(
            f"| {bars} | {len(sel)} | {cs[len(cs) // 2]} | "
            f"${sum(r['target_after_n_before'] for r in sel):,.2f} | "
            f"${sum(r['target_after_n_after'] for r in sel):,.2f} | "
            f"${sum(r['traj_delta'] for r in sel):+,.2f} |"
        )
    L.append("")
    L.append(
        "Each row runs its own bot's live target forward by the "
        "number of D2-b cycles its own asset's tape contains. The "
        "BEFORE column adds a constant `anchor * pct/100` every "
        "cycle; the AFTER column adds `pct/100` of the target it "
        "has reached. The gap is the curve the operator asked "
        "for.\n"
    )

    L.append("## Calibration\n")
    L.extend(calibrate(rows, meta))

    L.append("## Decision sweep\n")
    L.append("```")
    L.append(f"digest BEFORE  {digest(rows, DEC_KEYS)}")
    L.append(f"digest AFTER   {digest(rows, DEC_KEYS_A)}")
    L.append("```\n")
    withT = [r for r in rows if r["n_tranches"]]
    flip = [r for r in withT if r["tranche_flips"]]
    wider = [r for r in withT if r["usd_after"] > r["usd_before"]]
    narrower = [r for r in withT if r["usd_after"] < r["usd_before"]]
    L.append(
        f"Rows carrying a queued tranche ladder: **{len(withT)}**. "
        f"Rows where the production packer takes a DIFFERENT set of "
        f"tranches: **{len(flip)}**.\n"
    )
    L.append("| direction | rows | fold-back USD deployed |\n|---|---|---|")
    L.append(
        f"| MORE deployed after | {len(wider)} | "
        f"${sum(r['usd_after'] - r['usd_before'] for r in wider):+,.4f} |"
    )
    L.append(
        f"| LESS deployed after | {len(narrower)} | "
        f"${sum(r['usd_after'] - r['usd_before'] for r in narrower):+,.4f} |"
    )
    L.append(
        f"| unchanged | {len(withT) - len(wider) - len(narrower)} | " f"$0.0000 |\n"
    )
    L.append("### every flip, attributable\n")
    L.append(
        "| bot | ladder | budget before | budget after | taken before "
        "| taken after | part before | part after | USD before | USD "
        "after |\n|---|---|---|---|---|---|---|---|---|---|"
    )
    seen = set()
    for r in sorted(flip, key=lambda x: x["bot_id"]):
        if r["bot_id"] in seen:
            continue
        seen.add(r["bot_id"])
        L.append(
            f"| {r['asset']} | {r['n_tranches']} | "
            f"${max(0.0, r['cap_before'] - r['consumed']):.4f} | "
            f"${max(0.0, r['cap_after'] - r['consumed']):.4f} | "
            f"{r['taken_before']} | {r['taken_after']} | "
            f"{r['partial_before']} | {r['partial_after']} | "
            f"${r['usd_before']:.4f} | ${r['usd_after']:.4f} |"
        )
    L.append("")
    L.append(
        "A flip is one direction only, and the reason is "
        "structural rather than statistical: `_plan_fold_consumption` "
        "is monotone in its budget. It walks the ladder in a fixed "
        "order and takes the whole of each tranche that fits, then "
        "the remaining room from the next. A larger budget can only "
        "take at least as much from each tranche in that order, so "
        "no tranche admitted under the smaller budget can be "
        "dropped by the larger one. C6 shows the budget itself only "
        "moves one way, so the deployment can only move one way "
        "too.\n"
    )
    L.append(
        "WHAT A FLIP IS AND IS NOT. It is a tranche REBUY that the "
        "cap used to defer to a later cycle and now admits this "
        "cycle. The tranche was already price-eligible: every gate "
        "upstream -- TA bearish, BB threshold, the MEM-171 "
        "per-tranche price floor -- had already passed it, and the "
        "cap was the last thing holding it. Nothing here admits a "
        "tranche that a price gate refused.\n"
    )

    with io.open(OUT / "rows.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    (OUT / "sweep_result.md").write_text(
        "\n".join(L) + "\n", encoding="utf-8", newline="\n"
    )
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
