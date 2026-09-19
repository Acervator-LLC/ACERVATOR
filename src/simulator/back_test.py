"""The run modes' walk: the shipped gate chains over Stone Tablet candles, each
trade sized by ``src.trading.scrumming.sizing``.

``new_bot`` makes one operator-defined ``SimBot`` and ``fleet_source.live_fleet``
supplies the imported clone. ``tape_context`` builds a ``GateContext`` from a
tablet window, the simulated position's grown target and the higher-timeframe
bias ``weigh_higher_tf_bias`` reads over ``phantom_tapes`` (the walk's own
candles rolled up to each phantom timeframe through the registry's
``_rollup``), ``validation.latch`` evaluates the same scrum and fold chains
live runs, ``apply_scrum`` forms one fold tranche per lot it sells from and
``apply_fold`` rebuys the eligible tranches, books the bought lots and grows
the target by the surplus under ``cycle_growth_cap_usd`` with
``growth_cycle_side`` resetting the cycle, each sized with the Live bot's own
functions, and ``run`` walks each bot's tablet keeping units, lots, cash and
fold tranches under one ``funding`` (Back Test from each bot's own scrum
proceeds, Validation and Portfolio Battery from ``run_budget_usd``, the sum of
the held Target Balances), emitting a ``BotStatsSnapshot`` on the run's bus
under ``STATS_TOPIC`` every tick and every fill. ``cited_rule_for`` names the
unit rule a bot's class trades under on its venue, every fill is sized under
it, and a bot with no cited rule is ``UNCITED_RULE`` and walks nothing.
``missing_pairs`` names the tablets a run needs and ``download_missing`` fills
them through the shipped ``GapFiller``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional, Sequence

from ..core.signal_contract import emit as pin_emit
from ..trading.container.config import BotState
from ..trading.gate_chain import GateContext
from ..trading.otd_math import fold_rebuy_factor
from ..trading.scrumming.sizing import (
    GROWTH_SIDE_LOWER,
    WHOLE_UNITS,
    cycle_growth_cap_usd,
    delta_below_interval,
    eligible_fold_tranches,
    estimated_fee_usd,
    fold_cap_remaining_usd,
    fold_rate_taper,
    fold_spend_usd,
    fold_surplus_usd,
    fold_units,
    growth_cycle_side,
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
    target_growth_applied,
    trim_fold_plan,
    unit_rule,
    wallet_capped_spend_usd,
)
from ..trading.scrumming.sizing import estimated_fee_usd as fee_usd
from ..trading.stone_tablets.registry import _TF_SECONDS, _rollup
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

#: The bus topic every walk emits its ``BotStatsSnapshot`` on through the run
#: emitter's bus; each host subscribes to it and writes the held record.
STATS_TOPIC = "bot.stats"

#: The signals the walk emits through ``signal_contract``: the record's stats
#: written on a fill and at the walk's end, and the higher-timeframe bias per
#: candle, the latter admitted once per ``HTF_BIAS_PIN_EVERY_S`` per bot and on
#: every fill.
STATS_WRITTEN_SIGNAL = "sim.bot.stats_written"
HTF_BIAS_SIGNAL = "sim.bot.htf_bias"
HTF_BIAS_PIN_EVERY_S = 5.0

#: The candles one phantom reads, ``PhantomBot._tick``'s ``limit``, and the
#: fewest it sets a summary from, ``phantom_balance.MIN_TICK_CANDLES``.
PHANTOM_WINDOW_CANDLES = 100
PHANTOM_MIN_CANDLES = 30

#: The four snapshot events: the walk's opening, a tick, a fill, the walk's end.
SNAPSHOT_START = "start"
SNAPSHOT_TICK = "tick"
SNAPSHOT_FILL = "fill"
SNAPSHOT_END = "end"

#: Why a phantom timeframe the bot names reads no summary on a walk.
PHANTOMS_OFF = "phantoms off"
BELOW_PARENT = "at or below the walk's timeframe"
UNROLLED = "cannot roll up from the walk's timeframe"

SCRUM_SIDE_WORD = "SCRUM"
FOLD_SIDE_WORD = "FOLD"

#: The marks a walk's opening and closing snapshots carry, ``BotState``'s
#: ``running`` and ``stopped`` values, unit 31's end state.
RUNNING_STATE = BotState.RUNNING.value
STOPPED_STATE = BotState.STOPPED.value


@dataclass(frozen=True)
class SimTrade:
    """One scrum sell or fold buy the tape produced, with ``scrum_price`` the
    scrum's own ``price`` on a scrum and ``plan_source_price`` over the
    tranches consumed on a fold, zero naming no scrum. ``timeframe`` is the
    ``ta_timeframe`` the walk ran at, empty when unknown; ``htf_bias`` is the
    higher-timeframe bias name the fill's gates read, empty for none;
    ``target_usd_after`` the position's target after the fill and
    ``growth_applied_usd`` what the fill added to it."""

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
    htf_bias: str = ""
    target_usd_after: float = 0.0
    growth_applied_usd: float = 0.0


#: The seam ``walk`` hands each ``SimTrade`` to as it fills, as ``run_battery``
#: hands ``progress`` each portfolio's line.
TradeSink = Callable[[SimTrade], None]


@dataclass
class SimPosition:
    """What a simulated bot holds as the tape advances: its units and the
    ``main_lots`` they sit in, the cash its scrums left, the fold tranches
    those scrums queued in the shape ``_tick_execute_scrum`` builds them, the
    target its folds have grown from ``anchor_target_usd``, the growth cycle's
    consumed cap, standing surplus and side, and the counters
    ``BotStats`` carries on a live bot."""

    units: float = 0.0
    cash_usd: float = 0.0
    fold_tranches: list = field(default_factory=list)
    opening_price: float = 0.0
    last_trade_price: float = 0.0
    cycle_cap_consumed_usd: float = 0.0
    main_lots: list = field(default_factory=list)
    target_usd: float = 0.0
    anchor_target_usd: float = 0.0
    standing_surplus_usd: float = 0.0
    growth_side: Optional[str] = None
    last_trade_side: str = ""
    total_trades: int = 0
    total_buys: int = 0
    total_sells: int = 0
    total_scrummed_usd: float = 0.0
    total_folded_usd: float = 0.0
    trade_volume: float = 0.0
    tranches_created: int = 0
    tranches_closed: int = 0
    scrum_sells: int = 0
    growth_applied_usd: float = 0.0
    target_path: list = field(default_factory=list)

    @property
    def tranches(self) -> int:
        """How many fold tranches are queued."""
        return len(self.fold_tranches)

    def value_usd(self, price: float) -> float:
        """``units`` at ``price``, ignoring cash held from an earlier scrum."""
        return priced_usd(self.units, float(price))

    def cost_basis_usd(self) -> float:
        """Each lot's units at its ``initial_buy_price``, summed: the cost basis
        ``ScrummingBot.tick`` reads ``unrealised_pnl`` against."""
        return sum(
            float(lot.get("units", 0) or 0)
            * float(lot.get("initial_buy_price", 0) or 0)
            for lot in self.main_lots
        )

    def unrealised_pnl_usd(self, price: float) -> float:
        """``value_usd`` at ``price`` less ``cost_basis_usd``."""
        return self.value_usd(price) - self.cost_basis_usd()


@dataclass(frozen=True)
class BotStatsSnapshot:
    """What one walk wrote at one moment, in the two shapes the held record
    holds: ``stats`` in ``BotStats``'s keys and ``scrumming_state`` in the
    keys ``SimBotView`` reads; ``state`` is the mark the walk's start and end
    carry, empty on a tick or a fill."""

    bot_id: str
    symbol: str
    timeframe: str
    ts_ms: int
    tick: int
    event: str
    state: str
    stats: dict
    scrumming_state: dict


#: The seam a walk's ``BotStatsSnapshot`` reaches a host through.
StatsSink = Callable[[BotStatsSnapshot], None]


def stats_snapshot(
    bot: SimBot,
    position: SimPosition,
    price: float,
    ts_ms: int,
    tick: int,
    event: str,
    state: str = "",
) -> BotStatsSnapshot:
    """The ``BotStatsSnapshot`` of ``position`` at ``price``: the tick figures
    Live's tick writes (``current_price``, ``position_value``,
    ``unrealised_pnl``), the fill figures Live's fills write (the trade
    counts, the scrummed and folded sums, ``trade_volume``), and the
    ``scrumming_state`` keys the record holds, the lists copied."""
    stats = {
        "current_price": float(price),
        "position_value": position.value_usd(price),
        "unrealised_pnl": position.unrealised_pnl_usd(price),
        "total_trades": int(position.total_trades),
        "total_buys": int(position.total_buys),
        "total_sells": int(position.total_sells),
        "total_scrummed_usd": float(position.total_scrummed_usd),
        "total_folded_usd": float(position.total_folded_usd),
        "trade_volume": float(position.trade_volume),
        "standing_surplus_usd": float(position.standing_surplus_usd),
    }
    scrumming_state = {
        "target_balance": float(position.target_usd),
        "anchor_target_balance": float(position.anchor_target_usd),
        "quote_to_usd": 1.0,
        "main_lots": [dict(lot) for lot in position.main_lots],
        "fold_tranches": [dict(one) for one in position.fold_tranches],
        "stack_tranches": [],
        "fold_queue_usd": sum(
            float(one.get("usd", 0) or 0) for one in position.fold_tranches
        ),
        "fold_cycle_cap_consumed": float(position.cycle_cap_consumed_usd),
        "standing_surplus_usd": float(position.standing_surplus_usd),
        "target_grow_last_side": position.growth_side,
        "last_trade_price": float(position.last_trade_price),
        "last_trade_side": position.last_trade_side,
        "fold_accumulator": float(position.growth_applied_usd),
        "tranches_created_lifetime": int(position.tranches_created),
        "tranches_closed_lifetime": int(position.tranches_closed),
        "scrum_sells_lifetime": int(position.scrum_sells),
    }
    return BotStatsSnapshot(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        timeframe=str(bot.ta_timeframe or ""),
        ts_ms=int(ts_ms),
        tick=int(tick),
        event=str(event),
        state=str(state),
        stats=stats,
        scrumming_state=scrumming_state,
    )


def emit_stats(emitter: Optional[RunEmitter], snapshot: BotStatsSnapshot) -> bool:
    """Emit ``snapshot`` on ``emitter``'s bus under ``STATS_TOPIC`` with the
    run's stamp; answers whether it was emitted."""
    if emitter is None or not emitter.live:
        return False
    emitter.bus.emit(STATS_TOPIC, snapshot=snapshot, **emitter.stamp(snapshot.ts_ms))
    return True


