"""Shared LocalTestnet bridge.

``SharedTestnetBridge.install_on`` attaches one ``LocalTestnet``, one
``QuintessenceLedger`` and one ``PoaWorld`` to a MainWindow and starts
``_drain_queue`` on a timer. Each queued
``CompetitionRequest`` runs in a ``_CompetitionWorker``, which mutates
the chain on its own thread while it holds ``_mutation_lock``, one
worker at a time. ``_save_now`` appends every new record to the log beside
``DEFAULT_PERSIST_PATH`` and writes that path as a checkpoint once per
``CHECKPOINT_RECORD_INTERVAL`` records, and ``_try_load`` restores the
checkpoint and replays the log after it. ``_try_load`` drops a checkpoint whose
``schema_version`` is not ``SCHEMA_VERSION``.

``chain_standing`` and ``reset_chain`` build one bridge over a saved chain and
read or reset it, so a screen reaches ``reset`` without a MainWindow.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from ..core.io_utils import (
    append_json_lines,
    atomic_write_json,
    read_json_line_before,
    read_json_lines,
)

if TYPE_CHECKING:
    from src.competition.action_spend import ActionSpend
    from src.competition.capture_bounds import CaptureBounds
    from src.competition.certification_socket import CertificationSocket
    from src.competition.event_redistribution import EventRedistribution
    from src.competition.market_rotation import MarketRotation
    from src.competition.node_link import PoaNodeLink
    from src.competition.quintessence_ledger import QuintessenceLedger
    from src.competition.world_grid import PoaWorld
    from src.competition.world_movement import WorldJourneys

from PySide6.QtCore import QObject, QThread, QTimer, Signal

logger = logging.getLogger("acervator.shared_testnet")


SCHEMA_VERSION = 1

#: The reason ``_read_checkpoint`` emits when it drops a checkpoint of another schema.
SCHEMA_WIPE_REASON = "schema version upgrade ({found} → {wanted})"

DEFAULT_PERSIST_PATH = Path.home() / ".acervator" / "testnet_chain.json"
QUEUE_DRAIN_INTERVAL_MS = 250
PERSIST_DEBOUNCE_MS = 500

#: Records the log may hold past a checkpoint before ``_save_now`` writes one.
#: At the twenty layers the world budget measures, 52,420 records fill one world
#: turn, so this is about one checkpoint an hour.
CHECKPOINT_RECORD_INTERVAL = 50_000

#: One layer's byte ceiling for one world turn, which buys 2,621 records at 400 bytes.
TURN_BYTE_CAPACITY = 1_048_576

#: What one log line carries. ``state`` holds what no block, transaction or
#: event does: the token balances, the competitions and the id origin.
LOG_KINDS = ("block", "transaction", "event", "state")

#: The log sits beside the checkpoint under this suffix.
LOG_SUFFIX = ".log"


def _log_line(kind: str, record: dict, content_id: Callable[[dict], str]) -> dict:
    """Return one log line naming ``record`` by the content id of its own fields."""
    return {"kind": kind, "id": content_id(record), "record": record}


def _line_names_its_record(line: Any, content_id: Callable[[dict], str]) -> bool:
    """Answer whether ``line`` is a log line whose id is its record's content id.

    A line cut part way through never reaches here, because it does not parse;
    this refuses one that parses and no longer names what it carries.
    """
    if not isinstance(line, dict) or line.get("kind") not in LOG_KINDS:
        return False
    record = line.get("record")
    if not isinstance(record, dict):
        return False
    try:
        return line.get("id") == content_id(record)
    except ValueError:
        return False


@dataclass
class _SavePlan:
    """What one ``_save_now`` writes, and the counters it advances afterwards.

    ``_plan_save`` builds it under ``_mutation_lock`` so the file writes happen
    outside that lock against a snapshot nothing can still be mutating.
    """

    lines: list = field(default_factory=list)
    blocks: int = 0
    transactions: int = 0
    events: int = 0
    derived_state: dict = field(default_factory=dict)
    checkpoint: Optional[dict] = None


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
        self._log_path = persist_path.with_suffix(LOG_SUFFIX) if persist_path else None
        self._logged_blocks = 0
        self._logged_transactions = 0
        self._logged_events = 0
        self._log_bytes = 0
        self._log_tail_id: Optional[str] = None
        self._records_since_checkpoint = 0
        self._logged_derived_state: Optional[dict] = None
        self._queue: queue.Queue = queue.Queue()
        self._mutation_lock = threading.Lock()
        self._active_worker: Optional[_CompetitionWorker] = None
        self._certification_socket: Optional[CertificationSocket] = None
        self._market_rotation: Optional[MarketRotation] = None
        self._capture_bounds: Optional[CaptureBounds] = None
        self._node_link: Optional[PoaNodeLink] = None
        self._action_spend: Optional[ActionSpend] = None
        self._event_redistribution: Optional[EventRedistribution] = None
        self._poa_world: Optional[PoaWorld] = None
        self._poa_journeys: Optional[WorldJourneys] = None

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
        world_path: Optional[Path] = None,
        journey_path: Optional[Path] = None,
    ):
        """Create the shared ``LocalTestnet``, the bridge, the
        ``QuintessenceLedger``, the ``CertificationSocket``, the
        ``MarketRotation``, the ``CaptureBounds``, the ``PoaNodeLink``, the
        ``ActionSpend``, the ``EventRedistribution``, the ``PoaWorld`` and the
        ``WorldJourneys``, and attach all eleven to ``main_win``.

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
        main_win._market_rotation = bridge.install_market_rotation(rotation_path)
        main_win._capture_bounds = bridge.install_capture_bounds(
            main_win._market_rotation, bounds_path
        )
        main_win._certification_socket = bridge.install_certification_socket(
            ledger, socket_path, main_win._capture_bounds
        )
        main_win._node_link = bridge.install_node_link(peer_dir, network)
        main_win._action_spend = bridge.install_action_spend(
            ledger, action_store_path, event_pot_address
        )
        main_win._event_redistribution = bridge.install_event_redistribution(
            ledger, main_win._action_spend
        )
        main_win._poa_world = bridge.install_world(world_path)
        main_win._poa_journeys = bridge.install_journeys(
            main_win._poa_world, journey_path
        )
        logger.info("SharedTestnetBridge installed (persist=%s)", path)
        return bridge

    @classmethod
    def load_from(cls, persist_path: Path) -> "SharedTestnetBridge":
        """One bridge over ``persist_path``, its chain replayed and both timers stopped.

        Nothing is attached to a MainWindow, so a screen reads or resets a saved
        chain without the installed bridge.
        """
        from src.competition.local_testnet import LocalTestnet

        bridge = cls(LocalTestnet(), persist_path=persist_path)
        bridge.stand_down()
        bridge._try_load()
        return bridge

    def stand_down(self) -> None:
        """Stop ``_drain_timer`` and ``_persist_timer``, so this bridge runs nothing."""
        self._drain_timer.stop()
        self._persist_timer.stop()

    def install_event_redistribution(
        self,
        quint_ledger: QuintessenceLedger,
        action_spend: ActionSpend,
    ) -> EventRedistribution:
        """Build the ``EventRedistribution`` over the pot ``action_spend`` spends into.

        It takes that object's store and held address and this bridge's chain, so a
        demo run divides its own chain's pot through the same ``settle`` path and
        reads its own chain's certification senders.
        """
        from src.competition.event_redistribution import RETURN_PERCENT
        from src.competition.event_redistribution import (
            EventRedistribution as _Redistribution,
        )

        redistribution = _Redistribution(
            quint_ledger,
            action_spend.store,
            action_spend.held_address,
            self._testnet,
        )
        self._event_redistribution = redistribution
        logger.info(
            "EventRedistribution installed (pot=%s, return=%d%%, pot rests %s, "
            "store=%s)",
            redistribution.held_address,
            RETURN_PERCENT,
            quint_ledger.held_balance(redistribution.held_address),
            redistribution.store.store_path,
        )
        return redistribution

    @property
    def event_redistribution(self) -> Optional[EventRedistribution]:
        """Read the ``EventRedistribution`` this bridge installed."""
        return self._event_redistribution

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

    def install_world(self, world_path: Optional[Path] = None) -> PoaWorld:
        """Build the ``PoaWorld`` over this bridge's chain and read its record.

        A demo run is the same ``discover`` path over a different ``LocalTestnet``,
        and an install with no record on disk holds no world and no layer.
        """
        from src.competition.world_grid import (
            DEFAULT_GRID_WIDTH,
            SEPHIROT_LAYERS,
            addressable_squares,
        )
        from src.competition.world_grid import PoaWorld as _World

        world = _World(self._testnet, world_path=world_path)
        world.load()
        self._poa_world = world
        logger.info(
            "PoaWorld installed (path=%s, worlds=%d, default grid %d across "
            "holding %d squares, %d declared layers)",
            world.world_path,
            len(world.world_ids),
            DEFAULT_GRID_WIDTH,
            addressable_squares(DEFAULT_GRID_WIDTH),
            SEPHIROT_LAYERS,
        )
        return world

    @property
    def poa_world(self) -> Optional[PoaWorld]:
        """Read the ``PoaWorld`` this bridge installed."""
        return self._poa_world

    def install_journeys(
        self, world: PoaWorld, journey_path: Optional[Path] = None
    ) -> WorldJourneys:
        """Build the ``WorldJourneys`` over this bridge's chain and ``world``.

        A demo run is the same ``open_leg`` path over a different ``LocalTestnet``,
        and an install with no record on disk holds no journey and no leg.
        """
        from src.competition.world_movement import BASE_STEPS_PER_TURN
        from src.competition.world_movement import WorldJourneys as _Journeys

        journeys = _Journeys(self._testnet, world, journey_path=journey_path)
        journeys.load()
        self._poa_journeys = journeys
        logger.info(
            "WorldJourneys installed (path=%s, worlds=%d, base %d steps a turn)",
            journeys.journey_path,
            len(journeys.world_ids),
            BASE_STEPS_PER_TURN,
        )
        return journeys

    @property
    def poa_journeys(self) -> Optional[WorldJourneys]:
        """Read the ``WorldJourneys`` this bridge installed."""
        return self._poa_journeys

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
        capture_bounds: Optional[CaptureBounds] = None,
    ) -> CertificationSocket:
        """Build the ``CertificationSocket`` over this bridge's chain,
        ``quint_ledger`` and ``capture_bounds``, and load its certified-fee totals.

        The socket shares ``_mutation_lock`` with ``_CompetitionWorker`` and with
        ``CaptureBounds.award``, so only one of them writes the chain at a time.
        """
        from src.competition.certification_socket import (
            CertificationSocket as _Socket,
        )

        socket = _Socket(
            self._testnet,
            quint_ledger,
            socket_path=socket_path,
            mutation_lock=self._mutation_lock,
            capture_bounds=capture_bounds or self._capture_bounds,
        )
        socket.load()
        self._certification_socket = socket
        summary = socket.socket_summary()
        logger.info(
            "CertificationSocket installed (path=%s, bots=%d, awards bounded=%s)",
            socket_path or "default",
            len(summary["bots"]),
            summary["awards_bounded"],
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
        """Replace the chain with a fresh ``LocalTestnet`` and unlink both files.

        The checkpoint at ``_persist_path`` and the log at ``_log_path`` go
        together: a log kept past a reset would replay the history the reset
        dropped. Emits ``chain_reset`` with ``reason`` and then ``chain_updated``.
        """
        from src.competition.local_testnet import LocalTestnet

        with self._mutation_lock:
            self._testnet.__dict__.update(LocalTestnet().__dict__)
        self._logged_blocks = 0
        self._logged_transactions = 0
        self._logged_events = 0
        self._log_bytes = 0
        self._log_tail_id = None
        self._records_since_checkpoint = 0
        self._logged_derived_state = None
        for path in (self._persist_path, self._log_path):
            try:
                if path and path.is_file():
                    path.unlink()
            except Exception as e:
                logger.warning("failed to delete %s: %s", path, e)
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
        """Append every record the log does not hold, then checkpoint when due.

        Does nothing while ``_persist_path`` is ``None``. Re-arms
        ``_persist_timer`` and returns while another thread holds
        ``_mutation_lock``, so an append never reads a record a worker is still
        writing. The append costs the new records only; the checkpoint costs the
        whole chain and fires once per ``CHECKPOINT_RECORD_INTERVAL`` records.
        """
        if self._persist_path is None or self._log_path is None:
            return
        try:
            plan = self._plan_save()
        except Exception as e:
            logger.warning("failed to serialize chain state: %s", e)
            return
        if plan is None:
            self._persist_timer.start()
            return
        if plan.lines and not self._append_log(plan):
            return
        if plan.checkpoint is not None:
            self._write_checkpoint(plan)

    def _plan_save(self) -> Optional[_SavePlan]:
        """Snapshot the lines to append and the checkpoint to write, or ``None``.

        Takes ``_mutation_lock`` without waiting and returns ``None`` when it
        cannot, so a mutation in progress defers the save rather than being read
        half written. The file writes happen after the release.
        """
        from src.competition.local_testnet import content_id

        if not self._mutation_lock.acquire(blocking=False):
            return None
        started = time.perf_counter()
        try:
            chain = self._testnet._chain
            transactions = list(chain._txs.values())
            lines = [
                _log_line("block", b.to_dict(), content_id)
                for b in chain._blocks[self._logged_blocks :]
            ]
            lines += [
                _log_line("transaction", t.to_dict(), content_id)
                for t in transactions[self._logged_transactions :]
            ]
            lines += [
                _log_line("event", e.to_dict(), content_id)
                for e in chain._events[self._logged_events :]
            ]
            derived_state = self._derived_state()
            if derived_state != self._logged_derived_state:
                lines.append(_log_line("state", derived_state, content_id))
            due = (
                self._records_since_checkpoint + len(lines)
                >= CHECKPOINT_RECORD_INTERVAL
            )
            plan = _SavePlan(
                lines=lines,
                blocks=len(chain._blocks),
                transactions=len(transactions),
                events=len(chain._events),
                derived_state=derived_state,
                checkpoint=self._serialize_state() if due else None,
            )
        finally:
            self._mutation_lock.release()
        logger.debug(
            "chain save planned (records=%d, checkpoint=%s, ms=%.1f)",
            len(plan.lines),
            plan.checkpoint is not None,
            (time.perf_counter() - started) * 1000,
        )
        return plan

    def _append_log(self, plan: _SavePlan) -> bool:
        """Append ``plan.lines`` to ``_log_path`` and advance what the log holds.

        Returns False when the append raised, leaving every counter as it was so
        the next ``_save_now`` offers the same records again.
        """
        started = time.perf_counter()
        try:
            written = append_json_lines(self._log_path, plan.lines)
        except Exception as e:
            logger.warning("chain log append failed: %s", e)
            return False
        self._logged_blocks = plan.blocks
        self._logged_transactions = plan.transactions
        self._logged_events = plan.events
        self._logged_derived_state = plan.derived_state
        self._log_bytes += written
        self._log_tail_id = plan.lines[-1]["id"]
        self._records_since_checkpoint += len(plan.lines)
        logger.debug(
            "chain log appended (records=%d, bytes=%d, log bytes=%d, ms=%.1f)",
            len(plan.lines),
            written,
            self._log_bytes,
            (time.perf_counter() - started) * 1000,
        )
        return True

    def _write_checkpoint(self, plan: _SavePlan) -> None:
        """Write ``plan.checkpoint`` over ``_persist_path`` with ``atomic_write_json``.

        That call stages a temp file, fsyncs it and renames it, so a reader never
        sees half a checkpoint and a failed write leaves the previous one whole.
        ``_append_log`` has already run, so ``_log_bytes`` and ``_log_tail_id``
        name the log position this checkpoint absorbs.
        """
        started = time.perf_counter()
        plan.checkpoint["log_bytes"] = self._log_bytes
        plan.checkpoint["log_tail_id"] = self._log_tail_id
        try:
            path = atomic_write_json(self._persist_path, plan.checkpoint, indent=2)
        except Exception as e:
            logger.warning("chain checkpoint failed: %s", e)
            return
        self._records_since_checkpoint = 0
        logger.info(
            "chain checkpoint written (block=%d, txs=%d, log bytes absorbed=%d, "
            "bytes=%d, ms=%.1f)",
            plan.checkpoint.get("block_number", 0),
            len(plan.checkpoint.get("transactions", [])),
            self._log_bytes,
            path.stat().st_size,
            (time.perf_counter() - started) * 1000,
        )

    def _derived_state(self) -> dict:
        """Return the state no block, transaction or event on the log carries.

        ``_restore_derived_state`` reads the same keys, from a checkpoint or from
        the log's last ``state`` record, so both load paths reach one state.
        """
        acrv = self._testnet._acrv
        registry = self._testnet._registry
        return {
            "content_ids_from_block": self._testnet._chain.content_id_from_block,
            "acrv_balances": dict(acrv._balances),
            "acrv_allowances": {a: dict(b) for a, b in acrv._allowances.items()},
            "acrv_total_supply": acrv._total_supply,
            "acrv_mint_log": list(acrv._mint_log),
            "competitions": {k: v for k, v in registry._comps.items()},
        }

    def _serialize_state(self) -> dict:
        """Return the whole chain as the checkpoint payload ``_restore_state`` reads.

        ``_write_checkpoint`` adds ``log_bytes`` and ``log_tail_id`` to it after the
        append that this payload covers.
        """
        chain = self._testnet._chain
        return {
            "schema_version": SCHEMA_VERSION,
            "saved_at": time.time(),
            "block_number": chain._block_number,
            "blocks": [b.to_dict() for b in chain._blocks],
            # _txs is a dict keyed by hash → preserve as list of tx dicts
            "transactions": [t.to_dict() for t in chain._txs.values()],
            "events": [e.to_dict() for e in chain._events],
            **self._derived_state(),
        }

    def _try_load(self) -> None:
        """Fill the chain from the checkpoint, then replay the log after it.

        The log decides. A checkpoint naming a last log record the log does not
        carry is ignored and the whole log replayed instead. A checkpoint that
        absorbed no log bytes is the only source for the records it holds, which is
        how a whole-file chain written before the log loads. A failed restore
        unlinks the checkpoint.
        """
        started = time.perf_counter()
        payload = self._read_checkpoint()
        start = self._confirmed_log_start(payload) if payload is not None else 0
        if start is None:
            payload = None
            start = 0
        lines, log_end = self._read_log(start)
        if payload is None and not lines:
            return
        chain = self._testnet._chain
        try:
            if payload is not None:
                self._restore_state(payload)
            else:
                chain._blocks = []
                chain._txs = {}
                chain._events = []
            self._replay_log(lines)
            if lines:
                chain._block_number = chain._blocks[-1].number if chain._blocks else 0
                chain.reindex_placements()
            self._logged_blocks = len(chain._blocks)
            self._logged_transactions = len(chain._txs)
            self._logged_events = len(chain._events)
            self._log_bytes = log_end
            self._log_tail_id = (
                lines[-1]["id"] if lines else (payload or {}).get("log_tail_id")
            )
            self._records_since_checkpoint = len(lines)
            self._logged_derived_state = self._derived_state()
            saved_at = self._saved_at(payload)
            logger.info(
                "chain restored from disk (block=%d, log records replayed=%d, "
                "log bytes=%d, age=%.0f min, ms=%.1f)",
                chain.block_number,
                len(lines),
                log_end,
                max(0, (time.time() - saved_at) / 60) if saved_at else 0,
                (time.perf_counter() - started) * 1000,
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
                if self._persist_path is not None:
                    self._persist_path.unlink()
            except Exception as e:
                logger.warning("corrupt chain file not removed: %s", e)

    def _saved_at(self, payload: Optional[dict]) -> float:
        """When the state now loading was written, by the checkpoint or the log."""
        stamp = float((payload or {}).get("saved_at") or 0.0)
        if stamp or self._log_path is None or not self._log_path.is_file():
            return stamp
        return self._log_path.stat().st_mtime

    def _read_log(self, start: int) -> tuple[list, int]:
        """Return the whole log lines after byte ``start``, and where they end.

        A line counts only when it parses and still names its own record, so a write
        cut part way through contributes nothing; the bytes after the last counted
        line are dropped, because an append onto them would produce a line no load
        can read. The lines before ``start`` are not read at all: the checkpoint
        that named that offset already holds them.
        """
        from src.competition.local_testnet import content_id

        if self._log_path is None or not self._log_path.is_file():
            return [], start
        started = time.perf_counter()
        try:
            lines, end = read_json_lines(
                self._log_path,
                start=start,
                accept=lambda line: _line_names_its_record(line, content_id),
            )
            size = self._log_path.stat().st_size
        except OSError as e:
            logger.warning("chain log unreadable (%s) — replaying none of it", e)
            return [], start
        logger.info(
            "chain log read %d whole records from byte %d of %d (ms=%.1f)",
            len(lines),
            start,
            size,
            (time.perf_counter() - started) * 1000,
        )
        if size > end:
            logger.warning(
                "chain log carries %d bytes past its %d whole records, which no "
                "load can read — dropping them",
                size - end,
                len(lines),
            )
            try:
                os.truncate(self._log_path, end)
            except OSError as e:
                logger.warning("incomplete chain log tail not removed: %s", e)
        return lines, end

    def _confirmed_log_start(self, payload: dict) -> Optional[int]:
        """Return the byte the log continues ``payload`` from, or ``None``.

        ``None`` means the log carries a different record where the checkpoint
        names ``log_tail_id``, and the log is the history; a log too short to reach
        that offset holds nothing the checkpoint does not, so it is emptied and the
        checkpoint stands.
        """
        end = int(payload.get("log_bytes", 0))
        if end <= 0 or self._log_path is None or not self._log_path.is_file():
            return 0
        if self._log_path.stat().st_size < end:
            logger.warning(
                "chain log is shorter than the %d bytes this checkpoint absorbed, "
                "so it carries nothing the checkpoint does not — emptying it",
                end,
            )
            try:
                os.truncate(self._log_path, 0)
            except OSError as e:
                logger.warning("short chain log not emptied: %s", e)
            return 0
        standing = read_json_line_before(self._log_path, end)
        if isinstance(standing, dict) and standing.get("id") == payload.get(
            "log_tail_id"
        ):
            return end
        logger.warning(
            "checkpoint absorbed %d log bytes and names %s as the last record "
            "there, which the log does not carry — replaying the log instead, "
            "because the log is the history",
            end,
            payload.get("log_tail_id"),
        )
        return None

    def _read_checkpoint(self) -> Optional[dict]:
        """Return the checkpoint payload at ``_persist_path``, or ``None``.

        A ``schema_version`` other than ``SCHEMA_VERSION`` unlinks the file under
        the wipe-and-warn policy, and unreadable JSON leaves it in place and hands
        the load to the log.
        """
        if self._persist_path is None or not self._persist_path.is_file():
            return None
        try:
            payload = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(
                "persisted checkpoint unreadable (%s) — replaying the log " "instead",
                e,
            )
            return None
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
            self.chain_reset.emit(
                SCHEMA_WIPE_REASON.format(found=ver, wanted=SCHEMA_VERSION)
            )
            return None
        return payload

    def _replay_log(self, lines: list) -> None:
        """Apply ``lines`` to the chain in the order they were appended."""
        from src.competition.local_testnet import Block, ChainEvent, TxRecord

        chain = self._testnet._chain
        for line in lines:
            kind = line["kind"]
            record = line["record"]
            if kind == "block":
                chain._blocks.append(Block(**record))
            elif kind == "transaction":
                tx = TxRecord(**record)
                chain._txs[tx.tx_hash] = tx
            elif kind == "event":
                chain._events.append(ChainEvent(**record))
            else:
                self._restore_derived_state(
                    record, int(record["content_ids_from_block"])
                )

    def _restore_state(self, payload: dict) -> None:
        """Rebuild ``_chain``, ``_acrv`` and ``_registry`` from a checkpoint payload.

        A missing or mismatched field raises out of ``Block``, ``TxRecord`` or
        ``ChainEvent``. A payload with no ``content_ids_from_block`` marks every
        record it carries legacy.
        """
        from src.competition.local_testnet import Block, ChainEvent, TxRecord

        chain = self._testnet._chain
        chain._blocks = [Block(**b) for b in payload.get("blocks", [])]
        # Restore _txs as the dict LocalChain expects: hash → TxRecord
        chain._txs = {
            t["tx_hash"]: TxRecord(**t) for t in payload.get("transactions", [])
        }
        chain._events = [ChainEvent(**e) for e in payload.get("events", [])]
        chain._block_number = payload.get("block_number", 0)
        chain.reindex_placements()
        self._restore_derived_state(
            payload,
            int(payload.get("content_ids_from_block", chain._block_number + 1)),
        )

    def _restore_derived_state(self, state: dict, content_ids_from_block: int) -> None:
        """Fill the token, registry and id-origin state from ``state``.

        A checkpoint payload and a log ``state`` record carry the same keys, so
        restoring either reaches the same balances and competitions.
        """
        acrv = self._testnet._acrv
        registry = self._testnet._registry
        self._testnet._chain.set_content_id_from_block(content_ids_from_block)
        acrv._balances = dict(state.get("acrv_balances", {}))
        acrv._allowances = {
            a: dict(b) for a, b in state.get("acrv_allowances", {}).items()
        }
        acrv._total_supply = int(state.get("acrv_total_supply", 0))
        acrv._mint_log = list(state.get("acrv_mint_log", []))
        registry._comps = dict(state.get("competitions", {}))


def chain_bytes(persist_path: Optional[Path]) -> int:
    """The bytes the checkpoint at ``persist_path`` and its ``LOG_SUFFIX`` log hold.

    Each file's own length as the file system records it, which is what
    ``_write_checkpoint`` and ``_append_log`` wrote; no record is parsed.
    """
    if persist_path is None:
        return 0
    total = 0
    for path in (persist_path, persist_path.with_suffix(LOG_SUFFIX)):
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _standing(bridge: SharedTestnetBridge, persist_path: Path, reasons: list) -> dict:
    """The chain's own stats, the bytes its files hold, and the ``reasons`` emitted."""
    stats = bridge.testnet.get_competition_stats()
    return {
        "block_height": int(stats["block_number"]),
        "transactions": int(stats["total_transactions"]),
        "events": int(stats["total_events"]),
        "bytes": chain_bytes(persist_path),
        "reasons": list(reasons),
    }


def chain_standing(persist_path: Path) -> dict:
    """What the saved chain at ``persist_path`` holds, read through one loaded bridge."""
    return _standing(SharedTestnetBridge.load_from(persist_path), persist_path, [])


def reset_chain(persist_path: Path, reason: str) -> dict:
    """Reset the chain at ``persist_path`` through ``SharedTestnetBridge.reset``.

    The returned ``reasons`` carry what ``chain_reset`` emitted, which is what tells
    a deliberate reset from the schema wipe raising the same signal.
    """
    bridge = SharedTestnetBridge.load_from(persist_path)
    reasons: list = []
    bridge.chain_reset.connect(reasons.append)
    bridge.reset(reason)
    return _standing(bridge, persist_path, reasons)
