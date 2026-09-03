"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
smart_wire.py routes realized profit between cooperating bots and
tracks its provenance.

Each bot registers with SmartWireManager. A registered wire moves a
percentage of a source bot's realized fold profit to a target bot on
every fold. process_wires separately deploys mature profit into
MR Inspector-flagged undervalued bots and wires a percentage back to
the predominant funding source. Mature profit above a bot's Primary
Provenance Source threshold can fund a new bot through the cascade
spawn.
"""

from __future__ import annotations
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("acervator.smart_wire")


def compute_safe_outflow_pct(
    scrum_profit_usd: float,
    target_balance_usd: float,
    current_price: float,
    band_lower: float,
    band_upper: float,
    next_fold_ammo_usd: float,
    current_cash_usd: float,
    compound_growth_pct: float,
    retained_this_cycle_usd: float,
) -> float:
    """Pure function; no I/O or bot references.

    Returns the maximum percentage of scrum_profit_usd safe to wire
    out without reducing the source bot's Fold or Compounding-Growth
    reserve. Returns a float in [0.0, 100.0]; 0.0 when
    scrum_profit_usd is non-positive or the exportable share is
    under a 1% floor.
    """
    if scrum_profit_usd <= 0:
        return 0.0

    # 0 = at/below band_lower (imminent Fold); 1 = at/above band_upper (deep in Scrum).
    if band_upper <= band_lower:
        # Degenerate band (upper <= lower): treated as imminent Fold.
        distance_to_fold_pct = 0.0
    else:
        distance_to_fold_pct = max(
            0.0, min(1.0, (current_price - band_lower) / (band_upper - band_lower))
        )

    # Safety factor ranges 0.2 (deep Scrum) to 2.0 (imminent Fold).
    if band_upper <= band_lower:
        safety_factor = 2.0  # forced conservative
    else:
        safety_factor = 0.2 + 1.8 * (1.0 - distance_to_fold_pct)

    fold_shortfall_usd = max(0.0, float(next_fold_ammo_usd) - float(current_cash_usd))
    fold_reserve_usd = fold_shortfall_usd * safety_factor

    compound_target_usd = float(target_balance_usd) * float(compound_growth_pct) / 100.0
    compound_reserve_usd = max(
        0.0, compound_target_usd - float(retained_this_cycle_usd)
    )

    reserves_total_usd = fold_reserve_usd + compound_reserve_usd
    exportable_usd = max(0.0, scrum_profit_usd - reserves_total_usd)
    raw_safe_pct = 100.0 * exportable_usd / scrum_profit_usd

    # Sub-1% exportable share is dust; returns 0.
    if raw_safe_pct < 1.0:
        return 0.0
    return min(100.0, raw_safe_pct)


@dataclass
class WireTransaction:
    """Record of a single smart wire transfer."""

    timestamp: int
    source_bot: str
    target_bot: str
    amount: float
    wire_type: str  # "MR_FUND" | "WIRE_BACK"
    reason: str = ""


@dataclass
class BotLedger:
    """Profit provenance ledger for a single bot.

    starting_balance is the capital this bot was seeded with, from
    SEED or from a funding bot's mature-profit transfer; immutable
    after init. mature_profit_allocated is the cumulative amount
    transferred to spawn child bots.

    Bot N may spawn bot N+1 once its mature profit reaches the
    starting balance of its Primary Provenance Source (PPS), so
    every bot in a cascade starts with the same capital as its
    funder.
    """

    bot_id: str
    asset: str
    total_profit: float = 0.0
    available_profit: float = 0.0  # Profit available for wiring
    wired_in: float = 0.0
    wired_out: float = 0.0
    provenance: dict = field(default_factory=dict)  # source_bot_id → amount
    starting_balance: float = 0.0
    mature_profit_allocated: float = 0.0

    # Consumed directly by src/gui/live_settings/bot_swarm_tab.py, which
    # falls back to 70% if this import fails.
    MATURE_RATIO: float = 0.7

    @property
    def predominant_source(self) -> Optional[str]:
        """Find the non-SEED bot that funded this bot the most."""
        sources = {k: v for k, v in self.provenance.items() if k != "SEED" and v > 0}
        if not sources:
            return None
        return max(sources, key=sources.get)

    @property
    def mature_profit_total(self) -> float:
        """Total mature profit earned across history.

        Returns total_profit * MATURE_RATIO, or 0.0 when total_profit
        is not positive.
        """
        if self.total_profit <= 0:
            return 0.0
        return self.total_profit * self.MATURE_RATIO

    @property
    def mature_profit_available(self) -> float:
        """Mature profit not yet allocated to child spawns.

        Returns mature_profit_total - mature_profit_allocated.
        can_fund_new_bot compares this against the PPS starting
        balance; it can go negative after a spawn if the bot then
        loses money.
        """
        return self.mature_profit_total - self.mature_profit_allocated


class SmartWireManager:
    """Manages the cross-compounding network between accumulation bots.

    Usage:
        mgr = SmartWireManager(wire_back_pct=0.30, mr_fund_pct=0.15)
        mgr.register_bot("bot_btc", "BTC/USD", seed_amount=200)
        mgr.register_bot("bot_eth", "ETH/USD", seed_amount=200)
        mgr.record_profit("bot_btc", amount=5.50)
        wires = mgr.process_wires(undervalued_bots=["bot_eth"])
    """

    def __init__(
        self,
        wire_back_pct: float = 0.30,
        mr_fund_pct: float = 0.15,
        min_wire_amount: float = 0.01,
        bus=None,
    ):
        # None falls back to get_event_bus() lazily at each emit site;
        # an injected bus keeps a sim manager's wire activity off the live bus.
        self._bus = bus
        self._wire_back_pct = wire_back_pct
        self._mr_fund_pct = mr_fund_pct
        self._min_wire = min_wire_amount
        self._ledgers: dict[str, BotLedger] = {}
        self._transactions: list[WireTransaction] = []
        self._enabled = True
        # source_bot_id -> {target_bot_id: pct}. Set via register_wire, called
        # from BotManager's wire.created handler; read by distribute_fold_profit.
        self._wires: dict[str, dict[str, float]] = {}
        # Plain dict, not a weakref map; BotManager calls detach_bot on
        # bot deletion to remove the reference.
        self._bot_refs: dict[str, object] = {}

    def attach_bot(self, bot_id: str, bot_ref: object) -> None:
        """Register a bot instance so distribute_fold_profit can reach
        its apply_wire_income. Called by BotManager after every bot
        creation alongside bot.set_smart_wire(self).
        """
        self._bot_refs[bot_id] = bot_ref
        # A wire is deployable only when both endpoints resolve to an
        # attached bot; recording each attachment lets that count be computed.
        try:
            from src.core.signal_contract import emit as _wb

            _wb(
                "topology.09.001.state_transition.bot_attached",
                actual=str(bot_id),
                context={"attached_total": len(self._bot_refs)},
            )
        except Exception:  # noqa: BLE001,S110 - advisory
            pass

    def detach_bot(self, bot_id: str) -> None:
        """Remove a bot instance + all wires that reference it on
        either side. Called on bot deletion.
        """
        self._bot_refs.pop(bot_id, None)
        self._ledgers.pop(bot_id, None)
        # Drop wires sourced from this bot
        self._wires.pop(bot_id, None)
        # Drop wires targeting this bot (scan all sources)
        for src in list(self._wires.keys()):
            self._wires[src].pop(bot_id, None)
            if not self._wires[src]:
                del self._wires[src]

    def register_wire(self, source_id: str, target_id: str, pct: float) -> dict:
        """Create or update the wire from source_id to target_id with the
        given percentage (0-100), overwriting any existing pct in place.

        Returns {"applied": bool, "reason": str, "replaced_pct": ...}.
        replaced_pct is the pair's prior percentage, or None if it was
        previously unwired.
        """
        if source_id == target_id:
            return {"applied": False, "reason": "source and target must differ"}
        # float() can raise OverflowError (not just TypeError/ValueError)
        # on an int literal too large for a double.
        try:
            p = float(pct)
        except Exception as exc:
            return {
                "applied": False,
                "reason": (
                    f"pct could not be read as a number: "
                    f"{pct!r} ({type(exc).__name__}: {exc})"
                ),
            }
        # nan is unordered, so p<=0 and p>100 are both False; math.isnan
        # must be checked explicitly to reject it.
        if math.isnan(p):
            return {
                "applied": False,
                "reason": (
                    "pct must be a real number; got nan, "
                    "which is unordered - it is not outside "
                    "(0, 100], both comparisons are False, "
                    "and that is why it used to be accepted"
                ),
            }
        if p <= 0 or p > 100:
            return {"applied": False, "reason": f"pct must be in (0, 100]; got {p}"}
        prior = self._wires.get(source_id, {}).get(target_id)
        self._wires.setdefault(source_id, {})[target_id] = p
        if prior is None:
            logger.info(
                "SmartWire: registered %s -> %s @ %.2f%%", source_id, target_id, p
            )
        else:
            logger.warning(
                "SmartWire: OVERWROTE %s -> %s: %.2f%% replaced by %.2f%%",
                source_id,
                target_id,
                float(prior),
                p,
            )
        return {
            "applied": True,
            "source_id": source_id,
            "target_id": target_id,
            "pct": p,
            "replaced_pct": (None if prior is None else float(prior)),
        }

    def unregister_wire(self, source_id: str, target_id: str) -> bool:
        """Remove the wire. Returns True if it existed, False otherwise."""
        if source_id in self._wires and target_id in self._wires[source_id]:
            del self._wires[source_id][target_id]
            if not self._wires[source_id]:
                del self._wires[source_id]
            logger.info("SmartWire: unregistered %s -> %s", source_id, target_id)
            return True
        return False

    def get_outgoing_wires(self, source_id: str) -> dict[str, float]:
        """Return the source bot's {target_id: pct} map (or empty)."""
        return dict(self._wires.get(source_id, {}))

    def export_wires(self) -> list[dict]:
        """Snapshot the wire registry as a JSON-serializable list of
        {source_id, target_id, pct} dicts. Used by BotManager to
        persist swarm state across restart."""
        out: list[dict] = []
        for src, targets in self._wires.items():
            for tgt, pct in targets.items():
                out.append(
                    {
                        "source_id": str(src),
                        "target_id": str(tgt),
                        "pct": float(pct),
                    }
                )
        return out

    def export_ledgers(self) -> list[dict]:
        """Snapshot each BotLedger as a JSON-serializable dict so the
        per-bot wired_in/wired_out totals + provenance survive restart.
        Returns a list of dicts that can be passed to import_ledgers().
        """
        out: list[dict] = []
        dropped = 0
        for bot_id, ledger in self._ledgers.items():
            try:
                out.append(
                    {
                        "bot_id": str(bot_id),
                        "asset": str(getattr(ledger, "asset", "") or ""),
                        "total_profit": float(
                            getattr(ledger, "total_profit", 0.0) or 0.0
                        ),
                        "available_profit": float(
                            getattr(ledger, "available_profit", 0.0) or 0.0
                        ),
                        "wired_in": float(getattr(ledger, "wired_in", 0.0) or 0.0),
                        "wired_out": float(getattr(ledger, "wired_out", 0.0) or 0.0),
                        "provenance": dict(getattr(ledger, "provenance", {}) or {}),
                        "starting_balance": float(
                            getattr(ledger, "starting_balance", 0.0) or 0.0
                        ),
                        "mature_profit_allocated": float(
                            getattr(ledger, "mature_profit_allocated", 0.0) or 0.0
                        ),
                    }
                )
            except Exception as exc:
                # A dropped row's wired_in/wired_out and provenance are
                # not saved. container/restore.py's save_all_state (lines
                # 32-69) catches anything that escapes export_ledgers and
                # still calls save_state, so one bad row does not erase
                # every row.
                dropped += 1
                logger.warning(
                    "SmartWire: export DROPPED ledger row for %s "
                    "(%s: %s) - its wired_in/wired_out history is NOT "
                    "in this save and is not recoverable from it",
                    bot_id,
                    type(exc).__name__,
                    exc,
                )
                continue
        if dropped:
            logger.warning(
                "SmartWire: exported %d of %d ledger row(s); " "%d dropped",
                len(out),
                len(self._ledgers),
                dropped,
            )
        return out

    def import_ledgers(self, ledgers: list[dict]) -> int:
        """Restore per-bot ledger totals from a snapshot produced by
        export_ledgers(). Existing ledger entries (from register_bot
        called during attach_bot at startup) are UPDATED in place
        with the persisted totals; missing entries are created.
        Returns count of ledgers successfully imported.
        """
        if not isinstance(ledgers, list):
            return 0
        n = 0
        offered = 0
        dropped = 0
        # offered counts every row before the guards below, so a
        # guard-dropped row is not invisible to the reconciling total.
        malformed = 0  # row was not a dict at all
        unidentified = 0  # row was a dict but carried no usable bot_id
        for row in ledgers:
            offered += 1
            if not isinstance(row, dict):
                malformed += 1
                logger.warning(
                    "SmartWire: import DROPPED ledger row %d of %d - it "
                    "is a %s, not a row. No writer here produces that, "
                    "so the save is corrupt; one bot's wired_in/"
                    "wired_out history is not in this session and the "
                    "row cannot say which bot",
                    offered,
                    len(ledgers),
                    type(row).__name__,
                )
                continue
            bid = row.get("bot_id")
            if not bid:
                unidentified += 1
                logger.warning(
                    "SmartWire: import DROPPED ledger row %d of %d - "
                    "bot_id is %r, so the row cannot be applied to any "
                    "bot. Its wired_in/wired_out history is not in this "
                    "session",
                    offered,
                    len(ledgers),
                    bid,
                )
                continue
            bid = str(bid)
            try:
                if bid not in self._ledgers:
                    # Skeleton entry; attach_bot may later overwrite asset,
                    # and starting_balance here keeps cascade math intact.
                    self._ledgers[bid] = BotLedger(
                        bot_id=bid,
                        asset=str(row.get("asset", "") or ""),
                        starting_balance=float(row.get("starting_balance", 0.0) or 0.0),
                    )
                lg = self._ledgers[bid]
                lg.total_profit = float(row.get("total_profit", 0.0) or 0.0)
                lg.available_profit = float(row.get("available_profit", 0.0) or 0.0)
                lg.wired_in = float(row.get("wired_in", 0.0) or 0.0)
                lg.wired_out = float(row.get("wired_out", 0.0) or 0.0)
                _prov = row.get("provenance", {})
                if isinstance(_prov, dict):
                    lg.provenance = {str(k): float(v or 0.0) for k, v in _prov.items()}
                lg.mature_profit_allocated = float(
                    row.get("mature_profit_allocated", 0.0) or 0.0
                )
                # Only overlay when attach_bot's register_bot has not
                # already set asset/starting_balance.
                if not lg.asset and row.get("asset"):
                    lg.asset = str(row["asset"])
                if not lg.starting_balance and row.get("starting_balance"):
                    lg.starting_balance = float(row["starting_balance"])
                n += 1
            except Exception as exc:
                # The overlay writes field by field, so an exception here
                # leaves the row partially applied to an existing ledger.
                # BotManager.restore_smart_wires_from_state catches anything
                # escaping this call; narrowing drops every later row too.
                dropped += 1
                logger.warning(
                    "SmartWire: import DROPPED ledger row for %s "
                    "(%s: %s) - the row is PARTIALLY applied and that "
                    "bot's wire totals are wrong for this session",
                    bid,
                    type(exc).__name__,
                    exc,
                )
                continue
        if n > 0:
            logger.info("SmartWire: imported %d ledger(s) from saved state", n)
        lost = malformed + unidentified + dropped
        if lost:
            logger.warning(
                "SmartWire: import accepted %d of %d ledger row(s) "
                "offered; %d lost (%d raised, %d not a row, %d had no "
                "bot_id) - each lost row is one bot's lifetime "
                "wired_in/wired_out and provenance, absent for this "
                "session and not recoverable from the save",
                n,
                offered,
                lost,
                dropped,
                malformed,
                unidentified,
            )
        return n

    def import_wires(self, wires: list[dict]) -> int:
        """Restore wires from a snapshot produced by export_wires().
        Returns the count of successfully imported wires. Idempotent —
        re-importing the same snapshot is a no-op (same key overwrite).
        """
        if not isinstance(wires, list):
            return 0

        # Starts after the type guard, which returns without emitting a duration.
        _dur_t0 = time.monotonic()
        n = 0
        offered = 0
        # A lost wire means distribute_fold_profit's
        # self._wires.get(source_id) never sees that route: the source
        # bot's fold profit is not divided and the target's wired_in
        # does not grow.
        #
        # _wires has two writers (register_wire, this method), both
        # rejecting the same range; a dropped row means the save is corrupt.
        malformed = 0  # row was not a dict at all
        unreadable = 0  # float(pct) raised
        unroutable = 0  # no endpoint, or pct outside 0 < pct <= 100
        for w in wires:
            offered += 1
            if not isinstance(w, dict):
                malformed += 1
                logger.warning(
                    "SmartWire: import DROPPED wire row %d of %d - it "
                    "is a %s, not a row. No writer here produces that, "
                    "so the save is corrupt; one configured transfer "
                    "route does not exist this session and the row "
                    "cannot say which one",
                    offered,
                    len(wires),
                    type(w).__name__,
                )
                continue
            src = w.get("source_id")
            tgt = w.get("target_id")
            # float() can raise OverflowError (not just TypeError/ValueError)
            # on an int literal too large for a double. An uncaught raise here
            # returns 0 from BotManager.restore_smart_wires_from_state before
            # its import_ledgers overlay and its wire.created re-emit run.
            try:
                pct = float(w.get("pct", 0))
            except Exception as exc:
                unreadable += 1
                logger.warning(
                    "SmartWire: import DROPPED wire row %d of %d, "
                    "%s -> %s - float() refused pct %r (%s: %s). No "
                    "writer here produces that, so the save is corrupt; "
                    "fold profit from %s will never reach %s this "
                    "session",
                    offered,
                    len(wires),
                    src,
                    tgt,
                    w.get("pct"),
                    type(exc).__name__,
                    exc,
                    src,
                    tgt,
                )
                continue
            # nan is unordered, so pct<=0 and pct>100 are both False;
            # math.isnan must be checked explicitly to reject it.
            if not src or not tgt or math.isnan(pct) or pct <= 0 or pct > 100:
                unroutable += 1
                if not src:
                    why = "source_id is empty"
                elif not tgt:
                    why = "target_id is empty"
                elif math.isnan(pct):
                    why = (
                        "pct is nan, which is unordered - it is not "
                        "outside 0 < pct <= 100, both comparisons "
                        "are False, and that is exactly why this row "
                        "used to be stored and counted as imported"
                    )
                else:
                    why = "pct is outside the accepted 0 < pct <= 100"
                logger.warning(
                    "SmartWire: import DROPPED wire row %d of %d, "
                    "%s -> %s @ %r - %s. No writer here produces that, "
                    "so the save is corrupt; that transfer route does "
                    "not exist this session and the fold profit it "
                    "carried stays in the source bot",
                    offered,
                    len(wires),
                    src,
                    tgt,
                    pct,
                    why,
                )
                continue
            self._wires.setdefault(str(src), {})[str(tgt)] = pct
            n += 1
        # offered is counted above the first guard, the same number
        # topology.09.002 sends as expected; the two must agree.
        #
        # Excludes the two log calls below: log-dispatch cost is a
        # per-process constant, not proportional to the import's row
        # count, so tests/test_wires_received_duration.py measures the
        # import, not the report.
        _dur_elapsed = time.monotonic() - _dur_t0

        if n > 0:
            logger.info("SmartWire: imported %d wire(s) from saved state", n)
        lost = malformed + unreadable + unroutable
        if lost:
            logger.warning(
                "SmartWire: import accepted %d of %d wire row(s) "
                "offered; %d lost (%d not a row, %d had an unreadable "
                "pct, %d had no endpoint or a pct outside 0-100) - each "
                "lost row is one configured transfer route that does "
                "not exist this session, so that source bot's fold "
                "profit is never divided and the target's wired_in "
                "never grows",
                n,
                offered,
                lost,
                malformed,
                unreadable,
                unroutable,
            )
        # No _bot_refs check: n counts accepted rows, not bots active this run.
        try:
            from src.core.signal_contract import emit as _w

            _w(
                "topology.09.002.postcondition.wires_received",
                actual=n,
                expected=len(wires) if isinstance(wires, list) else 0,
                duration=_dur_elapsed,
                context={"sources": len(self._wires)},
            )
        except Exception:  # noqa: BLE001,S110 - advisory
            pass
        return n

    def distribute_fold_profit(
        self, source_id: str, profit_usd: float, ref: str = ""
    ) -> list[dict]:
        """Route pct% of source_id's realised fold profit to each target
        configured in the wire network.

        For each wire (source → target, raw_pct%):
          - pct = min(raw_pct, the per-wire Smart Wire Outflow Safety
            ceiling from compute_safe_outflow_pct)
          - share = profit_usd × pct / 100
          - If share < _min_wire: skip (below dust threshold)
          - Call target_bot.apply_wire_income(share, source_id, ref)
          - Record a WireTransaction entry for audit

        Returns a list of per-wire result dicts. Failures (missing
        target, disabled, etc.) are captured but do NOT raise — the
        fold path continues.
        """
        results: list[dict] = []
        if not self._enabled or profit_usd <= 0:
            return results
        outgoing = self._wires.get(source_id)
        if not outgoing:
            return results
        # An injected bus wins; falling through to get_event_bus() here is
        # what put a sim manager's wire logs on the live bus.
        _vis_bus = getattr(self, "_bus", None)
        if _vis_bus is None:
            try:
                from ..core.event_bus import get_event_bus as _gb_skip

                _vis_bus = _gb_skip()
            except Exception:  # bus init optional; None is the safe fallback
                _vis_bus = None
        _src_short_skip = (
            str(source_id)[:8] + "\u2026" if len(str(source_id)) > 8 else str(source_id)
        )
        # Emit failures are counted and reported once after the loop, not per wire.
        _notice_emit_fails: list[str] = []
        # Computed once per fold, before the loop, then split evenly
        # across the N outbound wires. Falls back to 100 (uncapped) when
        # the source bot has no get_swos_inputs.
        _per_wire_safe_pct = 100.0
        _swos_safe_pct = 100.0
        try:
            _src_bot = self._bot_refs.get(source_id)
            _swos_getter = getattr(_src_bot, "get_swos_inputs", None)
            if _swos_getter is not None:
                _swos_inputs = _swos_getter()
                if _swos_inputs:
                    _swos_safe_pct = compute_safe_outflow_pct(
                        scrum_profit_usd=float(profit_usd), **_swos_inputs
                    )
                    _n_wires = max(1, len(outgoing))
                    _per_wire_safe_pct = _swos_safe_pct / _n_wires
                    logger.debug(
                        "SWOS %s: safe=%.2f%% \u00f7 %d wires = "
                        "%.2f%% per-wire (profit=$%.4f)",
                        _src_short_skip,
                        _swos_safe_pct,
                        _n_wires,
                        _per_wire_safe_pct,
                        profit_usd,
                    )
        except Exception as _swos_exc:  # noqa: BLE001 - best-effort
            logger.debug(
                "SWOS %s pre-check raised %s \u2014 falling back to "
                "raw operator pct (no safety cap this fire).",
                _src_short_skip,
                _swos_exc,
            )
        for target_id, raw_pct in outgoing.items():
            # Effective pct never exceeds the operator's rate or the
            # per-wire SWOS ceiling.
            pct = min(float(raw_pct), _per_wire_safe_pct)
            share = profit_usd * float(pct) / 100.0
            _tgt_short_skip = (
                str(target_id)[:8] + "\u2026"
                if len(str(target_id)) > 8
                else str(target_id)
            )
            if share < self._min_wire:
                results.append(
                    {
                        "target_id": target_id,
                        "pct": pct,
                        "share": share,
                        "applied": False,
                        "reason": "below min_wire_amount",
                    }
                )
                # WIRE FLOW prefix gets magenta styling in StatusLog._render.
                if _vis_bus is not None:
                    _dust_msg = (
                        f"WIRE FLOW (dust skip): ${share:.4f} from "
                        f"{_src_short_skip} \u2192 {_tgt_short_skip} below "
                        f"floor ${self._min_wire:.2f} (pct={pct:.1f}%)"
                    )
                    try:
                        _vis_bus.emit("bot.log", bot_id=source_id, message=_dust_msg)
                        _vis_bus.emit("bot.log", bot_id=target_id, message=_dust_msg)
                    except Exception as _emit_exc:
                        # Outside the per-route try below: an uncaught
                        # escape here would abandon every remaining wire.
                        _notice_emit_fails.append("dust-skip")
                        logger.debug(
                            "SmartWire: dust-skip notice for %s -> %s "
                            "did not reach the bus (%s: %s)",
                            _src_short_skip,
                            _tgt_short_skip,
                            type(_emit_exc).__name__,
                            _emit_exc,
                        )
                continue
            target = self._bot_refs.get(target_id)
            if target is None or not hasattr(target, "apply_wire_income"):
                results.append(
                    {
                        "target_id": target_id,
                        "pct": pct,
                        "share": share,
                        "applied": False,
                        "reason": "target bot not attached",
                    }
                )
                if _vis_bus is not None:
                    _orphan_msg = (
                        f"WIRE FLOW (target unreachable): ${share:.4f} "
                        f"from {_src_short_skip} \u2192 {_tgt_short_skip} "
                        f"\u2014 target bot not attached. Wire is orphaned."
                    )
                    try:
                        _vis_bus.emit("bot.log", bot_id=source_id, message=_orphan_msg)
                    except Exception as _emit_exc:
                        # Same containment reason as the dust-skip notice above.
                        _notice_emit_fails.append("target-unreachable")
                        logger.debug(
                            "SmartWire: orphan-wire notice for %s -> "
                            "%s did not reach the bus (%s: %s)",
                            _src_short_skip,
                            _tgt_short_skip,
                            type(_emit_exc).__name__,
                            _emit_exc,
                        )
                continue
            try:
                r = target.apply_wire_income(share, source=source_id, ref=ref)
                # apply_wire_income returns {"applied": False, "reason": ...}
                # on bad input; a transaction is recorded only when applied is True.
                _target_applied = (
                    bool(r.get("applied", False)) if isinstance(r, dict) else False
                )
                _src_short = (
                    str(source_id)[:8] + "…"
                    if len(str(source_id)) > 8
                    else str(source_id)
                )
                _tgt_short = (
                    str(target_id)[:8] + "…"
                    if len(str(target_id)) > 8
                    else str(target_id)
                )

                if not _target_applied:
                    # Target refused; no transaction is recorded.
                    _refusal_reason = (
                        r.get("reason", "target refused without reason")
                        if isinstance(r, dict)
                        else f"target returned non-dict: {type(r).__name__}"
                    )
                    if _vis_bus is not None:
                        try:
                            _vis_bus.emit(
                                "bot.log",
                                bot_id=source_id,
                                message=(
                                    f"WIRE FLOW (target refused): "
                                    f"${share:.4f} from {_src_short} → "
                                    f"{_tgt_short} ({pct:.1f}% of fold "
                                    f"profit) — target apply_wire_income "
                                    f"returned applied=False. Reason: "
                                    f"{_refusal_reason}. NO transfer "
                                    f"booked."
                                ),
                            )
                            _vis_bus.emit(
                                "bot.log",
                                bot_id=target_id,
                                message=(
                                    f"WIRE FLOW (own apply refused): "
                                    f"${share:.4f} from {_src_short} → "
                                    f"{_tgt_short} — apply_wire_income "
                                    f"refused. Reason: {_refusal_reason}."
                                ),
                            )
                        except (
                            AttributeError,
                            TypeError,
                            RuntimeError,
                            ValueError,
                        ) as _emit_exc:
                            # Narrowed: EventBus.emit already swallows a
                            # subscriber error; the except below still runs.
                            logger.warning(
                                "SmartWire: target-refused notice for "
                                "%s -> %s ($%.4f) did not reach the "
                                "operator console (%s: %s); the "
                                "refusal stands and is in the result",
                                _src_short,
                                _tgt_short,
                                share,
                                type(_emit_exc).__name__,
                                _emit_exc,
                            )
                    results.append(
                        {
                            "target_id": target_id,
                            "pct": pct,
                            "share": share,
                            "applied": False,
                            "reason": _refusal_reason,
                            "result": r,
                        }
                    )
                    continue

                # Audit trail: reached only when the target applied the income.
                import time as _t

                self._transactions.append(
                    WireTransaction(
                        timestamp=int(_t.time()),
                        source_bot=source_id,
                        target_bot=target_id,
                        amount=share,
                        wire_type="WIRE_BACK",
                        reason=f"fold_profit pct={pct}% ref={ref}",
                    )
                )
                _placement = ""
                try:
                    if isinstance(r, dict):
                        # Built in steps, not a nested-quote f-string: ruff
                        # parses that as a syntax error against this project's target.
                        _placement = " → " + str(r.get("placement", "tranche"))
                        _tranche_idx = r.get("tranche_index")
                        if _tranche_idx is not None:
                            _placement += " #" + str(_tranche_idx)
                except Exception as _place_exc:
                    # Guards str() over values the target bot returned; a
                    # broken __str__ there raises here, after the transfer
                    # already completed, so _placement resets to "" rather
                    # than reporting a booked transfer as failed.
                    _placement = ""
                    logger.warning(
                        "SmartWire: could not render placement for the "
                        "%s -> %s wire ($%.4f) (%s: %s); the WIRE FLOW "
                        "line omits where the income landed",
                        _src_short,
                        _tgt_short,
                        share,
                        type(_place_exc).__name__,
                        _place_exc,
                    )
                _flow_msg = (
                    f"WIRE FLOW: ${share:.2f} from {_src_short} → "
                    f"{_tgt_short} ({pct:.1f}% of fold profit"
                    f"{f', ref={ref}' if ref else ''}){_placement}"
                )
                try:
                    _bus = getattr(self, "_bus", None)
                    if _bus is None:
                        from ..core.event_bus import get_event_bus as _gb

                        _bus = _gb()
                    _bus.emit("bot.log", bot_id=source_id, message=_flow_msg)
                    _bus.emit("bot.log", bot_id=target_id, message=_flow_msg)
                except Exception as _emit_exc:
                    # The transfer already completed and is in
                    # self._transactions; only the console notice is lost here.
                    logger.warning(
                        "SmartWire: WIRE FLOW notice for a COMPLETED "
                        "transfer of $%.4f from %s to %s did not reach "
                        "the operator console (%s: %s); the transfer "
                        "stands and is in the audit trail",
                        share,
                        source_id,
                        target_id,
                        type(_emit_exc).__name__,
                        _emit_exc,
                    )
                results.append(
                    {
                        "target_id": target_id,
                        "pct": pct,
                        "share": share,
                        "applied": True,
                        "result": r,
                    }
                )
            except Exception as exc:
                logger.warning(
                    "SmartWire: route %s->%s raised: %s", source_id, target_id, exc
                )
                results.append(
                    {
                        "target_id": target_id,
                        "pct": pct,
                        "share": share,
                        "applied": False,
                        "reason": f"exception: {exc}",
                    }
                )
                if _vis_bus is not None:
                    try:
                        _vis_bus.emit(
                            "bot.log",
                            bot_id=source_id,
                            message=(
                                f"WIRE FLOW (error): ${share:.4f} from "
                                f"{_src_short_skip} \u2192 {_tgt_short_skip} "
                                f"raised {type(exc).__name__}: {exc}"
                            ),
                        )
                    except Exception as _emit_exc:
                        # DEBUG, not WARNING: the route failure itself was
                        # already logged above; this would double-count it.
                        logger.debug(
                            "SmartWire: route-error notice for %s -> "
                            "%s did not reach the bus (%s: %s)",
                            _src_short_skip,
                            _tgt_short_skip,
                            type(_emit_exc).__name__,
                            _emit_exc,
                        )
        # Emitted once when every configured wire this fold was filtered
        # (dust, unreachable, or errored), so no share routed.
        try:
            applied_count = sum(1 for r in results if r.get("applied"))
            if results and applied_count == 0 and _vis_bus is not None:
                dust = sum(
                    1 for r in results if r.get("reason") == "below min_wire_amount"
                )
                unreach = sum(
                    1 for r in results if r.get("reason") == "target bot not attached"
                )
                errs = sum(
                    1
                    for r in results
                    if str(r.get("reason", "")).startswith("exception")
                )
                _vis_bus.emit(
                    "bot.log",
                    bot_id=source_id,
                    message=(
                        f"WIRE FLOW: fold ${profit_usd:.4f} produced "
                        f"no routed shares ({len(results)} wire(s) "
                        f"checked: {dust} dust-skipped, "
                        f"{unreach} unreachable, {errs} errored)"
                    ),
                )
        except Exception as _emit_exc:
            # DEBUG: this method's contract is that failures never raise;
            # an escape here, after money may have moved, would break that.
            logger.debug(
                "SmartWire: no-flow summary for %s did not reach the " "bus (%s: %s)",
                _src_short_skip,
                type(_emit_exc).__name__,
                _emit_exc,
            )
        # Outside the try above: a broken bus is what this line reports.
        if _notice_emit_fails:
            logger.warning(
                "SmartWire: %d wire-notice emit(s) failed during the "
                "fold on %s (%s); those wire events are missing from "
                "the operator console",
                len(_notice_emit_fails),
                _src_short_skip,
                ", ".join(sorted(set(_notice_emit_fails))),
            )
        return results

    def register_bot(
        self,
        bot_id: str,
        asset: str,
        seed_amount: float = 200.0,
        funder_bot_id: Optional[str] = None,
    ) -> None:
        """Register a bot in the smart wire network.

        funder_bot_id, when provided, records that bot as this one's
        provenance source instead of SEED; the funder's own ledger is
        not touched here. Otherwise the bot is SEED-funded.
        """
        if funder_bot_id is None:
            # SEED registration
            provenance = {"SEED": seed_amount}
        else:
            # Cascade registration: funded by an existing bot
            provenance = {funder_bot_id: seed_amount}

        self._ledgers[bot_id] = BotLedger(
            bot_id=bot_id,
            asset=asset,
            provenance=provenance,
            starting_balance=seed_amount,  # read by primary_provenance_starting_balance
        )
        source_label = funder_bot_id or "SEED"
        logger.info(
            "SmartWire: registered %s (%s) with $%.2f from %s",
            bot_id,
            asset,
            seed_amount,
            source_label,
        )

    # Mature-Profit Cascade: primary_provenance_starting_balance,
    # can_fund_new_bot and execute_spawn_wire together implement it.

    def primary_provenance_starting_balance(self, bot_id: str) -> Optional[float]:
        """Resolve the PPS's starting balance for this bot.

        For a bot whose PPS is SEED: returns the amount in provenance['SEED'].
        For a bot whose PPS is another bot: returns that bot's
          starting_balance field.
        For an unknown bot: returns None.
        """
        ledger = self._ledgers.get(bot_id)
        if ledger is None:
            return None
        pps = ledger.predominant_source
        if pps is None:
            # No other-bot source: PPS is SEED.
            return float(ledger.provenance.get("SEED", 0.0))
        pps_ledger = self._ledgers.get(pps)
        if pps_ledger is None:
            # PPS bot not registered: falls back to this bot's own
            # starting balance so the cascade invariant still holds.
            return ledger.starting_balance
        return pps_ledger.starting_balance

    def can_fund_new_bot(self, bot_id: str) -> tuple[bool, float, str]:
        """Check whether this bot has enough mature profit to spawn.

        Returns (approved, amount, reason):
          - approved=True, amount>0, reason="ok" if mature_profit_available
            >= PPS starting balance
          - approved=False, amount=0, reason=explanation otherwise
        """
        ledger = self._ledgers.get(bot_id)
        if ledger is None:
            return False, 0.0, f"unknown_bot ({bot_id})"

        threshold = self.primary_provenance_starting_balance(bot_id)
        if threshold is None or threshold <= 0:
            return False, 0.0, "no_pps_starting_balance"

        available = ledger.mature_profit_available
        if available < threshold:
            return (
                False,
                0.0,
                f"insufficient_mature (${available:.2f} < " f"${threshold:.2f})",
            )

        return True, threshold, "ok"

    def execute_spawn_wire(
        self,
        funder_bot_id: str,
        new_bot_id: str,
        new_bot_asset: str,
        timestamp: int = 0,
    ) -> Optional[WireTransaction]:
        """Perform the cascade spawn:
        1. Verify funder can fund (re-checks can_fund_new_bot)
        2. Debit funder's mature_profit_allocated
        3. Register the new bot with funder as provenance source
        4. Record a WireTransaction (type=MR_FUND)
        5. Return the transaction (or None if can_fund_new_bot fails)
        """
        approved, amount, reason = self.can_fund_new_bot(funder_bot_id)
        if not approved:
            logger.info(
                "SmartWire spawn gate declined: funder=%s reason=%s",
                funder_bot_id,
                reason,
            )
            return None

        funder = self._ledgers[funder_bot_id]
        funder.mature_profit_allocated += amount
        funder.wired_out += amount

        self.register_bot(
            new_bot_id, new_bot_asset, seed_amount=amount, funder_bot_id=funder_bot_id
        )
        # wired_in reflects funding by another bot, not SEED.
        self._ledgers[new_bot_id].wired_in = amount

        tx = WireTransaction(
            timestamp=timestamp,
            source_bot=funder_bot_id,
            target_bot=new_bot_id,
            amount=amount,
            wire_type="MR_FUND",
            reason=(f"mature-profit cascade spawn " f"(threshold=${amount:.2f})"),
        )
        self._transactions.append(tx)
        logger.info(
            "SmartWire cascade: %s → %s funded with $%.2f "
            "(funder retains stake + $%.2f excess mature)",
            funder_bot_id,
            new_bot_id,
            amount,
            funder.mature_profit_available,
        )
        return tx

    def record_profit(self, bot_id: str, amount: float) -> None:
        """Record realized profit for a bot (from scrum-fold cycles)."""
        if bot_id in self._ledgers:
            self._ledgers[bot_id].total_profit += amount
            self._ledgers[bot_id].available_profit += amount

    def process_wires(
        self, undervalued_bots: list[str] = None, timestamp: int = 0
    ) -> list[WireTransaction]:
        """
        Process wire opportunities:
        1. Find bots with mature profits → deploy into undervalued bots
        2. Find funded bots with profits → wire back to source

        Parameters:
            undervalued_bots: list of bot_ids identified by MR Inspector as undervalued
            timestamp: current timestamp for transaction logging

        Returns: list of WireTransactions to execute
        """
        if not self._enabled:
            return []

        wires = []

        # Phase 1: MR-funded deployment
        if undervalued_bots:
            for bot_id, ledger in self._ledgers.items():
                if ledger.available_profit < self._min_wire * 2:
                    continue
                deploy = ledger.available_profit * self._mr_fund_pct
                if deploy < self._min_wire:
                    continue

                for target_id in undervalued_bots:
                    if target_id == bot_id:
                        continue
                    if target_id not in self._ledgers:
                        continue

                    wire = WireTransaction(
                        timestamp=timestamp,
                        source_bot=bot_id,
                        target_bot=target_id,
                        amount=deploy,
                        wire_type="MR_FUND",
                        reason=f"MR undervalued: {target_id}",
                    )
                    wires.append(wire)

                    # Update ledgers
                    ledger.available_profit -= deploy
                    ledger.wired_out += deploy
                    target = self._ledgers[target_id]
                    target.wired_in += deploy
                    if bot_id not in target.provenance:
                        target.provenance[bot_id] = 0
                    target.provenance[bot_id] += deploy
                    break  # One deployment per source per cycle

        # Phase 2: Wire-back to predominant source
        for bot_id, ledger in self._ledgers.items():
            if ledger.available_profit < self._min_wire:
                continue
            source = ledger.predominant_source
            if not source or source not in self._ledgers:
                continue

            wire_amount = ledger.available_profit * self._wire_back_pct
            if wire_amount < self._min_wire:
                continue

            wire = WireTransaction(
                timestamp=timestamp,
                source_bot=bot_id,
                target_bot=source,
                amount=wire_amount,
                wire_type="WIRE_BACK",
                reason=f"Provenance return to {source}",
            )
            wires.append(wire)

            ledger.available_profit -= wire_amount
            ledger.wired_out += wire_amount
            self._ledgers[source].wired_in += wire_amount

        self._transactions.extend(wires)
        return wires

    def get_ledger(self, bot_id: str) -> Optional[BotLedger]:
        return self._ledgers.get(bot_id)

    @property
    def stats(self) -> dict:
        return {
            "bots": len(self._ledgers),
            "transactions": len(self._transactions),
            "total_wired": sum(t.amount for t in self._transactions),
            "total_profit": sum(l.total_profit for l in self._ledgers.values()),
        }
