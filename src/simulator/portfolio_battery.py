"""Portfolio Battery Mode: every portfolio symbol walked over its RA-StoneTablet.

``plan_run`` gives each portfolio its bots, the held fleet's own where
``matched_bots`` finds one per symbol on the venue the run reads, else one
``generated_bot`` per symbol at the ``symbol_targets`` share of
``DEFAULT_TARGET_USD``; ``span_bounds``, ``asset_candles`` and ``resample``
give ``run_symbol`` the ``1d``, ``1w`` and ``1M`` bars it hands to
``back_test.walk``, the same gate chain a live bot ticks, reading the
buy-and-hold baseline and its trough off that walk's own prices.
``run_portfolio`` sums those runs per timeframe and reads ``reading_for``, the
highest historical mark the scrummed end clears, and ``run_battery`` reports
every portfolio, a symbol with no tablet as missing weight, a recorded gap
through ``gaps_in_span`` and a symbol with no ``cited_rule_for`` rule as
``UNCITED_RULE``, missing weight and not walked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

from ..trading.stone_tablets.ra_fetcher import read_gaps
from .back_test import (
    FUNDED_BY_TARGETS,
    MIN_CANDLES,
    UNCITED_RULE,
    SimTrade,
    TradeSink,
    cited_rule_for,
    new_bot,
    run_budget_usd,
    walk,
)
from .fleet_source import BATTERY_ORIGIN, SCRUMMING_MODE, SimBot
from .portfolios import PERIODS, PORTFOLIOS, Portfolio, is_crypto
from .sim_bus import RunEmitter
from .validation import iso_stamp

logger = logging.getLogger("acervator.simulator.portfolio_battery")

#: The timeframes a daily tablet builds, spelled as ``HTF_TIMEFRAMES`` spells
#: them.
TIMEFRAMES = ("1d", "1w", "1M")

#: The timeframe every RA-StoneTablet carries. ``resample`` folds these rows.
TABLET_TIMEFRAME = "1d"

#: The span label covering every candle the RA tablets hold.
FULL_SPAN = "All"

#: Every span a run may be asked for: the archive's six, and the whole tape.
SPANS = (FULL_SPAN,) + tuple(PERIODS)

#: The default Target Balance of one generated Battery bot, the operator's
#: figure; a portfolio's mix shares ``DEFAULT_TARGET_USD`` per symbol.
DEFAULT_TARGET_USD = 500.0

#: ``scrumming_interval`` as the Bot Wizard opens it.
SCRUMMING_INTERVAL_PCT = 1.0

#: The reading of one scrummed end against its historical path's three marks,
#: the highest one it clears.
REVERSED = "reversed"
IMPROVED = "improved"
DEFENDED = "defended"
UNDEFENDED = "undefended"
NOT_RUN = "not run"
READINGS = (REVERSED, IMPROVED, DEFENDED, UNDEFENDED, NOT_RUN)

#: ``PortfolioResult.fleet_origin`` when the held fleet's own bots ran.
HELD_FLEET = "held"

#: Which venue a symbol's tablets are read from. Crypto prefers the venue the
#: product trades.
CRYPTO_EXCHANGE = "coinbase"
EQUITY_EXCHANGE = "yahoo"

#: How many gate-chain evaluations one symbol spends, sizing ``walk``'s step.
TICKS_PER_SYMBOL = 120

NO_TABLET = "no_tablet"
SHORT_TAPE = "short_tape"
RAN = "ran"

SYMBOL_OUTCOMES = (NO_TABLET, SHORT_TAPE, UNCITED_RULE, RAN)

BETTER = "better"
WORSE = "worse"
LEVEL = "level"

DAY_MS = 86_400_000


def reading_for(
    ran: bool, start_usd: float, trough_usd: float, end_usd: float, scrummed_usd: float
) -> str:
    """The highest historical mark ``scrummed_usd`` clears: ``REVERSED`` at or
    above ``start_usd`` when ``end_usd`` fell below it, ``IMPROVED`` above
    ``end_usd``, ``DEFENDED`` above ``trough_usd``, else ``UNDEFENDED``;
    ``NOT_RUN`` while ``ran`` is False."""
    if not ran:
        return NOT_RUN
    if end_usd < start_usd and scrummed_usd >= start_usd:
        return REVERSED
    if scrummed_usd > end_usd:
        return IMPROVED
    if scrummed_usd > trough_usd:
        return DEFENDED
    return UNDEFENDED


def reading_arithmetic(
    start_usd: float, trough_usd: float, end_usd: float, scrummed_usd: float, read: str
) -> str:
    """The four figures ``reading_for`` compared, written out beside ``read``."""
    return (
        f"historical start {start_usd:,.2f}, trough {trough_usd:,.2f}, end "
        f"{end_usd:,.2f}; scrummed end {scrummed_usd:,.2f}; reading {read}"
    )


@dataclass(frozen=True)
class SymbolRun:
    """One symbol's whole pass over one span at one timeframe."""

    asset: str
    symbol: str
    exchange_id: str
    timeframe: str
    outcome: str
    capital_usd: float = 0.0
    bars: int = 0
    ticks: int = 0
    scrum_latched: int = 0
    fold_latched: int = 0
    trades: tuple[SimTrade, ...] = ()
    start_price: float = 0.0
    end_price: float = 0.0
    start_units: float = 0.0
    end_units: float = 0.0
    cash_usd: float = 0.0
    fees_usd: float = 0.0
    first_ts_ms: int = 0
    last_ts_ms: int = 0
    open_ts_ms: int = 0
    asset_class: str = ""
    venue: str = ""
    unit_rule: str = ""
    bot_id: str = ""
    origin: str = ""
    trough_price: float = 0.0

    @property
    def ran(self) -> bool:
        """True while ``outcome`` reads ``RAN``."""
        return self.outcome == RAN

    @property
    def baseline_usd(self) -> float:
        """``capital_usd`` carried from ``start_price`` to ``end_price``,
        untraded."""
        if self.start_price <= 0.0:
            return 0.0
        return self.capital_usd * self.end_price / self.start_price

    @property
    def trough_usd(self) -> float:
        """``capital_usd`` carried from ``start_price`` to ``trough_price``, the
        lowest the untraded holding read on any walked bar."""
        if self.start_price <= 0.0:
            return 0.0
        return self.capital_usd * self.trough_price / self.start_price

    @property
    def accumulation_usd(self) -> float:
        """What the walk ended holding: ``end_units`` at ``end_price``, plus
        ``cash_usd``."""
        return self.end_units * self.end_price + self.cash_usd

    @property
    def reading(self) -> str:
        """``reading_for`` over this symbol's own three marks."""
        return reading_for(
            self.ran,
            self.capital_usd,
            self.trough_usd,
            self.baseline_usd,
            self.accumulation_usd,
        )

    @property
    def units_gained(self) -> float:
        """``end_units`` less ``start_units``."""
        return self.end_units - self.start_units

    @property
    def trade_count(self) -> int:
        """How many fills are in ``trades``."""
        return len(self.trades)


