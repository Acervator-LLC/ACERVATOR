"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
bot_container.py — Isolated auto-trader container
===================================================
Each Auto Trader Container runs as an independent asyncio task with its
own error boundary.  A container crash does NOT propagate to other bots
or the main application.

Architecture:
  • Each bot has a unique ``bot_id`` and is bound to exactly one
    exchange, one base currency, and one target asset.
  • The ``BotManager`` oversees all containers, handles lifecycle
    (start/stop/restart), and aggregates status for the main window.
  • Containers communicate with the rest of the app exclusively via
    the EventBus — no shared mutable state.

Fault isolation strategy:
  • Each bot runs inside ``_run_with_guard()`` which catches ALL
    exceptions and emits ``bot.error`` events instead of crashing.
  • After N consecutive failures, the bot enters a cooldown state.
  • The manager can restart individual bots without affecting others.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # Names used only to describe what a value is, never to run
    # anything. guarded_place_order writes its order side, its order
    # kind and its return value as quoted names. This file turns every
    # such description into plain text at import time, so none of these
    # is ever looked up while the program runs. Naming them here lets
    # the checking tools find them; it adds no import when the program
    # runs, so it cannot cause an import loop and cannot slow start-up.
    # guarded_place_order still imports the real ones itself when it
    # needs to compare or build an order.
    from ..exchange.base import (
        ExchangeInterface,
        Order,
        OrderSide,
        OrderType,
    )

from ..core.event_bus import get_event_bus

logger = logging.getLogger("acervator.bot")


# Coins that are meant to hold a value of one dollar. For these, one
# dollar per unit is the true price, not a stand-in for a price we
# could not get. Kept in ONE place: two copies of a money list is how
# the two copies come to disagree.
DOLLAR_PEGGED_CURRENCIES = frozenset(
    {
        "USD",
        "USDC",
        "USDT",
        "DAI",
        "BUSD",
        "PYUSD",
        "FDUSD",
    }
)


# ---------------------------------------------------------------------------
# Bot state machine
# ---------------------------------------------------------------------------
class BotState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    COOLDOWN = "cooldown"
    STOPPED = "stopped"


class BotMode(str, Enum):
    # v3.20.4 — BotMode.GRID removed. grid_bot.py was deleted v3.16.0
    # per operator directive 2026-04-28 ("Delete the grid bot code. We
    # have grown beyond it and we do not need souvenirs."); the GRID
    # enum lived on for ~4 weeks as a half-working legacy-migration
    # shim that never actually worked end-to-end (ScrummingBot's
    # `assert config.mode == BotMode.SCRUMMING` rejected any restored
    # GRID config). Persisted GRID bots — if any exist on disk — now
    # hit the unknown-mode branch in restore_bots_from_state, which
    # ERROR-logs and skips. Operator directive 2026-05-23: "Grid code
    # and dangling mentions can be cleaned out."
    # sadp: R55 GOV  R62 FRG
    SCRUMMING = "scrumming"
    EXTRACTOR = "extractor"  # v3.19.1 — Base Currency Extractor Multi-Target


# ---------------------------------------------------------------------------
# Bot configuration
# ---------------------------------------------------------------------------
@dataclass
class BotConfig:
    """Immutable configuration snapshot for a bot instance."""

    exchange_id: str
    base_currency: str  # e.g. "USDT"
    target_asset: str  # e.g. "BTC"
    symbol: str = ""  # Derived: "BTC/USDT"
    # v3.20.4 — default changed from BotMode.GRID to BotMode.SCRUMMING
    # alongside the BotMode.GRID enum removal. SCRUMMING is the only
    # historically-real default for a freshly-constructed BotConfig
    # (grid_bot deleted v3.16.0; Extractor is opt-in via the wizard).
    mode: BotMode = BotMode.SCRUMMING

    # --- Sizing ---
    investment_amount: float = 200.0  # Total bot capital
    increment_style: str = "linear"  # "linear" or "logarithmic"
    spacing_style: str = (
        "expanding"  # "expanding" (wider gaps) or "stacked" (fixed gap)
    )
    # v3.23.25 — market_check_interval removed. Was declared as
    # "Seconds between price checks (Invisible mode)" but never read
    # at runtime (tick_interval hardcoded 5.0). Operator directive
    # 2026-07-25: "The Check Interval setting can be removed as the
    # bot does not need a secondary poll rate to make trade decisions."

    # Profit folding flag (engine-consulted)
    profit_folding_active: bool = True

    # --- Scrumming-specific ---
    target_balance: float = 200.0  # Balance the bot trades relative to
    # v3.24.92 — MAXIMUM USD THIS BOT MAY ADOPT FROM THE EXCHANGE.
    #
    # 0.0 means "use target_balance", which is the sane default: a bot
    # asked to hold $25 has no business claiming $500 of an asset
    # because it happened to be sitting in the account.
    #
    # Adoption (ScrummingBot, never-scrummed bots taking an
    # operator-placed position as their opening lot) is an INFERENCE
    # about ownership. This is the operator's DECLARATION, and the
    # declaration wins. Modelled on Hummingbot's `balance limit`
    # command (`balance limit [exchange] [asset] [amount]`), documented
    # as: "Sets the amount limit on how much assets Hummingbot can use
    # in an exchange or wallet. This can be useful when running multiple
    # bots on different trading pairs with same tokens."
    # https://hummingbot.org/client/global-configs/balance-limit/
    #
    # That is the one thing the inference cannot work out for itself,
    # because nothing on the exchange distinguishes "seed for this bot"
    # from "coins the operator wants kept back".
    #
    # CITATION CORRECTED v3.24.99. The first version of this comment
    # quoted the feature as keeping funds "left untouched for other bots
    # or manual trading". That phrase appears NOWHERE in Hummingbot's
    # documentation -- it was written from memory and presented as a
    # quotation, in a comment justifying a change to live trading
    # config. The feature is real and the analogy holds; the quotation
    # did not, and a fabricated citation is worse than none because it
    # invites the next reader to trust it.
    #
    # Researched 2026-08-09, see
    # docs/audits/2026-08-09_position_attribution_shared_account_research.md
    max_adoptable_usd: float = 0.0
    scrumming_interval_pct: float = 1.0  # % market move between actions

    # Scrumming: Profit routing (where excess delta goes after sell)
    profit_route: str = (
        "fold_to_target"  # "fold_to_target" | "spendable" | "split" | "cross_bot"
    )
    profit_route_bot_id: str = ""  # Target bot ID for cross-bot routing

    # Scrumming: Scrum-to-fold reentry ratio (MEM-234)
    # Controls what % of scrum sale proceeds queue for fold-back rebuy.
    # 100 = full reentry (maximum accumulation, maximum exposure after crash).
    # 50 = half the proceeds queue for fold, half realized as cash profit.
    # Low values preserve cash buffer — safer when price keeps falling
    # after the scrum. Default 100 preserves pre-MEM-234 behavior.
    scrum_fold_pct: int = 100  # 1-100: % of scrum proceeds queued for fold

    # Item 9 (2026-08-13) — Tranche despawn timer.
    # Operator spec: "We can also add a tranche despawn timer that
    # delists aged tranches from the tracker."
    #
    # THE UNIT IS WHOLE DAYS. Measured on a pinned read-only copy of
    # bot_state.json (2026-08-13 08:43): 471 open fold tranches across
    # 24 of 37 bots, every one carrying a usable `created_ts`. Days is
    # the unit the Fold Tranches panel already reads ages back in.
    #
    # 0 = OFF, and off is the default — the same "0 disables" convention
    # `band_travel_pct` uses. A timer that shipped enabled would delist
    # standing records on bots the operator never opted in for.
    #
    # NEVER READ THIS FIELD RAW. `despawn_threshold_days()` below is the
    # one rule, and both the sweep and the live-settings spinbox go
    # through it.
    tranche_despawn_days: int = 0  # 0 = off; else delist at >= N days

    # Scrumming: Max target-balance growth per completed cycle (ADR-029 / MEM-247 pending)
    # Caps how much _target_balance can increase from a single profit-fold event.
    # Excess profit (above the cap) routes to realised_pnl only — never compounded.
    # Operator Q3 answer: % of target balance at decision time.
    # Operator Q2 answer: default 1.0 (1% — intentional behavioral change on upgrade).
    # Valid range: 1-100. Slice 2 only declares the field; it is INERT until slice 4
    # wires up the shared helper src/trading/profit_fold.py per PLAN_MEM246 Step 2.
    # sadp: R42 R44 (cap must be mirrored live↔sim↔battery via shared helper)
    max_target_growth_pct: float = 1.0  # 1-100: cap on target growth per cycle as %

    # Scrumming: Bollinger Band proximity settings
    bb_tolerance_pct: float = 1.0  # 0.25% to 5% tolerance for BB proximity
    bb_landing_strip_candles: int = (
        3  # Min consecutive tight HA candles for landing strip
    )
    ta_timeframe: str = "1h"  # Timeframe for TA indicator calculations

    # Scrumming: advanced signal & risk parameters
    # v3.13.8 MEM-182 / P1.9 — added for Real/Sim UI parity. Were previously
    # sim-only; now canonical on both sides. Defaults match the sim's
    # existing defaults so current sim behavior is preserved.
    scrum_detect_pct: int = 75  # DETECT threshold — % distance from BB midline
    # before switching SEARCH→TRACK (10-90)
    scrum_fire_pct: float = 0.5  # FIRE threshold — % distance from BB band
    # to trigger a trade (0.1-10.0)
    bb_midline_gate: bool = True  # When True: scrums only above midline,
    # folds only below midline (bear-market friendly)
    scrum_read_rate_min: int = 5  # SEARCH-mode read rate in minutes; TRACK mode
    # reads 10x faster automatically
    band_travel_pct: int = 70  # Secondary harvest trigger — % of BB band width
    # price must travel since last fold (0 = off)
    bb_bullseye_check: bool = True  # Rapid Fire override when price touches a BB
    # band within 0.1% (overrides other gates)
    hedge_rebalance_active: bool = True  # Enable a separate USD reserve for buying on
    # sharp drawdowns (lets bot keep buying the dip)
    hedge_balance: float = 200.0  # USD reserve amount for hedge rebalancing
    # (not taken from target_balance)

    # v3.15.58 — Circuit Breakers (operator directive 2026-04-25).
    # Soft = time-delay interrupt on the move's side of the market;
    # Hard = bot pause requiring operator reset. Single-candle move
    # measured as (high - low) / open × 100. Direction inferred from
    # close vs open: close>=open → "up" (interrupt SCRUM side);
    # close<open → "down" (interrupt FOLD side).
    circuit_breaker_soft_pct: float = 25.0  # Soft trip threshold (default 25%)
    circuit_breaker_hard_pct: float = 35.0  # Hard trip threshold (default 35%)
    circuit_breaker_cooldown_candles: int = 3  # Candles to wait before soft re-opens

    # v3.15.63 — Maximum Cartridge Size (operator directive 2026-04-26).
    # Target Delta cap as % of target balance. When |delta| ≥ this %,
    # the bot fires an immediate aggressive rebalance (market order via
    # the same path as Manual Fire — bypasses auto gates because the
    # operator's directive is "perform an immediate aggressive trade"
    # and the whole point is to not let the cartridge over-fill).
    # Set to 0 to disable.
    max_cartridge_size_pct: float = 10.0

    # v3.15.92 — Smart Cartridge calibration (operator directive 2026-04-28).
    # When ``max_cartridge_smart=True``, the cartridge threshold is derived
    # from the rolling BB range on the bot's TA timeframe rather than the
    # static ``max_cartridge_size_pct``. The smart-derived threshold is
    # clamped:
    #   • Hard floor = ``scrumming_interval_pct`` (operator's directive —
    #     cartridge MUST NEVER fire below the interval, since round-trips
    #     below the interval are structurally fee-thrash by definition).
    #   • Soft ceiling = ``max_cartridge_smart_ceiling_pct`` (default 30%
    #     — prevents the smart calibration from going wide enough to
    #     effectively disable cartridge during a volatility expansion
    #     when the safety valve is most needed).
    # The static fallback when ``max_cartridge_smart=False`` is the
    # existing ``max_cartridge_size_pct`` behavior. Per-bot opt-in.
    max_cartridge_smart: bool = False
    max_cartridge_smart_ceiling_pct: float = 30.0

    # v3.15.69 — Wire-income stacking band (operator directive 2026-04-26).
    # When Smart Wire profit arrives at this bot AND |position - target|
    # is within this % of target balance AND current price is within this
    # % of the bot's entry price, use the wire income to ACQUIRE more
    # target asset (and bump target_balance accordingly). Outside this
    # band, the income falls through to the existing distribute / park
    # behavior. Default 1%. Set 0 to disable stacking.
    wire_inflow_stack_pct: float = 1.0

    # v3.16.15 — Operator-toggleable strategy gate flags (per the
    # 2026-04-30 design conversation).
    #
    # The auto-fire SCRUM and FOLD paths in tick() apply 6 internal
    # "trend protection" gates beyond the operator's three-condition
    # rule (price ≥ band, delta != 0, |delta| ≥ interval). These
    # gates exist as fee-thrash safeties tuned for a conservative
    # risk profile. When the operator runs Smart Cartridge enabled
    # with `max_cartridge_smart=True`, the cartridge auto-calibrates
    # to BB range and organically captures higher-TF swings — making
    # several of these gates redundant.
    #
    # Each flag below toggles ONE gate. Defaults preserve current
    # behavior (all True = "Conservative" profile). Setting all to
    # False = "Lean" profile (band-intersection harvesting; relies on
    # Smart Cartridge for HTF capture).
    #
    # SCRUM-side gates (sell at top):
    scrum_require_ta_bullish: bool = True  # Gate: is_bullish required for auto-scrum
    scrum_hold_in_uptrend: bool = (
        True  # Gate: trend_hold blocks scrum during sustained uptrend
    )
    scrum_defer_to_htf: bool = (
        True  # Gate: refuse scrum when higher-TF phantom is BULLISH
    )
    # FOLD-side gates (buy at bottom, mirror semantics):
    fold_require_ta_bearish: bool = True  # Gate: is_bearish required for auto-fold
    fold_hold_in_downtrend: bool = (
        True  # Gate: trend_hold blocks fold during sustained downtrend
    )
    fold_defer_to_htf: bool = (
        True  # Gate: refuse fold when higher-TF phantom is BEARISH
    )

    # --- Both modes ---
    visibility: str = "orderbook"  # "orderbook" or "internal"
    # v3.23.25 — Aggressive Trading redefined per operator directive
    # 2026-07-25: forces all engine-initiated trades to execute as
    # IOC-limit taker orders (immediate-or-cancel limit priced through
    # the spread). Manual fire is unaffected. Previously the flag was
    # only referenced in log tagging with no execution-path effect.
    aggressive_trading: bool = False

    # v3.23.25 — Stack Mode (formerly `bulk_trading`, always-False dead
    # field pre-v3.23.25). Operator directive 2026-07-25:
    #
    #   Stacks are the mirror of Fold Tranches: a SCRUM (sell) is split
    #   across a range of upward price levels instead of firing as a
    #   single order. The first tranche sits at the Minimum Opposing
    #   Trade Distance (== `scrumming_interval_pct` above the SCRUM
    #   trigger price, matching the existing opposite-direction
    #   hysteresis distance). Subsequent tranches are spaced upward per
    #   `stack_spacing_mode` at `split_distance` intervals.
    #
    # Semantic gate with `visibility`:
    #   - `visibility="orderbook"`  → Stack tranches placed as resting
    #     LIMIT SELL orders on the exchange at each computed level.
    #   - `visibility="internal"`   → Stack tranches tracked in the
    #     bot's internal ledger only; the bot fires a MARKET SELL for
    #     each tranche when price crosses that level. No book presence.
    stack_mode: bool = False
    # v3.23.25 — Split Distance. Percent spacing between successive Stack
    # tranches, applied via `stack_spacing_mode`. Range mirrors
    # `scrumming_interval_pct`.
    split_distance: float = 1.0
    # v3.23.25 — Target Stack tranche count. Actual runtime count may
    # be smaller due to (a) exchange minimum-order-size restriction on
    # per-tranche size, (b) mandatory merge of any two tranches whose
    # computed prices are within 0.1% of each other (operator directive
    # 2026-07-25: "Tranches within 0.1% of each other's price are
    # combined upwards").
    stack_tranche_count_target: int = 3
    # v3.23.26 — Spacing model for Stack tranches. Actual math
    # (Δp between tranches i and i+1, in units of `split_distance`):
    #
    #   "linear":      Δp = 1        → 1, 2, 3, 4    (constant delta)
    #   "quadratic":   Δp = i        → 1, 2, 4, 7    (arithmetic-on-Δ,
    #                                                 triangular growth)
    #   "exponential": Δp = 2^i      → 1, 2, 4, 8    (geometric doubling)
    #
    # Middle option renamed from "logarithmic" → "quadratic" v3.23.26
    # per operator directive 2026-07-25 for mathematical accuracy.
    # (True logarithmic spacing would COMPRESS as you go, opposite of
    # the desired behaviour.)
    stack_spacing_mode: str = "linear"

    # v3.23.25 — bulk_partial_on_return retired. Operator directive
    # 2026-07-25: "Retire". Was declared, restored on save, and passed
    # via kwarg allowlist but never read by any runtime code and never
    # exposed in the Settings GUI. Deprecated key silently dropped from
    # incoming bot_state.json in _sanitize_deprecated_kwargs().

    # v3.15.51 — Operator-set entry-price bounds (2026-04-25 directive).
    # Per-bot ceiling and floor on the price at which the bot is willing
    # to BUY. Operator framing: "Bot max / min entry price should be
    # able to be set by user." Both fields are Optional[float] so
    # leaving them unset (None) preserves current unbounded behavior.
    #
    # max_entry_price: bot REFUSES any auto-buy when the current price
    #   is ABOVE this. Use to cap exposure at known overvaluation.
    #   None = no ceiling.
    # min_entry_price: bot REFUSES any auto-buy when the current price
    #   is BELOW this. Use to avoid catching a falling knife / floor
    #   below which the operator considers the bot should pause buying.
    #   None = no floor.
    #
    # Manual Fire BYPASSES both bounds (operator override is authoritative,
    # consistent with the rest of the manual-fire bypass invariant).
    # Initial entry, fold rebuy, and hedge buy all RESPECT both bounds.
    max_entry_price: Optional[float] = None
    min_entry_price: Optional[float] = None

    # v3.15.52 — Coinbase trading-fee tier as a config field.
    # Operator directive 2026-04-25: "total scrum interval will now be
    # the setting plus trading fees which are 0.6% at the highest on
    # Coinbase. If current trading fee level can be dynamically
    # adjusted that would be good but I am fine just having it a user
    # setting and having the default at 0.6%."
    #
    # Used by the opposite-direction hysteresis safety: effective
    # required price deviation = scrumming_interval_pct + trading_fee_pct.
    # 0.6 default = Coinbase Advanced Trade max-tier fee. Operators
    # on lower tiers can lower this to claw back the fee adjustment.
    # Range: 0.0–5.0 (no fee → unrealistic ceiling).
    trading_fee_pct: float = 0.6

    # v3.23.25 — bulk_partial_on_return retired here. See stack_mode
    # block above for the retirement rationale.

    # --- MEM-244 Risk Controls (Session 24) ---
    # Operator directive: "Maybe make that a switch. Institutions are going
    # to want it for sure. 1x~10x should be reasonable. Bot should detonate
    # on 1D or higher Timeframe on BULLISH condition detection."
    #
    # Two independent toggles:
    #  (A) position_ceiling_enabled: caps accumulation at Nx of the bot's
    #      initial target_balance (stable anchor frozen at bot creation).
    #      As the bot approaches ceiling, fold interval is tapered linearly
    #      (100% → 10% from ratio 0.5 → 1.0). At ratio >= 1.0 fold is
    #      hard-stopped (scrum still allowed). Protects institutions from
    #      runaway accumulation on conviction plays.
    #  (B) detonation_enabled: monitors a higher TF (default 1D) for a
    #      high-confidence BULLISH reversal (confidence >= 0.75). On
    #      edge-triggered detection, executes a MARKET sell of everything
    #      above the anchor and resets target_balance to anchor — full
    #      lock-in, re-accumulate from scratch. Edge-triggered so a
    #      sustained bull run doesn't re-detonate every hour.
    position_ceiling_enabled: bool = False
    position_ceiling_multiple: float = 5.0  # Range [1.0, 10.0], default 5x
    detonation_enabled: bool = False
    detonation_timeframe: str = "1d"  # "1d", "1w"
    detonation_confidence_min: float = 0.75  # Fixed per operator Q4

    # v3.23.42 — Interoperability: capital reservation + operator hold-out
    # (per docs/audits/2026-07-27_interop_usd_denom_settlement_audit_and_design.md
    # § 3.1 and § 3.4). ScrummingBot registers its target-balance-worth
    # of the target asset in the CapitalReservationRegistry so sibling
    # bots on the same base don't fight for the same coins.
    # ``personal_hold_qty`` is target-asset units the operator keeps
    # out of the bot's decision math AND augments the registry
    # reservation so no other bot touches it either.
    self_reserve_capital: bool = True  # Default ON per operator Q1
    personal_hold_qty: float = 0.0  # Target-asset units held out

    # ─── v3.19.1 — Extractor Bot (mode == EXTRACTOR) ─────────────────
    # See docs/audits/2026-05-20_extractor_bot_design.md and
    # docs/audits/2026-05-20_extractor_bot_final_design_consideration.md
    # for the operator-approved design.
    #
    # Anchor model is INVERTED vs ScrummingBot: anchors to a POOL of the
    # BASE asset (e.g. ETH). Sends small temporary chunks ("artillery
    # rounds") into volatile ALT pairs (e.g. RAVE/ETH). Each round
    # returns the base unit count to the pool, ideally with a gain.
    # Result: grow the base unit count.
    #
    # Pair selection is dynamic — scans top-N */<base> pairs by 24h
    # volume each `extractor_scan_refresh_candles` ticks. ExtractorBots
    # do NOT spawn child bots (operator directive 2026-05-20) — multi-
    # pair reach is achieved by this within-bot scanning, not via MR
    # Inspector spawn cascades.
    # v3.20.74 Phase C-2 — Inverted Extractor (MEM-420).
    # Locked Q7: `inverted_extractor_standing_alt_units` is the
    # operator's entered ALT quantity (the bot reads the wallet to
    # confirm the amount is available at startup, then reserves it).
    # Locked Q8: single-cascade scope.
    #
    # Direction semantics:
    #   "normal"   — Regular Extractor (ammo = base/quote-side of pair;
    #                BUYS alt first; sells alt for more base; nets more
    #                base). Default — preserves all existing battery /
    #                live behavior.
    #   "inverted" — Inverted Extractor (ammo = ALT/base-side of pair;
    #                SELLS alt first into the quote currency; buys back
    #                more alt with the quote; nets more ALT). Operator's
    #                use case: "If I have a standing LINK position, I
    #                should be able to use within an Inverted Extractor
    #                that uses an alt for artillery fire (sell first)
    #                instead of base currency (buy first)."
    extractor_direction: str = "normal"
    inverted_extractor_standing_alt_units: float = 0.0
    extractor_chunk_size_usd: float = 100.0
    # USD-equivalent of base currency this bot OWNS. Converted to
    # base units at bot creation using quote_to_usd; thereafter
    # tracked in base units (so base-USD price drift doesn't
    # silently shrink/grow the bot's chunk).
    extractor_artillery_size_usd: float = 5.0
    # USD-equivalent per artillery round. Converted to base units
    # at FIRING time (each round may consume slightly different
    # base units as base-USD price drifts).
    extractor_scan_top_n: int = 8
    # Top-N */<base> pairs by 24h volume kept on the watch list.
    # Range [5, 10] per design doc § 6.
    extractor_scan_refresh_candles: int = 60
    # Re-rank top-N every N ticks. Default 60 = once per hour at
    # 1m cadence. Prevents thrashing while staying responsive.
    extractor_pool_reserve_pct: float = 50.0
    # % of chunk that stays free as reserve. New artillery only
    # fires if (chunk_free − artillery_size) ≥ reserve.
    extractor_exit_pct: float = 100.0
    # % of alt position sold on bullish trigger. 100 = full exit;
    # <100 leaves a "rider" tail. Operator-tunable per bot.
    extractor_drawdown_threshold_pct: float = 3.0
    # USD-value drawdown threshold below which averaging-down may
    # fire. Drawdown computed in USD (double-layer valuation per
    # design doc §6a) — catches base-currency exchange-rate skew.
    extractor_correction_skip_candles: int = 4
    # Minimum candles between consecutive averaging-down fires on
    # the same position. Throttles correction frequency.
    extractor_max_cost_basis_multiple: float = 2.0
    # Safety cap: cost basis of any position can't exceed
    # multiplier × original artillery_size. Hard floor against
    # runaway averaging-down drawdown.
    extractor_max_compounding_tier: int = 3
    # Per-position ephemeral tier counter (operator directive
    # 2026-05-20 — dies with the round). Tier N = roll N-1 times
    # then lock realized base gain to pool. Tier 1 always locks
    # to pool. Range [1, 10].
    extractor_hedge_budget_usd: float = 0.0
    # Optional separate base-currency reserve that powers
    # averaging-down corrections WITHOUT eating into chunk_free.
    # 0 = disabled; corrections come from chunk_free.
    extractor_trend_strength_threshold: float = 0.65
    # Trend-hold threshold for the per-symbol TASignalProvider
    # (mirrors ScrummingBot's inline 0.65 default). Above this
    # fraction of recent green candles, trend_hold = True.

    # v3.19.26 (P0 ExtractorBot wizard Symptom 1 closure) — operator-
    # selected alt targets from the wizard's ExtractorPoolPage.
    #
    # SEMANTIC: empty list (the default) means "auto — use extractor_scan_top_n
    # to pick the top-N */<base> pairs by 24h volume at runtime."
    # Non-empty list means "use exactly these symbols regardless of
    # the auto-scan." Operator override of the auto-scan default.
    #
    # The wizard's ExtractorPoolPage scans the exchange for all available
    # */<base> spot pairs and presents them as a multi-select grid; the
    # operator's selection populates this field.
    extractor_alt_targets: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.symbol:
            # v3.20.32 — mode-aware symbol derivation. For Extractor
            # bots, ``target_asset`` is the "*" pool sigil and the
            # bot is multi-pair by design — the derived symbol
            # ``"*/{base}"`` is a meaningless string that leaks
            # into log surfaces and downstream display sites
            # (operator-reported 2026-05-25 bug pattern). For
            # Extractor mode we set symbol to the pool sigil only,
            # so any consumer rendering ``symbol`` knows immediately
            # that this is a pool, not a single tradable pair.
            # ScrummingBot path is unchanged.
            if self.mode == BotMode.EXTRACTOR:
                # Pool sigil — explicit "not a tradeable symbol"
                # marker. Downstream consumers MUST check mode
                # before treating this as an exchange symbol.
                self.symbol = f"*/{self.base_currency}"
            else:
                self.symbol = f"{self.target_asset}/{self.base_currency}"

    def validate_mode_shape(self) -> list:
        """v3.20.32 — return a list of mode-shape violations.

        Catches the operator-reported 2026-05-25 bug class:
        Extractor configs with stale ScrummingBot-shaped field
        values (e.g. ``target_asset = "ONDO"`` on a USDC Extractor).
        Returns a list of human-readable violation strings — empty
        list means the config is shape-consistent with its mode.

        This is an INVARIANT check, not a hard error. Callers can
        choose to warn-and-continue or refuse-to-start based on
        their policy. The architectural fitness test pins specific
        invariants here.

        Extractor invariants:
          - ``target_asset`` must equal ``"*"`` (the pool sigil) —
            anything else is a stale-config leak from before v3.19.28
          - ``extractor_chunk_size_usd > 0`` — bot has no pool
            otherwise

        Scrumming invariants:
          - ``target_asset`` must NOT equal ``"*"`` (Scrumming is
            single-pair; "*" is the Extractor pool sigil)
          - ``base_currency`` and ``target_asset`` must be non-empty
        """
        violations: list = []
        if self.mode == BotMode.EXTRACTOR:
            if self.target_asset != "*":
                violations.append(
                    f"Extractor config has target_asset="
                    f"{self.target_asset!r}; expected '*' (pool "
                    f"sigil). This is likely a stale pre-v3.19.28 "
                    f"wizard write or a mode-tag drift bug — the "
                    f"value will leak into the startup notification "
                    f"as an unrelated wallet balance."
                )
            if self.extractor_chunk_size_usd <= 0:
                violations.append(
                    f"Extractor config has "
                    f"extractor_chunk_size_usd="
                    f"{self.extractor_chunk_size_usd}; must be "
                    f"positive (bot needs a pool to deploy)."
                )
        elif self.mode == BotMode.SCRUMMING:
            if self.target_asset == "*":
                violations.append(
                    f"Scrumming config has target_asset='*' (the "
                    f"Extractor pool sigil); Scrumming is "
                    f"single-pair and needs a real ticker."
                )
            if not self.target_asset:
                violations.append(
                    f"Scrumming config has empty target_asset; "
                    f"needs a real ticker (e.g. 'BTC')."
                )
            if not self.base_currency:
                violations.append(
                    f"Scrumming config has empty base_currency; "
                    f"needs a real quote currency (e.g. 'USDC')."
                )
        return violations


