"""The emitter checker's own controls are run by the suite, not by memory.

WHY THIS FILE EXISTS
====================
``tools/emitter_registry_check.py`` carries ``--selftest``. It plants one
defect of each class, asks whether each rule fired ON THAT PLANT, and
reports every control as PASS, KNOWN-RED, STALE or BROKEN. That is the
positive control for the whole instrument: it is the only thing that
says the rules can still see a defect at all.

Measured on this branch before this file existed:

    $ grep -rn "selftest" tests/ --include=*.py
    (no matches)

Nothing ran it. The controls held only while somebody remembered to type
the command, and a control nobody runs reports exactly as much as the
blind rule it is supposed to be watching -- nothing. The release gate
runs ``pytest tests``, so a test is the way in.

WHAT IS PINNED HERE, AND WHAT DELIBERATELY IS NOT
=================================================
``python -m tools.emitter_registry_check`` with no flag exits 1 today. It
reports a real pre-existing defect in the tree, E9 on
``bot.01.002.postcondition.capital_reservation``, filed as issue #21 and
owned by the repair for that pin. Nothing here asserts that path is
green, because today it is not, and a test authored to fail on the day
it lands is not a test.

``--selftest`` exits 0 today. That same red is DECLARED, so the
instrument reports itself sound. That is the fact this file pins.

WHY THE EXIT CODE IS NOT THE ONLY ASSERTION
===========================================
The summary line separates BROKEN from STALE from KNOWN-RED. The exit
code collapses all of it into one bit, produced by one ``if`` at the end
of ``_selftest``. An exit-code-only test is one refactor of that ``if``
away from passing over a blind instrument, which is the same class of
defect this whole unit exists to remove. So the states are read off the
tool's own output as well, and a positive control asserts that output
was parsed at all before any count is trusted.

WHY EVERY ARGV BELOW IS WRITTEN OUT IN FULL
===========================================
Neither ``subprocess.run`` call takes a computed argument vector, and
the two lists are not folded into one helper that would take the argv as
a parameter. Ruff's S603 fires on any argv element that is not a string
literal or ``sys.executable`` (measured with ruff 0.16 on eight forms on
2026-08-20), and the repository's coding archetype ranks S603 high.
Nothing variable therefore goes in the argv. The paths travel in ``cwd``
and ``PYTHONPATH``, which the rule does not flag and which are not
executed. ``--root .`` names the repository because ``cwd`` is the
repository. No suppression comment appears in this file.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKER = REPO_ROOT / "tools" / "emitter_registry_check.py"

SUMMARY_RE = re.compile(
    r"^controls: (\d+) passed, (\d+) known-red, (\d+) broken, "
    r"(\d+) stale, of (\d+)$", re.MULTILINE)
CONTROL_RE = re.compile(r"^  \[([A-Z-]+)\] (.+)$", re.MULTILINE)

_SUMMARY_KEYS = ("passed", "known_red", "broken", "stale", "total")


def _kwargs(extra_import_path: Path | None = None) -> dict[str, Any]:
    """Everything but the argv, so both call sites run the same way.

    ``cwd`` is ``REPO_ROOT``, derived from this file's own path, so the
    result does not depend on the directory pytest was started in.
    ``PYTHONPATH`` carries the same root, plus a temporary directory when
    a mutated copy has to be importable.

    ``PYTHONDONTWRITEBYTECODE`` stops the run dropping ``__pycache__``
    anywhere. Decoding is pinned to utf-8 with ``errors="replace"``: the
    tool quotes source text back at the reader, and the locale codec
    turns one unlucky byte into a blank read and an empty verdict.
    """
    path = str(REPO_ROOT)
    if extra_import_path is not None:
        path = os.pathsep.join([path, str(extra_import_path)])
    env = dict(os.environ)
    env["PYTHONPATH"] = path
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return {
        "cwd": str(REPO_ROOT), "env": env, "capture_output": True,
        "text": True, "encoding": "utf-8", "errors": "replace",
        "timeout": 600, "check": False,
    }


def _report(proc: subprocess.CompletedProcess[str]) -> str:
    """Return the tool's whole account of itself.

    ``exit 1 != 0`` names no control and sends the reader back to the
    command line. Every assertion below carries this instead.
    """
    return (f"exit code {proc.returncode}\n"
            f"--- stdout ---\n{proc.stdout}\n"
            f"--- stderr ---\n{proc.stderr}")


def _summary(stdout: str) -> dict[str, int] | None:
    """Return the tally the tool prints, or None if it is absent."""
    match = SUMMARY_RE.search(stdout)
    if match is None:
        return None
    # strict=True on purpose: if a group is added to SUMMARY_RE and
    # not to _SUMMARY_KEYS, this must raise rather than quietly drop
    # the state nobody remembered to name.
    return dict(zip(_SUMMARY_KEYS,
                    (int(g) for g in match.groups()), strict=True))


def _labels(stdout: str, state: str) -> list[str]:
    """Every control the tool reported in ``state``."""
    return [label for found, label in CONTROL_RE.findall(stdout)
            if found == state]


@pytest.fixture(scope="module")
def selftest() -> subprocess.CompletedProcess[str]:
    """One ``--selftest`` run, shared by the assertions that read it."""
    return subprocess.run(
        [sys.executable, "-m", "tools.emitter_registry_check",
         "--selftest"],
        **_kwargs())


class TestTheSelftestOutputCanBeRead:
    """POSITIVE CONTROL for every count-based assertion below.

    If the summary line were renamed, or the per-control lines reshaped,
    the patterns would find nothing and ``broken == 0`` would be true of
    an empty tally. A zero is a claim about the instrument until the
    instrument is shown to be reading something.
    """

    def test_the_summary_line_is_present_and_counts_controls(
            self, selftest: subprocess.CompletedProcess[str]) -> None:
        """The tally exists and describes at least one control."""
        summary = _summary(selftest.stdout)
        assert summary is not None, (
            "the checker printed no `controls: ... of N` summary line, so "
            "the state counts below would be read from nothing.\n"
            + _report(selftest))
        assert summary["total"] > 0, (
            "the checker reported 0 controls. It planted nothing, so it "
            "proved nothing.\n" + _report(selftest))

    def test_every_control_line_is_accounted_for(
            self, selftest: subprocess.CompletedProcess[str]) -> None:
        """The two surfaces must agree, or one of them is stale."""
        summary = _summary(selftest.stdout)
        assert summary is not None, _report(selftest)
        lines = CONTROL_RE.findall(selftest.stdout)
        assert len(lines) == summary["total"], (
            f"the summary claims {summary['total']} control(s) but "
            f"{len(lines)} per-control line(s) were printed. One of the "
            f"two surfaces is not reporting every control.\n"
            + _report(selftest))


class TestTheInstrumentReportsItselfSound:
    """What ``--selftest`` says about the checker on this tree today."""

    def test_selftest_exits_zero(
            self, selftest: subprocess.CompletedProcess[str]) -> None:
        """The gate-facing bit: every control behaved as declared."""
        assert selftest.returncode == 0, (
            "`python -m tools.emitter_registry_check --selftest` did not "
            "exit 0. The checker's own controls no longer behave as "
            "declared, so any clean result it reports about the tree is "
            "evidence of nothing.\n" + _report(selftest))

    def test_no_control_is_broken(
            self, selftest: subprocess.CompletedProcess[str]) -> None:
        """A rule that stopped firing on its own planted defect.

        Asserted apart from the exit code on purpose. This reads the
        state the tool itself computed, so it survives a rewrite of the
        exit logic that the exit-code assertion would not.
        """
        summary = _summary(selftest.stdout)
        broken = _labels(selftest.stdout, "BROKEN")
        assert summary is not None and summary["broken"] == 0 and (
            not broken), (
            f"{len(broken)} control(s) reported BROKEN: "
            f"{'; '.join(broken) or '<none named>'}. A broken control is "
            f"a rule that no longer fires on a defect planted in front "
            f"of it.\n" + _report(selftest))

    def test_no_control_is_stale(
            self, selftest: subprocess.CompletedProcess[str]) -> None:
        """A control declared red that came back green.

        Not good news to be swallowed: while a false declaration stands,
        that control reports nothing at all. The declaration has to be
        deleted, and this is what asks for it.
        """
        summary = _summary(selftest.stdout)
        stale = _labels(selftest.stdout, "STALE")
        assert summary is not None and summary["stale"] == 0 and (
            not stale), (
            f"{len(stale)} control(s) reported STALE: "
            f"{'; '.join(stale) or '<none named>'}. The defect each one "
            f"is declared red against appears to be fixed. Delete the "
            f"declaration so the control starts reporting again.\n"
            + _report(selftest))


_E4_ANCHOR = b"        if row.signal_type not in SIGNAL_TYPES:\n"
_E4_NEUTERED = (
    b"        if False and row.signal_type not in SIGNAL_TYPES:\n")
_E4_LABEL = "E4 fires on a signal type outside the vocabulary"
# The module name is written out at both use sites rather than held
# in a constant. The argv below must be all-literal or ruff's S603
# fires, and the archetype ranks S603 high.
_MUTANT_FILENAME = "emitter_registry_check_mutant.py"


class TestTheSelftestFailsWhenARuleGoesBlind:
    """The acceptance property, not the current state.

    The tests above pin what the instrument reports today. They would
    keep passing if every control were quietly deleted. This one pins the
    behaviour that makes them worth anything: take one rule's detection
    away, and the selftest must say so.

    The checker is copied into a temporary directory and mutated there.
    The copy is imported by module name off ``PYTHONPATH`` and reads the
    real tree through ``--root .``, so its answer is about the same pins
    and the same registry as the run above. The repository copy is never
    written, and the last assertion proves that byte for byte.
    """

    def test_the_mutation_target_is_still_where_it_was(self) -> None:
        """POSITIVE CONTROL.

        If the anchor no longer matched, the test below would run an
        UNMODIFIED copy and pass by reporting the healthy result it was
        written to reject.
        """
        assert CHECKER.read_bytes().count(_E4_ANCHOR) == 1, (
            f"the E4 detection line was not found exactly once in "
            f"{CHECKER}. The mutation below would be a no-op and would "
            f"prove nothing. Re-anchor it on the current source.")

    def test_a_copy_with_e4_detection_removed_reports_broken(
            self, tmp_path: Path) -> None:
        """Blind the E4 rule in a copy; the selftest must name it."""
        before = CHECKER.read_bytes()
        mutant = tmp_path / _MUTANT_FILENAME
        mutant.write_bytes(before.replace(_E4_ANCHOR, _E4_NEUTERED))

        proc = subprocess.run(
            [sys.executable, "-m", "emitter_registry_check_mutant",
             "--selftest", "--root", "."],
            **_kwargs(tmp_path))
        summary = _summary(proc.stdout)

        assert _E4_LABEL in _labels(proc.stdout, "BROKEN"), (
            f"E4's detection was removed and the selftest did not report "
            f"{_E4_LABEL!r} as BROKEN. The control cannot see its own "
            f"rule go blind.\n" + _report(proc))
        assert summary is not None and summary["broken"] == 1, (
            "removing E4's detection must break exactly one control. A "
            "different count means the mutation reached further than the "
            "rule it aimed at.\n" + _report(proc))
        assert proc.returncode == 1, (
            "a BROKEN control must turn the exit code, or the release "
            "gate never sees it.\n" + _report(proc))
        assert CHECKER.read_bytes() == before, (
            f"{CHECKER} changed during this test. The mutation must only "
            f"ever touch the temporary copy.")
