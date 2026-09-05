"""Pair each trade with the gate decision behind it.

``classify_trades`` gives every trade one ``GateStatus`` and returns a
``GateCoverageReport`` whose ``coverage_pct`` counts only ``HAS_GATE``.
``build_gate_index`` groups the gate entries by ``bot_id``, ``_nearest`` picks
the closest one inside ``DEFAULT_TOLERANCE_S``, and ``_in_log_gap`` separates
``LOG_GAP`` from ``NO_GATE_IN_TOLERANCE`` at ``LOG_GAP_THRESHOLD_S``.
``compute_validation_window`` turns that coverage into a ``ValidationWindow``,
which ``format_window_lines`` renders beside ``format_coverage_lines``.
"""

from __future__ import annotations

import bisect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger("acervator.gate_coverage")

DEFAULT_TOLERANCE_S: float = 300.0
"""One 5m candle either side of a trade, the window ``_nearest`` searches."""

LOG_GAP_THRESHOLD_S: float = 1800.0
"""Six 5m candles of silence, above which ``_in_log_gap`` returns True."""


class GateStatus:
    HAS_GATE = "has_gate"
    BEFORE_LOGGING = "before_logging"
    LOG_GAP = "log_gap"
    NO_GATE_FOR_BOT = "no_gate_for_bot"
    NO_GATE_DATA = "no_gate_data"
    # The bot logged either side of the trade, none within the tolerance.
    NO_GATE_IN_TOLERANCE = "no_gate_in_tolerance"


@dataclass
class TradeGatePairing:
    """One trade, its `status`, and the `gate_entry` behind it when there is one."""

    trade_ts: float
    bot_id: str
    symbol: str
    side: str
    status: str
    gate_entry: Optional[dict] = None
    drift_s: float = 0.0
    candle_address: str = ""

    @property
    def has_gate(self) -> bool:
        return self.status == GateStatus.HAS_GATE

    @property
    def scrum_armed(self) -> Optional[bool]:
        if not self.gate_entry:
            return None
        return bool((self.gate_entry.get("data") or {}).get("scrum_armed"))

    @property
    def fold_armed(self) -> Optional[bool]:
        if not self.gate_entry:
            return None
        return bool((self.gate_entry.get("data") or {}).get("fold_armed"))

    def blockers(self) -> list[str]:
        """Return `scrum_blockers` when `side` holds SELL, else `fold_blockers`."""
        if not self.gate_entry:
            return []
        data = self.gate_entry.get("data") or {}
        key = "scrum_blockers" if "SELL" in self.side.upper() else "fold_blockers"
        return list(data.get(key) or [])