# ---------------------------------------------------------------------------
# v3.20.33 — BotConfig field manifests + typed factory
# ---------------------------------------------------------------------------
# These manifests define WHICH BotConfig fields are meaningful for
# WHICH mode. They drive ``make_bot_config(...)``'s mode-foreign
# kwarg enforcement and the architectural-fitness rule that flags
# direct ``BotConfig(...)`` calls outside the factory.
#
# WHY THIS EXISTS: ``BotConfig`` is a single dataclass shared by
# both ScrummingBot and ExtractorBot. The 2026-05-25 operator-
# reported bug class is "ScrummingBot-shape leaks into Extractor"
# — stale configs with mode-foreign field values that the runtime
# treats as authoritative. The factory below catches the leak at
# construction time instead of letting it survive into a running
# bot.
#
# To add a new BotConfig field:
#   1) Add the field to the @dataclass
#   2) Add the field name to the appropriate manifest set below
#      (SHARED, SCRUMMING_ONLY, or EXTRACTOR_ONLY)
#   3) The factory will then enforce its mode-affinity at runtime

#: Fields whose meaning + values are the SAME across both modes.
#: Anything in this set may be passed to make_bot_config(...) for
#: either mode without warning.
_BOT_CONFIG_SHARED_FIELDS: frozenset = frozenset(
    {
        "exchange_id",
        "base_currency",
        "target_asset",
        "symbol",
        "mode",
        "target_balance",  # mode-overloaded but always required
        "ta_timeframe",
        "trading_fee_pct",
        "visibility",
        "aggressive_trading",
        # v3.23.25 — bulk_trading renamed to stack_mode; new fields join
        # the shared allowlist since they may be surfaced for both modes.
        "stack_mode",
        "split_distance",
        "stack_tranche_count_target",
        "stack_spacing_mode",
        # v3.23.25 — bulk_partial_on_return retired (see BotConfig comment)
        "max_entry_price",
        "min_entry_price",
    }
)

#: Fields that are ONLY meaningful for ScrummingBot. Passing any of
#: these to make_bot_config(mode=EXTRACTOR, ...) raises ValueError —
#: this is the structural enforcement that prevents stale
#: ScrummingBot config defaults from leaking into Extractor configs.
_BOT_CONFIG_SCRUMMING_ONLY_FIELDS: frozenset = frozenset(
    {
        # v3.23.3 R-CLN Phase 1: 8 grid-legacy dead fields excised after
        # empirical grep confirmed zero references in scrumming_bot.py.
        # See docs/audits/2026-06-12_scrumming_bot_field_alignment.md for
        # the field list. Operator-approved scope.
        "investment_amount",
        "increment_style",
        "spacing_style",  # v3.23.25 market_check_interval removed
        "profit_folding_active",
        # Scrumming-specific accumulation/routing
        "scrumming_interval_pct",
        "profit_route",
        "profit_route_bot_id",
        "scrum_fold_pct",
        "max_target_growth_pct",
        # Item 9 — despawn timer. Scrumming-only: the two ledgers it
        # sweeps (`_fold_tranches`, `_stack_tranches`) are ScrummingBot
        # state and neither exists on ExtractorBot.
        "tranche_despawn_days",
        "bb_tolerance_pct",
        "bb_landing_strip_candles",
        "scrum_detect_pct",
        "scrum_fire_pct",
        "bb_midline_gate",
        "scrum_read_rate_min",
        "band_travel_pct",
        "bb_bullseye_check",
        "hedge_rebalance_active",
        "hedge_balance",
        "circuit_breaker_soft_pct",
        "circuit_breaker_hard_pct",
        "circuit_breaker_cooldown_candles",
        "max_cartridge_size_pct",
        "max_cartridge_smart",
        "max_cartridge_smart_ceiling_pct",
        "wire_inflow_stack_pct",
        # v3.16.15 strategy gates
        "scrum_require_ta_bullish",
        "scrum_hold_in_uptrend",
        "scrum_defer_to_htf",
        "fold_require_ta_bearish",
        "fold_hold_in_downtrend",
        "fold_defer_to_htf",
        # MEM-244 risk controls
        "position_ceiling_enabled",
        "position_ceiling_multiple",
        "detonation_enabled",
        "detonation_timeframe",
        "detonation_confidence_min",
        # v3.23.42 interop
        "self_reserve_capital",
        "personal_hold_qty",
    }
)

#: Fields that are ONLY meaningful for ExtractorBot. Passing any of
#: these to make_bot_config(mode=SCRUMMING, ...) raises ValueError.
_BOT_CONFIG_EXTRACTOR_ONLY_FIELDS: frozenset = frozenset(
    {
        "extractor_chunk_size_usd",
        "extractor_artillery_size_usd",
        "extractor_scan_top_n",
        "extractor_scan_refresh_candles",
        "extractor_pool_reserve_pct",
        "extractor_exit_pct",
        "extractor_drawdown_threshold_pct",
        "extractor_correction_skip_candles",
        "extractor_max_cost_basis_multiple",
        "extractor_max_compounding_tier",
        "extractor_hedge_budget_usd",
        "extractor_trend_strength_threshold",
        "extractor_alt_targets",
        # v3.20.74 — Inverted Extractor direction flag + standing-position
        # import (Q6/Q7/Q8/Q9 locks)
        "extractor_direction",
        "inverted_extractor_standing_alt_units",
    }
)


# v3.23.25 — deprecated kwargs that may appear in older bot_state.json
# files. `_sanitize_deprecated_kwargs()` silently drops these before
# they reach BotConfig.__init__ so restore paths don't TypeError.
# Operator directive 2026-07-25: bulk_trading was always-False in
# practice; we can drop the key without behaviour loss because the
# new stack_mode replacement defaults to False (same effective
# behaviour). bulk_partial_on_return was declared but never read.
_DEPRECATED_KWARGS: frozenset = frozenset(
    {
        "bulk_trading",  # renamed to stack_mode; historically always False
        "bulk_partial_on_return",  # retired; never had a runtime consumer
        "market_check_interval",  # retired v3.23.25; never had a runtime consumer
        # v3.23.3 R-CLN Phase 1 grid-legacy fields (kept here so any
        # bot_state.json still carrying them doesn't crash on load):
        "position_count",
        "position_distance_pct",
        "fold_mode",
        "fold_target",
        "fold_target_count",
        "profit_fold_pct",
        "distribute_target",
        "distribute_target_count",
    }
)


#: An int this large already exceeds float range, so converting one
#: raises OverflowError rather than returning inf. Ints outside the
#: bound are refused instead of converted; 2**1023 is under the float
#: maximum (~1.798e308) and no real timestamp or setting approaches it.
_FLOAT_SAFE_INT: int = 2**1023

#: Saturation bound for the despawn threshold: 10,000 years in days.
#: Beyond this the value stops meaning anything different — no record
#: is ever that old — while an unbounded one makes `days * 86400.0`
#: raise OverflowError on a huge int read from a corrupted state file.
#: Saturating keeps the arithmetic in range and loses no behaviour.
DESPAWN_MAX_DAYS: int = 3_650_000


def as_finite_float(value) -> Optional[float]:
    """`value` as a float when it is EXACTLY int or float AND finite.

    None for everything else, and None is an answer rather than an
    error: the callers treat it as "no usable number here".

    EXACT TYPE, not `isinstance`, matching the Fold Tranches panel's own
    reader in bot_live_settings.py. `bool` is a subclass of `int`, so
    `isinstance(True, int)` is True and a stored `True` would read as
    the number 1 — one day of threshold, or a timestamp at the epoch
    that dates a record to about 56 years old. Refused here by type.

    AND FINITE, WHICH EXACT TYPE ALONE DOES NOT GIVE. A type is not a
    domain: `type(float("nan")) is float` is True, so the strictest
    possible type gate still admits `nan`, `inf` and `-inf`. Those are
    not merely odd values — `int(nan)` raises ValueError and `int(inf)`
    raises OverflowError. Reachability is low but not zero: the two
    spinboxes are integer-only and clamped, but `json.dumps(float("nan"))`
    emits bare `NaN` and `json.loads("NaN")` returns it (both measured
    2026-08-13), so a hand-edited or corrupted state file reaches this.

    HUGE INTS ARE REFUSED RATHER THAN CONVERTED. `float()` of an int
    above the float maximum raises OverflowError, so the bound is
    checked with an integer comparison, which is exact and cannot itself
    raise. JSON has no integer width limit, so this shape is reachable
    from the same corrupted file as `NaN`.

    Args:
      value: anything at all, including values read straight off a
        JSON-decoded state file.

    Returns:
      The finite float, or None when `value` is not a usable number.
    """
    if type(value) is float:
        return value if math.isfinite(value) else None
    if type(value) is int and -_FLOAT_SAFE_INT <= value <= _FLOAT_SAFE_INT:
        return float(value)
    return None


def despawn_threshold_days(config) -> int:
    """The tranche despawn threshold in whole days. 0 means OFF.

    THE ONE RULE, READ BY BOTH SURFACES. `ScrummingBot.
    _despawn_aged_tranches` sweeps on this and the live-settings spinbox
    seeds itself from it, so a stored value cannot mean one thing to the
    sweep and another to the control that sets it.

    A NON-NUMERIC, NON-FINITE OR NEGATIVE SETTING IS OFF, decided before
    any comparison runs. `as_finite_float` above carries the type and
    value reasoning; `max(0, ...)` is what stops `-5` meaning "delist
    everything".

    TRUNCATION IS TOWARD ZERO, so 30.7 days is a 30-day threshold. The
    field is declared `int`; a float only arrives from a hand-edited
    file, and rounding a corrupted value up would delist more.

    THE VALUE IS NOT CLAMPED TO THE SPINBOX RANGE. That control offers
    0-365, but the config is the authority and silently truncating a
    larger stored number would misreport the operator's own setting.
    The only bound is the saturation at `DESPAWN_MAX_DAYS`, which is
    10,000 years and changes no reachable behaviour.

    Args:
      config: any object. The field is read with `getattr`, so a config
        predating it — every bot restored from a state file written
        before 2026-08-13 — reads as OFF.

    Returns:
      Whole days in [0, DESPAWN_MAX_DAYS]. 0 means the timer is off.
    """
    days = as_finite_float(getattr(config, "tranche_despawn_days", 0))
    if days is None:
        return 0
    return min(DESPAWN_MAX_DAYS, max(0, int(days)))


def _sanitize_deprecated_kwargs(kwargs: dict) -> dict:
    """Drop any deprecated keys from a kwargs dict, returning the
    caller-safe subset. Callers must pass the *sanitized* dict to
    BotConfig.__init__ / make_bot_config. This preserves
    bot_state.json compatibility for files saved under older schemas.

    v3.23.26 — also normalizes stack_spacing_mode values: the v3.23.25
    "logarithmic" label was renamed to "quadratic" for accuracy. Any
    incoming "logarithmic" value is silently promoted to "quadratic"
    so freshly-saved v3.23.25 states still load."""
    out = {k: v for k, v in kwargs.items() if k not in _DEPRECATED_KWARGS}
    if out.get("stack_spacing_mode") == "logarithmic":
        out["stack_spacing_mode"] = "quadratic"
    return out


def make_bot_config(mode, **kwargs) -> BotConfig:
    """v3.20.33 — typed factory for BotConfig.

    The canonical construction path for new BotConfig instances.
    Enforces mode-shape at construction time so the operator-reported
    2026-05-25 bug class (ScrummingBot-shape leaks into Extractor)
    cannot recur:

      - mode-foreign kwargs raise ``ValueError`` (Scrumming-only
        fields passed with mode=EXTRACTOR, and vice versa)
      - mode is propagated into the BotConfig.mode field
      - mode-aware target_asset default applied if caller omits it
        (Extractor → "*" sigil; Scrumming → "BTC" legacy default)
      - the constructed BotConfig is validated via
        ``validate_mode_shape()`` and any violation re-raised

    Direct ``BotConfig(...)`` calls outside this factory are flagged
    by the architectural fitness rule in
    ``tests/test_architectural_fitness.py``.

    Args:
        mode: BotMode (EXTRACTOR or SCRUMMING) — required positional
        **kwargs: BotConfig dataclass field values

    Raises:
        ValueError: any mode-foreign kwarg, or any validate_mode_shape
            violation that survives construction

    Returns:
        A BotConfig instance with mode set and shape validated.
    """
    if not isinstance(mode, BotMode):
        raise TypeError(
            f"make_bot_config(): mode must be BotMode enum, got "
            f"{type(mode).__name__}={mode!r}"
        )

    # v3.23.25 — drop deprecated keys from bot_state.json before any
    # mode-shape validation. Prevents the "position_count-class"
    # TypeError from recurring on load of older saved states.
    kwargs = _sanitize_deprecated_kwargs(kwargs)

    # Identify mode-foreign kwargs BEFORE construction so we get a
    # clean error message naming the offending fields.
    foreign: list = []
    if mode == BotMode.EXTRACTOR:
        for key in kwargs:
            if key in _BOT_CONFIG_SCRUMMING_ONLY_FIELDS:
                foreign.append(key)
    elif mode == BotMode.SCRUMMING:
        for key in kwargs:
            if key in _BOT_CONFIG_EXTRACTOR_ONLY_FIELDS:
                foreign.append(key)
    if foreign:
        raise ValueError(
            f"make_bot_config(mode={mode.value}): mode-foreign "
            f"kwargs {sorted(foreign)} cannot be passed to a "
            f"{mode.value} bot config. These are "
            f"{'Scrumming-only' if mode == BotMode.EXTRACTOR else 'Extractor-only'} "
            f"fields — passing them on a {mode.value} config "
            f"would silently store nonsense values that leak into "
            f"downstream display/persistence. See "
            f"_BOT_CONFIG_SCRUMMING_ONLY_FIELDS / "
            f"_BOT_CONFIG_EXTRACTOR_ONLY_FIELDS in bot_container.py."
        )

    # Mode-aware default for target_asset (Extractor: "*" sigil;
    # Scrumming: "BTC" legacy fallback). Caller-provided value wins.
    if "target_asset" not in kwargs:
        kwargs["target_asset"] = "*" if mode == BotMode.EXTRACTOR else "BTC"

    # Construct + validate. If validate_mode_shape returns
    # violations, raise — the operator shouldn't see those as
    # warnings; the factory's job is to produce VALID configs.
    cfg = BotConfig(mode=mode, **kwargs)
    violations = cfg.validate_mode_shape()
    if violations:
        raise ValueError(
            f"make_bot_config(mode={mode.value}): construction "
            f"produced an invalid config. Violations:\n  " + "\n  ".join(violations)
        )
    return cfg


# ---------------------------------------------------------------------------
# Bot runtime stats
# ---------------------------------------------------------------------------
@dataclass
class BotStats:
    """Mutable runtime statistics — updated by the bot during operation."""

    total_trades: int = 0
    total_buys: int = 0
    total_sells: int = 0
    trade_volume: float = 0.0  # Cumulative USD volume traded
    realised_pnl: float = 0.0
    unrealised_pnl: float = 0.0
    active_buy_orders: int = 0
    active_sell_orders: int = 0
    current_price: float = 0.0
    position_value: float = 0.0
    accumulated_fold: float = 0.0  # Tracks toward extended position
    accumulated_distribute: float = 0.0  # Tracks toward extended position
    # v3.24.44 — fold tranches DISCARDED by an operator clear, never
    # folded. Deliberately separate from any "closed" counter so that one
    # keeps meaning "actually folded"; see
    # ScrummingBot.clear_fold_tranches.
    tranches_discarded_lifetime: int = 0
    # v3.24.45 — USD of parked wire credit discarded by an operator
    # clear. An earmark released, not funds moved.
    wire_credits_discarded_lifetime: float = 0.0
    extended_positions_created: int = 0
    consecutive_errors: int = 0
    last_error: str = ""
    last_trade_time: float = 0.0
    uptime_seconds: float = 0.0
    # R55 VH v3 telemetry (per R57 EPM — parity with sim engines)
    verify_clean: int = 0
    verify_adjusted: int = 0
    verify_canceled: int = 0
    verify_samples: int = 0
    # v3.15.50 — Platform high-score counters. Operator directive
    # 2026-04-24: "How about display total scrummed and total folded.
    # Like two high scores for the platform run." Per-bot accumulators
    # of SCRUM (sell) USD and FOLD (buy) USD; the header sums across
    # all running bots.
    total_scrummed_usd: float = 0.0
    total_folded_usd: float = 0.0
    # v3.23.60 — YTD (year-to-date, since YTD_TRADE_ANCHOR_UTC =
    # 2026-04-01) buy/sell USD totals pulled from the exchange
    # trade history via sync_ytd_trade_count. Populated by the
    # same paginated chunked-window walk that sets
    # exchange_trade_count. The dashboard "Scrummed" / "Folded"
    # cards prefer these over the platform-run accumulators when
    # exchange_data_fresh_ts > 0, so the display reflects real
    # exchange totals rather than internal counters that only
    # count fills fired since the current process started.
    ytd_scrummed_usd: float = 0.0
    ytd_folded_usd: float = 0.0
    # v3.16.46 — Cumulative error counter. Operator directive
    # 2026-05-10: "No error counter updating despite all the prior CCX
    # error occurrences." The existing `consecutive_errors` resets on
    # success, and the header's "Errors" stat counts bots CURRENTLY in
    # ERROR state — neither surfaces total error count over the bot's
    # lifetime. This counter never resets; it increments alongside
    # consecutive_errors at every error site (line ~676 in this file).
    total_errors: int = 0
    # v3.16.46 — Exchange-pulled position health. Operator directive:
    # "Everything that is available on the exchange and is related to
    # position health should not be getting calculated locally in some
    # strange manner." These fields are refreshed periodically by the
    # bot tick loop via the connector's get_my_trades + the
    # position_health module. They reflect Coinbase-truth values
    # rather than the synthetic accumulators (realised_pnl,
    # unrealised_pnl) that were previously the sole source.
    # Default 0 means "not yet refreshed" — call sites should respect
    # exchange_data_fresh_ts to know if the value is stale.
    realized_pnl_exchange: float = 0.0  # FIFO-matched realized P/L
    avg_entry_exchange: float = 0.0  # weighted-avg cost basis
    cost_basis_total_exchange: float = 0.0  # qty × avg_entry
    fees_paid_exchange: float = 0.0
    exchange_trade_count: int = 0
    exchange_data_fresh_ts: float = 0.0  # unix-seconds of last refresh
    # v3.16.48 — Operator directive 2026-05-10: "Pull the data and
    # display it. Spendable balance is my cash." The Spendable header
    # widget should show actual exchange wallet cash (USD + USDC),
    # not a derived "mature" calculation. Each bot caches the
    # quote-currency balance from its connector during refresh; the
    # bot_manager aggregator picks the freshest value (all bots share
    # the same wallet so all values converge to the same number).
    cash_balance_usd: float = 0.0

    # v3.16.50 — Standing surplus accumulator (Tranche-Surplus discipline).
    # Mirrors ScrummingBot._standing_surplus_usd. Surplus from fold-back
    # rebuys that exceed Target Delta accrues here.
    #
    # v3.24.50 — TWO CORRECTIONS to what this comment used to claim.
    #
    # It said "Surfaced for visibility (Status tab + diagnostics)". It
    # was not: a grep of src/gui/ for `standing_surplus` returned zero
    # matches. It is surfaced NOW, via get_status and the Fold Tranches
    # panel, which is what makes the sentence true rather than the
    # sentence making it so.
    #
    # It also said the per-cycle growth budget "drains it into
    # target_balance over time". There is no drain: `_standing_surplus_usd`
    # has no decrement anywhere in src/. Money accrues here and stays.
    # Implementing that drain is Phase 2 Step 7 of the tranche repair
    # plan; until it lands, this field is a one-way sink and the comment
    # must not imply otherwise.
    standing_surplus_usd: float = 0.0


