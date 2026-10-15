"""Per-exchange API load telemetry, read from the APIInteractionLog.

``sample`` derives calls-per-minute over a trailing window, the P95 of the
venue's own answer and of the wait for a connector worker, the share of the
window that worker was busy, and the calls its queue refused.
``should_allow_new_phantom_set`` refuses a new phantom set whose projected CPM
would breach ``DEFAULT_CEILING_CPM``, and no call here mutates the log or
throttles the connector.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("acervator.api_load_monitor")


DEFAULT_CEILING_CPM = 600.0  # 10 rps × 60 s (matches connector 100 ms floor)
DEFAULT_SAFETY_PCT = 0.75  # refuse new phantoms above this
DEFAULT_WINDOW_SECONDS = 60.0

# One worker serves every sync call on a connector, so the calls a connector can
# serve in a window is bounded by how long the venue takes, not by the request
# floor DEFAULT_CEILING_CPM is derived from.
SERIAL_WORKERS_PER_CONNECTOR = 1

# One phantom costs about one `fetch_ohlcv` per candle on its own
# timeframe, which is fewer calls per minute above 1m.
PHANTOM_CPM_ESTIMATE_PER_TF = 1.0


def _percentile(entries: list, field: str, share: float) -> float:
    """The ``share`` percentile of ``field`` across ``entries``, 0.0 when empty."""
    values = sorted(float(e.get(field, 0) or 0) for e in entries)
    if not values:
        return 0.0
    return values[max(0, min(len(values) - 1, int(len(values) * share)))]


@dataclass
class LoadReading:
    """Snapshot of one exchange's recent API load."""

    exchange: str
    window_seconds: float
    call_count: int
    calls_per_minute: float
    p95_latency_ms: float
    load_score: float  # in [0, 1] against ceiling
    ceiling_cpm: float
    p95_queued_ms: float = 0.0
    worker_busy_pct: float = 0.0
    queue_refusals: int = 0


class APILoadMonitor:
    """Read-only telemetry over the shared APIInteractionLog."""

    def __init__(
        self,
        ceiling_cpm: float = DEFAULT_CEILING_CPM,
        safety_pct: float = DEFAULT_SAFETY_PCT,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
    ):
        self._ceiling_cpm = float(ceiling_cpm)
        self._safety_pct = float(safety_pct)
        self._window_s = float(window_seconds)

    @property
    def ceiling_cpm(self) -> float:
        return self._ceiling_cpm

    @property
    def safety_pct(self) -> float:
        return self._safety_pct

    def _api_log(self):
        """Late import so headless tests can stub the log module."""
        from .api_logger import get_api_log

        return get_api_log()

    def _window_entries(self, exchange: str) -> list:
        now = time.time()
        cutoff = now - self._window_s
        try:
            all_entries = self._api_log().get_for_exchange(exchange, count=10_000)
        except Exception as _exc:  # noqa: BLE001 - probe best-effort
            logger.debug("api_log.get_for_exchange failed for %s: %s", exchange, _exc)
            return []
        return [e for e in all_entries if float(e.get("timestamp", 0) or 0) >= cutoff]

    def sample(self, exchange: str, connector=None) -> LoadReading:
        """Compute a snapshot reading for one exchange.

        ``worker_busy_pct`` is the share of the window the venue's own answers
        held a connector worker, and ``load_score`` is the worse of it and the
        calls-per-minute score, because a refused call reaches no log and so
        reads as idleness in the count alone.
        """
        entries = self._window_entries(exchange)
        n = len(entries)
        # calls per minute — scale to a 60 s equivalent regardless of window
        cpm = (n * 60.0 / self._window_s) if self._window_s > 0 else 0.0
        p95 = _percentile(entries, "elapsed_ms", 0.95)
        p95_queued = _percentile(entries, "queued_ms", 0.95)
        served_s = sum(float(e.get("elapsed_ms", 0) or 0) for e in entries) / 1000.0
        load = self._queue_load(connector)
        workers = max(1, int(load.get("workers", SERIAL_WORKERS_PER_CONNECTOR)))
        busy = (served_s / (self._window_s * workers)) if self._window_s > 0 else 0.0
        cpm_score = (
            min(1.0, max(0.0, cpm / self._ceiling_cpm))
            if self._ceiling_cpm > 0
            else 0.0
        )
        score = max(cpm_score, min(1.0, max(0.0, busy)))
        return LoadReading(
            exchange=exchange,
            window_seconds=self._window_s,
            call_count=n,
            calls_per_minute=round(cpm, 1),
            p95_latency_ms=round(p95, 1),
            load_score=round(score, 3),
            ceiling_cpm=self._ceiling_cpm,
            p95_queued_ms=round(p95_queued, 1),
            worker_busy_pct=round(100.0 * busy, 1),
            queue_refusals=int(load.get("refusals", 0) or 0),
        )

    @staticmethod
    def _queue_load(connector) -> dict:
        """``connector.sync_queue_load()``, or an empty reading without one."""
        reader = getattr(connector, "sync_queue_load", None)
        if reader is None:
            return {}
        try:
            load = reader()
        except Exception as exc:  # noqa: BLE001 - telemetry best-effort
            logger.debug("sync_queue_load failed: %s", exc)
            return {}
        return load if isinstance(load, dict) else {}

    def load_score(self, exchange: str) -> float:
        """Convenience: just the [0, 1] score."""
        return self.sample(exchange).load_score

    def projected_cpm_with_new_phantoms(self, exchange: str, tf_count: int) -> float:
        """Estimate current CPM plus what a new N-phantom set adds."""
        current = self.sample(exchange).calls_per_minute
        added = max(0, int(tf_count)) * PHANTOM_CPM_ESTIMATE_PER_TF
        return current + added

    def should_allow_new_phantom_set(
        self, exchange: str, tf_count: int
    ) -> tuple[bool, str]:
        """Decide whether spawning a fresh phantom set is safe.

        Returns ``(allow, reason)``. ``allow=False`` when the projected
        post-spawn CPM exceeds ``safety_pct × ceiling_cpm``. The reason
        string is intended for operator display.
        """
        if tf_count <= 0:
            return True, "no phantoms requested"
        reading = self.sample(exchange)
        threshold = self._safety_pct * self._ceiling_cpm
        added = tf_count * PHANTOM_CPM_ESTIMATE_PER_TF
        projected = reading.calls_per_minute + added
        if projected <= threshold:
            return True, (
                f"OK — projected {projected:.0f} CPM "
                f"(threshold {threshold:.0f} = "
                f"{int(self._safety_pct * 100)} % of "
                f"{self._ceiling_cpm:.0f})"
            )
        return False, (
            f"REFUSED — projected {projected:.0f} CPM would exceed "
            f"safety threshold {threshold:.0f} "
            f"({int(self._safety_pct * 100)} % of "
            f"{self._ceiling_cpm:.0f}). Current load: "
            f"{reading.calls_per_minute:.0f} CPM "
            f"({int(reading.load_score * 100)} %). Try again after "
            f"load drops, or reduce the phantom timeframe count."
        )


# Process-wide shared monitor

_GLOBAL_MONITOR: Optional[APILoadMonitor] = None


def get_load_monitor() -> APILoadMonitor:
    global _GLOBAL_MONITOR
    if _GLOBAL_MONITOR is None:
        _GLOBAL_MONITOR = APILoadMonitor()
    return _GLOBAL_MONITOR
