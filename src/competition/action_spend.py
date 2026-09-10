"""The Action Budget Curve, the charge that spans turns, and the PoA record store.

``BANDS`` prices five actions from ``BAND_X1`` to ``BAND_X100`` and ``band_ratio``
reads the dearest against the cheapest. ``ActionSpend.act`` takes a single-turn
action and ``begin_charge`` / ``complete_charge`` / ``abandon_charge`` take one
spanning turns, every one reaching ``QuintessenceLedger.spend``. ``PoaRecordStore``
holds each participant's ``SkillProgress`` and one ``ActionRecord`` a participant an
event, and ``UnderwriteOffer`` carries an officer's treasury commitment until
``accept_underwrite`` or ``refuse_underwrite``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.io_utils import atomic_write_json
from .skill_ladder import (
    SKILL_NAMES,
    TRANSFER_SKILL_NAME,
    UNTRAINED_LEVEL,
    SkillGateError,
    SkillProgress,
    transfer_bleed,
    transfer_level,
)

if TYPE_CHECKING:
    from .quintessence_ledger import QuintessenceLedger

logger = logging.getLogger("acervator.action_spend")

BAND_X1 = "x1"
BAND_X3 = "x3"
BAND_X10 = "x10"
BAND_X30 = "x30"
BAND_X100 = "x100"

#: Each band costs about three times the one below, dearest a hundred times cheapest.
BANDS: dict[str, Decimal] = {
    BAND_X1: Decimal("0.001"),
    BAND_X3: Decimal("0.003"),
    BAND_X10: Decimal("0.010"),
    BAND_X30: Decimal("0.030"),
    BAND_X100: Decimal("0.100"),
}

BAND_NAMES: tuple[str, ...] = tuple(BANDS)
CHEAPEST_BAND = BAND_NAMES[0]
DEAREST_BAND = BAND_NAMES[-1]

#: What each band buys, from the Action Budget Curve.
BAND_ACTIONS: dict[str, str] = {
    BAND_X1: "move, switch weapon, take an item from a bag",
    BAND_X3: "a basic attack, a basic heal",
    BAND_X10: "a class ability on a cooldown",
    BAND_X30: "a group-wide ability, a threat move across the field",
    BAND_X100: "a multi-turn spell, and the decisive tactics beside it",
}

MIN_CHARGE_TURNS = 1

DEFAULT_STORE_PATH = Path.home() / ".acervator" / "poa_record_store.json"
STORE_FILE_VERSION = 1

#: The held address every Elite action's Quintessence rests at, and the pot a payout
#: divides; what stays there after a payout is the reserve.
EVENT_POT_ADDRESS = "poa_elite_event_pot"

PAYER_ACTOR = "actor"
PAYER_TREASURY = "treasury"

OFFER_OPEN = "open"
OFFER_REFUSED = "refused"


class ActionSpendError(RuntimeError):
    """Base for every refusal this module raises."""


class UnknownBandError(ActionSpendError):
    """Raised for a band name ``BANDS`` does not carry."""


class UnaffordableActionError(ActionSpendError):
    """Raised when the payer's wallet holds less than ``band_cost``."""


class ChargeError(ActionSpendError):
    """Raised for a charge unknown, early, or under ``MIN_CHARGE_TURNS``."""


class UnderwriteError(ActionSpendError):
    """Raised for an ``UnderwriteOffer`` unknown or not the actor's."""


def _as_identifier(value: object, name: str) -> str:
    """Return ``value`` as a stripped non-empty string; every other value raises."""
    if type(value) is not str or not value.strip():
        raise ActionSpendError(f"{name} must be a non-empty string, got {value!r}")
    return value.strip()


def band_cost(band: str) -> Decimal:
    """Return what ``band`` costs in Quintessence."""
    cost = BANDS.get(band)
    if cost is None:
        raise UnknownBandError(
            f"{band!r} is not an action band; the curve carries "
            f"{', '.join(BAND_NAMES)}"
        )
    return cost


