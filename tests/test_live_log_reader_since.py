"""v3.24.24 — pin tests for the ``since`` fast path in live_log_reader.

THE DEFECT
==========
``since`` was applied AFTER ``json.loads``, so a narrow window still paid
a full parse of every line. On the operator's logs that is 165,062 rows
across 262,868,525 bytes, on the Qt thread, for every History page turn —
and the caller docstring claiming ``since`` stopped the iterators
"scanning back further than necessary" was false.

Measured after the fix:

    window        rows     time
    90d (all)  165,062   1.726 s
    30d            366   0.004 s     <- 431x
    7d             284   0.004 s
    1d              21   0.001 s

TWO FILTERS, BOTH CONSERVATIVE
==============================
1. File-level: a ROTATED file whose mtime precedes the cutoff cannot
   contain a qualifying row, because mtime is its last write. The ACTIVE
   file is never skipped — it is still being appended to, so its mtime
   says nothing about its oldest row.
2. Line-level: a raw-text ISO prefix comparison before ``json.loads``.

Neither is authoritative. The parsed-timestamp check still runs, so a
false keep costs one parse and a false reject is impossible by
construction. That matters because sim-parity tooling reads this same
path — silently dropping a gate decision would corrupt a parity claim
rather than merely slow it down.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading import live_log_reader as R  # noqa: E402

_T0 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _row(ts: datetime, bot="b1"):
    return json.dumps({
        "timestamp": ts.isoformat(), "category": "bot.gate_decision",
        "bot_id": bot,
        "data": {"symbol": "BTC/USD", "scrum_armed": False,
                 "fold_armed": False, "scrum_blockers": [],
                 "fold_blockers": []}})


# ── line-level pre-filter ────────────────────────────────────────

def test_older_line_is_rejected():
    line = _row(_T0 - timedelta(days=2))
    assert R._line_predates(line, (_T0).isoformat()[:19]) is True


def test_newer_line_is_kept():
    line = _row(_T0 + timedelta(days=2))
    assert R._line_predates(line, (_T0).isoformat()[:19]) is False


def test_line_without_timestamp_is_kept():
    """Conservative: anything unrecognised must survive to the
    authoritative parsed check."""
    assert R._line_predates('{"bot_id": "b1"}', "2026-06-01") is False


def test_malformed_stamp_is_kept():
    assert R._line_predates(
        '{"timestamp": "not-a-date", "bot_id": "b"}', "2026-06-01") \
        is False


def test_garbage_line_is_kept():
    assert R._line_predates("not json at all", "2026-06-01") is False


def test_empty_line_is_kept():
    assert R._line_predates("", "2026-06-01") is False


# ── file-level skip ──────────────────────────────────────────────

def test_rotated_file_older_than_since_is_skipped(tmp_path):
    p = tmp_path / "gate.log.3"
    p.write_text(_row(_T0 - timedelta(days=10)), encoding="utf-8")
    import os
    old = (_T0 - timedelta(days=9)).timestamp()
    os.utime(p, (old, old))
    assert R._file_predates(p, _T0) is True


def test_rotated_file_newer_than_since_is_kept(tmp_path):
    p = tmp_path / "gate.log.3"
    p.write_text(_row(_T0), encoding="utf-8")
    import os
    new = (_T0 + timedelta(days=1)).timestamp()
    os.utime(p, (new, new))
    assert R._file_predates(p, _T0) is False


def test_active_file_is_never_skipped(tmp_path):
    """It is still being appended to; its mtime says nothing about its
    oldest row."""
    p = tmp_path / "gate.log"
    p.write_text(_row(_T0), encoding="utf-8")
    import os
    old = (_T0 - timedelta(days=30)).timestamp()
    os.utime(p, (old, old))
    assert R._file_predates(p, _T0) is False


def test_missing_file_is_not_skipped(tmp_path):
    assert R._file_predates(tmp_path / "gate.log.9", _T0) is False


# ── end-to-end equivalence ───────────────────────────────────────

def _fixture_logs(tmp_path, monkeypatch):
    """Active file plus two rotated ones spanning a known range."""
    import os
    active = tmp_path / "gate.log"
    active.write_text("\n".join(
        _row(_T0 + timedelta(hours=h)) for h in range(4)),
        encoding="utf-8")
    r1 = tmp_path / "gate.log.1"
    r1.write_text("\n".join(
        _row(_T0 - timedelta(days=5, hours=h)) for h in range(4)),
        encoding="utf-8")
    old = (_T0 - timedelta(days=5)).timestamp()
    os.utime(r1, (old, old))
    r2 = tmp_path / "gate.log.2"
    r2.write_text("\n".join(
        _row(_T0 - timedelta(days=20, hours=h)) for h in range(4)),
        encoding="utf-8")
    older = (_T0 - timedelta(days=20)).timestamp()
    os.utime(r2, (older, older))
    monkeypatch.setattr(R, "LIVE_GATE_LOG", active)
    return active


def test_no_since_reads_every_row(tmp_path, monkeypatch):
    _fixture_logs(tmp_path, monkeypatch)
    assert len(list(R.live_gate_decisions(validate=False))) == 12


def test_since_matches_a_brute_force_filter(tmp_path, monkeypatch):
    """The fast path must return exactly what filtering every parsed
    row would return."""
    _fixture_logs(tmp_path, monkeypatch)
    for days in (0, 1, 3, 6, 10, 21, 40):
        since = _T0 - timedelta(days=days)
        fast = [e["timestamp"]
                for e in R.live_gate_decisions(
                    since=since, validate=False)]
        brute = [e["timestamp"]
                 for e in R.live_gate_decisions(validate=False)
                 if R._parse_ts(e["timestamp"]) >= since]
        assert sorted(fast) == sorted(brute), f"days={days}"


def test_since_actually_skips_rotated_files(tmp_path, monkeypatch):
    """The point of the file-level filter — not just correct, cheaper."""
    _fixture_logs(tmp_path, monkeypatch)
    opened: list[str] = []
    real = R._iter_ndjson_lines

    def spy(path):
        opened.append(path.name)
        yield from real(path)

    monkeypatch.setattr(R, "_iter_ndjson_lines", spy)
    list(R.live_gate_decisions(
        since=_T0 - timedelta(days=1), validate=False))
    assert "gate.log" in opened
    assert "gate.log.2" not in opened, "stale rotated file was parsed"


def test_boundary_row_is_included(tmp_path, monkeypatch):
    """>= since, not > since."""
    active = tmp_path / "gate.log"
    active.write_text(_row(_T0), encoding="utf-8")
    monkeypatch.setattr(R, "LIVE_GATE_LOG", active)
    assert len(list(R.live_gate_decisions(
        since=_T0, validate=False))) == 1
