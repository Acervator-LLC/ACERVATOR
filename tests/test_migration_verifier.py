"""`tools/migration_verifier.py` answers RED when its subject is wrong.

Why this file is built the way it is
------------------------------------
A verifier is the one kind of tool that can be completely broken and still
look perfect. Every check it makes returns GREEN on a healthy tree, and a
check hard-wired to return GREEN also returns GREEN on a healthy tree. The
two are indistinguishable from a passing run.

So nothing here asserts only that a check goes GREEN. Every check is driven
TWICE: once against the state it must accept, and once against the exact
state it exists to catch. `TestHooksPath` unsets `core.hooksPath`,
`TestRemotes` leaves one tree behind, `TestGateStamp` points the stamp at a
different commit and then deletes the commit, `TestIssues` removes an issue
and renames another, and `TestReferences` plants a citation to an issue
that does not exist. If any of those returned GREEN the check is
decoration, and the pair fails.

`TestRefusalWithoutABaseline` is the same discipline applied to the tool's
central claim. A verifier with no baseline can only check
self-consistency, so it must REFUSE. The test drives `verify` with no
capture file and requires a non-zero exit and a message that names the
capture command.

`TestTheToolIsReadOnly` is the other half. The tool's read-only property
is enforced in code -- `run_git`, `GhCliReader.run` and `assert_writable`
all raise before doing anything -- and each guard is driven here with the
call it must refuse. A guard nobody points a violation at is a comment.

Two layers, on purpose
----------------------
The `check_*` functions take plain dicts, so most tests build a payload
and read the verdict. That is exact and fast, and it makes the two-sided
pairs easy to write honestly.

`TestAgainstRealGitRepositories` then proves the MEASUREMENT layer reads
reality, by building real git repositories in `tmp_path` and running
`measure_tree` over them. Without it, every dict-level test could be
agreeing with a `measure_tree` that reads the wrong field.

No network
----------
Nothing here calls GitHub. `GhCliReader` takes an injectable runner and
the tests pass a recorder that returns fixture text, so the argv is
asserted without a process being spawned. `TestNoNetworkInTests` states
that as a contract rather than leaving it to convention.
"""

# ruff: noqa: S603
# S607 is fixed by construction: the git spawns below resolve through
# `shutil.which` and run by absolute path, following the reasoning in
# tests/test_tools_are_reachable.py. S603 is the residue, because every
# argv here carries a tmp_path, which is a variable by definition.

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path, PureWindowsPath
from typing import Any

import pytest

from tools import migration_verifier
from tools.migration_verifier import (
    GH_INSTALL_DIRS,
    GREEN,
    RED,
    SCHEMA,
    UNKNOWN,
    Completed,
    GhCliReader,
    GitHubUnavailable,
    JsonFileReader,
    ReadOnlyViolation,
    assert_writable,
    check_branch_protection,
    check_gate_stamp,
    check_hooks,
    check_issues,
    check_references,
    check_remotes,
    check_tracked,
    default_runner,
    gh_candidates,
    issue_citations,
    issue_numbers_in,
    load_baseline,
    main,
    measure_tree,
    probe_github,
    render,
    repo_slug,
    resolve_program,
    run_git,
    scan_issue_references,
    verify,
)

OLD_URL = "https://github.com/ekthelius/ACERVATOR.git"
NEW_URL = "https://github.com/acervator-org/ACERVATOR.git"


# --------------------------------------------------------------------------
# Builders. A payload is a dict, so a test can state exactly one difference.
# --------------------------------------------------------------------------


def tree(label: str, **over: object) -> dict[str, Any]:
    """One measured working tree, healthy unless a field is overridden."""
    base: dict[str, Any] = {
        "label": label,
        "path": f"/trees/{label}",
        "exists": True,
        "head": "a" * 40,
        "branch": "current",
        "origin_fetch": OLD_URL,
        "origin_push": OLD_URL,
        "hooks_path": ".githooks",
        "pre_push_present": True,
        "tracked_count": 757,
        "tracked_digest": "digest-757",
        "gate_stamp": {"present": True, "commit": "a" * 40, "version": "3.26.0"},
    }
    base.update(over)
    return base


def github(**over: object) -> dict[str, Any]:
    """Issue facts as `probe_github` returns them."""
    base: dict[str, Any] = {
        "available": True,
        "reason": "",
        "repo": "ekthelius/ACERVATOR",
        "issues": {"96": "the leak guard", "101": "the teardown", "104": "favours"},
        "states": {"96": "closed", "101": "closed", "104": "open"},
        "open": 1,
        "closed": 2,
        "protection": "unavailable-on-plan",
        "protection_detail": "403",
    }
    base.update(over)
    return base


def payload(**over: object) -> dict[str, Any]:
    """A whole capture file."""
    base: dict[str, Any] = {
        "schema": SCHEMA,
        "trees": [tree("primary"), tree("desktop")],
        "references": {
            "pattern": "x",
            "total": 4,
            "files_with_refs": 2,
            "by_suffix": {".py": 2},
            "counts": {"96": 2, "101": 1, "104": 1},
            "sites": {
                "96": ["tests/test_migration_verifier.py:10"],
                "101": ["tools/migration_verifier.py:3"],
                "104": ["tools/migration_verifier.py:9"],
            },
        },
        "commits": {"depth": 60, "examined": 60, "naming": 47, "numbers": ["96"]},
        "github": github(),
    }
    base.update(over)
    return base


def statuses(checks: list[Any]) -> dict[str, str]:
    """name -> status, so a test names the check it is about."""
    return {check.name: check.status for check in checks}


def detail_of(checks: list[Any], name: str) -> str:
    """The evidence line for one check."""
    return next(check.detail for check in checks if check.name == name)


# --------------------------------------------------------------------------
# The refusal. The tool's central claim.
# --------------------------------------------------------------------------


