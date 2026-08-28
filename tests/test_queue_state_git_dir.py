"""Remote discovery must not depend on the shape of a checkout's ``.git``.

A linked worktree carries ``.git`` as a ``gitdir:`` pointer file. Composing
``.git/config`` under it names nothing, and the miss is silent: the answer is
an empty remote list, which reads as a repository that has no remote.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import queue_state

# Shaped after the repository's own config: tab-indented keys, one remote, and
# several ``[branch "..."]`` sections that a prefix test must not count.
CONFIG = "\n".join(
    [
        "[core]",
        "\trepositoryformatversion = 0",
        "\thooksPath = .githooks",
        '[remote "origin"]',
        "\turl = https://example.invalid/acervator.git",
        "\tfetch = +refs/heads/*:refs/remotes/origin/*",
        '[branch "current"]',
        "\tremote = origin",
        "\tmerge = refs/heads/current",
        '[branch "fix-queue-state-gitdir"]',
        "\tremote = origin",
        "",
    ]
)


def _clone(base: Path) -> Path:
    """A plain checkout: ``.git`` is a directory and the config sits in it."""
    root = base / "clone"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "config").write_text(CONFIG, encoding="utf-8")
    return root


def _linked_worktree(base: Path, *, relative: bool = False) -> Path:
    """A linked worktree: a pointer file, and the config in the common dir."""
    main = _clone(base)
    git_dir = main / ".git" / "worktrees" / "wt"
    git_dir.mkdir(parents=True)
    (git_dir / "commondir").write_text("../..\n", encoding="utf-8")
    root = base / "wt"
    root.mkdir()
    target = "../clone/.git/worktrees/wt" if relative else git_dir.as_posix()
    (root / ".git").write_text(f"gitdir: {target}\n", encoding="utf-8")
    return root


def _submodule(base: Path) -> Path:
    """A submodule: a pointer file, and the config in the directory it names."""
    root = base / "sub"
    root.mkdir(parents=True)
    git_dir = base / "modules" / "sub"
    git_dir.mkdir(parents=True)
    (git_dir / "config").write_text(CONFIG, encoding="utf-8")
    (root / ".git").write_text(f"gitdir: {git_dir.as_posix()}\n", encoding="utf-8")
    return root


@pytest.fixture()
def remotes_at(monkeypatch: pytest.MonkeyPatch):
    """Point the module's ROOT at a constructed tree and read its remotes."""

    def _read(root: Path) -> list[str]:
        monkeypatch.setattr(queue_state, "ROOT", root)
        return queue_state.git_remotes()

    return _read


def test_the_two_shapes_really_differ_on_disk(tmp_path: Path) -> None:
    """If both fixtures built a directory, the parity test would be vacuous."""
    assert (_clone(tmp_path / "a") / ".git").is_dir()
    assert (_linked_worktree(tmp_path / "b") / ".git").is_file()


def test_a_linked_worktree_reports_the_remotes_a_clone_reports(
    tmp_path: Path, remotes_at
) -> None:
    """If this fails, a measurement taken from a worktree undercounts remotes."""
    from_clone = remotes_at(_clone(tmp_path / "a"))
    from_worktree = remotes_at(_linked_worktree(tmp_path / "b"))
    assert from_clone == ["origin"]
    assert from_worktree == from_clone


def test_a_relative_gitdir_pointer_resolves(tmp_path: Path, remotes_at) -> None:
    """If this fails, a relative pointer is read as absolute and names nothing."""
    assert remotes_at(_linked_worktree(tmp_path, relative=True)) == ["origin"]


def test_a_pointer_without_a_commondir_reads_its_own_config(
    tmp_path: Path, remotes_at
) -> None:
    """If this fails, a submodule is redirected to a common dir it does not have."""
    assert remotes_at(_submodule(tmp_path)) == ["origin"]


def test_a_tree_that_is_not_a_checkout_reports_nothing(
    tmp_path: Path, remotes_at
) -> None:
    """The empty answer must stay reachable, or it cannot be told from a miss."""
    bare = tmp_path / "plain"
    bare.mkdir()
    assert remotes_at(bare) == []


def test_a_pointer_naming_a_git_dir_that_is_gone_reports_nothing(
    tmp_path: Path, remotes_at
) -> None:
    """A stale pointer must answer empty rather than raise."""
    root = tmp_path / "stale"
    root.mkdir()
    gone = (tmp_path / "gone").as_posix()
    (root / ".git").write_text(f"gitdir: {gone}\n", encoding="utf-8")
    assert remotes_at(root) == []
