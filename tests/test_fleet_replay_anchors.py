"""Anchor indices must live in the master clock's index space (NF-18).

THE DEFECT. `build_anchor_indices` computed a slot on a gapless ruler:

    idx = int((float(ts) * 1000.0 - base_ts_ms) // step_ms)   # step_ms = 300_000

The value it is compared against is a different space entirely. The run loop
tests `candle_i not in self._anchor_indices`, and `candle_i` is the MasterClock
cursor — a position in `sorted(union_of_all_series_timestamps)`. Nothing
converted between them.

The two spaces agree only while the union is gapless. Every missing 5-minute
slot in the union shifts every later candle's position one earlier, so a trade
after k missing slots anchors k candles too late.

WHY THE EXISTING TESTS DID NOT CATCH IT. `tests/test_fleet_replay_controller.py`
builds `base` and `n_candles` inside one synthetic uniform grid, so union ==
grid and those tests pass identically whether or not the defect exists. They
have no positive control for this defect class. The tests below plant a gap,
which is the only thing that separates the two spaces.

SEVERITY, HONESTLY. Latent on the operator's normal soft-start window, whose
union has no gaps. Active on the full-YTD path, where the union is missing 78
slots. Under warmup=100 the true trade candle is still inside
`range(idx - 100, idx + 1)`, so today's damage is warm-up truncation — 22 real
warm-up candles instead of 100 — plus one trade dropped by the `idx >=
n_candles` guard. It becomes a genuinely MISSED trade candle only once drift
exceeds the warm-up. Margin: 22 candles.

THE SECOND HALF. The BOUND was in the wrong space too. The panel passes
`progress.total_candles or max(len(r) for r in candles.values())`, and
`progress.total_candles` is assigned inside `start()` — which runs AFTER
`_build_sim()` and after the panel has already built its anchors. The `or`
fallback therefore fired on every run, making the bound the longest single
series rather than the union.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.simulator_tab.fleet.fleet_replay_controller import (  # noqa: E402
    build_anchor_indices,
    clock_timestamps_from_candles,
)
from src.gui.simulator_tab.fleet.master_clock import MasterClock  # noqa: E402

STEP = 300_000
BASE = 1_700_000_000_000


def _rows(slots):
    """Candle rows at the given gapless-grid slot numbers."""
    return [[BASE + s * STEP, 1.0, 1.0, 1.0, 1.0, 1.0] for s in slots]


class _Series:
    """Minimal stand-in for CandleSeries — MasterClock reads `.rows` only."""

    def __init__(self, rows):
        self.rows = rows


def _union_index(clock_ts, slot):
    """Where grid `slot` actually sits in the master clock."""
    return clock_ts.index(BASE + slot * STEP)


class TestTheInstrumentSeparatesTheTwoSpaces:
    """POSITIVE CONTROL. Every assertion below is worthless unless the fixture
    actually makes union index and grid index disagree."""

    def test_the_planted_gap_really_does_displace_later_candles(self):
        # Slots 0..9 and 30..39 — twenty interior slots absent.
        clock_ts = clock_timestamps_from_candles(
            {"A/USD": _rows(range(0, 10)), "B/USD": _rows(range(30, 40))})
        assert len(clock_ts) == 20
        assert _union_index(clock_ts, 30) == 10   # union position
        assert 30 != 10                            # grid slot
        # And the clock the run loop actually uses agrees with the helper.
        mc = MasterClock.from_series(
            [_Series(_rows(range(0, 10))), _Series(_rows(range(30, 40)))])
        assert list(mc.timestamps) == clock_ts

    def test_a_gapless_union_makes_the_two_spaces_identical(self):
        """NEGATIVE CONTROL. With no gap the old and new answers must agree —
        otherwise the fix is not a correction, it is a different bug."""
        clock_ts = clock_timestamps_from_candles({"A/USD": _rows(range(0, 40))})
        for slot in (0, 1, 17, 39):
            assert _union_index(clock_ts, slot) == slot


class TestAnchorsResolveToUnionPositions:
    def test_a_trade_after_the_gap_anchors_at_its_union_index(self):
        clock_ts = clock_timestamps_from_candles(
            {"A/USD": _rows(range(0, 10)), "B/USD": _rows(range(30, 40))})
        trade_ts = (BASE + 30 * STEP) / 1000.0     # trade timestamps are SECONDS

        anchors = build_anchor_indices(
            [trade_ts], base_ts_ms=BASE, n_candles=len(clock_ts),
            warmup=0, clock_ts_ms=clock_ts)

        assert anchors == {10}, (
            "the anchor must be the trade's position in the master clock's "
            f"union, not its slot on a gapless ruler; got {sorted(anchors)}")

    def test_the_real_world_shape_truncates_warmup_it_does_not_drop_trades(self):
        """THE HONEST SEVERITY TEST — modelled on the operator's actual data,
        not on a fixture chosen to look bad.

        Measured 2026-08-07 across the 35 live tablets: union of 61,201
        candles spanning 2026-01-01 to 2026-08-01, with exactly THREE gaps
        totalling 79 slots — 1 slot on 2026-02-19, a 77-slot outage on
        2026-05-08 01:15 (~6.4 hours), and 1 more that evening.

        So on real data NO TRADE IS DROPPED: drift (79) stays below warmup
        (100), which means `range(idx - 100, idx + 1)` still contains the true
        candle. What is lost is warm-up depth — 21 real warm-up candles
        instead of 100.

        That is the defect worth fixing, stated at its true size. On a harness
        whose entire purpose is that simulated indicators match live ones, a
        79%-truncated TA window is a fidelity loss. It is not a missed trade.
        """
        drift, warm = 79, 100
        clock_ts = clock_timestamps_from_candles({
            "A/USD": _rows(range(0, 300)),
            "B/USD": _rows(range(300 + drift, 600 + drift)),
        })
        trade_slot = 400 + drift              # comfortably after the gap
        trade_ts = (BASE + trade_slot * STEP) / 1000.0
        true_idx = _union_index(clock_ts, trade_slot)

        old = build_anchor_indices(
            [trade_ts], base_ts_ms=BASE, n_candles=len(clock_ts), warmup=warm)
        new = build_anchor_indices(
            [trade_ts], base_ts_ms=BASE, n_candles=len(clock_ts),
            warmup=warm, clock_ts_ms=clock_ts)

        # The trade candle survives BOTH ways — this is why the defect went
        # unnoticed, and why calling it "dropped trades" would be false.
        assert true_idx in old, "on real-world drift the old path still covers it"
        assert true_idx in new

        # What actually differs is how much valid warm-up precedes it.
        old_warmup = len([i for i in old if i < true_idx])
        new_warmup = len([i for i in new if i < true_idx])
        assert new_warmup == warm, f"fixed path must give {warm}, got {new_warmup}"
        assert old_warmup == warm - drift, (
            f"unfixed path should give {warm - drift} real warm-up candles, "
            f"got {old_warmup}")
        assert old != new

    def test_a_drift_beyond_the_warmup_would_lose_the_trade_candle(self):
        """The failure mode the fix forecloses, labelled as NOT-YET-REACHED.

        Margin on the operator's current data is 21 candles (79 drift against
        100 warm-up). One more outage of that size and the anchored run starts
        skipping the very candles it exists to evaluate — silently, since a
        skipped candle logs nothing.
        """
        drift, warm = 140, 100            # past the margin
        clock_ts = clock_timestamps_from_candles({
            "A/USD": _rows(range(0, 300)),
            "B/USD": _rows(range(300 + drift, 600 + drift)),
        })
        trade_slot = 400 + drift
        trade_ts = (BASE + trade_slot * STEP) / 1000.0
        true_idx = _union_index(clock_ts, trade_slot)

        old = build_anchor_indices(
            [trade_ts], base_ts_ms=BASE, n_candles=len(clock_ts), warmup=warm)
        new = build_anchor_indices(
            [trade_ts], base_ts_ms=BASE, n_candles=len(clock_ts),
            warmup=warm, clock_ts_ms=clock_ts)

        assert true_idx not in old, "beyond the margin the true candle is lost"
        assert true_idx in new

    def test_a_trade_between_candles_anchors_to_the_one_containing_it(self):
        clock_ts = clock_timestamps_from_candles({"A/USD": _rows(range(0, 20))})
        mid = (BASE + 7 * STEP + STEP // 3) / 1000.0

        anchors = build_anchor_indices(
            [mid], base_ts_ms=BASE, n_candles=len(clock_ts),
            warmup=0, clock_ts_ms=clock_ts)

        assert anchors == {7}

    def test_a_trade_before_the_first_candle_is_dropped_not_clamped(self):
        clock_ts = clock_timestamps_from_candles({"A/USD": _rows(range(5, 20))})
        early = (BASE + 1 * STEP) / 1000.0
        assert build_anchor_indices(
            [early], base_ts_ms=BASE, n_candles=len(clock_ts),
            warmup=0, clock_ts_ms=clock_ts) == set()

    def test_warmup_counts_union_candles_not_grid_slots(self):
        """The live consequence. Warm-up must reach back 100 candles the read
        head will actually evaluate, not 100 ruler slots that may not exist."""
        clock_ts = clock_timestamps_from_candles(
            {"A/USD": _rows(range(0, 10)), "B/USD": _rows(range(30, 40))})
        trade_ts = (BASE + 32 * STEP) / 1000.0     # union index 12

        anchors = build_anchor_indices(
            [trade_ts], base_ts_ms=BASE, n_candles=len(clock_ts),
            warmup=5, clock_ts_ms=clock_ts)

        assert anchors == {7, 8, 9, 10, 11, 12}, (
            "warm-up must span union positions, so it crosses the gap into "
            f"the earlier series; got {sorted(anchors)}")

    def test_the_bound_is_the_union_size(self):
        clock_ts = clock_timestamps_from_candles(
            {"A/USD": _rows(range(0, 10)), "B/USD": _rows(range(30, 40))})
        last = (BASE + 39 * STEP) / 1000.0
        anchors = build_anchor_indices(
            [last], base_ts_ms=BASE, n_candles=len(clock_ts),
            warmup=0, clock_ts_ms=clock_ts)
        assert anchors == {19}
        assert max(anchors) < len(clock_ts)


class TestTheUnionHelper:
    def test_it_dedupes_across_series(self):
        ts = clock_timestamps_from_candles(
            {"A/USD": _rows(range(0, 10)), "B/USD": _rows(range(5, 15))})
        assert len(ts) == 15
        assert ts == sorted(set(ts))

    def test_it_skips_empty_and_malformed_rows(self):
        ts = clock_timestamps_from_candles({
            "A/USD": _rows(range(0, 3)),
            "B/USD": [],
            "C/USD": [["not-a-timestamp", 1, 1, 1, 1, 1]],
            "D/USD": None,
        })
        assert len(ts) == 3

    def test_it_matches_master_clock_exactly(self):
        """The whole point: this helper must produce the same index space the
        run loop's cursor walks. If they ever diverge, anchors are wrong again
        and nothing would say so."""
        candles = {"A/USD": _rows(range(0, 10)), "B/USD": _rows(range(7, 25))}
        mc = MasterClock.from_series([_Series(r) for r in candles.values()])
        assert clock_timestamps_from_candles(candles) == list(mc.timestamps)


class TestTheCallSitesPassTheClock:
    """Structural pin on the panel.

    Read as AST, never as source text. Counting occurrences of a name in source
    has produced a false reading three separate times on this project — comments
    and docstrings mentioning a symbol get counted as uses.
    """

    @staticmethod
    def _anchor_calls():
        panel = (REPO_ROOT / "src" / "gui" / "simulator_tab" / "fleet"
                 / "fleet_replay_panel.py")
        tree = ast.parse(panel.read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(
                node.func, "attr", None)
            if name in ("build_anchor_indices", "_bai"):
                found.append(node)
        return found

    def test_the_panel_still_builds_anchors(self):
        """POSITIVE CONTROL for the pin below — if the call sites are ever
        renamed away, the kwarg assertion would pass vacuously on an empty
        list."""
        assert len(self._anchor_calls()) >= 2, (
            "expected the screening-mode and expected-index call sites")

    @pytest.mark.parametrize("kw", ["clock_ts_ms", "n_candles"])
    def test_every_call_site_passes(self, kw):
        for call in self._anchor_calls():
            assert any(k.arg == kw for k in call.keywords), (
                f"a build_anchor_indices call at line {call.lineno} does not "
                f"pass {kw}=; anchors would silently fall back to the gapless "
                "ruler")
