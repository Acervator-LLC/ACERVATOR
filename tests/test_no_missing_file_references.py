"""A shipped file may not name a path that is not in the tree.

Every path a file in ``SHIPPED`` names is checked with ``Path.exists()``, and
the pytest ``addopts`` ignores, the README install step and the README project
structure are each read the same way. A block of prose may name an absent path
when that same block carries one of ``ABSENCE_MARKERS``; the marker is per
block, so one sentence cannot excuse a whole document. ``RETIRED_DOCKER`` names
the two deployment files that must stay deleted.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from tests.fixtures.repo_tree import source_files

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that ship to a user or drive a build.
SHIPPED = (
    "pyproject.toml",
    "README.md",
    "CONTRIBUTING.md",
    "DISCLAIMER.md",
    # The root changelog is a live document, not a transcript. Its one
    # path claim is the link to the archived narrative changelog.
    "CHANGELOG.md",
)

# Extensions that make a token a path claim rather than prose.
_EXT = (
    "py",
    "md",
    "pdf",
    "txt",
    "json",
    "toml",
    "yml",
    "yaml",
    "cfg",
    "ini",
    "sol",
    "sh",
    "ps1",
    "bat",
    "spec",
)
_TOKEN = re.compile(
    r"(?:[A-Za-z0-9_.\-]+/)*[A-Za-z0-9_.\-]+\.(?:" + "|".join(_EXT) + r")"
    r"(?![A-Za-z0-9_])",
)
_URL = re.compile(r"https?://\S+")

# A block that carries one of these may name a path that is gone.
ABSENCE_MARKERS = (
    "not in the tree",
    "not in this repository",
)

# TOML table headers read as paths: ``[tool.coverage.json]`` ends in
# ``.json``. They are section names, not files.
_TOML_HEADER_PREFIX = "tool."

# Path claims that are true for a reason the scanner cannot see. Every
# entry carries that reason. This map may not grow without one.
ALLOWED: dict[tuple[str, str], str] = {
    # A coverage output path, not a file the repo ships.
    (
        "pyproject.toml",
        "qa_baselines/coverage_current.json",
    ): "coverage output path; coverage creates the directory on demand",
    # Template placeholders in the contributor instructions.
    ("CONTRIBUTING.md", "tests/test_your_file.py"): "placeholder, not a claim",
    ("CONTRIBUTING.md", "src/your_file.py"): "placeholder, not a claim",
    # Runtime state. ``~/.acervator/bot_state.json`` is written by the
    # running platform and is never in the source tree.
    ("README.md", "bot_state.json"): "runtime state under ~/.acervator/",
}


def _file_names() -> set[str]:
    """Every file name in the tree, to resolve a bare file name.

    A document that gave the directory once may then name a file on its
    own: ``docs_archetype.py`` beside
    ``dev_harness/harness/coding_archetype.py``. A bare name resolves if
    a file of that name is anywhere in the tree. A name that carries a
    separator must resolve exactly.
    """
    return {path.name for path in source_files()}


def _resolves(token: str, names: set[str]) -> bool:
    if token.startswith(_TOML_HEADER_PREFIX):
        return True
    if "/" in token:
        return (REPO_ROOT / token).exists()
    return token in names


def _blocks(path: Path) -> list[tuple[int, list[str]]]:
    """Split a file into blocks of (first line number, lines).

    In a config file a block is a run of comment lines. In Markdown a
    block is a run of non-blank lines. Every other line is its own
    block.
    """
    lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    comment_only = (
        path.suffix in (".toml", ".yml", ".yaml") or path.name == "Dockerfile"
    )
    out: list[tuple[int, list[str]]] = []
    current: list[str] = []
    start = 1
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        is_body = stripped.startswith("#") if comment_only else bool(stripped)
        if is_body:
            if not current:
                start = lineno
            current.append(line)
            continue
        if current:
            out.append((start, current))
            current = []
        out.append((lineno, [line]))
    if current:
        out.append((start, current))
    return out


def _block_excused(block: list[str]) -> bool:
    joined = " ".join(line.lstrip("# ").strip() for line in block)
    joined = " ".join(joined.split())
    return any(marker in joined for marker in ABSENCE_MARKERS)


def _bad_tokens(name: str, names: set[str]) -> list[str]:
    bad: list[str] = []
    for start, block in _blocks(REPO_ROOT / name):
        if _block_excused(block):
            continue
        for offset, line in enumerate(block):
            for match in _TOKEN.finditer(_URL.sub(" ", line)):
                token = match.group(0)
                if _resolves(token, names) or (name, token) in ALLOWED:
                    continue
                bad.append(f"{name}:{start + offset}: {token}")
    return bad


@pytest.mark.parametrize("name", SHIPPED)
def test_shipped_file_names_no_missing_path(name: str) -> None:
    """Every path a shipped file names must be in the tree."""
    path = REPO_ROOT / name
    assert path.is_file(), f"{name} is missing"
    assert _bad_tokens(name, _file_names()) == []


# ── README Project Structure tree ────────────────────────────────────

_ENTRY = re.compile(r"^((?:(?:│   )|(?:    ))*)(?:├── |└── )(.*)$")
_TRAILING_COMMENT = re.compile(r"\s{2,}#.*$")


def _tree_entries() -> list[tuple[str, int]]:
    """Return (repo-relative path, README line number) for each entry."""
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8").split("\n")
    start = next(
        i for i, line in enumerate(text) if line.startswith("## Project Structure")
    )
    fence = [
        i for i, line in enumerate(text[start:], start=start) if line.startswith("```")
    ]
    assert len(fence) >= 2, "the Project Structure block has no fence"
    body = text[fence[0] + 1 : fence[1]]

    stack: list[str] = []
    entries: list[tuple[str, int]] = []
    for offset, line in enumerate(body):
        match = _ENTRY.match(line)
        if not match:
            continue
        depth = len(match.group(1)) // 4
        label = _TRAILING_COMMENT.sub("", match.group(2)).strip()
        if not label or label.startswith("#"):
            continue
        lineno = fence[0] + 2 + offset
        stack = stack[:depth]
        if label.endswith("/"):
            stack.append(label.rstrip("/"))
            entries.append(("/".join(stack), lineno))
            continue
        entries.extend(
            ("/".join([*stack, part]), lineno)
            for part in (p.strip() for p in label.split("·"))
            if part
        )
    return entries


def test_readme_project_structure_tree_resolves() -> None:
    """Every entry drawn in the README tree must be in the tree.

    The Project Structure block held the worst of the rot: 8 documents
    under ``docs/``, a ``logs/`` subtree and 9 modules under ``src/``
    that are not there. A reader uses this block to find a file.
    """
    entries = _tree_entries()
    assert len(entries) > 40, f"the parser found only {len(entries)} entries"
    missing = [
        f"README.md:{line}: {path}"
        for path, line in entries
        if not (REPO_ROOT / path).exists()
    ]
    assert missing == []


# ── pyproject structural claims ──────────────────────────────────────


def _pyproject() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_pyproject_config_paths_exist() -> None:
    """Coverage sources, vulture paths and testpaths must all be real.

    A ``source`` entry that names a directory which is not there
    contributes no files. Coverage prints one warning and carries on, so
    the reported percentage describes a smaller set than the config
    claims.
    """
    conf = _pyproject()
    claims: list[str] = []
    claims += [
        f"[tool.coverage.run] source: {p}"
        for p in conf["tool"]["coverage"]["run"]["source"]
    ]
    claims += [f"[tool.vulture] paths: {p}" for p in conf["tool"]["vulture"]["paths"]]
    claims += [
        f"[tool.pytest.ini_options] testpaths: {p}"
        for p in conf["tool"]["pytest"]["ini_options"]["testpaths"]
    ]
    missing = [c for c in claims if not (REPO_ROOT / c.split(": ", 1)[1]).exists()]
    assert missing == []


def test_pytest_addopts_ignores_nothing_that_is_gone() -> None:
    """An ``--ignore=`` for a path that is not there hides the rot.

    pytest accepts it in silence, so the entry reads as a live exclusion
    long after the file it named has gone.
    """
    ini = _pyproject()["tool"]["pytest"]["ini_options"]
    ignored = re.findall(r"--ignore=(\S+)", ini.get("addopts", ""))
    missing = [p for p in ignored if not (REPO_ROOT / p).exists()]
    assert missing == []


def test_readme_install_step_names_a_real_dependency_source() -> None:
    """The install step must name a dependency source that is present.

    A step naming ``requirements.txt`` fails at once, because no
    requirements file is in the tree.
    """
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for match in re.finditer(r"pip install\s+(?:--\S+\s+)*-r\s+(\S+)", text):
        target = match.group(1)
        assert (REPO_ROOT / target).exists(), (
            f"the README install step reads {target}, " "which is not in the tree"
        )
    assert _pyproject()["project"]["dependencies"], (
        "pyproject.toml declares no dependencies, so `pip install -e .` "
        "installs nothing"
    )


RETIRED_DOCKER = ("Dockerfile", "docker-compose.yml")

# A retired deployment must leave no caller behind. These are the parts
# of the tree the scan does not read, and why each one is out.
_SCAN_SKIP_PARTS = {
    ".git",  # object store, not source
    "__pycache__",  # bytecode
    ".pytest_cache",  # tool cache
    ".claude",  # session settings hold past shell command text
    "build",  # build output
    "dist",  # build output; vendored keyring metadata says Docker
}
_SCAN_SKIP_DIRS = (
    "docs/audits",  # historical record, kept as written
    "docs-archive",  # historical record, kept as written
)
_SCAN_SKIP_FILES = {
    Path(__file__).name,  # this file carries the record of the removal
}
# Suffixes that make a file source rather than data or an image.
_SCAN_SUFFIXES = {
    ".py",
    ".md",
    ".toml",
    ".yml",
    ".yaml",
    ".json",
    ".cfg",
    ".ini",
    ".txt",
    ".sh",
    ".ps1",
    ".bat",
    ".spec",
    ".service",
    ".desktop",
}


def _docker_mentions() -> list[str]:
    """Every line of a live source file that names Docker."""
    hits: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _SCAN_SUFFIXES:
            continue
        rel = path.relative_to(REPO_ROOT)
        if set(rel.parts) & _SCAN_SKIP_PARTS or rel.name in _SCAN_SKIP_FILES:
            continue
        if any(rel.is_relative_to(skip) for skip in _SCAN_SKIP_DIRS):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hits += [
            f"{rel.as_posix()}:{n}: {line.strip()[:70]}"
            for n, line in enumerate(text.split("\n"), start=1)
            if "docker" in line.lower()
        ]
    return hits


def test_retired_docker_build_files_are_gone() -> None:
    """The Docker build is deleted, and it may not return.

    The image copied a directory that no commit ever added, so it could
    not build; and it excluded the toolkit that the one entry point
    needs, so it could not run. Restoring either file re-states a claim
    that no code in this tree can satisfy.
    """
    present = [name for name in RETIRED_DOCKER if (REPO_ROOT / name).exists()]
    assert present == [], f"issue #89 retired the Docker build; {present} came back"


def test_nothing_references_the_retired_docker_build() -> None:
    """A retired deployment may not keep a caller in a live file.

    Deleting a build file and leaving a script, a document or a config
    that still calls it moves the false claim instead of ending it.
    """
    assert _docker_mentions() == []
