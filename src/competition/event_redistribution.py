"""Divides an Elite Event's pot on a normalised performance score.

``performance_score`` reads one ``TradeGrade`` through ``grade_metrics`` and
``divide_pot`` normalises the scores handed to it, so no share can read a
participant's spend. ``record_certified_fill`` joins one
``CertificationReceipt`` to the record of the participant ``certified_participant``
names off the chain. ``EventRedistribution.settle`` moves every share through
``QuintessenceLedger.payout`` in one commit and the remainder stays at the pot's
held address as the reserve.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from .capture_bounds import GRADE_NOT_COMPUTED, MIN_SCORED_AXES
from .quintessence_ledger import amount_text
from .rpg_metrics import grade_metrics

if TYPE_CHECKING:
    from .action_spend import ActionRecord, PoaRecordStore
    from .local_testnet import LocalTestnet
    from .quintessence_ledger import QuintessenceLedger

logger = logging.getLogger("acervator.event_redistribution")

#: The share of a pot that returns to participants; what is left is the reserve.
RETURN_PERCENT = 75

#: One Quintessence in the indivisible units ``contracts/Quintessence.sol`` counts.
BASE_UNITS_PER_QUINTESSENCE = 10**18

SCORED = "scored"
NO_SCORE = "no_score"

_NUMBER_TYPES = (int, float, Decimal)


class RedistributionError(RuntimeError):
    """Base for every refusal this module raises."""


def _as_quantity(value: object, name: str) -> Decimal:
    """Return ``value`` as a non-negative finite Decimal; bool, str and NaN raise."""
    if type(value) is bool or type(value) not in _NUMBER_TYPES:
        raise RedistributionError(
            f"{name} must be int, float or Decimal, not {type(value).__name__}"
        )
    quantity = value if isinstance(value, Decimal) else Decimal(str(value))
    if not quantity.is_finite():
        raise RedistributionError(f"{name} must be finite, got {value!r}")
    if quantity < 0:
        raise RedistributionError(f"{name} must not be negative, got {value!r}")
    return quantity


def _as_name(value: object, name: str) -> str:
    """Return ``value`` as a stripped non-empty string; every other value raises."""
    if type(value) is not str or not value.strip():
        raise RedistributionError(f"{name} must be a non-empty string, got {value!r}")
    return value.strip()


def to_base_units(amount: object, name: str = "amount") -> int:
    """Return ``amount`` as whole indivisible units, dropping anything below one."""
    quantity = _as_quantity(amount, name)
    scaled = quantity * BASE_UNITS_PER_QUINTESSENCE
    return int(scaled.to_integral_value(rounding="ROUND_DOWN"))


def from_base_units(units: int) -> Decimal:
    """Return ``units`` indivisible units as a Decimal amount, with no rounding."""
    if type(units) is not int:
        raise RedistributionError(
            f"units must be a whole number, not {type(units).__name__}"
        )
    return Decimal(units).scaleb(-len(str(BASE_UNITS_PER_QUINTESSENCE)) + 1)


@dataclass(frozen=True)
class PerformanceScore:
    """One participant's graded performance, and how many axes carried it.

    ``is_scoreable`` is false below ``MIN_SCORED_AXES``, the bound
    ``capture_bounds`` sets on a grade that is a default and not a measurement.
    """

    address: str
    score: Decimal
    scored_axes: int

    @property
    def is_scoreable(self) -> bool:
        """Whether ``scored_axes`` reaches ``MIN_SCORED_AXES``."""
        return self.scored_axes >= MIN_SCORED_AXES

    @property
    def standing(self) -> str:
        """``SCORED`` while ``is_scoreable``, and ``NO_SCORE`` otherwise."""
        return SCORED if self.is_scoreable else NO_SCORE

    def to_dict(self) -> dict:
        """Return this score as a JSON-safe dict with ``score`` as a string."""
        return {
            "address": self.address,
            "score": amount_text(self.score),
            "scored_axes": self.scored_axes,
            "standing": self.standing,
        }


@dataclass(frozen=True)
class PayoutShare:
    """What one participant's normalised score took out of the return pool."""

    address: str
    score: Decimal
    normalised_share: Decimal
    amount: Decimal

    def to_dict(self) -> dict:
        """Return this share as a JSON-safe dict with every Decimal as a string."""
        return {
            "address": self.address,
            "score": amount_text(self.score),
            "normalised_share": amount_text(self.normalised_share),
            "amount": amount_text(self.amount),
        }


