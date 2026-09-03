"""Nuclear Mode: loop the bot_state fleet over Stone Tablet history.

A soak test. It repeats the fleet over the tablet window until stopped,
varying market structure and machine load between cycles, and records
each cycle so a failure appearing late can be traced back.

Each cycle drives ``FleetReplayController``, which already owns fleet
loading, the sim exchange, real ``ScrummingBot.tick()`` on an isolated
bus and master-clock timestamps.

``SystemLoadOscillator`` supplies the load pulse: a 120 s cycle of 45 s
cosine ramp up, 30 s sustain at 4x and 45 s ramp down, capped at 1.5x
while its COOLING regime is active. Per-cycle jitter varies successive
cycles without breaking the ramp. Machine load is sampled through
psutil; with psutil absent the oscillator gets no sensor and the
multiplier is capped at ``UNSENSED_LOAD_CAP``, because the pulse shares
a machine with the live trading engine.

Stone Tablets are READ ONLY throughout.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("acervator.nuclear_fleet")

WORKER_WAIT_CAP_S = 900.0
"""Seconds to wait for one worker fleet before abandoning the wait.

Bounds the wait so a controller that never sets ``stopped_event``
degrades to a logged anomaly instead of holding the asyncio loop the
GUI and live trading share.
"""

DEFAULT_NOISE_SEED = 0xACE12A7
"""Base seed for per-cycle market-structure noise.

Fixed, so a soak replays the same market structure on a re-run. Cycles
differ because the cycle index is mixed into this base, not because the
base changes. ``seed=`` overrides it.
"""

DEFAULT_CYCLE_CANDLES = 3000
"""Candles per cycle.

Short enough that load oscillation is observable across cycles, long
enough for scrum/fold cycles to complete repeatedly.
"""

UNSENSED_LOAD_CAP = 1.5
"""Multiplier ceiling when machine load cannot be sampled.

Matches ``SystemLoadOscillator.COOLING_CAP``.
"""

_NOISE_PCT = 0.15
"""Jitter fraction applied to each cycle's load multiplier."""


@dataclass
class NuclearCycle:
    """One pass of the fleet over the tablet window."""

    index: int
    started_at: float = 0.0
    elapsed_s: float = 0.0
    candles_played: int = 0
    trades_fired: int = 0
    exceptions: int = 0
    load_multiplier: float = 1.0
    load_at_start: float = 1.0
    workers: int = 1
    # Intensity is depth per tick times tick rate, not fleet count.
    candles_per_tick: float = 0.0
    cooling: bool = False
    error: str = ""
    # Amplitude of the market-structure noise this cycle ran against.
    noise_pct: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.error

    def to_dict(self) -> dict:
        return {
            "cycle": self.index,
            "elapsed_s": round(self.elapsed_s, 2),
            "candles_played": self.candles_played,
            "trades_fired": self.trades_fired,
            "exceptions": self.exceptions,
            "load_multiplier": round(self.load_multiplier, 3),
            "workers": self.workers,
            "cooling": self.cooling,
            "noise_pct": round(self.noise_pct, 4),
            "error": self.error,
            "candles_per_s": (
                round(self.candles_played / self.elapsed_s, 2)
                if self.elapsed_s > 0
                else None
            ),
        }


@dataclass
class NuclearState:
    """Live status for the GUI panel."""

    running: bool = False
    started_at: float = 0.0
    cycles_completed: int = 0
    total_candles: int = 0
    total_trades: int = 0
    total_exceptions: int = 0
    current_cycle: int = 0
    # Noise amplitude of the cycle now running; the GUI polls state.
    noise_pct: float = 0.0
    load_multiplier: float = 1.0
    cooling: bool = False
    fleet_size: int = 0
    symbols: int = 0
    last_error: str = ""
    stop_requested: bool = False
    cycles: list = field(default_factory=list)

    @property
    def uptime_s(self) -> float:
        return time.monotonic() - self.started_at if self.running else 0.0


