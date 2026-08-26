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

Fold ONLY executes when price < fold_ref, which guarantees more asset is
bought back than was sold; do not change that condition.

The simulator holds a mirrored copy of this logic in
``src/gui/simulator.py::_sim_scrumming_tick``; changes here must be
mirrored there (known technical debt). See ARCHITECTURE.md for the full
invariants list.

Implements the strategy with a 7-indicator TA engine (confidence/voting),
Phantom Balance multi-timeframe analysis, higher-timeframe
prioritization, the Memorize grid-conversion function, Profit Folding and
Upward Distribution, and Extended Position creation.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..exchange.base import ExchangeInterface

from ..exchange.base import OrderSide, OrderType
from .wallet_reservations import get_wallet_reservations, wallet_key
from .target_bands import at_target_dust_band, manual_fire_dust_band
from .bot_container import (
    BotContainer,
    BotConfig,
    BotMode,
    BotState,
    as_finite_float,
    despawn_threshold_days,
)
from .ta_engine import (
    VotingEngine,
    VotingSummary,
    SignalDirection,
    candles_from_raw,
    detect_bb_proximity,
    BBProximityResult,
    detect_landing_strip_v2,
)
from .phantom_balance import (
    PhantomBalanceManager,
    TimeframeCoordinator,
)

from .gate_chain import (
    GateContext,
    build_scrumming_scrum_chain,
    build_scrumming_fold_chain,
)
from .scrumming import (
    CapitalReservationMixin,
    CircuitBreakerMixin,
    SnapshotEmitterMixin,
    StateSerializerMixin,
    WireRoutingMixin,
)

logger = logging.getLogger("acervator.scrumming")


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
the operator's word means -- a skew SCALES, a shift OFFSETS, and v3.15.64
shipped a shift.

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

_STRONG_TREND_CANDLES = 20
"""How many candles back TREND-HOLD reads. ``tick`` slices exactly this
many."""

