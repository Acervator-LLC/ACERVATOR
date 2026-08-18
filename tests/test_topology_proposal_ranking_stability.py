"""Sector-cluster ranking must not be decided by dict iteration order.

C35 / finding SWARM-4.28.

THE DEFECT
`topology_proposals.detect_sector_cluster` scored purely on cluster
size:

    score = max(0.0, min(100.0, 100.0 * (len(ranked) / float(max_cluster))))

Any sector that reaches `max_cluster` scores exactly 100.0, so every
full sector ties at the ceiling. `build_proposals` then does

    proposals.sort(key=lambda p: p["score"], reverse=True)

which is a STABLE sort, so tied proposals keep their input order — and
that order comes from `by_sector` dict insertion, which comes from
`tickers_by_asset` iteration. The operator's "top" proposal was
whichever sector happened to be encountered first.

THE COMMENT ABOVE THAT SORT IS ALSO WRONG. It claims ties fall back to
"the higher archetype priority order: momentum -> mean_reversion ->
sector -> distance (matches the append order, so a stable sort
suffices)". That reasoning only covers ties BETWEEN archetypes. Nine
tied sector clusters are all the same archetype, so archetype priority
cannot separate them at all.

THE FIX (operator decision 2026-08-07: liquidity)
`baseVolume` is already fetched and already used inside this function to
rank members and choose the hub, so using it for the sector score costs
nothing and makes the score coherent with how the cluster is built. Size
becomes PART of the score instead of all of it, which is what stops the
ceiling being reachable by size alone.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.topology_proposals import detect_sector_cluster  # noqa: E402

SECTORS = {
    "AAA": "alpha", "AAB": "alpha", "AAC": "alpha", "AAD": "alpha",
    "BBA": "beta", "BBB": "beta", "BBC": "beta", "BBD": "beta",
    "CCA": "gamma", "CCB": "gamma", "CCC": "gamma", "CCD": "gamma",
}
# Three full sectors, so all three hit max_cluster and tie on size.
# Liquidity differs sharply and unambiguously: beta > gamma > alpha.
VOLUMES = {
    "AAA": 10.0, "AAB": 9.0, "AAC": 8.0, "AAD": 7.0,        # alpha  = 34
    "BBA": 900.0, "BBB": 800.0, "BBC": 700.0, "BBD": 600.0,  # beta   = 3000
    "CCA": 90.0, "CCB": 80.0, "CCC": 70.0, "CCD": 60.0,      # gamma  = 300
}


def _tickers(order):
    return {
        a: {"quote": "USD", "symbol": f"{a}/USD",
            "baseVolume": VOLUMES[a], "existing_bot_id": ""}
        for a in order
    }


def _run(order):
    return detect_sector_cluster(_tickers(order), SECTORS,
                                 min_cluster=4, max_cluster=4, now=1000.0)


def _leader(props):
    return max(props, key=lambda p: p["score"])["title"]


class TestTheFixtureCanDetectTheDefect:
    """POSITIVE CONTROL. Every assertion below assumes all three sectors
    are FULL and therefore tie on size. If the fixture stopped producing
    three proposals, the file would pass while measuring nothing."""

    def test_three_sectors_are_proposed(self):
        props = _run(list(SECTORS))
        assert len(props) == 3, [p["title"] for p in props]

    def test_all_three_are_at_max_cluster_size(self):
        for p in _run(list(SECTORS)):
            assert len(p["assets"]) == 4


class TestScoreIsNotDecidedBySizeAlone:
    def test_not_every_full_sector_scores_the_ceiling(self):
        """The defect in one line: three full sectors, three 100.0s."""
        scores = [p["score"] for p in _run(list(SECTORS))]
        assert len([s for s in scores if s >= 100.0]) <= 1, (
            f"more than one proposal reached the 100.0 ceiling: {scores}")

    def test_fewer_than_two_proposals_share_the_top_score(self):
        """The exit gate, stated as the plan states it."""
        scores = sorted((p["score"] for p in _run(list(SECTORS))),
                        reverse=True)
        assert scores[0] != scores[1], (
            f"top score is shared: {scores}")

    def test_the_most_liquid_sector_leads(self):
        """Operator decision 2026-08-07: liquidity is the tie-break.
        beta's members trade ~10x gamma's and ~90x alpha's."""
        assert "beta" in _leader(_run(list(SECTORS)))

    def test_size_still_matters(self):
        """NEGATIVE CONTROL: liquidity must not simply REPLACE size, or a
        tiny high-volume sector would outrank a full one."""
        sectors = dict(SECTORS)
        vols = dict(VOLUMES)
        # A 4-member sector of modest volume vs the same sector shrunk
        # below min_cluster should not survive at all.
        small = {k: v for k, v in sectors.items() if not k.startswith("CC")}
        props = detect_sector_cluster(
            {a: {"quote": "USD", "symbol": f"{a}/USD",
                 "baseVolume": vols[a], "existing_bot_id": ""}
             for a in small},
            small, min_cluster=4, max_cluster=4, now=1000.0)
        assert all(len(p["assets"]) == 4 for p in props)


class TestRankingIsDeterministic:
    def test_the_leader_is_identical_over_twenty_shuffles(self):
        """THE exit-gate measurement. Input order must not decide the
        operator's top proposal."""
        rng = random.Random(20260807)
        order = list(SECTORS)
        leaders = set()
        for _ in range(20):
            rng.shuffle(order)
            leaders.add(_leader(_run(order)))
        assert len(leaders) == 1, (
            f"leader changed with input order across 20 shuffles: "
            f"{leaders}")

    def test_the_full_ranking_is_identical_over_twenty_shuffles(self):
        """Stronger than the leader alone: the whole order must be
        stable, or positions 2 and 3 still shuffle under the operator."""
        rng = random.Random(4242)
        order = list(SECTORS)
        rankings = set()
        for _ in range(20):
            rng.shuffle(order)
            props = sorted(_run(order), key=lambda p: -p["score"])
            rankings.add(tuple(p["title"] for p in props))
        assert len(rankings) == 1, f"ranking is input-order dependent: {rankings}"

    def test_equal_liquidity_still_ranks_deterministically(self):
        """Two sectors identical on BOTH signals must still not depend
        on dict order — the tie-break needs a deterministic floor."""
        sectors = {"XA": "x", "XB": "x", "XC": "x", "XD": "x",
                   "YA": "y", "YB": "y", "YC": "y", "YD": "y"}
        tick = {a: {"quote": "USD", "symbol": f"{a}/USD",
                    "baseVolume": 100.0, "existing_bot_id": ""}
                for a in sectors}
        rng = random.Random(7)
        seen = set()
        for _ in range(20):
            order = list(sectors)
            rng.shuffle(order)
            props = detect_sector_cluster(
                {a: tick[a] for a in order}, sectors,
                min_cluster=4, max_cluster=4, now=1000.0)
            seen.add(tuple(p["title"] for p in
                           sorted(props, key=lambda p: -p["score"])))
        assert len(seen) == 1, f"tied sectors rank nondeterministically: {seen}"