def band_ratio() -> Decimal:
    """Return ``DEAREST_BAND``'s cost divided by ``CHEAPEST_BAND``'s."""
    return BANDS[DEAREST_BAND] / BANDS[CHEAPEST_BAND]


def band_rows() -> list[dict]:
    """Return every band with its cost and what ``BAND_ACTIONS`` puts in it."""
    return [
        {"band": name, "cost": str(BANDS[name]), "actions": BAND_ACTIONS[name]}
        for name in BAND_NAMES
    ]


@dataclass(frozen=True)
class ActionDraft:
    """One action before anything is debited: who acts, in which band, and who pays.

    ``by_actor`` names the actor as ``payer_address`` and ``by_treasury`` names a
    guild treasury.
    """

    event_id: str
    address: str
    band: str
    payer: str
    payer_address: str

    def __post_init__(self) -> None:
        """Refuse an empty identifier and a band ``BANDS`` does not carry."""
        for name in ("event_id", "address", "payer", "payer_address"):
            _as_identifier(getattr(self, name), name)
        band_cost(self.band)

    @property
    def cost(self) -> Decimal:
        """Return what ``band`` costs, from ``band_cost``."""
        return band_cost(self.band)

    @classmethod
    def by_actor(cls, event_id: str, address: str, band: str) -> ActionDraft:
        """Return a draft the actor pays for, which is the default payer."""
        wallet = _as_identifier(address, "address")
        return cls(
            event_id=_as_identifier(event_id, "event_id"),
            address=wallet,
            band=band,
            payer=PAYER_ACTOR,
            payer_address=wallet,
        )

    @classmethod
    def by_treasury(
        cls, event_id: str, address: str, band: str, treasury_address: str
    ) -> ActionDraft:
        """Return a draft a guild treasury pays for, which the actor must accept."""
        return cls(
            event_id=_as_identifier(event_id, "event_id"),
            address=_as_identifier(address, "address"),
            band=band,
            payer=PAYER_TREASURY,
            payer_address=_as_identifier(treasury_address, "treasury_address"),
        )


