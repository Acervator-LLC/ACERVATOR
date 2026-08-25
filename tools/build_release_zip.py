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

  • PRIMARY    — live source, active docs, tests, sadp/, latest
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

sadp: R28 FL · R55 GOV · R62 FRG · R68 DPA · R76 DMW
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
#   *.log.scrubbed   — output of tools/scrub_gate_log_nulls.py
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
# release package if included. Operator audit 2026-05-31
# (docs/audits/2026-05-31_unused_files_audit.md) classified each item.

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
    # Cat 4 — old HOPs + dept review (superseded by HOP5 +
    # sadp/DEPARTMENT_LEADS.md)
    "ACERVATOR_HOP2.md",
    "ACERVATOR_HOP3.md",
    "ACERVATOR_HOP4.md",
    "ACERVATOR_DEPT_LEAD_REVIEW_v3_12_0.md",
    # Cat 5 — stale test/report artifacts
    "pytest_out.txt",
    "pytest_v3_16_48.txt",
    "TESTNET_POA_VERIFY_REPORT.md",
    # Cat 6 — zero-importer root scripts (orphan diagnostics +
    # superseded one-offs)
    "EXCHANGE_DIAGNOSTIC.py",
    "cartoon_screen.py",
    "download_archive.py",
    "generate_essay_ja.py",
    "generate_essay_localized.py",
    "investor_screen.py",
    "test_scrumming_v3.py",
    # Cat 7 — low-coupling promo (trailer chain). KEEP
    # generate_essay.py in PRIMARY — it builds the live product
    # manual. The trailer chain (splash + render) is dormant.
    "splash_screen.py",
    "render_trailer.py",
}

# Regex patterns: route to ADDITIONAL if matched. Used for historical
# product-manual PDFs — every version EXCEPT the latest.
ADDITIONAL_REGEXES = (
    # Older product-manual PDFs handled by the manual-version filter
    # below — listed here for documentation but matched in
    # `_is_older_manual()`.
)


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


# v3.23.20 — sadp/RAIntSimBat/reports/ defensive zip exclusion.
# Operator-approved 2026-06-16: route the reports archive to ADDITIONAL
# bucket so it doesn't bloat the primary release zip, EXCEPT historical-
# proof files cited verbatim by CHANGELOG / Chronicle / HOP. Those stay
# in PRIMARY for chain-of-evidence integrity.
_RAINTSIMBAT_REPORTS_REL = ("sadp", "RAIntSimBat", "reports")
RAINTSIMBAT_REPORTS_PRIMARY_KEEP = frozenset(
    {
        "RAIntSimBat_20260421_055850.json",  # HOP4/HOP5 cited
        "RAIntSimBat_RESULTS_20260427_183334.json",  # CHANGELOG + Chronicle cited
        "RAIntSimBat_RESULTS_20260428_095359.json",  # CHANGELOG cited
    }
)


def _is_raintsimbat_reports_archive(rel_path: Path) -> bool:
    """True if path is inside sadp/RAIntSimBat/reports/ AND not a cited
    historical-proof file."""
    parts = rel_path.parts
    if len(parts) < 4:
        return False
    if parts[:3] != _RAINTSIMBAT_REPORTS_REL:
        return False
    if rel_path.name in RAINTSIMBAT_REPORTS_PRIMARY_KEEP:
        return False
    return True


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
    if _is_older_manual(rel_path, latest_manual_name):
        return True
    # v3.23.20 — RAIntSimBat reports archive (except cited historical-proof)
    if _is_raintsimbat_reports_archive(rel_path):
        return True
    return False


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
# Backward-compat shim: old `should_include` API still used by tests
# from v3.20.35. Returns True for PRIMARY bucket only.
# ─────────────────────────────────────────────────────────────────────


def should_include(rel_path: Path, latest_manual_name: Optional[str]) -> bool:
    """Legacy API kept for v3.20.35-era test compatibility. Returns
    True iff the path lands in the PRIMARY bucket."""
    return classify_path(rel_path, latest_manual_name) == "primary"


# Legacy aliases — old field names still referenced by
# test_build_release_zip.py from v3.20.35.
EXCLUDE_DIRS = JUNK_DIRS
EXCLUDE_SUFFIXES = JUNK_SUFFIXES
EXCLUDE_BASENAMES = JUNK_BASENAMES


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


def read_session_number() -> int:
    """Try to read the session number from the latest MEM entry. Falls
    back to 27 (current session) if unparseable."""
    try:
        import json

        p = _REPO / "sadp" / "EPISODIC_MEMORY.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        sessions = [
            e.get("session")
            for e in data
            if isinstance(e, dict) and isinstance(e.get("session"), int)
        ]
        return max(sessions) if sessions else 27
    except (OSError, json.JSONDecodeError, ValueError):
        return 27


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
    dry_run: bool = False, primary_only: bool = False, additional_only: bool = False
) -> int:
    version = read_version()
    if version is None:
        print("ERROR: could not read version from src/__init__.py", file=sys.stderr)
        return 1

    session = read_session_number()
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

    print(f"\nPartition:")
    print(f"  PRIMARY:    {len(primary):>5,} files")
    print(f"  ADDITIONAL: {len(additional):>5,} files")
    print(f"  JUNK:       {len(junk):>5,} files (excluded from both)")

    if dry_run:
        # Show a few sample paths per bucket
        print("\n  PRIMARY sample (first 5):")
        for rel in primary[:5]:
            print(f"    {rel}")
        print(f"\n  ADDITIONAL sample (first 10):")
        for rel in sorted(additional)[:10]:
            print(f"    {rel}")
        if len(additional) > 10:
            print(f"    ... and {len(additional) - 10} more")
        print(f"\n(dry-run) Would write:")
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
    )


if __name__ == "__main__":
    raise SystemExit(main())
