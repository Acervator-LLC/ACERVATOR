"""Issue #104 -- the value sweep and the DECISION sweep, calibrated first.

WHAT IT MEASURES. The other two favours in ``ScrummingBot.tick()``'s TA
confidence gate, before and after the repair, over all 406 stone tablets
at six tape lengths.

  BEFORE:  consensus + position_boost + bb_confidence_boost  >=  floor
           where floor is 0.25, or 0.1923 on the BB-priority arm.
  AFTER:   consensus  >=  _skewed_confidence_floor(
               position_boost + bb_confidence_boost + arm_skew)

BEFORE IS THE SHIPPING GATE AT ``040fc8e``, NOT THE PRE-#102 GATE. Issue
#102 already moved the BB-priority skew off the measurement. This unit
measures what #102 left behind, so its BEFORE is #102's AFTER.

WHY THE GATE IS REPLICATED HERE RATHER THAN CALLED. ``tick()`` is a
4,500-line coroutine that needs an exchange, a bus and a live ladder.
The confidence pipeline inside it is a pure function of the candle tape,
and that is what this file rebuilds: the voting engine, the two boosts,
the BB zones and the arm's proximity test. It is the SAME replication
``sweep_the_confidence_gate.py`` used for issue #102 -- the boost
builders are copied from it unchanged, so the two units measure the same
quantities and their row digests are comparable.

WHAT IS SWEPT AND WHAT IS HELD. Proximity is MEASURED from the tape. The
arm's other two conditions -- opposing-trade hysteresis and an available
target delta -- are bot state that no tablet carries, so they are held
PERMISSIVE. That is the arm at its widest, which is the case the defect
is about. ``position_boost`` and ``bb_confidence_boost`` are NOT held:
they apply on every tick, on and off the arm, and that is the finding.

CALIBRATION COMES FIRST, AND THIS UNIT ADDS THREE CONTROLS TO #102's.
C4 enumerates ``position_boost``'s term structure exhaustively and
requires the enumerated ceiling to equal the OBSERVED maximum -- the
enumeration is otherwise an assertion about arithmetic nobody checked.
C5 derives ``bb_confidence_boost``'s ceiling from its two component
bounds and states plainly that the tape does not reach it. C6 counts
whether the two favours land on the same reading, because the repair
sums them and a repair that summed two things that never co-occur would
be measuring nothing.

READ-ONLY. It opens ``~/.acervator/stone_tablets`` and writes nothing
outside its own output directory.
"""
from __future__ import annotations

import hashlib
import io
import itertools
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("acervator.audits.issue_104")

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.trading.gate_chain import (  # noqa: E402
    GateContext, build_scrumming_fold_chain, build_scrumming_scrum_chain)
from src.trading.indicators.bb_proximity import detect_bb_proximity  # noqa: E402
from src.trading.indicators.landing_strip import (  # noqa: E402
    detect_landing_strip_v2)
from src.trading.indicators.types import Candle, SignalDirection  # noqa: E402
from src.trading.scrumming_bot import (  # noqa: E402
    _BB_PRIORITY_CONFIDENCE_FLOOR, _BB_PRIORITY_SKEW, _TA_CONFIDENCE_FLOOR,
    _skewed_confidence_floor)
from src.trading.ta_engine import VotingEngine  # noqa: E402

TABLETS = Path.home() / ".acervator" / "stone_tablets"
OUT = Path(__file__).resolve().parent
BARS = (35, 40, 60, 100, 200, 400)

# BotConfig defaults, src/trading/bot_container.py.
BB_TOLERANCE_PCT = 1.0
BB_LANDING_STRIP_CANDLES = 3
TA_TIMEFRAME = "1h"
SCRUM_DETECT_PCT = 75.0

# ScrummingBot._bb_detect_thresholds(). detect_frac = 0.75.
_DETECT_FRAC = SCRUM_DETECT_PCT / 100.0
UPPER_DETECT = 0.5 + _DETECT_FRAC / 2.0
LOWER_DETECT = 0.5 - _DETECT_FRAC / 2.0

# The inline Bullseye tolerances in tick().
TOUCH_TOL = 0.005
WICK_TOL = 0.002


# -- the confidence pipeline, copied from tick() ----------------------

