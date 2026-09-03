"""GateChain framework for evaluating the SCRUM and FOLD trigger gates.

Each gate is a stateless class with an ``evaluate(ctx) -> GateResult``
method; ``GateContext`` carries every input a gate can read. A
``GateChain`` evaluates every gate in its list — never short-circuits —
so its blocker list is the exact inverse of what fired, by
construction. Override gates declare, in ``overrides``, which other
gates they force-pass when they themselves pass; the chain applies
overrides in a second pass after the initial evaluation.

ScrummingBot builds one SCRUM chain and one FOLD chain at construction
(``self._scrum_chain``, ``self._fold_chain``) and calls
``evaluate(ctx)`` on each every tick. ``ChainResult.should_fire``
directly gates whether that tick's SCRUM or FOLD trade executes.
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

    Built once per tick from ScrummingBot state and computed TA
    primitives, then fed into both the SCRUM chain and the FOLD chain
    (each gate declares which side it applies to). Field names mirror
    ScrummingBot.tick()'s local variable names, e.g. ``_eff_is_bullish``
    becomes ``ctx.eff_is_bullish``.
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

    # ── Effective values after operator-toggle flags ──
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
    mem253_at_ceiling: bool
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

    # Populated each tick by ScrummingBot.tick(); 0.0 means not
    # populated, and ADXTrendSuppressionGate passes trivially on it.
    adx: float = 0.0

    # Populated each tick by ScrummingBot.tick(); 0.0 means not
    # populated, and EfficiencyRatioRegimeGate passes trivially on it.
    efficiency_ratio: float = 0.0

    # Populated each tick by ScrummingBot.tick(); 0.0 means not
    # populated or exactly at mean, and ZScoreExtremityGate passes
    # trivially either way.
    z_score: float = 0.0


@dataclass
class GateResult:
    """One gate's verdict on the current GateContext."""

    passed: bool
    blocker_message: str = ""
    # Names the other gates this result force-passes; GateChain applies
    # the override in its second pass.
    override_gates: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class ChainResult:
    """Final verdict from evaluating a GateChain on one GateContext.

    ``should_fire`` is True exactly when no regular gate remains
    blocked after overrides are applied. ``blocked`` is produced in
    the same evaluation pass, so it can never drift out of sync with
    ``should_fire`` — there is no separate trigger-only code path.
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
    # Non-empty means this gate overrides the listed gates when it
    # passes; GateChain applies the override after the initial pass.
    overrides: tuple[str, ...] = ()

    @abstractmethod
    def evaluate(self, ctx: GateContext) -> GateResult: ...


# ─────────────────────────────────────────────────────────────────────
# Gate implementations
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
    """SCRUM-only: |Δ%| must be ≥ scrumming_interval_pct."""

    name = "interval"
    side = "scrum"
    # FOLD checks below_interval one level up, skipped when no
    # tranches are queued.

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
    """Usable on either side: TA direction must match the side, subject
    to the operator toggle flags:
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
    """Usable on either side: BB midline gate.
      SCRUM: scrum_ok (bb_pos > 0.50, unmodified by any override)
      FOLD : fold_ok_midline (bb_pos < 0.50, unmodified by any override)

    evaluate() reads the raw value. When this gate is blocked,
    GateChain's own override pass can still move it to passed via
    RipeHarvestScrumOverride or DeepFoldOverride, without touching
    ctx.scrum_ok / ctx.fold_ok_midline.
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
    """Usable on either side: BB position past the detect threshold.
    SCRUM: passes on ctx.bb_above_upper_dt
    FOLD : passes on ctx.bb_below_lower_dt
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
    """Usable on either side: passes unless the soft Circuit Breaker is
    tripped on this instance's side.
    """

    def __init__(self, side: Literal["scrum", "fold"]):
        self.side = side
        self.name = f"circuit_breaker_{side}"

    def evaluate(self, ctx: GateContext) -> GateResult:
        blocks = ctx.cb_blocks_scrum if self.side == "scrum" else ctx.cb_blocks_fold
        if not blocks:
            return GateResult(passed=True)
        return GateResult(passed=False, blocker_message="CB-soft-trip")


class HTFDeferGate(Gate):
    """Usable on either side: higher-timeframe defer.
    SCRUM blocked when HTF says BULLISH (don't sell into a confirmed uptrend)
    FOLD  blocked when HTF says BEARISH (don't buy into a confirmed downtrend)
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
    """Usable on either side: OTD (Minimum Opposing Trade Distance)
    hysteresis. Passes when EITHER the side is disarmed OR price has
    moved by interval+fee from the pivot price captured at arming.
    ctx.hyst_ok_scrum_side / ctx.hyst_ok_fold_side already carry that
    computed verdict; this gate reads it and builds the blocker
    message from the pivot when blocked.
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
    """FOLD-only: hard-stops FOLD once position reaches the smart
    ceiling. Blocks when ctx.mem253_at_ceiling is True, computed
    upstream from position_ceiling_enabled and current position ≥
    anchor × position_ceiling_multiple.
    """

    name = "smart_ceiling"
    side = "fold"

    def evaluate(self, ctx: GateContext) -> GateResult:
        if not ctx.mem253_at_ceiling:
            return GateResult(passed=True)
        return GateResult(passed=False, blocker_message="MEM-253-position-ceiling")


# ─────────────────────────────────────────────────────────────────────
# Override gates — force-pass other gates when ripe-harvest / deep-fold
# conditions hold.
# ─────────────────────────────────────────────────────────────────────


