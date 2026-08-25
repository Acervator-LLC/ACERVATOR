"""
src/trading/gate_chain.py — Operator-approved TA gate cleanup, Step 2.

Per docs/audits/2026-05-20_ta_gate_logic_audit.md §6, this module provides
the GateChain framework that will eventually replace the 1,000+ lines of
inline gate evaluation currently spread across ScrummingBot.tick()
(~lines 4540-5980).

DESIGN PRINCIPLES:
  • Each gate is a class with an evaluate(ctx) -> GateResult method.
  • Gates are stateless — all inputs flow through GateContext.
  • The chain evaluates every gate (not short-circuited) so the
    diagnostic blocker list IS the inverse of the trigger conjunction
    BY CONSTRUCTION — drift between trigger and diagnostic is
    architecturally impossible.
  • Override gates (MEM-196 ripe-harvest) are first-class — they
    declare which gates they can override, and the chain applies the
    override AFTER initial evaluation.

CURRENT STATUS (v3.18.11):
  Framework + 14 gate classes lands as PURE ADDITIVE code. ScrummingBot
  is NOT yet rewired to consume this. The Step 3 parity test
  (tests/test_gate_chain_parity.py — Phase 3 of the roadmap) is what
  validates the framework against the v3.18.9 baseline fixture before
  any cutover (Step 4).

  When the parity test passes bit-identically across the 200-tick
  baseline fixture, ScrummingBot.tick() can be refactored to call
  self._scrum_chain.evaluate(ctx) / self._fold_chain.evaluate(ctx).
  Until then, this module is dead code — present but unused by
  production tick().

WHY ADDITIVE FIRST:
  Section 7 of the audit doc lays out the safe-by-construction migration:
  Step 2 (this module, additive) → Step 3 (parity test) → Step 4
  (cutover, gated by Step 3) → Step 5 (retire patchwork). The audit's
  bit-identical regression fixture from v3.18.9 is the safety net.

Patent flag: this is engineering hygiene, not a new mechanism.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Optional

# ─────────────────────────────────────────────────────────────────────
# Data containers — all stateless dataclasses
# ─────────────────────────────────────────────────────────────────────


@dataclass
class GateContext:
    """All inputs every gate evaluator sees. Pure data — no methods.

    Constructed once per tick from ScrummingBot state + computed
    TA primitives. Then fed into both the SCRUM chain and the FOLD
    chain (gates declare which side they apply to).

    Field names mirror the local variable names in ScrummingBot.tick()
    so the cutover (Step 4) is a near-mechanical rename:
      _eff_is_bullish    → ctx.eff_is_bullish
      _eff_trend_hold    → ctx.eff_trend_hold
      _bb_above_upper_dt → ctx.bb_above_upper_dt
      etc.
    """

    # ── Symbol + market data ──
    symbol: str
    ticker_last: float
    bb_pos: float
    bb_upper_dt: float
    bb_lower_dt: float

    # ── Position / target accounting ──
    delta: float  # current_value - target_balance
    delta_pct: float  # |delta| / target_balance × 100
    below_interval: bool  # delta_pct < scrumming_interval_pct

    # ── TA voting + direction ──
    is_bullish: bool  # raw TA voting bullish
    is_bearish: bool  # raw TA voting bearish
    trend_hold: bool  # sustained-uptrend gate
    trend_strength: float
    eff_direction_name: str  # "BULLISH"/"BEARISH"/"NEUTRAL"

    # ── Effective values after v3.16.15 operator-toggle flags ──
    eff_is_bullish: bool
    eff_is_bearish: bool
    eff_trend_hold: bool
    eff_htf_blocks_scrum: bool  # HTF defer applied (SCRUM side)
    eff_htf_blocks_fold: bool

    # ── Operator-toggle flag states (raw) ──
    flag_require_ta_bullish: bool
    flag_hold_in_uptrend: bool
    flag_defer_to_htf: bool
    flag_fold_require_ta_bearish: bool
    flag_fold_defer_to_htf: bool

    # ── BB / Detect-fire state machine ──
    bb_above_upper_dt: bool
    bb_below_lower_dt: bool
    scrum_ok: bool  # midline gate or override
    fold_ok_midline: bool
    target_fires: bool  # detect/fire FSM

    # ── Bot state for stateful gates ──
    cb_blocks_scrum: bool  # circuit breaker SCRUM side
    cb_blocks_fold: bool
    hyst_ok_scrum_side: bool  # OTD hysteresis SCRUM side
    hyst_ok_fold_side: bool
    hyst_armed_scrum_side: bool
    hyst_armed_fold_side: bool
    hyst_ref_scrum_side: float  # pivot price (diagnostic)
    hyst_ref_fold_side: float
    mem253_at_ceiling: bool  # MEM-244 / MEM-253 Smart Ceiling
    mem253_smart_ceiling_usd: float
    mem253_current_pos: float
    has_fold_tranches: bool
    n_fold_tranches: int

    # ── Higher-TF bias ──
    htf_bias_name: Optional[str]  # "BULLISH"/"BEARISH"/"NEUTRAL"/None
    htf_blocks_scrum: bool  # raw (pre flag)
    htf_blocks_fold: bool

    # ── Operator settings copied for diagnostic context ──
    scrumming_interval_pct: float
    trading_fee_pct: float

    # ── Optional fields for ripe-harvest / deep-fold overrides ──
    ripe_scrum: bool = False
    deep_fold: bool = False

    # ── v3.19.16 (Part 6 L4 second-half closure) ──
    # ADX trend strength reading from Wilder DMI computation. Populated by
    # ScrummingBot.tick() from the VotingSummary's ADX value when available;
    # defaults to 0.0 (no-trend) so the ADXTrendSuppressionGate trivially
    # passes when the call site hasn't been wired yet — additive landing
    # pattern from v3.18.11. Production wiring of the field by call sites
    # is a follow-up (operator decides ship cadence).
    adx: float = 0.0

    # ── v3.19.17 (Trading-Discipline Arc #2 — Part 6 L3.b closure) ──
    # Perry Kaufman Efficiency Ratio reading [0.0, 1.0]. Populated by
    # ScrummingBot.tick() from the VotingSummary's Kaufman ER value when
    # available; defaults to 0.0 (sentinel — no-data) so the
    # EfficiencyRatioRegimeGate trivially passes when the call site hasn't
    # been wired yet — additive landing pattern from v3.18.11. The
    # "ER is the Anti-pattern substitute" claim in Part 6 L3 was false at
    # write time (class existed, no caller); this field + the gate close
    # the substitution.
    efficiency_ratio: float = 0.0

    # ── v3.20.7 (Trading-Discipline Arc — v3.19.17 forward-work #3) ──
    # Statistical-extremity reading from ZScoreIndicator. Real z-scores
    # range roughly [−4, +4] in normal markets, with |z| > 2.0 considered
    # the "strong" mean-reversion threshold. Populated by
    # ScrummingBot.tick() from the VotingSummary's `zscore` signal's
    # `details["z"]`. The default 0.0 doubles as both "field not
    # populated" sentinel and "exactly at mean" — in either case the
    # ZScoreExtremityGate trivially passes (since |0| < 2 always), so
    # no special sentinel branch is needed. The audit doc
    # (docs/audits/2026-05-23_indicator_voting_panel_audit.md #5
    # cross-cutting) flagged this gate as queued from the v3.19.17 plan
    # but never shipped; v3.20.7 closes that gap.
    z_score: float = 0.0


@dataclass
class GateResult:
    """One gate's verdict on the current GateContext."""

    passed: bool
    blocker_message: str = ""
    # Override gates set this to the names of OTHER gates they're
    # forcing-pass. The chain handles the actual override application.
    override_gates: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class ChainResult:
    """Final result of evaluating a GateChain on a GateContext.

    ``should_fire`` is the inverse of the existing 10-clause AND chain
    in ScrummingBot.tick(). ``blocked`` is the human-readable
    inverse — the SAME source-of-truth, by construction. The current
    inline code has the trigger conjunction and the diagnostic blocker
    list as two separate code paths that must stay in sync manually.
    """

    should_fire: bool
    passed: list[str] = field(default_factory=list)
    blocked: list[tuple[str, str]] = field(default_factory=list)
    overrides_applied: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────