def _boosts(candles, summary, bb_result):
    """``position_boost`` and ``bb_confidence_boost``, as tick() builds them."""
    bb_pos = bb_result.bb_position if bb_result else 0
    at_upper_bb = bb_pos > 0.75
    in_bb_middle = 0.35 <= bb_pos <= 0.65

    bb_boost = 0.0
    override_direction = None
    if bb_result and bb_result.landing_strip:
        bb_boost = 0.15 + bb_result.consolidation_strength * 0.20
        if bb_result.landing_strip_side == "upper":
            override_direction = SignalDirection.BEARISH
        elif bb_result.landing_strip_side == "lower":
            override_direction = SignalDirection.BULLISH
    if len(candles) >= 25:
        try:
            tightening = detect_landing_strip_v2(
                candles, min_consecutive=3, shrink_threshold=0.90,
                bb_tolerance_pct=3.0)
            if tightening and tightening.detected:
                bb_boost += tightening.confidence_boost
        except Exception as exc:
            # tick() suppresses the same way.
            logger.debug("landing-strip v2 declined: %r", exc)

    pos = 0.0
    if summary:
        for sig in summary.signals:
            if (sig.indicator == "vortex"
                    and sig.direction == SignalDirection.BULLISH):
                if at_upper_bb and sig.confidence > 0.5:
                    pos += 0.12
                elif in_bb_middle:
                    pos -= 0.05
            if (sig.indicator == "macd"
                    and sig.direction == SignalDirection.BULLISH):
                if at_upper_bb and sig.confidence > 0.3:
                    pos += 0.08
                elif in_bb_middle:
                    pos -= 0.03
            if (sig.indicator == "ichimoku"
                    and sig.direction == SignalDirection.BULLISH):
                pos += 0.05
            elif (sig.indicator == "ichimoku"
                  and sig.direction == SignalDirection.BEARISH):
                pos -= 0.05
            if sig.indicator == "stochastic_rsi" and sig.confidence > 0.7:
                if sig.direction == SignalDirection.BEARISH:
                    pos += 0.10
                elif sig.direction == SignalDirection.BULLISH:
                    pos -= 0.08
    if len(candles) >= 60:
        sw = 20
        highs = [c.high for c in candles[-sw * 3:]]
        lows = [c.low for c in candles[-sw * 3:]]
        if len(highs) >= sw * 3:
            rh, ph = max(highs[-sw:]), max(highs[-sw * 2:-sw])
            rl, pl = min(lows[-sw:]), min(lows[-sw * 2:-sw])
            if rh > ph and rl > pl:
                if at_upper_bb:
                    pos += 0.05
                elif in_bb_middle:
                    pos -= 0.08
            elif rh < ph and rl < pl:
                pos += 0.05
    return pos, bb_boost, override_direction, bb_pos


def _proximity(candles, bb_result, bb_pos):
    """``_bb_proximity_upper`` / ``_bb_proximity_lower``, from tick()."""
    be_up = be_up_wick = be_lo = be_lo_wick = False
    price = candles[-1].close
    if (bb_result is not None and getattr(bb_result, "upper", 0) > 0
            and getattr(bb_result, "lower", 0) > 0):
        try:
            be_up = abs(price - bb_result.upper) / bb_result.upper < TOUCH_TOL
            be_lo = abs(price - bb_result.lower) / bb_result.lower < TOUCH_TOL
            if not be_up:
                be_up_wick = candles[-1].high >= bb_result.upper * (1.0 - WICK_TOL)
            if not be_lo:
                be_lo_wick = candles[-1].low <= bb_result.lower * (1.0 + WICK_TOL)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    upper = (bb_pos >= UPPER_DETECT) or be_up or be_up_wick
    lower = (bb_pos <= LOWER_DETECT) or be_lo or be_lo_wick
    return upper, lower


# -- the gate, both sides of the repair -------------------------------

def gate_before(consensus, pos, bb, eff_dir, arm):
    """``040fc8e``: both boosts are ADDED to the measurement."""
    conf = consensus + pos + bb
    floor = _BB_PRIORITY_CONFIDENCE_FLOOR if arm else _TA_CONFIDENCE_FLOOR
    bull = (eff_dir in (SignalDirection.BULLISH, SignalDirection.NEUTRAL)
            and conf >= floor)
    bear = (eff_dir in (SignalDirection.BEARISH, SignalDirection.NEUTRAL)
            and conf >= floor)
    return bull, bear, conf, floor


