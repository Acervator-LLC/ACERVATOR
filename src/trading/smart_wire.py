"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
smart_wire.py — Cross-Compounding Bot Network
# ┌─────────────────────────────────────────────────────────────┐
# │ AI DEVELOPER NOTE                                           │
# │                                                             │
# │ PATENT-ELIGIBLE INVENTION #6.                               │
# │                                                             │
# │ Smart Wire routes profits between cooperating bots with     │
# │ provenance tracking. When Bot A generates profit, a         │
# │ configurable % is wired to Bot B's target, increasing B's   │
# │ operating capital. The wire carries a provenance tag         │
# │ recording: source_bot, amount, timestamp, trade_id.         │
# │                                                             │
# │ Key insight (inventor's): "profits should flow back to      │
# │ their generating source" — unlike portfolio rebalancing     │
# │ which redistributes blindly.                                │
# │                                                             │
# │ Validated: +54.3% network improvement ($75K → $116K).       │
# └─────────────────────────────────────────────────────────────┘
==============================================
Manages profit provenance tracking and smart wire capital routing
between multiple accumulation bots.

Architecture:
  - Each bot registers with the SmartWireManager
  - Profits are tracked with provenance (which bot generated them)
  - MR Inspector identifies undervalued opportunities
  - Mature profits are deployed into undervalued bots
  - When funded bots profit, x% is wired back to the funding source
  - This creates a self-reinforcing compounding network

v3.1.71 — Initial implementation
"""

from __future__ import annotations
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("acervator.smart_wire")


# v3.23.64 — Smart Wire Outflow Safety (SWOS) arithmetic.
# Full spec: docs/audits/2026-07-31_smart_wire_outflow_safety_arithmetic.md
#
# Pure function; no I/O, no bot references, no logging. Returns the
# maximum safe outflow % for a single scrum event based on the bot's
# current market position and its own reserve requirements.
#
# Endpoints per operator directive 2026-07-31: steep 0.2 → 2.0
# safety factor from band_upper (permissive, deep in Scrum) to
# band_lower (conservative, imminent Fold). Minimum-export floor at
# 1 % — anything smaller returns 0 to avoid dust transfers.
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
    """Safe % of ``scrum_profit_usd`` that may be routed OUT via
    smart wires without jeopardising the source bot's next Fold or
    Compounding-Growth cadence.

    Returns a float in ``[0.0, 100.0]``. See the SWOS spec doc for
    the derivation of the formula and the invariants each caller may
    rely on."""
    # Invariant 3: zero profit → zero export.
    if scrum_profit_usd <= 0:
        return 0.0

    # Distance-to-fold-band clamped [0, 1]. 0 = at/below band_lower
    # (imminent fold); 1 = at/above band_upper (deep in scrum).
    if band_upper <= band_lower:
        # Invariant 9 — degenerate: conservative safety.
        distance_to_fold_pct = 0.0
    else:
        distance_to_fold_pct = max(
            0.0,
            min(1.0,
                (current_price - band_lower)
                / (band_upper - band_lower)))

    # Safety factor 0.2 → 2.0 (steeper ramp per operator 2026-07-31).
    if band_upper <= band_lower:
        safety_factor = 2.0     # forced conservative
    else:
        safety_factor = 0.2 + 1.8 * (1.0 - distance_to_fold_pct)

    # Fold reserve.
    fold_shortfall_usd = max(
        0.0, float(next_fold_ammo_usd) - float(current_cash_usd))
    fold_reserve_usd = fold_shortfall_usd * safety_factor

    # Compound-growth reserve.
    compound_target_usd = (
        float(target_balance_usd)
        * float(compound_growth_pct) / 100.0)
    compound_reserve_usd = max(
        0.0, compound_target_usd - float(retained_this_cycle_usd))

    reserves_total_usd = fold_reserve_usd + compound_reserve_usd
    exportable_usd = max(0.0, scrum_profit_usd - reserves_total_usd)
    raw_safe_pct = 100.0 * exportable_usd / scrum_profit_usd

    # Minimum-export floor: sub-1 % dust becomes 0.
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

    v3.13.5 — Mature-profit cascade fields added:
      - starting_balance: the capital this bot was seeded with (from SEED
        or from a parent bot's mature transfer). Immutable after init.
      - mature_profit_allocated: cumulative $ transferred to spawn child
        bots. Used to compute available mature profits for further spawns.

    The "mature profit cascade" design (user directive, Session 18):
      Bot N may spawn bot N+1 only when its mature profits reach the
      starting balance of its primary Provenance Source (PPS). This
      ensures N retains its stake as a sustained liquidity buffer after
      spawning. Each bot thus starts with exactly the same capital as
      its funder, compounding the NETWORK of earning units, not per-bot
      capital.

      sadp: R60 (older P1 work); user invariant Session 18
    """
    bot_id: str
    asset: str
    total_profit: float = 0.0
    available_profit: float = 0.0  # Profit available for wiring
    wired_in: float = 0.0
    wired_out: float = 0.0
    provenance: dict = field(default_factory=dict)  # source_bot_id → amount
    starting_balance: float = 0.0        # v3.13.5 — seed capital
    mature_profit_allocated: float = 0.0  # v3.13.5 — sum spent on spawns

    # Mature ratio follows main_window.py convention: 70% of realized
    # PnL is considered "mature" (30% haircut absorbs drawdown noise)
    MATURE_RATIO: float = 0.7

    @property
    def predominant_source(self) -> Optional[str]:
        """Find the non-SEED bot that funded this bot the most."""
        sources = {k: v for k, v in self.provenance.items()
                   if k != "SEED" and v > 0}
        if not sources:
            return None
        return max(sources, key=sources.get)

    @property
    def mature_profit_total(self) -> float:
        """Total mature profit earned across history.

        70% haircut on positive total_profit. Clamped at 0 for losses —
        a losing bot has zero mature profit regardless of PPS state.
        Matches main_window.py line 1912: mature = total_pnl * 0.7
        if total_pnl > 0 else 0.
        """
        if self.total_profit <= 0:
            return 0.0
        return self.total_profit * self.MATURE_RATIO

    @property
    def mature_profit_available(self) -> float:
        """Mature profit NOT yet allocated to child spawns.

        This is the value the spawn gate compares against the PPS
        starting balance. Each child spawn debits exactly the PPS
        starting balance from this pool. Can go negative if bot has
        spawned children and then lost money — in that case the gate
        (which requires available >= threshold) correctly blocks
        further spawns until profits recover.
        """
        return self.mature_profit_total - self.mature_profit_allocated


