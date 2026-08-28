"""``src._version`` must derive the version from git, and bake it for a bundle.

WHAT A FAILURE MEANS
====================
``test_a_clean_version_tag_reports_a_bare_release`` red: a tagged release
no longer reports its own number.

``test_a_backup_tag_never_becomes_the_version`` red: the ``--match`` guard
is gone and a local backup tag such as ``pre-rejoin-backup`` is being
reported as the application version.

``test_a_dirty_tree_never_reports_a_clean_release`` and
``test_only_an_exact_clean_tag_reports_a_release_number`` red: a build can
claim to be a release it is not. That is the failure the whole module
exists to prevent.

``test_a_baked_tree_keeps_its_version_after_git_is_removed`` red: a frozen
bundle, which carries no repository, has stopped reporting the version the
build resolved for it.

``test_src_init_holds_no_version_literal`` red: a hand-maintained literal
is back in the package.

TWO-SIDED
=========
``test_the_unguarded_form_would_adopt_a_backup_tag`` drives the same
repository without ``--match`` and requires the backup tag to appear. A
guard that matched nothing would look identical to a guard that worked.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

import src
from src._version import (
    BAKED_FILENAME,
    DIRTY_SUFFIX,
    TAG_GLOB,
    UNKNOWN_VERSION,
    baked_path,
    describe,
    format_describe,
    project_root,
    read_baked_version,
    resolve_version,
)
from tools.gate import describe_tags
from tools.migration_verifier import default_runner
from tools.spec_common import BAKE_SUBDIR, bake_version_datas, read_acervator_version

REPO = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> str:
    """Run one git command in ``root`` and refuse to continue if it failed.

    Spawning is delegated to the migration verifier's absolute-path runner,
    so no test spawns a process of its own.
    """
    done = default_runner(["git", "-C", str(root), *args], None)
    assert done.code == 0, f"git {' '.join(args)} -> {done.code}: {done.err.strip()}"
    return done.out.strip()


def _repo(root: Path) -> Path:
    """Initialise a throwaway repository with a local identity."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "current")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "Fixture")
    _git(root, "config", "commit.gpgsign", "false")
    assert (root / ".git").is_dir(), "git init produced no .git"
    return root


def _commit(root: Path, text: str) -> str:
    """Commit ``text`` as the tracked file and return the short commit id."""
    (root / "tracked.txt").write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", text)
    return _git(root, "rev-parse", "--short", "HEAD")


def _rmtree(root: Path) -> None:
    """Delete a directory tree, clearing the read-only bits git leaves.

    ``.git`` holds read-only object files, which a plain rmtree refuses on
    Windows.
    """
    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(stat.S_IWRITE)
        if path.is_file():
            path.unlink()
        else:
            path.rmdir()
    root.rmdir()


def _dirty(root: Path) -> None:
    """Modify the tracked file, and prove git now calls the tree dirty."""
    (root / "tracked.txt").write_text("modified", encoding="utf-8")
    assert _git(root, "status", "--porcelain", "--untracked-files=no")


@pytest.fixture
def tagged(tmp_path: Path) -> Path:
    """A repository sitting exactly on the version tag ``v0.4.2``."""
    root = _repo(tmp_path / "tagged")
    _commit(root, "one")
    _git(root, "tag", "v0.4.2")
    return root


def test_a_clean_version_tag_reports_a_bare_release(tagged: Path) -> None:
    """A tagged, unmodified tree must report the release number alone."""
    assert resolve_version(tagged) == "0.4.2"


def test_a_modified_version_tag_reports_dirty(tagged: Path) -> None:
    """Editing a tracked file must change what the tree reports."""
    _dirty(tagged)
    assert resolve_version(tagged) == "0.4.2+dirty"


def test_a_dirty_tree_never_reports_a_clean_release(tagged: Path) -> None:
    """A modified tree must never answer a bare release number."""
    _dirty(tagged)
    version = resolve_version(tagged)
    assert "+" in version, version
    assert version != "0.4.2"


