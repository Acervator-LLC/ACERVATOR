"""gate_coverage.py — pair trades with the gate decision behind them.

Operator directive 2026-08-02:

    "The other piece that has yet to be brought into this version of
    the sim are the trading gate logs that were previously
    implemented during legacy live to sim parity attempts. Since
    these were introduced late, it will create a blind spot prior to
    this feature being added so we will need to: 1) Find and
    validate the logic gate tracking logs and import to the current
    build, 2) Create error handling for trade actions that do not
    have logic gate data, and 3) Determine if any improvements to
    this process can be made."

This module is (2): every trade is classified by WHY it does or
does not have gate data, so a missing gate decision is an explicit,
named condition rather than a silent absence.

MEASURED STATE OF THE GATE LOGS (verified 2026-08-02)
=====================================================
    ~/.acervator_logs/trade/gate.log     626 KB    446 entries
                                         2026-06-14 -> 2026-08-02
    gate.log.1 .. gate.log.5             52 MB ea  ~165k entries
                                         2026-06-09 -> 2026-06-11

The rotations are dense (~197k entries per 33 hours). The current
file is sparse (446 entries per 7 weeks) with a 28-day hole from
2026-06-26 to 2026-07-24. Gate data therefore exists for only a
fraction of the YTD trade window that starts 2026-04-01.

Classification distinguishes the causes, because they need
different responses:

    HAS_GATE          — a gate decision was found. Parity can run.
    BEFORE_LOGGING    — trade predates the earliest gate entry that
                        exists. This is the operator's "blind spot";
                        it is NOT a bug and cannot be backfilled.
    LOG_GAP           — trade falls between two gate entries that
                        are far enough apart that the log was not
                        being written then (app not running, or the
                        writer stalled). Recoverable in future by
                        keeping the app up; not recoverable for past
                        trades.
    NO_GATE_FOR_BOT   — gate entries exist in this time range, but
                        none for this bot_id. Suggests the bot was
                        not evaluating, or its gate emission path is
                        broken while others work. THIS one is worth
                        investigating as a defect.
    NO_GATE_DATA      — no gate entries at all were supplied.

Only HAS_GATE trades can participate in a strict parity claim.
Reporting the rest by cause is what stops a 11%-coverage run from
being mistaken for a 100%-agreement result.

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import bisect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger("acervator.gate_coverage")

DEFAULT_TOLERANCE_S: float = 300.0
"""±one 5m candle. A gate decision that produced a trade is
evaluated on the candle the trade fired within."""

LOG_GAP_THRESHOLD_S: float = 1800.0
"""Gap between consecutive gate entries above which we call the log
'not being written' rather than merely quiet. 30 min = 6 missed 5m
candles."""


class GateStatus:
    HAS_GATE = "has_gate"
    BEFORE_LOGGING = "before_logging"
    LOG_GAP = "log_gap"
    NO_GATE_FOR_BOT = "no_gate_for_bot"
    NO_GATE_DATA = "no_gate_data"
    # v3.24.24 — the bot WAS logging either side of this trade, but no
    # entry landed inside the pairing tolerance.
    #
    # This case previously fell through to LOG_GAP. `classify_trades`
    # assigned LOG_GAP in BOTH the `elif _in_log_gap(...)` branch and the
    # `else`, so the scan's result was computed and discarded, and two
    # genuinely different situations were reported as one: "the app was
    # down / the writer stalled" versus "the app was running and logging
    # normally, but this trade has no decision near it." The second is
    # the more alarming of the two and was invisible.
    NO_GATE_IN_TOLERANCE = "no_gate_in_tolerance"


@dataclass
class TradeGatePairing:
    """One trade and the gate decision behind it (or why there is
    none)."""

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
        """Blockers recorded on the side matching this trade —
        a SELL is a scrum, a BUY is a fold."""
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
    """Parse an ISO timestamp from a log entry. 0.0 when absent or
    malformed — callers filter those out rather than treating them
    as epoch-zero events."""
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
"""The only fields any consumer of ``TradeGatePairing.gate_entry`` reads.

