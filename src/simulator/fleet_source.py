"""The Simulator's fleet path: the records the sim fleet file holds under
``get_sim_dir``, the bots the wizard creates, the bots Import Live Fleet
copies out of the live bot_state record and the bots Generate From YTD builds
from the YTD trade files, both read only.

``FleetSource`` answers ``root``, ``path``, ``saved_at``, ``bots``, ``bot_for``,
``record_for``, ``exchanges``, ``symbols``, ``statuses``, ``aggregate``,
``create``, ``sim_bot_for``, ``set_state``, ``remove``, ``clear``,
``stored_records``, ``stored_exchanges``, ``import_live_fleet``, ``generate_from_ytd``,
``hold_battery_fleet``, ``sim_dir``, ``sim_path`` and ``save``; it holds no venue, writes ``sim_path``
alone and sends nothing, and ``__getattr__`` raises ``SendRefused`` for every
other name. ``bots``, ``exchanges``, ``statuses`` and ``aggregate`` read the
held records alone, so the tab starts empty; ``stored_records`` and
``stored_exchanges`` read ``bot_state.json``, ``import_live_fleet`` copies its
records on one exchange into the held map under their own ids with
``LIVE_ORIGIN``, ``generate_from_ytd`` holds one ``ytd_record`` per traded
pair a ``YtdTradeSource`` names on one exchange under the pair's own id with
``YTD_ORIGIN`` and the Target Balance ``ytd_target_usd`` reads off its fills,
and ``sim_bot_for``, ``set_state`` and ``remove`` read and move the held
records, which is what ``SimBotManager`` acts on; ``clear`` drops every held
record at once, which is what Clear Fleet asks. ``SimBot`` is a read-only
record forked from the live bot's config, its stats and its saved state, never
a ``ScrummingBot``; ``row_status`` answers one as the status dict the Scrumming
Bots table and the Extractor Bots table read; ``aggregate_stats`` answers the
header strip's figures over a list of them with ``get_aggregate_stats``'s
arithmetic; ``live_fleet`` builds one per stored bot, ``ytd_fleet`` one per YTD
trade file, and ``wizard_record`` the stored-record shape from the bot
wizard's config, its phantom keys from ``wizard_phantom_timeframes``.
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from ..core.io_utils import atomic_write_json
from ..core.log_paths import get_sim_dir
from ..exchange.ytd_trade_store import SIDE_BUY, SIDE_SELL, YtdFileEntry, YtdTrade
from ..trading.container.config import (
    BotMode,
    BotState,
    bot_config_kwargs,
    make_bot_config,
)
from ..trading.scrumming.sizing import DRAWDOWN_STATE, priced_usd
from ..trading.smart_wire import mature_profit_usd
from .tablet_source import SendRefused

logger = logging.getLogger("acervator.simulator.fleet")

BOT_STATE_NAME = "bot_state.json"

#: The sim fleet file under ``get_sim_dir``, in ``bot_state.json``'s shape.
SIM_FLEET_NAME = "sim_fleet.json"

#: The ``saved_at_human`` format ``StateManager.save_state`` writes.
SAVED_AT_HUMAN_FORMAT = "%Y-%m-%d %H:%M:%S"

#: Every name ``FleetSource`` answers. ``__getattr__`` refuses the rest.
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
    "sim_bot_for",
    "set_state",
    "remove",
    "clear",
    "stored_records",
    "stored_exchanges",
    "import_live_fleet",
    "generate_from_ytd",
    "hold_battery_fleet",
    "sim_dir",
    "sim_path",
    "save",
)

LIVE_ORIGIN = "live"
YTD_ORIGIN = "ytd"
NEW_ORIGIN = "new"
BATTERY_ORIGIN = "battery"

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
#: tick; a stored record holds no gate state, so every sim row reads this.
PRE_TICK_AUTO_FIRE = {
    "scrum_armed": False,
    "fold_armed": False,
    "scrum_blockers": ["pre-tick"],
    "fold_blockers": ["pre-tick"],
    "evaluated_at_tick": 0,
}

#: ``phantoms_enabled`` for a record without the key, as the restore reads it.
PHANTOMS_ENABLED_DEFAULT = True


@dataclass(frozen=True)
class SimBot:
    """One simulated bot: its ids, its symbol, the config the gates read, and
    the figures the Scrumming Bots table, the Extractor Bots table and the
    Status tab draw.

    ``chunk_size_usd``, ``chunk_size_base``, ``chunk_free_base``,
    ``n_positions_open`` and ``n_positions_drawdown`` are the Extractor's pool
    figures and stay zero on a scrumming bot.
    """

    bot_id: str
    symbol: str
    exchange_id: str
    base_currency: str
    origin: str
    target_usd: Optional[float] = None
    ta_timeframe: str = ""
    scrumming_interval_pct: float = 0.0
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

    @property
    def asset(self) -> str:
        """The base of ``symbol``, the name a Stone Tablet is filed under."""
        return self.symbol.split("/")[0] if self.symbol else ""


def _number(value: Any, fallback: float) -> float:
    """``value`` as a float, or ``fallback`` when it is not one."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _lots_units(lots: Any) -> float:
    """The units held across ``lots``, which is how the live bot sets
    ``_current_holdings`` from ``_main_lots``."""
    if not isinstance(lots, list):
        return 0.0
    return sum(_number(lot.get("units"), 0.0) for lot in lots if isinstance(lot, dict))


