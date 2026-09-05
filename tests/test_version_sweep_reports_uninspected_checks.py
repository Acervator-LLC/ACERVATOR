"""``VersionSweep.run`` must not mark a check passed when it inspected nothing.

``check_r6_two_paths`` and ``check_sadp_dependency_graph`` call ``_no_subject``
when the paths they compare are absent, and ``run`` then records them in
``SweepResult.not_inspected``.
``test_no_tick_is_printed_for_a_check_that_read_nothing`` reads the ``SYNTAX``
line as its control for the ``TICK``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.version_sweep import Finding, Severity, SweepResult, VersionSweep

TICK = "✓"

R6 = "R6 two-path (R6)"
DEP_GRAPH = "SADP dep graph"
SYNTAX = "Syntax"

GATE_TEXT = (
    'GATES = "macd_taper vip_at_ceiling _vip_ceil ichi_twist_bull '
    '_ichi_ squeeze_bull SLINGSHOT"\n'
)
NO_GATE_TEXT = 'GATES = ""\n'


def _write(path: Path, text: str) -> None:
    """Create the parents of ``path`` and write ``text`` as UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Return a tree that parses cleanly and holds no ``sadp`` directory."""
    root = tmp_path / "repo"
    _write(root / "src" / "core" / "thing.py", "VALUE = 1\n")
    return root


def _line(output: str, name: str) -> str:
    """Return the ``run`` progress line that names ``name``."""
    for line in output.splitlines():
        if f"Checking: {name}..." in line:
            return line
    raise AssertionError(f"{name!r} never appeared in the sweep output:\n{output}")


def _of_category(result: SweepResult, category: str) -> list[Finding]:
    """Return the ``result`` findings carrying ``category``."""
    return [f for f in result.findings if f.category == category]


def test_no_tick_is_printed_for_a_check_that_read_nothing(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``run`` withholds the tick from ``R6`` and ``DEP_GRAPH`` on this tree.

    The ``SYNTAX`` line is the control for reading a tick at all.
    """
    VersionSweep(root=tree).run()
    out = capsys.readouterr().out

    assert TICK in _line(
        out, SYNTAX
    ), f"the tick reader is blind; {SYNTAX} line was {_line(out, SYNTAX)!r}"
    ticked = [name for name in (R6, DEP_GRAPH) if TICK in _line(out, name)]
    assert ticked == [], f"these checks read nothing and still ticked: {ticked}\n{out}"


