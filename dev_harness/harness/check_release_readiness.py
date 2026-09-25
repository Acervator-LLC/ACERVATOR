"""Release-readiness gate — must print `[OK] Release-ready (vX.Y.Z, N tests)`
on a clean tree before any banner-bump cascade.

What it runs:
  1. pytest suite (tests/) — must be all-green
  2. Each archetype self-check (coding, gui, docs) against its
     `known_good` fixture — must all pass with `passed=true`
  3. Claim ledger check — must have zero `open` claims

Output on success:
  writes sidecar `.release_ready.json` with {version, tests, timestamp}
  prints [OK] Release-ready (v3.23.20, 36 tests)
  exit 0

Output on failure:
  prints [FAIL] with the specific failure
  exit 1 (or 2 on infrastructure error)

This replaces the deleted `packaging/sadp/src/sadp/_tools/check_release_readiness.py`.
The sidecar path also changed: `.release_ready.json` at repo root, not
`.sadp/.last_release_check.json`.

FALSIFICATION: this gate is wrong if (a) pytest is not on PATH — I catch
this and report cleanly; (b) any archetype's fixtures were deleted or
modified so the self-check doesn't reflect real behavior; (c) the sidecar
is edited outside this tool.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dev_harness.harness.report import (
    OPTIONAL_ANALYZERS as _SHARED_OPTIONAL_ANALYZERS,
)

REPO = Path(__file__).resolve().parent.parent.parent
SIDECAR_PATH = REPO / ".release_ready.json"
TESTS_DIR = REPO / "tests"

# Fixtures the archetype self-check runs against
CODING_GOOD = REPO / "harness_fixtures" / "coding_archetype" / "known_good.py"
GUI_GOOD = REPO / "harness_fixtures" / "gui_archetype" / "known_good_widget.py"
DOCS_GOOD = REPO / "harness_fixtures" / "docs_archetype" / "known_good.md"

# Analyzers whose absence is reported but does not fail the gate. Every
# analyzer not listed is required, and its absence turns the gate red.
OPTIONAL_ANALYZERS: frozenset[str] = _SHARED_OPTIONAL_ANALYZERS


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _read_version() -> str:
    """Return the version `src` resolves for this checkout, or "unknown".

    No literal is scanned for. `src/_version.py` derives the version from
    the git tag, and from the value a build baked in for a bundle.
    """
    try:
        from src._version import resolve_version
    except ImportError:
        return "unknown"

    return resolve_version(REPO)


def _run_pytest() -> tuple[bool, int, str]:
    """Returns (passed, test_count, output). test_count is 0 if we couldn't parse."""
    if not TESTS_DIR.exists():
        return False, 0, "tests/ directory not found"
    # Literal argv with the only variable moved to `cwd`, so ruff draws no
    # S603 here and no suppression is needed. "tests" under REPO is TESTS_DIR.
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q", "--tb=no"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=1800,
        )
    except subprocess.TimeoutExpired as exc:
        return (
            False,
            0,
            (
                f"pytest did not finish within {exc.timeout} seconds and was "
                f"killed. The suite never reported, so this run is not "
                f"evidence and the gate is RED."
            ),
        )
    output = proc.stdout + proc.stderr
    # Parse summary line like "36 passed, 1 warning in 1.62s" or "1 failed, 5 passed"
    passed_match = re.search(r"(\d+)\s+passed", output)
    failed_match = re.search(r"(\d+)\s+failed", output)
    n_passed = int(passed_match.group(1)) if passed_match else 0
    n_failed = int(failed_match.group(1)) if failed_match else 0
    all_green = proc.returncode == 0 and n_failed == 0
    return all_green, n_passed, output


def _run_archetype_selfcheck() -> tuple[bool, list[str], list[str]]:
    """Each archetype's known_good fixture must gate as passed=true.

    Returns (ok, errors, notes). `notes` carries non-fatal coverage
    gaps — an optional analyzer that is not installed — so they are
    surfaced rather than silently absorbed.
    """
    # import lazily so this tool works even if a peer import fails
    sys.path.insert(0, str(REPO))
    errors: list[str] = []
    notes: list[str] = []
    try:
        from dev_harness.harness.coding_archetype import CodingArchetype
        from dev_harness.harness.gui_archetype import GUIArchetype
        from dev_harness.harness.docs_archetype import DocsArchetype
    except ImportError as e:
        return False, [f"cannot import archetypes: {e}"], notes

    for label, arch, fixture in [
        ("coding", CodingArchetype(), CODING_GOOD),
        ("gui", GUIArchetype(), GUI_GOOD),
        ("docs", DocsArchetype(), DOCS_GOOD),
    ]:
        if not fixture.exists():
            errors.append(f"{label}: known_good fixture missing at {fixture}")
            continue
        try:
            report = arch.review(fixture)
        except Exception as e:
            errors.append(f"{label}: review raised {type(e).__name__}: {e}")
            continue
        if not report.passed:
            highs = [
                f"{f.tool}:{f.rule_id}"
                for f in report.findings
                if f.severity in ("critical", "high")
            ]
            errors.append(
                f"{label}: known_good fixture no longer passes; "
                f"reasons: {report.why_not_green()}; "
                f"high/critical findings: {highs}"
            )
        if not report.falsification:
            errors.append(f"{label}: falsification field is empty")
        # A fixture can pass because the analyzer that would flag it never ran.
        absent = sorted(
            t
            for t, s in getattr(report, "tool_availability", {}).items()
            if s in ("missing", "error")
        )
        required_absent = [t for t in absent if t not in OPTIONAL_ANALYZERS]
        optional_absent = [t for t in absent if t in OPTIONAL_ANALYZERS]
        if required_absent:
            errors.append(
                f"{label}: required analyzer(s) unavailable: "
                f"{', '.join(required_absent)} - coverage is incomplete, "
                f"so this run is not evidence"
            )
        if optional_absent:
            notes.append(
                f"{label}: optional analyzer(s) not installed: "
                f"{', '.join(optional_absent)}"
            )
    return len(errors) == 0, errors, notes


