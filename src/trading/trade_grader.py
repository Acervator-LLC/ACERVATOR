"""
sadp/_tools/trade_grader.py — v3.20.78 trade grading library.

Deterministic, read-only trade scoring across five axes:

  1. EXECUTION QUALITY    — fill price vs reference price at decision
                            tick (slippage in basis points)
  2. TIMING               — MFE / MAE (max favorable/adverse excursion)
                            in the N candles after the trade
  3. STRATEGIC ALIGNMENT  — did this trade improve or hurt the asset's
                            rolling S/B ratio?
  4. OUTCOME              — realized P&L per unit if the round-trip
                            closed; otherwise unrealized mark-to-mkt
  5. DECISION CONTEXT     — regime tag (BULL / BEAR / CHOP) for
                            attribution

Each axis produces a sub-score; the overall grade is a weighted
combination. Grades are A+ / A / B / C / D / F.

The grader is INTENTIONALLY:
  - Deterministic (same input → same grade)
  - Transparent (the rationale string explains the grade)
  - Read-only (grades NEVER feed back into trading decisions — that's
    a separate explicit operator decision; see MEM-424 lesson)
  - Composable with both production trade journal AND RAIntSimBat
    per-trade logs

Mirrors institutional Transaction Cost Analysis (TCA) practice but
adapted for the Acervator scrumming + extractor patterns: the
"strategic alignment" axis specifically tracks whether each trade
moves the asset's rolling S/B ratio in the operator-favored direction.

sadp: R28 R42 R55 R63 R68 R70
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# ─────────────────────────────────────────────────────────────────────
# Data shapes
# ─────────────────────────────────────────────────────────────────────


@dataclass
class TradeRecord:
    """A single executed trade. Both Coinbase CSV and RAIntSimBat
    per-trade logs normalize into this shape."""

    trade_id: str
    timestamp: Optional[datetime]
    asset: str
    side: str  # "buy" or "sell"
    price: float
    quantity: float
    fee: float
    subtotal: float = 0.0
    notes: str = ""


@dataclass
class PriceContext:
    """Surrounding-price context for grading a single trade.

    Fields are nullable because real-world trade journals don't always
    have every piece of context. The grader degrades gracefully —
    each axis is computed if its inputs are present, otherwise that
    axis contributes "N/A" to the rationale and doesn't affect the
    overall grade."""

    ref_price_at_decision: Optional[float] = None
    # Future prices = next N candles after the trade. Used for MFE/MAE.
    future_prices: list[float] = field(default_factory=list)
    # Rolling S/B ratio before this trade (avg_sell / avg_buy for the
    # asset using only trades up to but not including this one). The
    # grader compares before vs after to score strategic alignment.
    rolling_sb_before: Optional[float] = None
    rolling_sb_after: Optional[float] = None
    # Regime tag at the time of the trade. Free-form string.
    regime_tag: str = ""
    # Realized P&L if the round-trip has closed. None if still open.
    realized_pnl_per_unit: Optional[float] = None


@dataclass
class TradeGrade:
    """A graded trade — deterministic output of grade_trade()."""

    trade_id: str
    asset: str
    side: str
    timestamp: Optional[datetime]
    # Sub-scores in [0.0, 1.0]; None if not computable for this trade
    execution_score: Optional[float]
    timing_score: Optional[float]
    strategic_score: Optional[float]
    outcome_score: Optional[float]
    # Overall grade letter — A+/A/B/C/D/F
    overall: str
    # Numeric grade in [0.0, 1.0] used to compute the letter
    overall_numeric: float
    # Per-axis raw metrics
    execution_bps: Optional[float] = None
    mfe_pct: Optional[float] = None
    mae_pct: Optional[float] = None
    sb_improvement: Optional[float] = None
    realized_pnl_per_unit: Optional[float] = None
    regime: str = ""
    rationale: str = ""


# ─────────────────────────────────────────────────────────────────────
# Sub-scorers — each axis is a pure function
# ─────────────────────────────────────────────────────────────────────


def _score_execution(
    record: TradeRecord, ctx: PriceContext
) -> tuple[Optional[float], Optional[float]]:
    """Score execution quality from slippage in bps.

    Returns (score, bps). Score is 1.0 at zero slippage, 0.0 at 100bps
    (1.0% slip) or worse. Linear in between. None if no ref price.

    Slippage convention: for a buy, paying ABOVE ref = bad (positive
    bps); for a sell, receiving BELOW ref = bad (positive bps).
    """
    if ctx.ref_price_at_decision is None or ctx.ref_price_at_decision <= 0:
        return (None, None)
    ref = ctx.ref_price_at_decision
    if record.side == "buy":
        bps = (record.price - ref) / ref * 10000.0
    else:
        bps = (ref - record.price) / ref * 10000.0
    # Clamp to score in [0, 1]
    score = max(0.0, min(1.0, 1.0 - (bps / 100.0)))
    return (score, bps)


def _score_timing(
    record: TradeRecord, ctx: PriceContext
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Score timing from MFE / MAE.

    Returns (score, mfe_pct, mae_pct). Score is 1.0 when MFE > |MAE|
    (the trade got more favorable than adverse), 0.0 when MAE > MFE.

    For a BUY: favorable = price went UP after the buy. So
        MFE = (max_future - price) / price * 100
        MAE = (min_future - price) / price * 100   (negative)

    For a SELL: favorable = price went DOWN after the sell. So
        MFE = (price - min_future) / price * 100
        MAE = (price - max_future) / price * 100   (negative)
    """
    if not ctx.future_prices or record.price <= 0:
        return (None, None, None)
    fut = [p for p in ctx.future_prices if p > 0]
    if not fut:
        return (None, None, None)
    p_max = max(fut)
    p_min = min(fut)
    if record.side == "buy":
        mfe_pct = (p_max - record.price) / record.price * 100.0
        mae_pct = (p_min - record.price) / record.price * 100.0
    else:
        mfe_pct = (record.price - p_min) / record.price * 100.0
        mae_pct = (record.price - p_max) / record.price * 100.0
    # Score: balanced score from MFE/|MAE| ratio
    abs_mae = abs(mae_pct) if mae_pct < 0 else 0.0
    if mfe_pct <= 0:
        score = 0.0
    elif abs_mae <= 0:
        score = 1.0
    else:
        # ratio > 1 means MFE bigger than worst drawdown — good
        ratio = mfe_pct / abs_mae
        score = max(0.0, min(1.0, ratio / 3.0))  # ratio of 3+ caps at 1
    return (score, mfe_pct, mae_pct)