# Gate ABC
# ─────────────────────────────────────────────────────────────────────


class Gate(ABC):
    """Abstract gate. Subclasses define name + side + evaluate()."""

    name: str = "<unnamed>"
    side: Literal["scrum", "fold", "both"] = "both"
    # If non-empty, this gate can OVERRIDE the listed gates when it passes.
    # The chain applies overrides AFTER initial evaluation pass.
    overrides: tuple[str, ...] = ()

    @abstractmethod
    def evaluate(self, ctx: GateContext) -> GateResult: ...


# ─────────────────────────────────────────────────────────────────────
# Gate implementations
#
# Each one mirrors the corresponding inline check in ScrummingBot.tick().
# Variable names + return logic are 1:1 with the live code so the Step 3
# parity test can prove bit-identical evaluation.
# ─────────────────────────────────────────────────────────────────────


class DeltaPositiveGate(Gate):
    """SCRUM-only: delta must be positive (surplus above target)."""

    name = "delta_positive"
    side = "scrum"

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.delta > 0:
            return GateResult(passed=True)
        return GateResult(passed=False, blocker_message="delta≤0")


class IntervalGate(Gate):
    """Both sides: |Δ%| must be ≥ scrumming_interval_pct."""

    name = "interval"
    side = "scrum"  # FOLD trigger doesn't include below_interval check
    # at the trigger line; it's checked one level up
    # and skipped if no tranches queued

    def evaluate(self, ctx: GateContext) -> GateResult:
        if not ctx.below_interval:
            return GateResult(passed=True)
        return GateResult(
            passed=False,
            blocker_message=f"below_interval(Δ%<{ctx.scrumming_interval_pct})",
        )


