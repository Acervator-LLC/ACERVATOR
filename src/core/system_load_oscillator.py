"""
src/core/system_load_oscillator.py — v3.13.7 Nuclear Mode speed oscillator.

User directive Session 18 (turn 11):
  "Nuclear Mode - Upgrade - Instead of system speed being a manual
  control, it now oscillates in 2m intervals with a 30s sustain at
  max load speed per cycle with increase system sensing."

Confirmed spec (3 verify-first answers):
  Q1 — Oscillates: BOTH tick rate AND per-tick workload ("true load pulse")
  Q2 — Peak ratio: 4× base (0.8s → 0.2s tick, 1× → 4× workload)
  Q3 — Sensing:    5× sampling + tighter thresholds + COOLING regime

Shape (symmetric):
  ╭─ 45s cosine ramp up ─╮╭─ 30s sustain at 4× ─╮╭─ 45s cosine ramp down ─╮
  │                       ││                      ││                        │
  │   1.0×  ─────────►    ││        4.0×          ││    ◄───────── 1.0×     │
  ╰───────────────────────╯╰──────────────────────╯╰────────────────────────╯
                              120s cycle, repeat

COOLING protection:
  - Background daemon samples SystemLoadMR at 5Hz (0.2s)
  - STRESS or CRITICAL regime → enter COOLING
  - COOLING state: multiplier capped at 1.5× regardless of cycle
  - 3 consecutive CALM samples → exit COOLING

Workload application:
  Deterministic accumulator: each engine tick adds current multiplier
  to the accumulator; the integer part becomes the number of
  _tick_feed iterations that tick. Fractional remainder preserved
  across ticks → expected value matches multiplier exactly, without
  stochastic variance.

sadp: R60 (override approved — user explicit override of 'run current
build' queue order this turn), R61 CBF (fail-loudly at sampling
thread boundary — no silent-swallow).
"""

from __future__ import annotations
import math
import threading
import time
from typing import Optional


def _cosine_ramp(phase: float) -> float:
    """Cosine ease-in-out: 0 → 1 smoothly over [0, 1].

    Uses 0.5 * (1 - cos(π × phase)). Zero derivative at both
    endpoints so the sustain edges don't kink.
    """
    phase = max(0.0, min(1.0, phase))
    return 0.5 * (1.0 - math.cos(math.pi * phase))


