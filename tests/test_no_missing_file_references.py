"""A shipped file may not name a path that is not in the tree.

WHAT WAS MEASURED
=================
Issue #69, on 2026-08-22, in a clone at commit b1bcd8b. Every path the
issue listed was checked with ``Path.exists()``. All of them were absent:

    RAIntSimBat.py            generate_essay.py       WHY_SADP.md
    ARCHITECTURE.md           docs/RISK_REGISTER.md   qa_baselines/
    tests/obsolete/           cloud/                  requirements.txt
    requirements-optional.txt tests/test_swarm_row_parity.py
    acervator_product_manual_v3_13_7.pdf

They fall into three classes, and the class decides the repair:

  INERT      ``--ignore=tests/obsolete`` and
             ``--ignore=tests/test_swarm_row_parity.py`` in pytest
             ``addopts``. pytest accepts an ignore for a path that is
             not in the tree. Collection returned 7382 tests with the
             two entries present and 7382 with them gone. Removal
             changed nothing except the truth of the file.

  BROKEN     The README install step ran ``pip install -r
             requirements.txt``, and no requirements file is in the
             tree, so the documented setup stopped at its first command.
             The README Project Structure block drew 8 documents under
             ``docs/``, a whole ``logs/`` subtree and 9 modules under
             ``src/`` that are not there.

  VACUOUS    ``[tool.mutmut] runner`` named two test files that are not
             in the tree. pytest exits 4 on a missing path, and mutmut
             reads any non-zero exit as "mutant killed". A mutation run
             would report every mutant killed while it ran zero tests.
             Nothing else read a qa_baselines file: the two tests the
             config said would read one
             (``tests/test_coverage_floor.py``,
             ``tests/test_mutation_baseline.py``) are not in the tree
             either. The config claimed a guard that never existed.

WHY A GUARD AND NOT A CLEANUP
=============================
``docs_archetype`` passed README.md green on 2026-08-22 while that
README named seven files which are not in the tree. No instrument in the
repo reads a shipped document and asks whether its paths resolve. This
test is that instrument.

HOW A DOCUMENT SAYS A FILE IS GONE
==================================
A document must be able to record an absence. A block of text may name a
path that is not in the tree when the same block carries one of the
phrases in ABSENCE_MARKERS. The marker is per block, not per file, so
one sentence cannot excuse a whole document.

TWO-SIDED CONTROL
==================
Driven both ways on 2026-08-22 against the same tree. The reverted files
failed the matching tests; the restored files passed and matched their
recorded sha256.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that ship to a user or drive a build. The same line issue #68
# drew for the retired-subsystem guard.
SHIPPED = (
    "pyproject.toml",
    "README.md",
    "CONTRIBUTING.md",
    "DISCLAIMER.md",
    "Dockerfile",
    "docker-compose.yml",
)

# Extensions that make a token a path claim rather than prose.
_EXT = (
    "py", "md", "pdf", "txt", "json", "toml", "yml", "yaml",
    "cfg", "ini", "sol", "sh", "ps1", "bat", "spec",
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
    # Coverage WRITE target. Measured 2026-08-22: ``python -m pytest
    # --cov --cov-report=json`` created ``qa_baselines/`` and wrote the
    # file. It is an output path, not a file the repo must ship.
    ("pyproject.toml", "qa_baselines/coverage_current.json"):
        "coverage output path; coverage creates the directory on demand",

    # Template placeholders in the contributor instructions.
    ("CONTRIBUTING.md", "tests/test_your_file.py"):
        "placeholder, not a claim",
    ("CONTRIBUTING.md", "src/your_file.py"):
        "placeholder, not a claim",

    # Issue #89 owns the Docker build. Recorded here, not hidden:
    # ``cloud/`` is not in the tree, so ``COPY cloud/requirements_cloud
    # .txt`` fails at the first COPY and the image cannot build. Delete
    # these entries when #89 lands.
    ("Dockerfile", "cloud/requirements_cloud.txt"):
        "issue #89, the Docker build is broken",
    ("Dockerfile", "requirements_cloud.txt"):
        "issue #89, the Docker build is broken",
    ("Dockerfile", "RAIntSimBat.py"):
        "issue #89, the Docker build is broken",
    ("Dockerfile", "cloud/acervator_daemon.py"):
        "issue #89, the Docker build is broken",
    ("Dockerfile", "cloud/config.json"):
        "issue #89, the Docker build is broken",
    ("docker-compose.yml", "./cloud/config.json"):
        "issue #89, the Docker build is broken",
    ("docker-compose.yml", "app/cloud/config.json"):
        "issue #89, a path inside the container",

    # Runtime state. ``~/.acervator/bot_state.json`` is written by the
    # running platform and is never in the source tree.
    ("README.md", "bot_state.json"):
        "runtime state under ~/.acervator/",
}


def _file_names() -> set[str]:
    """Every file name in the tree, to resolve a bare file name.

    A document that gave the directory once may then name a file on its
    own: ``docs_archetype.py`` beside
    ``dev_harness/harness/coding_archetype.py``. A bare name resolves if
    a file of that name is anywhere in the tree. A name that carries a
    separator must resolve exactly.
    """
    names: set[str] = set()
    for path in REPO_ROOT.rglob("*"):
        if "__pycache__" in path.parts or ".git" in path.parts:
            continue
        if path.is_file():
            names.add(path.name)
    return names


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
    comment_only = (path.suffix in (".toml", ".yml", ".yaml")
                    or path.name == "Dockerfile")
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
    start = next(i for i, line in enumerate(text)
                 if line.startswith("## Project Structure"))
    fence = [i for i, line in enumerate(text[start:], start=start)
             if line.startswith("```")]
    assert len(fence) >= 2, "the Project Structure block has no fence"
    body = text[fence[0] + 1:fence[1]]

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
            for part in (p.strip() for p in label.split("·")) if part
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
    missing = [f"README.md:{line}: {path}"
               for path, line in entries if not (REPO_ROOT / path).exists()]
    assert missing == []


# ── pyproject structural claims ──────────────────────────────────────

def _pyproject() -> dict:
    return tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_pyproject_config_paths_exist() -> None:
    """Coverage sources, vulture paths and testpaths must all be real.

    A ``source`` entry that names a directory which is not there
    contributes no files. Coverage prints one warning and carries on, so
    the reported percentage describes a smaller set than the config
    claims.
    """
    conf = _pyproject()
    claims: list[str] = []
    claims += [f"[tool.coverage.run] source: {p}"
               for p in conf["tool"]["coverage"]["run"]["source"]]
    claims += [f"[tool.vulture] paths: {p}"
               for p in conf["tool"]["vulture"]["paths"]]
    claims += [f"[tool.pytest.ini_options] testpaths: {p}"
               for p in conf["tool"]["pytest"]["ini_options"]["testpaths"]]
    missing = [c for c in claims
               if not (REPO_ROOT / c.split(": ", 1)[1]).exists()]
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

    Before issue #69 it ran ``pip install -r requirements.txt``, and no
    requirements file is in the tree, so the documented setup failed at
    its first command.
    """
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for match in re.finditer(r"pip install\s+(?:--\S+\s+)*-r\s+(\S+)", text):
        target = match.group(1)
        assert (REPO_ROOT / target).exists(), (
            f"the README install step reads {target}, "
            "which is not in the tree")
    assert _pyproject()["project"]["dependencies"], (
        "pyproject.toml declares no dependencies, so `pip install -e .` "
        "installs nothing")
