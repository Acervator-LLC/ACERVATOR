"""Paper Mode: the shipped gate chains ticked at Live's cadence over the paper
exchange adapter, filled at the book against the unbounded fake budget.

``PaperRunner`` is the forked shape of the Simulator's ``_walk_bot``: one
worker thread per Start Paper Run that ticks every ``running`` paper bot each
``TICK_INTERVAL_S`` and works one every ``tick_skip`` ticks, reading the
adapter's ``ticker`` and ``candles`` on that thread and never on the GUI
thread. ``tick`` builds a ``GateContext`` through ``paper_tape_context``,
which prices the position at the ticker's last as Live's tick does and leaves
the candle window to the indicators, and evaluates it with ``latch``;
``apply_scrum`` and ``apply_fold`` are the Simulator's two fills forked over
``src.trading.scrumming.sizing`` and a ``FakeBalance``, a scrum filling at the
tick's ``best_bid`` and a fold at its ``best_ask`` with ``taker_fee_pct`` and
then compounding its surplus into the target through ``grow_target``.
``record`` files each ``PaperTick`` on the ``PaperRun`` with one ``paper_log``
row, the only file a run writes, and ``post_stats`` hands ``on_stats`` the
``stats_snapshot`` a host writes into the held record.

OVERTAKEN: "``apply_scrum`` and ``apply_fold`` are the Simulator's two fills
forked over ``src.trading.scrumming.sizing`` and a ``FakeBalance``".
``run_market_rules`` reads the ``MarketRules`` recorded for every bot's market at
``start``, and ``sized_order`` sizes both fills on those rules where they were
recorded and on the cited unit rule where they were not. Every ``PaperTrade``
carries the ``rule_source`` that sized it.

``route_fold_growth`` hands the growth ``grow_target`` applied to a
``PaperWireManager``, which moves each wire's share onto another paper bot's
fold tranches, and ``land_wire_credits`` spreads a pool parked for a bot whose
balance was not yet open.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional, Sequence

from ..simulator.back_test import (
    BEARISH,
    BULLISH,
    DEFAULT_TRADING_FEE_PCT,
    FOLD,
    FOLD_SIDE_WORD,
    MIN_CANDLES,
    SCRUM,
    SCRUM_SIDE_WORD,
    SNAPSHOT_END,
    SNAPSHOT_FILL,
    SNAPSHOT_START,
    SNAPSHOT_TICK,
    STOPPED_STATE,
    WINDOW_CANDLES,
    BotStatsSnapshot,
    bb_detect_thresholds,
    grow_target,
    reset_growth_cycle,
    signal_detail,
    stats_snapshot,
    ta_direction,
    trend_reading,
)
from ..exchange.base import MarketRules
from ..exchange.market_rules_store import recorded_rules
from ..simulator.validation import BB_MIDLINE, bb_reading, latch
from ..trading.container.config import BotState
from ..trading.gate_chain import GateContext
from ..trading.otd_math import fold_rebuy_factor
from ..trading.scrumming.sizing import (
    CLASS_CRYPTO,
    HELD_OUTSIDE_SESSION,
    HELD_UNSETTLED_CASH,
    cycle_growth_cap_usd,
    delta_below_interval,
    eligible_fold_tranches,
    estimated_fee_usd,
    fold_cap_remaining_usd,
    fold_rate_taper,
    fold_spend_usd,
    fold_surplus_usd,
    plan_fold_consumption,
    order_types_for,
    outside_session,
    plan_source_price,
    position_ceiling,
    priced_usd,
    ratio_to_ceiling,
    sale_proceeds_usd,
    scrumming_interval_usd,
    settle_fold_plan,
    sized_order,
    spend_less_unsettled_usd,
    target_delta_pct,
    target_delta_usd,
    trim_fold_plan,
    unit_rule,
    unsettled_usd,
    untradeable_reason,
    variant_refuses_sale,
    variant_trades_market,
    venue_session,
    venue_settlement_days,
)
from . import paper_log
from .fake_balance import FakeBalance, PaperLedger, opening_ledger
from .fleet_source import PaperBot
from .paper_wire import PaperWireManager

logger = logging.getLogger("acervator.paper.run")

NO_FEED_TEXT = "The live feed answered no candle."
NO_BOOK_TEXT = "The venue answered no ticker, so nothing can fill."
SHORT_FEED_FORMAT = "{symbol} answered {count} candles; {need} are needed."
NO_UNIT_RULE_FORMAT = (
    "{asset_class} on {venue} has no cited unit rule; nothing started."
)

STARTED = "started"
STOPPED = "stopped"
IDLE = "idle"
RUN_STATES = (IDLE, STARTED, STOPPED)

#: The seconds between two ticks of one bot, ``ScrummingBot.tick_interval``.
TICK_INTERVAL_S = 5.0

#: The venue's taker fee at the default tier, the rate a record with no
#: ``trading_fee_pct`` fills at; ``DEFAULT_TRADING_FEE_PCT`` in the Simulator.
TAKER_FEE_PCT = DEFAULT_TRADING_FEE_PCT

#: The ``scrum_target_mode`` values under which the worked tick comes ten
#: times as often, as ``ScrummingBot.tick`` reads them.
TRACK_MODES = ("track", "fire")

#: The name of the worker thread one Start Paper Run starts.
RUN_THREAD_NAME = "paper-run"

#: The record state the runner ticks; every other state is skipped.
RUNNING_STATE = BotState.RUNNING.value


def wall_clock_ms() -> int:
    """Wall-clock milliseconds now, the stamp every ``PaperTrade`` carries."""
    return int(time.time() * 1000)


class WallClock:
    """The one seam the runner reads time through: ``now`` in seconds and
    ``wait``, which sleeps ``seconds`` unless ``event`` is set first."""

    def now(self) -> float:
        """Seconds since the epoch, ``time.time``."""
        return time.time()

    def wait(self, event: threading.Event, seconds: float) -> bool:
        """``event.wait`` for ``seconds``; True when the event was set."""
        return event.wait(seconds)


WALL_CLOCK = WallClock()


@dataclass(frozen=True)
class PaperTrade:
    """One scrum sell or fold buy the tick produced against fake money:
    ``price`` is the ``bid`` on a scrum and the ``ask`` on a fold, ``last``
    the same read's last trade, ``delta_usd`` the Target Delta a scrum was
    sized on, ``eligible_usd`` and ``taper`` what a fold's spend was sized
    on, ``realized_usd`` a fold's ``fold_surplus_usd``, ``scrum_price`` the
    ``plan_source_price`` a fold re-entered against, and ``target_usd_after``
    the balance's target once ``grow_target`` has taken a fold's surplus."""

    bot_id: str
    symbol: str
    side: str
    candle_ts_ms: int
    wall_ms: int
    price: float
    units: float
    usd: float
    fee_usd: float
    realized_usd: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    rule: str = ""
    delta_usd: float = 0.0
    eligible_usd: float = 0.0
    taper: float = 0.0
    scrum_price: float = 0.0
    timeframe: str = ""
    target_usd_after: float = 0.0
    #: The ``sizing.RULE_SOURCE`` that sized ``units``: the market's own recorded
    #: rules, or the cited unit rule for its class and venue.
    rule_source: str = ""


@dataclass(frozen=True)
class PaperTick:
    """One gate-chain evaluation of one bot against the newest bar, with the
    ``bid``, ``ask`` and ``last`` of the ticker read that priced it."""

    bot_id: str
    symbol: str
    wall_ms: int
    candles_read: int
    price: float
    scrum_armed: bool
    fold_armed: bool
    filled: Optional[PaperTrade] = None
    refusal: str = ""
    #: Why ``sized_order`` refused the latched order, empty when none latched or
    #: the order filled.
    order_refusal: str = ""
    scrum_blockers: tuple[str, ...] = ()
    fold_blockers: tuple[str, ...] = ()
    scrum_fixture: dict = field(default_factory=dict)
    fold_fixture: dict = field(default_factory=dict)
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0


def tick_skip(scrum_read_rate_min: int, scrum_target_mode: Optional[str]) -> int:
    """How many ``TICK_INTERVAL_S`` ticks pass between two worked ticks, the
    rule ``ScrummingBot.tick`` applies: ``scrum_read_rate_min`` minutes over
    the tick, at least one, a tenth of that in ``TRACK_MODES``."""
    rate = max(0, int(scrum_read_rate_min or 0))
    if rate <= 0:
        return 1
    base = max(1, int((rate * 60) / max(TICK_INTERVAL_S, 0.1)))
    if str(scrum_target_mode or "") in TRACK_MODES:
        return max(1, base // 10)
    return base


def taker_fee_pct(bot: PaperBot) -> float:
    """``bot.trading_fee_pct`` when set, else ``TAKER_FEE_PCT``."""
    return float(bot.trading_fee_pct or TAKER_FEE_PCT)


def fold_taper(bot: PaperBot, balance: FakeBalance) -> float:
    """``fold_rate_taper`` over the balance's ``ratio_to_ceiling`` at its
    ``last_trade_price`` when the bot's ceiling is on and a trade has filled,
    one otherwise, the Simulator's ``fold_taper``."""
    if not bot.position_ceiling_enabled:
        return 1.0
    ceiling = position_ceiling(
        float(bot.target_usd or 0.0), bot.position_ceiling_multiple
    )
    if ceiling <= 0.0 or balance.last_trade_price <= 0.0:
        return 1.0
    value = balance.value_usd(balance.last_trade_price)
    return fold_rate_taper(ratio_to_ceiling(value, ceiling))