def _extractor_figures(config: dict, record: dict) -> dict:
    """The five pool figures of an extractor record, keyed as ``SimBot`` names
    them; every figure is zero when ``config`` is not in extractor mode.

    ``extractor_state`` is what ``ExtractorBot.export_state`` wrote; a record
    holding none reads as ``ExtractorBot.__init__`` sets the chunk before a
    rate arrives, the base size and the free base both equal to the dollar
    size, with no position.
    """
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
    chunk_size_usd = _number(
        state.get("chunk_size_usd"),
        _number(config.get("extractor_chunk_size_usd"), 0.0),
    )
    chunk_size_base = _number(state.get("chunk_size_base"), chunk_size_usd)
    chunk_free_base = _number(state.get("chunk_free_base"), chunk_size_base)
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


def _sim_bot_from_record(
    bot_id: str, record: dict, origin: str = LIVE_ORIGIN
) -> Optional[SimBot]:
    """One ``SimBot`` from a stored bot record, or None when it names no
    symbol.

    ``config`` gives the ids and the gate fields, ``stats`` the figures,
    ``scrumming_state`` the grown target, the quote rate, the phase and the
    lots, ``extractor_state`` the pool figures, ``state_when_saved`` the
    state, and ``phantoms_enabled`` and ``phantom_timeframes`` the phantom
    set, read as the restore path reads them. A ``target_balance`` of None,
    which ``ytd_record`` writes for a pair whose fills give no basis, reads as
    ``target_usd`` None.
    """
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
    config_target = None if raw_target is None else _number(raw_target, 0.0)
    pool = _extractor_figures(config, record)
    phantom_tfs = tuple(str(one) for one in (record.get("phantom_timeframes") or []))
    return SimBot(
        bot_id=str(bot_id),
        symbol=symbol,
        exchange_id=str(config.get("exchange_id") or ""),
        base_currency=str(config.get("base_currency") or ""),
        origin=origin,
        target_usd=config_target,
        ta_timeframe=str(config.get("ta_timeframe") or ""),
        scrumming_interval_pct=_number(config.get("scrumming_interval_pct"), 0.0),
        trading_fee_pct=_number(config.get("trading_fee_pct"), 0.0),
        bb_midline_gate=bool(config.get("bb_midline_gate", True)),
        bb_tolerance_pct=_number(config.get("bb_tolerance_pct"), 1.0),
        bb_landing_strip_candles=int(
            _number(config.get("bb_landing_strip_candles"), 2)
        ),
        scrum_detect_pct=_number(config.get("scrum_detect_pct"), 75.0),
        scrum_require_ta_bullish=bool(config.get("scrum_require_ta_bullish", True)),
        scrum_hold_in_uptrend=bool(config.get("scrum_hold_in_uptrend", True)),
        scrum_defer_to_htf=bool(config.get("scrum_defer_to_htf", True)),
        fold_require_ta_bearish=bool(config.get("fold_require_ta_bearish", True)),
        fold_defer_to_htf=bool(config.get("fold_defer_to_htf", True)),
        mode=str(config.get("mode") or SCRUMMING_MODE),
        state=str(record.get("state_when_saved") or ""),
        current_price=_number(stats.get("current_price"), 0.0),
        holdings=_lots_units(saved.get("main_lots")),
        position_value_usd=_number(stats.get("position_value"), 0.0),
        quote_to_usd=_number(saved.get("quote_to_usd"), 1.0) or 1.0,
        live_target_usd=_number(saved.get("target_balance"), config_target or 0.0),
        total_trades=int(_number(stats.get("total_trades"), 0)),
        active_buys=int(_number(stats.get("active_buy_orders"), 0)),
        active_sells=int(_number(stats.get("active_sell_orders"), 0)),
        total_scrummed_usd=_number(stats.get("total_scrummed_usd"), 0.0),
        total_folded_usd=_number(stats.get("total_folded_usd"), 0.0),
        realised_pnl_usd=_number(stats.get("realised_pnl"), 0.0),
        unrealised_pnl_usd=_number(stats.get("unrealised_pnl"), 0.0),
        total_errors=int(_number(stats.get("total_errors"), 0)),
        last_error=str(stats.get("last_error") or ""),
        uptime_s=_number(stats.get("uptime_seconds"), 0.0),
        realized_pnl_exchange_usd=_number(stats.get("realized_pnl_exchange"), 0.0),
        avg_entry_exchange=_number(stats.get("avg_entry_exchange"), 0.0),
        cost_basis_exchange_usd=_number(stats.get("cost_basis_total_exchange"), 0.0),
        fees_paid_exchange_usd=_number(stats.get("fees_paid_exchange"), 0.0),
        exchange_trade_count=int(_number(stats.get("exchange_trade_count"), 0)),
        exchange_data_fresh_ts=_number(stats.get("exchange_data_fresh_ts"), 0.0),
        scrum_target_mode=(
            str(saved["scrum_target_mode"])
            if saved.get("scrum_target_mode") is not None
            else None
        ),
        position_ceiling_enabled=bool(config.get("position_ceiling_enabled", False)),
        position_ceiling_multiple=_number(config.get("position_ceiling_multiple"), 5.0),
        max_target_growth_pct=_number(config.get("max_target_growth_pct"), 1.0),
        detonation_enabled=bool(config.get("detonation_enabled", False)),
        detonation_timeframe=str(config.get("detonation_timeframe") or "1d"),
        chunk_size_usd=pool["chunk_size_usd"],
        chunk_size_base=pool["chunk_size_base"],
        chunk_free_base=pool["chunk_free_base"],
        n_positions_open=pool["n_positions_open"],
        n_positions_drawdown=pool["n_positions_drawdown"],
        phantoms_enabled=bool(record.get("phantoms_enabled", PHANTOMS_ENABLED_DEFAULT)),
        phantom_timeframes=phantom_tfs,
        cash_balance_usd=_number(stats.get("cash_balance_usd"), 0.0),
        ytd_scrummed_usd=_number(stats.get("ytd_scrummed_usd"), 0.0),
        ytd_folded_usd=_number(stats.get("ytd_folded_usd"), 0.0),
    )


