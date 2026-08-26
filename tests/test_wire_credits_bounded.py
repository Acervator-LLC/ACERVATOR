"""v3.24.20 — pin tests for bounded wire-credit provenance.

THE DEFECT
==========
``wire_credits`` grew without limit inside every fold tranche. Each wire
income event appends one entry to EVERY open tranche, so growth is
credits x tranches rather than credits.

Measured against the operator's live ``~/.acervator/bot_state.json``
(read-only) on 2026-08-04:

    file total          1,450,434 B
    wire_credits          377,851 B   = 26.1% of the whole file
    bot 7c4c4ff3          385,930 B, of which 96.0% was wire_credits
                          (3,325 entries across 27 tranches)

The file grew 35,640 B in the hours between the audit measuring it and
this fix landing, and it is re-serialised on a 60 s timer.

``grep`` finds appends at exactly two sites and ZERO readers: the list was
write-only.

WHY IT IS CAPPED AND NOT DELETED
================================
These entries are money provenance -- which source funded which tranche,
and when. Nothing reads them today, but discarding them outright loses the
audit trail for funds that actually moved. So detail is capped and the
overflow is folded into ``wire_credits_rolled``, which preserves count,
total USD and USD-per-source exactly.

**The conservation tests are the ones that matter.** A cap that loses
dollars would be worse than the bloat it fixes.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.scrumming.wire_routing import (  # noqa: E402
    _WIRE_CREDIT_CAP,
    _roll_wire_credit_overflow,
)


def _entry(i: int, usd: float = 1.0, source: str = "smart_wire"):
    return {"source": source, "usd": usd, "ref": f"r{i}", "ts": 1000 + i}


def _tranche(n: int, usd: float = 1.0, source: str = "smart_wire"):
    return {"usd": 100.0, "wire_credits": [_entry(i, usd, source) for i in range(n)]}


# ── conservation ─────────────────────────────────────────────────


def test_no_dollars_are_lost_when_rolling():
    """The invariant that matters: detail + aggregate must still sum to
    everything ever credited."""
    n = _WIRE_CREDIT_CAP * 5
    t = _tranche(n, usd=2.5)
    expected = 2.5 * n

    _roll_wire_credit_overflow(t)

    kept = sum(e["usd"] for e in t["wire_credits"])
    rolled = t["wire_credits_rolled"]["total_usd"]
    assert round(kept + rolled, 6) == round(expected, 6)


def test_every_event_is_still_counted():
    n = _WIRE_CREDIT_CAP * 3 + 7
    t = _tranche(n)
    _roll_wire_credit_overflow(t)
    total = len(t["wire_credits"]) + t["wire_credits_rolled"]["count"]
    assert total == n


def test_per_source_totals_are_preserved():
    """Provenance is the point. Which source funded the tranche must
    survive the roll-up even when the per-event rows do not."""
    t = {"usd": 100.0, "wire_credits": []}
    for i in range(_WIRE_CREDIT_CAP * 2):
        t["wire_credits"].append(_entry(i, 1.0, "alpha"))
    for i in range(_WIRE_CREDIT_CAP * 2):
        t["wire_credits"].append(_entry(i, 3.0, "beta"))

    _roll_wire_credit_overflow(t)

    rolled = t["wire_credits_rolled"]["by_source"]
    kept_alpha = sum(e["usd"] for e in t["wire_credits"] if e["source"] == "alpha")
    kept_beta = sum(e["usd"] for e in t["wire_credits"] if e["source"] == "beta")
    assert round(rolled.get("alpha", 0.0) + kept_alpha, 6) == round(
        1.0 * _WIRE_CREDIT_CAP * 2, 6
    )
    assert round(rolled.get("beta", 0.0) + kept_beta, 6) == round(
        3.0 * _WIRE_CREDIT_CAP * 2, 6
    )


def test_repeated_rolls_are_stable():
    """Compaction runs on every restore; it must be idempotent or the
    aggregate would double-count on each boot."""
    t = _tranche(_WIRE_CREDIT_CAP * 4)
    _roll_wire_credit_overflow(t)
    snapshot = dict(t["wire_credits_rolled"])
    for _ in range(5):
        _roll_wire_credit_overflow(t)
    assert t["wire_credits_rolled"] == snapshot


def test_incremental_rolls_match_one_big_roll():
    """Appending past the cap repeatedly must produce the same totals as
    rolling once at the end."""
    incremental = {"usd": 100.0, "wire_credits": []}
    for i in range(_WIRE_CREDIT_CAP * 6):
        incremental["wire_credits"].append(_entry(i, 1.5))
        _roll_wire_credit_overflow(incremental)

    bulk = _tranche(_WIRE_CREDIT_CAP * 6, usd=1.5)
    _roll_wire_credit_overflow(bulk)

    def total(t):
        return round(
            sum(e["usd"] for e in t["wire_credits"])
            + t.get("wire_credits_rolled", {}).get("total_usd", 0.0),
            6,
        )

    assert total(incremental) == total(bulk)


# ── the bound ────────────────────────────────────────────────────


def test_detail_is_capped():
    t = _tranche(_WIRE_CREDIT_CAP * 10)
    _roll_wire_credit_overflow(t)
    assert len(t["wire_credits"]) == _WIRE_CREDIT_CAP


def test_most_recent_entries_are_the_ones_kept():
    """Recent provenance is the useful kind; the oldest ages out."""
    t = _tranche(_WIRE_CREDIT_CAP + 5)
    _roll_wire_credit_overflow(t)
    refs = [e["ref"] for e in t["wire_credits"]]
    assert refs[-1] == f"r{_WIRE_CREDIT_CAP + 4}"
    assert refs[0] == "r5"


def test_under_cap_is_untouched():
    t = _tranche(_WIRE_CREDIT_CAP - 1)
    before = list(t["wire_credits"])
    assert _roll_wire_credit_overflow(t) == 0
    assert t["wire_credits"] == before
    assert "wire_credits_rolled" not in t


def test_exactly_at_cap_is_untouched():
    t = _tranche(_WIRE_CREDIT_CAP)
    assert _roll_wire_credit_overflow(t) == 0
    assert "wire_credits_rolled" not in t


def test_returns_number_rolled():
    t = _tranche(_WIRE_CREDIT_CAP + 13)
    assert _roll_wire_credit_overflow(t) == 13


# ── timestamps + robustness ──────────────────────────────────────


def test_timestamp_span_is_recorded():
    t = _tranche(_WIRE_CREDIT_CAP * 2)
    _roll_wire_credit_overflow(t)
    r = t["wire_credits_rolled"]
    assert r["first_ts"] == 1000
    assert r["last_ts"] == 1000 + _WIRE_CREDIT_CAP - 1


def test_missing_or_malformed_entries_do_not_raise():
    """State restored from an older build may hold anything."""
    t = {
        "usd": 100.0,
        "wire_credits": (
            [None, "junk", {"usd": "not-a-number"}, {}]
            + [_entry(i) for i in range(_WIRE_CREDIT_CAP * 2)]
        ),
    }
    _roll_wire_credit_overflow(t)  # must not raise
    assert len(t["wire_credits"]) == _WIRE_CREDIT_CAP


def test_absent_wire_credits_key_is_safe():
    assert _roll_wire_credit_overflow({"usd": 1.0}) == 0


def test_non_list_wire_credits_is_safe():
    assert _roll_wire_credit_overflow({"usd": 1.0, "wire_credits": "corrupt"}) == 0


def test_unknown_source_is_bucketed_not_dropped():
    t = {
        "usd": 100.0,
        "wire_credits": [{"usd": 2.0, "ts": 1} for _ in range(_WIRE_CREDIT_CAP * 2)],
    }
    _roll_wire_credit_overflow(t)
    by_src = t["wire_credits_rolled"]["by_source"]
    assert by_src.get("unknown", 0.0) > 0.0


# ── the real-world magnitude ─────────────────────────────────────


def test_worst_case_live_tranche_compacts_hard():
    """Bot 7c4c4ff3 carried 3,325 entries across 27 tranches — 96% of
    its persisted record. Per-tranche that is ~123 entries."""
    t = _tranche(123)
    _roll_wire_credit_overflow(t)
    assert len(t["wire_credits"]) == _WIRE_CREDIT_CAP
    assert t["wire_credits_rolled"]["count"] == 123 - _WIRE_CREDIT_CAP