def paper_tape_context(
    bot: PaperBot,
    balance: FakeBalance,
    window: Sequence[Any],
    reading: Any,
    summary: Any,
    ticker_last: float,
    htf_bias_name: Optional[str] = None,
) -> GateContext:
    """A ``GateContext`` for the newest candle of ``window`` with the position
    priced at ``ticker_last``.

    The Simulator's ``tape_context`` prices the position at the newest bar's
    close, the only price a tape carries. Live's tick prices it at the
    ticker's last each ``tick_interval`` and reads the candle window for the
    indicators alone, so this fork takes ``ticker_last`` for ``ticker_last``,
    for the ``delta`` against the position's grown ``target_usd`` and for
    ``mem253_current_pos``, and leaves ``reading``, ``summary`` and ``window``
    to drive ``bb_pos``, every indicator and ``trend_reading``.
    """
    last = float(ticker_last)
    bb_pos = float(reading.bb_position) if reading is not None else 0.0
    lower_dt, upper_dt = bb_detect_thresholds(bot.scrum_detect_pct)
    target_usd = float(getattr(balance, "target_usd", 0.0) or bot.target_usd or 0.0)
    position_usd = balance.value_usd(last)
    delta = target_delta_usd(position_usd, target_usd)
    htf_blocks_scrum = htf_bias_name == BULLISH
    htf_blocks_fold = htf_bias_name == BEARISH
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
        ticker_last=last,
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
        eff_htf_blocks_scrum=htf_blocks_scrum if bot.scrum_defer_to_htf else False,
        eff_htf_blocks_fold=htf_blocks_fold if bot.fold_defer_to_htf else False,
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
        mem253_current_pos=position_usd,
        has_fold_tranches=balance.tranches > 0,
        n_fold_tranches=balance.tranches,
        htf_bias_name=htf_bias_name,
        htf_blocks_scrum=htf_blocks_scrum,
        htf_blocks_fold=htf_blocks_fold,
        scrumming_interval_pct=float(bot.scrumming_interval_pct),
        trading_fee_pct=float(bot.trading_fee_pct or DEFAULT_TRADING_FEE_PCT),
        ripe_scrum=banded and delta > 0 and not below_interval and above_upper,
        deep_fold=banded and delta < 0 and not below_interval and below_lower,
        adx=signal_detail(summary, "adx", "adx"),
        efficiency_ratio=signal_detail(summary, "kaufman_er", "er"),
        z_score=signal_detail(summary, "zscore", "z"),
    )


