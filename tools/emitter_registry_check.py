"""emitter_registry_check.py -- every pin has a registry row, and back.

Run it from the repository root, the way every other tool here is run::

    python -m tools.emitter_registry_check
    python -m tools.emitter_registry_check --selftest

Operator's spec, 2026-08-13:

    "ID numbers are recorded into an Emitter Identification Markdown as
    they are created so that we do not lose track."

An ID that is assigned but never recorded is exactly the failure the
registry exists to prevent, so a missing entry has to be DETECTABLE and
not merely discouraged. This is the detector.

WHAT IT COMPARES
================
Left side  : the pins the Watchdog archetype finds under ``src``.
Right side : the rows of the Emitter Identification markdown.

WHY IT IMPORTS THE WATCHDOG INSTEAD OF MATCHING TEXT
====================================================
"What is a pin" already has one definition, in
``tools/harness/watchdog_archetype.py``. It resolves names through the
AST because a pin is a call that reaches the installed handler, not a
spelling. The inventory of 2026-08-13 measured what happens when a
counter guesses at the spelling instead: one regex returned 0 against a
recorded 40, another returned 309. So this file imports that scanner and
never re-implements it. It adds only the part the Watchdog does not
record -- the name string each pin carries.

This file is NOT part of the harness. It lives under ``tools/`` because
the Coding Archetype may not edit ``tools/harness/``.

THE MATCH KEY IS (file, name), COUNTED
======================================
Not (file, line, name). Line numbers move on every edit above a pin, and
a check that went red on unrelated edits would be switched off. Not name
alone either: ``bot.capital_reservation`` is emitted from two sites in
one file, and ``signal_contract._throttle_admit`` already keys its rate
limit on ``(name, site)`` because "the same signal emitted from two
places is two different things to a reader". So the comparison is
between MULTISETS -- two pins with one row is a finding.

The throttle gained a third key element in issue #57 -- an ``instance``
a rate-limited pin may declare when several live objects run its line --
and this match key did NOT. Those objects are ONE pin at ONE call site
and they take ONE row; they are told apart on the record by the id their
context already carries.

Line drift is reported as a warning and does not fail the run. That is a
stated blind spot: a row whose line number is stale still passes.

WHAT FAILS THE RUN
==================
  E0  the registry markdown does not parse
  E1  a pin in src with no registry row
  E2  a registry row with no pin in src
  E3  a malformed or duplicated ID
  E4  a signal type outside the declared vocabulary
  E5  a row whose subsystem disagrees with its own name or its number
  E6  a planned name that is not the derivation of its own row, or a
      current name that is not that planned name
  E7  a row that no longer carries the name the pin used to have

WHY E7 EXISTS
=============
Queue item 10.2 renamed all 40 pins, so ``current name`` holds the new
name and the old one would have gone with it. 267 MB of signal history
on the operator's disk is written under the OLD names, and those
records join to this register through that string alone.

The column is also load-bearing for E6. ``planned_name`` derives the
slug from the name that is still spelled ``subsystem.slug``, which
after the rename is the PREVIOUS name. Blank the column and the
derivation has nothing to read.

CONTROLS
========
``--selftest`` plants one defect of each class, confirms the checker
reports it, and confirms a clean pin reports nothing. A checker with no
planted-failure control is a claim about the checker, not about the
tree.

Three properties, each of them bought by a measured failure:

EVERY FIRE HALF IS SCOPED TO ITS OWN PLANT. Asking "did any problem
start with E9?" is answered by ANY E9 in the tree, including a real one
that has nothing to do with the plant. Measured 2026-08-20: with the E9
plant neutered so it carried no defect, the control still reported
PASS.

E8 AND E9 PLANT SOURCE, NOT ``Pin`` OBJECTS. A fabricated Pin skips
``_scan_module``, ``_call_spans``, ``collect_pins`` and
``render_pin_name`` entirely, so it cannot show whether a rule sees a
violation written in real code. The planted module goes to a temporary
directory, is read back through the checker's own collection path, and
is removed again on every path including failure.

THE SIGNAL SEPARATES A BROKEN CONTROL FROM A KNOWN DEFECT. A control
may be DECLARED red against a defect that is filed and owned elsewhere;
that red is expected and does not move the verdict. Anything else does.
The exit code answers one question -- did every control behave as
declared -- so deleting a rule's detection now turns its own control
red and turns the summary line and the exit code with it. The plain run
carries the same check, because a green banner from an unproven
instrument says nothing.
"""
from __future__ import annotations

import argparse
import ast
import dataclasses
import json
import re
import shutil
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from tools.harness.watchdog_archetype import _iter_python, _scan_module, is_exempt

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = Path("docs/EMITTER_IDENTIFICATION.md")

SIGNAL_TYPES: tuple[str, ...] = (
    "counter", "gauge", "event", "state_transition",
    "postcondition", "invariant",
)
"""The closed vocabulary. Every term is established terminology:
counter and gauge are Prometheus / OpenTelemetry instrument types, event
is an OpenTelemetry Event, state_transition is finite-state-machine
terminology, and postcondition and invariant are Hoare-logic and
design-by-contract assertion terms. The registry names the source of
each and gives one example pin.
"""

ID_RE = re.compile(r"^(\d{2})-(\d{3})$")
SOURCE_RE = re.compile(r"^(.+):(\d+)$")
SUBSYSTEM_RE = re.compile(r"^[a-z][a-z0-9_]*$")

MAIN_HEADER = ("ID", "subsystem", "signal type", "duration",
               "current name", "previous name", "source", "observes")
PLANNED_HEADER = ("ID", "planned name")
SUBSYS_HEADER = ("subsystem", "number", "pins")

_MAIN_COLS = len(MAIN_HEADER)
_PLANNED_COLS = len(PLANNED_HEADER)
_SUBSYS_COLS = len(SUBSYS_HEADER)
_PLANNED_FIELDS = 5


# --------------------------------------------------------------------- #
# The left side: pins in src                                            #
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class Pin:
    """One pin call site and the name string it passes to the wire."""

    file: str
    line: int
    callee: str
    name: str
    dynamic: bool
    # E9 — does this call site pass `actual` and `expected` as the SAME
    # EXPRESSION? Compared by AST dump, so formatting and whitespace do
    # not hide it and a textually different but equivalent expression is
    # NOT claimed to be equal -- this reports only what it can prove.
    vacuous_check: bool = False
    # E8 — does this call site pass `duration=`?
    #
    # Defaulted so any other construction of a Pin keeps working. Read
    # from the AST call node, never from the source text: a `duration`
    # appearing in a comment or a context dict is not the keyword.
    carries_duration: bool = False


