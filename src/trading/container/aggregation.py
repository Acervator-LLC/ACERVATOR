"""Fleet-wide sums for BotManager.

Two of them: what the other bots have claimed of a shared pool, and the
dashboard aggregate.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional

from .config import DOLLAR_PEGGED_CURRENCIES, BotState

logger = logging.getLogger("acervator.bot")


class FleetAggregationMixin:
    """Aggregation half of ``BotManager``: totals computed across ``_bots``.

    Composed into ``BotManager``; ``self`` is the manager instance.
    """

    # Annotation only, supplied by BotManager at runtime: no attribute is
    # created and the runtime base stays `object`.
    _bots: dict

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

    def get_aggregate_stats(self) -> dict:
        """Compute totals across all bots for the main dashboard."""
        total_pnl = 0.0
        total_trades = 0
        running = 0
        errored = 0
        total_scrummed = 0.0
        total_folded = 0.0
        # YTD sums come from exchange fills via ScrummingBot.sync_ytd_trade_count.
        total_scrummed_ytd = 0.0
        total_folded_ytd = 0.0
        total_errors_lifetime = 0  # cumulative across all bots
        # Exchange-pulled, not the synthetic stats.realised_pnl accumulator.
        total_realized_exchange = 0.0
        total_unrealized_exchange = 0.0
        total_fees_exchange = 0.0
        bots_with_fresh_exchange_data = 0
        wallet_cash_usd = 0.0  # max across bots (shared wallet)
        crypto_position_value_usd = 0.0  # sum of per-bot position values

        for bot in self._bots.values():
            total_pnl += bot.stats.realised_pnl
            total_trades += bot.stats.total_trades
            total_scrummed += float(
                getattr(bot.stats, "total_scrummed_usd", 0.0) or 0.0
            )
            total_folded += float(getattr(bot.stats, "total_folded_usd", 0.0) or 0.0)
            total_scrummed_ytd += float(
                getattr(bot.stats, "ytd_scrummed_usd", 0.0) or 0.0
            )
            total_folded_ytd += float(getattr(bot.stats, "ytd_folded_usd", 0.0) or 0.0)
            total_errors_lifetime += int(getattr(bot.stats, "total_errors", 0) or 0)
            _re = float(getattr(bot.stats, "realized_pnl_exchange", 0.0) or 0.0)
            _ue = float(getattr(bot.stats, "unrealised_pnl", 0.0) or 0.0)
            _fe = float(getattr(bot.stats, "fees_paid_exchange", 0.0) or 0.0)
            _fresh_ts = float(getattr(bot.stats, "exchange_data_fresh_ts", 0.0) or 0.0)
            total_realized_exchange += _re
            total_unrealized_exchange += _ue
            total_fees_exchange += _fe
            if _fresh_ts > 0:
                bots_with_fresh_exchange_data += 1
            # Freshest non-zero cash balance wins.
            _bot_cash = float(getattr(bot.stats, "cash_balance_usd", 0.0) or 0.0)
            if _bot_cash > wallet_cash_usd:
                wallet_cash_usd = _bot_cash
            # stats.position_value and stats.current_price are written at different moments.
            _bot_pos_val = float(getattr(bot.stats, "position_value", 0.0) or 0.0)
            try:
                _h = float(getattr(bot, "_current_holdings", 0.0) or 0.0)
                _p = float(getattr(bot.stats, "current_price", 0.0) or 0.0)
                _q = float(getattr(bot, "_quote_to_usd", 1.0) or 1.0)
                # A missing holding or price keeps the cached value rather
                # than reporting $0 against a real position.
                if _h > 0 and _p > 0:
                    _bot_pos_val = _h * _p * _q
            except Exception as _pv_exc:  # noqa: BLE001 - aggregate must not raise
                logger.debug(
                    "aggregate: position recompute failed for %s (%s); "
                    "using the cached value",
                    getattr(bot, "bot_id", "?"),
                    _pv_exc,
                )
            crypto_position_value_usd += _bot_pos_val
            if bot.state == BotState.RUNNING:
                running += 1
            if bot.state == BotState.ERROR:
                errored += 1

        return {
            "total_bots": len(self._bots),
            "running": running,
            "errored": errored,  # CURRENT-state bots in ERROR
            "total_errors_lifetime": total_errors_lifetime,  # CUMULATIVE error count
            "total_realized_exchange": round(total_realized_exchange, 4),
            "total_unrealized_exchange": round(total_unrealized_exchange, 4),
            "total_fees_exchange": round(total_fees_exchange, 4),
            "bots_with_fresh_exchange_data": bots_with_fresh_exchange_data,
            # `SpendableProfitsWidget` renders these two as spendable and locked.
            "wallet_cash_usd": round(wallet_cash_usd, 4),
            "crypto_position_value_usd": round(crypto_position_value_usd, 4),
            "total_account_value_usd": round(
                wallet_cash_usd + crypto_position_value_usd, 4
            ),
            "total_realised_pnl": round(total_pnl, 4),
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
        }
