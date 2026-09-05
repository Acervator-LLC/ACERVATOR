"""Issue #102 -- the value sweep and the DECISION sweep, calibrated first.

WHAT IT MEASURES. The BB-priority arm of the TA confidence gate in
``ScrummingBot.tick()``, before and after the repair, over all 406 stone
tablets at six tape lengths.

  BEFORE:  eff_confidence + 0.30  >=  _TA_CONFIDENCE_FLOOR (0.25)
  AFTER:   eff_confidence         >=  _BB_PRIORITY_CONFIDENCE_FLOOR

WHY THE GATE IS REPLICATED HERE RATHER THAN CALLED. ``tick()`` is a
4,500-line coroutine that needs an exchange, a bus and a live ladder. The
confidence pipeline inside it is a pure function of the candle tape, and
that is what this file rebuilds: the voting engine, the two boosts, the
BB zones and the arm's proximity test, each copied from the shipping
source at the line it lives on. ``_TA_CONFIDENCE_FLOOR`` and
``_BB_PRIORITY_CONFIDENCE_FLOOR`` are imported from the module rather
than restated; the rest of the copy has no pin against the module.

WHAT IS SWEPT AND WHAT IS HELD. Proximity is MEASURED from the tape. The
arm's other two conditions -- opposing-trade hysteresis and an available
target delta -- are bot state that no tablet carries, so they are held
PERMISSIVE. That is the arm at its widest, which is the case the defect
is about.

CALIBRATION COMES FIRST. Two false zeros were caught on 2026-08-23: #99's
instrument reported zero decisions until it was rebuilt, and #100 found
this gate returns a STRUCTURAL zero. Every zero this file prints is
preceded by a positive control that proves the instrument can register a
change of that kind.

READ-ONLY. It opens ``~/.acervator/stone_tablets`` and writes nothing
outside its own output directory.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("acervator.audits.issue_102")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.trading.gate_chain import (  # noqa: E402
    GateContext,
    build_scrumming_fold_chain,
    build_scrumming_scrum_chain,
)
from src.trading.indicators.bb_proximity import detect_bb_proximity  # noqa: E402
from src.trading.indicators.landing_strip import detect_landing_strip_v2  # noqa: E402
from src.trading.indicators.types import Candle, SignalDirection  # noqa: E402
from src.trading.scrumming_bot import (  # noqa: E402
    _BB_PRIORITY_CONFIDENCE_FLOOR,
    _BB_PRIORITY_SKEW,
    _TA_CONFIDENCE_FLOOR,
)
from src.trading.ta_engine import VotingEngine  # noqa: E402

TABLETS = Path.home() / ".acervator" / "stone_tablets"
OUT = REPO / "artifacts" / "confidence-gate-sweep"
BARS = (35, 40, 60, 100, 200, 400)

# BotConfig defaults, src/trading/bot_container.py:201-209.
BB_TOLERANCE_PCT = 1.0
BB_LANDING_STRIP_CANDLES = 3
TA_TIMEFRAME = "1h"
SCRUM_DETECT_PCT = 75.0

# _bb_detect_thresholds(), scrumming_bot.py:4540. detect_frac = 0.75.
_DETECT_FRAC = SCRUM_DETECT_PCT / 100.0
UPPER_DETECT = 0.5 + _DETECT_FRAC / 2.0
LOWER_DETECT = 0.5 - _DETECT_FRAC / 2.0

# The inline Bullseye tolerances, scrumming_bot.py:8168-8170.
TOUCH_TOL = 0.005
WICK_TOL = 0.002


# ── the confidence pipeline, copied from tick() ──────────────────────


def _boosts(candles, summary, bb_result):
    """``position_boost`` and ``bb_confidence_boost``, as tick() builds them.

    position_boost: scrumming_bot.py:7981-8026.
    bb_confidence_boost: scrumming_bot.py:7861-7889.
    """
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
                candles, min_consecutive=3, shrink_threshold=0.90, bb_tolerance_pct=3.0
            )
            if tightening and tightening.detected:
                bb_boost += tightening.confidence_boost
        except Exception as exc:
            # tick() suppresses the same way at scrumming_bot.py:7893.
            logger.debug("landing-strip v2 declined: %r", exc)

    pos = 0.0
    if summary:
        for sig in summary.signals:
            if sig.indicator == "vortex" and sig.direction == SignalDirection.BULLISH:
                if at_upper_bb and sig.confidence > 0.5:
                    pos += 0.12
                elif in_bb_middle:
                    pos -= 0.05
            if sig.indicator == "macd" and sig.direction == SignalDirection.BULLISH:
                if at_upper_bb and sig.confidence > 0.3:
                    pos += 0.08
                elif in_bb_middle:
                    pos -= 0.03
            if sig.indicator == "ichimoku" and sig.direction == SignalDirection.BULLISH:
                pos += 0.05
            elif (
                sig.indicator == "ichimoku" and sig.direction == SignalDirection.BEARISH
            ):
                pos -= 0.05
            if sig.indicator == "stochastic_rsi" and sig.confidence > 0.7:
                if sig.direction == SignalDirection.BEARISH:
                    pos += 0.10
                elif sig.direction == SignalDirection.BULLISH:
                    pos -= 0.08
    if len(candles) >= 60:
        sw = 20
        highs = [c.high for c in candles[-sw * 3 :]]
        lows = [c.low for c in candles[-sw * 3 :]]
        if len(highs) >= sw * 3:
            rh, ph = max(highs[-sw:]), max(highs[-sw * 2 : -sw])
            rl, pl = min(lows[-sw:]), min(lows[-sw * 2 : -sw])
            if rh > ph and rl > pl:
                if at_upper_bb:
                    pos += 0.05
                elif in_bb_middle:
                    pos -= 0.08
            elif rh < ph and rl < pl:
                pos += 0.05
    return pos, bb_boost, override_direction, bb_pos


def _proximity(candles, bb_result, bb_pos):
    """``_bb_proximity_upper`` / ``_bb_proximity_lower``, scrumming_bot.py:8153-8213."""
    be_up = be_up_wick = be_lo = be_lo_wick = False
    price = candles[-1].close
    if (
        bb_result is not None
        and getattr(bb_result, "upper", 0) > 0
        and getattr(bb_result, "lower", 0) > 0
    ):
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


# ── the gate, both sides of the repair ───────────────────────────────


def gate_before(eff_conf, eff_dir, arm):
    """v3.15.64: the skew is ADDED to the measurement, floor stays 0.25."""
    conf = eff_conf
    if arm:
        conf = max(0.0, min(1.0, eff_conf + 0.30))
    bull = (
        eff_dir in (SignalDirection.BULLISH, SignalDirection.NEUTRAL) and conf >= 0.25
    )
    bear = (
        eff_dir in (SignalDirection.BEARISH, SignalDirection.NEUTRAL) and conf >= 0.25
    )
    return bull, bear, conf


def gate_after(eff_conf, eff_dir, arm):
    """Issue #102: the measurement is untouched, the floor is relaxed."""
    floor = _BB_PRIORITY_CONFIDENCE_FLOOR if arm else _TA_CONFIDENCE_FLOOR
    bull = (
        eff_dir in (SignalDirection.BULLISH, SignalDirection.NEUTRAL)
        and eff_conf >= floor
    )
    bear = (
        eff_dir in (SignalDirection.BEARISH, SignalDirection.NEUTRAL)
        and eff_conf >= floor
    )
    return bull, bear, eff_conf


