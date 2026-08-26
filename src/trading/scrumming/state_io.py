"""State serialization for ScrummingBot: export/import of compounding state."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ..bot_container import BotState, as_finite_float

logger = logging.getLogger("acervator.scrumming")


class StateSerializerMixin:
    """Persist and restore the bot's compounding state as a plain dict.

    Exchange-derivable fields (unit holdings) are intentionally not
    persisted: the exchange is authoritative and the boot handshake
    repopulates them. Only state the exchange cannot report is saved —
    cost-basis lots, fold tranches, operator set-points, internal counters,
    and the trade state machine.
    """

    # Supplied by ScrummingBot at runtime; declared so a type
    # checker can resolve them. Annotations only: no attribute is
    # created and the runtime base stays `object`.
    _anchor_target_balance: float
    _bus: Any
    _cb_hard_trip_pct: float
    _cb_hard_tripped: bool
    _cb_hard_tripped_at: float
    _cb_soft_active_side: Optional[str]
    _cb_soft_cooldown_remaining: int
    _cb_soft_trip_pct: float
    _current_holdings: float
    _dist_accumulator: float
    _fold_accumulator: float
    _fold_cycle_cap_consumed: float
    _fold_queue_usd: float
    _fold_tranches: list[dict]
    _hedge_bal: float
    _hedge_trades: int
    _hyst_armed_fold_side: bool
    _hyst_armed_scrum_side: bool
    _hyst_ref_fold_side: float
    _hyst_ref_scrum_side: float
    _initialised: Any
    _last_trade_price: float
    _last_trade_side: Optional[str]
    _main_lots: list[dict]
    _compact_wire_credits: Callable[..., int]
    _pending_stack_buy_usd: float
    _pending_wire_credits: float
    _pending_wire_ledger: list[dict]
    _quote_to_usd: float
    _scrum_sells_lifetime: int
    _scrum_target_mode: str
    _scrum_target_side: Optional[str]
    _stack_counters_reset_ts: float
    _stack_created: int
    _stack_discarded: int
    _stack_tranches: list[dict]
    _standing_surplus_usd: float
    _target_balance: Any
    _target_grow_last_side: Optional[str]
    _tranches_closed_lifetime: int
    _tranches_counters_reset_ts: float
    _tranches_created_lifetime: int
    _tranches_discarded_lifetime: Any
    _tranches_malformed_dropped: int
    _wire_credits_discarded_lifetime: Any
    bot_id: Any
    config: Any
    state: Any

    def export_scrumming_state(self) -> dict:
        """Export compounding state as a JSON-serializable dict.

        Called by ``BotContainer.get_full_state()``.
        """
        return {
            "target_balance": float(self._target_balance),
            "anchor_target_balance": float(self._anchor_target_balance),
            "standing_surplus_usd": float(
                getattr(self, "_standing_surplus_usd", 0.0) or 0.0
            ),
            "fold_cycle_cap_consumed": float(
                getattr(self, "_fold_cycle_cap_consumed", 0.0) or 0.0
            ),
            "pending_wire_credits": float(
                getattr(self, "_pending_wire_credits", 0.0) or 0.0
            ),
            "last_trade_price": float(self._last_trade_price),
            "last_trade_side": self._last_trade_side,
            "quote_to_usd": float(self._quote_to_usd or 1.0),
            "pending_stack_buy_usd": float(
                getattr(self, "_pending_stack_buy_usd", 0.0) or 0.0
            ),
            "cb_hard_tripped": bool(getattr(self, "_cb_hard_tripped", False)),
            "cb_hard_tripped_at": float(
                getattr(self, "_cb_hard_tripped_at", 0.0) or 0.0
            ),
            "cb_hard_trip_pct": float(getattr(self, "_cb_hard_trip_pct", 0.0) or 0.0),
            "cb_soft_active_side": getattr(self, "_cb_soft_active_side", None),
            "cb_soft_cooldown_remaining": int(
                getattr(self, "_cb_soft_cooldown_remaining", 0) or 0
            ),
            "cb_soft_trip_pct": float(getattr(self, "_cb_soft_trip_pct", 0.0) or 0.0),
            "fold_queue_usd": float(self._fold_queue_usd),
            "dist_accumulator": float(self._dist_accumulator),
            "hedge_bal": float(self._hedge_bal),
            "hedge_trades": int(self._hedge_trades),
            "scrum_target_mode": str(self._scrum_target_mode),
            "scrum_target_side": self._scrum_target_side,
            "main_lots": [dict(lot) for lot in self._main_lots],
            "fold_tranches": [dict(t) for t in self._fold_tranches],
            "hyst_armed_fold_side": bool(getattr(self, "_hyst_armed_fold_side", False)),
            "hyst_armed_scrum_side": bool(
                getattr(self, "_hyst_armed_scrum_side", False)
            ),
            "hyst_ref_fold_side": float(
                getattr(self, "_hyst_ref_fold_side", 0.0) or 0.0
            ),
            "hyst_ref_scrum_side": float(
                getattr(self, "_hyst_ref_scrum_side", 0.0) or 0.0
            ),
            "tranches_created_lifetime": int(
                getattr(self, "_tranches_created_lifetime", 0) or 0
            ),
            "tranches_closed_lifetime": int(
                getattr(self, "_tranches_closed_lifetime", 0) or 0
            ),
            "scrum_sells_lifetime": int(getattr(self, "_scrum_sells_lifetime", 0) or 0),
            "tranches_discarded_lifetime": int(
                getattr(self, "_tranches_discarded_lifetime", 0) or 0
            ),
            "wire_credits_discarded_lifetime": float(
                getattr(self, "_wire_credits_discarded_lifetime", 0.0) or 0.0
            ),
            "pending_wire_ledger": [
                dict(_e)
                for _e in (getattr(self, "_pending_wire_ledger", []) or [])
                if isinstance(_e, dict)
            ],
            "fold_accumulator": float(getattr(self, "_fold_accumulator", 0.0) or 0.0),
            "tranches_malformed_dropped": int(
                getattr(self, "_tranches_malformed_dropped", 0) or 0
            ),
            "tranches_counters_reset_ts": float(
                getattr(self, "_tranches_counters_reset_ts", 0.0) or 0.0
            ),
            "stack_tranches": [
                dict(_t)
                for _t in (getattr(self, "_stack_tranches", []) or [])
                if isinstance(_t, dict)
            ],
            "stack_created": int(getattr(self, "_stack_created", 0) or 0),
            # as_finite_float: JSON NaN/Infinity would crash a bare int().
            "stack_discarded": int(
                as_finite_float(getattr(self, "_stack_discarded", 0)) or 0.0
            ),
            "stack_counters_reset_ts": float(
                as_finite_float(getattr(self, "_stack_counters_reset_ts", 0.0)) or 0.0
            ),
            "target_grow_last_side": (
                str(getattr(self, "_target_grow_last_side", None))
                if getattr(self, "_target_grow_last_side", None) in ("lower", "upper")
                else None
            ),
            "_format_version": 7,
        }

    def import_scrumming_state(self, data: dict) -> None:
        """Restore compounding state from an ``export_scrumming_state`` dict.

        Safe against missing keys (treated as defaults). Called by
        ``BotContainer.restore_bots_from_state()`` after construction but
        before registration. The boot handshake reconciles against exchange
        reality afterward.
        """
        if not isinstance(data, dict):
            return

        # Anchor restored first so the Smart Ceiling check below can evaluate
        # against the restored target.
        self._anchor_target_balance = float(
            data.get("anchor_target_balance", self._anchor_target_balance)
        )
        _restored_target = float(data.get("target_balance", self._target_balance))

        # A restored target above anchor is expected (organic growth). But if
        # Smart Ceiling is enabled, refuse a target past the maturity ceiling —
        # that would be stale pre-detonation state; snap it back.
        if getattr(self.config, "position_ceiling_enabled", False):
            try:
                _smart_mult = float(
                    getattr(self.config, "position_ceiling_multiple", 1.0)
                )
                _smart_mult = max(1.0, min(10.0, _smart_mult))
                _smart_ceiling_target = self._anchor_target_balance * _smart_mult
                if _restored_target > _smart_ceiling_target:
                    logger.warning(
                        "restore: persisted target_balance $%.2f "
                        "exceeds Smart Ceiling $%.2f (anchor $%.2f × %.1fx). "
                        "Snapping to Smart Ceiling — likely stale "
                        "pre-detonation state.",
                        _restored_target,
                        _smart_ceiling_target,
                        self._anchor_target_balance,
                        _smart_mult,
                    )
                    _restored_target = _smart_ceiling_target
            except (TypeError, ValueError, AttributeError) as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "import_scrumming_state",
                    type(_sup).__name__,
                    _sup,
                )
        self._target_balance = _restored_target

        try:
            self._standing_surplus_usd = float(
                data.get(
                    "standing_surplus_usd", getattr(self, "_standing_surplus_usd", 0.0)
                )
                or 0.0
            )
            if self._standing_surplus_usd < 0.0:
                self._standing_surplus_usd = 0.0
        except (TypeError, ValueError):
            self._standing_surplus_usd = 0.0
        try:
            self._fold_cycle_cap_consumed = float(
                data.get(
                    "fold_cycle_cap_consumed",
                    getattr(self, "_fold_cycle_cap_consumed", 0.0),
                )
                or 0.0
            )
            if self._fold_cycle_cap_consumed < 0.0:
                self._fold_cycle_cap_consumed = 0.0
        except (TypeError, ValueError):
            self._fold_cycle_cap_consumed = 0.0
        try:
            self._pending_wire_credits = float(
                data.get(
                    "pending_wire_credits", getattr(self, "_pending_wire_credits", 0.0)
                )
                or 0.0
            )
            if self._pending_wire_credits < 0.0:
                self._pending_wire_credits = 0.0
        except (TypeError, ValueError):
            self._pending_wire_credits = 0.0
        # current_holdings is not restored: the exchange is authoritative and
        # the boot handshake repopulates it. Leaves the __init__ default here.
        self._last_trade_price = float(
            data.get("last_trade_price", self._last_trade_price)
        )
        _lts = data.get("last_trade_side", self._last_trade_side)
        if _lts in ("SCRUM", "FOLD"):
            self._last_trade_side = _lts
        else:
            self._last_trade_side = None
        _qrate_saved = data.get("quote_to_usd", None)
        try:
            _qrate_saved = float(_qrate_saved) if _qrate_saved is not None else 0.0
        except (TypeError, ValueError):
            _qrate_saved = 0.0
        if _qrate_saved > 0:
            self._quote_to_usd = _qrate_saved
        try:
            self._pending_stack_buy_usd = float(
                data.get("pending_stack_buy_usd", 0.0) or 0.0
            )
        except (TypeError, ValueError):
            self._pending_stack_buy_usd = 0.0
        self._hyst_armed_fold_side = bool(data.get("hyst_armed_fold_side", False))
        self._hyst_armed_scrum_side = bool(data.get("hyst_armed_scrum_side", False))
        try:
            self._hyst_ref_fold_side = float(data.get("hyst_ref_fold_side", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._hyst_ref_fold_side = 0.0
        try:
            self._hyst_ref_scrum_side = float(
                data.get("hyst_ref_scrum_side", 0.0) or 0.0
            )
        except (TypeError, ValueError):
            self._hyst_ref_scrum_side = 0.0
        # Armed but no reference is incoherent — force disarm.
        if self._hyst_armed_fold_side and self._hyst_ref_fold_side <= 0:
            self._hyst_armed_fold_side = False
        if self._hyst_armed_scrum_side and self._hyst_ref_scrum_side <= 0:
            self._hyst_armed_scrum_side = False
        # A hard-tripped breaker must persist across restart.
        self._cb_hard_tripped = bool(data.get("cb_hard_tripped", False))
        try:
            self._cb_hard_tripped_at = float(data.get("cb_hard_tripped_at", 0.0) or 0.0)
            self._cb_hard_trip_pct = float(data.get("cb_hard_trip_pct", 0.0) or 0.0)
        except (TypeError, ValueError) as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "import_scrumming_state",
                type(_sup).__name__,
                _sup,
            )
        _cb_side = data.get("cb_soft_active_side", None)
        self._cb_soft_active_side = _cb_side if _cb_side in ("scrum", "fold") else None
        try:
            self._cb_soft_cooldown_remaining = int(
                data.get("cb_soft_cooldown_remaining", 0) or 0
            )
            self._cb_soft_trip_pct = float(data.get("cb_soft_trip_pct", 0.0) or 0.0)
        except (TypeError, ValueError) as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "import_scrumming_state",
                type(_sup).__name__,
                _sup,
            )
        # A persisted hard trip forces PAUSED; operator must reset to resume.
        if self._cb_hard_tripped:
            try:
                self.state = BotState.PAUSED
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "import_scrumming_state",
                    type(_sup).__name__,
                    _sup,
                )
        self._dist_accumulator = float(
            data.get("dist_accumulator", self._dist_accumulator)
        )
        self._hedge_bal = float(data.get("hedge_bal", self._hedge_bal))
        self._hedge_trades = int(data.get("hedge_trades", self._hedge_trades))
        self._scrum_target_mode = str(data.get("scrum_target_mode", "search"))
        _side = data.get("scrum_target_side", None)
        self._scrum_target_side = _side if _side in ("upper", "lower", None) else None

        lots_raw = data.get("main_lots", [])
        if isinstance(lots_raw, list):
            self._main_lots = [dict(lot) for lot in lots_raw if isinstance(lot, dict)]
        tranches_raw = data.get("fold_tranches", [])
        # issue #98 defect 4 - THIS FILTER IS A REMOVAL SITE. A stored
        # entry that is not a record is dropped here, and a removal that
        # moves no counter is one unit of permanent negative drift in
        # `created - closed - discarded == standing`. The count is only
        # MEASURED here; it is applied further down, beside the counter
        # restores, because `_tranches_malformed_dropped` has not been
        # read out of `data` yet and a bump written here would be
        # overwritten by that read.
        _unreadable_tranches = 0
        if isinstance(tranches_raw, list):
            self._fold_tranches = [dict(t) for t in tranches_raw if isinstance(t, dict)]
            _unreadable_tranches = len(tranches_raw) - len(self._fold_tranches)
            # Compact wire-credit provenance carried in from older saves so a
            # tranche that never receives another credit stops re-serializing
            # thousands of detail entries.
            _rolled = self._compact_wire_credits()
            if _rolled:
                logger.info(
                    "Bot %s: rolled %d wire-credit detail entries into "
                    "aggregate on restore",
                    self.bot_id,
                    _rolled,
                )

        _created = int(data.get("tranches_created_lifetime", 0) or 0)
        _closed = int(data.get("tranches_closed_lifetime", 0) or 0)
        self._tranches_discarded_lifetime = int(
            data.get("tranches_discarded_lifetime", 0) or 0
        )
        self._wire_credits_discarded_lifetime = float(
            data.get("wire_credits_discarded_lifetime", 0.0) or 0.0
        )
        self._pending_wire_ledger = [
            dict(_e)
            for _e in (data.get("pending_wire_ledger", []) or [])
            if isinstance(_e, dict)
        ]
        self._fold_accumulator = float(data.get("fold_accumulator", 0.0) or 0.0)
        self._tranches_malformed_dropped = int(
            data.get("tranches_malformed_dropped", 0) or 0
        )
        # issue #133 unit 3 -- the second an operator cleared the four
        # counters, 0.0 when they never were. Read through
        # `as_finite_float` because it comes straight off JSON, where
        # `NaN` and `Infinity` are both representable and a bare
        # `float()` would carry either into the predicate that decides
        # whether this bot adopts the exchange balance as its opening
        # position.
        self._tranches_counters_reset_ts = float(
            as_finite_float(data.get("tranches_counters_reset_ts", 0.0)) or 0.0
        )
        # issue #98 defect 4 - the restore filter above removed records.
        # They did not fold, so they are DISCARDED; they were unreadable,
        # so they are ALSO malformed-dropped. The malformed counter is a
        # SUB-COUNT of the discarded one, never a fourth term: only
        # `discarded` appears in the reconciliation the panel prints, and
        # a removal that moved the malformed counter alone left that
        # reconciliation short by exactly the number dropped.
        #
        # NO `stats` MIRROR HERE, DELIBERATELY, AND IT IS NOT AN
        # OVERSIGHT. This restore mirrors NOTHING to `stats` -- not
        # created, not closed, not discarded -- so a mirror written for
        # this one counter would be the only one in the method and would
        # read as a rule the method does not keep.
        if _unreadable_tranches:
            self._tranches_malformed_dropped += _unreadable_tranches
            self._tranches_discarded_lifetime += _unreadable_tranches
            logger.warning(
                "Bot %s: %d stored fold tranche(s) were not readable "
                "records and were dropped on restore. Counted as "
                "discarded, so the tranche ledger still reconciles.",
                self.bot_id,
                _unreadable_tranches,
            )
        self._stack_tranches = [
            dict(_t)
            for _t in (data.get("stack_tranches", []) or [])
            if isinstance(_t, dict)
        ]
        self._stack_created = int(data.get("stack_created", 0) or 0)
        # as_finite_float: JSON NaN/Infinity would crash a bare int().
        self._stack_discarded = int(
            as_finite_float(data.get("stack_discarded", 0)) or 0.0
        )
        self._stack_counters_reset_ts = float(
            as_finite_float(data.get("stack_counters_reset_ts", 0.0)) or 0.0
        )
        # closed > created is structurally impossible; clamp and surface it.
        if _closed > _created:
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"TRANCHE COUNTER REPAIR: persisted closed="
                        f"{_closed} > created={_created}; clamping "
                        f"closed to {_created}. Historical drift "
                        f"surfaced — investigate if recurring."
                    ),
                )
            except Exception:
                logger.warning(
                    "Bot %s tranche counter repair: persisted closed=%d > "
                    "created=%d; clamping closed to %d.",
                    self.bot_id,
                    _closed,
                    _created,
                    _created,
                )
            _closed = _created
        self._tranches_created_lifetime = _created
        self._tranches_closed_lifetime = _closed
        # issue #133 unit 2 -- default 0 on a state file written before
        # the key existed. NO BACK-FILL from `_created`: the count bound
        # is a rule about sells made from here on, and inventing a
        # matching history would publish a ratio nothing measured.
        self._scrum_sells_lifetime = int(data.get("scrum_sells_lifetime", 0) or 0)

        try:
            _saved_side = data.get("target_grow_last_side", None)
            if _saved_side in ("lower", "upper"):
                self._target_grow_last_side = _saved_side
            else:
                self._target_grow_last_side = None
        except Exception:
            self._target_grow_last_side = None

        # Recompute the aggregate from per-tranche sums so a drifted saved
        # value self-heals.
        self._fold_queue_usd = sum(
            float(t.get("usd", 0.0)) for t in self._fold_tranches
        )

        # Warn (don't block) if lots disagree with holdings; the handshake
        # reconciles against the exchange next tick.
        lots_sum = sum(float(lot.get("units", 0.0)) for lot in self._main_lots)
        if self._current_holdings > 0 and lots_sum > 0:
            drift = abs(lots_sum - self._current_holdings) / max(
                self._current_holdings, 1e-9
            )
            if drift > 0.001:
                try:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"STATE RESTORE WARNING: main_lots "
                            f"total {lots_sum:.6f} drifts "
                            f"{drift*100:.2f}% from saved holdings "
                            f"{self._current_holdings:.6f}. "
                            f"Init handshake will reconcile "
                            f"against exchange on next start."
                        ),
                    )
                except Exception:
                    logger.warning(
                        "Bot %s state restore drift: lots=%.6f holdings=%.6f",
                        self.bot_id,
                        lots_sum,
                        self._current_holdings,
                    )

        # Force uninitialised so the boot handshake re-verifies exchange
        # balance next tick and catches drift from the restart window.
        self._initialised = False
