# ruff: noqa: S311
# S311 (non-cryptographic RNG) is deliberate throughout: these tests seed
# the market-structure noise generator to assert reproducibility. Nothing
# here is security-relevant.
"""v3.24.20 — pin tests for Nuclear Mode tape sourcing + noise injection.

WHY THIS EXISTS
===============
Nuclear Mode was inert. ``NuclearCandleSource`` scanned only
``sadp/RAIntSimBat/data/cache/*.json``, a directory that does not exist in
this tree — SADP was deprecated as an authority and that cache went with
it. So ``list_tapes()`` returned [] on every call, the panel rendered its
empty state, and the panel's remedy text told the operator to "run an
RAIntSimBat battery", an instruction that could no longer be followed.

Tapes now come from the Stone Tablet archive: 406 assets / 7,230,993 real
5m candles. That matches what tapes were always supposed to be —

    "They represent organic price action data ... The injected, smoothed
    randomized data that is used instead of this has always been a
    sticking point for me."   -- operator, 2026-05-20

NOISE INJECTION (operator directive 2026-08-04)
===============================================
    "plays tapes forward and then backwards with a 10~25% random noise
    injection to vary the market structure conditions"

and the hard constraint that followed:

    "the noise injector CANNOT cause permanent edits or corruption to the
    Stone Tablets."

The immutability tests below are the ones that matter most. They assert
byte-level stability of the tablet files across a full noisy playback,
not merely that the code "looks read-only".
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.simulator.nuclear_candle_source import (  # noqa: E402
    _NOISE_MAX_PCT,
    _NOISE_MIN_PCT,
    NuclearCandleSource,
    _Tape,
)
from src.trading.stone_tablets.storage import (  # noqa: E402
    Tablet,
    TabletEntry,
    write_manifest,
    write_tablet,
)

_BASE_TS = 1_774_915_200_000  # 2026-04-01T00:00:00Z


def _make_candles(n: int, start: float = 100.0) -> list[list[float]]:
    out = []
    px = start
    for i in range(n):
        px *= 1.0 + (0.01 if i % 3 else -0.008)
        o = px
        c = px * 1.004
        out.append([_BASE_TS + i * 300_000, o, c * 1.002, o * 0.998, c, 10.0 + i])
    return out


@pytest.fixture
def tablet_root(tmp_path, monkeypatch):
    """A throwaway tablet archive. Never touches ~/.acervator."""
    from src.trading.stone_tablets import storage as S

    root = tmp_path / "stone_tablets"
    root.mkdir(parents=True)
    monkeypatch.setattr(S, "STONE_TABLETS_DIR", root)

    entries = []
    for asset, n in (("BTC", 400), ("ETH", 300), ("TINY", 5)):
        tab = Tablet(
            asset=asset,
            exchange_id="coinbase",
            timeframe="5m",
            year=2026,
            source="test",
            fetched_at="2026-08-04",
            candles=_make_candles(n),
        )
        write_tablet(tab, root=root)
        entries.append(
            TabletEntry(
                asset=asset,
                exchange_id="coinbase",
                timeframe="5m",
                year=2026,
                file=f"{asset}_5m_2026_coinbase.json",
                checksum_sha256=tab.compute_checksum(),
                candle_count=n,
                first_ts_ms=tab.first_ts_ms,
                last_ts_ms=tab.last_ts_ms,
                fetched_at="2026-08-04",
                source="test",
                listed_at_ms=tab.first_ts_ms,
            )
        )
    write_manifest(entries, root=root)
    return root


def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.glob("*.json")):
        h.update(p.name.encode())
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def _src(tablet_root, **kw) -> NuclearCandleSource:
    # cache_dir points at a nonexistent path so the tablet path is taken.
    return NuclearCandleSource(cache_dir=tablet_root / "_no_legacy_cache", **kw)


# ── sourcing ─────────────────────────────────────────────────────


def test_tapes_are_built_from_tablets(tablet_root):
    s = _src(tablet_root)
    assert s.has_any_tapes()
    assert s.list_tapes() == ["A", "B"]  # TINY is below the floor


def test_tablets_below_the_candle_floor_are_rejected(tablet_root):
    """A 5-candle tablet cannot warm up TA and must not become a tape."""
    s = _src(tablet_root)
    assert all("TINY" not in s.tape_label(t) for t in s.list_tapes())


def test_largest_tablet_becomes_tape_a(tablet_root):
    """Selection is by candle count descending, so the fullest history
    is always Tape A."""
    s = _src(tablet_root)
    assert "BTC" in s.tape_label("A")
    assert "ETH" in s.tape_label("B")


def test_max_tapes_is_respected(tablet_root):
    assert _src(tablet_root, max_tapes=1).list_tapes() == ["A"]


def test_legacy_cache_wins_when_present(tablet_root, tmp_path):
    """An operator who restores the RAIntSimBat tree keeps their tape
    ids; the tablet path is a fallback, not a takeover."""
    cache = tmp_path / "legacy"
    cache.mkdir()
    (cache / "aaa.json").write_text(
        json.dumps({"symbol": "LEGACY", "year": "2023", "candles": _make_candles(50)}),
        encoding="utf-8",
    )
    s = NuclearCandleSource(cache_dir=cache)
    assert "LEGACY" in s.tape_label("A")


def test_empty_manifest_yields_no_tapes(tmp_path, monkeypatch):
    from src.trading.stone_tablets import storage as S

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(S, "STONE_TABLETS_DIR", empty)
    s = NuclearCandleSource(cache_dir=tmp_path / "nope")
    assert s.list_tapes() == []
    assert s.has_any_tapes() is False


# ── the immutability constraint ──────────────────────────────────


def test_playback_does_not_alter_tablet_files(tablet_root):
    """Operator directive: the noise injector CANNOT cause permanent
    edits or corruption to the Stone Tablets. Asserted at byte level."""
    before = _tree_digest(tablet_root)
    s = _src(tablet_root)
    s.wire("A")
    for _ in range(1200):  # enough to wrap several times
        s.advance("A")
        s.history("A", 60)
    assert _tree_digest(tablet_root) == before


def test_perturbation_does_not_mutate_in_memory_candles(tablet_root):
    s = _src(tablet_root)
    s.wire("A")
    snapshot = [tuple(c) for c in s._tapes["A"].candles]
    for _ in range(400):
        s.advance("A")
        s.history("A", 30)
    assert [tuple(c) for c in s._tapes["A"].candles] == snapshot


def test_history_returns_a_new_list_each_call(tablet_root):
    """A caller mutating the returned window must not affect the tape.

    The cursor is advanced first: history() is bounded by cursor+1, so a
    freshly-wired tape legitimately returns a single candle.
    """
    s = _src(tablet_root)
    s.wire("A")
    for _ in range(50):
        s.advance("A")
    a = s.history("A", 20)
    assert len(a) == 20
    a.append(("poison",))
    assert len(s.history("A", 20)) == 20


# ── noise behaviour ──────────────────────────────────────────────


def test_noise_amplitude_is_inside_the_directed_band(tablet_root):
    s = _src(tablet_root)
    s.wire("A")
    seen = []
    for _ in range(1500):
        s.advance("A")
        seen.append(s._tapes["A"].noise_pct)
    assert seen, "no samples"
    assert all(
        _NOISE_MIN_PCT <= p <= _NOISE_MAX_PCT for p in seen
    ), f"noise outside 10-25%: min={min(seen)} max={max(seen)}"


def test_first_pass_is_already_noised(tablet_root):
    """If only later passes varied, the bot would meet clean data
    exactly once — the least useful ordering.

    v3.24.28: noise is rolled when the body loads, which is wire()
    time now that discovery is metadata-only. The guarantee is
    unchanged — the first PLAYED pass is noised — but it is observable
    only after wiring.
    """
    s = _src(tablet_root)
    s.wire("A")
    assert s._tapes["A"].noise_pct >= _NOISE_MIN_PCT


def test_reads_are_stable_within_a_pass(tablet_root):
    """TA recomputes over the same indices every tick. If the values
    moved between reads, indicators would be computed over a series that
    never existed."""
    s = _src(tablet_root)
    s.wire("A")
    for _ in range(37):
        s.advance("A")
    assert s.history("A", 50) == s.history("A", 50)
    assert s.current("A") == s.current("A")


def test_noise_changes_the_series_from_raw(tablet_root):
    s = _src(tablet_root)
    s.wire("A")
    raw = s._tapes["A"].candles[10]
    got = s._tapes["A"]._at(10)
    assert got != raw, "noise had no effect"
    assert got[0] == raw[0], "timestamp must never be perturbed"


def test_noise_can_be_disabled(tablet_root):
    s = _src(tablet_root, noise_enabled=False)
    s.wire("A")  # bodies are lazy as of v3.24.28
    tape = s._tapes["A"]
    assert tape._at(10) == tape.candles[10]


def test_seeded_runs_are_reproducible(tablet_root):
    a = _src(tablet_root, noise_rng_seed=1234)
    b = _src(tablet_root, noise_rng_seed=1234)
    a.wire("A")
    b.wire("A")
    for _ in range(120):
        a.advance("A")
        b.advance("A")
    assert a.history("A", 40) == b.history("A", 40)


def test_different_seeds_diverge(tablet_root):
    a = _src(tablet_root, noise_rng_seed=1)
    b = _src(tablet_root, noise_rng_seed=2)
    a.wire("A")
    b.wire("A")
    assert a.history("A", 40) != b.history("A", 40)


# ── candle wellformedness under noise ────────────────────────────


def test_ohlc_invariant_survives_perturbation(tablet_root):
    """A noisy candle must still be a well-formed candle: high brackets
    every price, low is bracketed by every price."""
    s = _src(tablet_root)
    tape = s._tapes["A"]
    for i in range(len(tape.candles)):
        _ts, o, h, low, c, v = tape._at(i)
        assert h >= max(o, c, low), f"high < body at {i}"
        assert low <= min(o, c, h), f"low > body at {i}"
        assert v >= 0.0, f"negative volume at {i}"


def test_prices_stay_strictly_positive(tablet_root):
    """A zero or negative price divides through position sizing, VWAP and
    every percentage gate."""
    s = _src(tablet_root)
    tape = s._tapes["A"]
    tape.noise_pct = _NOISE_MAX_PCT
    for i in range(len(tape.candles)):
        _ts, o, h, low, c, _v = tape._at(i)
        assert min(o, h, low, c) > 0.0, f"non-positive price at {i}"


def test_timestamps_are_never_perturbed(tablet_root):
    s = _src(tablet_root)
    tape = s._tapes["A"]
    for i in range(0, len(tape.candles), 17):
        assert tape._at(i)[0] == tape.candles[i][0]


def test_reroll_moves_the_band_not_the_timestamps():
    """Unit-level: reroll only touches amplitude + seed."""
    import random

    t = _Tape(
        tape_id="A",
        label="x",
        source_file="f",
        symbol_source="X",
        period_source="2026",
        candles=_make_candles(40),
    )
    t.reroll_noise(random.Random(7))
    first = t.noise_pct
    t.reroll_noise(random.Random(8))
    assert t.noise_pct != first
    assert _NOISE_MIN_PCT <= t.noise_pct <= _NOISE_MAX_PCT
