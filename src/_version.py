# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Resolve the version of the ``src`` package.

``RELEASE`` declares the release number for a tree with no tags, no history and
no network. ``describe`` adds the build count and the commit as a PEP 440 local
segment after a ``+``. ``UNRESOLVED_LOCAL`` names a count ``describe`` could not
derive, and ``BAKED_FILENAME`` carries the value a build stamped in.
"""

from __future__ import annotations

import sys
from pathlib import Path

RELEASE = "0.2.0"

BAKED_FILENAME = "_baked_version.txt"
DIRTY_SUFFIX = ".dirty"
UNRESOLVED_LOCAL = "unknown"
UNKNOWN_VERSION = f"{RELEASE}+{UNRESOLVED_LOCAL}"

# `git describe` answers for this one tag or not at all. A pattern admitting
# any version tag lets a machine missing one count from an older tag.
RELEASE_TAG = f"v{RELEASE}"

_DESCRIBE_PARTS = 3


def is_frozen() -> bool:
    """Report whether this module is running inside a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Return the directory that holds the ``src`` package.

    Inside a bundle that is the unpacked directory PyInstaller reports as
    ``sys._MEIPASS``.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle)
    return Path(__file__).resolve().parents[1]


def describe(root: str | Path) -> str:
    """Return ``git describe`` output for the repository at ``root``, or ''.

    Every git subprocess in this repository belongs to the gate wrapper, so
    the call is delegated and imported lazily: a frozen bundle ships no
    ``tools`` package and must never depend on one. A directory with no
    ``.git`` answers '', which stops a bundle unpacked inside a checkout
    from reporting the enclosing repository's version.
    """
    base = Path(root)
    if not (base / ".git").exists():
        return ""
    try:
        from tools.gate import describe_tags
    except ImportError:
        return ""
    return describe_tags(base, RELEASE_TAG, DIRTY_SUFFIX)


def _split_describe(text: str) -> tuple[int, str] | None:
    """Split ``v<tag>-<distance>-g<commit>`` into its distance and its commit.

    Splits from the right, so a tag that itself contains a hyphen keeps it.
    Returns None for the bare commit id that ``--always`` falls back to.
    """
    parts = text.rsplit("-", 2)
    if len(parts) != _DESCRIBE_PARTS:
        return None
    tag, distance, commit = parts
    if not tag.startswith("v") or not distance.isdigit():
        return None
    if not commit.startswith("g"):
        return None
    return int(distance), commit


def format_describe(text: str) -> str:
    """Turn ``git describe`` output into the version string to report.

    ``RELEASE`` is the whole number before the ``+``. A distance, a modified
    tree and a ``RELEASE_TAG`` that ``describe`` could not reach each add a
    local segment.
    """
    dirty = text.endswith(DIRTY_SUFFIX)
    core = text[: -len(DIRTY_SUFFIX)] if dirty else text
    split = _split_describe(core)
    if split is None:
        local = [UNRESOLVED_LOCAL] + ([f"g{core}"] if core else [])
    else:
        distance, commit = split
        local = [] if distance == 0 else ["dev", str(distance), commit]
    if dirty:
        local.append("dirty")
    return f"{RELEASE}+{'.'.join(local)}" if local else RELEASE


def baked_path(root: str | Path) -> Path:
    """Return where a build stamps the version, relative to a project root."""
    return Path(root) / "src" / BAKED_FILENAME


def read_baked_version(root: str | Path) -> str:
    """Return the version a build stamped in, or '' when there is none."""
    try:
        return baked_path(root).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def resolve_version(root: str | Path | None = None) -> str:
    """Return the version for the tree at ``root``, defaulting to this package.

    A frozen bundle answers from the baked file first. A source checkout
    answers from git, and reaches a baked file only when git cannot answer.
    """
    base = Path(root) if root is not None else project_root()
    if is_frozen():
        frozen_baked = read_baked_version(base)
        if frozen_baked:
            return frozen_baked
    described = describe(base)
    if described:
        return format_describe(described)
    return read_baked_version(base) or UNKNOWN_VERSION
