"""Configuration data for bots: modes, states, the BotConfig dataclass and its factory.

Leaf module: imports nothing from the trading package, so the container
mixins can depend on it without an import cycle through bot_container.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# DOLLAR_PEGGED_CURRENCIES price at exactly 1.0 USD when no market price is available.
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
    SCRUMMING = "scrumming"
    EXTRACTOR = "extractor"


# ---------------------------------------------------------------------------
# Bot configuration
# ---------------------------------------------------------------------------
#: Stack Mode value used only when a bot has no stored `stack_mode`.
STACK_MODE_DEFAULT: bool = True


@dataclass
class BotConfig:
    """Immutable configuration snapshot for a bot instance."""

    exchange_id: str
    base_currency: str  # e.g. "USDT"
    target_asset: str  # e.g. "BTC"
    symbol: str = ""  # Derived: "BTC/USDT"
    mode: BotMode = BotMode.SCRUMMING

    # --- Sizing ---
    investment_amount: float = 200.0  # Total bot capital
    increment_style: str = "linear"  # "linear" or "logarithmic"
    spacing_style: str = (
        "expanding"  # "expanding" (wider gaps) or "stacked" (fixed gap)
    )

    # Profit folding flag (engine-consulted)
    profit_folding_active: bool = True

    # --- Scrumming-specific ---
    target_balance: float = 200.0  # Balance the bot trades relative to
    # Caps USD adopted from an existing exchange balance; 0.0 uses target_balance.
    max_adoptable_usd: float = 0.0
    scrumming_interval_pct: float = 1.0  # % market move between actions

    # Scrumming: Profit routing (where excess delta goes after sell)
    profit_route: str = (
        "fold_to_target"  # "fold_to_target" | "spendable" | "split" | "cross_bot"
    )
    profit_route_bot_id: str = ""  # Target bot ID for cross-bot routing

    scrum_fold_pct: int = 100  # 1-100: % of scrum proceeds queued for fold

    # Read via despawn_threshold_days() below, never raw; 0 = off.
    tranche_despawn_days: int = 0  # 0 = off; else delist at >= N days

    # Caps per-cycle target_balance growth as % of the cycle's anchor; consulted live.
    max_target_growth_pct: float = 1.0  # 1-100: cap on target growth per cycle as %

    # Scrumming: Bollinger Band proximity settings
    bb_tolerance_pct: float = 1.0  # 0.25% to 5% tolerance for BB proximity
    bb_landing_strip_candles: int = (
        3  # Min consecutive tight HA candles for landing strip
    )
    ta_timeframe: str = "1h"  # Timeframe for TA indicator calculations

    # Scrumming: advanced signal & risk parameters
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

    # Soft = time-delay interrupt; Hard = pause requiring operator reset.
    # Move measured as (high - low) / open x 100; direction from close vs open.
    circuit_breaker_soft_pct: float = 25.0  # Soft trip threshold (default 25%)
    circuit_breaker_hard_pct: float = 35.0  # Hard trip threshold (default 35%)
    circuit_breaker_cooldown_candles: int = 3  # Candles to wait before soft re-opens

    # 0 disables; otherwise triggers a rebalance once |delta| >= target_balance x
    # pct/100.
    max_cartridge_size_pct: float = 10.0

    # When True, threshold derives from BB range, clamped between scrumming_interval_pct
    # and max_cartridge_smart_ceiling_pct; when False, max_cartridge_size_pct applies.
    max_cartridge_smart: bool = False
    max_cartridge_smart_ceiling_pct: float = 30.0

    # Wire income buys target asset instead of parking, when |position-target| and
    # price-vs-entry both fall within this %; 0 disables.
    wire_inflow_stack_pct: float = 1.0

    # SCRUM-side (sell at top):
    scrum_require_ta_bullish: bool = True  # Requires is_bullish for auto-scrum
    scrum_hold_in_uptrend: bool = (
        True  # trend_hold blocks scrum during sustained uptrend
    )
    scrum_defer_to_htf: bool = True  # Refuses scrum when higher-TF phantom is BULLISH
    # FOLD-side (buy at bottom, mirror semantics):
    fold_require_ta_bearish: bool = True  # Requires is_bearish for auto-fold
    fold_hold_in_downtrend: bool = (
        True  # trend_hold blocks fold during sustained downtrend
    )
    fold_defer_to_htf: bool = True  # Refuses fold when higher-TF phantom is BEARISH

    # --- Both modes ---
    visibility: str = "orderbook"  # "orderbook" or "internal"
    # Forces engine-initiated trades to execute as IOC-limit taker orders;
    # Manual Fire is unaffected.
    aggressive_trading: bool = False

    # Splits a SCRUM sell across upward price levels; first tranche sits
    # (scrumming_interval_pct + trading_fee_pct) above the trigger price.
    # Later tranches space by stack_spacing_mode at split_distance intervals.
    # visibility="orderbook" rests LIMIT SELL orders on the exchange; "internal"
    # tracks internally and market-sells each tranche as price crosses.
    stack_mode: bool = STACK_MODE_DEFAULT
    # Percent spacing between tranches, scaled by stack_spacing_mode.
    split_distance: float = 1.0
    # Target level count; actual count may drop for exchange min-order-size or
    # 0.1% merge.
    stack_tranche_count_target: int = 3
    # Cumulative distance from anchor in units of split_distance: "linear" n -> 1,2,3,4;
    # "quadratic" n^2 -> 1,4,9,16; "exponential" 2^(n-1) -> 1,2,4,8.
    stack_spacing_mode: str = "linear"

    # max_entry_price refuses auto-buy above it, min_entry_price below it;
    # None means no bound.
    # Manual Fire bypasses both; fold rebuy and hedge buy respect both.
    max_entry_price: Optional[float] = None
    min_entry_price: Optional[float] = None

    # Effective hysteresis deviation = scrumming_interval_pct + trading_fee_pct;
    # default 0.6 = Coinbase max tier.
    trading_fee_pct: float = 0.6

    # position_ceiling_enabled caps accumulation at position_ceiling_multiple x the
    # anchor target_balance.
    # Fold interval tapers 100%->10% as the ratio runs 0.5->1.0, hard-stopping at 1.0.
    # Scrum is unaffected; only fold is capped and eventually stopped.
    position_ceiling_enabled: bool = False
    position_ceiling_multiple: float = 5.0  # Range [1.0, 10.0], default 5x
    # detonation_enabled watches detonation_timeframe for a BULLISH reversal at or
    # above detonation_confidence_min.
    # On detection it market-sells everything above the anchor and resets
    # target_balance to it.
    # Edge-triggered: it detonates once per reversal, not every tick while
    # BULLISH holds.
    detonation_enabled: bool = False
    detonation_timeframe: str = "1d"  # "1d", "1w"
    detonation_confidence_min: float = (
        0.75  # BULLISH confidence threshold; operator-adjustable 0.50-1.00
    )

    # Registers target-balance-worth of the target asset in CapitalReservationRegistry
    # so other bots don't claim the same coins.
    self_reserve_capital: bool = True
    # Target-asset units held out of the bot's decision math and reservation.
    personal_hold_qty: float = 0.0

    # Extractor Bot (mode == EXTRACTOR) anchors to a base-asset pool and sends
    # chunks into volatile ALT pairs to grow it; ExtractorBots spawn no child bots.
    # Pair selection scans top-N */<base> pairs by 24h volume every
    # extractor_scan_refresh_candles ticks.
    #
    # extractor_direction "normal" buys alt first for more base; "inverted" sells alt
    # first for the quote currency, buying back more alt.
    extractor_direction: str = "normal"
    # Operator-entered ALT quantity reserved at startup for the inverted direction.
    inverted_extractor_standing_alt_units: float = 0.0
    extractor_chunk_size_usd: float = 100.0
    # USD-equivalent base currency owned; converted to base units at creation, then
    # tracked in base units.
    extractor_artillery_size_usd: float = 5.0
    # Top-N */<base> pairs by 24h volume kept on the watch list.
    extractor_scan_top_n: int = 8
    # Re-ranks the top-N every N ticks.
    extractor_scan_refresh_candles: int = 60
    # % of the chunk kept free; a new round needs (chunk_free - artillery_size)
    # >= reserve.
    extractor_pool_reserve_pct: float = 50.0
    # % of the alt position sold on a bullish trigger; 100 is a full exit.
    extractor_exit_pct: float = 100.0
    # USD drawdown threshold below which averaging-down may trigger.
    extractor_drawdown_threshold_pct: float = 3.0
    # Minimum candles between consecutive averaging-down rounds on the same position.
    extractor_correction_skip_candles: int = 4
    # Cost basis of a position cannot exceed this multiple of the original
    # artillery_size.
    extractor_max_cost_basis_multiple: float = 2.0
    # Per-position tier counter capped at extractor_max_compounding_tier; realized
    # gain always credits chunk_free_base.
    extractor_max_compounding_tier: int = 3
    # Separate base-currency reserve for averaging-down; 0 draws from
    # chunk_free instead.
    extractor_hedge_budget_usd: float = 0.0
    # Trend-hold threshold for the per-symbol TASignalProvider.
    extractor_trend_strength_threshold: float = 0.65

    # Empty list: auto-pick top-N */<base> pairs via extractor_scan_top_n.
    # Non-empty: trade exactly these symbols, set from the wizard's pool picker.
    extractor_alt_targets: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.symbol:
            if self.mode == BotMode.EXTRACTOR:
                # Pool sigil; not a tradeable exchange symbol on its own.
                self.symbol = f"*/{self.base_currency}"
            else:
                self.symbol = f"{self.target_asset}/{self.base_currency}"

    def validate_mode_shape(self) -> list:
        """Return mode-shape violations as human-readable strings.

        Empty list means the config matches its mode. Extractor requires
        target_asset == "*" and extractor_chunk_size_usd > 0. Scrumming
        requires target_asset != "*", and both target_asset and
        base_currency non-empty.
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
# BotConfig field manifests + typed factory
# ---------------------------------------------------------------------------
# These sets mark which fields are valid per mode; make_bot_config() raises
# on a foreign field.

