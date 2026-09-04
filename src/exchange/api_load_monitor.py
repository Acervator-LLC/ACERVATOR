"""api_load_monitor.py — Per-exchange API load telemetry + gating.

Reads the process-wide APIInteractionLog and derives:
  * calls-per-minute (CPM) on a trailing window
  * P95 latency
  * a load_score in [0, 1] against the connector's rate ceiling
    (10 req/s = 600 CPM by default, matching CCXTConnector's
    _min_request_interval=0.1)

Provides two decision surfaces:
  * ``load_score(exchange_id)`` — read-only telemetry.
  * ``should_allow_new_phantom_set(exchange_id, tf_count)`` —
    refuses new phantom-set creation when the projected CPM
    would breach the safety threshold (default 75 % of ceiling).

Additive: does not mutate the log, does not throttle callers,
does not modify the connector's rate limit. Purely advisory.

sadp: R28 SSS + R70 RCN
v3.23.40 — Initial implementation (per phantom-bot design proposal
docs/engineering-notes/2026-07-27_phantom_bots_audit_and_design_proposal.md § 3.3).
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

# One phantom bot performs ~one exchange-heavy tick per candle.
# The heaviest single-tick call is the OHLCV fetch (fetch_ohlcv on
# the phantom's TF). Empirically this is ~1 API call per active
# candle-cycle, so a phantom's steady-state cost is well approximated
# as "1 CPM per phantom running on a sub-minute TF, less at higher
# TFs". Being conservative for the estimate keeps the operator on
# the safe side of the cap; the real steady-state is usually lower.
PHANTOM_CPM_ESTIMATE_PER_TF = 1.0


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

    def sample(self, exchange: str) -> LoadReading:
        """Compute a snapshot reading for one exchange."""
        entries = self._window_entries(exchange)
        n = len(entries)
        # calls per minute — scale to a 60 s equivalent regardless of window
        cpm = (n * 60.0 / self._window_s) if self._window_s > 0 else 0.0
        # P95 latency on the entries we have
        p95 = 0.0
        if entries:
            lat = sorted(float(e.get("elapsed_ms", 0) or 0) for e in entries)
            idx = max(0, min(len(lat) - 1, int(len(lat) * 0.95)))
            p95 = lat[idx]
        score = (
            min(1.0, max(0.0, cpm / self._ceiling_cpm))
            if self._ceiling_cpm > 0
            else 0.0
        )
        return LoadReading(
            exchange=exchange,
            window_seconds=self._window_s,
            call_count=n,
            calls_per_minute=round(cpm, 1),
            p95_latency_ms=round(p95, 1),
            load_score=round(score, 3),
            ceiling_cpm=self._ceiling_cpm,
        )

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
