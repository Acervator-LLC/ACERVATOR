"""`SIGIL` is CODE.OPTIMIZE on the `core` card; `optimize` judges one input line."""

import sys
from dataclasses import dataclass
from pathlib import Path

from .coding_input import (
    CONTENT_TIER,
    DATA_TYPE_TIER,
    INPUT_FORM,
    OWNER,
    READERS,
    SEPARATOR,
    content_fault,
    data_type_fault,
    locate,
)
from .core import FLAGS, Flag, FlagRow, Sigil, Verdict, judge, main
from .fix_class import BY_FIX_CLASS, FOLLOW_ON
from .ruff_rules import RUFF_BUILT, ToolFault, check, fix_class, ruff_version

CLEAN = "CLEAN"
OPTIMIZABLE = "OPTIMIZABLE"
REJECTED = "REJECTED"

FAMILIES = ("PERF", "SIM", "C4", "UP", "FURB", "PLR17", "C901")

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "ruff_version": RUFF_BUILT,
    "rule_families": ", ".join(FAMILIES),
    "ruff_config": "the one ruff finds from the folder of the file: "
    "its target version, preview and complexity limit",
}


@dataclass(frozen=True)
class Finding:
    """One ruff finding: rule `code`, rule `name`, `line` and `fix` class."""

    code: str
    name: str
    line: int
    fix: str


def _ruff_findings(source: bytes, folder: Path) -> list[Finding]:
    """Return each `FAMILIES` `Finding` for `source` on stdin, run from `folder`."""
    return [
        Finding(row.code, row.name, row.line, fix_class(row.code))
        for row in check(source, folder, FAMILIES, preview=False)
    ]


def _functions_verdict(text: str, root: Path) -> tuple[str, str]:
    """Return `CLEAN`, or `OPTIMIZABLE` with each `Finding` in the `locate` span."""
    located = locate(text, root)
    if isinstance(located, str):
        raise ToolFault(f"{text}: {located}, after tier 2 accepted it")
    file, source, (first, last) = located
    findings = [
        finding
        for finding in _ruff_findings(source, file.parent)
        if first <= finding.line <= last
    ]
    version = f"ruff {ruff_version()}"
    if not findings:
        return CLEAN, f"{version}: no rule in {SETTINGS['rule_families']} fires"
    rows = "; ".join(
        f"{item.code} {item.name} line {item.line} fix {item.fix}" for item in findings
    )
    return OPTIMIZABLE, f"{version}: {rows}"


SIGIL = Sigil(
    name="CODE.OPTIMIZE",
    edition=1,
    owner=OWNER,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        CONTENT_TIER,
        {
            "runs": [
                "python -m ruff check --select with the rule families, "
                "the file on standard input, from the folder of the file",
                "for a symbol, only the findings inside its lines",
                "python -m ruff rule --all, for the fix class of each rule",
            ],
            "clean": "no rule in the rule families fires",
            "optimizable": ["rule id", "rule name", "line", "fix class"],
            "fix_classes": list(FOLLOW_ON),
            "not_read": "a ruff setting matched on the file name, such as "
            "per-file-ignores, because the file reaches ruff on standard input",
        },
    ),
    outputs={
        CLEAN: FlagRow(Flag.PASS),
        OPTIMIZABLE: FlagRow(Flag.OPTIMIZE),
    },
    refusal=REJECTED,
    follows={Flag.OPTIMIZE: FLAGS[Flag.OPTIMIZE]["follows"] + BY_FIX_CLASS},
    readers=READERS,
    data_type=data_type_fault,
    content=content_fault,
    functions=_functions_verdict,
)


def optimize(text: str, root: Path) -> Verdict:
    """Return the `judge` verdict of `SIGIL` for one input line under `root`."""
    return judge(SIGIL, text, root, in_source=False)


def run(argv: list[str] | None = None) -> int:
    """Return `main` for `SIGIL`, or 1 with the `ToolFault` on stderr."""
    try:
        return main(SIGIL, argv)
    except ToolFault as exc:
        print(f"ruff did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