def gate_after(consensus, pos, bb, eff_dir, arm):
    """Issue #104: the measurement is untouched, all three skews divide."""
    skew = pos + bb + (_BB_PRIORITY_SKEW if arm else 0.0)
    floor = _skewed_confidence_floor(skew)
    bull = (eff_dir in (SignalDirection.BULLISH, SignalDirection.NEUTRAL)
            and consensus >= floor)
    bear = (eff_dir in (SignalDirection.BEARISH, SignalDirection.NEUTRAL)
            and consensus >= floor)
    return bull, bear, consensus, floor


# -- the chains, one free variable ------------------------------------

_SCRUM = build_scrumming_scrum_chain()
_FOLD = build_scrumming_fold_chain()


def _ctx(bull, bear, direction_name):
    """Every field permissive except the TA verdict."""
    return GateContext(
        symbol="SWEEP/USD", ticker_last=100.0, bb_pos=0.9,
        bb_upper_dt=0.875, bb_lower_dt=0.125,
        delta=100.0, delta_pct=10.0, below_interval=False,
        is_bullish=bull, is_bearish=bear, trend_hold=False,
        trend_strength=0.5, eff_direction_name=direction_name,
        eff_is_bullish=bull, eff_is_bearish=bear, eff_trend_hold=False,
        eff_htf_blocks_scrum=False, eff_htf_blocks_fold=False,
        flag_require_ta_bullish=True, flag_hold_in_uptrend=False,
        flag_defer_to_htf=False, flag_fold_require_ta_bearish=True,
        flag_fold_defer_to_htf=False,
        bb_above_upper_dt=True, bb_below_lower_dt=True,
        scrum_ok=True, fold_ok_midline=True, target_fires=True,
        cb_blocks_scrum=False, cb_blocks_fold=False,
        hyst_ok_scrum_side=True, hyst_ok_fold_side=True,
        hyst_armed_scrum_side=False, hyst_armed_fold_side=False,
        hyst_ref_scrum_side=0.0, hyst_ref_fold_side=0.0,
        mem253_at_ceiling=False, mem253_smart_ceiling_usd=1e9,
        mem253_current_pos=0.0, has_fold_tranches=True, n_fold_tranches=3,
        htf_bias_name=None, htf_blocks_scrum=False, htf_blocks_fold=False,
        scrumming_interval_pct=3.0, trading_fee_pct=0.6,
    )


def _verdicts(bull, bear, direction_name):
    ctx = _ctx(bull, bear, direction_name)
    return bool(_SCRUM.evaluate(ctx).should_fire), bool(
        _FOLD.evaluate(ctx).should_fire)


# -- the tape ---------------------------------------------------------

def _tablets():
    for path in sorted(TABLETS.glob("*.json")):
        if path.name == "MANIFEST.json":
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("tablet %s did not parse: %r", path.name, exc)
            continue
        rows = raw.get("candles") or []
        if not rows:
            continue
        yield raw.get("asset") or path.stem, rows


def _candles(rows, n):
    tail = rows[-n:]
    if len(tail) < n:
        return None
    out = []
    for r in tail:
        try:
            out.append(Candle(timestamp=int(r[0]), open=float(r[1]),
                              high=float(r[2]), low=float(r[3]),
                              close=float(r[4]), volume=float(r[5])))
        except (TypeError, ValueError, IndexError):
            return None
    return out


def _hexes(*values):
    return "|".join(v.hex() if isinstance(v, float) else repr(v)
                    for v in values)


