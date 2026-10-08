"""Bot modes, states, the ``BotConfig`` dataclass and ``make_bot_config``.

``BotConfig`` carries every operator setting and ``BotStats`` carries the
runtime counters. ``make_bot_config`` refuses a kwarg foreign to the given
``BotMode``. This module imports nothing from the trading package.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from enum import Enum
from typing import Optional

# DOLLAR_PEGGED_CURRENCIES count as 1.00 USD; no market price is read for them.
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


#: Default for ``BotConfig.stack_mode`` and the wizard's checkbox.
STACK_MODE_DEFAULT: bool = True

#: ``BotConfig.expiry_close_action``: stop buying and let the sell ladder run.
EXPIRY_CLOSE_FINISH_LADDER: str = "finish_ladder"
#: ``BotConfig.expiry_close_action``: one order for the whole remaining position.
EXPIRY_CLOSE_SELL_ALL: str = "sell_all"
#: The two close meanings, in the order the control offers them.
EXPIRY_CLOSE_ACTIONS: tuple = (EXPIRY_CLOSE_FINISH_LADDER, EXPIRY_CLOSE_SELL_ALL)

#: ``BotConfig.expiry_lead_mode``: a share of the contract's life at bot start.
EXPIRY_LEAD_FRACTION: str = "fraction"
#: ``BotConfig.expiry_lead_mode``: a figure in days read from the contract's end.
EXPIRY_LEAD_ABSOLUTE: str = "absolute"
#: The two lead modes, in the order the control offers them.
EXPIRY_LEAD_MODES: tuple = (EXPIRY_LEAD_FRACTION, EXPIRY_LEAD_ABSOLUTE)

#: Default ``expiry_lead_fraction``. The recorded Coinbase ladder steps 11 days
#: between expiry dates over a median contract life of 51.17 days, which is
#: 0.2150, taken to the nearest 0.05 step the control offers.
EXPIRY_LEAD_FRACTION_DEFAULT: float = 0.20

#: Default ``expiry_lead_days``, read in absolute mode. The recorded ladder's
#: median step between consecutive expiry dates.
EXPIRY_LEAD_DAYS_DEFAULT: float = 11.0

#: Default ``expiry_horizon_days``. The recorded dated ladder's longest contract
#: runs 264.21 days and the next expiry date is 1,534.42 days out, so one
#: calendar year holds the whole ladder and nothing beyond it.
EXPIRY_HORIZON_DAYS_DEFAULT: float = 365.0

#: ``expiry_close_decision``'s answer when the market publishes no expiry.
EXPIRY_NOT_EXPIRING: str = "the venue publishes no expiry for this market"
#: ``expiry_close_decision``'s answer when the epoch cannot be read as days.
EXPIRY_UNREADABLE: str = "the expiry epoch cannot be read as a number of days"
#: ``expiry_close_decision``'s answer beyond ``expiry_horizon_days``.
EXPIRY_BEYOND_HORIZON: str = "the expiry is beyond the horizon"
#: ``expiry_close_decision``'s answer when ``expiry_horizon_days`` is zero.
EXPIRY_HORIZON_OFF: str = "the horizon is off"
#: ``expiry_close_decision``'s answer when the resolved lead is zero or less.
EXPIRY_LEAD_OFF: str = "the lead time is off"
#: ``expiry_close_decision``'s answer before the lead time is reached.
EXPIRY_OUTSIDE_LEAD: str = "the expiry is outside the lead time"
#: ``expiry_close_decision``'s answer when the close acts.
EXPIRY_INSIDE_LEAD: str = "the expiry is inside the lead time"

#: Default ``asset_class``, what ``BotContainer._asset_class`` answers for a
#: market the recording holds no class for.
ASSET_CLASS_DEFAULT: str = "crypto"

#: ``whole_unit_opening_units`` reading OFF, where the engine's own
#: ``sizing.WHOLE_UNIT_POSITION_MINIMUM`` decides the opening size.
WHOLE_UNIT_OPENING_ENGINE: int = 0


@dataclass
class BotConfig:
    """Immutable configuration snapshot for a bot instance."""

    exchange_id: str
    base_currency: str  # e.g. "USDT"
    target_asset: str  # e.g. "BTC"
    symbol: str = ""  # Derived: "BTC/USDT"
    mode: BotMode = BotMode.SCRUMMING
    # The sector this bot's market belongs to; the wizard's asset page sets it.
    asset_class: str = ASSET_CLASS_DEFAULT

    profit_folding_active: bool = True

    target_balance: float = 200.0  # Balance the bot trades relative to
    scrumming_interval_pct: float = 1.0  # % market move between actions

    scrum_fold_pct: int = 100  # 1-100: % of scrum proceeds queued for fold

    # Read via despawn_threshold_days() below, never raw; 0 = off.
    tranche_despawn_days: int = 0  # 0 = off; else remove at >= N days

    # Caps per-cycle target_balance growth as a % of the cycle's anchor; 1-100.
    max_target_growth_pct: float = 1.0

    bb_tolerance_pct: float = 1.0  # 0.25% to 5% tolerance for BB proximity
    bb_landing_strip_candles: int = (
        3  # Min consecutive tight HA candles for landing strip
    )
    ta_timeframe: str = "1h"  # Timeframe for TA indicator calculations

    # % distance from the BB midline that switches SEARCH to TRACK; 10-90.
    scrum_detect_pct: int = 75
    # % distance from a BB band that triggers a trade; 0.1-10.0.
    scrum_fire_pct: float = 0.5
    # True scrums only above the BB midline and folds only below it.
    bb_midline_gate: bool = True
    # SEARCH-mode read rate in minutes; TRACK mode reads 10x faster.
    scrum_read_rate_min: int = 5
    # % of BB band width price must travel since the last fold; 0 is off.
    band_travel_pct: int = 70
    # A band touch inside 0.5%, or a wick inside 0.2%, lowers the TA
    # confidence floor; scrum_fire_pct is untouched.
    bb_bullseye_check: bool = True
    # A separate USD reserve for buying sharp drawdowns.
    hedge_rebalance_active: bool = True
    # Hedge reserve in USD; not taken from target_balance.
    hedge_balance: float = 200.0

    # Trip % is (high - low) / open x 100; the soft trip re-opens after the cooldown.
    circuit_breaker_soft_pct: float = 25.0
    circuit_breaker_hard_pct: float = 35.0
    circuit_breaker_cooldown_candles: int = 3

    # 0 disables; otherwise triggers a rebalance once |delta| >= target_balance x
    # pct/100.
    max_cartridge_size_pct: float = 10.0

    # Derives the threshold from the BB range, clamped by
    # max_cartridge_smart_ceiling_pct.
    max_cartridge_smart: bool = False
    max_cartridge_smart_ceiling_pct: float = 30.0

    # Wire income buys the target asset when |position-target| and price-vs-entry
    # are both within this %; 0 disables.
    wire_inflow_stack_pct: float = 1.0

    # SCRUM-side (sell at top):
    scrum_require_ta_bullish: bool = True  # Requires is_bullish for auto-scrum
    scrum_hold_in_uptrend: bool = (
        True  # trend_hold blocks scrum during sustained uptrend
    )
    scrum_defer_to_htf: bool = True  # Refuses scrum when higher-TF phantom is BULLISH
    # FOLD-side (buy at bottom); scrum_hold_in_uptrend has no fold twin.
    fold_require_ta_bearish: bool = True  # Requires is_bearish for auto-fold
    fold_defer_to_htf: bool = True  # Refuses fold when higher-TF phantom is BEARISH

    visibility: str = "orderbook"  # "orderbook" or "internal"
    # Forces engine-initiated trades to execute as IOC-limit taker orders;
    # Manual Fire is unaffected.
    aggressive_trading: bool = False

    # Splits a SCRUM sell across upward levels; "orderbook" rests LIMIT SELLs and
    # "internal" market-sells each tranche as price crosses.
    stack_mode: bool = STACK_MODE_DEFAULT
    # Percent spacing between tranches, scaled by stack_spacing_mode.
    split_distance: float = 1.0
    # Target level count; actual count may drop for exchange min-order-size or
    # 0.1% merge.
    stack_tranche_count_target: int = 3
    # Cumulative distance from anchor in units of split_distance: linear 1,2,3,4;
    # quadratic 1,4,9,16; exponential 1,2,4,8.
    stack_spacing_mode: str = "linear"

    # max_entry_price refuses auto-buy above it and min_entry_price below it;
    # Manual Fire bypasses both.
    max_entry_price: Optional[float] = None
    min_entry_price: Optional[float] = None

    # Effective hysteresis deviation is scrumming_interval_pct + trading_fee_pct;
    # 0.6 is the Coinbase max tier.
    trading_fee_pct: float = 0.6

    # Caps accumulation at position_ceiling_multiple x the anchor target_balance;
    # fold_rate_taper shrinks the fold's USD size 100%->10% over ratio 0.5->1.0.
    position_ceiling_enabled: bool = False
    position_ceiling_multiple: float = 5.0  # Range [1.0, 10.0]
    # A BULLISH reversal on detonation_timeframe at or above
    # detonation_confidence_min market-sells above the anchor, once per reversal.
    # position_ceiling_enabled gates none of the three: detonation fires on the
    # anchor, not on the ceiling.
    detonation_enabled: bool = False
    detonation_timeframe: str = "1d"  # "1d", "1w"
    detonation_confidence_min: float = (
        0.75  # BULLISH confidence threshold; operator-adjustable 0.50-1.00
    )

    # Read through expiry_close_decision() below, never raw. The close acts only
    # inside the resolved lead time and inside expiry_horizon_days.
    expiry_close_action: str = EXPIRY_CLOSE_FINISH_LADDER
    expiry_lead_mode: str = EXPIRY_LEAD_FRACTION
    # Share of the contract's remaining life at bot start; 0 is off.
    expiry_lead_fraction: float = EXPIRY_LEAD_FRACTION_DEFAULT
    # Days before expiry, read in absolute mode; 0 is off.
    expiry_lead_days: float = EXPIRY_LEAD_DAYS_DEFAULT
    # A contract expiring beyond this reads as non-expiring and gains no action.
    expiry_horizon_days: float = EXPIRY_HORIZON_DAYS_DEFAULT

    # Read through whole_unit_opening_units() below, never raw. Whole units a
    # position on a market that places no fraction opens at; 0 is the engine's.
    whole_unit_opening_units: int = WHOLE_UNIT_OPENING_ENGINE

    # Target-asset units held out of the bot's decision math and reservation.
    personal_hold_qty: float = 0.0

    # BotMode.EXTRACTOR anchors to a base-asset pool and sends chunks into ALT
    # pairs; it spawns no child bots.

    extractor_chunk_size_usd: float = 100.0
    # USD-equivalent base currency owned; converted to base units at creation, then
    # tracked in base units.
    extractor_artillery_size_usd: float = 5.0
    # Top-N */<base> pairs by 24h volume kept on the watch list.
    extractor_scan_top_n: int = 8
    # Re-ranks the top-N every N ticks.
    extractor_scan_refresh_candles: int = 60
    # % of the alt position sold on a bullish trigger; 100 is a full exit.
    extractor_exit_pct: float = 100.0

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
                    f"sigil). This is likely a stale "
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


# These sets mark which fields are valid per mode; make_bot_config raises on a
# foreign field.

#: Fields valid for either mode's make_bot_config(...) call, unmodified.
_BOT_CONFIG_SHARED_FIELDS: frozenset = frozenset(
    {
        "exchange_id",
        "base_currency",
        "target_asset",
        "symbol",
        "mode",
        # A bot in either mode trades a market belonging to one sector.
        "asset_class",
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
        # Every order path reads the expiry close, so both modes carry it.
        "expiry_close_action",
        "expiry_lead_mode",
        "expiry_lead_fraction",
        "expiry_lead_days",
        "expiry_horizon_days",
        # Every order path is sized by the market's unit rule, so both modes
        # carry the opening size a whole-unit market takes.
        "whole_unit_opening_units",
    }
)

#: Fields meaningful only for ScrummingBot; make_bot_config(mode=EXTRACTOR, ...)
#: raises ValueError if any of these is passed.
_BOT_CONFIG_SCRUMMING_ONLY_FIELDS: frozenset = frozenset(
    {
        "profit_folding_active",
        # Scrumming-specific accumulation
        "scrumming_interval_pct",
        "scrum_fold_pct",
        "max_target_growth_pct",
        # tranche_despawn_days sweeps the fold and stack ledgers, both
        # ScrummingBot-only.
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
        "fold_defer_to_htf",
        # risk-control fields
        "position_ceiling_enabled",
        "position_ceiling_multiple",
        "detonation_enabled",
        "detonation_timeframe",
        "detonation_confidence_min",
        # interop fields
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
        "extractor_exit_pct",
    }
)


#: A retirement record, not a setting set. Each name is a setting removed from
#: the product, kept so a config stored before its removal still builds;
#: `_sanitize_deprecated_kwargs` drops each before `BotConfig.__init__`.
#: Add no name. Only `bulk_trading` is read, by `bot_config_kwargs`.
_DEPRECATED_KWARGS: frozenset = frozenset(
    {
        "bulk_trading",  # renamed to stack_mode
        "bulk_partial_on_return",
        "market_check_interval",
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


#: Bound for `as_finite_float`'s int branch; 2**1023 is under the float max.
_FLOAT_SAFE_INT: int = 2**1023

#: Saturation cap for `despawn_threshold_days`, 10,000 years in whole days.
DESPAWN_MAX_DAYS: int = 3_650_000

#: Seconds `BotManager.start_all` waits between bots, and the figure the Start
#: All dialog quotes. 0.6 drew HTTP 429 on three of 38 starts.
START_ALL_GAP_SECONDS: float = 3.5


def as_finite_float(value) -> Optional[float]:
    """Return `value` as a float when its exact type is int or float and it is
    finite.

    A bool is refused, and so is an int outside +/-`_FLOAT_SAFE_INT`.

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

    Reads `config.tranche_despawn_days` through `as_finite_float`, truncates
    toward zero and saturates at `DESPAWN_MAX_DAYS`. A non-numeric,
    non-finite or negative setting reads as OFF.

    Args:
      config: any object; the field is read with `getattr`.

    Returns:
      Whole days in [0, DESPAWN_MAX_DAYS]. 0 means the timer is off.
    """
    days = as_finite_float(getattr(config, "tranche_despawn_days", 0))
    if days is None:
        return 0
    return min(DESPAWN_MAX_DAYS, max(0, int(days)))


#: Candidate windows the Fold Tranches panel offers when the timer is OFF.
DESPAWN_PREVIEW_WINDOWS: tuple[int, ...] = (7, 14, 30, 60)


def _despawn_age_seconds(tranche: object, field: str, now: float) -> Optional[float]:
    """Return one tranche's age in seconds, or None when it has no usable timestamp.

    `as_finite_float` refuses a stored bool and a non-positive stamp reads as
    unset, matching `ScrummingBot._tranche_age_seconds`.

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
    `stack_kept_live_order`, never as removable.
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
    `ScrummingBot._despawn_aged_tranches`: age >= days is removable, an
    ageless record is kept, and a stack tranche holding a live exchange
    order is kept.

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


