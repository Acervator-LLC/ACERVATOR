"""Link two Acervator nodes over loopback so both chains hold the same records.

``PoaNodeLink`` takes its ``LocalTestnet`` at construction and binds no socket
until ``start_listening`` runs. ``announce`` writes one ``PeerEndpoint`` file into
``peer_dir``, ``peers`` reads the others, and ``sync_with`` trades every
``ChainRecord`` both ways. ``apply_records`` keeps a record whose ``placement_id``
the chain does not already hold and closes one block over the batch, so arrival
order decides nothing, and refuses one whose id its own contents do not name.
"""

from __future__ import annotations

import json
import logging
import socket
import socketserver
import threading
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..core.io_utils import atomic_write_json
from .local_testnet import LocalTestnet, TxRecord, canonical_json

logger = logging.getLogger("acervator.node_link")

#: The only interface this link binds. No method takes a host argument.
LOOPBACK_HOST = "127.0.0.1"

DEFAULT_PEER_DIR = Path.home() / ".acervator" / "poa_nodes"
DEFAULT_NETWORK = "acervator-poa"
PEER_FILE_SUFFIX = ".json"

MAX_MESSAGE_BYTES = 8 * 1024 * 1024
CONNECT_TIMEOUT_S = 5.0


class NodeLinkError(RuntimeError):
    """Raised when a link is not listening, or a peer is refused."""


@dataclass(frozen=True)
class ChainRecord:
    """One ``LocalChain`` transaction, its ``placement_id`` and the events it emitted.

    The eight declared fields are the whole of the wire record, so ``from_payload``
    raises ``TypeError`` for any other key.
    """

    from_addr: str
    to_addr: str
    function_name: str
    args: dict
    gas_used: int
    placement_id: str
    placed_at: float
    events: tuple

    @classmethod
    def from_payload(cls, payload: dict) -> "ChainRecord":
        """Build one record from a wire ``payload``, normalizing ``events``."""
        if not isinstance(payload, dict):
            raise TypeError(f"a record payload must be a dict, not {type(payload)}")
        fields = dict(payload)
        raw_events = fields.pop("events", ())
        events = tuple(
            (str(contract), str(event_name), dict(event_args))
            for contract, event_name, event_args in raw_events
        )
        return cls(events=events, **fields)

    def to_payload(self) -> dict:
        """Return this record as the JSON-safe dict the wire carries."""
        return {
            "from_addr": self.from_addr,
            "to_addr": self.to_addr,
            "function_name": self.function_name,
            "args": self.args,
            "gas_used": self.gas_used,
            "placement_id": self.placement_id,
            "placed_at": self.placed_at,
            "events": [list(event) for event in self.events],
        }

    def as_tx(self) -> TxRecord:
        """Return this record as an unmined ``TxRecord`` for ``LocalChain.mine``."""
        return TxRecord(
            tx_hash="",
            block_number=0,
            from_addr=self.from_addr,
            to_addr=self.to_addr,
            function_name=self.function_name,
            args=dict(self.args),
            gas_used=self.gas_used,
            timestamp=self.placed_at,
        )

    def content_id(self) -> str:
        """Return the ``TxRecord.placement_id`` this record's own fields produce."""
        return self.as_tx().placement_id()

    def id_matches_contents(self) -> bool:
        """Answer whether ``placement_id`` equals the ``content_id`` of this record."""
        return self.placement_id == self.content_id()


@dataclass(frozen=True)
class PeerEndpoint:
    """Where one node listens, and the ``network`` it will trade records on."""

    node_id: str
    network: str
    host: str
    port: int

    @classmethod
    def from_payload(cls, payload: dict) -> "PeerEndpoint":
        """Build one endpoint from an announcement file's ``payload``."""
        return cls(
            node_id=str(payload["node_id"]),
            network=str(payload["network"]),
            host=str(payload["host"]),
            port=int(payload["port"]),
        )

    def to_payload(self) -> dict:
        """Return this endpoint as the dict ``announce`` writes."""
        return {
            "node_id": self.node_id,
            "network": self.network,
            "host": self.host,
            "port": self.port,
        }


