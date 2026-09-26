"""The Paper Trader's fleet path, forked from the Simulator's ``FleetSource``:
the records the paper fleet file holds under ``PAPER_ROOT``, and the bots
Import Live Fleet copies out of the live bot_state record, read only.

``PaperFleetSource`` answers ``READ_NAMES``, holds one fleet and no run mode,
writes ``paper_path`` alone, and ``__getattr__`` raises ``SendRefused`` for
every other name. ``bots``, ``exchanges``, ``statuses`` and ``aggregate`` read
the held records alone; ``stored_records`` and ``stored_exchanges`` read
``bot_state.json``, and ``import_live_fleet`` copies its records on one
exchange whole into the held map under their own ids with ``LIVE_ORIGIN``,
each written ``loaded_idle``. ``PaperBot`` is a read-only record forked from
the live bot's config, its stats and its saved state, ``row_status`` answers
one as the status dict the two bot tables read, ``aggregate_stats`` answers the
header strip's figures over a list of them, and ``strip_aggregate`` lays the
paper ledger's four money figures over it.
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass
from dataclasses import fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from ..core.io_utils import atomic_write_json
from ..trading.container.config import (
    BotConfig,
    BotMode,
    BotState,
    as_finite_float,
    bot_config_kwargs,
    make_bot_config,
)
from ..trading.scrumming.sizing import DRAWDOWN_STATE, priced_usd
from ..trading.smart_wire import mature_profit_usd
from .live_feed_source import SendRefused
from .paper_paths import PAPER_FLEET_NAME, get_paper_root

logger = logging.getLogger("acervator.paper.fleet")

BOT_STATE_NAME = "bot_state.json"
STATE_DIR_NAME = ".acervator"

#: The ``saved_at_human`` format ``StateManager.save_state`` writes.
SAVED_AT_HUMAN_FORMAT = "%Y-%m-%d %H:%M:%S"

#: Every name ``PaperFleetSource`` answers. ``__getattr__`` refuses the rest.
READ_NAMES = (
    "root",
    "path",
    "saved_at",
    "bots",
    "bot_for",
    "record_for",
    "exchanges",
    "symbols",
    "statuses",
    "aggregate",
    "create",
    "paper_bot_for",
    "set_state",
    "set_config_field",
    "write_stats",
    "remove",
    "clear",
    "stored_records",
    "stored_exchanges",
    "import_live_fleet",
    "paper_dir",
    "paper_path",
    "save",
)

#: Every field ``BotConfig`` declares, the names a paper record's ``config``
#: may hold.
CONFIG_FIELD_NAMES = frozenset(one.name for one in dataclass_fields(BotConfig))

#: The Bot Settings window's three non-``BotConfig`` fields and the record key
#: each one is stored under.
RECORD_FIELDS = {
    "enable_phantoms": "phantoms_enabled",
    "phantom_timeframes": "phantom_timeframes",
    "lock_candle_count": "lock_candle_count",
}

LIVE_ORIGIN = "live"
NEW_ORIGIN = "new"

SCRUMMING_MODE = "scrumming"
EXTRACTOR_MODE = "extractor"

#: The characters of ``uuid4`` a live bot keeps as its ``bot_id``.
BOT_ID_LENGTH = 8

#: The ``state`` an ``ExtractorBot`` writes on a position below its entry value,
#: the one ``DRAWDOWN_STATE`` that ``POSITION_STATE_DRAWDOWN`` also reads.
EXTRACTOR_DRAWDOWN_STATE = DRAWDOWN_STATE

#: The three names ``ExtractorBot.pool_color`` answers.
POOL_GREEN = "green"
POOL_YELLOW = "yellow"
POOL_RED = "red"

#: What a live bot's ``get_status`` answers for ``auto_fire`` before its first
#: tick; a stored record holds no gate state, so every paper row reads this.
PRE_TICK_AUTO_FIRE = {
    "scrum_armed": False,
    "fold_armed": False,
    "scrum_blockers": ["pre-tick"],
    "fold_blockers": ["pre-tick"],
    "evaluated_at_tick": 0,
}

#: ``scrum_read_rate_min`` for a record without the key, ``BotConfig``'s default.
SCRUM_READ_RATE_MIN_DEFAULT = 5

#: ``phantoms_enabled`` for a record without the key, as the restore reads it.
PHANTOMS_ENABLED_DEFAULT = True

#: The keys of ``PaperLedger.figures`` laid over the aggregate's money keys.
LEDGER_TO_AGGREGATE = (
    ("spendable_usd", "wallet_cash_usd"),
    ("locked_usd", "crypto_position_value_usd"),
    ("realized_profit_usd", "total_realized_exchange"),
    ("mature_profit_usd", "total_mature_exchange"),
)


@dataclass(frozen=True)
class PaperBot:
    """One paper bot: its ids, its symbol, the config the gates read, and the
    figures the Scrumming Bots table, the Extractor Bots table and the Status
    tab draw. ``chunk_size_usd``, ``chunk_size_base``, ``chunk_free_base``,
    ``n_positions_open`` and ``n_positions_drawdown`` are the Extractor's pool
    figures and stay zero on a scrumming bot."""

    bot_id: str
    symbol: str
    exchange_id: str
    base_currency: str
    origin: str
    target_usd: Optional[float] = None
    ta_timeframe: str = ""
    scrumming_interval_pct: float = 0.0
    scrum_read_rate_min: int = SCRUM_READ_RATE_MIN_DEFAULT
    trading_fee_pct: float = 0.0
    bb_midline_gate: bool = True
    bb_tolerance_pct: float = 1.0
    bb_landing_strip_candles: int = 2
    scrum_detect_pct: float = 75.0
    scrum_require_ta_bullish: bool = True
    scrum_hold_in_uptrend: bool = True
    scrum_defer_to_htf: bool = True
    fold_require_ta_bearish: bool = True
    fold_defer_to_htf: bool = True
    mode: str = SCRUMMING_MODE
    state: str = ""
    current_price: float = 0.0
    holdings: float = 0.0
    position_value_usd: float = 0.0
    quote_to_usd: float = 1.0
    live_target_usd: float = 0.0
    total_trades: int = 0
    active_buys: int = 0
    active_sells: int = 0
    total_scrummed_usd: float = 0.0
    total_folded_usd: float = 0.0
    realised_pnl_usd: float = 0.0
    unrealised_pnl_usd: float = 0.0
    total_errors: int = 0
    last_error: str = ""
    uptime_s: float = 0.0
    realized_pnl_exchange_usd: float = 0.0
    avg_entry_exchange: float = 0.0
    cost_basis_exchange_usd: float = 0.0
    fees_paid_exchange_usd: float = 0.0
    exchange_trade_count: int = 0
    exchange_data_fresh_ts: float = 0.0
    scrum_target_mode: Optional[str] = None
    position_ceiling_enabled: bool = False
    position_ceiling_multiple: float = 5.0
    max_target_growth_pct: float = 1.0
    detonation_enabled: bool = False
    detonation_timeframe: str = "1d"
    chunk_size_usd: float = 0.0
    chunk_size_base: float = 0.0
    chunk_free_base: float = 0.0
    n_positions_open: int = 0
    n_positions_drawdown: int = 0
    phantoms_enabled: bool = PHANTOMS_ENABLED_DEFAULT
    phantom_timeframes: tuple = ()
    cash_balance_usd: float = 0.0
    ytd_scrummed_usd: float = 0.0
    ytd_folded_usd: float = 0.0
    profit_folding_active: bool = True

    @property
    def asset(self) -> str:
        """The base of ``symbol``, ``BTC`` for ``BTC/USD``."""
        return self.symbol.split("/")[0] if self.symbol else ""


#: Units, dollars and counts a record draws when as_finite_float refuses them.
REFUSED_FIGURE: float = 0.0


def _lots_units(lots: Any) -> float:
    """The units held across ``lots``, which is how the live bot sets
    ``_current_holdings`` from ``_main_lots``."""
    if not isinstance(lots, list):
        return REFUSED_FIGURE
    reads = [as_finite_float(lot.get("units")) for lot in lots if isinstance(lot, dict)]
    return sum(REFUSED_FIGURE if read is None else read for read in reads)


def _extractor_figures(config: dict, record: dict) -> dict:
    """The five pool figures of an extractor record, keyed as ``PaperBot`` names
    them, every figure zero when ``config`` is not in extractor mode.
    ``extractor_state`` is what ``ExtractorBot.export_state`` wrote, and a
    record holding none reads the base size and the free base equal to the
    dollar size with no position."""
    if str(config.get("mode") or SCRUMMING_MODE) != EXTRACTOR_MODE:
        return {
            "chunk_size_usd": 0.0,
            "chunk_size_base": 0.0,
            "chunk_free_base": 0.0,
            "n_positions_open": 0,
            "n_positions_drawdown": 0,
        }
    state = record.get("extractor_state")
    state = state if isinstance(state, dict) else {}
    configured_size = as_finite_float(config.get("extractor_chunk_size_usd"))
    configured_size = REFUSED_FIGURE if configured_size is None else configured_size
    size_usd = as_finite_float(state.get("chunk_size_usd"))
    chunk_size_usd = configured_size if size_usd is None else size_usd
    size_base = as_finite_float(state.get("chunk_size_base"))
    chunk_size_base = chunk_size_usd if size_base is None else size_base
    free_base = as_finite_float(state.get("chunk_free_base"))
    chunk_free_base = chunk_size_base if free_base is None else free_base
    positions = state.get("positions")
    positions = (
        [one for one in positions if isinstance(one, dict)]
        if isinstance(positions, list)
        else []
    )
    return {
        "chunk_size_usd": chunk_size_usd,
        "chunk_size_base": chunk_size_base,
        "chunk_free_base": chunk_free_base,
        "n_positions_open": len(positions),
        "n_positions_drawdown": sum(
            1 for one in positions if one.get("state") == EXTRACTOR_DRAWDOWN_STATE
        ),
    }


def extractor_pool_color(n_positions_open: int, n_positions_drawdown: int) -> str:
    """The Liquid cell's colour name for one extractor, the rule of
    ``ExtractorBot.pool_color``: ``POOL_GREEN`` with no position open,
    ``POOL_RED`` with one in drawdown, ``POOL_YELLOW`` otherwise."""
    if n_positions_open <= 0:
        return POOL_GREEN
    if n_positions_drawdown > 0:
        return POOL_RED
    return POOL_YELLOW


def paper_bot_from_record(
    bot_id: str, record: dict, origin: str = LIVE_ORIGIN
) -> Optional[PaperBot]:
    """One ``PaperBot`` from a stored bot record, or None when it names no
    symbol. ``config`` gives the ids and the gate fields, ``stats`` the
    figures, ``scrumming_state`` the grown target, the quote rate and the
    lots, ``extractor_state`` the pool figures, ``state_when_saved`` the
    state, and ``phantoms_enabled`` and ``phantom_timeframes`` the phantom
    set, read as the restore path reads them."""
    config = record.get("config")
    if not isinstance(config, dict):
        return None
    symbol = str(config.get("symbol") or "")
    if not symbol:
        return None
    stats = record.get("stats")
    stats = stats if isinstance(stats, dict) else {}
    saved = record.get("scrumming_state")
    saved = saved if isinstance(saved, dict) else {}
    raw_target = config.get("target_balance")
    target_read = None if raw_target is None else as_finite_float(raw_target)
    config_target = (
        None
        if raw_target is None
        else (REFUSED_FIGURE if target_read is None else target_read)
    )
    pool = _extractor_figures(config, record)
    phantom_tfs = tuple(str(one) for one in (record.get("phantom_timeframes") or []))
    interval_pct = as_finite_float(config.get("scrumming_interval_pct"))
    read_rate_min = as_finite_float(config.get("scrum_read_rate_min"))
    fee_pct = as_finite_float(config.get("trading_fee_pct"))
    tolerance_pct = as_finite_float(config.get("bb_tolerance_pct"))
    landing_candles = as_finite_float(config.get("bb_landing_strip_candles"))
    detect_pct = as_finite_float(config.get("scrum_detect_pct"))
    price = as_finite_float(stats.get("current_price"))
    position_value = as_finite_float(stats.get("position_value"))
    quote_rate = as_finite_float(saved.get("quote_to_usd"))
    grown_target = as_finite_float(saved.get("target_balance"))
    trades = as_finite_float(stats.get("total_trades"))
    buys = as_finite_float(stats.get("active_buy_orders"))
    sells = as_finite_float(stats.get("active_sell_orders"))
    scrummed = as_finite_float(stats.get("total_scrummed_usd"))
    folded = as_finite_float(stats.get("total_folded_usd"))
    realised = as_finite_float(stats.get("realised_pnl"))
    unrealised = as_finite_float(stats.get("unrealised_pnl"))
    errors = as_finite_float(stats.get("total_errors"))
    uptime = as_finite_float(stats.get("uptime_seconds"))
    venue_realised = as_finite_float(stats.get("realized_pnl_exchange"))
    venue_entry = as_finite_float(stats.get("avg_entry_exchange"))
    venue_basis = as_finite_float(stats.get("cost_basis_total_exchange"))
    venue_fees = as_finite_float(stats.get("fees_paid_exchange"))
    venue_trades = as_finite_float(stats.get("exchange_trade_count"))
    venue_fresh_ts = as_finite_float(stats.get("exchange_data_fresh_ts"))
    ceiling_multiple = as_finite_float(config.get("position_ceiling_multiple"))
    growth_cap_pct = as_finite_float(config.get("max_target_growth_pct"))
    cash = as_finite_float(stats.get("cash_balance_usd"))
    ytd_scrummed = as_finite_float(stats.get("ytd_scrummed_usd"))
    ytd_folded = as_finite_float(stats.get("ytd_folded_usd"))
    return PaperBot(
        bot_id=str(bot_id),
        symbol=symbol,
        exchange_id=str(config.get("exchange_id") or ""),
        base_currency=str(config.get("base_currency") or ""),
        origin=origin,
        target_usd=config_target,
        ta_timeframe=str(config.get("ta_timeframe") or ""),
        scrumming_interval_pct=(
            REFUSED_FIGURE if interval_pct is None else interval_pct
        ),
        scrum_read_rate_min=int(
            SCRUM_READ_RATE_MIN_DEFAULT if read_rate_min is None else read_rate_min
        ),
        trading_fee_pct=REFUSED_FIGURE if fee_pct is None else fee_pct,
        bb_midline_gate=bool(config.get("bb_midline_gate", True)),
        bb_tolerance_pct=1.0 if tolerance_pct is None else tolerance_pct,
        bb_landing_strip_candles=int(2 if landing_candles is None else landing_candles),
        scrum_detect_pct=75.0 if detect_pct is None else detect_pct,
        scrum_require_ta_bullish=bool(config.get("scrum_require_ta_bullish", True)),
        scrum_hold_in_uptrend=bool(config.get("scrum_hold_in_uptrend", True)),
        scrum_defer_to_htf=bool(config.get("scrum_defer_to_htf", True)),
        fold_require_ta_bearish=bool(config.get("fold_require_ta_bearish", True)),
        fold_defer_to_htf=bool(config.get("fold_defer_to_htf", True)),
        mode=str(config.get("mode") or SCRUMMING_MODE),
        state=str(record.get("state_when_saved") or ""),
        current_price=REFUSED_FIGURE if price is None else price,
        holdings=_lots_units(saved.get("main_lots")),
        position_value_usd=(
            REFUSED_FIGURE if position_value is None else position_value
        ),
        quote_to_usd=(1.0 if quote_rate is None else quote_rate) or 1.0,
        live_target_usd=(
            (config_target or REFUSED_FIGURE) if grown_target is None else grown_target
        ),
        total_trades=int(REFUSED_FIGURE if trades is None else trades),
        active_buys=int(REFUSED_FIGURE if buys is None else buys),
        active_sells=int(REFUSED_FIGURE if sells is None else sells),
        total_scrummed_usd=REFUSED_FIGURE if scrummed is None else scrummed,
        total_folded_usd=REFUSED_FIGURE if folded is None else folded,
        realised_pnl_usd=REFUSED_FIGURE if realised is None else realised,
        unrealised_pnl_usd=REFUSED_FIGURE if unrealised is None else unrealised,
        total_errors=int(REFUSED_FIGURE if errors is None else errors),
        last_error=str(stats.get("last_error") or ""),
        uptime_s=REFUSED_FIGURE if uptime is None else uptime,
        realized_pnl_exchange_usd=(
            REFUSED_FIGURE if venue_realised is None else venue_realised
        ),
        avg_entry_exchange=REFUSED_FIGURE if venue_entry is None else venue_entry,
        cost_basis_exchange_usd=(
            REFUSED_FIGURE if venue_basis is None else venue_basis
        ),
        fees_paid_exchange_usd=REFUSED_FIGURE if venue_fees is None else venue_fees,
        exchange_trade_count=int(
            REFUSED_FIGURE if venue_trades is None else venue_trades
        ),
        exchange_data_fresh_ts=(
            REFUSED_FIGURE if venue_fresh_ts is None else venue_fresh_ts
        ),
        scrum_target_mode=(
            str(saved["scrum_target_mode"])
            if saved.get("scrum_target_mode") is not None
            else None
        ),
        position_ceiling_enabled=bool(config.get("position_ceiling_enabled", False)),
        position_ceiling_multiple=(
            5.0 if ceiling_multiple is None else ceiling_multiple
        ),
        max_target_growth_pct=1.0 if growth_cap_pct is None else growth_cap_pct,
        detonation_enabled=bool(config.get("detonation_enabled", False)),
        detonation_timeframe=str(config.get("detonation_timeframe") or "1d"),
        chunk_size_usd=pool["chunk_size_usd"],
        chunk_size_base=pool["chunk_size_base"],
        chunk_free_base=pool["chunk_free_base"],
        n_positions_open=pool["n_positions_open"],
        n_positions_drawdown=pool["n_positions_drawdown"],
        phantoms_enabled=bool(record.get("phantoms_enabled", PHANTOMS_ENABLED_DEFAULT)),
        phantom_timeframes=phantom_tfs,
        cash_balance_usd=REFUSED_FIGURE if cash is None else cash,
        ytd_scrummed_usd=REFUSED_FIGURE if ytd_scrummed is None else ytd_scrummed,
        ytd_folded_usd=REFUSED_FIGURE if ytd_folded is None else ytd_folded,
        profit_folding_active=bool(config.get("profit_folding_active", True)),
    )


def _held_bot(bot_id: str, record: dict) -> Optional[PaperBot]:
    """One ``PaperBot`` from a held record, its ``origin`` the record's own
    ``origin`` key, ``NEW_ORIGIN`` when the record carries none."""
    return paper_bot_from_record(
        bot_id, record, origin=str(record.get("origin") or NEW_ORIGIN)
    )


def wizard_record(config: dict) -> dict:
    """The stored-record shape ``get_full_state`` writes, built from the bot
    wizard's ``get_bot_config`` dict through ``bot_config_kwargs`` and
    ``make_bot_config``, with ``state_when_saved`` idle, no stats,
    ``phantoms_enabled`` from the wizard's ``enable_phantoms`` and
    ``phantom_timeframes`` from ``wizard_phantom_timeframes``.
    ``make_bot_config`` raises ``ValueError`` on a mode-foreign key or a bad
    shape and ``TypeError`` on a value a ``BotConfig`` field cannot hold."""
    collected = dict(config or {})
    mode = (
        BotMode.EXTRACTOR
        if collected.get("mode") == EXTRACTOR_MODE
        else BotMode.SCRUMMING
    )
    kwargs = bot_config_kwargs(
        mode, collected, exchange_id=str(collected.get("exchange_id") or "")
    )
    built = make_bot_config(mode, **kwargs)
    stored = asdict(built)
    stored["mode"] = built.mode.value
    scrumming = mode == BotMode.SCRUMMING
    record = {
        "config": stored,
        "stats": {},
        "scrumming_state": {},
        "state_when_saved": BotState.IDLE.value,
        "phantoms_enabled": scrumming and bool(collected.get("enable_phantoms", False)),
    }
    timeframes = (
        wizard_phantom_timeframes(
            collected.get("phantom_timeframes"), built.ta_timeframe, built.exchange_id
        )
        if scrumming
        else []
    )
    if timeframes:
        record["phantom_timeframes"] = timeframes
    return record


def wizard_phantom_timeframes(
    typed: Any, ta_timeframe: str, exchange_id: str
) -> list[str]:
    """The phantom timeframes ``ScrummingBot.__init__`` gives a new bot:
    ``typed`` as the wizard handed it, or ``default_phantom_timeframes`` over
    ``ta_timeframe`` when ``typed`` is empty, kept to what
    ``available_timeframes`` lists for ``exchange_id``."""
    from ..exchange.timeframes import available_timeframes
    from ..trading.phantom_balance import default_phantom_timeframes

    offered = list(available_timeframes(exchange_id))
    chosen = [str(one) for one in (typed or []) if str(one)]
    if not chosen:
        chosen = default_phantom_timeframes(str(ta_timeframe or ""), offered)
    return [one for one in chosen if one in offered]


def _extractor_status(bot: PaperBot) -> dict:
    """The keys ``ExtractorBot.get_status`` adds over the base status, which
    the Extractor Bots table reads: the base currency, the three pool figures,
    the two position counts and ``extractor_pool_color`` over them."""
    return {
        "base_currency": bot.base_currency,
        "chunk_size_usd": bot.chunk_size_usd,
        "chunk_size_base": bot.chunk_size_base,
        "chunk_free_base": bot.chunk_free_base,
        "n_positions_open": bot.n_positions_open,
        "n_positions_drawdown": bot.n_positions_drawdown,
        "pool_color": extractor_pool_color(
            bot.n_positions_open, bot.n_positions_drawdown
        ),
    }


def row_status(bot: PaperBot) -> dict:
    """``bot`` as the status dict a live bot's ``get_status`` answers, in the
    keys the Scrumming Bots table, the Extractor Bots table and the Status tab
    read, an extractor's carrying ``_extractor_status`` over the base keys.
    ``armed_action``, ``position_ceiling_usd``, ``ceiling_ratio`` and
    ``fold_rate_taper`` are runtime values a stored record does not hold and
    read as they do on a live bot before its first tick."""
    status = {
        "bot_id": bot.bot_id,
        "state": bot.state,
        "exchange": bot.exchange_id,
        "symbol": bot.symbol,
        "mode": bot.mode,
        "scrum_target_mode": bot.scrum_target_mode,
        "armed_action": None,
        "position_ceiling_enabled": bot.position_ceiling_enabled,
        "position_ceiling_multiple": bot.position_ceiling_multiple,
        "position_ceiling_usd": None,
        "ceiling_ratio": None,
        "fold_rate_taper": 1.0,
        "detonation_enabled": bot.detonation_enabled,
        "detonation_timeframe": bot.detonation_timeframe,
        "target_balance": bot.target_usd or 0.0,
        "live_target_balance": bot.live_target_usd,
        "ta_timeframe": bot.ta_timeframe or "1h",
        "current_holdings": bot.holdings,
        "quote_to_usd": bot.quote_to_usd,
        "stats": {
            "total_trades": bot.total_trades,
            "realised_pnl": bot.realised_pnl_usd,
            "unrealised_pnl": bot.unrealised_pnl_usd,
            "active_buys": bot.active_buys,
            "active_sells": bot.active_sells,
            "current_price": bot.current_price,
            "position_value": bot.position_value_usd,
            "uptime": bot.uptime_s,
            "last_error": bot.last_error,
            "total_scrummed_usd": bot.total_scrummed_usd,
            "total_folded_usd": bot.total_folded_usd,
            "total_errors": bot.total_errors,
            "realized_pnl_exchange": bot.realized_pnl_exchange_usd,
            "avg_entry_exchange": bot.avg_entry_exchange,
            "cost_basis_total_exchange": bot.cost_basis_exchange_usd,
            "fees_paid_exchange": bot.fees_paid_exchange_usd,
            "exchange_trade_count": bot.exchange_trade_count,
            "exchange_data_fresh_ts": bot.exchange_data_fresh_ts,
        },
        "auto_fire": dict(PRE_TICK_AUTO_FIRE),
    }
    if bot.mode == EXTRACTOR_MODE:
        status.update(_extractor_status(bot))
    return status


def aggregate_stats(bots: Sequence[PaperBot]) -> dict:
    """The header strip's figures over ``bots``, keyed as
    ``FleetAggregationMixin.get_aggregate_stats`` keys the live fleet's and
    summed by its arithmetic: the wallet is the largest ``cash_balance_usd``,
    a position is ``priced_usd`` of ``holdings``, ``current_price`` and
    ``quote_to_usd`` when both are positive and ``position_value_usd``
    otherwise, maturity is read only where ``exchange_data_fresh_ts`` is
    positive, and each YTD sum falls back to the lifetime sum at zero."""
    total_pnl = 0.0
    total_trades = 0
    running = 0
    errored = 0
    total_scrummed = 0.0
    total_folded = 0.0
    total_scrummed_ytd = 0.0
    total_folded_ytd = 0.0
    total_errors_lifetime = 0
    total_realized_exchange = 0.0
    total_unrealized_exchange = 0.0
    total_fees_exchange = 0.0
    bots_with_fresh_exchange_data = 0
    wallet_cash_usd = 0.0
    crypto_position_value_usd = 0.0
    total_mature_exchange = 0.0
    mature_positions = 0

    for bot in bots:
        total_pnl += bot.realised_pnl_usd
        total_trades += bot.total_trades
        total_scrummed += bot.total_scrummed_usd
        total_folded += bot.total_folded_usd
        total_scrummed_ytd += bot.ytd_scrummed_usd
        total_folded_ytd += bot.ytd_folded_usd
        total_errors_lifetime += bot.total_errors
        total_realized_exchange += bot.realized_pnl_exchange_usd
        total_unrealized_exchange += bot.unrealised_pnl_usd
        total_fees_exchange += bot.fees_paid_exchange_usd
        fresh = bot.exchange_data_fresh_ts > 0
        if fresh:
            bots_with_fresh_exchange_data += 1
        if bot.cash_balance_usd > wallet_cash_usd:
            wallet_cash_usd = bot.cash_balance_usd
        position_value = bot.position_value_usd
        if bot.holdings > 0 and bot.current_price > 0:
            position_value = priced_usd(
                bot.holdings, bot.current_price, bot.quote_to_usd
            )
        crypto_position_value_usd += position_value
        if fresh:
            mature = mature_profit_usd(bot.cost_basis_exchange_usd, position_value)
            if mature > 0:
                total_mature_exchange += mature
                mature_positions += 1
        if bot.state == BotState.RUNNING.value:
            running += 1
        if bot.state == BotState.ERROR.value:
            errored += 1

    return {
        "total_bots": len(bots),
        "running": running,
        "errored": errored,
        "total_errors_lifetime": total_errors_lifetime,
        "total_realized_exchange": round(total_realized_exchange, 4),
        "total_unrealized_exchange": round(total_unrealized_exchange, 4),
        "total_fees_exchange": round(total_fees_exchange, 4),
        "total_mature_exchange": round(total_mature_exchange, 4),
        "mature_positions": mature_positions,
        "bots_with_fresh_exchange_data": bots_with_fresh_exchange_data,
        "wallet_cash_usd": round(wallet_cash_usd, 4),
        "crypto_position_value_usd": round(crypto_position_value_usd, 4),
        "total_account_value_usd": round(
            wallet_cash_usd + crypto_position_value_usd, 4
        ),
        "total_realised_pnl": round(total_pnl, 4),
        "total_trades": total_trades,
        "total_scrummed_usd": round(
            total_scrummed_ytd if total_scrummed_ytd > 0 else total_scrummed, 4
        ),
        "total_folded_usd": round(
            total_folded_ytd if total_folded_ytd > 0 else total_folded, 4
        ),
        "total_scrummed_usd_ytd": round(total_scrummed_ytd, 4),
        "total_folded_usd_ytd": round(total_folded_ytd, 4),
        "total_scrummed_usd_lifetime": round(total_scrummed, 4),
        "total_folded_usd_lifetime": round(total_folded, 4),
    }


def strip_aggregate(bots: Sequence[PaperBot], figures: Optional[dict] = None) -> dict:
    """``aggregate_stats`` over ``bots`` with the paper ledger's four money
    figures laid over it: ``figures`` is ``PaperLedger.figures``, its keys
    mapped by ``LEDGER_TO_AGGREGATE``, ``bots_open`` standing for the bots the
    venue has answered and ``mature_positions`` its own count. With no
    ``figures`` the four money keys read zero and the strip draws an em dash
    for each, the ledger before a run."""
    out = aggregate_stats(bots)
    held = dict(figures or {})
    for ledger_key, aggregate_key in LEDGER_TO_AGGREGATE:
        read = as_finite_float(held.get(ledger_key))
        out[aggregate_key] = round(REFUSED_FIGURE if read is None else read, 4)
    out["total_account_value_usd"] = round(
        out["wallet_cash_usd"] + out["crypto_position_value_usd"], 4
    )
    open_read = as_finite_float(held.get("bots_open"))
    mature_read = as_finite_float(held.get("mature_positions"))
    out["bots_with_fresh_exchange_data"] = int(
        REFUSED_FIGURE if open_read is None else open_read
    )
    out["mature_positions"] = int(
        REFUSED_FIGURE if mature_read is None else mature_read
    )
    return out


#: The header strip's figures for a fleet holding no bot, ``aggregate_stats``
#: over none.
EMPTY_AGGREGATE = aggregate_stats(())


def loaded_idle(record: dict) -> dict:
    """``record`` with its ``state_when_saved`` written ``BotState.IDLE``, as
    ``restore_bots_from_state`` recreates every persisted bot in IDLE until
    the operator starts it; a loaded bot never reads ``running`` with no run."""
    record["state_when_saved"] = BotState.IDLE.value
    return record


def _records_of(stored: dict, path: Path) -> dict[str, dict]:
    """The records of one ``bots`` map ``stored``, by ``bot_id``, each read as
    ``loaded_idle``, a record that names no symbol kept and named in one
    warning line with ``path``."""
    records = {
        str(bot_id): loaded_idle(record)
        for bot_id, record in stored.items()
        if bot_id and isinstance(record, dict)
    }
    unread = [
        bot_id
        for bot_id, record in records.items()
        if _held_bot(bot_id, record) is None
    ]
    if unread:
        logger.warning(
            "paper fleet file %s: %d record(s) name no symbol and are not drawn: %s",
            path,
            len(unread),
            ", ".join(unread),
        )
    return records


def _read_paper_records(path: Path) -> dict[str, dict]:
    """The ``bots`` map of the paper fleet file at ``path``, each record read
    through ``_records_of``. An absent, empty or malformed file answers an
    empty map, the malformed one named in one warning line with ``path``."""
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("paper fleet file %s unreadable: %s", path, exc)
        return {}
    if not text.strip():
        return {}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("paper fleet file %s malformed: %s", path, exc)
        return {}
    stored = loaded.get("bots") if isinstance(loaded, dict) else None
    if not isinstance(stored, dict):
        logger.warning("paper fleet file %s malformed: no bots object", path)
        return {}
    return _records_of(stored, path)


class PaperFleetSource:
    """The records the paper fleet file holds as ``PaperBot`` records, and the
    read of ``bot_state.json`` that ``import_live_fleet`` copies them from."""

    def __init__(
        self, root: Optional[Path] = None, paper_dir: Optional[Path] = None
    ) -> None:
        """Read the paper fleet file from ``paper_dir``, or from
        ``get_paper_root`` when it is None. ``bot_state.json`` under ``root``,
        or under ``~/.acervator`` when it is None, is read on
        ``stored_records`` alone."""
        self._root = Path(root) if root is not None else Path.home() / STATE_DIR_NAME
        self._paper_dir = Path(paper_dir) if paper_dir is not None else get_paper_root()
        self._records: dict[str, dict] = _read_paper_records(self.paper_path())

    def root(self) -> Path:
        """The directory holding the ``bot_state.json`` this source reads."""
        return self._root

    def path(self) -> Path:
        """The ``bot_state.json`` file itself."""
        return self._root / BOT_STATE_NAME

    def paper_dir(self) -> Path:
        """The directory holding the paper fleet file, ``get_paper_root`` by default."""
        return self._paper_dir

    def paper_path(self) -> Path:
        """The paper fleet file, ``PAPER_FLEET_NAME`` under ``paper_dir``."""
        return self._paper_dir / PAPER_FLEET_NAME

    def _state(self) -> dict:
        path = self.path()
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("paper fleet: %s unreadable: %s", path.name, exc)
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def saved_at(self) -> str:
        """The ``saved_at_human`` stamp the live process last wrote."""
        return str(self._state().get("saved_at_human") or "")

    def bots(self) -> list[PaperBot]:
        """Every held record as a ``PaperBot``, by exchange_id then symbol then
        bot_id; a record read from ``bot_state.json`` is not held until
        ``import_live_fleet`` copies it."""
        out: list[PaperBot] = []
        for bot_id, record in self._records.items():
            bot = _held_bot(bot_id, record)
            if bot is not None:
                out.append(bot)
        return sorted(out, key=lambda one: (one.exchange_id, one.symbol, one.bot_id))

    def stored_records(self) -> dict[str, dict]:
        """The ``bots`` map of ``bot_state.json`` as it lies on disk, by
        ``bot_id``, each a copy; the one read of that file with a caller."""
        stored = self._state().get("bots")
        if not isinstance(stored, dict):
            return {}
        return {
            str(bot_id): copy.deepcopy(record)
            for bot_id, record in stored.items()
            if bot_id and isinstance(record, dict)
        }

    def stored_exchanges(self) -> list[str]:
        """Every distinct ``exchange_id`` the bots in ``bot_state.json`` name,
        sorted; the options ``exchange_choice`` takes for Import Live Fleet."""
        return sorted({bot.exchange_id for bot in live_fleet(self) if bot.exchange_id})

    def import_live_fleet(self, exchange_id: str) -> list[PaperBot]:
        """Copy every stored bot on ``exchange_id`` from ``bot_state.json`` into
        the held records under its own ``bot_id`` with ``origin`` ``LIVE_ORIGIN``
        and its state ``loaded_idle`` whatever the live file saved, replacing a
        held record of the same id and keeping every other. Answers the
        ``PaperBot`` of each record copied, by symbol then bot_id, none for an
        empty ``exchange_id``, and the paper fleet file takes them on the next
        ``save``."""
        wanted = str(exchange_id or "")
        if not wanted:
            return []
        imported: list[PaperBot] = []
        for bot_id, record in self.stored_records().items():
            bot = paper_bot_from_record(bot_id, record, origin=LIVE_ORIGIN)
            if bot is None or bot.exchange_id != wanted:
                continue
            record["bot_id"] = bot_id
            record["origin"] = LIVE_ORIGIN
            self._records[bot_id] = loaded_idle(record)
            imported.append(_held_bot(bot_id, record) or bot)
        return sorted(imported, key=lambda one: (one.symbol, one.bot_id))

    def create(self, config: dict) -> PaperBot:
        """Hold one record built from the bot wizard's config through
        ``wizard_record`` and answer its ``PaperBot``, its ``bot_id`` the first
        ``BOT_ID_LENGTH`` characters of a ``uuid4`` as a live bot draws its own.
        """
        record = wizard_record(config)
        bot_id = str(uuid.uuid4())[:BOT_ID_LENGTH]
        record["bot_id"] = bot_id
        record["origin"] = NEW_ORIGIN
        bot = _held_bot(bot_id, record)
        if bot is None:
            raise ValueError("the wizard config names no symbol")
        self._records[bot_id] = record
        return bot

    def paper_bot_for(self, bot_id: str) -> Optional[PaperBot]:
        """The ``PaperBot`` of the held record under ``bot_id``, or None; a
        record in ``bot_state.json`` that ``import_live_fleet`` has not copied
        is not held and answers None."""
        record = self._records.get(str(bot_id))
        if not isinstance(record, dict):
            return None
        return _held_bot(str(bot_id), record)

    def set_state(self, bot_id: str, state: str, clear_error: bool = False) -> str:
        """Write ``state`` into the held record's ``state_when_saved`` and answer
        it, ``clear_error`` emptying ``stats.last_error`` and zeroing
        ``stats.consecutive_errors`` as ``BotContainer.start`` does before it
        moves the state. Raises ``KeyError`` when no record is held under
        ``bot_id``."""
        wanted = str(bot_id)
        record = self._records.get(wanted)
        if not isinstance(record, dict):
            raise KeyError(f"no paper record is held under {wanted!r}")
        record["state_when_saved"] = str(state)
        if clear_error:
            stats = record.get("stats")
            if not isinstance(stats, dict):
                stats = {}
                record["stats"] = stats
            stats["last_error"] = ""
            stats["consecutive_errors"] = 0
        return str(state)

    def set_config_field(self, bot_id: str, field: str, value: Any) -> Any:
        """Write ``field`` into the held record under ``bot_id`` and answer the
        value stored, a ``BotConfig`` name landing in the record's ``config``
        and a ``RECORD_FIELDS`` name at the record's top level."""
        wanted = str(bot_id)
        record = self._records.get(wanted)
        if not isinstance(record, dict):
            raise KeyError(f"no paper record is held under {wanted!r}")
        name = str(field)
        if name in RECORD_FIELDS:
            record[RECORD_FIELDS[name]] = value
            return value
        if name not in CONFIG_FIELD_NAMES:
            raise SendRefused(
                f"BotConfig declares no {name!r}, so no paper record holds it."
            )
        config = record.get("config")
        if not isinstance(config, dict):
            config = {}
            record["config"] = config
        config[name] = value
        return value

    def write_stats(
        self,
        bot_id: str,
        stats: Optional[dict] = None,
        scrumming_state: Optional[dict] = None,
        state: str = "",
    ) -> dict:
        """Write a run's figures into the held record under ``bot_id``, ``stats``
        merged into the record's ``stats``, ``scrumming_state`` into its
        ``scrumming_state`` and ``state`` into ``state_when_saved`` when given,
        and answer the keys written per part. Raises ``KeyError`` when no
        record is held under ``bot_id``."""
        wanted = str(bot_id)
        record = self._records.get(wanted)
        if not isinstance(record, dict):
            raise KeyError(f"no paper record is held under {wanted!r}")
        written: dict[str, list[str]] = {
            "stats": [],
            "scrumming_state": [],
            "state": [],
        }
        for part, fields in (("stats", stats), ("scrumming_state", scrumming_state)):
            if not fields:
                continue
            held = record.get(part)
            if not isinstance(held, dict):
                held = {}
                record[part] = held
            for key, value in fields.items():
                held[str(key)] = value
                written[part].append(str(key))
        if state:
            record["state_when_saved"] = str(state)
            written["state"].append(str(state))
        return written

    def remove(self, bot_id: str) -> bool:
        """Drop the held record under ``bot_id`` and answer whether one was
        held; the paper fleet file loses it on the next ``save``."""
        return self._records.pop(str(bot_id), None) is not None

    def clear(self) -> int:
        """Drop every held record on every exchange and answer how many were
        held; the paper fleet file loses them on the next ``save``."""
        count = len(self._records)
        self._records = {}
        return count

    def save(self) -> Optional[Path]:
        """Write the held records to ``paper_path`` through
        ``atomic_write_json`` under the keys ``StateManager.save_state``
        writes, ``saved_at``, ``saved_at_human``, ``bot_count`` and ``bots``,
        and answer the path, or None when the write fails."""
        payload = {
            "saved_at": time.time(),
            "saved_at_human": datetime.now().strftime(SAVED_AT_HUMAN_FORMAT),
            "bot_count": len(self._records),
            "bots": dict(self._records),
        }
        path = self.paper_path()
        try:
            atomic_write_json(path, payload, indent=2, default=str)
        except (OSError, TypeError, ValueError) as exc:
            logger.error("paper fleet save failed: %s: %s", path, exc)
            return None
        logger.info("paper fleet saved to %s: %d bot(s)", path, len(self._records))
        return path

    def bot_for(self, bot_id: str) -> Optional[PaperBot]:
        """The ``PaperBot`` whose ``bot_id`` is ``bot_id``, or None."""
        for bot in self.bots():
            if bot.bot_id == str(bot_id):
                return bot
        return None

    def record_for(self, bot_id: str) -> Optional[dict]:
        """A copy of the held record whose ``bot_id`` is ``bot_id``, or None."""
        held = self._records.get(str(bot_id))
        if isinstance(held, dict):
            return copy.deepcopy(held)
        return None

    def exchanges(self) -> list[str]:
        """Every distinct ``exchange_id`` the held bots name, sorted; empty
        until Import Live Fleet has loaded a fleet."""
        return sorted({bot.exchange_id for bot in self.bots() if bot.exchange_id})

    def symbols(self, exchange_id: Optional[str] = None) -> list[str]:
        """The symbols the held bots trade, narrowed to ``exchange_id`` when
        given."""
        return sorted(
            {
                bot.symbol
                for bot in self.bots()
                if exchange_id is None or bot.exchange_id == exchange_id
            }
        )

    def statuses(self, exchange_id: str = "") -> list[dict]:
        """One ``row_status`` per held bot, narrowed to ``exchange_id`` when
        given; the list a venue page's ``update_bots`` takes."""
        return [
            row_status(bot)
            for bot in self.bots()
            if not exchange_id or bot.exchange_id == exchange_id
        ]

    def aggregate(self) -> dict:
        """The header strip's figures over every held record,
        ``aggregate_stats`` of ``bots``."""
        return aggregate_stats(self.bots())

    def __getattr__(self, name: str):
        """Refuse every name outside ``READ_NAMES``."""
        raise SendRefused(
            f"PaperFleetSource answers {READ_NAMES} and cannot {name!r}. "
            "The Paper Trader receives and asks; it sends nothing."
        )