class PhantomTape:
    """One phantom timeframe's candles, rolled from the walk's own rows
    through the registry's ``_rollup``: the completed buckets rolled once, the
    bucket holding the walk's candle rolled from its rows up to that candle on
    each read, so no later row reaches a window."""

    def __init__(self, rows: Sequence[Sequence[float]], timeframe: str, factor: int):
        self.timeframe = str(timeframe)
        self.factor = int(factor)
        self.bucket_ms = _TF_SECONDS[self.timeframe] * 1000
        self.rows = [list(row) for row in rows]
        self.keys = [
            (int(row[0]) // self.bucket_ms) * self.bucket_ms for row in self.rows
        ]
        self.complete = _rollup(self.rows, self.factor, self.bucket_ms)
        self.complete_index = {int(row[0]): n for n, row in enumerate(self.complete)}
        self.starts: dict[int, int] = {}
        for n, key in enumerate(self.keys):
            self.starts.setdefault(key, n)

    @property
    def rank(self) -> int:
        """``tf_rank`` of ``timeframe``."""
        from ..trading.phantom_balance import tf_rank

        return tf_rank(self.timeframe)

    def window(self, index: int) -> list[list[float]]:
        """The last ``PHANTOM_WINDOW_CANDLES`` rolled candles up to and
        including the walk's candle at ``index``."""
        key = self.keys[index]
        partial = _rollup(
            self.rows[self.starts[key] : index + 1], self.factor, self.bucket_ms
        )
        earlier_count = self.complete_index[key]
        earlier = self.complete[
            max(
                0, earlier_count - (PHANTOM_WINDOW_CANDLES - len(partial))
            ) : earlier_count
        ]
        return (earlier + partial)[-PHANTOM_WINDOW_CANDLES:]

    def summary(self, index: int, engine: Any) -> Any:
        """``engine.compute_all`` over ``window`` at ``index`` on
        ``timeframe``, as ``PhantomBot._tick`` computes it; None under
        ``PHANTOM_MIN_CANDLES`` rolled candles."""
        from ..trading.indicators.types import candles_from_raw

        window = self.window(index)
        if len(window) < PHANTOM_MIN_CANDLES:
            return None
        return engine.compute_all(candles_from_raw(window), self.timeframe)


def phantom_timeframes_for(bot: SimBot, walk_timeframe: str) -> list[str]:
    """The phantom timeframes Live's bot would run for ``bot`` at
    ``walk_timeframe``: the record's own, or ``default_phantom_timeframes``
    above the walk's timeframe when it names none."""
    from ..trading.phantom_balance import default_phantom_timeframes

    named = [str(one) for one in (bot.phantom_timeframes or ()) if str(one)]
    if named:
        return named
    return list(default_phantom_timeframes(str(walk_timeframe)))


def phantom_tapes(
    bot: SimBot, rows: Sequence[Sequence[float]], walk_timeframe: str
) -> tuple[list[PhantomTape], dict[str, str]]:
    """One ``PhantomTape`` per phantom timeframe of ``bot`` the walk's ``rows``
    at ``walk_timeframe`` can roll up to, and the timeframes refused by name:
    every one under ``PHANTOMS_OFF`` when the record's phantoms are off,
    ``BELOW_PARENT`` for one ranked at or under the walk's own, ``UNROLLED``
    for one outside the registry's table or not a whole multiple of it."""
    from ..trading.phantom_balance import tf_rank

    refused: dict[str, str] = {}
    tapes: list[PhantomTape] = []
    wanted = phantom_timeframes_for(bot, walk_timeframe)
    if not bot.phantoms_enabled:
        return [], {one: PHANTOMS_OFF for one in wanted}
    walk_rank = tf_rank(str(walk_timeframe))
    walk_seconds = _TF_SECONDS.get(str(walk_timeframe))
    for timeframe in wanted:
        if tf_rank(timeframe) <= walk_rank:
            refused[timeframe] = BELOW_PARENT
            continue
        seconds = _TF_SECONDS.get(timeframe)
        if (
            walk_seconds is None
            or seconds is None
            or seconds % walk_seconds
            or seconds // walk_seconds <= 1
        ):
            refused[timeframe] = UNROLLED
            continue
        tapes.append(PhantomTape(rows, timeframe, seconds // walk_seconds))
    return tapes, refused


def higher_tf_bias(
    tapes: Sequence[PhantomTape], index: int, engine: Any
) -> tuple[Optional[str], dict]:
    """The bias name the tick's gates read at ``index`` and the per-timeframe
    detail: each tape's ``summary``, weighed through
    ``weigh_higher_tf_bias`` as ``get_higher_tf_bias`` weighs the registered
    phantoms; None with no summary, as Live reads with no phantom."""
    from ..trading.phantom_balance import weigh_higher_tf_bias

    phantoms: dict[str, Any] = {}
    higher = []
    for tape in tapes:
        summary = tape.summary(index, engine)
        if summary is None:
            phantoms[tape.timeframe] = "no summary"
            continue
        phantoms[tape.timeframe] = {
            "direction": summary.consensus_direction.name,
            "conf": round(float(summary.consensus_confidence), 4),
        }
        higher.append((tape.timeframe, tape.rank, summary))
    direction, detail = weigh_higher_tf_bias(higher, [])
    return (None if direction is None else str(direction.name)), {
        "phantoms": phantoms,
        "weighing": detail,
    }


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
    #: The position's target at the walk's end, grown from the bot's own.
    end_target_usd: float = 0.0
    #: The ``stats`` of the walk's last ``BotStatsSnapshot``.
    stats: dict = field(default_factory=dict)
    #: One entry per fold that grew the target: the step's figures.
    target_path: tuple = ()
    #: The phantom timeframes evaluated, those refused by name, and the bias
    #: counts over the ticks.
    htf: dict = field(default_factory=dict)

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
    position: Any,
    window: Sequence[Any],
    reading: Any,
    summary: Any,
    htf_bias_name: Optional[str] = None,
) -> GateContext:
    """A ``GateContext`` for the last candle of ``window`` and the ``position``
    holding it.

    The tape drives ``ticker_last``, ``bb_pos`` and every indicator;
    ``position`` drives ``delta`` (against its own grown ``target_usd``, the
    bot's when it holds none) and ``n_fold_tranches``; ``htf_bias_name`` sets
    the higher-timeframe fields as ``ScrummingBot.tick`` sets them off the
    coordinator's bias, blocking a scrum on ``BULLISH`` and a fold on
    ``BEARISH`` under the two defer flags; the circuit breaker and hysteresis
    fields read as not populated.
    """
    close = float(window[-1].close)
    bb_pos = float(reading.bb_position) if reading is not None else 0.0
    lower_dt, upper_dt = bb_detect_thresholds(bot.scrum_detect_pct)
    target_usd = float(getattr(position, "target_usd", 0.0) or bot.target_usd or 0.0)
    delta = target_delta_usd(position.value_usd(close), target_usd)
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
        mem253_current_pos=position.value_usd(close),
        has_fold_tranches=position.tranches > 0,
        n_fold_tranches=position.tranches,
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


def apply_scrum(
    bot: SimBot,
    position: SimPosition,
    price: float,
    ts_ms: int,
    delta: float,
    rule: str,
) -> Optional[SimTrade]:
    """Sell ``scrum_units`` of ``delta`` at ``price`` under ``rule`` from the
    highest-priced ``main_lots`` first and queue the proceeds net of
    ``estimated_fee_usd`` as one fold tranche per lot sold from, each
    carrying that lot's ``initial_buy_price``, as ``_tick_execute_scrum``
    books a sale over the lots; the trade counters move as Live's fill moves
    them.

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
    position.last_trade_side = SCRUM_SIDE_WORD
    position.main_lots.sort(
        key=lambda lot: float(lot.get("initial_buy_price", 0) or 0), reverse=True
    )
    remaining = units
    for lot in list(position.main_lots):
        if remaining <= 1e-12:
            break
        take = min(float(lot.get("units", 0) or 0), remaining)
        if take <= 1e-12:
            continue
        position.fold_tranches.append(
            {
                "usd": (take / units) * proceeds,
                "units": take,
                "ref": float(price),
                "initial_buy_price": float(lot.get("initial_buy_price", 0) or 0),
                "created_ts": float(ts_ms) / 1000.0,
            }
        )
        position.tranches_created += 1
        lot["units"] = float(lot.get("units", 0) or 0) - take
        remaining -= take
        if lot["units"] <= 1e-12:
            position.main_lots.remove(lot)
    position.total_trades += 1
    position.total_sells += 1
    position.scrum_sells += 1
    position.total_scrummed_usd += notional
    position.trade_volume += notional
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
    logs ``BELOW_ONE_UNIT`` when the spend buys under one unit. The bought
    units join ``main_lots`` per consumed tranche's share, and the surplus
    ``fold_surplus_usd`` reads grows ``position.target_usd`` through
    ``target_growth_applied`` under the cycle cap, as
    ``_apply_fold_target_growth`` grows a live bot's target.
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
        float(position.target_usd),
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
    position.last_trade_side = FOLD_SIDE_WORD
    scrum_price = plan_source_price(plan)
    slice_units = sum(float(one.get("units", 0) or 0) for one in slices) + 1e-12
    for one in slices:
        position.main_lots.append(
            {
                "units": units * (float(one.get("units", 0) or 0) / slice_units),
                "initial_buy_price": float(one.get("initial_buy_price", 0) or 0),
            }
        )
    position.fold_tranches, removed, _spent = settle_fold_plan(
        position.fold_tranches, plan
    )
    position.tranches_closed += int(removed)
    position.total_trades += 1
    position.total_buys += 1
    position.total_folded_usd += spend
    position.trade_volume += spend
    growth = grow_target(bot, position, units, slices, float(price), int(ts_ms))
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
        target_usd_after=float(position.target_usd),
        growth_applied_usd=growth,
    )


def grow_target(
    bot: SimBot,
    position: SimPosition,
    units_bought: float,
    slices: list,
    price: float,
    ts_ms: int,
) -> float:
    """Grow ``position.target_usd`` by the fold's surplus as
    ``_apply_fold_target_growth`` grows a live bot's: ``fold_surplus_usd``
    over the consumed ``slices``, ``target_growth_applied`` under what
    ``cycle_growth_cap_usd`` leaves of the cycle, the applied growth added to
    the target and to the consumed cap, the rest parked as standing surplus,
    the growth side set to ``GROWTH_SIDE_LOWER``; nothing moves with
    ``profit_folding_active`` off. Answers the growth applied and records the
    step on ``position.target_path``.
    """
    if not bot.profit_folding_active:
        return 0.0
    surplus = fold_surplus_usd(units_bought, slices, price)
    standing_before = float(position.standing_surplus_usd)
    if surplus <= 1e-9 and standing_before <= 1e-9:
        return 0.0
    target_before = float(position.target_usd)
    consumed_before = float(position.cycle_cap_consumed_usd)
    cap = cycle_growth_cap_usd(
        target_before, consumed_before, bot.max_target_growth_pct
    )
    cap_remaining = fold_cap_remaining_usd(cap, consumed_before)
    applied, standing_after = target_growth_applied(
        surplus, standing_before, cap_remaining
    )
    position.standing_surplus_usd = standing_after
    if applied <= 0.0:
        return 0.0
    position.target_usd = target_before + applied
    position.cycle_cap_consumed_usd = consumed_before + applied
    position.growth_side = GROWTH_SIDE_LOWER
    position.growth_applied_usd += applied
    position.target_path.append(
        {
            "ts_ms": int(ts_ms),
            "candle_at": iso_stamp(ts_ms),
            "surplus_usd": surplus,
            "standing_before": standing_before,
            "growth_pct": float(bot.max_target_growth_pct),
            "cap_usd": cap,
            "consumed_before": consumed_before,
            "cap_remaining": cap_remaining,
            "applied_usd": applied,
            "target_before": target_before,
            "target_after": float(position.target_usd),
            "standing_after": standing_after,
        }
    )
    return applied


def reset_growth_cycle(position: SimPosition, reading: Any) -> bool:
    """The tick's growth-cycle check over ``reading.bb_position`` through
    ``growth_cycle_side``: the side moves as Live's tick moves it and the
    consumed cap zeroes when the opposite extreme is reached; answers whether
    it reset. Nothing moves with no ``reading``."""
    if reading is None:
        return False
    side, reset = growth_cycle_side(position.growth_side, float(reading.bb_position))
    position.growth_side = side
    if reset and position.cycle_cap_consumed_usd > 1e-9:
        position.cycle_cap_consumed_usd = 0.0
    return reset


def opening_position(bot: SimBot, price: float, rule: str) -> SimPosition:
    """A ``SimPosition`` worth ``bot.target_usd`` at ``price`` under ``rule``,
    the ``fold_units`` the initial entry's buy of the target books as one lot
    at ``price``, its target and anchor the bot's own."""
    target_usd = float(bot.target_usd or 0.0)
    units = fold_units(target_usd, float(price), rule) if price > 0.0 else 0.0
    lots = [{"units": units, "initial_buy_price": float(price)}] if units > 0 else []
    return SimPosition(
        units=units,
        cash_usd=0.0,
        opening_price=float(price),
        main_lots=lots,
        target_usd=target_usd,
        anchor_target_usd=target_usd,
    )


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
    on_tick: Optional[Callable[[int, int, int], None]] = None,
) -> BotResult:
    """Run ``bot`` over ``candles``, one gate-chain evaluation every ``step``
    bars, each fold funded as ``funding`` says and every fill sized under
    ``rule``; ``on_trade`` is handed each ``SimTrade`` the moment it fills,
    ``emitter`` emits ``trade_filled``, ``bot_line``, ``voting_snapshot`` and
    ``gate_decision`` on every tick in Live's fire order and a
    ``BotStatsSnapshot`` under ``STATS_TOPIC`` at the walk's start, on every
    tick, on every fill and at its end, ``on_tick`` is handed the bar reached,
    the bars in the tape and the ticks so far after each tick, and ``stop``
    answering True before a tick ends the walk at the last bar ticked with
    ``stopped`` set. Each tick reads the higher-timeframe bias over
    ``phantom_tapes`` and the growth cycle over the tick's Bollinger reading
    before its gates, as ``ScrummingBot.tick`` orders them."""
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
    phantom_engine = VotingEngine()
    timeframe = bot.ta_timeframe or DEFAULT_TIMEFRAME
    rows = [
        [one.timestamp, one.open, one.high, one.low, one.close, one.volume]
        for one in candles
    ]
    tapes, refused = phantom_tapes(bot, rows, timeframe)
    for name, reason in refused.items():
        logger.info("%s: phantom %s reads no summary: %s", bot.bot_id, name, reason)
    bias_counts: dict[str, int] = {}
    position = opening_position(bot, float(candles[MIN_CANDLES - 1].close), rule)
    start_units = position.units
    trades: list[SimTrade] = []
    scrum_latched = 0
    fold_latched = 0
    ticks = 0
    fees = 0.0
    halted = False
    last_index = MIN_CANDLES - 1
    opening = stats_snapshot(
        bot,
        position,
        position.opening_price,
        int(candles[MIN_CANDLES - 1].timestamp),
        0,
        SNAPSHOT_START,
        state=RUNNING_STATE,
    )
    emit_stats(emitter, opening)
    run_id = emitter.run_id if emitter is not None else ""
    for index in range(MIN_CANDLES - 1, len(candles), max(int(step), 1)):
        if stop is not None and stop():
            halted = True
            break
        last_index = index
        window = list(candles[max(0, index + 1 - WINDOW_CANDLES) : index + 1])
        reading = bb_reading(window, bot)
        summary = engine.compute_all(window, timeframe, symbol=bot.symbol)
        htf_name, htf_detail = higher_tf_bias(tapes, index, phantom_engine)
        bias_counts[str(htf_name)] = bias_counts.get(str(htf_name), 0) + 1
        reset_growth_cycle(position, reading)
        context = tape_context(bot, position, window, reading, summary, htf_name)
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
            filled = replace(
                filled,
                htf_bias=str(htf_name or ""),
                target_usd_after=float(position.target_usd),
            )
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
        snapshot = stats_snapshot(
            bot,
            position,
            price,
            stamp,
            ticks,
            SNAPSHOT_FILL if filled is not None else SNAPSHOT_TICK,
        )
        emit_stats(emitter, snapshot)
        pin_htf_bias(
            bot, stamp, htf_name, context, htf_detail, refused, filled is not None
        )
        if filled is not None:
            pin_stats_written(snapshot, len(trades), run_id)
        if on_tick is not None:
            on_tick(index + 1, len(candles), ticks)
    end_index = last_index if halted else len(candles) - 1
    end_price = float(candles[end_index].close)
    closing = stats_snapshot(
        bot,
        position,
        end_price,
        int(candles[end_index].timestamp),
        ticks,
        SNAPSHOT_END,
        state=STOPPED_STATE,
    )
    emit_stats(emitter, closing)
    pin_stats_written(closing, len(trades), run_id)
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
        end_price=end_price,
        cash_usd=position.cash_usd,
        fees_usd=fees,
        first_ts_ms=int(candles[0].timestamp),
        last_ts_ms=int(candles[end_index].timestamp),
        unit_rule=rule,
        stopped=halted,
        end_target_usd=float(position.target_usd),
        stats=dict(closing.stats),
        target_path=tuple(dict(one) for one in position.target_path),
        htf={
            "phantoms_enabled": bool(bot.phantoms_enabled),
            "named": phantom_timeframes_for(bot, timeframe),
            "evaluated": [one.timeframe for one in tapes],
            "refused": dict(refused),
            "bias_counts": bias_counts,
        },
    )


