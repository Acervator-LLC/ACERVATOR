"""The register is compared with the tree by the gate, not by memory.

WHY THIS FILE EXISTS
====================
``tools/emitter_registry_check.py`` is the detector for the register:
every pin under ``src`` has a row, every row has a pin, the ID
vocabulary holds, a duration rides only on a postcondition, and no
check compares a value with itself.

Measured on this branch before this file existed::

    $ grep -rn "emitter_registry" tools/harness/ tests/
    tests/test_emitter_checker_selftest.py:<docstring mention>

One mention, in prose. No invocation. Nothing on the way to green ran
the checker, so the register was enforced only while somebody
remembered to type the command.

WHAT THAT COST, 2026-08-20
==========================
Merge ``06abf83`` inserted 11 lines into ``fleet_replay_panel.py``.
Nine rows then recorded a line number that no longer held their pin.
The checker reported all nine. The merge landed anyway, because the
gate never asked it anything.

WHAT THIS FILE PINS, AND WHAT THE SIBLING FILE PINS
===================================================
``tests/test_emitter_checker_selftest.py`` runs ``--selftest``. That is
a fact about the INSTRUMENT: every rule still fires on a defect planted
in front of it. It says nothing about the tree.

This file runs the checker with no flag. That is a fact about the TREE:
today's source and today's register describe the same set of pins.
Those are different facts and they fail for different reasons, so they
are asserted in different files.

WHY THE WARNINGS ARE ASSERTED AS WELL AS THE EXIT CODE
======================================================
Read the exit logic before reading this paragraph as a preference.
``main`` computes ``problems`` and ``warnings`` separately, and returns
0 when ``not problems and not broken``. ``warnings`` is printed and
never consulted. The ``--json`` path does the same: ``passed`` is
``not problems and not broken``, with ``warnings`` carried alongside as
data. So a W1 line drift CANNOT move the exit code, by construction, in
either output mode.

The nine rows that ``06abf83`` broke were all W1. The checker exited 0
on them at the time. An exit-code-only test here would have watched
that merge go past exactly as the empty gate did, and would have
reported green about it.

So the drift is asserted, in its own test, separately from the exit
code. The checker's own semantics are not changed to do it: W1 stays a
warning for somebody running the tool by hand mid-edit, where a line
number is expected to be stale for the length of an edit. This file is
the gate, and the gate is where a warning becomes a stop.

The two are separate tests rather than one, because "a pin has no row"
and "a row records the wrong line" send the reader to different work.

WHY EVERY ARGV BELOW IS WRITTEN OUT IN FULL
===========================================
The same reason as the sibling file, and measured there: ruff's S603
fires on any argv element that is not a string literal or
``sys.executable``, and this repository's coding archetype ranks S603
high. Nothing computed goes in an argv. The paths travel in ``cwd``
and ``PYTHONPATH``, which the rule does not flag and which are not
executed. ``--root .`` names the repository because ``cwd`` is the
repository -- which is also why no assertion here depends on the
directory pytest was started in. No suppression comment appears in
this file.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from tools.emitter_registry_check import REGISTRY_PATH

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / REGISTRY_PATH

PINS_RE = re.compile(r"^pins in src\s*:\s*(\d+)\s*$", re.MULTILINE)
ROWS_RE = re.compile(r"^registry rows\s*:\s*(\d+)\s*$", re.MULTILINE)
WARNING_RE = re.compile(r"^\s*(W1 (\d{2}-\d{3}):.*)$", re.MULTILINE)
ID_CELL_RE = re.compile(r"^\d{2}-\d{3}$")
SOURCE_CELL_RE = re.compile(r"`([^`]+\.py):(\d+)`")

# Far enough past the end of any file in the tree that the moved row
# cannot land on another pin by accident and report a false clean.
LINE_DRIFT = 100_000
_MAIN_COLS = 7


def _kwargs(cwd: Path) -> dict[str, Any]:
    """Everything but the argv, so both call sites run the same way.

    ``cwd`` is passed in because the two runs read two different trees:
    the repository itself, and a copy with one row moved off its pin.
    Neither is ever the directory pytest happened to start in.

    ``PYTHONPATH`` always carries ``REPO_ROOT``, derived from this
    file's own path, so ``-m tools.emitter_registry_check`` resolves to
    the checker in this repository whatever ``cwd`` is.

    ``PYTHONDONTWRITEBYTECODE`` stops the run dropping ``__pycache__``
    anywhere. Decoding is pinned to utf-8 with ``errors="replace"``:
    the tool quotes source text back at the reader, and the locale
    codec turns one unlucky byte into a blank read and an empty
    verdict.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return {
        "cwd": str(cwd), "env": env, "capture_output": True,
        "text": True, "encoding": "utf-8", "errors": "replace",
        "timeout": 600, "check": False,
    }


