"""`SIGIL` is CODE.VARIABLE on the `core` card; `variable_check` judges an input."""

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
    "ANN001",
    "ANN401",
    "ASYNC230",
    "ASYNC250",
    "S509",
    "BLE001",
    "B003",
    "B007",
    "B020",
    "B023",
    "B025",
    "B031",
    "B032",
    "A001",
    "A002",
    "LOG002",
    "PIE794",
    "PIE796",
    "RET504",
    "SIM113",
    "SIM115",
    "ARG001",
    "ARG002",
    "ARG003",
    "ARG004",
    "ARG005",
    "PTH123",
    "N803",
    "N804",
    "N805",
    "N806",
    "N815",
    "N816",
    "PERF403",
    "E731",
    "E741",
    "F402",
    "F405",
    "F602",
    "F633",
    "F821",
    "F823",
    "F841",
    "F901",
    "PLC0105",
    "PLC0131",
    "PLC0205",
    "PLC2401",
    "PLE0115",
    "PLE0117",
    "PLE0118",
    "PLE0237",
    "PLE0241",
    "PLE0604",
    "PLE0605",
    "PLE1141",
    "PLR1704",
    "PLR1722",
    "PLR6104",
    "PLW0127",
    "PLW0128",
    "PLW0131",
    "PLW0211",
    "PLW0245",
    "PLW0602",
    "PLW0603",
    "PLW0642",
    "PLW1514",
    "UP001",
    "UP004",
    "UP006",
    "UP013",
    "UP014",
    "UP019",
    "UP024",
    "UP037",
    "FURB148",
    "FURB187",
    "FURB189",
    "RUF007",
    "RUF013",
    "RUF018",
    "RUF020",
    "RUF036",
    "RUF052",
    "RUF059",
    "RUF070",
    "TRY201",
    "TRY401",
)
NO_BINDING_FORM = "faulty: refused at tier 2, the published form holds no binding"
LEFT_OFF: dict[str, str] = {
    "ANN001": "faulty: vulture unused variable 'x'",
    "ANN401": "faulty: vulture unused variable 'x'",
    "S509": NO_BINDING_FORM,
    "B025": NO_BINDING_FORM,
    "B032": "faulty: mypy valid-type and pyright reportInvalidTypeForm",
    "ARG001": "faulty: vulture unused variable 'baz'",
    "ARG002": "faulty: vulture unused variable 'arg2'",
    "ARG003": "faulty: vulture unused variable 'cls' and 'arg2'",
    "ARG004": "faulty: vulture unused variable 'arg2'",
    "ARG005": "faulty: vulture unused variable 'y'",
    "PTH123": NO_BINDING_FORM,
    "N803": "faulty: vulture unused variable 'A' and 'myArg'",
    "N804": "faulty: vulture unused variable 'data'",
    "N805": "faulty: vulture unused variable 'cls' and 'data'",
    "F402": "corrected: vulture unused import 'path'",
    "F633": NO_BINDING_FORM,
    "F821": NO_BINDING_FORM,
    "F823": "faulty: pyright reportUnboundVariable, 'x' is unbound",
    "PLE0115": "faulty: pyright, 'counter' declared global and nonlocal",
    "PLE0117": "faulty: pyright reportUndefinedVariable and no binding for "
    "nonlocal 'bar'",
    "PLE0241": NO_BINDING_FORM,
    "PLE0604": "faulty: mypy list-item, list items 1 and 2",
    "PLE1141": "faulty: mypy str-unpack, unpacking a string",
    "PLR1722": NO_BINDING_FORM,
    "PLW0211": "corrected: vulture unused variable 'sheep'",
    "PLW0245": "faulty: pyright reportIncompatibleMethodOverride, method 'speak'",
    "PLW1514": NO_BINDING_FORM,
    "UP004": NO_BINDING_FORM,
    "UP024": NO_BINDING_FORM,
    "UP037": "corrected: reads UP037",
    "RUF013": "faulty: vulture unused variable 'arg'",
    "RUF018": "corrected: reads RUF018",
    "RUF020": NO_BINDING_FORM,
    "RUF036": "faulty: vulture unused variable 'arg'",
    "TRY201": NO_BINDING_FORM,
}
RULES = tuple(code for code in CANDIDATES if code not in LEFT_OFF)
PREVIEW_CANDIDATES = (
    "PLE1141",
    "PLR6104",
    "PLW1514",
    "FURB148",
    "FURB189",
    "RUF052",
    "RUF070",
)
PREVIEW = tuple(code for code in RULES if code in PREVIEW_CANDIDATES)
PYLINT_ERRORS = (
    "PLE0115",
    "PLE0117",
    "PLE0118",
    "PLE0237",
    "PLE0241",
    "PLE0604",
    "PLE0605",
    "PLE1141",
)
UNDEFINED_NAMES = ("F821", "F823")
HOLDING = tuple(code for code in RULES if code in PYLINT_ERRORS + UNDEFINED_NAMES)
BINDING_NODES = (
    ast.Assign,
    ast.AnnAssign,
    ast.AugAssign,
    ast.NamedExpr,
    ast.arg,
    ast.Global,
    ast.Nonlocal,
)
NO_BINDING = (
    "no assignment, annotated or augmented assignment, named expression, "
    "function argument, or global or nonlocal statement"
)

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "ruff_version": RUFF_BUILT,
    "rules": " ".join(RULES),
    "preview_rules": " ".join(PREVIEW),
    "holding_rules": " ".join(HOLDING),
    "pylint_errors": " ".join(PYLINT_ERRORS),
    "undefined_names": " ".join(UNDEFINED_NAMES),
    "fault_file": "the file the input line names: FINDINGS reads HOLD when it sits "
    "in application_source and one of holding_rules fires",
    "ruff_config": "the one ruff finds from the folder of the file",
}


def _ruff_findings(source: bytes, folder: Path) -> list[tuple[str, int]]:
    """Return each `RULES` code and line for `source` on stdin, run from `folder`."""
    rows = check(source, folder, RULES, preview=bool(PREVIEW))
    return [(row.code, row.line) for row in rows]


def _content_fault(text: str, root: Path) -> str | None:
    """Return the tier 2 fault of `text`: `locate`'s, else `NO_BINDING`."""
    located = locate(text, root)
    if isinstance(located, str):
        return located
    _, source, (first, last) = located
    has_binding = any(
        isinstance(node, BINDING_NODES) and first <= node.lineno <= last
        for node in ast.walk(ast.parse(source))
    )
    return None if has_binding else NO_BINDING


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
    name="CODE.VARIABLE",
    edition=1,
    owner=OWNER,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        {
            **CONTENT_TIER,
            "narrowed": "Python's ast module finds, in the input's lines, an "
            "assignment, annotated or augmented assignment, named expression, "
            "function argument, or global or nonlocal statement",
            "narrowed_rejects": [NO_BINDING],
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
            "published form, run from the sample tree; refused at tier 2 means "
            "the published form holds none of the bindings tier 2 names",
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


def variable_check(
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
