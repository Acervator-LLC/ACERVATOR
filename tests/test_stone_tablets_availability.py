"""v3.24.6 — pin tests for tablet availability metadata + WindowStatus.

Covers:
    A1  AvailabilityInfo.listed_at_iso formats correctly
    A2  AvailabilityInfo.is_listed_before boundary
    A3  AvailabilityInfo.listing_notice content
    A4  Registry.get_asset_availability returns None when empty
    A5  Registry.get_asset_availability aggregates listing across years
    A6  WindowStatus.EMPTY on missing asset
    A7  WindowStatus.FULL when tablet covers window (with listing tolerance)
    A8  WindowStatus.LATE_LISTING when asset listed after tolerance
    A9  WindowStatus.STALE when tablet ends more than stale_threshold ago
    A10 WindowStatus.LATE_AND_STALE when both conditions hit
    A11 storage.py — TabletEntry round-trips listed_at_ms through manifest
    A12 storage.py — read_manifest fallback: missing field derives from
        first_ts_ms (backward-compat with pre-v3.24.6 manifests)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.stone_tablets import (  # noqa: E402
    AvailabilityInfo, StoneTabletsRegistry, WindowStatus,
)
from src.trading.stone_tablets.storage import (  # noqa: E402
    TabletEntry, read_manifest, write_manifest,
)

# 5m constants
STEP = 300_000  # ms
_ANCHOR = 1_735_689_600_000  # 2025-01-01T00:00:00Z


def _rows(start_ms: int, n: int, price: float = 100.0) -> list:
    return [[start_ms + i * STEP, price, price + 1, price - 1,
             price + 0.5, 5.0] for i in range(n)]


# ---- A1 ----
def test_availability_info_listed_at_iso():
    a = AvailabilityInfo(
        asset="BTC", exchange_id="coinbase",
        listed_at_ms=1_735_689_600_000,  # 2025-01-01 00:00
        last_ts_ms=1_735_776_000_000, total_candles=100,
        tablet_count=1)
    assert a.listed_at_iso == "2025-01-01"


def test_availability_info_listed_at_iso_empty_when_zero():
    a = AvailabilityInfo(
        asset="X", exchange_id="coinbase",
        listed_at_ms=0, last_ts_ms=0,
        total_candles=0, tablet_count=0)
    assert a.listed_at_iso == ""


# ---- A2 ----
def test_is_listed_before_boundary():
    a = AvailabilityInfo(
        asset="X", exchange_id="coinbase",
        listed_at_ms=1000, last_ts_ms=2000,
        total_candles=10, tablet_count=1)
    assert a.is_listed_before(999) is False
    assert a.is_listed_before(1000) is True   # inclusive boundary
    assert a.is_listed_before(2000) is True
    # Zero listing is treated as "no data" — never listed before anything
    b = AvailabilityInfo(
        asset="Y", exchange_id="coinbase",
        listed_at_ms=0, last_ts_ms=0,
        total_candles=0, tablet_count=0)
    assert b.is_listed_before(9999) is False


# ---- A3 ----
def test_listing_notice_content():
    a = AvailabilityInfo(
        asset="ADA", exchange_id="coinbase",
        listed_at_ms=1_735_689_600_000, last_ts_ms=1_735_776_000_000,
        total_candles=100, tablet_count=1)
    msg = a.listing_notice("Coinbase")
    assert "ADA" in msg
    assert "Coinbase" in msg
    assert "2025-01-01" in msg
    assert "no prior data" in msg


def test_listing_notice_empty_variant():
    a = AvailabilityInfo(
        asset="XYZ", exchange_id="coinbase",
        listed_at_ms=0, last_ts_ms=0,
        total_candles=0, tablet_count=0)
    msg = a.listing_notice("Coinbase")
    assert "no data" in msg


# ---- A4 ----
def test_get_asset_availability_none_when_missing(tmp_path):
    reg = StoneTabletsRegistry(root=tmp_path)
    assert reg.get_asset_availability("NOTHERE") is None


# ---- A5 ----
def test_get_asset_availability_aggregates(tmp_path):
    """Tablet split across two years — availability aggregates
    listed_at from earliest tablet, last_ts from latest."""
    reg = StoneTabletsRegistry(root=tmp_path)
    # 2025 rows
    reg.ingest_candles(
        asset="BTC", timeframe="5m",
        rows=_rows(_ANCHOR, 100), source="test",
        exchange_id="coinbase")
    # 2026 rows
    _2026 = 1_767_225_600_000  # 2026-01-01
    reg.ingest_candles(
        asset="BTC", timeframe="5m",
        rows=_rows(_2026, 200), source="test",
        exchange_id="coinbase")
    info = reg.get_asset_availability("BTC")
    assert info is not None
    assert info.tablet_count == 2      # two years = two tablets
    assert info.total_candles == 300
    assert info.listed_at_ms == _ANCHOR
    assert info.last_ts_ms == _2026 + 199 * STEP


# ---- A6 ----
def test_window_status_empty_on_missing_asset(tmp_path):
    reg = StoneTabletsRegistry(root=tmp_path)
    st = reg.check_window_availability(
        "NOTHERE", since_ms=_ANCHOR, until_ms=_ANCHOR + 999 * STEP)
    assert st == WindowStatus.EMPTY


# ---- A7 ----
def test_window_status_full_within_tolerance(tmp_path):
    reg = StoneTabletsRegistry(root=tmp_path)
    # Tablet starts at ANCHOR + 15min (within default 24h tolerance).
    # Last candle = now.
    import time
    now_ms = int(time.time() * 1000)
    reg.ingest_candles(
        asset="X", timeframe="5m",
        rows=[[_ANCHOR + 15 * 60_000, 100, 101, 99, 100, 5],
              [now_ms, 100, 101, 99, 100, 5]],
        source="test", exchange_id="coinbase")
    st = reg.check_window_availability("X", _ANCHOR, now_ms)
    assert st == WindowStatus.FULL


# ---- A8 ----
def test_window_status_late_listing_beyond_tolerance(tmp_path):
    reg = StoneTabletsRegistry(root=tmp_path)
    import time
    now_ms = int(time.time() * 1000)
    # Tablet starts 2 days after since_ms — beyond default 24h tolerance.
    reg.ingest_candles(
        asset="X", timeframe="5m",
        rows=[[_ANCHOR + 2 * 86_400_000, 100, 101, 99, 100, 5],
              [now_ms, 100, 101, 99, 100, 5]],
        source="test", exchange_id="coinbase")
    st = reg.check_window_availability("X", _ANCHOR, now_ms)
    assert st == WindowStatus.LATE_LISTING


# ---- A9 ----
def test_window_status_stale_when_last_ts_old(tmp_path):
    reg = StoneTabletsRegistry(root=tmp_path)
    import time
    now_ms = int(time.time() * 1000)
    # Last candle 3 days ago — beyond default 24h stale threshold.
    reg.ingest_candles(
        asset="X", timeframe="5m",
        rows=[[_ANCHOR, 100, 101, 99, 100, 5],
              [now_ms - 3 * 86_400_000, 100, 101, 99, 100, 5]],
        source="test", exchange_id="coinbase")
    st = reg.check_window_availability("X", _ANCHOR, now_ms)
    assert st == WindowStatus.STALE


# ---- A10 ----
def test_window_status_late_and_stale(tmp_path):
    reg = StoneTabletsRegistry(root=tmp_path)
    import time
    now_ms = int(time.time() * 1000)
    reg.ingest_candles(
        asset="X", timeframe="5m",
        rows=[[_ANCHOR + 2 * 86_400_000, 100, 101, 99, 100, 5],
              [now_ms - 3 * 86_400_000, 100, 101, 99, 100, 5]],
        source="test", exchange_id="coinbase")
    st = reg.check_window_availability("X", _ANCHOR, now_ms)
    assert st == WindowStatus.LATE_AND_STALE


# ---- A11 ----
def test_tablet_entry_roundtrips_listed_at_ms(tmp_path):
    e = TabletEntry(
        asset="X", exchange_id="coinbase", timeframe="5m",
        year=2026, file="X_5m_2026_coinbase.json",
        checksum_sha256="a" * 64, candle_count=100,
        first_ts_ms=1000, last_ts_ms=2000,
        fetched_at="2026-08-01T00:00:00Z", source="test",
        listed_at_ms=1000)
    write_manifest([e], root=tmp_path)
    loaded = read_manifest(root=tmp_path)
    assert len(loaded) == 1
    assert loaded[0].listed_at_ms == 1000


# ---- A12 ----
def test_read_manifest_backward_compat_missing_listed_at_ms(tmp_path):
    """Old manifest with no listed_at_ms field must derive it from
    first_ts_ms (v3.24.5 registry state that we don't want to force
    a migration on)."""
    mf = {
        "schema_version": 2,
        "generated_at": "2026-08-01T00:00:00Z",
        "tablets": [{
            "asset": "X",
            "exchange_id": "coinbase",
            "timeframe": "5m",
            "year": 2026,
            "file": "X_5m_2026_coinbase.json",
            "checksum_sha256": "a" * 64,
            "candle_count": 100,
            "first_ts_ms": 1234,
            "last_ts_ms": 5678,
            "fetched_at": "2026-08-01T00:00:00Z",
            "source": "test",
            # NO listed_at_ms field — mimics pre-v3.24.6 manifests
        }],
    }
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps(mf), encoding="utf-8")
    loaded = read_manifest(root=tmp_path)
    assert len(loaded) == 1
    assert loaded[0].listed_at_ms == 1234  # fell back to first_ts_ms