@dataclass
class GateCoverageReport:
    pairings: list[TradeGatePairing] = field(default_factory=list)
    gate_first_ts: float = 0.0
    gate_last_ts: float = 0.0
    gate_entry_count: int = 0

    def by_status(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self.pairings:
            out[p.status] = out.get(p.status, 0) + 1
        return out

    @property
    def total(self) -> int:
        return len(self.pairings)

    @property
    def covered(self) -> int:
        return sum(1 for p in self.pairings if p.has_gate)

    @property
    def coverage_pct(self) -> float:
        return (100.0 * self.covered / self.total) if self.total else 0.0


def _ts_of(entry: dict) -> float:
    """Return `entry`'s "timestamp" as epoch seconds, or 0.0.

    `build_gate_index` drops every entry this returns 0.0 for.
    """
    s = str(entry.get("timestamp", "") or "")
    if not s:
        return 0.0
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return 0.0


_RETAINED_GATE_FIELDS = (
    "scrum_armed",
    "fold_armed",
    "scrum_blockers",
    "fold_blockers",
)
"""The only ``data`` keys ``TradeGatePairing.scrum_armed``, ``fold_armed`` and
``blockers`` read out of ``gate_entry``."""


def _project(entry: dict) -> dict:
    """Return `entry` reduced to "timestamp", "bot_id" and _RETAINED_GATE_FIELDS.

    `build_gate_index` stores this projection, and the full parsed line is
    collectable once it returns.
    """
    data = entry.get("data") or {}
    return {
        "timestamp": entry.get("timestamp", ""),
        "bot_id": entry.get("bot_id", ""),
        "data": {k: data.get(k) for k in _RETAINED_GATE_FIELDS},
    }


def build_gate_index(
    gate_entries: Iterable[dict],
) -> tuple[dict[str, list[tuple[float, dict]]], float, float]:
    """Return ``(index, earliest_ts, latest_ts)``, each list sorted by timestamp.

    ``gate_entries`` may be any ``Iterable``, including the unsorted output of
    ``live_log_reader.live_gate_decisions``; entries ``_ts_of`` reads as 0.0
    are dropped and counted in a debug line.
    """
    index: dict[str, list[tuple[float, dict]]] = {}
    earliest = float("inf")
    latest = 0.0
    dropped = 0
    for e in gate_entries or []:
        ts = _ts_of(e)
        if ts <= 0:
            dropped += 1
            continue
        bot_id = str(e.get("bot_id", "") or "")
        index.setdefault(bot_id, []).append((ts, _project(e)))
        earliest = min(earliest, ts)
        latest = max(latest, ts)
    for lst in index.values():
        lst.sort(key=lambda p: p[0])
    if dropped:
        logger.debug(
            "gate_coverage: dropped %d entries with unparseable " "timestamps", dropped
        )
    if earliest == float("inf"):
        earliest = 0.0
    return index, earliest, latest


def _nearest(
    candidates: list[tuple[float, dict]],
    target: float,
    tolerance_s: float,
) -> tuple[Optional[dict], float]:
    """Return the `candidates` entry closest to `target` within `tolerance_s`.

    On the sorted list `build_gate_index` produces, the minimiser of
    ``|ts - target|`` is at the ``bisect_left`` insertion point or the index
    before it, so probing those two is exact.
    """
    if not candidates:
        return None, 0.0
    i = bisect.bisect_left(candidates, (target,))
    best: Optional[dict] = None
    best_drift = float("inf")
    for j in (i - 1, i):  # i - 1 first, so an equidistant tie keeps the earlier
        if 0 <= j < len(candidates):
            ts, e = candidates[j]
            drift = abs(ts - target)
            if drift <= tolerance_s and drift < best_drift:
                best, best_drift = e, drift
    return best, (0.0 if best is None else best_drift)


def _in_log_gap(
    candidates: list[tuple[float, dict]],
    target: float,
    gap_threshold_s: float,
) -> bool:
    """Return True when `candidates` is silent around `target`.

    The silence must exceed `gap_threshold_s`, and a `target` past the last
    entry measures it from that entry.
    """
    prev_ts = None
    for ts, _e in candidates:
        if prev_ts is not None and prev_ts < target < ts:
            return (ts - prev_ts) > gap_threshold_s
        prev_ts = ts
    if prev_ts is not None and target > prev_ts:
        return (target - prev_ts) > gap_threshold_s
    return False


def classify_trades(
    trades: list[dict],
    gate_entries: Iterable[dict],
    tolerance_s: float = DEFAULT_TOLERANCE_S,
    gap_threshold_s: float = LOG_GAP_THRESHOLD_S,
    address_resolver: Optional[Any] = None,
) -> GateCoverageReport:
    """Give every trade one GateStatus and return a GateCoverageReport.

    ``address_resolver`` is a ``(symbol, ts_ms) -> Optional[str]`` callable
    from ``stone_tablets.addressing``; it fills ``candle_address`` on each
    TradeGatePairing.
    """
    index, earliest, latest = build_gate_index(gate_entries)
    report = GateCoverageReport(
        gate_first_ts=earliest,
        gate_last_ts=latest,
        gate_entry_count=sum(len(v) for v in index.values()),
    )

    for t in trades or []:
        ts = float(t.get("timestamp", 0) or 0)
        bot_id = str(t.get("bot_id", "") or "")
        symbol = str(
            t.get("symbol", "") or (t.get("data") or {}).get("symbol", "") or ""
        )
        side = str(t.get("side", "") or (t.get("data") or {}).get("side", "") or "")

        address = ""
        if address_resolver is not None and ts > 0:
            try:
                address = address_resolver(symbol, int(ts * 1000)) or ""
            except Exception as exc:  # noqa: BLE001 - resolver is external
                logger.debug(
                    "gate_coverage: address resolve failed for %s: %s", symbol, exc
                )

        pairing = TradeGatePairing(
            trade_ts=ts,
            bot_id=bot_id,
            symbol=symbol,
            side=side,
            status=GateStatus.NO_GATE_DATA,
            candle_address=address,
        )

        if not index:
            report.pairings.append(pairing)
            continue

        candidates = index.get(bot_id, [])
        if not candidates:
            pairing.status = GateStatus.NO_GATE_FOR_BOT
            report.pairings.append(pairing)
            continue

        entry, drift = _nearest(candidates, ts, tolerance_s)
        if entry is not None:
            pairing.status = GateStatus.HAS_GATE
            pairing.gate_entry = entry
            pairing.drift_s = drift
        elif ts < earliest:
            pairing.status = GateStatus.BEFORE_LOGGING
        elif _in_log_gap(candidates, ts, gap_threshold_s):
            pairing.status = GateStatus.LOG_GAP
        else:
            pairing.status = GateStatus.NO_GATE_IN_TOLERANCE
        report.pairings.append(pairing)

    return report


def format_coverage_lines(
    report: GateCoverageReport,
    max_examples: int = 5,
) -> list[str]:
    """Render `report` as operator-facing lines, one per GateStatus.

    `max_examples` caps the bot_ids listed for NO_GATE_FOR_BOT.
    """
    lines: list[str] = []
    counts = report.by_status()
    lines.append(
        f"Gate coverage: {report.covered:,} / {report.total:,} trades "
        f"have a gate decision ({report.coverage_pct:.1f}%)"
    )
    if report.gate_entry_count:

        def _fmt(ts: float) -> str:
            if not ts:
                return "?"
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M"
            )

        first = _fmt(report.gate_first_ts)
        last = _fmt(report.gate_last_ts)
        lines.append(
            f"  gate log: {report.gate_entry_count:,} entries, "
            f"{first} -> {last} UTC"
        )
    label = {
        GateStatus.HAS_GATE: "paired with a gate decision",
        GateStatus.BEFORE_LOGGING: "predate gate logging (blind spot — not backfillable)",
        GateStatus.LOG_GAP: "fall in a gate-log gap (app down or writer stalled)",
        GateStatus.NO_GATE_IN_TOLERANCE: "bot was logging either side, but no decision within "
        "tolerance (investigate)",
        GateStatus.NO_GATE_FOR_BOT: "bot emitted NO gate entries (investigate)",
        GateStatus.NO_GATE_DATA: "no gate data supplied at all",
    }
    for status, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {n:>6,}  {label.get(status, status)}")

    suspicious = [p for p in report.pairings if p.status == GateStatus.NO_GATE_FOR_BOT]
    if suspicious:
        bots = sorted({p.bot_id for p in suspicious})[:max_examples]
        lines.append(
            f"  bots with zero gate entries: {', '.join(bots)}"
            + (" ..." if len(suspicious) > max_examples else "")
        )
    return lines


