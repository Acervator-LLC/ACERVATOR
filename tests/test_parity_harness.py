"""v3.24.5 — pin tests for sim vs live trade parity harness."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.stone_tablets.parity_harness import (  # noqa: E402
    compare_trades,
    format_report_lines,
)


def _live(ts: float, sym: str, side: str, amt: float = 1.0) -> dict:
    return {"timestamp": ts, "symbol": sym, "side": side, "amount": amt, "price": 100.0}


def _sim(ts: float, sym: str, side: str, amt: float = 1.0):
    """OrderSide str is fine — harness handles both enum + str."""
    t = SimpleNamespace()
    t.timestamp = ts
    t.symbol = sym
    t.side = side  # "BUY"/"SELL"
    t.amount = amt
    return t


def test_exact_match_produces_matched_only():
    live = [_live(1000.0, "BTC/USD", "BUY", 1.0)]
    sim = [_sim(1000.0, "BTC/USD", "BUY", 1.0)]
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 1
    assert len(r.live_only) == 0
    assert len(r.sim_only) == 0
    assert r.matched[0].drift_s == 0.0


def test_within_tolerance_still_matches():
    live = [_live(1000.0, "BTC/USD", "BUY")]
    sim = [_sim(1250.0, "BTC/USD", "BUY")]  # 250s drift
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 1
    assert r.matched[0].drift_s == 250.0


def test_outside_tolerance_produces_live_only_and_sim_only():
    live = [_live(1000.0, "BTC/USD", "BUY")]
    sim = [_sim(2000.0, "BTC/USD", "BUY")]  # 1000s drift > 300s
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 0
    assert len(r.live_only) == 1
    assert len(r.sim_only) == 1


def test_side_mismatch_never_matches():
    live = [_live(1000.0, "BTC/USD", "BUY")]
    sim = [_sim(1000.0, "BTC/USD", "SELL")]
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 0
    assert len(r.live_only) == 1
    assert len(r.sim_only) == 1


def test_symbol_mismatch_never_matches():
    live = [_live(1000.0, "BTC/USD", "BUY")]
    sim = [_sim(1000.0, "ETH/USD", "BUY")]
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 0


def test_greedy_first_come_first_served_when_multiple_candidates():
    """Two live trades on same symbol/side, three sim candidates —
    the closest-in-time pair matches first, second matches with the
    next closest, third sim = sim_only."""
    live = [
        _live(1000.0, "BTC/USD", "BUY"),
        _live(2000.0, "BTC/USD", "BUY"),
    ]
    sim = [
        _sim(1050.0, "BTC/USD", "BUY"),  # closest to live #1
        _sim(2100.0, "BTC/USD", "BUY"),  # closest to live #2
        _sim(3500.0, "BTC/USD", "BUY"),  # no live partner
    ]
    r = compare_trades(live, sim, tolerance_s=300)
    assert len(r.matched) == 2
    assert len(r.live_only) == 0
    assert len(r.sim_only) == 1


def test_per_symbol_matrix_aggregates_correctly():
    live = [_live(1000.0, "BTC/USD", "BUY"), _live(1100.0, "ETH/USD", "SELL")]
    sim = [_sim(1000.0, "BTC/USD", "BUY")]
    r = compare_trades(live, sim, tolerance_s=300)
    m = r.per_symbol_counts()
    assert m["BTC/USD"]["matched"] == 1
    assert m["ETH/USD"]["live_only"] == 1
    assert m["ETH/USD"]["matched"] == 0


def test_match_rate_zero_when_no_live():
    r = compare_trades([], [], tolerance_s=300)
    assert r.match_rate == 0.0
    assert r.total_live == 0


def test_match_rate_100_when_all_matched():
    live = [_live(1000.0, "BTC/USD", "BUY"), _live(2000.0, "BTC/USD", "SELL")]
    sim = [_sim(1000.0, "BTC/USD", "BUY"), _sim(2000.0, "BTC/USD", "SELL")]
    r = compare_trades(live, sim, tolerance_s=300)
    assert r.match_rate == 100.0


def test_window_filter_excludes_out_of_range_trades():
    live = [_live(500.0, "BTC/USD", "BUY"), _live(1500.0, "BTC/USD", "BUY")]
    sim = [_sim(500.0, "BTC/USD", "BUY"), _sim(1500.0, "BTC/USD", "BUY")]
    # Only the 1500 pair should be in-window
    r = compare_trades(
        live, sim, tolerance_s=300, window_since_ts=1000.0, window_until_ts=2000.0
    )
    assert len(r.matched) == 1
    assert r.matched[0].live_ts == 1500.0


def test_format_report_lines_summary_present():
    live = [_live(1000.0, "BTC/USD", "BUY")]
    sim = [_sim(1000.0, "BTC/USD", "BUY")]
    r = compare_trades(live, sim)
    out = format_report_lines(r)
    assert any("Parity:" in line for line in out)
    assert any("Match rate" in line for line in out)


def test_format_report_lines_empty_message_when_nothing():
    r = compare_trades([], [])
    out = format_report_lines(r)
    assert any("nothing to compare" in line for line in out)
