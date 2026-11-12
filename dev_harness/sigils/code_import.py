"""`SIGIL` is CODE.IMPORT on the `core` card; `import_check` judges one input line."""

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
    "A004",
    "ICN001",
    "TID252",
    "TC001",
    "TC002",
    "TC003",
    "TC004",
    "N811",
    "N812",
    "N813",
    "N814",
    "N817",
    "E401",
    "E402",
    "F401",
    "F403",
    "F404",
    "F406",
    "F811",
    "PLC0414",
    "PLC0415",
    "PLC2403",
    "PLR0402",
    "UP010",
    "UP023",
    "UP026",
    "UP029",
    "UP035",
)
LEFT_OFF: dict[str, str] = {
    "ICN001": "faulty: vulture unused import 'pandas'; mypy import-untyped pandas",
    "TID252": "faulty: vulture unused import 'foo'",
    "TC002": "faulty: mypy import-untyped pandas",
    "N811": "faulty: vulture unused import 'ConstantValue'",
    "N812": "faulty: vulture unused import 'MyClassName'",
    "N813": "faulty: vulture unused import 'myclassname'",
    "N814": "faulty: vulture unused import 'MY_CLASS_NAME'",
    "N817": "faulty: vulture unused import 'MCN'",
    "E401": "faulty: vulture unused import 'os'",
    "E402": "faulty: vulture unused import 'os' and 'x'",
    "F401": "faulty: vulture unused import 'np'",
    "F404": "faulty: vulture unused import 'Path'",
    "F406": "faulty: pyright, wildcard import not allowed within a class or function",
    "F811": "faulty: vulture unused import 'foo' and 'bar'",
    "PLC0414": "corrected: vulture unused import 'np'",
    "PLC2403": "faulty: vulture unused import 'bár'",
    "PLR0402": "faulty: vulture unused import 'futures'",
    "UP023": "faulty: vulture unused import 'ET'; semgrep use-defused-xml",
    "UP026": "faulty: vulture unused import 'mock'",
    "UP035": "faulty: vulture unused import 'Sequence'",
}
RULES = tuple(code for code in CANDIDATES if code not in LEFT_OFF)
ERROR_CLASS = "PLE"
UNDEFINED_NAME = "F821"
HOLDING = tuple(
    code for code in RULES if code.startswith(ERROR_CLASS) or code == UNDEFINED_NAME
)
IMPORT_NODES = (ast.Import, ast.ImportFrom)
NO_IMPORT = "no import or from-import statement"

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "ruff_version": RUFF_BUILT,
    "rules": " ".join(RULES),
    "holding_rules": " ".join(HOLDING),
    "error_class": ERROR_CLASS,
    "undefined_name": UNDEFINED_NAME,
    "fault_file": "the file the input line names: FINDINGS reads HOLD when it sits "
    "in application_source and one of holding_rules fires",
    "ruff_config": "the one ruff finds from the folder of the file",
}


def _ruff_findings(source: bytes, folder: Path) -> list[tuple[str, int]]:
    """Return each `RULES` code and line for `source` on stdin, run from `folder`."""
    return [(row.code, row.line) for row in check(source, folder, RULES, preview=False)]


def _content_fault(text: str, root: Path) -> str | None:
    """Return the tier 2 fault of `text`: `locate`'s, else `NO_IMPORT`."""
    located = locate(text, root)
    if isinstance(located, str):
        return located
    _, source, (first, last) = located
    has_import = any(
        isinstance(node, IMPORT_NODES) and first <= node.lineno <= last
        for node in ast.walk(ast.parse(source))
    )
    return None if has_import else NO_IMPORT


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
    name="CODE.IMPORT",
    edition=1,
    owner=OWNER,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        {
            **CONTENT_TIER,
            "narrowed": "Python's ast module finds an import or from-import "
            "statement in the input's lines",
            "narrowed_rejects": [NO_IMPORT],
        },
        {
            "runs": [
                "python -m ruff check --select with the rules, "
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
            "preview": "no rule on the list is a preview rule, so ruff runs "
            "without --preview",
            "left_off": LEFT_OFF,
            "left_off_because": "the write gate refused that rule's faulty or "
            "corrected sample, because the coding archetype grades the named "
            "finding high",
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


def import_check(
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