def test_commits_past_a_tag_carry_distance_and_commit(tagged: Path) -> None:
    """Four commits past v0.4.2 must report the distance and the commit."""
    short = ""
    for index in range(4):
        short = _commit(tagged, f"past-{index}")
    assert resolve_version(tagged) == f"0.4.2+dev.4.g{short}"


def test_no_version_tag_reachable_reports_the_untagged_base(tmp_path: Path) -> None:
    """A repository with no version tag must report 0.1.0 plus the commit."""
    root = _repo(tmp_path / "untagged")
    short = _commit(root, "one")
    assert resolve_version(root) == f"0.1.0+dev.g{short}"


def test_a_backup_tag_never_becomes_the_version(tmp_path: Path) -> None:
    """A local backup tag must not be adopted as the application version."""
    root = _repo(tmp_path / "backup-tagged")
    _commit(root, "one")
    _git(root, "tag", "pre-rejoin-backup")
    short = _commit(root, "two")

    version = resolve_version(root)
    assert version == f"0.1.0+dev.g{short}"
    assert "pre-rejoin-backup" not in version


def test_the_unguarded_form_would_adopt_a_backup_tag(tmp_path: Path) -> None:
    """Positive control: without ``--match`` the backup tag does get picked."""
    root = _repo(tmp_path / "backup-tagged")
    _commit(root, "one")
    _git(root, "tag", "pre-rejoin-backup")
    _commit(root, "two")

    assert "pre-rejoin-backup" in describe_tags(root, "*", DIRTY_SUFFIX)


def test_describe_asks_git_only_for_version_tags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tag glob handed to git must stay the version-tag glob."""
    seen: list[tuple[str, str]] = []

    def _record(root: object, match: str, dirty_suffix: str) -> str:
        seen.append((match, dirty_suffix))
        return ""

    root = _repo(tmp_path / "probe")
    _commit(root, "one")
    monkeypatch.setattr("tools.gate.describe_tags", _record)

    describe(root)

    assert seen == [(TAG_GLOB, DIRTY_SUFFIX)]
    assert TAG_GLOB == "v[0-9]*"


def test_a_directory_with_no_git_and_nothing_baked_is_unknown(tmp_path: Path) -> None:
    """A tree that can answer nothing must say so, not guess a release."""
    assert resolve_version(tmp_path) == UNKNOWN_VERSION
    assert "+" in UNKNOWN_VERSION


def test_a_bundle_without_git_reports_the_baked_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A frozen tree with no repository must report what the build baked in."""
    baked_path(tmp_path).parent.mkdir(parents=True)
    baked_path(tmp_path).write_text("0.4.2\n", encoding="utf-8")
    assert not (tmp_path / ".git").exists()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert resolve_version(tmp_path) == "0.4.2"


def test_a_source_tree_reaches_a_baked_file_when_git_cannot_answer(
    tmp_path: Path,
) -> None:
    """Unfrozen, with no repository, the baked file is still the answer."""
    baked_path(tmp_path).parent.mkdir(parents=True)
    baked_path(tmp_path).write_text("0.4.2\n", encoding="utf-8")

    assert resolve_version(tmp_path) == "0.4.2"


