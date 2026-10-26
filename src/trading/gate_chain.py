"""GateChain evaluation for the SCRUM and FOLD trigger gates.

Each Gate returns a GateResult from ``evaluate(ctx)``, and GateContext
carries every input a gate reads. GateChain evaluates every gate with no
short-circuit; ChainResult.blocked names each gate that failed, and an
override gate force-passes the gates listed in its ``overrides``.
ScrummingBot.tick calls evaluate on ``self._scrum_chain`` and
``self._fold_chain``, and ChainResult.should_fire decides whether that
tick's trade executes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from .otd_math import minimum_opposing_trade_distance_pct

OVERRIDE_APPLIED_FORMAT = "{gate} overridden by {override}: {refusal}"
"""One ``ChainResult.overrides_applied`` entry, naming the override."""

OVERRIDE_NOT_APPLIED_FORMAT = "{message} [override not applied: {overrides}]"
"""One ``ChainResult.blocked`` message from a gate an override covers."""

OVERRIDES_APPLIED_KEY = "overrides_applied"
"""The gate record key every ``overrides_applied`` entry is written under."""

TREND_HOLD_OVERRIDE = "trend_hold_override"
"""The override ScrummingBot.tick applies when the delta reaches twice the
scrumming interval or band travel fires."""


@dataclass
class GateContext:
    """Inputs every Gate reads, built once per tick by ScrummingBot.tick.

    Field names mirror that method's locals: ``_eff_is_bullish`` becomes
    ``eff_is_bullish``.
    """

    symbol: str
    ticker_last: float
    bb_pos: float
    # Detect thresholds in bb_pos terms (0.0 lower band, 1.0 upper), never prices.
    bb_upper_dt: float
    bb_lower_dt: float

    delta: float  # current_value - target_balance
    delta_pct: float  # |delta| / target_balance × 100
    below_interval: bool  # delta_pct < scrumming_interval_pct

    is_bullish: bool
    is_bearish: bool
    trend_hold: bool
    trend_strength: float
    eff_direction_name: str  # "BULLISH"/"BEARISH"/"NEUTRAL"

    eff_is_bullish: bool
    eff_is_bearish: bool
    eff_trend_hold: bool
    eff_htf_blocks_scrum: bool
    eff_htf_blocks_fold: bool

    flag_require_ta_bullish: bool
    flag_hold_in_uptrend: bool
    flag_defer_to_htf: bool
    flag_fold_require_ta_bearish: bool
    flag_fold_defer_to_htf: bool

    bb_above_upper_dt: bool
    bb_below_lower_dt: bool
    # Combines the midline with the phantom lock; bb_pos alone may not explain it.
    scrum_ok: bool
    fold_ok_midline: bool
    target_fires: bool

    cb_blocks_scrum: bool
    cb_blocks_fold: bool
    hyst_ok_scrum_side: bool  # OTD = Minimum Opposing Trade Distance
    hyst_ok_fold_side: bool
    hyst_armed_scrum_side: bool
    hyst_armed_fold_side: bool
    hyst_ref_scrum_side: float  # pivot price captured at arming
    hyst_ref_fold_side: float
    mem253_at_ceiling: bool
    mem253_smart_ceiling_usd: float
    mem253_current_pos: float
    has_fold_tranches: bool
    n_fold_tranches: int

    htf_bias_name: Optional[str]  # "BULLISH"/"BEARISH"/"NEUTRAL"/None
    htf_blocks_scrum: bool  # raw, before flag_defer_to_htf
    htf_blocks_fold: bool

    scrumming_interval_pct: float
    trading_fee_pct: float

    ripe_scrum: bool = False
    deep_fold: bool = False

    # 0.0 is the not-populated sentinel; ADXTrendSuppressionGate passes on it.
    adx: float = 0.0

    # 0.0 is the not-populated sentinel; EfficiencyRatioRegimeGate passes on it.
    efficiency_ratio: float = 0.0

    # 0.0 reads as not-populated or exactly at mean; ZScoreExtremityGate passes.
    z_score: float = 0.0

    # The collated vote confidence and the floor it is read against. Both 0.0
    # leaves TADirectionGate on its plain refusal text.
    eff_confidence: float = 0.0
    ta_conf_floor: float = 0.0


@dataclass(frozen=True)
class EffectiveGateFlags:
    """The five GateContext ``eff_`` values the Strategy Gate Flags produce."""

    eff_is_bullish: bool
    eff_is_bearish: bool
    eff_trend_hold: bool
    eff_htf_blocks_scrum: bool
    eff_htf_blocks_fold: bool


def effective_gate_flags(
    settings: Any,
    *,
    is_bullish: bool,
    is_bearish: bool,
    trend_hold: bool,
    htf_blocks_scrum: bool,
    htf_blocks_fold: bool,
) -> EffectiveGateFlags:
    """Apply the five Strategy Gate Flags on ``settings`` to five raw readings.

    A cleared require flag passes its direction outright; a cleared hold or
    defer flag drops its block. ScrummingBot.tick, ata_gate_scan.gate_context,
    back_test.tape_context and paper_run.tape_context all read this one
    mapping, and each flag defaults to True when ``settings`` omits it.
    """
    require_bullish = bool(getattr(settings, "scrum_require_ta_bullish", True))
    hold_in_uptrend = bool(getattr(settings, "scrum_hold_in_uptrend", True))
    defer_scrum = bool(getattr(settings, "scrum_defer_to_htf", True))
    require_bearish = bool(getattr(settings, "fold_require_ta_bearish", True))
    defer_fold = bool(getattr(settings, "fold_defer_to_htf", True))
    return EffectiveGateFlags(
        eff_is_bullish=bool(is_bullish) if require_bullish else True,
        eff_is_bearish=bool(is_bearish) if require_bearish else True,
        eff_trend_hold=bool(trend_hold) if hold_in_uptrend else False,
        eff_htf_blocks_scrum=bool(htf_blocks_scrum) if defer_scrum else False,
        eff_htf_blocks_fold=bool(htf_blocks_fold) if defer_fold else False,
    )


@dataclass
class GateResult:
    """One gate's verdict on the current GateContext."""

    passed: bool
    blocker_message: str = ""
    # Gate names GateChain force-passes in its second pass.
    override_gates: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class ChainResult:
    """Verdict from evaluating a GateChain on one GateContext.

    ``should_fire`` is True when ``blocked`` is empty after overrides are
    applied. A refusal that stood is a ``blocked`` entry carrying
    ``OVERRIDE_NOT_APPLIED_FORMAT`` when an override covers that gate, and a
    refusal an override replaced is an ``overrides_applied`` entry in
    ``OVERRIDE_APPLIED_FORMAT``.
    """

    should_fire: bool
    passed: list[str] = field(default_factory=list)
    blocked: list[tuple[str, str]] = field(default_factory=list)
    overrides_applied: list[str] = field(default_factory=list)


