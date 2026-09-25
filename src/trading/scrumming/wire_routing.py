"""Smart Wire routing and wire-credit provenance for ScrummingBot.

Routes scrum/manual/detonation proceeds to downstream bots, applies
incoming wire USD to the fold queue (or parks it when no tranches are
open), and keeps per-tranche wire-credit provenance bounded.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from ...core.event_bus import LINE_KIND_WIRE_FLOW, LINE_KIND_WIRE_STACK
from .sizing import priced_usd

logger = logging.getLogger("acervator.scrumming")

if TYPE_CHECKING:
    from ..scrumming_bot import ScrummingBot as _Host
else:
    _Host = object


_WIRE_CREDIT_CAP = 20
"""Per-tranche cap on wire-credit DETAIL entries.

Everything older is folded into ``wire_credits_rolled``, which keeps the
totals exactly.
"""


def _roll_wire_credit_overflow(tranche: dict) -> int:
    """Trim a tranche's ``wire_credits`` to the cap, folding the excess
    into a lossless ``wire_credits_rolled`` aggregate.

    Returns how many detail entries were rolled up. The aggregate
    preserves count, total USD and USD-per-source, so no credited dollar
    leaves the record — only per-event granularity ages out.
    """
    wc = tranche.get("wire_credits")
    if not isinstance(wc, list) or len(wc) <= _WIRE_CREDIT_CAP:
        return 0
    overflow = wc[:-_WIRE_CREDIT_CAP]
    del wc[:-_WIRE_CREDIT_CAP]
    rolled = tranche.setdefault(
        "wire_credits_rolled",
        {
            "count": 0,
            "total_usd": 0.0,
            "by_source": {},
            "first_ts": None,
            "last_ts": None,
        },
    )
    by_source = rolled.setdefault("by_source", {})
    for e in overflow:
        if not isinstance(e, dict):
            continue
        try:
            usd = float(e.get("usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            usd = 0.0
        src = str(e.get("source", "") or "unknown")
        rolled["count"] = int(rolled.get("count", 0)) + 1
        rolled["total_usd"] = round(float(rolled.get("total_usd", 0.0) or 0.0) + usd, 8)
        by_source[src] = round(float(by_source.get(src, 0.0) or 0.0) + usd, 8)
        ts = e.get("ts")
        if ts is not None:
            if rolled.get("first_ts") is None:
                rolled["first_ts"] = ts
            rolled["last_ts"] = ts
    return len(overflow)


class WireRoutingMixin(_Host):
    """Smart Wire outflow routing, inflow application, and provenance.

    Methods keep ``self``; composed into ``ScrummingBot``. Outflow
    routing is best-effort and never raises into the caller's sell path.
    """

    # ScrummingBot supplies these at runtime; the annotations create no attributes.
    _anchor_target_balance: float
    _pending_wire_ledger: list[dict]
    _target_balance: Any

    def set_smart_wire(self, manager) -> None:
        """Attach a Smart Wire manager for cross-compounding."""
        self._smart_wire_mgr = manager

    def _route_scrum_proceeds_via_wires(
        self, scrum_usd: float, sell_fill: float, label: str = "scrum"
    ) -> float:
        """Route pct% of `scrum_usd` to each outgoing wire's target via
        `apply_wire_income`. Updates Smart Wire ledger for both
        source-side wired_out and target-side wired_in.

        Args:
          scrum_usd:  full proceeds available for routing (USD).
          sell_fill:  the actual fill price (used in audit ref string).
          label:      "scrum" / "manual_scrum" / "detonation" — appears
                      in WireTransaction.wire_type and operator log.

        Returns the total USD routed. Caller subtracts this from local
        accounting so tranches/fold-queue reflect only the local share.

        Failures are caught and logged; never raises (caller's sell path
        continues even if routing has issues).
        """
        _scrum_routed_total = 0.0
        try:
            _wire_mgr = self._smart_wire_mgr
            if _wire_mgr is None or not hasattr(_wire_mgr, "get_outgoing_wires"):
                return 0.0
            _wires = _wire_mgr.get_outgoing_wires(self.bot_id)
            if not _wires:
                return 0.0
            # Clamp total pct to 100% (operator config could sum > 100%).
            _total_pct = sum(float(p) for p in _wires.values())
            _scaling = 1.0
            if _total_pct > 100.0:
                _scaling = 100.0 / _total_pct
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"WIRE WARNING: outgoing wires sum to "
                        f"{_total_pct:.1f}% (>100%); clamping to "
                        f"100% via {_scaling:.4f}× scaling factor."
                    ),
                )
            _bot_refs = getattr(_wire_mgr, "_bot_refs", {}) or {}
            _ledgers = getattr(_wire_mgr, "_ledgers", {}) or {}
            # SWOS safety math: compute once per scrum event, divide by N
            # outbound wires, cap each wire at min(operator_pct, per_wire_safe).
            _n_wires = max(1, len(_wires))
            _swos_safe_pct = 100.0
            _per_wire_safe_pct = 100.0
            try:
                _swos_inputs = self.get_swos_inputs()
                if _swos_inputs:
                    from ..smart_wire import compute_safe_outflow_pct

                    _swos_safe_pct = compute_safe_outflow_pct(
                        scrum_profit_usd=float(scrum_usd), **_swos_inputs
                    )
                    _per_wire_safe_pct = _swos_safe_pct / _n_wires
                    logger.debug(
                        "SWOS %s (scrum-route): safe=%.2f%% ÷ %d "
                        "wires = %.2f%% per-wire (scrum_usd=$%.4f)",
                        self.bot_id,
                        _swos_safe_pct,
                        _n_wires,
                        _per_wire_safe_pct,
                        scrum_usd,
                    )
            except Exception as _swos_exc:  # noqa: BLE001 - best-effort
                logger.debug(
                    "SWOS %s (scrum-route) pre-check raised %s — "
                    "falling back to raw pct.",
                    self.bot_id,
                    _swos_exc,
                )
            for _tgt_id, _pct in _wires.items():
                try:
                    _eff_pct = min(float(_pct) * _scaling, _per_wire_safe_pct)
                    _routed = scrum_usd * (_eff_pct / 100.0)
                    if _routed < 0.01:  # dust floor
                        continue
                    _tgt_bot = _bot_refs.get(_tgt_id)
                    if _tgt_bot is None:
                        continue
                    if not hasattr(_tgt_bot, "apply_wire_income"):
                        continue
                    _apply_result = _tgt_bot.apply_wire_income(
                        usd=_routed, source=self.bot_id, ref=f"{label}@{sell_fill:.8f}"
                    )
                    _scrum_routed_total += _routed
                    try:
                        _mode = (
                            _apply_result.get("mode", "?")
                            if isinstance(_apply_result, dict)
                            else "?"
                        )
                        _tgt_short = (
                            str(_tgt_id)[:8] + "…"
                            if len(str(_tgt_id)) > 8
                            else str(_tgt_id)
                        )
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"[WIRE FIRE] scrum-route: ${_routed:.4f} "
                                f"→ {_tgt_short} (pct={_eff_pct:.2f}%, "
                                f"landed: {_mode})"
                            ),
                        )
                    except Exception as _sup:  # noqa: BLE001 - log best-effort
                        logger.debug(
                            "suppressed in %s: %s: %s",
                            "_route_scrum_proceeds_via_wires",
                            type(_sup).__name__,
                            _sup,
                        )
                    _txns = getattr(_wire_mgr, "_transactions", None)
                    if _txns is not None:
                        try:
                            from ..smart_wire import WireTransaction
                            import time as _wt_time

                            _txns.append(
                                WireTransaction(
                                    timestamp=int(_wt_time.time()),
                                    source_bot=self.bot_id,
                                    target_bot=str(_tgt_id),
                                    amount=float(_routed),
                                    wire_type=f"{label.upper()}_ROUTE",
                                    reason=(
                                        f"{_eff_pct:.2f}% of "
                                        f"${scrum_usd:.4f} {label}"
                                    ),
                                )
                            )
                        except Exception as _sup:  # noqa: BLE001 - audit-only
                            logger.debug(
                                "suppressed in %s: %s: %s",
                                "_route_scrum_proceeds_via_wires",
                                type(_sup).__name__,
                                _sup,
                            )
                    if _tgt_id in _ledgers:
                        try:
                            _ledgers[_tgt_id].wired_in += float(_routed)
                        except Exception as _sup:  # noqa: BLE001 - ledger probe
                            logger.debug(
                                "suppressed in %s: %s: %s",
                                "_route_scrum_proceeds_via_wires",
                                type(_sup).__name__,
                                _sup,
                            )
                    if self.bot_id in _ledgers:
                        try:
                            _ledgers[self.bot_id].wired_out += float(_routed)
                        except Exception as _sup:  # noqa: BLE001 - ledger probe
                            logger.debug(
                                "suppressed in %s: %s: %s",
                                "_route_scrum_proceeds_via_wires",
                                type(_sup).__name__,
                                _sup,
                            )
                except Exception as _wone_exc:
                    logger.warning(
                        "Bot %s wire route to %s failed (label=%s): %s",
                        self.bot_id,
                        _tgt_id,
                        label,
                        _wone_exc,
                    )
            if _scrum_routed_total > 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"WIRE OUT ({label.upper()}): routed "
                        f"${_scrum_routed_total:.4f} of "
                        f"${scrum_usd:.4f} {label} proceeds "
                        f"across {len(_wires)} target bot(s). "
                        f"Remaining "
                        f"${scrum_usd - _scrum_routed_total:.4f} "
                        f"stays with this bot."
                    ),
                )
        except Exception as _wr_exc:
            logger.warning(
                "Bot %s %s-time wire routing raised: %s "
                "(continues with full proceeds to local accounting)",
                self.bot_id,
                label,
                _wr_exc,
            )
            return 0.0
        return _scrum_routed_total

    def apply_wire_income(self, usd: float, source: str, ref: str = "") -> dict:
        """Apply incoming Smart Wire USD to this bot's fold queue.

        Semantic (two cases):

        1. `_fold_tranches` non-empty: distribute `usd` EVENLY across
           all existing tranches. Each tranche's `usd` grows by
           `usd / len(tranches)`. `_fold_queue_usd` recomputed as the
           sum. Each tranche gains a `wire_credits` provenance entry
           naming the source bot + ref.

        2. `_fold_tranches` empty: park the USD in `_pending_wire_credits`
           with a ledger entry. The bucket drains at the next fold-tranche
           build on any of the three build loops, and on state restore --
           see `_land_pending_wire_credits`. On the SCRUM loop with a queue
           that was empty, the whole pool goes to the first new tranche and
           its initial `usd` = scrum_usd + pending.

        A stack-at-entry fast path bumps the target and queues an
        aggressive buy when the bot is at its center line and at its
        entry price (guarded by `config.wire_inflow_stack_pct`).

        Non-blocking: caller ignores return value in happy path. Rejects
        invalid USD with {"applied": False, "reason": ...}.
        """
        try:
            u = float(usd)
        except (TypeError, ValueError):
            return {"applied": False, "reason": f"usd must be numeric; got {usd!r}"}
        if u <= 0:
            return {"applied": False, "reason": f"usd must be > 0; got {u}"}

        src = str(source or "?")
        rf = str(ref or "")
        import time as _t

        credit = {"ts": _t.time(), "source": src, "usd": u, "ref": rf}

        # Stack-at-entry: at centre line and at entry price, the wire raises
        # _target_balance and queues a buy instead of feeding the fold queue.
        try:
            stack_pct = float(getattr(self.config, "wire_inflow_stack_pct", 1.0) or 0)
        except (TypeError, ValueError):
            stack_pct = 0.0
        _stack_eligible = False
        _stack_reason = ""
        _target = 0.0
        _entry_px = 0.0
        if stack_pct > 0:
            try:
                _last_px = getattr(self, "_last_trade_price", 0) or float(
                    getattr(self.stats, "current_price", 0)
                )
                if _last_px <= 0:
                    _stack_reason = "no last-trade price yet"
                else:
                    _qrate_local = float(self._quote_to_usd or 1.0)
                    _pos_usd = priced_usd(
                        self._current_holdings, _last_px, _qrate_local
                    )
                    _target = float(self._target_balance)
                    _band_usd = _target * stack_pct / 100.0
                    _at_center = abs(_pos_usd - _target) <= _band_usd
                    _entry_px = 0.0
                    if self._main_lots:
                        try:
                            _entry_px = float(
                                self._main_lots[0].get("initial_buy_price", 0) or 0
                            )
                        except (TypeError, ValueError):
                            _entry_px = 0.0
                    _at_entry = (
                        _entry_px > 0
                        and abs(_last_px - _entry_px) <= _entry_px * stack_pct / 100.0
                    )
                    if _at_center and _at_entry and _target > 0:
                        _stack_eligible = True
                    elif not _at_center:
                        _stack_reason = (
                            f"position ${_pos_usd:.2f} not within "
                            f"{stack_pct:.1f}% band of target ${_target:.2f}"
                        )
                    elif _entry_px <= 0:
                        _stack_reason = "no entry price (no main lots)"
                    elif not _at_entry:
                        _stack_reason = (
                            f"price ${_last_px:.6f} not within "
                            f"{stack_pct:.1f}% of entry ${_entry_px:.6f}"
                        )
            except Exception as _stack_exc:  # noqa: BLE001 - reason emitted downstream
                _stack_reason = f"eval raised {type(_stack_exc).__name__}"

        if _stack_eligible:
            self._target_balance = float(self._target_balance) + u
            self._anchor_target_balance = float(self._anchor_target_balance) + u
            try:
                self.config.target_balance = self._target_balance
            except Exception as _sup:  # noqa: BLE001 - best-effort mirror
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "apply_wire_income",
                    type(_sup).__name__,
                    _sup,
                )
            self._pending_stack_buy_usd = (
                float(getattr(self, "_pending_stack_buy_usd", 0.0) or 0.0) + u
            )
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"WIRE STACK: +${u:.2f} from {src} stacked at entry. "
                        f"Target ${_target:.2f} → ${self._target_balance:.2f} "
                        f"(at center line ±{stack_pct:.1f}%, at entry "
                        f"${_entry_px:.6f}). Next tick will acquire "
                        f"{u:.2f}-USD-worth of {self.config.target_asset} "
                        f"via aggressive rebalance. ref={rf}"
                    ),
                    kind=LINE_KIND_WIRE_STACK,
                )
            except Exception as _sup:  # noqa: BLE001 - best-effort mirror
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "apply_wire_income",
                    type(_sup).__name__,
                    _sup,
                )
            return {
                "applied": True,
                "mode": "stacked",
                "stacked_usd": u,
                "new_target_balance": self._target_balance,
                "entry_price": _entry_px,
            }
        elif stack_pct > 0 and _stack_reason:
            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"WIRE STACK skipped ({_stack_reason}). "
                        f"Income falls through to "
                        f"{'distribute' if self._fold_tranches else 'pending'}."
                    ),
                    kind=LINE_KIND_WIRE_STACK,
                )
            except Exception as _sup:  # noqa: BLE001 - best-effort mirror
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "apply_wire_income",
                    type(_sup).__name__,
                    _sup,
                )

        if self._fold_tranches:
            # Case 1 — even distribution across existing tranches
            share = self._spread_wire_usd_over_fold_queue(u, [credit])
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"WIRE INCOME: +${u:.4f} from {src} distributed "
                    f"evenly across {len(self._fold_tranches)} "
                    f"tranche(s) (${share:.4f}/tranche). Fold queue "
                    f"now ${self._fold_queue_usd:.4f}."
                ),
                kind=LINE_KIND_WIRE_FLOW,
            )
            logger.info(
                "Bot %s wire income %.4f from %s → %d tranches",
                self.bot_id,
                u,
                src,
                len(self._fold_tranches),
            )
            return {
                "applied": True,
                "mode": "distributed",
                "tranches_credited": len(self._fold_tranches),
                "per_tranche_usd": share,
                "new_fold_queue_usd": self._fold_queue_usd,
            }

        # Case 2 — no tranches yet; park in pending
        self._pending_wire_credits += u
        self._pending_wire_ledger.append(credit)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"WIRE INCOME PENDING: +${u:.4f} from {src} parked "
                f"(no open tranches). Pending total "
                f"${self._pending_wire_credits:.4f}. Lands in the "
                f"fold queue when the next sell opens a tranche."
            ),
            kind=LINE_KIND_WIRE_FLOW,
        )
        logger.info(
            "Bot %s wire income %.4f from %s → pending " "(no tranches)",
            self.bot_id,
            u,
            src,
        )
        return {
            "applied": True,
            "mode": "pending",
            "pending_total": self._pending_wire_credits,
            "ledger_size": len(self._pending_wire_ledger),
        }

    def _spread_wire_usd_over_fold_queue(self, usd: float, entries: list) -> float:
        """Add `usd` evenly to every standing fold tranche.

        Each tranche's `usd` grows by `usd / len(tranches)` and gains one
        `wire_credits` entry per element of `entries`, each entry's own
        `usd` divided by the same count. Recomputes `_fold_queue_usd`
        from the per-tranche sums.

        Returns the per-tranche share, or 0.0 when the fold queue holds
        no tranche.
        """
        tranches = self._fold_tranches
        if not tranches:
            return 0.0
        n = len(tranches)
        share = float(usd) / n
        for t in tranches:
            t["usd"] = float(t.get("usd", 0) or 0) + share
            self._add_wire_credits(
                t,
                [
                    {
                        "ts": e.get("ts"),
                        "source": e.get("source", "?"),
                        "usd": float(e.get("usd", 0.0) or 0.0) / n,
                        "ref": e.get("ref", ""),
                    }
                    for e in entries
                ],
            )
        self._refresh_fold_queue_total()
        return share

    def _refresh_fold_queue_total(self) -> float:
        """Set `_fold_queue_usd` to the total the tranche rows hold.

        `_fold_queue_usd` is the scalar the Fold Tranches panel prints
        and the fold gate reads. Every write to a tranche's `usd` moves
        it. Returns the new total.
        """
        total = 0.0
        for t in getattr(self, "_fold_tranches", None) or []:
            total += float(t.get("usd", 0) or 0)
        self._fold_queue_usd = total
        return total

    def _land_pending_wire_credits(self) -> float:
        """Move the parked pool into a fold queue that now holds tranches.

        issue #133 unit 11. `_pending_wire_credits` is the bucket
        `apply_wire_income` case 2 fills when the fold queue is empty.
        Case 1 distributes evenly the moment a tranche exists, so a
        parked pool standing beside an open tranche is money that missed
        its destination.

        Three build loops create fold tranches -- the SCRUM sell, the
        DIST sell and `_execute_manual_rebalance`. Only the SCRUM loop
        drained the bucket, and only when the queue was empty before it,
        so a DIST or manual sell that opened the first tranche stranded
        the pool until the queue emptied again and a SCRUM fired.

        Called after every build loop and on state restore. Distribution
        is `_spread_wire_usd_over_fold_queue`, the same routine case 1
        uses, so wire USD reaches the same place whether it arrives with
        tranches standing or lands afterwards.

        Returns the landed amount. Returns 0.0 when the pool is empty or
        the fold queue holds no tranche.
        """
        pending = float(getattr(self, "_pending_wire_credits", 0.0) or 0.0)
        tranches = getattr(self, "_fold_tranches", None) or []
        if pending <= 0.0 or not tranches:
            return 0.0

        n = len(tranches)
        ledger = list(getattr(self, "_pending_wire_ledger", []) or [])
        share = self._spread_wire_usd_over_fold_queue(pending, ledger)
        self._pending_wire_credits = 0.0
        self._pending_wire_ledger = []

        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"WIRE LANDED: ${pending:.4f} of parked credit spread "
                    f"across {n} standing tranche(s) "
                    f"(${share:.4f}/tranche). Fold queue now "
                    f"${self._fold_queue_usd:.4f}. Pending cleared."
                ),
            )
        except Exception as exc:  # noqa: BLE001 - operator log only
            logger.debug("_land_pending_wire_credits: log emit failed: %s", exc)

        logger.info(
            "Bot %s landed %.4f pending wire credits across %d tranches",
            self.bot_id,
            pending,
            n,
        )
        return pending

    def _add_wire_credits(self, tranche: dict, entries: list) -> None:
        """Append wire-credit provenance to a tranche, bounded.

        Every wire-income event appends one entry to every open tranche,
        so growth is credits × tranches. Detail is capped at the most
        recent ``_WIRE_CREDIT_CAP`` entries; older entries fold into a
        running ``wire_credits_rolled`` aggregate that preserves the
        totals (count, total USD, USD per source) exactly. No credited
        dollar disappears from the record; only per-event granularity
        ages out.
        """
        if entries:
            tranche.setdefault("wire_credits", []).extend(entries)
        _roll_wire_credit_overflow(tranche)

    def _compact_wire_credits(self) -> int:
        """Fold already-oversized tranches down on state restore.

        The cap in ``_add_wire_credits`` only engages on the next append,
        so a tranche that never receives another credit would never
        compact. Returns the number of detail entries rolled into the
        aggregate.
        """
        rolled = 0
        for t in getattr(self, "_fold_tranches", None) or []:
            rolled += _roll_wire_credit_overflow(t)
        return rolled

    def _absorb_pending_wire_credits_into(self, new_tranche: dict) -> float:
        """Merge `_pending_wire_credits` into a freshly-formed tranche.

        Called from `_execute_sell` at the tranche-append site. If the
        pending bucket has usd > 0, the new tranche's `usd` grows by that
        amount, the bucket clears, and the ledger entries become this
        tranche's `wire_credits` provenance.

        The deposit is EXEMPT from `scrum_fold_pct`: this method adds USD
        and NO units, and the fold-fraction block at the call site prices
        each new tranche's units at the scrum's own net rate and scales
        only that part, so wired-in money reaches the fold queue at full
        value on a bot folding less than 100%.

        Returns the absorbed amount (for logging).
        """
        pending = float(self._pending_wire_credits or 0.0)
        if pending <= 0:
            return 0.0
        new_tranche["usd"] = float(new_tranche.get("usd", 0) or 0) + pending
        self._add_wire_credits(new_tranche, list(self._pending_wire_ledger))
        self._pending_wire_credits = 0.0
        self._pending_wire_ledger = []
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"WIRE ABSORB: ${pending:.4f} pending wire credits "
                f"absorbed into new tranche (usd now "
                f"${new_tranche['usd']:.4f}). Pending cleared."
            ),
        )
        logger.info(
            "Bot %s absorbed %.4f pending wire credits into new tranche",
            self.bot_id,
            pending,
        )
        return pending

    def clear_pending_wire_credits(self, reason: str = "operator") -> dict:
        """Discard this bot's parked wire credits. Trades nothing.

        `_pending_wire_credits` is bookkeeping, not custody: no code path
        places an order, withdraws, or transfers exchange funds on the
        strength of it. All bots share one exchange wallet, so a Smart
        Wire route is an accounting reallocation of a claim on shared
        cash — the source bot already gave the claim up at the scrum
        site. Clearing the credit releases the earmark; the cash stays in
        the wallet as ordinary spendable balance.

        Returns a report of what was discarded. Never raises.
        """
        amount = float(getattr(self, "_pending_wire_credits", 0.0) or 0.0)
        ledger = list(getattr(self, "_pending_wire_ledger", []) or [])
        report = {
            "bot_id": self.bot_id,
            "symbol": getattr(self.config, "symbol", ""),
            "usd": round(amount, 8),
            "ledger_entries": len(ledger),
            "reason": str(reason),
        }
        if amount <= 1e-9 and not ledger:
            return report

        self._pending_wire_credits = 0.0
        self._pending_wire_ledger = []
        self._wire_credits_discarded_lifetime = round(
            float(getattr(self, "_wire_credits_discarded_lifetime", 0.0) or 0.0)
            + amount,
            8,
        )

        try:
            self.stats.wire_credits_discarded_lifetime = (
                self._wire_credits_discarded_lifetime
            )
        except Exception as exc:  # noqa: BLE001 - telemetry mirror only
            logger.debug("clear_pending_wire_credits: stats mirror failed: %s", exc)

        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"WIRE CREDITS CLEARED ({reason}): discarded "
                    f"${amount:.4f} of parked credit across "
                    f"{len(ledger)} ledger entrie(s). This releases "
                    f"an earmark only — no order was placed and no "
                    f"funds moved; the cash remains in the wallet "
                    f"as spendable balance."
                ),
            )
        except Exception as exc:  # noqa: BLE001 - diagnostic best-effort
            logger.debug("clear_pending_wire_credits: log emit failed: %s", exc)

        logger.info(
            "Bot %s: cleared $%.4f pending wire credits (%d ledger "
            "entries) reason=%s",
            self.bot_id,
            amount,
            len(ledger),
            reason,
        )
        return report