class RipeHarvestScrumOverride(Gate):
    """SCRUM-side override: when ripe-scrum conditions hold (delta > 0,
    price already above the upper detect threshold), force-passes
    every gate named in ``overrides`` even if it blocked on the raw
    context.

    GateChain applies the override in its second evaluation pass; the
    target gates' own evaluate() methods are unaffected and still read
    the unmodified GateContext.
    """

    name = "ripe_harvest_override"
    side = "scrum"
    overrides = ("midline_scrum", "target_fires", "trend_hold", "ta_bullish")

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.ripe_scrum:
            return GateResult(passed=True, override_gates=self.overrides)
        return GateResult(passed=False, blocker_message="not-ripe")


class DeepFoldOverride(Gate):
    """FOLD-side override: when deep-fold conditions hold (delta < 0,
    price already below the lower detect threshold), force-passes
    every gate named in ``overrides`` even if it blocked on the raw
    context.

    The per-tranche initial_buy_price floor is not one of the
    overridden gates, so it is unaffected by this override.
    """

    name = "deep_fold_override"
    side = "fold"
    overrides = ("midline_fold", "ta_bearish")

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.deep_fold:
            return GateResult(passed=True, override_gates=self.overrides)
        return GateResult(passed=False, blocker_message="not-deep")


class ADXTrendSuppressionGate(Gate):
    """SCRUM-only: blocks SCRUM when Wilder ADX shows a strong trend.

    Mean-reversion strategies lose in a strongly trending market — the
    "mean" moves faster than price can revert to it. This gate blocks
    SCRUM when ``ctx.adx >= adx_threshold`` (default 30.0, Wilder's
    textbook strong-trend value) and passes when ``ctx.adx <
    adx_threshold``. ``ctx.adx <= 0.0`` is the "field not populated"
    sentinel and always passes. ScrummingBot.tick() populates
    ``ctx.adx`` each tick from the VotingSummary's ADX signal detail.
    """

    name = "adx_trend_suppression"
    side = "scrum"

    def __init__(self, adx_threshold: float = 30.0) -> None:
        self.adx_threshold = adx_threshold

    def evaluate(self, ctx: GateContext) -> GateResult:
        # adx <= 0.0 is the not-populated sentinel: treated as
        # no-trend, so the gate passes.
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


class EfficiencyRatioRegimeGate(Gate):
    """SCRUM-only: blocks SCRUM at either extreme of Kaufman's
    Efficiency Ratio (ER = |net price change| / sum(|bar changes|),
    Kaufman 1995).

    Blocks when ``ctx.efficiency_ratio >= upper_threshold`` (default
    0.70 — strong-trend regime, MR strategy bleeds) or when
    ``ctx.efficiency_ratio <= lower_threshold`` (default 0.05 —
    no-edge, flat market with nothing to harvest). Passes between the
    two thresholds. ``ctx.efficiency_ratio <= 0.0`` is the "field not
    populated" sentinel and always passes (real ER values from
    KaufmanERIndicator are > 0 whenever there is any price motion).
    ScrummingBot.tick() populates the field each tick from the
    VotingSummary's Kaufman ER signal detail.
    """

    name = "efficiency_ratio_regime"
    side = "scrum"

    def __init__(
        self, upper_threshold: float = 0.70, lower_threshold: float = 0.05
    ) -> None:
        self.upper_threshold = upper_threshold
        self.lower_threshold = lower_threshold

    def evaluate(self, ctx: GateContext) -> GateResult:
        # Real ER is always > 0 given any price motion, so <= 0.0 is
        # unambiguous as the not-populated sentinel.
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


class ZScoreExtremityGate(Gate):
    """Contrarian filter at statistical price extremes; behavior depends
    on which side it is instantiated for.

      side="scrum": blocks SCRUM when z < -lower_threshold (default
        2.0) — price is extreme-low, so mean-reversion should pull it
        back up and folding (not scrumming) is the trade.
      side="fold" : blocks FOLD when z > +upper_threshold (default
        2.0) — price is extreme-high, so mean-reversion should pull it
        back down and scrumming (not folding) is the trade.

    ctx.z_score doubles as "field not populated" and "exactly at the
    mean" — both read as 0.0, and |0| is always inside the threshold,
    so the gate passes on either. ScrummingBot.tick() populates
    ctx.z_score each tick from the VotingSummary's zscore signal
    detail.
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
                # An override gate's own pass/fail never appears in
                # passed or blocked; it only unblocks other gates.
                continue
            for target_name in result.override_gates:
                if target_name in blocked_index:
                    idx = blocked_index.pop(target_name)
                    # Marks the entry override-cleared and records it
                    # in overrides_applied for diagnostics.
                    _name, _msg = blocked[idx]
                    blocked[idx] = (_name, f"OVERRIDDEN_BY:{gate.name}({_msg})")
                    overrides_applied.append(target_name)

        # Moves override-cleared entries from blocked to passed; the
        # OVERRIDDEN_BY marker stays in the message for diagnostics.
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
    """Construct the SCRUM-side chain ScrummingBot.tick() evaluates each
    tick via self._scrum_chain.evaluate(ctx); should_fire on the result
    directly gates whether a SCRUM trade executes. Gate order
    determines where each blocked gate's message appears in
    ChainResult.blocked.
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
            ADXTrendSuppressionGate(),
            EfficiencyRatioRegimeGate(),
            ZScoreExtremityGate(side="scrum"),  # extreme-low SCRUM contrarian filter
            RipeHarvestScrumOverride(),  # runs in pass 2 regardless of list position
        ],
        side="scrum",
    )


def build_scrumming_fold_chain() -> GateChain:
    """Construct the FOLD-side chain ScrummingBot.tick() evaluates each
    tick via self._fold_chain.evaluate(ctx); should_fire on the result
    directly gates whether a FOLD trade executes.
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
            ZScoreExtremityGate(side="fold"),  # extreme-high FOLD contrarian filter
            DeepFoldOverride(),
        ],
        side="fold",
    )