def route_fold_growth(wires: Any, bot_id: str, growth_usd: float, price: float) -> list:
    """Hand ``growth_usd`` to ``wires.distribute_fold_profit`` and answer its
    result rows.

    A manager that raises is logged and answers an empty list, leaving the
    growth booked on ``balance.target_usd``.
    """
    try:
        return list(
            wires.distribute_fold_profit(
                source_id=str(bot_id),
                profit_usd=float(growth_usd),
                ref=f"fold-compound@{float(price):.8f}",
            )
        )
    except Exception as exc:  # noqa: BLE001 - the growth stays booked locally
        logger.warning(
            "%s: paper wire fold route raised: %s; the fold growth stays booked",
            bot_id,
            exc,
        )
        return []


def land_wire_credits(wires: Any, bot_id: str, balance: FakeBalance) -> float:
    """Hand ``balance`` to ``wires.land_parked_credits`` and answer the USD
    that landed in ``balance.fold_tranches``.

    A manager that raises is logged and answers 0.0, leaving the pool parked.
    """
    try:
        return float(wires.land_parked_credits(str(bot_id), balance))
    except Exception as exc:  # noqa: BLE001 - the pool stays parked
        logger.warning(
            "%s: paper wire credit landing raised: %s; the pool stays parked",
            bot_id,
            exc,
        )
        return 0.0


# OVERTAKEN: "Sell ``scrum_units`` of ``delta`` at ``price``".
# ``sized_order`` sizes the sale: ``rules`` floors it onto the venue's recorded
# size step and refuses it under the venue's recorded minimum, and ``rule``
# sizes it only where ``rules`` holds no recorded size rule.
# ``variant_refuses_sale`` replaces ``variant_trades_market`` here, so a sale out
# of a market ``MarketRules.expires`` names still fills where a fold refuses.
def apply_scrum(
    bot: PaperBot,
    balance: FakeBalance,
    price: float,
    now_s: float,
    candle_ts_ms: int,
    delta: float,
    rule: str,
    rules: Optional[MarketRules] = None,
    on_refusal: Optional[Callable[[str], None]] = None,
    wires: Any = None,
) -> Optional[PaperTrade]:
    """Sell ``scrum_units`` of ``delta`` at ``price``, the tick's ``best_bid``,
    under ``rule`` from the highest-priced ``main_lots`` first, and queue the
    proceeds ``sale_proceeds_usd`` leaves after ``estimated_fee_usd`` as one
    fold tranche per lot sold from, the Simulator's ``apply_scrum`` over a
    ``FakeBalance``; nothing fills when the balance holds fewer units than
    the sell needs or a whole-unit ``delta`` buys under one unit.

    A ``wires`` manager lands its parked credits on the tranches the sale
    builds through ``land_wire_credits``."""
    if outside_session(getattr(rules, "session", None), float(now_s)):
        logger.info(
            "%s: a scrum of $%.2f is %s; nothing fills and nothing changes",
            bot.bot_id,
            abs(float(delta)),
            HELD_OUTSIDE_SESSION,
        )
        if on_refusal is not None:
            on_refusal(HELD_OUTSIDE_SESSION)
        return None
    # A sale out of a market the venue expires still fills, because a position
    # that cannot be sold cannot close before its expiry.
    if variant_refuses_sale(rules, float(price)):
        held = untradeable_reason(rules, float(price))
        logger.info(
            "%s: a scrum of $%.2f is read and not traded: %s",
            bot.bot_id,
            abs(float(delta)),
            held,
        )
        if on_refusal is not None:
            on_refusal(held)
        return None
    order = sized_order(abs(float(delta)) / float(price), rule, rules)
    units = order.units
    if units <= 0.0:
        logger.info(
            "%s: a scrum of $%.2f at %.8f is %s; nothing fills",
            bot.bot_id,
            abs(float(delta)),
            float(price),
            order.refusal,
        )
        if on_refusal is not None:
            on_refusal(order.refusal)
        return None
    if units > balance.units:
        return None
    notional = priced_usd(units, float(price))
    fee = estimated_fee_usd(notional, taker_fee_pct(bot))
    proceeds = sale_proceeds_usd(notional, fee)
    balance.units -= units
    balance.cash_usd += proceeds
    balance.last_trade_price = float(price)
    balance.last_trade_side = SCRUM_SIDE_WORD
    balance.main_lots.sort(
        key=lambda lot: float(lot.get("initial_buy_price", 0) or 0), reverse=True
    )
    remaining = units
    for lot in list(balance.main_lots):
        if remaining <= 1e-12:
            break
        take = min(float(lot.get("units", 0) or 0), remaining)
        if take <= 1e-12:
            continue
        balance.fold_tranches.append(
            {
                "usd": (take / units) * proceeds,
                "units": take,
                "ref": float(price),
                "initial_buy_price": float(lot.get("initial_buy_price", 0) or 0),
                "created_ts": float(now_s),
            }
        )
        balance.tranches_created += 1
        lot["units"] = float(lot.get("units", 0) or 0) - take
        remaining -= take
        if lot["units"] <= 1e-12:
            balance.main_lots.remove(lot)
    balance.total_trades += 1
    balance.total_sells += 1
    balance.scrum_sells += 1
    balance.total_scrummed_usd += notional
    balance.trade_volume += notional
    if wires is not None:
        land_wire_credits(wires, bot.bot_id, balance)
    return PaperTrade(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        side=SCRUM,
        candle_ts_ms=int(candle_ts_ms),
        wall_ms=int(now_s * 1000),
        price=float(price),
        units=units,
        usd=notional,
        fee_usd=fee,
        rule=rule,
        delta_usd=float(delta),
        scrum_price=float(price),
        timeframe=str(bot.ta_timeframe or ""),
        rule_source=order.source,
    )


