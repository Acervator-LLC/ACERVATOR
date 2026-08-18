"""gate_healer.py — reconstruct the market half of missing gate rows.

Operator directive 2026-08-02:

    "we should be able to retroactively generate this by 1) aligning
    all trades to the candles in which they happened, 2) reading the
    indicators as they were the trade's timestamp, and 3) inserting
    what the gate states should have been."

    "For trades that do not have bot state data, we will leave the
    field null."

WHAT CAN AND CANNOT BE REBUILT
==============================
A gate decision has two halves. Only one is recoverable from a
Stone Tablet.

RECOVERABLE (market-derived) — recomputed here from the candles
that existed at the trade's timestamp:
    TA consensus direction, net score, confidence, per-indicator
    votes, Bollinger position, band extremes, landing-strip state.
    These are pure functions of the candle history, so replaying
    them yields exactly what the live bot would have computed.

NOT RECOVERABLE (bot-state-derived) — left explicitly ``None``:
    delta vs target_balance, scrum_armed / fold_armed, hysteresis
    arming + reference prices, tranche availability, circuit-breaker
    trips, cash on hand, MEM-253 ceiling state.
    These depend on the bot's internal state at that instant, which
    no candle contains. Recovering them would require replaying the
    bot forward from a known state — and a gate row reconstructed by
    replaying the sim CANNOT then be used to validate the sim,
    because it would agree by construction.

That circularity is why every reconstructed row is stamped
``source="reconstructed_market"`` and is EXCLUDED from parity by
default. Reconstructed rows answer "what did the market look like
when this trade fired". They do not answer "did live and sim agree",
and must never be counted as if they did.

PROVENANCE CONTRACT
===================
    source = "recorded"              from live gate.log. Parity-eligible.
    source = "reconstructed_market"  rebuilt here. NOT parity-eligible.

``parity_eligible`` is a field, not a convention, so a caller cannot
forget to filter. ``split_by_provenance()`` exists so reports can
state both counts side by side.

sadp: R28 SSS + R70 RCN
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

logger = logging.getLogger("acervator.gate_healer")

SOURCE_RECORDED = "recorded"
SOURCE_RECONSTRUCTED = "reconstructed_market"

MIN_CANDLES_FOR_TA = 30
"""Below this the indicator set is unreliable; we emit a row whose
market half is also null rather than a confidently wrong one."""

BB_LOOKBACK = 100
"""Candles fed to the indicator pass. Matches the live bot's
get_ohlcv(limit=100) so the reconstruction sees the same window."""


@dataclass
class ReconstructedGate:
    """A gate row rebuilt from tablet candles.

    Field naming mirrors live gate.log's ``data`` block so consumers
    can treat both shapes uniformly, with the bot-state fields
    present-but-None instead of absent — an explicit "unknown"
    rather than a silently missing key.
    """
    # identity
    symbol: str
    bot_id: str
    trade_ts: float
    candle_address: str = ""
    candle_index: Optional[int] = None
    candle_ts_ms: Optional[int] = None

    # provenance
    source: str = SOURCE_RECONSTRUCTED
    parity_eligible: bool = False
    reconstruction_note: str = ""

    # ---- market-derived (recoverable) ----
    ta_direction: Optional[str] = None
    ta_net_score: Optional[float] = None
    ta_confidence: Optional[float] = None
    ta_bullish_count: Optional[int] = None
    ta_bearish_count: Optional[int] = None
    ta_neutral_count: Optional[int] = None
    ta_timeframe: str = ""
    indicator_votes: dict = field(default_factory=dict)
    bb_position: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    near_upper: Optional[bool] = None
    near_lower: Optional[bool] = None
    candle_close: Optional[float] = None
    candle_volume: Optional[float] = None

    # ---- bot-state-derived (NOT recoverable — always None) ----
    scrum_armed: Optional[bool] = None
    fold_armed: Optional[bool] = None
    scrum_blockers: Optional[list] = None
    fold_blockers: Optional[list] = None
    delta: Optional[float] = None
    target_balance: Optional[float] = None
    hyst_armed_scrum_side: Optional[bool] = None
    hyst_armed_fold_side: Optional[bool] = None
    n_fold_tranches: Optional[int] = None
    cb_blocks_scrum: Optional[bool] = None
    cb_blocks_fold: Optional[bool] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def has_market_data(self) -> bool:
        return self.ta_direction is not None


def _direction_name(summary: Any) -> Optional[str]:
    """VotingSummary.consensus_direction -> 'BULLISH'/'BEARISH'/
    'NEUTRAL'. Returns None when the enum is missing or odd."""
    try:
        d = summary.consensus_direction
    except Exception:  # noqa: BLE001 - summary shape is external
        return None
    name = getattr(d, "name", None)
    if name:
        return str(name).upper()
    return str(d).upper() or None


def _indicator_votes(summary: Any) -> dict:
    """Flatten VotingSummary.signals into {indicator: {...}}.

    Signal objects carry (indicator, direction, confidence, weight,
    timeframe) but exact attribute names vary by indicator, so each
    is read defensively — a missing field yields None for that key
    rather than dropping the whole vote.
    """
    out: dict = {}
    for sig in (getattr(summary, "signals", None) or []):
        name = (getattr(sig, "indicator", None)
                or getattr(sig, "name", None) or "unknown")
        direction = getattr(sig, "direction", None)
        dname = getattr(direction, "name", None)
        out[str(name)] = {
            "direction": (str(dname).upper() if dname
                          else (str(direction) if direction is not None
                                else None)),
            "confidence": _safe_float(
                getattr(sig, "confidence", None)),
            "weight": _safe_float(getattr(sig, "weight", None)),
        }
    return out


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return round(float(v), 6)
    except (TypeError, ValueError):
        return None


def reconstruct_market_gate(
    symbol: str,
    bot_id: str,
    trade_ts: float,
    candles: list,
    timeframe: str = "5m",
    bb_tolerance_pct: float = 1.0,
) -> ReconstructedGate:
    """Rebuild the market half of a gate decision for one trade.

    ``candles`` is the FULL tablet row list for the symbol. This
    function slices it to the window ending at the trade's candle,
    so no future data leaks into the reconstruction — a trade at
    candle N sees candles [N-99 .. N], exactly what the live bot's
    ``get_ohlcv(limit=100)`` returned at that moment.

    Never raises: a reconstruction failure yields a row with the
    market half null and the reason in ``reconstruction_note``.
    """
    from .stone_tablets.addressing import (
        format_address, index_for_ts, ticker_from_symbol)

    ticker = ticker_from_symbol(symbol)
    out = ReconstructedGate(
        symbol=symbol, bot_id=bot_id, trade_ts=trade_ts,
        ta_timeframe=timeframe)

    if not candles:
        out.reconstruction_note = "no tablet for symbol"
        return out

    idx = index_for_ts(candles, int(trade_ts * 1000))
    if idx is None:
        out.reconstruction_note = (
            "trade predates first candle (asset not yet listed)")
        return out

    out.candle_index = idx
    out.candle_ts_ms = int(candles[idx][0])
    try:
        out.candle_address = format_address(ticker, idx)
    except ValueError as exc:
        out.reconstruction_note = f"address failed: {exc}"

    row = candles[idx]
    out.candle_close = _safe_float(row[4])
    out.candle_volume = _safe_float(row[5])

    # Causal window: never look past the trade's own candle.
    start = max(0, idx - BB_LOOKBACK + 1)
    window = candles[start:idx + 1]
    if len(window) < MIN_CANDLES_FOR_TA:
        out.reconstruction_note = (
            f"only {len(window)} candles before this trade "
            f"(need {MIN_CANDLES_FOR_TA}) — market half left null")
        return out

    try:
        from .ta_engine import (
            VotingEngine, candles_from_raw, detect_bb_proximity)
        parsed = candles_from_raw(window)
        summary = VotingEngine().compute_all(parsed, timeframe)
        out.ta_direction = _direction_name(summary)
        out.ta_net_score = _safe_float(
            getattr(summary, "net_score", None))
        out.ta_confidence = _safe_float(
            getattr(summary, "consensus_confidence", None))
        out.ta_bullish_count = getattr(summary, "bullish_count", None)
        out.ta_bearish_count = getattr(summary, "bearish_count", None)
        out.ta_neutral_count = getattr(summary, "neutral_count", None)
        out.indicator_votes = _indicator_votes(summary)

        bb = detect_bb_proximity(parsed, tolerance_pct=bb_tolerance_pct)
        if bb is not None:
            out.bb_position = _safe_float(bb.bb_position)
            out.bb_upper = _safe_float(bb.upper)
            out.bb_middle = _safe_float(bb.middle)
            out.bb_lower = _safe_float(bb.lower)
            out.near_upper = bool(bb.near_upper)
            out.near_lower = bool(bb.near_lower)
        out.reconstruction_note = (
            f"market half rebuilt from {len(window)} candles; "
            "bot-state fields null by design")
    except Exception as exc:  # noqa: BLE001 - TA surface is broad
        out.ta_direction = None
        out.reconstruction_note = (
            f"TA recompute failed: {type(exc).__name__}: {exc}")
        logger.debug(
            "gate_healer: TA recompute failed for %s @ %s: %s",
            symbol, trade_ts, exc)
    return out


@dataclass
class HealReport:
    reconstructed: list[ReconstructedGate] = field(default_factory=list)
    already_covered: int = 0
    failed: int = 0

    @property
    def total_attempted(self) -> int:
        return len(self.reconstructed) + self.failed

    @property
    def with_market_data(self) -> int:
        return sum(1 for r in self.reconstructed if r.has_market_data)

    def notes_histogram(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.reconstructed:
            key = r.reconstruction_note.split(";")[0][:60] or "ok"
            out[key] = out.get(key, 0) + 1
        return out


def heal_gate_gaps(
    coverage_report: Any,
    candle_lookup: Any,
    timeframe: str = "5m",
) -> HealReport:
    """Reconstruct gate rows for every trade lacking one.

    ``coverage_report`` is a ``GateCoverageReport`` from
    ``gate_coverage.classify_trades``. Only pairings whose status is
    NOT ``has_gate`` are reconstructed — recorded rows are left
    untouched, since overwriting real data with a reconstruction
    would destroy the only parity-eligible evidence we have.

    ``candle_lookup`` is ``(symbol) -> list[rows]``; callers
    typically close over the Stone Tablets registry with a cache,
    because one tablet may serve hundreds of trades.
    """
    from .gate_coverage import GateStatus

    report = HealReport()
    for p in getattr(coverage_report, "pairings", []) or []:
        if getattr(p, "status", "") == GateStatus.HAS_GATE:
            report.already_covered += 1
            continue
        try:
            rows = candle_lookup(p.symbol) or []
        except Exception as exc:  # noqa: BLE001 - lookup is external
            report.failed += 1
            logger.debug(
                "gate_healer: candle lookup failed for %s: %s",
                p.symbol, exc)
            continue
        report.reconstructed.append(
            reconstruct_market_gate(
                symbol=p.symbol, bot_id=p.bot_id,
                trade_ts=p.trade_ts, candles=rows,
                timeframe=timeframe))
    return report


def split_by_provenance(rows: list) -> tuple[list, list]:
    """Partition mixed gate rows into ``(parity_eligible, other)``.

    Recorded live rows (plain dicts from gate.log) have no
    ``parity_eligible`` attribute and are treated as eligible;
    ReconstructedGate instances carry it as False. This is the
    guard that stops a reconstructed row from silently inflating a
    parity score.
    """
    eligible: list = []
    other: list = []
    for r in rows or []:
        flag = getattr(r, "parity_eligible", None)
        if flag is None and isinstance(r, dict):
            flag = r.get("parity_eligible", True)
        (eligible if (flag is None or flag) else other).append(r)
    return eligible, other


def format_heal_lines(report: HealReport) -> list[str]:
    """Operator-facing summary."""
    lines = [
        f"Gate healing: {len(report.reconstructed):,} row(s) "
        f"reconstructed, {report.with_market_data:,} with usable "
        f"market data, {report.already_covered:,} already recorded, "
        f"{report.failed:,} failed",
        "  reconstructed rows are NOT parity-eligible "
        "(bot-state fields are null by design)",
    ]
    hist = report.notes_histogram()
    for note, n in sorted(hist.items(), key=lambda kv: -kv[1])[:6]:
        lines.append(f"    {n:>6,}  {note}")
    return lines


__all__ = [
    "BB_LOOKBACK",
    "MIN_CANDLES_FOR_TA",
    "SOURCE_RECONSTRUCTED",
    "SOURCE_RECORDED",
    "HealReport",
    "ReconstructedGate",
    "format_heal_lines",
    "heal_gate_gaps",
    "reconstruct_market_gate",
    "split_by_provenance",
]
