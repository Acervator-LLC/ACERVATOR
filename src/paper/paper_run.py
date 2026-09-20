"""Paper Mode: the shipped gate chains ticked at Live's cadence over the paper
exchange adapter, filled at the book against the unbounded fake budget.

``PaperRunner`` is the forked shape of the Simulator's ``_walk_bot``: one
worker thread per Start Paper Run that ticks every ``running`` paper bot each
``TICK_INTERVAL_S`` and works one every ``tick_skip`` ticks, reading the
adapter's ``ticker`` and ``candles`` on that thread and never on the GUI
thread. ``tick`` builds a ``GateContext`` through ``tape_context`` and
evaluates it with ``latch``, ``apply_scrum`` and ``apply_fold`` are the
Simulator's two fills forked over ``src.trading.scrumming.sizing`` and a
``FakeBalance``, a scrum filling at the tick's ``best_bid`` and a fold at its
``best_ask`` with ``taker_fee_pct``, and ``record`` files each ``PaperTick``
on the ``PaperRun`` with one ``paper_log`` row, the only file a run writes.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional, Sequence

from ..simulator.back_test import (
    BELOW_ONE_UNIT,
    DEFAULT_TRADING_FEE_PCT,
    FOLD,
    FOLD_SIDE_WORD,
    MIN_CANDLES,
    SCRUM,
    SCRUM_SIDE_WORD,
    WINDOW_CANDLES,
    tape_context,
)
from ..simulator.validation import bb_reading, latch
from ..trading.container.config import BotState
from ..trading.otd_math import fold_rebuy_factor
from ..trading.scrumming.sizing import (
    CLASS_CRYPTO,
    WHOLE_UNITS,
    cycle_growth_cap_usd,
    eligible_fold_tranches,
    estimated_fee_usd,
    fold_cap_remaining_usd,
    fold_rate_taper,
    fold_spend_usd,
    fold_surplus_usd,
    fold_units,
    plan_fold_consumption,
    plan_source_price,
    position_ceiling,
    priced_usd,
    ratio_to_ceiling,
    sale_proceeds_usd,
    scrum_units,
    settle_fold_plan,
    trim_fold_plan,
    unit_rule,
)
from . import paper_log
from .fake_balance import FakeBalance, PaperLedger, opening_ledger
from .fleet_source import PaperBot

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
    ``plan_source_price`` a fold re-entered against."""

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


def apply_scrum(
    bot: PaperBot,
    balance: FakeBalance,
    price: float,
    now_s: float,
    candle_ts_ms: int,
    delta: float,
    rule: str,
) -> Optional[PaperTrade]:
    """Sell ``scrum_units`` of ``delta`` at ``price``, the tick's ``best_bid``,
    under ``rule`` from the highest-priced ``main_lots`` first, and queue the
    proceeds ``sale_proceeds_usd`` leaves after ``estimated_fee_usd`` as one
    fold tranche per lot sold from, the Simulator's ``apply_scrum`` over a
    ``FakeBalance``; nothing fills when the balance holds fewer units than
    the sell needs or a whole-unit ``delta`` buys under one unit."""
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
    )


def apply_fold(
    bot: PaperBot,
    balance: FakeBalance,
    price: float,
    ticker_last: float,
    now_s: float,
    candle_ts_ms: int,
    rule: str,
) -> Optional[PaperTrade]:
    """Rebuy the tranches ``eligible_fold_tranches`` names at ``ticker_last``
    under ``fold_rebuy_factor``, planned under ``cycle_growth_cap_usd`` by
    ``plan_fold_consumption``, spent as ``fold_spend_usd`` under
    ``fold_taper`` with no wallet cap, booked as ``fold_units`` at ``price``,
    the tick's ``best_ask``, under ``rule``, settled by ``settle_fold_plan``,
    the cash charged the spend plus ``estimated_fee_usd``, the bought units
    joining ``main_lots`` per consumed slice's share, and the surplus
    ``fold_surplus_usd`` reads carried as ``realized_usd``: the Simulator's
    ``apply_fold`` under ``FUNDED_BY_TARGETS`` over a ``FakeBalance``."""
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


