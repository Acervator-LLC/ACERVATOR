"""Refuses a heavy test run when the machine cannot afford it, before it starts.

Enforces OCIR C98 in ``~/.claude/skills/ocir/SKILL.md``: denies a run above the
RAM ceiling, a run while another is resident, and ``-n auto`` outright.
"""

import json
import re
import subprocess
import shutil
import sys

# A pytest call carrying xdist, or the whole-suite lanes. The -n must sit in the
# same command segment as pytest: a later `sed -n` is not an xdist run.
HEAVY = re.compile(
    r"\bpytest\b[^;&|\n]*?\s-n\s|\blocal_ci\b|check_release_readiness"
)

# `-n auto` is 24 workers plus a browser each on this machine.
N_AUTO = re.compile(r"\s-n\s+auto\b")

# Refuse a new heavy run above this. Acervator itself holds about 2.7 GB.
RAM_CEILING_PCT = 70.0

# Another heavy run is already live above this much resident python.
PYTHON_BUDGET_MB = 2500.0

PS = shutil.which("powershell") or "powershell"

PROBE = (
    "$os = Get-CimInstance Win32_OperatingSystem; "
    "$pct = 100 - ($os.FreePhysicalMemory / $os.TotalVisibleMemorySize * 100); "
    "$py = (Get-Process python -ErrorAction SilentlyContinue | "
    "Measure-Object WorkingSet64 -Sum).Sum / 1MB; "
    "Write-Output ('{0:N1} {1:N0}' -f $pct, [double]$py)"
)


def reading() -> tuple[float, float] | None:
    """Return (RAM percent used, resident python MB), or None if unreadable."""
    try:
        done = subprocess.run(  # noqa: S603
            [PS, "-NoProfile", "-NonInteractive", "-Command", PROBE],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        pct, mb = done.stdout.split()
        return float(pct.replace(",", "")), float(mb.replace(",", ""))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if payload.get("tool_name") not in ("Bash", "PowerShell"):
        sys.exit(0)

    command = str(payload.get("tool_input", {}).get("command", ""))

    if N_AUTO.search(command):
        print(
            "`-n auto` refused. It is 24 workers plus a browser each on this "
            "machine, while Acervator trades real money. Use `-n 4` at most.",
            file=sys.stderr,
        )
        sys.exit(2)

    if not HEAVY.search(command):
        sys.exit(0)

    seen = reading()
    if seen is None:
        sys.exit(0)
    pct, python_mb = seen

    if pct >= RAM_CEILING_PCT:
        print(
            f"Heavy run refused: RAM is at {pct:.1f}%, ceiling {RAM_CEILING_PCT:.0f}%. "
            "Acervator is trading on this machine. Stop other work, or wait.",
            file=sys.stderr,
        )
        sys.exit(2)

    if python_mb >= PYTHON_BUDGET_MB:
        print(
            f"Heavy run refused: {python_mb:.0f} MB of python is already resident, "
            f"budget {PYTHON_BUDGET_MB:.0f} MB. One heavy consumer at a time — "
            "`-n 4` caps one run, not how many run at once. Stop the other first.",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
