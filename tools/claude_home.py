"""Find the Claude Code harness, wherever this machine keeps it.

`search_roots` states the one order every caller uses: user level, then `REPO`.
`find`, `hooks_dir`, `settings_file` and `skill_file` answer None when nothing
holds the path, and `absent_reason` names each `candidates` entry it tried.
`missing_hooks` separates a partial install from an absent one.
"""

from __future__ import annotations

from pathlib import Path

CLAUDE_DIR_NAME = ".claude"

REPO = Path(__file__).resolve().parent.parent

# `missing_hooks` reports a directory short of any of these as a partial install.
HOOK_NAMES: tuple[str, ...] = (
    "archetype_gate.py",
    "prompt_router.py",
    "session_stop_backstop.py",
    "verify_release_gate.py",
)


def search_roots() -> tuple[Path, ...]:
    """The `CLAUDE_DIR_NAME` directories to search, user level then `REPO`.

    `Path.home()` is read on every call, never captured at import.
    """
    return (Path.home() / CLAUDE_DIR_NAME, REPO / CLAUDE_DIR_NAME)


def candidates(*parts: str) -> tuple[Path, ...]:
    """Every path `parts` could occupy under `search_roots`, in search order.

    Returned whether or not any of them exists on disk.
    """
    return tuple(root.joinpath(*parts) for root in search_roots())


def find(*parts: str) -> Path | None:
    """The first `candidates` entry for `parts` that exists on disk, else None.

    `absent_reason` supplies the message that goes with a None.
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
    """The `HOOK_NAMES` entries that are not files under `hooks`.

    A non-empty list means the directory was found and is incomplete.
    """
    return [name for name in HOOK_NAMES if not (hooks / name).is_file()]