def opening_balance(bot: PaperBot, price: float, rule: str) -> FakeBalance:
    """A ``FakeBalance`` worth ``bot.target_usd`` at ``price`` under ``rule``,
    the ``fold_units`` the target buys as one lot at ``price``, plus
    ``cash_usd`` of the target, the bot's share of the unbounded budget."""
    target_usd = float(bot.target_usd or 0.0)
    units = fold_units(target_usd, float(price), rule) if price > 0.0 else 0.0
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
) -> PaperTick:
    """Evaluate the shipped chains on the newest bar of ``candles`` and fill
    what latched at ``book``'s ``best_bid`` or ``best_ask``, ``engine`` the
    ``VotingEngine`` the window is voted by; a refusal arms nothing."""
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
    context = tape_context(bot, balance, window, reading, summary)
    armed = latch(context)
    close = float(window[-1].close)
    stamp = int(window[-1].timestamp)
    last = last or close
    filled = None
    if armed["scrum_armed"]:
        filled = apply_scrum(bot, balance, bid, now_s, stamp, context.delta, rule)
    elif armed["fold_armed"]:
        filled = apply_fold(bot, balance, ask, last, now_s, stamp, rule)
    if filled is not None:
        filled = replace(filled, bid=bid, ask=ask, last=last)
    return PaperTick(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        wall_ms=int(now_s * 1000),
        candles_read=len(window),
        price=close,
        scrum_armed=bool(armed["scrum_armed"]),
        fold_armed=bool(armed["fold_armed"]),
        filled=filled,
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


def start(bots: Sequence[PaperBot], rule: str) -> PaperRun:
    """Mark a run started over ``bots`` under ``rule``, asking the feed for
    nothing yet; ``opening_ledger`` sets Paper Spendable and Paper Locked to
    the fleet's dollar target and each balance opens on its first worked tick."""
    return PaperRun(
        bots=tuple(bots),
        state=STARTED,
        started_at_ms=wall_clock_ms(),
        rule=rule,
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
    ``PaperTick``, ``on_figures`` the ledger's figures after each worked pass,
    ``on_finished`` the run when the loop ends, ``say`` each line, and
    ``clock`` is the one seam time is read through."""

    def __init__(
        self,
        run: PaperRun,
        exchange: Any,
        states: Callable[[], dict],
        on_trade: Optional[Callable[[PaperTrade], None]] = None,
        on_tick: Optional[Callable[[PaperTick], None]] = None,
        on_figures: Optional[Callable[[dict], None]] = None,
        on_finished: Optional[Callable[[PaperRun], None]] = None,
        say: Optional[Callable[[str], None]] = None,
        clock: Optional[WallClock] = None,
        tick_interval_s: float = TICK_INTERVAL_S,
    ) -> None:
        from ..trading.ta_engine import VotingEngine

        self._run = run
        self._exchange = exchange
        self._states = states
        self._on_trade = on_trade
        self._on_tick = on_tick
        self._on_figures = on_figures
        self._on_finished = on_finished
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
        if self._on_finished is not None:
            self._on_finished(self._run)

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
        ``on_trade`` on a fill and ``on_tick`` after."""
        book = self._exchange.ticker(bot.symbol)
        candles = candles_for(self._exchange, bot)
        balance = self._run.balances.get(bot.bot_id)
        if balance is None and not refusal_for(bot, candles, book):
            price = float((book or {}).get("last") or candles[-1].close)
            balance = opening_balance(bot, price, self._run.rule)
            self._run.balances[bot.bot_id] = balance
        seen = tick(
            bot,
            balance or FakeBalance(),
            candles,
            book,
            self._run.rule,
            self._clock.now(),
            self._engine,
        )
        record(self._run, bot, seen)
        if seen.filled is not None and self._on_trade is not None:
            self._on_trade(seen.filled)
        if self._on_tick is not None:
            self._on_tick(seen)
        return seen


__all__ = [
    "IDLE",
    "MIN_CANDLES",
    "NO_BOOK_TEXT",
    "NO_FEED_TEXT",
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
    "opening_balance",
    "record",
    "refusal_for",
    "run_rule",
    "start",
    "stop",
    "taker_fee_pct",
    "tick",
    "tick_skip",
    "wall_clock_ms",
]