# ---------------------------------------------------------------------------
# Bot container
# ---------------------------------------------------------------------------
class BotContainer:
    """
    Isolated auto-trader container.  Subclassed by ``ScrummingBot`` (the
    only remaining engine; ``GridBot`` was deleted v3.16.0). Original
    docstring left intact below for historical context. New text:
    ``ScrummingBot`` which implement the mode-specific trading logic.

    Lifecycle::

        bot = ScrummingBot(config, exchange)
        await bot.start()     # Begins the trading loop
        await bot.pause()     # Suspends without cancelling orders
        await bot.resume()    # Resumes from pause
        await bot.stop()      # Graceful shutdown
    """

    MAX_CONSECUTIVE_ERRORS = 5
    COOLDOWN_SECONDS = 60

    def __init__(
        self,
        config: BotConfig,
        exchange: ExchangeInterface,
    ) -> None:
        self.bot_id: str = str(uuid.uuid4())[:8]
        self.config = config
        self.exchange = exchange
        self.stats = BotStats()
        self.state = BotState.IDLE
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._start_time: float = 0.0
        self._bus = get_event_bus()
        self._volume_guard = None  # Set by BotManager if available
        self._data_pool = None  # Set by BotManager if available
        # v3.15.78 — Pre-flight precision-check cache. Operator
        # directive 2026-04-27: "We should not be spamming the APIs
        # with improperly valued orders." Maps symbol → (min_amount,
        # min_cost, amount_precision). Lazy-loaded from
        # exchange.get_markets() on first need; refreshed only when
        # explicitly invalidated. Markets rarely change at the
        # min-precision level so a long-lived cache is safe.
        self._market_limits_cache: dict[str, tuple] = {}
        # ------------------------------------------------------------
        # Phantom settings — given a starting value HERE, on the shared
        # parent, so that get_full_state writes both keys for every bot.
        #
        # THE DEFECT THIS CLOSES: only ScrummingBot ever set
        # _phantoms_enabled, and it does so in its own constructor.
        # Every other bot reached get_full_state with the attribute
        # missing, and the guarded read there simply left the key out.
        # A saved Extractor and a saved Scrumming bot therefore had
        # differently-shaped records, and nothing in the file said why.
        #
        # False is taken from the code, not chosen: ExtractorBot
        # declares enable_phantoms=False as its own default and never
        # stores the value, and restore_bots_from_state builds every
        # ExtractorBot with enable_phantoms=False. The Extractor is
        # exactly the bot that was missing the key. ScrummingBot
        # overwrites this line moments later from its own constructor
        # argument, so no phantom behaviour changes for it.
        self._phantoms_enabled: bool = False
        # Nothing in the codebase assigns _phantom_config, so the export
        # has never emitted this key for any bot at all. The empty
        # mapping is what "no phantom settings were recorded" looks
        # like. Restore reads no such key back, so no behaviour hangs
        # on the value — only the shape of the saved record changes.
        self._phantom_config: dict = {}

    def force_fire(self, aggressive: bool = False) -> None:
        """MEM-236 + MEM-241 — Manual Fire from the dashboard. Base
        implementation is a no-op; ScrummingBot overrides. Grid bots
        ignore (no equivalent rate-gate and no rebalance semantic).
        Called from the GUI thread via BotManager, so the
        implementation must be thread-safe and non-blocking — set a
        flag or counter; do NOT call async methods directly here.

        Args:
            aggressive: MEM-241. When True (new GUI default), the
                scrumming implementation executes a market-order
                rebalance-to-target bypassing TA/BB gates. When False,
                legacy MEM-236 behavior (flush tick-skip, run normal
                gate checks next tick).
        """
        return

    async def _get_market_limits(
        self,
        symbol: str,
    ) -> tuple[float, float, int]:
        """v3.15.78 — Return ``(min_amount, min_cost, amount_precision)``
        for ``symbol`` from the exchange's market metadata. Cached on
        the bot for the bot's lifetime (markets rarely change at the
        precision level). Returns ``(0.0, 0.0, 8)`` on any lookup
        failure so the caller fails-open rather than blocking trades
        on metadata absence.

        Operator directive 2026-04-27: "We should not be spamming the
        APIs with improperly valued orders."

        sadp: R28 R44
        """
        cached = self._market_limits_cache.get(symbol)
        if cached is not None:
            return cached
        try:
            markets = await self.exchange.get_markets()
        except Exception as exc:
            logger.debug(
                "Bot %s could not fetch markets for precision check: %s",
                self.bot_id,
                exc,
            )
            # Negative-cache the failure briefly so we don't spam
            # get_markets() on every order. Fail-open with
            # zero-min so trades still flow.
            fallback = (0.0, 0.0, 8)
            self._market_limits_cache[symbol] = fallback
            return fallback
        for m in markets or []:
            if getattr(m, "symbol", None) == symbol:
                limits = (
                    float(getattr(m, "min_amount", 0.0) or 0.0),
                    float(getattr(m, "min_cost", 0.0) or 0.0),
                    int(getattr(m, "amount_precision", 8) or 8),
                )
                self._market_limits_cache[symbol] = limits
                return limits
        # Symbol not in markets list — cache zero so we don't re-loop
        fallback = (0.0, 0.0, 8)
        self._market_limits_cache[symbol] = fallback
        return fallback

    async def guarded_place_order(
        self,
        symbol: str,
        side: "OrderSide",
        order_type: "OrderType",
        amount: float,
        price: Optional[float] = None,
        purpose: str = "trade",
    ) -> "Order":

        # sadp: R28 R29  # order placement: fail-loudly(R28) idempotent(R29)
        """
        Place an order through the VolumeGuard if available.
        Falls back to direct exchange.place_order if guard is disabled/absent.

        v3.15.78 — Pre-flight precision check. If the rounded amount is
        below the exchange's ``min_amount`` for ``symbol``, OR the
        notional cost (amount × price) is below ``min_cost``, raise a
        ``PRE-FLIGHT REJECTED`` exception WITHOUT calling the exchange.
        Operator directive 2026-04-27: "We should not be spamming the
        APIs with improperly valued orders." Caught by the existing
        SCRUM/FOLD failure-handling at every call site (which logs
        ``SELL FAILED: {exc}`` / ``BUY FAILED: {exc}``); the
        ``PRE-FLIGHT REJECTED`` prefix in the message lets the operator
        distinguish locally-rejected orders from exchange-rejected
        ones at a glance.
        """
        from ..exchange.base import OrderSide, OrderType, Order, OrderStatus

        # ============================================================
        # THE AMOUNT MUST BE A NUMBER. NOTHING ELSE REACHES THE VENUE.
        # ============================================================
        # Every dispatch path out of this method is BELOW this block:
        # the VolumeGuard call and the direct exchange call. Both hand
        # the caller's ``amount`` object on unchanged, so this is the
        # only place that can refuse it.
        #
        # THE SIZE CHECK BELOW CANNOT DO THIS JOB. It reads
        # ``float(amount)`` inside a try that yields 0.0 on failure,
        # and it decides with ``<``. Both steps are blind to a NaN:
        # ``math.floor(nan * scale)`` raises ValueError, which drops
        # the test back to ``_amt < _min_amount``, and every
        # comparison against NaN is False. A NaN amount therefore
        # passed the size check and was handed to the exchange. A live
        # path produces one: when standing_surplus_usd cannot be read
        # the fold preview returns NaN, and that value is an addend in
        # buy_usd_target.
        #
        # THE TYPE TEST IS EXACT, NOT ``isinstance``. An isinstance
        # test admits every subclass, so ``bool`` passes it and
        # ``float(True)`` then makes True look like a one-unit order.
        # It also admits a float subclass, an int subclass, an IntEnum
        # member and every numpy scalar. The abstract types do not
        # describe the domain either: measured on Python 3.14, ``bool``
        # passes numbers.Real, ``Decimal`` fails it and ``Fraction``
        # passes it. A type is not a domain. An exact type test cannot
        # be spoofed from Python.
        #
        # THIS REFUSAL IS LOUDER THAN THE SIZE REFUSAL BELOW, and it
        # should be. An order below the exchange minimum is ordinary
        # market friction. An amount that is not a finite positive
        # number means an upstream invariant is ALREADY broken, so it
        # is logged at error level here, where the bot and the symbol
        # are both known.
        _side_str = "BUY" if side == OrderSide.BUY else "SELL"
        _amt_is_number = type(amount) in (int, float)
        _amt = 0.0
        if _amt_is_number:
            try:
                _amt = float(amount)
            except (TypeError, ValueError, OverflowError):
                # An int too large for a float lands here. It has no
                # float value, so it has no usable size.
                # ``math.isfinite`` would raise OverflowError on it for
                # the same reason, which is why the conversion is
                # guarded here rather than left to the test below.
                _amt_is_number = False
                _amt = 0.0
        if not _amt_is_number or not math.isfinite(_amt) or _amt <= 0.0:
            # ``math.isfinite`` is read BEFORE the positivity test on
            # purpose. ``nan <= 0.0`` is False, so a positivity test
            # alone would pass a NaN straight through.
            logger.error(
                "Bot %s PRE-FLIGHT REJECTED %s %s: amount is not a finite "
                "positive number: %r (type %s). Upstream produced an "
                "unusable size; the API was not called.",
                getattr(self, "bot_id", "?"),
                _side_str,
                symbol,
                amount,
                type(amount).__name__,
            )
            raise Exception(
                f"PRE-FLIGHT REJECTED: {_side_str} {symbol} amount is not "
                f"a finite positive number: {amount!r} "
                f"(type {type(amount).__name__}). An amount that is not a "
                f"number cannot be sized, compared or sent, and this one "
                f"means an upstream value is already corrupt. "
                f"API not called."
            )

        # ============================================================
        # v3.15.78 — Pre-flight precision check.
        # ============================================================
        # Look up the exchange's min_amount / min_cost for this symbol.
        # Round the requested amount to amount_precision before the
        # comparison (the exchange does this internally; if our amount
        # rounds to zero or below min, the exchange rejects with
        # "amount precision" errors like the operator-reported RAVE
        # case from 2026-04-27).
        try:
            _min_amount, _min_cost, _amount_prec = await self._get_market_limits(symbol)
        except Exception:  # R28-OK: market-limits probe; safe defaults if fetch fails
            _min_amount, _min_cost, _amount_prec = 0.0, 0.0, 8

        # Truncate (NOT round) the amount to the exchange's precision.
        # Banker's rounding (Python's default) would let 0.05 RAVE pass
        # a 0.1-min check by rounding UP to 0.1, but the exchange itself
        # truncates excess precision. Truncation matches reality.
        #
        # The size test below is made in WHOLE STEPS, not in fractions
        # of a coin. A step is the smallest size the exchange will
        # accept for this symbol. Both sides are scaled up by the same
        # power of ten, so the test compares two whole counts of the
        # same thing. Nothing is divided to reach the verdict, and
        # comparing whole counts cannot drift the way comparing
        # fractions can.
        #
        # The two sides round in OPPOSITE directions, on purpose:
        #   • the requested size rounds DOWN, because the exchange
        #     throws away any size below a whole step;
        #   • the minimum rounds UP, because a minimum of any size at
        #     all still demands at least one whole step. Rounding the
        #     minimum down would turn a minimum smaller than one step
        #     into a minimum of zero, and a zero-size order would then
        #     be handed to the exchange instead of being refused here.
        #
        # ``_amt_trunc`` below is still worked out, but only so the
        # rejection message can quote the truncated size back to the
        # operator.
        import math as _math

        _amt_steps: Optional[int] = None
        _min_steps: Optional[int] = None
        if _amount_prec >= 0:
            try:
                _scale = 10 ** int(_amount_prec)
                _amt_steps = _math.floor(_amt * _scale)
                _min_steps = _math.ceil(_min_amount * _scale)
                _amt_trunc = _amt_steps / _scale
            except (TypeError, ValueError, OverflowError):
                _amt_steps = None
                _min_steps = None
                _amt_trunc = _amt
        else:
            _amt_trunc = _amt

        # When the step counts could not be worked out (precision is
        # negative, or the scaling overflowed) fall back to comparing
        # the untruncated size, exactly as before.
        if _amt_steps is None or _min_steps is None:
            _below_min = _amt < _min_amount
        else:
            _below_min = _amt_steps < _min_steps
        if _min_amount > 0 and _below_min:
            raise Exception(
                f"PRE-FLIGHT REJECTED: {_side_str} amount {_amt:.8f} "
                f"({_amt_trunc:.{max(_amount_prec,0)}f} after truncating "
                f"to precision={_amount_prec}) is below {symbol} "
                f"min_amount {_min_amount}. API not called."
            )

        if _min_cost > 0 and price is not None:
            try:
                _px = float(price)
            except (TypeError, ValueError):
                _px = 0.0
            if _px > 0:
                _notional = _amt * _px
                if _notional < _min_cost:
                    raise Exception(
                        f"PRE-FLIGHT REJECTED: {_side_str} notional "
                        f"${_notional:.4f} ({_amt:.8f} \u00d7 ${_px:.8f}) "
                        f"is below {symbol} min_cost ${_min_cost:.4f}. "
                        f"API not called."
                    )

        # ============================================================
        # End of pre-flight check. Continue to existing dispatch.
        # ============================================================

        if self._volume_guard and self._volume_guard.enabled:
            side_str = "buy" if side == OrderSide.BUY else "sell"
            ot_str = "market" if order_type == OrderType.MARKET else "limit"
            report = await self._volume_guard.execute(
                symbol,
                side_str,
                amount,
                price=price or 0,
                order_type=ot_str,
                exchange=self.exchange,
            )

            if not report.success:
                raise Exception(f"VolumeGuard execution failed: {report.reason}")

            # Construct a synthetic Order from the report
            return Order(
                id=f"vg_{int(time.time()*1000)}",
                symbol=symbol,
                side=side,
                type=order_type,
                amount=report.requested_amount,
                price=report.avg_fill_price,
                filled=report.executed_amount,
                remaining=report.requested_amount - report.executed_amount,
                average=report.avg_fill_price,
                status=(
                    OrderStatus.CLOSED
                    if report.executed_amount > 0
                    else OrderStatus.FAILED
                ),
                timestamp=time.time(),
            )

        # ============================================================
        # v3.15.98 — TD-004 idempotency closure.
        # ============================================================
        # Derive a deterministic client_order_id from the trade INTENT
        # (symbol + side + amount + price + bot_id + purpose + session
        # nonce). On retry of the same intent within TTL the same coid
        # is reused; the exchange refuses the duplicate (Coinbase 409,
        # Binance -2010), preventing double-fills from network-timeout
        # retry storms. See src/exchange/idempotency.py for the full
        # design rationale.
        from ..exchange.idempotency import get_idempotency_layer, TradeIntent

        _idem = get_idempotency_layer()
        _intent = TradeIntent(
            symbol=symbol,
            side="buy" if side == OrderSide.BUY else "sell",
            amount=float(amount),
            price=float(price) if price is not None else None,
            bot_id=getattr(self, "bot_id", "?"),
            purpose=purpose,
        )
        _coid = _idem.derive_coid(_intent)

        # No guard — direct execution
        try:
            order = await self.exchange.place_order(
                symbol, side, order_type, amount, price, client_order_id=_coid
            )
            _idem.mark_fulfilled(_intent)
            return order
        except Exception:
            # On non-409 rejection, invalidate so a future legitimate
            # retry can generate a fresh coid. We can't always tell from
            # here whether it was 409 (duplicate, GOOD — keep) vs other
            # 4xx (invalidate); err on the side of keeping cached. The
            # TTL window will evict if it never resolves.
            raise

    # -- Lifecycle ------------------------------------------------------
    async def start(self) -> None:
        """Launch the bot's trading loop in a guarded asyncio task."""
        if self.state in (BotState.RUNNING, BotState.STARTING):
            logger.warning("Bot %s already running", self.bot_id)
            return

        # v3.15.98 — clear stale last_error on (re)start. Operator-reported
        # 2026-04-28: a NameError captured during a prior run kept showing
        # in the dashboard "Last Error" panel after the bug was fixed,
        # making it impossible to tell whether the latest start was clean
        # or still broken. Stamp a fresh start: reset the error and consec
        # counter so the panel reflects the CURRENT session.
        self.stats.last_error = ""
        self.stats.consecutive_errors = 0

        self.state = BotState.STARTING
        self._stop_event.clear()
        self._start_time = time.monotonic()
        # Register with shared data pool
        if self._data_pool:
            self._data_pool.register(
                self.config.exchange_id,
                self.config.symbol,
                getattr(self.config, "ta_timeframe", "1h"),
            )
        self._task = asyncio.create_task(self._run_with_guard())
        self._bus.emit("bot.started", bot_id=self.bot_id, config=self.config)
        logger.info("Bot %s starting on %s", self.bot_id, self.config.symbol)

    async def stop(self) -> None:
        """Gracefully stop the bot and cancel remaining orders."""
        self._stop_event.set()
        self._pause_event.set()  # Unpause so the loop can exit
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.state = BotState.STOPPED
        self.stats.uptime_seconds = time.monotonic() - self._start_time
        # Unregister from shared data pool
        if self._data_pool:
            self._data_pool.unregister(
                self.config.exchange_id,
                self.config.symbol,
                getattr(self.config, "ta_timeframe", "1h"),
            )
        self._bus.emit("bot.stopped", bot_id=self.bot_id)
        logger.info("Bot %s stopped", self.bot_id)

    async def pause(self) -> None:
        """Suspend the trading loop without cancelling orders."""
        self._pause_event.clear()
        self.state = BotState.PAUSED
        self._bus.emit("bot.paused", bot_id=self.bot_id)

    async def resume(self) -> None:
        """Resume from paused state."""
        self._pause_event.set()
        self.state = BotState.RUNNING
        self._bus.emit("bot.resumed", bot_id=self.bot_id)

    # -- Fault-isolated execution wrapper --------------------------------
    async def _run_with_guard(self) -> None:
        # sadp: R28 R32  # circuit-breaker wrapper(R32) fail-loudly(R28)
        """
        Wraps the trading loop in a fault boundary.  All exceptions are
        caught, logged, and emitted as events.  After MAX_CONSECUTIVE_ERRORS,
        the bot enters cooldown before retrying.
        """
        self.state = BotState.RUNNING
        try:
            while not self._stop_event.is_set():
                try:
                    # Wait if paused
                    await self._pause_event.wait()
                    if self._stop_event.is_set():
                        break

                    # === MAIN TRADING TICK ===
                    await self.tick()

                    # Reset error counter on success
                    self.stats.consecutive_errors = 0
                    # v3.24.40 (C54 / NF-122) — clear the ERROR state a
                    # failing tick set below. Only ERROR is cleared:
                    # COOLDOWN owns its own transition back to RUNNING,
                    # and PAUSED/STOPPING must not be overwritten by a
                    # tick that happened to succeed.
                    if self.state == BotState.ERROR:
                        self.state = BotState.RUNNING

                    # v3.16.5 — heartbeat update of uptime_seconds. The
                    # dashboard reads this via get_status_dict; without
                    # the heartbeat, the operator-facing Uptime display
                    # never increments while the bot is running. Cheap
                    # operation; safe to do every tick.
                    if self._start_time:
                        self.stats.uptime_seconds = time.monotonic() - self._start_time

                except asyncio.CancelledError:
                    raise  # Let cancellation propagate
                except Exception as exc:
                    self.stats.consecutive_errors += 1
                    self.stats.total_errors += 1  # v3.16.46 — cumulative, never resets
                    self.stats.last_error = f"{type(exc).__name__}: {exc}"
                    # v3.24.40 (C54 / NF-122) — BotState.ERROR was
                    # assigned NOWHERE in src/. It was only ever
                    # compared against, in get_aggregate_stats, so the
                    # dashboard's current-state "Errors" count was
                    # structurally pinned at zero: a bot could fail
                    # every tick and the fleet still reported 0 errored.
                    # The state machine went RUNNING -> COOLDOWN (at 5
                    # consecutive) -> RUNNING and skipped ERROR
                    # entirely. Set it here so a failing bot is visible
                    # from the first failure rather than the fifth.
                    self.state = BotState.ERROR
                    logger.error(
                        "Bot %s error (%d/%d, lifetime %d): %s",
                        self.bot_id,
                        self.stats.consecutive_errors,
                        self.MAX_CONSECUTIVE_ERRORS,
                        self.stats.total_errors,
                        exc,
                    )
                    self._bus.emit(
                        "bot.error",
                        bot_id=self.bot_id,
                        error=str(exc),
                        consecutive=self.stats.consecutive_errors,
                    )

                    if self.stats.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                        self.state = BotState.COOLDOWN
                        self._bus.emit("bot.cooldown", bot_id=self.bot_id)
                        logger.warning(
                            "Bot %s entering cooldown for %ds",
                            self.bot_id,
                            self.COOLDOWN_SECONDS,
                        )
                        await asyncio.sleep(self.COOLDOWN_SECONDS)
                        self.stats.consecutive_errors = 0
                        self.state = BotState.RUNNING

                # Tick interval — subclasses can override
                await asyncio.sleep(self.tick_interval)

        except asyncio.CancelledError:
            pass
        finally:
            self.stats.uptime_seconds = time.monotonic() - self._start_time

    # -- Subclass hooks -------------------------------------------------
    @property
    def tick_interval(self) -> float:
        # sadp: R28 R29  # base tick: fail-loudly(R28) idempotent-order(R29)
        """Seconds between trading ticks.  Override in subclasses."""
        return 5.0

    async def tick(self) -> None:

        # sadp: R28 R29  # base tick: fail-loudly(R28) idempotent-order(R29)
        """
        One iteration of the trading loop.  Subclasses MUST override this
        with their mode-specific logic (grid management or scrumming).
        """
        raise NotImplementedError("Subclasses must implement tick()")

    # -- Status ---------------------------------------------------------
    def get_status(self) -> dict:
        """Return a snapshot of the bot's state and stats."""
        # MEM-236 — expose scrum SEARCH/TRACK/FIRE phase when this is a
        # scrumming bot subclass, so the GUI can pace tracking beeps.
        # None for grid bots (they don't have this phase machine).
        scrum_mode = getattr(self, "scrum_target_mode", None)
        # MEM-241 — armed_action is 'scrum' / 'fold' / None based on
        # delta sign. Drives the Fire button's internal color so the
        # operator sees whether pressing Fire will sell (scrum/red) or
        # buy (fold/green). None on grid bots and on scrumming bots
        # within the dust band around target.
        armed_action = getattr(self, "armed_action", None)
        # MEM-244 — Risk Control state for dashboard indicators
        anchor_tb = getattr(self, "_anchor_target_balance", None)
        ceiling_usd = getattr(self, "position_ceiling_usd", None)
        ceiling_ratio = getattr(self, "ceiling_ratio", None)
        fold_taper = getattr(self, "fold_rate_taper", 1.0)

        # v3.24.50 (Phase 1 Step 3) — how much queued tranche capital the
        # per-cycle filter can never admit. The filter takes a tranche
        # only if it fits ENTIRELY inside the remaining budget and
        # explicitly refuses to deploy part of one, so any single tranche
        # larger than the whole budget is skipped on every cycle forever.
        # Computed defensively: a status call must never raise.
        _over_cap_summary = {
            "tranches_over_cycle_cap": 0,
            "tranches_over_cycle_cap_usd": 0.0,
        }
        try:
            _budget = (
                float(getattr(self, "_anchor_target_balance", 0.0) or 0.0)
                * float(getattr(self.config, "max_target_growth_pct", 0.0) or 0.0)
                / 100.0
            )
            if _budget > 0:
                _over = [
                    float(_t.get("usd", 0) or 0)
                    for _t in (getattr(self, "_fold_tranches", []) or [])
                    if isinstance(_t, dict) and float(_t.get("usd", 0) or 0) > _budget
                ]
                _over_cap_summary = {
                    "tranches_over_cycle_cap": len(_over),
                    "tranches_over_cycle_cap_usd": round(sum(_over), 8),
                }
        except Exception as _oc_exc:  # noqa: BLE001 - status must not raise
            logger.debug(
                "over-cap tranche summary unavailable for %s: %s",
                getattr(self, "bot_id", "?"),
                _oc_exc,
            )

        return {
            "bot_id": self.bot_id,
            "state": self.state.value,
            "exchange": self.config.exchange_id,
            "symbol": self.config.symbol,
            "mode": self.config.mode.value,
            "scrum_target_mode": scrum_mode,  # MEM-236
            "armed_action": armed_action,  # MEM-241
            # MEM-244 Risk Controls
            "anchor_target_balance": anchor_tb,
            "position_ceiling_enabled": getattr(
                self.config, "position_ceiling_enabled", False
            ),
            "position_ceiling_multiple": getattr(
                self.config, "position_ceiling_multiple", 5.0
            ),
            "position_ceiling_usd": ceiling_usd,
            "ceiling_ratio": ceiling_ratio,
            "fold_rate_taper": fold_taper,
            "detonation_enabled": getattr(self.config, "detonation_enabled", False),
            "detonation_timeframe": getattr(self.config, "detonation_timeframe", "1d"),
            "target_balance": self.config.target_balance,
            # v3.24.50 (Phase 1 Step 3) — the COMPOUNDING SURFACE.
            #
            # `target_balance` above is `config.target_balance`: the
            # operator's input, which compounding does not move. The
            # number the bot actually trades against is the runtime
            # `_target_balance`, and it was exported nowhere, so no GUI
            # could show whether compounding had done anything. That is
            # the mechanism behind the target-delta drift docket.
            #
            # Read-only additions. Nothing consumes these to make a
            # trading decision; they exist so Phase 2 and Phase 3 are
            # observable, because the failure mode this whole cascade is
            # fixing is "it silently did nothing and nobody could tell".
            "live_target_balance": float(getattr(self, "_target_balance", 0.0) or 0.0),
            "standing_surplus_usd": float(
                getattr(self, "_standing_surplus_usd", 0.0) or 0.0
            ),
            "fold_cycle_cap_consumed": float(
                getattr(self, "_fold_cycle_cap_consumed", 0.0) or 0.0
            ),
            "cycle_growth_budget_usd": round(
                float(getattr(self, "_anchor_target_balance", 0.0) or 0.0)
                * float(getattr(self.config, "max_target_growth_pct", 0.0) or 0.0)
                / 100.0,
                8,
            ),
            # How much queued tranche capital the per-cycle filter can
            # never admit, because a tranche is only taken if it fits
            # ENTIRELY. Counted here rather than in the GUI so the
            # arithmetic lives beside the fields it reads.
            **_over_cap_summary,
            "ta_timeframe": getattr(self.config, "ta_timeframe", "1h") or "1h",
            # MEM-248: expose current_holdings so the GUI Ammo column can
            # compute position_value = holdings × price even when the tick
            # loop hasn't yet populated stats.position_value. Without this,
            # idle / freshly-restored bots that actually hold positions
            # rendered as "$0.00 at center line" — dangerously hiding real
            # exposure (operator caught this on an XRP bot that had 104.8
            # XRP ≈ $149.85 but showed Ammo $0.0000).
            "current_holdings": float(getattr(self, "_current_holdings", 0.0)),
            # v3.15.55 — quote→USD multiplier so the GUI can render
            # USD-correct Ammo/position even on crypto-quoted pairs
            # (BTC/ETH, anything/BTC). 1.0 for USD-quoted pairs (no-op).
            "quote_to_usd": float(getattr(self, "_quote_to_usd", 1.0) or 1.0),
            "stats": {
                # v3.23.24 — prefer exchange_trade_count (from
                # get_my_trades / compute_position_health, refreshed
                # every 5min) when a refresh has landed. Falls back to
                # the internal counter for the first ~5min after bot
                # start, and for exchanges without get_my_trades.
                # Directive: position-health values belong to the
                # exchange, not internal accumulators.
                "total_trades": (
                    int(getattr(self.stats, "exchange_trade_count", 0) or 0)
                    if float(getattr(self.stats, "exchange_data_fresh_ts", 0.0) or 0.0)
                    > 0
                    else self.stats.total_trades
                ),
                "trade_volume": round(self.stats.trade_volume, 2),
                "realised_pnl": round(self.stats.realised_pnl, 4),
                "unrealised_pnl": round(self.stats.unrealised_pnl, 4),
                "active_buys": self.stats.active_buy_orders,
                "active_sells": self.stats.active_sell_orders,
                "current_price": self.stats.current_price,
                "position_value": round(getattr(self.stats, "position_value", 0.0), 4),
                "extended_positions": self.stats.extended_positions_created,
                # v3.16.5 — live uptime computation. Operator-reported
                # 2026-04-28: dashboard Uptime field never incremented
                # despite bots running normally. Root cause: stats.uptime_seconds
                # was only updated in stop() and the tick-loop finally
                # block — while the bot was RUNNING, it stayed at the
                # dataclass default (0.0). Compute the live elapsed time
                # here so the dashboard always sees the current value.
                "uptime": round(
                    (
                        (time.monotonic() - self._start_time)
                        if (
                            self._start_time
                            and self.state in (BotState.RUNNING, BotState.STARTING)
                        )
                        else self.stats.uptime_seconds
                    ),
                    1,
                ),
                "last_error": self.stats.last_error,
                # v3.24.40 (C54 / NF-83) — THIS BOT'S OWN accumulators.
                # Consumers read these per row; the producer never
                # emitted them, so anything reading them off a status
                # dict got nothing. They must come from self.stats, NOT
                # from BotManager.get_aggregate_stats: that is a
                # fleet-wide sum, and sourcing a per-bot key from it
                # would make every row show the fleet total.
                "total_scrummed_usd": round(
                    getattr(self.stats, "total_scrummed_usd", 0.0), 4
                ),
                "total_folded_usd": round(
                    getattr(self.stats, "total_folded_usd", 0.0), 4
                ),
                "ytd_scrummed_usd": round(
                    getattr(self.stats, "ytd_scrummed_usd", 0.0), 4
                ),
                "ytd_folded_usd": round(getattr(self.stats, "ytd_folded_usd", 0.0), 4),
            },
            # v3.24.40 (C54) — this bot's contribution to portfolio
            # value, at the TOP level because check_live_monitor reads
            # it off the status root. There is no separate
            # portfolio_value field on BotStats; a single bot's
            # portfolio contribution IS its position value.
            "portfolio_value": round(
                getattr(self.stats, "position_value", 0.0) or 0.0, 4
            ),
            # v3.16.16 — auto-fire eligibility snapshot from last tick.
            # GUI fire button reads this to render solid (auto would
            # fire) vs outline (manual override only) and tooltip the
            # specific blocking gate(s). Falls back to defaults for
            # bot subclasses that don't maintain _last_gate_state.
            "auto_fire": dict(
                getattr(
                    self,
                    "_last_gate_state",
                    {
                        "scrum_armed": False,
                        "fold_armed": False,
                        "scrum_blockers": ["pre-tick"],
                        "fold_blockers": ["pre-tick"],
                        "evaluated_at_tick": 0,
                    },
                )
            ),
        }

    def get_full_state(self) -> dict:
        """Export complete bot state for persistence. Includes config, stats,
        grid levels, and all data needed to restore without re-executing trades."""
        from dataclasses import asdict

        state = {
            "bot_id": self.bot_id,
            "state_when_saved": self.state.value,
            "config": asdict(self.config),
            "stats": asdict(self.stats),
            "saved_at": time.time(),
        }
        # Config mode is an enum — convert to string
        state["config"]["mode"] = self.config.mode.value

        # v3.20.4 — grid_levels save block removed (grid_bot deleted
        # v3.16.0). No live ScrummingBot/ExtractorBot has a `grid`
        # attribute; the legacy block was dead code.

        # Scrumming bot: save phantom config
        if hasattr(self, "_phantom_config"):
            state["phantom_config"] = self._phantom_config

        # v3.16.27 P0g — save the phantom enabled flag so operator's
        # explicit OFF state survives shutdown. Operator-reported
        # 2026-05-05: "On bot restart, phantom bots are activating
        # despite being turned off prior to shut down." Root cause was
        # that this flag was never persisted — restore always fell
        # back to ScrummingBot.__init__'s default `enable_phantoms=True`.
        if hasattr(self, "_phantoms_enabled"):
            state["phantoms_enabled"] = bool(self._phantoms_enabled)

        # MEM-245 — Scrumming bot compounding state (main_lots,
        # fold_tranches, accumulation state). Without this, every
        # restart reseeds main_lots at current price and starts with
        # zero tranches, resetting the compounding mechanism.
        #
        # The exporter belongs to ScrummingBot, not to this shared
        # parent, so it is fetched by name with a default rather than
        # read straight off self. Same guard as before, same skip when
        # the bot has no exporter, and the same warning if the exporter
        # itself misbehaves — but now there is no window in which the
        # attribute can vanish between the check and the call. This
        # matches how the auto-fire snapshot above reads
        # _last_gate_state.
        _export_scrumming = getattr(self, "export_scrumming_state", None)
        if _export_scrumming is not None:
            try:
                state["scrumming_state"] = _export_scrumming()
            except Exception as exc:
                logger.warning(
                    "export_scrumming_state failed on %s: %s", self.bot_id, exc
                )

        # v3.20.4 — Extractor runtime state (positions, chunk, hedge,
        # watch list, tick counter). Without this, every restart of a
        # persisted Extractor would lose all open positions + the
        # chunk/hedge balances would reset to construction defaults.
        # Symmetric to scrumming_state above; gated on the bot's mode
        # so we only emit the key for actual Extractors (avoids inflating
        # state files for ScrummingBots that happen to inherit
        # export_state from a future refactor).
        # sadp: R28 FL  R49 MDEL  R55 GOV  R68 DPA
        #
        # Fetched by name with a default, for the same reason as the
        # scrumming exporter above: this exporter belongs to
        # ExtractorBot, not to this shared parent. The mode check is
        # kept and still comes first.
        _export_extractor = getattr(self, "export_state", None)
        if self.config.mode == BotMode.EXTRACTOR and _export_extractor is not None:
            try:
                state["extractor_state"] = _export_extractor()
            except Exception as exc:
                logger.warning(
                    "export_state (extractor) failed on %s: %s", self.bot_id, exc
                )

        return state