def _held_bot(bot_id: str, record: dict) -> Optional[SimBot]:
    """One ``SimBot`` from a held record, its ``origin`` the record's own
    ``origin`` key, ``NEW_ORIGIN`` when the record carries none."""
    return _sim_bot_from_record(
        bot_id, record, origin=str(record.get("origin") or NEW_ORIGIN)
    )


def wizard_record(config: dict) -> dict:
    """The stored-record shape ``get_full_state`` writes, built from the bot
    wizard's ``get_bot_config`` dict through ``bot_config_kwargs`` and
    ``make_bot_config``, with ``state_when_saved`` idle, no stats,
    ``phantoms_enabled`` from the wizard's ``enable_phantoms`` and
    ``phantom_timeframes`` from ``wizard_phantom_timeframes``.

    ``make_bot_config`` raises ``ValueError`` on a mode-foreign key or a bad
    shape and ``TypeError`` on a value a ``BotConfig`` field cannot hold.
    """
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


def ytd_target_usd(trades: Sequence[YtdTrade]) -> Optional[float]:
    """The Target Balance a pair's fills establish: the ``amount`` the
    ``SIDE_BUY`` fills bought less the ``amount`` the ``SIDE_SELL`` fills sold,
    at the last fill's ``price``, rounded to the cent; None when no unit is
    held, which is a position opened before the first fill.
    """
    ordered = sorted(trades, key=lambda one: one.sort_key())
    if not ordered:
        return None
    bought = sum(float(one.amount) for one in ordered if one.side == SIDE_BUY)
    sold = sum(float(one.amount) for one in ordered if one.side == SIDE_SELL)
    held = bought - sold
    if held <= 0:
        return None
    return round(priced_usd(held, float(ordered[-1].price)), 2)