Verified by grep: ``gate_entry`` is consumed exclusively by
``scrum_armed`` / ``fold_armed`` / ``blockers`` in this module.
``history_helpers.lookup_gate_entry`` is a different index and is
unaffected.
"""


def _project(entry: dict) -> dict:
    """Keep only what pairing consumers read.

    v3.24.24 — the index used to retain the whole parsed log line. On the
    operator's real gate.log (165,047 rows / 262.1 MB of NDJSON, average
    1,603 B/line) that was measured at **1.03 GB of Python heap**, held
    synchronously on the Qt thread. Retaining a four-field projection
    lets the full parsed line be collected inside the generator loop.
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
    """Index gate entries by bot_id, each list sorted by timestamp.

    Returns ``(index, earliest_ts, latest_ts)``. Entries with an
    unparseable timestamp are dropped and counted in the log, since
    an un-timestamped gate decision cannot be paired with anything.

    NOTE: ``live_log_reader.live_gate_decisions()`` yields the
    current file BEFORE the rotated ones, so its output is NOT in
    chronological order. This function sorts, so callers may pass
    the reader's output directly.

    v3.24.24 — takes any ``Iterable``, so callers can stream a generator
    instead of materialising every row first. Combined with the
    projection below, peak heap drops by roughly 20x.
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
    """Closest entry within tolerance.

    v3.24.24 — bisect, not a linear scan. The old docstring claimed
    "per-bot lists are small relative to the total"; measured against the
    operator's real gate.log that is false — 83 distinct bot_ids with an
    average of 1,988 entries each and 12,366 for the busiest. 597 trades
    scanning their bot's list is 3,413,906 iterations, measured at
    0.971 s, on the Qt thread.

    ``build_gate_index`` already sorts each per-bot list, so the ordering
    this needs was being built and then ignored.

    EXACTNESS
    =========
    On a sorted list the minimiser of ``|ts - target|`` is always at the
    insertion point or immediately before it, so probing those two is not
    an approximation.

    ``i - 1`` is probed FIRST to preserve the original first-wins
    tie-break: the linear scan used strict ``<``, so on two entries
    equidistant from the target it kept the earlier one.
    """
    if not candidates:
        return None, 0.0
    i = bisect.bisect_left(candidates, (target,))
    best: Optional[dict] = None
    best_drift = float("inf")
    for j in (i - 1, i):  # order matters — see tie-break above
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
    """True when target falls inside a stretch where this bot
    produced no gate entries for longer than the threshold."""
    prev_ts = None
    for ts, _e in candidates:
        if prev_ts is not None and prev_ts < target < ts:
            return (ts - prev_ts) > gap_threshold_s
        prev_ts = ts
    # Past the last entry — a gap if the trailing silence is long.
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
    """Pair every trade with its gate decision, or name why not.

    ``address_resolver`` is an optional callable
    ``(symbol, ts_ms) -> Optional[str]`` returning a candle address
    (see stone_tablets.addressing). When supplied, each pairing
    carries the address of the candle the trade fired within, which
    lets parity compare on exact candle identity rather than a
    timestamp tolerance window.
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
            # Gate data exists overall, none for this bot. Worth
            # investigating — other bots emitted, this one did not.
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
            # v3.24.24 — was also LOG_GAP, which made the _in_log_gap
            # call above dead work and merged two distinct findings.
            # The bot was logging on both sides of this trade; nothing
            # landed within tolerance.
            pairing.status = GateStatus.NO_GATE_IN_TOLERANCE
        report.pairings.append(pairing)

    return report


def format_coverage_lines(
    report: GateCoverageReport,
    max_examples: int = 5,
) -> list[str]:
    """Operator-facing summary for the Performance Log."""
    lines: list[str] = []
    counts = report.by_status()
    lines.append(
        f"Gate coverage: {report.covered:,} / {report.total:,} trades "
        f"have a gate decision ({report.coverage_pct:.1f}%)"
    )
    if report.gate_entry_count:
        # timezone-aware: utcfromtimestamp is deprecated and slated
        # for removal (surfaced as a DeprecationWarning by the pin
        # tests on 2026-08-02).
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


# --------------------------------------------------------------------- #
# v3.24.15 — validation-scoped replay window                            #
# --------------------------------------------------------------------- #
#
# Operator directive 2026-08-03:
#
#   "the oldest trade with all validation data in the trade gate log
#    should emit a soft start read date cap of which the user will be
#    informed via the simulation log."
#
# Before this, Fleet Replay played the entire tablet span (2026-04-01
# onward, 35,282 candles / ~47 min at the measured 12.5 candles/s)
# even though gate logging only began 2026-06-10. Everything before
# that point is unvalidatable by construction — no gate row exists to
# compare a sim decision against — so replaying it burns time and
# produces nothing.
#
# The cap is SOFT: it bounds the default window, it does not delete
# tablet data and it does not stop the operator asking for the full
# span. Tablets remain immutable.


@dataclass
class ValidationWindow:
    """Where a replay should start so every candle it plays can
    actually be validated."""

    soft_start_ms: int = 0
    """Oldest trade that HAS gate data — the validation floor."""

    replay_start_ms: int = 0
    """soft_start minus TA warm-up. The value the sim should use."""

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
    """Derive the soft start cap from gate coverage.

    The floor is the OLDEST trade whose status is ``has_gate`` — not
    simply the first gate-log entry. Those differ when the log begins
    before the first trade it covers, and using the trade keeps the
    window tied to something we can actually check.

    ``warmup_candles`` is subtracted so indicators are primed before
    the first validatable decision; a bot evaluated on a cold TA
    window would diverge from live for reasons that have nothing to
    do with strategy.
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
    """Operator-facing explanation for the Simulator Activity Log."""
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