def _report(proc: subprocess.CompletedProcess[str]) -> str:
    """Return the tool's whole account of itself.

    ``exit 1 != 0`` names no pin and no row, and sends the reader back
    to the command line to find out what happened. This test fires most
    often on somebody who has just added an emitter and does not yet
    know the register exists, so every assertion below carries the
    tool's own output, which names the ID and the file and the line.
    """
    return (f"exit code {proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}")


def _count(pattern: re.Pattern[str], stdout: str) -> int | None:
    """Return the number the tool printed, or None if it printed none."""
    match = pattern.search(stdout)
    return None if match is None else int(match.group(1))


def _warnings(stdout: str) -> list[str]:
    """Return every W1 line the tool printed, whole, in order."""
    return [line for line, _ in WARNING_RE.findall(stdout)]


def _warned_ids(stdout: str) -> list[str]:
    """Return the emitter ID of every W1 line the tool printed."""
    return [emitter_id for _, emitter_id in WARNING_RE.findall(stdout)]


def _drift_one_row(text: str, already_drifted: set[str]) -> tuple[str, str]:
    """Move one row's recorded line off its pin.

    Returns the whole register with that one edit, and the ID of the
    row that was moved. Only the number inside the source cell changes,
    so the row still parses and the only thing wrong with it is the one
    thing under test.

    ``already_drifted`` holds the IDs the tree is ALREADY warning
    about. Those rows are skipped: moving a row that is warned about
    twice adds no warning to count, so the control would read its own
    plant as invisible and blame the checker for a defect in the tree.
    """
    lines = text.split("\n")
    for index, raw in enumerate(lines):
        cells = [cell.strip().strip("`").strip()
                 for cell in raw.strip().strip("|").split("|")]
        if len(cells) != _MAIN_COLS or not ID_CELL_RE.match(cells[0]):
            continue
        if cells[0] in already_drifted:
            continue
        match = SOURCE_CELL_RE.search(raw)
        if match is None:
            continue
        moved = f"`{match.group(1)}:{int(match.group(2)) + LINE_DRIFT}`"
        lines[index] = raw[:match.start()] + moved + raw[match.end():]
        return "\n".join(lines), cells[0]
    msg = (f"no row of the main table in {REGISTRY} carried a "
           f"`<path>.py:<line>` source cell that is not already drifted, "
           f"so the plant below would have been a no-op. Re-anchor it on "
           f"the current register.")
    raise AssertionError(msg)


def _tree_with_one_drifted_row(destination: Path,
                               already_drifted: set[str]) -> str:
    """Build a copy of the tree whose register has one stale line.

    ``src`` is copied whole rather than sampled: the checker compares
    two multisets, so a partial tree would report every absent pin as a
    problem and drown the one warning under test.
    """
    shutil.copytree(REPO_ROOT / "src", destination / "src",
                    ignore=shutil.ignore_patterns("__pycache__"))
    drifted, emitter_id = _drift_one_row(
        REGISTRY.read_bytes().decode("utf-8"), already_drifted)
    target = destination / REGISTRY_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    # write_bytes, not write_text: the text path on this box translates
    # "\n" on the way out, and the register is LF.
    target.write_bytes(drifted.encode("utf-8"))
    return emitter_id


@pytest.fixture(scope="module")
def plain_run() -> subprocess.CompletedProcess[str]:
    """One no-flag run over this repository, shared by its readers."""
    return subprocess.run(
        [sys.executable, "-m", "tools.emitter_registry_check",
         "--root", "."],
        **_kwargs(REPO_ROOT))


class TestTheRunCanBeRead:
    """POSITIVE CONTROL for everything asserted below it.

    A clean verdict from a scanner that scanned nothing reads the same
    as a clean verdict from a scanner that scanned the tree. So the
    counts the tool prints are read first, and they have to be present
    and non-zero before an empty warning list is worth anything.
    """

    def test_the_run_says_how_many_pins_it_found(
            self, plain_run: subprocess.CompletedProcess[str]) -> None:
        """The left side of the comparison exists."""
        pins = _count(PINS_RE, plain_run.stdout)
        assert pins is not None, (
            "the checker printed no `pins in src : N` line, so nothing "
            "below is reading a count at all.\n" + _report(plain_run))
        assert pins > 0, (
            "the checker found 0 pins under src. It compared an empty "
            "left side against the register, so a clean result is "
            "evidence of nothing.\n" + _report(plain_run))

    def test_the_run_says_how_many_rows_it_read(
            self, plain_run: subprocess.CompletedProcess[str]) -> None:
        """The right side of the comparison exists."""
        rows = _count(ROWS_RE, plain_run.stdout)
        assert rows is not None, (
            "the checker printed no `registry rows: N` line.\n"
            + _report(plain_run))
        assert rows > 0, (
            "the checker read 0 rows out of the register. Either the "
            "register is empty or its table stopped parsing.\n"
            + _report(plain_run))