class SmartWireManager:
    """
    Manages the cross-compounding network between accumulation bots.

    Usage:
        mgr = SmartWireManager(wire_back_pct=0.30, mr_fund_pct=0.15)
        mgr.register_bot("bot_btc", "BTC/USD", seed_amount=200)
        mgr.register_bot("bot_eth", "ETH/USD", seed_amount=200)

        # When a bot realizes profit:
        mgr.record_profit("bot_btc", amount=5.50)

        # Periodic: check for wire opportunities
        wires = mgr.process_wires(current_prices, mr_signals)
    """

    def __init__(self, wire_back_pct: float = 0.30,
                 mr_fund_pct: float = 0.15,
                 min_wire_amount: float = 0.01,
                 bus=None):
        # v3.24.61 (C17) — injectable bus.
        #
        # THE CASCADE PLAN SAYS THIS CLASS DOES NOT NEED IT: "SmartWire-
        # Manager takes no bus and emits nothing, so SN-28's stated fix
        # is misdiagnosed." That correction is itself wrong. This class
        # resolves get_event_bus() lazily at :491 and :675 and emits
        # bot.log on both paths, and BotManager constructs one, so a sim
        # manager's wire activity reached the LIVE bus even after the
        # manager's own bus was isolated.
        #
        # Resolved once here rather than lazily per call site, so a
        # future emit site cannot reintroduce the leak by forgetting.
        # None keeps the previous lazy behaviour for live construction.
        self._bus = bus
        # v3.15.74 — dust floor lowered from $1.00 to $0.01.
        # Operator directive 2026-04-26: "Still not seeing bot smart
        # distributions in the console." Root cause was the $1.00 floor
        # silently swallowing flat-market wire shares: a $200 target bot
        # with a 30% wire and a $3.00 fold profit produced a $0.90 share,
        # under the floor, silently skipped — operator saw nothing.
        # See docs/audits/2026-04-26_smart_wire_visibility_rca.md.
        self._wire_back_pct = wire_back_pct
        self._mr_fund_pct = mr_fund_pct
        self._min_wire = min_wire_amount
        self._ledgers: dict[str, BotLedger] = {}
        self._transactions: list[WireTransaction] = []
        self._enabled = True
        # Session 26 P1b (2026-04-24) — fold-profit routing network.
        # Maps source_bot_id → {target_bot_id: pct_of_profit}.
        # Populated by BotContainer.register_wire / unregister_wire
        # when the operator draws / removes a wire in the Bot Swarm GUI.
        # Consumed by distribute_fold_profit on every source-bot fold.
        self._wires: dict[str, dict[str, float]] = {}
        # Weak(ish) ref back to bot objects so distribute_fold_profit
        # can reach target.apply_wire_income without a separate lookup.
        # Not using weakref.WeakValueDictionary intentionally — BotManager
        # owns bot lifecycle; manager unregisters on bot deletion.
        self._bot_refs: dict[str, object] = {}

    # ══════════════════════════════════════════════════════════════════
    # P1b — Fold-profit routing API (Session 26, 2026-04-24)
    # ══════════════════════════════════════════════════════════════════

    def attach_bot(self, bot_id: str, bot_ref: object) -> None:
        """Register a bot instance so distribute_fold_profit can reach
        its apply_wire_income. Called by BotContainer after every bot
        creation alongside bot.set_smart_wire(self).
        """
        self._bot_refs[bot_id] = bot_ref
        # DIRECTIVE 4 — "DEPLOYS". A wire is only deployable if BOTH
        # endpoints resolve to a bot in this run. Recording each
        # attachment lets the active count be computed instead of
        # assumed.
        try:
            from src.core.signal_contract import emit as _wb
            _wb("topology.09.001.state_transition.bot_attached", actual=str(bot_id),
                context={"attached_total": len(self._bot_refs)})
        except Exception:  # noqa: BLE001,S110 - advisory
            pass

    def detach_bot(self, bot_id: str) -> None:
        """Remove a bot instance + all wires that reference it on
        either side. Called on bot deletion.
        """
        self._bot_refs.pop(bot_id, None)
        # v3.24.35 (C01) — drop the ledger row too.
        #
        # It was left behind, and export_ledgers() then re-persisted a
        # row for a bot that no longer exists. Measured on the live file
        # 2026-08-05: 13 of 48 ledger rows are orphans of already-deleted
        # bots, two carrying non-zero wired_out ($132.86 and $9.81).
        # This stops new ones; the existing 13 are pre-existing and are
        # deliberately NOT touched here — they are the only surviving
        # record those transfers happened.
        self._ledgers.pop(bot_id, None)
        # Drop wires sourced from this bot
        self._wires.pop(bot_id, None)
        # Drop wires targeting this bot (scan all sources)
        for src in list(self._wires.keys()):
            self._wires[src].pop(bot_id, None)
            if not self._wires[src]:
                del self._wires[src]

    def register_wire(self, source_id: str, target_id: str,
                      pct: float) -> dict:
        """Create or update the wire from source_id to target_id with
        the given percentage (0-100). pct is the fraction of source's
        fold profit that will be routed to target on each fold event.

        Returns {"applied": bool, "reason": str, ...}.

        v3.24.37 (C06c) — the return now carries ``replaced_pct``: the
        percentage that was on this pair before the call, or None if the
        pair was previously unwired. This method has always overwritten
        an existing pct in place and reported ``applied: True`` either
        way, so a caller had no way to tell "drew a new wire" from
        "silently replaced the operator's hand-tuned 20% with 50%".
        Behaviour is unchanged — the overwrite still happens — but it is
        now visible to callers and logged at WARNING rather than
        disappearing into an INFO line identical to a fresh wire.
        """
        if source_id == target_id:
            return {"applied": False,
                    "reason": "source and target must differ"}
        # ── HOLE 1, ORIGIN SIDE (2026-08-15). The breadth here is new
        # and it closes the SAME hole as import_wires below: this was
        # `except (TypeError, ValueError)`, and float() has a third
        # failure mode neither covers - OverflowError, on an int too
        # large for a double.
        #
        # MEASURED ON THIS METHOD: register_wire("a", "b", int("9"*400))
        # RAISED OverflowError straight out, through a method whose
        # entire documented contract is to RETURN
        # {"applied": bool, "reason": str}. Every caller that reads the
        # result dict got an exception instead, so a refusal became a
        # crash. That is worse than the importer's version of the same
        # defect in one way and better in another: there is no partial
        # state to leave behind here, but the caller has no handler at
        # all.
        #
        # FOUND BY THIS UNIT'S OWN CONTROL, not by the work order. The
        # order named only nan at this site; sweeping one value domain
        # through BOTH writers into `_wires` - which "no nan may reach
        # distribute_fold_profit" requires - returned the wide integer
        # raising from the writer nobody had driven.
        #
        # THE GUARDED REGION IS THE COERCION AND NOTHING ELSE, exactly
        # as in import_wires. The isnan test, the range test, the
        # overwrite WARNING and the store below all sit outside it and
        # must stay outside it: swallowing a failed store here would
        # report applied=True for a wire that does not exist. Widen an
        # except around a COERCION of a caller-supplied value; never
        # around code that should not throw.
        #
        # The reason no longer says "must be numeric". That was FALSE
        # for a 400-digit integer, which is numeric and simply has no
        # double to land on, and it would send a reader after the wrong
        # defect. The exception type is named instead, as
        # import_ledgers does.
        try:
            p = float(pct)
        except Exception as exc:
            return {"applied": False,
                    "reason": (f"pct could not be read as a number: "
                               f"{pct!r} ({type(exc).__name__}: {exc})")}
        # ── HOLE 2, ORIGIN SIDE (2026-08-15). The isnan test is new
        # and it is the SAME hole closed in import_wires below.
        # register_wire is the other writer into `_wires`, and it is
        # where a NaN-bearing save comes from: nan is unordered, so
        # `p <= 0` and `p > 100` were both False, this method returned
        # applied=True, export_wires wrote the row, and json.dumps put a
        # bare `NaN` token into bot_state.json. Closing only the import
        # side would leave this path open and let the save keep growing
        # NaN tokens that the importer then correctly refuses - which
        # the operator would see as a wire he drew silently vanishing on
        # the next launch. inf is already refused by `p > 100`, so this
        # adds exactly one rejected class and changes no other verdict.
        #
        # nan gets its own reason string for the same cause as the
        # importer's: "must be in (0, 100]" would describe a range test
        # that nan does not fail, and would send the reader looking for
        # the wrong defect.
        if math.isnan(p):
            return {"applied": False,
                    "reason": ("pct must be a real number; got nan, "
                               "which is unordered - it is not outside "
                               "(0, 100], both comparisons are False, "
                               "and that is why it used to be accepted")}
        if p <= 0 or p > 100:
            return {"applied": False,
                    "reason": f"pct must be in (0, 100]; got {p}"}
        prior = self._wires.get(source_id, {}).get(target_id)
        self._wires.setdefault(source_id, {})[target_id] = p
        if prior is None:
            logger.info("SmartWire: registered %s -> %s @ %.2f%%",
                        source_id, target_id, p)
        else:
            logger.warning(
                "SmartWire: OVERWROTE %s -> %s: %.2f%% replaced by %.2f%%",
                source_id, target_id, float(prior), p)
        return {"applied": True, "source_id": source_id,
                "target_id": target_id, "pct": p,
                "replaced_pct": (None if prior is None else float(prior))}

    def unregister_wire(self, source_id: str, target_id: str) -> bool:
        """Remove the wire. Returns True if it existed, False otherwise."""
        if source_id in self._wires and target_id in self._wires[source_id]:
            del self._wires[source_id][target_id]
            if not self._wires[source_id]:
                del self._wires[source_id]
            logger.info("SmartWire: unregistered %s -> %s",
                        source_id, target_id)
            return True
        return False

    def get_outgoing_wires(self, source_id: str) -> dict[str, float]:
        """Return the source bot's {target_id: pct} map (or empty)."""
        return dict(self._wires.get(source_id, {}))

    # v3.15.68 — state persistence (operator: "Bot swarm state is not
    # being preserved")
    def export_wires(self) -> list[dict]:
        """Snapshot the wire registry as a JSON-serializable list of
        {source_id, target_id, pct} dicts. Used by BotManager to
        persist swarm state across restart."""
        out: list[dict] = []
        for src, targets in self._wires.items():
            for tgt, pct in targets.items():
                out.append({
                    "source_id": str(src),
                    "target_id": str(tgt),
                    "pct": float(pct),
                })
        return out

    # v3.16.57 — Ledger persistence. Operator-reported bug 2026-05-13:
    # "Smart Wire credits are not persisting across platform restarts."
    # Root cause: prior versions exported only the wire topology
    # (source→target→pct via `export_wires`), but the lifetime
    # `wired_in` / `wired_out` totals and the provenance history on
    # each BotLedger were NOT persisted. Every platform restart reset
    # the Bot Swarm tab counters to $0.00.
    def export_ledgers(self) -> list[dict]:
        """Snapshot each BotLedger as a JSON-serializable dict so the
        per-bot wired_in/wired_out totals + provenance survive restart.
        Returns a list of dicts that can be passed to import_ledgers().
        """
        out: list[dict] = []
        dropped = 0
        for bot_id, ledger in self._ledgers.items():
            try:
                out.append({
                    "bot_id": str(bot_id),
                    "asset": str(getattr(ledger, "asset", "") or ""),
                    "total_profit": float(getattr(
                        ledger, "total_profit", 0.0) or 0.0),
                    "available_profit": float(getattr(
                        ledger, "available_profit", 0.0) or 0.0),
                    "wired_in": float(getattr(
                        ledger, "wired_in", 0.0) or 0.0),
                    "wired_out": float(getattr(
                        ledger, "wired_out", 0.0) or 0.0),
                    "provenance": dict(getattr(
                        ledger, "provenance", {}) or {}),
                    "starting_balance": float(getattr(
                        ledger, "starting_balance", 0.0) or 0.0),
                    "mature_profit_allocated": float(getattr(
                        ledger, "mature_profit_allocated", 0.0) or 0.0),
                })
            except Exception as exc:
                # 2026-08-14 - this was `except Exception: continue`,
                # which dropped the row in total silence. The row is
                # that bot's lifetime wired_in / wired_out and its
                # provenance, and state_manager.save_state writes
                # whatever this returns with NO carry-forward for
                # smart_wire_ledgers (state_manager.py:92), so a
                # dropped row leaves the save file permanently.
                #
                # THE BREADTH IS DELIBERATE AND MUST NOT BE NARROWED.
                # bot_container.save_all_state catches anything that
                # escapes here, leaves `ledgers = []`, and STILL calls
                # save_state (bot_container.py:3363-3387) - so one
                # unhandled row would erase EVERY row instead of one.
                dropped += 1
                logger.warning(
                    "SmartWire: export DROPPED ledger row for %s "
                    "(%s: %s) - its wired_in/wired_out history is NOT "
                    "in this save and is not recoverable from it",
                    bot_id, type(exc).__name__, exc)
                continue
        if dropped:
            logger.warning(
                "SmartWire: exported %d of %d ledger row(s); "
                "%d dropped", len(out), len(self._ledgers), dropped)
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
        # 2026-08-14 - `offered` used to be incremented AFTER the two
        # guards below, so it counted only the rows that reached the
        # try. Every row the guards dropped was invisible to it, and
        # the summary WARNING under-reported the loss in the one
        # direction that reassures: a six-row payload losing four rows
        # reported "accepted 2 of 3 ... 1 dropped". Worse, a payload
        # losing rows ONLY to the guards left `dropped` at 0, so the
        # WARNING never fired and the operator saw nothing but the
        # "imported N ledger(s)" INFO. The two guards are not exception
        # handlers, so ruff S110/S112 never saw them.
        #
        # WHY A GUARD-DROP IS A REAL LOSS, NOT ROUTINE PADDING: no
        # writer in this codebase can produce either shape.
        # export_ledgers always appends a dict carrying
        # "bot_id": str(bot_id) (see above); state_manager.save_state
        # stores that list verbatim (state_manager.py:92); and
        # state_manager.delete_bot only FILTERS rows out, never adds
        # one (state_manager.py:238-240). So a non-dict row, or a row
        # with no usable bot_id, means the save has been corrupted,
        # truncated or hand-edited - and the bot behind it reads
        # $0.00 wired_in / $0.00 wired_out for the whole session,
        # exactly as it would after an exception-drop.
        #
        # They are counted SEPARATELY because they differ in what can
        # be reported: an exception-drop knows `bid` and leaves the row
        # PARTIALLY applied, while a guard-drop cannot name the bot at
        # all and applies nothing. Merging them would hide which of
        # those two the operator is looking at.
        malformed = 0      # row was not a dict at all
        unidentified = 0   # row was a dict but carried no usable bot_id
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
                    offered, len(ledgers), type(row).__name__)
                continue
            bid = row.get("bot_id")
            if not bid:
                unidentified += 1
                logger.warning(
                    "SmartWire: import DROPPED ledger row %d of %d - "
                    "bot_id is %r, so the row cannot be applied to any "
                    "bot. Its wired_in/wired_out history is not in this "
                    "session",
                    offered, len(ledgers), bid)
                continue
            bid = str(bid)
            try:
                if bid not in self._ledgers:
                    # Create skeleton; attach_bot may overwrite asset
                    # later. starting_balance is loaded from save so
                    # mature-profit cascade math survives restart.
                    self._ledgers[bid] = BotLedger(
                        bot_id=bid,
                        asset=str(row.get("asset", "") or ""),
                        starting_balance=float(
                            row.get("starting_balance", 0.0) or 0.0))
                lg = self._ledgers[bid]
                lg.total_profit = float(
                    row.get("total_profit", 0.0) or 0.0)
                lg.available_profit = float(
                    row.get("available_profit", 0.0) or 0.0)
                lg.wired_in = float(row.get("wired_in", 0.0) or 0.0)
                lg.wired_out = float(row.get("wired_out", 0.0) or 0.0)
                _prov = row.get("provenance", {})
                if isinstance(_prov, dict):
                    lg.provenance = {str(k): float(v or 0.0)
                                     for k, v in _prov.items()}
                lg.mature_profit_allocated = float(
                    row.get("mature_profit_allocated", 0.0) or 0.0)
                # Only update asset/starting_balance if not already set
                # (attach_bot's register_bot may have set them already).
                if not lg.asset and row.get("asset"):
                    lg.asset = str(row["asset"])
                if (not lg.starting_balance
                        and row.get("starting_balance")):
                    lg.starting_balance = float(row["starting_balance"])
                n += 1
            except Exception as exc:
                # 2026-08-14 - this was `except Exception: continue`.
                # attach_bot has already created a fresh BotLedger for
                # this bot, so a dropped row does not merely skip it:
                # it leaves that bot reading $0.00 wired_in / $0.00
                # wired_out for the whole session. That is the operator
                # bug of 2026-05-13 which import_ledgers exists to fix,
                # re-armed one row at a time and reported by nobody.
                #
                # The overlay writes field by field, so the row is also
                # PARTIALLY applied - whichever assignments ran before
                # the raise are still on the ledger. That ordering is a
                # separate defect and is NOT changed here; this log
                # makes it visible instead of silent.
                #
                # THE BREADTH IS DELIBERATE. bot_container catches
                # anything that escapes (bot_container.py:3418), so
                # narrowing would drop this row AND every row after it
                # rather than only this one.
                dropped += 1
                logger.warning(
                    "SmartWire: import DROPPED ledger row for %s "
                    "(%s: %s) - the row is PARTIALLY applied and that "
                    "bot's wire totals are wrong for this session",
                    bid, type(exc).__name__, exc)
                continue
        if n > 0:
            logger.info(
                "SmartWire: imported %d ledger(s) from saved state", n)
        # The headline must RECONCILE: accepted + lost == offered, and
        # `offered` is now every element of the list. It fires on any
        # loss, whichever of the three causes produced it - the guard
        # cases used to be completely silent here.
        lost = malformed + unidentified + dropped
        if lost:
            logger.warning(
                "SmartWire: import accepted %d of %d ledger row(s) "
                "offered; %d lost (%d raised, %d not a row, %d had no "
                "bot_id) - each lost row is one bot's lifetime "
                "wired_in/wired_out and provenance, absent for this "
                "session and not recoverable from the save",
                n, offered, lost, dropped, malformed, unidentified)
        return n

    def import_wires(self, wires: list[dict]) -> int:
        """Restore wires from a snapshot produced by export_wires().
        Returns the count of successfully imported wires. Idempotent —
        re-importing the same snapshot is a no-op (same key overwrite).
        """
        if not isinstance(wires, list):
            return 0

        # 10.3 phase 2 — the import starts HERE, after the type guard.
        # That guard returns WITHOUT emitting, so it needs no duration:
        # there is no record to carry one.
        _dur_t0 = time.monotonic()
        n = 0
        offered = 0
        # 2026-08-15 - THE SIBLING DEFECT, OPPOSITE SHAPE. import_ledgers
        # (above) was repaired for a wrong NUMBER. Here the number is
        # right and the operator-visible REPORT was missing. The
        # topology.09.002 emitter below already sends
        # `expected=len(wires)`, the true offered count, so the emitted
        # pair reconciles and that pin can genuinely fail. But the three
        # guards below dropped rows with no counter and no log line, so
        # a six-row topology losing four rows wrote exactly one line:
        # "SmartWire: imported 2 wire(s) from saved state" - true,
        # cheerful, and hiding four vanished transfer routes. On TOTAL
        # loss the method said nothing at all, because the INFO below is
        # guarded by `if n > 0`.
        #
        # WHAT A LOST WIRE COSTS. `_wires` is read by exactly one
        # money-moving consumer, distribute_fold_profit, which does
        # `outgoing = self._wires.get(source_id)` and returns at once
        # when it is empty. So a lost wire is not a lost log line: that
        # source bot's realised fold profit is never divided,
        # apply_wire_income is never called on the target, no
        # WireTransaction is recorded, and the target's wired_in never
        # grows. Every visibility log in that method - the dust-skip
        # line, the target-unreachable line, the "produced no routed
        # shares" summary - sits INSIDE the loop over `outgoing`, so the
        # one failure mode where the route itself vanished is the only
        # one it cannot report.
        #
        # WHY A GUARD-DROP IS A CORRUPT SAVE, NOT ROUTINE FILTERING.
        # export_wires (above) appends a dict literal carrying
        # str(source_id), str(target_id) and float(pct);
        # state_manager.save_state stores that list verbatim
        # (state_manager.py:90); state_manager.delete_bot only FILTERS
        # rows out, never adds one (state_manager.py:241-244). `_wires`
        # has only two writers - register_wire and this method - and
        # both enforce the same predicate. So no writer in this codebase
        # can produce a non-dict row, an unreadable pct, or a pct
        # outside 0-100. Each message below therefore says the save is
        # corrupt rather than implying a row was filtered on purpose.
        #
        # The three causes are counted SEPARATELY because they differ in
        # what can be reported: a non-dict row cannot name either
        # endpoint, an unreadable pct knows both endpoints, and an
        # unroutable row knows which predicate failed. Merging them
        # would hide which of the three the operator is looking at.
        malformed = 0    # row was not a dict at all
        unreadable = 0   # float(pct) raised
        unroutable = 0   # no endpoint, or pct outside 0 < pct <= 100
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
                    offered, len(wires), type(w).__name__)
                continue
            src = w.get("source_id")
            tgt = w.get("target_id")
            # ── HOLE 1 (2026-08-15): THE EXCEPT TUPLE WAS TOO
            # NARROW. This was `except (TypeError, ValueError)`, and
            # float() has a THIRD failure mode neither of those covers:
            # OverflowError, raised when the operand is an int too large
            # for a double. json.loads parses integer literals at
            # arbitrary precision, so a bare integer of 309 to 4300
            # digits in a corrupt, truncated or hand-edited save reaches
            # this line and raises. (309 is the smallest all-nines
            # integer that overflows a double; 4300 is
            # sys.get_int_max_str_digits(), above which json.loads
            # itself refuses. Both edges measured.) OverflowError is an
            # ArithmeticError, so it is neither a TypeError nor a
            # ValueError and the tuple let it straight through.
            #
            # THE ESCAPE COST THE WHOLE RESTORE, NOT THIS ROW. The raise
            # left `self._wires` PARTIALLY applied, ran neither the
            # per-row line nor the reconciling headline below (both live
            # after the loop), and never reached the emitter - so
            # topology.09.002 produced NO RECORD AT ALL rather than a
            # disagreeing pair. BotManager.restore_smart_wires_from_state
            # then caught it (bot_container.py:3404-3407) and returned
            # 0, which additionally skipped the ledger import at
            # :3412-3421 and the wire.created re-emit at :3426. Measured
            # against the operator's own 33-row topology: one planted
            # row destroyed 33 wires and 50 ledgers and wrote a single
            # line that named none of them.
            #
            # THE BREADTH IS DELIBERATE, and the argument is the sibling
            # import_ledgers' own (above): the caller catches anything
            # that escapes, so narrowing drops this row AND every row
            # after it rather than only this one. It is strictly
            # stronger here, because that caller also drops the ledgers
            # and the re-emit.
            #
            # THE GUARDED REGION IS THE COERCION AND NOTHING ELSE, and
            # it must stay that way. It must never grow to cover the
            # store and `n += 1` below - a failed store swallowed as
            # "unreadable" would shrink the topology while the headline
            # still reconciled, which is a lie that reads as truth - nor
            # the logger calls, where a broken format string would make
            # a row vanish with no line at all, the exact defect this
            # method was repaired for, nor the range guard, whose
            # predicate must stay a decision rather than an exception
            # path. Widen an except around a COERCION of untrusted
            # input; never around code that should not throw.
            #
            # WHAT IS CAUGHT IS STILL COUNTED AND STILL NAMED. `exc` is
            # bound and its type printed, as import_ledgers does, and
            # `unreadable` still feeds `lost`, so accepted + lost ==
            # offered continues to hold.
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
                    offered, len(wires), src, tgt, w.get("pct"),
                    type(exc).__name__, exc, src, tgt)
                continue
            # ── HOLE 2 (2026-08-15): nan PASSED THIS GUARD. The
            # math.isnan clause is new. nan is UNORDERED, so `nan <= 0`
            # is False and `nan > 100` is False; a nan pct satisfied
            # every clause, was stored, and was counted as an imported
            # wire. It was the one bad shape that was broken AND silent
            # AND reported as a success - every other one was at least
            # refused and named.
            #
            # Measured before this clause existed: register_wire took
            # nan, export_wires wrote it, json.dumps emitted a bare
            # `NaN` token (which RFC 8259 does not allow), import_wires
            # read it back and returned n=2 of 2 with no dropped line
            # and no headline, and distribute_fold_profit then computed
            # `share = profit * nan / 100 = nan` and booked a
            # WireTransaction of nan as a COMPLETED transfer. Its dust
            # floor could not stop that either, because `nan < min_wire`
            # is False as well.
            #
            # THIS IS A GUARD HOLE, NOT AN EXCEPT HOLE. nan never
            # raises, so no width of except above can reach it; the
            # treatment has to be in the predicate. inf is already
            # refused by `pct > 100` - measured - so this clause admits
            # exactly one new rejected class and changes the verdict for
            # nothing else. The operator's 33 real rows are untouched.
            if (not src or not tgt or math.isnan(pct)
                    or pct <= 0 or pct > 100):
                unroutable += 1
                if not src:
                    why = "source_id is empty"
                elif not tgt:
                    why = "target_id is empty"
                elif math.isnan(pct):
                    # NOT "outside the range". That sentence would be
                    # false and would hide the mechanism: nan is not
                    # outside 0 < pct <= 100, it is unordered, and both
                    # comparisons returning False is precisely why this
                    # row used to be accepted.
                    why = ("pct is nan, which is unordered - it is not "
                           "outside 0 < pct <= 100, both comparisons "
                           "are False, and that is exactly why this row "
                           "used to be stored and counted as imported")
                else:
                    why = "pct is outside the accepted 0 < pct <= 100"
                logger.warning(
                    "SmartWire: import DROPPED wire row %d of %d, "
                    "%s -> %s @ %r - %s. No writer here produces that, "
                    "so the save is corrupt; that transfer route does "
                    "not exist this session and the fold profit it "
                    "carried stays in the source bot",
                    offered, len(wires), src, tgt, pct, why)
                continue
            self._wires.setdefault(str(src), {})[str(tgt)] = pct
            n += 1
        # The headline must RECONCILE: accepted + lost == offered, and
        # `offered` is every element of the list because it is counted
        # ABOVE the first guard - the exact ordering import_ledgers was
        # repaired for. It is also the SAME number topology.09.002 sends
        # as `expected`; if those two can ever disagree, one is wrong.
        #
        # `if lost:` is what keeps a clean restore silent. The operator
        # restores on every launch and carries a guard-clean topology,
        # so a line he sees every time is noise he learns to ignore -
        # which is the same defect as silence.
        # 10.3 phase 2 — STOP HERE. `n` and `offered` are final, so the
        # import is over. What follows is REPORTING: the accepted-count
        # line, the lost-row tally and the operator warning. Timing
        # those would bill the report to the import, and making the log
        # cheaper would read as a faster import. Same boundary as
        # fleet.03.001 and 03.004.
        #
        # 2026-08-22 — THE ACCEPTED-COUNT LINE USED TO SIT ABOVE THIS
        # CLOCK, and the comment above already said it should not. The
        # code disagreed with its own stated boundary, so the duration
        # this method declared was the import PLUS one log dispatch.
        #
        # WHAT THAT COST, MEASURED. A log dispatch is a CONSTANT: it
        # fires once whatever the row count, and its price is set by how
        # many handlers the root logger carries, which is a property of
        # the process and not of the import. Measured 2026-08-22 with 16
        # console handlers attached and the root logger at DEBUG, one
        # such dispatch cost 0.001585 s, the minimum of twenty. Against
        # a 1_000-row import that really costs 0.000290 s, the declared
        # duration became 0.001965 s — five parts report to one part
        # work. The operator reading this pin was reading his own
        # console painting.
        #
        # AND IT IS NOT A SMALL ERROR ON THE LARGE SIDE EITHER. The same
        # constant landed on a 10_000-row import, so the two readings
        # moved together and their RATIO collapsed from 10.4 to 2.4.
        # tests/test_wires_received_duration.py asks whether the
        # duration grows with the work; with the report inside the
        # bracket that question was being asked of a number that was
        # mostly not the work, and the release gate went red on it.
        # Moving the line down repairs the measurement. It changes no
        # log text, no log level and no log ORDER — this line still
        # precedes the lost-row warning below, exactly as before.
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
                n, offered, lost, malformed, unreadable, unroutable)
        # ── DIRECTIVE 4 EMITTER — "RECEIVES ... topologies" ──────────
        # import_wires does NO existence check against _bot_refs: it
        # setdefaults every well-formed row and returns the count. So a
        # topology can import cleanly and reference bots that do not
        # exist in this run. Reporting the return value as though it
        # were the ACTIVE count is the "40 wires, $0.00 routed" failure.
        # expected = rows offered, actual = rows accepted.
        try:
            from src.core.signal_contract import emit as _w
            _w("topology.09.002.postcondition.wires_received", actual=n,
               expected=len(wires) if isinstance(wires, list) else 0,
               duration=_dur_elapsed,
               context={"sources": len(self._wires)})
        except Exception:  # noqa: BLE001,S110 - advisory
            pass
        return n

    def distribute_fold_profit(self, source_id: str, profit_usd: float,
                               ref: str = "") -> list[dict]:
        """Route pct% of source_id's realised fold profit to each target
        configured in the wire network.

        For each wire (source → target, pct%):
          - Compute share = profit_usd × pct / 100
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
        # v3.15.74 — emit visibility logs on the silent-skip paths so the
        # operator can see WHY no flow happened (operator directive
        # 2026-04-26). Pull bus lazily to avoid coupling at construction.
        # C17 — injected bus wins. Falling through to get_event_bus()
        # here is what put a sim manager's wire logs on the live bus.
        _vis_bus = getattr(self, "_bus", None)
        if _vis_bus is None:
            try:
                from ..core.event_bus import get_event_bus as _gb_skip
                _vis_bus = _gb_skip()
            except Exception:  # R28-OK: bus init optional; None is the safe fallback
                _vis_bus = None
        _src_short_skip = (str(source_id)[:8] + "\u2026"
                           if len(str(source_id)) > 8
                           else str(source_id))
        # 2026-08-14 - notice-emit failures are counted here and
        # reported once, after the loop. A WARNING per wire would spam
        # a fleet with many wires; silence is what this replaces.
        _notice_emit_fails: list[str] = []
        # v3.23.65 \u2014 Smart Wire Outflow Safety (SWOS). Compute the
        # per-wire safety ceiling ONCE per source scrum event, before
        # the outbound loop. Ceiling is divided across the N
        # outbound wires per operator directive 2026-07-31 \u00a7 8.3.
        # Fall-through (safety = 100) when source bot doesn't expose
        # get_swos_inputs OR the inputs are incomplete \u2014 this keeps
        # existing non-ScrummingBot wires (Extractors, etc.) working
        # without change. Recompute happens at wire-fire time
        # (\u00a7 8.3 addendum) \u2014 right here, not at scrum-detect time.
        _per_wire_safe_pct = 100.0
        _swos_safe_pct = 100.0
        try:
            _src_bot = self._bot_refs.get(source_id)
            _swos_getter = getattr(
                _src_bot, "get_swos_inputs", None)
            if _swos_getter is not None:
                _swos_inputs = _swos_getter()
                if _swos_inputs:
                    _swos_safe_pct = compute_safe_outflow_pct(
                        scrum_profit_usd=float(profit_usd),
                        **_swos_inputs)
                    _n_wires = max(1, len(outgoing))
                    _per_wire_safe_pct = _swos_safe_pct / _n_wires
                    logger.debug(
                        "SWOS %s: safe=%.2f%% \u00f7 %d wires = "
                        "%.2f%% per-wire (profit=$%.4f)",
                        _src_short_skip, _swos_safe_pct,
                        _n_wires, _per_wire_safe_pct, profit_usd)
        except Exception as _swos_exc:  # noqa: BLE001 - best-effort
            logger.debug(
                "SWOS %s pre-check raised %s \u2014 falling back to "
                "raw operator pct (no safety cap this fire).",
                _src_short_skip, _swos_exc)
        for target_id, raw_pct in outgoing.items():
            # v3.23.65 \u2014 effective pct = min(operator's rate, per-wire
            # safe pct). Never exceeds either. When SWOS is
            # unavailable, per_wire_safe_pct = 100.0 so this is a
            # no-op and behaviour matches pre-v3.23.65.
            pct = min(float(raw_pct), _per_wire_safe_pct)
            share = profit_usd * float(pct) / 100.0
            _tgt_short_skip = (str(target_id)[:8] + "\u2026"
                               if len(str(target_id)) > 8
                               else str(target_id))
            if share < self._min_wire:
                results.append({"target_id": target_id, "pct": pct,
                                "share": share, "applied": False,
                                "reason": "below min_wire_amount"})
                # v3.15.74 — visible dust-skip log on BOTH source and
                # target buses with WIRE FLOW prefix so it picks up the
                # magenta styling in StatusLog._render.
                if _vis_bus is not None:
                    _dust_msg = (
                        f"WIRE FLOW (dust skip): ${share:.4f} from "
                        f"{_src_short_skip} \u2192 {_tgt_short_skip} below "
                        f"floor ${self._min_wire:.2f} (pct={pct:.1f}%)")
                    try:
                        _vis_bus.emit("bot.log", bot_id=source_id,
                                      message=_dust_msg)
                        _vis_bus.emit("bot.log", bot_id=target_id,
                                      message=_dust_msg)
                    except Exception as _emit_exc:
                        # THE BREADTH IS DELIBERATE. This block is
                        # OUTSIDE the per-route try below, so an escape
                        # would abandon every remaining wire in this
                        # fold and skip transfers that would otherwise
                        # happen. Counted, not warned per wire.
                        _notice_emit_fails.append("dust-skip")
                        logger.debug(
                            "SmartWire: dust-skip notice for %s -> %s "
                            "did not reach the bus (%s: %s)",
                            _src_short_skip, _tgt_short_skip,
                            type(_emit_exc).__name__, _emit_exc)
                continue
            target = self._bot_refs.get(target_id)
            if target is None or not hasattr(target, "apply_wire_income"):
                results.append({"target_id": target_id, "pct": pct,
                                "share": share, "applied": False,
                                "reason": "target bot not attached"})
                # v3.15.74 — visible "target unreachable" log so wires
                # pointing at deleted/orphaned bots produce console
                # feedback rather than silent failure.
                if _vis_bus is not None:
                    _orphan_msg = (
                        f"WIRE FLOW (target unreachable): ${share:.4f} "
                        f"from {_src_short_skip} \u2192 {_tgt_short_skip} "
                        f"\u2014 target bot not attached. Wire is orphaned.")
                    try:
                        _vis_bus.emit("bot.log", bot_id=source_id,
                                      message=_orphan_msg)
                    except Exception as _emit_exc:
                        # Same containment reason as the dust-skip
                        # notice above: an escape here would skip every
                        # later wire in this fold.
                        _notice_emit_fails.append("target-unreachable")
                        logger.debug(
                            "SmartWire: orphan-wire notice for %s -> "
                            "%s did not reach the bus (%s: %s)",
                            _src_short_skip, _tgt_short_skip,
                            type(_emit_exc).__name__, _emit_exc)
                continue
            try:
                r = target.apply_wire_income(share, source=source_id,
                                             ref=ref)
                # v3.15.90 (F1 fix from 2026-04-26 silent-result-dict
                # audit): apply_wire_income returns
                # {"applied": False, "reason": ...} on bad input
                # (usd <= 0, non-numeric, etc). Pre-fix, the caller
                # IGNORED r["applied"] and unconditionally:
                #   - recorded a WireTransaction in self._transactions
                #   - emitted "WIRE FLOW: $X routed from src→tgt" on
                #     both buses
                #   - appended {"applied": True, "result": r} to results
                # That produced false fund-movement visibility — the
                # operator saw the magenta WIRE FLOW log but the target
                # bot's fold queue / pending bucket DIDN'T change.
                # Same shape as v3.15.74 dust-skip but one layer up.
                #
                # Fix: branch on r.get("applied"). True path is the
                # original happy emit. False path emits a clearly-
                # distinct "WIRE FLOW (target refused)" log so the
                # operator sees the refusal rather than a celebration,
                # and the transaction is NOT recorded.
                _target_applied = bool(r.get("applied", False)) if isinstance(r, dict) else False
                _src_short = (str(source_id)[:8] + "…"
                              if len(str(source_id)) > 8
                              else str(source_id))
                _tgt_short = (str(target_id)[:8] + "…"
                              if len(str(target_id)) > 8
                              else str(target_id))

                if not _target_applied:
                    # F1 fix: target refused the income (bad input,
                    # validation failure, or other non-success). Do
                    # NOT record a transaction. Emit a refused-flow
                    # log so the operator sees the refusal.
                    _refusal_reason = (
                        r.get("reason", "target refused without reason")
                        if isinstance(r, dict)
                        else f"target returned non-dict: {type(r).__name__}")
                    if _vis_bus is not None:
                        try:
                            _vis_bus.emit(
                                "bot.log", bot_id=source_id,
                                message=(
                                    f"WIRE FLOW (target refused): "
                                    f"${share:.4f} from {_src_short} → "
                                    f"{_tgt_short} ({pct:.1f}% of fold "
                                    f"profit) — target apply_wire_income "
                                    f"returned applied=False. Reason: "
                                    f"{_refusal_reason}. NO transfer "
                                    f"booked."))
                            _vis_bus.emit(
                                "bot.log", bot_id=target_id,
                                message=(
                                    f"WIRE FLOW (own apply refused): "
                                    f"${share:.4f} from {_src_short} → "
                                    f"{_tgt_short} — apply_wire_income "
                                    f"refused. Reason: {_refusal_reason}."))
                        except (AttributeError, TypeError,
                                RuntimeError, ValueError) as _emit_exc:
                            # NARROWED, and this is the ONLY one of the
                            # nine where narrowing is safe. An escape
                            # lands in the sibling handler below, in
                            # the SAME loop iteration: it still records
                            # applied=False and the loop still reaches
                            # every remaining wire, so no transfer is
                            # added, removed or misreported. At every
                            # other site an escape would either skip
                            # later wires or mark a BOOKED transfer as
                            # failed.
                            #
                            # EventBus.emit already swallows subscriber
                            # errors (event_bus.py:251-255), so what
                            # can reach here is a broken bus object
                            # (AttributeError), a bad signature or a
                            # raising filter_fn (TypeError,
                            # RuntimeError), or a refusal reason whose
                            # __format__ raises (ValueError).
                            logger.warning(
                                "SmartWire: target-refused notice for "
                                "%s -> %s ($%.4f) did not reach the "
                                "operator console (%s: %s); the "
                                "refusal stands and is in the result",
                                _src_short, _tgt_short, share,
                                type(_emit_exc).__name__, _emit_exc)
                    results.append({"target_id": target_id, "pct": pct,
                                    "share": share, "applied": False,
                                    "reason": _refusal_reason,
                                    "result": r})
                    continue

                # Audit trail (only on success — F1 fix)
                import time as _t
                self._transactions.append(WireTransaction(
                    timestamp=int(_t.time()),
                    source_bot=source_id,
                    target_bot=target_id,
                    amount=share,
                    wire_type="WIRE_BACK",
                    reason=f"fold_profit pct={pct}% ref={ref}"))
                # v3.15.68 — clear, color-coded operator-visible feedback
                # on BOTH source and target bot buses. Prefix "WIRE FLOW:"
                # gets magenta styling in StatusLog._render so wire
                # routing is visually distinct from regular bot.log
                # chatter and from TRADE NOTIFICATION trade events.
                # Where did the income land in the target?
                _placement = ""
                try:
                    if isinstance(r, dict):
                        # Rewritten from a nested-quote f-string, which
                        # needs PEP 701 (3.12+) and which ruff parses
                        # against this project's target as a syntax
                        # error. Same value, one step at a time.
                        _placement = " → " + str(
                            r.get("placement", "tranche"))
                        _tranche_idx = r.get("tranche_index")
                        if _tranche_idx is not None:
                            _placement += " #" + str(_tranche_idx)
                except Exception as _place_exc:
                    # The comment here used to read "bus emit
                    # best-effort". There is no bus emit in this block
                    # and there never was - the comment was copied from
                    # a neighbour and was false. What this guards is
                    # str() over values the TARGET bot returned, so a
                    # hostile or buggy __str__ does raise here.
                    #
                    # THE BREADTH IS DELIBERATE. This sits INSIDE the
                    # per-route try, AFTER apply_wire_income has moved
                    # the money, so an escape would be caught below and
                    # would report a completed, booked transfer as a
                    # failure. Reset to "" so a half-built suffix
                    # cannot reach the operator's WIRE FLOW line.
                    _placement = ""
                    logger.warning(
                        "SmartWire: could not render placement for the "
                        "%s -> %s wire ($%.4f) (%s: %s); the WIRE FLOW "
                        "line omits where the income landed",
                        _src_short, _tgt_short, share,
                        type(_place_exc).__name__, _place_exc)
                _flow_msg = (
                    f"WIRE FLOW: ${share:.2f} from {_src_short} → "
                    f"{_tgt_short} ({pct:.1f}% of fold profit"
                    f"{f', ref={ref}' if ref else ''}){_placement}")
                try:
                    # C17 — injected bus wins; see __init__.
                    _bus = getattr(self, "_bus", None)
                    if _bus is None:
                        from ..core.event_bus import get_event_bus as _gb
                        _bus = _gb()
                    _bus.emit("bot.log", bot_id=source_id, message=_flow_msg)
                    _bus.emit("bot.log", bot_id=target_id, message=_flow_msg)
                except Exception as _emit_exc:
                    # THE MONEY HAS ALREADY MOVED. apply_wire_income
                    # returned applied=True above and the
                    # WireTransaction is already in self._transactions.
                    # A silent swallow here is the one case where a
                    # real, completed transfer produces no operator-
                    # visible line anywhere, so this names both bot ids
                    # AND the amount.
                    #
                    # THE BREADTH IS DELIBERATE AND MUST NOT BE
                    # NARROWED, and this must never re-raise: it is
                    # inside the per-route try, so an escape would be
                    # caught below and would append applied=False for a
                    # transfer that DID happen.
                    logger.warning(
                        "SmartWire: WIRE FLOW notice for a COMPLETED "
                        "transfer of $%.4f from %s to %s did not reach "
                        "the operator console (%s: %s); the transfer "
                        "stands and is in the audit trail",
                        share, source_id, target_id,
                        type(_emit_exc).__name__, _emit_exc)
                results.append({"target_id": target_id, "pct": pct,
                                "share": share, "applied": True,
                                "result": r})
            except Exception as exc:
                logger.warning(
                    "SmartWire: route %s->%s raised: %s",
                    source_id, target_id, exc)
                results.append({"target_id": target_id, "pct": pct,
                                "share": share, "applied": False,
                                "reason": f"exception: {exc}"})
                # v3.15.74 — surface routing exceptions so the operator
                # knows a wire blew up rather than guessing at silence.
                if _vis_bus is not None:
                    try:
                        _vis_bus.emit(
                            "bot.log", bot_id=source_id,
                            message=(
                                f"WIRE FLOW (error): ${share:.4f} from "
                                f"{_src_short_skip} \u2192 {_tgt_short_skip} "
                                f"raised {type(exc).__name__}: {exc}"))
                    except Exception as _emit_exc:
                        # DEBUG on purpose, not WARNING. The route
                        # failure itself was already logged at WARNING
                        # a few lines up, so a second WARNING here
                        # would double-count one event. What is lost
                        # here is only the console copy.
                        #
                        # THE BREADTH IS DELIBERATE: an escape from
                        # inside this handler would leave the for loop
                        # and abandon every wire after this one.
                        logger.debug(
                            "SmartWire: route-error notice for %s -> "
                            "%s did not reach the bus (%s: %s)",
                            _src_short_skip, _tgt_short_skip,
                            type(_emit_exc).__name__, _emit_exc)
        # v3.15.74 — per-fold summary when nothing routed. If the source
        # bot has wires configured but EVERY route was filtered (dust,
        # unreachable, or errored), emit one summary log so the operator
        # has a single-glance signal that the fold produced no flow.
        try:
            applied_count = sum(1 for r in results if r.get("applied"))
            if results and applied_count == 0 and _vis_bus is not None:
                dust = sum(
                    1 for r in results
                    if r.get("reason") == "below min_wire_amount")
                unreach = sum(
                    1 for r in results
                    if r.get("reason") == "target bot not attached")
                errs = sum(
                    1 for r in results
                    if str(r.get("reason", "")).startswith("exception"))
                _vis_bus.emit(
                    "bot.log", bot_id=source_id,
                    message=(
                        f"WIRE FLOW: fold ${profit_usd:.4f} produced "
                        f"no routed shares ({len(results)} wire(s) "
                        f"checked: {dust} dust-skipped, "
                        f"{unreach} unreachable, {errs} errored)"))
        except Exception as _emit_exc:
            # DEBUG: nothing routed, no money crossed this block, and
            # `results` is already complete and is returned unchanged.
            #
            # THE BREADTH IS DELIBERATE: this method documents that
            # failures "do NOT raise - the fold path continues", and an
            # escape here would break that contract after money had
            # already moved on the successful wires.
            logger.debug(
                "SmartWire: no-flow summary for %s did not reach the "
                "bus (%s: %s)",
                _src_short_skip, type(_emit_exc).__name__, _emit_exc)
        # Outside the try above on purpose: a broken bus is exactly the
        # condition this line reports, so it must not depend on it.
        if _notice_emit_fails:
            logger.warning(
                "SmartWire: %d wire-notice emit(s) failed during the "
                "fold on %s (%s); those wire events are missing from "
                "the operator console",
                len(_notice_emit_fails), _src_short_skip,
                ", ".join(sorted(set(_notice_emit_fails))))
        return results

    def register_bot(self, bot_id: str, asset: str,
                     seed_amount: float = 200.0,
                     funder_bot_id: Optional[str] = None) -> None:
        """Register a bot in the smart wire network.

        v3.13.5 — optional funder_bot_id parameter enables the
        Mature-Profit Cascade: if provided, the new bot's provenance
        records the funder (not SEED) and the funder is debited.
        Otherwise falls back to SEED funding (initial bot or manual
        registration).
        """
        if funder_bot_id is None:
            # Traditional SEED registration
            provenance = {"SEED": seed_amount}
        else:
            # Cascade registration: funded by an existing bot
            provenance = {funder_bot_id: seed_amount}

        self._ledgers[bot_id] = BotLedger(
            bot_id=bot_id,
            asset=asset,
            provenance=provenance,
            starting_balance=seed_amount,   # v3.13.5 — capture for PPS lookup
        )
        source_label = funder_bot_id or "SEED"
        logger.info("SmartWire: registered %s (%s) with $%.2f from %s",
                     bot_id, asset, seed_amount, source_label)

    # ══════════════════════════════════════════════════════════════════
    # v3.13.5 — Mature-Profit Cascade API
    #
    # User directive (Session 18): 'MR determination should be off of
    # Mature Profits presence first. First success launches second which
    # compounds first and spawns third which compounds the second...'
    #
    # Cascade rules:
    # 1. Threshold to spawn = starting balance of the bot's primary
    #    Provenance Source (PPS). For bot 1, PPS = SEED and starting
    #    balance = the original seed_amount. For bot N, PPS = bot N-1
    #    and starting balance = bot N-1's starting_balance.
    # 2. When bot N's mature_profit_available >= threshold, it may
    #    fund a new bot. Exactly $threshold is transferred. Bot N's
    #    mature_profit_allocated is debited by that amount. Bot N's
    #    original stake is untouched — preserved as liquidity buffer.
    # 3. The new bot starts with exactly $threshold (which equals bot
    #    N's own starting_balance). This creates a self-propagating
    #    invariant where every bot in the cascade starts with the
    #    original seed amount.
    #
    # Safety: hard cap on bot count and system brake (RSS/regime) were
    # previously enforced upstream by MRSpawnController in the retired
    # nuclear_live.py engine (v3.18.3 deletion). The new Nuclear Mode
    # under src/gui/simulator_tab/ will re-introduce these gates against
    # the real BotManager rather than a parallel implementation.
    # This module continues to handle the mature-profit check + the
    # actual capital transfer regardless of which upstream gate fires.
    # sadp: R60 P1
    # ══════════════════════════════════════════════════════════════════

    def primary_provenance_starting_balance(
            self, bot_id: str) -> Optional[float]:
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
            # No other-bot source → PPS is SEED. Starting balance
            # equals the SEED entry in provenance.
            return float(ledger.provenance.get("SEED", 0.0))
        # PPS is another bot. Look up ITS starting balance.
        pps_ledger = self._ledgers.get(pps)
        if pps_ledger is None:
            # PPS bot not registered — fall back to this bot's own
            # starting balance as the threshold (safe default:
            # maintains the cascade invariant that everyone starts with
            # the same amount).
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
            return (False, 0.0,
                    f"insufficient_mature (${available:.2f} < "
                    f"${threshold:.2f})")

        return True, threshold, "ok"

    def execute_spawn_wire(self, funder_bot_id: str, new_bot_id: str,
                            new_bot_asset: str,
                            timestamp: int = 0) -> Optional[WireTransaction]:
        """Perform the cascade spawn:
          1. Verify funder can fund (re-checks the gate)
          2. Debit funder's mature_profit_allocated
          3. Register the new bot with funder as provenance source
          4. Record a WireTransaction (type=MR_FUND)
          5. Return the transaction (or None if gate fails)
        """
        approved, amount, reason = self.can_fund_new_bot(funder_bot_id)
        if not approved:
            logger.info(
                "SmartWire spawn gate declined: funder=%s reason=%s",
                funder_bot_id, reason)
            return None

        funder = self._ledgers[funder_bot_id]
        funder.mature_profit_allocated += amount
        funder.wired_out += amount

        # Register the new bot with funder as provenance source
        self.register_bot(new_bot_id, new_bot_asset,
                          seed_amount=amount,
                          funder_bot_id=funder_bot_id)
        # wired_in on the new bot is $amount (since it was funded by
        # another bot, not SEED)
        self._ledgers[new_bot_id].wired_in = amount

        tx = WireTransaction(
            timestamp=timestamp,
            source_bot=funder_bot_id,
            target_bot=new_bot_id,
            amount=amount,
            wire_type="MR_FUND",
            reason=(f"mature-profit cascade spawn "
                    f"(threshold=${amount:.2f})"))
        self._transactions.append(tx)
        logger.info(
            "SmartWire cascade: %s → %s funded with $%.2f "
            "(funder retains stake + $%.2f excess mature)",
            funder_bot_id, new_bot_id, amount,
            funder.mature_profit_available)
        return tx

    def record_profit(self, bot_id: str, amount: float) -> None:

        # sadp: R28 R29 R33  # profit record: fail-loudly(R28) idempotent(R29) append-only(R33)
        """Record realized profit for a bot (from scrum-fold cycles)."""
        if bot_id in self._ledgers:
            self._ledgers[bot_id].total_profit += amount
            self._ledgers[bot_id].available_profit += amount

    def process_wires(self, undervalued_bots: list[str] = None,
                      timestamp: int = 0) -> list[WireTransaction]:

        # sadp: R28 R29  # wire processing: fail-loudly(R28) idempotent(R29)
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
