"""Every pin declares what it does about time, and the declaration is true.

Queue item 10.3, on the operator's standing queue:

    "TIME -- duration in the pin record. MANDATORY, not conditional."

    "10.3 SITS IN FRONT OF ALL THREE. Duration is MANDATORY in the
     record, and his health definition for item 17 -- on time, slow
     downs, hangs -- is entirely time-aware. A tab migrated before the
     record carries a duration is a tab that gets rewired afterwards."

WHAT "MANDATORY" CAN AND CANNOT MEAN
====================================
It cannot mean a number on all 74 pins. 26 of them are a `counter`, a
`gauge`, an `event`, an `invariant` or a `state_transition`, and none of
those follows a completed operation -- a duration on one is FABRICATED,
which is worse than a missing one because item 17 computes health from
it. Rule E8 in `tools/emitter_registry_check.py` already refuses those
in source.

So it means this instead: NO PIN MAY EXIST WITHOUT A DECLARED
DISPOSITION, and the declaration must agree with the code. That is
enforceable, it does not decay, and it is what this file pins.

WHY A SWEEP WAS NOT ENOUGH, MEASURED
====================================
Before 10.3 the register carried its duration decisions in PROSE, one
paragraph per unit -- "the ninth arrived", "the tenth is", "the twelfth
through the sixteenth". Two of those claims were false by the time 10.3
read them. The prose said the History tab's other five pins carry no
duration because they work over data already in memory: `05-007` writes
a file and reads it back, and `05-006` reads two logs off disk. Nobody
was checking, so nobody knew.

A count in prose has no reader. A column has a rule.

WHAT THIS FILE PINS AND WHAT IT DELIBERATELY DOES NOT
=====================================================
It pins the AGREEMENT between the register's `duration` column, the
call sites under `src`, and the signal type in the same row -- read off
the syntax tree through the checker's own collector, never off the
source text.

It does NOT pin that a `measured` bracket spans the operation its cell
names. No static rule can read that. The per-pin duration tests under
`tests/` are what hold it, each driving the real emitter through two
known workloads and requiring two DIFFERENT recorded values.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tools.emitter_registry_check import (
    DURATION_DISPOSITIONS,
    DURATION_TYPE,
    REGISTRY_PATH,
    _disposition_of,
    check,
    collect_pins,
    parse_registry,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# The tree as it stands today. Read once; every test below asks the same
# question of the same pair, so a disagreement between two tests would
# be a disagreement about the reading, not about the tree.
_PINS = collect_pins(REPO_ROOT / "src", REPO_ROOT)
_REGISTRY = parse_registry((REPO_ROOT / REGISTRY_PATH).read_bytes().decode("utf-8"))
_BY_KEY = {(pin.file, pin.name): pin for pin in _PINS}


def test_the_reading_itself_worked() -> None:
    """POSITIVE CONTROL, and it comes first for a reason.

    Every assertion below is a loop over `_REGISTRY.rows`. An empty list
    satisfies all of them silently, and a zero is a claim about the
    instrument before it is a claim about the tree. So the instrument is
    asked to prove it read something first.
    """
    assert not _REGISTRY.parse_errors, _REGISTRY.parse_errors
    assert len(_REGISTRY.rows) == len(_PINS)
    assert len(_PINS) >= 74, (
        f"only {len(_PINS)} pin(s) collected. The register recorded 74 "
        f"when this file was written; a smaller number means the "
        f"collector stopped seeing pins, not that pins were removed."
    )


def test_every_row_declares_a_disposition() -> None:
    """The mandatory half. An unfilled cell is not "no duration"."""
    missing = [
        row.emitter_id
        for row in _REGISTRY.rows
        if _disposition_of(row)[0] not in DURATION_DISPOSITIONS
    ]
    assert not missing, (
        f"{len(missing)} row(s) declare nothing about a duration: "
        f"{', '.join(missing)}. Every row must carry one of "
        f"{', '.join(DURATION_DISPOSITIONS)}."
    )


def test_every_declaration_that_needs_a_reason_has_one() -> None:
    """`forbidden` is the only term whose reason is elsewhere.

    Its reason is the signal type, which sits in the same row and is
    machine-checked. The other three have to say why in words, because
    nothing else in the row carries it.
    """
    bare = [
        row.emitter_id
        for row in _REGISTRY.rows
        if _disposition_of(row)[0] != "forbidden" and not _disposition_of(row)[1]
    ]
    assert not bare, (
        f"{len(bare)} declaration(s) carry no reason: " f"{', '.join(bare)}."
    )


def test_the_dispositions_partition_the_register() -> None:
    """Four terms, no overlap, and they add up to every pin."""
    counted = sum(
        1 for row in _REGISTRY.rows if _disposition_of(row)[0] in DURATION_DISPOSITIONS
    )
    assert counted == len(_REGISTRY.rows)


def test_a_measured_row_has_a_call_site_that_passes_duration() -> None:
    """The register may not claim a number the record never carries."""
    lying = [
        row.emitter_id
        for row in _REGISTRY.rows
        if _disposition_of(row)[0] == "measured"
        and (row.file, row.name) in _BY_KEY
        and not _BY_KEY[(row.file, row.name)].carries_duration
    ]
    assert not lying, (
        f"{len(lying)} row(s) declare a measured duration whose call "
        f"site passes none: {', '.join(lying)}."
    )


def test_a_row_that_declares_no_duration_has_a_site_that_passes_none() -> None:
    """And the other direction, which is the one that rots quietly.

    A site that gains a `duration=` while its row still reads `none` is
    a number nobody declared, arriving in a field item 17 reads as
    latency.
    """
    stale = [
        row.emitter_id
        for row in _REGISTRY.rows
        if _disposition_of(row)[0] != "measured"
        and (row.file, row.name) in _BY_KEY
        and _BY_KEY[(row.file, row.name)].carries_duration
    ]
    assert not stale, (
        f"{len(stale)} row(s) deny a duration their call site passes: "
        f"{', '.join(stale)}."
    )


def test_the_measured_count_matches_the_tree() -> None:
    """Counted on both sides, independently, and compared.

    The two tests above compare row against site one pin at a time. This
    compares the TOTALS, which is what catches a pin that carries a
    duration and has no row at all -- that pin is invisible to a
    row-driven loop.
    """
    declared = sum(1 for row in _REGISTRY.rows if _disposition_of(row)[0] == "measured")
    in_tree = sum(1 for pin in _PINS if pin.carries_duration)
    assert declared == in_tree, (
        f"the register declares {declared} measured duration(s) and the "
        f"tree carries {in_tree}."
    )


def test_only_a_postcondition_may_declare_anything_but_forbidden() -> None:
    """The type decides, and it decides both ways round."""
    wrong = [
        row.emitter_id
        for row in _REGISTRY.rows
        if (_disposition_of(row)[0] == "forbidden")
        is not (row.signal_type != DURATION_TYPE)
    ]
    assert not wrong, (
        f"{len(wrong)} row(s) declare a disposition that disagrees with "
        f"their signal type: {', '.join(wrong)}."
    )


def test_no_pin_of_a_forbidden_type_carries_a_duration() -> None:
    """Read off the TREE, not off the register.

    The test above reads the register's own two columns against each
    other. This reads the code, so a call site that adds `duration=` to
    a gauge is caught even if nobody touched the register.
    """
    offenders = [
        f"{pin.name} at {pin.file}:{pin.line}"
        for pin in _PINS
        if pin.carries_duration
        and not pin.dynamic
        and len(pin.name.split(".")) >= 4
        and pin.name.split(".")[3] != DURATION_TYPE
    ]
    assert not offenders, (
        f"a duration rides on a non-{DURATION_TYPE}: " f"{'; '.join(offenders)}."
    )


def test_the_tree_is_clean_under_the_duration_rules() -> None:
    """No E10, E11 or E12 on the tree as it stands."""
    problems = [
        p for p in check(_PINS, _REGISTRY) if p.startswith(("E10", "E11", "E12"))
    ]
    assert not problems, "\n".join(problems)


# ── the rules driven in the failing direction ──────────────────────────
#
# Every test above is a silence. A silence proves nothing until the rule
# behind it has been shown to speak, so each rule is planted against a
# real row and the finding is required to name THAT row. Asking "did any
# E11 fire?" would be answered by anybody's E11.


def _swap(emitter_id: str, duration: str):
    """The registry with one row's duration cell replaced."""
    return dataclasses.replace(
        _REGISTRY,
        rows=[
            (
                dataclasses.replace(row, duration=duration)
                if row.emitter_id == emitter_id
                else row
            )
            for row in _REGISTRY.rows
        ],
    )


