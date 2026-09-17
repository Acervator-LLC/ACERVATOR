"""The Simulator's fleet path: the live bot_state record, read only.

``FleetSource`` answers ``root``, ``path``, ``saved_at``, ``bots``, ``bot_for``,
``exchanges``, ``symbols``, ``statuses`` and ``aggregate`` from
``bot_state.json``. It holds no venue and defines no write, and ``__getattr__``
raises ``SendRefused`` for every other name. ``SimBot`` is a read-only record
forked from the live bot's config, its stats and its saved state, never a
``ScrummingBot``; ``row_status`` answers one as the status dict the Scrumming
Bots table reads; ``live_fleet`` builds one per stored bot and ``ytd_fleet``
builds one per YTD trade file.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .tablet_source import SendRefused

logger = logging.getLogger("acervator.simulator.fleet")

BOT_STATE_NAME = "bot_state.json"

#: Every name ``FleetSource`` answers. ``__getattr__`` refuses the rest.
READ_NAMES = (
    "root",
    "path",
    "saved_at",
    "bots",
    "bot_for",
    "exchanges",
    "symbols",
    "statuses",
    "aggregate",
)

LIVE_ORIGIN = "live"
YTD_ORIGIN = "ytd"

SCRUMMING_MODE = "scrumming"

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
    the figures the Scrumming Bots table and the Status tab draw."""

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


def _sim_bot_from_record(bot_id: str, record: dict) -> Optional[SimBot]:
    """One ``SimBot`` from a stored bot record, or None when it names no
    symbol.

    ``config`` gives the ids and the gate fields, ``stats`` the figures,
    ``scrumming_state`` the grown target, the quote rate, the phase and the
    lots, and ``state_when_saved`` the state.
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
    return SimBot(
        bot_id=str(bot_id),
        symbol=symbol,
        exchange_id=str(config.get("exchange_id") or ""),
        base_currency=str(config.get("base_currency") or ""),
        origin=LIVE_ORIGIN,
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
    )


def row_status(bot: SimBot) -> dict:
    """``bot`` as the status dict a live bot's ``get_status`` answers, in the
    keys the Scrumming Bots table and the Status tab read.

    ``armed_action``, ``position_ceiling_usd``, ``ceiling_ratio`` and
    ``fold_rate_taper`` are runtime values a stored record does not hold; they
    read as they do on a live bot before its first tick.
    """
    return {
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


class FleetSource:
    """The live fleet on disk, as ``SimBot`` records read from
    ``bot_state.json``."""

    def __init__(self, root: Optional[Path] = None) -> None:
        """Read from ``root``, or from ``~/.acervator`` when it is None."""
        self._root = Path(root) if root is not None else Path.home() / ".acervator"

    def root(self) -> Path:
        """The directory holding the ``bot_state.json`` this source reads."""
        return self._root

    def path(self) -> Path:
        """The ``bot_state.json`` file itself."""
        return self._root / BOT_STATE_NAME

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
        """Every stored bot as a ``SimBot``, by exchange_id then symbol."""
        stored = self._state().get("bots")
        if not isinstance(stored, dict):
            return []
        out: list[SimBot] = []
        for bot_id, record in stored.items():
            if not isinstance(record, dict):
                continue
            bot = _sim_bot_from_record(bot_id, record)
            if bot is not None:
                out.append(bot)
        return sorted(out, key=lambda one: (one.exchange_id, one.symbol, one.bot_id))

    def bot_for(self, bot_id: str) -> Optional[SimBot]:
        """The ``SimBot`` whose ``bot_id`` is ``bot_id``, or None."""
        for bot in self.bots():
            if bot.bot_id == str(bot_id):
                return bot
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
    "BOT_STATE_NAME",
    "EMPTY_AGGREGATE",
    "LIVE_ORIGIN",
    "PRE_TICK_AUTO_FIRE",
    "READ_NAMES",
    "SCRUMMING_MODE",
    "YTD_ORIGIN",
    "FleetSource",
    "SendRefused",
    "SimBot",
    "exchange_choice",
    "live_fleet",
    "row_status",
    "ytd_fleet",
]
