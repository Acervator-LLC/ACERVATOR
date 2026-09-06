"""A shipped file may not name a path that is not in the tree.

Every path a file in ``SHIPPED`` names is checked with ``Path.exists()``, and
the pytest ``addopts`` and the README install step are each read the same way;
``doc_pages`` extends the scan to every Markdown page under ``docs/`` except the
``MEASUREMENT_RECORDS``. A block of prose may name an absent path when that same
block carries one of ``ABSENCE_MARKERS``. ``RETIRED_DOCKER`` names the two
deployment files that must stay deleted.
"""

from __future__ import annotations

import re
import tomllib
from functools import cache
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

# A token whose left edge touches one of these is the tail of a glob, not a
# path: ``test_*_surface_parity.py`` names a family, never a file.
_GLOB = "*?]"

# A block that carries one of these may name a path that is gone. Each
# asserts the absence in the page's own words, so a reader is not sent
# looking for a file.
ABSENCE_MARKERS = (
    "not in the tree",
    "not in this repository",
    "no commit that added",
    "none is committed",
    "not committed",
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


def _line_excused(line: str) -> bool:
    """Whether one line carries an ``ABSENCE_MARKERS`` entry of its own.

    One table row is excused while every other row in that block is read.
    """
    return any(marker in " ".join(line.split()) for marker in ABSENCE_MARKERS)


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


# ── documentation pages ──────────────────────────────────────────────

DOCS = REPO_ROOT / "docs"

# Pages whose dead citations are ROWS OF A MEASUREMENT TABLE: each row
# names a file the run read, on the dated tree the page names. Repointing
# a row would report a measurement that was never taken, so the scan does
# not read these pages. A page joins this list only when its table rows
# are the citations; prose that names a dead path belongs in no record.
MEASUREMENT_RECORDS: dict[str, str] = {
    "docs/audits/manual-original-parts-audit.md": (
        "the manual read against the tree of the day; it also quotes the "
        "tokens the PDF extractor damaged"
    ),
    "docs/engineering-notes/2026-08-24_archetype_census.md": (
        "one archetype run over every file present that day"
    ),
    "docs/engineering-notes/2026-08-25_subsystem_capability_matrix.md": (
        "one capability sweep; the rows are the files it read"
    ),
    "docs/engineering-notes/2026-08-25_the_venue_seam.md": (
        "one probe run; the probe files were removed after it"
    ),
    "docs/engineering-notes/2026-08-26_issue_revalidation.md": (
        "one probe run; the probe files were removed after it"
    ),
    "docs/engineering-notes/2026-08-27_gui_hex_literal_inventory.md": (
        "one tokenizer pass over src/gui/ at the commit it names"
    ),
    "docs/engineering-notes/2026-08-27_simulator_fleet_nuclear_divergence.md": (
        "one import census over tests/ at the commit it names"
    ),
    "docs/engineering-notes/2026-08-28_linux_server_readiness.md": (
        "one CI run read on ubuntu-24.04; the rows name the files it read "
        "and the scratch trees its controls built"
    ),
}

# The two roots the running platform owns, kept outside this repository.
_RUNTIME_ROOTS = (".acervator/", ".acervator_logs/")

# A block naming one of these describes a tree outside this repository:
# the platform's runtime state, or the operator's Claude Code harness.
_EXTERNAL_ROOTS = ("~/.acervator", "~/.claude")

# Only a DATA file is excused inside an external-root block. A module or
# a page named there must still resolve, so a dead citation cannot hide
# in a paragraph that happens to mention the runtime tree.
_DATA_EXT = frozenset(
    {"cfg", "ini", "json", "jsonl", "log", "toml", "txt", "yaml", "yml"}
)

# A path segment of this shape is a deployment placeholder.
_PLACEHOLDER = re.compile(r"^__[A-Z_]+__$")


def doc_pages() -> list[str]:
    """Every Markdown page under ``docs/`` that the scan reads."""
    return sorted(
        rel
        for rel in (
            path.relative_to(REPO_ROOT).as_posix() for path in DOCS.rglob("*.md")
        )
        if rel not in MEASUREMENT_RECORDS
    )


@cache
def _generated_names() -> frozenset[str]:
    """File names the repository's own ``.gitignore`` excludes.

    ``.release_ready.json`` and ``bot_state.json`` are written at run time
    and the tree never holds them.
    """
    names: set[str] = set()
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for line in text.split("\n"):
        entry = line.split("#", 1)[0].strip().lstrip("!")
        if not entry or entry.endswith("/"):
            continue
        leaf = entry.rsplit("/", 1)[-1]
        if not set(leaf) & set("*?["):
            names.add(leaf)
    return frozenset(names)


@cache
def _path_suffixes() -> frozenset[str]:
    """Every trailing run of path parts of every source file.

    A page writes ``scrumming/fold_tranches.py`` for
    ``src/trading/scrumming/fold_tranches.py``, and the shorter form names
    the same file.
    """
    out: set[str] = set()
    for path in source_files():
        parts = path.relative_to(REPO_ROOT).parts
        out.update("/".join(parts[start:]) for start in range(len(parts)))
    return frozenset(out)


def _block_names_an_external_root(block: list[str]) -> bool:
    joined = " ".join(block)
    return any(root in joined for root in _EXTERNAL_ROOTS)


def _doc_resolves(token: str, page: Path, outside: bool, external: bool) -> bool:
    if token.startswith(_RUNTIME_ROOTS):
        return True
    if token.rsplit("/", 1)[-1] in _generated_names():
        return True
    if outside or any(_PLACEHOLDER.match(part) for part in token.split("/")):
        return True
    if external and token.rsplit(".", 1)[-1] in _DATA_EXT:
        return True
    if "/" not in token:
        return token in _file_names()
    if token in _path_suffixes():
        return True
    candidate = (page.parent / token).resolve()
    return candidate.is_relative_to(REPO_ROOT) and candidate.exists()


def _scan_page(page: Path, label: str) -> list[str]:
    """Every path claim in ``page`` that resolves to nothing."""
    bad: list[str] = []
    for start, block in _blocks(page):
        if _block_excused(block):
            continue
        external = _block_names_an_external_root(block)
        for offset, line in enumerate(block):
            if _line_excused(line):
                continue
            masked = _URL.sub(" ", line)
            for match in _TOKEN.finditer(masked):
                token = match.group(0)
                before = masked[match.start() - 1] if match.start() else ""
                if before in _GLOB:
                    continue
                outside = before in "/\\"
                if _doc_resolves(token, page, outside, external):
                    continue
                bad.append(f"{label}:{start + offset}: {token}")
    return bad


@pytest.mark.parametrize("rel", doc_pages())
def test_doc_page_names_no_missing_path(rel: str) -> None:
    """Every path a documentation page names must be in the tree."""
    assert _scan_page(REPO_ROOT / rel, rel) == []


def test_every_measurement_record_is_still_a_page() -> None:
    """A record that leaves the tree must leave the exclusion list with it.

    An entry naming a page that is gone would silence a later page of the
    same name.
    """
    missing = [rel for rel in MEASUREMENT_RECORDS if not (REPO_ROOT / rel).is_file()]
    assert missing == [], f"MEASUREMENT_RECORDS names pages that are gone: {missing}"


def test_the_doc_scan_reports_a_dead_path(tmp_path: Path) -> None:
    """The control for the scan above: a dead path must be reported."""
    page = tmp_path / "planted.md"
    page.write_text(
        "The panel is built in `src/gui/not_in_the_tree_at_all.py`.\n",
        encoding="utf-8",
    )
    assert _scan_page(page, "planted.md") == [
        "planted.md:1: src/gui/not_in_the_tree_at_all.py"
    ]


def test_the_doc_scan_leaves_a_live_path_alone(tmp_path: Path) -> None:
    """The other half of the control: a real path must not be reported."""
    page = tmp_path / "planted.md"
    page.write_text(
        "The log root is set in `src/core/log_paths.py`.\n", encoding="utf-8"
    )
    assert _scan_page(page, "planted.md") == []


def test_the_doc_scan_reads_a_glob_as_a_family_not_a_file(tmp_path: Path) -> None:
    """``_scan_page`` reports nothing for a token whose left edge is in ``_GLOB``."""
    page = tmp_path / "planted.md"
    page.write_text(
        "Only a `test_*_surface_parity.py` importing one of each is read.\n",
        encoding="utf-8",
    )
    assert _scan_page(page, "planted.md") == []


def test_the_glob_rule_still_reports_a_dead_path_beside_it(tmp_path: Path) -> None:
    """``_scan_page`` still reports a dead path sharing a line with a ``_GLOB`` token."""
    page = tmp_path / "planted.md"
    page.write_text(
        "`test_*_surface_parity.py` and `src/gui/gone_from_the_tree.py`.\n",
        encoding="utf-8",
    )
    assert _scan_page(page, "planted.md") == [
        "planted.md:1: src/gui/gone_from_the_tree.py"
    ]


def test_a_measurement_record_is_not_scanned() -> None:
    """No page in ``MEASUREMENT_RECORDS`` reaches the parametrised scan."""
    scanned = set(doc_pages())
    assert scanned & set(MEASUREMENT_RECORDS) == set()
    assert scanned, "doc_pages found no page to scan"


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


def _docker_mentions_under(root: Path) -> list[str]:
    """Every line under ``root`` that ``source_files`` calls source and names Docker.

    ``source_files`` drops ``node_modules``, which ``npm install`` writes under
    ``desktop`` and which carries the word in third-party changelogs.
    """
    hits: list[str] = []
    for path in source_files(root):
        if path.suffix.lower() not in _SCAN_SUFFIXES:
            continue
        rel = path.relative_to(root)
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


def _docker_mentions() -> list[str]:
    """Every line of a live source file in this repository that names Docker."""
    return _docker_mentions_under(REPO_ROOT)


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


def test_the_docker_scan_reports_a_script_that_calls_it(tmp_path: Path) -> None:
    """Control: the scan above expects [], and so does a scan reading nothing."""
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "run.sh").write_text(
        "#!/bin/sh\ndocker compose up\n", encoding="utf-8"
    )
    assert _docker_mentions_under(tmp_path) == ["deploy/run.sh:2: docker compose up"]


def test_the_docker_scan_skips_an_installed_dependency(tmp_path: Path) -> None:
    """``npm install`` writes changelogs naming Docker under ``node_modules``."""
    vendored = tmp_path / "desktop" / "node_modules" / "progress"
    vendored.mkdir(parents=True)
    (vendored / "CHANGELOG.md").write_text(
        "* Fix: prevent crash in Docker\n", encoding="utf-8"
    )
    assert _docker_mentions_under(tmp_path) == []