# OVERTAKEN: "booked as ``fold_units`` at ``price`` under ``rule``".
# ``sized_order`` books the buy: ``rules`` floors the units onto the venue's
# recorded size step and refuses them under the venue's recorded minimum, and
# ``rule`` sizes them only where ``rules`` holds no recorded size rule.
# OVERTAKEN in apply_fold's docstring below: "spent as ``fold_spend_usd`` under
# ``fold_taper`` with no wallet cap".
# ``spend_less_unsettled_usd`` holds the spend to the cash ``unsettled_usd``
# leaves settled at the tick's ``now_s``, and answers the spend unchanged where
# the venue published no ``settlement_days``, so the wallet is still uncapped.
def apply_fold(
    bot: PaperBot,
    balance: FakeBalance,
    price: float,
    ticker_last: float,
    now_s: float,
    candle_ts_ms: int,
    rule: str,
    rules: Optional[MarketRules] = None,
    on_refusal: Optional[Callable[[str], None]] = None,
    wires: Any = None,
) -> Optional[PaperTrade]:
    """Rebuy the tranches ``eligible_fold_tranches`` names at ``ticker_last``
    under ``fold_rebuy_factor``, planned under ``cycle_growth_cap_usd`` by
    ``plan_fold_consumption``, spent as ``fold_spend_usd`` under
    ``fold_taper`` with no wallet cap, booked as ``fold_units`` at ``price``,
    the tick's ``best_ask``, under ``rule``, settled by ``settle_fold_plan``,
    the cash charged the spend plus ``estimated_fee_usd``, the bought units
    joining ``main_lots`` per consumed slice's share, and the surplus
    ``fold_surplus_usd`` reads carried as ``realized_usd``: the Simulator's
    ``apply_fold`` under ``FUNDED_BY_TARGETS`` over a ``FakeBalance``.

    ``grow_target`` then compounds that surplus into ``balance.target_usd``
    under the cycle cap, as ``_apply_fold_target_growth`` compounds a live
    bot's, and a ``wires`` manager takes that same growth figure to its wire
    targets through ``route_fold_growth``.
    """
    if outside_session(getattr(rules, "session", None), float(now_s)):
        logger.info(
            "%s: a fold is %s; nothing fills and the tranches stay queued",
            bot.bot_id,
            HELD_OUTSIDE_SESSION,
        )
        if on_refusal is not None:
            on_refusal(HELD_OUTSIDE_SESSION)
        return None
    if not variant_trades_market(rules, float(ticker_last)):
        held = untradeable_reason(rules, float(ticker_last))
        logger.info(
            "%s: a fold is read and not traded: %s; the tranches stay queued",
            bot.bot_id,
            held,
        )
        if on_refusal is not None:
            on_refusal(held)
        return None
    fee_pct = taker_fee_pct(bot)
    factor = fold_rebuy_factor(bot.scrumming_interval_pct, fee_pct)
    eligible = eligible_fold_tranches(balance.fold_tranches, float(ticker_last), factor)
    if not eligible:
        return None
    ordered = sorted(
        eligible, key=lambda t: -float(t.get("initial_buy_price", t.get("ref", 0)))
    )
    cap = cycle_growth_cap_usd(
        float(balance.target_usd),
        balance.cycle_cap_consumed_usd,
        bot.max_target_growth_pct,
    )
    plan, slices, _partial = plan_fold_consumption(
        ordered, fold_cap_remaining_usd(cap, balance.cycle_cap_consumed_usd)
    )
    if not slices:
        return None
    taper = fold_taper(bot, balance)
    if taper <= 0.0:
        return None
    eligible_usd = sum(one["usd"] for one in slices)
    spend = fold_spend_usd(eligible_usd, taper)
    # The tick's own ``now_s``, never a real clock read here. A sale the venue
    # has not settled has not returned its cash, so the fold may not spend it.
    unsettled = unsettled_usd(
        balance.fold_tranches,
        float(now_s),
        getattr(rules, "settlement_days", None),
    )
    spend = spend_less_unsettled_usd(spend, balance.cash_usd, unsettled)
    if spend <= 0.0:
        if unsettled > 0.0:
            logger.info(
                "%s: a fold finds $%.4f of $%.4f cash unsettled at %s day(s); "
                "nothing fills and the tranches stay queued",
                bot.bot_id,
                unsettled,
                balance.cash_usd,
                getattr(rules, "settlement_days", None),
            )
            if on_refusal is not None:
                on_refusal(HELD_UNSETTLED_CASH)
        return None
    order = sized_order(spend / float(price), rule, rules)
    units = order.units
    if units <= 0.0:
        logger.info(
            "%s: a fold of $%.2f at %.8f is %s; nothing fills",
            bot.bot_id,
            spend,
            float(price),
            order.refusal,
        )
        if on_refusal is not None:
            on_refusal(order.refusal)
        return None
    bought_usd = priced_usd(units, float(price))
    if bought_usd < spend:
        plan = trim_fold_plan(plan, spend - bought_usd)
        spend = bought_usd
    fee = estimated_fee_usd(spend, fee_pct)
    balance.units += units
    balance.cash_usd -= spend + fee
    balance.last_trade_price = float(price)
    balance.last_trade_side = FOLD_SIDE_WORD
    scrum_price = plan_source_price(plan)
    slice_units = sum(float(one.get("units", 0) or 0) for one in slices) + 1e-12
    for one in slices:
        balance.main_lots.append(
            {
                "units": units * (float(one.get("units", 0) or 0) / slice_units),
                "initial_buy_price": float(one.get("initial_buy_price", 0) or 0),
            }
        )
    balance.fold_tranches, removed, _spent = settle_fold_plan(
        balance.fold_tranches, plan
    )
    balance.tranches_closed += int(removed)
    balance.total_trades += 1
    balance.total_buys += 1
    balance.total_folded_usd += spend
    balance.trade_volume += spend
    realized = fold_surplus_usd(units, slices, float(price))
    growth = grow_target(bot, balance, units, slices, float(price), int(candle_ts_ms))
    if wires is not None and growth > 0.0:
        route_fold_growth(wires, bot.bot_id, growth, float(price))
    return PaperTrade(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        side=FOLD,
        candle_ts_ms=int(candle_ts_ms),
        wall_ms=int(now_s * 1000),
        price=float(price),
        units=units,
        usd=spend,
        fee_usd=fee,
        realized_usd=realized,
        rule=rule,
        eligible_usd=eligible_usd,
        taper=taper,
        scrum_price=scrum_price,
        timeframe=str(bot.ta_timeframe or ""),
        rule_source=order.source,
    )