class TestTheTreeAndTheRegisterDescribeTheSamePins:
    """The gate-facing fact: run the checker, and it must be green."""

    def test_the_checker_exits_zero(
            self, plain_run: subprocess.CompletedProcess[str]) -> None:
        """Every pin has a row, and every row has a pin.

        If this is red and you have just added an emitter: the output
        below names it. Give it an ID and a row in
        ``docs/EMITTER_IDENTIFICATION.md``.
        """
        assert plain_run.returncode == 0, (
            "`python -m tools.emitter_registry_check` did not exit 0. "
            "The register and the source no longer describe the same "
            "set of pins, or one of the checker's own rules failed its "
            "control. Its account of what it found:\n"
            + _report(plain_run))

    def test_no_row_records_a_line_that_moved(
            self, plain_run: subprocess.CompletedProcess[str]) -> None:
        """No row points at a line that no longer holds its pin.

        Asserted apart from the exit code because the checker cannot
        express this one through the exit code: ``main`` returns 0
        whenever ``problems`` and ``broken`` are empty, and ``warnings``
        is printed without being consulted. Nine rows drifted on
        2026-08-20 and the tool exited 0 on all nine.

        If this is red: the pins moved, the rows did not. Update the
        ``source`` column of each ID named below.
        """
        drifted = _warnings(plain_run.stdout)
        assert not drifted, (
            f"{len(drifted)} register row(s) record a line that no "
            f"longer holds their pin:\n  " + "\n  ".join(drifted)
            + "\n" + _report(plain_run))


class TestADriftedRowIsVisibleToThisFile:
    """POSITIVE CONTROL for the drift assertion above.

    ``not drifted`` is true of a list that is empty because the tool
    reported nothing, and equally true of a list that is empty because
    the pattern reading the tool's output stopped matching it. This
    plants the defect that started the unit -- one row recording a line
    its pin does not sit on -- and requires that the pattern sees it.

    The plant goes in a COPY. ``src`` is copied whole and the register
    is written beside it with one number changed, so the run answers
    about the same pins the run above answered about. The repository is
    never written, and the last assertion proves that byte for byte.
    """

    def test_the_drift_target_is_still_where_it_was(
            self, plain_run: subprocess.CompletedProcess[str]) -> None:
        """The register still has a row this plant can move.

        Without this, a register whose source cells were reshaped would
        make ``_drift_one_row`` raise, or worse, return the text
        unchanged, and the test below would pass by reporting the
        healthy result it was written to reject.
        """
        before = REGISTRY.read_bytes().decode("utf-8")
        drifted, emitter_id = _drift_one_row(
            before, set(_warned_ids(plain_run.stdout)))
        assert drifted != before, (
            f"the drift changed nothing in {REGISTRY}. The plant below "
            f"would be a no-op and would prove nothing.")
        assert ID_CELL_RE.match(emitter_id), (
            f"the drifted row reported its ID as {emitter_id!r}, which "
            f"is not an emitter ID. The main table is not being read.")

    def test_a_row_moved_off_its_pin_is_reported_and_moves_no_exit_code(
            self, tmp_path: Path,
            plain_run: subprocess.CompletedProcess[str]) -> None:
        """The whole reason the warning is asserted separately.

        Both assertions are DIFFERENCES against the same tree without
        the plant, never absolutes. An absolute would fail this control
        whenever the tree itself is dirty, and would then accuse the
        checker of changing its semantics when the real fault is the
        unrelated defect the tests above are already naming.
        """
        before = REGISTRY.read_bytes()
        emitter_id = _tree_with_one_drifted_row(
            tmp_path, set(_warned_ids(plain_run.stdout)))

        proc = subprocess.run(
            [sys.executable, "-m", "tools.emitter_registry_check",
             "--root", "."],
            **_kwargs(tmp_path))
        added = (Counter(_warned_ids(proc.stdout))
                 - Counter(_warned_ids(plain_run.stdout)))

        assert list(added.elements()) == [emitter_id], (
            f"one row was moved off its pin, and the W1 lines this file "
            f"can read grew by {sorted(added.elements())} rather than by "
            f"exactly [{emitter_id!r}]. Either the checker stopped "
            f"reporting line drift or this file stopped being able to "
            f"read the report, and the drift assertion above is then "
            f"green over nothing.\n" + _report(proc))
        assert proc.returncode == plain_run.returncode, (
            f"moving one row off its pin changed the exit code from "
            f"{plain_run.returncode} to {proc.returncode}. W1 is a "
            f"warning and cannot move it, so either the checker's exit "
            f"logic changed or the plant reached past the line number "
            f"it aimed at.\n" + _report(proc))
        assert REGISTRY.read_bytes() == before, (
            f"{REGISTRY} changed during this test. The plant must only "
            f"ever touch the copy under the temporary directory.")
