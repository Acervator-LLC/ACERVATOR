"""nuclear_fleet_controller.py — Nuclear Mode v2: fleet-wide soak test.

Operator directive 2026-08-05, replacing the Phase-B single-tape scout:

    "Nuclear Mode does not run singular tapes. It runs full Stone
    Tablets in loop across the fleet loaded from bot_state."

WHAT THIS IS
============
A soak test, not a backtest. Fleet Replay answers "did the fleet
reproduce history?" once. Nuclear Mode answers "does the platform stay
correct when you run it forever under varying load?" — which is a
different question and needs a different harness.

It loops the bot_state fleet over Stone Tablet history until stopped,
varying system load between cycles, and records everything so a failure
that appears on cycle 40 can be traced back.

WHY IT DRIVES FleetReplayController RATHER THAN RE-IMPLEMENTING IT
==================================================================
Everything a cycle needs already exists and is pinned by tests: fleet
loading from bot_state, the sim exchange, real ScrummingBot.tick() on an
isolated bus, master-clock timestamps, per-symbol trade attribution, run
logging. A second tick loop here would drift from that one, and then a
Nuclear failure would be ambiguous — a real defect, or a divergence
between two simulators? Reusing the controller keeps failures
attributable.

LOAD OSCILLATION (item 4)
=========================
``SystemLoadOscillator`` (v3.13.7) already implements the required
shape: 45 s cosine ramp up, 30 s sustain at 4x, 45 s ramp down, on a
120 s cycle, with a COOLING regime that caps the multiplier when the
machine is under stress. It had ZERO callers — built and never wired.
This is its first consumer.

The cosine ramp is the "smoothed" half of the operator's "noise-injected
but smoothed"; per-cycle jitter supplies the noise, so successive cycles
are not identical while the ramp stays continuous.

SAFETY
======
A 4x load pulse runs on the same machine as the live trading engine.
COOLING is therefore not optional decoration — without it a soak test
could starve the process executing real orders. Load is sampled from
psutil when available; if it is not, the oscillator is constructed with
no sensor and the multiplier is capped, because an unmonitored 4x pulse
against live trading is not a trade worth making.

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
"""Wall-clock ceiling on waiting for one worker fleet to finish.

A backstop, not a schedule. The cause of the v3.24.74 hang is fixed at
the source (`start()` now reports refusal), but a soak is the one place
where an unbounded wait is least acceptable: it runs unattended for
hours on the same event loop the GUI and live trading use. Generous
enough that a legitimate 3000-candle cycle under 6-way concurrency never
trips it — measured throughput is ~25.8 candles/s — and finite so a
regression degrades to a logged anomaly instead of a frozen application.
"""

DEFAULT_NOISE_SEED = 0xACE12A7
"""Base seed for per-cycle market-structure noise.

FIXED, not random, so a soak is reproducible: cycle 40 replays the same
market structure on a re-run, which is the difference between a
diagnostic and an anecdote. Variety across cycles comes from mixing the
cycle INDEX into this base, not from the base changing. Pass ``seed=``
to explore a different sequence.
"""

DEFAULT_CYCLE_CANDLES = 3000
"""Candles per cycle. Short enough that a cycle completes in minutes so
load oscillation is observable across cycles, long enough for scrum/fold
cycles to complete repeatedly."""

UNSENSED_LOAD_CAP = 1.5
"""Multiplier ceiling when machine load cannot be sampled.