class _LinkRequestHandler(socketserver.StreamRequestHandler):
    """Apply one peer's records to this node's chain and answer with its own."""

    def handle(self) -> None:
        """Read one request line, apply its records, and write this node's records."""
        link: PoaNodeLink = self.server.link  # type: ignore[attr-defined]
        raw = self.rfile.readline(MAX_MESSAGE_BYTES + 1)
        if len(raw) > MAX_MESSAGE_BYTES:
            self._refuse(f"a request over {MAX_MESSAGE_BYTES} bytes is refused")
            return
        try:
            request = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._refuse(f"unreadable request: {type(exc).__name__}: {exc}")
            return
        asked = request.get("network")
        if asked != link.network:
            self._refuse(f"network {asked!r} is not {link.network!r}")
            return
        try:
            records = [ChainRecord.from_payload(r) for r in request.get("records", ())]
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            self._refuse(f"unusable record: {type(exc).__name__}: {exc}")
            return
        applied = link.apply_records(records)
        logger.info(
            "node %s took %d of %d records from peer %s",
            link.node_id,
            applied,
            len(records),
            request.get("node_id"),
        )
        self._answer({"records": [r.to_payload() for r in link.records()]})

    def _answer(self, payload: dict) -> None:
        """Write ``payload`` back, stamped with this node's id and network."""
        link: PoaNodeLink = self.server.link  # type: ignore[attr-defined]
        body = dict(payload)
        body["node_id"] = link.node_id
        body["network"] = link.network
        self.wfile.write((canonical_json(body) + "\n").encode("utf-8"))

    def _refuse(self, reason: str) -> None:
        """Answer with ``reason`` and apply nothing."""
        logger.warning("node link refused a request: %s", reason)
        self._answer({"error": reason})


class _LinkServer(socketserver.ThreadingTCPServer):
    """The loopback server one ``PoaNodeLink`` starts, refusing any other address."""

    daemon_threads = True

    def __init__(self, link: "PoaNodeLink") -> None:
        """Bind an ephemeral loopback port and hold ``link`` for the handler."""
        self.link = link
        super().__init__((LOOPBACK_HOST, 0), _LinkRequestHandler)

    def verify_request(self, request: object, client_address: tuple) -> bool:
        """Refuse a client whose address is not ``LOOPBACK_HOST``."""
        if client_address[0] != LOOPBACK_HOST:
            logger.warning("node link refused non-loopback client %s", client_address)
            return False
        return True


