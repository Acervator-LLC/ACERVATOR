"""Move the harness to a new repository. A SCRIPT, not a checklist.

Why this exists. HOP6 told a human to copy the harness directory, copy the
memory entries and copy `tools/queue_state.py`. None of it happened, and the
new instance came up with no gate, no skills, no hooks and no durable rulings
— the exact failure this project already measured once: BLOCKING MECHANISMS
BIND, PROSE DOES NOT. A migration written as prose is prose.

Where the harness is — 2026-08-25. It moved to user level at the CTO's
request, so the source is no longer inside this tree. Step 1 resolves it
through `tools.claude_home`, user level first and then the repository. Before
that repair the source directory did not exist, `copy_tree` answered (0, 0),
and this tool printed "0 to copy" over "0 skills, 0 hooks" and returned 0. A
migration that carries nothing and reports success is the precise failure the
paragraph above exists to end, so an unresolvable harness is now REFUSED.

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
import json
import pathlib
import re
import shutil
import sys

from tools import claude_home

HERE = pathlib.Path(__file__).resolve().parent.parent
CLAUDE_PROJECTS = pathlib.Path.home() / claude_home.CLAUDE_DIR_NAME / "projects"

# Repo-relative files that live OUTSIDE the harness directory and so are not
# carried by step 1. Add to this list rather than remembering them. Issue #84
# moved touchset out of tools/, so these are whole paths, not bare names.
#
# `tools/island.py` left this list under issue #67, which deleted the file.
# A missing source is REFUSED by name below, so a stale entry here would
# have stopped every migration outright.
#
# `tools/claude_home.py` joined on 2026-08-25. It is what the hook tests and
# step 1 below use to FIND the harness, so a tree without it cannot resolve
# the harness at all.
#
# `tools/emitter_registry_check.py` left this list with the pin system, which
# deleted the file. The same refusal below applies: a stale entry here stops
# every migration outright.
LOOSE_TOOLS = (
    "tools/queue_state.py",
    "dev_harness/touchset.py",
    "tools/claude_home.py",
    "tools/migrate_harness.py",
)

# Step 4 measures absolute paths. It replaced a hand-kept PATCHES table
# that named two files and one regex and was read by no code path. One
# of the two files was a one-shot migration script, deleted under issue
# #83 once its migration was shown to have run. A list of known-bad
# paths that nothing consults is a checklist wearing a script's clothes,
# which is the failure this whole file exists to end.
# `report_absolute_paths` MEASURES the same fault over every tool in the
# tree, so it cannot name a file that is no longer there.


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


# Inside the harness directory only `skills`, `hooks` and the root settings
# files are the harness. `worktrees` measured 10,909 files and 562 MB of build
# junk on 2026-08-16 and a naive rglob would have copied all of it.
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

# The two subdirectories that ARE the harness. Named positively rather than
# by growing SKIP_PARTS, because the user-level directory holds whatever
# Claude Code decides to keep there. Measured 2026-08-25: the resolved
# source held 4538 files, of which 4363 were per-project transcripts under
# `projects/`. Step 3 already carries the memory entries, keyed to the
# project path, so a deny list would have to be extended on every release
# of the tool that writes them.
HARNESS_SUBDIRS = ("skills", "hooks")

# Root-level files that configure the harness. Depth 1 only.
HARNESS_ROOT_GLOB = "*.json"


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


def copy_harness(src: pathlib.Path, dst: pathlib.Path, apply: bool) -> tuple[int, int]:
    """Copy the harness parts of `src` into `dst`. Returns (copied, same).

    Only `HARNESS_SUBDIRS` and the root-level settings files travel. The
    user-level directory also holds transcripts, caches and per-project
    state that belong to Claude Code rather than to this project.
    """
    copied = identical = 0
    for name in HARNESS_SUBDIRS:
        part_copied, part_same = copy_tree(src / name, dst / name, apply)
        copied += part_copied
        identical += part_same
    for path in sorted(src.glob(HARNESS_ROOT_GLOB)):
        if not path.is_file():
            continue
        target = dst / path.name
        if target.is_file() and sha(target) == sha(path):
            identical += 1
            continue
        copied += 1
        if apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return copied, identical


def report_settings_absolute_paths(source: pathlib.Path) -> list[str]:
    """Hook commands in the settings files that name an absolute path.

    The move to user level rewrote every command to an absolute path on
    THIS machine. Carried to another machine they resolve to nothing, and
    a hook that cannot be found fails open in silence. This measures the
    same fault `report_absolute_paths` measures over `tools/`.
    """
    hits: list[str] = []
    for path in sorted(source.glob(HARNESS_ROOT_GLOB)):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(body, dict):
            continue
        for event, entries in (body.get("hooks") or {}).items():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    command = hook.get("command", "")
                    if re.search(r"[A-Za-z]:[\\/]", command):
                        hits.append(f"{path.name} {event}: {command}")
    return hits


def report_absolute_paths(repo: pathlib.Path) -> list[str]:
    """Find hardcoded absolute paths that will not work in the new tree."""
    tools = repo / "tools"
    if not tools.is_dir():
        message = f"no tools directory under {repo}"
        raise FileNotFoundError(message)
    hits: list[str] = []
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

    absent = [n for n in LOOSE_TOOLS if not (HERE / n).is_file()]
    if absent:
        print(
            f"REFUSED: LOOSE_TOOLS names {len(absent)} file(s) that are "
            f"not in the source tree: {absent}"
        )
        print("Each one would travel nowhere while this tool still printed")
        print("a count and returned 0. Fix the list or restore the file.")
        return 3

    mode = "APPLYING" if args.apply else "DRY RUN — nothing will be written"
    print(f"{mode}\n  from {HERE}\n    to {target}\n")

    # 1. the harness itself, from wherever this machine keeps it.
    #
    # The source used to be `HERE / <dirname>` and nothing else. After the
    # move to user level that directory was gone, copy_tree answered (0, 0)
    # for a missing source, and the tool reported a successful migration
    # that carried no hook and no skill. Both the resolution and the refusal
    # below exist because of that.
    source = claude_home.find()
    if source is None:
        print(
            "REFUSED: no harness directory found. Searched, in order: "
            + ", ".join(str(c) for c in claude_home.candidates())
        )
        print("Nothing would travel and this tool would still return 0.")
        return 4

    skills = len(list((source / "skills").glob("*/SKILL.md")))
    hooks = len(list((source / "hooks").glob("*.py")))
    if not skills or not hooks:
        print(f"REFUSED: {source} holds {skills} skills and {hooks} hooks.")
        print("A harness short of either half is not worth carrying, and a")
        print("count of zero printed under a success line reads as a pass.")
        return 5

    destination = target / claude_home.CLAUDE_DIR_NAME
    n, same = copy_harness(source, destination, args.apply)
    print(f"1. harness directory   {n:>4} to copy, {same:>4} already identical")
    print(f"                       {skills} skills, {hooks} hooks")
    print(f"                       from {source}")
    print(f"                         to {destination}")
    if source == pathlib.Path.home() / claude_home.CLAUDE_DIR_NAME:
        print("                       NOTE: the source is the USER-level")
        print("                       harness, which already fires on every")
        print("                       project on this machine, the target")
        print("                       included. This copy is for a DIFFERENT")
        print("                       machine, or for a project that is to")
        print("                       carry its own. Delete it otherwise:")
        print("                       two harnesses both fire.")

    # 2. loose tools that live outside the harness directory.
    #
    # A missing source used to `continue`. Issue #84 moved touchset.py out
    # of tools/, and under that skip the migration would have dropped it
    # for ever while still printing a count and returning 0. A tool that
    # does nothing and reports success is worse than one that crashes, so
    # a missing source is now REFUSED by name.
    moved = []
    for name in LOOSE_TOOLS:
        src = HERE / name
        dst = target / name
        if dst.is_file() and sha(dst) == sha(src):
            continue
        moved.append(name)
        if args.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    print(f"2. loose tools         {len(moved):>4} to copy  " f"{moved or ''}")

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
    print("\n   hook commands in the settings files that name an absolute path:")
    wired = report_settings_absolute_paths(source)
    for hit in wired:
        print(f"     {hit}")
    if not wired:
        print("     none")
    else:
        print("   Each one points at THIS machine. On another machine the")
        print("   hook is not found and Claude Code fails open in silence,")
        print("   which is a harness that reports nothing and blocks nothing.")
    print("   These are NOT auto-patched. Each needs a deliberate")
    print("   replacement. The list above IS the finding: an empty list")
    print("   means every tool derives its paths at run time, and a")
    print("   non-empty one names each site that would point at the old")
    print("   machine after the move.")

    # 5. what proves it worked. Not asserted here; run it.
    print("\n5. VERIFY. Run these IN THE NEW REPO. This tool does not grade itself.")
    print("   Both are required: a gate that always fails is as useless as one")
    print("   that always passes.\n")
    fixtures = "docs/audits/2026-07-24_coding_archetype_multi_agent_test/fixtures"
    print(f"   python -m dev_harness.harness.coding_archetype {fixtures}/known_bad.py")
    print("     -> MUST exit 1, passed=False. Exit 0 means nothing is checked.")
    print(f"   python -m dev_harness.harness.coding_archetype {fixtures}/known_good.py")
    print("     -> MUST exit 0, passed=True.")
    print("   python -m dev_harness.harness.check_release_readiness")
    print("     -> MUST print [OK]. Run it DETACHED, read the exit code from a")
    print("        FILE, never through a pipe.")
    print("\n   Then edit any file and confirm an [archetype-gate] line appears.")
    print("   If it does not, the hooks are not registered and the instance")
    print("   is running unpoliced no matter what it has read.")

    if not args.apply:
        print("\nDRY RUN. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
