"""Shared LocalTestnet bridge.

``SharedTestnetBridge.install_on`` attaches one ``LocalTestnet`` and one
``QuintessenceLedger`` to a MainWindow and starts ``_drain_queue`` on a
timer. Each queued
``CompetitionRequest`` runs in a ``_CompetitionWorker``, which mutates
the chain on its own thread while it holds ``_mutation_lock``, one
worker at a time. ``_save_now`` writes the chain to
``DEFAULT_PERSIST_PATH`` and ``_try_load`` drops a file whose
``schema_version`` is not ``SCHEMA_VERSION``.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from ..core.io_utils import atomic_write_json

if TYPE_CHECKING:
    from src.competition.action_spend import ActionSpend
    from src.competition.capture_bounds import CaptureBounds
    from src.competition.certification_socket import CertificationSocket
    from src.competition.market_rotation import MarketRotation
    from src.competition.node_link import PoaNodeLink
    from src.competition.quintessence_ledger import QuintessenceLedger

from PySide6.QtCore import QObject, QThread, QTimer, Signal

logger = logging.getLogger("acervator.shared_testnet")


SCHEMA_VERSION = 1
DEFAULT_PERSIST_PATH = Path.home() / ".acervator" / "testnet_chain.json"
QUEUE_DRAIN_INTERVAL_MS = 250
PERSIST_DEBOUNCE_MS = 500


@dataclass
class CompetitionRequest:
    """One competition to run against the shared chain.

    ``request_competition`` enqueues it from any thread and
    ``_CompetitionWorker`` runs it.
    """

    symbol: str
    season: int
    n_bots: int = 3
    round_id: Optional[int] = None  # for caller correlation


class _CompetitionWorker(QThread):
    """Run one ``CompetitionRequest`` against the shared ``LocalTestnet``.

    ``run`` holds ``_lock`` for the mutation and emits
    ``finished_competition`` with the result dict, or with an ``error``
    key when ``run_demo_competition`` raises.
    """

    finished_competition = Signal(dict)

    def __init__(
        self, testnet, request: CompetitionRequest, lock: threading.Lock, parent=None
    ):
        super().__init__(parent)
        self._testnet = testnet
        self._request = request
        self._lock = lock

    def run(self):
        try:
            with self._lock:
                result = self._testnet.run_demo_competition(
                    n_bots=self._request.n_bots,
                    season=self._request.season,
                    symbol=self._request.symbol,
                )
            if not isinstance(result, dict):
                result = {"error": f"unexpected result type: {type(result)}"}
            result["_request"] = {
                "symbol": self._request.symbol,
                "season": self._request.season,
                "n_bots": self._request.n_bots,
                "round_id": self._request.round_id,
            }
            self.finished_competition.emit(result)
        except Exception as e:
            logger.exception("CompetitionWorker failed: %s", e)
            self.finished_competition.emit(
                {
                    "error": f"{type(e).__name__}: {e}",
                    "_request": asdict(self._request),
                }
            )


class SharedTestnetBridge(QObject):
    """Owns one ``LocalTestnet`` and the queue that crosses threads into it.

    ``request_competition`` enqueues work, ``chain_updated`` and
    ``competition_completed`` report a finished run, and ``reset``
    clears the chain and the file at ``_persist_path``.
    """

    chain_updated = Signal()  # not emitted when the worker returns an error
    competition_completed = Signal(dict)  # full result, including "error"
    chain_reset = Signal(str)  # reason string

    def __init__(self, testnet, persist_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._testnet = testnet
        self._persist_path = persist_path
        self._queue: queue.Queue = queue.Queue()
        self._mutation_lock = threading.Lock()
        self._active_worker: Optional[_CompetitionWorker] = None
        self._certification_socket: Optional[CertificationSocket] = None
        self._market_rotation: Optional[MarketRotation] = None
        self._capture_bounds: Optional[CaptureBounds] = None
        self._node_link: Optional[PoaNodeLink] = None
        self._action_spend: Optional[ActionSpend] = None

        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(QUEUE_DRAIN_INTERVAL_MS)
        self._drain_timer.timeout.connect(self._drain_queue)
        self._drain_timer.start()

        self._persist_timer = QTimer(self)
        self._persist_timer.setInterval(PERSIST_DEBOUNCE_MS)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.timeout.connect(self._save_now)

    # ── Installation factory (called once by MainWindow) ──────────────
    @classmethod
    def install_on(
        cls,
        main_win,
        persist_path: Optional[Path] = None,
        quint_ledger_path: Optional[Path] = None,
        socket_path: Optional[Path] = None,
        rotation_path: Optional[Path] = None,
        bounds_path: Optional[Path] = None,
        peer_dir: Optional[Path] = None,
        network: Optional[str] = None,
        action_store_path: Optional[Path] = None,
        event_pot_address: Optional[str] = None,
    ):
        """Create the shared ``LocalTestnet``, the bridge, the
        ``QuintessenceLedger``, the ``CertificationSocket``, the
        ``MarketRotation``, the ``CaptureBounds``, the ``PoaNodeLink`` and
        the ``ActionSpend``, and attach all eight to ``main_win``.

        A second call raises ``RuntimeError`` while ``_testnet_bridge``
        is set.
        """
        if getattr(main_win, "_testnet_bridge", None) is not None:
            raise RuntimeError(
                "SharedTestnetBridge already installed " "on this MainWindow"
            )
        from src.competition.local_testnet import LocalTestnet

        path = persist_path or DEFAULT_PERSIST_PATH
        testnet = LocalTestnet()
        bridge = cls(testnet, persist_path=path, parent=main_win)
        bridge._try_load()
        main_win._local_testnet = testnet
        main_win._testnet_bridge = bridge
        ledger = cls.install_quint_ledger(quint_ledger_path)
        main_win._quint_ledger = ledger
        main_win._certification_socket = bridge.install_certification_socket(
            ledger, socket_path
        )
        main_win._market_rotation = bridge.install_market_rotation(rotation_path)
        main_win._capture_bounds = bridge.install_capture_bounds(
            main_win._market_rotation, bounds_path
        )
        main_win._node_link = bridge.install_node_link(peer_dir, network)
        main_win._action_spend = bridge.install_action_spend(
            ledger, action_store_path, event_pot_address
        )
        logger.info("SharedTestnetBridge installed (persist=%s)", path)
        return bridge

    def install_action_spend(
        self,
        quint_ledger: QuintessenceLedger,
        store_path: Optional[Path] = None,
        held_address: Optional[str] = None,
    ) -> ActionSpend:
        """Build the ``ActionSpend`` and load its ``PoaRecordStore``.

        The ledger, the store path and the held address arrive by
        construction, so a demo run is one ``ActionSpend`` over another
        chain's ledger and store running the same ``act`` path.
        """
        from src.competition.action_spend import (
            EVENT_POT_ADDRESS,
            PoaRecordStore,
            band_ratio,
            band_rows,
        )
        from src.competition.action_spend import ActionSpend as _Spend

        store = PoaRecordStore(store_path)
        store.load()
        spend = _Spend(quint_ledger, store, held_address or EVENT_POT_ADDRESS)
        self._action_spend = spend
        logger.info(
            "ActionSpend installed (store=%s, pot=%s, bands=%s, ratio=%s)",
            store.store_path,
            spend.held_address,
            ", ".join(f"{row['band']} {row['cost']}" for row in band_rows()),
            band_ratio(),
        )
        return spend

    @property
    def action_spend(self) -> Optional[ActionSpend]:
        """Read the ``ActionSpend`` this bridge installed."""
        return self._action_spend

    def install_market_rotation(
        self,
        rotation_path: Optional[Path] = None,
    ) -> MarketRotation:
        """Build the ``MarketRotation`` over this bridge's chain and load its record.

        The rotation draws from whichever chain this bridge holds, so a TestNet
        run is the same ``open_window`` path over a different ``LocalTestnet``.
        """
        from src.competition.market_rotation import MarketRotation as _Rotation

        rotation = _Rotation(self._testnet, rotation_path=rotation_path)
        rotation.load()
        self._market_rotation = rotation
        summary = rotation.rotation_summary()
        logger.info(
            "MarketRotation installed (path=%s, open windows=%d, top %d by volume, "
            "floor %d, share ceiling %s%%)",
            rotation.rotation_path,
            len(summary["open_windows"]),
            summary["top_n_by_volume"],
            summary["min_eligible_pool"],
            summary["share_ceiling_pct"],
        )
        return rotation

    @property
    def market_rotation(self) -> Optional[MarketRotation]:
        """Read the ``MarketRotation`` this bridge installed."""
        return self._market_rotation

    def install_capture_bounds(
        self,
        rotation: MarketRotation,
        bounds_path: Optional[Path] = None,
    ) -> CaptureBounds:
        """Build the ``CaptureBounds`` over this bridge's chain and ``rotation``.

        A demo run is the same ``activate`` and ``award`` path over a different
        ``LocalTestnet``.
        """
        from src.competition.capture_bounds import CaptureBounds as _Bounds

        bounds = _Bounds(self._testnet, rotation, bounds_path=bounds_path)
        bounds.load()
        self._capture_bounds = bounds
        summary = bounds.bounds_summary()
        logger.info(
            "CaptureBounds installed (path=%s, activations=%d, cooldown %d candles "
            "floored at %ds, %d scored axis minimum)",
            bounds.bounds_path,
            len(summary["activations"]),
            summary["cooldown_candles"],
            summary["cooldown_floor_s"],
            summary["min_scored_axes"],
        )
        return bounds

    @property
    def capture_bounds(self) -> Optional[CaptureBounds]:
        """Read the ``CaptureBounds`` this bridge installed."""
        return self._capture_bounds

    def install_node_link(
        self,
        peer_dir: Optional[Path] = None,
        network: Optional[str] = None,
    ) -> PoaNodeLink:
        """Build the ``PoaNodeLink`` over this bridge's chain, binding no port.

        The link shares ``_mutation_lock``, so applying a peer's records and a
        ``_CompetitionWorker`` never write the chain at once. Only
        ``start_listening`` opens a socket, and nothing here calls it.
        """
        from src.competition.node_link import DEFAULT_NETWORK, PoaNodeLink

        link = PoaNodeLink(
            self._testnet,
            self.node_id(),
            peer_dir=peer_dir,
            network=network or DEFAULT_NETWORK,
            mutation_lock=self._mutation_lock,
        )
        self._node_link = link
        logger.info(
            "PoaNodeLink installed (node=%s, peers=%s, network=%s, listening=%s)",
            link.node_id,
            link.peer_dir,
            link.network,
            link.is_listening,
        )
        return link

    @property
    def node_link(self) -> Optional[PoaNodeLink]:
        """Read the ``PoaNodeLink`` this bridge installed."""
        return self._node_link

    @staticmethod
    def node_id() -> str:
        """This node's PoA identity, or a fresh id when no key file is readable."""
        from src.competition.bot_identity import BotIdentity

        key_path = DEFAULT_PERSIST_PATH.parent / BotIdentity.KEY_FILE
        try:
            return BotIdentity(str(key_path)).load().short_id
        except Exception as e:
            node_id = f"node-{uuid.uuid4().hex[:12]}"
            logger.info(
                "no PoA identity at %s (%s), so this node is %s for as long as it runs",
                key_path,
                e,
                node_id,
            )
            return node_id

    def install_certification_socket(
        self,
        quint_ledger: QuintessenceLedger,
        socket_path: Optional[Path] = None,
    ) -> CertificationSocket:
        """Build the ``CertificationSocket`` over this bridge's chain and
        ``quint_ledger``, and load its per-bot certified-fee totals.

        The socket shares ``_mutation_lock``, so a certification and a
        ``_CompetitionWorker`` never write the chain at once.
        """
        from src.competition.certification_socket import (
            CertificationSocket as _Socket,
        )

        socket = _Socket(
            self._testnet,
            quint_ledger,
            socket_path=socket_path,
            mutation_lock=self._mutation_lock,
        )
        socket.load()
        self._certification_socket = socket
        logger.info(
            "CertificationSocket installed (path=%s, bots=%d)",
            socket_path or "default",
            len(socket.socket_summary()["bots"]),
        )
        return socket

    @property
    def certification_socket(self) -> Optional[CertificationSocket]:
        """Read the ``CertificationSocket`` this bridge installed."""
        return self._certification_socket

    @staticmethod
    def install_quint_ledger(
        ledger_path: Optional[Path] = None,
    ) -> QuintessenceLedger:
        """Return a loaded ``QuintessenceLedger``, or one that refuses every write."""
        from src.competition.quintessence_ledger import (
            QuintessenceLedger as _Ledger,
        )
        from src.competition.quintessence_ledger import (
            QuintessenceLedgerError,
        )

        ledger = _Ledger(ledger_path)
        try:
            ledger.load()
        except (QuintessenceLedgerError, OSError):
            logger.exception(
                "QuintessenceLedger at %s raised while replaying its movements",
                ledger_path or "default",
            )
        report = ledger.conservation()
        logger.info(
            "QuintessenceLedger installed (path=%s, ever minted=%s, balanced=%s)",
            ledger_path or "default",
            report.total_ever_minted,
            report.is_balanced,
        )
        return ledger

    # ── Public API ────────────────────────────────────────────────────

    @property
    def testnet(self):
        """Read the shared ``LocalTestnet``; ``request_competition`` is
        the only write path.
        """
        return self._testnet

    def request_competition(self, req: CompetitionRequest) -> None:
        """Enqueue ``req`` for ``_drain_queue``, from any thread."""
        self._queue.put(req)

    def reset(self, reason: str = "user-requested") -> None:
        """Replace the chain with a fresh ``LocalTestnet`` and unlink
        ``_persist_path``.

        Emits ``chain_reset`` with ``reason`` and then ``chain_updated``.
        """
        from src.competition.local_testnet import LocalTestnet

        with self._mutation_lock:
            self._testnet.__dict__.update(LocalTestnet().__dict__)
        try:
            if self._persist_path and self._persist_path.is_file():
                self._persist_path.unlink()
        except Exception as e:
            logger.warning("failed to delete persist file: %s", e)
        logger.info("chain reset (%s)", reason)
        self.chain_reset.emit(reason)
        self.chain_updated.emit()

    # ── Queue drain (runs on Qt main thread) ──────────────────────────

    def _drain_queue(self) -> None:
        """Start a ``_CompetitionWorker`` for the next queued request.

        Returns without dequeuing while ``_active_worker`` is still
        running.
        """
        if self._active_worker is not None and self._active_worker.isRunning():
            return
        try:
            req = self._queue.get_nowait()
        except queue.Empty:
            return
        worker = _CompetitionWorker(
            self._testnet, req, self._mutation_lock, parent=self
        )
        worker.finished_competition.connect(self._on_worker_done)
        self._active_worker = worker
        worker.start()

    def _on_worker_done(self, result: dict) -> None:
        """Clear ``_active_worker``, then emit ``competition_completed``.

        A result with no ``error`` key also schedules a save and emits
        ``chain_updated``.
        """
        self._active_worker = None
        if "error" in result:
            logger.warning("competition worker error: %s", result["error"])
        else:
            # The worker mutated the chain already, under _mutation_lock.
            self._schedule_save()
            self.chain_updated.emit()
        self.competition_completed.emit(result)

    # ── Persistence ────────────────────────────────────────────────────

    def _schedule_save(self) -> None:
        """Start ``_persist_timer``, which coalesces rapid updates into
        one ``_save_now``.
        """
        self._persist_timer.start()

    def _save_now(self) -> None:
        """Write ``_serialize_state`` to ``_persist_path`` through
        ``atomic_write_json``.

        Does nothing while ``_persist_path`` is ``None``.
        """
        if self._persist_path is None:
            return
        try:
            payload = self._serialize_state()
        except Exception as e:
            logger.warning("failed to serialize chain state: %s", e)
            return
        try:
            atomic_write_json(self._persist_path, payload, indent=2)
            logger.debug(
                "chain persisted (block=%d, txs=%d)",
                payload.get("block_number", 0),
                len(payload.get("transactions", [])),
            )
        except Exception as e:
            logger.warning("chain persist failed: %s", e)

    def _serialize_state(self) -> dict:
        """Return the ``_chain``, ``_acrv`` and ``_registry`` state as a
        JSON dict.

        ``_restore_state`` reads the same keys, and ``schema_version``
        carries ``SCHEMA_VERSION``.
        """
        chain = self._testnet._chain
        acrv = self._testnet._acrv
        registry = self._testnet._registry
        return {
            "schema_version": SCHEMA_VERSION,
            "saved_at": time.time(),
            "block_number": chain._block_number,
            "blocks": [b.to_dict() for b in chain._blocks],
            # _txs is a dict keyed by hash → preserve as list of tx dicts
            "transactions": [t.to_dict() for t in chain._txs.values()],
            "events": [e.to_dict() for e in chain._events],
            "acrv_balances": dict(acrv._balances),
            "acrv_allowances": {a: dict(b) for a, b in acrv._allowances.items()},
            "acrv_total_supply": acrv._total_supply,
            "acrv_mint_log": list(acrv._mint_log),
            "competitions": {k: v for k, v in registry._comps.items()},
        }

    def _try_load(self) -> None:
        """Fill the chain from ``_persist_path`` through ``_restore_state``.

        A ``schema_version`` other than ``SCHEMA_VERSION`` or a failed
        restore unlinks the file; unreadable JSON leaves it in place.
        """
        if self._persist_path is None or not self._persist_path.is_file():
            return
        try:
            payload = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("persisted chain unreadable (%s) — starting " "fresh", e)
            return
        ver = payload.get("schema_version")
        if ver != SCHEMA_VERSION:
            logger.warning(
                "persisted chain schema %s != current %s — discarding "
                "old chain history (wipe+warn policy)",
                ver,
                SCHEMA_VERSION,
            )
            try:
                self._persist_path.unlink()
            except Exception as e:
                logger.warning("stale chain file not removed: %s", e)
            self.chain_reset.emit(f"schema version upgrade ({ver} → {SCHEMA_VERSION})")
            return
        try:
            self._restore_state(payload)
            saved_at = payload.get("saved_at", 0)
            age_min = max(0, (time.time() - saved_at) / 60)
            logger.info(
                "chain restored from disk (block=%d, age=%.0f min)",
                payload.get("block_number", 0),
                age_min,
            )
            try:
                self._testnet.verify_integrity()
            except (TypeError, ValueError) as e:
                # A raise here must not reach the handler below, which unlinks.
                logger.warning("restored chain could not be verified: %s", e)
        except Exception as e:
            logger.warning("chain restore failed (%s) — starting fresh", e)
            # Don't leave a corrupt file in place
            try:
                self._persist_path.unlink()
            except Exception as e:
                logger.warning("corrupt chain file not removed: %s", e)

    def _restore_state(self, payload: dict) -> None:
        """Rebuild ``_chain``, ``_acrv`` and ``_registry`` from a
        ``_serialize_state`` payload.

        A missing or mismatched field raises out of ``Block``,
        ``TxRecord`` or ``ChainEvent``.
        """
        from src.competition.local_testnet import Block, TxRecord, ChainEvent

        chain = self._testnet._chain
        acrv = self._testnet._acrv
        registry = self._testnet._registry

        chain._blocks = [Block(**b) for b in payload.get("blocks", [])]
        # Restore _txs as the dict LocalChain expects: hash → TxRecord
        chain._txs = {
            t["tx_hash"]: TxRecord(**t) for t in payload.get("transactions", [])
        }
        chain._events = [ChainEvent(**e) for e in payload.get("events", [])]
        chain._block_number = payload.get("block_number", 0)

        acrv._balances = dict(payload.get("acrv_balances", {}))
        acrv._allowances = {
            a: dict(b) for a, b in payload.get("acrv_allowances", {}).items()
        }
        acrv._total_supply = int(payload.get("acrv_total_supply", 0))
        acrv._mint_log = list(payload.get("acrv_mint_log", []))

        registry._comps = dict(payload.get("competitions", {}))