_STRONG_TREND_MIN_BULL_CANDLES = 13
"""How many of them must close up before the reading is a strong trend."""

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
    """``floor`` relaxed by ``skew``, proportionally, so the gate can refuse.

    THE DEFECT CLASS THIS CLOSES. ``tick()`` carried THREE favours and
    every one was written as an edit to ``eff_confidence``: the
    BB-priority skew (issue #102, repaired), ``position_boost`` and
    ``bb_confidence_boost`` (issue #104, this one). Confidence is bounded
    [0, 1] and the floor is 0.25, so a favour of 0.25 or more makes
    ``eff_confidence >= floor`` true for EVERY reading. The comparison
    has no false case and the conjunct cannot refuse.

    MEASURED, over 406 stone tablets at six tape lengths, 2,436 readings.
    ``position_boost`` reached +0.4000 -- larger than the largest
    consensus confidence the same sweep measured, 0.3402. A term bigger
    than the quantity it adjusts is not an adjustment to it. The two
    favours summed past the floor that judged them on 73 readings, and
    drove ``eff_confidence`` BELOW ZERO on 316: a confidence outside the
    domain of a confidence, printed to the operator at nine sites.

    WHY PROPORTIONAL AND NOT SUBTRACTIVE. Subtracting a favour of 0.30
    from a floor of 0.25 lands at or below zero and is the tautology
    again. Dividing preserves zero -- however large the favour, a reading
    of exactly 0.0 is still refused -- and it needs no second rule for a
    NEGATIVE skew, which tightens the floor by the same arithmetic.

    THE LIMIT AT A SKEW OF -1 IS INFINITY, AND THAT IS THE RIGHT ANSWER.
    A favour of -1 is total evidence against, and the floor no reading
    can clear is what the division tends to. It is returned rather than
    clamped to something friendlier. No skew this module builds reaches
    it: ``position_boost`` bottoms at -0.29 by enumeration of its own
    terms, ``bb_confidence_boost`` is never negative, and the BB-priority
    skew is positive. The branch guards a future term, not a live path.

    NO NEW NUMBER IS INTRODUCED. The floor and every skew are constants
    or measurements already of record. Only the form of the favour, and
    what it is applied to, change.
    """
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
    """Trim a tranche's ``wire_credits`` to the cap, folding the excess
    into a lossless ``wire_credits_rolled`` aggregate.

    Returns how many detail entries were rolled up.

    The aggregate preserves count, total USD and USD-per-source, so no
    credited dollar leaves the record — only per-event granularity ages
    out. Callers rely on that: this is money provenance, not telemetry.
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
    """Return True if the given currency code is a USD-equivalent stable.

    Stable quotes get a 1.0 quote→USD multiplier; non-stable quotes
    require a {QUOTE}/USD ticker fetch to recover the USD rate.
    """
    return (currency or "").upper() in _USD_STABLE_QUOTES


def _extract_signal_detail(
    summary: Optional["VotingSummary"],
    indicator_name: str,
    detail_key: str,
    default: float = 0.0,
) -> float:
    """Call-site activation helper for gate-chain context fields.

    The sentinel-zero return is what makes the gates' additive-landing
    contract survive call-site failures — gates with ``ctx.X == 0.0``
    trivially pass.
    """
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
class MemorisedTrade:
    """A scrumming event stored for potential conversion to a grid level."""

    timestamp: float
    side: str
    price: float
    amount: float
    voting_summary: Optional[VotingSummary] = None


@dataclass(frozen=True)
class SettledSellFee:
    """The fee the VENUE reported for one settled sell.

    issue #133 unit 9b. A sell is credited NET: the venue keeps its
    fee out of the proceeds. The fold-tranche loops valued a sell at
    ``units x fill_price``, which is the GROSS notional, so every
    tranche was booked richer than the wallet actually got.

    This record carries the venue's own number from the point an
    order settles to the point a tranche is valued. It NEVER carries
    a fee derived from ``config.trading_fee_pct``: that is the bot's
    configured estimate, the venue charges what it charges, and
    synthesising one in place of the other books a number the
    exchange never charged.

    ``units`` and ``price`` identify the fill this fee belongs to. A
    consumer that cannot match both books the gross, because a fee
    from some other order is not this order's fee.

    ``reported`` is False when the venue gave no fee. That case books
    the gross and says so; it does not fall back to a rate.
    """

    units: float
    price: float
    fee_amount: float
    currency: str
    reported: bool


@dataclass
class StackTrancheSummary:
    """A minimal stand-in summary carrying a Stack's opening vote.

    NOT a gate, and never was. `_execute_sell` reads
    `consensus_confidence` only for its "SELL signal:" line and the
    `MemorisedTrade` record; no branch there tests it. Authority to
    spend a tranche comes from the SCRUM gate chain evaluated on the
    tick it is spent, and `_spend_activated_stack_tranches` passes
    that tick's LIVE `VotingSummary`. This type is the fallback for a
    caller with no live vote, rebuilt from the `open_confidence` /
    `open_direction` recorded at stack-open time -- a forensic record
    of what opened the Stack, never authority to close it.
    """

    consensus_confidence: float = 0.0
    consensus_direction: str = "stack"


class ScrummingBot(
    CapitalReservationMixin,
    CircuitBreakerMixin,
    SnapshotEmitterMixin,
    StateSerializerMixin,
    WireRoutingMixin,
    BotContainer,
):
    """Speculative Scrumming auto-trader."""

    DEFAULT_PHANTOM_TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"]

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

        self._scrum_chain = build_scrumming_scrum_chain()
        self._fold_chain = build_scrumming_fold_chain()

        self._coordinator = coordinator or TimeframeCoordinator(bus=self._bus)
        self._phantom_mgr = PhantomBalanceManager(self._coordinator)
        self._phantom_timeframes = phantom_timeframes or self.DEFAULT_PHANTOM_TIMEFRAMES

        try:
            from ..exchange.timeframes import available_timeframes as _avail_tfs

            _allowed = set(_avail_tfs(config.exchange_id))
        except Exception:
            _allowed = None
        if _allowed is not None:
            _original = list(self._phantom_timeframes)
            self._phantom_timeframes = [
                tf for tf in self._phantom_timeframes if tf in _allowed
            ]
            _dropped = [tf for tf in _original if tf not in _allowed]
            if _dropped:
                self._phantom_tf_dropped_note = (
                    f"v3.15.61 phantom-TF filter: dropped {_dropped} on "
                    f"exchange '{config.exchange_id}' — not supported by "
                    f"native API. Remaining: {self._phantom_timeframes}."
                )
            else:
                self._phantom_tf_dropped_note = None
        else:
            self._phantom_tf_dropped_note = None

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

        self._fold_tranches: list[dict] = []
        self._main_lots: list[dict] = []

        # issue #133 unit 9b -- the fee the VENUE reported for the most
        # recent settled SELL, cleared as soon as a valuation consumes
        # it. Written only by `_record_venue_fee`, read only by
        # `_take_venue_fee`. Never derived from `trading_fee_pct`.
        self._last_sell_venue_fee: Optional[SettledSellFee] = None

        self._stack_tranches: list[dict] = []
        self._stack_created: int = 0
        self._stack_discarded: int = 0
        # issue #133 unit 7 -- the epoch second an operator cleared the
        # two counters above, 0.0 when they never have been. It is the
        # mirror of `_tranches_counters_reset_ts` and it is read for the
        # same reason: `_stack_created == 0` alone cannot tell "no stack
        # has ever opened" from "the operator cleared the record", and
        # the Stack panel prints the first of those as a sentence.
        self._stack_counters_reset_ts: float = 0.0

        self._tranches_created_lifetime: int = 0
        self._tranches_closed_lifetime: int = 0
        self._tranches_malformed_dropped: int = 0
        # issue #133 unit 3 -- the epoch second an operator cleared the
        # four counters above, 0.0 when they never have been. The four
        # carry no history once they read zero, so the init handshake
        # asks this field instead of reading a zeroed `created` as
        # "this bot has never scrummed".
        self._tranches_counters_reset_ts: float = 0.0
        # issue #133 unit 2 -- how many SELLS have opened fold tranches.
        # The operator's rule is a comparison and needs both sides:
        # "never more Fold tranches than Scrums that have occurred,
        # except during strong trends". This is the denominator. It
        # counts the autonomous SCRUM, the DIST sell and the manual /
        # wire-stack / max-cartridge fire, because each is the opposing
        # trade a fold tranche answers and each builds one.
        #
        # `clear_lifetime_tranche_counters` DELIBERATELY LEAVES IT
        # ALONE. Zeroing `created` and not this one keeps `created <=
        # scrums` true; zeroing this one and not `created` would break
        # it on the next read.
        self._scrum_sells_lifetime: int = 0
        # How many of the last 20 candles closed up, at the last tick
        # that had 20 to read. A COUNT and not the share TREND-HOLD
        # compares, because `_strong_trend_now` then answers on two
        # integers and cannot round at its own threshold. 0 until a
        # tick measures it, so a bot that has not yet read the market
        # gets the bound and not the exception.
        self._last_trend_bull_candles: int = 0

        self._scrum_target_mode: str = "search"
        self._scrum_target_side: Optional[str] = None

        self._manual_fire_pending: bool = False

        self._anchor_target_balance: float = float(config.target_balance)

        self._detonation_last_check_ts: float = 0.0
        self._detonation_last_signal_bullish: bool = False

        self._hedge_bal: float = (
            float(config.hedge_balance) if config.hedge_rebalance_active else 0.0
        )
        self._hedge_balance_initial: float = (
            float(config.hedge_balance) if config.hedge_rebalance_active else 0.0
        )
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

        Best-effort; returns ``None`` when critical fields are missing
        (bot not yet bootstrapped) so the caller can fall back to raw
        operator pct without applying safety math.
        """
        try:
            _price = float(getattr(self.stats, "current_price", 0.0) or 0.0)
            _target = float(getattr(self, "_target_balance", 0.0) or 0.0)
            _interval = float(
                getattr(self.config, "scrumming_interval_pct", 1.0) or 1.0
            )
            _growth = float(getattr(self.config, "max_target_growth_pct", 0.0) or 0.0)
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
        """Increment the per-cycle retained counter used by SWOS.

        Called by the scrum-fill sites beside ``stats.total_scrummed_usd``.
        """
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
        """Reset the retained-this-cycle counter to 0.

        Called at Fold execution — one Fold closes one cycle.
        """
        self._retained_this_cycle_usd = 0.0

    def set_market_pairs_scout(self, scout) -> None:
        """Attach the process-wide MarketPairsScout.

        Silently no-ops if ``scout`` is falsy — this keeps unit tests
        and headless simulators simple; the bot behaves identically
        with or without an attached scout.
        """
        self._market_pairs_scout = scout

    def get_target_asset_pairs(self):
        """Return the current PairSnapshots for the bot's target asset
        on this bot's exchange, from the attached scout.

        Returns an empty list when no scout is attached, when the
        scout has not yet polled, or when the target asset trades no
        recognised pairs on the exchange. Never raises.
        """
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

    def set_target_balance_live(self, new_target: float) -> dict:
        """Apply an operator-initiated Target Balance change mid-session.

        This method is the correct entry point for operator-initiated
        target changes. Updates BOTH `_target_balance` and
        `_anchor_target_balance` because an explicit operator raise
        re-sets the set-point for ceiling purposes — the anchor's job
        is to freeze the set-point against INTERNAL drift (profit-fold
        growth, Smart Wire routing) but NOT against EXPLICIT operator
        intent. Config is also updated so persistence + re-reads see
        the new value.

        v3.25.9 — `new_target` is compared against the ANCHOR, not
        against the grown `_target_balance`. The value arrives from an
        anchor-denominated spinbox (`cfg.target_balance`), so the grown
        target is the wrong frame to test it in. Worked example on live
        bot IMU (anchor $50.00, target $63.53, $13.53 accrued): the
        operator raises the displayed $50 to $60 to add $10 of capital.
        Under the anchor reference this is a top-up — anchor becomes
        $60 and target becomes $73.53. Under the old grown-target
        reference 60 > 63.53 was False, so both collapsed to $60, the
        $13.53 was destroyed, and the target FELL. The top-up policy of
        the 2026-07-26 Option A directive is unchanged; only the
        reference the comparison reads is corrected.

        Returns a dict:
            {
                "applied": True/False,
                "old_target": float,
                "old_anchor": float,
                "new_target": float,
                "new_anchor": float,
                "delta_usd": float    # new_target - position_value
            }
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

        # v3.23.30 — top-up preserves auto-accrued growth (Option A per
        # operator directive 2026-07-26). Previously any operator set
        # collapsed target + anchor to the new value, WIPING any
        # compounded growth accumulated between anchors. Symptom: bot
        # auto-grew target from $200 → $205, operator raised to $250
        # (thinking "add $50 capital"), old code set both = $250,
        # erasing the $5. Diagnosed via
        # docs/audits/2026-07-25_ytd_compounding_replay/REPORT.md.
        #
        # v3.25.9 — the comparison reads the ANCHOR, not the grown
        # target. `nt` arrives from the Target Balance spinbox, which
        # shows `cfg.target_balance` and is deliberately NOT repointed
        # at the grown value (the hazard is spelled out at
        # bot_live_settings.py:3736). The spinbox is therefore
        # anchor-denominated, so `nt` must be compared against the
        # anchor. Comparing it against the grown target made every
        # top-up smaller than the accrued growth fall into the
        # collapse branch: on live bot IMU (anchor $50.00, target
        # $63.53) raising the displayed $50 to $60 tested 60 > 63.53,
        # took the else branch, and set BOTH to 60 — destroying
        # $13.53 of accrued growth AND lowering the target below where
        # it already stood. The position then sat above target, the
        # Delta flipped positive, and the bot folded the excess.
        # This is a correction to the REFERENCE, not to the top-up
        # policy of the 2026-07-26 Option A directive.
        #
        # New behaviour:
        #   * new > current_anchor → interpret as top-up.
        #       anchor := new_target (fresh capital base)
        #       target := new_target + (current_target − current_anchor)
        #                                            (preserved growth)
        #     e.g. anchor=200 target=205 (5 accrued) + new=250 →
        #          anchor=250 target=255. Operator's $50 top-up
        #          preserved on top of $5 accrued.
        #     e.g. anchor=50 target=63.53 (13.53 accrued) + new=60 →
        #          anchor=60 target=73.53. The $10 top-up lands and
        #          the $13.53 survives, even though 60 is BELOW the
        #          grown target.
        #   * new < current_anchor → interpret as explicit lower / withdrawal.
        #       anchor := new_target
        #       target := new_target
        #     Accrued growth cleared (can't accrue above a lower base).
        #   * new == current_anchor → no-op path (mark_changed diff should
        #     already skip; guarded here too for robustness). Falls to
        #     the else branch, which is a no-op when target == anchor
        #     and a re-confirmation of the anchor when it is not.
        accrued = max(0.0, old_t - old_a)  # non-negative growth so far
        if nt > old_a and accrued > 1e-9:
            # Top-up path — preserve the accrued growth on top of the
            # new anchor.
            self._anchor_target_balance = nt
            self._target_balance = nt + accrued
        else:
            # At-or-below-anchor / zero-accrued — old behaviour (both
            # in lockstep). Zero-accrued == old behaviour by definition
            # since accrued=0.
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
        """The per-cycle Growth Rate Cap in USD. THE ONE DEFINITION.

        Issue #106, operator report 2026-08-21: "the compounding rate
        appears to stay frozen as a calculation based on the starting
        value of the bot but this should refresh after each Fold so as
        to induce the appropriate curve."

        THE BASE IS THE GROWN TARGET, NOT THE FROZEN ANCHOR. Every site
        that needed this number used to spell out
        `self._anchor_target_balance * (max_target_growth_pct / 100)`
        for itself. `_anchor_target_balance` moves only on operator
        input, wire income or tranche arrival; a Fold never moves it. So
        the cap held ONE dollar value for the life of the bot and the
        curve was `anchor x (1 + 0.01N)` rather than `anchor x 1.01^N`.
        Measured on the live fleet 2026-08-24: IMU had grown 27.1%, from
        $50.00 to $63.53, and still capped each Fold at $0.50.

        WHY THE BASE SUBTRACTS `_fold_cycle_cap_consumed` RATHER THAN
        READING `_target_balance` RAW. `_apply_fold_target_growth` adds
        the SAME `_growth_applied` to `_target_balance` and to
        `_fold_cycle_cap_consumed`, so their difference is invariant
        across a cycle and equals the target as it stood when the cycle
        opened. Reading the raw target instead would let the cap grow as
        the cycle consumed it -- a bound that expands while you spend it
        -- and one cycle would settle at pct/(1-pct) rather than pct.
        At 1% that is 1.0101% per cycle, an overrun of the per-event
        bound MEM-249 states. Subtracting the consumption pins the base
        for the cycle and needs no new attribute and no state migration.

        WHAT THIS DOES NOT CHANGE, and MEM-249 at
        `src/trading/bot_container.py` is the rule being kept: fold
        surplus is still the ONLY mechanism that may grow the target,
        and it is still bounded per event. Only the BASE of the bound
        moved. Nothing new became able to grow the target.

        FAIL-CLOSED. A non-finite or unreadable input returns 0.0, which
        is a cap of zero and therefore no growth at all. A cap that
        defaulted wide on unreadable state would grow the target from a
        number nobody could read.

        NOT ONE-DIRECTIONAL IN TWO NAMED STATES. The cap is >= the old
        one whenever accrued growth (`target - anchor`) is at least the
        consumption booked this cycle, which is the ordinary case
        because this cycle's consumption is PART of accrued growth.
        Detonation (`_execute_detonation`) puts the target back to the
        anchor and deliberately does NOT clear
        `_fold_cycle_cap_consumed`, and a withdrawal below the anchor
        clears growth the same way; in both the base sits BELOW the
        anchor until the cycle resets, so the cap is briefly smaller
        than it used to be. Both are bounded by the consumption already
        booked and both self-clear on the next cycle reset. Detonation
        is disabled on all 38 live bots.

        Returns:
          The whole cycle's cap in USD, not the remaining headroom.
          Callers subtract `_fold_cycle_cap_consumed` themselves, which
          is what the four call sites did before this property existed.

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
        # The target as it stood when this cycle opened. Never negative:
        # a detonation or a withdrawal can leave the consumption above
        # the target until the next reset, and a negative base would
        # make the cap negative and `cap - consumed` wrong in the other
        # direction.
        _base = max(0.0, _target - _consumed)
        return _base * (_pct / 100.0)

    def _apply_fold_target_growth(self, accum_profit: float, source: str) -> float:
        """Drain fold surplus into `_target_balance`, bounded by the
        per-cycle Growth Rate Cap. Returns `_growth_applied` (USD).


        Args:
          accum_profit: pre-quote-conversion USD-equivalent profit
                        from the caller's tranche match.
          source: short tag for the TARGET GROWN log line so operator
                  can see which fold kind produced the growth
                  ("auto", "MANUAL_FOLD", "CARTRIDGE_FOLD", etc.).

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
        # Issue #106 -- THE CAP COMPOUNDS. This read
        # `self._anchor_target_balance * (_cap_pct / 100.0)`, and the
        # anchor is the operator's input value which no Fold ever moves.
        # `cycle_growth_cap_usd` takes the same percentage of the target
        # as it stood when this cycle opened. Read its docstring for why
        # the base is not the raw target. `_cap_pct` used to be bound
        # here and is not, because nothing in this method reads the
        # percentage now that the property owns the arithmetic.
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
        """What ``_apply_fold_target_growth`` WOULD add. Moves no money.

            "After growth is calculated so that the Fold does not
             acquire too little and actually fails to compound."

        To size against the post-growth target the caller needs to know
        the growth BEFORE placing the order. The growth depends on the
        fill price, which is not knowable in advance -- so this uses the
        current quote as the proxy and the caller applies the REAL
        growth after the fill. The difference between the two is
        slippage on one order, not the whole growth.

        Mirrors the cap arithmetic of ``_apply_fold_target_growth``
        exactly (cycle cap off the ANCHOR, standing pool as an input,
        drawn down to the remaining cap). If that formula changes, this
        must change with it -- pinned by test.

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
        # Issue #106 -- the SAME property the applier reads. This is a
        # preview of what `_apply_fold_target_growth` WOULD add, so a
        # second spelling of the cap here would let the preview and the
        # applier disagree about the one number the preview exists to
        # predict. `_cap_pct` is no longer read for the cap and is not
        # bound at all.
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
        """Apply live aggressive-trading toggle.

        Runtime gap: __init__ snapshots config.aggressive_trading into
        self._aggressive (line 112). Config setattr alone leaves
        self._aggressive stale. Log strings at line 1121 and any
        downstream behavior keyed off self._aggressive stay on the old
        value.
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

    def set_hedge_balance_live(self, new_hedge_balance: float) -> dict:
        """Apply live hedge-balance cap change.

        Runtime gap: __init__ snapshots config.hedge_balance into
        self._hedge_bal AND self._hedge_balance_initial (search
        `_hedge_bal:` in __init__) but ONLY if hedge_rebalance_active
        is True at init. Config
        setattr alone doesn't update either runtime attr.

        Semantics:
          - _hedge_balance_initial is the OPERATOR-CONFIGURED CAP on
            the hedge reserve; bot refills up to this cap.
          - _hedge_bal is the CURRENT drainable reserve; drains on
            hedge spends, refills on scrum skims up to the cap.
          - Raising the cap: new room to refill. _hedge_bal unchanged.
          - Lowering the cap: no forced drain; reserve will simply not
            refill above the new cap. _hedge_bal unchanged.
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
        self._hedge_balance_initial = nv
        try:
            self.config.hedge_balance = nv
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "set_hedge_balance_live",
                type(_sup).__name__,
                _sup,
            )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"HEDGE BALANCE CAP LIVE UPDATE: ${old_cap:.2f} -> "
                f"${nv:.2f}. Current reserve ${old_reserve:.2f} "
                f"unchanged (refill will target the new cap)."
            ),
        )
        logger.info(
            "Bot %s hedge_balance cap live: %.2f -> %.2f", self.bot_id, old_cap, nv
        )
        return {
            "applied": True,
            "old_cap": old_cap,
            "new_cap": nv,
            "current_reserve": old_reserve,
        }

    _ARRIVAL_ATOMIC_TOL_USD: float = 1e-6

    @staticmethod
    def _positive_observed_quantity(
        value: Any, label: str
    ) -> tuple[float | None, str | None]:
        """Parse one observed money-path quantity, or say why it is unusable.

        Both halves of an Extractor arrival are OBSERVED quantities --
        USD that landed and units that landed -- and both are refused on
        exactly the same four grounds. One parser keeps the two halves
        from drifting apart, which is how a validated half and an
        unvalidated half end up in the same write.

        `float()` STILL RAISES ON A VALID `int`. `float(10 ** 400)` is
        OverflowError, not ValueError, and the old two-member `except`
        did not list it, so a caller-supplied huge integer raised
        straight out of a documented fail-closed money path. It is
        caught below with the other two.

        The parameter is `Any` on purpose. Annotating `float` while the
        body exists to reject `None` and `"x"` would be an annotation
        that documents the opposite of the contract.

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
        """Coerce one piece of the bot's OWN state, or say why it is unusable.

        A DIFFERENT CONTRACT FROM `_positive_observed_quantity`, and the
        difference is the point. An arrival must be strictly positive --
        a zero-dollar arrival is not an arrival. A target of 0.0 and
        holdings of 0.0 are ordinary, legal states of a bot that has not
        bought yet, so this checks numeric-and-finite only. Reusing the
        stricter parser here would refuse a healthy bot.

        What the two share is that they RETURN the refusal instead of
        raising. That is what lets every value the atomic block writes
        be validated BEFORE the block opens, which is the whole of D1's
        fix: a coercion that can raise must never sit between two
        writes.


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
        """Total units the lot ledger holds, or say why it cannot be read.

        The atomicity check reads this on BOTH sides of the arrival, so
        it is the ledger's own witness rather than a restatement of
        `_current_holdings`. A residual computed only from the two
        scalars is algebraically zero and cannot falsify anything; a
        residual that reads the lots back can.

        Refuses instead of raising for the same reason as
        `_finite_state_number`: the pre-block read must be able to stop
        the arrival, and the post-block read must be able to report a
        violation, and neither may throw on a money path.


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
        """Book base currency returned by a child Extractor Tranche.

            "rather than have an immediate Base Currency to USD sell
             fire this profit off as Surplus we want it protected by
             lifting the Target Balance to contain it and then have the
             received additional Base Currency to be distributed upward
             for further gains in terms of USD"


          holdings booked, target not lifted -> delta POSITIVE. The
            header model says "If delta > 0 and delta_pct >= interval:
            SCRUM (sell excess)", so the parent sells the child's gain.
          target lifted, holdings not booked -> delta NEGATIVE. The
            parent buys to close a gap that does not exist, spending
            real USD on a phantom shortfall.


            d(delta) = base_units * P * q_tick - usd_value

        and since `usd_value = base_units * arrival_price * q_arr` by
        construction, that is

            d(delta) = base_units * (P * q_tick
                                     - arrival_price * q_arr)

        At any other USD price the arrival moves delta by the
        mark-to-market of the units just booked -- precisely what the
        same units would contribute had the parent bought them itself.
        So the claim is that the arrival adds NO DELTA OF ITS OWN, not
        that delta is frozen: containment neutralises the booking, and
        the market still prices the position afterwards.


          * Incrementing `_current_holdings` without appending a lot
            breaks the invariant, and the next drift-down reconcile
            rescales `_main_lots` and resets holdings (:14314-14334),
            silently undoing the credit.
          * Booking nothing at all is not neutral either. Units that
            land on the exchange but are never attributed are refused
            by the drift-UP policy (:14336-14369) -- "those units
            belong to another bot, prior state, or operator" -- so the
            child's gain would sit unclaimed forever.

        This method owns both the scalar holdings write and the lot
        append, synchronously, with nothing suspending between them. The
        buy path splits the two across an await (scalar first, lot after
        the await returns), which briefly exposes a false holdings/lots
        invariant a concurrent tick can observe — so this method keeps
        both halves rather than delegating one.

        WHY `usd_value` IS AN OBSERVED ARRIVAL, NOT A COMPUTED PROFIT.
        The caller passes what ACTUALLY LANDED in the balance. That is
        already net of every fee the Extractor paid on both legs, so
        this lift cannot be gross or net -- there is nothing to net.
        Measure the arrival; do not compute the gain. Same exchange-truth
        principle as `buy_safety`. `base_units` is the matching observed
        quantity, so the lot's `initial_buy_price` is the two of them
        put back into the shape `_main_lots` stores -- a quote-side
        price -- and not a fabricated entry price.

        WHY THIS IS NOT `_apply_fold_target_growth` (:2070). That helper
        applies the per-cycle Growth Rate Cap (`max_target_growth_pct`,
        default 1.0% of the cycle-open target -- issue #106 moved that
        base off the anchor). A cap is WRONG here: a return larger
        than the cap would be truncated, the uncontained remainder would
        read as excess, and the parent would scrum exactly the amount
        this method exists to protect. Containment is uncapped by
        construction.

        Returns:
          {"applied": bool, ...}. On refusal nothing is mutated.

        Tests: tests/test_extractor_tranche_containment.py.
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

        # ---------------- ATOMIC ARRIVAL — DO NOT SPLIT ----------------
        lots.append(_arrival_lot)
        self._current_holdings = _h_after
        self._target_balance = _t_after
        self._anchor_target_balance = _a_after
        # -------------- END ATOMIC ARRIVAL — DO NOT SPLIT --------------

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

            # Expectation 1: the target moved by EXACTLY the arrival. A
            # cap or a partial write breaks it.
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
            # Expectation 2: all four writes landed, each measured
            # against the arrival. `actual` is the delta residual an
            # operator reads; `ok` carries the four per-write terms and
            # the two readability flags, so this record fails when ANY
            # write is missing -- including the run where they are ALL
            # missing, which every difference-based term reported as
            # zero.
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
        except Exception as _sup:  # noqa: BLE001,S110 - advisory
            logger.debug(
                "suppressed in %s: %s: %s",
                "apply_extractor_tranche_return",
                type(_sup).__name__,
                _sup,
            )

        # EVERY REPORTED BALANCE IS THE READ-BACK, NOT THE VALUE THIS
        # METHOD MEANT TO WRITE. Returning `_h_after` here would restate
        # the intention and hide the one failure the read-back exists to
        # expose; `_h_seen` is what the object actually holds now.
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
                f"Smart Ceiling + MEM-257 still apply."
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
                    "Ceiling / MEM-257 / P0b guard, or "
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
        """Live-update phantom configuration. Called by the live-settings

        Semantics:
        - enable_phantoms: toggles the flag; if turning OFF while
          phantoms are started, we leave existing phantoms running
          (stopping them cleanly requires an async call that the GUI
          thread cannot await) but set _phantoms_enabled=False so no
          new phantoms spawn. Fully stopping requires a bot restart
          until a proper async unwind path is added.
        - phantom_timeframes: updated for the next phantom create pass.
          Existing already-started phantoms keep running until bot
          restart — this method does NOT forcibly remove or add them
          mid-session to avoid state-race with the tick loop.
        - lock_candle_count: applied to the TimeframeCoordinator
          immediately (next lock installation uses the new value).

        Returns a dict of what was applied plus any caveats.
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
            _EXCHANGE_UNSUPPORTED_TFS = {
                "coinbase": {"4h", "2h", "30m", "1m"},
            }
            _unsupported = _EXCHANGE_UNSUPPORTED_TFS.get(
                self.config.exchange_id.lower(), set()
            )
            filtered = [tf for tf in phantom_timeframes if tf not in _unsupported]
            if list(filtered) != list(self._phantom_timeframes):
                self._phantom_timeframes = list(filtered)
                applied["phantom_timeframes"] = list(filtered)
                if self._phantoms_started:
                    caveats.append(
                        "TF set updated; already-started phantoms keep "
                        "their original TFs until bot restart."
                    )
                if _unsupported and any(
                    tf in _unsupported for tf in phantom_timeframes
                ):
                    dropped = [tf for tf in phantom_timeframes if tf in _unsupported]
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
        """Fetch a ticker through the shared MarketDataPool when wired,
        else fall back to a direct ``self.exchange.get_ticker`` call.

        Falls back to a direct fetch when ``self._data_pool`` is
        unset (test harnesses, paper-trading without a manager).
        """
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
        """Fetch a balance through the shared MarketDataPool when
        wired, else fall back to a direct exchange call. Callers
        that mutate the balance (post-trade paths) should also call
        ``_invalidate_balance(currency)`` so the next read reflects
        the change immediately."""
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
        """Force the next _get_balance for this (exchange, currency)
        to re-fetch from the connector. Fire from post-trade paths
        so the freshly-adjusted balance is visible to the next
        gate/reconciliation call within the tick."""
        if self._data_pool is None:
            return
        try:
            self._data_pool.invalidate_balance(self.config.exchange_id, currency)
        except Exception as _inv_exc:  # noqa: BLE001
            logger.debug("Bot %s balance invalidate failed: %s", self.bot_id, _inv_exc)

    async def _refresh_quote_to_usd(self) -> Optional[float]:
        """Refresh the cached quote→USD rate.

        For USD-stable quotes (USD/USDC/USDT/etc.) this is 1.0 — no fetch
        needed. For crypto quotes (ETH, BTC, SOL, ...) this fetches
        ``{QUOTE}/USD`` ticker.last and caches the result. Throttled to
        one fetch per 30s so it doesn't blow API quota — staleness of
        a few seconds is tolerable for a slow-moving rate.

        On fetch failure the cached rate is preserved (better than
        falling back to 1.0, which would silently mis-evaluate Target
        Balance for the entire tick). A single warning is emitted via
        bot.log so the operator sees the degraded state once; subsequent
        failures stay quiet to avoid spam.

        Returns the resolved rate, or ``None`` if the fetch failed and
        no cached rate exists.
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
        """Convert an amount in quote currency to its USD equivalent.

        For USD-quoted pairs returns ``quote_amount`` unchanged. For
        crypto-quoted pairs multiplies by the cached quote→USD rate.
        """
        try:
            return float(quote_amount) * float(self._quote_to_usd or 1.0)
        except (TypeError, ValueError):
            return 0.0

    def _from_usd(self, usd_amount: float) -> float:
        """Convert a USD amount into quote-currency units.

        Used at trade-execution sites where the bot decides to spend
        ``$X USD`` and must size the order in quote currency for the
        exchange. For USD-quoted pairs returns ``usd_amount`` unchanged;
        for crypto-quoted pairs divides by the quote→USD rate.

        Returns 0.0 if the rate is unavailable or non-positive — caller
        must check and refuse the trade.
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
        """Per-tick update of conditional opposing-direction hysteresis
        arm/disarm state.

        Behavior:
          • After a SCRUM (last_trade_side='SCRUM'): the FOLD-side gate
            arms when delta crosses into negative territory; disarms
            when delta returns non-negative. SCRUM-side stays
            disarmed (no longer relevant — last trade was already a
            SCRUM).
          • After a FOLD (last_trade_side='FOLD'): symmetric — the
            SCRUM-side gate arms when delta crosses into positive
            territory; disarms when delta returns non-positive.

        Reference price (`_hyst_ref_*_side`) is captured AT THE MOMENT
        OF ARMING — it becomes the new pivot from which the opposing
        price-distance requirement is measured. In a market bouncing
        near a BB extreme, each fresh arming captures a fresh pivot,
        so the gate "flickers on and off" (operator's words) tracking
        the current swing.
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
        """Called by every site that sets ``_last_trade_side`` after a
        fresh fill. Resets both opposing-direction hysteresis
        gates to disarmed with cleared pivot references. The next tick's
        ``_update_opposing_hysteresis_state`` call will re-arm if the
        Target Delta has crossed into opposing territory.

        Sites: regular SCRUM fill, regular FOLD fill, manual-fire SCRUM,
        manual-fire FOLD, self-destruct SCRUM. Centralized here so the
        invariant 'fresh fill ⇒ both gates disarmed' is one-spot-bound."""
        self._hyst_armed_fold_side = False
        self._hyst_armed_scrum_side = False
        self._hyst_ref_fold_side = 0.0
        self._hyst_ref_scrum_side = 0.0

    @property
    def position_value_usd(self) -> float:
        """USD-equivalent of current holdings.

        For USD-quoted pairs this is simply ``holdings * last_price``.
        For crypto-quoted pairs (BTC/ETH, anything/BTC) it converts via
        the cached quote→USD rate so comparisons against ``target_balance``
        (which is always operator-stated USD) remain meaningful.

        Returns 0.0 if no price is available (bot hasn't ticked yet).
        """
        price = getattr(self, "_last_trade_price", 0.0) or self.stats.current_price
        if not price or price <= 0:
            return 0.0
        return (
            float(self._current_holdings)
            * float(price)
            * float(self._quote_to_usd or 1.0)
        )

    @property
    def armed_action(self) -> Optional[str]:
        """What action Manual Fire will take if pressed NOW.

        Operator-stated rule: 'Positive [delta] = Scrum while Negative =
        Fold.' Delta here is in USD: current_holdings_value - target_balance.

        Returns:
            'scrum' — bot is above target, Manual Fire sells to rebalance
            'fold'  — bot is below target, Manual Fire buys to rebalance
            None    — within the dust band (|delta| < 1% of target), or
                      price/holdings unavailable; Manual Fire is a no-op.

        Dust band keeps the Fire button from falsely appearing "armed"
        when the bot is effectively at target and small price noise
        flips the sign tick-to-tick.
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
            value = holdings * price * _qrate
            delta = value - tgt
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
            mult = max(1.0, min(10.0, mult))
            return self._anchor_target_balance * mult
        except Exception:
            return None

    @property
    def ceiling_ratio(self) -> Optional[float]:
        """current_holdings_value / ceiling. None when ceiling disabled
        or no price available.

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
        value = (
            self._current_holdings
            * price
            * float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
        )
        return value / ceiling

    @property
    def fold_rate_taper(self) -> float:
        """Fold interval multiplier in [0.0, 1.0].

        Operator Q2: "Slow fold rate — reduce interval size the closer
        we get to ceiling."

        Taper schedule:
            ratio < 0.5  → 1.0 (full rate)
            ratio 0.5-1.0 → linear 1.0 → 0.1
            ratio >= 1.0 → 0.0 (hard stop)

        When ceiling is disabled, always returns 1.0 (no taper).
        """
        ratio = self.ceiling_ratio
        if ratio is None:
            return 1.0
        if ratio >= 1.0:
            return 0.0
        if ratio < 0.5:
            return 1.0
        return 1.0 - (ratio - 0.5) / 0.5 * 0.9

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

    EXCHANGE_HEALTH_REFRESH_COOLDOWN_SEC = 300.0

    async def refresh_exchange_position_health(self, force: bool = False) -> bool:
        """Refresh exchange-pulled position health stats.

        Returns True if a refresh actually fetched + updated stats,
        False if throttled or unavailable.

        Args:
            force: bypass throttle (use sparingly — e.g., on operator-
                triggered diagnostics).
        """
        import time as _t

        _now = _t.time()
        _cooldown = self.EXCHANGE_HEALTH_REFRESH_COOLDOWN_SEC
        if not force and (_now - self.stats.exchange_data_fresh_ts) < _cooldown:
            return False

        if self.exchange is None:
            return False
        if not hasattr(self.exchange, "get_my_trades"):
            return False

        try:
            from ..exchange.position_health import compute_position_health

            _trades = await self.exchange.get_my_trades(self.config.symbol, limit=500)
            if _trades is None:
                return False
            _asset_base = self.config.symbol.split("/")[0]
            _ph = compute_position_health(_trades, _asset_base)

            self.stats.realized_pnl_exchange = float(_ph.realized_pnl_usd)
            self.stats.avg_entry_exchange = float(_ph.avg_entry)
            self.stats.cost_basis_total_exchange = float(_ph.cost_basis_total_usd)
            self.stats.fees_paid_exchange = float(_ph.fees_paid_total)
            try:
                await self.sync_ytd_trade_count()
            except Exception as _ytd_exc:
                logger.debug(
                    "Bot %s YTD sync inside health-refresh raised: %s",
                    self.bot_id,
                    _ytd_exc,
                )
            self.stats.exchange_data_fresh_ts = _now

            try:
                _cash_usd = 0.0
                _bal_usd = await self._get_balance("USD")
                if _bal_usd is not None:
                    _cash_usd += float(getattr(_bal_usd, "free", 0) or 0)
                try:
                    _bal_usdc = await self._get_balance("USDC")
                    if _bal_usdc is not None:
                        _cash_usd += float(getattr(_bal_usdc, "free", 0) or 0)
                except Exception as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s",
                        "refresh_exchange_position_health",
                        type(_sup).__name__,
                        _sup,
                    )
                self.stats.cash_balance_usd = _cash_usd
            except Exception as _cash_exc:
                logger.debug(
                    "Bot %s cash balance refresh failed (non-fatal): %s",
                    self.bot_id,
                    _cash_exc,
                )

            try:
                if hasattr(self.exchange, "get_open_orders"):
                    from ..exchange.base import OrderSide as _OS

                    _open = await self.exchange.get_open_orders(self.config.symbol)
                    if _open is not None:
                        _buys = sum(
                            1 for o in _open if getattr(o, "side", None) == _OS.BUY
                        )
                        _sells = sum(
                            1 for o in _open if getattr(o, "side", None) == _OS.SELL
                        )
                        self.stats.active_buy_orders = int(_buys)
                        self.stats.active_sell_orders = int(_sells)
            except Exception as _oo_exc:
                logger.debug(
                    "Bot %s open-orders refresh failed (non-fatal): %s",
                    self.bot_id,
                    _oo_exc,
                )

            return True
        except Exception as _exc:
            logger.warning(
                "Bot %s exchange position-health refresh failed: %s", self.bot_id, _exc
            )
            return False

    YTD_TRADE_ANCHOR_UTC = 1_775_001_600.0
    YTD_TRADE_PAGE_LIMIT = 500
    YTD_TRADE_MAX_PAGES = 40

    async def sync_ytd_trade_count(self) -> Optional[int]:
        """Paginate get_my_trades from YTD_TRADE_ANCHOR_UTC forward
        and reconcile ``stats.total_trades`` / ``exchange_trade_count``.

        Returns the reconciled total, or ``None`` when the exchange
        can't be consulted (missing connector, method not implemented,
        API error). Never lowers the persisted counter — the
        reconciled value is ``max(persisted, exchange_count)`` so a
        partial-page response or transient rate-limit can't wipe out
        real history. Called once at boot from
        ``bootstrap_exchange_state``; subsequent per-trade increments
        continue via the normal execute-buy / execute-sell paths.
        """
        if self.exchange is None:
            return None
        if not hasattr(self.exchange, "get_my_trades"):
            return None
        _persisted = int(getattr(self.stats, "total_trades", 0) or 0)
        import time as _t

        _now = _t.time()
        _window_s = 30 * 24 * 3600.0
        _cursor = self.YTD_TRADE_ANCHOR_UTC
        _seen_ids: set = set()
        _windows = 0
        _ytd_scrum_usd = 0.0
        _ytd_fold_usd = 0.0
        _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
        try:
            while _cursor < _now and _windows < 12:
                _end = min(_cursor + _window_s, _now)
                _end_ms = int(_end * 1000)
                _window_trades = await self.exchange.get_my_trades(
                    self.config.symbol,
                    since=_cursor,
                    limit=self.YTD_TRADE_PAGE_LIMIT,
                    params={"paginate": True, "until": _end_ms},
                )
                _new = 0
                for _tr in _window_trades or []:
                    _tid = getattr(_tr, "id", None) or id(_tr)
                    if _tid in _seen_ids:
                        continue
                    _seen_ids.add(_tid)
                    _new += 1
                    try:
                        _amt = float(getattr(_tr, "amount", 0) or 0)
                        _px = float(getattr(_tr, "price", 0) or 0)
                        _usd = _amt * _px * _qrate
                        _side = getattr(_tr, "side", None)
                        _side_str = str(getattr(_side, "value", _side) or "").lower()
                        if "sell" in _side_str:
                            _ytd_scrum_usd += _usd
                        elif "buy" in _side_str:
                            _ytd_fold_usd += _usd
                    except (TypeError, ValueError) as _sup:
                        logger.debug(
                            "suppressed in %s: %s: %s",
                            "sync_ytd_trade_count",
                            type(_sup).__name__,
                            _sup,
                        )
                logger.debug(
                    "Bot %s YTD window %d: [%.0f..%.0f] returned=%d "
                    "new=%d cumulative_unique=%d",
                    self.bot_id,
                    _windows + 1,
                    _cursor,
                    _end,
                    len(_window_trades or []),
                    _new,
                    len(_seen_ids),
                )
                _windows += 1
                _cursor = _end
            _count = len(_seen_ids)
            logger.info(
                "Bot %s YTD sync via chunked-window walk: "
                "symbol=%s returned %d unique trades over %d windows "
                "(scrummed=$%.2f folded=$%.2f)",
                self.bot_id,
                self.config.symbol,
                _count,
                _windows,
                _ytd_scrum_usd,
                _ytd_fold_usd,
            )
        except Exception as _exc:
            logger.warning(
                "Bot %s sync_ytd_trade_count fetch failed: %s "
                "(persisted counter %d retained)",
                self.bot_id,
                _exc,
                _persisted,
            )
            return None
        _prev_exc = int(getattr(self.stats, "exchange_trade_count", 0) or 0)
        _reconciled = max(_persisted, _prev_exc, _count)
        self.stats.total_trades = _reconciled
        self.stats.exchange_trade_count = _reconciled
        _prev_scrum = float(getattr(self.stats, "ytd_scrummed_usd", 0.0) or 0.0)
        _prev_fold = float(getattr(self.stats, "ytd_folded_usd", 0.0) or 0.0)
        self.stats.ytd_scrummed_usd = max(_prev_scrum, _ytd_scrum_usd)
        self.stats.ytd_folded_usd = max(_prev_fold, _ytd_fold_usd)
        import time as _t

        self.stats.exchange_data_fresh_ts = _t.time()
        logger.info(
            "Bot %s YTD trade-count sync: exchange=%d persisted=%d "
            "prev_exchange=%d reconciled=%d",
            self.bot_id,
            _count,
            _persisted,
            _prev_exc,
            _reconciled,
        )
        return _reconciled

    async def bootstrap_exchange_state(self) -> None:
        """One-shot live-pull of exchange state for the GUI.

        Populates: _current_holdings, stats.current_price, stats.position_value.
        Runs fail-closed — any exception logged but not raised. Intended to
        be scheduled as a background task right after the connector is
        attached to the bot; irrelevant for bots that tick quickly (the
        handshake covers them) but essential for bots that haven't started.
        """
        if (
            self.exchange is None
            or not hasattr(self.exchange, "get_balance")
            or type(self.exchange).__name__ == "_PlaceholderExchangeForRestore"
        ):
            logger.debug(
                "Bot %s bootstrap_exchange_state: exchange not ready "
                "(placeholder or missing); will retry once real "
                "connector attaches.",
                self.bot_id,
            )
            return
        try:
            symbol = self.config.symbol
            target_asset = self.config.target_asset
            _bal = await self._get_balance(target_asset)
            _units = float(getattr(_bal, "total", 0) or _bal.free or 0)
            _ticker = await self._get_ticker(symbol)
            _price = float(getattr(_ticker, "last", 0) or 0)
            try:
                await self._refresh_quote_to_usd()
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "bootstrap_exchange_state",
                    type(_sup).__name__,
                    _sup,
                )

            _tracked_units_bootstrap = sum(
                float(lot.get("units", 0) or 0) for lot in self._main_lots
            )
            if _units >= 0:
                self._current_holdings = (
                    min(max(0.0, _units), _tracked_units_bootstrap)
                    if _tracked_units_bootstrap > 0
                    else 0.0
                )
                self._bootstrap_adopt_from_exchange(
                    max(0.0, _units), _tracked_units_bootstrap, _price, target_asset
                )
            if _price > 0:
                self.stats.current_price = _price
            if _price > 0 and self._current_holdings > 0:
                self.stats.position_value = (
                    self._current_holdings * _price * float(self._quote_to_usd or 1.0)
                )
            else:
                self.stats.position_value = 0.0
            logger.info(
                "Bot %s bootstrap_exchange_state: %s units=%.8f @ $%.8f "
                "quote_to_usd=%.4f (position_usd=$%.4f)",
                self.bot_id,
                target_asset,
                _units,
                _price,
                self._quote_to_usd,
                _units * _price * float(self._quote_to_usd or 1.0),
            )

            try:
                _refreshed = await self.refresh_exchange_position_health(force=True)
                if _refreshed:
                    logger.info(
                        "Bot %s bootstrap_exchange_state: position health "
                        "refreshed (realized=$%.4f, avg_entry=$%.8f, "
                        "trades=%d)",
                        self.bot_id,
                        self.stats.realized_pnl_exchange,
                        self.stats.avg_entry_exchange,
                        self.stats.exchange_trade_count,
                    )
            except Exception as _ph_exc:
                logger.warning(
                    "Bot %s bootstrap position-health refresh failed: %s "
                    "(will retry on first action tick)",
                    self.bot_id,
                    _ph_exc,
                )
            try:
                await self.sync_ytd_trade_count()
            except Exception as _ytd_exc:
                logger.warning(
                    "Bot %s bootstrap YTD trade-count sync failed: %s "
                    "(persisted counter retained)",
                    self.bot_id,
                    _ytd_exc,
                )
        except Exception as exc:
            logger.warning(
                "Bot %s bootstrap_exchange_state raised %s: %s "
                "(GUI will show pending until first tick)",
                self.bot_id,
                type(exc).__name__,
                exc,
            )

    def _pre_buy_allowed(
        self, intended_cost: float, path: str, ticker_price: float
    ) -> tuple[bool, str]:
        """Return (allowed, reason).

        • Layer 1 — Target-Delta budget per path:
            fold_rebuy / unspecified: projected ≤ target + per_cycle_growth_budget
            zero_balance_initial_entry: projected ≤ target_balance × (1 + tol)
            hedge_replenish: projected ≤ current_position + hedge_bal
        • Layer 2 — Smart Ceiling (when enabled): projected ≤ anchor × multiple
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
                    f"MEM-253 PRE-BUY REFUSED (path={path}, Layer 1): "
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
                    _smart_mult = max(1.0, min(10.0, _smart_mult))
                    _smart_ceiling_usd = _anchor * _smart_mult
                    if _projected > _smart_ceiling_usd:
                        return False, (
                            f"MEM-253 PRE-BUY REFUSED (path={path}, Layer 2): "
                            f"projected position ${_projected:.2f} would "
                            f"exceed Smart Ceiling ${_smart_ceiling_usd:.2f} "
                            f"(anchor ${_anchor:.2f} × {_smart_mult:.1f}x). "
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
                f"MEM-253 PRE-BUY REFUSED (path={path}): pre-check raised "
                f"{type(exc).__name__}: {exc}. Fail-closed."
            )

    def _fold_eligible_tranches(self, ticker_last: float, otd_factor: float) -> list:
        """Fold-queue tranches eligible for fold-back at ``ticker_last``.

        A tranche is eligible when ``ticker_last <= ref * otd_factor``.
        This is the single definition of fold eligibility, called by both
        the FOLD_DIAG counter and the fold-back executor so the
        diagnostic can never report a different set than the one that
        fires.
        """
        return [
            t
            for t in self._fold_tranches
            if ticker_last <= float(t.get("ref", 0)) * otd_factor
        ]

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
                # Still polling — but init tick always runs so we don't
                # defer exchange connection + phantom setup.
                #
                # ── DIRECTIVE 2 EMITTER — the throttle, at its site ──
                # This return is why "per-candle TA every tick" is false:
                # measured on the live fleet, scrum_read_rate_min is 1 on
                # 29 bots and 5 on 6, against a hardcoded tick_interval
                # of 5.0, so _tick_skip is 12 for most of the fleet and
                # 60 for the rest. Roughly 91% of ticks exit HERE.
                #
                # `bots_ticked` in the replay controller increments after
                # tick() returns regardless, so it counted this exit
                # identically to a full evaluation. Recording the exit
                # where it happens makes the two separable without
                # inferring anything.
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
                except Exception as _sup:  # noqa: BLE001,S110 - advisory
                    logger.debug(
                        "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                    )
                return
            self._tick_counter = 0
            # The satisfied path. Emitted so silence is never ambiguous:
            # a run with zero `tick.08.002.event.worked` records did
            # not work, and a run with no records at all was not
            # collected. Those must not look the same.
            try:
                from src.core.signal_contract import emit as _tk2

                _tk2(
                    "tick.08.002.event.worked",
                    actual=True,
                    context={"bot_id": self.bot_id, "skip": self._tick_skip},
                )
            except Exception as _sup:  # noqa: BLE001,S110 - advisory
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
            ticker = await self._get_ticker(symbol)
            self._last_price = ticker.last
            self.stats.current_price = ticker.last
            try:
                await self._refresh_quote_to_usd()
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )

            try:
                _bal1 = await self._get_balance(self.config.target_asset)
                _h1 = float(getattr(_bal1, "total", 0) or _bal1.free or 0)
                await asyncio.sleep(0.25)
                _bal2 = await self._get_balance(self.config.target_asset)
                _h2 = float(getattr(_bal2, "total", 0) or _bal2.free or 0)
            except Exception as _hs_exc:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INIT HANDSHAKE FAILED: exchange balance fetch "
                        f"raised ({_hs_exc}). Bot NOT marked initialised. "
                        f"Outer loop will retry on next tick. Refusing to "
                        f"proceed with unknown holdings."
                    ),
                )
                logger.warning(
                    "Bot %s init handshake raised: %s; will retry", self.bot_id, _hs_exc
                )
                raise

            _max_h = max(_h1, _h2)
            _abs_diff = abs(_h1 - _h2)
            _rel_diff = _abs_diff / _max_h if _max_h > 0 else 0.0
            if _max_h > 0 and _rel_diff > 0.001:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INIT HANDSHAKE MISMATCH: two successive "
                        f"get_balance reads returned "
                        f"{_h1:.6f} vs {_h2:.6f} ({_rel_diff*100:.2f}% "
                        f"diff). Refusing to initialise on an uncertain "
                        f"read. Retrying next tick."
                    ),
                )
                logger.warning(
                    "Bot %s init handshake mismatch: %.6f vs %.6f",
                    self.bot_id,
                    _h1,
                    _h2,
                )
                return

            if getattr(_bal1, "absent", False) or getattr(_bal2, "absent", False):
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INIT HANDSHAKE REFUSED (absent-sentinel): "
                        f"exchange OMITTED "
                        f"{self.config.target_asset} from "
                        f"fetch_balance response "
                        f"(bal1.absent={getattr(_bal1, 'absent', '?')}, "
                        f"bal2.absent={getattr(_bal2, 'absent', '?')}). "
                        f"Cannot verify holdings. Will NOT initialise bot "
                        f"on a structurally-zeroed read. Retrying next tick."
                    ),
                )
                logger.warning(
                    "Bot %s init handshake refused — %s absent from exchange response",
                    self.bot_id,
                    self.config.target_asset,
                )
                return

            _lots_units = sum(
                float(lot.get("units", 0) or 0) for lot in self._main_lots
            )
            if _h2 == 0.0 and _lots_units > 0.0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INIT HANDSHAKE REFUSED (lots-cross-check): "
                        f"exchange reports 0 {self.config.target_asset} "
                        f"but restored state shows {_lots_units:.6f} "
                        f"units in _main_lots. Refusing to overwrite "
                        f"persisted holdings with a suspicious zero. If "
                        f"the position was genuinely liquidated "
                        f"off-platform, operator must clear _main_lots "
                        f"via state reset tool. Retrying next tick."
                    ),
                )
                logger.warning(
                    "Bot %s init handshake refused — exchange=0 vs "
                    "restored lots=%.6f",
                    self.bot_id,
                    _lots_units,
                )
                return

            _never_scrummed = (
                int(getattr(self, "_tranches_created_lifetime", 0) or 0) == 0
                and float(getattr(self, "_tranches_counters_reset_ts", 0.0) or 0.0)
                <= 0.0
            )
            if _never_scrummed and _h2 > 0:
                _sib_units = 0.0
                _mgr = getattr(self, "_bot_manager", None)
                if _mgr is not None:
                    try:
                        if _mgr.has_sibling_target_bots(
                            self.bot_id, self.config.target_asset
                        ):
                            _sib_units = float(
                                _mgr.sum_sibling_tracked_units(
                                    self.bot_id, self.config.target_asset
                                )
                                or 0.0
                            )
                    except Exception as _sib_exc:  # noqa: BLE001
                        _sib_units = float(_h2)
                        logger.warning(
                            "Bot %s adoption: sibling query raised (%s); "
                            "claiming nothing",
                            self.bot_id,
                            _sib_exc,
                        )
                _own = max(0.0, float(_h2) - _sib_units)

                _px_cap = float(getattr(ticker, "last", 0.0) or 0.0)
                _cap_usd = float(getattr(self.config, "max_adoptable_usd", 0.0) or 0.0)
                if _cap_usd <= 0:
                    _cap_usd = float(self._target_balance or 0.0)
                _uncapped = _own
                _was_capped = False
                if _cap_usd > 0 and _px_cap > 0 and _own * _px_cap > _cap_usd:
                    _own = _cap_usd / _px_cap
                    _was_capped = True
                if _was_capped:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"ADOPTION CAPPED: exchange holds "
                            f"{_uncapped:.6f} {self.config.target_asset} but "
                            f"this bot may adopt at most ${_cap_usd:.2f} "
                            f"({_own:.6f} units @ ${_px_cap:.8f}). The "
                            f"remaining {_uncapped - _own:.6f} units stay "
                            f"unmanaged. Raise max_adoptable_usd to change "
                            f"this."
                        ),
                    )
                    try:
                        from src.core.signal_contract import emit as _cap_emit

                        _cap_emit(
                            "bot.01.003.postcondition.adoption_capped",
                            actual=round(_own, 10),
                            expected=round(_uncapped, 10),
                            context={
                                "bot_id": str(self.bot_id),
                                "asset": str(self.config.target_asset),
                                "cap_usd": _cap_usd,
                                "withheld_units": round(_uncapped - _own, 10),
                            },
                        )
                    except Exception as _sup:  # noqa: BLE001,S110 - advisory
                        logger.debug(
                            "suppressed in %s: %s: %s",
                            "tick",
                            type(_sup).__name__,
                            _sup,
                        )

                _held = sum(float(lot.get("units", 0) or 0) for lot in self._main_lots)
                if _own > 0.0 and abs(_own - _held) > 1e-12:
                    _px = float(getattr(ticker, "last", 0.0) or 0.0)
                    _basis_src = "ticker"
                    _basis = _px
                    try:
                        _cb = float(
                            getattr(self.stats, "cost_basis_total_exchange", 0.0) or 0.0
                        )
                        if _cb > 0:
                            _basis = _cb / _own
                            _basis_src = "exchange cost basis"
                    except (TypeError, ValueError, ZeroDivisionError) as _sup:
                        logger.debug(
                            "suppressed in %s: %s: %s",
                            "tick",
                            type(_sup).__name__,
                            _sup,
                        )
                    if _basis > 0:
                        self._main_lots = [
                            {
                                "units": _own,
                                "initial_buy_price": _basis,
                            }
                        ]
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"OPENING POSITION ADOPTED: {_own:.6f} "
                                f"{self.config.target_asset} held on the exchange "
                                f"(${_own * _px:.2f} @ ${_px:.8f}) is this bot's "
                                f"opening position; cost basis ${_basis:.8f} from "
                                f"{_basis_src}. This bot has never scrummed, so "
                                f"it has no earned history to protect"
                                + (
                                    f"; {_sib_units:.6f} units excluded as sibling"
                                    f"-tracked"
                                    if _sib_units > 0
                                    else ""
                                )
                                + f". Previously tracked {_held:.6f}."
                            ),
                        )
                        logger.info(
                            "Bot %s adopted opening position: %.8f %s @ %.8f "
                            "(was %.8f, sibling-tracked %.8f)",
                            self.bot_id,
                            _own,
                            self.config.target_asset,
                            _basis,
                            _held,
                            _sib_units,
                        )

            self._current_holdings = sum(
                float(lot.get("units", 0) or 0) for lot in self._main_lots
            )
            self._initialised = True
            _qrate = float(self._quote_to_usd or 1.0)
            _init_usd = self._current_holdings * ticker.last * _qrate
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"INIT HANDSHAKE OK: position=${_init_usd:.2f} "
                    f"verified across 2 reads within tolerance. "
                    f"(forensic: {self._current_holdings:.6f} "
                    f"{self.config.target_asset} @ ${ticker.last:.8f}"
                    f'{chr(44)+chr(32)+f"quote-USD={_qrate:.4f}" if abs(_qrate - 1.0) > 1e-9 else ""})'
                ),
            )

            _init_usd = (
                self._current_holdings * ticker.last * float(self._quote_to_usd or 1.0)
            )
            _init_delta = _init_usd - self._target_balance
            _init_region = (
                "on-target"
                if abs(_init_delta) < at_target_dust_band(self._target_balance)
                else (
                    "above target by " + f"${_init_delta:+.2f}"
                    if _init_delta > 0
                    else "below target by " + f"${_init_delta:+.2f}"
                )
            )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"Scrumming init: {symbol} position=${_init_usd:.2f} "
                    f"vs target=${self._target_balance:.2f} ({_init_region}). "
                    f"(forensic: {self._current_holdings:.6f} "
                    f"{self.config.target_asset} @ ${ticker.last:.8f})"
                ),
            )
            vis = "INVISIBLE" if self._invisible else "ORDER BOOK"
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"  Mode: {vis}"
                f"{' + AGGRESSIVE' if self._aggressive else ''}",
            )

            if not getattr(self, "_phantom_gate_logged", False):
                logger.info(
                    "P0g-DIAG | bot=%s tick-gate _phantoms_enabled=%s "
                    "_phantoms_started=%s timeframes=%s",
                    self.bot_id[:8],
                    self._phantoms_enabled,
                    self._phantoms_started,
                    self._phantom_timeframes,
                )
                self._phantom_gate_logged = True
            if self._phantoms_enabled and not self._phantoms_started:
                self._phantom_mgr.create_phantom_set(
                    parent_bot_id=self.bot_id,
                    timeframes=self._phantom_timeframes,
                    target_balance=self._target_balance,
                    exchange=self.exchange,
                    symbol=symbol,
                    ta_weights=self._ta_weights,
                )
                await self._phantom_mgr.start_all(self.bot_id)
                self._phantoms_started = True
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"  Phantoms: {len(self._phantom_timeframes)} TFs active "
                    f"({', '.join(self._phantom_timeframes)})",
                )
                if self._phantom_tf_dropped_note:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=self._phantom_tf_dropped_note,
                    )
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

        current_value = (
            self._current_holdings * ticker.last * float(self._quote_to_usd or 1.0)
        )

        _delta_early = current_value - self._target_balance
        self._update_opposing_hysteresis_state(_delta_early, ticker.last)

        # ================================================================
        # MEM-258 DELTA-ZERO SHORT-CIRCUIT (FUND-SAFETY, Session 26).
        # ================================================================
        # Operator directive, verbatim:
        #   "IF THE GOD DAMN FUCKING CURRENT BALANCE EQUAL TARGET BALANCE
        #    NO SIGNAL LEAVES THE GOD DAMN PLATFORM. WHY THE FUCK ARE YOU
        #    EVEN LOOKING FOR AN OPPORTUNITY WITHOUT A TARGET DELTA!!!!!!"
        #
        # Rule: if current_value is within the dust band of target, the bot
        # EXITS THE TICK IMMEDIATELY. No TA evaluated. No opportunity sought.
        # No buy or sell path considered. No fresh balance fetched downstream
        # (which could generate a transient reading that might trigger an
        # erroneous action). The bot stays parked until price moves the
        # position far enough from target that action is meaningfully needed.
        #
        # Manual fire override (self._manual_fire_pending) still bypasses —
        # operator-invoked action takes precedence over the parked state.
        # Otherwise: parked.
        # 0.1% of target, $0.01 floor. The dashboard's Ammo cell reads
        # the same function, so the cell cannot promise a different
        # park band from the one this tick applies.
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
                        f"AT TARGET (MEM-258): position=${current_value:.2f} "
                        f"within dust band (±${_dust_band_usd:.4f}) of "
                        f"target=${self._target_balance:.2f}. Tick exits "
                        f"early. No TA, no signals, no buys or sells "
                        f"evaluated until price moves position off target."
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
            except Exception as _sup:  # noqa: BLE001,S110 - advisory
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
            return
        self._at_target_counter = 0

        if self._manual_fire_pending:
            _mf_usd = (
                self._current_holdings * ticker.last * float(self._quote_to_usd or 1.0)
            )
            _mf_delta = _mf_usd - self._target_balance
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MANUAL FIRE: tick reached rebalance entry. "
                    f"position=${_mf_usd:.2f} vs target=${self._target_balance:.2f} "
                    f"(delta=${_mf_delta:+.2f}). Executing rebalance... "
                    f"(forensic: holdings={self._current_holdings:.6f} "
                    f"price=${ticker.last:.8f} target=${self._target_balance:.2f})"
                ),
            )
            try:
                await self._execute_manual_rebalance(
                    ticker, caller_intent="manual_button"
                )
            except Exception as exc:
                self._manual_fire_pending = False
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"MANUAL FIRE: exception during rebalance: {exc}",
                )
                logger.exception("Manual fire rebalance failed")
            return

        try:
            _stack_pending = float(getattr(self, "_pending_stack_buy_usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            _stack_pending = 0.0
        if _stack_pending > 0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"WIRE STACK FIRE: acquiring ${_stack_pending:.2f} of "
                    f"{self.config.target_asset} via aggressive rebalance "
                    f"to new target ${self._target_balance:.2f}."
                ),
            )
            try:
                self._emit_trade_notification(
                    "WIRE_STACK", "SENT", f"${_stack_pending:.2f} acquisition"
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
            self._pending_stack_buy_usd = 0.0
            _verified_units, _refuse_msg = await self._verify_buy_safe_or_refuse(
                path="wire_stack"
            )
            if _refuse_msg:
                self._bus.emit("bot.log", bot_id=self.bot_id, message=_refuse_msg)
                logger.warning("Bot %s %s", self.bot_id, _refuse_msg)
                return
            try:
                await self._execute_manual_rebalance(ticker, caller_intent="wire_stack")
            except Exception as exc:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"WIRE STACK FIRE: rebalance raised "
                        f"{type(exc).__name__}: {exc}"
                    ),
                )
                logger.exception("Wire stack rebalance failed")
            return

        try:
            _cartridge_pct = float(
                getattr(self.config, "max_cartridge_size_pct", 10.0) or 0.0
            )
        except (TypeError, ValueError):
            _cartridge_pct = 0.0

        _smart_bb = getattr(self, "_last_bb", None)
        if (
            getattr(self.config, "max_cartridge_smart", False)
            and _smart_bb is not None
            and getattr(_smart_bb, "upper", 0) > 0
            and getattr(_smart_bb, "lower", 0) > 0
        ):
            try:
                _bb_mid = (
                    getattr(_smart_bb, "bb_middle", 0)
                    or getattr(_smart_bb, "middle", 0)
                    or ((_smart_bb.upper + _smart_bb.lower) / 2.0)
                )
                if _bb_mid > 0:
                    _bb_range_pct = (
                        (_smart_bb.upper - _smart_bb.lower) / _bb_mid * 100.0
                    )
                    _interval_floor = float(self.config.scrumming_interval_pct or 0)
                    _smart_ceiling = float(
                        getattr(self.config, "max_cartridge_smart_ceiling_pct", 30.0)
                        or 30.0
                    )
                    _smart_pct = max(
                        _interval_floor, min(_smart_ceiling, _bb_range_pct)
                    )
                    _last_smart = float(
                        getattr(self, "_cartridge_last_smart_pct", 0.0) or 0.0
                    )
                    if abs(_smart_pct - _last_smart) >= 1.0:
                        try:
                            self._bus.emit(
                                "bot.log",
                                bot_id=self.bot_id,
                                message=(
                                    f"SMART CARTRIDGE calibrated to "
                                    f"{_smart_pct:.2f}% "
                                    f"(BB range {_bb_range_pct:.2f}%, "
                                    f"floor={_interval_floor:.2f}%, "
                                    f"ceiling={_smart_ceiling:.2f}%). "
                                    f"Effective threshold = "
                                    f"${self._target_balance * _smart_pct / 100.0:.2f}."
                                ),
                            )
                        except Exception as _sup:
                            logger.debug(
                                "suppressed in %s: %s: %s",
                                "tick",
                                type(_sup).__name__,
                                _sup,
                            )
                        self._cartridge_last_smart_pct = _smart_pct
                    _cartridge_pct = _smart_pct
            except (TypeError, ValueError, ZeroDivisionError) as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )

        if _cartridge_pct > 0 and self._target_balance > 0:
            _cartridge_threshold = self._target_balance * _cartridge_pct / 100.0
            _cartridge_delta = current_value - self._target_balance
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
                                f"MAX CARTRIDGE BLOCKED (hysteresis "
                                f"v3.15.79): would fire {_direction} on "
                                f"|delta|=${abs(_cartridge_delta):.2f} "
                                f"≥ ${_cartridge_threshold:.2f}, but "
                                f"{_hyst_reason}. Refusing to prevent "
                                f"fee-thrash round-trip with recent "
                                f"opposite trade. Will re-evaluate "
                                f"each tick as price moves."
                            ),
                        )
                else:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"MAX CARTRIDGE FIRE ({_direction}): "
                            f"|delta|=${abs(_cartridge_delta):.2f} "
                            f"≥ threshold ${_cartridge_threshold:.2f} "
                            f"({_cartridge_pct:.1f}% of target "
                            f"${self._target_balance:.2f}). "
                            f"Hysteresis clear. Firing aggressive "
                            f"rebalance — bypasses BB Detection / "
                            f"soft CB / higher-TF bias gates. "
                            f"v3.15.79 NO LONGER bypasses "
                            f"opposing-direction hysteresis."
                        ),
                    )
                    if _direction == "FOLD":
                        _verified_units, _refuse_msg = (
                            await self._verify_buy_safe_or_refuse(path="cartridge_fold")
                        )
                        if _refuse_msg:
                            self._bus.emit(
                                "bot.log", bot_id=self.bot_id, message=_refuse_msg
                            )
                            logger.warning("Bot %s %s", self.bot_id, _refuse_msg)
                            return
                    try:
                        self._emit_trade_notification(
                            f"CARTRIDGE_{_direction}",
                            "SENT",
                            f"|delta|=${abs(_cartridge_delta):.2f} ≥ "
                            f"${_cartridge_threshold:.2f}",
                        )
                    except Exception as _sup:
                        logger.debug(
                            "suppressed in %s: %s: %s",
                            "tick",
                            type(_sup).__name__,
                            _sup,
                        )
                    try:
                        await self._execute_manual_rebalance(
                            ticker, caller_intent="max_cartridge"
                        )
                    except Exception as exc:
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"MAX CARTRIDGE: rebalance raised "
                                f"{type(exc).__name__}: {exc}"
                            ),
                        )
                        logger.exception("Max cartridge rebalance failed")
                    return

        if getattr(self.config, "detonation_enabled", False):
            try:
                fired = await self._check_detonation_trigger(ticker)
                if fired:
                    await self._execute_detonation(ticker)
                    return
            except Exception as exc:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"DETONATION: check/execute raised: " f"{exc}. Continuing tick."
                    ),
                )
                logger.exception("Detonation raised")

        if current_value < self._target_balance * 0.01:
            try:
                _fresh_bal = await self._get_balance(self.config.target_asset)
                _fresh_units = float(_fresh_bal.free or 0)
            except Exception as _fb_exc:
                _fresh_units = None
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INITIAL ENTRY: fresh balance fetch raised "
                        f"({type(_fb_exc).__name__}: {_fb_exc}). "
                        f"Falling back to internal state. If phantom-"
                        f"buy appears, check exchange UI directly."
                    ),
                )

            if _fresh_units is not None:
                _qrate = float(self._quote_to_usd or 1.0)
                _attributed_units = sum(
                    float(lot.get("units", 0) or 0) for lot in self._main_lots
                )
                _fresh_units_eff = _attributed_units
                _fresh_usd = _attributed_units * ticker.last * _qrate

                if self._current_holdings > 0 and _fresh_units_eff == 0:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"INITIAL ENTRY BLOCKED (Phase-B guard a): "
                            f"attributed units 0 but saved state "
                            f"holds {self._current_holdings:.6f} "
                            f"units "
                            f"(~${self._current_holdings * ticker.last * _qrate:.2f}). "
                            f"Refusing buy on top of existing position. "
                            f"Clear saved state manually before restart."
                        ),
                    )
                    return

                _value_threshold = max(
                    self._target_balance * 0.25, max(self._target_balance * 0.01, 1.0)
                )
                if _fresh_usd >= _value_threshold:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"INITIAL ENTRY BLOCKED (Phase-B guard b): "
                            f"fresh USD value ${_fresh_usd:.2f} "
                            f"({_fresh_units_eff:.6f} {self.config.target_asset} "
                            f"@ ${ticker.last:.8f}) ≥ threshold "
                            f"${_value_threshold:.2f}. Not empty — let "
                            f"the regular scrum/fold cycle handle this "
                            f"position instead of initial entry."
                        ),
                    )
                    return

                if getattr(self.config, "position_ceiling_enabled", False):
                    try:
                        _smart_mult = float(
                            getattr(self.config, "position_ceiling_multiple", 1.0)
                        )
                        _smart_mult = max(1.0, min(10.0, _smart_mult))
                        _smart_ceiling_usd = self._anchor_target_balance * _smart_mult
                        _prospective = _fresh_usd + self._target_balance
                        if _prospective > _smart_ceiling_usd:
                            self._bus.emit(
                                "bot.log",
                                bot_id=self.bot_id,
                                message=(
                                    f"INITIAL ENTRY BLOCKED "
                                    f"(Smart Ceiling): prospective "
                                    f"position ${_prospective:.2f} "
                                    f"(existing ${_fresh_usd:.2f} + "
                                    f"buy ${self._target_balance:.2f}) "
                                    f"would exceed Smart Ceiling "
                                    f"${_smart_ceiling_usd:.2f} "
                                    f"(anchor "
                                    f"${self._anchor_target_balance:.2f} "
                                    f"× {_smart_mult:.1f}x). "
                                    f"Refusing buy."
                                ),
                            )
                            return
                    except (TypeError, ValueError, AttributeError) as _sup:
                        logger.debug(
                            "suppressed in %s: %s: %s",
                            "tick",
                            type(_sup).__name__,
                            _sup,
                        )

            try:
                _quote_bal = await self._get_balance(self.config.base_currency)
                _quote_free_raw = float(_quote_bal.free or 0)
            except Exception as _qb_exc:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INITIAL ENTRY BLOCKED: quote-currency balance "
                        f"fetch raised ({_qb_exc}). Retrying next tick."
                    ),
                )
                return

            _sibling_claims = self._sum_sibling_base_currency_claims()
            _quote_free = _quote_free_raw - _sibling_claims
            if _quote_free < 0:
                self._underfunded_log_counter = (
                    getattr(self, "_underfunded_log_counter", 0) + 1
                )
                if self._underfunded_log_counter % 60 == 1:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"INITIAL ENTRY BLOCKED (over-allocation): "
                            f"raw {self.config.base_currency} free "
                            f"${_quote_free_raw:.2f} − sibling claims "
                            f"${_sibling_claims:.2f} = "
                            f"${_quote_free:.2f} (negative). Operator has "
                            f"over-allocated capital across bots on this "
                            f"exchange. Refusing to fire until allocations "
                            f"are rebalanced. Reduce another bot's "
                            f"target_balance OR add base-currency funds OR "
                            f"pause a sibling bot to release its claim."
                        ),
                    )
                return

            if _quote_free < self._target_balance:
                self._underfunded_log_counter = (
                    getattr(self, "_underfunded_log_counter", 0) + 1
                )
                if self._underfunded_log_counter % 60 == 1:
                    _have_str = (
                        f"${_quote_free:.2f} after sibling claims "
                        f"${_sibling_claims:.2f} (raw ${_quote_free_raw:.2f})"
                        if _sibling_claims > 0
                        else f"${_quote_free:.2f}"
                    )
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"INITIAL ENTRY BLOCKED: insufficient "
                            f"{self.config.base_currency} — have "
                            f"{_have_str}, need "
                            f"${self._target_balance:.2f}. "
                            f"({self.config.target_asset} position: "
                            f"{self._current_holdings:.6f} @ "
                            f"${ticker.last:.8f} = "
                            f"${current_value:.2f})"
                        ),
                    )
                return
            self._underfunded_log_counter = 0

            candles = await self._get_ohlcv(symbol, self.config.ta_timeframe, limit=100)
            if candles and len(candles) >= 30:
                engine = VotingEngine()
                parsed = candles_from_raw(candles)
                summary = engine.compute_all(
                    parsed, self.config.ta_timeframe, symbol=self.config.symbol
                )
                self._last_summary = summary

                _wallet = (
                    f" [{self.config.base_currency}: ${_quote_free:.2f} · "
                    f"{self.config.target_asset}: "
                    f"{self._current_holdings:.6f} = "
                    f"${current_value:.2f}]"
                )

                _init_bb = detect_bb_proximity(
                    parsed,
                    tolerance_pct=self.config.bb_tolerance_pct,
                    consolidation_threshold=3.0,
                    min_pattern_candles=self.config.bb_landing_strip_candles,
                )
                if (
                    _init_bb is None
                    or _init_bb.upper <= 0
                    or _init_bb.lower <= 0
                    or _init_bb.upper <= _init_bb.lower
                ):
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"INITIAL ENTRY BLOCKED: BB data not yet "
                        f"computable — need proper band formation "
                        f"before entry. Price=${ticker.last:.8f}"
                        f"{_wallet}",
                    )
                    return

                _init_price = ticker.last
                _init_bb_width = _init_bb.upper - _init_bb.lower
                _init_bb_pos = (_init_price - _init_bb.lower) / max(
                    _init_bb_width, 1e-12
                )

                if _init_bb_pos > 0.30:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"INITIAL ENTRY BLOCKED: bb_pos="
                        f"{_init_bb_pos:.2f} > 0.30 — price too "
                        f"high in band for structural entry. "
                        f"Waiting for decline to lower third."
                        f"{_wallet}",
                    )
                    return

                _detect_pct_frac = self.config.scrum_detect_pct / 100.0
                _fire_pct_frac = self.config.scrum_fire_pct / 100.0
                _bb_mid_init = (_init_bb.upper + _init_bb.lower) / 2.0
                _lower_half = _bb_mid_init - _init_bb.lower
                _dist_down = (_bb_mid_init - _init_price) / max(_lower_half, 1e-12)
                _near_lower = (
                    abs(_init_price - _init_bb.lower) / max(_init_bb.lower, 1e-12)
                    <= _fire_pct_frac
                )

                if not (
                    _near_lower
                    or (_bb_mid_init - _init_price)
                    >= _detect_pct_frac * max(_lower_half, 1e-12)
                ):
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"INITIAL ENTRY BLOCKED: distance-down "
                        f"{_dist_down:.0%} < {_detect_pct_frac:.0%} "
                        f"and not within {_fire_pct_frac:.2%} of "
                        f"lower band. Price=${_init_price:.8f} "
                        f"(lower=${_init_bb.lower:.8f}, "
                        f"mid=${_bb_mid_init:.8f})"
                        f"{_wallet}",
                    )
                    return

                if summary.consensus_direction.name != "BEARISH":
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"INITIAL ENTRY BLOCKED: TA="
                        f"{summary.consensus_direction.name} "
                        f"({summary.consensus_confidence:.0%}) — "
                        f"need BEARISH (accumulation-trading "
                        f"thesis: buy decline, not rally). "
                        f"BB OK (pos={_init_bb_pos:.2f}, "
                        f"dist={_dist_down:.0%})."
                        f"{_wallet}",
                    )
                    return

                buy_cost = self._target_balance
                price = _init_price
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"INITIAL ENTRY: all 4 gates pass — "
                    f"BB OK, bb_pos={_init_bb_pos:.2f}, "
                    f"dist_down={_dist_down:.0%}, "
                    f"TA=BEARISH ({summary.consensus_confidence:.0%}). "
                    f"Acquiring ${buy_cost:.2f} of "
                    f"{self.config.target_asset} @ ${price:.8f}",
                )
                entry_fill = await self._execute_buy(
                    buy_cost,
                    price,
                    summary,
                    trace_context={
                        "path": "zero_balance_initial_entry",
                        "bb_pos": f"{_init_bb_pos:.3f}",
                        "dist_down": f"{_dist_down:.1%}",
                        "gate_current_value": f"${current_value:.6f}",
                        "gate_threshold": f"${self._target_balance * 0.01:.6f}",
                    },
                )
                if entry_fill is None or entry_fill <= 0:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"INITIAL ENTRY ABORTED: buy failed at "
                            f"${price:.8f}; no main_lots entry added. "
                            f"Bot will retry on next tick if gates "
                            f"still pass."
                        ),
                    )
                    return
                bought_units = buy_cost / entry_fill
                self._main_lots.append(
                    {
                        "units": bought_units,
                        "initial_buy_price": entry_fill,
                    }
                )
                _entry_usd = self._current_holdings * entry_fill
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INITIAL ENTRY COMPLETE: position=${_entry_usd:.2f} "
                        f"vs target=${self._target_balance:.2f}. "
                        f"(forensic: {self._current_holdings:.6f} "
                        f"{self.config.target_asset} filled @ ${entry_fill:.8f}, "
                        f"intended ${price:.8f})"
                    ),
                )
                self._bus.emit(
                    "trade.filled",
                    bot_id=self.bot_id,
                    side="buy",
                    type="ENTRY",
                    price=entry_fill,
                    amount=bought_units,
                    size=buy_cost,
                    profit=0.0,
                    operator_initiated=False,
                )
                self._emit_voting_panel_snapshot_at_fire(
                    side="BUY", trade_action="ENTRY"
                )
                self._emit_gate_decision_at_fire(side="BUY", trade_action="ENTRY")
            return

        self.stats.position_value = current_value

        delta = current_value - self._target_balance
        delta_pct = abs(delta) / (self._target_balance + 1e-9) * 100
        _interval_usd = (
            self._target_balance * self.config.scrumming_interval_pct / 100.0
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

        try:
            _live_px = float(getattr(ticker, "last", 0.0) or 0.0)
            if _live_px > 0:
                _cbx = float(
                    getattr(self.stats, "cost_basis_total_exchange", 0.0) or 0.0
                )
                if _cbx > 0:
                    _cost_basis = _cbx
                else:
                    _cost_basis = sum(
                        float(l.get("units", 0) or 0)
                        * float(l.get("initial_buy_price", 0) or 0)
                        for l in (getattr(self, "_main_lots", []) or [])
                    )
                _market_value = (
                    float(getattr(self, "_current_holdings", 0.0) or 0.0) * _live_px
                )
                self.stats.unrealised_pnl = _market_value - _cost_basis
        except Exception as _sup:
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        summary = None
        bb_result = None
        if len(candles) >= 30:
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

        below_interval = abs(delta) < _interval_usd

        if below_interval and self._fold_queue_usd == 0 and self._dist_accumulator == 0:
            ta_dir = summary.consensus_direction.name if summary else "N/A"
            ta_conf = f"{summary.consensus_confidence:.0%}" if summary else "—"
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"READ: ${ticker.last:.8f} | "
                f"Δ=${delta:+.4f} ({delta_pct:.1f}% < {self.config.scrumming_interval_pct}%) | "
                f"TA={ta_dir} ({ta_conf}) | holding",
            )
            self._last_price = ticker.last
            return

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=f"Delta: ${delta:+.4f} ({delta_pct:.1f}%) — "
            f"holdings=${current_value:.4f} vs target=${self._target_balance:.2f}"
            f"{' [BELOW INTERVAL — checking queues]' if below_interval else ''}",
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
            bb_confidence_boost = 0.15 + bb_result.consolidation_strength * 0.20
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
        if len(candles) >= 25:
            try:
                tightening = detect_landing_strip_v2(
                    candles,
                    min_consecutive=3,
                    shrink_threshold=0.90,
                    bb_tolerance_pct=3.0,
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

        # v3.26.x (issue #104) -- POSITION-AWARE MOMENTUM SKEWS THE
        # FLOOR. IT DOES NOT EDIT THE MEASUREMENT.
        #
        # This line read `eff_confidence += position_boost`.
        #
        # WHAT THE BLOCK IS FOR, from the record. DEVELOPMENT_CHRONICLE
        # carries the BONK insight of 2026-04-14 that created it --
        # "strong VX bullish AT the upper BB means the price is being
        # PUSHED into resistance with force. Best time to sell, not
        # worst." That is a statement about WHEN TO TRADE, and every
        # comment above says the same: "boost scrum", "great time to
        # scrum", "Bearish = good for scrum". It is a PRIORITY rule, and
        # it was written into a confidence.
        #
        # IT ADDS NO MEASUREMENT. Every signal it reads -- vortex, macd,
        # ichimoku, stochastic_rsi -- has already been counted by
        # `VotingEngine` into `summary.consensus_confidence`, each with a
        # weight of its own. This block re-reads those same votes and
        # grants a FLAT bonus for where inside the band the price sits.
        # A builder adds evidence; this re-spends evidence.
        #
        # AND IT OUTGREW WHAT IT ADJUSTED. Enumerating its own terms, the
        # ceiling is +0.40 and the floor is -0.29. The product manual
        # documents it as ±0.03 to ±0.20 -- deliberately under the 0.25
        # confidence floor, so that it could not carry a reading over the
        # gate by itself. The shipped arithmetic can, and the sweep
        # observed +0.4000 against a largest measured consensus
        # confidence of 0.3402.
        #
        # So the favour lands on the THRESHOLD now, together with the
        # other two. See `_skewed_confidence_floor` and the
        # `_eff_conf_floor` computation below.

        trend_hold = False
        trend_strength = 0.5
        if len(candles) >= 20:
            recent = candles[-20:]
            bull_count = sum(1 for c in recent if c.close > c.open)
            trend_strength = bull_count / len(recent)
            if trend_strength > _STRONG_TREND_MIN_BULL_SHARE:
                trend_hold = True
            # issue #133 unit 2 -- the fold-tranche count bound reads
            # this AFTER the override below has cleared `trend_hold`,
            # so it has to be the measurement and not the gate's
            # verdict. A sell that fires because band travel lifted
            # TREND-HOLD is a sell made during a strong trend, and that
            # is the exception. Written INSIDE the 20-candle branch: a
            # tick with fewer candles measured nothing, and the line
            # below leaves the count at 0 for it.
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
                bb_near = " NEAR UPPER"
            elif bb_result.near_lower:
                bb_near = " NEAR LOWER"

        # v3.26.x (issue #104) -- `+ BB 0.nn` READ AS AN ADDEND TO THE
        # CONFIDENCE PRINTED BESIDE IT, and until this change it was one.
        # Both favours now skew the FLOOR instead, so they are named as
        # skews and the confidence stands alone as the measurement it is.
        _skew_note = ""
        if position_boost or bb_confidence_boost:
            _skew_note = f", floor skew {position_boost:+.2f} pos" + (
                "" if not bb_confidence_boost else " %+.2f BB" % bb_confidence_boost
            )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=f"TA Vote: {summary.consensus_direction.name} "
            f"(conf={summary.consensus_confidence:.2f}"
            f"{_skew_note}, "
            f"B:{summary.bullish_count}/N:{summary.neutral_count}/"
            f"S:{summary.bearish_count})"
            f" | BB pos={bb_pos:.2f}{bb_near}",
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
                break  # Highest active TF wins — don't double-log

        # =================================================================
        # TRADE DECISION — Aligned with Simulator
        # =================================================================
        # SCRUM: delta > 0 + BULLISH TA → sell 100% delta → queue for fold
        # FOLD:  fold_queue > 0 + BEARISH TA + price dropped → buy back
        # DISTRIBUTE: dist_queue > 0 + BULLISH → sell excess
        # =================================================================
        # v3.13.8 MEM-191 / Chunk 7 — eff_confidence was hoisted above; here
        # we add bb_confidence_boost (computed inside the BB/landing-strip
        # block) to the already-position-boosted value. Previously this
        # line did 'eff_confidence = summary.consensus_confidence + boost',
        # which overwrote the position-aware adjustment from line 540.
        # v3.26.x (issue #104) -- THE BB/LANDING-STRIP FAVOUR SKEWS THE
        # FLOOR TOO. Same defect, same repair.
        #
        # This line read `eff_confidence += bb_confidence_boost`.
        #
        # WHY IT IS A FAVOUR AND NOT EVIDENCE. It is ONE-DIRECTIONAL --
        # a detected pattern only ever raises the confidence, never
        # lowers it -- and it raises the confidence used by BOTH
        # `is_bullish` and `is_bearish` at once, while the pattern that
        # granted it names ONE side in `bb_result.landing_strip_side`.
        # A reading that names one direction but favours both is not a
        # measurement of either. The landing-strip half is also already
        # honoured as a hard override further down, where
        # `landing_strip_side` sets `is_bullish` or `is_bearish` to True
        # regardless of any confidence, so its contribution here only
        # ever favoured a comparison that had already been decided.
        #
        # THE CEILING, DERIVED FROM SOURCE rather than from the tape.
        # The landing-strip term is `0.15 + consolidation_strength *
        # 0.20` and `consolidation_strength` is bounded to 1.0 twice in
        # `bb_proximity.py`, so that term tops out at +0.35. The
        # tightening term is `detect_landing_strip_v2`'s
        # `confidence_boost`, `0.08 + 0.17 * length_factor *
        # tightness_factor`, both factors bounded to 1.0, so it tops out
        # at +0.25. They are independent detections and both can fire on
        # one reading, so the sum reaches +0.60 -- more than twice the
        # floor it was compared against, and well past the +0.15 to
        # +0.35 the product manual documents. The 406-tablet sweep only
        # reached +0.1437, so this ceiling is derived and NOT observed;
        # it is stated that way on purpose.
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
        # v3.26.x (issue #102) — THE PRIORITY ARM RELAXES THE FLOOR. IT
        # DOES NOT EDIT THE MEASUREMENT, AND IT CAN STILL REFUSE.
        #
        # v3.15.64 wrote `eff_confidence += 0.30` here and then compared
        # the result against a 0.25 floor. That is `conf >= -0.05` on a
        # quantity bounded [0, 1]: the confidence conjunct had no false
        # case, so the arm was the hard override the operator refused by
        # name on 2026-04-26. The addition also travelled — nine sites
        # below print `eff_confidence`, and they printed the inflated
        # number rather than the measured one.
        #
        # Both halves are the same mistake: a favour was written as an
        # edit to a measurement. It is now written as what the operator
        # called it, a prioritisation, and it lands on the THRESHOLD.
        # `_BB_PRIORITY_CONFIDENCE_FLOOR` carries the derivation and the
        # reason the relaxation is proportional rather than subtractive.
        _bb_priority_arm = _bb_priority_scrum_skew or _bb_priority_fold_skew
        # v3.26.x (issue #104) -- ALL THREE FAVOURS, IN ONE PLACE, ON THE
        # THRESHOLD. `position_boost` and `bb_confidence_boost` used to
        # be added to `eff_confidence` above; the BB-priority skew used
        # to be added here. They COMPOUND -- all three are computed on
        # every tick from the same reading, and the 406-tablet sweep
        # measured both of the first two positive together on 3 readings
        # and their sum past the floor that judged them on 73. Summing
        # them here keeps the MAGNITUDE of the favour exactly what the
        # added form gave, and changes only what it is applied to.
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
                        f"({'SCRUM' if _bb_priority_scrum_skew else 'FOLD'} "
                        f"side): bb_pos={bb_pos:.3f}, hysteresis OK, "
                        f"|Δ|=${abs(delta):.2f}≥interval. confidence "
                        f"{eff_confidence:.2f} UNCHANGED; floor "
                        f"{_TA_CONFIDENCE_FLOOR:.2f} → "
                        f"{_eff_conf_floor:.4f} "
                        f"(÷{1.0 + _ta_conf_skew:.2f} = 1 + BB-priority "
                        f"{_BB_PRIORITY_SKEW:+.2f} + position "
                        f"{position_boost:+.2f} + BB-confidence "
                        f"{bb_confidence_boost:+.2f}). Arm alone would be "
                        f"{_BB_PRIORITY_CONFIDENCE_FLOOR:.4f}. TA direction "
                        f"NOT flipped — actively-contradicting TA still "
                        f"gates trade, and a confidence under the relaxed "
                        f"floor still refuses it."
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
                    f"MEM-196 RIPE-HARVEST (v3.15.75, override via "
                    f"GateChain v3.18.13): Δ={delta_pct:.1f}% ≥ "
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
                    f"MEM-196 DEEP-FOLD (v3.15.75, override via "
                    f"GateChain v3.18.13): Δ={delta_pct:.1f}% ≥ "
                    f"interval {self.config.scrumming_interval_pct:.1f}% "
                    f"+ bb_pos={bb_pos:.2f} ≤ Lower Detect Threshold "
                    f"{_bb_lower_dt:.3f}. DeepFoldOverride will "
                    f"force-pass midline_fold + ta_bearish. MEM-171 "
                    f"per-tranche price-floor still enforced downstream."
                ),
            )

        detect_pct_frac = self.config.scrum_detect_pct / 100.0
        fire_pct_frac = self.config.scrum_fire_pct / 100.0

        target_fires = True
        if bb_result is not None and bb_result.upper > 0 and bb_result.lower > 0:
            _bb_mid = bb_result.middle
            _bb_upper = bb_result.upper
            _bb_lower = bb_result.lower
            _price = ticker.last
            if _price > _bb_mid:
                _side = "upper"
                _band_range = _bb_upper - _bb_mid
                _band_span = max(_band_range, 1e-12)
                _dist_abs = _price - _bb_mid
                _dist_to_band = _dist_abs / _band_span
                _near_band = abs(_price - _bb_upper) <= fire_pct_frac * _bb_upper
            else:
                _side = "lower"
                _band_range = _bb_mid - _bb_lower
                _band_span = max(_band_range, 1e-12)
                _dist_abs = _bb_mid - _price
                _dist_to_band = _dist_abs / _band_span
                _near_band = abs(_price - _bb_lower) <= fire_pct_frac * _bb_lower

            _prev_side = self._scrum_target_side
            _mode = self._scrum_target_mode

            if _prev_side is not None and _prev_side != _side:
                _mode = "search"

            if _mode == "search":
                if _near_band and abs(delta) >= _interval_usd * 0.5:
                    _mode = "fire"
                    self._scrum_target_side = _side
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: SEARCH→FIRE ({_side}) — fast move to band, "
                        f"Δ {delta_pct:.1f}% ≥ {self.config.scrumming_interval_pct * 0.5:.1f}%",
                    )
                elif (
                    _dist_abs >= detect_pct_frac * _band_span
                    and abs(delta) >= _interval_usd * 0.5
                ):
                    _mode = "track"
                    self._scrum_target_side = _side
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: SEARCH→TRACK ({_side}) — "
                        f"BB dist {_dist_to_band:.0%} ≥ {detect_pct_frac:.0%}",
                    )
            elif _mode == "track":
                if _near_band:
                    _mode = "fire"
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: TRACK→FIRE ({_side}) — "
                        f"within {fire_pct_frac:.2%} of BB band",
                    )
                elif _dist_abs < detect_pct_frac * 0.5 * _band_span:
                    _mode = "search"
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: TRACK→SEARCH — retreated "
                        f"(dist {_dist_to_band:.0%} < {detect_pct_frac * 0.5:.0%})",
                    )
            elif _mode == "fire":
                if not _near_band and _dist_abs >= detect_pct_frac * _band_span:
                    _mode = "track"
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: FIRE→TRACK ({_side}) — off band, "
                        f"still in detect zone (dist {_dist_to_band:.0%})",
                    )
                elif _dist_abs < detect_pct_frac * 0.5 * _band_span:
                    _mode = "search"
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: FIRE→SEARCH — retreated "
                        f"(dist {_dist_to_band:.0%} < {detect_pct_frac * 0.5:.0%})",
                    )

            self._scrum_target_mode = _mode
            target_fires = _mode == "fire"

        bullseye_upper = False
        bullseye_upper_wick = False
        bullseye_lower = False
        bullseye_lower_wick = False
        if (
            self.config.bb_bullseye_check
            and bb_result is not None
            and bb_result.upper > 0
            and bb_result.lower > 0
        ):
            _bp = ticker.last
            _touch_tol = 0.005
            _wick_tol = 0.002
            bullseye_upper = abs(_bp - bb_result.upper) / bb_result.upper < _touch_tol
            bullseye_lower = abs(_bp - bb_result.lower) / bb_result.lower < _touch_tol
            if candles and not bullseye_upper:
                _last_high = candles[-1].high
                bullseye_upper_wick = _last_high >= bb_result.upper * (1.0 - _wick_tol)
            if candles and not bullseye_lower:
                _last_low = candles[-1].low
                bullseye_lower_wick = _last_low <= bb_result.lower * (1.0 + _wick_tol)

        if bullseye_upper or bullseye_upper_wick:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"BULLSEYE UPPER ({'wick' if bullseye_upper_wick else 'close'}): "
                f"price ${ticker.last:.8f} at BB upper ${bb_result.upper:.8f}. "
                f"FIRE ramp in {self._scrum_target_mode.upper()}; "
                f"scrum fires only when ramp reaches FIRE.",
            )
        if bullseye_lower or bullseye_lower_wick:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"BULLSEYE LOWER ({'wick' if bullseye_lower_wick else 'close'}): "
                f"price ${ticker.last:.8f} at BB lower ${bb_result.lower:.8f}. "
                f"Fold decision governed by MEM-171 tranche gates.",
            )

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
                        f"below_interval(Δ={delta_pct:.1f}% < "
                        f"{self.config.scrumming_interval_pct}%)"
                    )
                if not is_bullish:
                    _blocked.append(f"not_bullish(dir={eff_direction.name})")
                if trend_hold:
                    _blocked.append("trend_hold")
                if not scrum_ok:
                    _blocked.append(
                        f"scrum_ok_false(bb_pos={bb_pos:.2f},"
                        f"phantom={self._phantom_locked})"
                    )
                if not target_fires:
                    _blocked.append("target_fires_false(detect/fire)")
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"HOLD w/ Δ=+{delta_pct:.1f}% "
                    f"(${current_value:.2f} vs target ${self._target_balance:.2f}): "
                    f"blocked by [{', '.join(_blocked) or 'unknown'}]. "
                    f"Tick #{self._hold_tick_counter}.",
                )

        if _ripe_scrum:
            if not is_bullish:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"MEM-196 RIPE-HARVEST OVERRIDE ta_bullish: "
                    f"raw is_bullish=False (dir={eff_direction.name}, "
                    f"conf={eff_confidence:.2f}, floor "
                    f"{_eff_conf_floor:.2f}) — "
                    f"RipeHarvestScrumOverride will force-pass.",
                )
            if not target_fires:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message="MEM-196 RIPE-HARVEST OVERRIDE target_fires: "
                    "raw target_fires=False (detect/fire SM) — "
                    "RipeHarvestScrumOverride will force-pass.",
                )
            if trend_hold:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"MEM-196 RIPE-HARVEST OVERRIDE trend_hold: "
                    f"raw trend_hold=True ({trend_strength:.0%}) — "
                    f"RipeHarvestScrumOverride will force-pass.",
                )
        if _deep_fold:
            if not is_bearish:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"MEM-196 DEEP-FOLD OVERRIDE ta_bearish: "
                    f"raw is_bearish=False (dir={eff_direction.name}, "
                    f"conf={eff_confidence:.2f}, floor "
                    f"{_eff_conf_floor:.2f}) — "
                    f"DeepFoldOverride will force-pass.",
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
                f"conf={eff_confidence:.2f}<{_eff_conf_floor:.2f})"
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
        self._emit_risk_gate_snapshot(
            "scrum", _scrum_chain_result, summary, float(ticker.last)
        )
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
            scrum_asset = abs(delta) / ticker.last
            try:
                self._emit_trade_fire_snapshot(
                    "scrum",
                    summary,
                    float(ticker.last),
                    decision_extra={
                        "delta": round(float(delta), 6),
                        "scrum_asset": round(float(scrum_asset), 8),
                        "overrides_applied": list(
                            getattr(_scrum_chain_result, "overrides_applied", []) or []
                        ),
                    },
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )

            _scrum_skipped_below_min = False
            try:
                _qrate_for_cost = float(self._quote_to_usd or 1.0)
                _scrum_notional_usd = scrum_asset * float(ticker.last) * _qrate_for_cost
                _min_amt_sc, _min_cost_sc, _ = await self._get_market_limits(
                    self.config.symbol
                )
                _below_min_cost_sc = (
                    _min_cost_sc > 0 and _scrum_notional_usd < _min_cost_sc
                )
                _below_min_amt_sc = (
                    _min_amt_sc > 0
                    and _scrum_notional_usd < _min_amt_sc * float(ticker.last)
                )
                if _below_min_cost_sc or _below_min_amt_sc:
                    _scrum_skipped_below_min = True
                    import time as _t_sc

                    _now_ts = _t_sc.time()
                    if (_now_ts - self._below_min_scrum_log_ts) >= 300.0:
                        self._below_min_scrum_log_ts = _now_ts
                        _reason_parts = []
                        if _below_min_cost_sc:
                            _reason_parts.append(
                                f"notional ${_scrum_notional_usd:.4f} < "
                                f"min_cost ${_min_cost_sc:.2f}"
                            )
                        if _below_min_amt_sc:
                            _reason_parts.append(
                                f"amount {scrum_asset:.8f} < "
                                f"min_amount {_min_amt_sc:.8f}"
                            )
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"SCRUM HELD (below min trade size): "
                                f"Target Delta ${abs(delta):.4f} = "
                                f"{scrum_asset:.8f} units × "
                                f"${float(ticker.last):.8f}. "
                                f"{self.config.symbol} blockers: "
                                f"{'; '.join(_reason_parts)}. "
                                f"Bot intentionally idle until "
                                f"conditions allow a tradeable "
                                f"size. (Throttled: next emit "
                                f"~5 min.)"
                            ),
                        )
            except Exception as _mc_exc:
                logger.debug(
                    "Bot %s SCRUM min_cost pre-check raised: %s "
                    "(falling through to normal _execute_sell)",
                    self.bot_id,
                    _mc_exc,
                )

            if _scrum_skipped_below_min:
                sell_fill = None
            else:
                sell_fill = await self._execute_sell(scrum_asset, ticker.last, summary)
            if sell_fill is None or sell_fill <= 0:
                if not _scrum_skipped_below_min:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"SCRUM ABORTED: sell failed for "
                            f"{scrum_asset:.6f} units @ ${ticker.last:.8f}. "
                            f"No tranches queued; main_lots unchanged; "
                            f"no fold profit claimed. Retry next tick."
                        ),
                    )
            else:
                # issue #133 unit 9b -- the venue credits the NET.
                # `scrum_asset * sell_fill` is the GROSS notional,
                # so every tranche built below was booked richer
                # than the wallet. The wire routing reads this too,
                # and the bot cannot route money it never received.
                scrum_usd = self._settled_sale_proceeds(
                    scrum_asset, sell_fill, label="SCRUM"
                )

                if self._fold_cycle_cap_consumed > 1e-9:
                    _prev_cap_consumed = self._fold_cycle_cap_consumed
                    self._fold_cycle_cap_consumed = 0.0
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD CYCLE RESET (SCRUM fired): "
                            f"Target Delta swung positive, sell "
                            f"event ends fold cycle. Growth Rate "
                            f"Cap consumed ${_prev_cap_consumed:.4f} "
                            f"this cycle — reset to $0.00. Next "
                            f"fold burst gets fresh cap budget."
                        ),
                    )

                _scrum_routed_total = self._route_scrum_proceeds_via_wires(
                    scrum_usd=scrum_usd, sell_fill=sell_fill, label="scrum"
                )

                scrum_usd = scrum_usd - _scrum_routed_total

                self._main_lots.sort(key=lambda l: l["initial_buy_price"], reverse=True)
                _tranche_count_before = len(self._fold_tranches)
                _units_remaining = scrum_asset
                _first_new_tranche = None
                for _lot in list(self._main_lots):
                    if _units_remaining <= 1e-12:
                        break
                    _take = min(_lot["units"], _units_remaining)
                    if _take <= 1e-12:
                        continue
                    _t_usd = (_take / scrum_asset) * scrum_usd
                    _new_tr = {
                        "usd": _t_usd,
                        "units": _take,
                        "ref": sell_fill,
                        "initial_buy_price": _lot["initial_buy_price"],
                        "created_ts": time.time(),
                    }
                    self._fold_tranches.append(_new_tr)
                    self._tranches_created_lifetime += 1
                    if _first_new_tranche is None:
                        _first_new_tranche = _new_tr
                    _lot["units"] -= _take
                    _units_remaining -= _take
                    if _lot["units"] <= 1e-12:
                        self._main_lots.remove(_lot)

                # issue #133 unit 2 -- BEFORE the absorb, so the parked
                # credit lands in the record that survives, and before
                # the ratio and the top-up, so both read a slice of one.
                # `_first_new_tranche` is re-read from the list because
                # the merge replaces the object the loop above kept.
                if self._bound_new_fold_tranches(_tranche_count_before):
                    _first_new_tranche = self._fold_tranches[_tranche_count_before]

                # P1b Session 26 (2026-04-24) — if there were pending
                # wire credits parked before this scrum (target bot had
                # no tranches when a wire income arrived), absorb them
                # into the FIRST new tranche of this scrum burst. Only
                # applies when this scrum actually created at least one
                # new tranche AND there were zero tranches prior (wait-
                # for-new-tranche semantic per operator directive).
                if (
                    _first_new_tranche is not None
                    and _tranche_count_before == 0
                    and self._pending_wire_credits > 0
                ):
                    self._absorb_pending_wire_credits_into(_first_new_tranche)

                self._apply_scrum_fold_pct(
                    _tranche_count_before, scrum_usd, scrum_asset
                )

                self._top_up_remnant_fold_tranches(
                    _tranche_count_before,
                    float(getattr(bb_result, "lower", 0.0) or 0.0),
                    float(getattr(bb_result, "upper", 0.0) or 0.0),
                )

                self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)
                self._fold_queue_ref_price = sell_fill
                self.stats.trade_volume += scrum_usd

                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"SCRUM: Target=${self._target_balance:.2f}, "
                    f"Value=${current_value:.2f} (+{delta_pct:.1f}%), "
                    f"sold {scrum_asset:.6f} (${scrum_usd:.4f}) on "
                    f"{eff_direction.name} (conf={eff_confidence:.2f}"
                    f"≥floor {_eff_conf_floor:.2f}, "
                    f"pos_skew={position_boost:+.2f}, bb={bb_pos:.0%}). "
                    f"Fill=${sell_fill:.8f}, queued ${scrum_usd:.4f} for fold.",
                )
                self._bus.emit(
                    "trade.filled",
                    bot_id=self.bot_id,
                    side="sell",
                    type="SCRUM",
                    price=sell_fill,
                    amount=scrum_asset,
                    size=scrum_usd,
                    profit=0,
                )
                self._emit_voting_panel_snapshot_at_fire(
                    side="SELL", trade_action="SCRUM"
                )
                self._emit_gate_decision_at_fire(side="SELL", trade_action="SCRUM")
                try:
                    _avg_entry_for_pnl = 0.0
                    if self._main_lots:
                        _tu = sum(
                            float(l.get("units", 0) or 0) for l in self._main_lots
                        )
                        if _tu > 0:
                            _avg_entry_for_pnl = (
                                sum(
                                    float(l.get("units", 0) or 0)
                                    * float(l.get("initial_buy_price", 0) or 0)
                                    for l in self._main_lots
                                )
                                / _tu
                            )
                    _pct_vs_entry = 0.0
                    if _avg_entry_for_pnl > 0:
                        _pct_vs_entry = (
                            (sell_fill - _avg_entry_for_pnl)
                            / _avg_entry_for_pnl
                            * 100.0
                        )
                    self._bus.emit(
                        "pnl.event",
                        bot_id=self.bot_id,
                        data={
                            "kind": "SCRUM",
                            "asset": self.config.target_asset,
                            "symbol": self.config.symbol,
                            "units": float(scrum_asset),
                            "fill_price": float(sell_fill),
                            "usd_captured": float(scrum_usd)
                            * float(self._quote_to_usd or 1.0),
                            "avg_entry": float(_avg_entry_for_pnl),
                            "pct_vs_avg_entry": float(_pct_vs_entry),
                        },
                    )
                except Exception as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                    )
                _scrum_usd_true = float(scrum_usd) * float(self._quote_to_usd or 1.0)
                self.stats.total_scrummed_usd += _scrum_usd_true
                self.note_scrum_retention_usd(_scrum_usd_true)
                self._last_trade_side = "SCRUM"
                self._reset_opposing_hysteresis_after_fill()

                self._scrum_target_mode = "search"
                self._scrum_target_side = None
                self._last_trade_price = sell_fill

        elif delta > 0 and not below_interval and trend_hold:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"HOLD SCRUM: delta +${abs(delta):.4f} but TREND-HOLD active "
                f"({trend_strength:.0%} bullish) — riding the trend",
            )

        elif delta > 0 and not below_interval and not is_bullish:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"HOLD SCRUM: delta +${abs(delta):.4f} but TA={eff_direction.name} "
                f"conf={eff_confidence:.2f} (floor {_eff_conf_floor:.2f}) "
                f"— waiting for BULLISH",
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

        float(getattr(self.config, "max_target_growth_pct", 1.0))
        _anchor = float(getattr(self, "_anchor_target_balance", self._target_balance))
        _mem253_current_pos = float(self._current_holdings) * float(ticker.last)

        _mem253_at_smart_ceiling = False
        _mem253_smart_ceiling_usd = None
        if getattr(self.config, "position_ceiling_enabled", False):
            try:
                _smart_mult_253 = float(
                    getattr(self.config, "position_ceiling_multiple", 1.0)
                )
                _smart_mult_253 = max(1.0, min(10.0, _smart_mult_253))
                _mem253_smart_ceiling_usd = _anchor * _smart_mult_253
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
                        f"FOLD HOLD (Smart Ceiling): position "
                        f"${_mem253_current_pos:.2f} ≥ Smart Ceiling "
                        f"${_mem253_smart_ceiling_usd:.2f} "
                        f"(anchor ${_anchor:.2f} × multiple). "
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
                f"conf={eff_confidence:.2f}<{_eff_conf_floor:.2f})"
                if eff_direction in (SignalDirection.BEARISH, SignalDirection.NEUTRAL)
                else f"TA-not-bearish(dir={eff_direction.name})"
            )
        if not fold_ok_midline and not _deep_fold:
            _fold_blockers.append(f"fold_ok_midline=False(bb_pos={bb_pos:.2f})")
        if _mem253_at_ceiling:
            _fold_blockers.append("MEM-253-position-ceiling")
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

        try:
            self._fold_diag_tick += 1
            if self._fold_tranches:
                _per_tranche_eligible = len(
                    self._fold_eligible_tranches(ticker.last, _otd_factor)
                )
                _patent_only_eligible = sum(
                    1
                    for _t in self._fold_tranches
                    if ticker.last
                    <= float(_t.get("initial_buy_price", _t.get("ref", 0)))
                )
                _gate_armed_now = len(_fold_blockers) == 0

                if _per_tranche_eligible > 0 and not _gate_armed_now:
                    _blocker_key = "|".join(sorted(_fold_blockers))
                    if _blocker_key != self._fold_diag_last_blocker_set:
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"FOLD_DIAG_BLOCKED: "
                                f"{_per_tranche_eligible}/"
                                f"{len(self._fold_tranches)} tranches "
                                f"strict-eligible at ${ticker.last:.8f}, "
                                f"but FOLD gate refused. "
                                f"Blockers: [{', '.join(_fold_blockers)}]. "
                                f"State: bb_pos={bb_pos:.3f}, "
                                f"is_bearish={is_bearish}, "
                                f"fold_ok_midline={fold_ok_midline}, "
                                f"bb_below_lower_dt={_bb_below_lower_dt}, "
                                f"cycle_cap_consumed=${self._fold_cycle_cap_consumed:.4f}, "
                                f"last_grow_side={self._target_grow_last_side}, "
                                f"target_balance=${self._target_balance:.4f}, "
                                f"anchor=${self._anchor_target_balance:.4f}, "
                                f"profit_folding_active={self.config.profit_folding_active}."
                            ),
                        )
                        self._fold_diag_last_blocker_set = _blocker_key

                if self._fold_diag_tick % 100 == 0:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD_DIAG_SNAPSHOT (tick "
                            f"{self._fold_diag_tick}): "
                            f"{len(self._fold_tranches)} tranches queued, "
                            f"{_per_tranche_eligible} strict-eligible, "
                            f"{_patent_only_eligible} patent-only-eligible. "
                            f"Price=${ticker.last:.8f}, bb_pos={bb_pos:.3f}, "
                            f"is_bearish={is_bearish}, "
                            f"cycle_cap_consumed=${self._fold_cycle_cap_consumed:.4f}, "
                            f"last_grow_side={self._target_grow_last_side}, "
                            f"target_balance=${self._target_balance:.4f}, "
                            f"anchor=${self._anchor_target_balance:.4f}, "
                            f"closed_lifetime={self._tranches_closed_lifetime}, "
                            f"created_lifetime={self._tranches_created_lifetime}."
                        ),
                    )

                if _per_tranche_eligible == 0 and self._fold_diag_tick % 500 == 0:
                    _min_ref = min(
                        float(_t.get("ref", 0)) for _t in self._fold_tranches
                    )
                    _otd_diag = _otd_pct_for_gate
                    _activation = _min_ref * _otd_factor
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD_DIAG_NO_STRICT_ELIGIBLE: "
                            f"{len(self._fold_tranches)} tranches queued "
                            f"but 0 strict-eligible at "
                            f"${ticker.last:.8f}. "
                            f"Lowest tranche ref=${_min_ref:.8f}; with "
                            f"the {_otd_diag:.2f}% OTD gate the fold "
                            f"activates at or below "
                            f"${_activation:.8f} "
                            f"(price must fall a further "
                            f"{max(0.0, (ticker.last / _activation - 1.0) * 100.0):.2f}%)."
                            if _activation > 0
                            else f"FOLD_DIAG_NO_STRICT_ELIGIBLE: "
                            f"{len(self._fold_tranches)} tranches queued "
                            f"but 0 strict-eligible at ${ticker.last:.8f}; "
                            f"lowest tranche ref=${_min_ref:.8f}."
                        ),
                    )
        except Exception as _diag_exc:
            logger.debug("FOLD_DIAG emission failed: %s", _diag_exc)

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
        self._emit_risk_gate_snapshot(
            "fold", _fold_chain_result, summary, float(ticker.last)
        )
        if _fold_chain_result.should_fire:
            try:
                self._emit_trade_fire_snapshot(
                    "fold",
                    summary,
                    float(ticker.last),
                    decision_extra={
                        "delta": round(float(delta), 6),
                        "n_fold_tranches": len(self._fold_tranches or []),
                        "overrides_applied": list(
                            getattr(_fold_chain_result, "overrides_applied", []) or []
                        ),
                    },
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
            self._drop_malformed_fold_tranches()
            _eligible = self._fold_eligible_tranches(ticker.last, _otd_factor)
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD_DIAG_GATE_PASSED: TA-validated fold-back "
                        f"firing at ${ticker.last:.8f}. "
                        f"{len(_eligible)} of {len(self._fold_tranches)} "
                        f"tranches strict-eligible. "
                        f"cycle_cap_consumed=${self._fold_cycle_cap_consumed:.4f}, "
                        f"profit_folding_active={self.config.profit_folding_active}."
                    ),
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
            _excluded = 0
            _partial_count = 0
            _fold_plan: list[tuple[dict, float, float]] = []
            if _eligible:
                # v3.16.40 — Per-cycle fold-back capital soft cap
                # (operator directive 2026-05-08):
                #   "if I have enough lingering Folds that will
                #    immediately exceed my 10% growth rate, the
                #    amount needs to be soft-capped until the next
                #    lower BB touch is confirmed and we re-calculate
                #    the input as needed."
                #
                # When many lingering tranches become eligible at once,
                # soft-cap the deployed fold-back capital to the
                # configured per-cycle growth rate. Issue #106: that
                # rate is max_target_growth_pct of the target as the
                # cycle opened, NOT of the anchor. Excess tranches stay
                # queued for the NEXT TA-validated fold opportunity.
                # Sort highest-initial_buy_price-first so the most
                # expensive lots get fold-back priority (mirrors
                # SCRUM-side MEM-171 highest-priced-first consumption).
                # Issue #106 -- the admission bound compounds with the
                # cap it is a bound ON. This read
                # `self._anchor_target_balance * _max_growth_pct / 100`
                # and so admitted the same dollar of tranche capital on
                # a bot that had grown 27% as on the day it was made.
                # `_max_growth_pct` is still read because the emit below
                # names the percentage.
                _max_growth_pct = float(
                    getattr(self.config, "max_target_growth_pct", 1.0)
                )
                _cycle_cap_usd = self.cycle_growth_cap_usd
                # The base the property took, named so the emit below
                # can quote it without respelling the subtraction.
                _cycle_open_target = max(
                    0.0,
                    float(self._target_balance) - float(self._fold_cycle_cap_consumed),
                )
                # v3.20.62 — bug-1B fix: subtract what's already been
                # consumed this cycle so successive eligibility batches
                # respect the cumulative budget. Pre-fix, this site
                # used the FULL cap on every pass — the growth-
                # application path at line 7237 was correctly bounded
                # by cap_remaining, but the eligibility queue
                # over-allowed tranches that then applied $0 growth
                # silently. Operator-reported MEM-408: tranches firing
                # past the 3% cap with zero actual target growth.
                _cap_remaining_for_queue = max(
                    0.0, _cycle_cap_usd - self._fold_cycle_cap_consumed
                )
                _elig_sorted = sorted(
                    _eligible,
                    key=lambda _t: -float(
                        _t.get("initial_buy_price", _t.get("ref", 0))
                    ),
                )
                _fold_plan, _elig_capped, _partial_count = self._plan_fold_consumption(
                    _elig_sorted, _cap_remaining_for_queue
                )
                _running_usd = sum(_take for _, _take, _ in _fold_plan)
                _excluded = len(_eligible) - len(_elig_capped)
                if _excluded > 0 or _partial_count > 0:
                    _excluded_usd = (
                        sum(float(t.get("usd", 0) or 0) for t in _eligible)
                        - _running_usd
                    )
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD CYCLE-CAP: deploying "
                            f"${_running_usd:.2f} of "
                            f"${(sum(float(t.get('usd',0) or 0) for t in _eligible)):.2f} "
                            f"eligible, bounded by the per-cycle growth "
                            f"cap ${_cycle_cap_usd:.2f} "
                            f"(${_cap_remaining_for_queue:.2f} remaining "
                            f"after ${self._fold_cycle_cap_consumed:.2f} "
                            f"consumed this cycle, "
                            f"{_max_growth_pct}% of cycle-open target "
                            f"${_cycle_open_target:.2f}, "
                            f"anchor ${self._anchor_target_balance:.2f}). "
                            f"{_partial_count} tranche(s) part-consumed "
                            f"— each keeps its remaining balance and "
                            f"stays queued. {_excluded} of "
                            f"{len(_eligible)} left untouched. "
                            f"${_excluded_usd:.2f} stays queued in "
                            f"total for the next TA-validated fold "
                            f"opportunity."
                        ),
                    )
                _eligible = _elig_capped
            if _eligible:
                _taper = self.fold_rate_taper
                if _taper <= 0.0:
                    _ratio = self.ceiling_ratio or 0.0
                    _ceiling_pos_usd = (
                        self._current_holdings
                        * ticker.last
                        * float(self._quote_to_usd or 1.0)
                    )
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD BLOCKED by position ceiling: "
                            f"current ${_ceiling_pos_usd:.2f} "
                            f">= ceiling ${self.position_ceiling_usd:.2f} "
                            f"({_ratio*100:.1f}% of ceiling). "
                            f"Scrum still allowed."
                        ),
                    )
                    _eligible = []

            if _eligible:
                _fusd = sum(t["usd"] for t in _eligible)
                sum(t["units"] for t in _eligible)
                buy_cost = _fusd * _taper
                if _taper < 1.0:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD TAPER: ratio "
                            f"{(self.ceiling_ratio or 0)*100:.1f}% of "
                            f"ceiling → fold sized at {_taper*100:.0f}% "
                            f"of eligible (${_fusd:.4f} → "
                            f"${buy_cost:.4f})."
                        ),
                    )

                _fold_skipped_below_min = False
                try:
                    _qrate_fc = float(self._quote_to_usd or 1.0)
                    _fold_notional_usd = buy_cost * _qrate_fc
                    _min_amt_fc, _min_cost_fc, _ = await self._get_market_limits(
                        self.config.symbol
                    )
                    buy_cost / float(ticker.last) if ticker.last > 0 else 0.0
                    _below_min_cost_fc = (
                        _min_cost_fc > 0 and _fold_notional_usd < _min_cost_fc
                    )
                    _below_min_amt_fc = (
                        _min_amt_fc > 0 and buy_cost < _min_amt_fc * float(ticker.last)
                    )
                    if _below_min_cost_fc or _below_min_amt_fc:
                        _fold_skipped_below_min = True
                        import time as _t_fc

                        _now_ts_fc = _t_fc.time()
                        if (_now_ts_fc - self._below_min_fold_log_ts) >= 300.0:
                            self._below_min_fold_log_ts = _now_ts_fc
                            self._bus.emit(
                                "bot.log",
                                bot_id=self.bot_id,
                                message=(
                                    f"FOLD HELD (below min trade size): "
                                    f"{len(_eligible)} eligible tranche(s) "
                                    f"totaling ${_fusd:.4f} (tapered to "
                                    f"${buy_cost:.4f}) is below "
                                    f"{self.config.symbol} min_cost "
                                    f"${_min_cost_fc:.2f}. Bot intentionally "
                                    f"holding; tranches stay queued until "
                                    f"more accumulate or price moves "
                                    f"enough. (Throttled: next emit ~5 min.)"
                                ),
                            )
                except Exception as _mc_fold_exc:
                    logger.debug(
                        "Bot %s FOLD min_cost pre-check raised: %s "
                        "(falling through to normal _execute_buy)",
                        self.bot_id,
                        _mc_fold_exc,
                    )

                buy_asset = buy_cost / ticker.last
                asset_at_scrum = sum(t["usd"] / t["ref"] for t in _eligible)
                extra_asset = buy_asset - asset_at_scrum
                min_ref = min(t["ref"] for t in _eligible)
                pct_cheaper = (1 - ticker.last / min_ref) * 100
                accum_profit = extra_asset * ticker.last

                _intended_min_ref = min(t["ref"] for t in _eligible)

                if _fold_skipped_below_min:
                    buy_fill = None
                else:
                    buy_fill = await self._execute_buy(
                        buy_cost,
                        ticker.last,
                        summary,
                        trace_context={
                            "path": "fold_rebuy",
                            "eligible_tranches": len(_eligible),
                            "min_ref": f"${min_ref:.8f}",
                            "pct_cheaper": f"{pct_cheaper:.2f}%",
                        },
                    )
                if buy_fill is None or buy_fill <= 0:
                    if not _fold_skipped_below_min:
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"FOLD ABORTED: rebuy failed at "
                                f"${ticker.last:.8f} for "
                                f"{len(_eligible)} eligible tranches. "
                                f"Tranches stay queued; no profit booked; "
                                f"no hedge replenish. Will retry next "
                                f"tick."
                            ),
                        )
                    return

                buy_asset = buy_cost / buy_fill
                asset_at_scrum = sum(t["usd"] / t["ref"] for t in _eligible)
                extra_asset = buy_asset - asset_at_scrum
                pct_cheaper = (1 - buy_fill / _intended_min_ref) * 100
                accum_profit = extra_asset * buy_fill

                _total_elig_units = sum(t["units"] for t in _eligible) + 1e-12
                for _t in _eligible:
                    _share = _t["units"] / _total_elig_units
                    self._main_lots.append(
                        {
                            "units": buy_asset * _share,
                            "initial_buy_price": _t["initial_buy_price"],
                        }
                    )

                _pre_remove = len(self._fold_tranches)
                _removed, _n_spent = self._settle_fold_plan(_fold_plan)
                if _removed > 0:
                    self._tranches_closed_lifetime += _removed
                if _removed != _n_spent:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD DEQUEUE MISMATCH: {_n_spent} "
                            f"tranche(s) were drained to nothing but "
                            f"{_removed} left the queue. Likely "
                            f"concurrent mutation — investigate."
                        ),
                    )
                self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)
                if not self._fold_tranches:
                    self._fold_queue_ref_price = 0.0

                self.stats.trade_volume += buy_cost

                _new_surplus_usd = max(
                    0.0, accum_profit * float(self._quote_to_usd or 1.0)
                )

                # Issue #106 -- DIAGNOSTIC ONLY, and it still has to be
                # right. Nothing downstream enforces this value: the
                # drain below delegates to `_apply_fold_target_growth`,
                # which reads the cap itself. But this is the line an
                # operator greps to see what the budget WAS, so a stale
                # spelling here would report a cap the bot did not use.
                _cap_pct_growth = float(
                    getattr(self.config, "max_target_growth_pct", 1.0)
                )
                _cycle_cap_growth = self.cycle_growth_cap_usd
                _cycle_open_target_d = max(
                    0.0,
                    float(self._target_balance) - float(self._fold_cycle_cap_consumed),
                )

                try:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD_DIAG_SURPLUS_CHECK: "
                            f"buy_fill=${buy_fill:.8f}, "
                            f"holdings={self._current_holdings:.6f}, "
                            f"accum_profit=${float(accum_profit):.6f}, "
                            f"target=${self._target_balance:.4f}, "
                            f"new_surplus=${_new_surplus_usd:+.4f}, "
                            f"standing_surplus_in=${self._standing_surplus_usd:.4f}, "
                            f"cycle_budget=${_cycle_cap_growth:.4f} "
                            f"({_cap_pct_growth}% of cycle-open target "
                            f"${_cycle_open_target_d:.4f}, "
                            f"anchor ${self._anchor_target_balance:.4f}), "
                            f"profit_folding_active="
                            f"{self.config.profit_folding_active}."
                        ),
                    )
                except Exception as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                    )

                _growth_applied = self._apply_fold_target_growth(
                    accum_profit, source="auto"
                )

                try:
                    mgr = self._smart_wire_mgr
                    if (
                        mgr is not None
                        and _growth_applied > 0
                        and hasattr(mgr, "distribute_fold_profit")
                    ):
                        try:
                            self._bus.emit(
                                "bot.log",
                                bot_id=self.bot_id,
                                message=(
                                    f"[WIRE FIRE] fold-compound: "
                                    f"${_growth_applied:.4f} → "
                                    f"distribute_fold_profit "
                                    f"(from realized compound growth "
                                    f"@{buy_fill:.8f})"
                                ),
                            )
                        except Exception as _sup:  # noqa: BLE001
                            logger.debug(
                                "suppressed in %s: %s: %s",
                                "tick",
                                type(_sup).__name__,
                                _sup,
                            )
                        mgr.distribute_fold_profit(
                            source_id=self.bot_id,
                            profit_usd=float(_growth_applied),
                            ref=f"fold-compound@{buy_fill:.8f}",
                        )
                except Exception as _wr_exc:
                    logger.warning(
                        "Bot %s Smart Wire compound-route raised: %s "
                        "(fold profit still booked locally)",
                        self.bot_id,
                        _wr_exc,
                    )

                if (
                    self.config.hedge_rebalance_active
                    and self._hedge_balance_initial > 0
                    and self._hedge_bal < self._hedge_balance_initial
                    and _growth_applied > 0
                ):
                    _prev = self._hedge_bal
                    self._hedge_bal = min(
                        self._hedge_balance_initial,
                        self._hedge_bal + _growth_applied * 0.08,
                    )
                    _added = self._hedge_bal - _prev
                    if _added > 1e-9:
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=f"HEDGE REPLENISH: +${_added:.4f} from compound growth "
                            f"→ reserve now ${self._hedge_bal:.2f} "
                            f"(cap ${self._hedge_balance_initial:.2f})",
                        )

                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"FOLD: Bought ${buy_cost:.4f} @ ${buy_fill:.8f} "
                    f"(intended ${ticker.last:.8f}, "
                    f"{pct_cheaper:.1f}% below min tranche ref ${_intended_min_ref:.8f}). "
                    f"Accumulated +{extra_asset:.6f} extra asset. "
                    f"Profit: ${accum_profit:.4f}. "
                    f"Rebought {_n_spent} tranche(s) whole and "
                    f"part-consumed {_partial_count}, out of "
                    f"{_pre_remove} queued "
                    f"(others held by the OTD price gate: needs "
                    f"price <= ref x {_otd_factor:.4f}"
                    + (
                        f"; {_excluded} more were price-eligible "
                        f"but skipped by the per-cycle cap"
                        if _excluded
                        else ""
                    )
                    + ")",
                )
                self._bus.emit(
                    "trade.filled",
                    bot_id=self.bot_id,
                    side="buy",
                    type="FOLD",
                    price=buy_fill,
                    amount=(buy_cost / buy_fill) if buy_fill else 0.0,
                    size=buy_cost,
                    profit=_growth_applied,
                )
                self._emit_voting_panel_snapshot_at_fire(
                    side="BUY", trade_action="FOLD"
                )
                self._emit_gate_decision_at_fire(side="BUY", trade_action="FOLD")
                try:
                    _pct_token_gain = 0.0
                    if asset_at_scrum > 1e-12:
                        _pct_token_gain = extra_asset / asset_at_scrum * 100.0
                    self._bus.emit(
                        "pnl.event",
                        bot_id=self.bot_id,
                        data={
                            "kind": "FOLD",
                            "asset": self.config.target_asset,
                            "symbol": self.config.symbol,
                            "units_rebought": float(buy_asset),
                            "units_at_scrum_refs": float(asset_at_scrum),
                            "extra_asset": float(extra_asset),
                            "pct_token_gain": float(_pct_token_gain),
                            "fill_price": float(buy_fill),
                            "min_ref": float(min_ref),
                            "pct_cheaper_vs_ref": float(pct_cheaper),
                            "usd_spent": float(buy_cost)
                            * float(self._quote_to_usd or 1.0),
                            "growth_applied_usd": float(_growth_applied),
                        },
                    )
                except Exception as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                    )
                self.stats.total_folded_usd += float(buy_cost) * float(
                    self._quote_to_usd or 1.0
                )
                self.reset_swos_cycle()
                self._last_trade_side = "FOLD"
                self._last_trade_price = buy_fill
                self._reset_opposing_hysteresis_after_fill()

                if extra_asset > 0:
                    self._dist_accumulator += extra_asset

            else:
                _min_ref = min(t["ref"] for t in self._fold_tranches)
                _min_ibp = min(
                    t.get("initial_buy_price", t["ref"]) for t in self._fold_tranches
                )
                _binding = (
                    "initial_buy_price floor"
                    if ticker.last > _min_ibp
                    else "scrum ref gate"
                )
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"HOLD FOLD: BEARISH but {len(self._fold_tranches)} "
                    f"tranche(s) all gated — price ${ticker.last:.8f} "
                    f"above the binding gate ({_binding}; "
                    f"min_ref=${_min_ref:.8f}, min_ibp=${_min_ibp:.8f})",
                )

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
                    f"{eff_confidence:.2f} < {_eff_conf_floor:.2f} "
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

        # ═══════════════════════════════════════════════════════════════
        # v3.13.8 MEM-187 / Chunk 3 — HEDGE REBALANCE
        # ═══════════════════════════════════════════════════════════════
        #
        # Separate reserve buys during delta depletion. When the bot is
        # below target (delta<0), a bearish candle is still falling, and
        # price is in the lower BB region (bb_pos<0.40), deploy half the
        # hedge reserve to buy the dip. Replenished later from fold
        # profit (8% recycle, see Chunk 3 block above inside fold path).
        #
        # Ported from RAIntSimBat.py lines 2144-2159. Gap threshold: >= 1% of
        # target. Hedge buys append a new lot to _main_lots at current
        # fill price (MEM-171 compliance — the hedge buy's cost basis
        # becomes its future fold floor).
        #
        # Not gated by phantom lock or bb_midline_gate — hedge is downside
        # protection and must work in bearish regimes by design.
        #
        # THE GAP IS RE-READ HERE AND `delta` IS NOT USED. Issue #133
        # unit 6, operator rule: "when a buy is triggered, tranched
        # funds are considered first and are spent". They are — the fold
        # above runs first — but `delta` was measured at :9173, BEFORE
        # it, and the fold moves both of that subtraction's operands:
        # `_execute_buy` credits `_current_holdings` and
        # `_apply_fold_target_growth` raises `_target_balance`. Sizing
        # the reserve on the stale figure buys the same deficit twice,
        # so the tranche dollars bought the bot nothing and it paid two
        # fees instead of one. MEASURED on a 400-candle replay, one
        # tick, seed 20260825: gap $5.0627, the fold spent $1.0070 of
        # tranche capital and grew the target $0.0990, leaving $4.1617 --
        # and the reserve took $5.0955. See
        # tests/test_hedge_reserve_reads_the_gap_the_fold_left.py.
        #
        # Spelled exactly as the tick's own `current_value` at :8188 --
        # holdings x this tick's price x quote->USD. `position_value_usd`
        # is NOT used: it reads `_last_trade_price`, which the fold above
        # has just overwritten with its own fill.
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
                        )
                        self._emit_voting_panel_snapshot_at_fire(
                            side="BUY", trade_action="HEDGE"
                        )
                        self._emit_gate_decision_at_fire(
                            side="BUY", trade_action="HEDGE"
                        )
                        self._last_trade_price = hedge_fill

        if self._dist_accumulator > 0 and is_bullish:
            dist_asset = self._dist_accumulator
            try:
                bal = await self._get_balance(self.config.symbol.split("/")[0])
                dist_asset = min(dist_asset, bal)
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
            if dist_asset > 0:
                dist_fill = await self._execute_sell(dist_asset, ticker.last, summary)
                if dist_fill is None or dist_fill <= 0:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"DIST ABORTED: sell failed for "
                            f"{dist_asset:.6f} excess @ ${ticker.last:.8f}. "
                            f"Accumulator kept; no re-fold tranches "
                            f"created. Retry next tick."
                        ),
                    )
                else:
                    # issue #133 unit 9b -- the venue credits the
                    # NET, exactly as on the SCRUM path above.
                    dist_usd = self._settled_sale_proceeds(
                        dist_asset, dist_fill, label="DIST"
                    )
                    self.stats.trade_volume += dist_usd

                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"DIST: Sold {dist_asset:.6f} excess @ ${dist_fill:.8f} "
                        f"(intended ${ticker.last:.8f}) = ${dist_usd:.4f}",
                    )
                    self._bus.emit(
                        "trade.filled",
                        bot_id=self.bot_id,
                        side="sell",
                        type="DIST",
                        price=dist_fill,
                        amount=dist_asset,
                        size=dist_usd,
                        profit=dist_usd * 0.02,
                    )
                    self._emit_voting_panel_snapshot_at_fire(
                        side="SELL", trade_action="DIST"
                    )
                    self._emit_gate_decision_at_fire(side="SELL", trade_action="DIST")
                    self._last_trade_price = dist_fill

                    self._dist_accumulator = 0.0

                    if self.config.profit_folding_active:
                        self._main_lots.sort(
                            key=lambda l: l["initial_buy_price"], reverse=True
                        )
                        _dist_tranche_count_before = len(self._fold_tranches)
                        _units_remaining = dist_asset
                        for _lot in list(self._main_lots):
                            if _units_remaining <= 1e-12:
                                break
                            _take = min(_lot["units"], _units_remaining)
                            if _take <= 1e-12:
                                continue
                            _t_usd = (_take / dist_asset) * dist_usd
                            self._fold_tranches.append(
                                {
                                    "usd": _t_usd,
                                    "units": _take,
                                    "ref": dist_fill,
                                    "initial_buy_price": _lot["initial_buy_price"],
                                    "created_ts": time.time(),
                                }
                            )
                            self._tranches_created_lifetime += 1
                            _lot["units"] -= _take
                            _units_remaining -= _take
                            if _lot["units"] <= 1e-12:
                                self._main_lots.remove(_lot)
                        # issue #133 unit 2 -- a DIST sell is an
                        # opposing trade and builds tranches exactly as
                        # a SCRUM does, so it answers the same count
                        # rule. Ordered before the ratio and the top-up
                        # for the reason the SCRUM site gives.
                        self._bound_new_fold_tranches(_dist_tranche_count_before)
                        # 2026-08-12 — MIRRORED FROM THE SCRUM PATH.
                        # A DIST sell builds fold tranches exactly as a
                        # SCRUM does, so scrum_fold_pct governs it
                        # exactly as it governs a SCRUM. Before this,
                        # DIST proceeds queued 100% for fold whatever
                        # the setting said. `dist_usd` and `dist_asset`
                        # are the same two figures the build loop above
                        # divided, so the units test inside the helper
                        # reads this sale's own rate. Ordered before the
                        # top-up for the reason the helper gives.
                        self._apply_scrum_fold_pct(
                            _dist_tranche_count_before, dist_usd, dist_asset
                        )
                        self._top_up_remnant_fold_tranches(
                            _dist_tranche_count_before,
                            float(getattr(bb_result, "lower", 0.0) or 0.0),
                            float(getattr(bb_result, "upper", 0.0) or 0.0),
                        )
                        self._fold_queue_usd = sum(
                            t["usd"] for t in self._fold_tranches
                        )
                        self._fold_queue_ref_price = dist_fill
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=f"DIST proceeds ${dist_usd:.4f} queued for re-fold "
                            f"(tranche-provenance preserved, fill=${dist_fill:.8f})",
                        )

        self._last_price = ticker.last

    def _apply_scrum_fold_pct(
        self, _tranche_count_before: int, scrum_usd: float, scrum_asset: float
    ) -> None:
        """Scale the tranches THIS sell just appended by scrum_fold_pct.

        CALL IT BEFORE ``_top_up_remnant_fold_tranches``. The top-up
        merges this sale's money into an OLDER record, which sits
        outside the ``_tranche_count_before:`` slice. Merging first
        would let that money escape the ratio entirely.

        CALL IT BEFORE refreshing ``_fold_queue_usd``, so the derived
        scalar reports the queue that survived the ratio.

        Args:
            _tranche_count_before: ``len(self._fold_tranches)`` sampled
                before this sale's build loop ran. The slice from there
                to the end is exactly what this sale appended.
            scrum_usd: dollars this sale left with THIS bot, already net
                of Smart Wire routing, and the same figure the build
                loop divided.
            scrum_asset: units this sale sold, the same figure the build
                loop divided. The two together give the sale's own net
                rate, which is what tells scrum proceeds apart from
                wired-in money below.
        """
        _fold_pct = max(0, min(100, int(getattr(self.config, "scrum_fold_pct", 100))))
        _new_tranches = self._fold_tranches[_tranche_count_before:]
        if _fold_pct < 100 and _new_tranches:
            _fold_frac = _fold_pct / 100.0
            _rate_known = scrum_asset > 0
            _unit_rate = (scrum_usd / scrum_asset) if _rate_known else 0.0
            _skim_usd = 0.0
            _skim_cost_basis = 0.0
            _queued_usd = 0.0
            for _t in _new_tranches:
                _full_usd = _t["usd"]
                _full_units = _t["units"]
                _scrummed_usd = (
                    min(max(_full_units * _unit_rate, 0.0), _full_usd)
                    if _rate_known
                    else _full_usd
                )
                _wire_usd = _full_usd - _scrummed_usd
                _t["usd"] = _wire_usd + _scrummed_usd * _fold_frac
                _t["units"] = _full_units * _fold_frac
                _skim_units = _full_units * (1 - _fold_frac)
                _skim_proceeds = _scrummed_usd * (1 - _fold_frac)
                _skim_usd += _skim_proceeds
                _skim_cost_basis += _skim_units * _t["initial_buy_price"]
                _queued_usd += _t["usd"]
            _skim_profit = _skim_usd - _skim_cost_basis
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD RATIO: scrum_fold_pct={_fold_pct}% — "
                    f"queued ${_queued_usd:.4f} for "
                    f"fold, retired ${_skim_usd:.4f} as cash "
                    f"(realised profit ${_skim_profit:+.4f}). "
                    f"Cash buffer preserved against further drops."
                ),
            )

    def _plan_fold_consumption(
        self, eligible: list, cap_remaining: float
    ) -> tuple[list, list, int]:
        """Decide what this fold cycle takes from each tranche.

        Args:
          eligible: price-eligible tranches, already ordered
            highest-``initial_buy_price``-first by the caller.
          cap_remaining: room left under the per-cycle growth cap.

        Returns:
          (plan, slices, part-consumed count). ``plan`` is a list of
          ``(source tranche, usd taken, units taken)``.
        """
        plan: list[tuple[dict, float, float]] = []
        slices: list[dict] = []
        running_usd = 0.0
        partial_count = 0
        for _t in eligible:
            room = cap_remaining - running_usd
            if room <= 1e-12:
                break
            tranche_usd = float(_t.get("usd", 0) or 0)
            tranche_units = float(_t.get("units", 0) or 0)
            if tranche_usd <= 0.0 or tranche_units <= 0.0:
                continue
            if tranche_usd <= room + 1e-9:
                take_usd = tranche_usd
                take_units = tranche_units
            else:
                take_usd = room
                take_units = tranche_units * (take_usd / tranche_usd)
                partial_count += 1
            slices.append(
                {
                    "usd": take_usd,
                    "units": take_units,
                    "ref": float(_t.get("ref", 0) or 0),
                    "initial_buy_price": _t["initial_buy_price"],
                    "created_ts": _t.get("created_ts", 0.0),
                }
            )
            plan.append((_t, take_usd, take_units))
            running_usd += take_usd
        return plan, slices, partial_count

    def _drop_malformed_fold_tranches(self) -> int:
        """Remove every queued tranche whose ``ref`` is not above zero.

        Returns the number removed.

        WHY THIS IS A METHOD. It was eleven statements inside ``tick``,
        and ``tick`` needs a live ticker, a populated TA engine and an
        exchange to reach them. So the one removal site on the fold
        queue that no test could drive was also the one whose counters
        were wrong. Issue #98 defect 4.

        WHAT A MALFORMED TRANCHE IS. ``ref`` is the price the scrum
        sold at, and every fold divides by it. A record whose ``ref``
        is missing, zero, negative or ``nan`` fails
        ``t.get("ref", 0) > 0`` -- ``nan`` because every comparison
        against ``nan`` is False -- and it would otherwise raise out of
        ``sum(t["usd"] / t["ref"])`` and end the cycle.

        WHICH COUNTERS MOVE, AND WHY THAT CHANGED.

        * ``_tranches_discarded_lifetime`` moves UP by the number
          removed. THIS IS THE FIX. The drop used to move
          ``_tranches_malformed_dropped`` and nothing else, and that
          counter is not a term in the reconciliation the Fold-Tranche
          panel prints -- ``created - closed - discarded == standing``.
          A removal that moves no term of that identity leaves the
          standing count one lower than the counters predict, per
          record, forever. It is a NEGATIVE-drift write site, and every
          other removal on this queue already moves a term:
          ``_settle_fold_plan`` moves ``closed``, ``clear_fold_tranches``
          and ``run_despawn_sweep`` and the detonation reset move
          ``discarded``, and ``_top_up_remnant_fold_tranches`` moves
          ``created`` down by exactly what it removes.

        * ``_tranches_malformed_dropped`` moves UP by the same number,
          and it is now a SUB-COUNT of ``discarded`` rather than a
          fourth term. It answers "how many of the discards were
          unreadable", which is what the panel row reading "Tranches
          dropped as malformed" claims.

        * ``_tranches_closed_lifetime`` does NOT move, and must not. A
          closed tranche is one that FOLDED BACK. ``ref <= 0`` means
          the record never held a price to fold against, so counting
          it as folded would re-introduce the exact conflation
          v3.24.44 split apart.

        NOT DONE HERE, AND NAMED SO IT IS NOT MISTAKEN FOR AN OMISSION:
        ``_fold_queue_usd`` is not recomputed. The pre-existing code did
        not recompute it either, and the derived scalar agreed with the
        summed tranche ``usd`` on all 38 live bots when the panel was
        evaluated, so nothing is measured wrong today. Moving it is a
        second verb.
        """
        _malformed = [t for t in self._fold_tranches if not (t.get("ref", 0) > 0)]
        if not _malformed:
            return 0
        _dropped = len(_malformed)
        self._tranches_malformed_dropped = (
            int(getattr(self, "_tranches_malformed_dropped", 0) or 0) + _dropped
        )
        self._tranches_discarded_lifetime = (
            int(getattr(self, "_tranches_discarded_lifetime", 0) or 0) + _dropped
        )
        try:
            self.stats.tranches_discarded_lifetime = self._tranches_discarded_lifetime
        except AttributeError as exc:
            logger.debug("_drop_malformed_fold_tranches: stats mirror failed: %s", exc)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"FOLD GUARD: dropping {_dropped} malformed "
                f"tranche(s) with ref<=0. Operator visibility: "
                f"{_malformed}. Malformed-dropped now "
                f"{self._tranches_malformed_dropped}, and these "
                f"are counted as DISCARDED, never as closed."
            ),
        )
        self._fold_tranches = [t for t in self._fold_tranches if (t.get("ref", 0) > 0)]
        return _dropped

    def _settle_fold_plan(self, plan: list) -> tuple[int, int]:
        """Take from each source tranche what the plan says.

        This was
        ``[t for t in self._fold_tranches if t not in _eligible]``, a
        VALUE compare against the admitted list. Under partial
        consumption the fold buys from SLICES, and a PART-consumed
        slice does not equal its source, so that line would have left
        the source in the queue holding its whole balance and the bot
        would have rebought the same money on every later fold. On a
        WHOLE take the slice does still compare equal, which is the
        second defect below rather than a saving grace.

        Each source gives up what the plan took from it. A source
        drained to nothing is removed, exactly as a whole consumption
        removed it before. A source with a balance left STAYS, carrying
        the untouched ``initial_buy_price`` and ``ref`` it had on the
        way in -- the operator's "a tranche that does not spend all of
        its money just sits there minus what left".

        Removal is BY IDENTITY, not by value. The old ``not in``
        deleted every tranche that compared equal to an admitted one,
        so two tranches holding identical numbers -- routine after the
        proportional ``scrum_fold_pct`` rescale, which writes the same
        figure onto each new tranche cut from one lot -- meant one buy
        silently retired two records.

        Args:
          plan: ``(source tranche, usd taken, units taken)`` triples,
            as returned by ``_plan_fold_consumption``.

        Returns:
          (records removed from the queue, records drained to nothing).
        """
        pre_remove = len(self._fold_tranches)
        spent: set[int] = set()
        for src, took_usd, took_units in plan:
            src["usd"] = max(0.0, float(src.get("usd", 0) or 0) - took_usd)
            src["units"] = max(0.0, float(src.get("units", 0) or 0) - took_units)
            if src["usd"] <= 1e-9 or src["units"] <= 1e-12:
                spent.add(id(src))
            else:
                src["fold_partial_spent"] = True
        self._fold_tranches = [t for t in self._fold_tranches if id(t) not in spent]
        return pre_remove - len(self._fold_tranches), len(spent)

    def _top_up_remnant_fold_tranches(
        self, first_new_index: int, bb_lower: float, bb_upper: float
    ) -> tuple[int, float]:
        """Move a sell's new tranche money into a part-spent tranche.

        ``ref`` DOES blend, and it has to. Requiring a ``ref`` match too
        would make this dead code, because ``ref`` is a fill price and
        two fills are never equal. The blend is the one that preserves
        ``usd / ref``, the units-at-sale quantity the surplus step reads
        as ``asset_at_scrum``. Keeping the old ``ref`` would understate
        surplus; taking the new one would overstate it and invent
        compounding that did not happen.

        Args:
          first_new_index: index in ``_fold_tranches`` where this
            sell's own tranches start. Records before it are the
            candidates; records from it on are the new money.
          bb_lower: lower Bollinger band this tick. 0.0 when the tick
            had no BB reading.
          bb_upper: upper Bollinger band this tick.

        Returns:
          (tranches merged away, USD moved).
        """
        if not (bb_upper > bb_lower > 0.0):
            return 0, 0.0
        if first_new_index <= 0:
            return 0, 0.0
        _candidates = self._fold_tranches[:first_new_index]
        _fresh = self._fold_tranches[first_new_index:]
        _merged_away: set[int] = set()
        _merged_n = 0
        _merged_usd = 0.0
        for _new_t in _fresh:
            _new_usd = float(_new_t.get("usd", 0) or 0)
            _new_units = float(_new_t.get("units", 0) or 0)
            _new_ref = float(_new_t.get("ref", 0) or 0)
            if _new_usd <= 0.0 or _new_units <= 0.0 or _new_ref <= 0.0:
                continue
            _new_ibp = float(_new_t.get("initial_buy_price", 0.0) or 0.0)
            _best = None
            _best_ref = 0.0
            for _cand in _candidates:
                if not _cand.get("fold_partial_spent"):
                    continue
                if float(_cand.get("usd", 0) or 0) <= 0.0:
                    continue
                if float(_cand.get("initial_buy_price", 0.0) or 0.0) != _new_ibp:
                    continue
                _c_ref = float(_cand.get("ref", 0) or 0)
                if not (bb_lower <= _c_ref <= bb_upper):
                    continue
                if _best is None or _c_ref < _best_ref:
                    _best = _cand
                    _best_ref = _c_ref
            if _best is None:
                continue
            _b_usd = float(_best.get("usd", 0) or 0)
            _b_ref = float(_best.get("ref", 0) or 0)
            _units_at_sale = (_b_usd / _b_ref) + (_new_usd / _new_ref)
            _best["usd"] = _b_usd + _new_usd
            _best["units"] = float(_best.get("units", 0) or 0) + _new_units
            _best["ref"] = _best["usd"] / _units_at_sale
            _merged_away.add(id(_new_t))
            _merged_n += 1
            _merged_usd += _new_usd
        if not _merged_away:
            return 0, 0.0
        self._fold_tranches = [
            t for t in self._fold_tranches if id(t) not in _merged_away
        ]
        self._tranches_created_lifetime = max(
            0, int(self._tranches_created_lifetime) - _merged_n
        )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"FOLD TOP-UP: ${_merged_usd:.4f} from this sell "
                f"went INTO {_merged_n} part-spent tranche(s) "
                f"instead of opening new ones — same "
                f"initial_buy_price, lowest ref inside the BB "
                f"range ${bb_lower:.8f}..${bb_upper:.8f}. "
                f"{len(self._fold_tranches)} tranche(s) open."
            ),
        )
        return _merged_n, _merged_usd

    def _strong_trend_now(self) -> bool:
        """Is the market in a strong trend, on the TREND-HOLD reading.

        THE ONE READER of ``_last_trend_bull_candles``, which ``tick``
        writes as the number of the last 20 candles that closed up.

        ON TWO COUNTS, NOT ON THE SHARE. TREND-HOLD asks
        ``bull_count / 20 > 13 / 20``; this asks ``bull_count > 13``.
        Over the closed domain -- ``bull_count`` is an integer in
        [0, 20] -- the two answer identically, and the integer form
        cannot round at its own threshold.

        A bot that has not measured the market holds 0 and reads False,
        and an unreadable count reads False as well. The exception
        LOOSENS a bound, so its default has to be off.
        """
        _n = as_finite_float(getattr(self, "_last_trend_bull_candles", 0))
        return _n is not None and _n > _STRONG_TREND_MIN_BULL_CANDLES

    def _bound_new_fold_tranches(self, first_new_index: int) -> int:
        """One sell opens one fold tranche, unless the trend is strong.

        issue #133 unit 2, operator rule 2026-08-25: "We should never
        see more Fold tranches than Scrums that have occurred except
        during strong trends."

        WHERE THE COUNT CAME FROM. All three build loops -- the SCRUM,
        the DIST sell and ``_execute_manual_rebalance`` -- append ONE
        tranche PER ``_main_lots`` entry they consume, so that each
        lot's ``initial_buy_price`` travels with its own units.
        ``_main_lots`` gains an entry on every buy, so one sell that
        walks twelve lots opens twelve tranches and the panel counts
        twelve. Measured on the operator's saved state 2026-08-25:
        16,042 tranches opened against 445 recorded sells across 38
        bots, 37 of the 38 above 1.0, and CHIP alone at 4,925 against
        461 exchange trades counting BOTH sides.

        CALLED ONCE PER SELL, DIRECTLY AFTER ITS BUILD LOOP, and it
        carries the sell counter for that reason: a caller cannot take
        the exception and forget to count the sell, because both
        decisions are made here.

        WHAT IS CONSERVED, AND WHY IT CAN BE. Every record in this slice
        came from ONE sale, so all of them carry that sale's fill as
        ``ref`` and the same USD-per-unit rate. ``usd`` and ``units``
        are summed in the order the build loop wrote them and come back
        bit-identical; ``usd / ref``, the units-at-sale quantity the
        surplus step reads, comes with them.

        ``initial_buy_price`` IS THE ONE FIELD THAT DIFFERS ACROSS THE
        SLICE, and the merged record takes it UNITS-WEIGHTED. That
        conserves ``units x initial_buy_price`` -- the term summed as
        the cost basis behind unrealised P/L, and summed again as the
        skim cost basis inside ``_apply_scrum_fold_pct``. Measured over
        20,000 synthetic sales of up to 60 lots each, prices 1e-8 to
        61234.5: every conserved quantity within 4.4e-16 relative.

        TAKING THE MINIMUM WAS THE OTHER CANDIDATE and it is refused by
        measurement. It would honour ``_top_up_remnant_fold_tranches``'s
        rule against averaging a floor, and on the same sweep it
        understates the merged cost basis by up to 91.6% -- a bot
        reporting profit it did not make. The floor that rule protects
        is not read on this path: v3.16.43 took ``initial_buy_price``
        out of the fold eligibility gate, which is ``ticker.last <= ref
        x (1 - OTD/100)`` and carries no basis term.
        ``_top_up_remnant_fold_tranches`` merges across DIFFERENT sells
        at different fills and is left exactly as it was.

        Args:
          first_new_index: index in ``_fold_tranches`` where this sell's
            own records start. Everything before it belongs to earlier
            sells and is not touched.

        Returns:
          The number of records removed. 0 when this sell opened fewer
          than two, and 0 under the strong-trend exception.
        """
        _fresh = self._fold_tranches[first_new_index:] if first_new_index >= 0 else []
        if not _fresh:
            return 0
        # The sell counted here OPENED a tranche. A sell that reached
        # the build loop and appended nothing -- no lots left to
        # consume -- is not a scrum this rule has to answer for.
        _sells = int(getattr(self, "_scrum_sells_lifetime", 0) or 0)
        self._scrum_sells_lifetime = _sells + 1
        if len(_fresh) < 2:
            return 0
        if self._strong_trend_now():
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD TRANCHE BOUND LIFTED: "
                    f"{self._last_trend_bull_candles} of the last "
                    f"{_STRONG_TREND_CANDLES} candles closed up, over "
                    f"the {_STRONG_TREND_MIN_BULL_CANDLES} that make a "
                    f"strong trend, so this sell keeps its "
                    f"{len(_fresh)} per-lot tranche(s)."
                ),
            )
            return 0

        # NAMED `_row_*` AND NOT `_t_*`. The SCRUM build loop already
        # binds `_t_usd` to `(_take / scrum_asset) * scrum_usd`, and
        # `ta_archetype` reads provenance per MODULE: a second meaning
        # for that name carries the first one's units into every
        # comparison here.
        _read = []
        for _t in _fresh:
            _row_units = as_finite_float(_t.get("units", 0.0))
            _row_usd = as_finite_float(_t.get("usd", 0.0))
            _row_ref = as_finite_float(_t.get("ref", 0.0))
            _row_basis = as_finite_float(_t.get("initial_buy_price", 0.0))
            _row = (_row_units, _row_usd, _row_ref, _row_basis)
            if any(_v is None for _v in _row):
                # A record this method cannot read is a record it must
                # not fold into another one. Merging would carry the
                # unreadable field into a good record and lose the bad
                # one; leaving the slice alone keeps the malformed row
                # where `_drop_malformed_fold_tranches` can see it.
                return 0
            if _row_units <= 0.0 or _row_ref <= 0.0:
                return 0
            _read.append(_row)

        # `math.fsum` and NOT `+=` or `sum`, on all four. This method
        # replaces N records with one, so the survivor's totals have to
        # be the totals of what it replaced, and an accumulation order
        # must not decide them. Measured on a 25-lot sale: a running
        # `+=` lands 2.8e-14 away from the true total on $147.03, which
        # is the accumulation drifting, not the money moving.
        # `math.fsum` is exactly rounded, so a second reader summing the
        # same records gets the same number.
        _usd = math.fsum(_r[1] for _r in _read)
        _units = math.fsum(_r[0] for _r in _read)
        _cost = math.fsum(_r[0] * _r[3] for _r in _read)
        _at_sale = math.fsum(_r[1] / _r[2] for _r in _read)
        _refs = {_r[2] for _r in _read}
        if _units <= 0.0 or _at_sale <= 0.0:
            return 0

        # One fill wrote every record here, so the set holds one price
        # and it is kept VERBATIM. Re-deriving it as ``usd / at_sale``
        # lands an ULP away and moves the ``ticker.last <= ref x
        # factor`` comparison at its own boundary. The derived form is
        # the fallback, and it is the one that preserves ``usd / ref``.
        _ref = _refs.pop() if len(_refs) == 1 else (_usd / _at_sale)
        _merged = dict(_fresh[0])
        _merged["usd"] = _usd
        _merged["units"] = _units
        _merged["ref"] = _ref
        _merged["initial_buy_price"] = _cost / _units
        if any(bool(_t.get("operator_initiated")) for _t in _fresh):
            # The operator touched part of this sale, so the surviving
            # record says so. The Fold Tranches table is the only
            # consumer of the tag; no gate, order or amount reads it.
            _merged["operator_initiated"] = True
        # REBOUND, not slice-assigned, and that is deliberate. This
        # method REMOVES records; it is a sibling of
        # `_top_up_remnant_fold_tranches` and
        # `_drop_malformed_fold_tranches` and it rebinds the way both of
        # them do. A subscript write to `_fold_tranches` is the shape
        # every build site uses, and the wiring scan in
        # `test_scrum_fold_pct_mirrored_on_every_path` reads it as one.
        self._fold_tranches = self._fold_tranches[:first_new_index] + [_merged]

        _removed = len(_fresh) - 1
        # These records were never separately opened, so the created
        # counter must not claim they were. Same reasoning as the
        # decrement in ``_top_up_remnant_fold_tranches``: leaving it up
        # breaks ``created - closed - discarded == standing``.
        _created = int(getattr(self, "_tranches_created_lifetime", 0) or 0)
        self._tranches_created_lifetime = max(0, _created - _removed)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"FOLD TRANCHE BOUND: this sell's {len(_fresh)} per-lot "
                f"tranche(s) opened as ONE record -- ${_usd:.4f} over "
                f"{_units:.6f} units at ref ${_ref:.8f}, cost basis "
                f"${_merged['initial_buy_price']:.8f}. "
                f"{self._scrum_sells_lifetime} sell(s) have opened "
                f"tranches; {len(self._fold_tranches)} open."
            ),
        )
        return _removed

    @staticmethod
    def _reconcilable_units(value: Any, label: str) -> tuple[float | None, str | None]:
        """One units reading as a finite, NON-NEGATIVE float, or a reason.

        Returns (number, None) when usable, (None, reason) when
        refused, the same shape as `_positive_observed_quantity`
        (:3134), `_finite_state_number` (:3199) and `_sum_lot_units`
        (:3245). Returning the refusal instead of raising is what lets
        `_reconcile_holdings` decline the whole audit before it writes
        anything.

        The restore paths coerce the same field more loosely, with
        `float(lot.get("units", 0) or 0)` (:6910, :7985). That
        divergence is deliberate and it runs one way only: this reader
        refuses a strict superset of what they refuse, so a book they
        loaded can be declined here, and a book declined here is never
        written to. The reverse -- a book this reader accepts that they
        would reject -- cannot happen.

        `-0.0` is a zero and is normalised to `0.0`, so no caller
        formats a negative zero into a log line.

        `float(10 ** 400)` raises OverflowError, which is neither
        ValueError nor TypeError, so it is caught by name. Reaching for
        `math.isfinite` instead does not help: the conversion raises
        before `isfinite` is ever evaluated, and `json.loads` parses a
        400-digit literal into exactly that int.
        """
        if type(value) is not int and type(value) is not float:
            return None, (
                f"{label} must be exactly an int or a float, "
                f"not a {type(value).__name__}; got {value!r}"
            )
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None, f"{label} is not a number; got {value!r}"
        if not math.isfinite(number):
            return None, f"{label} must be finite; got {number!r}"
        if number < 0.0:
            return None, f"{label} must be >= 0; got {number!r}"
        return number + 0.0, None

    def _reconcilable_lot_book(self) -> tuple[list[float] | None, str | None]:
        """Every lot's units, coerced, in book order — or a reason.

        The per-lot values are returned rather than only their total
        because the drift-down branch multiplies them one by one.
        Deriving them a second time down there would let two passes
        disagree about one book.

        NOT `_sum_lot_units` (:3245), and the difference is deliberate
        in both directions. That helper refuses a lot with no "units"
        key; here such a lot counts as ZERO, which is what the restore
        paths' `.get` already does (:6910, :7985). Refusing it instead
        would leave a bot permanently unreconcilable over a lot that
        holds nothing. It also returns a total only, and a total cannot
        be multiplied back into a book. Its contract is pinned by the
        atomicity check in `apply_extractor_tranche_return`, so it is
        left exactly as it is.

        ONE unreadable lot refuses the whole book: the correction is a
        single ratio applied to every lot, so a lot that cannot be read
        cannot be corrected around.

        The caller totals this with `sum`, not with a `+=` loop,
        because those two do not agree — CPython's `sum` applies
        Neumaier compensation to floats. On ORCA's real 48-lot book
        `sum` gives 54.053407815409216 and an accumulator loop gives
        54.05340781540922, one ULP apart. `sum` is what :6910 and :7985
        use to derive the scalar, so the audited total comes out
        bit-identical to theirs.
        """
        per_lot: list[float] = []
        for _index, _lot in enumerate(self._main_lots):
            if not isinstance(_lot, dict):
                return None, (
                    f"_main_lots[{_index}] must be a lot dict; "
                    f"got a {type(_lot).__name__}"
                )
            _raw = _lot.get("units", 0.0)
            _units, _why = self._reconcilable_units(
                _raw if _raw else 0.0, f"_main_lots[{_index}]['units']"
            )
            if _units is None:
                return None, _why
            per_lot.append(_units)
        return per_lot, None

    def _claimable_exchange_units(
        self, exchange_units: float
    ) -> tuple[float, float, float]:
        """``(claimable, personal_hold, sibling_tracked)`` for this asset.

        Lifted verbatim out of the drift-UP branch of
        ``_reconcile_holdings`` so ``bootstrap_exchange_state`` asks the
        same question the same way. The rule is unchanged:

            claimable = exchange - personal_hold_qty - sibling_tracked

        Both subtrahends are operator/bot DECLARATIONS, not inferences,
        and they are what preserves the 2026-07-27 ETH/BTC protection.

        FAIL CLOSED. An unreadable sibling total returns ``inf`` for the
        siblings, which drives ``claimable`` negative and claims
        nothing. Under-claiming costs a log line; over-claiming spends
        the operator's coins.
        """
        _personal = max(
            0.0, float(getattr(self.config, "personal_hold_qty", 0.0) or 0.0)
        )
        _sib_units = 0.0
        _mgr = getattr(self, "_bot_manager", None)
        if _mgr is not None:
            try:
                _sib_units = max(
                    0.0,
                    float(
                        _mgr.sum_sibling_tracked_units(
                            self.bot_id, self.config.target_asset
                        )
                    ),
                )
            except Exception as _sib_exc:  # R28-OK: fail closed
                logger.warning(
                    "Bot %s claimable units: sibling total unreadable "
                    "(%s) — claiming nothing this pass.",
                    self.bot_id,
                    _sib_exc,
                )
                _sib_units = float("inf")
        return (exchange_units - _personal - _sib_units, _personal, _sib_units)

    def _bootstrap_adopt_from_exchange(
        self, exchange_units: float, book_units: float, price: float, asset: str
    ) -> float | None:
        """Raise a restored book to the wallet at startup, once.

        Same ownership rule as the periodic reconcile, and the same lot
        writer, so a restart cannot re-introduce the figure that
        reconcile just corrected. Returns the units added, or ``None``
        when nothing was adopted.

        It lives in its own method rather than inline because the two
        branches it carries pushed ``bootstrap_exchange_state`` past
        the complexity ceiling, and both belong to one idea.
        """
        if book_units <= 0:
            return None
        _claimable, _personal, _sib = self._claimable_exchange_units(exchange_units)
        _adopt = min(exchange_units, _claimable)
        _gain = self._book_reconciliation_lot(_adopt, book_units, price)
        if _gain is None:
            return None
        _foreign = max(0.0, exchange_units - self._current_holdings)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"DRIFT UP (bootstrap): adopted the exchange balance. "
                f"internal={book_units:.8f} -> "
                f"{self._current_holdings:.8f} {asset} "
                f"(exchange={exchange_units:.8f}). Booked {_gain:.8f} "
                f"units as a reconciliation lot at ${float(price):.8f}. "
                + (
                    f"{_foreign:.8f} units left unclaimed (personal hold "
                    f"{_personal:.8f}, siblings {_sib:.8f})."
                    if _foreign > 1e-9
                    else "No units on this asset are spoken for elsewhere."
                )
            ),
        )
        logger.warning(
            "Bot %s bootstrap adopted %.8f %s from the exchange "
            "(book %.8f -> holdings %.8f, foreign %.8f)",
            self.bot_id,
            _gain,
            asset,
            book_units,
            self._current_holdings,
            _foreign,
        )
        return _gain

    def _book_reconciliation_lot(
        self, adopt_units: float, book_units: float, price: float
    ) -> float | None:
        """Write the top-up as a lot, then re-derive holdings from it.

        Returns the units added, or ``None`` when nothing was written.

        TWO THINGS THIS CLOSES, BOTH OF THEM IN THE ARITHMETIC.

        1. THE TOP-UP IS MEASURED FROM THE BOOK. The drift-UP branch
           measured it from ``internal_units``, which is
           ``max(scalar, book)``. Whenever the scalar leads the book
           those are different numbers, the lot written is short by the
           difference, and the invariant the adopt exists to keep --
           ``sum(l["units"] for l in _main_lots) == _current_holdings``
           -- comes out FALSE. Measured on the live BILL book with a
           scalar of 15000 against a 14131-unit book and a 15778-unit
           wallet: holdings 15778, book 14909, invariant_ok False. The
           delta is computed from the scalar and the scrum reads the
           book, so the two consumers disagree by 869 units.

        2. NO PRICE, NO LOT. The basis was written straight from
           ``stats.current_price`` with no test, and that field is 0.0
           on a bot that has not completed a priced tick -- a
           post-failure reconcile on a freshly restored bot reaches
           here. The same measurement books
           ``initial_buy_price: 0.0``, which is not a cheap entry, it
           is a lot that claims infinite profit against every price
           and can arm a sell that never should have armed. Refusing
           costs one cycle; the reconcile runs again.

        The scalar is re-derived by summing the book rather than
        assigned from ``adopt_units``, so the two counters agree bit
        for bit whatever the float addition did.
        """
        # NO READING IS NOT A QUANTITY. `nan` compares False against
        # every bound, so `nan <= 1e-9` falls THROUGH a guard written
        # as a comparison and writes a nan lot, a nan scalar and a nan
        # delta. The reconcile path cannot deliver one -- its inputs go
        # through `_reconcilable_lot_book` first -- but the bootstrap
        # path sums the book with a bare `float(lot.get(...))` and can.
        # A writer that is safe only when its caller validates is not
        # safe.
        for _reading in (adopt_units, book_units):
            try:
                if not math.isfinite(float(_reading)):
                    return None
            except (TypeError, ValueError):
                return None
        if adopt_units - book_units <= 1e-9:
            return None
        try:
            _basis = float(price)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(_basis) or _basis <= 0.0:
            return None
        _gain = adopt_units - book_units
        self._main_lots.append(
            {
                "units": _gain,
                "initial_buy_price": _basis,
                "operator_initiated": False,
                "reconciled_to_exchange": True,
            }
        )
        self._current_holdings = sum(
            float(lot.get("units", 0) or 0) for lot in self._main_lots
        )
        return _gain

    async def _reconcile_holdings(self, reason: str = "periodic") -> bool:
        """Re-fetch asset balance from the exchange and compare it to
        what this bot claims to hold. On drift above tolerance, log
        prominently and reset internal state to exchange reality.


        Returns True if reconciliation completed (with or without drift
        action). Returns False in three cases, all of which leave every
        counter and every lot untouched: the balance fetch itself
        failed (network blip; retry next scheduled interval), the
        exchange OMITTED the currency from its response so the venue
        holding is unknown rather than zero (`Balance.absent`), or one
        of the three inputs was outside the reconcilable domain
        (exactly an int or a float, finite, non-negative — see
        `_reconcilable_units`).

        Reason tags help the operator and post-hoc investigation know
        why reconciliation ran:
          "init"           — first-tick verification after bot start
          "periodic"       — every N ticks routine check
          "post_failure"   — after a trade attempt returned None
          "operator_req"   — explicitly requested via future GUI action
        """
        try:
            balance = await self._get_balance(self.config.target_asset)

            _venue_absent = bool(getattr(balance, "absent", False))
            _venue_raw = getattr(balance, "total", 0) or balance.free or 0.0
        except Exception as exc:
            logger.debug(
                "Bot %s reconcile fetch failed (%s): %s", self.bot_id, reason, exc
            )
            return False

        if _venue_absent:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"RECONCILE REFUSED ({reason}): exchange OMITTED "
                    f"{self.config.target_asset} from the balance "
                    f"response, so the venue holding is UNKNOWN, not "
                    f"zero. No lot was rescaled and no holdings were "
                    f"reset. Retrying next interval."
                ),
            )
            logger.warning(
                "Bot %s reconcile (%s) REFUSED — %s absent from exchange "
                "response; venue holding UNKNOWN, not zero. No lot was "
                "rescaled and no holdings were reset.",
                self.bot_id,
                reason,
                self.config.target_asset,
            )
            return False

        _lot_each, _why = self._reconcilable_lot_book()
        _readings: list[float] = []
        if _lot_each is not None:
            for _value, _label in (
                (_venue_raw, "exchange balance (total)"),
                (self._current_holdings, "_current_holdings"),
                (sum(_lot_each), "_main_lots total"),
            ):
                _number, _why = self._reconcilable_units(_value, _label)
                if _number is None:
                    break
                _readings.append(_number)
        if _lot_each is None or len(_readings) != 3:
            logger.warning(
                "Bot %s reconcile (%s) REFUSED — %s. No lot was "
                "rescaled and no holdings were reset.",
                self.bot_id,
                reason,
                _why,
            )
            return False
        exchange_units, _scalar_units, _lot_units = _readings
        internal_units = _lot_units if _lot_units > _scalar_units else _scalar_units

        drift_units = exchange_units - internal_units
        if internal_units > 0:
            drift_pct = abs(drift_units) / internal_units * 100.0
        elif exchange_units > 0:
            drift_pct = float("inf")
        else:
            drift_pct = 0.0

        _TOLERANCE_PCT = 0.5
        _tolerance_units = abs(internal_units) * _TOLERANCE_PCT / 100.0

        if abs(drift_units) <= _tolerance_units:
            logger.debug(
                "Bot %s reconcile (%s) aligned: internal=%.6f exchange=%.6f "
                "drift=%.4f (%.3f%%)",
                self.bot_id,
                reason,
                internal_units,
                exchange_units,
                drift_units,
                drift_pct,
            )
            return True

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"BALANCE DRIFT ({reason}): internal={internal_units:.6f} "
                f"exchange={exchange_units:.6f} "
                f"drift={drift_units:+.6f} ({drift_pct:.2f}%)."
            ),
        )
        # This line is emitted BEFORE either branch runs, so it states
        # the OBSERVATION only. It used to end "Resetting internal
        # state to exchange reality" and then the drift-UP branch
        # preserved instead -- two log lines one second apart saying
        # opposite things, 735 times on BILL alone. Each branch below
        # reports what it actually did.
        logger.warning(
            "Bot %s balance drift (%s): internal=%.6f exchange=%.6f "
            "drift=%+.6f (%.3f%%)",
            self.bot_id,
            reason,
            internal_units,
            exchange_units,
            drift_units,
            drift_pct,
        )

        if exchange_units < internal_units - 1e-9:
            if internal_units > 0 and self._main_lots:
                _ratio = exchange_units / internal_units
                for _lot, _units in zip(self._main_lots, _lot_each, strict=True):
                    _lot["units"] = _units * _ratio
                self._main_lots = [l for l in self._main_lots if l["units"] > 1e-12]
            self._current_holdings = exchange_units
        else:

            _surplus = max(0.0, exchange_units - internal_units)
            if _surplus > 1e-9:
                _claimable, _personal, _sib_units = self._claimable_exchange_units(
                    exchange_units
                )
                _adopt = min(exchange_units, _claimable)
                # v3.25.10 — measured from the BOOK, not from
                # `internal_units`. See `_book_reconciliation_lot`:
                # `internal_units` is `max(scalar, book)`, so a scalar
                # that leads the book wrote a lot short by the
                # difference and left `sum(lots) != _current_holdings`.
                _gain = _adopt - _lot_units
                _basis = float(
                    getattr(getattr(self, "stats", None), "current_price", 0.0) or 0.0
                )

                # ONE WRITER DECIDES, AND THE SENTENCE FOLLOWS IT.
                # The branch used to re-test the price itself, so the
                # message could describe an adopt the writer had
                # refused -- and `_basis` of `inf` passes `> 0`, is
                # refused inside the writer, and would then have
                # formatted `None` into the operator's line and raised
                # a TypeError out of the tick. The writer answers with
                # the units it wrote, or None, and the two branches
                # below read that answer.
                _written = (
                    self._book_reconciliation_lot(_adopt, _lot_units, _basis)
                    if _gain > 1e-9
                    else None
                )
                if _written is not None:
                    # Reconciliation lot. The units are real and on the
                    # exchange; only their cost basis is unknown, so it
                    # is booked at the price this reconcile ran at and
                    # flagged, rather than inventing a fill that never
                    # happened. The invariant every consumer relies on
                    # -- sum(_main_lots units) == _current_holdings --
                    # is what makes the delta computable, so the lot is
                    # appended in the same step that moves the scalar,
                    # and the scalar is re-derived from the book.
                    _gain = _written
                    _adopt = self._current_holdings
                    _foreign = max(0.0, exchange_units - _adopt)
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"DRIFT UP ({reason}): adopted the exchange "
                            f"balance. internal={internal_units:.8f} -> "
                            f"{_adopt:.8f} {self.config.target_asset} "
                            f"(exchange={exchange_units:.8f}). Booked "
                            f"{_gain:.8f} units as a reconciliation lot "
                            f"at ${_basis:.8f}. "
                            + (
                                f"{_foreign:.8f} units left unclaimed "
                                f"(personal hold {_personal:.8f}, "
                                f"siblings {_sib_units:.8f})."
                                if _foreign > 1e-9
                                else "No units on this asset are spoken for "
                                "elsewhere."
                            )
                        ),
                    )
                    logger.info(
                        "Bot %s drift UP (%s): adopted %.8f (was %.8f, "
                        "exchange %.8f, personal %.8f, siblings %.8f)",
                        self.bot_id,
                        reason,
                        _adopt,
                        internal_units,
                        exchange_units,
                        _personal,
                        _sib_units,
                    )
                elif _gain > 1e-9:  # claimable, but the writer refused
                    # v3.25.10 — the units are claimable but there is no
                    # price to book them at. A lot at a zero basis is
                    # not a cheap entry; it reads as infinite profit
                    # against every price and can arm a sell. Say so and
                    # keep the position, rather than write a number that
                    # was never observed.
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"DRIFT UP ({reason}): {_gain:.8f} "
                            f"{self.config.target_asset} on exchange is "
                            f"this bot's, but there is no usable price "
                            f"to book it at (internal={internal_units:.8f} "
                            f"exchange={exchange_units:.8f}). ADOPTION "
                            f"DEFERRED — stats.current_price reads "
                            f"{_basis:.8f}, and a lot booked without a "
                            f"real basis claims unlimited profit against "
                            f"every price. Retrying next cycle."
                        ),
                    )
                    logger.warning(
                        "Bot %s drift UP (%s): adoption of %.8f deferred "
                        "— stats.current_price is %.8f",
                        self.bot_id,
                        reason,
                        _gain,
                        _basis,
                    )
                else:
                    # Every surplus unit is spoken for. This is the
                    # 2026-07-27 case and it still refuses -- but it
                    # now says WHY, with the numbers that decided it.
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"DRIFT UP ({reason}): {_surplus:.8f} "
                            f"{self.config.target_asset} on exchange is "
                            f"not this bot's (internal="
                            f"{internal_units:.8f} exchange="
                            f"{exchange_units:.8f}). Personal hold "
                            f"{_personal:.8f}, sibling bots "
                            f"{_sib_units:.8f}. Preserving internal "
                            f"state."
                        ),
                    )
                    logger.info(
                        "Bot %s drift UP (%s): surplus=%.8f fully "
                        "attributed elsewhere — preserved internal=%.8f",
                        self.bot_id,
                        reason,
                        _surplus,
                        internal_units,
                    )
        return True

    # issue #133 unit 9b -- a CLASS-LEVEL default, not only an
    # `__init__` one. A sell must never raise `AttributeError` on a bot
    # built without `__init__`, and both the suite and the restore
    # paths build them that way. `None` is immutable and every write
    # goes to the instance, so no bot can read another bot's fee.
    _last_sell_venue_fee: Optional["SettledSellFee"] = None

    _SETTLED_FILL_DEFAULT_LABEL = "MANUAL FIRE"
    _SETTLED_FILL_LABELS = frozenset(
        (
            "MANUAL FIRE",
            "SCRUM",
            "DIST",
            "STACK",
        )
    )

    @classmethod
    def _settled_fill_label(cls, label: object) -> str:
        """Resolve ``label`` against the closed set above. Never raises.

        This runs AFTER an order is already placed. Raising on a bad
        label would abandon the accounting for a trade that really
        happened, which is strictly worse than logging the default.
        ``None`` and ``""`` are accepted and mean "use the default".
        Anything else unrecognised also degrades to the default, and
        says so in the developer log so the caller gets fixed.
        """
        if isinstance(label, str) and label in cls._SETTLED_FILL_LABELS:
            return label
        if label is not None and label != "":
            logger.warning(
                "settled-fill label %r is not one of %s; the operator "
                "log will read %s",
                label,
                sorted(cls._SETTLED_FILL_LABELS),
                cls._SETTLED_FILL_DEFAULT_LABEL,
            )
        return cls._SETTLED_FILL_DEFAULT_LABEL

    async def _settled_fill(
        self,
        order,
        symbol: str,
        requested_amount: float,
        quoted_price: float,
        label: str | None = None,
    ):
        """Re-read a just-placed order so accounting books the REAL fill.

        A market order is not settled the instant ``create_order``
        returns, so this polls briefly rather than reading once.

        ``label`` names the CALLER in that fallback line, drawn from a
        closed set (see ``_settled_fill_label``). It is ABSENT on the
        manual path, which keeps the message byte-identical to what the
        operator has always read there.

        Returns ``(fill_amount, fill_price, is_real)``.

        issue #133 unit 9b -- also records the venue's fee, taken from
        the SAME order object the accepted fill came from. That is the
        re-read order when a re-read is what settled, not the object
        the caller passed in. An ESTIMATE clears the record: the venue
        confirmed nothing, so there is no fee to book.
        """
        self._last_sell_venue_fee = None

        def _extract(o):
            if o is None:
                return 0.0, 0.0
            try:
                amt = float(getattr(o, "filled", 0) or 0)
            except (TypeError, ValueError):
                amt = 0.0
            try:
                px = float(getattr(o, "average", 0) or 0)
            except (TypeError, ValueError):
                px = 0.0
            return amt, px

        amt, px = _extract(order)
        if amt > 0 and px > 0:
            self._record_venue_fee(order, amt, px)
            return amt, px, True

        order_id = str(getattr(order, "id", "") or "")
        if order_id:
            for _attempt in range(3):
                try:
                    await asyncio.sleep(0.2)
                    fetched = await self.exchange.get_order(order_id, symbol)
                except Exception as exc:
                    logger.debug(
                        "settled-fill re-read failed for %s: %s", order_id, exc
                    )
                    break
                f_amt, f_px = _extract(fetched)
                if f_amt > 0 and f_px > 0:
                    self._record_venue_fee(fetched, f_amt, f_px)
                    return f_amt, f_px, True
                amt = f_amt or amt
                px = f_px or px

        est_amt = amt if amt > 0 else float(requested_amount or 0.0)
        est_px = px if px > 0 else float(quoted_price or 0.0)
        self._last_sell_venue_fee = None
        _label = self._settled_fill_label(label)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"{_label}: exchange reported no settled fill for "
                f"order {order_id or '?'}; booking the ESTIMATE "
                f"({est_amt:.6f} @ ${est_px:.8f}) instead of a "
                f"confirmed fill. Position accounting may drift from "
                f"the exchange until the next reconcile."
            ),
        )
        return est_amt, est_px, False

    def _venue_quote_currency(self) -> str:
        """The currency a sale is credited in, taken from the symbol."""
        _sym = str(getattr(self.config, "symbol", "") or "")
        _, _, _quote = _sym.partition("/")
        return _quote.strip().upper()

    def _record_venue_fee(self, order, units: float, price: float) -> None:
        """Store the fee the VENUE reported for a just-settled sell.

        issue #133 unit 9b. Called from the two places that hold a
        settled order object: `_execute_sell`, which serves SCRUM and
        DIST, and `_settled_fill`, which serves the manual paths. It
        reads `order.fee` and `order.fee_currency` only. The connector
        fills both from the venue's own `fee.cost` / `fee.currency`
        (`ccxt_connector.py:1661`), so nothing here is computed.

        A BUY clears the record instead of writing it. Sale proceeds
        are the only consumer and a buy fee is not a sale fee.

        WHAT REACHES THIS METHOD ON COINBASE, ESTABLISHED FROM SOURCE
        rather than from a live call. `ccxt.coinbase.create_order`
        returns `parse_order(response["success_response"])`, and that
        body carries four keys -- `order_id`, `product_id`, `side`,
        `client_order_id`. There is no `total_fees` in it, so
        `fee.cost` parses to None and `Order.fee` is 0.0 on EVERY
        just-placed Coinbase order. `fetch_order` is a different
        endpoint and its documented body does carry `total_fees`;
        whether Coinbase has settled a NON-ZERO value into it seconds
        after a market fill is unobserved and is not assumed here.

        So on live Coinbase the SCRUM and DIST paths, which read the
        placed order and never re-read it, record no fee and book the
        gross -- and say so, every time, in the operator's log. That
        is the specified no-fee behaviour, not a silent one. The
        manual paths re-read through `_settled_fill` and are the only
        ones a Coinbase fee can currently reach.

        Never raises. The order already executed, and losing the
        accounting for a real trade is worse than losing a fee.
        """
        _side = getattr(order, "side", None)
        _side_txt = str(getattr(_side, "value", _side) or "").lower()
        if _side_txt != "sell":
            self._last_sell_venue_fee = None
            return
        try:
            _units = float(units)
            _price = float(price)
        except (TypeError, ValueError):
            self._last_sell_venue_fee = None
            return
        try:
            _amount = float(getattr(order, "fee", 0) or 0)
            _currency = str(getattr(order, "fee_currency", "") or "")
        except (TypeError, ValueError):
            _amount = 0.0
            _currency = ""
        self._last_sell_venue_fee = SettledSellFee(
            units=_units,
            price=_price,
            fee_amount=_amount,
            currency=_currency.strip().upper(),
            reported=_amount > 0.0,
        )

    def _take_venue_fee(self, units: float, price: float) -> Optional[SettledSellFee]:
        """Consume the stored fee, and only for the fill it belongs to.

        Single use: the record is cleared whether or not it matched, so
        one venue fee can never be subtracted from two valuations. A
        record whose units or price disagree with the fill being valued
        belongs to some other order, so it is discarded rather than
        applied.
        """
        _rec = self._last_sell_venue_fee
        self._last_sell_venue_fee = None
        if _rec is None:
            return None
        try:
            _units = float(units)
            _price = float(price)
        except (TypeError, ValueError):
            return None
        if not math.isclose(_rec.units, _units, rel_tol=1e-9, abs_tol=1e-12):
            return None
        if not math.isclose(_rec.price, _price, rel_tol=1e-9, abs_tol=1e-12):
            return None
        return _rec

    def _settled_sale_proceeds(
        self, units: float, price: float, *, label: str
    ) -> float:
        """Value a settled sell at what the venue actually credited.

        issue #133 unit 9b. The three fold-tranche loops booked
        `units x fill_price`, the GROSS notional. A venue credits the
        NET: it keeps its fee out of the proceeds.

        THE NUMBERS, EACH WITH ITS PROVENANCE. Bot c8e5c5db,
        2026-08-26 21:50:57, 473 CHIP at $0.03376:

        * $15.96848 booked gross -- LOGGED, `trade.log` and
          `pnl/daily/2026-08-26.ndjson`, both carrying no fee field;
        * 1.2% -- the venue's own rate, read off Coinbase's CSV export
          of CHIP fills, 92 of 92 August 2026 fills at exactly 1.2000%
          of subtotal, both sides;
        * $15.77686 net -- INFERRED from those two. The export ends
          2026-08-20, so the credited amount for this trade itself is
          recorded nowhere and is not claimed as measured.

        Returns the gross MINUS the fee the venue reported. Books the
        gross, and emits the reason, when that fee cannot be used. It
        never falls back to `config.trading_fee_pct`: that value was
        1.6 on the measured trade and the venue charged 1.2, so a
        synthesised fee books a number the exchange never charged.
        """
        _units = float(units)
        _price = float(price)
        _gross = _units * _price
        _fee = self._take_venue_fee(_units, _price)
        _refusal = ""
        if _fee is None or not _fee.reported:
            _refusal = "the venue reported no fee"
        elif not _fee.currency:
            _refusal = "the venue named no fee currency"
        elif self._venue_quote_currency() and _fee.currency != (
            self._venue_quote_currency()
        ):
            _refusal = (
                f"the venue charged the fee in {_fee.currency}, not the "
                f"{self._venue_quote_currency()} this sale is credited in"
            )
        elif _fee.fee_amount >= _gross:
            _refusal = (
                f"the reported fee ${_fee.fee_amount:.5f} is not smaller "
                f"than the gross ${_gross:.5f}"
            )
        if _refusal:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"{label} PROCEEDS BOOKED GROSS ${_gross:.5f} for "
                    f"{_units:.6f} @ ${_price:.8f}: {_refusal}. No fee "
                    f"was subtracted and none was estimated. Tranches "
                    f"read richer than the wallet if the venue did "
                    f"charge one."
                ),
            )
            return _gross
        _net = _gross - _fee.fee_amount
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"{label} PROCEEDS BOOKED NET ${_net:.5f} for "
                f"{_units:.6f} @ ${_price:.8f}: gross ${_gross:.5f} "
                f"minus the ${_fee.fee_amount:.5f} {_fee.currency} fee "
                f"the venue reported."
            ),
        )
        return _net

    def _fold_discharge_order(self) -> list[dict]:
        """Queued tranches in discharge order; unreadable rows omitted.

        Sorts ``_fold_tranches`` in place by ``ref`` descending, rows
        whose ``ref`` is not a finite number last. Returns only the rows
        whose ``ref`` and ``units`` are both finite numbers -- the same
        rows in the same order as ``_preview_fold_growth``, which sizes
        the buy. Runs after the fill, so it raises on no row.
        """

        def _rank(t) -> float:
            # Total order. A row that cannot yield a finite ref sorts last.
            if not isinstance(t, dict):
                return float("-inf")
            try:
                _ref = float(t.get("ref", 0.0) or 0.0)
            except (TypeError, ValueError, OverflowError):
                return float("-inf")
            return _ref if math.isfinite(_ref) else float("-inf")

        self._fold_tranches.sort(key=_rank, reverse=True)

        _readable: list[dict] = []
        for _t in self._fold_tranches:
            if not isinstance(_t, dict):
                continue
            try:
                _ref = float(_t.get("ref", 0.0) or 0.0)
                _units = float(_t.get("units", 0.0) or 0.0)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(_ref) and math.isfinite(_units):
                _readable.append(_t)
        return _readable

    async def _execute_manual_rebalance(
        self, ticker, caller_intent: str = "manual_button"
    ) -> None:
        """Rebalance holdings to target in one shot.

        Invoked from tick() when self._manual_fire_pending is True
        (operator clicked Manual Fire), AND from two autonomous code
        paths that piggyback on the same rebalance-to-center math:
        Wire Stack Fire (L4213) and Max Cartridge Fire (L4477).

          - ``"manual_button"`` (default) — operator clicked Fire.
            Emits ``type="MANUAL_SCRUM"`` / ``"MANUAL_FOLD"`` with
            ``operator_initiated=True``.
          - ``"wire_stack"`` — autonomous Wire Stack Fire (L4213).
            Emits ``type="WIRE_STACK_SCRUM"`` / ``"WIRE_STACK_FOLD"``
            with ``operator_initiated=False``.
          - ``"max_cartridge"`` — autonomous Max Cartridge Fire
            (L4477). Emits ``type="CARTRIDGE_SCRUM"`` /
            ``"CARTRIDGE_FOLD"`` with ``operator_initiated=False``.

        Unknown values raise ``ValueError`` (fail-loud so the next
        caller can't silently inherit the wrong attribution).

        Semantic:
          - Computes delta_usd = current_value - target_balance at
            ticker.last
          - delta > 0 → sell delta/price asset at MARKET
          - delta < 0 → buy |delta|/price asset at MARKET (clipped by
            available USD)
          - |delta| within 1% dust band → no-op with operator log

        The operator_initiated flag makes operator-clicked trades
        visible to downstream audits (equity curve, P/L attribution,
        reconciliation tools) so a manual intervention doesn't look
        identical to an autonomous Wire Stack or Max Cartridge fire
        in the trade log.
        """

        _INTENT_MAP = {
            "manual_button": ("MANUAL_SCRUM", "MANUAL_FOLD", True),
            "wire_stack": ("WIRE_STACK_SCRUM", "WIRE_STACK_FOLD", False),
            "max_cartridge": ("CARTRIDGE_SCRUM", "CARTRIDGE_FOLD", False),
        }
        if caller_intent not in _INTENT_MAP:
            raise ValueError(
                f"_execute_manual_rebalance: unknown caller_intent "
                f"{caller_intent!r}; expected one of "
                f"{sorted(_INTENT_MAP)}"
            )
        _scrum_label, _fold_label, _operator_initiated = _INTENT_MAP[caller_intent]

        self._manual_fire_pending = False

        price = ticker.last
        if not price or price <= 0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message="MANUAL FIRE: no valid price; aborting.",
            )
            return

        try:
            await self._refresh_quote_to_usd()
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_execute_manual_rebalance",
                type(_sup).__name__,
                _sup,
            )
        _qrate = float(self._quote_to_usd or 1.0)

        current_value = self._current_holdings * price * _qrate
        delta_usd = current_value - self._target_balance
        dust = manual_fire_dust_band(self._target_balance)

        if caller_intent != "manual_button":
            try:
                _xbal = await self._get_balance(self.config.target_asset)
                _xunits = float(
                    getattr(_xbal, "total", 0) or getattr(_xbal, "free", 0) or 0.0
                )
                _absent = bool(getattr(_xbal, "absent", False))
            except Exception as _xb_exc:  # noqa: BLE001
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"AUTONOMOUS FIRE REFUSED: could not read "
                        f"{self.config.target_asset} balance to verify the "
                        f"position ({_xb_exc}). Gates are bypassed on this "
                        f"path, so an unverified position is not traded."
                    ),
                )
                return
            if _absent:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"AUTONOMOUS FIRE REFUSED: exchange OMITTED "
                        f"{self.config.target_asset} from its balance "
                        f"response, so the position cannot be verified."
                    ),
                )
                return
            _xvalue = _xunits * price * _qrate
            if abs(_xvalue - current_value) > dust:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"AUTONOMOUS FIRE REFUSED (position mismatch): this "
                        f"bot has {self._current_holdings:.6f} "
                        f"{self.config.target_asset} (${current_value:.2f}) "
                        f"but the exchange reports {_xunits:.6f} "
                        f"(${_xvalue:.2f}). Gates are bypassed on this path, "
                        f"so it will not trade on a disputed position. "
                        f"Intended {'SELL' if delta_usd > 0 else 'BUY'} of "
                        f"${abs(delta_usd):.2f} withheld."
                    ),
                )
                logger.warning(
                    "Bot %s autonomous fire refused: internal %.8f vs "
                    "exchange %.8f %s",
                    self.bot_id,
                    self._current_holdings,
                    _xunits,
                    self.config.target_asset,
                )
                return
            if delta_usd < 0:
                _growth = float(
                    getattr(self.config, "max_target_growth_pct", 0.0) or 0.0
                )
                _ceiling = float(self._target_balance) * (1.0 + _growth / 100.0)
                _prospective = _xvalue + abs(delta_usd)
                if _prospective > _ceiling + dust:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"AUTONOMOUS FIRE REFUSED (ceiling): buying "
                            f"${abs(delta_usd):.2f} would take the position "
                            f"to ${_prospective:.2f}, above the "
                            f"${_ceiling:.2f} cap (target "
                            f"${self._target_balance:.2f} x 1+{_growth:.1f}%)."
                        ),
                    )
                    logger.warning(
                        "Bot %s autonomous buy refused: prospective %.2f "
                        "> ceiling %.2f",
                        self.bot_id,
                        _prospective,
                        _ceiling,
                    )
                    return

        if abs(delta_usd) < dust:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MANUAL FIRE: already within dust band "
                    f"(|delta|=${abs(delta_usd):.4f} < "
                    f"${dust:.2f}). No-op."
                ),
            )
            return

        class _ManualSummary:
            consensus_confidence = 1.0
            direction = None
            raw_votes: dict = {}

            def __repr__(self) -> str:
                return "<ManualSummary operator_initiated=True>"

        _ManualSummary()

        if delta_usd > 0:
            _denom_sc = price * _qrate
            sell_amount = (delta_usd / _denom_sc) if _denom_sc > 0 else 0.0
            sell_amount = min(sell_amount, self._current_holdings)
            if sell_amount <= 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message="MANUAL FIRE: computed zero sell amount; abort.",
                )
                return

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MANUAL FIRE SCRUM: delta=+${delta_usd:.4f} "
                    f"over target → selling {sell_amount:.6f} "
                    f"{self.config.symbol.split('/')[0]} @ MARKET "
                    f"(~${price:.8f}) to rebalance."
                ),
            )

            order = await self.guarded_place_order(
                symbol=self.config.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                amount=sell_amount,
                price=None,
            )

            if order is None:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message="MANUAL FIRE SCRUM: exchange returned no order.",
                )
                return

            fill_amount, fill_price, _fill_is_real = await self._settled_fill(
                order, self.config.symbol, sell_amount, price
            )
            if fill_amount <= 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"MANUAL FIRE SCRUM: order placed but no "
                        f"filled amount reported (order.filled="
                        f"{getattr(order, 'filled', 'missing')}, "
                        f"order.amount={getattr(order, 'amount', 'missing')}). "
                        f"Aborting post-fill accounting; check exchange for actual state."
                    ),
                )
                return
            if fill_price <= 0:
                fill_price = price

            # issue #133 unit 9b -- the venue credits the NET,
            # exactly as on the SCRUM and DIST paths. `_settled_fill`
            # carried the fee from whichever order object settled.
            fill_usd = self._settled_sale_proceeds(
                fill_amount, fill_price, label=_scrum_label
            )
            self._current_holdings = max(0.0, self._current_holdings - fill_amount)

            _manual_routed_total = self._route_scrum_proceeds_via_wires(
                scrum_usd=fill_usd, sell_fill=fill_price, label="manual_scrum"
            )
            fill_usd = max(0.0, fill_usd - _manual_routed_total)

            self._main_lots.sort(key=lambda l: l["initial_buy_price"], reverse=True)
            _manual_tranche_count_before = len(self._fold_tranches)
            remaining = fill_amount
            new_tranches_count = 0
            for lot in list(self._main_lots):
                if remaining <= 1e-12:
                    break
                take = min(lot["units"], remaining)
                t_usd = (take / fill_amount) * fill_usd
                self._fold_tranches.append(
                    {
                        "usd": t_usd,
                        "units": take,
                        "ref": fill_price,
                        "initial_buy_price": lot["initial_buy_price"],
                        "operator_initiated": _operator_initiated,
                        "created_ts": time.time(),
                    }
                )
                self._tranches_created_lifetime += 1
                lot["units"] -= take
                remaining -= take
                if lot["units"] <= 1e-12:
                    self._main_lots.remove(lot)
                new_tranches_count += 1

            # issue #133 unit 2 -- the third build loop, same rule. Two
            # of this method's three callers fire autonomously, so
            # leaving it out would bound the count everywhere the
            # operator does not click and nowhere he does.
            new_tranches_count -= self._bound_new_fold_tranches(
                _manual_tranche_count_before
            )

            # 2026-08-12 — MIRRORED FROM THE SCRUM PATH. This method
            # serves three callers -- Manual Fire, Wire Stack and Max
            # Cartridge -- and two of the three fire autonomously, so
            # the gap was never "manual only". `fill_usd` is already net
            # of Smart Wire routing and is the same figure the build
            # loop divided, so the units test inside the helper reads
            # this sale's own rate. Runs before the _fold_queue_usd sum
            # below so the derived scalar reports the scaled queue.
            self._apply_scrum_fold_pct(
                _manual_tranche_count_before, fill_usd, fill_amount
            )

            _bb_last = getattr(self, "_last_bb", None)
            _merged_n, _ = self._top_up_remnant_fold_tranches(
                _manual_tranche_count_before,
                float(getattr(_bb_last, "lower", 0.0) or 0.0),
                float(getattr(_bb_last, "upper", 0.0) or 0.0),
            )
            new_tranches_count -= _merged_n

            self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)
            self.stats.total_trades += 1

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MANUAL FIRE SCRUM FILLED: {fill_amount:.6f} "
                    f"@ ${fill_price:.8f} = ${fill_usd:.4f}. "
                    f"{new_tranches_count} tranche(s) queued "
                    f"(operator_initiated). Holdings now "
                    f"{self._current_holdings:.6f} "
                    f"(~${self._current_holdings * price * float(self._quote_to_usd or 1.0):.2f})."
                ),
            )
            self._bus.emit(
                "trade.filled",
                bot_id=self.bot_id,
                data={
                    "type": _scrum_label,
                    "side": "SELL",
                    "amount": fill_amount,
                    "price": fill_price,
                    "usd": fill_usd,
                    "profit": 0.0,
                    "operator_initiated": _operator_initiated,
                },
            )
            self._emit_voting_panel_snapshot_at_fire(
                side="SELL", trade_action=str(_scrum_label or "MANUAL_SCRUM")
            )
            self._emit_gate_decision_at_fire(
                side="SELL", trade_action=str(_scrum_label or "MANUAL_SCRUM")
            )
            try:
                self._bus.emit(
                    "pnl.event",
                    bot_id=self.bot_id,
                    data={
                        "kind": "SCRUM",
                        "asset": self.config.target_asset,
                        "symbol": self.config.symbol,
                        "units": float(fill_amount),
                        "fill_price": float(fill_price),
                        "usd_captured": float(fill_usd)
                        * float(self._quote_to_usd or 1.0),
                        "operator_initiated": _operator_initiated,
                        "manual_kind": _scrum_label,
                    },
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_manual_rebalance",
                    type(_sup).__name__,
                    _sup,
                )
            _fill_usd_true = float(fill_usd) * float(self._quote_to_usd or 1.0)
            self.stats.total_scrummed_usd += _fill_usd_true
            self.note_scrum_retention_usd(_fill_usd_true)
            self._last_trade_side = "SCRUM"
            self._last_trade_price = fill_price
            self._reset_opposing_hysteresis_after_fill()

        else:

            if caller_intent != "manual_button" and self._fold_tranches:
                from .otd_math import (
                    fold_rebuy_factor,
                )

                _fold_factor = 1.0
                _best_rebuy = 0.0
                _distance_ok = False

                _unreadable_refs = 0
                _thresholds: list[float] = []
                try:
                    _fold_factor = fold_rebuy_factor(
                        getattr(self.config, "scrumming_interval_pct", 0) or 0,
                        getattr(self.config, "trading_fee_pct", 0.6) or 0.6,
                    )

                    for _t in self._fold_tranches:
                        _t_thresh = float(_t.get("ref", 0)) * _fold_factor
                        if not math.isfinite(_t_thresh):
                            _unreadable_refs += 1
                            continue
                        _thresholds.append(_t_thresh)
                    if _thresholds:
                        _best_rebuy = max(_thresholds)
                        _distance_ok = price <= _best_rebuy
                except (TypeError, ValueError, OverflowError) as _otd_exc:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"AUTONOMOUS FIRE REFUSED (opposing distance "
                            f"unreadable): {_otd_exc}. Gates are bypassed on "
                            f"this path, so a rebuy distance that cannot be "
                            f"computed is not traded. Intended BUY of "
                            f"${abs(delta_usd):.2f} withheld."
                        ),
                    )
                    logger.warning(
                        "Bot %s autonomous fold refused: opposing distance "
                        "unreadable: %s",
                        self.bot_id,
                        _otd_exc,
                    )
                    return
                _unread_tail = ""
                if _unreadable_refs:
                    _unread_tail = (
                        f" {_unreadable_refs} of the "
                        f"{len(self._fold_tranches)} queued tranche(s) hold "
                        f"a ref that is not a finite number; those set no "
                        f"threshold at all, so this answer is the one for "
                        f"the {len(_thresholds)} readable tranche(s)."
                    )
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD REF UNREADABLE: {_unreadable_refs} of "
                            f"{len(self._fold_tranches)} queued tranche(s) hold a "
                            f"ref that is not a finite number (nan or inf), so "
                            f"they set no rebuy threshold and the gate answered "
                            f"on the {len(_thresholds)} readable one(s). The "
                            f"ladder is NOT altered here; this gate only "
                            f"withholds or allows the fire. Repair the row in "
                            f"bot state to bring those tranches back into the "
                            f"distance test."
                        ),
                    )
                    logger.warning(
                        "Bot %s fold ref unreadable on %d of %d tranche(s); "
                        "gated on the %d readable one(s)",
                        self.bot_id,
                        _unreadable_refs,
                        len(self._fold_tranches),
                        len(_thresholds),
                    )
                if not _distance_ok:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"AUTONOMOUS FIRE REFUSED (opposing distance): at "
                            f"${price:.8f} not one of the "
                            f"{len(self._fold_tranches)} queued tranche(s) is "
                            f"eligible. The highest rebuy any of them allows "
                            f"is ${_best_rebuy:.8f} (its ref x "
                            f"{_fold_factor:.4f}), so price must fall "
                            f"${price - _best_rebuy:.8f} further. Gates are "
                            f"bypassed on this path, so it will not rebuy "
                            f"above what it sold at. Intended BUY of "
                            f"${abs(delta_usd):.2f} withheld.{_unread_tail}"
                        ),
                    )
                    logger.warning(
                        "Bot %s autonomous fold refused: price %.8f above "
                        "best rebuy %.8f across %d tranche(s), %d unreadable",
                        self.bot_id,
                        price,
                        _best_rebuy,
                        len(self._fold_tranches),
                        _unreadable_refs,
                    )
                    return

            _denom_pre = price * _qrate
            _growth_preview = 0.0
            self._fold_preview_unreadable_refs = 0
            self._fold_preview_unreadable_units = 0
            if _denom_pre > 0:
                for _ in range(4):
                    _units_pre = ((-delta_usd) + _growth_preview) / _denom_pre
                    _g = self._preview_fold_growth(_units_pre, price)
                    if abs(_g - _growth_preview) <= 1e-9:
                        break
                    _growth_preview = _g
            _preview_unreadable = int(
                getattr(self, "_fold_preview_unreadable_refs", 0) or 0
            )
            if _preview_unreadable:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD SIZING REF UNREADABLE: {_preview_unreadable} of "
                        f"{len(self._fold_tranches)} queued tranche(s) hold a "
                        f"ref that is not a finite number (nan or inf). Those "
                        f"set no discharge order and add no prospective "
                        f"growth, so this buy is sized on the "
                        f"{len(self._fold_tranches) - _preview_unreadable} "
                        f"readable one(s). The ladder is NOT altered here. "
                        f"Repair the row in bot state to bring those tranches "
                        f"back into the sizing."
                    ),
                )
                logger.warning(
                    "Bot %s fold sizing ref unreadable on %d of %d " "tranche(s)",
                    self.bot_id,
                    _preview_unreadable,
                    len(self._fold_tranches),
                )
            _preview_unsizable = int(
                getattr(self, "_fold_preview_unreadable_units", 0) or 0
            )
            if _preview_unsizable:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD SIZING UNITS UNREADABLE: {_preview_unsizable} of "
                        f"{len(self._fold_tranches)} queued tranche(s) hold "
                        f"units that are not a finite number (nan or inf). "
                        f"Those discharge nothing and add no prospective "
                        f"growth, so this buy is sized on the remaining "
                        f"readable one(s). The ladder is NOT altered here. "
                        f"Repair the row in bot state to bring those tranches "
                        f"back into the sizing."
                    ),
                )
                logger.warning(
                    "Bot %s fold sizing units unreadable on %d of %d " "tranche(s)",
                    self.bot_id,
                    _preview_unsizable,
                    len(self._fold_tranches),
                )
            buy_usd_target = -delta_usd + _growth_preview
            if _growth_preview > 1e-9:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"MANUAL FIRE FOLD: sizing against the "
                        f"POST-growth target — base deficit "
                        f"${-delta_usd:.4f} + prospective compound "
                        f"growth ${_growth_preview:.4f} = "
                        f"${buy_usd_target:.4f}. Without this the "
                        f"fold would land ${_growth_preview:.4f} "
                        f"short and could not compound."
                    ),
                )
            quote_currency = self.config.symbol.split("/")[-1]
            quote_free = 0.0
            _bal_err = None
            try:
                bal = await self._get_balance(quote_currency)
                quote_free = float(getattr(bal, "free", 0) or 0)
            except Exception as exc:
                _bal_err = exc
                try:
                    balances = await self.exchange.get_balances()
                    b = balances.get(quote_currency)
                    if b is not None:
                        quote_free = float(getattr(b, "free", 0) or 0)
                except Exception as exc2:
                    _bal_err = exc2
            _wallet_key = wallet_key(self.config.exchange_id, quote_currency)
            _reservations = get_wallet_reservations()
            _wallet_free = quote_free * _qrate
            usd_balance = _reservations.available(_wallet_key, _wallet_free)
            _held_by_others = _reservations.reserved(_wallet_key)
            buy_usd = min(buy_usd_target, usd_balance)
            if buy_usd <= 0:
                err_tail = f" (fetch error: {_bal_err})" if _bal_err else ""
                held_tail = (
                    f", of which ${_held_by_others:.4f} is reserved by "
                    f"other bots' in-flight orders"
                    if _held_by_others > 1e-9
                    else ""
                )
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"MANUAL FIRE FOLD: delta=-${buy_usd_target:.4f} "
                        f"but {quote_currency} free=${quote_free:.4f} "
                        f"(~${_wallet_free:.4f} USD{held_tail}; "
                        f"spendable ${usd_balance:.4f})"
                        f"{err_tail}. Cannot rebalance."
                    ),
                )
                return
            denom = price * _qrate
            buy_amount = (buy_usd / denom) if denom > 0 else 0.0
            clipped = buy_usd < buy_usd_target
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MANUAL FIRE FOLD: delta=-${buy_usd_target:.4f} "
                    f"under target → buying {buy_amount:.6f} "
                    f"{self.config.symbol.split('/')[0]} @ MARKET "
                    f"(~${price:.8f}) with ${buy_usd:.4f}"
                    f"{f' (CLIPPED by {quote_currency})' if clipped else ''}."
                ),
            )

            _reservations.reserve(_wallet_key, buy_usd)
            try:
                order = await self.guarded_place_order(
                    symbol=self.config.symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    amount=buy_amount,
                    price=None,
                )
            finally:
                _reservations.release(_wallet_key, buy_usd)

            if order is None:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message="MANUAL FIRE FOLD: exchange returned no order.",
                )
                return

            fill_amount, fill_price, _fill_is_real = await self._settled_fill(
                order, self.config.symbol, buy_amount, price
            )
            if fill_amount <= 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"MANUAL FIRE FOLD: order placed but no "
                        f"filled amount reported (order.filled="
                        f"{getattr(order, 'filled', 'missing')}, "
                        f"order.amount={getattr(order, 'amount', 'missing')}). "
                        f"Aborting post-fill accounting; check exchange for actual state."
                    ),
                )
                return
            if fill_price <= 0:
                fill_price = price

            _manual_fold_accum_profit = 0.0
            if self._fold_tranches:
                remaining = fill_amount
                consumed = []
                for t in self._fold_discharge_order():
                    if remaining <= 1e-12:
                        break
                    # Finite, per _fold_discharge_order. Coerced so the
                    # write-back below is float arithmetic.
                    t_units = float(t.get("units", 0.0) or 0.0)
                    take = min(t_units, remaining)
                    if take <= 1e-12:
                        continue
                    _t_ref = float(t.get("ref", 0.0) or 0.0)
                    if _t_ref > fill_price:
                        _manual_fold_accum_profit += take * (_t_ref - fill_price)
                    self._main_lots.append(
                        {
                            "units": take,
                            "initial_buy_price": t.get("initial_buy_price", fill_price),
                            "operator_initiated": _operator_initiated,
                        }
                    )
                    t["units"] = t_units - take
                    if t_units > 0:
                        t["usd"] *= t["units"] / t_units
                    remaining -= take
                    if t["units"] <= 1e-12:
                        consumed.append(t)

                for t in consumed:
                    self._fold_tranches.remove(t)
                if consumed:
                    try:
                        self._tranches_closed_lifetime = int(
                            getattr(self, "_tranches_closed_lifetime", 0) or 0
                        ) + len(consumed)
                    except Exception as _sup:
                        logger.debug(
                            "suppressed in %s: %s: %s",
                            "_execute_manual_rebalance",
                            type(_sup).__name__,
                            _sup,
                        )

                if remaining > 1e-12:
                    self._main_lots.append(
                        {
                            "units": remaining,
                            "initial_buy_price": fill_price,
                            "operator_initiated": _operator_initiated,
                        }
                    )

                self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)

                msg = (
                    f"MANUAL FIRE FOLD FILLED: {fill_amount:.6f} @ "
                    f"${fill_price:.8f}. Discharged "
                    f"{len(consumed)} tranche(s) bypassing MEM-171 "
                    f"gates (operator override)."
                )
            else:
                self._main_lots.append(
                    {
                        "units": fill_amount,
                        "initial_buy_price": fill_price,
                        "operator_initiated": _operator_initiated,
                    }
                )
                msg = (
                    f"MANUAL FIRE FOLD FILLED: {fill_amount:.6f} @ "
                    f"${fill_price:.8f}. No tranches queued; "
                    f"opened new lot (operator_initiated)."
                )

            self._current_holdings += fill_amount
            self.stats.total_trades += 1

            _growth_applied = self._apply_fold_target_growth(
                _manual_fold_accum_profit, source=str(_fold_label)
            )

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    msg + f" Holdings now "
                    f"{self._current_holdings:.6f} "
                    f"(~${self._current_holdings * price * float(self._quote_to_usd or 1.0):.2f})."
                ),
            )
            self.stats.total_folded_usd += float(
                fill_amount * fill_price * float(self._quote_to_usd or 1.0)
            )
            self.reset_swos_cycle()
            self._last_trade_side = "FOLD"
            self._reset_opposing_hysteresis_after_fill()
            self._bus.emit(
                "trade.filled",
                bot_id=self.bot_id,
                data={
                    "type": _fold_label,
                    "side": "BUY",
                    "amount": fill_amount,
                    "price": fill_price,
                    "usd": fill_amount * fill_price,
                    "profit": _growth_applied,
                    "operator_initiated": _operator_initiated,
                },
            )
            self._emit_voting_panel_snapshot_at_fire(
                side="BUY", trade_action=str(_fold_label or "MANUAL_FOLD")
            )
            self._emit_gate_decision_at_fire(
                side="BUY", trade_action=str(_fold_label or "MANUAL_FOLD")
            )
            try:
                self._bus.emit(
                    "pnl.event",
                    bot_id=self.bot_id,
                    data={
                        "kind": "FOLD",
                        "asset": self.config.target_asset,
                        "symbol": self.config.symbol,
                        "units_rebought": float(fill_amount),
                        "fill_price": float(fill_price),
                        "usd_spent": float(fill_amount * fill_price)
                        * float(self._quote_to_usd or 1.0),
                        "operator_initiated": _operator_initiated,
                        "manual_kind": _fold_label,
                    },
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_manual_rebalance",
                    type(_sup).__name__,
                    _sup,
                )
            self._last_trade_price = fill_price

    async def _check_detonation_trigger(self, ticker) -> bool:
        """Check higher-TF signal for detonation trigger.

        Edge-triggered: fires only on transition from not-bullish-or-
        low-conf to BULLISH+>=0.75. A sustained bull run that stays
        above threshold will detonate ONCE, not every hour.

        Rate-limited to 1 check per hour (higher TF candles close
        slowly; no reason to burn API quota faster).

        Additional gates:
          - detonation_enabled must be True
          - current_value must be above anchor (nothing to harvest
            if bot is below its anchor)

        Returns:
            True if trigger fired this call (caller should execute
                 detonation immediately);
            False otherwise.
        """
        if not getattr(self.config, "detonation_enabled", False):
            return False

        price = getattr(ticker, "last", None) or 0.0
        if price <= 0:
            return False
        current_value = (
            self._current_holdings * price * float(self._quote_to_usd or 1.0)
        )
        if current_value <= self._anchor_target_balance:
            return False

        now = time.time()
        if now - self._detonation_last_check_ts < 3600:
            return False
        self._detonation_last_check_ts = now

        tf = getattr(self.config, "detonation_timeframe", "1d") or "1d"
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

        if not candles or len(candles) < 30:
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

    def clear_fold_tranches(self, reason: str = "operator") -> dict:
        """Discard every queued fold tranche. Trades nothing.

        WHAT THIS DOES NOT TOUCH, deliberately:
          * holdings, `_main_lots`, or any position — nothing is sold or
            bought, no order is placed
          * `_target_balance` or `_anchor_target_balance` — unlike
            detonation's full reset, the target is left exactly where it
            is
          * `_pending_wire_credits` — that is real routed income, not a
            tranche. See the warning below.


        Returns a report of what was discarded. Never raises.
        """
        tranches = list(self._fold_tranches or [])
        report = {
            "bot_id": self.bot_id,
            "symbol": getattr(self.config, "symbol", ""),
            "count": len(tranches),
            "usd": round(sum(float(t.get("usd", 0) or 0) for t in tranches), 8),
            "units": round(sum(float(t.get("units", 0) or 0) for t in tranches), 8),
            "pending_wire_credits": round(
                float(getattr(self, "_pending_wire_credits", 0.0) or 0.0), 8
            ),
            "reason": str(reason),
        }
        if not tranches:
            return report

        self._fold_tranches = []
        self._fold_queue_usd = 0.0
        self._tranches_discarded_lifetime = (
            int(getattr(self, "_tranches_discarded_lifetime", 0) or 0) + report["count"]
        )

        try:
            self.stats.tranches_discarded_lifetime = self._tranches_discarded_lifetime
        except Exception as exc:  # noqa: BLE001
            logger.debug("clear_fold_tranches: stats mirror failed: %s", exc)

        try:
            _warn = ""
            if report["pending_wire_credits"] > 1e-9:
                _warn = (
                    f" WARNING: ${report['pending_wire_credits']:.4f} "
                    f"of pending wire credits remain parked, and "
                    f"clearing has OPENED the absorb window — the "
                    f"next scrum will dump all of it into a single "
                    f"tranche."
                )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD TRANCHES CLEARED ({reason}): discarded "
                    f"{report['count']} tranche(s) holding "
                    f"${report['usd']:.4f} against "
                    f"{report['units']:.8f} units. No trade was "
                    f"placed; holdings and target balance are "
                    f"unchanged.{_warn}"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("clear_fold_tranches: log emit failed: %s", exc)

        logger.info(
            "Bot %s: cleared %d fold tranche(s) ($%.4f, %.8f units) "
            "reason=%s pending_wire_credits=$%.4f",
            self.bot_id,
            report["count"],
            report["usd"],
            report["units"],
            reason,
            report["pending_wire_credits"],
        )
        return report

    def clear_lifetime_tranche_counters(self, reason: str = "operator") -> dict:
        """Reset the four fold-tranche lifetime counters to zero.

        issue #133 unit 3, operator directive 2026-08-25: "Lifetime
        tranche counts can be cleared since we are resetting to the new
        standard." The live CHIP bot carried opened 4925, closed 4813
        and discarded 91, all accumulated under rules that no longer
        apply.

        FOUR COUNTERS, FIVE FIGURES ON THE PANEL. Opened, closed,
        discarded and malformed-dropped are stored and are cleared here.
        The cycle close ratio is `closed / (created - discarded)`,
        computed on the panel from three of them, so it follows the
        reset without being a counter of its own.

        MALFORMED IS A SUB-COUNT OF DISCARDED, so clearing discarded and
        leaving it would publish a sub-count larger than the total it
        belongs to.

        THE `stats` MIRROR GOES TOO. `stats.tranches_discarded_lifetime`
        is a second copy of one of the four and is serialised into its
        own section of the state file, so a clear that skipped it would
        write 0 under `scrumming_state` and 91 under `stats`.

        WHAT THIS DOES NOT TOUCH: the standing `_fold_tranches` and the
        `_fold_queue_usd` they park, `_pending_wire_credits` and its
        ledger, `_wire_credits_discarded_lifetime`, the stack-side
        `_stack_created` and `_stack_discarded`, and every holding, lot,
        cost basis and target. This clears counters, not inventory.

        THE RESET STAMP IS NOT A DECORATION. The init handshake reads
        `_tranches_created_lifetime == 0` as "no scrum has ever fired"
        and adopts the exchange balance as the bot's opening position,
        REPLACING `_main_lots` with one lot at a single derived basis.
        Zeroing the counter alone would re-arm that at the next launch
        on a bot with thousands of scrums behind it. The stamp records
        that the zero was written by an operator, and the predicate
        reads it.

        A BOT WHOSE FOUR COUNTERS ARE ALREADY ZERO IS LEFT ALONE, stamp
        included. On that bot the zero is its real history, and stamping
        it would take the opening-position adoption away from the one
        bot that needs it.

        Returns a report of the four values destroyed. Never raises.
        """
        _before = {
            "created": int(
                as_finite_float(getattr(self, "_tranches_created_lifetime", 0)) or 0.0
            ),
            "closed": int(
                as_finite_float(getattr(self, "_tranches_closed_lifetime", 0)) or 0.0
            ),
            "discarded": int(
                as_finite_float(getattr(self, "_tranches_discarded_lifetime", 0)) or 0.0
            ),
            "malformed": int(
                as_finite_float(getattr(self, "_tranches_malformed_dropped", 0)) or 0.0
            ),
        }
        report = {
            "bot_id": self.bot_id,
            "symbol": getattr(self.config, "symbol", ""),
            "before": dict(_before),
            "cleared": sum(_before.values()),
            "open_tranches": len([t for t in (self._fold_tranches or [])]),
            "reset_ts": float(getattr(self, "_tranches_counters_reset_ts", 0.0) or 0.0),
            "reason": str(reason),
        }
        if report["cleared"] <= 0:
            return report

        self._tranches_created_lifetime = 0
        self._tranches_closed_lifetime = 0
        self._tranches_discarded_lifetime = 0
        self._tranches_malformed_dropped = 0
        self._tranches_counters_reset_ts = float(time.time())
        report["reset_ts"] = self._tranches_counters_reset_ts

        try:
            self.stats.tranches_discarded_lifetime = 0
        except Exception as exc:  # noqa: BLE001 - telemetry mirror only
            logger.debug(
                "clear_lifetime_tranche_counters: stats mirror failed: %s", exc
            )

        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"LIFETIME TRANCHE COUNTERS CLEARED ({reason}): "
                    f"opened {_before['created']}, closed "
                    f"{_before['closed']}, discarded "
                    f"{_before['discarded']}, malformed-dropped "
                    f"{_before['malformed']} are now zero. No tranche, "
                    f"no parked credit and no holding was touched; "
                    f"{report['open_tranches']} tranche(s) remain in "
                    f"the queue."
                ),
            )
        except Exception as exc:  # noqa: BLE001 - diagnostic best-effort
            logger.debug("clear_lifetime_tranche_counters: log emit failed: %s", exc)

        logger.info(
            "Bot %s: cleared lifetime tranche counters "
            "(opened=%d closed=%d discarded=%d malformed=%d) reason=%s "
            "open_tranches=%d",
            self.bot_id,
            _before["created"],
            _before["closed"],
            _before["discarded"],
            _before["malformed"],
            reason,
            report["open_tranches"],
        )
        return report

    def clear_stack_tranches(self, reason: str = "operator") -> dict:
        """Discard this bot's standing Stack tranches. Trades nothing.

        issue #133 unit 7, the operator's rule of 2026-08-25: "Either
        side of the ladder should basically be functioning the same way
        but travelling down (Fold) or up (Stack)."
        ``clear_fold_tranches`` emptied one side and the other had no
        counterpart, so a control that exists on one side and not the
        other was the defect. Same verb, opposite direction.

        ONE REFUSAL, AND IT IS THE DESPAWN SWEEP'S. A Visible-mode
        tranche with ``status == "pending"`` and an ``order_id`` holds a
        resting LIMIT SELL on the exchange. Dropping THAT record would
        leave a live order on the book with nothing tracking it, which is
        the single way this method could strand something. Such a record
        is KEPT and counted. The fold ledger needs no such rule because a
        fold tranche owns no order.

        COUNTER SEMANTICS, MIRRORED. Every discarded record moves
        ``_stack_discarded`` and nothing else. There is no closed counter
        on this ledger to conflate it with: filling a stack tranche sets
        ``status`` and LEAVES THE RECORD LISTED, so
        ``created - discarded == standing`` is the whole reconciliation
        here, and this method keeps it true. Neither stack counter has a
        ``stats`` mirror, so unlike ``clear_fold_tranches`` this has no
        second copy to write.

        WHAT THIS DOES NOT TOUCH: holdings, ``_main_lots``, the fold
        queue, parked wire credits, the target and the anchor. Nothing is
        sold, nothing is bought, and no order is placed or cancelled.

        NO LIVE BLAST RADIUS TODAY. ``stack_mode`` reads False on all 38
        live bots and every one of them stores zero stack tranches, so
        this returns an empty report on the fleet as it stands.

        Returns a report of what was discarded. Never raises.
        """
        _keep: list[dict] = []
        _drop: list[dict] = []
        for _t in list(self._stack_tranches or []):
            if _t.get("status") == "pending" and _t.get("order_id"):
                _keep.append(_t)
            else:
                _drop.append(_t)

        # A REFUSED SIZE IS COUNTED, NOT DROPPED, which is the rule the
        # Stack panel already totals its own sizes under. Skipping an
        # unreadable record reports a total below the truth with nothing
        # on the report saying so.
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
                f"hold resting exchange orders, and delisting a record "
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
        except Exception as exc:  # noqa: BLE001 - diagnostic best-effort
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
        """Reset the two stack-tranche lifetime counters to zero.

        issue #133 unit 7. Unit 3 gave the fold ledger
        ``clear_lifetime_tranche_counters``; this side carried two
        counters and no control of its own, so the Stack panel's fill
        ratio could not be reset to the new standard while the Fold
        panel's cycle ratio could.

        TWO COUNTERS, NOT FOUR, and the two the fold side has that this
        one lacks are absent for a stated reason rather than overlooked.
        ``closed`` is structurally zero here -- filling a stack tranche
        sets ``status`` and leaves the record listed -- and nothing on
        this ledger is dropped for being unreadable, so there is no
        malformed sub-count. ``created - discarded == standing`` is the
        whole reconciliation, and both of its terms are cleared.

        A SEPARATE METHOD, NOT A SECOND JOB FOR THE FOLD ONE. Widening
        that method would make one click clear both ledgers, and the
        operator can want one side's record reset with the other's
        intact. Same reasoning that made the fold counter clear a third
        button rather than a third job for the tranche clear.

        THE RESET STAMP IS NOT A DECORATION, for the reason the fold
        stamp is not. The Stack panel prints "no stacks opened yet"
        whenever ``created`` reads 0, and on a cleared bot that sentence
        is false. ``_stack_counters_reset_ts`` is what tells the two
        zeroes apart.

        WHAT THIS DOES NOT TOUCH: the standing ``_stack_tranches``, the
        four fold counters and their own stamp, ``_pending_wire_credits``
        and its ledger, and every holding, lot, cost basis and target.
        This clears counters, not inventory. Neither counter has a
        ``stats`` mirror, so there is no second copy to write.

        A BOT WHOSE TWO COUNTERS ARE ALREADY ZERO IS LEFT ALONE, stamp
        included, so a bot that genuinely never opened a stack keeps
        saying so.

        Returns a report of the two values destroyed. Never raises.
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
        except Exception as exc:  # noqa: BLE001 - diagnostic best-effort
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

    @staticmethod
    def _tranche_age_seconds(tranche: dict, field: str, now: float) -> Optional[float]:
        """Age of one tranche in seconds, or None when it has no age.

        None is not an error. It is the answer for a record that carries
        no usable timestamp, and the despawn sweep treats it as "do not
        touch" rather than as zero or as infinity.

        `as_finite_float` carries the whole admission rule: exactly int
        or exactly float, and finite. `bool` is a subclass of `int`, so
        a stored `True` would otherwise be read as 1.0 and date the
        record to the epoch — an age of about 56 years, which every
        threshold would delist. A numeric string, a Decimal, None, an
        object with `__float__`, `nan` and the infinities all take the
        same no-timestamp path.

        Args:
          tranche: one fold or stack tranche record.
          field: ``created_ts`` on the fold side, ``opened_ts`` on the
            stack side. Each ledger ages on its own field.
          now: the wall-clock second to measure against.

        Returns:
          Age in seconds, which may be negative for a future-dated
          stamp, or None when there is no usable timestamp.
        """
        _ts = as_finite_float(tranche.get(field))
        if _ts is None or _ts <= 0:
            return None
        return now - _ts

    def _despawn_threshold_days(self) -> int:
        """This bot's despawn threshold in whole days; 0 means off.

        A thin read of the shared rule in ``bot_container``, which the
        live-settings spinbox also reads, so the sweep and the control
        that sets it can never disagree about what a stored value means.
        """
        return despawn_threshold_days(self.config)

    def _despawn_aged_tranches(self, now: Optional[float] = None) -> dict:
        """Delist tranches older than ``config.tranche_despawn_days``.

        WHAT IT DOES WRITE, and why each is part of dropping the record
        rather than something extra: ``_fold_queue_usd`` is a DERIVED
        aggregate, recomputed at every other site that removes a fold
        tranche; leaving it stale would keep the tick's
        ``_fold_queue_usd == 0`` short-circuit and the panel's "Parked
        USD" both reporting money with no tranche behind it. And a
        delist is counted in ``_tranches_discarded_lifetime``, never in
        ``_tranches_closed_lifetime``, because a closed tranche is one
        that FOLDED. That split is what keeps
        ``created - closed - discarded == standing`` true.

        BOTH LEDGERS KEEP THAT INVARIANT, not the fold one alone. This
        sweep is the only site in src/ that removes a stack tranche, so
        ``_stack_discarded`` is incremented here beside
        ``_stack_created``. An earlier build dropped stack records and
        touched no counter at all, which left ``_stack_created``
        climbing against a shrinking standing list and drove the Stack
        panel's ``filled / created`` readout down permanently — red
        below 30% — with no discarded row to account for it. On this
        ledger the ``closed`` term is structurally zero: filling a stack
        tranche sets its ``status`` and LEAVES THE RECORD LISTED, so
        nothing else ever takes one out.

        THE ONE ASYMMETRY, and it is a refusal rather than a second
        policy. A Visible-mode stack tranche holds a resting LIMIT order
        on the exchange — ``status == "pending"`` with an ``order_id``.
        Dropping THAT record would leave a live order on the book with
        nothing tracking it, which is the single way this sweep could
        strand something and would falsify the "no order" claim above.
        Such a tranche is kept and counted. Invisible-mode tranches
        carry ``order_id=None`` and are delisted like any other record,
        as are filled and cancelled ones, whose orders are already
        terminal.

        IT CANNOT RAISE OUT OF THE TICK, and that is a requirement
        rather than a hope: the call site sits outside every ``try`` in
        ``tick``, so an exception here ends the tick. Every number this
        method reads — the threshold, both timestamps, the injected
        ``now``, the delisted USD total, the parked-credit total and
        BOTH discard counters — goes through
        ``as_finite_float`` or the shared threshold reader, which refuse
        `nan`, the infinities and out-of-range ints instead of
        converting them. An earlier build gated on exact type ALONE and
        `type(float("nan")) is float` is True, so `nan` passed the gate
        and `int(nan)` then raised ValueError from a site with no
        handler above it.

        THE QUEUE-TOTAL RECOMPUTE IS GUARDED TOO, and it therefore
        DIVERGES from the six sibling sites that recompute the same
        aggregate with ``float(t.get("usd", 0) or 0)``. Leaving it
        unguarded would falsify the paragraph above: a surviving
        tranche whose ``usd`` is a huge int makes ``float()`` raise
        from a site with no handler. Those six keep the old expression;
        putting all seven on one rule is a separate unit, named here
        and deliberately not done here.

        Args:
          now: wall-clock seconds to age against. Defaults to
            ``time.time()``; injected by the tests. A non-numeric or
            non-finite value makes every age unmeasurable, so the sweep
            delists nothing and says so.

        Returns:
          A report of what the sweep did.
        """
        _days = self._despawn_threshold_days()
        report = {
            "threshold_days": _days,
            "fold_delisted": 0,
            "stack_delisted": 0,
            "stack_kept_live_order": 0,
            "ageless_kept": 0,
            "usd_delisted": 0.0,
        }
        if _days <= 0:
            return report

        _now = time.time() if now is None else as_finite_float(now)
        if _now is None:
            logger.warning(
                "Bot %s: despawn sweep delisted nothing — `now` was %r, "
                "which is not a finite number, so no age is measurable",
                self.bot_id,
                now,
            )
            return report
        _cutoff = _days * 86400.0

        _fold_keep = []
        for _t in self._fold_tranches or []:
            _age = self._tranche_age_seconds(_t, "created_ts", _now)
            if _age is None:
                report["ageless_kept"] += 1
                _fold_keep.append(_t)
            elif _age >= _cutoff:
                report["fold_delisted"] += 1
                _usd = as_finite_float(_t.get("usd", 0))
                if _usd is not None:
                    report["usd_delisted"] += _usd
            else:
                _fold_keep.append(_t)

        _stack_keep = []
        for _t in self._stack_tranches or []:
            _age = self._tranche_age_seconds(_t, "opened_ts", _now)
            if _age is None:
                report["ageless_kept"] += 1
                _stack_keep.append(_t)
            elif _age < _cutoff:
                _stack_keep.append(_t)
            elif _t.get("status") == "pending" and _t.get("order_id"):
                report["stack_kept_live_order"] += 1
                _stack_keep.append(_t)
            else:
                report["stack_delisted"] += 1

        if not (report["fold_delisted"] or report["stack_delisted"]):
            return report

        if report["fold_delisted"]:
            self._fold_tranches = _fold_keep
            self._fold_queue_usd = sum(
                (as_finite_float(_t.get("usd", 0)) or 0.0) for _t in self._fold_tranches
            )
            self._tranches_discarded_lifetime = (
                int(
                    as_finite_float(getattr(self, "_tranches_discarded_lifetime", 0))
                    or 0.0
                )
                + report["fold_delisted"]
            )
            try:
                self.stats.tranches_discarded_lifetime = (
                    self._tranches_discarded_lifetime
                )
            except AttributeError as exc:
                logger.debug("despawn: stats mirror failed: %s", exc)
        if report["stack_delisted"]:
            self._stack_tranches = _stack_keep
            self._stack_discarded = (
                int(as_finite_float(getattr(self, "_stack_discarded", 0)) or 0.0)
                + report["stack_delisted"]
            )

        _parked = as_finite_float(getattr(self, "_pending_wire_credits", 0.0)) or 0.0
        _warn = ""
        if not self._fold_tranches and _parked > 1e-9:
            _warn = (
                f" WARNING: ${_parked:.4f} of pending wire credits "
                f"remain parked and the fold queue is now empty, "
                f"which has OPENED the absorb window — the next "
                f"scrum will dump all of it into a single tranche."
            )
        _skipped = ""
        if report["stack_kept_live_order"]:
            _skipped = (
                f" {report['stack_kept_live_order']} aged stack "
                f"tranche(s) KEPT: they hold resting exchange "
                f"orders, and delisting a record that owns a "
                f"live order would strand it."
            )
        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"TRANCHES DESPAWNED (>= {_days}d): delisted "
                    f"{report['fold_delisted']} fold tranche(s) "
                    f"holding ${report['usd_delisted']:.4f} and "
                    f"{report['stack_delisted']} stack tranche(s). "
                    f"No order was placed or cancelled; holdings, "
                    f"cost basis and target balance are "
                    f"unchanged.{_skipped}{_warn}"
                ),
            )
        except AttributeError as exc:
            logger.debug("despawn: log emit failed: %s", exc)

        logger.info(
            "Bot %s: despawned %d fold + %d stack tranche(s) at >= %d "
            "days (kept %d ageless, %d with live orders)",
            self.bot_id,
            report["fold_delisted"],
            report["stack_delisted"],
            _days,
            report["ageless_kept"],
            report["stack_kept_live_order"],
        )
        return report

    async def _execute_detonation(self, ticker) -> None:
        """Execute the detonation harvest.

        Operator Q3: "Sell everything above the ANCHOR, not above
        current target (locks in full gains)."
        Operator post-detonation semantic: "Yes — reset target to
        anchor. 'Locks in' means fully reset; re-accumulate from
        scratch."

        Effect:
          1. Compute excess = current_holdings_value - anchor
          2. MARKET SELL excess/price asset
          3. Reset self._target_balance = anchor (full reset)
          4. Clear fold queue (no re-accumulation pressure)
          5. Tag the trade and resulting tranches auto_detonated=True
             for downstream audit visibility
        """
        price = getattr(ticker, "last", None)
        if not price or price <= 0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message="DETONATION: no valid price; aborting.",
            )
            return

        _qrate = float(self._quote_to_usd or 1.0)
        current_value = self._current_holdings * price * _qrate
        excess_usd = current_value - self._anchor_target_balance
        if excess_usd <= 0:
            return

        sell_amount = excess_usd / (price * _qrate) if (price * _qrate) > 0 else 0.0
        sell_amount = min(sell_amount, self._current_holdings)
        if sell_amount <= 0:
            return

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"DETONATION HARVEST: value=${current_value:.2f}, "
                f"anchor=${self._anchor_target_balance:.2f}, "
                f"selling {sell_amount:.6f} "
                f"{self.config.symbol.split('/')[0]} @ MARKET "
                f"(~${price:.8f}) to lock in "
                f"${excess_usd:.2f} gains."
            ),
        )

        order = await self.guarded_place_order(
            symbol=self.config.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=sell_amount,
            price=None,
        )

        if order is None:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message="DETONATION: exchange returned no order.",
            )
            return

        _filled_raw = (
            getattr(order, "filled", None)
            or getattr(order, "amount", None)
            or sell_amount
        )
        try:
            fill_amount = float(_filled_raw or 0.0)
        except (TypeError, ValueError):
            fill_amount = 0.0
        if fill_amount <= 0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    "DETONATION: order placed but no filled "
                    "amount reported. Check exchange for actual "
                    "state."
                ),
            )
            return

        fill_price = (
            getattr(order, "average_price", None)
            or getattr(order, "average", None)
            or getattr(order, "price", None)
            or price
        )
        try:
            fill_price = float(fill_price)
        except (TypeError, ValueError):
            fill_price = price

        fill_usd = fill_price * fill_amount

        self._current_holdings = max(0.0, self._current_holdings - fill_amount)

        _detonation_routed_total = self._route_scrum_proceeds_via_wires(
            scrum_usd=fill_usd, sell_fill=fill_price, label="detonation"
        )
        try:
            _detonation_kept = float(fill_usd) - float(_detonation_routed_total or 0.0)
            self._bus.emit(
                "pnl.event",
                bot_id=self.bot_id,
                data={
                    "kind": "SCRUM",
                    "asset": self.config.target_asset,
                    "symbol": self.config.symbol,
                    "units": float(fill_amount),
                    "fill_price": float(fill_price),
                    "usd_captured": _detonation_kept * float(self._quote_to_usd or 1.0),
                    "usd_routed_via_wires": float(_detonation_routed_total or 0.0)
                    * float(self._quote_to_usd or 1.0),
                    "operator_initiated": False,
                    "manual_kind": "DETONATION",
                },
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_execute_detonation",
                type(_sup).__name__,
                _sup,
            )

        prior_target = self._target_balance
        self._target_balance = self._anchor_target_balance
        _detonated_tranches = len(self._fold_tranches)
        if _detonated_tranches:
            self._tranches_discarded_lifetime = (
                int(getattr(self, "_tranches_discarded_lifetime", 0) or 0)
                + _detonated_tranches
            )
        self._fold_tranches.clear()
        self._fold_queue_usd = 0.0
        float(getattr(self, "_standing_surplus_usd", 0.0) or 0.0)
        self._standing_surplus_usd = 0.0
        try:
            self.stats.standing_surplus_usd = 0.0
        except Exception as _sp_exc:  # noqa: BLE001
            logger.debug("detonation surplus mirror failed: %s", _sp_exc)

        self._main_lots.clear()
        if self._current_holdings > 0:
            self._main_lots.append(
                {
                    "units": self._current_holdings,
                    "initial_buy_price": fill_price,
                    "auto_detonated_reset": True,
                }
            )

        self.stats.total_trades += 1
        self._last_trade_price = fill_price

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"DETONATION COMPLETE: filled {fill_amount:.6f} @ "
                f"${fill_price:.8f} = ${fill_usd:.2f}. "
                f"target_balance reset ${prior_target:.2f} → "
                f"${self._anchor_target_balance:.2f} (anchor). "
                f"Fold queue cleared. Bot will re-accumulate "
                f"from scratch on next dip."
            ),
        )

        self._bus.emit(
            "trade.filled",
            bot_id=self.bot_id,
            data={
                "type": "AUTO_DETONATION",
                "side": "SELL",
                "amount": fill_amount,
                "price": fill_price,
                "usd": fill_usd,
                "profit": excess_usd,
                "auto_detonated": True,
                "anchor": self._anchor_target_balance,
            },
        )
        self._emit_voting_panel_snapshot_at_fire(
            side="SELL", trade_action="AUTO_DETONATION"
        )
        self._emit_gate_decision_at_fire(side="SELL", trade_action="AUTO_DETONATION")

    async def _open_stack_from_scrum(
        self,
        scrum_price: float,
        scrum_size: float,
        summary: Optional[VotingSummary] = None,
        origin: str = "scrum",
    ) -> int:
        """Split a SCRUM decision into Stack tranches instead of firing
        one immediate sell. Populates `self._stack_tranches`. Returns
        the number of tranches created (>=1).

        `origin` names WHAT OPENED THIS STACK and is recorded on every
        tranche it builds. "scrum" is the intercept in `_execute_sell`;
        "fold" is the item-7 spawn in `_execute_buy`, whose ladder
        anchor is the price a fold actually filled at. It changes no
        arithmetic -- both origins build the same ascending sell ladder
        through the same `stack_math` call -- but a tranche that cannot
        say which side of the pair created it is not a record, and the
        line this method emits said "from scrum" whoever called it.
        fire on price crossing via the invisible reconciler."""
        from .stack_math import (
            split_scrum_into_tranches,
        )

        _interval = float(getattr(self.config, "scrumming_interval_pct", 0) or 0)
        _fee = float(getattr(self.config, "trading_fee_pct", 0.6) or 0.6)
        min_opposing_pct = _interval + _fee

        n_target = int(getattr(self.config, "stack_tranche_count_target", 3) or 3)
        # THE FIELD IS `split_distance`, declared at bot_container.py:350.
        # `split_distance_pct` is on no bot and on no schema, so this read
        # took its 1.0 fallback on every ladder and the operator's Split
        # Distance setting reached nothing. All 38 live bots store 1.0, so
        # the fallback and the setting agree today and the ladders do not
        # move; the setting starts working the moment one is changed.
        split_dist = float(getattr(self.config, "split_distance", 1.0) or 1.0)
        spacing = str(getattr(self.config, "stack_spacing_mode", "linear") or "linear")
        min_order = float(
            getattr(self.exchange_interface, "min_order_size", 0.0) or 0.0
        )

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
        """Visible-mode Stack reconciliation.

        Once per tick, cross-reference `_stack_tranches` order_ids against
        the exchange's list of currently-open orders. Any tranche whose
        order_id no longer appears open is assumed filled (or cancelled
        externally) — fetch the terminal order state to disambiguate,
        update status, capture fill price.

        No-op when not visible mode, no pending tranches, stack_mode off,
        or exchange lacks get_open_orders."""
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
        """STAGE ONE of the two-stage Stack rule: a crossed price
        threshold ACTIVATES a tranche. It does not spend it.

        Spending is `_spend_activated_stack_tranches`, inside the chain's
        should_fire block.

        ACTIVATION IS STICKY, and deliberately. The operator separated
        "activates" from "is spent"; re-testing the threshold at spend
        time would AND the two conditions into a single instant and
        silently de-activate a tranche whose price retraced before the
        chain authorised anything. `status` stays "pending" throughout, so
        the ledger's three states (pending / filled / cancelled) and every
        reader of them are unchanged -- activation is a separate flag on
        the same entry, not a fourth state.

        Returns the number of tranches NEWLY activated this tick.
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
        """STAGE TWO: spend the tranches the price threshold already
        activated, now that the trading condition has manifested.

        CALLED FROM ONE PLACE -- inside `tick`'s
        `if _scrum_chain_result.should_fire:` branch, immediately after
        `self._scrum_chain.evaluate(_scrum_ctx)`. Every gate the chain
        owns has therefore passed on THIS tick's candles and this tick's
        price, and every pre-chain return that ends a tick has already
        been survived. A tranche can no longer be spent on a tick the bot
        refused to trade on, nor on one where it never reached a decision.

        THE TRANCHE SURVIVES A REFUSAL, and there is no refusal branch
        here to do it: refusal is expressed by NOT CALLING this method.
        The tranche keeps `status == "pending"` and `activated == True`,
        so the next authorised tick spends it. Dropping an activated
        tranche on a refusal would be the same family of defect as
        spending it on one, pointed the other way.

        `current_price` is this tick's `ticker.last`, NOT the tranche's
        threshold. Invisible mode sells at MARKET, and `_execute_sell`
        measures its opposing-hysteresis and Verify-Hit gates against the
        price it is handed; handing it a threshold recorded on an earlier
        tick would measure both against a price that no longer exists.

        `summary` is the LIVE `VotingSummary` the chain just evaluated,
        which is the vote that authorised this sell. The tranche's
        `open_confidence` / `open_direction` are used only when no live
        vote is supplied -- they record what opened the Stack, and are
        never authority to close it.

        Returns the number of tranches spent this tick.
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

    async def _execute_sell(
        self,
        amount: float,
        price: float,
        summary: VotingSummary,
        bypass_stack: bool = False,
    ) -> Optional[float]:
        """Execute a sell order. Returns actual fill price captured from
        original semantics.

        issue #133 unit 9b -- also records the fee the venue reported
        for the settled order, so the SCRUM and DIST fold loops can
        value the sale at what the wallet was credited. The record is
        cleared on entry: a sell that never reaches the exchange must
        not leave the previous sell's fee readable.
        """
        self._last_sell_venue_fee = None

        if (
            not bypass_stack
            and getattr(self.config, "stack_mode", False)
            and amount
            and amount > 0
            and price
            and price > 0
        ):
            _n = await self._open_stack_from_scrum(
                scrum_price=float(price),
                scrum_size=float(amount),
                summary=summary,
            )
            if _n > 0:
                return None

        if (
            self._hyst_armed_scrum_side
            and self._hyst_ref_scrum_side > 0
            and getattr(self.config, "scrumming_interval_pct", 0) > 0
        ):
            try:
                _px_check = float(price)
            except (TypeError, ValueError):
                _px_check = 0.0
            _interval = float(self.config.scrumming_interval_pct)
            _fee = float(getattr(self.config, "trading_fee_pct", 0.6))
            _eff_pct = _interval + _fee
            _interval_frac = _eff_pct / 100.0
            _required_min = self._hyst_ref_scrum_side * (1.0 + _interval_frac)
            if _px_check > 0 and _px_check < _required_min:
                _rise_pct = (
                    (_px_check - self._hyst_ref_scrum_side)
                    / self._hyst_ref_scrum_side
                    * 100.0
                )
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"SCRUM REFUSED (opposing hysteresis v3.15.77): "
                        f"pivot ref ${self._hyst_ref_scrum_side:.8f} "
                        f"(captured when Δ crossed positive after recent "
                        f"FOLD), current ${_px_check:.8f} "
                        f"(only {_rise_pct:+.2f}% from pivot). "
                        f"Need ≥ {_eff_pct:.2f}% rise "
                        f"(interval {_interval:.2f}% + fee {_fee:.2f}%; "
                        f"price ≥ ${_required_min:.8f}) before "
                        f"SCRUM can fire."
                    ),
                )
                self._emit_trade_notification(
                    "SCRUM", "CANCELLED", f"hysteresis (need ≥ {_eff_pct:.2f}% rise)"
                )
                return None

        try:
            _crr_reg = self._crr()
            if _crr_reg is None:
                raise RuntimeError("no capital registry")
            _crr_effective = _crr_reg.effective_available(
                asset=self.config.target_asset,
                bot_id=self.bot_id,
                total_holdings=float(self._current_holdings or 0),
            )
            if amount > _crr_effective + 1e-12:
                _crr_msg = (
                    f"SELL REFUSED (capital reservation, v3.20.2): "
                    f"requested {amount:.6f} {self.config.target_asset} but "
                    f"only {_crr_effective:.6f} available to this bot — "
                    f"other bots hold reservations on this asset. "
                    f"_current_holdings={float(self._current_holdings or 0):.6f}; "
                    f"check Settings → Capital Reservations or "
                    f"force_release if a reservation is stale."
                )
                self._bus.emit("bot.log", bot_id=self.bot_id, message=_crr_msg)
                self._emit_trade_notification(
                    "SCRUM",
                    "CANCELLED",
                    f"capital reservation (avail {_crr_effective:.6f})",
                )
                logger.info(
                    "Bot %s sell refused by capital reservation: "
                    "amount=%.6f effective=%.6f asset=%s",
                    self.bot_id,
                    amount,
                    _crr_effective,
                    self.config.target_asset,
                )
                return None
        except Exception as _crr_exc:
            logger.debug(
                "Bot %s capital reservation pre-check raised %s — "
                "falling through to existing gates; v3.20.1 backstop "
                "remains active.",
                self.bot_id,
                _crr_exc,
            )

        try:
            _open = await self.exchange.get_open_orders(self.config.symbol)
        except Exception as _oo_exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"P0b SELL REFUSED (fail-closed): "
                    f"get_open_orders raised {type(_oo_exc).__name__}: "
                    f"{_oo_exc}. Cannot verify absence of stacked "
                    f"orders. Refusing."
                ),
            )
            return None
        try:
            _open_sells = [
                o
                for o in (_open or [])
                if getattr(o, "side", None) == OrderSide.SELL
                and getattr(o, "symbol", None) == self.config.symbol
            ]
        except Exception:
            _open_sells = [
                o
                for o in (_open or [])
                if getattr(o, "symbol", None) == self.config.symbol
            ]
        if _open_sells:
            _ids = ", ".join(str(getattr(o, "id", "?")) for o in _open_sells[:3])
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"P0b STACKED SELL REFUSED: {len(_open_sells)} open "
                    f"SELL order(s) already on exchange for "
                    f"{self.config.symbol} (ids: {_ids}). "
                    f"Refusing to place a second SELL on top. "
                    f"Wait for existing order(s) to fill or cancel."
                ),
            )
            return None

        try:
            from ..core.execution_discipline import verify_hit as _vh

            vh_fp, vh_status, vh_samples = _vh(
                price, "sell", symbol=self.config.target_asset
            )
            self.stats.verify_samples += vh_samples
            if vh_fp is None:
                self.stats.verify_canceled += 1
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"SELL CANCELED (R55 VH): slippage would "
                    f"exceed {self.config.target_asset} class "
                    f"tolerance @ ${price:.8f}",
                )
                logger.info(
                    "Bot %s VH-canceled sell of %.6f at %.4f",
                    self.bot_id,
                    amount,
                    price,
                )
                return
            if vh_status == "clean":
                self.stats.verify_clean += 1
            else:
                self.stats.verify_adjusted += 1

            if self._invisible:
                ot = OrderType.MARKET
                exec_price = None
            else:
                ot = OrderType.LIMIT
                exec_price = vh_fp

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"SELL signal: {amount:.6f} @ ${price:.8f} "
                f"(VH:{vh_status}, confidence="
                f"{summary.consensus_confidence:.2f}, "
                f"{'MARKET' if self._invisible else 'LIMIT'})",
            )
            self._emit_trade_notification(
                "SCRUM", "SENT", f"{amount:.6f} @ ${price:.8f}"
            )

            order = await self.guarded_place_order(
                symbol=self.config.symbol,
                side=OrderSide.SELL,
                order_type=ot,
                amount=amount,
                price=exec_price,
            )

            if order is None:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"SELL ABORTED: exchange/guard returned no order for "
                        f"{amount:.6f} {self.config.target_asset} @ "
                        f"${price:.8f}. No state update. Caller must not "
                        f"treat this as success."
                    ),
                )
                logger.warning(
                    "Bot %s sell aborted (order None) for %.6f at %.4f",
                    self.bot_id,
                    amount,
                    price,
                )
                try:
                    await self._reconcile_holdings(reason="post_failure")
                except Exception as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s",
                        "_execute_sell",
                        type(_sup).__name__,
                        _sup,
                    )
                return None

            self._current_holdings -= amount
            self.stats.total_sells += 1
            self.stats.total_trades += 1

            actual_fill = getattr(order, "average", None) or getattr(
                order, "price", None
            )
            if not actual_fill or actual_fill <= 0:
                actual_fill = price
            # issue #133 unit 9b -- the only point on the SCRUM and
            # DIST paths that holds the settled order, so the venue's
            # fee is carried from here.
            self._record_venue_fee(order, amount, actual_fill)
            slippage_pct = ((actual_fill - price) / price * 100.0) if price > 0 else 0.0

            self.stats.trade_volume += amount * actual_fill
            self.stats.last_trade_time = time.time()

            try:
                _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
                _fill_usd = float(amount) * float(actual_fill) * _qrate
                self.stats.ytd_scrummed_usd = (
                    float(getattr(self.stats, "ytd_scrummed_usd", 0.0) or 0.0)
                    + _fill_usd
                )
            except (TypeError, ValueError) as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_sell",
                    type(_sup).__name__,
                    _sup,
                )

            self._memorised_trades.append(
                MemorisedTrade(
                    timestamp=time.time(),
                    side="sell",
                    price=actual_fill,
                    amount=amount,
                    voting_summary=summary,
                )
            )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"SELL FILLED: {amount:.6f} {self.config.target_asset} "
                f"@ ${actual_fill:.8f} "
                f"(intended ${price:.8f}, slip {slippage_pct:+.3f}%)",
            )
            self._emit_trade_notification(
                "SCRUM", "FILLED", f"{amount:.6f} @ ${actual_fill:.8f}"
            )
            logger.info(
                "Bot %s sold %.6f at %.4f (intended %.4f, slip %+.3f%%, confidence=%.2f)",
                self.bot_id,
                amount,
                actual_fill,
                price,
                slippage_pct,
                summary.consensus_confidence,
            )
            return actual_fill
        except Exception as exc:
            self._bus.emit("bot.log", bot_id=self.bot_id, message=f"SELL FAILED: {exc}")
            logger.error("Bot %s sell failed: %s", self.bot_id, exc)
            try:
                await self._reconcile_holdings(reason="post_failure")
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_sell",
                    type(_sup).__name__,
                    _sup,
                )
            return None

    async def _verify_buy_safe_or_refuse(
        self,
        *,
        path: str,
    ) -> tuple[Optional[float], str]:
        """Fail-closed ScrummingBot wrapper around the generalized
        buy-safety helper at
        ``src/trading/buy_safety.py::verify_buy_safe_or_refuse``.

        Returns ``(verified_units, refuse_reason)``. If
        ``refuse_reason`` is non-empty, the caller MUST refuse the
        buy and emit the reason to ``bot.log``. Otherwise
        ``verified_units`` is the bot's current position in
        ``target_asset`` units (may be ``0.0`` for legitimately-empty).

        ScrummingBot's expected-units source: ``sum(lot["units"]
        for lot in self._main_lots)`` — the bot's full attributed
        position across all open lots.
        """
        from .buy_safety import verify_buy_safe_or_refuse

        expected_units = sum(
            float(lot.get("units", 0.0)) for lot in getattr(self, "_main_lots", [])
        )
        return await verify_buy_safe_or_refuse(
            self.exchange,
            self.config.target_asset,
            expected_units,
            path=path,
        )

    async def _execute_buy(
        self,
        cost: float,
        price: float,
        summary: VotingSummary,
        trace_context: Optional[dict] = None,
    ) -> Optional[float]:
        """Execute a buy order. Returns actual fill price captured from
        the exchange response. See _execute_sell docstring for the
        Chunk 6 fill-price-capture design.
        has full causal context on every buy."""

        try:
            _ctx = dict(trace_context or {})
            _path = _ctx.get("path", "unspecified")
            _holdings = self._current_holdings
            _value = _holdings * price * float(self._quote_to_usd or 1.0)
            _delta = _value - self._target_balance
            _tranches_n = len(self._fold_tranches)
            _main_lots_n = len(self._main_lots)
            _ctx_extras = ", ".join(f"{k}={v}" for k, v in _ctx.items() if k != "path")
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MEM-205 BUY TRACE: path={_path} "
                    f"value=${_value:.4f} target=${self._target_balance:.2f} "
                    f"delta=${_delta:+.4f} cost=${cost:.4f} price=${price:.8f} "
                    f"holdings={_holdings:.6f} "
                    f"main_lots={_main_lots_n} fold_tranches={_tranches_n} "
                    f"initialised={self._initialised} "
                    f"conf={summary.consensus_confidence:.2f}"
                    + (f" | {_ctx_extras}" if _ctx_extras else "")
                ),
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s", "_execute_buy", type(_sup).__name__, _sup
            )

        if (
            self._hyst_armed_fold_side
            and self._hyst_ref_fold_side > 0
            and getattr(self.config, "scrumming_interval_pct", 0) > 0
        ):
            try:
                _px_check = float(price)
            except (TypeError, ValueError):
                _px_check = 0.0
            _interval = float(self.config.scrumming_interval_pct)
            _fee = float(getattr(self.config, "trading_fee_pct", 0.6))
            _eff_pct = _interval + _fee
            _interval_frac = _eff_pct / 100.0
            _required_max = self._hyst_ref_fold_side * (1.0 - _interval_frac)
            if _px_check > 0 and _px_check > _required_max:
                _drop_pct = (
                    (self._hyst_ref_fold_side - _px_check)
                    / self._hyst_ref_fold_side
                    * 100.0
                )
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD REFUSED (opposing hysteresis v3.15.77): "
                        f"pivot ref ${self._hyst_ref_fold_side:.8f} "
                        f"(captured when Δ crossed negative after recent "
                        f"SCRUM), current ${_px_check:.8f} "
                        f"(only {_drop_pct:+.2f}% from pivot). "
                        f"Need ≥ {_eff_pct:.2f}% drop "
                        f"(interval {_interval:.2f}% + fee {_fee:.2f}%; "
                        f"price ≤ ${_required_max:.8f}) before "
                        f"FOLD can fire."
                    ),
                )
                self._emit_trade_notification(
                    "FOLD", "CANCELLED", f"hysteresis (need ≥ {_eff_pct:.2f}% drop)"
                )
                return None

        _max_ep = getattr(self.config, "max_entry_price", None)
        _min_ep = getattr(self.config, "min_entry_price", None)
        try:
            _px = float(price) if price is not None else 0.0
        except (TypeError, ValueError):
            _px = 0.0
        if _max_ep is not None and _px > 0 and _px > float(_max_ep):
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"BUY REFUSED (max_entry_price gate): current "
                    f"price ${_px:.8f} > max_entry_price "
                    f"${float(_max_ep):.8f}. Operator-set ceiling. "
                    f"Bot stands down until price drops below."
                ),
            )
            return None
        if _min_ep is not None and _px > 0 and _px < float(_min_ep):
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"BUY REFUSED (min_entry_price gate): current "
                    f"price ${_px:.8f} < min_entry_price "
                    f"${float(_min_ep):.8f}. Operator-set floor. "
                    f"Bot stands down until price rises above."
                ),
            )
            return None

        try:
            _open = await self.exchange.get_open_orders(self.config.symbol)
        except Exception as _oo_exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"P0b BUY REFUSED (fail-closed): "
                    f"get_open_orders raised {type(_oo_exc).__name__}: "
                    f"{_oo_exc}. Cannot verify absence of stacked "
                    f"orders. Refusing."
                ),
            )
            return None
        try:
            from ..exchange.base import OrderSide as _OS

            _open_buys = [
                o
                for o in (_open or [])
                if getattr(o, "side", None) == _OS.BUY
                and getattr(o, "symbol", None) == self.config.symbol
            ]
        except Exception:
            _open_buys = [
                o
                for o in (_open or [])
                if getattr(o, "symbol", None) == self.config.symbol
            ]
        if _open_buys:
            _ids = ", ".join(str(getattr(o, "id", "?")) for o in _open_buys[:3])
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"P0b STACKED BUY REFUSED: {len(_open_buys)} open "
                    f"BUY order(s) already on exchange for "
                    f"{self.config.symbol} (ids: {_ids}). "
                    f"Refusing to place a second BUY on top. "
                    f"Wait for existing order(s) to fill or cancel."
                ),
            )
            return None

        _ctx = trace_context or {}
        _path = _ctx.get("path", "unspecified")
        _cap_pct = float(getattr(self.config, "max_target_growth_pct", 1.0))
        _anchor = float(getattr(self, "_anchor_target_balance", self._target_balance))
        _per_cycle_growth_budget = _anchor * (_cap_pct / 100.0)

        _fresh_units, _refuse_reason_msg = await self._verify_buy_safe_or_refuse(
            path=_path
        )
        if _refuse_reason_msg:
            self._bus.emit("bot.log", bot_id=self.bot_id, message=_refuse_reason_msg)
            logger.warning("Bot %s %s", self.bot_id, _refuse_reason_msg)
            return None

        _qrate_buy = float(self._quote_to_usd or 1.0)
        _ceiling_units = sum(float(lot.get("units", 0) or 0) for lot in self._main_lots)
        _current_position_usd = _ceiling_units * price * _qrate_buy
        _projected_position_usd = _current_position_usd + cost

        _target_delta_usd = float(self._target_balance) - _current_position_usd
        _slippage_tol_pct = 0.5
        if _path == "zero_balance_initial_entry":
            _path_budget = float(self._target_balance)
        elif _path in ("fold_rebuy", "manual_tranche_fire"):
            _path_budget = float(cost)
        elif _path == "hedge_replenish":
            try:
                _hedge_limit = float(getattr(self, "_hedge_bal", 0.0) or 0.0)
            except (TypeError, ValueError):
                _hedge_limit = 0.0
            _path_budget = _hedge_limit
        else:
            _path_budget = max(0.0, _target_delta_usd) + _per_cycle_growth_budget
            logger.warning(
                "Bot %s _execute_buy: unspecified path used the conservative "
                "fold_rebuy-equivalent budget (cost=$%.2f, budget=$%.2f). "
                "If this is a new legitimate path, enumerate it in the "
                "Layer 1 dispatch.",
                self.bot_id,
                cost,
                _path_budget,
            )

        _budget_with_tol = _path_budget * (1.0 + _slippage_tol_pct / 100.0)
        if cost > _budget_with_tol:
            _reason = (
                f"MEM-251 v2 LAYER 1 BREACH — buy REFUSED. "
                f"Path={_path}. Current position=${_current_position_usd:.2f} "
                f"({_fresh_units:.8f} {self.config.target_asset} @ "
                f"${price:.8f}). Target=${self._target_balance:.2f}, "
                f"Target Delta=${_target_delta_usd:+.2f}. "
                f"Path budget=${_path_budget:.2f} (+{_slippage_tol_pct:.2f}% "
                f"tol → ${_budget_with_tol:.2f}). Proposed cost ${cost:.2f} "
                f"exceeds budget. No buy may exceed its path's Target-Delta "
                f"+ per-cycle-growth allowance."
            )
            self._bus.emit("bot.log", bot_id=self.bot_id, message=_reason)
            logger.warning("Bot %s %s", self.bot_id, _reason)
            return None

        if getattr(self.config, "position_ceiling_enabled", False):
            try:
                _smart_ceiling_usd = self.position_ceiling_usd
            except Exception:
                _smart_ceiling_usd = None
            if _smart_ceiling_usd is not None and _smart_ceiling_usd > 0:
                if _projected_position_usd > _smart_ceiling_usd:
                    _reason = (
                        f"MEM-251 v2 LAYER 2 (SMART CEILING) BREACH — "
                        f"buy REFUSED. Path={_path}. Projected position "
                        f"${_projected_position_usd:.2f} > Smart Ceiling "
                        f"${_smart_ceiling_usd:.2f} (anchor "
                        f"${_anchor:.2f} × multiple "
                        f"{self.config.position_ceiling_multiple}). "
                        f"Bot has reached configured maturity — no further "
                        f"acquisition until detonation harvests grown "
                        f"position on next bullish higher-TF vote."
                    )
                    self._bus.emit("bot.log", bot_id=self.bot_id, message=_reason)
                    logger.warning("Bot %s %s", self.bot_id, _reason)
                    return None

        try:
            amount = cost / price
            if _qrate_buy > 0 and abs(_qrate_buy - 1.0) > 1e-9:
                amount = amount / _qrate_buy

            from ..core.execution_discipline import verify_hit as _vh

            vh_fp, vh_status, vh_samples = _vh(
                price, "buy", symbol=self.config.target_asset
            )
            self.stats.verify_samples += vh_samples
            if vh_fp is None:
                self.stats.verify_canceled += 1
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"BUY CANCELED (R55 VH): slippage would "
                    f"exceed {self.config.target_asset} class "
                    f"tolerance @ ${price:.8f}",
                )
                logger.info(
                    "Bot %s VH-canceled buy of %.6f at %.4f", self.bot_id, amount, price
                )
                return
            if vh_status == "clean":
                self.stats.verify_clean += 1
            else:
                self.stats.verify_adjusted += 1
                amount = cost / vh_fp
                if _qrate_buy > 0 and abs(_qrate_buy - 1.0) > 1e-9:
                    amount = amount / _qrate_buy

            if self._invisible:
                ot = OrderType.MARKET
                exec_price = None
            else:
                ot = OrderType.LIMIT
                exec_price = vh_fp

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"BUY signal: {amount:.6f} @ ${price:.8f} "
                f"(VH:{vh_status}, confidence="
                f"{summary.consensus_confidence:.2f}, "
                f"{'MARKET' if self._invisible else 'LIMIT'})",
            )
            self._emit_trade_notification(
                "FOLD", "SENT", f"{amount:.6f} @ ${price:.8f}"
            )

            order = await self.guarded_place_order(
                symbol=self.config.symbol,
                side=OrderSide.BUY,
                order_type=ot,
                amount=amount,
                price=exec_price,
            )

            if order is None:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"BUY ABORTED: exchange/guard returned no order for "
                        f"{amount:.6f} {self.config.target_asset} @ "
                        f"${price:.8f}. No state update. Caller must not "
                        f"treat this as success."
                    ),
                )
                logger.warning(
                    "Bot %s buy aborted (order None) for %.6f at %.4f",
                    self.bot_id,
                    amount,
                    price,
                )
                try:
                    await self._reconcile_holdings(reason="post_failure")
                except Exception as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s",
                        "_execute_buy",
                        type(_sup).__name__,
                        _sup,
                    )
                return None

            self._current_holdings += amount
            self.stats.total_buys += 1
            self.stats.total_trades += 1

            actual_fill = getattr(order, "average", None) or getattr(
                order, "price", None
            )
            if not actual_fill or actual_fill <= 0:
                actual_fill = price
            slippage_pct = ((actual_fill - price) / price * 100.0) if price > 0 else 0.0

            self.stats.trade_volume += amount * actual_fill
            self.stats.last_trade_time = time.time()

            try:
                _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
                _fill_usd = float(amount) * float(actual_fill) * _qrate
                self.stats.ytd_folded_usd = (
                    float(getattr(self.stats, "ytd_folded_usd", 0.0) or 0.0) + _fill_usd
                )
            except (TypeError, ValueError) as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_buy",
                    type(_sup).__name__,
                    _sup,
                )

            self._memorised_trades.append(
                MemorisedTrade(
                    timestamp=time.time(),
                    side="buy",
                    price=actual_fill,
                    amount=amount,
                    voting_summary=summary,
                )
            )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"BUY FILLED: {amount:.6f} {self.config.target_asset} "
                f"@ ${actual_fill:.8f} "
                f"(intended ${price:.8f}, slip {slippage_pct:+.3f}%, "
                f"holdings now {self._current_holdings:.6f})",
            )
            self._emit_trade_notification(
                "FOLD", "FILLED", f"{amount:.6f} @ ${actual_fill:.8f}"
            )

            await self._spawn_stack_from_fold(
                fold_price=actual_fill, fold_size=amount, summary=summary, path=_path
            )
            return actual_fill
        except Exception as exc:
            self._bus.emit("bot.log", bot_id=self.bot_id, message=f"BUY FAILED: {exc}")
            logger.error("Bot %s buy failed: %s", self.bot_id, exc)
            try:
                await self._reconcile_holdings(reason="post_failure")
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_buy",
                    type(_sup).__name__,
                    _sup,
                )
            return None

    def memorize_to_grid(self) -> list[dict]:
        """
        Convert memorised scrumming trades into grid-style buy/sell pairs
        with organic/random price levels from actual trade history.
        """
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
        """Human-readable snapshot of the tranche-gate state for debugging."""
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
        """Stop this bot and all its phantom balance bots."""
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
        """A filled FOLD spawns the Stack ladder above it. Returns how
        many Stack tranches were created, 0 when none were.
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

        Returns an empty list when no manager is attached or no child
        matches -- which is every bot the operator runs without an
        Extractor. A child that raises is logged and skipped, so one bad
        child cannot blind the parent to the rest.
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
