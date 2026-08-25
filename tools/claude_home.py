"""Find the Claude Code harness, wherever this machine keeps it.

WHY THIS EXISTS
===============
The harness directory moved out of the repository on 2026-08-25 at the
CTO's request. Hooks and skills now live under the user's home
directory, and the directory name is in `.gitignore`, so a clone
carries neither. Five repository files still resolved the harness as
`<repo>/<dirname>/...`. One of them imported a hook at module scope, so
the release gate went red during COLLECTION and nothing could be
pushed.

Repairing each caller with its own copy of the search would put five
independent opinions in the tree about where the harness lives. This
module states the search ONCE, so a caller cannot state a different
one.

SEARCH ORDER
============
User level first, then the repository. That is not a new order: it is
the order `_skill_exists` in the prompt-router hook already uses, and
the reason it uses it is that a project which still carries its own
harness directory must keep working. Any other order here would mean
the tests measure a resolution the hooks do not perform.

NO MACHINE IS NAMED
===================
Nothing here holds a user name, a drive or an absolute path.
`Path.home()` is read on every call rather than captured at import, so
a caller can point HOME at an empty directory and observe the ABSENT
case. That is what makes the absent branch testable instead of
theoretical.
"""
from __future__ import annotations

from pathlib import Path

# The harness directory's name. Held as a constant because writing the
# literal into a docstring or a message makes it a repo-relative path
# citation that no longer resolves, which the hallucination rule reads
# as a dead reference.
CLAUDE_DIR_NAME = ".claude"

REPO = Path(__file__).resolve().parent.parent

# Every hook the repository pins. A directory that exists but is short
# of one of these is a PARTIAL install, which is a defect rather than an
# absence, and the tests treat the two differently.
HOOK_NAMES: tuple[str, ...] = (
    "archetype_gate.py",
    "prompt_router.py",
    "session_stop_backstop.py",
    "verify_release_gate.py",
)


def search_roots() -> tuple[Path, ...]:
    """The harness directories to search, user level first.

    Read fresh on every call. A module-level tuple would freeze whatever
    HOME held at import time and make the absent case unreachable from a
    test.
    """
    return (Path.home() / CLAUDE_DIR_NAME, REPO / CLAUDE_DIR_NAME)


def candidates(*parts: str) -> tuple[Path, ...]:
    """Every path `parts` could occupy, in search order.

    Returned even when none exists, because a failure message that names
    only the target teaches nothing; one that names the places searched
    tells the reader what to install and where.
    """
    return tuple(root.joinpath(*parts) for root in search_roots())


def find(*parts: str) -> Path | None:
    """The first candidate for `parts` that exists on disk, else None.

    None is a real answer, not an error. A fresh clone on a machine with
    no harness installed gets None, and the caller decides what that
    means. See `absent_reason` for the message that goes with it.
    """
    for candidate in candidates(*parts):
        if candidate.exists():
            return candidate
    return None


def absent_reason(*parts: str) -> str:
    """Why `parts` was not found, naming every path that was tried."""
    tried = ", ".join(str(candidate) for candidate in candidates(*parts))
    wanted = "/".join((CLAUDE_DIR_NAME, *parts))
    return (
        f"the Claude harness is not installed on this machine: no "
        f"{wanted} was found. Searched, in order: {tried}. "
        f"These tests pin harness behaviour, so they have nothing to "
        f"measure until the harness is present."
    )


def hooks_dir() -> Path | None:
    """The directory holding the hook scripts, or None."""
    return find("hooks")


def settings_file() -> Path | None:
    """The settings file that wires the hooks up, or None."""
    return find("settings.json")


def skill_file(slug: str) -> Path | None:
    """The SKILL.md for `slug`, or None."""
    return find("skills", slug, "SKILL.md")


def missing_hooks(hooks: Path) -> list[str]:
    """The names from HOOK_NAMES that are not files under `hooks`.

    A non-empty list means the harness directory was found but is
    incomplete. That is the silently-skipped-check failure this
    repository keeps meeting, so a caller must FAIL on it rather than
    skip.
    """
    return [name for name in HOOK_NAMES if not (hooks / name).is_file()]
