"""v3.24.20 — pin tests for three archetype-gate calibration defects.

All three let real bugs ship green while blocking on style. They were
found on 2026-08-04 by auditing why the gate passed a NameError that I
had just introduced in v3.24.19.

DEFECT 1 — possibly-unbound demoted wholesale
    v3.23.44 mapped `reportPossiblyUnboundVariable` to "low" because it
    fires 2,465 times across src/ + main.py. Measured breakdown:

        import-bound only (Qt try/except guard)   2,456   noise
        ASSIGNMENT-bound only (real flow bug)         9   real
        ambiguous                                     0

    The separation is total, so the blanket demotion was throwing away
    9 real defects to silence 2,456 false ones. One of the 9 was
    main.py:1107 `_autostart_bot_count` — an UnboundLocalError that
    killed startup on every fresh install. The gate saw it and passed.

DEFECT 2 — ruff family matched on code[0]
    `fam = code[0]` made every multi-letter key in the severity map
    unreachable, and collided SIM/SLF with bandit's S:
        SIM114 "combine these if branches" -> "S" -> HIGH -> BLOCKED
        RUF*/ANN*                          -> no match -> low
    So style hints blocked releases while real findings did not.

DEFECT 3 — the bug that started it
    fleet_replay_panel._apply_stat_fields referenced `_ss_exc` inside
    `except Exception as _ap_exc`. A guaranteed NameError in an error
    handler. Ruff DOES emit F821 for it, but F -> "medium", so it
    shipped.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.harness.coding_archetype import (  # noqa: E402
    _RUFF_FAMILIES_BY_LEN,
    _RUFF_SEV_MAP,
    _module_binding_kinds,
    _possibly_unbound_severity,
)


def _write(tmp_path, body: str) -> str:
    p = tmp_path / "mod_under_test.py"
    p.write_text(body, encoding="utf-8")
    return str(p)


# ── DEFECT 1: binding-kind triage ────────────────────────────────

def test_import_bound_name_is_classified_as_import(tmp_path):
    """The Qt guard pattern: 2,456 of 2,465 real occurrences."""
    path = _write(tmp_path, "try:\n"
                            "    from PySide6.QtWidgets import QWidget\n"
                            "    _HAS_QT = True\n"
                            "except ImportError:\n"
                            "    _HAS_QT = False\n")
    imported, assigned = _module_binding_kinds(path)
    assert "QWidget" in imported
    assert "QWidget" not in assigned


def test_assignment_bound_name_is_classified_as_assignment(tmp_path):
    path = _write(tmp_path, "def f(flag):\n"
                            "    if flag:\n"
                            "        n = 1\n"
                            "    return n\n")
    imported, assigned = _module_binding_kinds(path)
    assert "n" in assigned
    assert "n" not in imported


def test_qt_guard_symbol_stays_low(tmp_path):
    """Must not block: this pattern is everywhere and is safe behind
    the `if _HAS_QT:` guard."""
    path = _write(tmp_path, "try:\n"
                            "    from PySide6.QtWidgets import QWidget\n"
                            "except ImportError:\n"
                            "    pass\n")
    assert _possibly_unbound_severity(
        '"QWidget" is possibly unbound', path) == "low"


def test_conditional_local_is_promoted_to_high(tmp_path):
    """This is the main.py:1107 shape. It MUST block."""
    path = _write(tmp_path, "def f(flag):\n"
                            "    if flag:\n"
                            "        count = 1\n"
                            "    return count\n")
    assert _possibly_unbound_severity(
        '"count" is possibly unbound', path) == "high"


def test_for_target_counts_as_assignment(tmp_path):
    """A loop variable read after an empty loop is the same defect."""
    path = _write(tmp_path, "def f(xs):\n"
                            "    for row in xs:\n"
                            "        pass\n"
                            "    return row\n")
    assert _possibly_unbound_severity(
        '"row" is possibly unbound', path) == "high"


def test_with_as_target_counts_as_assignment(tmp_path):
    path = _write(tmp_path, "def f(flag, cm):\n"
                            "    if flag:\n"
                            "        with cm as handle:\n"
                            "            pass\n"
                            "    return handle\n")
    assert _possibly_unbound_severity(
        '"handle" is possibly unbound', path) == "high"


def test_walrus_target_counts_as_assignment(tmp_path):
    path = _write(tmp_path, "def f(flag):\n"
                            "    if flag and (val := 1):\n"
                            "        pass\n"
                            "    return val\n")
    assert _possibly_unbound_severity(
        '"val" is possibly unbound', path) == "high"


def test_unparseable_module_never_blocks(tmp_path):
    """A promotion must never turn a parse failure into a blocked
    release — that would be worse than the bug it catches."""
    path = _write(tmp_path, "def f(:\n  syntax error\n")
    assert _possibly_unbound_severity('"x" is possibly unbound',
                                      path) == "low"


def test_missing_file_never_blocks():
    assert _possibly_unbound_severity(
        '"x" is possibly unbound', "no/such/file.py") == "low"


def test_unquoted_message_never_blocks(tmp_path):
    path = _write(tmp_path, "x = 1\n")
    assert _possibly_unbound_severity(
        "something is possibly unbound", path) == "low"


# ── DEFECT 2: ruff family longest-prefix ─────────────────────────

def _sev(code: str) -> str:
    for fam in _RUFF_FAMILIES_BY_LEN:
        if code.startswith(fam):
            return _RUFF_SEV_MAP[fam]
    return "low"


def test_families_are_ordered_longest_first():
    """The ordering IS the fix. Shortest-first would reintroduce the
    S/SIM collision silently."""
    lens = [len(f) for f in _RUFF_FAMILIES_BY_LEN]
    assert lens == sorted(lens, reverse=True)


def test_sim_does_not_collide_with_bandit_s():
    assert _sev("SIM114") == "low", "style hint must not block a release"
    assert _sev("SLF001") == "low"
    assert _sev("S603") == "high", "real security finding must block"


def test_multi_letter_families_are_reachable():
    """Under `fam = code[0]` every one of these silently fell through
    to 'low'."""
    assert _sev("RUF100") == "medium"
    assert _sev("ANN201") == "medium"
    assert _sev("BLE001") == "medium"
    assert _sev("PERF401") == "low"
    assert _sev("UP007") == "low"


def test_single_letter_families_still_work():
    assert _sev("F821") == "medium"
    assert _sev("E501") == "medium"
    assert _sev("W291") == "low"
    assert _sev("B008") == "medium"
    assert _sev("D100") == "low"


def test_unknown_code_defaults_to_low():
    assert _sev("ZZZ999") == "low"
    assert _sev("no-code") == "low"


# ── DEFECT 3 + the startup crash: source regressions ─────────────

def test_apply_stat_fields_does_not_reference_stale_exc_name():
    """v3.24.19 renamed the caught exception to `_ap_exc` but left a
    `_ss_exc` reference on the next line — a NameError inside an error
    handler, which the gate passed."""
    src = (REPO / "src" / "gui" / "simulator_tab" / "fleet"
           / "fleet_replay_panel.py").read_text(encoding="utf-8")
    body = src.split("def _apply_stat_fields", 1)
    assert len(body) == 2, "_apply_stat_fields not found"
    seg = body[1].split("\n        def ", 1)[0]
    assert "_ss_exc" not in seg, "stale exception name is back"


def test_autostart_count_is_bound_before_its_conditional():
    """main.py:1107 read a name only assigned inside
    `if state_mgr.has_saved_state():`. Fresh install -> the branch is
    skipped -> UnboundLocalError -> app dies before app.exec()."""
    src = (REPO / "main.py").read_text(encoding="utf-8")
    init = src.find("_autostart_bot_count = 0")
    guard = src.find("if state_mgr.has_saved_state():")
    use = src.find("if _autostart_bot_count > 0:", guard)
    assert init != -1, "unconditional initialiser is missing"
    assert init < guard, "initialiser must precede the guard"
    assert guard < use