def pin_htf_bias(
    bot: SimBot,
    stamp: int,
    htf_name: Optional[str],
    context: GateContext,
    detail: dict,
    refused: dict,
    on_fill: bool,
) -> None:
    """Emit ``HTF_BIAS_SIGNAL`` for one tick: the bias and the two block flags
    the gates read, each phantom's reading or refusal, against the timeframes
    the bot names; ``ok`` when every named timeframe was evaluated or refused
    by name. A fill's tick lands unthrottled; the rest once per
    ``HTF_BIAS_PIN_EVERY_S`` per bot."""
    phantoms = dict(detail.get("phantoms") or {})
    named = list(bot.phantom_timeframes or ()) or list(phantoms) + list(refused)
    covered = set(phantoms) | set(refused)
    pin_emit(
        HTF_BIAS_SIGNAL,
        actual={
            "bot": bot.bot_id,
            "candle": iso_stamp(stamp),
            "bias": htf_name,
            "blocks_scrum": bool(context.htf_blocks_scrum),
            "blocks_fold": bool(context.htf_blocks_fold),
            "eff_blocks_scrum": bool(context.eff_htf_blocks_scrum),
            "eff_blocks_fold": bool(context.eff_htf_blocks_fold),
            "phantoms": phantoms,
            "refused": dict(refused),
        },
        expected={"timeframes": named},
        ok=all(one in covered for one in named),
        context={"bot_id": bot.bot_id, "on_fill": bool(on_fill)},
        every=0.0 if on_fill else HTF_BIAS_PIN_EVERY_S,
        instance=bot.bot_id,
    )


