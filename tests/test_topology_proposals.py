"""v3.23.67 — pin tests for src/trading/topology_proposals.py.

Covers tests 1-9 from the design doc § 8:
  1. momentum_funnel finds correlated cluster
  2. momentum_funnel ranks leader by 24h volume
  3. momentum_funnel skips clusters below min size
  4. mean_reversion consumes precomputed opposing-pair table
  5. mean_reversion liquidity gate
  6. sector_cluster hub = highest volume within sector
  7. distance_to_band pairs deep_scrum → deep_fold
  8. detect_all_topologies dedupes by asset overlap
  9. proposal shape matches spec § 4
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading import topology_proposals as tp  # noqa: E402

# --------------------------------------------------------------------- #
# Fixtures                                                              #
# --------------------------------------------------------------------- #


def _ticker(
    quote="USD", symbol=None, base_volume=1_000_000.0, last=100.0, existing_bot_id=""
):
    return {
        "quote": quote,
        "symbol": symbol,
        "baseVolume": base_volume,
        "last": last,
        "existing_bot_id": existing_bot_id,
    }


# --------------------------------------------------------------------- #
# Test 1: momentum_funnel finds correlated cluster                       #
# --------------------------------------------------------------------- #


def test_momentum_funnel_finds_correlated_cluster():
    tickers = {
        "ETH": _ticker(symbol="ETH/USD", base_volume=10_000_000),
        "ARB": _ticker(symbol="ARB/USD", base_volume=3_000_000),
        "OP": _ticker(symbol="OP/USD", base_volume=2_000_000),
    }
    corr = {
        ("ARB", "ETH"): 0.82,
        ("ETH", "OP"): 0.80,
        ("ARB", "OP"): 0.78,
    }
    out = tp.detect_momentum_funnel(tickers, corr)
    assert len(out) == 1
    p = out[0]
    assert p["archetype"] == "momentum_funnel"
    assert set(p["assets"]) == {"ETH", "ARB", "OP"}
    # 2 wires from leader
    assert len(p["wires"]) == 2
    assert all(w["source_asset"] == "ETH" for w in p["wires"])
    assert all(w["pct"] == tp.MOMENTUM_WIRE_PCT for w in p["wires"])


# --------------------------------------------------------------------- #
# Test 2: momentum_funnel ranks leader by volume                        #
# --------------------------------------------------------------------- #


def test_momentum_funnel_ranks_leader_by_volume():
    tickers = {
        "A": _ticker(symbol="A/USD", base_volume=100.0),
        "B": _ticker(symbol="B/USD", base_volume=999_999.0),
        "C": _ticker(symbol="C/USD", base_volume=500.0),
    }
    corr = {
        ("A", "B"): 0.90,
        ("A", "C"): 0.90,
        ("B", "C"): 0.90,
    }
    out = tp.detect_momentum_funnel(tickers, corr)
    assert len(out) >= 1
    leader_bots = [b for b in out[0]["bots"] if b["role"] == "leader"]
    assert len(leader_bots) == 1
    assert leader_bots[0]["asset"] == "B"


# --------------------------------------------------------------------- #
# Test 3: momentum_funnel skips clusters below min size                 #
# --------------------------------------------------------------------- #


def test_momentum_funnel_skips_clusters_below_min_size():
    tickers = {
        "X": _ticker(symbol="X/USD", base_volume=1e6),
        "Y": _ticker(symbol="Y/USD", base_volume=1e6),
    }
    corr = {("X", "Y"): 0.95}
    assert tp.detect_momentum_funnel(tickers, corr) == []


# --------------------------------------------------------------------- #
# Test 4: mean_reversion consumes opposing pair table                   #
# --------------------------------------------------------------------- #


def test_mean_reversion_uses_opposing_pairs():
    opposing = [{"long_asset": "BTC", "short_asset": "GOLD", "corr": -0.75}]
    tickers = {
        "BTC": _ticker(symbol="BTC/USD", base_volume=1_000, last=50_000),
        "GOLD": _ticker(symbol="GOLD/USD", base_volume=5_000, last=2_000),
    }
    out = tp.detect_mean_reversion_pair(opposing, tickers)
    assert len(out) == 1
    assert out[0]["archetype"] == "mean_reversion_pair"
    assert len(out[0]["wires"]) == 2  # bidirectional
    sources = {w["source_asset"] for w in out[0]["wires"]}
    targets = {w["target_asset"] for w in out[0]["wires"]}
    assert sources == {"BTC", "GOLD"}
    assert targets == {"BTC", "GOLD"}


# --------------------------------------------------------------------- #
# Test 5: mean_reversion liquidity gate                                 #
# --------------------------------------------------------------------- #


def test_mean_reversion_liquidity_gate():
    opposing = [{"long_asset": "DUST", "short_asset": "BTC", "corr": -0.90}]
    tickers = {
        # DUST fails: 500 * $1 = $500 (below $1M gate)
        "DUST": _ticker(symbol="DUST/USD", base_volume=500, last=1.0),
        "BTC": _ticker(symbol="BTC/USD", base_volume=1_000, last=50_000),
    }
    assert tp.detect_mean_reversion_pair(opposing, tickers) == []


# --------------------------------------------------------------------- #
# Test 6: sector_cluster hub = highest volume within sector             #
# --------------------------------------------------------------------- #


def test_sector_cluster_hub_by_highest_volume():
    tickers = {
        "ARB": _ticker(symbol="ARB/USD", base_volume=2_000_000),
        "OP": _ticker(symbol="OP/USD", base_volume=1_500_000),
        "MATIC": _ticker(symbol="MATIC/USD", base_volume=5_000_000),
        "STRK": _ticker(symbol="STRK/USD", base_volume=800_000),
    }
    sector_map = {"ARB": "l2", "OP": "l2", "MATIC": "l2", "STRK": "l2"}
    out = tp.detect_sector_cluster(tickers, sector_map)
    assert len(out) == 1
    p = out[0]
    hub_bots = [b for b in p["bots"] if b["role"] == "hub"]
    assert len(hub_bots) == 1
    assert hub_bots[0]["asset"] == "MATIC"
    spoke_assets = {b["asset"] for b in p["bots"] if b["role"] == "spoke"}
    assert spoke_assets == {"ARB", "OP", "STRK"}


# --------------------------------------------------------------------- #
# Test 7: distance_to_band pairs deep_scrum → deep_fold                 #
# --------------------------------------------------------------------- #


def test_distance_to_band_pairs_deep_scrum_to_fold():
    bots = [
        {
            "bot_id": "bot-scrum",
            "asset": "SOL",
            "quote": "USD",
            "symbol": "SOL/USD",
            "position_val": 300.0,
            "target_balance": 200.0,
        },  # +50% → deep scrum
        {
            "bot_id": "bot-fold",
            "asset": "SOL",
            "quote": "USD",
            "symbol": "SOL/USD",
            "position_val": 100.0,
            "target_balance": 200.0,
        },  # -50% → deep fold
    ]
    out = tp.detect_distance_to_band(bots)
    assert len(out) == 1
    p = out[0]
    roles = {b["role"] for b in p["bots"]}
    assert roles == {"scrum_deep", "fold_deep"}
    assert len(p["wires"]) == 1
    assert p["wires"][0]["source_asset"] == "SOL"
    assert p["wires"][0]["target_asset"] == "SOL"
    assert p["wires"][0]["pct"] == tp.DISTANCE_WIRE_PCT


# --------------------------------------------------------------------- #
# Test 8: detect_all_topologies dedupes by asset overlap                #
# --------------------------------------------------------------------- #


def test_detect_all_topologies_dedupes_by_asset_overlap():
    # Craft two proposals that share ≥ 50% assets → dedup keeps higher
    # score. Momentum cluster of 3 correlated L1s at score ~90; sector
    # cluster of the same 3 (all sector "l1") plus a 4th at score ~66.
    tickers = {
        "ETH": _ticker(symbol="ETH/USD", base_volume=10_000_000),
        "SOL": _ticker(symbol="SOL/USD", base_volume=3_000_000),
        "AVAX": _ticker(symbol="AVAX/USD", base_volume=1_500_000),
        "ADA": _ticker(symbol="ADA/USD", base_volume=500_000),
    }
    corr = {
        ("ETH", "SOL"): 0.90,
        ("AVAX", "ETH"): 0.90,
        ("AVAX", "SOL"): 0.90,
    }
    sector_map = {"ETH": "l1", "SOL": "l1", "AVAX": "l1", "ADA": "l1"}
    ctx = {
        "tickers_by_asset": tickers,
        "correlations": corr,
        "sector_map": sector_map,
        "target_defaults": {},
        "target_fallback": 25.0,
    }
    out = tp.detect_all_topologies(ctx)
    ids = [p["id"] for p in out]
    # After dedup, only the higher-scoring momentum proposal survives
    # (or at least the sector proposal is eliminated because its
    # assets overlap ≥ 50% with momentum).
    assert any("momentum_funnel" in i for i in ids)
    momentum_assets = {
        a for p in out if p["archetype"] == "momentum_funnel" for a in p["assets"]
    }
    sector_proposals = [
        p
        for p in out
        if p["archetype"] == "sector_cluster" and set(p["assets"]) & momentum_assets
    ]
    assert len(sector_proposals) == 0


# --------------------------------------------------------------------- #
# Test 9: proposal shape matches spec § 4                               #
# --------------------------------------------------------------------- #


def test_proposal_shape_matches_spec():
    tickers = {
        "ETH": _ticker(symbol="ETH/USD", base_volume=1e7),
        "ARB": _ticker(symbol="ARB/USD", base_volume=3e6),
        "OP": _ticker(symbol="OP/USD", base_volume=2e6),
    }
    corr = {("ARB", "ETH"): 0.85, ("ETH", "OP"): 0.85, ("ARB", "OP"): 0.80}
    proposals = tp.detect_momentum_funnel(tickers, corr)
    assert proposals, "expected at least one proposal to check shape"
    for p in proposals:
        for k in (
            "id",
            "archetype",
            "title",
            "created_ts",
            "score",
            "assets",
            "bots",
            "wires",
            "adopt_notes",
        ):
            assert k in p, f"missing key {k!r}"
        assert isinstance(p["id"], str) and p["id"]
        assert isinstance(p["archetype"], str)
        assert isinstance(p["title"], str) and p["title"]
        assert isinstance(p["created_ts"], float)
        assert isinstance(p["score"], float)
        assert 0.0 <= p["score"] <= 100.0
        assert isinstance(p["assets"], list) and all(
            isinstance(a, str) and a == a.upper() for a in p["assets"]
        )
        assert isinstance(p["bots"], list) and p["bots"]
        for b in p["bots"]:
            for bk in (
                "asset",
                "quote",
                "symbol",
                "existing_bot_id",
                "role",
                "suggested_target_usd",
            ):
                assert bk in b, f"bot missing {bk!r}"
        assert isinstance(p["wires"], list)
        for w in p["wires"]:
            for wk in ("source_asset", "target_asset", "pct", "rationale"):
                assert wk in w, f"wire missing {wk!r}"
        assert isinstance(p["adopt_notes"], list)


# --------------------------------------------------------------------- #
# Bonus: config loaders behave                                          #
# --------------------------------------------------------------------- #


def test_load_sector_map_returns_dict():
    m = tp.load_sector_map()
    # Ships with a curated map; at minimum BTC + ETH must be tagged.
    assert m.get("BTC") == "l1"
    assert m.get("ETH") == "l1"


def test_load_target_defaults_fallback_present():
    defaults, fallback = tp.load_target_defaults()
    assert fallback == pytest.approx(25.0)
    assert defaults.get("BTC", 0.0) > 0.0


def test_suggested_target_usd_uses_map_then_fallback():
    d = {"FOO": 111.11}
    assert tp.suggested_target_usd("FOO", d, 25.0) == pytest.approx(111.11)
    assert tp.suggested_target_usd("BAR", d, 25.0) == pytest.approx(25.0)
