"""sim_validation_guard.py — halt the sim when its data cannot be trusted.

Operator directive 2026-08-02:

    "Should add further robustness so that the sim gracefully stops
    when encountering trade events that cannot be validated."

WHY A HALT AND NOT A WARNING
============================
A replay that keeps running past unvalidatable data still produces a
parity percentage, a trade count, and a green-looking summary. Those
numbers are indistinguishable from a sound run unless someone reads
the warnings — and the whole failure mode this project keeps hitting
is a result that LOOKS complete while resting on partial input.

Stopping converts a silent data problem into a loud one. The run
ends with a named reason and whatever partial results exist are kept
and clearly marked partial, rather than being presented as final.

WHAT COUNTS AS UNVALIDATABLE
============================
    NO_TABLET          symbol has no Stone Tablet — the sim cannot
                       price it, so any trade on it is fiction.
    PRE_LISTING        trade timestamp precedes the tablet's first
                       candle; no market state existed to evaluate.
    UNRESOLVABLE_TS    timestamp missing/zero/unparseable, so the
                       trade cannot be bound to a candle at all.
    SCHEMA_DRIFT       a gate row is missing fields the comparison
                       requires; shape changed under us.
    ADDRESS_MISMATCH   a trade's recorded candle address disagrees
                       with the address recomputed from the tablet —
                       means the tablet changed beneath stored data.

ADDRESS_MISMATCH is the most serious: it implies a Stone Tablet was
back-filled with earlier candles, shifting every index for that
ticker. Stone Tablets are append-only by directive, so this should
be impossible; if it fires, stored addresses across the whole
dataset are suspect.

POLICY
======
Default is halt-on-first for the two integrity failures
(SCHEMA_DRIFT, ADDRESS_MISMATCH) and tolerate-with-count for the
three data-coverage failures — because a fleet legitimately holds
assets listed mid-window, and halting the entire run for one
pre-listing trade would make the sim unusable. ``max_tolerated``
bounds that tolerance so a wholesale coverage collapse still stops
the run rather than quietly degrading it.

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("acervator.sim_validation_guard")


class ValidationIssueType:
    NO_TABLET = "no_tablet"
    PRE_LISTING = "pre_listing"
    UNRESOLVABLE_TS = "unresolvable_timestamp"
    SCHEMA_DRIFT = "schema_drift"
    ADDRESS_MISMATCH = "address_mismatch"


#: Issues that indicate the DATASET ITSELF is inconsistent. These
#: halt immediately regardless of count — tolerating them would mean
#: computing on data whose meaning has shifted.
INTEGRITY_ISSUES = frozenset(
    {
        ValidationIssueType.SCHEMA_DRIFT,
        ValidationIssueType.ADDRESS_MISMATCH,
    }
)


@dataclass
class ValidationIssue:
    issue_type: str
    symbol: str = ""
    bot_id: str = ""
    trade_ts: float = 0.0
    detail: str = ""

    def describe(self) -> str:
        who = f"{self.symbol or '?'}"
        if self.bot_id:
            who += f" [{self.bot_id}]"
        base = f"{self.issue_type}: {who}"
        return f"{base} — {self.detail}" if self.detail else base


@dataclass
class ValidationPolicy:
    """How tolerant the run should be.

    ``max_tolerated`` counts only non-integrity issues. Integrity
    issues always halt on the first occurrence.
    """

    max_tolerated: int = 25
    halt_on_integrity: bool = True
    enabled: bool = True

    @classmethod
    def strict(cls) -> "ValidationPolicy":
        """Halt on the very first issue of any kind. Appropriate for
        a parity run, where one unvalidatable trade invalidates the
        claim being measured."""
        return cls(max_tolerated=0, halt_on_integrity=True)

    @classmethod
    def permissive(cls) -> "ValidationPolicy":
        """Never halt; record everything. For exploratory backtests
        where coverage gaps are expected and acceptable."""
        return cls(max_tolerated=10**9, halt_on_integrity=False)


@dataclass
class SimValidationGuard:
    """Accumulates validation issues and decides when to halt.

    Deliberately has no Qt or asyncio dependency so it can be unit
    tested directly. The controller polls ``should_halt`` and calls
    its own stop path; the guard never stops anything itself.
    """

    policy: ValidationPolicy = field(default_factory=ValidationPolicy)
    issues: list[ValidationIssue] = field(default_factory=list)
    halted: bool = False
    halt_reason: str = ""

    # ── recording ────────────────────────────────────────────────

    def record(
        self,
        issue_type: str,
        symbol: str = "",
        bot_id: str = "",
        trade_ts: float = 0.0,
        detail: str = "",
    ) -> bool:
        """Record an issue. Returns True if this triggered a halt.

        Recording is idempotent with respect to halting: once halted
        the guard keeps collecting issues (useful for the report)
        but the reason is fixed at the first cause.
        """
        if not self.policy.enabled:
            return False
        issue = ValidationIssue(
            issue_type=issue_type,
            symbol=symbol,
            bot_id=bot_id,
            trade_ts=trade_ts,
            detail=detail,
        )
        self.issues.append(issue)

        if issue_type in INTEGRITY_ISSUES and self.policy.halt_on_integrity:
            return self._halt(f"dataset integrity failure — {issue.describe()}")

        if self.tolerated_count > self.policy.max_tolerated:
            return self._halt(
                f"{self.tolerated_count} unvalidatable trade events "
                f"exceeded the limit of {self.policy.max_tolerated} "
                f"(most recent: {issue.describe()})"
            )
        return False

    def _halt(self, reason: str) -> bool:
        if not self.halted:
            self.halted = True
            self.halt_reason = reason
            logger.warning("sim halted: %s", reason)
        return True

    # ── reading ──────────────────────────────────────────────────

    @property
    def tolerated_count(self) -> int:
        """Issues that count against ``max_tolerated``."""
        return sum(1 for i in self.issues if i.issue_type not in INTEGRITY_ISSUES)

    @property
    def integrity_count(self) -> int:
        return sum(1 for i in self.issues if i.issue_type in INTEGRITY_ISSUES)

    @property
    def should_halt(self) -> bool:
        return self.halted

    def counts_by_type(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for i in self.issues:
            out[i.issue_type] = out.get(i.issue_type, 0) + 1
        return out

    def report_lines(self, max_examples: int = 5) -> list[str]:
        lines: list[str] = []
        if not self.issues:
            lines.append("Validation: no unvalidatable trade events.")
            return lines
        verdict = "HALTED" if self.halted else "completed with issues"
        lines.append(
            f"Validation: {verdict} — {len(self.issues):,} issue(s), "
            f"{self.integrity_count:,} integrity / "
            f"{self.tolerated_count:,} coverage"
        )
        if self.halted:
            lines.append(f"  halt reason: {self.halt_reason}")
        for itype, n in sorted(self.counts_by_type().items(), key=lambda kv: -kv[1]):
            lines.append(f"  {n:>6,}  {itype}")
        shown = 0
        for i in self.issues:
            if shown >= max_examples:
                break
            lines.append(f"    e.g. {i.describe()}")
            shown += 1
        if len(self.issues) > shown:
            lines.append(f"    ... and {len(self.issues) - shown:,} more")
        return lines


@dataclass
class ScopeResult:
    """Trades split into what validation can and cannot speak to."""

    in_scope: list = field(default_factory=list)
    out_of_scope: list = field(default_factory=list)
    window_start_ts: float = 0.0
    window_end_ts: float = 0.0

    @property
    def total(self) -> int:
        return len(self.in_scope) + len(self.out_of_scope)

    def describe(self) -> str:
        if not self.total:
            return "Validation scope: no trades supplied."
        return (
            f"Validation scope: {len(self.in_scope):,} of "
            f"{self.total:,} trades fall inside the gate-log window; "
            f"{len(self.out_of_scope):,} predate it and are EXCLUDED "
            "(not failures — no gate data could exist for them)."
        )


def scope_to_validatable_window(
    trades: list,
    window_start_ts: float,
    window_end_ts: float = 0.0,
) -> ScopeResult:
    """Split trades into in-scope and out-of-scope by time window.

    Operator clarification 2026-08-02: "we cannot validate anything
    beyond the 700 trades that have data so we have no need to scan
    the previous 3700 or so."

    The exchange-side YTD set (~4,040 trades from 2026-04-01) is far
    larger than the window any gate data covers (gate.log begins
    2026-06-10). Feeding the whole set to the guard would record
    ~3,340 NO_TABLET/PRE_LISTING issues and trip the halt on the
    first batch — reporting a data-integrity emergency when the real
    situation is simply that gate logging started later.

    Scoping first makes the guard's output meaningful: an issue
    INSIDE the window is a genuine anomaly, because gate data was
    being written then and should exist.

    ``window_end_ts <= 0`` means open-ended.
    """
    res = ScopeResult(
        window_start_ts=float(window_start_ts), window_end_ts=float(window_end_ts)
    )
    for t in trades or []:
        ts = float(
            (
                t.get("timestamp", 0)
                if isinstance(t, dict)
                else getattr(t, "trade_ts", 0)
            )
            or 0
        )
        if ts <= 0:
            # Keep unparseable timestamps IN scope — that is itself
            # a defect the guard should see, not something to hide.
            res.in_scope.append(t)
            continue
        if ts < res.window_start_ts:
            res.out_of_scope.append(t)
            continue
        if res.window_end_ts > 0 and ts > res.window_end_ts:
            res.out_of_scope.append(t)
            continue
        res.in_scope.append(t)
    return res


def validate_trade_event(
    guard: SimValidationGuard,
    symbol: str,
    bot_id: str,
    trade_ts: float,
    candles: Optional[list],
    recorded_address: str = "",
) -> bool:
    """Validate one trade against its tablet. Returns True when the
    event is usable; False when an issue was recorded.

    ``recorded_address`` is optional; when supplied it is recomputed
    from the tablet and compared, which is what catches a tablet
    whose indices have shifted (ADDRESS_MISMATCH).
    """
    from .stone_tablets.addressing import (
        format_address,
        index_for_ts,
        ticker_from_symbol,
    )

    if not trade_ts or trade_ts <= 0:
        guard.record(
            ValidationIssueType.UNRESOLVABLE_TS,
            symbol,
            bot_id,
            trade_ts,
            "timestamp missing or non-positive",
        )
        return False

    if not candles:
        guard.record(
            ValidationIssueType.NO_TABLET,
            symbol,
            bot_id,
            trade_ts,
            "no Stone Tablet for this symbol",
        )
        return False

    idx = index_for_ts(candles, int(trade_ts * 1000))
    if idx is None:
        guard.record(
            ValidationIssueType.PRE_LISTING,
            symbol,
            bot_id,
            trade_ts,
            "trade predates the tablet's first candle",
        )
        return False

    if recorded_address:
        try:
            actual = format_address(ticker_from_symbol(symbol), idx)
        except ValueError as exc:
            guard.record(
                ValidationIssueType.SCHEMA_DRIFT,
                symbol,
                bot_id,
                trade_ts,
                f"address format failed: {exc}",
            )
            return False
        if actual != recorded_address:
            guard.record(
                ValidationIssueType.ADDRESS_MISMATCH,
                symbol,
                bot_id,
                trade_ts,
                f"stored {recorded_address!r} but tablet resolves to "
                f"{actual!r} — tablet indices have shifted",
            )
            return False
    return True


REQUIRED_GATE_DATA_FIELDS = (
    "symbol",
    "scrum_armed",
    "fold_armed",
    "scrum_blockers",
    "fold_blockers",
)


def validate_gate_entry(
    guard: SimValidationGuard,
    entry: dict,
) -> bool:
    """Confirm a gate row still carries the fields comparison needs.

    Verified against both live schemas on 2026-08-02 (per-tick
    v3.23.6 rotations and per-fire v3.23.11+ current) — the two are
    identical, so a miss here means genuinely new drift.
    """
    data = (entry or {}).get("data")
    if not isinstance(data, dict):
        guard.record(
            ValidationIssueType.SCHEMA_DRIFT, detail="gate entry has no 'data' object"
        )
        return False
    missing = [f for f in REQUIRED_GATE_DATA_FIELDS if f not in data]
    if missing:
        guard.record(
            ValidationIssueType.SCHEMA_DRIFT,
            symbol=str(data.get("symbol", "") or ""),
            bot_id=str((entry or {}).get("bot_id", "") or ""),
            detail=f"gate row missing fields: {', '.join(missing)}",
        )
        return False
    return True


__all__ = [
    "INTEGRITY_ISSUES",
    "REQUIRED_GATE_DATA_FIELDS",
    "ScopeResult",
    "SimValidationGuard",
    "ValidationIssue",
    "ValidationIssueType",
    "ValidationPolicy",
    "scope_to_validatable_window",
    "validate_gate_entry",
    "validate_trade_event",
]