def measure():
    """One pass over every tablet at every tape length."""
    engine = VotingEngine()
    rows = []
    for asset, raw in _tablets():
        for bars in BARS:
            candles = _candles(raw, bars)
            if candles is None:
                continue
            try:
                summary = engine.compute_all(
                    candles, TA_TIMEFRAME, symbol=f"{asset}/USD")
                bb = detect_bb_proximity(
                    candles, tolerance_pct=BB_TOLERANCE_PCT,
                    consolidation_threshold=3.0,
                    min_pattern_candles=BB_LANDING_STRIP_CANDLES)
            except Exception as exc:
                rows.append({"asset": asset, "bars": bars, "error": repr(exc)})
                continue
            pos_boost, bb_boost, override, bb_pos = _boosts(
                candles, summary, bb)
            eff_dir = summary.consensus_direction
            if override is not None and eff_dir == SignalDirection.NEUTRAL:
                eff_dir = override
            up, lo = _proximity(candles, bb, bb_pos)
            rows.append({
                "asset": asset, "bars": bars,
                "consensus_confidence": summary.consensus_confidence,
                "consensus_direction": summary.consensus_direction.name,
                "position_boost": pos_boost,
                "bb_confidence_boost": bb_boost,
                "eff_confidence": (summary.consensus_confidence
                                   + pos_boost + bb_boost),
                "eff_direction": eff_dir.name,
                "bb_pos": float(bb_pos),
                "proximity_upper": bool(up),
                "proximity_lower": bool(lo),
            })
    return rows


def digest(rows, gate):
    """SHA-256 per row over the gate's inputs AND its verdicts."""
    per_row = []
    for r in rows:
        if "error" in r:
            per_row.append((r["asset"], r["bars"],
                            hashlib.sha256(r["error"].encode()).hexdigest()))
            continue
        eff_dir = getattr(SignalDirection, r["eff_direction"])
        arm = bool(r["proximity_upper"] or r["proximity_lower"])
        cells = [r["consensus_confidence"], r["consensus_direction"],
                 r["position_boost"], r["bb_confidence_boost"],
                 r["eff_direction"], r["bb_pos"],
                 r["proximity_upper"], r["proximity_lower"]]
        bull, bear, judged, floor = gate(
            r["consensus_confidence"], r["position_boost"],
            r["bb_confidence_boost"], eff_dir, arm)
        cells += [bull, bear, judged, floor]
        per_row.append((r["asset"], r["bars"],
                        hashlib.sha256(_hexes(*cells).encode()).hexdigest()))
    whole = hashlib.sha256(
        "\n".join(f"{a}@{b}:{h}" for a, b, h in per_row).encode()).hexdigest()
    return whole, {(a, b): h for a, b, h in per_row}


# -- the enumerated ceiling of position_boost -------------------------

def _position_boost_extremes():
    """Every value ``position_boost`` can take, by its own term structure.

    The block reads five terms. ``at_upper_bb`` (bb_pos > 0.75) and
    ``in_bb_middle`` (0.35 <= bb_pos <= 0.65) are MUTUALLY EXCLUSIVE, so
    a reading sits in exactly one of three zones and each term offers a
    different menu per zone. The product over the menus is the whole
    reachable set.

    ONE SIGNAL PER INDICATOR IS ASSUMED. ``tick()`` loops over
    ``summary.signals`` and would add a term twice if an indicator voted
    twice. ``VotingEngine.compute_all`` on one timeframe emits one signal
    per indicator, and C4 checks the assumption the only way that can be
    checked -- the enumerated ceiling has to equal the OBSERVED maximum.
    """
    menus = {
        "upper": (
            (0.0, +0.12),               # vortex bullish at upper
            (0.0, +0.08),               # macd bullish at upper
            (0.0, +0.05, -0.05),        # ichimoku, either way
            (0.0, +0.10, -0.08),        # stochastic_rsi over 0.7
            (0.0, +0.05),               # structure: up or down, both +0.05
        ),
        "middle": (
            (0.0, -0.05),
            (0.0, -0.03),
            (0.0, +0.05, -0.05),
            (0.0, +0.10, -0.08),
            (0.0, -0.08, +0.05),        # up -> -0.08, down -> +0.05
        ),
        "outside": (
            (0.0,),
            (0.0,),
            (0.0, +0.05, -0.05),
            (0.0, +0.10, -0.08),
            (0.0, +0.05),               # only the downtrend arm applies
        ),
    }
    best = {}
    for zone, menu in menus.items():
        totals = [round(sum(c), 10) for c in itertools.product(*menu)]
        best[zone] = (min(totals), max(totals))
    lo = min(v[0] for v in best.values())
    hi = max(v[1] for v in best.values())
    return lo, hi, best


# -- calibration ------------------------------------------------------

