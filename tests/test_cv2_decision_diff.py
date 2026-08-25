"""Pins for the CV2 decision-diff harness.

The harness exists so a live-behaviour cascade can prove it did not move
a SCRUM or FOLD decision. Every such cascade's exit gate depends on it,
which makes ITS correctness load-bearing: a differ that cannot report a
difference would bless every change it was pointed at.

MEASURED WHILE BUILDING IT, and the reason this file leads with a
positive control: perturbing the Bollinger period 20 -> 21 across 72
real decisions produced 36 indicator value changes and ZERO gate
decision differences. That is a true result — a one-step band change
genuinely did not flip a gate on those windows — but it means the
end-to-end run exercised only the indicator path. The decision path went
unproven by that experiment, so it is proven here directly instead of
hunting for a perturbation that happens to flip a gate.

tmp_path and synthetic records only. Reads the tablet archive; writes
nothing anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.harness import decision_diff as dd  # noqa: E402


def _rec(
    asset="BTC",
    start=0,
    scenario="scrum_plausible",
    *,
    scrum=False,
    fold=False,
    net=1.0,
    bb=0.5,
):
    return {
        "asset": asset,
        "start": start,
        "scenario": scenario,
        "net_score": net,
        "consensus": 0.2,
        "bb_position": bb,
        "is_bullish": True,
        "is_bearish": False,
        "trend_hold": False,
        "scrum_fires": scrum,
        "fold_fires": fold,
        "scrum_blockers": [],
        "fold_blockers": [],
    }


def _doc(records):
    return {"records": records}


class TestComparerReportsDecisionChanges:
    """THE positive control. If these pass vacuously the harness is
    decorative and every cascade relying on it is unverified."""

    def test_a_scrum_flip_is_reported_as_a_DECISION_difference(self):
        a = _doc([_rec(scrum=False)])
        b = _doc([_rec(scrum=True)])
        diffs, lines = dd.compare(a, b)
        assert diffs == 1, "a flipped SCRUM must count as a decision diff"
        assert any("scrum_fires" in ln and "DECISION" in ln for ln in lines)

    def test_a_fold_flip_is_reported_as_a_DECISION_difference(self):
        a = _doc([_rec(fold=True)])
        b = _doc([_rec(fold=False)])
        diffs, lines = dd.compare(a, b)
        assert diffs == 1
        assert any("fold_fires" in ln and "DECISION" in ln for ln in lines)

    def test_both_sides_flipping_counts_twice(self):
        a = _doc([_rec(scrum=False, fold=False)])
        b = _doc([_rec(scrum=True, fold=True)])
        diffs, _ = dd.compare(a, b)
        assert diffs == 2

    def test_a_flip_in_one_of_many_records_is_not_lost(self):
        base = [_rec(start=i) for i in range(20)]
        cand = [_rec(start=i) for i in range(20)]
        cand[13]["scrum_fires"] = True
        diffs, lines = dd.compare(_doc(base), _doc(cand))
        assert diffs == 1, "a single flip among 20 must not be swallowed"
        assert any("13" in ln for ln in lines)


class TestComparerIsNotOverEager:
    def test_identical_records_report_zero(self):
        a = _doc([_rec(), _rec(asset="ETH")])
        diffs, lines = dd.compare(a, _doc([_rec(), _rec(asset="ETH")]))
        assert diffs == 0
        assert lines == []

    def test_indicator_drift_alone_is_NOT_a_decision_difference(self):
        """Values may move without changing an outcome. Reporting drift
        as a decision change would make every cascade look unsafe and
        the harness would stop being believed."""
        a = _doc([_rec(net=1.0, bb=0.50)])
        b = _doc([_rec(net=1.7, bb=0.61)])
        diffs, lines = dd.compare(a, b)
        assert diffs == 0
        assert any(
            "indicator" in ln for ln in lines
        ), "drift must still be REPORTED, just not counted as a decision"


class TestComparerCatchesStructuralChange:
    def test_a_missing_record_is_a_difference(self):
        diffs, lines = dd.compare(_doc([_rec(), _rec(start=9)]), _doc([_rec()]))
        assert diffs == 1
        assert any("MISSING" in ln for ln in lines)

    def test_a_new_record_is_a_difference(self):
        diffs, lines = dd.compare(_doc([_rec()]), _doc([_rec(), _rec(start=9)]))
        assert diffs == 1
        assert any("NEW" in ln for ln in lines)


class TestTabletFeed:
    def test_returns_the_window_and_honours_limit(self):
        import asyncio

        rows = [[i, 1, 1, 1, 1 + i, 10] for i in range(500)]
        feed = dd.TabletFeed(rows)
        got = asyncio.run(feed.get_ohlcv("BTC/USD", timeframe="1h", limit=100))
        assert len(got) == 100
        assert got[-1] == rows[-1], "must serve the window's tail"

    def test_is_deterministic_across_calls(self):
        import asyncio

        rows = [[i, 1, 1, 1, 1 + i, 10] for i in range(200)]
        feed = dd.TabletFeed(rows)
        a = asyncio.run(feed.get_ohlcv("BTC/USD", limit=50))
        b = asyncio.run(feed.get_ohlcv("BTC/USD", limit=50))
        assert a == b, "two runs must see byte-identical input"


class TestScenariosArePinnedAndVisible:
    def test_every_scenario_supplies_the_same_field_set(self):
        """A scenario missing a key would silently inherit FIXED and the
        difference between scenarios would stop being what it claims."""
        keys = [set(s) for s in dd.SCENARIOS.values()]
        assert all(
            k == keys[0] for k in keys
        ), f"scenarios disagree on fields: {[sorted(k) for k in keys]}"

    def test_fixed_and_scenario_fields_do_not_overlap(self):
        """An overlap means the scenario silently overrides a value the
        harness claims is held constant."""
        for name, scen in dd.SCENARIOS.items():
            clash = set(scen) & set(dd.FIXED)
            assert not clash, f"{name} overrides FIXED fields: {clash}"

    def test_scenarios_cover_both_sides(self):
        assert any(s["delta"] > 0 for s in dd.SCENARIOS.values())
        assert any(s["delta"] < 0 for s in dd.SCENARIOS.values())


class TestEndToEnd:
    """Runs the real provider and the real chains over real candles."""

    def test_one_window_produces_a_decision(self):
        import asyncio

        res = asyncio.run(dd.run(["BTC"], per_asset=1, window=300))
        if res["n_windows"] == 0:
            pytest.skip(
                "no local stone-tablet candle archive for BTC; this end-to-end "
                "decision test needs real candle data on disk"
            )
        assert res["n_decisions"] == len(dd.SCENARIOS)
        rec = res["records"][0]
        if rec.get("snapshot", "present") is None:
            pytest.fail("warmup: 300 candles should be enough for TA")
        assert isinstance(rec["scrum_fires"], bool)
        assert isinstance(rec["fold_fires"], bool)
        assert rec["net_score"] is not None

    def test_two_runs_on_the_same_tree_are_identical(self):
        """The whole method rests on this. If a run is not reproducible,
        every diff is noise."""
        import asyncio

        a = asyncio.run(dd.run(["BTC"], per_asset=1, window=300))
        b = asyncio.run(dd.run(["BTC"], per_asset=1, window=300))
        diffs, lines = dd.compare(a, b)
        assert (
            diffs == 0 and lines == []
        ), f"same tree produced different results: {lines[:5]}"
