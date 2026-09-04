"""Pin the two parts of `tools/local_ci.py` that decide a verdict on their own.

The lanes themselves are black, flake8 and pytest; running them here would
prove nothing about this module and would be the whole-suite run the tool
exists to schedule. What is worth pinning is everything that happens WITHOUT a
lane running: which lanes get selected from a diff, and how a return code is
read once one has.

Every path used as test data is a real path in this repository, so the
hallucination rule stays a live instrument over this file.

Each negative assertion carries the positive control beside it, so a green
here cannot mean the check went blind.
"""

from __future__ import annotations

import subprocess

import pytest

from tools import local_ci

A_DOC = "docs/desktop_shell.md"
A_DOC_ARTEFACT = "docs/engineering-notes/2026-08-22_item_10_4_evidence/callers.json"
A_SOURCE_FILE = "src/trading/scrumming_bot.py"


# --------------------------------------------------------------------------- #
# Lane selection: mirroring ci.yml's `changes` job                             #
# --------------------------------------------------------------------------- #


def test_a_docs_only_change_skips_the_code_lanes() -> None:
    changes = local_ci.classify_changes([A_DOC, "CHANGELOG.md"])
    assert changes.run_code_lanes is False, (
        "both files are in ci.yml's IGNORE set, so the code lanes must be "
        f"skipped; got reason {changes.reason!r}"
    )


def test_one_source_file_beside_the_docs_runs_the_code_lanes() -> None:
    """The positive control for the skip above: the same input plus one .py."""
    changes = local_ci.classify_changes([A_DOC, "CHANGELOG.md", A_SOURCE_FILE])
    assert (
        changes.run_code_lanes is True
    ), f"one functional file is enough to run the lanes; got {changes.reason!r}"
    assert changes.functional == (A_SOURCE_FILE,)


@pytest.mark.parametrize(
    "path",
    [
        ".claude/rules/tests.md",
        A_DOC,
        A_DOC_ARTEFACT,
        "CHANGELOG.md",
        "LICENSE",
        ".gitignore",
        ".gitattributes",
    ],
)
def test_the_ignore_set_from_ci_yml_is_non_functional(path: str) -> None:
    assert (
        local_ci.functional_files([path]) == []
    ), f"{path} matches ci.yml's IGNORE pattern and must not count as functional"


@pytest.mark.parametrize(
    "path",
    [
        A_SOURCE_FILE,
        "tests/conftest.py",
        "tools/local_ci.py",
        "main.py",
        ".github/workflows/ci.yml",
        "pyproject.toml",
        "dev_harness/harness/docs_archetype.py",
    ],
)
def test_paths_outside_the_ignore_set_are_functional(path: str) -> None:
    """The control for the skip list above: these must all get through.

    `dev_harness/harness/docs_archetype.py` is the one the anchor decides:
    `^docs/` is anchored at the start, so a path merely containing the word is
    still functional.
    """
    assert local_ci.functional_files([path]) == [
        path
    ], f"{path} does not match ci.yml's IGNORE pattern and must run the lanes"


def test_an_unmeasurable_diff_runs_every_lane() -> None:
    changes = local_ci.classify_changes(None, unmeasured="no base ref resolved")
    assert changes.run_code_lanes is True, (
        "ci.yml falls back to running everything when it has no comparable "
        "history; an unread diff must never be read as a skip"
    )
    assert "no base ref resolved" in changes.reason


def test_an_empty_diff_needs_no_lane() -> None:
    changes = local_ci.classify_changes([])
    assert changes.run_code_lanes is False
    assert changes.paths == ()


def test_a_rename_counts_both_of_its_paths() -> None:
    paths = local_ci.status_paths(f"R  {A_DOC} -> src/core/log_paths.py\n M main.py\n")
    assert paths == [A_DOC, "src/core/log_paths.py", "main.py"], (
        "a rename out of docs/ into src/ is a functional change and both ends "
        f"must be seen; got {paths}"
    )


def test_an_untracked_file_is_seen() -> None:
    assert local_ci.status_paths(f"?? {A_SOURCE_FILE}") == [A_SOURCE_FILE]


def test_a_clean_tree_reports_no_paths() -> None:
    assert local_ci.status_paths("") == []


# --------------------------------------------------------------------------- #
# Exit-code interpretation                                                     #
# --------------------------------------------------------------------------- #


def test_zero_is_the_only_passing_code() -> None:
    assert local_ci.interpret_exit(0).passed is True
    assert local_ci.interpret_exit(0).code == 0


@pytest.mark.parametrize("returncode", [1, 2, 3, 4, 5, 7, 127, 139, 143, -11, -15])
def test_no_non_zero_code_is_ever_read_as_a_pass(returncode: int) -> None:
    verdict = local_ci.interpret_exit(returncode, is_pytest=True)
    assert (
        verdict.passed is False
    ), f"return code {returncode} must be a failure; got {verdict!r}"