def _fired(problems: list[str], code: str, emitter_id: str) -> list[str]:
    return [p for p in problems if p.startswith(code) and emitter_id in p]


@pytest.fixture(scope="module")
def a_measured_row() -> str:
    row = next((r for r in _REGISTRY.rows if _disposition_of(r)[0] == "measured"), None)
    assert row is not None, (
        "no row declares a measured duration, so the plants below "
        "would have nothing to plant against."
    )
    return row.emitter_id


@pytest.fixture(scope="module")
def a_forbidden_row() -> str:
    row = next(
        (r for r in _REGISTRY.rows if _disposition_of(r)[0] == "forbidden"), None
    )
    assert row is not None, (
        "no row declares forbidden, so the type plant below would have "
        "nothing to plant against."
    )
    return row.emitter_id


def test_e10_fires_on_an_empty_cell(a_measured_row: str) -> None:
    assert _fired(check(_PINS, _swap(a_measured_row, "")), "E10", a_measured_row)


def test_e10_fires_on_a_coined_term(a_measured_row: str) -> None:
    assert _fired(
        check(_PINS, _swap(a_measured_row, "sometimes: if it feels right")),
        "E10",
        a_measured_row,
    )


def test_e10_fires_on_a_declaration_with_no_reason(a_measured_row: str) -> None:
    assert _fired(
        check(_PINS, _swap(a_measured_row, "measured")), "E10", a_measured_row
    )