def refusal_for(
    bot: PaperBot, candles: Sequence[Any], book: Optional[dict] = None
) -> str:
    """Why ``candles`` and ``book`` cannot be ticked, empty when they can."""
    if not candles:
        return NO_FEED_TEXT
    if len(candles) < MIN_CANDLES:
        return SHORT_FEED_FORMAT.format(
            symbol=bot.symbol, count=len(candles), need=MIN_CANDLES
        )
    if book is None or not (book.get("best_bid") and book.get("best_ask")):
        return NO_BOOK_TEXT
    return ""


# OVERTAKEN: "the ``fold_units`` the target buys as one lot at ``price``".
# ``sized_order`` sizes the opening buy, on ``rules`` where the venue's step was
# recorded and on ``rule`` where it was not.
def opening_balance(
    bot: PaperBot, price: float, rule: str, rules: Optional[MarketRules] = None
) -> FakeBalance:
    """A ``FakeBalance`` worth ``bot.target_usd`` at ``price`` under ``rule``,
    the ``fold_units`` the target buys as one lot at ``price``, plus
    ``cash_usd`` of the target, the bot's share of the unbounded budget."""
    target_usd = float(bot.target_usd or 0.0)
    units = (
        sized_order(target_usd / float(price), rule, rules).units
        if price > 0.0
        else 0.0
    )
    lots = [{"units": units, "initial_buy_price": float(price)}] if units > 0 else []
    return FakeBalance(
        units=units,
        cash_usd=target_usd,
        opening_price=float(price),
        main_lots=lots,
        target_usd=target_usd,
        anchor_target_usd=target_usd,
    )