# ── the chains, one free variable ────────────────────────────────────

_SCRUM = build_scrumming_scrum_chain()
_FOLD = build_scrumming_fold_chain()


def _ctx(bull, bear, direction_name):
    """Every field permissive except the TA verdict."""
    return GateContext(
        symbol="SWEEP/USD",
        ticker_last=100.0,
        bb_pos=0.9,
        bb_upper_dt=0.875,
        bb_lower_dt=0.125,
        delta=100.0,
        delta_pct=10.0,
        below_interval=False,
        is_bullish=bull,
        is_bearish=bear,
        trend_hold=False,
        trend_strength=0.5,
        eff_direction_name=direction_name,
        eff_is_bullish=bull,
        eff_is_bearish=bear,
        eff_trend_hold=False,
        eff_htf_blocks_scrum=False,
        eff_htf_blocks_fold=False,
        flag_require_ta_bullish=True,
        flag_hold_in_uptrend=False,
        flag_defer_to_htf=False,
        flag_fold_require_ta_bearish=True,
        flag_fold_defer_to_htf=False,
        bb_above_upper_dt=True,
        bb_below_lower_dt=True,
        scrum_ok=True,
        fold_ok_midline=True,
        target_fires=True,
        cb_blocks_scrum=False,
        cb_blocks_fold=False,
        hyst_ok_scrum_side=True,
        hyst_ok_fold_side=True,
        hyst_armed_scrum_side=False,
        hyst_armed_fold_side=False,
        hyst_ref_scrum_side=0.0,
        hyst_ref_fold_side=0.0,
        mem253_at_ceiling=False,
        mem253_smart_ceiling_usd=1e9,
        mem253_current_pos=0.0,
        has_fold_tranches=True,
        n_fold_tranches=3,
        htf_bias_name=None,
        htf_blocks_scrum=False,
        htf_blocks_fold=False,
        scrumming_interval_pct=3.0,
        trading_fee_pct=0.6,
    )


