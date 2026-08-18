"""v3.23.40 — api_load_monitor pin tests.

Covers CPM math, load_score bounds, P95 latency, and
should_allow_new_phantom_set gating against the 75 % threshold.

Uses a stub APIInteractionLog so tests don't depend on the process-wide
singleton or the real record() pipeline.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.exchange.api_load_monitor import (  # noqa: E402
    APILoadMonitor, LoadReading,
    DEFAULT_CEILING_CPM, DEFAULT_SAFETY_PCT,
    PHANTOM_CPM_ESTIMATE_PER_TF,
    get_load_monitor,
)


class _StubAPILog:
    """Minimal stub matching APIInteractionLog.get_for_exchange contract."""

    def __init__(self, entries: list[dict]):
        self._entries = entries

    def get_for_exchange(self, exchange: str, count: int = 50) -> list[dict]:
        return [e for e in self._entries if e["exchange"] == exchange][-count:]


def _mk_entry(exchange: str, ts: float, elapsed_ms: float = 50.0) -> dict:
    return {
        "exchange": exchange,
        "timestamp": ts,
        "elapsed_ms": elapsed_ms,
        "action": "TEST",
    }


def _monitor_with_entries(entries: list[dict], **kwargs) -> APILoadMonitor:
    mon = APILoadMonitor(**kwargs)
    stub = _StubAPILog(entries)
    mon._api_log = lambda: stub  # type: ignore[method-assign]
    return mon


class TestSample:
    def test_empty_returns_zero_cpm(self):
        mon = _monitor_with_entries([])
        r = mon.sample("coinbase")
        assert isinstance(r, LoadReading)
        assert r.call_count == 0
        assert r.calls_per_minute == 0.0
        assert r.load_score == 0.0
        assert r.exchange == "coinbase"

    def test_cpm_scales_to_60s_from_window(self):
        # 30 entries in a 60 s window → 30 CPM
        now = time.time()
        entries = [_mk_entry("coinbase", now - i * 0.5) for i in range(30)]
        mon = _monitor_with_entries(entries, window_seconds=60.0)
        r = mon.sample("coinbase")
        assert r.call_count == 30
        assert r.calls_per_minute == 30.0

    def test_load_score_bounded_at_1(self):
        # Ceiling 600 CPM; 1000 entries in 60 s = 1000 CPM → capped at 1.0
        now = time.time()
        entries = [_mk_entry("coinbase", now - i * 0.05)
                   for i in range(1000)]
        mon = _monitor_with_entries(
            entries, window_seconds=60.0, ceiling_cpm=600.0)
        r = mon.sample("coinbase")
        assert r.load_score == 1.0

    def test_out_of_window_entries_excluded(self):
        now = time.time()
        recent = [_mk_entry("coinbase", now - 5) for _ in range(10)]
        stale = [_mk_entry("coinbase", now - 120) for _ in range(50)]
        mon = _monitor_with_entries(recent + stale, window_seconds=60.0)
        r = mon.sample("coinbase")
        assert r.call_count == 10

    def test_p95_latency_computed(self):
        now = time.time()
        # 20 entries at 100 ms, one big 1000 ms outlier
        entries = [_mk_entry("coinbase", now - i, elapsed_ms=100.0)
                   for i in range(20)]
        entries.append(_mk_entry("coinbase", now - 0.5, elapsed_ms=1000.0))
        mon = _monitor_with_entries(entries)
        r = mon.sample("coinbase")
        assert r.p95_latency_ms >= 100.0
        # 21 entries: 95th percentile is the 20th (index 19)
        assert r.p95_latency_ms in (100.0, 1000.0)

    def test_other_exchange_ignored(self):
        now = time.time()
        entries = ([_mk_entry("coinbase", now - i) for i in range(5)]
                   + [_mk_entry("binance", now - i) for i in range(50)])
        mon = _monitor_with_entries(entries)
        assert mon.sample("coinbase").call_count == 5


class TestShouldAllowNewPhantomSet:
    def test_zero_tfs_always_allowed(self):
        mon = _monitor_with_entries([])
        allow, reason = mon.should_allow_new_phantom_set("coinbase", 0)
        assert allow is True
        assert "no phantoms" in reason.lower()

    def test_idle_exchange_permits_typical_set(self):
        # Idle → current CPM 0, adding 6 phantoms ~ 6 CPM, well below 450
        mon = _monitor_with_entries([])
        allow, reason = mon.should_allow_new_phantom_set("coinbase", 6)
        assert allow is True
        assert "OK" in reason

    def test_hot_exchange_refuses_new_set(self):
        # 500 CPM current → adding 6 = 506, threshold = 450 → refused
        now = time.time()
        entries = [_mk_entry("coinbase", now - i * 0.12)
                   for i in range(500)]
        mon = _monitor_with_entries(entries, window_seconds=60.0)
        allow, reason = mon.should_allow_new_phantom_set("coinbase", 6)
        assert allow is False
        assert "REFUSED" in reason
        assert "75" in reason  # threshold pct

    def test_threshold_boundary(self):
        # ceiling=600, safety=0.75 → threshold=450
        # If current=445 and tf_count=5 → projected=450 → equal, allowed
        now = time.time()
        entries = [_mk_entry("coinbase", now - i * 0.135)
                   for i in range(445)]
        mon = _monitor_with_entries(entries, window_seconds=60.0)
        allow, _r = mon.should_allow_new_phantom_set(
            "coinbase", int(5 / PHANTOM_CPM_ESTIMATE_PER_TF))
        # At the boundary, still allowed.
        assert allow is True

    def test_custom_safety_pct_applied(self):
        # ceiling=600, custom safety=0.5 → threshold=300
        now = time.time()
        entries = [_mk_entry("coinbase", now - i * 0.2)
                   for i in range(299)]
        mon = _monitor_with_entries(
            entries, window_seconds=60.0, safety_pct=0.5)
        # Just under threshold, adding 5 phantoms would push over
        allow, _r = mon.should_allow_new_phantom_set("coinbase", 5)
        assert allow is False


class TestSharedMonitor:
    def test_shared_instance_is_singleton(self):
        a = get_load_monitor()
        b = get_load_monitor()
        assert a is b
        assert isinstance(a, APILoadMonitor)


class TestDefaults:
    def test_ceiling_matches_connector_rate_limit(self):
        # Connector _min_request_interval=0.1s → 10 rps → 600 CPM
        assert DEFAULT_CEILING_CPM == 600.0

    def test_safety_default_is_75pct(self):
        assert DEFAULT_SAFETY_PCT == 0.75

    def test_phantom_cpm_estimate_is_conservative(self):
        # 1 CPM per phantom — see design proposal § 3.3
        assert PHANTOM_CPM_ESTIMATE_PER_TF == 1.0
