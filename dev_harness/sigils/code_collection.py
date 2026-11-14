"""`SIGIL` is CODE.COLLECTION on the `core` card; `collection_check` judges an input."""

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
from .construct_rules import take
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
    "reads each tuple, list, set and dictionary, written out, built or called, for "
    "contents that are wrong, wasteful, unsafe, unclear, untyped or against convention"
)
DISCIPLINES = (
    "conventions",
    "maintainability",
    "performance-efficiency",
    "reliability",
    "security",
    "typing",
)
TAKEN = take("collection", DISCIPLINES)
RULES = TAKEN.rules
PREVIEW = TAKEN.preview
HOLDING = TAKEN.holding
DISPLAY_NODES = (ast.Tuple, ast.List)
COLLECTION_NODES = (ast.Set, ast.Dict, ast.ListComp, ast.SetComp, ast.DictComp)
BUILDERS = frozenset({"tuple", "list", "set", "dict"})
NO_COLLECTION = (
    "no tuple, list, set or dictionary, written out or built by a comprehension, "
    "and no call to tuple, list, set or dict"
)

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "ruff_version": RUFF_BUILT,
    **TAKEN.settings(FUNCTION),
    "fault_file": "the file the input line names: FINDINGS reads HOLD when it sits "
    "in application_source and one of holding_rules fires",
    "ruff_config": "the one ruff finds from the folder of the file",
}


def _ruff_findings(source: bytes, folder: Path) -> list[tuple[str, int]]:
    """Return each `RULES` code and line for `source` on stdin, run from `folder`."""
    rows = check(source, folder, RULES, preview=bool(PREVIEW))
    return [(row.code, row.line) for row in rows]


def _is_collection(node: ast.expr) -> bool:
    """Report whether `node` writes out, builds or calls a tuple, list, set or dict."""
    if isinstance(node, DISPLAY_NODES):
        return isinstance(node.ctx, ast.Load)
    if isinstance(node, ast.Call):
        return isinstance(node.func, ast.Name) and node.func.id in BUILDERS
    return isinstance(node, COLLECTION_NODES)


def _content_fault(text: str, root: Path) -> str | None:
    """Return the tier 2 fault of `text`: `locate`'s, else `NO_COLLECTION`."""
    located = locate(text, root)
    if isinstance(located, str):
        return located
    _, source, (first, last) = located
    has_collection = any(
        isinstance(node, ast.expr)
        and _is_collection(node)
        and first <= node.lineno <= last
        for node in ast.walk(ast.parse(source))
    )
    return None if has_collection else NO_COLLECTION


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
    name="CODE.COLLECTION",
    edition=1,
    owner=OWNER,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        {
            **CONTENT_TIER,
            "narrowed": "Python's ast module finds, in the input's lines, a tuple or "
            "list written out and read as a value, a set or dictionary written out, "
            "a list, set or dictionary comprehension, or a call to tuple, list, set "
            "or dict by that name",
            "narrowed_rejects": [NO_COLLECTION],
        },
        {
            "runs": [
                (
                    "python -m ruff check --preview --select with the rules, "
                    "the file on standard input, from the folder of the file"
                )
                if PREVIEW
                else (
                    "python -m ruff check --select with the rules, "
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


def collection_check(
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