class TranchesQueuedGate(Gate):
    """FOLD-only: at least one fold tranche must be queued."""

    name = "tranches_queued"
    side = "fold"

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.has_fold_tranches:
            return GateResult(passed=True)
        return GateResult(passed=False, blocker_message="no-tranches-queued")


class TADirectionGate(Gate):
    """Both sides: TA direction must match the side (with operator
    toggle override). Mirrors the v3.16.15 flag application:
      SCRUM: eff_is_bullish = is_bullish if flag_require_ta_bullish else True
      FOLD : eff_is_bearish = is_bearish if flag_fold_require_ta_bearish else True
    """

    def __init__(self, side: Literal["scrum", "fold"]):
        self.side = side
        self.name = f"ta_{('bullish' if side == 'scrum' else 'bearish')}"

    def evaluate(self, ctx: GateContext) -> GateResult:
        if self.side == "scrum":
            if ctx.eff_is_bullish:
                return GateResult(passed=True)
            return GateResult(
                passed=False,
                blocker_message=f"TA-not-bullish(dir={ctx.eff_direction_name})",
            )
        else:
            if ctx.eff_is_bearish:
                return GateResult(passed=True)
            return GateResult(
                passed=False,
                blocker_message=f"TA-not-bearish(dir={ctx.eff_direction_name})",
            )


class TrendHoldGate(Gate):
    """SCRUM-only: trend-hold blocks scrum (sustained uptrend)."""

    name = "trend_hold"
    side = "scrum"

    def evaluate(self, ctx: GateContext) -> GateResult:
        if not ctx.eff_trend_hold:
            return GateResult(passed=True)
        return GateResult(
            passed=False, blocker_message=f"trend_hold({ctx.trend_strength:.0%})"
        )


class MidlineGate(Gate):
    """Both sides: BB midline gate.
      SCRUM: scrum_ok (bb_pos > 0.50 or MEM-196 override)
      FOLD : fold_ok_midline (bb_pos < 0.50 or MEM-196 override)

    The MEM-196 ripe-harvest override is applied UPSTREAM in
    ScrummingBot.tick() — scrum_ok/fold_ok_midline are passed
    into the context already overridden. So this gate just
    reads the effective value.
    """

    def __init__(self, side: Literal["scrum", "fold"]):
        self.side = side
        self.name = f"midline_{side}"

    def evaluate(self, ctx: GateContext) -> GateResult:
        ok = ctx.scrum_ok if self.side == "scrum" else ctx.fold_ok_midline
        if ok:
            return GateResult(passed=True)
        label = "scrum_ok" if self.side == "scrum" else "fold_ok_midline"
        return GateResult(
            passed=False, blocker_message=f"{label}=False(bb_pos={ctx.bb_pos:.2f})"
        )


class TargetFiresGate(Gate):
    """SCRUM-only: detect/fire state machine must be in FIRE."""

    name = "target_fires"
    side = "scrum"

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.target_fires:
            return GateResult(passed=True)
        return GateResult(
            passed=False, blocker_message="target_fires=False(detect/fire)"
        )


class BBProximityGate(Gate):
    """Both sides: BB position past the detect threshold.
    SCRUM: bb_above_upper_dt
    FOLD : bb_below_lower_dt
    """

    def __init__(self, side: Literal["scrum", "fold"]):
        self.side = side
        self.name = f"bb_proximity_{side}"

    def evaluate(self, ctx: GateContext) -> GateResult:
        if self.side == "scrum":
            if ctx.bb_above_upper_dt:
                return GateResult(passed=True)
            return GateResult(
                passed=False,
                blocker_message=(
                    f"BB-below-upper-detect(bb_pos={ctx.bb_pos:.2f}"
                    f"<{ctx.bb_upper_dt:.2f})"
                ),
            )
        else:
            if ctx.bb_below_lower_dt:
                return GateResult(passed=True)
            return GateResult(
                passed=False,
                blocker_message=(
                    f"BB-above-lower-detect(bb_pos={ctx.bb_pos:.2f}"
                    f">{ctx.bb_lower_dt:.2f})"
                ),
            )


