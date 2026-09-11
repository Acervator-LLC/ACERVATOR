"""Every Vessel a Reincarnate occupies, and the one wallet balance they all read.

``Vessel`` pairs a ``CLASSES`` entry with a level and reads its ``StatBlock``
from ``stat_block_at_level``, and ``Reincarnate`` holds an address with every
Vessel owned by it. ``Reincarnate.requirement`` adds every Vessel's block through
``quintessence_requirement`` and ``Reincarnate.potential`` reads that one sum
against one balance through ``potential_at``, so ``vessel_potentials`` hands
every Vessel the same ``fraction`` and another Vessel lowers it.
``pleroma_standing`` answers whether a Reincarnate has merged with the pleroma,
which needs a zero balance and ``has_ever_held_quintessence`` together, and
``ABSENT_MECHANISMS`` names what no module builds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from .entity_stats import (
    Potential,
    StatBlock,
    potential_at,
    quintessence_requirement,
    stat_block_at_level,
)
from .quintessence_ledger import QuintessenceLedger, amount_text
from .rpg_classes import (
    CLASS_NAMES,
    FIRST_LEVEL,
    CharacterClass,
    UnknownClassError,
    class_named,
)

logger = logging.getLogger("acervator.vessels")

#: What a Reincarnate reads once a balance it held has fallen to nothing.
MERGED_WITH_PLEROMA = "fully merged with the pleroma"

#: What a Reincarnate still holding Quintessence reads.
HOLDS_A_BALANCE = "holds a Quintessence balance"

#: What a participant no movement has touched reads, and it never merges.
NEVER_HELD_A_BALANCE = "has never held a Quintessence balance"

#: What bounds a Reincarnate's Vessel count. No figure caps it.
VESSEL_COUNT_UNCAPPED = "the wallet balance is the only bound on Vessel count"

#: What a Vessel takes part in that no module builds.
ABSENT_MECHANISMS: tuple[str, ...] = (
    "assignments",
    "lifeskilling",
    "crafting",
    "notifications",
    "gear",
    "equipping",
    "destruction",
    "permadeath",
)

#: What each entry in ``ABSENT_MECHANISMS`` waits on.
ABSENT_MECHANISM_NOTES: dict[str, str] = {
    "assignments": "nothing gives a Vessel a task to carry over several turns",
    "lifeskilling": "one skill ladder exists and no Vessel runs it",
    "crafting": "no module makes an item",
    "notifications": "nothing tells a player that a Vessel finished",
    "gear": "no module holds an item a Vessel wears",
    "equipping": "nothing holds gear to the equipping holder's Quintessence",
    "destruction": "pvp_vote.may_destroy answers who may, and nothing destroys",
    "permadeath": "no module ends a Vessel",
}


class VesselError(RuntimeError):
    """Base for every refusal this module raises."""


class VesselOwnerError(VesselError):
    """Raised for a blank address, or a Vessel whose owner is another address."""


def _as_address(value: object, name: str) -> str:
    """Return ``value`` as a non-empty address string; every other value raises."""
    if type(value) is not str or not value.strip():
        raise VesselOwnerError(
            f"{name} must be a non-empty address string, got {value!r}"
        )
    return value


def require_class(name: str) -> CharacterClass:
    """The ``CLASSES`` entry ``name`` names, refusing a name outside ``CLASS_NAMES``."""
    entry = class_named(name)
    if entry is None:
        raise UnknownClassError(
            f"{name!r} is not a PoA class; the seven are {', '.join(CLASS_NAMES)}"
        )
    return entry


@dataclass(frozen=True)
class Vessel:
    """One class a Reincarnate occupies, at one level, owned by one address.

    ``stats`` reads ``stat_block_at_level`` and ``requirement`` is the
    Quintessence that block holds.
    """

    owner: str
    class_name: str
    level: int = FIRST_LEVEL

    def __post_init__(self) -> None:
        """Refuse a blank ``owner``, a name outside ``CLASS_NAMES``, and a bad ``level``."""
        _as_address(self.owner, "owner")
        require_class(self.class_name)
        stat_block_at_level(self.level)

    @property
    def character_class(self) -> CharacterClass:
        """The ``CLASSES`` entry ``class_name`` names."""
        return require_class(self.class_name)

    @property
    def stats(self) -> StatBlock:
        """This Vessel's stats at ``level``, from ``stat_block_at_level``."""
        return stat_block_at_level(self.level)

    @property
    def requirement(self) -> Decimal:
        """The Quintessence this Vessel alone needs to run at full potential."""
        return quintessence_requirement((self.stats,))

    def to_dict(self) -> dict:
        """This Vessel as a JSON-safe dict, the requirement a plain string."""
        entry = self.character_class
        return {
            "owner": self.owner,
            "class_name": self.class_name,
            "planet": entry.planet,
            "assignment": entry.assignment,
            "level": self.level,
            "requirement": amount_text(self.requirement),
        }