def expiry_close_action(config) -> str:
    """Return this bot's close meaning: `finish_ladder` or `sell_all`.

    A stored value `EXPIRY_CLOSE_ACTIONS` does not hold reads as
    `EXPIRY_CLOSE_FINISH_LADDER`, which leaves the bot's own sell ladder running.

    Args:
      config: any object; the field is read with `getattr`.

    Returns:
      One name out of `EXPIRY_CLOSE_ACTIONS`.
    """
    held = getattr(config, "expiry_close_action", EXPIRY_CLOSE_FINISH_LADDER)
    return held if held in EXPIRY_CLOSE_ACTIONS else EXPIRY_CLOSE_FINISH_LADDER


def expiry_lead_mode(config) -> str:
    """Return this bot's lead-time mode: `fraction` or `absolute`.

    A stored value `EXPIRY_LEAD_MODES` does not hold reads as
    `EXPIRY_LEAD_FRACTION`.

    Args:
      config: any object; the field is read with `getattr`.

    Returns:
      One name out of `EXPIRY_LEAD_MODES`.
    """
    held = getattr(config, "expiry_lead_mode", EXPIRY_LEAD_FRACTION)
    return held if held in EXPIRY_LEAD_MODES else EXPIRY_LEAD_FRACTION


def expiry_horizon_days(config) -> float:
    """Return this bot's expiry horizon in whole and fractional days; 0 is OFF.

    Reads `config.expiry_horizon_days` through `as_finite_float`. A non-numeric
    or non-finite setting reads as `EXPIRY_HORIZON_DAYS_DEFAULT` and a negative
    one reads as 0.

    Args:
      config: any object; the field is read with `getattr`.

    Returns:
      Days in [0.0, inf). 0.0 means no contract gets an expiry action.
    """
    days = as_finite_float(
        getattr(config, "expiry_horizon_days", EXPIRY_HORIZON_DAYS_DEFAULT)
    )
    if days is None:
        return EXPIRY_HORIZON_DAYS_DEFAULT
    return max(0.0, days)