#: Fields valid for either mode's make_bot_config(...) call, unmodified.
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
        "stack_mode",
        "split_distance",
        "stack_tranche_count_target",
        "stack_spacing_mode",
        "max_entry_price",
        "min_entry_price",
    }
)

#: Fields meaningful only for ScrummingBot; make_bot_config(mode=EXTRACTOR, ...)
#: raises ValueError if any of these is passed.
_BOT_CONFIG_SCRUMMING_ONLY_FIELDS: frozenset = frozenset(
    {
        "investment_amount",
        "increment_style",
        "spacing_style",
        "profit_folding_active",
        # Scrumming-specific accumulation/routing
        "scrumming_interval_pct",
        "profit_route",
        "profit_route_bot_id",
        "scrum_fold_pct",
        "max_target_growth_pct",
        # The two ledgers this sweeps only exist on ScrummingBot.
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
        # strategy toggle fields
        "scrum_require_ta_bullish",
        "scrum_hold_in_uptrend",
        "scrum_defer_to_htf",
        "fold_require_ta_bearish",
        "fold_hold_in_downtrend",
        "fold_defer_to_htf",
        # risk-control fields
        "position_ceiling_enabled",
        "position_ceiling_multiple",
        "detonation_enabled",
        "detonation_timeframe",
        "detonation_confidence_min",
        # interop fields
        "self_reserve_capital",
        "personal_hold_qty",
    }
)