def _run_claim_ledger_check() -> tuple[bool, str]:
    """No open claims allowed."""
    sys.path.insert(0, str(REPO))
    try:
        from dev_harness.harness.claim_ledger import list_open
    except ImportError as e:
        return False, f"cannot import claim_ledger: {e}"
    open_claims = list_open()
    if open_claims:
        ids = ", ".join(c.id for c in open_claims)
        return False, f"{len(open_claims)} open claim(s): {ids}"
    return True, "no open claims"


def _write_sidecar(version: str, tests: int, checks_run: dict[str, str]) -> None:
    """Write the green sidecar.

    ``checks_run`` records what actually executed. Without it a consumer
    cannot tell a full run from ``--no-pytest``, and the two produce an
    identical-looking green. Observed 2026-08-05: a ``tests: 0`` sidecar
    left by a skipped run advertised release-readiness for 46 minutes.
    """
    payload = {
        "version": version,
        "tests": tests,
        "checks_run": checks_run,
        "timestamp": _now_iso(),
        "generator": "tools/harness/check_release_readiness.py",
    }
    SIDECAR_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _remove_sidecar() -> None:
    if SIDECAR_PATH.exists():
        SIDECAR_PATH.unlink()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="check_release_readiness",
        description="Release-readiness gate; must be [OK] before banner-bump cascade.",
    )
    p.add_argument(
        "--no-pytest", action="store_true", help="skip pytest suite (dev only)"
    )
    p.add_argument(
        "--no-archetypes",
        action="store_true",
        help="skip archetype self-check (dev only)",
    )
    p.add_argument(
        "--no-claims", action="store_true", help="skip claim-ledger check (dev only)"
    )
    args = p.parse_args(argv)

    version = _read_version()
    failures: list[str] = []
    test_count = 0
    checks_run = {"pytest": "skipped", "archetypes": "skipped", "claims": "skipped"}

    # 1. pytest
    if not args.no_pytest:
        checks_run["pytest"] = "ran"
        passed, test_count, output = _run_pytest()
        if not passed:
            # tail the last ~15 lines of pytest output for context
            tail = "\n".join(output.splitlines()[-15:])
            failures.append(f"pytest failed:\n{tail}")
        elif test_count <= 0:
            # A green exit with no collected tests is not evidence of
            # anything. Parse failure or an empty run both land here.
            failures.append(
                "pytest reported 0 collected tests - a green run that "
                "collected nothing cannot support a release claim."
            )

    # 2. archetype self-check
    if not args.no_archetypes:
        checks_run["archetypes"] = "ran"
        arch_ok, arch_errors, arch_notes = _run_archetype_selfcheck()
        if not arch_ok:
            failures.append(
                "archetype self-check failed:\n  " + "\n  ".join(arch_errors)
            )
        for note in arch_notes:
            print(f"[NOTE] {note}")

    # 3. claim ledger
    if not args.no_claims:
        checks_run["claims"] = "ran"
        claims_ok, msg = _run_claim_ledger_check()
        if not claims_ok:
            failures.append(f"claim ledger: {msg}")

    skipped = sorted(k for k, v in checks_run.items() if v == "skipped")
    if skipped:
        failures.append(
            "checks skipped: "
            + ", ".join(skipped)
            + " - re-run without the --no-* flag(s) before claiming ready."
        )

    if failures:
        print(f"[FAIL] Release-not-ready (v{version})")
        for f in failures:
            print()
            print(f)
        _remove_sidecar()
        return 1

    _write_sidecar(version, test_count, checks_run)
    print(f"[OK] Release-ready (v{version}, {test_count} tests)")
    try:
        _shown = SIDECAR_PATH.relative_to(REPO)
    except ValueError:
        # SIDECAR_PATH can be redirected (tests isolate it onto tmp_path).
        # Failing to format a success message must not raise.
        _shown = SIDECAR_PATH
    print(f"     sidecar: {_shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