class TestRefusalWithoutABaseline:
    """No capture file means no answer, not a partial answer."""

    def test_verify_refuses_when_the_capture_file_is_absent(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        code = main(
            [
                "--no-github",
                "--primary",
                str(tmp_path),
                "verify",
                "--baseline",
                str(tmp_path / "nope.json"),
            ]
        )
        assert code == 2, "a missing baseline must REFUSE, not report"
        err = capsys.readouterr().err
        assert "REFUSED" in err
        assert "capture" in err, "the refusal must name the command that fixes it"

    def test_the_refusal_says_why_a_baseline_is_needed(
        self,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(FileNotFoundError) as caught:
            load_baseline(tmp_path / "missing.json")
        assert "self-consistency" in str(caught.value)

    def test_a_file_that_is_not_a_capture_is_refused(
        self,
        tmp_path: Path,
    ) -> None:
        wrong = tmp_path / "other.json"
        wrong.write_text(json.dumps({"schema": "something/else"}), encoding="utf-8")
        with pytest.raises(ValueError, match="not a"):
            load_baseline(wrong)

    def test_unreadable_json_is_refused_rather_than_treated_as_empty(
        self,
        tmp_path: Path,
    ) -> None:
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError, match="readable JSON"):
            load_baseline(broken)

    def test_a_real_capture_round_trips(self, tmp_path: Path) -> None:
        """The control. Refusal must not be the answer to everything."""
        good = tmp_path / "baseline.json"
        good.write_text(json.dumps(payload()), encoding="utf-8")
        assert load_baseline(good)["schema"] == SCHEMA


# --------------------------------------------------------------------------
# hooksPath. The highest-value check.
# --------------------------------------------------------------------------


class TestHooksPath:
    """Local config does not travel, and its absence is silent."""

    def test_green_when_set_and_the_hook_is_present(self) -> None:
        got = statuses(check_hooks(payload()))
        assert got["hooks_path_primary"] == GREEN
        assert got["hooks_path_desktop"] == GREEN

    def test_red_when_hooks_path_is_unset(self) -> None:
        broken = payload(trees=[tree("primary"), tree("desktop", hooks_path="")])
        checks = check_hooks(broken)
        assert statuses(checks)["hooks_path_desktop"] == RED
        assert statuses(checks)["hooks_path_primary"] == GREEN, "only one moved"

    def test_the_red_tells_the_operator_the_exact_repair(self) -> None:
        broken = payload(trees=[tree("primary", hooks_path=""), tree("desktop")])
        detail = detail_of(check_hooks(broken), "hooks_path_primary")
        assert "config core.hooksPath .githooks" in detail

    def test_red_when_hooks_path_is_set_but_the_hook_is_missing(self) -> None:
        """A path that points nowhere is as dead as no path at all."""
        broken = payload(
            trees=[
                tree("primary", pre_push_present=False),
                tree("desktop"),
            ]
        )
        assert statuses(check_hooks(broken))["hooks_path_primary"] == RED

    def test_unknown_when_the_tree_is_not_on_this_machine(self) -> None:
        absent = payload(
            trees=[
                tree("primary"),
                {"label": "desktop", "exists": False, "reason": "not here"},
            ]
        )
        assert statuses(check_hooks(absent))["hooks_path_desktop"] == UNKNOWN


# --------------------------------------------------------------------------
# Remotes. Two trees, and the stale one is the dangerous one.
# --------------------------------------------------------------------------


class TestRemotes:
    """He builds from the Desktop tree, so a stale remote there is worse."""

    def test_green_when_both_trees_moved_together(self) -> None:
        after = payload(
            trees=[
                tree("primary", origin_fetch=NEW_URL),
                tree("desktop", origin_fetch=NEW_URL),
            ]
        )
        got = statuses(check_remotes(payload(), after, ""))
        assert got["remote_primary"] == GREEN
        assert got["remote_desktop"] == GREEN
        assert got["remotes_agree_between_trees"] == GREEN

    def test_red_when_only_one_tree_was_repointed(self) -> None:
        """The failure the operator named: build from the wrong place."""
        after = payload(
            trees=[
                tree("primary", origin_fetch=NEW_URL),
                tree("desktop", origin_fetch=OLD_URL),
            ]
        )
        checks = check_remotes(payload(), after, "")
        got = statuses(checks)
        assert got["remote_primary"] == GREEN
        assert got["remote_desktop"] == RED
        assert got["remotes_agree_between_trees"] == RED
        assert "DIFFERENT" in detail_of(checks, "remotes_agree_between_trees")

    def test_red_when_neither_tree_moved(self) -> None:
        got = statuses(check_remotes(payload(), payload(), ""))
        assert got["remote_primary"] == RED
        assert got["remote_desktop"] == RED

    def test_two_trees_can_agree_and_both_still_be_wrong(self) -> None:
        """Agreement is necessary and not sufficient. Both checks matter."""
        got = statuses(check_remotes(payload(), payload(), ""))
        assert got["remotes_agree_between_trees"] == GREEN
        assert got["remote_primary"] == RED

    def test_expect_remote_greens_the_named_url(self) -> None:
        after = payload(
            trees=[
                tree("primary", origin_fetch=NEW_URL),
                tree("desktop", origin_fetch=NEW_URL),
            ]
        )
        got = statuses(check_remotes(payload(), after, NEW_URL))
        assert got["remote_primary"] == GREEN

    def test_expect_remote_reds_a_different_url(self) -> None:
        after = payload(
            trees=[
                tree("primary", origin_fetch=NEW_URL),
                tree("desktop", origin_fetch=NEW_URL),
            ]
        )
        got = statuses(check_remotes(payload(), after, "https://example/other.git"))
        assert got["remote_primary"] == RED

    def test_red_when_origin_has_no_url_at_all(self) -> None:
        after = payload(
            trees=[
                tree("primary", origin_fetch=""),
                tree("desktop", origin_fetch=NEW_URL),
            ]
        )
        assert statuses(check_remotes(payload(), after, ""))["remote_primary"] == RED


# --------------------------------------------------------------------------
# The gate stamp, and the history it binds to.
# --------------------------------------------------------------------------


class TestGateStamp:
    """The stamp names a SHA. A transfer keeps SHAs; a rewrite does not."""

    def test_green_when_the_stamp_binds_head(self) -> None:
        got = statuses(check_gate_stamp(payload(), payload()))
        assert got["gate_stamp_binds_head"] == GREEN

    def test_red_when_the_stamp_names_a_different_commit(self) -> None:
        after = payload(
            trees=[
                tree("primary", gate_stamp={"present": True, "commit": "b" * 40}),
                tree("desktop"),
            ]
        )
        checks = check_gate_stamp(payload(), after)
        assert statuses(checks)["gate_stamp_binds_head"] == RED
        assert "REFUSE" in detail_of(checks, "gate_stamp_binds_head")

    def test_red_when_there_is_no_stamp(self) -> None:
        after = payload(
            trees=[
                tree("primary", gate_stamp={"present": False, "reason": "gone"}),
                tree("desktop"),
            ]
        )
        assert statuses(check_gate_stamp(payload(), after))["gate_stamp_present"] == RED

    def test_green_when_head_never_moved(self) -> None:
        assert (
            statuses(check_gate_stamp(payload(), payload()))["history_preserved"]
            == GREEN
        )

    def test_green_when_head_advanced_and_the_old_commit_survives(self) -> None:
        """New commits are normal. A vanished commit is not."""
        after = payload(
            trees=[
                tree(
                    "primary",
                    head="c" * 40,
                    gate_stamp={"present": True, "commit": "c" * 40},
                ),
                tree("desktop"),
            ]
        )

        def found(argv: Sequence[str], cwd: Path | None) -> Completed:
            del argv, cwd
            return Completed(0, "", "")

        got = statuses(check_gate_stamp(payload(), after, found))
        assert got["history_preserved"] == GREEN

    def test_red_when_the_baseline_commit_is_gone(self) -> None:
        """A history rewrite. Every SHA citation is now wrong."""
        after = payload(
            trees=[
                tree(
                    "primary",
                    head="c" * 40,
                    gate_stamp={"present": True, "commit": "c" * 40},
                ),
                tree("desktop"),
            ]
        )

        def missing(argv: Sequence[str], cwd: Path | None) -> Completed:
            del argv, cwd
            return Completed(1, "", "no such object")

        checks = check_gate_stamp(payload(), after, missing)
        assert statuses(checks)["history_preserved"] == RED
        assert "rewritten" in detail_of(checks, "history_preserved")


# --------------------------------------------------------------------------
# Tracked files.
# --------------------------------------------------------------------------


class TestTrackedFiles:
    """A transfer moves bytes, not content."""

    def test_green_when_the_path_list_is_identical(self) -> None:
        assert check_tracked(payload(), payload()).status == GREEN

    def test_red_when_the_count_changed(self) -> None:
        after = payload(
            trees=[
                tree("primary", tracked_count=700, tracked_digest="other"),
                tree("desktop"),
            ]
        )
        check = check_tracked(payload(), after)
        assert check.status == RED
        assert "757" in check.detail and "700" in check.detail

    def test_unknown_when_the_tree_was_not_measured(self) -> None:
        after = payload(trees=[{"label": "primary", "exists": False}])
        assert check_tracked(payload(), after).status == UNKNOWN


# --------------------------------------------------------------------------
# Issues. The reason to Transfer rather than re-push.
# --------------------------------------------------------------------------


class TestIssues:
    """Numbers, titles and counts, each driven both ways."""

    def test_green_when_every_issue_survived(self) -> None:
        got = statuses(check_issues(payload(), payload()))
        assert got["issue_numbers_preserved"] == GREEN
        assert got["issue_titles_preserved"] == GREEN
        assert got["issue_open_closed_counts"] == GREEN

    def test_red_when_an_issue_is_missing(self) -> None:
        after = payload(
            github=github(
                issues={"96": "the leak guard", "104": "favours"},
                states={"96": "closed", "104": "open"},
                open=1,
                closed=1,
            )
        )
        checks = check_issues(payload(), after)
        assert statuses(checks)["issue_numbers_preserved"] == RED
        assert "#101" in detail_of(checks, "issue_numbers_preserved")

    def test_red_when_a_title_changed(self) -> None:
        after = payload(
            github=github(
                issues={
                    "96": "the leak guard",
                    "101": "RENAMED",
                    "104": "favours",
                }
            )
        )
        checks = check_issues(payload(), after)
        assert statuses(checks)["issue_titles_preserved"] == RED
        assert "#101" in detail_of(checks, "issue_titles_preserved")

    def test_red_when_the_open_closed_split_moved(self) -> None:
        after = payload(github=github(open=3, closed=0))
        assert (
            statuses(check_issues(payload(), after))["issue_open_closed_counts"] == RED
        )

    def test_unknown_when_the_baseline_never_captured_issues(self) -> None:
        """A baseline with no issue data cannot prove issues survived."""
        blind = payload(github={"available": False, "reason": "no gh"})
        checks = check_issues(blind, payload())
        assert statuses(checks)["issue_numbers_and_titles"] == UNKNOWN

    def test_unknown_is_not_green_when_the_reader_fails_after_the_move(
        self,
    ) -> None:
        after = payload(github={"available": False, "reason": "token expired"})
        got = statuses(check_issues(payload(), after))
        assert got["issue_numbers_and_titles"] == UNKNOWN


# --------------------------------------------------------------------------
# The citations in the tree.
# --------------------------------------------------------------------------


class TestReferences:
    """479 sentences cite issue numbers. Nothing links them."""

    def test_green_when_every_cited_number_is_still_cited(self) -> None:
        got = statuses(check_references(payload(), payload()))
        assert got["reference_set_preserved"] == GREEN

    def test_red_when_a_cited_number_disappeared_from_the_tree(self) -> None:
        thin = payload(
            references={
                "total": 2,
                "files_with_refs": 1,
                "by_suffix": {},
                "counts": {"96": 2},
                "sites": {"96": ["tests/test_migration_verifier.py:10"]},
            }
        )
        checks = check_references(payload(), thin)
        assert statuses(checks)["reference_set_preserved"] == RED
        assert "#101" in detail_of(checks, "reference_set_preserved")

    def test_green_when_every_citation_resolves(self) -> None:
        got = statuses(check_references(payload(), payload()))
        assert got["issue_numbers_still_resolve"] == GREEN

    def test_red_when_the_move_took_away_a_cited_issue(self) -> None:
        """The wrong-but-plausible failure class, caught by file and line.

        The tree still says "issue #101 ...". The move lost issue #101.
        The sentence now reads perfectly and points at nothing.
        """
        after = payload(
            github=github(
                issues={"96": "the leak guard", "104": "favours"},
                states={"96": "closed", "104": "open"},
                open=1,
                closed=1,
            )
        )
        after["references"]["sites"]["101"] = ["docs/TOUCHSET.md:42"]
        checks = check_references(payload(), after)
        assert statuses(checks)["issue_numbers_still_resolve"] == RED
        detail = detail_of(checks, "issue_numbers_still_resolve")
        assert "#101" in detail
        assert "docs/TOUCHSET.md:42" in detail, "name the exact sentence"

    def test_a_number_that_never_resolved_is_not_a_migration_failure(
        self,
    ) -> None:
        """The false-positive class this check must NOT have.

        `gh issue list` returns issues only, and pull requests share the
        same number sequence, so gaps are normal. `#26170` is a ccxt issue
        cited in market_pairs_scout.py. Neither is something the move
        broke, so neither may go RED.
        """
        after = payload(
            references={
                "total": 6,
                "files_with_refs": 3,
                "by_suffix": {},
                "counts": {"96": 2, "101": 1, "104": 1, "99": 1, "26170": 1},
                "sites": {"26170": ["src/exchange/market_pairs_scout.py:88"]},
            }
        )
        checks = check_references(payload(), after)
        assert statuses(checks)["issue_numbers_still_resolve"] == GREEN
        assert "not a migration failure" in detail_of(
            checks,
            "issue_numbers_still_resolve",
        )

    def test_unknown_when_there_is_no_issue_data_to_resolve_against(
        self,
    ) -> None:
        blind = payload(github={"available": False, "reason": "no gh"})
        got = statuses(check_references(payload(), blind))
        assert got["issue_numbers_still_resolve"] == UNKNOWN


# --------------------------------------------------------------------------
# The citation pattern itself. The instrument needs a control.
# --------------------------------------------------------------------------


class TestTheCitationPatternIsCalibrated:
    """A wide pattern would report false REDs forever.

    Measured on the real tree: a bare `#(\\d+)` scored 2040 hits, of which
    `#2` alone was 140 and `#0` was 96, because CSS hex colours and
    ordinals dominate. Both halves are asserted here -- what must match,
    and what must not.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "issue #96 measured that the guard held",
            "Issue #96 measured it",
            "issues #96 and #97",
            "#102's harness caught it",
            "fix(#101): the teardown actually destroys",
            "https://github.com/ekthelius/ACERVATOR/issues/104",
            "repaired under\n    issue #68",
        ],
    )
    def test_real_citation_forms_are_found(self, text: str) -> None:
        assert issue_numbers_in(text), f"missed a real citation in {text!r}"

    @pytest.mark.parametrize(
        "text",
        [
            "Captions: #2d0000  |  Table body: #1a0000",
            'DARK = HexColor("#0C0C18")',
            "dark #0d0d14 background, #00ff88 buys",
            "Queue item #2 instrumented src/gui/history_tab.py",
            "Adapter for old kwarg in restore path (Open Q #7)",
            "tranche #0 credited $0.03927376",
            "colour #888 and #555 and #333",
        ],
    )
    def test_colours_and_ordinals_are_not_citations(self, text: str) -> None:
        assert not issue_numbers_in(text), f"false citation in {text!r}"

    def test_a_wrapped_citation_reports_the_line_it_starts_on(self) -> None:
        found = issue_citations("alpha\nbeta\nrepaired under\nissue #68 here")
        assert found == [("68", 4)]

    def test_the_scan_finds_a_planted_citation_and_its_site(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "a.py").write_text(
            '"""Under issue #96 the guard held."""\n',
            encoding="utf-8",
        )
        (tmp_path / "b.md").write_text("no citations here\n", encoding="utf-8")
        got = scan_issue_references(tmp_path, ["a.py", "b.md"])
        assert got["counts"] == {"96": 1}
        assert got["sites"]["96"] == ["a.py:1"]
        assert got["files_with_refs"] == 1, "b.md holds none and must not count"

    def test_a_binary_file_is_skipped_rather_than_decoded(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "blob.bin").write_bytes(b"issue #96\x00\x01\x02")
        assert scan_issue_references(tmp_path, ["blob.bin"])["total"] == 0


