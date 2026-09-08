"""The Paper Trader's fleet path: the live bot_state record, read only.

``PaperFleetSource`` answers ``root``, ``path``, ``saved_at``, ``bots``,
``exchanges`` and ``symbols`` from ``bot_state.json``, and ``__getattr__``
raises ``SendRefused`` for every other name. ``PaperBot`` is a frozen record
forked from the stored config, never a ``ScrummingBot``, and ``paper_fleet``
builds one per stored bot.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .live_feed_source import DEFAULT_TIMEFRAME, SendRefused

logger = logging.getLogger("acervator.paper.fleet")

BOT_STATE_NAME = "bot_state.json"
STATE_DIR_NAME = ".acervator"

LIVE_ORIGIN = "live"

#: Every name ``PaperFleetSource`` answers. ``__getattr__`` refuses the rest.
READ_NAMES = ("root", "path", "saved_at", "bots", "exchanges", "symbols")

#: ``trading_fee_pct`` when a stored config names none.
DEFAULT_TRADING_FEE_PCT = 0.6


@dataclass(frozen=True)
class PaperBot:
    """One paper bot: its ids, its symbol and the config the gates read."""

    bot_id: str
    symbol: str
    exchange_id: str
    base_currency: str
    origin: str = LIVE_ORIGIN
    target_usd: float = 0.0
    ta_timeframe: str = DEFAULT_TIMEFRAME
    scrumming_interval_pct: float = 0.0
    trading_fee_pct: float = DEFAULT_TRADING_FEE_PCT
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
        """The base of ``symbol``, ``BTC`` for ``BTC/USD``."""
        return self.symbol.split("/")[0] if self.symbol else ""


def _number(value: Any, fallback: float) -> float:
    """``value`` as a float, or ``fallback`` when it is not one."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def paper_bot_from_record(bot_id: str, record: dict) -> Optional[PaperBot]:
    """One ``PaperBot`` from a stored bot record, None when it names no symbol."""
    config = record.get("config")
    if not isinstance(config, dict):
        return None
    symbol = str(config.get("symbol") or "")
    if not symbol:
        return None
    return PaperBot(
        bot_id=str(bot_id),
        symbol=symbol,
        exchange_id=str(config.get("exchange_id") or ""),
        base_currency=str(config.get("base_currency") or ""),
        target_usd=_number(config.get("target_balance"), 0.0),
        ta_timeframe=str(config.get("ta_timeframe") or DEFAULT_TIMEFRAME),
        scrumming_interval_pct=_number(config.get("scrumming_interval_pct"), 0.0),
        trading_fee_pct=_number(config.get("trading_fee_pct"), DEFAULT_TRADING_FEE_PCT),
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


class PaperFleetSource:
    """The live fleet on disk, as ``PaperBot`` records from ``bot_state.json``."""

    def __init__(self, root: Optional[Path] = None) -> None:
        """Read from ``root``, or from ``~/.acervator`` when it is None."""
        self._root = Path(root) if root is not None else Path.home() / STATE_DIR_NAME

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
            logger.warning("paper fleet: %s unreadable: %s", path.name, exc)
            return {}
        return loaded if isinstance(loaded, dict) else {}

    def saved_at(self) -> str:
        """The ``saved_at_human`` stamp the live process last wrote."""
        return str(self._state().get("saved_at_human") or "")

    def bots(self) -> list[PaperBot]:
        """Every stored bot as a ``PaperBot``, by exchange_id then symbol."""
        stored = self._state().get("bots")
        if not isinstance(stored, dict):
            return []
        out: list[PaperBot] = []
        for bot_id, record in stored.items():
            if not isinstance(record, dict):
                continue
            bot = paper_bot_from_record(bot_id, record)
            if bot is not None:
                out.append(bot)
        return sorted(out, key=lambda one: (one.exchange_id, one.symbol, one.bot_id))

    def exchanges(self) -> list[str]:
        """Every distinct ``exchange_id`` the stored bots name, sorted."""
        return sorted({bot.exchange_id for bot in self.bots() if bot.exchange_id})

    def symbols(self, exchange_id: Optional[str] = None) -> list[str]:
        """The symbols the stored bots trade, narrowed to ``exchange_id``."""
        return sorted(
            {
                bot.symbol
                for bot in self.bots()
                if exchange_id is None or bot.exchange_id == exchange_id
            }
        )

    def __getattr__(self, name: str):
        """Refuse every name outside ``READ_NAMES``."""
        raise SendRefused(
            f"PaperFleetSource answers {READ_NAMES} and cannot {name!r}. "
            "The Paper Trader receives and asks; it sends nothing."
        )


def paper_fleet(source: PaperFleetSource, exchange_id: str = "") -> list[PaperBot]:
    """The fleet ``source`` holds, narrowed to ``exchange_id`` when given."""
    bots = source.bots()
    if not exchange_id:
        return bots
    return [bot for bot in bots if bot.exchange_id == exchange_id]


__all__ = [
    "BOT_STATE_NAME",
    "DEFAULT_TRADING_FEE_PCT",
    "LIVE_ORIGIN",
    "READ_NAMES",
    "PaperBot",
    "PaperFleetSource",
    "SendRefused",
    "paper_bot_from_record",
    "paper_fleet",
]