class CircuitBreakerGate(Gate):
    """Both sides: soft Circuit Breaker must not be tripped on this side."""

    def __init__(self, side: Literal["scrum", "fold"]):
        self.side = side
        self.name = f"circuit_breaker_{side}"

    def evaluate(self, ctx: GateContext) -> GateResult:
        blocks = ctx.cb_blocks_scrum if self.side == "scrum" else ctx.cb_blocks_fold
        if not blocks:
            return GateResult(passed=True)
        return GateResult(passed=False, blocker_message="CB-soft-trip")


class HTFDeferGate(Gate):
    """Both sides: higher-TF phantom defer.
    SCRUM blocked when HTF says BULLISH (don't sell into confirmed uptrend)
    FOLD  blocked when HTF says BEARISH (don't buy into confirmed downtrend)
    """

    def __init__(self, side: Literal["scrum", "fold"]):
        self.side = side
        self.name = f"htf_defer_{side}"

    def evaluate(self, ctx: GateContext) -> GateResult:
        blocks = (
            ctx.eff_htf_blocks_scrum
            if self.side == "scrum"
            else ctx.eff_htf_blocks_fold
        )
        if not blocks:
            return GateResult(passed=True)
        label = "HTF-bullish" if self.side == "scrum" else "HTF-bearish"
        return GateResult(passed=False, blocker_message=label)


class HysteresisGate(Gate):
    """Both sides: OTD (Minimum Opposing Trade Distance) hysteresis.
    Mirrors v3.15.77 (gate added) + v3.18.1 (consumed at autonomous
    trigger) — the gate is True (clear-to-trade) when EITHER the
    side is disarmed OR price has moved by interval+fee from the
    pivot captured at arming.
    """

    def __init__(self, side: Literal["scrum", "fold"]):
        self.side = side
        self.name = f"hysteresis_{side}"

    def evaluate(self, ctx: GateContext) -> GateResult:
        ok = ctx.hyst_ok_scrum_side if self.side == "scrum" else ctx.hyst_ok_fold_side
        if ok:
            return GateResult(passed=True)
        ref = (
            ctx.hyst_ref_scrum_side if self.side == "scrum" else ctx.hyst_ref_fold_side
        )
        eff_pct = ctx.scrumming_interval_pct + ctx.trading_fee_pct
        if self.side == "scrum":
            required = ref * (1.0 + eff_pct / 100.0)
            return GateResult(
                passed=False,
                blocker_message=(
                    f"OTD-hyst(px ${ctx.ticker_last:.8f} < "
                    f"${required:.8f}; pivot ${ref:.8f} "
                    f"+ {eff_pct:.2f}%)"
                ),
            )
        else:
            required = ref * (1.0 - eff_pct / 100.0)
            return GateResult(
                passed=False,
                blocker_message=(
                    f"OTD-hyst(px ${ctx.ticker_last:.8f} > "
                    f"${required:.8f}; pivot ${ref:.8f} "
                    f"- {eff_pct:.2f}%)"
                ),
            )


class SmartCeilingGate(Gate):
    """FOLD-only: MEM-244 / MEM-253 Smart Ceiling.

    When position_ceiling_enabled and current position ≥ anchor ×
    position_ceiling_multiple, FOLD is hard-stopped. Computed
    upstream into ctx.mem253_at_ceiling.
    """

    name = "smart_ceiling"
    side = "fold"

    def evaluate(self, ctx: GateContext) -> GateResult:
        if not ctx.mem253_at_ceiling:
            return GateResult(passed=True)
        return GateResult(passed=False, blocker_message="MEM-253-position-ceiling")


# ─────────────────────────────────────────────────────────────────────
# Override gates — first-class modeling of MEM-196 ripe-harvest /
# deep-fold pattern.
# ─────────────────────────────────────────────────────────────────────


