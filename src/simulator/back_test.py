"""The run modes' walk: the shipped gate chains over Stone Tablet candles, each
trade sized by ``src.trading.scrumming.sizing``.

``new_bot`` makes one operator-defined ``SimBot`` and ``fleet_source.live_fleet``
supplies the imported clone. ``tape_context`` builds a ``GateContext`` from a
tablet window and the simulated position, ``validation.latch`` evaluates the same
scrum and fold chains live runs, ``apply_scrum`` and ``apply_fold`` size each
fill with the Live bot's own functions, and ``run`` walks each bot's tablet
keeping units, cash and fold tranches under one ``funding``: Back Test from each
bot's own scrum proceeds, Validation and Portfolio Battery from ``run_budget_usd``,
the sum of the held Target Balances. ``cited_rule_for`` names the unit rule a
bot's class trades under on its venue, every fill is sized under it, and a bot
with no cited rule is ``UNCITED_RULE`` and walks nothing. ``missing_pairs``
names the tablets a run needs and ``download_missing`` fills them through the
shipped ``GapFiller``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional, Sequence

from ..trading.gate_chain import GateContext
from ..trading.otd_math import fold_rebuy_factor
from ..trading.scrumming.sizing import (
    WHOLE_UNITS,
    cycle_growth_cap_usd,
    delta_below_interval,
    eligible_fold_tranches,
    estimated_fee_usd,
    fold_cap_remaining_usd,
    fold_rate_taper,
    fold_spend_usd,
    fold_units,
    plan_fold_consumption,
    plan_source_price,
    position_ceiling,
    priced_usd,
    ratio_to_ceiling,
    sale_proceeds_usd,
    scrum_units,
    scrumming_interval_usd,
    settle_fold_plan,
    target_delta_pct,
    target_delta_usd,
    trim_fold_plan,
    unit_rule,
    wallet_capped_spend_usd,
)
from ..trading.scrumming.sizing import estimated_fee_usd as fee_usd
from .fleet_source import NEW_ORIGIN, SimBot
from .portfolios import asset_class, trading_venue
from .sim_bus import (
    FOLD_ACTION,
    FOLD_SIDE,
    SCRUM_ACTION,
    SCRUM_SIDE,
    RunEmitter,
    fill_line,
)
from .validation import (
    BB_MIDLINE,
    MIN_RERUN_CANDLES,
    RERUN_WINDOW_CANDLES,
    bb_reading,
    candle_interval_ms,
    iso_stamp,
    latch,
    tablet_for,
)

logger = logging.getLogger("acervator.simulator.back_test")

SCRUM = "scrum"
FOLD = "fold"

TABLET_SUFFIX = ".json"

#: The candle window every tick reads, and the least a window may hold.
WINDOW_CANDLES = RERUN_WINDOW_CANDLES
MIN_CANDLES = MIN_RERUN_CANDLES

#: ``_TA_CONFIDENCE_FLOOR`` in ``scrumming_bot``, unskewed. A simulated bot
#: carries no arm and no favour, so the skew is zero and the floor is this.
TA_CONFIDENCE_FLOOR = 0.25

#: ``scrum_detect_pct`` when a stored config names none.
DEFAULT_SCRUM_DETECT_PCT = 75.0

#: ``trading_fee_pct`` when a stored config names none.
DEFAULT_TRADING_FEE_PCT = 0.6

#: ``ta_timeframe`` when a stored config names none. Every live tablet is 5m.
DEFAULT_TIMEFRAME = "5m"

#: How many candles the trend reading covers, and how many of them must close
#: up to call it a trend.
TREND_CANDLES = 20
TREND_MIN_BULL_CANDLES = 13

#: ``_STRONG_TREND_MIN_BULL_SHARE`` in ``scrumming_bot``, a share compared
#: against the up-close share of ``TREND_CANDLES``.
TREND_MIN_BULL_SHARE = TREND_MIN_BULL_CANDLES / TREND_CANDLES

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"

UPPER = "upper"
LOWER = "lower"

NO_TABLET = "no_tablet"
SHORT_TABLET = "short_tablet"
BACK_TESTED = "back_tested"

#: The bot's class on its venue has no row in ``sizing.CITED_UNIT_RULES``, so
#: ``run`` walks nothing for it.
UNCITED_RULE = "uncited_rule"

BOT_OUTCOMES = (NO_TABLET, SHORT_TABLET, BACK_TESTED, UNCITED_RULE)

#: Why a whole-unit scrum or fold fills nothing: its dollars buy under one unit.
BELOW_ONE_UNIT = "below one unit"

#: Back Test: each bot's fold spends its own scrum proceeds and no more.
FUNDED_BY_PROCEEDS = "proceeds"

#: Validation and Portfolio Battery: the run's budget is ``run_budget_usd`` and
#: no fold is capped for cash.
FUNDED_BY_TARGETS = "targets"

FUNDINGS = (FUNDED_BY_PROCEEDS, FUNDED_BY_TARGETS)


@dataclass(frozen=True)
class SimTrade:
    """One scrum sell or fold buy the tape produced, with ``scrum_price`` the
    scrum's own ``price`` on a scrum and ``plan_source_price`` over the
    tranches consumed on a fold, zero naming no scrum. ``timeframe`` is the
    ``ta_timeframe`` the walk ran at, empty when unknown."""

    bot_id: str
    symbol: str
    side: str
    ts_ms: int
    price: float
    units: float
    usd: float
    fee_usd: float
    scrum_price: float = 0.0
    timeframe: str = ""


#: The seam ``walk`` hands each ``SimTrade`` to as it fills, as ``run_battery``
#: hands ``progress`` each portfolio's line.
TradeSink = Callable[[SimTrade], None]


@dataclass
class SimPosition:
    """What a simulated bot holds as the tape advances: its units, the cash its
    scrums left, the fold tranches those scrums queued in the shape
    ``_tick_execute_scrum`` builds them, and the price its units were opened
    at, which every tranche carries as ``initial_buy_price``."""

    units: float = 0.0
    cash_usd: float = 0.0
    fold_tranches: list = field(default_factory=list)
    opening_price: float = 0.0
    last_trade_price: float = 0.0
    cycle_cap_consumed_usd: float = 0.0

    @property
    def tranches(self) -> int:
        """How many fold tranches are queued."""
        return len(self.fold_tranches)

    def value_usd(self, price: float) -> float:
        """``units`` at ``price``, ignoring cash held from an earlier scrum."""
        return priced_usd(self.units, float(price))


@dataclass(frozen=True)
class BotResult:
    """One bot's whole pass over its tablet."""

    bot_id: str
    symbol: str
    tablet_key: str
    outcome: str
    candles_read: int = 0
    ticks: int = 0
    scrum_latched: int = 0
    fold_latched: int = 0
    trades: tuple[SimTrade, ...] = ()
    start_units: float = 0.0
    end_units: float = 0.0
    start_price: float = 0.0
    end_price: float = 0.0
    cash_usd: float = 0.0
    fees_usd: float = 0.0
    first_ts_ms: int = 0
    last_ts_ms: int = 0
    asset_class: str = ""
    venue: str = ""
    unit_rule: str = ""
    #: True when ``stop`` ended the walk before the tape's last bar.
    stopped: bool = False

    @property
    def units_gained(self) -> float:
        """``end_units`` less ``start_units``."""
        return self.end_units - self.start_units

    @property
    def scrum_trades(self) -> int:
        """How many trades in ``trades`` are a scrum sell."""
        return sum(1 for one in self.trades if one.side == SCRUM)

    @property
    def fold_trades(self) -> int:
        """How many trades in ``trades`` are a fold buy."""
        return sum(1 for one in self.trades if one.side == FOLD)