Matches the oscillator's own COOLING cap. An unmonitored 4x pulse shares
a machine with the live trading engine; refusing to go above 1.5x blind
is the conservative default.
"""

_NOISE_PCT = 0.15
"""Per-cycle jitter on the load multiplier. Keeps successive cycles from
presenting identical load while leaving the cosine ramp continuous."""


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
    # v3.24.83 - mean candles fed per engine tick this cycle.
    # THE load figure for a looper: intensity is depth per
    # tick x tick rate, not fleet count.
    candles_per_tick: float = 0.0
    cooling: bool = False
    error: str = ""
    # v3.24.73 — this cycle's market-structure noise amplitude. Recorded
    # because a varied structure the operator cannot see is
    # indistinguishable from an unvaried one, and because a soak's whole
    # value is being able to say WHICH market a failure happened in.
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
            # v3.24.73 — which market this cycle actually ran against.
            # Without it a soak report cannot distinguish "survived a
            # violent tape" from "replayed the calm one forty times".
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
    # v3.24.78 — the market-structure noise amplitude of the cycle
    # currently running. Lives on the cycle record too, but the GUI
    # polls state, and a varied market the operator cannot see is
    # indistinguishable from an unvaried one.
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
            """SystemLoadMR-shaped probe.

            The contract is READ FROM ``SystemLoadOscillator``
            ``_monitor_loop``, not guessed: it calls ``sample(now)``
            and then reads the ``current_regime`` ATTRIBUTE, at 5 Hz.

            An earlier version of this class exposed ``regime()`` and a
            ``current_regime`` property but no ``sample``. The monitor
            thread then raised AttributeError on every single sample,
            so COOLING never engaged — the safety mechanism was dead
            while reporting itself as sensed. Hence the explicit note:
            match the caller, do not assume it.
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

        psutil.cpu_percent(interval=None)  # prime the sampler
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
        # v3.24.73 — per-cycle MARKET-STRUCTURE noise.
        #
        # Distinct from the SystemLoadOscillator above, which varies CPU
        # load. Operator directive 2026-08-07: the loops "are supposed to
        # have varied market structure via an oscillator that injects
        # noise to simulate varied market structures without writing over
        # the stone tablets." Load oscillation is not that.
        self._noise_enabled = bool(noise_enabled)
        # Derived from a FIXED base rather than drawn from self._rng.
        #
        # Two reasons. (1) A soak that cannot be re-run is not a
        # diagnostic — the operator must be able to replay cycle 40 after
        # it fails. (2) Drawing from _rng would couple a cycle's market
        # structure to how many unrelated jitter draws preceded it, so
        # the same cycle index would differ between runs that took
        # different load paths. Pass `seed=` for a different sequence.
        self._noise_seed_base = DEFAULT_NOISE_SEED if seed is None else int(seed)
        self.state = NuclearState()
        self._task: Optional[asyncio.Task] = None
        self._osc = None
        self._sensed = False
        self._configs: list[dict] = []
        # v3.24.76 — bot_state's top-level `smart_wires`, loaded in
        # prepare() alongside the configs. Part of the fleet, not an
        # optional extra.
        self._smart_wires: list[dict] = []
        self._candles: dict[str, list] = {}
        # v3.24.75 (C23 step 3) — the live child fleets of the CURRENT
        # cycle, so `request_stop()` has something to fan out to.
        #
        # Before this, `ctl` was a local inside the `_one()` closure and
        # never escaped, so the only stop signal was the between-cycles
        # flag check and a Stop click waited out the whole cycle.
        #
        # A plain list, not a WeakSet: the entries are alive for exactly
        # as long as the cycle that registered them, and `_run_cycle`
        # drains it in a `finally` so a crashed worker cannot leave a
        # stale controller behind for the next cycle's Stop to poke.
        self._live_fleets: list = []
        self._log = None
        # v3.24.30 — feature coverage. Declared up front so a feature
        # that never fires reports as UNVERIFIED rather than being
        # absent from the report entirely.
        self._verifier = None
        # v3.24.30 — emit-contract observation. Validates that bus
        # payloads carry the fields consumers read, which is how a
        # producer/consumer key rename becomes visible instead of
        # silently yielding None.
        self._emit_obs = None
        # Topology proposals to stress. Empty = ring across the fleet.
        self._topologies: list = []
        self._wire_pct = 10.0
        # Simulator Swarm hooks. The swarm already exposes
        # register_sim_run / update_sim_run / stop_sim_run, but nothing
        # in the tree ever called them — the rows were built and never
        # driven. Nuclear Mode becomes that producer. Held as callbacks
        # so this controller stays GUI-agnostic and testable.
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
        """Wire the Simulator Swarm row API.

        Operator directive 2026-08-05: Nuclear Mode "must be using the
        Simulator Swarm". These three callbacks are that seam.
        """
        self._swarm_register = register
        self._swarm_update = update
        self._swarm_stop = stop

    # ── setup ────────────────────────────────────────────────────

    def prepare(self) -> bool:
        """Load the fleet and its tablet history. Returns False (with an
        operator-readable reason) rather than raising, so the panel can
        report why a run did not start."""
        from .fleet import bot_state_loader as _loader

        try:
            self._configs = _loader.load_bot_configs_from_state()
            # v3.24.76 — THE WIRES ARE PART OF THE FLEET.
            #
            # Operator directive 2026-08-07: a fleet load references
            # bot_state and "all pieces / functions of the fleet must
            # import". A fleet imported with its bots but not its wires
            # is not the fleet — its compounding engine is switched
            # off, and every tranche-chain and cross-bot-credit number
            # the soak reports is measured against a topology the
            # operator does not have.
            #
            # Loaded here rather than in the panel so a Nuclear run
            # cannot be started without them.
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

    # ── run loop ─────────────────────────────────────────────────

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
        """v3.24.75 — the panel calls this.

        `NuclearController` (v1) has `is_running()` and `stop()`; this class
        had only `request_stop()`. The Nuclear panel calls all three names,
        so repointing it at v2 without these is an AttributeError on the
        operator's first Stop click. Pinned against v1's surface in
        `tests/test_nuclear_stop_is_responsive.py`.
        """
        return bool(self.state.running)

    def stop(self) -> None:
        """Panel-facing alias for `request_stop()`. Same meaning, and pinned
        that way — two stop verbs that drift apart is how a Stop button ends
        up calling the one that does less."""
        self.request_stop()

    def request_stop(self) -> None:
        """Cooperative stop — and it now REACHES THE RUNNING FLEETS.

        v3.24.75 (C23 step 3). `stop_requested` was read in exactly one
        place: the between-cycles `while` in `_run`. Nothing inside a cycle
        read it, and the child `FleetReplayController` — which has a working
        `request_stop()` — was a local inside the `_one()` closure, so
        nothing outside could reach it to ask.

        A cycle is DEFAULT_CYCLE_CANDLES (3000) across up to 6 gathered
        fleets; at the measured ~25.8 candles/s that is minutes of an
        unresponsive Stop, on the single asyncio loop `main.py` pumps from
        the Qt GUI thread and shares with live trading. The realistic
        failure mode here is not a crash — it is an application that
        ignores the operator.

        Fanning out is best-effort per child on purpose: one child that
        raises must not prevent the others from being asked.
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
        except Exception as exc:  # noqa: BLE001 - loop guard
            self.state.last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("nuclear: run loop failed")
            self._activity(f"Nuclear: run loop failed — {exc}")
        finally:
            self._teardown()

    def _noised_candles_for_cycle(self, idx: int) -> tuple[dict, float]:
        """This cycle's market structure — a perturbed COPY of the tablets.

        v3.24.73. The missing half of the mode. Every cycle previously
        replayed a byte-identical tape (loaded once at `prepare()`, handed
        unchanged to every `FleetReplayController`), so the loop varied
        only how hard the machine worked. A bot can learn one fixed tape,
        which is the entire reason the noise exists.

        Operator directive 2026-08-07: the loops "are supposed to have
        varied market structure via an oscillator that injects noise to
        simulate varied market structures WITHOUT WRITING OVER THE STONE
        TABLETS."

        THE CYCLE IS THE UNIT OF STRUCTURE. All workers within a cycle
        share one noised tape: concurrency is the LOAD stressor, and
        giving each worker its own market would mean a cycle's results
        described several different markets at once.

        The tablets are never mutated — `noised_series` copies — and
        nothing here writes to disk. Deterministic in (base seed, idx) so
        a failing cycle can be replayed.

        Returns ``({symbol: rows}, noise_pct)``. With noise disabled it
        returns the tablets unchanged and 0.0, which is how an operator
        asks "does this fail on the clean tape too?"
        """
        if not self._noise_enabled:
            return dict(self._candles), 0.0
        from .nuclear_candle_source import noised_series

        # Mix the index into the base rather than advancing a stream, so
        # cycle N is reproducible without replaying cycles 0..N-1.
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
        # v3.24.73 — vary the MARKET, not just the load. One tape per
        # cycle, shared by every worker in it.
        _cycle_candles_map, _noise_pct = self._noised_candles_for_cycle(idx)
        cyc.noise_pct = _noise_pct
        # v3.24.78 — also onto the polled state, so the GUI can show
        # WHICH market this cycle is running against.
        self.state.noise_pct = _noise_pct
        mult, cooling = self._current_load()
        cyc.load_multiplier = mult
        cyc.load_at_start = mult
        cyc.cooling = cooling
        self.state.load_multiplier = mult
        self.state.cooling = cooling

        # Load is applied as CONCURRENCY, not as tick delay.
        #
        # An earlier draft scaled tick_delay_s by the multiplier, which
        # is backwards: tick_delay only ever ADDS idle time, so the
        # "4x load" pulse would have made the cycle slower, not the
        # machine busier. The replay already runs flat out at
        # tick_delay=0, so raising load means running more work in
        # parallel — see _load_workers().
        # Load is applied as CONCURRENCY: run ceil(multiplier) fleets
        # at once. Anything else would be theatre — an earlier draft
        # scaled tick_delay_s, but tick_delay only ADDS idle time, so a
        # "4x load" pulse would have made the machine quieter. Measured
        # before this change: throughput held at ~25.8 c/s while the
        # multiplier swept 0.99x -> 3.14x, i.e. the oscillator moved a
        # number and nothing else.
        #
        # Concurrency is also the right stressor for a soak test: N
        # fleets sharing one process is what surfaces contention and
        # races, which a single fleet running slower never would.
        # ── ONE FLEET. LOAD IS INTENSITY, NOT COPIES. ───────────────
        # v3.24.83. This read
        #     workers = max(1, min(int(mult + 0.5), 6))
        # and gathered that many FleetReplayControllers, each with its
        # OWN full fleet of bots, its own swarm rows, its own everything.
        # A 4x load pulse produced FOUR COPIES of the operator's fleet
        # rather than driving one fleet four times as hard.
        #
        # That contradicts the mode's own spec. Operator, Session 18:
        # "Instead of system speed being a manual control, it now
        # oscillates in 2m intervals with a 30s sustain at max load
        # speed per cycle", confirmed as:
        #     Q1 - oscillates BOTH tick rate AND per-tick workload
        #     Q2 - peak 4x base (0.8s -> 0.2s tick, 1x -> 4x workload)
        # and system_load_oscillator.py's own header: "each engine tick
        # adds current multiplier to the accumulator; the integer part
        # becomes the number of _tick_feed iterations that tick."
        #
        # `_tick_feed` was never built — grep of src/ finds it only in
        # that docstring. The workload half of the oscillator was
        # specified, its API shipped (`tick_workload`,
        # `effective_tick_interval`), and the consumer was replaced by
        # fleet cloning.
        #
        # Nuclear is a high-intensity Stone Tablet LOOPER: it supplies
        # candle data to the simulated bots, the Simulator Swarm and the
        # indicator panel, harder each pulse. One fleet, fed faster and
        # deeper — which is also the only shape that stresses the REAL
        # plumbing rather than N private copies of it.
        cyc.workers = 1
        results: list = []
        try:

            async def _one(worker_idx: int):
                ctl = FleetReplayController(
                    configs=self._configs,
                    candles_by_symbol=_cycle_candles_map,
                    # RATE half of the pulse: base 0.8s / multiplier,
                    # so 0.8s -> 0.2s at the 4x peak (Session 18 spec,
                    # Q2). Read once per cycle; the DEPTH half is
                    # per-tick via set_load_feed below.
                    tick_delay_s=(
                        self._osc.effective_tick_interval(0.8)
                        if self._osc is not None
                        else 0.0
                    ),
                    max_candles=self._cycle_candles,
                    activity_log_cb=lambda _m: None,
                    performance_log_cb=lambda _m: None,
                    # v3.24.76 — the fleet's OWN topology, from
                    # bot_state. The child imports and attaches these
                    # (C20/v3.24.72); without them the fleet runs with
                    # cross-bot compounding switched off and every
                    # tranche-chain number describes a topology the
                    # operator does not have.
                    smart_wires=self._smart_wires,
                )
                # v3.24.75 (C23 step 3) — REGISTER BEFORE STARTING.
                #
                # Registered before `await ctl.start()`, not after: the
                # await is a suspension point, so a Stop arriving during
                # start would otherwise find an empty registry and the
                # fleet would run on unaware. Drained in `_run_cycle`'s
                # finally.
                self._live_fleets.append(ctl)
                # If Stop arrived while this worker was being set up,
                # honour it now rather than running a whole fleet that
                # is already unwanted.
                if self.state.stop_requested:
                    ctl.request_stop()
                # v3.24.74 — a bool since C23 step 4. `is not False`
                # rather than truthiness so an older controller that
                # still returns None is treated as "started", which is
                # what it used to mean.
                # DEPTH half: `tick_workload()` is the deterministic
                # accumulator the oscillator header describes — mean
                # equals the multiplier exactly, clamped to >=1 so a bot
                # always advances at least one candle.
                if self._osc is not None:
                    ctl.set_load_feed(self._osc.tick_workload)
                started = await ctl.start() is not False
                if self.state.stop_requested:
                    ctl.request_stop()

                # Register this fleet as a Simulator Swarm row. The
                # swarm's row API existed with zero callers; this is
                # the producer it was built for.
                sim_id = f"nuclear-c{idx}-w{worker_idx}"
                if self._swarm_register is not None:
                    try:
                        # v3.24.77 — THREE arguments, matching the real
                        # consumer. `BotVisualizationTab.register_sim_run`
                        # is `(sim_id, label, cfg)`; this passed two,
                        # putting the cfg dict where `label` goes and
                        # omitting cfg entirely. That is a TypeError on
                        # the first cycle, swallowed to logger.debug
                        # below — so the rows never appeared and nothing
                        # said why. `nuclear_verification.py:19` recorded
                        # the symptom ("register_sim_run() zero callers
                        # -> swarm rows never driven") without the cause.
                        # One fleet per cycle now, so the swarm row
                        # names the CYCLE. "fleet 1/4" described the
                        # cloning that v3.24.83 removed.
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

                # Attach the feature verifier to this fleet's bots.
                bots = getattr(ctl, "_bots", None) or []
                for b in bots:
                    if self._verifier is not None:
                        self._verifier.attach(b)
                    if self._emit_obs is not None:
                        self._emit_obs.attach(getattr(b, "_bus", None))
                self._wire_topology(bots)

                # Stream progress into the swarm row while it runs.
                #
                # v3.24.74 (C23 step 4) — BOUNDED, and it now believes
                # `start()`.
                #
                # This loop used to poll `progress.finished` while
                # awaiting an Event that `start()` leaves SET on both
                # refusal paths. Awaiting an already-set Event completes
                # without suspending, so `timeout=0.5` never fired and
                # the loop never yielded: measured at 477,043 iterations
                # per second with every other coroutine on the loop
                # advancing ZERO. Since main.py pumps ONE loop from the
                # Qt GUI thread, that freezes the GUI and live trading
                # rather than merely wasting a core.
                #
                # Two independent guards, because one is not enough:
                #   1. Honour start()'s refusal — do not wait on a fleet
                #      that never launched. Fixes the cause.
                #   2. Bound the loop in wall-clock anyway. A future
                #      controller could reintroduce a
                #      finished-but-not-stopped window, and a soak must
                #      degrade to a logged anomaly rather than a hang.
                if not started:
                    self._activity(
                        f"  cycle {idx} worker {worker_idx}: fleet "
                        "refused to start (no bots instantiated) — "
                        "skipping. This worker contributes no candles."
                    )
                    return ctl.progress
                _deadline = time.monotonic() + WORKER_WAIT_CAP_S
                while not ctl.progress.finished:
                    if self._swarm_update is not None:
                        try:
                            # v3.24.77 — PnL is 0.0, not the trade count.
                            #
                            # This passed `trades_fired` as the PnL
                            # argument, so the swarm row would have
                            # rendered "PnL +37.00" for 37 trades — a
                            # count formatted as dollars. Nuclear does
                            # not measure P&L; it measures coverage and
                            # survival, against a deliberately noised
                            # tape that is not history. Reporting a real
                            # number in the wrong unit is worse than
                            # reporting nothing, so it reports nothing.
                            self._swarm_update(
                                sim_id,
                                0.0,
                                int(ctl.progress.trades_fired),
                                int(ctl.progress.candles_played),
                            )
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("swarm update failed: %s", exc)
                    # v3.24.75 (C23 step 3) — honour Stop INSIDE the
                    # cycle. `request_stop()` has already asked this
                    # child directly; this is the loop's own exit so a
                    # child that ignores or is slow to honour the ask
                    # cannot hold the operator for the rest of a
                    # 3000-candle cycle.
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
                    # The event is set. Either the run really finished
                    # (the loop condition ends it) or something set it
                    # without setting `finished` — yield explicitly so
                    # that case degrades to a slow poll, never a spin.
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
                        # v3.24.77 — 0.0 PnL, same reason as the update
                        # call above: Nuclear does not measure P&L.
                        self._swarm_stop(sim_id, 0.0, int(ctl.progress.trades_fired))
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("swarm stop failed: %s", exc)
                return ctl.progress

            try:
                results = list(await asyncio.gather(_one(0), return_exceptions=True))
            finally:
                # v3.24.75 (C23 step 3) — drain the registry whatever
                # happened. A crashed worker must not leave a dead
                # controller behind for the NEXT cycle's Stop to poke,
                # and an unbounded list would grow one entry per worker
                # per cycle across an all-night soak.
                self._live_fleets.clear()
            for r in results:
                if isinstance(r, BaseException):
                    cyc.error = f"{type(r).__name__}: {r}"
                    continue
                cyc.candles_played += int(r.candles_played)
                cyc.trades_fired += int(r.trades_fired)
                cyc.exceptions += int(r.exceptions)
        except Exception as exc:  # noqa: BLE001 - one cycle must not
            # end the soak; that is the whole point of a soak test.
            cyc.error = f"{type(exc).__name__}: {exc}"
            logger.exception("nuclear: cycle %d failed", idx)
        cyc.elapsed_s = time.monotonic() - cyc.started_at

        rate = cyc.candles_played / cyc.elapsed_s if cyc.elapsed_s > 0 else 0.0
        # Mean candles fed per engine tick — the honest load figure for
        # a looper. ticks = candles - extra_fed, so the ratio is depth.
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
        """Give this fleet a Smart Wire network.

        WHY THIS IS NEEDED
        ------------------
        Smart Wire was never instantiated anywhere in the simulator —
        ``grep SmartWireManager`` finds live wiring and stocks, but no
        sim path. So no wire transaction ever ran in a replay, no
        tranche was ever wire-fed, and the tranche chain's links 2-4
        could not pass no matter how long a soak ran. The verifier was
        reporting the truth: 9 tranches created, 0 fed.

        The bot already routes on its own —
        ``TickPhaseMixin._tick_execute_fold`` in
        ``src/trading/scrumming/tick_phases.py``
        calls ``mgr.distribute_fold_profit`` whenever
        ``self._smart_wire_mgr`` is set. So this does not hook events or
        reimplement routing; it supplies the manager the bot is already
        looking for, and registers wires between fleet members.

        TOPOLOGY SOURCE
        ---------------
        Market Inspector proposals when the caller supplies them,
        otherwise a ring across the fleet. A ring is deliberate rather
        than arbitrary: every bot is both a source and a target, so
        cross-bot credit is exercised in both directions and link 4
        cannot pass by accident on a self-fed tranche.
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
            # v3.24.72 (C20) — INJECT A PRIVATE BUS.
            #
            # This was `SmartWireManager()`, and the C20 cascade plan
            # cited this very line as the precedent to copy on the
            # grounds that "the class has no bus". It is the leak.
            #
            # SmartWireManager takes `bus=None` (smart_wire.py:217) and
            # both emit paths resolve the PROCESS-WIDE get_event_bus()
            # when it is None (:507-511, :695-698), then emit bot.log.
            # So a sim topology's wire activity was landing on the
            # operator's LIVE bus, while the sim bots wired into it are
            # fail-closed onto private buses (scrumming_bot.py:393-394).
            #
            # Verified rather than assumed: a bus-less manager with
            # wires registered DOES reach a spy on the live bus — the
            # premise control in tests/test_build_sim_smart_wires.py
            # passes on the unmodified baseline. Note the leak only
            # arms once wires exist; with none, smart_wire.py:500-501
            # returns before the bus is resolved.
            ids = [
                str(getattr(b, "bot_id", "") or "")
                for b in bots
                if str(getattr(b, "bot_id", "") or "")
            ]
            if len(ids) < 2:
                return
            pairs = self._topology_pairs(ids)

            # v3.24.76 — DO NOT REPLACE THE FLEET'S OWN TOPOLOGY.
            #
            # The child FleetReplayController has already imported
            # bot_state's persisted wires and attached a manager to
            # every bot (C20/v3.24.72). Building a second manager here
            # and reassigning `b._smart_wire_mgr` would discard the
            # operator's real topology on every cycle — which is what
            # the old code did, silently, using an invented circular
            # chain because `set_topologies` had zero callers.
            #
            # With no proposal injected there is nothing to add, and
            # the fleet's own wires stand.
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

            # A proposal WAS injected. Register it onto the fleet's
            # existing manager so the injected strategy is stressed on
            # top of the real topology rather than instead of it.
            mgr = existing
            if mgr is None:
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
        except Exception as exc:  # noqa: BLE001 - wiring must not end
            # the soak; an unwired cycle is still a valid load cycle.
            logger.warning("nuclear: smart wire setup failed: %s", exc)

    def _topology_pairs(self, ids: list) -> list:
        """Wires INJECTED on top of the fleet's own topology, or none.

        Returns (source_bot_id, target_bot_id, pct) built from Market
        Inspector proposals handed in via `set_topologies`. Stressing
        those is the mode's job: topology propagation across the swarm
        under cycling load.

        v3.24.76 — THE FABRICATED FALLBACK IS GONE.

        This used to end with a hard-coded circular chain when no
        proposal was present: bot 1 -> bot 2 -> ... -> last -> bot 1,
        each at a fixed percentage. Nothing designed that as a
        strategy; it was invented so the tranche-chain verifier would
        have SOME wires to exercise, back when no simulator path built
        Smart Wires at all.

        It ran on EVERY cycle ever executed, because `set_topologies`
        had zero callers, so the proposal branch above was never taken.
        The operator's real fleet was silently rewired into a circle
        that exists nowhere in bot_state, and the coverage numbers that
        produced described a topology the operator never had.

        Operator directive 2026-08-07: "The ONLY source beyond the user
        adding new bots manually must be a fleet load that references
        bot_state and all pieces / functions of the fleet must import"
        — and "no more inventing things to generate results from
        elements that exist and must be tested."

        So the tiers are now, in order, with no invented one:
          1. injected Market Inspector proposals (here)
          2. otherwise the fleet's PERSISTED wires, which the child
             FleetReplayController already imported from bot_state —
             returning [] leaves those standing, untouched
          3. neither -> no topology, said out loud by `_wire_topology`

        A fleet with no wires is a finding about the fleet. It is not a
        licence to give it some.
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
            # `is_cooling` is a PROPERTY on SystemLoadOscillator,
            # not a method. Calling it would raise TypeError and
            # be swallowed by the guard below, silently pinning
            # load to 1.0x for the whole soak.
            cooling = bool(self._osc.is_cooling)
        except Exception as exc:  # noqa: BLE001 - sensor guard
            logger.debug("nuclear: oscillator read failed: %s", exc)
            return 1.0, False
        # Per-cycle jitter: the cosine ramp supplies smoothness, this
        # supplies the noise, so no two cycles present identical load.
        mult *= 1.0 + self._rng.uniform(-_NOISE_PCT, _NOISE_PCT)
        if not self._sensed:
            mult = min(mult, UNSENSED_LOAD_CAP)
        return max(0.25, mult), cooling

    # ── logging ──────────────────────────────────────────────────

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

    # ── GUI snapshot ─────────────────────────────────────────────

    def snapshot(self) -> dict:
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