def _score_strategic(
    record: TradeRecord, ctx: PriceContext
) -> tuple[Optional[float], Optional[float]]:
    """Score strategic alignment from S/B ratio impact.

    Returns (score, improvement_delta). Score is 1.0 when the trade
    moves the asset's S/B ratio toward the operator-favored direction
    (>1.0 = sells above buys, the desirable scrumming target).

    For a BUY: a desirable buy LOWERS the avg buy price → improves S/B.
    For a SELL: a desirable sell RAISES the avg sell price → improves S/B.
    Either direction: the absolute improvement is the score input.
    """
    if ctx.rolling_sb_before is None or ctx.rolling_sb_after is None:
        return (None, None)
    delta = ctx.rolling_sb_after - ctx.rolling_sb_before
    # 0.05 delta is the cleanly-positive threshold — typical
    # session-over-session shifts are 0.01-0.05; >0.05 = strong move
    # in the right direction
    if delta > 0:
        score = min(1.0, delta / 0.05)
    else:
        # Negative delta hurts the S/B ratio
        score = max(0.0, 0.5 + delta / 0.05 * 0.5)
    return (score, delta)


def _score_outcome(
    record: TradeRecord, ctx: PriceContext
) -> tuple[Optional[float], Optional[float]]:
    """Score outcome from realized P&L per unit if the round-trip has
    closed. None if still open."""
    if ctx.realized_pnl_per_unit is None:
        return (None, None)
    if record.price <= 0:
        return (None, ctx.realized_pnl_per_unit)
    # Score: positive P&L scales toward 1.0; negative scales toward 0
    pnl_pct = ctx.realized_pnl_per_unit / record.price * 100.0
    if pnl_pct >= 0:
        score = min(1.0, pnl_pct / 5.0)  # 5%+ gain = full score
    else:
        score = max(0.0, 0.5 + pnl_pct / 5.0 * 0.5)
    return (score, ctx.realized_pnl_per_unit)


# ─────────────────────────────────────────────────────────────────────
# Letter grade boundaries
# ─────────────────────────────────────────────────────────────────────


def _letter_from_numeric(num: float) -> str:
    """Map [0.0, 1.0] numeric grade to A+/A/B/C/D/F."""
    if num >= 0.93:
        return "A+"
    elif num >= 0.85:
        return "A"
    elif num >= 0.70:
        return "B"
    elif num >= 0.55:
        return "C"
    elif num >= 0.40:
        return "D"
    else:
        return "F"


# ─────────────────────────────────────────────────────────────────────
# Main grader API
# ─────────────────────────────────────────────────────────────────────


