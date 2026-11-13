"""`SIGIL` is CODE.FLOW on the `core` card; `flow_check` judges an input."""

import ast
import sys
from collections.abc import Sequence
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

CANDIDATES = (
    "ASYNC100",
    "S101",
    "S110",
    "S112",
    "B012",
    "B029",
    "B901",
    "B904",
    "G201",
    "G202",
    "PIE790",
    "RET501",
    "RET502",
    "RET505",
    "RET506",
    "RET507",
    "RET508",
    "SIM102",
    "SIM103",
    "SIM105",
    "SIM107",
    "SIM108",
    "SIM114",
    "SIM116",
    "SIM117",
    "SIM401",
    "TC005",
    "PERF203",
    "PERF401",
    "E701",
    "E722",
    "F631",
    "F707",
    "PLE0101",
    "PLE0704",
    "PLE1205",
    "PLE1206",
    "PLR1708",
    "PLR1711",
    "PLR1712",
    "PLR1730",
    "PLR5501",
    "PLW0717",
    "FURB101",
    "FURB103",
    "FURB131",
    "FURB132",
    "RUF047",
    "RUF050",
    "RUF051",
    "RUF072",
    "TRY004",
    "TRY203",
    "TRY300",
    "TRY301",
    "TRY400",
)
LEFT_OFF: dict[str, str] = {
    "S101": "faulty: bandit B101 and ruff S101 use of assert",
    "S110": "faulty: ruff S110 try-except-pass",
    "S112": "faulty: ruff S112 try-except-continue",
    "B012": "faulty: pyright, a return cannot exit a finally block",
    "B904": "faulty: vulture unreachable else block",
    "PIE790": "corrected: reads PIE790",
    "SIM103": "corrected: reads SIM103",
    "SIM107": "faulty: pyright, a return cannot exit a finally block",
    "SIM108": "corrected: reads SIM108",
    "SIM401": "corrected: reads SIM401",
    "PERF203": "faulty: reads no PERF203, which ruff reads only below Python 3.11",
    "F631": "faulty: bandit B101 and ruff S101 use of assert",
    "F707": "faulty: pyright, a named except clause after a catch-all except clause",
    "PLE0704": "faulty: mypy return and pyright reportReturnType, missing return",
    "PLR1712": "faulty: bandit B101 and ruff S101 use of assert",
    "PLW0717": "faulty: ruff S311 pseudo-random generator",
    "RUF051": "faulty and corrected: mypy var-annotated, dictionary",
}
RULES = tuple(code for code in CANDIDATES if code not in LEFT_OFF)
PREVIEW_CANDIDATES = (
    "B901",
    "PLR1712",
    "PLW0717",
    "FURB101",
    "FURB103",
    "FURB131",
    "RUF047",
    "RUF050",
    "RUF072",
)
PREVIEW = tuple(code for code in RULES if code in PREVIEW_CANDIDATES)
PYLINT_ERRORS = ("PLE0101", "PLE0704", "PLE1205", "PLE1206")
HOLDING = tuple(code for code in RULES if code in PYLINT_ERRORS)
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
    "rules": " ".join(RULES),
    "preview_rules": " ".join(PREVIEW),
    "holding_rules": " ".join(HOLDING),
    "pylint_errors": " ".join(PYLINT_ERRORS),
    "fault_file": "the file the input line names: FINDINGS reads HOLD when it sits "
    "in application_source and one of holding_rules fires",
    "ruff_config": "the one ruff finds from the folder of the file",
}


def _ruff_findings(source: bytes, folder: Path) -> list[tuple[str, int]]:
    """Return each `RULES` code and line for `source` on stdin, run from `folder`."""
    rows = check(source, folder, RULES, preview=bool(PREVIEW))
    return [(row.code, row.line) for row in rows]


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
    """Return `CLEAN`, or `FINDINGS` holding when a `HOLDING` rule fires."""
    located = locate(text, root)
    if isinstance(located, str):
        message = f"{text}: {located}, after tier 2 accepted it"
        raise ToolFault(message)
    file, source, (first, last) = located
    is_narrowed = bool(text.partition(SETTINGS["separator"])[1])
    findings = [
        (code, line)
        for code, line in _ruff_findings(source, file.parent)
        if not is_narrowed or first <= line <= last
    ]
    version = f"ruff {ruff_version()}"
    if not findings:
        return Reading(CLEAN, f"{version}: no rule on the list fires", holds=False)
    pages = {code: rule_page(code) for code, _ in findings}
    rows = "; ".join(
        f"{code} {pages[code].name} line {line} fix {pages[code].fix}"
        for code, line in findings
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
                "python -m ruff check --preview --select with the rules, "
                "the file on standard input, from the folder of the file",
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
            "preview": "the preview_rules fire only with --preview",
            "left_off": LEFT_OFF,
            "left_off_because": "faulty or corrected names the sample; a tool and its "
            "finding mean the write gate refused that sample, because the coding "
            "archetype grades the finding high; reads names what ruff reads on that "
            "published form, run from the sample tree",
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