@dataclass(frozen=True)
class VesselPotential:
    """What one Vessel reaches, read off the whole wallet and not off its own share.

    ``requirement`` is this Vessel alone and ``wallet_potential`` is every Vessel
    of one ``Reincarnate`` against one balance.
    """

    vessel: Vessel
    requirement: Decimal
    wallet_potential: Potential

    @property
    def fraction(self) -> Decimal:
        """The fraction of full potential this Vessel runs at, shared with its siblings."""
        return self.wallet_potential.fraction

    @property
    def is_full(self) -> bool:
        """Whether the balance covers every Vessel's requirement together."""
        return self.wallet_potential.is_full

    def to_dict(self) -> dict:
        """This reading as a JSON-safe dict, every amount a plain string."""
        return {
            "vessel": self.vessel.to_dict(),
            "requirement": amount_text(self.requirement),
            "fraction": amount_text(self.fraction),
            "is_full": self.is_full,
            "wallet_potential": self.wallet_potential.to_dict(),
        }


@dataclass(frozen=True)
class Reincarnate:
    """One participant, named by its wallet address, and every Vessel it occupies.

    ``requirement`` adds every Vessel's block, and ``VESSEL_COUNT_UNCAPPED`` names
    the one balance ``potential`` reads as the only bound on ``vessels``.
    """

    address: str
    vessels: tuple[Vessel, ...] = ()

    def __post_init__(self) -> None:
        """Refuse a blank ``address`` and any Vessel whose ``owner`` is another address."""
        _as_address(self.address, "address")
        held = tuple(self.vessels)
        for vessel in held:
            if vessel.owner != self.address:
                raise VesselOwnerError(
                    f"{vessel.class_name} is owned by {vessel.owner!r}, "
                    f"not by {self.address!r}"
                )
        object.__setattr__(self, "vessels", held)

    @property
    def blocks(self) -> tuple[StatBlock, ...]:
        """One ``StatBlock`` a Vessel, in the order ``vessels`` holds them."""
        return tuple(vessel.stats for vessel in self.vessels)

    @property
    def requirement(self) -> Decimal:
        """What every Vessel needs together, from ``quintessence_requirement``."""
        return quintessence_requirement(self.blocks)

    def potential(self, balance: object) -> Potential:
        """Read ``balance`` against every Vessel's requirement at once.

        ``potential_at`` deducts nothing, and the balance stays in the wallet
        while the Vessels run on it.
        """
        return potential_at(balance, self.blocks)

    def vessel_potentials(self, balance: object) -> tuple[VesselPotential, ...]:
        """One reading a Vessel, each carrying the ``fraction`` all of them share."""
        shared = self.potential(balance)
        logger.info(
            "%s runs %d Vessels needing %s against a balance of %s, each at %s of full",
            self.address,
            len(self.vessels),
            amount_text(shared.requirement),
            amount_text(shared.balance),
            amount_text(shared.fraction),
        )
        return tuple(
            VesselPotential(vessel, vessel.requirement, shared)
            for vessel in self.vessels
        )

    def to_dict(self) -> dict:
        """This Reincarnate as a JSON-safe dict, one entry a Vessel."""
        return {
            "address": self.address,
            "vessels": [vessel.to_dict() for vessel in self.vessels],
            "requirement": amount_text(self.requirement),
            "vessel_count_bound": VESSEL_COUNT_UNCAPPED,
        }


@dataclass(frozen=True)
class PleromaStanding:
    """Whether one ``Reincarnate`` has merged with the pleroma.

    ``is_merged`` needs a zero ``balance`` and ``has_ever_held`` together.
    """

    address: str
    balance: Decimal
    has_ever_held: bool
    is_merged: bool
    reason: str

    def to_dict(self) -> dict:
        """This standing as a JSON-safe dict, the balance a plain string."""
        return {
            "address": self.address,
            "balance": amount_text(self.balance),
            "has_ever_held": self.has_ever_held,
            "is_merged": self.is_merged,
            "reason": self.reason,
        }


def has_ever_held_quintessence(ledger: QuintessenceLedger, address: str) -> bool:
    """Whether ``ledger`` records any movement touching ``address``.

    ``movements`` is empty for a newcomer and not for a spent participant at the
    same zero balance.
    """
    return bool(ledger.movements(_as_address(address, "address")))


def pleroma_standing(
    address: str, balance: object, has_ever_held: object
) -> PleromaStanding:
    """Read whether ``address`` has merged with the pleroma at ``balance``.

    ``NEVER_HELD_A_BALANCE`` keeps a newcomer out of ``MERGED_WITH_PLEROMA`` at
    the same zero balance.
    """
    wallet = _as_address(address, "address")
    if type(has_ever_held) is not bool:
        raise VesselError(
            f"has_ever_held must be bool, not {type(has_ever_held).__name__}"
        )
    # potential_at refuses a balance outside the supply, and no block requires nothing.
    held = potential_at(balance, ()).balance
    if held > 0:
        merged, reason = False, HOLDS_A_BALANCE
    elif not has_ever_held:
        merged, reason = False, NEVER_HELD_A_BALANCE
    else:
        merged, reason = True, MERGED_WITH_PLEROMA
    logger.info(
        "%s holds %s and has ever held %s, so it reads %s",
        wallet,
        amount_text(held),
        has_ever_held,
        reason,
    )
    return PleromaStanding(wallet, held, has_ever_held, merged, reason)