@dataclass(frozen=True)
class PotDivision:
    """One event's pot, the shares it divides into, and the reserve left over.

    ``reserve`` is ``held_back`` plus ``division_remainder`` and ``is_exact`` is
    whether ``pot`` equals ``paid_total`` plus ``reserve``.
    """

    event_id: str
    pot: Decimal
    return_pool: Decimal
    shares: tuple[PayoutShare, ...]
    unscored: tuple[str, ...]
    paid_total: Decimal
    held_back: Decimal
    division_remainder: Decimal
    reserve: Decimal
    is_exact: bool

    def to_dict(self) -> dict:
        """Return this division as a JSON-safe dict with every Decimal as a string."""
        return {
            "event_id": self.event_id,
            "pot": amount_text(self.pot),
            "return_percent": RETURN_PERCENT,
            "return_pool": amount_text(self.return_pool),
            "shares": [share.to_dict() for share in self.shares],
            "unscored": list(self.unscored),
            "paid_total": amount_text(self.paid_total),
            "held_back": amount_text(self.held_back),
            "division_remainder": amount_text(self.division_remainder),
            "reserve": amount_text(self.reserve),
            "is_exact": self.is_exact,
        }


def performance_score(address: str, grade: object) -> PerformanceScore:
    """Return ``address``'s score, off one ``TradeGrade`` through ``grade_metrics``.

    ``grade_metrics`` supplies ``grade_numeric`` and the grade supplies
    ``scored_axes``, so nothing here computes a score of its own.
    """
    wallet = _as_name(address, "address")
    metrics = grade_metrics(grade)
    numeric = metrics.get("grade_numeric")
    axes = grade.get("scored_axes") if isinstance(grade, dict) else None
    if axes is None:
        axes = getattr(grade, "scored_axes", None)
    if numeric is None or type(axes) is not int:
        return PerformanceScore(wallet, Decimal(0), 0)
    return PerformanceScore(wallet, _as_quantity(numeric, "grade_numeric"), axes)


def certified_participant(receipt: object, testnet: LocalTestnet | None) -> str:
    """Return the address that sent ``receipt``'s certification to ``testnet``.

    The chain records that address as the transaction's sender, so it is the one
    spelling of a participant's wallet; a receipt naming no bot, and one whose
    transaction the chain does not hold, both raise.
    """
    bot = _as_name(getattr(receipt, "bot_id", None), "bot_id")
    if testnet is None:
        no_chain = (
            f"bot {bot[:12]} certified with no chain to read the sender from, so "
            f"the fill names no participant"
        )
        raise RedistributionError(no_chain)
    tx_hash = _as_name(getattr(receipt, "tx_hash", None), "tx_hash")
    transaction = testnet.chain.get_tx(tx_hash)
    if transaction is None:
        not_on_chain = (
            f"transaction {tx_hash[:16]} is not on this chain, so the fill names "
            f"no participant"
        )
        raise RedistributionError(not_on_chain)
    return _as_name(transaction.from_addr, "from_addr")


def scores_from_records(records: list) -> list[PerformanceScore]:
    """Return one ``PerformanceScore`` an ``ActionRecord``, reading no spend field.

    This is the only place a record reaches a division, and it carries
    ``grade_numeric`` and ``scored_axes`` alone.
    """
    return [
        PerformanceScore(
            address=_as_name(record.address, "address"),
            score=_as_quantity(record.grade_numeric, "grade_numeric"),
            scored_axes=int(record.scored_axes),
        )
        for record in records
    ]


def divide_pot(event_id: str, pot: object, scores: list) -> PotDivision:
    """Divide ``pot`` across ``scores`` in proportion to each normalised score.

    A score below ``MIN_SCORED_AXES`` takes nothing and every indivisible unit
    ``divide_pot`` cannot place rests in ``reserve``.
    """
    event = _as_name(event_id, "event_id")
    pot_units = to_base_units(pot, "pot")
    return_pool_units = pot_units * RETURN_PERCENT // 100
    scoreable = sorted(
        (score for score in scores if score.is_scoreable),
        key=lambda score: score.address,
    )
    unscored = tuple(
        sorted(score.address for score in scores if not score.is_scoreable)
    )
    score_units = {
        score.address: to_base_units(score.score, "score") for score in scoreable
    }
    total_score_units = sum(score_units.values())
    shares: list[PayoutShare] = []
    for score in scoreable:
        if total_score_units == 0:
            continue
        own = score_units[score.address]
        amount_units = return_pool_units * own // total_score_units
        normalised_units = own * BASE_UNITS_PER_QUINTESSENCE // total_score_units
        shares.append(
            PayoutShare(
                address=score.address,
                score=score.score,
                normalised_share=from_base_units(normalised_units),
                amount=from_base_units(amount_units),
            )
        )
    paid_units = sum(to_base_units(share.amount, "amount") for share in shares)
    held_back_units = pot_units - return_pool_units
    remainder_units = return_pool_units - paid_units
    reserve_units = held_back_units + remainder_units
    return PotDivision(
        event_id=event,
        pot=from_base_units(pot_units),
        return_pool=from_base_units(return_pool_units),
        shares=tuple(shares),
        unscored=unscored,
        paid_total=from_base_units(paid_units),
        held_back=from_base_units(held_back_units),
        division_remainder=from_base_units(remainder_units),
        reserve=from_base_units(reserve_units),
        is_exact=pot_units == paid_units + reserve_units,
    )