def day_ms(day: str) -> int:
    """Midnight UTC of a ``YYYY-MM-DD`` day, in milliseconds."""
    parsed = datetime.strptime(str(day), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def span_bounds(span: str, entries: Sequence[Any]) -> tuple[int, int]:
    """``(start_ms, end_ms)`` for ``span``, ``FULL_SPAN`` reading ``entries``.

    An unknown label answers ``FULL_SPAN``, and no entry answers ``(0, 0)``.
    """
    window = PERIODS.get(str(span))
    if window is not None:
        return (day_ms(window[0]), day_ms(window[1]) + DAY_MS)
    if not entries:
        return (0, 0)
    return (
        min(int(one.first_ts_ms) for one in entries),
        max(int(one.last_ts_ms) for one in entries) + DAY_MS,
    )


def exchange_for(asset: str, entries: Sequence[Any]) -> str:
    """The venue ``asset``'s tablets are read from, or empty when it has
    none."""
    held = {one.exchange_id for one in entries if one.asset == str(asset)}
    if not held:
        return ""
    preferred = CRYPTO_EXCHANGE if is_crypto(asset) else EQUITY_EXCHANGE
    return preferred if preferred in held else sorted(held)[0]


def asset_candles(source: Any, asset: str, exchange_id: str) -> list[list[float]]:
    """Every candle ``asset`` holds on ``exchange_id``, oldest first, one per
    stamp."""
    by_stamp: dict[int, list[float]] = {}
    for entry in source.entries():
        if entry.asset != str(asset) or entry.exchange_id != str(exchange_id):
            continue
        for row in source.candles(entry):
            by_stamp[int(row[0])] = [float(one) for one in row]
    return [by_stamp[stamp] for stamp in sorted(by_stamp)]


def slice_span(
    rows: Sequence[Sequence[float]], start_ms: int, end_ms: int
) -> list[list[float]]:
    """The rows stamped inside ``[start_ms, end_ms)``, or every row when the
    span is empty."""
    if end_ms <= start_ms:
        return [list(row) for row in rows]
    return [list(row) for row in rows if start_ms <= int(row[0]) < end_ms]


def bucket_key(ts_ms: int, timeframe: str) -> tuple:
    """The calendar bucket ``ts_ms`` falls in at ``timeframe``.

    ``1w`` buckets by ISO week and ``1M`` by calendar month, so a bar covers the
    days a chart draws.
    """
    moment = datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc)
    if timeframe == "1w":
        iso = moment.isocalendar()
        return (iso[0], iso[1])
    if timeframe == "1M":
        return (moment.year, moment.month)
    return (moment.year, moment.month, moment.day)


def fold_bucket(rows: Sequence[Sequence[float]]) -> list[float]:
    """One bar from ``rows``: first open, highest high, lowest low, last close,
    summed volume."""
    return [
        float(rows[0][0]),
        float(rows[0][1]),
        max(float(one[2]) for one in rows),
        min(float(one[3]) for one in rows),
        float(rows[-1][4]),
        sum(float(one[5]) for one in rows),
    ]


def resample(rows: Sequence[Sequence[float]], timeframe: str) -> list[list[float]]:
    """``rows`` folded into ``timeframe`` bars, the trailing bar kept partial.

    ``TABLET_TIMEFRAME`` is already the tablet's own bar, so it folds nothing.
    """
    if timeframe == TABLET_TIMEFRAME or not rows:
        return [list(row) for row in rows]
    out: list[list[float]] = []
    held: list[Sequence[float]] = []
    key: Optional[tuple] = None
    for row in rows:
        found = bucket_key(int(row[0]), timeframe)
        if key is not None and found != key:
            out.append(fold_bucket(held))
            held = []
        key = found
        held.append(row)
    if held:
        out.append(fold_bucket(held))
    return out