def tick(
    bot: PaperBot,
    balance: FakeBalance,
    candles: Sequence[Any],
    book: Optional[dict],
    rule: str,
    now_s: float,
    engine: Any = None,
    rules: Optional[MarketRules] = None,
    wires: Any = None,
) -> PaperTick:
    """Evaluate the shipped chains against ``book``'s last trade over the
    newest bar of ``candles`` and fill what latched at ``book``'s
    ``best_bid`` or ``best_ask``, ``engine`` the ``VotingEngine`` the window
    is voted by; a refusal arms nothing.

    ``reset_growth_cycle`` reads the bar's band position before the context is
    built, as the Simulator's walk reads it, so the growth cycle and the gates
    see the same bar. ``wires`` reaches ``apply_scrum`` and ``apply_fold``
    unchanged.
    """
    from ..trading.ta_engine import VotingEngine

    held = dict(book or {})
    bid = float(held.get("best_bid") or 0.0)
    ask = float(held.get("best_ask") or 0.0)
    last = float(held.get("last") or 0.0)
    refusal = refusal_for(bot, candles, book)
    if refusal:
        close = float(candles[-1].close) if candles else 0.0
        return PaperTick(
            bot_id=bot.bot_id,
            symbol=bot.symbol,
            wall_ms=int(now_s * 1000),
            candles_read=len(candles),
            price=close,
            scrum_armed=False,
            fold_armed=False,
            refusal=refusal,
            bid=bid,
            ask=ask,
            last=last or close,
        )
    window = list(candles[-WINDOW_CANDLES:])
    reading = bb_reading(window, bot)
    voter = engine if engine is not None else VotingEngine()
    summary = voter.compute_all(window, bot.ta_timeframe, symbol=bot.symbol)
    close = float(window[-1].close)
    stamp = int(window[-1].timestamp)
    last = last or close
    reset_growth_cycle(balance, reading)
    context = paper_tape_context(bot, balance, window, reading, summary, last)
    armed = latch(context)
    filled = None
    refused: list[str] = []
    if armed["scrum_armed"]:
        filled = apply_scrum(
            bot,
            balance,
            bid,
            now_s,
            stamp,
            context.delta,
            rule,
            rules,
            refused.append,
            wires,
        )
    elif armed["fold_armed"]:
        filled = apply_fold(
            bot, balance, ask, last, now_s, stamp, rule, rules, refused.append, wires
        )
    if filled is not None:
        filled = replace(
            filled,
            bid=bid,
            ask=ask,
            last=last,
            target_usd_after=float(balance.target_usd),
        )
    return PaperTick(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        wall_ms=int(now_s * 1000),
        candles_read=len(window),
        price=close,
        scrum_armed=bool(armed["scrum_armed"]),
        fold_armed=bool(armed["fold_armed"]),
        filled=filled,
        order_refusal=refused[0] if refused else "",
        scrum_blockers=tuple(str(one) for one in armed["scrum_blockers"]),
        fold_blockers=tuple(str(one) for one in armed["fold_blockers"]),
        scrum_fixture=paper_log.scrum_fixture(context),
        fold_fixture=paper_log.fold_fixture(context),
        bid=bid,
        ask=ask,
        last=last,
    )


@dataclass
class PaperRun:
    """The fleet, its fake balances, its ledger and what the ticks produced.

    Every field lives in memory and the only file a run writes is the paper log
    under ``src.paper.paper_paths.PAPER_ROOT``.
    """

    bots: tuple[PaperBot, ...] = ()
    state: str = IDLE
    started_at_ms: int = 0
    rule: str = ""
    ledger: PaperLedger = field(default_factory=PaperLedger)
    balances: dict[str, FakeBalance] = field(default_factory=dict)
    last_price: dict[str, float] = field(default_factory=dict)
    trades: list[PaperTrade] = field(default_factory=list)
    ticks: list[PaperTick] = field(default_factory=list)
    refusals: dict[str, str] = field(default_factory=dict)
    ticks_made: int = 0
    #: The ``MarketRules`` recorded for each bot's market, by ``bot_id``, read
    #: once at ``start`` and handed to every ``tick``.
    market_rules: dict[str, MarketRules] = field(default_factory=dict)

    @property
    def running(self) -> bool:
        """True while ``state`` reads ``STARTED``."""
        return self.state == STARTED

    def figures(self) -> dict:
        """``ledger.figures`` over ``balances`` at ``last_price``."""
        return self.ledger.figures(self.balances, self.last_price)

    @property
    def summary(self) -> dict:
        """The counts the Paper pane reports."""
        return {
            "bots": len(self.bots),
            "bots_open": len(self.balances),
            "ticks": self.ticks_made,
            "worked": len(self.ticks),
            "scrum_armed": sum(1 for one in self.ticks if one.scrum_armed),
            "fold_armed": sum(1 for one in self.ticks if one.fold_armed),
            "scrum_trades": sum(1 for one in self.trades if one.side == SCRUM),
            "fold_trades": sum(1 for one in self.trades if one.side == FOLD),
            "fees_usd": sum(one.fee_usd for one in self.trades),
            "realized_usd": sum(one.realized_usd for one in self.trades),
            "budget_usd": self.ledger.fleet_target_usd,
        }

    def bot_for(self, bot_id: str) -> Optional[PaperBot]:
        """The bot whose ``bot_id`` is ``bot_id``, or None."""
        for bot in self.bots:
            if bot.bot_id == str(bot_id):
                return bot
        return None


def candles_for(feed: Any, bot: PaperBot) -> list[Any]:
    """``bot``'s live window from ``feed``, parsed for the voting engine."""
    from ..trading.indicators.types import candles_from_raw

    raw = feed.candles(bot.symbol, bot.ta_timeframe, WINDOW_CANDLES)
    return list(candles_from_raw(raw)) if raw else []


def run_rule(venue: str) -> Optional[str]:
    """``unit_rule`` for ``CLASS_CRYPTO`` on ``venue``, None when uncited."""
    return unit_rule(CLASS_CRYPTO, str(venue or ""))


def run_market_rules(bots: Sequence[PaperBot]) -> dict[str, MarketRules]:
    """The ``MarketRules`` recorded for each bot's market, by ``bot_id``.

    Every bot's own ``exchange_id`` is the venue that would execute its order,
    and a market with nothing recorded answers a ``MarketRules`` whose ``read``
    is False.
    """
    found: dict[str, MarketRules] = {}
    for bot in bots:
        recorded = recorded_rules(bot.exchange_id, bot.symbol)
        found[bot.bot_id] = replace(
            recorded,
            session=venue_session(CLASS_CRYPTO, bot.exchange_id),
            order_types=order_types_for(recorded, CLASS_CRYPTO, bot.exchange_id),
            settlement_days=venue_settlement_days(CLASS_CRYPTO, bot.exchange_id),
        )
    return found


