"""Build the primary release zip and the additional-items zip beside the repo.

`classify_path` puts every walked file in exactly one bucket: `primary`,
`additional` or `junk`. `find_latest_manual` keeps one product manual in the
primary zip and routes the rest to additional. `read_version` and
`read_session_number` name the two archives, and `build` refuses when either
answers nothing.

    python -m tools.build_release_zip --dry-run
    python -m tools.build_release_zip --session 28
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Optional

_REPO = Path(__file__).resolve().parent.parent

JUNK_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".hypothesis",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "worktrees",
    "quarantine",
}
JUNK_SUFFIXES = (".pyc", ".pyo", ".log", ".tmp")
# `.coveragerc` is not matched: only the data file `.coverage` is junk.
JUNK_BASENAMES = {".coverage"}

# Derived log and backup names that `JUNK_SUFFIXES` cannot reach.
JUNK_NAME_SUBSTRINGS = (
    ".log.scrubbed",
    ".log.bak",
    ".PRIVACY_ARC_BACKUP_",
    ".BOT_SWARM_ARC_BACKUP_",
    ".RECOVERY_PRE_",
    ".D01_BACKUP_",
)
JUNK_ROTATED_LOG_RE = re.compile(r"\.log\.\d+$")

MANUAL_RE = re.compile(r"^acervator_product_manual_v(\d+)_(\d+)_(\d+)\.pdf$")

# Top-level directories routed whole to the additional zip.
ADDITIONAL_DIRS = {
    ".session26_backups",
    "_archive",
}

# Matched on basename at any depth by `_is_additional`.
ADDITIONAL_FILES_EXACT: set[str] = set()


def _parse_manual_version(name: str) -> Optional[tuple[int, int, int]]:
    """The (major, minor, patch) `MANUAL_RE` reads out of `name`, or None."""
    m = MANUAL_RE.match(name)
    if not m:
        return None
    try:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def find_latest_manual(repo: Path = _REPO) -> Optional[Path]:
    """The highest-versioned manual PDF directly under `repo`, or None."""
    best: Optional[tuple[tuple[int, int, int], Path]] = None
    for p in repo.iterdir():
        if not p.is_file():
            continue
        v = _parse_manual_version(p.name)
        if v is None:
            continue
        if best is None or v > best[0]:
            best = (v, p)
    return best[1] if best else None


def _is_junk(rel_path: Path) -> bool:
    """True if the path should be excluded from BOTH zips."""
    for part in rel_path.parts:
        if part in JUNK_DIRS:
            return True
    if rel_path.suffix in JUNK_SUFFIXES:
        return True
    if rel_path.name in JUNK_BASENAMES:
        return True
    if rel_path.suffix == ".zip":
        return True
    name = rel_path.name
    for needle in JUNK_NAME_SUBSTRINGS:
        if needle in name:
            return True
    if JUNK_ROTATED_LOG_RE.search(name):
        return True
    return False


def _is_older_manual(rel_path: Path, latest_manual_name: Optional[str]) -> bool:
    """True when `rel_path` is a manual PDF other than `latest_manual_name`."""
    if not MANUAL_RE.match(rel_path.name):
        return False
    if latest_manual_name is None:
        return False
    return rel_path.name != latest_manual_name


def _is_additional(rel_path: Path, latest_manual_name: Optional[str]) -> bool:
    """True when `rel_path` matches `ADDITIONAL_DIRS`, `ADDITIONAL_FILES_EXACT`
    or `_is_older_manual`.

    `classify_path` applies `_is_junk` first, so junk never reaches here.
    """
    if rel_path.parts and rel_path.parts[0] in ADDITIONAL_DIRS:
        return True
    if rel_path.name in ADDITIONAL_FILES_EXACT:
        return True
    return _is_older_manual(rel_path, latest_manual_name)


def classify_path(rel_path: Path, latest_manual_name: Optional[str]) -> str:
    """The one bucket for `rel_path`: 'junk', 'additional' or 'primary'."""
    if _is_junk(rel_path):
        return "junk"
    if _is_additional(rel_path, latest_manual_name):
        return "additional"
    return "primary"


def read_version() -> Optional[str]:
    """What `resolve_version` answers for this tree, or None for `UNKNOWN_VERSION`.

    A tree on no version tag resolves to the commit it was built from.
    """
    if str(_REPO) not in sys.path:
        sys.path.insert(0, str(_REPO))
    from src._version import UNKNOWN_VERSION, resolve_version

    version = resolve_version(_REPO)
    return None if version == UNKNOWN_VERSION else version


PACKAGE_RE = re.compile(r"^acervator_session(\d+)_CLOSE_hop5_v(\d+)_(\d+)_(\d+)\.zip$")


def read_session_number(parent: Path) -> Optional[tuple[int, str]]:
    """(session, evidence) from the `PACKAGE_RE` file in `parent` with the
    highest version tuple, or None.

    `evidence` names that file; the session number itself is never ordered on.
    """
    best: Optional[tuple[tuple[int, int, int], int, str]] = None
    if not parent.is_dir():
        return None
    for entry in sorted(parent.iterdir()):
        if not entry.is_file():
            continue
        m = PACKAGE_RE.match(entry.name)
        if m is None:
            continue
        version = (int(m.group(2)), int(m.group(3)), int(m.group(4)))
        if best is None or version > best[0]:
            best = (version, int(m.group(1)), entry.name)
    return (best[1], best[2]) if best else None


def unmatched_rules(primary: list[Path], additional: list[Path]) -> list[str]:
    """Every `ADDITIONAL_DIRS` and `ADDITIONAL_FILES_EXACT` entry that matched
    nothing in `primary` or `additional`."""
    seen = {rel.as_posix() for rel in primary + additional}
    tops = {rel.parts[0] for rel in primary + additional if rel.parts}
    names = {rel.name for rel in primary + additional}
    stale = [f"dir  {d}" for d in sorted(ADDITIONAL_DIRS) if d not in tops]
    stale += [
        f"file {f}"
        for f in sorted(ADDITIONAL_FILES_EXACT)
        if f not in names and f not in seen
    ]
    return stale


def _walk_and_partition(
    latest_name: Optional[str],
) -> tuple[list[Path], list[Path], list[Path]]:
    """Every file under `_REPO` split by `classify_path` into
    (primary, additional, junk)."""
    primary: list[Path] = []
    additional: list[Path] = []
    junk: list[Path] = []
    for p in _REPO.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(_REPO)
        bucket = classify_path(rel, latest_name)
        if bucket == "primary":
            primary.append(rel)
        elif bucket == "additional":
            additional.append(rel)
        else:
            junk.append(rel)
    return primary, additional, junk


def _write_zip(out_path: Path, arc_root: str, files: list[Path]) -> tuple[int, float]:
    """Write the zip and return (total_src_bytes, elapsed_seconds)."""
    t0 = time.time()
    total_src_bytes = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel in files:
            full = _REPO / rel
            arcname = str(Path(arc_root) / rel)
            zf.write(full, arcname=arcname)
            total_src_bytes += full.stat().st_size
    return total_src_bytes, time.time() - t0


def build(
    *,
    dry_run: bool = False,
    primary_only: bool = False,
    additional_only: bool = False,
    session: Optional[int] = None,
) -> int:
    version = read_version()
    if version is None:
        print(
            "ERROR: this tree resolves no version - no reachable v* git tag "
            "and no baked version file. Cannot name the package.",
            file=sys.stderr,
        )
        return 1

    if session is not None:
        print(f"Session {session} (given with --session)")
    else:
        measured = read_session_number(_REPO.parent)
        if measured is None:
            print("REFUSED: no session number.", file=sys.stderr)
            print(
                f"No release package beside {_REPO.parent} to read it off,",
                file=sys.stderr,
            )
            print(
                "and the directory name is not evidence. Pass --session N.",
                file=sys.stderr,
            )
            return 1
        session, evidence = measured
        print(f"Session {session} (read off {evidence})")

    version_us = version.replace(".", "_")
    base = f"acervator_session{session}_CLOSE_hop5_v{version_us}"
    primary_path = _REPO.parent / f"{base}.zip"
    additional_path = _REPO.parent / f"{base}_additional_items.zip"

    latest_manual = find_latest_manual(_REPO)
    latest_name = latest_manual.name if latest_manual else None
    if latest_name:
        print(f"Latest manual: {latest_name}")
    else:
        print("No product manual PDFs found in repo root.")

    primary, additional, junk = _walk_and_partition(latest_name)

    stale = unmatched_rules(primary, additional)
    if stale:
        print(f"\nADDITIONAL rules that matched nothing ({len(stale)}):")
        for rule in stale:
            print(f"  {rule}")
        print("  Each names a path that is not in this tree. Harmless to the")
        print("  zip, but it is a rule nobody is maintaining. Delete it or")
        print("  restore the file.")

    print("\nPartition:")
    print(f"  PRIMARY:    {len(primary):>5,} files")
    print(f"  ADDITIONAL: {len(additional):>5,} files")
    print(f"  JUNK:       {len(junk):>5,} files (excluded from both)")

    if dry_run:
        # Show a few sample paths per bucket
        print("\n  PRIMARY sample (first 5):")
        for rel in primary[:5]:
            print(f"    {rel}")
        print("\n  ADDITIONAL sample (first 10):")
        for rel in sorted(additional)[:10]:
            print(f"    {rel}")
        if len(additional) > 10:
            print(f"    ... and {len(additional) - 10} more")
        print("\n(dry-run) Would write:")
        if not additional_only:
            print(f"  {primary_path}")
        if not primary_only:
            print(f"  {additional_path}")
        return 0

    # PRIMARY zip
    if not additional_only:
        bytes_p, elapsed_p = _write_zip(primary_path, base, primary)
        size_mb = primary_path.stat().st_size / (1024 * 1024)
        print(f"\nBuilt PRIMARY:    {primary_path}")
        print(f"  files:         {len(primary):,}")
        print(f"  source bytes:  {bytes_p:,}")
        print(f"  zip size:      {size_mb:.2f} MB")
        print(f"  elapsed:       {elapsed_p:.1f}s")

    # ADDITIONAL zip
    if not primary_only:
        if not additional:
            print("\n(no ADDITIONAL items — skipping supplementary zip)")
        else:
            arc_root_add = f"{base}_additional_items"
            bytes_a, elapsed_a = _write_zip(additional_path, arc_root_add, additional)
            size_mb = additional_path.stat().st_size / (1024 * 1024)
            print(f"\nBuilt ADDITIONAL: {additional_path}")
            print(f"  files:         {len(additional):,}")
            print(f"  source bytes:  {bytes_a:,}")
            print(f"  zip size:      {size_mb:.2f} MB")
            print(f"  elapsed:       {elapsed_a:.1f}s")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the v{VERSION} release zip suite (PRIMARY + "
            "ADDITIONAL_ITEMS). Primary stays lean; supplementary "
            "preserves archival material without bloating it."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List partition counts + samples without writing zips",
    )
    parser.add_argument(
        "--primary-only", action="store_true", help="Build only the primary release zip"
    )
    parser.add_argument(
        "--additional-only",
        action="store_true",
        help="Build only the additional-items zip",
    )
    parser.add_argument(
        "--session",
        type=int,
        default=None,
        help="Session number for the package name. Without it the number "
        "is read off the highest-version package beside the repo, and "
        "the build refuses when there is none.",
    )
    parser.add_argument(
        "--print-latest-manual",
        action="store_true",
        help="Print the filename of the latest manual that would be "
        "kept in the primary zip, then exit 0",
    )
    args = parser.parse_args(argv)

    if args.print_latest_manual:
        m = find_latest_manual(_REPO)
        print(m.name if m else "<none>")
        return 0

    return build(
        dry_run=args.dry_run,
        primary_only=args.primary_only,
        additional_only=args.additional_only,
        session=args.session,
    )


if __name__ == "__main__":
    raise SystemExit(main())