def _make_oscillator():
    """Build the load oscillator with a real sensor when possible.

    Returns ``(oscillator, sensed)``. ``sensed`` is False when machine
    load cannot be read, and the caller must then cap the multiplier —
    see ``UNSENSED_LOAD_CAP``.
    """
    from src.core.system_load_oscillator import SystemLoadOscillator

    sensor = None
    sensed = False
    try:
        import psutil  # type: ignore[import-untyped]

        class _Sensor:
            """SystemLoadMR-shaped probe for ``SystemLoadOscillator``.

            Its ``_monitor_loop`` calls ``sample(now)`` at 5 Hz and then
            reads the ``current_regime`` ATTRIBUTE, so both must exist
            or COOLING never engages.
            """

            def __init__(self) -> None:
                self.current_regime = "CALM"

            def sample(self, _now: float) -> None:
                cpu = psutil.cpu_percent(interval=None)
                if cpu >= 92.0:
                    self.current_regime = "CRITICAL"
                elif cpu >= 78.0:
                    self.current_regime = "STRESS"
                else:
                    self.current_regime = "CALM"

        # The first call returns 0.0; prime it so samples are real.
        psutil.cpu_percent(interval=None)
        sensor = _Sensor()
        sensed = True
    except ImportError:
        logger.warning(
            "nuclear: psutil unavailable — machine load cannot be "
            "sampled, so the load multiplier is capped at %.1fx. An "
            "unmonitored 4x pulse shares this machine with the live "
            "trading engine.",
            UNSENSED_LOAD_CAP,
        )
    return SystemLoadOscillator(sensor), sensed


