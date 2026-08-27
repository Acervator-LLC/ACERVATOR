"""Configuration data for bots: modes, states, the BotConfig dataclass and its factory.

Leaf module: imports nothing from the trading package, so the container
mixins can depend on it without an import cycle through bot_container.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

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
#: The Stack Mode value a bot takes when NOTHING is stored for it.
#: Issue #133 unit 8: ON. Every read of an absent `stack_mode`
#: resolves here, so the declared default and the value a bot gets
#: cannot drift. `get_full_state` persists `asdict(self.config)`,
#: so a bot that has been saved once carries its own value and
#: never reaches this line again -- all 38 bots in the operator's
#: bot_state.json store False and keep it.
STACK_MODE_DEFAULT: bool = True


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
    # docs/engineering-notes/2026-08-09_position_attribution_shared_account_research.md
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
    stack_mode: bool = STACK_MODE_DEFAULT
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
    # (per docs/engineering-notes/2026-07-27_interop_usd_denom_settlement_audit_and_design.md
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
                    "Scrumming config has target_asset='*' (the "
                    "Extractor pool sigil); Scrumming is "
                    "single-pair and needs a real ticker."
                )
            if not self.target_asset:
                violations.append(
                    "Scrumming config has empty target_asset; "
                    "needs a real ticker (e.g. 'BTC')."
                )
            if not self.base_currency:
                violations.append(
                    "Scrumming config has empty base_currency; "
                    "needs a real quote currency (e.g. 'USDC')."
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
# practice, so dropping the key loses no setting -- there was only
# ever one value to carry. A file that carried it takes
# STACK_MODE_DEFAULT like any other file with no stored value.
# bulk_partial_on_return was declared but never read.
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


#: The candidate windows the Fold Tranches panel offers when the timer
#: is OFF, so the operator reads a CONSEQUENCE instead of a blank.
#:
#: MEASURED, NOT PICKED. Against the operator's own state file of
#: 2026-08-24 (read-only, 38 bots, 1,680 open fold tranches, every one
#: carrying a usable `created_ts`) the age distribution is:
#:
#:     >=  7 d   343 tranches   20.4 %
#:     >= 14 d   209 tranches   12.4 %
#:     >= 30 d    80 tranches    4.8 %
#:     >= 60 d    19 tranches    1.1 %
#:     >= 90 d     0 tranches    0.0 %
#:
#: Four windows that each move the number, and the last one that is not
#: yet zero. A fifth at 90 days would print 0 on every bot in the fleet
#: and teach the operator nothing.
DESPAWN_PREVIEW_WINDOWS: tuple[int, ...] = (7, 14, 30, 60)


def _despawn_age_seconds(tranche: object, field: str, now: float) -> Optional[float]:
    """Give the age of one tranche in seconds, or None when it has none.

    THE SAME RULE THE SWEEP APPLIES, and the reasoning is
    `ScrummingBot._tranche_age_seconds`'s: `as_finite_float` admits
    exactly int or float and finite, so a stored `True` is not read as
    one second past the epoch; a non-positive stamp is not a time and
    means "unset"; and None is an answer, not an error — the record has
    no measurable age and nothing may be concluded about it.

    Args:
      tranche: one fold or stack tranche record.
      field: `created_ts` on the fold side, `opened_ts` on the stack
        side. Each ledger ages on its own field.
      now: the wall-clock second to measure against.

    Returns:
      Age in seconds, negative for a future-dated stamp, or None.
    """
    if not isinstance(tranche, dict):
        return None
    _ts = as_finite_float(tranche.get(field))
    if _ts is None or _ts <= 0:
        return None
    return now - _ts


def _despawn_preview_fold(fold: list, cutoff: float, now: float, report: dict) -> None:
    """Count the fold ledger into `report`. Removes nothing.

    Split out of `despawn_preview` so each ledger's rule is read on its
    own. The fold side has ONE refusal — an ageless record — and no
    live-order case, because a fold tranche owns no exchange order.
    """
    for _t in fold:
        _age = _despawn_age_seconds(_t, "created_ts", now)
        if _age is None:
            report["ageless_kept"] += 1
            continue
        if _age < cutoff:
            continue
        report["fold_removed"] += 1
        _usd = as_finite_float(_t.get("usd", 0))
        if _usd is not None:
            report["usd_removed"] += _usd
        _units = as_finite_float(_t.get("units", 0))
        if _units is not None:
            report["units_removed"] += _units


def _despawn_preview_stack(
    stack: list, cutoff: float, now: float, report: dict
) -> None:
    """Count the stack ledger into `report`. Removes nothing.

    THE ONE ASYMMETRY WITH THE FOLD SIDE, and it is a refusal rather
    than a second policy. A Visible-mode stack tranche that is
    `status == "pending"` with an `order_id` holds a resting LIMIT
    order on the exchange. Removing that record would leave a live
    order on the book with nothing tracking it, so it is KEPT and
    counted apart. Invisible-mode tranches carry `order_id=None`, and
    filled or cancelled orders are already terminal; those are removed
    like any other record.
    """
    for _t in stack:
        _age = _despawn_age_seconds(_t, "opened_ts", now)
        if _age is None:
            report["ageless_kept"] += 1
        elif _age < cutoff:
            continue
        elif _t.get("status") == "pending" and _t.get("order_id"):
            report["stack_kept_live_order"] += 1
        else:
            report["stack_removed"] += 1


def despawn_preview(
    fold_tranches: Optional[list],
    stack_tranches: Optional[list],
    days: object,
    now: object,
) -> dict:
    """Report what a despawn sweep at `days` WOULD remove. Removes nothing.

    WHY THIS EXISTS. Item 9 shipped the despawn timer on 2026-08-13 and
    it works. It is 0 — Off — on all 38 bots, and it has never run
    once. The setting sits on the Settings tab while the tranche count
    the operator worries about sits on the Fold Tranches tab, and
    nothing anywhere said what turning it on would cost. A control that
    names no consequence is a control nobody moves. This function is
    the consequence, computed on the panel where the problem is already
    on screen.

    IT REMOVES NOTHING AND WRITES NOTHING. It reads two lists and
    returns numbers. The lists are not copied into the bot, sorted or
    mutated, and no counter, aggregate or config field is touched.
    Passing a bot's real ledgers to it is safe by construction.

    THE PREDICATE IS THE SWEEP'S PREDICATE, TERM FOR TERM:

      * fold tranches age on `created_ts`, stack tranches on
        `opened_ts`;
      * the boundary is INCLUSIVE — `age >= days` is old enough;
      * a tranche with no measurable age is NEVER counted for removal,
        it is counted as `ageless_kept`;
      * a stack tranche holding a resting exchange order is KEPT and
        counted as `stack_kept_live_order`;
      * `days <= 0` is OFF and removes nothing.

    THE TWO IMPLEMENTATIONS ARE BOUND BY A TEST, NOT BY A COMMENT.
    `ScrummingBot._despawn_aged_tranches` cannot call this function
    today: that method lives in a file another unit holds open, and
    `bot_container` is imported BY `scrumming_bot`, so the dependency
    runs one way only. Two implementations that agree today drift the
    next time either moves — that is exactly how the Min-rebuy column
    came to print a price the executor refuses.
    `tests/test_despawn_window_is_usable.py` therefore drives the
    SHIPPED sweep and this preview over the same fixture and asserts
    they agree on every count, so a change to either one that breaks
    the agreement fails. Re-pointing the sweep at this function is one
    line and belongs to whoever next holds `scrumming_bot.py`.

    `units_removed` HAS NO COUNTERPART IN THE SWEEP'S REPORT, and it is
    the panel's reason for calling this at all: the operator's question
    is what the removal costs, and the sweep reports only USD. It is
    additional information about the same records, not a second opinion
    about which records go.

    Args:
      fold_tranches: this bot's fold ledger, or None.
      stack_tranches: this bot's stack ledger, or None.
      days: whole days, as `despawn_threshold_days` returns them, or a
        candidate window the operator has not committed to. Anything
        that is not a finite number reads as OFF.
      now: the wall-clock second to age against. Anything that is not a
        finite number makes every age unmeasurable, so the preview
        reports nothing removable — the same refusal the sweep makes.

    Returns:
      A dict of counts. `fold_removed` + `stack_removed` is what a
      sweep at `days` would take; `usd_removed` and `units_removed`
      are what those records held.
    """
    _fold = list(fold_tranches or [])
    _stack = list(stack_tranches or [])
    report = {
        "threshold_days": 0,
        "fold_open": len(_fold),
        "stack_open": len(_stack),
        "fold_removed": 0,
        "stack_removed": 0,
        "stack_kept_live_order": 0,
        "ageless_kept": 0,
        "usd_removed": 0.0,
        "units_removed": 0.0,
    }
    _days = as_finite_float(days)
    if _days is None:
        return report
    _days = min(DESPAWN_MAX_DAYS, max(0, int(_days)))
    report["threshold_days"] = _days
    if _days <= 0:
        return report
    _now = as_finite_float(now)
    if _now is None:
        return report
    _cutoff = _days * 86400.0
    _despawn_preview_fold(_fold, _cutoff, _now, report)
    _despawn_preview_stack(_stack, _cutoff, _now, report)
    return report


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