def test_139_is_reported_as_sigsegv_by_name() -> None:
    verdict = local_ci.interpret_exit(139)
    assert verdict.code == 139
    assert verdict.passed is False
    assert "SIGSEGV" in verdict.detail, (
        "139 must name SIGSEGV so a crash is not read as an empty run; "
        f"got {verdict.detail!r}"
    )
    assert "summary" in verdict.detail


def test_a_negative_signal_normalizes_to_the_code_a_shell_reports() -> None:
    """subprocess gives -11 for the crash a shell calls 139. One event, two views."""
    from_python = local_ci.interpret_exit(-11)
    from_shell = local_ci.interpret_exit(139)
    assert from_python.code == 139, (
        "subprocess reports a POSIX signal as a negative number; -11 must "
        f"normalize to 128 + 11; got {from_python.code}"
    )
    assert from_python.detail == from_shell.detail


def test_143_is_reported_as_sigterm_by_name() -> None:
    verdict = local_ci.interpret_exit(143)
    assert verdict.code == 143
    assert verdict.passed is False
    assert "SIGTERM" in verdict.detail


def test_a_negative_sigterm_normalizes_to_143() -> None:
    assert local_ci.interpret_exit(-15).code == 143


def test_a_timeout_is_a_failure_reported_as_143() -> None:
    verdict = local_ci.interpret_exit(0, timed_out=True)
    assert verdict.passed is False, (
        "a lane that was killed never answered; the zero handed to the timeout "
        "path must not become a pass"
    )
    assert verdict.code == 143
    assert "timed out" in verdict.detail


def test_a_windows_crash_code_is_named_not_left_as_a_bare_number() -> None:
    """On this machine a segfault is 0xC0000005, never 139."""
    for code in (3221225477, -1073741819):
        verdict = local_ci.interpret_exit(code)
        assert verdict.passed is False
        assert (
            "access violation" in verdict.detail
        ), f"{code} is a crash and must say so; got {verdict.detail!r}"


def test_a_pytest_lane_names_what_kind_of_red_it_is() -> None:
    assert "no tests collected" in local_ci.interpret_exit(5, is_pytest=True).detail
    assert "tests failed" in local_ci.interpret_exit(1, is_pytest=True).detail


def test_a_lint_lane_does_not_borrow_pytest_exit_code_meanings() -> None:
    """The control for the test above: 5 means nothing to black."""
    verdict = local_ci.interpret_exit(5, is_pytest=False)
    assert verdict.passed is False
    assert "no tests collected" not in verdict.detail


# --------------------------------------------------------------------------- #
# Lane commands                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("lane", ["fast", "full"])
def test_a_pytest_lane_caps_xdist_at_four_workers(lane: str) -> None:
    argv = local_ci.lane_command(lane)
    assert "auto" not in argv, (
        "`-n auto` would take all 24 cores on the machine running the live "
        f"application; got {argv}"
    )
    assert argv[argv.index("-n") + 1] == "4"


def _marker_expression(argv: list[str]) -> str:
    """The `-m` value pytest receives, not the `-m pytest` that launched it."""
    after_pytest = argv[argv.index("pytest") + 1 :]
    return after_pytest[after_pytest.index("-m") + 1]


def test_the_two_pytest_lanes_split_the_suite_the_way_ci_yml_does() -> None:
    fast = _marker_expression(local_ci.lane_command("fast"))
    full = _marker_expression(local_ci.lane_command("full"))
    assert fast == "not slow and not archetype"
    assert full == "slow or archetype"
    assert fast != full, "the two lanes must not select the same tests"


def test_the_lint_lanes_expand_the_glob_ci_yml_hands_to_a_shell() -> None:
    argv = local_ci.lane_command("black")
    assert "*.py" not in argv, (
        "there is no shell in a subprocess argv; an unexpanded glob reaches "
        f"black as a filename that does not exist. got {argv}"
    )
    targets = local_ci.lint_targets()
    assert argv[-len(targets) :] == targets
    for expected in ("src", "tests", "tools", "main.py"):
        assert expected in argv


def test_black_checks_and_never_rewrites() -> None:
    argv = local_ci.lane_command("black")
    assert "--check" in argv and "--diff" in argv


def test_an_unknown_lane_is_refused_rather_than_silently_skipped() -> None:
    with pytest.raises(ValueError, match="unknown lane"):
        local_ci.lane_command("typecheck")


# --------------------------------------------------------------------------- #
# The verdict main() returns                                                   #
# --------------------------------------------------------------------------- #


def _stub_lanes(
    monkeypatch: pytest.MonkeyPatch, code_by_lane: dict[str, int]
) -> list[str]:
    """Replace `run_lane` with a recorder; return the list of lanes it saw."""
    ran: list[str] = []

    def fake_run_lane(name: str, _timeout: int | None) -> local_ci.LaneResult:
        ran.append(name)
        return local_ci.LaneResult(
            name, local_ci.interpret_exit(code_by_lane.get(name, 0)), 0.0
        )

    monkeypatch.setattr(local_ci, "run_lane", fake_run_lane)
    return ran