__all__ = [
    "DEFAULT_TOLERANCE_S",
    "LOG_GAP_THRESHOLD_S",
    "GateCoverageReport",
    "GateStatus",
    "TradeGatePairing",
    "build_gate_index",
    "classify_trades",
    "format_coverage_lines",
]


@dataclass
class ValidationWindow:
    """The replay bounds `compute_validation_window` derives from coverage.

    `has_cap` is False until `soft_start_ms` is set, and no tablet data is
    deleted or withheld by either value.
    """

    soft_start_ms: int = 0
    """The oldest `HAS_GATE` trade, in epoch milliseconds."""

    replay_start_ms: int = 0
    """`soft_start_ms` less `warmup_candles` of `step_ms`, floored at 0."""

    warmup_candles: int = 0
    trades_validatable: int = 0
    trades_excluded: int = 0
    excluded_oldest_ts: float = 0.0
    excluded_newest_ts: float = 0.0
    gate_first_ts: float = 0.0
    reason: str = ""

    @property
    def has_cap(self) -> bool:
        return self.soft_start_ms > 0


def compute_validation_window(
    coverage: GateCoverageReport,
    warmup_candles: int = 100,
    step_ms: int = 300_000,
) -> ValidationWindow:
    """Return the ValidationWindow `coverage` supports.

    ``soft_start_ms`` is the oldest ``HAS_GATE`` trade, not
    ``coverage.gate_first_ts``, and ``replay_start_ms`` backs it off by
    ``warmup_candles`` steps of ``step_ms``.
    """
    win = ValidationWindow(
        warmup_candles=max(0, int(warmup_candles)), gate_first_ts=coverage.gate_first_ts
    )

    paired = [p for p in coverage.pairings if p.status == GateStatus.HAS_GATE]
    if not paired:
        win.reason = (
            "no trade has gate data — cannot scope the window; "
            "replay will use the full tablet span"
        )
        return win

    oldest = min(p.trade_ts for p in paired)
    win.soft_start_ms = int(oldest * 1000)
    win.replay_start_ms = max(0, win.soft_start_ms - win.warmup_candles * step_ms)
    win.trades_validatable = len(paired)

    excluded = [p for p in coverage.pairings if p.trade_ts < oldest]
    win.trades_excluded = len(excluded)
    if excluded:
        win.excluded_oldest_ts = min(p.trade_ts for p in excluded)
        win.excluded_newest_ts = max(p.trade_ts for p in excluded)

    win.reason = (
        f"oldest trade with gate data is "
        f"{_fmt_ts(oldest)}; {win.trades_excluded} earlier trade(s) "
        "have no gate row and can never be validated"
    )
    return win


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def format_window_lines(
    win: ValidationWindow,
    full_candles: int = 0,
    scoped_candles: int = 0,
) -> list[str]:
    """Render `win` as operator-facing lines for the Simulator Activity Log.

    Without `has_cap` only `win.reason` is returned; `full_candles` and
    `scoped_candles` add the line naming how far the window narrowed.
    """
    if not win.has_cap:
        return [f"Validation window: {win.reason}"]
    lines = [
        f"Validation soft-start: {_fmt_ts(win.soft_start_ms / 1000)}",
        f"  {win.reason}",
        f"  replay begins {win.warmup_candles} candles earlier "
        f"({_fmt_ts(win.replay_start_ms / 1000)}) to prime indicators",
        f"  {win.trades_validatable:,} trade(s) validatable in window",
    ]
    if win.trades_excluded:
        lines.append(
            f"  {win.trades_excluded} trade(s) excluded "
            f"({_fmt_ts(win.excluded_oldest_ts)} .. "
            f"{_fmt_ts(win.excluded_newest_ts)}) — no gate data exists "
            "for them, so no sim result could be checked"
        )
    if full_candles and scoped_candles:
        saved = full_candles - scoped_candles
        pct = 100.0 * saved / full_candles if full_candles else 0.0
        lines.append(
            f"  window scoped {full_candles:,} -> {scoped_candles:,} "
            f"candles ({pct:.0f}% fewer)"
        )
    return lines
