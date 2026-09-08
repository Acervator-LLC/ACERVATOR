"""A file that starts agent processes to run the canon, with two DC002 defects.

`launch_review` starts one agent process per path to run the coding archetype,
and `launch_debug` starts one per subsystem to run the debugger. Both name the
canon inside an agent argv, so neither reads a return code of its own.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SUBSYSTEMS = ("trading", "exchange", "core")


def launch_review(paths: list[Path]) -> list[int]:
    """Start one agent process per entry of `paths` to review it."""
    codes = []
    for path in paths:
        done = subprocess.run(
            [
                "agent",
                "--prompt",
                f"Run python -m dev_harness.harness.coding_archetype on {path}",
            ],
            check=False,
        )
        codes.append(done.returncode)
    return codes


def launch_debug() -> list[subprocess.Popen[bytes]]:
    """Start one agent process per entry of `SUBSYSTEMS` to run the debugger."""
    return [
        subprocess.Popen(
            ["agent", "--prompt", f"Run the debugger over src/{name}"],
        )
        for name in SUBSYSTEMS
    ]


def main() -> int:
    """Launch the reviews and the debug runs, and return 0."""
    launch_review([Path("src")])
    launch_debug()
    return 0
