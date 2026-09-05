"""Deterministic trade scoring.

``grade_trade`` averages the sub-scores that ``_score_execution``,
``_score_timing``, ``_score_strategic`` and ``_score_outcome`` return for one
``TradeRecord`` and ``PriceContext``, skipping every axis that lacks inputs.
``_letter_from_numeric`` turns that unweighted mean into ``A+``, ``A``, ``B``,
``C``, ``D`` or ``F``. ``PriceContext.regime_tag`` reaches ``TradeGrade.regime``
and ``TradeGrade.rationale`` with no sub-score of its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TradeRecord:
    """One executed trade, as ``grade_trade`` takes it.

    ``_score_execution``, ``_score_timing`` and ``_score_outcome`` read only
    ``side`` and ``price``; ``quantity``, ``fee``, ``subtotal`` and ``notes``
    are carried and never scored.
    """

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
    """Surrounding-price inputs for one ``grade_trade`` call.

    Every field is optional; an axis whose inputs are absent is left out of
    ``TradeGrade.overall_numeric`` and out of ``TradeGrade.rationale``.
    """

    ref_price_at_decision: Optional[float] = None
    # ``future_prices`` are the prices after the trade; ``_score_timing``
    # keeps only their maximum and minimum.
    future_prices: list[float] = field(default_factory=list)
    rolling_sb_before: Optional[float] = None
    rolling_sb_after: Optional[float] = None
    regime_tag: str = ""
    realized_pnl_per_unit: Optional[float] = None


@dataclass
class TradeGrade:
    """One graded trade, as ``grade_trade`` returns it.

    ``execution_score``, ``timing_score``, ``strategic_score`` and
    ``outcome_score`` are each in [0.0, 1.0] or None, and ``overall`` is the
    letter ``_letter_from_numeric`` gives ``overall_numeric``.
    """

    trade_id: str
    asset: str
    side: str
    timestamp: Optional[datetime]
    execution_score: Optional[float]
    timing_score: Optional[float]
    strategic_score: Optional[float]
    outcome_score: Optional[float]
    overall: str
    overall_numeric: float
    execution_bps: Optional[float] = None
    mfe_pct: Optional[float] = None
    mae_pct: Optional[float] = None
    sb_improvement: Optional[float] = None
    realized_pnl_per_unit: Optional[float] = None
    regime: str = ""
    rationale: str = ""


def _score_execution(
    record: TradeRecord, ctx: PriceContext
) -> tuple[Optional[float], Optional[float]]:
    """Score ``record.price`` against ``ctx.ref_price_at_decision``.

    Returns the score and the slippage in basis points: 1.0 at no slippage
    against ``record.side``, 0.0 at 100 bps or worse, and ``(None, None)``
    when the reference price is missing or not positive.
    """
    if ctx.ref_price_at_decision is None or ctx.ref_price_at_decision <= 0:
        return (None, None)
    ref = ctx.ref_price_at_decision
    if record.side == "buy":
        bps = (record.price - ref) / ref * 10000.0
    else:
        bps = (ref - record.price) / ref * 10000.0
    score = max(0.0, min(1.0, 1.0 - (bps / 100.0)))
    return (score, bps)


def _score_timing(
    record: TradeRecord, ctx: PriceContext
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Score excursion across the positive entries of ``ctx.future_prices``.

    Returns the score, ``mfe_pct`` and ``mae_pct``, where the score reaches
    1.0 at an ``mfe_pct`` to ``mae_pct`` ratio of 3 or at a non-adverse
    ``mae_pct``, and is 0.0 when ``mfe_pct`` is not positive.
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
    abs_mae = abs(mae_pct) if mae_pct < 0 else 0.0
    if mfe_pct <= 0:
        score = 0.0
    elif abs_mae <= 0:
        score = 1.0
    else:
        ratio = mfe_pct / abs_mae
        score = max(0.0, min(1.0, ratio / 3.0))
    return (score, mfe_pct, mae_pct)


def _score_strategic(
    record: TradeRecord, ctx: PriceContext
) -> tuple[Optional[float], Optional[float]]:
    """Score the shift from ``ctx.rolling_sb_before`` to ``ctx.rolling_sb_after``.

    Returns the score and that delta: 1.0 at +0.05 or more, 0.5 at no shift,
    0.0 at -0.05 or worse, and ``(None, None)`` when either field is unset.
    """
    if ctx.rolling_sb_before is None or ctx.rolling_sb_after is None:
        return (None, None)
    delta = ctx.rolling_sb_after - ctx.rolling_sb_before
    if delta > 0:
        score = min(1.0, delta / 0.05)
    else:
        score = max(0.0, 0.5 + delta / 0.05 * 0.5)
    return (score, delta)


def _score_outcome(
    record: TradeRecord, ctx: PriceContext
) -> tuple[Optional[float], Optional[float]]:
    """Score ``ctx.realized_pnl_per_unit`` as a percentage of ``record.price``.

    Returns the score and that P&L: 1.0 at +5% or more, 0.5 at zero, 0.0 at
    -5% or worse, and no score when ``record.price`` is not positive.
    """
    if ctx.realized_pnl_per_unit is None:
        return (None, None)
    if record.price <= 0:
        return (None, ctx.realized_pnl_per_unit)
    pnl_pct = ctx.realized_pnl_per_unit / record.price * 100.0
    if pnl_pct >= 0:
        score = min(1.0, pnl_pct / 5.0)
    else:
        score = max(0.0, 0.5 + pnl_pct / 5.0 * 0.5)
    return (score, ctx.realized_pnl_per_unit)


def _letter_from_numeric(num: float) -> str:
    """Map ``num`` in [0.0, 1.0] to ``A+``, ``A``, ``B``, ``C``, ``D`` or ``F``."""
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


def grade_trade(record: TradeRecord, ctx: PriceContext) -> TradeGrade:
    """Grade one ``record`` against its ``ctx``.

    ``TradeGrade.overall_numeric`` is the unweighted mean of the sub-scores
    whose inputs were present, or 0.5 when no axis could be scored.
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
        overall_num = 0.5
    letter = _letter_from_numeric(overall_num)

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


def grade_trades(
    records: list[TradeRecord], contexts: list[PriceContext]
) -> list[TradeGrade]:
    """Grade ``records`` against the parallel ``contexts`` with ``grade_trade``.

    Raises ``ValueError`` when the two lists differ in length.
    """
    if len(records) != len(contexts):
        raise ValueError(
            f"grade_trades: parallel-list shape mismatch: "
            f"{len(records)} records vs {len(contexts)} contexts"
        )
    return [grade_trade(r, c) for r, c in zip(records, contexts)]


def grade_distribution(grades: list[TradeGrade]) -> dict:
    """Summarize ``grades`` into counts and means.

    Returns ``count_total``, ``count_by_letter``, ``mean_numeric``,
    ``mean_per_axis`` and ``by_asset``, whose entries hold ``count``,
    ``mean_numeric`` and ``letter_counts``.
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