def expiry_lead_resolved_days(config, life_days) -> Optional[float]:
    """Return the lead time in days this bot acts at, or None when it is off.

    In `fraction` mode the lead is `expiry_lead_fraction` of `life_days`, which
    is the contract's remaining life at the bot's own start, so one setting
    covers contracts whose lives differ by orders of magnitude. In `absolute`
    mode the lead is `expiry_lead_days` and `life_days` is not read.

    Args:
      config: any object; the fields are read with `getattr`.
      life_days: the contract's remaining life in days at the bot's start.

    Returns:
      A positive number of days, or None when the figure is unusable or zero.
    """
    if expiry_lead_mode(config) == EXPIRY_LEAD_ABSOLUTE:
        days = as_finite_float(
            getattr(config, "expiry_lead_days", EXPIRY_LEAD_DAYS_DEFAULT)
        )
        return days if days is not None and days > 0.0 else None
    share = as_finite_float(
        getattr(config, "expiry_lead_fraction", EXPIRY_LEAD_FRACTION_DEFAULT)
    )
    life = as_finite_float(life_days)
    if share is None or share <= 0.0 or life is None or life <= 0.0:
        return None
    return share * life


def whole_unit_opening_units(config) -> int:
    """Return the whole units this bot opens a position at on a market that
    places no fraction of a unit; `WHOLE_UNIT_OPENING_ENGINE` means the
    engine's own minimum decides.

    Reads `config.whole_unit_opening_units` through `as_finite_float` and
    truncates toward zero, so a non-numeric, non-finite or negative setting
    leaves `sizing.WHOLE_UNIT_POSITION_MINIMUM` deciding the opening size.

    Args:
      config: any object; the field is read with `getattr`.

    Returns:
      Whole units in [0, inf). 0 reads the engine's own minimum.
    """
    units = as_finite_float(
        getattr(config, "whole_unit_opening_units", WHOLE_UNIT_OPENING_ENGINE)
    )
    if units is None:
        return WHOLE_UNIT_OPENING_ENGINE
    return max(WHOLE_UNIT_OPENING_ENGINE, int(units))