def test_e11_fires_when_a_row_denies_a_duration_the_site_passes(
    a_measured_row: str,
) -> None:
    assert _fired(
        check(_PINS, _swap(a_measured_row, "none: a false denial")),
        "E11",
        a_measured_row,
    )


def test_e11_fires_when_a_row_claims_a_duration_the_site_lacks() -> None:
    row = next(r for r in _REGISTRY.rows if _disposition_of(r)[0] == "none")
    assert _fired(
        check(_PINS, _swap(row.emitter_id, "measured: a false claim")),
        "E11",
        row.emitter_id,
    )


def test_e12_fires_when_a_forbidden_type_declares_otherwise(
    a_forbidden_row: str,
) -> None:
    assert _fired(
        check(_PINS, _swap(a_forbidden_row, "none: wrong for this type")),
        "E12",
        a_forbidden_row,
    )


def test_e12_fires_when_a_postcondition_declares_forbidden() -> None:
    row = next(r for r in _REGISTRY.rows if r.signal_type == DURATION_TYPE)
    assert _fired(
        check(_PINS, _swap(row.emitter_id, "forbidden")), "E12", row.emitter_id
    )


def test_the_rules_stay_silent_on_a_re_worded_but_correct_cell(
    a_measured_row: str,
) -> None:
    """The half that separates a rule from a rule that hates edits.

    The clean-tree test above says today's register is quiet. This says
    a row that is CHANGED and still correct stays quiet, so the rules
    are reading the declaration and not the diff.
    """
    problems = _fired(
        check(_PINS, _swap(a_measured_row, "measured: a re-worded description")),
        "E10",
        a_measured_row,
    )
    problems += _fired(
        check(_PINS, _swap(a_measured_row, "measured: a re-worded description")),
        "E11",
        a_measured_row,
    )
    problems += _fired(
        check(_PINS, _swap(a_measured_row, "measured: a re-worded description")),
        "E12",
        a_measured_row,
    )
    assert not problems, "\n".join(problems)


# ── the deferred list, which is the standing work ──────────────────────


def test_a_deferred_row_says_what_is_missing() -> None:
    """`deferred` is not a softer `none`, and the reason is why.

    `none` says a duration cannot be honest at this site, ever.
    `deferred` says it can and nobody has written it. One word covering
    both leaves a reader unable to tell "leave this alone" from "this is
    the next unit". So a `deferred` cell has to name what is missing.
    """
    vague = [
        row.emitter_id
        for row in _REGISTRY.rows
        if _disposition_of(row)[0] == "deferred" and len(_disposition_of(row)[1]) < 20
    ]
    assert not vague, (
        f"{len(vague)} deferred row(s) do not say what is missing: "
        f"{', '.join(vague)}."
    )


def test_the_deferred_list_is_visible_rather_than_absent() -> None:
    """The whole point of the column, asserted rather than assumed.

    A pin that COULD carry a duration and does not is the only class the
    register used to lose. It carried no cell, so it was
    indistinguishable from a pin that must never carry one. If this list
    ever empties, delete this test rather than weakening it: an empty
    list would then be a true statement about the tree.
    """
    deferred = sorted(
        row.emitter_id
        for row in _REGISTRY.rows
        if _disposition_of(row)[0] == "deferred"
    )
    assert deferred, (
        "no row declares `deferred`. Either every timeable site is now "
        "bracketed -- in which case this test has done its job and "
        "should be removed -- or the term has been dropped, which would "
        "hide the standing work list the column exists to show."
    )
