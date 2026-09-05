"""Pins for the live-baseline capture tool.

Every fixture here is synthetic and written under ``tmp_path``; the tool is
never pointed at the operator's runtime tree from a test.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from tools import capture_live_baseline as clb

MODULE_PATH = Path(clb.__file__)

_BLOCKER_SIBLINGS = [
    "TA-conf-below-floor(dir=BEARISH,conf=0.04<0.20)",
    "TA-conf-below-floor(dir=BEARISH,conf=0.09<0.25)",
    "TA-conf-below-floor(dir=BEARISH,conf=0.00<0.25)",
]

_PREFLIGHT = (
    "Bot {bot} sell failed: PRE-FLIGHT REJECTED: SELL notional ${n} "
    "({units} × ${px}) is below {sym} min_cost $1.0000. API not called."
)


def _gate_line(bot_id, symbol, stamp, scrum_armed, fold_armed, scrum, fold):
    return json.dumps(
        {
            "timestamp": stamp,
            "category": "gate",
            "bot_id": bot_id,
            "data": {
                "symbol": symbol,
                "scrum_armed": scrum_armed,
                "fold_armed": fold_armed,
                "scrum_blockers": scrum,
                "fold_blockers": fold,
            },
        }
    )


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_blocker_normaliser_groups_numeric_siblings():
    """Fails when a measured number keeps two readings of one gate apart."""
    keys = {clb.normalise_blocker(b) for b in _BLOCKER_SIBLINGS}
    assert keys == {"TA-conf-below-floor(dir=BEARISH,conf=#<#)"}


def test_blocker_siblings_are_distinct_before_normalising():
    """Control: fails if the siblings were already equal, making the pin free."""
    assert len(set(_BLOCKER_SIBLINGS)) == len(_BLOCKER_SIBLINGS)


def test_blocker_normaliser_keeps_direction_vocabulary():
    """Fails when direction is normalised away and a gate flip reads as no change."""
    bullish = clb.normalise_blocker("TA-not-bearish(dir=BULLISH)")
    bearish = clb.normalise_blocker("TA-not-bearish(dir=BEARISH)")
    assert bullish != bearish


def test_gate_capture_counts_latches_and_keeps_one_example(tmp_path):
    """Fails when the latch tally, the blocker grouping or its example is lost."""
    log = _write(
        tmp_path / "gate.log",
        [
            _gate_line(
                "aaaa1111",
                "SUI/USD",
                "2026-08-27T10:00:00+00:00",
                True,
                False,
                [],
                _BLOCKER_SIBLINGS[:1],
            ),
            _gate_line(
                "aaaa1111",
                "SUI/USD",
                "2026-08-27T11:00:00+00:00",
                False,
                True,
                ["delta≤0"],
                _BLOCKER_SIBLINGS[1:2],
            ),
        ],
    )
    got = clb.capture_gate([log])
    bot = got["bots"]["aaaa1111"]
    assert bot["events"] == 2
    assert bot["scrum_armed"] == 1
    assert bot["fold_armed"] == 1
    fold = got["blocker_vocabulary"]["fold"]
    assert fold["TA-conf-below-floor(dir=BEARISH,conf=#<#)"]["count"] == 2
    assert fold["TA-conf-below-floor(dir=BEARISH,conf=#<#)"]["example"] in (
        _BLOCKER_SIBLINGS
    )
    assert got["totals"]["first_ts"] == "2026-08-27T10:00:00+00:00"
    assert got["totals"]["last_ts"] == "2026-08-27T11:00:00+00:00"


def test_gate_capture_survives_a_truncated_line(tmp_path):
    """Fails when one half-written JSON line costs the rest of the file."""
    good = _gate_line(
        "aaaa1111", "SUI/USD", "2026-08-27T10:00:00+00:00", True, False, [], []
    )
    log = tmp_path / "gate.log"
    log.write_text(
        good + "\n" + good[:120] + "\n" + "[]\n" + good + "\n", encoding="utf-8"
    )
    got = clb.capture_gate([log])
    assert got["totals"]["events"] == 2
    assert got["totals"]["malformed"] == 2
    assert got["files"][0]["lines"] == 4


def test_gate_since_filter_drops_older_records(tmp_path):
    """Fails when --since silently keeps records from a previous build."""
    log = _write(
        tmp_path / "gate.log",
        [
            _gate_line(
                "aaaa1111", "SUI/USD", "2026-06-01T00:00:00+00:00", True, False, [], []
            ),
            _gate_line(
                "aaaa1111", "SUI/USD", "2026-08-27T00:00:00+00:00", True, False, [], []
            ),
        ],
    )
    got = clb.capture_gate([log], since="2026-08-01T00:00:00+00:00")
    assert got["totals"]["events"] == 1
    assert got["totals"]["skipped_by_since"] == 1


def test_console_grouper_folds_one_error_class_and_splits_by_symbol(tmp_path):
    """Fails when the pre-flight rejections stop being one class split by pair."""
    rows = []
    for i in range(3):
        rows.append(
            "2026-08-27 16:23:%02d,359 [ERROR] " % i
            + _PREFLIGHT.format(
                bot="c1f7469a",
                n=f"0.146{i}",
                units="0.18731515",
                px="0.78",
                sym="SUI/USD",
            )
        )
    rows.append(
        "2026-08-27 16:30:00,000 [ERROR] "
        + _PREFLIGHT.format(
            bot="7c30a150", n="0.5", units="1.25", px="0.40", sym="BIO/USD"
        )
    )
    log = _write(tmp_path / "system.log", rows)
    got = clb.capture_console([log], clb.build_symbol_pattern(["SUI", "BIO"]))
    errors = got["classes"]["ERROR"]
    assert len(errors) == 1
    only = next(iter(errors.values()))
    assert only["count"] == 4
    assert only["by_symbol"] == {"SUI/USD": 3, "BIO/USD": 1}
    assert only["by_bot"] == {"c1f7469a": 3, "7c30a150": 1}
    assert "PRE-FLIGHT REJECTED" in only["example"]
    assert got["levels"] == {"ERROR": 4}


def test_console_messages_are_distinct_before_normalising():
    """Control: fails if the raw messages already matched, making the grouper free."""
    raw = {
        _PREFLIGHT.format(
            bot="c1f7469a", n="0.1463", units="0.187", px="0.78", sym="SUI/USD"
        ),
        _PREFLIGHT.format(
            bot="7c30a150", n="0.5", units="1.25", px="0.40", sym="BIO/USD"
        ),
    }
    assert len(raw) == 2


def test_console_grouper_keeps_bare_ticker_out_of_the_class_key():
    """Fails when a per-asset warning splits into one class per asset."""
    symbols = clb.build_symbol_pattern(["LTC", "AERO"])
    a = clb.normalise_message("over-commit on LTC: 0.53 + 0.47 > 0.47", symbols)
    b = clb.normalise_message("over-commit on AERO: 64.1 + 50 > 50", symbols)
    assert a == b == "over-commit on <SYM>: # + # > #"


def test_console_capture_counts_a_continuation_line_separately(tmp_path):
    """Fails when a traceback line is booked as a record and inflates a level."""
    log = _write(
        tmp_path / "system.log",
        [
            "2026-08-27 16:23:33,359 [ERROR] boom",
            "Traceback (most recent call last):",
            "  File 'x.py', line 1",
        ],
    )
    got = clb.capture_console([log])
    assert got["totals"]["records"] == 1
    assert got["totals"]["continuations"] == 2
    assert got["levels"] == {"ERROR": 1}


def test_symbol_pattern_prefers_the_longer_ticker():
    """Fails when LSETH is shortened to LSE and two assets merge."""
    pattern = clb.build_symbol_pattern(["LSE", "LSETH"])
    assert pattern is not None
    assert pattern.sub("<SYM>", "holdings on LSETH now") == "holdings on <SYM> now"


def test_symbol_pattern_is_none_without_usable_tickers():
    """Fails when an empty fleet compiles a pattern that matches everything."""
    assert clb.build_symbol_pattern(["", "None", "x"]) is None


def test_emitter_capture_names_the_declared_pins_that_never_fired(tmp_path):
    """Fails when a pin that produced nothing is not reported as silent."""
    log = _write(
        tmp_path / "session.jsonl",
        [
            json.dumps(
                {"ts": "2026-08-27T10:00:00+00:00", "name": "a.1.x", "count": 1}
            ),
            json.dumps(
                {"ts": "2026-08-27T11:00:00+00:00", "name": "a.1.x", "count": 1}
            ),
            json.dumps({"ts": "2026-08-27T11:00:00+00:00", "name": "c.3.raw.rsi"}),
            "{ truncated",
        ],
    )
    declared = {"a.1.x": "always_on", "b.2.y": "toggle", "c.3.raw.{}": "always_on"}
    got = clb.capture_emitters([log], declared)
    assert got["totals"]["records"] == 3
    assert got["totals"]["malformed"] == 1
    assert got["silent_declared_pins"] == ["b.2.y"]
    assert got["undeclared_names"] == []
    assert got["seen_declared_pins"] == {"a.1.x": 2, "c.3.raw.{}": 1}
    assert got["seen_names"]["a.1.x"]["per_hour"] == 2.0


def test_undeclared_emitter_name_is_reported(tmp_path):
    """Fails when an emitter outside the roster passes unnoticed."""
    log = _write(
        tmp_path / "session.jsonl",
        [json.dumps({"ts": "2026-08-27T10:00:00+00:00", "name": "z.9.stranger"})],
    )
    got = clb.capture_emitters([log], {"a.1.x": "toggle"})
    assert got["undeclared_names"] == ["z.9.stranger"]


def test_template_pin_does_not_swallow_its_own_prefix():
    """Fails when a bare template prefix resolves as one of its own leaves."""
    declared = {"c.3.raw.{}": "always_on"}
    assert clb.declared_pin_for("c.3.raw.rsi", declared) == "c.3.raw.{}"
    assert clb.declared_pin_for("c.3.raw.", declared) is None


def _fleet_payload():
    return {
        "version": "1.9.5",
        "saved_at": 1787884504.4,
        "bot_count": 1,
        "bots": {
            "c8e5c5db": {
                "state_when_saved": "running",
                "config": {
                    "symbol": "CHIP/USD",
                    "target_asset": "CHIP",
                    "base_currency": "USD",
                    "exchange_id": "coinbase",
                    "mode": "scrumming",
                    "investment_amount": 200.0,
                    "max_target_growth_pct": 1.0,
                    "profit_route": "fold_to_target",
                },
                "scrumming_state": {
                    "target_balance": 261.0,
                    "anchor_target_balance": 251.0,
                    "fold_queue_usd": 24.0,
                    "fold_tranches": [{"usd": 1.5, "units": 23.0}],
                    "stack_tranches": [],
                    "main_lots": [{"units": 81.0}, {"units": 745.0}],
                    "tranches_created_lifetime": 6,
                    "tranches_closed_lifetime": 2,
                    "last_trade_side": "FOLD",
                    "last_trade_price": 0.03962,
                },
                "stats": {
                    "position_value": 256.25,
                    "current_price": 0.03885,
                    "cash_balance_usd": 1918.48,
                    "total_folded_usd": 1585.85,
                },
            }
        },
        "smart_wires": [{"source_id": "c8e5c5db", "target_id": "aaaa1111", "pct": 5.0}],
        "smart_wire_ledgers": [
            {"bot_id": "c8e5c5db", "asset": "CHIP", "wired_in": 1.0}
        ],
    }


def test_fleet_capture_reads_tranches_lots_and_wires(tmp_path):
    """Fails when a tranche, a lot or a wire edge is dropped from the snapshot."""
    state = tmp_path / "bot_state.json"
    state.write_text(json.dumps(_fleet_payload()), encoding="utf-8")
    got = clb.capture_fleet(state)
    bot = got["bots"]["c8e5c5db"]
    assert bot["identity"]["anchor_target_balance"] == 251.0
    assert bot["position"]["accrued_growth_usd"] == 10.0
    assert bot["position"]["fold_tranche_count"] == 1
    assert bot["position"]["fold_tranche_usd"] == 1.5
    assert bot["position"]["stack_tranche_count"] == 0
    assert bot["position"]["lot_count"] == 2
    assert bot["position"]["position_units"] == 826.0
    assert got["totals"]["bot_count"] == 1
    assert got["totals"]["position_value_usd"] == 256.25
    assert got["wires"]["edge_count"] == 1
    assert got["wires"]["ledger_count"] == 1
    assert got["source"]["changed_during_read"] is False
    assert got["source"]["size_before"] == got["source"]["size_after"]


def test_fleet_capture_reports_a_decode_error_without_raising(tmp_path):
    """Fails when a half-written state file aborts the whole capture."""
    state = tmp_path / "bot_state.json"
    state.write_text('{"bots": {', encoding="utf-8")
    got = clb.capture_fleet(state)
    assert "decode_error" in got["source"]
    assert got["source"]["present"] is True


def test_boolean_is_not_booked_as_a_number():
    """Fails when a True in the state file is folded into a dollar total."""
    assert clb.as_number(True) is None
    assert clb.as_number("20.0") is None
    assert clb.as_number(20) == 20.0


def _snapshot(target_balance=261.0, fold_classes=("A(#)", "B(#)")):
    return {
        "build": {
            "version": "3.27.0",
            "git_head": "ba2dfca",
            "git_dirty_tracked": False,
            "gate_stamp": None,
        },
        "capture": {"captured_at_utc": "2026-08-27T20:00:00+00:00"},
        "fleet": {
            "bots": {
                "c8e5c5db": {
                    "identity": {"symbol": "CHIP/USD", "anchor_target_balance": 251.0},
                    "position": {"target_balance": target_balance},
                }
            },
            "totals": {"bot_count": 1},
            "wires": {"edges": []},
        },
        "gate_latch": {
            "blocker_vocabulary": {
                "scrum": {},
                "fold": {c: {"count": 10, "example": c} for c in fold_classes},
            },
            "totals": {"events": 100},
            "bots": {},
        },
        "console_classes": {"levels": {"ERROR": 1}, "classes": {"ERROR": {}}},
        "emitters": {
            "silent_declared_pins": ["b.2.y"],
            "undeclared_names": [],
            "seen_declared_pins": {"a.1.x": 5},
        },
    }


def test_compare_reports_no_change_between_identical_snapshots():
    """Control: fails if the comparison invents a finding from equal inputs."""
    found = clb.compare(_snapshot(), _snapshot())
    assert found == {"identity": [], "drift": [], "movement": []}


def test_compare_surfaces_a_changed_target_balance_as_movement():
    """Fails when a moved dollar target is not reported with its delta."""
    found = clb.compare(_snapshot(), _snapshot(target_balance=999.0))
    assert found["drift"] == []
    assert found["movement"] == ["fleet: bot c8e5c5db target_balance 261 -> 999 (+738)"]


def test_compare_surfaces_a_dropped_blocker_class_as_drift():
    """Fails when a gate blocker vocabulary loss passes as ordinary movement."""
    found = clb.compare(_snapshot(), _snapshot(fold_classes=("A(#)",)))
    assert found["movement"] == []
    assert found["drift"] == ["gate: fold blocker class GONE 'B(#)' (was 10)"]


def test_compare_surfaces_build_identity_separately():
    """Fails when a version or HEAD change is buried among moved counts."""
    after = _snapshot()
    after["build"]["version"] = "3.28.0"
    found = clb.compare(_snapshot(), after)
    assert found["identity"] == ["build.version: '3.27.0' -> '3.28.0'"]
    assert found["drift"] == []


def test_compare_surfaces_a_removed_bot_and_a_silenced_pin():
    """Fails when a lost bot or a newly silent emitter is not called drift."""
    after = copy.deepcopy(_snapshot())
    after["fleet"]["bots"].clear()
    after["emitters"]["silent_declared_pins"] = ["a.1.x", "b.2.y"]
    found = clb.compare(_snapshot(), after)
    assert "fleet: bot c8e5c5db REMOVED (CHIP/USD)" in found["drift"]
    assert "emitters: pin WENT SILENT a.1.x" in found["drift"]


def test_format_comparison_truncates_movement_but_never_drift():
    """Fails when a long movement list pushes drift lines out of the report."""
    found = {
        "identity": [],
        "drift": ["d1", "d2"],
        "movement": ["m%d" % i for i in range(9)],
    }
    text = clb.format_comparison(_snapshot(), _snapshot(), found, movement_limit=3)
    assert "d1" in text and "d2" in text
    assert "m0" in text and "m8" not in text
    assert "6 further moved values" in text


def test_compare_mode_exits_nonzero_on_drift(tmp_path):
    """Fails when --fail-on-drift cannot be used to break a build check."""
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(_snapshot()), encoding="utf-8")
    b.write_text(json.dumps(_snapshot(fold_classes=("A(#)",))), encoding="utf-8")
    assert clb.main(["--compare", str(a), str(b), "--fail-on-drift"]) == 1
    assert clb.main(["--compare", str(a), str(a), "--fail-on-drift"]) == 0


def test_module_never_opens_a_file_for_writing_outside_write_snapshot():
    """Fails when a write path appears anywhere but the snapshot writer."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    writers = {"write_text", "write_bytes", "unlink", "rename", "touch", "rmdir"}
    offenders = []
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in writers and func.name != "write_snapshot":
                    offenders.append(f"{func.name}:{node.func.attr}")
                if node.func.attr == "open":
                    mode = _mode_of(node)
                    if mode != "r":
                        offenders.append(f"{func.name}:open({mode})")
    assert offenders == []


