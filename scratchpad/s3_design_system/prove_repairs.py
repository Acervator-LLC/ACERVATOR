"""Puts each repair's old code back into the target module, one at a time."""

from __future__ import annotations

import hashlib
import subprocess
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "src" / "gui" / "web" / "design_system.js"
TESTS = "tests/test_react_design_system.py"
PYTHON = sys.executable
GIT = shutil.which("git") or "git"

REPAIRS = {
    "the alpha byte stays a byte": (
        "    parts[ALPHA_AT] = String(alpha * ALPHA_STEP);",
        "    parts[ALPHA_AT] = String(alpha);",
        "alpha_byte or converted_alpha or computes_in_the_browser",
    ),
    "a length loses its unit": (
        "    return text.indexOf(EXPONENT_MARK) < NO_OFFSET ? text + unit : null;",
        "    return text.indexOf(EXPONENT_MARK) < NO_OFFSET ? text : null;",
        "agrees_with_the_surface_value or computes_in_the_browser",
    ),
    "order comes from a bag walk": (
        "    return held === null ? [] : held.order.slice();",
        "    return held === null ? [] : Object.keys(held.rendered);",
        "order or position or renders_nothing or lands_on_the_page",
    ),
    "a shared value resolves to the first carrier": (
        "    if (carriers.length > OPAQUE) {",
        "    if (carriers.length > ALPHA_SCALE) {",
        "several_names_carry",
    ),
}


def run_tests(pattern: str) -> tuple:
    """Run only the checks naming one repair and answer code and tail."""
    done = subprocess.run(
        [PYTHON, "-m", "pytest", TESTS, "-n", "2", "-q", "-k", pattern],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    tail = [line for line in done.stdout.splitlines() if line.strip()][-1:]
    return done.returncode, tail[0] if tail else ""


def main() -> None:
    original = TARGET.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    print(f"module digest before: {before}")
    for label, (good, bad, pattern) in REPAIRS.items():
        source = original.decode("utf-8")
        if good not in source:
            print(f"  MISSED {label}: {good[:50]!r}")
            continue
        TARGET.write_text(source.replace(good, bad, 1), encoding="utf-8", newline="")
        code, tail = run_tests(pattern)
        TARGET.write_bytes(original)
        after = hashlib.sha256(TARGET.read_bytes()).hexdigest()
        mark = "FAILED as it must" if code != 0 else "STAYED GREEN - the check is void"
        print(f"\n{label}")
        print(f"  with the old code: exit {code}  {mark}")
        print(f"  {tail}")
        print(f"  restored: {after == before}")
    code, tail = run_tests("design")
    print(f"\nwith every repair in place: exit {code}  {tail}")
    print(f"module digest after: {hashlib.sha256(TARGET.read_bytes()).hexdigest()}")
    subprocess.run([GIT, "status", "--porcelain", str(TARGET)], cwd=REPO, check=False)


if __name__ == "__main__":
    main()
