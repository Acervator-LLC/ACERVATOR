"""Bot registry for BotManager: admission, removal, lookup and lineage queries."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from ..bot_container import BotContainer

logger = logging.getLogger("acervator.bot")


class BotRegistryMixin:
    """The ``_bots`` dict ``BotManager`` composes in, and every read of it."""

    # Annotations only; BotManager binds these at runtime and creates no attribute here.
    _boot_state_records: dict
    _bots: dict
    _bus: Any
    _capital_registry: Any
    _connector: Any
    _data_pool: Any
    _dispatch_bootstrap: Callable[..., None]
    _reservation_usd_and_mode: Callable[..., tuple]
    _restore_ledger: dict
    _smart_wire_mgr: Any
    _state_manager: Any
    _usd_per_base_for: Callable[..., Any]
    _volume_guard: Any

    def register(self, bot: BotContainer) -> tuple[bool, "Optional[str]"]:
        """Add ``bot`` to ``_bots`` and return ``(granted, refusal_reason)``.

        A wired ``_capital_registry`` is asked for a reservation first, and a
        refusal returns ``(False, reason)`` without adding the bot;
        ``main_window`` reads that reason and logs it. When ``_connector`` is
        already attached, ``_dispatch_bootstrap`` runs the bot's live pull so
        its holdings are not 0 until the first tick.
        """
        if self._capital_registry is None:
            # set_capital_registry has no caller, so every admission takes this
            # branch and request_reservation is never asked.
            logger.warning(
                "Bot %s was added WITHOUT a capital reservation: no capital "
                "registry is attached to the bot manager, so its $%.2f "
                "allocation is not held aside and another bot may claim it.",
                bot.bot_id,
                self._reservation_usd_and_mode(bot)[0],
            )
        else:
            try:
                usd_amount, mode_str = self._reservation_usd_and_mode(bot)
                if usd_amount > 0:
                    rate = self._usd_per_base_for(
                        bot.config.exchange_id, bot.config.base_currency
                    )
                    if rate is None:
                        # No rate means the claim cannot be sized, so the bot
                        # is kept and no claim is written.
                        logger.warning(
                            "Bot %s was added WITHOUT a capital "
                            "reservation: no %s price is available, so "
                            "how much %s its $%.2f allocation comes to "
                            "cannot be worked out. Its money is not "
                            "held aside, so another bot may claim it.",
                            bot.bot_id,
                            bot.config.base_currency,
                            bot.config.base_currency,
                            usd_amount,
                        )
                    else:
                        granted, reason, _ = self._capital_registry.request_reservation(
                            bot_id=bot.bot_id,
                            exchange_id=bot.config.exchange_id,
                            base_currency=bot.config.base_currency,
                            usd_amount=usd_amount,
                            current_rate_usd_per_base=rate,
                            bot_mode=mode_str,
                        )
                        if not granted:
                            self._bus.emit(
                                "bot.register_refused",
                                bot_id=bot.bot_id,
                                reason=reason or "CapitalRegistry refused",
                            )
                            return False, reason
            except Exception as _reg_exc:
                # A CapitalRegistry failure logs and falls through; it never
                # blocks registration.
                logger.warning(
                    "v3.20.71 CapitalRegistry consult failed for bot %s; "
                    "proceeding without reservation: %s",
                    bot.bot_id,
                    _reg_exc,
                )

        self._bots[bot.bot_id] = bot
        if self._volume_guard:
            bot._volume_guard = self._volume_guard
        if hasattr(self, "_data_pool") and self._data_pool:
            bot._data_pool = self._data_pool
        # attach_bot fills _bot_refs; register_bot fills _ledgers, where the
        # wired_in and wired_out totals land.
        try:
            self._smart_wire_mgr.attach_bot(bot.bot_id, bot)
            if hasattr(bot, "set_smart_wire"):
                bot.set_smart_wire(self._smart_wire_mgr)
            try:
                _existing_ledgers = getattr(self._smart_wire_mgr, "_ledgers", {}) or {}
                if bot.bot_id not in _existing_ledgers:
                    _seed = float(getattr(bot.config, "target_balance", 0) or 0)
                    _asset = str(
                        getattr(bot.config, "target_asset", "")
                        or getattr(bot.config, "symbol", "")
                    )
                    self._smart_wire_mgr.register_bot(
                        bot.bot_id, _asset, seed_amount=_seed
                    )
            except Exception as _reg_exc:
                logger.warning(
                    "Bot %s SmartWire ledger register failed: %s", bot.bot_id, _reg_exc
                )
        except Exception as _sw_exc:
            logger.warning("Bot %s SmartWire attach failed: %s", bot.bot_id, _sw_exc)
        # set_bot_manager gives the bot the back-reference it needs to
        # attribute holdings per base currency.
        if hasattr(bot, "set_bot_manager"):
            try:
                bot.set_bot_manager(self)
            except Exception as _bm_exc:
                logger.warning("Bot %s set_bot_manager failed: %s", bot.bot_id, _bm_exc)
        # get_scout returns the process-wide MarketPairsScout, which lists
        # every pair trading the bot's target asset.
        if hasattr(bot, "set_market_pairs_scout"):
            try:
                from ...exchange.market_pairs_scout import get_scout

                bot.set_market_pairs_scout(get_scout())
            except Exception as _scout_exc:
                logger.warning(
                    "Bot %s set_market_pairs_scout failed: %s", bot.bot_id, _scout_exc
                )
        if self._connector:
            self._connector.add_scan_symbol(bot.config.symbol)
            logger.debug("Registered %s for trade history scanning", bot.config.symbol)
            if not getattr(bot, "exchange", None):
                try:
                    bot.exchange = self._connector
                except Exception as _attach_exc:
                    # A frozen bot record refuses the attribute write, and
                    # registration still succeeds.
                    logger.error(
                        "Bot %s would not accept the exchange connector "
                        "(%s). It has no connector and cannot trade "
                        "until one is attached.",
                        getattr(bot, "bot_id", "<unknown bot>"),
                        _attach_exc,
                    )
            if hasattr(bot, "bootstrap_exchange_state"):
                self._dispatch_bootstrap(bot, "register")
        self._bus.emit("bot.registered", bot_id=bot.bot_id)
        return True, None

    def unregister(self, bot_id: str) -> None:
        """Remove ``bot_id`` from ``_bots``, from disk, and from every linkage.

        A wired ``_capital_registry`` releases the bot's reservation so the
        freed USD is claimable again. Releasing an unknown ``bot_id`` is a
        no-op.
        """
        # These two pops clear caches only; save_state reads the file, so
        # delete_bot below is what removes the record.
        self._restore_ledger.pop(str(bot_id), None)
        self._boot_state_records.pop(str(bot_id), None)
        if self._state_manager is not None:
            try:
                self._state_manager.delete_bot(str(bot_id))
            except Exception as exc:  # noqa: BLE001 - teardown continues
                logger.error(
                    "unregister(%s): disk delete failed (%s) — the record "
                    "remains on disk and will be carried forward",
                    bot_id,
                    exc,
                )
        # Release the claim before the bot leaves _bots, so it cannot outlive
        # its place there.
        if self._capital_registry is not None:
            try:
                self._capital_registry.release_reservation(bot_id=bot_id)
            except Exception as _rel_exc:
                logger.warning(
                    "v3.20.71 CapitalRegistry release failed for bot %s: %s",
                    bot_id,
                    _rel_exc,
                )
        bot = self._bots.pop(bot_id, None)
        if bot and self._connector:
            still_used = any(
                b.config.symbol == bot.config.symbol for b in self._bots.values()
            )
            if not still_used:
                self._connector.remove_scan_symbol(bot.config.symbol)
        # detach_bot drops the bot ref, its ledger, and every wire naming it
        # on either side.
        try:
            self._smart_wire_mgr.detach_bot(bot_id)
        except Exception as _sw_exc:
            logger.warning("Bot %s SmartWire detach failed: %s", bot_id, _sw_exc)
        self._bus.emit("bot.unregistered", bot_id=bot_id)

    def get_trade_history(self, symbol: str):
        """Return the connector's latest HistoryAnalysis for ``symbol``, else None."""
        if self._connector:
            return self._connector.get_history(symbol)
        return None

    def refresh_trade_history(self, symbol: str | None = None):
        """Rescan trade history for ``symbol``, or every registered symbol when None."""
        if self._connector:
            self._connector.refresh_history(symbol)
        else:
            logger.warning("refresh_trade_history: no connector attached")

    def get_bot(self, bot_id: str) -> Optional[BotContainer]:
        return self._bots.get(bot_id)

    def list_parent_bot_candidates_for_base_currency(
        self, base_currency: object, *, exchange_id: object
    ) -> list[tuple[str, BotContainer]]:
        """Return every ScrummingBot on this exchange holding this currency.

        The answer is ``(bot_id, bot)`` pairs in registration order, matched on
        ``config.target_asset`` and ``config.exchange_id``.
        ``find_parent_bot_for_base_currency`` derives its single answer from
        this list, and ``main_window`` reads the length to tell an empty list
        from several before it creates an Extractor. Matching strips spaces and
        ignores case; a non-string argument returns an empty list. Nothing is
        refused and nothing is logged here.
        """
        if not isinstance(base_currency, str):
            return []
        wanted = base_currency.strip().upper()
        if not wanted:
            return []
        # scrumming_bot imports bot_container, which imports this module, so a
        # top-level import would be circular.
        from ..scrumming_bot import ScrummingBot

        holders: list[tuple[str, BotContainer]] = []
        for bot_id, bot in self._bots.items():
            if not isinstance(bot, ScrummingBot):
                continue
            if (
                getattr(getattr(bot, "config", None), "exchange_id", None)
                != exchange_id
            ):
                continue
            held = getattr(getattr(bot, "config", None), "target_asset", "")
            if not isinstance(held, str):
                continue
            if held.strip().upper() == wanted:
                holders.append((bot_id, bot))
        return holders

    def find_parent_bot_for_base_currency(
        self, base_currency: Any, *, exchange_id: Any
    ) -> Optional[BotContainer]:
        """Return the one ScrummingBot that holds this currency, or None.

        ``ScrummingBot.apply_extractor_tranche_return`` raises that bot's
        target balance by the returned base currency, and this names the bot to
        call it on. ``exchange_id`` is keyword-only with no default, so a
        parent on another exchange is never matched. An empty ``holders`` list
        returns None. Two or more returns None and logs the refusal, because
        nothing here can tell which bot earned the return. An ExtractorBot is
        never a parent: it is not a ScrummingBot.
        """
        holders = self.list_parent_bot_candidates_for_base_currency(
            base_currency, exchange_id=exchange_id
        )
        wanted = (
            base_currency.strip().upper()
            if isinstance(base_currency, str)
            else base_currency
        )
        if len(holders) == 1:
            return holders[0][1]
        if len(holders) > 1:
            logger.warning(
                "extractor parent lookup REFUSED %s: %d Scrumming Bots "
                "hold it (%s). Returning nothing rather than guessing an "
                "owner — the returned base currency stays where it is.",
                wanted,
                len(holders),
                ", ".join(bid for bid, _ in holders),
            )
        return None

    def list_extractor_children_for_parent(
        self, parent: object
    ) -> list[tuple[str, object]]:
        """Return the ExtractorBots that spend this ScrummingBot's asset.

        The answer is ``(bot_id, bot)`` pairs sorted by bot id, so the listing
        does not reshuffle between reads. A bot is a child when it is an
        ExtractorBot on the same ``exchange_id`` whose ``base_currency`` is the
        parent's ``target_asset`` — the same match
        ``list_parent_bot_candidates_for_base_currency`` makes, read backwards.
        Several children are a valid answer and are not refused. Anything that
        is not a ScrummingBot with a text ``target_asset`` returns an empty
        list.
        """
        # scrumming_bot and extractor_bot both import bot_container, which
        # imports this module, so a top-level import would be circular.
        from ..scrumming_bot import ScrummingBot
        from ..extractor_bot import ExtractorBot

        if not isinstance(parent, ScrummingBot):
            return []
        p_cfg = getattr(parent, "config", None)
        held = getattr(p_cfg, "target_asset", "")
        if not isinstance(held, str):
            return []
        wanted = held.strip().upper()
        if not wanted:
            return []
        p_exchange = getattr(p_cfg, "exchange_id", None)
        children: list[tuple[str, object]] = []
        for bot_id, bot in self._bots.items():
            if not isinstance(bot, ExtractorBot):
                continue
            c_cfg = getattr(bot, "config", None)
            if getattr(c_cfg, "exchange_id", None) != p_exchange:
                continue
            spends = getattr(c_cfg, "base_currency", "")
            if not isinstance(spends, str):
                continue
            if spends.strip().upper() == wanted:
                children.append((bot_id, bot))
        children.sort(key=lambda pair: pair[0])
        return children

    def list_bots(self) -> list[dict]:
        """Return status snapshots for all registered bots."""
        return [bot.get_status() for bot in self._bots.values()]

    def list_bots_by_exchange(self, exchange_id: str) -> list[dict]:
        """Filter bots by exchange."""
        return [
            bot.get_status()
            for bot in self._bots.values()
            if bot.config.exchange_id == exchange_id
        ]
