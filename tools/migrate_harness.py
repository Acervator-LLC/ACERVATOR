"""Copy the Claude harness, the LOOSE_TOOLS files and the memory to a new repo.

`claude_home.find` resolves the source, user level first, and the run REFUSES
when it answers None or when the directory holds no skill or no hook.
`copy_harness` carries only `HARNESS_SUBDIRS` and `HARNESS_ROOT_GLOB`.
`report_absolute_paths` names every machine-specific path it finds, and nothing
is written without `--apply`.

    python -m tools.migrate_harness --to <path> --apply
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

# Repo-relative paths outside the harness directory. An entry naming a file
# that is not in the source tree REFUSES the whole migration.
LOOSE_TOOLS = (
    "tools/queue_state.py",
    "dev_harness/touchset.py",
    "tools/claude_home.py",
    "tools/migrate_harness.py",
)


def project_key(repo: pathlib.Path) -> str:
    """Reproduce Claude Code's project-directory key for `repo`.

    `project_key` joins the drive, '--' and the path segments with '-', and
    turns each space and underscore into '-' as well.
    """
    resolved = repo.resolve()
    drive = resolved.drive.rstrip(":") or "C"
    parts = [p for p in resolved.parts[1:] if p not in ("\\", "/")]
    joined = "-".join(parts)
    joined = re.sub(r"[ _]", "-", joined)
    return f"{drive}--{joined}"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# Directory names `copy_tree` never descends into.
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

# The only subdirectories `copy_harness` carries; everything else is left.
HARNESS_SUBDIRS = ("skills", "hooks")

# Depth 1 only, so no nested json travels.
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
    """Copy the `HARNESS_SUBDIRS` and `HARNESS_ROOT_GLOB` parts of `src` into `dst`.

    Returns (copied, identical), as `copy_tree` does.
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

    `report_absolute_paths` measures the same fault over `tools/`.
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