class Gate(ABC):
    """Abstract gate; a subclass sets ``name`` and ``side`` and defines evaluate."""

    name: str = "<unnamed>"
    side: Literal["scrum", "fold", "both"] = "both"
    # Non-empty names the gates GateChain force-passes when this one passes.
    overrides: tuple[str, ...] = ()

    @abstractmethod
    def evaluate(self, ctx: GateContext) -> GateResult: ...


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
    # No FOLD twin; ScrummingBot.tick returns early on below_interval when both
    # its fold queue and distribution accumulator are empty.

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
    """Passes on ``ctx.eff_is_bullish`` for scrum, ``ctx.eff_is_bearish`` for fold.

    ScrummingBot.tick sets each to True outright when
    ``flag_require_ta_bullish`` or ``flag_fold_require_ta_bearish`` is off.
    """

    def __init__(self, side: Literal["scrum", "fold"]):
        self.side = side
        self.name = f"ta_{('bullish' if side == 'scrum' else 'bearish')}"

    def _refusal(self, ctx: GateContext) -> str:
        """The refusal text, naming the floor when the direction cleared it.

        ``eff_confidence`` and ``ta_conf_floor`` both 0.0 leaves the plain
        direction text.
        """
        wanted = "BULLISH" if self.side == "scrum" else "BEARISH"
        direction_ok = ctx.eff_direction_name in (wanted, "NEUTRAL")
        if direction_ok and (ctx.eff_confidence or ctx.ta_conf_floor):
            return (
                f"TA-conf-below-floor(dir={ctx.eff_direction_name},"
                f"conf={ctx.eff_confidence:.4f}<{ctx.ta_conf_floor:.4f})"
            )
        return f"TA-not-{wanted.lower()}(dir={ctx.eff_direction_name})"

    def evaluate(self, ctx: GateContext) -> GateResult:
        passed = ctx.eff_is_bullish if self.side == "scrum" else ctx.eff_is_bearish
        if passed:
            return GateResult(passed=True)
        return GateResult(passed=False, blocker_message=self._refusal(ctx))


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
    """Passes on ``ctx.scrum_ok`` for scrum, ``ctx.fold_ok_midline`` for fold.

    ``ctx.scrum_ok`` combines the midline with ScrummingBot's phantom lock, and
    ``blocker_message`` reports ``ctx.bb_pos`` for either cause.
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
    """Passes on ``ctx.bb_above_upper_dt`` for scrum, ``ctx.bb_below_lower_dt``
    for fold.

    ``blocker_message`` compares ``ctx.bb_pos`` against ``ctx.bb_upper_dt`` or
    ``ctx.bb_lower_dt``, all three in bb_pos terms.
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
    """Passes unless ``ctx.cb_blocks_scrum`` or ``ctx.cb_blocks_fold`` is set."""

    def __init__(self, side: Literal["scrum", "fold"]):
        self.side = side
        self.name = f"circuit_breaker_{side}"

    def evaluate(self, ctx: GateContext) -> GateResult:
        blocks = ctx.cb_blocks_scrum if self.side == "scrum" else ctx.cb_blocks_fold
        if not blocks:
            return GateResult(passed=True)
        return GateResult(passed=False, blocker_message="CB-soft-trip")


