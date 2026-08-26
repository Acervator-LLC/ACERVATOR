"""The emitter register documents the same pins the tree emits.

``tools/emitter_registry_check.py`` compares the emitters under ``src``
against the rows of ``docs/EMITTER_IDENTIFICATION.md``: every pin has a
row and every row has a pin, the ID vocabulary holds, a duration rides
only on a postcondition, and no check compares a value with itself.

This runs the checker over the repository and requires it green — a
completeness fact about the tree (today's source and today's register
describe the same set of pins), asserted through the checker's exit
code. The sibling ``tests/test_emitter_checker_selftest.py`` asserts a
fact about the instrument instead (every rule still fires on a planted
defect).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tools.emitter_registry_check import REGISTRY_PATH

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / REGISTRY_PATH

PINS_RE = re.compile(r"^pins in src\s*:\s*(\d+)\s*$", re.MULTILINE)
ROWS_RE = re.compile(r"^registry rows\s*:\s*(\d+)\s*$", re.MULTILINE)


def _kwargs(cwd: Path) -> dict[str, Any]:
    """Subprocess kwargs so the checker resolves to this repository.

    ``PYTHONPATH`` carries ``REPO_ROOT`` so ``-m
    tools.emitter_registry_check`` resolves here whatever ``cwd`` is.
    ``PYTHONDONTWRITEBYTECODE`` stops the run dropping ``__pycache__``.
    Decoding is pinned to utf-8 with ``errors="replace"`` because the
    tool quotes source text back at the reader.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return {
        "cwd": str(cwd),
        "env": env,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 600,
        "check": False,
    }


def _report(proc: subprocess.CompletedProcess[str]) -> str:
    """Return the tool's whole account of itself for a failure message."""
    return (
        f"exit code {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n"
        f"--- stderr ---\n{proc.stderr}"
    )


def _count(pattern: re.Pattern[str], stdout: str) -> int | None:
    """Return the number the tool printed, or None if it printed none."""
    match = pattern.search(stdout)
    return None if match is None else int(match.group(1))


@pytest.fixture(scope="module")
def plain_run() -> subprocess.CompletedProcess[str]:
    """One no-flag run over this repository, shared by its readers."""
    return subprocess.run(
        [sys.executable, "-m", "tools.emitter_registry_check", "--root", "."],
        **_kwargs(REPO_ROOT),
    )


class TestTheRunCanBeRead:
    """Positive control: a clean verdict from a scanner that scanned
    nothing reads the same as one that scanned the tree, so the counts
    the tool prints must be present and non-zero first."""

    def test_the_run_says_how_many_pins_it_found(
        self, plain_run: subprocess.CompletedProcess[str]
    ) -> None:
        pins = _count(PINS_RE, plain_run.stdout)
        assert pins is not None, (
            "the checker printed no `pins in src : N` line, so nothing "
            "below is reading a count at all.\n" + _report(plain_run)
        )
        assert pins > 0, (
            "the checker found 0 pins under src. It compared an empty "
            "left side against the register, so a clean result is "
            "evidence of nothing.\n" + _report(plain_run)
        )

    def test_the_run_says_how_many_rows_it_read(
        self, plain_run: subprocess.CompletedProcess[str]
    ) -> None:
        rows = _count(ROWS_RE, plain_run.stdout)
        assert (
            rows is not None
        ), "the checker printed no `registry rows: N` line.\n" + _report(plain_run)
        assert rows > 0, (
            "the checker read 0 rows out of the register. Either the "
            "register is empty or its table stopped parsing.\n" + _report(plain_run)
        )


class TestTheTreeAndTheRegisterDescribeTheSamePins:
    """The gate-facing fact: run the checker, and it must be green."""

    def test_the_checker_exits_zero(
        self, plain_run: subprocess.CompletedProcess[str]
    ) -> None:
        """Every pin has a row, and every row has a pin.

        If this is red and you have just added an emitter: the output
        below names it. Give it an ID and a row in
        ``docs/EMITTER_IDENTIFICATION.md``.
        """
        assert plain_run.returncode == 0, (
            "`python -m tools.emitter_registry_check` did not exit 0. "
            "The register and the source no longer describe the same "
            "set of pins, or one of the checker's own rules failed its "
            "control. Its account of what it found:\n" + _report(plain_run)
        )