def render_pin_name(node: ast.Call) -> tuple[str, bool]:
    """Render the pin's name; say whether any part is built at run time.

    A run-time leaf renders as ``{}``. ``f"ta.raw.{indicator}"`` becomes
    ``ta.raw.{}``: the subsystem is decidable from the source even
    though the leaf is not, so the row can still be filed under its
    subsystem.
    """
    arg: ast.expr | None = None
    if node.args:
        arg = node.args[0]
    else:
        for keyword in node.keywords:
            if keyword.arg == "name":
                arg = keyword.value
                break
    if arg is None:
        return ("<no name argument>", True)
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return (arg.value, False)
    if isinstance(arg, ast.JoinedStr):
        parts = [
            piece.value
            if isinstance(piece, ast.Constant)
            and isinstance(piece.value, str) else "{}"
            for piece in arg.values
        ]
        return ("".join(parts), True)
    return (f"<built at run time: {type(arg).__name__}>", True)


def _call_spans(tree: ast.AST) -> dict[tuple[int, str], ast.Call]:
    """Map (line, callee) to its call node.

    Keyed by line AND callee, never by line alone. A line-only key was
    measured overwriting itself on 2026-08-13, which read four pins'
    payloads off the wrong call.
    """
    spans: dict[tuple[int, str], ast.Call] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            callee = func.id
        elif isinstance(func, ast.Attribute):
            receiver = func.value
            head = (receiver.id if isinstance(receiver, ast.Name)
                    else getattr(receiver, "attr", ""))
            callee = f"{head}.{func.attr}"
        else:
            continue
        spans[(node.lineno, callee)] = node
    return spans


def collect_pins(src_root: Path, repo_root: Path) -> list[Pin]:
    """Collect every pin under src_root, in (file, line) order."""
    pins: list[Pin] = []
    for path in _iter_python(src_root):
        if is_exempt(path):
            continue
        calls, err = _scan_module(path)
        if err or not calls:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        spans = _call_spans(tree)
        for call in calls:
            node = spans.get((call.line, call.callee))
            if node is None:
                msg = (f"no call node for pin {call.callee} at "
                       f"{path}:{call.line}")
                raise LookupError(msg)
            name, dynamic = render_pin_name(node)
            has_duration = any(
                kw.arg == "duration" for kw in node.keywords)
            _kw = {k.arg: k.value for k in node.keywords if k.arg}
            _act, _exp = _kw.get("actual"), _kw.get("expected")
            is_vacuous = (
                _act is not None and _exp is not None
                and ast.dump(_act) == ast.dump(_exp))
            pins.append(Pin(
                file=path.resolve().relative_to(repo_root).as_posix(),
                line=call.line, callee=call.callee,
                name=name, dynamic=dynamic,
                carries_duration=has_duration,
                vacuous_check=is_vacuous))
    pins.sort(key=lambda pin: (pin.file, pin.line))
    return pins


# --------------------------------------------------------------------- #
# The right side: rows in the registry                                  #
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class Row:
    """One registry row."""

    emitter_id: str
    subsystem: str
    signal_type: str
    name: str
    previous_name: str
    file: str
    line: int
    observes: str
    doc_line: int
    # 10.3 -- the DECLARED duration disposition, verbatim from the cell.
    #
    # Defaulted so any other construction of a Row keeps working, and so
    # a row written before the column existed still parses. The default
    # is NOT a pass: E10 refuses an empty cell, which is how a row that
    # skipped the column is caught rather than read as "no duration".
    duration: str = ""


@dataclass
class Registry:
    """The parsed registry: three tables and any parse trouble."""

    rows: list[Row]
    planned: dict[str, str]
    subsystem_numbers: dict[str, str]
    parse_errors: list[str]


def _cells(line: str) -> list[str]:
    """Split one markdown table row into stripped, unbackticked cells."""
    return [cell.strip().strip("`").strip()
            for cell in line.strip().strip("|").split("|")]


def _is_header(cells: list[str], header: tuple[str, ...]) -> bool:
    """Say whether these cells are the header row of this table."""
    if len(cells) != len(header):
        return False
    return all(cell.lower().startswith(want.lower())
               for cell, want in zip(cells, header, strict=True))


def _table_body(lines: list[str],
                header: tuple[str, ...]) -> list[tuple[int, list[str]]]:
    """Return (line number, cells) for every body row of one table."""
    body: list[tuple[int, list[str]]] = []
    inside = False
    for number, raw in enumerate(lines, start=1):
        if not raw.lstrip().startswith("|"):
            inside = False
            continue
        cells = _cells(raw)
        if _is_header(cells, header):
            inside = True
            continue
        if not inside:
            continue
        if all(cell and set(cell) <= {"-", ":"} for cell in cells):
            continue
        body.append((number, cells))
    return body


def _parse_main(lines: list[str],
                errors: list[str]) -> list[Row]:
    """Parse the one-row-per-emitter table."""
    rows: list[Row] = []
    for number, cells in _table_body(lines, MAIN_HEADER):
        if len(cells) != _MAIN_COLS:
            errors.append(f"line {number}: expected {_MAIN_COLS} cells, "
                          f"found {len(cells)}")
            continue
        (emitter_id, subsystem, signal_type, duration, name,
         previous_name, source, observes) = cells
        match = SOURCE_RE.match(source)
        if match is None:
            errors.append(
                f"line {number}: source {source!r} is not path:line")
            continue
        rows.append(Row(
            emitter_id=emitter_id, subsystem=subsystem,
            signal_type=signal_type, name=name,
            previous_name=previous_name,
            file=match.group(1), line=int(match.group(2)),
            observes=observes, doc_line=number,
            duration=duration))
    return rows