#: Fields meaningful only for ExtractorBot; make_bot_config(mode=SCRUMMING, ...)
#: raises ValueError if any of these is passed.
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
        "extractor_direction",
        "inverted_extractor_standing_alt_units",
    }
)


#: Keys `_sanitize_deprecated_kwargs()` drops before BotConfig.__init__, so an
#: older bot_state.json with these keys does not raise TypeError on load.
_DEPRECATED_KWARGS: frozenset = frozenset(
    {
        "bulk_trading",  # renamed to stack_mode; historically always False
        "bulk_partial_on_return",  # retired; never had a runtime consumer
        "market_check_interval",  # retired; never had a runtime consumer
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


#: Bound for as_finite_float's int branch; 2**1023 is under the float max, so
#: comparing does not risk OverflowError.
_FLOAT_SAFE_INT: int = 2**1023

#: Days-to-seconds saturation cap (10,000 years); prevents days * 86400.0 from
#: raising OverflowError on a corrupted value.
DESPAWN_MAX_DAYS: int = 3_650_000


def as_finite_float(value) -> Optional[float]:
    """Return `value` as a float when it is exactly int or float and finite;
    None for everything else.

    Uses exact type, not isinstance, so a bool (a subclass of int) is not
    accepted. An int outside +/-2**1023 is also refused rather than
    overflowed into `float()`.

    Args:
      value: anything, including a value read from a JSON-decoded state file.

    Returns:
      The finite float, or None when `value` is not a usable number.
    """
    if type(value) is float:
        return value if math.isfinite(value) else None
    if type(value) is int and -_FLOAT_SAFE_INT <= value <= _FLOAT_SAFE_INT:
        return float(value)
    return None


def despawn_threshold_days(config) -> int:
    """Return the tranche despawn threshold in whole days; 0 means OFF.

    Reads `config.tranche_despawn_days`.
    `ScrummingBot._despawn_aged_tranches` and the live-settings spinbox both
    read through this function, so a stored value means the same thing to
    the sweep and to the spinbox that sets it. A non-numeric, non-finite, or
    negative setting reads as OFF. The value truncates toward zero and
    saturates at DESPAWN_MAX_DAYS; it is not clamped to the spinbox's 0-365
    display range.

    Args:
      config: any object; the field is read with `getattr`, so a config
        predating it reads as OFF.

    Returns:
      Whole days in [0, DESPAWN_MAX_DAYS]. 0 means the timer is off.
    """
    days = as_finite_float(getattr(config, "tranche_despawn_days", 0))
    if days is None:
        return 0
    return min(DESPAWN_MAX_DAYS, max(0, int(days)))


#: Candidate windows the Fold Tranches panel offers when the timer is OFF,
#: so the operator reads a consequence instead of a blank.
DESPAWN_PREVIEW_WINDOWS: tuple[int, ...] = (7, 14, 30, 60)


def _despawn_age_seconds(tranche: object, field: str, now: float) -> Optional[float]:
    """Return one tranche's age in seconds, or None when it has no usable timestamp.

    Uses `as_finite_float` so a stored bool is not read as a timestamp and a
    non-positive stamp reads as unset. Mirrors
    `ScrummingBot._tranche_age_seconds`.

    Args:
      tranche: one fold or stack tranche record.
      field: `created_ts` on the fold side, `opened_ts` on the stack side.
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
    """Count the fold ledger into `report` by age against `cutoff`; removes nothing.

    An ageless record counts as `ageless_kept`, never as removable.
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
    """Count the stack ledger into `report` by age against `cutoff`; removes nothing.

    A pending tranche holding a live exchange order counts as
    `stack_kept_live_order` instead of removable, since despawning it would
    leave an untracked resting order.
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
    """Report what a despawn sweep at `days` would remove; mutates nothing.

    Reads `fold_tranches` and `stack_tranches` without changing either list
    or any bot state. Applies the same predicate as
    `ScrummingBot._despawn_aged_tranches`: age
    >= days is removable, an ageless record is kept, and a stack tranche
    holding a live exchange order is kept.
    `tests/test_despawn_window_is_usable.py` asserts the two
    implementations agree on every count.

    Args:
      fold_tranches: this bot's fold ledger, or None.
      stack_tranches: this bot's stack ledger, or None.
      days: whole days, or a candidate window; anything not a finite number
        reads as OFF.
      now: the wall-clock second to age against; anything not finite
        reports nothing removable.

    Returns:
      A dict of counts: `fold_removed` + `stack_removed` is what a sweep at
      `days` would take; `usd_removed` and `units_removed` are what those
      records held.
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
    """Return `kwargs` with deprecated keys dropped and legacy values normalized.

    Drops every key in `_DEPRECATED_KWARGS` and promotes
    `stack_spacing_mode="logarithmic"` to `"quadratic"`. Callers must pass
    the returned dict, not the original, to BotConfig.__init__ or
    make_bot_config.
    """
    out = {k: v for k, v in kwargs.items() if k not in _DEPRECATED_KWARGS}
    if out.get("stack_spacing_mode") == "logarithmic":
        out["stack_spacing_mode"] = "quadratic"
    return out


def make_bot_config(mode, **kwargs) -> BotConfig:
    """Construct and validate a BotConfig for `mode`; the canonical build path.

    Raises before construction if any kwarg is foreign to `mode`
    (Scrumming-only fields under EXTRACTOR, or the reverse). Applies the
    mode-aware `target_asset` default when the caller omits it (Extractor:
    "*"; Scrumming: "BTC"), then re-raises any violation
    `validate_mode_shape()` reports on the constructed instance.

    Args:
        mode: BotMode.EXTRACTOR or BotMode.SCRUMMING.
        **kwargs: BotConfig dataclass field values.

    Raises:
        TypeError: `mode` is not a BotMode.
        ValueError: a mode-foreign kwarg, or a validate_mode_shape
            violation surviving construction.

    Returns:
        A BotConfig instance with mode set and shape validated.
    """
    if not isinstance(mode, BotMode):
        raise TypeError(
            f"make_bot_config(): mode must be BotMode enum, got "
            f"{type(mode).__name__}={mode!r}"
        )

    kwargs = _sanitize_deprecated_kwargs(kwargs)

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

    if "target_asset" not in kwargs:
        kwargs["target_asset"] = "*" if mode == BotMode.EXTRACTOR else "BTC"

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
    # Fold tranches discarded by an operator clear, never folded; kept apart
    # from any "closed" counter.
    # See ScrummingBot.clear_fold_tranches.
    tranches_discarded_lifetime: int = 0
    # USD of parked wire credit released by an operator clear; an earmark,
    # not moved funds.
    wire_credits_discarded_lifetime: float = 0.0
    extended_positions_created: int = 0
    consecutive_errors: int = 0
    last_error: str = ""
    last_trade_time: float = 0.0
    uptime_seconds: float = 0.0
    # Order-verification sample counters (clean / adjusted / canceled / total).
    verify_clean: int = 0
    verify_adjusted: int = 0
    verify_canceled: int = 0
    verify_samples: int = 0
    # Per-bot SCRUM (sell) and FOLD (buy) USD; the header sums these across
    # all running bots.
    total_scrummed_usd: float = 0.0
    total_folded_usd: float = 0.0
    # YTD USD totals since YTD_TRADE_ANCHOR_UTC (2026-04-01), pulled via
    # sync_ytd_trade_count.
    # Dashboard prefers these over the platform-run accumulators once
    # exchange_data_fresh_ts > 0.
    ytd_scrummed_usd: float = 0.0
    ytd_folded_usd: float = 0.0
    # Never resets, unlike consecutive_errors (clears on success) and the
    # header's "Errors" stat (only bots CURRENTLY in ERROR).
    total_errors: int = 0
    # Refreshed by the tick loop via the connector's get_my_trades and
    # position_health; exchange-truth values, not the synthetic realised_pnl
    # / unrealised_pnl accumulators.
    # 0 means not yet refreshed; call sites should check
    # exchange_data_fresh_ts for staleness.
    realized_pnl_exchange: float = 0.0  # FIFO-matched realized P/L
    avg_entry_exchange: float = 0.0  # weighted-avg cost basis
    cost_basis_total_exchange: float = 0.0  # qty × avg_entry
    fees_paid_exchange: float = 0.0
    exchange_trade_count: int = 0
    exchange_data_fresh_ts: float = 0.0  # unix-seconds of last refresh
    # Exchange wallet USD + USDC cash; the container aggregator takes the
    # max value across bots (all share one wallet).
    cash_balance_usd: float = 0.0

    # Surplus profit parked when the cycle's growth cap is exhausted, drained into
    # target_balance by later cycles. Mirrors ScrummingBot._standing_surplus_usd,
    # read by the live settings tab's surplus display.
    standing_surplus_usd: float = 0.0
