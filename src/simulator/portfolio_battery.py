"""Portfolio Battery Mode: every portfolio symbol walked over its RA-StoneTablet.

``span_bounds`` names the window a run covers, ``asset_candles`` gathers one
asset's RA tablets into one series and ``resample`` folds those daily rows into
``1d``, ``1w`` and ``1M`` bars. ``run_symbol`` hands the bars to
``back_test.walk``, the same gate chain a live bot ticks, and reads the
buy-and-hold baseline off that walk's own ``start_price`` and ``end_price``.
``run_portfolio`` sums those runs per timeframe and ``run_battery`` reports every
portfolio, a symbol with no tablet as missing weight and a recorded gap through
``gaps_in_span``. Each symbol walks under the unit rule ``cited_rule_for``
names for its class on its venue, and a symbol with no cited rule is
``UNCITED_RULE``, missing weight, and not walked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from ..trading.stone_tablets.ra_fetcher import read_gaps
from .back_test import (
    FUNDED_BY_TARGETS,
    MIN_CANDLES,
    UNCITED_RULE,
    SimTrade,
    cited_rule_for,
    new_bot,
    walk,
)
from .portfolios import PERIODS, PORTFOLIOS, is_crypto
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

#: What one symbol is given, the Bot Wizard's own ``target_balance`` default.
SYMBOL_CAPITAL_USD = 200.0

#: ``scrumming_interval`` as the Bot Wizard opens it.
SCRUMMING_INTERVAL_PCT = 1.0

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
    def accumulation_usd(self) -> float:
        """What the walk ended holding: ``end_units`` at ``end_price``, plus
        ``cash_usd``."""
        return self.end_units * self.end_price + self.cash_usd

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


def run_symbol(
    asset: str,
    rows: Sequence[Sequence[float]],
    exchange_id: str,
    timeframe: str,
    capital_usd: float = SYMBOL_CAPITAL_USD,
    ticks: int = TICKS_PER_SYMBOL,
) -> SymbolRun:
    """Walk ``asset`` over ``rows`` folded to ``timeframe`` and read the result.

    ``rows`` are one span's daily tablet candles; no bar answers ``NO_TABLET``,
    a class with no rule in ``cited_rule_for`` answers ``UNCITED_RULE``, and
    too few bars answers ``SHORT_TAPE``.
    """
    from ..trading.indicators.types import candles_from_raw

    bars = resample(rows, timeframe)
    symbol = f"{asset}/USD"
    if not bars:
        return SymbolRun(
            asset=asset,
            symbol=symbol,
            exchange_id=exchange_id,
            timeframe=timeframe,
            outcome=NO_TABLET,
            capital_usd=float(capital_usd),
        )
    class_name, venue, rule = cited_rule_for(asset, exchange_id)
    if rule is None:
        return SymbolRun(
            asset=asset,
            symbol=symbol,
            exchange_id=exchange_id,
            timeframe=timeframe,
            outcome=UNCITED_RULE,
            capital_usd=float(capital_usd),
            bars=len(bars),
            first_ts_ms=int(bars[0][0]),
            last_ts_ms=int(bars[-1][0]),
            asset_class=class_name,
            venue=venue,
        )
    if len(bars) < MIN_CANDLES:
        return SymbolRun(
            asset=asset,
            symbol=symbol,
            exchange_id=exchange_id,
            timeframe=timeframe,
            outcome=SHORT_TAPE,
            capital_usd=float(capital_usd),
            bars=len(bars),
            first_ts_ms=int(bars[0][0]),
            last_ts_ms=int(bars[-1][0]),
            asset_class=class_name,
            venue=venue,
            unit_rule=rule,
        )
    bot = battery_bot(asset, exchange_id, timeframe, capital_usd)
    result = walk(
        bot,
        candles_from_raw(bars),
        walk_step(len(bars), ticks),
        FUNDED_BY_TARGETS,
        rule=rule,
    )
    return SymbolRun(
        asset=asset,
        symbol=symbol,
        exchange_id=exchange_id,
        timeframe=timeframe,
        outcome=RAN,
        capital_usd=float(capital_usd),
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
        }

    @property
    def lines(self) -> list[str]:
        """The span, what improved, what had no tape and what had no cited
        unit rule, in the pane's own order."""
        read = self.summary
        if not self.portfolios:
            return ["No portfolio reached an RA-StoneTablet with enough candles."]
        out = [
            f"{read['portfolios']} portfolio(s) over {read['span']}, "
            f"{read['first_at']} to {read['last_at']}.",
            f"{read['symbol_runs']} symbol runs at "
            f"{', '.join(read['timeframes'])}.",
            f"{read['portfolios_improved']} of {read['portfolios']} portfolio(s) "
            "beat their own buy-and-hold at one timeframe or more.",
        ]
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
    capital_usd: float = SYMBOL_CAPITAL_USD,
    ticks: int = TICKS_PER_SYMBOL,
    cache: Optional[TapeCache] = None,
    held: Optional[dict] = None,
) -> PortfolioResult:
    """Walk every symbol of ``name`` over ``span`` at each of ``timeframes``.

    ``held`` keeps one ``(asset, timeframe)`` run across portfolios, so a symbol
    two portfolios share is walked once.
    """
    entry = PORTFOLIOS.get(str(name))
    symbols = entry.symbols if entry is not None else ()
    start_ms, end_ms = span_bounds(span, tablets.entries())
    tape = cache if cache is not None else TapeCache(tablets, start_ms, end_ms)
    walked_by_key = held if held is not None else {}
    by_timeframe: list[TimeframeResult] = []
    for timeframe in timeframes:
        walked: list[SymbolRun] = []
        for asset in symbols:
            key = (asset, timeframe)
            if key not in walked_by_key:
                walked_by_key[key] = run_symbol(
                    asset,
                    tape.rows(asset),
                    tape.venue(asset),
                    timeframe,
                    capital_usd,
                    ticks,
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
    )


def run_battery(
    tablets: Any,
    names: Sequence[str] = (),
    span: str = FULL_SPAN,
    timeframes: Sequence[str] = TIMEFRAMES,
    capital_usd: float = SYMBOL_CAPITAL_USD,
    ticks: int = TICKS_PER_SYMBOL,
) -> BatteryRun:
    """Run each portfolio in ``names`` over ``span``, or every portfolio when it
    is empty."""
    wanted = [str(one) for one in names] or sorted(PORTFOLIOS)
    start_ms, end_ms = span_bounds(span, tablets.entries())
    tape = TapeCache(tablets, start_ms, end_ms)
    walked_by_key: dict[tuple[str, str], SymbolRun] = {}
    results = [
        run_portfolio(
            name, tablets, span, timeframes, capital_usd, ticks, tape, walked_by_key
        )
        for name in wanted
        if name in PORTFOLIOS
    ]
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
    )


__all__ = [
    "BETTER",
    "CRYPTO_EXCHANGE",
    "DAY_MS",
    "EQUITY_EXCHANGE",
    "FULL_SPAN",
    "LEVEL",
    "MIN_CANDLES",
    "NO_TABLET",
    "RAN",
    "SCRUMMING_INTERVAL_PCT",
    "SHORT_TAPE",
    "SPANS",
    "SYMBOL_CAPITAL_USD",
    "SYMBOL_OUTCOMES",
    "TABLET_TIMEFRAME",
    "TICKS_PER_SYMBOL",
    "TIMEFRAMES",
    "WORSE",
    "BatteryRun",
    "PortfolioResult",
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
    "resample",
    "run_battery",
    "run_portfolio",
    "run_symbol",
    "slice_span",
    "span_bounds",
    "walk_step",
]