class EventRedistribution:
    """Divides one event's pot on performance and pays the shares out of the ledger.

    The ledger, the store, the held address and the chain ``record_certified_fill``
    reads a sender off all arrive by construction, so a demo run is one
    ``EventRedistribution`` over another chain taking the same ``settle`` path.
    """

    def __init__(
        self,
        ledger: QuintessenceLedger,
        store: PoaRecordStore,
        held_address: str,
        testnet: LocalTestnet | None = None,
    ) -> None:
        """Hold the ledger, the store, the pot's held address and the chain."""
        self._ledger = ledger
        self._store = store
        self._held_address = _as_name(held_address, "held_address")
        self._testnet = testnet
        self._settled: dict[str, PotDivision] = {}
        self._lock = threading.RLock()

    @property
    def held_address(self) -> str:
        """Return the held address the pot this object divides rests at."""
        return self._held_address

    @property
    def store(self) -> PoaRecordStore:
        """Return the ``PoaRecordStore`` the scores and the pot are read from."""
        return self._store

    def write_grade(self, event_id: str, address: str, grade: object) -> ActionRecord:
        """Put ``address``'s graded trade on its ``ActionRecord`` for ``event_id``."""
        score = performance_score(address, grade)
        return self._store.write_grade(
            event_id, score.address, score.score, score.scored_axes
        )

    def record_certified_fill(
        self, event_id: str, receipt: object, fill: object
    ) -> ActionRecord:
        """Add one certified fill's grade to its participant's record in ``event_id``.

        The participant is the sender of ``receipt``'s certification transaction and
        the grade is the fill's own ``trade_grade`` and ``scored_axes``, so nothing
        here reads a spend. A fill naming no participant raises.
        """
        address = certified_participant(receipt, self._testnet)
        return self._store.add_graded_fill(
            event_id,
            address,
            getattr(fill, "trade_grade", None),
            getattr(fill, "scored_axes", None),
        )

    def scores(self, event_id: str) -> list[PerformanceScore]:
        """Return one ``PerformanceScore`` a participant in ``event_id``."""
        return scores_from_records(self._store.event_records(event_id))

    def pot(self, event_id: str) -> Decimal:
        """Return what ``event_id``'s participants moved into the pot, off the store."""
        return self._store.event_spent(event_id)

    def division(self, event_id: str) -> PotDivision:
        """Return the division of ``event_id``'s pot, moving no Quintessence."""
        return divide_pot(event_id, self.pot(event_id), self.scores(event_id))

    def settled_at(self, event_id: str) -> float:
        """Return the epoch second ``event_id`` was settled, or nought when unpaid."""
        return self._store.event_settled_at(event_id)

    def settled(self, event_id: str) -> PotDivision | None:
        """Return the division ``settle`` paid for ``event_id``, or None."""
        with self._lock:
            return self._settled.get(_as_name(event_id, "event_id"))

    def settle(self, event_id: str, at_epoch: float | None = None) -> PotDivision:
        """Pay every share of ``event_id``'s pot, leaving the reserve where it rests.

        The store is stamped before the ledger moves and unstamped when it refuses,
        so a second ``settle`` is refused across a restart as well as inside one run.
        """
        event = _as_name(event_id, "event_id")
        with self._lock:
            already = self.settled_at(event)
            if already:
                raise RedistributionError(
                    f"{event} was settled at {already}; a second payout would take "
                    f"Quintessence the pot no longer rests"
                )
            division = self.division(event)
            if not division.is_exact:
                raise RedistributionError(
                    f"{event} divides {amount_text(division.pot)} into "
                    f"{amount_text(division.paid_total)} paid and "
                    f"{amount_text(division.reserve)} reserve, which do not sum "
                    f"to the pot"
                )
            credits = {share.address: share.amount for share in division.shares}
            stamp = time.time() if at_epoch is None else float(at_epoch)
            self._store.write_payout(event, credits, stamp)
            try:
                self._ledger.payout(self._held_address, credits)
            except Exception:
                self._store.clear_payout(event)
                raise
            self._settled[event] = division
        logger.info(
            "%s settled: pot %s, %d%% return pool %s, %d share(s) paid %s, reserve "
            "%s rests at %s, %d unscored (%s)",
            event,
            amount_text(division.pot),
            RETURN_PERCENT,
            amount_text(division.return_pool),
            len(division.shares),
            amount_text(division.paid_total),
            amount_text(division.reserve),
            self._held_address,
            len(division.unscored),
            GRADE_NOT_COMPUTED,
        )
        return division

    def summary(self, event_id: str) -> dict:
        """Return the division of ``event_id`` beside the ledger's conservation report."""
        division = self.division(event_id)
        summary = division.to_dict()
        summary["held_address"] = self._held_address
        summary["held_balance"] = amount_text(
            self._ledger.held_balance(self._held_address)
        )
        summary["min_scored_axes"] = MIN_SCORED_AXES
        summary["settled_at"] = self.settled_at(event_id)
        summary["is_settled"] = summary["settled_at"] > 0
        summary["conservation"] = self._ledger.conservation().to_dict()
        return summary
