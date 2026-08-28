"""State persistence for BotManager: save, and rebuild the fleet from saved state."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .config import STACK_MODE_DEFAULT, BotState, make_bot_config

logger = logging.getLogger("acervator.bot")


class StateRestoreMixin:
    """Persistence half of ``BotManager``: writes state out, reads the fleet back.

    Composed into ``BotManager``; ``self`` is the manager instance.
    """

    # Supplied by BotManager at runtime; declared so a type checker
    # can resolve them. Annotations only: no attribute is created and
    # the runtime base stays `object`.
    _boot_state_records: dict
    _bots: dict
    _bus: Any
    _restore_completed: bool
    _restore_ledger: dict
    _smart_wire_mgr: Any
    _state_manager: Any
    register: Callable[..., tuple]

    # -- State persistence -----------------------------------------------
    def save_all_state(self) -> None:
        """Save complete state of all bots + Smart Wire registry.

        v3.15.68 — operator directive 2026-04-26: "Bot swarm state is
        not being preserved." Smart Wire registry (source→target→pct)
        is now saved alongside bot state and rehydrated on restore.
        """
        if not self._state_manager:
            return
        states = [bot.get_full_state() for bot in self._bots.values()]
        wires = []
        ledgers: list = []
        try:
            if self._smart_wire_mgr is not None and hasattr(
                self._smart_wire_mgr, "export_wires"
            ):
                wires = self._smart_wire_mgr.export_wires()
        except Exception as exc:
            logger.warning("save_all_state: smart wire export raised: %s", exc)
        # v3.16.57 — persist per-bot ledgers (wired_in/wired_out totals
        # + provenance) so Smart Wire credits survive restart. Operator
        # bug 2026-05-13: "Smart Wire credits are not persisting across
        # platform restarts." Root cause: only topology was exported,
        # not the ledger state.
        try:
            if self._smart_wire_mgr is not None and hasattr(
                self._smart_wire_mgr, "export_ledgers"
            ):
                ledgers = self._smart_wire_mgr.export_ledgers()
        except Exception as exc:
            logger.warning("save_all_state: smart wire ledger export raised: %s", exc)
        # v3.24.35 (C01) — the DRY-RUN block that stood here is gone.
        # It computed which records a future merge WOULD carry forward
        # and then did not carry them. save_state now carries them for
        # real, and keeping both would leave two answers to one question.
        self._state_manager.save_state(
            states, smart_wires=wires, smart_wire_ledgers=ledgers
        )

    def restore_smart_wires_from_state(self, state: dict) -> int:
        """v3.15.68 — restore the Smart Wire registry from saved state.
        Returns count of wires imported. Re-emits ``wire.created``
        events on the bus so the GUI visualizer can rehydrate its
        on-screen wire list.
        """
        wires = state.get("smart_wires", []) if isinstance(state, dict) else []
        ledgers = state.get("smart_wire_ledgers", []) if isinstance(state, dict) else []
        if (not wires and not ledgers) or self._smart_wire_mgr is None:
            return 0
        n = 0
        try:
            if wires and hasattr(self._smart_wire_mgr, "import_wires"):
                n = self._smart_wire_mgr.import_wires(wires)
        except Exception as exc:
            logger.warning("restore_smart_wires_from_state: import raised: %s", exc)
            return 0
        # v3.16.57 — restore per-bot ledger totals so wired_in /
        # wired_out / provenance survive restart. Attach_bot at startup
        # registers fresh BotLedger entries; import_ledgers overlays the
        # saved totals onto them.
        try:
            if ledgers and hasattr(self._smart_wire_mgr, "import_ledgers"):
                _l = self._smart_wire_mgr.import_ledgers(ledgers)
                if _l > 0:
                    logger.info("Bot Swarm restored: %d ledger(s) rehydrated", _l)
        except Exception as exc:
            logger.warning(
                "restore_smart_wires_from_state: ledger import raised: %s", exc
            )
        # Re-emit wire.created events so the GUI visualizer (which
        # subscribes to the event bus) draws them. Skip if both
        # endpoints aren't currently registered — orphaned wires after
        # bot deletion shouldn't redraw.
        for w in wires:
            try:
                src = str(w.get("source_id", ""))
                tgt = str(w.get("target_id", ""))
                pct = float(w.get("pct", 0))
                if not src or not tgt:
                    continue
                if src not in self._bots or tgt not in self._bots:
                    continue
                self._bus.emit("wire.created", source_id=src, target_id=tgt, pct=pct)
            except Exception as _wire_exc:
                # Skipping a saved link that cannot be read is right —
                # one bad record must not stop the rest being drawn.
                # It used to be silent, so a link the operator set up
                # would simply not appear, with nothing said anywhere.
                # The count printed below still counts it, so the count
                # and the picture disagree; this line is how that shows.
                logger.warning(
                    "Skipped a saved bot-to-bot link while restoring: "
                    "the record could not be read (%s). Record: %r. "
                    "It is not drawn.",
                    _wire_exc,
                    w,
                )
                continue
        logger.info("Bot Swarm restored: %d Smart Wire(s) rehydrated from state", n)
        return n

    def get_saved_state(self) -> dict:
        """Load saved state without restoring."""
        if not self._state_manager:
            return {}
        return self._state_manager.load_state()

    def _ledger_skip(self, bid: str, reason: str) -> None:
        """Record that a bot was OBSERVED failing to load.

        v3.24.35 (C01 PR-0). The single writer of ``_restore_ledger``.
        Only code that watched a bot fail may call it, which is what
        makes the ledger different from inferring intent from absence:
        a bot missing from ``self._bots`` might have been deleted by the
        operator, but a bot in this ledger definitely was not.

        Never raises — a bookkeeping failure must not abort a restore
        that is already handling an error.
        """
        try:
            self._restore_ledger[str(bid)] = str(reason)
        except Exception:  # noqa: BLE001,S110 - bookkeeping only
            pass  # noqa: S110

    def restore_bots_from_state(self, state: dict) -> list[str]:
        """
        Recreate bots from saved state in PAUSED mode.
        Does NOT connect to exchanges or place any orders.
        Returns list of restored bot IDs.

        SAFETY: All restored bots start in IDLE state with a
        'restored' flag. User must explicitly start each one,
        which triggers exchange sync before any trading.
        """
        from .config import BotMode

        bots_data = state.get("bots", {})
        restored = []

        # v3.24.35 (C01 PR-0) — hold the boot records in RAM.
        #
        # Deep-copied so a later mutation of `state` (or of a bot's own
        # dict during restore) cannot alter what was actually on disk at
        # boot. PR-1 hands these to save_state BY VALUE, which is what
        # lets the save path carry a skipped bot's record forward
        # without performing a read — a read there could fail and freeze
        # persistence for the whole fleet.
        import copy as _copy

        try:
            self._boot_state_records = _copy.deepcopy(bots_data) or {}
        except Exception as _cp_exc:  # noqa: BLE001 - never block restore
            self._boot_state_records = {}
            logger.error(
                "C01: could not snapshot boot records (%s); carry-forward "
                "will be unavailable this session",
                _cp_exc,
            )
        self._restore_ledger = {}
        self._restore_completed = False

        for bid, bot_data in bots_data.items():
            cfg = bot_data.get("config", {})
            if not cfg.get("exchange_id"):
                # v3.24.35 (C01 PR-0) — this skip was entirely SILENT.
                # Of the five `continue` exits in this function it was
                # the only one with no log line at any level, so a bot
                # whose persisted config lost its exchange_id vanished
                # without a trace -- and then, because save_state
                # rebuilds "bots" solely from the registered set, its
                # record was deleted from bot_state.json by the 60s
                # save timer. Silent skip followed by silent deletion.
                #
                # Measured 2026-08-05 on the live file: 35 bots holding
                # 1,949 lots and 829 fold tranches, none of it
                # reconstructible from exchange fill history.
                logger.error(
                    "Bot %s SKIPPED during restore: persisted config has "
                    "no exchange_id. Its saved record (lots, tranches, "
                    "anchor balance) is NOT loaded and must not be "
                    "overwritten.",
                    bid,
                )
                self._ledger_skip(bid, "no exchange_id in persisted config")
                continue

            # Recreate BotConfig.
            # v3.20.4 — grid handling fully removed. Missing/empty
            # mode is treated as SCRUMMING for backward compat with
            # pre-v3.19.1 save files; any explicit but unrecognized
            # mode string (including the now-defunct "grid") is
            # ERROR-logged and skipped rather than silently
            # misclassified.
            # sadp: R28 FL  R55 GOV  R68 DPA
            _mode_str = (cfg.get("mode") or "").lower()
            if _mode_str == "extractor":
                mode = BotMode.EXTRACTOR
            elif _mode_str == "scrumming" or _mode_str == "":
                mode = BotMode.SCRUMMING
            else:
                logger.error(
                    "Bot %s has unrecognized mode %r in saved state "
                    "— skipping restoration. (Legacy 'grid' mode was "
                    "removed v3.20.4; persisted grid bots are not "
                    "restorable. Add an explicit branch in "
                    "restore_bots_from_state() if you intend to "
                    "support a new mode.)",
                    bid,
                    _mode_str,
                )
                self._ledger_skip(bid, "legacy grid mode (unrestorable)")
                continue
            # v3.20.35 — restore path migrated to make_bot_config
            # factory (per operator directive 2026-05-25 "Make sure
            # any syntax deemed 'old' is being purged"). Same
            # three-layer split as main_window.py: shared kwargs +
            # mode-specific kwargs + factory call. Stale persisted
            # configs with mode-foreign field values are caught at
            # restore time with a clear error, then skipped (the
            # restore path must not abort the platform launch on
            # one bad bot — we log and continue).
            # Local boolean hoisted so the test_bot_restoration_
            # dispatch fitness pin (which scans for the FIRST
            # mode-equality occurrence and expects ExtractorBot
            # construction within 600 chars) still lands on the
            # actual dispatch branch below, not on the target_asset
            # default ternary.
            _ta_default = "*" if mode.value == "extractor" else "BTC"
            _shared_kwargs = {
                "exchange_id": cfg["exchange_id"],
                "base_currency": cfg.get("base_currency", "USDT"),
                "target_asset": cfg.get("target_asset", _ta_default),
                "symbol": cfg.get("symbol", ""),
                "target_balance": cfg.get("target_balance", 200.0),
                "ta_timeframe": cfg.get("ta_timeframe", "1h"),
                "visibility": cfg.get("visibility", "orderbook"),
                "aggressive_trading": cfg.get("aggressive_trading", False),
                # An absent key resolves to STACK_MODE_DEFAULT, not to
                # the retired `bulk_trading`. That key was always False,
                # so reading it here resolved a pre-rename state file to
                # a stale False instead of the current default; it is
                # dropped by _sanitize_deprecated_kwargs() either way.
                "stack_mode": cfg.get("stack_mode", STACK_MODE_DEFAULT),
                "split_distance": cfg.get("split_distance", 1.0),
                "stack_tranche_count_target": cfg.get("stack_tranche_count_target", 3),
                "stack_spacing_mode": cfg.get("stack_spacing_mode", "linear"),
                # v3.23.25 bulk_partial_on_return retired
                "max_entry_price": cfg.get("max_entry_price", None),
                "min_entry_price": cfg.get("min_entry_price", None),
                "trading_fee_pct": cfg.get("trading_fee_pct", 0.6),
            }
            if mode == BotMode.SCRUMMING:
                # v3.23.3 R-CLN Phase 1: 8 grid-legacy dead fields no
                # longer extracted from cfg. See
                # docs/audits/2026-06-12_scrumming_bot_field_alignment.md
                # for the list. Operator's bot_state.json may still
                # carry these keys — silently ignored by cleaned code.
                # GUI wizard/settings cleanup deferred to R-CLN Phase 2.
                _mode_kwargs = {
                    "investment_amount": cfg.get("investment_amount", 200.0),
                    "increment_style": cfg.get("increment_style", "linear"),
                    "spacing_style": cfg.get("spacing_style", "expanding"),
                    # v3.23.25 market_check_interval kwarg removed
                    "profit_folding_active": cfg.get("profit_folding_active", True),
                    "scrumming_interval_pct": cfg.get("scrumming_interval_pct", 1.0),
                    "profit_route": cfg.get("profit_route", "fold_to_target"),
                    "profit_route_bot_id": cfg.get("profit_route_bot_id", ""),
                    "scrum_fold_pct": cfg.get("scrum_fold_pct", 100),
                    # Item 9 — despawn timer. Absent from every
                    # state file written before 2026-08-13, so the
                    # default here is what those bots restore with: 0.
                    "tranche_despawn_days": cfg.get("tranche_despawn_days", 0),
                    "max_target_growth_pct": cfg.get("max_target_growth_pct", 1.0),
                    "bb_tolerance_pct": cfg.get("bb_tolerance_pct", 1.0),
                    "bb_landing_strip_candles": cfg.get("bb_landing_strip_candles", 3),
                    "scrum_detect_pct": cfg.get("scrum_detect_pct", 75),
                    "scrum_fire_pct": cfg.get("scrum_fire_pct", 0.5),
                    "bb_midline_gate": cfg.get("bb_midline_gate", True),
                    "scrum_read_rate_min": cfg.get("scrum_read_rate_min", 5),
                    "band_travel_pct": cfg.get("band_travel_pct", 70),
                    "bb_bullseye_check": cfg.get("bb_bullseye_check", True),
                    "hedge_rebalance_active": cfg.get("hedge_rebalance_active", True),
                    "hedge_balance": cfg.get("hedge_balance", 200.0),
                    "position_ceiling_enabled": cfg.get(
                        "position_ceiling_enabled", False
                    ),
                    "position_ceiling_multiple": cfg.get(
                        "position_ceiling_multiple", 5.0
                    ),
                    "detonation_enabled": cfg.get("detonation_enabled", False),
                    "detonation_timeframe": cfg.get("detonation_timeframe", "1d"),
                    "detonation_confidence_min": cfg.get(
                        "detonation_confidence_min", 0.75
                    ),
                    # v3.23.42 interop
                    "self_reserve_capital": cfg.get("self_reserve_capital", True),
                    "personal_hold_qty": cfg.get("personal_hold_qty", 0.0),
                    "circuit_breaker_soft_pct": cfg.get(
                        "circuit_breaker_soft_pct", 25.0
                    ),
                    "circuit_breaker_hard_pct": cfg.get(
                        "circuit_breaker_hard_pct", 35.0
                    ),
                    "circuit_breaker_cooldown_candles": cfg.get(
                        "circuit_breaker_cooldown_candles", 3
                    ),
                    "max_cartridge_size_pct": cfg.get("max_cartridge_size_pct", 10.0),
                    "max_cartridge_smart": cfg.get("max_cartridge_smart", False),
                    "max_cartridge_smart_ceiling_pct": cfg.get(
                        "max_cartridge_smart_ceiling_pct", 30.0
                    ),
                    "wire_inflow_stack_pct": cfg.get("wire_inflow_stack_pct", 1.0),
                    "scrum_require_ta_bullish": cfg.get(
                        "scrum_require_ta_bullish", True
                    ),
                    "scrum_hold_in_uptrend": cfg.get("scrum_hold_in_uptrend", True),
                    "scrum_defer_to_htf": cfg.get("scrum_defer_to_htf", True),
                    "fold_require_ta_bearish": cfg.get("fold_require_ta_bearish", True),
                    "fold_hold_in_downtrend": cfg.get("fold_hold_in_downtrend", True),
                    "fold_defer_to_htf": cfg.get("fold_defer_to_htf", True),
                }
            else:  # BotMode.EXTRACTOR
                _mode_kwargs = {
                    "extractor_chunk_size_usd": cfg.get(
                        "extractor_chunk_size_usd", 100.0
                    ),
                    "extractor_artillery_size_usd": cfg.get(
                        "extractor_artillery_size_usd", 5.0
                    ),
                    "extractor_scan_top_n": cfg.get("extractor_scan_top_n", 8),
                    "extractor_scan_refresh_candles": cfg.get(
                        "extractor_scan_refresh_candles", 60
                    ),
                    "extractor_pool_reserve_pct": cfg.get(
                        "extractor_pool_reserve_pct", 50.0
                    ),
                    "extractor_exit_pct": cfg.get("extractor_exit_pct", 100.0),
                    "extractor_drawdown_threshold_pct": cfg.get(
                        "extractor_drawdown_threshold_pct", 3.0
                    ),
                    "extractor_correction_skip_candles": cfg.get(
                        "extractor_correction_skip_candles", 4
                    ),
                    "extractor_max_cost_basis_multiple": cfg.get(
                        "extractor_max_cost_basis_multiple", 2.0
                    ),
                    "extractor_max_compounding_tier": cfg.get(
                        "extractor_max_compounding_tier", 3
                    ),
                    "extractor_hedge_budget_usd": cfg.get(
                        "extractor_hedge_budget_usd", 0.0
                    ),
                    "extractor_trend_strength_threshold": cfg.get(
                        "extractor_trend_strength_threshold", 0.65
                    ),
                    "extractor_alt_targets": list(
                        cfg.get("extractor_alt_targets", []) or []
                    ),
                    # v3.20.74 — Inverted Extractor (Q6/Q7/Q8/Q9):
                    # direction flag + standing-position import unit
                    # count for Inverted variants.
                    "extractor_direction": cfg.get("extractor_direction", "normal"),
                    "inverted_extractor_standing_alt_units": float(
                        cfg.get("inverted_extractor_standing_alt_units", 0.0) or 0.0
                    ),
                }
            try:
                config = make_bot_config(mode, **_shared_kwargs, **_mode_kwargs)
            except (ValueError, TypeError) as _restore_err:
                logger.error(
                    "Bot %s restoration FAILED — mode-shape "
                    "violation in persisted config: %s. Skipping "
                    "this bot. (Either operator manually edited "
                    "state.json to a bad shape, or a pre-v3.20.32 "
                    "config drifted out of mode invariants. To "
                    "recover: delete the bot's entry from state "
                    "and recreate via the wizard, OR fix the "
                    "persisted JSON to match mode invariants.)",
                    bid,
                    _restore_err,
                )
                self._ledger_skip(bid, "mode-shape violation in persisted config")
                continue

            # Create bot with placeholder exchange (will be replaced
            # on start).
            #
            # v3.20.4 — DISPATCH BY MODE. Prior to this hotfix, the
            # restore path always constructed a ScrummingBot regardless
            # of the persisted mode. EXTRACTOR-mode bots (added
            # v3.19.1) tripped ScrummingBot.__init__'s `assert
            # config.mode == BotMode.SCRUMMING` and **aborted the
            # platform launch** before the GUI loaded. Operator hit
            # this 2026-05-23 with a persisted Extractor in state.
            # Root cause: BotMode.EXTRACTOR was added to the enum but
            # the dispatch table at this call site was never updated.
            # The same cascade removed BotMode.GRID entirely (operator
            # directive 2026-05-23: "Grid code and dangling mentions
            # can be cleaned out").
            #
            # Discipline going forward:
            #   - Every BotMode value MUST have an explicit branch.
            #   - Unknown modes ERROR-log and `continue` — one corrupt
            #     record never takes down platform launch (R28 FL
            #     loud-but-not-fatal where the user is locked out).
            #   - Whole construction wrapped in try/except so a broken
            #     bot can't poison restoration of healthy bots either.
            #
            # ExtractorBot is constructed with enable_phantoms=False
            # unconditionally — Extractor does not use phantoms by
            # design (extractor_bot.py:140).
            # sadp: R28 FL  R55 GOV  R62 FRG  R68 DPA  R76 DMW
            bot = None
            try:
                if mode == BotMode.EXTRACTOR:
                    from ...trading.extractor_bot import ExtractorBot

                    bot = ExtractorBot(
                        config,
                        _PlaceholderExchangeForRestore(cfg["exchange_id"]),
                        enable_phantoms=False,
                    )
                    logger.info(
                        "Restore: constructed ExtractorBot for %s " "(mode=%s)",
                        bid[:8],
                        _mode_str,
                    )
                elif mode == BotMode.SCRUMMING:
                    from ...trading.scrumming_bot import ScrummingBot

                    # v3.16.27 P0g — restore phantom enabled flag from
                    # saved state. Default: True (matches
                    # ScrummingBot.__init__ default — preserves
                    # prior-version behavior for save files that don't
                    # carry the flag yet). Once a bot has been saved
                    # by v3.16.27+ it round-trips correctly.
                    _restored_phantoms_enabled = bot_data.get("phantoms_enabled", True)
                    bot = ScrummingBot(
                        config,
                        _PlaceholderExchangeForRestore(cfg["exchange_id"]),
                        enable_phantoms=bool(_restored_phantoms_enabled),
                    )
                    # v3.16.36 — operator-reported 2026-05-06 that
                    # phantoms were still activating after restart
                    # despite the v3.16.27 fix. Inspection of the
                    # actual saved state file confirmed
                    # phantoms_enabled=False is correctly persisted;
                    # my v3.16.27 save/restore round-trip works. This
                    # post-restore diagnostic INFO log lets the
                    # operator verify directly in the activity log
                    # that the flag was honored at restore time. If
                    # the log shows False at restart but phantoms
                    # still appear active, the bug is downstream
                    # (GUI display, tick auto-start guard, or an
                    # unconfirmed override path) — the diagnostic
                    # narrows the search space.
                    logger.info(
                        "P0g-DIAG | bot=%s saved_phantoms_enabled=%s "
                        "constructed_with_enable_phantoms=%s "
                        "bot._phantoms_enabled=%s",
                        bid[:8],
                        _restored_phantoms_enabled,
                        bool(_restored_phantoms_enabled),
                        bot._phantoms_enabled,
                    )
                else:
                    # Defensive — should be unreachable because the
                    # mode-parsing step above already skips unknown
                    # modes via `continue`. Kept as a belt-and-braces
                    # guard so adding a new BotMode without a branch
                    # here is logged rather than silently broken.
                    logger.error(
                        "Bot %s mode %s (parsed from %r) has no "
                        "construction branch in "
                        "restore_bots_from_state — skipping. Add an "
                        "explicit branch for this BotMode value.",
                        bid,
                        mode,
                        _mode_str,
                    )
                    self._ledger_skip(bid, "no construction branch for mode")
                    continue
            except Exception as exc:
                logger.error(
                    "Bot %s construction failed during restore (%s) — "
                    "skipping. Other bots in the saved state will "
                    "still be restored. Platform launch continues.",
                    bid,
                    exc,
                )
                self._ledger_skip(bid, "construction failed")
                continue

            # Preserve original bot ID
            bot.bot_id = bid

            # Restore stats
            saved_stats = bot_data.get("stats", {})
            for key, val in saved_stats.items():
                if hasattr(bot.stats, key):
                    setattr(bot.stats, key, val)

            # MEM-245 — Restore scrumming compounding state (main_lots,
            # fold_tranches, accumulation scalars). Absence is safe
            # (bot starts fresh as before).
            # v3.20.4 — symmetric extractor branch restores
            # positions/chunk/hedge from extractor_state if present.
            # v3.24.35 (C01 PR-0) — did this bot's persisted state
            # actually load?
            #
            # The two branches below are the ONLY restore failures that
            # do not `continue`. Control falls through to register(), so
            # the bot ends up in self._bots holding DEFAULT state — and
            # because save_state rebuilds "bots" from the registered
            # set, the next 60s save writes those defaults over the good
            # persisted record. That is strictly worse than a skip: a
            # skipped bot is merely absent, this one actively overwrites.
            #
            # The old message said "(bot will start fresh)", which reads
            # as harmless. It is not: the record it would have started
            # from is destroyed one minute later.
            bot._state_import_failed = False
            if mode == BotMode.EXTRACTOR:
                ext_state = bot_data.get("extractor_state")
                if ext_state and hasattr(bot, "import_state"):
                    try:
                        bot.import_state(ext_state)
                        logger.info(
                            "Restored extractor state for %s: "
                            "%d position(s), chunk_free_base=%.6f, "
                            "hedge_free_base=%.6f, watch_list=%d",
                            bid,
                            len(getattr(bot, "_positions", {})),
                            getattr(bot, "_chunk_free_base", 0.0),
                            getattr(bot, "_hedge_free_base", 0.0),
                            len(getattr(bot, "_watch_list", [])),
                        )
                    except Exception as exc:
                        bot._state_import_failed = True
                        self._ledger_skip(bid, "extractor import_state failed")
                        logger.error(
                            "Extractor import_state FAILED on %s: %s. The "
                            "bot is registered with DEFAULT state, so the "
                            "next save would overwrite its persisted "
                            "record. Do not let that record be replaced.",
                            bid,
                            exc,
                        )
            else:
                scrum_state = bot_data.get("scrumming_state")
                if scrum_state and hasattr(bot, "import_scrumming_state"):
                    try:
                        bot.import_scrumming_state(scrum_state)
                        logger.info(
                            "Restored scrumming state for %s: "
                            "%d lot(s), %d tranche(s), target=$%.2f, "
                            "anchor=$%.2f, holdings=%.6f",
                            bid,
                            len(getattr(bot, "_main_lots", [])),
                            len(getattr(bot, "_fold_tranches", [])),
                            getattr(bot, "_target_balance", 0.0),
                            getattr(bot, "_anchor_target_balance", 0.0),
                            getattr(bot, "_current_holdings", 0.0),
                        )
                    except Exception as exc:
                        bot._state_import_failed = True
                        self._ledger_skip(bid, "import_scrumming_state failed")
                        # v3.24.48 (Phase 1 Step 5) — this used to log
                        # the hazard and then fall through to register()
                        # anyway, with DEFAULT state. The message below
                        # said "the next save would overwrite its
                        # persisted lots and tranches. Do not let that
                        # record be replaced" -- and then nothing stopped
                        # it. Sixty seconds after launch the save timer
                        # wrote 0 lots and 0 tranches over the good
                        # record. On the largest queue in the fleet that
                        # is ~200 tranches plus every lot's cost basis,
                        # destroyed by one malformed field.
                        #
                        # Skipping registration is what protects it. A
                        # bot absent from self._bots is absent from the
                        # dict save_state rebuilds, and state_manager's
                        # carry-forward keys on exactly that absence, so
                        # the on-disk record survives untouched.
                        #
                        # import_scrumming_state is NOT transactional --
                        # it applies fields sequentially -- so what is
                        # being protected is a PARTIALLY-applied record,
                        # not a cleanly zeroed one. That is the reason
                        # the in-memory object must not be trusted or
                        # saved from.
                        logger.error(
                            "import_scrumming_state FAILED on %s: %s. The "
                            "bot is NOT being registered this launch, so "
                            "its persisted lots and tranches are carried "
                            "forward intact rather than overwritten with "
                            "defaults. It will be ABSENT from the fleet "
                            "until the state record is repaired.",
                            bid,
                            exc,
                        )
                        # The bot vanishing from the fleet must never
                        # read as a silent deletion, so say so on the
                        # operator's own surface, not just in a log file.
                        try:
                            self._bus.emit(
                                "bot.restore_failed",
                                bot_id=bid,
                                symbol=getattr(config, "symbol", ""),
                                error=f"{type(exc).__name__}: {exc}",
                                message=(
                                    f"BOT NOT LOADED: {getattr(config, 'symbol', bid)} "
                                    f"({bid[:8]}) failed to restore its "
                                    f"saved state ({type(exc).__name__}: "
                                    f"{exc}). It is absent from the fleet "
                                    f"this launch. Its saved lots and "
                                    f"tranches are INTACT on disk and "
                                    f"were not overwritten. Repair the "
                                    f"record and relaunch."
                                ),
                            )
                        except Exception as _emit_exc:  # noqa: BLE001
                            logger.error(
                                "restore-failure banner could not be "
                                "emitted for %s (%s); the bot is missing "
                                "from the fleet with no operator-facing "
                                "notice",
                                bid,
                                _emit_exc,
                            )
                        continue

            # Mark as restored — stays IDLE until user starts
            bot.state = BotState.IDLE
            bot._restored = True
            # v3.16.11 — record whether this bot was running at the time
            # the saved state was captured. The auto-restart-after-launch
            # path (start_all with eligible_filter) uses this to decide
            # which bots to bring back online.
            bot._was_running = (
                str(bot_data.get("state_when_saved", "")).lower() == "running"
            )

            # v3.24.35 (C01 PR-0) — register() returns
            # (granted, refusal_reason) and its result was DISCARDED, so
            # a refused registration was still appended to `restored`.
            # That made it a sixth restore exit nobody had enumerated:
            # the bot is counted as restored, is absent from self._bots,
            # and is therefore absent from the list save_state rebuilds
            # "bots" from -- deleted by the next 60s save while the boot
            # report claimed success.
            _granted, _refusal = self.register(bot)
            if not _granted:
                logger.error(
                    "Bot %s REFUSED registration during restore (%s). Its "
                    "saved record is NOT loaded and must not be "
                    "overwritten.",
                    bid,
                    _refusal,
                )
                self._ledger_skip(bid, "registration refused")
                continue
            restored.append(bid)
            logger.info(
                "Restored bot %s (%s on %s) in IDLE state%s",
                bid,
                config.symbol,
                config.exchange_id,
                " (was RUNNING at save)" if bot._was_running else "",
            )

        # v3.24.35 (C01 PR-0) — restore reached its end.
        #
        # PR-1 requires this before any carry-forward decision: if a
        # restore ABORTED partway, the ledger is incomplete and absence
        # proves nothing, so a save must refuse rather than guess. The
        # flag distinguishes "no bots failed" from "we never finished
        # looking", which an empty ledger alone cannot.
        self._restore_completed = True
        if self._restore_ledger:
            logger.error(
                "C01: restore completed with %d bot(s) NOT loaded: %s. "
                "Their records are still on disk and will be DELETED by "
                "the next save (PR-0 is log-only).",
                len(self._restore_ledger),
                ", ".join(
                    f"{b} ({r})" for b, r in list(self._restore_ledger.items())[:8]
                ),
            )
        else:
            logger.info(
                "C01: restore completed, all %d persisted bot(s) loaded", len(bots_data)
            )

        self._sweep_orphan_capital_reservations(bots_data)
        return restored

    def _sweep_orphan_capital_reservations(self, bots_data: dict) -> int:
        """Drop capital reservations whose bot id is not in the persisted
        fleet. Returns the number dropped; never raises into restore.

        The reservation table persists across restarts, so a reservation left
        by a bot that no longer exists is inherited by every launch and no
        owner can release it. Swept against every persisted record, including
        the ones restore skipped, because a skipped bot is still a real bot.
        """
        if not bots_data:
            return 0
        try:
            from src.trading.capital_reservation import get_registry

            dropped = get_registry().sweep_unknown_bots(
                bots_data.keys(), note="fleet restore"
            )
        except Exception as _sweep_exc:  # noqa: BLE001 - never block restore
            logger.error(
                "Capital-reservation orphan sweep raised %s: %s — the "
                "reservation table is left exactly as it was on disk",
                type(_sweep_exc).__name__,
                _sweep_exc,
            )
            return 0
        if dropped:
            logger.warning(
                "Dropped %d capital reservation(s) held by bot ids outside "
                "the %d-bot persisted fleet",
                len(dropped),
                len(bots_data),
            )
        return len(dropped)


class _PlaceholderExchangeForRestore:
    """Minimal placeholder used during state restore. Replaced on bot start."""

    def __init__(self, exchange_id: str):
        self.exchange_id = exchange_id
        self.display_name = exchange_id.capitalize()
        self.is_connected = False
