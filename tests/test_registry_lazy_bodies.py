"""v3.24.23 — pin tests for lazy Stone Tablet bodies.

THE DEFECT
==========
``StoneTabletsRegistry.__init__`` called ``read_tablet()`` for every
MANIFEST row, fully parsing all 406 tablet files. Measured against the
live archive:

    construction      13.154 s
    resident memory   +2,282 MB   (19.9 -> 2,301.9 MB)

``main.py:486`` builds the registry at app boot, so that was a 13 s
blocking startup stall and 2.3 GB held for the process lifetime — in the
process that executes real trades — for candle bodies boot never reads.

Boot asks for exactly ``coverage_summary()`` and ``stale_assets()``. Both
are answerable from MANIFEST metadata: its rows carry candle_count,
first_ts_ms, last_ts_ms and listed_at_ms, and summing candle_count over
the live manifest reproduces the archive total (7,230,993) exactly.

After: construction 0.008 s, +6.4 MB.

WHAT THESE TESTS DEFEND
=======================
Laziness is only safe if the metadata answers agree with the bodies. The
equivalence tests below are the ones that matter — a metadata path that
disagrees with the candles would be a silent wrong answer, which is worse
than a slow correct one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.stone_tablets.registry import (  # noqa: E402
    NATIVE_TIMEFRAME, StoneTabletsRegistry, WindowStatus,
)
from src.trading.stone_tablets.storage import (  # noqa: E402
    Tablet, TabletEntry, write_manifest, write_tablet,
)

_BASE = 1_774_915_200_000        # 2026-04-01T00:00:00Z
_STEP = 300_000                  # 5m


def _candles(n, start_ts=_BASE, px=100.0):
    return [[start_ts + i * _STEP, px, px * 1.01, px * 0.99,
             px * 1.005, 10.0 + i] for i in range(n)]


@pytest.fixture
def archive(tmp_path):
    """A small real archive on disk: 3 assets, known candle counts."""
    root = tmp_path / "stone_tablets"
    root.mkdir(parents=True)
    spec = {"BTC": 300, "ETH": 120, "SOL": 40}
    entries = []
    for asset, n in spec.items():
        tab = Tablet(asset=asset, exchange_id="coinbase",
                     timeframe=NATIVE_TIMEFRAME, year=2026,
                     source="test", fetched_at="2026-08-04",
                     candles=_candles(n))
        write_tablet(tab, root=root)
        entries.append(TabletEntry(
            asset=asset, exchange_id="coinbase",
            timeframe=NATIVE_TIMEFRAME, year=2026,
            file=f"{asset}_5m_2026_coinbase.json",
            checksum_sha256=tab.compute_checksum(), candle_count=n,
            first_ts_ms=tab.first_ts_ms, last_ts_ms=tab.last_ts_ms,
            fetched_at="2026-08-04", source="test",
            listed_at_ms=tab.first_ts_ms))
    write_manifest(entries, root=root)
    return root, spec


# ── laziness ─────────────────────────────────────────────────────

def test_construction_loads_no_bodies(archive):
    """The whole point: boot must not parse candle files."""
    root, spec = archive
    reg = StoneTabletsRegistry(root=root)
    assert reg._tablets == {}, "bodies loaded at construction"
    assert len(reg._entries) == len(spec)


def test_boot_path_queries_load_no_bodies(archive):
    """main.py:486 calls exactly these two. Neither may touch a body."""
    root, spec = archive
    reg = StoneTabletsRegistry(root=root)
    cov = reg.coverage_summary()
    stale = reg.stale_assets(now_ms=_BASE + _STEP * 400)
    assert reg._tablets == {}, (
        "boot-path query forced a body load: "
        f"{sorted(reg._tablets)}")
    assert len(cov) == len(spec)
    assert isinstance(stale, list)


def test_body_loads_only_when_candles_are_requested(archive):
    root, _ = archive
    reg = StoneTabletsRegistry(root=root)
    assert reg._tablets == {}
    reg.get_candles("BTC", _BASE, _BASE + _STEP * 50)
    assert ("BTC", "coinbase", NATIVE_TIMEFRAME, 2026) in reg._tablets
    assert ("ETH", "coinbase", NATIVE_TIMEFRAME, 2026) not in reg._tablets


# ── metadata answers agree with bodies ───────────────────────────

def test_coverage_totals_match_the_candle_bodies(archive):
    """Metadata-derived totals must equal what the bodies actually
    contain, or the fast path is silently lying."""
    root, spec = archive
    reg = StoneTabletsRegistry(root=root)
    by_asset = {c.asset: c for c in reg.coverage_summary()}
    for asset, n in spec.items():
        assert by_asset[asset].total_candles == n
        body = reg.get_candles(asset, 0, 10**15)
        assert len(body) == n, f"{asset}: metadata {n} != body {len(body)}"


def test_ts_bounds_match_the_bodies(archive):
    root, spec = archive
    reg = StoneTabletsRegistry(root=root)
    for asset, n in spec.items():
        cov = next(c for c in reg.coverage_summary() if c.asset == asset)
        rows = reg.get_candles(asset, 0, 10**15)
        assert cov.first_ts_ms == int(rows[0][0])
        assert cov.last_ts_ms == int(rows[-1][0])


def test_availability_matches_the_bodies(archive):
    root, spec = archive
    reg = StoneTabletsRegistry(root=root)
    for asset, n in spec.items():
        info = reg.get_asset_availability(asset)
        rows = reg.get_candles(asset, 0, 10**15)
        assert info is not None
        assert info.total_candles == n
        assert info.listed_at_ms == int(rows[0][0])
        assert info.last_ts_ms == int(rows[-1][0])


def test_get_candles_returns_the_requested_window(archive):
    root, _ = archive
    reg = StoneTabletsRegistry(root=root)
    lo, hi = _BASE + _STEP * 10, _BASE + _STEP * 20
    rows = reg.get_candles("BTC", lo, hi)
    assert len(rows) == 11
    assert all(lo <= int(r[0]) <= hi for r in rows)


def test_window_availability_still_classifies(archive):
    root, _ = archive
    reg = StoneTabletsRegistry(root=root)
    assert reg.check_window_availability(
        "BTC", _BASE, _BASE + _STEP * 299) == WindowStatus.FULL
    assert reg.check_window_availability(
        "NOPE", _BASE, _BASE + _STEP) == WindowStatus.EMPTY


def test_unknown_asset_returns_none(archive):
    root, _ = archive
    assert StoneTabletsRegistry(
        root=root).get_asset_availability("NOPE") is None


# ── missing / corrupt files ──────────────────────────────────────

def test_manifest_row_with_missing_file_is_skipped(archive):
    """Old behaviour was warn-and-skip at load. Lazy loading must keep
    it — via a cheap existence check, not a full parse."""
    root, spec = archive
    (root / "ETH_5m_2026_coinbase.json").unlink()
    reg = StoneTabletsRegistry(root=root)
    assets = {c.asset for c in reg.coverage_summary()}
    assert "ETH" not in assets
    assert "BTC" in assets


def test_corrupt_body_is_treated_as_absent(archive):
    """The file exists so the load-time stat passes; corruption is only
    discovered on first body read and must not raise."""
    root, _ = archive
    reg = StoneTabletsRegistry(root=root)
    (root / "SOL_5m_2026_coinbase.json").write_text(
        "{ not json", encoding="utf-8")
    assert reg.get_candles("SOL", 0, 10**15) == []


# ── the body cache is bounded ────────────────────────────────────

def test_cache_is_evicted_past_the_cap(archive, monkeypatch):
    """Without a cap, a 406-asset sweep re-accumulates the 2.3 GB this
    change exists to avoid."""
    from src.trading.stone_tablets import registry as R
    root, spec = archive
    monkeypatch.setattr(R, "_BODY_CACHE_MAX", 2)
    reg = R.StoneTabletsRegistry(root=root)
    for asset in spec:
        reg.get_candles(asset, 0, 10**15)
    assert len(reg._tablets) <= 2


def test_eviction_does_not_lose_data(archive, monkeypatch):
    """An evicted body must reload transparently and return the same
    candles."""
    from src.trading.stone_tablets import registry as R
    root, spec = archive
    monkeypatch.setattr(R, "_BODY_CACHE_MAX", 1)
    reg = R.StoneTabletsRegistry(root=root)
    first = reg.get_candles("BTC", 0, 10**15)
    for asset in spec:
        reg.get_candles(asset, 0, 10**15)
    again = reg.get_candles("BTC", 0, 10**15)
    assert again == first


# ── ingest ───────────────────────────────────────────────────────

def test_ingest_appends_and_updates_metadata(archive):
    root, spec = archive
    reg = StoneTabletsRegistry(root=root)
    new = _candles(5, start_ts=_BASE + _STEP * 1000, px=200.0)
    added = reg.ingest_candles("BTC", NATIVE_TIMEFRAME, new, "test")
    assert added == 5
    cov = next(c for c in reg.coverage_summary() if c.asset == "BTC")
    assert cov.total_candles == spec["BTC"] + 5


def test_ingest_survives_a_fresh_registry(archive):
    """Metadata written by ingest must be readable by the next process."""
    root, spec = archive
    reg = StoneTabletsRegistry(root=root)
    reg.ingest_candles(
        "BTC", NATIVE_TIMEFRAME,
        _candles(7, start_ts=_BASE + _STEP * 2000, px=300.0), "test")
    reloaded = StoneTabletsRegistry(root=root)
    cov = next(c for c in reloaded.coverage_summary() if c.asset == "BTC")
    assert cov.total_candles == spec["BTC"] + 7


def test_ingest_does_not_drop_other_manifest_rows(archive):
    """_persist_manifest rebuilds from the index. If it rebuilt from the
    loaded-body cache instead, every un-loaded asset would vanish from
    MANIFEST on the first ingest."""
    root, spec = archive
    reg = StoneTabletsRegistry(root=root)
    reg.ingest_candles(
        "BTC", NATIVE_TIMEFRAME,
        _candles(3, start_ts=_BASE + _STEP * 3000), "test")
    reloaded = StoneTabletsRegistry(root=root)
    assets = {c.asset for c in reloaded.coverage_summary()}
    assert assets == set(spec), f"manifest rows lost: {set(spec) - assets}"


def test_ingest_of_a_new_asset_works(archive):
    root, _ = archive
    reg = StoneTabletsRegistry(root=root)
    added = reg.ingest_candles(
        "DOGE", NATIVE_TIMEFRAME, _candles(9), "test")
    assert added == 9
    reloaded = StoneTabletsRegistry(root=root)
    assert "DOGE" in {c.asset for c in reloaded.coverage_summary()}


def test_duplicate_ingest_is_a_noop(archive):
    root, _ = archive
    reg = StoneTabletsRegistry(root=root)
    rows = _candles(4, start_ts=_BASE + _STEP * 5000)
    assert reg.ingest_candles("BTC", NATIVE_TIMEFRAME, rows, "t") == 4
    assert reg.ingest_candles("BTC", NATIVE_TIMEFRAME, rows, "t") == 0
