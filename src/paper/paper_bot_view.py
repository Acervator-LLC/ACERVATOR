"""A stored bot record read as the bot the Bot Settings window reads.

``PaperBotView`` offers the attribute names the window's seven tabs read off a
live bot, each answered from one ``PaperBot`` and its raw record: ``config`` and
``stats`` rebuilt as ``restore_bots_from_state`` rebuilds them, the scrumming
figures from ``scrumming_state``, the phantom readings from the record's own
keys, the pool figures and ``positions_for_gui`` from ``extractor_state``.
``SEND_NAMES`` lists every method the window writes through; each raises
``SendRefused``. A runtime name the record does not hold raises
``SendRefused`` too, which ``getattr`` with a default reads as absent.
"""

# OVERTAKEN: "``SEND_NAMES`` lists every method the window writes through; each
# raises ``SendRefused``."
# ``SEND_NAMES`` lists every method that raises; ``set_config_field`` is a
# method of its own and writes the record through ``writer``.

from __future__ import annotations

from dataclasses import fields
from typing import Any, Callable, Optional

from ..trading.container.config import (
    BotConfig,
    BotMode,
    BotStats,
    as_finite_float,
    bot_config_kwargs,
    make_bot_config,
)
from ..trading.scrumming.sizing import cycle_growth_cap_usd
from .fleet_source import (
    EXTRACTOR_MODE,
    PHANTOMS_ENABLED_DEFAULT,
    RECORD_FIELDS,
    PaperBot,
    extractor_pool_color,
    row_status,
)
from .live_feed_source import SendRefused

#: Every name the Bot Settings window writes a bot through; ``set_config_field``
#: stands for Live's ``setattr`` on the config.
# OVERTAKEN: the two lines above.
# Every name the Bot Settings window writes a bot through EXCEPT
# ``set_config_field``, which writes the held record through ``writer``.
SEND_NAMES = (
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


#: Units, dollars and counts a record draws when as_finite_float refuses them.
REFUSED_FIGURE: float = 0.0


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


class PaperBotView:
    """One ``PaperBot`` and its record, read through a live bot's attribute names."""

    def __init__(
        self,
        bot: PaperBot,
        record: Optional[dict] = None,
        writer: Optional[Callable[[str, Any], Any]] = None,
    ) -> None:
        stored = dict(record) if isinstance(record, dict) else {}
        self._writer = writer
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
            read = as_finite_float(saved.get(key))
            setattr(self, "_" + key, REFUSED_FIGURE if read is None else read)
        for key in SCRUMMING_INTS:
            read = as_finite_float(saved.get(key))
            setattr(self, "_" + key, int(REFUSED_FIGURE if read is None else read))
        for key in SCRUMMING_LISTS:
            setattr(self, "_" + key, _dicts(saved.get(key)))
        if "target_balance" not in saved:
            target_read = as_finite_float(bot.live_target_usd)
            self._target_balance = (
                REFUSED_FIGURE if target_read is None else target_read
            )
        holdings_read = as_finite_float(bot.holdings)
        self._current_holdings = (
            REFUSED_FIGURE if holdings_read is None else holdings_read
        )
        self._phantoms_enabled = bool(
            stored.get("phantoms_enabled", PHANTOMS_ENABLED_DEFAULT)
        )
        self._phantom_timeframes = [
            str(one) for one in (stored.get("phantom_timeframes") or [])
        ]
        lock = stored.get("lock_candle_count")
        self._coordinator = PhantomLock(lock) if lock is not None else None
        size_usd = as_finite_float(pool.get("chunk_size_usd"))
        size_base = as_finite_float(pool.get("chunk_size_base"))
        free_base = as_finite_float(pool.get("chunk_free_base"))
        extracted = as_finite_float(pool.get("chunk_extracted_total"))
        base_rate = as_finite_float(pool.get("chunk_to_base_rate"))
        self._chunk_size_usd = bot.chunk_size_usd if size_usd is None else size_usd
        self._chunk_size_base = bot.chunk_size_base if size_base is None else size_base
        self._chunk_free_base = bot.chunk_free_base if free_base is None else free_base
        self._chunk_extracted_total = REFUSED_FIGURE if extracted is None else extracted
        self._usd_per_base_rate = 1.0 if base_rate is None else base_rate
        self._positions = _dicts(pool.get("positions"))
        self.cycle_growth_cap_usd = cycle_growth_cap_usd(
            self._target_balance,
            self._fold_cycle_cap_consumed,
            float(getattr(self.config, "max_target_growth_pct", 1.0) or 0.0),
        )

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
            units_read = as_finite_float(one.get("alt_units"))
            buy_read = as_finite_float(one.get("avg_buy_price_base_per_alt"))
            entry_read = as_finite_float(one.get("artillery_size_usd_at_entry"))
            basis_read = as_finite_float(one.get("cost_basis_base"))
            alt_units = REFUSED_FIGURE if units_read is None else units_read
            avg_buy = REFUSED_FIGURE if buy_read is None else buy_read
            entry_usd = REFUSED_FIGURE if entry_read is None else entry_read
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
                    "cost_basis_base": (
                        REFUSED_FIGURE if basis_read is None else basis_read
                    ),
                    "avg_buy_price_base_per_alt": avg_buy,
                    "opened_at": one.get("opened_at"),
                }
            )
        return rows

    def set_config_field(self, field: str, value: Any) -> Any:
        """Write one field of this bot's stored record through ``writer`` and
        answer what it stored, raising ``SendRefused`` when none was given."""
        if self._writer is None:
            raise SendRefused(
                f"PaperBotView was built with no writer and cannot set {field!r}."
            )
        stored = self._writer(field, value)
        if field in RECORD_FIELDS:
            self.record[RECORD_FIELDS[field]] = stored
        else:
            setattr(self.config, field, stored)
        return stored

    def __getattr__(self, name: str) -> Any:
        """Refuse every send in ``SEND_NAMES`` and every runtime name not held."""
        if name.startswith("__"):
            raise AttributeError(name)
        if name in SEND_NAMES:
            return _refusal(name)
        reason = (
            f"PaperBotView holds no {name!r}: the stored record carries no such "
            "reading. The Paper Trader receives and asks; it sends nothing."
        )
        raise SendRefused(reason)


def _refusal(name: str) -> Callable[..., Any]:
    reason = (
        f"PaperBotView cannot {name!r}: the Paper Trader receives and asks; "
        "it sends nothing."
    )

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise SendRefused(reason)

    refuse.__name__ = name
    return refuse


def _config_from_bot(bot: PaperBot) -> BotConfig:
    """A ``BotConfig`` from the ``PaperBot`` alone, for a bot with no record."""
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
    "PaperBotView",
    "config_of",
    "stats_of",
]
