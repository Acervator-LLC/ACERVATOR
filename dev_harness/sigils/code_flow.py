"""`SIGIL` is CODE.FLOW on the `core` card; `flow_check` judges an input."""

import ast
import sys
from collections.abc import Collection, Sequence
from pathlib import Path

from .coding_input import (
    CONTENT_TIER,
    DATA_TYPE_TIER,
    INPUT_FORM,
    OWNER,
    READERS,
    SEPARATOR,
    data_type_fault,
    fault_file,
    locate,
)
from .coding_partition import SELECTION, selection
from .construct_rules import TOOL, take
from .core import (
    APPLICATION_SOURCE,
    FLAGS,
    Flag,
    FlagRow,
    Reading,
    Sigil,
    Verdict,
    in_application_source,
    judge,
    main,
)
from .fix_class import BY_FIX_CLASS, FOLLOW_ON
from .ruff_rules import RUFF_BUILT, ToolFault, check, rule_page, ruff_version

CLEAN = "CLEAN"
FINDINGS = "FINDINGS"
REJECTED = "REJECTED"

FUNCTION = (
    "reads each if, try, with, return, raise, assert, pass and del statement for a "
    "control path that fails, hides an error, opens a hole, wastes work, or reads "
    "harder than Python's own form"
)
DISCIPLINES = (
    "conventions",
    "maintainability",
    "performance-efficiency",
    "reliability",
    "security",
)
TAKEN = take("flow", DISCIPLINES)
RULES = TAKEN.rules
PREVIEW = TAKEN.preview
HOLDING = TAKEN.holding
CAN_RUN = tuple(f"{TOOL} {code}" for code in RULES)
FLOW_NODES = (
    ast.If,
    ast.Try,
    ast.TryStar,
    ast.With,
    ast.AsyncWith,
    ast.Return,
    ast.Raise,
    ast.Assert,
    ast.Pass,
    ast.Delete,
)
NO_FLOW = "no if, try, with, return, raise, assert, pass or del statement"

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "ruff_version": RUFF_BUILT,
    **TAKEN.settings(FUNCTION),
    "selection": SELECTION,
    "can_run": str(len(CAN_RUN)),
    "fault_file": "the file the input line names: FINDINGS reads HOLD when it sits "
    "in application_source and one of holding_rules fires",
    "ruff_config": "the one ruff finds from the folder of the file",
}


def _ruff_findings(
    source: bytes, folder: Path, rules: tuple[str, ...]
) -> list[tuple[str, int]]:
    """Return each code and line of `rules` for `source` on stdin, run from `folder`; none when `rules` is empty."""
    if not rules:
        return []
    rows = check(source, folder, rules, preview=bool(PREVIEW))
    return [(row.code, row.line) for row in rows]


def findings(
    text: str, root: Path, to_run: Collection[str]
) -> tuple[str, list[tuple[str, int]]]:
    """Return the ruff version and each code and line of the `to_run` rules inside the input `text` names."""
    located = locate(text, root)
    if isinstance(located, str):
        message = f"{text}: {located}, after tier 2 accepted it"
        raise ToolFault(message)
    file, source, (first, last) = located
    is_narrowed = bool(text.partition(SETTINGS["separator"])[1])
    rules = tuple(code for code in RULES if f"{TOOL} {code}" in to_run)
    found = [
        (code, line)
        for code, line in _ruff_findings(source, file.parent, rules)
        if not is_narrowed or first <= line <= last
    ]
    return f"ruff {ruff_version()}", found


def _content_fault(text: str, root: Path) -> str | None:
    """Return the tier 2 fault of `text`: `locate`'s, else `NO_FLOW`."""
    located = locate(text, root)
    if isinstance(located, str):
        return located
    _, source, (first, last) = located
    has_flow = any(
        isinstance(node, FLOW_NODES) and first <= node.lineno <= last
        for node in ast.walk(ast.parse(source))
    )
    return None if has_flow else NO_FLOW


def _functions_verdict(text: str, root: Path) -> Reading:
    """Return `CLEAN`, or `FINDINGS` holding when a `HOLDING` rule fires, from the `selection` rules."""
    version, found = findings(text, root, selection(text, root, CAN_RUN))
    if not found:
        return Reading(CLEAN, f"{version}: no rule on the list fires", holds=False)
    pages = {code: rule_page(code) for code, _ in found}
    rows = "; ".join(
        f"{code} {pages[code].name} line {line} fix {pages[code].fix}"
        for code, line in found
    )
    forms = "".join(
        f"\n{code} faulty:\n{page.faulty}{code} corrected:\n{page.corrected}"
        for code, page in pages.items()
    )
    holds = any(code in HOLDING for code in pages)
    return Reading(FINDINGS, f"{version}: {rows}{forms}", holds)


SIGIL = Sigil(
    name="CODE.FLOW",
    edition=1,
    owner=OWNER,
    disciplines=DISCIPLINES,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        {
            **CONTENT_TIER,
            "narrowed": "Python's ast module finds, in the input's lines, an if, try, "
            "try star, with, async with, return, raise, assert, pass or del statement",
            "narrowed_rejects": [NO_FLOW],
        },
        {
            "runs": [
                "the selection: the rules of the card that coding_partition.select "
                "gives for the input's facts; no rule selected, no ruff run",
                (
                    "python -m ruff check --preview --select with the selected rules, "
                    "the file on standard input, from the folder of the file"
                )
                if PREVIEW
                else (
                    "python -m ruff check --select with the selected rules, "
                    "the file on standard input, from the folder of the file"
                ),
                "for a symbol, only the findings inside its lines",
                "python -m ruff rule <code> --output-format json, for each rule "
                "that fires: its name, fix class, and the code under Example, "
                "before and after Use instead",
            ],
            "clean": "no rule on the list fires",
            "findings": [
                "rule id",
                "rule name",
                "line",
                "fix class",
                "faulty form",
                "corrected form",
            ],
            "fix_classes": list(FOLLOW_ON),
            "preview": (
                "the preview_rules fire only with --preview"
                if PREVIEW
                else "no rule on the list is a preview rule, so ruff runs without --preview"
            ),
            "left": TAKEN.left,
            "left_because": TAKEN.left_because,
            "not_read": "a ruff setting matched on the file name, such as "
            "per-file-ignores, because the file reaches ruff on standard input",
            "refuses": "ruff exits otherwise, or prints a finding or a rule page "
            "this module cannot read",
        },
    ),
    outputs={
        CLEAN: FlagRow(Flag.PASS),
        FINDINGS: FlagRow(Flag.FIX, holds_in_source=bool(HOLDING)),
    },
    refusal=REJECTED,
    follows={
        flag: FLAGS[flag]["follows"] + BY_FIX_CLASS for flag in (Flag.HOLD, Flag.FIX)
    },
    readers=READERS,
    data_type=data_type_fault,
    content=_content_fault,
    functions=_functions_verdict,
    fault_file=fault_file,
)


def flow_check(
    text: str, root: Path, source: Sequence[str] = APPLICATION_SOURCE
) -> Verdict:
    """Return the `judge` verdict of `SIGIL` for one input line under `root`."""
    named = fault_file(text, root)
    in_source = named is not None and in_application_source(named, root, source)
    return judge(SIGIL, text, root, in_source=in_source)


def run(argv: list[str] | None = None) -> int:
    """Return `main` for `SIGIL`, or 1 with the `ToolFault` on stderr."""
    try:
        return main(SIGIL, argv)
    except ToolFault as exc:
        print(f"ruff did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