class PoaNodeLink:
    """One Acervator node's link to the others sharing its ``peer_dir``.

    The chain arrives by construction, so a TestNet demo run is one link over a
    different ``LocalTestnet`` and a different ``peer_dir`` running the same
    ``sync_with`` path. Construction binds nothing; ``start_listening`` is the only
    call that creates a socket.
    """

    def __init__(
        self,
        testnet: LocalTestnet,
        node_id: str,
        peer_dir: str | Path | None = None,
        network: str = DEFAULT_NETWORK,
        mutation_lock: AbstractContextManager[bool] | None = None,
    ) -> None:
        """Hold the chain, the node id and the peer directory; no socket is made."""
        self._testnet = testnet
        self._node_id = str(node_id)
        self._peer_dir = Path(peer_dir) if peer_dir else DEFAULT_PEER_DIR
        self._network = str(network)
        self._chain_lock: AbstractContextManager[bool] = (
            mutation_lock if mutation_lock is not None else threading.RLock()
        )
        self._server: _LinkServer | None = None
        self._serve_thread: threading.Thread | None = None

    # -- Identity ------------------------------------------------------------

    @property
    def node_id(self) -> str:
        """The id naming this node's announcement file in ``peer_dir``."""
        return self._node_id

    @property
    def network(self) -> str:
        """The network name a peer must match before any record is applied."""
        return self._network

    @property
    def peer_dir(self) -> Path:
        """The directory this node announces into and discovers peers from."""
        return self._peer_dir

    @property
    def is_listening(self) -> bool:
        """Whether ``start_listening`` has built a server that is still open."""
        return self._server is not None

    @property
    def endpoint(self) -> PeerEndpoint:
        """Where this node listens; raises ``NodeLinkError`` while not listening."""
        if self._server is None:
            raise NodeLinkError(
                f"node {self._node_id} is not listening, so it has no endpoint"
            )
        host, port = self._server.server_address[:2]
        return PeerEndpoint(
            node_id=self._node_id,
            network=self._network,
            host=str(host),
            port=int(port),
        )

    # -- Chain records -------------------------------------------------------

    def records(self) -> list[ChainRecord]:
        """Every transaction on this node's chain, in the order it was mined."""
        with self._chain_lock:
            chain = self._testnet.chain
            events: dict[str, list] = {}
            for event in chain._events:
                events.setdefault(event.tx_hash, []).append(
                    (event.contract, event.event_name, dict(event.args))
                )
            return [
                ChainRecord(
                    from_addr=tx.from_addr,
                    to_addr=tx.to_addr,
                    function_name=tx.function_name,
                    args=dict(tx.args),
                    gas_used=int(tx.gas_used),
                    placement_id=tx.placement_id(),
                    placed_at=float(tx.timestamp),
                    events=tuple(events.get(tx.tx_hash, ())),
                )
                for tx in chain._txs.values()
            ]

    def apply_records(self, records: Iterable[ChainRecord]) -> int:
        """Close one block over every record this chain lacks, and return how many.

        Refuses a record whose ``placement_id`` is not the ``content_id`` of its own
        fields, and reaches ``LocalChain.mine`` and ``LocalChain.emit`` only.
        """
        placed: list[tuple[ChainRecord, TxRecord]] = []
        with self._chain_lock:
            chain = self._testnet.chain
            held = set()
            for record in records:
                if not record.id_matches_contents():
                    logger.warning(
                        "node %s refused record %s calling %s: its contents name %s",
                        self._node_id,
                        record.placement_id,
                        record.function_name,
                        record.content_id(),
                    )
                    continue
                if record.placement_id in held or chain.holds_placement(
                    record.placement_id
                ):
                    continue
                held.add(record.placement_id)
                placed.append((record, record.as_tx()))
            if not placed:
                return 0
            chain.mine([tx for _, tx in placed])
            for record, tx in placed:
                for contract, event_name, event_args in record.events:
                    chain.emit(tx.tx_hash, contract, event_name, dict(event_args))
        return len(placed)

    # -- Listening -----------------------------------------------------------

    def start_listening(self) -> PeerEndpoint:
        """Bind an ephemeral loopback port, serve it on a thread, and announce it."""
        if self._server is not None:
            raise NodeLinkError(f"node {self._node_id} is already listening")
        self._server = _LinkServer(self)
        self._serve_thread = threading.Thread(
            target=self._server.serve_forever,
            name=f"poa-node-link-{self._node_id}",
            daemon=True,
        )
        self._serve_thread.start()
        endpoint = self.endpoint
        self.announce(endpoint)
        logger.info(
            "node %s listening on %s:%d (network=%s, records=%d)",
            self._node_id,
            endpoint.host,
            endpoint.port,
            self._network,
            len(self.records()),
        )
        return endpoint

    def stop_listening(self) -> None:
        """Close the server, join its thread, and delete this node's announcement."""
        server, thread = self._server, self._serve_thread
        self._server = None
        self._serve_thread = None
        self.withdraw()
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=CONNECT_TIMEOUT_S)
        logger.info("node %s stopped listening", self._node_id)

    def announce(self, endpoint: PeerEndpoint) -> Path:
        """Write ``endpoint`` to this node's own file under ``peer_dir``."""
        path = self._peer_dir / f"{self._node_id}{PEER_FILE_SUFFIX}"
        atomic_write_json(path, endpoint.to_payload(), indent=2)
        return path

    def withdraw(self) -> None:
        """Delete this node's announcement file, so no peer discovers it again."""
        path = self._peer_dir / f"{self._node_id}{PEER_FILE_SUFFIX}"
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(
                "node %s left its announcement behind: %s", self._node_id, exc
            )

    # -- Discovery -----------------------------------------------------------

    def peers(self) -> list[PeerEndpoint]:
        """Every endpoint announced in ``peer_dir`` on this ``network``, bar
        ``node_id``.
        """
        if not self._peer_dir.is_dir():
            return []
        found: list[PeerEndpoint] = []
        for path in sorted(self._peer_dir.glob(f"*{PEER_FILE_SUFFIX}")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                endpoint = PeerEndpoint.from_payload(payload)
            except (OSError, KeyError, TypeError, ValueError) as exc:
                logger.warning("unreadable peer file %s: %s", path.name, exc)
                continue
            if endpoint.node_id == self._node_id or endpoint.network != self._network:
                continue
            found.append(endpoint)
        return found

    # -- Synchronisation -----------------------------------------------------

    def sync_with(self, peer: PeerEndpoint) -> int:
        """Trade records with ``peer`` and return how many this node took from it."""
        if peer.network != self._network:
            raise NodeLinkError(
                f"peer {peer.node_id} is on network {peer.network!r}, "
                f"not {self._network!r}"
            )
        sent = self.records()
        request = {
            "node_id": self._node_id,
            "network": self._network,
            "records": [r.to_payload() for r in sent],
        }
        reply = self._exchange(peer, request)
        if "error" in reply:
            raise NodeLinkError(f"peer {peer.node_id} refused: {reply['error']}")
        offered = [ChainRecord.from_payload(r) for r in reply.get("records", ())]
        held_before = len(sent)
        applied = self.apply_records(offered)
        logger.info(
            "node %s synced with %s: held %d, offered %d, took %d, now holds %d",
            self._node_id,
            peer.node_id,
            held_before,
            len(offered),
            applied,
            len(self.records()),
        )
        return applied

    def sync_all(self) -> int:
        """Sync with every discovered peer and return the total records taken."""
        taken = 0
        discovered = self.peers()
        logger.info(
            "node %s discovered %d peers in %s",
            self._node_id,
            len(discovered),
            self._peer_dir,
        )
        for peer in discovered:
            try:
                taken += self.sync_with(peer)
            except (NodeLinkError, OSError) as exc:
                logger.warning(
                    "node %s could not sync with %s: %s",
                    self._node_id,
                    peer.node_id,
                    exc,
                )
        return taken

    def _exchange(self, peer: PeerEndpoint, request: dict) -> dict:
        """Send ``request`` to ``peer`` over loopback and read its one-line reply."""
        with socket.create_connection(
            (peer.host, peer.port), timeout=CONNECT_TIMEOUT_S
        ) as conn:
            conn.sendall((canonical_json(request) + "\n").encode("utf-8"))
            with conn.makefile("rb") as stream:
                raw = stream.readline(MAX_MESSAGE_BYTES + 1)
        if not raw:
            raise NodeLinkError(f"peer {peer.node_id} closed without a reply")
        if len(raw) > MAX_MESSAGE_BYTES:
            raise NodeLinkError(f"peer {peer.node_id} replied over the byte ceiling")
        reply = json.loads(raw.decode("utf-8"))
        if not isinstance(reply, dict):
            raise NodeLinkError(
                f"peer {peer.node_id} replied with {type(reply).__name__}, not an object"
            )
        return reply