def test_a_frozen_bundle_prefers_the_baked_value_over_a_repository(
    tagged: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Frozen answers from the bake; the same tree unfrozen answers from git."""
    baked_path(tagged).parent.mkdir(parents=True)
    baked_path(tagged).write_text("9.9.9\n", encoding="utf-8")

    assert resolve_version(tagged) == "0.4.2"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert resolve_version(tagged) == "9.9.9"


def test_a_baked_tree_keeps_its_version_after_git_is_removed(
    tagged: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bundle case: bake from git, delete .git, still report the version.

    This is what a PyInstaller bundle is -- the whole ``src`` tree with no
    repository beside it.
    """
    resolved = resolve_version(tagged)
    assert resolved == "0.4.2"

    pairs = bake_version_datas(str(tagged))
    source, destination = pairs[0]
    assert destination == "src"

    baked_path(tagged).parent.mkdir(parents=True, exist_ok=True)
    baked_path(tagged).write_text(
        Path(source).read_text(encoding="utf-8"), encoding="utf-8"
    )

    _rmtree(tagged / ".git")
    assert not (tagged / ".git").exists()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert resolve_version(tagged) == resolved


def test_bake_writes_the_resolved_version_beside_the_package(tmp_path: Path) -> None:
    """The build artefact must carry exactly what the resolver answered."""
    pairs = bake_version_datas(str(tmp_path))

    assert len(pairs) == 1
    source, destination = pairs[0]
    assert destination == "src"
    assert Path(source).name == BAKED_FILENAME
    assert Path(source).parent == tmp_path / BAKE_SUBDIR
    assert Path(source).read_text(encoding="utf-8").strip() == read_acervator_version(
        str(tmp_path)
    )


def test_bake_writes_nothing_into_the_package_directory(tmp_path: Path) -> None:
    """The bake must not create a file under src/ in the source tree."""
    bake_version_datas(str(tmp_path))
    assert not baked_path(tmp_path).exists()


def test_read_baked_version_strips_the_trailing_newline(tmp_path: Path) -> None:
    """A stray newline must not become part of the version string."""
    baked_path(tmp_path).parent.mkdir(parents=True)
    baked_path(tmp_path).write_text("0.4.2\n", encoding="utf-8")

    assert read_baked_version(tmp_path) == "0.4.2"


@pytest.mark.parametrize(
    ("described", "expected"),
    [
        ("v0.4.2-0-g5e336c8", "0.4.2"),
        ("v0.4.2-0-g5e336c8.dirty", "0.4.2+dirty"),
        ("v0.4.2-4-g5e336c8", "0.4.2+dev.4.g5e336c8"),
        ("v0.4.2-4-g5e336c8.dirty", "0.4.2+dev.4.g5e336c8.dirty"),
        ("5e336c8", "0.1.0+dev.g5e336c8"),
        ("5e336c8.dirty", "0.1.0+dev.g5e336c8.dirty"),
    ],
)
def test_every_describe_shape_maps_to_its_version(
    described: str, expected: str
) -> None:
    """Each shape git can produce must map to the documented version."""
    assert format_describe(described) == expected


@pytest.mark.parametrize(
    "described",
    [
        "v0.4.2-0-g5e336c8.dirty",
        "v0.4.2-4-g5e336c8",
        "v0.4.2-4-g5e336c8.dirty",
        "5e336c8",
        "5e336c8.dirty",
    ],
)
def test_only_an_exact_clean_tag_reports_a_release_number(described: str) -> None:
    """Anything that is not a clean tagged commit must carry a local segment."""
    assert "+" in format_describe(described)


def test_an_exact_clean_tag_is_the_one_shape_with_no_local_segment() -> None:
    """The control for the rule above: the release shape must have no ``+``."""
    assert "+" not in format_describe("v0.4.2-0-g5e336c8")


def test_the_package_version_is_the_resolved_version() -> None:
    """``src.__version__`` must be whatever the resolver answers for the repo."""
    assert src.__version__ == resolve_version()
    assert resolve_version() == resolve_version(project_root())


def test_src_init_holds_no_version_literal() -> None:
    """A hand-maintained literal must not come back into the package."""
    text = (REPO / "src" / "__init__.py").read_text(encoding="utf-8")
    assert '__version__ = "' not in text
    assert "__version__ = '" not in text


def test_this_checkout_answers_from_its_own_repository() -> None:
    """Run against a real checkout, the resolver must reach git, not the fallback."""
    if not (REPO / ".git").exists():
        pytest.skip("not a git checkout")
    assert describe(REPO)
    assert resolve_version(REPO) != UNKNOWN_VERSION