def ytd_record(bot: SimBot, target_usd: Optional[float]) -> dict:
    """The stored-record shape for one ``ytd_fleet`` bot: ``wizard_record``
    over its exchange, quote, base and symbol, ``config.target_balance`` then
    set to ``target_usd`` or None, ``bot_id`` its own and ``origin``
    ``YTD_ORIGIN``.
    """
    record = wizard_record(
        {
            "exchange_id": bot.exchange_id,
            "base_currency": bot.base_currency,
            "target_asset": bot.asset,
            "symbol": bot.symbol,
            "target_balance": 0.0 if target_usd is None else float(target_usd),
        }
    )
    record["config"]["target_balance"] = target_usd
    record["bot_id"] = bot.bot_id
    record["origin"] = YTD_ORIGIN
    return record


def battery_record(bot: SimBot) -> dict:
    """The stored-record shape for one generated Battery bot: ``wizard_record``
    over its exchange, quote, base, symbol, ``target_usd``, ``ta_timeframe``
    and ``scrumming_interval_pct``, ``bot_id`` its own and ``origin``
    ``BATTERY_ORIGIN``."""
    record = wizard_record(
        {
            "exchange_id": bot.exchange_id,
            "base_currency": bot.base_currency,
            "target_asset": bot.asset,
            "symbol": bot.symbol,
            "target_balance": float(bot.target_usd or 0.0),
            "ta_timeframe": bot.ta_timeframe,
            "scrumming_interval_pct": float(bot.scrumming_interval_pct),
        }
    )
    record["bot_id"] = bot.bot_id
    record["origin"] = BATTERY_ORIGIN
    return record


@dataclass(frozen=True)
class YtdGeneration:
    """What one ``generate_from_ytd`` held: ``bots``, the ``SimBot`` of each
    record held, ``files_read``, how many trade files they were read from,
    ``files``, those files' names, ``trades_read``, the fills read from them,
    and ``missing``, the manifest rows whose file is absent."""

    bots: tuple[SimBot, ...] = ()
    files_read: int = 0
    missing: tuple[YtdFileEntry, ...] = ()
    files: tuple[str, ...] = ()
    trades_read: int = 0


def _extractor_status(bot: SimBot) -> dict:
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


def row_status(bot: SimBot) -> dict:
    """``bot`` as the status dict a live bot's ``get_status`` answers, in the
    keys the Scrumming Bots table, the Extractor Bots table and the Status tab
    read; an extractor's carries ``_extractor_status`` over the base keys.

    ``armed_action``, ``position_ceiling_usd``, ``ceiling_ratio`` and
    ``fold_rate_taper`` are runtime values a stored record does not hold; they
    read as they do on a live bot before its first tick.
    """
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


def aggregate_stats(bots: Sequence[SimBot], budget_usd: Optional[float] = None) -> dict:
    """The header strip's figures over ``bots``, keyed as
    ``FleetAggregationMixin.get_aggregate_stats`` keys the live fleet's and
    summed by its arithmetic: the wallet is ``budget_usd`` when a run names one
    and the largest ``cash_balance_usd`` otherwise, a position is ``priced_usd``
    of ``holdings``, ``current_price`` and ``quote_to_usd`` when both are
    positive and ``position_value_usd`` otherwise, maturity is read only where
    ``exchange_data_fresh_ts`` is positive, and each YTD sum falls back to the
    lifetime sum at zero."""
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
    if budget_usd is not None:
        wallet_cash_usd = float(budget_usd)

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