@dataclass
class ActionRecord:
    """One participant's acting in one event, the only record either reader reads.

    ``spent`` and ``underwritten`` sum what each payer moved, ``last_acted_at`` is
    the epoch second the dormancy clock reads, and ``grade_numeric`` with
    ``scored_axes`` carry the ``TradeGrade`` the payout divides on.
    """

    event_id: str
    address: str
    actions: int = 0
    spent: Decimal = Decimal(0)
    underwritten: Decimal = Decimal(0)
    bands: dict[str, int] = field(default_factory=dict)
    first_acted_at: float = 0.0
    last_acted_at: float = 0.0
    grade_numeric: Decimal = Decimal(0)
    scored_axes: int = 0
    paid: Decimal = Decimal(0)
    settled_at: float = 0.0

    def to_dict(self) -> dict:
        """Return this record as a JSON-safe dict with every Decimal as a string."""
        return {
            "event_id": self.event_id,
            "address": self.address,
            "actions": self.actions,
            "spent": str(self.spent),
            "underwritten": str(self.underwritten),
            "bands": dict(self.bands),
            "first_acted_at": self.first_acted_at,
            "last_acted_at": self.last_acted_at,
            "grade_numeric": str(self.grade_numeric),
            "scored_axes": self.scored_axes,
            "paid": str(self.paid),
            "settled_at": self.settled_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ActionRecord:
        """Return an ``ActionRecord`` built from a dict written by ``to_dict``."""
        return cls(
            event_id=str(d["event_id"]),
            address=str(d["address"]),
            actions=int(d.get("actions", 0)),
            spent=Decimal(str(d.get("spent", "0"))),
            underwritten=Decimal(str(d.get("underwritten", "0"))),
            bands={str(k): int(v) for k, v in (d.get("bands") or {}).items()},
            first_acted_at=float(d.get("first_acted_at", 0.0)),
            last_acted_at=float(d.get("last_acted_at", 0.0)),
            grade_numeric=Decimal(str(d.get("grade_numeric", "0"))),
            scored_axes=int(d.get("scored_axes", 0)),
            paid=Decimal(str(d.get("paid", "0"))),
            settled_at=float(d.get("settled_at", 0.0)),
        )


@dataclass(frozen=True)
class ActionCharge:
    """One ``ActionDraft`` held over ``turns`` turns before ``complete_charge`` pays it.

    ``begin_charge`` debits nothing and ``completes_turn`` is the turn it casts on.
    """

    charge_id: str
    draft: ActionDraft
    turns: int
    opened_turn: int

    @property
    def cost(self) -> Decimal:
        """Return what the draft's band costs."""
        return self.draft.cost

    @property
    def completes_turn(self) -> int:
        """Return the turn index this charge casts on."""
        return self.opened_turn + self.turns - 1


@dataclass(frozen=True)
class UnderwriteOffer:
    """A guild ``officer``'s commitment of treasury funds to one actor's action.

    ``state`` stays ``OFFER_OPEN`` until ``accept_underwrite`` or
    ``refuse_underwrite`` answers it, and only the draft's address may answer.
    """

    offer_id: str
    draft: ActionDraft
    officer: str
    state: str = OFFER_OPEN

    @property
    def cost(self) -> Decimal:
        """Return what the draft's band costs."""
        return self.draft.cost


@dataclass(frozen=True)
class ActionReceipt:
    """What one completed action moved, and the ``ActionRecord`` it left behind."""

    draft: ActionDraft
    cost: Decimal
    held_address: str
    record: ActionRecord


class PoaRecordStore:
    """The durable store behind the skill ladder and the action records.

    ``skill_progress`` and ``record_skill_use`` hold a participant's
    ``SkillProgress``, ``action_record`` and ``last_acted_at`` read the record,
    ``write_grade`` puts the graded trade a payout divides on, and ``save`` and
    ``load`` carry both across a restart.
    """

    def __init__(self, store_path: str | Path | None = None) -> None:
        """Point the store at ``store_path`` or ``DEFAULT_STORE_PATH``, reading none."""
        self._path: Path = Path(store_path) if store_path else DEFAULT_STORE_PATH
        self._skills: dict[str, dict[str, SkillProgress]] = {}
        self._records: dict[str, dict[str, ActionRecord]] = {}
        self._lock = threading.RLock()

    @property
    def store_path(self) -> Path:
        """Return the file ``save`` writes and ``load`` replays."""
        return self._path

    # -- The skill ladder's store --------------------------------------------

    def skill_progress(self, address: str, skill_name: str) -> SkillProgress:
        """Return ``address``'s ``SkillProgress``, building it on first use."""
        wallet = _as_identifier(address, "address")
        if skill_name not in SKILL_NAMES:
            raise ActionSpendError(
                f"{skill_name!r} is not a PoA skill; the ladder carries "
                f"{', '.join(SKILL_NAMES)}"
            )
        with self._lock:
            held = self._skills.setdefault(wallet, {})
            progress = held.get(skill_name)
            if progress is None:
                progress = SkillProgress(skill_name)
                held[skill_name] = progress
            return progress

    def record_skill_use(
        self, address: str, skill_name: str, quality: object
    ) -> SkillProgress:
        """Add one use's ``quality`` to ``address``'s standing and write the store."""
        progress = self.skill_progress(address, skill_name)
        with self._lock:
            progress.record_use(quality)
            self.save()
        return progress

    def skill_rows(self, address: str) -> list[dict]:
        """Return ``address``'s level, weighted uses and effect in each held skill."""
        wallet = _as_identifier(address, "address")
        with self._lock:
            held = self._skills.get(wallet, {})
            return [
                {
                    "skill_name": name,
                    "level": held[name].level,
                    "weighted_uses": str(held[name].weighted_uses),
                    "effect": str(held[name].effect),
                }
                for name in sorted(held)
            ]

    # -- The action record's two readers -------------------------------------

    def action_record(self, event_id: str, address: str) -> ActionRecord:
        """Return the one ``ActionRecord`` for ``address`` in ``event_id``."""
        event = _as_identifier(event_id, "event_id")
        wallet = _as_identifier(address, "address")
        with self._lock:
            per_event = self._records.setdefault(event, {})
            record = per_event.get(wallet)
            if record is None:
                record = ActionRecord(event, wallet)
                per_event[wallet] = record
            return record

    def last_acted_at(self, address: str) -> float:
        """Return the latest ``last_acted_at`` over every event ``address`` acted in."""
        wallet = _as_identifier(address, "address")
        with self._lock:
            return max(
                (
                    per_event[wallet].last_acted_at
                    for per_event in self._records.values()
                    if wallet in per_event
                ),
                default=0.0,
            )

    def event_records(self, event_id: str) -> list[ActionRecord]:
        """Return every participant's ``ActionRecord`` in ``event_id``, by address."""
        event = _as_identifier(event_id, "event_id")
        with self._lock:
            per_event = self._records.get(event, {})
            return [per_event[wallet] for wallet in sorted(per_event)]

    def event_spent(self, event_id: str) -> Decimal:
        """Return every record's ``spent`` and ``underwritten`` in ``event_id``, summed.

        Both payers move Quintessence to the held address, so this total is what
        rests there for ``event_id``.
        """
        return sum(
            (
                record.spent + record.underwritten
                for record in self.event_records(event_id)
            ),
            Decimal(0),
        )

    def write_action(
        self, draft: ActionDraft, cost: Decimal, at_epoch: float
    ) -> ActionRecord:
        """Add one action of ``draft`` to its ``ActionRecord`` and write the store."""
        record = self.action_record(draft.event_id, draft.address)
        with self._lock:
            record.actions += 1
            record.bands[draft.band] = record.bands.get(draft.band, 0) + 1
            if draft.payer == PAYER_TREASURY:
                record.underwritten += cost
            else:
                record.spent += cost
            stamp = float(at_epoch)
            if record.first_acted_at == 0.0:
                record.first_acted_at = stamp
            record.last_acted_at = stamp
            self.save()
        return record

    def write_grade(
        self, event_id: str, address: str, grade_numeric: object, scored_axes: object
    ) -> ActionRecord:
        """Put one graded trade's ``grade_numeric`` and ``scored_axes`` on the record.

        ``scored_axes`` of nought leaves ``grade_numeric`` a default, which the
        payout refuses a share on.
        """
        if type(scored_axes) is not int or scored_axes < 0:
            raise ActionSpendError(
                f"scored_axes must be a whole number of axes, got {scored_axes!r}"
            )
        if (
            type(grade_numeric) not in (int, float, Decimal)
            or type(grade_numeric) is bool
        ):
            raise ActionSpendError(
                f"grade_numeric must be int, float or Decimal, "
                f"not {type(grade_numeric).__name__}"
            )
        numeric = Decimal(str(grade_numeric))
        if not numeric.is_finite() or numeric < 0 or numeric > 1:
            raise ActionSpendError(
                f"grade_numeric must be 0 to 1, got {grade_numeric!r}"
            )
        record = self.action_record(event_id, address)
        with self._lock:
            record.grade_numeric = numeric
            record.scored_axes = scored_axes
            self.save()
        return record

    def event_settled_at(self, event_id: str) -> float:
        """Return the latest ``settled_at`` in ``event_id``, or nought when unpaid."""
        return max(
            (record.settled_at for record in self.event_records(event_id)),
            default=0.0,
        )

    def write_payout(
        self, event_id: str, credits: dict, at_epoch: float
    ) -> list[ActionRecord]:
        """Stamp ``credits`` and ``at_epoch`` onto every record in ``event_id``.

        Every record in the event takes the stamp, so an event with no credit is
        still marked settled and ``event_settled_at`` refuses a second payout.
        """
        event = _as_identifier(event_id, "event_id")
        if not isinstance(credits, dict):
            raise ActionSpendError(
                f"credits must be a dict of address to amount, "
                f"not {type(credits).__name__}"
            )
        stamp = float(at_epoch)
        with self._lock:
            records = self.event_records(event)
            for record in records:
                record.paid = Decimal(str(credits.get(record.address, 0)))
                record.settled_at = stamp
            self.save()
        return records

    def clear_payout(self, event_id: str) -> list[ActionRecord]:
        """Take the payout stamp back off every record in ``event_id``."""
        with self._lock:
            records = self.event_records(event_id)
            for record in records:
                record.paid = Decimal(0)
                record.settled_at = 0.0
            self.save()
        return records

    # -- Persistence ---------------------------------------------------------

    def save(self) -> Path:
        """Write every ``SkillProgress`` and ``ActionRecord`` to ``store_path``."""
        with self._lock:
            return atomic_write_json(
                self._path,
                {
                    "version": STORE_FILE_VERSION,
                    "skills": {
                        address: {
                            name: str(progress.weighted_uses)
                            for name, progress in sorted(held.items())
                        }
                        for address, held in sorted(self._skills.items())
                    },
                    "records": {
                        event: {
                            address: record.to_dict()
                            for address, record in sorted(per_event.items())
                        }
                        for event, per_event in sorted(self._records.items())
                    },
                },
            )

    def load(self) -> PoaRecordStore:
        """Replay ``store_path``, leaving every held value as it stands on a bad read.

        A missing, unreadable or foreign-version file lowers nothing.
        """
        if not self._path.exists():
            return self
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception(
                "%s could not be read; the store stays as held", self._path
            )
            return self
        if data.get("version") != STORE_FILE_VERSION:
            logger.warning(
                "%s is version %r, this build reads %d; the store stays as held",
                self._path,
                data.get("version"),
                STORE_FILE_VERSION,
            )
            return self
        with self._lock:
            self._load_skills(data.get("skills") or {})
            self._load_records(data.get("records") or {})
        return self

    def _load_skills(self, skills: dict) -> None:
        """Fill ``_skills``, dropping a name outside ``SKILL_NAMES``."""
        for address, held in skills.items():
            for name, uses in held.items():
                if name not in SKILL_NAMES:
                    logger.warning(
                        "%s holds standing in %r, which is no PoA skill; dropped",
                        address,
                        name,
                    )
                    continue
                self._skills.setdefault(str(address), {})[str(name)] = SkillProgress(
                    str(name), Decimal(str(uses))
                )

    def _load_records(self, records: dict) -> None:
        """Fill ``_records`` through ``ActionRecord.from_dict``."""
        for event, per_event in records.items():
            for address, row in per_event.items():
                self._records.setdefault(str(event), {})[str(address)] = (
                    ActionRecord.from_dict(row)
                )


def transfer_standing(store: PoaRecordStore, address: str) -> dict:
    """Return ``address``'s transfer-skill standing, read from ``store``.

    ``level`` and ``bleed`` come from ``transfer_level`` and ``transfer_bleed``, and
    an untrained standing reports ``UNTRAINED_LEVEL`` with no bleed.
    """
    progress = store.skill_progress(address, TRANSFER_SKILL_NAME)
    standing: dict[str, object] = {
        "skill_name": progress.skill_name,
        "address": address,
        "weighted_uses": str(progress.weighted_uses),
        "effect": str(progress.effect),
        "uses_to_next_level": str(progress.uses_to_next_level),
    }
    try:
        standing["level"] = transfer_level(progress)
        standing["bleed"] = str(transfer_bleed(progress))
    except SkillGateError as gate:
        standing["level"] = UNTRAINED_LEVEL
        standing["bleed"] = None
        standing["gate"] = str(gate)
    return standing


class ActionSpend:
    """Prices an Elite action on the Action Budget Curve and debits it on the cast.

    The ledger, the store and the held address arrive by construction, so a demo run
    is one ``ActionSpend`` over a different chain's ledger and store running the same
    ``act`` path.
    """

    def __init__(
        self,
        ledger: QuintessenceLedger,
        store: PoaRecordStore,
        held_address: str,
    ) -> None:
        """Hold the ledger, the store and the held address every spend rests at."""
        self._ledger = ledger
        self._store = store
        self._held_address = _as_identifier(held_address, "held_address")
        self._charges: dict[str, ActionCharge] = {}
        self._offers: dict[str, UnderwriteOffer] = {}
        self._lock = threading.RLock()

    @property
    def held_address(self) -> str:
        """Return the held address every action's Quintessence rests at."""
        return self._held_address

    @property
    def store(self) -> PoaRecordStore:
        """Return the ``PoaRecordStore`` this spend writes its records to."""
        return self._store

    # -- A single-turn action ------------------------------------------------

    def quote(self, band: str) -> Decimal:
        """Return what ``band`` costs, from ``band_cost``."""
        return band_cost(band)

    def can_afford(self, address: str, band: str) -> bool:
        """Whether ``address``'s wallet covers ``band``'s cost."""
        return self._ledger.balance(_as_identifier(address, "address")) >= band_cost(
            band
        )

    def act(
        self,
        event_id: str,
        address: str,
        band: str,
        at_epoch: float | None = None,
    ) -> ActionReceipt:
        """Debit ``band``'s cost from ``address`` and write one action to its record."""
        return self._settle(ActionDraft.by_actor(event_id, address, band), at_epoch)

    # -- A charge that spans turns ------------------------------------------

    def begin_charge(
        self, draft: ActionDraft, turns: int, opened_turn: int
    ) -> ActionCharge:
        """Open ``draft`` over ``turns`` turns, refusing one its payer cannot afford.

        Nothing is debited here; ``complete_charge`` is the only write path.
        """
        if type(turns) is not int or turns < MIN_CHARGE_TURNS:
            raise ChargeError(
                f"a charge occupies at least {MIN_CHARGE_TURNS} turn, got {turns!r}"
            )
        self._require_balance(draft)
        charge = ActionCharge(
            charge_id=(
                f"{draft.event_id}:{draft.address}:{draft.band}:{int(opened_turn)}"
            ),
            draft=draft,
            turns=int(turns),
            opened_turn=int(opened_turn),
        )
        with self._lock:
            self._charges[charge.charge_id] = charge
        return charge

    def open_charges(self) -> list[ActionCharge]:
        """Return every charge that has neither completed nor been abandoned."""
        with self._lock:
            return [self._charges[key] for key in sorted(self._charges)]

    def abandon_charge(self, charge_id: str, reason: str) -> ActionCharge:
        """Drop an open charge, debiting nothing and writing no ``ActionRecord``."""
        charge = self._take_charge(charge_id)
        logger.info(
            "charge %s abandoned (%s); %s Quintessence stays in %s",
            charge.charge_id,
            reason,
            charge.cost,
            charge.draft.payer_address,
        )
        return charge

    def complete_charge(
        self, charge_id: str, at_turn: int, at_epoch: float | None = None
    ) -> ActionReceipt:
        """Debit an open charge at ``completes_turn`` and write one action to it."""
        with self._lock:
            charge = self._charges.get(charge_id)
            if charge is None:
                raise ChargeError(
                    f"{charge_id!r} is not an open charge; "
                    f"{len(self._charges)} stand open"
                )
            if int(at_turn) < charge.completes_turn:
                raise ChargeError(
                    f"charge {charge.charge_id} casts on turn "
                    f"{charge.completes_turn} and it is turn {int(at_turn)}; "
                    f"no partial action exists"
                )
            del self._charges[charge_id]
        return self._settle(charge.draft, at_epoch)

    # -- The treasury underwrite --------------------------------------------

    def offer_underwrite(self, draft: ActionDraft, officer: str) -> UnderwriteOffer:
        """Record an officer's commitment of treasury funds, debiting nothing yet."""
        if draft.payer != PAYER_TREASURY:
            raise UnderwriteError(
                f"an underwrite draft pays from {PAYER_TREASURY!r} and this one "
                f"pays from {draft.payer!r}; build it with ActionDraft.by_treasury"
            )
        offer = UnderwriteOffer(
            offer_id=f"{draft.event_id}:{draft.address}:{draft.band}",
            draft=draft,
            officer=_as_identifier(officer, "officer"),
        )
        with self._lock:
            self._offers[offer.offer_id] = offer
        return offer

    def open_offers(self, address: str | None = None) -> list[UnderwriteOffer]:
        """Return every unanswered offer, or only those addressed to ``address``."""
        with self._lock:
            offers = [self._offers[key] for key in sorted(self._offers)]
        if address is None:
            return offers
        wallet = _as_identifier(address, "address")
        return [offer for offer in offers if offer.draft.address == wallet]

    def accept_underwrite(
        self, offer_id: str, address: str, at_epoch: float | None = None
    ) -> ActionReceipt:
        """Answer an offer yes, debiting the treasury and writing the actor's record."""
        offer = self._take_offer(offer_id, address)
        return self._settle(offer.draft, at_epoch)

    def refuse_underwrite(self, offer_id: str, address: str) -> UnderwriteOffer:
        """Answer an offer no, debiting neither the treasury nor the actor."""
        offer = self._take_offer(offer_id, address)
        logger.info(
            "underwrite %s refused by %s; %s Quintessence stays in treasury %s",
            offer.offer_id,
            offer.draft.address,
            offer.cost,
            offer.draft.payer_address,
        )
        return UnderwriteOffer(
            offer_id=offer.offer_id,
            draft=offer.draft,
            officer=offer.officer,
            state=OFFER_REFUSED,
        )

    # -- Readouts -----------------------------------------------------------

    def spend_summary(self, event_id: str) -> dict:
        """Return the curve, the held address and every record in ``event_id``."""
        return {
            "held_address": self._held_address,
            "store_path": str(self._store.store_path),
            "bands": band_rows(),
            "band_ratio": str(band_ratio()),
            "event_id": event_id,
            "event_spent": str(self._store.event_spent(event_id)),
            "records": [
                record.to_dict() for record in self._store.event_records(event_id)
            ],
            "open_charges": len(self.open_charges()),
            "open_offers": len(self.open_offers()),
        }

    # -- Internals ----------------------------------------------------------

    def _require_balance(self, draft: ActionDraft) -> None:
        """Raise ``UnaffordableActionError`` while the payer holds under the cost."""
        held = self._ledger.balance(draft.payer_address)
        if held < draft.cost:
            raise UnaffordableActionError(
                f"{draft.payer_address} holds {held} Quintessence and band "
                f"{draft.band} costs {draft.cost}; no partial action exists and "
                f"nobody borrows against the next turn"
            )

    def _settle(self, draft: ActionDraft, at_epoch: float | None) -> ActionReceipt:
        """Spend through the ledger, then write the record; a refusal writes none."""
        self._require_balance(draft)
        self._ledger.spend(draft.payer_address, draft.cost, self._held_address)
        stamp = time.time() if at_epoch is None else float(at_epoch)
        record = self._store.write_action(draft, draft.cost, stamp)
        return ActionReceipt(
            draft=draft,
            cost=draft.cost,
            held_address=self._held_address,
            record=record,
        )

    def _take_charge(self, charge_id: str) -> ActionCharge:
        """Remove and return an open charge, raising ``ChargeError`` for any other."""
        with self._lock:
            charge = self._charges.pop(charge_id, None)
        if charge is None:
            raise ChargeError(
                f"{charge_id!r} is not an open charge; "
                f"{len(self._charges)} stand open"
            )
        return charge

    def _take_offer(self, offer_id: str, address: str) -> UnderwriteOffer:
        """Remove an open offer, raising ``UnderwriteError`` for any other id."""
        wallet = _as_identifier(address, "address")
        with self._lock:
            offer = self._offers.get(offer_id)
            if offer is None:
                raise UnderwriteError(
                    f"{offer_id!r} is not an open underwrite offer; "
                    f"{len(self._offers)} stand open"
                )
            if offer.draft.address != wallet:
                raise UnderwriteError(
                    f"offer {offer_id} is addressed to {offer.draft.address} and "
                    f"{wallet} cannot answer it; only the actor accepts"
                )
            del self._offers[offer_id]
        return offer