def _stub_changes(monkeypatch: pytest.MonkeyPatch, changes: local_ci.ChangeSet) -> None:
    monkeypatch.setattr(local_ci, "read_changes", lambda _base: changes)


ALL_FUNCTIONAL = local_ci.ChangeSet(("main.py",), ("main.py",), True, "test input")
DOCS_ONLY = local_ci.ChangeSet((A_DOC,), (), False, "test input")


def test_one_lane_flag_runs_that_lane_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_changes(monkeypatch, ALL_FUNCTIONAL)
    ran = _stub_lanes(monkeypatch, {})
    assert local_ci.main(["--lane", "fast"]) == 0
    assert ran == ["fast"], f"--lane fast must run only the fast lane; ran {ran}"


def test_no_lane_flag_runs_every_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control for the test above: without the flag, all four run."""
    _stub_changes(monkeypatch, ALL_FUNCTIONAL)
    ran = _stub_lanes(monkeypatch, {})
    assert local_ci.main([]) == 0
    assert ran == list(local_ci.LANE_ORDER)


def test_repeated_lane_flags_run_in_ci_order(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_changes(monkeypatch, ALL_FUNCTIONAL)
    ran = _stub_lanes(monkeypatch, {})
    assert local_ci.main(["--lane", "fast", "--lane", "black"]) == 0
    assert ran == ["black", "fast"]


def test_a_docs_only_change_runs_nothing_and_still_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_changes(monkeypatch, DOCS_ONLY)
    ran = _stub_lanes(monkeypatch, {})
    assert local_ci.main([]) == 0
    assert ran == [], f"a docs-only change must run no lane; ran {ran}"


def test_the_all_flag_overrides_the_docs_only_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control for the skip above: the same input with --all runs them."""
    _stub_changes(monkeypatch, DOCS_ONLY)
    ran = _stub_lanes(monkeypatch, {})
    assert local_ci.main(["--all"]) == 0
    assert ran == list(local_ci.LANE_ORDER)


def test_one_failing_lane_fails_the_whole_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_changes(monkeypatch, ALL_FUNCTIONAL)
    _stub_lanes(monkeypatch, {"flake8": 1})
    assert local_ci.main([]) == 1


def test_a_crashed_lane_fails_the_whole_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """A SIGSEGV prints no failure summary, so only the code can catch it."""
    _stub_changes(monkeypatch, ALL_FUNCTIONAL)
    _stub_lanes(monkeypatch, {"fast": -11})
    assert local_ci.main([]) == 1, (
        "a lane killed by SIGSEGV produces no failure output; reading the "
        "return code is the only thing that can fail the run"
    )


def test_the_verdict_line_names_the_failing_lane(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub_changes(monkeypatch, ALL_FUNCTIONAL)
    _stub_lanes(monkeypatch, {"full": 139})
    local_ci.main([])
    out = capsys.readouterr().out
    assert "VERDICT: FAILED" in out and "full" in out
    assert "SIGSEGV" in out, f"the crash code must reach the report; got:\n{out}"


def test_a_timing_out_lane_is_reported_as_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(local_ci.subprocess, "run", explode)
    result = local_ci.run_lane("black", 1)
    assert result.verdict.passed is False
    assert result.verdict.code == 143


def test_a_lane_that_exits_zero_is_reported_as_a_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control for the timeout test: the same path with a clean exit."""

    def clean(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(local_ci.subprocess, "run", clean)
    assert local_ci.run_lane("black", 1).verdict.passed is True


# --------------------------------------------------------------------------- #
# The git reader                                                               #
# --------------------------------------------------------------------------- #

_GIT_CLEAN_TREE = {
    "rev-parse": (0, "abc123"),
    "merge-base": (0, "abc123"),
    "diff": (0, A_DOC),
    "status": (0, ""),
}


def test_a_clean_tree_is_not_mistaken_for_git_being_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty output with a zero code is a clean tree, not a failed measurement.

    If those two were confused, every clean tree would take the
    unmeasurable-diff branch and the skip decision would never fire.
    """
    monkeypatch.setattr(local_ci, "run_git", lambda *args: _GIT_CLEAN_TREE[args[0]])
    changes = local_ci.read_changes(None)
    assert changes.paths == (A_DOC,)
    assert changes.run_code_lanes is False


def test_a_failed_git_status_runs_every_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: the same flow with git failing must NOT reach a skip."""
    broken = dict(_GIT_CLEAN_TREE, status=(127, ""))
    monkeypatch.setattr(local_ci, "run_git", lambda *args: broken[args[0]])
    changes = local_ci.read_changes(None)
    assert changes.run_code_lanes is True
    assert "git status failed" in changes.reason


def test_no_base_ref_runs_every_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_ci, "run_git", lambda *args: (1, ""))
    changes = local_ci.read_changes(None)
    assert changes.run_code_lanes is True
    assert "no base ref resolved" in changes.reason