def whole_position_units(position_value_usd, price) -> Optional[float]:
    """Return the base units a position worth `position_value_usd` holds at `price`.

    None when either figure is not a finite positive number, so an unread
    position and a price of zero both size no order at all.

    Args:
      position_value_usd: the position's value in quote currency.
      price: quote currency per base unit.

    Returns:
      Base units, or None.
    """
    value = as_finite_float(position_value_usd)
    at = as_finite_float(price)
    if value is None or value <= 0.0 or at is None or at <= 0.0:
        return None
    return value / at


def expiry_close_decision(config, rules, moment_s, start_s=0.0) -> dict:
    """Report what this bot's expiry close does for one market at `moment_s`.

    `acts` is True only while the contract's expiry is inside
    `expiry_horizon_days` AND inside the lead time
    `expiry_lead_resolved_days` returns. The horizon is read first, so a
    contract dated beyond it never acts whatever its lead time resolves to.
    Decides nothing about permission: a sale out of an expiring market already
    passes the order path's own pre-flight and a purchase into one already
    refuses.

    Args:
      config: the bot's `BotConfig`.
      rules: the market's `MarketRules`, or None.
      moment_s: the wall-clock second the decision is taken at.
      start_s: the wall-clock second the bot started, which `fraction` mode
        measures the contract's life at; 0 reads `moment_s` instead.

    Returns:
      A dict carrying `acts`, `action`, `mode`, `lead_days`, `days_left`,
      `life_days`, `horizon_days` and `reason`. `reason` names why `acts` is
      False, and `EXPIRY_INSIDE_LEAD` when it is True.
    """
    answer: dict = {
        "acts": False,
        "action": expiry_close_action(config),
        "mode": expiry_lead_mode(config),
        "lead_days": None,
        "days_left": None,
        "life_days": None,
        "horizon_days": expiry_horizon_days(config),
        "reason": EXPIRY_NOT_EXPIRING,
    }
    if rules is None or not getattr(rules, "expires", False):
        return answer
    moment = as_finite_float(moment_s)
    if moment is None:
        answer["reason"] = EXPIRY_UNREADABLE
        return answer
    left = as_finite_float(_days_to_expiry(rules, moment))
    if left is None:
        answer["reason"] = EXPIRY_UNREADABLE
        return answer
    answer["days_left"] = left
    horizon = answer["horizon_days"]
    if horizon <= 0.0:
        answer["reason"] = EXPIRY_HORIZON_OFF
        return answer
    if left > horizon:
        answer["reason"] = EXPIRY_BEYOND_HORIZON
        return answer
    start = as_finite_float(start_s)
    if start is None or start <= 0.0:
        start = moment
    answer["life_days"] = as_finite_float(_days_to_expiry(rules, start))
    lead = expiry_lead_resolved_days(config, answer["life_days"])
    if lead is None:
        answer["reason"] = EXPIRY_LEAD_OFF
        return answer
    answer["lead_days"] = lead
    if left > lead:
        answer["reason"] = EXPIRY_OUTSIDE_LEAD
        return answer
    answer["acts"] = True
    answer["reason"] = EXPIRY_INSIDE_LEAD
    return answer


