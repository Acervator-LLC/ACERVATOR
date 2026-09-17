"""The Simulator's fleet path: the live bot_state record, read only, and the
bots the wizard creates, held in the sim fleet file under ``get_sim_dir``.

``FleetSource`` answers ``root``, ``path``, ``saved_at``, ``bots``, ``bot_for``,
``record_for``, ``exchanges``, ``symbols``, ``statuses``, ``aggregate``,
``create``, ``sim_bot_for``, ``set_state``, ``remove``, ``sim_dir``,
``sim_path`` and ``save`` from ``bot_state.json`` and the records the sim
fleet file holds; it holds no venue, writes ``sim_path`` alone and sends
nothing, and ``__getattr__`` raises ``SendRefused`` for every other name.
``sim_bot_for``, ``set_state`` and ``remove`` read and move the held records
alone, which is what ``SimBotManager`` acts on. ``SimBot`` is a
read-only record forked from the live bot's config, its stats and its saved
state, never a ``ScrummingBot``; ``row_status`` answers one as the status dict
the Scrumming Bots table and the Extractor Bots table read; ``live_fleet``
builds one per stored bot, ``ytd_fleet`` one per YTD trade file, and
``wizard_record`` the stored-record shape from the bot wizard's config.
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
from typing import Any, Optional

from ..core.io_utils import atomic_write_json
from ..core.log_paths import get_sim_dir
from ..trading.container.config import (
    BotMode,
    BotState,
    bot_config_kwargs,
    make_bot_config,
)
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
    "sim_dir",
    "sim_path",
    "save",
)

LIVE_ORIGIN = "live"
YTD_ORIGIN = "ytd"
NEW_ORIGIN = "new"

SCRUMMING_MODE = "scrumming"
EXTRACTOR_MODE = "extractor"

#: The characters of ``uuid4`` a live bot keeps as its ``bot_id``.
BOT_ID_LENGTH = 8

#: The ``state`` an ``ExtractorBot`` writes on a position below its entry value,
#: ``POSITION_STATE_DRAWDOWN`` in ``src/trading/extractor_bot.py``.
EXTRACTOR_DRAWDOWN_STATE = "drawdown"

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

#: The header strip's figures for a fleet holding no bot, keyed as
#: ``get_aggregate_stats`` keys the live fleet's. Every total is a sum over
#: no bot, and no bot counts as answered by a venue.
EMPTY_AGGREGATE = {
    "running": 0,
    "total_trades": 0,
    "total_errors_lifetime": 0,
    "total_scrummed_usd": 0.0,
    "total_folded_usd": 0.0,
    "total_realised_pnl": 0.0,
    "wallet_cash_usd": 0.0,
    "crypto_position_value_usd": 0.0,
    "total_realized_exchange": 0.0,
    "total_mature_exchange": 0.0,
    "bots_with_fresh_exchange_data": 0,
}


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
    detonation_enabled: bool = False
    detonation_timeframe: str = "1d"
    chunk_size_usd: float = 0.0
    chunk_size_base: float = 0.0
    chunk_free_base: float = 0.0
    n_positions_open: int = 0
    n_positions_drawdown: int = 0

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
    lots, ``extractor_state`` the pool figures, and ``state_when_saved`` the
    state.
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
    config_target = _number(config.get("target_balance"), 0.0)
    pool = _extractor_figures(config, record)
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
        live_target_usd=_number(saved.get("target_balance"), config_target),
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
        detonation_enabled=bool(config.get("detonation_enabled", False)),
        detonation_timeframe=str(config.get("detonation_timeframe") or "1d"),
        chunk_size_usd=pool["chunk_size_usd"],
        chunk_size_base=pool["chunk_size_base"],
        chunk_free_base=pool["chunk_free_base"],
        n_positions_open=pool["n_positions_open"],
        n_positions_drawdown=pool["n_positions_drawdown"],
    )


def wizard_record(config: dict) -> dict:
    """The stored-record shape ``get_full_state`` writes, built from the bot
    wizard's ``get_bot_config`` dict through ``bot_config_kwargs`` and
    ``make_bot_config``, with ``state_when_saved`` idle and no stats.

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
    return {
        "config": stored,
        "stats": {},
        "scrumming_state": {},
        "state_when_saved": BotState.IDLE.value,
    }


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
        if _sim_bot_from_record(bot_id, record, origin=NEW_ORIGIN) is None
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
    """The live fleet on disk, as ``SimBot`` records read from
    ``bot_state.json``, beside the records the sim fleet file holds."""

    def __init__(
        self, root: Optional[Path] = None, sim_dir: Optional[Path] = None
    ) -> None:
        """Read ``bot_state.json`` from ``root``, or from ``~/.acervator`` when
        it is None, and the sim fleet file from ``sim_dir``, or from
        ``get_sim_dir`` when it is None."""
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
        """Every bot the sim fleet file holds and every stored bot as a
        ``SimBot``, by exchange_id then symbol."""
        out: list[SimBot] = []
        for bot_id, record in self._records.items():
            bot = _sim_bot_from_record(bot_id, record, origin=NEW_ORIGIN)
            if bot is not None:
                out.append(bot)
        stored = self._state().get("bots")
        if isinstance(stored, dict):
            for bot_id, record in stored.items():
                if not isinstance(record, dict):
                    continue
                bot = _sim_bot_from_record(bot_id, record)
                if bot is not None:
                    out.append(bot)
        return sorted(out, key=lambda one: (one.exchange_id, one.symbol, one.bot_id))

    def create(self, config: dict) -> SimBot:
        """Hold one record built from the bot wizard's config through
        ``wizard_record`` and answer its ``SimBot``; its ``bot_id`` is the first
        ``BOT_ID_LENGTH`` characters of a ``uuid4``, as a live bot draws its own.
        """
        record = wizard_record(config)
        bot_id = str(uuid.uuid4())[:BOT_ID_LENGTH]
        record["bot_id"] = bot_id
        bot = _sim_bot_from_record(bot_id, record, origin=NEW_ORIGIN)
        if bot is None:
            raise ValueError("the wizard config names no symbol")
        self._records[bot_id] = record
        return bot

    def sim_bot_for(self, bot_id: str) -> Optional[SimBot]:
        """The ``SimBot`` of the held record under ``bot_id``, or None; a
        record read from ``bot_state.json`` is not held and answers None."""
        record = self._records.get(str(bot_id))
        if not isinstance(record, dict):
            return None
        return _sim_bot_from_record(str(bot_id), record, origin=NEW_ORIGIN)

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
        """A copy of the stored record whose ``bot_id`` is ``bot_id``, from the
        sim fleet file first and ``bot_state.json`` second, or None."""
        wanted = str(bot_id)
        held = self._records.get(wanted)
        if isinstance(held, dict):
            return copy.deepcopy(held)
        stored = self._state().get("bots")
        if isinstance(stored, dict) and isinstance(stored.get(wanted), dict):
            return copy.deepcopy(stored[wanted])
        return None

    def exchanges(self) -> list[str]:
        """Every distinct ``exchange_id`` the stored bots name, sorted."""
        return sorted({bot.exchange_id for bot in self.bots() if bot.exchange_id})

    def symbols(self, exchange_id: Optional[str] = None) -> list[str]:
        """The symbols the stored bots trade, narrowed to ``exchange_id`` when
        given."""
        return sorted(
            {
                bot.symbol
                for bot in self.bots()
                if exchange_id is None or bot.exchange_id == exchange_id
            }
        )

    def statuses(self, exchange_id: str = "") -> list[dict]:
        """One ``row_status`` per stored bot, narrowed to ``exchange_id`` when
        given; the list a venue page's ``update_bots`` takes."""
        return [row_status(bot) for bot in live_fleet(self, exchange_id)]

    def aggregate(self) -> dict:
        """The header strip's figures for the fleet the Simulator holds.

        No bot is loaded into the Simulator, so the answer is
        ``EMPTY_AGGREGATE``.
        """
        return dict(EMPTY_AGGREGATE)

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
    """The live fleet from ``source``, narrowed to ``exchange_id`` when given."""
    bots = source.bots()
    if not exchange_id:
        return bots
    return [bot for bot in bots if bot.exchange_id == exchange_id]


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
    "BOT_ID_LENGTH",
    "BOT_STATE_NAME",
    "EMPTY_AGGREGATE",
    "EXTRACTOR_DRAWDOWN_STATE",
    "EXTRACTOR_MODE",
    "LIVE_ORIGIN",
    "NEW_ORIGIN",
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
    "exchange_choice",
    "extractor_pool_color",
    "live_fleet",
    "row_status",
    "wizard_record",
    "ytd_fleet",
]