#: The header strip's figures for a fleet holding no bot, ``aggregate_stats``
#: over none.
EMPTY_AGGREGATE = aggregate_stats(())


def _read_sim_records(path: Path) -> dict[str, dict]:
    """The ``bots`` map of the sim fleet file at ``path``, by ``bot_id``.

    An absent or empty file answers no records and logs nothing; a file that
    is not a JSON object holding a ``bots`` object logs one warning naming
    ``path`` and answers no records.
    """
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("sim fleet file %s unreadable: %s", path, exc)
        return {}
    if not text.strip():
        return {}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("sim fleet file %s malformed: %s", path, exc)
        return {}
    stored = loaded.get("bots") if isinstance(loaded, dict) else None
    if not isinstance(stored, dict):
        logger.warning("sim fleet file %s malformed: no bots object", path)
        return {}
    records = {
        str(bot_id): record
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
            "sim fleet file %s: %d record(s) name no symbol and are not drawn: %s",
            path,
            len(unread),
            ", ".join(unread),
        )
    return records


class FleetSource:
    """The records the sim fleet file holds, as ``SimBot`` records, and the
    read of ``bot_state.json`` that ``import_live_fleet`` copies them from."""

    def __init__(
        self, root: Optional[Path] = None, sim_dir: Optional[Path] = None
    ) -> None:
        """Read the sim fleet file from ``sim_dir``, or from ``get_sim_dir``
        when it is None; ``bot_state.json`` under ``root``, or under
        ``~/.acervator`` when it is None, is read on ``stored_records`` alone."""
        self._root = Path(root) if root is not None else Path.home() / ".acervator"
        self._sim_dir = Path(sim_dir) if sim_dir is not None else get_sim_dir()
        self._records: dict[str, dict] = _read_sim_records(self.sim_path())

    def root(self) -> Path:
        """The directory holding the ``bot_state.json`` this source reads."""
        return self._root

    def path(self) -> Path:
        """The ``bot_state.json`` file itself."""
        return self._root / BOT_STATE_NAME

    def sim_dir(self) -> Path:
        """The directory holding the sim fleet file, ``get_sim_dir`` by default."""
        return self._sim_dir

    def sim_path(self) -> Path:
        """The sim fleet file, ``SIM_FLEET_NAME`` under ``sim_dir``."""
        return self._sim_dir / SIM_FLEET_NAME

    def _state(self) -> dict:
        path = self.path()
        if not path.exists():
            return {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("fleet_source: %s unreadable: %s", path.name, exc)
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def saved_at(self) -> str:
        """The ``saved_at_human`` stamp the live process last wrote."""
        return str(self._state().get("saved_at_human") or "")

    def bots(self) -> list[SimBot]:
        """Every held record as a ``SimBot``, by exchange_id then symbol then
        bot_id; a record read from ``bot_state.json`` is not held until
        ``import_live_fleet`` copies it."""
        out: list[SimBot] = []
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

    def import_live_fleet(self, exchange_id: str) -> list[SimBot]:
        """Copy every stored bot on ``exchange_id`` from ``bot_state.json`` into
        the held records under its own ``bot_id`` with ``origin`` ``LIVE_ORIGIN``,
        replacing a held record of the same id and keeping every other; answers
        the ``SimBot`` of each record copied, by symbol then bot_id, and none
        for an empty ``exchange_id``. The sim fleet file takes them on the next
        ``save``."""
        wanted = str(exchange_id or "")
        if not wanted:
            return []
        imported: list[SimBot] = []
        for bot_id, record in self.stored_records().items():
            bot = _sim_bot_from_record(bot_id, record, origin=LIVE_ORIGIN)
            if bot is None or bot.exchange_id != wanted:
                continue
            record["bot_id"] = bot_id
            record["origin"] = LIVE_ORIGIN
            self._records[bot_id] = record
            imported.append(bot)
        return sorted(imported, key=lambda one: (one.symbol, one.bot_id))

    def generate_from_ytd(self, source: Any, exchange_id: str) -> YtdGeneration:
        """Hold one ``ytd_record`` per pair ``ytd_fleet`` names in ``source``
        on ``exchange_id``, under the pair's own ``bot_id`` with ``YTD_ORIGIN``
        and the ``ytd_target_usd`` of its fills across every year file,
        replacing a held record of the same id; a pair with a manifest row
        whose file ``source.trade_path`` cannot find is not held and its rows
        are answered in ``missing``. The sim fleet file takes them on the next
        ``save``."""
        wanted = str(exchange_id or "")
        if not wanted:
            return YtdGeneration()
        entries = [one for one in source.entries() if one.exchange_id == wanted]
        held: list[SimBot] = []
        missing: list[YtdFileEntry] = []
        files_read = 0
        files: list[str] = []
        trades_read = 0
        for bot in ytd_fleet(source, wanted):
            own = [one for one in entries if one.symbol == bot.symbol]
            absent = [one for one in own if source.trade_path(one) is None]
            if absent:
                missing.extend(absent)
                continue
            trades: list[YtdTrade] = []
            for entry in own:
                trades.extend(source.trades(entry))
                files.append(entry.file)
            files_read += len(own)
            trades_read += len(trades)
            target_usd = ytd_target_usd(trades)
            record = ytd_record(bot, target_usd)
            self._records[bot.bot_id] = record
            made = _held_bot(bot.bot_id, record)
            if made is not None:
                held.append(made)
        return YtdGeneration(
            bots=tuple(held),
            files_read=files_read,
            missing=tuple(sorted(missing, key=lambda one: (one.symbol, one.year))),
            files=tuple(sorted(files)),
            trades_read=trades_read,
        )

    def hold_battery_fleet(self, bots: Sequence[SimBot]) -> list[SimBot]:
        """Make ``bots`` the held fleet: a bot already held under its
        ``bot_id`` on the same symbol, exchange and ``target_usd`` keeps its
        record, every other is held as ``battery_record``, and every held
        record outside ``bots`` is dropped; answers the ``SimBot`` of each
        record held, by exchange then symbol then id. The sim fleet file takes
        them on the next ``save``."""
        kept: dict[str, dict] = {}
        for bot in bots:
            record = self._records.get(bot.bot_id)
            held = _held_bot(bot.bot_id, record) if isinstance(record, dict) else None
            same = (
                held is not None
                and held.symbol == bot.symbol
                and held.exchange_id == bot.exchange_id
                and held.target_usd == bot.target_usd
            )
            kept[bot.bot_id] = record if same else battery_record(bot)
        self._records = kept
        return self.bots()

    def create(self, config: dict) -> SimBot:
        """Hold one record built from the bot wizard's config through
        ``wizard_record`` and answer its ``SimBot``; its ``bot_id`` is the first
        ``BOT_ID_LENGTH`` characters of a ``uuid4``, as a live bot draws its own.
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

    def sim_bot_for(self, bot_id: str) -> Optional[SimBot]:
        """The ``SimBot`` of the held record under ``bot_id``, or None; a
        record in ``bot_state.json`` that ``import_live_fleet`` has not copied
        is not held and answers None."""
        record = self._records.get(str(bot_id))
        if not isinstance(record, dict):
            return None
        return _held_bot(str(bot_id), record)

    def set_state(self, bot_id: str, state: str, clear_error: bool = False) -> str:
        """Write ``state`` into the held record's ``state_when_saved`` and answer
        it; ``clear_error`` empties ``stats.last_error`` and zeroes
        ``stats.consecutive_errors``, as ``BotContainer.start`` does before it
        moves the state. Raises ``KeyError`` when no record is held under
        ``bot_id``."""
        wanted = str(bot_id)
        record = self._records.get(wanted)
        if not isinstance(record, dict):
            raise KeyError(f"no sim record is held under {wanted!r}")
        record["state_when_saved"] = str(state)
        if clear_error:
            stats = record.get("stats")
            if not isinstance(stats, dict):
                stats = {}
                record["stats"] = stats
            stats["last_error"] = ""
            stats["consecutive_errors"] = 0
        return str(state)

    def remove(self, bot_id: str) -> bool:
        """Drop the held record under ``bot_id``; answers whether one was held.
        The sim fleet file loses it on the next ``save``."""
        return self._records.pop(str(bot_id), None) is not None

    def clear(self) -> int:
        """Drop every held record, on every exchange; answers how many were
        held. The sim fleet file loses them on the next ``save``."""
        count = len(self._records)
        self._records = {}
        return count

    def save(self) -> Optional[Path]:
        """Write the held records to ``sim_path`` through ``atomic_write_json``
        under ``saved_at``, ``saved_at_human``, ``bot_count`` and ``bots``, the
        keys ``StateManager.save_state`` writes; answers the path, or None when
        the write fails."""
        payload = {
            "saved_at": time.time(),
            "saved_at_human": datetime.now().strftime(SAVED_AT_HUMAN_FORMAT),
            "bot_count": len(self._records),
            "bots": dict(self._records),
        }
        path = self.sim_path()
        try:
            atomic_write_json(path, payload, indent=2, default=str)
        except (OSError, TypeError, ValueError) as exc:
            logger.error("sim fleet save failed: %s: %s", path, exc)
            return None
        logger.info("sim fleet saved: %d bots to %s", len(self._records), path)
        return path

    def bot_for(self, bot_id: str) -> Optional[SimBot]:
        """The ``SimBot`` whose ``bot_id`` is ``bot_id``, or None."""
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
        until a way in has loaded a fleet."""
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
            f"FleetSource answers {READ_NAMES} and cannot {name!r}. "
            "The Simulator receives and asks; it sends nothing."
        )