def cited_rule_for(asset: str, exchange_id: str) -> tuple[str, str, Optional[str]]:
    """``asset``'s class, the venue it trades that class on, and the rule
    ``unit_rule`` cites for the pair, None when the pair has no row."""
    class_name = asset_class(asset, exchange_id) or ""
    venue = trading_venue(class_name, exchange_id)
    return class_name, venue, unit_rule(class_name, venue)


def uncited_rule_line(result: Any) -> str:
    """The Activity Log line for one ``UNCITED_RULE`` result, named by its
    ``bot_id`` for a ``BotResult`` and by its ``asset`` for a ``SymbolRun``."""
    name = getattr(result, "bot_id", "") or getattr(result, "asset", "")
    return (
        f"{name}: {result.symbol} is class {result.asset_class or 'none'} "
        f"on venue {result.venue or 'none'}, which has no cited unit rule; "
        "not simulated."
    )


def no_tablet_line(bot: SimBot) -> str:
    """The diagnostics line for one ``NO_TABLET`` bot."""
    return (
        f"{bot.bot_id}: no Stone Tablet for {bot.asset} on {bot.exchange_id}; "
        "nothing walked."
    )


def short_tablet_line(bot: SimBot, candles: int) -> str:
    """The diagnostics line for one ``SHORT_TABLET`` bot over ``candles``
    bars, under ``MIN_CANDLES``."""
    return (
        f"{bot.bot_id}: the Stone Tablet holds {candles} candles, under "
        f"{MIN_CANDLES}; nothing walked."
    )


def fill_action(filled: Optional[SimTrade]) -> str:
    """``SCRUM_ACTION`` or ``FOLD_ACTION`` for ``filled``, empty for None."""
    if filled is None:
        return ""
    return SCRUM_ACTION if filled.side == SCRUM else FOLD_ACTION


def fill_side(filled: Optional[SimTrade]) -> str:
    """``SCRUM_SIDE`` or ``FOLD_SIDE`` for ``filled``, empty for None."""
    if filled is None:
        return ""
    return SCRUM_SIDE if filled.side == SCRUM else FOLD_SIDE


def new_bot(
    symbol: str,
    exchange_id: str,
    target_usd: float,
    ta_timeframe: str = "",
    scrumming_interval_pct: float = 0.0,
    bot_id: str = "",
) -> SimBot:
    """One operator-defined ``SimBot``, its ``bot_id`` built from the pair when
    unnamed."""
    pair = str(symbol or "")
    venue = str(exchange_id or "")
    return SimBot(
        bot_id=str(bot_id or f"{pair}@{venue}"),
        symbol=pair,
        exchange_id=venue,
        base_currency=pair.split("/")[-1] if pair else "",
        origin=NEW_ORIGIN,
        target_usd=float(target_usd),
        ta_timeframe=str(ta_timeframe or ""),
        scrumming_interval_pct=float(scrumming_interval_pct),
        trading_fee_pct=DEFAULT_TRADING_FEE_PCT,
    )