def pin_stats_written(snapshot: BotStatsSnapshot, fills: int, run_id: str) -> None:
    """Emit ``STATS_WRITTEN_SIGNAL`` for ``snapshot``: the bot, the tick, the
    fills and the fields moved, against the fill count off the trades;
    ``ok`` when the snapshot's trade count equals it."""
    stats = snapshot.stats
    pin_emit(
        STATS_WRITTEN_SIGNAL,
        actual={
            "bot": snapshot.bot_id,
            "tick": snapshot.tick,
            "event": snapshot.event,
            "fills": int(stats.get("total_trades", 0)),
            "fields": {
                "current_price": stats.get("current_price"),
                "position_value": stats.get("position_value"),
                "unrealised_pnl": stats.get("unrealised_pnl"),
                "total_scrummed_usd": stats.get("total_scrummed_usd"),
                "total_folded_usd": stats.get("total_folded_usd"),
                "target_balance": snapshot.scrumming_state.get("target_balance"),
                "fold_tranches": len(
                    snapshot.scrumming_state.get("fold_tranches") or []
                ),
            },
        },
        expected={"fills": int(fills)},
        ok=int(stats.get("total_trades", 0)) == int(fills),
        context={"bot_id": snapshot.bot_id, "run_id": run_id, "state": snapshot.state},
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
    "BELOW_PARENT",
    "BOT_OUTCOMES",
    "BackTestRun",
    "BotResult",
    "BotStatsSnapshot",
    "DEFAULT_SCRUM_DETECT_PCT",
    "DEFAULT_TIMEFRAME",
    "DEFAULT_TRADING_FEE_PCT",
    "FOLD",
    "FUNDED_BY_PROCEEDS",
    "FUNDED_BY_TARGETS",
    "FUNDINGS",
    "HTF_BIAS_PIN_EVERY_S",
    "HTF_BIAS_SIGNAL",
    "MIN_CANDLES",
    "NEW_ORIGIN",
    "NO_TABLET",
    "PHANTOMS_OFF",
    "PHANTOM_MIN_CANDLES",
    "PHANTOM_WINDOW_CANDLES",
    "PhantomTape",
    "RUNNING_STATE",
    "SCRUM",
    "SHORT_TABLET",
    "SNAPSHOT_END",
    "SNAPSHOT_FILL",
    "SNAPSHOT_START",
    "SNAPSHOT_TICK",
    "STATS_TOPIC",
    "STATS_WRITTEN_SIGNAL",
    "STOPPED_STATE",
    "StatsSink",
    "TA_CONFIDENCE_FLOOR",
    "UNCITED_RULE",
    "UNROLLED",
    "WINDOW_CANDLES",
    "SimPosition",
    "SimTrade",
    "TradeSink",
    "apply_fold",
    "apply_scrum",
    "bb_detect_thresholds",
    "cited_rule_for",
    "download_missing",
    "emit_stats",
    "fee_usd",
    "fill_action",
    "fill_side",
    "fold_taper",
    "grow_target",
    "higher_tf_bias",
    "missing_pairs",
    "new_bot",
    "new_bots",
    "no_tablet_line",
    "opening_position",
    "phantom_tapes",
    "phantom_timeframes_for",
    "pin_htf_bias",
    "pin_stats_written",
    "reset_growth_cycle",
    "run",
    "run_budget_usd",
    "shared_step",
    "short_tablet_line",
    "signal_detail",
    "stats_snapshot",
    "ta_direction",
    "tape_context",
    "trend_reading",
    "uncited_rule_line",
    "walk",
]