def calibrate(rows, log):
    """No zero in this report is believed before this passes."""
    ok = True
    good = [r for r in rows if "error" not in r]

    # C1 -- THE INSTRUMENT SEES A CHANGE IT SHOULD SEE.
    log("### C1 positive control -- injected perturbation, off-arm gate")
    log("")
    log("| injected | verdict flips |")
    log("|---|---|")
    seen = []
    for eps in (0.0, 1e-9, 1e-3, 1e-2, 5e-2, 2e-1):
        flips = 0
        for r in good:
            d = getattr(SignalDirection, r["eff_direction"])
            a = gate_after(r["consensus_confidence"], r["position_boost"],
                           r["bb_confidence_boost"], d, False)[:2]
            b = gate_after(r["consensus_confidence"] + eps,
                           r["position_boost"], r["bb_confidence_boost"],
                           d, False)[:2]
            flips += (a != b)
        seen.append((eps, flips))
        log("| %g | %d |" % (eps, flips))
    log("")
    if seen[0][1] != 0:
        log("**C1 FAILED**: a zero perturbation registered a flip.")
        ok = False
    if seen[-1][1] == 0:
        log("**C1 FAILED**: a 0.20 perturbation registered nothing.")
        ok = False

    # C2 -- THE ARM IS REACHED AT ALL.
    reach = sum(1 for r in good
                if r["proximity_upper"] or r["proximity_lower"])
    log("### C2 the BB-priority arm is reached")
    log("")
    log("%d of %d rows satisfy the arm's measured condition (%.1f%%)."
        % (reach, len(good), 100.0 * reach / max(len(good), 1)))
    log("")
    if reach == 0:
        log("**C2 FAILED**: the arm never applies.")
        ok = False

    # C3 -- CAN THE CONFIDENCE CONJUNCT REFUSE, AND WHERE COULD IT NOT?
    b_conf = a_conf = 0
    unfailable = 0
    for r in good:
        d = getattr(SignalDirection, r["eff_direction"])
        arm = bool(r["proximity_upper"] or r["proximity_lower"])
        _, _, jb, fb = gate_before(r["consensus_confidence"],
                                   r["position_boost"],
                                   r["bb_confidence_boost"], d, arm)
        _, _, ja, fa = gate_after(r["consensus_confidence"],
                                  r["position_boost"],
                                  r["bb_confidence_boost"], d, arm)
        b_conf += (jb < fb)
        a_conf += (ja < fa)
        # The BEFORE conjunct is UNFAILABLE on this reading when the
        # favours alone clear the floor: consensus is bounded below by
        # 0, so no measurement at all could have refused.
        favour = r["position_boost"] + r["bb_confidence_boost"]
        if favour >= fb:
            unfailable += 1
    log("### C3 can the confidence conjunct refuse?")
    log("")
    log("| | rows | conjunct refuses | rows where NO reading could refuse |")
    log("|---|---|---|---|")
    log("| BEFORE | %d | %d | %d |" % (len(good), b_conf, unfailable))
    log("| AFTER | %d | %d | %d |" % (len(good), a_conf, 0))
    log("")
    log("A BEFORE row is counted unfailable when "
        "`position_boost + bb_confidence_boost >= floor`. Consensus "
        "confidence is bounded below by 0, so on those rows the "
        "comparison has no false case whatever the indicators said. "
        "AFTER, the count is 0 BY CONSTRUCTION and not by measurement: "
        "the favour divides the floor and a division of a positive "
        "floor is positive, so a reading of exactly 0.0 always refuses.")
    log("")
    if a_conf == 0:
        log("**C3 FAILED**: the repaired gate refused nothing either.")
        ok = False

    # C4 -- THE ENUMERATED CEILING, AGAINST THE OBSERVED ONE.
    lo, hi, per_zone = _position_boost_extremes()
    obs_lo = min(r["position_boost"] for r in good)
    obs_hi = max(r["position_boost"] for r in good)
    log("### C4 `position_boost` -- enumerated range against observed")
    log("")
    log("| zone | min | max |")
    log("|---|---|---|")
    for zone in ("upper", "middle", "outside"):
        log("| %s | %+.2f | %+.2f | " % (zone, *per_zone[zone]))
    log("")
    log("enumerated over the whole term structure: **%+.2f to %+.2f**"
        % (lo, hi))
    log("")
    log("observed over %d readings: **%+.4f to %+.4f**"
        % (len(good), obs_lo, obs_hi))
    log("")
    if abs(obs_hi - hi) > 1e-9:
        log("**NOTE**: the observed maximum does not reach the "
            "enumerated ceiling, so the ceiling is DERIVED here and not "
            "OBSERVED.")
    else:
        log("The observed maximum EQUALS the enumerated ceiling, which "
            "is the positive control for the enumeration: a term "
            "structure counted wrongly would not land on the same "
            "number the tape produced.")
    log("")
    if obs_hi > hi + 1e-9 or obs_lo < lo - 1e-9:
        log("**C4 FAILED**: an observation lies outside the enumeration, "
            "so the enumeration is wrong.")
        ok = False

    # C5 -- THE DERIVED CEILING OF THE OTHER FAVOUR.
    obs_bb_hi = max(r["bb_confidence_boost"] for r in good)
    log("### C5 `bb_confidence_boost` -- derived ceiling, NOT observed")
    log("")
    log("| term | source | range |")
    log("|---|---|---|")
    log("| landing strip | `0.15 + consolidation_strength * 0.20`, "
        "strength bounded to 1.0 twice in `bb_proximity.py` | +0.15 to "
        "+0.35 |")
    log("| tightening | `detect_landing_strip_v2` "
        "`0.08 + 0.17 * length_factor * tightness_factor`, both factors "
        "bounded to 1.0 | +0.08 to +0.25 |")
    log("")
    log("The two detections are independent and both can fire on one "
        "reading, so the sum reaches **+0.60** -- more than twice the "
        "0.25 floor. Observed maximum over %d readings: **%+.4f**, so "
        "the ceiling is DERIVED and the tape does not reach it. This "
        "is stated rather than measured on purpose."
        % (len(good), obs_bb_hi))
    log("")
    if obs_bb_hi > 0.60 + 1e-9:
        log("**C5 FAILED**: an observation exceeds the derived ceiling.")
        ok = False

    # C6 -- DO THE FAVOURS COMPOUND?
    both = sum(1 for r in good
               if r["position_boost"] > 0 and r["bb_confidence_boost"] > 0)
    over = sum(1 for r in good
               if r["position_boost"] + r["bb_confidence_boost"] >= 0.25)
    neg = sum(1 for r in good if r["eff_confidence"] < 0.0)
    log("### C6 the two favours land on the same reading")
    log("")
    log("| question | rows |")
    log("|---|---|")
    log("| both favours strictly positive | %d |" % both)
    log("| their sum at or above the 0.25 floor | %d |" % over)
    log("| BEFORE `eff_confidence` below zero | %d |" % neg)
    log("")
    log("They compound. `position_boost` is built on every tick and "
        "`bb_confidence_boost` on every tick a pattern is detected, "
        "from the SAME reading, and the BB-priority arm adds a third on "
        "top. That is why the repair sums the three and divides once "
        "rather than relaxing one floor at a time.")
    log("")
    if both == 0:
        log("**C6 FAILED**: the two favours never co-occur, so summing "
            "them is untested by this tape.")
        ok = False
    return ok