class RipeHarvestScrumOverride(Gate):
    """MEM-196 v3 + MEM-202 fix: when ripe-scrum conditions hold
    (delta > 0, above upper detect threshold), force-pass:
      - midline_scrum
      - target_fires
      - trend_hold
      - ta_bullish

    The current inline code does these rewrites at line 5323+ in
    ScrummingBot.tick(). This gate exposes the pattern as a first-
    class override declared up front, so the chain semantics are
    transparent rather than buried.
    """

    name = "ripe_harvest_override"
    side = "scrum"
    overrides = ("midline_scrum", "target_fires", "trend_hold", "ta_bullish")

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.ripe_scrum:
            return GateResult(passed=True, override_gates=self.overrides)
        return GateResult(passed=False, blocker_message="not-ripe")


class DeepFoldOverride(Gate):
    """MEM-196 v3 deep-fold override: when deep-fold conditions hold
    (delta < 0, below lower detect threshold), force-pass:
      - midline_fold
      - ta_bearish

    MEM-171 per-tranche initial_buy_price floor is preserved
    (not in the override list — see audit doc §6a).
    """

    name = "deep_fold_override"
    side = "fold"
    overrides = ("midline_fold", "ta_bearish")

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.deep_fold:
            return GateResult(passed=True, override_gates=self.overrides)
        return GateResult(passed=False, blocker_message="not-deep")


# ─────────────────────────────────────────────────────────────────────
# v3.19.16 — Part 6 L4 second-half closure
# ─────────────────────────────────────────────────────────────────────


class ADXTrendSuppressionGate(Gate):
    """SCRUM-only: ADX-based strong-trend MR suppression.

    Wilder's classical interpretation: ADX > 25 indicates a trending
    market; ADX > 30 is a strong trend; ADX > 50 is an extreme trend.
    Mean-reversion strategies bleed in trending markets — fading the
    band-touch loses on every pullback because the "mean" is moving
    faster than the reversion. The Department Leads' L4 (Oscillators)
    pushback (Part 6 / Part 6 L4) explicitly requested this gate.

    The first half of P2.9 (wiring ADXIndicator into VotingEngine) was
    closed by MEM-200. This gate is the second half: an explicit
    SCRUM-side suppressor that blocks the trigger when ADX shows strong
    trend regime, regardless of TA voting direction.

    Threshold default ``adx_threshold=30.0`` is the textbook Wilder
    strong-trend value, and it now means what it says.

    HISTORY, because the number moved twice. v3.19.16 set 30 from the
    textbook. That blocked 100% of every baseline fixture, because
    ``ADXIndicator._wilder_smooth`` accumulated instead of averaging and
    returned ~14x the real ADX. v3.20.22 responded by recalibrating the
    THRESHOLD to 500.0 against the inflated distribution (62-681,
    median 239) rather than fixing the indicator — operator-approved as
    Option 1 of `docs/audits/2026-05-25_audit_gate_activity_baseline_
    fixtures.md`, with Option 2 (fix the smoothing) left open.

    v3.24.83 took Option 2. `_wilder_smooth` now averages, so ADX is
    back inside its definitional [0, 100] and the textbook reading
    (>25 trending, >30 strong, >50 extreme) applies directly. That
    docstring carried an explicit instruction for this moment — "If a
    future ship replaces ``_wilder_smooth`` with textbook averaging
    Wilder (audit Option 2), this threshold MUST be reset to 30" — and
    the two changes ship together. Landing the indicator fix alone
    would have left a gate that can never fire, since the new ADX
    cannot reach 500.

    Do NOT divide by 14 to compare against the textbook any more; the
    prior note told readers to and it is no longer true.

    ADDITIVE LANDING (v3.18.11 pattern):
      ``GateContext.adx`` defaults to 0.0 — the gate trivially passes
      until the production call site (ScrummingBot.tick()) is wired
      to populate ``ctx.adx`` from the VotingSummary's ADX reading.
      The gate is structurally correct, tested, and present in the
      canonical SCRUM chain at landing; production wiring of the
      input field is a separate follow-up.

    sadp: R28 R42 R55 R76  # additive-first landing per the
                       # v3.18.11 GateChain framework migration
                       # discipline; v3.20.22 R76 DMW empirical
                       # recalibration with documented rationale
    """

    name = "adx_trend_suppression"
    side = "scrum"

    def __init__(self, adx_threshold: float = 30.0) -> None:
        self.adx_threshold = adx_threshold

    def evaluate(self, ctx: GateContext) -> GateResult:
        # ADX of 0.0 is the "field not populated" sentinel — the gate
        # passes (does not block). Once the production call site
        # populates ctx.adx, the gate becomes active.
        if ctx.adx <= 0.0:
            return GateResult(passed=True)
        if ctx.adx < self.adx_threshold:
            return GateResult(passed=True)
        return GateResult(
            passed=False,
            blocker_message=(
                f"adx_trend_suppression(ADX={ctx.adx:.1f}>"
                f"{self.adx_threshold:.0f}; strong-trend MR suppression)"
            ),
        )