def _parse_pairs(lines: list[str], header: tuple[str, ...], width: int,
                 errors: list[str]) -> dict[str, str]:
    """Parse a two-or-three column lookup table into {first: second}."""
    out: dict[str, str] = {}
    for number, cells in _table_body(lines, header):
        if len(cells) != width:
            errors.append(f"line {number}: {header[0]} table needs "
                          f"{width} cells, found {len(cells)}")
            continue
        out[cells[0]] = cells[1]
    return out


def parse_registry(text: str) -> Registry:
    """Parse the three tables out of the registry markdown."""
    lines = text.splitlines()
    errors: list[str] = []
    return Registry(
        rows=_parse_main(lines, errors),
        planned=_parse_pairs(lines, PLANNED_HEADER, _PLANNED_COLS, errors),
        subsystem_numbers=_parse_pairs(
            lines, SUBSYS_HEADER, _SUBSYS_COLS, errors),
        parse_errors=errors)


# --------------------------------------------------------------------- #
# The comparison                                                        #
# --------------------------------------------------------------------- #


def slug_of(name: str) -> str:
    """Return the part of a current pin name after its subsystem token."""
    head, _, tail = name.partition(".")
    return tail or head


def planned_name(row: Row) -> str:
    """Derive the 10.2 name from this row's own fields.

    The slug comes from the PREVIOUS name, not the current one. Before
    10.2 landed those were the same field and `slug_of(row.name)` was
    correct. It is not correct now: `slug_of` returns everything after
    the first dot, so a current name of
    `bot.01.001.postcondition.capital_reservation` yields
    `01.001.postcondition.capital_reservation` and the derivation
    repeats its own middle. The previous name is the one still spelled
    `subsystem.slug`.
    """
    subsystem_number, emitter_number = row.emitter_id.split("-", 1)
    return (f"{row.subsystem}.{subsystem_number}.{emitter_number}."
            f"{row.signal_type}.{slug_of(row.previous_name)}")


def _check_membership(pins: list[Pin], reg: Registry) -> list[str]:
    """Compare the two multisets keyed on (file, name)."""
    problems: list[str] = []
    pin_counts = Counter((pin.file, pin.name) for pin in pins)
    row_counts = Counter((row.file, row.name) for row in reg.rows)
    for key, seen in sorted(pin_counts.items()):
        missing = seen - row_counts.get(key, 0)
        if missing > 0:
            where = sorted(pin.line for pin in pins
                           if (pin.file, pin.name) == key)
            problems.append(
                f"E1 {missing} pin(s) absent from the registry: "
                f"{key[1]} in {key[0]} at line(s) "
                f"{', '.join(str(line) for line in where)}")
    for key, seen in sorted(row_counts.items()):
        extra = seen - pin_counts.get(key, 0)
        if extra > 0:
            ids = sorted(row.emitter_id for row in reg.rows
                         if (row.file, row.name) == key)
            problems.append(
                f"E2 {extra} registry row(s) with no pin in src: "
                f"{key[1]} in {key[0]}, ID(s) {', '.join(ids)}")
    return problems


def _check_identity(row: Row, match: re.Match[str],
                    reg: Registry) -> list[str]:
    """Check one row's subsystem against its name and its number."""
    problems: list[str] = []
    if not SUBSYSTEM_RE.match(row.subsystem):
        problems.append(
            f"E5 {row.emitter_id}: subsystem {row.subsystem!r} is not a "
            f"lowercase token")
    elif row.name.split(".", 1)[0] != row.subsystem:
        problems.append(
            f"E5 {row.emitter_id}: subsystem {row.subsystem!r} is not "
            f"the prefix of name {row.name!r}; SignalSink.by_subsystem "
            f"would file it under {row.name.split('.', 1)[0]!r}")
    declared = reg.subsystem_numbers.get(row.subsystem)
    if declared is None:
        problems.append(
            f"E5 {row.emitter_id}: subsystem {row.subsystem!r} has no "
            f"row in the subsystem-number table")
    elif declared != match.group(1):
        problems.append(
            f"E5 {row.emitter_id}: ID carries subsystem number "
            f"{match.group(1)} but {row.subsystem!r} is numbered "
            f"{declared}")
    return problems


def _check_planned(row: Row, reg: Registry) -> list[str]:
    """Check the planned name is this row's own derivation, and landed.

    Two assertions, not one. The derivation says the target was
    computed and not typed. The equality with `current name` says the
    rename actually reached the source -- 10.2 is done, and a row that
    quietly reverted would say so here rather than at the next reader.
    """
    want = planned_name(row)
    got = reg.planned.get(row.emitter_id)
    if got is None:
        return [f"E6 {row.emitter_id}: no planned name recorded"]
    if got != want:
        return [(f"E6 {row.emitter_id}: planned name {got!r} is not the "
                 f"derivation of its own row, which is {want!r}")]
    if row.name != want:
        return [(f"E6 {row.emitter_id}: current name {row.name!r} is not "
                 f"the planned name {want!r}; the rename did not land on "
                 f"this row")]
    if len(got.split(".", _PLANNED_FIELDS - 1)) != _PLANNED_FIELDS:
        return [(f"E6 {row.emitter_id}: planned name {got!r} does not "
                 f"have {_PLANNED_FIELDS} dotted fields")]
    return []


def _check_previous(row: Row) -> list[str]:
    """Check the row still carries the name its pin used to have.

    Two ways the column dies. It can be blanked, which is the obvious
    one. It can also be REFILLED with the current name, which is what
    happened on the first attempt at 10.2: the rename rewrote both
    name-bearing columns, so every row looked populated and not one
    carried the old key. Emptiness alone would not have caught that.
    """
    got = row.previous_name.strip()
    if not got:
        return [f"E7 {row.emitter_id}: previous name is empty; the "
                f"on-disk history keyed by the old name has no way "
                f"back to this row"]
    if got == row.name:
        return [f"E7 {row.emitter_id}: previous name {got!r} is the "
                f"current name, so the row records no rename"]
    return []


