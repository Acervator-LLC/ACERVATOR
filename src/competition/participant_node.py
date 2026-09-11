"""A participant is one Acervator node holding a Quintessence wallet the ledger knows.

``ParticipantRegistry.register_node`` files one node against a wallet address its
``QuintessenceLedger`` already holds a record for, and ``attach_bot`` names a bot one
source of the trading activity feeding that node.
``participant_count`` counts nodes while ``source_bot_count`` counts bots, so a node
running ten bots is one participant fed by ten sources.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from .quintessence_ledger import QuintessenceLedger, is_wallet_address

logger = logging.getLogger("acervator.participant_node")

#: What a registry with no ledger answers, because no wallet address is checkable.
NO_LEDGER_REASON = (
    "this registry holds no Quintessence ledger, so no wallet address can be "
    "checked and no node registers as a participant"
)


class ParticipantRegistryError(RuntimeError):
    """Raised when a node's wallet is refused, or a bot names an unfiled node."""


def _as_node_id(value: object) -> str:
    """Return ``value`` as a non-empty node id; every other value raises."""
    if type(value) is not str or not value.strip():
        raise ParticipantRegistryError(
            f"a node id must be a non-empty string, got {value!r}"
        )
    return value


def _as_bot_id(value: object) -> str:
    """Return ``value`` as a non-empty bot id; every other value raises."""
    if type(value) is not str or not value.strip():
        raise ParticipantRegistryError(
            f"a bot id must be a non-empty string, got {value!r}"
        )
    return value


@dataclass(frozen=True)
class ParticipantNode:
    """One participant: its node id, the Quintessence wallet it holds, and when."""

    node_id: str
    wallet_address: str
    registered_at: float

    def to_dict(self) -> dict:
        """Return this participant as a JSON-safe dict."""
        return {
            "node_id": self.node_id,
            "wallet_address": self.wallet_address,
            "registered_at": self.registered_at,
        }


class ParticipantRegistry:
    """Every participant node, and the bots whose trading activity feeds each one.

    A bot stays the thing that signs a trade, so nothing here keys a trade log;
    ``node_of_bot`` is the one hop from a signing bot to the participant it feeds.
    """

    def __init__(self, ledger: QuintessenceLedger | None = None) -> None:
        """Hold ``ledger`` as the one authority on which wallet addresses exist."""
        self._ledger = ledger
        self._nodes: dict[str, ParticipantNode] = {}
        self._node_of_bot: dict[str, str] = {}
        self._bots_of_node: dict[str, list[str]] = {}

    # -- Registration --------------------------------------------------------

    def register_node(self, node_id: str, wallet_address: str) -> ParticipantNode:
        """File ``node_id`` as one participant holding ``wallet_address``.

        Refuses an address the ledger's own rule rejects, one no movement has put in
        the ledger's wallet book, and one another node already registered.
        """
        node = _as_node_id(node_id)
        if not is_wallet_address(wallet_address):
            raise ParticipantRegistryError(
                f"node {node} gave {wallet_address!r}, which is no wallet address"
            )
        if self._ledger is None:
            raise ParticipantRegistryError(NO_LEDGER_REASON)
        if not self._ledger.holds_wallet(wallet_address):
            raise ParticipantRegistryError(
                f"node {node} gave wallet {wallet_address}, which the Quintessence "
                f"ledger holds no record of; a participant's wallet is one the "
                f"ledger can answer for"
            )
        held = self._nodes.get(node)
        if held is not None:
            raise ParticipantRegistryError(
                f"node {node} already registered wallet {held.wallet_address}"
            )
        taken = self.node_holding(wallet_address)
        if taken is not None:
            raise ParticipantRegistryError(
                f"wallet {wallet_address} is node {taken}'s already, and counting "
                f"{node} on it would read one wallet as two participants"
            )
        filed = ParticipantNode(node, wallet_address, time.time())
        self._nodes[node] = filed
        self._bots_of_node.setdefault(node, [])
        logger.info("participant node %s registered wallet %s", node, wallet_address)
        return filed

    def attach_bot(self, bot_id: str, node_id: str) -> ParticipantNode:
        """Name ``bot_id`` one source of the activity feeding participant ``node_id``.

        Refuses a node no ``register_node`` call filed, and a bot already feeding a
        different node.
        """
        bot = _as_bot_id(bot_id)
        node = _as_node_id(node_id)
        filed = self._nodes.get(node)
        if filed is None:
            raise ParticipantRegistryError(
                f"bot {bot[:12]} names node {node}, which registered no participant "
                f"wallet; a node registers before its bots feed it"
            )
        held = self._node_of_bot.get(bot)
        if held is not None and held != node:
            raise ParticipantRegistryError(
                f"bot {bot[:12]} already feeds node {held} and cannot also feed {node}"
            )
        if held is None:
            self._node_of_bot[bot] = node
            self._bots_of_node[node].append(bot)
            logger.info("bot %s feeds participant node %s", bot[:12], node)
        return filed

    # -- Queries -------------------------------------------------------------

    def participant_count(self) -> int:
        """Return how many participant nodes this registry holds."""
        return len(self._nodes)

    def participant_nodes(self) -> tuple[ParticipantNode, ...]:
        """Return every participant node, in the order each one registered."""
        return tuple(self._nodes.values())

    def holds_node(self, node_id: str) -> bool:
        """Answer whether ``node_id`` registered a participant wallet."""
        return node_id in self._nodes

    def node_holding(self, wallet_address: str) -> str | None:
        """Return the node id registered against ``wallet_address``, or None."""
        for filed in self._nodes.values():
            if filed.wallet_address == wallet_address:
                return filed.node_id
        return None

    def wallet_of(self, node_id: str) -> str | None:
        """Return the wallet address ``node_id`` registered, or None."""
        filed = self._nodes.get(node_id)
        return None if filed is None else filed.wallet_address

    def node_of_bot(self, bot_id: str) -> str | None:
        """Return the participant node ``bot_id`` feeds, or None when it feeds none."""
        return self._node_of_bot.get(bot_id)

    def source_bots_of(self, node_id: str) -> tuple[str, ...]:
        """Return every bot feeding ``node_id``, in the order each one attached."""
        return tuple(self._bots_of_node.get(node_id, ()))

    def source_bot_count(self) -> int:
        """Return how many bots feed a participant node this registry holds."""
        return len(self._node_of_bot)

    def summary(self) -> dict:
        """Return the participant count, the source-bot count, and each node's bots."""
        return {
            "participant_count": self.participant_count(),
            "source_bot_count": self.source_bot_count(),
            "nodes": [
                {
                    **filed.to_dict(),
                    "source_bots": list(self.source_bots_of(filed.node_id)),
                }
                for filed in self._nodes.values()
            ],
        }
