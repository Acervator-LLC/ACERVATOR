"""Parties, the armies their Raid parties link into, and the General a leader becomes.

``form_party`` seats members against an ``EventMode`` through
``GuildRoster.require_party`` and names one of them the leader. ``Army.link``
admits a ``Party`` of ``ARMY_MODE`` only and refuses an address another linked
raid already holds. ``Army.generals`` reads one General off each linked raid's
own ``Party.leader``, and ``Army.require_formed`` answers ``MIN_LINKED_RAIDS``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .poa_modes import RAID, EventMode, mode_named

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .guild_roster import GuildRoster

logger = logging.getLogger("acervator.army_command")

#: The one mode an army links; every other mode forms a party and links into none.
ARMY_MODE = RAID

#: Raids an army links at least, so one linked raid is never an army.
MIN_LINKED_RAIDS = 2

ROLE_LEADER = "leader"
ROLE_MEMBER = "member"

#: A raid leader reads as this through an army only; a ``Party`` records no general.
ROLE_GENERAL = "general"


class CommandError(RuntimeError):
    """Base for every refusal this module raises."""


class PartyLeaderError(CommandError):
    """Raised for a leader outside the party's own ``Party.members``."""


class ArmyLinkError(CommandError):
    """Raised by ``Army.link`` for a mode no army admits, or an address it holds."""


class ArmySizeError(CommandError):
    """Raised by ``Army.require_formed`` below ``MIN_LINKED_RAIDS`` linked raids."""


def _seated(members: Sequence[object]) -> tuple[str, ...]:
    """``members`` as the addresses ``GuildRoster.require_party`` has admitted."""
    return tuple(str(member).strip() for member in members)


@dataclass(frozen=True)
class Party:
    """One party: its ``EventMode``, its members in seat order, its leader, its guild.

    ``members`` is a tuple, so the size ``GuildRoster.require_party`` admitted at
    forming is the size this party holds for its whole life.
    """

    mode: EventMode
    leader: str
    members: tuple[str, ...]
    guild_key: str | None = None

    @property
    def size(self) -> int:
        """How many addresses ``members`` seats."""
        return len(self.members)

    @property
    def joins_an_army(self) -> bool:
        """Whether this party's ``mode`` is the one ``ARMY_MODE`` names."""
        return self.mode.code == ARMY_MODE

    def holds(self, address: str) -> bool:
        """Whether ``members`` carries ``address``."""
        return address in self.members

    def role_of(self, address: str) -> str | None:
        """Return ``ROLE_LEADER`` for ``leader``, ``ROLE_MEMBER``, else None."""
        if address == self.leader:
            return ROLE_LEADER
        if address in self.members:
            return ROLE_MEMBER
        return None

    def to_dict(self) -> dict:
        """Return this party as a JSON-safe dict ``from_dict`` rebuilds."""
        return {
            "mode": self.mode.code,
            "leader": self.leader,
            "members": list(self.members),
            "guild_key": self.guild_key,
        }

    @classmethod
    def from_dict(cls, d: dict, roster: GuildRoster) -> Party:
        """Return a party rebuilt from ``to_dict``, re-seated by ``form_party``."""
        return form_party(
            roster,
            mode_named(d["mode"]),
            d["leader"],
            [str(member) for member in (d.get("members") or [])],
        )


def form_party(
    roster: GuildRoster,
    mode: EventMode,
    leader: object,
    members: Sequence[object],
) -> Party:
    """Seat ``members`` in ``mode`` with ``leader`` among them, via ``require_party``.

    Raises ``PartyLeaderError`` for a leader outside the seated addresses, and
    ``guild_roster.PartyError`` for a size or a guild ``mode`` does not admit.
    """
    guild = roster.require_party(mode, members)
    wallets = _seated(members)
    leader_wallet = str(leader).strip()
    if leader_wallet not in wallets:
        refusal = (
            f"{leader_wallet!r} leads this {mode.label} party of {len(wallets)} and "
            f"holds no seat in it: {', '.join(wallets)}; a leader is one of the "
            f"party's own members"
        )
        raise PartyLeaderError(refusal)
    party = Party(
        mode=mode,
        leader=leader_wallet,
        members=wallets,
        guild_key=None if guild is None else guild.key,
    )
    logger.info(
        "%s leads a %s party of %d; guild %s",
        party.leader,
        mode.label,
        party.size,
        party.guild_key or "none",
    )
    return party


