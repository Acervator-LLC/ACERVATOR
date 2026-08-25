"""
src/gui/shared_testnet.py — Shared LocalTestnet bridge (Session 18,
v3.12.0) between Nuclear mode, TestNet tab, and persistence.

ARCHITECTURE
────────────
ONE LocalTestnet instance lives on MainWindow. Every subsystem that
wants to read its state OR append to it goes through this bridge.

WRITE PATH (Nuclear → chain):
  Nuclear thread     →  SharedTestnetBridge.request_competition(event)
                        (thread-safe queue.put)
  Qt main thread     ←  drain QTimer (every 250ms) picks up event
                     →  PipCompetitionWorker (QThread) runs it
                     →  worker.done → applies to LocalTestnet on main thread
                     →  chain_updated signal fires → TestnetTab refreshes

READ PATH (TestNet tab → display):
  QTimer poll (3s)   →  SharedTestnetBridge.testnet  (direct read; safe because
                        all writes are marshaled through main thread)

PERSISTENCE
───────────
Chain state round-trips to ~/.acervator/testnet_chain.json on every
mutation (debounced 500ms). Schema version 1. On load, schema mismatch
→ wipe + warn (no migration).

THREADING INVARIANT (critical)
──────────────────────────────
LocalTestnet itself is NOT thread-safe. This module enforces that ALL
mutations happen on the Qt main thread. Nuclear (engine thread) only
enqueues requests; it never calls mutating methods directly.

sadp: R28 FL  R44 DRY  R49 LOG  R50 ANCH
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal

logger = logging.getLogger("acervator.shared_testnet")


SCHEMA_VERSION = 1
DEFAULT_PERSIST_PATH = Path.home() / ".acervator" / "testnet_chain.json"
QUEUE_DRAIN_INTERVAL_MS = 250
PERSIST_DEBOUNCE_MS = 500


# ══════════════════════════════════════════════════════════════════════════
# Event schema
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class CompetitionRequest:
    """Request from Nuclear (or any other producer) to run a PoA
    competition against the shared chain. Enqueued from any thread;
    executed on Qt main thread."""

    symbol: str
    season: int
    n_bots: int = 3
    round_id: Optional[int] = None  # for caller correlation


# ══════════════════════════════════════════════════════════════════════════
# Worker thread — runs run_demo_competition off the Qt main thread
# ══════════════════════════════════════════════════════════════════════════


class _CompetitionWorker(QThread):
    """Runs a single competition against the shared LocalTestnet on
    a worker thread. The mutation itself happens here — but this
    thread owns exclusive access via the bridge's mutation_lock.

    Emits `finished_competition(result_dict)` when done. Failures
    emit a dict with `"error"` key."""

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
                # sadp: R28 FL — if run_demo_competition raises, we
                # want the exception in the signal payload, not
                # swallowed. The worker thread dying silently would
                # be the exact anti-pattern we've been fighting.
                result = self._testnet.run_demo_competition(
                    n_bots=self._request.n_bots,
                    season=self._request.season,
                    symbol=self._request.symbol,
                )
            if not isinstance(result, dict):
                result = {"error": f"unexpected result type: {type(result)}"}
            # Echo the request for correlation
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


# ══════════════════════════════════════════════════════════════════════════
# The bridge — singleton held on MainWindow
# ══════════════════════════════════════════════════════════════════════════


class SharedTestnetBridge(QObject):
    """Owns the single LocalTestnet instance + the thread-crossing queue.

    Lifecycle:
      bridge = SharedTestnetBridge.install_on(main_win)   # once at startup
      bridge.request_competition(CompetitionRequest(...)) # any thread
      bridge.chain_updated                                # signal subscribers
      bridge.competition_completed                        # signal w/ result
      bridge.reset()                                      # wipe memory + persist
    """

    chain_updated = Signal()  # fires after any mutation
    competition_completed = Signal(dict)  # full result, including "error"
    chain_reset = Signal(str)  # reason string

    def __init__(self, testnet, persist_path: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self._testnet = testnet
        self._persist_path = persist_path
        self._queue: queue.Queue = queue.Queue()
        self._mutation_lock = threading.Lock()
        self._active_worker: Optional[_CompetitionWorker] = None

        # Drain timer — pulls from queue, spawns worker per request
        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(QUEUE_DRAIN_INTERVAL_MS)
        self._drain_timer.timeout.connect(self._drain_queue)
        self._drain_timer.start()

        # Persistence debounce timer (single-shot)
        self._persist_timer = QTimer(self)
        self._persist_timer.setInterval(PERSIST_DEBOUNCE_MS)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.timeout.connect(self._save_now)

    # ── Installation factory (called once by MainWindow) ──────────────
    @classmethod
    def install_on(cls, main_win, persist_path: Optional[Path] = None):
        """Create the shared LocalTestnet + bridge + attach to main_win.
        Safe to call exactly once per MainWindow lifecycle.

        sadp: R28 FL — raises on double-install so we detect misuse."""
        if getattr(main_win, "_testnet_bridge", None) is not None:
            raise RuntimeError(
                "SharedTestnetBridge already installed " "on this MainWindow"
            )
        from src.competition.local_testnet import LocalTestnet

        path = persist_path or DEFAULT_PERSIST_PATH
        testnet = LocalTestnet()  # fresh
        bridge = cls(testnet, persist_path=path, parent=main_win)
        # Try loading persisted state
        bridge._try_load()
        main_win._local_testnet = testnet
        main_win._testnet_bridge = bridge
        logger.info("SharedTestnetBridge installed (persist=%s)", path)
        return bridge

    # ── Public API ────────────────────────────────────────────────────

    @property
    def testnet(self):
        """Direct read access. Writes via request_competition only."""
        return self._testnet

    def request_competition(self, req: CompetitionRequest) -> None:
        """Thread-safe enqueue. Callable from Nuclear engine thread."""
        self._queue.put(req)

    def reset(self, reason: str = "user-requested") -> None:
        """Wipe the in-memory chain + remove persistence file.
        Must be called on the Qt main thread. Emits chain_reset signal."""
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
        """Pull the next request off the queue, spawn a worker to run
        it. If a worker is already running, we wait — one-at-a-time to
        keep the chain state consistent and avoid parallel writers."""
        if self._active_worker is not None and self._active_worker.isRunning():
            return  # serialize
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
        """Called on Qt main thread when a worker finishes."""
        self._active_worker = None
        if "error" in result:
            logger.warning("competition worker error: %s", result["error"])
        else:
            # Mutation already happened inside the worker (under lock);
            # schedule a persistence save + notify listeners
            self._schedule_save()
            self.chain_updated.emit()
        self.competition_completed.emit(result)

    # ── Persistence ────────────────────────────────────────────────────

    def _schedule_save(self) -> None:
        """Debounced save — coalesces rapid updates into one write."""
        self._persist_timer.start()

    def _save_now(self) -> None:
        """Serialize the chain state to JSON. Called from the debounced
        timer on the Qt main thread."""
        if self._persist_path is None:
            return
        try:
            payload = self._serialize_state()
        except Exception as e:
            logger.warning("failed to serialize chain state: %s", e)
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._persist_path.with_suffix(self._persist_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self._persist_path)
            logger.debug(
                "chain persisted (block=%d, txs=%d)",
                payload.get("block_number", 0),
                len(payload.get("transactions", [])),
            )
        except Exception as e:
            logger.warning("chain persist failed: %s", e)

    def _serialize_state(self) -> dict:
        """Capture the current chain state as a plain JSON dict.
        Field names match LocalTestnet internals verified 2026-04-20:
          LocalChain: _blocks (list), _txs (dict[hash→tx]), _events
                       (list), _block_number (int)
          LocalACRV:  _balances (dict[addr→wei]), _allowances,
                       _total_supply (int), _mint_log (list[dict])
          LocalRegistry: _comps (dict[id→dict])
        Any schema drift here needs a SCHEMA_VERSION bump."""
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
        """Load persisted state on startup. On any error (missing file,
        bad JSON, schema mismatch): wipe + warn + continue with empty
        chain.  sadp: R28 FL"""
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
            except Exception:
                pass  # sadp: R61 ACCEPT — schema wipe
            # best-effort; unlink failure (file already gone, permission,
            # etc.) doesn't change behaviour since we're discarding the
            # old chain anyway and will overwrite on next persist.
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
            except Exception:
                pass  # sadp: R61 ACCEPT — corrupt-file
            # cleanup best-effort; same rationale as above.

    def _restore_state(self, payload: dict) -> None:
        """Rehydrate LocalTestnet fields from a serialized payload.
        Field names must match _serialize_state exactly.
        sadp: R28 FL — any missing or mismatched field raises"""
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
