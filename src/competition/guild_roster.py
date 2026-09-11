"""The guild roster: each guild's members, its officers and the treasury it spends.

``GuildRoster`` files every ``Guild`` under its own ``guild_key``, ``found`` opens
one with its founder as the first member and the first officer, and ``join``,
``leave``, ``promote`` and ``demote`` move the rest. ``guild_of`` answers the one
guild an address belongs to, ``guild_name_of`` answers the guild metric, and
``treasury_of`` answers which guild a treasury address belongs to.
``require_underwrite`` answers whether an officer may commit treasury funds to one
actor's action, and ``require_party`` answers a party against an ``EventMode``'s
``guild_required``, ``party_min`` and ``party_max``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .poa_modes import EventMode

logger = logging.getLogger("acervator.guild_roster")

#: Every treasury address begins with this, as EVENT_POT_ADDRESS names the event pot.
TREASURY_ADDRESS_PREFIX = "poa_guild_treasury_"

#: The QuintessenceLedger bucket a treasury address holds in; ActionSpend._settle
#: reaches QuintessenceLedger.spend, which debits a wallet and credits a held address.
TREASURY_LEDGER_BUCKET = "wallets"

RANK_OFFICER = "officer"
RANK_MEMBER = "member"

#: The runs of characters a guild_key keeps; every other run becomes one underscore.
_KEY_RUNS = re.compile(r"[a-z0-9]+")


class GuildRosterError(RuntimeError):
    """Base for every refusal this module raises."""


class GuildNameError(GuildRosterError):
    """Raised by ``guild_key`` for a name carrying no letter and no digit."""


class GuildExistsError(GuildRosterError):
    """Raised by ``found`` for a name whose ``guild_key`` a guild already holds."""


class UnknownGuildError(GuildRosterError):
    """Raised for a ``guild_key`` no guild in the roster answers to."""


class MembershipError(GuildRosterError):
    """Raised by ``join``, ``leave``, ``promote``, ``demote`` and underwrite checks."""


class PartyError(GuildRosterError):
    """Raised by ``require_party`` for a party an ``EventMode`` does not admit."""


def _as_address(value: object, name: str) -> str:
    """Return ``value`` as a stripped non-empty string; every other value raises."""
    if type(value) is not str or not value.strip():
        refusal = f"{name} must be a non-empty string, got {value!r}"
        raise GuildRosterError(refusal)
    return value.strip()


def guild_key(name: object) -> str:
    """Return ``name`` as the key the roster files a guild under, lowercase."""
    runs = _KEY_RUNS.findall(str(name).lower())
    if not runs:
        refusal = f"a guild name carries at least one letter or digit, got {name!r}"
        raise GuildNameError(refusal)
    return "_".join(runs)


def treasury_address(key: object) -> str:
    """Return the address the guild under ``key`` pays an underwrite from.

    ``guild_key`` runs over ``key`` again, so a guild's name and its key derive one
    address and no second guild reaches it.
    """
    return f"{TREASURY_ADDRESS_PREFIX}{guild_key(key)}"


def treasury_key(address: object) -> str | None:
    """Return the ``guild_key`` inside a treasury ``address``, or None for any other."""
    text = str(address)
    if not text.startswith(TREASURY_ADDRESS_PREFIX):
        return None
    return text[len(TREASURY_ADDRESS_PREFIX) :] or None


@dataclass
class Guild:
    """One guild: its key, its name, its founder, its members and its officers.

    ``members`` keeps join order and ``officers`` holds a subset of it, so
    ``treasury`` names an address only this guild's own officers commit.
    """

    key: str
    name: str
    founder: str
    members: list[str] = field(default_factory=list)
    officers: list[str] = field(default_factory=list)

    @property
    def treasury(self) -> str:
        """Return this guild's treasury address, from ``treasury_address``."""
        return treasury_address(self.key)

    @property
    def member_count(self) -> int:
        """Return how many addresses ``members`` carries."""
        return len(self.members)

    @property
    def officer_count(self) -> int:
        """Return how many addresses ``officers`` carries."""
        return len(self.officers)

    def holds(self, address: object) -> bool:
        """Whether ``members`` carries ``address``."""
        return _as_address(address, "address") in self.members

    def is_officer(self, address: object) -> bool:
        """Whether ``officers`` carries ``address``."""
        return _as_address(address, "address") in self.officers

    def rank_of(self, address: object) -> str | None:
        """Return RANK_OFFICER or RANK_MEMBER, and None outside ``members``."""
        wallet = _as_address(address, "address")
        if wallet in self.officers:
            return RANK_OFFICER
        if wallet in self.members:
            return RANK_MEMBER
        return None

    def to_dict(self) -> dict:
        """Return this guild as a JSON-safe dict ``from_dict`` rebuilds."""
        return {
            "key": self.key,
            "name": self.name,
            "founder": self.founder,
            "members": list(self.members),
            "officers": list(self.officers),
            "treasury": self.treasury,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Guild:
        """Return a ``Guild`` built from a dict written by ``to_dict``."""
        members = [str(member) for member in (d.get("members") or [])]
        officers = [str(officer) for officer in (d.get("officers") or [])]
        return cls(
            key=guild_key(d["key"]),
            name=str(d.get("name", d["key"])),
            founder=str(d["founder"]),
            members=members,
            officers=[officer for officer in officers if officer in members],
        )


class GuildRoster:
    """Every guild in one world, reached by key, by member address and by treasury.

    ``found`` and ``join`` refuse an address another guild already carries, so
    ``guild_of`` answers one guild an address and an underwrite reads one membership.
    """

    def __init__(self) -> None:
        """Open an empty roster holding no guild and no membership."""
        self._guilds: dict[str, Guild] = {}
        self._guild_by_member: dict[str, str] = {}

    @property
    def guild_count(self) -> int:
        """Return how many guilds the roster holds."""
        return len(self._guilds)

    @property
    def member_count(self) -> int:
        """Return how many addresses hold membership across every guild."""
        return len(self._guild_by_member)

    def keys(self) -> list[str]:
        """Return every ``guild_key`` the roster holds, in sorted order."""
        return sorted(self._guilds)

    def guilds(self) -> list[Guild]:
        """Return every ``Guild`` the roster holds, ordered by ``guild_key``."""
        return [self._guilds[key] for key in self.keys()]

    def guild(self, key: object) -> Guild:
        """Return the guild under ``key``, raising ``UnknownGuildError`` for others."""
        wanted = guild_key(key)
        found = self._guilds.get(wanted)
        if found is None:
            refusal = (
                f"{wanted!r} is no guild in this roster; it holds "
                f"{self.guild_count} of them"
            )
            raise UnknownGuildError(refusal)
        return found

    # -- Membership ----------------------------------------------------------

    def found(self, name: object, founder: object) -> Guild:
        """Open a guild under ``name`` with ``founder`` as first member and officer.

        ``require_underwrite`` needs an officer, so a guild opened with none commits
        no treasury at all.
        """
        key = guild_key(name)
        wallet = _as_address(founder, "founder")
        if key in self._guilds:
            held = self._guilds[key]
            refusal = (
                f"{held.name!r} already holds the key {key!r} and its treasury "
                f"{held.treasury}; two guilds never share one treasury address"
            )
            raise GuildExistsError(refusal)
        self._require_unaffiliated(wallet, "founder")
        guild = Guild(
            key=key,
            name=str(name),
            founder=wallet,
            members=[wallet],
            officers=[wallet],
        )
        self._guilds[key] = guild
        self._guild_by_member[wallet] = key
        logger.info(
            "%s founded guild %s as its first officer; treasury %s holds in the "
            "%s bucket",
            wallet,
            key,
            guild.treasury,
            TREASURY_LEDGER_BUCKET,
        )
        return guild

    def join(self, key: object, address: object) -> Guild:
        """Add ``address`` to the guild under ``key`` as a member holding no office."""
        guild = self.guild(key)
        wallet = _as_address(address, "address")
        self._require_unaffiliated(wallet, "address")
        guild.members.append(wallet)
        self._guild_by_member[wallet] = guild.key
        logger.info(
            "%s joined guild %s, which now holds %d member(s)",
            wallet,
            guild.key,
            guild.member_count,
        )
        return guild

    def leave(self, key: object, address: object) -> Guild:
        """Remove ``address`` from the guild under ``key``, and from office with it."""
        guild = self.guild(key)
        wallet = self._require_member(guild, address)
        guild.members.remove(wallet)
        if wallet in guild.officers:
            guild.officers.remove(wallet)
        del self._guild_by_member[wallet]
        logger.info(
            "%s left guild %s, which now holds %d member(s) and %d officer(s)",
            wallet,
            guild.key,
            guild.member_count,
            guild.officer_count,
        )
        return guild

    def promote(self, key: object, address: object) -> Guild:
        """Put a member of the guild under ``key`` into office."""
        guild = self.guild(key)
        wallet = self._require_member(guild, address)
        if wallet not in guild.officers:
            guild.officers.append(wallet)
            logger.info("%s took office in guild %s", wallet, guild.key)
        return guild

    def demote(self, key: object, address: object) -> Guild:
        """Take an officer of guild ``key`` out of office, keeping ``members``."""
        guild = self.guild(key)
        wallet = self._require_member(guild, address)
        if wallet in guild.officers:
            guild.officers.remove(wallet)
            logger.info(
                "%s left office in guild %s, which now holds %d officer(s)",
                wallet,
                guild.key,
                guild.officer_count,
            )
        return guild

    # -- The lookups the other modules read ----------------------------------

    def guild_of(self, address: object) -> Guild | None:
        """Return the one guild ``address`` holds membership in, or None for none."""
        key = self._guild_by_member.get(_as_address(address, "address"))
        return None if key is None else self._guilds[key]

    def guild_name_of(self, address: object) -> str | None:
        """Return the name of the guild ``address`` belongs to, or None for none.

        This is the value the guild metric holds, which ``METRIC_SEAMS`` names as
        carried by no field.
        """
        guild = self.guild_of(address)
        return None if guild is None else guild.name

    def rank_of(self, address: object) -> str | None:
        """Return ``address``'s rank in its own guild, or None outside every guild."""
        guild = self.guild_of(address)
        return None if guild is None else guild.rank_of(address)

    def treasury_of(self, address: object) -> Guild | None:
        """Return the guild whose treasury is ``address``, or None for any other."""
        key = treasury_key(address)
        return None if key is None else self._guilds.get(key)

    def treasury_for(self, address: object) -> str | None:
        """Return the treasury address of the guild ``address`` belongs to, or None."""
        guild = self.guild_of(address)
        return None if guild is None else guild.treasury

    # -- The underwrite check -------------------------------------------------

    def require_underwrite(self, officer: object, actor: object) -> Guild:
        """Return the guild whose treasury ``officer`` may commit to ``actor``'s action.

        ``ActionSpend.offer_underwrite`` takes an officer name and checks nothing, so
        this answers its four refusals: an officer in no guild, an officer holding no
        office, an actor outside that guild, and an officer underwriting their own act.
        """
        officer_wallet = _as_address(officer, "officer")
        actor_wallet = _as_address(actor, "actor")
        guild = self.guild_of(officer_wallet)
        if guild is None:
            refusal = (
                f"{officer_wallet} belongs to no guild and commits no treasury; "
                f"the roster holds {self.guild_count} guild(s)"
            )
            raise MembershipError(refusal)
        if not guild.is_officer(officer_wallet):
            refusal = (
                f"{officer_wallet} is a {RANK_MEMBER} of {guild.key} and not an "
                f"{RANK_OFFICER}; {guild.officer_count} officer(s) commit its "
                f"treasury"
            )
            raise MembershipError(refusal)
        if not guild.holds(actor_wallet):
            refusal = (
                f"{actor_wallet} is no member of {guild.key}, so treasury "
                f"{guild.treasury} pays nothing for that action"
            )
            raise MembershipError(refusal)
        if officer_wallet == actor_wallet:
            refusal = (
                f"{officer_wallet} is both the {RANK_OFFICER} and the actor; an "
                f"underwrite takes two addresses and nobody underwrites their own act"
            )
            raise MembershipError(refusal)
        return guild

    # -- The party check ------------------------------------------------------

    def require_party(self, mode: EventMode, party: Sequence[object]) -> Guild | None:
        """Return the guild a party shares, or None for a mode needing no guild.

        ``EventMode.guild_required`` is declared and read by no check, so this answers
        it beside ``party_min`` and ``party_max`` of the same mode.
        """
        wallets = self._seated(party)
        if not mode.party_min <= len(wallets) <= mode.party_max:
            refusal = (
                f"{mode.label} admits {mode.party_min} to {mode.party_max} "
                f"participants and this party holds {len(wallets)}"
            )
            raise PartyError(refusal)
        if not mode.guild_required:
            return None
        guild = self.guild_of(wallets[0])
        if guild is None:
            refusal = f"{mode.label} requires a guild and {wallets[0]} belongs to none"
            raise PartyError(refusal)
        outside = [wallet for wallet in wallets if not guild.holds(wallet)]
        if outside:
            refusal = (
                f"{mode.label} requires one guild and {len(outside)} of "
                f"{len(wallets)} participants are no members of {guild.key}: "
                f"{', '.join(outside)}"
            )
            raise PartyError(refusal)
        return guild

    # -- Reconstruction and readout ------------------------------------------

    def to_dict(self) -> dict:
        """Return every guild as a JSON-safe dict ``from_dict`` rebuilds."""
        return {
            "treasury_bucket": TREASURY_LEDGER_BUCKET,
            "guilds": [guild.to_dict() for guild in self.guilds()],
        }

    @classmethod
    def from_dict(cls, d: dict) -> GuildRoster:
        """Return a roster rebuilt from a dict written by ``to_dict``."""
        stored_bucket = str(d.get("treasury_bucket", TREASURY_LEDGER_BUCKET))
        if stored_bucket != TREASURY_LEDGER_BUCKET:
            refusal = (
                f"the stored roster holds its treasuries in the {stored_bucket!r} "
                f"bucket and this one reads {TREASURY_LEDGER_BUCKET!r}"
            )
            raise GuildRosterError(refusal)
        roster = cls()
        for row in d.get("guilds") or []:
            roster._adopt(Guild.from_dict(row))
        return roster

    def roster_rows(self) -> list[dict]:
        """Return one row a guild, as a surface would serve the roster."""
        return [
            {
                "key": guild.key,
                "name": guild.name,
                "founder": guild.founder,
                "treasury": guild.treasury,
                "members": guild.member_count,
                "officers": guild.officer_count,
            }
            for guild in self.guilds()
        ]

    def roster_summary(self) -> dict:
        """Return the guild count, the member count, the treasury bucket and rows."""
        return {
            "guild_count": self.guild_count,
            "member_count": self.member_count,
            "treasury_prefix": TREASURY_ADDRESS_PREFIX,
            "treasury_bucket": TREASURY_LEDGER_BUCKET,
            "guilds": self.roster_rows(),
        }

    # -- Internals ------------------------------------------------------------

    def _seated(self, party: Sequence[object]) -> list[str]:
        """Return a party as addresses, refusing one address seated twice."""
        seats = list(party)
        wallets: list[str] = []
        for seat, address in enumerate(seats):
            wallet = _as_address(address, f"party[{seat}]")
            if wallet in wallets:
                refusal = (
                    f"{wallet} holds two seats in a party of {len(seats)}; one "
                    f"address takes one seat"
                )
                raise PartyError(refusal)
            wallets.append(wallet)
        return wallets

    def _adopt(self, guild: Guild) -> None:
        """Take a rebuilt ``Guild`` in, refusing a repeated key or a repeated member."""
        if guild.key in self._guilds:
            refusal = (
                f"the stored roster carries {guild.key!r} twice and one key names "
                f"one treasury address"
            )
            raise GuildExistsError(refusal)
        claimed = [
            member for member in guild.members if member in self._guild_by_member
        ]
        if claimed:
            refusal = (
                f"the stored roster puts {', '.join(claimed)} in {guild.key} and in "
                f"another guild; one address belongs to one guild"
            )
            raise MembershipError(refusal)
        self._guilds[guild.key] = guild
        for member in guild.members:
            self._guild_by_member[member] = guild.key

    def _require_unaffiliated(self, wallet: str, name: str) -> None:
        """Raise ``MembershipError`` while another guild already carries ``wallet``."""
        held = self._guild_by_member.get(wallet)
        if held is not None:
            refusal = (
                f"{name} {wallet} already belongs to {held}; one address belongs to "
                f"one guild, so a transfer between guild members reads one guild"
            )
            raise MembershipError(refusal)

    def _require_member(self, guild: Guild, address: object) -> str:
        """Return ``address`` as a member of ``guild``, raising for any other."""
        wallet = _as_address(address, "address")
        if wallet not in guild.members:
            refusal = (
                f"{wallet} is no member of {guild.key}, which holds "
                f"{guild.member_count} member(s)"
            )
            raise MembershipError(refusal)
        return wallet
