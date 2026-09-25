"""Portfolio Battery Mode: every portfolio symbol walked over its RA-StoneTablet.

``plan_run`` gives each portfolio its bots, the held fleet's own where
``matched_bots`` finds one per symbol on the venue the run reads, else one
``generated_bot`` per symbol at the ``symbol_targets`` share of
``DEFAULT_TARGET_USD``; ``span_bounds``, ``asset_candles`` and ``resample``
give ``run_symbol`` the ``1d``, ``1w`` and ``1M`` bars it hands to
``back_test.walk``, the same gate chain a live bot ticks, over every bar from
the ``MIN_CANDLES``th on, reading the HODL end and its trough off that walk's
own prices and the Harvest-Fold end off what the walk ended holding.
``run_portfolio`` sums those runs per timeframe into the three figures,
``baseline_usd`` (HODL end), ``accumulation_usd`` (Harvest-Fold end) and
``difference_usd``, and ``run_battery`` runs one portfolio at a time through
``_walk_portfolios``, a report per portfolio and a summary over them, a symbol
with no tablet as missing weight, a recorded gap through ``gaps_in_span`` and a
symbol with no ``cited_rule_for`` rule as ``UNCITED_RULE``, missing weight and
not walked. Nothing here ranks a portfolio or declares a winner.

``TapeCache.bars`` reads each bot at the timeframe its asset's tablet carries:
a crypto bot the ``CRYPTO_TABLET_TIMEFRAME`` file through
``StoneTabletsRegistry.get_candles`` on the same root, native at ``5m`` and
rolled up by the registry for every other timeframe in ``bot_timeframes``; a
non-crypto bot the ``TABLET_TIMEFRAME`` file through ``resample``.
``battery_costs`` states, before a press, the ``RetrievalCost`` of each crypto
asset over the span, and ``retrieve_tablets`` fetches them on the Battery's
own thread through ``tablet_retrieval.retrieve`` before the first walk; a
crypto asset the venue refuses reads ``NO_TABLET`` at ``5m`` by name.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

from ..core.signal_contract import emit as pin_emit
from ..trading.stone_tablets.fetcher import STEP_5M_MS
from ..trading.stone_tablets.ra_fetcher import read_gaps
from ..trading.stone_tablets.registry import (
    NATIVE_TIMEFRAME,
    SUPPORTED_TIMEFRAMES,
    StoneTabletsRegistry,
)
from .back_test import (
    FOLD,
    FUNDED_BY_TARGETS,
    MIN_CANDLES,
    PROGRESS_EVERY_BARS,
    RATE_LINE_FORMAT,
    SCRUM,
    UNCITED_RULE,
    SimTrade,
    TradeSink,
    cited_rule_for,
    evaluations_expected,
    new_bot,
    run_budget_usd,
    seconds_per_thousand,
    venue_rules_for,
    walk,
)
from .fleet_source import BATTERY_ORIGIN, SCRUMMING_MODE, SimBot
from .portfolios import (
    PERIODS,
    PORTFOLIOS,
    TEST_RUN_SPAN,
    Portfolio,
    is_crypto,
    period_window,
)
from .read_only_connector import ReadOnlyConnector, VenueCall
from .sim_bus import RunEmitter
from .tablet_retrieval import (
    RetrievalCost,
    RetrievalOutcome,
    closed_until_ms,
    retrieval_cost,
    retrieve,
    venue_pages,
)
from .validation import iso_stamp

logger = logging.getLogger("acervator.simulator.portfolio_battery")

#: The timeframes a daily tablet builds, spelled as ``HTF_TIMEFRAMES`` spells
#: them.
TIMEFRAMES = ("1d", "1w", "1M")

#: The timeframe every non-crypto RA-StoneTablet carries. ``resample`` folds
#: these rows.
TABLET_TIMEFRAME = "1d"

#: The timeframe every crypto RA-StoneTablet carries, the live store's native
#: one; ``StoneTabletsRegistry`` rolls it up to every other.
CRYPTO_TABLET_TIMEFRAME = NATIVE_TIMEFRAME

#: The order the walk's timeframes are reported in: the registry's, native
#: first, then the folded daily ones.
TIMEFRAME_ORDER = tuple(SUPPORTED_TIMEFRAMES) + tuple(
    one for one in TIMEFRAMES if one not in SUPPORTED_TIMEFRAMES
)

#: The span label covering every candle the RA tablets hold.
FULL_SPAN = "All"

#: Every span a run may be asked for: the archive's six, the live fleet's
#: test run, and the whole tape.
SPANS = (FULL_SPAN,) + tuple(PERIODS)

#: The signal one crypto asset's retrieval emits through ``signal_contract``
#: when it lands, and the one a refusal emits.
TABLET_RETRIEVED_SIGNAL = "sim.tablet.retrieved"
TABLET_REFUSED_SIGNAL = "sim.tablet.refused"

#: The refusal a crypto bot carries when its asset's ``CRYPTO_TABLET_TIMEFRAME``
#: tablet does not cover the span after retrieval.
NO_TABLET_AT_FORMAT = "no {timeframe} tablet for {asset} on {exchange_id} over {span}"
VENUE_REFUSED_FORMAT = "{exchange_id} refused {asset} at {timeframe}: {error}"
UNROLLED_FORMAT = (
    "{timeframe} is not a timeframe the registry rolls {native} up to; "
    "supported: {supported}"
)

#: The Activity Log lines ``retrieve_tablets`` writes through ``progress``.
RETRIEVING_LINE_FORMAT = (
    "Retrieving {asset} {timeframe} from {exchange_id}: {candles:,} candle(s) "
    "in {chunks} chunk(s), {calls} call(s), about {mb:.1f} MB, "
    "{since} to {until}."
)
RETRIEVED_LINE_FORMAT = (
    "{asset} {timeframe} retrieved: {appended:,} candle(s) appended in "
    "{chunks} chunk(s) fetched, {calls} call(s), into {files} under {root}."
)
REFUSED_LINE_FORMAT = (
    "{asset} {timeframe} refused by {exchange_id} after {chunks} chunk(s): "
    "{error}; {asset} reads {outcome} at {timeframe}."
)
COVERED_LINE_FORMAT = (
    "{asset} {timeframe} already covers {since} to {until}; nothing fetched."
)

#: The one line the chooser shows before the press.
COST_LINE_FORMAT = (
    "{timeframe} tablets to retrieve from {exchange_id} before the run: {assets}; "
    "{candles:,} candle(s), {calls} call(s), about {mb:.1f} MB. OK retrieves them, "
    "then runs."
)
COST_ASSET_FORMAT = "{asset} {candles:,}"
NO_COST_TEXT = (
    "Every crypto tablet holds {timeframe} over this span; nothing to retrieve."
)
NO_CRYPTO_TEXT = (
    "No crypto asset in this choice; the daily tablets are read as they are."
)

#: The default Target Balance of one generated Battery bot, the operator's
#: figure; a portfolio's mix shares ``DEFAULT_TARGET_USD`` per symbol.
DEFAULT_TARGET_USD = 500.0

#: ``scrumming_interval`` as the Bot Wizard opens it.
SCRUMMING_INTERVAL_PCT = 1.0

#: ``PortfolioResult.fleet_origin`` when the held fleet's own bots ran.
HELD_FLEET = "held"

#: Which venue a symbol's tablets are read from. Crypto prefers the venue the
#: product trades.
CRYPTO_EXCHANGE = "coinbase"
EQUITY_EXCHANGE = "yahoo"

#: The signals one portfolio's start and end emit through ``signal_contract``.
PORTFOLIO_STARTED_SIGNAL = "sim.battery.portfolio_started"
PORTFOLIO_FINISHED_SIGNAL = "sim.battery.portfolio_finished"

#: The comparison every Battery figure serves, in the words the report reads.
COMPARISON_RULE = (
    "HODL end is the Target Balance bought at the walk's opening bar and held to "
    "its last bar; Harvest-Fold end is the same capital walked by the scrumming "
    "bot on the IVP's logic, its units at the last close plus the cash its "
    "partial exits left; difference is Harvest-Fold end less HODL end, as a "
    "figure and as a percentage of HODL end; historical trough is the lowest the "
    "untraded holding read on a walked bar. Nothing ranks or declares a winner."
)

#: The Activity Log lines one (bot, timeframe) walk writes through ``progress``.
WALK_STARTED_LINE_FORMAT = (
    "Walking {asset} {timeframe} on {exchange_id}: {bars:,} bar(s), "
    "{evaluations:,} evaluation(s) to make."
)
WALK_PROGRESS_LINE_FORMAT = (
    "{asset} {timeframe}: bar {bar:,} of {bars:,}, {evaluations:,} evaluation(s), "
    "{partial_exits} partial exit(s), {re_entries} re-entr{re_entries_word}, "
    "{seconds:.1f} s."
)
WALK_ENDED_LINE_FORMAT = (
    "{asset} {timeframe} walked: {evaluations:,} evaluation(s) over {bars:,} "
    "bar(s) in {seconds:.1f} s ({per_thousand:.2f} s per 1,000); HODL end "
    "${hodl:,.2f}, Harvest-Fold end ${harvest_fold:,.2f}, difference "
    "{difference:+,.2f} ({difference_pct:+.2f}% of HODL); {partial_exits} partial "
    "exit(s), {re_entries} re-entr{re_entries_word}."
)
WALK_STOPPED_LINE_FORMAT = (
    "{asset} {timeframe} stopped at bar {bar:,} of {bars:,} ({candle_at}): "
    "{evaluations:,} evaluation(s) made."
)

#: The three figures one portfolio at one timeframe reads, on the Activity Log
#: and in the report.
COMPARISON_FORMAT = (
    "HODL end ${hodl:,.2f}; Harvest-Fold end ${harvest_fold:,.2f}; difference "
    "{difference:+,.2f} ({difference_pct:+.2f}% of HODL); historical trough "
    "${trough:,.2f}; {partial_exits} partial exit(s), {re_entries} "
    "re-entr{re_entries_word}"
)
COST_SPAN_FORMAT = "{span} ({bars:,} bars) in {cost}"
COSTED_LINE_FORMAT = (
    "At {per_thousand:.2f} s per 1,000 evaluations a crypto bot at "
    "{timeframe} walks {spans}."
)
STOPPED_LINE_FORMAT = (
    "Stopped by the operator: {reached} of {named} portfolio(s) reached; "
    "{where}; not reached: {not_reached}."
)

NO_TABLET = "no_tablet"
SHORT_TAPE = "short_tape"
RAN = "ran"

SYMBOL_OUTCOMES = (NO_TABLET, SHORT_TAPE, UNCITED_RULE, RAN)

DAY_MS = 86_400_000


def difference_pct_of(hodl_usd: float, harvest_fold_usd: float) -> float:
    """``harvest_fold_usd`` less ``hodl_usd`` as a percentage of ``hodl_usd``;
    zero when ``hodl_usd`` is not above zero."""
    if float(hodl_usd) <= 0.0:
        return 0.0
    return 100.0 * (float(harvest_fold_usd) - float(hodl_usd)) / float(hodl_usd)


def re_entries_word(count: int) -> str:
    """The ending ``re-entr`` takes for ``count``: ``y`` for one, ``ies``
    otherwise."""
    return "y" if int(count) == 1 else "ies"


def seconds_text(seconds: float) -> str:
    """``seconds`` as ``12.3 s``, ``4.5 min`` or ``1.2 h``."""
    value = float(seconds)
    if value < 60.0:
        return f"{value:.1f} s"
    if value < 3600.0:
        return f"{value / 60.0:.1f} min"
    return f"{value / 3600.0:.1f} h"


def comparison_text(
    hodl_usd: float,
    harvest_fold_usd: float,
    trough_usd: float,
    partial_exits: int,
    re_entries: int,
) -> str:
    """``COMPARISON_FORMAT`` over the three figures, the trough and the two
    counts."""
    return COMPARISON_FORMAT.format(
        hodl=float(hodl_usd),
        harvest_fold=float(harvest_fold_usd),
        difference=float(harvest_fold_usd) - float(hodl_usd),
        difference_pct=difference_pct_of(hodl_usd, harvest_fold_usd),
        trough=float(trough_usd),
        partial_exits=int(partial_exits),
        re_entries=int(re_entries),
        re_entries_word=re_entries_word(re_entries),
    )


@dataclass(frozen=True)
class TabletRead:
    """One RA-StoneTablet file a bot's walk read: its MANIFEST row's ``file``,
    ``timeframe``, ``candles`` and ``sha256``."""

    file: str
    timeframe: str
    candles: int
    sha256: str

    @property
    def row(self) -> dict:
        """The four fields as the report's Tablets section carries them."""
        return {
            "file": self.file,
            "timeframe": self.timeframe,
            "candles": int(self.candles),
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class SymbolRun:
    """One symbol's whole pass over one span at one timeframe.

    ``tablet_timeframe`` names the timeframe the tablet read carried and
    ``tablets`` the files; ``refusal`` names why a ``NO_TABLET`` run read no
    bar; ``ticks`` counts the evaluations the walk made over every bar from
    the ``MIN_CANDLES``th on, ``walk_seconds`` how long they took, and
    ``stopped`` with ``bars_reached`` where Stop ended the walk.
    """

    asset: str
    symbol: str
    exchange_id: str
    timeframe: str
    outcome: str
    capital_usd: float = 0.0
    bars: int = 0
    ticks: int = 0
    walk_seconds: float = 0.0
    stopped: bool = False
    bars_reached: int = 0
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
    tablet_timeframe: str = ""
    tablets: tuple = ()
    refusal: str = ""

    @property
    def ran(self) -> bool:
        """True while ``outcome`` reads ``RAN``."""
        return self.outcome == RAN

    @property
    def tablet_rows(self) -> list[dict]:
        """Each ``TabletRead.row`` in ``tablets``."""
        return [one.row for one in self.tablets]

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
        ``cash_usd``; the Harvest-Fold end."""
        return self.end_units * self.end_price + self.cash_usd

    @property
    def difference_usd(self) -> float:
        """``accumulation_usd`` less ``baseline_usd``: Harvest-Fold end less
        HODL end."""
        return self.accumulation_usd - self.baseline_usd

    @property
    def difference_pct(self) -> float:
        """``difference_usd`` as a percentage of ``baseline_usd``."""
        return difference_pct_of(self.baseline_usd, self.accumulation_usd)

    @property
    def evaluations_expected(self) -> int:
        """``evaluations_expected`` over ``bars`` when the walk ran, else zero."""
        return evaluations_expected(self.bars) if self.ran else 0

    @property
    def seconds_per_thousand(self) -> float:
        """``walk_seconds`` scaled to 1,000 evaluations."""
        return seconds_per_thousand(self.walk_seconds, self.ticks)

    @property
    def partial_exits(self) -> int:
        """How many fills in ``trades`` are a scrum sell."""
        return sum(1 for one in self.trades if one.side == SCRUM)

    @property
    def re_entries(self) -> int:
        """How many fills in ``trades`` are a fold buy."""
        return sum(1 for one in self.trades if one.side == FOLD)

    @property
    def units_gained(self) -> float:
        """``end_units`` less ``start_units``."""
        return self.end_units - self.start_units

    @property
    def trade_count(self) -> int:
        """How many fills are in ``trades``."""
        return len(self.trades)

    @property
    def stopped_at(self) -> str:
        """Where Stop ended this walk, ``WALK_STOPPED_LINE_FORMAT`` without
        the evaluation count's context; empty when it ran to its end."""
        if not self.stopped:
            return ""
        return WALK_STOPPED_LINE_FORMAT.format(
            asset=self.asset,
            timeframe=self.timeframe,
            bar=int(self.bars_reached),
            bars=int(self.bars),
            candle_at=iso_stamp(self.last_ts_ms),
            evaluations=int(self.ticks),
        )


def day_ms(day: str) -> int:
    """Midnight UTC of a ``YYYY-MM-DD`` day, in milliseconds."""
    parsed = datetime.strptime(str(day), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def tablet_timeframe_for(asset: str) -> str:
    """The timeframe ``asset``'s RA tablet carries: ``CRYPTO_TABLET_TIMEFRAME``
    for a crypto asset, else ``TABLET_TIMEFRAME``."""
    return CRYPTO_TABLET_TIMEFRAME if is_crypto(asset) else TABLET_TIMEFRAME


def timeframe_rank(timeframe: str) -> int:
    """``timeframe``'s place in ``TIMEFRAME_ORDER``; one past the end when it
    is not there."""
    try:
        return TIMEFRAME_ORDER.index(str(timeframe))
    except ValueError:
        return len(TIMEFRAME_ORDER)


def bot_timeframes(bot: SimBot, timeframes: Sequence[str] = TIMEFRAMES) -> tuple:
    """The timeframes the walk evaluates ``bot`` at: a crypto bot its own
    ``ta_timeframe`` on the native ``5m`` tablet and then each of
    ``timeframes`` in ``SUPPORTED_TIMEFRAMES``, the ones the registry rolls
    ``5m`` up to; a non-crypto bot ``timeframes`` as given, folded from its
    daily tablet."""
    if not is_crypto(bot.asset):
        return tuple(str(one) for one in timeframes)
    own = str(bot.ta_timeframe or CRYPTO_TABLET_TIMEFRAME)
    rolled = [
        str(one)
        for one in timeframes
        if str(one) in SUPPORTED_TIMEFRAMES and str(one) != own
    ]
    return (own, *sorted(rolled, key=timeframe_rank))


def walk_timeframes(
    bots: Sequence[SimBot], timeframes: Sequence[str] = TIMEFRAMES
) -> tuple:
    """Every timeframe any bot in ``bots`` walks, once, in ``TIMEFRAME_ORDER``."""
    found = {one for bot in bots for one in bot_timeframes(bot, timeframes)}
    return tuple(sorted(found, key=timeframe_rank))


def span_bounds(span: str, entries: Sequence[Any]) -> tuple[int, int]:
    """``(start_ms, end_ms)`` for ``span``, ``FULL_SPAN`` reading ``entries``.

    A ``period_window`` label answers its window, the end day included; an
    unknown label answers ``FULL_SPAN``, and no entry answers ``(0, 0)``.
    """
    window = period_window(str(span))
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


def asset_candles(
    source: Any, asset: str, exchange_id: str, timeframe: str = TABLET_TIMEFRAME
) -> list[list[float]]:
    """Every ``timeframe`` candle ``asset`` holds on ``exchange_id``, oldest
    first, one per stamp; a ``5m`` file beside a daily one is left out."""
    by_stamp: dict[int, list[float]] = {}
    for entry in source.entries():
        if (
            entry.asset != str(asset)
            or entry.exchange_id != str(exchange_id)
            or str(entry.timeframe) != str(timeframe)
        ):
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
    """``CRYPTO_EXCHANGE`` for a crypto asset, whose ``5m`` tablet is read
    from and retrieved through that venue; else ``exchange_for`` when ``asset``
    holds a tablet, else ``EQUITY_EXCHANGE``, so a bot is seated even when its
    symbol reads ``NO_TABLET``."""
    if is_crypto(asset):
        return CRYPTO_EXCHANGE
    return exchange_for(asset, entries) or EQUITY_EXCHANGE


def generated_bot(asset: str, exchange_id: str, target_usd: float) -> SimBot:
    """One scrumming ``SimBot`` for ``asset`` on ``exchange_id`` at
    ``target_usd``, ``ta_timeframe`` the ``tablet_timeframe_for`` its asset,
    ``bot_id`` the pair and venue, ``origin`` ``BATTERY_ORIGIN``."""
    bot = new_bot(
        f"{asset}/USD",
        exchange_id,
        target_usd,
        ta_timeframe=tablet_timeframe_for(asset),
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
    bars: Sequence[Sequence[float]],
    timeframe: str,
    on_trade: Optional[TradeSink] = None,
    emitter: Optional[RunEmitter] = None,
    tablet_timeframe: str = "",
    tablets: Sequence[TabletRead] = (),
    refusal: str = "",
    progress: Optional[Callable[[str], None]] = None,
    stop: Optional[Callable[[], bool]] = None,
) -> SymbolRun:
    """Walk ``bot`` over every bar of ``bars``, already at ``timeframe``
    through ``TapeCache.bars``, at its own ``target_usd``, handing ``on_trade``,
    ``emitter`` and ``stop`` to ``walk``, timing ``walk`` alone, handing
    ``progress`` ``WALK_STARTED_LINE_FORMAT`` before it,
    ``WALK_PROGRESS_LINE_FORMAT`` every ``PROGRESS_EVERY_BARS`` bars and
    ``WALK_ENDED_LINE_FORMAT`` or ``WALK_STOPPED_LINE_FORMAT`` after it, and
    read the result.

    No bar answers ``NO_TABLET`` carrying ``refusal``, a class with no rule in
    ``cited_rule_for`` answers ``UNCITED_RULE``, and too few bars answers
    ``SHORT_TAPE``; ``emitter.bot_line`` names each, and every run carries
    ``tablet_timeframe`` and the ``tablets`` it read.
    """
    from ..trading.indicators.types import candles_from_raw
    from .back_test import no_tablet_line, short_tablet_line, uncited_rule_line

    asset = bot.asset
    exchange_id = bot.exchange_id
    capital_usd = float(bot.target_usd or 0.0)
    bars = [list(row) for row in bars]
    symbol = bot.symbol or f"{asset}/USD"

    def say(line: str) -> None:
        if progress is not None:
            progress(line)

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
            refusal=refusal
            or NO_TABLET_AT_FORMAT.format(
                timeframe=tablet_timeframe or timeframe,
                asset=asset,
                exchange_id=exchange_id,
                span="the span",
            ),
            tablet_timeframe=tablet_timeframe,
            tablets=tuple(tablets),
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
            tablet_timeframe=tablet_timeframe,
            tablets=tuple(tablets),
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
            tablet_timeframe=tablet_timeframe,
            tablets=tuple(tablets),
        )
    walked = replace(bot, ta_timeframe=timeframe)
    expected = evaluations_expected(len(bars))
    say(
        WALK_STARTED_LINE_FORMAT.format(
            asset=asset,
            timeframe=timeframe,
            exchange_id=exchange_id,
            bars=len(bars),
            evaluations=expected,
        )
    )
    filled: list[SimTrade] = []

    def took(trade: SimTrade) -> None:
        filled.append(trade)
        if on_trade is not None:
            on_trade(trade)

    started = time.perf_counter()

    def on_tick(bar: int, bar_count: int, ticks: int) -> None:
        if bar % PROGRESS_EVERY_BARS != 0 or bar >= bar_count:
            return
        say(
            WALK_PROGRESS_LINE_FORMAT.format(
                asset=asset,
                timeframe=timeframe,
                bar=bar,
                bars=bar_count,
                evaluations=ticks,
                partial_exits=sum(1 for one in filled if one.side == SCRUM),
                re_entries=sum(1 for one in filled if one.side == FOLD),
                re_entries_word=re_entries_word(
                    sum(1 for one in filled if one.side == FOLD)
                ),
                seconds=time.perf_counter() - started,
            )
        )

    result = walk(
        walked,
        candles_from_raw(bars),
        funding=FUNDED_BY_TARGETS,
        rule=rule,
        rules=venue_rules_for(asset, exchange_id, symbol),
        on_trade=took,
        stop=stop,
        emitter=emitter,
        on_tick=on_tick,
    )
    seconds = time.perf_counter() - started
    run = SymbolRun(
        asset=asset,
        symbol=symbol,
        exchange_id=exchange_id,
        timeframe=timeframe,
        outcome=RAN,
        capital_usd=capital_usd,
        bars=len(bars),
        ticks=result.ticks,
        walk_seconds=seconds,
        stopped=result.stopped,
        bars_reached=result.candles_read,
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
        trough_price=min(
            float(bar[4]) for bar in bars[MIN_CANDLES - 1 : result.candles_read]
        ),
        tablet_timeframe=tablet_timeframe,
        tablets=tuple(tablets),
    )
    if run.stopped:
        say(run.stopped_at)
    else:
        say(
            WALK_ENDED_LINE_FORMAT.format(
                asset=asset,
                timeframe=timeframe,
                evaluations=run.ticks,
                bars=run.bars,
                seconds=seconds,
                per_thousand=run.seconds_per_thousand,
                hodl=run.baseline_usd,
                harvest_fold=run.accumulation_usd,
                difference=run.difference_usd,
                difference_pct=run.difference_pct,
                partial_exits=run.partial_exits,
                re_entries=run.re_entries,
                re_entries_word=re_entries_word(run.re_entries),
            )
        )
    return run


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
        """What holding the covered symbols untraded would have ended at: the
        HODL end."""
        return sum(one.baseline_usd for one in self.ran)

    @property
    def accumulation_usd(self) -> float:
        """What the gate chain ended holding across the covered symbols: the
        Harvest-Fold end."""
        return sum(one.accumulation_usd for one in self.ran)

    @property
    def difference_usd(self) -> float:
        """``accumulation_usd`` less ``baseline_usd``."""
        return self.accumulation_usd - self.baseline_usd

    @property
    def difference_pct(self) -> float:
        """``difference_usd`` as a percentage of ``baseline_usd``."""
        return difference_pct_of(self.baseline_usd, self.accumulation_usd)

    @property
    def trough_usd(self) -> float:
        """The sum of each covered symbol's ``trough_usd``, the floor the
        untraded holdings never read below."""
        return sum(one.trough_usd for one in self.ran)

    @property
    def evaluations(self) -> int:
        """The ``ticks`` every run in ``ran`` made."""
        return sum(one.ticks for one in self.ran)

    @property
    def evaluations_expected(self) -> int:
        """The ``evaluations_expected`` of every run in ``ran``."""
        return sum(one.evaluations_expected for one in self.ran)

    @property
    def walk_seconds(self) -> float:
        """The ``walk_seconds`` of every run in ``ran``."""
        return sum(one.walk_seconds for one in self.ran)

    @property
    def seconds_per_thousand(self) -> float:
        """``walk_seconds`` scaled to 1,000 ``evaluations``."""
        return seconds_per_thousand(self.walk_seconds, self.evaluations)

    @property
    def partial_exits(self) -> int:
        """The scrum sells every run in ``ran`` filled."""
        return sum(one.partial_exits for one in self.ran)

    @property
    def re_entries(self) -> int:
        """The fold buys every run in ``ran`` filled."""
        return sum(one.re_entries for one in self.ran)

    @property
    def stopped(self) -> bool:
        """True when Stop ended any run in ``ran``."""
        return any(one.stopped for one in self.ran)

    @property
    def stopped_at(self) -> list[str]:
        """Each ``SymbolRun.stopped_at`` in ``ran`` that is not empty."""
        return [one.stopped_at for one in self.ran if one.stopped]

    @property
    def comparison(self) -> str:
        """``comparison_text`` over the three figures, the trough and the two
        counts."""
        return comparison_text(
            self.baseline_usd,
            self.accumulation_usd,
            self.trough_usd,
            self.partial_exits,
            self.re_entries,
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
            "ticks": self.evaluations,
            "evaluations_expected": self.evaluations_expected,
            "walk_seconds": self.walk_seconds,
            "seconds_per_thousand": self.seconds_per_thousand,
            "scrum_latched": sum(one.scrum_latched for one in ran),
            "fold_latched": sum(one.fold_latched for one in ran),
            "trades": sum(one.trade_count for one in ran),
            "partial_exits": self.partial_exits,
            "re_entries": self.re_entries,
            "fees_usd": sum(one.fees_usd for one in ran),
            "committed_usd": self.committed_usd,
            "baseline_usd": self.baseline_usd,
            "accumulation_usd": self.accumulation_usd,
            "difference_usd": self.difference_usd,
            "difference_pct": self.difference_pct,
            "trough_usd": self.trough_usd,
            "units_gained": sum(one.units_gained for one in ran),
            "missing_usd": self.missing_usd,
            "missing_weight": self.missing_weight,
            "missing_symbols": self.missing_symbols,
            "comparison": self.comparison,
            "stopped": self.stopped,
            "stopped_at": self.stopped_at,
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
    #: True when Stop ended a walk of this portfolio; ``not_walked`` names
    #: each ``(bot_id, timeframe)`` walk Stop kept from starting.
    stopped: bool = False
    not_walked: tuple[str, ...] = ()

    @property
    def comparisons(self) -> dict[str, str]:
        """Each timeframe's ``comparison``, by timeframe."""
        return {one.timeframe: one.comparison for one in self.timeframes}

    @property
    def evaluations(self) -> int:
        """The ``evaluations`` of every timeframe."""
        return sum(one.evaluations for one in self.timeframes)

    @property
    def evaluations_expected(self) -> int:
        """The ``evaluations_expected`` of every timeframe."""
        return sum(one.evaluations_expected for one in self.timeframes)

    @property
    def walk_seconds(self) -> float:
        """The ``walk_seconds`` of every timeframe."""
        return sum(one.walk_seconds for one in self.timeframes)

    @property
    def trade_count(self) -> int:
        """Every fill of every timeframe."""
        return sum(one.trade_count for frame in self.timeframes for one in frame.ran)

    @property
    def stopped_at(self) -> list[str]:
        """Each ``TimeframeResult.stopped_at`` line, in timeframe order."""
        return [line for one in self.timeframes for line in one.stopped_at]

    @property
    def line(self) -> str:
        """One Activity Log line: the name, the span, each timeframe's three
        figures and how many symbols ran at the first timeframe."""
        figures = "; ".join(f"at {tf} {text}" for tf, text in self.comparisons.items())
        first = self.timeframes[0] if self.timeframes else None
        ran = (
            f"{len(first.ran)} of {len(first.runs)}" if first is not None else "0 of 0"
        )
        stopped = " Stopped by the operator." if self.stopped else ""
        return (
            f"{self.name} over {self.span}: {figures or 'no timeframe walked'}; "
            f"{ran} symbol(s) ran; bots {self.fleet_origin}.{stopped}"
        )

    @property
    def summary(self) -> dict:
        """The portfolio's own row, and one row per timeframe."""
        return {
            "portfolio": self.name,
            "description": self.description,
            "span": self.span,
            "first_at": iso_stamp(self.start_ms),
            "last_at": iso_stamp(self.end_ms),
            "timeframes": [one.summary for one in self.timeframes],
            "fleet_origin": self.fleet_origin,
            "bot_ids": list(self.bot_ids),
            "comparisons": self.comparisons,
            "evaluations": self.evaluations,
            "evaluations_expected": self.evaluations_expected,
            "walk_seconds": self.walk_seconds,
            "stopped": self.stopped,
            "stopped_at": self.stopped_at,
            "not_walked": list(self.not_walked),
        }


@dataclass(frozen=True)
class BatteryRun:
    """One Portfolio Battery press, or one portfolio of it: its span, its
    portfolios, the gaps, and the three figures totalled per timeframe."""

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
    #: The ``ParityReport`` written for this run: one portfolio's own, or the
    #: summary over ``portfolio_runs``; None until written, and None on the
    #: summary when the press named one portfolio, whose own report stands.
    report: Any = None
    bots: tuple[SimBot, ...] = ()
    budget_usd: float = 0.0
    fleet_origins: tuple[str, ...] = ()
    #: The id every row of this run carries in ``data.run_id``; empty when
    #: ``run_battery`` was handed no bus.
    run_id: str = ""
    #: What ``RunEmitter.close`` answered: the rows emitted per topic and the
    #: ``EmitObserver`` reading; empty when ``run_battery`` was handed no bus.
    emitted: dict = field(default_factory=dict)
    #: One ``retrieval_row`` per crypto asset ``retrieve_tablets`` walked or
    #: refused before the first walk.
    retrievals: tuple = ()
    #: The names the press asked for, in order; ``not_reached`` those Stop
    #: kept from starting.
    names: tuple[str, ...] = ()
    stopped: bool = False
    not_reached: tuple[str, ...] = ()
    #: One ``BatteryRun`` per portfolio the press ran, each carrying its own
    #: ``report``; empty on a single portfolio's own run.
    portfolio_runs: tuple = ()
    #: ``cost_span`` rows: the 5m bars each named span holds, so the measured
    #: rate costs a crypto bot's walk over it.
    costed: tuple[dict, ...] = ()

    @property
    def refused_assets(self) -> tuple:
        """Each asset in ``retrievals`` the venue refused, sorted."""
        return tuple(sorted(one["asset"] for one in self.retrievals if one["refused"]))

    def frames(self, timeframe: str) -> list[TimeframeResult]:
        """Every portfolio's ``TimeframeResult`` at ``timeframe`` in which a
        symbol ran."""
        return [
            frame
            for portfolio in self.portfolios
            for frame in portfolio.timeframes
            if frame.timeframe == timeframe and frame.ran
        ]

    def totals(self, timeframe: str) -> dict:
        """The three figures, the trough, the two counts and the evaluations
        summed over ``frames`` at ``timeframe``, with the portfolio count."""
        frames = self.frames(timeframe)
        hodl = sum(one.baseline_usd for one in frames)
        harvest_fold = sum(one.accumulation_usd for one in frames)
        partial_exits = sum(one.partial_exits for one in frames)
        re_entries = sum(one.re_entries for one in frames)
        evaluations = sum(one.evaluations for one in frames)
        seconds = sum(one.walk_seconds for one in frames)
        return {
            "timeframe": timeframe,
            "portfolios": len(frames),
            "committed_usd": sum(one.committed_usd for one in frames),
            "baseline_usd": hodl,
            "accumulation_usd": harvest_fold,
            "difference_usd": harvest_fold - hodl,
            "difference_pct": difference_pct_of(hodl, harvest_fold),
            "trough_usd": sum(one.trough_usd for one in frames),
            "partial_exits": partial_exits,
            "re_entries": re_entries,
            "bars": sum(int(run.bars) for one in frames for run in one.ran),
            "evaluations": evaluations,
            "evaluations_expected": sum(one.evaluations_expected for one in frames),
            "walk_seconds": seconds,
            "seconds_per_thousand": seconds_per_thousand(seconds, evaluations),
            "comparison": comparison_text(
                hodl,
                harvest_fold,
                sum(one.trough_usd for one in frames),
                partial_exits,
                re_entries,
            ),
        }

    @property
    def evaluations(self) -> int:
        """The evaluations every portfolio made."""
        return sum(one.evaluations for one in self.portfolios)

    @property
    def evaluations_expected(self) -> int:
        """The evaluations every portfolio's walks were expected to make."""
        return sum(one.evaluations_expected for one in self.portfolios)

    @property
    def walk_seconds(self) -> float:
        """The seconds every portfolio's walks took."""
        return sum(one.walk_seconds for one in self.portfolios)

    @property
    def seconds_per_thousand(self) -> float:
        """``walk_seconds`` scaled to 1,000 ``evaluations``."""
        return seconds_per_thousand(self.walk_seconds, self.evaluations)

    @property
    def rate_line(self) -> str:
        """``RATE_LINE_FORMAT`` over the evaluations, the expected count and
        the seconds."""
        return RATE_LINE_FORMAT.format(
            evaluations=self.evaluations,
            expected=self.evaluations_expected,
            seconds=self.walk_seconds,
            per_thousand=self.seconds_per_thousand,
        )

    @property
    def costed_line(self) -> str:
        """``COSTED_LINE_FORMAT`` over ``costed`` at ``seconds_per_thousand``;
        empty with no rate or no costed span."""
        rate = self.seconds_per_thousand
        if rate <= 0.0 or not self.costed:
            return ""
        spans = " and ".join(
            COST_SPAN_FORMAT.format(
                span=one["span"],
                bars=int(one["bars"]),
                cost=seconds_text(
                    rate * evaluations_expected(int(one["bars"])) / 1000.0
                ),
            )
            for one in self.costed
        )
        return COSTED_LINE_FORMAT.format(
            per_thousand=rate, timeframe=CRYPTO_TABLET_TIMEFRAME, spans=spans
        )

    @property
    def stopped_line(self) -> str:
        """``STOPPED_LINE_FORMAT`` naming the portfolios reached, the bar
        each stopped walk reached and the portfolios not reached; empty
        unless ``stopped``."""
        if not self.stopped:
            return ""
        where = "; ".join(
            line.rstrip(".")
            for portfolio in self.portfolios
            for line in portfolio.stopped_at
        )
        return STOPPED_LINE_FORMAT.format(
            reached=len(self.portfolios),
            named=len(self.names) or len(self.portfolios),
            where=where or "no walk was in progress",
            not_reached=", ".join(self.not_reached) or "none",
        )

    @property
    def summary(self) -> dict:
        """The counts the Portfolio Battery pane reports."""
        return {
            "span": self.span,
            "first_at": iso_stamp(self.start_ms),
            "last_at": iso_stamp(self.end_ms),
            "portfolios": len(self.portfolios),
            "timeframes": list(self.timeframes),
            "symbol_runs": self.symbol_runs,
            "evaluations": self.evaluations,
            "evaluations_expected": self.evaluations_expected,
            "walk_seconds": self.walk_seconds,
            "seconds_per_thousand": self.seconds_per_thousand,
            "gaps": len(self.gaps),
            "missing_assets": list(self.missing_assets),
            "uncited_assets": list(self.uncited_assets),
            "bots": len(self.bots),
            "budget_usd": self.budget_usd,
            "fleet_origins": list(self.fleet_origins),
            "comparison": {tf: self.totals(tf) for tf in self.timeframes},
            "retrievals": [dict(one) for one in self.retrievals],
            "refused_assets": list(self.refused_assets),
            "stopped": self.stopped,
            "not_reached": list(self.not_reached),
            "costed": [dict(one) for one in self.costed],
        }

    @property
    def lines(self) -> list[str]:
        """The span, the budget, the rate, the three figures totalled per
        timeframe, the costed spans, what had no tape and what had no cited
        unit rule, in the pane's own order; the stopped line first when
        ``stopped``."""
        read = self.summary
        if not self.portfolios:
            return (
                [self.stopped_line]
                if self.stopped
                else ["No portfolio reached an RA-StoneTablet with enough candles."]
            )
        out = [
            f"{read['portfolios']} portfolio(s) over {read['span']}, "
            f"{read['first_at']} to {read['last_at']}.",
            f"{read['bots']} bot(s), budget ${read['budget_usd']:,.2f}, the sum of "
            f"their Target Balances; bots {', '.join(read['fleet_origins'])}.",
            f"{read['symbol_runs']} symbol runs at "
            f"{', '.join(read['timeframes'])}; {self.rate_line}",
        ]
        if self.stopped:
            out.insert(0, self.stopped_line)
        for timeframe in self.timeframes:
            total = read["comparison"][timeframe]
            if not total["portfolios"]:
                out.append(f"At {timeframe}: no portfolio walked.")
                continue
            out.append(
                f"At {timeframe} over {total['portfolios']} portfolio(s): "
                f"{total['comparison']}."
            )
        if self.costed_line:
            out.append(self.costed_line)
        if self.missing_assets:
            out.append(
                f"{len(self.missing_assets)} symbol(s) hold no tablet: "
                + ", ".join(self.missing_assets)
            )
        if self.retrievals:
            landed = sum(int(one["candles_appended"]) for one in self.retrievals)
            out.append(
                f"{len(self.retrievals)} crypto asset(s) checked at "
                f"{CRYPTO_TABLET_TIMEFRAME} before the walk: {landed:,} candle(s) "
                f"retrieved, {len(self.refused_assets)} refused"
                + (": " + ", ".join(self.refused_assets) if self.refused_assets else "")
                + "."
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
    """One span's rows and venue per asset, read from ``source`` once.

    ``rows`` is the daily side; ``bars`` reads a bot at one timeframe, a
    crypto bot through ``StoneTabletsRegistry.get_candles`` on ``source``'s
    root and a non-crypto bot through ``resample`` over ``rows``.
    """

    def __init__(self, source: Any, start_ms: int, end_ms: int) -> None:
        """Hold ``source`` and the span every ``rows`` read is sliced to."""
        self._source = source
        self._entries = source.entries()
        self._start_ms = int(start_ms)
        self._end_ms = int(end_ms)
        self._rows: dict[str, list[list[float]]] = {}
        self._venues: dict[str, str] = {}
        self._registry: Optional[StoneTabletsRegistry] = None
        self._refusals: dict[str, str] = {}

    def venue(self, asset: str) -> str:
        """The exchange ``asset`` is read from: ``CRYPTO_EXCHANGE`` for a
        crypto asset, else ``exchange_for``, empty when it holds no tablet."""
        if asset not in self._venues:
            self._venues[asset] = (
                CRYPTO_EXCHANGE
                if is_crypto(asset)
                else exchange_for(asset, self._entries)
            )
        return self._venues[asset]

    def rows(self, asset: str) -> list[list[float]]:
        """``asset``'s daily candles inside the span, empty when it has none."""
        if asset not in self._rows:
            venue = self.venue(asset)
            whole = asset_candles(self._source, asset, venue) if venue else []
            self._rows[asset] = slice_span(whole, self._start_ms, self._end_ms)
        return self._rows[asset]

    def registry(self) -> StoneTabletsRegistry:
        """The ``StoneTabletsRegistry`` over ``source``'s root, built once."""
        if self._registry is None:
            self._registry = StoneTabletsRegistry(self._source.root())
        return self._registry

    def refuse(self, asset: str, reason: str) -> None:
        """Hold ``reason`` so every ``bars`` read of ``asset`` answers no bar."""
        self._refusals[str(asset)] = str(reason)

    def refusal(self, asset: str) -> str:
        """What ``refuse`` held for ``asset``, empty when nothing."""
        return self._refusals.get(str(asset), "")

    def bars(self, bot: SimBot, timeframe: str) -> list[list[float]]:
        """``bot``'s bars at ``timeframe`` inside the span: a refused asset
        answers none, a crypto bot reads ``registry().get_candles`` on
        ``CRYPTO_EXCHANGE``, and a non-crypto bot ``resample`` over ``rows``."""
        asset = bot.asset
        if self.refusal(asset):
            return []
        if not is_crypto(asset):
            return resample(self.rows(asset), timeframe)
        if str(timeframe) not in SUPPORTED_TIMEFRAMES:
            return []
        if self._end_ms <= self._start_ms:
            return []
        return self.registry().get_candles(
            asset,
            self._start_ms,
            self._end_ms - 1,
            timeframe=str(timeframe),
            exchange_id=CRYPTO_EXCHANGE,
        )

    def bar_refusal(self, bot: SimBot, timeframe: str, span: str) -> str:
        """Why ``bars`` answered none for ``bot`` at ``timeframe``: the held
        ``refusal``, ``UNROLLED_FORMAT`` for a timeframe outside
        ``SUPPORTED_TIMEFRAMES``, else ``NO_TABLET_AT_FORMAT``."""
        held = self.refusal(bot.asset)
        if held:
            return held
        if is_crypto(bot.asset) and str(timeframe) not in SUPPORTED_TIMEFRAMES:
            return UNROLLED_FORMAT.format(
                timeframe=timeframe,
                native=CRYPTO_TABLET_TIMEFRAME,
                supported=", ".join(SUPPORTED_TIMEFRAMES),
            )
        return NO_TABLET_AT_FORMAT.format(
            timeframe=tablet_timeframe_for(bot.asset),
            asset=bot.asset,
            exchange_id=self.venue(bot.asset) or bot.exchange_id,
            span=span,
        )

    def tablets_read(self, bot: SimBot) -> tuple:
        """The ``TabletRead`` rows ``bars`` reads for ``bot``: the entries at
        ``tablet_timeframe_for`` its asset on its venue whose year overlaps the
        span."""
        timeframe = tablet_timeframe_for(bot.asset)
        venue = self.venue(bot.asset)
        first_year = _year_of(self._start_ms) if self._end_ms > self._start_ms else 0
        last_year = (
            _year_of(self._end_ms - 1) if self._end_ms > self._start_ms else 9999
        )
        return tuple(
            TabletRead(
                file=entry.file,
                timeframe=entry.timeframe,
                candles=int(entry.candle_count),
                sha256=entry.checksum_sha256,
            )
            for entry in self._entries
            if entry.asset == bot.asset
            and entry.exchange_id == venue
            and str(entry.timeframe) == timeframe
            and first_year <= int(entry.year) <= last_year
        )


def _year_of(ts_ms: int) -> int:
    """The UTC calendar year of ``ts_ms``."""
    return datetime.fromtimestamp(int(ts_ms) / 1000.0, tz=timezone.utc).year


def run_portfolio(
    name: str,
    tablets: Any,
    span: str = FULL_SPAN,
    timeframes: Sequence[str] = TIMEFRAMES,
    cache: Optional[TapeCache] = None,
    held: Optional[dict] = None,
    bots: Optional[dict[str, SimBot]] = None,
    fleet_origin: str = BATTERY_ORIGIN,
    on_trade: Optional[TradeSink] = None,
    emitter: Optional[RunEmitter] = None,
    progress: Optional[Callable[[str], None]] = None,
    stop: Optional[Callable[[], bool]] = None,
) -> PortfolioResult:
    """Walk every symbol of ``name`` over ``span`` at each timeframe
    ``bot_timeframes`` gives its bot from ``timeframes``, each on the bot
    ``bots`` names for it, ``plan_run`` with no held fleet when ``bots`` is
    None; the bars come from ``TapeCache.bars``, every walk hands
    ``progress`` its lines, and ``stop`` answering True before a walk ends
    the portfolio with ``stopped`` set and that walk in ``not_walked``.

    ``held`` keeps one ``(bot_id, timeframe, target)`` run inside one
    portfolio, so a bot named twice is walked once and its trades reach
    ``on_trade`` and ``emitter`` once.
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
    seated = [bots[asset] for asset in symbols if asset in bots]
    by_timeframe: list[TimeframeResult] = []
    halted = False
    not_walked: list[str] = []
    for timeframe in walk_timeframes(seated, timeframes):
        walked: list[SymbolRun] = []
        for bot in seated:
            if timeframe not in bot_timeframes(bot, timeframes):
                continue
            key = (bot.bot_id, timeframe, round(float(bot.target_usd or 0.0), 2))
            if key in walked_by_key:
                walked.append(walked_by_key[key])
                continue
            if halted or (stop is not None and stop()):
                halted = True
                not_walked.append(f"{bot.asset} {timeframe}")
                continue
            bars = tape.bars(bot, timeframe)
            walked_by_key[key] = run_symbol(
                bot,
                bars,
                timeframe,
                on_trade,
                emitter,
                tablet_timeframe=tablet_timeframe_for(bot.asset),
                tablets=tape.tablets_read(bot),
                refusal=("" if bars else tape.bar_refusal(bot, timeframe, str(span))),
                progress=progress,
                stop=stop,
            )
            halted = halted or walked_by_key[key].stopped
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
        stopped=halted,
        not_walked=tuple(not_walked),
    )


def crypto_assets(bots: Sequence[SimBot]) -> list[str]:
    """Each crypto asset among ``bots``, once, sorted."""
    return sorted({bot.asset for bot in bots if is_crypto(bot.asset)})


def retrieval_until_ms(end_ms: int, now_ms: Optional[int] = None) -> int:
    """The newest ``CRYPTO_TABLET_TIMEFRAME`` candle a span ending at
    ``end_ms`` asks for: one step before ``end_ms``, capped at
    ``closed_until_ms``."""
    return min(int(end_ms) - int(STEP_5M_MS), closed_until_ms(now_ms))


def battery_costs(
    tablets: Any, bots: Sequence[SimBot], start_ms: int, end_ms: int
) -> list[RetrievalCost]:
    """One ``retrieval_cost`` per ``crypto_assets`` of ``bots`` over
    ``[start_ms, retrieval_until_ms(end_ms)]`` on ``CRYPTO_EXCHANGE``, read
    off a ``StoneTabletsRegistry`` on ``tablets``' root; an empty span costs
    nothing."""
    assets = crypto_assets(bots)
    if not assets or int(end_ms) <= int(start_ms):
        return []
    registry = StoneTabletsRegistry(tablets.root())
    until = retrieval_until_ms(end_ms)
    return [
        retrieval_cost(registry, asset, CRYPTO_EXCHANGE, int(start_ms), until)
        for asset in assets
    ]


def plan_costs(tablets: Any, names: Sequence[str], span: str) -> list[RetrievalCost]:
    """``battery_costs`` for the bots ``plan_run`` seats for ``names`` over
    ``span_bounds`` of ``span``, what the chooser states before a press."""
    plan = plan_run(names, tablets)
    start_ms, end_ms = span_bounds(span, tablets.entries())
    return battery_costs(tablets, plan.bots, start_ms, end_ms)


def cost_line(costs: Sequence[RetrievalCost], crypto: bool = True) -> str:
    """The chooser's one line over ``costs``: ``COST_LINE_FORMAT`` naming each
    asset that needs candles, ``NO_COST_TEXT`` when none does, and
    ``NO_CRYPTO_TEXT`` when the choice holds no crypto asset."""
    if not crypto:
        return NO_CRYPTO_TEXT
    needed = [one for one in costs if one.needed]
    if not needed:
        return NO_COST_TEXT.format(timeframe=CRYPTO_TABLET_TIMEFRAME)
    candles = sum(one.candles for one in needed)
    calls = sum(one.calls for one in needed)
    return COST_LINE_FORMAT.format(
        timeframe=CRYPTO_TABLET_TIMEFRAME,
        exchange_id=CRYPTO_EXCHANGE,
        assets=", ".join(
            COST_ASSET_FORMAT.format(asset=one.asset, candles=one.candles)
            for one in needed
        ),
        candles=candles,
        calls=calls,
        mb=sum(one.bytes for one in needed) / 1_000_000.0,
    )


def retrieval_row(
    cost: RetrievalCost,
    outcome: Optional[RetrievalOutcome],
    calls: int,
    files: Sequence[str],
) -> dict:
    """One asset's retrieval as ``BatteryRun.retrievals`` carries it: the
    ``cost`` asked, what ``outcome`` appended over the chunks it walked and
    fetched and whether it ``refused``, the venue ``calls`` counted as
    ``venue_pages`` and the ``files`` written."""
    refused = outcome is not None and outcome.refused
    return {
        "asset": cost.asset,
        "exchange_id": cost.exchange_id,
        "timeframe": CRYPTO_TABLET_TIMEFRAME,
        "since": iso_stamp(cost.since_ms),
        "until": iso_stamp(cost.until_ms),
        "candles_asked": int(cost.candles),
        "calls_asked": int(cost.calls),
        "chunks": int(outcome.chunks) if outcome is not None else 0,
        "chunks_fetched": int(outcome.chunks_ok) if outcome is not None else 0,
        "calls": int(calls),
        "candles_appended": int(outcome.candles_appended) if outcome is not None else 0,
        "refused": bool(refused),
        "error": str(outcome.error) if outcome is not None else "",
        "files": list(files),
    }


def tablet_files_for(tablets: Any, asset: str, since_ms: int, until_ms: int) -> list:
    """The ``CRYPTO_TABLET_TIMEFRAME`` file names ``tablets`` holds for
    ``asset`` on ``CRYPTO_EXCHANGE`` whose year overlaps ``[since_ms,
    until_ms]``, sorted."""
    first, last = _year_of(since_ms), _year_of(until_ms)
    return sorted(
        entry.file
        for entry in tablets.entries()
        if entry.asset == str(asset)
        and entry.exchange_id == CRYPTO_EXCHANGE
        and str(entry.timeframe) == CRYPTO_TABLET_TIMEFRAME
        and first <= int(entry.year) <= last
    )


def retrieve_tablets(
    tablets: Any,
    costs: Sequence[RetrievalCost],
    span: str,
    connector: Any = None,
    progress: Optional[Callable[[str], None]] = None,
) -> list[dict]:
    """Fetch every ``RetrievalCost`` in ``costs`` that is ``needed`` through
    ``tablet_retrieval.retrieve`` over ``tablets``' root and ``connector``, a
    fresh ``ReadOnlyConnector`` when None, and answer one ``retrieval_row``
    per cost.

    ``progress`` is handed ``RETRIEVING_LINE_FORMAT`` before each fetch and
    ``RETRIEVED_LINE_FORMAT``, ``REFUSED_LINE_FORMAT`` or
    ``COVERED_LINE_FORMAT`` after it; each landed asset emits
    ``TABLET_RETRIEVED_SIGNAL`` and each refusal ``TABLET_REFUSED_SIGNAL``
    through ``signal_contract.emit``.
    """
    calls: list[VenueCall] = []
    reader = (
        connector if connector is not None else ReadOnlyConnector(on_call=calls.append)
    )
    counted = connector is None
    root = tablets.root()
    rows: list[dict] = []

    def say(line: str) -> None:
        if progress is not None:
            progress(line)

    for cost in costs:
        if not cost.needed:
            say(
                COVERED_LINE_FORMAT.format(
                    asset=cost.asset,
                    timeframe=CRYPTO_TABLET_TIMEFRAME,
                    since=iso_stamp(cost.since_ms),
                    until=iso_stamp(cost.until_ms),
                )
            )
            rows.append(
                retrieval_row(
                    cost,
                    None,
                    0,
                    tablet_files_for(tablets, cost.asset, cost.since_ms, cost.until_ms),
                )
            )
            continue
        say(
            RETRIEVING_LINE_FORMAT.format(
                asset=cost.asset,
                timeframe=CRYPTO_TABLET_TIMEFRAME,
                exchange_id=cost.exchange_id,
                candles=cost.candles,
                chunks=cost.chunks,
                calls=cost.calls,
                mb=cost.bytes / 1_000_000.0,
                since=iso_stamp(cost.since_ms),
                until=iso_stamp(cost.until_ms),
            )
        )
        before = len(calls)
        outcome = asyncio.run(
            retrieve(
                root,
                reader,
                cost.asset,
                cost.exchange_id,
                cost.since_ms,
                cost.until_ms,
            )
        )
        made = (
            sum(venue_pages(one) for one in calls[before:])
            if counted
            else int(outcome.chunks_ok)
        )
        files = tablet_files_for(tablets, cost.asset, cost.since_ms, cost.until_ms)
        row = retrieval_row(cost, outcome, made, files)
        rows.append(row)
        if outcome.refused:
            say(
                REFUSED_LINE_FORMAT.format(
                    asset=cost.asset,
                    timeframe=CRYPTO_TABLET_TIMEFRAME,
                    exchange_id=cost.exchange_id,
                    chunks=outcome.chunks,
                    error=outcome.error,
                    outcome=NO_TABLET,
                )
            )
            pin_emit(
                TABLET_REFUSED_SIGNAL,
                actual={
                    "asset": cost.asset,
                    "timeframe": CRYPTO_TABLET_TIMEFRAME,
                    "span": str(span),
                    "reason": outcome.error,
                    "refused": True,
                },
                expected={
                    "asset": cost.asset,
                    "timeframe": CRYPTO_TABLET_TIMEFRAME,
                    "span": str(span),
                    "reason": "",
                    "refused": False,
                },
                ok=False,
                context={"row": row, "root": str(root)},
            )
            continue
        say(
            RETRIEVED_LINE_FORMAT.format(
                asset=cost.asset,
                timeframe=CRYPTO_TABLET_TIMEFRAME,
                appended=outcome.candles_appended,
                chunks=outcome.chunks_ok,
                calls=made,
                files=", ".join(files) or "no file",
                root=root,
            )
        )
        pin_emit(
            TABLET_RETRIEVED_SIGNAL,
            actual={
                "asset": cost.asset,
                "timeframe": CRYPTO_TABLET_TIMEFRAME,
                "years": sorted({_year_of(cost.since_ms), _year_of(cost.until_ms)}),
                "candles_appended": int(outcome.candles_appended),
                "calls": int(made),
                "refused": False,
            },
            expected={
                "asset": cost.asset,
                "timeframe": CRYPTO_TABLET_TIMEFRAME,
                "years": sorted({_year_of(cost.since_ms), _year_of(cost.until_ms)}),
                "candles_appended": int(cost.candles),
                "calls": int(cost.calls),
                "refused": False,
            },
            ok=outcome.candles_appended > 0,
            context={"row": row, "root": str(root), "calls_counted": counted},
        )
    return rows


def cost_spans(entries: Sequence[Any]) -> list[dict]:
    """One row per span the report costs, ``TEST_RUN_SPAN`` and ``FULL_SPAN``:
    the ``CRYPTO_TABLET_TIMEFRAME`` bars its ``span_bounds`` hold at
    ``STEP_5M_MS``."""
    out: list[dict] = []
    for span in (TEST_RUN_SPAN, FULL_SPAN):
        start_ms, end_ms = span_bounds(span, entries)
        bars = max(0, (int(end_ms) - int(start_ms)) // int(STEP_5M_MS))
        out.append(
            {"span": str(span), "timeframe": CRYPTO_TABLET_TIMEFRAME, "bars": bars}
        )
    return out


def merged_emitted(reads: Sequence[dict]) -> dict:
    """Every ``RunEmitter.close`` reading in ``reads`` summed into one: the
    topic counts added, the observer's emissions and field presence added,
    its violations added by topic, kind and detail."""
    emitted: dict[str, int] = {}
    emissions: dict[str, int] = {}
    presence: dict[str, dict[str, int]] = {}
    violations: dict[tuple, dict] = {}
    declared = 0
    for read in reads:
        for topic, count in (read.get("emitted") or {}).items():
            emitted[topic] = emitted.get(topic, 0) + int(count)
        observer = read.get("observer") or {}
        declared = max(declared, int(observer.get("topics_declared", 0) or 0))
        for topic, count in (observer.get("emissions") or {}).items():
            emissions[topic] = emissions.get(topic, 0) + int(count)
        for topic, fields in (observer.get("field_presence") or {}).items():
            held = presence.setdefault(topic, {})
            for name, count in fields.items():
                held[name] = held.get(name, 0) + int(count)
        for one in observer.get("violations") or []:
            key = (one.get("topic"), one.get("kind"), one.get("detail"))
            if key in violations:
                violations[key]["count"] += int(one.get("count", 1))
            else:
                violations[key] = dict(one)
    return {
        "emitted": emitted,
        "observer": {
            "topics_declared": declared,
            "topics_seen": sum(1 for count in emissions.values() if count > 0),
            "emissions": dict(sorted(emissions.items())),
            "violations": [violations[key] for key in sorted(violations, key=str)],
            "field_presence": {
                topic: dict(sorted(fields.items()))
                for topic, fields in sorted(presence.items())
            },
        },
    }


def portfolio_run(
    result: PortfolioResult,
    bots: Sequence[SimBot],
    tablets: Any,
    start_ms: int,
    end_ms: int,
    timeframes: Sequence[str],
    retrievals: Sequence[dict],
    run_id: str,
    emitted: dict,
    costed: Sequence[dict],
) -> BatteryRun:
    """The ``BatteryRun`` of one portfolio: ``result`` alone, its ``bots``,
    the gaps of its assets, the retrievals of its crypto assets, and the
    walks it made."""
    runs = [one for frame in result.timeframes for one in frame.runs]
    assets = sorted({one.asset for one in runs})
    return BatteryRun(
        span=result.span,
        start_ms=start_ms,
        end_ms=end_ms,
        portfolios=(result,),
        gaps=tuple(gaps_in_span(assets, start_ms, end_ms)),
        timeframes=walk_timeframes(bots, timeframes),
        missing_assets=tuple(
            sorted({one.asset for one in runs if one.outcome == NO_TABLET})
        ),
        tablet_root=str(tablets.root()),
        symbol_runs=len(runs),
        uncited_assets=tuple(
            sorted({one.asset for one in runs if one.outcome == UNCITED_RULE})
        ),
        bots=tuple(bots),
        budget_usd=run_budget_usd(bots),
        fleet_origins=tuple(sorted({bot.origin for bot in bots})),
        run_id=run_id,
        emitted=dict(emitted),
        retrievals=tuple(one for one in retrievals if one["asset"] in assets),
        names=(result.name,),
        stopped=result.stopped,
        costed=tuple(costed),
    )


def emit_portfolio_started(name: str, bots: Sequence[SimBot], span: str) -> None:
    """Emit ``PORTFOLIO_STARTED_SIGNAL`` for ``name``: the bots seated against
    the portfolio's symbol count."""
    symbols = PORTFOLIOS[name].symbols if name in PORTFOLIOS else ()
    pin_emit(
        PORTFOLIO_STARTED_SIGNAL,
        actual={"portfolio": str(name), "bots": len(bots), "span": str(span)},
        expected={"portfolio": str(name), "bots": len(symbols), "span": str(span)},
        context={"bot_ids": [bot.bot_id for bot in bots]},
    )


def emit_portfolio_finished(run: BatteryRun) -> None:
    """Emit ``PORTFOLIO_FINISHED_SIGNAL`` for the one portfolio of ``run``:
    per timeframe the three figures, the evaluations made against the
    evaluations expected, and the fills; ``ok`` when every walk that ran made
    every evaluation expected of it."""
    result = run.portfolios[0]
    actual = {
        "portfolio": result.name,
        "span": result.span,
        "stopped": bool(result.stopped),
        "timeframes": {
            frame.timeframe: {
                "hodl_end": round(frame.baseline_usd, 2),
                "harvest_fold_end": round(frame.accumulation_usd, 2),
                "difference": round(frame.difference_usd, 2),
                "evaluations": frame.evaluations,
                "fills": sum(one.trade_count for one in frame.ran),
            }
            for frame in result.timeframes
        },
    }
    expected = {
        "portfolio": result.name,
        "span": result.span,
        "stopped": False,
        "timeframes": {
            frame.timeframe: {"evaluations": frame.evaluations_expected}
            for frame in result.timeframes
        },
    }
    pin_emit(
        PORTFOLIO_FINISHED_SIGNAL,
        actual=actual,
        expected=expected,
        ok=(
            not result.stopped
            and all(
                frame.evaluations == frame.evaluations_expected
                for frame in result.timeframes
            )
        ),
        context={
            "run_id": run.run_id,
            "report": str(run.report.markdown_path) if run.report is not None else "",
            "bot_ids": list(result.bot_ids),
        },
    )


def run_battery(
    tablets: Any,
    names: Sequence[str] = (),
    span: str = FULL_SPAN,
    timeframes: Sequence[str] = TIMEFRAMES,
    plan: Optional[RunPlan] = None,
    progress: Optional[Callable[[str], None]] = None,
    on_trade: Optional[TradeSink] = None,
    bus: Any = None,
    connector: Any = None,
    stop: Optional[Callable[[], bool]] = None,
    on_portfolio_started: Optional[Callable[[str, list], None]] = None,
    on_portfolio_finished: Optional[Callable[[str, BatteryRun], None]] = None,
) -> BatteryRun:
    """Run each portfolio in ``names`` over ``span`` through
    ``_walk_portfolios`` on ``plan``'s bots, one at a time with its own
    report, and write the summary through ``write_report`` onto
    ``BatteryRun.report`` when the press names more than one portfolio.

    ``progress`` is handed each retrieval line, each walk's lines and each
    portfolio's line, ``on_trade`` each ``SimTrade`` as it fills, ``connector``
    the venue path ``retrieve_tablets`` fetches through, ``stop`` is read
    before each portfolio, each walk and each tick, ``on_portfolio_started``
    and ``on_portfolio_finished`` are called around each portfolio, ``bus``
    becomes one ``RunEmitter`` per portfolio, and a ``_walk_portfolios`` that
    raises reaches ``write_partial`` with the exception and re-raises.
    """
    from .parity_report import (
        PORTFOLIO_BATTERY,
        new_run_id,
        write_partial,
        write_report,
    )

    press_id = new_run_id(PORTFOLIO_BATTERY)
    try:
        outcome = _walk_portfolios(
            tablets,
            names,
            span,
            timeframes,
            plan,
            progress,
            on_trade,
            bus,
            connector,
            stop,
            on_portfolio_started,
            on_portfolio_finished,
        )
    except Exception as exc:
        write_partial(
            PORTFOLIO_BATTERY,
            exc,
            tablets=tablets,
            names=tuple(names),
            span=str(span),
            run_id=press_id,
        )
        raise
    outcome = replace(outcome, run_id=press_id)
    if len(outcome.names) > 1 or not outcome.portfolio_runs:
        return replace(
            outcome, report=write_report(PORTFOLIO_BATTERY, outcome, tablets)
        )
    return outcome


def _walk_portfolios(
    tablets: Any,
    names: Sequence[str],
    span: str,
    timeframes: Sequence[str],
    plan: Optional[RunPlan],
    progress: Optional[Callable[[str], None]],
    on_trade: Optional[TradeSink] = None,
    bus: Any = None,
    connector: Any = None,
    stop: Optional[Callable[[], bool]] = None,
    on_portfolio_started: Optional[Callable[[str, list], None]] = None,
    on_portfolio_finished: Optional[Callable[[str, BatteryRun], None]] = None,
) -> BatteryRun:
    """Run each portfolio ``plan`` names, ``plan_run`` over ``names`` when it
    is None, one at a time: ``retrieve_tablets`` over ``battery_costs``
    first, then per portfolio ``on_portfolio_started``, its walks over a
    ``TapeCache`` that refuses each asset the venue refused on a
    ``RunEmitter`` of its own, its ``portfolio_run`` written through
    ``write_report``, ``emit_portfolio_finished`` and ``on_portfolio_finished``;
    ``stop`` answering True before a portfolio names it in ``not_reached``."""
    from .parity_report import PORTFOLIO_BATTERY, new_run_id, write_report

    chosen = plan if plan is not None else plan_run(names, tablets)
    start_ms, end_ms = span_bounds(span, tablets.entries())
    costs = battery_costs(tablets, chosen.bots, start_ms, end_ms)
    retrievals = retrieve_tablets(tablets, costs, str(span), connector, progress)
    tape = TapeCache(tablets, start_ms, end_ms)
    for row in retrievals:
        if row["refused"]:
            tape.refuse(
                row["asset"],
                VENUE_REFUSED_FORMAT.format(
                    exchange_id=row["exchange_id"],
                    asset=row["asset"],
                    timeframe=CRYPTO_TABLET_TIMEFRAME,
                    error=row["error"],
                ),
            )
    costed = cost_spans(tablets.entries())
    results: list[PortfolioResult] = []
    runs: list[BatteryRun] = []
    not_reached: list[str] = []
    halted = False
    for name in chosen.names:
        if halted or (stop is not None and stop()):
            halted = True
            not_reached.append(name)
            continue
        bots = chosen.by_portfolio.get(name, {})
        seated = [bots[asset] for asset in PORTFOLIOS[name].symbols if asset in bots]
        if on_portfolio_started is not None:
            on_portfolio_started(name, list(seated))
        emit_portfolio_started(name, seated, str(span))
        emitter = RunEmitter(bus, new_run_id(PORTFOLIO_BATTERY), PORTFOLIO_BATTERY)
        result = run_portfolio(
            name,
            tablets,
            span,
            timeframes,
            tape,
            {},
            bots,
            chosen.origins.get(name, BATTERY_ORIGIN),
            on_trade,
            emitter,
            progress,
            stop,
        )
        emitted = emitter.close()
        one = portfolio_run(
            result,
            seated,
            tablets,
            start_ms,
            end_ms,
            timeframes,
            retrievals,
            emitter.run_id,
            emitted,
            costed,
        )
        one = replace(one, report=write_report(PORTFOLIO_BATTERY, one, tablets))
        emit_portfolio_finished(one)
        if progress is not None:
            progress(result.line)
        if on_portfolio_finished is not None:
            on_portfolio_finished(name, one)
        results.append(result)
        runs.append(one)
        halted = halted or result.stopped
    walked = [
        one for result in results for frame in result.timeframes for one in frame.runs
    ]
    assets = sorted({one.asset for one in walked})
    return BatteryRun(
        span=str(span),
        start_ms=start_ms,
        end_ms=end_ms,
        portfolios=tuple(results),
        gaps=tuple(gaps_in_span(assets, start_ms, end_ms)),
        timeframes=walk_timeframes(chosen.bots, timeframes),
        missing_assets=tuple(
            sorted({one.asset for one in walked if one.outcome == NO_TABLET})
        ),
        tablet_root=str(tablets.root()),
        symbol_runs=len(walked),
        uncited_assets=tuple(
            sorted({one.asset for one in walked if one.outcome == UNCITED_RULE})
        ),
        bots=tuple(chosen.bots),
        budget_usd=chosen.budget_usd,
        fleet_origins=chosen.fleet_origins,
        emitted=merged_emitted([one.emitted for one in runs]),
        retrievals=tuple(retrievals),
        names=tuple(chosen.names),
        stopped=halted,
        not_reached=tuple(not_reached),
        portfolio_runs=tuple(runs),
        costed=tuple(costed),
    )


__all__ = [
    "COMPARISON_RULE",
    "CRYPTO_EXCHANGE",
    "DAY_MS",
    "DEFAULT_TARGET_USD",
    "EQUITY_EXCHANGE",
    "FULL_SPAN",
    "HELD_FLEET",
    "MIN_CANDLES",
    "NO_TABLET",
    "PORTFOLIO_FINISHED_SIGNAL",
    "PORTFOLIO_STARTED_SIGNAL",
    "PROGRESS_EVERY_BARS",
    "RAN",
    "SCRUMMING_INTERVAL_PCT",
    "SHORT_TAPE",
    "SPANS",
    "SYMBOL_OUTCOMES",
    "TABLET_REFUSED_SIGNAL",
    "TABLET_RETRIEVED_SIGNAL",
    "TABLET_TIMEFRAME",
    "CRYPTO_TABLET_TIMEFRAME",
    "TIMEFRAMES",
    "TIMEFRAME_ORDER",
    "BatteryRun",
    "PortfolioResult",
    "RunPlan",
    "SymbolRun",
    "TabletRead",
    "TapeCache",
    "TimeframeResult",
    "asset_candles",
    "battery_bot",
    "battery_costs",
    "bot_timeframes",
    "bucket_key",
    "comparison_text",
    "cost_line",
    "cost_spans",
    "crypto_assets",
    "day_ms",
    "difference_pct_of",
    "emit_portfolio_finished",
    "emit_portfolio_started",
    "evaluations_expected",
    "exchange_for",
    "fold_bucket",
    "gaps_in_span",
    "generated_bot",
    "matched_bots",
    "merged_emitted",
    "plan_costs",
    "plan_run",
    "plan_venue",
    "portfolio_run",
    "re_entries_word",
    "resample",
    "retrieval_row",
    "retrieval_until_ms",
    "retrieve_tablets",
    "run_battery",
    "run_portfolio",
    "run_symbol",
    "seconds_per_thousand",
    "seconds_text",
    "slice_span",
    "span_bounds",
    "symbol_targets",
    "tablet_files_for",
    "tablet_timeframe_for",
    "timeframe_rank",
    "walk_timeframes",
]