def walk_step(bar_count: int, ticks: int) -> int:
    """One step in bars, so a walk over ``bar_count`` spends about ``ticks``
    evaluations."""
    if ticks <= 0:
        return 1
    usable = max(0, int(bar_count) - MIN_CANDLES + 1)
    return max(1, usable // int(ticks))


def battery_bot(asset: str, exchange_id: str, timeframe: str, capital_usd: float):
    """One ``SimBot`` for ``asset``, on the Bot Wizard's own new-bot defaults."""
    return new_bot(
        f"{asset}/USD",
        exchange_id,
        capital_usd,
        ta_timeframe=timeframe,
        scrumming_interval_pct=SCRUMMING_INTERVAL_PCT,
        bot_id=f"{asset}@{exchange_id}:{timeframe}",
    )


def symbol_targets(
    portfolio: Portfolio, default_usd: float = DEFAULT_TARGET_USD
) -> dict[str, float]:
    """Each symbol's Target Balance: its ``positions_usd`` size when
    ``sizes_known``, else its ``weights`` share of ``default_usd`` per symbol,
    to the cent."""
    if portfolio.sizes_known:
        sizes = portfolio.positions_usd or {}
        return {symbol: round(float(sizes[symbol]), 2) for symbol in portfolio.symbols}
    if portfolio.mix is None:
        return {symbol: float(default_usd) for symbol in portfolio.symbols}
    whole = float(default_usd) * len(portfolio.symbols)
    weights = portfolio.weights
    return {symbol: round(whole * weights[symbol], 2) for symbol in portfolio.symbols}


def plan_venue(asset: str, entries: Sequence[Any]) -> str:
    """``exchange_for`` when ``asset`` holds a tablet, else the venue its class
    prefers, so a bot is seated even when its symbol reads ``NO_TABLET``."""
    return exchange_for(asset, entries) or (
        CRYPTO_EXCHANGE if is_crypto(asset) else EQUITY_EXCHANGE
    )


def generated_bot(asset: str, exchange_id: str, target_usd: float) -> SimBot:
    """One scrumming ``SimBot`` for ``asset`` on ``exchange_id`` at
    ``target_usd``, ``ta_timeframe`` ``TABLET_TIMEFRAME``, ``bot_id`` the pair
    and venue, ``origin`` ``BATTERY_ORIGIN``."""
    bot = new_bot(
        f"{asset}/USD",
        exchange_id,
        target_usd,
        ta_timeframe=TABLET_TIMEFRAME,
        scrumming_interval_pct=SCRUMMING_INTERVAL_PCT,
        bot_id=f"{asset}@{exchange_id}",
    )
    return replace(bot, origin=BATTERY_ORIGIN)


def matched_bots(
    portfolio: Portfolio, held: Sequence[SimBot], venue_of: Callable[[str], str]
) -> Optional[dict[str, SimBot]]:
    """One held scrumming bot per symbol of ``portfolio``, on ``venue_of`` that
    symbol with ``target_usd`` above zero, the lowest ``bot_id`` where several
    match; None when any symbol has none."""
    out: dict[str, SimBot] = {}
    for symbol in portfolio.symbols:
        venue = venue_of(symbol)
        found = sorted(
            (
                bot
                for bot in held
                if bot.mode == SCRUMMING_MODE
                and bot.asset == symbol
                and bot.exchange_id == venue
                and bot.target_usd is not None
                and float(bot.target_usd) > 0.0
            ),
            key=lambda bot: bot.bot_id,
        )
        if not found:
            return None
        out[symbol] = found[0]
    return out


@dataclass(frozen=True)
class RunPlan:
    """The bots one press runs: per portfolio name, one ``SimBot`` per symbol,
    and whether they are the held fleet's own or generated."""

    names: tuple[str, ...]
    by_portfolio: dict[str, dict[str, SimBot]]
    origins: dict[str, str]

    @property
    def bots(self) -> list[SimBot]:
        """Every bot the run holds, one per ``bot_id``, the first portfolio's
        where two name one id."""
        seen: dict[str, SimBot] = {}
        for name in self.names:
            for bot in self.by_portfolio.get(name, {}).values():
                seen.setdefault(bot.bot_id, bot)
        return list(seen.values())

    @property
    def budget_usd(self) -> float:
        """``run_budget_usd`` over ``bots``."""
        return run_budget_usd(self.bots)

    @property
    def fleet_origins(self) -> tuple[str, ...]:
        """The ``origin`` words ``bots`` carry, sorted."""
        return tuple(sorted({bot.origin for bot in self.bots}))

    @property
    def plan_origins(self) -> tuple[str, ...]:
        """The distinct ``origins`` values, ``BATTERY_ORIGIN`` or
        ``HELD_FLEET``, sorted."""
        return tuple(sorted(set(self.origins.values())))

    @property
    def summary(self) -> dict:
        """The counts one plan reports."""
        return {
            "portfolios": list(self.names),
            "bots": len(self.bots),
            "budget_usd": self.budget_usd,
            "origins": {name: self.origins.get(name, "") for name in self.names},
            "targets": {
                name: {asset: bot.target_usd for asset, bot in bots.items()}
                for name, bots in self.by_portfolio.items()
            },
        }


def plan_run(
    names: Sequence[str],
    tablets: Any,
    held: Sequence[SimBot] = (),
    default_usd: float = DEFAULT_TARGET_USD,
) -> RunPlan:
    """The ``RunPlan`` for ``names``, every ``PORTFOLIOS`` name when empty:
    ``matched_bots`` from ``held`` where the whole portfolio matches, else one
    ``generated_bot`` per symbol at ``symbol_targets``."""
    wanted = [str(one) for one in names if str(one) in PORTFOLIOS] or sorted(PORTFOLIOS)
    entries = tablets.entries()
    venues: dict[str, str] = {}

    def venue_of(asset: str) -> str:
        if asset not in venues:
            venues[asset] = plan_venue(asset, entries)
        return venues[asset]

    by_portfolio: dict[str, dict[str, SimBot]] = {}
    origins: dict[str, str] = {}
    for name in wanted:
        portfolio = PORTFOLIOS[name]
        matched = matched_bots(portfolio, held, venue_of)
        if matched is not None:
            by_portfolio[name] = matched
            origins[name] = HELD_FLEET
            continue
        targets = symbol_targets(portfolio, default_usd)
        by_portfolio[name] = {
            symbol: generated_bot(symbol, venue_of(symbol), targets[symbol])
            for symbol in portfolio.symbols
        }
        origins[name] = BATTERY_ORIGIN
    return RunPlan(names=tuple(wanted), by_portfolio=by_portfolio, origins=origins)


def run_symbol(
    bot: SimBot,
    rows: Sequence[Sequence[float]],
    timeframe: str,
    ticks: int = TICKS_PER_SYMBOL,
    on_trade: Optional[TradeSink] = None,
    emitter: Optional[RunEmitter] = None,
) -> SymbolRun:
    """Walk ``bot`` over ``rows`` folded to ``timeframe`` at its own
    ``target_usd``, handing ``on_trade`` and ``emitter`` to ``walk``, and read
    the result.

    ``rows`` are one span's daily tablet candles; no bar answers ``NO_TABLET``,
    a class with no rule in ``cited_rule_for`` answers ``UNCITED_RULE``, and
    too few bars answers ``SHORT_TAPE``; ``emitter.bot_line`` names each.
    """
    from ..trading.indicators.types import candles_from_raw
    from .back_test import no_tablet_line, short_tablet_line, uncited_rule_line

    asset = bot.asset
    exchange_id = bot.exchange_id
    capital_usd = float(bot.target_usd or 0.0)
    bars = resample(rows, timeframe)
    symbol = bot.symbol or f"{asset}/USD"
    if not bars:
        if emitter is not None:
            emitter.bot_line(bot.bot_id, no_tablet_line(bot))
        return SymbolRun(
            asset=asset,
            symbol=symbol,
            exchange_id=exchange_id,
            timeframe=timeframe,
            outcome=NO_TABLET,
            capital_usd=capital_usd,
            bot_id=bot.bot_id,
            origin=bot.origin,
        )
    class_name, venue, rule = cited_rule_for(asset, exchange_id)
    if rule is None:
        refused = SymbolRun(
            asset=asset,
            symbol=symbol,
            exchange_id=exchange_id,
            timeframe=timeframe,
            outcome=UNCITED_RULE,
            capital_usd=capital_usd,
            bars=len(bars),
            first_ts_ms=int(bars[0][0]),
            last_ts_ms=int(bars[-1][0]),
            asset_class=class_name,
            venue=venue,
            bot_id=bot.bot_id,
            origin=bot.origin,
        )
        if emitter is not None:
            emitter.bot_line(bot.bot_id, uncited_rule_line(refused))
        return refused
    if len(bars) < MIN_CANDLES:
        if emitter is not None:
            emitter.bot_line(bot.bot_id, short_tablet_line(bot, len(bars)))
        return SymbolRun(
            asset=asset,
            symbol=symbol,
            exchange_id=exchange_id,
            timeframe=timeframe,
            outcome=SHORT_TAPE,
            capital_usd=capital_usd,
            bars=len(bars),
            first_ts_ms=int(bars[0][0]),
            last_ts_ms=int(bars[-1][0]),
            asset_class=class_name,
            venue=venue,
            unit_rule=rule,
            bot_id=bot.bot_id,
            origin=bot.origin,
        )
    walked = replace(bot, ta_timeframe=timeframe)
    result = walk(
        walked,
        candles_from_raw(bars),
        walk_step(len(bars), ticks),
        FUNDED_BY_TARGETS,
        rule=rule,
        on_trade=on_trade,
        emitter=emitter,
    )
    return SymbolRun(
        asset=asset,
        symbol=symbol,
        exchange_id=exchange_id,
        timeframe=timeframe,
        outcome=RAN,
        capital_usd=capital_usd,
        bars=len(bars),
        ticks=result.ticks,
        scrum_latched=result.scrum_latched,
        fold_latched=result.fold_latched,
        trades=result.trades,
        start_price=result.start_price,
        end_price=result.end_price,
        start_units=result.start_units,
        end_units=result.end_units,
        cash_usd=result.cash_usd,
        fees_usd=result.fees_usd,
        first_ts_ms=result.first_ts_ms,
        last_ts_ms=result.last_ts_ms,
        open_ts_ms=int(bars[MIN_CANDLES - 1][0]),
        asset_class=class_name,
        venue=venue,
        unit_rule=rule,
        bot_id=bot.bot_id,
        origin=bot.origin,
        trough_price=min(float(bar[4]) for bar in bars[MIN_CANDLES - 1 :]),
    )


@dataclass(frozen=True)
class TimeframeResult:
    """One portfolio at one timeframe: every symbol run, and the two totals."""

    timeframe: str
    runs: tuple[SymbolRun, ...]

    @property
    def ran(self) -> list[SymbolRun]:
        """Every run whose ``outcome`` reads ``RAN``."""
        return [one for one in self.runs if one.ran]

    @property
    def first_ts_ms(self) -> int:
        """The earliest bar a run in ``ran`` opened its position on, zero when
        none ran.

        ``walk`` opens after ``MIN_CANDLES`` warm-up bars, so this is later than
        the tape's own first bar and later again at a coarser timeframe.
        """
        stamps = [one.open_ts_ms for one in self.ran if one.open_ts_ms]
        return min(stamps) if stamps else 0

    @property
    def last_ts_ms(self) -> int:
        """The latest bar any run in ``ran`` read, zero when none ran."""
        stamps = [one.last_ts_ms for one in self.ran if one.last_ts_ms]
        return max(stamps) if stamps else 0

    @property
    def committed_usd(self) -> float:
        """The capital the runs in ``ran`` were given."""
        return sum(one.capital_usd for one in self.ran)

    @property
    def missing_usd(self) -> float:
        """The capital of every symbol that reached no usable tape."""
        return sum(one.capital_usd for one in self.runs if not one.ran)

    @property
    def missing_weight(self) -> float:
        """``missing_usd`` as a share of every symbol's ``capital_usd``."""
        whole = sum(one.capital_usd for one in self.runs)
        return self.missing_usd / whole if whole > 0.0 else 0.0

    @property
    def missing_symbols(self) -> list[str]:
        """Each asset carrying ``missing_usd``, with the ``outcome`` that put it
        there."""
        return [f"{one.asset} ({one.outcome})" for one in self.runs if not one.ran]

    @property
    def baseline_usd(self) -> float:
        """What holding the covered symbols untraded would have ended at."""
        return sum(one.baseline_usd for one in self.ran)

    @property
    def accumulation_usd(self) -> float:
        """What the gate chain ended holding across the covered symbols."""
        return sum(one.accumulation_usd for one in self.ran)

    @property
    def improvement_usd(self) -> float:
        """``accumulation_usd`` less ``baseline_usd``."""
        return self.accumulation_usd - self.baseline_usd

    @property
    def improvement_pct(self) -> float:
        """``improvement_usd`` as a percentage of ``baseline_usd``."""
        base = self.baseline_usd
        return 100.0 * self.improvement_usd / base if base > 0.0 else 0.0

    @property
    def verdict(self) -> str:
        """``BETTER``, ``WORSE`` or ``LEVEL`` against ``baseline_usd``."""
        if not self.ran:
            return LEVEL
        if self.improvement_usd > 0.0:
            return BETTER
        return WORSE if self.improvement_usd < 0.0 else LEVEL

    @property
    def trough_usd(self) -> float:
        """The sum of each covered symbol's ``trough_usd``, the floor the
        untraded holdings never read below."""
        return sum(one.trough_usd for one in self.ran)

    @property
    def historical_failed(self) -> bool:
        """True when ``baseline_usd`` ended below ``committed_usd``."""
        return bool(self.ran) and self.baseline_usd < self.committed_usd

    @property
    def reading(self) -> str:
        """``reading_for`` over ``committed_usd``, ``trough_usd``,
        ``baseline_usd`` and ``accumulation_usd``."""
        return reading_for(
            bool(self.ran),
            self.committed_usd,
            self.trough_usd,
            self.baseline_usd,
            self.accumulation_usd,
        )

    @property
    def reading_arithmetic(self) -> str:
        """``reading_arithmetic`` over the same four figures and ``reading``."""
        return reading_arithmetic(
            self.committed_usd,
            self.trough_usd,
            self.baseline_usd,
            self.accumulation_usd,
            self.reading,
        )

    @property
    def summary(self) -> dict:
        """The counts one Portfolio Battery row reports."""
        ran = self.ran
        return {
            "timeframe": self.timeframe,
            "symbols": len(self.runs),
            "symbols_run": len(ran),
            "first_at": iso_stamp(self.first_ts_ms),
            "last_at": iso_stamp(self.last_ts_ms),
            "bars": sum(one.bars for one in ran),
            "ticks": sum(one.ticks for one in ran),
            "scrum_latched": sum(one.scrum_latched for one in ran),
            "fold_latched": sum(one.fold_latched for one in ran),
            "trades": sum(one.trade_count for one in ran),
            "fees_usd": sum(one.fees_usd for one in ran),
            "committed_usd": self.committed_usd,
            "baseline_usd": self.baseline_usd,
            "accumulation_usd": self.accumulation_usd,
            "improvement_usd": self.improvement_usd,
            "improvement_pct": self.improvement_pct,
            "units_gained": sum(one.units_gained for one in ran),
            "missing_usd": self.missing_usd,
            "missing_weight": self.missing_weight,
            "missing_symbols": self.missing_symbols,
            "verdict": self.verdict,
            "trough_usd": self.trough_usd,
            "historical_failed": self.historical_failed,
            "reading": self.reading,
            "reading_arithmetic": self.reading_arithmetic,
        }


@dataclass(frozen=True)
class PortfolioResult:
    """One portfolio over one span, at every timeframe it was asked for."""

    name: str
    description: str
    span: str
    start_ms: int
    end_ms: int
    timeframes: tuple[TimeframeResult, ...]
    fleet_origin: str = BATTERY_ORIGIN
    bot_ids: tuple[str, ...] = ()

    @property
    def improved_timeframes(self) -> list[str]:
        """Every timeframe whose ``verdict`` reads ``BETTER``."""
        return [one.timeframe for one in self.timeframes if one.verdict == BETTER]

    @property
    def best(self) -> Optional[TimeframeResult]:
        """The timeframe with the largest ``improvement_usd``, or None when none
        ran."""
        ranked = [one for one in self.timeframes if one.ran]
        return max(ranked, key=lambda one: one.improvement_usd) if ranked else None

    @property
    def readings(self) -> dict[str, str]:
        """Each timeframe's ``reading``, by timeframe."""
        return {one.timeframe: one.reading for one in self.timeframes}

    @property
    def line(self) -> str:
        """One Activity Log line: the name, the span, each timeframe's reading
        and how many symbols ran at the first timeframe."""
        readings = ", ".join(f"{tf} {read}" for tf, read in self.readings.items())
        first = self.timeframes[0] if self.timeframes else None
        ran = (
            f"{len(first.ran)} of {len(first.runs)}" if first is not None else "0 of 0"
        )
        return (
            f"{self.name} over {self.span}: {readings}; {ran} symbol(s) ran; "
            f"bots {self.fleet_origin}."
        )

    @property
    def summary(self) -> dict:
        """The portfolio's own row, and one row per timeframe."""
        best = self.best
        return {
            "portfolio": self.name,
            "description": self.description,
            "span": self.span,
            "first_at": iso_stamp(self.start_ms),
            "last_at": iso_stamp(self.end_ms),
            "timeframes": [one.summary for one in self.timeframes],
            "improved_timeframes": self.improved_timeframes,
            "best_timeframe": best.timeframe if best is not None else "",
            "best_improvement_usd": best.improvement_usd if best is not None else 0.0,
            "fleet_origin": self.fleet_origin,
            "bot_ids": list(self.bot_ids),
            "readings": self.readings,
        }


@dataclass(frozen=True)
class BatteryRun:
    """One Portfolio Battery press: its span, its portfolios and the gaps."""

    span: str
    start_ms: int
    end_ms: int
    portfolios: tuple[PortfolioResult, ...]
    gaps: tuple[dict, ...] = ()
    timeframes: tuple[str, ...] = TIMEFRAMES
    missing_assets: tuple[str, ...] = ()
    tablet_root: str = ""
    symbol_runs: int = 0
    uncited_assets: tuple[str, ...] = ()
    #: The ``ParityReport`` ``run_battery`` wrote for this press; None until it has.
    report: Any = None
    bots: tuple[SimBot, ...] = ()
    budget_usd: float = 0.0
    fleet_origins: tuple[str, ...] = ()
    #: The id every row of this press carries in ``data.run_id``; empty when
    #: ``run_battery`` was handed no bus.
    run_id: str = ""
    #: What ``RunEmitter.close`` answered: the rows emitted per topic and the
    #: ``EmitObserver`` reading; empty when ``run_battery`` was handed no bus.
    emitted: dict = field(default_factory=dict)

    def reading_counts(self, timeframe: str) -> dict[str, int]:
        """How many portfolios read each of ``READINGS`` at ``timeframe``."""
        counts = {read: 0 for read in READINGS}
        for portfolio in self.portfolios:
            read = portfolio.readings.get(timeframe)
            if read in counts:
                counts[read] += 1
        return counts

    @property
    def summary(self) -> dict:
        """The counts the Portfolio Battery pane reports."""
        improved = sum(1 for one in self.portfolios if one.improved_timeframes)
        return {
            "span": self.span,
            "first_at": iso_stamp(self.start_ms),
            "last_at": iso_stamp(self.end_ms),
            "portfolios": len(self.portfolios),
            "portfolios_improved": improved,
            "timeframes": list(self.timeframes),
            "symbol_runs": self.symbol_runs,
            "gaps": len(self.gaps),
            "missing_assets": list(self.missing_assets),
            "uncited_assets": list(self.uncited_assets),
            "bots": len(self.bots),
            "budget_usd": self.budget_usd,
            "fleet_origins": list(self.fleet_origins),
            "readings": {tf: self.reading_counts(tf) for tf in self.timeframes},
        }

    @property
    def lines(self) -> list[str]:
        """The span, the budget, the readings per timeframe, what improved,
        what had no tape and what had no cited unit rule, in the pane's own
        order."""
        read = self.summary
        if not self.portfolios:
            return ["No portfolio reached an RA-StoneTablet with enough candles."]
        out = [
            f"{read['portfolios']} portfolio(s) over {read['span']}, "
            f"{read['first_at']} to {read['last_at']}.",
            f"{read['bots']} bot(s), budget ${read['budget_usd']:,.2f}, the sum of "
            f"their Target Balances; bots {', '.join(read['fleet_origins'])}.",
            f"{read['symbol_runs']} symbol runs at "
            f"{', '.join(read['timeframes'])}.",
        ]
        for timeframe in self.timeframes:
            counts = self.reading_counts(timeframe)
            out.append(
                f"At {timeframe}: "
                + ", ".join(f"{counts[one]} {one}" for one in READINGS)
                + " against the historical path."
            )
        out.append(
            f"{read['portfolios_improved']} of {read['portfolios']} portfolio(s) "
            "beat their own buy-and-hold at one timeframe or more."
        )
        if self.missing_assets:
            out.append(
                f"{len(self.missing_assets)} symbol(s) hold no tablet: "
                + ", ".join(self.missing_assets)
            )
        if self.gaps:
            out.append(f"{len(self.gaps)} recorded gap(s) fall inside the span.")
        if self.uncited_assets:
            out.append(
                f"{len(self.uncited_assets)} symbol(s) have no cited unit rule "
                "on their venue and were not simulated: "
                + ", ".join(self.uncited_assets)
            )
        return out


def gaps_in_span(assets: Sequence[str], start_ms: int, end_ms: int) -> list[dict]:
    """Every recorded RA gap for ``assets`` overlapping ``[start_ms,
    end_ms)``."""
    wanted = {str(one) for one in assets}
    out: list[dict] = []
    for gap in read_gaps():
        if gap.asset not in wanted:
            continue
        if end_ms > start_ms and (
            int(gap.until_ms) < start_ms or int(gap.since_ms) >= end_ms
        ):
            continue
        out.append(
            {
                "asset": gap.asset,
                "exchange_id": gap.exchange_id,
                "year": int(gap.year),
                "since": iso_stamp(gap.since_ms),
                "until": iso_stamp(gap.until_ms),
                "reason": gap.reason,
            }
        )
    return out


class TapeCache:
    """One span's daily rows and venue per asset, read from ``source`` once."""

    def __init__(self, source: Any, start_ms: int, end_ms: int) -> None:
        """Hold ``source`` and the span every ``rows`` read is sliced to."""
        self._source = source
        self._entries = source.entries()
        self._start_ms = int(start_ms)
        self._end_ms = int(end_ms)
        self._rows: dict[str, list[list[float]]] = {}
        self._venues: dict[str, str] = {}

    def venue(self, asset: str) -> str:
        """The exchange ``asset`` is read from, empty when it holds no
        tablet."""
        if asset not in self._venues:
            self._venues[asset] = exchange_for(asset, self._entries)
        return self._venues[asset]

    def rows(self, asset: str) -> list[list[float]]:
        """``asset``'s daily candles inside the span, empty when it has none."""
        if asset not in self._rows:
            venue = self.venue(asset)
            whole = asset_candles(self._source, asset, venue) if venue else []
            self._rows[asset] = slice_span(whole, self._start_ms, self._end_ms)
        return self._rows[asset]


def run_portfolio(
    name: str,
    tablets: Any,
    span: str = FULL_SPAN,
    timeframes: Sequence[str] = TIMEFRAMES,
    ticks: int = TICKS_PER_SYMBOL,
    cache: Optional[TapeCache] = None,
    held: Optional[dict] = None,
    bots: Optional[dict[str, SimBot]] = None,
    fleet_origin: str = BATTERY_ORIGIN,
    on_trade: Optional[TradeSink] = None,
    emitter: Optional[RunEmitter] = None,
) -> PortfolioResult:
    """Walk every symbol of ``name`` over ``span`` at each of ``timeframes``,
    each on the bot ``bots`` names for it, ``plan_run`` with no held fleet when
    ``bots`` is None.

    ``held`` keeps one ``(bot_id, timeframe, target)`` run across portfolios,
    so a symbol two portfolios share on one bot is walked once and its trades
    reach ``on_trade`` and ``emitter`` once.
    """
    entry = PORTFOLIOS.get(str(name))
    symbols = entry.symbols if entry is not None else ()
    if bots is None:
        plan = plan_run((str(name),), tablets)
        bots = plan.by_portfolio.get(str(name), {})
        fleet_origin = plan.origins.get(str(name), BATTERY_ORIGIN)
    start_ms, end_ms = span_bounds(span, tablets.entries())
    tape = cache if cache is not None else TapeCache(tablets, start_ms, end_ms)
    walked_by_key = held if held is not None else {}
    by_timeframe: list[TimeframeResult] = []
    for timeframe in timeframes:
        walked: list[SymbolRun] = []
        for asset in symbols:
            bot = bots.get(asset)
            if bot is None:
                continue
            key = (bot.bot_id, timeframe, round(float(bot.target_usd or 0.0), 2))
            if key not in walked_by_key:
                walked_by_key[key] = run_symbol(
                    bot, tape.rows(asset), timeframe, ticks, on_trade, emitter
                )
            walked.append(walked_by_key[key])
        by_timeframe.append(TimeframeResult(timeframe=timeframe, runs=tuple(walked)))
    return PortfolioResult(
        name=str(name),
        description=entry.description if entry is not None else "",
        span=str(span),
        start_ms=start_ms,
        end_ms=end_ms,
        timeframes=tuple(by_timeframe),
        fleet_origin=fleet_origin,
        bot_ids=tuple(bots[asset].bot_id for asset in symbols if asset in bots),
    )


def run_battery(
    tablets: Any,
    names: Sequence[str] = (),
    span: str = FULL_SPAN,
    timeframes: Sequence[str] = TIMEFRAMES,
    ticks: int = TICKS_PER_SYMBOL,
    plan: Optional[RunPlan] = None,
    progress: Optional[Callable[[str], None]] = None,
    on_trade: Optional[TradeSink] = None,
    bus: Any = None,
) -> BatteryRun:
    """Run each portfolio in ``names`` over ``span`` through
    ``_walk_portfolios`` on ``plan``'s bots and write the pass through
    ``write_report`` onto ``BatteryRun.report``.

    ``progress`` is handed each portfolio's line and ``on_trade`` each
    ``SimTrade`` as it fills; ``bus`` becomes the ``RunEmitter`` every row of
    the pass goes through, under ``new_run_id``; a ``_walk_portfolios`` that
    raises reaches ``write_partial`` with the exception and re-raises.
    """
    from .parity_report import (
        PORTFOLIO_BATTERY,
        new_run_id,
        write_partial,
        write_report,
    )

    emitter = RunEmitter(bus, new_run_id(PORTFOLIO_BATTERY), PORTFOLIO_BATTERY)
    try:
        outcome = _walk_portfolios(
            tablets, names, span, timeframes, ticks, plan, progress, on_trade, emitter
        )
    except Exception as exc:
        emitter.close()
        write_partial(
            PORTFOLIO_BATTERY,
            exc,
            tablets=tablets,
            names=tuple(names),
            span=str(span),
            run_id=emitter.run_id,
        )
        raise
    outcome = replace(outcome, run_id=emitter.run_id, emitted=emitter.close())
    return replace(outcome, report=write_report(PORTFOLIO_BATTERY, outcome, tablets))


def _walk_portfolios(
    tablets: Any,
    names: Sequence[str],
    span: str,
    timeframes: Sequence[str],
    ticks: int,
    plan: Optional[RunPlan],
    progress: Optional[Callable[[str], None]],
    on_trade: Optional[TradeSink] = None,
    emitter: Optional[RunEmitter] = None,
) -> BatteryRun:
    """Run each portfolio ``plan`` names, ``plan_run`` over ``names`` when it
    is None, handing ``progress`` each ``PortfolioResult.line`` as it lands
    and ``on_trade`` and ``emitter`` each ``SimTrade`` as it fills."""
    chosen = plan if plan is not None else plan_run(names, tablets)
    start_ms, end_ms = span_bounds(span, tablets.entries())
    tape = TapeCache(tablets, start_ms, end_ms)
    walked_by_key: dict[tuple[str, str, float], SymbolRun] = {}
    results: list[PortfolioResult] = []
    for name in chosen.names:
        result = run_portfolio(
            name,
            tablets,
            span,
            timeframes,
            ticks,
            tape,
            walked_by_key,
            chosen.by_portfolio.get(name, {}),
            chosen.origins.get(name, BATTERY_ORIGIN),
            on_trade,
            emitter,
        )
        results.append(result)
        if progress is not None:
            progress(result.line)
    assets = sorted({one.asset for one in walked_by_key.values()})
    missing = sorted(
        {one.asset for one in walked_by_key.values() if one.outcome == NO_TABLET}
    )
    uncited = sorted(
        {one.asset for one in walked_by_key.values() if one.outcome == UNCITED_RULE}
    )
    return BatteryRun(
        span=str(span),
        start_ms=start_ms,
        end_ms=end_ms,
        portfolios=tuple(results),
        gaps=tuple(gaps_in_span(assets, start_ms, end_ms)),
        timeframes=tuple(timeframes),
        missing_assets=tuple(missing),
        tablet_root=str(tablets.root()),
        symbol_runs=len(walked_by_key),
        uncited_assets=tuple(uncited),
        bots=tuple(chosen.bots),
        budget_usd=chosen.budget_usd,
        fleet_origins=chosen.fleet_origins,
    )


__all__ = [
    "BETTER",
    "CRYPTO_EXCHANGE",
    "DAY_MS",
    "DEFAULT_TARGET_USD",
    "DEFENDED",
    "EQUITY_EXCHANGE",
    "FULL_SPAN",
    "HELD_FLEET",
    "IMPROVED",
    "LEVEL",
    "MIN_CANDLES",
    "NOT_RUN",
    "NO_TABLET",
    "RAN",
    "READINGS",
    "REVERSED",
    "SCRUMMING_INTERVAL_PCT",
    "SHORT_TAPE",
    "SPANS",
    "SYMBOL_OUTCOMES",
    "TABLET_TIMEFRAME",
    "TICKS_PER_SYMBOL",
    "TIMEFRAMES",
    "UNDEFENDED",
    "WORSE",
    "BatteryRun",
    "PortfolioResult",
    "RunPlan",
    "SymbolRun",
    "TapeCache",
    "TimeframeResult",
    "asset_candles",
    "battery_bot",
    "bucket_key",
    "day_ms",
    "exchange_for",
    "fold_bucket",
    "gaps_in_span",
    "generated_bot",
    "matched_bots",
    "plan_run",
    "plan_venue",
    "reading_arithmetic",
    "reading_for",
    "resample",
    "run_battery",
    "run_portfolio",
    "run_symbol",
    "slice_span",
    "span_bounds",
    "symbol_targets",
    "walk_step",
]
