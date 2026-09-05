"""Shared LocalTestnet bridge.

``SharedTestnetBridge.install_on`` attaches one ``LocalTestnet`` to a
MainWindow and starts ``_drain_queue`` on a timer. Each queued
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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from ..core.io_utils import atomic_write_json

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
    def install_on(cls, main_win, persist_path: Optional[Path] = None):
        """Create the shared ``LocalTestnet`` and bridge, and attach both
        to ``main_win``.

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
        logger.info("SharedTestnetBridge installed (persist=%s)", path)
        return bridge

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