class HTFDeferGate(Gate):
    """Blocks on ``ctx.eff_htf_blocks_scrum`` or ``ctx.eff_htf_blocks_fold``.

    ``ctx.htf_bias_name`` BULLISH sets the scrum flag; BEARISH sets the fold flag.
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
    """Passes on ``ctx.hyst_ok_scrum_side`` or ``ctx.hyst_ok_fold_side``.

    ``blocker_message`` rebuilds the required price from ``hyst_ref_scrum_side``
    or ``hyst_ref_fold_side`` plus the
    ``minimum_opposing_trade_distance_pct`` of the context's interval and fee.
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
        eff_pct = minimum_opposing_trade_distance_pct(
            ctx.scrumming_interval_pct, ctx.trading_fee_pct
        )
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
    """Blocks FOLD when ``ctx.mem253_at_ceiling`` is set.

    ScrummingBot.tick sets it once ``ctx.mem253_current_pos`` reaches
    ``ctx.mem253_smart_ceiling_usd``.
    """

    name = "smart_ceiling"
    side = "fold"

    def evaluate(self, ctx: GateContext) -> GateResult:
        if not ctx.mem253_at_ceiling:
            return GateResult(passed=True)
        return GateResult(passed=False, blocker_message="position-ceiling")


class RipeHarvestScrumOverride(Gate):
    """Force-passes every gate in ``overrides`` when ``ctx.ripe_scrum`` is set.

    ScrummingBot.tick sets ``ripe_scrum`` from positive ``delta``, cleared
    ``below_interval``, and ``bb_pos`` at or above ``bb_upper_dt``.
    """

    name = "ripe_harvest_override"
    side = "scrum"
    overrides = ("midline_scrum", "target_fires", "trend_hold", "ta_bullish")

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.ripe_scrum:
            return GateResult(passed=True, override_gates=self.overrides)
        return GateResult(passed=False, blocker_message="not-ripe")


class DeepFoldOverride(Gate):
    """Force-passes every gate in ``overrides`` when ``ctx.deep_fold`` is set.

    ScrummingBot.tick sets ``deep_fold`` from negative ``delta``, cleared
    ``below_interval``, and ``bb_pos`` at or below ``bb_lower_dt``.
    """

    name = "deep_fold_override"
    side = "fold"
    overrides = ("midline_fold", "ta_bearish")

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.deep_fold:
            return GateResult(passed=True, override_gates=self.overrides)
        return GateResult(passed=False, blocker_message="not-deep")