def _check_rows(reg: Registry) -> list[str]:
    """Check every row's ID, signal type, subsystem and planned name."""
    problems: list[str] = []
    seen_ids: dict[str, int] = {}
    for row in reg.rows:
        match = ID_RE.match(row.emitter_id)
        if match is None:
            problems.append(
                f"E3 malformed ID {row.emitter_id!r} at registry line "
                f"{row.doc_line}; the format is NN-EEE")
            continue
        if row.emitter_id in seen_ids:
            problems.append(
                f"E3 duplicate ID {row.emitter_id} at registry line "
                f"{row.doc_line}; first seen at line "
                f"{seen_ids[row.emitter_id]}")
        else:
            seen_ids[row.emitter_id] = row.doc_line
        if row.signal_type not in SIGNAL_TYPES:
            problems.append(
                f"E4 {row.emitter_id}: signal type {row.signal_type!r} "
                f"is not in the vocabulary {', '.join(SIGNAL_TYPES)}")
        problems.extend(_check_identity(row, match, reg))
        problems.extend(_check_previous(row))
        problems.extend(_check_planned(row, reg))
    problems.extend(
        f"E6 planned name recorded for {orphan}, which has no row in "
        f"the main table"
        for orphan in sorted(set(reg.planned) - set(seen_ids)))
    return problems


DURATION_TYPE = "postcondition"
"""The ONLY signal type permitted to carry an operation duration.

Operator, 2026-08-19: emitters must share one basic shape, with a handful
of variants adapted to their monitoring role. This is one of those
variants, and it is not an aesthetic preference -- it follows from what
the six types MEAN.

A `postcondition` asserts something AFTER an operation completes, so it
is the only type with a bounded operation behind it. A `counter` reads a
value. A `gauge` samples one. An `invariant` compares two things. An
`event` and a `state_transition` happen at a point. None of those has a
"how long did it take" to report, so a duration on one would be
FABRICATED -- and item 17 computes health from it.

MEASURED 2026-08-19 across all 40 emitters: durations appear on
`postcondition` and on nothing else, zero exceptions. This rule makes
that regularity enforced rather than emergent. See
docs/audits/2026-08-19_emitter_duration_classification.md.
"""


def _check_duration_shape(pins: list[Pin]) -> list[str]:
    """E8 — a duration may only ride on a postcondition.

    Reads the SIGNAL TYPE OUT OF THE NAME rather than the register, so a
    call site that adds `duration=` without touching the register is
    still caught. A dynamic name cannot be typed and is skipped: it is
    E6's job to report those, and failing here as well would report one
    defect twice.
    """
    problems: list[str] = []
    for pin in pins:
        if not pin.carries_duration or pin.dynamic:
            continue
        parts = pin.name.split(".")
        if len(parts) < 4:
            continue
        signal_type = parts[3]
        if signal_type != DURATION_TYPE:
            problems.append(
                f"E8 {pin.name} at {pin.file}:{pin.line}: a duration may "
                f"only ride on a {DURATION_TYPE}, not a {signal_type}. "
                f"Only a postcondition follows a completed operation; on "
                f"any other type the number is fabricated.")
    return problems


DURATION_DISPOSITIONS: tuple[str, ...] = (
    "measured", "forbidden", "none", "deferred",
)
"""The closed vocabulary of the register's `duration` column.

10.3. Operator, on the standing queue: "TIME -- duration in the pin
record. MANDATORY, not conditional." A sweep that fills the field once
decays; a rule does not. So every row DECLARES what it does about a
duration, the declaration is one of four terms, and the checker holds
the declaration against the code.

    measured    the call site brackets an operation and passes
                `duration=`. The text after the colon names WHAT THE
                BRACKET SPANS, because a bracket that drifts onto the
                wrong work still passes an existence check.
    forbidden   the signal type is not `postcondition`, so rule E8
                refuses a duration here. No reason is written: the
                reason is the type, the type is in the same row, and
                E12 checks the two agree.
    none        a `postcondition` whose site owns no interval -- it
                reads a value back, or another pin owns the operation.
                A number here would be FABRICATED, and item 17 computes
                health from it. The reason says which.
    deferred    a `postcondition` whose site DOES own a bounded
                operation that nobody has bracketed yet. The reason
                names what is missing.

`none` AND `deferred` ARE NOT THE SAME CLAIM, AND MERGING THEM WOULD
LOSE THE ONE THAT IS ACTIONABLE. `none` says a duration cannot be
honest here, ever. `deferred` says it can, and is not written yet. One
message covering both causes is the disjunction defect this repo keeps
paying for -- a reader given one word cannot tell "leave it alone" from
"this is the next unit".
"""

_NEEDS_REASON: tuple[str, ...] = ("measured", "none", "deferred")
"""Dispositions whose cell must carry text after the colon.

`forbidden` is excluded and is the only one: its reason is the signal
type, which is a machine-checked field in the same row.
"""


def _disposition_of(row: Row) -> tuple[str, str]:
    """Split one duration cell into (term, reason).

    Returns ("", "") for an empty cell, which E10 then reports. The
    term comes from before the FIRST colon, so a reason may hold one.
    """
    cell = (row.duration or "").strip()
    if not cell:
        return ("", "")
    term, _, reason = cell.partition(":")
    return (term.strip(), reason.strip())


def _check_duration_declared(pins: list[Pin],
                             reg: Registry) -> list[str]:
    """E10, E11, E12 -- every row declares a duration, and it is true.

    THIS IS THE RULE THAT MAKES 10.3 STICK. `_check_duration_shape`
    (E8) already refuses a duration on the wrong signal type, but it
    only ever looks at a call site that HAS one. Nothing looked at the
    58 sites that had none, so a pin could be added, migrated or
    rewritten with no duration and no statement about why, and every
    check stayed green. That is the silence the emitter network exists
    to remove, reproduced inside the checker for the network.

    Three findings, deliberately separate.

      E10  the cell does not declare anything the vocabulary knows.
           An empty cell lands here, which is what catches a row added
           after this change that skipped the column.
      E11  the declaration and the CODE disagree. Read off the AST, so
           a `duration` word in a comment or a context dict is not
           mistaken for the keyword.
      E12  the declaration and the SIGNAL TYPE disagree.

    A row with no pin is not reported here. That is E1/E2's finding and
    reporting it twice would name one defect as two.
    """
    problems: list[str] = []
    by_key = {(pin.file, pin.name): pin for pin in pins}
    for row in reg.rows:
        term, reason = _disposition_of(row)
        if term not in DURATION_DISPOSITIONS:
            problems.append(
                f"E10 {row.emitter_id}: duration cell "
                f"{row.duration!r} does not start with one of "
                f"{', '.join(DURATION_DISPOSITIONS)}. Every row must "
                f"say what it does about a duration; an unfilled cell "
                f"is not 'no duration', it is no statement.")
            continue
        if term in _NEEDS_REASON and not reason:
            problems.append(
                f"E10 {row.emitter_id}: duration {term!r} carries no "
                f"reason. Write it as '{term}: <reason>' -- for "
                f"'measured' the reason names what the bracket spans, "
                f"and for the others it says why no bracket exists.")
            continue
        if (term == "forbidden") is not (row.signal_type != DURATION_TYPE):
            problems.append(
                f"E12 {row.emitter_id}: duration {term!r} disagrees "
                f"with signal type {row.signal_type!r}. Only a "
                f"{DURATION_TYPE} may carry a duration, so every other "
                f"type declares 'forbidden' and a {DURATION_TYPE} "
                f"never does.")
            continue
        pin = by_key.get((row.file, row.name))
        if pin is None:
            continue
        if term == "measured" and not pin.carries_duration:
            problems.append(
                f"E11 {row.emitter_id}: the row declares a measured "
                f"duration, but {row.file}:{pin.line} passes no "
                f"`duration=`. The register is claiming a number the "
                f"record never carries.")
        elif term != "measured" and pin.carries_duration:
            problems.append(
                f"E11 {row.emitter_id}: the row declares {term!r}, "
                f"but {row.file}:{pin.line} passes `duration=`. Either "
                f"the bracket is wrong or the row is stale; a reader "
                f"cannot tell which while they disagree.")
    return problems


