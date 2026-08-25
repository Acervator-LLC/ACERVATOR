"""Move the harness to a new repository. A SCRIPT, not a checklist.

Why this exists. HOP6 told a human to copy `.claude/`, copy the memory entries
and copy `tools/queue_state.py`. None of it happened, and the new instance came
up with no gate, no skills, no hooks and no durable rulings — the exact failure
this project already measured once: BLOCKING MECHANISMS BIND, PROSE DOES NOT.
A migration written as prose is prose.

Run from the OLD tree, which has everything:

    python -m tools.migrate_harness --to "C:/path/to/new/repo"
    python -m tools.migrate_harness --to "C:/path/to/new/repo" --apply

Without --apply it reports what it WOULD do and changes nothing.

It does NOT run the archetypes itself; it prints the two commands whose exit
codes prove the gate is live, because a migration tool asserting its own success
is the same self-reported verdict this repo refuses everywhere else.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
CLAUDE_PROJECTS = pathlib.Path.home() / ".claude" / "projects"

# tools/ files that are NOT reachable by `island promote` and so never travel
# on their own. Add to this list rather than remembering them.
LOOSE_TOOLS = (
    "queue_state.py",
    "island.py",
    "touchset.py",
    "emitter_registry_check.py",
    "migrate_harness.py",
)

# (file, exact text to find, replacement, why)
PATCHES = (
    (
        "tools/island.py",
        're.compile(r"^ISLANDS_ROOT = Path\\(", re.M)',
        None,
        "ISLANDS_ROOT is a hardcoded absolute path to the old machine's "
        "scratchpad. Islands will fork to the wrong place.",
    ),
    (
        "tools/migrate_stone_tablets.py",
        None,
        None,
        "carries an absolute Desktop path to a different session directory.",
    ),
)


def project_key(repo: pathlib.Path) -> str:
    """Reproduce Claude Code's project-directory key for a repo path.

    Measured against this repo's own key: drive letter, then '--', then every
    path segment joined by '-', with spaces and underscores also becoming '-'.
    """
    resolved = repo.resolve()
    drive = resolved.drive.rstrip(":") or "C"
    parts = [p for p in resolved.parts[1:] if p not in ("\\", "/")]
    joined = "-".join(parts)
    joined = re.sub(r"[ _]", "-", joined)
    return f"{drive}--{joined}"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# Under .claude/ only `skills`, `hooks` and the root settings files are the
# harness. `worktrees` measured 10,909 files and 562 MB of build junk on
# 2026-08-16 and a naive rglob would have copied all of it.
SKIP_PARTS = {
    "worktrees",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "history",
    "shell-snapshots",
    "todos",
    "statsig",
    "logs",
}


def copy_tree(src: pathlib.Path, dst: pathlib.Path, apply: bool) -> tuple[int, int]:
    """Copy every file under src into dst. Returns (copied, identical)."""
    copied = identical = 0
    if not src.is_dir():
        return 0, 0
    for path in sorted(src.rglob("*")):
        if not path.is_file() or SKIP_PARTS & set(path.parts):
            continue
        target = dst / path.relative_to(src)
        if target.is_file() and sha(target) == sha(path):
            identical += 1
            continue
        copied += 1
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return copied, identical


def report_absolute_paths(repo: pathlib.Path) -> list[str]:
    """Find hardcoded absolute paths that will not work in the new tree."""
    hits: list[str] = []
    tools = repo / "tools"
    if not tools.is_dir():
        return hits
    for path in sorted(tools.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if re.search(r"[A-Za-z]:[\\/]{1,2}Users", line):
                rel = path.relative_to(repo).as_posix()
                hits.append(f"{rel}:{number}: {line.strip()[:88]}")
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--to", required=True, help="the new repository root")
    parser.add_argument(
        "--apply", action="store_true", help="actually copy; without it, report only"
    )
    args = parser.parse_args()

    target = pathlib.Path(args.to).expanduser()
    if not target.is_dir():
        print(f"REFUSED: target is not a directory: {target}")
        return 2
    if target.resolve() == HERE.resolve():
        print("REFUSED: target is the source tree.")
        return 2

    mode = "APPLYING" if args.apply else "DRY RUN — nothing will be written"
    print(f"{mode}\n  from {HERE}\n    to {target}\n")

    # 1. .claude/ — the harness itself
    n, same = copy_tree(HERE / ".claude", target / ".claude", args.apply)
    print(f"1. .claude/            {n:>4} to copy, {same:>4} already identical")
    skills = len(list((HERE / ".claude" / "skills").glob("*/SKILL.md")))
    hooks = len(list((HERE / ".claude" / "hooks").glob("*.py")))
    print(f"                       {skills} skills, {hooks} hooks")

    # 2. loose tools that promote never moves
    moved = []
    for name in LOOSE_TOOLS:
        src = HERE / "tools" / name
        dst = target / "tools" / name
        if not src.is_file():
            continue
        if dst.is_file() and sha(dst) == sha(src):
            continue
        moved.append(name)
        if args.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    print(f"2. loose tools         {len(moved):>4} to copy  {moved if moved else ''}")

    # 3. memory — keyed to the project path, so it never travels by itself
    src_mem = CLAUDE_PROJECTS / project_key(HERE) / "memory"
    dst_mem = CLAUDE_PROJECTS / project_key(target) / "memory"
    n_mem, same_mem = copy_tree(src_mem, dst_mem, args.apply)
    print(f"3. memory entries      {n_mem:>4} to copy, {same_mem:>4} already identical")
    print(f"                       from {src_mem}")
    print(f"                         to {dst_mem}")
    if not src_mem.is_dir():
        print("                       SOURCE MEMORY DIR NOT FOUND — check the key")

    # 4. absolute paths that will not work in the new tree
    print("\n4. hardcoded absolute paths still present in the SOURCE tools/:")
    hits = report_absolute_paths(HERE)
    for hit in hits:
        print(f"     {hit}")
    if not hits:
        print("     none")
    print("   These are NOT auto-patched. Each needs a deliberate replacement,")
    print("   and island.py's ISLANDS_ROOT is the one that matters — island")
    print("   discipline is mandatory and it currently forks to the old machine.")

    # 5. what proves it worked. Not asserted here; run it.
    print("\n5. VERIFY. Run these IN THE NEW REPO. This tool does not grade itself.")
    print("   Both are required: a gate that always fails is as useless as one")
    print("   that always passes.\n")
    fixtures = "docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures"
    print(f"   python -m tools.harness.coding_archetype {fixtures}/known_bad.py")
    print("     -> MUST exit 1, passed=False. Exit 0 means nothing is checked.")
    print(f"   python -m tools.harness.coding_archetype {fixtures}/known_good.py")
    print("     -> MUST exit 0, passed=True.")
    print("   python -m tools.harness.check_release_readiness")
    print("     -> MUST print [OK]. Run it DETACHED, read the exit code from a")
    print("        FILE, never through a pipe.")
    print("\n   Then edit any file and confirm an [archetype-gate] line appears.")
    print("   If it does not, .claude/hooks/ is not registered and the instance")
    print("   is running unpoliced no matter what it has read.")

    if not args.apply:
        print("\nDRY RUN. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