# ---------------------------------------------------------------------------
# Bot manager — oversees all containers
# ---------------------------------------------------------------------------
class BotManager:
    """
    Central registry for all bot containers.  Provides:
      - Create / start / stop / restart individual bots
      - Aggregate stats for the main window dashboard
      - Bulk operations (stop all, pause all)
      - State persistence (save/restore between sessions)
    """

    def __init__(self, bus=None) -> None:
        """v3.24.61 (C17 / SWARM-4.23) — `bus` is injectable.

        This constructor subscribes three handlers below, INSIDE
        `__init__`. A caller that rebinds `._bus` afterwards — which is
        exactly what `nuclear_controller.py:262` does, one line after
        constructing at :261 — is already too late: the subscriptions
        are latched on the process-wide bus and, until C17, could never
        be retracted.

        The leaked handlers are bound methods of an abandoned SIM
        manager, so they went on firing on LIVE events for the life of
        the process, three more per replay.

        Defaults to the process-wide bus, so every live construction
        site is unchanged.
        """
        self._bots: dict[str, BotContainer] = {}
        # Retained so the subscriptions can be taken off again. Every
        # caller of `subscribe` in src/ discarded these closures, which
        # is what made the leak unfixable from outside.
        self._bus_unsubs: list = []
        # v3.24.35 (C01 PR-0) — restore observation registries.
        #
        # save_state rebuilds "bots" solely from the registered set, so
        # a bot's absence from self._bots currently means BOTH "the
        # operator deleted it" and "restore could not load it" — and the
        # 60s save timer resolves that ambiguity by deleting the record
        # either way. Absence is not evidence.
        #
        # _restore_ledger is written ONLY by code that OBSERVED a bot
        # fail to load, so it can distinguish the two. PR-0 records and
        # reports; PR-1 uses it to decide what a save must carry.
        self._restore_ledger: dict[str, str] = {}  # bot_id -> reason
        self._boot_state_records: dict = {}  # bot_id -> record
        self._restore_completed: bool = False
        # C17 — resolved HERE, ~40 lines ahead of the three subscribes
        # below, so an injected bus is the one they land on.
        self._bus = bus if bus is not None else get_event_bus()
        self._state_manager = None
        self._volume_guard = None  # Shared VolumeGuard for all bots
        self._data_pool = None  # Shared MarketDataPool for API efficiency
        self._ticker_refresh_task = None  # Bulk ticker refresher handle
        self._ticker_refresh_stop = False
        self._live_monitor = None  # AI feedback loop (LiveMonitor)
        self._connector = None  # CcxtConnector — set via set_connector()
        # v3.20.71 Phase B-2 — CapitalRegistry broker integration.
        # Wired by main.py via set_capital_registry() AFTER settings.json
        # is loaded so initial_reservations can rehydrate from disk. When
        # None (e.g. in tests that don't construct the registry), register()
        # skips the reservation gate — keeps legacy test paths working.
        # Operator-locked Q3: register() returns (False, reason) on
        # over-allocation; the wizard surfaces the reason to the user
        # and does NOT add the bot. MEM-417.
        self._capital_registry = None
        # v3.16.19 — persistent asyncio loop reference. Set by
        # main.py via set_async_loop(). Used to route
        # bootstrap_exchange_state() onto the SAME loop that
        # bot.tick() runs on, so any asyncio.Lock instances
        # acquired during bootstrap (e.g., the v3.16.17 data_pool
        # ticker-coalescing locks) bind to the right loop and
        # don't poison the cache when the throwaway thread
        # finishes. Operator-reported runtime bug 2026-05-01:
        # "RuntimeError: <Lock object [unlocked, waiter ...]>"
        # on BONK after creating a 15th bot (TAO) — root cause
        # was the previous asyncio.run() spawn creating a
        # throwaway loop that bound the per-symbol lock, then
        # closing and leaving the lock pointing at a dead loop.
        self._async_loop = None
        # Session 26 P1b (2026-04-24) — Smart Wire singleton shared across
        # all bots. Operator spec: "Smart Wire feeds passively increase
        # Fold Queue of target bots ... distributed evenly across existing
        # tranches OR wait for a new tranche to form." Registration of
        # wires happens via the Bot Swarm GUI; actual fold-profit routing
        # fires from each source bot's fold success path.
        from .smart_wire import SmartWireManager

        # C17 — the wire manager emits bot.log on two paths and resolved
        # get_event_bus() lazily, so a SIM manager's wire activity
        # reached the LIVE bus even after this manager was isolated.
        self._smart_wire_mgr = SmartWireManager(bus=self._bus)
        # Subscribe to cross-bot profit routing events.
        # C17 — the closures are RETAINED now. Discarding them is what
        # left three handlers per sim replay permanently attached to the
        # process-wide bus.
        self._bus_unsubs.append(
            self._bus.subscribe("profit.cross_bot", self._on_cross_bot_profit)
        )
        # P1b — GUI wire drag events land on the manager + register/
        # unregister with the SmartWireManager so the fold path can see
        # them. Source-side routing fires per fold inside ScrummingBot.
        self._bus_unsubs.append(
            self._bus.subscribe("wire.created", self._on_wire_created_mgr)
        )
        self._bus_unsubs.append(
            self._bus.subscribe("wire.removed", self._on_wire_removed_mgr)
        )

    def detach_bus(self) -> int:
        """Retract every subscription this manager made.

        v3.24.61 (C17). Call in sim teardown. Returns the number of
        subscriptions removed, so a caller (or the exit gate) can assert
        the bus is back where it started.

        Never raises: teardown paths must complete. Idempotent — the
        retained list is cleared, so a second call is a no-op rather
        than a double-removal.
        """
        removed = 0
        for _off in list(self._bus_unsubs):
            try:
                _off()
                removed += 1
            except Exception as exc:  # R28-OK: teardown must finish
                logger.debug("bus detach skipped one handler: %s", exc)
        self._bus_unsubs = []
        return removed

    @property
    def smart_wire_manager(self):
        """Expose the SmartWireManager singleton (used by GUI to
        register/unregister wires drawn in the Bot Swarm tab)."""
        return self._smart_wire_mgr

    def _on_wire_created_mgr(self, event) -> None:
        """GUI wire drag → register with SmartWireManager so fold
        profits actually route. Session 26 P1b.

        v3.24.37 (C06c) — the result was discarded. register_wire
        refuses a wire whose pct is non-numeric, <= 0, > 100, or whose
        endpoints are equal, and every one of those refusals was
        dropped here: the GUI had already drawn the wire and the event
        had already fired, so the canvas showed a routing the engine
        never accepted and no fold profit would ever follow. An
        overwrite of an existing pct was equally invisible.
        """
        try:
            src = event.data.get("source_id", "")
            tgt = event.data.get("target_id", "")
            pct = event.data.get("pct", 0)
            if src and tgt:
                res = self._smart_wire_mgr.register_wire(src, tgt, pct) or {}
                if not res.get("applied"):
                    logger.warning(
                        "BotManager wire.created: engine REFUSED %s -> %s "
                        "@ %r (%s); anything drawing this wire is showing "
                        "a routing that will never carry profit",
                        src,
                        tgt,
                        pct,
                        res.get("reason", "no reason given"),
                    )
                elif res.get("replaced_pct") is not None:
                    logger.warning(
                        "BotManager wire.created: %s -> %s OVERWROTE an "
                        "existing %.2f%% with %.2f%%",
                        src,
                        tgt,
                        res["replaced_pct"],
                        res.get("pct", 0.0),
                    )
        except Exception as exc:
            logger.warning("BotManager wire.created handler raised: %s", exc)

    def _on_wire_removed_mgr(self, event) -> None:
        """GUI wire disconnect → unregister."""
        try:
            src = event.data.get("source_id", "")
            tgt = event.data.get("target_id", "")
            if src and tgt:
                self._smart_wire_mgr.unregister_wire(src, tgt)
        except Exception as exc:
            logger.warning("BotManager wire.removed handler raised: %s", exc)

    def _on_cross_bot_profit(self, event) -> None:
        """Handle cross-bot profit transfer.

        MEM-249 (Session 26 operator directive, enforces MEM-246 Phase B absolutely):
        Target Balance is a HARD CODED set-point. The ONLY legitimate mechanism
        that may grow it is fold-surplus bounded by max_target_growth_pct per
        event. Cross-bot profit wire is NOT that mechanism — it is a separate
        profit-routing feature that was previously pumping BOTH _target_balance
        AND config.target_balance unclamped, which is exactly the path the
        operator caught on 2026-04-23: "Target Balance increasing in this
        manner does not happen anymore!? It BREAKS the system."

        Fix: cross-bot profit routes to the recipient's `realised_pnl` stat.
        Operator still sees the profit in the P/L column; Target stays frozen
        at its set-point (subject only to the fold-surplus clamp). Target
        Balance is NOW safe against every mutation path we control.
        """
        target_id = event.data.get("target_bot_id", "")
        amount = event.data.get("amount", 0)
        source_id = event.data.get("source_bot_id", "")
        target_bot = self._bots.get(target_id)
        if target_bot and amount > 0:
            # Route to realised_pnl — NOT to target_balance. Target stays frozen.
            # sadp: R1 R28 — fold-only target growth; fail loudly if anyone else tries.
            if hasattr(target_bot, "stats") and hasattr(
                target_bot.stats, "realised_pnl"
            ):
                target_bot.stats.realised_pnl += float(amount)
            self._bus.emit(
                "bot.log",
                bot_id=target_id,
                message=(
                    f"CROSS-BOT RECEIVED: +${amount:.4f} from "
                    f"{source_id[:8]} booked to realised_pnl "
                    f"(Target frozen at ${target_bot.config.target_balance:.2f} — "
                    f"MEM-249 cross-wire no longer touches Target)."
                ),
            )
        elif not target_bot:
            self._bus.emit(
                "bot.log",
                bot_id=source_id,
                message=f"CROSS-BOT FAILED: target bot {target_id[:8]} not found",
            )

    def set_state_manager(self, sm) -> None:
        """Attach a StateManager for persistence."""
        self._state_manager = sm

    def force_fire(self, bot_id: str, aggressive: bool = False) -> bool:
        """MEM-236 + MEM-241 — Manual Fire from the dashboard.

        Looks up the bot by id and calls its force_fire() method. Safe
        on unknown bot_id (returns False) and on grid bots (base class
        force_fire is a no-op). Returns True when the call reached a
        scrumming bot instance.

        Called synchronously from the GUI thread — must not await or
        block. The bot's force_fire only mutates a counter/flag that
        the async tick loop picks up on next iteration.

        Args:
            aggressive: MEM-241. When True (GUI default), scrumming
                bots execute a one-shot market-order rebalance-to-target
                on the next tick, bypassing gate checks. When False,
                legacy MEM-236 flush-tick-skip behavior.
        """
        bot = self._bots.get(bot_id)
        if bot is None:
            return False
        try:
            # Forward-compat: older ScrummingBot builds may not accept
            # the aggressive kwarg. Try the new signature first; fall
            # back if TypeError on unexpected keyword.
            try:
                bot.force_fire(aggressive=aggressive)
            except TypeError:
                bot.force_fire()
            return hasattr(bot, "scrum_target_mode")
        except Exception as exc:
            logger.warning("force_fire failed on %s: %s", bot_id, exc)
            return False

    def set_volume_guard(self, guard) -> None:
        """Attach a VolumeGuard for market-safe trade execution."""
        self._volume_guard = guard
        for bot in self._bots.values():
            bot._volume_guard = guard
        logger.info(
            "VolumeGuard attached to BotManager (%d existing bots)", len(self._bots)
        )

    def set_data_pool(self, pool) -> None:
        """Attach shared MarketDataPool for efficient API usage."""
        self._data_pool = pool
        for bot in self._bots.values():
            bot._data_pool = pool
        logger.info(
            "DataPool attached to BotManager (%d existing bots)", len(self._bots)
        )

    # ── Bulk ticker refresh (operator item 1, 2026-08-06) ───────────

    def _connectors_by_exchange(self) -> dict:
        """One live connector per distinct exchange_id across the fleet.

        The bulk fetch is per-exchange, so 35 bots on one exchange need
        exactly one connector — not one per bot.
        """
        out: dict = {}
        for bot_id, bot in self._bots.items():
            try:
                exch_id = getattr(bot.config, "exchange_id", None)
                conn = getattr(bot, "exchange", None)
            except Exception as exc:
                # One malformed container must not blind the refresher
                # for the whole fleet, but a silent skip here would hide
                # a bot that never gets fresh prices.
                logger.warning(
                    "Ticker refresh: cannot read exchange handle for %s "
                    "(%s); that bot keeps its own fetch path.",
                    bot_id,
                    exc,
                )
                continue
            if exch_id and conn is not None and exch_id not in out:
                out[exch_id] = conn
        return out

    async def refresh_all_tickers_once(self) -> int:
        """One bulk ticker refresh across every exchange in the fleet.

        Separated from the loop so it is testable without a scheduler
        and callable on demand (e.g. immediately after a manual fire).
        """
        pool = getattr(self, "_data_pool", None)
        if pool is None or not hasattr(pool, "refresh_all_tickers"):
            return 0
        total = 0
        for exch_id, conn in self._connectors_by_exchange().items():
            try:
                total += await pool.refresh_all_tickers(conn, exch_id)
            except (
                Exception
            ) as exc:  # R28-OK: refresher is best-effort; bots keep their own fetch path
                logger.warning("Bulk ticker refresh raised for %s: %s", exch_id, exc)
        return total

    async def _ticker_refresh_loop(self, interval: float) -> None:
        """Warm the shared ticker cache on a display-grade cadence.

        WHY: a bot fetching its own ticker on its own gated schedule
        spends 35 calls to cover ground one bulk call covers. Measured
        2026-08-06: 10,272 ticker fetches/hour across the fleet, which
        this reduces to ~720 at the 5s default.

        This does NOT change any bot's decision cadence. Bots still act
        on their own gated schedule; that schedule now sees a fresher
        price. It REPLACES traffic rather than adding it: a warmed entry
        takes the fast path in `get_or_fetch_ticker`, so the bot does
        not issue its own request.

        CORRECTED 2026-08-07 -- what this does NOT do
        This was originally shipped believing it also unstuck the stale
        Ammo readout. It does not. The dashboard reads
        `stats.current_price` (`main_window.py:1621`), whose only
        recurring writer is `scrumming_bot.py:5136`, downstream of the
        read-rate gate. Nothing here writes that field. Display
        freshness is fixed separately, by having the display consult the
        pool cache this loop keeps warm.
        """
        logger.info("Bulk ticker refresher started (every %.1fs)", interval)
        while not self._ticker_refresh_stop:
            try:
                await asyncio.sleep(interval)
                if self._ticker_refresh_stop:
                    break
                await self.refresh_all_tickers_once()
            except asyncio.CancelledError:
                raise
            except (
                Exception
            ) as exc:  # R28-OK: the loop must survive any single failed cycle
                logger.warning("Ticker refresh cycle failed: %s", exc)
        logger.info("Bulk ticker refresher stopped.")

    def start_ticker_refresher(self, interval: float = 5.0) -> bool:
        """Launch the refresher on the manager's loop. Idempotent."""
        if getattr(self, "_ticker_refresh_task", None) is not None:
            return False
        loop = getattr(self, "_async_loop", None)
        if loop is None:
            logger.warning("Bulk ticker refresher not started: no async loop attached.")
            return False
        self._ticker_refresh_stop = False
        self._ticker_refresh_task = asyncio.run_coroutine_threadsafe(
            self._ticker_refresh_loop(interval), loop
        )
        return True

    def stop_ticker_refresher(self) -> None:
        task = getattr(self, "_ticker_refresh_task", None)
        self._ticker_refresh_stop = True
        if task is not None:
            task.cancel()
            self._ticker_refresh_task = None

    def set_async_loop(self, loop) -> None:
        """v3.16.19 — Attach the persistent asyncio loop.

        Required so ``bootstrap_exchange_state`` (and any future
        BotManager-side coroutine launches) can run on the SAME
        loop as ``bot.tick()`` instead of spawning a throwaway
        loop in a new thread via ``asyncio.run()``. The throwaway
        pattern was poisoning v3.16.17's per-symbol asyncio.Lock
        instances, leaving them bound to a loop that would soon
        close. Operator-reported 2026-05-01 — see CHANGELOG
        v3.16.19 for the full root-cause writeup.
        """
        self._async_loop = loop
        logger.info(
            "AsyncLoop attached to BotManager (id=%s)",
            id(loop) if loop is not None else "None",
        )

    def _dispatch_bootstrap(self, bot, source: str) -> None:
        """v3.16.19 — Run ``bot.bootstrap_exchange_state()`` on the
        persistent asyncio loop when wired, otherwise fall back to
        the legacy throwaway-thread pattern.

        Persistent-loop path (production): use
        ``asyncio.run_coroutine_threadsafe(coro, self._async_loop)``.
        The coroutine runs on the SAME loop that ``bot.tick()`` will
        run on, so any asyncio.Lock created during bootstrap (e.g.,
        the v3.16.17 ticker-coalescing locks in MarketDataPool)
        binds to the right loop and stays valid for tick-time
        access. The future is fire-and-forget — exceptions are
        logged via add_done_callback rather than blocking the
        caller.

        Throwaway-loop path (tests / no-loop fallback): the legacy
        ``asyncio.run()`` in a daemon thread. Only safe in
        environments where the bot will not later use shared
        asyncio primitives on a different loop (i.e., tests that
        construct bots in isolation).

        Parameters
        ----------
        source : str
            Origin label for log messages ("set_connector" |
            "register" | future). Helps the operator distinguish
            which dispatch path failed when warnings appear.
        """
        coro = bot.bootstrap_exchange_state()
        loop = self._async_loop
        if loop is not None and not loop.is_closed():
            try:
                fut = asyncio.run_coroutine_threadsafe(coro, loop)

                def _on_done(_fut, _bid=bot.bot_id, _src=source):
                    try:
                        _exc = _fut.exception()
                    except (
                        Exception
                    ) as _probe_exc:  # R28-OK: future-state probe; defensive against future cancellation surfacing as a non-Exception
                        logger.debug(
                            "Bot %s bootstrap (%s) future probe raised %s",
                            _bid,
                            _src,
                            _probe_exc,
                        )
                        return
                    if _exc is not None:
                        logger.warning(
                            "Bot %s bootstrap dispatch (%s) raised: %s",
                            _bid,
                            _src,
                            _exc,
                        )

                fut.add_done_callback(_on_done)
            except Exception as exc:
                logger.warning(
                    "Bot %s bootstrap scheduling (%s) failed: %s",
                    bot.bot_id,
                    source,
                    exc,
                )
            return
        # Fallback: no persistent loop wired (test harness path).
        # Close the coroutine first if we can't dispatch — leaving
        # an unawaited coroutine raises a RuntimeWarning.
        try:
            coro.close()
        except Exception as _close_exc:
            # The comment here used to say this was logged. It was not.
            # Nothing was written anywhere, so a failure to tidy up the
            # unused start-up job left no trace at all. It is written
            # now. The failure is still not treated as fatal, because
            # a fresh job is started on the next lines either way; the
            # only cost of a failed tidy-up is a warning from Python
            # about a job nobody waited for.
            logger.debug(
                "Bot %s could not close the unused start-up job from "
                "%s (%s). Carrying on to start a fresh one.",
                bot.bot_id,
                source,
                _close_exc,
            )
        try:
            import threading
            import asyncio as _aio

            def _boot(_b=bot, _src=source):
                try:
                    _aio.run(_b.bootstrap_exchange_state())
                except Exception as _exc:
                    logger.warning(
                        "Bot %s bootstrap dispatch (%s, fallback) failed: %s",
                        _b.bot_id,
                        _src,
                        _exc,
                    )

            threading.Thread(
                target=_boot,
                daemon=True,
                name=f"bot-bootstrap-{source[:6]}-{bot.bot_id[:8]}",
            ).start()
        except Exception as exc:
            logger.warning(
                "Bot %s bootstrap scheduling (%s, fallback) failed: %s",
                bot.bot_id,
                source,
                exc,
            )

    def set_live_monitor(self, monitor) -> None:
        """Attach LiveMonitor for AI feedback loop."""
        self._live_monitor = monitor
        logger.info(
            "LiveMonitor attached to BotManager (enabled=%s)",
            monitor.enabled if monitor else False,
        )

    def configure_live_monitor(self, settings: dict) -> None:
        """Create or reconfigure LiveMonitor from settings dict.

        Called when settings are saved. Keys:
          api_key, interval_hours, connect_phrase, confirm_phrase, enabled
        """
        if not settings.get("enabled") or not settings.get("api_key"):
            self._live_monitor = None
            logger.info("LiveMonitor disabled")
            return
        from .live_monitor import LiveMonitor, TradeJournal

        journal = TradeJournal()
        self._live_monitor = LiveMonitor(
            api_key=settings["api_key"],
            journal=journal,
            interval_hours=settings.get("interval_hours", 4.0),
            connect_phrase=settings.get("connect_phrase", ""),
            confirm_phrase=settings.get("confirm_phrase", ""),
        )
        logger.info(
            "LiveMonitor configured (interval=%.1fh, phrase='%s')",
            settings.get("interval_hours", 4.0),
            settings.get("connect_phrase", "")[:20],
        )

    async def check_live_monitor(self) -> dict | None:
        """Run AI feedback check if due. Returns feedback dict or None."""
        if not self._live_monitor or not self._live_monitor.enabled:
            return None
        if not self._live_monitor.should_check:
            return None
        # Aggregate portfolio stats from all bots.
        #
        # v3.24.40 (C54) — get_status() emitted NEITHER key, so both
        # .get(..., 0) calls returned 0 for every bot on every check.
        # The monitor was handed "Portfolio: $0.00 | Passive: $0.00"
        # every time, sent that to the model, and surfaced the reply on
        # the bus as ai.feedback — advice about a portfolio it had been
        # told was empty. The default argument made it silent.
        #
        # portfolio_value is now emitted per bot. passive_value has no
        # source anywhere in src/ (declared nowhere, written nowhere),
        # so it is reported as UNAVAILABLE rather than as $0.00. A
        # buy-and-hold baseline needs each position's entry basis; that
        # is a real computation, not a default, and inventing a zero
        # for it is what made this wrong in the first place.
        total_port = 0.0
        contributing = 0
        for bot in self._bots.values():
            try:
                s = bot.get_status()
            except Exception as exc:  # R28-OK: lifecycle/state best-effort
                logger.warning(
                    "live monitor: get_status failed for a bot (%s); it "
                    "is excluded from the portfolio total",
                    exc,
                )
                continue
            if "portfolio_value" in s:
                total_port += float(s.get("portfolio_value") or 0.0)
                contributing += 1
        if contributing < len(self._bots):
            logger.warning(
                "live monitor: only %d of %d bots reported a portfolio "
                "value; the figure sent for analysis is PARTIAL",
                contributing,
                len(self._bots),
            )
        result = await self._live_monitor.analyze(
            portfolio=total_port, passive=None, bots=len(self._bots)
        )
        if result.get("feedback"):
            self._bus.emit("ai.feedback", data=result)
            logger.info("AI feedback received: %s", result.get("feedback", "")[:80])
        return result

    @property
    def live_monitor_info(self) -> dict:
        """Return current LiveMonitor connection status."""
        if not self._live_monitor:
            return {"enabled": False, "authenticated": False, "checks": 0}
        return self._live_monitor.connection_info

    def set_connector(self, connector) -> None:
        """
        Attach the CcxtConnector so BotManager can register bot symbols
        for post-connect trade history scanning.

        MEM-255: ALSO fires a one-shot live-pull of exchange state for every
        registered bot that supports `bootstrap_exchange_state`. Without
        this, idle bots (not yet started) show holdings=0 in the GUI
        because the tick-time MEM-226 handshake never runs. Operator
        directive: "if it displays exchange data, it should plug in
        immediately to the first verified API."
        """
        self._connector = connector
        # Register any already-running bots' symbols immediately
        for bot in self._bots.values():
            connector.add_scan_symbol(bot.config.symbol)
            # Attach the connector as the bot's exchange so bootstrap +
            # subsequent tick-time handshake see a real exchange. (Some
            # callers already set bot.exchange at construction; this is
            # idempotent when they match.)
            if not getattr(bot, "exchange", None) or bot.exchange is None:
                try:
                    bot.exchange = connector
                except Exception as _attach_exc:
                    # A bot may be a frozen record that refuses any
                    # attribute write, so this must not stop the loop
                    # or reach the caller. It DOES have to be said out
                    # loud: the bot now holds no connector, later reads
                    # fall back to a default, and a bot with no
                    # connector cannot trade. Silence here is what made
                    # that state invisible.
                    logger.error(
                        "Bot %s would not accept the exchange connector "
                        "(%s). It has no connector and cannot trade "
                        "until one is attached.",
                        getattr(bot, "bot_id", "<unknown bot>"),
                        _attach_exc,
                    )
            # Fire the one-shot live-pull on the persistent asyncio
            # loop when available (v3.16.19 fix for cross-loop Lock
            # poisoning). Falls back to the legacy throwaway-thread
            # `asyncio.run` path only when no loop is wired — that
            # branch is only used in test harnesses that don't
            # attach a persistent loop.
            if hasattr(bot, "bootstrap_exchange_state"):
                self._dispatch_bootstrap(bot, "set_connector")
        logger.info(
            "Connector attached to BotManager — "
            "%d symbol(s) registered for history scanning + bootstrap",
            len(self._bots),
        )

    # ------------------------------------------------------------------
    # v3.20.71 Phase B-2 — CapitalRegistry broker integration
    # ------------------------------------------------------------------
    def set_capital_registry(self, registry) -> None:
        """Wire in a CapitalRegistry broker instance. After this is set,
        register() consults it as a reservation gate (Q3 refuse-outright)
        and unregister() releases the reservation. main.py wires this in
        AFTER settings.json is loaded so initial_reservations can
        rehydrate from disk per Q4."""
        self._capital_registry = registry

    @property
    def capital_registry(self):
        """Expose the broker for tests + Phase D's GUI registry table."""
        return self._capital_registry

    def reconcile_capital_registry(
        self,
        *,
        exchange_id: str,
        base_currency: str,
        drift_threshold_pct: float = 5.0,
    ) -> "Optional[dict]":
        """v3.20.73 Phase D — periodic reconciliation of one
        (exchange, base) pool against the live exchange balance.
        Locked Q1: 5-minute cadence (callers schedule the call;
        this method is the single-shot reconcile step).

        Mechanism:
        - Fetch live exchange balance via the wired connector
        - Convert to USD using a best-effort rate from the connector ticker
        - Call ``registry.reconcile_with_exchange(...)`` which
          returns ``{wallet_base, wallet_usd, reserved_usd, reserved_base,
          free_usd, free_base, drift_usd, drift_pct}``
        - If ``drift_pct > drift_threshold_pct`` (default 5%), emit
          ``capital.drift_alert`` event with the full report for the
          operator notification panel
        - Refresh the registry's snapshot rate (so reserved_base on
          each reservation tracks the current rate)

        Returns the drift report dict, or None if the registry isn't
        wired or the connector can't fetch a balance. Never raises.

        MEM-419.
        """
        if self._capital_registry is None:
            return None
        try:
            # Fetch wallet balance via the connector's sync interface
            if not self._connector or not hasattr(self._connector, "_ccxt_sync"):
                return None
            balances = self._connector._ccxt_sync.fetch_balance()
            free = balances.get("free", {}) if isinstance(balances, dict) else {}
            wallet_base = float(free.get(base_currency, 0) or 0)
            # Rate lookup (USD-like = 1.0)
            rate = self._usd_per_base_for(exchange_id, base_currency)
            if rate is None:
                # Comparing the wallet against the saved claims needs a
                # real price. Without one this used to carry on with a
                # made-up $1.00, which rewrote every saved claim in the
                # pool through reconcile_with_exchange and raised a
                # false drift alarm. No price means no comparison.
                logger.warning(
                    "Skipped the %s/%s capital check: no %s price is "
                    "available. The saved claims are left exactly as "
                    "they are.",
                    exchange_id,
                    base_currency,
                    base_currency,
                )
                return None
            # Reconcile
            report = self._capital_registry.reconcile_with_exchange(
                exchange_id=exchange_id,
                base_currency=base_currency,
                exchange_balance_base=wallet_base,
                current_rate_usd_per_base=rate,
            )
            # Drift alert
            drift_pct = float(report.get("drift_pct", 0.0) or 0.0)
            if abs(drift_pct) > drift_threshold_pct:
                self._bus.emit(
                    "capital.drift_alert",
                    exchange_id=exchange_id,
                    base_currency=base_currency,
                    drift_pct=drift_pct,
                    report=report,
                )
                logger.warning(
                    "v3.20.73 capital drift on %s/%s: %.2f%% "
                    "(wallet $%.2f vs reserved $%.2f)",
                    exchange_id,
                    base_currency,
                    drift_pct,
                    report.get("wallet_usd", 0.0),
                    report.get("reserved_usd", 0.0),
                )
            return report
        except (
            Exception
        ) as _exc:  # R28-OK: reconcile best-effort; never block bot lifecycle
            logger.warning(
                "v3.20.73 reconcile_capital_registry failed " "for %s/%s: %s",
                exchange_id,
                base_currency,
                _exc,
            )
            return None

    def reconcile_all_capital(
        self,
        *,
        drift_threshold_pct: float = 5.0,
    ) -> list[dict]:
        """v3.20.73 Phase D — reconcile every (exchange, base) tuple
        that has at least one active reservation. Returns the list of
        drift reports (one per pool). Empty list if no registry / no
        reservations. The 5-min cadence callers (Phase D background
        task / GUI manual-refresh) invoke this single method to
        reconcile all pools in one pass."""
        if self._capital_registry is None:
            return []
        reservations = self._capital_registry.get_reservations()
        # Distinct (exchange, base) tuples to reconcile
        pools: set[tuple[str, str]] = set()
        for r in reservations:
            pools.add((r.exchange_id, r.base_currency))
        reports: list[dict] = []
        for exch, base in sorted(pools):
            rep = self.reconcile_capital_registry(
                exchange_id=exch,
                base_currency=base,
                drift_threshold_pct=drift_threshold_pct,
            )
            if rep is not None:
                rep["exchange_id"] = exch
                rep["base_currency"] = base
                reports.append(rep)
        return reports

    def notify_bot_profit(
        self,
        *,
        bot_id: str,
        profit_usd: float,
    ) -> tuple[bool, "Optional[str]"]:
        """v3.20.72 Phase C-1 — relay an Extractor profit credit to
        the CapitalRegistry so the bot's reservation grows by the
        profit amount (MEM-418). Closes the cross-bot leak surface:
        without this, sibling bots see the wallet's grown balance as
        unreserved excess and could claim it (fee-stacking cascade).

        Locked Q6 semantics: same-bot-only overshoot. The bot's own
        reservation grows immediately even if the wallet provider
        hasn't observed the profit settlement yet; siblings'
        request_reservation() calls then see the higher total and
        refuse over-allocation against unsettled profit.

        Returns ``(success, reason)``. On failure (no registry wired
        / no existing reservation / non-positive profit), this is a
        no-op — never blocks the trade flow.
        """
        if self._capital_registry is None or profit_usd <= 0:
            return False, None
        try:
            granted, reason, _ = self._capital_registry.grow_reservation(
                bot_id=bot_id, additional_usd=profit_usd
            )
            return granted, reason
        except (
            Exception
        ) as _exc:  # R28-OK: best-effort registry growth; never block trade
            logger.warning(
                "v3.20.72 notify_bot_profit failed for bot %s " "(+$%.2f): %s",
                bot_id,
                profit_usd,
                _exc,
            )
            return False, str(_exc)

    def _reservation_usd_and_mode(self, bot) -> tuple[float, str]:
        """Extract the canonical (usd_amount, bot_mode) tuple from a bot
        config for registry consultation. Scrumming uses target_balance;
        Extractor uses extractor_chunk_size_usd. Mode string is
        lowercase, matching the broker's expected enum."""
        try:
            mode_val = getattr(bot.config, "mode", None)
            mode_str = (
                str(mode_val.value if hasattr(mode_val, "value") else mode_val) or ""
            ).lower()
        except Exception:  # R28-OK: best-effort mode probe; default to scrumming
            mode_str = "scrumming"
        if "extractor" in mode_str:
            usd_amount = float(getattr(bot.config, "extractor_chunk_size_usd", 0) or 0)
            return usd_amount, "extractor"
        usd_amount = float(getattr(bot.config, "target_balance", 0) or 0)
        return usd_amount, "scrumming"

    def _usd_per_base_for(
        self,
        exchange_id: str,
        base_currency: str,
    ) -> "Optional[float]":
        """How many dollars one unit of ``base_currency`` is worth.

        Returns nothing when no honest price can be had: the price
        request failed, the exchange gave back zero or a negative
        number or something that is not a number, or there is no
        exchange connection at all.

        This used to return 1.0 in every one of those cases. That
        priced one Bitcoin at one dollar, silently, on the path that
        decides how much money each bot may claim. Two things were
        measured with that made-up number in place: ``register``
        refused a $2,000 bot on a real half-Bitcoin wallet and dropped
        the bot, blaming a wallet it had valued at fifty cents; and
        ``reconcile_capital_registry`` overwrote a saved claim of
        0.0327 BTC with 2000.0 BTC and saved it to disk.

        There is no correct number to hand back when the price is
        unknown, so it hands back nothing and each caller decides what
        to do about it. Dollar-pegged coins still return 1.0, because
        for those one dollar per unit is the true price, not a
        stand-in.

        ``exchange_id`` is accepted for a future per-exchange price
        source; the lookup is exchange-wide today.
        """
        base = (base_currency or "").upper()
        if base in DOLLAR_PEGGED_CURRENCIES:
            return 1.0
        if not self._connector or not hasattr(self._connector, "_ccxt_sync"):
            logger.warning(
                "No exchange connection, so no %s price for %s. "
                "Returning no rate rather than pretending one %s is "
                "worth one dollar.",
                base,
                exchange_id,
                base,
            )
            return None
        try:
            t = self._connector._ccxt_sync.fetch_ticker(f"{base}/USD")
            rate = float(t.get("last") or t.get("close") or 0)
        except Exception as _rate_exc:
            logger.warning(
                "Could not read the %s/USD price on %s (%s). Returning "
                "no rate rather than pretending one %s is worth one "
                "dollar.",
                base,
                exchange_id,
                _rate_exc,
                base,
            )
            return None
        if rate <= 0:
            logger.warning(
                "The %s/USD price on %s came back as %r, which cannot "
                "be a price. Returning no rate rather than pretending "
                "one %s is worth one dollar.",
                base,
                exchange_id,
                rate,
                base,
            )
            return None
        return rate

    def register(self, bot: BotContainer) -> tuple[bool, "Optional[str]"]:
        """Add a bot to the manager's registry.

        Returns ``(granted, refusal_reason)``. On success, the bot is
        added and ``(True, None)`` is returned. On capital-registry
        refusal (Q3 over-allocation), the bot is NOT added and
        ``(False, reason)`` is returned. Existing callers that ignore
        the return value still work — they just miss the refusal path.

        MEM-256 (Session 26): when the connector is already attached, also
        fire the bootstrap_exchange_state live-pull for this newly
        registered bot. Without this, bots added AFTER set_connector has
        already run (the common case on startup — restore_bots_from_state
        registers bots after the connector is attached) would not get
        their bootstrap dispatch. Idle bots then show 0 holdings in the
        GUI until their first tick.

        MEM-417 (v3.20.71 Phase B-2): if a CapitalRegistry is wired,
        request_reservation is called BEFORE the bot is added. On
        refusal, an event ``bot.register_refused`` is emitted with
        ``bot_id`` and ``reason``; the wizard surfaces the reason to
        the operator.
        """
        # v3.20.71 — CapitalRegistry gate (Q3 refuse-outright)
        if self._capital_registry is not None:
            try:
                usd_amount, mode_str = self._reservation_usd_and_mode(bot)
                if usd_amount > 0:
                    rate = self._usd_per_base_for(
                        bot.config.exchange_id, bot.config.base_currency
                    )
                    if rate is None:
                        # No price means the claim cannot be sized. See
                        # _usd_per_base_for for why nothing is returned.
                        # A price outage must not delete a bot, so the
                        # bot is kept and no claim is written from a
                        # number nobody has. This lands on the same
                        # outcome as the fall-through below, which is
                        # what already happens when the registry cannot
                        # be consulted.
                        logger.warning(
                            "Bot %s was added WITHOUT a capital "
                            "reservation: no %s price is available, so "
                            "how much %s its $%.2f allocation comes to "
                            "cannot be worked out. Its money is not "
                            "held aside, so another bot may claim it.",
                            bot.bot_id,
                            bot.config.base_currency,
                            bot.config.base_currency,
                            usd_amount,
                        )
                    else:
                        granted, reason, _ = self._capital_registry.request_reservation(
                            bot_id=bot.bot_id,
                            exchange_id=bot.config.exchange_id,
                            base_currency=bot.config.base_currency,
                            usd_amount=usd_amount,
                            current_rate_usd_per_base=rate,
                            bot_mode=mode_str,
                        )
                        if not granted:
                            self._bus.emit(
                                "bot.register_refused",
                                bot_id=bot.bot_id,
                                reason=reason or "CapitalRegistry refused",
                            )
                            return False, reason
            except Exception as _reg_exc:
                # If the registry path crashes, log + fall through.
                # The registry is a safety layer, not a hard requirement —
                # never block bot creation on a registry bug.
                logger.warning(
                    "v3.20.71 CapitalRegistry consult failed for bot %s; "
                    "proceeding without reservation: %s",
                    bot.bot_id,
                    _reg_exc,
                )

        self._bots[bot.bot_id] = bot
        if self._volume_guard:
            bot._volume_guard = self._volume_guard
        if hasattr(self, "_data_pool") and self._data_pool:
            bot._data_pool = self._data_pool
        # Session 26 P1b — attach SmartWireManager to every new bot so
        # (a) source-side fold routing can find outgoing wires via the
        # manager, and (b) target-side apply_wire_income is reachable
        # from distribute_fold_profit via the attach_bot registry.
        #
        # v3.16.46 — Operator-flagged bug 2026-05-10: "Smart Wire has
        # never worked." Root cause: previously we called only
        # attach_bot (populates _bot_refs) but NEVER register_bot
        # (populates _ledgers). With empty _ledgers, the wired_in /
        # wired_out tracking that the Bot Swarm visibility tab reads
        # had nowhere to land — every bot showed $0.0000 forever.
        # Fix: also call register_bot here so the ledger entry exists
        # at the moment the bot is attached. seed_amount is the bot's
        # configured target_balance (the closest analogue to "starting
        # capital" we have at this point in the lifecycle).
        try:
            self._smart_wire_mgr.attach_bot(bot.bot_id, bot)
            if hasattr(bot, "set_smart_wire"):
                bot.set_smart_wire(self._smart_wire_mgr)
            # v3.16.46 — ensure ledger entry exists for this bot
            try:
                _existing_ledgers = getattr(self._smart_wire_mgr, "_ledgers", {}) or {}
                if bot.bot_id not in _existing_ledgers:
                    _seed = float(getattr(bot.config, "target_balance", 0) or 0)
                    _asset = str(
                        getattr(bot.config, "target_asset", "")
                        or getattr(bot.config, "symbol", "")
                    )
                    self._smart_wire_mgr.register_bot(
                        bot.bot_id, _asset, seed_amount=_seed
                    )
            except Exception as _reg_exc:
                logger.warning(
                    "Bot %s SmartWire ledger register failed: %s", bot.bot_id, _reg_exc
                )
        except Exception as _sw_exc:
            logger.warning("Bot %s SmartWire attach failed: %s", bot.bot_id, _sw_exc)
        # v3.15.56 — give the bot a back-reference to this manager so it
        # can answer questions about siblings (multi-base attribution).
        # Operator directive 2026-04-25: a RAVE/USDC bot must NOT see
        # the RAVE/USD bot's accumulated RAVE as if it owned it.
        if hasattr(bot, "set_bot_manager"):
            try:
                bot.set_bot_manager(self)
            except Exception as _bm_exc:
                logger.warning("Bot %s set_bot_manager failed: %s", bot.bot_id, _bm_exc)
        # v3.23.47 — attach the process-wide MarketPairsScout so the
        # bot (and eventually the Bot Details Status tab) can see all
        # pairs trading its target asset. Read-only in this cascade.
        if hasattr(bot, "set_market_pairs_scout"):
            try:
                from ..exchange.market_pairs_scout import get_scout

                bot.set_market_pairs_scout(get_scout())
            except Exception as _scout_exc:
                logger.warning(
                    "Bot %s set_market_pairs_scout failed: %s", bot.bot_id, _scout_exc
                )
        # Register symbol for trade history scanning on next connect
        if self._connector:
            self._connector.add_scan_symbol(bot.config.symbol)
            logger.debug("Registered %s for trade history scanning", bot.config.symbol)
            # Ensure bot.exchange points to the connector (idempotent).
            if not getattr(bot, "exchange", None):
                try:
                    bot.exchange = self._connector
                except Exception as _attach_exc:
                    # Same as in set_connector: the bot may be a frozen
                    # record that refuses any attribute write, so
                    # registration must still succeed. But the bot ends
                    # up with no connector, the later read falls back to
                    # a default, and a bot with no connector cannot
                    # trade — so say which bot it was.
                    logger.error(
                        "Bot %s would not accept the exchange connector "
                        "(%s). It has no connector and cannot trade "
                        "until one is attached.",
                        getattr(bot, "bot_id", "<unknown bot>"),
                        _attach_exc,
                    )
            # MEM-256 — fire the bootstrap live-pull for this bot now.
            if hasattr(bot, "bootstrap_exchange_state"):
                self._dispatch_bootstrap(bot, "register")
        self._bus.emit("bot.registered", bot_id=bot.bot_id)
        return True, None

    def unregister(self, bot_id: str) -> None:
        """Remove a bot from the registry.

        v3.20.71 (MEM-417): if a CapitalRegistry is wired, the bot's
        reservation is released so the freed USD becomes available to
        sibling bots. Idempotent — releasing an unknown bot_id is a
        no-op."""
        # v3.24.35 (C01) — DELETE THE RECORD ON DISK, EXPLICITLY.
        #
        # This method used to touch no storage at all: no state manager,
        # no save call, no file access. A deleted bot disappeared from
        # bot_state.json only because the next save rebuilt the file
        # from RAM — deletion was a side effect of the very bug C01
        # fixes, which is also why it was never logged anywhere.
        #
        # Now that save_state carries unknown records forward, that
        # accident is gone and delete must be a positive act, or a
        # deleted bot returns on the next save.
        #
        # The two pops below are DIAGNOSTIC ONLY. An earlier comment
        # here claimed they were what protected an explicit delete;
        # they never were, and believing it is how this bug comes back.
        # The carry-forward reads the FILE, not these dicts.
        self._restore_ledger.pop(str(bot_id), None)
        self._boot_state_records.pop(str(bot_id), None)
        if self._state_manager is not None:
            try:
                self._state_manager.delete_bot(str(bot_id))
            except Exception as exc:  # noqa: BLE001 - teardown continues
                logger.error(
                    "unregister(%s): disk delete failed (%s) — the record "
                    "remains on disk and will be carried forward",
                    bot_id,
                    exc,
                )
        # v3.20.71 — release capital reservation before tearing down
        # other linkages (the bot's claim must not outlive its place
        # in the manager registry).
        if self._capital_registry is not None:
            try:
                self._capital_registry.release_reservation(bot_id=bot_id)
            except Exception as _rel_exc:
                logger.warning(
                    "v3.20.71 CapitalRegistry release failed for bot %s: %s",
                    bot_id,
                    _rel_exc,
                )
        bot = self._bots.pop(bot_id, None)
        if bot and self._connector:
            # Only remove symbol if no other bot is trading it
            still_used = any(
                b.config.symbol == bot.config.symbol for b in self._bots.values()
            )
            if not still_used:
                self._connector.remove_scan_symbol(bot.config.symbol)
        # Session 26 P1b — clear bot from SmartWireManager (drops bot
        # ref + any wires that reference it on either side)
        try:
            self._smart_wire_mgr.detach_bot(bot_id)
        except Exception as _sw_exc:
            logger.warning("Bot %s SmartWire detach failed: %s", bot_id, _sw_exc)
        self._bus.emit("bot.unregistered", bot_id=bot_id)

    def get_trade_history(self, symbol: str):
        """
        Return the most recent HistoryAnalysis for a symbol.
        Returns None if no connector is set or history not yet available.
        """
        if self._connector:
            return self._connector.get_history(symbol)
        return None

    def refresh_trade_history(self, symbol: str | None = None):
        """
        Trigger a fresh trade history scan.  If symbol is None, refreshes
        all registered symbols.  Safe to call from GUI Refresh button.
        """
        if self._connector:
            self._connector.refresh_history(symbol)
        else:
            logger.warning("refresh_trade_history: no connector attached")

    def get_bot(self, bot_id: str) -> Optional[BotContainer]:
        return self._bots.get(bot_id)

    # ------------------------------------------------------------------
    # Extractor Tranche parent lookup
    # ------------------------------------------------------------------
    def list_parent_bot_candidates_for_base_currency(
        self, base_currency: object, *, exchange_id: object
    ) -> list[tuple[str, BotContainer]]:
        """Return the Scrumming Bots on this exchange holding a currency.

        The answer is ``(bot_id, bot)`` pairs, in registration order.
        Both arguments are taken as anything at all, because a caller
        can hand over whatever a saved config had in it; what is not
        text simply matches nothing.

        THIS IS THE MATCH ITSELF, AND IT IS THE ONLY COPY OF IT.
        `find_parent_bot_for_base_currency` answers a different
        question — "which bot gets the money" — and answers nothing
        unless exactly one bot holds the currency. That single answer is
        all a payment needs, but it cannot tell an empty set of holders
        from a crowded one.

        A caller that must tell those two apart needs the count. The bot
        creation wizard is one: it refuses to create an Extractor in
        both cases, and the operator's remedy is opposite in each
        (create a holder, versus reduce two holders to one). Counting
        with a second copy of the match is how the two answers would
        drift apart, so the list is what is computed here and the single
        answer is derived from it.

        NOTHING IS REFUSED HERE AND NOTHING IS LOGGED. A list of two is
        a fact about the books, not a decision about money. The refusal,
        and the record of it, stay with the lookup that moves money.

        The rules are the lookup's rules, because this is where they are
        written: Scrumming Bots only, same exchange only, and the
        currency matched with surrounding spaces removed and without
        regard to upper or lower case. Anything that is not text matches
        nothing and returns an empty list.
        """
        if not isinstance(base_currency, str):
            return []
        wanted = base_currency.strip().upper()
        if not wanted:
            return []
        # Imported here, not at module scope: scrumming_bot imports this
        # module, so a top-level import would be circular.
        from .scrumming_bot import ScrummingBot

        holders: list[tuple[str, BotContainer]] = []
        for bot_id, bot in self._bots.items():
            if not isinstance(bot, ScrummingBot):
                continue
            if (
                getattr(getattr(bot, "config", None), "exchange_id", None)
                != exchange_id
            ):
                continue
            held = getattr(getattr(bot, "config", None), "target_asset", "")
            if not isinstance(held, str):
                continue
            if held.strip().upper() == wanted:
                holders.append((bot_id, bot))
        return holders

    def find_parent_bot_for_base_currency(
        self, base_currency: Any, *, exchange_id: Any
    ) -> Optional[BotContainer]:
        """Return the Scrumming Bot that holds this currency, or None.

        An Extractor works in one base currency and hands that currency
        back when it closes a position. Operator design 2026-08-09: the
        money goes to the Scrumming Bot that HOLDS that currency, which
        raises its target balance to keep the gain instead of selling it
        away as surplus. `ScrummingBot.apply_extractor_tranche_return`
        does that booking; this is how a caller finds the bot to call it
        on.

        A Scrumming Bot holds exactly one asset, named `target_asset` in
        its config. So the parent of an Extractor whose `base_currency`
        is ETH is the Scrumming Bot whose `target_asset` is ETH.

        SAME EXCHANGE, ALWAYS. Operator correction 2026-08-10: "Scrumming
        (Parent) and Extractor (Sibling) are Exchange Bound. We have not
        added any cross-exchange arbitrage features yet." Money that came
        back on one exchange never landed on another, so a bot elsewhere
        is not a parent however well its currency matches -- paying it
        would raise a target balance against money that bot never
        received, while the bot that did receive it stays short. The
        caller names its own exchange, which every config carries as
        `exchange_id` beside `base_currency` and `target_asset`. It is
        asked for by name and has no default, so no caller can leave it
        out: one that tries is refused outright instead of silently
        matching every exchange at once.

        The exchange has to match exactly. Every bot's exchange comes
        from the same saved settings, and `restore_bots_from_state`
        refuses to load a bot whose saved settings name no exchange, so
        both sides are the same text or the bot is not on the books at
        all. Any difference therefore means a different exchange and the
        answer is nothing, which costs a lift and never pays a stranger.

        The currency is matched with surrounding spaces removed and
        without regard to upper or lower case. Anything that is not text
        returns None.

        TWO HOLDERS RETURNS NOTHING. Real money moves on this answer. If
        two Scrumming Bots hold the same asset there is nothing here that
        can tell which one earned the return, and picking either would
        raise the wrong bot's target on money it never received while the
        right bot stays short. The refusal is logged.

        An Extractor is never a parent: it is the child, and it has no
        target balance to raise.

        The matching itself lives in
        `list_parent_bot_candidates_for_base_currency` so that a caller
        needing the COUNT of holders reads the same rules this does. The
        rules above are unchanged; only their one copy moved.
        """
        holders = self.list_parent_bot_candidates_for_base_currency(
            base_currency, exchange_id=exchange_id
        )
        wanted = (
            base_currency.strip().upper()
            if isinstance(base_currency, str)
            else base_currency
        )
        if len(holders) == 1:
            return holders[0][1]
        if len(holders) > 1:
            logger.warning(
                "extractor parent lookup REFUSED %s: %d Scrumming Bots "
                "hold it (%s). Returning nothing rather than guessing an "
                "owner — the returned base currency stays where it is.",
                wanted,
                len(holders),
                ", ".join(bid for bid, _ in holders),
            )
        return None

    def list_extractor_children_for_parent(
        self, parent: object
    ) -> list[tuple[str, object]]:
        """Return the Extractors that spend this Scrumming Bot's asset.

        Item 4, operator design 2026-08-09: an Extractor's in-flight
        position is an "Extractor Tranche" and it is "listed under the
        base-currency bot". Listing needs the walk that the payment
        never did — parent to children, rather than child to parent.

        THIS IS THE SAME MATCH, READ BACKWARDS. A bot is a child of this
        parent when it is an Extractor, on the same exchange, whose
        `base_currency` is the parent's `target_asset`. That is exactly
        the predicate `list_parent_bot_candidates_for_base_currency`
        applies in the other direction, so it lives here beside it
        rather than in `scrumming_bot`, where a second copy would drift
        away from the first and start disagreeing about who owes whom.

        A CROWD IS NOT REFUSED HERE. The parent lookup returns nothing
        when two Scrumming Bots hold one asset, because a payment cannot
        be split by guessing. Listing has no such problem: several
        Extractors may lease from one parent at once, and naming all of
        them is the correct answer. Nothing here moves money, so nothing
        here needs that refusal.

        Anything that is not a Scrumming Bot with a text `target_asset`
        has no children, and the answer is an empty list. Sorted by bot
        id so the listing does not reshuffle between reads.
        """
        # Imported here, not at module scope: both modules import this
        # one, so a top-level import would be circular.
        from .scrumming_bot import ScrummingBot
        from .extractor_bot import ExtractorBot

        if not isinstance(parent, ScrummingBot):
            return []
        p_cfg = getattr(parent, "config", None)
        held = getattr(p_cfg, "target_asset", "")
        if not isinstance(held, str):
            return []
        wanted = held.strip().upper()
        if not wanted:
            return []
        p_exchange = getattr(p_cfg, "exchange_id", None)
        children: list[tuple[str, object]] = []
        for bot_id, bot in self._bots.items():
            if not isinstance(bot, ExtractorBot):
                continue
            c_cfg = getattr(bot, "config", None)
            if getattr(c_cfg, "exchange_id", None) != p_exchange:
                continue
            spends = getattr(c_cfg, "base_currency", "")
            if not isinstance(spends, str):
                continue
            if spends.strip().upper() == wanted:
                children.append((bot_id, bot))
        children.sort(key=lambda pair: pair[0])
        return children

    # ------------------------------------------------------------------
    # v3.15.56 — multi-base attribution support
    # ------------------------------------------------------------------
    def has_sibling_target_bots(self, bot_id: str, target_asset: str) -> bool:
        """Return True if any OTHER registered bot has the same target
        asset (regardless of base currency).

        Used by ScrummingBot.tick init handshake to decide whether
        ``exchange.get_balance(target_asset).total`` represents this
        bot's holdings (single-bot scenario, trust it) or a shared pool
        across multiple bots (multi-base scenario, do NOT trust it —
        the bot must use its own _main_lots as the authoritative
        attribution of "what THIS bot bought").

        Operator directive 2026-04-25:
          "if I have my $450 USD RAVE bot running, creating a RAVE
           USDC bot at $50 causes the second bot to want to sell the
           majority of the position because it sees what it thinks is
           a surplus rather than just considering the fact that it
           has $50 USDC that it has failed to convert to RAVE."

        The fix: detect the multi-bot scenario at this layer; the
        downstream bot then refuses to inherit exchange total as its
        own holdings. Even paused/idle sibling bots count — restarting
        Bot A must not surprise Bot B.
        """
        target_norm = (target_asset or "").upper()
        for other_id, other_bot in self._bots.items():
            if other_id == bot_id:
                continue
            try:
                other_target = (other_bot.config.target_asset or "").upper()
            except Exception as _read_exc:
                # Skipping a bot whose settings cannot be read is the
                # right thing to do — one broken record must not stop
                # the check. But it used to happen in silence, so a bot
                # that quietly dropped out of every sibling check looked
                # exactly like a bot that was never there. Now it says
                # which bot it dropped and why.
                logger.warning(
                    "Sibling check for %s skipped bot %s: its coin "
                    "setting could not be read (%s). That bot is not "
                    "counted as sharing %s.",
                    bot_id,
                    other_id,
                    _read_exc,
                    target_norm or "the coin",
                )
                continue
            if other_target == target_norm and target_norm:
                return True
        return False

    def sum_sibling_tracked_units(self, bot_id: str, target_asset: str) -> float:
        """Sum the tracked _main_lots units across all sibling bots
        with the same target_asset (excluding the caller).

        Used by reconciliation in multi-base mode: this bot's
        _current_holdings should never exceed
        ``exchange_total - sum_sibling_tracked_units``. If it does,
        a sibling bot has lost track of some of its inventory.
        """
        target_norm = (target_asset or "").upper()
        total = 0.0
        for other_id, other_bot in self._bots.items():
            if other_id == bot_id:
                continue
            try:
                if (other_bot.config.target_asset or "").upper() != target_norm:
                    continue
            except Exception as _read_exc:
                # Same reason as the sibling check above: skip the
                # unreadable bot, but say so. A silent skip here makes
                # the running total look smaller than it is, and the
                # total is what tells a bot how much of the coin on the
                # exchange is already spoken for.
                logger.warning(
                    "Tracked-units total for %s skipped bot %s: its "
                    "coin setting could not be read (%s). None of that "
                    "bot's %s is counted in the total.",
                    bot_id,
                    other_id,
                    _read_exc,
                    target_norm or "coin",
                )
                continue
            try:
                lots = getattr(other_bot, "_main_lots", []) or []
                for lot in lots:
                    total += float(lot.get("units", 0) or 0)
            except Exception as _lot_exc:
                # One unreadable purchase record stops this bot's
                # remaining records from being added. Whatever was
                # already added stays in the total. Say so, because the
                # total that comes out is short by an unknown amount
                # and the caller cannot tell from the number alone.
                logger.warning(
                    "Tracked-units total for %s stopped part-way "
                    "through bot %s: one of its purchase records "
                    "could not be read (%s). The total is short by "
                    "that bot's remaining %s.",
                    bot_id,
                    other_id,
                    _lot_exc,
                    target_norm or "coin",
                )
                continue
        return total

    def _one_sibling_claim(
        self,
        other_bot: Any,
        other_cfg: Any,
        dollar_pegged: bool,
    ) -> "tuple[Optional[float], str]":
        """What one other bot has claimed from the shared pool.

        The answer is in units of the pool's currency. Returns the
        claim and an empty reason when it can be worked out, or
        nothing and the reason when it cannot.

        Nothing is never the same as zero here. Zero means this bot
        claims none of the pool. Nothing means we do not know what it
        claims, and a bot that does not know must not guess low.

        Two kinds of claim are added together. A dollar allocation is
        turned into pool units with the bot's own cached rate. An
        allocated chunk is already in pool units and is added as it
        stands.
        """
        claim = 0.0
        try:
            target_usd = float(getattr(other_cfg, "target_balance", 0) or 0)
        except Exception as _t_exc:
            return None, f"its dollar allocation could not be read ({_t_exc})"
        if not math.isfinite(target_usd):
            return None, "its dollar allocation is not a number"
        if target_usd < 0:
            return None, (
                f"its dollar allocation is negative ({target_usd}), which "
                f"cannot be an amount of money"
            )
        if target_usd > 0:
            rate, why = self._sibling_pool_rate(other_bot, dollar_pegged)
            if rate is None:
                return None, why
            claim += target_usd / rate
        try:
            chunk_base = float(getattr(other_bot, "_chunk_size_base", 0) or 0)
        except Exception as _c_exc:
            return None, f"its allocated chunk could not be read ({_c_exc})"
        if not math.isfinite(chunk_base):
            return None, "its allocated chunk is not a number"
        if chunk_base < 0:
            return None, (
                f"its allocated chunk is negative ({chunk_base}), which "
                f"cannot be an amount held"
            )
        return claim + chunk_base, ""

    def _sibling_pool_rate(
        self,
        other_bot: Any,
        dollar_pegged: bool,
    ) -> "tuple[Optional[float], str]":
        """How many dollars one unit of the pool currency is worth,
        taken from the other bot's own cached rate.

        Returns the rate and an empty reason, or nothing and the
        reason. When the pool holds a coin that is meant to be worth
        one dollar, one is the true rate and is used whenever the
        cached rate is unusable.

        This used to fall back to one for EVERY pool. On a Bitcoin
        pool that read a bot's $1,000 allocation as a claim on 1,000
        Bitcoin.
        """
        raw: Any = None
        rate: "Optional[float]" = None
        try:
            # Inside the guard on purpose. A missing rate is not the
            # only way this read fails: reading it can raise, and a
            # default value does not catch that.
            raw = getattr(other_bot, "_quote_to_usd", None)
            if raw is not None:
                rate = float(raw)
        except Exception as _r_exc:
            if dollar_pegged:
                return 1.0, ""
            return None, f"its cached rate could not be read ({_r_exc})"
        if rate is not None and math.isfinite(rate) and rate > 0:
            return rate, ""
        if dollar_pegged:
            return 1.0, ""
        return None, (
            f"its cached rate is {raw!r}, so its dollar allocation "
            f"cannot be turned into pool units"
        )

    def sum_sibling_base_currency_claims(
        self,
        bot_id: str,
        exchange_id: str,
        currency: str,
    ) -> "Optional[float]":
        """Sum of base-currency (quote-currency) claims by OTHER bots
        on the same exchange.

        Returns nothing when any other bot in the pool cannot be read.
        A total that quietly leaves one bot's claim out is LOWER than
        the truth, and a low total tells the asking bot that money is
        free when another bot has already claimed it. That is how two
        bots come to spend the same money. There is no safe number to
        hand back in that case, so this hands back nothing and writes
        one warning naming every bot it could not read, the reason for
        each, and the incomplete total, so the size of the gap is on
        the record.

        A caller that gets nothing must refuse to act. It must not
        read nothing as zero claims. Zero is the most dangerous answer
        of all, because zero says the whole pool is free.

        A "claim" is operator-allocated capital that a sibling bot OWNS
        even if it's not actively deployed. For:

          * **ScrummingBots** whose ``config.base_currency == currency``:
            their ``target_balance`` is the claim (the USD-equivalent
            target the bot's accumulation strategy is sized to).
            Converted to base-currency units via the sibling's own
            cached ``_quote_to_usd`` rate; ``_quote_to_usd`` represents
            "1 unit of quote currency = N USD", so ``USD / _quote_to_usd``
            yields the equivalent quote-currency units. A pool of a
            coin that is meant to be worth one dollar needs no rate.
            Any other pool with no usable rate counts as unreadable.
          * **ExtractorBots** whose ``config.base_currency == currency``:
            their ``_chunk_size_base`` (operator-allocated base-unit
            chunk). Forward-compatible — the Extractor class is
            slated to ship in v3.19.0 (per the Extractor design doc
            §13a). Until then this branch is dormant via ``getattr``.

        When every bot in the pool can be read, returns the sum in
        **base-currency (quote) units**. The caller subtracts that from
        the raw exchange balance to get its claim-aware free.

        Includes:
          - All sibling bots regardless of run state. A paused bot
            still owns its allocation; restarting a paused sibling must
            not surprise the active bot by silently un-reserving its
            funds.

        Excludes:
          - The querying bot itself (its own claim is implicit).
          - Bots on different exchanges (different fund pools).

        Operator directive 2026-05-20 (Extractor design doc §13a):

          > "It will also be important for the Scrumming Bots to
          >  detect base currency balance overlap as excess and try to
          >  sell what is assigned to an Extractor."

        v3.18.18 ships this helper standalone (decoupled from Extractor
        build per Tier-1 review of the Extractor design doc) so the
        helper's regression coverage stays independent of Extractor
        completion. The helper also closes a multi-ScrummingBot
        over-allocation risk — two ScrummingBots on the same exchange
        with overlapping base_currency (e.g. both on USD) could
        previously each see the entire USD pool as their own free
        balance; with this helper, each sees only its claim-aware
        slice.
        """
        currency_norm = (currency or "").upper()
        if not currency_norm:
            logger.warning(
                "Asked what the other bots have claimed on %s, but no "
                "currency was named. Returning no total rather than "
                "zero, because zero would say the whole pool is free.",
                exchange_id,
            )
            return None
        dollar_pegged = currency_norm in DOLLAR_PEGGED_CURRENCIES
        total = 0.0
        unread: list[str] = []
        for other_id, other_bot in self._bots.items():
            if other_id == bot_id:
                continue
            try:
                other_cfg = other_bot.config
                same_exchange = other_cfg.exchange_id == exchange_id
                other_base = (getattr(other_cfg, "base_currency", "") or "").upper()
            except Exception as _cfg_exc:
                # This bot may or may not be in the pool. It cannot be
                # skipped on the strength of a failed read: if it IS in
                # the pool, skipping it hides its claim.
                unread.append(
                    f"{other_id} (its settings could not be read: " f"{_cfg_exc})"
                )
                continue
            if not same_exchange or other_base != currency_norm:
                # A different exchange or a different currency is a
                # different pool of money. Not a claim on this one.
                continue
            claim, why = self._one_sibling_claim(other_bot, other_cfg, dollar_pegged)
            if claim is None:
                unread.append(f"{other_id} ({why})")
                continue
            total += claim
        if unread:
            logger.warning(
                "Could not read what %d of the other bots on %s have "
                "claimed of the %s pool: %s. Leaving them out would "
                "have reported %.8f %s, which is lower than the truth "
                "and would let a bot spend money another bot has "
                "already claimed. Returning no total instead.",
                len(unread),
                exchange_id,
                currency_norm,
                "; ".join(unread),
                total,
                currency_norm,
            )
            return None
        return total

    def list_bots(self) -> list[dict]:
        """Return status snapshots for all registered bots."""
        return [bot.get_status() for bot in self._bots.values()]

    def list_bots_by_exchange(self, exchange_id: str) -> list[dict]:
        """Filter bots by exchange."""
        return [
            bot.get_status()
            for bot in self._bots.values()
            if bot.config.exchange_id == exchange_id
        ]

    # -- State persistence -----------------------------------------------
    def save_all_state(self) -> None:
        """Save complete state of all bots + Smart Wire registry.

        v3.15.68 — operator directive 2026-04-26: "Bot swarm state is
        not being preserved." Smart Wire registry (source→target→pct)
        is now saved alongside bot state and rehydrated on restore.
        """
        if not self._state_manager:
            return
        states = [bot.get_full_state() for bot in self._bots.values()]
        wires = []
        ledgers: list = []
        try:
            if self._smart_wire_mgr is not None and hasattr(
                self._smart_wire_mgr, "export_wires"
            ):
                wires = self._smart_wire_mgr.export_wires()
        except Exception as exc:
            logger.warning("save_all_state: smart wire export raised: %s", exc)
        # v3.16.57 — persist per-bot ledgers (wired_in/wired_out totals
        # + provenance) so Smart Wire credits survive restart. Operator
        # bug 2026-05-13: "Smart Wire credits are not persisting across
        # platform restarts." Root cause: only topology was exported,
        # not the ledger state.
        try:
            if self._smart_wire_mgr is not None and hasattr(
                self._smart_wire_mgr, "export_ledgers"
            ):
                ledgers = self._smart_wire_mgr.export_ledgers()
        except Exception as exc:
            logger.warning("save_all_state: smart wire ledger export raised: %s", exc)
        # v3.24.35 (C01) — the DRY-RUN block that stood here is gone.
        # It computed which records a future merge WOULD carry forward
        # and then did not carry them. save_state now carries them for
        # real, and keeping both would leave two answers to one question.
        self._state_manager.save_state(
            states, smart_wires=wires, smart_wire_ledgers=ledgers
        )

    def restore_smart_wires_from_state(self, state: dict) -> int:
        """v3.15.68 — restore the Smart Wire registry from saved state.
        Returns count of wires imported. Re-emits ``wire.created``
        events on the bus so the GUI visualizer can rehydrate its
        on-screen wire list.
        """
        wires = state.get("smart_wires", []) if isinstance(state, dict) else []
        ledgers = state.get("smart_wire_ledgers", []) if isinstance(state, dict) else []
        if (not wires and not ledgers) or self._smart_wire_mgr is None:
            return 0
        n = 0
        try:
            if wires and hasattr(self._smart_wire_mgr, "import_wires"):
                n = self._smart_wire_mgr.import_wires(wires)
        except Exception as exc:
            logger.warning("restore_smart_wires_from_state: import raised: %s", exc)
            return 0
        # v3.16.57 — restore per-bot ledger totals so wired_in /
        # wired_out / provenance survive restart. Attach_bot at startup
        # registers fresh BotLedger entries; import_ledgers overlays the
        # saved totals onto them.
        try:
            if ledgers and hasattr(self._smart_wire_mgr, "import_ledgers"):
                _l = self._smart_wire_mgr.import_ledgers(ledgers)
                if _l > 0:
                    logger.info("Bot Swarm restored: %d ledger(s) rehydrated", _l)
        except Exception as exc:
            logger.warning(
                "restore_smart_wires_from_state: ledger import raised: %s", exc
            )
        # Re-emit wire.created events so the GUI visualizer (which
        # subscribes to the event bus) draws them. Skip if both
        # endpoints aren't currently registered — orphaned wires after
        # bot deletion shouldn't redraw.
        for w in wires:
            try:
                src = str(w.get("source_id", ""))
                tgt = str(w.get("target_id", ""))
                pct = float(w.get("pct", 0))
                if not src or not tgt:
                    continue
                if src not in self._bots or tgt not in self._bots:
                    continue
                self._bus.emit("wire.created", source_id=src, target_id=tgt, pct=pct)
            except Exception as _wire_exc:
                # Skipping a saved link that cannot be read is right —
                # one bad record must not stop the rest being drawn.
                # It used to be silent, so a link the operator set up
                # would simply not appear, with nothing said anywhere.
                # The count printed below still counts it, so the count
                # and the picture disagree; this line is how that shows.
                logger.warning(
                    "Skipped a saved bot-to-bot link while restoring: "
                    "the record could not be read (%s). Record: %r. "
                    "It is not drawn.",
                    _wire_exc,
                    w,
                )
                continue
        logger.info("Bot Swarm restored: %d Smart Wire(s) rehydrated from state", n)
        return n

    def get_saved_state(self) -> dict:
        """Load saved state without restoring."""
        if not self._state_manager:
            return {}
        return self._state_manager.load_state()

    def _ledger_skip(self, bid: str, reason: str) -> None:
        """Record that a bot was OBSERVED failing to load.

        v3.24.35 (C01 PR-0). The single writer of ``_restore_ledger``.
        Only code that watched a bot fail may call it, which is what
        makes the ledger different from inferring intent from absence:
        a bot missing from ``self._bots`` might have been deleted by the
        operator, but a bot in this ledger definitely was not.

        Never raises — a bookkeeping failure must not abort a restore
        that is already handling an error.
        """
        try:
            self._restore_ledger[str(bid)] = str(reason)
        except Exception:  # noqa: BLE001,S110 - bookkeeping only
            pass  # noqa: S110

    def restore_bots_from_state(self, state: dict) -> list[str]:
        """
        Recreate bots from saved state in PAUSED mode.
        Does NOT connect to exchanges or place any orders.
        Returns list of restored bot IDs.

        SAFETY: All restored bots start in IDLE state with a
        'restored' flag. User must explicitly start each one,
        which triggers exchange sync before any trading.
        """
        from .bot_container import BotConfig, BotMode

        bots_data = state.get("bots", {})
        restored = []

        # v3.24.35 (C01 PR-0) — hold the boot records in RAM.
        #
        # Deep-copied so a later mutation of `state` (or of a bot's own
        # dict during restore) cannot alter what was actually on disk at
        # boot. PR-1 hands these to save_state BY VALUE, which is what
        # lets the save path carry a skipped bot's record forward
        # without performing a read — a read there could fail and freeze
        # persistence for the whole fleet.
        import copy as _copy

        try:
            self._boot_state_records = _copy.deepcopy(bots_data) or {}
        except Exception as _cp_exc:  # noqa: BLE001 - never block restore
            self._boot_state_records = {}
            logger.error(
                "C01: could not snapshot boot records (%s); carry-forward "
                "will be unavailable this session",
                _cp_exc,
            )
        self._restore_ledger = {}
        self._restore_completed = False

        for bid, bot_data in bots_data.items():
            cfg = bot_data.get("config", {})
            if not cfg.get("exchange_id"):
                # v3.24.35 (C01 PR-0) — this skip was entirely SILENT.
                # Of the five `continue` exits in this function it was
                # the only one with no log line at any level, so a bot
                # whose persisted config lost its exchange_id vanished
                # without a trace -- and then, because save_state
                # rebuilds "bots" solely from the registered set, its
                # record was deleted from bot_state.json by the 60s
                # save timer. Silent skip followed by silent deletion.
                #
                # Measured 2026-08-05 on the live file: 35 bots holding
                # 1,949 lots and 829 fold tranches, none of it
                # reconstructible from exchange fill history.
                logger.error(
                    "Bot %s SKIPPED during restore: persisted config has "
                    "no exchange_id. Its saved record (lots, tranches, "
                    "anchor balance) is NOT loaded and must not be "
                    "overwritten.",
                    bid,
                )
                self._ledger_skip(bid, "no exchange_id in persisted config")
                continue

            # Recreate BotConfig.
            # v3.20.4 — grid handling fully removed. Missing/empty
            # mode is treated as SCRUMMING for backward compat with
            # pre-v3.19.1 save files; any explicit but unrecognized
            # mode string (including the now-defunct "grid") is
            # ERROR-logged and skipped rather than silently
            # misclassified.
            # sadp: R28 FL  R55 GOV  R68 DPA
            _mode_str = (cfg.get("mode") or "").lower()
            if _mode_str == "extractor":
                mode = BotMode.EXTRACTOR
            elif _mode_str == "scrumming" or _mode_str == "":
                mode = BotMode.SCRUMMING
            else:
                logger.error(
                    "Bot %s has unrecognized mode %r in saved state "
                    "— skipping restoration. (Legacy 'grid' mode was "
                    "removed v3.20.4; persisted grid bots are not "
                    "restorable. Add an explicit branch in "
                    "restore_bots_from_state() if you intend to "
                    "support a new mode.)",
                    bid,
                    _mode_str,
                )
                self._ledger_skip(bid, "legacy grid mode (unrestorable)")
                continue
            # v3.20.35 — restore path migrated to make_bot_config
            # factory (per operator directive 2026-05-25 "Make sure
            # any syntax deemed 'old' is being purged"). Same
            # three-layer split as main_window.py: shared kwargs +
            # mode-specific kwargs + factory call. Stale persisted
            # configs with mode-foreign field values are caught at
            # restore time with a clear error, then skipped (the
            # restore path must not abort the platform launch on
            # one bad bot — we log and continue).
            # Local boolean hoisted so the test_bot_restoration_
            # dispatch fitness pin (which scans for the FIRST
            # mode-equality occurrence and expects ExtractorBot
            # construction within 600 chars) still lands on the
            # actual dispatch branch below, not on the target_asset
            # default ternary.
            _ta_default = "*" if mode.value == "extractor" else "BTC"
            _shared_kwargs = {
                "exchange_id": cfg["exchange_id"],
                "base_currency": cfg.get("base_currency", "USDT"),
                "target_asset": cfg.get("target_asset", _ta_default),
                "symbol": cfg.get("symbol", ""),
                "target_balance": cfg.get("target_balance", 200.0),
                "ta_timeframe": cfg.get("ta_timeframe", "1h"),
                "visibility": cfg.get("visibility", "orderbook"),
                "aggressive_trading": cfg.get("aggressive_trading", False),
                # v3.23.25 — Stack Mode (renamed from bulk_trading).
                # Older bot_state.json files with `bulk_trading: false`
                # are handled by _sanitize_deprecated_kwargs() at the
                # top of make_bot_config; the new field defaults False.
                "stack_mode": cfg.get("stack_mode", cfg.get("bulk_trading", False)),
                "split_distance": cfg.get("split_distance", 1.0),
                "stack_tranche_count_target": cfg.get("stack_tranche_count_target", 3),
                "stack_spacing_mode": cfg.get("stack_spacing_mode", "linear"),
                # v3.23.25 bulk_partial_on_return retired
                "max_entry_price": cfg.get("max_entry_price", None),
                "min_entry_price": cfg.get("min_entry_price", None),
                "trading_fee_pct": cfg.get("trading_fee_pct", 0.6),
            }
            if mode == BotMode.SCRUMMING:
                # v3.23.3 R-CLN Phase 1: 8 grid-legacy dead fields no
                # longer extracted from cfg. See
                # docs/audits/2026-06-12_scrumming_bot_field_alignment.md
                # for the list. Operator's bot_state.json may still
                # carry these keys — silently ignored by cleaned code.
                # GUI wizard/settings cleanup deferred to R-CLN Phase 2.
                _mode_kwargs = {
                    "investment_amount": cfg.get("investment_amount", 200.0),
                    "increment_style": cfg.get("increment_style", "linear"),
                    "spacing_style": cfg.get("spacing_style", "expanding"),
                    # v3.23.25 market_check_interval kwarg removed
                    "profit_folding_active": cfg.get("profit_folding_active", True),
                    "scrumming_interval_pct": cfg.get("scrumming_interval_pct", 1.0),
                    "profit_route": cfg.get("profit_route", "fold_to_target"),
                    "profit_route_bot_id": cfg.get("profit_route_bot_id", ""),
                    "scrum_fold_pct": cfg.get("scrum_fold_pct", 100),
                    # Item 9 — despawn timer. Absent from every
                    # state file written before 2026-08-13, so the
                    # default here is what those bots restore with: 0.
                    "tranche_despawn_days": cfg.get("tranche_despawn_days", 0),
                    "max_target_growth_pct": cfg.get("max_target_growth_pct", 1.0),
                    "bb_tolerance_pct": cfg.get("bb_tolerance_pct", 1.0),
                    "bb_landing_strip_candles": cfg.get("bb_landing_strip_candles", 3),
                    "scrum_detect_pct": cfg.get("scrum_detect_pct", 75),
                    "scrum_fire_pct": cfg.get("scrum_fire_pct", 0.5),
                    "bb_midline_gate": cfg.get("bb_midline_gate", True),
                    "scrum_read_rate_min": cfg.get("scrum_read_rate_min", 5),
                    "band_travel_pct": cfg.get("band_travel_pct", 70),
                    "bb_bullseye_check": cfg.get("bb_bullseye_check", True),
                    "hedge_rebalance_active": cfg.get("hedge_rebalance_active", True),
                    "hedge_balance": cfg.get("hedge_balance", 200.0),
                    "position_ceiling_enabled": cfg.get(
                        "position_ceiling_enabled", False
                    ),
                    "position_ceiling_multiple": cfg.get(
                        "position_ceiling_multiple", 5.0
                    ),
                    "detonation_enabled": cfg.get("detonation_enabled", False),
                    "detonation_timeframe": cfg.get("detonation_timeframe", "1d"),
                    "detonation_confidence_min": cfg.get(
                        "detonation_confidence_min", 0.75
                    ),
                    # v3.23.42 interop
                    "self_reserve_capital": cfg.get("self_reserve_capital", True),
                    "personal_hold_qty": cfg.get("personal_hold_qty", 0.0),
                    "circuit_breaker_soft_pct": cfg.get(
                        "circuit_breaker_soft_pct", 25.0
                    ),
                    "circuit_breaker_hard_pct": cfg.get(
                        "circuit_breaker_hard_pct", 35.0
                    ),
                    "circuit_breaker_cooldown_candles": cfg.get(
                        "circuit_breaker_cooldown_candles", 3
                    ),
                    "max_cartridge_size_pct": cfg.get("max_cartridge_size_pct", 10.0),
                    "max_cartridge_smart": cfg.get("max_cartridge_smart", False),
                    "max_cartridge_smart_ceiling_pct": cfg.get(
                        "max_cartridge_smart_ceiling_pct", 30.0
                    ),
                    "wire_inflow_stack_pct": cfg.get("wire_inflow_stack_pct", 1.0),
                    "scrum_require_ta_bullish": cfg.get(
                        "scrum_require_ta_bullish", True
                    ),
                    "scrum_hold_in_uptrend": cfg.get("scrum_hold_in_uptrend", True),
                    "scrum_defer_to_htf": cfg.get("scrum_defer_to_htf", True),
                    "fold_require_ta_bearish": cfg.get("fold_require_ta_bearish", True),
                    "fold_hold_in_downtrend": cfg.get("fold_hold_in_downtrend", True),
                    "fold_defer_to_htf": cfg.get("fold_defer_to_htf", True),
                }
            else:  # BotMode.EXTRACTOR
                _mode_kwargs = {
                    "extractor_chunk_size_usd": cfg.get(
                        "extractor_chunk_size_usd", 100.0
                    ),
                    "extractor_artillery_size_usd": cfg.get(
                        "extractor_artillery_size_usd", 5.0
                    ),
                    "extractor_scan_top_n": cfg.get("extractor_scan_top_n", 8),
                    "extractor_scan_refresh_candles": cfg.get(
                        "extractor_scan_refresh_candles", 60
                    ),
                    "extractor_pool_reserve_pct": cfg.get(
                        "extractor_pool_reserve_pct", 50.0
                    ),
                    "extractor_exit_pct": cfg.get("extractor_exit_pct", 100.0),
                    "extractor_drawdown_threshold_pct": cfg.get(
                        "extractor_drawdown_threshold_pct", 3.0
                    ),
                    "extractor_correction_skip_candles": cfg.get(
                        "extractor_correction_skip_candles", 4
                    ),
                    "extractor_max_cost_basis_multiple": cfg.get(
                        "extractor_max_cost_basis_multiple", 2.0
                    ),
                    "extractor_max_compounding_tier": cfg.get(
                        "extractor_max_compounding_tier", 3
                    ),
                    "extractor_hedge_budget_usd": cfg.get(
                        "extractor_hedge_budget_usd", 0.0
                    ),
                    "extractor_trend_strength_threshold": cfg.get(
                        "extractor_trend_strength_threshold", 0.65
                    ),
                    "extractor_alt_targets": list(
                        cfg.get("extractor_alt_targets", []) or []
                    ),
                    # v3.20.74 — Inverted Extractor (Q6/Q7/Q8/Q9):
                    # direction flag + standing-position import unit
                    # count for Inverted variants.
                    "extractor_direction": cfg.get("extractor_direction", "normal"),
                    "inverted_extractor_standing_alt_units": float(
                        cfg.get("inverted_extractor_standing_alt_units", 0.0) or 0.0
                    ),
                }
            try:
                config = make_bot_config(mode, **_shared_kwargs, **_mode_kwargs)
            except (ValueError, TypeError) as _restore_err:
                logger.error(
                    "Bot %s restoration FAILED — mode-shape "
                    "violation in persisted config: %s. Skipping "
                    "this bot. (Either operator manually edited "
                    "state.json to a bad shape, or a pre-v3.20.32 "
                    "config drifted out of mode invariants. To "
                    "recover: delete the bot's entry from state "
                    "and recreate via the wizard, OR fix the "
                    "persisted JSON to match mode invariants.)",
                    bid,
                    _restore_err,
                )
                self._ledger_skip(bid, "mode-shape violation in persisted config")
                continue

            # Create bot with placeholder exchange (will be replaced
            # on start).
            #
            # v3.20.4 — DISPATCH BY MODE. Prior to this hotfix, the
            # restore path always constructed a ScrummingBot regardless
            # of the persisted mode. EXTRACTOR-mode bots (added
            # v3.19.1) tripped ScrummingBot.__init__'s `assert
            # config.mode == BotMode.SCRUMMING` and **aborted the
            # platform launch** before the GUI loaded. Operator hit
            # this 2026-05-23 with a persisted Extractor in state.
            # Root cause: BotMode.EXTRACTOR was added to the enum but
            # the dispatch table at this call site was never updated.
            # The same cascade removed BotMode.GRID entirely (operator
            # directive 2026-05-23: "Grid code and dangling mentions
            # can be cleaned out").
            #
            # Discipline going forward:
            #   - Every BotMode value MUST have an explicit branch.
            #   - Unknown modes ERROR-log and `continue` — one corrupt
            #     record never takes down platform launch (R28 FL
            #     loud-but-not-fatal where the user is locked out).
            #   - Whole construction wrapped in try/except so a broken
            #     bot can't poison restoration of healthy bots either.
            #
            # ExtractorBot is constructed with enable_phantoms=False
            # unconditionally — Extractor does not use phantoms by
            # design (extractor_bot.py:140).
            # sadp: R28 FL  R55 GOV  R62 FRG  R68 DPA  R76 DMW
            bot = None
            try:
                if mode == BotMode.EXTRACTOR:
                    from ..trading.extractor_bot import ExtractorBot

                    bot = ExtractorBot(
                        config,
                        _PlaceholderExchangeForRestore(cfg["exchange_id"]),
                        enable_phantoms=False,
                    )
                    logger.info(
                        "Restore: constructed ExtractorBot for %s " "(mode=%s)",
                        bid[:8],
                        _mode_str,
                    )
                elif mode == BotMode.SCRUMMING:
                    from ..trading.scrumming_bot import ScrummingBot

                    # v3.16.27 P0g — restore phantom enabled flag from
                    # saved state. Default: True (matches
                    # ScrummingBot.__init__ default — preserves
                    # prior-version behavior for save files that don't
                    # carry the flag yet). Once a bot has been saved
                    # by v3.16.27+ it round-trips correctly.
                    _restored_phantoms_enabled = bot_data.get("phantoms_enabled", True)
                    bot = ScrummingBot(
                        config,
                        _PlaceholderExchangeForRestore(cfg["exchange_id"]),
                        enable_phantoms=bool(_restored_phantoms_enabled),
                    )
                    # v3.16.36 — operator-reported 2026-05-06 that
                    # phantoms were still activating after restart
                    # despite the v3.16.27 fix. Inspection of the
                    # actual saved state file confirmed
                    # phantoms_enabled=False is correctly persisted;
                    # my v3.16.27 save/restore round-trip works. This
                    # post-restore diagnostic INFO log lets the
                    # operator verify directly in the activity log
                    # that the flag was honored at restore time. If
                    # the log shows False at restart but phantoms
                    # still appear active, the bug is downstream
                    # (GUI display, tick auto-start guard, or an
                    # unconfirmed override path) — the diagnostic
                    # narrows the search space.
                    logger.info(
                        "P0g-DIAG | bot=%s saved_phantoms_enabled=%s "
                        "constructed_with_enable_phantoms=%s "
                        "bot._phantoms_enabled=%s",
                        bid[:8],
                        _restored_phantoms_enabled,
                        bool(_restored_phantoms_enabled),
                        bot._phantoms_enabled,
                    )
                else:
                    # Defensive — should be unreachable because the
                    # mode-parsing step above already skips unknown
                    # modes via `continue`. Kept as a belt-and-braces
                    # guard so adding a new BotMode without a branch
                    # here is logged rather than silently broken.
                    logger.error(
                        "Bot %s mode %s (parsed from %r) has no "
                        "construction branch in "
                        "restore_bots_from_state — skipping. Add an "
                        "explicit branch for this BotMode value.",
                        bid,
                        mode,
                        _mode_str,
                    )
                    self._ledger_skip(bid, "no construction branch for mode")
                    continue
            except Exception as exc:
                logger.error(
                    "Bot %s construction failed during restore (%s) — "
                    "skipping. Other bots in the saved state will "
                    "still be restored. Platform launch continues.",
                    bid,
                    exc,
                )
                self._ledger_skip(bid, "construction failed")
                continue

            # Preserve original bot ID
            bot.bot_id = bid

            # Restore stats
            saved_stats = bot_data.get("stats", {})
            for key, val in saved_stats.items():
                if hasattr(bot.stats, key):
                    setattr(bot.stats, key, val)

            # MEM-245 — Restore scrumming compounding state (main_lots,
            # fold_tranches, accumulation scalars). Absence is safe
            # (bot starts fresh as before).
            # v3.20.4 — symmetric extractor branch restores
            # positions/chunk/hedge from extractor_state if present.
            # v3.24.35 (C01 PR-0) — did this bot's persisted state
            # actually load?
            #
            # The two branches below are the ONLY restore failures that
            # do not `continue`. Control falls through to register(), so
            # the bot ends up in self._bots holding DEFAULT state — and
            # because save_state rebuilds "bots" from the registered
            # set, the next 60s save writes those defaults over the good
            # persisted record. That is strictly worse than a skip: a
            # skipped bot is merely absent, this one actively overwrites.
            #
            # The old message said "(bot will start fresh)", which reads
            # as harmless. It is not: the record it would have started
            # from is destroyed one minute later.
            bot._state_import_failed = False
            if mode == BotMode.EXTRACTOR:
                ext_state = bot_data.get("extractor_state")
                if ext_state and hasattr(bot, "import_state"):
                    try:
                        bot.import_state(ext_state)
                        logger.info(
                            "Restored extractor state for %s: "
                            "%d position(s), chunk_free_base=%.6f, "
                            "hedge_free_base=%.6f, watch_list=%d",
                            bid,
                            len(getattr(bot, "_positions", {})),
                            getattr(bot, "_chunk_free_base", 0.0),
                            getattr(bot, "_hedge_free_base", 0.0),
                            len(getattr(bot, "_watch_list", [])),
                        )
                    except Exception as exc:
                        bot._state_import_failed = True
                        self._ledger_skip(bid, "extractor import_state failed")
                        logger.error(
                            "Extractor import_state FAILED on %s: %s. The "
                            "bot is registered with DEFAULT state, so the "
                            "next save would overwrite its persisted "
                            "record. Do not let that record be replaced.",
                            bid,
                            exc,
                        )
            else:
                scrum_state = bot_data.get("scrumming_state")
                if scrum_state and hasattr(bot, "import_scrumming_state"):
                    try:
                        bot.import_scrumming_state(scrum_state)
                        logger.info(
                            "Restored scrumming state for %s: "
                            "%d lot(s), %d tranche(s), target=$%.2f, "
                            "anchor=$%.2f, holdings=%.6f",
                            bid,
                            len(getattr(bot, "_main_lots", [])),
                            len(getattr(bot, "_fold_tranches", [])),
                            getattr(bot, "_target_balance", 0.0),
                            getattr(bot, "_anchor_target_balance", 0.0),
                            getattr(bot, "_current_holdings", 0.0),
                        )
                    except Exception as exc:
                        bot._state_import_failed = True
                        self._ledger_skip(bid, "import_scrumming_state failed")
                        # v3.24.48 (Phase 1 Step 5) — this used to log
                        # the hazard and then fall through to register()
                        # anyway, with DEFAULT state. The message below
                        # said "the next save would overwrite its
                        # persisted lots and tranches. Do not let that
                        # record be replaced" -- and then nothing stopped
                        # it. Sixty seconds after launch the save timer
                        # wrote 0 lots and 0 tranches over the good
                        # record. On the largest queue in the fleet that
                        # is ~200 tranches plus every lot's cost basis,
                        # destroyed by one malformed field.
                        #
                        # Skipping registration is what protects it. A
                        # bot absent from self._bots is absent from the
                        # dict save_state rebuilds, and state_manager's
                        # carry-forward keys on exactly that absence, so
                        # the on-disk record survives untouched.
                        #
                        # import_scrumming_state is NOT transactional --
                        # it applies fields sequentially -- so what is
                        # being protected is a PARTIALLY-applied record,
                        # not a cleanly zeroed one. That is the reason
                        # the in-memory object must not be trusted or
                        # saved from.
                        logger.error(
                            "import_scrumming_state FAILED on %s: %s. The "
                            "bot is NOT being registered this launch, so "
                            "its persisted lots and tranches are carried "
                            "forward intact rather than overwritten with "
                            "defaults. It will be ABSENT from the fleet "
                            "until the state record is repaired.",
                            bid,
                            exc,
                        )
                        # The bot vanishing from the fleet must never
                        # read as a silent deletion, so say so on the
                        # operator's own surface, not just in a log file.
                        try:
                            self._bus.emit(
                                "bot.restore_failed",
                                bot_id=bid,
                                symbol=getattr(config, "symbol", ""),
                                error=f"{type(exc).__name__}: {exc}",
                                message=(
                                    f"BOT NOT LOADED: {getattr(config, 'symbol', bid)} "
                                    f"({bid[:8]}) failed to restore its "
                                    f"saved state ({type(exc).__name__}: "
                                    f"{exc}). It is absent from the fleet "
                                    f"this launch. Its saved lots and "
                                    f"tranches are INTACT on disk and "
                                    f"were not overwritten. Repair the "
                                    f"record and relaunch."
                                ),
                            )
                        except Exception as _emit_exc:  # noqa: BLE001
                            logger.error(
                                "restore-failure banner could not be "
                                "emitted for %s (%s); the bot is missing "
                                "from the fleet with no operator-facing "
                                "notice",
                                bid,
                                _emit_exc,
                            )
                        continue

            # Mark as restored — stays IDLE until user starts
            bot.state = BotState.IDLE
            bot._restored = True
            # v3.16.11 — record whether this bot was running at the time
            # the saved state was captured. The auto-restart-after-launch
            # path (start_all with eligible_filter) uses this to decide
            # which bots to bring back online.
            bot._was_running = (
                str(bot_data.get("state_when_saved", "")).lower() == "running"
            )

            # v3.24.35 (C01 PR-0) — register() returns
            # (granted, refusal_reason) and its result was DISCARDED, so
            # a refused registration was still appended to `restored`.
            # That made it a sixth restore exit nobody had enumerated:
            # the bot is counted as restored, is absent from self._bots,
            # and is therefore absent from the list save_state rebuilds
            # "bots" from -- deleted by the next 60s save while the boot
            # report claimed success.
            _granted, _refusal = self.register(bot)
            if not _granted:
                logger.error(
                    "Bot %s REFUSED registration during restore (%s). Its "
                    "saved record is NOT loaded and must not be "
                    "overwritten.",
                    bid,
                    _refusal,
                )
                self._ledger_skip(bid, "registration refused")
                continue
            restored.append(bid)
            logger.info(
                "Restored bot %s (%s on %s) in IDLE state%s",
                bid,
                config.symbol,
                config.exchange_id,
                " (was RUNNING at save)" if bot._was_running else "",
            )

        # v3.24.35 (C01 PR-0) — restore reached its end.
        #
        # PR-1 requires this before any carry-forward decision: if a
        # restore ABORTED partway, the ledger is incomplete and absence
        # proves nothing, so a save must refuse rather than guess. The
        # flag distinguishes "no bots failed" from "we never finished
        # looking", which an empty ledger alone cannot.
        self._restore_completed = True
        if self._restore_ledger:
            logger.error(
                "C01: restore completed with %d bot(s) NOT loaded: %s. "
                "Their records are still on disk and will be DELETED by "
                "the next save (PR-0 is log-only).",
                len(self._restore_ledger),
                ", ".join(
                    f"{b} ({r})" for b, r in list(self._restore_ledger.items())[:8]
                ),
            )
        else:
            logger.info(
                "C01: restore completed, all %d persisted bot(s) loaded", len(bots_data)
            )

        return restored

    # -- Bulk operations ------------------------------------------------
    async def start_all(
        self,
        verify_timeout_seconds: float = 10.0,
        min_gap_seconds: float = 0.6,
        eligible_filter: Optional[Callable[["BotContainer"], bool]] = None,
    ) -> None:
        """v3.16.11 — VERIFY-THEN-NEXT staggered start. Operator directive
        2026-04-28 (clarification): "Should have a delay between bots hence
        staggered. One should start, be verified running, then the next
        one starts..."

        v3.23.86 — bumped defaults ~10-15% slower per operator directive
        2026-07-31 (avg ~3 initial start failures per boot):
          * ``verify_timeout_seconds`` 8.0 → 10.0 (25% more headroom for
            slow-handshake bots to reach RUNNING before we time out and
            move on).
          * ``min_gap_seconds`` 0.5 → 0.6 (20% larger cooldown between
            bots to space API-handshake bursts).
        Combined effect on a 35-bot boot: ~3.5s extra total, roughly
        10-15% slower depending on per-bot handshake variance.

        Each eligible bot starts; the loop polls `bot.state` until it
        reaches RUNNING (or `verify_timeout_seconds` elapses), then a
        small `min_gap_seconds` cooldown before the next bot starts.
        The fixed-delay v3.16.7 version was wrong — a slow-starting bot
        (network handshake / candle backfill) wouldn't have its
        verification reflected before the next one fired.

        Emits `bot_manager.start_all_progress` events:
          phase="begin"        — total + zero started
          phase="bot_starting" — bot.bot_id, count
          phase="bot_started"  — bot reached RUNNING (verified)
          phase="bot_timeout"  — verify_timeout elapsed; moving on anyway
          phase="cancelled"    — operator hit Cancel
          phase="done"         — all eligible bots processed

        Filter: by default, all bots in IDLE/STOPPED are eligible. Pass
        `eligible_filter=lambda b: b._was_running` to restart only bots
        whose `state_when_saved == "running"` (the auto-restart-after-
        crash scenario).
        """
        eligible = [
            b
            for b in self._bots.values()
            if b.state in (BotState.IDLE, BotState.STOPPED)
            and (eligible_filter is None or eligible_filter(b))
        ]
        total = len(eligible)
        self._start_all_cancel = False
        self._bus.emit(
            "bot_manager.start_all_progress", phase="begin", total=total, started=0
        )
        if total == 0:
            self._bus.emit(
                "bot_manager.start_all_progress", phase="done", total=0, started=0
            )
            return
        for i, bot in enumerate(eligible):
            if getattr(self, "_start_all_cancel", False):
                self._bus.emit(
                    "bot_manager.start_all_progress",
                    phase="cancelled",
                    total=total,
                    started=i,
                )
                return
            self._bus.emit(
                "bot_manager.start_all_progress",
                phase="bot_starting",
                total=total,
                started=i,
                bot_id=bot.bot_id,
            )
            await bot.start()
            # Verify-then-next: poll until state==RUNNING or timeout.
            verified = False
            poll_interval = 0.25
            elapsed = 0.0
            while elapsed < verify_timeout_seconds:
                if getattr(self, "_start_all_cancel", False):
                    break
                if bot.state == BotState.RUNNING:
                    verified = True
                    break
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
            if verified:
                self._bus.emit(
                    "bot_manager.start_all_progress",
                    phase="bot_started",
                    total=total,
                    started=i + 1,
                    bot_id=bot.bot_id,
                )
            else:
                # Timeout — proceed to next bot anyway. The slow bot
                # may still come up; the operator can see the timeout
                # event and decide.
                self._bus.emit(
                    "bot_manager.start_all_progress",
                    phase="bot_timeout",
                    total=total,
                    started=i + 1,
                    bot_id=bot.bot_id,
                    timeout_seconds=verify_timeout_seconds,
                )
            # Small cooldown before next bot to space out exchange-API
            # bursts (each bot does its own handshake during start).
            if i < len(eligible) - 1:
                await asyncio.sleep(min_gap_seconds)
        self._bus.emit(
            "bot_manager.start_all_progress", phase="done", total=total, started=total
        )

    def cancel_start_all(self) -> None:
        """Operator-callable: abort an in-flight start_all. The current
        bot finishes its start; subsequent bots are skipped."""
        self._start_all_cancel = True

    async def stop_all(self) -> None:
        tasks = [bot.stop() for bot in self._bots.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def pause_all(self) -> None:
        for bot in self._bots.values():
            if bot.state == BotState.RUNNING:
                await bot.pause()

    async def resume_all(self) -> None:
        for bot in self._bots.values():
            if bot.state == BotState.PAUSED:
                await bot.resume()

    # -- Aggregated stats for main window ------------------------------
    def get_aggregate_stats(self) -> dict:
        """Compute totals across all bots for the main dashboard.

        v3.15.50 — adds total_scrummed_usd + total_folded_usd as
        platform high-score counters per operator directive
        2026-04-24: "How about display total scrummed and total
        folded. Like two high scores for the platform run. Just add
        it all up from all running bots."
        """
        total_pnl = 0.0
        total_trades = 0
        running = 0
        errored = 0
        total_scrummed = 0.0
        total_folded = 0.0
        # v3.23.60 — YTD scrum/fold totals pulled from exchange fills
        # (see ScrummingBot.sync_ytd_trade_count). When any bot has
        # exchange_data_fresh_ts > 0 the dashboard prefers this over
        # the platform-run accumulator; the two run in parallel so
        # bots that haven't yet completed a sync still contribute
        # via the lifetime counters.
        total_scrummed_ytd = 0.0
        total_folded_ytd = 0.0
        total_errors_lifetime = 0  # v3.16.46 — cumulative across all bots
        # v3.16.46 — exchange-pulled aggregates (realized P/L from
        # actual trade history, fees paid, etc.). When all bots have
        # refreshed at least once, this represents Coinbase-truth
        # values vs the synthetic stats.realised_pnl accumulator.
        total_realized_exchange = 0.0
        total_unrealized_exchange = 0.0
        total_fees_exchange = 0.0
        bots_with_fresh_exchange_data = 0
        # v3.16.48 — wallet cash + crypto position aggregates pulled
        # from exchange. Operator directive: "Pull the data and
        # display it. Spendable balance is my cash."
        wallet_cash_usd = 0.0  # max across bots (shared wallet)
        crypto_position_value_usd = 0.0  # sum of per-bot position values

        for bot in self._bots.values():
            total_pnl += bot.stats.realised_pnl
            total_trades += bot.stats.total_trades
            total_scrummed += float(
                getattr(bot.stats, "total_scrummed_usd", 0.0) or 0.0
            )
            total_folded += float(getattr(bot.stats, "total_folded_usd", 0.0) or 0.0)
            # v3.23.60 — YTD from exchange sync
            total_scrummed_ytd += float(
                getattr(bot.stats, "ytd_scrummed_usd", 0.0) or 0.0
            )
            total_folded_ytd += float(getattr(bot.stats, "ytd_folded_usd", 0.0) or 0.0)
            total_errors_lifetime += int(getattr(bot.stats, "total_errors", 0) or 0)
            # v3.16.46 — exchange-pulled aggregates
            _re = float(getattr(bot.stats, "realized_pnl_exchange", 0.0) or 0.0)
            _ue = float(getattr(bot.stats, "unrealised_pnl", 0.0) or 0.0)
            _fe = float(getattr(bot.stats, "fees_paid_exchange", 0.0) or 0.0)
            _fresh_ts = float(getattr(bot.stats, "exchange_data_fresh_ts", 0.0) or 0.0)
            total_realized_exchange += _re
            total_unrealized_exchange += _ue
            total_fees_exchange += _fe
            if _fresh_ts > 0:
                bots_with_fresh_exchange_data += 1
            # v3.16.48 — wallet cash: shared across bots, take max
            # (freshest non-zero value wins). Crypto position: sum
            # per-bot position values (each bot owns its own asset).
            _bot_cash = float(getattr(bot.stats, "cash_balance_usd", 0.0) or 0.0)
            if _bot_cash > wallet_cash_usd:
                wallet_cash_usd = _bot_cash
            # v3.24.55 — recompute rather than trusting the cached
            # field, matching what the Ammo cell and the manual-fire
            # engine both already do.
            #
            # `stats.position_value` and `stats.current_price` are
            # written at different moments in the tick, so the cached
            # product lags whenever price moved after the last write.
            # Measured 2026-08-06 by
            # tools/harness/reconcile_position_values.py: 11 of 35 bots
            # diverged more than 1% from holdings x price, worst
            # ORCA/USD at 11.53%, and the fleet total understated the
            # position by $35.46 against $3,317.16.
            #
            # C10 fixed this for the per-bot Ammo and
            # scrumming_bot.py:9246 was already correct for manual fire.
            # This was the last consumer still summing the stale value,
            # and it is the one the headline portfolio figure is built
            # from.
            _bot_pos_val = float(getattr(bot.stats, "position_value", 0.0) or 0.0)
            try:
                _h = float(getattr(bot, "_current_holdings", 0.0) or 0.0)
                _p = float(getattr(bot.stats, "current_price", 0.0) or 0.0)
                _q = float(getattr(bot, "_quote_to_usd", 1.0) or 1.0)
                if _h > 0 and _p > 0:
                    # Both inputs present: the recomputed value is the
                    # fresher of the two by construction. Falls through
                    # to the cached value otherwise rather than
                    # reporting $0 for a real position -- an empty
                    # portfolio is a worse lie than a slightly stale one.
                    _bot_pos_val = _h * _p * _q
            except Exception as _pv_exc:  # noqa: BLE001 - aggregate must not raise
                logger.debug(
                    "aggregate: position recompute failed for %s (%s); "
                    "using the cached value",
                    getattr(bot, "bot_id", "?"),
                    _pv_exc,
                )
            crypto_position_value_usd += _bot_pos_val
            if bot.state == BotState.RUNNING:
                running += 1
            if bot.state == BotState.ERROR:
                errored += 1

        return {
            "total_bots": len(self._bots),
            "running": running,
            "errored": errored,  # CURRENT-state bots in ERROR
            "total_errors_lifetime": total_errors_lifetime,  # CUMULATIVE error count
            # v3.16.46 — exchange-pulled position health aggregates
            "total_realized_exchange": round(total_realized_exchange, 4),
            "total_unrealized_exchange": round(total_unrealized_exchange, 4),
            "total_fees_exchange": round(total_fees_exchange, 4),
            "bots_with_fresh_exchange_data": bots_with_fresh_exchange_data,
            # v3.16.48 — direct exchange-pulled wallet cash + crypto
            # value. These are the values the SpendableWidget displays
            # (replacing the prior synthetic computation).
            "wallet_cash_usd": round(wallet_cash_usd, 4),
            "crypto_position_value_usd": round(crypto_position_value_usd, 4),
            "total_account_value_usd": round(
                wallet_cash_usd + crypto_position_value_usd, 4
            ),
            "total_realised_pnl": round(total_pnl, 4),
            "total_trades": total_trades,
            # v3.23.60 — dashboard prefers the YTD sums when any bot
            # has completed a sync (>0). Falls back to the platform-
            # run accumulators otherwise so fresh installs / new
            # bots aren't blank.
            "total_scrummed_usd": round(
                total_scrummed_ytd if total_scrummed_ytd > 0 else total_scrummed, 4
            ),
            "total_folded_usd": round(
                total_folded_ytd if total_folded_ytd > 0 else total_folded, 4
            ),
            # Also expose raw YTD + lifetime separately for callers
            # that want to distinguish them.
            "total_scrummed_usd_ytd": round(total_scrummed_ytd, 4),
            "total_folded_usd_ytd": round(total_folded_ytd, 4),
            "total_scrummed_usd_lifetime": round(total_scrummed, 4),
            "total_folded_usd_lifetime": round(total_folded, 4),
        }


class _PlaceholderExchangeForRestore:
    """Minimal placeholder used during state restore. Replaced on bot start."""

    def __init__(self, exchange_id: str):
        self.exchange_id = exchange_id
        self.display_name = exchange_id.capitalize()
        self.is_connected = False