def start(bots: Sequence[PaperBot], rule: str) -> PaperRun:
    """Mark a run started over ``bots`` under ``rule``, asking the feed for
    nothing yet; ``opening_ledger`` sets Paper Spendable and Paper Locked to
    the fleet's dollar target and each balance opens on its first worked tick."""
    return PaperRun(
        bots=tuple(bots),
        state=STARTED,
        started_at_ms=wall_clock_ms(),
        rule=rule,
        market_rules=run_market_rules(bots),
        ledger=opening_ledger(bots),
    )


def record(run: PaperRun, bot: PaperBot, seen: PaperTick) -> None:
    """File ``seen`` on ``run`` and append its row to the paper log."""
    run.ticks.append(seen)
    price = seen.last or seen.price
    if price > 0.0:
        run.last_price[bot.bot_id] = price
    if seen.filled is not None:
        run.trades.append(seen.filled)
        run.ledger.record_close(seen.filled.realized_usd)
    if seen.refusal:
        run.refusals[bot.bot_id] = seen.refusal
    else:
        run.refusals.pop(bot.bot_id, None)
    paper_log.append_row(paper_log.paper_row(seen, bot.exchange_id, run.figures()))


def stop(run: PaperRun) -> PaperRun:
    """Mark ``run`` stopped; its balances, ledger and trades stay readable."""
    run.state = STOPPED
    return run