class SystemLoadOscillator:
    """Dual-oscillator for Nuclear Mode tick rate + per-tick workload.

    Thread-safe. Caller gets current multiplier via
    `current_multiplier()` on each tick; the engine scales both
    tick_interval (via division) and workload count (via integer
    accumulator).

    The oscillator starts at `start()`, which takes a monotonic
    reference time and spawns the COOLING monitor daemon. `stop()`
    joins the daemon and invalidates state. Safe to call stop()
    multiple times; calling current_multiplier() before start()
    returns BASE_MULTIPLIER.

    sadp: R61 CBF — sampling thread uses try/except with stderr
    surfacing, not silent swallow.
    """

    # ── Cycle geometry ─────────────────────────────────────────────
    CYCLE_SEC = 120.0  # full period
    RAMP_UP_SEC = 45.0  # cosine ease up
    SUSTAIN_SEC = 30.0  # flat at peak
    RAMP_DOWN_SEC = 45.0  # cosine ease down
    # Invariant: RAMP_UP + SUSTAIN + RAMP_DOWN == CYCLE_SEC

    # ── Intensity ─────────────────────────────────────────────────
    BASE_MULTIPLIER = 1.0
    PEAK_MULTIPLIER = 4.0
    COOLING_CAP = 1.5  # max multiplier while in COOLING

    # ── COOLING state machine ─────────────────────────────────────
    COOLING_EXIT_CALM_COUNT = 3  # consecutive CALM samples to exit

    # ── Sampling ──────────────────────────────────────────────────
    SAMPLING_HZ = 5.0  # samples per second (0.2s interval)

    def __init__(self, system_load_mr):
        """Initialize bound to a SystemLoadMR for COOLING detection.
        system_load_mr may be None for tests (COOLING never triggers).
        """
        self._sysmr = system_load_mr
        self._start_time: Optional[float] = None
        self._cooling: bool = False
        self._cooling_calm_count: int = 0
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # Workload accumulator — caller can use this via tick_workload()
        self._workload_accumulator: float = 0.0
        # Diagnostics
        self.cooling_enter_count = 0
        self.cooling_exit_count = 0
        self.samples_taken = 0

    # ══ Lifecycle ══════════════════════════════════════════════════

    def start(self):
        """Begin oscillation cycle + start COOLING monitor thread."""
        with self._lock:
            self._start_time = time.monotonic()
            self._cooling = False
            self._cooling_calm_count = 0
            self._workload_accumulator = 0.0
        if self._sysmr is not None:
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="SystemLoadOscillatorMonitor",
            )
            self._thread.start()

    def stop(self):
        """Stop COOLING monitor and clear state. Idempotent."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        with self._lock:
            self._start_time = None

    # ══ Public query API ═══════════════════════════════════════════

    def cycle_position(self) -> float:
        """Seconds into current 120s cycle, or 0 if not started."""
        with self._lock:
            st = self._start_time
        if st is None:
            return 0.0
        elapsed = time.monotonic() - st
        return elapsed % self.CYCLE_SEC

    def current_multiplier(self) -> float:
        """Multiplier in [BASE, PEAK], clamped by COOLING if active.

        Shape:
          0 ≤ t < 45  — cosine-ease ramp up (1.0 → 4.0)
          45 ≤ t < 75 — sustain at 4.0
          75 ≤ t < 120 — cosine-ease ramp down (4.0 → 1.0)
        """
        # Compute geometric multiplier first
        with self._lock:
            st = self._start_time
        if st is None:
            return self.BASE_MULTIPLIER

        t = (time.monotonic() - st) % self.CYCLE_SEC
        span = self.PEAK_MULTIPLIER - self.BASE_MULTIPLIER

        if t < self.RAMP_UP_SEC:
            phase = t / self.RAMP_UP_SEC
            m = self.BASE_MULTIPLIER + span * _cosine_ramp(phase)
        elif t < self.RAMP_UP_SEC + self.SUSTAIN_SEC:
            m = self.PEAK_MULTIPLIER
        else:
            phase = (t - self.RAMP_UP_SEC - self.SUSTAIN_SEC) / self.RAMP_DOWN_SEC
            m = self.PEAK_MULTIPLIER - span * _cosine_ramp(phase)

        # Clamp by COOLING state (read under lock)
        with self._lock:
            if self._cooling:
                m = min(m, self.COOLING_CAP)
        return m

    def tick_workload(self) -> int:
        """Return integer workload count for this tick using a
        deterministic accumulator. Expected value over many ticks
        equals current_multiplier exactly.

        Example: multiplier=2.3 produces sequence 2, 3, 2, 3, 2, 2, 3, ...
        (accumulator wraps: 2.3 → 2 (rem 0.3), +2.3=2.6 → 2 (rem 0.6),
        +2.3=2.9 → 2 (rem 0.9), +2.3=3.2 → 3 (rem 0.2), ...)

        Clamped to [1, ceil(PEAK)] so a bot always advances at
        least 1 candle per tick (engine invariant).
        """
        m = self.current_multiplier()
        with self._lock:
            self._workload_accumulator += m
            count = int(self._workload_accumulator)
            self._workload_accumulator -= count
        return max(1, min(count, int(math.ceil(self.PEAK_MULTIPLIER))))

    def effective_tick_interval(self, base_interval: float) -> float:
        """Return the interval the engine should sleep between ticks:
        base_interval divided by current multiplier. At peak 4x,
        base 0.8s → 0.2s."""
        m = self.current_multiplier()
        # Defensive: never divide by zero, always at least a floor
        m_safe = max(m, 0.1)
        return base_interval / m_safe

    @property
    def is_cooling(self) -> bool:
        """Whether COOLING state is active right now."""
        with self._lock:
            return self._cooling

    @property
    def started(self) -> bool:
        with self._lock:
            return self._start_time is not None

    # ══ Internal: COOLING monitor thread ═══════════════════════════

    def _monitor_loop(self):
        """Background sampler. Runs at SAMPLING_HZ independent of the
        engine tick rate. Writes COOLING state under lock.

        sadp: R61 CBF — any exception surfaces to stderr, does not
        silently kill the monitor.
        """
        interval = 1.0 / self.SAMPLING_HZ  # 0.2s by default
        while not self._stop_event.is_set():
            try:
                self._sysmr.sample(time.time())
                regime = self._sysmr.current_regime
                self.samples_taken += 1
                with self._lock:
                    if regime in ("STRESS", "CRITICAL"):
                        if not self._cooling:
                            self._cooling = True
                            self.cooling_enter_count += 1
                        self._cooling_calm_count = 0
                    elif regime == "CALM":
                        if self._cooling:
                            self._cooling_calm_count += 1
                            if self._cooling_calm_count >= self.COOLING_EXIT_CALM_COUNT:
                                self._cooling = False
                                self.cooling_exit_count += 1
                                self._cooling_calm_count = 0
                    # Anything else (e.g., new 'COOLING' regime if
                    # someone later renames): treat as non-CALM, don't
                    # exit COOLING
            except Exception as exc:
                # R61 CBF — surface, don't swallow
                import sys as _s, traceback as _tb

                _s.stderr.write(
                    f"SystemLoadOscillator sampler: " f"{type(exc).__name__}: {exc}\n"
                )
                _tb.print_exc(file=_s.stderr)
                # Don't kill the thread; back off one interval and try
                # again
            # Honor stop_event even during sleep — wait() returns early
            if self._stop_event.wait(timeout=interval):
                break
