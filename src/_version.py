# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Resolve the version of the ``src`` package.

``RELEASE`` declares the release number for a tree with no history and no
network. ``read_stamp`` adds the two facts that identify one commit, its own
date and its own id, as a PEP 440 local segment after a ``+``.
``UNRESOLVED_LOCAL`` names a commit ``read_stamp`` could not reach, and
``BAKED_FILENAME`` carries the value a build stamped in.
"""

from __future__ import annotations

import sys
from pathlib import Path

RELEASE = "0.2.0"

BAKED_FILENAME = "_baked_version.txt"
DIRTY_SUFFIX = ".dirty"
UNRESOLVED_LOCAL = "unknown"
UNKNOWN_VERSION = f"{RELEASE}+{UNRESOLVED_LOCAL}"

# HEAD's committer date, rendered in the zone the commit itself records. It
# orders two builds without counting commits; a distance from a tag is equal
# for many commits and names none of them.
MOMENT_FORMAT = "%Y%m%d.%H%M"

# Fixed width. Git's own abbreviation grows with a clone's object count, so
# one commit would otherwise answer different widths in different clones.
COMMIT_DIGITS = 12

_STAMP_PARTS = 2


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


def read_stamp(root: str | Path) -> str:
    """Return HEAD's date and id at ``root``, with ``DIRTY_SUFFIX``, or ''.

    ``tools.gate`` holds both git calls and is imported lazily for a frozen
    bundle that ships no ``tools`` package, and a tree with no ``.git``
    answers ''.
    """
    base = Path(root)
    if not (base / ".git").exists():
        return ""
    try:
        from tools.gate import commit_stamp, tree_is_dirty
    except ImportError:
        return ""
    stamp = commit_stamp(base, MOMENT_FORMAT)
    if not stamp:
        return ""
    return stamp + DIRTY_SUFFIX if tree_is_dirty(base) else stamp


def format_stamp(text: str) -> str:
    """Turn ``read_stamp`` output into the version string to report.

    ``RELEASE`` leads, the local segment carries the date and the first
    ``COMMIT_DIGITS`` of the id, and a modified tree adds one more term.
    """
    dirty = text.endswith(DIRTY_SUFFIX)
    core = text[: -len(DIRTY_SUFFIX)] if dirty else text
    parts = core.split()
    if len(parts) != _STAMP_PARTS:
        local = [UNRESOLVED_LOCAL]
    else:
        moment, commit = parts
        local = [moment, f"g{commit[:COMMIT_DIGITS]}"]
    if dirty:
        local.append(DIRTY_SUFFIX.lstrip("."))
    return f"{RELEASE}+{'.'.join(local)}"


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
    stamp = read_stamp(base)
    if stamp:
        return format_stamp(stamp)
    return read_baked_version(base) or UNKNOWN_VERSION