def _check_vacuous(pins: list[Pin]) -> list[str]:
    """E9 — a CHECK whose `actual` and `expected` are the same expression.

    S9: `actual` is mandatory; `expected=None` means a deliberate SAMPLE.
    A CHECK that compares an expression to itself derives `ok` True on
    every call, so it can never fail -- it reports the request back as
    though it were the result, and a green record from it is evidence of
    nothing.

    THE RULE IS ENCODED, NOT THE LIST. Three emitters were recorded as
    having this shape. Measured 2026-08-20, only one still did: the other
    two had been repaired or were deliberate samples, and the list had
    gone stale while the defect class had not. A list needs re-reading; a
    rule does not.

    Reports only what it can PROVE, by comparing the AST dumps. Two
    expressions that are equivalent but written differently are not
    claimed to be equal here -- that would be a guess, and this check
    exists to remove guesses.
    """
    return [
        f"E9 {pin.name} at {pin.file}:{pin.line}: `actual` and "
        f"`expected` are the same expression, so `ok` derives True on "
        f"every call and this check can never fail. Compare the OBSERVED "
        f"value against the DECLARED expectation, or declare it a sample "
        f"by dropping `expected`."
        for pin in pins if pin.vacuous_check
    ]


def check(pins: list[Pin], reg: Registry) -> list[str]:
    """Return every problem found. An empty list is a clean run."""
    problems = [f"E0 registry parse: {err}" for err in reg.parse_errors]
    problems.extend(_check_membership(pins, reg))
    problems.extend(_check_rows(reg))
    problems.extend(_check_duration_shape(pins))
    problems.extend(_check_duration_declared(pins, reg))
    problems.extend(_check_vacuous(pins))
    return problems


def line_warnings(pins: list[Pin], reg: Registry) -> list[str]:
    """Report rows whose recorded line no longer holds that pin.

    A warning, not a failure. Line numbers move on every edit above a
    pin; failing on drift would make the check fire for reasons that
    have nothing to do with losing track of an emitter.
    """
    live = {(pin.file, pin.name, pin.line) for pin in pins}
    return [
        f"W1 {row.emitter_id}: recorded at {row.file}:{row.line}, but no "
        f"pin named {row.name} sits on that line now"
        for row in reg.rows
        if (row.file, row.name, row.line) not in live
    ]


# --------------------------------------------------------------------- #
# Controls                                                              #
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class Control:
    """One control, and how this control is ALLOWED to behave.

    Three facts, not one.

    ``ok``          the rule under test behaved the way a working rule
                    must -- it fired on the plant, or stayed silent on
                    the clean pin.
    ``known``       non-empty when this control is DECLARED red against
                    a defect that is already filed and owned somewhere
                    else. The text names the owner.
    ``as_declared`` the red that arrived is that same red, and not a
                    different one wearing its label.

    Splitting them is the whole point of this type. Before it, one
    permanently failing control held the exit code at 1 on every run,
    so a control that genuinely BROKE changed nothing a reader could
    act on: same summary line, same exit code, one word different deep
    in the body. A signal that is red whatever happens carries no
    information, and the first thing anyone does with it is stop
    reading it.
    """

    label: str
    ok: bool
    detail: str
    known: str = ""
    as_declared: bool = True

    @property
    def state(self) -> str:
        """PASS, KNOWN-RED, STALE or BROKEN.

        STALE is a control that was declared red and came back green.
        That is not good news to be swallowed: the declaration is now
        false, and while it stands the control reports nothing. The
        declaration has to be deleted, so this state is not healthy.
        """
        if self.ok:
            return "STALE" if self.known else "PASS"
        if self.known and self.as_declared:
            return "KNOWN-RED"
        return "BROKEN"

    @property
    def healthy(self) -> bool:
        """True when this control behaved exactly as declared."""
        return self.state in ("PASS", "KNOWN-RED")


_PLANT_MODULE = "planted_emitters.py"

_PLANT_SOURCE = '''"""Planted pins for E8 and E9 -- source, not Pin objects.

Written to a temporary directory, read back through the checker's own
collection path, and deleted again. It is never written into the
repository and never under the runtime directory.
"""
from src.core.signal_contract import emit


def planted_pins() -> None:
    """Five call sites: two for E8, three for E9."""
    value = 1.0
    emit("ghost.99.002.counter.not_a_postcondition",
         actual=value, duration=0.5)
    emit("ghost.99.003.postcondition.allowed",
         actual=value, duration=0.5)
    emit("ghost.99.004.postcondition.compares_itself",
         actual=value, expected=value)
    emit("ghost.99.005.postcondition.compares_something",
         actual=value, expected=2.0)
    emit("ghost.99.006.postcondition.positional_vacuous", value, value)
'''

