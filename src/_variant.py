# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Resolve which build variant of the application is running.

A variant selects between two implementations of the same surface, so the
React conversion and the Qt original can be built as separate executables
and run against each other. The value is derived the way the version is: a
frozen bundle answers from the file the build baked in, and a source
checkout answers from the environment. Neither reads a literal held in the
application.
"""

from __future__ import annotations

import os
from pathlib import Path

from ._version import is_frozen, project_root

BAKED_FILENAME = "_baked_variant.txt"
ENV_VAR = "ACERVATOR_VARIANT"

REACT = "react"
QT = "qt"

# Every variant the build and the application both understand.
VARIANTS: tuple[str, ...] = (REACT, QT)

# What an unstamped source checkout runs. The React panels are the shipping
# surface; the Qt originals are the preserved comparison.
DEFAULT_VARIANT = REACT


def baked_path(root: str | Path) -> Path:
    """Return where a build stamps the variant, relative to a project root."""
    return Path(root) / "src" / BAKED_FILENAME


def read_baked_variant(root: str | Path) -> str:
    """Return the variant a build stamped in, or '' when there is none."""
    try:
        return baked_path(root).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def normalise(name: str) -> str:
    """Return ``name`` as a known variant, or '' when it names none.

    An unknown name answers '' rather than raising, so a mistyped
    environment variable falls back to the default instead of stopping the
    application from starting.
    """
    candidate = (name or "").strip().lower()
    return candidate if candidate in VARIANTS else ""


def resolve_variant(root: str | Path | None = None) -> str:
    """Return the variant for the tree at ``root``, defaulting to this package.

    A frozen bundle answers from the baked file first, so a stray
    environment variable on the operator's machine cannot make one
    executable claim to be the other. A source checkout answers from the
    environment, which is how a test and a developer select a variant with
    no build in between.
    """
    base = Path(root) if root is not None else project_root()
    if is_frozen():
        baked = normalise(read_baked_variant(base))
        if baked:
            return baked
    from_env = normalise(os.environ.get(ENV_VAR, ""))
    if from_env:
        return from_env
    return normalise(read_baked_variant(base)) or DEFAULT_VARIANT