def _days_to_expiry(rules, moment: float):
    """Return `rules.days_to_expiry(moment)`, or None when the call cannot answer."""
    try:
        return rules.days_to_expiry(moment)
    except (AttributeError, TypeError, ValueError):
        return None


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


def bot_config_kwargs(mode, collected: dict, *, exchange_id: str = "") -> dict:
    """Return the `make_bot_config` kwargs for `mode` out of `collected`.

    `exchange_id` names the venue when `collected` carries no `exchange_id`.
    """
    foreign = (
        _BOT_CONFIG_SCRUMMING_ONLY_FIELDS
        if mode == BotMode.EXTRACTOR
        else _BOT_CONFIG_EXTRACTOR_ONLY_FIELDS
    )
    # make_bot_config sets mode itself and raises on a foreign field.
    carried = {f.name for f in fields(BotConfig)} - foreign - {"mode"}
    kwargs = {
        key: value
        for key, value in _sanitize_deprecated_kwargs(collected).items()
        if key in carried
    }
    # BotConfig declares no default for either, and make_bot_config defaults
    # target_asset itself.
    kwargs.setdefault("exchange_id", exchange_id)
    kwargs.setdefault("base_currency", "USDT")
    # An Extractor's parameter page offers no target_balance row; its pool is
    # the figure the bot trades against.
    kwargs.setdefault(
        "target_balance",
        (
            collected.get("extractor_chunk_size_usd", 200.0)
            if mode == BotMode.EXTRACTOR
            else 200.0
        ),
    )
    # An absent bulk_trading is the retired Grid checkbox, so False rather
    # than STACK_MODE_DEFAULT.
    kwargs.setdefault("stack_mode", collected.get("bulk_trading", False))
    return kwargs


