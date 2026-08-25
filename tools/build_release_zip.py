"""
tools/build_release_zip.py — v3.20.36.

Build the release zip suite (PRIMARY + ADDITIONAL_ITEMS) with the
bloat-trim rules + archival-preservation discipline the operator
surfaced 2026-05-31:

  v3.20.35: only the LATEST `acervator_product_manual_v*.pdf` is
            included in the release zip (8.4 MB / 97 files
            excluded from the primary zip).
  v3.20.36: rather than DELETE the discardables, package them into
            a separate "Additional Items" zip. Primary stays lean
            and organized; nothing is lost.

Operator directive 2026-05-31:
    "Rather than delete from the package all together. Package hard
     delete items into Additional Items .zip to keep the primary
     package more organized. The conversation back up is large and
     important but not needed in the package."

Partition invariant
───────────────────
Every file in the repo is classified into exactly ONE of three
buckets:

  • PRIMARY    — live source, active docs, tests, latest
                 product manual. Lean release package.
  • ADDITIONAL — historical artifacts, archived backups, old
                 product manuals, stale reports, orphaned scripts.
                 Preserved for archival but not part of the lean
                 release.
  • JUNK       — __pycache__, .git, .pytest_cache, .hypothesis,
                 .mypy_cache, .ruff_cache, .venv, dist, build,
                 node_modules, .coverage, *.pyc, *.pyo, *.zip.
                 Excluded from both zips.

The partition is enforced by `classify_path(rel_path, latest_manual_name)`
which returns the bucket name. Every walked file produces exactly one
classification.

CLI
───
  python tools/build_release_zip.py          # build both zips
  python tools/build_release_zip.py --dry-run
                                             # list what would land
                                             #   in each bucket
  python tools/build_release_zip.py --primary-only
                                             # build only the primary zip
  python tools/build_release_zip.py --additional-only
                                             # build only the additional zip
  python tools/build_release_zip.py --print-latest-manual
  python tools/build_release_zip.py --session 28

The session number is MEASURED, never assumed. It comes from --session,
or from the highest-version release package beside the repository, and
the build prints which package it was read off. With neither source
the build REFUSES. A guessed session number already shipped two
packages as `session79`, and a wrongly named archive looks exactly
like a right one.
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

# ─────────────────────────────────────────────────────────────────────
# Classification rules
# ─────────────────────────────────────────────────────────────────────

# JUNK — excluded from BOTH zips (true bloat, machine-specific, or
# regenerable build artifacts).
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
    # v3.24.35 — agent worktree scratch. Measured on the v3.24.35
    # build: 1,414 of 1,901 primary-zip files (~30 MB) came from
    # .claude/worktrees, swamping the 487 files of actual project
    # content. Scratch, not deliverable.
    "worktrees",
}
JUNK_SUFFIXES = (".pyc", ".pyo", ".log", ".tmp")
# Exclude .coverage data file (machine-specific paths), but keep
# .coveragerc (the configuration file).
JUNK_BASENAMES = {".coverage"}

# v3.23.6 — additional name-substring blacklist for rotated/derived log
# artifacts that the suffix rule would miss:
#   *.log.scrubbed   — output of a gate-log scrubber
#   *.log.scrubbed.N — pre-replace scratch from the same tool
#   *.log.bak / *.log.bak.N — pre-scrub backups
#   *.log.[0-9]+   — rotated NDJSON files (gate.log.1, trade.log.2, etc.)
# These can grow large + machine-specific; never ship in any zip.
JUNK_NAME_SUBSTRINGS = (
    ".log.scrubbed",
    ".log.bak",
    # In-session backup files written before risky edits
    # (e.g. main_window.py.PRIVACY_ARC_BACKUP_2026-06-14,
    # bot_visualizer.py.BOT_SWARM_ARC_BACKUP_2026-06-14,
    # scrumming_bot.py.RECOVERY_PRE_v3_23_7.BAK,
    # history_tab.py.D01_BACKUP_2026-06-14).
    # These are scratch — never ship in any zip.
    ".PRIVACY_ARC_BACKUP_",
    ".BOT_SWARM_ARC_BACKUP_",
    ".RECOVERY_PRE_",
    ".D01_BACKUP_",
)
JUNK_ROTATED_LOG_RE = re.compile(r"\.log\.\d+$")

MANUAL_RE = re.compile(r"^acervator_product_manual_v(\d+)_(\d+)_(\d+)\.pdf$")

# ADDITIONAL — route to the supplementary zip rather than the primary.
# These are NOT junk (preserved for archival) but DO bloat the primary
# release package if included. An operator audit on 2026-05-31
# classified each item below.

# Top-level directories that go in their entirety to ADDITIONAL.
ADDITIONAL_DIRS = {
    ".session26_backups",  # 1.7 MB · session-26 .bak files
    "_archive",  # 2026-07-25 audit: all migrated content
}

# Top-level files that go to ADDITIONAL (exact-match by repo-relative
# string).
ADDITIONAL_FILES_EXACT = {
    # Cat 1 — conversation backup (62.9 MB)
    "ACERVATOR_DEV_1_BACKUP_2026-05-20.jsonl",
    # Cat 4 — old HOPs + dept review (superseded by HOP7)
    "ACERVATOR_HOP2.md",
    "ACERVATOR_HOP3.md",
    "ACERVATOR_HOP4.md",
    "ACERVATOR_DEPT_LEAD_REVIEW_v3_12_0.md",
    # Cat 5 — stale test/report artifacts
    "pytest_out.txt",
    "pytest_v3_16_48.txt",
    "TESTNET_POA_VERIFY_REPORT.md",
    # Cat 6 — zero-importer root scripts (orphan diagnostics +
    # superseded one-offs). EXCHANGE_DIAGNOSTIC.py moved to
    # tools/exchange_diagnostic.py and test_scrumming_v3.py became
    # tests/test_scrumming_scenarios.py, so neither is listed here.
    "cartoon_screen.py",
    "download_archive.py",
    "generate_essay_ja.py",
    "generate_essay_localized.py",
    "investor_screen.py",
    # Issue #74 extracted the animation core these three screens shared.
    # It travels with them: it has no other consumer, and splitting a
    # helper from every file that imports it across two zips would give
    # the PRIMARY zip a module nothing there calls.
    "screen_fx.py",
    # Issue #85 renamed `test_scrumming_v3.py` to
    # `tools/scrumming_v3_sim.py`. This set matches a repo-relative
    # string EXACTLY, so the old entry would have stopped matching in
    # silence and the file would have joined the PRIMARY zip with no
    # message. It joins the PRIMARY zip on purpose now: it is a tool in
    # `tools/`, and every other tool in that directory ships there.
    # Cat 7 — low-coupling promo (trailer chain). KEEP
    # generate_essay.py in PRIMARY — it builds the live product
    # manual. The trailer chain (splash + render) is dormant.
    "splash_screen.py",
    "render_trailer.py",
}


def _parse_manual_version(name: str) -> Optional[tuple[int, int, int]]:
    """Parse 'acervator_product_manual_v3_20_33.pdf' -> (3, 20, 33).
    Returns None if the name doesn't match the pattern."""
    m = MANUAL_RE.match(name)
    if not m:
        return None
    try:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def find_latest_manual(repo: Path = _REPO) -> Optional[Path]:
    """Return the Path of the highest-versioned product manual PDF
    in the repo root, or None if no manuals exist."""
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
    # v3.23.6 — rotated log files (.log.1 etc.) + scrubbed copies +
    # pre-scrub backups never ship in a release zip.
    name = rel_path.name
    for needle in JUNK_NAME_SUBSTRINGS:
        if needle in name:
            return True
    if JUNK_ROTATED_LOG_RE.search(name):
        return True
    return False