def test_an_absent_two_path_subject_is_reported_as_not_inspected(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``check_r6_two_paths`` has no subject when neither compared path exists."""
    result = VersionSweep(root=tree).run()
    line = _line(capsys.readouterr().out, R6)

    assert R6 in result.not_inspected, (
        f"{R6} inspected nothing and was not recorded; "
        f"not_inspected={result.not_inspected}"
    )
    assert TICK not in line, f"{R6} printed the pass tick: {line!r}"
    assert (
        "absent" in result.not_inspected[R6]
    ), f"{R6} must name the missing path; got {result.not_inspected[R6]!r}"


def test_an_absent_rule_registry_is_reported_as_not_inspected(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``check_sadp_dependency_graph`` has no subject without a registry file."""
    result = VersionSweep(root=tree).run()
    line = _line(capsys.readouterr().out, DEP_GRAPH)

    assert DEP_GRAPH in result.not_inspected, (
        f"{DEP_GRAPH} inspected nothing and was not recorded; "
        f"not_inspected={result.not_inspected}"
    )
    assert TICK not in line, f"{DEP_GRAPH} printed the pass tick: {line!r}"
    assert "RULE_REGISTRY.json" in result.not_inspected[DEP_GRAPH], (
        f"{DEP_GRAPH} must name the missing registry; "
        f"got {result.not_inspected[DEP_GRAPH]!r}"
    )


def test_a_clean_check_still_reports_a_pass(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``check_syntax`` reads a real file, so ``run`` keeps its tick."""
    result = VersionSweep(root=tree).run()
    line = _line(capsys.readouterr().out, SYNTAX)

    assert TICK in line, f"{SYNTAX} lost its pass tick: {line!r}"
    assert SYNTAX not in result.not_inspected, (
        f"{SYNTAX} parsed the tree fixture and must not be recorded; "
        f"not_inspected={result.not_inspected}"
    )


def test_a_present_two_path_subject_is_inspected_and_passes(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``check_r6_two_paths`` compares both files when both are on disk."""
    _write(tree / "src" / "gui" / "simulator.py", GATE_TEXT)
    _write(tree / "sadp" / "RAIntSimBat" / "RAIntSimBat.py", GATE_TEXT)

    result = VersionSweep(root=tree).run()
    line = _line(capsys.readouterr().out, R6)

    assert (
        R6 not in result.not_inspected
    ), f"both paths exist, so {R6} ran; not_inspected={result.not_inspected}"
    assert TICK in line, f"{R6} inspected a matching pair and must tick: {line!r}"


def test_a_present_two_path_subject_still_scores_a_mismatch(tree: Path) -> None:
    """``check_r6_two_paths`` scores a gate only ``simulator.py`` names."""
    _write(tree / "src" / "gui" / "simulator.py", GATE_TEXT)
    _write(tree / "sadp" / "RAIntSimBat" / "RAIntSimBat.py", NO_GATE_TEXT)

    result = VersionSweep(root=tree).run()
    violations = [f for f in result.findings if "R6 VIOLATION" in f.description]

    assert R6 not in result.not_inspected
    assert (
        len(violations) == 4
    ), f"all four gate_pairs entries are unmatched; got {violations}"


def test_a_present_registry_scores_a_suspended_dependency(tree: Path) -> None:
    """``check_sadp_dependency_graph`` reads a registry that is on disk."""
    _write(
        tree / "sadp" / "RULE_REGISTRY.json",
        json.dumps(
            {
                "R1": {"state": "SUSPENDED", "depends_on": []},
                "R5": {"state": "LOCKED", "depends_on": ["R1"]},
            }
        ),
    )

    result = VersionSweep(root=tree).run()

    assert DEP_GRAPH not in result.not_inspected, (
        f"the registry exists, so {DEP_GRAPH} ran; "
        f"not_inspected={result.not_inspected}"
    )
    assert (
        len(_of_category(result, "SADP-DEP")) == 1
    ), f"R5 depends on suspended R1; got {_of_category(result, 'SADP-DEP')}"


def test_an_unreadable_registry_is_reported_as_not_inspected(tree: Path) -> None:
    """``check_sadp_dependency_graph`` cannot read a registry that is not JSON."""
    _write(tree / "sadp" / "RULE_REGISTRY.json", "{ not json")

    result = VersionSweep(root=tree).run()

    assert "unreadable" in result.not_inspected.get(DEP_GRAPH, ""), (
        f"a registry that will not parse was scored clean; "
        f"not_inspected={result.not_inspected}"
    )
    assert _of_category(result, "SADP-DEP") == []


def test_the_json_report_carries_the_not_inspected_checks(tree: Path) -> None:
    """``save_json_report`` writes ``not_inspected`` beside ``passed``."""
    sweep = VersionSweep(root=tree)
    result = sweep.run()
    out = sweep.save_json_report(result, reports_dir=tree.parent / "reports")

    data = json.loads(out.read_text(encoding="utf-8"))
    assert (
        R6 in data["not_inspected"]
    ), f"the JSON report hides the uninspected checks: {data['not_inspected']}"
    assert DEP_GRAPH in data["not_inspected"]


def test_an_exec_call_is_scored_in_every_file(tree: Path) -> None:
    """``check_insecure_patterns`` scores ``exec`` wherever the file sits."""
    _write(tree / "RAIntSimBat.py", "exec('1')\n")

    sweep = VersionSweep(root=tree)
    sweep.check_insecure_patterns()

    scored = [f for f in sweep.result.findings if "exec()" in f.description]
    assert scored, f"exec() went unscored; findings={sweep.result.findings}"
    assert all(
        f.severity != Severity.INFO for f in scored
    ), f"exec() was downgraded to INFO: {scored}"
