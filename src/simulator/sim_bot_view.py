"""A stored bot record read as the bot the Bot Settings window reads.

``SimBotView`` offers the attribute names the window's seven tabs read off a
live bot, each answered from one ``SimBot`` and its raw record: ``config`` and
``stats`` rebuilt as ``restore_bots_from_state`` rebuilds them, the scrumming
figures from ``scrumming_state``, the phantom readings from the record's own
keys, the pool figures and ``positions_for_gui`` from ``extractor_state``.
``SEND_NAMES`` lists every method the window writes through; each raises
``SendRefused``. A runtime name the record does not hold raises
``SendRefused`` too, which ``getattr`` with a default reads as absent.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any, Callable, Optional

from ..trading.container.config import (
    BotConfig,
    BotMode,
    BotStats,
    bot_config_kwargs,
    make_bot_config,
)
from .fleet_source import (
    EXTRACTOR_MODE,
    SimBot,
    extractor_pool_color,
    row_status,
)
from .tablet_source import SendRefused

#: Every name the Bot Settings window writes a bot through; ``set_config_field``
#: stands for Live's ``setattr`` on the config.
SEND_NAMES = (
    "set_config_field",
    "clear_fold_tranches",
    "clear_pending_wire_credits",
    "clear_lifetime_tranche_counters",
    "manual_fire_tranche",
    "toggle_tranche_arbiter",
    "clear_stack_tranches",
    "clear_stack_lifetime_counters",
    "reset_circuit_breaker",
    "self_destruct",
    "manual_fire_position",
    "update_phantom_config",
    "set_target_balance_live",
    "set_visibility_live",
    "set_aggressive_live",
    "set_hedge_balance_live",
    "set_hedge_rebalance_active_live",
    "set_chunk_size_usd",
)

#: ``phantoms_enabled`` for a record without the key, as the restore reads it.
PHANTOMS_ENABLED_DEFAULT = True

#: ``scrumming_state`` keys read as the attribute of the same name with ``_``.
SCRUMMING_FLOATS = (
    "target_balance",
    "anchor_target_balance",
    "standing_surplus_usd",
    "fold_cycle_cap_consumed",
    "pending_wire_credits",
    "wire_credits_discarded_lifetime",
    "tranches_counters_reset_ts",
    "stack_counters_reset_ts",
)
SCRUMMING_INTS = (
    "tranches_created_lifetime",
    "tranches_closed_lifetime",
    "tranches_discarded_lifetime",
    "tranches_malformed_dropped",
    "stack_created",
    "stack_discarded",
)
SCRUMMING_LISTS = (
    "fold_tranches",
    "stack_tranches",
    "pending_wire_ledger",
)


def _number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _dicts(value: Any) -> list:
    if not isinstance(value, list):
        return []
    return [dict(one) for one in value if isinstance(one, dict)]


def config_of(record: dict) -> BotConfig:
    """``record["config"]`` as a ``BotConfig``, built as the restore builds it."""
    stored = record.get("config")
    stored = dict(stored) if isinstance(stored, dict) else {}
    mode = (
        BotMode.EXTRACTOR if stored.get("mode") == EXTRACTOR_MODE else BotMode.SCRUMMING
    )
    exchange_id = str(stored.get("exchange_id") or "")
    kwargs = bot_config_kwargs(mode, stored, exchange_id=exchange_id)
    return make_bot_config(mode, **kwargs)


def stats_of(record: dict) -> BotStats:
    """``record["stats"]`` as a ``BotStats``; a key the class lacks is dropped."""
    stored = record.get("stats")
    stored = stored if isinstance(stored, dict) else {}
    known = {one.name for one in fields(BotStats)}
    return BotStats(**{key: value for key, value in stored.items() if key in known})


class PhantomLock:
    """The one coordinator reading the window asks for, ``lock_candle_count``."""

    def __init__(self, lock_candle_count: int) -> None:
        self.lock_candle_count = int(lock_candle_count)


class SimBotView:
    """One ``SimBot`` and its record, read through a live bot's attribute names."""

    def __init__(self, bot: SimBot, record: Optional[dict] = None) -> None:
        stored = dict(record) if isinstance(record, dict) else {}
        saved = stored.get("scrumming_state")
        saved = saved if isinstance(saved, dict) else {}
        pool = stored.get("extractor_state")
        pool = pool if isinstance(pool, dict) else {}
        self.bot = bot
        self.record = stored
        self.bot_id = bot.bot_id
        self.state = bot.state
        self.config = config_of(stored) if stored else _config_from_bot(bot)
        self.stats = stats_of(stored)
        for key in SCRUMMING_FLOATS:
            setattr(self, "_" + key, _number(saved.get(key), 0.0))
        for key in SCRUMMING_INTS:
            setattr(self, "_" + key, int(_number(saved.get(key), 0)))
        for key in SCRUMMING_LISTS:
            setattr(self, "_" + key, _dicts(saved.get(key)))
        if "target_balance" not in saved:
            self._target_balance = _number(bot.live_target_usd, 0.0)
        self._current_holdings = _number(bot.holdings, 0.0)
        self._phantoms_enabled = bool(
            stored.get("phantoms_enabled", PHANTOMS_ENABLED_DEFAULT)
        )
        self._phantom_timeframes = [
            str(one) for one in (stored.get("phantom_timeframes") or [])
        ]
        lock = stored.get("lock_candle_count")
        self._coordinator = PhantomLock(lock) if lock is not None else None
        self._chunk_size_usd = _number(pool.get("chunk_size_usd"), bot.chunk_size_usd)
        self._chunk_size_base = _number(
            pool.get("chunk_size_base"), bot.chunk_size_base
        )
        self._chunk_free_base = _number(
            pool.get("chunk_free_base"), bot.chunk_free_base
        )
        self._chunk_extracted_total = _number(pool.get("chunk_extracted_total"), 0.0)
        self._usd_per_base_rate = _number(pool.get("chunk_to_base_rate"), 1.0)
        self._positions = _dicts(pool.get("positions"))
        self.cycle_growth_cap_usd = None

    def get_status(self) -> dict:
        """The status dict the tables and the Status tab read, ``row_status``."""
        return row_status(self.bot)

    def open_extractor_tranches(self) -> list:
        """No manager is attached, so no Extractor Tranche is listed."""
        return []

    def pool_color(self) -> str:
        """``extractor_pool_color`` over the stored positions."""
        drawdown = sum(1 for one in self._positions if one.get("state") == "drawdown")
        return extractor_pool_color(len(self._positions), drawdown)

    def positions_for_gui(self) -> list:
        """One row per stored position, keyed as ``ExtractorBot.positions_for_gui``."""
        rows = []
        for one in self._positions:
            alt_units = _number(one.get("alt_units"), 0.0)
            avg_buy = _number(one.get("avg_buy_price_base_per_alt"), 0.0)
            entry_usd = _number(one.get("artillery_size_usd_at_entry"), 0.0)
            current_usd = alt_units * avg_buy * self._usd_per_base_rate
            delta_pct = (
                (current_usd - entry_usd) / entry_usd * 100.0 if entry_usd > 0 else 0.0
            )
            rows.append(
                {
                    "pair": one.get("pair"),
                    "state": one.get("state"),
                    "alt_units": alt_units,
                    "entry_usd": entry_usd,
                    "current_usd_approx": current_usd,
                    "delta_pct_usd_approx": delta_pct,
                    "cost_basis_base": _number(one.get("cost_basis_base"), 0.0),
                    "avg_buy_price_base_per_alt": avg_buy,
                    "opened_at": one.get("opened_at"),
                }
            )
        return rows

    def __getattr__(self, name: str) -> Any:
        """Refuse every send in ``SEND_NAMES`` and every runtime name not held."""
        if name.startswith("__"):
            raise AttributeError(name)
        if name in SEND_NAMES:
            return _refusal(name)
        reason = (
            f"SimBotView holds no {name!r}: the stored record carries no such "
            "reading. The Simulator receives and asks; it sends nothing."
        )
        raise SendRefused(reason)


def _refusal(name: str) -> Callable[..., Any]:
    reason = (
        f"SimBotView cannot {name!r}: the Simulator receives and asks; "
        "it sends nothing."
    )

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise SendRefused(reason)

    refuse.__name__ = name
    return refuse


def _config_from_bot(bot: SimBot) -> BotConfig:
    """A ``BotConfig`` from the ``SimBot`` alone, for a bot with no record."""
    mode = BotMode.EXTRACTOR if bot.mode == EXTRACTOR_MODE else BotMode.SCRUMMING
    base, _, quote = bot.symbol.partition("/")
    collected = {
        "exchange_id": bot.exchange_id,
        "base_currency": bot.base_currency or quote,
        "target_asset": base,
        "symbol": bot.symbol,
        "target_balance": bot.target_usd or 0.0,
        "ta_timeframe": bot.ta_timeframe or "1h",
    }
    return make_bot_config(mode, **bot_config_kwargs(mode, collected))


__all__ = [
    "PHANTOMS_ENABLED_DEFAULT",
    "SEND_NAMES",
    "PhantomLock",
    "SimBotView",
    "config_of",
    "stats_of",
]