def _verdicts(bull, bear, direction_name):
    ctx = _ctx(bull, bear, direction_name)
    s = _SCRUM.evaluate(ctx)
    f = _FOLD.evaluate(ctx)
    return bool(s.should_fire), bool(f.should_fire), s, f


# ── the tape ─────────────────────────────────────────────────────────


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


def _hexes(*values):
    parts = []
    for v in values:
        if isinstance(v, float):
            parts.append(v.hex())
        else:
            parts.append(repr(v))
    return "|".join(parts)


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
                    candles, TA_TIMEFRAME, symbol=f"{asset}/USD"
                )
                bb = detect_bb_proximity(
                    candles,
                    tolerance_pct=BB_TOLERANCE_PCT,
                    consolidation_threshold=3.0,
                    min_pattern_candles=BB_LANDING_STRIP_CANDLES,
                )
            except Exception as exc:
                rows.append({"asset": asset, "bars": bars, "error": repr(exc)})
                continue
            pos_boost, bb_boost, override, bb_pos = _boosts(candles, summary, bb)
            eff_conf = summary.consensus_confidence + pos_boost + bb_boost
            eff_dir = summary.consensus_direction
            if override is not None and eff_dir == SignalDirection.NEUTRAL:
                eff_dir = override
            up, lo = _proximity(candles, bb, bb_pos)
            rows.append(
                {
                    "asset": asset,
                    "bars": bars,
                    "consensus_confidence": summary.consensus_confidence,
                    "consensus_direction": summary.consensus_direction.name,
                    "position_boost": pos_boost,
                    "bb_confidence_boost": bb_boost,
                    "eff_confidence": eff_conf,
                    "eff_direction": eff_dir.name,
                    "bb_pos": float(bb_pos),
                    "proximity_upper": bool(up),
                    "proximity_lower": bool(lo),
                }
            )
    return rows


def digest(rows, gate):
    """SHA-256 per row over the gate's inputs AND its verdicts."""
    per_row = []
    for r in rows:
        if "error" in r:
            per_row.append(
                (r["asset"], r["bars"], hashlib.sha256(r["error"].encode()).hexdigest())
            )
            continue
        eff_dir = getattr(SignalDirection, r["eff_direction"])
        cells = [
            r["consensus_confidence"],
            r["consensus_direction"],
            r["position_boost"],
            r["bb_confidence_boost"],
            r["eff_confidence"],
            r["eff_direction"],
            r["bb_pos"],
            r["proximity_upper"],
            r["proximity_lower"],
        ]
        live_arm = bool(r["proximity_upper"] or r["proximity_lower"])
        for arm in (live_arm,):
            bull, bear, judged = gate(r["eff_confidence"], eff_dir, arm)
            cells += [bull, bear, judged]
        blob = _hexes(*cells)
        per_row.append(
            (r["asset"], r["bars"], hashlib.sha256(blob.encode()).hexdigest())
        )
    whole = hashlib.sha256(
        "\n".join(f"{a}@{b}:{h}" for a, b, h in per_row).encode()
    ).hexdigest()
    return whole, {(a, b): h for a, b, h in per_row}


# ── calibration ──────────────────────────────────────────────────────