# --------------------------------------------------------------------------
# Branch protection. Informational, and never a RED.
# --------------------------------------------------------------------------


class TestBranchProtection:
    """403 on the personal plan. An organization may change that."""

    def test_green_when_protection_is_actually_enforced(self) -> None:
        after = payload(github=github(protection="enforced"))
        assert check_branch_protection(payload(), after).status == GREEN

    def test_unavailable_is_unknown_and_never_red(self) -> None:
        """It is a possibility to re-probe, not a requirement to satisfy."""
        check = check_branch_protection(payload(), payload())
        assert check.status == UNKNOWN
        assert check.status != RED

    def test_the_unknown_says_the_local_hook_is_still_the_only_guard(
        self,
    ) -> None:
        assert "pre-push" in check_branch_protection(payload(), payload()).detail


# --------------------------------------------------------------------------
# Read-only. Enforced in code, so driven with the calls it must refuse.
# --------------------------------------------------------------------------


class TestTheToolIsReadOnly:
    """It reports; the operator acts."""

    @pytest.mark.parametrize(
        "args",
        [
            ["push", "origin", "current"],
            ["commit", "-m", "no"],
            ["reset", "--hard"],
            ["checkout", "main"],
            ["fetch"],
            ["clean", "-fd"],
            [],
        ],
    )
    def test_run_git_refuses_a_mutating_subcommand(
        self,
        args: list[str],
        tmp_path: Path,
    ) -> None:
        with pytest.raises(ReadOnlyViolation):
            run_git(args, tmp_path, _never_spawn)

    @pytest.mark.parametrize(
        "args",
        [
            ["config", "core.hooksPath", ".githooks"],
            ["config", "--unset", "core.hooksPath"],
            ["config", "--add", "remote.origin.url", NEW_URL],
            ["remote", "set-url", "origin", NEW_URL],
            ["remote", "add", "org", NEW_URL],
            ["remote", "remove", "origin"],
        ],
    )
    def test_run_git_refuses_a_writing_argument_form(
        self,
        args: list[str],
        tmp_path: Path,
    ) -> None:
        """`git config` and `git remote` both read AND write. Flags decide."""
        with pytest.raises(ReadOnlyViolation):
            run_git(args, tmp_path, _never_spawn)

    @pytest.mark.parametrize(
        "args",
        [
            ["config", "--get", "core.hooksPath"],
            ["remote", "get-url", "origin"],
            ["rev-parse", "HEAD"],
            ["ls-files"],
            ["log", "-5", "--format=%s"],
            ["cat-file", "-e", "abc^{commit}"],
        ],
    )
    def test_run_git_allows_the_reads_the_tool_needs(
        self,
        args: list[str],
        tmp_path: Path,
    ) -> None:
        """The control. A guard that refuses everything guards nothing."""
        assert run_git(args, tmp_path, _ok_spawn).code == 0

    @pytest.mark.parametrize(
        "args",
        [
            ["issue", "create", "--title", "no"],
            ["issue", "close", "101"],
            ["pr", "merge", "12"],
            ["repo", "rename", "other"],
            ["api", "--method", "POST", "repos/x/y/issues"],
            ["api", "-X", "DELETE", "repos/x/y"],
            ["api", "repos/x/y/issues", "-f", "title=no"],
            [],
        ],
    )
    def test_the_github_reader_refuses_every_mutation(
        self,
        args: list[str],
    ) -> None:
        with pytest.raises(ReadOnlyViolation):
            GhCliReader(_never_spawn).run(args)

    def test_the_github_reader_allows_a_get(self) -> None:
        """The control for the refusals above."""
        reader = GhCliReader(_ok_spawn)
        assert reader.run(["api", "--method", "GET", "repos/x/y"]) == "[]"

    @pytest.mark.parametrize(
        "leaf",
        [
            ".acervator/coinbase_credentials.json",
            ".acervator/bot_state.json",
            ".acervator_logs/trade/gate.log",
            ".acervator",
        ],
    )
    def test_it_refuses_to_write_into_the_runtime_directories(
        self,
        leaf: str,
        tmp_path: Path,
    ) -> None:
        """Credentials live there. This tool has no business in either."""
        with pytest.raises(ReadOnlyViolation):
            assert_writable(tmp_path / leaf, tmp_path)

    def test_it_writes_anywhere_else(self, tmp_path: Path) -> None:
        """The control."""
        assert_writable(tmp_path / "docs" / "baseline.json", tmp_path)

    def test_capture_exits_refused_when_pointed_at_the_runtime_directory(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        target = Path.home() / ".acervator" / "baseline.json"
        code = main(
            [
                "--no-github",
                "--primary",
                str(tmp_path),
                "capture",
                "--out",
                str(target),
            ]
        )
        assert code == 2
        assert "REFUSED" in capsys.readouterr().err
        assert not target.exists(), "it must refuse BEFORE writing"


def _never_spawn(argv: Sequence[str], cwd: Path | None) -> Completed:
    """A runner that fails the test if anything reaches it."""
    del cwd
    msg = f"the guard let {argv!r} through to a subprocess"
    raise AssertionError(msg)


def _ok_spawn(argv: Sequence[str], cwd: Path | None) -> Completed:
    """A runner that records nothing and succeeds."""
    del argv, cwd
    return Completed(0, "[]", "")


# --------------------------------------------------------------------------
# The GitHub seam.
# --------------------------------------------------------------------------


class FakeReader:
    """A GitHubReader built from fixtures. No network, ever."""

    def __init__(
        self,
        rows: list[dict[str, Any]],
        protection: tuple[str, str],
    ) -> None:
        self.rows = rows
        self.protection = protection

    def issues(self, repo: str) -> list[dict[str, Any]]:
        del repo
        return self.rows

    def branch_protection(self, repo: str, branch: str) -> tuple[str, str]:
        del repo, branch
        return self.protection


class TestNoNetworkInTests:
    """The seam is the point. Nothing here opens a socket."""

    def test_probe_github_reads_the_injected_reader(self) -> None:
        got = probe_github(
            FakeReader(
                [
                    {"number": 96, "title": "guard", "state": "CLOSED"},
                    {"number": 104, "title": "favours", "state": "OPEN"},
                ],
                ("unavailable-on-plan", "403"),
            ),
            "org/repo",
            "main",
        )
        assert got["available"] is True
        assert got["issues"] == {"96": "guard", "104": "favours"}
        assert (got["open"], got["closed"]) == (1, 1)

    def test_probe_github_records_the_reason_when_it_cannot_read(self) -> None:
        """UNKNOWN carries its cause. A bare zero is a claim about nothing."""

        class Broken:
            def issues(self, repo: str) -> list[dict[str, Any]]:
                del repo
                msg = "gh is not installed"
                raise GitHubUnavailable(msg)

            def branch_protection(
                self,
                repo: str,
                branch: str,
            ) -> tuple[str, str]:
                del repo, branch
                return (UNKNOWN.lower(), "")

        got = probe_github(Broken(), "org/repo", "main")
        assert got["available"] is False
        assert "gh is not installed" in got["reason"]

    def test_no_reader_at_all_is_unavailable_not_empty(self) -> None:
        got = probe_github(None, "org/repo", "main")
        assert got["available"] is False

    def test_the_gh_reader_asks_for_all_issues_and_never_spawns_here(
        self,
    ) -> None:
        seen: list[list[str]] = []

        def recorder(argv: Sequence[str], cwd: Path | None) -> Completed:
            del cwd
            seen.append(list(argv))
            return Completed(0, '[{"number":1,"title":"t","state":"OPEN"}]', "")

        rows = GhCliReader(recorder).issues("org/repo")
        assert rows == [{"number": 1, "title": "t", "state": "OPEN"}]
        assert seen[0][0] == "gh", "the argv is asserted, not executed"
        assert "--state" in seen[0] and "all" in seen[0]

    def test_a_missing_gh_raises_unavailable_rather_than_returning_empty(
        self,
    ) -> None:
        def absent(argv: Sequence[str], cwd: Path | None) -> Completed:
            del argv, cwd
            return Completed(127, "", "gh: not found")

        with pytest.raises(GitHubUnavailable, match="not found on PATH"):
            GhCliReader(absent).issues("org/repo")

    def test_the_json_reader_reads_an_export_instead(
        self,
        tmp_path: Path,
    ) -> None:
        export = tmp_path / "issues.json"
        export.write_text(
            json.dumps([{"number": 96, "title": "guard", "state": "CLOSED"}]),
            encoding="utf-8",
        )
        assert JsonFileReader(export).issues("x")[0]["number"] == 96

    def test_the_json_reader_refuses_a_file_that_is_not_a_list(
        self,
        tmp_path: Path,
    ) -> None:
        export = tmp_path / "issues.json"
        export.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        with pytest.raises(GitHubUnavailable):
            JsonFileReader(export).issues("x")


# --------------------------------------------------------------------------
# The measurement layer, against real git repositories.
# --------------------------------------------------------------------------


def _git(tmp: Path, *args: str) -> None:
    """Build a fixture repository. Test setup, not tool code."""
    exe = shutil.which("git")
    assert exe is not None, "git is required to build the fixture"
    done = subprocess.run(
        [exe, "-C", str(tmp), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, f"git {args}: {done.stderr}"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real repository with a hook directory and a gate stamp."""
    root = tmp_path / "tree"
    root.mkdir()
    _git(root, "init", "-q", "-b", "current")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "Fixture")
    hooks = root / ".githooks"
    hooks.mkdir()
    (hooks / "pre-push").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (root / "note.py").write_text(
        '"""Under issue #96 the guard held."""\n',
        encoding="utf-8",
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed(#96): the fixture")
    _git(root, "remote", "add", "origin", OLD_URL)
    return root


class TestAgainstRealGitRepositories:
    """Proof that the measurement reads reality, not a convenient field."""

    def test_it_reports_hooks_path_unset_on_a_fresh_repository(
        self,
        repo: Path,
    ) -> None:
        """This is the migration failure, reproduced. A clone has it unset."""
        got = measure_tree("primary", repo)
        assert got["hooks_path"] == ""
        assert statuses(check_hooks({"trees": [got]}))["hooks_path_primary"] == RED

    def test_it_reports_hooks_path_once_the_repository_sets_it(
        self,
        repo: Path,
    ) -> None:
        """The control. The same tree, one config line later, goes GREEN."""
        _git(repo, "config", "core.hooksPath", ".githooks")
        got = measure_tree("primary", repo)
        assert got["hooks_path"] == ".githooks"
        assert got["pre_push_present"] is True
        assert statuses(check_hooks({"trees": [got]}))["hooks_path_primary"] == GREEN

    def test_it_reads_the_real_origin_and_head(self, repo: Path) -> None:
        got = measure_tree("primary", repo)
        assert got["origin_fetch"] == OLD_URL
        assert len(got["head"]) == 40
        assert got["branch"] == "current"
        assert got["tracked_count"] == 2

    def test_a_slot_with_no_tree_named_reports_absent(self) -> None:
        """`--desktop` is optional, and an unnamed slot measures nothing."""
        got = measure_tree("desktop", None)
        assert got["exists"] is False
        assert got["path"] == ""
        assert "no tree was named" in got["reason"]
        assert "head" not in got

    def test_the_unnamed_slot_does_not_read_the_current_directory(
        self,
        repo: Path,
    ) -> None:
        """The control for the test above.

        `Path("")` is `Path(".")`, so an empty argument measured the primary
        tree a second time and the two-tree comparison agreed with itself.
        """
        named = measure_tree("desktop", repo)
        assert named["exists"] is True
        assert len(named["head"]) == 40
        assert measure_tree("desktop", None)["exists"] is False

    def test_it_reads_a_real_gate_stamp_and_binds_it_to_head(
        self,
        repo: Path,
    ) -> None:
        head = measure_tree("primary", repo)["head"]
        (repo / ".gate_stamp.json").write_text(
            json.dumps({"commit": head, "version": "3.26.0"}),
            encoding="utf-8",
        )
        got = measure_tree("primary", repo)
        before = {"trees": [dict(got)]}
        assert (
            statuses(check_gate_stamp(before, {"trees": [got]}))[
                "gate_stamp_binds_head"
            ]
            == GREEN
        )

    def test_a_stamp_naming_another_commit_goes_red_on_a_real_tree(
        self,
        repo: Path,
    ) -> None:
        (repo / ".gate_stamp.json").write_text(
            json.dumps({"commit": "b" * 40}),
            encoding="utf-8",
        )
        got = measure_tree("primary", repo)
        assert (
            statuses(check_gate_stamp({"trees": [got]}, {"trees": [got]}))[
                "gate_stamp_binds_head"
            ]
            == RED
        )

    def test_a_missing_stamp_is_reported_as_missing(self, repo: Path) -> None:
        assert measure_tree("primary", repo)["gate_stamp"]["present"] is False

    def test_a_directory_that_is_not_a_repository_is_not_invented(
        self,
        tmp_path: Path,
    ) -> None:
        got = measure_tree("desktop", tmp_path / "nowhere")
        assert got["exists"] is False
        assert "not a git working tree" in got["reason"]

    def test_commit_subjects_are_scanned_for_issue_numbers(
        self,
        repo: Path,
    ) -> None:
        from tools.migration_verifier import scan_commit_references

        got = scan_commit_references(repo, 10)
        assert got["examined"] == 1
        assert got["naming"] == 1
        assert got["numbers"] == ["96"]

    def test_capture_then_verify_is_green_when_nothing_moved(
        self,
        repo: Path,
    ) -> None:
        """End to end, on a real tree, with the seam closed."""
        from tools.migration_verifier import capture

        head = measure_tree("primary", repo)["head"]
        (repo / ".gate_stamp.json").write_text(
            json.dumps({"commit": head}),
            encoding="utf-8",
        )
        _git(repo, "config", "core.hooksPath", ".githooks")
        reader = FakeReader(
            [{"number": 96, "title": "guard", "state": "CLOSED"}],
            ("enforced", "{}"),
        )
        before = capture(repo, repo, reader, "current", 10)
        after = capture(repo, repo, reader, "current", 10)
        checks = verify(before, after, expect_remote=OLD_URL)
        reds = [c.name for c in checks if c.status == RED]
        assert reds == [], f"an unmoved tree must be clean, got {reds}"

    def test_the_same_pair_goes_red_when_the_remote_moves_underneath(
        self,
        repo: Path,
    ) -> None:
        """The control for the test above."""
        from tools.migration_verifier import capture

        reader = FakeReader(
            [{"number": 96, "title": "guard", "state": "CLOSED"}],
            ("absent", ""),
        )
        before = capture(repo, repo, reader, "current", 10)
        _git(repo, "remote", "set-url", "origin", NEW_URL)
        after = capture(repo, repo, reader, "current", 10)
        got = statuses(verify(before, after, expect_remote=OLD_URL))
        assert got["remote_primary"] == RED


# --------------------------------------------------------------------------
# Reporting and the command line.
# --------------------------------------------------------------------------


class TestTheReportDoesNotReassure:
    """UNKNOWN must never read as a pass."""

    def test_all_green_says_green(self) -> None:
        """Everything measurable and everything intact."""
        whole = payload(github=github(protection="enforced"))
        text = render(verify(whole, whole, expect_remote=OLD_URL))
        assert "RESULT: GREEN" in text

    def test_any_red_says_red(self) -> None:
        whole = payload(github=github(protection="enforced"))
        after = payload(
            trees=[tree("primary", hooks_path=""), tree("desktop")],
            github=github(protection="enforced"),
        )
        assert "RESULT: RED" in render(verify(whole, after, OLD_URL))

    def test_unknown_without_red_is_still_not_green(self) -> None:
        """The whole point. A check that did not run did not pass."""
        blind = payload(github={"available": False, "reason": "no gh"})
        text = render(verify(blind, blind, expect_remote=OLD_URL))
        assert "RESULT: NOT GREEN" in text
        assert "did not run" in text
        assert "RESULT: GREEN" not in text

    def test_every_rendered_line_carries_its_evidence(self) -> None:
        """A verdict alone cannot be checked by the reader."""
        for check in verify(payload(), payload(), OLD_URL):
            assert check.detail.strip(), f"{check.name} reported no evidence"

    def test_exit_codes_separate_green_red_and_unknown(
        self,
        tmp_path: Path,
        repo: Path,
    ) -> None:
        baseline = tmp_path / "baseline.json"
        assert (
            main(
                [
                    "--no-github",
                    "--primary",
                    str(repo),
                    "--desktop",
                    str(repo),
                    "capture",
                    "--out",
                    str(baseline),
                ]
            )
            == 3
        ), "a capture with no issue data must not exit 0"
        assert (
            main(
                [
                    "--no-github",
                    "--primary",
                    str(repo),
                    "--desktop",
                    str(repo),
                    "verify",
                    "--baseline",
                    str(baseline),
                ]
            )
            == 1
        ), "hooksPath is unset on the fixture, so this is RED"

    def test_help_works_as_a_program(self) -> None:
        """`tests/test_tools_are_reachable.py` requires this; assert it here."""
        done = subprocess.run(
            [sys.executable, "-m", "tools.migration_verifier", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0
        assert "capture" in done.stdout and "verify" in done.stdout

    @pytest.mark.parametrize(
        ("url", "want"),
        [
            ("https://github.com/ekthelius/ACERVATOR.git", "ekthelius/ACERVATOR"),
            ("https://github.com/acervator-org/ACERVATOR", "acervator-org/ACERVATOR"),
            ("git@github.com:ekthelius/ACERVATOR.git", "ekthelius/ACERVATOR"),
            ("https://gitlab.com/x/y.git", ""),
            ("", ""),
        ],
    )
    def test_the_repo_slug_is_read_from_the_remote(
        self,
        url: str,
        want: str,
    ) -> None:
        assert repo_slug(url) == want


# --------------------------------------------------------------------------
# Issue #108. Two reasons `capture` skipped the issue data, and the issue
# data is what the tool itself calls the most important thing the migration
# must preserve. Each one is driven BOTH ways: the state it must now
# accept, and the state it must still refuse.
# --------------------------------------------------------------------------


class TestGhIsFoundWhenItIsInstalledButOffPath:
    r"""Installed-but-off-PATH is the machine the operator actually has.

    Measured 2026-08-24: `shutil.which("gh")` returns None in Git Bash
    and in PowerShell, and `C:\Program Files\GitHub CLI\gh.exe` runs. The
    old reader asked PATH only and reported `gh is not installed`, which
    is FALSE and sends the operator to reinstall what he has.
    """

    def test_path_answers_first(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The control. An operator who chose a `gh` keeps that one."""
        chosen = tmp_path / "chosen" / "gh.exe"
        chosen.parent.mkdir(parents=True)
        chosen.write_text("", encoding="utf-8")
        monkeypatch.setattr(
            migration_verifier.shutil,
            "which",
            lambda _name: str(chosen),
        )
        assert resolve_program("gh", {"ProgramFiles": "C:/nowhere"}) == str(
            chosen,
        )

    @pytest.mark.parametrize(
        ("variable", "tail"),
        [
            ("ProgramFiles", "GitHub CLI"),
            ("ProgramW6432", "GitHub CLI"),
            ("ProgramFiles(x86)", "GitHub CLI"),
            ("LOCALAPPDATA", "Microsoft/WinGet/Links"),
            ("ProgramData", "chocolatey/bin"),
            ("USERPROFILE", "scoop/shims"),
        ],
    )
    def test_an_installed_gh_that_is_off_path_is_found(
        self,
        variable: str,
        tail: str,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """PATH says no; the standard install directory says yes."""
        planted = tmp_path / tail / "gh.exe"
        planted.parent.mkdir(parents=True)
        planted.write_text("", encoding="utf-8")
        monkeypatch.setattr(
            migration_verifier.shutil,
            "which",
            lambda _name: None,
        )
        got = resolve_program("gh", {variable: str(tmp_path)})
        assert got == str(planted), "an installed gh must not read as absent"

    def test_only_gh_gets_a_fallback(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`git` is on PATH on any machine that cloned this repository."""
        monkeypatch.setattr(
            migration_verifier.shutil,
            "which",
            lambda _name: None,
        )
        assert resolve_program("git") is None

    def test_a_gh_that_is_genuinely_absent_still_reads_as_absent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The other half. Widening discovery must not invent a `gh`.

        Driven over the rows a fixture can redirect. The three absolute
        POSIX rows are constants, so a host carrying a real
        `/usr/bin/gh` cannot be handed an empty one, and the `posix`
        seam is what keeps the claim the same on every host.
        """
        monkeypatch.setattr(
            migration_verifier.shutil,
            "which",
            lambda _name: None,
        )
        env = {variable: str(tmp_path) for variable, _ in GH_INSTALL_DIRS if variable}
        redirected = gh_candidates(env, posix=False)
        assert redirected, "the fixture redirected no candidate"
        present = [path for path in redirected if path.is_file()]
        assert present == [], f"the fixture is not clean: {present}"
        monkeypatch.setattr(
            migration_verifier,
            "gh_candidates",
            lambda mapping=None, **_kw: gh_candidates(mapping, posix=False),
        )
        assert resolve_program("gh", env) is None

    def test_the_candidate_list_is_fixed_and_never_read_from_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A wider search must not become a caller-chosen search."""
        monkeypatch.setenv("PATH", "C:/planted")
        names = {path.name for path in gh_candidates({"ProgramFiles": "C:/x"})}
        assert names == {"gh.exe", "gh"}
        assert not any(
            "planted" in str(path) for path in gh_candidates({"ProgramFiles": "C:/x"})
        )

    def test_every_candidate_is_an_absolute_path(self) -> None:
        r"""A drive-relative probe depends on where the operator stood.

        `Path("/usr/bin/gh")` on Windows is NOT absolute. It probes
        `C:\usr\bin\gh` from a C: working directory. Both halves
        are driven, because the POSIX rows must still be searched on
        POSIX.
        """
        assert gh_candidates({}, posix=False) == ()
        windows = gh_candidates(
            {"ProgramFiles": "C:/Program Files"},
            posix=False,
        )
        assert windows, "a set ProgramFiles must give candidates"
        for path in windows:
            assert PureWindowsPath(
                path
            ).is_absolute(), f"{path} is not absolute on Windows"

        on_posix = gh_candidates({}, posix=True)
        assert on_posix, "the POSIX rows must be searched on POSIX"
        assert all(path.as_posix().startswith("/") for path in on_posix)

    def test_the_absent_message_says_where_it_looked(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`gh is not installed` was the false half. It must be gone.

        The absent state is driven through `gh_candidates`, because a
        host with a real `gh` in a standard POSIX directory cannot be
        emptied by moving an environment variable.
        """
        monkeypatch.setattr(
            migration_verifier.shutil,
            "which",
            lambda _name: None,
        )
        for variable, _ in GH_INSTALL_DIRS:
            if variable:
                monkeypatch.setenv(variable, str(tmp_path))
        monkeypatch.setattr(
            migration_verifier,
            "gh_candidates",
            lambda mapping=None, **_kw: (),
        )
        done = default_runner(["gh", "--version"], None)
        assert done.code == 127
        assert "PATH" in done.err
        assert "standard install" in done.err
        assert "is not installed" not in done.err

    def test_the_reader_refuses_honestly_when_gh_is_nowhere(self) -> None:
        """UNKNOWN with a true reason, never an empty issue list."""

        def absent(argv: Sequence[str], cwd: Path | None) -> Completed:
            del argv, cwd
            return Completed(127, "", "gh was not found")

        with pytest.raises(GitHubUnavailable) as caught:
            GhCliReader(absent).issues("org/repo")
        text = str(caught.value)
        assert "not found on PATH" in text
        assert "standard install" in text
        assert "--issues-json" in text, "the refusal must name the way out"

    def test_capture_reports_not_captured_and_exits_three(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The refusal design stays intact. Exit 3 is not a pass."""
        out = tmp_path / "baseline.json"
        code = main(
            [
                "--no-github",
                "--primary",
                str(tmp_path),
                "capture",
                "--out",
                str(out),
            ]
        )
        assert code == 3
        assert "issues NOT CAPTURED" in capsys.readouterr().out


class TestWideningDiscoveryDoesNotWidenWhatIsAllowed:
    """The read-only guarantee is load-bearing. It is unchanged."""

    @pytest.mark.parametrize(
        "args",
        [
            ["issue", "create", "--title", "no"],
            ["issue", "close", "108"],
            ["repo", "delete", "x/y"],
            ["api", "--method", "POST", "repos/x/y/issues"],
            ["api", "repos/x/y/issues", "-f", "title=no"],
        ],
    )
    def test_a_mutation_is_refused_before_discovery_ever_runs(
        self,
        args: list[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`run` validates first, so the resolved path is never reached."""

        def never(name: str, env: object = None) -> str:
            del env
            msg = f"discovery ran for a refused command: {name}"
            raise AssertionError(msg)

        monkeypatch.setattr(migration_verifier, "resolve_program", never)
        with pytest.raises(ReadOnlyViolation):
            GhCliReader(migration_verifier.default_runner).run(args)

    def test_a_get_still_reaches_the_runner(self) -> None:
        """The control. A guard that refuses everything guards nothing."""
        seen: list[list[str]] = []

        def recorder(argv: Sequence[str], cwd: Path | None) -> Completed:
            del cwd
            seen.append(list(argv))
            return Completed(0, "[]", "")

        assert (
            GhCliReader(recorder).run(
                ["api", "--method", "GET", "repos/x/y"],
            )
            == "[]"
        )
        assert seen == [["gh", "api", "--method", "GET", "repos/x/y"]]

    def test_run_git_still_refuses_a_write(self, tmp_path: Path) -> None:
        """`git remote set-url` writes. It must still never spawn."""
        with pytest.raises(ReadOnlyViolation):
            run_git(["remote", "set-url", "origin", NEW_URL], tmp_path, _never_spawn)

    def test_assert_writable_still_refuses_the_runtime_directory(
        self,
        tmp_path: Path,
    ) -> None:
        """Credentials live there. The tool has no business in it."""
        with pytest.raises(ReadOnlyViolation):
            assert_writable(
                tmp_path / ".acervator" / "coinbase_credentials.json",
                tmp_path,
            )


class TestTheIssueExportIsReadWithOrWithoutABom:
    """`Out-File -Encoding utf8` on PowerShell 5.1 writes a BOM."""

    def test_the_fixture_really_carries_a_bom(self, tmp_path: Path) -> None:
        """The positive control for the two tests below.

        Without this, a passing BOM test could be passing on a file that
        never held a BOM.
        """
        export = _write_export(tmp_path / "bom.json", bom=True)
        assert export.read_bytes()[:3] == b"\xef\xbb\xbf"
        with pytest.raises(json.JSONDecodeError, match="BOM"):
            json.loads(export.read_text(encoding="utf-8"))

    def test_a_bom_export_is_read(self, tmp_path: Path) -> None:
        """The file the tool's own documented command produces."""
        export = _write_export(tmp_path / "bom.json", bom=True)
        rows = JsonFileReader(export).issues("x")
        assert [row["number"] for row in rows] == [96, 108]

    def test_a_no_bom_export_is_read(self, tmp_path: Path) -> None:
        """The other half. `utf-8-sig` must not require a BOM."""
        export = _write_export(tmp_path / "plain.json", bom=False)
        assert export.read_bytes()[:1] == b"["
        rows = JsonFileReader(export).issues("x")
        assert [row["number"] for row in rows] == [96, 108]

    def test_a_broken_export_is_still_refused(self, tmp_path: Path) -> None:
        """Reading a BOM must not turn into reading anything."""
        broken = tmp_path / "broken.json"
        broken.write_bytes(b"\xef\xbb\xbf{not json")
        with pytest.raises(GitHubUnavailable, match="cannot read"):
            JsonFileReader(broken).issues("x")

    @pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-8"])
    def test_capture_exits_zero_with_either_export(
        self,
        encoding: str,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """End to end, the exit code the operator reads."""
        export = _write_export(
            tmp_path / "issues.json",
            bom=encoding == "utf-8-sig",
        )
        out = tmp_path / "baseline.json"
        code = main(
            [
                "--issues-json",
                str(export),
                "--primary",
                str(tmp_path),
                "capture",
                "--out",
                str(out),
            ]
        )
        assert code == 0, "the documented export must be accepted"
        assert "issues 1 open, 1 closed" in capsys.readouterr().out


def _write_export(path: Path, *, bom: bool) -> Path:
    """Write the export `gh issue list --json ...` makes, either encoding."""
    rows = [
        {"number": 96, "title": "guard", "state": "CLOSED"},
        {"number": 108, "title": "capture skips issue data", "state": "OPEN"},
    ]
    body = json.dumps(rows)
    path.write_bytes(
        (b"\xef\xbb\xbf" if bom else b"") + body.encode("utf-8"),
    )
    return path
