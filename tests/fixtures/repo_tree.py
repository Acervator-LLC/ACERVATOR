"""Which paths in the repository are source, for a test that walks the tree.

`is_source` drops any path holding a build-output, cache or vendor part.
A PyInstaller run writes a copy of every `src` module under `dist`, which
`named` and `source_files` would otherwise return a second time.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A path with any of these parts is not source. Each says why.
NOT_SOURCE_PARTS = frozenset(
    {
        ".git",  # object store
        ".pytest_cache",  # tool cache
        ".ruff_cache",  # tool cache
        ".mypy_cache",  # tool cache
        "__pycache__",  # bytecode
        "build",  # build output
        "dist",  # build output, holds a copy of every src module
        "node_modules",  # third-party
        "scratchpad",  # agent working files
        "vendor",  # third-party, React itself
    }
)


def is_source(path: Path) -> bool:
    """Whether `path` is a file this repository authors."""
    return not (set(path.parts) & NOT_SOURCE_PARTS)


def named(name: str, root: Path | None = None) -> list:
    """Every source file called `name`, build output left out."""
    base = REPO_ROOT if root is None else root
    return sorted(path for path in base.rglob(name) if is_source(path))


def source_files(root: Path | None = None) -> list:
    """Every source file under `root`, build output left out."""
    base = REPO_ROOT if root is None else root
    return sorted(
        path for path in base.rglob("*") if path.is_file() and is_source(path)
    )