class PaperRunner:
    """One worker thread ticking ``run``'s bots over ``exchange`` at Live's
    cadence: ``states`` answers each record's state so only ``RUNNING_STATE``
    bots tick, ``on_trade`` takes each ``PaperTrade``, ``on_tick`` each
    ``PaperTick``, ``on_stats`` each ``BotStatsSnapshot``, ``on_figures`` the
    ledger's figures after each worked pass, ``on_finished`` the run when the
    loop ends, ``say`` each line, and ``clock`` is the one seam time is read
    through.

    ``wires`` is the ``PaperWireManager`` the run routes fold growth over: each
    balance is held through ``attach_bot`` on the tick that opens it and given
    back through ``release_bot`` when the loop ends."""

    def __init__(
        self,
        run: PaperRun,
        exchange: Any,
        states: Callable[[], dict],
        on_trade: Optional[Callable[[PaperTrade], None]] = None,
        on_tick: Optional[Callable[[PaperTick], None]] = None,
        on_figures: Optional[Callable[[dict], None]] = None,
        on_finished: Optional[Callable[[PaperRun], None]] = None,
        on_stats: Optional[Callable[[BotStatsSnapshot], None]] = None,
        say: Optional[Callable[[str], None]] = None,
        clock: Optional[WallClock] = None,
        tick_interval_s: float = TICK_INTERVAL_S,
        wires: Optional[PaperWireManager] = None,
    ) -> None:
        from ..trading.ta_engine import VotingEngine

        self._wires = wires
        self._run = run
        self._exchange = exchange
        self._states = states
        self._on_trade = on_trade
        self._on_tick = on_tick
        self._on_figures = on_figures
        self._on_finished = on_finished
        self._on_stats = on_stats
        self._say = say
        self._clock = clock if clock is not None else WALL_CLOCK
        self._tick_interval_s = float(tick_interval_s)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._counters: dict[str, int] = {}
        self._engine = VotingEngine()

    @property
    def run(self) -> PaperRun:
        """The run this runner ticks."""
        return self._run

    @property
    def wires(self) -> Optional[PaperWireManager]:
        """The ``PaperWireManager`` this run routes fold growth over, or None."""
        return self._wires

    @property
    def thread(self) -> Optional[threading.Thread]:
        """The worker thread, None before ``start``."""
        return self._thread

    def running(self) -> bool:
        """True while the worker thread is alive."""
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> threading.Thread:
        """Start the ``RUN_THREAD_NAME`` daemon thread over ``_loop``."""
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name=RUN_THREAD_NAME, daemon=True
        )
        self._thread.start()
        return self._thread

    def stop(self) -> None:
        """Set the event the loop reads before each tick and each wait."""
        self._stop.set()

    def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                self.advance()
                if self._stop.is_set():
                    break
                self._clock.wait(self._stop, self._tick_interval_s)
        except Exception as exc:
            logger.exception("paper run failed: %s", exc)
            if self._say is not None:
                self._say(f"Paper run failed: {exc}")
        stop(self._run)
        self.close_stats()
        self.release_balances()
        if self._on_finished is not None:
            self._on_finished(self._run)

    def release_balances(self) -> int:
        """Give every attached balance back to ``_wires`` through
        ``release_bot`` and answer how many were held; the wires and the
        ledgers stay, so the next run routes over the same topology."""
        if self._wires is None:
            return 0
        released = 0
        for bot in self._run.bots:
            if self._wires.release_bot(bot.bot_id):
                released += 1
        return released

    def close_stats(self) -> int:
        """Post one ``SNAPSHOT_END`` snapshot per opened balance carrying
        ``STOPPED_STATE``, the mark the row reads after Stop Paper Run, and
        answer how many were posted."""
        posted = 0
        for bot in self._run.bots:
            balance = self._run.balances.get(bot.bot_id)
            if balance is None:
                continue
            price = self._run.last_price.get(bot.bot_id, balance.opening_price)
            if self.post_stats(
                bot, balance, float(price), None, SNAPSHOT_END, STOPPED_STATE
            ):
                posted += 1
        return posted

    def advance(self) -> list[PaperTick]:
        """One tick over every bot whose state reads ``RUNNING_STATE``: each
        counts one tick and is worked through ``work`` at its ``tick_skip``,
        the first tick after it starts running always worked, as
        ``ScrummingBot.tick`` throttles; ``on_figures`` is handed the ledger's
        figures when any bot was worked."""
        states = dict(self._states() or {})
        made: list[PaperTick] = []
        for bot in self._run.bots:
            if states.get(bot.bot_id) != RUNNING_STATE:
                self._counters.pop(bot.bot_id, None)
                continue
            self._run.ticks_made += 1
            skip = tick_skip(bot.scrum_read_rate_min, bot.scrum_target_mode)
            counter = self._counters.get(bot.bot_id)
            if counter is not None:
                counter += 1
                if counter < skip:
                    self._counters[bot.bot_id] = counter
                    continue
            self._counters[bot.bot_id] = 0
            made.append(self.work(bot))
            if self._stop.is_set():
                break
        if made and self._on_figures is not None:
            self._on_figures(self._run.figures())
        return made

    def work(self, bot: PaperBot) -> PaperTick:
        """One worked tick of ``bot``: the adapter's ``ticker`` and
        ``candles`` read on this thread, the balance opened at the read's
        ``last`` on the first, ``tick`` over them, ``record`` on the run,
        ``on_trade`` on a fill and ``on_tick`` after.

        ``post_stats`` carries the opening snapshot on the tick the balance
        opens, with ``SNAPSHOT_START`` and ``RUNNING_STATE``, and one snapshot
        after every tick, ``SNAPSHOT_FILL`` when it filled.

        The tick that opens a balance hands it to ``_wires.attach_bot`` and
        runs ``land_wire_credits`` once, so a share parked before this bot
        opened reaches the tranches it already holds.
        """
        book = self._exchange.ticker(bot.symbol)
        candles = candles_for(self._exchange, bot)
        balance = self._run.balances.get(bot.bot_id)
        market = self._run.market_rules.get(bot.bot_id)
        opened = False
        if balance is None and not refusal_for(bot, candles, book):
            price = float((book or {}).get("last") or candles[-1].close)
            balance = opening_balance(bot, price, self._run.rule, market)
            self._run.balances[bot.bot_id] = balance
            opened = True
            if self._wires is not None:
                self._wires.attach_bot(bot.bot_id, balance)
                land_wire_credits(self._wires, bot.bot_id, balance)
        held = balance or FakeBalance()
        seen = tick(
            bot,
            held,
            candles,
            book,
            self._run.rule,
            self._clock.now(),
            self._engine,
            market,
            self._wires,
        )
        record(self._run, bot, seen)
        priced = seen.last or seen.price
        if opened:
            self.post_stats(bot, held, priced, seen, SNAPSHOT_START, RUNNING_STATE)
        if seen.filled is not None and self._on_trade is not None:
            self._on_trade(seen.filled)
        if not seen.refusal:
            event = SNAPSHOT_FILL if seen.filled is not None else SNAPSHOT_TICK
            self.post_stats(bot, held, priced, seen, event)
        if self._on_tick is not None:
            self._on_tick(seen)
        return seen

    def post_stats(
        self,
        bot: PaperBot,
        balance: FakeBalance,
        price: float,
        seen: Optional[PaperTick],
        event: str,
        state: str = "",
    ) -> Optional[BotStatsSnapshot]:
        """Hand ``on_stats`` the ``stats_snapshot`` of ``balance`` at
        ``price``, the shape ``PaperFleetSource.write_stats`` writes into the
        held record; answers the snapshot, or None with no ``on_stats``.

        ``stats_snapshot`` is the Simulator's own builder over a duck-typed
        position, so a paper row and a simulated row carry the same keys.
        """
        if self._on_stats is None:
            return None
        stamp = int(seen.wall_ms) if seen is not None else int(self._clock.now() * 1000)
        snapshot = stats_snapshot(
            bot,
            balance,
            float(price),
            stamp,
            len(self._run.ticks),
            event,
            state=state,
        )
        self._on_stats(snapshot)
        return snapshot


__all__ = [
    "IDLE",
    "MIN_CANDLES",
    "NO_BOOK_TEXT",
    "NO_FEED_TEXT",
    "SNAPSHOT_END",
    "SNAPSHOT_FILL",
    "SNAPSHOT_START",
    "SNAPSHOT_TICK",
    "STOPPED_STATE",
    "BotStatsSnapshot",
    "paper_tape_context",
    "NO_UNIT_RULE_FORMAT",
    "RUN_STATES",
    "RUN_THREAD_NAME",
    "RUNNING_STATE",
    "STARTED",
    "STOPPED",
    "TAKER_FEE_PCT",
    "TICK_INTERVAL_S",
    "TRACK_MODES",
    "WALL_CLOCK",
    "WINDOW_CANDLES",
    "PaperRun",
    "PaperRunner",
    "PaperTick",
    "PaperTrade",
    "WallClock",
    "apply_fold",
    "apply_scrum",
    "candles_for",
    "fold_taper",
    "land_wire_credits",
    "opening_balance",
    "record",
    "refusal_for",
    "route_fold_growth",
    "run_market_rules",
    "run_rule",
    "start",
    "stop",
    "taker_fee_pct",
    "tick",
    "tick_skip",
    "wall_clock_ms",
]
