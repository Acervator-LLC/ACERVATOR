"""Back Test Mode: the shipped gate chains walked over Stone Tablet candles.

``new_bot`` makes one operator-defined ``SimBot`` and ``fleet_source.live_fleet``
supplies the imported clone. ``tape_context`` builds a ``GateContext`` from a
tablet window and the simulated position, ``validation.latch`` evaluates the same
scrum and fold chains live runs, and ``run`` walks each bot's tablet keeping
units, cash and tranches. ``missing_pairs`` names the tablets a run needs and
``download_missing`` fills them through the shipped ``GapFiller``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from ..trading.gate_chain import GateContext
from .fleet_source import SimBot
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

NEW_ORIGIN = "new"

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

BOT_OUTCOMES = (NO_TABLET, SHORT_TABLET, BACK_TESTED)


@dataclass(frozen=True)
class SimTrade:
    """One scrum sell or fold buy the tape produced."""

    bot_id: str
    symbol: str
    side: str
    ts_ms: int
    price: float
    units: float
    usd: float
    fee_usd: float


@dataclass
class SimPosition:
    """What a simulated bot holds as the tape advances."""

    units: float = 0.0
    cash_usd: float = 0.0
    tranches: int = 0

    def value_usd(self, price: float) -> float:
        """``units`` at ``price``, ignoring cash held from an earlier scrum."""
        return self.units * float(price)


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
    delta = position.value_usd(close) - target_usd
    interval_usd = target_usd * float(bot.scrumming_interval_pct) / 100.0
    below_interval = abs(delta) < interval_usd
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
        delta_pct=abs(delta),
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


def fee_usd(notional_usd: float, fee_pct: float) -> float:
    """``fee_pct`` of ``notional_usd``."""
    return abs(float(notional_usd)) * float(fee_pct) / 100.0


def apply_scrum(
    bot: SimBot, position: SimPosition, price: float, ts_ms: int, delta: float
) -> Optional[SimTrade]:
    """Sell ``delta / price`` units and hold the proceeds as one fold tranche.

    Nothing fills when ``position`` holds fewer units than the sell needs.
    """
    units = abs(float(delta)) / float(price)
    if units <= 0.0 or units > position.units:
        return None
    notional = units * float(price)
    fee = fee_usd(notional, bot.trading_fee_pct or DEFAULT_TRADING_FEE_PCT)
    position.units -= units
    position.cash_usd += notional - fee
    position.tranches += 1
    return SimTrade(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        side=SCRUM,
        ts_ms=int(ts_ms),
        price=float(price),
        units=units,
        usd=notional,
        fee_usd=fee,
    )


def apply_fold(
    bot: SimBot, position: SimPosition, price: float, ts_ms: int, delta: float
) -> Optional[SimTrade]:
    """Buy ``delta`` back at ``price`` and spend one tranche.

    The spend is capped at ``position.cash_usd``, so one scrum's proceeds fund
    one fold.
    """
    spend = min(abs(float(delta)), position.cash_usd)
    if spend <= 0.0 or position.tranches <= 0:
        return None
    fee = fee_usd(spend, bot.trading_fee_pct or DEFAULT_TRADING_FEE_PCT)
    units = (spend - fee) / float(price)
    if units <= 0.0:
        return None
    position.units += units
    position.cash_usd -= spend
    position.tranches -= 1
    return SimTrade(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        side=FOLD,
        ts_ms=int(ts_ms),
        price=float(price),
        units=units,
        usd=spend,
        fee_usd=fee,
    )


def opening_position(bot: SimBot, price: float) -> SimPosition:
    """A ``SimPosition`` worth exactly ``bot.target_usd`` at ``price``."""
    target_usd = float(bot.target_usd or 0.0)
    units = target_usd / float(price) if price > 0.0 else 0.0
    return SimPosition(units=units, cash_usd=0.0, tranches=0)


def walk(bot: SimBot, candles: Sequence[Any], step: int = 1) -> BotResult:
    """Run ``bot`` over ``candles``, one gate-chain evaluation every ``step``
    bars."""
    from ..trading.ta_engine import VotingEngine

    if len(candles) < MIN_CANDLES:
        return BotResult(
            bot_id=bot.bot_id,
            symbol=bot.symbol,
            tablet_key="",
            outcome=SHORT_TABLET,
            candles_read=len(candles),
        )
    engine = VotingEngine()
    timeframe = bot.ta_timeframe or DEFAULT_TIMEFRAME
    position = opening_position(bot, float(candles[MIN_CANDLES - 1].close))
    start_units = position.units
    trades: list[SimTrade] = []
    scrum_latched = 0
    fold_latched = 0
    ticks = 0
    fees = 0.0
    for index in range(MIN_CANDLES - 1, len(candles), max(int(step), 1)):
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
            filled = apply_scrum(bot, position, price, stamp, context.delta)
        elif armed["fold_armed"]:
            fold_latched += 1
            filled = apply_fold(bot, position, price, stamp, context.delta)
        if filled is not None:
            trades.append(filled)
            fees += filled.fee_usd
    return BotResult(
        bot_id=bot.bot_id,
        symbol=bot.symbol,
        tablet_key="",
        outcome=BACK_TESTED,
        candles_read=len(candles),
        ticks=ticks,
        scrum_latched=scrum_latched,
        fold_latched=fold_latched,
        trades=tuple(trades),
        start_units=start_units,
        end_units=position.units,
        start_price=float(candles[MIN_CANDLES - 1].close),
        end_price=float(candles[-1].close),
        cash_usd=position.cash_usd,
        fees_usd=fees,
        first_ts_ms=int(candles[0].timestamp),
        last_ts_ms=int(candles[-1].timestamp),
    )


@dataclass(frozen=True)
class BackTestRun:
    """One Back Test pass: its fleet, its tablets and what the tape produced."""

    exchange_id: str
    bots: tuple[SimBot, ...]
    results: tuple[BotResult, ...]
    missing: tuple[tuple[str, str], ...] = ()
    bot_outcomes: dict[str, int] = field(default_factory=dict)
    interval_ms: int = 0

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
        }

    @property
    def lines(self) -> list[str]:
        """The fleet, the tape span and what latched, in the pane's own
        order."""
        read = self.summary
        if not read["bots_run"]:
            return ["No bot reached a Stone Tablet with enough candles."]
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
        return out


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
) -> BackTestRun:
    """Walk every bot over its own tablet and report what the gates latched.

    ``max_candles`` caps how much of each tape is read and ``ticks_per_bot``
    replaces ``step`` with one ``shared_step`` every bot ticks on.
    """
    from ..trading.indicators.types import candles_from_raw

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
    for bot in bots:
        entry = tablet_for(entries, bot.asset, bot.exchange_id)
        if entry is None:
            outcomes[NO_TABLET] += 1
            results.append(
                BotResult(
                    bot_id=bot.bot_id,
                    symbol=bot.symbol,
                    tablet_key="",
                    outcome=NO_TABLET,
                )
            )
            continue
        raw = tablets.candles(entry)
        if max_candles:
            raw = raw[-int(max_candles) :]
        if not interval_ms and len(raw) > 1:
            interval_ms = candle_interval_ms([int(one[0]) for one in raw])
        walked = walk(bot, candles_from_raw(raw), step)
        key = entry.file
        if key.endswith(TABLET_SUFFIX):
            key = key[: -len(TABLET_SUFFIX)]
        results.append(BotResult(**{**walked.__dict__, "tablet_key": key}))
        outcomes[walked.outcome] += 1
    return BackTestRun(
        exchange_id=exchange_id,
        bots=tuple(bots),
        results=tuple(results),
        missing=tuple(missing_pairs(bots, entries)),
        bot_outcomes=outcomes,
        interval_ms=interval_ms,
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
    "BOT_OUTCOMES",
    "BackTestRun",
    "BotResult",
    "DEFAULT_SCRUM_DETECT_PCT",
    "DEFAULT_TIMEFRAME",
    "DEFAULT_TRADING_FEE_PCT",
    "FOLD",
    "MIN_CANDLES",
    "NEW_ORIGIN",
    "NO_TABLET",
    "SCRUM",
    "SHORT_TABLET",
    "TA_CONFIDENCE_FLOOR",
    "WINDOW_CANDLES",
    "SimPosition",
    "SimTrade",
    "apply_fold",
    "apply_scrum",
    "bb_detect_thresholds",
    "download_missing",
    "fee_usd",
    "missing_pairs",
    "new_bot",
    "new_bots",
    "opening_position",
    "run",
    "shared_step",
    "signal_detail",
    "ta_direction",
    "tape_context",
    "trend_reading",
    "walk",
]
