"""The Simulator's fleet path: the live bot_state record, read only.

``FleetSource`` answers ``root``, ``path``, ``saved_at``, ``bots``, ``bot_for``,
``exchanges``, ``symbols`` and ``aggregate`` from ``bot_state.json``. It holds
no venue and defines no write, and ``__getattr__`` raises ``SendRefused`` for
every other name. ``SimBot`` is a read-only record forked from the live bot's
config, never a ``ScrummingBot``; ``live_fleet`` builds one per stored bot and
``ytd_fleet`` builds one per YTD trade file.
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
    "aggregate",
)

LIVE_ORIGIN = "live"
YTD_ORIGIN = "ytd"

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
    """One simulated bot: its ids, its symbol and the config the gates read."""

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


def _sim_bot_from_record(bot_id: str, record: dict) -> Optional[SimBot]:
    """One ``SimBot`` from a stored bot record, or None when it names no
    symbol."""
    config = record.get("config")
    if not isinstance(config, dict):
        return None
    symbol = str(config.get("symbol") or "")
    if not symbol:
        return None
    return SimBot(
        bot_id=str(bot_id),
        symbol=symbol,
        exchange_id=str(config.get("exchange_id") or ""),
        base_currency=str(config.get("base_currency") or ""),
        origin=LIVE_ORIGIN,
        target_usd=_number(config.get("target_balance"), 0.0),
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
    )


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
    "READ_NAMES",
    "YTD_ORIGIN",
    "FleetSource",
    "SendRefused",
    "SimBot",
    "exchange_choice",
    "live_fleet",
    "ytd_fleet",
]
