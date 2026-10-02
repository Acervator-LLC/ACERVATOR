"""Accumulation Trading Bot — the live Scrum/Fold engine.

Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All
rights reserved.

The core cycle:
  1. delta = (holdings × price) - target
  2. delta > 0 and delta_pct >= interval → SCRUM (sell the excess,
     deposit USD into the fold queue)
  3. fold_queue > 0 and price < fold_ref → FOLD (buy back lower,
     accumulate extra asset)
  4. after a fold: target += profit (compound growth)

"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..exchange.base import ExchangeInterface

from ..exchange.base import OrderSide, OrderType
from .target_bands import at_target_dust_band
from .bot_container import (
    BotContainer,
    BotConfig,
    BotMode,
    BotState,
    as_finite_float,
)
from .ta_engine import (
    MIN_CANDLES_FOR_TA,
    VotingEngine,
    VotingSummary,
    SignalDirection,
    candles_from_raw,
    detect_bb_proximity,
    BBProximityResult,
    detect_landing_strip_v2,
)
from .phantom_balance import (
    TIMEFRAME_SECONDS,
    PhantomBalanceManager,
    TimeframeCoordinator,
    default_phantom_timeframes,
)

from .ata_gate_scan import (
    LANDING_STRIP_FAVOUR,
    LANDING_STRIP_STRENGTH_FAVOUR,
    TIGHTENING_MIN_CANDLES,
    TIGHTENING_MIN_CONSECUTIVE,
    TIGHTENING_SHRINK_THRESHOLD,
    TIGHTENING_TOLERANCE_PCT,
)
from .gate_chain import (
    GateContext,
    build_scrumming_scrum_chain,
    build_scrumming_fold_chain,
)
from .scrumming import (
    CapitalReservationMixin,
    CircuitBreakerMixin,
    ExecutionEngineMixin,
    FoldTrancheAccountingMixin,
    ReconciliationEngineMixin,
    SnapshotEmitterMixin,
    StateSerializerMixin,
    TickPhaseMixin,
    WireRoutingMixin,
)
from .scrumming.execution import MemorisedTrade, SettledFillFee
from .scrumming.snapshots import yes_no as _yes_no
from .scrumming.fold_tranches import (
    _STRONG_TREND_CANDLES,
    _STRONG_TREND_MIN_BULL_CANDLES,
)
from .scrumming.sizing import (
    cartridge_threshold_usd,
    cycle_growth_cap_usd,
    delta_below_interval,
    fold_rate_taper,
    position_ceiling,
    priced_usd,
    ratio_to_ceiling,
    scrumming_interval_usd,
    target_delta_pct,
    target_delta_usd,
)

logger = logging.getLogger("acervator.scrumming")

#: Seconds between detonation trigger checks.
_DETONATION_CHECK_INTERVAL_S: float = 3600.0

#: Minimum seconds the detonation bullish latch survives without a check.
_DETONATION_LATCH_MIN_TTL_S: float = 2.0 * _DETONATION_CHECK_INTERVAL_S


_TA_CONFIDENCE_FLOOR = 0.25
"""Minimum TA confidence before a direction counts as actionable.
"""

_BB_PRIORITY_SKEW = 0.30
"""How far the BB-priority arm relaxes ``_TA_CONFIDENCE_FLOOR``.

The number is the one v3.15.64 shipped. What changed is its UNIT: it was
0.30 of confidence ADDED to the measurement, and it is now a 0.30
PROPORTIONAL relaxation of the threshold the measurement is judged
against. See ``_BB_PRIORITY_CONFIDENCE_FLOOR``.
"""

_BB_PRIORITY_CONFIDENCE_FLOOR = _TA_CONFIDENCE_FLOOR / (1.0 + _BB_PRIORITY_SKEW)
"""The floor that applies when the three BB-priority conditions coincide.

WHAT THE OPERATOR ASKED FOR, verbatim, 2026-04-26::

    "BB proximity and / or contact should immediately trigger or heavily
     favor a trade if Minimum Opposing Trade Distance is also satisfied
     and a Target Delta is available."
    Refinement: "Should skew TA confidence, not over ride as this seems
     dangerous."

The refinement is a ruling. ``DEVELOPMENT_CHRONICLE`` records why: the
first attempt WAS an override -- ``_bb_priority_scrum`` /
``_bb_priority_fold`` clauses bolted onto the SCRUM/FOLD if-conditions --
and the operator refused it by name.

WHAT SHIPPED INSTEAD, AND WHY IT WAS THE SAME OVERRIDE. v3.15.64 replaced
those clauses with ``eff_confidence += 0.30``, sized in the chronicle as
"enough to lift any low-confidence NEUTRAL reading (0.0-0.24) over the
0.25 threshold". Confidence is bounded [0, 1]. A skew of 0.30 against a
floor of 0.25 reduces ``eff_confidence + 0.30 >= 0.25`` to
``eff_confidence >= -0.05``, which EVERY reading satisfies, including
exactly 0.0. So the confidence conjunct became universally true on that
arm: the refused override, restored in arithmetic. Issue #102, found by
the #100 unit when a decision sweep on that arm returned a structural
zero -- not "no decisions changed" but "this comparison has no false
case".

A SECOND DEFECT IN THE SAME LINE. The chronicle also required the skew
to be "not so large that it inflates already-confident readings into
something deceptive". The addition inflated every reading, and the
inflated number -- not the measured one -- was what nine downstream
sites in ``tick()`` printed, including the ``HOLD FOLD`` explainer that
names the failing conjunct. The audit trail reported a confidence no
indicator produced.

THE REPAIR, AND WHY THIS SHAPE. ``eff_confidence`` is a measured
quantity. It is left alone. The favour is what it always was in the
operator's own words -- a PRIORITISATION -- so it is expressed against
the THRESHOLD, and the arm gets this floor instead of the standing one.

The relaxation is PROPORTIONAL, not subtractive, and that is what makes
the gate able to refuse. Subtracting the same 0.30 from 0.25 lands at or
below zero and is the tautology again. Dividing preserves zero: however
large the favour, a confidence of exactly 0.0 is still refused, and here
the arm refuses everything below 0.25 / 1.30 = 0.1923. It is also what
the operator's word means -- a skew SCALES, a shift OFFSETS, and a shift
is what shipped.

NO NEW NUMBER IS INTRODUCED. This floor is derived from the two constants
already of record: the 0.25 floor and the 0.30 favour. The magnitude of
the favour is unchanged; only its form and its target are.

WHAT IS DELIBERATELY NOT CHANGED. The direction conjunct
(``eff_direction in (BULLISH, NEUTRAL)``) still gates the trade, exactly
as v3.15.64 preserved it -- actively-contradicting TA still refuses. The
non-priority arm keeps ``_TA_CONFIDENCE_FLOOR`` untouched.