def calibrate(rows, log):
    """No zero in this report is believed before this passes.

    Three controls, and each answers a different way of lying.
    """
    ok = True

    # C1 -- THE INSTRUMENT SEES A CHANGE IT SHOULD SEE. Perturb
    # eff_confidence by a known amount and count verdict flips on the
    # NON-arm gate. A blind instrument returns zero for every size.
    log("### C1 positive control -- injected perturbation, non-arm gate")
    log("")
    log("| injected | verdict flips |")
    log("|---|---|")
    seen = []
    for eps in (0.0, 1e-9, 1e-3, 1e-2, 5e-2, 2e-1):
        flips = 0
        for r in rows:
            if "error" in r:
                continue
            d = getattr(SignalDirection, r["eff_direction"])
            a = gate_after(r["eff_confidence"], d, False)[:2]
            b = gate_after(r["eff_confidence"] + eps, d, False)[:2]
            flips += a != b
        seen.append((eps, flips))
        log("| %g | %d |" % (eps, flips))
    log("")
    if seen[0][1] != 0:
        log("**C1 FAILED**: a zero perturbation registered a flip.")
        ok = False
    if seen[-1][1] == 0:
        log("**C1 FAILED**: a 0.20 perturbation registered nothing.")
        ok = False

    # C2 -- THE ARM IS REACHED AT ALL. A sweep of an arm that never
    # applies is a zero about the tape, not about the gate.
    reach = sum(
        1
        for r in rows
        if "error" not in r and (r["proximity_upper"] or r["proximity_lower"])
    )
    total = sum(1 for r in rows if "error" not in r)
    log("### C2 the arm is reached")
    log("")
    log(
        "%d of %d rows satisfy the arm's measured condition (%.1f%%)."
        % (reach, total, 100.0 * reach / max(total, 1))
    )
    log("")
    if reach == 0:
        log("**C2 FAILED**: the arm never applies.")
        ok = False

    # C3 -- THE STRUCTURAL ZERO, MEASURED RATHER THAN ASSERTED.
    arm_rows = b_all = a_all = 0
    b_conf = a_conf = 0
    for r in rows:
        if "error" in r:
            continue
        if not (r["proximity_upper"] or r["proximity_lower"]):
            continue
        arm_rows += 1
        d = getattr(SignalDirection, r["eff_direction"])
        if not any(gate_before(r["eff_confidence"], d, True)[:2]):
            b_all += 1
        if not any(gate_after(r["eff_confidence"], d, True)[:2]):
            a_all += 1
        judged = gate_before(r["eff_confidence"], d, True)[2]
        b_conf += judged < _TA_CONFIDENCE_FLOOR
        a_conf += r["eff_confidence"] < _BB_PRIORITY_CONFIDENCE_FLOOR
    log("### C3 can the confidence conjunct refuse on the arm?")
    log("")
    log("| | arm rows | confidence conjunct refuses | whole gate refuses |")
    log("|---|---|---|---|")
    log("| BEFORE | %d | %d | %d |" % (arm_rows, b_conf, b_all))
    log("| AFTER | %d | %d | %d |" % (arm_rows, a_conf, a_all))
    log("")
    if b_conf != 0:
        log("**NOTE**: the BEFORE confidence conjunct refused %d rows." % b_conf)
    if a_conf == 0:
        log(
            "**C3 FAILED**: the repaired gate refused nothing either, so "
            "the repair did not restore refusal."
        )
        ok = False
    return ok