def new_bots(specs: Sequence[dict]) -> list[SimBot]:
    """One ``SimBot`` per spec in ``specs``, dropping any that names no
    symbol."""
    out: list[SimBot] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        symbol = str(spec.get("symbol") or "")
        if not symbol:
            continue
        out.append(
            new_bot(
                symbol,
                str(spec.get("exchange_id") or ""),
                float(spec.get("target_usd") or 0.0),
                str(spec.get("ta_timeframe") or ""),
                float(spec.get("scrumming_interval_pct") or 0.0),
                str(spec.get("bot_id") or ""),
            )
        )
    return out


def bb_detect_thresholds(scrum_detect_pct: float) -> tuple[float, float]:
    """``(lower, upper)`` in ``bb_pos`` terms, 75 giving 0.125 and 0.875.

    A second spelling of ``CircuitBreakerMixin._bb_detect_thresholds``, which is
    a method on a live bot mixin and needs one to call.
    """
    try:
        detect_pct = float(scrum_detect_pct)
    except (TypeError, ValueError):
        detect_pct = DEFAULT_SCRUM_DETECT_PCT
    half = max(0.0, min(1.0, detect_pct / 100.0)) * 0.5
    return (0.5 - half, 0.5 + half)


def trend_reading(window: Sequence[Any]) -> tuple[bool, float]:
    """``(trend_hold, trend_strength)`` from the share of up closes in the last
    20."""
    if len(window) < TREND_CANDLES:
        return False, 0.5
    recent = window[-TREND_CANDLES:]
    bull = sum(1 for one in recent if one.close > one.open)
    strength = bull / len(recent)
    return strength > TREND_MIN_BULL_SHARE, strength