def _is_older_manual(rel_path: Path, latest_manual_name: Optional[str]) -> bool:
    """True if this is a product-manual PDF that ISN'T the latest
    version (routes to ADDITIONAL)."""
    if not MANUAL_RE.match(rel_path.name):
        return False
    if latest_manual_name is None:
        return False
    return rel_path.name != latest_manual_name


def _is_additional(rel_path: Path, latest_manual_name: Optional[str]) -> bool:
    """True if the path routes to the ADDITIONAL_ITEMS zip rather
    than the primary release zip. Junk filtering is checked BEFORE
    this in `classify_path` — so anything reaching here is genuinely
    archival, not bloat."""
    # Top-level directory match (e.g. .session26_backups/)
    if rel_path.parts and rel_path.parts[0] in ADDITIONAL_DIRS:
        return True
    # Exact filename match at any depth (these are all root-level
    # files but we don't constrain the depth in case a future
    # reorg moves them)
    if rel_path.name in ADDITIONAL_FILES_EXACT:
        return True
    # Historical product manual
    return _is_older_manual(rel_path, latest_manual_name)


def classify_path(rel_path: Path, latest_manual_name: Optional[str]) -> str:
    """Return 'junk', 'additional', or 'primary' for the given path.
    The partition is mutually exclusive: every file lands in exactly
    one bucket."""
    if _is_junk(rel_path):
        return "junk"
    if _is_additional(rel_path, latest_manual_name):
        return "additional"
    return "primary"


# ─────────────────────────────────────────────────────────────────────
# Build orchestration
# ─────────────────────────────────────────────────────────────────────


def read_version() -> Optional[str]:
    """Read src/__init__.py.__version__. Used to name the zip."""
    init = _REPO / "src" / "__init__.py"
    if not init.exists():
        return None
    m = re.search(
        r'__version__\s*=\s*"(\d+\.\d+\.\d+)"', init.read_text(encoding="utf-8")
    )
    return m.group(1) if m else None


PACKAGE_RE = re.compile(r"^acervator_session(\d+)_CLOSE_hop5_v(\d+)_(\d+)_(\d+)\.zip$")


def read_session_number(parent: Path) -> Optional[tuple[int, str]]:
    """Session number read off the newest release package beside the repo.

    Returns (session, evidence) where `evidence` names the package the
    number came from, or None when no package is there.

    The number comes from the package with the highest VERSION tuple, not
    the highest session number and never the directory name. Measured
    2026-08-16: session numbers on this disk do not rise with version, so
    `max(session)` picks a package from a different era and names the new
    drop after it.

    This replaced a reader of an episodic-memory file under the retired
    governance subsystem. That file is not in the tree, the read raised,
    and the except branch returned a hardcoded 27 with no output. Every
    build therefore produced a `session27` name whatever the truth was,
    and reported success.
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
    """Every ADDITIONAL routing rule that matched no file in this tree.

    A rule that matches nothing is invisible: the partition still prints a
    count and the build still succeeds. Six of these rules named paths that
    had been deleted, and no build said so. This makes each one visible on
    every run without dropping a rule that may fire again.
    """
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
    """Walk the repo and partition every file into
    (primary, additional, junk). Same walk pass for all three lists
    so the partition is provably mutually exclusive."""
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
        print("ERROR: could not read version from src/__init__.py", file=sys.stderr)
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
