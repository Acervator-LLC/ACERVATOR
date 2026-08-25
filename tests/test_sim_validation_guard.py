"""v3.24.12 — pin tests for the sim validation guard + bus isolation.

Two operator directives converge here:

    2026-08-02: "Should add further robustness so that the sim
    gracefully stops when encountering trade events that cannot be
    validated."

    2026-08-02: "we cannot validate anything beyond the 700 trades
    that have data so we have no need to scan the previous 3700 or
    so."

Scoping is tested as hard as halting, because a guard that halts on
out-of-window data is worse than no guard — it reports a data
emergency when the real situation is that gate logging started
later than the trade history.

The bus-isolation tests cover a MEASURED contamination: 136 of 699
rows in the live trade.log came from 50 sim bot_ids that do not
exist in bot_state.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.trading.sim_validation_guard import (  # noqa: E402
    SimValidationGuard,
    ValidationIssueType,
    ValidationPolicy,
    scope_to_validatable_window,
    validate_gate_entry,
    validate_trade_event,
)

_STEP = 300_000
_T0 = 1_774_915_200_000  # 2026-04-01T00:00:00Z (ms)
_T0_S = _T0 / 1000.0


def _rows(n: int, start: int = _T0) -> list[list[float]]:
    return [[start + i * _STEP, 100.0, 101.0, 99.0, 100.5, 5.0] for i in range(n)]


def _trade(ts_s: float) -> dict:
    return {"timestamp": ts_s, "bot_id": "b", "symbol": "BTC/USD", "side": "SELL"}


# ── scoping: must not halt on out-of-window data ─────────────────


def test_scope_excludes_pre_window_trades():
    window_start = _T0_S + 1000
    trades = [_trade(window_start - 500), _trade(window_start + 500)]
    res = scope_to_validatable_window(trades, window_start)
    assert len(res.in_scope) == 1
    assert len(res.out_of_scope) == 1


def test_scope_excludes_post_window_trades():
    res = scope_to_validatable_window(
        [_trade(_T0_S + 50), _trade(_T0_S + 5000)], _T0_S, _T0_S + 1000
    )
    assert len(res.in_scope) == 1
    assert len(res.out_of_scope) == 1


def test_scope_open_ended_when_no_end_given():
    res = scope_to_validatable_window([_trade(_T0_S + 10**9)], _T0_S)
    assert len(res.in_scope) == 1


def test_scope_keeps_unparseable_timestamps_in_scope():
    """A zero timestamp is itself a defect — the guard must see it
    rather than have scoping quietly discard it."""
    res = scope_to_validatable_window([_trade(0.0)], _T0_S)
    assert len(res.in_scope) == 1
    assert res.out_of_scope == []


def test_scope_describe_states_exclusion_is_not_failure():
    res = scope_to_validatable_window([_trade(_T0_S - 10)], _T0_S)
    assert "not failures" in res.describe()


def test_scope_handles_empty_input():
    res = scope_to_validatable_window([], _T0_S)
    assert res.total == 0
    assert "no trades" in res.describe()


# ── halting behaviour ────────────────────────────────────────────


def test_valid_trade_records_nothing():
    g = SimValidationGuard()
    ok = validate_trade_event(
        g, "BTC/USD", "b", (_T0 + 50 * _STEP) / 1000.0, _rows(100)
    )
    assert ok is True
    assert g.issues == []
    assert g.should_halt is False


def test_missing_tablet_is_recorded():
    g = SimValidationGuard()
    assert validate_trade_event(g, "X/USD", "b", _T0_S, []) is False
    assert g.issues[0].issue_type == ValidationIssueType.NO_TABLET


def test_pre_listing_trade_is_recorded():
    g = SimValidationGuard()
    ok = validate_trade_event(g, "BTC/USD", "b", (_T0 - _STEP) / 1000.0, _rows(100))
    assert ok is False
    assert g.issues[0].issue_type == ValidationIssueType.PRE_LISTING


def test_zero_timestamp_is_recorded():
    g = SimValidationGuard()
    assert validate_trade_event(g, "BTC/USD", "b", 0.0, _rows(100)) is False
    assert g.issues[0].issue_type == (ValidationIssueType.UNRESOLVABLE_TS)


def test_halts_after_exceeding_tolerance():
    g = SimValidationGuard(policy=ValidationPolicy(max_tolerated=2))
    for _ in range(3):
        validate_trade_event(g, "X/USD", "b", _T0_S, [])
    assert g.should_halt is True
    assert "exceeded the limit of 2" in g.halt_reason


def test_does_not_halt_within_tolerance():
    g = SimValidationGuard(policy=ValidationPolicy(max_tolerated=5))
    for _ in range(3):
        validate_trade_event(g, "X/USD", "b", _T0_S, [])
    assert g.should_halt is False


def test_strict_policy_halts_on_first_issue():
    g = SimValidationGuard(policy=ValidationPolicy.strict())
    validate_trade_event(g, "X/USD", "b", _T0_S, [])
    assert g.should_halt is True


def test_permissive_policy_never_halts():
    g = SimValidationGuard(policy=ValidationPolicy.permissive())
    for _ in range(500):
        validate_trade_event(g, "X/USD", "b", _T0_S, [])
    assert g.should_halt is False
    assert len(g.issues) == 500


def test_disabled_policy_records_nothing():
    g = SimValidationGuard(policy=ValidationPolicy(enabled=False))
    g.record(ValidationIssueType.NO_TABLET)
    assert g.issues == []


# ── integrity issues halt immediately ────────────────────────────


def test_address_mismatch_halts_on_first_occurrence():
    """Stone Tablets are append-only; a shifted index means stored
    addresses across the whole dataset are suspect."""
    g = SimValidationGuard(policy=ValidationPolicy(max_tolerated=999))
    ok = validate_trade_event(
        g,
        "BTC/USD",
        "b",
        (_T0 + 5 * _STEP) / 1000.0,
        _rows(100),
        recorded_address="000099_BTC",
    )
    assert ok is False
    assert g.should_halt is True
    assert g.issues[0].issue_type == (ValidationIssueType.ADDRESS_MISMATCH)


def test_matching_address_does_not_halt():
    g = SimValidationGuard()
    ok = validate_trade_event(
        g,
        "BTC/USD",
        "b",
        (_T0 + 5 * _STEP) / 1000.0,
        _rows(100),
        recorded_address="000005_BTC",
    )
    assert ok is True
    assert g.should_halt is False


def test_integrity_ignored_when_halt_on_integrity_false():
    g = SimValidationGuard(
        policy=ValidationPolicy(max_tolerated=999, halt_on_integrity=False)
    )
    validate_trade_event(
        g,
        "BTC/USD",
        "b",
        (_T0 + 5 * _STEP) / 1000.0,
        _rows(100),
        recorded_address="000099_BTC",
    )
    assert g.should_halt is False
    assert g.integrity_count == 1


def test_halt_reason_fixed_at_first_cause():
    g = SimValidationGuard(policy=ValidationPolicy(max_tolerated=0))
    validate_trade_event(g, "AAA/USD", "b", _T0_S, [])
    first = g.halt_reason
    validate_trade_event(g, "BBB/USD", "b", _T0_S, [])
    assert g.halt_reason == first


# ── gate schema validation ───────────────────────────────────────


def _gate_entry() -> dict:
    return {
        "timestamp": "2026-06-14T12:00:00+00:00",
        "bot_id": "b",
        "data": {
            "symbol": "BTC/USD",
            "scrum_armed": True,
            "fold_armed": False,
            "scrum_blockers": [],
            "fold_blockers": [],
        },
    }


def test_valid_gate_entry_passes():
    g = SimValidationGuard()
    assert validate_gate_entry(g, _gate_entry()) is True
    assert g.issues == []


def test_gate_entry_missing_field_is_drift():
    g = SimValidationGuard()
    e = _gate_entry()
    del e["data"]["fold_armed"]
    assert validate_gate_entry(g, e) is False
    assert g.issues[0].issue_type == ValidationIssueType.SCHEMA_DRIFT
    assert "fold_armed" in g.issues[0].detail


def test_gate_entry_without_data_is_drift():
    g = SimValidationGuard()
    assert validate_gate_entry(g, {"bot_id": "b"}) is False
    assert g.issues[0].issue_type == ValidationIssueType.SCHEMA_DRIFT


# ── reporting ────────────────────────────────────────────────────


def test_report_clean_when_no_issues():
    body = "\n".join(SimValidationGuard().report_lines())
    assert "no unvalidatable" in body


def test_report_states_halt_reason():
    g = SimValidationGuard(policy=ValidationPolicy.strict())
    validate_trade_event(g, "X/USD", "b", _T0_S, [])
    body = "\n".join(g.report_lines())
    assert "HALTED" in body
    assert "halt reason" in body


def test_report_separates_integrity_from_coverage():
    g = SimValidationGuard(
        policy=ValidationPolicy(max_tolerated=999, halt_on_integrity=False)
    )
    validate_trade_event(g, "X/USD", "b", _T0_S, [])
    validate_trade_event(
        g,
        "BTC/USD",
        "b",
        (_T0 + 5 * _STEP) / 1000.0,
        _rows(100),
        recorded_address="000099_BTC",
    )
    body = "\n".join(g.report_lines())
    assert "1 integrity" in body
    assert "1 coverage" in body


# ── sim bus isolation (measured contamination fix) ───────────────


def test_sim_bot_gets_isolated_bus():
    from src.core.event_bus import get_event_bus
    from src.trading.bot_container import BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    cfg = make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="test",
        base_currency="USD",
        target_asset="BTC",
        target_balance=100.0,
    )

    class _Ex:
        exchange_id = "test"

    live = ScrummingBot(cfg, _Ex(), enable_phantoms=False)
    sim = ScrummingBot(cfg, _Ex(), enable_phantoms=False, sim_mode=True)
    assert live._bus is get_event_bus()
    assert sim._bus is not get_event_bus()


def test_sim_emits_do_not_reach_global_bus():
    """The measured defect: sim trades landed in live trade.log."""
    from src.core.event_bus import get_event_bus
    from src.trading.bot_container import BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    seen: list = []
    get_event_bus().subscribe("trade.filled", seen.append)

    cfg = make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="test",
        base_currency="USD",
        target_asset="BTC",
        target_balance=100.0,
    )

    class _Ex:
        exchange_id = "test"

    sim = ScrummingBot(cfg, _Ex(), enable_phantoms=False, sim_mode=True)
    sim._bus.emit("trade.filled", bot_id="sim", data={"type": "SCRUM"})
    assert seen == [], "sim emit must not reach the live bus"

    live = ScrummingBot(cfg, _Ex(), enable_phantoms=False)
    live._bus.emit("trade.filled", bot_id="live", data={"type": "SCRUM"})
    assert len(seen) == 1, "live emit must still reach the bus"
