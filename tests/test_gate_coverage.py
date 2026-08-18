"""v3.24.10 — pin tests for trade/gate-decision pairing.

Operator directive 2026-08-02, point 2: "Create error handling for
trade actions that do not have logic gate data."

The point of these tests is that a MISSING gate decision must be a
named, distinguishable condition. A run with 11% gate coverage must
never be reportable as agreement — the causes carry different
meanings:

    BEFORE_LOGGING   not backfillable, not a bug
    LOG_GAP          app was down / writer stalled
    NO_GATE_FOR_BOT  other bots emitted, this one did not -> defect
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.gate_coverage import (  # noqa: E402
    GateStatus,
    build_gate_index,
    classify_trades,
    format_coverage_lines,
)

_T0 = 1_774_915_200.0  # 2026-04-01T00:00:00Z (seconds)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _gate(ts: float, bot_id: str = "bot-1", *,
          scrum: bool = True, fold: bool = False,
          scrum_blockers=None, fold_blockers=None) -> dict:
    return {
        "timestamp": _iso(ts), "category": "gate.decision",
        "bot_id": bot_id,
        "data": {
            "symbol": "BTC/USD",
            "scrum_armed": scrum, "fold_armed": fold,
            "scrum_blockers": scrum_blockers or [],
            "fold_blockers": fold_blockers or [],
        },
    }


def _trade(ts: float, bot_id: str = "bot-1",
           side: str = "SELL") -> dict:
    return {"timestamp": ts, "bot_id": bot_id,
            "symbol": "BTC/USD", "side": side}


# ── index construction ───────────────────────────────────────────

def test_index_groups_by_bot_and_sorts():
    gates = [_gate(_T0 + 100, "b"), _gate(_T0, "a"),
             _gate(_T0 + 50, "a")]
    idx, first, last = build_gate_index(gates)
    assert set(idx) == {"a", "b"}
    assert [t for t, _ in idx["a"]] == [_T0, _T0 + 50]
    assert first == _T0
    assert last == _T0 + 100


def test_index_drops_unparseable_timestamps():
    gates = [_gate(_T0), {"timestamp": "not-a-date", "bot_id": "x"},
             {"bot_id": "y"}]
    idx, _f, _l = build_gate_index(gates)
    assert sum(len(v) for v in idx.values()) == 1


def test_index_handles_empty():
    idx, first, last = build_gate_index([])
    assert idx == {}
    assert first == 0.0
    assert last == 0.0


# ── the happy path ───────────────────────────────────────────────

def test_trade_pairs_with_nearest_gate():
    rep = classify_trades([_trade(_T0 + 60)], [_gate(_T0 + 30)])
    p = rep.pairings[0]
    assert p.status == GateStatus.HAS_GATE
    assert p.has_gate is True
    assert p.drift_s == 30
    assert p.scrum_armed is True


def test_exact_timestamp_match_wins_over_near():
    gates = [_gate(_T0 - 100), _gate(_T0), _gate(_T0 + 100)]
    rep = classify_trades([_trade(_T0)], gates)
    assert rep.pairings[0].drift_s == 0


def test_coverage_percentage():
    rep = classify_trades(
        [_trade(_T0), _trade(_T0 + 100_000)], [_gate(_T0)])
    assert rep.total == 2
    assert rep.covered == 1
    assert rep.coverage_pct == 50.0


# ── the failure modes, each distinguishable ──────────────────────

def test_trade_before_any_gate_entry_is_before_logging():
    """The operator's blind spot: trades predating the feature."""
    rep = classify_trades([_trade(_T0)], [_gate(_T0 + 86_400)])
    assert rep.pairings[0].status == GateStatus.BEFORE_LOGGING


def test_trade_inside_long_silence_is_log_gap():
    gates = [_gate(_T0), _gate(_T0 + 86_400)]  # 24h apart
    rep = classify_trades([_trade(_T0 + 43_200)], gates)
    assert rep.pairings[0].status == GateStatus.LOG_GAP


def test_bot_with_no_entries_is_flagged_separately():
    """Other bots emitted; this one did not. That is a defect
    signal, not a logging gap."""
    rep = classify_trades(
        [_trade(_T0, bot_id="silent")], [_gate(_T0, "noisy")])
    assert rep.pairings[0].status == GateStatus.NO_GATE_FOR_BOT


def test_no_gate_data_at_all():
    rep = classify_trades([_trade(_T0)], [])
    assert rep.pairings[0].status == GateStatus.NO_GATE_DATA


def test_statuses_are_mutually_exclusive():
    gates = [_gate(_T0 + 86_400, "bot-1"),
             _gate(_T0 + 200_000, "bot-1")]
    trades = [
        _trade(_T0, "bot-1"),                  # before logging
        _trade(_T0 + 86_400 + 10, "bot-1"),    # has gate
        _trade(_T0 + 150_000, "bot-1"),        # log gap
        _trade(_T0 + 86_400, "other"),         # no gate for bot
    ]
    counts = classify_trades(trades, gates).by_status()
    assert counts == {
        GateStatus.BEFORE_LOGGING: 1,
        GateStatus.HAS_GATE: 1,
        GateStatus.LOG_GAP: 1,
        GateStatus.NO_GATE_FOR_BOT: 1,
    }


# ── blockers read the side-appropriate list ──────────────────────

def test_sell_reads_scrum_blockers():
    g = _gate(_T0, scrum_blockers=["a", "b"], fold_blockers=["z"])
    rep = classify_trades([_trade(_T0, side="SELL")], [g])
    assert rep.pairings[0].blockers() == ["a", "b"]


def test_buy_reads_fold_blockers():
    g = _gate(_T0, scrum_blockers=["a"], fold_blockers=["z", "y"])
    rep = classify_trades([_trade(_T0, side="BUY")], [g])
    assert rep.pairings[0].blockers() == ["z", "y"]


def test_blockers_empty_without_gate():
    rep = classify_trades([_trade(_T0)], [])
    assert rep.pairings[0].blockers() == []
    assert rep.pairings[0].scrum_armed is None


# ── candle addressing integration ────────────────────────────────

def test_address_resolver_tags_pairings():
    rep = classify_trades(
        [_trade(_T0)], [_gate(_T0)],
        address_resolver=lambda _sym, _ts_ms: "001234_BTC")
    assert rep.pairings[0].candle_address == "001234_BTC"


def test_resolver_failure_does_not_break_classification():
    def boom(_sym, _ts_ms):
        raise RuntimeError("resolver exploded")

    rep = classify_trades([_trade(_T0)], [_gate(_T0)],
                          address_resolver=boom)
    assert rep.pairings[0].status == GateStatus.HAS_GATE
    assert rep.pairings[0].candle_address == ""


# ── reporting ────────────────────────────────────────────────────

def test_report_states_coverage_and_causes():
    rep = classify_trades(
        [_trade(_T0), _trade(_T0 + 86_400 + 10)],
        [_gate(_T0 + 86_400)])
    body = "\n".join(format_coverage_lines(rep))
    assert "Gate coverage:" in body
    assert "blind spot" in body


def test_report_names_bots_missing_gate_entries():
    rep = classify_trades(
        [_trade(_T0, bot_id="ghost")], [_gate(_T0, "real")])
    body = "\n".join(format_coverage_lines(rep))
    assert "ghost" in body


def test_report_handles_zero_trades():
    body = "\n".join(format_coverage_lines(classify_trades([], [])))
    assert "0 / 0" in body or "0.0%" in body