def phantom_init_kwargs(collected: dict) -> dict:
    """Return the phantom constructor kwargs for a Scrumming bot out of
    `collected`.

    `bot_config_kwargs` carries the declared `BotConfig` fields; the wizard's
    phantom page writes three keys that are none of them. The enable flag and
    the timeframe list are runtime attributes and the lock count belongs to the
    bot's `TimeframeCoordinator`, so all three travel as keyword arguments
    instead. An absent `lock_candle_count` is left out, which keeps the
    coordinator's own declared count.
    """
    kwargs: dict = {
        "enable_phantoms": collected.get("enable_phantoms", False),
        "phantom_timeframes": collected.get("phantom_timeframes", []),
    }
    lock_candles = collected.get("lock_candle_count")
    if lock_candles is not None:
        kwargs["lock_candle_count"] = lock_candles
    return kwargs


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
    # Fold tranches discarded by ScrummingBot.clear_fold_tranches, never folded.
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
    # USD since YTD_TRADE_ANCHOR_UTC, refreshed by sync_ytd_trade_count.
    ytd_scrummed_usd: float = 0.0
    ytd_folded_usd: float = 0.0
    # Never resets, unlike consecutive_errors, which clears on success.
    total_errors: int = 0
    # Exchange-truth values from the connector's get_my_trades; 0 until
    # exchange_data_fresh_ts is set.
    realized_pnl_exchange: float = 0.0  # FIFO-matched realized P/L
    avg_entry_exchange: float = 0.0  # weighted-avg cost basis
    cost_basis_total_exchange: float = 0.0  # qty x avg_entry
    fees_paid_exchange: float = 0.0
    # Distinct venue ORDERS, which is what one trade means on the TRADES card.
    exchange_trade_count: int = 0
    # Distinct venue FILLS behind those orders; one order can fill in pieces.
    exchange_fill_count: int = 0
    exchange_data_fresh_ts: float = 0.0  # unix-seconds of last refresh
    # True when realized_pnl_exchange and fees_paid_exchange were computed
    # over every fill the venue holds, not a walk that stopped short.
    fill_history_complete: bool = False
    # Exchange wallet USD + USDC cash; the aggregator takes the max across bots.
    cash_balance_usd: float = 0.0

    # Surplus parked when the cycle's growth cap is exhausted; mirrors
    # ScrummingBot._standing_surplus_usd.
    standing_surplus_usd: float = 0.0
