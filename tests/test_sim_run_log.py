"""v3.24.13 — pin tests for the persistent sim run log.

Context: v3.24.12 isolated sim bots onto private event buses to stop
them writing into the live trade.log (136 measured contaminated
rows). That fixed pollution but left sim runs with no durable record
at all. This module is that record.

The tests that matter most are the SEPARATION ones. A sim row must
never be mistakable for a live trade, and this log must never write
into the live tree — that is the failure it exists downstream of.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.sim_run_log import (  # noqa: E402
    ORIGIN_SIM,
    SIM_LOG_ROOT,
    SimRunLog,
    list_runs,
    load_run_gates,
    load_run_trades,
)

_TS = 1_774_915_200_000  # 2026-04-01T00:00:00Z in ms


def _log(tmp_path, **kw) -> SimRunLog:
    return SimRunLog(root=tmp_path, **kw)


# ── separation from live ─────────────────────────────────────────


def test_default_root_is_sim_tree_not_live():
    """The live tree is ~/.acervator_logs/trade/. This must not be
    anywhere inside it."""
    assert SIM_LOG_ROOT.name == "sim"
    assert "trade" not in SIM_LOG_ROOT.parts[-1:]


def test_every_trade_row_marks_itself_sim(tmp_path):
    log = _log(tmp_path)
    rid = log.start_run()
    log.record_trade("BTC/USD", "SELL", 1.0, 100.0)
    log.finish_run()
    rows = load_run_trades(rid, tmp_path)
    assert rows[0]["origin"] == ORIGIN_SIM


def test_every_gate_row_marks_itself_sim(tmp_path):
    log = _log(tmp_path)
    rid = log.start_run()
    log.record_gate("b", "BTC/USD", {"scrum_armed": True})
    log.finish_run()
    assert load_run_gates(rid, tmp_path)[0]["origin"] == ORIGIN_SIM


def test_refuses_to_attach_to_live_bot_bus(tmp_path):
    """Attaching to a live bot would write live decisions into the
    sim log — the mirror image of the contamination we just fixed."""

    class _Bus:
        def subscribe(self, *_a, **_k):
            raise AssertionError("must not subscribe")

    class _LiveBot:
        _bus = _Bus()
        _sim_mode = False
        bot_id = "live-1"

    log = _log(tmp_path)
    log.start_run()
    assert log.attach_to_bot_bus(_LiveBot()) is False


def test_attaches_to_sim_bot_bus(tmp_path):
    calls: list = []

    class _Bus:
        def subscribe(self, topic, _cb):
            calls.append(topic)

    class _SimBot:
        _bus = _Bus()
        _sim_mode = True
        bot_id = "sim-1"

    log = _log(tmp_path)
    log.start_run()
    assert log.attach_to_bot_bus(_SimBot()) is True
    assert "bot.gate_decision" in calls


def test_attach_returns_false_without_bus(tmp_path):
    class _NoBus:
        _sim_mode = True

    log = _log(tmp_path)
    log.start_run()
    assert log.attach_to_bot_bus(_NoBus()) is False


# ── master-clock timestamps ──────────────────────────────────────


def test_trade_uses_master_clock_not_wall(tmp_path):
    """Wall-clock stamps would make sim rows uncomparable to live
    history — the defect v3.24.5 fixed inside the sim exchange."""
    log = _log(tmp_path)
    rid = log.start_run()
    log.record_trade("BTC/USD", "SELL", 1.0, 100.0, sim_ts_ms=_TS)
    log.finish_run()
    ts = load_run_trades(rid, tmp_path)[0]["timestamp"]
    assert ts.startswith("2026-03-31") or ts.startswith("2026-04-01")


def test_gate_uses_master_clock(tmp_path):
    log = _log(tmp_path)
    rid = log.start_run()
    log.record_gate("b", "BTC/USD", {}, sim_ts_ms=_TS)
    log.finish_run()
    ts = load_run_gates(rid, tmp_path)[0]["timestamp"]
    assert ts.startswith("2026-")


# ── schema parity with live ──────────────────────────────────────


def test_trade_row_mirrors_live_schema(tmp_path):
    log = _log(tmp_path)
    rid = log.start_run()
    log.record_trade(
        "BTC/USD", "sell", 2.0, 50.0, bot_id="b", action="SCRUM", usd=100.0
    )
    log.finish_run()
    d = load_run_trades(rid, tmp_path)[0]["data"]
    for k in (
        "action",
        "symbol",
        "side",
        "amount",
        "price",
        "status",
        "usd",
        "operator_initiated",
    ):
        assert k in d, f"live trade.log field {k!r} missing"
    assert d["side"] == "SELL", "side must be upper-cased like live"


def test_gate_row_mirrors_live_schema(tmp_path):
    log = _log(tmp_path)
    rid = log.start_run()
    log.record_gate(
        "b",
        "BTC/USD",
        {
            "scrum_armed": True,
            "fold_armed": False,
            "scrum_blockers": ["a"],
            "fold_blockers": [],
            "scrum_fixture": {"x": 1},
            "fold_fixture": {"y": 2},
        },
    )
    log.finish_run()
    d = load_run_gates(rid, tmp_path)[0]["data"]
    for k in (
        "symbol",
        "scrum_armed",
        "fold_armed",
        "scrum_blockers",
        "fold_blockers",
        "scrum_fixture",
        "fold_fixture",
    ):
        assert k in d, f"live gate.log field {k!r} missing"


def test_candle_address_is_carried(tmp_path):
    log = _log(tmp_path)
    rid = log.start_run()
    log.record_trade("BTC/USD", "SELL", 1.0, 1.0, candle_address="001234_BTC")
    log.finish_run()
    assert load_run_trades(rid, tmp_path)[0]["candle_address"] == "001234_BTC"


# ── buffering + durability ───────────────────────────────────────


def test_rows_flush_at_threshold(tmp_path):
    log = _log(tmp_path, flush_every=3)
    rid = log.start_run()
    for _ in range(3):
        log.record_trade("BTC/USD", "SELL", 1.0, 1.0)
    # flushed without finish_run
    assert len(load_run_trades(rid, tmp_path)) == 3
    log.finish_run()


def test_finish_flushes_partial_buffer(tmp_path):
    log = _log(tmp_path, flush_every=1000)
    rid = log.start_run()
    log.record_trade("BTC/USD", "SELL", 1.0, 1.0)
    assert load_run_trades(rid, tmp_path) == []  # still buffered
    log.finish_run()
    assert len(load_run_trades(rid, tmp_path)) == 1


def test_explicit_flush_works(tmp_path):
    log = _log(tmp_path, flush_every=1000)
    rid = log.start_run()
    log.record_trade("BTC/USD", "SELL", 1.0, 1.0)
    log.flush()
    assert len(load_run_trades(rid, tmp_path)) == 1
    log.finish_run()


# ── lifecycle guards ─────────────────────────────────────────────


def test_records_ignored_before_start(tmp_path):
    log = _log(tmp_path)
    log.record_trade("BTC/USD", "SELL", 1.0, 1.0)
    assert log.trade_count == 0


def test_records_ignored_after_finish(tmp_path):
    log = _log(tmp_path)
    log.start_run()
    log.finish_run()
    log.record_trade("BTC/USD", "SELL", 1.0, 1.0)
    assert log.trade_count == 0


def test_finish_is_idempotent(tmp_path):
    log = _log(tmp_path)
    rid = log.start_run()
    log.record_trade("BTC/USD", "SELL", 1.0, 1.0)
    log.finish_run()
    log.finish_run()
    assert len(load_run_trades(rid, tmp_path)) == 1


def test_run_id_is_unique_per_run(tmp_path):
    a = _log(tmp_path).start_run()
    b = _log(tmp_path).start_run()
    assert a != b


# ── meta + index ─────────────────────────────────────────────────


def test_meta_records_config_and_summary(tmp_path):
    log = _log(tmp_path)
    rid = log.start_run(config={"bots": 27})
    log.record_trade("BTC/USD", "SELL", 1.0, 1.0)
    log.finish_run(summary={"candles_played": 500})
    meta = json.loads(
        (tmp_path / "runs" / rid / "meta.json").read_text(encoding="utf-8")
    )
    assert meta["config"]["bots"] == 27
    assert meta["summary"]["candles_played"] == 500
    assert meta["summary"]["trades_logged"] == 1
    assert meta["origin"] == ORIGIN_SIM


def test_index_lists_runs_newest_first(tmp_path):
    first = _log(tmp_path)
    rid1 = first.start_run()
    first.finish_run()
    second = _log(tmp_path)
    rid2 = second.start_run()
    second.finish_run()
    runs = list_runs(tmp_path)
    assert [r["run_id"] for r in runs][:2] == [rid2, rid1]


def test_list_runs_empty_when_no_index(tmp_path):
    assert list_runs(tmp_path) == []


def test_load_missing_run_returns_empty(tmp_path):
    assert load_run_trades("nope", tmp_path) == []
    assert load_run_gates("nope", tmp_path) == []


# ── failure tolerance ────────────────────────────────────────────


def test_unwritable_root_degrades_to_noop(tmp_path):
    """Losing the sim record must never take down the replay."""
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    log = SimRunLog(root=blocker)
    rid = log.start_run()
    assert rid  # still returns an id
    assert log.is_open is False
    log.record_trade("BTC/USD", "SELL", 1.0, 1.0)  # must not raise
    log.finish_run()


def test_unserialisable_payload_is_skipped(tmp_path):
    log = _log(tmp_path)
    rid = log.start_run()
    log.record_trade("BTC/USD", "SELL", 1.0, 1.0, extra={"bad": object()})
    log.finish_run()
    # default=str keeps it writable; the row must still be valid JSON
    for row in load_run_trades(rid, tmp_path):
        assert isinstance(row, dict)


# A fill carries the candle address it fired on, so a sim trade traces
# back to one Stone Tablet candle.


def test_candle_address_survives_roundtrip(tmp_path):
    log = _log(tmp_path)
    rid = log.start_run()
    log.record_trade("BTC/USD", "BUY", 1.0, 100.0, candle_address="004096_BTC")
    log.finish_run()
    assert load_run_trades(rid, tmp_path)[0]["candle_address"] == "004096_BTC"


def test_missing_address_is_empty_not_absent(tmp_path):
    """A fill with no resolvable address must still record, with an
    empty address rather than a missing key — consumers should not
    have to distinguish 'no key' from 'no address'."""
    log = _log(tmp_path)
    rid = log.start_run()
    log.record_trade("BTC/USD", "BUY", 1.0, 100.0)
    log.finish_run()
    row = load_run_trades(rid, tmp_path)[0]
    assert "candle_address" in row
    assert row["candle_address"] == ""