class NuclearFleetController:
    """Loops the bot_state fleet over Stone Tablet history until stopped.

    GUI-agnostic: all operator-visible output goes through the callbacks,
    so this is testable without Qt.
    """

    def __init__(
        self,
        *,
        cycle_candles: int = DEFAULT_CYCLE_CANDLES,
        activity_cb: Optional[Callable[[str], None]] = None,
        perf_cb: Optional[Callable[[str], None]] = None,
        max_cycles: Optional[int] = None,
        load_oscillation: bool = True,
        seed: Optional[int] = None,
        noise_enabled: bool = True,
    ) -> None:
        self._cycle_candles = max(120, int(cycle_candles))
        self._activity = activity_cb or (lambda _m: None)
        self._perf = perf_cb or (lambda _m: None)
        self._max_cycles = max_cycles
        self._load_oscillation = bool(load_oscillation)
        self._rng = random.Random(seed)  # noqa: S311 - not cryptographic
        # Market-structure noise, distinct from the load oscillator.
        self._noise_enabled = bool(noise_enabled)
        # A fixed base, not self._rng, so cycle N reproduces whatever
        # jitter draws preceded it.
        self._noise_seed_base = DEFAULT_NOISE_SEED if seed is None else int(seed)
        self.state = NuclearState()
        self._task: Optional[asyncio.Task] = None
        self._osc = None
        self._sensed = False
        self._configs: list[dict] = []
        # bot_state's top-level `smart_wires`, loaded in prepare().
        self._smart_wires: list[dict] = []
        self._candles: dict[str, list] = {}
        # Child fleets of the current cycle, so request_stop() can fan
        # out; _run_cycle drains this in a finally.
        self._live_fleets: list = []
        self._log = None
        # Declared up front so a feature that never runs reports
        # UNVERIFIED instead of being absent from the report.
        self._verifier = None
        # Checks that bus payloads carry the fields consumers read, so
        # a producer/consumer key rename becomes visible.
        self._emit_obs = None
        # Market Inspector proposals to inject. Empty leaves the fleet's
        # own bot_state wires standing.
        self._topologies: list = []
        self._wire_pct = 10.0
        # Simulator Swarm row callbacks, held as plain callables so this
        # controller stays GUI-agnostic.
        self._swarm_register = None
        self._swarm_update = None
        self._swarm_stop = None
        self.stopped_event = asyncio.Event()
        self.stopped_event.set()

    def set_topologies(self, proposals: list, wire_pct: float = 10.0) -> None:
        """Stress these Market Inspector proposals instead of a ring."""
        self._topologies = list(proposals or [])
        self._wire_pct = float(wire_pct)

    def set_swarm_hooks(self, register=None, update=None, stop=None) -> None:
        """Install the Simulator Swarm row callbacks.

        ``register``, ``update`` and ``stop`` map to the swarm's
        ``register_sim_run`` / ``update_sim_run`` / ``stop_sim_run``.
        """
        self._swarm_register = register
        self._swarm_update = update
        self._swarm_stop = stop

    def prepare(self) -> bool:
        """Load the fleet and its tablet history.

        Returns False with an operator-readable reason rather than
        raising, so the panel can report why a run did not start.
        """
        from .fleet import bot_state_loader as _loader

        try:
            self._configs = _loader.load_bot_configs_from_state()
            # Loaded here, not in the panel, so a run cannot start
            # without the fleet's own wires.
            self._smart_wires = _loader.load_smart_wires_from_state()
        except (OSError, ValueError) as exc:
            self._activity(f"Nuclear: could not read bot_state — {exc}")
            return False
        if not self._configs:
            self._activity(
                "Nuclear: bot_state has no scrumming bots — nothing to " "stress."
            )
            return False

        symbols = sorted(
            {str(c.get("symbol", "") or "") for c in self._configs if c.get("symbol")}
        )
        self._candles = self._load_tablet_series(symbols)
        if not self._candles:
            self._activity(
                "Nuclear: no Stone Tablet history for any fleet symbol. "
                "Build the archive before running."
            )
            return False

        self.state.fleet_size = len(self._configs)
        self.state.symbols = len(self._candles)
        missing = len(symbols) - len(self._candles)
        self._activity(
            f"Nuclear: fleet {len(self._configs)} bot(s), "
            f"{len(self._candles)} symbol(s) with tablet history"
            + (f"; {missing} symbol(s) have none and are excluded" if missing else "")
        )
        return True

    def _load_tablet_series(self, symbols: list[str]) -> dict[str, list]:
        """Read tablet candles for each fleet symbol. READ ONLY."""
        from src.trading.stone_tablets import get_registry
        from src.trading.stone_tablets.fetcher import YTD_START_MS

        reg = get_registry()
        now_ms = int(time.time() * 1000)
        out: dict[str, list] = {}
        for sym in symbols:
            asset = sym.split("/", 1)[0].upper()
            try:
                rows = reg.get_candles(asset, YTD_START_MS, now_ms)
            except (KeyError, ValueError, OSError) as exc:
                logger.debug("nuclear: %s tablet read failed: %s", asset, exc)
                continue
            if rows and len(rows) >= 120:
                out[sym] = rows
        return out

    async def start(self) -> bool:
        if self.state.running:
            return False
        if not self._configs or not self._candles:
            if not self.prepare():
                return False

        self._osc, self._sensed = (
            _make_oscillator() if self._load_oscillation else (None, False)
        )
        if self._osc is not None:
            self._osc.start()

        try:
            from src.trading.nuclear_verification import SwarmFeatureVerifier

            self._verifier = SwarmFeatureVerifier()
        except Exception as exc:  # noqa: BLE001 - verification advisory
            logger.warning("nuclear: verifier unavailable: %s", exc)
            self._verifier = None
        try:
            from src.core.emit_contracts import EmitObserver

            self._emit_obs = EmitObserver()
        except Exception as exc:  # noqa: BLE001 - observation advisory
            logger.warning("nuclear: emit observer unavailable: %s", exc)
            self._emit_obs = None

        self._open_log()
        self.state.running = True
        self.state.started_at = time.monotonic()
        self.state.stop_requested = False
        self.stopped_event.clear()
        self._task = asyncio.ensure_future(self._run())
        return True

    def is_running(self) -> bool:
        """Whether a soak is running. The Nuclear panel polls this."""
        return bool(self.state.running)

    def stop(self) -> None:
        """Call ``request_stop()``. The Nuclear panel calls this name."""
        self.request_stop()

    def request_stop(self) -> None:
        """Ask the soak and every fleet in the running cycle to stop.

        Best-effort per child, so one child that raises does not stop
        the others being asked.
        """
        self.state.stop_requested = True
        for ctl in list(self._live_fleets):
            try:
                ctl.request_stop()
            except Exception as exc:  # noqa: BLE001 - stop must reach the rest
                logger.debug("nuclear: child stop failed: %s", exc)

    async def _run(self) -> None:
        try:
            idx = 0
            while not self.state.stop_requested:
                if self._max_cycles is not None and idx >= self._max_cycles:
                    self._activity(f"Nuclear: reached max_cycles={self._max_cycles}.")
                    break
                idx += 1
                self.state.current_cycle = idx
                cyc = await self._run_cycle(idx)
                self.state.cycles.append(cyc)
                self._record_cycle(cyc)
                if cyc.ok:
                    self.state.cycles_completed += 1
                    self.state.total_candles += cyc.candles_played
                    self.state.total_trades += cyc.trades_fired
                    self.state.total_exceptions += cyc.exceptions
                else:
                    self.state.last_error = cyc.error
                    self._activity(f"Nuclear cycle {idx} FAILED: {cyc.error}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.state.last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("nuclear: run loop failed")
            self._activity(f"Nuclear: run loop failed — {exc}")
        finally:
            self._teardown()

    def _noised_candles_for_cycle(self, idx: int) -> tuple[dict, float]:
        """Build one cycle's market as a perturbed copy of the tablets.

        Every worker in a cycle shares one noised tape, so a cycle's
        results describe a single market. ``noised_series`` copies, so
        the tablets are never mutated and nothing here writes to disk.
        Deterministic in the base seed and ``idx``, so a failing cycle
        replays.

        Returns ``({symbol: rows}, noise_pct)``. With noise disabled the
        tablets come back unchanged with a noise_pct of 0.0.
        """
        if not self._noise_enabled:
            return dict(self._candles), 0.0
        from .nuclear_candle_source import noised_series

        # Mix the index into the base, so cycle N replays without
        # running cycles 0..N-1 first.
        seed = (self._noise_seed_base ^ ((idx + 1) * 0x9E3779B1)) & 0xFFFFFFFF
        out: dict = {}
        pct = 0.0
        for sym, rows in self._candles.items():
            if not rows:
                out[sym] = rows
                continue
            noised, pct = noised_series(rows, seed)
            out[sym] = noised
        return out, float(pct)

    async def _run_cycle(self, idx: int) -> NuclearCycle:
        from .fleet.fleet_replay_controller import FleetReplayController

        cyc = NuclearCycle(index=idx, started_at=time.monotonic())
        _cycle_candles_map, _noise_pct = self._noised_candles_for_cycle(idx)
        cyc.noise_pct = _noise_pct
        # Onto the polled state too, so the GUI can show which market
        # this cycle is running against.
        self.state.noise_pct = _noise_pct
        mult, cooling = self._current_load()
        cyc.load_multiplier = mult
        cyc.load_at_start = mult
        cyc.cooling = cooling
        self.state.load_multiplier = mult
        self.state.cooling = cooling

        # One fleet per cycle: the pulse raises tick rate and candles
        # per tick, it does not clone the fleet.
        cyc.workers = 1
        results: list = []
        try:

            async def _one(worker_idx: int):
                ctl = FleetReplayController(
                    configs=self._configs,
                    candles_by_symbol=_cycle_candles_map,
                    # Rate half of the pulse, read once per cycle: 0.8s
                    # over the multiplier, so 0.2s at the 4x peak.
                    tick_delay_s=(
                        self._osc.effective_tick_interval(0.8)
                        if self._osc is not None
                        else 0.0
                    ),
                    max_candles=self._cycle_candles,
                    activity_log_cb=lambda _m: None,
                    performance_log_cb=lambda _m: None,
                    # The fleet's own bot_state topology; the child
                    # attaches these to every bot it builds.
                    smart_wires=self._smart_wires,
                )
                # Appended before `await ctl.start()`, because the await
                # suspends and a Stop arriving then must find this ctl.
                self._live_fleets.append(ctl)
                if self.state.stop_requested:
                    ctl.request_stop()
                # Depth half of the pulse: candles to advance this tick,
                # clamped to at least 1.
                if self._osc is not None:
                    ctl.set_load_feed(self._osc.tick_workload)
                # `is not False` so a controller returning None still
                # counts as started.
                started = await ctl.start() is not False
                if self.state.stop_requested:
                    ctl.request_stop()

                sim_id = f"nuclear-c{idx}-w{worker_idx}"
                if self._swarm_register is not None:
                    try:
                        # `BotVisualizationTab.register_sim_run` takes
                        # (sim_id, label, cfg); the row names the cycle.
                        _label = f"Nuclear cycle {idx}"
                        self._swarm_register(
                            sim_id,
                            _label,
                            {
                                "asset": _label,
                                "mode": "NUCLEAR",
                                "timeframe": "5m",
                                "capital": 0,
                                "candle_total": self._cycle_candles,
                            },
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("swarm register failed: %s", exc)

                bots = getattr(ctl, "_bots", None) or []
                for b in bots:
                    if self._verifier is not None:
                        self._verifier.attach(b)
                    if self._emit_obs is not None:
                        self._emit_obs.attach(getattr(b, "_bus", None))
                self._wire_topology(bots)

                # `start()` leaves stopped_event SET on refusal, so a
                # wait here never suspends and would spin the loop.
                if not started:
                    self._activity(
                        f"  cycle {idx} worker {worker_idx}: fleet "
                        "refused to start (no bots instantiated) — "
                        "skipping. This worker contributes no candles."
                    )
                    return ctl.progress
                # Wall-clock bound, in case a controller finishes
                # without ever setting stopped_event.
                _deadline = time.monotonic() + WORKER_WAIT_CAP_S
                while not ctl.progress.finished:
                    if self._swarm_update is not None:
                        try:
                            # PnL is 0.0: Nuclear measures coverage and
                            # survival on a noised tape, not P&L.
                            self._swarm_update(
                                sim_id,
                                0.0,
                                int(ctl.progress.trades_fired),
                                int(ctl.progress.candles_played),
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("swarm update failed: %s", exc)
                    # The loop's own exit, so a child slow to honour
                    # request_stop cannot hold the operator all cycle.
                    if self.state.stop_requested:
                        break
                    if time.monotonic() > _deadline:
                        self._activity(
                            f"  cycle {idx} worker {worker_idx}: still "
                            f"unfinished after {WORKER_WAIT_CAP_S:.0f}s — "
                            "abandoning the wait. Its partial progress is "
                            "still counted."
                        )
                        break
                    try:
                        await asyncio.wait_for(ctl.stopped_event.wait(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue
                    # The event is set without `finished` — yield so
                    # this degrades to a slow poll, never a spin.
                    await asyncio.sleep(0)
                try:
                    await asyncio.wait_for(
                        ctl.stopped_event.wait(), timeout=WORKER_WAIT_CAP_S
                    )
                except asyncio.TimeoutError:
                    logger.debug(
                        "cycle %s worker %s: stopped_event never set", idx, worker_idx
                    )

                if self._verifier is not None:
                    self._verifier.scan_bots(getattr(ctl, "_bots", None) or [])
                if self._swarm_stop is not None:
                    try:
                        # 0.0 PnL, same reason as the update call above.
                        self._swarm_stop(sim_id, 0.0, int(ctl.progress.trades_fired))
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("swarm stop failed: %s", exc)
                return ctl.progress

            try:
                results = list(await asyncio.gather(_one(0), return_exceptions=True))
            finally:
                # Drained whatever happened, so a dead fleet cannot
                # outlive its cycle and the list cannot grow per cycle.
                self._live_fleets.clear()
            for r in results:
                if isinstance(r, BaseException):
                    cyc.error = f"{type(r).__name__}: {r}"
                    continue
                cyc.candles_played += int(r.candles_played)
                cyc.trades_fired += int(r.trades_fired)
                cyc.exceptions += int(r.exceptions)
        except Exception as exc:
            # A failed cycle is recorded, not fatal; the soak continues.
            cyc.error = f"{type(exc).__name__}: {exc}"
            logger.exception("nuclear: cycle %d failed", idx)
        cyc.elapsed_s = time.monotonic() - cyc.started_at

        rate = cyc.candles_played / cyc.elapsed_s if cyc.elapsed_s > 0 else 0.0
        # Ticks are candles minus the ones fed past the first, so the
        # ratio is mean feed depth.
        try:
            _extra = sum(
                getattr(r, "candles_fed_under_load", 0)
                for r in results
                if hasattr(r, "candles_fed_under_load")
            )
            _ticks = max(1, cyc.candles_played - _extra)
            cyc.candles_per_tick = round(cyc.candles_played / _ticks, 2)
        except Exception as _cpx:  # noqa: BLE001
            logger.debug("candles_per_tick calc failed: %s", _cpx)

        self._perf(
            f"Nuclear cycle {idx}: {cyc.candles_played:,} candles · "
            f"{cyc.trades_fired} trades · {cyc.exceptions} exceptions · "
            f"{rate:.1f} c/s · load {mult:.2f}x "
            f"(1 fleet, {cyc.candles_per_tick} candle/tick avg)"
            + ("  [COOLING]" if cooling else "")
        )
        return cyc

    def _wire_topology(self, bots: list) -> None:
        """Give this fleet the Smart Wire manager its bots look for.

        ``TickPhaseMixin._tick_execute_fold`` calls
        ``mgr.distribute_fold_profit`` whenever ``_smart_wire_mgr`` is
        set, so this supplies that manager rather than hooking events or
        reimplementing the routing.

        The child ``FleetReplayController`` has already attached the
        fleet's persisted bot_state wires. Market Inspector proposals
        passed to ``set_topologies`` are registered on top of those;
        with no proposal the fleet's own topology stands untouched, and
        a fleet with no wires is reported rather than given some.
        """
        if not bots:
            return
        try:
            from src.core.event_bus import EventBus
            from src.trading.smart_wire import SmartWireManager
        except ImportError as exc:
            logger.warning("nuclear: smart wire unavailable: %s", exc)
            return
        try:
            ids = [
                str(getattr(b, "bot_id", "") or "")
                for b in bots
                if str(getattr(b, "bot_id", "") or "")
            ]
            if len(ids) < 2:
                return
            pairs = self._topology_pairs(ids)

            # The child has already attached bot_state's wires, so a
            # second manager here would discard the real topology.
            existing = getattr(bots[0], "_smart_wire_mgr", None)
            if not pairs:
                if existing is None:
                    self._activity(
                        f"  cycle wiring: {len(ids)} bot(s) have NO Smart "
                        "Wires — bot_state carried none and no Market "
                        "Inspector proposal was injected. Cross-bot "
                        "compounding is inert this run; tranche-chain "
                        "coverage will read 0 for the wire-fed links."
                    )
                else:
                    self._activity(
                        f"  cycle wiring: using the fleet's own topology "
                        f"from bot_state across {len(ids)} bot(s); no "
                        "Market Inspector proposal injected."
                    )
                return

            # Register the proposal on the fleet's existing manager, so
            # it is stressed on top of the real topology.
            mgr = existing
            if mgr is None:
                # A private bus: SmartWireManager resolves the
                # process-wide live bus when bus is None.
                self._sim_bus = EventBus()
                mgr = SmartWireManager(bus=self._sim_bus)
                for b in bots:
                    bid = str(getattr(b, "bot_id", "") or "")
                    if bid:
                        mgr.attach_bot(bid, b)
                        b.set_smart_wire(mgr)
            wired = 0
            for src, tgt, pct in pairs:
                if mgr.register_wire(src, tgt, pct).get("applied"):
                    wired += 1
            self._activity(
                f"  cycle wiring: injected {wired} of {len(pairs)} Market "
                f"Inspector proposal wire(s) across {len(ids)} bot(s), on "
                "top of the fleet's own bot_state topology."
            )
            logger.info(
                "nuclear: smart wire — %d bot(s), %d injected wire(s)", len(ids), wired
            )
        except Exception as exc:  # noqa: BLE001 - an unwired cycle is
            # still a valid load cycle, so wiring must not end the soak.
            logger.warning("nuclear: smart wire setup failed: %s", exc)

    def _topology_pairs(self, ids: list) -> list:
        """Return the wires to inject on top of the fleet's own topology.

        Each entry is ``(source_bot_id, target_bot_id, pct)``, built
        from the Market Inspector proposals passed to
        ``set_topologies``. There is no fallback topology: an empty
        result leaves the fleet's persisted bot_state wires standing,
        and a fleet with none stays unwired.
        """
        pairs: list = []
        for prop in self._topologies or []:
            for w in prop.get("wires", []) or []:
                src = self._bot_for_asset(ids, w.get("source_asset"))
                tgt = self._bot_for_asset(ids, w.get("target_asset"))
                if src and tgt and src != tgt:
                    pairs.append((src, tgt, float(w.get("pct", 10.0))))
        return pairs

    def _bot_for_asset(self, ids: list, asset) -> str:
        """Map a proposal asset to a bot id in this fleet."""
        if not asset:
            return ""
        want = str(asset).upper()
        for cfg, bid in zip(self._configs, ids):
            if str(cfg.get("target_asset", "")).upper() == want:
                return bid
        return ""

    def _current_load(self) -> tuple[float, bool]:
        """Load multiplier for this cycle, plus whether COOLING is on."""
        if self._osc is None:
            return 1.0, False
        try:
            mult = float(self._osc.current_multiplier())
            # `is_cooling` is a property; calling it would raise into
            # the guard below and pin load at 1.0x.
            cooling = bool(self._osc.is_cooling)
        except Exception as exc:  # noqa: BLE001 - sensor guard
            logger.debug("nuclear: oscillator read failed: %s", exc)
            return 1.0, False
        # Jitter on top of the cosine ramp, so no two cycles present
        # identical load.
        mult *= 1.0 + self._rng.uniform(-_NOISE_PCT, _NOISE_PCT)
        if not self._sensed:
            mult = min(mult, UNSENSED_LOAD_CAP)
        return max(0.25, mult), cooling

    def _open_log(self) -> None:
        try:
            from src.trading.sim_run_log import SimRunLog

            self._log = SimRunLog()
            self._log.start_run(
                config={
                    "mode": "nuclear",
                    "bots": len(self._configs),
                    "symbols": sorted(self._candles.keys()),
                    "cycle_candles": self._cycle_candles,
                    "load_oscillation": self._load_oscillation,
                    "load_sensed": self._sensed,
                    "max_cycles": self._max_cycles,
                }
            )
            self._activity(f"Nuclear log: {self._log.run_id}")
        except Exception as exc:  # noqa: BLE001 - logging is advisory
            self._log = None
            logger.warning("nuclear: run log unavailable: %s", exc)

    def _record_cycle(self, cyc: NuclearCycle) -> None:
        if self._log is None:
            return
        try:
            self._log.record_gate(
                bot_id="nuclear", symbol="", payload={"nuclear_cycle": cyc.to_dict()}
            )
        except Exception as exc:  # noqa: BLE001 - advisory
            logger.debug("nuclear: cycle record failed: %s", exc)

    def _teardown(self) -> None:
        if self._osc is not None:
            try:
                self._osc.stop()
            except Exception as exc:  # noqa: BLE001
                logger.debug("nuclear: oscillator stop failed: %s", exc)
        if self._log is not None:
            try:
                self._log.finish_run(
                    summary={
                        "cycles_completed": self.state.cycles_completed,
                        "total_candles": self.state.total_candles,
                        "total_trades": self.state.total_trades,
                        "total_exceptions": self.state.total_exceptions,
                        "failed_cycles": sum(1 for c in self.state.cycles if not c.ok),
                        "uptime_s": round(self.state.uptime_s, 1),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("nuclear: log close failed: %s", exc)
        if self._emit_obs is not None:
            try:
                from src.core.emit_contracts import format_observer_lines

                self._emit_obs.finish()
                for line in format_observer_lines(self._emit_obs):
                    self._perf(line)
                if self._log is not None:
                    self._log.record_gate(
                        bot_id="nuclear",
                        symbol="",
                        payload={"emit_contracts": self._emit_obs.to_dict()},
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("nuclear: emit report failed: %s", exc)
        if self._verifier is not None:
            try:
                from src.trading.nuclear_verification import format_coverage_lines

                for line in format_coverage_lines(self._verifier.report):
                    self._perf(line)
                if self._log is not None:
                    self._log.record_gate(
                        bot_id="nuclear",
                        symbol="",
                        payload={"coverage": self._verifier.report.to_dict()},
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug("nuclear: coverage report failed: %s", exc)
        self.state.running = False
        self.stopped_event.set()
        self._activity(
            f"Nuclear stopped: {self.state.cycles_completed} cycle(s), "
            f"{self.state.total_candles:,} candles, "
            f"{self.state.total_trades} trades, "
            f"{self.state.total_exceptions} exceptions."
        )

    def snapshot(self) -> dict:
        """Return the GUI panel's polled view of this soak."""
        s = self.state
        return {
            "running": s.running,
            "uptime_seconds": s.uptime_s,
            "fleet_size": s.fleet_size,
            "symbols": s.symbols,
            "cycles_completed": s.cycles_completed,
            "current_cycle": s.current_cycle,
            "noise_pct": s.noise_pct,
            "wires_loaded": len(self._smart_wires),
            "total_candles": s.total_candles,
            "total_trades": s.total_trades,
            "total_exceptions": s.total_exceptions,
            "load_multiplier": s.load_multiplier,
            "cooling": s.cooling,
            "load_sensed": self._sensed,
            "last_error": s.last_error,
            "failed_cycles": sum(1 for c in s.cycles if not c.ok),
        }