_PLANT_NAMES = {
    "e8_fires": "ghost.99.002.counter.not_a_postcondition",
    "e8_quiet": "ghost.99.003.postcondition.allowed",
    "e9_fires": "ghost.99.004.postcondition.compares_itself",
    "e9_quiet": "ghost.99.005.postcondition.compares_something",
    "e9_positional": "ghost.99.006.postcondition.positional_vacuous",
}


def _planted_pins() -> tuple[list[Pin], str]:
    """Write the planted module, collect its pins, remove it.

    WHY SOURCE AND NOT ``dataclasses.replace(pins[0], ...)``
    =======================================================
    A fabricated Pin hands the rule a flag the control set itself. It
    proves the rule can read a boolean. It cannot prove the rule ever
    SEES a violation written in real code, because the whole path from
    text to Pin -- ``_scan_module``, ``_call_spans``, ``collect_pins``,
    ``render_pin_name`` -- is skipped.

    That gap is not theoretical. Both E8 and E9 read their flags from
    ``node.keywords`` alone, so the same violation written with
    positional arguments produces a Pin with the flag unset and both
    rules go silent. No Pin-level control can see that, because it
    never parses anything. The positional call site in the planted
    module is there for exactly that reason.

    Returns ``(pins, error)``; the error string is empty on success.
    The temporary directory is removed on every path, failure included.
    """
    root = Path(tempfile.mkdtemp(prefix="emitter_control_plant_")).resolve()
    try:
        path = root / _PLANT_MODULE
        path.write_bytes(_PLANT_SOURCE.encode("utf-8"))
        if is_exempt(path):
            return ([], (f"the planted module at {path} is exempt "
                         f"from the scan, so it would prove "
                         f"nothing"))
        return (collect_pins(root, root), "")
    except (OSError, SyntaxError, ValueError, LookupError) as exc:
        return ([], f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _variant(reg: Registry, rows: list[Row] | None = None,
             planned: dict[str, str] | None = None,
             numbers: dict[str, str] | None = None) -> Registry:
    """Copy the registry with one part replaced."""
    return Registry(
        rows=list(reg.rows) if rows is None else rows,
        planned=dict(reg.planned) if planned is None else planned,
        subsystem_numbers=(dict(reg.subsystem_numbers)
                           if numbers is None else numbers),
        parse_errors=[])


def _duration_controls(
        pins: list[Pin], reg: Registry, first: Row,
        fired: Callable[..., tuple[bool, str]]) -> list[Control]:
    """Plant E10, E11 and E12 against real rows and read them back.

    Split out of `_controls`, which had grown past the archetype's
    statement and length ceilings once these ten arrived. `fired` is
    passed in rather than redefined, so both halves of this file ask
    the same scoping question of every plant.
    """
    results: list[Control] = []
    # 10.3 -- E10, E11 AND E12, EACH PLANTED AGAINST A REAL ROW.
    #
    # Every half is scoped to the ID it planted, for the reason written
    # at the top of this function: a global "did any E10 fire?" is
    # answered by anybody's E10 and measures nothing about this plant.
    #
    # THE SILENCE HALVES ARE NOT THE CLEAN-TREE CONTROL. That one says
    # the tree as it stands is quiet. These say the rule stays quiet on
    # a row that is CHANGED and still correct -- which is what separates
    # a rule from a rule that fires on any edit.
    _measured = next(
        (r for r in reg.rows if _disposition_of(r)[0] == "measured"), None)
    _forbidden = next(
        (r for r in reg.rows if _disposition_of(r)[0] == "forbidden"), None)
    results.append(Control(
        "the registry holds a measured row and a forbidden row to plant",
        _measured is not None and _forbidden is not None,
        f"measured={_measured.emitter_id if _measured else 'none'}, "
        f"forbidden={_forbidden.emitter_id if _forbidden else 'none'}"))

    if _measured is not None and _forbidden is not None:
        def _swap(row: Row, duration: str) -> Registry:
            """Copy the registry with one row's duration cell replaced."""
            return _variant(reg, rows=[
                dataclasses.replace(r, duration=duration)
                if r.emitter_id == row.emitter_id else r
                for r in reg.rows])

        blank = check(pins, _swap(first, ""))
        ok, detail = fired(blank, "E10", first.emitter_id, "does not start")
        results.append(Control(
            "E10 fires when a duration cell is empty", ok, detail))

        coined = check(pins, _swap(first, "sometimes: when it feels right"))
        ok, detail = fired(coined, "E10", first.emitter_id, "does not start")
        results.append(Control(
            "E10 fires on a term outside the vocabulary", ok, detail))

        bare = check(pins, _swap(first, "none"))
        ok, detail = fired(bare, "E10", first.emitter_id, "carries no")
        results.append(Control(
            "E10 fires when a declaration carries no reason", ok, detail))

        kept = check(pins, _swap(first, "none: a rewritten but valid reason"))
        noise = [q for q in kept
                 if q.startswith(("E10", "E11", "E12"))
                 and first.emitter_id in q]
        results.append(Control(
            "E10/E11/E12 stay silent on a re-worded but correct cell",
            not noise, "; ".join(noise) or "silent"))

        # E11 -- the declaration against the CODE, both ways round.
        demoted = check(pins, _swap(
            _measured, "none: claims the site owns no interval"))
        ok, detail = fired(demoted, "E11", _measured.emitter_id,
                           "passes `duration=`")
        results.append(Control(
            "E11 fires when a row denies a duration the site passes",
            ok, detail))

        promoted = check(pins, _swap(
            first, "measured: claims a bracket that is not there"))
        ok, detail = fired(promoted, "E11", first.emitter_id,
                           "passes no `duration=`")
        results.append(Control(
            "E11 fires when a row claims a duration the site never passes",
            ok, detail))

        quiet11 = [q for q in check(pins, _swap(
            _measured, "measured: a re-worded description of the bracket"))
            if q.startswith("E11") and _measured.emitter_id in q]
        results.append(Control(
            "E11 is silent when the row and the site agree",
            not quiet11, "; ".join(quiet11) or "silent"))

        # E12 -- the declaration against the SIGNAL TYPE, both ways round.
        mistyped = check(pins, _swap(
            _forbidden, "none: claims a postcondition's disposition"))
        ok, detail = fired(mistyped, "E12", _forbidden.emitter_id,
                           "disagrees with signal type")
        results.append(Control(
            "E12 fires when a non-postcondition declares anything but "
            "forbidden", ok, detail))

        overreach = check(pins, _swap(first, "forbidden"))
        ok, detail = fired(overreach, "E12", first.emitter_id,
                           "disagrees with signal type")
        results.append(Control(
            "E12 fires when a postcondition declares forbidden", ok, detail))

        quiet12 = [q for q in check(pins, _swap(_forbidden, "forbidden"))
                   if q.startswith("E12") and _forbidden.emitter_id in q]
        results.append(Control(
            "E12 is silent when the disposition matches the type",
            not quiet12, "; ".join(quiet12) or "silent"))

    return results


def _controls(pins: list[Pin],
              reg: Registry) -> list[Control]:
    """Plant one defect of each class and read the problem list back.

    EVERY HALF IS SCOPED TO ITS OWN PLANT
    =====================================
    A fire half used to ask "did any problem start with E9?". Measured
    twice, independently, on 2026-08-20: with the E9 plant neutered so
    that it carried no defect at all, the control still reported PASS,
    because the tree holds one real E9 and the question was global. The
    same was measured for E8 with a real violation added elsewhere. A
    control that a stranger's defect can satisfy is not measuring its
    own rule.

    So every fire half now names the identity it planted -- a pin name,
    a registry ID, a phantom row -- and asks whether the rule fired ON
    THAT. The silence halves were already scoped this way, and the
    reason written beside them applies to both halves equally.
    """
    def fired(problems: list[str], code: str,
              *needles: str) -> tuple[bool, str]:
        """Say whether `code` fired ON THE PLANTED THING.

        `needles` are the identity of the plant, and every one of them
        must appear in the problem line. A hit that names something
        else is somebody else's finding and is not evidence about this
        rule.
        """
        hits = [p for p in problems
                if p.startswith(code) and all(n in p for n in needles)]
        return (bool(hits), "; ".join(hits) or "silent")

    results: list[Control] = []

    # THE DECLARATION THAT USED TO SIT HERE IS RETIRED, 2026-08-20.
    #
    # This control carried `known=` naming one real E9 in the tree, on
    # `bot.01.002.postcondition.capital_reservation`, and `as_declared=`
    # requiring the red that arrived to be that one. Issue #21 repaired
    # that pin: it now reads the HELD reservation against the NEEDED
    # quantity instead of comparing the request with itself.
    #
    # A declaration that outlives its defect is not harmless. While it
    # stands the control reports nothing -- a green comes back STALE
    # rather than PASS, and any red at all is admitted under the old
    # excuse. So it goes out in the same unit as the repair, and the
    # control is a plain one again: the tree is clean, or it is not.
    clean = check(pins, reg)
    results.append(Control(
        label="clean tree reports nothing",
        ok=not clean,
        detail="; ".join(clean) or "silent"))

    dropped_row = reg.rows[0]
    dropped = check(pins, _variant(reg, rows=reg.rows[1:]))
    ok, detail = fired(dropped, "E1",
                       f"{dropped_row.name} in {dropped_row.file}")
    results.append(Control(
        "E1 fires when a row is removed", ok, detail))

    phantom = Row(
        emitter_id="99-001", subsystem="ghost", signal_type="gauge",
        name="ghost.99.001.gauge.not_a_pin",
        previous_name="ghost.not_a_pin",
        file="src/core/log_paths.py", line=1,
        observes="a row for a pin that does not exist", doc_line=0,
        duration="forbidden")
    added = check(pins, _variant(
        reg, rows=[*reg.rows, phantom],
        planned={**reg.planned, "99-001": "ghost.99.001.gauge.not_a_pin"},
        numbers={**reg.subsystem_numbers, "ghost": "99"}))
    ok, detail = fired(added, "E2", phantom.name, phantom.emitter_id)
    results.append(Control(
        "E2 fires when a phantom row is added", ok, detail))

    first = reg.rows[0]
    typed = check(pins, _variant(reg, rows=[
        dataclasses.replace(first, signal_type="vibe"), *reg.rows[1:]]))
    ok, detail = fired(typed, "E4", first.emitter_id, "'vibe'")
    results.append(Control(
        "E4 fires on a signal type outside the vocabulary", ok, detail))

    renumbered = check(pins, _variant(reg, rows=[
        dataclasses.replace(first, emitter_id="97-001"), *reg.rows[1:]]))
    ok, detail = fired(renumbered, "E5", "97-001",
                       f"{first.subsystem!r} is numbered")
    results.append(Control(
        "E5 fires when an ID carries the wrong subsystem number",
        ok, detail))

    blanked = check(pins, _variant(reg, rows=[
        dataclasses.replace(first, previous_name=""), *reg.rows[1:]]))
    ok, detail = fired(blanked, "E7", first.emitter_id,
                       "previous name is empty")
    results.append(Control(
        "E7 fires when a previous name is blanked", ok, detail))

    echoed = check(pins, _variant(reg, rows=[
        dataclasses.replace(first, previous_name=first.name),
        *reg.rows[1:]]))
    ok, detail = fired(echoed, "E7", first.emitter_id,
                       "is the current name")
    results.append(Control(
        "E7 fires when a previous name echoes the current name",
        ok, detail))

    # E8 and E9 are planted as SOURCE. See `_planted_pins`.
    planted, plant_error = _planted_pins()
    want = set(_PLANT_NAMES.values())
    got = want & {pin.name for pin in planted}
    results.append(Control(
        "the planted source module parses to its pins",
        not plant_error and got == want,
        plant_error or (
            f"collected {len(planted)} pin(s) from source"
            if got == want else
            f"collected {len(planted)} pin(s); missing "
            f"{', '.join(sorted(want - got))}")))
    with_plant = check([*pins, *planted], reg)

    ok, detail = fired(with_plant, "E8", _PLANT_NAMES["e8_fires"])
    results.append(Control(
        "E8 fires on a duration outside a postcondition, from source",
        ok, detail))

    # The other half: a duration ON a postcondition, out of the same
    # parsed module, must be silent. A rule that fires on everything is
    # not a rule. Scoped to the planted pin, because a global-silence
    # check breaks as soon as the tree holds a real violation, which is
    # when the rule is working.
    quiet8 = [p for p in with_plant
              if p.startswith("E8") and _PLANT_NAMES["e8_quiet"] in p]
    results.append(Control(
        "E8 is silent on a duration ON a postcondition, from source",
        not quiet8, "; ".join(quiet8) or "silent"))

    ok, detail = fired(with_plant, "E9", _PLANT_NAMES["e9_fires"])
    results.append(Control(
        "E9 fires on a check that can never fail, from source",
        ok, detail))

    quiet9 = [p for p in with_plant
              if p.startswith("E9") and _PLANT_NAMES["e9_quiet"] in p]
    results.append(Control(
        "E9 is silent on a check that can fail, from source",
        not quiet9, "; ".join(quiet9) or "silent"))

    # The blind spot, made visible. The same defect as the E9 plant
    # above, written with positional arguments. DECLARED red: the rule
    # reads `actual` and `expected` from `node.keywords` only, so this
    # pin arrives with the flag unset and E9 cannot see it. When the
    # detection repair lands, this control turns STALE and demands its
    # declaration be deleted -- which is how a blind spot gets closed
    # rather than commented on.
    ok, detail = fired(with_plant, "E9", _PLANT_NAMES["e9_positional"])
    results.append(Control(
        label=("E9 fires on a vacuous check written with positional "
               "arguments"),
        ok=ok, detail=detail,
        known=("`_check_vacuous` reads `actual` and `expected` from "
               "`node.keywords` only, so a positional call leaves the "
               "flag unset; owned by the detection repair, not by the "
               "controls"),
        as_declared=not ok))

    # 10.3 -- the duration column's own controls. Extracted into
    # `_duration_controls` rather than written inline: adding ten
    # controls here pushed `_controls` past the archetype's statement
    # and length ceilings, and the answer to a function that outgrew
    # its limit is to split it, never to quiet the rule that said so.
    results.extend(_duration_controls(pins, reg, first, fired))

    replanned = check(pins, _variant(
        reg, planned={**reg.planned, first.emitter_id: "made.up.name"}))
    ok, detail = fired(replanned, "E6", first.emitter_id, "made.up.name")
    results.append(Control(
        "E6 fires on a planned name that is not its own derivation",
        ok, detail))
    return results


def _selftest(pins: list[Pin], reg: Registry) -> int:
    """Run the controls and report at the surface that drives exit.

    The summary line and the exit code answer ONE question: did every
    control behave the way it was declared to behave? A known-red
    control that came back red is a declared fact about the tree and
    does not move that answer. A control that broke does.
    """
    write = sys.stdout.write
    results = _controls(pins, reg)
    for control in results:
        write(f"  [{control.state}] {control.label}\n")
        write(f"         {control.detail}\n")
        if control.known:
            write(f"         declared red: {control.known}\n")
    tally = Counter(control.state for control in results)
    unhealthy = [control for control in results if not control.healthy]
    write(f"controls: {tally['PASS']} passed, {tally['KNOWN-RED']} "
          f"known-red, {tally['BROKEN']} broken, {tally['STALE']} stale, "
          f"of {len(results)}\n")
    if unhealthy:
        write(f"SELFTEST FAIL {len(unhealthy)} control(s) did not behave "
              f"as declared: "
              f"{'; '.join(control.label for control in unhealthy)}\n")
        return 1
    write(f"SELFTEST OK {len(results)} control(s), every one behaved as "
          f"declared\n")
    return 0


# --------------------------------------------------------------------- #
# CLI                                                                   #
# --------------------------------------------------------------------- #


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Build the command line."""
    parser = argparse.ArgumentParser(
        description="check every pin in src has a registry row and back")
    parser.add_argument(
        "--root", default=str(REPO_ROOT),
        help="repository root (default: this file's repository)")
    parser.add_argument(
        "--registry", default=None,
        help=f"registry path (default: <root>/{REGISTRY_PATH.as_posix()})")
    parser.add_argument(
        "--selftest", action="store_true",
        help="plant one defect of each class and report whether "
             "every control behaved as declared")
    parser.add_argument(
        "--json", action="store_true", help="machine-readable output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Compare src against the registry; exit 1 on any problem."""
    args = _parse_args(argv)
    root = Path(args.root).resolve()
    registry_path = (Path(args.registry) if args.registry
                     else root / REGISTRY_PATH)
    write = sys.stdout.write

    if not registry_path.exists():
        write(f"registry not found: {registry_path}\n")
        return 2

    pins = collect_pins(root / "src", root)
    reg = parse_registry(
        registry_path.read_text(encoding="utf-8", errors="replace"))

    if args.selftest:
        write(f"controls against {len(pins)} pin(s) and "
              f"{len(reg.rows)} row(s)\n")
        return _selftest(pins, reg)

    problems = check(pins, reg)
    warnings = line_warnings(pins, reg)
    # The controls run on the PLAIN path too. A green banner is a claim
    # about the tree, and it is only worth the ink if the rules behind
    # it have been shown to fire on a planted defect on THIS run.
    # Measured 2026-08-20: with E9's detection deleted, this path
    # printed OK and exited 0 over a tree that holds a check which can
    # never fail. An unproven instrument reporting nothing is not the
    # same fact as a clean tree, and it must not print the same line.
    broken = [c for c in _controls(pins, reg) if not c.healthy]

    if args.json:
        write(json.dumps({
            "pins": len(pins), "rows": len(reg.rows),
            "problems": problems, "warnings": warnings,
            "broken_controls": [c.label for c in broken],
            "passed": not problems and not broken}, indent=2) + "\n")
        return 1 if (problems or broken) else 0

    write(f"pins in src  : {len(pins)}\n")
    write(f"registry rows: {len(reg.rows)}\n")
    if broken:
        write(f"instrument   : {len(broken)} control(s) did not behave as "
              f"declared: {'; '.join(c.label for c in broken)}\n")
        write("instrument   : these rules are NOT proven on this run, so "
              "a clean result below is evidence of nothing. Run "
              "--selftest.\n")
    else:
        write("instrument   : controls OK\n")
    for warning in warnings:
        write(f"  {warning}\n")
    if not problems and not broken:
        write("OK every pin has a row and every row has a pin\n")
        return 0
    for problem in problems:
        write(f"  {problem}\n")
    write(f"FAIL {len(problems)} problem(s), {len(broken)} broken "
          f"control(s)\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
