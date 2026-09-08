"""Paper Mode: the shipped gate chains walked over live feed candles.

``tick`` builds a ``GateContext`` through ``tape_context`` and evaluates it with
``latch``, which runs ``build_scrumming_scrum_chain`` and
``build_scrumming_fold_chain`` unchanged. ``apply_scrum`` and ``apply_fold``
move a ``FakeBalance`` and record a ``PaperTrade`` stamped with the wall clock,
and a fold closing a tranche carries the ``realized_usd`` that reaches
``PaperRun.ledger``. ``advance`` appends one ``paper_log`` row per tick, the
only file a paper run writes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from ..simulator.back_test import (
    FOLD,
    MIN_CANDLES,
    SCRUM,
    WINDOW_CANDLES,
    fee_usd,
    tape_context,
)
from ..simulator.validation import bb_reading, latch
from . import paper_log
from .fake_balance import FakeBalance, PaperLedger, opening_balance, opening_ledger
from .fleet_source import PaperBot

logger = logging.getLogger("acervator.paper.run")

NO_FEED_TEXT = "The live feed answered no candle."
SHORT_FEED_FORMAT = "{symbol} answered {count} candles; {need} are needed."

#: What one press of Start opens the run with, per bot, at the newest close.
STARTED = "started"
STOPPED = "stopped"
IDLE = "idle"
RUN_STATES = (IDLE, STARTED, STOPPED)


def wall_clock_ms() -> int:
    """Wall-clock milliseconds now, the stamp every ``PaperTrade`` carries."""
    return int(time.time() * 1000)


@dataclass(frozen=True)
class PaperTrade:
    """One scrum sell or fold buy the live feed produced, against fake money."""

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


@dataclass(frozen=True)
class PaperTick:
    """One gate-chain evaluation of one bot against the newest bar."""

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


def apply_scrum(
    bot: PaperBot,
    balance: FakeBalance,
    price: float,
    candle_ts_ms: int,
    delta: float,
) -> Optional[PaperTrade]:
    """Sell ``delta / price`` units and hold the proceeds as one fold tranche.

    Nothing fills when ``balance`` holds fewer units than the sell needs.
    """
    units = abs(float(delta)) / float(price) if float(price) > 0.0 else 0.0
    if units <= 0.0 or units > balance.units:
        return None
    notional = units * float(price)
    fee = fee_usd(notional, bot.trading_fee_pct)
    balance.sell_basis(units)
    balance.units -= units
    balance.cash_usd += notional - fee
    balance.open_tranche(notional - fee)
    return PaperTrade(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        side=SCRUM,
        candle_ts_ms=int(candle_ts_ms),
        wall_ms=wall_clock_ms(),
        price=float(price),
        units=units,
        usd=notional,
        fee_usd=fee,
    )


def apply_fold(
    bot: PaperBot,
    balance: FakeBalance,
    price: float,
    candle_ts_ms: int,
    delta: float,
) -> Optional[PaperTrade]:
    """Buy ``delta`` back at ``price``, spend one tranche and realize its close.

    The spend is capped at ``balance.cash_usd``, so one scrum's proceeds fund
    one fold.
    """
    spend = min(abs(float(delta)), balance.cash_usd)
    if spend <= 0.0 or balance.tranches <= 0 or float(price) <= 0.0:
        return None
    fee = fee_usd(spend, bot.trading_fee_pct)
    units = (spend - fee) / float(price)
    if units <= 0.0:
        return None
    realized = balance.close_tranche(spend)
    balance.units += units
    balance.cash_usd -= spend
    balance.cost_basis_usd += spend
    return PaperTrade(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        side=FOLD,
        candle_ts_ms=int(candle_ts_ms),
        wall_ms=wall_clock_ms(),
        price=float(price),
        units=units,
        usd=spend,
        fee_usd=fee,
        realized_usd=realized,
    )


def refusal_for(bot: PaperBot, candles: Sequence[Any]) -> str:
    """Why ``candles`` cannot be ticked, empty when they can."""
    if not candles:
        return NO_FEED_TEXT
    if len(candles) < MIN_CANDLES:
        return SHORT_FEED_FORMAT.format(
            symbol=bot.symbol, count=len(candles), need=MIN_CANDLES
        )
    return ""


def open_balance(bot: PaperBot, candles: Sequence[Any]) -> FakeBalance:
    """A ``FakeBalance`` opened at the newest close in ``candles``."""
    price = float(candles[-1].close) if candles else 0.0
    return opening_balance(bot.target_usd, price)


def tick(bot: PaperBot, balance: FakeBalance, candles: Sequence[Any]) -> PaperTick:
    """Evaluate the shipped chains on the newest bar and fill what latched.

    A window shorter than ``MIN_CANDLES`` arms nothing and carries the refusal.
    """
    from ..trading.ta_engine import VotingEngine

    refusal = refusal_for(bot, candles)
    if refusal:
        return PaperTick(
            bot_id=bot.bot_id,
            symbol=bot.symbol,
            wall_ms=wall_clock_ms(),
            candles_read=len(candles),
            price=float(candles[-1].close) if candles else 0.0,
            scrum_armed=False,
            fold_armed=False,
            refusal=refusal,
        )
    window = list(candles[-WINDOW_CANDLES:])
    reading = bb_reading(window, bot)
    summary = VotingEngine().compute_all(window, bot.ta_timeframe, symbol=bot.symbol)
    context = tape_context(bot, balance, window, reading, summary)
    armed = latch(context)
    price = float(window[-1].close)
    stamp = int(window[-1].timestamp)
    filled = None
    if armed["scrum_armed"]:
        filled = apply_scrum(bot, balance, price, stamp, context.delta)
    elif armed["fold_armed"]:
        filled = apply_fold(bot, balance, price, stamp, context.delta)
    return PaperTick(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        wall_ms=wall_clock_ms(),
        candles_read=len(window),
        price=price,
        scrum_armed=bool(armed["scrum_armed"]),
        fold_armed=bool(armed["fold_armed"]),
        filled=filled,
        scrum_blockers=tuple(str(one) for one in armed["scrum_blockers"]),
        fold_blockers=tuple(str(one) for one in armed["fold_blockers"]),
        scrum_fixture=paper_log.scrum_fixture(context),
        fold_fixture=paper_log.fold_fixture(context),
    )


@dataclass
class PaperRun:
    """The fleet, its fake balances, its ledger and what the live feed produced.

    Every field lives in memory and the only file a run writes is the paper log
    under ``src.paper.paper_paths.PAPER_ROOT``.
    """

    bots: tuple[PaperBot, ...] = ()
    state: str = IDLE
    started_at_ms: int = 0
    ledger: PaperLedger = field(default_factory=PaperLedger)
    balances: dict[str, FakeBalance] = field(default_factory=dict)
    last_price: dict[str, float] = field(default_factory=dict)
    trades: list[PaperTrade] = field(default_factory=list)
    ticks: list[PaperTick] = field(default_factory=list)
    refusals: dict[str, str] = field(default_factory=dict)

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
            "ticks": len(self.ticks),
            "scrum_armed": sum(1 for one in self.ticks if one.scrum_armed),
            "fold_armed": sum(1 for one in self.ticks if one.fold_armed),
            "scrum_trades": sum(1 for one in self.trades if one.side == SCRUM),
            "fold_trades": sum(1 for one in self.trades if one.side == FOLD),
            "fees_usd": sum(one.fee_usd for one in self.trades),
            "budget_usd": sum(one.budget_usd for one in self.balances.values()),
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


def start(bots: Sequence[PaperBot]) -> PaperRun:
    """Mark a run started over ``bots``, asking the feed for nothing yet.

    ``opening_ledger`` sets Paper Spendable and Paper Locked to the fleet's
    dollar target, and each bot's ``FakeBalance`` opens on its first ``advance``.
    """
    return PaperRun(
        bots=tuple(bots),
        state=STARTED,
        started_at_ms=wall_clock_ms(),
        ledger=opening_ledger(bots),
    )


def record(run: PaperRun, bot: PaperBot, seen: PaperTick) -> None:
    """File ``seen`` on ``run`` and append its row to the paper log."""
    run.ticks.append(seen)
    if seen.price > 0.0:
        run.last_price[bot.bot_id] = seen.price
    if seen.filled is not None:
        run.trades.append(seen.filled)
        run.ledger.record_close(seen.filled.realized_usd)
    if seen.refusal:
        run.refusals[bot.bot_id] = seen.refusal
    else:
        run.refusals.pop(bot.bot_id, None)
    paper_log.append_row(paper_log.paper_row(seen, bot.exchange_id, run.figures()))


def advance(run: PaperRun, feed: Any, bot_id: str = "") -> list[PaperTick]:
    """Ask ``feed`` for each bot's newest window, open its balance and tick it.

    A ``bot_id`` narrows the pass to that one bot, which is one feed ask.
    """
    if not run.running:
        return []
    made: list[PaperTick] = []
    for bot in run.bots:
        if bot_id and bot.bot_id != bot_id:
            continue
        candles = candles_for(feed, bot)
        balance = run.balances.get(bot.bot_id)
        if balance is None and not refusal_for(bot, candles):
            balance = open_balance(bot, candles)
            run.balances[bot.bot_id] = balance
        seen = tick(bot, balance or FakeBalance(), candles)
        made.append(seen)
        record(run, bot, seen)
    return made


def stop(run: PaperRun) -> PaperRun:
    """Mark ``run`` stopped; its balances, ledger and trades stay readable."""
    run.state = STOPPED
    return run


__all__ = [
    "IDLE",
    "MIN_CANDLES",
    "NO_FEED_TEXT",
    "RUN_STATES",
    "STARTED",
    "STOPPED",
    "WINDOW_CANDLES",
    "PaperRun",
    "PaperTick",
    "PaperTrade",
    "advance",
    "apply_fold",
    "apply_scrum",
    "candles_for",
    "open_balance",
    "record",
    "refusal_for",
    "start",
    "stop",
    "tick",
    "wall_clock_ms",
]