# ─────────────────────────────────────────────────────────────────────
# v3.19.17 — Part 6 L3.b second-half closure (Kaufman Efficiency Ratio)
# ─────────────────────────────────────────────────────────────────────


class EfficiencyRatioRegimeGate(Gate):
    """SCRUM-only: Kaufman Efficiency Ratio regime classifier.

    Perry Kaufman's Efficiency Ratio (1995) measures market quality:
    ER = |net price change| / sum(|individual bar changes|). ER → 1.0
    means efficient trending; ER → 0.0 means noisy/choppy. The
    Department Leads' L3 pushback (Part 6 / Part 6 L3) named this
    metric as the Anti-pattern suppressor — but until v3.19.17 the
    KaufmanERIndicator class existed without any consumer. This gate
    closes that L3.b finding from the v3.19.16 indicator-coverage
    audit.

    Behavior:
      ER ≥ 0.70 → strong-trend regime, MR strategy bleeds → block SCRUM
      ER ≤ 0.05 → no-edge market (essentially flat) → block SCRUM
      otherwise → pass (normal accumulation regime)

    The two-sided suppression matches Kaufman's regime taxonomy:
    SCRUM mean-reversion needs price oscillation. Strong trends move
    the mean faster than reversion can catch; flat no-edge markets
    have no oscillation amplitude to harvest. Both should suppress
    the trigger.

    Threshold defaults (operator-tunable):
      ``upper_threshold=0.70`` — Kaufman's "highly efficient trend"
      ``lower_threshold=0.05`` — empirical "no-edge" floor

    ADDITIVE LANDING (v3.18.11 pattern):
      ``GateContext.efficiency_ratio`` defaults to 0.0 — interpreted
      as "field not populated" rather than "no edge." The gate
      passes trivially until the production call site populates
      ctx.efficiency_ratio from the VotingSummary's KaufmanER reading.

    sadp: R28 R42 R55  # additive-first landing per the v3.18.11
                       # GateChain framework migration discipline
    """

    name = "efficiency_ratio_regime"
    side = "scrum"

    def __init__(
        self, upper_threshold: float = 0.70, lower_threshold: float = 0.05
    ) -> None:
        self.upper_threshold = upper_threshold
        self.lower_threshold = lower_threshold

    def evaluate(self, ctx: GateContext) -> GateResult:
        # ER of 0.0 is the "field not populated" sentinel — pass.
        # Real ER values from KaufmanERIndicator are bounded strictly
        # in (0, 1] when there is any price motion at all (path_length
        # is summed with epsilon 1e-9). A true zero ER would require
        # identical close prices across all N+1 bars, which the
        # sentinel safely represents as "no data."
        if ctx.efficiency_ratio <= 0.0:
            return GateResult(passed=True)
        if ctx.efficiency_ratio >= self.upper_threshold:
            return GateResult(
                passed=False,
                blocker_message=(
                    f"efficiency_ratio_regime(ER="
                    f"{ctx.efficiency_ratio:.3f}≥"
                    f"{self.upper_threshold:.2f}; strong-trend MR "
                    f"suppression)"
                ),
            )
        if ctx.efficiency_ratio <= self.lower_threshold:
            return GateResult(
                passed=False,
                blocker_message=(
                    f"efficiency_ratio_regime(ER="
                    f"{ctx.efficiency_ratio:.3f}≤"
                    f"{self.lower_threshold:.2f}; no-edge market "
                    f"suppression)"
                ),
            )
        return GateResult(passed=True)


# ─────────────────────────────────────────────────────────────────────
# v3.20.7 — Trading-Discipline Arc #3 — ZScoreExtremityGate
# (queued from v3.19.17 plan, audit doc 2026-05-23 flagged as never
# shipped; cross-cutting finding #5 closure)
# ─────────────────────────────────────────────────────────────────────