def main():
    lines = []

    def log(text=""):
        lines.append(text)

    log("# Issue #102 -- the confidence gate can refuse")
    log("")
    log(
        "floor %r, favour %r, priority floor %r"
        % (_TA_CONFIDENCE_FLOOR, _BB_PRIORITY_SKEW, _BB_PRIORITY_CONFIDENCE_FLOOR)
    )
    log("")
    cache = OUT / "rows.jsonl"
    if os.environ.get("SWEEP_CACHE") and cache.exists():
        rows = [json.loads(l) for l in io.open(cache, encoding="utf-8") if l.strip()]
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
    for asset, bars in moved:
        by_bar[bars] = by_bar.get(bars, 0) + 1
    log("| bars | rows moved |")
    log("|---|---|")
    for bars in BARS:
        log("| %d | %d |" % (bars, by_bar.get(bars, 0)))
    log("")
    log(
        "A row is hashed at the arm state its own tape produces, so a "
        "moved row is a row whose LIVE evaluation moved. Rows off the arm "
        "are judged against the unchanged 0.25 floor and cannot move."
    )
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
        b_bull, b_bear, _ = gate_before(r["eff_confidence"], d, arm)
        a_bull, a_bear, _ = gate_after(r["eff_confidence"], d, arm)
        bs, bf, _, _ = _verdicts(b_bull, b_bear, r["eff_direction"])
        a_s, a_f, _, _ = _verdicts(a_bull, a_bear, r["eff_direction"])
        cell = per_bar.setdefault(r["bars"], [0, 0, 0, 0, 0, 0])
        cell[0] += 1
        cell[1] += arm
        cell[2] += bs
        cell[3] += a_s
        cell[4] += bf
        cell[5] += a_f
        if bs != a_s:
            flips["scrum"].append((r, bs, a_s, arm))
        if bf != a_f:
            flips["fold"].append((r, bf, a_f, arm))

    log(
        "| bars | rows | on the arm | SCRUM before | SCRUM after | "
        "FOLD before | FOLD after |"
    )
    log("|---|---|---|---|---|---|---|")
    for bars in BARS:
        c = per_bar.get(bars)
        if not c:
            continue
        log(
            "| %d | %d | %d | %d | %d | %d | %d |"
            % (bars, c[0], c[1], c[2], c[3], c[4], c[5])
        )
    log("")
    log(
        "SCRUM verdict flips: **%d**   FOLD verdict flips: **%d**"
        % (len(flips["scrum"]), len(flips["fold"]))
    )
    log("")
    log("| side | FIRE -> shut | shut -> FIRE | off the arm |")
    log("|---|---|---|---|")
    for side in ("scrum", "fold"):
        f2s = sum(1 for _, b, a, _ in flips[side] if b and not a)
        s2f = sum(1 for _, b, a, _ in flips[side] if a and not b)
        off = sum(1 for _, _, _, arm in flips[side] if not arm)
        log("| %s | %d | %d | %d |" % (side.upper(), f2s, s2f, off))
    log("")

    for side in ("scrum", "fold"):
        log("### every %s flip, named" % side.upper())
        log("")
        log(
            "| tablet@bars | eff_dir | consensus | pos boost | bb boost | "
            "eff_conf | on arm | before | after |"
        )
        log("|---|---|---|---|---|---|---|---|---|")
        for r, b, a, arm in sorted(
            flips[side], key=lambda x: (x[0]["bars"], x[0]["asset"])
        ):
            log(
                "| %s@%d | %s | %.4f | %+.2f | %.2f | %.4f | %s | %s | %s |"
                % (
                    r["asset"],
                    r["bars"],
                    r["eff_direction"],
                    r["consensus_confidence"],
                    r["position_boost"],
                    r["bb_confidence_boost"],
                    r["eff_confidence"],
                    "yes" if arm else "no",
                    "FIRE" if b else "shut",
                    "FIRE" if a else "shut",
                )
            )
        log("")

    good = [r for r in rows if "error" not in r]
    log("## The measured range of eff_confidence")
    log("")
    log("| quantity | min | max | median |")
    log("|---|---|---|---|")
    for name in (
        "consensus_confidence",
        "position_boost",
        "bb_confidence_boost",
        "eff_confidence",
    ):
        s = sorted(r[name] for r in good)
        log("| %s | %.4f | %.4f | %.4f |" % (name, s[0], s[-1], s[len(s) // 2]))
    log("")
    log("### the 71 rows the BEFORE arm could still refuse")
    log("")
    log("| tablet@bars | consensus | pos boost | bb boost | eff_conf |")
    log("|---|---|---|---|---|")
    for r in good:
        if not (r["proximity_upper"] or r["proximity_lower"]):
            continue
        if r["eff_confidence"] + 0.30 >= _TA_CONFIDENCE_FLOOR:
            continue
        log(
            "| %s@%d | %.4f | %+.2f | %.2f | %.4f |"
            % (
                r["asset"],
                r["bars"],
                r["consensus_confidence"],
                r["position_boost"],
                r["bb_confidence_boost"],
                r["eff_confidence"],
            )
        )
    log("")
    neg = sum(1 for r in good if r["eff_confidence"] < -0.05)
    log(
        "rows with eff_confidence < -0.05, the only reading the BEFORE arm "
        "could refuse: **%d**" % neg
    )
    log("")

    OUT.mkdir(parents=True, exist_ok=True)
    # An explicit LF newline: `write_text` translates on Windows, and
    # a CRLF pin on ONE file here once cost a whole suite.
    with io.open(OUT / "sweep_result.md", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    with io.open(OUT / "rows.jsonl", "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    print("\n".join(lines[:60]))
    print("... written:", OUT / "sweep_result.md")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
