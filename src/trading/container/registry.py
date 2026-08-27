"""Bot registry for BotManager: admission, removal, lookup and lineage queries."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from ..bot_container import BotContainer

logger = logging.getLogger("acervator.bot")


class BotRegistryMixin:
    """Registry half of ``BotManager``: the ``_bots`` dict and every read of it.

    Composed into ``BotManager``; ``self`` is the manager instance.
    """

    # Supplied by BotManager at runtime; declared so a type checker
    # can resolve them. Annotations only: no attribute is created and
    # the runtime base stays `object`.
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
        """Add a bot to the manager's registry.

        Returns ``(granted, refusal_reason)``. On success, the bot is
        added and ``(True, None)`` is returned. On capital-registry
        refusal (Q3 over-allocation), the bot is NOT added and
        ``(False, reason)`` is returned. Existing callers that ignore
        the return value still work — they just miss the refusal path.

        MEM-256 (Session 26): when the connector is already attached, also
        fire the bootstrap_exchange_state live-pull for this newly
        registered bot. Without this, bots added AFTER set_connector has
        already run (the common case on startup — restore_bots_from_state
        registers bots after the connector is attached) would not get
        their bootstrap dispatch. Idle bots then show 0 holdings in the
        GUI until their first tick.

        MEM-417 (v3.20.71 Phase B-2): if a CapitalRegistry is wired,
        request_reservation is called BEFORE the bot is added. On
        refusal, an event ``bot.register_refused`` is emitted with
        ``bot_id`` and ``reason``; the wizard surfaces the reason to
        the operator.
        """
        # v3.20.71 — CapitalRegistry gate (Q3 refuse-outright)
        if self._capital_registry is not None:
            try:
                usd_amount, mode_str = self._reservation_usd_and_mode(bot)
                if usd_amount > 0:
                    rate = self._usd_per_base_for(
                        bot.config.exchange_id, bot.config.base_currency
                    )
                    if rate is None:
                        # No price means the claim cannot be sized. See
                        # _usd_per_base_for for why nothing is returned.
                        # A price outage must not delete a bot, so the
                        # bot is kept and no claim is written from a
                        # number nobody has. This lands on the same
                        # outcome as the fall-through below, which is
                        # what already happens when the registry cannot
                        # be consulted.
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
                # If the registry path crashes, log + fall through.
                # The registry is a safety layer, not a hard requirement —
                # never block bot creation on a registry bug.
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
        # Session 26 P1b — attach SmartWireManager to every new bot so
        # (a) source-side fold routing can find outgoing wires via the
        # manager, and (b) target-side apply_wire_income is reachable
        # from distribute_fold_profit via the attach_bot registry.
        #
        # v3.16.46 — Operator-flagged bug 2026-05-10: "Smart Wire has
        # never worked." Root cause: previously we called only
        # attach_bot (populates _bot_refs) but NEVER register_bot
        # (populates _ledgers). With empty _ledgers, the wired_in /
        # wired_out tracking that the Bot Swarm visibility tab reads
        # had nowhere to land — every bot showed $0.0000 forever.
        # Fix: also call register_bot here so the ledger entry exists
        # at the moment the bot is attached. seed_amount is the bot's
        # configured target_balance (the closest analogue to "starting
        # capital" we have at this point in the lifecycle).
        try:
            self._smart_wire_mgr.attach_bot(bot.bot_id, bot)
            if hasattr(bot, "set_smart_wire"):
                bot.set_smart_wire(self._smart_wire_mgr)
            # v3.16.46 — ensure ledger entry exists for this bot
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
        # v3.15.56 — give the bot a back-reference to this manager so it
        # can answer questions about siblings (multi-base attribution).
        # Operator directive 2026-04-25: a RAVE/USDC bot must NOT see
        # the RAVE/USD bot's accumulated RAVE as if it owned it.
        if hasattr(bot, "set_bot_manager"):
            try:
                bot.set_bot_manager(self)
            except Exception as _bm_exc:
                logger.warning("Bot %s set_bot_manager failed: %s", bot.bot_id, _bm_exc)
        # v3.23.47 — attach the process-wide MarketPairsScout so the
        # bot (and eventually the Bot Details Status tab) can see all
        # pairs trading its target asset. Read-only in this cascade.
        if hasattr(bot, "set_market_pairs_scout"):
            try:
                from ...exchange.market_pairs_scout import get_scout

                bot.set_market_pairs_scout(get_scout())
            except Exception as _scout_exc:
                logger.warning(
                    "Bot %s set_market_pairs_scout failed: %s", bot.bot_id, _scout_exc
                )
        # Register symbol for trade history scanning on next connect
        if self._connector:
            self._connector.add_scan_symbol(bot.config.symbol)
            logger.debug("Registered %s for trade history scanning", bot.config.symbol)
            # Ensure bot.exchange points to the connector (idempotent).
            if not getattr(bot, "exchange", None):
                try:
                    bot.exchange = self._connector
                except Exception as _attach_exc:
                    # Same as in set_connector: the bot may be a frozen
                    # record that refuses any attribute write, so
                    # registration must still succeed. But the bot ends
                    # up with no connector, the later read falls back to
                    # a default, and a bot with no connector cannot
                    # trade — so say which bot it was.
                    logger.error(
                        "Bot %s would not accept the exchange connector "
                        "(%s). It has no connector and cannot trade "
                        "until one is attached.",
                        getattr(bot, "bot_id", "<unknown bot>"),
                        _attach_exc,
                    )
            # MEM-256 — fire the bootstrap live-pull for this bot now.
            if hasattr(bot, "bootstrap_exchange_state"):
                self._dispatch_bootstrap(bot, "register")
        self._bus.emit("bot.registered", bot_id=bot.bot_id)
        return True, None

    def unregister(self, bot_id: str) -> None:
        """Remove a bot from the registry.

        v3.20.71 (MEM-417): if a CapitalRegistry is wired, the bot's
        reservation is released so the freed USD becomes available to
        sibling bots. Idempotent — releasing an unknown bot_id is a
        no-op."""
        # v3.24.35 (C01) — DELETE THE RECORD ON DISK, EXPLICITLY.
        #
        # This method used to touch no storage at all: no state manager,
        # no save call, no file access. A deleted bot disappeared from
        # bot_state.json only because the next save rebuilt the file
        # from RAM — deletion was a side effect of the very bug C01
        # fixes, which is also why it was never logged anywhere.
        #
        # Now that save_state carries unknown records forward, that
        # accident is gone and delete must be a positive act, or a
        # deleted bot returns on the next save.
        #
        # The two pops below are DIAGNOSTIC ONLY. An earlier comment
        # here claimed they were what protected an explicit delete;
        # they never were, and believing it is how this bug comes back.
        # The carry-forward reads the FILE, not these dicts.
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
        # v3.20.71 — release capital reservation before tearing down
        # other linkages (the bot's claim must not outlive its place
        # in the manager registry).
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
            # Only remove symbol if no other bot is trading it
            still_used = any(
                b.config.symbol == bot.config.symbol for b in self._bots.values()
            )
            if not still_used:
                self._connector.remove_scan_symbol(bot.config.symbol)
        # Session 26 P1b — clear bot from SmartWireManager (drops bot
        # ref + any wires that reference it on either side)
        try:
            self._smart_wire_mgr.detach_bot(bot_id)
        except Exception as _sw_exc:
            logger.warning("Bot %s SmartWire detach failed: %s", bot_id, _sw_exc)
        self._bus.emit("bot.unregistered", bot_id=bot_id)

    def get_trade_history(self, symbol: str):
        """
        Return the most recent HistoryAnalysis for a symbol.
        Returns None if no connector is set or history not yet available.
        """
        if self._connector:
            return self._connector.get_history(symbol)
        return None

    def refresh_trade_history(self, symbol: str | None = None):
        """
        Trigger a fresh trade history scan.  If symbol is None, refreshes
        all registered symbols.  Safe to call from GUI Refresh button.
        """
        if self._connector:
            self._connector.refresh_history(symbol)
        else:
            logger.warning("refresh_trade_history: no connector attached")

    def get_bot(self, bot_id: str) -> Optional[BotContainer]:
        return self._bots.get(bot_id)

    # ------------------------------------------------------------------
    # Extractor Tranche parent lookup
    # ------------------------------------------------------------------
    def list_parent_bot_candidates_for_base_currency(
        self, base_currency: object, *, exchange_id: object
    ) -> list[tuple[str, BotContainer]]:
        """Return the Scrumming Bots on this exchange holding a currency.

        The answer is ``(bot_id, bot)`` pairs, in registration order.
        Both arguments are taken as anything at all, because a caller
        can hand over whatever a saved config had in it; what is not
        text simply matches nothing.

        THIS IS THE MATCH ITSELF, AND IT IS THE ONLY COPY OF IT.
        `find_parent_bot_for_base_currency` answers a different
        question — "which bot gets the money" — and answers nothing
        unless exactly one bot holds the currency. That single answer is
        all a payment needs, but it cannot tell an empty set of holders
        from a crowded one.

        A caller that must tell those two apart needs the count. The bot
        creation wizard is one: it refuses to create an Extractor in
        both cases, and the operator's remedy is opposite in each
        (create a holder, versus reduce two holders to one). Counting
        with a second copy of the match is how the two answers would
        drift apart, so the list is what is computed here and the single
        answer is derived from it.

        NOTHING IS REFUSED HERE AND NOTHING IS LOGGED. A list of two is
        a fact about the books, not a decision about money. The refusal,
        and the record of it, stay with the lookup that moves money.

        The rules are the lookup's rules, because this is where they are
        written: Scrumming Bots only, same exchange only, and the
        currency matched with surrounding spaces removed and without
        regard to upper or lower case. Anything that is not text matches
        nothing and returns an empty list.
        """
        if not isinstance(base_currency, str):
            return []
        wanted = base_currency.strip().upper()
        if not wanted:
            return []
        # Imported here, not at module scope: scrumming_bot imports this
        # module, so a top-level import would be circular.
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
        """Return the Scrumming Bot that holds this currency, or None.

        An Extractor works in one base currency and hands that currency
        back when it closes a position. Operator design 2026-08-09: the
        money goes to the Scrumming Bot that HOLDS that currency, which
        raises its target balance to keep the gain instead of selling it
        away as surplus. `ScrummingBot.apply_extractor_tranche_return`
        does that booking; this is how a caller finds the bot to call it
        on.

        A Scrumming Bot holds exactly one asset, named `target_asset` in
        its config. So the parent of an Extractor whose `base_currency`
        is ETH is the Scrumming Bot whose `target_asset` is ETH.

        SAME EXCHANGE, ALWAYS. Operator correction 2026-08-10: "Scrumming
        (Parent) and Extractor (Sibling) are Exchange Bound. We have not
        added any cross-exchange arbitrage features yet." Money that came
        back on one exchange never landed on another, so a bot elsewhere
        is not a parent however well its currency matches -- paying it
        would raise a target balance against money that bot never
        received, while the bot that did receive it stays short. The
        caller names its own exchange, which every config carries as
        `exchange_id` beside `base_currency` and `target_asset`. It is
        asked for by name and has no default, so no caller can leave it
        out: one that tries is refused outright instead of silently
        matching every exchange at once.

        The exchange has to match exactly. Every bot's exchange comes
        from the same saved settings, and `restore_bots_from_state`
        refuses to load a bot whose saved settings name no exchange, so
        both sides are the same text or the bot is not on the books at
        all. Any difference therefore means a different exchange and the
        answer is nothing, which costs a lift and never pays a stranger.

        The currency is matched with surrounding spaces removed and
        without regard to upper or lower case. Anything that is not text
        returns None.

        TWO HOLDERS RETURNS NOTHING. Real money moves on this answer. If
        two Scrumming Bots hold the same asset there is nothing here that
        can tell which one earned the return, and picking either would
        raise the wrong bot's target on money it never received while the
        right bot stays short. The refusal is logged.

        An Extractor is never a parent: it is the child, and it has no
        target balance to raise.

        The matching itself lives in
        `list_parent_bot_candidates_for_base_currency` so that a caller
        needing the COUNT of holders reads the same rules this does. The
        rules above are unchanged; only their one copy moved.
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
        """Return the Extractors that spend this Scrumming Bot's asset.

        Item 4, operator design 2026-08-09: an Extractor's in-flight
        position is an "Extractor Tranche" and it is "listed under the
        base-currency bot". Listing needs the walk that the payment
        never did — parent to children, rather than child to parent.

        THIS IS THE SAME MATCH, READ BACKWARDS. A bot is a child of this
        parent when it is an Extractor, on the same exchange, whose
        `base_currency` is the parent's `target_asset`. That is exactly
        the predicate `list_parent_bot_candidates_for_base_currency`
        applies in the other direction, so it lives here beside it
        rather than in `scrumming_bot`, where a second copy would drift
        away from the first and start disagreeing about who owes whom.

        A CROWD IS NOT REFUSED HERE. The parent lookup returns nothing
        when two Scrumming Bots hold one asset, because a payment cannot
        be split by guessing. Listing has no such problem: several
        Extractors may lease from one parent at once, and naming all of
        them is the correct answer. Nothing here moves money, so nothing
        here needs that refusal.

        Anything that is not a Scrumming Bot with a text `target_asset`
        has no children, and the answer is an empty list. Sorted by bot
        id so the listing does not reshuffle between reads.
        """
        # Imported here, not at module scope: both modules import this
        # one, so a top-level import would be circular.
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
