# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Resolve the version of the ``src`` package.

The version is derived, never written down. A source checkout answers from
the nearest ``v<digit>...`` git tag; a frozen bundle carries no repository
and answers from the value the build stamped into the package as
``BAKED_FILENAME``. Only a tree sitting exactly on a version tag, with no
modifications, reports a bare release number. Every other state carries a
PEP 440 local segment after a ``+``.
"""

from __future__ import annotations

import sys
from pathlib import Path

BAKED_FILENAME = "_baked_version.txt"
DIRTY_SUFFIX = ".dirty"
UNKNOWN_VERSION = "0.1.0+unknown"
UNTAGGED_RELEASE = "0.1.0"

# Without this glob `git describe --tags` answers with the nearest tag of
# any kind, including local backup tags.
TAG_GLOB = "v[0-9]*"

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
    return describe_tags(base, TAG_GLOB, DIRTY_SUFFIX)


def _split_describe(text: str) -> tuple[str, int, str] | None:
    """Split ``v<tag>-<distance>-g<commit>`` into its three parts.

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
    return tag[1:], int(distance), commit


def format_describe(text: str) -> str:
    """Turn ``git describe`` output into the version string to report.

    A bare release comes back only from distance zero on a clean tree.
    Distance, a modified tree and an unreachable version tag each add a
    local segment.
    """
    dirty = text.endswith(DIRTY_SUFFIX)
    core = text[: -len(DIRTY_SUFFIX)] if dirty else text
    split = _split_describe(core)
    if split is None:
        release = UNTAGGED_RELEASE
        local = ["dev", f"g{core}"]
    else:
        release, distance, commit = split
        local = [] if distance == 0 else ["dev", str(distance), commit]
    if dirty:
        local.append("dirty")
    return f"{release}+{'.'.join(local)}" if local else release


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
