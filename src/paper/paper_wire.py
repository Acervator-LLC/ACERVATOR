"""Smart wire profit routing between paper bots, forked over
``src/simulator/sim_wire.py``.

``PaperWireManager`` holds the wire topology and one ``PaperWireLedger`` per
paper bot. ``distribute_fold_profit`` moves each wire's share of a bot's
realised fold growth into the target's standing fold tranches through
``apply_wire_income``, and onto the target ledger's ``parked_usd`` when no
``FakeBalance`` is attached for it, and ``land_parked_credits`` spreads a parked
pool once the target's own scrum builds a tranche. ``compute_safe_outflow_pct``
caps a share only when the attached source answers ``get_swos_inputs``, which a
``FakeBalance`` does not.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..trading.smart_wire import compute_safe_outflow_pct, mature_profit_usd

logger = logging.getLogger("acervator.paper.wire")

#: The share below which a transfer is skipped, ``SmartWireManager``'s default.
MIN_WIRE_USD: float = 0.01

#: ``WireTransaction.wire_type`` for a fold route, the name Live books it under.
FOLD_WIRE_TYPE = "WIRE_BACK"

#: The provenance key ``register_bot`` writes for capital no wire supplied.
SEED_SOURCE = "SEED"

#: What ``_safe_outflow_pct`` answers with no ``get_swos_inputs``.
UNCAPPED_OUTFLOW_PCT: float = 100.0


@dataclass
class PaperWireTransaction:
    """One transfer ``PaperWireManager`` booked, typed by ``wire_type``."""

    timestamp: int
    source_bot: str
    target_bot: str
    amount: float
    wire_type: str
    reason: str = ""


@dataclass
class PaperWireLedger:
    """Profit provenance, wire totals and parked credits for one paper bot.

    ``provenance`` maps each funder id to the amount it supplied, with
    ``SEED_SOURCE`` for the seed capital, and ``parked_usd`` holds what
    ``land_parked_credits`` has yet to spread into fold tranches.
    """

    bot_id: str
    asset: str
    total_profit: float = 0.0
    available_profit: float = 0.0
    wired_in: float = 0.0
    wired_out: float = 0.0
    provenance: dict = field(default_factory=dict)
    starting_balance: float = 0.0
    mature_profit_allocated: float = 0.0
    parked_usd: float = 0.0
    parked_credits: list = field(default_factory=list)

    @property
    def predominant_source(self) -> Optional[str]:
        """The largest funder id in ``provenance`` other than ``SEED_SOURCE``."""
        sources = {
            key: value
            for key, value in self.provenance.items()
            if key != SEED_SOURCE and value > 0
        }
        if not sources:
            return None
        return max(sources, key=sources.get)

    @property
    def mature_profit_total(self) -> float:
        """``starting_balance`` read against ``starting_balance`` plus
        ``total_profit`` through ``mature_profit_usd``."""
        return mature_profit_usd(
            self.starting_balance, self.starting_balance + self.total_profit
        )

    @property
    def mature_profit_available(self) -> float:
        """``mature_profit_total`` less ``mature_profit_allocated``."""
        return self.mature_profit_total - self.mature_profit_allocated


def spread_over_fold_queue(balance: Any, usd: float, credits: list) -> float:
    """Add ``usd`` evenly to every standing tranche of ``balance`` and answer
    the per-tranche share.

    Each tranche's ``usd`` grows by ``usd`` over the tranche count and gains one
    ``wire_credits`` entry per element of ``credits``, each entry's own ``usd``
    divided by the same count.
    """
    tranches = getattr(balance, "fold_tranches", None) or []
    if not tranches:
        return 0.0
    count = len(tranches)
    share = float(usd) / count
    for tranche in tranches:
        tranche["usd"] = float(tranche.get("usd", 0) or 0) + share
        if credits:
            tranche.setdefault("wire_credits", []).extend(
                {
                    "ts": one.get("ts"),
                    "source": one.get("source", "?"),
                    "usd": float(one.get("usd", 0.0) or 0.0) / count,
                    "ref": one.get("ref", ""),
                }
                for one in credits
            )
    return share


def apply_wire_income(balance: Any, usd: float, source: str, ref: str = "") -> dict:
    """Spread ``usd`` over ``balance``'s standing fold tranches and answer
    whether it was applied.

    A balance holding no tranche answers ``applied`` False, which
    ``PaperWireManager.distribute_fold_profit`` reads as the parked case.
    """
    try:
        amount = float(usd)
    except (TypeError, ValueError):
        return {"applied": False, "reason": f"usd must be numeric; got {usd!r}"}
    if not math.isfinite(amount) or amount <= 0:
        return {"applied": False, "reason": f"usd must be > 0; got {amount}"}
    credit = {
        "ts": time.time(),
        "source": str(source or "?"),
        "usd": amount,
        "ref": str(ref or ""),
    }
    tranches = getattr(balance, "fold_tranches", None) or []
    if not tranches:
        return {"applied": False, "reason": "no standing fold tranche"}
    share = spread_over_fold_queue(balance, amount, [credit])
    logger.info(
        "paper wire income %.4f from %s spread over %d tranche(s)",
        amount,
        credit["source"],
        len(tranches),
    )
    return {
        "applied": True,
        "placement": "tranche",
        "tranches_credited": len(tranches),
        "per_tranche_usd": share,
    }


class PaperWireManager:
    """The paper fleet's wire topology and its ``PaperWireLedger`` set.

    ``register_wire`` and ``import_wires`` write the source-to-target map
    ``distribute_fold_profit`` reads on each fold, and ``attach_bot`` holds the
    ``FakeBalance`` of an open paper bot that a share can reach.
    """

    def __init__(self, min_wire_amount: float = MIN_WIRE_USD) -> None:
        self._min_wire = float(min_wire_amount)
        self._ledgers: dict[str, PaperWireLedger] = {}
        self._transactions: list[PaperWireTransaction] = []
        self._wires: dict[str, dict[str, float]] = {}
        self._bot_refs: dict[str, Any] = {}

    def attach_bot(self, bot_id: str, bot_ref: Any) -> None:
        """Hold the ``FakeBalance`` of ``bot_id`` that a share can reach."""
        self._bot_refs[str(bot_id)] = bot_ref

    def release_bot(self, bot_id: str) -> bool:
        """Drop the held balance of ``bot_id`` and keep its ledger and wires;
        answers whether one was held."""
        return self._bot_refs.pop(str(bot_id), None) is not None

    def detach_bot(self, bot_id: str) -> None:
        """Drop ``bot_id`` from ``_bot_refs`` and ``_ledgers`` and every wire
        naming it, as ``SmartWireManager.detach_bot`` drops a live bot."""
        wanted = str(bot_id)
        self._bot_refs.pop(wanted, None)
        self._ledgers.pop(wanted, None)
        self._wires.pop(wanted, None)
        for source in list(self._wires.keys()):
            self._wires[source].pop(wanted, None)
            if not self._wires[source]:
                del self._wires[source]

    def register_bot(
        self,
        bot_id: str,
        asset: str,
        seed_amount: float = 200.0,
        funder_bot_id: Optional[str] = None,
    ) -> PaperWireLedger:
        """Create the ``PaperWireLedger`` of ``bot_id`` with ``seed_amount`` as
        its ``starting_balance`` and answer it.

        ``funder_bot_id`` names the ``provenance`` key and ``SEED_SOURCE`` is
        used when it is None, leaving the funder's own ledger untouched.
        """
        wanted = str(bot_id)
        funder = SEED_SOURCE if funder_bot_id is None else str(funder_bot_id)
        ledger = PaperWireLedger(
            bot_id=wanted,
            asset=str(asset or ""),
            provenance={funder: float(seed_amount)},
            starting_balance=float(seed_amount),
        )
        self._ledgers[wanted] = ledger
        logger.info(
            "paper wire: registered %s (%s) with $%.2f from %s",
            wanted,
            asset,
            float(seed_amount),
            funder,
        )
        return ledger

    def register_wire(self, source_id: str, target_id: str, pct: float) -> dict:
        """Set the ``source_id`` to ``target_id`` percentage in ``_wires``,
        overwriting any prior value, and answer a dict carrying ``applied``.

        An accepted pair also carries ``pct`` and ``replaced_pct``, the prior
        percentage or None, and the accepted range is ``0 < pct <= 100``.
        """
        if str(source_id) == str(target_id):
            return {"applied": False, "reason": "source and target must differ"}
        try:
            wanted_pct = float(pct)
        except Exception as exc:  # noqa: BLE001 - float() also raises OverflowError
            return {
                "applied": False,
                "reason": (
                    f"pct could not be read as a number: "
                    f"{pct!r} ({type(exc).__name__}: {exc})"
                ),
            }
        if math.isnan(wanted_pct):
            return {
                "applied": False,
                "reason": "pct must be a real number; got nan, which is unordered",
            }
        if wanted_pct <= 0 or wanted_pct > 100:
            return {
                "applied": False,
                "reason": f"pct must be in (0, 100]; got {wanted_pct}",
            }
        prior = self._wires.get(str(source_id), {}).get(str(target_id))
        self._wires.setdefault(str(source_id), {})[str(target_id)] = wanted_pct
        if prior is None:
            logger.info(
                "paper wire: registered %s -> %s @ %.2f%%",
                source_id,
                target_id,
                wanted_pct,
            )
        else:
            logger.warning(
                "paper wire: OVERWROTE %s -> %s: %.2f%% replaced by %.2f%%",
                source_id,
                target_id,
                float(prior),
                wanted_pct,
            )
        return {
            "applied": True,
            "source_id": str(source_id),
            "target_id": str(target_id),
            "pct": wanted_pct,
            "replaced_pct": (None if prior is None else float(prior)),
        }

    def unregister_wire(self, source_id: str, target_id: str) -> bool:
        """Delete the ``source_id`` to ``target_id`` entry from ``_wires``;
        answers whether one existed."""
        source = str(source_id)
        target = str(target_id)
        if source in self._wires and target in self._wires[source]:
            del self._wires[source][target]
            if not self._wires[source]:
                del self._wires[source]
            logger.info("paper wire: unregistered %s -> %s", source, target)
            return True
        return False

    def get_outgoing_wires(self, source_id: str) -> dict[str, float]:
        """A copy of the ``source_id`` entry in ``_wires``, or an empty dict."""
        return dict(self._wires.get(str(source_id), {}))

    def get_ledger(self, bot_id: str) -> Optional[PaperWireLedger]:
        """The ``PaperWireLedger`` of ``bot_id``, or None."""
        return self._ledgers.get(str(bot_id))

    def record_profit(self, bot_id: str, amount: float) -> None:
        """Add ``amount`` to ``bot_id``'s ``total_profit`` and
        ``available_profit``; an id with no ledger is ignored."""
        ledger = self._ledgers.get(str(bot_id))
        if ledger is not None:
            ledger.total_profit += float(amount)
            ledger.available_profit += float(amount)

    def export_wires(self) -> list[dict]:
        """``_wires`` as a list of ``source_id``, ``target_id`` and ``pct``
        dicts, the rows ``import_wires`` reads back."""
        rows: list[dict] = []
        for source, targets in self._wires.items():
            for target, pct in targets.items():
                rows.append(
                    {
                        "source_id": str(source),
                        "target_id": str(target),
                        "pct": float(pct),
                    }
                )
        return rows

    def export_ledgers(self) -> list[dict]:
        """Each ``PaperWireLedger`` as a dict for ``import_ledgers`` to read
        back; a row that raises is dropped and logged."""
        rows: list[dict] = []
        dropped = 0
        for bot_id, ledger in self._ledgers.items():
            try:
                rows.append(
                    {
                        "bot_id": str(bot_id),
                        "asset": str(ledger.asset or ""),
                        "total_profit": float(ledger.total_profit or 0.0),
                        "available_profit": float(ledger.available_profit or 0.0),
                        "wired_in": float(ledger.wired_in or 0.0),
                        "wired_out": float(ledger.wired_out or 0.0),
                        "provenance": dict(ledger.provenance or {}),
                        "starting_balance": float(ledger.starting_balance or 0.0),
                        "mature_profit_allocated": float(
                            ledger.mature_profit_allocated or 0.0
                        ),
                        "parked_usd": float(ledger.parked_usd or 0.0),
                        "parked_credits": [
                            dict(one) for one in (ledger.parked_credits or [])
                        ],
                    }
                )
            except (AttributeError, TypeError, ValueError) as exc:
                dropped += 1
                logger.warning(
                    "paper wire: export DROPPED ledger row for %s (%s: %s); its "
                    "wired_in, wired_out and parked credits are NOT in this save",
                    bot_id,
                    type(exc).__name__,
                    exc,
                )
        if dropped:
            logger.warning(
                "paper wire: exported %d of %d ledger row(s); %d dropped",
                len(rows),
                len(self._ledgers),
                dropped,
            )
        return rows

    def import_wires(self, wires: Any) -> int:
        """Apply an ``export_wires`` snapshot onto ``_wires`` and answer the
        count accepted.

        A row that is not a dict, names no endpoint or carries a ``pct``
        outside ``0 < pct <= 100`` is dropped and logged.
        """
        if not isinstance(wires, list):
            return 0
        accepted = 0
        lost = 0
        for offered, row in enumerate(wires, start=1):
            if not isinstance(row, dict):
                lost += 1
                logger.warning(
                    "paper wire: import DROPPED wire row %d of %d - it is a %s, "
                    "not a row; that transfer route does not exist this session",
                    offered,
                    len(wires),
                    type(row).__name__,
                )
                continue
            source = row.get("source_id")
            target = row.get("target_id")
            try:
                pct = float(row.get("pct", 0))
            except Exception as exc:  # noqa: BLE001 - float() also raises OverflowError
                lost += 1
                logger.warning(
                    "paper wire: import DROPPED wire row %d of %d, %s -> %s - "
                    "float() refused pct %r (%s: %s); fold growth from %s never "
                    "reaches %s this session",
                    offered,
                    len(wires),
                    source,
                    target,
                    row.get("pct"),
                    type(exc).__name__,
                    exc,
                    source,
                    target,
                )
                continue
            if not source or not target or math.isnan(pct) or pct <= 0 or pct > 100:
                lost += 1
                logger.warning(
                    "paper wire: import DROPPED wire row %d of %d, %s -> %s @ %r - "
                    "no endpoint, or a pct outside 0 < pct <= 100; that transfer "
                    "route does not exist this session and the growth it carried "
                    "stays with the source bot",
                    offered,
                    len(wires),
                    source,
                    target,
                    pct,
                )
                continue
            self._wires.setdefault(str(source), {})[str(target)] = pct
            accepted += 1
        if accepted:
            logger.info(
                "paper wire: imported %d wire(s) from the paper fleet", accepted
            )
        if lost:
            logger.warning(
                "paper wire: import accepted %d of %d wire row(s) offered; %d lost",
                accepted,
                len(wires),
                lost,
            )
        return accepted

    def import_ledgers(self, ledgers: Any) -> int:
        """Apply an ``export_ledgers`` snapshot onto ``_ledgers``, updating an
        existing ``PaperWireLedger`` in place and creating a missing one, and
        answer the count applied.

        A row that is not a dict or carries no ``bot_id`` is dropped and
        logged.
        """
        if not isinstance(ledgers, list):
            return 0
        accepted = 0
        lost = 0
        for offered, row in enumerate(ledgers, start=1):
            if not isinstance(row, dict) or not row.get("bot_id"):
                lost += 1
                logger.warning(
                    "paper wire: import DROPPED ledger row %d of %d - it is a %s "
                    "with bot_id %r, so it cannot be applied to any bot; one "
                    "bot's wired_in, wired_out and parked credits are not in "
                    "this session",
                    offered,
                    len(ledgers),
                    type(row).__name__,
                    row.get("bot_id") if isinstance(row, dict) else None,
                )
                continue
            bot_id = str(row["bot_id"])
            try:
                ledger = self._ledgers.get(bot_id)
                if ledger is None:
                    ledger = PaperWireLedger(
                        bot_id=bot_id,
                        asset=str(row.get("asset", "") or ""),
                        starting_balance=float(row.get("starting_balance", 0.0) or 0.0),
                    )
                    self._ledgers[bot_id] = ledger
                ledger.total_profit = float(row.get("total_profit", 0.0) or 0.0)
                ledger.available_profit = float(row.get("available_profit", 0.0) or 0.0)
                ledger.wired_in = float(row.get("wired_in", 0.0) or 0.0)
                ledger.wired_out = float(row.get("wired_out", 0.0) or 0.0)
                ledger.mature_profit_allocated = float(
                    row.get("mature_profit_allocated", 0.0) or 0.0
                )
                ledger.parked_usd = float(row.get("parked_usd", 0.0) or 0.0)
                stored_provenance = row.get("provenance")
                if isinstance(stored_provenance, dict):
                    ledger.provenance = {
                        str(key): float(value or 0.0)
                        for key, value in stored_provenance.items()
                    }
                stored_credits = row.get("parked_credits")
                if isinstance(stored_credits, list):
                    ledger.parked_credits = [
                        dict(one) for one in stored_credits if isinstance(one, dict)
                    ]
                if not ledger.asset and row.get("asset"):
                    ledger.asset = str(row["asset"])
                if not ledger.starting_balance and row.get("starting_balance"):
                    ledger.starting_balance = float(row["starting_balance"])
                accepted += 1
            except (AttributeError, TypeError, ValueError) as exc:
                lost += 1
                logger.warning(
                    "paper wire: import DROPPED ledger row for %s (%s: %s) - the "
                    "row is PARTIALLY applied and that bot's wire totals are "
                    "wrong for this session",
                    bot_id,
                    type(exc).__name__,
                    exc,
                )
        if accepted:
            logger.info(
                "paper wire: imported %d ledger(s) from the paper fleet", accepted
            )
        if lost:
            logger.warning(
                "paper wire: import accepted %d of %d ledger row(s) offered; %d lost",
                accepted,
                len(ledgers),
                lost,
            )
        return accepted

    def land_parked_credits(self, bot_id: str, balance: Any) -> float:
        """Spread ``bot_id``'s parked pool over ``balance``'s standing fold
        tranches and answer what landed.

        Answers 0.0 while ``parked_usd`` is empty or the balance holds no
        tranche.
        """
        ledger = self._ledgers.get(str(bot_id))
        if ledger is None or ledger.parked_usd <= 0.0:
            return 0.0
        tranches = getattr(balance, "fold_tranches", None) or []
        if not tranches:
            return 0.0
        landed = float(ledger.parked_usd)
        share = spread_over_fold_queue(balance, landed, list(ledger.parked_credits))
        ledger.parked_usd = 0.0
        ledger.parked_credits = []
        logger.info(
            "paper wire: landed $%.4f of parked credit on %s over %d tranche(s) "
            "($%.4f each)",
            landed,
            bot_id,
            len(tranches),
            share,
        )
        return landed

    def _park_credit(
        self, target_id: str, usd: float, source_id: str, ref: str
    ) -> dict:
        """Hold ``usd`` on ``target_id``'s ``parked_usd`` until
        ``land_parked_credits`` spreads it, and answer the result row
        ``distribute_fold_profit`` reports."""
        ledger = self._ledgers.get(str(target_id))
        if ledger is None:
            return {"applied": False, "reason": "target bot has no ledger"}
        ledger.parked_usd += float(usd)
        ledger.parked_credits.append(
            {
                "ts": time.time(),
                "source": str(source_id),
                "usd": float(usd),
                "ref": str(ref or ""),
            }
        )
        logger.info(
            "paper wire: parked $%.4f from %s on %s; its next scrum lands it on "
            "the tranche that scrum builds",
            float(usd),
            source_id,
            target_id,
        )
        return {
            "applied": True,
            "placement": "parked",
            "parked_total": ledger.parked_usd,
        }

    def _safe_outflow_pct(self, source_id: str, profit_usd: float) -> float:
        """``compute_safe_outflow_pct`` over the attached source's
        ``get_swos_inputs``, or ``UNCAPPED_OUTFLOW_PCT`` when it answers none."""
        source_ref = self._bot_refs.get(str(source_id))
        getter = getattr(source_ref, "get_swos_inputs", None)
        if getter is None:
            return UNCAPPED_OUTFLOW_PCT
        try:
            inputs = getter()
        except Exception as exc:  # noqa: BLE001 - the cap is advisory on Live too
            logger.debug(
                "paper wire: %s get_swos_inputs raised %s; no safety cap this fire",
                source_id,
                exc,
            )
            return UNCAPPED_OUTFLOW_PCT
        if not inputs:
            return UNCAPPED_OUTFLOW_PCT
        return compute_safe_outflow_pct(scrum_profit_usd=float(profit_usd), **inputs)

    def distribute_fold_profit(
        self, source_id: str, profit_usd: float, ref: str = ""
    ) -> list[dict]:
        """Route each wire's share of ``source_id``'s realised fold growth to
        the target and answer one result row per wire.

        A share is capped by ``_safe_outflow_pct`` divided across the outbound
        wires, skipped under ``_min_wire``, and booked by ``_book`` onto both
        ledgers with one ``PaperWireTransaction``; no failure raises.
        """
        results: list[dict] = []
        try:
            profit = float(profit_usd)
        except (TypeError, ValueError):
            return results
        if not math.isfinite(profit) or profit <= 0:
            return results
        outgoing = self._wires.get(str(source_id))
        if not outgoing:
            return results
        safe_pct = self._safe_outflow_pct(source_id, profit)
        per_wire_safe_pct = safe_pct / max(1, len(outgoing))
        for target_id, raw_pct in outgoing.items():
            pct = min(float(raw_pct), per_wire_safe_pct)
            share = profit * pct / 100.0
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
                continue
            target = self._bot_refs.get(str(target_id))
            landed: dict = {"applied": False, "reason": "target bot not attached"}
            if target is not None:
                landed = apply_wire_income(target, share, source=source_id, ref=ref)
            if not landed.get("applied"):
                landed = self._park_credit(target_id, share, source_id, ref)
            if not landed.get("applied"):
                results.append(
                    {
                        "target_id": target_id,
                        "pct": pct,
                        "share": share,
                        "applied": False,
                        "reason": landed.get("reason", "target refused the share"),
                    }
                )
                continue
            self._book(source_id, target_id, share, pct, ref)
            results.append(
                {
                    "target_id": target_id,
                    "pct": pct,
                    "share": share,
                    "applied": True,
                    "placement": landed.get("placement", ""),
                    "result": landed,
                }
            )
        return results

    def _book(
        self, source_id: str, target_id: str, share: float, pct: float, ref: str
    ) -> None:
        """Move ``share`` onto the source ledger's ``wired_out`` and the target
        ledger's ``wired_in`` and append one ``PaperWireTransaction``."""
        source_ledger = self._ledgers.get(str(source_id))
        if source_ledger is not None:
            source_ledger.wired_out += float(share)
        target_ledger = self._ledgers.get(str(target_id))
        if target_ledger is not None:
            target_ledger.wired_in += float(share)
            held = float(target_ledger.provenance.get(str(source_id), 0.0))
            target_ledger.provenance[str(source_id)] = held + float(share)
        self._transactions.append(
            PaperWireTransaction(
                timestamp=int(time.time()),
                source_bot=str(source_id),
                target_bot=str(target_id),
                amount=float(share),
                wire_type=FOLD_WIRE_TYPE,
                reason=f"fold_growth pct={pct} ref={ref}",
            )
        )

    @property
    def stats(self) -> dict:
        """The bot count, the transaction count, the total wired, the total
        profit and the total parked across every ``PaperWireLedger``."""
        return {
            "bots": len(self._ledgers),
            "transactions": len(self._transactions),
            "total_wired": sum(one.amount for one in self._transactions),
            "total_profit": sum(one.total_profit for one in self._ledgers.values()),
            "total_parked": sum(one.parked_usd for one in self._ledgers.values()),
        }


__all__ = [
    "FOLD_WIRE_TYPE",
    "MIN_WIRE_USD",
    "SEED_SOURCE",
    "UNCAPPED_OUTFLOW_PCT",
    "PaperWireLedger",
    "PaperWireManager",
    "PaperWireTransaction",
    "apply_wire_income",
    "spread_over_fold_queue",
]
