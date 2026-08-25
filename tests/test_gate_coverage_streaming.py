"""v3.24.24 — pin tests for the gate.log analysis path.

MEASURED ON THE OPERATOR'S REAL LOGS
====================================
gate.log + gate.log.1-.5 = 165,062 rows across 262,868,525 bytes of
NDJSON, 83 distinct bot_ids, average 1,989 entries per bot, 12,366 for
the busiest. Both consumers run synchronously on the Qt thread.

    materialised   streamed
    ------------   --------
    4.222 s        2.547 s
    1,125.5 MB     19.0 MB      <- 59x less heap

...with per-trade classification verified identical.

THREE DEFECTS
=============
1. ``_nearest`` linear-scanned each bot's list. The docstring claimed
   "per-bot lists are small relative to the total"; against real data
   that is false. ``build_gate_index`` already sorts each list, so the
   ordering bisect needs was being built and then ignored.

2. ``build_gate_index`` retained the whole parsed log line. Consumers
   read four fields. Retaining a projection lets the parsed line be
   collected inside the generator loop.

3. ``classify_trades`` assigned ``LOG_GAP`` in BOTH the
   ``elif _in_log_gap(...)`` branch and the ``else``, so the scan was
   dead work AND two different findings were reported as one. On the
   real logs, 7 trades previously labelled "app was down" are actually
   "the bot was logging either side but nothing landed within
   tolerance" — the more alarming case, and it was invisible.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.gate_coverage import (  # noqa: E402
    DEFAULT_TOLERANCE_S,
    LOG_GAP_THRESHOLD_S,
    GateStatus,
    _nearest,
    build_gate_index,
    classify_trades,
)

_T0 = 1_780_000_000.0


def _iso(ts: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _gate(ts: float, bot: str = "b1", **data):
    payload = {
        "scrum_armed": False,
        "fold_armed": False,
        "scrum_blockers": [],
        "fold_blockers": [],
    }
    payload.update(data)
    return {
        "timestamp": _iso(ts),
        "category": "bot.gate_decision",
        "bot_id": bot,
        "data": payload,
    }


def _trade(ts: float, bot: str = "b1", side: str = "SELL"):
    return {"timestamp": ts, "bot_id": bot, "symbol": "BTC/USD", "side": side}


# ── bisect exactness ─────────────────────────────────────────────


def _cands(offsets):
    return sorted((_T0 + o, {"o": o}) for o in offsets)


def test_nearest_finds_the_true_minimum():
    """Bisect must not be an approximation — compare against the
    brute-force argmin over many targets."""
    cands = _cands([-500, -300, -120, -10, 0, 15, 90, 240, 900])
    for probe in range(-600, 1000, 7):
        target = _T0 + probe
        got, drift = _nearest(cands, target, DEFAULT_TOLERANCE_S)
        best, best_d = None, float("inf")
        for ts, e in cands:
            d = abs(ts - target)
            if d <= DEFAULT_TOLERANCE_S and d < best_d:
                best, best_d = e, d
        assert got == best, f"probe={probe}: {got} != {best}"
        if best is not None:
            assert abs(drift - best_d) < 1e-9


def test_tie_break_keeps_the_earlier_entry():
    """The linear scan used strict `<`, so on two equidistant entries it
    kept the first. Bisect probes i-1 before i to preserve that."""
    cands = [(_T0 - 10.0, {"which": "early"}), (_T0 + 10.0, {"which": "late"})]
    got, _ = _nearest(cands, _T0, DEFAULT_TOLERANCE_S)
    assert got["which"] == "early"


def test_exact_match_wins():
    cands = _cands([-5, 0, 5])
    got, drift = _nearest(cands, _T0, DEFAULT_TOLERANCE_S)
    assert got["o"] == 0
    assert drift == 0.0


def test_outside_tolerance_returns_none():
    cands = _cands([-10_000, 10_000])
    got, drift = _nearest(cands, _T0, DEFAULT_TOLERANCE_S)
    assert got is None
    assert drift == 0.0


def test_empty_candidates_is_safe():
    assert _nearest([], _T0, DEFAULT_TOLERANCE_S) == (None, 0.0)


def test_single_candidate_both_sides():
    assert _nearest([(_T0 + 1.0, {"x": 1})], _T0, DEFAULT_TOLERANCE_S)[0] == {"x": 1}
    assert _nearest([(_T0 - 1.0, {"x": 1})], _T0, DEFAULT_TOLERANCE_S)[0] == {"x": 1}


def test_bisect_never_compares_dicts():
    """Two entries sharing a timestamp would make a naive
    bisect compare the dict payloads and raise TypeError."""
    cands = [(_T0, {"a": 1}), (_T0, {"b": 2})]
    got, _ = _nearest(cands, _T0, DEFAULT_TOLERANCE_S)
    assert got is not None


# ── retention projection ─────────────────────────────────────────


def test_index_retains_the_fields_consumers_read():
    idx, _, _ = build_gate_index(
        [
            _gate(
                _T0,
                scrum_armed=True,
                fold_armed=False,
                scrum_blockers=["delta"],
                fold_blockers=["mid"],
            )
        ]
    )
    _ts, e = idx["b1"][0]
    d = e["data"]
    assert d["scrum_armed"] is True
    assert d["fold_armed"] is False
    assert d["scrum_blockers"] == ["delta"]
    assert d["fold_blockers"] == ["mid"]


def test_index_drops_unread_payload():
    """The point of the projection: a 1.6 KB line must not be retained
    whole when four fields are read."""
    big = _gate(_T0)
    big["data"]["a_large_unused_field"] = "x" * 5000
    idx, _, _ = build_gate_index([big])
    _ts, e = idx["b1"][0]
    assert "a_large_unused_field" not in e["data"]


def test_pairing_properties_survive_projection():
    """scrum_armed / fold_armed / blockers read through gate_entry."""
    cov = classify_trades(
        [_trade(_T0, side="SELL")],
        [_gate(_T0, scrum_armed=True, scrum_blockers=["BB-below-upper"])],
    )
    p = cov.pairings[0]
    assert p.has_gate
    assert p.scrum_armed is True
    assert p.blockers() == ["BB-below-upper"]


def test_buy_reads_fold_blockers():
    cov = classify_trades(
        [_trade(_T0, side="BUY")], [_gate(_T0, fold_armed=True, fold_blockers=["MID"])]
    )
    assert cov.pairings[0].blockers() == ["MID"]


# ── streaming ────────────────────────────────────────────────────


def test_accepts_a_generator():
    """live_gate_decisions has always been a generator; nothing used to
    pass it without list()-ing first."""

    def gen():
        yield _gate(_T0)
        yield _gate(_T0 + 600)

    idx, first, last = build_gate_index(gen())
    assert len(idx["b1"]) == 2
    assert first < last


def test_classify_accepts_a_generator():
    cov = classify_trades([_trade(_T0)], (g for g in [_gate(_T0)]))
    assert cov.pairings[0].has_gate


def test_empty_generator_is_safe():
    cov = classify_trades([_trade(_T0)], (x for x in []))
    assert cov.gate_entry_count == 0
    assert cov.pairings[0].status == GateStatus.NO_GATE_DATA


# ── the mislabelled status ───────────────────────────────────────


def test_no_gate_in_tolerance_is_distinct_from_log_gap():
    """Entries exist close on both sides but none within tolerance.
    Previously reported as LOG_GAP, i.e. 'app was down' — which it
    demonstrably was not, since it logged either side."""
    gates = [_gate(_T0 - 400), _gate(_T0 + 400)]
    cov = classify_trades([_trade(_T0)], gates)
    assert cov.pairings[0].status == GateStatus.NO_GATE_IN_TOLERANCE


def test_real_log_gap_is_still_log_gap():
    """A genuine outage — entries far enough apart to exceed the gap
    threshold — must still classify as LOG_GAP."""
    gates = [_gate(_T0 - LOG_GAP_THRESHOLD_S * 2), _gate(_T0 + LOG_GAP_THRESHOLD_S * 2)]
    cov = classify_trades([_trade(_T0)], gates)
    assert cov.pairings[0].status == GateStatus.LOG_GAP


def test_before_logging_still_wins():
    gates = [_gate(_T0 + 10_000)]
    cov = classify_trades([_trade(_T0)], gates)
    assert cov.pairings[0].status == GateStatus.BEFORE_LOGGING


def test_no_gate_for_bot_still_wins():
    cov = classify_trades([_trade(_T0, bot="ghost")], [_gate(_T0, bot="other")])
    assert cov.pairings[0].status == GateStatus.NO_GATE_FOR_BOT


def test_new_status_has_a_human_label():
    """Without a label entry the report prints the raw status string."""
    from src.trading.gate_coverage import format_coverage_lines

    cov = classify_trades([_trade(_T0)], [_gate(_T0 - 400), _gate(_T0 + 400)])
    text = "\n".join(format_coverage_lines(cov))
    assert (
        GateStatus.NO_GATE_IN_TOLERANCE not in text
    ), "raw status string leaked into operator-facing output"
    assert "within tolerance" in text
