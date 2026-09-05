"""Nuclear Mode speed oscillator for tick rate and per-tick workload.

``SystemLoadOscillator.current_multiplier`` walks a ``CYCLE_SEC`` cycle:
``RAMP_UP_SEC`` of cosine rise, ``SUSTAIN_SEC`` at ``PEAK_MULTIPLIER``, then
``RAMP_DOWN_SEC`` back to ``BASE_MULTIPLIER``. A daemon samples
``SystemLoadMR`` at ``SAMPLING_HZ`` and caps the multiplier at
``COOLING_CAP`` until ``COOLING_EXIT_CALM_COUNT`` CALM samples follow.
``tick_workload`` returns the integer part of a running accumulator, so the
fractional remainder carries into the next tick.
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
    """Dual oscillator for Nuclear Mode tick rate and per-tick workload.

    ``start`` takes the monotonic reference and spawns the COOLING
    daemon; ``stop`` joins it and is idempotent. ``current_multiplier``
    returns ``BASE_MULTIPLIER`` before ``start``.
    """

    # RAMP_UP_SEC + SUSTAIN_SEC + RAMP_DOWN_SEC must equal CYCLE_SEC.
    CYCLE_SEC = 120.0
    RAMP_UP_SEC = 45.0
    SUSTAIN_SEC = 30.0
    RAMP_DOWN_SEC = 45.0

    BASE_MULTIPLIER = 1.0
    PEAK_MULTIPLIER = 4.0
    COOLING_CAP = 1.5  # ceiling applied while COOLING

    COOLING_EXIT_CALM_COUNT = 3  # consecutive CALM samples needed to exit

    SAMPLING_HZ = 5.0

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
        """Multiplier in [BASE_MULTIPLIER, PEAK_MULTIPLIER], capped while COOLING."""
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
        """Return this tick's integer workload count from the accumulator.

        The running mean equals ``current_multiplier``; the result is
        clamped to ``[1, ceil(PEAK_MULTIPLIER)]``.
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
            except Exception as exc:
                import sys as _s, traceback as _tb

                _s.stderr.write(
                    f"SystemLoadOscillator sampler: " f"{type(exc).__name__}: {exc}\n"
                )
                _tb.print_exc(file=_s.stderr)
            # wait() returns early on stop_event, so stop() is not delayed.
            if self._stop_event.wait(timeout=interval):
                break
