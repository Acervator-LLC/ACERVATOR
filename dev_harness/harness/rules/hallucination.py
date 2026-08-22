"""hallucination.py — universal hallucination detector.

Reference specification (Diataxis: reference). Consumed by
coding_archetype, gui_archetype, docs_archetype. Introduced 2026-08-01
as v3.23.91 alongside the scaffolding rule (v3.23.90).

Detectors — each fires as a normalized Finding matching the
ArchetypeReport schema in tools.harness.coding_archetype:

    H001 (medium) — DEAD PATH REFERENCE
        Comments, docstrings, or markdown text mention a file path
        (e.g., ``src/trading/foo.py`` or ``docs/audits/…/report.md``)
        that does not exist on disk. Common hallucination when
        copying an old block or when a file was renamed / archived
        without updating the reference.

    H002 (low) — DEAD ARCHITECTURE REFERENCE
        Mentions of retired subsystems that no longer exist in the
        current tree: ``sadp/``, ``deprecated_sadp/``,
        ``RAIntSimBat/``, ``simulator_tab/basic_modes_panel.py``
        (retired v3.23.79-A). Exceptions: files under _archive/ or
        docs/audits/ are allowed to reference retired names (that's
        the retirement documentation itself).

    H003 (medium) — IMPORT OF LOCAL MODULE THAT DOESN'T EXIST
        ``from src.foo.bar import baz`` or ``import src.foo.bar``
        where ``src/foo/bar.py`` (or ``src/foo/bar/__init__.py``)
        does not exist. Stdlib and third-party imports are skipped
        (their availability is validated by pip / interpreter at
        install time).

FALSIFICATION — this rule module is wrong if:
  (a) H001 fires on a path that exists via a case-sensitivity
      quirk (Windows FS is case-insensitive; the check is
      case-sensitive by design to catch typos);
  (b) H002 fires on a legitimate historical narrative in a
      release-notes file outside the exempt paths (add its dir
      to _H002_EXEMPT_DIRS);
  (c) H003 misses a symlinked local module that resolves at
      runtime via sys.path manipulation (rare; not attempted);
  (d) H001/H002/H003 fires on a fenced code block in markdown
      that is intentionally showing "how it USED to be" — no
      fenced-block filter is implemented for v1.

sadp: R28 SSS + R70 RCN
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Finding:
    tool: str
    severity: str
    file: str
    line: int
    rule_id: str
    message: str


# --------------------------------------------------------------------- #
# H001 — dead path reference                                            #
# --------------------------------------------------------------------- #

# Match patterns like `src/foo/bar.py`, `docs/audits/2026-…/x.md`,
# `.claude/hooks/foo.py`, `tests/test_x.py`. Anchor on at least one
# slash + a recognised code/docs extension so we don't fire on prose
# containing dotted names ("scrumming_bot.py" alone is ambiguous).
_PATH_PATTERN = re.compile(
    r"[a-zA-Z0-9_\-./]*[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-./]+"
    r"\.(py|md|markdown|json|toml|yaml|yml|csv|txt|log)"
)

# Prefixes that indicate a path is INSIDE the repo root and should be
# resolved relative to it. Any path starting with these + is a valid
# extension is checked against disk.
_REPO_PATH_PREFIXES = (
    "src/", "src\\",
    "tests/", "tests\\",
    "tools/", "tools\\",
    "docs/", "docs\\",
    ".claude/", ".claude\\",
    "_archive/", "_archive\\",
    "_logs/", "_logs\\",
)


def _find_dead_paths(source: str, repo_root: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    for i, line in enumerate(source.splitlines(), start=1):
        for match in _PATH_PATTERN.finditer(line):
            raw = match.group(0)
            norm = raw.replace("\\", "/")
            # Only check paths that look repo-relative
            if not any(norm.startswith(p.replace("\\", "/"))
                       for p in _REPO_PATH_PREFIXES):
                continue
            candidate = (repo_root / norm).resolve()
            # Guard against path traversal outside the repo
            try:
                candidate.relative_to(repo_root.resolve())
            except ValueError:
                continue
            if candidate.exists():
                continue
            key = (i, norm)
            if key in seen:
                continue
            seen.add(key)
            hits.append((i, norm))
    return hits


# --------------------------------------------------------------------- #
# H002 — dead architecture reference                                    #
# --------------------------------------------------------------------- #

_RETIRED_NAMES = (
    "sadp/", "sadp\\",
    "deprecated_sadp/", "deprecated_sadp\\",
    "RAIntSimBat/", "RAIntSimBat\\",
    "basic_modes_panel",  # retired v3.23.79-A
)

# Files under these directories are ALLOWED to mention retired names
# (they're the retirement documentation itself, changelogs, or archived
# copies that predate the retirement).
_H002_EXEMPT_DIRS = (
    "_archive/", "_archive\\",
    "docs/audits/",  "docs\\audits\\",
    "docs/hop_scratch/",  "docs\\hop_scratch\\",
)


def _find_dead_architecture(
    source: str, target: Path, repo_root: Path,
) -> list[tuple[int, str]]:
    try:
        rel = str(target.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        rel = str(target)
    rel_norm = rel.replace("\\", "/")
    if any(rel_norm.startswith(e.replace("\\", "/"))
           for e in _H002_EXEMPT_DIRS):
        return []
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(source.splitlines(), start=1):
        for token in _RETIRED_NAMES:
            if token in line:
                hits.append((i, token.rstrip("/\\")))
                break
    return hits


# --------------------------------------------------------------------- #
# H003 — import of local module that doesn't exist                     #
# --------------------------------------------------------------------- #

_LOCAL_IMPORT_PREFIXES = ("src.", "tests.", "tools.")


def _find_dead_imports(tree: ast.AST, repo_root: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []

    def _resolve_module_path(dotted: str) -> Path | None:
        parts = dotted.split(".")
        # Try as file first: foo/bar/baz.py
        as_file = repo_root.joinpath(*parts).with_suffix(".py")
        if as_file.exists():
            return as_file
        # Then as package: foo/bar/baz/__init__.py
        as_pkg = repo_root.joinpath(*parts, "__init__.py")
        if as_pkg.exists():
            return as_pkg
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if not any(module.startswith(p)
                       for p in _LOCAL_IMPORT_PREFIXES):
                continue
            if _resolve_module_path(module) is None:
                hits.append((node.lineno, module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if not any(name.startswith(p)
                           for p in _LOCAL_IMPORT_PREFIXES):
                    continue
                if _resolve_module_path(name) is None:
                    hits.append((node.lineno, name))
    return hits


# --------------------------------------------------------------------- #
# Repo root discovery                                                   #
# --------------------------------------------------------------------- #


def _find_repo_root(start: Path) -> Path:
    """Walk parents until we find one containing pyproject.toml OR
    src/ + tools/ (repo markers). Fall back to start's parent."""
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    for candidate in [cur, *cur.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
        if ((candidate / "src").is_dir()
                and (candidate / "tools").is_dir()):
            return candidate
    return start.parent if start.is_file() else start


# --------------------------------------------------------------------- #
# Public entry                                                          #
# --------------------------------------------------------------------- #


def scan(target: Path, source: str) -> list[Any]:
    """Return a list of Finding-shaped objects. Returns [] on empty
    source or non-scannable suffix."""
    suffix = target.suffix.lower()
    if suffix not in (".py", ".md", ".markdown"):
        return []
    repo_root = _find_repo_root(target)
    findings: list[Any] = []

    for line, path in _find_dead_paths(source, repo_root):
        findings.append(Finding(
            tool="hallucination", severity="medium",
            file=str(target), line=line, rule_id="H001",
            message=(
                f"referenced path {path!r} does not exist on disk. "
                "Common hallucination when copying old code or when "
                "a file was renamed/archived without updating this "
                "reference.")))

    for line, token in _find_dead_architecture(source, target, repo_root):
        findings.append(Finding(
            tool="hallucination", severity="low",
            file=str(target), line=line, rule_id="H002",
            message=(
                f"reference to retired subsystem {token!r} outside "
                "an exempt archive/audits directory. This name no "
                "longer exists in the current tree.")))

    if suffix == ".py":
        try:
            tree = ast.parse(source, filename=str(target))
        except SyntaxError:
            tree = None
        if tree is not None:
            for line, module in _find_dead_imports(tree, repo_root):
                findings.append(Finding(
                    tool="hallucination", severity="medium",
                    file=str(target), line=line, rule_id="H003",
                    message=(
                        f"import of local module {module!r} does "
                        "not resolve to a file on disk. Typo, "
                        "rename, or hallucinated module name.")))

    return findings


__all__ = ["Finding", "scan"]