class ADXTrendSuppressionGate(Gate):
    """Blocks SCRUM when ``ctx.adx`` reaches ``adx_threshold``, default 30.0.

    ``ctx.adx <= 0.0`` is the not-populated sentinel and passes;
    ScrummingBot.tick fills the field from the VotingSummary ADX signal detail.
    """

    name = "adx_trend_suppression"
    side = "scrum"

    def __init__(self, adx_threshold: float = 30.0) -> None:
        self.adx_threshold = adx_threshold

    def evaluate(self, ctx: GateContext) -> GateResult:
        if ctx.adx <= 0.0:
            return GateResult(passed=True)
        if ctx.adx < self.adx_threshold:
            return GateResult(passed=True)
        return GateResult(
            passed=False,
            blocker_message=(
                f"adx_trend_suppression(ADX={ctx.adx:.1f}≥"
                f"{self.adx_threshold:.1f}; strong-trend MR suppression)"
            ),
        )


class EfficiencyRatioRegimeGate(Gate):
    """Blocks SCRUM at either extreme of ``ctx.efficiency_ratio``.

    Blocks at or above ``upper_threshold`` (0.70) and at or below
    ``lower_threshold`` (0.05); ``ctx.efficiency_ratio <= 0.0`` is the
    not-populated sentinel and passes.
    """

    name = "efficiency_ratio_regime"
    side = "scrum"

    def __init__(
        self, upper_threshold: float = 0.70, lower_threshold: float = 0.05
    ) -> None:
        self.upper_threshold = upper_threshold
        self.lower_threshold = lower_threshold

    def evaluate(self, ctx: GateContext) -> GateResult:
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
    """Blocks on an extreme ``ctx.z_score`` opposite the side it is built for.

    Scrum blocks below ``-lower_threshold`` and fold above
    ``upper_threshold``, both 2.0 by default; ``ctx.z_score`` of 0.0 passes.
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


class GateChain:
    """Evaluates every Gate for one side and returns a ChainResult.

    A Gate declaring ``overrides`` is held back to a second pass, where
    passing it moves each named gate from ``blocked`` into ``overrides_applied``.
    """

    def __init__(self, gates: list[Gate], side: Literal["scrum", "fold"]) -> None:
        self._side = side
        self._gates = [g for g in gates if g.side in (side, "both")]
        self._gates_by_name = {g.name: g for g in self._gates}
        self._override_gates = [g for g in self._gates if g.overrides]
        self._regular_gates = [g for g in self._gates if not g.overrides]
        covered: dict[str, list[str]] = {}
        for gate in self._override_gates:
            for target_name in gate.overrides:
                covered.setdefault(target_name, []).append(gate.name)
        self._covered_by = {name: tuple(names) for name, names in covered.items()}

    def covering_overrides(self, gate_name: str) -> tuple[str, ...]:
        """Return the override gates whose ``overrides`` names ``gate_name``."""
        return self._covered_by.get(gate_name, ())

    def evaluate(self, ctx: GateContext) -> ChainResult:
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

        # An override gate's own verdict never reaches passed or blocked.
        overrides_applied: list[str] = []
        for gate in self._override_gates:
            result = gate.evaluate(ctx)
            if not result.passed:
                continue
            for target_name in result.override_gates:
                if target_name in blocked_index:
                    idx = blocked_index.pop(target_name)
                    _name, _msg = blocked[idx]
                    blocked[idx] = (_name, f"OVERRIDDEN_BY:{gate.name}({_msg})")
                    overrides_applied.append(
                        OVERRIDE_APPLIED_FORMAT.format(
                            gate=target_name, override=gate.name, refusal=_msg
                        )
                    )

        final_blocked: list[tuple[str, str]] = []
        for name, msg in blocked:
            if msg.startswith("OVERRIDDEN_BY:"):
                passed.append(name)
                continue
            covering = self.covering_overrides(name)
            if covering:
                msg = OVERRIDE_NOT_APPLIED_FORMAT.format(
                    message=msg, overrides=", ".join(covering)
                )
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
        """Return the ``name`` of every Gate this chain kept for its side."""
        return [g.name for g in self._gates]


def build_scrumming_scrum_chain() -> GateChain:
    """Build the chain ScrummingBot.tick holds as ``self._scrum_chain``.

    Gate order fixes where each blocked gate appears in ChainResult.blocked.
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
            ZScoreExtremityGate(side="scrum"),
            RipeHarvestScrumOverride(),  # runs in pass 2 regardless of list position
        ],
        side="scrum",
    )


def build_scrumming_fold_chain() -> GateChain:
    """Build the chain ScrummingBot.tick holds as ``self._fold_chain``."""
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
            ZScoreExtremityGate(side="fold"),
            DeepFoldOverride(),
        ],
        side="fold",
    )
