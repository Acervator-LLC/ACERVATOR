"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
scrumming_bot.py — Accumulation Trading Bot (live engine)
==========================================================
# ┌─────────────────────────────────────────────────────────────┐
# │ AI DEVELOPER NOTE                                           │
# │                                                             │
# │ This is the LIVE trading engine. The simulator has its own  │
# │ copy of this logic in src/gui/simulator.py at               │
# │ _sim_scrumming_tick(). Any change here MUST be mirrored     │
# │ there, and vice versa. This is known technical debt.        │
# │                                                             │
# │ The core algorithm:                                         │
# │   1. Compute delta = (holdings × price) - target            │
# │   2. If delta > 0 and delta_pct >= interval: SCRUM          │
# │      (sell excess, deposit USD into fold queue)              │
# │   3. If fold_queue > 0 and price < fold_ref: FOLD           │
# │      (buy back at lower price, accumulate extra asset)      │
# │   4. After fold: target += profit (compound growth)         │
# │                                                             │
# │ CRITICAL: fold ONLY executes when price < fold_ref.         │
# │ This guarantees more asset is bought back than was sold.    │
# │ DO NOT change this condition.                               │
# │                                                             │
# │ See ARCHITECTURE.md for full invariants list.               │
# └─────────────────────────────────────────────────────────────┘

Implements the Accumulation Trading strategy with:

  • 7-indicator TA engine with confidence/voting logic
  • Phantom Balance Bot integration for multi-timeframe analysis
  • Higher-timeframe prioritization and contradiction prevention
  • Memorize function for organic grid conversion
  • Profit Folding and Upward Distribution
  • Extended Position creation
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, asdict
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..exchange.base import ExchangeInterface

from ..exchange.base import OrderSide, OrderType
from .wallet_reservations import get_wallet_reservations, wallet_key
from .bot_container import (
    BotContainer, BotConfig, BotMode, BotState,
    as_finite_float, despawn_threshold_days,
)
from .ta_engine import (
    VotingEngine, VotingSummary, SignalDirection, candles_from_raw,
    detect_bb_proximity, BBProximityResult,
    detect_landing_strip_v2,
)
from .phantom_balance import (
    PhantomBalanceManager, TimeframeCoordinator,
)
# v3.18.12 (TA-gate cleanup Step 4) — GateChain framework. The two
# autonomous trigger conjunctions in tick() (SCRUM ~line 5512, FOLD
# ~line 6148) now delegate to self._scrum_chain.evaluate(ctx) /
# self._fold_chain.evaluate(ctx). The framework was added in v3.18.11
# (additive) and validated against the v3.18.9 baseline fixture via
# tests/test_gate_chain_parity.py — bit-identical across 200 ticks
# before this cutover landed. Per the audit doc § 7.
from .gate_chain import (
    GateContext, build_scrumming_scrum_chain, build_scrumming_fold_chain,
)

logger = logging.getLogger("acervator.scrumming")


# ---------------------------------------------------------------------------
# v3.15.55 — USD-stable quote-currency set (operator directive 2026-04-25):
#   "Target Balance only looks at the Base Currency and it must be
#    extrapolated into USD ... For these crypto only pairs, ensure that the
#    Target Asset always equals the stated value in USD but trades are
#    performed in BTC or ETH or whatever the base currency might be."
#
# Many sites in this engine compute `holdings * ticker.last` and compare
# the result against `target_balance` (which is operator-stated USD). For
# USD-quoted pairs (BTC/USD, ETH/USDC) the comparison is correct because
# ticker.last is already USD. For crypto-quoted pairs (BTC/ETH, SOL/BTC,
# anything/BTC) ticker.last is in QUOTE units (ETH-per-BTC), so the
# product is in QUOTE-units, NOT USD — comparing it against a USD target
# yields garbage (operator saw "$50 of BTC + $50 of ETH but BTC/ETH
# Target Balance shows negative").
#
# The fix: maintain a `_quote_to_usd` multiplier on every bot.
#   • USD-stable quote → multiplier is 1.0
#   • Crypto quote     → multiplier is the QUOTE/USD ticker.last
# Every USD-comparison site multiplies `holdings * price` by this rate;
# every USD-spend → quote-amount conversion divides by it.
# ---------------------------------------------------------------------------
_TA_CONFIDENCE_FLOOR = 0.25
"""Minimum TA confidence before a direction counts as actionable.

v3.24.43 — this was a bare ``0.25`` literal inlined twice in ``tick()``.
Naming it changes NO behaviour; it makes the gate greppable and lets the
logs quote the same number they are enforcing.

WHY IT MATTERS. ``is_bullish`` / ``is_bearish`` require the direction AND
this floor. An operator who sets ``fold_require_ta_bearish = True`` is
therefore also opting into "and confidence >= 0.25" without being told:
there is no config key for this value anywhere in ``src/``, and no
corresponding field on any live bot.

Measured 2026-08-06 against the live diagnostics log: ``TA-not-bearish``
was the single most frequent fold blocker, present in 214 of 229
FOLD_DIAG_BLOCKED events (93%), while 4,516 of 7,209 tranches (62.6%)
were strict-eligible and refused. Whether the floor itself is correctly
placed is a strategy decision and is deliberately NOT changed here.
"""

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
    rolled = tranche.setdefault("wire_credits_rolled", {
        "count": 0, "total_usd": 0.0, "by_source": {},
        "first_ts": None, "last_ts": None})
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
        rolled["total_usd"] = round(
            float(rolled.get("total_usd", 0.0) or 0.0) + usd, 8)
        by_source[src] = round(
            float(by_source.get(src, 0.0) or 0.0) + usd, 8)
        ts = e.get("ts")
        if ts is not None:
            if rolled.get("first_ts") is None:
                rolled["first_ts"] = ts
            rolled["last_ts"] = ts
    return len(overflow)


_USD_STABLE_QUOTES = frozenset({
    "USD", "USDC", "USDT", "USDS", "USDP", "USDD", "DAI",
    "BUSD", "GUSD", "TUSD", "PYUSD", "FDUSD",
})


def is_usd_stable_quote(currency: str) -> bool:
    """Return True if the given currency code is a USD-equivalent stable.

    Stable quotes get a 1.0 quote→USD multiplier; non-stable quotes
    require a {QUOTE}/USD ticker fetch to recover the USD rate.
    """
    return (currency or "").upper() in _USD_STABLE_QUOTES


# v3.20.9 — Risk-gate forensic-snapshot helper (audit Finding #10 closure).
#
# The v3.20.6 audit's cross-cutting finding #10 was that "risk gates"
# (CircuitBreaker, SmartCeiling, Hysteresis) consume position/risk
# flags rather than voter output — so when they block a trade, the
# operator can't ask "which indicators were what when this fired?"
# bot.log captures the gate's name but not the panel state at the
# moment of firing.
#
# This module-level constant names the gate-chain entries that count
# as "risk gates" for forensic purposes. When ANY of these appear in
# a blocked chain result, the post-tick emitter writes a structured
# RISK GATE SNAPSHOT line to bot.log capturing the full voter panel.
# Operator grep-pattern: `grep "RISK GATE SNAPSHOT" bot.log` returns
# every risk-blocked tick with its indicator context.
#
# Names match `Gate.name` attribute values in src/trading/gate_chain.py.
_RISK_GATE_NAMES: frozenset = frozenset({
    "circuit_breaker_scrum",
    "circuit_breaker_fold",
    "smart_ceiling",
    "hysteresis_scrum",
    "hysteresis_fold",
})


def _build_panel_snapshot(
    summary: Optional["VotingSummary"],
) -> dict:
    """Capture a compact {indicator: {dir, conf, weight, detail}} dict
    from VotingSummary.signals. Used by the risk-gate forensic emitter.

    NEUTRAL voters are included (they're informative for forensics —
    "indicator was NEUTRAL at risk-block time" is a real data point).
    Confidence rounded to 3 decimals; weight included so a future
    reader can reconstruct the contribution magnitude.

    Returns empty dict when summary is None (pre-TA tick).
    """
    if summary is None:
        return {}
    snap: dict = {}
    for sig in summary.signals:
        try:
            dir_name = (sig.direction.name
                        if hasattr(sig.direction, "name")
                        else str(sig.direction))
        except Exception:  # R28-OK: forensic best-effort; defensive over any unexpected direction type
            dir_name = "UNKNOWN"
        # Headline detail from each indicator (the non-% panel cells —
        # ADX raw, ZSc signed, KER raw — surface here too).
        detail_value = None
        for key in ("adx", "z", "er"):
            if key in (sig.details or {}):
                detail_value = sig.details[key]
                break
        snap[sig.indicator] = {
            "dir": dir_name,
            "conf": round(float(sig.confidence), 3),
            "weight": round(float(sig.weight), 3),
            "detail": detail_value,
        }
    return snap


def _extract_signal_detail(
    summary: Optional["VotingSummary"],
    indicator_name: str,
    detail_key: str,
    default: float = 0.0,
) -> float:
    """v3.19.18 — call-site activation helper for gate-chain context fields.

    Pulls a numeric ``detail`` value from a named ``Signal`` in the
    ``VotingSummary.signals`` list. Used by ScrummingBot.tick() to wire
    the v3.19.16 ADX gate (``ctx.adx``) and v3.19.17 EfficiencyRatio gate
    (``ctx.efficiency_ratio``) from the live VotingEngine output.

    Returns ``default`` (sentinel) when:
      • ``summary`` is None (insufficient candles, no TA yet)
      • The named indicator isn't present (defensive: should always be
        present after v3.19.16/v3.19.17 wiring, but the additive-landing
        contract is "sentinel-pass on any gap")
      • The detail value is missing or None

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


# ---------------------------------------------------------------------------
# Memorised trade (for conversion to grid positions)
# ---------------------------------------------------------------------------
@dataclass
class MemorisedTrade:
    """A scrumming event stored for potential conversion to a grid level."""
    timestamp: float
    side: str
    price: float
    amount: float
    voting_summary: Optional[VotingSummary] = None


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


# ---------------------------------------------------------------------------
# Scrumming bot v1.1
# ---------------------------------------------------------------------------
class ScrummingBot(BotContainer):
    """
    Speculative Scrumming auto-trader v1.1.

    New in v1.1:
      • Full 7-indicator TA engine (Bollinger, Vortex, MACD, StochRSI,
        Ichimoku, Volume, Slingshot) with confidence/voting
      • Phantom Balance Bots for multi-timeframe analysis
      • Higher-TF prioritization locks contradicting lower-TF trades
      • Configurable indicator weights and confidence thresholds
    """

    # v3.19.23 (Part 6 L9 pushback closure): 30m added as the tactical-
    # timing screen in the Triple Screen framework. Previously the
    # default had 5m + 15m for sub-parent fine-tuning and 4h + 1d as the
    # two higher-TF screens, but no dedicated tactical (LTF trigger)
    # scale around the 30-minute cadence. L9 (Multi-TF Psychology) called
    # for "adding a 15m or 30m phantom for tactical timing to complete
    # the framework." 30m chosen because 15m was already present;
    # adding the gap-filling scale makes the per-TF coverage more even.
    # The strict Triple Screen sequence gate ("HTF direction → MTF wave
    # → LTF trigger") is queued as a separate follow-up — this ship is
    # the additive phantom-set change.
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
                f"ScrummingBot requires BotMode.SCRUMMING; "
                f"got {config.mode!r}")
        super().__init__(config, exchange)

        self._target_balance = config.target_balance
        self._current_holdings: float = 0.0
        self._last_price: float = 0.0
        self._memorised_trades: list[MemorisedTrade] = []
        self._initialised = False
        self._invisible = config.visibility == "internal"
        self._aggressive = config.aggressive_trading
        # v3.24.1 — sim_mode isolation flag. When True, this bot
        # suppresses TRADE NOTIFICATION emits so the live main_window
        # sound-engine path (main_window.py:343 intercepts
        # "TRADE NOTIFICATION:" prefix and calls play_state_change)
        # does not fire during Fleet Replay. Also serves as a
        # single-attr contract for future sim-isolation shields
        # (analytics writes, order persistence, etc.).
        self._sim_mode = bool(sim_mode)
        # v3.24.31 — INJECTED capital-reservation registry.
        #
        # Operator directive 2026-08-05: sim bots must be "simulator
        # equivalents with all of the same functionality except that
        # operate in a simulated environment."
        #
        # Reservation was previously SKIPPED in sim (`if _sim_mode:
        # return`), which REMOVES the feature rather than simulating
        # it. The registry is a process-wide singleton persisted to
        # ~/.acervator/reservation_state.json — LIVE state — so a sim
        # bot could not safely share it. Injecting a private,
        # non-persisting instance lets the real reservation code path
        # RUN, isolated, instead of being switched off.
        self._capital_registry = capital_registry
        if self._sim_mode:
            # v3.24.12 — ISOLATE THE SIM BUS.
            #
            # BotContainer.__init__ assigns the GLOBAL singleton bus
            # (bot_container.py:870). LogManager is attached to that
            # same bus, so a sim bot's trade.filled / gate.decision /
            # voting emits were being written into the LIVE logs at
            # ~/.acervator_logs/trade/ as though they were real fills.
            #
            # Measured 2026-08-02: 136 of 699 rows in live trade.log
            # (19.5%) came from 50 bot_ids that do not exist in
            # bot_state.json — all dated 2026-08-01, the day Fleet
            # Replay was first exercised. They carried symbol="" only
            # because main.py's bot_id->symbol resolver could not find
            # a sim bot in the live BotManager; the contamination
            # itself was silent.
            #
            # v3.24.1's sim_mode suppressed TRADE NOTIFICATION (the
            # sound path) but left trade.filled reaching the bus.
            # Swapping the bus wholesale closes every emit route at
            # once instead of guarding 9 call sites individually, and
            # cannot be defeated by a future emit site that forgets to
            # check the flag.
            #
            # The sim's own accounting is unaffected: FleetSimExchange
            # counts fills through its on_trade callback, not the bus.
            try:
                from ..core.event_bus import EventBus
                self._bus = EventBus()
            except Exception as _bus_exc:
                # v3.24.61 (C17 / SN-39) — FAIL CLOSED.
                #
                # This used to log a warning and CONTINUE, which left
                # `self._bus` pointing at the process-wide bus. The
                # warning even said so: "sim emits may reach live logs".
                # A sim bot silently emitting onto the live bus is the
                # exact condition this whole cascade exists to prevent,
                # and it was reachable by one failed construction.
                #
                # Losing a sim run is cheap. Method rule M10: a sim path
                # that cannot obtain its private bus aborts with an
                # operator-visible reason.
                logger.error(
                    "sim_mode: could not isolate the event bus (%s) — "
                    "refusing to construct the bot rather than emit "
                    "onto the live bus", _bus_exc)
                raise RuntimeError(
                    f"sim bus isolation failed: {_bus_exc}. Refusing to "
                    f"build a sim bot that would emit on the "
                    f"process-wide EventBus."
                ) from _bus_exc

        # v1.1: Full TA engine with voting
        self._ta_weights = ta_weights
        self._voting_engine = VotingEngine(weights=ta_weights)
        self._last_summary: Optional[VotingSummary] = None
        self._last_bb: Optional[BBProximityResult] = None
        # v3.16.16 — last-tick auto-fire gate evaluation. The dashboard
        # reads this via get_status_dict()["auto_fire"] to render the
        # fire button as solid (auto would fire) vs outline (manual
        # override only). Updated at the END of each tick.
        # Schema:
        #   {
        #     "scrum_armed": bool,        # auto-fire SCRUM would fire NOW
        #     "fold_armed": bool,         # auto-fire FOLD would fire NOW
        #     "scrum_blockers": list[str], # gate names blocking SCRUM
        #     "fold_blockers": list[str],
        #     "evaluated_at_tick": int,    # tick counter when computed
        #   }
        self._last_gate_state: dict = {
            "scrum_armed": False, "fold_armed": False,
            "scrum_blockers": ["pre-tick"], "fold_blockers": ["pre-tick"],
            "evaluated_at_tick": 0,
        }

        # v3.18.12 (TA-gate cleanup Step 4) — autonomous-trigger GateChains.
        # The 10-clause SCRUM AND-conjunction at tick() line ~5512 and the
        # 7-clause FOLD AND-conjunction at tick() line ~6148 both now
        # delegate to these chain.evaluate(ctx) calls. Chains are stateless
        # — single instance per bot lifetime. Step 3 parity test
        # (tests/test_gate_chain_parity.py) proved bit-identical
        # equivalence to the inline conjunctions across the v3.18.9
        # 200-tick baseline fixture before this cutover landed.
        self._scrum_chain = build_scrumming_scrum_chain()
        self._fold_chain = build_scrumming_fold_chain()

        # v1.1: Phantom Balance integration
        # v3.24.61 (C17 / SN-42) — thread THIS bot's bus in. Constructed
        # after the sim private-bus swap above, and previously without
        # the bus, so a sim bot's coordinator resolved and emitted on
        # the process-wide bus while the bot itself was isolated.
        self._coordinator = coordinator or TimeframeCoordinator(
            bus=self._bus)
        self._phantom_mgr = PhantomBalanceManager(self._coordinator)
        self._phantom_timeframes = phantom_timeframes or self.DEFAULT_PHANTOM_TIMEFRAMES

        # MEM-203 / v3.15.61 — filter phantom TFs to what the exchange
        # actually supports. The single source of truth is now
        # ``src/exchange/timeframes.py::available_timeframes``; this
        # block reads from there rather than carrying a hardcoded copy.
        # Coinbase Advanced Trade supports {1m, 5m, 15m, 30m, 1h, 2h,
        # 6h, 1d} — NOT 4h, 12h, 1w. Requesting unsupported TFs from
        # CCXT raises and spams the Console; filter rather than fail.
        try:
            from ..exchange.timeframes import available_timeframes as _avail_tfs
            _allowed = set(_avail_tfs(config.exchange_id))
        except Exception:  # R28-OK: optional TF filter; None = "trust the list"
            _allowed = None
        if _allowed is not None:
            _original = list(self._phantom_timeframes)
            self._phantom_timeframes = [
                tf for tf in self._phantom_timeframes if tf in _allowed
            ]
            _dropped = [tf for tf in _original if tf not in _allowed]
            if _dropped:
                # Defer log emit — bus attach happens after __init__.
                self._phantom_tf_dropped_note = (
                    f"v3.15.61 phantom-TF filter: dropped {_dropped} on "
                    f"exchange '{config.exchange_id}' — not supported by "
                    f"native API. Remaining: {self._phantom_timeframes}.")
            else:
                self._phantom_tf_dropped_note = None
        else:
            self._phantom_tf_dropped_note = None

        self._phantoms_enabled = enable_phantoms
        self._phantoms_started = False

        # Profit folding / upward distribution accumulators
        self._fold_accumulator: float = 0.0
        self._dist_accumulator: float = 0.0
        # Fold queue: USD queued from scrums, waiting for bearish price drop
        self._fold_queue_usd: float = 0.0
        self._fold_queue_ref_price: float = 0.0

        # v3.16.50 — Standing surplus accumulator (Tranche-Surplus discipline).
        # When a tranche fires and its USD value exceeds the amount needed
        # to re-zero the current Target Delta, the leftover is "surplus".
        # max_target_growth_pct is a PER-CYCLE rate cap, not a hard ceiling:
        # the surplus that exceeds this cycle's growth budget is parked here
        # and drained on subsequent cycles at the same rate. Operator
        # directive 2026-05-10: "the max target growth soft caps the
        # amount of standing surplus that will be used to increase the
        # Target Balance for the given cycle. This allows surplus to
        # accrue and be spread out over time."
        #
        # Drain mechanic (per cycle):
        #   per_cycle_growth_budget = anchor × (max_target_growth_pct / 100)
        #   this_cycle_growth = min(this_cycle_surplus + standing_surplus,
        #                           per_cycle_growth_budget)
        #   target_balance += this_cycle_growth
        #   standing_surplus = (this_cycle_surplus + standing_surplus)
        #                      - this_cycle_growth
        #
        # The ONLY organic Target-Balance growth path; nothing else may
        # mutate target via a fold-derived surplus channel.
        self._standing_surplus_usd: float = 0.0

        # MEM-202 — throttled HOLD-diagnostic counter. Increments every
        # tick where delta > 0 but the bot held. Used for diagnostic
        # log emission (once per 50 holds) so operator can see WHY the
        # bot is holding. Purely diagnostic; no behavior effect.
        self._hold_tick_counter: int = 0

        # MEM-208 — exchange balance reconciliation counters. Bumped
        # per tick; reconcile fires at multiples of _reconcile_interval.
        # Also fires on init (first tick after start) and immediately
        # after any trade-abort path (BUY ABORTED / SELL ABORTED) where
        # exchange reality might have diverged from internal state.
        self._reconcile_tick_counter: int = 0
        self._reconcile_interval: int = 20  # ~every 20 ticks (≈10 min at 30s cadence)

        # v3.13.8 MEM-069 + MEM-171 port — per-tranche provenance fold queue
        # + initial-buy-price floor (patent-flagged inventions ADR-010 / ADR-004).
        # Each scrum creates a tranche preserving the initial_buy_price of
        # the main_lots it consumed (HIGHEST-PRICE-FIRST). On fold, rebuys
        # are gated by: current price must be BELOW the tranche's
        # initial_buy_price — no unit is ever rebought at a higher price
        # than it was originally acquired at.
        #
        # Data shapes:
        #   _fold_tranches: list of {usd, units, ref, initial_buy_price}
        #   _main_lots:     list of {units, initial_buy_price}
        #
        # Invariant: sum(l["units"] for l in _main_lots) == _current_holdings
        # (within float tolerance). Enforced by tests; inspected at runtime
        # via _main_lots_invariant_ok().
        #
        # The legacy _fold_queue_usd and _fold_queue_ref_price scalars above
        # are kept as derived aggregates (see properties below) for any
        # downstream code that reads them during migration.
        self._fold_tranches: list[dict] = []
        self._main_lots: list[dict] = []

        # v3.23.26 — Stack Mode ledger. Populated by 2B-2's SCRUM path
        # when self.config.stack_mode is True; each dict = one Stack
        # tranche (Tranche.to_dict() from src/trading/stack_math.py:
        # {"index": int, "price": float, "size": float}). Iteration is
        # append-only; entries are marked filled or removed as the tick
        # loop reconciles them against the exchange (Invisible mode:
        # fire-on-cross; Visible mode: reconcile with fetch_open_orders).
        # Bounded to a few tranches by n_target × operator config.
        self._stack_tranches: list[dict] = []
        self._stack_created: int = 0    # lifetime counter (mirror of _fold_created)
        # Item 9 (2026-08-13) — stack tranches DELISTED without filling.
        # The mirror of `_tranches_discarded_lifetime` on the fold side,
        # added for the same reason that one was: the despawn sweep
        # REMOVES stack tranches, and with nothing recording the removal
        # `_stack_created` kept climbing while the standing list shrank.
        # The Stack panel divides by that created total, so every sweep
        # drove its fill ratio down permanently with nothing on screen
        # to account for the gap.
        #
        # ON THIS LEDGER `closed` IS STRUCTURALLY ZERO, which is why no
        # closed counter is added beside this one. Filling a stack
        # tranche sets `status` and LEAVES THE RECORD LISTED
        # (`_spend_activated_stack_tranches` and both reconcilers only
        # mutate the dict), so the despawn sweep is the only site in
        # src/ that removes one. `created - closed - discarded ==
        # standing` therefore reads here as `created - 0 - discarded ==
        # len(_stack_tranches)`.
        self._stack_discarded: int = 0

        # v3.16.39 P2-VIS — Fold-tranche lifetime visibility counters.
        # Operator directive 2026-05-08 (post live-trading evaluation):
        # surface in Bot Settings how many tranches the bot has opened
        # vs. closed over its lifetime, so the operator can see Leg-1 /
        # Leg-2 cycle health at a glance instead of needing a CSV pull.
        # Created counter increments at every _fold_tranches.append site;
        # closed counter increments by `_removed` on every fold-back
        # dequeue at scrumming_bot.py:5329 region. Both persist via
        # export/import_scrumming_state with default 0 backward-compat.
        # Cycle close ratio (closed/created) signals strategy throughput:
        # ratio approaches 1.0 in equilibrium, drifts low if fold-back
        # is stagnating (e.g., asset price never reaches initial_buy
        # trigger).
        self._tranches_created_lifetime: int = 0
        self._tranches_closed_lifetime: int = 0
        # v3.23.7 Anomaly C: separate counter for malformed-tranche drops.
        # Malformed tranches (ref<=0) entering the queue were never real
        # cycles; counting them in closed_lifetime inflates the invariant.
        # Tracking them separately preserves operator visibility into
        # drop volume without polluting the closed/created throughput
        # ratio.
        self._tranches_malformed_dropped: int = 0

        # v3.13.8 MEM-186 / Chunk 2 — Detect/Fire Threshold state machine state.
        # Mirrors the canonical SEARCH → TRACK → FIRE lifecycle from
        # simulator.py lines 5305-5369. Gates scrum firing: a scrum only
        # fires when the state machine is in 'fire' state for the current
        # band side, which requires the operator's detect_pct / fire_pct
        # thresholds to both be passed in sequence.
        self._scrum_target_mode: str = 'search'  # 'search' | 'track' | 'fire'
        self._scrum_target_side: Optional[str] = None  # 'upper' | 'lower' | None

        # MEM-241 — Manual Fire rebalance-to-target state.
        # Operator directive (Session 24): "Manual Fire button should act
        # as an Aggressive Trade." ... "the amount Scrummed or Folded
        # will be the amount needed to get the Target Balance back to
        # center line." ... "Positive [delta] = Scrum while Negative =
        # Fold."
        #
        # Mechanism: when force_fire(aggressive=True) is called from the
        # GUI, we set _manual_fire_pending. The NEXT tick() sees the
        # flag, calls _execute_manual_rebalance(), and clears it. The
        # rebalance bypasses TA/BB/midline/MEM-171 gates (operator
        # override is absolute) and sizes the order as abs(delta_usd)
        # rounded to exchange precision. Uses MARKET order (aggressive).
        # Lots/tranches created are tagged operator_initiated=True for
        # downstream accounting visibility.
        self._manual_fire_pending: bool = False

        # MEM-244 — Position Ceiling + Detonation state (Session 24).
        # Operator directive: "Make that a switch. Institutions are
        # going to want it for sure. 1x~10x should be reasonable. Bot
        # should detonate on 1D or higher Timeframe on BULLISH
        # condition detection."
        #
        # ANCHOR: frozen at bot creation from config.target_balance.
        # Every risk-control calculation pivots around this stable
        # number. target_balance itself may grow during accumulation;
        # the anchor does not. On detonation, target_balance is reset
        # back to this anchor ("locks in" gains fully per operator
        # Q-answer, clean harvest-and-restart semantics).
        self._anchor_target_balance: float = float(config.target_balance)

        # Detonation edge-detection state. We fire only on transition
        # from non-bullish (or low-conf bullish) to BULLISH + conf >=
        # threshold. Otherwise a sustained bull run would re-detonate
        # every hour.
        self._detonation_last_check_ts: float = 0.0  # UNIX seconds
        self._detonation_last_signal_bullish: bool = False

        # v3.13.8 MEM-187 / Chunk 3 — Hedge Rebalance reserve.
        # Separate pool of USD that buys additional asset during dip
        # depletion (delta<0 and bb_pos<0.40 and !bullish) as a
        # countercyclical capital deployment. Replenished from fold
        # profit (8% of accum_profit) up to the initial reserve size.
        # Ported from RAIntSimBat.py:2144-2159 (hedge buy) and
        # lines 1794-1795, 1903-1904 (replenishment from fold profit).
        self._hedge_bal: float = (
            float(config.hedge_balance) if config.hedge_rebalance_active else 0.0)
        self._hedge_balance_initial: float = (
            float(config.hedge_balance) if config.hedge_rebalance_active else 0.0)
        self._hedge_trades: int = 0

        # v3.13.8 MEM-188 / Chunk 4 — Band Travel + Read Rate state.
        # Band Travel: tracks price distance from last executed trade as
        # a fraction of BB width. Triggers a trend_hold OVERRIDE (allows
        # scrum even during strong uptrend) when >= band_travel_pct%.
        # Ported from RAIntSimBat.py:1250-1252, 1246.
        #
        # Read Rate: per-tick skip counter. In SEARCH mode, bot processes
        # every N-th tick where N = scrum_read_rate_min / timeframe_min.
        # In TRACK/FIRE mode, N shrinks by 10x for faster polling.
        # Ported from simulator.py:5507, 5324, 5331, 5333.
        self._last_trade_price: float = 0.0
        # v3.15.52 — opposite-direction hysteresis safety per operator
        # directive 2026-04-25: "If a scrum or fold occurs then the
        # opposite CANNOT occur without price deviating by the minimum
        # scrum interval ... Scrum Interval is 3% the price must change
        # 3% in the opposing direction. No ifs ands or buts about it."
        #
        # _last_trade_side tracks whether the most recent fill was a
        # SCRUM (sell) or FOLD (buy). Subsequent opposite-side trades
        # are gated on price deviation by scrumming_interval_pct in the
        # required direction:
        #   - After SCRUM at price P, FOLD allowed only when current
        #     price ≤ P × (1 - interval%/100)
        #   - After FOLD at price P, SCRUM allowed only when current
        #     price ≥ P × (1 + interval%/100)
        # Manual fire BYPASSES this gate (uses guarded_place_order
        # directly; consistent with manual-fire-bypasses-everything).
        self._last_trade_side: Optional[str] = None  # "SCRUM" | "FOLD" | None

        # v3.15.77 — Conditional opposing-direction hysteresis state.
        # Operator directive 2026-04-27:
        #   "The opposing trade distance should not activate after one
        #    trade. The opposing directional movement should be confirmed
        #    first i.e. once the Target Delta begins drifting negative
        #    from the most recent Scrum. If the Target Delta goes
        #    positive again, it can deactivate. Similarly we need to
        #    have the opposing direction from a Fold to be the opposite
        #    with the Target Delta drifting positive to activate the
        #    gate. In markets that bouncing at the upper BB, this gate
        #    may flicker on and off frequently but that should be how
        #    it functions."
        #
        # Replaces v3.15.52's "always-on-since-last-trade-price"
        # hysteresis. The new model:
        #   • _hyst_armed_*_side  — armed iff the current Target Delta
        #     direction is OPPOSING the most recent trade direction.
        #     After a SCRUM, the FOLD-side gate arms when delta drifts
        #     negative; disarms when delta returns non-negative. After
        #     a FOLD, the SCRUM-side gate arms when delta drifts
        #     positive; disarms when delta returns non-positive.
        #   • _hyst_ref_*_side  — reference price captured at the
        #     moment of arming. Becomes the new pivot from which the
        #     opposing-direction price-distance requirement is
        #     measured. In oscillating markets each fresh arming
        #     captures a fresh pivot.
        # Both states reset to (False, 0.0) on every new fill so a
        # brand-new trade never inherits stale hysteresis.
        self._hyst_armed_fold_side: bool = False
        self._hyst_armed_scrum_side: bool = False
        self._hyst_ref_fold_side: float = 0.0
        self._hyst_ref_scrum_side: float = 0.0

        # v3.15.55 — quote→USD conversion rate (operator directive 2026-04-25:
        # crypto-quoted pairs like BTC/ETH must evaluate Target Balance in USD
        # despite trades executing in the base currency). For USD-stable
        # quotes this stays 1.0; for crypto quotes this is refreshed each
        # tick from the {QUOTE}/USD ticker. See _refresh_quote_to_usd().
        self._quote_to_usd: float = 1.0
        self._quote_to_usd_last_fetch: float = 0.0
        self._quote_to_usd_warned: bool = False

        self._tick_counter: int = 0  # increments each tick
        self._tick_skip: int = 1     # current skip interval (SEARCH=N, TRACK/FIRE=N/10)
        self._tick_skip_search: int = 1  # cached SEARCH value for restore

        # v3.16.41 P0-DIAG — Compound-mechanism diagnostic instrumentation.
        # Operator directive 2026-05-08 (post-v3.16.40 retraction): "I have
        # yet to see any Target Balances increase organically." After three
        # retracted speculative fixes, the proper investigation requires
        # runtime logging to observe the actual gate state across multiple
        # bots and BB cycles. These counters throttle diagnostic emission
        # so the log isn't flooded.
        #   _fold_diag_tick: monotonic counter, used for throttled snapshot
        #     emission (every N ticks when tranches exist)
        #   _fold_diag_last_blocker_set: dedup key for the "blocked" log
        #     so we don't spam the same blocker condition every tick
        self._fold_diag_tick: int = 0
        self._fold_diag_last_blocker_set: str = ""

        # v3.13.8 MEM-189 / Chunk 5 — Phantom lock state (scrum-only suppression).
        # When a higher-TF phantom has locked the bullish direction (e.g. 4h
        # phantom detects overbought conditions), the _phantom_locked flag
        # suppresses scrum harvesting ONLY. Folds, hedge buys, and DIST
        # remain active — downside protection must never be blocked by
        # phantom locks (per canonical sim comment RAIntSimBat.py:1263-1266).
        # Derived each tick from self._coordinator.is_locked — this field
        # is cached across the gate computation + logging.
        self._phantom_locked: bool = False
        self._phantom_lock_timeframe: str = ""

        # Smart Wire integration. (v3.23.37 — retired _mr_inspector +
        # set_mr_inspector: the crypto path never invoked the setter,
        # so the attribute was a phantom. The stocks path retains its
        # own MRInspector wiring in stock_accumulation_bot.py. HTF
        # market discovery moved to src.trading.market_inspector.)
        self._smart_wire_mgr = None  # Set externally via set_smart_wire()
        # v3.23.65 — Smart Wire Outflow Safety (SWOS) per-cycle
        # counter. Incremented by the scrum fill sites (right beside
        # `stats.total_scrummed_usd`) with the USD profit the bot
        # retained from that scrum. Reset to 0 on every Fold
        # execution — one Fold closes the cycle. Read by
        # get_swos_inputs() which feeds compute_safe_outflow_pct
        # in smart_wire.py. Persisted → bot_state.json restore is
        # OK to lose it (worst case: over-conservative safety on
        # the tick immediately after a restart, self-heals).
        self._retained_this_cycle_usd: float = 0.0
        # v3.23.47 — read-only cross-pair rate scout, attached via
        # set_market_pairs_scout() by the BotContainer / main_window
        # on bot creation. None until then; get_target_asset_pairs()
        # returns [] gracefully in that state.
        self._market_pairs_scout = None

        # v3.23.42 — CapitalReservationRegistry hook (F62 + F65 fix
        # per docs/audits/2026-07-27_interop_usd_denom_settlement_...).
        # Token is minted on the first tick that has ticker.last (need
        # price to convert target_balance USD → target-asset units).
        # Updated whenever _target_balance or personal_hold_qty change.
        # Released in stop(). Heartbeated per tick.
        self._crr_token: Optional[str] = None
        self._crr_last_reserved_qty: float = 0.0
        # v3.23.46 — exchange-balance cache for CRR over-commit enforcement.
        # asset (upper) -> (free_units, epoch_seconds). Populated by
        # _ensure_capital_reservation on first ensure or when stale (60s).
        self._exchange_balance_cache: dict[str, tuple[float, float]] = {}
        # BotManager back-reference (set externally via
        # set_bot_manager). Used only for cross-bot registry
        # coordination now; multi-base sibling attribution is retired
        # (v3.23.43 — operator directive 2026-07-27).
        self._bot_manager = None
        self._boost_fold_q: float = 0.0
        self._boost_fold_ref: float = 0.0
        self._boost_fold_sma: float = 0.0
        self._boost_scrums: int = 0
        self._boost_folds: int = 0

        # Session 26 P1b ship — Smart Wire target-side receiver state.
        # Operator spec (2026-04-24): "Smart Wire feeds passively increase
        # Fold Queue of target bots and are distributed evenly across any
        # existing tranches OR wait for a new tranche to form before
        # combining with it." The pending bucket implements the
        # wait-then-combine case; the even-distribution case is handled
        # directly in apply_wire_income.
        self._pending_wire_credits: float = 0.0
        self._pending_wire_ledger: list[dict] = []

        # v3.15.69 — wire-income stacking pending buy USD. When non-zero,
        # the next tick fires an aggressive market rebalance to acquire
        # the asset. apply_wire_income sets this when at-center + at-entry.
        self._pending_stack_buy_usd: float = 0.0

        # v3.23.7 R-CLN: the v3.15.49 BB-cycle re-arm gate (the bool
        # plus its companion last-bb-pos scalar) was retired in
        # v3.16.56 but the fields were kept "for backward-compat".
        # They are now fully removed — design Section 3.A. The
        # Growth Rate Cap mechanic below is the sole rate-limit; the
        # D2-b asymmetric BB-extreme cycle-reset (operator pin
        # 2026-06-13) provides the side-aware reset semantics.
        # Persisted older fields are silently ignored on import.

        # v3.23.7 D2-b — Asymmetric BB-extreme cycle-reset side tracker
        # (operator pin 2026-06-13). Records which BB band the last
        # target-growth fired against: "lower" → fold-growth (bot bought
        # below target → opposite extreme is upper, bb_pos >= 0.75
        # resets); "upper" → reserved for future scrum-side growth path;
        # None → no growth yet this cycle, no asymmetric reset armed.
        # The "any extreme touch" rule that briefly shipped in the v3.23.7
        # design (before operator D2-b pin) was symmetric — that would
        # have reset the cycle on the SAME side the bot just fired,
        # double-firing fold growth in tight-range markets. D2-b restores
        # the asymmetric semantic per the original v3.15.49 spec.
        self._target_grow_last_side: Optional[str] = None  # "lower" | "upper" | None

        # v3.16.56 — Per-cycle Growth Rate Cap consumed tracker. Operator
        # directive 2026-05-13: the Growth Rate Cap is the ONLY mechanic
        # that stops burst-fire. Each cycle has a budget of
        # anchor × max_target_growth_pct/100. Per-fold drain decrements
        # this; when consumed >= cap, no further target growth until
        # cap resets. Cap resets on EITHER:
        #   (A) SCRUM fires (Target Delta swings positive, sell event)
        #   (B) D2-b asymmetric BB-extreme touch (bb_pos >= 0.75 when
        #       last growth fired lower-side, or bb_pos <= 0.25 when
        #       last growth fired upper-side)
        # Whichever fires first resets cap to 0.
        self._fold_cycle_cap_consumed: float = 0.0

        # How many ladder rows the LAST growth preview could not order.
        # Written by `_preview_fold_growth`, read by its one caller to
        # tell the operator the sizing answer came from fewer tranches
        # than he has queued. Diagnostic only: nothing sizes off it.
        self._fold_preview_unreadable_refs: int = 0

        # How many ladder rows the LAST growth preview could not SIZE.
        # The twin of the counter above, one field over: `ref` decides
        # the ORDER a row discharges in, `units` decides HOW MUCH it
        # discharges, and both are restored from bot state, so both can
        # arrive non-finite. Written by `_preview_fold_growth`, read by
        # the same caller. Diagnostic only: nothing sizes off it.
        self._fold_preview_unreadable_units: int = 0

        # v3.16.58 — Below-min-cost throttle state. Operator-discovered
        # bug 2026-05-14: ORCA bot retried the same $0.33 SCRUM every
        # ~62s for 25+ hours (5,558 PRE-FLIGHT REJECTED log entries)
        # because Target Delta was below the $1.00 Coinbase min_cost
        # threshold. Pre-flight guard correctly refused the API call,
        # but the bot kept re-issuing the same tick decision every tick,
        # flooding the log with the same error.
        #
        # v3.16.58 fix: pre-decision check at the SCRUM and FOLD branches
        # — if (sell_amount × price) < min_cost (or buy cost < min_cost),
        # skip the trade attempt entirely. Throttled log emits once per
        # 5 minutes per side so the operator gets a heartbeat that the
        # bot is intentionally idle (delta below tradeable threshold),
        # not crashed.
        self._below_min_scrum_log_ts: float = 0.0
        self._below_min_fold_log_ts: float = 0.0

        # v3.15.58 — Circuit Breakers (operator directive 2026-04-25).
        # Soft: time-delay interrupt of trades on the move's side.
        # Hard: bot pause requiring operator reset.
        self._cb_hard_tripped: bool = False
        self._cb_hard_tripped_at: float = 0.0
        self._cb_hard_trip_pct: float = 0.0
        self._cb_soft_active_side: Optional[str] = None  # "scrum" | "fold" | None
        self._cb_soft_cooldown_remaining: int = 0
        self._cb_soft_tripped_at: float = 0.0
        self._cb_soft_trip_pct: float = 0.0
        # Avoid double-evaluation of the same candle.
        self._cb_last_candle_ts: float = 0.0

    def set_smart_wire(self, manager) -> None:
        """Attach a Smart Wire manager for cross-compounding."""
        self._smart_wire_mgr = manager

    def get_swos_inputs(self) -> Optional[dict]:
        """v3.23.65 — return the input dict for
        ``smart_wire.compute_safe_outflow_pct``. Best-effort; returns
        ``None`` when critical fields are missing (bot not yet
        bootstrapped) so the caller can fall back to raw operator
        pct without applying safety math.

        Band approximations for the v3.23.65 first-cut integration:
          band_upper ≈ current_price × (1 + scrumming_interval_pct/100)
          band_lower ≈ current_price × (1 - scrumming_interval_pct/100)
          next_fold_ammo_usd ≈ target_balance × scrumming_interval_pct/100

        Refined band accessors that read the actual per-position
        fold/scrum thresholds are queued for a follow-up cascade;
        this heuristic is close enough for the initial live run.
        """
        try:
            _price = float(getattr(
                self.stats, "current_price", 0.0) or 0.0)
            _target = float(getattr(
                self, "_target_balance", 0.0) or 0.0)
            _interval = float(getattr(
                self.config, "scrumming_interval_pct", 1.0) or 1.0)
            _growth = float(getattr(
                self.config, "max_target_growth_pct", 0.0) or 0.0)
            _cash = float(getattr(
                self.stats, "cash_balance_usd", 0.0) or 0.0)
            _retained = float(getattr(
                self, "_retained_this_cycle_usd", 0.0) or 0.0)
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
        except Exception as _swos_exc:  # noqa: BLE001 - best-effort accessor
            logger.debug(
                "Bot %s get_swos_inputs raised: %s",
                self.bot_id, _swos_exc)
            return None

    def note_scrum_retention_usd(self, retained_usd: float) -> None:
        """v3.23.65 — increment the per-cycle retained counter used
        by SWOS. Called by the scrum-fill sites right beside the
        existing ``stats.total_scrummed_usd += fill_usd`` line."""
        try:
            self._retained_this_cycle_usd += max(0.0, float(retained_usd))
        except Exception as _sup:  # noqa: BLE001 - best-effort
            logger.debug("suppressed in %s: %s: %s", "note_scrum_retention_usd", type(_sup).__name__, _sup)

    def reset_swos_cycle(self) -> None:
        """v3.23.65 — reset the retained-this-cycle counter to 0.
        Called at Fold execution — one Fold closes one cycle."""
        self._retained_this_cycle_usd = 0.0

    def set_market_pairs_scout(self, scout) -> None:
        """v3.23.47 — attach the process-wide MarketPairsScout.

        Read-only awareness: the scout tells the bot what other pairs
        trade this bot's target asset on this exchange, and where
        those pairs are moving (24h % change, last, spread, volume).
        The bot itself does NOT route trades through those pairs in
        this cascade — that decision is deferred to a possible
        v3.23.49 smart-routing cascade pending live divergence data.
        See docs/audits/2026-07-28_multibase_coordination_and_cross_pair_intelligence_plan.md
        §§ 6, 8.5.6.

        Silently no-ops if ``scout`` is falsy — this keeps unit tests
        and headless simulators simple; the bot behaves identically
        with or without an attached scout.
        """
        self._market_pairs_scout = scout

    def get_target_asset_pairs(self):
        """v3.23.47 — return the current PairSnapshots for the bot's
        target asset on this bot's exchange, from the attached scout.

        Returns an empty list when no scout is attached, when the
        scout has not yet polled, or when the target asset trades no
        recognised pairs on the exchange. Never raises.
        """
        _scout = getattr(self, "_market_pairs_scout", None)
        if _scout is None:
            return []
        try:
            _asset = str(getattr(
                self.config, "target_asset", "") or "").upper()
            _eid = str(getattr(
                self.config, "exchange_id", "") or "")
            if not _asset:
                return []
            return _scout.pairs_for(
                _asset, exchange_id=(_eid or None))
        except Exception as _pairs_exc:  # noqa: BLE001 - scout query best-effort
            logger.debug(
                "Bot %s scout query raised: %s",
                self.bot_id, _pairs_exc)
            return []

    # ── v3.23.42 — Capital reservation lifecycle (F62 + F65) ─────────

    def _compute_reservation_qty(self, current_price: float) -> float:
        """Target-asset units this bot should claim in the registry.

        Formula: ``target_balance_USD / (current_price × quote_to_usd)``
        (with a 10 % safety margin so tick-to-tick price drift doesn't
        leave us under-reserved) plus ``personal_hold_qty``
        (operator-declared units this bot keeps out of both its own
        math AND other bots' reach).

        v3.23.46: previously divided by ``current_price`` alone, which
        was wrong for non-USD-quoted pairs (e.g., ETH/BTC where
        current_price is BTC-per-ETH, not USD-per-ETH). Multiplying by
        ``_quote_to_usd`` (already maintained by ``_refresh_quote_to_usd``,
        1.0 for USD/USDC quoted pairs) gives USD-per-target-asset —
        the correct denominator for a USD-denominated target balance.
        Without this fix, an ETH/BTC bot with $200 target reserved
        ``200 / 0.06 = 3,333 ETH`` instead of ``200 / 3000 = 0.067 ETH``.
        """
        if current_price <= 0:
            return 0.0
        try:
            _target = float(self._target_balance or 0)
        except (TypeError, ValueError):
            _target = 0.0
        try:
            _hold = float(
                getattr(self.config, "personal_hold_qty", 0.0) or 0.0)
        except (TypeError, ValueError):
            _hold = 0.0
        _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
        if _qrate <= 0:
            _qrate = 1.0
        _usd_per_asset = current_price * _qrate
        if _usd_per_asset <= 0:
            return 0.0
        _base_units = (
            (_target / _usd_per_asset) if _target > 0 else 0.0)
        return _base_units * 1.10 + max(0.0, _hold)

    async def _get_cached_exchange_balance(
            self, asset: str, max_age_s: float = 60.0
    ) -> Optional[float]:
        """Return this bot's exchange free-balance for ``asset``.

        v3.23.46: cached with ``max_age_s`` TTL (default 60 s) so the
        CRR ensure path doesn't fire an ``exchange.get_balance`` call
        every tick. Returns None on fetch failure (caller should not
        pass ``total_holdings`` to the registry on None, to avoid
        blocking a legitimate reserve on transient exchange errors).
        """
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
        except Exception as _bal_exc:  # noqa: BLE001 - balance fetch best-effort
            logger.debug(
                "Bot %s balance fetch for %s (CRR ensure) raised %s — "
                "skipping over-commit check this cycle.",
                self.bot_id, _asset, _bal_exc)
            return None

    def _crr(self):
        """The capital-reservation registry this bot should use.

        Injected instance when one was supplied (sim fleets get a
        private, non-persisting registry); the process-wide singleton
        otherwise. None only if the module cannot be imported.
        """
        if self._capital_registry is not None:
            return self._capital_registry
        # v3.24.54 (C15 step 4) — STRUCTURAL BACKSTOP.
        #
        # The process-wide registry autosaves to
        # ~/.acervator/reservation_state.json, which is LIVE capital
        # state. A sim bot must never reach it. v3.24.31 gave sim fleets
        # a private registry and v3.24.35 (CV1) made the factory raise
        # rather than return None, but both protect only the callers
        # that ASK for one. A sim bot constructed by any other path
        # arrived here with `_capital_registry is None` and was handed
        # the live singleton.
        #
        # The recorded cost of that path: 16,558 bot_ids against 35 real
        # ones, 16,523 orphans, 6.5 MB of sim residue feeding live
        # allocation decisions.
        #
        # Returning None is the fail-closed answer: reservation is
        # refused rather than silently performed against live state.
        # Callers already handle None (`_crr()` is documented as
        # returning None when the module cannot be imported).
        if getattr(self, "_sim_mode", False):
            logger.warning(
                "Bot %s is in sim mode with no injected capital registry; "
                "refusing to resolve the process-wide registry, which "
                "persists to the operator's reservation_state.json. "
                "Reservation is unavailable for this bot.", self.bot_id)
            return None
        try:
            from .capital_reservation import (
                get_registry as _crr_get_registry)
            return _crr_get_registry()
        except ImportError as exc:
            logger.debug("capital registry unavailable: %s", exc)
            return None

    async def _ensure_capital_reservation(
            self, current_price: float) -> None:
        """Idempotent: reserve on first eligible call, update on
        subsequent calls, always heartbeat.

        No-ops when self_reserve_capital is disabled or price is
        unavailable. Failures log at WARNING and set the token to
        None so the next tick can retry. Never raises into the tick
        path.

        v3.23.46: async so it can consult the balance cache and pass
        ``total_holdings`` to ``reserve()`` / ``update()`` — required
        for the registry's over-commit check to fire. Prior versions
        omitted the argument entirely, silently disabling the check
        (see docs/audits/2026-07-28_multibase_coordination_and_cross_pair_intelligence_plan.md § 2.1).
        """
        # v3.24.14 — sim bots must NOT touch the capital-reservation
        # registry. get_registry() is a process-wide singleton that
        # PERSISTS to ~/.acervator/reservation_state.json, so every
        # Fleet Replay was writing reservations into the operator's
        # live capital state.
        #
        # Measured 2026-08-03: 16,558 bot_ids in that file against 35
        # real ones — 16,523 orphans, 6.5 MB of accumulated sim
        # residue. It also produced a flood of "over-commit ... >
        # total holdings 0" warnings during replay, because sim bots
        # hold nothing on the live exchange.
        #
        # Same defect class as the v3.24.12 event-bus leak, but worse:
        # that one was in-memory per-process, this one survives on
        # disk and feeds live allocation decisions.
        # v3.24.31 — the `if _sim_mode: return` that used to sit here
        # is GONE. Sim bots now reserve against their own injected
        # registry (see _crr()), so this code path is EXERCISED rather
        # than skipped. Isolation comes from WHICH registry the bot
        # holds, not from refusing to run — the operator's directive is
        # that sim bots carry the same functionality in a simulated
        # environment, and skipping removes the feature instead.
        if not bool(getattr(
                self.config, "self_reserve_capital", True)):
            return
        if current_price is None or current_price <= 0:
            return
        _asset = str(getattr(
            self.config, "target_asset", "") or "").upper()
        if not _asset:
            return
        _qty = self._compute_reservation_qty(current_price)
        if _qty <= 0:
            return
        _total_holdings = await self._get_cached_exchange_balance(_asset)

        # v3.24.93 - CAP THE CLAIM AT WHAT IS ACTUALLY HELD.
        #
        # `_compute_reservation_qty` returns `base_units * 1.10`. The
        # 10% is drift headroom so a live bot is not left UNDER-reserved
        # between ticks. But a bot at its target holds ~100% of
        # target-worth, so the claim is ~110% of its own inventory, the
        # over-commit guard refuses it, and the failure repeats on every
        # tick for the life of the process.
        #
        # MEASURED in the operator's live log, 2026-08-08: nearly every
        # bot in the 37-bot fleet, once per tick. XRP is the arithmetic
        # in plain sight -- "existing reservations 0 + requested
        # 80.3863967 > total holdings 74": 80.3863967 / 1.10 = 73.08
        # base units against 74 held. LINK, ORCA, ALLO, BONK, CHIP,
        # GROVE, ONDO, WLFI, KAT, SUI, RAVE, PENGU, TAO, BILL, HYPE,
        # BIO, ADA, XLM, NEAR, AGLD, CAP, VVV, LTC and BTC all the same.
        #
        # Headroom above a ceiling is not headroom, it is a request the
        # registry must refuse. The margin still applies BELOW the
        # ceiling, which is where it does its job -- a bot part-way into
        # its position still over-claims slightly against drift.
        #
        # Not applied when holdings are unknown (`None`): a transient
        # balance-fetch failure must not silently shrink a live
        # reservation, and the registry is not given a ceiling to check
        # against in that case either.
        if _total_holdings is not None and _qty > _total_holdings > 0:
            _qty = float(_total_holdings)
        # v3.24.63 (C16 / SN-5) — sim does not assert holdings on the
        # FIRST reserve.
        #
        # `_compute_reservation_qty` claims target/(price x qrate) with a
        # 10% safety margin so tick-to-tick drift cannot leave a LIVE bot
        # under-reserved. Sim inventory is seeded at exactly
        # target/open_px, so the claim is ~110% of what the sim bot
        # holds, `reserve()` sees qty > total_holdings, raises on
        # over-commit, and the reservation fails for every bot on every
        # tick. The "SELL REFUSED (capital reservation)" branch was
        # therefore UNREACHABLE in sim — a gate that can never fire is a
        # gate the simulator cannot tell you anything about.
        #
        # The over-commit check exists to stop bots sharing ONE live
        # exchange balance from collectively over-claiming it. A sim
        # fleet holds a private, non-persisting registry (C15) and no
        # live inventory, so here the check is measuring the wrong
        # thing. The docstring on `_get_cached_exchange_balance` already
        # blesses passing None rather than blocking a legitimate
        # reserve.
        #
        # DO NOT "FIX" THIS BY SEEDING SIM HOLDINGS AT THE CEILING. The
        # 1.10 is over-commit headroom, not an inventory target; seeding
        # there gives every sim bot 110% of a live bot's base units, sim
        # out-scrums live, and the inflation reads as the fix working.
        # Only the FIRST reserve skips the assertion — subsequent
        # updates still pass holdings, so drift is still caught.
        if getattr(self, "_sim_mode", False) and self._crr_token is None:
            _total_holdings = None
        try:
            _crr_reg = self._crr()
            if _crr_reg is None:
                return
            if self._crr_token is None:
                _reason = (
                    f"Scrumming target — "
                    f"target_balance=${self._target_balance:.2f}, "
                    f"personal_hold={float(getattr(self.config, 'personal_hold_qty', 0.0)):.10g}, "
                    f"at_price=${current_price:.8f}")
                self._crr_token = _crr_reg.reserve(
                    bot_id=self.bot_id,
                    asset=_asset,
                    qty=_qty,
                    reason=_reason,
                    bot_kind="scrumming",
                    total_holdings=_total_holdings,
                )
                self._crr_last_reserved_qty = _qty
                logger.info(
                    "Bot %s reserved %.10g %s with "
                    "CapitalReservationRegistry (token %s, "
                    "total_holdings=%s)",
                    self.bot_id, _qty, _asset,
                    self._crr_token[:8] if self._crr_token else "?",
                    (f"{_total_holdings:.10g}"
                     if _total_holdings is not None else "unavailable"))
            else:
                # Only push an update when qty drift > 1 %.
                if self._crr_last_reserved_qty > 0:
                    _drift = abs(
                        _qty - self._crr_last_reserved_qty
                    ) / self._crr_last_reserved_qty
                else:
                    _drift = 1.0
                if _drift > 0.01:
                    _crr_reg.update(
                        self._crr_token, self.bot_id, _qty,
                        total_holdings=_total_holdings)
                    self._crr_last_reserved_qty = _qty
            _crr_reg.heartbeat(self.bot_id)
        except Exception as _crr_exc:  # noqa: BLE001 - registry best-effort
            logger.warning(
                "Bot %s capital-reservation ensure raised %s: %s — "
                "continuing tick; will retry next call.",
                self.bot_id, type(_crr_exc).__name__, _crr_exc)
            # v3.24.93 - RELEASE BEFORE FORGETTING.
            #
            # This dropped the token and left the RESERVATION standing.
            # The registry then held units under a token nobody owned,
            # and the next ensure -- seeing `_crr_token is None` --
            # called `reserve()` afresh, whose over-commit check counts
            # every reservation on the asset INCLUDING the orphan. So
            # one failure produced a permanent one: existing >= holdings
            # forever, refused every tick, and each refusal re-entered
            # this branch.
            #
            # That is the second signature in the operator's log, the
            # one where `existing` is non-zero: "over-commit on LINK -
            # existing reservations 30.02068843 + requested
            # 9.984649731". Nothing held 30 LINK under a live token;
            # 30.02 was abandoned.
            #
            # Releasing first makes the retry a real retry instead of a
            # collision with this bot's own ghost.
            _stale = self._crr_token
            if _stale is not None:
                try:
                    _reg = self._crr()
                    if _reg is not None:
                        _reg.release(_stale, self.bot_id)
                        logger.info(
                            "Bot %s released stale reservation %s after "
                            "a failed ensure", self.bot_id, _stale[:8])
                except Exception as _rel_exc:  # noqa: BLE001
                    logger.warning(
                        "Bot %s could not release stale reservation "
                        "%s: %s", self.bot_id, _stale[:8], _rel_exc)
            self._crr_token = None
            self._crr_last_reserved_qty = 0.0
            try:
                from src.core.signal_contract import emit as _cr_emit
                _cr_emit(
                    "bot.01.001.postcondition.capital_reservation",
                    actual=0.0,
                    expected=round(float(_qty), 10),
                    every=30.0,
                    context={
                        "bot_id": str(self.bot_id),
                        "asset": _asset,
                        "holdings": (round(float(_total_holdings), 10)
                                     if _total_holdings is not None
                                     else None),
                        "error": f"{type(_crr_exc).__name__}: {_crr_exc}"[:180],
                        "released_stale": bool(_stale),
                    })
            except Exception as _sup:  # noqa: BLE001,S110 - advisory
                logger.debug("suppressed in %s: %s: %s", "_ensure_capital_reservation", type(_sup).__name__, _sup)
        else:
            # v3.24.93 - the success path reports too, so a green run is
            # evidence rather than silence. Throttled: this runs on
            # every tick of every bot.
            #
            # v3.25.x (issue #21) - IT COMPARED THE REQUEST WITH ITSELF.
            #
            # `actual` and `expected` were both
            # `round(float(_qty), 10)`. `ok` therefore derived True on
            # every call of every bot for the whole life of the pin, and
            # a green record from it was evidence of nothing.
            #
            # THE TWO HALVES ARE DIFFERENT STATE AND THEY DIVERGE FOR A
            # STATED REASON. `_qty` is what THIS tick computed as
            # needed. `self._crr_last_reserved_qty` is the quantity the
            # registry was last told to hold - it is written where a
            # reservation lands and where an update lands, and nowhere
            # else. The update path above pushes only when the drift
            # exceeds 1 %, so the held quantity is allowed to sit
            # anywhere inside that band and nowhere outside it.
            #
            # THE BAND IS READ FROM THAT UPDATE PATH, NOT CHOSEN HERE.
            # `ok` is False exactly when the held reservation has left
            # the band that path is supposed to keep it inside - an
            # update that did not land, or a mirror that stopped
            # agreeing with the registry. That is the postcondition this
            # pin was written to carry and could not carry before.
            #
            # JUDGED ON THE ROUNDED PAIR THE RECORD ITSELF CARRIES, so a
            # reader of the JSONL can recompute the verdict from
            # `actual` and `expected` alone rather than take it on
            # trust. The round is 1e-10 against a band of 1 % of the
            # quantity, so it cannot change a verdict for any
            # reservation above about 1e-8 units, and it cannot
            # manufacture an agreement that is not there.
            #
            # A HELD QUANTITY OF ZERO OR LESS IS NOT A PASS. There is no
            # reservation for a band to be measured against, and no
            # divisor to measure one with. The update path above already
            # reads that state this way - it sets `_drift = 1.0`, "out
            # of band, push an update" - so False here is the reading
            # that path already encodes. True would put back the
            # unconditional green this repair exists to remove.
            #
            # `ok` IS PASSED EXPLICITLY. `emit` derives it by equality
            # when it is not, and these two numbers are legitimately
            # unequal on every tick that sits inside the band.
            try:
                from src.core.signal_contract import emit as _cr_ok
                _held = round(float(self._crr_last_reserved_qty), 10)
                _need = round(float(_qty), 10)
                _cr_ok(
                    "bot.01.002.postcondition.capital_reservation",
                    actual=_held,
                    expected=_need,
                    ok=bool(_held > 0.0
                            and abs(_need - _held) / _held <= 0.01),
                    every=60.0,
                    context={
                        "bot_id": str(self.bot_id),
                        "asset": _asset,
                        "holdings": (round(float(_total_holdings), 10)
                                     if _total_holdings is not None
                                     else None),
                        "capped": bool(
                            _total_holdings is not None
                            and abs(_qty - float(_total_holdings)) < 1e-12),
                    })
            except Exception as _sup:  # noqa: BLE001,S110 - advisory
                logger.debug("suppressed in %s: %s: %s", "_ensure_capital_reservation", type(_sup).__name__, _sup)

    def _release_capital_reservation(self) -> None:
        """Release the registry token in stop() / destroy paths.
        Non-raising; the registry's own heartbeat-staleness prune is
        the backstop if this call fails."""
        if self._crr_token is None:
            return
        try:
            _crr_reg = self._crr()
            if _crr_reg is None:
                return
            _crr_reg.release(self._crr_token, self.bot_id)
            logger.info(
                "Bot %s released capital reservation %s on stop()",
                self.bot_id,
                self._crr_token[:8] if self._crr_token else "?")
            self._crr_token = None
            self._crr_last_reserved_qty = 0.0
        except Exception as _crr_exc:  # noqa: BLE001 - release best-effort
            logger.warning(
                "Bot %s capital reservation release at stop raised "
                "%s: %s — leaving for heartbeat-staleness prune.",
                self.bot_id, type(_crr_exc).__name__, _crr_exc)

    def set_bot_manager(self, manager) -> None:
        """Attach the BotManager for cross-bot registry coordination.

        v3.23.43 — Scrumming bots always treat ``_main_lots`` as the
        authoritative source of holdings; the raw exchange balance is
        never adopted as this bot's own view. Cross-bot capital
        protection is handled via ``CapitalReservationRegistry``,
        not by attribution.
        """
        self._bot_manager = manager

    def set_target_balance_live(self, new_target: float) -> dict:
        """Apply an operator-initiated Target Balance change mid-session.

        Session 26 (2026-04-24) operator-reported bug:
            "Modifying the Target Balance while the bot is running is
             causing a Target Delta calculation and corresponding bot
             response issue where I cannot acquire the increased amount
             with Manual Fire nor will the bot auto scrum the increased
             amount."

        Root cause: `bot_live_settings.py::_apply_changes` set
        `bot.config.target_balance` via setattr but did NOT update the
        runtime attributes `_target_balance` (consumed by tick) or
        `_anchor_target_balance` (consumed by MEM-251/253/257 ceiling
        guards). Config value changed; runtime stayed frozen at the old
        value, so tick + guards operated on a stale target.

        This method is the correct entry point for operator-initiated
        target changes. Updates BOTH `_target_balance` and
        `_anchor_target_balance` because an explicit operator raise
        re-sets the set-point for ceiling purposes — the anchor's job
        is to freeze the set-point against INTERNAL drift (profit-fold
        growth, Smart Wire routing) but NOT against EXPLICIT operator
        intent. Config is also updated so persistence + re-reads see
        the new value.

        Returns a dict:
            {
                "applied": True/False,
                "old_target": float,
                "old_anchor": float,
                "new_target": float,
                "new_anchor": float,
                "delta_usd": float    # new_target - position_value
            }

        sadp: R1 R17 R28 R46
        """
        try:
            nt = float(new_target)
        except (TypeError, ValueError):
            # v3.15.91 (F3 fix): operator-visible emit on validation
            # failure. Pre-fix Live Settings GUI consumed `applied`
            # but if the operator typed garbage and the dialog
            # auto-closed, the refusal left no log trail.
            try:
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id,
                    message=(f"TARGET BALANCE CHANGE REFUSED: invalid "
                             f"value {new_target!r} — could not coerce "
                             f"to float. Target unchanged at "
                             f"${self._target_balance:.2f}."))
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "set_target_balance_live", type(_sup).__name__, _sup)
            return {"applied": False, "reason": f"invalid value: {new_target!r}"}
        if nt <= 0:
            try:
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id,
                    message=(f"TARGET BALANCE CHANGE REFUSED: must be "
                             f"> 0, got {nt}. Target unchanged at "
                             f"${self._target_balance:.2f}."))
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "set_target_balance_live", type(_sup).__name__, _sup)
            return {"applied": False,
                    "reason": f"target must be > 0, got {nt}"}

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
        # New behaviour:
        #   * new > current_target → interpret as top-up.
        #       anchor := new_target (fresh capital base)
        #       target := new_target + (current_target − current_anchor)
        #                                            (preserved growth)
        #     e.g. anchor=200 target=205 (5 accrued) + new=250 →
        #          anchor=250 target=255. Operator's $50 top-up
        #          preserved on top of $5 accrued.
        #   * new < current_target → interpret as explicit lower / withdrawal.
        #       anchor := new_target
        #       target := new_target
        #     Accrued growth cleared (can't accrue above a lower base).
        #   * new == current_target → no-op path (mark_changed diff should
        #     already skip; guarded here too for robustness).
        accrued = max(0.0, old_t - old_a)   # non-negative growth so far
        if nt > old_t and accrued > 1e-9:
            # Top-up path — preserve the accrued growth on top of the
            # new anchor.
            self._anchor_target_balance = nt
            self._target_balance = nt + accrued
        else:
            # Lower / equal / zero-accrued top-up — old behaviour
            # (both in lockstep). Zero-accrued top-up == old behaviour
            # by definition since accrued=0.
            self._target_balance = nt
            self._anchor_target_balance = nt
        try:
            # config.target_balance always reflects the operator's INPUT
            # value (anchor) — GUI + persistence show what the operator
            # set, not the accrued-growth-included target.
            self.config.target_balance = nt
        except Exception as _sup:  # R28-OK: config may be a plain struct
            logger.debug("suppressed in %s: %s: %s",
                         "_set_target_balance", type(_sup).__name__, _sup)

        try:
            _px = float(getattr(self.stats, "current_price", 0) or 0)
        except Exception:  # R28-OK: price probe; 0 disables pos_val math
            _px = 0.0
        pos_val = float(self._current_holdings) * _px if _px > 0 else 0.0
        # v3.23.30 — actual post-set values (may differ from nt when
        # top-up preserved accrued growth)
        new_t = float(self._target_balance)
        new_a = float(self._anchor_target_balance)
        delta = new_t - pos_val

        # v3.23.30 — surface top-up-preserved growth in the log so
        # operator can see the mechanic worked.
        preserved_note = ""
        if new_t != nt:   # only true on the top-up-preserve branch
            preserved_note = (f" [top-up preserved ${new_t - new_a:.4f} "
                              f"accrued growth: target=${new_t:.4f}]")

        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"TARGET BALANCE LIVE UPDATE: ${old_t:.2f} -> "
                     f"${new_t:.2f} (anchor ${old_a:.2f} -> "
                     f"${new_a:.2f}). Position ${pos_val:.2f} -> "
                     f"delta ${delta:+.2f}.{preserved_note} "
                     f"Ceiling guards recompute on next tick."))
        logger.info(
            "Bot %s target_balance live-update: target %.2f -> %.2f, "
            "anchor %.2f -> %.2f",
            self.bot_id, old_t, new_t, old_a, new_a)

        return {
            "applied": True,
            "old_target": old_t,
            "old_anchor": old_a,
            "new_target": new_t,
            "new_anchor": new_a,
            "delta_usd": delta,
            "preserved_growth": max(0.0, new_t - new_a),
        }

    def _apply_fold_target_growth(self, accum_profit: float,
                                  source: str) -> float:
        """Drain fold surplus into `_target_balance`, bounded by the
        per-cycle Growth Rate Cap. Returns `_growth_applied` (USD).

        v3.23.30 — extracted from the autonomous FOLD-back path (was
        inline at ~line 7549) so MANUAL_FOLD and CARTRIDGE_FOLD paths
        can share the same drain logic. Per operator directive
        2026-07-26 (Option B): every fold-shape event that reduces a
        tranche back to cash-equivalent should contribute to target
        growth, not just the autonomous FOLD path.

        Formula (v3.23.7 realignment):
          surplus_usd = max(0, accum_profit * quote_to_usd)
          cycle_cap = anchor * (max_target_growth_pct/100)
          cap_remaining = max(0, cycle_cap - fold_cycle_cap_consumed)
          growth_applied = min(surplus_usd, cap_remaining)
          _target_balance += growth_applied
          _fold_cycle_cap_consumed += growth_applied
          leftover surplus accrues to _standing_surplus_usd

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
            # v3.23.66 — distinctive diagnostic so the operator can
            # tell WHY a fold didn't grow the target. Grep for
            # "[COMPOUND SKIPPED]" in the log to spot fold events
            # that had no compounding effect.
            try:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"[COMPOUND SKIPPED] ({source}): "
                             f"profit_folding_active=False — the "
                             f"compound-growth feature is off for "
                             f"this bot. No target bump."))
            except Exception as _sup:  # noqa: BLE001 - diagnostic best-effort
                logger.debug("suppressed in %s: %s: %s", "_apply_fold_target_growth", type(_sup).__name__, _sup)
            return 0.0
        _quote = float(self._quote_to_usd or 1.0)
        _new_surplus_usd = max(0.0, float(accum_profit) * _quote)
        # v3.24.51 (Phase 2 Step 7) — a break-even fold must still drain
        # the standing pool. This returned on zero surplus alone, before
        # reaching the drain, so parked money could only ever be released
        # by a PROFITABLE fold. The message immediately below says a
        # break-even fold is EXPECTED ("when a fold buys back at cost
        # basis or when scrum->fold spread is eaten by fees"), which is
        # the common case — so the pool's only outlet was the rare case.
        # Skip only when there is nothing new AND nothing parked.
        if (_new_surplus_usd <= 1e-9
                and float(getattr(self, "_standing_surplus_usd", 0.0)
                          or 0.0) <= 1e-9):
            # v3.23.66 diagnostic: fold produced no net profit.
            try:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"[COMPOUND SKIPPED] ({source}): "
                             f"accum_profit ${float(accum_profit):.4f} × "
                             f"quote {_quote:.4f} = ${_new_surplus_usd:.4f} "
                             f"— fold produced no surplus, and no standing "
                             f"surplus is parked. No target bump. "
                             f"(This is expected when a fold buys back at "
                             f"cost basis or when scrum→fold spread is "
                             f"eaten by fees.)"))
            except Exception as _sup:  # noqa: BLE001 - diagnostic best-effort
                logger.debug("suppressed in %s: %s: %s", "_apply_fold_target_growth", type(_sup).__name__, _sup)
            return 0.0
        _cap_pct = float(getattr(self.config, "max_target_growth_pct", 1.0))
        _cycle_cap_growth = self._anchor_target_balance * (_cap_pct / 100.0)
        _cap_remaining = max(
            0.0,
            _cycle_cap_growth - self._fold_cycle_cap_consumed)
        if _cap_remaining <= 1e-9:
            # Cap consumed for this cycle; surplus accrues to standing pool.
            self._standing_surplus_usd += _new_surplus_usd
            try:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"TARGET-GROW HELD ({source}): surplus "
                             f"${_new_surplus_usd:.4f} accrues to standing "
                             f"pool (now ${self._standing_surplus_usd:.4f}). "
                             f"Cap ${_cycle_cap_growth:.4f} fully consumed "
                             f"this cycle."))
            except Exception as _sup:  # R28-OK: diagnostic-only
                logger.debug("suppressed in %s: %s: %s", "_apply_fold_target_growth", type(_sup).__name__, _sup)
            try:
                self.stats.standing_surplus_usd = self._standing_surplus_usd
            except Exception as _sup:  # R28-OK: telemetry mirror
                logger.debug("suppressed in %s: %s: %s", "_apply_fold_target_growth", type(_sup).__name__, _sup)
            return 0.0
        # v3.24.51 (Phase 2 Step 7) — the drain the spec at :488-494 has
        # always described and the code never implemented.
        #
        # It was `min(_new_surplus_usd, _cap_remaining)`: only THIS
        # fold's surplus was eligible for growth, and anything over the
        # cap was added to `_standing_surplus_usd` below. So the pool
        # took deposits and had no withdrawal — `_standing_surplus_usd`
        # has no decrement anywhere else in src/ either. Surplus parked
        # once stayed parked, and a later cycle with cap headroom to
        # spare could not reach it.
        #
        # The spec's formula makes the pool an INPUT: this cycle's
        # surplus plus everything previously parked, drawn down to the
        # cap, with the remainder carried. Bounded by the same
        # `_cap_remaining` as before, so no cycle can grow the target by
        # more than it could have yesterday.
        _prior_pool = float(getattr(self, "_standing_surplus_usd", 0.0) or 0.0)
        _available = _new_surplus_usd + _prior_pool
        _growth_applied = min(_available, _cap_remaining)
        self._target_balance = float(self._target_balance) + _growth_applied
        self._fold_cycle_cap_consumed += _growth_applied
        # v3.23.7 D2-b asymmetric cycle-reset — record side for tick-entry.
        self._target_grow_last_side = "lower"
        self._standing_surplus_usd = max(0.0, _available - _growth_applied)
        _drained = max(0.0, _prior_pool - self._standing_surplus_usd)
        _leftover = self._standing_surplus_usd
        self._fold_accumulator += _growth_applied
        try:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                # v3.24.51 — reports the DRAIN, not just this fold's
                # surplus. The old line quoted only _new_surplus_usd and
                # a leftover, which made a growth funded largely from the
                # standing pool look like it came from the fold.
                message=(f"TARGET GROWN ({source}): surplus "
                         f"${_new_surplus_usd:.4f}"
                         + (f" + ${_prior_pool:.4f} standing "
                            f"(${_drained:.4f} drained)"
                            if _prior_pool > 1e-9 else "")
                         + f", applied "
                           f"${_growth_applied:.4f} (cap remaining "
                           f"${_cap_remaining:.4f} of "
                           f"${_cycle_cap_growth:.4f}). New target "
                           f"${self._target_balance:.4f}, cycle consumed "
                           f"${self._fold_cycle_cap_consumed:.4f}. "
                           f"Standing pool now ${_leftover:.4f}."))
        except Exception as _sup:  # R28-OK: diagnostic-only
            logger.debug("suppressed in %s: %s: %s", "_apply_fold_target_growth", type(_sup).__name__, _sup)
        try:
            self.stats.standing_surplus_usd = self._standing_surplus_usd
        except Exception as _sup:  # R28-OK: telemetry mirror
            logger.debug("suppressed in %s: %s: %s", "_apply_fold_target_growth", type(_sup).__name__, _sup)
        return _growth_applied

    def _preview_fold_growth(self, units: float, price: float) -> float:
        """What ``_apply_fold_target_growth`` WOULD add. Moves no money.

        MUTATES NO LEDGER STATE, AND THAT IS THE CLAIM. It does not
        touch the ladder, the target, the cap or the standing pool; the
        sort below runs on a COPY for exactly that reason. It writes
        TWO attributes, ``_fold_preview_unreadable_refs`` and
        ``_fold_preview_unreadable_units``, diagnostic counts its
        caller reads to warn the operator. Nothing sizes off either
        count. The heading used to read "Mutates nothing", which
        stopped being true the moment the first count was added -- a
        docstring that overstates is worse than one that explains, and
        "ONE attribute" stopped being true the moment the second was.

        WHY THIS EXISTS (operator directive 2026-08-07)
        Manual Fire sized its fold buy against the target, then grew the
        target afterwards, so position landed on the OLD target and the
        residual was identically the growth. Operator ruling:

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
        # Same highest-price-first discharge order as the real loop, on
        # a COPY -- previewing must not reorder the live queue.
        #
        # v3.25.x -- THE ROW IS FILTERED BEFORE IT IS ORDERED, AND THAT
        # ORDER IS THE WHOLE POINT.
        #
        # THE RULE IS ONE RULE, AND IT IS NOT NEW HERE. The autonomous
        # rebuy-distance gate states it at :12338: a value sets an
        # ordering or a threshold ONLY IF IT IS A FINITE NUMBER, and the
        # finiteness test runs BEFORE any comparison, never as part of
        # one. That gate tests the threshold it is about to compare
        # (`ref * factor`); this one tests the key it is about to sort
        # by (`ref`). Same rule, each applied to the quantity that site
        # actually orders on.
        #
        # `float(x) or 0.0` DOES NOT CATCH nan, WHICH IS WHY THIS LOOKED
        # SAFE. `nan` is TRUTHY, so the `or` never fires and the key
        # receives nan. Every comparison against nan is False, so
        # `sorted` cannot place it and the result depends on where the
        # nan started. Measured on the code this replaces, one 3-row
        # content {1.0, nan, 0.9} over all six orderings gave FOUR
        # DISTINCT sorted results, one of them (0.9, nan, 1.0) -- not
        # sorted at all.
        #
        # AND THIS METHOD SIZES AN ORDER, which is what makes it worse
        # than the gate's. The return flows through
        # `buy_usd_target = -delta_usd + _growth_preview` (:12507) into
        # `guarded_place_order` (:12596). Measured end to end on the
        # operator's own config (interval 5.0, fee 1.6, growth cap 1.0),
        # ladders differing only in row order placed TWO DIFFERENT
        # AMOUNTS for the same ladder at the same price.
        #
        # SKIP; DO NOT PURGE AND DO NOT REFUSE. The verb is the gate's
        # verb, for a stronger reason: this method is a PREVIEW that
        # mutates no ledger state, so an unreadable row simply sets no
        # discharge order and contributes no surplus. A ladder of only
        # unreadable rows previews the growth an EMPTY ladder previews,
        # which is already this method's answer for a ladder whose refs
        # all sit below `price`.
        #
        # THE COERCION IS DELIBERATELY UNCHANGED. `float(...) or 0.0`
        # still runs, so a None ref still reads 0.0 and a string ref
        # still parses exactly as it did; only the finiteness test is
        # new. Narrowing the coercion to `as_finite_float` here would
        # ALSO drop string and bool refs, changing the amount on ladders
        # that size correctly today -- the one thing this must not do.
        _readable: list[tuple[float, dict]] = []
        _unreadable_refs = 0
        for _t in (self._fold_tranches or []):
            if not isinstance(_t, dict):
                continue
            _t_ref = float(_t.get("ref", 0.0) or 0.0)
            if not math.isfinite(_t_ref):
                _unreadable_refs += 1
                continue
            _readable.append((_t_ref, _t))
        # The key is the ref itself, already proven finite above, so the
        # sort is a total order by construction rather than by hope.
        _readable.sort(key=lambda pair: pair[0], reverse=True)
        # Read by the one caller (:12467) to say out loud that the
        # sizing answer came from fewer tranches than are queued.
        self._fold_preview_unreadable_refs = _unreadable_refs
        _remaining = float(units)
        _accum = 0.0
        _unreadable_units = 0
        for _ref, t in _readable:
            if _remaining <= 1e-12:
                break
            # THE THIRD SITE, AND IT IS THE SAME RULE ONE FIELD OVER.
            # `ref` decides the ORDER a row discharges in and is proven
            # finite above; `units` decides HOW MUCH it discharges and
            # was not. Both are restored from bot state, so both can
            # arrive non-finite, and the rule is the one the two sites
            # above already apply: a value sets an ordering or a
            # threshold ONLY IF IT IS FINITE, tested BEFORE any
            # comparison rather than as part of one.
            #
            # `float(x) or 0.0` DOES NOT CATCH nan -- nan is TRUTHY, so
            # the `or` never fires. Measured on the code this replaces:
            # `min(nan, _remaining)` returns nan, `nan <= 1e-12` is
            # False so the row is NOT skipped, `_accum` becomes nan, and
            # `_remaining -= nan` makes `_remaining <= 1e-12` False for
            # ever so the `break` above is DEAD for the rest of the
            # ladder.
            #
            # WHAT IT ACTUALLY PRODUCED IS WORSE THAN A nan ANSWER, and
            # this is the part worth writing down. `max(0.0, nan)`
            # returns 0.0, because `nan > 0.0` is False -- so the
            # poisoned accumulator does NOT surface as a nan the caller
            # could notice. It surfaces as ZERO GROWTH. Over all
            # permutations of {nan, inf, big, small, zero} at sizes 2-4,
            # 30 of 120 multisets returned two answers, and every one of
            # the 30 contained a nan: $1736.00 when the buy truncated
            # before reaching the nan row, $0.00 when it did not. Zero
            # growth silently reinstates the exact defect this method
            # was written to prevent -- the fold lands short and cannot
            # compound.
            #
            # SKIP; DO NOT PURGE AND DO NOT REFUSE, for the reason the
            # ref filter gives: this method mutates no ledger state, so
            # an unsizable row simply discharges nothing and contributes
            # no surplus, exactly as a ladder shorter by that row would.
            #
            # THE COERCION IS DELIBERATELY UNCHANGED. `float(...) or
            # 0.0` still runs, so a None reads 0.0 and a string parses
            # exactly as it did; only the finiteness test is new.
            # Narrowing to `as_finite_float` would ALSO drop string and
            # bool units, changing the amount on ladders that size
            # correctly today -- the one thing this must not do.
            _t_units = float(t.get("units", 0.0) or 0.0)
            if not math.isfinite(_t_units):
                _unreadable_units += 1
                continue
            # The SAME finite value tested above, reused. Re-reading the
            # field here would let the test and the threshold disagree
            # about one row -- the defect this change exists to end,
            # reintroduced three lines later.
            take = min(_t_units, _remaining)
            if take <= 1e-12:
                continue
            # The SAME finite value the ordering used. Re-reading the
            # field here would let the filter and the threshold disagree
            # about one row -- the defect this change exists to end,
            # reintroduced three lines later.
            if _ref > price:
                _accum += take * (_ref - price)
            _remaining -= take
        # Read by the one caller to say out loud that the sizing answer
        # discharged fewer tranches than it ordered.
        self._fold_preview_unreadable_units = _unreadable_units
        _quote = float(self._quote_to_usd or 1.0)
        _new_surplus_usd = max(0.0, _accum * _quote)
        _cap_pct = float(getattr(self.config, "max_target_growth_pct", 1.0))
        _cycle_cap_growth = self._anchor_target_balance * (_cap_pct / 100.0)
        _cap_remaining = max(
            0.0, _cycle_cap_growth - self._fold_cycle_cap_consumed)
        if _cap_remaining <= 1e-9:
            return 0.0
        _available = _new_surplus_usd + float(
            getattr(self, "_standing_surplus_usd", 0.0) or 0.0)
        return min(_available, _cap_remaining)

    def set_visibility_live(self, new_visibility: str) -> dict:
        """Apply live visibility change (internal ↔ orderbook).

        Runtime gap (Session 26 audit 2026-04-24): __init__ snapshots
        config.visibility into self._invisible (line 111). Changing
        config.visibility via setattr leaves self._invisible stale, so
        the bot continues placing MARKET vs LIMIT orders per the old
        mode. _execute_buy, _execute_sell, and _execute_manual_rebalance
        all branch on self._invisible (lines 1118, 3556, 3567, 3906) —
        all stuck on the old mode until restart.

        Fix: update config + self._invisible in lockstep.
        sadp: R1 R17 R28
        """
        nv = str(new_visibility or "").lower()
        if nv not in ("internal", "orderbook"):
            return {"applied": False,
                    "reason": f"visibility must be 'internal' or "
                              f"'orderbook'; got {new_visibility!r}"}
        old_inv = bool(self._invisible)
        self._invisible = (nv == "internal")
        try:
            self.config.visibility = nv
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "set_visibility_live", type(_sup).__name__, _sup)
        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"VISIBILITY LIVE UPDATE: {'INVISIBLE' if old_inv else 'ORDERBOOK'}"
                     f" -> {'INVISIBLE' if self._invisible else 'ORDERBOOK'}. "
                     f"Next order placement uses the new mode."))
        logger.info("Bot %s visibility live: %s -> %s",
                    self.bot_id, 'internal' if old_inv else 'orderbook', nv)
        return {"applied": True, "old_invisible": old_inv,
                "new_invisible": self._invisible}

    def set_aggressive_live(self, new_aggressive: bool) -> dict:
        """Apply live aggressive-trading toggle.

        Runtime gap: __init__ snapshots config.aggressive_trading into
        self._aggressive (line 112). Config setattr alone leaves
        self._aggressive stale. Log strings at line 1121 and any
        downstream behavior keyed off self._aggressive stay on the old
        value.

        Fix: update config + self._aggressive in lockstep.
        sadp: R17 R28
        """
        nv = bool(new_aggressive)
        old = bool(self._aggressive)
        self._aggressive = nv
        try:
            self.config.aggressive_trading = nv
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "set_aggressive_live", type(_sup).__name__, _sup)
        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"AGGRESSIVE TRADING LIVE UPDATE: {old} -> {nv}."))
        logger.info("Bot %s aggressive_trading live: %s -> %s",
                    self.bot_id, old, nv)
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

        Fix: update config + _hedge_balance_initial in lockstep.
        _hedge_bal stays — it reflects actual drainable reserve.
        sadp: R11 R17 R28
        """
        try:
            nv = float(new_hedge_balance)
        except (TypeError, ValueError):
            return {"applied": False,
                    "reason": f"hedge_balance must be numeric; "
                              f"got {new_hedge_balance!r}"}
        if nv < 0:
            return {"applied": False,
                    "reason": f"hedge_balance must be ≥ 0; got {nv}"}
        old_cap = float(getattr(self, "_hedge_balance_initial", 0.0) or 0.0)
        old_reserve = float(getattr(self, "_hedge_bal", 0.0) or 0.0)
        self._hedge_balance_initial = nv
        try:
            self.config.hedge_balance = nv
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "set_hedge_balance_live", type(_sup).__name__, _sup)
        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"HEDGE BALANCE CAP LIVE UPDATE: ${old_cap:.2f} -> "
                     f"${nv:.2f}. Current reserve ${old_reserve:.2f} "
                     f"unchanged (refill will target the new cap)."))
        logger.info("Bot %s hedge_balance cap live: %.2f -> %.2f",
                    self.bot_id, old_cap, nv)
        return {"applied": True, "old_cap": old_cap, "new_cap": nv,
                "current_reserve": old_reserve}

    # ------------------------------------------------------------------
    # Smart Wire target-side receiver (P1b ship, Session 26, 2026-04-24).
    # Operator spec: "Smart Wire feeds passively increase Fold Queue of
    # target bots and are distributed evenly across any existing
    # tranches OR wait for a new tranche to form before combining with
    # it."
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # v3.16.51 — Unified Smart Wire SCRUM-time routing helper.
    # ------------------------------------------------------------------
    # Operator directive 2026-05-10:
    #   "If I have a $5 scrum and a 25% route to ETH then WHY THE FUCK
    #    did not $1.25 go to ETH!?"
    #
    # The v3.16.46 ship added SCRUM-time routing to the AUTONOMOUS sell
    # path only. Manual Fire SCRUM and Detonation harvest both produced
    # scrum proceeds but bypassed the routing entirely — the operator's
    # heavy use of Manual Fire ("dagger catch" pattern) meant most
    # SCRUM proceeds never reached the wired bots.
    #
    # This helper extracts the routing into one place so EVERY sell
    # path that produces proceeds calls the same routine. Returns the
    # USD routed so the caller can subtract it from local accounting
    # (tranche build / fold queue / detonation harvest).
    def _route_scrum_proceeds_via_wires(
            self, scrum_usd: float, sell_fill: float,
            label: str = "scrum") -> float:
        """Route pct% of `scrum_usd` to each outgoing wire's target via
        `apply_wire_income`. Updates Smart Wire ledger for both
        source-side wired_out and target-side wired_in.

        Args:
          scrum_usd:  full proceeds available for routing (USD).
          sell_fill:  the actual fill price (used in audit ref string).
          label:      "scrum" / "manual_scrum" / "detonation" — appears
                      in WireTransaction.wire_type and operator log.

        Returns the total USD routed. Caller subtracts this from local
        accounting so tranches/fold-queue reflect only the local share.

        Failures are caught and logged; never raises (caller's sell path
        continues even if routing has issues).
        """
        _scrum_routed_total = 0.0
        try:
            _wire_mgr = self._smart_wire_mgr
            if (_wire_mgr is None
                    or not hasattr(_wire_mgr, "get_outgoing_wires")):
                return 0.0
            _wires = _wire_mgr.get_outgoing_wires(self.bot_id)
            if not _wires:
                return 0.0
            # Defensive: clamp total pct to 100% (operator config could
            # accidentally have wires summing > 100%).
            _total_pct = sum(float(p) for p in _wires.values())
            _scaling = 1.0
            if _total_pct > 100.0:
                _scaling = 100.0 / _total_pct
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"WIRE WARNING: outgoing wires sum to "
                             f"{_total_pct:.1f}% (>100%); clamping to "
                             f"100% via {_scaling:.4f}× scaling factor."))
            _bot_refs = getattr(_wire_mgr, "_bot_refs", {}) or {}
            _ledgers = getattr(_wire_mgr, "_ledgers", {}) or {}
            # v3.23.66 — apply SWOS safety math to the scrum-time
            # route (was only wired into distribute_fold_profit in
            # v3.23.65 — the fold-compound path). Same formula:
            # compute once per scrum event, divide by N outbound
            # wires, cap each wire at min(operator_pct, per_wire_safe).
            _n_wires = max(1, len(_wires))
            _swos_safe_pct = 100.0
            _per_wire_safe_pct = 100.0
            try:
                _swos_inputs = self.get_swos_inputs()
                if _swos_inputs:
                    from .smart_wire import compute_safe_outflow_pct
                    _swos_safe_pct = compute_safe_outflow_pct(
                        scrum_profit_usd=float(scrum_usd),
                        **_swos_inputs)
                    _per_wire_safe_pct = _swos_safe_pct / _n_wires
                    logger.debug(
                        "SWOS %s (scrum-route): safe=%.2f%% ÷ %d "
                        "wires = %.2f%% per-wire (scrum_usd=$%.4f)",
                        self.bot_id, _swos_safe_pct, _n_wires,
                        _per_wire_safe_pct, scrum_usd)
            except Exception as _swos_exc:  # noqa: BLE001 - best-effort
                logger.debug(
                    "SWOS %s (scrum-route) pre-check raised %s — "
                    "falling back to raw pct.",
                    self.bot_id, _swos_exc)
            for _tgt_id, _pct in _wires.items():
                try:
                    _eff_pct = min(
                        float(_pct) * _scaling, _per_wire_safe_pct)
                    _routed = scrum_usd * (_eff_pct / 100.0)
                    if _routed < 0.01:  # dust floor
                        continue
                    _tgt_bot = _bot_refs.get(_tgt_id)
                    if _tgt_bot is None:
                        continue
                    if not hasattr(_tgt_bot, "apply_wire_income"):
                        continue
                    _apply_result = _tgt_bot.apply_wire_income(
                        usd=_routed,
                        source=self.bot_id,
                        ref=f"{label}@{sell_fill:.8f}")
                    _scrum_routed_total += _routed
                    # v3.23.66 — distinctive [WIRE FIRE] log at every
                    # scrum-time route hop so operator can grep for it.
                    # Prior 'WIRE INCOME' log only fired on the target
                    # side and read like GUI chrome — this one is
                    # source-side + names both the amount and the
                    # target bot's placement.
                    try:
                        _mode = (
                            _apply_result.get("mode", "?")
                            if isinstance(_apply_result, dict) else "?")
                        _tgt_short = (
                            str(_tgt_id)[:8] + "…"
                            if len(str(_tgt_id)) > 8 else str(_tgt_id))
                        self._bus.emit(
                            "bot.log", bot_id=self.bot_id,
                            message=(
                                f"[WIRE FIRE] scrum-route: ${_routed:.4f} "
                                f"→ {_tgt_short} (pct={_eff_pct:.2f}%, "
                                f"landed: {_mode})"))
                    except Exception as _sup:  # noqa: BLE001 - log best-effort
                        logger.debug("suppressed in %s: %s: %s", "_route_scrum_proceeds_via_wires", type(_sup).__name__, _sup)
                    # Audit: record transaction
                    _txns = getattr(_wire_mgr, "_transactions", None)
                    if _txns is not None:
                        try:
                            from .smart_wire import WireTransaction
                            import time as _wt_time
                            _txns.append(WireTransaction(
                                timestamp=int(_wt_time.time()),
                                source_bot=self.bot_id,
                                target_bot=str(_tgt_id),
                                amount=float(_routed),
                                wire_type=f"{label.upper()}_ROUTE",
                                reason=(f"{_eff_pct:.2f}% of "
                                         f"${scrum_usd:.4f} {label}")))
                        except Exception as _sup:  # R28-OK: audit-only
                            logger.debug("suppressed in %s: %s: %s", "_route_scrum_proceeds_via_wires", type(_sup).__name__, _sup)
                    # Update target's ledger wired_in
                    if _tgt_id in _ledgers:
                        try:
                            _ledgers[_tgt_id].wired_in += float(_routed)
                        except Exception as _sup:  # R28-OK: ledger probe
                            logger.debug("suppressed in %s: %s: %s", "_route_scrum_proceeds_via_wires", type(_sup).__name__, _sup)
                    # Update source's ledger wired_out
                    if self.bot_id in _ledgers:
                        try:
                            _ledgers[self.bot_id].wired_out += float(_routed)
                        except Exception as _sup:  # R28-OK: ledger probe
                            logger.debug("suppressed in %s: %s: %s", "_route_scrum_proceeds_via_wires", type(_sup).__name__, _sup)
                except Exception as _wone_exc:
                    logger.warning(
                        "Bot %s wire route to %s failed (label=%s): %s",
                        self.bot_id, _tgt_id, label, _wone_exc)
            if _scrum_routed_total > 0:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"WIRE OUT ({label.upper()}): routed "
                             f"${_scrum_routed_total:.4f} of "
                             f"${scrum_usd:.4f} {label} proceeds "
                             f"across {len(_wires)} target bot(s). "
                             f"Remaining "
                             f"${scrum_usd - _scrum_routed_total:.4f} "
                             f"stays with this bot."))
        except Exception as _wr_exc:
            logger.warning(
                "Bot %s %s-time wire routing raised: %s "
                "(continues with full proceeds to local accounting)",
                self.bot_id, label, _wr_exc)
            return 0.0
        return _scrum_routed_total

    def apply_wire_income(self, usd: float, source: str,
                          ref: str = "") -> dict:
        """Apply incoming Smart Wire USD to this bot's fold queue.

        Semantic (two cases):

        1. `_fold_tranches` non-empty: distribute `usd` EVENLY across
           all existing tranches. Each tranche's `usd` grows by
           `usd / len(tranches)`. `_fold_queue_usd` recomputed as the
           sum. Each tranche gains a `wire_credits` provenance entry
           naming the source bot + ref.

        2. `_fold_tranches` empty: park the USD in `_pending_wire_credits`
           with a ledger entry. The pending bucket is absorbed into the
           next tranche created by `_execute_sell` (see tranche-build
           site below); at that moment the new tranche's initial `usd`
           = scrum_usd + pending, and the bucket clears.

        Non-blocking: caller ignores return value in happy path. Rejects
        invalid USD with {"applied": False, "reason": ...}.

        sadp: R1 R11 R28 R33
        """
        try:
            u = float(usd)
        except (TypeError, ValueError):
            return {"applied": False,
                    "reason": f"usd must be numeric; got {usd!r}"}
        if u <= 0:
            return {"applied": False,
                    "reason": f"usd must be > 0; got {u}"}

        src = str(source or "?")
        rf = str(ref or "")
        import time as _t
        credit = {"ts": _t.time(), "source": src, "usd": u, "ref": rf}

        # =================================================================
        # v3.15.69 — WIRE-INCOME STACKING AT ENTRY
        # =================================================================
        # Operator directive 2026-04-26:
        #   "Bot Swarm profit outflows now acquire additional Target Asset
        #    at the destination if the Target Balance is within x% of
        #    center line. This will allow for a bottom targeted bot that
        #    has yet to move upward to increase its Target Balance at
        #    whatever pace the in flows are moving until it moves off
        #    center line and is no longer safe to stack. This cannot
        #    happen at any other point than the Entry Price for the bot
        #    so as to avoid subsequent aggressive stacking at different
        #    price points."
        #
        # Conditions ALL required:
        #   1. config.wire_inflow_stack_pct > 0  (feature enabled)
        #   2. |position - target| ≤ target × wire_inflow_stack_pct%
        #      (bot is currently AT center line)
        #   3. Bot has at least one main lot (an "entry price" exists)
        #   4. |current_price - entry_price| ≤ entry_price ×
        #      wire_inflow_stack_pct% (price still at entry — same x%)
        #
        # When all met:
        #   • Bump _target_balance + _anchor_target_balance by usd so
        #     the new center line is at the higher level
        #   • Set _pending_stack_buy_usd += usd so the next tick's
        #     _execute_manual_rebalance acquires the asset (bypasses
        #     normal gates by virtue of the operator-initiated rebalance
        #     path)
        # When NOT met: fall through to the existing distribute / park
        # behavior so wire income is preserved as future fold-queue credit.
        try:
            stack_pct = float(getattr(
                self.config, "wire_inflow_stack_pct", 1.0) or 0)
        except (TypeError, ValueError):
            stack_pct = 0.0
        _stack_eligible = False
        _stack_reason = ""
        # v3.24.20 — bind before the try. Both names are assigned only
        # inside the try below, and the `if _stack_eligible:` block that
        # reads them is reachable only when that try got far enough to
        # set the flag — so today this is safe by correlation, which is
        # why pyright flags it as possibly-unbound and a human reads it
        # as fine. That correlation is not enforced by anything: one
        # extra `_stack_eligible = True` path, or a reordering, turns
        # this into a NameError on a live wire-income event. Binding
        # here makes the invariant explicit instead of emergent.
        _target = 0.0
        _entry_px = 0.0
        if stack_pct > 0:
            try:
                _last_px = (
                    getattr(self, "_last_trade_price", 0)
                    or float(getattr(self.stats, "current_price", 0))
                )
                if _last_px <= 0:
                    _stack_reason = "no last-trade price yet"
                else:
                    _qrate_local = float(self._quote_to_usd or 1.0)
                    _pos_usd = (
                        self._current_holdings * _last_px * _qrate_local)
                    _target = float(self._target_balance)
                    _band_usd = _target * stack_pct / 100.0
                    _at_center = abs(_pos_usd - _target) <= _band_usd
                    # Entry price = first lot's initial_buy_price (bot's
                    # original cost basis). Operator's rule: stacking
                    # only happens at entry to avoid pyramiding at
                    # different price points.
                    _entry_px = 0.0
                    if self._main_lots:
                        try:
                            _entry_px = float(
                                self._main_lots[0].get(
                                    "initial_buy_price", 0) or 0)
                        except (TypeError, ValueError):
                            _entry_px = 0.0
                    _at_entry = (
                        _entry_px > 0
                        and abs(_last_px - _entry_px)
                        <= _entry_px * stack_pct / 100.0)
                    if _at_center and _at_entry and _target > 0:
                        _stack_eligible = True
                    elif not _at_center:
                        _stack_reason = (
                            f"position ${_pos_usd:.2f} not within "
                            f"{stack_pct:.1f}% band of target ${_target:.2f}")
                    elif _entry_px <= 0:
                        _stack_reason = "no entry price (no main lots)"
                    elif not _at_entry:
                        _stack_reason = (
                            f"price ${_last_px:.6f} not within "
                            f"{stack_pct:.1f}% of entry ${_entry_px:.6f}")
            except Exception as _stack_exc:  # R28-OK: error captured in _stack_reason for downstream emit
                _stack_reason = f"eval raised {type(_stack_exc).__name__}"

        if _stack_eligible:
            # Bump target + anchor; queue an aggressive buy for next tick.
            self._target_balance = float(self._target_balance) + u
            self._anchor_target_balance = (
                float(self._anchor_target_balance) + u)
            try:
                self.config.target_balance = self._target_balance
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "apply_wire_income", type(_sup).__name__, _sup)
            self._pending_stack_buy_usd = (
                float(getattr(self, "_pending_stack_buy_usd", 0.0) or 0.0)
                + u)
            try:
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id,
                    message=(
                        f"WIRE STACK: +${u:.2f} from {src} stacked at entry. "
                        f"Target ${_target:.2f} → ${self._target_balance:.2f} "
                        f"(at center line ±{stack_pct:.1f}%, at entry "
                        f"${_entry_px:.6f}). Next tick will acquire "
                        f"{u:.2f}-USD-worth of {self.config.target_asset} "
                        f"via aggressive rebalance. ref={rf}"))
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "apply_wire_income", type(_sup).__name__, _sup)
            return {"applied": True, "mode": "stacked",
                    "stacked_usd": u,
                    "new_target_balance": self._target_balance,
                    "entry_price": _entry_px}
        elif stack_pct > 0 and _stack_reason:
            # Operator wants visibility into WHY a stack didn't fire so
            # the feature isn't silently degrading to park-only.
            try:
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id,
                    message=(
                        f"WIRE STACK skipped ({_stack_reason}). "
                        f"Income falls through to "
                        f"{'distribute' if self._fold_tranches else 'pending'}."))
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "apply_wire_income", type(_sup).__name__, _sup)
        # =================================================================
        # End of v3.15.69 stack-at-entry block. Fall through to existing
        # distribute (Case 1) / park-pending (Case 2) behavior.
        # =================================================================

        if self._fold_tranches:
            # Case 1 — even distribution across existing tranches
            share = u / len(self._fold_tranches)
            for t in self._fold_tranches:
                t["usd"] = float(t.get("usd", 0) or 0) + share
                # v3.24.20 — bounded. This runs once per tranche per
                # wire event, so growth was credits x tranches; at 27
                # tranches it was 96% of this bot's persisted state.
                self._add_wire_credits(t, [{
                    "source": src, "usd": share, "ref": rf,
                    "ts": credit["ts"]}])
            self._fold_queue_usd = sum(
                float(t.get("usd", 0) or 0) for t in self._fold_tranches)
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"WIRE INCOME: +${u:.4f} from {src} distributed "
                         f"evenly across {len(self._fold_tranches)} "
                         f"tranche(s) (${share:.4f}/tranche). Fold queue "
                         f"now ${self._fold_queue_usd:.4f}."))
            logger.info("Bot %s wire income %.4f from %s → %d tranches",
                        self.bot_id, u, src, len(self._fold_tranches))
            return {"applied": True, "mode": "distributed",
                    "tranches_credited": len(self._fold_tranches),
                    "per_tranche_usd": share,
                    "new_fold_queue_usd": self._fold_queue_usd}

        # Case 2 — no tranches yet; park in pending
        self._pending_wire_credits += u
        self._pending_wire_ledger.append(credit)
        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"WIRE INCOME PENDING: +${u:.4f} from {src} parked "
                     f"(no open tranches). Pending total "
                     f"${self._pending_wire_credits:.4f}. Will absorb "
                     f"into next scrum tranche."))
        logger.info("Bot %s wire income %.4f from %s → pending "
                    "(no tranches)", self.bot_id, u, src)
        return {"applied": True, "mode": "pending",
                "pending_total": self._pending_wire_credits,
                "ledger_size": len(self._pending_wire_ledger)}

    # USD tolerance for the atomicity check below. The arrival is booked
    # in USD and the target lifts in USD, so the residual is USD too.
    # 1e-6 USD is one ten-thousandth of a cent: float noise, not money.
    #
    # THIS NUMBER IS PART OF THE CHECK, NOT A KNOB. Widening it blinds
    # the only mechanism that can falsify a half-applied arrival: at
    # 1e9 every residual this method can produce compares "within
    # tolerance", so `atomic` would read True on a ledger that booked
    # nothing. `test_the_tolerance_is_too_small_to_hide_an_arrival`
    # pins the magnitude for that reason. Do not raise it to make a
    # failing case pass; a residual above 1e-6 USD is a defect report.
    _ARRIVAL_ATOMIC_TOL_USD: float = 1e-6

    @staticmethod
    def _positive_observed_quantity(
            value: Any, label: str) -> tuple[float | None, str | None]:
        """Parse one observed money-path quantity, or say why it is unusable.

        Both halves of an Extractor arrival are OBSERVED quantities --
        USD that landed and units that landed -- and both are refused on
        exactly the same four grounds. One parser keeps the two halves
        from drifting apart, which is how a validated half and an
        unvalidated half end up in the same write.

        THE BOOL GROUND IS NOT DEFENSIVE PADDING. `bool` is a subclass
        of `int`, so `float(True)` is 1.0 -- finite, greater than zero,
        and indistinguishable from a dollar to every numeric test below
        it. `usd_value=True` therefore returned applied=True and lifted
        the target from $200.00 to $201.00 on real money. A flag is not
        an amount, so it is refused BY TYPE, before any numeric test can
        launder it into one.

        AND A STRING IS NOT AN AMOUNT EITHER -- v3.25.7. The bool ground
        was the ONLY type ground here, and everything else fell through
        to `float()`, which parses `"20.0"` without complaint. Operator
        probe against v3.25.6, measured: `usd_value="20.0"` with
        `base_units="0.1"` returned applied=True and booked to real
        state -- holdings 1.0 -> 1.1, target $200.00 -> $220.00, anchor
        $200.00 -> $220.00, `_main_lots` 1 -> 2. A caller that hands a
        money path a string has read a number out of a log line, a JSON
        blob or a widget, and the arrival this method exists to contain
        is an OBSERVED EXCHANGE QUANTITY: it comes off a fill, as a
        number. So the ground is now the type itself. `int` and `float`
        (and their subclasses, which is how `numpy.float64` gets in)
        are amounts; everything else is refused by name.

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
        # EXACT type, not isinstance. isinstance admits bool (an int
        # subclass) and any user subclass of int or float, so the set
        # of accepted inputs was open. An exact test closes it to two.
        if type(value) is not int and type(value) is not float:
            return None, (f"{label} must be exactly an int or a float, "
                          f"not a {type(value).__name__}; got {value!r}")
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
    def _finite_state_number(
            value: Any, label: str) -> tuple[float | None, str | None]:
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

        THE TYPE GROUND IS SHARED TOO, v3.25.7, and for a reason this
        contract does not merely inherit. The tick multiplies
        `_current_holdings` by a price (:6783) and subtracts
        `_target_balance` (:7608); a string in either raises TypeError
        in the DECIDER. State that only `float()` can read is already
        broken state, so coercing it here would launder a corruption
        into a durable float write. Refuse it and say which name it was.
        `OverflowError` is caught for the same reason as in
        `_positive_observed_quantity`: a huge `int` is a valid `int`.

        Returns:
          (number, None) when usable, (None, reason) when refused.
        """
        # EXACT type, not isinstance. isinstance admits bool (an int
        # subclass) and any user subclass of int or float, so the set
        # of accepted inputs was open. An exact test closes it to two.
        if type(value) is not int and type(value) is not float:
            return None, (f"{label} must be exactly an int or a float, "
                          f"not a {type(value).__name__}; got {value!r}")
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

        TOTAL BY CONSTRUCTION, v3.25.7. The old body was not: a lot
        object whose `__getitem__` or `__float__` raised anything
        outside the four listed exceptions threw straight out of the
        read-back, and the read-back is the one instrument that runs
        AFTER the writes. Each lot is therefore required to be exactly
        a `dict` -- `dict.__getitem__` runs no Python and cannot raise
        anything but `KeyError` -- and the coercion catches every
        exception, because `__float__` on the stored value is the one
        place caller-shaped data still gets to run code. The units
        value is deliberately NOT type-refused the way the two money
        parameters are: `_main_lots_invariant_ok` (:14971) coerces the
        same field with a bare `sum`, and refusing here what that
        accepts would put the ledger's two readers on different rules.

        Returns:
          (total_units, None) when readable, (None, reason) when not.
        """
        total = 0.0
        for _index, _lot in enumerate(lots):
            if type(_lot) is not dict:  # noqa: E721 - exact dict only
                return None, (f"_main_lots[{_index}] must be a lot dict; "
                              f"got a {type(_lot).__name__}")
            if "units" not in _lot:
                return None, (f"_main_lots[{_index}] has no usable "
                              f"'units' entry")
            try:
                _units = float(_lot["units"])
            except Exception:  # noqa: BLE001 - any __float__ may raise
                return None, (f"_main_lots[{_index}] has no usable "
                              f"'units' entry")
            if not math.isfinite(_units):
                return None, (f"_main_lots[{_index}]['units'] must be "
                              f"finite; got {_units!r}")
            total += _units
        return total, None

    def apply_extractor_tranche_return(
            self, usd_value: Any, source: str, base_units: Any,
            ref: str = "") -> dict:
        """Book base currency returned by a child Extractor Tranche.

        v3.25.2 lifted the target. v3.25.5 makes the method own BOTH
        halves of the arrival. Operator design 2026-08-09:

            "rather than have an immediate Base Currency to USD sell
             fire this profit off as Surplus we want it protected by
             lifting the Target Balance to contain it and then have the
             received additional Base Currency to be distributed upward
             for further gains in terms of USD"

        THE TWO HALVES ARE THE TWO TERMS OF ONE SUBTRACTION. The tick
        computes `current_value = _current_holdings * ticker.last *
        _quote_to_usd` (:6783) and then `delta = current_value -
        _target_balance` (:7608). An arrival moves BOTH terms. Split the
        halves and delta moves, in whichever direction the missing half
        was:

          holdings booked, target not lifted -> delta POSITIVE. The
            header model says "If delta > 0 and delta_pct >= interval:
            SCRUM (sell excess)", so the parent sells the child's gain.
          target lifted, holdings not booked -> delta NEGATIVE. The
            parent buys to close a gap that does not exist, spending
            real USD on a phantom shortfall.

        v3.25.2 delegated the holdings half to a caller in prose. No
        caller was ever written, so the shipped behaviour was the second
        failure: lift with no units. The method now performs both writes
        itself, in one synchronous block with no await and no callback
        between the first write and the last. That is the whole of the
        atomicity guarantee -- every coroutine in this app runs on the
        Qt GUI thread, so a block that never yields cannot be observed
        half-applied.

        WHAT "DELTA DOES NOT MOVE" MEANS, STATED WITH ITS CONDITION.
        v3.25.7 -- the v3.25.6 wording carried ONE quote rate `q`
        through an expression that reads the rate at TWO DIFFERENT
        TIMES, and so quietly assumed the rate cannot move between the
        arrival and the tick that reads it. Write both out. With P the
        live quote-side price, `q_tick` the rate the tick reads (:6783)
        and `q_arr` the rate this method read when it priced the
        arrival:

            d(delta) = base_units * P * q_tick - usd_value

        and since `usd_value = base_units * arrival_price * q_arr` by
        construction, that is

            d(delta) = base_units * (P * q_tick
                                     - arrival_price * q_arr)

        which is ZERO EXACTLY WHEN `P * q_tick` EQUALS
        `arrival_price * q_arr` -- when the USD price of one base unit
        is unchanged, not merely when the quote-side price is. Two ways
        to satisfy it and only two: both factors unchanged, or the two
        moved by exactly reciprocal amounts. On a USD-quoted symbol
        `q_arr == q_tick == 1.0` and the condition collapses to
        `P == arrival_price`, which is what v3.25.6 stated as though it
        were the general case. On a non-USD quote it does not collapse:
        a move in the rate ALONE moves delta, with the quote-side price
        frozen.

        At any other USD price the arrival moves delta by the
        mark-to-market of the units just booked -- precisely what the
        same units would contribute had the parent bought them itself.
        So the claim is that the arrival adds NO DELTA OF ITS OWN, not
        that delta is frozen: containment neutralises the booking, and
        the market still prices the position afterwards.

        KNOWN LIMITATION -- CONTAINMENT DOES NOT SURVIVE A DRIFT-DOWN
        RECONCILE, AND BOTH LIFTED BALANCES ARE LEFT BEHIND.
        `_reconcile_holdings` (:11323) writes `_main_lots` and
        `_current_holdings` and writes NEITHER `_target_balance` NOR
        `_anchor_target_balance` anywhere (AST-verified over the whole
        function, both names). Its drift-DOWN branch (:11573-11595)
        rescales every lot by `exchange_units / internal_units` and
        resets holdings to the exchange figure. Run it after an arrival
        and the units go while both lifts stay: a $20 arrival on a
        1.0-unit position, reconciled against an exchange that reports
        the pre-arrival 1.0, leaves delta at -$20.00. Measured, not
        reasoned.

        v3.25.6 RECORDED ONLY HALF OF THAT BLAST RADIUS. It named the
        target and stopped. The stranded ANCHOR is the wider of the two,
        because the anchor is the base other limits are taken from and
        it is not reset by the tick: `_apply_fold_target_growth` sizes
        the per-cycle Growth Rate Cap as
        `self._anchor_target_balance * (max_target_growth_pct / 100)`
        (:1702), and `position_ceiling_usd` returns
        `self._anchor_target_balance * mult` (:4714). A $20 stranded
        lift on a $200 anchor therefore widens the growth cap by 10% and
        raises the Smart Ceiling by $20 x mult, for as long as it
        stands.

        THIS IS NOT FIXED HERE, ON PURPOSE. A rescale is PROPORTIONAL
        across every lot and the ledger records no provenance, so
        nothing in `_main_lots` says which units arrived from a child
        and which were bought. `_target_balance` is built from operator
        config, fold growth (:1628), wire income (:2378) and arrivals
        together, so there is no evidence available at reconcile time to
        size a matching un-lift. Un-lifting proportionally would guess.
        The drift-DOWN branch is also the "legitimate loss" branch: a
        target that stays put while units vanish drives delta negative,
        which makes the parent re-buy the position -- accumulation
        behaviour, not obviously a defect. Deciding that needs its own
        evidence and its own arc. Pinned by
        `test_KNOWN_LIMITATION_drift_down_reconcile_breaks_the_pairing`
        so the limitation cannot quietly change without this text
        changing too.

        THE HOLDINGS HALF IS A LOT, NOT A NUMBER. Since v3.23.43 this
        bot owns exactly what is in `_main_lots` and derives
        `_current_holdings` from that source alone (:6777). The
        invariant `sum(lot["units"]) == _current_holdings` (:574) is
        checked by `_main_lots_invariant_ok` (:14971). Two consequences,
        both load-bearing:

          * Incrementing `_current_holdings` without appending a lot
            breaks the invariant, and the next drift-down reconcile
            rescales `_main_lots` and resets holdings (:11573-11595),
            silently undoing the credit.
          * Booking nothing at all is not neutral either. Units that
            land on the exchange but are never attributed are refused
            by the drift-UP policy (:11597-11614) -- "those units
            belong to another bot, prior state, or operator" -- so the
            child's gain would sit unclaimed forever.

        HOW THE REST OF THE FILE MAINTAINS THE TWO HALVES. Re-derived
        by AST over every method, v3.25.6, because the v3.25.5 note
        said "every other credit site appends a lot AND moves the
        scalar" and the file does not do that. There are two shapes:

          SPLIT ACROSS AN AWAIT, and it is the common one. `_execute_buy`
            (:14369) moves the scalar -- `self._current_holdings +=
            amount` (:14846) -- and appends NO lot. Its callers append
            the lot after the await returns: `tick` at :7550 -> :7573,
            :10010 -> :10067, :10519 -> :10553, and `manual_fire_tranche`
            at :3453 -> :3498. Between the scalar write and the lot
            append the coroutine has already yielded, so the :574
            invariant is briefly false and a tick can see it.

          SYNCHRONOUS, and rarer. `_execute_manual_rebalance` (:11742)
            appends (:12703 / :12720) and moves the scalar (:12729)
            with nothing suspending in between.

        This method is deliberately the second shape. The first shape is
        exactly why a caller-side pairing is unsafe, and therefore why
        the method owns both halves instead of delegating one of them.

        WHY `usd_value` IS AN OBSERVED ARRIVAL, NOT A COMPUTED PROFIT.
        The caller passes what ACTUALLY LANDED in the balance. That is
        already net of every fee the Extractor paid on both legs, so
        this lift cannot be gross or net -- there is nothing to net.
        Measure the arrival; do not compute the gain. Same exchange-truth
        principle as `buy_safety`. `base_units` is the matching observed
        quantity, so the lot's `initial_buy_price` is the two of them
        put back into the shape `_main_lots` stores -- a quote-side
        price -- and not a fabricated entry price.

        WHY THIS IS NOT `_apply_fold_target_growth` (:1628). That helper
        applies the per-cycle Growth Rate Cap (`max_target_growth_pct`,
        default 1.0% of anchor). A cap is WRONG here: a return larger
        than the cap would be truncated, the uncontained remainder would
        read as excess, and the parent would scrum exactly the amount
        this method exists to protect. Containment is uncapped by
        construction.

        Args:
          usd_value:  USD value of the base currency that arrived. Must
                      be finite and > 0, or the call is refused.
          source:     child bot id, for the audit line.
          base_units: units that arrived. Load-bearing since v3.25.5 --
                      this is the holdings half. Must be finite and
                      > 0, or the call is refused. No default: a silent
                      0.0 is the "target moves, holdings do not" failure
                      written as a signature.
          ref:        optional correlation tag.

        Returns:
          {"applied": bool, ...}. On refusal nothing is mutated.

        Tests: tests/test_extractor_tranche_containment.py.

        """
        # FAIL-CLOSED, AND THE EXACT SCOPE OF THAT PROMISE.
        #
        # v3.25.7 narrows this AGAIN, because v3.25.6's narrowing was
        # still wider than the code. It listed what the method reads and
        # said it refuses on all of it, while four raise paths were open
        # underneath: `float(10 ** 400)` is OverflowError and neither
        # parser caught it; a lot object with a hostile `__getitem__` or
        # `__float__` threw out of the ledger read-back, which is the
        # one instrument that runs AFTER the writes; an overridden
        # `append` could raise from INSIDE the atomic block; and
        # `self._ARRIVAL_ATOMIC_TOL_USD`, shadowed on an instance, threw
        # from the comparison after all four writes were durable.
        #
        # WHAT IS PROMISED, and each item is a test: the method returns
        # {"applied": False, "reason": ...} and mutates nothing for
        # every value it reads or writes -- `usd_value` and `base_units`
        # (refused BY TYPE, ahead of every numeric test), `source`,
        # `_quote_to_usd`, `_main_lots` and every lot inside it,
        # `_target_balance`, `_current_holdings`,
        # `_anchor_target_balance`, `_ARRIVAL_ATOMIC_TOL_USD`, the
        # arrival price, and the three post-arrival sums. AFTER the last
        # of those checks the method runs nothing that can raise: the
        # block is one `list.append` on an exact `list` -- a C-level
        # store that executes no Python -- plus three stores of
        # pre-computed floats, and every statement past the block is
        # either float arithmetic on validated numbers or already inside
        # a `try`.
        #
        # WHAT IS NOT PROMISED, named rather than implied:
        #   * `MemoryError`, `KeyboardInterrupt` and `SystemExit`.
        #     Nothing in this application recovers from those.
        #   * a `config` whose `target_balance` setter raises. Caught by
        #     the mirror's own `except`, and harmless: the delta path
        #     reads `self._target_balance`, never `config`.
        #   * a `self` whose `__setattr__` drops or rewrites a store.
        #     Nothing can detect that in advance. It is caught AFTER the
        #     writes by the state read-back below, which re-reads all
        #     three scalars and reports `atomic: False` with the gap
        #     that names which write went missing.
        #   * `self._bus` and the signal sink. Both are wrapped; a
        #     diagnostic that fails must not move money or raise.
        u, _why = self._positive_observed_quantity(usd_value, "usd_value")
        if u is None:
            return {"applied": False, "reason": _why or "usd_value refused"}
        b, _why = self._positive_observed_quantity(base_units, "base_units")
        if b is None:
            return {"applied": False, "reason": _why or "base_units refused"}

        # `source` is only ever rendered into an audit line, but a
        # caller-supplied object can raise from `__bool__` or `__str__`,
        # and this used to run unguarded. It sits before the writes, so
        # the old failure cost no money -- it cost the refusal contract.
        try:
            src = str(source or "?")
        except Exception as _src_exc:  # noqa: BLE001 - any __str__ may raise
            return {"applied": False,
                    "reason": (f"source is not renderable: "
                               f"{type(_src_exc).__name__}: {_src_exc}")}

        # `bot_id` is read by the two diagnostic blocks AND by the
        # `except` handlers that guard them. Reading it inside a handler
        # is a raise the handler cannot catch, so it is rendered once,
        # here, where failing is free.
        try:
            _bot_id = str(getattr(self, "bot_id", "?"))
        except Exception:  # noqa: BLE001 - any __str__ may raise
            _bot_id = "?"

        try:
            # `or 1.0` is not a convenience here. The tick prices the
            # position with EXACTLY this expression (:6783), so the
            # arrival must be priced with it too. A stricter reading
            # here -- refusing a 0.0 rate the tick silently reads as
            # 1.0 -- would put the containment arithmetic and the
            # decision arithmetic on different numbers, which is the
            # only way a correct lift can still move delta.
            #
            # This is also why `_quote_to_usd` is NOT TYPE-refused the
            # way the two money parameters are: the tick coerces the
            # stored value with THIS expression, so refusing here what
            # the tick accepts would BE the divergence, not the safety.
            qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
        except (TypeError, ValueError, OverflowError):
            return {"applied": False,
                    "reason": "quote_to_usd is not numeric; cannot price "
                              "the arrival"}
        # NaN, inf and negatives survive the `or 1.0` coercion, and each
        # would write a nonsense price into `_main_lots`. Refuse those.
        if not math.isfinite(qrate) or qrate <= 0:
            return {"applied": False,
                    "reason": f"quote_to_usd must be finite and > 0; "
                              f"got {qrate!r}"}

        # No ledger, no credit. Booking units the ledger cannot hold is
        # what breaks the :574 invariant.
        #
        # EXACTLY A LIST, NOT MERELY SOMETHING THAT PASSES `isinstance`.
        # v3.25.7. `isinstance(lots, list)` stood here, and it admits a
        # SUBCLASS -- which means an overridden `append`, which means
        # caller-supplied Python running INSIDE the atomic block, which
        # is the one place this method promises nothing can raise.
        # Measured on the v3.25.6 file with a ledger whose `append`
        # stored the lot and then raised: `RuntimeError` escaped the
        # method, `_main_lots` went 1 -> 2, `_current_holdings` and
        # `_target_balance` did not move at all, and the :574 invariant
        # was left 0.1 units apart. The atomic block had been split by
        # the one call inside it.
        #
        # `list.append` on an EXACT list is a C-level store: it runs no
        # Python and cannot raise short of `MemoryError`. That is what
        # turns the block's "nothing here can raise" rule from an
        # assertion into a proof. Nothing legitimate is refused --
        # `test_every_main_lots_assignment_builds_a_plain_list`
        # AST-checks that every site in this file which assigns
        # `self._main_lots` assigns a plain list literal or a list
        # comprehension.
        lots = getattr(self, "_main_lots", None)
        if type(lots) is not list:  # noqa: E721 - subclasses are refused
            return {"applied": False,
                    "reason": (f"_main_lots must be exactly a list, not a "
                               f"{type(lots).__name__}; refusing to book "
                               f"an unattributable arrival")}

        # USD = units x quote_price x quote_to_usd (:4619). Inverted,
        # this is the quote-side price `_main_lots` stores alongside
        # every other lot. Both observed quantities, no model.
        #
        # GUARD THE PRODUCT, NOT THE FACTORS. `b` and `qrate` are each
        # validated finite and > 0 above, and that is not sufficient:
        # two tiny-but-positive operands underflow, `1e-200 * 1e-200`
        # is exactly 0.0, and `u / 0.0` raised ZeroDivisionError out of
        # a money path that documents itself as fail-closed.
        #
        # THE MIRROR CASE IS REFUSED BY THIS SAME GUARD, NOT BY THE
        # PRICE CHECK. v3.25.6's comment said two huge factors "overflow
        # to inf, which the price check below then catches as a zero
        # price". They do overflow, and the price check never sees it:
        # `math.isfinite(_price_divisor)` is evaluated FIRST and an inf
        # divisor fails it. Measured on this file with
        # `base_units=1e300` and `quote_to_usd=1e300`, the reason string
        # reads "base_units x quote_to_usd is not a usable divisor;
        # 1e+300 x 1e+300 = inf" -- this guard's own words, not the
        # price check's.
        _price_divisor = b * qrate
        if not math.isfinite(_price_divisor) or _price_divisor <= 0.0:
            return {"applied": False,
                    "reason": (f"base_units x quote_to_usd is not a usable "
                               f"divisor; {b!r} x {qrate!r} = "
                               f"{_price_divisor!r}")}
        arrival_price = u / _price_divisor
        if not math.isfinite(arrival_price) or arrival_price <= 0:
            return {"applied": False,
                    "reason": f"arrival price not usable; got "
                              f"{arrival_price!r}"}

        # EVERY READ THE BLOCK DEPENDS ON HAPPENS HERE, WHERE FAILING
        # IS FREE. `_anchor_target_balance` used to be coerced inside
        # the block; see the block header for what that cost.
        _t_before, _why = self._finite_state_number(
            getattr(self, "_target_balance", None), "_target_balance")
        if _t_before is None:
            return {"applied": False,
                    "reason": _why or "_target_balance refused"}
        _h_before, _why = self._finite_state_number(
            getattr(self, "_current_holdings", None), "_current_holdings")
        if _h_before is None:
            return {"applied": False,
                    "reason": _why or "_current_holdings refused"}
        _a_before, _why = self._finite_state_number(
            getattr(self, "_anchor_target_balance", None),
            "_anchor_target_balance")
        if _a_before is None:
            return {"applied": False,
                    "reason": _why or "_anchor_target_balance refused"}

        # The verdict's tolerance is read from state too, so it is read
        # HERE. `_ARRIVAL_ATOMIC_TOL_USD` is a class constant, but an
        # instance can shadow it, and every use of it is an `abs(...) <=
        # _tol` comparison AFTER all four writes are durable -- exactly
        # the shape D1 was about. A negative tolerance is refused as
        # well: it cannot hide a defect, but it would report every
        # healthy arrival as non-atomic, and an alarm that is always on
        # is the same failure as one that never fires.
        _tol, _why = self._finite_state_number(
            getattr(self, "_ARRIVAL_ATOMIC_TOL_USD", None),
            "_ARRIVAL_ATOMIC_TOL_USD")
        if _tol is None or _tol < 0.0:
            return {"applied": False,
                    "reason": (_why or f"_ARRIVAL_ATOMIC_TOL_USD must be "
                                       f"finite and >= 0; got {_tol!r}")}

        # The ledger's own reading of itself, taken before the write so
        # the check below can subtract one from the other. A ledger that
        # cannot be summed cannot be added to.
        _units_before, _why = self._sum_lot_units(lots)
        if _units_before is None:
            return {"applied": False,
                    "reason": _why or "_main_lots is unreadable"}
        _lots_before = len(lots)

        # The four values the block writes, computed and checked here.
        # Addition is the last thing that can produce a non-finite
        # number, so it is the last thing checked before the block.
        _h_after = _h_before + b
        _t_after = _t_before + u
        _a_after = _a_before + u
        for _field, _value in (("_current_holdings", _h_after),
                               ("_target_balance", _t_after),
                               ("_anchor_target_balance", _a_after)):
            if not math.isfinite(_value):
                return {"applied": False,
                        "reason": (f"{_field} would become {_value!r}; "
                                   f"refusing to write a non-finite "
                                   f"balance")}
        _arrival_lot = {
            "units": b,
            "initial_buy_price": arrival_price,
            "operator_initiated": False,
        }

        # ---------------- ATOMIC ARRIVAL — DO NOT SPLIT ----------------
        # ASSIGNMENTS ONLY, plus the one ledger append of a dict that is
        # already built. Nothing here coerces, parses, divides or calls
        # anything that can raise. Every value was validated above.
        #
        # THE DEFECT THIS SHAPE CLOSES. `_anchor_target_balance` used to
        # be coerced HERE, as `float(self._anchor_target_balance) + u`,
        # the last statement in the block. A stored "not-a-number"
        # raised ValueError AFTER the lot append, the holdings write and
        # the target write had all landed, and the bot ran on with three
        # of four writes durable: holdings 1.0 -> 1.1, target
        # 200.0 -> 220.0, one extra lot, anchor untouched. The method
        # whose only job is atomicity left exactly the corruption it
        # exists to prevent, and it survived every gate.
        #
        # Both halves, one synchronous run. No await, no bus emit, no
        # caller-supplied callable between the first write and the last,
        # so no tick can read a half-applied state. Target and anchor
        # move together, following the co-movement precedent at
        # :2378-2382.
        lots.append(_arrival_lot)
        self._current_holdings = _h_after
        self._target_balance = _t_after
        self._anchor_target_balance = _a_after
        # -------------- END ATOMIC ARRIVAL — DO NOT SPLIT --------------

        # Outside the atomic block on purpose: `config` may be any
        # object the caller built, and a property setter on it can run
        # arbitrary code. The delta path reads `self._target_balance`,
        # not `config`, so a failure here cannot move delta.
        try:
            self.config.target_balance = self._target_balance
        except Exception as _mirror_exc:  # R28-OK: state already moved
            logger.debug(
                "Bot %s could not mirror target_balance to config: %s",
                _bot_id, _mirror_exc)

        # ---- THE CHECK, READ BACK FROM STATE, ONE TERM PER WRITE ----
        #
        # WHY THE v3.25.5 RESIDUAL COULD NOT FALSIFY ANYTHING. It was
        # `(self._current_holdings - _h_before) * arrival_price * qrate
        #  - (self._target_balance - _t_before)`. Substitute the two
        # writes and `arrival_price = u / (b * qrate)` and it expands to
        # `b * u / (b * qrate) * qrate - u`, which is identically zero
        # whenever the two scalar writes run, whatever they ran on. It
        # never read the lot at all. Measured: with a ledger whose
        # `append` silently drops the write, it reported
        # `delta_shift_usd = 1.8e-14` and `atomic = True` while
        # `main_lots_added` was 0 and the :574 invariant was False. A
        # residual that is zero by algebra is decoration.
        #
        # THAT PARTICULAR LEDGER IS NOW REFUSED UP FRONT -- see the
        # exact-list guard above -- so this check no longer has an
        # overridden `append` to catch. It is not decoration for that
        # reason: an exact `list` still cannot prove that the three
        # SCALAR writes landed, because `self` is not exact anything.
        # The verdict below re-reads all four destinations from the
        # object, so it measures what is there rather than what the
        # method meant to put there.
        #
        # ONE TERM PER WRITE, AND EACH TERM MEASURED AGAINST THE ARRIVAL
        # ITSELF -- NOT AGAINST ANOTHER WRITE.
        #
        # v3.25.6 built the verdict from three DIFFERENCES between
        # writes plus a readability flag, and a difference agrees when
        # NOTHING happens. Measured on that file, with the two scalar
        # stores dropped by a `__setattr__` and the ledger append
        # dropped by an overridden `append`: `delta_shift_usd` 0.0,
        # `ledger_gap_usd` 0.0, `anchor_gap_usd` 0.0, `atomic` True,
        # `main_lots_added` 0. It reported the arrival atomic on a run
        # where the arrival never landed. Every term it had could say
        # "the parts agree"; not one of them could say "the arrival is
        # here".
        #
        # So each of the four terms below is `<what that write moved>
        # minus <the arrival>`. Each is zero only when that specific
        # write moved by the observed arrival, and no combination of
        # missing writes cancels, because a missing write now has
        # nothing to be compared against except `u` itself.
        _units_after, _read_why = self._sum_lot_units(lots)
        _ledger_readable = _units_after is not None
        _units_seen = _units_before if _units_after is None else _units_after

        # THE THREE SCALARS ARE RE-READ, NOT ASSUMED. A `__setattr__`
        # that drops or rewrites a store is the one failure this method
        # cannot refuse in advance, and re-reading is what makes it
        # visible. Each falls back to its pre-arrival value when it
        # comes back unusable, so the arithmetic below stays total, and
        # `_state_readable` is what carries the failure into the
        # verdict instead.
        _h_seen, _h_why = self._finite_state_number(
            getattr(self, "_current_holdings", None), "_current_holdings")
        _t_seen, _t_why = self._finite_state_number(
            getattr(self, "_target_balance", None), "_target_balance")
        _a_seen, _a_why = self._finite_state_number(
            getattr(self, "_anchor_target_balance", None),
            "_anchor_target_balance")
        _state_readable = None not in (_h_seen, _t_seen, _a_seen)
        _state_read_why = _h_why or _t_why or _a_why
        _h_seen = _h_before if _h_seen is None else _h_seen
        _t_seen = _t_before if _t_seen is None else _t_seen
        _a_seen = _a_before if _a_seen is None else _a_seen

        # The lot the ledger actually accepted, in units then in USD.
        _lot_units_booked = _units_seen - _units_before
        _lot_usd_booked = _lot_units_booked * arrival_price * qrate

        # NAMED FOR THE SCALAR, SO SOURCED FROM THE SCALAR. v3.25.7 --
        # this term used to be computed from the LEDGER read-back, which
        # made `_delta_shift_usd` (the tick's own d(delta)) a statement
        # about `_main_lots` rather than about `_current_holdings`, and
        # `_current_holdings` is the quantity the tick actually prices
        # (:6783). The two agree on a healthy arrival and diverge on
        # exactly the runs the check exists for.
        _holdings_usd_added = ((_h_seen - _h_before)
                               * arrival_price * qrate)
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
            and abs(_anchor_gap_usd) <= _tol)

        # REPORTED, NOT RE-ASSERTED. Both of these are DERIVED from the
        # four terms above -- `_delta_shift_usd` is `_holdings_gap_usd -
        # _target_gap_usd`, and `_ledger_gap_usd` is `_lot_gap_usd -
        # _holdings_gap_usd` -- so putting either into the conjunction
        # would add no falsifying power. They are kept because they are
        # the two quantities an operator reads: how far the arrival
        # moved delta, and how far the ledger and the scalar drifted
        # apart over this one write. The :574 invariant is scoped to
        # THIS arrival rather than measured absolutely, because a bot
        # may already carry a gap from an earlier path and this method
        # reports on its own write, not on somebody else's.
        _delta_shift_usd = _holdings_usd_added - _target_usd_added
        _ledger_gap_units = ((_units_seen - _h_seen)
                             - (_units_before - _h_before))
        _ledger_gap_usd = _ledger_gap_units * arrival_price * qrate

        # BOTH BRANCHES SHOW THEIR WORK. v3.25.6 made the verdict
        # conditional and left the success branch a bare conclusion --
        # "both halves booked together, so the arrival is neither
        # scrummed nor chased" -- with no measured quantity in it
        # anywhere. Only the failure branch published numbers, so on the
        # runs an operator scans to confirm the mechanism is ALIVE, the
        # line asserted the conclusion and showed no evidence for it. A
        # line that says the check passed, on a run whose check was
        # never printed, is worse than no line: it is an audit record
        # that cannot be audited. The same four measurements now appear
        # on both branches; only the verdict word differs.
        _measured = (f"lot {_lot_units_booked:.10g} of {b:.10g} units, "
                     f"holdings ${_holdings_usd_added:+.6f}, target "
                     f"${_target_usd_added:+.6f}, anchor "
                     f"${_anchor_usd_added:+.6f}, each against an arrival "
                     f"of ${u:.6f}; ledger gap ${_ledger_gap_usd:+.6f}; "
                     f"tol ${_tol:g}")
        if not _ledger_readable:
            _measured = f"{_measured}; ledger unreadable: {_read_why}"
        if not _state_readable:
            _measured = f"{_measured}; state unreadable: {_state_read_why}"
        _verdict = (f"CHECKED [{_measured}] — both halves booked "
                    f"together, so the arrival is neither scrummed nor "
                    f"chased"
                    if _atomic_ok else
                    f"ARRIVAL NOT ATOMIC [{_measured}]")
        try:
            self._bus.emit(
                "bot.log", bot_id=_bot_id,
                message=(f"EXTRACTOR TRANCHE CONTAINED: +${u:.4f} from "
                         f"{src} ({b:.10g} "
                         f"{getattr(self.config, 'base_currency', '')} "
                         f"@ ${arrival_price:.8f}). Target ${_t_before:.2f} "
                         f"-> ${_t_seen:.2f}, uncapped. "
                         f"Holdings {_h_before:.8f} -> "
                         f"{_h_seen:.8f}. Delta shift "
                         f"${_delta_shift_usd:+.6f} — {_verdict}. "
                         f"ref={ref}"))
        except Exception as _log_exc:  # R28-OK: diagnostic best-effort
            logger.debug("Bot %s containment log line failed: %s",
                         _bot_id, _log_exc)

        try:
            from src.core.signal_contract import emit as _et_emit
            # Expectation 1: the target moved by EXACTLY the arrival. A
            # cap or a partial write breaks it.
            _et_emit("extractor.02.001.postcondition.tranche_contained",
                     actual=_target_usd_added,
                     expected=u,
                     context={"bot_id": _bot_id, "source": src,
                              "base_units": b,
                              "target_before": _t_before,
                              "target_after": _t_seen,
                              "ref": ref})
            # Expectation 2: all four writes landed, each measured
            # against the arrival. `actual` is the delta residual an
            # operator reads; `ok` carries the four per-write terms and
            # the two readability flags, so this record fails when ANY
            # write is missing -- including the run where they are ALL
            # missing, which every difference-based term reported as
            # zero.
            _et_emit("extractor.02.002.invariant.arrival_atomic",
                     actual=_delta_shift_usd,
                     expected=0.0,
                     ok=_atomic_ok,
                     context={"bot_id": _bot_id, "source": src,
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
                              "ref": ref})
        except Exception as _sup:  # noqa: BLE001,S110 - advisory
            logger.debug("suppressed in %s: %s: %s", "apply_extractor_tranche_return", type(_sup).__name__, _sup)

        # EVERY REPORTED BALANCE IS THE READ-BACK, NOT THE VALUE THIS
        # METHOD MEANT TO WRITE. Returning `_h_after` here would restate
        # the intention and hide the one failure the read-back exists to
        # expose; `_h_seen` is what the object actually holds now.
        return {"applied": True,
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
                "atomic": _atomic_ok}

    def _emit_trade_notification(self, role: str, stage: str,
                                 extra: str = "") -> None:
        """Emit a uniformly-formatted trade lifecycle notification.

        Operator directive 2026-04-25: "I also want a TRADE NOTIFICATION:
        FOLD: TICKER: SENT / PLACED / FILLED / CANCELLED in big red
        letters when a buy or sell signal is sent, confirmed, filled."

        Format:
            TRADE NOTIFICATION: <ROLE>: <SYMBOL>: <STAGE>[ — <extra>]

        StatusLog widget (main_window.py) detects the prefix and renders
        these in large bold colored font, color-coded by stage:
          SENT      → cyan       (decision made, about to call exchange)
          PLACED    → amber      (exchange acknowledged the order)
          FILLED    → green      (fill confirmed, accounting updated)
          CANCELLED → red        (gate refused or operator/exchange cancel)

        role: "SCRUM" | "FOLD" | "INITIAL"
              | "MANUAL_SCRUM" | "MANUAL_FOLD"           (operator-clicked)
              | "WIRE_STACK_SCRUM" | "WIRE_STACK_FOLD"   (v3.23.2 autonomous)
              | "CARTRIDGE_SCRUM" | "CARTRIDGE_FOLD"     (v3.23.2 autonomous)
              | "HEDGE" | "DIST" | etc.
        stage: "SENT" | "PLACED" | "FILLED" | "CANCELLED"
        """
        # v3.24.1 — sim_mode isolation. Fleet Replay uses real
        # ScrummingBot code against a fake exchange; without this
        # gate, every simulated fill emits "TRADE NOTIFICATION:"
        # on the shared bus, which the live main_window handler
        # (main_window.py:343) forwards to the sound engine. Sim
        # runs must be silent + fast (operator scan finding #3).
        # v3.24.62 (C22 / SN-54) — the `if _sim_mode: return` that used
        # to sit here is GONE.
        #
        # IT WAS DOING REAL WORK. Sim notifications reached the SHARED
        # bus, main_window forwarded them to the sound engine, and a
        # replay made noise. Removing it before C17 would have been a
        # regression, not a fix, which is why C22 was gated behind C17.
        #
        # WHAT CHANGED: C17 made the sim private-bus swap FAIL CLOSED
        # (see __init__). A sim bot now either holds a private EventBus
        # or is never constructed, so `self._bus.emit` below cannot
        # reach main_window's handler. Isolation comes from WHICH bus
        # the bot holds, not from refusing to emit — the same principle
        # the capital registry follows at :1170.
        #
        # WHAT IT COST: the SENT / PLACED / FILLED / CANCELLED trace,
        # including the CANCELLED reason string, is the only place a sim
        # run records WHY a trade did not fire. Skipping it removed the
        # feature instead of simulating it.
        #
        # Do not reinstate this guard to silence a noisy replay. Noise
        # would mean a sim bot is holding the LIVE bus, which is a
        # C17 isolation failure and must be fixed there.
        try:
            sym = self.config.symbol or self.config.target_asset
            msg = f"TRADE NOTIFICATION: {role}: {sym}: {stage}"
            if extra:
                msg += f" — {extra}"
            self._bus.emit("bot.log", bot_id=self.bot_id, message=msg)
        except Exception as _sup:  # R28-OK: notification failure must not break trade path
            logger.debug("suppressed in %s: %s: %s", "_emit_trade_notification", type(_sup).__name__, _sup)

    # ------------------------------------------------------------------
    # v3.16.53 — Per-tranche operator-initiated fold-back.
    # ------------------------------------------------------------------
    # Operator directive 2026-05-11:
    #   "Manual Fire buttons for the Fold Tranches is still not operational."
    #
    # Per-tranche Manual Fire is the operator-initiated bypass for the
    # auto-fold gate chain. The operator clicks Fire on a specific
    # tranche row; the bot:
    #   1. Validates index + that the tranche has parked USD
    #   2. Fetches current ticker
    #   3. Calls _execute_buy with path="manual_tranche_fire" — the
    #      MEM-251 v2 / MEM-253 v2 path handling lets this through
    #      Target-Delta gating (caller bounded by tranche.usd); Smart
    #      Ceiling and MEM-257 fail-closed still apply
    #   4. On success: adds rebought units to _main_lots preserving the
    #      tranche's initial_buy_price (MEM-171 compound protection),
    #      removes the tranche, recomputes _fold_queue_usd, bumps the
    #      lifetime-closed counter
    #   5. Emits bot.log + trade.filled for visibility
    #
    # Bypasses (per operator "manual fire bypasses everything"):
    #   - TA direction/confidence
    #   - BB midline / lower-DT
    #   - OTD per-tranche price gate (operator chose this tranche
    #     explicitly — assume operator knows what they want)
    #   - Target-Delta budget (path-specific relaxation in MEM-251 v2)
    #
    # Still enforced:
    #   - Smart Ceiling (Layer 2) — when enabled, refuses if projected
    #     position would exceed anchor × position_ceiling_multiple
    #   - MEM-257 fail-closed — phantom-zero / multi-base / fresh-
    #     balance verification
    #   - P0b stacked-order guard — refuses if an in-flight BUY exists
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
                return {"applied": False,
                        "reason": f"tranche_index must be int; got {tranche_index!r}"}
        if not (0 <= tranche_index < len(self._fold_tranches)):
            return {"applied": False,
                    "reason": (f"invalid tranche_index {tranche_index} "
                               f"(have {len(self._fold_tranches)} tranches)")}

        tranche = self._fold_tranches[tranche_index]
        cost = float(tranche.get("usd", 0) or 0)
        ibp = float(tranche.get("initial_buy_price",
                                 tranche.get("ref", 0)) or 0)
        if cost <= 0:
            return {"applied": False,
                    "reason": f"tranche #{tranche_index+1} has zero USD"}

        try:
            ticker = await self._get_ticker(self.config.symbol)
        except Exception as exc:
            return {"applied": False,
                    "reason": f"ticker fetch failed: {type(exc).__name__}: {exc}"}
        price = getattr(ticker, "last", 0) or 0
        if not price or price <= 0:
            return {"applied": False, "reason": "no valid price"}

        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"MANUAL TRANCHE FIRE: operator requested fold-back "
                     f"of tranche #{tranche_index+1} "
                     f"(usd ${cost:.4f}, ref ${tranche.get('ref', 0):.8f}, "
                     f"IBP ${ibp:.8f}) at current "
                     f"${price:.8f}. Bypasses TA/OTD/Target-Delta gates; "
                     f"Smart Ceiling + MEM-257 still apply."))

        # Minimal manual summary for _execute_buy's signature.
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
            trace_context={"path": "manual_tranche_fire",
                           "tranche_index": tranche_index,
                           "tranche_ref": str(tranche.get("ref", "")),
                           "tranche_ibp": str(ibp)})
        if fill_price is None or fill_price <= 0:
            return {"applied": False,
                    "reason": ("_execute_buy refused or failed (Smart "
                               "Ceiling / MEM-257 / P0b guard, or "
                               "exchange rejection); tranche unchanged")}

        # Post-fill: rebought units back to _main_lots preserving IBP
        rebought_units = cost / float(fill_price)

        # v3.24.52 (Phase 2 Step 8) — book the compound growth this fold
        # earned. Per-tranche Manual Fire filled a tranche and applied
        # ZERO target growth: it never called _apply_fold_target_growth,
        # so the operator's dominant dip path contributed nothing to
        # compounding no matter how far below ref it bought.
        #
        # Computed in the CASH frame, identical to the autonomous path.
        # For a single tranche the autonomous formula reduces to it:
        #   extra_asset  = cost x (1/fill - 1/ref)
        #   accum_profit = extra_asset x fill = cost x (1 - fill/ref)
        # Buying at ref yields 0; buying above ref yields a negative that
        # the helper floors at 0, so an unprofitable manual fold cannot
        # shrink the target.
        _mf_ref = float(tranche.get("ref", 0.0) or 0.0)
        _mf_profit = (
            float(cost) * (1.0 - float(fill_price) / _mf_ref)
            if _mf_ref > 0 else 0.0)
        try:
            _mf_growth = self._apply_fold_target_growth(
                _mf_profit, source="MANUAL_TRANCHE_FOLD")
        except Exception as _mf_exc:  # noqa: BLE001 - never fail a filled buy
            # The buy has already executed. A bookkeeping failure must
            # not raise back over a completed order.
            _mf_growth = 0.0
            logger.error(
                "manual tranche fold: target-growth booking FAILED after a "
                "filled buy on %s (%s); the fill stands, the growth was "
                "not applied", self.bot_id, _mf_exc)
        self._main_lots.append({
            "units": rebought_units,
            "initial_buy_price": ibp,
            "operator_initiated": True,
        })
        # Remove the tranche BY IDENTITY (index may have shifted in
        # the unlikely event of concurrent mutation; identity is safe).
        # v3.23.7 Anomaly C: gate the closed-counter bump on the actual
        # removal. The prior unconditional `+= 1` on the ValueError path
        # double-counted whenever the autonomous fold-back removed the
        # tranche between Manual Fire dispatch and post-fill — the live
        # RAVE bot reached closed=494 > created=444 via this race.
        _removed_ok = False
        try:
            self._fold_tranches.remove(tranche)
            _removed_ok = True
        except ValueError:
            # Tranche disappeared between dispatch and post-fill. Buy
            # already happened — log it but don't fail the operation.
            # v3.23.7 — DO NOT increment closed counter in this branch;
            # whoever actually removed the tranche owns the counter bump.
            logger.warning(
                "Bot %s manual_fire_tranche: tranche disappeared "
                "between dispatch and post-fill; lots updated, "
                "tranche cleanup skipped; closed-counter NOT bumped.",
                self.bot_id)
        self._fold_queue_usd = sum(
            float(t.get("usd", 0) or 0) for t in self._fold_tranches)
        if _removed_ok:
            try:
                self._tranches_closed_lifetime = int(
                    getattr(self, "_tranches_closed_lifetime", 0) or 0) + 1
            except Exception as _sup:  # R28-OK: counter probe; non-critical
                logger.debug("suppressed in %s: %s: %s", "manual_fire_tranche", type(_sup).__name__, _sup)

        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"MANUAL TRANCHE FIRE COMPLETE: tranche "
                     f"#{tranche_index+1} consumed. "
                     f"${cost:.4f} → {rebought_units:.6f} units @ "
                     f"${fill_price:.8f}, returned to main_lots with "
                     f"IBP ${ibp:.8f}. Fold queue now "
                     f"${self._fold_queue_usd:.4f} across "
                     f"{len(self._fold_tranches)} tranche(s)."))
        # v3.16.60 — PnL event for per-tranche Manual Fire (audit completeness).
        try:
            self._bus.emit("pnl.event", bot_id=self.bot_id, data={
                "kind": "FOLD",
                "asset": self.config.target_asset,
                "symbol": self.config.symbol,
                "units_rebought": float(rebought_units),
                "fill_price": float(fill_price),
                "usd_spent": float(cost) * float(
                    self._quote_to_usd or 1.0),
                "operator_initiated": True,
                "manual_kind": "MANUAL_TRANCHE_FOLD",
                "tranche_ibp": float(ibp),
                # v3.24.52 — this event carried no profit field at all,
                # so a manual fold was indistinguishable from a
                # zero-profit one in every downstream consumer.
                "accum_profit": float(_mf_profit),
                "growth_applied": float(_mf_growth),
            })
        except Exception as _sup:  # R28-OK: PnL telemetry best-effort
            logger.debug("suppressed in %s: %s: %s", "manual_fire_tranche", type(_sup).__name__, _sup)
        self._bus.emit("trade.filled", bot_id=self.bot_id, data={
            "type": "MANUAL_TRANCHE_FOLD",
            "side": "BUY",
            "amount": rebought_units,
            "price": fill_price,
            "usd": cost,
            "operator_initiated": True,
            # v3.24.52 — same omission as the pnl.event above.
            "accum_profit": float(_mf_profit),
            "growth_applied": float(_mf_growth),
        })
        # v3.23.11 — voting.log + gate.log snapshots at fire (D-NEW-A).
        self._emit_voting_panel_snapshot_at_fire(
            side="BUY", trade_action="MANUAL_TRANCHE_FOLD")
        self._emit_gate_decision_at_fire(
            side="BUY", trade_action="MANUAL_TRANCHE_FOLD")
        return {"applied": True,
                "tranche_index": tranche_index,
                "cost_usd": cost,
                "fill_price": float(fill_price),
                "units_returned": rebought_units,
                "remaining_tranches": len(self._fold_tranches)}

    def _add_wire_credits(self, tranche: dict, entries: list) -> None:
        """Append wire-credit provenance to a tranche, bounded.

        WHY THIS IS BOUNDED (v3.24.20)
        ==============================
        ``wire_credits`` grew without limit. Every wire-income event
        appends one entry to EVERY open tranche, so a bot with 27
        tranches records 27 entries per credit — growth is
        credits x tranches, not credits.

        Measured against the operator's live ``bot_state.json``
        (read-only) on 2026-08-04:

            file total                1,450,434 B
            wire_credits              377,851 B   = 26.1% of the file
            bot 7c4c4ff3              385,930 B, of which 96.0% is
                                      wire_credits (3,325 entries)

        The file had grown 35,640 B in the hours between the audit
        measuring it and this fix landing. ``bot_state.json`` is
        serialised on a 60 s timer, so this is real recurring I/O.

        The list is also WRITE-ONLY: grep finds appends at exactly two
        sites and zero readers anywhere in the tree.

        WHY NOT JUST DELETE IT
        ======================
        These entries are money provenance -- which source funded which
        tranche, and when. Nothing reads them today, but discarding the
        record outright would lose the audit trail for funds that moved.
        So detail is capped at the most recent ``_WIRE_CREDIT_CAP``
        entries and everything older is folded into a running aggregate
        (``wire_credits_rolled``) that preserves the totals exactly:
        count, total USD, and USD per source. No credited dollar
        disappears from the record; only per-event granularity is aged
        out.
        """
        if entries:
            tranche.setdefault("wire_credits", []).extend(entries)
        _roll_wire_credit_overflow(tranche)

    def _compact_wire_credits(self) -> int:
        """Fold already-oversized tranches down on state restore.

        Without this a bot that already carries thousands of entries
        would keep re-serialising them forever: the cap in
        ``_add_wire_credits`` only engages on the next append, and a
        tranche that never receives another credit would never compact.

        Returns the number of detail entries rolled into the aggregate.
        """
        rolled = 0
        for t in getattr(self, "_fold_tranches", None) or []:
            rolled += _roll_wire_credit_overflow(t)
        return rolled

    def _absorb_pending_wire_credits_into(self, new_tranche: dict) -> float:
        """Merge `_pending_wire_credits` into a freshly-formed tranche.

        Called from `_execute_sell` at the tranche-append site (P1b
        Session 26). If the pending bucket has usd > 0, the new
        tranche's `usd` grows by that amount, the bucket clears, and
        the ledger entries become this tranche's `wire_credits`
        provenance.

        The deposit is EXEMPT from `scrum_fold_pct`. This method adds
        USD and NO units, and the fold-fraction block a few lines below
        the call site uses exactly that to tell the two apart: it prices
        each new tranche's units at the scrum's own net rate and scales
        only that part, so wired-in money reaches the fold queue at full
        value on a bot folding less than 100%. See the comment at that
        block for the measurement, and for why the `wire_credits`
        provenance written here is NOT the number it trusts.

        Returns the absorbed amount (for logging).
        """
        pending = float(self._pending_wire_credits or 0.0)
        if pending <= 0:
            return 0.0
        new_tranche["usd"] = float(new_tranche.get("usd", 0) or 0) + pending
        self._add_wire_credits(new_tranche, list(self._pending_wire_ledger))
        self._pending_wire_credits = 0.0
        self._pending_wire_ledger = []
        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"WIRE ABSORB: ${pending:.4f} pending wire credits "
                     f"absorbed into new tranche (usd now "
                     f"${new_tranche['usd']:.4f}). Pending cleared."))
        logger.info("Bot %s absorbed %.4f pending wire credits into new tranche",
                    self.bot_id, pending)
        return pending

    def update_phantom_config(
        self,
        enable_phantoms: Optional[bool] = None,
        phantom_timeframes: Optional[list[str]] = None,
        lock_candle_count: Optional[int] = None,
    ) -> dict:
        """Live-update phantom configuration. Called by the live-settings
        dialog (MEM-232) to apply Phantom Bot tab changes without a
        restart.

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
                    "restart.")
            if not was_enabled and self._phantoms_enabled and not self._phantoms_started:
                caveats.append(
                    "Phantoms will start on next tick.")

        if phantom_timeframes is not None:
            # Apply MEM-203 filter at update time too, consistent with __init__.
            _EXCHANGE_UNSUPPORTED_TFS = {
                "coinbase": {"4h", "2h", "30m", "1m"},
            }
            _unsupported = _EXCHANGE_UNSUPPORTED_TFS.get(
                self.config.exchange_id.lower(), set())
            filtered = [tf for tf in phantom_timeframes if tf not in _unsupported]
            if list(filtered) != list(self._phantom_timeframes):
                self._phantom_timeframes = list(filtered)
                applied["phantom_timeframes"] = list(filtered)
                if self._phantoms_started:
                    caveats.append(
                        "TF set updated; already-started phantoms keep "
                        "their original TFs until bot restart.")
                if _unsupported and any(
                        tf in _unsupported for tf in phantom_timeframes):
                    dropped = [tf for tf in phantom_timeframes
                               if tf in _unsupported]
                    caveats.append(
                        f"Dropped unsupported TFs for "
                        f"{self.config.exchange_id}: {dropped}.")

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

    # MEM-236 — expose scrum SEARCH/TRACK/FIRE phase for GUI consumption.
    # The GUI reads this to pace tracking beeps: silent in SEARCH, slow
    # beeps in TRACK, fast beeps in FIRE.
    @property
    def scrum_target_mode(self) -> str:
        return self._scrum_target_mode

    # ------------------------------------------------------------------
    # v3.16.17 (P0d) — Coalesced ticker fetch
    # ------------------------------------------------------------------
    async def _get_ticker(self, symbol: Optional[str] = None):
        """Fetch a ticker through the shared MarketDataPool when wired,
        else fall back to a direct ``self.exchange.get_ticker`` call.

        The pool path is the CCXTQueueFullError mitigation (P0d): N
        bots on the same exchange + same symbol now share a single
        ticker fetch per 5s TTL window, instead of each bot firing
        its own request and saturating the per-connector queue cap.
        Unregistered symbols (USD-conversion lookups, etc.) are also
        coalesced — the pool creates the entry on first access.

        Falls back to a direct fetch when ``self._data_pool`` is
        unset (test harnesses, paper-trading without a manager).
        """
        if symbol is None:
            symbol = self.config.symbol
        if self._data_pool is not None:
            try:
                return await self._data_pool.get_or_fetch_ticker(
                    self.exchange, self.config.exchange_id, symbol)
            except Exception:
                # Pool layer threw something other than a coalesced
                # CCXTQueueFullError (e.g., the underlying connector
                # raised). Re-raise unchanged so the caller's existing
                # try/except handling (and retry semantics) fire as
                # they did pre-coalescing.
                raise
        return await self.exchange.get_ticker(symbol)

    # ------------------------------------------------------------------
    # v3.23.74 — Coalesced OHLCV fetch (mirror of _get_ticker)
    # ------------------------------------------------------------------
    async def _get_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 100,
    ) -> list:
        """Fetch OHLCV through the shared MarketDataPool when wired,
        else fall back to a direct exchange call.

        Bots on the same (exchange, symbol, timeframe) now share ONE
        candle fetch per TF-matched TTL window (5m → 300s, 1h →
        3600s, etc). Before v3.23.74 this went straight to
        self.exchange.get_ohlcv on every action tick — the biggest
        single contributor to the CPM saturation the operator flagged
        on 2026-07-31.
        """
        if self._data_pool is not None:
            try:
                return await self._data_pool.get_or_fetch_ohlcv(
                    self.exchange, self.config.exchange_id,
                    symbol, timeframe, limit=limit)
            except Exception:
                raise
        return await self.exchange.get_ohlcv(
            symbol, timeframe, limit=limit)

    # ------------------------------------------------------------------
    # v3.23.76 — Coalesced balance fetch (mirror of _get_ticker /
    # _get_ohlcv). ScrummingBot calls exchange.get_balance() at 9+
    # sites per action tick; coalescing at the pool cuts that to
    # one API call per (exchange, currency) per 10s window.
    # ------------------------------------------------------------------
    async def _get_balance(self, currency: str):
        """Fetch a balance through the shared MarketDataPool when
        wired, else fall back to a direct exchange call. Callers
        that mutate the balance (post-trade paths) should also call
        ``_invalidate_balance(currency)`` so the next read reflects
        the change immediately."""
        if self._data_pool is not None:
            try:
                return await self._data_pool.get_or_fetch_balance(
                    self.exchange, self.config.exchange_id, currency)
            except Exception:
                raise
        # v3.23.96: FIX — must call self.exchange.get_balance() here,
        # NOT self._get_balance(). Prior v3.23.76 global replace of
        # `self.exchange.get_balance(` → `self._get_balance(` ate its
        # own tail inside this fallback path, creating infinite self-
        # recursion. Live bots never hit it (pool wired → early
        # return above); sim bots hit it every tick and blew up with
        # RecursionError — operator caught it on Start Replay 2026-08-01.
        return await self.exchange.get_balance(currency)

    def _invalidate_balance(
        self, currency: Optional[str] = None,
    ) -> None:
        """Force the next _get_balance for this (exchange, currency)
        to re-fetch from the connector. Fire from post-trade paths
        so the freshly-adjusted balance is visible to the next
        gate/reconciliation call within the tick."""
        if self._data_pool is None:
            return
        try:
            self._data_pool.invalidate_balance(
                self.config.exchange_id, currency)
        except Exception as _inv_exc:  # noqa: BLE001 - best-effort
            logger.debug(
                "Bot %s balance invalidate failed: %s",
                self.bot_id, _inv_exc)

    # ------------------------------------------------------------------
    # v3.15.55 — quote→USD conversion (operator directive 2026-04-25)
    # ------------------------------------------------------------------
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

        sadp: R28 (surface failure) R29 (cache, don't drift)
        """
        quote = self.config.symbol.split("/")[-1].upper()
        if is_usd_stable_quote(quote):
            self._quote_to_usd = 1.0
            return 1.0
        # Throttle fetches to once every 30 seconds.
        now = time.time()
        if (now - self._quote_to_usd_last_fetch) < 30.0 and self._quote_to_usd > 0:
            return self._quote_to_usd
        try:
            usd_ticker = await self._get_ticker(f"{quote}/USD")
            rate = float(getattr(usd_ticker, "last", 0) or 0)
            if rate > 0:
                self._quote_to_usd = rate
                self._quote_to_usd_last_fetch = now
                # Reset the warning latch on successful fetch so a
                # later outage will warn again.
                self._quote_to_usd_warned = False
                return rate
        except Exception as exc:
            if not self._quote_to_usd_warned:
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id,
                    message=(
                        f"QUOTE→USD: failed to fetch {quote}/USD rate "
                        f"({type(exc).__name__}: {exc}). Falling back to "
                        f"cached rate {self._quote_to_usd:.4f}. Target "
                        f"Balance evaluation may be off until a successful "
                        f"refresh."))
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

    # ------------------------------------------------------------------
    # v3.15.58 — Circuit Breakers (operator directive 2026-04-25)
    # ------------------------------------------------------------------
    def _check_circuit_breakers(self, candles) -> bool:
        """Evaluate the most recent candle for circuit-breaker triggers.

        Operator directive 2026-04-25 (verbatim):
          "Soft Circuit Breaker is a time delay. Triggered by user set
           threshold. Default is 25%. Any single candle move =>25% will
           interrupt any trade on that side of the market. Subsequent TA
           evaluation on next x# of candles required before Circuit
           Breaker opens again.
           Hard Circuit Breaker is only user reset and causes the bot to
           PAUSE. Default is 35%. Any single candle move =>35%
           interrupts all trades and pauses the bot."

        Single-candle move % = ``(high - low) / open × 100``. The
        DIRECTION (which side gets interrupted) is inferred from
        ``close vs open``: close >= open → "up" → SCRUM side gets
        interrupted (don't sell into a pump); close < open → "down"
        → FOLD side gets interrupted (don't buy a falling knife).

        State machine:
          Hard tripped → bot transitions to ``BotState.PAUSED``.
            Operator reset required via ``reset_circuit_breaker()``.
          Soft tripped → ``_cb_soft_active_side`` set to "scrum" or
            "fold". Cooldown counter set to
            ``config.circuit_breaker_cooldown_candles``. Each
            subsequent fresh candle decrements it; soft re-opens when
            counter hits 0.

        Returns True if either breaker is currently blocking trades
        on either side, False otherwise. The SCRUM/FOLD gates use the
        per-side state directly; the bool here is a quick overall
        check.

        sadp: R28 (surface) R29 (idempotent — same candle never
        double-trips)
        """
        if not candles:
            return self._cb_hard_tripped or self._cb_soft_active_side is not None
        candle = candles[-1]
        try:
            o = float(candle.open)
            h = float(candle.high)
            l = float(candle.low)
            c = float(candle.close)
        except (TypeError, ValueError, AttributeError):
            return self._cb_hard_tripped or self._cb_soft_active_side is not None
        if o <= 0:
            return self._cb_hard_tripped or self._cb_soft_active_side is not None

        # Idempotency: skip if this candle was already evaluated.
        ts = float(getattr(candle, "timestamp", 0) or 0)
        already_seen = (ts > 0 and ts == self._cb_last_candle_ts)
        if not already_seen and ts > 0:
            self._cb_last_candle_ts = ts

        move_pct = (h - l) / o * 100.0
        _move_abs = h - l          # same threshold, expressed in price
        direction = "up" if c >= o else "down"

        hard_pct = float(getattr(self.config, "circuit_breaker_hard_pct", 35.0))
        soft_pct = float(getattr(self.config, "circuit_breaker_soft_pct", 25.0))

        # --- Hard breaker (highest priority) ---
        # Only trip on a fresh candle and not already tripped.
        if (not already_seen and not self._cb_hard_tripped
                and hard_pct > 0 and _move_abs >= hard_pct / 100.0 * o):
            self._cb_hard_tripped = True
            self._cb_hard_tripped_at = time.time()
            self._cb_hard_trip_pct = move_pct
            try:
                self.state = BotState.PAUSED
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "_check_circuit_breakers", type(_sup).__name__, _sup)
            self._bus.emit(
                "bot.log", bot_id=self.bot_id,
                message=(
                    f"HARD CIRCUIT BREAKER TRIPPED: single-candle move "
                    f"{move_pct:.2f}% ≥ hard threshold {hard_pct:.2f}% "
                    f"(direction={direction}, OHLC: ${o:.8f}/${h:.8f}/"
                    f"${l:.8f}/${c:.8f}). Bot PAUSED — operator reset "
                    f"required. All trade paths interrupted."))
            try:
                self._emit_trade_notification(
                    "ALL", "CANCELLED",
                    f"HARD breaker @ {move_pct:.2f}% (≥ {hard_pct:.2f}%)")
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "_check_circuit_breakers", type(_sup).__name__, _sup)
            return True

        # If hard is already tripped, all gates remain closed.
        if self._cb_hard_tripped:
            return True

        # --- Soft breaker cooldown decrement on each fresh candle ---
        if (not already_seen and self._cb_soft_active_side is not None
                and self._cb_soft_cooldown_remaining > 0):
            self._cb_soft_cooldown_remaining -= 1
            if self._cb_soft_cooldown_remaining <= 0:
                old_side = self._cb_soft_active_side
                self._cb_soft_active_side = None
                self._cb_soft_trip_pct = 0.0
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id,
                    message=(
                        f"SOFT CIRCUIT BREAKER RESET: cooldown elapsed; "
                        f"{old_side.upper()} side re-opens. Normal trade "
                        f"flow resumed."))

        # --- Soft breaker check ---
        # Only trip on a fresh candle, not already soft-tripped.
        if (not already_seen and self._cb_soft_active_side is None
                and soft_pct > 0 and _move_abs >= soft_pct / 100.0 * o):
            side = "scrum" if direction == "up" else "fold"
            cooldown = max(1, int(getattr(
                self.config, "circuit_breaker_cooldown_candles", 3) or 3))
            self._cb_soft_active_side = side
            self._cb_soft_cooldown_remaining = cooldown
            self._cb_soft_tripped_at = time.time()
            self._cb_soft_trip_pct = move_pct
            self._bus.emit(
                "bot.log", bot_id=self.bot_id,
                message=(
                    f"SOFT CIRCUIT BREAKER TRIPPED: single-candle move "
                    f"{move_pct:.2f}% ≥ soft threshold {soft_pct:.2f}% "
                    f"(direction={direction}, side={side.upper()}). "
                    f"Cooldown: {cooldown} candles before re-open. "
                    f"OHLC: ${o:.8f}/${h:.8f}/${l:.8f}/${c:.8f}."))
            try:
                self._emit_trade_notification(
                    side.upper(), "CANCELLED",
                    f"SOFT breaker @ {move_pct:.2f}% on {side.upper()} side")
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "_check_circuit_breakers", type(_sup).__name__, _sup)
            return True

        return self._cb_hard_tripped or self._cb_soft_active_side is not None

    async def self_destruct(
        self, confirmation_token: str = "",
        keep_running: bool = False,
    ) -> dict:
        """v3.15.62 — Aggressive full-position exit (operator directive
        2026-04-26: "Bots will now have a self-destruct button under
        the details panel. This will aggressively exit the entire
        position when activated.").

        BEHAVIOR:
          1. Validate ``confirmation_token`` literally equals
             ``"SELF-DESTRUCT"`` — guards against accidental call.
             Returns refused dict if missing/wrong.
          2. Fetch current holdings fresh from the exchange.
          3. Market-SELL the entire holdings via ``guarded_place_order``
             (same trade path as Manual Fire — bypasses every auto
             gate including BB Detection Threshold, hysteresis,
             Circuit Breakers, Higher-TF bias, since this is operator-
             initiated rapid exit).
          4. Update internal state: clear ``_main_lots`` and
             ``_fold_tranches``, zero ``_current_holdings``.
          5. Transition bot to ``BotState.PAUSED`` (default) so it
             doesn't immediately try to re-enter on next tick. Set
             ``keep_running=True`` to leave it RUNNING (operator can
             let the bot re-accumulate from zero).
          6. Emit a ``trade.filled`` event with ``role="SELF_DESTRUCT"``
             so the v3.15.59 History tab attributes the action.

        Returns dict:
            {"ok": bool, "reason": str, "sold_qty": float,
             "sold_usd": float, "fill_price": float}

        sadp: R28 (surface fully) R29 (idempotent — repeated call is safe
        after holdings hit zero). Always non-raising (failures returned
        as ``ok=False`` for the GUI button to surface).
        """
        if confirmation_token != "SELF-DESTRUCT":  # noqa: S105  # nosec B105
            # v3.15.91 (F2 fix from 2026-04-26 silent-result-dict
            # audit): operator-visible emit on the entry-guard refusal.
            # Pre-fix this branch returned the dict but emitted no
            # bot.log — the GUI button consumed `ok`/`reason` and showed
            # a toast, but if the operator's bottom-sheet was closed or
            # they pressed-and-walked-away, the refusal left no event-
            # bus / log trail. R71 SSS compliance.
            try:
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id,
                    message=("SELF-DESTRUCT REFUSED (entry guard): "
                             "confirmation_token must equal "
                             "'SELF-DESTRUCT' (case-sensitive). "
                             "No state changed."))
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)
            return {
                "ok": False,
                "reason": ("self_destruct refused: confirmation_token "
                           "must equal 'SELF-DESTRUCT' (case-sensitive)"),
                "sold_qty": 0.0, "sold_usd": 0.0, "fill_price": 0.0,
            }

        try:
            self._bus.emit(
                "bot.log", bot_id=self.bot_id,
                message=("SELF-DESTRUCT armed. Querying exchange for "
                         "current holdings before market-sell..."))
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)

        # 1. Fresh holdings read
        try:
            bal = await self._get_balance(self.config.target_asset)
            units = float(getattr(bal, "total", 0) or bal.free or 0)
        except Exception as exc:
            # v3.15.91 (F2 fix): operator-visible emit on balance-fetch
            # failure during SELF-DESTRUCT entry. Pre-fix this branch
            # returned the dict silently — operator could miss why a
            # SELF-DESTRUCT they pressed didn't actually fire.
            try:
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id,
                    message=(f"SELF-DESTRUCT REFUSED (balance fetch): "
                             f"exchange.get_balance("
                             f"{self.config.target_asset!r}) raised "
                             f"{type(exc).__name__}: {exc}. State "
                             f"unchanged. Retry when exchange is "
                             f"reachable."))
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)
            return {
                "ok": False,
                "reason": (f"self_destruct refused: balance fetch "
                           f"raised {type(exc).__name__}: {exc}"),
                "sold_qty": 0.0, "sold_usd": 0.0, "fill_price": 0.0,
            }

        if units <= 0:
            # Nothing to sell — clean up internal state anyway and pause.
            self._main_lots = []
            # v3.23.7 Anomaly C: SELF_DESTRUCT discharges every queued
            # tranche by clearing the list. Each cleared tranche IS a
            # closed cycle (sold via the no-holdings cleanup), so bump
            # the closed-counter by the pre-clear queue size. Previously
            # this path silently dropped tranches without counter bumps,
            # leaving created > closed asymmetric on the disk-persisted
            # state. Explicit-but-zero bump (queue size may be 0) makes
            # the accounting visible.
            try:
                self._tranches_closed_lifetime = int(
                    getattr(self, "_tranches_closed_lifetime", 0) or 0
                ) + len(self._fold_tranches)
            except Exception as _sup:  # R28-OK: counter probe; non-critical
                logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)
            self._fold_tranches = []
            self._fold_queue_usd = 0.0
            self._current_holdings = 0.0
            try:
                if not keep_running:
                    self.state = BotState.PAUSED
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)
            try:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=("SELF-DESTRUCT: exchange holdings already 0. "
                             "State cleared; bot " +
                             ("PAUSED" if not keep_running else "kept RUNNING") +
                             "."))
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)
            return {
                "ok": True, "reason": "no holdings to sell",
                "sold_qty": 0.0, "sold_usd": 0.0, "fill_price": 0.0,
            }

        # 2. Get current ticker for fill_price reference
        try:
            ticker = await self._get_ticker(self.config.symbol)
            ref_price = float(ticker.last)
        except Exception:  # R28-OK: ticker probe; last_trade_price is the documented fallback
            ref_price = float(self._last_trade_price or 0)

        # 3. Market sell entire holdings
        from ..exchange.base import OrderSide, OrderType
        try:
            self._bus.emit(
                "bot.log", bot_id=self.bot_id,
                message=(f"SELF-DESTRUCT FIRING: market-sell {units:.8f} "
                         f"{self.config.target_asset} (~${units * ref_price:.2f}) "
                         f"on {self.config.symbol}. All auto gates bypassed."))
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)
        try:
            self._emit_trade_notification(
                "SELF_DESTRUCT", "SENT",
                f"{units:.6f} {self.config.target_asset}")
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)

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
                    "bot.log", bot_id=self.bot_id,
                    message=(f"SELF-DESTRUCT FAILED: order raised "
                             f"{type(exc).__name__}: {exc}. State "
                             f"NOT cleared — operator must investigate."))
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)
            return {
                "ok": False,
                "reason": f"order raised: {type(exc).__name__}: {exc}",
                "sold_qty": 0.0, "sold_usd": 0.0, "fill_price": 0.0,
            }

        if order is None:
            try:
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id,
                    message=("SELF-DESTRUCT FAILED: exchange returned no "
                             "order. State NOT cleared."))
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)
            return {
                "ok": False, "reason": "exchange returned no order",
                "sold_qty": 0.0, "sold_usd": 0.0, "fill_price": 0.0,
            }

        # 4. Pull fill details
        fill_amount = float(
            getattr(order, "filled", None)
            or getattr(order, "amount", None)
            or units)
        fill_price = float(
            getattr(order, "average_price", None)
            or getattr(order, "average", None)
            or getattr(order, "price", None)
            or ref_price)
        fill_usd = fill_amount * fill_price * float(self._quote_to_usd or 1.0)

        # 5. Clear internal state
        self._main_lots = []
        # v3.23.7 Anomaly C: SELF_DESTRUCT successfully discharged every
        # queued tranche via the market sell. Each cleared tranche IS a
        # closed cycle, so bump the closed-counter by the pre-clear
        # queue size before clearing. Previously this path silently
        # dropped tranches without counter bumps. Explicit-but-zero bump
        # (queue size may be 0) makes the accounting visible.
        try:
            self._tranches_closed_lifetime = int(
                getattr(self, "_tranches_closed_lifetime", 0) or 0
            ) + len(self._fold_tranches)
        except Exception as _sup:  # R28-OK: counter probe; non-critical
            logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)
        self._fold_tranches = []
        self._fold_queue_usd = 0.0
        self._current_holdings = max(0.0, self._current_holdings - fill_amount)
        self._last_trade_side = "SCRUM"
        self._last_trade_price = fill_price
        # v3.15.77 — disarm both opposing-hysteresis gates; the next
        # tick re-arms when delta drifts opposing.
        self._reset_opposing_hysteresis_after_fill()
        try:
            self.stats.total_scrummed_usd += fill_usd
            # v3.23.65 SWOS retention counter (manual scrum path).
            self.note_scrum_retention_usd(fill_usd)
            self.stats.total_trades += 1
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)

        # 6. Pause unless operator asked to keep running
        try:
            if not keep_running:
                self.state = BotState.PAUSED
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)

        # 7. Emit trade.filled with the new SELF_DESTRUCT role so the
        # v3.15.59 History tab attributes this correctly.
        try:
            self._bus.emit(
                "trade.filled", bot_id=self.bot_id, data={
                    "type": "SELF_DESTRUCT",
                    "side": "SELL",
                    "amount": fill_amount,
                    "price": fill_price,
                    "usd": fill_usd,
                    "profit": 0.0,
                    "operator_initiated": True,
                    "symbol": self.config.symbol,
                    "exchange": self.config.exchange_id,
                })
            # v3.23.11 — voting.log + gate.log snapshots at fire (D-NEW-A).
            self._emit_voting_panel_snapshot_at_fire(
                side="SELL", trade_action="SELF_DESTRUCT")
            self._emit_gate_decision_at_fire(
                side="SELL", trade_action="SELF_DESTRUCT")
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)
        try:
            self._emit_trade_notification(
                "SELF_DESTRUCT", "FILLED",
                f"{fill_amount:.6f} @ ${fill_price:.8f} = ${fill_usd:.2f}")
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)
        try:
            self._bus.emit(
                "bot.log", bot_id=self.bot_id,
                message=(f"SELF-DESTRUCT COMPLETE: sold {fill_amount:.8f} "
                         f"@ ${fill_price:.8f} = ${fill_usd:.2f}. "
                         f"Internal state cleared. Bot " +
                         ("PAUSED" if not keep_running else "kept RUNNING") +
                         "."))
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "self_destruct", type(_sup).__name__, _sup)

        return {
            "ok": True, "reason": "self-destruct complete",
            "sold_qty": fill_amount, "sold_usd": fill_usd,
            "fill_price": fill_price,
        }

    def reset_circuit_breaker(self, scope: str = "all") -> dict:
        """Operator-initiated circuit breaker reset.

        Operator directive 2026-04-25: "Hard Circuit Breaker is only
        user reset". The soft breaker self-resets on cooldown elapse;
        an explicit operator override via this method clears it
        immediately. Hard breaker REQUIRES this call to clear.

        Args:
            scope: 'all' (clear both), 'soft' (clear soft only), or
                'hard' (clear hard only and resume bot if PAUSED).

        Returns:
            dict with 'applied' (list of human-readable strings) and
            'scope'. Always non-raising — fail-soft for GUI buttons.
        """
        applied: list[str] = []
        scope_norm = (scope or "all").lower()
        if scope_norm not in ("all", "soft", "hard"):
            scope_norm = "all"

        if scope_norm in ("all", "soft") and self._cb_soft_active_side is not None:
            old_side = self._cb_soft_active_side
            old_pct = self._cb_soft_trip_pct
            self._cb_soft_active_side = None
            self._cb_soft_cooldown_remaining = 0
            self._cb_soft_trip_pct = 0.0
            self._cb_soft_tripped_at = 0.0
            applied.append(
                f"soft breaker cleared (was {old_side.upper()} "
                f"@ {old_pct:.2f}%)")

        if scope_norm in ("all", "hard") and self._cb_hard_tripped:
            old_pct = self._cb_hard_trip_pct
            self._cb_hard_tripped = False
            self._cb_hard_tripped_at = 0.0
            self._cb_hard_trip_pct = 0.0
            try:
                if self.state == BotState.PAUSED:
                    self.state = BotState.RUNNING
                    applied.append("bot resumed from PAUSED → RUNNING")
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "reset_circuit_breaker", type(_sup).__name__, _sup)
            applied.append(f"hard breaker cleared (was @ {old_pct:.2f}%)")

        msg_tail = ("; ".join(applied)
                    if applied else "no circuit breakers active")
        try:
            self._bus.emit(
                "bot.log", bot_id=self.bot_id,
                message=f"CIRCUIT BREAKER RESET ({scope_norm}): {msg_tail}")
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "reset_circuit_breaker", type(_sup).__name__, _sup)
        return {"applied": applied, "scope": scope_norm}

    def _bb_detect_thresholds(self) -> tuple[float, float]:
        """v3.15.57 — Return ``(lower_detect, upper_detect)`` thresholds
        in ``bb_pos`` terms based on ``config.scrum_detect_pct``.

        Operator directive 2026-04-25:
          "Scrums cannot occur below the Upper BB Detection Threshold
           and Folds cannot occur above the Lower BB Detection Threshold."

        Translation (with the codebase's ``bb_pos`` convention where
        0.0 = at lower band, 0.5 = midline, 1.0 = at upper band):

          • SCRUM (sell) requires ``bb_pos >= upper_detect``
          • FOLD (buy) requires ``bb_pos <= lower_detect``

        ``scrum_detect_pct`` is "percent distance from midline to band"
        — the same parameter the existing scrum state machine uses for
        SEARCH→TRACK transitions. A value of 75 → detect_frac=0.75 →
        upper_detect = 0.5 + 0.375 = 0.875 and lower_detect = 0.125.

        This rule is a HARD GATE: it sits AFTER the existing
        target_fires / fold_ok_midline / MEM-187 BB Bullseye / MEM-196
        RIPE-HARVEST overrides and CANNOT be bypassed by them. Manual
        fire bypasses naturally because manual fire does not traverse
        the auto-scrum/auto-fold gate logic.
        """
        # Use a sentinel default (None means missing) so a legitimate 0
        # value isn't silently coerced to 75 by `or` truthiness.
        _raw = getattr(self.config, "scrum_detect_pct", None)
        try:
            detect_pct = float(_raw) if _raw is not None else 75.0
        except (TypeError, ValueError):
            detect_pct = 75.0
        detect_frac = max(0.0, min(1.0, detect_pct / 100.0))
        half = detect_frac * 0.5
        return (0.5 - half, 0.5 + half)

    def _update_opposing_hysteresis_state(
            self, delta: float, current_price: float) -> None:
        """v3.15.77 — Per-tick update of conditional opposing-direction
        hysteresis arm/disarm state.

        Operator directive 2026-04-27:
          "The opposing trade distance should not activate after one
           trade. The opposing directional movement should be confirmed
           first i.e. once the Target Delta begins drifting negative
           from the most recent Scrum. If the Target Delta goes
           positive again, it can deactivate."

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

        Pre-fix (v3.15.52) used `_last_trade_price` as the reference
        and was always-on after a trade. The new model is strictly
        less aggressive — fewer false refusals — but still preserves
        the operator's invariant that opposite trades require a
        meaningful price-move once the bot is actually approaching
        an opposing-direction trade.

        sadp: R28 R44 R55
        """
        try:
            _px = float(current_price)
        except (TypeError, ValueError):
            return
        if _px <= 0:
            return

        if self._last_trade_side == "SCRUM":
            # FOLD-side gate tracks delta crossing into negative.
            if delta < 0:
                if not self._hyst_armed_fold_side:
                    self._hyst_armed_fold_side = True
                    self._hyst_ref_fold_side = _px
                    try:
                        _interval = float(
                            self.config.scrumming_interval_pct or 0)
                    except (TypeError, ValueError):
                        _interval = 0.0
                    self._bus.emit(
                        "bot.log", bot_id=self.bot_id,
                        message=(
                            f"FOLD-side hysteresis ARMED: target delta "
                            f"crossed negative after recent SCRUM. "
                            f"Pivot ref = ${_px:.8f}. FOLD now requires "
                            f"price drop of {_interval:.2f}% + fee from "
                            f"this pivot."))
            else:
                if self._hyst_armed_fold_side:
                    self._hyst_armed_fold_side = False
                    self._hyst_ref_fold_side = 0.0
                    self._bus.emit(
                        "bot.log", bot_id=self.bot_id,
                        message=(
                            f"FOLD-side hysteresis DISARMED: target "
                            f"delta returned non-negative. Gate cleared "
                            f"until delta drifts negative again."))
            # SCRUM-side is irrelevant when last trade was SCRUM.
            if self._hyst_armed_scrum_side:
                self._hyst_armed_scrum_side = False
                self._hyst_ref_scrum_side = 0.0
        elif self._last_trade_side == "FOLD":
            # SCRUM-side gate tracks delta crossing into positive.
            if delta > 0:
                if not self._hyst_armed_scrum_side:
                    self._hyst_armed_scrum_side = True
                    self._hyst_ref_scrum_side = _px
                    try:
                        _interval = float(
                            self.config.scrumming_interval_pct or 0)
                    except (TypeError, ValueError):
                        _interval = 0.0
                    self._bus.emit(
                        "bot.log", bot_id=self.bot_id,
                        message=(
                            f"SCRUM-side hysteresis ARMED: target delta "
                            f"crossed positive after recent FOLD. "
                            f"Pivot ref = ${_px:.8f}. SCRUM now requires "
                            f"price rise of {_interval:.2f}% + fee from "
                            f"this pivot."))
            else:
                if self._hyst_armed_scrum_side:
                    self._hyst_armed_scrum_side = False
                    self._hyst_ref_scrum_side = 0.0
                    self._bus.emit(
                        "bot.log", bot_id=self.bot_id,
                        message=(
                            f"SCRUM-side hysteresis DISARMED: target "
                            f"delta returned non-positive. Gate cleared "
                            f"until delta drifts positive again."))
            # FOLD-side is irrelevant when last trade was FOLD.
            if self._hyst_armed_fold_side:
                self._hyst_armed_fold_side = False
                self._hyst_ref_fold_side = 0.0
        else:
            # No prior trade — both gates idle.
            self._hyst_armed_fold_side = False
            self._hyst_armed_scrum_side = False
            self._hyst_ref_fold_side = 0.0
            self._hyst_ref_scrum_side = 0.0

    def _reset_opposing_hysteresis_after_fill(self) -> None:
        """v3.15.77 — Called by every site that sets ``_last_trade_side``
        after a fresh fill. Resets both opposing-direction hysteresis
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
        return float(self._current_holdings) * float(price) * float(self._quote_to_usd or 1.0)

    @property
    def armed_action(self) -> Optional[str]:
        """MEM-241 — What action Manual Fire will take if pressed NOW.

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

        v3.15.55 — `value` is now `holdings * price * _quote_to_usd` so
        crypto-quoted pairs (BTC/ETH) compare USD-vs-USD correctly.
        """
        try:
            tgt = float(self._target_balance)
            if tgt <= 0:
                return None
            # v3.15.72 — REQUIRE init-handshake completion before
            # evaluating. Operator-reported chain (2026-04-26):
            #   1. Bot restored from saved state.
            #   2. MEM-254 chose NOT to restore _current_holdings
            #      from save (exchange is authoritative; handshake
            #      repopulates on boot). So between restore and the
            #      first tick, _current_holdings = 0 (default).
            #   3. bootstrap_exchange_state fires in background and
            #      sets stats.current_price + stats.position_value
            #      from live exchange.
            #   4. At this point armed_action would see
            #      _current_holdings=0 × fresh price = $0 → delta
            #      = -target → returns "fold" → button GREEN at
            #      launch, even though the bot actually has its
            #      real position once the handshake completes.
            # Fix: require self._initialised. The handshake sets
            # this after validating exchange holdings. Until then,
            # return None — button unilluminated until we know what
            # the bot actually holds.
            if not getattr(self, "_initialised", False):
                return None
            # v3.15.71 — armed_action requires the FRESH ticker price
            # (stats.current_price). If unavailable (pre-tick or
            # transient outage), return None. _last_trade_price is the
            # price of the last EXECUTED trade and can be hours stale
            # — using it as a fallback caused the Fire button to latch
            # green/red on launch against state that no longer existed.
            try:
                price = float(getattr(self.stats, "current_price", 0) or 0)
            except Exception:  # R28-OK: price probe; None signals "cannot compute"
                return None
            if price <= 0:
                return None
            holdings = float(self._current_holdings)
            # v3.15.55 — multiply by quote→USD rate so non-USD-quoted
            # pairs evaluate Target Balance in USD per operator directive.
            # getattr with default 1.0 keeps stub-based tests (which
            # don't construct the full bot) working — USD-quoted
            # behavior is unchanged when the field is absent.
            _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
            value = holdings * price * _qrate
            delta = value - tgt
            # Dust band: 1% of target. On $220 target that's $2.20.
            # Larger than typical per-tick price noise; small enough
            # that a meaningfully over/under bot always shows armed.
            dust = max(tgt * 0.01, 0.01)
            if delta > dust:
                return "scrum"
            if delta < -dust:
                return "fold"
            return None
        except Exception:  # R28-OK: armed-action probe; None disables the gate
            return None

    # ------------------------------------------------------------------
    # MEM-244 — Position Ceiling math helpers
    # ------------------------------------------------------------------
    @property
    def position_ceiling_usd(self) -> Optional[float]:
        """Ceiling in USD when enabled; None when disabled.

        = anchor_target_balance * position_ceiling_multiple
        """
        if not getattr(self.config, "position_ceiling_enabled", False):
            return None
        try:
            mult = float(self.config.position_ceiling_multiple)
            # Defensive clamp to the operator-stated [1, 10] range
            mult = max(1.0, min(10.0, mult))
            return self._anchor_target_balance * mult
        except Exception:  # R28-OK: ceiling math probe; None signals "ceiling unset"
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
        # v3.15.55 — quote→USD multiplier for crypto-quoted pairs.
        # getattr default keeps legacy stub-based tests passing.
        value = self._current_holdings * price * float(
            getattr(self, "_quote_to_usd", 1.0) or 1.0)
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
            return 1.0  # no ceiling → no taper
        if ratio >= 1.0:
            return 0.0  # hard stop at/above ceiling
        if ratio < 0.5:
            return 1.0  # plenty of runway
        # Linear taper from (0.5, 1.0) to (1.0, 0.1)
        #   f(ratio) = 1.0 - (ratio - 0.5) / 0.5 * 0.9
        return 1.0 - (ratio - 0.5) / 0.5 * 0.9

    # ------------------------------------------------------------------
    # MEM-245 — Compounding state persistence (save/restore across restart)
    # ------------------------------------------------------------------
    # Operator directive (Session 24, 2026-04-23):
    #   "When restarting the platform, the bot settings are not migrating.
    #    [...] the states preserved. Also, it may be worth making sure
    #    that Scrum / Fold order ID and so on carry over also otherwise
    #    the compounding mechanism will reset every time."
    #
    # Clarified via ask_user_input to mean per-tranche/per-lot identity
    # (fold tranches + main lots), not exchange order IDs.
    #
    # What's preserved:
    #   • _main_lots       — MEM-171 cost-basis tracking (initial_buy_price
    #                        per lot, operator_initiated / auto_detonated_reset
    #                        tags)
    #   • _fold_tranches   — queued fold opportunities with their ref
    #                        prices, initial_buy_price floors, and
    #                        operator_initiated tags
    #   • _fold_queue_usd  — aggregate fold queue (recomputed from
    #                        tranches on import as belt-and-suspenders)
    #   • _dist_accumulator — DIST accumulator running total
    #   • _target_balance  — MUTABLE (grows with accumulation profit)
    #   • _anchor_target_balance — MEM-244 frozen anchor
    #   • _current_holdings — authoritative internal holdings
    #   • _last_trade_price — band-travel baseline
    #   • _hedge_bal       — hedge reserve remaining
    #   • _hedge_trades    — hedge deployment counter
    #   • _scrum_target_mode / _scrum_target_side — FIRE ramp state
    #
    # What's NOT preserved (deliberately reset on restart):
    #   • _manual_fire_pending  — a queued manual fire at shutdown
    #                             shouldn't replay after restart
    #   • _tick_counter         — tick-skip cycle is cycle-local
    #   • _detonation_last_*    — detonation edge-trigger resets so
    #                             first tick evaluates fresh (correct
    #                             behavior after a session gap)
    #   • _initialised          — forced False so MEM-226 handshake
    #                             re-verifies exchange reality
    def export_scrumming_state(self) -> dict:
        """Export compounding state for persistence. Returns a JSON-
        serializable dict. Called by BotContainer.get_full_state().

        MEM-254 (Session 26 operator directive): exchange-derivable fields
        are NOT persisted. The exchange is the source of truth for what the
        bot holds; on every boot, MEM-226 handshake pulls the authoritative
        unit count live from the exchange. Persisting `_current_holdings`
        created the entire saved-state-vs-exchange-disagreement surface
        that BONK-style phantom buys exploited. Removed.

        What we DO persist: things the exchange cannot tell us.
          - _main_lots: per-lot cost basis (MEM-171)
          - _fold_tranches: queued fold operations with ref prices
          - _target_balance / _anchor_target_balance: operator set-point
          - _last_trade_price: band-travel reference
          - _dist_accumulator / _hedge_*: internal counters
          - _scrum_target_mode / _side: state machine phase
        """
        return {
            "target_balance": float(self._target_balance),
            "anchor_target_balance": float(self._anchor_target_balance),
            # v3.16.50 — standing surplus accumulator. Persists between
            # sessions so accrued (but not-yet-converted) tranche surplus
            # carries across restart and continues to drain at the
            # per-cycle rate cap.
            "standing_surplus_usd": float(
                getattr(self, "_standing_surplus_usd", 0.0) or 0.0),
            # v3.16.56 — Persist per-cycle Growth Rate Cap consumed.
            # Cycle continuity is preserved across restart so a bot
            # restored mid-cycle doesn't accidentally double-spend its
            # cap budget. Resets on next SCRUM or opposing-band touch
            # post-restart as normal.
            "fold_cycle_cap_consumed": float(
                getattr(self, "_fold_cycle_cap_consumed", 0.0) or 0.0),
            # v3.16.57 — persist pending wire credits parked while no
            # tranches exist. Without this, wire-incoming USD that
            # arrived between scrums was lost on every restart.
            "pending_wire_credits": float(
                getattr(self, "_pending_wire_credits", 0.0) or 0.0),
            # MEM-254: current_holdings REMOVED from persistence. Exchange
            # is authoritative. MEM-226 handshake re-populates on boot.
            "last_trade_price": float(self._last_trade_price),
            "last_trade_side": self._last_trade_side,    # v3.15.52
            # v3.15.55 — quote→USD rate. Persisted so the GUI can render
            # USD-correct status immediately on restart, before the first
            # tick refreshes it from the exchange.
            "quote_to_usd": float(self._quote_to_usd or 1.0),
            # v3.15.69 — wire-income stack pending buy. Persists so a
            # restart mid-stack doesn't lose the queued acquisition.
            "pending_stack_buy_usd": float(
                getattr(self, "_pending_stack_buy_usd", 0.0) or 0.0),
            # v3.15.58 — Circuit Breaker state. Hard trip MUST persist
            # across restart (a tripped breaker cannot silently reopen
            # because the process restarted). Soft state persists for
            # cooldown continuity. getattr with defaults so legacy
            # stub-based callers (tests) work without setting CB fields.
            "cb_hard_tripped": bool(getattr(self, "_cb_hard_tripped", False)),
            "cb_hard_tripped_at": float(
                getattr(self, "_cb_hard_tripped_at", 0.0) or 0.0),
            "cb_hard_trip_pct": float(
                getattr(self, "_cb_hard_trip_pct", 0.0) or 0.0),
            "cb_soft_active_side": getattr(self, "_cb_soft_active_side", None),
            "cb_soft_cooldown_remaining": int(
                getattr(self, "_cb_soft_cooldown_remaining", 0) or 0),
            "cb_soft_trip_pct": float(
                getattr(self, "_cb_soft_trip_pct", 0.0) or 0.0),
            "fold_queue_usd": float(self._fold_queue_usd),
            "dist_accumulator": float(self._dist_accumulator),
            "hedge_bal": float(self._hedge_bal),
            "hedge_trades": int(self._hedge_trades),
            "scrum_target_mode": str(self._scrum_target_mode),
            "scrum_target_side": self._scrum_target_side,  # str | None
            # Deep copies — lots and tranches are lists of dicts with
            # primitive values. JSON-safe as-is.
            "main_lots": [dict(lot) for lot in self._main_lots],
            "fold_tranches": [dict(t) for t in self._fold_tranches],
            # v3.15.77 — Conditional opposing-direction hysteresis state.
            # Persists across restart so a bot mid-armed-gate doesn't
            # forget its pivot reference. Format version bumped to 4.
            # getattr fallbacks tolerate stub/test bots that bypass
            # __init__ (e.g. ScrummingBot.__new__() in unit tests).
            "hyst_armed_fold_side": bool(
                getattr(self, "_hyst_armed_fold_side", False)),
            "hyst_armed_scrum_side": bool(
                getattr(self, "_hyst_armed_scrum_side", False)),
            "hyst_ref_fold_side": float(
                getattr(self, "_hyst_ref_fold_side", 0.0) or 0.0),
            "hyst_ref_scrum_side": float(
                getattr(self, "_hyst_ref_scrum_side", 0.0) or 0.0),
            # v3.16.39 P2-VIS — fold-tranche lifetime counters. Persist
            # so the visibility panel survives restart and reflects the
            # bot's true cycle history, not just the current session.
            "tranches_created_lifetime": int(
                getattr(self, "_tranches_created_lifetime", 0) or 0),
            "tranches_closed_lifetime": int(
                getattr(self, "_tranches_closed_lifetime", 0) or 0),
            # v3.24.44 — tranches DISCARDED without folding, kept apart
            # from `closed` so that counter keeps meaning "folded". With
            # this, created - closed - discarded = standing reconciles;
            # without it a clear makes the pair permanently unexplainable.
            "tranches_discarded_lifetime": int(
                getattr(self, "_tranches_discarded_lifetime", 0) or 0),
            # v3.24.45 — USD of parked wire credit discarded by an
            # operator clear. An earmark released, never funds moved;
            # kept so the release is auditable after the fact rather
            # than vanishing without trace.
            "wire_credits_discarded_lifetime": float(
                getattr(self, "_wire_credits_discarded_lifetime", 0.0) or 0.0),
            # v3.24.49 (Phase 1 Step 4) — diagnostic state that was
            # destroyed on every launch. Each of these is read to answer
            # "why did nothing happen", and each reset to zero before
            # the question could be asked.
            #
            # pending_wire_ledger: the PROVENANCE of parked wire credit.
            # The total was persisted; the itemisation that says where
            # it came from was not, so after any restart the money had
            # no explanation. _add_wire_credits also guards with
            # `if entries:`, so a post-restart absorb wrote no
            # wire_credits key at all.
            "pending_wire_ledger": [
                dict(_e) for _e in (
                    getattr(self, "_pending_wire_ledger", []) or [])
                if isinstance(_e, dict)],
            # fold_accumulator: the lifetime compound counter. Restarting
            # zeroed the only running total of how much compounding had
            # ever actually happened.
            "fold_accumulator": float(
                getattr(self, "_fold_accumulator", 0.0) or 0.0),
            # tranches_malformed_dropped: how many tranches were silently
            # discarded for bad shape. This is the single most diagnostic
            # number for "tranches fill but nothing happens", and it did
            # not survive a launch.
            "tranches_malformed_dropped": int(
                getattr(self, "_tranches_malformed_dropped", 0) or 0),
            # stack_*: latent today (stack_mode is off on all 35 bots),
            # persisted for the same reason pending_stack_buy_usd already
            # is — a restart must not lose a queued acquisition, and the
            # tranches that acquisition produces are part of it.
            "stack_tranches": [
                dict(_t) for _t in (
                    getattr(self, "_stack_tranches", []) or [])
                if isinstance(_t, dict)],
            "stack_created": int(
                getattr(self, "_stack_created", 0) or 0),
            # Item 9 (2026-08-13) — the stack-side discard counter, and
            # it must persist for the reason `tranches_discarded_lifetime`
            # above does: `stack_tranches` and `stack_created` both
            # survive a restart, so a discard total that did not would
            # let a relaunch silently re-open the gap it exists to close.
            #
            # READ THROUGH `as_finite_float`, DIVERGING FROM THE SIBLING
            # KEYS AROUND IT, and deliberately. A bare `int()` on a value
            # that came back from JSON raises ValueError on `NaN` and
            # OverflowError on `Infinity` — both of which `json.loads`
            # produces — from inside the state export, which would take
            # the whole save down. Those siblings keep the old expression
            # and putting them all on one rule is a separate unit.
            "stack_discarded": int(
                as_finite_float(getattr(self, "_stack_discarded", 0))
                or 0.0),
            # v3.23.7 R-CLN: the v3.16.41 persistence keys
            # `target_grow_cycle_armed` / `target_grow_last_bb_pos` were
            # removed alongside the field retirement. Pre-v3.23.7 saves
            # still carrying these keys are silently dropped on import
            # (the field was non-load-bearing for the last six versions).

            # v3.23.7 D2-b — Asymmetric BB-extreme cycle-reset side.
            # Records which side the last target-growth fired against so
            # the tick-entry asymmetric reset block can detect "opposite
            # extreme touched". See __init__ comment for full semantics.
            "target_grow_last_side": (
                str(getattr(self, "_target_grow_last_side", None))
                if getattr(self, "_target_grow_last_side", None) in ("lower", "upper")
                else None),
            # Versioning — if we add/remove fields later, import
            # gracefully degrades.
            "_format_version": 7,   # v3.23.7 — D2-b asymmetric cycle-reset side tracker
        }

    def import_scrumming_state(self, data: dict) -> None:
        """Restore compounding state from a dict produced by
        export_scrumming_state. Safe against missing keys (treats as
        defaults). Called by BotContainer.restore_bots_from_state()
        after the bot is constructed but before registration.

        Logs a warning if main_lots.sum(units) disagrees with the
        saved current_holdings by more than 0.1% — that would
        indicate data corruption or an older incompatible save format.
        The MEM-226 init handshake on start will further reconcile
        against exchange reality.
        """
        if not isinstance(data, dict):
            return

        # Scalars with safe defaults.
        # Anchor restored FIRST so the Smart Ceiling sanity check can
        # evaluate correctly for the restored target below.
        self._anchor_target_balance = float(data.get(
            "anchor_target_balance", self._anchor_target_balance))
        _restored_target = float(data.get(
            "target_balance", self._target_balance))

        # v3.16.50 — Tranche-Surplus discipline restore. Target Balance
        # grows organically via standing surplus across cycles. A
        # restored target_balance ABOVE anchor is the correct, expected
        # state — that's the persistence mechanism. The OLD restore
        # clamp ("anchor × (1 + max_target_growth_pct/100)") was the
        # same fictional ceiling that v3.16.50 retired in MEM-251 v2
        # and Phase B; clamping at restore was just an extension of
        # the same misimplementation.
        #
        # Sanity check: if Smart Ceiling is enabled, refuse to trust a
        # restored target that exceeds the operator-set maturity ceiling
        # (anchor × position_ceiling_multiple). That's the same
        # detonation harvest threshold; a target past it would mean the
        # bot should have detonated and we somehow restored stale
        # pre-detonation state. Snap back to Smart Ceiling in that case.
        if getattr(self.config, "position_ceiling_enabled", False):
            try:
                _smart_mult = float(getattr(
                    self.config, "position_ceiling_multiple", 1.0))
                _smart_mult = max(1.0, min(10.0, _smart_mult))
                _smart_ceiling_target = (
                    self._anchor_target_balance * _smart_mult)
                if _restored_target > _smart_ceiling_target:
                    logger.warning(
                        "v3.16.50 restore: persisted target_balance $%.2f "
                        "exceeds Smart Ceiling $%.2f (anchor $%.2f × %.1fx). "
                        "Snapping to Smart Ceiling — likely stale "
                        "pre-detonation state.",
                        _restored_target, _smart_ceiling_target,
                        self._anchor_target_balance, _smart_mult)
                    _restored_target = _smart_ceiling_target
            except (TypeError, ValueError, AttributeError) as _sup:
                # Smart Ceiling math probe failed — trust the restored
                # value (R28: fail-loudly elsewhere if something genuine
                # is wrong; don't silently mutate operator state here).
                logger.debug("suppressed in %s: %s: %s", "import_scrumming_state", type(_sup).__name__, _sup)
        self._target_balance = _restored_target

        # v3.16.50 — restore standing surplus accumulator so accrued
        # cross-session surplus continues to drain at the per-cycle rate.
        try:
            self._standing_surplus_usd = float(data.get(
                "standing_surplus_usd",
                getattr(self, "_standing_surplus_usd", 0.0)) or 0.0)
            if self._standing_surplus_usd < 0.0:
                self._standing_surplus_usd = 0.0
        except (TypeError, ValueError):
            self._standing_surplus_usd = 0.0
        # v3.16.56 — Restore fold-cycle Growth Rate Cap consumed.
        try:
            self._fold_cycle_cap_consumed = float(data.get(
                "fold_cycle_cap_consumed",
                getattr(self, "_fold_cycle_cap_consumed", 0.0)) or 0.0)
            if self._fold_cycle_cap_consumed < 0.0:
                self._fold_cycle_cap_consumed = 0.0
        except (TypeError, ValueError):
            self._fold_cycle_cap_consumed = 0.0
        # v3.16.57 — Restore pending wire credits across restart.
        try:
            self._pending_wire_credits = float(data.get(
                "pending_wire_credits",
                getattr(self, "_pending_wire_credits", 0.0)) or 0.0)
            if self._pending_wire_credits < 0.0:
                self._pending_wire_credits = 0.0
        except (TypeError, ValueError):
            self._pending_wire_credits = 0.0
        # MEM-254: `current_holdings` is NO LONGER restored from saved
        # state. Exchange is the authoritative source for the bot's unit
        # count. MEM-226 init handshake pulls it live from the exchange on
        # every boot. If older saves contain the field, it is silently
        # ignored — the handshake overwrites it anyway (former path).
        # Leaving `self._current_holdings` at its default (0.0 from
        # __init__) here; handshake will populate it.
        self._last_trade_price = float(data.get(
            "last_trade_price", self._last_trade_price))
        # v3.15.52 — restore _last_trade_side for opposite-direction
        # hysteresis so the gate keeps state across restart.
        _lts = data.get("last_trade_side", self._last_trade_side)
        if _lts in ("SCRUM", "FOLD"):
            self._last_trade_side = _lts
        else:
            self._last_trade_side = None
        # v3.15.55 — restore quote→USD rate. Will be refreshed on the
        # first tick anyway, but having a sane saved value lets the GUI
        # show USD-correct numbers immediately on boot. Only restore a
        # positive rate; otherwise leave the default 1.0.
        _qrate_saved = data.get("quote_to_usd", None)
        try:
            _qrate_saved = float(_qrate_saved) if _qrate_saved is not None else 0.0
        except (TypeError, ValueError):
            _qrate_saved = 0.0
        if _qrate_saved > 0:
            self._quote_to_usd = _qrate_saved
        # v3.15.69 — restore pending stack-buy USD
        try:
            self._pending_stack_buy_usd = float(
                data.get("pending_stack_buy_usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._pending_stack_buy_usd = 0.0
        # v3.15.77 — restore conditional opposing-direction hysteresis
        # state. Older saves (format_version < 4) lack these fields;
        # default to disarmed/zero so the next tick re-evaluates from
        # current delta direction. Cleanly degrades.
        self._hyst_armed_fold_side = bool(
            data.get("hyst_armed_fold_side", False))
        self._hyst_armed_scrum_side = bool(
            data.get("hyst_armed_scrum_side", False))
        try:
            self._hyst_ref_fold_side = float(
                data.get("hyst_ref_fold_side", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._hyst_ref_fold_side = 0.0
        try:
            self._hyst_ref_scrum_side = float(
                data.get("hyst_ref_scrum_side", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._hyst_ref_scrum_side = 0.0
        # Defensive: if armed but no reference, force disarm.
        if self._hyst_armed_fold_side and self._hyst_ref_fold_side <= 0:
            self._hyst_armed_fold_side = False
        if self._hyst_armed_scrum_side and self._hyst_ref_scrum_side <= 0:
            self._hyst_armed_scrum_side = False
        # v3.15.58 — restore Circuit Breaker state. Hard trip MUST
        # persist across restart so a tripped bot stays tripped.
        self._cb_hard_tripped = bool(data.get("cb_hard_tripped", False))
        try:
            self._cb_hard_tripped_at = float(
                data.get("cb_hard_tripped_at", 0.0) or 0.0)
            self._cb_hard_trip_pct = float(
                data.get("cb_hard_trip_pct", 0.0) or 0.0)
        except (TypeError, ValueError) as _sup:
            logger.debug("suppressed in %s: %s: %s", "import_scrumming_state", type(_sup).__name__, _sup)
        _cb_side = data.get("cb_soft_active_side", None)
        self._cb_soft_active_side = (
            _cb_side if _cb_side in ("scrum", "fold") else None)
        try:
            self._cb_soft_cooldown_remaining = int(
                data.get("cb_soft_cooldown_remaining", 0) or 0)
            self._cb_soft_trip_pct = float(
                data.get("cb_soft_trip_pct", 0.0) or 0.0)
        except (TypeError, ValueError) as _sup:
            logger.debug("suppressed in %s: %s: %s", "import_scrumming_state", type(_sup).__name__, _sup)
        # If hard breaker was persisted as tripped, force the bot state
        # to PAUSED so the run-loop honors it. The operator must call
        # reset_circuit_breaker('hard') to resume.
        if self._cb_hard_tripped:
            try:
                self.state = BotState.PAUSED
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "import_scrumming_state", type(_sup).__name__, _sup)
        self._dist_accumulator = float(data.get(
            "dist_accumulator", self._dist_accumulator))
        self._hedge_bal = float(data.get(
            "hedge_bal", self._hedge_bal))
        self._hedge_trades = int(data.get(
            "hedge_trades", self._hedge_trades))
        self._scrum_target_mode = str(data.get(
            "scrum_target_mode", "search"))
        _side = data.get("scrum_target_side", None)
        self._scrum_target_side = _side if _side in (
            "upper", "lower", None) else None

        # Collections — lists of dicts. Coerce each dict to plain dict
        # (defensive against any lingering non-serializable residue).
        lots_raw = data.get("main_lots", [])
        if isinstance(lots_raw, list):
            self._main_lots = [dict(lot) for lot in lots_raw
                               if isinstance(lot, dict)]
        tranches_raw = data.get("fold_tranches", [])
        if isinstance(tranches_raw, list):
            self._fold_tranches = [dict(t) for t in tranches_raw
                                    if isinstance(t, dict)]
            # v3.24.20 — compact wire-credit provenance carried in from
            # older saves. The append-side cap only engages on the next
            # credit, so a tranche that never receives another one would
            # re-serialise thousands of entries forever. Measured on the
            # operator's live state: one bot held 3,325 entries = 96% of
            # its 385,930-byte record.
            _rolled = self._compact_wire_credits()
            if _rolled:
                logger.info(
                    "Bot %s: rolled %d wire-credit detail entries into "
                    "aggregate on restore", self.bot_id, _rolled)

        # v3.16.39 P2-VIS — restore lifetime counters. Default 0 for
        # pre-v3.16.39 saved states (counters did not exist before).
        # Operator implication: bots restored from older saves will show
        # "0 tranches opened lifetime" in the visibility panel until they
        # do their first scrum after upgrade — that's correct backward-
        # compat semantics; we don't fabricate historical counts.
        _created = int(data.get("tranches_created_lifetime", 0) or 0)
        _closed = int(data.get("tranches_closed_lifetime", 0) or 0)
        # v3.24.44 — restored alongside, defaulting to 0 for state written
        # before the key existed. No back-fill: a bot that never had a
        # clear genuinely has none, and fabricating one would corrupt the
        # reconciliation this counter exists to provide.
        self._tranches_discarded_lifetime = int(
            data.get("tranches_discarded_lifetime", 0) or 0)
        self._wire_credits_discarded_lifetime = float(
            data.get("wire_credits_discarded_lifetime", 0.0) or 0.0)
        # v3.24.49 (Phase 1 Step 4) — every restore below is defaulted,
        # so a NEWER build reading an OLDER state file simply starts
        # these at zero rather than raising. The export side adds keys an
        # OLDER build will ignore, so the file stays readable both ways.
        # No back-fill is attempted: fabricating a historical value would
        # corrupt the very counters these exist to make trustworthy.
        self._pending_wire_ledger = [
            dict(_e) for _e in (data.get("pending_wire_ledger", []) or [])
            if isinstance(_e, dict)]
        self._fold_accumulator = float(
            data.get("fold_accumulator", 0.0) or 0.0)
        self._tranches_malformed_dropped = int(
            data.get("tranches_malformed_dropped", 0) or 0)
        self._stack_tranches = [
            dict(_t) for _t in (data.get("stack_tranches", []) or [])
            if isinstance(_t, dict)]
        self._stack_created = int(data.get("stack_created", 0) or 0)
        # Item 9 (2026-08-13) — defaults to 0 for every state file
        # written before the key existed. No back-fill: a bot that never
        # ran a despawn sweep genuinely has no discards, and inventing
        # one would corrupt the reconciliation the counter exists for.
        # Guarded for the same reason the export side is: this value
        # comes straight off JSON, where `NaN` and `Infinity` are both
        # representable, and a bare `int()` on either raises inside the
        # restore path.
        self._stack_discarded = int(
            as_finite_float(data.get("stack_discarded", 0)) or 0.0)
        # v3.23.7 Anomaly C — invariant guard: closed > created is
        # structurally impossible (every close pairs to an open). If
        # persisted state shows that, clamp closed to created and emit
        # warning so the operator can investigate the underlying drift.
        # The live RAVE bot reached closed=494 > created=444 (delta 50)
        # via the unconditional `_tranches_closed_lifetime += 1` on the
        # Manual Fire ValueError fallthrough at L1567 (now fixed via
        # `_removed_ok` gate); this clamp is the historical-data repair.
        if _closed > _created:
            try:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"TRANCHE COUNTER REPAIR: persisted closed="
                             f"{_closed} > created={_created}; clamping "
                             f"closed to {_created}. Historical drift "
                             f"surfaced — investigate if recurring."))
            except Exception:  # R28-OK: bus may not be wired during restore
                logger.warning(
                    "Bot %s tranche counter repair: persisted closed=%d > "
                    "created=%d; clamping closed to %d.",
                    self.bot_id, _closed, _created, _created)
            _closed = _created
        self._tranches_created_lifetime = _created
        self._tranches_closed_lifetime = _closed

        # v3.23.7 D2-b — restore asymmetric cycle-reset side tracker.
        # Pre-v3.23.7 saves carry no `target_grow_last_side` key; default
        # to None ("freshly-armed never-fired" state). Older saves with
        # the retired `target_grow_cycle_armed` / `target_grow_last_bb_pos`
        # keys are silently dropped — the field was non-load-bearing for
        # the last six versions.
        try:
            _saved_side = data.get("target_grow_last_side", None)
            if _saved_side in ("lower", "upper"):
                self._target_grow_last_side = _saved_side
            else:
                self._target_grow_last_side = None
        except Exception:  # R28-OK: defensive restore — fall back to None
            self._target_grow_last_side = None

        # Recompute fold_queue_usd from tranches (belt-and-suspenders;
        # also self-heals if saved aggregate drifted from per-tranche sum).
        self._fold_queue_usd = sum(
            float(t.get("usd", 0.0)) for t in self._fold_tranches)

        # Invariant sanity check — if lots disagree with holdings,
        # warn but don't block. Init handshake will reconcile vs exchange.
        lots_sum = sum(float(lot.get("units", 0.0))
                        for lot in self._main_lots)
        if self._current_holdings > 0 and lots_sum > 0:
            drift = abs(lots_sum - self._current_holdings) / max(
                self._current_holdings, 1e-9)
            if drift > 0.001:  # 0.1% tolerance
                try:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"STATE RESTORE WARNING: main_lots "
                                 f"total {lots_sum:.6f} drifts "
                                 f"{drift*100:.2f}% from saved holdings "
                                 f"{self._current_holdings:.6f}. "
                                 f"MEM-226 init handshake will reconcile "
                                 f"against exchange on next start."))
                except Exception:
                    # Bus may not be wired yet during restore; log-only
                    logger.warning(
                        "Bot %s state restore drift: lots=%.6f "
                        "holdings=%.6f", self.bot_id, lots_sum,
                        self._current_holdings)

        # Critical: force uninitialised so the MEM-226 handshake runs
        # on next tick. This re-verifies exchange balance and catches
        # drift that occurred during the restart window (manual trades,
        # exchange-side events). Saved _current_holdings becomes our
        # starting assumption; handshake may override it.
        self._initialised = False

    def force_fire(self, aggressive: bool = False) -> None:
        """MEM-236 + MEM-241 — Manual Fire from the dashboard.

        Args:
            aggressive: if True (the new default from the GUI), queue a
                one-shot rebalance-to-target on the next tick. Uses
                MARKET order. Sized by delta. Bypasses TA/BB/midline
                gates per operator directive. If False (legacy call
                sites), falls back to the original MEM-236 behavior of
                just flushing the tick-skip counter so the next tick
                evaluates through the normal gate chain.
        """
        if aggressive:
            self._manual_fire_pending = True
            # Also flush tick-skip so we don't wait up to 5 minutes in
            # SEARCH mode before the rebalance actually runs.
            self._tick_counter = max(self._tick_counter, self._tick_skip - 1)
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=("MANUAL FIRE (aggressive): operator requested "
                         "immediate rebalance-to-target. Next tick will "
                         "execute a MARKET order sized to the current "
                         "delta. Bypasses TA/BB/fold gates."))
        else:
            # Legacy non-aggressive behavior preserved for any existing
            # callers; original MEM-236 semantic.
            self._tick_counter = max(self._tick_counter, self._tick_skip - 1)
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=("MANUAL FIRE: operator requested immediate "
                         "evaluation. Next tick will run full scrum/fold "
                         "gate checks. This does NOT bypass gate conditions."))

    # ------------------------------------------------------------------
    # v3.16.46 — Exchange-pulled position health refresh.
    # Operator directive 2026-05-10: position health belongs to the
    # exchange, not internal accumulators. This method fetches recent
    # trade history via get_my_trades and derives avg_entry, realized
    # P/L, fees-paid, etc. via the position_health helper. Results
    # cached in stats.realized_pnl_exchange / avg_entry_exchange / etc.
    #
    # Throttled: refreshes at most once every REFRESH_COOLDOWN_SEC
    # (default 300s = 5 min). Caller passes the current unix-seconds
    # timestamp; comparison against stats.exchange_data_fresh_ts gates
    # the actual API call. The trade-history endpoint is rate-limited
    # at the exchange; we don't want to hammer it from every tick.
    # ------------------------------------------------------------------
    EXCHANGE_HEALTH_REFRESH_COOLDOWN_SEC = 300.0  # 5 minutes

    async def refresh_exchange_position_health(self,
                                                force: bool = False) -> bool:
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
        if (not force
                and (_now - self.stats.exchange_data_fresh_ts) < _cooldown):
            return False  # throttled

        if self.exchange is None:
            return False
        if not hasattr(self.exchange, "get_my_trades"):
            return False

        try:
            from ..exchange.position_health import compute_position_health
            _trades = await self.exchange.get_my_trades(
                self.config.symbol, limit=500)
            if _trades is None:
                return False
            _asset_base = self.config.symbol.split("/")[0]
            _ph = compute_position_health(_trades, _asset_base)

            # v3.23.56 — write P&L / cost-basis / fees FIRST (these
            # are correct as computed from the single-page fills;
            # they're about the currently-OPEN position, not lifetime
            # count). Then run the paginated YTD sync which is the
            # sole authoritative writer for `exchange_trade_count`.
            # ONLY AFTER both complete do we stamp `fresh_ts` — that
            # field is what the GUI reader gates on
            # (bot_container.get_status), so as long as it stays 0
            # (or its previous value) during the async gap, the
            # display keeps showing the last-known count instead of
            # toggling to the single-page intermediate value.
            self.stats.realized_pnl_exchange = float(_ph.realized_pnl_usd)
            self.stats.avg_entry_exchange = float(_ph.avg_entry)
            self.stats.cost_basis_total_exchange = float(_ph.cost_basis_total_usd)
            self.stats.fees_paid_exchange = float(_ph.fees_paid_total)
            try:
                await self.sync_ytd_trade_count()
            except Exception as _ytd_exc:  # R28-OK: best-effort
                logger.debug(
                    "Bot %s YTD sync inside health-refresh raised: %s",
                    self.bot_id, _ytd_exc)
            # LAST — stamp fresh_ts so the GUI reader now switches
            # over to exchange_trade_count (which sync just wrote).
            self.stats.exchange_data_fresh_ts = _now

            # v3.16.48 — also pull and cache wallet cash balance.
            # Operator directive: Spendable = cash. Pull USD + USDC
            # directly from exchange. All bots share the same wallet,
            # so any bot's cached value is authoritative for the
            # aggregator (which picks max-of-fresh per
            # get_aggregate_stats).
            try:
                _cash_usd = 0.0
                _bal_usd = await self._get_balance("USD")
                if _bal_usd is not None:
                    _cash_usd += float(getattr(_bal_usd, "free", 0) or 0)
                # USDC for stablecoin holdings
                try:
                    _bal_usdc = await self._get_balance("USDC")
                    if _bal_usdc is not None:
                        _cash_usd += float(getattr(_bal_usdc, "free", 0) or 0)
                except Exception as _sup:  # R28-OK: USDC may not exist on this exchange
                    logger.debug("suppressed in %s: %s: %s", "refresh_exchange_position_health", type(_sup).__name__, _sup)
                self.stats.cash_balance_usd = _cash_usd
            except Exception as _cash_exc:  # R28-OK: best-effort
                logger.debug(
                    "Bot %s cash balance refresh failed (non-fatal): %s",
                    self.bot_id, _cash_exc)

            # v3.23.24 — active order counts. Bot Details Status tab
            # previously showed 0 forever because active_buy_orders /
            # active_sell_orders were dataclass defaults with no assign
            # site (audit 2026-07-25). Pull open orders for this symbol
            # from the exchange and count by side. Best-effort: if the
            # exchange method is missing or errors, leave prior values.
            try:
                if hasattr(self.exchange, "get_open_orders"):
                    from ..exchange.base import OrderSide as _OS
                    _open = await self.exchange.get_open_orders(
                        self.config.symbol)
                    if _open is not None:
                        _buys = sum(
                            1 for o in _open
                            if getattr(o, "side", None) == _OS.BUY)
                        _sells = sum(
                            1 for o in _open
                            if getattr(o, "side", None) == _OS.SELL)
                        self.stats.active_buy_orders = int(_buys)
                        self.stats.active_sell_orders = int(_sells)
            except Exception as _oo_exc:  # R28-OK: best-effort
                logger.debug(
                    "Bot %s open-orders refresh failed (non-fatal): %s",
                    self.bot_id, _oo_exc)

            return True
        except Exception as _exc:  # R28-OK: best-effort exchange fetch
            logger.warning(
                "Bot %s exchange position-health refresh failed: %s",
                self.bot_id, _exc)
            return False

    # ------------------------------------------------------------------
    # v3.23.54 — YTD trade-count reconciliation.
    # Operator directive 2026-07-28: the dashboard "Trades" column got
    # stuck at 500 for several bots because refresh_exchange_position_
    # health calls get_my_trades(limit=500) — a single-page fetch. Any
    # bot with more than 500 YTD fills capped there. This method
    # paginates from the 2026-04-01 anchor and reconciles both counters
    # (stats.total_trades and stats.exchange_trade_count) so subsequent
    # per-trade increments pick up from the true count.
    # ------------------------------------------------------------------
    YTD_TRADE_ANCHOR_UTC = 1_775_001_600.0  # 2026-04-01T00:00:00Z
    YTD_TRADE_PAGE_LIMIT = 500              # ccxt / Coinbase per-page cap
    YTD_TRADE_MAX_PAGES = 40                # 20k-trade ceiling, safety cap

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
        # v3.23.58 — RAVE-fix, second attempt. Coinbase Advanced
        # Trade's fills endpoint has a HARD ~500-trade cap on a
        # single time-range query regardless of cursor pagination.
        # v3.23.57 (`params={'paginate': True}`) returned exactly
        # 500 for RAVE across 3 consecutive syncs while every other
        # bot's count matched ground truth. Fix: walk YTD in 30-day
        # windows, each well under the 500 cap for any realistic
        # bot (RAVE at ~9 trades/day = ~270 per 30-day window).
        # Merge unique trade IDs across windows.
        import time as _t
        _now = _t.time()
        _window_s = 30 * 24 * 3600.0             # 30-day window
        _cursor = self.YTD_TRADE_ANCHOR_UTC
        _seen_ids: set = set()
        _windows = 0
        # v3.23.60 — accumulate YTD buy/sell USD alongside the count.
        # Powers the dashboard Scrummed/Folded cards.
        _ytd_scrum_usd = 0.0
        _ytd_fold_usd = 0.0
        _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
        try:
            while _cursor < _now and _windows < 12:  # 12*30d = 360d
                _end = min(_cursor + _window_s, _now)
                _end_ms = int(_end * 1000)
                _window_trades = await self.exchange.get_my_trades(
                    self.config.symbol,
                    since=_cursor,
                    limit=self.YTD_TRADE_PAGE_LIMIT,
                    params={"paginate": True, "until": _end_ms})
                _new = 0
                for _tr in (_window_trades or []):
                    _tid = getattr(_tr, "id", None) or id(_tr)
                    if _tid in _seen_ids:
                        continue
                    _seen_ids.add(_tid)
                    _new += 1
                    # v3.23.60 — classify + accumulate USD notional.
                    try:
                        _amt = float(getattr(_tr, "amount", 0) or 0)
                        _px = float(getattr(_tr, "price", 0) or 0)
                        _usd = _amt * _px * _qrate
                        _side = getattr(_tr, "side", None)
                        _side_str = str(
                            getattr(_side, "value", _side) or ""
                        ).lower()
                        if "sell" in _side_str:
                            _ytd_scrum_usd += _usd
                        elif "buy" in _side_str:
                            _ytd_fold_usd += _usd
                    except (TypeError, ValueError) as _sup:
                        logger.debug("suppressed in %s: %s: %s", "sync_ytd_trade_count", type(_sup).__name__, _sup)
                logger.debug(
                    "Bot %s YTD window %d: [%.0f..%.0f] returned=%d "
                    "new=%d cumulative_unique=%d",
                    self.bot_id, _windows + 1, _cursor, _end,
                    len(_window_trades or []), _new, len(_seen_ids))
                _windows += 1
                _cursor = _end
            _count = len(_seen_ids)
            logger.info(
                "Bot %s YTD sync via chunked-window walk: "
                "symbol=%s returned %d unique trades over %d windows "
                "(scrummed=$%.2f folded=$%.2f)",
                self.bot_id, self.config.symbol, _count, _windows,
                _ytd_scrum_usd, _ytd_fold_usd)
        except Exception as _exc:  # R28-OK: best-effort exchange fetch
            logger.warning(
                "Bot %s sync_ytd_trade_count fetch failed: %s "
                "(persisted counter %d retained)",
                self.bot_id, _exc, _persisted)
            return None
        # v3.23.56 — protect against DOWNWARD toggling. Never lower
        # either counter with a sync result smaller than what's
        # already there. `_count` is what the paginated fetch just
        # observed; both persisted total_trades and the previous
        # exchange_trade_count act as floors so a partial-page /
        # rate-limited / exchange-quirk response can't visually
        # regress the dashboard while other refreshes still hold
        # the higher truth.
        _prev_exc = int(getattr(
            self.stats, "exchange_trade_count", 0) or 0)
        _reconciled = max(_persisted, _prev_exc, _count)
        self.stats.total_trades = _reconciled
        self.stats.exchange_trade_count = _reconciled
        # v3.23.60 — YTD Scrummed/Folded USD writes. Same downward-
        # toggle floor as the count: never overwrite a higher known
        # value with a lower one (partial-page / rate-limit safety).
        _prev_scrum = float(getattr(
            self.stats, "ytd_scrummed_usd", 0.0) or 0.0)
        _prev_fold = float(getattr(
            self.stats, "ytd_folded_usd", 0.0) or 0.0)
        self.stats.ytd_scrummed_usd = max(_prev_scrum, _ytd_scrum_usd)
        self.stats.ytd_folded_usd = max(_prev_fold, _ytd_fold_usd)
        import time as _t
        self.stats.exchange_data_fresh_ts = _t.time()
        logger.info(
            "Bot %s YTD trade-count sync: exchange=%d persisted=%d "
            "prev_exchange=%d reconciled=%d",
            self.bot_id, _count, _persisted, _prev_exc, _reconciled)
        return _reconciled

    # ------------------------------------------------------------------
    # MEM-255 — Live-pull bootstrap (operator directive 2026-04-23:
    # "On start up. All the other values seem okay. Something is still not
    # right with how it is interpreting and displaying BTC.")
    #
    # The tick loop's MEM-226 handshake is the authoritative populator of
    # _current_holdings, but it only runs when the bot actually ticks. An
    # IDLE bot (freshly registered, not yet started) shows holdings = 0
    # in the GUI until the operator starts it. For bots restored from
    # saved state this creates a false "empty position" display right
    # after boot. This bootstrap is the live-pull solution: fired once
    # when the bot gets its connector, it queries exchange balance + price
    # and populates the GUI-visible state fields. It is NOT a substitute
    # for the tick-time handshake — that still runs on first tick and
    # reconciles against the full two-read MEM-226 protocol. This is
    # purely to give the GUI real data before the first tick.
    # ------------------------------------------------------------------
    async def bootstrap_exchange_state(self) -> None:
        """One-shot live-pull of exchange state for the GUI.

        Populates: _current_holdings, stats.current_price, stats.position_value.
        Runs fail-closed — any exception logged but not raised. Intended to
        be scheduled as a background task right after the connector is
        attached to the bot; irrelevant for bots that tick quickly (the
        handshake covers them) but essential for bots that haven't started.

        v3.16.60 — Guard against the placeholder exchange used during
        bot-restore-before-connector-ready window. Operator-reported
        2026-05-14: 380 retry-storm errors per session of the form
        `_PlaceholderExchangeForRestore object has no attribute
        get_balance`. Pre-fix: bootstrap was invoked on every tick
        during the warm-up window, each one raising AttributeError on
        the placeholder. Now: detect the placeholder and return silently;
        bootstrap re-runs naturally once the real connector attaches.
        """
        # v3.16.60 — placeholder-exchange guard
        if (self.exchange is None
                or not hasattr(self.exchange, "get_balance")
                or type(self.exchange).__name__ == "_PlaceholderExchangeForRestore"):
            logger.debug(
                "Bot %s bootstrap_exchange_state: exchange not ready "
                "(placeholder or missing); will retry once real "
                "connector attaches.", self.bot_id)
            return
        try:
            symbol = self.config.symbol
            target_asset = self.config.target_asset
            # Pull balance + ticker concurrently-ish (one await each).
            _bal = await self._get_balance(target_asset)
            _units = float(getattr(_bal, "total", 0) or _bal.free or 0)
            _ticker = await self._get_ticker(symbol)
            _price = float(getattr(_ticker, "last", 0) or 0)
            # v3.15.55 — refresh quote→USD rate so position_value goes
            # into stats.position_value already converted to USD even
            # for crypto-quoted pairs (BTC/ETH, etc.). Best-effort: a
            # failure here just leaves stats.position_value stale, the
            # main tick will refresh later.
            try:
                await self._refresh_quote_to_usd()
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "bootstrap_exchange_state", type(_sup).__name__, _sup)
            # v3.23.43 — same fix as init-handshake + drift-reconcile:
            # never trust the raw exchange balance as this bot's own
            # holdings. Bot's authoritative source is `_main_lots`.
            # Any excess on the exchange belongs to the operator or a
            # sibling bot on the same asset. Bootstrap pre-fills the
            # GUI *conservatively* — an under-report is corrected on
            # the first tick's handshake; an over-report (what we're
            # preventing here) is what caused the ETH/BTC $178 surplus
            # symptom.
            _tracked_units_bootstrap = sum(
                float(lot.get("units", 0) or 0)
                for lot in self._main_lots
            )
            if _units >= 0:
                self._current_holdings = min(
                    max(0.0, _units), _tracked_units_bootstrap) \
                    if _tracked_units_bootstrap > 0 \
                    else 0.0
            if _price > 0:
                self.stats.current_price = _price
            if _price > 0 and self._current_holdings > 0:
                # USD value = base_units * quote_price * quote_to_usd
                self.stats.position_value = (
                    self._current_holdings * _price
                    * float(self._quote_to_usd or 1.0)
                )
            else:
                self.stats.position_value = 0.0
            logger.info(
                "Bot %s bootstrap_exchange_state: %s units=%.8f @ $%.8f "
                "quote_to_usd=%.4f (position_usd=$%.4f)",
                self.bot_id, target_asset, _units, _price,
                self._quote_to_usd,
                _units * _price * float(self._quote_to_usd or 1.0),
            )

            # v3.16.47 — Bootstrap-time exchange position health refresh.
            # Without this, the SpendableWidget waits ~5 minutes (the
            # tick-loop refresh cooldown) before showing real values.
            # On bot bootstrap, force-refresh once so the GUI shows
            # exchange-truth Realized P/L / cost basis immediately.
            try:
                _refreshed = await self.refresh_exchange_position_health(
                    force=True)
                if _refreshed:
                    logger.info(
                        "Bot %s bootstrap_exchange_state: position health "
                        "refreshed (realized=$%.4f, avg_entry=$%.8f, "
                        "trades=%d)",
                        self.bot_id,
                        self.stats.realized_pnl_exchange,
                        self.stats.avg_entry_exchange,
                        self.stats.exchange_trade_count)
            except Exception as _ph_exc:  # R28-OK: best-effort
                logger.warning(
                    "Bot %s bootstrap position-health refresh failed: %s "
                    "(will retry on first action tick)",
                    self.bot_id, _ph_exc)
            # v3.23.54 — YTD trade-count reconciliation. Operator
            # directive 2026-07-28: refresh_exchange_position_health
            # caps at get_my_trades(limit=500) so bots with >500 YTD
            # fills got stuck at 500 on the dashboard. Paginate from
            # the 2026-04-01 YTD anchor and take max(persisted,
            # exchange) so the internal counter self-heals without
            # ever overwriting a higher persisted value with a lower
            # API result (partial page / rate-limit safety).
            try:
                await self.sync_ytd_trade_count()
            except Exception as _ytd_exc:  # R28-OK: best-effort
                logger.warning(
                    "Bot %s bootstrap YTD trade-count sync failed: %s "
                    "(persisted counter retained)",
                    self.bot_id, _ytd_exc)
        except Exception as exc:  # sadp: R28 surface but don't crash startup
            logger.warning(
                "Bot %s bootstrap_exchange_state raised %s: %s "
                "(GUI will show pending until first tick)",
                self.bot_id, type(exc).__name__, exc,
            )

    # ------------------------------------------------------------------
    # MEM-253 — Pre-decision territory gate (operator directive 2026-04-23:
    # "Why not have a pre-buy/sell protection that checks Target Balance
    # BEFORE even sending a damn signal to the exchange. Would this not be
    # a more elegant solution?")
    #
    # This helper is called at the TOP of every buy decision path — before
    # TA is consulted, before the order is constructed, before _execute_buy.
    # The MEM-251 guard in _execute_buy remains as a last-ditch defense-in-
    # depth belt-and-suspenders; this pre-check is the primary layer that
    # keeps the bot from wasting tick cycles considering actions that can't
    # legally fire.
    # ------------------------------------------------------------------
    def _pre_buy_allowed(self, intended_cost: float, path: str,
                         ticker_price: float) -> tuple[bool, str]:
        """Return (allowed, reason).

        v3.16.50 — pre-decision territory gate aligned with the unified
        Target-Delta + Smart Ceiling defense-in-depth (MEM-251 v2). The
        rule:

          • Layer 1 — Target-Delta budget per path:
              fold_rebuy / unspecified: projected ≤ target + per_cycle_growth_budget
              zero_balance_initial_entry: projected ≤ target_balance × (1 + tol)
              hedge_replenish: projected ≤ current_position + hedge_bal
          • Layer 2 — Smart Ceiling (when enabled): projected ≤ anchor × multiple

        Use the authoritative anchor and the current in-memory holdings
        (cheap — no async exchange call here). The MEM-251 v2 guard inside
        _execute_buy separately re-validates against a fresh exchange
        balance. A pre-check using stale in-memory holdings is still
        correct-direction: if stale holdings say we're over, fresh data
        would almost certainly agree; if stale holdings say we're clear
        and fresh data says we're over, MEM-251 v2 catches it at the
        last moment.

        Pre-v3.16.50 this site computed `anchor × (1 + max_target_growth_pct
        /100)` as a hard ceiling — same fictional ceiling that v3.16.50
        retired across the codebase. Replaced with the layered model.

        sadp: R1 R28
        """
        try:
            _cap_pct = float(getattr(self.config, "max_target_growth_pct", 1.0))
            _anchor = float(getattr(self, "_anchor_target_balance",
                                    self._target_balance))
            _per_cycle_growth_budget = _anchor * (_cap_pct / 100.0)
            # v3.15.55 — convert to USD. Anchor and intended_cost are USD
            # by convention; ticker_price is in QUOTE units, so we need
            # the quote→USD multiplier for crypto-quoted pairs.
            _qrate = float(self._quote_to_usd or 1.0)
            _current_pos = float(self._current_holdings) * float(ticker_price) * _qrate
            _projected = _current_pos + float(intended_cost)
            _target = float(self._target_balance)
            _slip = 0.005  # 0.5% slippage tolerance

            # Layer 1 — per-path Target-Delta budget
            if path == "zero_balance_initial_entry":
                _budget_ceiling = _target * (1.0 + _slip)
            elif path == "hedge_replenish":
                # Hedge has its own bucket; sanity-check against current
                # position + hedge_bal as conservative upper bound.
                try:
                    _hedge_bal = float(getattr(self, "_hedge_bal", 0.0) or 0.0)
                except (TypeError, ValueError):
                    _hedge_bal = 0.0
                _budget_ceiling = _current_pos + _hedge_bal * (1.0 + _slip)
            elif path in ("fold_rebuy", "manual_tranche_fire"):
                # v3.16.53 — fold-back / manual-tranche-fire is a tranche-
                # consuming rebuy. Cost is bounded by tranche.usd at the
                # caller (per-tranche math). Position may legitimately
                # exceed target — that excess is the Tranche Surplus that
                # drives organic target growth via Phase B. Don't block
                # via Target-Delta math here; Layer 2 (Smart Ceiling) is
                # the only legitimate position-level cap for these paths.
                _budget_ceiling = _projected + 1.0  # effectively passes
            else:
                # unspecified: conservative — target + per-cycle growth budget
                _budget_ceiling = (
                    _target + _per_cycle_growth_budget) * (1.0 + _slip)
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

            # Layer 2 — Smart Ceiling (when enabled)
            if getattr(self.config, "position_ceiling_enabled", False):
                try:
                    _smart_mult = float(getattr(
                        self.config, "position_ceiling_multiple", 1.0))
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
                    # Smart Ceiling probe failed; trust Layer 1 result.
                    logger.debug("suppressed in %s: %s: %s", "_pre_buy_allowed", type(_sup).__name__, _sup)
            return True, ""
        except Exception as exc:  # R28-OK: error surfaced via tuple return; sadp R28 fail-closed
            # If the pre-check itself fails, refuse — cannot verify budget.
            return False, (
                f"MEM-253 PRE-BUY REFUSED (path={path}): pre-check raised "
                f"{type(exc).__name__}: {exc}. Fail-closed.")

    # ------------------------------------------------------------------
    # v3.20.9 — Risk-gate forensic snapshot emitter (audit Finding #10)
    # ------------------------------------------------------------------
    def _emit_risk_gate_snapshot(
        self,
        side: str,
        chain_result,
        summary,
        ticker_last: float,
    ) -> None:
        """If any risk gate blocked this side's chain, write a
        structured RISK GATE SNAPSHOT line to bot.log with the full
        voter panel at the moment of the block.

        Closes v3.20.6 audit cross-cutting finding #10 — "No per-
        indicator audit trail when risk gates fire — operator can't
        trace a CB to its cause." The risk gates (CircuitBreaker,
        SmartCeiling, Hysteresis) consume position/risk flags rather
        than voter output, so their `blocker_message` never reveals
        which indicators were what when they fired. This emitter
        binds the two together.

        Operator forensic pattern:
            grep "RISK GATE SNAPSHOT" bot.log
        returns every risk-blocked tick with side, blocker names,
        and the indicator state at that moment.

        Quiet by design: if no risk gate is in the blocked list, this
        emits nothing. Operators tailing bot.log don't see noise on
        normal ticks.

        sadp: R28 FL · R49 MDEL · R55 GOV · R62 FRG · R68 DPA
        """
        try:
            blocked_names = {n for n, _msg in (
                chain_result.blocked or [])}
        except Exception:  # R28-OK: forensic best-effort; defensive over unexpected ChainResult shape
            return
        # Intersect with the canonical risk-gate name set; if empty,
        # no risk gate blocked this tick — nothing to log.
        risk_blockers = blocked_names & _RISK_GATE_NAMES
        if not risk_blockers:
            return
        try:
            snapshot = _build_panel_snapshot(summary)
            # Stable ordering for grep + diff workflows.
            risk_blockers_sorted = sorted(risk_blockers)
            # Compact one-liner formatting. JSON-shaped dict keeps it
            # parseable by future tools/trade_attribution.py while
            # staying human-skimmable in bot.log.
            msg = (
                f"RISK GATE SNAPSHOT [{side.upper()}] "
                f"risk_blockers={risk_blockers_sorted} "
                f"ticker_last={ticker_last:.6g} "
                f"panel={snapshot}")
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=msg,
            )
        except Exception as exc:  # R28-OK: forensic snapshot must never crash the trading tick
            # Don't disrupt the tick if the forensic emit itself fails.
            # Log at debug for diagnostics but do not propagate.
            try:
                logger.debug(
                    "Bot %s risk-gate snapshot emit failed: %s: %s",
                    self.bot_id[:8], type(exc).__name__, exc)
            except Exception as _sup:  # R28-OK: even the debug-log fallback is best-effort
                logger.debug("suppressed in %s: %s: %s", "_emit_risk_gate_snapshot", type(_sup).__name__, _sup)

    # ------------------------------------------------------------------
    # v3.20.11 — Trade-fire forensic snapshot emitter
    # Companion to the v3.20.9 RISK GATE SNAPSHOT. Closes the
    # data-completeness gap that v3.20.6's Part 8 attribution
    # chapter implicitly assumed: when a trade actually FIRES,
    # capture the same indicator panel snapshot so the
    # `tools/trade_attribution.py` instrument can classify
    # consensus-driven vs single-voter-dominated vs override-fired
    # decisions from log alone, no manual triangulation.
    # ------------------------------------------------------------------
    def _emit_trade_fire_snapshot(
        self,
        side: str,
        summary,
        ticker_last: float,
        decision_extra: Optional[dict] = None,
    ) -> None:
        """Write a structured TRADE FIRED SNAPSHOT line to bot.log
        when a SCRUM or FOLD decision actually fires.

        Pairs with `_emit_risk_gate_snapshot` (v3.20.9): together they
        capture both sides of every decision tick that matters —
        risk-blocked AND fired. The trade-attribution tool grep
        pattern `RISK GATE SNAPSHOT|TRADE FIRED SNAPSHOT` returns
        the full decision audit trail for any window.

        `decision_extra` is an optional dict the caller may pass with
        side-specific context (asset size, tranche count, override-
        engaged flag, etc.) — surfaced under the `extra` key in the
        emitted message so the attribution classifier can use it to
        bucket the trade into one of the 5 Part 8 taxonomy
        categories (Consensus-Driven / Single-Voter-Dominated /
        Override-Fired / Gate-Refused-Then-Manual / Noise-Threshold-
        Tripped).

        Same resilience contract as the risk-gate emitter: wrapped
        in try/except per R28 FL; failures swallow at logger.debug
        so the forensic emit can never crash the trading tick.

        sadp: R28 FL · R49 MDEL · R55 GOV · R62 FRG · R68 DPA
        """
        try:
            snapshot = _build_panel_snapshot(summary)
            extra_str = ""
            if decision_extra:
                # Sort keys for deterministic output (grep + diff)
                extra_kv = ", ".join(
                    f"{k}={v!r}" for k, v
                    in sorted(decision_extra.items()))
                extra_str = f" extra={{{extra_kv}}}"
            msg = (
                f"TRADE FIRED SNAPSHOT [{side.upper()}] "
                f"ticker_last={ticker_last:.6g} "
                f"panel={snapshot}{extra_str}")
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=msg,
            )
        except Exception as exc:  # R28-OK: forensic emit must never crash the trading tick
            try:
                logger.debug(
                    "Bot %s trade-fire snapshot emit failed: %s: %s",
                    self.bot_id[:8], type(exc).__name__, exc)
            except Exception as _sup:  # R28-OK: debug-log fallback is best-effort
                logger.debug("suppressed in %s: %s: %s", "_emit_trade_fire_snapshot", type(_sup).__name__, _sup)

    def _emit_voting_panel_snapshot_at_fire(
        self,
        side: str,
        trade_action: str,
    ) -> None:
        """v3.23.6 — emit ``bot.voting_panel_snapshot`` at trade-fire time.

        Called immediately AFTER every ``self._bus.emit("trade.filled",
        ...)`` site so the VotingSummary panel state that drove the
        trade gets persisted to voting.log alongside the trade event.

        Operator pin 2026-06-13: snapshot panel outputs ONLY at trade
        execution (not per-tick). LogManager._on_voting_panel_snapshot_bus
        routes the payload to ~/.acervator_logs/trade/voting.log as
        NDJSON.

        Fail-soft pin from spec: if ``self._last_summary`` is None
        (early-tick startup window, manual-fire bypass, etc.) emit with
        ``panel={}`` instead of skipping — the consumer null-checks
        downstream. We do NOT fail-loud here per existing patterns.
        """
        try:
            panel: dict = {}
            try:
                _summary = getattr(self, "_last_summary", None)
                if _summary is not None:
                    # asdict() on the dataclass — signals is a list of
                    # Signal sub-dataclasses, also asdict'able. The
                    # SignalDirection enum on each Signal stringifies
                    # via its .value at write time (json.dumps handles
                    # the str-based StrEnum cleanly).
                    panel = asdict(_summary)
            except Exception:  # R28-OK: voting-log telemetry; must not break tick
                panel = {}
            self._bus.emit(
                "bot.voting_panel_snapshot",
                bot_id=self.bot_id,
                exchange=getattr(self.config, "exchange_id", "") or "",
                symbol=getattr(self.config, "symbol", "") or "",
                side=str(side or "").upper(),
                trade_action=str(trade_action or "") or "",
                panel=panel,
            )
        except Exception as _sup:  # R28-OK: voting-log telemetry; must not break tick
            logger.debug("suppressed in %s: %s: %s", "_emit_voting_panel_snapshot_at_fire", type(_sup).__name__, _sup)

    def _emit_gate_decision_at_fire(
        self,
        side: str,
        trade_action: str,
    ) -> None:
        """v3.23.11 — emit ``bot.gate_decision`` at trade-fire time (D-NEW-A).

        Mirrors the v3.23.6 voting helper pattern. Replaces the v3.23.6
        in-tick gate emit block (previously at the tail of ``tick()``)
        which was position-buggy: gated on ``_trade_fired_this_tick`` and
        located such that only the organic SCRUM fire path (upstream in
        tick()) could reach it. CARTRIDGE_FOLD, CARTRIDGE_SCRUM, FOLD,
        HEDGE, DIST, ENTRY, AUTO_DETONATION and operator manual fires all
        bypassed it — empirical 1/9 = 11.1% gate.log coverage at v3.23.10.

        Called immediately AFTER every ``self._bus.emit("trade.filled",
        ...)`` site (10 sites, same as voting helper) so every fired
        trade emits a paired gate.log row. ``self._last_gate_state`` is
        read at fire time; for in-tick sites that state was just refreshed
        by the scrum/fold gate evaluators upstream in tick() (L6034 /
        L6721 pre-D-NEW-A); for out-of-tick sites (manual_fire_tranche,
        self_destruct, _execute_manual_rebalance, _execute_detonation)
        the state reflects the most-recent autonomous tick's evaluation
        — informational for the History tab read-time joiner, not
        authoritative for those fires (consumer differentiates via
        trade_action / operator_initiated).
        """
        try:
            self._bus.emit(
                "bot.gate_decision",
                bot_id=self.bot_id,
                exchange=getattr(self.config, "exchange_id", "") or "",
                symbol=getattr(self.config, "symbol", "") or "",
                side=str(side or "").upper(),
                trade_action=str(trade_action or "") or "",
                scrum_armed=bool(
                    self._last_gate_state.get("scrum_armed", False)),
                fold_armed=bool(
                    self._last_gate_state.get("fold_armed", False)),
                scrum_blockers=list(
                    self._last_gate_state.get("scrum_blockers") or []),
                fold_blockers=list(
                    self._last_gate_state.get("fold_blockers") or []),
                scrum_fixture=self._last_gate_state.get("scrum_fixture"),
                fold_fixture=self._last_gate_state.get("fold_fixture"),
                # v3.24.10 — tranche + compounding snapshot. Operator
                # directive 2026-08-02: "We need more data on what the
                # Tranches are doing ... this may help us troubleshoot
                # the compounding issue later."
                #
                # Prior gate rows carried only n_fold_tranches (a bare
                # count) inside fold_fixture, and NOTHING for the Stack
                # side or for compounding state. When a fold produced
                # no target growth there was no recorded evidence of
                # why. These two blocks close that.
                tranche_snapshot=self._tranche_snapshot(),
                compounding_snapshot=self._compounding_snapshot(),
            )
        except Exception as _gate_exc:  # noqa: BLE001 - see below
            # v3.24.10 — was `except Exception: pass`, which meant a
            # failed gate emit vanished with no trace and silently
            # produced an unpaired trade. The trade path still must
            # not break, so we swallow — but the failure is now
            # COUNTED so the telemetry report can surface it instead
            # of it looking like the trade simply had no gate data.
            try:
                from ..core.feature_telemetry import get_telemetry
                get_telemetry().record_exception(
                    "live.gate_decision.emit", _gate_exc)
            except Exception as _sup:  # noqa: BLE001,S110 - advisory only
                logger.debug("suppressed in %s: %s: %s", "_emit_gate_decision_at_fire", type(_sup).__name__, _sup)
            logger.debug(
                "Bot %s gate_decision emit failed: %s",
                self.bot_id, _gate_exc)

    def _tranche_snapshot(self) -> dict:
        """v3.24.10 — fold + stack tranche state at fire time.

        Fires per-trade (not per-tick), so walking the tranche lists
        is affordable. Returns aggregates rather than full contents:
        a bot can hold 49+ fold tranches and embedding every one
        would bloat gate.log by an order of magnitude for little
        diagnostic gain. Count / USD / unit totals / price extremes
        answer 'what were the tranches doing' without that cost.
        """
        snap: dict = {}
        try:
            fold = list(getattr(self, "_fold_tranches", []) or [])
            f_usd = sum(float(t.get("usd", 0) or 0) for t in fold)
            f_units = sum(float(t.get("units", 0) or 0) for t in fold)
            f_refs = [float(t.get("ref", 0) or 0) for t in fold
                      if float(t.get("ref", 0) or 0) > 0]
            snap["fold_count"] = len(fold)
            snap["fold_total_usd"] = round(f_usd, 6)
            snap["fold_total_units"] = round(f_units, 8)
            snap["fold_ref_min"] = round(min(f_refs), 8) if f_refs else 0.0
            snap["fold_ref_max"] = round(max(f_refs), 8) if f_refs else 0.0
        except Exception as _f_exc:  # noqa: BLE001 - snapshot best-effort
            snap["fold_error"] = f"{type(_f_exc).__name__}"
        try:
            stack = list(getattr(self, "_stack_tranches", []) or [])
            s_prices = []
            s_usd = 0.0
            for t in stack:
                # Stack entries may be dicts or objects depending on
                # the path that created them — handle both.
                px = (t.get("price") if isinstance(t, dict)
                      else getattr(t, "price", 0))
                uu = (t.get("usd") if isinstance(t, dict)
                      else getattr(t, "usd", 0))
                if px:
                    s_prices.append(float(px))
                if uu:
                    s_usd += float(uu)
            snap["stack_count"] = len(stack)
            snap["stack_total_usd"] = round(s_usd, 6)
            snap["stack_price_min"] = (
                round(min(s_prices), 8) if s_prices else 0.0)
            snap["stack_price_max"] = (
                round(max(s_prices), 8) if s_prices else 0.0)
        except Exception as _s_exc:  # noqa: BLE001 - snapshot best-effort
            snap["stack_error"] = f"{type(_s_exc).__name__}"
        return snap

    def _compounding_snapshot(self) -> dict:
        """v3.24.10 — target-growth state at fire time.

        The compounding question is 'did this fold raise the target,
        and if not, why not'. That needs the anchor, the live target,
        the accrued delta between them, the per-cycle cap, and how
        much of the cap this cycle already consumed. None of it was
        recorded before, which is why the earlier compounding
        investigation had to reason from bot_state snapshots taken
        long after the fact.
        """
        snap: dict = {}
        try:
            target = float(getattr(self, "_target_balance", 0.0) or 0.0)
            anchor = float(
                getattr(self, "_anchor_target_balance", 0.0) or 0.0)
            growth_pct = float(getattr(
                self.config, "max_target_growth_pct", 0.0) or 0.0)
            snap["target_balance"] = round(target, 6)
            snap["anchor_target_balance"] = round(anchor, 6)
            # Positive => target has grown above anchor via compounding.
            snap["accrued_growth_usd"] = round(target - anchor, 6)
            snap["max_target_growth_pct"] = growth_pct
            snap["cycle_growth_budget_usd"] = round(
                anchor * growth_pct / 100.0, 6)
            snap["fold_cycle_cap_consumed"] = round(float(getattr(
                self, "_fold_cycle_cap_consumed", 0.0) or 0.0), 6)
            snap["profit_folding_active"] = bool(getattr(
                self.config, "profit_folding_active", False))
        except Exception as _c_exc:  # noqa: BLE001 - snapshot best-effort
            snap["error"] = f"{type(_c_exc).__name__}"
        return snap

    # ------------------------------------------------------------------
    # Main trading tick (v1.1 — uses VotingEngine)
    # ------------------------------------------------------------------
    async def tick(self) -> None:
        # sadp: R1 R5 R6 R28 R29 R31  # target-increment(R1) bearish-conf(R5) two-paths(R6) fail-loudly(R28) idempotent-orders(R29)
        symbol = self.config.symbol

        # v3.23.42 — CapitalReservationRegistry ensure per tick (F62).
        # Idempotent: reserves on first call with price, updates when
        # target_balance / personal_hold_qty change, always heartbeats.
        # Safe when price is not yet loaded (helper no-ops).
        try:
            await self._ensure_capital_reservation(
                float(getattr(self, "_last_price", 0) or 0))
        except Exception as _crr_tick_exc:  # noqa: BLE001 - reservation best-effort
            logger.debug(
                "Bot %s reservation ensure at tick top raised: %s",
                self.bot_id, _crr_tick_exc)

        # v3.13.8 MEM-188 / Chunk 4 — Read Rate tick-skip gate.
        # Operator sets scrum_read_rate_min (minutes between reads in
        # SEARCH mode). In TRACK/FIRE mode, skip shrinks by 10x so the
        # bot polls the exchange much more frequently when price is near
        # the band (catches fast moves). Ported from simulator.py:5507, 5324.
        #
        # Base tick runs at tick_interval (5s default). read_rate_min=5 →
        # base_skip = ceil(5 min / 5 s) = 60 ticks between actual reads
        # in SEARCH mode, 6 ticks in TRACK/FIRE.
        #
        # Rationale for skipping at the tick()-level (vs. scheduler-level):
        # the scheduler ticks are cheap and coordinator logic (phantom
        # bots, indicator updates) still runs every tick. Only the
        # expensive exchange+TA pipeline is gated.
        #
        # MEM-242 bugfix: when a manual fire is pending, BYPASS the
        # skip gate entirely. The prior force_fire approach of bumping
        # _tick_counter to _tick_skip-1 broke when the next tick
        # recomputed _tick_skip larger (e.g. FIRE→SEARCH mode drop
        # multiplied the skip by 10x). The operator saw "no kaboom"
        # because the rebalance was waiting up to 5 minutes for the
        # SEARCH read-rate window. Hard-bypass is correct: Manual Fire
        # is an operator override and MUST run on the next scheduler
        # tick, not the next polling window.
        if self.config.scrum_read_rate_min > 0 and not self._manual_fire_pending:
            _tick_sec = max(self.tick_interval, 0.1)
            _base_skip = max(1, int((self.config.scrum_read_rate_min * 60) / _tick_sec))
            self._tick_skip_search = _base_skip
            # In TRACK/FIRE, poll 10x faster
            if self._scrum_target_mode in ('track', 'fire'):
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
                    _tk("tick.08.001.event.throttled", actual=True,
                        context={"bot_id": self.bot_id,
                                 "counter": self._tick_counter,
                                 "skip": self._tick_skip,
                                 "read_rate_min":
                                     self.config.scrum_read_rate_min})
                except Exception as _sup:  # noqa: BLE001,S110 - advisory
                    logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
                return
            # Reset counter on action tick
            self._tick_counter = 0
            # The satisfied path. Emitted so silence is never ambiguous:
            # a run with zero `tick.08.002.event.worked` records did
            # not work, and a run with no records at all was not
            # collected. Those must not look the same.
            try:
                from src.core.signal_contract import emit as _tk2
                _tk2("tick.08.002.event.worked", actual=True,
                     context={"bot_id": self.bot_id,
                              "skip": self._tick_skip})
            except Exception as _sup:  # noqa: BLE001,S110 - advisory
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
        elif self._manual_fire_pending:
            # Manual fire bypass: reset counter so the next real poll
            # cycle starts fresh after we handle the override.
            self._tick_counter = 0

        # v3.16.46 — Exchange-pulled position health refresh.
        # Throttled internally (5-min cooldown). Best-effort; failures
        # don't block the tick. Runs on action ticks only (not skipped
        # ticks) so the API call rate is bounded by tick_skip × cooldown.
        try:
            await self.refresh_exchange_position_health()
        except Exception as _sup:  # R28-OK: position health is decorative
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        # --- Initialisation ---
        if not self._initialised:
            ticker = await self._get_ticker(symbol)
            self._last_price = ticker.last
            self.stats.current_price = ticker.last
            # v3.15.55 — bootstrap quote→USD rate before any USD math.
            # Best-effort; tick continues even on failure (rate stays at
            # 1.0 default — wrong for crypto-quoted pairs but the
            # _refresh path emits a single warning so the operator sees
            # the degraded state rather than silent mis-evaluation).
            try:
                await self._refresh_quote_to_usd()
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

            # MEM-226 — Startup balance handshake. Previously the bot
            # trusted a single get_balance() call and silently accepted
            # Balance(free=0.0) if the asset key was absent from the
            # fetch_balance response. Two callers in this codebase read
            # balance independently (the GUI connection path in
            # main_window.py:2557 uses sync fetch_balance; this path
            # uses async get_balance via _call_sync). They can disagree.
            #
            # Handshake: fetch TWICE with a small gap and require both
            # reads to agree within 0.1% tolerance before trusting the
            # result. If they disagree, refuse to mark the bot
            # _initialised; the outer run_loop will retry the tick.
            # If both reads agree but report zero, trust that — it is
            # a legitimate zero (no prior position). The signal we are
            # defending against is a TRANSIENT zero from a stale/racy
            # response that would otherwise cause the bot to later fire
            # an initial-entry buy on top of an existing position.
            try:
                _bal1 = await self._get_balance(
                    self.config.target_asset)
                # MEM-255: use `total` (everything owned) not `free` (only
                # currently spendable). Matters for BTC / expensive tokens
                # where Coinbase may classify some portion as used/locked
                # (active orders, collateral). `total` is what the operator
                # SEES on the exchange UI; that's what the bot must track
                # for position value. Fall back to free if total is absent
                # or zero.
                _h1 = float(getattr(_bal1, "total", 0) or _bal1.free or 0)
                await asyncio.sleep(0.25)
                _bal2 = await self._get_balance(
                    self.config.target_asset)
                _h2 = float(getattr(_bal2, "total", 0) or _bal2.free or 0)
            except Exception as _hs_exc:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(
                        f"INIT HANDSHAKE FAILED: exchange balance fetch "
                        f"raised ({_hs_exc}). Bot NOT marked initialised. "
                        f"Outer loop will retry on next tick. Refusing to "
                        f"proceed with unknown holdings."))
                logger.warning(
                    "Bot %s init handshake raised: %s; will retry",
                    self.bot_id, _hs_exc)
                raise  # let outer loop count this as an error + retry

            _max_h = max(_h1, _h2)
            _abs_diff = abs(_h1 - _h2)
            _rel_diff = _abs_diff / _max_h if _max_h > 0 else 0.0
            if _max_h > 0 and _rel_diff > 0.001:
                # Two reads disagree by >0.1%. Could be a fill-in-flight
                # or a racy response. Do NOT trust either; let the
                # outer loop retry this init tick.
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(
                        f"INIT HANDSHAKE MISMATCH: two successive "
                        f"get_balance reads returned "
                        f"{_h1:.6f} vs {_h2:.6f} ({_rel_diff*100:.2f}% "
                        f"diff). Refusing to initialise on an uncertain "
                        f"read. Retrying next tick."))
                logger.warning(
                    "Bot %s init handshake mismatch: %.6f vs %.6f",
                    self.bot_id, _h1, _h2)
                return  # do NOT set _initialised; retry

            # Connector-sentinel defense: ccxt_connector.get_balance now
            # flags Balance.absent when the exchange OMITTED the currency
            # (vs explicitly reporting zero). Refuse to initialise on an
            # absent read regardless of agreement — two deterministic lies
            # from the same filter still agree, but they are still lies.
            # Defense-in-depth alongside MEM-259 VolumeGuard-disable.
            if getattr(_bal1, "absent", False) or getattr(_bal2, "absent", False):
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(
                        f"INIT HANDSHAKE REFUSED (absent-sentinel): "
                        f"exchange OMITTED "
                        f"{self.config.target_asset} from "
                        f"fetch_balance response "
                        f"(bal1.absent={getattr(_bal1, 'absent', '?')}, "
                        f"bal2.absent={getattr(_bal2, 'absent', '?')}). "
                        f"Cannot verify holdings. Will NOT initialise bot "
                        f"on a structurally-zeroed read. Retrying next tick."))
                logger.warning(
                    "Bot %s init handshake refused — %s absent from exchange response",
                    self.bot_id, self.config.target_asset)
                return  # do NOT set _initialised; retry

            # Persisted-lot cross-check: if _main_lots (restored from
            # state) says this bot held N units and the handshake reports
            # zero, the exchange response is almost certainly incomplete
            # (or the bot was manually liquidated off-platform, in which
            # case operator intervention is required to clear _main_lots).
            # Either way, refusing is safer than trusting a suspicious zero.
            _lots_units = sum(
                float(lot.get("units", 0) or 0)
                for lot in self._main_lots)
            if _h2 == 0.0 and _lots_units > 0.0:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(
                        f"INIT HANDSHAKE REFUSED (lots-cross-check): "
                        f"exchange reports 0 {self.config.target_asset} "
                        f"but restored state shows {_lots_units:.6f} "
                        f"units in _main_lots. Refusing to overwrite "
                        f"persisted holdings with a suspicious zero. If "
                        f"the position was genuinely liquidated "
                        f"off-platform, operator must clear _main_lots "
                        f"via state reset tool. Retrying next tick."))
                logger.warning(
                    "Bot %s init handshake refused — exchange=0 vs "
                    "restored lots=%.6f",
                    self.bot_id, _lots_units)
                return  # do NOT set _initialised; retry

            # v3.24.85 - A BOT THAT HAS NEVER SCRUMMED HAS NO HISTORY
            # TO PROTECT, SO THE EXCHANGE IS ITS OPENING POSITION.
            #
            # v3.23.43 made `_main_lots` the sole source of holdings and
            # applied it ALWAYS. The rule exists to stop a bot claiming
            # units that belong to the operator, a sibling bot, or a
            # prior bot on the asset -- the ETH/BTC $178 surplus. Every
            # one of those is a statement about a bot with TRADING
            # HISTORY. A bot that has never scrummed has no history for
            # a surplus to be measured against: there is no "excess",
            # only its position.
            #
            # Applied unconditionally, the rule made a brand-new bot
            # report $0.00 while the operator was looking at coins on
            # the exchange.
            #
            # LIVE INCIDENT 2026-08-09 (v3.24.51). Operator created BICO
            # and IMU with target $25 and manually bought the first $25
            # of each. `_main_lots` was empty, so `_current_holdings`
            # was forced to 0.0 and `position_value` to $0.00. Max
            # Cartridge Fire computed
            # `delta = current_value - target_balance = -$25` and, with
            # its gates deliberately bypassed, bought a SECOND $25:
            #   03:07:57 CARTRIDGE_FOLD BICO/USDC BUY 347.96 @ 0.0706380489
            #   03:11:19 CARTRIDGE_FOLD IMU/USDC  BUY 6350.0  @ 0.0039
            # Both gate records read `scrum_armed=false fold_armed=false
            # blockers=["pre-tick"]` -- nothing was armed, because that
            # path does not consult the gate chain.
            #
            # THE CONDITION IS "NEVER SCRUMMED", NOT "NO LOTS".
            # `_tranches_created_lifetime == 0` means no scrum has ever
            # fired, so nothing in `_main_lots` was earned by strategy.
            # Keying on empty lots instead would have missed exactly the
            # bots that need this: BICO and IMU now hold a lot from that
            # erroneous cartridge buy, so their lots are non-empty while
            # their scrum history is still zero.
            #
            # ISOLATION IS CONDITIONAL, AS IT ALWAYS SHOULD HAVE BEEN.
            # It matters only when another bot targets the same asset --
            # e.g. BICO/USDC and BICO/BTC each holding $25. That case
            # subtracts the siblings' tracked units so contested
            # inventory is never double-claimed. With no sibling there
            # is nothing to isolate from, and `has_sibling_target_bots`
            # is the predicate the codebase already had for the call.
            #
            # NOT CAPPED AT TARGET. Adoption records what is HELD; the
            # target ceiling governs what may be BOUGHT. Capping here
            # would leave real units unattributed and rebuild the same
            # blind spot one layer down.
            _never_scrummed = int(getattr(
                self, "_tranches_created_lifetime", 0) or 0) == 0
            if _never_scrummed and _h2 > 0:
                _sib_units = 0.0
                _mgr = getattr(self, "_bot_manager", None)
                if _mgr is not None:
                    try:
                        if _mgr.has_sibling_target_bots(
                                self.bot_id, self.config.target_asset):
                            _sib_units = float(_mgr.sum_sibling_tracked_units(
                                self.bot_id, self.config.target_asset) or 0.0)
                    except Exception as _sib_exc:  # noqa: BLE001
                        # An unknown sibling position is treated as
                        # owning EVERYTHING. Under-claiming costs a log
                        # line; over-claiming spends the operator's
                        # coins.
                        _sib_units = float(_h2)
                        logger.warning(
                            "Bot %s adoption: sibling query raised (%s); "
                            "claiming nothing", self.bot_id, _sib_exc)
                _own = max(0.0, float(_h2) - _sib_units)

                # v3.24.92 - THE OPERATOR'S CEILING ON ADOPTION.
                #
                # Everything above this line INFERS ownership from what
                # the exchange holds. Nothing on the exchange
                # distinguishes "the seed the operator bought for this
                # bot" from "coins the operator holds and wants left
                # alone", so the inference cannot get that right on its
                # own and must not be allowed to try.
                #
                # `max_adoptable_usd` is the declaration, defaulting
                # to `target_balance`. Hummingbot's `balance limit` is
                # the same idea -- documented as "Sets the amount limit
                # on how much assets Hummingbot can use in an exchange
                # or wallet. This can be useful when running multiple
                # bots on different trading pairs with same tokens."
                # https://hummingbot.org/client/global-configs/balance-limit/
                #
                # Applied in UNITS at the current price, because the
                # declaration is in USD and lots are in units.
                _px_cap = float(getattr(ticker, "last", 0.0) or 0.0)
                _cap_usd = float(getattr(
                    self.config, "max_adoptable_usd", 0.0) or 0.0)
                if _cap_usd <= 0:
                    _cap_usd = float(self._target_balance or 0.0)
                _uncapped = _own
                _was_capped = False
                if (_cap_usd > 0 and _px_cap > 0
                        and _own * _px_cap > _cap_usd):
                    _own = _cap_usd / _px_cap
                    _was_capped = True
                if _was_capped:
                    # The operator holds more of this asset than the bot
                    # is allowed to take. That is a fact worth stating
                    # once, loudly: the surplus stays theirs, and the
                    # bot will not be quietly reaching for it later.
                    self._bus.emit("bot.log", bot_id=self.bot_id, message=(
                        f"ADOPTION CAPPED: exchange holds "
                        f"{_uncapped:.6f} {self.config.target_asset} but "
                        f"this bot may adopt at most ${_cap_usd:.2f} "
                        f"({_own:.6f} units @ ${_px_cap:.8f}). The "
                        f"remaining {_uncapped - _own:.6f} units stay "
                        f"unmanaged. Raise max_adoptable_usd to change "
                        f"this."))
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
                                "withheld_units": round(
                                    _uncapped - _own, 10),
                            })
                    except Exception as _sup:  # noqa: BLE001,S110 - advisory
                        logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

                _held = sum(float(lot.get("units", 0) or 0)
                            for lot in self._main_lots)
                if _own > 0.0 and abs(_own - _held) > 1e-12:
                    _px = float(getattr(ticker, "last", 0.0) or 0.0)
                    # Cost basis from the exchange's own history when it
                    # is known -- the operator paid a real price and the
                    # MEM-171 initial_buy_price floor derives from it.
                    # Current price is the fallback and is logged AS a
                    # fallback rather than presented as fact.
                    _basis_src = "ticker"
                    _basis = _px
                    try:
                        _cb = float(getattr(
                            self.stats,
                            "cost_basis_total_exchange", 0.0) or 0.0)
                        if _cb > 0:
                            _basis = _cb / _own
                            _basis_src = "exchange cost basis"
                    except (TypeError, ValueError, ZeroDivisionError) as _sup:
                        logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
                    if _basis > 0:
                        # ONE lot replaces the pre-scrum bookkeeping.
                        # Safe precisely because no scrum has fired:
                        # nothing here was earned, so nothing is lost.
                        # The `sum(units) == _current_holdings`
                        # invariant (see the note at the top of this
                        # class) is preserved by the assignment below.
                        self._main_lots = [{
                            "units": _own,
                            "initial_buy_price": _basis,
                        }]
                        self._bus.emit("bot.log", bot_id=self.bot_id, message=(
                            f"OPENING POSITION ADOPTED: {_own:.6f} "
                            f"{self.config.target_asset} held on the exchange "
                            f"(${_own * _px:.2f} @ ${_px:.8f}) is this bot's "
                            f"opening position; cost basis ${_basis:.8f} from "
                            f"{_basis_src}. This bot has never scrummed, so "
                            f"it has no earned history to protect"
                            + (f"; {_sib_units:.6f} units excluded as sibling"
                               f"-tracked" if _sib_units > 0 else "")
                            + f". Previously tracked {_held:.6f}."))
                        logger.info(
                            "Bot %s adopted opening position: %.8f %s @ %.8f "
                            "(was %.8f, sibling-tracked %.8f)",
                            self.bot_id, _own, self.config.target_asset,
                            _basis, _held, _sib_units)

            # Holdings follow `_main_lots` -- now including an adopted
            # opening position when the bot has never scrummed.
            self._current_holdings = sum(
                float(lot.get('units', 0) or 0)
                for lot in self._main_lots)
            self._initialised = True
            _qrate = float(self._quote_to_usd or 1.0)
            _init_usd = self._current_holdings * ticker.last * _qrate
            self._bus.emit('bot.log', bot_id=self.bot_id,
                message=(
                    f'INIT HANDSHAKE OK: position=${_init_usd:.2f} '
                    f'verified across 2 reads within tolerance. '
                    f'(forensic: {self._current_holdings:.6f} '
                    f'{self.config.target_asset} @ ${ticker.last:.8f}'
                    f'{chr(44)+chr(32)+f"quote-USD={_qrate:.4f}" if abs(_qrate - 1.0) > 1e-9 else ""})'))

            # MEM-248: USD-first framing. Lead with position vs target in USD;
            # relegate coin count + price to forensic detail.
            # v3.15.55 — quote→USD-aware.
            _init_usd = self._current_holdings * ticker.last * float(self._quote_to_usd or 1.0)
            _init_delta = _init_usd - self._target_balance
            _init_region = ("on-target" if abs(_init_delta) < max(self._target_balance * 0.001, 0.01)
                            else ("above target by " + f"${_init_delta:+.2f}" if _init_delta > 0
                                  else "below target by " + f"${_init_delta:+.2f}"))
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"Scrumming init: {symbol} position=${_init_usd:.2f} "
                         f"vs target=${self._target_balance:.2f} ({_init_region}). "
                         f"(forensic: {self._current_holdings:.6f} "
                         f"{self.config.target_asset} @ ${ticker.last:.8f})"))
            vis = "INVISIBLE" if self._invisible else "ORDER BOOK"
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"  Mode: {vis}"
                        f"{' + AGGRESSIVE' if self._aggressive else ''}")

            # Start phantom balance bots
            # v3.16.36 — P0g diagnostic: log the gate decision once per
            # bot lifecycle so we can correlate "phantoms turned on
            # after restart" with the actual flag state at the moment
            # the auto-start gate evaluated. If this logs
            # `_phantoms_enabled=False` but phantoms still appear
            # active, the bug is somewhere ELSE (GUI display, manager
            # event subscription, etc.).
            if not getattr(self, "_phantom_gate_logged", False):
                logger.info(
                    "P0g-DIAG | bot=%s tick-gate _phantoms_enabled=%s "
                    "_phantoms_started=%s timeframes=%s",
                    self.bot_id[:8],
                    self._phantoms_enabled,
                    self._phantoms_started,
                    self._phantom_timeframes)
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
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"  Phantoms: {len(self._phantom_timeframes)} TFs active "
                            f"({', '.join(self._phantom_timeframes)})")
                if self._phantom_tf_dropped_note:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=self._phantom_tf_dropped_note)
            return

        # --- MEM-208 periodic reconciliation ---
        # Every _reconcile_interval ticks, re-fetch exchange balance and
        # compare. On drift above tolerance, reset internal state. This
        # catches any divergence that leaked through (manual trades via
        # exchange UI, exchange-side margin liquidations, any future
        # accounting pathology we haven't identified yet). Cheap safety
        # net: one API call every ~10 minutes at default 30s tick cadence.
        self._reconcile_tick_counter += 1
        if (self._reconcile_tick_counter >= self._reconcile_interval
                and self._reconcile_interval > 0):
            self._reconcile_tick_counter = 0
            try:
                await self._reconcile_holdings(reason="periodic")
            except Exception as exc:
                logger.debug("Bot %s periodic reconcile raised: %s",
                            self.bot_id, exc)

        # --- Zero-balance initial acquisition (v3.1.6) ---
        # MEM-197 (Session 23): Operator directive — full scrum discipline
        # applies to EVERY buy, including initial acquisition and any buy
        # after a manual sell empties the position. No more "bearish TA =
        # buy" bypass. The same gates that govern fold rebuys apply here:
        #   (1) BB data must be computable (≥30 candles with valid bands)
        #   (2) Price must be structurally below midline (bb_pos ≤ 0.30)
        #   (3) Scrum state machine must be in FIRE mode on LOWER side
        #       (price within fire_pct of lower band), OR _dist_to_band
        #       must have reached detect_pct threshold — the "70%" rule
        #   (4) TA consensus must be BEARISH (accumulation-trading thesis
        #       — buy during decline, not during rally)
        # Without all four, the bot waits. Manual sell does NOT permit
        # undisciplined re-entry — the bot must wait for a proper fold
        # setup to develop before re-entering.
        ticker = await self._get_ticker(symbol)
        self.stats.current_price = ticker.last
        # v3.15.55 — refresh quote→USD rate before any USD-vs-target math.
        # For USD-quoted pairs this is a no-op (returns 1.0 immediately);
        # for crypto-quoted pairs (BTC/ETH, etc.) it caches the
        # {QUOTE}/USD ticker.last so current_value below is in USD.
        try:
            await self._refresh_quote_to_usd()
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        # Item 9 -- tranche despawn timer. Placed with the Stack
        # reconcilers because it sweeps the same two ledgers, and ABOVE
        # the below-interval return further down, which would otherwise
        # skip the sweep on every quiet tick. Synchronous by design: a
        # list filter with no I/O and no await, so it adds nothing to
        # what already runs on the Qt GUI thread. Returns on its first
        # line when the setting is 0, which is the default.
        #
        # NOT INSIDE A TRY, and it does not need one. The nearest try
        # above closes on the line before this comment. Every number
        # this sweep converts goes through `as_finite_float` first, so
        # no reachable state makes it raise -- which is the whole reason
        # that helper exists.
        self._despawn_aged_tranches()

        # v3.23.44 -- Stack Mode (Invisible) STAGE ONE: activation only.
        # Marks every pending tranche whose target price the market has
        # crossed as an ACTIVATED candidate. It places NO order. Spending
        # is stage two, `_spend_activated_stack_tranches`, which runs
        # inside the SCRUM gate chain's should_fire block far below.
        #
        # Operator directive 2026-08-11: "tranches do not supersede any
        # trading gates. They are only 'used' when a valid trading
        # condition occurs." Before v3.23.44 this call fired a MARKET
        # sell from here -- above the dust-band, manual-fire, wire-stack,
        # max-cartridge, detonation, zero-balance-acquisition, hard
        # circuit-breaker, below-interval and insufficient-candle returns
        # that end a tick, and above the chain itself. None of the
        # reconciler's own conditions is a trading gate, so the sell could
        # land on a tick the bot had refused to trade on, or on a tick
        # that never reached a trading decision at all.
        #
        # No-op when stack_mode is off, no pending tranches exist, or the
        # bot is not in Invisible mode.
        try:
            await self._reconcile_stack_tranches_invisible(
                current_price=float(ticker.last))
        except Exception as _stack_exc:  # sadp: R28 CBF — surface loudly
            logger.warning(
                "Bot %s stack reconciler raised: %s",
                self.bot_id, _stack_exc)

        # v3.23.28 — Stack Mode (Visible) tick reconciliation. Polls the
        # exchange for open orders; tranches whose order_id is no longer
        # open are inspected via get_order to determine filled vs
        # cancelled. No-op when Invisible mode or no pending Visible
        # tranches exist.
        try:
            await self._reconcile_stack_tranches_visible()
        except Exception as _stack_v_exc:  # sadp: R28 CBF — surface loudly
            logger.warning(
                "Bot %s visible stack reconciler raised: %s",
                self.bot_id, _stack_v_exc)
        # v3.23.43 — retired _refresh_multi_base_isolation. Scrumming
        # bots no longer detect siblings or attribute across a shared
        # exchange pool; each bot owns exactly what is in its own
        # _main_lots and derives _current_holdings from that source
        # alone. Cross-bot capital protection is handled by
        # CapitalReservationRegistry.

        # current_value is in USD: base_units × quote_price × quote→USD.
        current_value = (
            self._current_holdings * ticker.last * float(self._quote_to_usd or 1.0)
        )

        # v3.15.79 — Compute delta and update conditional opposing-
        # direction hysteresis state EARLY in the tick (before the
        # cartridge gate at line ~2925) so the cartridge sees FRESH
        # hysteresis state. Pre-v3.15.79 the update lived ~line 3276,
        # AFTER the cartridge gate — which meant immediately after a
        # fill (state cleared by _reset_opposing_hysteresis_after_fill),
        # cartridge would see armed=False on the very next tick and
        # fire an opposing trade at near-identical price. That is
        # exactly the fee-thrash the operator reported on 2026-04-27
        # (ETH bot folded $49.48 @ $2295.13, then 62 seconds later
        # cartridge-scrumed $47.40 @ $2295.89 — net loss after fees).
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
        _dust_band_usd = max(
            float(self._target_balance) * 0.001,   # 0.1% of target
            0.01,                                   # or $0.01 floor
        )
        if (not self._manual_fire_pending
                and abs(current_value - self._target_balance) <= _dust_band_usd):
            # Throttle the log — at-target is the steady state and we don't
            # want to spam. 1 emit per ~60 ticks.
            self._at_target_counter = getattr(
                self, "_at_target_counter", 0) + 1
            if self._at_target_counter % 60 == 1:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(
                        f"AT TARGET (MEM-258): position=${current_value:.2f} "
                        f"within dust band (±${_dust_band_usd:.4f}) of "
                        f"target=${self._target_balance:.2f}. Tick exits "
                        f"early. No TA, no signals, no buys or sells "
                        f"evaluated until price moves position off target."))
            try:
                from src.core.signal_contract import emit as _dz
                _dz("tick.08.003.event.exit_dust_band", actual=True,
                    context={"bot_id": self.bot_id,
                             "position": round(float(current_value), 6),
                             "target": round(float(self._target_balance), 6),
                             "band": round(float(_dust_band_usd), 6)})
            except Exception as _sup:  # noqa: BLE001,S110 - advisory
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
            return
        # Out of dust band — clear the counter so the next at-target emit
        # logs immediately when the bot parks again.
        self._at_target_counter = 0
        # ================================================================

        # MEM-241 — Manual Fire aggressive rebalance (operator override).
        # Checked BEFORE any TA/BB/fold gate logic so the operator's
        # directive bypasses everything and executes a market-order
        # rebalance-to-target in one shot. See _execute_manual_rebalance
        # docstring for semantic.
        #
        # MEM-242 — diagnostic log at entry: operator reported "no
        # kaboom" after pressing Fire. The entry log proves the tick
        # reached this check point; absence of this log means tick
        # isn't running, is returning earlier, or the flag was cleared
        # before tick could see it.
        if self._manual_fire_pending:
            # MEM-248 USD-first. Keyword tail preserved for MEM-242 diagnostic
            # test (asserts `holdings=`, `price=`, `target=` in block).
            # v3.15.55 — quote→USD-aware.
            _mf_usd = self._current_holdings * ticker.last * float(self._quote_to_usd or 1.0)
            _mf_delta = _mf_usd - self._target_balance
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"MANUAL FIRE: tick reached rebalance entry. "
                         f"position=${_mf_usd:.2f} vs target=${self._target_balance:.2f} "
                         f"(delta=${_mf_delta:+.2f}). Executing rebalance... "
                         f"(forensic: holdings={self._current_holdings:.6f} "
                         f"price=${ticker.last:.8f} target=${self._target_balance:.2f})"))
            try:
                # v3.23.2 — caller_intent attribution. This is the
                # operator-clicked Manual Fire path.
                await self._execute_manual_rebalance(
                    ticker, caller_intent="manual_button")
            except Exception as exc:  # sadp: R28 CBF — surface fully
                self._manual_fire_pending = False
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"MANUAL FIRE: exception during rebalance: {exc}")
                logger.exception("Manual fire rebalance failed")
            # Return early — this tick was dedicated to the manual
            # override. Normal tick logic resumes next cycle.
            return

        # =================================================================
        # v3.15.69 — WIRE-INCOME STACKING BUY (operator directive 2026-04-26)
        # =================================================================
        # When apply_wire_income detected at-center + at-entry conditions,
        # it bumped target_balance + anchor and queued the income amount
        # in _pending_stack_buy_usd. Here we consume that flag by firing
        # an aggressive rebalance — the bot's new (bumped) target now
        # exceeds current_value by the queued amount, so manual rebalance
        # buys exactly that much.
        # =================================================================
        try:
            _stack_pending = float(
                getattr(self, "_pending_stack_buy_usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            _stack_pending = 0.0
        if _stack_pending > 0:
            self._bus.emit(
                "bot.log", bot_id=self.bot_id,
                message=(
                    f"WIRE STACK FIRE: acquiring ${_stack_pending:.2f} of "
                    f"{self.config.target_asset} via aggressive rebalance "
                    f"to new target ${self._target_balance:.2f}."))
            try:
                self._emit_trade_notification(
                    "WIRE_STACK", "SENT",
                    f"${_stack_pending:.2f} acquisition")
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
            # Clear the flag BEFORE the buy so an exception mid-execute
            # doesn't leave us in a replay loop.
            self._pending_stack_buy_usd = 0.0
            # v3.18.15 (P1 Manual Fire audit, MEM-273) — apply MEM-257
            # FAIL-CLOSED state-vs-exchange verification before the
            # AUTO-initiated wire-stack buy. Same rationale as the
            # Max Cartridge call site below: auto-fire paths need the
            # fund-safety net, but the check is at the call site so
            # operator-initiated Manual Fire (which also funnels
            # through `_execute_manual_rebalance`) bypasses MEM-257
            # per Session 26 invariant.
            _verified_units, _refuse_msg = (
                await self._verify_buy_safe_or_refuse(
                    path="wire_stack"))
            if _refuse_msg:
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id, message=_refuse_msg)
                logger.warning("Bot %s %s", self.bot_id, _refuse_msg)
                return
            try:
                # v3.23.2 — caller_intent attribution. Wire Stack Fire
                # is AUTONOMOUS; emits with operator_initiated=False +
                # WIRE_STACK_* action labels so downstream consumers
                # (trade.log, parity tool) can distinguish it from
                # operator manual fires.
                await self._execute_manual_rebalance(
                    ticker, caller_intent="wire_stack")
            except Exception as exc:
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id,
                    message=(f"WIRE STACK FIRE: rebalance raised "
                             f"{type(exc).__name__}: {exc}"))
                logger.exception("Wire stack rebalance failed")
            # Tick consumed by stacking buy; resume on next cycle.
            return

        # =================================================================
        # v3.15.63 — MAXIMUM CARTRIDGE SIZE (operator directive 2026-04-26)
        # =================================================================
        # "Sets the maximum value the Target Delta can achieve before
        #  performing an immediate aggressive trade. This will be x% of
        #  the Target Balance. The default is 10%."
        #
        # When |position - target| ≥ target × max_cartridge_size_pct/100,
        # fire an aggressive rebalance via the same path as Manual Fire
        # (market order, bypasses BB Detection / hysteresis / soft CB /
        # higher-TF bias). This prevents the bot from sitting on a
        # too-large excursion before normal SCRUM/FOLD logic catches up.
        #
        # Hard CB and SELF-DESTRUCT both PAUSE the bot, so this code path
        # is naturally gated by run-loop state — no explicit check needed.
        # Set ``max_cartridge_size_pct = 0`` to disable.
        # =================================================================
        # ================================================================
        # v3.15.79 — CARTRIDGE GATE NOW RESPECTS HYSTERESIS.
        # ================================================================
        # Operator-reported fee-thrash incident 2026-04-27:
        #   16:35:59  Bot FOLDED 0.02138672 ETH @ $2295.13 = $49.48
        #   16:37:01  Cartridge fired SCRUM 0.02081043 ETH @ $2295.89
        #             = $47.40, only 0.03% above the FOLD price.
        #   Net: round-trip loss after fees. Operator: "I designed
        #        logic to make it not happen."
        #
        # Root cause: pre-v3.15.79 the cartridge gate explicitly
        # bypassed the v3.15.77 opposing-direction hysteresis (the
        # very gate the operator designed to prevent this exact
        # fee-thrash). The bypass was justified at v3.15.63 ship
        # time as "manual-fire path bypasses everything because
        # operator is sovereign" — but cartridge is NOT operator-
        # initiated, it's automatic, and the hysteresis bypass
        # produced money loss.
        #
        # FIX: cartridge now consults v3.15.77 hysteresis state
        # before firing. If the proposed direction would round-trip
        # below the interval+fee threshold from the pivot reference,
        # cartridge REFUSES to fire and lets normal SCRUM/FOLD
        # discipline (also hysteresis-respecting) retry as price
        # moves. Cartridge still bypasses BB Detection, soft CB,
        # and higher-TF bias — those are entry/regime gates, not
        # anti-thrash gates, and the operator's intent for cartridge
        # (aggressive force-rebalance on runaway delta) is preserved
        # for cases where the trade isn't a fee-thrash round-trip.
        #
        # Tick-order fix: hysteresis state is now updated EARLIER in
        # tick (right after current_value, line ~2790) so the
        # cartridge gate sees fresh state. Pre-v3.15.79 the update
        # ran at line ~3276, AFTER the cartridge gate, so cartridge
        # saw stale armed=False state immediately after a fill — the
        # exact tick where the operator's ETH bot misfired.
        # ================================================================
        try:
            _cartridge_pct = float(getattr(
                self.config, "max_cartridge_size_pct", 10.0) or 0.0)
        except (TypeError, ValueError):
            _cartridge_pct = 0.0

        # v3.15.92 SMART CARTRIDGE: when enabled, derive the cartridge
        # threshold from current BB range (already a rolling-period
        # measure of price-envelope width on the bot's TA TF).
        # Hard floor = scrumming_interval_pct (operator directive
        #   2026-04-28: cartridge MUST NEVER fire below the interval
        #   since sub-interval round-trips are structurally fee-thrash).
        # Soft ceiling = max_cartridge_smart_ceiling_pct (default 30%).
        # Falls back to static when no prior bb_result available.
        #
        # v3.15.94 hot-fix: was reading bare `bb_result`, but that
        # variable isn't assigned until LATER in tick() (~line 3736
        # at the BB-priority-skew computation). Python promoted
        # bb_result to a local-from-function-start because it's
        # assigned later, so the cartridge gate raised
        # UnboundLocalError on every tick. Fix: use
        # self._last_bb (the bb_result from the previous tick,
        # already cached on self). On the first tick before any
        # bb_result has been computed, _last_bb is None and smart
        # cartridge falls back to static — correct behavior.
        # Operator-reported 2026-04-28; same anti-pattern as the
        # v3.15.66 RAVE-bot UnboundLocalError on bullseye_upper.
        _smart_bb = getattr(self, "_last_bb", None)
        if (getattr(self.config, "max_cartridge_smart", False)
                and _smart_bb is not None
                and getattr(_smart_bb, "upper", 0) > 0
                and getattr(_smart_bb, "lower", 0) > 0):
            try:
                _bb_mid = (
                    getattr(_smart_bb, "bb_middle", 0)
                    or getattr(_smart_bb, "middle", 0)
                    or ((_smart_bb.upper + _smart_bb.lower) / 2.0))
                if _bb_mid > 0:
                    _bb_range_pct = (
                        (_smart_bb.upper - _smart_bb.lower) / _bb_mid * 100.0)
                    _interval_floor = float(
                        self.config.scrumming_interval_pct or 0)
                    _smart_ceiling = float(getattr(
                        self.config, "max_cartridge_smart_ceiling_pct",
                        30.0) or 30.0)
                    _smart_pct = max(
                        _interval_floor,
                        min(_smart_ceiling, _bb_range_pct))
                    # Operator-visible: log the smart-derived threshold
                    # once per significant change so the operator can
                    # see how the calibration is moving. Throttled to
                    # avoid spam (only log when it shifts > 1pp).
                    _last_smart = float(getattr(
                        self, "_cartridge_last_smart_pct", 0.0) or 0.0)
                    if abs(_smart_pct - _last_smart) >= 1.0:
                        try:
                            self._bus.emit(
                                "bot.log", bot_id=self.bot_id,
                                message=(
                                    f"SMART CARTRIDGE calibrated to "
                                    f"{_smart_pct:.2f}% "
                                    f"(BB range {_bb_range_pct:.2f}%, "
                                    f"floor={_interval_floor:.2f}%, "
                                    f"ceiling={_smart_ceiling:.2f}%). "
                                    f"Effective threshold = "
                                    f"${self._target_balance * _smart_pct / 100.0:.2f}."))
                        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
                        self._cartridge_last_smart_pct = _smart_pct
                    _cartridge_pct = _smart_pct
            except (TypeError, ValueError, ZeroDivisionError) as _sup:
                # Smart computation failed; fall back to static
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        if _cartridge_pct > 0 and self._target_balance > 0:
            _cartridge_threshold = self._target_balance * _cartridge_pct / 100.0
            _cartridge_delta = current_value - self._target_balance
            if abs(_cartridge_delta) >= _cartridge_threshold:
                _direction = "SCRUM" if _cartridge_delta > 0 else "FOLD"

                # ─────────────────────────────────────────────────
                # v3.15.79 hysteresis check — refuse fee-thrash
                # round-trips. Cartridge respects the same v3.15.77
                # gate that normal SCRUM/FOLD respect.
                # ─────────────────────────────────────────────────
                _hyst_blocks = False
                _hyst_reason = ""
                try:
                    _interval = float(
                        self.config.scrumming_interval_pct or 0)
                    _fee = float(getattr(
                        self.config, "trading_fee_pct", 0.6) or 0.6)
                    _eff_pct = _interval + _fee
                    _eff_frac = _eff_pct / 100.0
                except (TypeError, ValueError):
                    _eff_pct = 3.6
                    _eff_frac = 0.036

                if (_direction == "SCRUM"
                        and getattr(self, "_hyst_armed_scrum_side", False)
                        and float(getattr(
                            self, "_hyst_ref_scrum_side", 0.0) or 0.0)
                        > 0):
                    _required_min = (
                        self._hyst_ref_scrum_side * (1.0 + _eff_frac))
                    if ticker.last < _required_min:
                        _hyst_blocks = True
                        _hyst_reason = (
                            f"price ${ticker.last:.8f} below "
                            f"${_required_min:.8f} "
                            f"(pivot ${self._hyst_ref_scrum_side:.8f} "
                            f"+ {_eff_pct:.2f}%)")
                elif (_direction == "FOLD"
                        and getattr(self, "_hyst_armed_fold_side", False)
                        and float(getattr(
                            self, "_hyst_ref_fold_side", 0.0) or 0.0)
                        > 0):
                    _required_max = (
                        self._hyst_ref_fold_side * (1.0 - _eff_frac))
                    if ticker.last > _required_max:
                        _hyst_blocks = True
                        _hyst_reason = (
                            f"price ${ticker.last:.8f} above "
                            f"${_required_max:.8f} "
                            f"(pivot ${self._hyst_ref_fold_side:.8f} "
                            f"− {_eff_pct:.2f}%)")

                if _hyst_blocks:
                    # Throttled refusal log so a delta sitting above
                    # threshold during a hysteresis-locked period
                    # doesn't spam the console.
                    import time as _t_block
                    _now_b = _t_block.time()
                    _last_b = float(getattr(
                        self, "_cartridge_blocked_last_log_ts", 0.0) or 0.0)
                    if _now_b - _last_b >= 30.0:
                        self._cartridge_blocked_last_log_ts = _now_b
                        self._bus.emit(
                            "bot.log", bot_id=self.bot_id,
                            message=(
                                f"MAX CARTRIDGE BLOCKED (hysteresis "
                                f"v3.15.79): would fire {_direction} on "
                                f"|delta|=${abs(_cartridge_delta):.2f} "
                                f"≥ ${_cartridge_threshold:.2f}, but "
                                f"{_hyst_reason}. Refusing to prevent "
                                f"fee-thrash round-trip with recent "
                                f"opposite trade. Will re-evaluate "
                                f"each tick as price moves."))
                    # Do NOT return — let normal SCRUM/FOLD continue
                    # (they also respect hysteresis and will refuse
                    # correctly on this tick, but rejecting here lets
                    # the rest of the tick run cleanly).
                else:
                    # Hysteresis clear — fire the cartridge as
                    # designed. The aggressive rebalance via the
                    # manual-fire path bypasses BB Detection / soft
                    # CB / higher-TF bias (those are entry/regime
                    # gates, not anti-thrash gates) but DOES respect
                    # hysteresis (we just verified above).
                    self._bus.emit(
                        "bot.log", bot_id=self.bot_id,
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
                            f"opposing-direction hysteresis."))
                    # v3.18.15 (P1 Manual Fire audit, MEM-273) — apply
                    # MEM-257 FAIL-CLOSED state-vs-exchange verification
                    # before the AUTO-initiated cartridge buy on the FOLD
                    # side (BONK phantom-buy defense). The check is at
                    # the auto-fire CALL SITE rather than inside the
                    # shared `_execute_manual_rebalance` so that
                    # operator-initiated Manual Fire bypasses MEM-257
                    # per the Session 26 invariant. Max Cartridge is
                    # automatic and needs the fund-safety net.
                    if _direction == "FOLD":
                        _verified_units, _refuse_msg = (
                            await self._verify_buy_safe_or_refuse(
                                path="cartridge_fold"))
                        if _refuse_msg:
                            self._bus.emit(
                                "bot.log", bot_id=self.bot_id,
                                message=_refuse_msg)
                            logger.warning(
                                "Bot %s %s", self.bot_id, _refuse_msg)
                            return
                    try:
                        self._emit_trade_notification(
                            f"CARTRIDGE_{_direction}", "SENT",
                            f"|delta|=${abs(_cartridge_delta):.2f} ≥ "
                            f"${_cartridge_threshold:.2f}")
                    except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                        logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
                    try:
                        # v3.23.2 — caller_intent attribution. Max
                        # Cartridge Fire is AUTONOMOUS; emits with
                        # operator_initiated=False + CARTRIDGE_* labels
                        # so downstream consumers can distinguish it
                        # from operator manual fires.
                        await self._execute_manual_rebalance(
                            ticker, caller_intent="max_cartridge")
                    except Exception as exc:
                        self._bus.emit(
                            "bot.log", bot_id=self.bot_id,
                            message=(
                                f"MAX CARTRIDGE: rebalance raised "
                                f"{type(exc).__name__}: {exc}"))
                        logger.exception(
                            "Max cartridge rebalance failed")
                    # Return early — tick consumed by cartridge fire.
                    return

        # MEM-244 — Detonation check (automatic harvest on higher-TF
        # BULLISH confirmation). Rate-limited internally to 1 check
        # per hour and edge-triggered so sustained bull runs don't
        # re-detonate. Only runs when detonation_enabled is True.
        if getattr(self.config, "detonation_enabled", False):
            try:
                fired = await self._check_detonation_trigger(ticker)
                if fired:
                    await self._execute_detonation(ticker)
                    # Return early — detonation was this tick's work,
                    # downstream gate logic would see a just-mutated
                    # state (target reset, fold queue cleared).
                    return
            except Exception as exc:  # sadp: R28 — surface, don't hide
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"DETONATION: check/execute raised: "
                             f"{exc}. Continuing tick."))
                logger.exception("Detonation raised")

        if current_value < self._target_balance * 0.01:  # < 1% of target = effectively zero
            # MEM-246 Phase B: pre-buy discipline. Operator directive:
            #   (1) Initial buy MUST NOT push position past the Target
            #       Balance set-point (hard-cap ceiling = anchor × (1 + cap/100)).
            #   (2) "Empty" decision must reflect USD/base-currency value,
            #       not unit count — an expensive coin held in small units
            #       still has real dollars on the line.
            #   (3) If exchange reports zero for an asset we have saved
            #       state for, DO NOT trust the exchange — likely the
            #       BONK-style phantom-zero (see PRIORITY 0 incident file).
            # These three guards sit BEFORE the existing USD-precondition
            # gate so an under-funded bot can still surface the right log.
            try:
                _fresh_bal = await self._get_balance(self.config.target_asset)
                _fresh_units = float(_fresh_bal.free or 0)
            except Exception as _fb_exc:
                _fresh_units = None  # unknown — don't block on fetch failure
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"INITIAL ENTRY: fresh balance fetch raised "
                             f"({type(_fb_exc).__name__}: {_fb_exc}). "
                             f"Falling back to internal state. If phantom-"
                             f"buy appears, check exchange UI directly."))

            if _fresh_units is not None:
                # v3.15.55 — quote→USD-aware so crypto-quoted pairs
                # evaluate "fresh USD value" in USD, not quote units.
                _qrate = float(self._quote_to_usd or 1.0)
                # v3.15.56 — multi-base attribution: when this bot
                # shares its target asset with a sibling, _fresh_units
                # is the SHARED POOL — most of which belongs to the
                # sibling. The Phase B guards must reason about THIS
                # bot's attributed units (sum of _main_lots), NOT the
                # shared pool, otherwise a freshly-created sibling
                # bot is permanently blocked from entering because
                # the pool already exceeds its target.
                # v3.23.43 — scrumming bots always reason about their
                # OWN attributed units (sum of _main_lots), never the
                # raw exchange pool. Operator directive: no multi-base
                # attribution logic in Scrumming.
                _attributed_units = sum(
                    float(lot.get("units", 0) or 0)
                    for lot in self._main_lots
                )
                _fresh_units_eff = _attributed_units
                _fresh_usd = _attributed_units * ticker.last * _qrate

                # Guard (a): saved-state vs attributed-units mismatch.
                # If persisted _current_holdings > 0 but attributed
                # units from _main_lots = 0, the persistence layer
                # disagrees with itself — refuse initial entry.
                if self._current_holdings > 0 and _fresh_units_eff == 0:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"INITIAL ENTRY BLOCKED (Phase-B guard a): "
                                 f"attributed units 0 but saved state "
                                 f"holds {self._current_holdings:.6f} "
                                 f"units "
                                 f"(~${self._current_holdings * ticker.last * _qrate:.2f}). "
                                 f"Refusing buy on top of existing position. "
                                 f"Clear saved state manually before restart."))
                    return

                # Guard (b): USD-value check — fresh exchange value already
                # meaningful, not "empty" in any real sense.
                _value_threshold = max(self._target_balance * 0.25,
                                       max(self._target_balance * 0.01, 1.0))
                # Threshold = max(25% of target, max(1% of target, $1)).
                # This catches the expensive-coin case: a holding worth 25%
                # of target is clearly not a clean-slate initial-entry scenario.
                if _fresh_usd >= _value_threshold:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"INITIAL ENTRY BLOCKED (Phase-B guard b): "
                                 f"fresh USD value ${_fresh_usd:.2f} "
                                 f"({_fresh_units_eff:.6f} {self.config.target_asset} "
                                 f"@ ${ticker.last:.8f}) ≥ threshold "
                                 f"${_value_threshold:.2f}. Not empty — let "
                                 f"the regular scrum/fold cycle handle this "
                                 f"position instead of initial entry."))
                    return

                # Guard (c): Smart Ceiling sanity check (v3.16.50).
                # The fictional `anchor × (1 + max_target_growth_pct/100)`
                # ceiling that previously lived here was retired across the
                # codebase in v3.16.50 — it conflated a per-cycle growth-rate
                # cap with a hard cumulative ceiling and silently strangled
                # the organic Tranche-Surplus growth path. Layer 1 of the
                # MEM-251 v2 buy guard (inside _execute_buy) now catches
                # the over-target initial-entry case via the Target-Delta
                # budget — no separate ceiling check is needed for the
                # default case.
                #
                # When Smart Ceiling is enabled, surface a clear refusal
                # at the caller site (saves a network round-trip on the
                # known-bad case). Otherwise fall through and let Layer 1
                # gate the buy size against Target-Delta.
                if getattr(self.config, "position_ceiling_enabled", False):
                    try:
                        _smart_mult = float(getattr(
                            self.config, "position_ceiling_multiple", 1.0))
                        _smart_mult = max(1.0, min(10.0, _smart_mult))
                        _smart_ceiling_usd = (
                            self._anchor_target_balance * _smart_mult)
                        _prospective = _fresh_usd + self._target_balance
                        if _prospective > _smart_ceiling_usd:
                            self._bus.emit("bot.log", bot_id=self.bot_id,
                                message=(f"INITIAL ENTRY BLOCKED "
                                         f"(Smart Ceiling): prospective "
                                         f"position ${_prospective:.2f} "
                                         f"(existing ${_fresh_usd:.2f} + "
                                         f"buy ${self._target_balance:.2f}) "
                                         f"would exceed Smart Ceiling "
                                         f"${_smart_ceiling_usd:.2f} "
                                         f"(anchor "
                                         f"${self._anchor_target_balance:.2f} "
                                         f"× {_smart_mult:.1f}x). "
                                         f"Refusing buy."))
                            return
                    except (TypeError, ValueError, AttributeError) as _sup:
                        # Probe failed; let Layer 1 in _execute_buy handle.
                        logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

            # Need initial acquisition — check USD precondition FIRST, then TA + BB gates.

            # Gate (0) — USD precondition. Before running any TA/BB check, verify the
            # bot has enough quote currency to actually execute an initial entry.
            # Without this, the bot spams BB/TA-centric BLOCKED messages every tick
            # with no acknowledgment of wallet state, and the operator cannot tell
            # whether the bot is gated on market conditions or insufficient funds.
            # Session 25 operator report: "$50 bots — warning keeps popping up because
            # it's not checking the USD value of the position or corresponding base
            # currency for the pair."
            try:
                _quote_bal = await self._get_balance(self.config.base_currency)
                _quote_free_raw = float(_quote_bal.free or 0)
            except Exception as _qb_exc:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"INITIAL ENTRY BLOCKED: quote-currency balance "
                             f"fetch raised ({_qb_exc}). Retrying next tick."))
                return

            # v3.18.18 (Extractor design §13a + multi-ScrummingBot USD-overlap):
            # subtract sibling bots' operator-allocated claims on this base
            # currency from the raw exchange free. Closes two related risks:
            # (1) sibling Extractor's chunk being mistaken for excess and
            # scrummed away; (2) two ScrummingBots on the same base each
            # seeing the whole pool as their own free balance. Falls back
            # to raw when no manager attached (single-bot / unit-test path).
            _sibling_claims = self._sum_sibling_base_currency_claims()
            _quote_free = _quote_free_raw - _sibling_claims
            if _quote_free < 0:
                # Over-allocation: the operator has configured more total
                # claims than the exchange holds. Refuse to fire — do NOT
                # try to "recover" from a sibling's allocation. Throttle
                # the warning so the steady-state over-allocated configuration
                # doesn't spam the log.
                self._underfunded_log_counter = getattr(
                    self, "_underfunded_log_counter", 0) + 1
                if self._underfunded_log_counter % 60 == 1:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
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
                            f"pause a sibling bot to release its claim."))
                return

            if _quote_free < self._target_balance:
                # Throttle this log — it's the common steady-state for under-funded
                # bots. Emit once per ~60 ticks to avoid spamming the console.
                self._underfunded_log_counter = getattr(
                    self, "_underfunded_log_counter", 0) + 1
                if self._underfunded_log_counter % 60 == 1:
                    # v3.18.18 — show claim-adjusted AND raw if there are
                    # sibling claims, so operator can tell whether the
                    # shortfall is real (raw < target) or due to sibling
                    # allocations (raw ≥ target but claim-adjusted < target).
                    _have_str = (
                        f"${_quote_free:.2f} after sibling claims "
                        f"${_sibling_claims:.2f} (raw ${_quote_free_raw:.2f})"
                        if _sibling_claims > 0
                        else f"${_quote_free:.2f}")
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"INITIAL ENTRY BLOCKED: insufficient "
                                 f"{self.config.base_currency} — have "
                                 f"{_have_str}, need "
                                 f"${self._target_balance:.2f}. "
                                 f"({self.config.target_asset} position: "
                                 f"{self._current_holdings:.6f} @ "
                                 f"${ticker.last:.8f} = "
                                 f"${current_value:.2f})"))
                return
            # Reset spam counter once funded
            self._underfunded_log_counter = 0

            # Need initial acquisition — compute TA + BB and check ALL gates.
            # v3.23.74: routed through _get_ohlcv → MarketDataPool
            # coalesce (was raw self.exchange.get_ohlcv burning CPM).
            candles = await self._get_ohlcv(
                symbol, self.config.ta_timeframe, limit=100)
            if candles and len(candles) >= 30:
                # v3.13.8 MEM-191 / Chunk 7 — use module-level imports.
                engine = VotingEngine()
                parsed = candles_from_raw(candles)
                summary = engine.compute_all(
                    parsed, self.config.ta_timeframe,
                    symbol=self.config.symbol)
                self._last_summary = summary

                # Shared wallet-state suffix for all BLOCKED messages — lets the
                # operator see both sides of the balance sheet at a glance.
                _wallet = (f" [{self.config.base_currency}: ${_quote_free:.2f} · "
                           f"{self.config.target_asset}: "
                           f"{self._current_holdings:.6f} = "
                           f"${current_value:.2f}]")

                # Gate (1): BB data must be computable
                _init_bb = detect_bb_proximity(
                    parsed,
                    tolerance_pct=self.config.bb_tolerance_pct,
                    consolidation_threshold=3.0,
                    min_pattern_candles=self.config.bb_landing_strip_candles,
                )
                if (_init_bb is None or _init_bb.upper <= 0
                        or _init_bb.lower <= 0
                        or _init_bb.upper <= _init_bb.lower):
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"INITIAL ENTRY BLOCKED: BB data not yet "
                                f"computable — need proper band formation "
                                f"before entry. Price=${ticker.last:.8f}"
                                f"{_wallet}")
                    return

                _init_price = ticker.last
                _init_bb_width = _init_bb.upper - _init_bb.lower
                _init_bb_pos = ((_init_price - _init_bb.lower)
                                / max(_init_bb_width, 1e-12))

                # Gate (2): bb_pos must be ≤ 0.30 (structural entry zone —
                # lower third of the band). Buying near the upper band is
                # the exact anti-pattern the operator caught.
                if _init_bb_pos > 0.30:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"INITIAL ENTRY BLOCKED: bb_pos="
                                f"{_init_bb_pos:.2f} > 0.30 — price too "
                                f"high in band for structural entry. "
                                f"Waiting for decline to lower third."
                                f"{_wallet}")
                    return

                # Gate (3): 70% rule — distance to opposing (upper) band
                # must have traversed ≥ detect_pct of the midline-to-upper
                # range, OR price must be within fire_pct of the LOWER
                # band (the FIRE condition).
                _detect_pct_frac = self.config.scrum_detect_pct / 100.0  # 0.75
                _fire_pct_frac = self.config.scrum_fire_pct / 100.0      # 0.005
                _bb_mid_init = (_init_bb.upper + _init_bb.lower) / 2.0
                # Distance from midline down to current price, normalized
                # by the lower half-width. 1.0 = at lower band, 0.0 = at
                # midline, >1.0 = below lower band.
                _lower_half = _bb_mid_init - _init_bb.lower
                _dist_down = ((_bb_mid_init - _init_price)
                              / max(_lower_half, 1e-12))
                _near_lower = (abs(_init_price - _init_bb.lower)
                               / max(_init_bb.lower, 1e-12)
                               <= _fire_pct_frac)

                if not (_near_lower
                        or (_bb_mid_init - _init_price)
                        >= _detect_pct_frac * max(_lower_half, 1e-12)):
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"INITIAL ENTRY BLOCKED: distance-down "
                                f"{_dist_down:.0%} < {_detect_pct_frac:.0%} "
                                f"and not within {_fire_pct_frac:.2%} of "
                                f"lower band. Price=${_init_price:.8f} "
                                f"(lower=${_init_bb.lower:.8f}, "
                                f"mid=${_bb_mid_init:.8f})"
                                f"{_wallet}")
                    return

                # Gate (4): TA consensus must be BEARISH
                if summary.consensus_direction.name != "BEARISH":
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"INITIAL ENTRY BLOCKED: TA="
                                f"{summary.consensus_direction.name} "
                                f"({summary.consensus_confidence:.0%}) — "
                                f"need BEARISH (accumulation-trading "
                                f"thesis: buy decline, not rally). "
                                f"BB OK (pos={_init_bb_pos:.2f}, "
                                f"dist={_dist_down:.0%})."
                                f"{_wallet}")
                    return

                # All four gates passed — execute initial entry
                buy_cost = self._target_balance
                price = _init_price
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"INITIAL ENTRY: all 4 gates pass — "
                            f"BB OK, bb_pos={_init_bb_pos:.2f}, "
                            f"dist_down={_dist_down:.0%}, "
                            f"TA=BEARISH ({summary.consensus_confidence:.0%}). "
                            f"Acquiring ${buy_cost:.2f} of "
                            f"{self.config.target_asset} @ ${price:.8f}")
                entry_fill = await self._execute_buy(
                    buy_cost, price, summary,
                    trace_context={
                        "path": "zero_balance_initial_entry",
                        "bb_pos": f"{_init_bb_pos:.3f}",
                        "dist_down": f"{_dist_down:.1%}",
                        "gate_current_value": f"${current_value:.6f}",
                        "gate_threshold": f"${self._target_balance * 0.01:.6f}",
                    })
                # MEM-207 — None means _execute_buy failed (exchange
                # rejected, guard blocked, or exception raised). Do NOT
                # append a lot; do NOT emit COMPLETE. The _execute_buy
                # path already logged BUY ABORTED / BUY FAILED; caller
                # just returns without mutating state.
                if entry_fill is None or entry_fill <= 0:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"INITIAL ENTRY ABORTED: buy failed at "
                                f"${price:.8f}; no main_lots entry added. "
                                f"Bot will retry on next tick if gates "
                                f"still pass."))
                    return
                # --- Success path ---
                bought_units = buy_cost / entry_fill
                self._main_lots.append({
                    "units": bought_units,
                    "initial_buy_price": entry_fill,
                })
                # MEM-248 USD-first.
                _entry_usd = self._current_holdings * entry_fill
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"INITIAL ENTRY COMPLETE: position=${_entry_usd:.2f} "
                             f"vs target=${self._target_balance:.2f}. "
                             f"(forensic: {self._current_holdings:.6f} "
                             f"{self.config.target_asset} filled @ ${entry_fill:.8f}, "
                             f"intended ${price:.8f})"))
                # v3.23.3 — typed trade.filled emit for INITIAL ENTRY so
                # this fire lands in trade.log with proper attribution.
                # Pre-v3.23.3 the only emit for this path was the typeless
                # one inside _execute_buy (L9505), which got removed in
                # the double-emit cleanup. Without this typed emit the
                # initial entry would be invisible in trade.log.
                self._bus.emit("trade.filled", bot_id=self.bot_id,
                    side="buy", type="ENTRY", price=entry_fill,
                    amount=bought_units, size=buy_cost, profit=0.0,
                    operator_initiated=False)
                # v3.23.11 — voting.log + gate.log snapshots at fire (D-NEW-A).
                self._emit_voting_panel_snapshot_at_fire(
                    side="BUY", trade_action="ENTRY")
                self._emit_gate_decision_at_fire(
                    side="BUY", trade_action="ENTRY")
            return

        # --- Current state ---
        self.stats.position_value = current_value

        # =================================================================
        # DELTA CALCULATION
        # =================================================================
        delta = current_value - self._target_balance
        delta_pct = abs(delta) / (self._target_balance + 1e-9) * 100
        # The same threshold expressed in USD. Decisions compare USD
        # against USD; `delta_pct` is retained for the log lines only.
        # Comparing a computed ratio against a configured percentage is
        # what TA Quant reports as TA004.
        _interval_usd = (self._target_balance
                         * self.config.scrumming_interval_pct / 100.0)

        # v3.15.79 — Hysteresis state was already updated EARLIER in
        # the tick (right after current_value at line ~2790) so the
        # cartridge gate could see fresh state. The call here used to
        # be the ONLY update site in v3.15.77; moving it earlier was
        # part of the v3.15.79 cartridge-thrash fix. This idempotent
        # second call is left as a no-op safety net — the state
        # machine emits arm/disarm logs only on transition, so
        # double-calling cannot duplicate events.
        # (No-op call retained for defense-in-depth; remove if the
        # earlier update site is verified always-reachable.)
        # self._update_opposing_hysteresis_state(delta, ticker.last)

        # =================================================================
        # TA VOTING ENGINE — always compute (feeds Indicator Panel)
        # =================================================================
        ta_tf = self.config.ta_timeframe or "1h"
        try:
            # v3.23.74: routed through _get_ohlcv → MarketDataPool
            # coalesce. Prior direct self.exchange.get_ohlcv on every
            # action tick was the primary CPM burn the operator saw
            # (35 bots × 2 hot sites × TRACK-mode 30s cycle ≈ 140
            # raw candle calls / min).
            raw_candles = await self._get_ohlcv(
                symbol, timeframe=ta_tf, limit=100,
            )
            candles = candles_from_raw(raw_candles)
        except Exception:  # R28-OK: candle fetch; empty list short-circuits TA below
            candles = []

        # v3.15.58 — Circuit Breaker check on the most recent candle.
        # Must run BEFORE TA / scrum / fold logic so a hard trip can
        # short-circuit the rest of the tick. Soft trip leaves _cb_soft_*
        # state for the SCRUM/FOLD gates to consume below.
        try:
            self._check_circuit_breakers(candles)
        except Exception as _cb_exc:
            logger.warning(
                "Bot %s circuit breaker check raised %s: %s",
                self.bot_id, type(_cb_exc).__name__, _cb_exc)
        # Hard breaker → skip the rest of the tick entirely. Bot is
        # already PAUSED via the state mutation in _check_circuit_breakers.
        if self._cb_hard_tripped:
            return

        # v3.16.8 — dashboard-contract closure (P0c follow-up).
        # `stats.unrealised_pnl` was exposed by get_status() but never
        # written, so the dashboard always showed $0.00 unrealized PnL
        # and risk_manager.py:336 always read 0 for risk decisions.
        # Compute it live from holdings × current price minus cost basis.
        #
        # v3.23.24 — cost basis now prefers the exchange-derived value
        # (stats.cost_basis_total_exchange, populated every 5min by
        # refresh_exchange_position_health) to align with the operator
        # directive 2026-05-10 that position health belongs to the
        # exchange. Falls back to the internal _main_lots sum when the
        # exchange value has not yet been refreshed (first ~5 min after
        # bot start, before the first position-health tick fires).
        try:
            _live_px = float(getattr(ticker, "last", 0.0) or 0.0)
            if _live_px > 0:
                _cbx = float(getattr(
                    self.stats, "cost_basis_total_exchange", 0.0) or 0.0)
                if _cbx > 0:
                    _cost_basis = _cbx
                else:
                    _cost_basis = sum(
                        float(l.get("units", 0) or 0) *
                        float(l.get("initial_buy_price", 0) or 0)
                        for l in (getattr(self, "_main_lots", []) or [])
                    )
                _market_value = float(
                    getattr(self, "_current_holdings", 0.0) or 0.0) * _live_px
                self.stats.unrealised_pnl = _market_value - _cost_basis
        except Exception as _sup:  # R28-OK: live PnL is best-effort; failure leaves prior value
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        summary = None
        bb_result = None
        if len(candles) >= 30:
            summary = self._voting_engine.compute_all(
                candles, ta_tf, symbol=self.config.symbol)
            self._last_summary = summary

            bb_result = detect_bb_proximity(
                candles,
                tolerance_pct=self.config.bb_tolerance_pct,
                consolidation_threshold=3.0,
                min_pattern_candles=self.config.bb_landing_strip_candles,
            )
            self._last_bb = bb_result

        # Below interval — log status but still check fold/dist queues below
        below_interval = abs(delta) < _interval_usd

        if below_interval and self._fold_queue_usd == 0 and self._dist_accumulator == 0:
            # Nothing pending — just log and return
            ta_dir = summary.consensus_direction.name if summary else "N/A"
            ta_conf = f"{summary.consensus_confidence:.0%}" if summary else "—"
            fold_status = ""
            dist_status = ""
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"READ: ${ticker.last:.8f} | "
                        f"Δ=${delta:+.4f} ({delta_pct:.1f}% < {self.config.scrumming_interval_pct}%) | "
                        f"TA={ta_dir} ({ta_conf}) | holding")
            self._last_price = ticker.last
            return

        # Log delta if above interval or queues active
        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=f"Delta: ${delta:+.4f} ({delta_pct:.1f}%) — "
                    f"holdings=${current_value:.4f} vs target=${self._target_balance:.2f}"
                    f"{' [BELOW INTERVAL — checking queues]' if below_interval else ''}")

        if not summary:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message="Insufficient candle data for TA (need 30+)")
            self._last_price = ticker.last
            return

        # =================================================================
        # BOLLINGER BAND PROXIMITY + LANDING STRIP
        # =================================================================
        bb_confidence_boost = 0.0
        bb_override_direction = None
        if bb_result and bb_result.landing_strip:
            bb_confidence_boost = 0.15 + bb_result.consolidation_strength * 0.20
            if bb_result.landing_strip_side == "upper":
                bb_override_direction = SignalDirection.BEARISH
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"LANDING STRIP (upper BB): {bb_result.landing_strip_candles} "
                            f"tight HA candles (avg body {bb_result.ha_body_avg}%), "
                            f"strength={bb_result.consolidation_strength:.2f}")
            elif bb_result.landing_strip_side == "lower":
                bb_override_direction = SignalDirection.BULLISH
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"LANDING STRIP (lower BB): {bb_result.landing_strip_candles} "
                            f"tight HA candles (avg body {bb_result.ha_body_avg}%), "
                            f"strength={bb_result.consolidation_strength:.2f}")

        # =================================================================
        # LANDING STRIP v2: TIGHTENING DETECTION (3-layer)
        # =================================================================
        tightening = None
        if len(candles) >= 25:
            try:
                tightening = detect_landing_strip_v2(
                    candles, min_consecutive=3,
                    shrink_threshold=0.90, bb_tolerance_pct=3.0)
                if tightening and tightening.detected:
                    bb_confidence_boost += tightening.confidence_boost
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"TIGHTENING ({tightening.side} BB): "
                                f"{tightening.length} candles, "
                                f"ratio={tightening.tightening_ratio:.0%}, "
                                f"boost=+{tightening.confidence_boost:.2f}")
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        # =================================================================
        # POSITION-AWARE MOMENTUM (v3.1.61)
        # =================================================================
        # v3.13.8 MEM-191 / Chunk 7 — hoist eff_confidence / eff_direction
        # initialization to before the position-boost block, which does
        # `eff_confidence += position_boost` at its end. Previously these
        # were assigned only inside the trade-decision block below, so
        # the position-boost addition operated on an unbound name and
        # raised UnboundLocalError on the first tick with summary != None.
        # Invisible in production because the zero-balance entry branch
        # always handled the early path, and afterward the harness's
        # entry-free path was the first case to hit this.
        if summary:
            eff_confidence = summary.consensus_confidence
            eff_direction = summary.consensus_direction
        else:
            eff_confidence = 0.0
            eff_direction = None

        bb_pos = bb_result.bb_position if bb_result else 0
        at_upper_bb = bb_pos > 0.75
        at_lower_bb = bb_pos < 0.25
        in_bb_middle = 0.35 <= bb_pos <= 0.65

        # v3.23.7 D2-b asymmetric cycle-reset (operator pin 2026-06-13).
        # Replaces the v3.15.49 symmetric opposing-band re-arm gate.
        #
        # Operator spec (2026-04-24, re-affirmed 2026-06-13): "Was
        # previously defined as once per cycle meaning that a touch or
        # close approach to the opposing BB and then back down again
        # before another surplus fold can occur." — the asymmetric
        # semantic the spec requires.
        #
        # Side semantics (`_target_grow_last_side`):
        #   "lower" — last growth fired during a fold-tranche fill (bot
        #     bought to refill below target). Opposite extreme is UPPER
        #     band (_at_upper_extreme). Reset only when bb_pos >= 0.75.
        #   "upper" — reserved for future scrum-side growth path.
        #     Opposite extreme is LOWER band (_at_lower_extreme).
        #     Reset only when bb_pos <= 0.25.
        #   None — no growth this cycle; first BB-extreme touch arms the
        #     side ("lower" if at_lower_extreme, "upper" if at_upper_
        #     extreme) but does NOT reset (no cycle to reset).
        if bb_result is not None:
            _cur = max(0.0, min(1.0, float(bb_pos)))
            _at_upper_extreme = _cur >= 0.75
            _at_lower_extreme = _cur <= 0.25
            _reset_fired = False
            if (self._target_grow_last_side == "lower"
                    and _at_upper_extreme):
                _reset_fired = True
            elif (self._target_grow_last_side == "upper"
                    and _at_lower_extreme):
                _reset_fired = True
            elif (self._target_grow_last_side is None
                    and (_at_upper_extreme or _at_lower_extreme)):
                # First extreme touch this cycle arms the side. No
                # reset fires (there's nothing to reset yet) but the
                # side is recorded so the OPPOSITE extreme later
                # triggers the asymmetric reset.
                self._target_grow_last_side = (
                    "lower" if _at_lower_extreme else "upper")
            if _reset_fired and self._fold_cycle_cap_consumed > 1e-9:
                _prev_consumed = self._fold_cycle_cap_consumed
                _prev_side = self._target_grow_last_side
                self._fold_cycle_cap_consumed = 0.0
                self._target_grow_last_side = None
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"FOLD CYCLE RESET (D2-b asymmetric): "
                             f"bb_pos {_cur:.2f} reached opposite "
                             f"extreme (last growth fired {_prev_side}-"
                             f"side). Growth Rate Cap consumed "
                             f"${_prev_consumed:.4f} this cycle — "
                             f"reset to $0.00. Next fold-surplus may "
                             f"grow target up to full cap budget."))
                logger.info(
                    "Bot %s fold cycle reset (D2-b asymmetric, last_side=%s)"
                    " at bb_pos=%.3f (prev consumed $%.4f)",
                    self.bot_id, _prev_side, _cur, _prev_consumed)
            elif _reset_fired:
                # Reset condition fired but cap was already zero — just
                # clear the side tracker so next fire arms fresh.
                self._target_grow_last_side = None

        position_boost = 0.0
        if summary:
            for sig in summary.signals:
                # Vortex at upper BB: strong bull confirms the stretch → boost scrum
                if sig.indicator == "vortex" and sig.direction == SignalDirection.BULLISH:
                    if at_upper_bb and sig.confidence > 0.5:
                        position_boost += 0.12
                    elif in_bb_middle:
                        position_boost -= 0.05
                # MACD expanding at upper BB = confirmed stretch
                if sig.indicator == "macd" and sig.direction == SignalDirection.BULLISH:
                    if at_upper_bb and sig.confidence > 0.3:
                        position_boost += 0.08
                    elif in_bb_middle:
                        position_boost -= 0.03
                # Ichimoku above cloud is always a scrum-positive signal
                if sig.indicator == "ichimoku" and sig.direction == SignalDirection.BULLISH:
                    position_boost += 0.05
                elif sig.indicator == "ichimoku" and sig.direction == SignalDirection.BEARISH:
                    position_boost -= 0.05
                # StochRSI overbought = great time to scrum
                if sig.indicator == "stochastic_rsi" and sig.confidence > 0.7:
                    if sig.direction == SignalDirection.BEARISH:  # overbought
                        position_boost += 0.10
                    elif sig.direction == SignalDirection.BULLISH:  # oversold
                        position_boost -= 0.08

        # Market Structure: higher-highs/higher-lows (position-aware)
        if len(candles) >= 60:
            sw = 20
            highs = [c.high for c in candles[-sw*3:]]
            lows = [c.low for c in candles[-sw*3:]]
            if len(highs) >= sw * 3:
                rh = max(highs[-sw:]); ph = max(highs[-sw*2:-sw])
                rl = min(lows[-sw:]); pl = min(lows[-sw*2:-sw])
                uptrend = rh > ph and rl > pl
                downtrend = rh < ph and rl < pl
                if uptrend:
                    if at_upper_bb:
                        position_boost += 0.05  # Confirmed stretch
                    elif in_bb_middle:
                        position_boost -= 0.08  # Trend running, wait
                elif downtrend:
                    position_boost += 0.05  # Bearish = good for scrum

        eff_confidence += position_boost

        # =================================================================
        # TREND-HOLD GATE (v3.1.48) with Chunk 4 Band Travel override
        # =================================================================
        trend_hold = False
        trend_strength = 0.5
        if len(candles) >= 20:
            recent = candles[-20:]
            bull_count = sum(1 for c in recent if c.close > c.open)
            trend_strength = bull_count / len(recent)
            if trend_strength > 0.65:
                trend_hold = True

        # v3.13.8 MEM-188 / Chunk 4 — Band Travel detection (trend_hold override)
        # Measures how far price has moved since last executed trade as a
        # fraction of BB width. When the move crosses the operator's
        # band_travel_pct threshold and delta>0, override trend_hold so
        # scrum can fire — catches secondary harvest opportunities during
        # strong trends that the delta/TA gates alone might miss.
        # Ported from RAIntSimBat.py:1250-1252, 1246.
        band_travel_triggered = False
        band_travel_frac = 0.0
        if (self.config.band_travel_pct > 0
                and self._last_trade_price > 0
                and bb_result is not None
                and bb_result.upper > 0 and bb_result.lower > 0):
            _bb_width = max(bb_result.upper - bb_result.lower, 1e-12)
            band_travel_frac = abs(ticker.last - self._last_trade_price) / _bb_width
            if (abs(ticker.last - self._last_trade_price)
                    >= self.config.band_travel_pct / 100.0 * _bb_width
                    and delta > 0):
                band_travel_triggered = True

        # Trend-override: delta far above interval OR band travel triggered.
        # Band travel is Chunk 4's new contribution — keeps trend_hold honest
        # by letting big moves bypass the 'riding the trend' suppression.
        trend_override = (abs(delta) >= _interval_usd * 2.0
                          or band_travel_triggered)
        if trend_hold and trend_override:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"TREND-HOLD OVERRIDE: trend {trend_strength:.0%} bullish "
                        f"but {'band travel ' + f'{band_travel_frac:.0%}' if band_travel_triggered else 'delta 2x interval'} "
                        f"— scrum allowed this tick")
            trend_hold = False
        elif trend_hold:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"TREND-HOLD: {trend_strength:.0%} of last 20 candles bullish "
                        f"— suppressing scrum")

        bb_near = ""
        if bb_result:
            if bb_result.near_upper: bb_near = " NEAR UPPER"
            elif bb_result.near_lower: bb_near = " NEAR LOWER"

        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=f"TA Vote: {summary.consensus_direction.name} "
                    f"(conf={summary.consensus_confidence:.2f}"
                    f"{'+ BB %.2f' % bb_confidence_boost if bb_confidence_boost > 0 else ''}, "
                    f"B:{summary.bullish_count}/N:{summary.neutral_count}/"
                    f"S:{summary.bearish_count})"
                    f" | BB pos={bb_pos:.2f}{bb_near}")

        self._bus.emit(
            "ta.voting",
            bot_id=self.bot_id, symbol=symbol,
            bullish=summary.bullish_count,
            bearish=summary.bearish_count,
            neutral=summary.neutral_count,
            net_score=summary.net_score,
            confidence=summary.consensus_confidence,
            direction=summary.consensus_direction.name,
            bb_position=bb_pos,
            landing_strip=bb_result.landing_strip if bb_result else False,
            signals=[{"indicator": s.indicator, "direction": s.direction.name,
                      "confidence": round(s.confidence, 3)} for s in summary.signals],
        )

        # ═══════════════════════════════════════════════════════════════
        # v3.13.8 MEM-189 / Chunk 5 — Phantom lock check (scrum-only)
        # ═══════════════════════════════════════════════════════════════
        #
        # Per canonical sim (RAIntSimBat.py:1263-1272), phantom locks
        # suppress scrum harvesting ONLY — folds, hedge buys, and DIST
        # must remain active. Downside protection is never gated by
        # phantom locks. Previous behavior (early-return on any lock)
        # was too aggressive: it would also block fold rebuys during a
        # 4h bearish lock, which is exactly the conditions where buying
        # the dip is most valuable.
        #
        # Implementation: cache the lock state on self, then gate only
        # the SCRUM block downstream. The 1h bullish lock is the
        # canonical suppression condition (4h detected overbought,
        # tells 1h not to harvest).
        #
        # ─── v3.15.97 lifecycle audit ────────────────────────────────────
        # The TimeframeCoordinator.create_lock() callers in
        # phantom_balance.py were REMOVED in v3.15.61 when phantoms became
        # read-only TA observers (see phantom_balance.py:263 NOTE). In
        # current production code NOTHING calls create_lock(). Therefore
        # `is_locked(...)` ALWAYS returns False and `self._phantom_locked`
        # is ALWAYS False. The SCRUM-blocked debug-log branch below is
        # structurally unreachable.
        #
        # The query is preserved (rather than deleted) because:
        #   (a) the lock surface is still exercised by tests/test_v1_1.py
        #       and the canonical sim still models phantom locks in its
        #       inner loop — keeping the live engine query symmetric with
        #       the sim makes future re-activation a one-line change;
        #   (b) if a future ship reintroduces lock creation (e.g. via a
        #       higher-TF supervisor bot), the gate is already in place.
        #
        # If you see `_phantom_locked` errors at runtime, you are running
        # a stale binary (pre-v3.15.94). Check src/__init__.py against
        # whatever version your interpreter actually loaded.
        self._phantom_locked = False
        self._phantom_lock_timeframe = ""
        for _lock_tf in ("4h", "1h"):
            if self._coordinator.is_locked(_lock_tf, SignalDirection.BULLISH):
                self._phantom_locked = True
                self._phantom_lock_timeframe = _lock_tf
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"PHANTOM LOCK ACTIVE ({_lock_tf} bullish): "
                            f"scrum suppressed for this tick. "
                            f"Folds/hedge/dist remain active per "
                            f"downside-protection invariant.")
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
        eff_confidence += bb_confidence_boost
        if bb_override_direction and eff_direction == SignalDirection.NEUTRAL:
            eff_direction = bb_override_direction

        # =================================================================
        # v3.15.64 — BB Priority confidence SKEW (operator directive
        # 2026-04-26: "BB proximity and / or contact should immediately
        # trigger or heavily favor a trade if Minimum Opposing Trade
        # Distance is also satisfied and a Target Delta is available."
        # Refinement: "Should skew TA confidence, not over ride as this
        # seems dangerous.")
        # =================================================================
        # When BB proximity/contact + opposing-trade hysteresis + target
        # delta all align, we BOOST eff_confidence so weakly-bullish or
        # NEUTRAL TA clears the 0.25 is_bullish/is_bearish threshold.
        # We do NOT flip the direction — if TA actively says BEARISH
        # while we'd like to SCRUM, the boost won't unlock SCRUM (the
        # `eff_direction in (BULLISH, NEUTRAL)` clause still fails).
        # That preserves the operator's safety: "skew, not override".
        try:
            _eff_hyst_pct = (
                float(self.config.scrumming_interval_pct) +
                float(getattr(self.config, "trading_fee_pct", 0.6) or 0.6)
            ) / 100.0
        except Exception:  # R28-OK: hysteresis-pct config probe; documented fallback
            _eff_hyst_pct = 0.036  # 3% + 0.6% fallback
        # v3.15.77 — conditional opposing-direction hysteresis.
        # `_hyst_ok_*_side` is True (i.e. clear to skew) when EITHER
        # the gate is currently disarmed (delta hasn't drifted into
        # opposing territory yet, or has reversed back) OR the gate
        # is armed but the price has moved by interval+fee from the
        # pivot captured at arming time. Pre-fix logic measured
        # against `_last_trade_price` and was always-on.
        _hyst_ok_scrum_side = True
        if (self._hyst_armed_scrum_side
                and self._hyst_ref_scrum_side > 0):
            _hyst_ok_scrum_side = ticker.last >= self._hyst_ref_scrum_side * (
                1.0 + _eff_hyst_pct)
        _hyst_ok_fold_side = True
        if (self._hyst_armed_fold_side
                and self._hyst_ref_fold_side > 0):
            _hyst_ok_fold_side = ticker.last <= self._hyst_ref_fold_side * (
                1.0 - _eff_hyst_pct)
        # BB proximity (at/past detect threshold) OR contact (Bullseye).
        # v3.15.66 hotfix: Bullseye flags are computed LATER in the tick
        # (around line 3450 in the MEM-187 block), so referencing them
        # here without a guard raises UnboundLocalError and locks the
        # bot mid-tick (operator-reported 2026-04-26 RAVE lockup). We
        # compute Bullseye inline here using the same arithmetic the
        # MEM-187 block uses — single source of truth, no order-of-
        # evaluation dependency. Safe-guarded by config flag and bb_result
        # availability checks.
        _bb_lower_dt_pre, _bb_upper_dt_pre = self._bb_detect_thresholds()
        _be_upper = False
        _be_upper_wick = False
        _be_lower = False
        _be_lower_wick = False
        if (getattr(self.config, "bb_bullseye_check", True)
                and bb_result is not None
                and getattr(bb_result, "upper", 0) > 0
                and getattr(bb_result, "lower", 0) > 0):
            _bp_inline = ticker.last
            _touch_tol_inline = 0.005
            _wick_tol_inline = 0.002
            try:
                _be_upper = (
                    abs(_bp_inline - bb_result.upper) / bb_result.upper
                    < _touch_tol_inline)
                _be_lower = (
                    abs(_bp_inline - bb_result.lower) / bb_result.lower
                    < _touch_tol_inline)
                if candles and not _be_upper:
                    _be_upper_wick = candles[-1].high >= bb_result.upper * (
                        1.0 - _wick_tol_inline)
                if candles and not _be_lower:
                    _be_lower_wick = candles[-1].low <= bb_result.lower * (
                        1.0 + _wick_tol_inline)
            except (TypeError, ValueError, ZeroDivisionError) as _sup:
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
        _bb_proximity_upper = (
            (bb_pos >= _bb_upper_dt_pre)
            or _be_upper or _be_upper_wick
        )
        _bb_proximity_lower = (
            (bb_pos <= _bb_lower_dt_pre)
            or _be_lower or _be_lower_wick
        )
        _delta_available = (abs(delta) >= _interval_usd)
        # SCRUM-side priority skew: bullish-direction trade
        _bb_priority_scrum_skew = (
            _bb_proximity_upper and _hyst_ok_scrum_side
            and _delta_available and delta > 0
        )
        # FOLD-side priority skew: bearish-direction trade
        _bb_priority_fold_skew = (
            _bb_proximity_lower and _hyst_ok_fold_side
            and _delta_available and delta < 0
        )
        # Confidence skew amount: enough to lift NEUTRAL low-conf
        # (0.0–0.24) over the 0.25 threshold without inflating
        # already-high confidence into something deceptive.
        _BB_PRIORITY_SKEW = 0.30
        if _bb_priority_scrum_skew or _bb_priority_fold_skew:
            _pre_skew = eff_confidence
            eff_confidence = max(
                0.0, min(1.0, eff_confidence + _BB_PRIORITY_SKEW))
            try:
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id,
                    message=(
                        f"BB PRIORITY SKEW "
                        f"({'SCRUM' if _bb_priority_scrum_skew else 'FOLD'} "
                        f"side): bb_pos={bb_pos:.3f}, hysteresis OK, "
                        f"|Δ|=${abs(delta):.2f}≥interval. eff_confidence "
                        f"{_pre_skew:.2f} → {eff_confidence:.2f} (+0.30). "
                        f"TA direction NOT flipped — actively-contradicting "
                        f"TA still gates trade."))
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        # v3.24.43 — same values, named. See _TA_CONFIDENCE_FLOOR for why
        # the second conjunct matters: an operator who switches on
        # fold_require_ta_bearish is also opting into a confidence floor
        # that has no config key and never appeared in any log line.
        is_bullish = (eff_direction in (SignalDirection.BULLISH, SignalDirection.NEUTRAL)
                      and eff_confidence >= _TA_CONFIDENCE_FLOOR)
        is_bearish = (eff_direction in (SignalDirection.BEARISH, SignalDirection.NEUTRAL)
                      and eff_confidence >= _TA_CONFIDENCE_FLOOR)

        # BB Landing Strip overrides
        if bb_result and bb_result.landing_strip and bb_result.landing_strip_side == "upper":
            is_bullish = True
        if bb_result and bb_result.landing_strip and bb_result.landing_strip_side == "lower":
            is_bearish = True

        # ═══════════════════════════════════════════════════════════════
        # v3.13.8 MEM-186 / Chunk 2 — BB Midline Gate + Detect/Fire state machine
        # ═══════════════════════════════════════════════════════════════
        #
        # Three gates land here (ported from sim + simulator.py):
        #   (1) bb_midline_gate: scrums fire ONLY above midline,
        #       folds fire ONLY below midline (canonical sim line 1258-1259)
        #   (2) Detect Threshold: price must cross detect_pct of the way from
        #       midline toward the band before entering TRACK mode
        #   (3) Fire Threshold: once in TRACK, price within fire_pct of the
        #       band itself transitions to FIRE — only state that permits
        #       scrum execution
        #
        # Scrum requires ALL THREE to pass. Fold requires bb_midline_gate
        # (below midline) AND the existing MEM-171 tranche gates. Detect/
        # Fire state machine is SCRUM-SIDE ONLY (folds use the tranche
        # eligibility logic from Chunk 1).

        # (1) BB Midline Gate — applies to both scrum and fold.
        # Chunk 5 — scrum_ok also conjuncted with (not _phantom_locked)
        # per canonical sim line 1258: the phantom lock is applied at
        # the scrum gate, NOT the fold gate. Downside protection
        # (fold, hedge, dist) is never suppressed by phantom locks.
        if self.config.bb_midline_gate:
            scrum_ok = (bb_pos > 0.50) and not self._phantom_locked
            fold_ok_midline = bb_pos < 0.50
        else:
            scrum_ok = not self._phantom_locked
            fold_ok_midline = True

        # ── MEM-196 v3 RIPE-HARVEST / DEEP-FOLD OVERRIDE ───────────
        # Operator directive (Session 23):
        #   "If they have profit, claim it. If they are far below the delta,
        #    fold. I do not miss positive balances near the top BB."
        #
        # DIAGNOSIS (MEM-202): v1/v2/v3 only overrode scrum_ok (midline gate)
        # but the BONK bug showed the blocker was is_bullish (TA consensus
        # < 0.25 confidence) and target_fires (detect/fire state machine).
        # The ripe-harvest override now overrides ALL gates that sit between
        # the ripe condition and the SCRUM execution.
        #
        # v3.15.75 (operator directive 2026-04-27):
        #   "A substantial Target Delta with a BB touch SHOULD have fired
        #    a Scrum here. It had $21 USD in profit to claim. Fix it."
        #
        # PRIOR BUG: ripe thresholds were hard-coded delta_pct ≥ 10% AND
        # bb_pos ≥ 0.80. Operator's RAVE bot at $450 target with a $21
        # surplus = 4.7% delta — BELOW 10% threshold, so override never
        # engaged. SCRUM was then blocked by is_bullish (TA BEARISH at
        # the top of the band per accumulation-trading aggregation),
        # even though bb_pos was clearly past the operator-set BB Detect
        # Threshold. The operator's BB Detect Threshold setting carried
        # less weight than they thought — the hard-coded 10% / 80% pair
        # silently dominated.
        #
        # FIX: tie the ripe condition to the operator's already-set
        # tunables — scrumming_interval_pct (delta floor) and the BB
        # Detect Thresholds derived from scrum_detect_pct. When BB is
        # past the operator's chosen Detect Threshold AND delta exceeds
        # the operator's chosen interval, fire (overriding TA direction).
        # The operator's settings now mean what the operator thinks they
        # mean. Stricter behavior → raise scrum_detect_pct or
        # scrumming_interval_pct.
        #
        # MEM-171 price-floor preserved on fold side (per-tranche buy-price
        # gate applies downstream; only the midline gate is cleared here).
        #
        # PARITY: RAIntSimBat.py still uses the 10%/80% form. R42 PRP
        # cascade pending — operator's funds can't wait for sim parity
        # (mirrors the v3.15.49 / MEM-246 Phase B pattern).
        # sadp: R42 R44 R68
        _ripe_scrum = False
        _deep_fold = False
        # Hoisted from line ~3842 so the ripe block can reference the
        # operator-set Detect Thresholds. Computing once here avoids the
        # double-call.
        _bb_lower_dt, _bb_upper_dt = self._bb_detect_thresholds()
        if (bb_result is not None and bb_result.upper > 0
                and bb_result.lower > 0 and ticker.last > 0):
            if (delta > 0 and not below_interval
                    and bb_pos >= _bb_upper_dt):
                _ripe_scrum = True
            if (delta < 0 and not below_interval
                    and bb_pos <= _bb_lower_dt):
                _deep_fold = True

        # v3.18.13 (TA-gate cleanup Step 5) — MEM-196 override is now
        # LIFTED INTO THE CHAIN. `RipeHarvestScrumOverride` declares
        # `overrides = ("midline_scrum", "target_fires", "trend_hold",
        # "ta_bullish")` upfront; `DeepFoldOverride` declares
        # `overrides = ("midline_fold", "ta_bearish")`. When the chain
        # sees `ctx.ripe_scrum=True` / `ctx.deep_fold=True`, its
        # two-pass evaluator force-passes those gates and records them
        # in `result.overrides_applied` for diagnostics.
        #
        # PRIOR DESIGN (retired v3.18.13): inline rewrites mutated the
        # local variables (`scrum_ok = True`, `is_bullish = True`,
        # `target_fires = True`, `trend_hold = False`, etc.) so the
        # downstream 10-clause trigger conjunction would pass. That
        # design predates the GateChain framework (added v3.18.11,
        # made load-bearing v3.18.12) and was always "redundant-but-
        # harmless" once the chain had its own override gates. This
        # block now emits the operator-readable narrative ONLY — no
        # local mutations. The chain is the single source of truth.
        if _ripe_scrum and not scrum_ok:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(
                    f"MEM-196 RIPE-HARVEST (v3.15.75, override via "
                    f"GateChain v3.18.13): Δ={delta_pct:.1f}% ≥ "
                    f"interval {self.config.scrumming_interval_pct:.1f}% "
                    f"+ bb_pos={bb_pos:.2f} ≥ Upper Detect Threshold "
                    f"{_bb_upper_dt:.3f}. RipeHarvestScrumOverride "
                    f"will force-pass midline_scrum + target_fires + "
                    f"trend_hold + ta_bullish. Operator directive: "
                    f"claim the profit."))
        if _deep_fold and not fold_ok_midline:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(
                    f"MEM-196 DEEP-FOLD (v3.15.75, override via "
                    f"GateChain v3.18.13): Δ={delta_pct:.1f}% ≥ "
                    f"interval {self.config.scrumming_interval_pct:.1f}% "
                    f"+ bb_pos={bb_pos:.2f} ≤ Lower Detect Threshold "
                    f"{_bb_lower_dt:.3f}. DeepFoldOverride will "
                    f"force-pass midline_fold + ta_bearish. MEM-171 "
                    f"per-tranche price-floor still enforced downstream."))
        # ────────────────────────────────────────────────────────────

        # (2) + (3) Detect/Fire state machine — scrum-side only
        # Compute side + dist_to_band + near_band from the BB band prices
        # (derived from bb_result if available; fall back to ticker alone
        # which degrades to a permissive state machine — FIRE mode from start)
        detect_pct_frac = self.config.scrum_detect_pct / 100.0  # 75 → 0.75
        fire_pct_frac = self.config.scrum_fire_pct / 100.0      # 0.5 → 0.005

        target_fires = True  # fallback: if no BB data, don't gate scrum
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

            # Side change resets to search
            if _prev_side is not None and _prev_side != _side:
                _mode = "search"

            # State transitions — lifted directly from simulator.py:5502-5552
            if _mode == "search":
                if _near_band and abs(delta) >= _interval_usd * 0.5:
                    # Fast move to band — skip TRACK, go straight to FIRE
                    _mode = "fire"
                    self._scrum_target_side = _side
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"TARGET: SEARCH→FIRE ({_side}) — fast move to band, "
                                f"Δ {delta_pct:.1f}% ≥ {self.config.scrumming_interval_pct * 0.5:.1f}%")
                elif (_dist_abs >= detect_pct_frac * _band_span
                      and abs(delta) >= _interval_usd * 0.5):
                    _mode = "track"
                    self._scrum_target_side = _side
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"TARGET: SEARCH→TRACK ({_side}) — "
                                f"BB dist {_dist_to_band:.0%} ≥ {detect_pct_frac:.0%}")
            elif _mode == "track":
                if _near_band:
                    _mode = "fire"
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"TARGET: TRACK→FIRE ({_side}) — "
                                f"within {fire_pct_frac:.2%} of BB band")
                elif _dist_abs < detect_pct_frac * 0.5 * _band_span:
                    _mode = "search"
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"TARGET: TRACK→SEARCH — retreated "
                                f"(dist {_dist_to_band:.0%} < {detect_pct_frac * 0.5:.0%})")
            elif _mode == "fire":
                # Lifecycle completion per sadp:R44 — FIRE needs exit paths
                if not _near_band and _dist_abs >= detect_pct_frac * _band_span:
                    _mode = "track"
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"TARGET: FIRE→TRACK ({_side}) — off band, "
                                f"still in detect zone (dist {_dist_to_band:.0%})")
                elif _dist_abs < detect_pct_frac * 0.5 * _band_span:
                    _mode = "search"
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"TARGET: FIRE→SEARCH — retreated "
                                f"(dist {_dist_to_band:.0%} < {detect_pct_frac * 0.5:.0%})")

            self._scrum_target_mode = _mode
            target_fires = (_mode == "fire")

        # ═══════════════════════════════════════════════════════════════
        # v3.13.8 MEM-187 / Chunk 3 — BB Bullseye Check
        # ═══════════════════════════════════════════════════════════════
        #
        # Rapid-fire override: when price touches (or wicks) an exact BB
        # band within tolerance, scrum/fold should fire regardless of
        # SEARCH/TRACK/FIRE state. Matches RAIntSimBat.py:1283-1293
        # bullseye detection + lines 1678, 1728 override paths.
        #
        # touch_tolerance: 0.5% (close within 0.5% of band — "close touch")
        # wick_tolerance:  0.2% (candle HIGH/LOW reached band — "wick touch")
        #
        # bullseye_upper/lower paths: price actively AT the band
        # bullseye_upper_wick/lower_wick: candle touched band but close retreated
        bullseye_upper = False
        bullseye_upper_wick = False
        bullseye_lower = False
        bullseye_lower_wick = False
        if (self.config.bb_bullseye_check and bb_result is not None
                and bb_result.upper > 0 and bb_result.lower > 0):
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

        # MEM-243 — Bullseye detection is NOW INFORMATIONAL ONLY.
        # Previously (pre-MEM-243), bullseye_upper overrode target_fires
        # to True, bypassing the SEARCH→TRACK→FIRE state machine ramp
        # whenever price was within 0.5% of the upper band.
        #
        # Operator directive (Session 24, MEM-243):
        #   "Why next tick? You got the signal. Do it."
        #   Choice: "Also remove the BB-bullseye override entirely —
        #            respect the ramp"
        #
        # Rationale: the prior override was self-contradictory — claimed
        # to bypass the ramp but still deferred to the other 5 gates,
        # and the log phrasing ("bypassing... if gates pass") read as
        # hedging. Operator chose honesty over optimization: respect
        # the ramp unconditionally. If price is at the band but ramp
        # hasn't transitioned to FIRE yet, the scrum waits. The ramp
        # will catch up on the next tick (its transitions are fast
        # enough that the 1-tick delay is negligible at a 5s cadence).
        #
        # Bullseye detection is still useful as a SIGNAL for phantoms,
        # operator diagnostics, and future bookkeeping, so we keep the
        # detection and the log — but the log no longer makes any
        # claim about "will fire" because the ramp state machine
        # retains sole authority over target_fires.
        if bullseye_upper or bullseye_upper_wick:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"BULLSEYE UPPER ({'wick' if bullseye_upper_wick else 'close'}): "
                        f"price ${ticker.last:.8f} at BB upper ${bb_result.upper:.8f}. "
                        f"FIRE ramp in {self._scrum_target_mode.upper()}; "
                        f"scrum fires only when ramp reaches FIRE.")
        if bullseye_lower or bullseye_lower_wick:
            # Symmetric honesty on the fold side — fold has its own
            # gate chain (MEM-171 tranche gates + BEARISH + midline),
            # the state machine doesn't force a fold and never did.
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"BULLSEYE LOWER ({'wick' if bullseye_lower_wick else 'close'}): "
                        f"price ${ticker.last:.8f} at BB lower ${bb_result.lower:.8f}. "
                        f"Fold decision governed by MEM-171 tranche gates.")

        # === SCRUM HOLD DIAGNOSTIC (MEM-202) ───────────────────────
        # If delta > 0 but the scrum condition is False, identify exactly
        # which of the six gates blocked. Purely diagnostic; no behavior
        # change. Logs to bot.log so the Lite GUI Console pane shows it
        # on live runs — operator can see WHY the bot held when they
        # expected it to scrum.
        #
        # Six gates: delta > 0, not below_interval, is_bullish,
        # not trend_hold, scrum_ok (MEM-196), target_fires (detect/fire).
        # Throttled to once every 50 ticks per bot to avoid log spam
        # during normal HOLD periods.
        if delta > 0 and not (
                not below_interval and is_bullish and not trend_hold
                and scrum_ok and target_fires):
            self._hold_tick_counter += 1
            if self._hold_tick_counter % 50 == 0:
                _blocked = []
                if below_interval:
                    _blocked.append(f"below_interval(Δ={delta_pct:.1f}% < "
                                    f"{self.config.scrumming_interval_pct}%)")
                if not is_bullish:
                    _blocked.append(f"not_bullish(dir={eff_direction.name})")
                if trend_hold:
                    _blocked.append("trend_hold")
                if not scrum_ok:
                    # v3.15.94 hot-fix: was bare `_phantom_locked`,
                    # raised NameError when this debug-log path fired
                    # on operator's first tick. Operator reported
                    # 2026-04-28 with Uptime: 0s. Instance attribute
                    # is `self._phantom_locked` (set at __init__ line
                    # ~380); the bare name had no binding in local or
                    # global scope.
                    _blocked.append(f"scrum_ok_false(bb_pos={bb_pos:.2f},"
                                    f"phantom={self._phantom_locked})")
                if not target_fires:
                    _blocked.append(f"target_fires_false(detect/fire)")
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"HOLD w/ Δ=+{delta_pct:.1f}% "
                            f"(${current_value:.2f} vs target ${self._target_balance:.2f}): "
                            f"blocked by [{', '.join(_blocked) or 'unknown'}]. "
                            f"Tick #{self._hold_tick_counter}.")
        # ────────────────────────────────────────────────────────────

        # === MEM-196 v3 FULL OVERRIDE — operator-narrative emit only ──
        # v3.18.13 (TA-gate cleanup Step 5): the inline local-variable
        # rewrites (`is_bullish = True`, `target_fires = True`,
        # `trend_hold = False`, `is_bearish = True`) are RETIRED. The
        # chain's RipeHarvestScrumOverride / DeepFoldOverride gates do
        # the override semantically — see the chain construction in
        # gate_chain.py and the cutover sites below where
        # `ctx.ripe_scrum=bool(_ripe_scrum)` /
        # `ctx.deep_fold=bool(_deep_fold)` are now passed truthfully.
        #
        # Why this fixed the BONK bug (MEM-202): without the override,
        # the bot would route to the "HOLD SCRUM: waiting for BULLISH"
        # elif at line ~1060 when TA confidence was below 0.25 even
        # though the operator visibly wanted to harvest. The chain's
        # override gate now models that semantic explicitly: when
        # ripe-scrum conditions hold, the four blocking gates are
        # force-passed and the chain's should_fire is True.
        #
        # The emit blocks below preserve the operator narrative so the
        # Activity Log still surfaces "MEM-196 fired and would force
        # these gates open". Pure logging — no local mutations.
        if _ripe_scrum:
            if not is_bullish:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"MEM-196 RIPE-HARVEST OVERRIDE ta_bullish: "
                            f"raw is_bullish=False (dir={eff_direction.name}, "
                            f"conf={eff_confidence:.2f}) — "
                            f"RipeHarvestScrumOverride will force-pass.")
            if not target_fires:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"MEM-196 RIPE-HARVEST OVERRIDE target_fires: "
                            f"raw target_fires=False (detect/fire SM) — "
                            f"RipeHarvestScrumOverride will force-pass.")
            if trend_hold:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"MEM-196 RIPE-HARVEST OVERRIDE trend_hold: "
                            f"raw trend_hold=True ({trend_strength:.0%}) — "
                            f"RipeHarvestScrumOverride will force-pass.")
        if _deep_fold:
            if not is_bearish:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"MEM-196 DEEP-FOLD OVERRIDE ta_bearish: "
                            f"raw is_bearish=False (dir={eff_direction.name}, "
                            f"conf={eff_confidence:.2f}) — "
                            f"DeepFoldOverride will force-pass.")
        # ────────────────────────────────────────────────────────────

        # === SCRUM: sell 100% of excess on BULLISH (only when above interval) ===
        # v3.13.8 Chunk 2 — also gated by scrum_ok (bb_midline_gate) and
        # target_fires (detect/fire state machine). Missing any gate = HOLD.
        # v3.15.57 — operator directive 2026-04-25: "Scrums cannot occur
        # below the Upper BB Detection Threshold". Hard gate, no overrides.
        # v3.15.58 — Circuit Breaker: soft trip on SCRUM side suppresses
        # all auto-scrums until cooldown elapses; hard trip already
        # short-circuited tick entry above.
        # v3.15.61 — Higher-TF phantom bias gate (operator directive
        # 2026-04-26: "As long as the higher TF bot is considering
        # placing an order, the lower TF measurements are just used for
        # fine tuning the order timing"). When ANY higher-TF phantom
        # signals BULLISH with confidence ≥ 30%, this bot's SCRUM
        # (selling INTO an upward bias) is refused — the higher TF says
        # the trend is up; selling here is fighting the higher TF.
        # Lower TFs (relative to this parent) are not consulted at this
        # gate — they enter as the existing target_fires / scrum state
        # machine which already times the local entry.
        # v3.15.75 — _bb_lower_dt / _bb_upper_dt hoisted to the MEM-196
        # ripe-harvest block above; reuse here without re-computing.
        _bb_above_upper_dt = bb_pos >= _bb_upper_dt
        _bb_below_lower_dt = bb_pos <= _bb_lower_dt
        _cb_blocks_scrum = self._cb_soft_active_side == "scrum"
        # v3.15.61 — read higher-TF bias from the phantom coordinator.
        # If no phantoms are attached or no higher-TF summaries exist,
        # this returns (None, ...) and the gate defaults to "no override".
        _htf_bias_dir = None
        _htf_bias_detail: dict = {}
        try:
            if self._coordinator is not None:
                _htf_bias_dir, _htf_bias_detail = (
                    self._coordinator.get_higher_tf_bias(
                        self.bot_id,
                        self.config.ta_timeframe or "1h",
                    )
                )
        except Exception as _hbexc:
            logger.debug(
                "Bot %s higher-TF bias read raised %s: %s",
                self.bot_id, type(_hbexc).__name__, _hbexc)
        # SCRUM is blocked when higher-TF says BULLISH (don't sell into
        # confirmed upward trend). NEUTRAL or BEARISH or None all permit.
        _htf_blocks_scrum = (_htf_bias_dir == SignalDirection.BULLISH)
        # v3.16.15 — operator-toggleable gate flags. Default True (current
        # "Conservative" behavior). Setting any to False relaxes that
        # specific gate per the 2026-04-30 design conversation.
        _flag_require_ta_bullish = bool(getattr(
            self.config, "scrum_require_ta_bullish", True))
        _flag_hold_in_uptrend = bool(getattr(
            self.config, "scrum_hold_in_uptrend", True))
        _flag_defer_to_htf = bool(getattr(
            self.config, "scrum_defer_to_htf", True))
        # If a flag is False, force the corresponding gate to a permissive
        # state. is_bullish/trend_hold are recomputed per-tick; the
        # gate-effective values used in the conditional below are local-
        # scope copies so the diagnostic logs still report the underlying
        # signal's true value.
        _eff_is_bullish = is_bullish if _flag_require_ta_bullish else True
        _eff_trend_hold = trend_hold if _flag_hold_in_uptrend else False
        _eff_htf_blocks = _htf_blocks_scrum if _flag_defer_to_htf else False

        # v3.16.16 — capture which gates are blocking SCRUM auto-fire
        # so the GUI fire button can render solid (auto would fire) vs
        # outline (manual override available but auto blocked) and the
        # tooltip can list the specific blocker(s).
        #
        # v3.18.13 — Step 5 cleanup. Four checks (`ta_bullish`,
        # `trend_hold`, `midline_scrum`, `target_fires`) now ALSO honor
        # the MEM-196 ripe-harvest override predicate so this
        # accumulator stays in sync with the chain's
        # `RipeHarvestScrumOverride` (which declares those exact four
        # gates as its overrides). Without this gating, the dashboard
        # would show false blockers on ripe-harvest ticks while the
        # chain was firing the SCRUM — exactly the drift class of bug
        # the audit eliminated at the trigger layer. The accumulator
        # below is operator-readable narrative; the chain remains the
        # single source of truth for `should_fire`.
        _scrum_blockers: list[str] = []
        if delta <= 0:
            _scrum_blockers.append("delta≤0")
        if below_interval:
            _scrum_blockers.append(f"below_interval(Δ%<{self.config.scrumming_interval_pct})")
        if not _eff_is_bullish and not _ripe_scrum:
            # v3.24.43 — symmetric with the fold side; the floor gates
            # SCRUM the same way and the label hid it the same way.
            _scrum_blockers.append(
                f"TA-conf-below-floor(dir={eff_direction.name},"
                f"conf={eff_confidence:.2f}<{_TA_CONFIDENCE_FLOOR:.2f})"
                if eff_direction in (SignalDirection.BULLISH,
                                     SignalDirection.NEUTRAL)
                else f"TA-not-bullish(dir={eff_direction.name})")
        if _eff_trend_hold and not _ripe_scrum:
            _scrum_blockers.append(f"trend_hold({trend_strength:.0%})")
        if not scrum_ok and not _ripe_scrum:
            _scrum_blockers.append(f"scrum_ok=False(bb_pos={bb_pos:.2f})")
        if not target_fires and not _ripe_scrum:
            _scrum_blockers.append("target_fires=False(detect/fire)")
        if not _bb_above_upper_dt:
            _scrum_blockers.append(f"BB-below-upper-detect(bb_pos={bb_pos:.2f}<{_bb_upper_dt:.2f})")
        if _cb_blocks_scrum:
            _scrum_blockers.append("CB-soft-trip")
        if _eff_htf_blocks:
            _scrum_blockers.append("HTF-bullish")
        # v3.18.1 — OTD-hysteresis gate (Minimum Opposing Trade Distance).
        # Operator-discovered bug 2026-05-19: this gate was computed but
        # never enforced on the autonomous SCRUM branch. Now hard-blocks.
        if not _hyst_ok_scrum_side:
            try:
                _ref_px = float(self._hyst_ref_scrum_side or 0)
                _eff_pct = (
                    float(self.config.scrumming_interval_pct or 0)
                    + float(getattr(
                        self.config, "trading_fee_pct", 0.6) or 0.6))
                _required = _ref_px * (1.0 + _eff_pct / 100.0)
                _scrum_blockers.append(
                    f"OTD-hyst(px ${ticker.last:.8f} < "
                    f"${_required:.8f}; pivot ${_ref_px:.8f} "
                    f"+ {_eff_pct:.2f}%)")
            except Exception:  # R28-OK: diag formatting; non-fatal
                _scrum_blockers.append("OTD-hyst-armed")
        # Persist for dashboard read (mutating instead of replacing so
        # the FOLD path below can write to the same dict).
        try:
            self._last_gate_state["scrum_armed"] = (len(_scrum_blockers) == 0)
            self._last_gate_state["scrum_blockers"] = list(_scrum_blockers)
            self._last_gate_state["evaluated_at_tick"] = (
                self._last_gate_state.get("evaluated_at_tick", 0) + 1)
            # v3.18.9 (TA-gate cleanup Step 1) — capture the full SCRUM
            # gate-variable inventory for the baseline fixture. Audit
            # 2026-05-20: this captures EVERY boolean and numeric input
            # to the 10-clause SCRUM trigger conjunction at line
            # ~5475-5478, so the GateChain framework parity test can
            # later assert bit-identical evaluation. Pure additive —
            # dict writes have no behavior impact; tick logic unchanged.
            self._last_gate_state["scrum_fixture"] = {
                "delta": float(delta),
                "below_interval": bool(below_interval),
                "ticker_last": float(ticker.last),
                "bb_pos": float(bb_pos),
                # v3.24.18 — landing strip was a DECISION INPUT with
                # no audit trail. At line ~6212 a detected strip
                # forces is_bullish/is_bearish True, so a trade can
                # fire that the TA gate alone would have refused —
                # and nothing recorded that it happened. Operator
                # 2026-08-03 called out the omission directly.
                # Recorded here so the reconstructed and live gate
                # rows agree on why a direction flipped.
                "landing_strip": bool(
                    bb_result.landing_strip if bb_result else False),
                "landing_strip_side": str(
                    bb_result.landing_strip_side
                    if bb_result else "") or "",
                "landing_strip_candles": int(
                    bb_result.landing_strip_candles
                    if bb_result else 0),
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
                "htf_bias_dir": (str(_htf_bias_dir.name)
                                   if _htf_bias_dir is not None else None),
                "htf_blocks_scrum": bool(_htf_blocks_scrum),
                "flag_require_ta_bullish": bool(_flag_require_ta_bullish),
                "flag_hold_in_uptrend": bool(_flag_hold_in_uptrend),
                "flag_defer_to_htf": bool(_flag_defer_to_htf),
                "eff_is_bullish": bool(_eff_is_bullish),
                "eff_trend_hold": bool(_eff_trend_hold),
                "eff_htf_blocks": bool(_eff_htf_blocks),
                "hyst_ok_scrum_side": bool(_hyst_ok_scrum_side),
                "hyst_armed_scrum_side": bool(getattr(
                    self, "_hyst_armed_scrum_side", False)),
                "hyst_ref_scrum_side": float(getattr(
                    self, "_hyst_ref_scrum_side", 0.0) or 0.0),
            }
        except Exception as _sfx_exc:  # noqa: BLE001 - see below
            # v3.24.18 — was `except Exception: pass`, which meant one
            # bad field silently discarded ALL 25 gate-fixture values
            # and left scrum_fixture=None in the log. Measured in sim
            # 2026-08-03: every gate row carried a null fixture and
            # nothing said why. The write still must not block the
            # tick, so we swallow — but the cause is now recorded,
            # once per bot, instead of vanishing.
            if not getattr(self, "_scrum_fixture_warned", False):
                self._scrum_fixture_warned = True
                logger.warning(
                    "Bot %s scrum_fixture capture failed (%s: %s) — "
                    "gate rows will carry a null scrum_fixture until "
                    "this is fixed",
                    self.bot_id, type(_sfx_exc).__name__, _sfx_exc)

        # v3.18.1 — OPERATOR-DISCOVERED BUG 2026-05-19: OTD hysteresis
        # gate was computed (lines 4913-4922 — _hyst_ok_scrum_side /
        # _hyst_ok_fold_side) but ONLY consumed in the BB priority skew
        # confidence modifier and the Max Cartridge path. The regular
        # autonomous SCRUM/FOLD execution branches NEVER CHECKED the
        # gate. Result: bot executed opposing trades within fractions
        # of a percent of the prior fill, sometimes selling LOWER than
        # the just-bought price. YTD CSV showed 27 RAVE pairs at <1%
        # distance, 7 with NEGATIVE distance (loss-locking trades).
        #
        # Wire the gate as a HARD REFUSAL here. Operator's directive
        # 2026-04-25 verbatim: "If a scrum or fold occurs then the
        # opposite CANNOT occur without price deviating by the minimum
        # scrum interval ... No ifs ands or buts about it."
        #
        # v3.18.12 — TA-gate cleanup Step 4 cutover. The 10-clause AND
        # conjunction that used to live on the next line is now delegated
        # to self._scrum_chain.evaluate(ctx). The chain framework
        # produces the SAME boolean result by construction — proven via
        # tests/test_gate_chain_parity.py against the v3.18.9 baseline
        # fixture (bit-identical across 200 ticks). FOLD-side context
        # fields are zero-defaulted here because the FOLD-side variables
        # haven't been computed yet at this tick offset; the SCRUM chain
        # only consults SCRUM-side gates (gate.side filter in __init__).
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
            hyst_armed_scrum_side=bool(getattr(
                self, "_hyst_armed_scrum_side", False)),
            hyst_armed_fold_side=False,
            hyst_ref_scrum_side=float(getattr(
                self, "_hyst_ref_scrum_side", 0.0) or 0.0),
            hyst_ref_fold_side=0.0,
            mem253_at_ceiling=False,
            mem253_smart_ceiling_usd=0.0,
            mem253_current_pos=0.0,
            has_fold_tranches=bool(self._fold_tranches),
            n_fold_tranches=len(self._fold_tranches or []),
            htf_bias_name=(str(_htf_bias_dir.name)
                            if _htf_bias_dir is not None else None),
            htf_blocks_scrum=bool(_htf_blocks_scrum),
            htf_blocks_fold=False,
            scrumming_interval_pct=float(
                self.config.scrumming_interval_pct or 0),
            trading_fee_pct=float(getattr(
                self.config, "trading_fee_pct", 0.6) or 0.6),
            # v3.18.13 (TA-gate cleanup Step 5): the MEM-196 ripe/deep
            # predicate is now passed TRUTHFULLY to the chain. The
            # inline local-variable rewrites that used to make the
            # chain's override gate a no-op are RETIRED (see the
            # operator-narrative emit blocks above for the lift-into-
            # chain commentary). `RipeHarvestScrumOverride` is now
            # load-bearing — it sees `ctx.ripe_scrum=True`, force-
            # passes its four declared overrides (midline_scrum,
            # target_fires, trend_hold, ta_bullish), and the chain's
            # `should_fire` reflects the override.
            ripe_scrum=bool(_ripe_scrum),
            deep_fold=bool(_deep_fold),
            # ── v3.19.18 — call-site activation of v3.19.16 + v3.19.17 gates ──
            # ADX gate (v3.19.16) and EfficiencyRatio gate (v3.19.17) landed
            # additively with sentinel-zero defaults; they were inert until
            # this call-site wiring. Pull ADX + ER readings from the
            # VotingSummary's signal details. When ``summary`` is None
            # (insufficient candles), we fall through to the sentinel-zero
            # defaults declared in GateContext, keeping the gates inert
            # exactly as before. Both gates pass under their sentinel.
            adx=_extract_signal_detail(summary, "adx", "adx", 0.0),
            efficiency_ratio=_extract_signal_detail(summary, "kaufman_er", "er", 0.0),
            # v3.20.7 — z-score from VotingSummary's zscore signal.
            # Real z-scores can be any real number; 0.0 is both
            # "not populated" sentinel and "exactly at mean" — gate
            # passes in both cases since |0| < 2.0 threshold.
            z_score=_extract_signal_detail(summary, "zscore", "z", 0.0),
        )
        _scrum_chain_result = self._scrum_chain.evaluate(_scrum_ctx)
        # v3.20.9 — emit risk-gate forensic snapshot if any risk gate
        # blocked. Closes v3.20.6 audit Finding #10. Additive; existing
        # per-gate REFUSED log emissions are unchanged.
        self._emit_risk_gate_snapshot(
            "scrum", _scrum_chain_result, summary, float(ticker.last))
        # -- STAGE TWO of the operator's two-stage Stack rule -----------
        # v3.23.44. The price threshold ACTIVATED these tranches at the
        # top of the tick; only here, with `_scrum_chain_result` in hand,
        # has the trading condition MANIFESTED. Spending sits inside the
        # should_fire branch, so a chain refusal -- and every pre-chain
        # return above -- prevents the sell. A refused tick leaves each
        # tranche pending and activated, ready for the next tick that is
        # authorised; losing it would be the same defect as spending it.
        #
        # The chain verdict cannot be moved up to the stage-one call
        # site instead: 25 of `GateContext`'s inputs (bb_pos, delta,
        # is_bullish, scrum_ok, target_fires, the eff_* set and the rest)
        # are computed between that call and this line.
        _stack_spent = 0
        if _scrum_chain_result.should_fire:
            _stack_spent = await self._spend_activated_stack_tranches(
                current_price=float(ticker.last), summary=summary)

        if _stack_spent > 0:
            # Spending an activated tranche IS this tick's SCRUM sell:
            # the tranches were split from an earlier SCRUM decision on
            # this same position, which is why no fresh `scrum_asset`
            # sell follows. Firing both would sell one Target Delta
            # twice, and the fresh sell would re-enter
            # `_open_stack_from_scrum` and open a Stack on a Stack. The
            # HOLD SCRUM branches below are skipped for the same reason:
            # the bot did not hold this tick, it sold.
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"SCRUM SERVED BY STACK: {_stack_spent} activated "
                         f"tranche(s) spent under this tick's authorised "
                         f"gate-chain decision. No fresh SCRUM sell this "
                         f"tick -- the tranches carry this Target Delta."))
        elif _scrum_chain_result.should_fire:
            scrum_asset = abs(delta) / ticker.last
            # v3.20.11 — fire-time forensic snapshot. Pairs with the
            # v3.20.9 RISK GATE SNAPSHOT on the refusal path; the
            # trade-attribution tool reads both to classify every
            # decision tick. The overrides_applied list comes from
            # the chain result so the classifier can identify
            # override-fired trades (RipeHarvestScrum / DeepFold).
            try:
                self._emit_trade_fire_snapshot(
                    "scrum", summary, float(ticker.last),
                    decision_extra={
                        "delta": round(float(delta), 6),
                        "scrum_asset": round(float(scrum_asset), 8),
                        "overrides_applied": list(
                            getattr(_scrum_chain_result,
                                    "overrides_applied", []) or []),
                    },
                )
            except Exception as _sup:  # R28-OK: forensic emit must never block trading
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

            # v3.16.58 — Pre-decision min_cost guard. Operator bug
            # 2026-05-14: bot stuck retrying $0.33 SCRUM every tick
            # because Target Delta was below Coinbase $1.00 min_cost.
            # Pre-flight guard refused at the API layer but the bot
            # kept re-issuing the same tick decision. v3.16.58: detect
            # at decision-time, skip the attempt, emit throttled log.
            _scrum_skipped_below_min = False
            try:
                _qrate_for_cost = float(self._quote_to_usd or 1.0)
                _scrum_notional_usd = (
                    scrum_asset * float(ticker.last) * _qrate_for_cost)
                _min_amt_sc, _min_cost_sc, _ = (
                    await self._get_market_limits(self.config.symbol))
                # v3.16.59 — check BOTH min_cost (USD notional) AND
                # min_amount (unit count). Operator-discovered 2026-05-14:
                # LINK had 11 PRE-FLIGHT REJECTED entries for below
                # min_amount rather than min_cost. Same retry-storm class
                # of bug, different threshold side.
                _below_min_cost_sc = (
                    _min_cost_sc > 0 and _scrum_notional_usd < _min_cost_sc)
                _below_min_amt_sc = (
                    _min_amt_sc > 0
                    and _scrum_notional_usd < _min_amt_sc * float(ticker.last))
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
                                f"min_cost ${_min_cost_sc:.2f}")
                        if _below_min_amt_sc:
                            _reason_parts.append(
                                f"amount {scrum_asset:.8f} < "
                                f"min_amount {_min_amt_sc:.8f}")
                        self._bus.emit("bot.log", bot_id=self.bot_id,
                            message=(f"SCRUM HELD (below min trade size): "
                                     f"Target Delta ${abs(delta):.4f} = "
                                     f"{scrum_asset:.8f} units × "
                                     f"${float(ticker.last):.8f}. "
                                     f"{self.config.symbol} blockers: "
                                     f"{'; '.join(_reason_parts)}. "
                                     f"Bot intentionally idle until "
                                     f"conditions allow a tradeable "
                                     f"size. (Throttled: next emit "
                                     f"~5 min.)"))
            except Exception as _mc_exc:  # R28-OK: probe; fail-open
                logger.debug(
                    "Bot %s SCRUM min_cost pre-check raised: %s "
                    "(falling through to normal _execute_sell)",
                    self.bot_id, _mc_exc)

            if _scrum_skipped_below_min:
                # Don't call _execute_sell; sell_fill stays unset.
                # Use a sentinel-None so the existing abort-log path
                # below correctly silences (already gated on the skip flag).
                sell_fill = None
            else:
                # v3.13.8 MEM-190 / Chunk 6 — capture actual fill price from sell.
                # Use it as the tranche ref (matching what the sim's _fill_price
                # does). Without this, tranches record the intended price and
                # fold's 'price < tranche.ref' gate is looser than the actual
                # sell justifies — silent loss of protection under slippage.
                sell_fill = await self._execute_sell(scrum_asset, ticker.last, summary)
            # MEM-207 — None means sell rejected. Must NOT create
            # phantom fold_tranches from a sell that didn't happen.
            # Old pattern (sell_fill = ticker.last fallback) would
            # queue tranches with a phantom ref price, create fake
            # "queued for fold" state, and claim sold units in
            # _main_lots that still belong to the bot. On next fold
            # cycle, bot would rebuy at the tranche ref (which never
            # sold) for profit accounting that's pure fiction.
            if sell_fill is None or sell_fill <= 0:
                # v3.16.58 — Don't emit "SCRUM ABORTED" if the skip was
                # intentional (below-min-cost guard fired). That path has
                # its own throttled log; ABORTED would be misleading.
                if not _scrum_skipped_below_min:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"SCRUM ABORTED: sell failed for "
                                f"{scrum_asset:.6f} units @ ${ticker.last:.8f}. "
                                f"No tranches queued; main_lots unchanged; "
                                f"no fold profit claimed. Retry next tick."))
            else:
                # --- Success path: sell_fill is a valid fill price ---
                scrum_usd = scrum_asset * sell_fill  # recompute from actual fill

                # v3.16.56 — Reset the Growth Rate Cap consumed counter
                # on SCRUM fire (Option A per operator directive
                # 2026-05-13). Target Delta has swung positive (position
                # was at/above target, prompting this sell); the fold
                # cycle has naturally ended. Next fold burst gets a
                # fresh cap budget.
                if self._fold_cycle_cap_consumed > 1e-9:
                    _prev_cap_consumed = self._fold_cycle_cap_consumed
                    self._fold_cycle_cap_consumed = 0.0
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"FOLD CYCLE RESET (SCRUM fired): "
                                 f"Target Delta swung positive, sell "
                                 f"event ends fold cycle. Growth Rate "
                                 f"Cap consumed ${_prev_cap_consumed:.4f} "
                                 f"this cycle — reset to $0.00. Next "
                                 f"fold burst gets fresh cap budget."))

                # v3.16.46 / v3.16.51 — Smart Wire SCRUM-time routing.
                # Operator directive 2026-05-10: "If I have a $5 scrum
                # and a 25% route to ETH then WHY THE FUCK did not
                # $1.25 go to ETH!?"
                #
                # v3.16.51 — extracted into _route_scrum_proceeds_via_wires
                # so Manual Fire SCRUM and Detonation harvest call the
                # SAME routing logic. Without that, only autonomous
                # SCRUMs routed; operator's heavy Manual Fire usage
                # ("dagger catch" pattern) bypassed the wire system.
                _scrum_routed_total = self._route_scrum_proceeds_via_wires(
                    scrum_usd=scrum_usd,
                    sell_fill=sell_fill,
                    label="scrum")

                # Reduce scrum_usd by routed amount so tranches/skim
                # operate on the remaining portion that stays with
                # this bot.
                scrum_usd = scrum_usd - _scrum_routed_total

                # v3.13.8 MEM-069 + MEM-171 port — consume _main_lots HIGHEST-PRICE-FIRST,
                # split into tranches preserving each lot's initial_buy_price. This replaces
                # the pre-port single-aggregate self._fold_queue_usd update.
                #
                # Per MEM-171 (ADR-004 patent-flagged): no unit sold at the current scrum
                # price will be rebought at a higher price than its ORIGINAL initial buy
                # price. Consuming HIGHEST-PRICE-FIRST ensures the most-expensive lots get
                # protection priority on fold-back (otherwise cheaper units would fill the
                # fold queue first and the expensive units would be stuck with no floor).
                self._main_lots.sort(key=lambda l: l["initial_buy_price"], reverse=True)
                _tranche_count_before = len(self._fold_tranches)
                _units_remaining = scrum_asset
                _first_new_tranche = None  # P1b: absorb pending wire credits here
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
                        "created_ts": time.time(),  # v3.16.39 P2-VIS
                    }
                    self._fold_tranches.append(_new_tr)
                    self._tranches_created_lifetime += 1  # v3.16.39 P2-VIS
                    if _first_new_tranche is None:
                        _first_new_tranche = _new_tr
                    _lot["units"] -= _take
                    _units_remaining -= _take
                    if _lot["units"] <= 1e-12:
                        self._main_lots.remove(_lot)

                # P1b Session 26 (2026-04-24) — if there were pending
                # wire credits parked before this scrum (target bot had
                # no tranches when a wire income arrived), absorb them
                # into the FIRST new tranche of this scrum burst. Only
                # applies when this scrum actually created at least one
                # new tranche AND there were zero tranches prior (wait-
                # for-new-tranche semantic per operator directive).
                if (_first_new_tranche is not None
                        and _tranche_count_before == 0
                        and self._pending_wire_credits > 0):
                    self._absorb_pending_wire_credits_into(_first_new_tranche)

                # MEM-234 — Scrum fold ratio, now applied through the
                # one shared helper. 2026-08-12: the same call runs on
                # the DIST sell and in _execute_manual_rebalance, so the
                # operator's single setting means one thing on all three
                # paths that build a fold tranche. The ORDER this path
                # always had is preserved: build, absorb, scale, top up.
                self._apply_scrum_fold_pct(
                    _tranche_count_before, scrum_usd, scrum_asset)

                # 2026-08-12 — TOP-UP ON AN OPPOSING TRADE. A SCRUM
                # sell is the opposing trade to a FOLD, so this is
                # where a part-spent tranche "gains more".
                #
                # WHY HERE, and not inside the build loop above.
                # `scrum_fold_pct` scales only the records THIS scrum
                # appended, the `_tranche_count_before:` slice. Merging
                # earlier would move this scrum's money into an OLDER
                # record, outside that slice, and the money would escape
                # the operator's fold-ratio setting entirely. Running
                # after means the amount merged is the amount that
                # already survived the ratio.
                self._top_up_remnant_fold_tranches(
                    _tranche_count_before,
                    float(getattr(bb_result, "lower", 0.0) or 0.0),
                    float(getattr(bb_result, "upper", 0.0) or 0.0))

                # Maintain legacy scalars as DERIVED aggregates for any external
                # consumer still reading them during the port migration. These are
                # no longer the source of truth — _fold_tranches is.
                self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)
                self._fold_queue_ref_price = sell_fill
                self.stats.trade_volume += scrum_usd

                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"SCRUM: Target=${self._target_balance:.2f}, "
                            f"Value=${current_value:.2f} (+{delta_pct:.1f}%), "
                            f"sold {scrum_asset:.6f} (${scrum_usd:.4f}) on "
                            f"{eff_direction.name} (conf={eff_confidence:.2f}, "
                            f"pos_boost={position_boost:+.2f}, bb={bb_pos:.0%}). "
                            f"Fill=${sell_fill:.8f}, queued ${scrum_usd:.4f} for fold.")
                self._bus.emit("trade.filled", bot_id=self.bot_id,
                    side="sell", type="SCRUM", price=sell_fill,
                    amount=scrum_asset, size=scrum_usd, profit=0)
                # v3.23.11 — voting.log + gate.log snapshots at fire (D-NEW-A).
                self._emit_voting_panel_snapshot_at_fire(
                    side="SELL", trade_action="SCRUM")
                self._emit_gate_decision_at_fire(
                    side="SELL", trade_action="SCRUM")
                # v3.16.59 — PnL event for SCRUM (USD-denominated gain).
                # Operator directive 2026-05-14: "SCRUM is a profitable
                # sell in terms of USD ... Both are % increases that
                # should be properly logged and reflect the platform's
                # core operating philosophy." Captures: USD value of
                # this sell event, and % gain vs the avg entry of the
                # consumed main_lots (the sell side's profit lens).
                try:
                    _avg_entry_for_pnl = 0.0
                    if self._main_lots:
                        # Weighted avg by units for cleanest reference
                        _tu = sum(float(l.get("units", 0) or 0)
                                  for l in self._main_lots)
                        if _tu > 0:
                            _avg_entry_for_pnl = sum(
                                float(l.get("units", 0) or 0)
                                * float(l.get("initial_buy_price", 0) or 0)
                                for l in self._main_lots) / _tu
                    _pct_vs_entry = 0.0
                    if _avg_entry_for_pnl > 0:
                        _pct_vs_entry = (
                            (sell_fill - _avg_entry_for_pnl)
                            / _avg_entry_for_pnl * 100.0)
                    self._bus.emit("pnl.event", bot_id=self.bot_id, data={
                        "kind": "SCRUM",
                        "asset": self.config.target_asset,
                        "symbol": self.config.symbol,
                        "units": float(scrum_asset),
                        "fill_price": float(sell_fill),
                        "usd_captured": float(scrum_usd) * float(
                            self._quote_to_usd or 1.0),
                        "avg_entry": float(_avg_entry_for_pnl),
                        "pct_vs_avg_entry": float(_pct_vs_entry),
                    })
                except Exception as _sup:  # R28-OK: PnL telemetry best-effort
                    logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
                # v3.15.50 — high-score counter: cumulative scrum USD.
                # v3.15.55 — `scrum_usd` is in QUOTE currency (the proceeds
                # of the sell). Multiply by quote→USD so the platform
                # high-score counter is always in true USD even on
                # crypto-quoted pairs.
                _scrum_usd_true = float(scrum_usd) * float(self._quote_to_usd or 1.0)
                self.stats.total_scrummed_usd += _scrum_usd_true
                # v3.23.65 SWOS retention counter (auto scrum path).
                self.note_scrum_retention_usd(_scrum_usd_true)
                # v3.15.52 — record side for opposite-direction hysteresis
                self._last_trade_side = "SCRUM"
                # v3.15.77 — disarm both gates so the next tick re-arms
                # if/when delta drifts opposing.
                self._reset_opposing_hysteresis_after_fill()

                # v3.13.8 MEM-186 / Chunk 2 — post-scrum state reset.
                # Per simulator.py:5494 "FIRE → SEARCH: after trade executes".
                # Keeps the state machine honest — next tick re-evaluates
                # detect/fire thresholds from scratch rather than staying
                # latched in FIRE and auto-scrumming every tick.
                self._scrum_target_mode = 'search'
                self._scrum_target_side = None
                # Chunk 4 + 6 — update band-travel baseline with actual fill
                self._last_trade_price = sell_fill

        elif delta > 0 and not below_interval and trend_hold:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"HOLD SCRUM: delta +${abs(delta):.4f} but TREND-HOLD active "
                        f"({trend_strength:.0%} bullish) — riding the trend")

        elif delta > 0 and not below_interval and not is_bullish:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"HOLD SCRUM: delta +${abs(delta):.4f} but TA={eff_direction.name} "
                        f"conf={eff_confidence:.2f} — waiting for BULLISH")

        # v3.15.57 — Upper BB Detection Threshold hard gate (operator
        # directive 2026-04-25). Surface explicitly when this gate is
        # the SOLE blocker so the operator can see the new rule
        # working. Conditions: would-have-scrummed (delta>0, interval
        # cleared, bullish, no trend-hold, scrum_ok, target_fires) but
        # bb_pos is below the upper detect threshold → refuse.
        elif (delta > 0 and not below_interval and is_bullish and not trend_hold
              and scrum_ok and target_fires and not _bb_above_upper_dt
              and not _cb_blocks_scrum):
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(
                    f"SCRUM REFUSED (Upper BB Detection Threshold): "
                    f"bb_pos={bb_pos:.3f} < upper_detect={_bb_upper_dt:.3f} "
                    f"(scrum_detect_pct={self.config.scrum_detect_pct}%). "
                    f"Operator rule: SCRUM cannot occur below the Upper "
                    f"BB Detection Threshold. All other gates passed."))
            self._emit_trade_notification(
                "SCRUM", "CANCELLED",
                f"bb_pos {bb_pos:.3f} < upper detect {_bb_upper_dt:.3f}")

        # v3.15.58 — Soft Circuit Breaker on SCRUM side blocks. Surface
        # explicitly when this is the SOLE blocker so the operator sees
        # the cooldown countdown.
        elif (delta > 0 and not below_interval and is_bullish and not trend_hold
              and scrum_ok and target_fires and _bb_above_upper_dt
              and _cb_blocks_scrum):
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(
                    f"SCRUM BLOCKED by SOFT CIRCUIT BREAKER: trip @ "
                    f"{self._cb_soft_trip_pct:.2f}% "
                    f"(threshold {self.config.circuit_breaker_soft_pct:.2f}%); "
                    f"{self._cb_soft_cooldown_remaining} candle(s) of cooldown "
                    f"remaining before SCRUM side re-opens."))

        # v3.15.61 — Higher-TF phantom bias contradicts SCRUM intent.
        # Surface explicitly when this is the SOLE blocker so the
        # operator can audit the phantom signals doing the gating.
        elif (delta > 0 and not below_interval and is_bullish and not trend_hold
              and scrum_ok and target_fires and _bb_above_upper_dt
              and not _cb_blocks_scrum and _htf_blocks_scrum):
            _bull_w = _htf_bias_detail.get("bull_weight", 0.0)
            _bear_w = _htf_bias_detail.get("bear_weight", 0.0)
            _contribs = _htf_bias_detail.get("contributors", [])
            _summary = ", ".join(
                f"{c.get('tf', '?')}={c.get('direction', '?')}"
                f"@{c.get('conf', 0):.2f}"
                for c in _contribs if not c.get('skipped')
            ) or "no usable phantoms"
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(
                    f"SCRUM REFUSED (Higher-TF Bias gate): higher-TF "
                    f"phantom consensus is BULLISH "
                    f"(bull weight {_bull_w:.2f} > bear {_bear_w:.2f}). "
                    f"Selling here would fight the higher-TF trend. "
                    f"Contributors: {_summary}."))
            self._emit_trade_notification(
                "SCRUM", "CANCELLED",
                f"higher-TF BULLISH bias ({_bull_w:.2f} vs {_bear_w:.2f})")

        # === FOLD: tranche-filtered buyback when BEARISH + per-tranche gates pass ===
        #
        # v3.13.8 MEM-069 + MEM-171 port. Replaces the pre-port single-aggregate
        # fold block. Two gates per tranche, both must be satisfied to rebuy:
        #   (1) price < tranche["ref"]                  — positive arithmetic vs sell
        #   (2) price <= tranche["initial_buy_price"]   — MEM-171 profit floor
        #
        # Only eligible tranches are rebought; others wait. If NO tranches are
        # eligible at the current price, the bot holds — preserving cost basis
        # discipline. On a volatile asset, this may mean sitting on USD for
        # extended periods rather than rebuying "cheap" units that are still
        # above their original cost basis.
        # MEM-253 pre-buy territory gate v3 (v3.16.53).
        # BEFORE evaluating fold eligibility, TA, or building any order:
        # is the current position above the SMART CEILING (when enabled)?
        # If yes, skip the entire fold branch — bot is at maturity and
        # awaiting detonation harvest.
        #
        # v3.16.53 — removed the Target-Delta Layer 1 check that
        # v3.16.50 added here. Fold-back is a tranche-consuming rebuy,
        # not a new-position buy; it mechanically produces position >
        # target as the surplus mechanism that drives organic target
        # growth. Layer 1 blocking caused 0 fold-back closures across
        # the entire platform because every bot with prior accumulation
        # already had position above target. Smart Ceiling (Layer 2)
        # remains the only legitimate position-level cap here.
        _cap_pct = float(getattr(self.config, "max_target_growth_pct", 1.0))
        _anchor = float(getattr(self, "_anchor_target_balance",
                                self._target_balance))
        _mem253_per_cycle_budget = _anchor * (_cap_pct / 100.0)
        _mem253_current_pos = float(self._current_holdings) * float(ticker.last)

        # Layer 2 — Smart Ceiling (when enabled) — the ONLY pre-decision
        # ceiling check that applies to fold-back. v3.16.53.
        _mem253_at_smart_ceiling = False
        _mem253_smart_ceiling_usd = None
        if getattr(self.config, "position_ceiling_enabled", False):
            try:
                _smart_mult_253 = float(getattr(
                    self.config, "position_ceiling_multiple", 1.0))
                _smart_mult_253 = max(1.0, min(10.0, _smart_mult_253))
                _mem253_smart_ceiling_usd = _anchor * _smart_mult_253
                _mem253_at_smart_ceiling = (
                    _mem253_current_pos >= _mem253_smart_ceiling_usd)
            except (TypeError, ValueError, AttributeError) as _sup:
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        # Alias for the legacy variable name still used by downstream
        # gate chain (_fold_blockers append, fold conditions, hedge gate).
        _mem253_at_ceiling = _mem253_at_smart_ceiling
        _mem253_at_any_ceiling = _mem253_at_smart_ceiling
        if _mem253_at_smart_ceiling and self._fold_tranches:
            # Throttled log so a long ceiling-hold doesn't spam the console.
            self._fold_ceiling_hold_count = getattr(
                self, "_fold_ceiling_hold_count", 0) + 1
            if self._fold_ceiling_hold_count % 60 == 1:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(
                        f"FOLD HOLD (Smart Ceiling): position "
                        f"${_mem253_current_pos:.2f} ≥ Smart Ceiling "
                        f"${_mem253_smart_ceiling_usd:.2f} "
                        f"(anchor ${_anchor:.2f} × multiple). "
                        f"Fold branch skipped — bot at maturity, "
                        f"awaiting detonation harvest on bullish vote."))
        elif not _mem253_at_smart_ceiling:
            # Clear throttle when back in-range.
            self._fold_ceiling_hold_count = 0

        # v3.15.57 — Lower BB Detection Threshold hard gate (operator
        # directive 2026-04-25: "Folds cannot occur above the Lower BB
        # Detection Threshold"). Applied AFTER all existing TA / midline
        # / DEEP-FOLD overrides so MEM-196 cannot bypass it. Manual fire
        # bypasses naturally because manual fire never traverses this
        # auto-fold path.
        # v3.15.58 — Soft Circuit Breaker on FOLD side also blocks here.
        _cb_blocks_fold = self._cb_soft_active_side == "fold"
        # v3.15.61 — Higher-TF phantom bias gate (operator directive
        # 2026-04-26). FOLD is buying INTO a downward bias; if higher-TF
        # phantoms say BEARISH, buying here is fighting the trend.
        # Defaults to permissive (no override) when phantoms aren't
        # attached or have no usable summaries — same _htf_bias_dir
        # variable computed once near the SCRUM gate above.
        _htf_blocks_fold = (_htf_bias_dir == SignalDirection.BEARISH)
        # v3.16.15 — operator-toggleable fold gates (mirror of scrum side).
        # `fold_hold_in_downtrend` flag is reserved on BotConfig but has
        # no current gate to toggle (no sustained-downtrend protection
        # exists on fold side today; future symmetric implementation).
        _flag_fold_require_ta_bearish = bool(getattr(
            self.config, "fold_require_ta_bearish", True))
        _flag_fold_defer_to_htf = bool(getattr(
            self.config, "fold_defer_to_htf", True))
        _eff_is_bearish = is_bearish if _flag_fold_require_ta_bearish else True
        _eff_htf_blocks_fold = _htf_blocks_fold if _flag_fold_defer_to_htf else False

        # v3.16.16 — capture FOLD gate blockers for the dashboard fire
        # button (mirror of the SCRUM-side block above).
        #
        # v3.18.13 — Step 5 cleanup. Two checks (`ta_bearish`,
        # `midline_fold`) now honor the MEM-196 deep-fold override
        # predicate so this accumulator stays in sync with the chain's
        # `DeepFoldOverride` (which declares those exact two gates as
        # its overrides). MEM-171 per-tranche price-floor is NOT
        # overrideable — it's enforced downstream and not part of this
        # gate chain.
        _fold_blockers: list[str] = []
        if not self._fold_tranches:
            _fold_blockers.append("no-tranches-queued")
        if not _eff_is_bearish and not _deep_fold:
            # v3.24.43 — was `TA-not-bearish(dir={name})`, which rendered
            # as the self-contradicting "TA-not-bearish(dir=BEARISH)"
            # whenever only the confidence floor was blocking. Name the
            # failing conjunct.
            _fold_blockers.append(
                f"TA-conf-below-floor(dir={eff_direction.name},"
                f"conf={eff_confidence:.2f}<{_TA_CONFIDENCE_FLOOR:.2f})"
                if eff_direction in (SignalDirection.BEARISH,
                                     SignalDirection.NEUTRAL)
                else f"TA-not-bearish(dir={eff_direction.name})")
        if not fold_ok_midline and not _deep_fold:
            _fold_blockers.append(f"fold_ok_midline=False(bb_pos={bb_pos:.2f})")
        if _mem253_at_ceiling:
            _fold_blockers.append("MEM-253-position-ceiling")
        if not _bb_below_lower_dt:
            _fold_blockers.append(f"BB-above-lower-detect(bb_pos={bb_pos:.2f}>{_bb_lower_dt:.2f})")
        if _cb_blocks_fold:
            _fold_blockers.append("CB-soft-trip")
        if _eff_htf_blocks_fold:
            _fold_blockers.append("HTF-bearish")
        # v3.18.1 — OTD-hysteresis gate (FOLD side).
        if not _hyst_ok_fold_side:
            try:
                _ref_px = float(self._hyst_ref_fold_side or 0)
                _eff_pct = (
                    float(self.config.scrumming_interval_pct or 0)
                    + float(getattr(
                        self.config, "trading_fee_pct", 0.6) or 0.6))
                _required = _ref_px * (1.0 - _eff_pct / 100.0)
                _fold_blockers.append(
                    f"OTD-hyst(px ${ticker.last:.8f} > "
                    f"${_required:.8f}; pivot ${_ref_px:.8f} "
                    f"- {_eff_pct:.2f}%)")
            except Exception:  # R28-OK: diag formatting; non-fatal
                _fold_blockers.append("OTD-hyst-armed")
        try:
            self._last_gate_state["fold_armed"] = (len(_fold_blockers) == 0)
            self._last_gate_state["fold_blockers"] = list(_fold_blockers)
            # v3.18.9 (TA-gate cleanup Step 1) — capture FOLD-side gate
            # fixture. Mirrors the SCRUM-side capture above. Audit
            # 2026-05-20.
            self._last_gate_state["fold_fixture"] = {
                "has_fold_tranches": bool(self._fold_tranches),
                "n_fold_tranches": len(self._fold_tranches or []),
                # v3.24.18 — see the scrum_fixture note. A "lower"
                # landing strip forces is_bearish True, so the fold
                # side has the same untracked override the scrum side
                # had.
                "landing_strip": bool(
                    bb_result.landing_strip if bb_result else False),
                "landing_strip_side": str(
                    bb_result.landing_strip_side
                    if bb_result else "") or "",
                "landing_strip_candles": int(
                    bb_result.landing_strip_candles
                    if bb_result else 0),
                "is_bearish": bool(is_bearish),
                "eff_direction": str(eff_direction.name),
                "fold_ok_midline": bool(fold_ok_midline),
                "mem253_at_ceiling": bool(_mem253_at_ceiling),
                "mem253_smart_ceiling_usd": float(
                    _mem253_smart_ceiling_usd if _mem253_smart_ceiling_usd else 0.0),
                "mem253_current_pos": float(
                    _mem253_current_pos if _mem253_current_pos else 0.0),
                "bb_below_lower_dt": bool(_bb_below_lower_dt),
                "cb_blocks_fold": bool(_cb_blocks_fold),
                "htf_blocks_fold": bool(_htf_blocks_fold),
                "flag_fold_require_ta_bearish": bool(
                    _flag_fold_require_ta_bearish),
                "flag_fold_defer_to_htf": bool(_flag_fold_defer_to_htf),
                "eff_is_bearish": bool(_eff_is_bearish),
                "eff_htf_blocks_fold": bool(_eff_htf_blocks_fold),
                "hyst_ok_fold_side": bool(_hyst_ok_fold_side),
                "hyst_armed_fold_side": bool(getattr(
                    self, "_hyst_armed_fold_side", False)),
                "hyst_ref_fold_side": float(getattr(
                    self, "_hyst_ref_fold_side", 0.0) or 0.0),
            }
        except Exception as _sup:  # R28-OK: dashboard hint cache; failure must not block tick
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        # ─── v3.16.41 P0-DIAG — Compound-mechanism diagnostic logging ───
        # Operator-queued investigation (post-v3.16.40 retraction): emit
        # diagnostic FOLD_DIAG lines so live runs surface exactly why
        # fold-back tranche-dequeue isn't firing despite tranches queued.
        # Three log types:
        #   (a) FOLD_DIAG_BLOCKED — when tranches exist AND >=1 tranche
        #       is per-tranche eligible (price < ref AND <= initial_buy)
        #       AND the gate is BLOCKED. Dedup'd by blocker-set key so
        #       the same condition doesn't spam every tick.
        #   (b) FOLD_DIAG_SNAPSHOT — every 100 ticks when any tranches
        #       exist. Periodic state dump for offline analysis.
        #   (c) FOLD_DIAG_NO_PER_TRANCHE_ELIGIBLE — when tranches exist
        #       but NONE pass strict per-tranche eligibility. This is
        #       the "regime-blocked" case — confirms whether market
        #       conditions ever supply the gate.
        # All emitted to bot.log (Activity Log) prefixed FOLD_DIAG so
        # operator can grep for them. REMOVE THIS BLOCK after diagnosis
        # is complete (sadp: temporary instrumentation, not load-bearing).
        #
        # v3.24.47 (Phase 1 Step 2) — the OTD factor is hoisted here from
        # its old site inside the fold-execution branch so the diagnostic
        # counters below can use the SAME value the executor will use.
        # Computing it twice would let the instrument and the executor
        # drift apart again, which is the whole defect being fixed. The
        # executor's own computation now reads this binding.
        #
        # v3.25.8 — the OTD now includes the TRADING FEE. It read
        # `scrumming_interval_pct` alone while three other sites already
        # read `scrumming_interval_pct + trading_fee_pct`:
        # `HysteresisGate` (gate_chain.py:405), the FOLD blocker
        # diagnostic just above, and the STACK open. A tranche could
        # therefore be re-bought at a price that cleared its interval but
        # still lost the round trip to fees. Operator ruling 2026-08-12:
        # "This issue should be getting mitigated by the trade fee being
        # added to the Minimum Opposing Trading Distance" and
        # "Functionality should be mirrored between either side of the
        # ladder."
        #
        # The arithmetic moved to `otd_math` so there is ONE definition
        # rather than a fourth copy. The clamp applies to the SUM, after
        # the fee -- see that module for why the other order breaks the
        # invariant the clamp asserts. Imported locally, matching the
        # STACK open's pattern, to keep module load light.
        from .otd_math import (  # local import: keep module load light
            fold_rebuy_factor_from_pct,
            minimum_opposing_trade_distance_pct,
        )
        _otd_pct_for_gate = 0.0
        try:
            _otd_pct_for_gate = minimum_opposing_trade_distance_pct(
                getattr(self.config, 'scrumming_interval_pct', 0) or 0,
                getattr(self.config, 'trading_fee_pct', 0.6) or 0.6)
        except (TypeError, ValueError):
            _otd_pct_for_gate = 0.0
        _otd_factor = fold_rebuy_factor_from_pct(_otd_pct_for_gate)

        try:
            self._fold_diag_tick += 1
            if self._fold_tranches:
                # v3.24.47 (Phase 1 Step 2) — measure what the EXECUTOR
                # measures. This counter used
                #     ticker.last < ref AND ticker.last <= initial_buy_price
                # while the executor's filter is
                #     ticker.last <= ref * _otd_factor
                # Three differences, all of them wrong in some regime:
                # strict `<` versus `<=`; an initial_buy_price term the
                # executor does not have; and no OTD factor at all, so
                # it counted tranches eligible at prices the executor
                # would refuse and missed the OTD margin entirely.
                #
                # An instrument that measures a different predicate than
                # the thing it reports on cannot confirm or refute a
                # change to that thing. Every "N of M strict-eligible"
                # figure ever read out of this log was computed on the
                # wrong criterion.
                _per_tranche_eligible = sum(
                    1 for _t in self._fold_tranches
                    if ticker.last <= float(_t.get("ref", 0)) * _otd_factor
                )
                # Retained as a SECONDARY reading only. It is not a gate:
                # no initial_buy_price term appears in the executor's
                # predicate. Kept because MEM-171 provenance is still
                # worth observing, and labelled so nobody mistakes it for
                # an eligibility criterion again.
                _patent_only_eligible = sum(
                    1 for _t in self._fold_tranches
                    if ticker.last <= float(_t.get("initial_buy_price",
                                                     _t.get("ref", 0)))
                )
                _gate_armed_now = (len(_fold_blockers) == 0)

                # (a) Blocked path: tranches eligible per strict criteria
                # but gate refused. Log on transitions only (dedup).
                if _per_tranche_eligible > 0 and not _gate_armed_now:
                    _blocker_key = "|".join(sorted(_fold_blockers))
                    if _blocker_key != self._fold_diag_last_blocker_set:
                        self._bus.emit("bot.log", bot_id=self.bot_id,
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
                                f"profit_folding_active={self.config.profit_folding_active}."))
                        self._fold_diag_last_blocker_set = _blocker_key

                # (b) Periodic snapshot — every 100 ticks while tranches
                # exist. Captures slow-moving state regardless of gate
                # decisions, for offline timeline analysis.
                if self._fold_diag_tick % 100 == 0:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
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
                            f"created_lifetime={self._tranches_created_lifetime}."))

                # (c) Regime-blocked: tranches exist, none strict-eligible.
                # This is the most common case if the strategy is waiting
                # for prices to drop below ref. Throttled to once per 500
                # ticks to avoid spam during sustained sideways-up regimes.
                if (_per_tranche_eligible == 0
                        and self._fold_diag_tick % 500 == 0):
                    _min_ref = min(float(_t.get("ref", 0))
                                   for _t in self._fold_tranches)
                    # v3.24.46 — `_min_initial` was computed here purely
                    # to be printed. The executor's predicate has no
                    # initial_buy_price term, so quoting it implied a
                    # gate that does not run. Dropped rather than left
                    # unused.
                    # v3.24.46 (Phase 1 Step 1) — the activation price
                    # was reported as _min_ref, but the executor's filter
                    # is `ticker.last <= ref * _otd_factor`, so the real
                    # trigger sits an OTD percentage BELOW that. Quoting
                    # _min_ref told the operator price was closer to
                    # firing than it was, on every diagnostic tick. The
                    # `minimum initial_buy` figure is dropped entirely:
                    # no initial_buy_price term appears in the executor's
                    # predicate, so it was never the binding gate.
                    # v3.24.47 — reads the single hoisted binding rather
                    # than recomputing. A second copy of this arithmetic
                    # is exactly how the instrument drifted from the
                    # executor in the first place.
                    _otd_diag = _otd_pct_for_gate
                    _activation = _min_ref * _otd_factor
                    self._bus.emit("bot.log", bot_id=self.bot_id,
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
                            if _activation > 0 else
                            f"FOLD_DIAG_NO_STRICT_ELIGIBLE: "
                            f"{len(self._fold_tranches)} tranches queued "
                            f"but 0 strict-eligible at ${ticker.last:.8f}; "
                            f"lowest tranche ref=${_min_ref:.8f}."))
        except Exception as _diag_exc:  # R28-OK: diagnostic-only, must not break tick
            logger.debug("FOLD_DIAG emission failed: %s", _diag_exc)

        # v3.18.1 — Wire the OTD hysteresis gate into the auto FOLD
        # execution branch (was previously bypassed — see SCRUM-side
        # comment block above at line ~5444 for full root-cause notes).
        #
        # v3.18.12 — TA-gate cleanup Step 4 cutover. The 7-clause AND
        # conjunction that used to live here is now delegated to
        # self._fold_chain.evaluate(ctx). All FOLD-side variables are
        # in scope at this tick offset, so the GateContext is fully
        # populated (no zero-defaults on the FOLD side).
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
            hyst_armed_scrum_side=bool(getattr(
                self, "_hyst_armed_scrum_side", False)),
            hyst_armed_fold_side=bool(getattr(
                self, "_hyst_armed_fold_side", False)),
            hyst_ref_scrum_side=float(getattr(
                self, "_hyst_ref_scrum_side", 0.0) or 0.0),
            hyst_ref_fold_side=float(getattr(
                self, "_hyst_ref_fold_side", 0.0) or 0.0),
            mem253_at_ceiling=bool(_mem253_at_ceiling),
            mem253_smart_ceiling_usd=float(
                _mem253_smart_ceiling_usd
                if _mem253_smart_ceiling_usd else 0.0),
            mem253_current_pos=float(
                _mem253_current_pos
                if _mem253_current_pos else 0.0),
            has_fold_tranches=bool(self._fold_tranches),
            n_fold_tranches=len(self._fold_tranches or []),
            htf_bias_name=(str(_htf_bias_dir.name)
                            if _htf_bias_dir is not None else None),
            htf_blocks_scrum=bool(_htf_blocks_scrum),
            htf_blocks_fold=bool(_htf_blocks_fold),
            scrumming_interval_pct=float(
                self.config.scrumming_interval_pct or 0),
            trading_fee_pct=float(getattr(
                self.config, "trading_fee_pct", 0.6) or 0.6),
            # v3.18.13 (TA-gate cleanup Step 5): MEM-196 ripe/deep
            # predicate passed TRUTHFULLY — see SCRUM-side comment
            # above at the cutover site for the full rationale.
            # `DeepFoldOverride` is now load-bearing for its two
            # declared overrides (midline_fold, ta_bearish).
            ripe_scrum=bool(_ripe_scrum),
            deep_fold=bool(_deep_fold),
            # v3.20.7 — z-score field for ZScoreExtremityGate(side=
            # "fold"). At z > +2.0 the gate blocks FOLD (don't buy
            # the statistical top). adx + efficiency_ratio omitted
            # because their gates are SCRUM-side only — the FOLD
            # chain doesn't filter them.
            z_score=_extract_signal_detail(summary, "zscore", "z", 0.0),
        )
        _fold_chain_result = self._fold_chain.evaluate(_fold_ctx)
        # v3.20.9 — symmetric snapshot on FOLD-side risk-gate blocks.
        self._emit_risk_gate_snapshot(
            "fold", _fold_chain_result, summary, float(ticker.last))
        if _fold_chain_result.should_fire:
            # v3.20.11 — symmetric fire-time forensic snapshot.
            try:
                self._emit_trade_fire_snapshot(
                    "fold", summary, float(ticker.last),
                    decision_extra={
                        "delta": round(float(delta), 6),
                        "n_fold_tranches": len(
                            self._fold_tranches or []),
                        "overrides_applied": list(
                            getattr(_fold_chain_result,
                                    "overrides_applied", []) or []),
                    },
                )
            except Exception as _sup:  # R28-OK: forensic emit must never block trading
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
            # TD-017 (trading H-4): filter malformed tranches before they reach
            # fold math. ref <= 0 would cause ZeroDivisionError in the
            # sum(t["usd"] / t["ref"]) step downstream. A bad tranche should
            # be logged and dropped, not crash the fold cycle.
            _malformed = [t for t in self._fold_tranches if not (t.get("ref", 0) > 0)]
            if _malformed:
                # v3.23.7 Anomaly C: malformed tranches dropped here were
                # never real cycles (ref<=0 means the entry condition was
                # never met). Counting them in `_tranches_closed_lifetime`
                # would inflate the closed/created invariant; instead we
                # track them in a separate `_tranches_malformed_dropped`
                # counter so the operator can see drop volume without it
                # polluting the cycle-throughput ratio.
                self._tranches_malformed_dropped = (
                    int(getattr(self, "_tranches_malformed_dropped", 0) or 0)
                    + len(_malformed))
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"FOLD GUARD: dropping {len(_malformed)} malformed "
                             f"tranche(s) with ref<=0. Operator visibility: "
                             f"{[t for t in _malformed]}. Malformed-"
                             f"dropped now {self._tranches_malformed_dropped}."))
                self._fold_tranches = [t for t in self._fold_tranches
                                        if (t.get("ref", 0) > 0)]
            # v3.16.43 — Architectural redesign per operator directive
            # 2026-05-08: "If anything, I should be compounding until a
            # configured smart ceiling of a given bot's position."
            #
            # The compound governance model shifts from PER-TRANCHE
            # patent-ceiling gating (initial_buy_price block) to
            # POSITION-LEVEL smart-ceiling gating (position_ceiling_usd
            # via MEM-253 / MEM-244, already in the outer gate chain).
            # This addresses the operator-flagged structural failure:
            # under the prior design, when asset price moved above the
            # tranche's initial_buy_price, the patent ceiling locked
            # the queue indefinitely — Acervator stopped compounding at
            # exactly the moment of asset success. Operator's exact
            # framing: "Its safe logic to say, I am above entry...its
            # only USD profit claiming from here...but that is not how
            # Acervator is supposed to work."
            #
            # New eligibility (per-tranche price gate):
            #   ticker.last <= ref × (1 - OTD/100)
            #
            # Per the operator's "buy no higher than x% (opposing trade
            # distance)" directive — the OTD threshold IS the per-tranche
            # max acceptable rebuy price. Naturally produces unit-surplus
            # because price has dropped at least OTD% below sell ref.
            #
            # Compound saturation (position-level governor):
            #   position_ceiling_usd = anchor × position_ceiling_multiple
            #   (MEM-244 fold rate taper kicks in at ratio 0.5;
            #    MEM-253 hard-stops at ratio >= 1.0)
            # Already in the outer fold-gate chain via _mem253_at_ceiling.
            #
            # TA validation (GEP):
            #   bearish + midline + lower-DT — never bypassed per operator.
            #
            # The per-tranche initial_buy_price field is RETAINED in
            # tranche records (export/import-compatible) but is no longer
            # consulted in the eligibility gate. It's informational —
            # tracks the original cost of the units in audit/visibility.
            # MEM-171 / ADR-004 patent invariant is NOT abandoned in
            # spirit — it's enforced at the strategy LEVEL via the
            # position ceiling (which bounds total accumulation cost
            # across the bot's lifetime), not at the tranche level.
            # v3.24.47 (Phase 1 Step 2) — `_otd_pct_for_gate` and
            # `_otd_factor` are computed ONCE, above the diagnostic
            # block, and read here. They used to be computed only at this
            # site while the diagnostic counters used an entirely
            # different predicate, so the instrument and the executor
            # could disagree. One binding means they cannot.
            _eligible = [
                t for t in self._fold_tranches
                if ticker.last <= float(t.get("ref", 0)) * _otd_factor
            ]
            # v3.16.41 P0-DIAG — fold-back gate PASSED, log eligibility detail
            try:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(
                        f"FOLD_DIAG_GATE_PASSED: TA-validated fold-back "
                        f"firing at ${ticker.last:.8f}. "
                        f"{len(_eligible)} of {len(self._fold_tranches)} "
                        f"tranches strict-eligible. "
                        f"cycle_cap_consumed=${self._fold_cycle_cap_consumed:.4f}, "
                        f"profit_folding_active={self.config.profit_folding_active}."))
            except Exception as _sup:  # R28-OK: diagnostic emission
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
            # v3.24.46 (Phase 1 Step 1) — bound BEFORE the guard so the
            # FOLD: Bought message can always name the cap-skipped count.
            # It is assigned inside the `if _eligible:` block below, and
            # today every path reaching that message passes through the
            # block, but relying on that is one refactor away from a
            # NameError raised while reporting a successful buy.
            _excluded = 0
            # 2026-08-12 — bound here for the same reason `_excluded`
            # is: the "FOLD: Bought" message names both, and both are
            # otherwise assigned inside the `if _eligible:` block below.
            # `_fold_plan` is what the dequeue walks, so an unbound name
            # there would raise AFTER the buy had already filled.
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
                # configured per-cycle growth rate (anchor ×
                # max_target_growth_pct/100). Excess tranches stay
                # queued for the NEXT TA-validated fold opportunity.
                # Sort highest-initial_buy_price-first so the most
                # expensive lots get fold-back priority (mirrors
                # SCRUM-side MEM-171 highest-priced-first consumption).
                _max_growth_pct = float(getattr(
                    self.config, 'max_target_growth_pct', 1.0))
                _cycle_cap_usd = (self._anchor_target_balance
                                   * _max_growth_pct / 100.0)
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
                    0.0,
                    _cycle_cap_usd - self._fold_cycle_cap_consumed)
                _elig_sorted = sorted(
                    _eligible,
                    key=lambda _t: -float(_t.get(
                        'initial_buy_price', _t.get('ref', 0))))
                # 2026-08-12 — PARTIAL CONSUMPTION. The packing loop is
                # `_plan_fold_consumption`; read its docstring for what
                # changed and why MEM-171 permits it.
                _fold_plan, _elig_capped, _partial_count = (
                    self._plan_fold_consumption(
                        _elig_sorted, _cap_remaining_for_queue))
                _running_usd = sum(_take for _, _take, _ in _fold_plan)
                _excluded = len(_eligible) - len(_elig_capped)
                if _excluded > 0 or _partial_count > 0:
                    _excluded_usd = (sum(float(t.get('usd', 0) or 0)
                                          for t in _eligible)
                                      - _running_usd)
                    # The old line called every undeployed dollar a
                    # "deferred tranche". Under partial consumption that
                    # dollar can also be the REMAINDER of a tranche this
                    # cycle just took from, which is a different thing,
                    # and the operator has to be able to tell them
                    # apart.
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(
                            f"FOLD CYCLE-CAP: deploying "
                            f"${_running_usd:.2f} of "
                            f"${(sum(float(t.get('usd',0) or 0) for t in _eligible)):.2f} "
                            f"eligible, bounded by the per-cycle growth "
                            f"cap ${_cycle_cap_usd:.2f} "
                            f"(${_cap_remaining_for_queue:.2f} remaining "
                            f"after ${self._fold_cycle_cap_consumed:.2f} "
                            f"consumed this cycle, "
                            f"{_max_growth_pct}% of anchor "
                            f"${self._anchor_target_balance:.2f}). "
                            f"{_partial_count} tranche(s) part-consumed "
                            f"— each keeps its remaining balance and "
                            f"stays queued. {_excluded} of "
                            f"{len(_eligible)} left untouched. "
                            f"${_excluded_usd:.2f} stays queued in "
                            f"total for the next TA-validated fold "
                            f"opportunity."))
                _eligible = _elig_capped
            if _eligible:
                # MEM-244 — Position Ceiling fold rate taper.
                # Operator Q2: "Slow fold rate — reduce interval size
                # the closer we get to ceiling." When ceiling enabled,
                # fold_rate_taper returns 1.0 with plenty of runway,
                # linearly tapers to 0.1 as ratio goes 0.5→1.0, and
                # hard-stops at 0.0 at/above ceiling. When ceiling
                # disabled, always returns 1.0 (no effect).
                _taper = self.fold_rate_taper
                if _taper <= 0.0:
                    # At/above ceiling — hard-stop fold
                    _ratio = self.ceiling_ratio or 0.0
                    # v3.15.55 — quote→USD-aware
                    _ceiling_pos_usd = (
                        self._current_holdings * ticker.last
                        * float(self._quote_to_usd or 1.0)
                    )
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"FOLD BLOCKED by position ceiling: "
                                 f"current ${_ceiling_pos_usd:.2f} "
                                 f">= ceiling ${self.position_ceiling_usd:.2f} "
                                 f"({_ratio*100:.1f}% of ceiling). "
                                 f"Scrum still allowed."))
                    _eligible = []  # falls through to the nothing-eligible path

            if _eligible:
                _fusd = sum(t["usd"] for t in _eligible)
                _funits = sum(t["units"] for t in _eligible)
                # Apply taper to the buy cost (preserves per-tranche
                # bookkeeping; the taper just reduces how much we
                # actually buy this tick).
                buy_cost = _fusd * _taper
                if _taper < 1.0:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"FOLD TAPER: ratio "
                                 f"{(self.ceiling_ratio or 0)*100:.1f}% of "
                                 f"ceiling → fold sized at {_taper*100:.0f}% "
                                 f"of eligible (${_fusd:.4f} → "
                                 f"${buy_cost:.4f})."))

                # v3.16.58 — Pre-decision min_cost guard (FOLD side).
                # If the combined eligible tranche USD (after taper) is
                # below the exchange's minimum trade size, skip the fold
                # attempt entirely with a throttled log. Without this,
                # the pre-flight guard refuses at the API layer but the
                # bot keeps re-issuing the same buy decision every tick.
                _fold_skipped_below_min = False
                try:
                    _qrate_fc = float(self._quote_to_usd or 1.0)
                    _fold_notional_usd = buy_cost * _qrate_fc
                    _min_amt_fc, _min_cost_fc, _ = (
                        await self._get_market_limits(self.config.symbol))
                    # v3.16.59 — check BOTH min_cost AND min_amount.
                    _fold_buy_units = buy_cost / float(ticker.last) if ticker.last > 0 else 0.0
                    _below_min_cost_fc = (
                        _min_cost_fc > 0
                        and _fold_notional_usd < _min_cost_fc)
                    _below_min_amt_fc = (
                        _min_amt_fc > 0
                        and buy_cost < _min_amt_fc * float(ticker.last))
                    if _below_min_cost_fc or _below_min_amt_fc:
                        _fold_skipped_below_min = True
                        import time as _t_fc
                        _now_ts_fc = _t_fc.time()
                        if (_now_ts_fc - self._below_min_fold_log_ts) >= 300.0:
                            self._below_min_fold_log_ts = _now_ts_fc
                            self._bus.emit("bot.log", bot_id=self.bot_id,
                                message=(f"FOLD HELD (below min trade size): "
                                         f"{len(_eligible)} eligible tranche(s) "
                                         f"totaling ${_fusd:.4f} (tapered to "
                                         f"${buy_cost:.4f}) is below "
                                         f"{self.config.symbol} min_cost "
                                         f"${_min_cost_fc:.2f}. Bot intentionally "
                                         f"holding; tranches stay queued until "
                                         f"more accumulate or price moves "
                                         f"enough. (Throttled: next emit ~5 min.)"))
                except Exception as _mc_fold_exc:  # R28-OK: probe; fail-open
                    logger.debug(
                        "Bot %s FOLD min_cost pre-check raised: %s "
                        "(falling through to normal _execute_buy)",
                        self.bot_id, _mc_fold_exc)

                buy_asset = buy_cost / ticker.last
                # extra_asset math uses the blended ref across eligible tranches,
                # which is equivalent to the per-tranche sum of (t["usd"]/t["ref"])
                # (R42 EPM parity with sim).
                asset_at_scrum = sum(t["usd"] / t["ref"] for t in _eligible)
                extra_asset = buy_asset - asset_at_scrum
                # Use the MIN ref across eligible tranches so the % cheaper reading
                # is conservative (vs picking max would overstate the discount).
                min_ref = min(t["ref"] for t in _eligible)
                pct_cheaper = (1 - ticker.last / min_ref) * 100
                accum_profit = extra_asset * ticker.last

                # Pre-compute with INTENDED price so we have baseline for
                # slippage comparison after the fill returns.
                _intended_buy_asset = buy_cost / ticker.last
                _intended_min_ref = min(t["ref"] for t in _eligible)

                # v3.16.58 — Skip _execute_buy if min_cost pre-check flagged
                # this fold attempt as below the exchange minimum.
                if _fold_skipped_below_min:
                    buy_fill = None
                else:
                    buy_fill = await self._execute_buy(
                        buy_cost, ticker.last, summary,
                        trace_context={
                            "path": "fold_rebuy",
                            "eligible_tranches": len(_eligible),
                            "min_ref": f"${min_ref:.8f}",
                            "pct_cheaper": f"{pct_cheaper:.2f}%",
                        })
                # MEM-207 — None means fold buy failed. Critical to abort
                # cleanly here: the old fallback ("buy_fill = ticker.last")
                # was one of the two paths that caused phantom-credit
                # accounting divergence in the 2026-04-22 operator log
                # (hedge rebalance path was the other). Failure path:
                # (1) do NOT dequeue eligible tranches — they stay in
                #     _fold_tranches so next tick can retry;
                # (2) do NOT book fold profit into target_balance or
                #     realised_pnl — no profit was actually realised;
                # (3) do NOT replenish hedge from phantom profit;
                # (4) do NOT append phantom lots to _main_lots;
                # (5) emit explicit FOLD ABORTED so operator sees it.
                if buy_fill is None or buy_fill <= 0:
                    # v3.16.58 — Don't emit "FOLD ABORTED" if the skip
                    # was intentional (below-min-cost guard fired).
                    # That path has its own throttled log.
                    if not _fold_skipped_below_min:
                        self._bus.emit("bot.log", bot_id=self.bot_id,
                            message=(f"FOLD ABORTED: rebuy failed at "
                                    f"${ticker.last:.8f} for "
                                    f"{len(_eligible)} eligible tranches. "
                                    f"Tranches stay queued; no profit booked; "
                                    f"no hedge replenish. Will retry next "
                                    f"tick."))
                    return

                # --- Success path: buy_fill is a valid fill price ---
                # v3.13.8 MEM-190 / Chunk 6 — recompute with actual fill
                buy_asset = buy_cost / buy_fill
                asset_at_scrum = sum(t["usd"] / t["ref"] for t in _eligible)
                extra_asset = buy_asset - asset_at_scrum
                pct_cheaper = (1 - buy_fill / _intended_min_ref) * 100
                # Compound surplus = extra units acquired (buy_fill < ref
                # means same USD buys MORE units than were sold).
                # Strictly positive only when buy_fill < weighted_avg_ref,
                # which is enforced by the strict eligibility filter
                # above (`ticker.last < t["ref"]`). This IS the per-cycle
                # liquidity surplus that drives organic target growth
                # per the operator's strategy thesis.
                accum_profit = extra_asset * buy_fill

                # Return rebought units to _main_lots, preserving each eligible
                # tranche's initial_buy_price. This is the MEM-171 "compounding
                # protection across cycles" rule — rebuy lots inherit the
                # original cost basis so a future scrum at a higher price can
                # still protect them from above-cost rebuys on subsequent folds.
                _total_elig_units = sum(t["units"] for t in _eligible) + 1e-12
                for _t in _eligible:
                    _share = _t["units"] / _total_elig_units
                    self._main_lots.append({
                        "units": buy_asset * _share,
                        "initial_buy_price": _t["initial_buy_price"],
                    })

                # 2026-08-12 — DEQUEUE BY DECREMENT. The mechanic is
                # `_settle_fold_plan`; read its docstring for why the
                # old value-compare could no longer work.
                _pre_remove = len(self._fold_tranches)
                _removed, _n_spent = self._settle_fold_plan(_fold_plan)
                # v3.16.39 P2-VIS — increment lifetime closed counter
                # by the actual removal count (not the planned count, in
                # case identity drift caused a partial dequeue — the
                # warning below catches that mismatch separately).
                if _removed > 0:
                    self._tranches_closed_lifetime += _removed
                # TD-017 (trading H-3): the count removed must match the
                # count the plan drained. It is no longer
                # `len(_eligible)` — a part-consumed tranche is
                # deliberately kept, so comparing against the admitted
                # count would now fire on every correct partial fold.
                if _removed != _n_spent:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"FOLD DEQUEUE MISMATCH: {_n_spent} "
                                 f"tranche(s) were drained to nothing but "
                                 f"{_removed} left the queue. Likely "
                                 f"concurrent mutation — investigate."))
                # Maintain legacy derived scalars
                self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)
                if not self._fold_tranches:
                    self._fold_queue_ref_price = 0.0

                self.stats.trade_volume += buy_cost

                # v3.23.7 — accum_profit-sourced surplus drain. Position-
                # vs-target frame retired (was v3.16.46/v3.16.50/v3.16.56).
                # See docs/audits/2026-06-13_v3_23_7_surplus_realignment_design.md.
                #
                # ──────────────────────────────────────────────────────────
                # Operator directive 2026-06-13: "Surplus = the realised
                # extra units the cycle acquired in DOLLAR terms,
                # regardless of whether position_value crossed back above
                # the new target this tick."
                #
                # The prior position-vs-target frame defined surplus as
                # max(0, position_value_after_fold - target_balance) — but
                # a fold-tranche fill on a bearish bot is by construction
                # re-zeroing a NEGATIVE target delta from below (position
                # was below target → bot bought to refill), so
                # position_value <= target was the typical case and
                # _new_surplus_usd evaluated to 0 even when the rebuy
                # literally produced extra units cheaper than the original
                # sell. The `extra_asset` at L7222 IS the surplus, but it
                # was discarded by the position-vs-target frame.
                #
                # v3.23.7 mechanic: surplus = accum_profit (computed at
                # L7231 as extra_asset × buy_fill) × quote_to_usd. This is
                # strictly >= 0 because the eligibility filter requires
                # buy_fill < tranche.ref for every eligible tranche.
                #
                # This is attempt 7 at the target-growth-fires-on-fold
                # arc; the prior 6 (MEM-004, MEM-053, MEM-246, v3.15.49
                # BB-arm, v3.16.46 position frame, v3.16.50 standing
                # pool, v3.16.56 per-fold drain, MEM-408 cap-subtract)
                # each addressed a different gate but never converged on
                # the surplus-source itself. The behavioural pin
                # `test_target_grows_on_fold_when_position_below_target`
                # in tests/test_v3_23_7_surplus_realignment.py is the
                # falsifier the prior pins never had — it tests runtime
                # growth, not code text.
                _new_surplus_usd = max(0.0, accum_profit * float(self._quote_to_usd or 1.0))

                _cap_pct_growth = float(getattr(
                    self.config, "max_target_growth_pct", 1.0))
                _cycle_cap_growth = (
                    self._anchor_target_balance * (_cap_pct_growth / 100.0)
                )

                # v3.23.7 P0-DIAG — accum_profit-sourced surplus frame.
                # Replaces v3.16.50 position-vs-target log.
                try:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(
                            f"FOLD_DIAG_SURPLUS_CHECK: "
                            f"buy_fill=${buy_fill:.8f}, "
                            f"holdings={self._current_holdings:.6f}, "
                            f"accum_profit=${float(accum_profit):.6f}, "
                            f"target=${self._target_balance:.4f}, "
                            f"new_surplus=${_new_surplus_usd:+.4f}, "
                            f"standing_surplus_in=${self._standing_surplus_usd:.4f}, "
                            f"cycle_budget=${_cycle_cap_growth:.4f} "
                            f"({_cap_pct_growth}% of anchor "
                            f"${self._anchor_target_balance:.4f}), "
                            f"profit_folding_active="
                            f"{self.config.profit_folding_active}."))
                except Exception as _sup:  # R28-OK: diagnostic-only
                    logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

                # v3.23.30 — drain block extracted into
                # _apply_fold_target_growth() so MANUAL_FOLD +
                # CARTRIDGE_FOLD paths can share the same logic
                # (Option B per operator directive 2026-07-26).
                # Helper handles: profit_folding_active gate, surplus
                # threshold, cap-remaining bound, standing-pool
                # accrual, D2-b side tag, log emission, stats mirror.
                _growth_applied = self._apply_fold_target_growth(
                    accum_profit, source="auto")

                # P1b Session 26 (2026-04-24) — source-side Smart Wire
                # routing. After fold profit is realised, if any wires
                # originate from THIS bot, route pct% of accum_profit
                # to each target bot's apply_wire_income. This is the
                # active cross-compounding that the GUI drag sets up
                # and the trading-layer honours.
                #
                # Operator spec: the wire IS the connection between
                # source profit and target fold_queue. Previously a
                # drag just stored pct/target in the GUI list; the
                # engine never consulted it. Now it does.
                # v3.16.46 — Smart Wire fold-back-time route now triggers
                # on _growth_applied (the actual realized compound growth
                # amount that just lifted target_balance), NOT on the
                # synthetic accum_profit. The dominant wire flow is
                # SCRUM-time on proceeds (line ~4787 area). This is
                # the SECONDARY orthogonal flow: when fold-back actually
                # produces compound surplus that grew target, route a
                # share to wired bots too. Aligns with the new
                # position-vs-target compound mental model.
                try:
                    mgr = self._smart_wire_mgr
                    if (mgr is not None and _growth_applied > 0
                            and hasattr(mgr, "distribute_fold_profit")):
                        # v3.23.66 — [WIRE FIRE] diagnostic mirrored
                        # from the scrum-route entry so the operator
                        # can grep for BOTH routes uniformly.
                        try:
                            self._bus.emit(
                                "bot.log", bot_id=self.bot_id,
                                message=(
                                    f"[WIRE FIRE] fold-compound: "
                                    f"${_growth_applied:.4f} → "
                                    f"distribute_fold_profit "
                                    f"(from realized compound growth "
                                    f"@{buy_fill:.8f})"))
                        except Exception as _sup:  # noqa: BLE001 - log best-effort
                            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
                        mgr.distribute_fold_profit(
                            source_id=self.bot_id,
                            profit_usd=float(_growth_applied),
                            ref=f"fold-compound@{buy_fill:.8f}")
                except Exception as _wr_exc:
                    # Wire routing failure MUST NOT break the fold path.
                    # Log and continue — fold still succeeded locally.
                    logger.warning(
                        "Bot %s Smart Wire compound-route raised: %s "
                        "(fold profit still booked locally)",
                        self.bot_id, _wr_exc)

                # v3.13.8 MEM-187 / Chunk 3 — hedge replenishment.
                # v3.16.46 — replenish on _growth_applied (actual realized
                # compound growth) instead of synthetic accum_profit.
                # 8% of compound growth recycles into the hedge reserve,
                # up to the initial reserve size. Only replenishes if
                # hedge rebalancing is active (disabled →
                # _hedge_balance_initial == 0 → no-op).
                if (self.config.hedge_rebalance_active
                        and self._hedge_balance_initial > 0
                        and self._hedge_bal < self._hedge_balance_initial
                        and _growth_applied > 0):
                    _prev = self._hedge_bal
                    self._hedge_bal = min(
                        self._hedge_balance_initial,
                        self._hedge_bal + _growth_applied * 0.08)
                    _added = self._hedge_bal - _prev
                    if _added > 1e-9:
                        self._bus.emit("bot.log", bot_id=self.bot_id,
                            message=f"HEDGE REPLENISH: +${_added:.4f} from compound growth "
                                    f"→ reserve now ${self._hedge_bal:.2f} "
                                    f"(cap ${self._hedge_balance_initial:.2f})")

                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"FOLD: Bought ${buy_cost:.4f} @ ${buy_fill:.8f} "
                            f"(intended ${ticker.last:.8f}, "
                            f"{pct_cheaper:.1f}% below min tranche ref ${_intended_min_ref:.8f}). "
                            f"Accumulated +{extra_asset:.6f} extra asset. "
                            f"Profit: ${accum_profit:.4f}. "
                            # 2026-08-12 — was
                            # `len(self._fold_tranches) + len(_eligible)`,
                            # which read as the queue size before the
                            # dequeue only while every admitted tranche
                            # was removed whole. A part-consumed tranche
                            # now stays in `_fold_tranches` AND counts
                            # in `_eligible`, so that sum counted it
                            # twice and over-stated the queue.
                            f"Rebought {_n_spent} tranche(s) whole and "
                            f"part-consumed {_partial_count}, out of "
                            f"{_pre_remove} queued "
                            # v3.24.46 (Phase 1 Step 1) — this blamed the
                            # "MEM-171 initial_buy_price floor". The
                            # executor's filter is
                            # `ticker.last <= ref * _otd_factor` and
                            # contains NO initial_buy_price term at all,
                            # so that gate does not participate. Naming a
                            # gate that does not run is why the real
                            # blockers went unexamined for so long.
                            f"(others held by the OTD price gate: needs "
                            f"price <= ref x {_otd_factor:.4f}"
                            + (f"; {_excluded} more were price-eligible "
                               f"but skipped by the per-cycle cap"
                               if _excluded else "") + ")")
                # v3.16.46 — emit profit as _growth_applied (actual
                # realized compound growth that lifted target_balance),
                # not the synthetic accum_profit. Sound engine,
                # spool log, and audit trail consume this value;
                # _growth_applied accurately represents the realized
                # event the operator cares about.
                self._bus.emit("trade.filled", bot_id=self.bot_id,
                    side="buy", type="FOLD", price=buy_fill,
                    amount=(buy_cost / buy_fill) if buy_fill else 0.0,
                    size=buy_cost, profit=_growth_applied)
                # v3.23.11 — voting.log + gate.log snapshots at fire (D-NEW-A).
                self._emit_voting_panel_snapshot_at_fire(
                    side="BUY", trade_action="FOLD")
                self._emit_gate_decision_at_fire(
                    side="BUY", trade_action="FOLD")
                # v3.16.59 — PnL event for FOLD (token-denominated gain).
                # Operator directive 2026-05-14: "FOLD is profitable in
                # terms of additional acquired tokens." Captures:
                # extra_asset (the surplus units acquired by rebuying
                # at a lower price than the tranches' sell ref) and
                # % gain in tokens vs the units originally sold.
                try:
                    _pct_token_gain = 0.0
                    if asset_at_scrum > 1e-12:
                        _pct_token_gain = (
                            extra_asset / asset_at_scrum * 100.0)
                    self._bus.emit("pnl.event", bot_id=self.bot_id, data={
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
                        "usd_spent": float(buy_cost) * float(
                            self._quote_to_usd or 1.0),
                        "growth_applied_usd": float(_growth_applied),
                    })
                except Exception as _sup:  # R28-OK: PnL telemetry best-effort
                    logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
                # v3.15.50 — high-score counter: cumulative fold USD.
                # v3.15.55 — `buy_cost` is in QUOTE currency. Multiply
                # by quote→USD so the platform counter stays in true USD
                # for crypto-quoted pairs.
                self.stats.total_folded_usd += float(buy_cost) * float(self._quote_to_usd or 1.0)
                # v3.23.65 — Fold closes the SWOS cycle. Reset the
                # per-cycle retained counter so the next scrum starts
                # from zero.
                self.reset_swos_cycle()
                # v3.15.52 — record side for opposite-direction hysteresis
                self._last_trade_side = "FOLD"
                # Chunk 4 + 6 — update band-travel baseline with actual fill
                self._last_trade_price = buy_fill
                # v3.15.77 — disarm both gates so the next tick re-arms
                # if/when delta drifts opposing.
                self._reset_opposing_hysteresis_after_fill()

                # MEM-235 — DIST queue increment. Operator-observed bug
                # (Session 24 log 15:59:06 onward): bot repeatedly
                # attempted to sell ~66M BONK via DIST path, hitting
                # Coinbase INSUFFICIENT_FUND each time (4+ retries over
                # 15min).
                #
                # Root cause (two-part, diagnosed by cold-read R68 audit):
                #
                #   (1) Old line `new_holdings = self._current_holdings
                #       + buy_asset` DOUBLE-COUNTED the fold buy.
                #       _execute_buy() already does `self._current_holdings
                #       += amount` internally at the success path (~line
                #       2185) BEFORE returning. So buy_asset was added
                #       twice — once inside _execute_buy and once here.
                #
                #   (2) More fundamentally, the ENTIRE value above target
                #       was being treated as distributable "excess". In the
                #       Scrum→Fold→Distribute cycle, only the asset gained
                #       by buying cheaper than we sold (extra_asset,
                #       computed at ~line 1464) is actually distributable.
                #       The rest of the fold-back is just restoring what
                #       the scrum sold out — distributing it would unwind
                #       the scrum that just happened.
                #
                # At fold #1 in the operator log:
                #   holdings after buy: 67,186,113 (correct)
                #   OLD formula: 67.19M + 33.13M = 100.3M; × price - target
                #                = ~$425 excess; / price = ~66M BONK queued.
                #   NEW formula: extra_asset = +120,110 BONK (matches the
                #                logged "Accumulated +120110.121372 extra
                #                asset" line exactly).
                #
                # 551× reduction. Bot holds 67M, so 120K is easily sellable.
                # No more INSUFFICIENT_FUND retries.
                #
                # Defensive `if extra_asset > 0`: MEM-171 gating makes
                # extra_asset non-positive impossible in practice (fold
                # only fires below scrum ref), but guard against edge
                # cases (rounding, exchange oddities).
                if extra_asset > 0:
                    self._dist_accumulator += extra_asset

            else:
                # Tranches exist and TA is BEARISH, but zero tranches cleared
                # both MEM-171 gates (price < tranche.ref AND
                # price <= tranche.initial_buy_price). Log which floor is binding.
                _min_ref = min(t["ref"] for t in self._fold_tranches)
                _min_ibp = min(t.get("initial_buy_price", t["ref"])
                               for t in self._fold_tranches)
                _binding = ("initial_buy_price floor" if ticker.last > _min_ibp
                            else "scrum ref gate")
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"HOLD FOLD: BEARISH but {len(self._fold_tranches)} "
                            f"tranche(s) all gated — price ${ticker.last:.8f} "
                            f"above the binding gate ({_binding}; "
                            f"min_ref=${_min_ref:.8f}, min_ibp=${_min_ibp:.8f})")

        elif self._fold_tranches and not is_bearish:
            # v3.24.43 — this printed `eff_direction` rather than the
            # conjunct that actually failed, so when the direction WAS
            # bearish and only the confidence floor blocked it, the line
            # read "TA=BEARISH — waiting for BEARISH": waiting for the
            # condition it reports as already met. Measured 1,377 times
            # in a 27-minute window on the live fleet. Same family as
            # C51 and NF-5 — confidently wrong rather than silent, which
            # is why this gate went unsuspected. Diagnostic only; the
            # gate itself is unchanged.
            _dir_ok = eff_direction in (
                SignalDirection.BEARISH, SignalDirection.NEUTRAL)
            if not _dir_ok:
                _why = (f"TA={eff_direction.name} is not BEARISH or "
                        f"NEUTRAL")
            elif eff_confidence < _TA_CONFIDENCE_FLOOR:
                _why = (f"TA={eff_direction.name} but confidence "
                        f"{eff_confidence:.2f} < {_TA_CONFIDENCE_FLOOR:.2f} "
                        f"floor")
            else:
                # Neither conjunct explains it — a landing-strip override
                # or a later mutation did. Say so rather than guess.
                _why = (f"TA={eff_direction.name}, confidence "
                        f"{eff_confidence:.2f} — blocked by an override, "
                        f"not by direction or confidence")
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"HOLD FOLD: {len(self._fold_tranches)} tranche(s) "
                        f"(${self._fold_queue_usd:.4f}) queued — {_why}")

        elif self._fold_tranches and is_bearish and not fold_ok_midline:
            # Chunk 2 — bb_midline_gate gating the fold side. Price is above
            # midline so the gate says "not yet — wait for price to drop
            # below midline before considering any fold rebuy."
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"HOLD FOLD: BEARISH and {len(self._fold_tranches)} "
                        f"tranche(s) queued but BB position {bb_pos:.0%} > 50% "
                        f"(bb_midline_gate blocking fold — wait for price "
                        f"to drop below midline)")

        # v3.15.57 — Lower BB Detection Threshold hard gate (operator
        # directive 2026-04-25). Surface explicitly when this gate is
        # the SOLE blocker. Conditions: would-have-folded (tranches
        # queued, bearish TA, midline gate cleared, ceiling clear) but
        # bb_pos is above the lower detect threshold → refuse.
        elif (self._fold_tranches and is_bearish and fold_ok_midline
              and not _mem253_at_ceiling and not _bb_below_lower_dt
              and not _cb_blocks_fold):
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(
                    f"FOLD REFUSED (Lower BB Detection Threshold): "
                    f"bb_pos={bb_pos:.3f} > lower_detect={_bb_lower_dt:.3f} "
                    f"(scrum_detect_pct={self.config.scrum_detect_pct}%). "
                    f"Operator rule: FOLD cannot occur above the Lower "
                    f"BB Detection Threshold. All other gates passed."))
            self._emit_trade_notification(
                "FOLD", "CANCELLED",
                f"bb_pos {bb_pos:.3f} > lower detect {_bb_lower_dt:.3f}")

        # v3.15.58 — Soft Circuit Breaker on FOLD side blocks. Surface
        # explicitly when this is the SOLE blocker.
        elif (self._fold_tranches and is_bearish and fold_ok_midline
              and not _mem253_at_ceiling and _bb_below_lower_dt
              and _cb_blocks_fold):
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(
                    f"FOLD BLOCKED by SOFT CIRCUIT BREAKER: trip @ "
                    f"{self._cb_soft_trip_pct:.2f}% "
                    f"(threshold {self.config.circuit_breaker_soft_pct:.2f}%); "
                    f"{self._cb_soft_cooldown_remaining} candle(s) of cooldown "
                    f"remaining before FOLD side re-opens."))

        # v3.15.61 — Higher-TF phantom bias contradicts FOLD intent.
        elif (self._fold_tranches and is_bearish and fold_ok_midline
              and not _mem253_at_ceiling and _bb_below_lower_dt
              and not _cb_blocks_fold and _htf_blocks_fold):
            _bull_w = _htf_bias_detail.get("bull_weight", 0.0)
            _bear_w = _htf_bias_detail.get("bear_weight", 0.0)
            _contribs = _htf_bias_detail.get("contributors", [])
            _summary = ", ".join(
                f"{c.get('tf', '?')}={c.get('direction', '?')}"
                f"@{c.get('conf', 0):.2f}"
                for c in _contribs if not c.get('skipped')
            ) or "no usable phantoms"
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(
                    f"FOLD REFUSED (Higher-TF Bias gate): higher-TF "
                    f"phantom consensus is BEARISH "
                    f"(bear weight {_bear_w:.2f} > bull {_bull_w:.2f}). "
                    f"Buying here would catch a falling knife. "
                    f"Contributors: {_summary}."))
            self._emit_trade_notification(
                "FOLD", "CANCELLED",
                f"higher-TF BEARISH bias ({_bear_w:.2f} vs {_bull_w:.2f})")

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
        # Ported from RAIntSimBat.py:2144-2159. Gap threshold: >= 1% of
        # target. Hedge buys append a new lot to _main_lots at current
        # fill price (MEM-171 compliance — the hedge buy's cost basis
        # becomes its future fold floor).
        #
        # Not gated by phantom lock or bb_midline_gate — hedge is downside
        # protection and must work in bearish regimes by design.
        if (self.config.hedge_rebalance_active
                and self._hedge_bal > 0.01
                and delta < 0
                and not is_bullish
                and bb_pos < 0.40):
            _gap = abs(delta)
            if _gap / max(self._target_balance, 1e-9) >= 0.01:
                _use = min(self._hedge_bal * 0.5, _gap)
                if _use > 0.01:
                    # v3.13.8 MEM-190 / Chunk 6 — capture actual fill.
                    # Hedge buys feed _main_lots with the cost basis — using
                    # the intended price here would understate the basis if
                    # fill came in higher, silently weakening the MEM-171
                    # floor for future scrums that consume these units.
                    hedge_fill = await self._execute_buy(
                        _use, ticker.last, summary,
                        trace_context={
                            "path": "hedge_replenish",
                            "hedge_bal": f"${self._hedge_bal:.4f}",
                            "gap": f"${_gap:.4f}",
                            "use": f"${_use:.4f}",
                        })
                    # MEM-207 — None means hedge buy failed. The worst
                    # offender from operator's 2026-04-22 incident log:
                    # 18 consecutive phantom hedge credits drained the
                    # reserve $200 → $14 while every buy was rejected by
                    # the exchange (INSUFFICIENT_FUND or internal
                    # OrderType error). On failure, make ZERO state
                    # changes: no phantom lot in _main_lots, no hedge
                    # reserve debit, no trade counter bump, no HEDGE
                    # REBALANCE log (which previously lied about
                    # success), no band-travel baseline update. Emit
                    # explicit HEDGE ABORTED so operator sees what
                    # happened. DISTRIBUTE block below is independent
                    # of this — structured if/else so we fall through.
                    if hedge_fill is None or hedge_fill <= 0:
                        self._bus.emit("bot.log", bot_id=self.bot_id,
                            message=(f"HEDGE ABORTED: buy failed at "
                                    f"${ticker.last:.8f} (gap=${_gap:.4f}, "
                                    f"reserve=${self._hedge_bal:.2f} "
                                    f"unchanged). No state update. "
                                    f"Retry next tick if gates still pass."))
                    else:
                        # --- Success path: hedge fill valid ---
                        _hedge_asset = _use / hedge_fill
                        # MEM-171 integration: hedge-bought units enter main_lots
                        # at ACTUAL fill price so future scrums correctly compute
                        # the HIGHEST-PRICE-FIRST fold floor.
                        self._main_lots.append({
                            "units": _hedge_asset,
                            "initial_buy_price": hedge_fill,
                        })
                        self._hedge_bal -= _use
                        self._hedge_trades += 1
                        self.stats.trade_volume += _use
                        self._bus.emit("bot.log", bot_id=self.bot_id,
                            message=f"HEDGE REBALANCE: spent ${_use:.4f} "
                                    f"(reserve ${self._hedge_bal:.2f} remaining) "
                                    f"→ bought {_hedge_asset:.6f} @ ${hedge_fill:.8f} "
                                    f"(intended ${ticker.last:.8f}), "
                                    f"gap=${_gap:.4f} ({_gap/max(self._target_balance, 1e-9)*100:.1f}%), "
                                    f"bb={bb_pos:.0%}. Trade #{self._hedge_trades}")
                        # v3.24.30 — `amount` + `usd` added.
                        #
                        # This site emitted only `size=_use`, and `_use`
                        # is USD SPENT, not base units. LogManager's
                        # handler reads `merged.get("amount", 0)`, so
                        # every HEDGE rebalance was written to the live
                        # trade.log with amount=0.0 — the fill quantity
                        # was simply absent from the trade record.
                        #
                        # Found by the v3.24.30 emit-contract observer,
                        # which flagged `trade.filled` payloads missing
                        # the required `amount` field. `size` is kept so
                        # any existing reader of it keeps working.
                        self._bus.emit("trade.filled", bot_id=self.bot_id,
                            side="buy", type="HEDGE", price=hedge_fill,
                            amount=_hedge_asset, usd=_use,
                            size=_use, profit=0)
                        # v3.23.11 — voting.log + gate.log snapshots at fire (D-NEW-A).
                        self._emit_voting_panel_snapshot_at_fire(
                            side="BUY", trade_action="HEDGE")
                        self._emit_gate_decision_at_fire(
                            side="BUY", trade_action="HEDGE")
                        # Chunk 4 + 6 — update band-travel baseline with actual fill
                        self._last_trade_price = hedge_fill

        # === DISTRIBUTE: sell excess accumulated asset on BULLISH ===
        if self._dist_accumulator > 0 and is_bullish:
            dist_asset = self._dist_accumulator
            try:
                bal = await self._get_balance(
                    self.config.symbol.split("/")[0])
                dist_asset = min(dist_asset, bal)
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
            if dist_asset > 0:
                # v3.13.8 MEM-190 / Chunk 6 — capture actual fill.
                # DIST is the sell that feeds re-fold tranches; using
                # intended price here would make subsequent fold's
                # 'price < tranche.ref' gate looser than the actual
                # sell justifies — silent loss of protection.
                dist_fill = await self._execute_sell(dist_asset, ticker.last, summary)
                # MEM-207 — None means DIST sell failed. Must NOT:
                # (1) reset self._dist_accumulator — proceeds weren't
                #     distributed; accumulator should stay intact so the
                #     next tick can retry;
                # (2) emit phantom DIST log;
                # (3) create phantom re-fold tranches from a sell that
                #     didn't happen. Use if/else so post-block updates
                #     (self._last_price = ticker.last) stay reachable.
                if dist_fill is None or dist_fill <= 0:
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"DIST ABORTED: sell failed for "
                                f"{dist_asset:.6f} excess @ ${ticker.last:.8f}. "
                                f"Accumulator kept; no re-fold tranches "
                                f"created. Retry next tick."))
                else:
                    # --- Success path: dist_fill is a valid fill price ---
                    dist_usd = dist_asset * dist_fill  # recompute from actual fill
                    self.stats.trade_volume += dist_usd

                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=f"DIST: Sold {dist_asset:.6f} excess @ ${dist_fill:.8f} "
                                f"(intended ${ticker.last:.8f}) = ${dist_usd:.4f}")
                    self._bus.emit("trade.filled", bot_id=self.bot_id,
                        side="sell", type="DIST", price=dist_fill,
                        amount=dist_asset, size=dist_usd,
                        profit=dist_usd * 0.02)
                    # v3.23.11 — voting.log + gate.log snapshots at fire (D-NEW-A).
                    self._emit_voting_panel_snapshot_at_fire(
                        side="SELL", trade_action="DIST")
                    self._emit_gate_decision_at_fire(
                        side="SELL", trade_action="DIST")
                    # Chunk 4 + 6 — update band-travel baseline with actual fill
                    self._last_trade_price = dist_fill

                    self._dist_accumulator = 0.0

                    # Re-fold distribution proceeds (compounding cycle)
                    # v3.13.8 MEM-069 + MEM-171 port — DIST sell also consumes
                    # _main_lots HIGHEST-PRICE-FIRST and creates a tranche so the
                    # MEM-171 initial_buy_price floor applies to re-fold cycles too.
                    # Without this, DIST proceeds would rebuild the queue using
                    # the old single-scalar pattern and bypass profit protection.
                    if self.config.profit_folding_active:
                        self._main_lots.sort(key=lambda l: l["initial_buy_price"], reverse=True)
                        # 2026-08-12 — recorded for the top-up call
                        # below, which needs to know where THIS sell's
                        # tranches start. A DIST sell is an opposing
                        # trade and spawns fold tranches exactly as a
                        # SCRUM does, so leaving it out would let
                        # remnants multiply on this path alone.
                        _dist_tranche_count_before = len(self._fold_tranches)
                        _units_remaining = dist_asset
                        for _lot in list(self._main_lots):
                            if _units_remaining <= 1e-12:
                                break
                            _take = min(_lot["units"], _units_remaining)
                            if _take <= 1e-12:
                                continue
                            _t_usd = (_take / dist_asset) * dist_usd
                            self._fold_tranches.append({
                                "usd": _t_usd,
                                "units": _take,
                                "ref": dist_fill,
                                "initial_buy_price": _lot["initial_buy_price"],
                                "created_ts": time.time(),  # v3.16.39 P2-VIS
                            })
                            self._tranches_created_lifetime += 1  # v3.16.39 P2-VIS
                            _lot["units"] -= _take
                            _units_remaining -= _take
                            if _lot["units"] <= 1e-12:
                                self._main_lots.remove(_lot)
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
                            _dist_tranche_count_before,
                            dist_usd, dist_asset)
                        # 2026-08-12 — same top-up as the SCRUM path.
                        self._top_up_remnant_fold_tranches(
                            _dist_tranche_count_before,
                            float(getattr(bb_result, "lower", 0.0) or 0.0),
                            float(getattr(bb_result, "upper", 0.0) or 0.0))
                        # Refresh legacy derived scalars
                        self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)
                        self._fold_queue_ref_price = dist_fill
                        self._bus.emit("bot.log", bot_id=self.bot_id,
                            message=f"DIST proceeds ${dist_usd:.4f} queued for re-fold "
                                    f"(tranche-provenance preserved, fill=${dist_fill:.8f})")

        self._last_price = ticker.last

    # ------------------------------------------------------------------
    # 2026-08-12 — ONE MEANING FOR scrum_fold_pct, ON EVERY SELL PATH
    # ------------------------------------------------------------------
    def _apply_scrum_fold_pct(
            self,
            _tranche_count_before: int,
            scrum_usd: float,
            scrum_asset: float) -> None:
        """Scale the tranches THIS sell just appended by scrum_fold_pct.

        WHY THIS IS A METHOD AND NOT THREE COPIES. Operator directive
        2026-08-12: "Functionality should be mirrored between either
        side of the ladder." This arithmetic used to live inline in
        ``tick``, and it ran on exactly one of the three sites that
        build a fold tranche -- the autonomous SCRUM. The DIST sell and
        ``_execute_manual_rebalance`` appended tranches with no scaling,
        so one operator setting meant one thing on one path and nothing
        on two others. Three copies would be three things to keep in
        step; one method called from all three makes them mirror by
        construction rather than by inspection.

        WHAT WAS MEASURED BEFORE THE CHANGE. Over the operator's filled
        sells from 2026-06-09 to 2026-08-13, 276 of 380 (72.6%) ran an
        unscaled path. On the eight bots that set the value below 100,
        95.6% of sell dollars bypassed it, so a setting of 50% governed
        about 4% of the money it names.

        WHAT IT SCALES: each new tranche's ``usd``, but only the part
        that came from THIS sale, and ``units`` in full.
        WHAT IT LEAVES ALONE: ``ref``, ``initial_buy_price``,
        ``created_ts``, ``operator_initiated``, and every tranche older
        than this sale.
        WHEN IT DOES NOTHING: ``scrum_fold_pct == 100``, the default,
        and 29 of the operator's 37 bots.

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
        _fold_pct = max(0, min(100, int(getattr(
            self.config, "scrum_fold_pct", 100))))
        _new_tranches = self._fold_tranches[_tranche_count_before:]
        if _fold_pct < 100 and _new_tranches:
            _fold_frac = _fold_pct / 100.0
            # 2026-08-11 — ABSORBED WIRE CREDIT IS EXEMPT.
            #
            # `_absorb_pending_wire_credits_into` runs a few lines
            # above and adds the WHOLE parked pool to the first
            # new tranche's `usd`. That money was earned by
            # another bot, routed by a Smart Wire, and merely
            # PARKED here because this bot had no tranche to
            # receive it. `scrum_fold_pct` decides how much of
            # THIS scrum's OWN proceeds fold back and has no
            # authority over it, but the loop below used to scale
            # the SUMMED `usd` and so retired
            # `pending x (1 - _fold_frac)` of wired-in money as
            # cash. Measured against the operator's live state
            # (read-only copy, saved 2026-08-11 20:33): bot
            # 7c39c7a2 holds $343.68 parked at scrum_fold_pct=50,
            # so its next autonomous scrum moved $171.84 out of
            # the fold queue.
            #
            # HOW THE TWO ARE TOLD APART: BY UNITS.
            #
            # Every tranche here was built moments ago at
            # `_t_usd = (_take / scrum_asset) * scrum_usd`, so a
            # tranche's scrummed dollars are exactly its units
            # priced at this scrum's own net rate. The absorb
            # adds USD and NO units. So whatever a tranche holds
            # ABOVE its units at that rate was wired in, and the
            # split is exact rather than inferred from a flag.
            #
            # WHY NOT READ THE `wire_credits` PROVENANCE, which
            # is the obvious answer: the record is lossy, and
            # measurably so. `pending_wire_ledger` was not
            # persisted before v3.24.49 (see the note at the
            # export site), so every restart before that fix kept
            # the parked TOTAL and dropped its itemisation.
            # Measured on the same live copy: 7c39c7a2 carries
            # $343.68 parked against a ledger summing $1.43, and
            # 5d335c96 $13.34 against $1.56. Exempting the
            # recorded amount would have rescued $0.71 of
            # 7c39c7a2's $171.84 and left the rest to be retired
            # — a fix that reads correct and does nothing.
            #
            # THE RATE IS THE SALE, NOT THE TICKER. `scrum_usd`
            # is already net of `_scrum_routed_total`, and the
            # build loop divided that same net figure, so the two
            # agree by construction. Reading a price from
            # anywhere else would not.
            _rate_known = scrum_asset > 0
            _unit_rate = (scrum_usd / scrum_asset) if _rate_known else 0.0
            _skim_usd = 0.0
            _skim_cost_basis = 0.0
            _queued_usd = 0.0
            for _t in _new_tranches:
                _full_usd = _t["usd"]
                _full_units = _t["units"]
                # With no usable rate, treat everything as scrum
                # proceeds. That is the pre-2026-08-11 behaviour:
                # the fallback declines to invent an exemption
                # rather than guessing one. The clamp bounds the
                # rate-known case to the dollars actually in the
                # tranche, so a rounding excess cannot drive
                # `_wire_usd` negative and shrink the queue.
                _scrummed_usd = (
                    min(max(_full_units * _unit_rate, 0.0), _full_usd)
                    if _rate_known else _full_usd)
                _wire_usd = _full_usd - _scrummed_usd
                _t["usd"] = _wire_usd + _scrummed_usd * _fold_frac
                # Units are NOT adjusted for the absorb: it adds
                # USD and no units, so every unit in this tranche
                # came from the scrum and every unit is scaled.
                _t["units"] = _full_units * _fold_frac
                _skim_units = _full_units * (1 - _fold_frac)
                _skim_proceeds = _scrummed_usd * (1 - _fold_frac)
                _skim_usd += _skim_proceeds
                _skim_cost_basis += _skim_units * _t["initial_buy_price"]
                _queued_usd += _t["usd"]
            _skim_profit = _skim_usd - _skim_cost_basis
            # v3.23.7 R-CLN (Anomaly B): the SCRUM-skim internal-
            # P/L write site (the `stats` accumulator increment
            # by `_skim_profit`) was removed. Operator directive
            # 2026-06-13: "Prefer to just pull from the exchange.
            # It is the true indicator of position health." The
            # exchange-pulled FIFO-matched `realized_pnl_exchange`
            # is the sole P/L surface displayed in the Status tab
            # and the phantom-bot table; the internal accumulator
            # added noise that diverged from exchange truth.
            # `_queued_usd` is summed from the tranches that were
            # actually written, not re-derived as
            # `scrum_usd * _fold_frac`. That re-derivation was a
            # second source of truth and now reports a different
            # number from the queue it claims to describe: it
            # omits absorbed wire credit, and it already
            # over-stated whenever `_main_lots` held fewer units
            # than `scrum_asset` and the build loop ran out of
            # lots before consuming the sale.
            self._bus.emit(
                "bot.log", bot_id=self.bot_id,
                message=(f"FOLD RATIO: scrum_fold_pct={_fold_pct}% — "
                         f"queued ${_queued_usd:.4f} for "
                         f"fold, retired ${_skim_usd:.4f} as cash "
                         f"(realised profit ${_skim_profit:+.4f}). "
                         f"Cash buffer preserved against further drops."))

    # ------------------------------------------------------------------
    # 2026-08-12 — PARTIAL CONSUMPTION OF A FOLD TRANCHE
    # ------------------------------------------------------------------
    def _plan_fold_consumption(
            self,
            eligible: list,
            cap_remaining: float) -> tuple[list, list, int]:
        """Decide what this fold cycle takes from each tranche.

        Operator spec 2026-08-12: "If the value of a given Fold tranche
        cannot be consumed due to the maximum growth cap it will
        survive the trade and continue to hold its remaining balance."

        WHAT THIS REPLACED. The rule was "admit the tranche only if its
        WHOLE balance fits the room left under the cap", and it carried
        the comment: "NOT partial-split -- that would corrupt the
        initial_buy_price provenance per MEM-171."

        MEM-171's own record says the opposite. Its locked operator
        design choices read "Partial tranche rebuy: PERMITTED (rejected
        whole-tranche-only)", and its algorithm summary reads
        "Fold-back eligibility filter ... Partial execution permitted"
        (docs/harness_archive/ACERVATOR_HOP5.md, Session 22 Addendum 2).
        What MEM-171 DOES require of the field is "re-acquired units
        return to main_lots with ORIGINAL init_buy_price (compounding
        protection)". A split satisfies that: ``initial_buy_price`` is a
        scalar COPIED onto the slice and left untouched on the
        remainder, never divided. Both parts carry the same floor the
        whole carried, and the rebought lot inherits it exactly as it
        does from a whole tranche.

        WHAT THE OLD RULE COST. Measured on the operator's live state
        (read-only pinned copy, saved 2026-08-12 17:08:26): three bots
        deployed $0.00 on a full cap, permanently. ADA held 4 of 4
        tranches over a $0.25 cap, WLFI 1 of 1 over $0.25, BICO 1 of 1
        over $0.50. Sixteen bots in all held at least one over-cap
        tranche, $102.40 of balance between them. A fold is what
        produces surplus, surplus is what grows the target, and growth
        is what raises the cap, so those three could not compound at
        all.

        THE SPLIT. A tranche that does not fit gives up exactly the
        room left under the cap and keeps the rest. Units come off in
        the same proportion as usd, so the two parts sum to the whole
        on both. A tranche that fits is taken whole, as before.

        TWO LISTS, AND WHY. The plan pairs each SOURCE tranche with
        what this cycle takes from it, by identity, and
        ``_settle_fold_plan`` later reads it. The slices are separate
        dicts, because every downstream sum, share and log must see the
        amount being consumed, not the tranche's full balance. That is
        also why the dequeue can no longer be the ``t not in _eligible``
        value-compare it used to be: a slice never compares equal to
        its source.

        THE CAP IS UNCHANGED. This decides only how a tranche meets the
        room already left under the cap. It does not compute the cap,
        widen it, or touch target growth.

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
                # Nothing to take. Left queued and untouched, so the
                # malformed-tranche guard in the caller stays the only
                # thing on this path that drops a record.
                continue
            # The fit test carries the same 1e-9 tolerance the
            # drained-to-nothing test uses, and it must. Three tranches
            # of $0.50, $0.30 and $0.20 against a $1.00 cap leave
            # $0.19999999999999996 of room for the last one in IEEE754,
            # so an exact `<=` called a whole fit a partial, logged a
            # part-consumed tranche that was not one, and left a
            # 4e-17 remnant for the removal step to clean up. A dollar
            # figure is never meaningful below a nanocent.
            if tranche_usd <= room + 1e-9:
                take_usd = tranche_usd
                take_units = tranche_units
            else:
                take_usd = room
                take_units = tranche_units * (take_usd / tranche_usd)
                partial_count += 1
            slices.append({
                "usd": take_usd,
                "units": take_units,
                "ref": float(_t.get("ref", 0) or 0),
                # Read exactly as the _main_lots append in the caller
                # reads it, so a tranche missing the key fails HERE,
                # before an order is placed, instead of after the buy
                # has already filled.
                "initial_buy_price": _t["initial_buy_price"],
                "created_ts": _t.get("created_ts", 0.0),
            })
            plan.append((_t, take_usd, take_units))
            running_usd += take_usd
        return plan, slices, partial_count

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
            src["units"] = max(
                0.0, float(src.get("units", 0) or 0) - took_units)
            if src["usd"] <= 1e-9 or src["units"] <= 1e-12:
                spent.add(id(src))
            else:
                # Marks this record as a REMNANT, which is what lets it
                # receive the next opposing trade's proceeds instead of
                # that trade adding yet another tranche to the list.
                src["fold_partial_spent"] = True
        self._fold_tranches = [t for t in self._fold_tranches
                               if id(t) not in spent]
        return pre_remove - len(self._fold_tranches), len(spent)

    # ------------------------------------------------------------------
    # 2026-08-12 — TOP-UP ON AN OPPOSING TRADE
    # ------------------------------------------------------------------
    def _top_up_remnant_fold_tranches(
            self,
            first_new_index: int,
            bb_lower: float,
            bb_upper: float) -> tuple[int, float]:
        """Move a sell's new tranche money into a part-spent tranche.

        Operator spec 2026-08-12: "A tranche that does not spend all of
        its money just sits there minus what left and gains more if
        another opposing trade occurs before its fully spent."

        WHY THIS EXISTS. Partial consumption on its own leaves a
        remnant behind on every capped fold, and the next sell appends
        a fresh tranche beside it. The list then grows without bound,
        which is the accumulation problem wearing a different hat. This
        collapses the two back together. The two halves ship together
        for that reason.

        WHICH TRANCHE RECEIVES IT. Operator directive 2026-08-12:
        "Lowest priced Fold Tranche within the BB range compounds
        first." So the candidate set is the part-spent tranches whose
        ``ref`` sits inside the current Bollinger range, and the LOWEST
        priced of those wins. ``ref`` is the price ordered on: it is the
        sell fill the fold-back is measured against, and it is the same
        field the fold eligibility gate reads. The range comes in from
        the ``detect_bb_proximity`` result the tick already computed;
        nothing is recomputed here, and no BB-width setting is added,
        because a user who wants a wider range raises the TIMEFRAME.

        NO CANDIDATE IS NOT AN ERROR AND GETS NO FALLBACK. Operator,
        2026-08-12: "It would only mean the absence of tranches and the
        Target Delta must always be getting set back to zero at the
        appropriate thresholds and in accordance standing trade logic."
        So this returns ``(0, 0.0)``, the sell's tranches stay exactly
        where the build loop put them, and every trade decision runs
        unchanged. There is no deferral, no queue and no retry here, and
        this method touches no target, no delta and no gate.

        WHAT MEM-171 FORCES. A top-up merges two lots into one record,
        and ``initial_buy_price`` is the floor MEM-171 exists to hold.
        Averaging two different floors would RAISE the floor on the
        cheaper lot's units, and so permit rebuying them above their
        real initial buy price, which is the one thing MEM-171 forbids.
        So there is no weighting. A tranche may receive a top-up ONLY
        when its ``initial_buy_price`` already equals the incoming
        one's, and the merged record keeps that exact value. The match
        is not rare: the build loop stamps every tranche cut from a lot
        with that lot's basis, and a fold returns rebought units to
        ``_main_lots`` under the same basis, so a remnant and a later
        sell off that lot agree exactly.

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
            # No older record to receive anything. Also the case the
            # wire-credit absorb runs in, so absorbed credit can never
            # be moved by this method.
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
            # Both sides are coerced to a float PRICE before the
            # compare. Exact equality is deliberate and it is safe:
            # every basis is copied unchanged from a `_main_lots`
            # entry, so two tranches cut from one lot hold the identical
            # float. A tolerance would be the wrong instrument. It would
            # merge two genuinely different floors that happen to sit
            # close together, which is the averaging MEM-171 forbids.
            _new_ibp = float(_new_t.get("initial_buy_price", 0.0) or 0.0)
            _best = None
            _best_ref = 0.0
            for _cand in _candidates:
                if not _cand.get("fold_partial_spent"):
                    continue
                if float(_cand.get("usd", 0) or 0) <= 0.0:
                    continue
                if float(_cand.get(
                        "initial_buy_price", 0.0) or 0.0) != _new_ibp:
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
            # initial_buy_price is deliberately untouched. It had to be
            # equal for this merge to happen at all.
            _merged_away.add(id(_new_t))
            _merged_n += 1
            _merged_usd += _new_usd
        if not _merged_away:
            return 0, 0.0
        self._fold_tranches = [t for t in self._fold_tranches
                               if id(t) not in _merged_away]
        # The sell did NOT, in the end, open these records. Leaving the
        # count up would break the created-versus-closed reconciliation
        # the Fold Tranches tab shows as cycle health, and would paint a
        # healthy bot red.
        self._tranches_created_lifetime = max(
            0, int(self._tranches_created_lifetime) - _merged_n)
        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"FOLD TOP-UP: ${_merged_usd:.4f} from this sell "
                     f"went INTO {_merged_n} part-spent tranche(s) "
                     f"instead of opening new ones — same "
                     f"initial_buy_price, lowest ref inside the BB "
                     f"range ${bb_lower:.8f}..${bb_upper:.8f}. "
                     f"{len(self._fold_tranches)} tranche(s) open."))
        return _merged_n, _merged_usd

    # ------------------------------------------------------------------
    # U2 (2026-08-13) — the units a reconcile is allowed to act on.
    # ------------------------------------------------------------------
    # `_reconcile_holdings` multiplies every lot in the book by a ratio
    # built from three numbers: the holdings scalar, the lot book's own
    # sum, and the venue reading. A value that is not a real quantity
    # does not make that correction wrong by a little. It ends the
    # book. Measured 2026-08-13 by driving the shipped method:
    #
    #   lots [30.0, nan], scalar 48.73, venue 40.0
    #     -> ratio 0.8208; nan * 0.8208 is nan; the `> 1e-12` filter
    #        below reads nan as False and DROPS that lot. Two lots in,
    #        one lot out, book 24.625487 standing against a scalar of
    #        40.0, and the dropped lot's initial_buy_price gone with
    #        it. Same shape for a -inf lot. A +inf lot survives the
    #        filter and the book stays inf forever.
    #   a lot with no "units" key, same inputs
    #     -> KeyError out of the method, AFTER "Resetting internal
    #        state to exchange reality" has already reached the
    #        operator's log, with lot 1 rescaled and lot 2 not. The
    #        line the operator reads is then a statement about work
    #        that did not happen.
    #
    # `json.loads` accepts `NaN`, `Infinity` and a 400-digit integer
    # literal, so a hand-edited or half-written state file reaches
    # every one of those rows.
    #
    # WHY A GUARD AND NOT A max(). `max(48.73, float("nan"))` is 48.73
    # and `max(float("nan"), 48.73)` is nan. Every comparison against
    # nan is False, so max() keeps whichever operand it saw first and
    # the ARGUMENT ORDER silently decides whether the nan survives. A
    # finiteness test has to run BEFORE any comparison, never as part
    # of one.
    # ------------------------------------------------------------------
    @staticmethod
    def _reconcilable_units(
            value: Any, label: str) -> tuple[float | None, str | None]:
        """One units reading as a finite, NON-NEGATIVE float, or a reason.

        Returns (number, None) when usable, (None, reason) when
        refused, the same shape as `_positive_observed_quantity`
        (:2474), `_finite_state_number` (:2536) and `_sum_lot_units`
        (:2581). Returning the refusal instead of raising is what lets
        `_reconcile_holdings` decline the whole audit before it writes
        anything.

        A FOURTH CONTRACT, AND THE DIFFERENCE IS THE POINT.
        `_positive_observed_quantity` demands strictly positive, which
        refuses a bot holding nothing — an ordinary state here.
        `_finite_state_number` allows any finite number, which accepts
        NEGATIVE units; every consumer of this reading is a quantity
        of coins or a divisor, and neither has a meaning below zero.
        The TYPE ground is shared with both of them, and it is not
        inherited politeness. `bool` subclasses `int` and `float(True)`
        is 1.0, so a flag would clear every numeric test below and be
        multiplied into a real position. A string is refused on the
        same ground: `float("12.5")` parses without complaint, but the
        drift-down branch writes the COERCED value back into the book,
        so accepting a string would let an audit silently retype
        persisted state under cover of a rescale. A units field that
        only `float()` can read is already broken state, and the
        audit's job is to refuse it out loud rather than repair it in
        passing.

        The restore paths coerce the same field more loosely, with
        `float(lot.get("units", 0) or 0)` (:5671, :6610). That
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
        # EXACT type, not isinstance. isinstance admits bool (an int
        # subclass) and any user subclass of int or float, so the set
        # of accepted inputs was open. An exact test closes it to two.
        if type(value) is not int and type(value) is not float:
            return None, (f"{label} must be exactly an int or a float, "
                          f"not a {type(value).__name__}; got {value!r}")
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None, f"{label} is not a number; got {value!r}"
        if not math.isfinite(number):
            return None, f"{label} must be finite; got {number!r}"
        if number < 0.0:
            return None, f"{label} must be >= 0; got {number!r}"
        return number + 0.0, None

    def _reconcilable_lot_book(self) -> tuple[list[float] | None,
                                              str | None]:
        """Every lot's units, coerced, in book order — or a reason.

        The per-lot values are returned rather than only their total
        because the drift-down branch multiplies them one by one.
        Deriving them a second time down there would let two passes
        disagree about one book.

        NOT `_sum_lot_units` (:2581), and the difference is deliberate
        in both directions. That helper refuses a lot with no "units"
        key; here such a lot counts as ZERO, which is what the restore
        paths' `.get` already does (:5671, :6610). Refusing it instead
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
        54.05340781540922, one ULP apart. `sum` is what :5671 and :6610
        use to derive the scalar, so the audited total comes out
        bit-identical to theirs.
        """
        per_lot: list[float] = []
        for _index, _lot in enumerate(self._main_lots):
            if not isinstance(_lot, dict):
                return None, (f"_main_lots[{_index}] must be a lot dict; "
                              f"got a {type(_lot).__name__}")
            _raw = _lot.get("units", 0.0)
            _units, _why = self._reconcilable_units(
                _raw if _raw else 0.0, f"_main_lots[{_index}]['units']")
            if _units is None:
                return None, _why
            per_lot.append(_units)
        return per_lot, None

    # ------------------------------------------------------------------
    # MEM-208 — Exchange balance reconciliation (state ↔ reality)
    # ------------------------------------------------------------------
    async def _reconcile_holdings(self, reason: str = "periodic") -> bool:
        """Re-fetch asset balance from the exchange and compare it to
        what this bot claims to hold. On drift above tolerance, log
        prominently and reset internal state to exchange reality.

        v3.25.8 (U2) — WHAT THE BOT CLAIMS IS TWO COUNTERS, NOT ONE.
        The comparison used to read `_current_holdings` alone. That
        scalar is the one `bootstrap_exchange_state` clamps against the
        wallet with `min` (:5676), so on a bot whose lot book sits
        above it the audit compared the wallet against the wallet and
        reported alignment while the excess stranded in `_main_lots`.
        The audited figure is now `max(scalar, sum of the lot book)` —
        see the block below for the measurement that motivated it.

        v3.25.8 (U2) — THE VENUE NUMBER IS `total`, NOT `free`. The
        read was `balance.free`, which excludes any coin committed to a
        resting order. The startup handshake reads `total` (:6347,
        MEM-255). One wallet, two readers, two different fields — see
        the block at the fetch for why that only becomes load-bearing
        once this audit starts firing.

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

        Tolerance: 0.5% of current_holdings (anything smaller is
        rounding noise). On drift above tolerance, internal state is
        reset to the exchange-reported value. The _main_lots list is
        adjusted proportionally to match the new total — lots' relative
        ratios and initial_buy_price values are preserved; only units
        are rescaled. This keeps MEM-171 cost-basis protection intact
        even when reconciliation reveals a phantom credit from a pre-
        MEM-207 code path, a manual user trade, a replay from exchange
        history, or any other source of divergence.

        Born: MEM-208 (Session 23 Addendum 8, 2026-04-22). Operator
        diagnosis of 2026-04-22 RAVE incident: "bots are blind to
        current_exchange_balances." MEM-207 stops new phantom credits;
        MEM-208 catches any existing drift and prevents future classes
        of divergence from persisting silently.
        """
        try:
            balance = await self._get_balance(self.config.target_asset)
            # --- U2 (2026-08-13) — WHICH VENUE NUMBER THE AUDIT READS
            # Coinbase reports TWO numbers per coin. `total` is every
            # coin owned. `free` is only the coins not tied up in a
            # resting order: free = total - used. This read was
            # `balance.free`. The startup handshake reads `total`
            # (:6347), and MEM-255 records why: `total` is the number
            # the operator sees on the exchange screen.
            #
            # Two readers of one wallet must not read two fields. The
            # branch below multiplies EVERY lot by venue / internal, so
            # on a bot with a resting order `free` is short by exactly
            # the committed units, and the book would be rescaled down
            # to exclude coins the operator still owns — discarding
            # those units AND their initial_buy_price permanently,
            # because the drift-UP branch never claims units back.
            #
            # EXPOSURE TODAY IS ZERO, AND THAT IS NOT A REASON TO LEAVE
            # IT. Measured in a read-only pin of bot_state.json:
            # active_buy_orders and active_sell_orders are 0 on all 37
            # bots, so total == free on every one of them right now,
            # and before U2 this rescale almost never ran at all. Stack
            # tranches PLACE RESTING ORDERS, so the condition that
            # makes this bite is the one the queue is heading for.
            #
            # The fallback chain is the handshake's, expression for
            # expression: total, else free, else zero -- unwrapped,
            # because `float(None)` raises where the domain rule below
            # is what should decide. `.free` is a BARE read on purpose:
            # a None or field-less balance must raise and fail closed.
            _venue_absent = bool(getattr(balance, "absent", False))
            _venue_raw = (getattr(balance, "total", 0)
                          or balance.free or 0.0)
        except Exception as exc:
            # Network blip / rate limit / exchange outage — retry later,
            # do not touch internal state (silent failure preserves
            # bot behaviour during transient issues).
            logger.debug("Bot %s reconcile fetch failed (%s): %s",
                        self.bot_id, reason, exc)
            return False

        # --- U2 (2026-08-13) — AN ABSENT READING IS NOT A ZERO ---
        # `ccxt_connector.get_balance` returns Balance(free=0, used=0,
        # total=0, absent=True) when the exchange response OMITTED the
        # currency entirely, and the SAME three zeros with absent=False
        # when the exchange really did report zero. No line number is
        # cited for that file -- nothing checks one, so it would rot
        # unseen. Reading the numbers alone made both arrive as one 0.0.
        #
        # Read as a zero it is maximally destructive, and only on the
        # branch U2 makes reachable: venue 0.0 against a real book is a
        # drift DOWN, ratio 0.0, every lot multiplied to zero, every
        # lot then dropped by the `> 1e-12` filter, `_current_holdings`
        # set to 0.0. A whole position and its entire cost basis erased
        # from one response that never mentioned the coin.
        #
        # No information is not a reading. Refuse, say which asset and
        # why, and let the next scheduled interval try again. The
        # startup handshake already refuses on this exact sentinel
        # (:6389); this closes the same hole on the periodic path.
        if _venue_absent:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(
                    f"RECONCILE REFUSED ({reason}): exchange OMITTED "
                    f"{self.config.target_asset} from the balance "
                    f"response, so the venue holding is UNKNOWN, not "
                    f"zero. No lot was rescaled and no holdings were "
                    f"reset. Retrying next interval."))
            logger.warning(
                "Bot %s reconcile (%s) REFUSED — %s absent from exchange "
                "response; venue holding UNKNOWN, not zero. No lot was "
                "rescaled and no holdings were reset.",
                self.bot_id, reason, self.config.target_asset)
            return False

        # --- U2 (2026-08-13) — AUDIT THE BOOK, NOT ONLY THE SCALAR ---
        # `bootstrap_exchange_state` sets the scalar with
        #     min(max(0.0, _units), _tracked_units_bootstrap)   (:5676)
        # so `min` can pull the SCALAR down to the wallet, can never
        # pull the LOT LIST down with it, and can never leave the
        # scalar above the lot sum. Auditing the scalar alone therefore
        # compares the wallet against the wallet, and the excess
        # strands in the book with nothing left to detect it.
        #
        # Measured in a read-only pin of ~/.acervator/bot_state.json
        # taken 2026-08-13 19:18Z: 20 of 37 bots carry a lot book ABOVE
        # their scalar and ZERO carry one below. One direction only,
        # which is what a `min` against a counter nobody audits
        # produces.
        #
        # ORCA is the worked example: book 54.05340782, scalar 48.73,
        # wallet 48.73. The old comparison read 48.73 against 48.73,
        # reported alignment, and left 5.32 units stranded. CAP is the
        # control that proves the other half: its excess had reached
        # the SCALAR too (book and scalar both 1136.227658), the
        # comparison could see it, and it fired at 08:10:54Z the same
        # day. CAP was the visible case, never the worst one.
        #
        # The audited quantity is now whichever counter claims MORE.
        # The larger keeps every drift the scalar already caught and
        # adds the ones only the book can see; the book alone would
        # have silenced any bot whose scalar is the higher of the two.
        _lot_each, _why = self._reconcilable_lot_book()
        _readings: list[float] = []
        if _lot_each is not None:
            # The book's TOTAL goes through the same domain rule as the
            # other two, so a book of finite lots that sums past the
            # float range is refused by the rule that already exists
            # rather than by a second one written for it.
            for _value, _label in (
                    (_venue_raw, "exchange balance (total)"),
                    (self._current_holdings, "_current_holdings"),
                    (sum(_lot_each), "_main_lots total")):
                _number, _why = self._reconcilable_units(_value, _label)
                if _number is None:
                    break
                _readings.append(_number)
        if _lot_each is None or len(_readings) != 3:
            # REFUSE. Same contract as a failed fetch: return False,
            # touch nothing, retry on the next scheduled interval. A
            # reconcile that cannot read its own inputs must not
            # rescale a real position, and must not tell the operator
            # it reset anything.
            logger.warning(
                "Bot %s reconcile (%s) REFUSED — %s. No lot was "
                "rescaled and no holdings were reset.",
                self.bot_id, reason, _why)
            return False
        exchange_units, _scalar_units, _lot_units = _readings
        # Both operands are known finite by here, so this is not the
        # comparison that can swallow a nan.
        internal_units = (_lot_units if _lot_units > _scalar_units
                          else _scalar_units)

        # v3.23.43 — retired multi-base attribution branch. Scrumming
        # bots reconcile against exchange asymmetrically (drift-down
        # only, per the fix below). Any units on exchange beyond what
        # `_main_lots` tracks belong to the operator or another bot;
        # this bot leaves them untouched.

        drift_units = exchange_units - internal_units
        if internal_units > 0:
            drift_pct = abs(drift_units) / internal_units * 100.0
        elif exchange_units > 0:
            # Internal thinks zero, exchange has some — always material
            drift_pct = float('inf')
        else:
            # Both zero: perfectly aligned
            drift_pct = 0.0

        _TOLERANCE_PCT = 0.5  # 0.5% — anything smaller is rounding noise
        # Same tolerance in UNITS. `drift_pct` is retained for the log
        # lines; the decision compares units against units.
        _tolerance_units = abs(internal_units) * _TOLERANCE_PCT / 100.0

        if abs(drift_units) <= _tolerance_units:
            # Aligned within tolerance. Log only at DEBUG level to avoid
            # Console noise for the common case.
            logger.debug(
                "Bot %s reconcile (%s) aligned: internal=%.6f exchange=%.6f "
                "drift=%.4f (%.3f%%)",
                self.bot_id, reason, internal_units, exchange_units,
                drift_units, drift_pct)
            return True

        # --- Drift above tolerance — reset internal state to exchange ---
        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(
                f"BALANCE DRIFT ({reason}): internal={internal_units:.6f} "
                f"exchange={exchange_units:.6f} "
                f"drift={drift_units:+.6f} ({drift_pct:.2f}%). "
                f"Resetting internal state to exchange reality."))
        logger.warning(
            "Bot %s balance drift (%s): internal=%.6f exchange=%.6f "
            "drift=%+.6f (%.3f%%) — resetting",
            self.bot_id, reason, internal_units, exchange_units,
            drift_units, drift_pct)

        # v3.23.43 — asymmetric drift-reconcile policy (operator
        # directive 2026-07-27 ETH/BTC-bot screenshot):
        #
        #   internal > exchange  → bot's records show more than the
        #     exchange has. This is a REAL problem (bot lost track of
        #     units, exchange debited without our knowledge, etc.).
        #     Rescale _main_lots down and reset _current_holdings.
        #
        #   internal < exchange  → exchange has MORE than the bot has
        #     tracked. These extra units are NOT the bot's — they
        #     belong to the operator (personal holdings), a prior bot
        #     that ran on this asset, a sibling bot in the shared pool,
        #     or a manual transfer. **The bot MUST NOT claim them.**
        #     Log the surplus for operator awareness; leave _main_lots
        #     and _current_holdings untouched. This is the fix for the
        #     "new ETH/BTC bot showed $178 surplus at fresh init"
        #     symptom — the bot was grabbing operator-owned ETH.
        if exchange_units < internal_units - 1e-9:
            # Drift DOWN: legitimate loss. Rescale internal state.
            if internal_units > 0 and self._main_lots:
                _ratio = exchange_units / internal_units
                # U2 — written from the COERCED units, not from the raw
                # ones. `_lot["units"] *= _ratio` raised KeyError on a
                # lot with no "units" key and TypeError on a string
                # one, both of them AFTER the drift line above had told
                # the operator the reset had already happened, and both
                # leaving the book half-rescaled. Neither can reach
                # here now: a missing key reads as zero and a string
                # unit is refused by type, both inside
                # `_reconcilable_lot_book`, before this method writes
                # anything at all. Nothing is awaited between that read
                # and here, so the list cannot have changed length
                # underneath; `strict` says so out loud rather than
                # truncating in silence if that ever stops being true.
                for _lot, _units in zip(self._main_lots, _lot_each,
                                        strict=True):
                    _lot["units"] = _units * _ratio
                self._main_lots = [l for l in self._main_lots
                                  if l["units"] > 1e-12]
            self._current_holdings = exchange_units
        else:
            # Drift UP (or effectively equal): extra units are NOT the
            # bot's. Do not auto-seed _main_lots, do not adopt the
            # exchange balance.
            _surplus = max(0.0, exchange_units - internal_units)
            if _surplus > 1e-9:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(
                        f"DRIFT UP ({reason}): {_surplus:.8f} "
                        f"{self.config.target_asset} on exchange NOT "
                        f"attributed to this bot (internal={internal_units:.8f} "
                        f"exchange={exchange_units:.8f}). Preserving "
                        f"internal state; those units belong to "
                        f"another bot, prior state, or operator."))
                logger.info(
                    "Bot %s drift UP (%s): surplus=%.8f preserved-internal=%.8f "
                    "→ NOT claiming exchange units",
                    self.bot_id, reason, _surplus, internal_units)
            # _current_holdings + _main_lots unchanged.
        return True


    # ------------------------------------------------------------------
    # Trade execution
    # ------------------------------------------------------------------

    # U1 (2026-08-13) -- the fallback emit in _settled_fill below used
    # to hardcode "MANUAL FIRE:". That was accurate only because the
    # manual rebalance was its one caller. The operator reads that
    # prefix in bot.log to tell WHICH path degraded to an estimate, so
    # the string becomes a lie about the path the moment a second
    # caller exists. Labelled here, BEFORE that caller is written.
    #
    # The set is CLOSED. An unrecognised token would only be a new way
    # to mislabel the same line, so unknown values -- and "" and None
    # -- resolve to the manual default. A rejected token goes to the
    # developer log, never to the operator's.
    _SETTLED_FILL_DEFAULT_LABEL = "MANUAL FIRE"
    _SETTLED_FILL_LABELS = frozenset((
        "MANUAL FIRE",   # the operator pressed Fire
        "SCRUM",         # an autonomous scrum sell
        "DIST",          # an upward-distribution sell
        "STACK",         # a wire-stack sell
    ))

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
                "log will read %s", label,
                sorted(cls._SETTLED_FILL_LABELS),
                cls._SETTLED_FILL_DEFAULT_LABEL)
        return cls._SETTLED_FILL_DEFAULT_LABEL

    async def _settled_fill(self, order, symbol: str,
                            requested_amount: float, quoted_price: float,
                            label: str | None = None):
        """Re-read a just-placed order so accounting books the REAL fill.

        THE DEFECT THIS CLOSES (operator item 2, 2026-08-06)
        ccxt's ``coinbase.create_order`` returns only
        ``{success, order_id, product_id, side, client_order_id}``. Every
        numeric field is absent, so ``_parse_order`` coerces them to 0
        and the caller's ``or`` chains fall through to the REQUESTED size
        and the TICK price. The bot then books those as if they were the
        fill. Holdings drift compounds across successive fires and
        corrupts the next delta -- which is what made the operator's
        amounts "strange, intermittent and hard to explain".

        A market order is not settled the instant ``create_order``
        returns, so this polls briefly rather than reading once.

        FALLING BACK IS ALLOWED, SILENTLY IS NOT. If the exchange never
        reports a fill we still return the requested/quoted estimate --
        the order DID execute and refusing to book it would be worse --
        but the caller is told, and the log says so in the operator's
        words rather than looking like a clean fill.

        ``label`` names the CALLER in that fallback line, drawn from a
        closed set (see ``_settled_fill_label``). It is ABSENT on the
        manual path, which keeps the message byte-identical to what the
        operator has always read there.

        Returns ``(fill_amount, fill_price, is_real)``.
        """
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
            return amt, px, True

        order_id = str(getattr(order, "id", "") or "")
        if order_id:
            # Coinbase settles market orders in well under a second, but
            # not synchronously. Three short polls cost ~0.6s worst case
            # on a path the operator triggered by hand.
            for _attempt in range(3):
                try:
                    await asyncio.sleep(0.2)
                    fetched = await self.exchange.get_order(order_id, symbol)
                except Exception as exc:  # R28-OK: fall through to the estimate below
                    logger.debug("settled-fill re-read failed for %s: %s",
                                 order_id, exc)
                    break
                f_amt, f_px = _extract(fetched)
                if f_amt > 0 and f_px > 0:
                    return f_amt, f_px, True
                amt = f_amt or amt
                px = f_px or px

        # Partial knowledge is still better than none: keep whatever the
        # exchange did report and only estimate the missing half.
        est_amt = amt if amt > 0 else float(requested_amount or 0.0)
        est_px = px if px > 0 else float(quoted_price or 0.0)
        _label = self._settled_fill_label(label)
        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"{_label}: exchange reported no settled fill for "
                     f"order {order_id or '?'}; booking the ESTIMATE "
                     f"({est_amt:.6f} @ ${est_px:.8f}) instead of a "
                     f"confirmed fill. Position accounting may drift from "
                     f"the exchange until the next reconcile."))
        return est_amt, est_px, False

    async def _execute_manual_rebalance(
            self, ticker, caller_intent: str = "manual_button") -> None:
        """MEM-241 — Rebalance holdings to target in one shot.

        Invoked from tick() when self._manual_fire_pending is True
        (operator clicked Manual Fire), AND from two autonomous code
        paths that piggyback on the same rebalance-to-center math:
        Wire Stack Fire (L4213) and Max Cartridge Fire (L4477).

        Operator directive (Session 24, for the manual_button path):
          "Manual Fire button should act as an Aggressive Trade."
          "Amount Scrummed or Folded will be the amount needed to get
           the Target Balance back to center line."
          "Positive [delta] = Scrum while Negative = Fold."

        Caller intent (v3.23.2 — fixes the attribution mislabeling
        observed at v3.23.0 launch: zero operator clicks but 28 of 31
        trade.log entries tagged operator_initiated=True because this
        helper used to hard-code the flag):

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

        Gates bypassed (per operator, Q1):
          - TA direction/confidence
          - BB fire thresholds, midline gate
          - MEM-171 initial_buy_price floor, scrum ref gate

        Downstream accounting:
          - Scrum proceeds queue for fold as a normal scrum would,
            which since 2026-08-12 includes scrum_fold_pct: the same
            _apply_scrum_fold_pct helper the autonomous path uses runs
            here too. The one intended difference from that path is
            that the resulting tranches are tagged operator_initiated
            per the caller intent (Q3).
          - 2026-08-12: the proceeds also run through
            _top_up_remnant_fold_tranches, the same merge the SCRUM and
            DIST sells do, so a part-spent tranche gains this sale's
            money instead of a new record appearing beside it. The band
            it filters on is self._last_bb, the tick's own cached
            reading; see the call site for why bb_result is not
            reachable from here. A merge keeps the OLDER record, so an
            operator_initiated tranche merged into an autonomous
            remnant is displayed thereafter as an autonomous one. Only
            the Fold Tranches "Source" column reads that field; the
            trade.filled and pnl.event attribution below is emitted
            separately and is unaffected.
          - Fold with no queued tranches opens a NEW lot at fill price,
            tagged operator_initiated per caller intent (Q2).
          - Fold with queued tranches discharges HIGHEST-PRICE-FIRST
            (matching MEM-069/MEM-171 FIFO discipline), but gates are
            skipped and any returned lot is tagged with caller_intent
            attribution.

        The operator_initiated flag makes operator-clicked trades
        visible to downstream audits (equity curve, P/L attribution,
        reconciliation tools) so a manual intervention doesn't look
        identical to an autonomous Wire Stack or Max Cartridge fire
        in the trade log.
        """
        # sadp: R28 R29 R55  # manual override: fail-loudly, idempotent, invariant-preserving

        # v3.23.2 — Derive emit-time labels + operator_initiated flag
        # from caller_intent. Single source of truth for the three-way
        # attribution; emit sites consume the derived values.
        _INTENT_MAP = {
            "manual_button": ("MANUAL_SCRUM", "MANUAL_FOLD", True),
            "wire_stack":    ("WIRE_STACK_SCRUM", "WIRE_STACK_FOLD", False),
            "max_cartridge": ("CARTRIDGE_SCRUM", "CARTRIDGE_FOLD", False),
        }
        if caller_intent not in _INTENT_MAP:
            raise ValueError(
                f"_execute_manual_rebalance: unknown caller_intent "
                f"{caller_intent!r}; expected one of "
                f"{sorted(_INTENT_MAP)}")
        _scrum_label, _fold_label, _operator_initiated = (
            _INTENT_MAP[caller_intent])

        # Clear the flag FIRST so an exception mid-execute doesn't
        # leave us in a replay loop.
        self._manual_fire_pending = False

        price = ticker.last
        if not price or price <= 0:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message="MANUAL FIRE: no valid price; aborting.")
            return

        # v3.15.55 — refresh quote→USD before the rebalance math so
        # crypto-quoted pairs (BTC/ETH) compute delta_usd correctly.
        try:
            await self._refresh_quote_to_usd()
        except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
            logger.debug("suppressed in %s: %s: %s", "_execute_manual_rebalance", type(_sup).__name__, _sup)
        _qrate = float(self._quote_to_usd or 1.0)

        current_value = self._current_holdings * price * _qrate
        delta_usd = current_value - self._target_balance
        dust = max(self._target_balance * 0.01, 0.01)

        # v3.24.87 - AUTONOMOUS FIRES ARE CHECKED AGAINST THE EXCHANGE.
        #
        # This path bypasses the gate chain BY DESIGN (see the "Gates
        # bypassed" note in the docstring): no TA direction, no BB
        # thresholds, no MEM-171 floor, no scrum ref gate. That is
        # acceptable for a button the operator pressed. It is not
        # acceptable for `wire_stack` and `max_cartridge`, which fire
        # autonomously -- with every gate off, `delta_usd` is the ONLY
        # thing standing between a bad holdings number and a market
        # order.
        #
        # LIVE INCIDENT 2026-08-09 (v3.24.51). BICO and IMU were created
        # with target $25 and the operator manually bought the first $25
        # of each. `_current_holdings` derived from `_main_lots`, which
        # was empty, so `current_value` was $0.00 while the exchange
        # held the coins. Max Cartridge computed `delta = -$25` and
        # bought a SECOND position:
        #   03:07:57 CARTRIDGE_FOLD BICO/USDC BUY 347.96 @ 0.0706380489
        #   03:11:19 CARTRIDGE_FOLD IMU/USDC  BUY 6350.0  @ 0.0039
        # Both gate records read `scrum_armed=false fold_armed=false
        # blockers=["pre-tick"]`.
        #
        # The holdings fix (opening-position adoption) stops the
        # miscount. This stops a miscount from SPENDING. They are
        # independent: this refuses on any disagreement with the
        # exchange, whatever produced it.
        #
        # Operator-pressed fires are deliberately exempt. The operator
        # can see the position and is entitled to act on a number this
        # bot disputes.
        if caller_intent != "manual_button":
            try:
                _xbal = await self._get_balance(self.config.target_asset)
                _xunits = float(getattr(_xbal, "total", 0) or
                                getattr(_xbal, "free", 0) or 0.0)
                _absent = bool(getattr(_xbal, "absent", False))
            except Exception as _xb_exc:  # noqa: BLE001
                self._bus.emit("bot.log", bot_id=self.bot_id, message=(
                    f"AUTONOMOUS FIRE REFUSED: could not read "
                    f"{self.config.target_asset} balance to verify the "
                    f"position ({_xb_exc}). Gates are bypassed on this "
                    f"path, so an unverified position is not traded."))
                return
            if _absent:
                # The exchange omitted the currency rather than
                # reporting zero. A structural zero is not evidence of
                # an empty position.
                self._bus.emit("bot.log", bot_id=self.bot_id, message=(
                    f"AUTONOMOUS FIRE REFUSED: exchange OMITTED "
                    f"{self.config.target_asset} from its balance "
                    f"response, so the position cannot be verified."))
                return
            _xvalue = _xunits * price * _qrate
            # Tolerance is the dust band: below it no trade fires anyway.
            if abs(_xvalue - current_value) > dust:
                self._bus.emit("bot.log", bot_id=self.bot_id, message=(
                    f"AUTONOMOUS FIRE REFUSED (position mismatch): this "
                    f"bot has {self._current_holdings:.6f} "
                    f"{self.config.target_asset} (${current_value:.2f}) "
                    f"but the exchange reports {_xunits:.6f} "
                    f"(${_xvalue:.2f}). Gates are bypassed on this path, "
                    f"so it will not trade on a disputed position. "
                    f"Intended {'SELL' if delta_usd > 0 else 'BUY'} of "
                    f"${abs(delta_usd):.2f} withheld."))
                logger.warning(
                    "Bot %s autonomous fire refused: internal %.8f vs "
                    "exchange %.8f %s", self.bot_id,
                    self._current_holdings, _xunits,
                    self.config.target_asset)
                return
            # HARD CEILING on the buy side. The live-settings tooltip
            # states it as a guarantee -- "position can never exceed
            # Target x (1 + Max Target Growth %/100)" (MEM-246/249/251)
            # -- and nothing on this path enforced it.
            if delta_usd < 0:
                _growth = float(getattr(
                    self.config, "max_target_growth_pct", 0.0) or 0.0)
                _ceiling = float(self._target_balance) * (
                    1.0 + _growth / 100.0)
                _prospective = _xvalue + abs(delta_usd)
                if _prospective > _ceiling + dust:
                    self._bus.emit("bot.log", bot_id=self.bot_id, message=(
                        f"AUTONOMOUS FIRE REFUSED (ceiling): buying "
                        f"${abs(delta_usd):.2f} would take the position "
                        f"to ${_prospective:.2f}, above the "
                        f"${_ceiling:.2f} cap (target "
                        f"${self._target_balance:.2f} x 1+{_growth:.1f}%)."))
                    logger.warning(
                        "Bot %s autonomous buy refused: prospective %.2f "
                        "> ceiling %.2f", self.bot_id, _prospective,
                        _ceiling)
                    return

        if abs(delta_usd) < dust:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"MANUAL FIRE: already within dust band "
                         f"(|delta|=${abs(delta_usd):.4f} < "
                         f"${dust:.2f}). No-op."))
            return

        # Build a synthetic summary for the execute helpers. They accept
        # a VotingSummary but only use consensus_confidence / direction
        # for logging — we pass a clearly-flagged manual marker.
        class _ManualSummary:
            consensus_confidence = 1.0
            direction = None  # exec helpers handle None gracefully
            raw_votes: dict = {}

            def __repr__(self) -> str:
                return "<ManualSummary operator_initiated=True>"

        summary = _ManualSummary()

        if delta_usd > 0:
            # -- SCRUM side: sell delta-worth of asset at MARKET --
            # v3.15.55 — delta_usd is USD; sell_amount must be base
            # units. USD / (quote_per_base × USD_per_quote) = base.
            _denom_sc = price * _qrate
            sell_amount = (delta_usd / _denom_sc) if _denom_sc > 0 else 0.0
            # Bound by current holdings (defensive; should never exceed)
            sell_amount = min(sell_amount, self._current_holdings)
            if sell_amount <= 0:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message="MANUAL FIRE: computed zero sell amount; abort.")
                return

            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"MANUAL FIRE SCRUM: delta=+${delta_usd:.4f} "
                         f"over target → selling {sell_amount:.6f} "
                         f"{self.config.symbol.split('/')[0]} @ MARKET "
                         f"(~${price:.8f}) to rebalance."))

            order = await self.guarded_place_order(
                symbol=self.config.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                amount=sell_amount,
                price=None,
            )

            # MEM-242 bugfix: check fill amount explicitly rather than
            # truthiness on getattr(order, "filled", None). Some
            # exchanges return Order objects with filled=0.0 on
            # successful market orders when fill detail lives on a
            # different field (average, info["filled_size"], etc.).
            # Truthiness check "not getattr(order, 'filled', None)"
            # treats 0.0 as falsey and aborts a legitimately-placed
            # order. Use multiple fallback fields, same discipline as
            # the organic _execute_sell post-fill path.
            if order is None:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message="MANUAL FIRE SCRUM: exchange returned no order.")
                return

            # v3.24.xx — read the SETTLED fill rather than assuming the
            # request was filled at the tick price. See _settled_fill.
            fill_amount, fill_price, _fill_is_real = await self._settled_fill(
                order, self.config.symbol, sell_amount, price)
            if fill_amount <= 0:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"MANUAL FIRE SCRUM: order placed but no "
                             f"filled amount reported (order.filled="
                             f"{getattr(order, 'filled', 'missing')}, "
                             f"order.amount={getattr(order, 'amount', 'missing')}). "
                             f"Aborting post-fill accounting; check exchange for actual state."))
                return
            if fill_price <= 0:
                fill_price = price

            # Fill accounting. Mirror _execute_sell's post-fill logic:
            # decrement holdings, build a fold tranche from main_lots
            # (highest-price-first), queue for fold.
            fill_usd = fill_price * fill_amount
            self._current_holdings = max(
                0.0, self._current_holdings - fill_amount)

            # v3.16.51 — Smart Wire SCRUM-time routing on Manual Fire.
            # Operator directive 2026-05-10: routing must fire on every
            # sell path that produces scrum proceeds, not just autonomous
            # tick. Operator's heavy Manual Fire usage ("dagger catch")
            # was silently bypassing the wire system pre-v3.16.51.
            # Tranches built below use the REDUCED fill_usd so the local
            # share equals what stays with this bot after routing.
            _manual_routed_total = self._route_scrum_proceeds_via_wires(
                scrum_usd=fill_usd,
                sell_fill=fill_price,
                label="manual_scrum")
            fill_usd = max(0.0, fill_usd - _manual_routed_total)

            # Build fold tranche(s) from highest-priced lots first
            # (same discipline as MEM-069/MEM-171 organic scrum path).
            self._main_lots.sort(
                key=lambda l: l["initial_buy_price"], reverse=True)
            # 2026-08-12 — where THIS fire's tranches start. Sampled
            # before the build loop so the slice the helper scales
            # covers what this fire appended and nothing from an
            # earlier one.
            _manual_tranche_count_before = len(self._fold_tranches)
            remaining = fill_amount
            new_tranches_count = 0
            for lot in list(self._main_lots):
                if remaining <= 1e-12:
                    break
                take = min(lot["units"], remaining)
                t_usd = (take / fill_amount) * fill_usd
                self._fold_tranches.append({
                    "usd": t_usd,
                    "units": take,
                    "ref": fill_price,
                    "initial_buy_price": lot["initial_buy_price"],
                    "operator_initiated": _operator_initiated,  # MEM-241 Q3 (v3.23.2: routed via caller_intent)
                    "created_ts": time.time(),  # v3.16.39 P2-VIS
                })
                self._tranches_created_lifetime += 1  # v3.16.39 P2-VIS
                lot["units"] -= take
                remaining -= take
                if lot["units"] <= 1e-12:
                    self._main_lots.remove(lot)
                new_tranches_count += 1

            # 2026-08-12 — MIRRORED FROM THE SCRUM PATH. This method
            # serves three callers -- Manual Fire, Wire Stack and Max
            # Cartridge -- and two of the three fire autonomously, so
            # the gap was never "manual only". `fill_usd` is already net
            # of Smart Wire routing and is the same figure the build
            # loop divided, so the units test inside the helper reads
            # this sale's own rate. Runs before the _fold_queue_usd sum
            # below so the derived scalar reports the scaled queue.
            self._apply_scrum_fold_pct(
                _manual_tranche_count_before, fill_usd, fill_amount)

            # 2026-08-12 — TOP-UP ON AN OPPOSING TRADE. The third and
            # last spawn site to get it. This sell is the opposing
            # trade to a FOLD exactly as a SCRUM or a DIST is, so a
            # part-spent tranche must "gain more" here too. Without
            # this call, and this path alone lacked it, every fire left
            # a new record BESIDE the remnants instead of merging into
            # them, and the tranche list grew on every fire. Two of the
            # three callers routed here fire autonomously, so that
            # growth was never bounded by operator clicks.
            #
            # WHY AFTER `_apply_scrum_fold_pct`, NOT BEFORE. The ratio
            # helper scales only
            # `_fold_tranches[_manual_tranche_count_before:]`, this
            # fire's own slice. The top-up moves that money into an
            # OLDER record, which sits OUTSIDE the slice, so merging
            # first would carry the money out of reach of the
            # operator's fold-ratio setting entirely. Running second
            # means only what already survived the ratio can merge.
            # Same order as the SCRUM and DIST sites.
            #
            # WHERE THE BAND COMES FROM, and why it is not `bb_result`.
            # `bb_result` is a local of `tick`; this is a different
            # method and cannot see it. All three callers of this
            # method sit ABOVE the `detect_bb_proximity` call in
            # `tick`, so even passing it in would carry the PREVIOUS
            # tick's band. `self._last_bb` IS that band: the cached
            # result of the tick's own `detect_bb_proximity`, and the
            # same source the Smart Cartridge gate already reads for
            # the same reason. Nothing is recomputed here — this path
            # holds no candles. Before any band has been computed
            # `_last_bb` is None, both figures read 0.0, and the
            # helper's own guard declines to merge rather than
            # inventing a range.
            #
            # WHAT HAPPENS TO `operator_initiated` ON A MERGE. The
            # surviving record is the OLDER one, so it keeps the tag it
            # already had and the incoming tranche's tag goes with the
            # record that is removed. A `manual_button` fire merging
            # into a remnant left by an autonomous scrum therefore
            # shows as "auto scrum" in the Fold Tranches table. That
            # column is the only consumer; no gate, order or amount
            # reads the field. The `trade.filled` and `pnl.event`
            # emissions below carry `operator_initiated` themselves and
            # are untouched by any merge, so trade-log attribution —
            # the thing v3.23.2 fixed — is unaffected. Making the tag a
            # merge condition would be a change to the SHARED helper
            # and so a change to the SCRUM and DIST paths as well; that
            # is an operator decision, not one to take here.
            _bb_last = getattr(self, "_last_bb", None)
            # The dollars moved are dropped on purpose: the helper
            # emits its own FOLD TOP-UP line carrying that figure, and
            # a second report of the same number from here would be a
            # second source of truth for it.
            _merged_n, _ = self._top_up_remnant_fold_tranches(
                _manual_tranche_count_before,
                float(getattr(_bb_last, "lower", 0.0) or 0.0),
                float(getattr(_bb_last, "upper", 0.0) or 0.0))
            # A merged tranche did not stay open, so the count the log
            # below reports has to come down with it. Left alone it
            # would tell the operator this fire queued records that are
            # not in the list.
            new_tranches_count -= _merged_n

            self._fold_queue_usd = sum(
                t["usd"] for t in self._fold_tranches)
            self.stats.total_trades += 1

            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"MANUAL FIRE SCRUM FILLED: {fill_amount:.6f} "
                         f"@ ${fill_price:.8f} = ${fill_usd:.4f}. "
                         f"{new_tranches_count} tranche(s) queued "
                         f"(operator_initiated). Holdings now "
                         f"{self._current_holdings:.6f} "
                         f"(~${self._current_holdings * price * float(self._quote_to_usd or 1.0):.2f})."))
            self._bus.emit("trade.filled", bot_id=self.bot_id, data={
                "type": _scrum_label,
                "side": "SELL",
                "amount": fill_amount,
                "price": fill_price,
                "usd": fill_usd,
                "profit": 0.0,  # profit computed at fold-back time
                "operator_initiated": _operator_initiated,
            })
            # v3.23.11 — voting.log + gate.log snapshots at fire (D-NEW-A).
            self._emit_voting_panel_snapshot_at_fire(
                side="SELL", trade_action=str(_scrum_label or "MANUAL_SCRUM"))
            self._emit_gate_decision_at_fire(
                side="SELL", trade_action=str(_scrum_label or "MANUAL_SCRUM"))
            # v3.16.60 — PnL event for SCRUM (audit completeness).
            # v3.23.2 — labels routed via caller_intent so Wire Stack
            # + Max Cartridge autonomous fires no longer mislabel as
            # MANUAL_SCRUM downstream.
            try:
                self._bus.emit("pnl.event", bot_id=self.bot_id, data={
                    "kind": "SCRUM",
                    "asset": self.config.target_asset,
                    "symbol": self.config.symbol,
                    "units": float(fill_amount),
                    "fill_price": float(fill_price),
                    "usd_captured": float(fill_usd) * float(
                        self._quote_to_usd or 1.0),
                    "operator_initiated": _operator_initiated,
                    "manual_kind": _scrum_label,
                })
            except Exception as _sup:  # R28-OK: PnL telemetry best-effort
                logger.debug("suppressed in %s: %s: %s", "_execute_manual_rebalance", type(_sup).__name__, _sup)
            # v3.15.50 — high-score counter.
            # v3.15.55 — quote→USD-aware (fill_usd is quote-units).
            _fill_usd_true = float(fill_usd) * float(self._quote_to_usd or 1.0)
            self.stats.total_scrummed_usd += _fill_usd_true
            # v3.23.65 SWOS retention counter (third scrum site).
            self.note_scrum_retention_usd(_fill_usd_true)
            # v3.15.52 — record side for opposite-direction hysteresis.
            # Manual fire is operator-authorised but still updates the
            # last-trade-side marker so the NEXT auto trade respects
            # the manual override's price as the new hysteresis anchor.
            self._last_trade_side = "SCRUM"
            self._last_trade_price = fill_price
            # v3.15.77 — disarm both gates after manual fire too.
            self._reset_opposing_hysteresis_after_fill()

        else:
            # -- FOLD side: buy |delta|-worth of asset at MARKET --

            # v3.25.x (U3) -- THE AUTONOMOUS FOLD IS GATED ON PRICE.
            #
            # Two of this method's three callers fire with no operator
            # present: Wire Stack (L6756) and Max Cartridge (L7026). On
            # that path every MEM-171 gate is bypassed by design, and
            # until now nothing compared the rebuy price against the
            # price the tranche was SOLD at. The discharge loop below
            # sorts by `ref` descending and consumes whatever the fill
            # reaches, booking profit only where `_t_ref > fill_price`
            # -- so a tranche re-bought ABOVE its own ref was consumed
            # for zero booked profit and its queued `usd` left the
            # ladder for good. The emit at the end reported success.
            #
            # THE RULE IS NOT NEW AND IS NOT REDEFINED HERE. It is the
            # autonomous tick fold-back's own per-tranche filter, whose
            # arithmetic lives in `otd_math`:
            #     eligible  <=>  ticker.last <= ref * factor
            # This site asks that module the same question. A second
            # copy of the arithmetic is how four copies drifted apart
            # before `otd_math` existed.
            #
            # THE VERB IS REFUSE, AND ONLY REFUSE. The order is placed
            # BELOW, before the discharge loop, so a check inside that
            # loop would not stop a trade -- it would only move where
            # the bought units land. This withholds the WHOLE fire when
            # not one queued tranche is eligible. When SOME are, the
            # fire proceeds unchanged and the loop still walks into
            # ineligible tranches; that residue has a different verb
            # and is NOT closed here.
            #
            # THE OPERATOR IS SOVEREIGN. `manual_button` is exempt --
            # the same exemption the MEM-257 verification above uses,
            # and the same one `manual_fire_tranche` states as an
            # operator ruling: "OTD per-tranche price gate (operator
            # chose this tranche explicitly)".
            #
            # AN EMPTY LADDER IS NOT REFUSED. With no queued tranche
            # there is no `ref` for a distance to be measured against,
            # and that fire takes the fresh-lot path below.
            #
            # A BAD CONFIG REFUSES, and that is a DELIBERATE DIFFERENCE
            # from the tick path, which falls back to an OTD of 0.0 --
            # a factor of 1.0, no distance gate at all. `otd_math`'s
            # own docstring names that fallback as a hazard. Inheriting
            # it would let an unparseable config silently restore this
            # defect on the one path where every other gate is already
            # off. The posture here is the posture stated by the
            # position check above: an unverified number is not traded.
            if caller_intent != "manual_button" and self._fold_tranches:
                from .otd_math import (  # local import: keep module load light
                    fold_rebuy_factor,
                )
                _fold_factor = 1.0
                _best_rebuy = 0.0
                _distance_ok = False
                # Bound before the `try` for the reason `_excluded`
                # (:9823) and `_fold_plan` (:9830) are: both are read
                # by messages below, and an unbound name there would
                # raise while REPORTING a decision rather than making
                # one.
                _unreadable_refs = 0
                _thresholds: list[float] = []
                try:
                    _fold_factor = fold_rebuy_factor(
                        getattr(self.config, 'scrumming_interval_pct', 0) or 0,
                        getattr(self.config, 'trading_fee_pct', 0.6) or 0.6)
                    # The most permissive threshold in the ladder: the
                    # highest price at which ANY queued tranche is still
                    # eligible. If price clears none of them, none of
                    # them should be bought back.
                    #
                    # THE THRESHOLD IS FILTERED BEFORE IT IS MAXIMISED,
                    # AND THAT ORDER IS THE WHOLE POINT. `max` keeps
                    # whichever operand it saw FIRST whenever the
                    # comparison is False, and EVERY comparison against
                    # nan is False -- so `max` DISCARDS a nan it meets
                    # late and KEEPS one it meets first. Measured on the
                    # code this replaces, one nan ref beside one plainly
                    # eligible ref=1.0, at price 0.5:
                    #     [nan, good] -> AUTONOMOUS FIRE REFUSED
                    #     [good, nan] -> PLACED BUY
                    # Same ladder, same price, opposite answer, decided
                    # by list position. Over all 24 permutations of a
                    # 4-row ladder holding one nan, 6 refused and 18
                    # bought. Nobody chose that; it fell out of `max`.
                    #
                    # `+inf` is the same hole facing the other way. It
                    # WINS every comparison, `price <= inf` is True for
                    # every price, and the gate is then fully disabled
                    # on the one path where every other gate already is.
                    #
                    # The rule is this file's own, recorded above
                    # `_reconcilable_units` (:11206): "A finiteness test
                    # has to run BEFORE any comparison, never as part of
                    # one."
                    #
                    # A ROW SETS THE THRESHOLD ONLY IF ITS THRESHOLD IS
                    # FINITE. THIS IS NOT A NEW POLICY. It is the policy
                    # this gate already had for every other malformed
                    # ref: a missing key reads 0.0 via the `get`
                    # default, and 0.0 and a negative both LOSE the max,
                    # so all three already failed to set the threshold
                    # while the gate answered on the readable rows --
                    # pinned by `test_a_ladder_of_only_malformed_refs_
                    # refuses` and by the "a zero ref and a negative ref
                    # sit beside a good one" row of IN_SPEC. `nan` was
                    # the single value that escaped it, because it is
                    # the single value `max` cannot order.
                    #
                    # THE VERB IS STILL ONLY REFUSE. The ladder is NOT
                    # purged here, which is the deliberate difference
                    # from the tick path's own guard (:9734). That guard
                    # DELETES the malformed rows and bumps
                    # `_tranches_malformed_dropped`; it can, because it
                    # runs after its fold has committed to acting. This
                    # site can return WITHOUT firing, so a purge here
                    # would destroy ladder rows on a fire that never
                    # happened -- and `manual_button` skips this whole
                    # block, so the ladder's content would then depend
                    # on which caller fired. Mutation is a second verb
                    # and it is not this one's.
                    for _t in self._fold_tranches:
                        _t_thresh = float(_t.get("ref", 0)) * _fold_factor
                        if not math.isfinite(_t_thresh):
                            _unreadable_refs += 1
                            continue
                        _thresholds.append(_t_thresh)
                    # AN UNREADABLE ROW IS NOT AN ELIGIBLE ROW. With no
                    # readable row there is no threshold, so there is
                    # nothing this price can clear and the fire is
                    # refused -- the same answer the pre-change code
                    # gave for a ladder of only zero and negative refs.
                    if _thresholds:
                        _best_rebuy = max(_thresholds)
                        # A non-finite price fails this comparison rather
                        # than passing it: `nan <= x` is False, and the
                        # validity check above admits nan and +inf.
                        _distance_ok = price <= _best_rebuy
                # OverflowError joins the tuple because `float()` raises
                # it, not ValueError, on an int too large for a float --
                # and `json.loads` accepts a 400-digit integer literal.
                # Before this it left the method entirely, so a corrupt
                # state file crashed the fold instead of refusing it.
                except (TypeError, ValueError, OverflowError) as _otd_exc:
                    self._bus.emit("bot.log", bot_id=self.bot_id, message=(
                        f"AUTONOMOUS FIRE REFUSED (opposing distance "
                        f"unreadable): {_otd_exc}. Gates are bypassed on "
                        f"this path, so a rebuy distance that cannot be "
                        f"computed is not traded. Intended BUY of "
                        f"${abs(delta_usd):.2f} withheld."))
                    logger.warning(
                        "Bot %s autonomous fold refused: opposing distance "
                        "unreadable: %s", self.bot_id, _otd_exc)
                    return
                # SKIPPING A ROW MUST NOT BE SILENT. Refusing is loud by
                # construction -- the operator sees a fold stop. Firing
                # on a PARTLY READABLE ladder is the quiet case, and it
                # is the one that needs saying out loud, because the
                # answer was computed from fewer tranches than he has.
                # Emitted whichever way the gate then decides, so the
                # corrupt row is reported even on the fire it allows.
                _unread_tail = ""
                if _unreadable_refs:
                    _unread_tail = (
                        f" {_unreadable_refs} of the "
                        f"{len(self._fold_tranches)} queued tranche(s) hold "
                        f"a ref that is not a finite number; those set no "
                        f"threshold at all, so this answer is the one for "
                        f"the {len(_thresholds)} readable tranche(s).")
                    self._bus.emit("bot.log", bot_id=self.bot_id, message=(
                        f"FOLD REF UNREADABLE: {_unreadable_refs} of "
                        f"{len(self._fold_tranches)} queued tranche(s) hold a "
                        f"ref that is not a finite number (nan or inf), so "
                        f"they set no rebuy threshold and the gate answered "
                        f"on the {len(_thresholds)} readable one(s). The "
                        f"ladder is NOT altered here; this gate only "
                        f"withholds or allows the fire. Repair the row in "
                        f"bot state to bring those tranches back into the "
                        f"distance test."))
                    logger.warning(
                        "Bot %s fold ref unreadable on %d of %d tranche(s); "
                        "gated on the %d readable one(s)", self.bot_id,
                        _unreadable_refs, len(self._fold_tranches),
                        len(_thresholds))
                if not _distance_ok:
                    self._bus.emit("bot.log", bot_id=self.bot_id, message=(
                        f"AUTONOMOUS FIRE REFUSED (opposing distance): at "
                        f"${price:.8f} not one of the "
                        f"{len(self._fold_tranches)} queued tranche(s) is "
                        f"eligible. The highest rebuy any of them allows "
                        f"is ${_best_rebuy:.8f} (its ref x "
                        f"{_fold_factor:.4f}), so price must fall "
                        f"${price - _best_rebuy:.8f} further. Gates are "
                        f"bypassed on this path, so it will not rebuy "
                        f"above what it sold at. Intended BUY of "
                        f"${abs(delta_usd):.2f} withheld.{_unread_tail}"))
                    logger.warning(
                        "Bot %s autonomous fold refused: price %.8f above "
                        "best rebuy %.8f across %d tranche(s), %d unreadable",
                        self.bot_id, price, _best_rebuy,
                        len(self._fold_tranches), _unreadable_refs)
                    return

            #
            # v3.24.xx (operator directive 2026-08-07) — size against the
            # POST-growth target, not the pre-growth one.
            #
            # THE DEFECT: the buy was sized from `-delta_usd` against
            # `_target_balance`, and only AFTER the fill did
            # `_apply_fold_target_growth` raise that target. Position
            # landed on target_OLD while target became target_OLD +
            # growth, so the residual deficit was IDENTICALLY the growth
            # and the fold logged success having structurally failed to
            # re-zero. Worse, the residual is always smaller than Manual
            # Fire's own 1% dust band (growth caps at 1% of anchor, and
            # target >= anchor), so firing again reported "already
            # within dust band" and the miss could never be worked off.
            #
            # Operator ruling: "After growth is calculated so that the
            # Fold does not acquire too little and actually fails to
            # compound." The growth must therefore be BACKED BY POSITION
            # rather than left sitting in the wallet as cash.
            #
            # Fixed point, because buying more units discharges more
            # tranches which yields more growth. It converges in one or
            # two passes: growth is bounded by the cycle cap, so the
            # feedback term is small and strictly decreasing.
            _denom_pre = price * _qrate
            _growth_preview = 0.0
            # RESET BEFORE THE LOOP, NOT INSIDE IT. `_denom_pre <= 0`
            # skips the loop entirely, and a count left over from an
            # earlier fire would then be reported against THIS ladder.
            # The preview overwrites it on every iteration that reaches
            # the filter, with the same ladder each time, so after the
            # loop it holds this ladder's count.
            self._fold_preview_unreadable_refs = 0
            self._fold_preview_unreadable_units = 0
            if _denom_pre > 0:
                for _ in range(4):
                    _units_pre = ((-delta_usd) + _growth_preview) / _denom_pre
                    _g = self._preview_fold_growth(_units_pre, price)
                    if abs(_g - _growth_preview) <= 1e-9:
                        break
                    _growth_preview = _g
            # SIZING ON A PARTLY READABLE LADDER MUST NOT BE SILENT.
            # This is the FOLD REF UNREADABLE notice's twin on the money
            # side, and it is the one the operator needs more: the gate
            # only withholds a fire, while this decides the AMOUNT sent
            # to the exchange. It is emitted for EVERY caller intent --
            # `manual_button` skips the distance gate above entirely, so
            # without this an operator-clicked fire on a corrupt ladder
            # would size off a subset of it and say nothing at all.
            _preview_unreadable = int(
                getattr(self, "_fold_preview_unreadable_refs", 0) or 0)
            if _preview_unreadable:
                self._bus.emit("bot.log", bot_id=self.bot_id, message=(
                    f"FOLD SIZING REF UNREADABLE: {_preview_unreadable} of "
                    f"{len(self._fold_tranches)} queued tranche(s) hold a "
                    f"ref that is not a finite number (nan or inf). Those "
                    f"set no discharge order and add no prospective "
                    f"growth, so this buy is sized on the "
                    f"{len(self._fold_tranches) - _preview_unreadable} "
                    f"readable one(s). The ladder is NOT altered here. "
                    f"Repair the row in bot state to bring those tranches "
                    f"back into the sizing."))
                logger.warning(
                    "Bot %s fold sizing ref unreadable on %d of %d "
                    "tranche(s)", self.bot_id, _preview_unreadable,
                    len(self._fold_tranches))
            # THE TWIN NOTICE, ONE FIELD OVER. A row whose `ref` is
            # unreadable sets no discharge ORDER; a row whose `units`
            # are unreadable discharges no AMOUNT. Both shrink the
            # ladder this buy is sized on, both are silent without a
            # notice, and the operator needs the same sentence about
            # each. Emitted separately because a row can fail either
            # test independently and the repair differs by field.
            _preview_unsizable = int(
                getattr(self, "_fold_preview_unreadable_units", 0) or 0)
            if _preview_unsizable:
                self._bus.emit("bot.log", bot_id=self.bot_id, message=(
                    f"FOLD SIZING UNITS UNREADABLE: {_preview_unsizable} of "
                    f"{len(self._fold_tranches)} queued tranche(s) hold "
                    f"units that are not a finite number (nan or inf). "
                    f"Those discharge nothing and add no prospective "
                    f"growth, so this buy is sized on the remaining "
                    f"readable one(s). The ladder is NOT altered here. "
                    f"Repair the row in bot state to bring those tranches "
                    f"back into the sizing."))
                logger.warning(
                    "Bot %s fold sizing units unreadable on %d of %d "
                    "tranche(s)", self.bot_id, _preview_unsizable,
                    len(self._fold_tranches))
            buy_usd_target = -delta_usd + _growth_preview
            if _growth_preview > 1e-9:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"MANUAL FIRE FOLD: sizing against the "
                             f"POST-growth target — base deficit "
                             f"${-delta_usd:.4f} + prospective compound "
                             f"growth ${_growth_preview:.4f} = "
                             f"${buy_usd_target:.4f}. Without this the "
                             f"fold would land ${_growth_preview:.4f} "
                             f"short and could not compound."))
            # v3.15.55 quote→USD-aware (crypto-quoted pairs route via _qrate)
            quote_currency = self.config.symbol.split("/")[-1]
            quote_free = 0.0
            _bal_err = None
            try:
                bal = await self._get_balance(quote_currency)
                quote_free = float(getattr(bal, "free", 0) or 0)
            except Exception as exc:  # R28-OK: error captured in _bal_err for downstream emit
                _bal_err = exc
                try:
                    balances = await self.exchange.get_balances()
                    b = balances.get(quote_currency)
                    if b is not None:
                        quote_free = float(getattr(b, "free", 0) or 0)
                except Exception as exc2:  # R28-OK: error captured in _bal_err for downstream emit
                    _bal_err = exc2
            # v3.24.xx (M3) — net off what other bots already have
            # in flight. All 35 bots read the SAME wallet, so without
            # this each one sees the full balance, each believes it can
            # afford its own buy, and together they can commit more than
            # exists. Whichever orders arrive last get rejected or
            # partially filled, which reaches the operator as an
            # unexplained amount.
            _wallet_key = wallet_key(self.config.exchange_id, quote_currency)
            _reservations = get_wallet_reservations()
            _wallet_free = quote_free * _qrate  # USD-equivalent in wallet
            usd_balance = _reservations.available(_wallet_key, _wallet_free)
            _held_by_others = _reservations.reserved(_wallet_key)
            buy_usd = min(buy_usd_target, usd_balance)
            if buy_usd <= 0:
                err_tail = f" (fetch error: {_bal_err})" if _bal_err else ""
                # Name the in-flight holds explicitly: "free $500 but you
                # may spend $0" is otherwise unreadable to the operator.
                held_tail = (
                    f", of which ${_held_by_others:.4f} is reserved by "
                    f"other bots' in-flight orders"
                    if _held_by_others > 1e-9 else "")
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"MANUAL FIRE FOLD: delta=-${buy_usd_target:.4f} "
                             f"but {quote_currency} free=${quote_free:.4f} "
                             f"(~${_wallet_free:.4f} USD{held_tail}; "
                             f"spendable ${usd_balance:.4f})"
                             f"{err_tail}. Cannot rebalance."))
                return
            # USD spend → BASE units (qrate=1 → legacy USD/price semantic).
            denom = price * _qrate
            buy_amount = (buy_usd / denom) if denom > 0 else 0.0
            clipped = buy_usd < buy_usd_target
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"MANUAL FIRE FOLD: delta=-${buy_usd_target:.4f} "
                         f"under target → buying {buy_amount:.6f} "
                         f"{self.config.symbol.split('/')[0]} @ MARKET "
                         f"(~${price:.8f}) with ${buy_usd:.4f}"
                         f"{f' (CLIPPED by {quote_currency})' if clipped else ''}."))

            # v3.18.14 (P0 BONK closure) → v3.18.15 (P1 Manual Fire
            # audit, MEM-273) — IMPORTANT REVISION. The v3.18.14 ship
            # added a MEM-257 FAIL-CLOSED helper call HERE inside the
            # shared `_execute_manual_rebalance` FOLD branch, intending
            # to close the Max Cartridge defense gap. The R68 self-
            # audit during the P1 Manual Fire investigation caught
            # that this also intercepted operator-initiated Manual
            # Fire — violating the Session 26 close invariant:
            # "Manual Fire is the operator-authorized override. It
            # MUST bypass every gate." The fix has been LIFTED OUT of
            # this shared method and pushed to the two AUTO-fire call
            # sites only (Max Cartridge at scrumming_bot.py:~4162,
            # Wire Stack at ~3918). Manual Fire (line ~3876) is
            # deliberately untouched — operator sovereignty preserved.
            # See MEM-273 for the full architectural rationale.
            #
            # v3.24.xx (M3) — hold this bot's share of the shared wallet
            # for as long as the order is in flight, so a concurrent
            # fire on another bot sizes against what is genuinely left.
            # try/finally: an exception between here and the release
            # would strand the hold and shrink every other bot's budget
            # for the life of the process.
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

            # MEM-242 bugfix — same explicit-fill-amount discipline as
            # the SCRUM branch above.
            if order is None:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message="MANUAL FIRE FOLD: exchange returned no order.")
                return

            # v3.24.xx — settled fill, same discipline as the SCRUM
            # branch. This one matters more: the fold's profit is
            # take x (ref - fill_price), so a fabricated fill_price
            # fabricates the compounding surplus too.
            fill_amount, fill_price, _fill_is_real = await self._settled_fill(
                order, self.config.symbol, buy_amount, price)
            if fill_amount <= 0:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"MANUAL FIRE FOLD: order placed but no "
                             f"filled amount reported (order.filled="
                             f"{getattr(order, 'filled', 'missing')}, "
                             f"order.amount={getattr(order, 'amount', 'missing')}). "
                             f"Aborting post-fill accounting; check exchange for actual state."))
                return
            if fill_price <= 0:
                fill_price = price

            # Decide: discharge queued tranches (Q1: bypass gates) OR
            # open a fresh lot if no tranches queued (Q2: mark
            # operator-initiated).
            # v3.23.30 — accumulate per-slice fold profit (Option B).
            # Each tranche slice contributes take × (ref − fill_price)
            # USD-equivalent when fill_price < ref. Applied via the
            # shared _apply_fold_target_growth() helper after the loop
            # so MANUAL_FOLD + CARTRIDGE_FOLD paths compound target
            # growth like autonomous FOLD does.
            _manual_fold_accum_profit = 0.0
            if self._fold_tranches:
                # Bypass MEM-171 gates (Q1 = bypass). Discharge
                # HIGHEST-PRICE-FIRST to preserve cost-basis discipline.
                self._fold_tranches.sort(
                    key=lambda t: t["ref"], reverse=True)
                remaining = fill_amount
                consumed = []
                for t in list(self._fold_tranches):
                    if remaining <= 1e-12:
                        break
                    t_units = t.get("units", 0.0)
                    take = min(t_units, remaining)
                    if take <= 1e-12:
                        continue
                    # v3.23.30 — per-slice surplus (take units bought
                    # cheaper than sold). Positive when fill_price <
                    # tranche's ref (the original sell price).
                    _t_ref = float(t.get("ref", 0.0) or 0.0)
                    if _t_ref > fill_price:
                        _manual_fold_accum_profit += (
                            take * (_t_ref - fill_price))
                    # Return rebought units to _main_lots, preserving
                    # initial_buy_price (profit-floor semantic). Tag
                    # operator_initiated per caller_intent (Q1 — these
                    # lots came from an operator-forced fold OR a
                    # Wire Stack / Max Cartridge autonomous fire;
                    # v3.23.2 routes the flag via the derived
                    # _operator_initiated rather than hard-coding True).
                    self._main_lots.append({
                        "units": take,
                        "initial_buy_price": t.get(
                            "initial_buy_price", fill_price),
                        "operator_initiated": _operator_initiated,
                    })
                    t["units"] -= take
                    # Scale tranche usd proportionally
                    if t_units > 0:
                        t["usd"] *= (t["units"] / t_units)
                    remaining -= take
                    if t["units"] <= 1e-12:
                        consumed.append(t)

                for t in consumed:
                    self._fold_tranches.remove(t)
                # v3.16.55 — increment the lifetime-closed counter for
                # whole-bot Manual Fire FOLD discharge. Prior versions
                # silently removed tranches here without bumping the
                # visibility counter; operator-observed bug 2026-05-12
                # ("Lifetime closed: 0" while open-tranches count was
                # demonstrably decreasing). This is the same discipline
                # the auto fold-back path at line ~6071 uses.
                if consumed:
                    try:
                        self._tranches_closed_lifetime = int(
                            getattr(self, "_tranches_closed_lifetime", 0)
                            or 0) + len(consumed)
                    except Exception as _sup:  # R28-OK: counter probe; non-critical
                        logger.debug("suppressed in %s: %s: %s", "_execute_manual_rebalance", type(_sup).__name__, _sup)

                # Any buy amount not consumed by tranches opens a
                # fresh lot (overshoot case). v3.23.2: operator_initiated
                # derived from caller_intent.
                if remaining > 1e-12:
                    self._main_lots.append({
                        "units": remaining,
                        "initial_buy_price": fill_price,
                        "operator_initiated": _operator_initiated,
                    })

                self._fold_queue_usd = sum(
                    t["usd"] for t in self._fold_tranches)

                msg = (f"MANUAL FIRE FOLD FILLED: {fill_amount:.6f} @ "
                       f"${fill_price:.8f}. Discharged "
                       f"{len(consumed)} tranche(s) bypassing MEM-171 "
                       f"gates (operator override).")
            else:
                # Q2 = proceed, open new lot, mark operator_initiated
                # per caller_intent (v3.23.2: routed from caller, not
                # hard-coded True).
                self._main_lots.append({
                    "units": fill_amount,
                    "initial_buy_price": fill_price,
                    "operator_initiated": _operator_initiated,
                })
                msg = (f"MANUAL FIRE FOLD FILLED: {fill_amount:.6f} @ "
                       f"${fill_price:.8f}. No tranches queued; "
                       f"opened new lot (operator_initiated).")

            self._current_holdings += fill_amount
            self.stats.total_trades += 1

            # v3.23.30 — apply fold target-growth for MANUAL_FOLD /
            # CARTRIDGE_FOLD / WIRE_STACK_FOLD paths (Option B per
            # operator directive 2026-07-26). Autonomous FOLD path
            # applies growth via the same helper at ~line 7629.
            # `_manual_fold_accum_profit` was accumulated inside the
            # tranche-consumption loop above and represents the
            # USD-equivalent surplus (take × (ref − fill_price)) from
            # rebuying below sell-refs.
            _growth_applied = self._apply_fold_target_growth(
                _manual_fold_accum_profit, source=str(_fold_label))

            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(msg + f" Holdings now "
                         f"{self._current_holdings:.6f} "
                         f"(~${self._current_holdings * price * float(self._quote_to_usd or 1.0):.2f})."))
            # v3.15.50 — high-score counter.
            # v3.15.55 — fill_amount × fill_price is QUOTE units; multiply
            # by quote→USD for the true USD-denominated counter.
            self.stats.total_folded_usd += float(
                fill_amount * fill_price * float(self._quote_to_usd or 1.0))
            # v3.23.65 — Fold closes the SWOS cycle (second fold site).
            self.reset_swos_cycle()
            # v3.15.52 — record side for opposite-direction hysteresis
            self._last_trade_side = "FOLD"
            # v3.15.77 — disarm both gates after manual-fire FOLD too.
            self._reset_opposing_hysteresis_after_fill()
            self._bus.emit("trade.filled", bot_id=self.bot_id, data={
                "type": _fold_label,
                "side": "BUY",
                "amount": fill_amount,
                "price": fill_price,
                "usd": fill_amount * fill_price,
                # v3.23.30 — profit now = actual growth applied
                # (formerly hardcoded 0.0). Enables Grafana / trade.log
                # inspection of per-fold compounding, matching the
                # autonomous FOLD path's emit shape.
                "profit": _growth_applied,
                "operator_initiated": _operator_initiated,
            })
            # v3.23.11 — voting.log + gate.log snapshots at fire (D-NEW-A).
            self._emit_voting_panel_snapshot_at_fire(
                side="BUY", trade_action=str(_fold_label or "MANUAL_FOLD"))
            self._emit_gate_decision_at_fire(
                side="BUY", trade_action=str(_fold_label or "MANUAL_FOLD"))
            # v3.16.60 — PnL event for FOLD (audit completeness).
            # v3.23.2 — labels routed via caller_intent so Wire Stack
            # + Max Cartridge autonomous fires no longer mislabel as
            # MANUAL_FOLD downstream.
            try:
                self._bus.emit("pnl.event", bot_id=self.bot_id, data={
                    "kind": "FOLD",
                    "asset": self.config.target_asset,
                    "symbol": self.config.symbol,
                    "units_rebought": float(fill_amount),
                    "fill_price": float(fill_price),
                    "usd_spent": float(fill_amount * fill_price) * float(
                        self._quote_to_usd or 1.0),
                    "operator_initiated": _operator_initiated,
                    "manual_kind": _fold_label,
                })
            except Exception as _sup:  # R28-OK: PnL telemetry best-effort
                logger.debug("suppressed in %s: %s: %s", "_execute_manual_rebalance", type(_sup).__name__, _sup)
            self._last_trade_price = fill_price

    # ------------------------------------------------------------------
    # MEM-244 — Detonation (automatic harvest on higher-TF BULLISH)
    # ------------------------------------------------------------------
    async def _check_detonation_trigger(self, ticker) -> bool:
        """MEM-244 — Check higher-TF signal for detonation trigger.

        Operator directive: "Bot should detonate on 1D or higher
        Timeframe on BULLISH condition detection." Q4: "BULLISH +
        confidence >= 0.75 (high conviction only)."

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
        # v3.15.55 — quote→USD-aware comparison against anchor (USD).
        current_value = (
            self._current_holdings * price * float(self._quote_to_usd or 1.0)
        )
        if current_value <= self._anchor_target_balance:
            # Nothing above anchor to harvest
            return False

        # Rate limit: 1 check per hour
        now = time.time()
        if now - self._detonation_last_check_ts < 3600:
            return False
        self._detonation_last_check_ts = now

        # Fetch higher-TF candles
        tf = getattr(self.config, "detonation_timeframe", "1d") or "1d"
        try:
            candles = await self.exchange.get_ohlcv(
                self.config.symbol, tf, limit=100)
        except Exception as exc:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"DETONATION check: failed to fetch {tf} "
                         f"candles: {exc}. Will retry in 1h."))
            return False

        if not candles or len(candles) < 30:
            return False

        # Compute TA consensus on the higher TF
        try:
            engine = VotingEngine()
            parsed = candles_from_raw(candles)
            summary = engine.compute_all(parsed, tf)
        except Exception as exc:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"DETONATION check: TA engine failed: {exc}. "
                         f"Will retry in 1h."))
            return False

        # Operator Q4: BULLISH + confidence >= configurable threshold
        conf_min = float(getattr(
            self.config, "detonation_confidence_min", 0.75))
        is_bullish = (summary.consensus_direction == SignalDirection.BULLISH
                      and summary.consensus_confidence >= conf_min)

        # Edge-trigger detection
        fired = is_bullish and not self._detonation_last_signal_bullish
        self._detonation_last_signal_bullish = is_bullish

        if fired:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"DETONATION TRIGGERED: {tf} BULLISH at "
                         f"confidence {summary.consensus_confidence:.2f} "
                         f"(>={conf_min:.2f}). Harvesting everything "
                         f"above anchor ${self._anchor_target_balance:.2f}."))
        elif is_bullish:
            # Already-bullish state; log-throttle one sitrep
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"DETONATION: {tf} still BULLISH conf="
                         f"{summary.consensus_confidence:.2f}; no "
                         f"edge transition, holding."))

        return fired

    def clear_fold_tranches(self, reason: str = "operator") -> dict:
        """Discard every queued fold tranche. Trades nothing.

        v3.24.44 — operator directive 2026-08-06: "let's just clear the
        existing tranche values and assume them as invalid. They were
        calculated without any outgoing safety rate math, have languished
        for weeks in some cases, and just need to be produced fresh."

        WHAT THIS DOES NOT TOUCH, deliberately:
          * holdings, `_main_lots`, or any position — nothing is sold or
            bought, no order is placed
          * `_target_balance` or `_anchor_target_balance` — unlike
            detonation's full reset, the target is left exactly where it
            is
          * `_pending_wire_credits` — that is real routed income, not a
            tranche. See the warning below.

        THE PENDING-CREDIT INTERACTION. The park/absorb outlet at the
        scrum site is gated on the bot holding ZERO tranches. Clearing
        therefore OPENS that window on any bot that has parked credits,
        and the absorb dumps the entire pool into ONE tranche with no
        split and no cap reference. On a bot with $342 parked against a
        $2.50 cycle cap that mints a single tranche 137x over cap, which
        the fold filter can never admit. So a caller that clears a bot
        with parked credits must surface the amount and the consequence;
        the report returned here carries it for exactly that purpose.

        COUNTER SEMANTICS. Discarded tranches are counted in
        `_tranches_discarded_lifetime`, NOT in `_tranches_closed_lifetime`.
        A closed tranche is one that FOLDED. The self-destruct path at
        :2988 conflates the two, which is why "created minus closed" has
        never reconciled against the standing count. Keeping them
        separate preserves created - closed - discarded = standing.

        Returns a report of what was discarded. Never raises.
        """
        tranches = list(self._fold_tranches or [])
        report = {
            "bot_id": self.bot_id,
            "symbol": getattr(self.config, "symbol", ""),
            "count": len(tranches),
            "usd": round(sum(float(t.get("usd", 0) or 0)
                             for t in tranches), 8),
            "units": round(sum(float(t.get("units", 0) or 0)
                               for t in tranches), 8),
            "pending_wire_credits": round(
                float(getattr(self, "_pending_wire_credits", 0.0) or 0.0), 8),
            "reason": str(reason),
        }
        if not tranches:
            return report

        self._fold_tranches = []
        self._fold_queue_usd = 0.0
        self._tranches_discarded_lifetime = int(
            getattr(self, "_tranches_discarded_lifetime", 0) or 0
        ) + report["count"]

        try:
            self.stats.tranches_discarded_lifetime = (
                self._tranches_discarded_lifetime)
        except Exception as exc:  # noqa: BLE001 - telemetry mirror only
            logger.debug("clear_fold_tranches: stats mirror failed: %s", exc)

        try:
            _warn = ""
            if report["pending_wire_credits"] > 1e-9:
                _warn = (f" WARNING: ${report['pending_wire_credits']:.4f} "
                         f"of pending wire credits remain parked, and "
                         f"clearing has OPENED the absorb window — the "
                         f"next scrum will dump all of it into a single "
                         f"tranche.")
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"FOLD TRANCHES CLEARED ({reason}): discarded "
                         f"{report['count']} tranche(s) holding "
                         f"${report['usd']:.4f} against "
                         f"{report['units']:.8f} units. No trade was "
                         f"placed; holdings and target balance are "
                         f"unchanged.{_warn}"))
        except Exception as exc:  # noqa: BLE001 - diagnostic best-effort
            logger.debug("clear_fold_tranches: log emit failed: %s", exc)

        logger.info(
            "Bot %s: cleared %d fold tranche(s) ($%.4f, %.8f units) "
            "reason=%s pending_wire_credits=$%.4f",
            self.bot_id, report["count"], report["usd"], report["units"],
            reason, report["pending_wire_credits"])
        return report

    def clear_pending_wire_credits(self, reason: str = "operator") -> dict:
        """Discard this bot's parked wire credits. Trades nothing.

        v3.24.45 — operator directive 2026-08-06: "Languishing wire
        credits can also be cleared. These too were not calculated using
        outgoing safety rate math."

        WHAT THIS NUMBER IS, and why discarding it destroys nothing.
        `_pending_wire_credits` is BOOKKEEPING, not custody. Verified by
        reading every writer: the park site at :2145 is `+= u` and a
        ledger append, and no code path anywhere places an order,
        withdraws, or transfers exchange funds on the strength of it.
        All bots share one exchange wallet, so a Smart Wire route is an
        accounting reallocation of a claim on shared cash — the source
        bot already gave the claim up at the scrum site. Clearing the
        credit releases the earmark; the cash stays in the wallet as
        ordinary spendable balance.

        WHY IT MATTERS THAT THIS EXISTS. The park/absorb outlet is gated
        on the bot holding ZERO tranches, so it opens only in a window
        the bot usually leaves immediately, and the absorb dumps the
        whole pool into ONE tranche with no split and no cap reference.
        Live: BTC/USD parked $342.26 against a $2.50 cycle cap. Clearing
        tranches alone would OPEN that window; clearing both closes the
        trap rather than arming it.

        Returns a report of what was discarded. Never raises.
        """
        amount = float(getattr(self, "_pending_wire_credits", 0.0) or 0.0)
        ledger = list(getattr(self, "_pending_wire_ledger", []) or [])
        report = {
            "bot_id": self.bot_id,
            "symbol": getattr(self.config, "symbol", ""),
            "usd": round(amount, 8),
            "ledger_entries": len(ledger),
            "reason": str(reason),
        }
        if amount <= 1e-9 and not ledger:
            return report

        self._pending_wire_credits = 0.0
        self._pending_wire_ledger = []
        self._wire_credits_discarded_lifetime = round(float(
            getattr(self, "_wire_credits_discarded_lifetime", 0.0) or 0.0
        ) + amount, 8)

        try:
            self.stats.wire_credits_discarded_lifetime = (
                self._wire_credits_discarded_lifetime)
        except Exception as exc:  # noqa: BLE001 - telemetry mirror only
            logger.debug(
                "clear_pending_wire_credits: stats mirror failed: %s", exc)

        try:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"WIRE CREDITS CLEARED ({reason}): discarded "
                         f"${amount:.4f} of parked credit across "
                         f"{len(ledger)} ledger entrie(s). This releases "
                         f"an earmark only — no order was placed and no "
                         f"funds moved; the cash remains in the wallet "
                         f"as spendable balance."))
        except Exception as exc:  # noqa: BLE001 - diagnostic best-effort
            logger.debug(
                "clear_pending_wire_credits: log emit failed: %s", exc)

        logger.info(
            "Bot %s: cleared $%.4f pending wire credits (%d ledger "
            "entries) reason=%s",
            self.bot_id, amount, len(ledger), reason)
        return report

    # ------------------------------------------------------------------
    # Item 9 (2026-08-13) — TRANCHE DESPAWN TIMER
    # ------------------------------------------------------------------
    @staticmethod
    def _tranche_age_seconds(
            tranche: dict, field: str, now: float) -> Optional[float]:
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

        A NON-POSITIVE STAMP IS ALSO NO STAMP. Zero is the epoch, which
        no real tranche carries and which every threshold would delist;
        it means "unset". A negative one is not a time at all.

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

        Operator spec 2026-08-13: "We can also add a tranche despawn
        timer that delists aged tranches from the tracker." With the
        governing principle of the same day — "Functionality should be
        mirrored between either side of the ladder" — that is ONE
        setting driving ONE sweep over BOTH ledgers: fold tranches by
        ``created_ts``, stack tranches by ``opened_ts``.

        ONE VERB: DELIST. This places no order, cancels no order, moves
        no balance, and touches no holding, no ``_main_lots`` entry, no
        target and no anchor. A tranche is a record and not a lock — no
        tokens are reserved behind one and no market position is taken
        by one — so dropping it frees nothing and strands nothing.

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

        AN AGELESS TRANCHE IS NEVER DELISTED. A pre-v3.16.39 fold
        tranche carries no ``created_ts`` at all and the panel prints an
        em dash for its age. This timer delists on MEASURED age; with no
        measurement there is nothing to compare, and reading "unknown"
        as "old" would silently bulk-delete every undated record on the
        first tick after the operator switched the setting on. A
        future-dated stamp needs no special case either: it yields a
        negative age, younger than every threshold.

        THE BOUNDARY IS INCLUSIVE: ``age >= threshold`` delists, so a
        tranche exactly at the threshold is old enough.

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
            return report           # off, and off is the default

        _now = time.time() if now is None else as_finite_float(now)
        if _now is None:
            logger.warning(
                "Bot %s: despawn sweep delisted nothing — `now` was %r, "
                "which is not a finite number, so no age is measurable",
                self.bot_id, now)
            return report
        _cutoff = _days * 86400.0

        _fold_keep = []
        for _t in (self._fold_tranches or []):
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
        for _t in (self._stack_tranches or []):
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
            return report           # nothing aged out; stay silent

        if report["fold_delisted"]:
            self._fold_tranches = _fold_keep
            self._fold_queue_usd = sum(
                (as_finite_float(_t.get("usd", 0)) or 0.0)
                for _t in self._fold_tranches)
            self._tranches_discarded_lifetime = int(
                as_finite_float(
                    getattr(self, "_tranches_discarded_lifetime", 0))
                or 0.0
            ) + report["fold_delisted"]
            try:
                self.stats.tranches_discarded_lifetime = (
                    self._tranches_discarded_lifetime)
            except AttributeError as exc:
                logger.debug("despawn: stats mirror failed: %s", exc)
        if report["stack_delisted"]:
            self._stack_tranches = _stack_keep
            # Item 9 — the stack ledger records its own delists, exactly
            # as the fold ledger above records its own. Without this the
            # sweep dropped stack tranches while `_stack_created` kept
            # climbing, so `created - discarded == standing` failed on
            # this side alone and the Stack panel's fill ratio fell with
            # nothing on screen to explain it.
            self._stack_discarded = int(
                as_finite_float(getattr(self, "_stack_discarded", 0))
                or 0.0
            ) + report["stack_delisted"]

        # The same trap `clear_fold_tranches` documents: the park/absorb
        # outlet is gated on the bot holding ZERO tranches, so a sweep
        # that empties the fold queue OPENS it, and the absorb dumps the
        # whole parked pool into one tranche with no split and no cap
        # reference. Saying so is a log line, not a behaviour change —
        # this method still does not touch that pool.
        _parked = as_finite_float(
            getattr(self, "_pending_wire_credits", 0.0)) or 0.0
        _warn = ""
        if not self._fold_tranches and _parked > 1e-9:
            _warn = (f" WARNING: ${_parked:.4f} of pending wire credits "
                     f"remain parked and the fold queue is now empty, "
                     f"which has OPENED the absorb window — the next "
                     f"scrum will dump all of it into a single tranche.")
        _skipped = ""
        if report["stack_kept_live_order"]:
            _skipped = (f" {report['stack_kept_live_order']} aged stack "
                        f"tranche(s) KEPT: they hold resting exchange "
                        f"orders, and delisting a record that owns a "
                        f"live order would strand it.")
        try:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"TRANCHES DESPAWNED (>= {_days}d): delisted "
                         f"{report['fold_delisted']} fold tranche(s) "
                         f"holding ${report['usd_delisted']:.4f} and "
                         f"{report['stack_delisted']} stack tranche(s). "
                         f"No order was placed or cancelled; holdings, "
                         f"cost basis and target balance are "
                         f"unchanged.{_skipped}{_warn}"))
        except AttributeError as exc:
            logger.debug("despawn: log emit failed: %s", exc)

        logger.info(
            "Bot %s: despawned %d fold + %d stack tranche(s) at >= %d "
            "days (kept %d ageless, %d with live orders)",
            self.bot_id, report["fold_delisted"], report["stack_delisted"],
            _days, report["ageless_kept"],
            report["stack_kept_live_order"])
        return report

    async def _execute_detonation(self, ticker) -> None:
        """MEM-244 — Execute the detonation harvest.

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
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message="DETONATION: no valid price; aborting.")
            return

        # v3.15.55 — quote→USD-aware. excess_usd is USD; sell_amount must
        # be in BASE units, so we divide by (price × quote_to_usd) to go
        # from USD → quote-units → base-units.
        _qrate = float(self._quote_to_usd or 1.0)
        current_value = self._current_holdings * price * _qrate
        excess_usd = current_value - self._anchor_target_balance
        if excess_usd <= 0:
            return  # should not happen (guarded in _check_detonation_trigger)

        # USD → BASE: USD / (quote_per_base × USD_per_quote) = base.
        sell_amount = excess_usd / (price * _qrate) if (price * _qrate) > 0 else 0.0
        sell_amount = min(sell_amount, self._current_holdings)
        if sell_amount <= 0:
            return

        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"DETONATION HARVEST: value=${current_value:.2f}, "
                     f"anchor=${self._anchor_target_balance:.2f}, "
                     f"selling {sell_amount:.6f} "
                     f"{self.config.symbol.split('/')[0]} @ MARKET "
                     f"(~${price:.8f}) to lock in "
                     f"${excess_usd:.2f} gains."))

        order = await self.guarded_place_order(
            symbol=self.config.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=sell_amount,
            price=None,
        )

        if order is None:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message="DETONATION: exchange returned no order.")
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
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=("DETONATION: order placed but no filled "
                         "amount reported. Check exchange for actual "
                         "state."))
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

        # Decrement holdings
        self._current_holdings = max(
            0.0, self._current_holdings - fill_amount)

        # v3.16.51 — Smart Wire SCRUM-time routing on Detonation harvest.
        # Detonation is the maturity profit-taking event (MEM-244 — bot
        # value exceeded Smart Ceiling on a bullish higher-TF vote, sell
        # everything above anchor). The harvested USD is realised gain
        # by definition; route a share to wired bots so cross-compounding
        # benefits from the harvest event the same way it benefits from
        # autonomous and manual SCRUMs. Pre-v3.16.51 detonation bypassed
        # the wire system entirely.
        _detonation_routed_total = self._route_scrum_proceeds_via_wires(
            scrum_usd=fill_usd,
            sell_fill=fill_price,
            label="detonation")
        # v3.16.60 — PnL event for Detonation harvest (audit completeness).
        # This is the maturity-event harvest — the operator-set Smart
        # Ceiling fired with bullish higher-TF vote. realised USD = full
        # fill_usd (minus wire-routed portion).
        try:
            _detonation_kept = float(fill_usd) - float(
                _detonation_routed_total or 0.0)
            self._bus.emit("pnl.event", bot_id=self.bot_id, data={
                "kind": "SCRUM",
                "asset": self.config.target_asset,
                "symbol": self.config.symbol,
                "units": float(fill_amount),
                "fill_price": float(fill_price),
                "usd_captured": _detonation_kept * float(
                    self._quote_to_usd or 1.0),
                "usd_routed_via_wires": float(
                    _detonation_routed_total or 0.0) * float(
                    self._quote_to_usd or 1.0),
                "operator_initiated": False,
                "manual_kind": "DETONATION",
            })
        except Exception as _sup:  # R28-OK: PnL telemetry best-effort
            logger.debug("suppressed in %s: %s: %s", "_execute_detonation", type(_sup).__name__, _sup)
        # Note: detonation proceeds aren't held in fold tranches (the
        # full reset clears them below), so the routed amount simply
        # goes OUT to wires; the remainder becomes "wallet realised
        # gain" via the normal post-fill semantic (wallet balance is
        # exchange-authoritative — no internal bookkeeping required).

        # FULL RESET per operator Q: lock in gains means target back
        # to anchor, fold queue cleared, _main_lots reseeded to
        # remaining holdings at current price (fresh cost basis for
        # whatever is still in position after harvest).
        prior_target = self._target_balance
        self._target_balance = self._anchor_target_balance
        # v3.24.51 (Phase 2 Step 6) — this clear bumped no counter at
        # all, so a detonation silently broke the tranche accounting: the
        # created total kept climbing while the standing count dropped to
        # zero with nothing to explain the gap.
        #
        # DEVIATION FROM THE REPAIR PLAN, deliberate. The plan says bump
        # `_tranches_closed_lifetime`, matching the two other bulk
        # clears. These tranches did NOT fold — detonation sells the
        # position and abandons the queued rebuys — and v3.24.44
        # established that `closed` means "actually folded", which is
        # what makes created - closed - discarded = standing meaningful.
        # Counting an abandoned tranche as closed would re-introduce the
        # exact conflation that split was for. They are DISCARDED.
        _detonated_tranches = len(self._fold_tranches)
        if _detonated_tranches:
            self._tranches_discarded_lifetime = int(
                getattr(self, "_tranches_discarded_lifetime", 0) or 0
            ) + _detonated_tranches
        self._fold_tranches.clear()
        self._fold_queue_usd = 0.0
        # The standing pool must not survive the reset. Detonation puts
        # the target back to anchor by design, so carrying pre-detonation
        # surplus forward would inject it into a post-detonation target —
        # growth earned against a position that no longer exists. Matters
        # from Phase 2 Step 7 onward, when this pool acquires a drain.
        _detonated_surplus = float(
            getattr(self, "_standing_surplus_usd", 0.0) or 0.0)
        self._standing_surplus_usd = 0.0
        try:
            self.stats.standing_surplus_usd = 0.0
        except Exception as _sp_exc:  # noqa: BLE001 - telemetry mirror
            logger.debug("detonation surplus mirror failed: %s", _sp_exc)
        # NOT cleared here: _fold_cycle_cap_consumed. Zeroing it would
        # unlatch folds, which is a buy-timing change and belongs in
        # Phase 3 Step 13.

        # Rebuild main_lots to match remaining holdings with
        # current price as new cost basis (fresh tracking — any
        # remaining holdings are now "at anchor")
        self._main_lots.clear()
        if self._current_holdings > 0:
            self._main_lots.append({
                "units": self._current_holdings,
                "initial_buy_price": fill_price,
                "auto_detonated_reset": True,
            })

        self.stats.total_trades += 1
        self._last_trade_price = fill_price

        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"DETONATION COMPLETE: filled {fill_amount:.6f} @ "
                     f"${fill_price:.8f} = ${fill_usd:.2f}. "
                     f"target_balance reset ${prior_target:.2f} → "
                     f"${self._anchor_target_balance:.2f} (anchor). "
                     f"Fold queue cleared. Bot will re-accumulate "
                     f"from scratch on next dip."))

        self._bus.emit("trade.filled", bot_id=self.bot_id, data={
            "type": "AUTO_DETONATION",
            "side": "SELL",
            "amount": fill_amount,
            "price": fill_price,
            "usd": fill_usd,
            "profit": excess_usd,  # realized gain locked in
            "auto_detonated": True,
            "anchor": self._anchor_target_balance,
        })
        # v3.23.11 — voting.log + gate.log snapshots at fire (D-NEW-A).
        self._emit_voting_panel_snapshot_at_fire(
            side="SELL", trade_action="AUTO_DETONATION")
        self._emit_gate_decision_at_fire(
            side="SELL", trade_action="AUTO_DETONATION")

    # -------------------------------------------------------------------
    # v3.23.27 -- Stack Mode helpers (Invisible-mode Stack execution).
    # v3.23.44 -- split into the operator's two stages.
    #
    # `_open_stack_from_scrum` intercepts a SCRUM decision and, instead of
    # firing one sell, splits the size into N tranches at ascending prices
    # per the operator's split spec. Tranches are stored in
    # `self._stack_tranches` (see __init__) as dict entries:
    #   {"index": int, "price": float, "size": float,
    #    "status": "pending"|"filled"|"cancelled", "opened_ts": float,
    #    "activated": bool, "activated_ts": float}
    #
    # Invisible mode is TWO STAGES, per operator directive 2026-08-11:
    #   1. `_reconcile_stack_tranches_invisible` runs at the top of every
    #      tick and ACTIVATES any pending tranche whose price the market
    #      has crossed. It places no order. `status` stays "pending".
    #   2. `_spend_activated_stack_tranches` runs inside the SCRUM gate
    #      chain's should_fire block and SPENDS activated tranches via
    #      `_execute_sell(..., bypass_stack=True)`, so the stack branch
    #      in `_execute_sell` is skipped for the actual order.
    #
    # A tranche therefore never confers authority to trade that the bot
    # does not already have this tick. A refused tick leaves the tranche
    # pending and activated for the next authorised one.
    #
    # Visible mode is unchanged and needs no such split: the gates are
    # evaluated once at placement time (`guarded_place_order` under
    # `if _visible:` below, reachable only from the gated scrum sell),
    # the EXCHANGE fills the resting LIMIT order, and
    # `_reconcile_stack_tranches_visible` only READS exchange state.
    # -------------------------------------------------------------------

    async def _open_stack_from_scrum(
        self, scrum_price: float, scrum_size: float,
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

        v3.23.28 — now async. In Visible mode (not self._invisible),
        places a LIMIT (or IOC_LIMIT if Aggressive) SELL order on the
        exchange for each tranche and records the returned order_id.
        In Invisible mode, tranches are stored with order_id=None and
        fire on price crossing via the invisible reconciler."""
        from .stack_math import split_scrum_into_tranches  # local import: keep module load light

        # Minimum Opposing Trade Distance = scrumming_interval_pct + trading_fee_pct
        # (matches the hysteresis reference used elsewhere in this file).
        _interval = float(getattr(self.config, "scrumming_interval_pct", 0) or 0)
        _fee = float(getattr(self.config, "trading_fee_pct", 0.6) or 0.6)
        min_opposing_pct = _interval + _fee

        n_target = int(getattr(self.config, "stack_tranche_count_target", 3) or 3)
        split_dist = float(getattr(self.config, "split_distance_pct", 1.0) or 1.0)
        spacing = str(getattr(self.config, "stack_spacing_mode", "linear") or "linear")
        min_order = float(getattr(self.exchange_interface, "min_order_size", 0.0) or 0.0)

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
            # sadp: R28 CBF — surface loudly, refuse silent bypass.
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"STACK OPEN FAILED: split_scrum_into_tranches "
                         f"rejected inputs: {e}. Stack not opened."))
            logger.warning("Bot %s stack open failed: %s", self.bot_id, e)
            return 0

        import time as _t
        now = _t.time()
        # Record the opening vote on every tranche. This is a FORENSIC
        # RECORD of what opened the Stack -- what TA said at stack-open
        # time -- and nothing more. It is not authority to close it.
        # `_spend_activated_stack_tranches` passes the LIVE VotingSummary
        # from the tick that authorises the spend, and falls back to this
        # record only when a caller supplies no live vote (which keeps
        # `_execute_sell` from raising AttributeError on
        # `summary.consensus_confidence` before it places the order --
        # the v3.23.43 defect that made every Invisible tranche
        # unfireable).
        try:
            _open_conf = float(getattr(summary, "consensus_confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            _open_conf = 0.0
        _open_dir = str(getattr(summary, "consensus_direction", "stack") or "stack")
        # v3.23.28 — Visible mode: place LIMIT (or IOC_LIMIT under
        # Aggressive) sell orders on the book at each tranche price.
        # Invisible mode: no exchange call — the invisible reconciler
        # fires each tranche on price crossing via MARKET.
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
                # item 7 -- which side of the pair opened this stack.
                # Additive: `export_scrumming_state` copies each entry
                # with `dict(_t)`, so it round-trips a restart, and no
                # existing reader indexes it.
                "origin": origin,
                "order_id": None,           # Visible: exchange order id; Invisible: None
                "visible": _visible,        # freeze placement mode for reconciler routing
                "open_confidence": _open_conf,  # opening vote, replayed at fire time
                "open_direction": _open_dir,
                # v3.23.44 -- two-stage Stack. `activated` is set by
                # `_reconcile_stack_tranches_invisible` when the market
                # crosses `price`. It makes the tranche a CANDIDATE;
                # spending it still requires the SCRUM gate chain to
                # authorise a sell on the tick it is spent.
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
                        # Placement returned None — mark tranche cancelled
                        # so it doesn't sit in "pending" forever with no
                        # exchange counterpart.
                        entry["status"] = "cancelled"
                        entry["cancel_reason"] = "exchange returned no order"
                except Exception as _place_exc:  # sadp: R28 CBF
                    logger.warning(
                        "Bot %s stack tranche %d placement failed: %s",
                        self.bot_id, t.index, _place_exc)
                    entry["status"] = "cancelled"
                    entry["cancel_reason"] = (
                        f"{type(_place_exc).__name__}: {_place_exc}")
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                        message=(f"STACK TRANCHE {t.index} PLACEMENT FAILED: "
                                 f"{entry['cancel_reason']}. "
                                 f"Tranche cancelled."))
            self._stack_tranches.append(entry)
            self._stack_created += 1

        _mode_label = "VISIBLE" if _visible else "INVISIBLE"
        _agg_label = " (AGGRESSIVE/IOC)" if _visible and _aggressive else ""
        self._bus.emit("bot.log", bot_id=self.bot_id,
            message=(f"STACK OPENED [{_mode_label}{_agg_label}] "
                     f"({len(tranches)} tranches) from {origin} @ "
                     f"${scrum_price:.8f}, size {scrum_size:.6f}. "
                     f"Prices: {[f'${t.price:.8f}' for t in tranches[:5]]}"
                     f"{'…' if len(tranches) > 5 else ''}"))
        return len(tranches)

    async def _reconcile_stack_tranches_visible(self) -> int:
        """v3.23.28 — Visible-mode Stack reconciliation.

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
            t for t in self._stack_tranches
            if t.get("status") == "pending"
            and t.get("visible")
            and t.get("order_id")
        ]
        if not pending_visible:
            return 0
        if not hasattr(self.exchange, "get_open_orders"):
            return 0

        try:
            open_orders = await self.exchange.get_open_orders(
                symbol=self.config.symbol)
        except Exception as exc:  # sadp: R28 CBF
            logger.warning(
                "Bot %s stack visible reconcile: get_open_orders failed: %s",
                self.bot_id, exc)
            return 0

        open_ids = {getattr(o, "id", None) for o in (open_orders or [])}
        settled = 0
        for t in pending_visible:
            oid = t["order_id"]
            if oid in open_ids:
                continue  # still resting on the book
            # Order no longer open — fetch terminal state
            try:
                order = await self.exchange.get_order(
                    order_id=oid, symbol=self.config.symbol)
            except Exception as exc:  # sadp: R28 CBF
                logger.warning(
                    "Bot %s stack visible reconcile: get_order(%s) failed: %s",
                    self.bot_id, oid, exc)
                continue
            status = getattr(order, "status", None)
            status_val = getattr(status, "value", status)
            _filled = float(getattr(order, "filled", 0) or 0)
            _avg = (getattr(order, "average", None)
                    or getattr(order, "price", None) or t["price"])
            if _filled > 0:
                t["status"] = "filled"
                t["fill_price"] = float(_avg or t["price"])
                t["filled_amount"] = _filled
                settled += 1
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"STACK TRANCHE {t['index']} FILLED [VISIBLE] "
                             f"@ ${float(_avg or t['price']):.8f} "
                             f"({_filled:.6f}/{t['size']:.6f})"))
            else:
                # Order closed with no fill — probably cancelled externally.
                t["status"] = "cancelled"
                t["cancel_reason"] = f"exchange status={status_val!r}, filled=0"
                settled += 1
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"STACK TRANCHE {t['index']} CANCELLED "
                             f"externally (order {oid} closed with 0 fill)"))
        return settled

    async def _reconcile_stack_tranches_invisible(self, current_price: float) -> int:
        """STAGE ONE of the two-stage Stack rule: a crossed price
        threshold ACTIVATES a tranche. It does not spend it.

        Operator directive 2026-08-11, verbatim: "A price threshold being
        passed activates the tranche which allows it to be spent when the
        trading condition manifests", and "tranches do not supersede any
        trading gates. They are only 'used' when a valid trading condition
        occurs."

        This method runs at the TOP of `tick`, before the SCRUM gate chain
        is built or evaluated and before nine pre-chain returns that end
        the tick outright. Until v3.23.44 it called `_execute_sell` from
        here, so a MARKET sell could leave the bot on a tick where the
        chain would have refused, or where the chain was never reached.
        Nothing this method tests is a trading gate: Invisible mode,
        `stack_mode`, a non-empty ledger, a positive price, and the
        tranche's own threshold. Marking is therefore all it may do.

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
                continue        # already a candidate; re-crossing changes nothing
            if current_price < float(t["price"]):
                continue
            t["activated"] = True
            t["activated_ts"] = _t.time()
            t["activated_price"] = float(current_price)
            activated += 1
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"STACK TRANCHE {t['index']} ACTIVATED @ "
                         f"${float(current_price):.8f} (threshold "
                         f"${float(t['price']):.8f}, size "
                         f"{float(t['size']):.6f}). Candidate only -- it is "
                         f"spent when the SCRUM gate chain authorises a "
                         f"sell, and not before."))
        return activated

    async def _spend_activated_stack_tranches(
        self, current_price: float,
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
                    consensus_confidence=float(
                        t.get("open_confidence", 0.0) or 0.0),
                    consensus_direction=str(
                        t.get("open_direction", "stack") or "stack"),
                )
            try:
                fill = await self._execute_sell(
                    amount=float(t["size"]),
                    price=float(current_price),
                    summary=_vote,
                    bypass_stack=True,
                )
            except Exception as exc:  # sadp: R28 CBF -- surface loudly
                logger.warning(
                    "Bot %s stack tranche %s spend raised: %s",
                    self.bot_id, t.get("index"), exc)
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"STACK TRANCHE {t['index']} SPEND FAILED: "
                             f"{type(exc).__name__}: {exc}. Tranche stays "
                             f"pending and activated -- retried on the next "
                             f"authorised tick."))
                continue
            if fill is None or float(fill) <= 0:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"STACK TRANCHE {t['index']} NOT SPENT: "
                             f"_execute_sell returned no fill. Tranche stays "
                             f"pending and activated -- retried on the next "
                             f"authorised tick."))
                continue
            t["status"] = "filled"
            t["fill_price"] = float(fill)
            spent += 1
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"STACK TRANCHE {t['index']} SPENT @ "
                         f"${float(fill):.8f} (threshold "
                         f"${float(t['price']):.8f}, size "
                         f"{float(t['size']):.6f}) under an authorised "
                         f"SCRUM gate-chain decision."))
        return spent

    async def _execute_sell(
        self, amount: float, price: float, summary: VotingSummary,
        bypass_stack: bool = False,
    ) -> Optional[float]:
        """Execute a sell order. Returns actual fill price captured from
        the exchange response (or the intended price if the response
        lacks detail). v3.13.8 MEM-190 / Chunk 6: fill-price capture
        replaces the sim's slip_pct_fn microstructure simulation — the
        real exchange provides real slippage, the bot just needs to
        surface it to downstream state (_last_trade_price, tranche refs,
        etc.) so band-travel and profit computations use the real fill
        rather than the intended price.

        v3.23.27 -- bypass_stack: when True, skip the Stack Mode branch
        below. Used by `_spend_activated_stack_tranches` (v3.23.44) when
        it spends an activated tranche, so we do not re-open a stack on
        top of a stack. Default False keeps every other caller on the
        original semantics."""
        # sadp: R1 R5 R28 R29 R33 R55 R57  # scrum-sell + Verify Hit pre-gate

        # ============================================================
        # v3.23.27 -- Stack Mode intercept. If enabled AND we are not
        # already spending a stack tranche (bypass_stack=False), replace
        # this single sell with a Stack of N tranches at ascending prices.
        # v3.23.44: `_reconcile_stack_tranches_invisible` ACTIVATES each
        # tranche in a later tick when its price threshold is crossed, and
        # `_spend_activated_stack_tranches` spends it on the next tick the
        # SCRUM gate chain authorises a sell. Returns a sentinel non-None
        # to signal "handled" without emitting a fill price the caller can
        # rely on.
        # ============================================================
        if (not bypass_stack
                and getattr(self.config, "stack_mode", False)
                and amount and amount > 0 and price and price > 0):
            _n = await self._open_stack_from_scrum(
                scrum_price=float(price),
                scrum_size=float(amount),
                summary=summary,
            )
            # If _open_stack_from_scrum couldn't build any tranches
            # (invalid inputs / all merged / all below min_order_size),
            # fall through to the single-sell path below rather than
            # silently swallowing the SCRUM.
            if _n > 0:
                return None

        # ============================================================
        # v3.15.77 — Conditional opposing-direction hysteresis.
        # ============================================================
        # Operator directive 2026-04-27 (refines v3.15.52):
        #   "The opposing trade distance should not activate after one
        #    trade. The opposing directional movement should be
        #    confirmed first i.e. once the Target Delta begins drifting
        #    [in the opposing direction] from the most recent [trade].
        #    If the Target Delta goes [back] again, it can deactivate."
        #
        # Active only when `_hyst_armed_scrum_side` is True (set by
        # _update_opposing_hysteresis_state when delta crossed positive
        # after the last FOLD). The reference price is the pivot
        # captured at the moment of arming, NOT the original FOLD
        # price. In an oscillating market the gate flickers on/off as
        # delta crosses zero — this is by design.
        # Manual fire bypasses (uses guarded_place_order).
        # sadp: R28 FL R17 R29 R44
        if (self._hyst_armed_scrum_side
                and self._hyst_ref_scrum_side > 0
                and getattr(self.config, "scrumming_interval_pct", 0) > 0):
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
                    / self._hyst_ref_scrum_side * 100.0)
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"SCRUM REFUSED (opposing hysteresis v3.15.77): "
                             f"pivot ref ${self._hyst_ref_scrum_side:.8f} "
                             f"(captured when Δ crossed positive after recent "
                             f"FOLD), current ${_px_check:.8f} "
                             f"(only {_rise_pct:+.2f}% from pivot). "
                             f"Need ≥ {_eff_pct:.2f}% rise "
                             f"(interval {_interval:.2f}% + fee {_fee:.2f}%; "
                             f"price ≥ ${_required_min:.8f}) before "
                             f"SCRUM can fire."))
                self._emit_trade_notification(
                    "SCRUM", "CANCELLED",
                    f"hysteresis (need ≥ {_eff_pct:.2f}% rise)")
                return None

        # ============================================================
        # v3.20.2 — CAPITAL RESERVATION REGISTRY (PRIMARY decision gate).
        # ============================================================
        # Operator directive 2026-05-23:
        #   "If I have a $100 ETH Extractor running then this field will
        #    tell the Scrumming Bot to start ignoring $100 of the ETH
        #    budget. Similarly, when an Extractor Bot is created its own
        #    field populates with the amount of the Base Currency being
        #    used by any other bots so that there is no predation at any
        #    phase of these two or future bot types predating each
        #    others' resources."
        #
        # This is the PRIMARY enforcement gate. The complementary BACKSTOP
        # at smart_orders.execute() (v3.20.1) catches anything that slips
        # past this check. By gating HERE, the bot never even forms the
        # INTENT to sell beyond what other bots have left available — the
        # decision-level math is correct on every tick.
        #
        # Distinct from the v3.15.56 multi-base attribution isolation:
        # that handles VERTICAL sibling-SB-on-same-asset relationships
        # (_main_lots authoritative attribution). The capital reservation
        # registry handles CROSS-BOT-TYPE relationships (SB ↔ Extractor
        # ↔ future bot types) where each kind of bot has its own claim
        # mechanics.
        #
        # Failure modes covered:
        #   - Registry call raises → log + fall through (smart_orders
        #     backstop is still in effect; we don't cripple all trading
        #     on a registry bug). R28 FL via debug log.
        #   - effective_available == amount within float epsilon →
        #     allowed (tolerance prevents legit trades killed by rounding).
        #   - effective_available < amount → refuse with operator-
        #     readable message naming the asset, requested-vs-available,
        #     and pointer to Settings tab for stale-reservation cleanup.
        # sadp: R28 FL  R68 DPA
        #
        # v3.24.31 — this pre-check now RUNS in sim.
        #
        # v3.24.27 skipped it entirely because the registry is a
        # process-wide singleton holding LIVE state, so a sim bot was
        # comparing live bots' claims against its own sim holdings and
        # refusing sells on that basis:
        #
        #   CRR.effective_available: 0bee0dac on ETH — others reserved
        #   0.1183015458 > total_holdings 0.08404350092. Clamping to 0.
        #
        # Skipping fixed the contamination but removed the feature,
        # which is the opposite of the operator's directive that sim
        # bots have "all of the same functionality except that operate
        # in a simulated environment." Isolation now comes from WHICH
        # registry the bot holds (see _crr()), so the real code path is
        # exercised against sim-only state.
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
                self._bus.emit("bot.log", bot_id=self.bot_id,
                               message=_crr_msg)
                self._emit_trade_notification(
                    "SCRUM", "CANCELLED",
                    f"capital reservation (avail {_crr_effective:.6f})")
                logger.info(
                    "Bot %s sell refused by capital reservation: "
                    "amount=%.6f effective=%.6f asset=%s",
                    self.bot_id, amount, _crr_effective,
                    self.config.target_asset)
                return None
        except Exception as _crr_exc:  # R28-OK: registry call defensive — smart_orders backstop still in effect
            logger.debug(
                "Bot %s capital reservation pre-check raised %s — "
                "falling through to existing gates; v3.20.1 backstop "
                "remains active.",
                self.bot_id, _crr_exc)

        # ============================================================
        # P0b STACKED-ORDER GUARD (Session 26, 2026-04-24, Layer 1).
        # ============================================================
        # Same operator directive as the BUY-side guard: refuse a second
        # SELL on the same symbol while an open SELL is in flight. Stacked
        # sells can oversell below zero if both fills land, producing an
        # exchange-side error + operator panic.
        try:
            _open = await self.exchange.get_open_orders(self.config.symbol)
        except Exception as _oo_exc:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"P0b SELL REFUSED (fail-closed): "
                         f"get_open_orders raised {type(_oo_exc).__name__}: "
                         f"{_oo_exc}. Cannot verify absence of stacked "
                         f"orders. Refusing."))
            return None
        try:
            _open_sells = [
                o for o in (_open or [])
                if getattr(o, "side", None) == OrderSide.SELL
                and getattr(o, "symbol", None) == self.config.symbol
            ]
        except Exception:  # R28-OK: side-enum filter probe; conservative all-orders fallback
            _open_sells = [
                o for o in (_open or [])
                if getattr(o, "symbol", None) == self.config.symbol
            ]
        if _open_sells:
            _ids = ", ".join(str(getattr(o, "id", "?")) for o in _open_sells[:3])
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"P0b STACKED SELL REFUSED: {len(_open_sells)} open "
                         f"SELL order(s) already on exchange for "
                         f"{self.config.symbol} (ids: {_ids}). "
                         f"Refusing to place a second SELL on top. "
                         f"Wait for existing order(s) to fill or cancel."))
            return None

        try:
            # R55 VH v3 — pre-trade gate (per R57 EPM — parity with
            # sim engines). Refuse to place the order if projected
            # slippage would breach the per-asset-class tolerance.
            # For LIMIT orders the exec_price below already includes a
            # -0.1% drift for fast fill; _verify_hit checks whether that
            # remains within class tolerance from the signaled price.
            from ..core.execution_discipline import verify_hit as _vh
            vh_fp, vh_status, vh_samples = _vh(
                price, 'sell', symbol=self.config.target_asset)
            self.stats.verify_samples += vh_samples
            if vh_fp is None:
                self.stats.verify_canceled += 1
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"SELL CANCELED (R55 VH): slippage would "
                            f"exceed {self.config.target_asset} class "
                            f"tolerance @ ${price:.8f}")
                logger.info("Bot %s VH-canceled sell of %.6f at %.4f",
                            self.bot_id, amount, price)
                return
            if vh_status == 'clean':
                self.stats.verify_clean += 1
            else:
                self.stats.verify_adjusted += 1

            # Invisible mode: ALWAYS market order (nothing on book)
            if self._invisible:
                ot = OrderType.MARKET
                exec_price = None
            else:
                ot = OrderType.LIMIT
                exec_price = vh_fp  # use VH-verified effective price

            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"SELL signal: {amount:.6f} @ ${price:.8f} "
                        f"(VH:{vh_status}, confidence="
                        f"{summary.consensus_confidence:.2f}, "
                        f"{'MARKET' if self._invisible else 'LIMIT'})")
            # v3.15.53 — trade lifecycle notification (SENT)
            self._emit_trade_notification(
                "SCRUM", "SENT",
                f"{amount:.6f} @ ${price:.8f}")

            order = await self.guarded_place_order(
                symbol=self.config.symbol,
                side=OrderSide.SELL,
                order_type=ot,
                amount=amount,
                price=exec_price,
            )

            # MEM-207 — explicit failure gate (symmetric to _execute_buy).
            # Previously the code decremented self._current_holdings
            # unconditionally, whether the exchange accepted the sell or
            # not. On a rejected sell, internal holdings would diverge
            # from exchange reality (and could go negative). Callers
            # also had the `if fill is None: fill = ticker.last` fallback
            # anti-pattern that treated failure as success. Failure path:
            # no state update, no SELL FILLED log, no trade.filled emit,
            # return None so the caller sees the signal.
            if order is None:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(
                        f"SELL ABORTED: exchange/guard returned no order for "
                        f"{amount:.6f} {self.config.target_asset} @ "
                        f"${price:.8f}. No state update. Caller must not "
                        f"treat this as success."))
                logger.warning(
                    "Bot %s sell aborted (order None) for %.6f at %.4f",
                    self.bot_id, amount, price)
                # MEM-208 — failed trade is a prime drift moment. Reconcile
                # immediately so any accumulated divergence surfaces now
                # rather than waiting for the periodic cycle.
                try:
                    await self._reconcile_holdings(reason="post_failure")
                except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                    logger.debug("suppressed in %s: %s: %s", "_execute_sell", type(_sup).__name__, _sup)
                return None

            # --- Success path: order is truthy ---
            self._current_holdings -= amount
            self.stats.total_sells += 1
            self.stats.total_trades += 1

            # v3.13.8 MEM-190 / Chunk 6 — capture actual fill price.
            # DPA: CCXT-001 exception — Order.average may be None on
            # some exchanges; fall back to order.price. Safe fallback
            # (order is known-truthy here), distinct from the MEM-207
            # anti-pattern of treating None-order as success.
            actual_fill = getattr(order, 'average', None) or getattr(order, 'price', None)
            if not actual_fill or actual_fill <= 0:
                actual_fill = price
            slippage_pct = ((actual_fill - price) / price * 100.0) if price > 0 else 0.0

            self.stats.trade_volume += amount * actual_fill
            self.stats.last_trade_time = time.time()

            # v3.23.78 — per-trade YTD Scrummed USD increment.
            # sync_ytd_trade_count's docstring (line 3717) claimed
            # "subsequent per-trade increments continue via the normal
            # execute-buy / execute-sell paths" — but those increments
            # were never wired. Result: Scrummed/Folded fields updated
            # only during the 5-min-throttled boot sync, then froze.
            # Operator flagged 2026-07-31. Fix: increment here on every
            # sell fill. The next sync_ytd_trade_count refresh will
            # clamp against these values via max(), so per-trade nudges
            # can only ADD accuracy, never regress.
            try:
                _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
                _fill_usd = float(amount) * float(actual_fill) * _qrate
                self.stats.ytd_scrummed_usd = float(getattr(
                    self.stats, "ytd_scrummed_usd", 0.0) or 0.0) + _fill_usd
            except (TypeError, ValueError) as _sup:
                logger.debug("suppressed in %s: %s: %s", "_execute_sell", type(_sup).__name__, _sup)

            # P/L tracked via profit folding in trade decision

            self._memorised_trades.append(MemorisedTrade(
                timestamp=time.time(), side="sell",
                price=actual_fill, amount=amount, voting_summary=summary,
            ))
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"SELL FILLED: {amount:.6f} {self.config.target_asset} "
                        f"@ ${actual_fill:.8f} "
                        f"(intended ${price:.8f}, slip {slippage_pct:+.3f}%)")
            # v3.15.53 — trade lifecycle notification (FILLED)
            self._emit_trade_notification(
                "SCRUM", "FILLED",
                f"{amount:.6f} @ ${actual_fill:.8f}")
            # v3.23.3 — typeless trade.filled emit REMOVED here. The
            # caller (scrum/DIST/manual-rebalance/etc.) emits its own
            # typed trade.filled with proper attribution, so this
            # bare-side emit was producing duplicate trade.log entries
            # tagged action="SELL" (typeless) alongside the typed
            # action="SCRUM"/"DIST"/etc. emit. Per the leads' direction
            # (Option 2 from the double-emit audit), the redundant
            # typeless emit is excised; callers now own emission.
            logger.info("Bot %s sold %.6f at %.4f (intended %.4f, slip %+.3f%%, confidence=%.2f)",
                        self.bot_id, amount, actual_fill, price, slippage_pct,
                        summary.consensus_confidence)
            return actual_fill
        except Exception as exc:
            # MEM-207 — exception path also must NOT leave state mutated.
            # The decrement is now inside the success branch above, so
            # an exception from guarded_place_order is caught here before
            # any state change runs. Return None so caller sees the
            # same failure signal as the order-None case.
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"SELL FAILED: {exc}")
            logger.error("Bot %s sell failed: %s", self.bot_id, exc)
            # MEM-208 — reconcile on exception-path failures too.
            try:
                await self._reconcile_holdings(reason="post_failure")
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "_execute_sell", type(_sup).__name__, _sup)
            return None

    async def _verify_buy_safe_or_refuse(
        self, *, path: str,
    ) -> tuple[Optional[float], str]:
        """MEM-257 FAIL-CLOSED — ScrummingBot wrapper around the
        generalized buy-safety helper at
        ``src/trading/buy_safety.py::verify_buy_safe_or_refuse``.

        Returns ``(verified_units, refuse_reason)``. If
        ``refuse_reason`` is non-empty, the caller MUST refuse the
        buy and emit the reason to ``bot.log``. Otherwise
        ``verified_units`` is the bot's current position in
        ``target_asset`` units (may be ``0.0`` for legitimately-empty).

        v3.18.19 (Tier-1 Q1.2 from Extractor design consideration):
        the buy-safety check was lifted from this method into the
        free function ``verify_buy_safe_or_refuse``. The new function
        is parameterized on ``(exchange, target_asset, expected_units,
        path)`` so the future ExtractorBot (v3.19.1) can call the
        SAME helper with its own expected-units computation
        (``self._positions[pair].alt_units``) without inheritance or
        per-bot duplication. This wrapper preserves the existing
        ScrummingBot call sites (``_execute_buy``,
        ``_execute_manual_rebalance`` FOLD via auto-fire call sites
        Wire Stack + Max Cartridge) unchanged — they continue to
        invoke ``self._verify_buy_safe_or_refuse(path=...)`` exactly
        as before.

        ScrummingBot's expected-units source: ``sum(lot["units"]
        for lot in self._main_lots)`` — the bot's full attributed
        position across all open lots.

        See also:
          • src/trading/buy_safety.py (the free function)
          • MEM-272 (v3.18.14 introduction of the helper)
          • MEM-273 (v3.18.15 operator-sovereignty correction)
          • MEM-275 (v3.18.19 lift to free function for Extractor reuse)
        """
        # Import locally to avoid a top-of-module dependency on a
        # future-extracted module; the cost is one dict lookup per
        # buy attempt which is negligible vs the network round-trip
        # the function does anyway.
        from .buy_safety import verify_buy_safe_or_refuse
        expected_units = sum(
            float(lot.get("units", 0.0))
            for lot in getattr(self, "_main_lots", []))
        return await verify_buy_safe_or_refuse(
            self.exchange,
            self.config.target_asset,
            expected_units,
            path=path,
        )

    async def _execute_buy(
        self, cost: float, price: float, summary: VotingSummary,
        trace_context: Optional[dict] = None,
    ) -> Optional[float]:
        """Execute a buy order. Returns actual fill price captured from
        the exchange response. See _execute_sell docstring for the
        Chunk 6 fill-price-capture design.

        MEM-205 — trace_context names the calling buy path (zero-balance
        initial, fold rebuy, hedge replenishment, or other) and carries
        any decision-relevant pre-call state. Emitted as a single
        structured log line BEFORE placing the order so the operator
        has full causal context on every buy."""

        # sadp: R1 R11 R28 R29 R33 R55 R57  # fold-buy + Verify Hit pre-gate
        # MEM-205 — structured BUY TRACE. One line per buy attempt,
        # captures the full causal picture. Grepable key 'MEM-205 BUY TRACE'.
        try:
            _ctx = dict(trace_context or {})
            _path = _ctx.get("path", "unspecified")
            _holdings = self._current_holdings
            _value = _holdings * price * float(self._quote_to_usd or 1.0)  # v3.15.55
            _delta = _value - self._target_balance
            _tranches_n = len(self._fold_tranches)
            _main_lots_n = len(self._main_lots)
            _ctx_extras = ", ".join(
                f"{k}={v}" for k, v in _ctx.items() if k != "path")
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(
                    f"MEM-205 BUY TRACE: path={_path} "
                    f"value=${_value:.4f} target=${self._target_balance:.2f} "
                    f"delta=${_delta:+.4f} cost=${cost:.4f} price=${price:.8f} "
                    f"holdings={_holdings:.6f} "
                    f"main_lots={_main_lots_n} fold_tranches={_tranches_n} "
                    f"initialised={self._initialised} "
                    f"conf={summary.consensus_confidence:.2f}"
                    + (f" | {_ctx_extras}" if _ctx_extras else "")
                ))
        except Exception as _sup:  # R28-OK: trace emit best-effort; never block the trade path
            # Trace must never break a trade path
            logger.debug("suppressed in %s: %s: %s", "_execute_buy", type(_sup).__name__, _sup)

        # ============================================================
        # v3.15.77 — Conditional opposing-direction hysteresis.
        # ============================================================
        # Operator directive 2026-04-27 (refines v3.15.52):
        #   "Similarly we need to have the opposing direction from a
        #    Fold to be the opposite with the Target Delta drifting
        #    positive to activate the gate."
        #
        # The FOLD-side gate is active only when `_hyst_armed_fold_side`
        # is True (set by _update_opposing_hysteresis_state when delta
        # crossed negative after the last SCRUM). Reference price is
        # the pivot captured at arming, not the original SCRUM price.
        # Manual fire bypasses (uses guarded_place_order directly).
        # sadp: R28 FL R17 R29 R44
        if (self._hyst_armed_fold_side
                and self._hyst_ref_fold_side > 0
                and getattr(self.config, "scrumming_interval_pct", 0) > 0):
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
                    / self._hyst_ref_fold_side * 100.0)
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(f"FOLD REFUSED (opposing hysteresis v3.15.77): "
                             f"pivot ref ${self._hyst_ref_fold_side:.8f} "
                             f"(captured when Δ crossed negative after recent "
                             f"SCRUM), current ${_px_check:.8f} "
                             f"(only {_drop_pct:+.2f}% from pivot). "
                             f"Need ≥ {_eff_pct:.2f}% drop "
                             f"(interval {_interval:.2f}% + fee {_fee:.2f}%; "
                             f"price ≤ ${_required_max:.8f}) before "
                             f"FOLD can fire."))
                self._emit_trade_notification(
                    "FOLD", "CANCELLED",
                    f"hysteresis (need ≥ {_eff_pct:.2f}% drop)")
                return None

        # ============================================================
        # v3.15.51 — Operator-set entry-price bounds (2026-04-25).
        # ============================================================
        # Operator directive: "Bot max / min entry price should be able
        # to be set by user."
        #
        # config.max_entry_price / config.min_entry_price are Optional
        # absolute USD bounds on the price at which the bot will buy.
        # Both default None (= unbounded). Manual fire bypasses these
        # bounds via guarded_place_order which never traverses
        # _execute_buy; that is intentional per the operator's manual-
        # fire-bypasses-everything invariant.
        #
        # Fail-closed: refuse the buy if price is outside the bound,
        # log explicitly so the operator sees why the bot stood down.
        # sadp: R17 R28 FL
        _max_ep = getattr(self.config, "max_entry_price", None)
        _min_ep = getattr(self.config, "min_entry_price", None)
        try:
            _px = float(price) if price is not None else 0.0
        except (TypeError, ValueError):
            _px = 0.0
        if _max_ep is not None and _px > 0 and _px > float(_max_ep):
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"BUY REFUSED (max_entry_price gate): current "
                         f"price ${_px:.8f} > max_entry_price "
                         f"${float(_max_ep):.8f}. Operator-set ceiling. "
                         f"Bot stands down until price drops below."))
            return None
        if _min_ep is not None and _px > 0 and _px < float(_min_ep):
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"BUY REFUSED (min_entry_price gate): current "
                         f"price ${_px:.8f} < min_entry_price "
                         f"${float(_min_ep):.8f}. Operator-set floor. "
                         f"Bot stands down until price rises above."))
            return None

        # ============================================================
        # P0b STACKED-ORDER GUARD (Session 26, 2026-04-24, Layer 1).
        # ============================================================
        # Operator directive 2026-04-24:
        #   "Placement of orders does not consider current open orders
        #    or position value after fill. This needs to be fixed so
        #    we do not have stacked orders that the bot was too blind
        #    to avoid placing."
        #
        # Before placing a BUY, query the exchange for open orders on
        # this symbol. If ANY open BUY exists, refuse — the bot was
        # about to stack on top of an in-flight order whose fill has
        # not yet landed on _current_holdings.
        #
        # Fail-closed: on exchange error during the check, REFUSE.
        # A single missed buy is recoverable; a stacked position is not.
        #
        # Layers 2 (projected-post-fill ceiling) and 3 (local in-flight
        # tracker) are scoped in P0b docket; Layer 1 ships here.
        try:
            _open = await self.exchange.get_open_orders(self.config.symbol)
        except Exception as _oo_exc:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"P0b BUY REFUSED (fail-closed): "
                         f"get_open_orders raised {type(_oo_exc).__name__}: "
                         f"{_oo_exc}. Cannot verify absence of stacked "
                         f"orders. Refusing."))
            return None
        try:
            from ..exchange.base import OrderSide as _OS
            _open_buys = [
                o for o in (_open or [])
                if getattr(o, "side", None) == _OS.BUY
                and getattr(o, "symbol", None) == self.config.symbol
            ]
        except Exception:  # R28-OK: side-enum filter probe; conservative all-orders fallback
            # Best-effort filter; if side enum mismatch, treat ALL open
            # orders as potential stack risk on this symbol.
            _open_buys = [
                o for o in (_open or [])
                if getattr(o, "symbol", None) == self.config.symbol
            ]
        if _open_buys:
            _ids = ", ".join(str(getattr(o, "id", "?")) for o in _open_buys[:3])
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"P0b STACKED BUY REFUSED: {len(_open_buys)} open "
                         f"BUY order(s) already on exchange for "
                         f"{self.config.symbol} (ids: {_ids}). "
                         f"Refusing to place a second BUY on top. "
                         f"Wait for existing order(s) to fill or cancel."))
            return None

        # ============================================================
        # MEM-251 v2 — DEFENSE-IN-DEPTH BUY GUARD (v3.16.50).
        # ============================================================
        # Operator directive 2026-05-10 (architectural correction):
        #   "Check the Target Balance. Check the Current Balance via the
        #    exchange. Calculate Target Delta. Sell or Buy the relevant
        #    amount of tokens to re-zero the Target Delta."
        #
        # History — what this guard USED to be vs what it IS now:
        #
        #   v1 (Session 26, 2026-04-23): ceiling = anchor × (1 + max_target
        #   _growth_pct/100). Default 1% cap meant every buy past anchor
        #   × 1.01 was refused, on every path. Stopped the rogue-buy class
        #   (XRP 4× / BONK 3× / SOL 2×) but ALSO silently strangled the
        #   organic Tranche-Surplus growth path that the strategy depends
        #   on. Operator-confirmed mis-implementation 2026-05-10.
        #
        #   v2 (v3.16.50): max_target_growth_pct is a per-cycle RATE cap
        #   on standing-surplus consumption (Phase B). It is NOT a hard
        #   ceiling. The right defenses are layered:
        #
        # Layer 1 — TARGET-DELTA BUDGET (this site, primary):
        #   For each calling path, compute the maximum legitimate buy cost:
        #     • zero_balance_initial_entry  → up to target_balance
        #     • fold_rebuy                  → max(0, target_delta) + per-cycle
        #                                     growth budget (anchor × cap%/100)
        #     • hedge_replenish             → cost ≤ hedge_bal × 0.5 (caller
        #                                     bounded; we sanity-check)
        #     • unspecified                 → max(0, target_delta) + per-cycle
        #                                     growth budget (conservative)
        #   Refuse if cost > path_budget × (1 + small slippage tolerance).
        #
        # Layer 2 — SMART CEILING BACKSTOP (when enabled):
        #   When config.position_ceiling_enabled, refuse any buy whose
        #   projected position exceeds anchor × position_ceiling_multiple.
        #   This is the MEM-244 detonation ceiling — the only LEGITIMATE
        #   absolute ceiling in the system. Bot detonation harvests grown
        #   position when value > ceiling AND higher-TF bullish vote.
        #
        # Layer 3 — MEM-257 FAIL-CLOSED (preserved below):
        #   Phantom-zero defense + multi-base attribution + fresh-balance
        #   verification. Refuses on any uncertainty. Independent of
        #   the ceiling-question; protects against exchange-state drift.
        #
        # Manual fire deliberately routes through guarded_place_order
        # (NOT _execute_buy) per operator directive. Operator-initiated
        # buys own their own sanity. Layer 2 (Smart Ceiling) does not
        # apply to manual fire either — operator can override at will.
        _ctx = trace_context or {}
        _path = _ctx.get("path", "unspecified")
        _cap_pct = float(getattr(self.config, "max_target_growth_pct", 1.0))
        _anchor = float(getattr(self, "_anchor_target_balance",
                                self._target_balance))
        # Per-cycle growth budget — same number Phase B uses to drain
        # standing surplus into target growth. This is the LEGITIMATE
        # above-target headroom on a fold-rebuy path that consumed a
        # tranche worth more than the Target Delta.
        _per_cycle_growth_budget = _anchor * (_cap_pct / 100.0)

        # MEM-257 (Session 26 — FUND SAFETY, operator rage):
        # "ON AN ASSET THAT HAS A TARGET BALANCE OF $50 and YET GOES OUT
        # WHILE HAVING A CURRENT BALANCE OF $50 and BUYS $100 MORE"
        #
        # The prior MEM-251 guard had three failure modes that let buys
        # slip through even when position was already at/over target:
        # (a) used Balance.free (BTC locked-in-open-order reports free=0);
        # (b) fell back to stale cached _current_holdings on exception;
        # (c) on any uncertainty it logged a warning and proceeded.
        #
        # Policy: FAIL CLOSED. The guard refuses the buy unless it can
        # POSITIVELY VERIFY current position is below the hard ceiling.
        # Any uncertainty — fresh-balance-fetch exception, suspicious
        # disagreement with local lots, target_asset not in the
        # response, anything — means refuse.
        #
        # v3.18.14 (P0 BONK closure, MEM-272): the verify logic has
        # been extracted into ``_verify_buy_safe_or_refuse`` so the
        # SAME check applies to ``_execute_manual_rebalance`` FOLD-side
        # (called by Max Cartridge). Prior to v3.18.14 the manual-
        # rebalance path bypassed MEM-257 entirely — the R68 cold-read
        # of the P0 BONK incident caught it.
        _fresh_units, _refuse_reason_msg = (
            await self._verify_buy_safe_or_refuse(path=_path))
        if _refuse_reason_msg:
            self._bus.emit(
                "bot.log", bot_id=self.bot_id, message=_refuse_reason_msg)
            logger.warning("Bot %s %s", self.bot_id, _refuse_reason_msg)
            return None

        # v3.15.55 — quote→USD-aware. _fresh_units × price gives QUOTE
        # currency value; we multiply by quote→USD so the Layer 1 / Layer 2
        # comparisons (USD) are meaningful for crypto-quoted pairs.
        # For USD-quoted pairs _qrate=1 → unchanged.
        _qrate_buy = float(self._quote_to_usd or 1.0)
        # v3.23.43 — buy guard always compares against THIS bot's own
        # attributed units (sum of _main_lots), never the raw exchange
        # pool. The pool may contain operator-personal balance or
        # units belonging to a different bot on the same asset; those
        # are not this bot's ceiling to enforce.
        _ceiling_units = sum(
            float(lot.get("units", 0) or 0)
            for lot in self._main_lots
        )
        _current_position_usd = _ceiling_units * price * _qrate_buy
        _projected_position_usd = _current_position_usd + cost

        # ─────────────────────────────────────────────────────────────
        # LAYER 1 — TARGET-DELTA BUDGET (per-path)
        # ─────────────────────────────────────────────────────────────
        # The legitimate cost is bounded by the Target Delta the buy is
        # supposed to re-zero, plus (where applicable) the per-cycle
        # growth budget for surplus-driven organic target growth.
        _target_delta_usd = float(self._target_balance) - _current_position_usd
        _slippage_tol_pct = 0.5  # 0.5% slippage allowance for fee/spread
        if _path == "zero_balance_initial_entry":
            # Initial entry: bring position from ~0 up to target.
            _path_budget = float(self._target_balance)
        elif _path in ("fold_rebuy", "manual_tranche_fire"):
            # v3.16.53 CORRECTION — fold-back consumes an existing tranche's
            # parked USD. The cost is already bounded by tranche.usd at
            # the caller (per-tranche math). Fold-back MECHANICALLY
            # produces position > target because it rebuys MORE units
            # than were sold (at lower price) — that excess IS the
            # Tranche Surplus that drives organic target growth.
            #
            # v3.16.50 bug: this site previously used
            # `max(0, target_delta) + per_cycle_growth_budget` as the
            # budget, which silently refused fold-back for any bot whose
            # position was already at/above target. Across the whole
            # platform that meant 0 lifetime fold-back closures despite
            # dozens of price-eligible tranches — operator caught it
            # 2026-05-11.
            #
            # Correct semantic: trust the caller's cost (already bounded
            # by tranche.usd). Smart Ceiling (Layer 2) remains the only
            # position-level cap. Per-tranche manual fire follows the
            # same rule — operator-initiated tranche fold-back must not
            # be blocked by target-delta math.
            _path_budget = float(cost)
        elif _path == "hedge_replenish":
            # Hedge has its own bucket. Caller already clamps to
            # hedge_bal × 0.5; we sanity-check against the hedge limit
            # rather than target. Allow up to current hedge_bal as a
            # conservative upper bound (caller is the real authority).
            try:
                _hedge_limit = float(getattr(self, "_hedge_bal", 0.0) or 0.0)
            except (TypeError, ValueError):
                _hedge_limit = 0.0
            _path_budget = _hedge_limit
        else:
            # Unspecified / unknown path. Conservative: same budget as
            # fold_rebuy but with a stricter log so the operator can see
            # any new path that wasn't enumerated above.
            _path_budget = max(0.0, _target_delta_usd) + _per_cycle_growth_budget
            logger.warning(
                "Bot %s _execute_buy: unspecified path used the conservative "
                "fold_rebuy-equivalent budget (cost=$%.2f, budget=$%.2f). "
                "If this is a new legitimate path, enumerate it in the "
                "Layer 1 dispatch.",
                self.bot_id, cost, _path_budget)

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

        # ─────────────────────────────────────────────────────────────
        # LAYER 2 — SMART CEILING BACKSTOP (when enabled)
        # ─────────────────────────────────────────────────────────────
        # Smart Ceiling = anchor × position_ceiling_multiple. When
        # enabled, no buy on any path may push position past it. This
        # is the operator-set "maturity" cap that triggers detonation
        # harvest on the next bullish higher-TF vote (MEM-244).
        if getattr(self.config, "position_ceiling_enabled", False):
            try:
                _smart_ceiling_usd = self.position_ceiling_usd
            except Exception:  # R28-OK: ceiling probe; None signals "unset"
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
                    self._bus.emit("bot.log", bot_id=self.bot_id,
                                   message=_reason)
                    logger.warning("Bot %s %s", self.bot_id, _reason)
                    return None

        try:
            amount = cost / price
            # v3.15.55 — quote→USD conversion. `cost` is operator USD;
            # `cost / price` lands in QUOTE units (correct for USD-quoted
            # pairs where _qrate_buy=1). For crypto-quoted pairs (BTC/ETH
            # etc.) we divide once more by quote→USD to land in BASE units
            # the exchange expects. No-op for USD-quoted (qrate=1.0).
            if _qrate_buy > 0 and abs(_qrate_buy - 1.0) > 1e-9:
                amount = amount / _qrate_buy

            # R55 VH v3 — pre-trade gate (per R57 EPM — parity with
            # sim engines). Refuse to place the order if projected
            # slippage would breach the per-asset-class tolerance.
            from ..core.execution_discipline import verify_hit as _vh
            vh_fp, vh_status, vh_samples = _vh(
                price, 'buy', symbol=self.config.target_asset)
            self.stats.verify_samples += vh_samples
            if vh_fp is None:
                self.stats.verify_canceled += 1
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=f"BUY CANCELED (R55 VH): slippage would "
                            f"exceed {self.config.target_asset} class "
                            f"tolerance @ ${price:.8f}")
                logger.info("Bot %s VH-canceled buy of %.6f at %.4f",
                            self.bot_id, amount, price)
                return
            if vh_status == 'clean':
                self.stats.verify_clean += 1
            else:
                self.stats.verify_adjusted += 1
                # Re-derive amount from verified effective price.
                amount = cost / vh_fp
                # v3.15.55 — apply the same quote→USD conversion.
                if _qrate_buy > 0 and abs(_qrate_buy - 1.0) > 1e-9:
                    amount = amount / _qrate_buy

            # Invisible mode: ALWAYS market order (nothing on book)
            if self._invisible:
                ot = OrderType.MARKET
                exec_price = None
            else:
                ot = OrderType.LIMIT
                exec_price = vh_fp  # use VH-verified effective price

            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"BUY signal: {amount:.6f} @ ${price:.8f} "
                        f"(VH:{vh_status}, confidence="
                        f"{summary.consensus_confidence:.2f}, "
                        f"{'MARKET' if self._invisible else 'LIMIT'})")
            # v3.15.53 — trade lifecycle notification (SENT). FOLD when
            # called from fold path; INITIAL/HEDGE could refine further
            # via trace_context but FOLD is the most common case.
            self._emit_trade_notification(
                "FOLD", "SENT",
                f"{amount:.6f} @ ${price:.8f}")

            order = await self.guarded_place_order(
                symbol=self.config.symbol,
                side=OrderSide.BUY,
                order_type=ot,
                amount=amount,
                price=exec_price,
            )

            # MEM-207 — explicit failure gate. guarded_place_order may
            # return None when the exchange rejected the request, the
            # volume guard blocked it, or any other non-exceptional
            # failure path. Previously this code unconditionally
            # incremented _current_holdings and emitted BUY FILLED even
            # when order was None, leading to phantom credits in
            # internal state that diverged from exchange reality.
            # Operator diagnosis (Session 23): "bots are blind to
            # current_exchange_balances." This is the fix.
            if order is None:
                self._bus.emit("bot.log", bot_id=self.bot_id,
                    message=(
                        f"BUY ABORTED: exchange/guard returned no order for "
                        f"{amount:.6f} {self.config.target_asset} @ "
                        f"${price:.8f}. No state update. Caller must not "
                        f"treat this as success."))
                logger.warning(
                    "Bot %s buy aborted (order None) for %.6f at %.4f",
                    self.bot_id, amount, price)
                # MEM-208 — failed trade is a prime drift moment. Reconcile
                # immediately so any accumulated divergence surfaces now
                # rather than waiting for the periodic cycle.
                try:
                    await self._reconcile_holdings(reason="post_failure")
                except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                    logger.debug("suppressed in %s: %s: %s", "_execute_buy", type(_sup).__name__, _sup)
                return None

            # --- Success path: order is truthy ---
            self._current_holdings += amount
            self.stats.total_buys += 1
            self.stats.total_trades += 1

            # v3.13.8 MEM-190 / Chunk 6 — capture actual fill price.
            # DPA: CCXT-001 exception — Order.average may be None on
            # some exchanges; fall back to order.price. This fallback
            # is SAFE (using a less-precise success field) — distinct
            # from the MEM-207 anti-pattern of treating None-order as
            # success.
            actual_fill = getattr(order, 'average', None) or getattr(order, 'price', None)
            if not actual_fill or actual_fill <= 0:
                actual_fill = price
            slippage_pct = ((actual_fill - price) / price * 100.0) if price > 0 else 0.0

            self.stats.trade_volume += amount * actual_fill
            self.stats.last_trade_time = time.time()

            # v3.23.78 — per-trade YTD Folded USD increment.
            # See matching comment in _execute_sell above for the
            # docstring-vs-reality gap this closes.
            try:
                _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
                _fill_usd = float(amount) * float(actual_fill) * _qrate
                self.stats.ytd_folded_usd = float(getattr(
                    self.stats, "ytd_folded_usd", 0.0) or 0.0) + _fill_usd
            except (TypeError, ValueError) as _sup:
                logger.debug("suppressed in %s: %s: %s", "_execute_buy", type(_sup).__name__, _sup)

            self._memorised_trades.append(MemorisedTrade(
                timestamp=time.time(), side="buy",
                price=actual_fill, amount=amount, voting_summary=summary,
            ))
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"BUY FILLED: {amount:.6f} {self.config.target_asset} "
                        f"@ ${actual_fill:.8f} "
                        f"(intended ${price:.8f}, slip {slippage_pct:+.3f}%, "
                        f"holdings now {self._current_holdings:.6f})")
            # v3.15.53 — trade lifecycle notification (FILLED)
            self._emit_trade_notification(
                "FOLD", "FILLED",
                f"{amount:.6f} @ ${actual_fill:.8f}")
            # v3.23.3 — typeless trade.filled emit REMOVED here. Same
            # rationale as the matching deletion in _execute_sell: every
            # caller of _execute_buy now owns the typed trade.filled
            # emit with proper attribution. The INITIAL ENTRY path added
            # its own typed emit at the success site (action="ENTRY")
            # since it had no downstream typed emit before this change.

            # ITEM 7 -- A FOLD SPAWNS STACK TRANCHES. The buy has filled
            # and its state is booked; this builds the sell ladder above
            # the fill. `amount` is the base-asset size the fill
            # acquired and `actual_fill` is the price it paid, which is
            # the anchor the Minimum Opposing Trade Distance is measured
            # from. The helper absorbs every failure and returns 0, so
            # it cannot reach the `except` below and turn a filled buy
            # into a reported failure.
            await self._spawn_stack_from_fold(
                fold_price=actual_fill, fold_size=amount,
                summary=summary, path=_path)
            return actual_fill
        except Exception as exc:
            # MEM-207 — exception path also must NOT leave state mutated.
            # The code above puts the increment AFTER the order-None gate
            # and AFTER try entry, so an exception from guarded_place_order
            # is caught here before any state update runs. Leaving this
            # except as the single failure-emit site; return None so the
            # caller sees the same signal as the order-None case.
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=f"BUY FAILED: {exc}")
            logger.error("Bot %s buy failed: %s", self.bot_id, exc)
            # MEM-208 — reconcile on exception-path failures too.
            try:
                await self._reconcile_holdings(reason="post_failure")
            except Exception as _sup:  # R28-OK: best-effort optional update / telemetry probe
                logger.debug("suppressed in %s: %s: %s", "_execute_buy", type(_sup).__name__, _sup)
            return None

    # ------------------------------------------------------------------
    # Memorize function — convert scrumming history to grid positions
    # ------------------------------------------------------------------
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
                levels.append({
                    "buy_price": buy.price,
                    "sell_price": sell.price,
                    "position_size": buy.amount * buy.price,
                    "is_extended": False,
                    "organic": True,
                })

        logger.info(
            "Bot %s memorised %d trades → %d grid levels",
            self.bot_id, len(self._memorised_trades), len(levels),
        )
        return levels

    # ------------------------------------------------------------------
    # MEM-069 + MEM-171 port — invariants and diagnostics
    # ------------------------------------------------------------------
    def _main_lots_invariant_ok(self, tol: float = 1e-6) -> bool:
        """True iff sum(lot['units']) == _current_holdings within tolerance.

        Invariant enforced by MEM-069 + MEM-171 bookkeeping: every unit
        currently held must be accounted for in exactly one main_lots entry
        with a known initial_buy_price. Drift indicates a bookkeeping bug
        in scrum/fold/dist paths.

        v3.25.6 -- CITATION CORRECTED. This named a caller under the
        tests directory, `test_mem171_scrumming_bot_port`, and no file
        of that name exists anywhere in the repo. The real callers,
        found by grep rather than by memory, are
        tests/test_extractor_tranche_containment.py and
        tests/test_opening_position_adoption.py. Also available for
        runtime diagnostics (e.g. operator can assert after N ticks).

        NOT A GUARD. This reports; it never blocks.

        v3.25.7 -- THE MEM-171 CITATION WAS WRONG TWICE IN ONE SENTENCE.
        It read: the fold-floor rule `price <= tranche
        ["initial_buy_price"]` "is enforced at :9262, not here". First,
        :9262 is a COMMENT that describes the rule; it evaluates
        nothing. Second, and worse, the rule is not enforced on the fold
        path AT ALL. The executor's eligibility filter is
        `ticker.last <= float(t.get("ref", 0)) * _otd_factor` (:9803),
        which carries no `initial_buy_price` term, and the comment
        beside it says so in as many words (:9791). The
        `initial_buy_price` reading survives only as a SECONDARY
        diagnostic counter, `_patent_only_eligible` (:9530), labelled
        there as "not a gate". MEM-171 is held at the strategy level by
        the position ceiling -- `self._anchor_target_balance * mult`
        (:4714) -- not per tranche. Cite the predicate, not the prose
        about it.
        """
        lots_sum = sum(l["units"] for l in self._main_lots)
        return abs(lots_sum - self._current_holdings) <= tol

    def _main_lots_summary(self) -> dict:
        """Human-readable snapshot of the MEM-171 state for debugging."""
        return {
            "main_lots_count": len(self._main_lots),
            "main_lots_units_sum": sum(l["units"] for l in self._main_lots),
            "main_lots_min_ibp": (
                min((l["initial_buy_price"] for l in self._main_lots), default=0.0)),
            "main_lots_max_ibp": (
                max((l["initial_buy_price"] for l in self._main_lots), default=0.0)),
            "fold_tranches_count": len(self._fold_tranches),
            "fold_tranches_usd_sum": sum(t["usd"] for t in self._fold_tranches),
            "fold_tranches_units_sum": sum(t["units"] for t in self._fold_tranches),
            "current_holdings": self._current_holdings,
            "invariant_ok": self._main_lots_invariant_ok(),
        }

    # ------------------------------------------------------------------
    # Phantom access
    # ------------------------------------------------------------------
    def get_multi_tf_summary(self) -> dict:
        """Return multi-timeframe voting summary from all phantoms."""
        return self._coordinator.get_multi_tf_summary(self.bot_id)

    def get_phantom_statuses(self) -> list[dict]:
        """Return status of all phantom bots."""
        return [p.get_status() for p in self._phantom_mgr.get_phantoms(self.bot_id)]

    # ------------------------------------------------------------------
    # Extended Position check
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    async def stop(self) -> None:
        """Stop this bot and all its phantom balance bots."""
        # v3.23.42 — release capital reservation FIRST so sibling
        # bots on the same base see the freed chunk immediately on
        # their next tick, before this bot's teardown.
        self._release_capital_reservation()
        await self._phantom_mgr.stop_all(self.bot_id)
        self._phantom_mgr.remove_set(self.bot_id)
        await super().stop()

    # ------------------------------------------------------------------
    # Item 7 -- A FOLD SPAWNS STACK TRANCHES.
    #
    # Operator spec: "When a fold occurs, it should generate stack
    # tranches and, when some or all of those tranches fill, the fold
    # tranches spawn on the other side starting at the minimum opposing
    # trade distance", and "Scrum fires using existing Stack Tranches,
    # Fold Tranches Spawn, Fold fires using existing Fold Tranches."
    #
    # The sell half already worked: a stack tranche filling IS a sell,
    # and the sell paths build fold tranches from it. The buy half did
    # not exist. An AST walk of the two executors on 2026-08-13 read
    #     _execute_sell -> ['_open_stack_from_scrum']
    #     _execute_buy  -> []
    # so a fold closed no pair. This is that missing half and nothing
    # else: merge, consumption, spacing and distribution are untouched,
    # and the ladder comes from the item-6 `stack_math` call the SCRUM
    # side already uses rather than from new arithmetic here.
    #
    # PLACED HERE ON PURPOSE, below every line the citation table in
    # tests/test_extractor_tranche_containment.py names -- its highest
    # anchor is `_main_lots_invariant_ok` -- and above the Extractor
    # block, which stays last for the reason its own comment gives.
    # ------------------------------------------------------------------

    # The buy paths that ARE a fold. EXACT MEMBERSHIP, not an open
    # predicate, so the accepted set can be read off the page:
    #
    #   fold_rebuy                   autonomous fold-back      SPAWNS
    #   manual_tranche_fire          per-tranche fold-back     SPAWNS
    #   zero_balance_initial_entry   an entry, not a fold      no spawn
    #   hedge_replenish              a hedge, not a fold       no spawn
    #   unspecified / absent / None  not known to be a fold    no spawn
    #
    # The two that spawn are the two `_execute_buy`'s own Layer 1 budget
    # dispatch already groups together, under the comment "fold-back
    # consumes an existing tranche's parked USD". The set is read off
    # that dispatch, not invented beside it.
    #
    # DETONATION AND SELF-DESTRUCT ARE TERMINAL AND APPEAR NOWHERE IN
    # THAT TABLE, because neither one reaches `_execute_buy` to be
    # tested against it: both are market SELLS that call
    # `guarded_place_order` directly. An AST reachability walk over
    # self-calls confirmed it on 2026-08-13 -- self_destruct,
    # _execute_detonation and _check_detonation_trigger all report
    # False for `_execute_buy` and for `_open_stack_from_scrum`, on a
    # walker whose positive control (the known
    # _execute_sell -> _open_stack_from_scrum edge) came back True.

    async def _spawn_stack_from_fold(
        self, fold_price: float, fold_size: float,
        summary: Optional[VotingSummary] = None,
        path: str = "",
    ) -> int:
        """A filled FOLD spawns the Stack ladder above it. Returns how
        many Stack tranches were created, 0 when none were.

        THE ANCHOR IS THE PRICE THE FOLD ACTUALLY FILLED AT, not the
        price it was offered at. `_open_stack_from_scrum` puts the
        ladder anchor one Minimum Opposing Trade Distance above the
        price handed to it -- `scrumming_interval_pct` plus
        `trading_fee_pct` -- and `stack_math` puts level 1 one initial
        gap above that. So the opposing distance is measured from what
        this fold paid. The SCRUM-side intercept has to use the tick
        price because it runs BEFORE any fill exists; this runs after
        one, and a distance measured from an intended price that
        slipped is a distance from a price that never traded.

        NOTHING NEW IS GATED, AND NOTHING NEW IS BYPASSED. The buy has
        already passed every gate `_execute_buy` owns and has already
        filled. The spawn reads `stack_mode` exactly as the SCRUM side
        reads it and inherits that gate unchanged; with the gate off it
        returns 0 and touches nothing.

        IT CANNOT FAIL THE TRADE. The call site sits inside
        `_execute_buy`'s try block, whose handler emits BUY FAILED and
        returns None to the caller. A raise out of a bookkeeping spawn
        would therefore turn a filled buy into a reported failure and
        strand the units it bought, so every failure is absorbed here
        and reported as 0.
        """
        # The literal set, not `self.SOMETHING`. An attribute lookup
        # here would raise on a duck-typed stub BEFORE the try block
        # below, escape into `_execute_buy`'s handler, and turn a
        # filled buy into a reported failure -- the one outcome this
        # helper exists to prevent.
        if path not in ("fold_rebuy", "manual_tranche_fire"):
            return 0
        # The same gate the SCRUM side applies, read the same way. The
        # Stack side ships dormant -- `stack_mode` is False on every
        # live bot -- so this returns 0 on every fold today.
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
        except Exception as _spawn_exc:  # R28 CBF -- surface, never raise
            logger.error(
                "Bot %s fold-spawned stack FAILED after a filled buy "
                "(%s: %s); the fill stands, no tranches were opened",
                self.bot_id, type(_spawn_exc).__name__, _spawn_exc)
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"FOLD STACK SPAWN FAILED: "
                         f"{type(_spawn_exc).__name__}: {_spawn_exc}. "
                         f"The fold fill stands; no Stack tranches were "
                         f"opened above it."))
            return 0
        if opened > 0:
            self._bus.emit("bot.log", bot_id=self.bot_id,
                message=(f"FOLD SPAWNED STACK: {opened} tranche(s) above "
                         f"a fold filled at ${float(fold_price):.8f} "
                         f"(size {float(fold_size):.6f}, path {path})."))
        return opened

    # ------------------------------------------------------------------
    # Extractor Tranches (item 4) — the parent's listing of its children
    #
    # DELIBERATELY THE LAST THING IN THE CLASS. `apply_extractor_tranche_
    # return` and four helpers carry `:NNNN` citations into this file,
    # and `tests/test_extractor_tranche_containment.py` checks that each
    # cited line still holds the token it was cited for. Inserting a
    # method higher up shifts every line below it and rots those
    # citations wholesale — which is exactly what happened on the first
    # attempt at item 4, and what that test caught. Adding here shifts
    # nothing, so not one citation moved.
    # ------------------------------------------------------------------
    def open_extractor_tranches(self) -> list[dict]:
        """List the Extractor Tranches held against this bot's asset.

        Operator design 2026-08-09: an Extractor's in-flight position is
        an "Extractor Tranche", its value "is tracked by the parent
        Scrumming Bot", and it is "listed under the base-currency bot".
        This is that listing. The parent owns the base asset; a child
        holds a lease on a slice of it, and this is how the parent reads
        the leases out.

        A VIEW, NOT A LEDGER ENTRY. Nothing is stored. This walks the
        bot manager on every call and asks each child what it is
        holding. That choice is the whole safety argument for item 4,
        so it is written down here rather than left to be re-derived:

        * IT CANNOT BE TRADED ON. An Extractor Tranche is not in
          ``_main_lots`` and not in ``_fold_tranches``, so no gate, no
          sizing loop and no fold-back can reach one. ``_current_holdings``
          derives from ``_main_lots`` alone (v3.23.43), so a lease can
          never inflate the holdings valued against the target balance,
          nor the ``total_holdings`` handed to the capital-reservation
          check. The alternative -- a ``kind`` key on ``_fold_tranches``
          -- would have needed a correct filter at roughly twenty
          consumers, most of them trading decisions, with a wrong buy or
          a wrongly-sized SCRUM as the price of missing one. This
          removes that surface by construction rather than by vigilance.
        * IT CANNOT DRIFT. The child is the only writer of its own
          positions. A stored copy here would need an open-side
          notification that does not exist today, and the sell-side one
          that does exist swallows every exception -- so a dropped
          message would leave the parent quietly wrong.
        * IT NEEDS NO MIGRATION. Nothing new is persisted, so a saved
          bot loads exactly as it did before item 4.
        * IT IS IMMUNE TO THE FOLD-TRANCHE COLLAPSE DEFECT, which leaves
          ``_fold_tranches`` over-populated. This view does not read
          that list.

        NO MONEY MOVES HERE AND NO STATE CHANGES. Item 4 is a record.
        The lift that contains a child's returned gain is item 1's
        ``apply_extractor_tranche_return``, and it stays there.

        NO NETWORK. The caller is the Qt GUI thread, which is the thread
        every coroutine in this application runs on. Each child reports
        prices it had already fetched during its own tick.

        Returns an empty list when no manager is attached or no child
        matches -- which is every bot the operator runs without an
        Extractor. A child that raises is logged and skipped, so one bad
        child cannot blind the parent to the rest.
        """
        manager = getattr(self, "_bot_manager", None)
        if manager is None:
            return []
        lister = getattr(
            manager, "list_extractor_children_for_parent", None)
        if not callable(lister):
            return []
        try:
            children = lister(self)
        except Exception as _list_exc:  # R28-OK: listing is display-only
            logger.warning(
                "Bot %s could not list Extractor children: %s: %s",
                self.bot_id, type(_list_exc).__name__, _list_exc)
            return []
        rows: list[dict] = []
        for child_id, child in children or []:
            reader = getattr(child, "extractor_tranche_rows", None)
            if not callable(reader):
                continue
            try:
                child_rows = reader()
            except Exception as _row_exc:  # R28-OK: skip one bad child
                logger.warning(
                    "Bot %s: Extractor child %s failed to report its "
                    "tranches: %s: %s — skipped, other children still "
                    "listed.", self.bot_id, child_id,
                    type(_row_exc).__name__, _row_exc)
                continue
            for row in child_rows or []:
                if isinstance(row, dict):
                    rows.append(dict(row))
        rows.sort(key=lambda r: str(r.get("tranche_id", "")))
        return rows
