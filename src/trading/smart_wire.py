"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
Smart wire profit routing between accumulation bots.

SmartWireManager holds the wire topology and one BotLedger per bot.
WireRoutingMixin._route_scrum_proceeds_via_wires reads that topology and sends
each wired target its share of a sale's surplus, capped by
compute_safe_outflow_pct.
"""

from __future__ import annotations
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("acervator.smart_wire")

MATURE_GROWTH_PCT: float = 200.0
"""A position is mature once its value exceeds its cost basis by this percent."""


def routable_pct(value) -> Optional[float]:
    """One stored wire percent as a float, or None when no reading admits it.

    The rule the Bot Swarm tab draws its Wire % cell by, so a saved percent the
    screen prints as an em dash can never route a share. Delegates to
    `as_finite_float`, imported inside the call so this module drags no bot
    configuration in at import time.
    """
    from .container.config import as_finite_float

    return as_finite_float(value)


def pct_kind_refusal(pct) -> Optional[str]:
    """Why a wire percent's kind is unusable, or None when the kind is usable.

    A bool is the one kind `float()` turns into a figure nobody stored:
    `float(True)` answers 1.0, which would stand as a one percent wire.
    """
    if type(pct) is bool:
        return (
            f"pct must be a number, not a {type(pct).__name__}; "
            f"float({pct!r}) answers {float(pct)} and nothing stored "
            f"that figure"
        )
    return None


def mature_threshold_usd(cost_basis_usd: float) -> float:
    """Return the value one position must reach to be mature.

    The threshold is the cost basis plus MATURE_GROWTH_PCT per cent of it, so
    a 200.0 threshold puts it at three times the cost. An unusable cost basis
    answers 0.0, which is_mature reads as no position.
    """
    try:
        basis = float(cost_basis_usd or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(basis) or basis <= 0.0:
        return 0.0
    return basis * (1.0 + MATURE_GROWTH_PCT / 100.0)


def is_mature(cost_basis_usd: float, current_value_usd: float) -> bool:
    """Return True when the position's value reaches mature_threshold_usd.

    get_aggregate_stats counts the mature positions with it, so a position
    sitting exactly on the threshold is counted even though mature_profit_usd
    answers 0.0 for it.
    """
    threshold = mature_threshold_usd(cost_basis_usd)
    if threshold <= 0.0:
        return False
    try:
        value = float(current_value_usd or 0.0)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value) and value >= threshold


def mature_profit_usd(cost_basis_usd: float, current_value_usd: float) -> float:
    """Return the part of one position's value that sits over mature_threshold_usd.

    A position under the threshold contributes 0.0, and a mature one
    contributes the amount over the threshold rather than its whole profit:
    a 100.00 cost basis worth 350.00 contributes 50.00. BotLedger
    .mature_profit_total reads it against a bot's seed capital and
    get_aggregate_stats reads it against the exchange cost basis of the
    holdings.
    """
    if not is_mature(cost_basis_usd, current_value_usd):
        return 0.0
    return float(current_value_usd) - mature_threshold_usd(cost_basis_usd)


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
    """Return the exportable share of scrum_profit_usd as a percentage.

    The result is a float in [0.0, 100.0]; it is 0.0 when
    scrum_profit_usd is not positive or raw_safe_pct is under 1.0.
    """
    if scrum_profit_usd <= 0:
        return 0.0

    # 0 = at/below band_lower (imminent Fold); 1 = at/above band_upper (deep in Scrum).
    if band_upper <= band_lower:
        distance_to_fold_pct = 0.0
    else:
        distance_to_fold_pct = max(
            0.0, min(1.0, (current_price - band_lower) / (band_upper - band_lower))
        )

    # Safety factor ranges 0.2 (deep Scrum) to 2.0 (imminent Fold).
    if band_upper <= band_lower:
        safety_factor = 2.0
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

    if raw_safe_pct < 1.0:
        return 0.0
    return min(100.0, raw_safe_pct)


@dataclass
class WireTransaction:
    """One transfer booked by SmartWireManager, typed by wire_type."""

    timestamp: int
    source_bot: str
    target_bot: str
    amount: float
    wire_type: str  # "MR_FUND" | "WIRE_BACK"
    reason: str = ""


@dataclass
class BotLedger:
    """Profit provenance and wire totals for one bot.

    provenance maps each funder id to the amount it supplied, with
    "SEED" for the initial capital. mature_profit_allocated carries what
    a saved ledger recorded as transferred to child bots; no code in this
    build writes it.
    """

    bot_id: str
    asset: str
    total_profit: float = 0.0
    available_profit: float = 0.0
    wired_in: float = 0.0
    wired_out: float = 0.0
    provenance: dict = field(default_factory=dict)  # source_bot_id → amount
    starting_balance: float = 0.0
    mature_profit_allocated: float = 0.0

    @property
    def predominant_source(self) -> Optional[str]:
        """Return the largest non-SEED key in provenance, or None."""
        sources = {k: v for k, v in self.provenance.items() if k != "SEED" and v > 0}
        if not sources:
            return None
        return max(sources, key=sources.get)

    @property
    def mature_profit_total(self) -> float:
        """Return the capital this bot holds over its maturity threshold.

        starting_balance is the cost basis and starting_balance plus
        total_profit is the current value, so the result is 0.0 until the
        capital has grown past MATURE_GROWTH_PCT and the amount over the
        threshold after that.
        """
        return mature_profit_usd(
            self.starting_balance, self.starting_balance + self.total_profit
        )

    @property
    def mature_profit_available(self) -> float:
        """Return mature_profit_total minus mature_profit_allocated.

        The Bot Swarm settings tab of each build draws it. Nothing in this
        build writes mature_profit_allocated, so the result equals
        mature_profit_total.
        """
        return self.mature_profit_total - self.mature_profit_allocated


class SmartWireManager:
    """The wire topology and the BotLedger set shared by every bot.

    register_wire and import_wires write the source-to-target map that
    get_outgoing_wires reads on each sale. attach_bot and detach_bot hold
    the bot references a sale routes income to.
    """

    def __init__(
        self,
        bus=None,
    ):
        # None makes each emit site call get_event_bus(); an injected bus
        # stays off the live bus.
        self._bus = bus
        self._ledgers: dict[str, BotLedger] = {}
        self._transactions: list[WireTransaction] = []
        # source_bot_id -> {target_bot_id: pct}, written by register_wire
        # and import_wires, read by get_outgoing_wires.
        self._wires: dict[str, dict[str, float]] = {}
        # Plain dict, not a weakref map; detach_bot drops the reference.
        self._bot_refs: dict[str, object] = {}

    def attach_bot(self, bot_id: str, bot_ref: object) -> None:
        """Store the bot reference a sale routes income to.

        BotManager calls this at bot creation, next to
        bot.set_smart_wire(self) and a separate register_bot.
        """
        self._bot_refs[bot_id] = bot_ref
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
        """Drop bot_id from _bot_refs and _ledgers and every wire naming it.

        The removed BotLedger's wired_in and wired_out totals are not kept.
        """
        self._bot_refs.pop(bot_id, None)
        self._ledgers.pop(bot_id, None)
        self._wires.pop(bot_id, None)
        for src in list(self._wires.keys()):
            self._wires[src].pop(bot_id, None)
            if not self._wires[src]:
                del self._wires[src]

    def register_wire(self, source_id: str, target_id: str, pct: float) -> dict:
        """Set the source_id to target_id percentage in _wires, overwriting
        any prior value.

        Returns a dict carrying "applied"; an accepted pair also carries
        "pct" and "replaced_pct", the prior percentage or None.
        """
        if source_id == target_id:
            return {"applied": False, "reason": "source and target must differ"}
        kind_refusal = pct_kind_refusal(pct)
        if kind_refusal:
            return {"applied": False, "reason": kind_refusal}
        # float() raises OverflowError, not only TypeError or ValueError,
        # on an int too large for a double.
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
        # nan makes p <= 0 and p > 100 both False; math.isnan rejects it.
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
        """Delete the source_id to target_id entry from _wires.

        Returns True when the entry existed.
        """
        if source_id in self._wires and target_id in self._wires[source_id]:
            del self._wires[source_id][target_id]
            if not self._wires[source_id]:
                del self._wires[source_id]
            logger.info("SmartWire: unregistered %s -> %s", source_id, target_id)
            return True
        return False

    def get_outgoing_wires(self, source_id: str) -> dict[str, float]:
        """Return a copy of the source_id entry in _wires, or an empty dict."""
        return dict(self._wires.get(source_id, {}))

    def export_wires(self) -> list[dict]:
        """Return _wires as a list of {source_id, target_id, pct} dicts.

        BotManager.save_all_state passes the result to save_state. A row whose
        percent no reading admits is dropped and logged rather than raising,
        because a raise here loses the whole topology from the save.
        """
        out: list[dict] = []
        for src, targets in self._wires.items():
            for tgt, pct in targets.items():
                admitted_pct = routable_pct(pct)
                if admitted_pct is None:
                    logger.warning(
                        "SmartWire: export DROPPED %s -> %s - stored pct "
                        "%r is not a number this reading admits. That "
                        "route is absent from the save and will not come "
                        "back on the next start",
                        src,
                        tgt,
                        pct,
                    )
                    continue
                out.append(
                    {
                        "source_id": str(src),
                        "target_id": str(tgt),
                        "pct": admitted_pct,
                    }
                )
        return out

    def export_ledgers(self) -> list[dict]:
        """Return each BotLedger as a dict for import_ledgers to read back.

        A row that raises is dropped and logged; its wired_in, wired_out
        and provenance are absent from the snapshot.
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
        """Apply an export_ledgers snapshot onto _ledgers, updating an
        existing BotLedger in place and creating a missing one.

        Returns the number of rows applied.
        """
        if not isinstance(ledgers, list):
            return 0
        n = 0
        offered = 0
        dropped = 0
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
                    # register_bot skips a bot that already has a ledger;
                    # this asset is never overwritten.
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
                if not lg.asset and row.get("asset"):
                    lg.asset = str(row["asset"])
                if not lg.starting_balance and row.get("starting_balance"):
                    lg.starting_balance = float(row["starting_balance"])
                n += 1
            except Exception as exc:
                # The overlay writes field by field, so the row is left
                # partially applied to an existing ledger.
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
        """Apply an export_wires snapshot onto _wires and return the count
        accepted.

        Re-importing the same snapshot overwrites the same keys and changes
        nothing.
        """
        if not isinstance(wires, list):
            return 0

        # Starts after the type guard, which returns without emitting a duration.
        _dur_t0 = time.monotonic()
        n = 0
        offered = 0
        # _wires has two writers, register_wire and this method, rejecting
        # the same range.
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
            kind_refusal = pct_kind_refusal(w.get("pct", 0))
            if kind_refusal:
                unreadable += 1
                logger.warning(
                    "SmartWire: import DROPPED wire row %d of %d, "
                    "%s -> %s - %s. No writer here produces that, so "
                    "the save is corrupt; fold profit from %s will "
                    "never reach %s this session, and no route is "
                    "created at the figure that kind converts to",
                    offered,
                    len(wires),
                    src,
                    tgt,
                    kind_refusal,
                    src,
                    tgt,
                )
                continue
            # float() raises OverflowError, not only TypeError or ValueError,
            # on an int too large for a double.
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
            # nan makes pct <= 0 and pct > 100 both False; math.isnan
            # rejects it.
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
        # Stops before the two log calls below; duration covers the row loop.
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

    def book_transfer(self, source_id: str, target_id: str, usd: float) -> bool:
        """Book one wire transfer onto the two ledgers it moves money between.

        ``usd`` is added to the source ledger's wired_out, to the target
        ledger's wired_in, and to the target ledger's provenance entry for
        ``source_id`` - the per-funder breakdown the Bot Swarm tab draws. The
        live transfer path books here, WireRoutingMixin.
        _route_scrum_proceeds_via_wires on a sale or a detonation, so one
        transfer cannot reach the totals without reaching the breakdown.

        A usd no reading admits as an amount books nothing and answers False. A
        funder entry already unreadable keeps the entry it has, because adding
        to it would turn a figure the tab draws as an em dash into one it draws
        as money. A ledger this manager does not hold is skipped, and no failure
        raises into the caller.
        """
        try:
            amount = float(usd)
        except (TypeError, ValueError):
            amount = math.nan
        if not math.isfinite(amount):
            logger.warning(
                "SmartWire: transfer %s -> %s carries %r, which no reading "
                "admits as an amount. Neither ledger moves, so the totals and "
                "the provenance breakdown already stored stay readable",
                source_id,
                target_id,
                usd,
            )
            return False
        funder = str(source_id)
        target_ledger = self._ledgers.get(str(target_id))
        if target_ledger is not None:
            target_ledger.wired_in += amount
            try:
                held = float(target_ledger.provenance.get(funder, 0.0))
            except (TypeError, ValueError):
                held = math.nan
            if math.isfinite(held):
                target_ledger.provenance[funder] = held + amount
            else:
                logger.warning(
                    "SmartWire: %s holds %r for funder %s, which no reading "
                    "admits, so the $%.4f this transfer adds has nothing to "
                    "add to. The breakdown entry stays as it is and the Bot "
                    "Swarm tab keeps drawing an em dash for it",
                    target_id,
                    target_ledger.provenance.get(funder),
                    funder,
                    amount,
                )
        source_ledger = self._ledgers.get(funder)
        if source_ledger is not None:
            source_ledger.wired_out += amount
        return True

    def register_bot(
        self,
        bot_id: str,
        asset: str,
        seed_amount: float = 200.0,
        funder_bot_id: Optional[str] = None,
    ) -> None:
        """Create the BotLedger for bot_id with seed_amount as its
        starting_balance.

        funder_bot_id names the provenance key; "SEED" is used when it is
        None, and the funder's own ledger is untouched.
        """
        if funder_bot_id is None:
            provenance = {"SEED": seed_amount}
        else:
            provenance = {funder_bot_id: seed_amount}

        self._ledgers[bot_id] = BotLedger(
            bot_id=bot_id,
            asset=asset,
            provenance=provenance,
            starting_balance=seed_amount,  # the cost basis mature_profit_total reads
        )
        source_label = funder_bot_id or "SEED"
        logger.info(
            "SmartWire: registered %s (%s) with $%.2f from %s",
            bot_id,
            asset,
            seed_amount,
            source_label,
        )

    def record_profit(self, bot_id: str, amount: float) -> None:
        """Add amount to bot_id's total_profit and available_profit.

        An id absent from _ledgers is ignored.
        """
        if bot_id in self._ledgers:
            self._ledgers[bot_id].total_profit += amount
            self._ledgers[bot_id].available_profit += amount

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