class ZScoreExtremityGate(Gate):
    """ASYMMETRIC two-sided gate: contrarian filter at statistical extremes.

    At extreme z-scores, short-term mean-reversion is the dominant
    force. The accumulation strategy doesn't want to be caught on the
    WRONG SIDE of that reversion:

      • z > +upper (price extreme HIGH)  → mean-reversion will pull
        price DOWN. The bot must NOT FOLD into that drop — buying at
        the statistical top is fighting the reversion. SCRUM is
        actually MORE attractive here (sell the top before it falls).

      • z < −lower (price extreme LOW)   → mean-reversion will pull
        price UP. The bot must NOT SCRUM into that rebound — selling
        at the statistical bottom is fighting the reversion. FOLD is
        MORE attractive here.

    The gate's behavior is DIRECTIONAL — it blocks based on which
    side it's instantiated on:

      ZScoreExtremityGate(side="scrum")  → blocks SCRUM when z < −lower
      ZScoreExtremityGate(side="fold")   → blocks FOLD when z > +upper

    Sentinel handling. Unlike ADX (which is always ≥ 0) and KER
    (which is always > 0 with any price motion), z-score *can* be
    exactly 0.0 at the population mean. The 0.0 default doubles as
    "field not populated" AND "exactly at mean" — but in either
    case |z| = 0 < upper/lower thresholds, so the gate trivially
    passes. No special sentinel branch needed.

    Threshold defaults match the audit's recommendation and standard
    statistical convention:
      ``upper_threshold = 2.0`` — "strong high" per the ZScoreIndicator
      ``lower_threshold = 2.0`` — symmetric (operator-tunable to make
                                  asymmetric if needed)

    Same additive-landing discipline as ADX + KER gates: lands as
    structurally correct + tested + in canonical chains, with
    ScrummingBot.tick() call-site wiring landing in the same ship
    (v3.20.7 unlike v3.19.16's two-step landing — the pattern is now
    established enough to wire end-to-end in one cascade).

    sadp: R28 FL  R55 GOV  R62 FRG  R68 DPA
    """

    name = "zscore_extremity"

    def __init__(
        self,
        side: str = "scrum",
        upper_threshold: float = 2.0,
        lower_threshold: float = 2.0,
    ) -> None:
        if side not in ("scrum", "fold"):
            raise ValueError(
                f"ZScoreExtremityGate side must be 'scrum' or 'fold', " f"got {side!r}"
            )
        self.side = side
        self.upper_threshold = float(upper_threshold)
        self.lower_threshold = float(lower_threshold)

    def evaluate(self, ctx: GateContext) -> GateResult:
        z = ctx.z_score
        if self.side == "scrum":
            # Block SCRUM when price is statistically extreme LOW —
            # selling at the bottom fights the imminent mean-reversion.
            if z < -self.lower_threshold:
                return GateResult(
                    passed=False,
                    blocker_message=(
                        f"zscore_extremity(z={z:+.2f}<"
                        f"-{self.lower_threshold:.1f}; extreme-low "
                        f"contrarian filter — mean-reversion pending)"
                    ),
                )
            return GateResult(passed=True)
        # side == "fold"
        # Block FOLD when price is statistically extreme HIGH —
        # buying at the top fights the imminent mean-reversion.
        if z > self.upper_threshold:
            return GateResult(
                passed=False,
                blocker_message=(
                    f"zscore_extremity(z={z:+.2f}>"
                    f"+{self.upper_threshold:.1f}; extreme-high "
                    f"contrarian filter — mean-reversion pending)"
                ),
            )
        return GateResult(passed=True)


# ─────────────────────────────────────────────────────────────────────
# GateChain
# ─────────────────────────────────────────────────────────────────────