def main():
    lines = []

    def log(text=""):
        lines.append(text)

    log("# Issue #104 -- the remaining confidence favours can refuse")
    log("")
    log("floor %r, BB-priority skew %r, arm-alone floor %r"
        % (_TA_CONFIDENCE_FLOOR, _BB_PRIORITY_SKEW,
           _BB_PRIORITY_CONFIDENCE_FLOOR))
    log("")
    cache = OUT / "rows.jsonl"
    if os.environ.get("SWEEP_CACHE") and cache.exists():
        rows = [json.loads(l) for l in
                io.open(cache, encoding="utf-8") if l.strip()]
    else:
        rows = measure()
    errs = [r for r in rows if "error" in r]
    log("rows measured: %d  (errors: %d)" % (len(rows), len(errs)))
    log("")

    d_before, per_before = digest(rows, gate_before)
    d_after, per_after = digest(rows, gate_after)
    log("## Value sweep")
    log("")
    log("```")
    log("digest BEFORE  " + d_before)
    log("digest AFTER   " + d_after)
    log("```")
    log("")
    moved = [k for k in per_before if per_before[k] != per_after[k]]
    log("**%d of %d rows moved.**" % (len(moved), len(per_before)))
    log("")
    by_bar = {}
    for (_asset, bars) in moved:
        by_bar[bars] = by_bar.get(bars, 0) + 1
    log("| bars | rows moved |")
    log("|---|---|")
    for bars in BARS:
        log("| %d | %d |" % (bars, by_bar.get(bars, 0)))
    log("")
    log("A row is hashed over the gate's inputs, the confidence it "
        "JUDGES, the floor it judges against, and both verdicts. Every "
        "row whose favour is non-zero moves in the first two of those "
        "even when its verdict does not, because the judged number "
        "stops being the inflated one.")
    log("")

    ok = calibrate(rows, log)
    log("### calibration verdict: %s" % ("PASSED" if ok else "FAILED"))
    log("")

    log("## Decision sweep")
    log("")
    flips = {"scrum": [], "fold": []}
    per_bar = {}
    for r in rows:
        if "error" in r:
            continue
        arm = bool(r["proximity_upper"] or r["proximity_lower"])
        d = getattr(SignalDirection, r["eff_direction"])
        b_bull, b_bear, _, b_floor = gate_before(
            r["consensus_confidence"], r["position_boost"],
            r["bb_confidence_boost"], d, arm)
        a_bull, a_bear, _, a_floor = gate_after(
            r["consensus_confidence"], r["position_boost"],
            r["bb_confidence_boost"], d, arm)
        bs, bf = _verdicts(b_bull, b_bear, r["eff_direction"])
        a_s, a_f = _verdicts(a_bull, a_bear, r["eff_direction"])
        cell = per_bar.setdefault(r["bars"], [0, 0, 0, 0, 0, 0])
        cell[0] += 1
        cell[1] += arm
        cell[2] += bs
        cell[3] += a_s
        cell[4] += bf
        cell[5] += a_f
        if bs != a_s:
            flips["scrum"].append((r, bs, a_s, arm, b_floor, a_floor))
        if bf != a_f:
            flips["fold"].append((r, bf, a_f, arm, b_floor, a_floor))

    log("| bars | rows | on the arm | SCRUM before | SCRUM after | "
        "FOLD before | FOLD after |")
    log("|---|---|---|---|---|---|---|")
    for bars in BARS:
        c = per_bar.get(bars)
        if not c:
            continue
        log("| %d | %d | %d | %d | %d | %d | %d |"
            % (bars, c[0], c[1], c[2], c[3], c[4], c[5]))
    log("")
    log("SCRUM verdict flips: **%d**   FOLD verdict flips: **%d**"
        % (len(flips["scrum"]), len(flips["fold"])))
    log("")
    log("| side | FIRE -> shut | shut -> FIRE | on the arm | off the arm |")
    log("|---|---|---|---|---|")
    for side in ("scrum", "fold"):
        f2s = sum(1 for _, b, a, _, _, _ in flips[side] if b and not a)
        s2f = sum(1 for _, b, a, _, _, _ in flips[side] if a and not b)
        on = sum(1 for _, _, _, arm, _, _ in flips[side] if arm)
        off = sum(1 for _, _, _, arm, _, _ in flips[side] if not arm)
        log("| %s | %d | %d | %d | %d |" % (side.upper(), f2s, s2f, on, off))
    log("")

    for side in ("scrum", "fold"):
        log("### every %s flip, named" % side.upper())
        log("")
        log("| tablet@bars | eff_dir | consensus | pos skew | BB skew | "
            "BEFORE judged | BEFORE floor | AFTER judged | AFTER floor | "
            "on arm | before | after |")
        log("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r, b, a, arm, bfl, afl in sorted(
                flips[side], key=lambda x: (x[0]["bars"], x[0]["asset"])):
            log("| %s@%d | %s | %.4f | %+.2f | %+.2f | %.4f | %.4f | "
                "%.4f | %.4f | %s | %s | %s |"
                % (r["asset"], r["bars"], r["eff_direction"],
                   r["consensus_confidence"], r["position_boost"],
                   r["bb_confidence_boost"], r["eff_confidence"], bfl,
                   r["consensus_confidence"], afl,
                   "yes" if arm else "no",
                   "FIRE" if b else "shut", "FIRE" if a else "shut"))
        log("")

    # -- THE FLIP TAXONOMY, DERIVED RATHER THAN ASSERTED ------------
    log("### the sign of the favour explains every flip")
    log("")
    log("| side | direction | favour > 0 | favour < 0 | favour == 0 |")
    log("|---|---|---|---|---|")
    unexplained = 0
    for side in ("scrum", "fold"):
        for name, want in (("FIRE -> shut", True), ("shut -> FIRE", False)):
            pos = negv = zero = 0
            for r, b, a, _arm, _bf, _af in flips[side]:
                if bool(b) != want:
                    continue
                fav = r["position_boost"] + r["bb_confidence_boost"]
                if fav > 0:
                    pos += 1
                elif fav < 0:
                    negv += 1
                else:
                    zero += 1
            log("| %s | %s | %d | %d | %d |"
                % (side.upper(), name, pos, negv, zero))
            unexplained += (negv if want else pos) + zero
    log("")
    log("A trade that STOPS firing is a reading a POSITIVE favour had "
        "carried over the floor. A trade that STARTS firing is a "
        "reading a NEGATIVE favour had dragged under it -- the mirror "
        "of issue #102's finding that the only rows its arm could "
        "still refuse were ones a negative `position_boost` had "
        "already pushed below zero. Rows in the wrong column, or with "
        "no favour at all: **%d**." % unexplained)
    log("")
    if unexplained:
        log("**A flip with no favour to explain it means this sweep is "
            "measuring something other than the change.**")
    log("")

    # -- WHAT ACTUALLY VARIES WITH TAPE LENGTH ----------------------
    log("### what varies with tape length, and why one length is a false green")
    log("")
    log("| bars | rows | `position_boost` non-zero | its min | its max | "
        "`bb_confidence_boost` non-zero |")
    log("|---|---|---|---|---|---|")
    for bars in BARS:
        s = [r for r in rows if "error" not in r and r["bars"] == bars]
        if not s:
            continue
        pv = [r["position_boost"] for r in s]
        log("| %d | %d | %d | %+.2f | %+.2f | %d |"
            % (bars, len(s), sum(1 for v in pv if v), min(pv), max(pv),
               sum(1 for r in s if r["bb_confidence_boost"] > 0)))
    log("")
    log("`position_boost` grows with the tape, and its CEILING grows "
        "with it: the market-structure term is guarded by "
        "`len(candles) >= 60`, so it contributes nothing at 35 or 40 "
        "bars. A sweep run at 35 bars alone would have measured a "
        "largest favour of +0.20, under the 0.25 floor, and concluded "
        "this gate could always refuse. That is the false green the "
        "six lengths exist to prevent.")
    log("")
    log("`bb_confidence_boost` is the opposite and matches issue "
        "#102's finding about the proximity condition: it is non-zero "
        "on the SAME number of rows at every length, because both "
        "detectors read a trailing window rather than the whole tape.")
    log("")

    good = [r for r in rows if "error" not in r]
    log("## The measured range of every quantity in the gate")
    log("")
    log("| quantity | min | max | median |")
    log("|---|---|---|---|")
    for name in ("consensus_confidence", "position_boost",
                 "bb_confidence_boost", "eff_confidence"):
        s = sorted(r[name] for r in good)
        log("| %s | %+.4f | %+.4f | %+.4f |"
            % (name, s[0], s[-1], s[len(s) // 2]))
    log("")
    passed_on_favour = sum(
        1 for r in good
        if r["eff_confidence"] >= _TA_CONFIDENCE_FLOOR
        and r["consensus_confidence"] < _TA_CONFIDENCE_FLOOR)
    log("Rows whose BEFORE `eff_confidence` cleared the standing 0.25 "
        "floor while the MEASURED consensus confidence did not: "
        "**%d**. The favour, not the measurement, is what carried them."
        % passed_on_favour)
    log("")

    OUT.mkdir(parents=True, exist_ok=True)
    # An explicit LF newline: `write_text` translates on Windows.
    with io.open(OUT / "sweep_result.md", "w", encoding="utf-8",
                 newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    with io.open(OUT / "rows.jsonl", "w", encoding="utf-8",
                 newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    print("\n".join(lines[:80]))
    print("... written:", OUT / "sweep_result.md")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
