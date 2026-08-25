"""
src/trading/extractor_bot.py — Base Currency Extractor Multi-Target Bot (v3.19.1).

CONCEPT
───────
The inversion of ScrummingBot. Where ScrummingBot anchors to a TARGET
BALANCE of an *alt* asset and grows USD-value through volatility, the
Extractor anchors to a POOL of a *base* asset and grows BASE UNIT COUNT
through volatility.

Use case: operator holds 5 ETH and wants to grow it to 6 ETH without
trading off the slow internal ETH price action. The Extractor pulls
$20 of ETH at a time, buys into a volatile altcoin during a dip, sells
it back during a rally, returns ~$22 of ETH to the pool. Repeat across
many alt pairs concurrently.

STATE MACHINE (per pair)
────────────────────────
    PENDING ──bearish─→ IN_FLIGHT ──bullish exit──→ PENDING (or roll)
       ↑                    │
       │                    ↓
       │                DRAWDOWN ──recovery──→ IN_FLIGHT
       │                    │
       └────tier max────────┘ (gain locks to pool)

DESIGN DOC
──────────
docs/audits/2026-05-20_extractor_bot_design.md (canonical).
docs/audits/2026-05-20_extractor_bot_final_design_consideration.md
(Tier-1 decisions: half-extract TA producer, generalized MEM-257
helper, Section 13a decoupled, MR Inspector REMOVED).

NO MR INSPECTOR (operator directive 2026-05-20):
  > "Extractors do not spawn child bots and therefore do not need to
  >  use Mr. Inspector. They are configured to be multi-pair and hit
  >  multiple assets for maximum accumulation."

Multi-asset reach is achieved by THIS bot's within-bot top-N watch
list scan, NOT via spawn cascades.

DEPENDENCIES (shipped in v3.18.18 → v3.19.0)
─────────────────────────────────────────────
  * BotManager.sum_sibling_base_currency_claims (v3.18.18, §13a) —
    claim-aware base-currency capacity check.
  * src/trading/buy_safety.py::verify_buy_safe_or_refuse (v3.18.19) —
    parameterized MEM-257 FAIL-CLOSED, used on every artillery buy +
    correction buy with expected_units = position.alt_units.
  * src/trading/ta_signal_provider.py::TASignalProvider (v3.19.0) —
    per-pair TA producer; bot constructs one provider per tick scope
    and calls evaluate(pair) for every pair in the watch list.

sadp: R28 R29 R51 R55 R68
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from ..exchange.base import OrderSide, OrderType
from .bot_container import BotContainer, BotConfig, BotMode
from .buy_safety import verify_buy_safe_or_refuse
from .ta_signal_provider import TASignalProvider, TASnapshot

if TYPE_CHECKING:
    from ..exchange.base import ExchangeInterface

logger = logging.getLogger("acervator.extractor")


# ─────────────────────────────────────────────────────────────────────
# Position dataclass — one per active pair
# ─────────────────────────────────────────────────────────────────────

# Percent points in one unit of a dimensionless ratio. Named so the
# conversion between the two is written once and visible: a threshold
# stored in percent divided by this constant is a ratio, and a ratio
# multiplied by it is percent. Used by update_base_usd_rate().
PERCENT_PER_RATIO_UNIT = 100.0

POSITION_STATE_PENDING = "pending"  # (transitional — never persisted on a Position)
POSITION_STATE_IN_FLIGHT = "in_flight"
POSITION_STATE_DRAWDOWN = "drawdown"
POSITION_STATE_BULLISH_EXIT = "bullish_exit"


# ─────────────────────────────────────────────────────────────────────
# Extractor Tranche Arbiter (item 5, operator directive 2026-08-10)
# ─────────────────────────────────────────────────────────────────────
# Operator, verbatim: "Just have a toggling option for 'Extractor
# Tranche Abiter' which decides who gets to sell it and when i.e.
# Parent or Sibling." It is PER TRANCHE, not per bot, so the value
# lives on the position and nowhere else.
#
# WHAT THE TWO VALUES NAME:
#   parent  — the base-currency ScrummingBot force-sells the tranche
#             at x% of growth.
#   sibling — the Extractor does all the work; the parent stands back.
#
# WHAT IS TRUE TODAY. Only `sibling` describes running code. Nothing
# in this repository force-sells a child's position from the parent:
# the automatic closer is this bot's own `_execute_bullish_exit`, the
# operator closer is this bot's own `manual_fire_position`, and the
# parent's whole involvement is booking money that already arrived
# (`ScrummingBot.apply_extractor_tranche_return`). So `parent` RECORDS
# AN INTENTION and changes no trading decision. Nothing reads this
# field except the row emitter and the surface that paints it.
#
# WHY THE DEFAULT IS SIBLING. It is the only value that describes what
# the fleet already does. Defaulting to `parent` would put a false
# record on every tranche and would silently arm every existing
# tranche the moment a force-sell was built. Defaulting to `sibling`
# means such a unit would ship inert and act only on tranches the
# operator deliberately toggled.
ARBITER_PARENT = "parent"
ARBITER_SIBLING = "sibling"

# Operator's own words for the surface. "Sibling", never "child".
ARBITER_LABELS = {
    ARBITER_PARENT: "Parent",
    ARBITER_SIBLING: "Sibling",
}


def normalize_arbiter(value: object) -> str:
    """Coerce anything at all to exactly one of the two arbiter values.

    FAIL TOWARDS THE INERT VALUE. Only the exact text ``parent``, once
    stripped and lower-cased, reads as `parent`. A typo, a ``None``, a
    ``True``, a truncated write, a number — every one of them lands on
    `sibling`, which is the value that describes what the code already
    does. The unrecognised case must never fall towards the value that
    a later force-sell would act on.

    THIS CANNOT RAISE, and that is the point. It is called from inside
    `import_state`'s per-position constructor, where a raise DROPS the
    record and the bot stops managing a real position. An arbiter
    string is a preference; it may never cost the operator a position.
    So nothing here can throw: `isinstance` cannot, and the two string
    methods are only ever reached on a value that IS a string. Note
    what is deliberately NOT done — `str(value)` is never called,
    because that runs an arbitrary object's ``__str__`` and would put
    a raise back on the path this exists to keep clear. A non-string
    is simply not a value, and lands on the inert default.
    """
    if not isinstance(value, str):
        return ARBITER_SIBLING
    text = value.strip().lower()
    return ARBITER_PARENT if text == ARBITER_PARENT else ARBITER_SIBLING


def arbiter_label(value: object) -> str:
    """Return the operator-facing word: ``Parent`` or ``Sibling``."""
    return ARBITER_LABELS[normalize_arbiter(value)]


def other_arbiter(value: object) -> str:
    """Return the value a toggle moves to. Two values, so a flip."""
    normalized = normalize_arbiter(value)
    return ARBITER_SIBLING if normalized == ARBITER_PARENT else ARBITER_PARENT


@dataclass
class ExtractorPosition:
    """One artillery round in flight against a pair.

    The Extractor owns ONE active ExtractorPosition per pair (operator
    directive 2026-05-20 decision #8: "one active position per pair,
    maintained until released"). The position is created on artillery
    fire (PENDING → IN_FLIGHT) and destroyed when the bullish exit
    sells the alt units back to base.
    """

    pair: str
    state: str

    # Original entry — base-units AND USD reference, captured at firing time
    artillery_size_base: float
    artillery_size_usd_at_entry: float

    # Current position state
    alt_units: float
    entry_price_base_per_alt: float
    avg_buy_price_base_per_alt: float
    cost_basis_base: float

    # Lifecycle counters
    compounding_tier: int = 1
    corrections_fired: int = 0
    last_correction_ts: float = 0.0
    opened_at: float = 0.0

    # Last observed alt price, in base currency per alt unit, recorded
    # by the tick that had already fetched it for its own decisions.
    # Item 4 (2026-08-11): the parent Scrumming Bot must be able to put
    # a value on an Extractor Tranche, and the Open Tranches table that
    # shows it is built on the Qt GUI thread, where every coroutine in
    # this application runs. Fetching a ticker there would block the
    # interface for the round trip, once per tranche, per repaint.
    #
    # So nothing new is fetched. The tick already calls get_ticker for
    # this pair; it now keeps the answer instead of discarding it.
    #
    # Zero means NEVER PRICED, and readers must treat it as "no mark
    # available" rather than as a price of zero. A position that has
    # not ticked yet — freshly restored from disk, for instance — has
    # no mark, and cost basis must not be dressed up as one.
    last_price_base_per_alt: float = 0.0
    last_priced_at: float = 0.0

    # Item 5 (2026-08-10) — who may close THIS tranche: `parent` or
    # `sibling`. See the ARBITER_* block above for what each word
    # names and why `sibling` is the default.
    #
    # WHY THE VALUE LIVES HERE AND NOT ON THE PARENT. The parent's
    # Extractor Tranche row is a COMPUTED VIEW: it walks the manager
    # and asks each child, and stores nothing. There is no parent-side
    # record to attach a value to, and a parent-side copy would be a
    # mirror that can diverge in silence — nothing tells the parent
    # when a position OPENS, and the one sell-side message that does
    # exist swallows every exception.
    #
    # WHY NOT A SIDE-MAP KEYED BY `tranche_id`. That id is DERIVED on
    # every call from bot_id|pair|opened_at and is never stored, so a
    # map keyed on it would depend on three fields all re-deriving
    # identically after a restore — and a position saved without
    # `opened_at` collapses to a `0.000000` suffix. A field on the
    # position is created with the position and dies with it, so it
    # cannot orphan and needs no pruning.
    #
    # WHY NOT BotConfig. The directive is per-tranche. A config field
    # is bot-wide by construction and would set every tranche at once.
    arbiter: str = ARBITER_SIBLING


# ─────────────────────────────────────────────────────────────────────
# ExtractorBot
# ─────────────────────────────────────────────────────────────────────


class ExtractorBot(BotContainer):
    """Multi-pair base-currency Extractor.

    See module docstring for the architecture overview. This class
    implements the per-tick logic; the dependencies (TASignalProvider,
    buy_safety, BotManager claim helper) ship in v3.18.18-v3.19.0.

    NO MR INSPECTOR INTEGRATION — operator directive 2026-05-20:
    ExtractorBots do not spawn child bots. The class deliberately does
    not register with the MR Inspector spawn controller and emits no
    bot-creation provenance events. Multi-asset reach is achieved
    via the within-bot top-N watch list, not via spawning. The
    drift-detector test at tests/test_extractor_bot.py pins this
    invariant by name-checking the module source.
    """

    DEFAULT_TIMEFRAME = "1h"

    def __init__(
        self,
        config: BotConfig,
        exchange: ExchangeInterface,
        enable_phantoms: bool = False,  # Extractor does not use phantoms
    ) -> None:
        # This mode guard used to be an `assert`. Under `python -O` an
        # assert is stripped, so the guard silently disappeared and an
        # ExtractorBot could be built on a Scrumming config and then run
        # extractor logic against real money. A raise cannot be stripped.
        # Same shape as ScrummingBot.__init__ (scrumming_bot.py:334).
        if config.mode != BotMode.EXTRACTOR:
            raise ValueError(
                f"ExtractorBot requires BotMode.EXTRACTOR; " f"got {config.mode!r}"
            )
        super().__init__(config, exchange)

        # Record the phantom flag this bot was constructed with.
        # BotContainer.__init__ hardcodes `_phantoms_enabled = False`,
        # and its own comment says that value was "taken from the code"
        # only because ExtractorBot "never stores the value"
        # (bot_container.py:969-975). Storing it makes the constructor
        # parameter real instead of decorative. The Extractor still runs
        # no phantom logic; the flag is state, not a switch.
        #
        # NO BEHAVIOUR CHANGE: the parameter defaults to False and both
        # construction sites pass False explicitly — main_window.py:7545
        # and bot_container.py:3557 — so the stored value is False on
        # every path that exists today, exactly what the parent set.
        self._phantoms_enabled = bool(enable_phantoms)

        # ── Chunk-based balance (operator directive decision #8) ────
        # The Extractor OWNS its assigned chunk of base currency.
        # NEVER queries exchange.get_balance(base) to size decisions;
        # only consults this internal ledger. Operator-allocated;
        # never auto-resized.
        #
        # Conversion USD → base: snapshot ratio at construction time.
        # Stored in base-currency units so base-USD price drift
        # doesn't silently shrink/grow the bot's chunk.
        # Until set_initial_chunk_rate() is called by the constructing
        # context (BotManager or test harness), we default to a
        # 1:1 USD/base ratio. Real callers MUST set the rate before
        # the bot ticks.
        self._chunk_size_usd: float = float(config.extractor_chunk_size_usd)
        self._chunk_to_base_rate: float = 1.0  # base/USD; set externally
        self._chunk_size_base: float = self._chunk_size_usd  # rebased when rate is set
        self._chunk_free_base: float = self._chunk_size_base
        self._chunk_extracted_total: float = 0.0  # cumulative base extracted

        # v3.20.72 Phase C-1 — USD-anchored sizing state (MEM-418).
        # Locked operator Q2: 10% rate-spike threshold with median-of-3
        # fallback. _recent_rates holds the last 3 accepted rate
        # samples; update_base_usd_rate() validates incoming rates
        # against the most recent sample and falls back to the median
        # of the trailing window if the spike is too large. Zero or
        # negative rates are REFUSED (fail-closed) — artillery sizing
        # defaults to the last-known-good rate until a valid update
        # arrives.
        self._recent_rates: list[float] = []  # last 3 accepted rates
        self._rate_spike_threshold_pct: float = 10.0
        self._rate_spike_window: int = 3
        self._rate_spike_events: int = 0  # diagnostic counter
        self._rate_refuse_events: int = 0  # zero/negative rate refusals

        # ── Hedge reserve (separate from chunk; powers corrections) ──
        # If extractor_hedge_budget_usd > 0, a separate base reserve
        # is provisioned. Corrections draw from hedge first; chunk
        # second. Until exhausted, chunk_free is protected.
        self._hedge_budget_usd: float = float(config.extractor_hedge_budget_usd)
        self._hedge_free_base: float = 0.0  # set in lock-step with rate

        # v3.20.72 Phase C-1 — back-reference to BotManager for profit
        # notifications (MEM-418). Set by BotManager.register() via
        # set_bot_manager(). When None, profit credits don't notify
        # the registry — preserves legacy test paths.
        self._bot_manager = None

        # ── Positions (one per pair, keyed by pair symbol) ──
        self._positions: dict[str, ExtractorPosition] = {}
        self._closed_position_log: list[dict] = []  # last 200 closed
        self._closed_log_max: int = 200

        # ── Top-N watch list (decision #5) ──
        self._watch_list: list[str] = []
        self._watch_list_refreshed_at_tick: int = -1
        self._tick_counter: int = 0

        # ── TA signal provider (one per bot; reused across pairs) ──
        # Indicator weights default; per-bot weights can be added later.
        self._ta_provider = TASignalProvider(
            exchange,
            timeframe=getattr(config, "ta_timeframe", self.DEFAULT_TIMEFRAME)
            or self.DEFAULT_TIMEFRAME,
            trend_strength_threshold=float(config.extractor_trend_strength_threshold),
        )

        # ── Per-position last-correction tick counters (for skip-candles) ──
        self._last_correction_tick: dict[str, int] = {}

        # ── Trade metrics ──
        self._cycle_extracted_total: float = 0.0  # this session
        self._lifetime_extracted_total: float = 0.0

        # ── v3.20.3 — Capital Reservation Registry token ──
        # Reserved at set_initial_chunk_rate (when base-unit chunk is
        # known); released at stop(). Heartbeat pulsed each tick.
        # None means "no reservation held" (either pre-rate-set or
        # post-release). The registry tolerates missing tokens
        # gracefully — operations are no-ops on None.
        # sadp: R28 FL  R68 DPA
        self._crr_token: Optional[str] = None

        self._initialised = False

    # ── Public chunk-rate setter ────────────────────────────────────

    def set_initial_chunk_rate(self, base_per_usd: float) -> None:
        """Rebase the chunk from USD to base units using the current
        base/USD rate. Called by BotManager (or test harness) BEFORE
        the bot's first tick so the chunk's base-unit denomination is
        captured at construction-time rates.

        After this call:
          self._chunk_size_base = self._chunk_size_usd / base_per_usd ???

        Actually we want: chunk_size_base such that
            chunk_size_base × base_USD_price = chunk_size_usd
        which means:
            chunk_size_base = chunk_size_usd / base_USD_price

        ``base_per_usd`` here is the *USD value per 1 base unit*
        (e.g. for ETH: ``3000``). So:
            chunk_size_base = chunk_size_usd / base_per_usd
        """
        if base_per_usd <= 0:
            logger.warning(
                "Bot %s set_initial_chunk_rate: rate %s invalid; "
                "leaving chunk at 1:1 default",
                self.bot_id,
                base_per_usd,
            )
            return
        self._chunk_to_base_rate = float(base_per_usd)
        # v3.20.74 Phase C-2 (MEM-420): Inverted Extractor standing-
        # position import per locked Q7. When direction="inverted" AND
        # inverted_extractor_standing_alt_units > 0, the chunk is
        # initialized from the operator's already-held ALT quantity
        # rather than from chunk_size_usd / rate. Sets the canonical
        # chunk_size_usd as an OBSERVATION (standing_units × rate)
        # rather than an INPUT, so downstream registry consultation
        # and per-tick re-anchoring see the correct USD value.
        _standing = float(
            getattr(self.config, "inverted_extractor_standing_alt_units", 0) or 0
        )
        if self._is_inverted and _standing > 0:
            self._chunk_size_base = _standing
            self._chunk_size_usd = _standing * base_per_usd
            logger.info(
                "Bot %s Inverted Extractor: imported standing "
                "position of %.6f ALT (= $%.2f at $%.4f/ALT)",
                self.bot_id,
                _standing,
                self._chunk_size_usd,
                base_per_usd,
            )
        else:
            self._chunk_size_base = self._chunk_size_usd / base_per_usd
        self._chunk_free_base = self._chunk_size_base
        if self._hedge_budget_usd > 0:
            self._hedge_free_base = self._hedge_budget_usd / base_per_usd

        # ── v3.20.3 — Capital Reservation Registry: SOURCE-side wiring ──
        # Operator design (2026-05-23):
        #   "when an Extractor Bot is created its own field populates
        #    with the amount of the Base Currency being used by any
        #    other bots so that there is no predation at any phase of
        #    these two or future bot types predating each others'
        #    resources."
        #
        # This is the moment the base-unit chunk count is concretely
        # known (was USD-denominated until now). Reserve the FULL
        # chunk + hedge with the registry so any concurrent
        # ScrummingBot on the same base_currency sees its effective
        # budget reduced by exactly this Extractor's claim.
        #
        # Reservation is in ASSET QUANTITY (not USD) — price-stable
        # through market moves. If ETH/USD drops 20%, the registry
        # still protects the same 0.0410 ETH the Extractor needs;
        # the displayed USD value of the reservation drops but the
        # underlying budget protection is unchanged.
        #
        # No explicit TTL — relies on heartbeat liveness. Bot.tick
        # pulses heartbeat; bot.stop releases. If the bot crashes
        # without releasing, HEARTBEAT_TTL (120s default) expires
        # the reservation automatically.
        #
        # Failure mode (R28 FL via log): if the registry call raises
        # (e.g., persisted state corrupted), we continue WITHOUT a
        # reservation. SB protection on this asset does not engage
        # for this Extractor's lifetime, but trading continues. The
        # smart_orders backstop (v3.20.1) and SB decision-gate
        # (v3.20.2) provide the only-when-bot_id-passed coverage.
        # Investigate at next operator opportunity.
        # sadp: R28 FL  R68 DPA
        base_asset = (self.config.base_currency or "").upper()
        total_reserved_base = self._chunk_size_base + self._hedge_free_base
        if base_asset and total_reserved_base > 0:
            try:
                from .capital_reservation import get_registry as _crr_get_registry

                _crr_reg = _crr_get_registry()
                self._crr_token = _crr_reg.reserve(
                    bot_id=self.bot_id,
                    asset=base_asset,
                    qty=total_reserved_base,
                    reason=(
                        f"Extractor chunk + hedge — "
                        f"chunk_usd=${self._chunk_size_usd:.2f}, "
                        f"hedge_usd=${self._hedge_budget_usd:.2f}, "
                        f"base_per_usd={base_per_usd:.6g}"
                    ),
                    bot_kind="extractor",
                )
                logger.info(
                    "Bot %s reserved %.10g %s with "
                    "CapitalReservationRegistry (token %s, "
                    "chunk_usd=$%.2f hedge_usd=$%.2f)",
                    self.bot_id,
                    total_reserved_base,
                    base_asset,
                    self._crr_token[:8] if self._crr_token else "?",
                    self._chunk_size_usd,
                    self._hedge_budget_usd,
                )
            except (
                Exception
            ) as _crr_exc:  # R28-OK: registry-call defensive; primary trading path unaffected
                logger.warning(
                    "Bot %s capital reservation at chunk-rate-set "
                    "raised %s: %s — continuing without reservation. "
                    "Concurrent ScrummingBot on %s will NOT see this "
                    "Extractor's claim. Investigate registry state.",
                    self.bot_id,
                    type(_crr_exc).__name__,
                    _crr_exc,
                    base_asset,
                )
                self._crr_token = None

    # ── v3.20.5 — Live-update for operator-edited Pool Size ─────────
    #
    # Operator-reported 2026-05-23: "updating the Chunk / Pool Size
    # field is not updating the numeric readouts in the bot list."
    # Root cause: `_chunk_size_usd` and `_chunk_size_base` are
    # snapshotted from `config.extractor_chunk_size_usd` at __init__
    # / set_initial_chunk_rate; nothing re-reads from config later.
    # Settings dialog's setattr(cfg, ...) path updates the persisted
    # field but leaves the runtime stale.
    #
    # This method is the runtime-routed entry point that
    # `bot_live_settings._RUNTIME_ROUTED` calls when the operator
    # edits Pool Size on a RUNNING Extractor. It updates BOTH the
    # config and the runtime, in lockstep — same discipline as
    # Session 26's settings-to-functions audit applied to SBs.
    #
    # Behavior:
    #   • Updates self._chunk_size_usd (operator-set USD denomination)
    #   • Recomputes self._chunk_size_base from current chunk_to_base
    #     rate (price-stable; preserves the operator's USD intent)
    #   • Scales self._chunk_free_base proportionally so the
    #     deployed-vs-free *ratio* is preserved (a 50%-deployed bot
    #     stays 50% deployed across the resize; open positions are
    #     not disturbed). If the new chunk is smaller than what's
    #     currently deployed, free → 0 and the bot will recover via
    #     natural extraction cycles.
    #   • Resizes the CapitalReservationRegistry claim via update()
    #     so concurrent ScrummingBots see the new claim immediately.
    #   • Returns {"applied": True, ...} on success, {"applied":
    #     False, "reason": "..."} on no-op (operator routing layer
    #     uses this to log accurately).
    #
    # Hedge is left alone — separate operator field, separate
    # reservation contribution. If/when a Hedge Size live-edit is
    # added, follow the same pattern.
    #
    # sadp: R28 FL  R55 GOV  R62 FRG  R68 DPA  R76 DMW

    def set_chunk_size_usd(self, new_value: float) -> dict:
        """Apply a new operator-set Pool Size (USD) to a running bot.

        See module-level comment block above for full design.
        Idempotent: a no-change call is a clean no-op.
        """
        try:
            new_value = float(new_value)
        except (TypeError, ValueError):
            return {"applied": False, "reason": "value not numeric"}
        if new_value <= 0:
            return {"applied": False, "reason": "Pool Size must be > 0"}

        old_usd = float(self._chunk_size_usd)
        if abs(new_value - old_usd) < 1e-9:
            return {"applied": False, "reason": "no change"}

        old_base = float(self._chunk_size_base)
        old_free_base = float(self._chunk_free_base)
        rate = float(self._chunk_to_base_rate or 0.0)

        # Recompute base-unit chunk from operator's USD intent at the
        # rate captured at construction. If rate hasn't been set
        # (pre-first-tick), keep the 1:1 default behavior — chunk_base
        # tracks chunk_usd directly. The next set_initial_chunk_rate
        # call will rebase from the real rate.
        self._chunk_size_usd = new_value
        self.config.extractor_chunk_size_usd = new_value
        if rate > 0:
            new_chunk_base = new_value / rate
        else:
            new_chunk_base = new_value  # 1:1 fallback (pre-rate-set)

        # Scale free in proportion. Preserve deployed-vs-free RATIO
        # across the resize so we don't suddenly claim phantom free
        # base units the bot doesn't actually own. If old_base was 0
        # (pre-rate-set), set free = new (all-free by default).
        if old_base > 0:
            free_ratio = old_free_base / old_base
            free_ratio = max(0.0, min(1.0, free_ratio))
            new_free_base = new_chunk_base * free_ratio
        else:
            new_free_base = new_chunk_base
        self._chunk_size_base = new_chunk_base
        self._chunk_free_base = new_free_base

        # Update the registry claim so concurrent SBs see the new
        # number on their next decision tick.
        registry_updated = False
        if self._crr_token is not None:
            try:
                from .capital_reservation import get_registry as _crr_get_registry

                _crr_reg = _crr_get_registry()
                new_total_base = self._chunk_size_base + self._hedge_free_base
                # Registry.update signature: (token, bot_id, new_qty).
                # No reason field — the registry tracks the
                # original `reason` from reserve(); the update is a
                # pure size adjustment. Audit trail lives in our
                # logger.info below.
                _crr_reg.update(self._crr_token, self.bot_id, new_total_base)
                registry_updated = True
            except (
                Exception
            ) as _crr_exc:  # R28-OK: registry update best-effort; in-process state is authoritative
                logger.warning(
                    "Bot %s set_chunk_size_usd: registry update "
                    "raised %s: %s — in-process chunk state is "
                    "still updated, but concurrent ScrummingBot "
                    "will see the OLD claim until heartbeat-driven "
                    "refresh or restart.",
                    self.bot_id,
                    type(_crr_exc).__name__,
                    _crr_exc,
                )

        logger.info(
            "Bot %s Pool Size live-updated: $%.2f → $%.2f "
            "(chunk_base %.10g → %.10g, free_base %.10g → %.10g, "
            "registry_updated=%s)",
            self.bot_id,
            old_usd,
            new_value,
            old_base,
            new_chunk_base,
            old_free_base,
            new_free_base,
            registry_updated,
        )
        return {
            "applied": True,
            "old_usd": old_usd,
            "new_usd": new_value,
            "old_chunk_base": old_base,
            "new_chunk_base": new_chunk_base,
            "registry_updated": registry_updated,
        }

    # ── Lifecycle override: release reservation on stop ─────────────

    async def stop(self) -> None:
        """v3.20.3 — release the capital reservation, then delegate
        to BotContainer.stop() for the standard shutdown path.

        If release fails (e.g., registry corrupted), log and continue —
        the heartbeat-staleness pruner in the registry will eventually
        collect the reservation, and the smart_orders + SB gates will
        keep functioning either way.

        sadp: R28 FL  R68 DPA
        """
        if self._crr_token is not None:
            try:
                from .capital_reservation import get_registry as _crr_get_registry

                _crr_reg = _crr_get_registry()
                _crr_reg.release(self._crr_token, self.bot_id)
                logger.info(
                    "Bot %s released capital reservation %s on stop()",
                    self.bot_id,
                    self._crr_token[:8] if self._crr_token else "?",
                )
                self._crr_token = None
            except (
                Exception
            ) as _crr_exc:  # R28-OK: release best-effort; heartbeat-staleness pruner is the backstop
                logger.warning(
                    "Bot %s capital reservation release at stop raised "
                    "%s: %s — leaving for heartbeat-staleness prune.",
                    self.bot_id,
                    type(_crr_exc).__name__,
                    _crr_exc,
                )
                # NOTE: do NOT clear self._crr_token here. If the
                # bot is restarted, init won't double-reserve because
                # set_initial_chunk_rate is called fresh; the old
                # token will simply be orphaned and pruned by TTL.
        await super().stop()

    # ── Capacity check ──────────────────────────────────────────────

    def _has_chunk_capacity(self, artillery_base: float) -> bool:
        """Return True iff this bot's claim-aware free chunk has room
        for one more artillery round of `artillery_base` base units.

        Reserve is computed against ``chunk_size_base`` (the operator's
        allocation), NOT ``chunk_free_base``, so corrections that have
        drained the chunk can't be papered over by the reserve math.

        Sibling claims are NOT subtracted from chunk_size_base here —
        each Extractor's chunk is its own allocation and the cross-bot
        check is enforced by ScrummingBot's claim-aware quote read
        (v3.18.18 §13a). Operator over-allocation surfaces at the
        ScrummingBot side, not here.
        """
        reserve = self._chunk_size_base * (
            self.config.extractor_pool_reserve_pct / 100.0
        )
        return (self._chunk_free_base - artillery_base) >= reserve

    # ── Pool color (for GUI / dashboard) ─────────────────────────────

    def pool_color(self) -> str:
        """Green / yellow / red traffic-light status of the pool.

        green  — no open positions; pool fully in base
        yellow — positions open, none in drawdown
        red    — at least one position in drawdown (USD value below
                 artillery_size × (1 - drawdown_threshold_pct/100))
        """
        if not self._positions:
            return "green"
        for pos in self._positions.values():
            if pos.state == POSITION_STATE_DRAWDOWN:
                return "red"
        return "yellow"

    # ── Watch-list refresh ──────────────────────────────────────────

    async def _refresh_watch_list(self) -> None:
        """Refresh the watch list — TWO MODES per operator spec
        (v3.19.27 closes a design contradiction):

          MODE A — MANUAL OVERRIDE (config.extractor_alt_targets is non-empty):
            The operator selected specific alt pairs in the wizard
            (ExtractorPoolPage multi-select). The bot uses EXACTLY
            those symbols, filtered to base-matching, and validated
            against the current exchange markets (delisted pairs
            dropped with a debug log). No top-N re-ranking by volume.

          MODE B — AUTO-SCAN (config.extractor_alt_targets is empty):
            The original §6 design — re-rank top-N */<base> pairs by
            24h volume every extractor_scan_refresh_candles ticks.

        BOTH modes:
          • Refresh on the same cadence (extractor_scan_refresh_candles).
          • Preserve pairs with open positions — never abandon mid-
            cycle positions even if they fell out of top-N (Mode B)
            or were de-selected by the operator (Mode A, unlikely
            mid-cycle but defensive).

        Failure modes (R28 fail-safe): if exchange.get_markets or
        get_ticker raises, the watch list is preserved as-is. The
        bot continues operating against the previous list. A repeated
        failure pattern would surface via the operator dashboard.
        """
        base = (self.config.base_currency or "").upper()
        if not base:
            return

        # v3.19.27 — operator manual-override list takes precedence.
        # Filter to base-matching + exchange-active; preserve open positions.
        manual_targets = list(getattr(self.config, "extractor_alt_targets", []) or [])

        if manual_targets:
            # MODE A — MANUAL OVERRIDE
            try:
                markets = await self.exchange.get_markets()
            except Exception as exc:  # R28-OK: best-effort refresh
                logger.debug(
                    "Bot %s _refresh_watch_list (manual): get_markets " "raised %s: %s",
                    self.bot_id,
                    type(exc).__name__,
                    exc,
                )
                return

            # Index active markets by symbol for O(1) validation
            # v3.20.74 Phase C-2 (MEM-420): mode-aware filter via
            # _pair_filter_matches — Normal keeps */{base}, Inverted
            # keeps {base}/*.
            active_symbols: set[str] = set()
            for m in markets:
                try:
                    if not self._pair_filter_matches(m):
                        continue
                    m_symbol = getattr(m, "symbol", None) or getattr(m, "id", None)
                    if m_symbol:
                        active_symbols.add(m_symbol)
                except Exception as exc:  # R28-OK: skip malformed entries
                    logger.debug(
                        "Bot %s _refresh_watch_list (manual): market entry "
                        "raised %s: %s — entry skipped, scan continues",
                        self.bot_id,
                        type(exc).__name__,
                        exc,
                    )
                    continue

            new_watch: list[str] = []
            dropped: list[str] = []
            for sym in manual_targets:
                if sym in active_symbols:
                    new_watch.append(sym)
                else:
                    dropped.append(sym)
            if dropped:
                logger.info(
                    "Bot %s manual watch-list: %d operator-selected "
                    "pair(s) dropped (delisted or wrong base): %s",
                    self.bot_id,
                    len(dropped),
                    dropped,
                )
        else:
            # MODE B — AUTO-SCAN top-N by 24h volume (original §6 design)
            try:
                markets = await self.exchange.get_markets()
            except Exception as exc:  # R28-OK: best-effort refresh
                logger.debug(
                    "Bot %s _refresh_watch_list (auto): get_markets " "raised %s: %s",
                    self.bot_id,
                    type(exc).__name__,
                    exc,
                )
                return

            # v3.20.74 Phase C-2 (MEM-420): mode-aware candidate
            # filter. Normal scans */{base}; Inverted scans {base}/*.
            candidates: list[str] = []
            for m in markets:
                try:
                    if not self._pair_filter_matches(m):
                        continue
                    m_symbol = getattr(m, "symbol", None) or getattr(m, "id", None)
                    if m_symbol:
                        candidates.append(m_symbol)
                except Exception as exc:  # R28-OK: skip malformed market entries
                    logger.debug(
                        "Bot %s _refresh_watch_list (auto): market entry "
                        "raised %s: %s — entry skipped, scan continues",
                        self.bot_id,
                        type(exc).__name__,
                        exc,
                    )
                    continue

            if not candidates:
                return

            # Pull 24h volume for each (best-effort; if a ticker fails,
            # that pair is dropped from THIS refresh and may reappear next).
            ranked: list[tuple[str, float]] = []
            for sym in candidates:
                try:
                    ticker = await self.exchange.get_ticker(sym)
                    vol = float(getattr(ticker, "volume_24h", 0) or 0)
                    ranked.append((sym, vol))
                except Exception as exc:  # R28-OK: per-symbol probe failure
                    logger.debug(
                        "Bot %s _refresh_watch_list: get_ticker(%s) raised "
                        "%s: %s — pair dropped from this refresh only",
                        self.bot_id,
                        sym,
                        type(exc).__name__,
                        exc,
                    )
                    continue

            ranked.sort(key=lambda x: x[1], reverse=True)
            top_n = int(self.config.extractor_scan_top_n)
            top_n = max(5, min(10, top_n))  # design doc range
            new_watch = [sym for sym, _ in ranked[:top_n]]

        # Both modes: preserve pairs with open positions even if they
        # fell out of the new watch (auto: dropped from top-N; manual:
        # operator de-selected mid-cycle — defensive against rogue
        # config edits that would orphan an open position).
        for pair in list(self._positions.keys()):
            if pair not in new_watch:
                new_watch.append(pair)

        self._watch_list = new_watch
        self._watch_list_refreshed_at_tick = self._tick_counter

    def _watch_list_due_for_refresh(self) -> bool:
        if self._watch_list_refreshed_at_tick < 0:
            return True
        ticks_since = self._tick_counter - self._watch_list_refreshed_at_tick
        return ticks_since >= int(self.config.extractor_scan_refresh_candles)

    # ── USD ↔ base conversion ───────────────────────────────────────

    def _usd_to_base(self, usd: float) -> float:
        """Convert USD to base-currency units using cached chunk rate."""
        if self._chunk_to_base_rate <= 0:
            return 0.0
        return float(usd) / float(self._chunk_to_base_rate)

    def _base_to_usd(self, base: float) -> float:
        """Convert base-currency units to USD via cached chunk rate."""
        return float(base) * float(self._chunk_to_base_rate)

    # ── v3.20.74 Phase C-2 — Inverted Extractor (MEM-420) ─────────────

    @property
    def _is_inverted(self) -> bool:
        """True if this bot is running the Inverted Extractor direction
        (ammo = ALT, sells first into quote, buys back more alt).
        Locked Q8: single mode field on BotConfig; reads via getattr
        with `"normal"` default so legacy configs are forward-compat."""
        direction = (
            getattr(self.config, "extractor_direction", "normal") or "normal"
        ).lower()
        return direction == "inverted"

    def _pair_filter_matches(self, market) -> bool:
        """Mode-aware pair filter for `_refresh_watch_list`. Returns
        True if the given market's symbol belongs in this bot's
        scanning universe.

        - Normal Extractor (`*/{base}` pairs): keeps markets whose
          QUOTE side equals the configured `base_currency`. Example:
          base=USDC → matches LINK/USDC, ETH/USDC, etc.
        - Inverted Extractor (`{base}/*` pairs): keeps markets whose
          BASE side equals the configured `base_currency` (where
          `base_currency` is the ALT operator owns). Example:
          base=LINK → matches LINK/USDC, LINK/BTC, LINK/ETH, etc.
        """
        try:
            if not getattr(market, "active", True):
                return False
            base = (self.config.base_currency or "").upper()
            if not base:
                return False
            if self._is_inverted:
                m_base = (getattr(market, "base", "") or "").upper()
                return m_base == base
            m_quote = (getattr(market, "quote", "") or "").upper()
            return m_quote == base
        except Exception:  # R28-OK: defensive market filter
            return False

    def _entry_signal_matched(self, snapshot) -> bool:
        """Mode-aware entry trigger.

        - Normal: fires on BEARISH signal (mirrors Scrumming's FOLD
          entry — buy when bearish).
        - Inverted: fires on BULLISH signal (sells alt when bullish on
          LINK/BTC means LINK is overbought vs BTC; we sell to capture
          the relative outperformance, plan to buy back lower).
        """
        if snapshot is None:
            return False
        if self._is_inverted:
            return bool(getattr(snapshot, "is_bullish", False))
        return bool(getattr(snapshot, "is_bearish", False))

    def _exit_signal_matched(self, snapshot) -> bool:
        """Mode-aware exit trigger.

        - Normal: fires on BULLISH signal (sell alt when bullish).
        - Inverted: fires on BEARISH signal (buy back ammo when LINK
          is oversold vs the quote — we close the inverted position
          by re-acquiring ALT).
        """
        if snapshot is None:
            return False
        if self._is_inverted:
            return bool(getattr(snapshot, "is_bearish", False))
        return bool(getattr(snapshot, "is_bullish", False))

    def _entry_order_side(self):
        """OrderSide for artillery entry: BUY for Normal, SELL for
        Inverted."""
        from ..exchange.base import OrderSide

        return OrderSide.SELL if self._is_inverted else OrderSide.BUY

    def _exit_order_side(self):
        """OrderSide for position exit: SELL for Normal, BUY for
        Inverted (close the inverted short by buying back the alt)."""
        from ..exchange.base import OrderSide

        return OrderSide.BUY if self._is_inverted else OrderSide.SELL

    def set_bot_manager(self, manager) -> None:
        """v3.20.72 Phase C-1 — accept back-reference to BotManager so
        profit credits can call notify_bot_profit() and trigger
        CapitalRegistry.grow_reservation(). Called by BotManager.register
        during bot lifecycle wire-up (mirror of the existing
        ScrummingBot.set_bot_manager pattern at scrumming_bot.py:696)."""
        self._bot_manager = manager

    def update_base_usd_rate(self, rate_base_per_usd: float) -> tuple[bool, str]:
        """v3.20.72 Phase C-1 — USD-anchored sizing rate update (MEM-418).

        Operator's stated intent: "fires an artillery round of a given
        USD value that is executed in converted terms of the selected
        base currency." Each artillery shot is sized at the CURRENT
        price, not the construction-time snapshot. Callers (tick
        loop / TASignalProvider cache / connector ticker) invoke this
        each tick with the live rate.

        Locked Q2 validations:

        - **Zero/negative**: REFUSED (fail-closed). The last-known-good
          rate stays in effect; artillery sizing continues to use it.
          ``_rate_refuse_events`` increments for diagnostic visibility.
        - **>10% divergence from most recent sample**: SPIKE-PROTECTED.
          Single-tick ticker glitches shouldn't propagate. Falls back
          to the MEDIAN of the last 3 accepted samples (or the most
          recent sample if fewer than 3 are buffered). ``_rate_spike_
          events`` increments.
        - **Otherwise**: ACCEPTED. ``_chunk_to_base_rate`` updates and
          the sample is appended to ``_recent_rates`` (trimmed to 3).

        Returns ``(accepted, reason)``. ``reason`` is a short string
        suitable for operator logs.
        """
        # Fail-closed on zero / negative — the rate must be positive.
        if rate_base_per_usd is None or rate_base_per_usd <= 0:
            self._rate_refuse_events += 1
            return False, (
                f"refused: invalid rate {rate_base_per_usd!r} " f"(must be > 0)"
            )
        new_rate = float(rate_base_per_usd)

        # First-ever update: accept unconditionally.
        if not self._recent_rates:
            self._recent_rates.append(new_rate)
            self._chunk_to_base_rate = new_rate
            return True, "accepted (first sample)"

        # Spike check against the MOST RECENT accepted sample.
        last_rate = self._recent_rates[-1]
        # Defensive: last_rate should always be > 0 at this point, but
        # guard against future regression.
        if last_rate <= 0:  # R28-OK: defensive guard; window should hold > 0
            self._recent_rates = [new_rate]
            self._chunk_to_base_rate = new_rate
            return True, "accepted (recovered from invalid window)"

        # UNITS, MADE EXPLICIT.
        # `abs(new_rate - last_rate) / last_rate` is a price over a
        # price: a dimensionless RATIO, 0.1 for a tenth. The threshold
        # is stated in PERCENT — `_rate_spike_threshold_pct` is 10.0 and
        # means 10%. The old line scaled the measurement UP by 100 and
        # compared it to the threshold's bare magnitude, so the two
        # sides of the `>` only matched by convention, not by units.
        # Converting the threshold DOWN into ratio space once puts both
        # sides in the same unit and leaves the rule identical.
        divergence_ratio = abs(new_rate - last_rate) / last_rate
        spike_limit_ratio = self._rate_spike_threshold_pct / PERCENT_PER_RATIO_UNIT
        if divergence_ratio > spike_limit_ratio:
            # Spike detected. Use median of buffered window as the
            # actual rate for this tick. The fresh sample is NOT
            # appended to the window — preserves the median-of-recent
            # fallback property across consecutive spikes.
            self._rate_spike_events += 1
            window = sorted(self._recent_rates)
            mid = len(window) // 2
            if len(window) % 2 == 1:
                median = window[mid]
            else:
                median = (window[mid - 1] + window[mid]) / 2.0
            self._chunk_to_base_rate = median
            return False, (
                f"spike-protected: incoming {new_rate:.6f} diverges "
                f"{divergence_ratio * PERCENT_PER_RATIO_UNIT:.2f}% from "
                f"last {last_rate:.6f}; "
                f"using median {median:.6f} of window"
            )

        # Normal acceptance — update the chunk rate and append to
        # the trailing window (trim to spike_window samples).
        self._recent_rates.append(new_rate)
        if len(self._recent_rates) > self._rate_spike_window:
            self._recent_rates = self._recent_rates[-self._rate_spike_window :]
        self._chunk_to_base_rate = new_rate
        return True, "accepted"

    # ── State-machine evaluators ────────────────────────────────────

    def _position_value_usd(
        self,
        pos: ExtractorPosition,
        alt_price_in_base: float,
    ) -> float:
        """Current USD value of the position via double-layer valuation
        (design doc §6a). alt_units × alt_price_in_base × base_per_USD."""
        return pos.alt_units * alt_price_in_base * self._chunk_to_base_rate

    def _is_in_drawdown(
        self,
        pos: ExtractorPosition,
        alt_price_in_base: float,
    ) -> bool:
        """USD-anchored drawdown check (design doc §6a).

        ``pos.artillery_size_usd_at_entry`` is snapshotted at FIRING
        and never updated — that's our USD floor. Drawdown fires when
        current USD value drops `drawdown_threshold_pct` below entry.
        """
        current_usd = self._position_value_usd(pos, alt_price_in_base)
        threshold = pos.artillery_size_usd_at_entry * (
            1.0 - self.config.extractor_drawdown_threshold_pct / 100.0
        )
        return current_usd < threshold

    def _exit_is_profitable_in_base(
        self,
        pos: ExtractorPosition,
        alt_price_in_base: float,
    ) -> bool:
        """Per design doc §6a: the point of the Extractor is growing
        BASE UNIT COUNT. Even if a bullish signal fires, refuse the
        exit if the proportional sell would net FEWER base units than
        we put in (after fees).

        Returns True iff sell would net MORE base units than the
        proportional cost basis.
        """
        units_to_sell = pos.alt_units * (self.config.extractor_exit_pct / 100.0)
        base_back = units_to_sell * alt_price_in_base
        fee_pct = float(getattr(self.config, "trading_fee_pct", 0.6))
        base_back_after_fee = base_back * (1.0 - fee_pct / 100.0)
        base_in_proportional = pos.cost_basis_base * (
            self.config.extractor_exit_pct / 100.0
        )
        return base_back_after_fee > base_in_proportional

    # ── Pair action evaluation ──────────────────────────────────────

    async def _evaluate_open_position(
        self,
        pos: ExtractorPosition,
        snapshot: TASnapshot,
        alt_price_in_base: float,
    ) -> None:
        """Drive an open position through its state transitions."""
        # Drawdown check first (sub-state of IN_FLIGHT).
        in_drawdown = self._is_in_drawdown(pos, alt_price_in_base)
        if in_drawdown:
            pos.state = POSITION_STATE_DRAWDOWN
        elif pos.state == POSITION_STATE_DRAWDOWN:
            # Recovery — drop back to IN_FLIGHT
            pos.state = POSITION_STATE_IN_FLIGHT

        # Drawdown correction (averaging-down) — gated by skip-candles
        # and cost-basis-multiple ceiling.
        if in_drawdown:
            await self._maybe_fire_correction(pos, alt_price_in_base)
            return

        # Mode-aware exit. v3.20.74 Phase C-2 (MEM-420): Normal exits
        # on BULLISH (sell alt high); Inverted exits on BEARISH (buy
        # back alt cheap to close the inverted short).
        if self._exit_signal_matched(snapshot) and self._exit_is_profitable_in_base(
            pos, alt_price_in_base
        ):
            pos.state = POSITION_STATE_BULLISH_EXIT
            await self._execute_bullish_exit(pos, alt_price_in_base)
            return

    async def _maybe_fire_correction(
        self,
        pos: ExtractorPosition,
        alt_price_in_base: float,
    ) -> None:
        """Average-down to maintain notional (design doc §7).

        Three gates:
          1. Skip-candles: at least extractor_correction_skip_candles
             must have elapsed since the last correction on this position.
          2. Hedge-or-chunk has budget: if hedge_free > 0 use it;
             else fall through to chunk_free. If neither has room,
             return without firing.
          3. Cost-basis-multiple ceiling: cost_basis_base must be below
             artillery_size_base × max_cost_basis_multiple. At ceiling,
             hold and wait for bullish exit.
        """
        last_tick = self._last_correction_tick.get(pos.pair, -(10**9))
        if self._tick_counter - last_tick < int(
            self.config.extractor_correction_skip_candles
        ):
            return  # skip-candles throttle

        max_basis = pos.artillery_size_base * float(
            self.config.extractor_max_cost_basis_multiple
        )
        headroom = max_basis - pos.cost_basis_base
        if headroom <= 0:
            return  # hard floor reached; wait for bullish exit

        # Compute deficit in base units to bring USD value back up to
        # original artillery_size_usd_at_entry.
        current_value_usd = self._position_value_usd(pos, alt_price_in_base)
        deficit_usd = pos.artillery_size_usd_at_entry - current_value_usd
        if deficit_usd <= 0:
            return  # no longer in drawdown
        deficit_base = self._usd_to_base(deficit_usd)
        add_amount_base = min(deficit_base, headroom)

        # Hedge-first capital sourcing.
        from_hedge = min(add_amount_base, self._hedge_free_base)
        from_chunk = add_amount_base - from_hedge
        if from_chunk > self._chunk_free_base:
            # Trim to available chunk
            from_chunk = self._chunk_free_base
            add_amount_base = from_hedge + from_chunk
        if add_amount_base <= 0:
            return  # no capital available

        # MEM-257 fail-closed check on the alt side
        target_asset = pos.pair.split("/")[0]
        verified, refuse = await verify_buy_safe_or_refuse(
            self.exchange,
            target_asset,
            expected_units=pos.alt_units,
            path="extractor_correction",
        )
        if refuse:
            self._bus.emit("bot.log", bot_id=self.bot_id, message=refuse)
            logger.warning("Bot %s %s", self.bot_id, refuse)
            return

        # v3.20.74 Phase C-2 (MEM-420): mode-aware order side.
        # Normal correction = BUY more alt at the lower price.
        # Inverted correction = SELL more alt (the alt has gone
        # FURTHER in the entry direction; we add to the inverted
        # position to lower the cost basis on the rebound).
        alt_units_to_buy = add_amount_base / alt_price_in_base
        try:
            order = await self.guarded_place_order(
                symbol=pos.pair,
                side=self._entry_order_side(),
                order_type=OrderType.MARKET,
                amount=alt_units_to_buy,
                price=None,
            )
        except Exception as exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"EXTRACTOR CORRECTION FAILED on {pos.pair}: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
            logger.exception("Extractor correction failed")
            return

        if order is None:
            return

        # Update position state — debit capital from hedge first, then chunk
        filled_units = float(
            getattr(order, "filled", None)
            or getattr(order, "amount", None)
            or alt_units_to_buy
        )
        fill_price = float(
            getattr(order, "average_price", None)
            or getattr(order, "average", None)
            or getattr(order, "price", None)
            or alt_price_in_base
        )
        actual_base_spent = filled_units * fill_price
        # Re-split actual_base_spent between hedge and chunk in same ratio
        if add_amount_base > 0:
            hedge_share = from_hedge / add_amount_base
            chunk_share = from_chunk / add_amount_base
        else:
            hedge_share = 0.0
            chunk_share = 1.0
        self._hedge_free_base -= actual_base_spent * hedge_share
        self._chunk_free_base -= actual_base_spent * chunk_share
        pos.alt_units += filled_units
        pos.cost_basis_base += actual_base_spent
        if pos.alt_units > 0:
            pos.avg_buy_price_base_per_alt = pos.cost_basis_base / pos.alt_units
        pos.corrections_fired += 1
        pos.last_correction_ts = time.time()
        self._last_correction_tick[pos.pair] = self._tick_counter
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"EXTRACTOR CORRECTION: {pos.pair} averaged down "
                f"{filled_units:.6f} units @ {fill_price:.8f} "
                f"(spent {actual_base_spent:.8f} base). "
                f"Position now {pos.alt_units:.6f} units, "
                f"cost_basis {pos.cost_basis_base:.8f} base, "
                f"corrections={pos.corrections_fired}/"
                f"{int(self.config.extractor_max_cost_basis_multiple)}x cap."
            ),
        )

    async def manual_fire_position(self, pair: str) -> dict:
        """v3.19.3 — operator-initiated Manual Fire on a SINGLE position.

        Per the Extractor design doc decision #7, each open position has
        its own Manual Fire button in the detail-dialog Positions Held
        tab. Clicking it calls THIS method, which closes the specific
        position at current market price.

        Operator-sovereignty (v3.18.15 invariant carry-over to Extractor):
        Manual Fire bypasses gates the auto path would respect.
        Specifically:
          • The base-unit-profitability gate (``_exit_is_profitable_in_base``)
            is DELIBERATELY SKIPPED — operator brings independent
            verification the bot doesn't have (e.g., visible market
            news, strategic decision to release capital).
          • The position is closed in FULL regardless of
            ``extractor_exit_pct`` — manual fire is an immediate full
            release, not the auto partial-exit semantic.
          • Compounding-tier roll-vs-lock logic still applies on the
            realized gain; operator does NOT lose the tier accounting.

        Returns a status dict the GUI consumes:
          {"success": bool, "pair": str, "reason": str,
           "alt_units_closed": float, "base_received": float,
           "gain_base": float, "log_message": str}

        sadp: R28 R55  # manual override: fail-loudly + invariant-preserving
        """
        pos = self._positions.get(pair)
        if pos is None:
            return {
                "success": False,
                "pair": pair,
                "reason": f"no open position for {pair}",
                "alt_units_closed": 0.0,
                "base_received": 0.0,
                "gain_base": 0.0,
                "log_message": (
                    f"EXTRACTOR MANUAL FIRE: refused — no open position "
                    f"for {pair}. Watch list may show the pair but no "
                    f"artillery is in flight."
                ),
            }

        # Fetch current price (base-per-alt) for the close.
        try:
            ticker = await self.exchange.get_ticker(pair)
            alt_price_in_base = float(ticker.last)
        except Exception as exc:
            msg = (
                f"EXTRACTOR MANUAL FIRE {pair}: ticker fetch raised "
                f"{type(exc).__name__}: {exc}. Refusing to fire on "
                f"uncertain price."
            )
            self._bus.emit("bot.log", bot_id=self.bot_id, message=msg)
            logger.warning("Bot %s %s", self.bot_id, msg)
            return {
                "success": False,
                "pair": pair,
                "reason": f"ticker fetch failed: {exc}",
                "alt_units_closed": 0.0,
                "base_received": 0.0,
                "gain_base": 0.0,
                "log_message": msg,
            }
        if alt_price_in_base <= 0:
            msg = (
                f"EXTRACTOR MANUAL FIRE {pair}: ticker.last "
                f"non-positive ({alt_price_in_base}). Refusing."
            )
            self._bus.emit("bot.log", bot_id=self.bot_id, message=msg)
            return {
                "success": False,
                "pair": pair,
                "reason": "non-positive price",
                "alt_units_closed": 0.0,
                "base_received": 0.0,
                "gain_base": 0.0,
                "log_message": msg,
            }

        # Emit the operator-narrative log BEFORE execution so the trail
        # records the intent even if the order placement raises.
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"EXTRACTOR MANUAL FIRE: operator requested close of "
                f"{pair} ({pos.alt_units:.6f} units @ "
                f"${alt_price_in_base:.8f}). Bypassing "
                f"base-unit-profitability gate per operator-sovereignty "
                f"invariant (v3.18.15)."
            ),
        )

        # Snapshot pre-close state for the return dict
        units_before = pos.alt_units
        cost_basis_before = pos.cost_basis_base

        # Force a 100% exit regardless of the configured
        # ``extractor_exit_pct`` — manual fire is an immediate full
        # release. Temporarily override exit_pct on the config in-memory;
        # restore after the call.
        _original_exit_pct = float(self.config.extractor_exit_pct)
        try:
            self.config.extractor_exit_pct = 100.0
            await self._execute_bullish_exit(pos, alt_price_in_base)
        except Exception as exc:
            self.config.extractor_exit_pct = _original_exit_pct
            msg = (
                f"EXTRACTOR MANUAL FIRE {pair}: exit raised "
                f"{type(exc).__name__}: {exc}."
            )
            self._bus.emit("bot.log", bot_id=self.bot_id, message=msg)
            logger.exception("Manual fire on extractor position failed")
            return {
                "success": False,
                "pair": pair,
                "reason": f"exit raised: {exc}",
                "alt_units_closed": 0.0,
                "base_received": 0.0,
                "gain_base": 0.0,
                "log_message": msg,
            }
        finally:
            self.config.extractor_exit_pct = _original_exit_pct

        # Position is removed from _positions by _execute_bullish_exit
        # on full exit. The last entry in _closed_position_log is THIS
        # close — read it for the return dict.
        last_close = self._closed_position_log[-1] if self._closed_position_log else {}
        return {
            "success": True,
            "pair": pair,
            "reason": "operator manual fire",
            "alt_units_closed": float(
                last_close.get("alt_units_initial", units_before)
            ),
            "base_received": float(last_close.get("base_received", 0.0)),
            "gain_base": float(last_close.get("gain_base", 0.0)),
            "log_message": (
                f"EXTRACTOR MANUAL FIRE COMPLETE: {pair} closed "
                f"{units_before:.6f} units; received "
                f"{last_close.get('base_received', 0.0):.8f} base; "
                f"gain {last_close.get('gain_base', 0.0):+.8f} base."
            ),
        }

    async def _execute_bullish_exit(
        self,
        pos: ExtractorPosition,
        alt_price_in_base: float,
    ) -> None:
        """Sell extractor_exit_pct of the position back to base."""
        units_to_sell = pos.alt_units * (self.config.extractor_exit_pct / 100.0)
        if units_to_sell <= 0:
            return

        # v3.20.74 Phase C-2 (MEM-420): mode-aware exit side.
        # Normal exit = SELL alt for base. Inverted exit = BUY alt
        # back from the quote (close the inverted short).
        try:
            order = await self.guarded_place_order(
                symbol=pos.pair,
                side=self._exit_order_side(),
                order_type=OrderType.MARKET,
                amount=units_to_sell,
                price=None,
            )
        except Exception as exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"EXTRACTOR EXIT FAILED on {pos.pair}: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
            logger.exception("Extractor exit failed")
            return

        if order is None:
            return

        filled_units = float(
            getattr(order, "filled", None)
            or getattr(order, "amount", None)
            or units_to_sell
        )
        fill_price = float(
            getattr(order, "average_price", None)
            or getattr(order, "average", None)
            or getattr(order, "price", None)
            or alt_price_in_base
        )
        base_received = filled_units * fill_price
        cost_basis_proportional = pos.cost_basis_base * (
            self.config.extractor_exit_pct / 100.0
        )
        gain_base = base_received - cost_basis_proportional

        # Update position: deduct sold units, deduct proportional cost basis
        pos.alt_units -= filled_units
        pos.cost_basis_base -= cost_basis_proportional

        # Compounding tier logic (design doc §8, operator decision #6 —
        # per-position; ephemeral).
        max_tier = int(self.config.extractor_max_compounding_tier)
        if pos.compounding_tier < max_tier and gain_base > 0:
            # Roll: realized base gain becomes part of next round's
            # artillery for SAME pair. Since we're closing the position
            # (full or partial exit), this means: if full exit, the
            # next PENDING→IN_FLIGHT for this pair will fire at the
            # rolled artillery size. For simplicity at v3.19.1, we
            # treat the gain as locked-to-pool for now (the rolling
            # mechanism with gain-as-next-artillery-size is a v3.19.1+
            # follow-up; this ship handles the lock case cleanly).
            self._chunk_free_base += base_received
            # Tier counter persists with the position; if exit was
            # partial, position survives with bumped tier.
            if pos.alt_units > 1e-12:
                pos.compounding_tier += 1
            log_kind = "ROLL_TO_NEXT_TIER"
        else:
            # Lock: gain stays in chunk; tier counter dies with position.
            self._chunk_free_base += base_received
            log_kind = "LOCK_TO_POOL"

        self._cycle_extracted_total += gain_base
        self._lifetime_extracted_total += gain_base
        self._chunk_extracted_total += gain_base

        # v3.20.72 Phase C-1 — profit auto-grow registry notification
        # (MEM-418). Closes the cross-bot leak surface identified in
        # docs/audits/2026-06-05_profit_cascade_prevention_audit.md.
        # When this bot earns positive gain_base, notify the manager so
        # the CapitalRegistry's reservation grows to cover the profit —
        # otherwise sibling bots see the wallet's grown balance as
        # phantom excess and could claim it (fee-stacking cascade).
        # Locked Q6 semantics: the bot's OWN reservation grows
        # immediately even if wallet provider hasn't caught up;
        # siblings' subsequent request_reservation() calls see the
        # full new total and can't claim against unsettled profit.
        if (
            gain_base > 0
            and self._bot_manager is not None
            and self._chunk_to_base_rate > 0
        ):
            try:
                gain_usd = self._base_to_usd(gain_base)
                if gain_usd > 0:
                    self._bot_manager.notify_bot_profit(
                        bot_id=self.bot_id, profit_usd=gain_usd
                    )
            except (
                Exception
            ) as _exc:  # R28-OK: profit notification best-effort; don't block trade flow
                logger.warning(
                    "v3.20.72 profit notification failed for bot %s: %s",
                    self.bot_id,
                    _exc,
                )

        # The sale has filled, so the base currency is back. Tell the
        # parent bot, which is what stops the parent selling it away.
        self._hand_base_currency_to_parent(base_received, pos.pair)

        # If position fully exited, remove + log to closed list
        if pos.alt_units < 1e-12 or self.config.extractor_exit_pct >= 100.0:
            self._closed_position_log.append(
                {
                    "pair": pos.pair,
                    "opened_at": pos.opened_at,
                    "closed_at": time.time(),
                    "alt_units_initial": (filled_units + pos.alt_units),
                    "cost_basis_base": (cost_basis_proportional + pos.cost_basis_base),
                    "base_received": base_received,
                    "gain_base": gain_base,
                    "compounding_tier": pos.compounding_tier,
                    "corrections_fired": pos.corrections_fired,
                    "log_kind": log_kind,
                }
            )
            # Cap closed-log size
            if len(self._closed_position_log) > self._closed_log_max:
                self._closed_position_log = self._closed_position_log[
                    -self._closed_log_max :
                ]
            self._positions.pop(pos.pair, None)
            self._last_correction_tick.pop(pos.pair, None)

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"EXTRACTOR EXIT ({log_kind}): {pos.pair} sold "
                f"{filled_units:.6f} @ {fill_price:.8f}; "
                f"received {base_received:.8f} base; "
                f"gain {gain_base:+.8f} base; tier={pos.compounding_tier}."
            ),
        )

    def _hand_base_currency_to_parent(self, base_received: float, pair: str) -> None:
        """Tell the parent bot that its base currency came back.

        Operator design 2026-08-09: an Extractor is a tranche under the
        Scrumming Bot that HOLDS its base currency. When the tranche
        sells, that currency arrives, and the parent has to raise its own
        target balance by the same amount. If nobody tells it, the
        arrival reads as spare money and the parent sells the gain
        straight back out as surplus.

        `BotManager.find_parent_bot_for_base_currency` names the parent.
        `ScrummingBot.apply_extractor_tranche_return` books the arrival
        and the lift together, in one go.

        THE PARENT IS ON THIS EXCHANGE. A parent and its Extractor are
        bound to one exchange; nothing here crosses between exchanges.
        So this bot's own `exchange_id` goes over with the currency, and
        a bot holding the same currency somewhere else is not a parent.
        The lookup asks for the exchange by name and has no default,
        so this call cannot lose it quietly.

        WHAT IS PASSED IS WHAT LANDED. `base_received` is the observed
        fill -- units filled at the price they filled at -- and the
        dollar figure is that same number through this bot's own
        `_base_to_usd`. No profit is worked out here. The booking refuses
        anything that is not exactly a plain number, so both halves go
        over as plain floats or the booking declines them.

        ONE CALL OR NONE. No parent, no manager, or a booking that
        refuses, all mean the lift does not happen and nothing else
        changes. There is no retry, no queue, and no second choice of
        parent: a wrong parent would raise ITS target on money it never
        received.

        A FAILURE HERE NEVER REACHES THE SALE. Losing the lift costs a
        lift. Breaking the exit would strand real money in a half-sold
        position. So everything is inside one guard, and the caller
        carries on either way.

        Tests: tests/test_extractor_tranche_return_call.py.
        """
        if base_received <= 0 or self._bot_manager is None:
            return
        try:
            parent = self._bot_manager.find_parent_bot_for_base_currency(
                self.config.base_currency, exchange_id=self.config.exchange_id
            )
            if parent is None:
                return
            parent.apply_extractor_tranche_return(
                usd_value=float(self._base_to_usd(base_received)),
                source=self.bot_id,
                base_units=float(base_received),
                ref=pair,
            )
        except Exception as _exc:  # R28-OK: the exit must finish anyway
            logger.warning(
                "Extractor %s could not hand %s back to a parent: %s: %s",
                self.bot_id,
                self.config.base_currency,
                type(_exc).__name__,
                _exc,
            )

    async def _fire_artillery(
        self,
        pair: str,
        snapshot: TASnapshot,
        alt_price_in_base: float,
    ) -> None:
        """Fire one artillery round into `pair`. Creates a new
        ExtractorPosition on success."""
        artillery_usd = float(self.config.extractor_artillery_size_usd)
        artillery_base = self._usd_to_base(artillery_usd)
        if artillery_base <= 0:
            return
        if not self._has_chunk_capacity(artillery_base):
            return  # reserve cap hit

        if alt_price_in_base <= 0:
            return

        # MEM-257 fail-closed check. For a fresh position the
        # expected_units is 0 — operator does not yet hold alt;
        # if exchange phantom-zeros THIS alt that's fine, we ARE
        # firing from a fresh state. If exchange reports nonzero
        # for the alt (impossible on a fresh Extractor unless
        # operator manually pre-funded), the helper returns
        # verified_units > 0 and we proceed; the helper's
        # purpose is the BONK-style "state says X, exchange says 0"
        # pattern which doesn't apply to a fresh position.
        target_asset = pair.split("/")[0]
        verified, refuse = await verify_buy_safe_or_refuse(
            self.exchange,
            target_asset,
            expected_units=0.0,
            path="extractor_artillery",
        )
        if refuse:
            self._bus.emit("bot.log", bot_id=self.bot_id, message=refuse)
            logger.warning("Bot %s %s", self.bot_id, refuse)
            return

        # v3.20.74 Phase C-2 (MEM-420): mode-aware artillery side.
        # Normal artillery = BUY alt with base (build the position).
        # Inverted artillery = SELL alt for quote (build the inverted
        # short — we now hold quote, plan to buy back more alt later).
        alt_units_to_buy = artillery_base / alt_price_in_base
        try:
            order = await self.guarded_place_order(
                symbol=pair,
                side=self._entry_order_side(),
                order_type=OrderType.MARKET,
                amount=alt_units_to_buy,
                price=None,
            )
        except Exception as exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"EXTRACTOR ARTILLERY FAILED on {pair}: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
            logger.exception("Extractor artillery failed")
            return
        if order is None:
            return

        filled_units = float(
            getattr(order, "filled", None)
            or getattr(order, "amount", None)
            or alt_units_to_buy
        )
        fill_price = float(
            getattr(order, "average_price", None)
            or getattr(order, "average", None)
            or getattr(order, "price", None)
            or alt_price_in_base
        )
        actual_base_spent = filled_units * fill_price

        # Debit chunk
        self._chunk_free_base -= actual_base_spent

        # Create position
        pos = ExtractorPosition(
            pair=pair,
            state=POSITION_STATE_IN_FLIGHT,
            artillery_size_base=artillery_base,
            artillery_size_usd_at_entry=artillery_usd,
            alt_units=filled_units,
            entry_price_base_per_alt=fill_price,
            avg_buy_price_base_per_alt=fill_price,
            cost_basis_base=actual_base_spent,
            compounding_tier=1,
            corrections_fired=0,
            last_correction_ts=time.time(),
            opened_at=time.time(),
        )
        self._positions[pair] = pos
        self._last_correction_tick[pair] = self._tick_counter
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"EXTRACTOR ARTILLERY FIRED: {pair} bought "
                f"{filled_units:.6f} @ {fill_price:.8f} "
                f"(spent {actual_base_spent:.8f} base, "
                f"~${artillery_usd:.2f}). chunk_free now "
                f"{self._chunk_free_base:.8f} base."
            ),
        )

    # ── tick() — main per-cycle entrypoint ──────────────────────────

    async def tick(self) -> None:
        """One tick of the Extractor.

        Order:
          0a. v3.20.3 — pulse heartbeat to CapitalReservationRegistry.
              Without this, the registry would zombie-prune our chunk
              reservation after HEARTBEAT_TTL (120s default) and SB
              protection on this base_currency would disengage.
          0b. Refresh watch list if due.
          1.  Evaluate ALL open positions (drawdown/exit) — manage
              existing commitments first.
          2.  Scan watch list for new artillery opportunities — pairs
              in volume-rank order; first eligible wins per tick.
        """
        self._tick_counter += 1

        # v3.20.3 — heartbeat the registry so our chunk reservation
        # stays live. Defensive: registry call must never block a tick.
        # sadp: R28 FL
        if self._crr_token is not None:
            try:
                from .capital_reservation import get_registry as _crr_get_registry

                _crr_get_registry().heartbeat(self.bot_id)
            except (
                Exception
            ) as _crr_exc:  # R28-OK: heartbeat best-effort; tick must not block
                logger.debug(
                    "Bot %s capital reservation heartbeat raised %s — "
                    "continuing tick.",
                    self.bot_id,
                    _crr_exc,
                )

        # Step 0: refresh watch list if due
        if self._watch_list_due_for_refresh():
            await self._refresh_watch_list()

        # Step 1: manage open positions
        for pair, pos in list(self._positions.items()):
            snapshot = await self._ta_provider.evaluate(pair)
            if snapshot is None:
                continue  # warmup or exchange hiccup; skip this pair
            try:
                ticker = await self.exchange.get_ticker(pair)
                alt_price_in_base = float(ticker.last)
            except Exception as exc:  # R28-OK: per-pair best-effort
                logger.debug(
                    "Bot %s tick: get_ticker(%s) raised %s: %s — open "
                    "position left untouched this tick",
                    self.bot_id,
                    pair,
                    type(exc).__name__,
                    exc,
                )
                continue
            if alt_price_in_base <= 0:
                continue
            # Item 4 (2026-08-11) — keep the price this tick already
            # paid for. The parent Scrumming Bot values its Extractor
            # Tranches from this field, on the GUI thread, where a
            # network call is not allowed. Recorded BEFORE the position
            # is evaluated so a raising evaluator still leaves a fresh
            # mark behind. Records only; moves nothing.
            pos.last_price_base_per_alt = alt_price_in_base
            pos.last_priced_at = time.time()
            try:
                await self._evaluate_open_position(pos, snapshot, alt_price_in_base)
            except Exception as exc:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"EXTRACTOR position eval {pair} raised "
                        f"{type(exc).__name__}: {exc}"
                    ),
                )
                logger.exception("Extractor position eval failed")

        # Step 2: scan watch list for new entries
        for pair in self._watch_list:
            if pair in self._positions:
                continue  # one position per pair (decision #8)
            snapshot = await self._ta_provider.evaluate(pair)
            if snapshot is None:
                continue
            # Entry trigger: mode-aware. v3.20.74 Phase C-2 (MEM-420):
            # Normal fires on BEARISH (buy alt cheap); Inverted fires
            # on BULLISH (sell alt expensive — capture relative outperf).
            if not self._entry_signal_matched(snapshot):
                continue
            try:
                ticker = await self.exchange.get_ticker(pair)
                alt_price_in_base = float(ticker.last)
            except Exception as _tk_exc:  # noqa: BLE001 - skip this pair
                # v3.24.21 — was a bare `continue`. An entry signal had
                # already matched at this point, so every skip here is a
                # trade the bot decided to take and then silently did
                # not. A pair that always fails ticker lookup (delisted,
                # renamed, rate-limited) would look identical to a pair
                # that never signalled.
                logger.warning(
                    "Extractor skipping %s after entry signal matched — "
                    "ticker fetch failed (%s): %s",
                    pair,
                    type(_tk_exc).__name__,
                    _tk_exc,
                )
                continue
            if alt_price_in_base <= 0:
                continue
            try:
                await self._fire_artillery(pair, snapshot, alt_price_in_base)
            except Exception as exc:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"EXTRACTOR fire_artillery {pair} raised "
                        f"{type(exc).__name__}: {exc}"
                    ),
                )
                logger.exception("Extractor fire_artillery failed")
                continue
            # First eligible wins per tick — break to manage capital
            break

    # ── Positions snapshot (for detail-dialog Positions Held tab) ──

    def positions_for_gui(self) -> list[dict]:
        """v3.19.3 — return a list of per-position dicts for the detail
        dialog's Positions Held tab.

        Each dict carries the columns the design doc §10 spec'd:

          | Pair | State | Tier | Alt units | Entry (USD) | Current (USD)
          | Δ% (USD) | Corrections | (Manual Fire button rendered by GUI)

        Current value computation needs a fresh per-pair price; the GUI
        passes that in OR queries the bot's last-known cache. For
        v3.19.3 we don't fetch live tickers here (GUI thread should
        never block on network); we use the position's
        ``avg_buy_price_base_per_alt`` as a fallback when the GUI
        hasn't yet supplied a live price. The detail dialog can refresh
        the rendered USD values asynchronously.
        """
        rows: list[dict] = []
        for p in self._positions.values():
            # Fallback: use avg buy price as the "current" reference until
            # the GUI refreshes the live price.
            current_price = p.avg_buy_price_base_per_alt
            current_value_usd = p.alt_units * current_price * self._chunk_to_base_rate
            entry_value_usd = p.artillery_size_usd_at_entry
            delta_pct = (
                ((current_value_usd - entry_value_usd) / entry_value_usd * 100.0)
                if entry_value_usd > 0
                else 0.0
            )
            rows.append(
                {
                    "pair": p.pair,
                    "state": p.state,
                    "tier": p.compounding_tier,
                    "alt_units": p.alt_units,
                    "entry_usd": entry_value_usd,
                    "current_usd_approx": current_value_usd,
                    "delta_pct_usd_approx": delta_pct,
                    "corrections_fired": p.corrections_fired,
                    "cost_basis_base": p.cost_basis_base,
                    "avg_buy_price_base_per_alt": p.avg_buy_price_base_per_alt,
                    "opened_at": p.opened_at,
                }
            )
        return rows

    # ── Extractor Tranches (item 4, for the PARENT's tranche list) ──

    def tranche_id_for_position(self, position: ExtractorPosition) -> str:
        """Build the stable Extractor Tranche id for one position.

        ONE COPY OF THE FORMAT, because two would be a defect waiting
        to happen. The row emitter labels a row with this id and the
        arbiter setter resolves a row back to a position with it; if
        those two ever formatted `opened_at` differently — say ``%.6f``
        against ``str()`` — the setter would refuse every row it was
        handed, or worse, match the wrong one. They now cannot differ.

        The parts are unchanged from item 4: `bot_id` survives restart
        and separates two Extractors on one pair, `pair` is unique
        within one Extractor, and `opened_at` stops a closed-and-
        reopened position from inheriting anything attached to its
        predecessor.
        """
        return (
            f"{self.bot_id}|{position.pair}|" f"{float(position.opened_at or 0.0):.6f}"
        )

    def set_tranche_arbiter(self, tranche_id: object, arbiter: object) -> str | None:
        """Record who may close ONE Extractor Tranche. Returns the value.

        NO MONEY MOVES HERE. This writes one string on one position.
        It places no order, cancels none, touches no balance, no chunk
        ledger and no target balance, and it awaits nothing. The value
        is read today by exactly one consumer — the row emitter that
        feeds the parent's Open Tranches table — so toggling it changes
        the record and nothing else. Nothing about the parent
        force-sell that `parent` names exists yet.

        RESOLVED BY FULL IDENTITY, NEVER BY PAIR AND NEVER BY INDEX.
        `_positions` is keyed by pair, and a pair can close and reopen;
        a pair-keyed write would land on the successor position and
        silently mislabel it. Matching the whole ``bot_id|pair|
        opened_at`` string is what makes that impossible, so an id that
        matches nothing gets ``None`` and NO write, rather than a
        best-effort guess.

        Returns the stored value on success, ``None`` when no open
        position carries that id. The caller must treat ``None`` as a
        refusal and leave its surface unchanged.
        """
        wanted = str(tranche_id) if tranche_id is not None else ""
        if not wanted:
            return None
        for position in self._positions.values():
            if self.tranche_id_for_position(position) != wanted:
                continue
            position.arbiter = normalize_arbiter(arbiter)
            logger.info(
                "Bot %s: Extractor Tranche %s arbiter set to %s "
                "(record only — no order placed, no balance changed).",
                self.bot_id,
                wanted,
                position.arbiter,
            )
            return position.arbiter
        return None

    def toggle_tranche_arbiter(self, tranche_id: object) -> str | None:
        """Flip ONE tranche's arbiter between parent and sibling.

        Reads that tranche's current value and writes the other one.
        Every other tranche is untouched, including another position on
        the same pair held by a different Extractor, because the write
        goes through `set_tranche_arbiter` and matches the full id.

        Returns the NEW value, or ``None`` when the id matches no open
        position — the same refusal `set_tranche_arbiter` gives, so a
        caller has one thing to check.
        """
        wanted = str(tranche_id) if tranche_id is not None else ""
        if not wanted:
            return None
        for position in self._positions.values():
            if self.tranche_id_for_position(position) != wanted:
                continue
            return self.set_tranche_arbiter(wanted, other_arbiter(position.arbiter))
        return None

    def extractor_tranche_rows(self) -> list[dict]:
        """Describe every open position as an Extractor Tranche.

        Operator design 2026-08-09: an Extractor's in-flight position is
        an "Extractor Tranche", and it is "listed under the base-currency
        bot" — the Scrumming Bot that holds the base currency this
        Extractor spends. This is the child's half of that listing. The
        parent reads it through `ScrummingBot.open_extractor_tranches`.

        WHY THE CHILD PRODUCES IT. The child is the only writer of its
        own positions. If the parent kept its own copy it would be a
        mirror that can silently fall out of step — and nothing today
        tells the parent when a position OPENS, only when one sells
        (`_hand_base_currency_to_parent`), through a call that swallows
        every exception. A mirror that can diverge in silence is worse
        than no mirror, so the parent asks and this answers.

        NO NETWORK, NO CLOCK, NO STATE CHANGE. Every number here is
        already in memory. The caller is the Qt GUI thread, which is
        also the thread every coroutine in this application runs on, so
        a fetch here would freeze the interface.

        IDENTITY. `tranche_id` is ``"<bot_id>|<pair>|<opened_at>"``.
        Each part earns its place: `bot_id` survives restart and
        separates two Extractors on the same pair; `pair` is unique
        within one Extractor because it enforces one position per pair;
        `opened_at` stops a closed-and-reopened position from inheriting
        anything attached to its predecessor. The id does not depend on
        position in any list, so it survives a re-sort and survives
        other tranches closing. Item 5 needs exactly that to hang a
        per-tranche control on a row.

        VALUATION IS HONEST OR ABSENT. `mark_*` is None when the
        position has never been priced. `positions_for_gui` substitutes
        the average buy price for a missing mark, which makes its
        "current" value equal cost basis and its delta near zero by
        construction; repeating that here would put a cost-basis number
        under a market-value heading in the parent's own ledger. The
        cost basis is reported too, under its own name.
        """
        rows: list[dict] = []
        base_asset = str(getattr(self.config, "base_currency", "") or "")
        rate = float(self._chunk_to_base_rate or 0.0)
        for p in self._positions.values():
            mark_price = float(p.last_price_base_per_alt or 0.0)
            if mark_price > 0:
                mark_value_base = float(p.alt_units) * mark_price
                # `_chunk_to_base_rate` is USD PER ONE BASE UNIT, not
                # base per USD, whatever its name suggests. Pinned from
                # `set_initial_chunk_rate`, which states the units
                # outright ("the *USD value per 1 base unit* (e.g. for
                # ETH: 3000)") and divides USD by it to get base, and
                # from `_position_value_usd`, which MULTIPLIES by it to
                # turn a base amount into USD. Dividing here would
                # invert the rate and report an ETH tranche worth about
                # nine millionths of its true value.
                mark_value_usd = mark_value_base * rate if rate > 0 else None
            else:
                mark_value_base = None
                mark_value_usd = None
            rows.append(
                {
                    "tranche_id": self.tranche_id_for_position(p),
                    "kind": "extractor",
                    "child_bot_id": self.bot_id,
                    "child_bot_name": str(
                        getattr(self.config, "name", "") or self.bot_id
                    ),
                    "pair": p.pair,
                    "state": p.state,
                    "base_asset": base_asset,
                    # Base currency this position is holding out of the
                    # parent's asset. Exact, and needs no price at all.
                    "base_deployed": float(p.cost_basis_base or 0.0),
                    "alt_units": float(p.alt_units or 0.0),
                    "mark_price_base_per_alt": (mark_price if mark_price > 0 else None),
                    "mark_value_base": mark_value_base,
                    "mark_value_usd": mark_value_usd,
                    "marked_at": (
                        float(p.last_priced_at or 0.0) if mark_price > 0 else None
                    ),
                    "cost_basis_base": float(p.cost_basis_base or 0.0),
                    "entry_usd": float(p.artillery_size_usd_at_entry or 0.0),
                    "compounding_tier": int(p.compounding_tier or 0),
                    "corrections_fired": int(p.corrections_fired or 0),
                    "opened_at": float(p.opened_at or 0.0),
                    # Item 5 — who may close this tranche. Normalised on
                    # the way out as well as on the way in, so a surface
                    # that trusts this dict can never be handed a third
                    # value. `arbiter_label` turns it into the operator's
                    # own word for the button.
                    "arbiter": normalize_arbiter(p.arbiter),
                }
            )
        rows.sort(key=lambda r: r["tranche_id"])
        return rows

    # ── Status snapshot (for GUI / dashboard) ───────────────────────

    def get_status(self) -> dict:
        """Snapshot of Extractor state for the bot table / dashboard."""
        base = super().get_status() if hasattr(super(), "get_status") else {}
        n_drawdown = sum(
            1 for p in self._positions.values() if p.state == POSITION_STATE_DRAWDOWN
        )
        base.update(
            {
                "bot_id": self.bot_id,
                "mode": "extractor",
                "base_currency": self.config.base_currency,
                "chunk_size_base": self._chunk_size_base,
                "chunk_free_base": self._chunk_free_base,
                "chunk_extracted_total": self._chunk_extracted_total,
                "chunk_size_usd": self._chunk_size_usd,
                "n_positions_open": len(self._positions),
                "n_positions_drawdown": n_drawdown,
                "pool_color": self.pool_color(),
                "watch_list": list(self._watch_list),
                "cycle_extracted_total": self._cycle_extracted_total,
                "lifetime_extracted_total": self._lifetime_extracted_total,
            }
        )
        return base

    # ── State persistence ──────────────────────────────────────────

    def export_state(self) -> dict:
        """Serialize the Extractor's runtime state for save/restore."""
        return {
            "version": 1,
            "mode": "extractor",
            "chunk_size_usd": self._chunk_size_usd,
            "chunk_to_base_rate": self._chunk_to_base_rate,
            "chunk_size_base": self._chunk_size_base,
            "chunk_free_base": self._chunk_free_base,
            "chunk_extracted_total": self._chunk_extracted_total,
            "hedge_budget_usd": self._hedge_budget_usd,
            "hedge_free_base": self._hedge_free_base,
            "positions": [
                {
                    "pair": p.pair,
                    "state": p.state,
                    "artillery_size_base": p.artillery_size_base,
                    "artillery_size_usd_at_entry": (p.artillery_size_usd_at_entry),
                    "alt_units": p.alt_units,
                    "entry_price_base_per_alt": p.entry_price_base_per_alt,
                    "avg_buy_price_base_per_alt": p.avg_buy_price_base_per_alt,
                    "cost_basis_base": p.cost_basis_base,
                    "compounding_tier": p.compounding_tier,
                    "corrections_fired": p.corrections_fired,
                    "last_correction_ts": p.last_correction_ts,
                    "opened_at": p.opened_at,
                    "last_price_base_per_alt": p.last_price_base_per_alt,
                    "last_priced_at": p.last_priced_at,
                    # Item 5 — the per-tranche Arbiter. This literal is
                    # an EXPLICIT key list, not a dataclass dump, so a
                    # new field that is not named here is silently
                    # dropped on every save. Normalised on the way out
                    # so a state file can never carry a third value.
                    "arbiter": normalize_arbiter(p.arbiter),
                }
                for p in self._positions.values()
            ],
            "closed_position_log": list(self._closed_position_log),
            "watch_list": list(self._watch_list),
            "tick_counter": self._tick_counter,
            "cycle_extracted_total": self._cycle_extracted_total,
            "lifetime_extracted_total": self._lifetime_extracted_total,
        }

    def import_state(self, state: dict) -> None:
        """Rehydrate from a previously-exported state dict.

        Graceful on missing fields (forward/backward compat): every
        read goes through `.get(key, default)`.
        """
        if not isinstance(state, dict):
            return
        self._chunk_size_usd = float(state.get("chunk_size_usd", self._chunk_size_usd))
        self._chunk_to_base_rate = float(
            state.get("chunk_to_base_rate", self._chunk_to_base_rate)
        )
        self._chunk_size_base = float(
            state.get("chunk_size_base", self._chunk_size_base)
        )
        self._chunk_free_base = float(
            state.get("chunk_free_base", self._chunk_free_base)
        )
        self._chunk_extracted_total = float(state.get("chunk_extracted_total", 0.0))
        self._hedge_budget_usd = float(state.get("hedge_budget_usd", 0.0))
        self._hedge_free_base = float(state.get("hedge_free_base", 0.0))
        self._positions = {}
        for pdict in state.get("positions", []):
            try:
                pos = ExtractorPosition(
                    pair=pdict["pair"],
                    state=pdict.get("state", POSITION_STATE_IN_FLIGHT),
                    artillery_size_base=float(pdict.get("artillery_size_base", 0.0)),
                    artillery_size_usd_at_entry=float(
                        pdict.get("artillery_size_usd_at_entry", 0.0)
                    ),
                    alt_units=float(pdict.get("alt_units", 0.0)),
                    entry_price_base_per_alt=float(
                        pdict.get("entry_price_base_per_alt", 0.0)
                    ),
                    avg_buy_price_base_per_alt=float(
                        pdict.get("avg_buy_price_base_per_alt", 0.0)
                    ),
                    cost_basis_base=float(pdict.get("cost_basis_base", 0.0)),
                    compounding_tier=int(pdict.get("compounding_tier", 1)),
                    corrections_fired=int(pdict.get("corrections_fired", 0)),
                    last_correction_ts=float(pdict.get("last_correction_ts", 0.0)),
                    opened_at=float(pdict.get("opened_at", 0.0)),
                    # Absent on any state file written before item 4.
                    # Defaulting to 0.0 means "never priced", which is
                    # the truth about a position restored from a file
                    # that did not record a mark.
                    last_price_base_per_alt=float(
                        pdict.get("last_price_base_per_alt", 0.0)
                    ),
                    last_priced_at=float(pdict.get("last_priced_at", 0.0)),
                    # Absent on every state file written before item 5,
                    # which today is every state file that exists. The
                    # default is the value that describes what the
                    # fleet already does, so an old record loads
                    # EXACTLY as it did before this field existed.
                    #
                    # `normalize_arbiter` cannot raise, deliberately.
                    # A `float(...)` above can, and the handler below
                    # DROPS the whole record when it does — a dropped
                    # record is a position this bot stops managing. A
                    # preference about who may sell must never cost the
                    # operator a position, so this read is incapable of
                    # reaching that path.
                    arbiter=normalize_arbiter(pdict.get("arbiter", ARBITER_SIBLING)),
                )
                self._positions[pos.pair] = pos
            except Exception as exc:  # R28-OK: skip malformed position records
                # A dropped record is a position the bot will no longer
                # manage, so this one is louder than the scan skips.
                logger.warning(
                    "Bot %s import_state: a saved position record raised "
                    "%s: %s — record dropped, remaining records still "
                    "load",
                    self.bot_id,
                    type(exc).__name__,
                    exc,
                )
                continue
        self._closed_position_log = list(state.get("closed_position_log", []))
        self._watch_list = list(state.get("watch_list", []))
        self._tick_counter = int(state.get("tick_counter", 0))
        self._cycle_extracted_total = float(state.get("cycle_extracted_total", 0.0))
        self._lifetime_extracted_total = float(
            state.get("lifetime_extracted_total", 0.0)
        )