def _mode_of(node: ast.Call) -> str:
    for i, arg in enumerate(node.args):
        if i == 0 and isinstance(arg, ast.Constant):
            return str(arg.value)
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return "?"


def test_module_makes_only_one_directory_and_it_is_the_output_directory():
    """Fails when the tool can create a directory anywhere but its own output."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    owners = [
        func.name
        for func in ast.walk(tree)
        if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "mkdir"
    ]
    assert owners == ["write_snapshot"]


def test_a_credential_store_is_refused_by_name(tmp_path):
    """Fails when the tool would open the operator's exchange credentials."""
    secret = tmp_path / "coinbase_credentials.json"
    secret.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="secret"):
        clb.capture_fleet(secret)


def test_display_path_never_leaks_a_user_directory(tmp_path):
    """Fails when a snapshot records an absolute, machine-specific path."""
    rendered = clb.display_path(Path.home() / ".acervator" / "bot_state.json")
    assert rendered == "~/.acervator/bot_state.json"
    assert str(Path.home()) not in rendered


def test_class_key_redacts_the_home_directory_but_the_example_stays_verbatim(tmp_path):
    """Fails when a machine-specific path enters the diffable class vocabulary."""
    home = str(Path.home())
    tail = r"\\.acervator\\bot_state.tmp"
    raw = f"Failed to save bot state: [WinError 5] denied: '{home}{tail}'"
    log = _write(tmp_path / "system.log", ["2026-08-27 16:23:33,359 [ERROR] " + raw])
    got = clb.capture_console([log])
    key, entry = next(iter(got["classes"]["ERROR"].items()))
    assert home not in key
    assert "~" in key
    assert entry["example"] == raw


def test_home_directory_is_present_before_redaction():
    """Control: fails if the fixture never carried a home path to redact."""
    tail = r"\\.acervator\\bot_state.tmp"
    assert str(Path.home()) in f"denied: '{Path.home()}{tail}'"