def exchange_choice(exchanges: list[str], chosen: str = "") -> dict:
    """Whether the operator must pick an exchange, and which one is in force;
    ``prompt`` is True while more than one exchange is active and ``chosen``
    names none of them."""
    options = [str(one) for one in exchanges]
    picked = str(chosen or "")
    if picked not in options:
        picked = options[0] if len(options) == 1 else ""
    return {
        "options": options,
        "chosen": picked,
        "prompt": len(options) > 1 and not picked,
        "count": len(options),
    }


def live_fleet(source: PaperFleetSource, exchange_id: str = "") -> list[PaperBot]:
    """One ``PaperBot`` per stored bot in ``source.stored_records()``, with
    ``LIVE_ORIGIN``, narrowed to ``exchange_id`` when given, by exchange_id
    then symbol then bot_id."""
    out: list[PaperBot] = []
    for bot_id, record in source.stored_records().items():
        bot = paper_bot_from_record(bot_id, record, origin=LIVE_ORIGIN)
        if bot is None or (exchange_id and bot.exchange_id != exchange_id):
            continue
        out.append(bot)
    return sorted(out, key=lambda one: (one.exchange_id, one.symbol, one.bot_id))


#: The name the former surface imported; ``live_fleet`` under it.
paper_fleet = live_fleet


__all__ = [
    "BOT_ID_LENGTH",
    "BOT_STATE_NAME",
    "CONFIG_FIELD_NAMES",
    "EMPTY_AGGREGATE",
    "EXTRACTOR_DRAWDOWN_STATE",
    "EXTRACTOR_MODE",
    "LEDGER_TO_AGGREGATE",
    "LIVE_ORIGIN",
    "NEW_ORIGIN",
    "PHANTOMS_ENABLED_DEFAULT",
    "POOL_GREEN",
    "POOL_RED",
    "POOL_YELLOW",
    "PRE_TICK_AUTO_FIRE",
    "READ_NAMES",
    "RECORD_FIELDS",
    "SAVED_AT_HUMAN_FORMAT",
    "SCRUMMING_MODE",
    "SCRUM_READ_RATE_MIN_DEFAULT",
    "STATE_DIR_NAME",
    "PaperBot",
    "PaperFleetSource",
    "SendRefused",
    "aggregate_stats",
    "exchange_choice",
    "extractor_pool_color",
    "live_fleet",
    "loaded_idle",
    "paper_bot_from_record",
    "paper_fleet",
    "row_status",
    "strip_aggregate",
    "wizard_phantom_timeframes",
    "wizard_record",
]
