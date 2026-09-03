"""Fleet-wide sums for BotManager: sibling claims and the dashboard aggregate."""

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

    # Supplied by BotManager at runtime; declared so a type checker
    # can resolve them. Annotations only: no attribute is created and
    # the runtime base stays `object`.
    _bots: dict

    # ------------------------------------------------------------------
    # v3.15.56 — multi-base attribution support
    # ------------------------------------------------------------------
    def has_sibling_target_bots(self, bot_id: str, target_asset: str) -> bool:
        """Return True if any OTHER registered bot has the same target
        asset (regardless of base currency).

        Used by ScrummingBot.tick init handshake to decide whether
        ``exchange.get_balance(target_asset).total`` represents this
        bot's holdings (single-bot scenario, trust it) or a shared pool
        across multiple bots (multi-base scenario, do NOT trust it —
        the bot must use its own _main_lots as the authoritative
        attribution of "what THIS bot bought").

        Operator directive 2026-04-25:
          "if I have my $450 USD RAVE bot running, creating a RAVE
           USDC bot at $50 causes the second bot to want to sell the
           majority of the position because it sees what it thinks is
           a surplus rather than just considering the fact that it
           has $50 USDC that it has failed to convert to RAVE."

        The fix: detect the multi-bot scenario at this layer; the
        downstream bot then refuses to inherit exchange total as its
        own holdings. Even paused/idle sibling bots count — restarting
        Bot A must not surprise Bot B.
        """
        target_norm = (target_asset or "").upper()
        for other_id, other_bot in self._bots.items():
            if other_id == bot_id:
                continue
            try:
                other_target = (other_bot.config.target_asset or "").upper()
            except Exception as _read_exc:
                # Skipping a bot whose settings cannot be read is the
                # right thing to do — one broken record must not stop
                # the check. But it used to happen in silence, so a bot
                # that quietly dropped out of every sibling check looked
                # exactly like a bot that was never there. Now it says
                # which bot it dropped and why.
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
        """Sum the tracked _main_lots units across all sibling bots
        with the same target_asset (excluding the caller).

        Used by reconciliation in multi-base mode: this bot's
        _current_holdings should never exceed
        ``exchange_total - sum_sibling_tracked_units``. If it does,
        a sibling bot has lost track of some of its inventory.
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
                # Same reason as the sibling check above: skip the
                # unreadable bot, but say so. A silent skip here makes
                # the running total look smaller than it is, and the
                # total is what tells a bot how much of the coin on the
                # exchange is already spoken for.
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
                # One unreadable purchase record stops this bot's
                # remaining records from being added. Whatever was
                # already added stays in the total. Say so, because the
                # total that comes out is short by an unknown amount
                # and the caller cannot tell from the number alone.
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

        The answer is in units of the pool's currency. Returns the
        claim and an empty reason when it can be worked out, or
        nothing and the reason when it cannot.

        Nothing is never the same as zero here. Zero means this bot
        claims none of the pool. Nothing means we do not know what it
        claims, and a bot that does not know must not guess low.

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
        """How many dollars one unit of the pool currency is worth,
        taken from the other bot's own cached rate.

        Returns the rate and an empty reason, or nothing and the
        reason. When the pool holds a coin that is meant to be worth
        one dollar, one is the true rate and is used whenever the
        cached rate is unusable.

        This used to fall back to one for EVERY pool. On a Bitcoin
        pool that read a bot's $1,000 allocation as a claim on 1,000
        Bitcoin.
        """
        raw: Any = None
        rate: Optional[float] = None
        try:
            # Inside the guard on purpose. A missing rate is not the
            # only way this read fails: reading it can raise, and a
            # default value does not catch that.
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
        """Sum of base-currency (quote-currency) claims by OTHER bots
        on the same exchange.

        Returns nothing when any other bot in the pool cannot be read.
        A total that quietly leaves one bot's claim out is LOWER than
        the truth, and a low total tells the asking bot that money is
        free when another bot has already claimed it. That is how two
        bots come to spend the same money. There is no safe number to
        hand back in that case, so this hands back nothing and writes
        one warning naming every bot it could not read, the reason for
        each, and the incomplete total, so the size of the gap is on
        the record.

        A caller that gets nothing must refuse to act. It must not
        read nothing as zero claims. Zero is the most dangerous answer
        of all, because zero says the whole pool is free.

        A "claim" is operator-allocated capital that a sibling bot OWNS
        even if it's not actively deployed. For:

          * **ScrummingBots** whose ``config.base_currency == currency``:
            their ``target_balance`` is the claim (the USD-equivalent
            target the bot's accumulation strategy is sized to).
            Converted to base-currency units via the sibling's own
            cached ``_quote_to_usd`` rate; ``_quote_to_usd`` represents
            "1 unit of quote currency = N USD", so ``USD / _quote_to_usd``
            yields the equivalent quote-currency units. A pool of a
            coin that is meant to be worth one dollar needs no rate.
            Any other pool with no usable rate counts as unreadable.
          * **ExtractorBots** whose ``config.base_currency == currency``:
            their ``_chunk_size_base`` (operator-allocated base-unit
            chunk). Forward-compatible — the Extractor class is
            slated to ship in v3.19.0 (per the Extractor design doc
            §13a). Until then this branch is dormant via ``getattr``.

        When every bot in the pool can be read, returns the sum in
        **base-currency (quote) units**. The caller subtracts that from
        the raw exchange balance to get its claim-aware free.

        Includes:
          - All sibling bots regardless of run state. A paused bot
            still owns its allocation; restarting a paused sibling must
            not surprise the active bot by silently un-reserving its
            funds.

        Excludes:
          - The querying bot itself (its own claim is implicit).
          - Bots on different exchanges (different fund pools).

        Operator directive 2026-05-20 (Extractor design doc §13a):

          > "It will also be important for the Scrumming Bots to
          >  detect base currency balance overlap as excess and try to
          >  sell what is assigned to an Extractor."

        v3.18.18 ships this helper standalone (decoupled from Extractor
        build per Tier-1 review of the Extractor design doc) so the
        helper's regression coverage stays independent of Extractor
        completion. The helper also closes a multi-ScrummingBot
        over-allocation risk — two ScrummingBots on the same exchange
        with overlapping base_currency (e.g. both on USD) could
        previously each see the entire USD pool as their own free
        balance; with this helper, each sees only its claim-aware
        slice.
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
                # This bot may or may not be in the pool. It cannot be
                # skipped on the strength of a failed read: if it IS in
                # the pool, skipping it hides its claim.
                unread.append(
                    f"{other_id} (its settings could not be read: " f"{_cfg_exc})"
                )
                continue
            if not same_exchange or other_base != currency_norm:
                # A different exchange or a different currency is a
                # different pool of money. Not a claim on this one.
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

    # -- Aggregated stats for main window ------------------------------
    def get_aggregate_stats(self) -> dict:
        """Compute totals across all bots for the main dashboard.

        v3.15.50 — adds total_scrummed_usd + total_folded_usd as
        platform high-score counters per operator directive
        2026-04-24: "How about display total scrummed and total
        folded. Like two high scores for the platform run. Just add
        it all up from all running bots."
        """
        total_pnl = 0.0
        total_trades = 0
        running = 0
        errored = 0
        total_scrummed = 0.0
        total_folded = 0.0
        # v3.23.60 — YTD scrum/fold totals pulled from exchange fills
        # (see ScrummingBot.sync_ytd_trade_count). When any bot has
        # exchange_data_fresh_ts > 0 the dashboard prefers this over
        # the platform-run accumulator; the two run in parallel so
        # bots that haven't yet completed a sync still contribute
        # via the lifetime counters.
        total_scrummed_ytd = 0.0
        total_folded_ytd = 0.0
        total_errors_lifetime = 0  # v3.16.46 — cumulative across all bots
        # v3.16.46 — exchange-pulled aggregates (realized P/L from
        # actual trade history, fees paid, etc.). When all bots have
        # refreshed at least once, this represents Coinbase-truth
        # values vs the synthetic stats.realised_pnl accumulator.
        total_realized_exchange = 0.0
        total_unrealized_exchange = 0.0
        total_fees_exchange = 0.0
        bots_with_fresh_exchange_data = 0
        # v3.16.48 — wallet cash + crypto position aggregates pulled
        # from exchange. Operator directive: "Pull the data and
        # display it. Spendable balance is my cash."
        wallet_cash_usd = 0.0  # max across bots (shared wallet)
        crypto_position_value_usd = 0.0  # sum of per-bot position values

        for bot in self._bots.values():
            total_pnl += bot.stats.realised_pnl
            total_trades += bot.stats.total_trades
            total_scrummed += float(
                getattr(bot.stats, "total_scrummed_usd", 0.0) or 0.0
            )
            total_folded += float(getattr(bot.stats, "total_folded_usd", 0.0) or 0.0)
            # v3.23.60 — YTD from exchange sync
            total_scrummed_ytd += float(
                getattr(bot.stats, "ytd_scrummed_usd", 0.0) or 0.0
            )
            total_folded_ytd += float(getattr(bot.stats, "ytd_folded_usd", 0.0) or 0.0)
            total_errors_lifetime += int(getattr(bot.stats, "total_errors", 0) or 0)
            # v3.16.46 — exchange-pulled aggregates
            _re = float(getattr(bot.stats, "realized_pnl_exchange", 0.0) or 0.0)
            _ue = float(getattr(bot.stats, "unrealised_pnl", 0.0) or 0.0)
            _fe = float(getattr(bot.stats, "fees_paid_exchange", 0.0) or 0.0)
            _fresh_ts = float(getattr(bot.stats, "exchange_data_fresh_ts", 0.0) or 0.0)
            total_realized_exchange += _re
            total_unrealized_exchange += _ue
            total_fees_exchange += _fe
            if _fresh_ts > 0:
                bots_with_fresh_exchange_data += 1
            # v3.16.48 — wallet cash: shared across bots, take max
            # (freshest non-zero value wins). Crypto position: sum
            # per-bot position values (each bot owns its own asset).
            _bot_cash = float(getattr(bot.stats, "cash_balance_usd", 0.0) or 0.0)
            if _bot_cash > wallet_cash_usd:
                wallet_cash_usd = _bot_cash
            # v3.24.55 — recompute rather than trusting the cached
            # field, matching what the Ammo cell and the manual-fire
            # engine both already do.
            #
            # `stats.position_value` and `stats.current_price` are
            # written at different moments in the tick, so the cached
            # product lags whenever price moved after the last write.
            # Measured 2026-08-06 by
            # dev_harness/harness/reconcile_position_values.py: 11 of 35 bots
            # diverged more than 1% from holdings x price, worst
            # ORCA/USD at 11.53%, and the fleet total understated the
            # position by $35.46 against $3,317.16.
            #
            # C10 fixed this for the per-bot Ammo and
            # `ExecutionEngineMixin._execute_manual_rebalance`
            # (`src/trading/scrumming/execution.py`) was already correct
            # for manual fire.
            # This was the last consumer still summing the stale value,
            # and it is the one the headline portfolio figure is built
            # from.
            _bot_pos_val = float(getattr(bot.stats, "position_value", 0.0) or 0.0)
            try:
                _h = float(getattr(bot, "_current_holdings", 0.0) or 0.0)
                _p = float(getattr(bot.stats, "current_price", 0.0) or 0.0)
                _q = float(getattr(bot, "_quote_to_usd", 1.0) or 1.0)
                if _h > 0 and _p > 0:
                    # Both inputs present: the recomputed value is the
                    # fresher of the two by construction. Falls through
                    # to the cached value otherwise rather than
                    # reporting $0 for a real position -- an empty
                    # portfolio is a worse lie than a slightly stale one.
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
            # v3.16.46 — exchange-pulled position health aggregates
            "total_realized_exchange": round(total_realized_exchange, 4),
            "total_unrealized_exchange": round(total_unrealized_exchange, 4),
            "total_fees_exchange": round(total_fees_exchange, 4),
            "bots_with_fresh_exchange_data": bots_with_fresh_exchange_data,
            # v3.16.48 — direct exchange-pulled wallet cash + crypto
            # value. These are the values the SpendableWidget displays
            # (replacing the prior synthetic computation).
            "wallet_cash_usd": round(wallet_cash_usd, 4),
            "crypto_position_value_usd": round(crypto_position_value_usd, 4),
            "total_account_value_usd": round(
                wallet_cash_usd + crypto_position_value_usd, 4
            ),
            "total_realised_pnl": round(total_pnl, 4),
            "total_trades": total_trades,
            # v3.23.60 — dashboard prefers the YTD sums when any bot
            # has completed a sync (>0). Falls back to the platform-
            # run accumulators otherwise so fresh installs / new
            # bots aren't blank.
            "total_scrummed_usd": round(
                total_scrummed_ytd if total_scrummed_ytd > 0 else total_scrummed, 4
            ),
            "total_folded_usd": round(
                total_folded_ytd if total_folded_ytd > 0 else total_folded, 4
            ),
            # Also expose raw YTD + lifetime separately for callers
            # that want to distinguish them.
            "total_scrummed_usd_ytd": round(total_scrummed_ytd, 4),
            "total_folded_usd_ytd": round(total_folded_ytd, 4),
            "total_scrummed_usd_lifetime": round(total_scrummed, 4),
            "total_folded_usd_lifetime": round(total_folded, 4),
        }