def grade_trade(record: TradeRecord, ctx: PriceContext) -> TradeGrade:
    """Grade a single trade across all five axes.

    Each axis contributes if its inputs are present; missing axes are
    skipped (don't penalize, don't credit). The overall numeric grade
    is the unweighted mean of the available sub-scores.

    Args:
        record: the executed trade
        ctx: surrounding-price context (any field may be None)

    Returns:
        TradeGrade with sub-scores, overall letter, and rationale.
    """
    exec_score, exec_bps = _score_execution(record, ctx)
    timing_score, mfe, mae = _score_timing(record, ctx)
    strategic_score, sb_delta = _score_strategic(record, ctx)
    outcome_score, realized = _score_outcome(record, ctx)

    sub_scores = [
        s
        for s in (exec_score, timing_score, strategic_score, outcome_score)
        if s is not None
    ]
    if sub_scores:
        overall_num = sum(sub_scores) / len(sub_scores)
    else:
        overall_num = 0.5  # neutral when no data at all
    letter = _letter_from_numeric(overall_num)

    # Build rationale string
    parts: list[str] = []
    if exec_score is not None and exec_bps is not None:
        if exec_bps < 5:
            parts.append(f"clean exec ({exec_bps:+.1f}bps)")
        elif exec_bps < 25:
            parts.append(f"modest slip ({exec_bps:+.1f}bps)")
        else:
            parts.append(f"heavy slip ({exec_bps:+.1f}bps)")
    if timing_score is not None and mfe is not None and mae is not None:
        parts.append(f"MFE/MAE {mfe:+.2f}%/{mae:+.2f}%")
    if strategic_score is not None and sb_delta is not None:
        sign = "+" if sb_delta >= 0 else ""
        parts.append(f"S/B {sign}{sb_delta:.3f}")
    if outcome_score is not None and realized is not None:
        parts.append(f"realized ${realized:+.4f}/unit")
    if ctx.regime_tag:
        parts.append(f"regime={ctx.regime_tag}")
    rationale = "; ".join(parts) if parts else "no context available"

    return TradeGrade(
        trade_id=record.trade_id,
        asset=record.asset,
        side=record.side,
        timestamp=record.timestamp,
        execution_score=exec_score,
        timing_score=timing_score,
        strategic_score=strategic_score,
        outcome_score=outcome_score,
        overall=letter,
        overall_numeric=round(overall_num, 4),
        execution_bps=round(exec_bps, 2) if exec_bps is not None else None,
        mfe_pct=round(mfe, 3) if mfe is not None else None,
        mae_pct=round(mae, 3) if mae is not None else None,
        sb_improvement=round(sb_delta, 4) if sb_delta is not None else None,
        realized_pnl_per_unit=(round(realized, 6) if realized is not None else None),
        regime=ctx.regime_tag,
        rationale=rationale,
    )


# ─────────────────────────────────────────────────────────────────────
# Aggregate grading
# ─────────────────────────────────────────────────────────────────────


def grade_trades(
    records: list[TradeRecord], contexts: list[PriceContext]
) -> list[TradeGrade]:
    """Grade a sequence of trades. records and contexts must be
    parallel lists (same length, same order).

    Raises:
        ValueError: if lengths differ.
    """
    if len(records) != len(contexts):
        raise ValueError(
            f"grade_trades: parallel-list shape mismatch: "
            f"{len(records)} records vs {len(contexts)} contexts"
        )
    return [grade_trade(r, c) for r, c in zip(records, contexts)]


def grade_distribution(grades: list[TradeGrade]) -> dict:
    """Aggregate a list of grades into a portfolio-level summary.

    Returns dict with:
      - count_total, count_by_letter (A+/A/B/C/D/F)
      - mean_numeric, mean_per_axis (execution/timing/strategic/outcome)
      - by_asset: dict[asset] -> {count, mean_numeric}
    """
    out: dict = {
        "count_total": len(grades),
        "count_by_letter": {"A+": 0, "A": 0, "B": 0, "C": 0, "D": 0, "F": 0},
        "mean_numeric": 0.0,
        "mean_per_axis": {
            "execution": None,
            "timing": None,
            "strategic": None,
            "outcome": None,
        },
        "by_asset": {},
    }
    if not grades:
        return out

    out["mean_numeric"] = round(sum(g.overall_numeric for g in grades) / len(grades), 4)
    for g in grades:
        out["count_by_letter"][g.overall] = out["count_by_letter"].get(g.overall, 0) + 1

    # Per-axis means (filtering None)
    for axis_attr, axis_key in [
        ("execution_score", "execution"),
        ("timing_score", "timing"),
        ("strategic_score", "strategic"),
        ("outcome_score", "outcome"),
    ]:
        vals = [
            getattr(g, axis_attr) for g in grades if getattr(g, axis_attr) is not None
        ]
        if vals:
            out["mean_per_axis"][axis_key] = round(sum(vals) / len(vals), 4)

    # Per-asset roll-up
    by_asset: dict[str, list[TradeGrade]] = {}
    for g in grades:
        by_asset.setdefault(g.asset, []).append(g)
    for asset, asset_grades in by_asset.items():
        out["by_asset"][asset] = {
            "count": len(asset_grades),
            "mean_numeric": round(
                sum(g.overall_numeric for g in asset_grades) / len(asset_grades), 4
            ),
            "letter_counts": {
                k: sum(1 for g in asset_grades if g.overall == k)
                for k in ["A+", "A", "B", "C", "D", "F"]
            },
        }
    return out