class GateChain:
    """Holds a list of Gates for one side; evaluates them all on a
    GateContext and returns a ChainResult.

    The chain ALWAYS evaluates every gate (no short-circuit) so the
    diagnostic blocker list is complete + the inverse of the trigger
    conjunction by construction.

    Override gates run AFTER initial evaluation. When an override gate
    passes, the gates it lists as overridable are moved from blocked
    → passed, and their names are recorded in overrides_applied.
    """

    def __init__(self, gates: list[Gate], side: Literal["scrum", "fold"]) -> None:
        self._side = side
        # Filter to gates applicable on this side (or "both")
        self._gates = [g for g in gates if g.side in (side, "both")]
        # Quick lookup by name for override resolution
        self._gates_by_name = {g.name: g for g in self._gates}
        # Separate override gates so we evaluate them in a second pass
        self._override_gates = [g for g in self._gates if g.overrides]
        self._regular_gates = [g for g in self._gates if not g.overrides]

    def evaluate(self, ctx: GateContext) -> ChainResult:
        # Pass 1: evaluate every regular gate
        passed: list[str] = []
        blocked: list[tuple[str, str]] = []
        blocked_index: dict[str, int] = {}  # name → index into blocked
        for gate in self._regular_gates:
            result = gate.evaluate(ctx)
            if result.passed:
                passed.append(gate.name)
            else:
                blocked_index[gate.name] = len(blocked)
                blocked.append((gate.name, result.blocker_message))

        # Pass 2: apply overrides
        overrides_applied: list[str] = []
        for gate in self._override_gates:
            result = gate.evaluate(ctx)
            if not result.passed:
                # Override gate didn't fire — its own status doesn't
                # appear in either passed/blocked. It's a meta-gate
                # whose ONLY job is to unblock others.
                continue
            for target_name in result.override_gates:
                if target_name in blocked_index:
                    idx = blocked_index.pop(target_name)
                    # Mark blocked entry as override-cleared. We move
                    # the gate name from blocked → passed and track it
                    # in overrides_applied so the operator can see in
                    # diagnostics that the gate would have blocked but
                    # was unblocked by the override.
                    _name, _msg = blocked[idx]
                    blocked[idx] = (_name, f"OVERRIDDEN_BY:{gate.name}({_msg})")
                    overrides_applied.append(target_name)

        # Final pass: split blocked entries that were overridden out
        # of the blocked list and into passed. The OVERRIDDEN_BY
        # marker stays in the chain result for diagnostics (an
        # operator-readable trail).
        final_blocked: list[tuple[str, str]] = []
        for name, msg in blocked:
            if msg.startswith("OVERRIDDEN_BY:"):
                passed.append(name)
            else:
                final_blocked.append((name, msg))

        return ChainResult(
            should_fire=(not final_blocked),
            passed=passed,
            blocked=final_blocked,
            overrides_applied=overrides_applied,
        )

    @property
    def side(self) -> str:
        return self._side

    def gate_names(self) -> list[str]:
        """Diagnostic helper: list of gate names in this chain."""
        return [g.name for g in self._gates]


# ─────────────────────────────────────────────────────────────────────
# Factory builders — canonical SCRUM and FOLD chains matching the
# current ScrummingBot.tick() trigger conjunctions.
# ─────────────────────────────────────────────────────────────────────


def build_scrumming_scrum_chain() -> GateChain:
    """Construct the SCRUM-side chain matching ScrummingBot.tick()
    line 5475-5478. Order is operator-meaningful in diagnostic logs;
    matches the current _scrum_blockers append order at line 5415-5450.

    v3.19.16 adds ``ADXTrendSuppressionGate`` (P2.9 second-half closure
    per Part 6 L4). Additive landing: ``ctx.adx`` defaults to 0.0 so
    the gate trivially passes until the call site (ScrummingBot.tick())
    is wired to populate it.

    v3.19.17 adds ``EfficiencyRatioRegimeGate`` (Part 6 L3.b closure
    per the v3.19.16 indicator-coverage audit). Same additive-landing
    discipline: ``ctx.efficiency_ratio`` defaults to 0.0 so the gate
    trivially passes until call-site wiring lands.
    """
    return GateChain(
        gates=[
            DeltaPositiveGate(),
            IntervalGate(),
            TADirectionGate(side="scrum"),
            TrendHoldGate(),
            MidlineGate(side="scrum"),
            TargetFiresGate(),
            BBProximityGate(side="scrum"),
            CircuitBreakerGate(side="scrum"),
            HTFDeferGate(side="scrum"),
            HysteresisGate(side="scrum"),
            ADXTrendSuppressionGate(),  # v3.19.16 — Part 6 L4 closure
            EfficiencyRatioRegimeGate(),  # v3.19.17 — Part 6 L3.b closure
            ZScoreExtremityGate(
                side="scrum"
            ),  # v3.20.7 — extreme-low SCRUM contrarian filter
            RipeHarvestScrumOverride(),  # last — runs in pass 2
        ],
        side="scrum",
    )


def build_scrumming_fold_chain() -> GateChain:
    """Construct the FOLD-side chain matching ScrummingBot.tick()
    line 6083-6086. Matches _fold_blockers append order at line 5941-5970.
    """
    return GateChain(
        gates=[
            TranchesQueuedGate(),
            TADirectionGate(side="fold"),
            MidlineGate(side="fold"),
            SmartCeilingGate(),
            BBProximityGate(side="fold"),
            CircuitBreakerGate(side="fold"),
            HTFDeferGate(side="fold"),
            HysteresisGate(side="fold"),
            ZScoreExtremityGate(
                side="fold"
            ),  # v3.20.7 — extreme-high FOLD contrarian filter
            DeepFoldOverride(),
        ],
        side="fold",
    )