v3.26.x (issue #104) -- THIS CONSTANT IS NO LONGER THE WHOLE FLOOR ON
THE ARM. Two further favours were found in the same shape and repaired
the same way, so the arm's skew is now one term of a sum that
``_skewed_confidence_floor`` divides by. With the other two at zero the
answer is still exactly this number, which is why it is kept and still
quoted in the log line.
"""

_STRONG_TREND_MIN_BULL_SHARE = _STRONG_TREND_MIN_BULL_CANDLES / _STRONG_TREND_CANDLES
"""Share of the last 20 candles that must close up to call it a trend.

WRITTEN AS ITS TWO COUNTS, not as 0.65. The quantity it is compared
against is ``bull_count / len(recent)``, a share, and a threshold on a
share has to be a share too. 13 / 20 is bit-identical to the 0.65 this
line used to hold -- both are 0x1.4cccccccccccdp-1 -- so the comparison
answers exactly as it did, and it now says which 20 candles and how
many of them.

TWO READERS, ONE NUMBER. ``tick`` sets TREND-HOLD from it, and
``_strong_trend_now`` answers the fold-tranche count bound with it. The
literal used to sit in the TREND-HOLD line alone; a second copy inside
the bound would be a second definition of the same phrase.

WHY THIS READING AND NOT ADX, since the file carries both.
``ADXIndicator`` names a ``strong_trend`` detail at ADX >= 35 and
``ADXTrendSuppressionGate`` refuses a SCRUM at ADX >= 30. Neither can
serve as the count bound's exception: the gate refuses the very sell
that would open the extra tranches, and ``RipeHarvestScrumOverride``
lists ``midline_scrum``, ``target_fires``, ``trend_hold`` and
``ta_bullish`` -- not ``adx_trend_suppression`` -- so nothing lifts it.
TREND-HOLD IS lifted: ``tick`` clears it on band travel or on a delta of
twice the interval, and the comment at that arm says it exists to catch
harvests "during strong trends". That is the sell the operator's
exception is about, so that is the reading the exception uses.
"""


def _skewed_confidence_floor(skew: float, floor: float = _TA_CONFIDENCE_FLOOR) -> float:
    """``floor`` relaxed by ``skew`` proportionally; a skew <= -1 returns infinity."""
    denominator = 1.0 + skew
    if denominator <= 0.0:
        return math.inf
    return floor / denominator


_WIRE_CREDIT_CAP = 20
"""Per-tranche cap on wire-credit DETAIL entries.

Everything older is folded into ``wire_credits_rolled``, which keeps the
totals exactly. See ``ScrummingBot._add_wire_credits`` for the measurement
that motivated this.
"""


def _roll_wire_credit_overflow(tranche: dict) -> int:
    """Trim ``wire_credits`` to the cap, folding excess into ``wire_credits_rolled``.

    Returns:
      How many detail entries were rolled up.

    """
    wc = tranche.get("wire_credits")
    if not isinstance(wc, list) or len(wc) <= _WIRE_CREDIT_CAP:
        return 0
    overflow = wc[:-_WIRE_CREDIT_CAP]
    del wc[:-_WIRE_CREDIT_CAP]
    rolled = tranche.setdefault(
        "wire_credits_rolled",
        {
            "count": 0,
            "total_usd": 0.0,
            "by_source": {},
            "first_ts": None,
            "last_ts": None,
        },
    )
    by_source = rolled.setdefault("by_source", {})
    for e in overflow:
        if not isinstance(e, dict):
            continue
        try:
            usd = float(e.get("usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            usd = 0.0
        src = str(e.get("source", "") or "unknown")
        rolled["count"] = int(rolled.get("count", 0)) + 1
        rolled["total_usd"] = round(float(rolled.get("total_usd", 0.0) or 0.0) + usd, 8)
        by_source[src] = round(float(by_source.get(src, 0.0) or 0.0) + usd, 8)
        ts = e.get("ts")
        if ts is not None:
            if rolled.get("first_ts") is None:
                rolled["first_ts"] = ts
            rolled["last_ts"] = ts
    return len(overflow)


_USD_STABLE_QUOTES = frozenset(
    {
        "USD",
        "USDC",
        "USDT",
        "USDS",
        "USDP",
        "USDD",
        "DAI",
        "BUSD",
        "GUSD",
        "TUSD",
        "PYUSD",
        "FDUSD",
    }
)


def is_usd_stable_quote(currency: str) -> bool:
    """Return True when ``currency`` is a USD-equivalent stable quote."""
    return (currency or "").upper() in _USD_STABLE_QUOTES


def _extract_signal_detail(
    summary: Optional["VotingSummary"],
    indicator_name: str,
    detail_key: str,
    default: float = 0.0,
) -> float:
    """Return an indicator's ``detail_key`` from ``summary``, else ``default``."""
    if summary is None:
        return default
    for sig in summary.signals:
        if sig.indicator == indicator_name:
            val = sig.details.get(detail_key, default)
            try:
                return float(val) if val is not None else default
            except (TypeError, ValueError):
                return default
    return default


@dataclass
class StackTrancheSummary:
    """A stand-in summary carrying the vote recorded when a Stack opened."""

    consensus_confidence: float = 0.0
    consensus_direction: str = "stack"


class ScrummingBot(
    CapitalReservationMixin,
    CircuitBreakerMixin,
    ExecutionEngineMixin,
    FoldTrancheAccountingMixin,
    ReconciliationEngineMixin,
    SnapshotEmitterMixin,
    StateSerializerMixin,
    TickPhaseMixin,
    WireRoutingMixin,
    BotContainer,
):
    """Speculative Scrumming auto-trader."""

    def __init__(
        self,
        config: BotConfig,
        exchange: ExchangeInterface,
        coordinator: Optional[TimeframeCoordinator] = None,
        ta_weights: Optional[dict[str, float]] = None,
        phantom_timeframes: Optional[list[str]] = None,
        enable_phantoms: bool = True,
        sim_mode: bool = False,
        capital_registry: Optional[Any] = None,
    ) -> None:
        if config.mode != BotMode.SCRUMMING:
            raise ValueError(
                f"ScrummingBot requires BotMode.SCRUMMING; " f"got {config.mode!r}"
            )
        super().__init__(config, exchange)

        self._target_balance = config.target_balance
        self._current_holdings: float = 0.0
        self._last_price: float = 0.0
        self._memorised_trades: list[MemorisedTrade] = []
        self._initialised = False
        self._invisible = config.visibility == "internal"
        self._aggressive = config.aggressive_trading
        self._sim_mode = bool(sim_mode)
        self._capital_registry = capital_registry
        if self._sim_mode:
            try:
                from ..core.event_bus import EventBus

                self._bus = EventBus()
            except Exception as _bus_exc:
                logger.error(
                    "sim_mode: could not isolate the event bus (%s) — "
                    "refusing to construct the bot rather than emit "
                    "onto the live bus",
                    _bus_exc,
                )
                raise RuntimeError(
                    f"sim bus isolation failed: {_bus_exc}. Refusing to "
                    f"build a sim bot that would emit on the "
                    f"process-wide EventBus."
                ) from _bus_exc

        self._ta_weights = ta_weights
        self._voting_engine = VotingEngine(weights=ta_weights)
        self._last_summary: Optional[VotingSummary] = None
        self._last_bb: Optional[BBProximityResult] = None
        self._last_gate_state: dict = {
            "scrum_armed": False,
            "fold_armed": False,
            "scrum_blockers": ["pre-tick"],
            "fold_blockers": ["pre-tick"],
            "evaluated_at_tick": 0,
        }
        self._last_gate_light_key: str = ""

        self._scrum_chain = build_scrumming_scrum_chain()
        self._fold_chain = build_scrumming_fold_chain()

        self._coordinator = coordinator or TimeframeCoordinator(bus=self._bus)
        self._phantom_mgr = PhantomBalanceManager(self._coordinator)

        try:
            from ..exchange.timeframes import available_timeframes as _avail_tfs

            _offered: Optional[list[str]] = list(_avail_tfs(config.exchange_id))
        except Exception:
            _offered = None
        # No stored selection: one timeframe straight above the bot's own,
        # so a phantom the Comp field could never weigh is never built.
        self._phantom_timeframes = list(
            phantom_timeframes
            or default_phantom_timeframes(config.ta_timeframe, _offered)
        )
        self._phantom_tf_dropped: list[str] = []
        self._phantom_tf_dropped_note: Optional[str] = None
        if _offered is not None:
            _allowed = set(_offered)
            _original = list(self._phantom_timeframes)
            self._phantom_timeframes = [
                tf for tf in self._phantom_timeframes if tf in _allowed
            ]
            self._phantom_tf_dropped = [tf for tf in _original if tf not in _allowed]
            if self._phantom_tf_dropped:
                self._phantom_tf_dropped_note = (
                    f"Phantom timeframes dropped: "
                    f"{', '.join(self._phantom_tf_dropped)} — "
                    f"'{config.exchange_id}' does not serve them. "
                    f"Remaining: {self._phantom_timeframes}."
                )

        self._phantoms_enabled = enable_phantoms
        self._phantoms_started = False

        self._fold_accumulator: float = 0.0
        self._dist_accumulator: float = 0.0
        self._fold_queue_usd: float = 0.0
        self._fold_queue_ref_price: float = 0.0

        self._standing_surplus_usd: float = 0.0

        self._hold_tick_counter: int = 0

        self._reconcile_tick_counter: int = 0
        self._reconcile_interval: int = 20
        self._fill_history = None

        self._fold_tranches: list[dict] = []
        self._main_lots: list[dict] = []

        self._last_sell_venue_fee: Optional[SettledFillFee] = None
        self._last_fill_venue_fee: Optional[SettledFillFee] = None

        self._stack_tranches: list[dict] = []
        self._stack_created: int = 0
        self._stack_discarded: int = 0
        # Epoch second an operator cleared the two counters above, 0.0 when never.
        self._stack_counters_reset_ts: float = 0.0

        self._tranches_created_lifetime: int = 0
        self._tranches_closed_lifetime: int = 0
        self._tranches_malformed_dropped: int = 0
        # Epoch second an operator cleared the three counters above, 0.0 when never.
        self._tranches_counters_reset_ts: float = 0.0
        # Count of SELLS that have opened fold tranches.
        self._scrum_sells_lifetime: int = 0
        # How many of the last 20 candles closed up, 0 until a tick measures it.
        self._last_trend_bull_candles: int = 0

        self._scrum_target_mode: str = "search"
        self._scrum_target_side: Optional[str] = None

        self._manual_fire_pending: bool = False

        self._anchor_target_balance: float = float(config.target_balance)

        # Never-checked defaults for a bot with no saved detonation state.
        self._detonation_last_check_ts: float = 0.0
        self._detonation_last_signal_bullish: bool = False

        # _hedge_balance_initial reads config.hedge_balance, so the seed cannot
        # drift from the ceiling a restart rebuilds.
        self._hedge_bal: float = self._hedge_balance_initial
        self._hedge_trades: int = 0

        self._last_trade_price: float = 0.0
        self._last_trade_side: Optional[str] = None

        self._hyst_armed_fold_side: bool = False
        self._hyst_armed_scrum_side: bool = False
        self._hyst_ref_fold_side: float = 0.0
        self._hyst_ref_scrum_side: float = 0.0

        self._quote_to_usd: float = 1.0
        self._quote_to_usd_last_fetch: float = 0.0
        self._quote_to_usd_warned: bool = False

        self._tick_counter: int = 0
        self._tick_skip: int = 1
        self._tick_skip_search: int = 1

        self._fold_diag_tick: int = 0
        self._fold_diag_last_blocker_set: str = ""

        self._phantom_locked: bool = False
        self._phantom_lock_timeframe: str = ""

        self._smart_wire_mgr = None
        self._retained_this_cycle_usd: float = 0.0
        self._market_pairs_scout = None

        self._crr_token: Optional[str] = None
        self._crr_last_reserved_qty: float = 0.0
        self._exchange_balance_cache: dict[str, tuple[float, float]] = {}
        self._bot_manager = None
        self._boost_fold_q: float = 0.0
        self._boost_fold_ref: float = 0.0
        self._boost_fold_sma: float = 0.0
        self._boost_scrums: int = 0
        self._boost_folds: int = 0

        self._pending_wire_credits: float = 0.0
        self._pending_wire_ledger: list[dict] = []

        self._pending_stack_buy_usd: float = 0.0

        self._target_grow_last_side: Optional[str] = None

        self._fold_cycle_cap_consumed: float = 0.0

        self._fold_preview_unreadable_refs: int = 0

        self._fold_preview_unreadable_units: int = 0

        self._below_min_scrum_log_ts: float = 0.0
        self._below_min_fold_log_ts: float = 0.0

        self._cb_hard_tripped: bool = False
        self._cb_hard_tripped_at: float = 0.0
        self._cb_hard_trip_pct: float = 0.0
        self._cb_soft_active_side: Optional[str] = None
        self._cb_soft_cooldown_remaining: int = 0
        self._cb_soft_tripped_at: float = 0.0
        self._cb_soft_trip_pct: float = 0.0
        self._cb_last_candle_ts: float = 0.0

    def get_swos_inputs(self) -> Optional[dict]:
        """Return the input dict for ``smart_wire.compute_safe_outflow_pct``.

        Returns:
          ``None`` when critical fields are missing.

        """
        try:
            _price = float(getattr(self.stats, "current_price", 0.0) or 0.0)
            _target = float(getattr(self, "_target_balance", 0.0) or 0.0)
            _interval = float(
                getattr(self.config, "scrumming_interval_pct", 1.0) or 1.0
            )
            _growth = float(getattr(self.config, "max_target_growth_pct", 1.0) or 0.0)
            _cash = float(getattr(self.stats, "cash_balance_usd", 0.0) or 0.0)
            _retained = float(getattr(self, "_retained_this_cycle_usd", 0.0) or 0.0)
            if _price <= 0 or _target <= 0:
                return None
            _band_upper = _price * (1.0 + _interval / 100.0)
            _band_lower = _price * (1.0 - _interval / 100.0)
            _next_fold_ammo = _target * (_interval / 100.0)
            return {
                "target_balance_usd": _target,
                "current_price": _price,
                "band_lower": _band_lower,
                "band_upper": _band_upper,
                "next_fold_ammo_usd": _next_fold_ammo,
                "current_cash_usd": _cash,
                "compound_growth_pct": _growth,
                "retained_this_cycle_usd": _retained,
            }
        except Exception as _swos_exc:  # noqa: BLE001
            logger.debug("Bot %s get_swos_inputs raised: %s", self.bot_id, _swos_exc)
            return None

    def note_scrum_retention_usd(self, retained_usd: float) -> None:
        """Increment the per-cycle retained counter used by SWOS."""
        try:
            self._retained_this_cycle_usd += max(0.0, float(retained_usd))
        except Exception as _sup:  # noqa: BLE001
            logger.debug(
                "suppressed in %s: %s: %s",
                "note_scrum_retention_usd",
                type(_sup).__name__,
                _sup,
            )

    def reset_swos_cycle(self) -> None:
        """Reset ``_retained_this_cycle_usd`` to 0, called at Fold execution."""
        self._retained_this_cycle_usd = 0.0

    def set_market_pairs_scout(self, scout) -> None:
        """Attach the process-wide MarketPairsScout; a falsy ``scout`` is a no-op."""
        self._market_pairs_scout = scout

    def get_target_asset_pairs(self):
        """Return PairSnapshots for this bot's target asset, empty when no scout."""
        _scout = getattr(self, "_market_pairs_scout", None)
        if _scout is None:
            return []
        try:
            _asset = str(getattr(self.config, "target_asset", "") or "").upper()
            _eid = str(getattr(self.config, "exchange_id", "") or "")
            if not _asset:
                return []
            return _scout.pairs_for(_asset, exchange_id=(_eid or None))
        except Exception as _pairs_exc:  # noqa: BLE001
            logger.debug("Bot %s scout query raised: %s", self.bot_id, _pairs_exc)
            return []

    async def _get_cached_exchange_balance(
        self, asset: str, max_age_s: float = 60.0
    ) -> Optional[float]:
        """Return this bot's exchange free-balance for ``asset``."""
        _asset = (asset or "").upper()
        if not _asset:
            return None
        _now = time.time()
        _cached = self._exchange_balance_cache.get(_asset)
        if _cached is not None:
            _val, _ts = _cached
            if (_now - _ts) <= max_age_s:
                return _val
        try:
            _bal = await self._get_balance(_asset)
            _free = float(getattr(_bal, "free", 0) or 0)
            self._exchange_balance_cache[_asset] = (_free, _now)
            return _free
        except Exception as _bal_exc:  # noqa: BLE001
            logger.debug(
                "Bot %s balance fetch for %s (CRR ensure) raised %s — "
                "skipping over-commit check this cycle.",
                self.bot_id,
                _asset,
                _bal_exc,
            )
            return None

    def set_bot_manager(self, manager) -> None:
        """Attach the BotManager for cross-bot registry coordination."""
        self._bot_manager = manager

    def _sum_sibling_base_currency_claims(self) -> Optional[float]:
        """What the other bots on this exchange have claimed of this bot's
        base-currency pool, asked of the attached BotManager.

        Only the manager holds the fleet, so the figure cannot be computed here.
        None when no manager is attached or the manager could not read every
        sibling; the initial-entry phase refuses on None rather than reading a
        short total as money that is free.
        """
        reader = getattr(
            getattr(self, "_bot_manager", None),
            "sum_sibling_base_currency_claims",
            None,
        )
        if not callable(reader):
            logger.warning(
                "Bot %s has no fleet to ask what the other bots have claimed "
                "of the %s pool, so its free balance cannot be trusted",
                self.bot_id,
                self.config.base_currency,
            )
            return None
        try:
            claimed = reader(
                self.bot_id,
                self.config.exchange_id,
                self.config.base_currency,
            )
        except Exception as _claims_exc:
            logger.warning(
                "Bot %s could not read sibling claims on the %s pool: %s: %s",
                self.bot_id,
                self.config.base_currency,
                type(_claims_exc).__name__,
                _claims_exc,
            )
            return None
        return None if claimed is None else float(claimed)

    def set_target_balance_live(self, new_target: float) -> dict:
        """Apply an operator-initiated Target Balance change, comparing ``new_target``
        against ``_anchor_target_balance`` rather than the grown target.

        Returns:
          {"applied", "old_target", "old_anchor", "new_target",
           "new_anchor", "delta_usd"}

        """
        try:
            nt = float(new_target)
        except (TypeError, ValueError):
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"TARGET BALANCE CHANGE REFUSED: invalid "
                        f"value {new_target!r} — could not coerce "
                        f"to float. Target unchanged at "
                        f"${self._target_balance:.2f}."
                    ),
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "set_target_balance_live",
                    type(_sup).__name__,
                    _sup,
                )
            return {"applied": False, "reason": f"invalid value: {new_target!r}"}
        if nt <= 0:
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"TARGET BALANCE CHANGE REFUSED: must be "
                        f"> 0, got {nt}. Target unchanged at "
                        f"${self._target_balance:.2f}."
                    ),
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "set_target_balance_live",
                    type(_sup).__name__,
                    _sup,
                )
            return {"applied": False, "reason": f"target must be > 0, got {nt}"}

        old_t = float(self._target_balance)
        old_a = float(getattr(self, "_anchor_target_balance", old_t))

        accrued = max(0.0, old_t - old_a)
        if nt > old_a and accrued > 1e-9:
            # Top-up: fresh anchor plus the growth accrued so far.
            self._anchor_target_balance = nt
            self._target_balance = nt + accrued
        else:
            # At or below anchor: target and anchor move together.
            self._target_balance = nt
            self._anchor_target_balance = nt
        try:
            self.config.target_balance = nt
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_set_target_balance",
                type(_sup).__name__,
                _sup,
            )

        try:
            _px = float(getattr(self.stats, "current_price", 0) or 0)
        except Exception:
            _px = 0.0
        pos_val = float(self._current_holdings) * _px if _px > 0 else 0.0
        new_t = float(self._target_balance)
        new_a = float(self._anchor_target_balance)
        delta = new_t - pos_val

        preserved_note = ""
        if new_t != nt:
            preserved_note = (
                f" [top-up preserved ${new_t - new_a:.4f} "
                f"accrued growth: target=${new_t:.4f}]"
            )

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"TARGET BALANCE LIVE UPDATE: ${old_t:.2f} -> "
                f"${new_t:.2f} (anchor ${old_a:.2f} -> "
                f"${new_a:.2f}). Position ${pos_val:.2f} -> "
                f"delta ${delta:+.2f}.{preserved_note} "
                f"Ceiling guards recompute on next tick."
            ),
        )
        logger.info(
            "Bot %s target_balance live-update: target %.2f -> %.2f, "
            "anchor %.2f -> %.2f",
            self.bot_id,
            old_t,
            new_t,
            old_a,
            new_a,
        )

        return {
            "applied": True,
            "old_target": old_t,
            "old_anchor": old_a,
            "new_target": new_t,
            "new_anchor": new_a,
            "delta_usd": delta,
            "preserved_growth": max(0.0, new_t - new_a),
        }

    @property
    def cycle_growth_cap_usd(self) -> float:
        """The per-cycle Growth Rate Cap in USD, based on the cycle-open target.

        Returns:
          The whole cycle's cap in USD, not the remaining headroom. The base is
          ``_target_balance`` minus ``_fold_cycle_cap_consumed``, so the cap cannot
          grow as the cycle consumes it. Unreadable input returns 0.0.

        """
        try:
            _pct = float(getattr(self.config, "max_target_growth_pct", 1.0) or 0.0)
            _target = float(getattr(self, "_target_balance", 0.0) or 0.0)
            _consumed = float(getattr(self, "_fold_cycle_cap_consumed", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0
        if not (
            math.isfinite(_pct) and math.isfinite(_target) and math.isfinite(_consumed)
        ):
            return 0.0
        if _pct <= 0.0:
            return 0.0
        # Never negative: consumption can exceed the target until the next reset.
        return cycle_growth_cap_usd(_target, _consumed, _pct)

    def _apply_fold_target_growth(self, accum_profit: float, source: str) -> float:
        """Drain fold surplus into ``_target_balance``, bounded by the per-cycle cap.

        Args:
          accum_profit: pre-quote-conversion USD-equivalent profit from the
                        caller's tranche match.
          source: short tag for the TARGET GROWN log line ("auto",
                  "MANUAL_FOLD", "CARTRIDGE_FOLD").

        Returns:
          _growth_applied (USD). 0.0 if profit_folding_active is off,
          surplus is non-positive, or cap fully consumed.

        """
        if not self.config.profit_folding_active:
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"[COMPOUND SKIPPED] ({source}): "
                        f"profit_folding_active=False — the "
                        f"compound-growth feature is off for "
                        f"this bot. No target bump."
                    ),
                )
            except Exception as _sup:  # noqa: BLE001
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_apply_fold_target_growth",
                    type(_sup).__name__,
                    _sup,
                )
            return 0.0
        _quote = float(self._quote_to_usd or 1.0)
        _new_surplus_usd = max(0.0, float(accum_profit) * _quote)
        if (
            _new_surplus_usd <= 1e-9
            and float(getattr(self, "_standing_surplus_usd", 0.0) or 0.0) <= 1e-9
        ):
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"[COMPOUND SKIPPED] ({source}): "
                        f"accum_profit ${float(accum_profit):.4f} × "
                        f"quote {_quote:.4f} = ${_new_surplus_usd:.4f} "
                        f"— fold produced no surplus, and no standing "
                        f"surplus is parked. No target bump. "
                        f"(This is expected when a fold buys back at "
                        f"cost basis or when scrum→fold spread is "
                        f"eaten by fees.)"
                    ),
                )
            except Exception as _sup:  # noqa: BLE001
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_apply_fold_target_growth",
                    type(_sup).__name__,
                    _sup,
                )
            return 0.0
        # The cap base is the cycle-open target, not the frozen anchor.
        _cycle_cap_growth = self.cycle_growth_cap_usd
        _cap_remaining = max(0.0, _cycle_cap_growth - self._fold_cycle_cap_consumed)
        if _cap_remaining <= 1e-9:
            self._standing_surplus_usd += _new_surplus_usd
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"TARGET-GROW HELD ({source}): surplus "
                        f"${_new_surplus_usd:.4f} accrues to standing "
                        f"pool (now ${self._standing_surplus_usd:.4f}). "
                        f"Cap ${_cycle_cap_growth:.4f} fully consumed "
                        f"this cycle."
                    ),
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_apply_fold_target_growth",
                    type(_sup).__name__,
                    _sup,
                )
            try:
                self.stats.standing_surplus_usd = self._standing_surplus_usd
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_apply_fold_target_growth",
                    type(_sup).__name__,
                    _sup,
                )
            return 0.0
        _prior_pool = float(getattr(self, "_standing_surplus_usd", 0.0) or 0.0)
        _available = _new_surplus_usd + _prior_pool
        _growth_applied = min(_available, _cap_remaining)
        self._target_balance = float(self._target_balance) + _growth_applied
        self._fold_cycle_cap_consumed += _growth_applied
        self._target_grow_last_side = "lower"
        self._standing_surplus_usd = max(0.0, _available - _growth_applied)
        _drained = max(0.0, _prior_pool - self._standing_surplus_usd)
        _leftover = self._standing_surplus_usd
        self._fold_accumulator += _growth_applied
        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"TARGET GROWN ({source}): surplus "
                    f"${_new_surplus_usd:.4f}"
                    + (
                        f" + ${_prior_pool:.4f} standing " f"(${_drained:.4f} drained)"
                        if _prior_pool > 1e-9
                        else ""
                    )
                    + f", applied "
                    f"${_growth_applied:.4f} (cap remaining "
                    f"${_cap_remaining:.4f} of "
                    f"${_cycle_cap_growth:.4f}). New target "
                    f"${self._target_balance:.4f}, cycle consumed "
                    f"${self._fold_cycle_cap_consumed:.4f}. "
                    f"Standing pool now ${_leftover:.4f}."
                ),
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_apply_fold_target_growth",
                type(_sup).__name__,
                _sup,
            )
        try:
            self.stats.standing_surplus_usd = self._standing_surplus_usd
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_apply_fold_target_growth",
                type(_sup).__name__,
                _sup,
            )
        return _growth_applied

    def _preview_fold_growth(self, units: float, price: float) -> float:
        """What ``_apply_fold_target_growth`` would add for ``units`` at ``price``,
        moving no money.

        Returns:
          The growth in USD, capped off the cycle-open target and NOT the
          anchor, overshooting what the applier later books by
          ``1 / (1 - venue_fee)``.

        Args:
          units: base units the prospective buy would acquire.
          price: quote price used in place of the unknown fill price.

        """
        if not self.config.profit_folding_active:
            return 0.0
        if units <= 0 or price <= 0:
            return 0.0

        _readable: list[tuple[float, dict]] = []
        _unreadable_refs = 0
        for _t in self._fold_tranches or []:
            if not isinstance(_t, dict):
                continue
            _t_ref = float(_t.get("ref", 0.0) or 0.0)
            if not math.isfinite(_t_ref):
                _unreadable_refs += 1
                continue
            _readable.append((_t_ref, _t))
        _readable.sort(key=lambda pair: pair[0], reverse=True)

        self._fold_preview_unreadable_refs = _unreadable_refs
        _remaining = float(units)
        _accum = 0.0
        _unreadable_units = 0
        for _ref, t in _readable:
            if _remaining <= 1e-12:
                break
            _t_units = float(t.get("units", 0.0) or 0.0)
            if not math.isfinite(_t_units):
                _unreadable_units += 1
                continue
            take = min(_t_units, _remaining)
            if take <= 1e-12:
                continue
            if _ref > price:
                _accum += take * (_ref - price)
            _remaining -= take
        self._fold_preview_unreadable_units = _unreadable_units
        _quote = float(self._quote_to_usd or 1.0)
        _new_surplus_usd = max(0.0, _accum * _quote)
        # The same property the applier reads, so the two cannot disagree.
        _cycle_cap_growth = self.cycle_growth_cap_usd
        _cap_remaining = max(0.0, _cycle_cap_growth - self._fold_cycle_cap_consumed)
        if _cap_remaining <= 1e-9:
            return 0.0
        _available = _new_surplus_usd + float(
            getattr(self, "_standing_surplus_usd", 0.0) or 0.0
        )
        return min(_available, _cap_remaining)

    def set_visibility_live(self, new_visibility: str) -> dict:
        """Apply live visibility change (internal ↔ orderbook)."""
        nv = str(new_visibility or "").lower()
        if nv not in ("internal", "orderbook"):
            return {
                "applied": False,
                "reason": f"visibility must be 'internal' or "
                f"'orderbook'; got {new_visibility!r}",
            }
        old_inv = bool(self._invisible)
        self._invisible = nv == "internal"
        try:
            self.config.visibility = nv
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "set_visibility_live",
                type(_sup).__name__,
                _sup,
            )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"VISIBILITY LIVE UPDATE: {'INVISIBLE' if old_inv else 'ORDERBOOK'}"
                f" -> {'INVISIBLE' if self._invisible else 'ORDERBOOK'}. "
                f"Next order placement uses the new mode."
            ),
        )
        logger.info(
            "Bot %s visibility live: %s -> %s",
            self.bot_id,
            "internal" if old_inv else "orderbook",
            nv,
        )
        return {
            "applied": True,
            "old_invisible": old_inv,
            "new_invisible": self._invisible,
        }

    def set_aggressive_live(self, new_aggressive: bool) -> dict:
        """Apply a live aggressive-trading toggle, writing ``self._aggressive`` as
        well as ``config``.
        """
        nv = bool(new_aggressive)
        old = bool(self._aggressive)
        self._aggressive = nv
        try:
            self.config.aggressive_trading = nv
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "set_aggressive_live",
                type(_sup).__name__,
                _sup,
            )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(f"AGGRESSIVE TRADING LIVE UPDATE: {old} -> {nv}."),
        )
        logger.info("Bot %s aggressive_trading live: %s -> %s", self.bot_id, old, nv)
        return {"applied": True, "old": old, "new": nv}

    def set_hedge_rebalance_active_live(self, active: bool) -> dict:
        """Set hedge_rebalance_active on a running bot and arm _hedge_bal.

        Ticking on raises _hedge_bal to _hedge_balance_initial and never lowers
        it; unticking leaves _hedge_bal alone because the arm gate and the
        refill gate both read hedge_rebalance_active first.
        """
        if not isinstance(active, bool):
            return {
                "applied": False,
                "reason": (
                    f"hedge_rebalance_active must be true or false; " f"got {active!r}"
                ),
            }
        old = bool(self.config.hedge_rebalance_active)
        old_reserve = float(getattr(self, "_hedge_bal", 0.0) or 0.0)
        self.config.hedge_rebalance_active = active
        cap = float(self._hedge_balance_initial)
        if active and old_reserve < cap:
            self._hedge_bal = cap
        new_reserve = float(self._hedge_bal)
        if not active:
            note = (
                f"Reserve ${new_reserve:.2f} is kept and frozen; every hedge "
                f"buy and every refill is refused while the box is unticked."
            )
        elif cap <= 0.0:
            note = (
                "Hedge Balance is $0.00, so the reserve stays empty and no "
                "hedge buy can fire. Type a Hedge Balance above zero to arm it."
            )
        else:
            note = (
                f"Reserve armed at ${new_reserve:.2f} against a " f"${cap:.2f} ceiling."
            )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"HEDGE REBALANCE ACTIVE LIVE UPDATE: {old} -> {active}. "
                f"Reserve ${old_reserve:.2f} -> ${new_reserve:.2f}. {note}"
            ),
        )
        logger.info(
            "Bot %s hedge_rebalance_active live: %s -> %s (reserve %.2f -> %.2f)",
            self.bot_id,
            old,
            active,
            old_reserve,
            new_reserve,
        )
        return {
            "applied": True,
            "old": old,
            "new": active,
            "old_reserve": old_reserve,
            "reserve": new_reserve,
            "cap": cap,
        }

    def set_hedge_balance_live(self, new_hedge_balance: float) -> dict:
        """Apply a live hedge-balance cap change.

        Semantics:
          - _hedge_balance_initial is the operator-configured CAP on the
            hedge reserve; the bot refills up to this cap.
          - _hedge_bal is the CURRENT drainable reserve; it drains on
            hedge spends and refills on scrum skims up to the cap.
          - Raising or lowering the cap leaves _hedge_bal unchanged.
          - The cap is stored once, on config.hedge_balance;
            _hedge_balance_initial reads and writes that one field.

        """
        try:
            nv = float(new_hedge_balance)
        except (TypeError, ValueError):
            return {
                "applied": False,
                "reason": f"hedge_balance must be numeric; "
                f"got {new_hedge_balance!r}",
            }
        if nv < 0:
            return {"applied": False, "reason": f"hedge_balance must be ≥ 0; got {nv}"}
        old_cap = float(getattr(self, "_hedge_balance_initial", 0.0) or 0.0)
        old_reserve = float(getattr(self, "_hedge_bal", 0.0) or 0.0)
        try:
            self._hedge_balance_initial = nv
        except Exception as _wr:
            return {
                "applied": False,
                "reason": (
                    f"hedge_balance is not writable on this config: "
                    f"{type(_wr).__name__}: {_wr}"
                ),
            }
        new_cap = float(self._hedge_balance_initial)
        if not self.config.hedge_rebalance_active:
            note = (
                f"${nv:.2f} is stored, and the ceiling stays $0.00 until "
                f"Hedge Rebalance Active is ticked."
            )
        elif nv == 0.0:
            note = (
                f"A $0.00 Hedge Balance is an empty reserve that never "
                f"refills, not an off switch. Untick Hedge Rebalance Active "
                f"to turn the hedge off. Reserve ${old_reserve:.2f} stays "
                f"spendable until it drains."
            )
        else:
            note = (
                f"Current reserve ${old_reserve:.2f} unchanged (refill will "
                f"target the new cap)."
            )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"HEDGE BALANCE CAP LIVE UPDATE: ${old_cap:.2f} -> "
                f"${new_cap:.2f}. {note}"
            ),
        )
        logger.info(
            "Bot %s hedge_balance cap live: %.2f -> %.2f",
            self.bot_id,
            old_cap,
            new_cap,
        )
        return {
            "applied": True,
            "old_cap": old_cap,
            "new_cap": new_cap,
            "current_reserve": old_reserve,
        }

    _ARRIVAL_ATOMIC_TOL_USD: float = 1e-6

    @staticmethod
    def _positive_observed_quantity(
        value: Any, label: str
    ) -> tuple[float | None, str | None]:
        """Parse one observed money-path quantity, refusing anything that is not a
        strictly positive finite int or float.

        Returns:
          (number, None) when usable, (None, reason) when refused.

        """
        if type(value) is not int and type(value) is not float:
            return None, (
                f"{label} must be exactly an int or a float, "
                f"not a {type(value).__name__}; got {value!r}"
            )
        try:
            x = float(value)
        except (TypeError, ValueError, OverflowError):
            return None, f"{label} must be numeric; got {value!r}"
        if not math.isfinite(x):
            return None, f"{label} must be finite; got {x!r}"
        if x <= 0:
            return None, f"{label} must be > 0; got {x}"
        return x, None

    @staticmethod
    def _finite_state_number(value: Any, label: str) -> tuple[float | None, str | None]:
        """Coerce one piece of the bot's own state, checking numeric-and-finite only
        so that 0.0 is accepted.

        Returns:
          (number, None) when usable, (None, reason) when refused.

        """
        if type(value) is not int and type(value) is not float:
            return None, (
                f"{label} must be exactly an int or a float, "
                f"not a {type(value).__name__}; got {value!r}"
            )
        try:
            x = float(value)
        except (TypeError, ValueError, OverflowError):
            return None, f"{label} is not numeric; got {value!r}"
        if not math.isfinite(x):
            return None, f"{label} must be finite; got {x!r}"
        return x, None

    @staticmethod
    def _sum_lot_units(lots: Any) -> tuple[float | None, str | None]:
        """Total units the lot ledger holds, refusing instead of raising.

        Returns:
          (total_units, None) when readable, (None, reason) when not.

        """
        total = 0.0
        for _index, _lot in enumerate(lots):
            if type(_lot) is not dict:  # noqa: E721
                return None, (
                    f"_main_lots[{_index}] must be a lot dict; "
                    f"got a {type(_lot).__name__}"
                )
            if "units" not in _lot:
                return None, (f"_main_lots[{_index}] has no usable " f"'units' entry")
            try:
                _units = float(_lot["units"])
            except Exception:  # noqa: BLE001
                return None, (f"_main_lots[{_index}] has no usable " f"'units' entry")
            if not math.isfinite(_units):
                return None, (
                    f"_main_lots[{_index}]['units'] must be " f"finite; got {_units!r}"
                )
            total += _units
        return total, None

    def apply_extractor_tranche_return(
        self, usd_value: Any, source: str, base_units: Any, ref: str = ""
    ) -> dict:
        """Book base currency returned by a child Extractor Tranche, lifting target
        and anchor atomically.

        Args:
          usd_value: USD that landed, already net of every fee the child paid.
          source: short tag naming the child, for the log line.
          base_units: base units that landed alongside it.
          ref: optional reference recorded on the arrival lot.

        Returns:
          {"applied": bool, ...}. On refusal nothing is mutated. The arrival
          adds no delta of its own and no growth cap applies.

        """
        u, _why = self._positive_observed_quantity(usd_value, "usd_value")
        if u is None:
            return {"applied": False, "reason": _why or "usd_value refused"}
        b, _why = self._positive_observed_quantity(base_units, "base_units")
        if b is None:
            return {"applied": False, "reason": _why or "base_units refused"}

        try:
            src = str(source or "?")
        except Exception as _src_exc:  # noqa: BLE001
            return {
                "applied": False,
                "reason": (
                    f"source is not renderable: "
                    f"{type(_src_exc).__name__}: {_src_exc}"
                ),
            }

        try:
            _bot_id = str(getattr(self, "bot_id", "?"))
        except Exception:  # noqa: BLE001
            _bot_id = "?"

        try:

            qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
        except (TypeError, ValueError, OverflowError):
            return {
                "applied": False,
                "reason": "quote_to_usd is not numeric; cannot price " "the arrival",
            }
        if not math.isfinite(qrate) or qrate <= 0:
            return {
                "applied": False,
                "reason": f"quote_to_usd must be finite and > 0; " f"got {qrate!r}",
            }

        lots = getattr(self, "_main_lots", None)
        if type(lots) is not list:  # noqa: E721
            return {
                "applied": False,
                "reason": (
                    f"_main_lots must be exactly a list, not a "
                    f"{type(lots).__name__}; refusing to book "
                    f"an unattributable arrival"
                ),
            }

        _price_divisor = b * qrate
        if not math.isfinite(_price_divisor) or _price_divisor <= 0.0:
            return {
                "applied": False,
                "reason": (
                    f"base_units x quote_to_usd is not a usable "
                    f"divisor; {b!r} x {qrate!r} = "
                    f"{_price_divisor!r}"
                ),
            }
        arrival_price = u / _price_divisor
        if not math.isfinite(arrival_price) or arrival_price <= 0:
            return {
                "applied": False,
                "reason": f"arrival price not usable; got " f"{arrival_price!r}",
            }

        _t_before, _why = self._finite_state_number(
            getattr(self, "_target_balance", None), "_target_balance"
        )
        if _t_before is None:
            return {"applied": False, "reason": _why or "_target_balance refused"}
        _h_before, _why = self._finite_state_number(
            getattr(self, "_current_holdings", None), "_current_holdings"
        )
        if _h_before is None:
            return {"applied": False, "reason": _why or "_current_holdings refused"}
        _a_before, _why = self._finite_state_number(
            getattr(self, "_anchor_target_balance", None), "_anchor_target_balance"
        )
        if _a_before is None:
            return {
                "applied": False,
                "reason": _why or "_anchor_target_balance refused",
            }

        _tol, _why = self._finite_state_number(
            getattr(self, "_ARRIVAL_ATOMIC_TOL_USD", None), "_ARRIVAL_ATOMIC_TOL_USD"
        )
        if _tol is None or _tol < 0.0:
            return {
                "applied": False,
                "reason": (
                    _why
                    or f"_ARRIVAL_ATOMIC_TOL_USD must be "
                    f"finite and >= 0; got {_tol!r}"
                ),
            }

        _units_before, _why = self._sum_lot_units(lots)
        if _units_before is None:
            return {"applied": False, "reason": _why or "_main_lots is unreadable"}
        _lots_before = len(lots)

        _h_after = _h_before + b
        _t_after = _t_before + u
        _a_after = _a_before + u
        for _field, _value in (
            ("_current_holdings", _h_after),
            ("_target_balance", _t_after),
            ("_anchor_target_balance", _a_after),
        ):
            if not math.isfinite(_value):
                return {
                    "applied": False,
                    "reason": (
                        f"{_field} would become {_value!r}; "
                        f"refusing to write a non-finite "
                        f"balance"
                    ),
                }
        _arrival_lot = {
            "units": b,
            "initial_buy_price": arrival_price,
            "operator_initiated": False,
        }

        # ATOMIC ARRIVAL: four writes, nothing suspends between them.
        lots.append(_arrival_lot)
        self._current_holdings = _h_after
        self._target_balance = _t_after
        self._anchor_target_balance = _a_after
        # END ATOMIC ARRIVAL

        try:
            self.config.target_balance = self._target_balance
        except Exception as _mirror_exc:
            logger.debug(
                "Bot %s could not mirror target_balance to config: %s",
                _bot_id,
                _mirror_exc,
            )

        _units_after, _read_why = self._sum_lot_units(lots)
        _ledger_readable = _units_after is not None
        _units_seen = _units_before if _units_after is None else _units_after

        _h_seen, _h_why = self._finite_state_number(
            getattr(self, "_current_holdings", None), "_current_holdings"
        )
        _t_seen, _t_why = self._finite_state_number(
            getattr(self, "_target_balance", None), "_target_balance"
        )
        _a_seen, _a_why = self._finite_state_number(
            getattr(self, "_anchor_target_balance", None), "_anchor_target_balance"
        )
        _state_readable = None not in (_h_seen, _t_seen, _a_seen)
        _state_read_why = _h_why or _t_why or _a_why
        _h_seen = _h_before if _h_seen is None else _h_seen
        _t_seen = _t_before if _t_seen is None else _t_seen
        _a_seen = _a_before if _a_seen is None else _a_seen

        _lot_units_booked = _units_seen - _units_before
        _lot_usd_booked = _lot_units_booked * arrival_price * qrate

        _holdings_usd_added = (_h_seen - _h_before) * arrival_price * qrate
        _target_usd_added = _t_seen - _t_before
        _anchor_usd_added = _a_seen - _a_before

        _lot_gap_usd = _lot_usd_booked - u
        _holdings_gap_usd = _holdings_usd_added - u
        _target_gap_usd = _target_usd_added - u
        _anchor_gap_usd = _anchor_usd_added - u

        _atomic_ok = bool(
            _ledger_readable
            and _state_readable
            and abs(_lot_gap_usd) <= _tol
            and abs(_holdings_gap_usd) <= _tol
            and abs(_target_gap_usd) <= _tol
            and abs(_anchor_gap_usd) <= _tol
        )

        _delta_shift_usd = _holdings_usd_added - _target_usd_added
        _ledger_gap_units = (_units_seen - _h_seen) - (_units_before - _h_before)
        _ledger_gap_usd = _ledger_gap_units * arrival_price * qrate

        _measured = (
            f"lot {_lot_units_booked:.10g} of {b:.10g} units, "
            f"holdings ${_holdings_usd_added:+.6f}, target "
            f"${_target_usd_added:+.6f}, anchor "
            f"${_anchor_usd_added:+.6f}, each against an arrival "
            f"of ${u:.6f}; ledger gap ${_ledger_gap_usd:+.6f}; "
            f"tol ${_tol:g}"
        )
        if not _ledger_readable:
            _measured = f"{_measured}; ledger unreadable: {_read_why}"
        if not _state_readable:
            _measured = f"{_measured}; state unreadable: {_state_read_why}"
        _verdict = (
            f"CHECKED [{_measured}] — both halves booked "
            f"together, so the arrival is neither scrummed nor "
            f"chased"
            if _atomic_ok
            else f"ARRIVAL NOT ATOMIC [{_measured}]"
        )
        try:
            self._bus.emit(
                "bot.log",
                bot_id=_bot_id,
                message=(
                    f"EXTRACTOR TRANCHE CONTAINED: +${u:.4f} from "
                    f"{src} ({b:.10g} "
                    f"{getattr(self.config, 'base_currency', '')} "
                    f"@ ${arrival_price:.8f}). Target ${_t_before:.2f} "
                    f"-> ${_t_seen:.2f}, uncapped. "
                    f"Holdings {_h_before:.8f} -> "
                    f"{_h_seen:.8f}. Delta shift "
                    f"${_delta_shift_usd:+.6f} — {_verdict}. "
                    f"ref={ref}"
                ),
            )
        except Exception as _log_exc:
            logger.debug("Bot %s containment log line failed: %s", _bot_id, _log_exc)

        try:
            from src.core.signal_contract import emit as _et_emit

            # The target moved by exactly the arrival.
            _et_emit(
                "extractor.02.001.postcondition.tranche_contained",
                actual=_target_usd_added,
                expected=u,
                context={
                    "bot_id": _bot_id,
                    "source": src,
                    "base_units": b,
                    "target_before": _t_before,
                    "target_after": _t_seen,
                    "ref": ref,
                },
            )
            # ``ok`` carries the four per-write terms, so a missing write fails it.
            _et_emit(
                "extractor.02.002.invariant.arrival_atomic",
                actual=_delta_shift_usd,
                expected=0.0,
                ok=_atomic_ok,
                context={
                    "bot_id": _bot_id,
                    "source": src,
                    "lot_units_booked": _lot_units_booked,
                    "lot_units_expected": b,
                    "ledger_units_before": _units_before,
                    "ledger_units_after": _units_seen,
                    "ledger_readable": _ledger_readable,
                    "ledger_read_error": _read_why,
                    "state_readable": _state_readable,
                    "state_read_error": _state_read_why,
                    "arrival_usd": u,
                    "lot_gap_usd": _lot_gap_usd,
                    "holdings_gap_usd": _holdings_gap_usd,
                    "target_gap_usd": _target_gap_usd,
                    "anchor_gap_usd": _anchor_gap_usd,
                    "ledger_gap_usd": _ledger_gap_usd,
                    "tolerance_usd": _tol,
                    "lot_usd_booked": _lot_usd_booked,
                    "holdings_usd_added": _holdings_usd_added,
                    "target_usd_added": _target_usd_added,
                    "anchor_usd_added": _anchor_usd_added,
                    "holdings_before": _h_before,
                    "holdings_after": _h_seen,
                    "arrival_price": arrival_price,
                    "quote_to_usd": qrate,
                    "ref": ref,
                },
            )
        except Exception as _sup:  # noqa: BLE001,S110
            logger.debug(
                "suppressed in %s: %s: %s",
                "apply_extractor_tranche_return",
                type(_sup).__name__,
                _sup,
            )

        # Reported balances are read back from the object, not the values written.
        return {
            "applied": True,
            "mode": "contained",
            "contained_usd": u,
            "base_units": b,
            "arrival_price": arrival_price,
            "new_target_balance": _t_seen,
            "new_anchor_target_balance": _a_seen,
            "new_holdings": _h_seen,
            "main_lots_added": len(lots) - _lots_before,
            "lot_units_booked": _lot_units_booked,
            "lot_gap_usd": _lot_gap_usd,
            "holdings_gap_usd": _holdings_gap_usd,
            "target_gap_usd": _target_gap_usd,
            "anchor_gap_usd": _anchor_gap_usd,
            "ledger_gap_usd": _ledger_gap_usd,
            "ledger_readable": _ledger_readable,
            "state_readable": _state_readable,
            "delta_shift_usd": _delta_shift_usd,
            "atomic": _atomic_ok,
        }

    async def manual_fire_tranche(self, tranche_index: int) -> dict:
        """Operator-initiated fold-back of a specific tranche.

        Args:
          tranche_index: 0-based index into self._fold_tranches.

        Returns:
          {"applied": True|False, "reason"?: str, ...}

        """
        if not isinstance(tranche_index, int):
            try:
                tranche_index = int(tranche_index)
            except (TypeError, ValueError):
                return {
                    "applied": False,
                    "reason": f"tranche_index must be int; got {tranche_index!r}",
                }
        if not (0 <= tranche_index < len(self._fold_tranches)):
            return {
                "applied": False,
                "reason": (
                    f"invalid tranche_index {tranche_index} "
                    f"(have {len(self._fold_tranches)} tranches)"
                ),
            }

        tranche = self._fold_tranches[tranche_index]
        cost = float(tranche.get("usd", 0) or 0)
        ibp = float(tranche.get("initial_buy_price", tranche.get("ref", 0)) or 0)
        if cost <= 0:
            return {
                "applied": False,
                "reason": f"tranche #{tranche_index+1} has zero USD",
            }

        try:
            ticker = await self._get_ticker(self.config.symbol)
        except Exception as exc:
            return {
                "applied": False,
                "reason": f"ticker fetch failed: {type(exc).__name__}: {exc}",
            }
        price = getattr(ticker, "last", 0) or 0
        if not price or price <= 0:
            return {"applied": False, "reason": "no valid price"}

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"MANUAL TRANCHE FIRE: operator requested fold-back "
                f"of tranche #{tranche_index+1} "
                f"(usd ${cost:.4f}, ref ${tranche.get('ref', 0):.8f}, "
                f"IBP ${ibp:.8f}) at current "
                f"${price:.8f}. Bypasses TA/OTD/Target-Delta gates; "
                f"Position Ceiling + fail-closed buy safety still apply."
            ),
        )

        class _ManualTrancheSummary:
            consensus_direction = "manual"
            consensus_confidence = 1.0

            def __repr__(self):
                return "<ManualTrancheFireSummary operator_initiated=True>"

        summary = _ManualTrancheSummary()

        fill_price = await self._execute_buy(
            cost=cost,
            price=price,
            summary=summary,
            trace_context={
                "path": "manual_tranche_fire",
                "tranche_index": tranche_index,
                "tranche_ref": str(tranche.get("ref", "")),
                "tranche_ibp": str(ibp),
            },
        )
        if fill_price is None or fill_price <= 0:
            return {
                "applied": False,
                "reason": (
                    "_execute_buy refused or failed (Smart "
                    "Ceiling / fail-closed buy safety / P0b guard, or "
                    "exchange rejection); tranche unchanged"
                ),
            }

        rebought_units = cost / float(fill_price)

        _mf_ref = float(tranche.get("ref", 0.0) or 0.0)
        _mf_profit = (
            float(cost) * (1.0 - float(fill_price) / _mf_ref) if _mf_ref > 0 else 0.0
        )
        try:
            _mf_growth = self._apply_fold_target_growth(
                _mf_profit, source="MANUAL_TRANCHE_FOLD"
            )
        except Exception as _mf_exc:  # noqa: BLE001
            _mf_growth = 0.0
            logger.error(
                "manual tranche fold: target-growth booking FAILED after a "
                "filled buy on %s (%s); the fill stands, the growth was "
                "not applied",
                self.bot_id,
                _mf_exc,
            )
        self._main_lots.append(
            {
                "units": rebought_units,
                "initial_buy_price": ibp,
                "operator_initiated": True,
            }
        )
        _removed_ok = False
        try:
            self._fold_tranches.remove(tranche)
            _removed_ok = True
        except ValueError:
            logger.warning(
                "Bot %s manual_fire_tranche: tranche disappeared "
                "between dispatch and post-fill; lots updated, "
                "tranche cleanup skipped; closed-counter NOT bumped.",
                self.bot_id,
            )
        self._fold_queue_usd = sum(
            float(t.get("usd", 0) or 0) for t in self._fold_tranches
        )
        if _removed_ok:
            try:
                self._tranches_closed_lifetime = (
                    int(getattr(self, "_tranches_closed_lifetime", 0) or 0) + 1
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "manual_fire_tranche",
                    type(_sup).__name__,
                    _sup,
                )

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"MANUAL TRANCHE FIRE COMPLETE: tranche "
                f"#{tranche_index+1} consumed. "
                f"${cost:.4f} → {rebought_units:.6f} units @ "
                f"${fill_price:.8f}, returned to main_lots with "
                f"IBP ${ibp:.8f}. Fold queue now "
                f"${self._fold_queue_usd:.4f} across "
                f"{len(self._fold_tranches)} tranche(s)."
            ),
        )
        try:
            self._bus.emit(
                "pnl.event",
                bot_id=self.bot_id,
                data={
                    "kind": "FOLD",
                    "asset": self.config.target_asset,
                    "symbol": self.config.symbol,
                    "units_rebought": float(rebought_units),
                    "fill_price": float(fill_price),
                    "usd_spent": float(cost) * float(self._quote_to_usd or 1.0),
                    "operator_initiated": True,
                    "manual_kind": "MANUAL_TRANCHE_FOLD",
                    "tranche_ibp": float(ibp),
                    "accum_profit": float(_mf_profit),
                    "growth_applied": float(_mf_growth),
                },
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "manual_fire_tranche",
                type(_sup).__name__,
                _sup,
            )
        self._bus.emit(
            "trade.filled",
            bot_id=self.bot_id,
            data={
                "type": "MANUAL_TRANCHE_FOLD",
                "side": "BUY",
                "amount": rebought_units,
                "price": fill_price,
                "usd": cost,
                "operator_initiated": True,
                "accum_profit": float(_mf_profit),
                "growth_applied": float(_mf_growth),
                **self._fill_fee_fields(fill_price),
            },
        )
        self._emit_voting_panel_snapshot_at_fire(
            side="BUY", trade_action="MANUAL_TRANCHE_FOLD"
        )
        self._emit_gate_decision_at_fire(side="BUY", trade_action="MANUAL_TRANCHE_FOLD")
        return {
            "applied": True,
            "tranche_index": tranche_index,
            "cost_usd": cost,
            "fill_price": float(fill_price),
            "units_returned": rebought_units,
            "remaining_tranches": len(self._fold_tranches),
        }

    def update_phantom_config(
        self,
        enable_phantoms: Optional[bool] = None,
        phantom_timeframes: Optional[list[str]] = None,
        lock_candle_count: Optional[int] = None,
    ) -> dict:
        """Live-update phantom configuration.

        Semantics:
          - enable_phantoms: toggles ``_phantoms_enabled``; turning it OFF
            leaves running phantoms alive and only stops new ones spawning.
          - phantom_timeframes: used by the next phantom create pass;
            already started phantoms keep running.
          - lock_candle_count: applied to the TimeframeCoordinator
            immediately.

        Returns:
          A dict of what was applied plus any caveats.

        """
        applied: dict = {}
        caveats: list[str] = []

        if enable_phantoms is not None and enable_phantoms != self._phantoms_enabled:
            was_enabled = self._phantoms_enabled
            self._phantoms_enabled = bool(enable_phantoms)
            applied["enable_phantoms"] = self._phantoms_enabled
            if was_enabled and not self._phantoms_enabled and self._phantoms_started:
                caveats.append(
                    "Phantoms already started; disabled flag prevents "
                    "new phantoms but existing ones continue until bot "
                    "restart."
                )
            if (
                not was_enabled
                and self._phantoms_enabled
                and not self._phantoms_started
            ):
                caveats.append("Phantoms will start on next tick.")

        if phantom_timeframes is not None:
            from ..exchange.timeframes import available_timeframes

            _offered = set(available_timeframes(self.config.exchange_id))
            filtered = [tf for tf in phantom_timeframes if tf in _offered]
            dropped = [tf for tf in phantom_timeframes if tf not in _offered]
            if list(filtered) != list(self._phantom_timeframes):
                self._phantom_timeframes = list(filtered)
                self._phantom_tf_dropped = list(dropped)
                applied["phantom_timeframes"] = list(filtered)
                if self._phantoms_started:
                    caveats.append(
                        "TF set updated; already-started phantoms keep "
                        "their original TFs until bot restart."
                    )
                if dropped:
                    caveats.append(
                        f"Dropped unsupported TFs for "
                        f"{self.config.exchange_id}: {dropped}."
                    )

        if lock_candle_count is not None and self._coordinator is not None:
            new_lc = max(1, int(lock_candle_count))
            if new_lc != getattr(self._coordinator, "lock_candle_count", None):
                self._coordinator.lock_candle_count = new_lc
                applied["lock_candle_count"] = new_lc

        return {"applied": applied, "caveats": caveats}

    @property
    def tick_interval(self) -> float:
        return 5.0

    @property
    def coordinator(self) -> TimeframeCoordinator:
        return self._coordinator

    @property
    def last_voting_summary(self) -> Optional[VotingSummary]:
        return self._last_summary

    @property
    def scrum_target_mode(self) -> str:
        return self._scrum_target_mode

    async def _get_ticker(self, symbol: Optional[str] = None):
        """Fetch a ticker through ``_data_pool``, else direct from the exchange."""
        if symbol is None:
            symbol = self.config.symbol
        if self._data_pool is not None:
            try:
                return await self._data_pool.get_or_fetch_ticker(
                    self.exchange, self.config.exchange_id, symbol
                )
            except Exception:
                raise
        return await self.exchange.get_ticker(symbol)

    async def _get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
    ) -> list:
        """Fetch OHLCV through the shared MarketDataPool when wired,
        else fall back to a direct exchange call.
        """
        if self._data_pool is not None:
            try:
                return await self._data_pool.get_or_fetch_ohlcv(
                    self.exchange,
                    self.config.exchange_id,
                    symbol,
                    timeframe,
                    limit=limit,
                )
            except Exception:
                raise
        return await self.exchange.get_ohlcv(symbol, timeframe, limit=limit)

    async def _get_balance(self, currency: str):
        """Fetch a balance through ``_data_pool``, else a direct exchange call."""
        if self._data_pool is not None:
            try:
                return await self._data_pool.get_or_fetch_balance(
                    self.exchange, self.config.exchange_id, currency
                )
            except Exception:
                raise
        return await self.exchange.get_balance(currency)

    def _invalidate_balance(
        self,
        currency: Optional[str] = None,
    ) -> None:
        """Force the next ``_get_balance`` for this exchange and currency."""
        if self._data_pool is None:
            return
        try:
            self._data_pool.invalidate_balance(self.config.exchange_id, currency)
        except Exception as _inv_exc:  # noqa: BLE001
            logger.debug("Bot %s balance invalidate failed: %s", self.bot_id, _inv_exc)

    async def _refresh_quote_to_usd(self) -> Optional[float]:
        """Refresh the cached quote→USD rate, at most once per 30s and 1.0 for
        USD-stable quotes.

        Returns:
          The resolved rate, or ``None`` when the fetch failed and no cached
          rate exists. On failure the cached rate is preserved and one
          bot.log warning is emitted.

        """
        quote = self.config.symbol.split("/")[-1].upper()
        if is_usd_stable_quote(quote):
            self._quote_to_usd = 1.0
            return 1.0
        now = time.time()
        if (now - self._quote_to_usd_last_fetch) < 30.0 and self._quote_to_usd > 0:
            return self._quote_to_usd
        try:
            usd_ticker = await self._get_ticker(f"{quote}/USD")
            rate = float(getattr(usd_ticker, "last", 0) or 0)
            if rate > 0:
                self._quote_to_usd = rate
                self._quote_to_usd_last_fetch = now
                self._quote_to_usd_warned = False
                return rate
        except Exception as exc:
            if not self._quote_to_usd_warned:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"QUOTE→USD: failed to fetch {quote}/USD rate "
                        f"({type(exc).__name__}: {exc}). Falling back to "
                        f"cached rate {self._quote_to_usd:.4f}. Target "
                        f"Balance evaluation may be off until a successful "
                        f"refresh."
                    ),
                )
                self._quote_to_usd_warned = True
        return self._quote_to_usd if self._quote_to_usd > 0 else None

    def _to_usd(self, quote_amount: float) -> float:
        """Convert a quote-currency amount to USD using ``_quote_to_usd``."""
        try:
            return float(quote_amount) * float(self._quote_to_usd or 1.0)
        except (TypeError, ValueError):
            return 0.0

    def _from_usd(self, usd_amount: float) -> float:
        """Convert a USD amount into quote-currency units, 0.0 when the rate is
        unusable and the caller must check.
        """
        try:
            rate = float(self._quote_to_usd or 0)
            if rate <= 0:
                return 0.0
            return float(usd_amount) / rate
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0

    async def self_destruct(
        self,
        confirmation_token: str = "",
        keep_running: bool = False,
    ) -> dict:
        """Aggressive full-position exit.

        Returns dict:
            {"ok": bool, "reason": str, "sold_qty": float,
             "sold_usd": float, "fill_price": float}

        """
        if confirmation_token != "SELF-DESTRUCT":  # noqa: S105  # nosec B105
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        "SELF-DESTRUCT REFUSED (entry guard): "
                        "confirmation_token must equal "
                        "'SELF-DESTRUCT' (case-sensitive). "
                        "No state changed."
                    ),
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "self_destruct",
                    type(_sup).__name__,
                    _sup,
                )
            return {
                "ok": False,
                "reason": (
                    "self_destruct refused: confirmation_token "
                    "must equal 'SELF-DESTRUCT' (case-sensitive)"
                ),
                "sold_qty": 0.0,
                "sold_usd": 0.0,
                "fill_price": 0.0,
            }

        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    "SELF-DESTRUCT armed. Querying exchange for "
                    "current holdings before market-sell..."
                ),
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup
            )

        try:
            bal = await self._get_balance(self.config.target_asset)
            units = float(getattr(bal, "total", 0) or bal.free or 0)
        except Exception as exc:
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"SELF-DESTRUCT REFUSED (balance fetch): "
                        f"exchange.get_balance("
                        f"{self.config.target_asset!r}) raised "
                        f"{type(exc).__name__}: {exc}. State "
                        f"unchanged. Retry when exchange is "
                        f"reachable."
                    ),
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "self_destruct",
                    type(_sup).__name__,
                    _sup,
                )
            return {
                "ok": False,
                "reason": (
                    f"self_destruct refused: balance fetch "
                    f"raised {type(exc).__name__}: {exc}"
                ),
                "sold_qty": 0.0,
                "sold_usd": 0.0,
                "fill_price": 0.0,
            }

        if units <= 0:
            self._main_lots = []
            try:
                self._tranches_closed_lifetime = int(
                    getattr(self, "_tranches_closed_lifetime", 0) or 0
                ) + len(self._fold_tranches)
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "self_destruct",
                    type(_sup).__name__,
                    _sup,
                )
            self._fold_tranches = []
            self._fold_queue_usd = 0.0
            self._current_holdings = 0.0
            try:
                if not keep_running:
                    self.state = BotState.PAUSED
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "self_destruct",
                    type(_sup).__name__,
                    _sup,
                )
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        "SELF-DESTRUCT: exchange holdings already 0. "
                        "State cleared; bot "
                        + ("PAUSED" if not keep_running else "kept RUNNING")
                        + "."
                    ),
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "self_destruct",
                    type(_sup).__name__,
                    _sup,
                )
            return {
                "ok": True,
                "reason": "no holdings to sell",
                "sold_qty": 0.0,
                "sold_usd": 0.0,
                "fill_price": 0.0,
            }

        try:
            ticker = await self._get_ticker(self.config.symbol)
            ref_price = float(ticker.last)
        except Exception:
            ref_price = float(self._last_trade_price or 0)

        from ..exchange.base import OrderSide, OrderType

        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"SELF-DESTRUCT FIRING: market-sell {units:.8f} "
                    f"{self.config.target_asset} (~${units * ref_price:.2f}) "
                    f"on {self.config.symbol}. All auto gates bypassed."
                ),
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup
            )
        try:
            self._emit_trade_notification(
                "SELF_DESTRUCT", "SENT", f"{units:.6f} {self.config.target_asset}"
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup
            )

        try:
            order = await self.guarded_place_order(
                symbol=self.config.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                amount=units,
                price=None,
            )
        except Exception as exc:
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"SELF-DESTRUCT FAILED: order raised "
                        f"{type(exc).__name__}: {exc}. State "
                        f"NOT cleared — operator must investigate."
                    ),
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "self_destruct",
                    type(_sup).__name__,
                    _sup,
                )
            return {
                "ok": False,
                "reason": f"order raised: {type(exc).__name__}: {exc}",
                "sold_qty": 0.0,
                "sold_usd": 0.0,
                "fill_price": 0.0,
            }

        if order is None:
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        "SELF-DESTRUCT FAILED: exchange returned no "
                        "order. State NOT cleared."
                    ),
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "self_destruct",
                    type(_sup).__name__,
                    _sup,
                )
            return {
                "ok": False,
                "reason": "exchange returned no order",
                "sold_qty": 0.0,
                "sold_usd": 0.0,
                "fill_price": 0.0,
            }

        fill_amount = float(
            getattr(order, "filled", None) or getattr(order, "amount", None) or units
        )
        fill_price = float(
            getattr(order, "average_price", None)
            or getattr(order, "average", None)
            or getattr(order, "price", None)
            or ref_price
        )
        fill_usd = fill_amount * fill_price * float(self._quote_to_usd or 1.0)
        # The only point on the SELF_DESTRUCT path holding the settled order.
        self._last_fill_venue_fee = self._venue_fee_record(
            order, fill_amount, fill_price
        )
        await self._settle_venue_fee(order, fill_amount, fill_price)

        self._main_lots = []
        try:
            self._tranches_closed_lifetime = int(
                getattr(self, "_tranches_closed_lifetime", 0) or 0
            ) + len(self._fold_tranches)
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup
            )
        self._fold_tranches = []
        self._fold_queue_usd = 0.0
        self._current_holdings = max(0.0, self._current_holdings - fill_amount)
        self._last_trade_side = "SCRUM"
        self._last_trade_price = fill_price
        self._reset_opposing_hysteresis_after_fill()
        try:
            self.stats.total_scrummed_usd += fill_usd
            self.note_scrum_retention_usd(fill_usd)
            self.stats.total_trades += 1
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup
            )

        try:
            if not keep_running:
                self.state = BotState.PAUSED
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup
            )

        try:
            self._bus.emit(
                "trade.filled",
                bot_id=self.bot_id,
                data={
                    "type": "SELF_DESTRUCT",
                    "side": "SELL",
                    "amount": fill_amount,
                    "price": fill_price,
                    "usd": fill_usd,
                    "profit": 0.0,
                    "operator_initiated": True,
                    "symbol": self.config.symbol,
                    "exchange": self.config.exchange_id,
                    **self._fill_fee_fields(fill_price),
                },
            )
            self._emit_voting_panel_snapshot_at_fire(
                side="SELL", trade_action="SELF_DESTRUCT"
            )
            self._emit_gate_decision_at_fire(side="SELL", trade_action="SELF_DESTRUCT")
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup
            )
        try:
            self._emit_trade_notification(
                "SELF_DESTRUCT",
                "FILLED",
                f"{fill_amount:.6f} @ ${fill_price:.8f} = ${fill_usd:.2f}",
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup
            )
        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"SELF-DESTRUCT COMPLETE: sold {fill_amount:.8f} "
                    f"@ ${fill_price:.8f} = ${fill_usd:.2f}. "
                    f"Internal state cleared. Bot "
                    + ("PAUSED" if not keep_running else "kept RUNNING")
                    + "."
                ),
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup
            )

        return {
            "ok": True,
            "reason": "self-destruct complete",
            "sold_qty": fill_amount,
            "sold_usd": fill_usd,
            "fill_price": fill_price,
        }

    def _update_opposing_hysteresis_state(
        self, delta: float, current_price: float
    ) -> None:
        """Per-tick arm and disarm of the opposing-direction hysteresis state.

        Behavior:
          • After a SCRUM: the FOLD side arms when ``delta`` crosses
            negative and disarms when it returns non-negative.
          • After a FOLD: the SCRUM side arms when ``delta`` crosses
            positive and disarms when it returns non-positive.

        ``_hyst_ref_*_side`` is captured at the moment of arming and becomes
        the pivot the opposing price distance is measured from.

        """
        try:
            _px = float(current_price)
        except (TypeError, ValueError):
            return
        if _px <= 0:
            return

        if self._last_trade_side == "SCRUM":
            if delta < 0:
                if not self._hyst_armed_fold_side:
                    self._hyst_armed_fold_side = True
                    self._hyst_ref_fold_side = _px
                    try:
                        _interval = float(self.config.scrumming_interval_pct or 0)
                    except (TypeError, ValueError):
                        _interval = 0.0
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD-side hysteresis ARMED: target delta "
                            f"crossed negative after recent SCRUM. "
                            f"Pivot ref = ${_px:.8f}. FOLD now requires "
                            f"price drop of {_interval:.2f}% + fee from "
                            f"this pivot."
                        ),
                    )
            else:
                if self._hyst_armed_fold_side:
                    self._hyst_armed_fold_side = False
                    self._hyst_ref_fold_side = 0.0
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            "FOLD-side hysteresis DISARMED: target "
                            "delta returned non-negative. Gate cleared "
                            "until delta drifts negative again."
                        ),
                    )
            if self._hyst_armed_scrum_side:
                self._hyst_armed_scrum_side = False
                self._hyst_ref_scrum_side = 0.0
        elif self._last_trade_side == "FOLD":
            if delta > 0:
                if not self._hyst_armed_scrum_side:
                    self._hyst_armed_scrum_side = True
                    self._hyst_ref_scrum_side = _px
                    try:
                        _interval = float(self.config.scrumming_interval_pct or 0)
                    except (TypeError, ValueError):
                        _interval = 0.0
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"SCRUM-side hysteresis ARMED: target delta "
                            f"crossed positive after recent FOLD. "
                            f"Pivot ref = ${_px:.8f}. SCRUM now requires "
                            f"price rise of {_interval:.2f}% + fee from "
                            f"this pivot."
                        ),
                    )
            else:
                if self._hyst_armed_scrum_side:
                    self._hyst_armed_scrum_side = False
                    self._hyst_ref_scrum_side = 0.0
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            "SCRUM-side hysteresis DISARMED: target "
                            "delta returned non-positive. Gate cleared "
                            "until delta drifts positive again."
                        ),
                    )
            if self._hyst_armed_fold_side:
                self._hyst_armed_fold_side = False
                self._hyst_ref_fold_side = 0.0
        else:
            self._hyst_armed_fold_side = False
            self._hyst_armed_scrum_side = False
            self._hyst_ref_fold_side = 0.0
            self._hyst_ref_scrum_side = 0.0

    def _reset_opposing_hysteresis_after_fill(self) -> None:
        """Disarm both opposing-direction hysteresis states and clear their pivots."""
        self._hyst_armed_fold_side = False
        self._hyst_armed_scrum_side = False
        self._hyst_ref_fold_side = 0.0
        self._hyst_ref_scrum_side = 0.0

    @property
    def position_value_usd(self) -> float:
        """USD-equivalent of current holdings via the cached quote→USD rate, 0.0
        without a price.
        """
        price = getattr(self, "_last_trade_price", 0.0) or self.stats.current_price
        if not price or price <= 0:
            return 0.0
        return priced_usd(
            float(self._current_holdings),
            float(price),
            float(self._quote_to_usd or 1.0),
        )

    @property
    def armed_action(self) -> Optional[str]:
        """What action Manual Fire will take if pressed now.

        Returns:
            'scrum' — above target, Manual Fire sells to rebalance
            'fold'  — below target, Manual Fire buys to rebalance
            None    — within the dust band (|delta| < 1% of target), or
                      price/holdings unavailable; Manual Fire is a no-op.

        """
        try:
            tgt = float(self._target_balance)
            if tgt <= 0:
                return None
            if not getattr(self, "_initialised", False):
                return None
            try:
                price = float(getattr(self.stats, "current_price", 0) or 0)
            except Exception:
                return None
            if price <= 0:
                return None
            holdings = float(self._current_holdings)
            _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
            value = priced_usd(holdings, price, _qrate)
            delta = target_delta_usd(value, tgt)
            dust = max(tgt * 0.01, 0.01)
            if delta > dust:
                return "scrum"
            if delta < -dust:
                return "fold"
            return None
        except Exception:
            return None

    @property
    def position_ceiling_usd(self) -> Optional[float]:
        """Ceiling in USD when enabled; None when disabled.

        = anchor_target_balance * position_ceiling_multiple
        """
        if not getattr(self.config, "position_ceiling_enabled", False):
            return None
        try:
            mult = float(self.config.position_ceiling_multiple)
            return position_ceiling(self._anchor_target_balance, mult)
        except Exception:
            return None

    @property
    def ceiling_ratio(self) -> Optional[float]:
        """``current_holdings_value / ceiling``, None when the ceiling is disabled
        or no price is available.

        Values:
            < 0.5  → plenty of runway, no taper
            0.5-1.0 → approaching ceiling, fold taper active
            >= 1.0 → at/above ceiling, fold hard-stopped

        """
        ceiling = self.position_ceiling_usd
        if ceiling is None or ceiling <= 0:
            return None
        price = getattr(self, "_last_trade_price", None)
        if not price or price <= 0:
            return None
        value = priced_usd(
            self._current_holdings,
            price,
            float(getattr(self, "_quote_to_usd", 1.0) or 1.0),
        )
        return ratio_to_ceiling(value, ceiling)

    @property
    def fold_rate_taper(self) -> float:
        """Multiplier on the fold's USD size in [0.0, 1.0], 1.0 when the ceiling
        is disabled.

        ``_tick_execute_fold`` spends the eligible tranche USD times this, so it
        shrinks the buy, not the interval between buys.

        Taper schedule:
            ratio < 0.5   → 1.0 (full size)
            ratio 0.5-1.0 → linear 1.0 → 0.1
            ratio >= 1.0  → 0.0 (hard stop)

        """
        ratio = self.ceiling_ratio
        if ratio is None:
            return 1.0
        return fold_rate_taper(ratio)

    def force_fire(self, aggressive: bool = False) -> None:
        """Manual Fire from the dashboard."""
        if aggressive:
            self._manual_fire_pending = True
            self._tick_counter = max(self._tick_counter, self._tick_skip - 1)
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    "MANUAL FIRE (aggressive): operator requested "
                    "immediate rebalance-to-target. Next tick will "
                    "execute a MARKET order sized to the current "
                    "delta. Bypasses TA/BB/fold gates."
                ),
            )
        else:
            self._tick_counter = max(self._tick_counter, self._tick_skip - 1)
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    "MANUAL FIRE: operator requested immediate "
                    "evaluation. Next tick will run full scrum/fold "
                    "gate checks. This does NOT bypass gate conditions."
                ),
            )

    def _pre_buy_allowed(
        self, intended_cost: float, path: str, ticker_price: float
    ) -> tuple[bool, str]:
        """Return (allowed, reason).

        • Layer 1 — Target-Delta budget per path:
            fold_rebuy / unspecified: projected ≤ target + per_cycle_growth_budget
            zero_balance_initial_entry: projected ≤ target_balance × (1 + tol)
            hedge_replenish: projected ≤ current_position + hedge_bal
        • Layer 2 — Position Ceiling (when enabled): projected ≤ anchor × multiple

        """
        try:
            _cap_pct = float(getattr(self.config, "max_target_growth_pct", 1.0))
            _anchor = float(
                getattr(self, "_anchor_target_balance", self._target_balance)
            )
            _per_cycle_growth_budget = _anchor * (_cap_pct / 100.0)
            _qrate = float(self._quote_to_usd or 1.0)
            _current_pos = float(self._current_holdings) * float(ticker_price) * _qrate
            _projected = _current_pos + float(intended_cost)
            _target = float(self._target_balance)
            _slip = 0.005

            if path == "zero_balance_initial_entry":
                _budget_ceiling = _target * (1.0 + _slip)
            elif path == "hedge_replenish":
                try:
                    _hedge_bal = float(getattr(self, "_hedge_bal", 0.0) or 0.0)
                except (TypeError, ValueError):
                    _hedge_bal = 0.0
                _budget_ceiling = _current_pos + _hedge_bal * (1.0 + _slip)
            elif path in ("fold_rebuy", "manual_tranche_fire"):
                _budget_ceiling = _projected + 1.0
            else:
                _budget_ceiling = (_target + _per_cycle_growth_budget) * (1.0 + _slip)
            if _projected > _budget_ceiling:
                return False, (
                    f"PRE-BUY REFUSED (path={path}, Layer 1): "
                    f"projected position ${_projected:.2f} (current "
                    f"${_current_pos:.2f} + intended buy "
                    f"${intended_cost:.2f}) would exceed Target-Delta "
                    f"budget ${_budget_ceiling:.2f} (target ${_target:.2f} "
                    f"+ per-cycle growth ${_per_cycle_growth_budget:.2f}). "
                    f"Buy skipped before TA/order."
                )

            if getattr(self.config, "position_ceiling_enabled", False):
                try:
                    _smart_mult = float(
                        getattr(self.config, "position_ceiling_multiple", 1.0)
                    )
                    _smart_ceiling_usd = position_ceiling(_anchor, _smart_mult)
                    if _projected > _smart_ceiling_usd:
                        return False, (
                            f"PRE-BUY REFUSED (path={path}, Layer 2): "
                            f"projected position ${_projected:.2f} would "
                            f"exceed Position Ceiling ${_smart_ceiling_usd:.2f} "
                            f"(anchor ${_anchor:.2f} × Ceiling Multiple "
                            f"{_smart_mult:.1f}x). "
                            f"Bot at maturity — awaiting detonation harvest."
                        )
                except (TypeError, ValueError, AttributeError) as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s",
                        "_pre_buy_allowed",
                        type(_sup).__name__,
                        _sup,
                    )
            return True, ""
        except Exception as exc:
            return False, (
                f"PRE-BUY REFUSED (path={path}): pre-check raised "
                f"{type(exc).__name__}: {exc}. Fail-closed."
            )

    async def tick(self) -> None:
        symbol = self.config.symbol

        try:
            await self._ensure_capital_reservation(
                float(getattr(self, "_last_price", 0) or 0)
            )
        except Exception as _crr_tick_exc:  # noqa: BLE001
            logger.debug(
                "Bot %s reservation ensure at tick top raised: %s",
                self.bot_id,
                _crr_tick_exc,
            )

        if self.config.scrum_read_rate_min > 0 and not self._manual_fire_pending:
            _tick_sec = max(self.tick_interval, 0.1)
            _base_skip = max(1, int((self.config.scrum_read_rate_min * 60) / _tick_sec))
            self._tick_skip_search = _base_skip
            if self._scrum_target_mode in ("track", "fire"):
                self._tick_skip = max(1, _base_skip // 10)
            else:
                self._tick_skip = _base_skip
            self._tick_counter += 1
            if self._tick_counter < self._tick_skip and self._initialised:
                # Still polling; the init tick always runs.
                try:
                    from src.core.signal_contract import emit as _tk

                    _tk(
                        "tick.08.001.event.throttled",
                        actual=True,
                        context={
                            "bot_id": self.bot_id,
                            "counter": self._tick_counter,
                            "skip": self._tick_skip,
                            "read_rate_min": self.config.scrum_read_rate_min,
                        },
                    )
                except Exception as _sup:  # noqa: BLE001,S110
                    logger.debug(
                        "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                    )
                return
            self._tick_counter = 0
            # The worked path, so a run with no records differs from no work.
            try:
                from src.core.signal_contract import emit as _tk2

                _tk2(
                    "tick.08.002.event.worked",
                    actual=True,
                    context={"bot_id": self.bot_id, "skip": self._tick_skip},
                )
            except Exception as _sup:  # noqa: BLE001,S110
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
        elif self._manual_fire_pending:
            self._tick_counter = 0

        try:
            await self.refresh_exchange_position_health()
        except Exception as _sup:
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        if not self._initialised:
            await self._tick_initialise(symbol)
            return

        self._reconcile_tick_counter += 1
        if (
            self._reconcile_tick_counter >= self._reconcile_interval
            and self._reconcile_interval > 0
        ):
            self._reconcile_tick_counter = 0
            try:
                await self._reconcile_holdings(reason="periodic")
            except Exception as exc:
                logger.debug("Bot %s periodic reconcile raised: %s", self.bot_id, exc)

        ticker = await self._get_ticker(symbol)
        self.stats.current_price = ticker.last
        try:
            await self._refresh_quote_to_usd()
        except Exception as _sup:
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        self._despawn_aged_tranches()

        try:
            await self._reconcile_stack_tranches_invisible(
                current_price=float(ticker.last)
            )
        except Exception as _stack_exc:
            logger.warning(
                "Bot %s stack reconciler raised: %s", self.bot_id, _stack_exc
            )

        try:
            await self._reconcile_stack_tranches_visible()
        except Exception as _stack_v_exc:
            logger.warning(
                "Bot %s visible stack reconciler raised: %s", self.bot_id, _stack_v_exc
            )

        current_value = priced_usd(
            self._current_holdings, ticker.last, float(self._quote_to_usd or 1.0)
        )

        _delta_early = target_delta_usd(current_value, self._target_balance)
        self._update_opposing_hysteresis_state(_delta_early, ticker.last)

        # Within the dust band of target the tick returns; manual fire bypasses it.
        _dust_band_usd = at_target_dust_band(self._target_balance)
        if (
            not self._manual_fire_pending
            and abs(current_value - self._target_balance) <= _dust_band_usd
        ):
            self._at_target_counter = getattr(self, "_at_target_counter", 0) + 1
            if self._at_target_counter % 60 == 1:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"AT TARGET: position=${current_value:.2f} sits "
                        f"within the dust band (±${_dust_band_usd:.4f}) of "
                        f"target=${self._target_balance:.2f}. The tick "
                        f"exits early. No TA, no signals and no trades "
                        f"until price moves the position off target."
                    ),
                )
            try:
                from src.core.signal_contract import emit as _dz

                _dz(
                    "tick.08.003.event.exit_dust_band",
                    actual=True,
                    context={
                        "bot_id": self.bot_id,
                        "position": round(float(current_value), 6),
                        "target": round(float(self._target_balance), 6),
                        "band": round(float(_dust_band_usd), 6),
                    },
                )
            except Exception as _sup:  # noqa: BLE001,S110
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
            return
        self._at_target_counter = 0

        if self._manual_fire_pending:
            await self._tick_manual_fire(ticker)
            return

        try:
            _stack_pending = float(getattr(self, "_pending_stack_buy_usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            _stack_pending = 0.0
        if _stack_pending > 0:
            await self._tick_wire_stack_fire(ticker, _stack_pending)
            return

        try:
            _cartridge_pct = float(
                getattr(self.config, "max_cartridge_size_pct", 10.0) or 0.0
            )
        except (TypeError, ValueError):
            _cartridge_pct = 0.0

        _cartridge_pct = self._tick_smart_cartridge_pct(_cartridge_pct)

        if _cartridge_pct > 0 and self._target_balance > 0:
            _cartridge_threshold = cartridge_threshold_usd(
                self._target_balance, _cartridge_pct
            )
            _cartridge_delta = target_delta_usd(current_value, self._target_balance)
            if abs(_cartridge_delta) >= _cartridge_threshold:
                _direction = "SCRUM" if _cartridge_delta > 0 else "FOLD"

                _hyst_blocks = False
                _hyst_reason = ""
                try:
                    _interval = float(self.config.scrumming_interval_pct or 0)
                    _fee = float(getattr(self.config, "trading_fee_pct", 0.6) or 0.6)
                    _eff_pct = _interval + _fee
                    _eff_frac = _eff_pct / 100.0
                except (TypeError, ValueError):
                    _eff_pct = 3.6
                    _eff_frac = 0.036

                if (
                    _direction == "SCRUM"
                    and getattr(self, "_hyst_armed_scrum_side", False)
                    and float(getattr(self, "_hyst_ref_scrum_side", 0.0) or 0.0) > 0
                ):
                    _required_min = self._hyst_ref_scrum_side * (1.0 + _eff_frac)
                    if ticker.last < _required_min:
                        _hyst_blocks = True
                        _hyst_reason = (
                            f"price ${ticker.last:.8f} below "
                            f"${_required_min:.8f} "
                            f"(pivot ${self._hyst_ref_scrum_side:.8f} "
                            f"+ {_eff_pct:.2f}%)"
                        )
                elif (
                    _direction == "FOLD"
                    and getattr(self, "_hyst_armed_fold_side", False)
                    and float(getattr(self, "_hyst_ref_fold_side", 0.0) or 0.0) > 0
                ):
                    _required_max = self._hyst_ref_fold_side * (1.0 - _eff_frac)
                    if ticker.last > _required_max:
                        _hyst_blocks = True
                        _hyst_reason = (
                            f"price ${ticker.last:.8f} above "
                            f"${_required_max:.8f} "
                            f"(pivot ${self._hyst_ref_fold_side:.8f} "
                            f"− {_eff_pct:.2f}%)"
                        )

                if _hyst_blocks:
                    import time as _t_block

                    _now_b = _t_block.time()
                    _last_b = float(
                        getattr(self, "_cartridge_blocked_last_log_ts", 0.0) or 0.0
                    )
                    if _now_b - _last_b >= 30.0:
                        self._cartridge_blocked_last_log_ts = _now_b
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"MAX CARTRIDGE BLOCKED (hysteresis): "
                                f"would fire {_direction} on "
                                f"|delta|=${abs(_cartridge_delta):.2f} "
                                f"≥ ${_cartridge_threshold:.2f}, but "
                                f"{_hyst_reason}. Refusing to prevent "
                                f"fee-thrash round-trip with recent "
                                f"opposite trade. Will re-evaluate "
                                f"each tick as price moves."
                            ),
                        )
                else:
                    await self._tick_cartridge_fire(
                        ticker,
                        _direction,
                        _cartridge_delta,
                        _cartridge_threshold,
                        _cartridge_pct,
                    )
                    return

        if await self._tick_detonation(ticker):
            return

        if current_value < self._target_balance * 0.01:
            await self._tick_initial_entry(ticker, symbol, current_value)
            return

        self.stats.position_value = current_value

        delta = target_delta_usd(current_value, self._target_balance)
        delta_pct = target_delta_pct(delta, self._target_balance)
        _interval_usd = scrumming_interval_usd(
            self._target_balance, self.config.scrumming_interval_pct
        )

        ta_tf = self.config.ta_timeframe or "1h"
        try:
            raw_candles = await self._get_ohlcv(
                symbol,
                timeframe=ta_tf,
                limit=100,
            )
            candles = candles_from_raw(raw_candles)
        except Exception:
            candles = []

        try:
            self._check_circuit_breakers(candles)
        except Exception as _cb_exc:
            logger.warning(
                "Bot %s circuit breaker check raised %s: %s",
                self.bot_id,
                type(_cb_exc).__name__,
                _cb_exc,
            )
        if self._cb_hard_tripped:
            return

        summary = None
        bb_result = None
        if len(candles) >= MIN_CANDLES_FOR_TA:
            summary = self._voting_engine.compute_all(
                candles, ta_tf, symbol=self.config.symbol
            )
            self._last_summary = summary

            bb_result = detect_bb_proximity(
                candles,
                tolerance_pct=self.config.bb_tolerance_pct,
                consolidation_threshold=3.0,
                min_pattern_candles=self.config.bb_landing_strip_candles,
            )
            self._last_bb = bb_result

        below_interval = delta_below_interval(delta, _interval_usd)

        if below_interval and self._fold_queue_usd == 0 and self._dist_accumulator == 0:
            ta_dir = summary.consensus_direction.name if summary else "N/A"
            ta_conf = f"{summary.consensus_confidence:.0%}" if summary else "—"
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"READ: ${ticker.last:.8f} | delta ${delta:+.4f} "
                f"({delta_pct:.1f}% of target, under the "
                f"{self.config.scrumming_interval_pct}% interval) | "
                f"TA={ta_dir} ({ta_conf}) | holding",
            )
            self._last_price = ticker.last
            return

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=f"DELTA: ${delta:+.4f} ({delta_pct:.1f}% of target) | "
            f"holdings ${current_value:.4f} vs target "
            f"${self._target_balance:.4f}"
            f"{' | under the interval, checking the queues' if below_interval else ''}",
        )

        if not summary:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message="Insufficient candle data for TA (need 30+)",
            )
            self._last_price = ticker.last
            return

        bb_confidence_boost = 0.0
        bb_override_direction = None
        if bb_result and bb_result.landing_strip:
            # The same favour ata_gate_scan.landing_strip_favour sums.
            bb_confidence_boost = (
                LANDING_STRIP_FAVOUR
                + bb_result.consolidation_strength * LANDING_STRIP_STRENGTH_FAVOUR
            )
            if bb_result.landing_strip_side == "upper":
                bb_override_direction = SignalDirection.BEARISH
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"LANDING STRIP (upper BB): {bb_result.landing_strip_candles} "
                    f"tight HA candles (avg body {bb_result.ha_body_avg}%), "
                    f"strength={bb_result.consolidation_strength:.2f}",
                )
            elif bb_result.landing_strip_side == "lower":
                bb_override_direction = SignalDirection.BULLISH
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"LANDING STRIP (lower BB): {bb_result.landing_strip_candles} "
                    f"tight HA candles (avg body {bb_result.ha_body_avg}%), "
                    f"strength={bb_result.consolidation_strength:.2f}",
                )

        tightening = None
        if len(candles) >= TIGHTENING_MIN_CANDLES:
            try:
                # min_consecutive counts shrinking bodies, not the tight
                # candles bb_landing_strip_candles counts.
                tightening = detect_landing_strip_v2(
                    candles,
                    min_consecutive=TIGHTENING_MIN_CONSECUTIVE,
                    shrink_threshold=TIGHTENING_SHRINK_THRESHOLD,
                    bb_tolerance_pct=TIGHTENING_TOLERANCE_PCT,
                )
                if tightening and tightening.detected:
                    bb_confidence_boost += tightening.confidence_boost
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TIGHTENING ({tightening.side} BB): "
                        f"{tightening.length} candles, "
                        f"ratio={tightening.tightening_ratio:.0%}, "
                        f"boost=+{tightening.confidence_boost:.2f}",
                    )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )

        if summary:
            eff_confidence = summary.consensus_confidence
            eff_direction = summary.consensus_direction
        else:
            eff_confidence = 0.0
            eff_direction = None

        bb_pos = bb_result.bb_position if bb_result else 0
        at_upper_bb = bb_pos > 0.75
        in_bb_middle = 0.35 <= bb_pos <= 0.65

        if bb_result is not None:
            _cur = max(0.0, min(1.0, float(bb_pos)))
            _at_upper_extreme = _cur >= 0.75
            _at_lower_extreme = _cur <= 0.25
            _reset_fired = False
            if self._target_grow_last_side == "lower" and _at_upper_extreme:
                _reset_fired = True
            elif self._target_grow_last_side == "upper" and _at_lower_extreme:
                _reset_fired = True
            elif self._target_grow_last_side is None and (
                _at_upper_extreme or _at_lower_extreme
            ):
                self._target_grow_last_side = "lower" if _at_lower_extreme else "upper"
            if _reset_fired and self._fold_cycle_cap_consumed > 1e-9:
                _prev_consumed = self._fold_cycle_cap_consumed
                _prev_side = self._target_grow_last_side
                self._fold_cycle_cap_consumed = 0.0
                self._target_grow_last_side = None
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD CYCLE RESET (D2-b asymmetric): "
                        f"bb_pos {_cur:.2f} reached opposite "
                        f"extreme (last growth fired {_prev_side}-"
                        f"side). Growth Rate Cap consumed "
                        f"${_prev_consumed:.4f} this cycle — "
                        f"reset to $0.00. Next fold-surplus may "
                        f"grow target up to full cap budget."
                    ),
                )
                logger.info(
                    "Bot %s fold cycle reset (D2-b asymmetric, last_side=%s)"
                    " at bb_pos=%.3f (prev consumed $%.4f)",
                    self.bot_id,
                    _prev_side,
                    _cur,
                    _prev_consumed,
                )
            elif _reset_fired:
                self._target_grow_last_side = None

        position_boost = 0.0
        if summary:
            for sig in summary.signals:
                if (
                    sig.indicator == "vortex"
                    and sig.direction == SignalDirection.BULLISH
                ):
                    if at_upper_bb and sig.confidence > 0.5:
                        position_boost += 0.12
                    elif in_bb_middle:
                        position_boost -= 0.05
                if sig.indicator == "macd" and sig.direction == SignalDirection.BULLISH:
                    if at_upper_bb and sig.confidence > 0.3:
                        position_boost += 0.08
                    elif in_bb_middle:
                        position_boost -= 0.03
                if (
                    sig.indicator == "ichimoku"
                    and sig.direction == SignalDirection.BULLISH
                ):
                    position_boost += 0.05
                elif (
                    sig.indicator == "ichimoku"
                    and sig.direction == SignalDirection.BEARISH
                ):
                    position_boost -= 0.05
                if sig.indicator == "stochastic_rsi" and sig.confidence > 0.7:
                    if sig.direction == SignalDirection.BEARISH:
                        position_boost += 0.10
                    elif sig.direction == SignalDirection.BULLISH:
                        position_boost -= 0.08

        if len(candles) >= 60:
            sw = 20
            highs = [c.high for c in candles[-sw * 3 :]]
            lows = [c.low for c in candles[-sw * 3 :]]
            if len(highs) >= sw * 3:
                rh = max(highs[-sw:])
                ph = max(highs[-sw * 2 : -sw])
                rl = min(lows[-sw:])
                pl = min(lows[-sw * 2 : -sw])
                uptrend = rh > ph and rl > pl
                downtrend = rh < ph and rl < pl
                if uptrend:
                    if at_upper_bb:
                        position_boost += 0.05
                    elif in_bb_middle:
                        position_boost -= 0.08
                elif downtrend:
                    position_boost += 0.05

        trend_hold = False
        trend_strength = 0.5
        if len(candles) >= 20:
            recent = candles[-20:]
            bull_count = sum(1 for c in recent if c.close > c.open)
            trend_strength = bull_count / len(recent)
            if trend_strength > _STRONG_TREND_MIN_BULL_SHARE:
                trend_hold = True
            # The measurement, not TREND-HOLD's verdict the override clears.
            self._last_trend_bull_candles = int(bull_count)
        else:
            self._last_trend_bull_candles = 0

        band_travel_triggered = False
        band_travel_frac = 0.0
        if (
            self.config.band_travel_pct > 0
            and self._last_trade_price > 0
            and bb_result is not None
            and bb_result.upper > 0
            and bb_result.lower > 0
        ):
            _bb_width = max(bb_result.upper - bb_result.lower, 1e-12)
            band_travel_frac = abs(ticker.last - self._last_trade_price) / _bb_width
            if (
                abs(ticker.last - self._last_trade_price)
                >= self.config.band_travel_pct / 100.0 * _bb_width
                and delta > 0
            ):
                band_travel_triggered = True

        trend_override = abs(delta) >= _interval_usd * 2.0 or band_travel_triggered
        if trend_hold and trend_override:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"TREND-HOLD OVERRIDE: trend {trend_strength:.0%} bullish "
                f"but {'band travel ' + f'{band_travel_frac:.0%}' if band_travel_triggered else 'delta 2x interval'} "
                f"— scrum allowed this tick",
            )
            trend_hold = False
        elif trend_hold:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"TREND-HOLD: {trend_strength:.0%} of last 20 candles bullish "
                f"— suppressing scrum",
            )

        bb_near = ""
        if bb_result:
            if bb_result.near_upper:
                bb_near = ", near the upper band"
            elif bb_result.near_lower:
                bb_near = ", near the lower band"

        # Both favours skew the floor, so the confidence prints alone.
        _skew_note = ""
        if position_boost or bb_confidence_boost:
            _skew_note = f", floor skew {position_boost:+.2f} position" + (
                "" if not bb_confidence_boost else f" {bb_confidence_boost:+.2f} BB"
            )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=f"TA VOTE: {summary.consensus_direction.name} at "
            f"confidence {summary.consensus_confidence:.2f}"
            f"{_skew_note} | "
            f"{summary.bullish_count} bullish, "
            f"{summary.neutral_count} neutral, "
            f"{summary.bearish_count} bearish | "
            f"BB position {bb_pos:.1%}{bb_near}",
        )

        self._bus.emit(
            "ta.voting",
            bot_id=self.bot_id,
            symbol=symbol,
            bullish=summary.bullish_count,
            bearish=summary.bearish_count,
            neutral=summary.neutral_count,
            net_score=summary.net_score,
            confidence=summary.consensus_confidence,
            direction=summary.consensus_direction.name,
            bb_position=bb_pos,
            landing_strip=bb_result.landing_strip if bb_result else False,
            signals=[
                {
                    "indicator": s.indicator,
                    "direction": s.direction.name,
                    "confidence": round(s.confidence, 3),
                }
                for s in summary.signals
            ],
        )

        self._phantom_locked = False
        self._phantom_lock_timeframe = ""
        for _lock_tf in ("4h", "1h"):
            if self._coordinator.is_locked(_lock_tf, SignalDirection.BULLISH):
                self._phantom_locked = True
                self._phantom_lock_timeframe = _lock_tf
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"PHANTOM LOCK ACTIVE ({_lock_tf} bullish): "
                    f"scrum suppressed for this tick. "
                    f"Folds/hedge/dist remain active per "
                    f"downside-protection invariant.",
                )
                break  # Highest active TF wins.

        if bb_override_direction and eff_direction == SignalDirection.NEUTRAL:
            eff_direction = bb_override_direction

        try:
            _eff_hyst_pct = (
                float(self.config.scrumming_interval_pct)
                + float(getattr(self.config, "trading_fee_pct", 0.6) or 0.6)
            ) / 100.0
        except Exception:
            _eff_hyst_pct = 0.036
        _hyst_ok_scrum_side = True
        if self._hyst_armed_scrum_side and self._hyst_ref_scrum_side > 0:
            _hyst_ok_scrum_side = ticker.last >= self._hyst_ref_scrum_side * (
                1.0 + _eff_hyst_pct
            )
        _hyst_ok_fold_side = True
        if self._hyst_armed_fold_side and self._hyst_ref_fold_side > 0:
            _hyst_ok_fold_side = ticker.last <= self._hyst_ref_fold_side * (
                1.0 - _eff_hyst_pct
            )
        _bb_lower_dt_pre, _bb_upper_dt_pre = self._bb_detect_thresholds()
        _be_upper = False
        _be_upper_wick = False
        _be_lower = False
        _be_lower_wick = False
        if (
            getattr(self.config, "bb_bullseye_check", True)
            and bb_result is not None
            and getattr(bb_result, "upper", 0) > 0
            and getattr(bb_result, "lower", 0) > 0
        ):
            _bp_inline = ticker.last
            _touch_tol_inline = 0.005
            _wick_tol_inline = 0.002
            try:
                _be_upper = (
                    abs(_bp_inline - bb_result.upper) / bb_result.upper
                    < _touch_tol_inline
                )
                _be_lower = (
                    abs(_bp_inline - bb_result.lower) / bb_result.lower
                    < _touch_tol_inline
                )
                if candles and not _be_upper:
                    _be_upper_wick = candles[-1].high >= bb_result.upper * (
                        1.0 - _wick_tol_inline
                    )
                if candles and not _be_lower:
                    _be_lower_wick = candles[-1].low <= bb_result.lower * (
                        1.0 + _wick_tol_inline
                    )
            except (TypeError, ValueError, ZeroDivisionError) as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
        _bb_proximity_upper = (
            (bb_pos >= _bb_upper_dt_pre) or _be_upper or _be_upper_wick
        )
        _bb_proximity_lower = (
            (bb_pos <= _bb_lower_dt_pre) or _be_lower or _be_lower_wick
        )
        _delta_available = abs(delta) >= _interval_usd
        _bb_priority_scrum_skew = (
            _bb_proximity_upper
            and _hyst_ok_scrum_side
            and _delta_available
            and delta > 0
        )
        _bb_priority_fold_skew = (
            _bb_proximity_lower
            and _hyst_ok_fold_side
            and _delta_available
            and delta < 0
        )
        _bb_priority_arm = _bb_priority_scrum_skew or _bb_priority_fold_skew
        # All three favours sum into one skew applied to the floor.
        _ta_conf_skew = position_boost + bb_confidence_boost
        if _bb_priority_arm:
            _ta_conf_skew += _BB_PRIORITY_SKEW
        _eff_conf_floor = _skewed_confidence_floor(_ta_conf_skew)
        if _bb_priority_arm:
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"BB PRIORITY SKEW "
                        f"[{'SCRUM' if _bb_priority_scrum_skew else 'FOLD'}] "
                        f"at BB position {bb_pos:.1%}, delta "
                        f"${abs(delta):.2f} at or over the interval. "
                        f"Confidence stays {eff_confidence:.2f}. The floor "
                        f"drops from {_TA_CONFIDENCE_FLOOR:.2f} to "
                        f"{_eff_conf_floor:.4f}, divided by "
                        f"{1.0 + _ta_conf_skew:.2f}: BB priority "
                        f"{_BB_PRIORITY_SKEW:+.2f}, position "
                        f"{position_boost:+.2f}, BB confidence "
                        f"{bb_confidence_boost:+.2f}. The direction is "
                        f"untouched, so a contradicting TA still refuses "
                        f"the trade."
                    ),
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )

        is_bullish = (
            eff_direction in (SignalDirection.BULLISH, SignalDirection.NEUTRAL)
            and eff_confidence >= _eff_conf_floor
        )
        is_bearish = (
            eff_direction in (SignalDirection.BEARISH, SignalDirection.NEUTRAL)
            and eff_confidence >= _eff_conf_floor
        )

        if (
            bb_result
            and bb_result.landing_strip
            and bb_result.landing_strip_side == "upper"
        ):
            is_bullish = True
        if (
            bb_result
            and bb_result.landing_strip
            and bb_result.landing_strip_side == "lower"
        ):
            is_bearish = True

        if self.config.bb_midline_gate:
            scrum_ok = (bb_pos > 0.50) and not self._phantom_locked
            fold_ok_midline = bb_pos < 0.50
        else:
            scrum_ok = not self._phantom_locked
            fold_ok_midline = True

        _ripe_scrum = False
        _deep_fold = False
        _bb_lower_dt, _bb_upper_dt = self._bb_detect_thresholds()
        if (
            bb_result is not None
            and bb_result.upper > 0
            and bb_result.lower > 0
            and ticker.last > 0
        ):
            if delta > 0 and not below_interval and bb_pos >= _bb_upper_dt:
                _ripe_scrum = True
            if delta < 0 and not below_interval and bb_pos <= _bb_lower_dt:
                _deep_fold = True

        if _ripe_scrum and not scrum_ok:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"RIPE-HARVEST (override via "
                    f"GateChain): Δ={delta_pct:.1f}% ≥ "
                    f"interval {self.config.scrumming_interval_pct:.1f}% "
                    f"+ bb_pos={bb_pos:.2f} ≥ Upper Detect Threshold "
                    f"{_bb_upper_dt:.3f}. RipeHarvestScrumOverride "
                    f"will force-pass midline_scrum + target_fires + "
                    f"trend_hold + ta_bullish. Operator directive: "
                    f"claim the profit."
                ),
            )
        if _deep_fold and not fold_ok_midline:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"DEEP-FOLD (override via "
                    f"GateChain): Δ={delta_pct:.1f}% ≥ "
                    f"interval {self.config.scrumming_interval_pct:.1f}% "
                    f"+ bb_pos={bb_pos:.2f} ≤ Lower Detect Threshold "
                    f"{_bb_lower_dt:.3f}. DeepFoldOverride will "
                    f"force-pass midline_fold + ta_bearish. The "
                    f"per-tranche price-floor is still enforced downstream."
                ),
            )

        target_fires = self._tick_target_ramp(
            bb_result, ticker, delta, delta_pct, _interval_usd
        )

        self._tick_bullseye_notices(bb_result, candles, ticker)

        if delta > 0 and not (
            not below_interval
            and is_bullish
            and not trend_hold
            and scrum_ok
            and target_fires
        ):
            self._hold_tick_counter += 1
            if self._hold_tick_counter % 50 == 0:
                _blocked = []
                if below_interval:
                    _blocked.append(
                        f"the {delta_pct:.1f}% move is under the "
                        f"{self.config.scrumming_interval_pct}% interval"
                    )
                if not is_bullish:
                    # is_bullish is a conjunction; name the half that failed.
                    if eff_direction not in (
                        SignalDirection.BULLISH,
                        SignalDirection.NEUTRAL,
                    ):
                        _blocked.append(
                            f"TA={eff_direction.name} is not BULLISH or NEUTRAL"
                        )
                    else:
                        _blocked.append(
                            f"TA={eff_direction.name} but confidence "
                            f"{eff_confidence:.4f} < {_eff_conf_floor:.4f} floor"
                        )
                if trend_hold:
                    _blocked.append("trend hold is active")
                if not scrum_ok:
                    _blocked.append(
                        f"the BB gate refused at position {bb_pos:.1%}, "
                        f"phantom lock {_yes_no(self._phantom_locked)}"
                    )
                if not target_fires:
                    _blocked.append("the ramp has not reached FIRE")
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"HOLD SCRUM SUMMARY (tick "
                    f"{self._hold_tick_counter}): delta +{delta_pct:.1f}%, "
                    f"${current_value:.2f} against target "
                    f"${self._target_balance:.2f}. Blocked by "
                    f"{'; '.join(_blocked) or 'a gate the summary does not name'}.",
                )

        if _ripe_scrum:
            if not is_bullish:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"RIPE HARVEST OVERRIDE: the TA gate refused "
                    f"the scrum (TA={eff_direction.name}, confidence "
                    f"{eff_confidence:.4f}, floor {_eff_conf_floor:.4f}). "
                    f"The ripe-harvest override passes it.",
                )
            if not target_fires:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message="RIPE HARVEST OVERRIDE: the FIRE gate refused "
                    "the scrum, the ramp having not reached FIRE. "
                    "The ripe-harvest override passes it.",
                )
            if trend_hold:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"RIPE HARVEST OVERRIDE: the trend-hold gate "
                    f"refused the scrum at {trend_strength:.0%} bullish. "
                    f"The ripe-harvest override passes it.",
                )
        if _deep_fold:
            if not is_bearish:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"DEEP FOLD OVERRIDE: the TA gate refused the "
                    f"fold (TA={eff_direction.name}, confidence "
                    f"{eff_confidence:.4f}, floor {_eff_conf_floor:.4f}). "
                    f"The deep-fold override passes it.",
                )

        _bb_above_upper_dt = bb_pos >= _bb_upper_dt
        _bb_below_lower_dt = bb_pos <= _bb_lower_dt
        _cb_blocks_scrum = self._cb_soft_active_side == "scrum"
        _htf_bias_dir = None
        _htf_bias_detail: dict = {}
        try:
            if self._coordinator is not None:
                _htf_bias_dir, _htf_bias_detail = self._coordinator.get_higher_tf_bias(
                    self.bot_id,
                    self.config.ta_timeframe or "1h",
                )
        except Exception as _hbexc:
            logger.debug(
                "Bot %s higher-TF bias read raised %s: %s",
                self.bot_id,
                type(_hbexc).__name__,
                _hbexc,
            )
        _htf_blocks_scrum = _htf_bias_dir == SignalDirection.BULLISH
        _flag_require_ta_bullish = bool(
            getattr(self.config, "scrum_require_ta_bullish", True)
        )
        _flag_hold_in_uptrend = bool(
            getattr(self.config, "scrum_hold_in_uptrend", True)
        )
        _flag_defer_to_htf = bool(getattr(self.config, "scrum_defer_to_htf", True))
        _eff_is_bullish = is_bullish if _flag_require_ta_bullish else True
        _eff_trend_hold = trend_hold if _flag_hold_in_uptrend else False
        _eff_htf_blocks = _htf_blocks_scrum if _flag_defer_to_htf else False

        _scrum_blockers: list[str] = []
        if delta <= 0:
            _scrum_blockers.append("delta≤0")
        if below_interval:
            _scrum_blockers.append(
                f"below_interval(Δ%<{self.config.scrumming_interval_pct})"
            )
        if not _eff_is_bullish and not _ripe_scrum:
            _scrum_blockers.append(
                f"TA-conf-below-floor(dir={eff_direction.name},"
                f"conf={eff_confidence:.4f}<{_eff_conf_floor:.4f})"
                if eff_direction in (SignalDirection.BULLISH, SignalDirection.NEUTRAL)
                else f"TA-not-bullish(dir={eff_direction.name})"
            )
        if _eff_trend_hold and not _ripe_scrum:
            _scrum_blockers.append(f"trend_hold({trend_strength:.0%})")
        if not scrum_ok and not _ripe_scrum:
            _scrum_blockers.append(f"scrum_ok=False(bb_pos={bb_pos:.2f})")
        if not target_fires and not _ripe_scrum:
            _scrum_blockers.append("target_fires=False(detect/fire)")
        if not _bb_above_upper_dt:
            _scrum_blockers.append(
                f"BB-below-upper-detect(bb_pos={bb_pos:.2f}<{_bb_upper_dt:.2f})"
            )
        if _cb_blocks_scrum:
            _scrum_blockers.append("CB-soft-trip")
        if _eff_htf_blocks:
            _scrum_blockers.append("HTF-bullish")
        if not _hyst_ok_scrum_side:
            try:
                _ref_px = float(self._hyst_ref_scrum_side or 0)
                _eff_pct = float(self.config.scrumming_interval_pct or 0) + float(
                    getattr(self.config, "trading_fee_pct", 0.6) or 0.6
                )
                _required = _ref_px * (1.0 + _eff_pct / 100.0)
                _scrum_blockers.append(
                    f"OTD-hyst(px ${ticker.last:.8f} < "
                    f"${_required:.8f}; pivot ${_ref_px:.8f} "
                    f"+ {_eff_pct:.2f}%)"
                )
            except Exception:
                _scrum_blockers.append("OTD-hyst-armed")
        try:
            self._last_gate_state["scrum_armed"] = len(_scrum_blockers) == 0
            self._last_gate_state["scrum_blockers"] = list(_scrum_blockers)
            self._last_gate_state["evaluated_at_tick"] = (
                self._last_gate_state.get("evaluated_at_tick", 0) + 1
            )
            self._last_gate_state["scrum_fixture"] = {
                "delta": float(delta),
                "below_interval": bool(below_interval),
                "ticker_last": float(ticker.last),
                "bb_pos": float(bb_pos),
                "landing_strip": bool(bb_result.landing_strip if bb_result else False),
                "landing_strip_side": str(
                    bb_result.landing_strip_side if bb_result else ""
                )
                or "",
                "landing_strip_candles": int(
                    bb_result.landing_strip_candles if bb_result else 0
                ),
                "bb_upper_dt": float(_bb_upper_dt),
                "bb_lower_dt": float(_bb_lower_dt),
                "is_bullish": bool(is_bullish),
                "trend_hold": bool(trend_hold),
                "eff_direction": str(eff_direction.name),
                "trend_strength": float(trend_strength),
                "scrum_ok": bool(scrum_ok),
                "target_fires": bool(target_fires),
                "bb_above_upper_dt": bool(_bb_above_upper_dt),
                "cb_blocks_scrum": bool(_cb_blocks_scrum),
                "htf_bias_dir": (
                    str(_htf_bias_dir.name) if _htf_bias_dir is not None else None
                ),
                "htf_blocks_scrum": bool(_htf_blocks_scrum),
                "flag_require_ta_bullish": bool(_flag_require_ta_bullish),
                "flag_hold_in_uptrend": bool(_flag_hold_in_uptrend),
                "flag_defer_to_htf": bool(_flag_defer_to_htf),
                "eff_is_bullish": bool(_eff_is_bullish),
                "eff_trend_hold": bool(_eff_trend_hold),
                "eff_htf_blocks": bool(_eff_htf_blocks),
                "hyst_ok_scrum_side": bool(_hyst_ok_scrum_side),
                "hyst_armed_scrum_side": bool(
                    getattr(self, "_hyst_armed_scrum_side", False)
                ),
                "hyst_ref_scrum_side": float(
                    getattr(self, "_hyst_ref_scrum_side", 0.0) or 0.0
                ),
            }
        except Exception as _sfx_exc:  # noqa: BLE001
            if not getattr(self, "_scrum_fixture_warned", False):
                self._scrum_fixture_warned = True
                logger.warning(
                    "Bot %s scrum_fixture capture failed (%s: %s) — "
                    "gate rows will carry a null scrum_fixture until "
                    "this is fixed",
                    self.bot_id,
                    type(_sfx_exc).__name__,
                    _sfx_exc,
                )

        _scrum_ctx = GateContext(
            symbol=str(self.config.symbol),
            ticker_last=float(ticker.last),
            bb_pos=float(bb_pos),
            bb_upper_dt=float(_bb_upper_dt),
            bb_lower_dt=float(_bb_lower_dt),
            delta=float(delta),
            delta_pct=abs(float(delta)),
            below_interval=bool(below_interval),
            is_bullish=bool(is_bullish),
            is_bearish=False,
            trend_hold=bool(trend_hold),
            trend_strength=float(trend_strength),
            eff_direction_name=str(eff_direction.name),
            eff_is_bullish=bool(_eff_is_bullish),
            eff_is_bearish=False,
            eff_trend_hold=bool(_eff_trend_hold),
            eff_htf_blocks_scrum=bool(_eff_htf_blocks),
            eff_htf_blocks_fold=False,
            flag_require_ta_bullish=bool(_flag_require_ta_bullish),
            flag_hold_in_uptrend=bool(_flag_hold_in_uptrend),
            flag_defer_to_htf=bool(_flag_defer_to_htf),
            flag_fold_require_ta_bearish=True,
            flag_fold_defer_to_htf=True,
            bb_above_upper_dt=bool(_bb_above_upper_dt),
            bb_below_lower_dt=False,
            scrum_ok=bool(scrum_ok),
            fold_ok_midline=False,
            target_fires=bool(target_fires),
            cb_blocks_scrum=bool(_cb_blocks_scrum),
            cb_blocks_fold=False,
            hyst_ok_scrum_side=bool(_hyst_ok_scrum_side),
            hyst_ok_fold_side=True,
            hyst_armed_scrum_side=bool(getattr(self, "_hyst_armed_scrum_side", False)),
            hyst_armed_fold_side=False,
            hyst_ref_scrum_side=float(
                getattr(self, "_hyst_ref_scrum_side", 0.0) or 0.0
            ),
            hyst_ref_fold_side=0.0,
            mem253_at_ceiling=False,
            mem253_smart_ceiling_usd=0.0,
            mem253_current_pos=0.0,
            has_fold_tranches=bool(self._fold_tranches),
            n_fold_tranches=len(self._fold_tranches or []),
            htf_bias_name=(
                str(_htf_bias_dir.name) if _htf_bias_dir is not None else None
            ),
            htf_blocks_scrum=bool(_htf_blocks_scrum),
            htf_blocks_fold=False,
            scrumming_interval_pct=float(self.config.scrumming_interval_pct or 0),
            trading_fee_pct=float(getattr(self.config, "trading_fee_pct", 0.6) or 0.6),
            ripe_scrum=bool(_ripe_scrum),
            deep_fold=bool(_deep_fold),
            adx=_extract_signal_detail(summary, "adx", "adx", 0.0),
            efficiency_ratio=_extract_signal_detail(summary, "kaufman_er", "er", 0.0),
            z_score=_extract_signal_detail(summary, "zscore", "z", 0.0),
        )
        _scrum_chain_result = self._scrum_chain.evaluate(_scrum_ctx)
        _stack_spent = 0
        if _scrum_chain_result.should_fire:
            _stack_spent = await self._spend_activated_stack_tranches(
                current_price=float(ticker.last), summary=summary
            )

        if _stack_spent > 0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"SCRUM SERVED BY STACK: {_stack_spent} activated "
                    f"tranche(s) spent under this tick's authorised "
                    f"gate-chain decision. No fresh SCRUM sell this "
                    f"tick -- the tranches carry this Target Delta."
                ),
            )
        elif _scrum_chain_result.should_fire:
            await self._tick_execute_scrum(
                ticker,
                summary,
                bb_result,
                delta,
                delta_pct,
                current_value,
                bb_pos,
                eff_direction,
                eff_confidence,
                _eff_conf_floor,
                position_boost,
                _scrum_chain_result,
            )

        elif delta > 0 and not below_interval and trend_hold:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"HOLD SCRUM: delta +${abs(delta):.4f} — trend hold "
                f"is active at {trend_strength:.0%} bullish",
            )

        elif delta > 0 and not below_interval and not is_bullish:
            # is_bullish is a conjunction, so exactly one half failed here.
            if eff_direction not in (
                SignalDirection.BULLISH,
                SignalDirection.NEUTRAL,
            ):
                _scrum_why = f"TA={eff_direction.name} is not BULLISH or NEUTRAL"
            else:
                _scrum_why = (
                    f"TA={eff_direction.name} but confidence "
                    f"{eff_confidence:.4f} < {_eff_conf_floor:.4f} floor"
                )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"HOLD SCRUM: delta +${abs(delta):.4f} — {_scrum_why}",
            )

        elif (
            delta > 0
            and not below_interval
            and is_bullish
            and not trend_hold
            and scrum_ok
            and target_fires
            and not _bb_above_upper_dt
            and not _cb_blocks_scrum
        ):
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"SCRUM REFUSED (Upper BB Detection Threshold): "
                    f"bb_pos={bb_pos:.3f} < upper_detect={_bb_upper_dt:.3f} "
                    f"(scrum_detect_pct={self.config.scrum_detect_pct}%). "
                    f"Operator rule: SCRUM cannot occur below the Upper "
                    f"BB Detection Threshold. All other gates passed."
                ),
            )
            self._emit_trade_notification(
                "SCRUM",
                "CANCELLED",
                f"bb_pos {bb_pos:.3f} < upper detect {_bb_upper_dt:.3f}",
            )

        elif (
            delta > 0
            and not below_interval
            and is_bullish
            and not trend_hold
            and scrum_ok
            and target_fires
            and _bb_above_upper_dt
            and _cb_blocks_scrum
        ):
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"SCRUM BLOCKED by SOFT CIRCUIT BREAKER: trip @ "
                    f"{self._cb_soft_trip_pct:.2f}% "
                    f"(threshold {self.config.circuit_breaker_soft_pct:.2f}%); "
                    f"{self._cb_soft_cooldown_remaining} candle(s) of cooldown "
                    f"remaining before SCRUM side re-opens."
                ),
            )

        elif (
            delta > 0
            and not below_interval
            and is_bullish
            and not trend_hold
            and scrum_ok
            and target_fires
            and _bb_above_upper_dt
            and not _cb_blocks_scrum
            and _htf_blocks_scrum
        ):
            _bull_w = _htf_bias_detail.get("bull_weight", 0.0)
            _bear_w = _htf_bias_detail.get("bear_weight", 0.0)
            _contribs = _htf_bias_detail.get("contributors", [])
            _summary = (
                ", ".join(
                    f"{c.get('tf', '?')}={c.get('direction', '?')}"
                    f"@{c.get('conf', 0):.2f}"
                    for c in _contribs
                    if not c.get("skipped")
                )
                or "no usable phantoms"
            )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"SCRUM REFUSED (Higher-TF Bias gate): higher-TF "
                    f"phantom consensus is BULLISH "
                    f"(bull weight {_bull_w:.2f} > bear {_bear_w:.2f}). "
                    f"Selling here would fight the higher-TF trend. "
                    f"Contributors: {_summary}."
                ),
            )
            self._emit_trade_notification(
                "SCRUM",
                "CANCELLED",
                f"higher-TF BULLISH bias ({_bull_w:.2f} vs {_bear_w:.2f})",
            )

        _anchor = float(getattr(self, "_anchor_target_balance", self._target_balance))
        _mem253_current_pos = float(self._current_holdings) * float(ticker.last)

        _mem253_at_smart_ceiling = False
        _mem253_smart_ceiling_usd = None
        if getattr(self.config, "position_ceiling_enabled", False):
            try:
                _smart_mult_253 = float(
                    getattr(self.config, "position_ceiling_multiple", 1.0)
                )
                _mem253_smart_ceiling_usd = position_ceiling(_anchor, _smart_mult_253)
                _mem253_at_smart_ceiling = (
                    _mem253_current_pos >= _mem253_smart_ceiling_usd
                )
            except (TypeError, ValueError, AttributeError) as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )

        _mem253_at_ceiling = _mem253_at_smart_ceiling
        if _mem253_at_smart_ceiling and self._fold_tranches:
            self._fold_ceiling_hold_count = (
                getattr(self, "_fold_ceiling_hold_count", 0) + 1
            )
            if self._fold_ceiling_hold_count % 60 == 1:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD HOLD (Position Ceiling): position "
                        f"${_mem253_current_pos:.2f} ≥ Position Ceiling "
                        f"${_mem253_smart_ceiling_usd:.2f} "
                        f"(anchor ${_anchor:.2f} × Ceiling Multiple). "
                        f"Fold branch skipped — bot at maturity, "
                        f"awaiting detonation harvest on bullish vote."
                    ),
                )
        elif not _mem253_at_smart_ceiling:
            self._fold_ceiling_hold_count = 0

        _cb_blocks_fold = self._cb_soft_active_side == "fold"
        _htf_blocks_fold = _htf_bias_dir == SignalDirection.BEARISH
        _flag_fold_require_ta_bearish = bool(
            getattr(self.config, "fold_require_ta_bearish", True)
        )
        _flag_fold_defer_to_htf = bool(getattr(self.config, "fold_defer_to_htf", True))
        _eff_is_bearish = is_bearish if _flag_fold_require_ta_bearish else True
        _eff_htf_blocks_fold = _htf_blocks_fold if _flag_fold_defer_to_htf else False

        _fold_blockers: list[str] = []
        if not self._fold_tranches:
            _fold_blockers.append("no-tranches-queued")
        if not _eff_is_bearish and not _deep_fold:
            _fold_blockers.append(
                f"TA-conf-below-floor(dir={eff_direction.name},"
                f"conf={eff_confidence:.4f}<{_eff_conf_floor:.4f})"
                if eff_direction in (SignalDirection.BEARISH, SignalDirection.NEUTRAL)
                else f"TA-not-bearish(dir={eff_direction.name})"
            )
        if not fold_ok_midline and not _deep_fold:
            _fold_blockers.append(f"fold_ok_midline=False(bb_pos={bb_pos:.2f})")
        if _mem253_at_ceiling:
            _fold_blockers.append("position-ceiling")
        if not _bb_below_lower_dt:
            _fold_blockers.append(
                f"BB-above-lower-detect(bb_pos={bb_pos:.2f}>{_bb_lower_dt:.2f})"
            )
        if _cb_blocks_fold:
            _fold_blockers.append("CB-soft-trip")
        if _eff_htf_blocks_fold:
            _fold_blockers.append("HTF-bearish")
        if not _hyst_ok_fold_side:
            try:
                _ref_px = float(self._hyst_ref_fold_side or 0)
                _eff_pct = float(self.config.scrumming_interval_pct or 0) + float(
                    getattr(self.config, "trading_fee_pct", 0.6) or 0.6
                )
                _required = _ref_px * (1.0 - _eff_pct / 100.0)
                _fold_blockers.append(
                    f"OTD-hyst(px ${ticker.last:.8f} > "
                    f"${_required:.8f}; pivot ${_ref_px:.8f} "
                    f"- {_eff_pct:.2f}%)"
                )
            except Exception:
                _fold_blockers.append("OTD-hyst-armed")
        try:
            self._last_gate_state["fold_armed"] = len(_fold_blockers) == 0
            self._last_gate_state["fold_blockers"] = list(_fold_blockers)
            self._last_gate_state["fold_fixture"] = {
                "has_fold_tranches": bool(self._fold_tranches),
                "n_fold_tranches": len(self._fold_tranches or []),
                "landing_strip": bool(bb_result.landing_strip if bb_result else False),
                "landing_strip_side": str(
                    bb_result.landing_strip_side if bb_result else ""
                )
                or "",
                "landing_strip_candles": int(
                    bb_result.landing_strip_candles if bb_result else 0
                ),
                "is_bearish": bool(is_bearish),
                "eff_direction": str(eff_direction.name),
                "fold_ok_midline": bool(fold_ok_midline),
                "mem253_at_ceiling": bool(_mem253_at_ceiling),
                "mem253_smart_ceiling_usd": float(
                    _mem253_smart_ceiling_usd if _mem253_smart_ceiling_usd else 0.0
                ),
                "mem253_current_pos": float(
                    _mem253_current_pos if _mem253_current_pos else 0.0
                ),
                "bb_below_lower_dt": bool(_bb_below_lower_dt),
                "cb_blocks_fold": bool(_cb_blocks_fold),
                "htf_blocks_fold": bool(_htf_blocks_fold),
                "flag_fold_require_ta_bearish": bool(_flag_fold_require_ta_bearish),
                "flag_fold_defer_to_htf": bool(_flag_fold_defer_to_htf),
                "eff_is_bearish": bool(_eff_is_bearish),
                "eff_htf_blocks_fold": bool(_eff_htf_blocks_fold),
                "hyst_ok_fold_side": bool(_hyst_ok_fold_side),
                "hyst_armed_fold_side": bool(
                    getattr(self, "_hyst_armed_fold_side", False)
                ),
                "hyst_ref_fold_side": float(
                    getattr(self, "_hyst_ref_fold_side", 0.0) or 0.0
                ),
            }
        except Exception as _sup:
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        from .otd_math import (
            fold_rebuy_factor_from_pct,
            minimum_opposing_trade_distance_pct,
        )

        _otd_pct_for_gate = 0.0
        try:
            _otd_pct_for_gate = minimum_opposing_trade_distance_pct(
                getattr(self.config, "scrumming_interval_pct", 0) or 0,
                getattr(self.config, "trading_fee_pct", 0.6) or 0.6,
            )
        except (TypeError, ValueError):
            _otd_pct_for_gate = 0.0
        _otd_factor = fold_rebuy_factor_from_pct(_otd_pct_for_gate)

        self._tick_fold_diagnostics(
            ticker,
            bb_pos,
            is_bearish,
            fold_ok_midline,
            _bb_below_lower_dt,
            _fold_blockers,
            _otd_pct_for_gate,
            _otd_factor,
        )

        _fold_ctx = GateContext(
            symbol=str(self.config.symbol),
            ticker_last=float(ticker.last),
            bb_pos=float(bb_pos),
            bb_upper_dt=float(_bb_upper_dt),
            bb_lower_dt=float(_bb_lower_dt),
            delta=float(delta),
            delta_pct=abs(float(delta)),
            below_interval=bool(below_interval),
            is_bullish=bool(is_bullish),
            is_bearish=bool(is_bearish),
            trend_hold=bool(trend_hold),
            trend_strength=float(trend_strength),
            eff_direction_name=str(eff_direction.name),
            eff_is_bullish=bool(_eff_is_bullish),
            eff_is_bearish=bool(_eff_is_bearish),
            eff_trend_hold=bool(_eff_trend_hold),
            eff_htf_blocks_scrum=bool(_eff_htf_blocks),
            eff_htf_blocks_fold=bool(_eff_htf_blocks_fold),
            flag_require_ta_bullish=bool(_flag_require_ta_bullish),
            flag_hold_in_uptrend=bool(_flag_hold_in_uptrend),
            flag_defer_to_htf=bool(_flag_defer_to_htf),
            flag_fold_require_ta_bearish=bool(_flag_fold_require_ta_bearish),
            flag_fold_defer_to_htf=bool(_flag_fold_defer_to_htf),
            bb_above_upper_dt=bool(_bb_above_upper_dt),
            bb_below_lower_dt=bool(_bb_below_lower_dt),
            scrum_ok=bool(scrum_ok),
            fold_ok_midline=bool(fold_ok_midline),
            target_fires=bool(target_fires),
            cb_blocks_scrum=bool(_cb_blocks_scrum),
            cb_blocks_fold=bool(_cb_blocks_fold),
            hyst_ok_scrum_side=bool(_hyst_ok_scrum_side),
            hyst_ok_fold_side=bool(_hyst_ok_fold_side),
            hyst_armed_scrum_side=bool(getattr(self, "_hyst_armed_scrum_side", False)),
            hyst_armed_fold_side=bool(getattr(self, "_hyst_armed_fold_side", False)),
            hyst_ref_scrum_side=float(
                getattr(self, "_hyst_ref_scrum_side", 0.0) or 0.0
            ),
            hyst_ref_fold_side=float(getattr(self, "_hyst_ref_fold_side", 0.0) or 0.0),
            mem253_at_ceiling=bool(_mem253_at_ceiling),
            mem253_smart_ceiling_usd=float(
                _mem253_smart_ceiling_usd if _mem253_smart_ceiling_usd else 0.0
            ),
            mem253_current_pos=float(
                _mem253_current_pos if _mem253_current_pos else 0.0
            ),
            has_fold_tranches=bool(self._fold_tranches),
            n_fold_tranches=len(self._fold_tranches or []),
            htf_bias_name=(
                str(_htf_bias_dir.name) if _htf_bias_dir is not None else None
            ),
            htf_blocks_scrum=bool(_htf_blocks_scrum),
            htf_blocks_fold=bool(_htf_blocks_fold),
            scrumming_interval_pct=float(self.config.scrumming_interval_pct or 0),
            trading_fee_pct=float(getattr(self.config, "trading_fee_pct", 0.6) or 0.6),
            ripe_scrum=bool(_ripe_scrum),
            deep_fold=bool(_deep_fold),
            z_score=_extract_signal_detail(summary, "zscore", "z", 0.0),
        )
        _fold_chain_result = self._fold_chain.evaluate(_fold_ctx)
        # Both banks are fresh here: the scrum blockers are written above and
        # the fold blockers just above this line, so one line carries the tick.
        self._emit_gate_light_line(
            _scrum_chain_result, _fold_chain_result, summary, float(ticker.last)
        )
        if _fold_chain_result.should_fire:
            if await self._tick_execute_fold(
                ticker, summary, delta, _otd_factor, _fold_chain_result
            ):
                return

        elif self._fold_tranches and not is_bearish:
            _dir_ok = eff_direction in (
                SignalDirection.BEARISH,
                SignalDirection.NEUTRAL,
            )
            if not _dir_ok:
                _why = f"TA={eff_direction.name} is not BEARISH or " f"NEUTRAL"
            elif eff_confidence < _eff_conf_floor:
                _why = (
                    f"TA={eff_direction.name} but confidence "
                    f"{eff_confidence:.4f} < {_eff_conf_floor:.4f} "
                    f"floor"
                )
            else:
                _why = (
                    f"TA={eff_direction.name}, confidence "
                    f"{eff_confidence:.2f} — blocked by an override, "
                    f"not by direction or confidence"
                )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"HOLD FOLD: {len(self._fold_tranches)} tranche(s) "
                f"(${self._fold_queue_usd:.4f}) queued — {_why}",
            )

        elif self._fold_tranches and is_bearish and not fold_ok_midline:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"HOLD FOLD: BEARISH and {len(self._fold_tranches)} "
                f"tranche(s) queued but BB position {bb_pos:.0%} > 50% "
                f"(bb_midline_gate blocking fold — wait for price "
                f"to drop below midline)",
            )

        elif (
            self._fold_tranches
            and is_bearish
            and fold_ok_midline
            and not _mem253_at_ceiling
            and not _bb_below_lower_dt
            and not _cb_blocks_fold
        ):
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD REFUSED (Lower BB Detection Threshold): "
                    f"bb_pos={bb_pos:.3f} > lower_detect={_bb_lower_dt:.3f} "
                    f"(scrum_detect_pct={self.config.scrum_detect_pct}%). "
                    f"Operator rule: FOLD cannot occur above the Lower "
                    f"BB Detection Threshold. All other gates passed."
                ),
            )
            self._emit_trade_notification(
                "FOLD",
                "CANCELLED",
                f"bb_pos {bb_pos:.3f} > lower detect {_bb_lower_dt:.3f}",
            )

        elif (
            self._fold_tranches
            and is_bearish
            and fold_ok_midline
            and not _mem253_at_ceiling
            and _bb_below_lower_dt
            and _cb_blocks_fold
        ):
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD BLOCKED by SOFT CIRCUIT BREAKER: trip @ "
                    f"{self._cb_soft_trip_pct:.2f}% "
                    f"(threshold {self.config.circuit_breaker_soft_pct:.2f}%); "
                    f"{self._cb_soft_cooldown_remaining} candle(s) of cooldown "
                    f"remaining before FOLD side re-opens."
                ),
            )

        elif (
            self._fold_tranches
            and is_bearish
            and fold_ok_midline
            and not _mem253_at_ceiling
            and _bb_below_lower_dt
            and not _cb_blocks_fold
            and _htf_blocks_fold
        ):
            _bull_w = _htf_bias_detail.get("bull_weight", 0.0)
            _bear_w = _htf_bias_detail.get("bear_weight", 0.0)
            _contribs = _htf_bias_detail.get("contributors", [])
            _summary = (
                ", ".join(
                    f"{c.get('tf', '?')}={c.get('direction', '?')}"
                    f"@{c.get('conf', 0):.2f}"
                    for c in _contribs
                    if not c.get("skipped")
                )
                or "no usable phantoms"
            )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD REFUSED (Higher-TF Bias gate): higher-TF "
                    f"phantom consensus is BEARISH "
                    f"(bear weight {_bear_w:.2f} > bull {_bull_w:.2f}). "
                    f"Buying here would catch a falling knife. "
                    f"Contributors: {_summary}."
                ),
            )
            self._emit_trade_notification(
                "FOLD",
                "CANCELLED",
                f"higher-TF BEARISH bias ({_bear_w:.2f} vs {_bull_w:.2f})",
            )

        # Re-read after the fold above moved ``_current_holdings`` and the target.
        _hedge_gap_usd = self._target_balance - (
            self._current_holdings * ticker.last * float(self._quote_to_usd or 1.0)
        )
        if (
            self.config.hedge_rebalance_active
            and self._hedge_bal > 0.01
            and _hedge_gap_usd > 0
            and not is_bullish
            and bb_pos < 0.40
        ):
            _gap = _hedge_gap_usd
            if _gap / max(self._target_balance, 1e-9) >= 0.01:
                _use = min(self._hedge_bal * 0.5, _gap)
                if _use > 0.01:
                    hedge_fill = await self._execute_buy(
                        _use,
                        ticker.last,
                        summary,
                        trace_context={
                            "path": "hedge_replenish",
                            "hedge_bal": f"${self._hedge_bal:.4f}",
                            "gap": f"${_gap:.4f}",
                            "use": f"${_use:.4f}",
                        },
                    )
                    if hedge_fill is None or hedge_fill <= 0:
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"HEDGE ABORTED: buy failed at "
                                f"${ticker.last:.8f} (gap=${_gap:.4f}, "
                                f"reserve=${self._hedge_bal:.2f} "
                                f"unchanged). No state update. "
                                f"Retry next tick if gates still pass."
                            ),
                        )
                    else:
                        _hedge_asset = _use / hedge_fill
                        self._main_lots.append(
                            {
                                "units": _hedge_asset,
                                "initial_buy_price": hedge_fill,
                            }
                        )
                        self._hedge_bal -= _use
                        self._hedge_trades += 1
                        self.stats.trade_volume += _use
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=f"HEDGE REBALANCE: spent ${_use:.4f} "
                            f"(reserve ${self._hedge_bal:.2f} remaining) "
                            f"→ bought {_hedge_asset:.6f} @ ${hedge_fill:.8f} "
                            f"(intended ${ticker.last:.8f}), "
                            f"gap=${_gap:.4f} ({_gap/max(self._target_balance, 1e-9)*100:.1f}%), "
                            f"bb={bb_pos:.0%}. Trade #{self._hedge_trades}",
                        )
                        self._bus.emit(
                            "trade.filled",
                            bot_id=self.bot_id,
                            side="buy",
                            type="HEDGE",
                            price=hedge_fill,
                            amount=_hedge_asset,
                            usd=_use,
                            size=_use,
                            profit=0,
                            **self._fill_fee_fields(hedge_fill),
                        )
                        self._emit_voting_panel_snapshot_at_fire(
                            side="BUY", trade_action="HEDGE"
                        )
                        self._emit_gate_decision_at_fire(
                            side="BUY", trade_action="HEDGE"
                        )
                        self._last_trade_price = hedge_fill

        await self._tick_distribute(ticker, summary, bb_result, is_bullish)

        self._last_price = ticker.last

    async def _check_detonation_trigger(self, ticker) -> bool:
        """Check the higher-timeframe signal for a detonation trigger, edge-triggered
        and rate-limited to ``_DETONATION_CHECK_INTERVAL_S``.

        Requires:
            ``detonation_enabled``, a current value above the anchor, and
            BULLISH at or above ``detonation_confidence_min``. The latch and
            the rate limit are persisted state that survives a restart.

        Returns:
            True if the trigger fired this call, False otherwise.

        """
        if not getattr(self.config, "detonation_enabled", False):
            return False

        price = getattr(ticker, "last", None) or 0.0
        if price <= 0:
            return False
        current_value = priced_usd(
            self._current_holdings, price, float(self._quote_to_usd or 1.0)
        )
        if current_value <= self._anchor_target_balance:
            return False

        now = time.time()
        elapsed = now - self._detonation_last_check_ts
        if elapsed < _DETONATION_CHECK_INTERVAL_S:
            return False
        self._detonation_last_check_ts = now

        tf = getattr(self.config, "detonation_timeframe", "1d") or "1d"
        # One unobserved detonation candle retires the latch; a shorter gap keeps it.
        latch_ttl = max(
            float(TIMEFRAME_SECONDS.get(tf, TIMEFRAME_SECONDS["1d"])),
            _DETONATION_LATCH_MIN_TTL_S,
        )
        if elapsed >= latch_ttl:
            self._detonation_last_signal_bullish = False

        try:
            candles = await self.exchange.get_ohlcv(self.config.symbol, tf, limit=100)
        except Exception as exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"DETONATION check: failed to fetch {tf} "
                    f"candles: {exc}. Will retry in 1h."
                ),
            )
            return False

        if not candles or len(candles) < MIN_CANDLES_FOR_TA:
            return False

        try:
            engine = VotingEngine()
            parsed = candles_from_raw(candles)
            summary = engine.compute_all(parsed, tf)
        except Exception as exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"DETONATION check: TA engine failed: {exc}. " f"Will retry in 1h."
                ),
            )
            return False

        conf_min = float(getattr(self.config, "detonation_confidence_min", 0.75))
        is_bullish = (
            summary.consensus_direction == SignalDirection.BULLISH
            and summary.consensus_confidence >= conf_min
        )

        fired = is_bullish and not self._detonation_last_signal_bullish
        self._detonation_last_signal_bullish = is_bullish

        if fired:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"DETONATION TRIGGERED: {tf} BULLISH at "
                    f"confidence {summary.consensus_confidence:.2f} "
                    f"(>={conf_min:.2f}). Harvesting everything "
                    f"above anchor ${self._anchor_target_balance:.2f}."
                ),
            )
        elif is_bullish:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"DETONATION: {tf} still BULLISH conf="
                    f"{summary.consensus_confidence:.2f}; no "
                    f"edge transition, holding."
                ),
            )

        return fired

    def clear_stack_tranches(self, reason: str = "operator") -> dict:
        """Discard this bot's standing Stack tranches, trading nothing.

        Kept:
            A Visible-mode tranche with ``status == "pending"`` and an
            ``order_id`` holds a resting LIMIT SELL, so it is kept and counted.

        Untouched:
            Holdings, ``_main_lots``, the fold queue, wire credits, the target
            and the anchor. Every discarded record moves ``_stack_discarded``
            and nothing else, keeping ``created - discarded == standing`` true.

        Returns:
            A report of what was discarded. Never raises.

        """
        _keep: list[dict] = []
        _drop: list[dict] = []
        for _t in list(self._stack_tranches or []):
            if _t.get("status") == "pending" and _t.get("order_id"):
                _keep.append(_t)
            else:
                _drop.append(_t)

        # An unreadable size is counted in ``_size_unreadable``, not skipped.
        _size = 0.0
        _size_unreadable = 0
        for _t in _drop:
            _one = as_finite_float(_t.get("size", 0))
            if _one is None:
                _size_unreadable += 1
            else:
                _size += _one

        report = {
            "bot_id": self.bot_id,
            "symbol": getattr(self.config, "symbol", ""),
            "count": len(_drop),
            "kept_live_order": len(_keep),
            "size": round(_size, 8),
            "size_unreadable": _size_unreadable,
            "reason": str(reason),
        }
        if not _drop:
            return report

        self._stack_tranches = _keep
        self._stack_discarded = (
            int(as_finite_float(getattr(self, "_stack_discarded", 0)) or 0.0)
            + report["count"]
        )

        _kept_note = ""
        if report["kept_live_order"]:
            _kept_note = (
                f" {report['kept_live_order']} tranche(s) KEPT: they "
                f"hold resting exchange orders, and removing a record "
                f"that owns a live order would strand it."
            )
        _unreadable_note = ""
        if _size_unreadable:
            _unreadable_note = (
                f" {_size_unreadable} discarded record(s) carried an "
                f"unreadable size and sit outside that total."
            )
        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"STACK TRANCHES CLEARED ({reason}): discarded "
                    f"{report['count']} tranche(s) covering "
                    f"{report['size']:.8f} base units. No order was "
                    f"placed or cancelled; holdings, cost basis and "
                    f"target balance are "
                    f"unchanged.{_kept_note}{_unreadable_note}"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("clear_stack_tranches: log emit failed: %s", exc)

        logger.info(
            "Bot %s: cleared %d stack tranche(s) (%.8f units, %d "
            "unreadable size, %d kept holding live orders) reason=%s",
            self.bot_id,
            report["count"],
            report["size"],
            _size_unreadable,
            report["kept_live_order"],
            reason,
        )
        return report

    def clear_stack_lifetime_counters(self, reason: str = "operator") -> dict:
        """Reset ``_stack_created`` and ``_stack_discarded`` to zero.

        Also sets:
            ``_stack_counters_reset_ts``, so a cleared bot is distinguishable
            from one that never opened a stack. A bot whose two counters
            already read zero is left alone.

        Untouched:
            The standing ``_stack_tranches``, the fold counters, wire credits,
            holdings, lots and the target.

        Returns:
            A report of the two values destroyed. Never raises.

        """
        _before = {
            "created": int(as_finite_float(getattr(self, "_stack_created", 0)) or 0.0),
            "discarded": int(
                as_finite_float(getattr(self, "_stack_discarded", 0)) or 0.0
            ),
        }
        report = {
            "bot_id": self.bot_id,
            "symbol": getattr(self.config, "symbol", ""),
            "before": dict(_before),
            "cleared": sum(_before.values()),
            "open_tranches": len(self._stack_tranches or []),
            "reset_ts": float(
                as_finite_float(getattr(self, "_stack_counters_reset_ts", 0.0)) or 0.0
            ),
            "reason": str(reason),
        }
        if report["cleared"] <= 0:
            return report

        self._stack_created = 0
        self._stack_discarded = 0
        self._stack_counters_reset_ts = float(time.time())
        report["reset_ts"] = self._stack_counters_reset_ts

        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"LIFETIME STACK COUNTERS CLEARED ({reason}): opened "
                    f"{_before['created']}, discarded "
                    f"{_before['discarded']} are now zero. No tranche and "
                    f"no holding was touched; {report['open_tranches']} "
                    f"stack tranche(s) remain in the ledger."
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("clear_stack_lifetime_counters: log emit failed: %s", exc)

        logger.info(
            "Bot %s: cleared lifetime stack counters (opened=%d "
            "discarded=%d) reason=%s open_tranches=%d",
            self.bot_id,
            _before["created"],
            _before["discarded"],
            reason,
            report["open_tranches"],
        )
        return report

    async def _open_stack_from_scrum(
        self,
        scrum_price: float,
        scrum_size: float,
        summary: Optional[VotingSummary] = None,
        origin: str = "scrum",
    ) -> int:
        """Split a SCRUM decision into Stack tranches instead of one immediate sell.

        Returns:
            The number of tranches created (>=1). Populates
            ``self._stack_tranches`` and records ``origin`` on every tranche.

        """
        from .stack_math import (
            split_scrum_into_tranches,
        )

        _interval = float(getattr(self.config, "scrumming_interval_pct", 0) or 0)
        _fee = float(getattr(self.config, "trading_fee_pct", 0.6) or 0.6)
        min_opposing_pct = _interval + _fee

        n_target = int(getattr(self.config, "stack_tranche_count_target", 3) or 3)
        split_dist = float(getattr(self.config, "split_distance", 1.0) or 1.0)
        spacing = str(getattr(self.config, "stack_spacing_mode", "linear") or "linear")
        _rules = await self._get_market_rules(self.config.symbol)
        min_order = float(_rules.smallest_amount or 0.0)

        try:
            tranches = split_scrum_into_tranches(
                scrum_price=scrum_price,
                scrum_size=scrum_size,
                n_target=n_target,
                split_distance_pct=split_dist,
                spacing_mode=spacing,
                min_opposing_pct=min_opposing_pct,
                min_order_size=min_order,
            )
        except ValueError as e:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"STACK OPEN FAILED: split_scrum_into_tranches "
                    f"rejected inputs: {e}. Stack not opened."
                ),
            )
            logger.warning("Bot %s stack open failed: %s", self.bot_id, e)
            return 0

        import time as _t

        now = _t.time()
        try:
            _open_conf = float(getattr(summary, "consensus_confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            _open_conf = 0.0
        _open_dir = str(getattr(summary, "consensus_direction", "stack") or "stack")
        _visible = not self._invisible
        _aggressive = bool(getattr(self, "_aggressive", False))
        _order_type_for_visible = (
            OrderType.IOC_LIMIT if _aggressive else OrderType.LIMIT
        )

        for t in tranches:
            entry = {
                "index": t.index,
                "price": t.price,
                "size": t.size,
                "status": "pending",
                "opened_ts": now,
                "opened_at_scrum_price": scrum_price,
                "origin": origin,
                "order_id": None,
                "visible": _visible,
                "open_confidence": _open_conf,
                "open_direction": _open_dir,
                "activated": False,
                "activated_ts": 0.0,
            }
            if _visible:
                try:
                    order = await self.guarded_place_order(
                        symbol=self.config.symbol,
                        side=OrderSide.SELL,
                        order_type=_order_type_for_visible,
                        amount=float(t.size),
                        price=float(t.price),
                    )
                    if order is not None:
                        entry["order_id"] = getattr(order, "id", None)
                        entry["order_type_placed"] = _order_type_for_visible.value
                    else:
                        entry["status"] = "cancelled"
                        entry["cancel_reason"] = "exchange returned no order"
                except Exception as _place_exc:
                    logger.warning(
                        "Bot %s stack tranche %d placement failed: %s",
                        self.bot_id,
                        t.index,
                        _place_exc,
                    )
                    entry["status"] = "cancelled"
                    entry["cancel_reason"] = (
                        f"{type(_place_exc).__name__}: {_place_exc}"
                    )
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"STACK TRANCHE {t.index} PLACEMENT FAILED: "
                            f"{entry['cancel_reason']}. "
                            f"Tranche cancelled."
                        ),
                    )
            self._stack_tranches.append(entry)
            self._stack_created += 1

        _mode_label = "VISIBLE" if _visible else "INVISIBLE"
        _agg_label = " (AGGRESSIVE/IOC)" if _visible and _aggressive else ""
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"STACK OPENED [{_mode_label}{_agg_label}] "
                f"({len(tranches)} tranches) from {origin} @ "
                f"${scrum_price:.8f}, size {scrum_size:.6f}. "
                f"Prices: {[f'${t.price:.8f}' for t in tranches[:5]]}"
                f"{'…' if len(tranches) > 5 else ''}"
            ),
        )
        return len(tranches)

    async def _reconcile_stack_tranches_visible(self) -> int:
        """Visible-mode Stack reconciliation, once per tick.

        Cross-references:
            ``_stack_tranches`` order_ids against the exchange's open orders,
            fetching the terminal state of any that no longer appear, then
            updating status and fill price.

        Returns:
            0 when not visible mode, when there are no pending tranches, when
            stack_mode is off, or when the exchange lacks get_open_orders.

        """
        if self._invisible:
            return 0
        if not getattr(self.config, "stack_mode", False):
            return 0
        pending_visible = [
            t
            for t in self._stack_tranches
            if t.get("status") == "pending" and t.get("visible") and t.get("order_id")
        ]
        if not pending_visible:
            return 0
        if not hasattr(self.exchange, "get_open_orders"):
            return 0

        try:
            open_orders = await self.exchange.get_open_orders(symbol=self.config.symbol)
        except Exception as exc:
            logger.warning(
                "Bot %s stack visible reconcile: get_open_orders failed: %s",
                self.bot_id,
                exc,
            )
            return 0

        open_ids = {getattr(o, "id", None) for o in (open_orders or [])}
        settled = 0
        for t in pending_visible:
            oid = t["order_id"]
            if oid in open_ids:
                continue
            try:
                order = await self.exchange.get_order(
                    order_id=oid, symbol=self.config.symbol
                )
            except Exception as exc:
                logger.warning(
                    "Bot %s stack visible reconcile: get_order(%s) failed: %s",
                    self.bot_id,
                    oid,
                    exc,
                )
                continue
            status = getattr(order, "status", None)
            status_val = getattr(status, "value", status)
            _filled = float(getattr(order, "filled", 0) or 0)
            _avg = (
                getattr(order, "average", None)
                or getattr(order, "price", None)
                or t["price"]
            )
            if _filled > 0:
                t["status"] = "filled"
                t["fill_price"] = float(_avg or t["price"])
                t["filled_amount"] = _filled
                settled += 1
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"STACK TRANCHE {t['index']} FILLED [VISIBLE] "
                        f"@ ${float(_avg or t['price']):.8f} "
                        f"({_filled:.6f}/{t['size']:.6f})"
                    ),
                )
            else:
                t["status"] = "cancelled"
                t["cancel_reason"] = f"exchange status={status_val!r}, filled=0"
                settled += 1
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"STACK TRANCHE {t['index']} CANCELLED "
                        f"externally (order {oid} closed with 0 fill)"
                    ),
                )
        return settled

    async def _reconcile_stack_tranches_invisible(self, current_price: float) -> int:
        """Stage one of the two-stage Stack rule: a crossed price threshold
        ACTIVATES a tranche without spending it.

        Returns:
            The number of tranches newly activated this tick. Activation is
            sticky and ``status`` stays "pending", so the ledger's three
            states are unchanged; ``_spend_activated_stack_tranches`` spends.

        """
        if not self._invisible:
            return 0
        if not getattr(self.config, "stack_mode", False):
            return 0
        if not self._stack_tranches:
            return 0
        if not (current_price and current_price > 0):
            return 0

        import time as _t

        activated = 0
        for t in self._stack_tranches:
            if t.get("status") != "pending":
                continue
            if t.get("activated"):
                continue
            if current_price < float(t["price"]):
                continue
            t["activated"] = True
            t["activated_ts"] = _t.time()
            t["activated_price"] = float(current_price)
            activated += 1
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"STACK TRANCHE {t['index']} ACTIVATED @ "
                    f"${float(current_price):.8f} (threshold "
                    f"${float(t['price']):.8f}, size "
                    f"{float(t['size']):.6f}). Candidate only -- it is "
                    f"spent when the SCRUM gate chain authorises a "
                    f"sell, and not before."
                ),
            )
        return activated

    async def _spend_activated_stack_tranches(
        self,
        current_price: float,
        summary: Optional[VotingSummary] = None,
    ) -> int:
        """Stage two: spend the tranches the price threshold already activated.

        Args:
          current_price: this tick's ``ticker.last``, not the tranche's
                         threshold, because invisible mode sells at market.
          summary: the live vote that authorised the sell; a tranche's
                   ``open_confidence`` and ``open_direction`` are used only
                   when no live vote is supplied.

        Returns:
          The number of tranches spent this tick. A tranche not spent keeps
          ``status == "pending"`` and ``activated == True``.

        """
        if not self._invisible:
            return 0
        if not getattr(self.config, "stack_mode", False):
            return 0
        if not self._stack_tranches:
            return 0
        if not (current_price and current_price > 0):
            return 0

        spent = 0
        for t in self._stack_tranches:
            if t.get("status") != "pending":
                continue
            if not t.get("activated"):
                continue
            _vote = summary
            if _vote is None:
                _vote = StackTrancheSummary(
                    consensus_confidence=float(t.get("open_confidence", 0.0) or 0.0),
                    consensus_direction=str(
                        t.get("open_direction", "stack") or "stack"
                    ),
                )
            try:
                fill = await self._execute_sell(
                    amount=float(t["size"]),
                    price=float(current_price),
                    summary=_vote,
                    bypass_stack=True,
                )
            except Exception as exc:
                logger.warning(
                    "Bot %s stack tranche %s spend raised: %s",
                    self.bot_id,
                    t.get("index"),
                    exc,
                )
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"STACK TRANCHE {t['index']} SPEND FAILED: "
                        f"{type(exc).__name__}: {exc}. Tranche stays "
                        f"pending and activated -- retried on the next "
                        f"authorised tick."
                    ),
                )
                continue
            if fill is None or float(fill) <= 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"STACK TRANCHE {t['index']} NOT SPENT: "
                        f"_execute_sell returned no fill. Tranche stays "
                        f"pending and activated -- retried on the next "
                        f"authorised tick."
                    ),
                )
                continue
            t["status"] = "filled"
            t["fill_price"] = float(fill)
            spent += 1
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"STACK TRANCHE {t['index']} SPENT @ "
                    f"${float(fill):.8f} (threshold "
                    f"${float(t['price']):.8f}, size "
                    f"{float(t['size']):.6f}) under an authorised "
                    f"SCRUM gate-chain decision."
                ),
            )
        return spent

    def memorize_to_grid(self) -> list[dict]:
        """Convert memorised scrumming trades into grid-style buy/sell pairs."""
        if not self._memorised_trades:
            return []

        levels = []
        buys = [t for t in self._memorised_trades if t.side == "buy"]
        sells = [t for t in self._memorised_trades if t.side == "sell"]

        used_sells = set()
        for buy in buys:
            best_sell = None
            best_dist = float("inf")
            for i, sell in enumerate(sells):
                if i in used_sells:
                    continue
                if sell.price > buy.price:
                    dist = sell.price - buy.price
                    if dist < best_dist:
                        best_dist = dist
                        best_sell = (i, sell)
            if best_sell:
                idx, sell = best_sell
                used_sells.add(idx)
                levels.append(
                    {
                        "buy_price": buy.price,
                        "sell_price": sell.price,
                        "position_size": buy.amount * buy.price,
                        "is_extended": False,
                        "organic": True,
                    }
                )

        logger.info(
            "Bot %s memorised %d trades → %d grid levels",
            self.bot_id,
            len(self._memorised_trades),
            len(levels),
        )
        return levels

    def _main_lots_invariant_ok(self, tol: float = 1e-6) -> bool:
        """True iff sum(lot['units']) == _current_holdings within tolerance."""
        lots_sum = sum(l["units"] for l in self._main_lots)
        return abs(lots_sum - self._current_holdings) <= tol

    def _main_lots_summary(self) -> dict:
        """Snapshot of the lot and tranche counters for debugging."""
        return {
            "main_lots_count": len(self._main_lots),
            "main_lots_units_sum": sum(l["units"] for l in self._main_lots),
            "main_lots_min_ibp": (
                min((l["initial_buy_price"] for l in self._main_lots), default=0.0)
            ),
            "main_lots_max_ibp": (
                max((l["initial_buy_price"] for l in self._main_lots), default=0.0)
            ),
            "fold_tranches_count": len(self._fold_tranches),
            "fold_tranches_usd_sum": sum(t["usd"] for t in self._fold_tranches),
            "fold_tranches_units_sum": sum(t["units"] for t in self._fold_tranches),
            "current_holdings": self._current_holdings,
            "invariant_ok": self._main_lots_invariant_ok(),
        }

    def get_multi_tf_summary(self) -> dict:
        """Return multi-timeframe voting summary from all phantoms."""
        return self._coordinator.get_multi_tf_summary(self.bot_id)

    def get_phantom_statuses(self) -> list[dict]:
        """Return status of all phantom bots."""
        return [p.get_status() for p in self._phantom_mgr.get_phantoms(self.bot_id)]

    async def stop(self) -> None:
        """Stop this bot and all its phantom bots."""
        self._release_capital_reservation()
        await self._phantom_mgr.stop_all(self.bot_id)
        self._phantom_mgr.remove_set(self.bot_id)
        await super().stop()

    async def _spawn_stack_from_fold(
        self,
        fold_price: float,
        fold_size: float,
        summary: Optional[VotingSummary] = None,
        path: str = "",
    ) -> int:
        """A filled FOLD spawns the Stack ladder above it.

        Returns:
            How many Stack tranches were created, 0 when none were.

        """
        if path not in ("fold_rebuy", "manual_tranche_fire"):
            return 0
        if not getattr(self.config, "stack_mode", False):
            return 0
        if not (fold_price and fold_price > 0):
            return 0
        if not (fold_size and fold_size > 0):
            return 0
        try:
            opened = await self._open_stack_from_scrum(
                scrum_price=float(fold_price),
                scrum_size=float(fold_size),
                summary=summary,
                origin="fold",
            )
        except Exception as _spawn_exc:
            logger.error(
                "Bot %s fold-spawned stack FAILED after a filled buy "
                "(%s: %s); the fill stands, no tranches were opened",
                self.bot_id,
                type(_spawn_exc).__name__,
                _spawn_exc,
            )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD STACK SPAWN FAILED: "
                    f"{type(_spawn_exc).__name__}: {_spawn_exc}. "
                    f"The fold fill stands; no Stack tranches were "
                    f"opened above it."
                ),
            )
            return 0
        if opened > 0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD SPAWNED STACK: {opened} tranche(s) above "
                    f"a fold filled at ${float(fold_price):.8f} "
                    f"(size {float(fold_size):.6f}, path {path})."
                ),
            )
        return opened

    def open_extractor_tranches(self) -> list[dict]:
        """List the Extractor Tranches held against this bot's asset.

        Returns:
            An empty list when no manager is attached or no child matches; a
            child that raises is logged and skipped.

        """
        manager = getattr(self, "_bot_manager", None)
        if manager is None:
            return []
        lister = getattr(manager, "list_extractor_children_for_parent", None)
        if not callable(lister):
            return []
        try:
            children = lister(self)
        except Exception as _list_exc:
            logger.warning(
                "Bot %s could not list Extractor children: %s: %s",
                self.bot_id,
                type(_list_exc).__name__,
                _list_exc,
            )
            return []
        rows: list[dict] = []
        for child_id, child in children or []:
            reader = getattr(child, "extractor_tranche_rows", None)
            if not callable(reader):
                continue
            try:
                child_rows = reader()
            except Exception as _row_exc:
                logger.warning(
                    "Bot %s: Extractor child %s failed to report its "
                    "tranches: %s: %s — skipped, other children still "
                    "listed.",
                    self.bot_id,
                    child_id,
                    type(_row_exc).__name__,
                    _row_exc,
                )
                continue
            for row in child_rows or []:
                if isinstance(row, dict):
                    rows.append(dict(row))
        rows.sort(key=lambda r: str(r.get("tranche_id", "")))
        return rows

    def set_ta_weights(self, weights: Optional[dict[str, float]] = None) -> None:
        """Vote on ``weights`` from the next tick, without a rebuild.

        ``_ta_weights`` also seeds a phantom set, so a set created after this
        call carries the new figures while one already running keeps its own.
        Nothing calls this on its own: the Settings Save button is the route.
        """
        self._ta_weights = dict(weights) if weights else None
        self._voting_engine.set_weights(self._ta_weights)
        logger.info(
            "Bot %s: TA weights taken (%d names) — from the next tick",
            self.bot_id,
            0 if not self._ta_weights else len(self._ta_weights),
        )
