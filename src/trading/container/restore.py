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

    # Declared for the type checker only; BotManager supplies these at runtime.
    _boot_state_records: dict
    _bots: dict
    _bus: Any
    _restore_completed: bool
    _restore_ledger: dict
    _smart_wire_mgr: Any
    _state_manager: Any
    _ta_weights: Any
    register: Callable[..., tuple]

    # -- State persistence -----------------------------------------------
    def save_all_state(self) -> None:
        """Write every registered bot's state, the Smart Wire topology and
        the per-bot wire ledgers through the state manager.
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
        # Ledger totals are separate from topology: export_wires carries
        # only source, target and pct.
        try:
            if self._smart_wire_mgr is not None and hasattr(
                self._smart_wire_mgr, "export_ledgers"
            ):
                ledgers = self._smart_wire_mgr.export_ledgers()
        except Exception as exc:
            logger.warning("save_all_state: smart wire ledger export raised: %s", exc)
        self._state_manager.save_state(
            states, smart_wires=wires, smart_wire_ledgers=ledgers
        )

    def restore_smart_wires_from_state(self, state: dict) -> int:
        """Rebuild the Smart Wire topology and ledger totals from saved state.

        Re-emits ``wire.created`` on the bus so the visualizer redraws each
        link. Returns the number of wires ``import_wires`` accepted.
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
        # import_ledgers updates an existing ledger entry in place and
        # creates a missing one.
        try:
            if ledgers and hasattr(self._smart_wire_mgr, "import_ledgers"):
                _l = self._smart_wire_mgr.import_ledgers(ledgers)
                if _l > 0:
                    logger.info("Bot Swarm restored: %d ledger(s) rehydrated", _l)
        except Exception as exc:
            logger.warning(
                "restore_smart_wires_from_state: ledger import raised: %s", exc
            )
        # A wire with either endpoint missing from self._bots is not re-emitted.
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
                # One unreadable record must not stop the remaining links
                # being drawn.
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

        Writes the bot id and the reason into ``_restore_ledger``. Only code
        that watched a bot fail may call it: a bot missing from ``self._bots``
        may have been deleted by the operator, but a bot in this ledger was
        not. Never raises, so a bookkeeping failure cannot abort a restore
        that is already handling an error.
        """
        try:
            self._restore_ledger[str(bid)] = str(reason)
        except Exception:  # noqa: BLE001,S110 - bookkeeping only
            pass

    def restore_bots_from_state(self, state: dict) -> list[str]:
        """Recreate every persisted bot in IDLE state; return the ids restored.

        Connects to no exchange and places no order. Each restored bot carries
        a ``_restored`` flag and stays IDLE until the operator starts it, which
        is what triggers the exchange sync before any trading.
        """
        from .config import BotMode

        bots_data = state.get("bots", {})
        restored = []

        # Deep-copied so a later mutation of `state` cannot change what was
        # on disk at boot.
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
                logger.error(
                    "Bot %s SKIPPED during restore: persisted config has "
                    "no exchange_id. Its saved record (lots, tranches, "
                    "anchor balance) is NOT loaded and must not be "
                    "overwritten.",
                    bid,
                )
                self._ledger_skip(bid, "no exchange_id in persisted config")
                continue

            # An absent or empty mode is treated as SCRUMMING for pre-rename
            # state files.
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
            # make_bot_config raises on a mode-foreign field, so a stale
            # config is skipped rather than constructed.
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
                # An absent stack_mode resolves to STACK_MODE_DEFAULT; a
                # stored bulk_trading reaches no kwarg on this path.
                "stack_mode": cfg.get("stack_mode", STACK_MODE_DEFAULT),
                "split_distance": cfg.get("split_distance", 1.0),
                "stack_tranche_count_target": cfg.get("stack_tranche_count_target", 3),
                "stack_spacing_mode": cfg.get("stack_spacing_mode", "linear"),
                "max_entry_price": cfg.get("max_entry_price", None),
                "min_entry_price": cfg.get("min_entry_price", None),
                "trading_fee_pct": cfg.get("trading_fee_pct", 0.6),
            }
            if mode == BotMode.SCRUMMING:
                # Every kwarg below is named one at a time, so a
                # _DEPRECATED_KWARGS name in cfg reaches none of them.
                _mode_kwargs = {
                    "investment_amount": cfg.get("investment_amount", 200.0),
                    "increment_style": cfg.get("increment_style", "linear"),
                    "spacing_style": cfg.get("spacing_style", "expanding"),
                    "profit_folding_active": cfg.get("profit_folding_active", True),
                    "scrumming_interval_pct": cfg.get("scrumming_interval_pct", 1.0),
                    "profit_route": cfg.get("profit_route", "fold_to_target"),
                    "profit_route_bot_id": cfg.get("profit_route_bot_id", ""),
                    "scrum_fold_pct": cfg.get("scrum_fold_pct", 100),
                    # Absent from older state files, so those bots restore
                    # with the despawn timer at 0.
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

            # Every BotMode needs an explicit branch here; ScrummingBot
            # rejects a config whose mode is not SCRUMMING.
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

                    # Default True matches ScrummingBot.__init__, so a state
                    # file without the flag keeps prior behaviour.
                    _restored_phantoms_enabled = bot_data.get("phantoms_enabled", True)
                    bot = ScrummingBot(
                        config,
                        _PlaceholderExchangeForRestore(cfg["exchange_id"]),
                        enable_phantoms=bool(_restored_phantoms_enabled),
                        ta_weights=self._ta_weights,
                    )
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
                    # Unreachable: the mode parse above already skips an
                    # unknown mode.
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

            bot.bot_id = bid

            saved_stats = bot_data.get("stats", {})
            for key, val in saved_stats.items():
                if hasattr(bot.stats, key):
                    setattr(bot.stats, key, val)

            # An extractor import failure still registers the bot; only the
            # scrumming branch skips registration.
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
                        # The bus banner tells the operator on screen; a log
                        # line alone would read as a deletion.
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

            bot.state = BotState.IDLE
            bot._restored = True
            # Recorded from the saved state; only the restore log below
            # reads it.
            bot._was_running = (
                str(bot_data.get("state_when_saved", "")).lower() == "running"
            )

            # register() refuses on capital over-allocation; a refused bot
            # must not be counted as restored.
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

        # An aborted restore leaves the ledger incomplete, so absence alone
        # cannot prove a bot loaded.
        self._restore_completed = True
        if self._restore_ledger:
            logger.error(
                "C01: restore completed with %d bot(s) NOT loaded: %s. "
                "Their records are still on disk and the next save carries "
                "them forward untouched. Do not recreate these bots.",
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