def exchange_choice(exchanges: list[str], chosen: str = "") -> dict:
    """Whether the operator must pick an exchange, and which one is in force.

    ``prompt`` is True while more than one exchange is active and ``chosen``
    names none of them.
    """
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


def live_fleet(source: FleetSource, exchange_id: str = "") -> list[SimBot]:
    """One ``SimBot`` per stored bot in ``source.stored_records()``, with
    ``LIVE_ORIGIN``, narrowed to ``exchange_id`` when given, by exchange_id
    then symbol then bot_id."""
    out: list[SimBot] = []
    for bot_id, record in source.stored_records().items():
        bot = _sim_bot_from_record(bot_id, record, origin=LIVE_ORIGIN)
        if bot is None or (exchange_id and bot.exchange_id != exchange_id):
            continue
        out.append(bot)
    return sorted(out, key=lambda one: (one.exchange_id, one.symbol, one.bot_id))


def ytd_fleet(source, exchange_id: str = "") -> list[SimBot]:
    """One ``SimBot`` per symbol in ``source``, narrowed to ``exchange_id``.

    A YTD file names no bot, so ``bot_id`` is its symbol and exchange, and
    ``target_usd`` stays None.
    """
    out: list[SimBot] = []
    seen: set[tuple[str, str]] = set()
    for entry in source.entries():
        if exchange_id and entry.exchange_id != exchange_id:
            continue
        key = (entry.exchange_id, entry.symbol)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            SimBot(
                bot_id=f"{entry.symbol}@{entry.exchange_id}",
                symbol=entry.symbol,
                exchange_id=entry.exchange_id,
                base_currency=entry.symbol.split("/")[-1],
                origin=YTD_ORIGIN,
                target_usd=None,
            )
        )
    return sorted(out, key=lambda one: (one.exchange_id, one.symbol))


__all__ = [
    "BATTERY_ORIGIN",
    "BOT_ID_LENGTH",
    "BOT_STATE_NAME",
    "EMPTY_AGGREGATE",
    "EXTRACTOR_DRAWDOWN_STATE",
    "EXTRACTOR_MODE",
    "LIVE_ORIGIN",
    "NEW_ORIGIN",
    "PHANTOMS_ENABLED_DEFAULT",
    "POOL_GREEN",
    "POOL_RED",
    "POOL_YELLOW",
    "PRE_TICK_AUTO_FIRE",
    "READ_NAMES",
    "SAVED_AT_HUMAN_FORMAT",
    "SCRUMMING_MODE",
    "SIM_FLEET_NAME",
    "YTD_ORIGIN",
    "FleetSource",
    "SendRefused",
    "SimBot",
    "YtdGeneration",
    "aggregate_stats",
    "battery_record",
    "exchange_choice",
    "extractor_pool_color",
    "live_fleet",
    "row_status",
    "wizard_phantom_timeframes",
    "wizard_record",
    "ytd_fleet",
    "ytd_record",
    "ytd_target_usd",
]
