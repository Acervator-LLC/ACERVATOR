"""Fleet-wide sums for BotManager.

Two of them: what the other bots have claimed of a shared pool, and the
dashboard aggregate.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

from ..smart_wire import is_mature, mature_profit_usd
from ..target_bands import fleet_ammo
from .config import (
    DOLLAR_PEGGED_CURRENCIES,
    UNREADABLE_TOTALS_KEY,
    BotState,
    as_finite_float,
    as_whole_count,
)

logger = logging.getLogger("acervator.bot")

#: The published total every bot's ``accrued_growth_usd`` feeds.
ACCRUED_TOTAL = "total_accrued_usd"

#: The three Scrummed totals. The published pair falls back from the
#: year-to-date sum to the lifetime one, so either refusal marks all three.
SCRUMMED_TOTALS = (
    "total_scrummed_usd",
    "total_scrummed_usd_ytd",
    "total_scrummed_usd_lifetime",
)

#: The three Folded totals, read the same way as SCRUMMED_TOTALS.
FOLDED_TOTALS = (
    "total_folded_usd",
    "total_folded_usd_ytd",
    "total_folded_usd_lifetime",
)

#: The totals one bot's cash balance feeds.
CASH_TOTALS = ("wallet_cash_usd", "total_account_value_usd")

#: The totals one bot's maturity reading feeds.
MATURE_TOTALS = ("total_mature_exchange", "mature_positions")

#: The totals one bot's Ammo reading feeds.
AMMO_TOTALS = (
    "total_target_delta_usd",
    "bots_scrum_territory",
    "bots_fold_territory",
)

#: The totals one bot's position value feeds: the Locked column, the account
#: value, the maturity reading taken against it and the Ammo distance.
POSITION_TOTALS = (
    (
        "crypto_position_value_usd",
        "total_account_value_usd",
    )
    + MATURE_TOTALS
    + AMMO_TOTALS
)

#: The totals one bot's exchange-freshness stamp gates.
FRESHNESS_TOTALS = (
    "bots_with_fresh_exchange_data",
    "realised_history_complete",
) + MATURE_TOTALS

#: The counts one bot's run state feeds.
STATE_TOTALS = ("running", "errored")

#: Every total one bot's ``stats`` feeds, marked together when ``stats``
#: itself cannot be reached.
STATS_TOTALS = tuple(
    dict.fromkeys(
        SCRUMMED_TOTALS
        + FOLDED_TOTALS
        + CASH_TOTALS
        + POSITION_TOTALS
        + FRESHNESS_TOTALS
        + (
            "total_realised_pnl",
            "total_trades",
            "total_errors_lifetime",
            "total_realized_exchange",
            "total_unrealized_exchange",
            "total_fees_exchange",
        )
    )
)


def accrued_growth_usd(
    target_balance: Any, anchor_target_balance: Any
) -> Optional[float]:
    """One bot's compounded growth: its live target less its anchor target.

    ``as_finite_float`` admits both figures, and a refused figure answers ``None``.
    """
    target = as_finite_float(target_balance)
    anchor = as_finite_float(anchor_target_balance)
    if target is None or anchor is None:
        return None
    return target - anchor


def fleet_accrued_usd(bots: Any, unreadable: set) -> float:
    """Every bot's ``accrued_growth_usd`` added together, to the cent.

    A bot carrying no ``_anchor_target_balance`` reads its own
    ``_target_balance`` as the anchor and contributes nothing; a bot whose
    target or anchor cannot be read contributes nothing and names
    ``ACCRUED_TOTAL`` in ``unreadable``.
    """
    total = 0.0
    for bot in bots:
        try:
            target = getattr(bot, "_target_balance", 0.0)
            growth = accrued_growth_usd(
                target, getattr(bot, "_anchor_target_balance", target)
            )
        except Exception as _read_exc:
            unreadable.add(ACCRUED_TOTAL)
            logger.warning(
                "Accumulated total: bot %s's target balance could not be "
                "read (%s). The total is marked unreadable and the "
                "ACCUMULATED card draws a dash.",
                getattr(bot, "bot_id", "?"),
                _read_exc,
            )
            continue
        if growth is None:
            unreadable.add(ACCRUED_TOTAL)
            continue
        total += growth
    return round(total, 4)


class FleetTotals:
    """The admissions one aggregate pass reads by, and the totals it marked.

    ``money``, ``count`` and ``flag`` each name every published total a refused
    figure feeds, which ``get_aggregate_stats`` publishes under
    ``UNREADABLE_TOTALS_KEY``.
    """

    def __init__(self) -> None:
        self.unreadable: set[str] = set()

    def money(self, value: Any, *totals: str) -> Optional[float]:
        """One stored dollar figure, or ``None`` after marking ``totals``."""
        amount = as_finite_float(value)
        if amount is None:
            self.unreadable.update(totals)
        return amount

    def count(self, value: Any, *totals: str) -> Optional[int]:
        """One stored whole count, or ``None`` after marking ``totals``."""
        counted = as_whole_count(value)
        if counted is None:
            self.unreadable.update(totals)
        return counted

    def flag(self, value: Any, *totals: str) -> bool:
        """One stored true or false; any other kind marks ``totals`` and is False."""
        if type(value) is bool:
            return value
        self.unreadable.update(totals)
        return False


class FleetAggregationMixin:
    """Aggregation half of ``BotManager``: totals computed across ``_bots``.

    Composed into ``BotManager``; ``self`` is the manager instance.
    """

    # Annotation only, supplied by BotManager at runtime: no attribute is
    # created and the runtime base stays `object`.
    _bots: dict

    #: The marked totals the last pass logged. The dashboard asks every two
    #: seconds, and an unchanged list is not logged again.
    _last_unreadable_totals: Optional[list] = None

    def _log_unreadable_totals(self, unreadable_totals: list) -> None:
        """Log the totals one pass could not sum whole, once per change.

        ``_last_unreadable_totals`` holds the last logged list, and an
        unchanged one is not logged again.
        """
        if unreadable_totals == self._last_unreadable_totals:
            return
        self._last_unreadable_totals = list(unreadable_totals)
        if not unreadable_totals:
            logger.info("Fleet totals: every dashboard total sums whole again.")
            return
        logger.warning(
            "Fleet totals: %d of the dashboard's totals could not be summed "
            "whole: %s. A bot's stored figure for each of them was not a "
            "number. The header strip draws a dash for each and every other "
            "cell still carries its figure.",
            len(unreadable_totals),
            ", ".join(unreadable_totals),
        )

    def has_sibling_target_bots(self, bot_id: str, target_asset: str) -> bool:
        """Return True if any OTHER registered bot has the same target
        asset, whatever its base currency.

        `ScrummingBot._tick_initialise` asks this to decide whether
        ``exchange.get_balance(target_asset).total`` is this bot's own
        holdings (one bot, trust it) or a pool shared with other bots
        (multi-base, distrust it and use ``_main_lots`` as the
        authoritative record of what THIS bot bought).

        Paused and idle bots count: restarting one must not surprise a
        running bot that had been reading the whole balance as its own.
        """
        target_norm = (target_asset or "").upper()
        for other_id, other_bot in self._bots.items():
            if other_id == bot_id:
                continue
            try:
                other_target = (other_bot.config.target_asset or "").upper()
            except Exception as _read_exc:
                logger.warning(
                    "Sibling check for %s skipped bot %s: its coin "
                    "setting could not be read (%s). That bot is not "
                    "counted as sharing %s.",
                    bot_id,
                    other_id,
                    _read_exc,
                    target_norm or "the coin",
                )
                continue
            if other_target == target_norm and target_norm:
                return True
        return False

    def sum_sibling_tracked_units(self, bot_id: str, target_asset: str) -> float:
        """Sum the ``_main_lots`` units tracked by every other bot with the
        same target_asset, excluding the caller.

        Reconciliation in multi-base mode holds that this bot's
        ``_current_holdings`` never exceeds
        ``exchange_total - sum_sibling_tracked_units``. When it does,
        another bot has lost track of some of its inventory.
        """
        target_norm = (target_asset or "").upper()
        total = 0.0
        for other_id, other_bot in self._bots.items():
            if other_id == bot_id:
                continue
            try:
                if (other_bot.config.target_asset or "").upper() != target_norm:
                    continue
            except Exception as _read_exc:
                logger.warning(
                    "Tracked-units total for %s skipped bot %s: its "
                    "coin setting could not be read (%s). None of that "
                    "bot's %s is counted in the total.",
                    bot_id,
                    other_id,
                    _read_exc,
                    target_norm or "coin",
                )
                continue
            try:
                lots = getattr(other_bot, "_main_lots", []) or []
                for lot in lots:
                    total += float(lot.get("units", 0) or 0)
            except Exception as _lot_exc:
                # Units added before the raise stay in the running total.
                logger.warning(
                    "Tracked-units total for %s stopped part-way "
                    "through bot %s: one of its purchase records "
                    "could not be read (%s). The total is short by "
                    "that bot's remaining %s.",
                    bot_id,
                    other_id,
                    _lot_exc,
                    target_norm or "coin",
                )
                continue
        return total

    def _one_sibling_claim(
        self,
        other_bot: Any,
        other_cfg: Any,
        dollar_pegged: bool,
    ) -> tuple[Optional[float], str]:
        """What one other bot has claimed from the shared pool.

        The answer is in units of the pool's currency. Returns the claim
        and an empty reason, or ``None`` and the reason when it cannot be
        worked out. ``None`` is never zero: zero means
        the bot claims none of the pool, ``None`` means we do not know
        what it claims, and a bot that does not know must not guess low.

        Two kinds of claim are added together. A dollar allocation is
        turned into pool units with the bot's own cached rate. An
        allocated chunk is already in pool units and is added as it
        stands.
        """
        claim = 0.0
        try:
            target_usd = float(getattr(other_cfg, "target_balance", 0) or 0)
        except Exception as _t_exc:
            return None, f"its dollar allocation could not be read ({_t_exc})"
        if not math.isfinite(target_usd):
            return None, "its dollar allocation is not a number"
        if target_usd < 0:
            return None, (
                f"its dollar allocation is negative ({target_usd}), which "
                f"cannot be an amount of money"
            )
        if target_usd > 0:
            rate, why = self._sibling_pool_rate(other_bot, dollar_pegged)
            if rate is None:
                return None, why
            claim += target_usd / rate
        try:
            chunk_base = float(getattr(other_bot, "_chunk_size_base", 0) or 0)
        except Exception as _c_exc:
            return None, f"its allocated chunk could not be read ({_c_exc})"
        if not math.isfinite(chunk_base):
            return None, "its allocated chunk is not a number"
        if chunk_base < 0:
            return None, (
                f"its allocated chunk is negative ({chunk_base}), which "
                f"cannot be an amount held"
            )
        return claim + chunk_base, ""

    def _sibling_pool_rate(
        self,
        other_bot: Any,
        dollar_pegged: bool,
    ) -> tuple[Optional[float], str]:
        """How many dollars one unit of the pool currency is worth, read
        from the other bot's own cached ``_quote_to_usd``.

        Returns the rate and an empty reason, or ``None`` and the reason.
        A pool of a coin meant to be worth one dollar falls back to 1.0
        whenever the cached rate is unusable. No other pool does: on a
        Bitcoin pool that fallback reads a bot's $1,000 allocation as a
        claim on 1,000 Bitcoin.
        """
        raw: Any = None
        rate: Optional[float] = None
        try:
            # A missing rate is not the only failure here: the read itself
            # can raise, which a default value does not catch.
            raw = getattr(other_bot, "_quote_to_usd", None)
            if raw is not None:
                rate = float(raw)
        except Exception as _r_exc:
            if dollar_pegged:
                return 1.0, ""
            return None, f"its cached rate could not be read ({_r_exc})"
        if rate is not None and math.isfinite(rate) and rate > 0:
            return rate, ""
        if dollar_pegged:
            return 1.0, ""
        return None, (
            f"its cached rate is {raw!r}, so its dollar allocation "
            f"cannot be turned into pool units"
        )

    def sum_sibling_base_currency_claims(
        self,
        bot_id: str,
        exchange_id: str,
        currency: str,
    ) -> Optional[float]:
        """Sum of base-currency (quote-currency) claims by OTHER bots on
        the same exchange, in base-currency units.

        A "claim" is operator-allocated capital a bot OWNS even when it is
        not actively deployed:

          * **ScrummingBot** whose ``config.base_currency == currency``:
            its ``target_balance``, converted through that bot's own
            cached ``_quote_to_usd``. That rate reads "1 unit of quote
            currency = N USD", so ``USD / _quote_to_usd`` yields quote
            units. A pool of a coin meant to be worth one dollar needs no
            rate; any other pool with no usable rate counts as unreadable.
          * **ExtractorBot** whose ``config.base_currency == currency``:
            its ``_chunk_size_base``, the operator-allocated base-unit
            chunk, already in base units.

        Includes bots in every run state — a paused bot still owns its
        allocation, and restarting it must not surprise the active bot by
        un-reserving its funds. Excludes the querying bot, whose own claim
        is implicit, and bots on other exchanges, which are other pools.

        Returns ``None``, never a partial sum, when any bot in the pool
        cannot be read, and logs one warning naming every unreadable bot,
        its reason, and the incomplete total. A short total tells the
        asking bot money is free that another bot has already claimed,
        which is how two bots spend the same money. A caller that gets
        ``None`` must refuse to act and must not read it as zero claims.

        On success the caller subtracts the sum from the raw exchange
        balance to get its claim-aware free balance.
        """
        currency_norm = (currency or "").upper()
        if not currency_norm:
            logger.warning(
                "Asked what the other bots have claimed on %s, but no "
                "currency was named. Returning no total rather than "
                "zero, because zero would say the whole pool is free.",
                exchange_id,
            )
            return None
        dollar_pegged = currency_norm in DOLLAR_PEGGED_CURRENCIES
        total = 0.0
        unread: list[str] = []
        for other_id, other_bot in self._bots.items():
            if other_id == bot_id:
                continue
            try:
                other_cfg = other_bot.config
                same_exchange = other_cfg.exchange_id == exchange_id
                other_base = (getattr(other_cfg, "base_currency", "") or "").upper()
            except Exception as _cfg_exc:
                # Pool membership is unknown after a failed read, so
                # skipping this bot could hide a real claim.
                unread.append(
                    f"{other_id} (its settings could not be read: " f"{_cfg_exc})"
                )
                continue
            if not same_exchange or other_base != currency_norm:
                continue
            claim, why = self._one_sibling_claim(other_bot, other_cfg, dollar_pegged)
            if claim is None:
                unread.append(f"{other_id} ({why})")
                continue
            total += claim
        if unread:
            logger.warning(
                "Could not read what %d of the other bots on %s have "
                "claimed of the %s pool: %s. Leaving them out would "
                "have reported %.8f %s, which is lower than the truth "
                "and would let a bot spend money another bot has "
                "already claimed. Returning no total instead.",
                len(unread),
                exchange_id,
                currency_norm,
                "; ".join(unread),
                total,
                currency_norm,
            )
            return None
        return total

    def _bot_position_usd(self, bot: Any, stats: Any, totals: FleetTotals) -> float:
        """One bot's position value in dollars, from its holdings and price.

        ``stats.position_value`` stands where ``_current_holdings`` or
        ``stats.current_price`` is not above zero, and every figure is admitted
        through ``totals``.
        """
        cached = totals.money(getattr(stats, "position_value", 0.0), *POSITION_TOTALS)
        holdings = totals.money(
            getattr(bot, "_current_holdings", 0.0), *POSITION_TOTALS
        )
        price = totals.money(getattr(stats, "current_price", 0.0), *POSITION_TOTALS)
        rate = totals.money(getattr(bot, "_quote_to_usd", 1.0), *POSITION_TOTALS)
        if holdings is not None and price is not None and rate is not None:
            if holdings > 0 and price > 0:
                return holdings * price * (rate or 1.0)
        return cached if cached is not None else 0.0

    def _read_one_bot(self, bot: Any, totals: FleetTotals, carry: dict) -> None:
        """Add one bot's admitted figures into ``carry``.

        A figure ``totals`` refuses adds nothing and marks every total it feeds,
        and an unreachable ``stats`` marks ``STATS_TOTALS``.
        """
        try:
            stats = bot.stats
        except Exception as _stats_exc:  # noqa: BLE001 - one bot, not the fleet
            totals.unreadable.update(STATS_TOTALS)
            logger.warning(
                "Fleet totals: bot %s's own figures could not be read (%s). "
                "Every total it feeds is marked unreadable and the header "
                "strip draws a dash for each.",
                getattr(bot, "bot_id", "?"),
                _stats_exc,
            )
            stats = None
        if stats is not None:
            self._add_bot_stats(bot, stats, totals, carry)
        try:
            state = bot.state
        except Exception as _state_exc:  # noqa: BLE001 - one bot, not the fleet
            totals.unreadable.update(STATE_TOTALS)
            logger.warning(
                "Fleet totals: bot %s's run state could not be read (%s). "
                "The running and errored counts are marked unreadable.",
                getattr(bot, "bot_id", "?"),
                _state_exc,
            )
            return
        if state == BotState.RUNNING:
            carry["running"] += 1
        if state == BotState.ERROR:
            carry["errored"] += 1

    def _add_bot_stats(
        self, bot: Any, stats: Any, totals: FleetTotals, carry: dict
    ) -> None:
        """Add one bot's ``stats`` figures into ``carry``, each admitted first.

        The money sums, the two counts, the cash maximum, the position value,
        the maturity reading and the Ammo reading all come from here.
        """
        for field, name, keys in (
            ("realised_pnl", "pnl", ("total_realised_pnl",)),
            ("total_scrummed_usd", "scrummed", SCRUMMED_TOTALS),
            ("total_folded_usd", "folded", FOLDED_TOTALS),
            ("ytd_scrummed_usd", "scrummed_ytd", SCRUMMED_TOTALS),
            ("ytd_folded_usd", "folded_ytd", FOLDED_TOTALS),
            (
                "realized_pnl_exchange",
                "realized_exchange",
                ("total_realized_exchange",),
            ),
            ("unrealised_pnl", "unrealized_exchange", ("total_unrealized_exchange",)),
            ("fees_paid_exchange", "fees_exchange", ("total_fees_exchange",)),
        ):
            amount = totals.money(getattr(stats, field, 0.0), *keys)
            if amount is not None:
                carry[name] += amount
        trades = totals.count(getattr(stats, "total_trades", 0), "total_trades")
        if trades is not None:
            carry["trades"] += trades
        errors = totals.count(
            getattr(stats, "total_errors", 0), "total_errors_lifetime"
        )
        if errors is not None:
            carry["errors_lifetime"] += errors
        # Freshest non-zero cash balance wins.
        cash = totals.money(getattr(stats, "cash_balance_usd", 0.0), *CASH_TOTALS)
        if cash is not None and cash > carry["wallet_cash"]:
            carry["wallet_cash"] = cash
        position_usd = self._bot_position_usd(bot, stats, totals)
        carry["position_value"] += position_usd
        self._add_ammo_reading(bot, position_usd, totals, carry)
        fresh_ts = totals.money(
            getattr(stats, "exchange_data_fresh_ts", 0.0), *FRESHNESS_TOTALS
        )
        # The cost basis is exchange-pulled, so a bot the venue has not
        # answered for contributes no maturity reading either way.
        if fresh_ts is None or fresh_ts <= 0:
            return
        carry["fresh_bots"] += 1
        if totals.flag(
            getattr(stats, "fill_history_complete", False),
            "realised_history_complete",
        ):
            carry["complete_history_bots"] += 1
        basis = totals.money(
            getattr(stats, "cost_basis_total_exchange", 0.0), *MATURE_TOTALS
        )
        if basis is not None and is_mature(basis, position_usd):
            carry["mature_usd"] += mature_profit_usd(basis, position_usd)
            carry["mature_positions"] += 1

    def _add_ammo_reading(
        self, bot: Any, position_usd: float, totals: FleetTotals, carry: dict
    ) -> None:
        """Append one bot's Ammo reading to ``carry["ammo_readings"]``.

        ``fleet_ammo`` reads the grown ``_target_balance`` first and
        ``config.target_balance`` as the fallback, and a refused target appends
        no reading.
        """
        live_target = totals.money(getattr(bot, "_target_balance", 0.0), *AMMO_TOTALS)
        try:
            configured = totals.money(
                getattr(bot.config, "target_balance", 0.0), *AMMO_TOTALS
            )
        except Exception as _cfg_exc:  # noqa: BLE001 - one bot, not the fleet
            totals.unreadable.update(AMMO_TOTALS)
            logger.warning(
                "Fleet Ammo total: bot %s's target balance setting could not "
                "be read (%s). The AMMO column is marked unreadable.",
                getattr(bot, "bot_id", "?"),
                _cfg_exc,
            )
            return
        if live_target is None or configured is None:
            return
        carry["ammo_readings"].append((position_usd, live_target, configured))

    def get_aggregate_stats(self) -> dict:
        """Compute totals across all bots for the main dashboard.

        Every stored figure is admitted through ``FleetTotals`` before it is
        summed, and each total one bot's refused figure left out is named under
        ``UNREADABLE_TOTALS_KEY``.
        """
        totals = FleetTotals()
        carry: dict = {
            "pnl": 0.0,
            "trades": 0,
            "running": 0,
            "errored": 0,
            "scrummed": 0.0,
            "folded": 0.0,
            # YTD sums come from exchange fills via ScrummingBot.sync_ytd_trade_count.
            "scrummed_ytd": 0.0,
            "folded_ytd": 0.0,
            "errors_lifetime": 0,
            # Exchange-pulled, not the synthetic stats.realised_pnl accumulator.
            "realized_exchange": 0.0,
            "unrealized_exchange": 0.0,
            "fees_exchange": 0.0,
            "fresh_bots": 0,
            "complete_history_bots": 0,
            # Max across bots: one shared wallet.
            "wallet_cash": 0.0,
            "position_value": 0.0,
            "mature_usd": 0.0,
            "mature_positions": 0,
            "ammo_readings": [],
        }

        for bot in self._bots.values():
            self._read_one_bot(bot, totals, carry)

        total_pnl = carry["pnl"]
        total_trades = carry["trades"]
        running = carry["running"]
        errored = carry["errored"]
        total_scrummed = carry["scrummed"]
        total_folded = carry["folded"]
        total_scrummed_ytd = carry["scrummed_ytd"]
        total_folded_ytd = carry["folded_ytd"]
        total_errors_lifetime = carry["errors_lifetime"]
        total_realized_exchange = carry["realized_exchange"]
        total_unrealized_exchange = carry["unrealized_exchange"]
        total_fees_exchange = carry["fees_exchange"]
        bots_with_fresh_exchange_data = carry["fresh_bots"]
        bots_with_complete_fill_history = carry["complete_history_bots"]
        wallet_cash_usd = carry["wallet_cash"]
        crypto_position_value_usd = carry["position_value"]
        total_mature_exchange = carry["mature_usd"]
        mature_positions = carry["mature_positions"]

        ammo = fleet_ammo(carry["ammo_readings"])
        total_accrued_usd = fleet_accrued_usd(self._bots.values(), totals.unreadable)
        unreadable_totals = sorted(totals.unreadable)
        self._log_unreadable_totals(unreadable_totals)
        return {
            "total_bots": len(self._bots),
            "running": running,
            "errored": errored,  # CURRENT-state bots in ERROR
            "total_errors_lifetime": total_errors_lifetime,  # CUMULATIVE error count
            "total_realized_exchange": round(total_realized_exchange, 4),
            "total_unrealized_exchange": round(total_unrealized_exchange, 4),
            "total_fees_exchange": round(total_fees_exchange, 4),
            # `SpendableProfitsWidget` renders this as mature; it is absent,
            # not zero, while bots_with_fresh_exchange_data is 0.
            "total_mature_exchange": round(total_mature_exchange, 4),
            "mature_positions": mature_positions,
            "bots_with_fresh_exchange_data": bots_with_fresh_exchange_data,
            # False while any answered bot's fill history was cut short, so the
            # realised sum is never drawn from part of a history.
            "realised_history_complete": (
                bots_with_fresh_exchange_data > 0
                and bots_with_complete_fill_history == bots_with_fresh_exchange_data
            ),
            # `SpendableProfitsWidget` renders these two as spendable and locked.
            "wallet_cash_usd": round(wallet_cash_usd, 4),
            "crypto_position_value_usd": round(crypto_position_value_usd, 4),
            "total_account_value_usd": round(
                wallet_cash_usd + crypto_position_value_usd, 4
            ),
            "total_realised_pnl": round(total_pnl, 4),
            # The header strip's AMMO column draws this: each bot's Ammo
            # WITHOUT its sign, as the bot list's Ammo column draws it, so a
            # bot above target cannot cancel one below.
            "total_target_delta_usd": ammo["total_target_delta_usd"],
            # The header strip's ACCUMULATED column draws this sum.
            "total_accrued_usd": total_accrued_usd,
            "bots_scrum_territory": ammo["bots_scrum_territory"],
            "bots_fold_territory": ammo["bots_fold_territory"],
            "total_trades": total_trades,
            # Falls back to the platform-run accumulator when the YTD sum
            # is zero, so a fresh install is not blank.
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
            # Every total above that a bot's unreadable figure left out. The
            # header strip draws a dash for each one it names.
            UNREADABLE_TOTALS_KEY: unreadable_totals,
        }