class Army:
    """Linked Raid parties and the General each linked raid's leader becomes.

    ``link`` keeps one address in one raid, and ``generals`` derives every General
    from a linked ``Party.leader`` at read time.
    """

    def __init__(self, name: object) -> None:
        """Open an army under ``name`` holding no raid and no member."""
        self._name = str(name)
        self._raids: list[Party] = []
        self._raid_by_member: dict[str, int] = {}

    @property
    def name(self) -> str:
        """The name this army was opened under."""
        return self._name

    @property
    def raid_count(self) -> int:
        """How many parties ``link`` has taken."""
        return len(self._raids)

    @property
    def member_count(self) -> int:
        """How many addresses the linked raids hold between them."""
        return len(self._raid_by_member)

    @property
    def is_formed(self) -> bool:
        """Whether ``raid_count`` has reached ``MIN_LINKED_RAIDS``."""
        return self.raid_count >= MIN_LINKED_RAIDS

    def raids(self) -> tuple[Party, ...]:
        """Return every linked party, in the order ``link`` took them."""
        return tuple(self._raids)

    def link(self, party: Party) -> Party:
        """Take ``party`` into this army as one more linked raid under its own General.

        Raises ``ArmyLinkError`` outside ``ARMY_MODE`` and for an address a linked
        raid already holds, and ``PartyLeaderError`` for a leaderless party.
        """
        if not party.joins_an_army:
            refusal = (
                f"a {party.mode.label} party links into no army; an army is built "
                f"from {mode_named(ARMY_MODE).label} parties"
            )
            raise ArmyLinkError(refusal)
        if not party.holds(party.leader):
            refusal = (
                f"{party.leader!r} holds no seat in this party of {party.size}, so "
                f"it has no leader to stand as a {ROLE_GENERAL} in army "
                f"{self._name!r}"
            )
            raise PartyLeaderError(refusal)
        held = [m for m in party.members if m in self._raid_by_member]
        if held:
            refusal = (
                f"{', '.join(held)} already hold seats in army {self._name!r} "
                f"across its {self.raid_count} linked raid(s); one address takes "
                f"one seat in one raid of an army"
            )
            raise ArmyLinkError(refusal)
        index = len(self._raids)
        self._raids.append(party)
        for member in party.members:
            self._raid_by_member[member] = index
        logger.info(
            "%s linked a raid of %d into army %s as the %s of raid %d; "
            "%d raid(s) and %d member(s) now linked",
            party.leader,
            party.size,
            self._name,
            ROLE_GENERAL,
            index,
            self.raid_count,
            self.member_count,
        )
        return party

    def raid_of(self, address: str) -> int | None:
        """Return the index of the linked raid holding ``address``, else None."""
        return self._raid_by_member.get(address)

    def holds(self, address: str) -> bool:
        """Whether any linked raid carries ``address``."""
        return address in self._raid_by_member

    def generals(self) -> tuple[str, ...]:
        """Return the ``Party.leader`` of each linked raid, in link order."""
        return tuple(raid.leader for raid in self._raids)

    def role_of(self, address: str) -> str | None:
        """Return ``ROLE_GENERAL`` for a raid's leader and ``ROLE_MEMBER`` inside one.

        Returns None for an address no linked raid holds.
        """
        index = self._raid_by_member.get(address)
        if index is None:
            return None
        if self._raids[index].leader == address:
            return ROLE_GENERAL
        return ROLE_MEMBER

    def require_formed(self) -> None:
        """Raise ``ArmySizeError`` below ``MIN_LINKED_RAIDS`` linked raids."""
        if self.is_formed:
            return
        refusal = (
            f"army {self._name!r} links {self.raid_count} "
            f"{mode_named(ARMY_MODE).label} party(s); an army links at least "
            f"{MIN_LINKED_RAIDS} of them"
        )
        raise ArmySizeError(refusal)

    def to_dict(self) -> dict:
        """Return this army as a JSON-safe dict ``from_dict`` rebuilds."""
        return {
            "name": self._name,
            "mode": ARMY_MODE,
            "raids": [raid.to_dict() for raid in self._raids],
        }

    @classmethod
    def from_dict(cls, d: dict, roster: GuildRoster) -> Army:
        """Return an army rebuilt from ``to_dict``, each raid re-linked in order."""
        stored_mode = str(d.get("mode", ARMY_MODE))
        if stored_mode != ARMY_MODE:
            refusal = (
                f"the stored army links {stored_mode!r} parties and an army links "
                f"{ARMY_MODE!r} parties"
            )
            raise ArmyLinkError(refusal)
        army = cls(d.get("name", ""))
        for row in d.get("raids") or []:
            army.link(Party.from_dict(row, roster))
        return army

    def command_rows(self) -> list[dict]:
        """Return one row a linked raid: its index, its General and its size."""
        return [
            {
                "raid": index,
                "mode": raid.mode.code,
                "general": raid.leader,
                "members": raid.size,
                "guild_key": raid.guild_key,
            }
            for index, raid in enumerate(self._raids)
        ]

    def command_summary(self) -> dict:
        """Return this army's counts, its Generals and one row a linked raid."""
        return {
            "name": self._name,
            "mode": ARMY_MODE,
            "raid_count": self.raid_count,
            "member_count": self.member_count,
            "min_linked_raids": MIN_LINKED_RAIDS,
            "is_formed": self.is_formed,
            "generals": list(self.generals()),
            "rows": self.command_rows(),
        }