def signal_detail(summary: Any, indicator: str, key: str) -> float:
    """One indicator's ``key`` detail from ``summary``, zero when it names
    none."""
    if summary is None:
        return 0.0
    for signal in summary.signals:
        if signal.indicator == indicator:
            try:
                return float(signal.details.get(key, 0.0) or 0.0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def ta_direction(summary: Any, reading: Any) -> tuple[bool, bool, str, float]:
    """``(is_bullish, is_bearish, direction_name, confidence)`` for one window.

    A ``landing_strip`` forces its own side true.
    """
    if summary is None:
        return False, False, NEUTRAL, 0.0
    name = summary.consensus_direction.name
    confidence = float(summary.consensus_confidence)
    above_floor = confidence >= TA_CONFIDENCE_FLOOR
    is_bullish = name in (BULLISH, NEUTRAL) and above_floor
    is_bearish = name in (BEARISH, NEUTRAL) and above_floor
    if reading is not None and getattr(reading, "landing_strip", False):
        side = getattr(reading, "landing_strip_side", "")
        is_bullish = is_bullish or side == UPPER
        is_bearish = is_bearish or side == LOWER
    return is_bullish, is_bearish, name, confidence


def tape_context(
    bot: SimBot,
    position: SimPosition,
    window: Sequence[Any],
    reading: Any,
    summary: Any,
) -> GateContext:
    """A ``GateContext`` for the last candle of ``window`` and the ``position``
    holding it.

    The tape drives ``ticker_last``, ``bb_pos`` and every indicator; ``position``
    drives ``delta`` and ``n_fold_tranches``; the circuit breaker, hysteresis and
    higher-timeframe fields read as not populated.
    """
    close = float(window[-1].close)
    bb_pos = float(reading.bb_position) if reading is not None else 0.0
    lower_dt, upper_dt = bb_detect_thresholds(bot.scrum_detect_pct)
    target_usd = float(bot.target_usd or 0.0)
    delta = target_delta_usd(position.value_usd(close), target_usd)
    interval_usd = scrumming_interval_usd(target_usd, float(bot.scrumming_interval_pct))
    below_interval = delta_below_interval(delta, interval_usd)
    is_bullish, is_bearish, direction_name, _confidence = ta_direction(summary, reading)
    trend_hold, trend_strength = trend_reading(window)

    if bot.bb_midline_gate:
        scrum_ok = bb_pos > BB_MIDLINE
        fold_ok_midline = bb_pos < BB_MIDLINE
    else:
        scrum_ok = True
        fold_ok_midline = True

    above_upper = bb_pos >= upper_dt
    below_lower = bb_pos <= lower_dt
    banded = reading is not None and reading.upper > 0 and reading.lower > 0
    return GateContext(
        symbol=bot.symbol,
        ticker_last=close,
        bb_pos=bb_pos,
        bb_upper_dt=upper_dt,
        bb_lower_dt=lower_dt,
        delta=delta,
        delta_pct=target_delta_pct(delta, target_usd),
        below_interval=below_interval,
        is_bullish=is_bullish,
        is_bearish=is_bearish,
        trend_hold=trend_hold,
        trend_strength=trend_strength,
        eff_direction_name=direction_name,
        eff_is_bullish=is_bullish if bot.scrum_require_ta_bullish else True,
        eff_is_bearish=is_bearish if bot.fold_require_ta_bearish else True,
        eff_trend_hold=trend_hold if bot.scrum_hold_in_uptrend else False,
        eff_htf_blocks_scrum=False,
        eff_htf_blocks_fold=False,
        flag_require_ta_bullish=bot.scrum_require_ta_bullish,
        flag_hold_in_uptrend=bot.scrum_hold_in_uptrend,
        flag_defer_to_htf=bot.scrum_defer_to_htf,
        flag_fold_require_ta_bearish=bot.fold_require_ta_bearish,
        flag_fold_defer_to_htf=bot.fold_defer_to_htf,
        bb_above_upper_dt=above_upper,
        bb_below_lower_dt=below_lower,
        scrum_ok=scrum_ok,
        fold_ok_midline=fold_ok_midline,
        target_fires=True,
        cb_blocks_scrum=False,
        cb_blocks_fold=False,
        hyst_ok_scrum_side=True,
        hyst_ok_fold_side=True,
        hyst_armed_scrum_side=False,
        hyst_armed_fold_side=False,
        hyst_ref_scrum_side=0.0,
        hyst_ref_fold_side=0.0,
        mem253_at_ceiling=False,
        mem253_smart_ceiling_usd=0.0,
        mem253_current_pos=position.value_usd(close),
        has_fold_tranches=position.tranches > 0,
        n_fold_tranches=position.tranches,
        htf_bias_name=None,
        htf_blocks_scrum=False,
        htf_blocks_fold=False,
        scrumming_interval_pct=float(bot.scrumming_interval_pct),
        trading_fee_pct=float(bot.trading_fee_pct or DEFAULT_TRADING_FEE_PCT),
        ripe_scrum=banded and delta > 0 and not below_interval and above_upper,
        deep_fold=banded and delta < 0 and not below_interval and below_lower,
        adx=signal_detail(summary, "adx", "adx"),
        efficiency_ratio=signal_detail(summary, "kaufman_er", "er"),
        z_score=signal_detail(summary, "zscore", "z"),
    )


def apply_scrum(
    bot: SimBot,
    position: SimPosition,
    price: float,
    ts_ms: int,
    delta: float,
    rule: str,
) -> Optional[SimTrade]:
    """Sell ``scrum_units`` of ``delta`` at ``price`` under ``rule`` and queue
    the proceeds net of ``estimated_fee_usd`` as one fold tranche, as
    ``_tick_execute_scrum`` books a sale over one lot.

    Nothing fills when ``position`` holds fewer units than the sell needs, or
    when a whole-unit ``delta`` buys under one unit, which is logged.
    """
    units = scrum_units(float(delta), float(price), rule)
    if units <= 0.0:
        if rule == WHOLE_UNITS:
            logger.info(
                "%s: a scrum of $%.2f at %.8f is %s; nothing fills",
                bot.bot_id,
                abs(float(delta)),
                float(price),
                BELOW_ONE_UNIT,
            )
        return None
    if units > position.units:
        return None
    notional = priced_usd(units, float(price))
    fee = estimated_fee_usd(notional, bot.trading_fee_pct or DEFAULT_TRADING_FEE_PCT)
    proceeds = sale_proceeds_usd(notional, fee)
    position.units -= units
    position.cash_usd += proceeds
    position.last_trade_price = float(price)
    position.fold_tranches.append(
        {
            "usd": proceeds,
            "units": units,
            "ref": float(price),
            "initial_buy_price": position.opening_price,
            "created_ts": float(ts_ms) / 1000.0,
        }
    )
    return SimTrade(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        side=SCRUM,
        ts_ms=int(ts_ms),
        price=float(price),
        units=units,
        usd=notional,
        fee_usd=fee,
        scrum_price=float(price),
        timeframe=str(bot.ta_timeframe or ""),
    )


def fold_taper(bot: SimBot, position: SimPosition) -> float:
    """``fold_rate_taper`` over the position's ``ratio_to_ceiling`` at its
    ``last_trade_price`` when the bot's ceiling is on and a trade has filled,
    one otherwise, as ``ScrummingBot.fold_rate_taper`` reads ``ceiling_ratio``
    with the anchor at the bot's target."""
    if not bot.position_ceiling_enabled:
        return 1.0
    ceiling = position_ceiling(
        float(bot.target_usd or 0.0), bot.position_ceiling_multiple
    )
    if ceiling <= 0.0 or position.last_trade_price <= 0.0:
        return 1.0
    value = position.value_usd(position.last_trade_price)
    return fold_rate_taper(ratio_to_ceiling(value, ceiling))


def apply_fold(
    bot: SimBot,
    position: SimPosition,
    price: float,
    ts_ms: int,
    delta: float,
    funding: str = FUNDED_BY_PROCEEDS,
    *,
    rule: str,
) -> Optional[SimTrade]:
    """Rebuy the eligible tranches as ``_tick_execute_fold`` does: the tranches
    ``eligible_fold_tranches`` names under ``fold_rebuy_factor``, sorted highest
    ``initial_buy_price`` first, planned under ``cycle_growth_cap_usd`` by
    ``plan_fold_consumption``, spent as ``fold_spend_usd`` under ``fold_taper``,
    booked as ``fold_units`` at ``price`` under ``rule``, and settled by
    ``settle_fold_plan``.

    ``FUNDED_BY_PROCEEDS`` holds the spend to ``position.cash_usd`` through
    ``wallet_capped_spend_usd`` and ``FUNDED_BY_TARGETS`` caps nothing, while
    ``delta`` sizes nothing here as it sizes nothing in ``_tick_execute_fold``,
    and under ``WHOLE_UNITS`` the fold spends the whole units' price with
    ``trim_fold_plan`` leaving the rest in the tranches, or fills nothing and
    logs ``BELOW_ONE_UNIT`` when the spend buys under one unit.
    """
    del delta
    fee_pct = bot.trading_fee_pct or DEFAULT_TRADING_FEE_PCT
    factor = fold_rebuy_factor(bot.scrumming_interval_pct, fee_pct)
    eligible = eligible_fold_tranches(position.fold_tranches, float(price), factor)
    if not eligible:
        return None
    ordered = sorted(
        eligible, key=lambda t: -float(t.get("initial_buy_price", t.get("ref", 0)))
    )
    cap = cycle_growth_cap_usd(
        float(bot.target_usd or 0.0),
        position.cycle_cap_consumed_usd,
        bot.max_target_growth_pct,
    )
    plan, slices, _partial = plan_fold_consumption(
        ordered, fold_cap_remaining_usd(cap, position.cycle_cap_consumed_usd)
    )
    if not slices:
        return None
    taper = fold_taper(bot, position)
    if taper <= 0.0:
        return None
    spend = fold_spend_usd(sum(one["usd"] for one in slices), taper)
    if funding == FUNDED_BY_PROCEEDS:
        spend = wallet_capped_spend_usd(spend, position.cash_usd)
    if spend <= 0.0:
        return None
    units = fold_units(spend, float(price), rule)
    if units <= 0.0:
        if rule == WHOLE_UNITS:
            logger.info(
                "%s: a fold of $%.2f at %.8f is %s; nothing fills",
                bot.bot_id,
                spend,
                float(price),
                BELOW_ONE_UNIT,
            )
        return None
    if rule == WHOLE_UNITS:
        bought_usd = priced_usd(units, float(price))
        plan = trim_fold_plan(plan, spend - bought_usd)
        spend = bought_usd
    fee = estimated_fee_usd(spend, fee_pct)
    position.units += units
    position.cash_usd -= spend
    position.last_trade_price = float(price)
    scrum_price = plan_source_price(plan)
    position.fold_tranches, _removed, _spent = settle_fold_plan(
        position.fold_tranches, plan
    )
    return SimTrade(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        side=FOLD,
        ts_ms=int(ts_ms),
        price=float(price),
        units=units,
        usd=spend,
        fee_usd=fee,
        scrum_price=scrum_price,
        timeframe=str(bot.ta_timeframe or ""),
    )


def opening_position(bot: SimBot, price: float, rule: str) -> SimPosition:
    """A ``SimPosition`` worth ``bot.target_usd`` at ``price`` under ``rule``,
    the ``fold_units`` the initial entry's buy of the target books."""
    target_usd = float(bot.target_usd or 0.0)
    units = fold_units(target_usd, float(price), rule) if price > 0.0 else 0.0
    return SimPosition(units=units, cash_usd=0.0, opening_price=float(price))


def run_budget_usd(bots: Sequence[SimBot]) -> float:
    """The sum of every held bot's ``target_usd``; a bot with no target adds
    nothing."""
    return sum(float(bot.target_usd) for bot in bots if bot.target_usd is not None)


def walk(
    bot: SimBot,
    candles: Sequence[Any],
    step: int = 1,
    funding: str = FUNDED_BY_PROCEEDS,
    *,
    rule: str,
    on_trade: Optional[TradeSink] = None,
    stop: Optional[Callable[[], bool]] = None,
    emitter: Optional[RunEmitter] = None,
) -> BotResult:
    """Run ``bot`` over ``candles``, one gate-chain evaluation every ``step``
    bars, each fold funded as ``funding`` says and every fill sized under
    ``rule``; ``on_trade`` is handed each ``SimTrade`` the moment it fills,
    ``emitter`` emits ``trade_filled``, ``bot_line``, ``voting_snapshot`` and
    ``gate_decision`` on every tick in Live's fire order, and ``stop``
    answering True before a tick ends the walk at the last bar ticked with
    ``stopped`` set."""
    from ..trading.ta_engine import VotingEngine

    if len(candles) < MIN_CANDLES:
        if emitter is not None:
            emitter.bot_line(bot.bot_id, short_tablet_line(bot, len(candles)))
        return BotResult(
            bot_id=bot.bot_id,
            symbol=bot.symbol,
            tablet_key="",
            outcome=SHORT_TABLET,
            candles_read=len(candles),
            unit_rule=rule,
        )
    engine = VotingEngine()
    timeframe = bot.ta_timeframe or DEFAULT_TIMEFRAME
    position = opening_position(bot, float(candles[MIN_CANDLES - 1].close), rule)
    start_units = position.units
    trades: list[SimTrade] = []
    scrum_latched = 0
    fold_latched = 0
    ticks = 0
    fees = 0.0
    halted = False
    last_index = MIN_CANDLES - 1
    for index in range(MIN_CANDLES - 1, len(candles), max(int(step), 1)):
        if stop is not None and stop():
            halted = True
            break
        last_index = index
        window = list(candles[max(0, index + 1 - WINDOW_CANDLES) : index + 1])
        reading = bb_reading(window, bot)
        summary = engine.compute_all(window, timeframe, symbol=bot.symbol)
        context = tape_context(bot, position, window, reading, summary)
        armed = latch(context)
        ticks += 1
        price = float(window[-1].close)
        stamp = int(window[-1].timestamp)
        filled = None
        if armed["scrum_armed"]:
            scrum_latched += 1
            filled = apply_scrum(bot, position, price, stamp, context.delta, rule)
        elif armed["fold_armed"]:
            fold_latched += 1
            filled = apply_fold(
                bot, position, price, stamp, context.delta, funding, rule=rule
            )
        if filled is not None:
            trades.append(filled)
            fees += filled.fee_usd
            if on_trade is not None:
                on_trade(filled)
        if emitter is not None:
            action = fill_action(filled)
            if filled is not None:
                emitter.trade_filled(filled, bot.exchange_id)
                emitter.bot_line(bot.bot_id, fill_line(filled), stamp)
            emitter.voting_snapshot(bot, summary, stamp, action, fill_side(filled))
            emitter.gate_decision(
                bot,
                context,
                armed,
                stamp,
                reading=reading,
                position=position,
                tick=ticks,
                trade_action=action,
                side=fill_side(filled),
            )
    end_index = last_index if halted else len(candles) - 1
    return BotResult(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        tablet_key="",
        outcome=BACK_TESTED,
        candles_read=end_index + 1,
        ticks=ticks,
        scrum_latched=scrum_latched,
        fold_latched=fold_latched,
        trades=tuple(trades),
        start_units=start_units,
        end_units=position.units,
        start_price=float(candles[MIN_CANDLES - 1].close),
        end_price=float(candles[end_index].close),
        cash_usd=position.cash_usd,
        fees_usd=fees,
        first_ts_ms=int(candles[0].timestamp),
        last_ts_ms=int(candles[end_index].timestamp),
        unit_rule=rule,
        stopped=halted,
    )


@dataclass(frozen=True)
class BackTestRun:
    """One pass of a run mode: its fleet, its tablets, what the tape produced,
    the ``funding`` its folds ran under and, for ``FUNDED_BY_TARGETS``, the
    ``budget_usd`` of ``run_budget_usd``."""

    exchange_id: str
    bots: tuple[SimBot, ...]
    results: tuple[BotResult, ...]
    missing: tuple[tuple[str, str], ...] = ()
    bot_outcomes: dict[str, int] = field(default_factory=dict)
    interval_ms: int = 0
    funding: str = FUNDED_BY_PROCEEDS
    budget_usd: Optional[float] = None
    #: The ``ParityReport`` ``run`` wrote for this pass; None until it has.
    report: Any = None
    #: True when ``stop`` ended the pass before every bot was walked to its end.
    stopped: bool = False
    #: The id every row of this pass carries in ``data.run_id``; empty when
    #: ``run`` was handed no bus.
    run_id: str = ""
    #: What ``RunEmitter.close`` answered: the rows emitted per topic and the
    #: ``EmitObserver`` reading; empty when ``run`` was handed no bus.
    emitted: dict = field(default_factory=dict)

    @property
    def ran(self) -> list[BotResult]:
        """Every result whose ``outcome`` reads ``BACK_TESTED``."""
        return [one for one in self.results if one.outcome == BACK_TESTED]

    @property
    def summary(self) -> dict:
        """The counts the Back Test pane reports."""
        ran = self.ran
        return {
            "bots": len(self.bots),
            "bots_run": len(ran),
            "candles_read": sum(one.candles_read for one in ran),
            "ticks": sum(one.ticks for one in ran),
            "scrum_latched": sum(one.scrum_latched for one in ran),
            "fold_latched": sum(one.fold_latched for one in ran),
            "scrum_trades": sum(one.scrum_trades for one in ran),
            "fold_trades": sum(one.fold_trades for one in ran),
            "fees_usd": sum(one.fees_usd for one in ran),
            "missing_tablets": len(self.missing),
            "uncited_rule": len(self.uncited),
        }

    @property
    def uncited(self) -> list[BotResult]:
        """Every result whose ``outcome`` reads ``UNCITED_RULE``."""
        return [one for one in self.results if one.outcome == UNCITED_RULE]

    @property
    def unreached(self) -> list[str]:
        """The bot ids the pass never reached: those with no result."""
        seen = {one.bot_id for one in self.results}
        return [one.bot_id for one in self.bots if one.bot_id not in seen]

    @property
    def stopped_line(self) -> str:
        """What the pass says when ``stopped``: the bots walked, the one cut
        short and the bots not reached; empty otherwise."""
        if not self.stopped:
            return ""
        missed = self.unreached
        cut = [one.bot_id for one in self.results if one.stopped]
        return (
            f"Stopped by the operator: {len(self.results)} of {len(self.bots)} "
            f"bots walked, {len(cut)} cut short at its last bar ticked; "
            f"{len(missed)} bot(s) not reached: "
            f"{', '.join(missed) if missed else 'none'}."
        )

    @property
    def lines(self) -> list[str]:
        """The stop line when ``stopped``, the fleet, the tape span, what
        latched and each bot refused for an uncited rule, in the pane's own
        order."""
        read = self.summary
        refused = [uncited_rule_line(one) for one in self.uncited]
        opening = [self.stopped_line] if self.stopped else []
        if not read["bots_run"]:
            return (
                opening
                + ["No bot reached a Stone Tablet with enough candles."]
                + refused
            )
        first = min(one.first_ts_ms for one in self.ran if one.first_ts_ms)
        last = max(one.last_ts_ms for one in self.ran if one.last_ts_ms)
        out = [
            f"{read['bots_run']} of {read['bots']} bots ran over "
            f"{read['candles_read']} tablet candles.",
            f"{iso_stamp(first)} to {iso_stamp(last)}, "
            f"{read['ticks']} gate-chain evaluations.",
            f"{read['scrum_latched']} scrum latches and "
            f"{read['fold_latched']} fold latches.",
            f"{read['scrum_trades']} scrum sells and {read['fold_trades']} "
            f"fold buys filled, ${read['fees_usd']:,.2f} in fees.",
        ]
        if self.missing:
            out.append(
                f"{len(self.missing)} tablet(s) missing: "
                + ", ".join(f"{asset} on {venue}" for asset, venue in self.missing)
            )
        return opening + out + refused


def adapter_for(exchange_id: str, connector: Any) -> Any:
    """The shipped ``ExchangeAdapter`` subclass whose ``exchange_id`` matches.

    None comes back when no shipped adapter names ``exchange_id``.
    """
    from ..trading.stone_tablets.fetcher import CoinbaseAdapter, CoinGeckoAdapter

    for adapter_class in (CoinbaseAdapter, CoinGeckoAdapter):
        if adapter_class.exchange_id == str(exchange_id):
            return adapter_class(connector)
    return None


def missing_pairs(
    bots: Sequence[SimBot], entries: Sequence[Any]
) -> list[tuple[str, str]]:
    """Each ``(asset, exchange_id)`` a bot names that no entry in ``entries``
    covers."""
    out: list[tuple[str, str]] = []
    for bot in bots:
        if tablet_for(entries, bot.asset, bot.exchange_id) is None:
            key = (bot.asset, bot.exchange_id)
            if key not in out:
                out.append(key)
    return sorted(out)


def shared_step(entries: Sequence[Any], ticks_per_bot: int, max_candles: int) -> int:
    """One step in candles, sized off the longest tape so every bot ticks
    together.

    A ``ticks_per_bot`` of zero, or no entry, answers one.
    """
    if ticks_per_bot <= 0 or not entries:
        return 1
    longest = max(int(one.candle_count) for one in entries)
    if max_candles:
        longest = min(longest, int(max_candles))
    return max(1, longest // int(ticks_per_bot))


def run(
    bots: Sequence[SimBot],
    tablets: Any,
    exchange_id: str = "",
    step: int = 1,
    max_candles: int = 0,
    ticks_per_bot: int = 0,
    funding: str = FUNDED_BY_PROCEEDS,
    on_trade: Optional[TradeSink] = None,
    stop: Optional[Callable[[], bool]] = None,
    bus: Any = None,
) -> BackTestRun:
    """Walk every bot over its own tablet through ``_walk_fleet`` and write the
    pass through ``write_report`` onto ``BackTestRun.report``.

    ``max_candles``, ``step``, ``ticks_per_bot``, ``funding``, ``on_trade`` and
    ``stop`` reach ``_walk_fleet`` unchanged; ``bus`` becomes the
    ``RunEmitter`` every row of the pass goes through, under ``new_run_id``;
    a ``_walk_fleet`` that raises reaches ``write_partial`` with the exception
    and re-raises.
    """
    from .parity_report import BACK_TEST, new_run_id, write_partial, write_report

    emitter = RunEmitter(bus, new_run_id(BACK_TEST), BACK_TEST)
    try:
        outcome = _walk_fleet(
            bots,
            tablets,
            exchange_id,
            step,
            max_candles,
            ticks_per_bot,
            funding,
            on_trade,
            stop,
            emitter,
        )
    except Exception as exc:
        emitter.close()
        write_partial(
            BACK_TEST,
            exc,
            bots=bots,
            exchange_id=exchange_id,
            tablets=tablets,
            funding=funding,
            run_id=emitter.run_id,
        )
        raise
    outcome = replace(outcome, run_id=emitter.run_id, emitted=emitter.close())
    return replace(outcome, report=write_report(BACK_TEST, outcome, tablets))


def _walk_fleet(
    bots: Sequence[SimBot],
    tablets: Any,
    exchange_id: str,
    step: int,
    max_candles: int,
    ticks_per_bot: int,
    funding: str,
    on_trade: Optional[TradeSink] = None,
    stop: Optional[Callable[[], bool]] = None,
    emitter: Optional[RunEmitter] = None,
) -> BackTestRun:
    """Walk every bot over its own tablet and report what the gates latched.

    ``max_candles`` caps how much of each tape is read, ``ticks_per_bot``
    replaces ``step`` with one ``shared_step`` every bot ticks on, ``funding``
    of ``FUNDED_BY_TARGETS`` reads ``run_budget_usd`` once here and caps no
    fold, ``on_trade``, ``stop`` and ``emitter`` reach every ``walk`` and ``stop``
    is read before each bot as well, and a bot whose ``cited_rule_for`` answers
    no rule is ``UNCITED_RULE`` and walks nothing; ``emitter.bot_line`` names each
    bot that walks nothing.
    """
    from ..trading.indicators.types import candles_from_raw

    budget = run_budget_usd(bots) if funding == FUNDED_BY_TARGETS else None

    entries = tablets.entries()
    matched = [
        one
        for one in (tablet_for(entries, bot.asset, bot.exchange_id) for bot in bots)
        if one is not None
    ]
    if ticks_per_bot > 0:
        step = shared_step(matched, ticks_per_bot, max_candles)
    outcomes: dict[str, int] = {name: 0 for name in BOT_OUTCOMES}
    results: list[BotResult] = []
    interval_ms = 0
    halted = False
    for bot in bots:
        if stop is not None and stop():
            halted = True
            break
        class_name, venue, rule = cited_rule_for(bot.asset, bot.exchange_id)
        if rule is None:
            outcomes[UNCITED_RULE] += 1
            results.append(
                BotResult(
                    bot_id=bot.bot_id,
                    symbol=bot.symbol,
                    tablet_key="",
                    outcome=UNCITED_RULE,
                    asset_class=class_name,
                    venue=venue,
                )
            )
            if emitter is not None:
                emitter.bot_line(bot.bot_id, uncited_rule_line(results[-1]))
            continue
        entry = tablet_for(entries, bot.asset, bot.exchange_id)
        if entry is None:
            outcomes[NO_TABLET] += 1
            results.append(
                BotResult(
                    bot_id=bot.bot_id,
                    symbol=bot.symbol,
                    tablet_key="",
                    outcome=NO_TABLET,
                    asset_class=class_name,
                    venue=venue,
                    unit_rule=rule,
                )
            )
            if emitter is not None:
                emitter.bot_line(bot.bot_id, no_tablet_line(bot))
            continue
        raw = tablets.candles(entry)
        if max_candles:
            raw = raw[-int(max_candles) :]
        if not interval_ms and len(raw) > 1:
            interval_ms = candle_interval_ms([int(one[0]) for one in raw])
        walked = walk(
            bot,
            candles_from_raw(raw),
            step,
            funding,
            rule=rule,
            on_trade=on_trade,
            stop=stop,
            emitter=emitter,
        )
        halted = halted or walked.stopped
        key = entry.file
        if key.endswith(TABLET_SUFFIX):
            key = key[: -len(TABLET_SUFFIX)]
        results.append(
            BotResult(
                **{
                    **walked.__dict__,
                    "tablet_key": key,
                    "asset_class": class_name,
                    "venue": venue,
                }
            )
        )
        outcomes[walked.outcome] += 1
    return BackTestRun(
        exchange_id=exchange_id,
        bots=tuple(bots),
        results=tuple(results),
        missing=tuple(missing_pairs(bots, entries)),
        bot_outcomes=outcomes,
        interval_ms=interval_ms,
        funding=funding,
        budget_usd=budget,
        stopped=halted,
    )


async def download_missing(
    pairs: Sequence[tuple[str, str]],
    connector: Any,
    since_ms: int,
    until_ms: Optional[int] = None,
    quote_currency: str = "USD",
    registry: Any = None,
) -> list[Any]:
    """Fill each ``(asset, exchange_id)`` in ``pairs`` through the shipped
    ``GapFiller``.

    ``registry`` names the tablet root written into and a None ``connector``
    fills nothing.
    """
    from ..trading.stone_tablets.fetcher import GapFiller
    from ..trading.stone_tablets.registry import get_registry

    if connector is None:
        logger.warning("back_test: no connector, %d tablet(s) unfetched", len(pairs))
        return []
    store = registry if registry is not None else get_registry()
    until = int(until_ms if until_ms is not None else since_ms)
    reports: list[Any] = []
    for asset, exchange_id in pairs:
        adapter = adapter_for(exchange_id, connector)
        if adapter is None:
            logger.warning("back_test: no adapter for exchange %s", exchange_id)
            continue
        filler = GapFiller(store, adapter, quote_currency=quote_currency)
        reports.append(await filler.fill_asset(asset, int(since_ms), until))
    return reports


__all__ = [
    "BACK_TESTED",
    "BELOW_ONE_UNIT",
    "BOT_OUTCOMES",
    "BackTestRun",
    "BotResult",
    "DEFAULT_SCRUM_DETECT_PCT",
    "DEFAULT_TIMEFRAME",
    "DEFAULT_TRADING_FEE_PCT",
    "FOLD",
    "FUNDED_BY_PROCEEDS",
    "FUNDED_BY_TARGETS",
    "FUNDINGS",
    "MIN_CANDLES",
    "NEW_ORIGIN",
    "NO_TABLET",
    "SCRUM",
    "SHORT_TABLET",
    "TA_CONFIDENCE_FLOOR",
    "UNCITED_RULE",
    "WINDOW_CANDLES",
    "SimPosition",
    "SimTrade",
    "TradeSink",
    "apply_fold",
    "apply_scrum",
    "bb_detect_thresholds",
    "cited_rule_for",
    "download_missing",
    "fee_usd",
    "fill_action",
    "fill_side",
    "fold_taper",
    "missing_pairs",
    "new_bot",
    "new_bots",
    "no_tablet_line",
    "opening_position",
    "run",
    "run_budget_usd",
    "shared_step",
    "short_tablet_line",
    "signal_detail",
    "ta_direction",
    "tape_context",
    "trend_reading",
    "uncited_rule_line",
    "walk",
]
