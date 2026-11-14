"""`SIGIL` is CODE.OPTIMIZE on the `core` card; `optimize` judges one input line."""

import sys
from collections.abc import Collection
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
from .coding_partition import SELECTION, selection
from .construct_rules import LEFT_BECAUSE, TOOL, hold
from .core import FLAGS, Flag, FlagRow, Sigil, Verdict, judge, main
from .fix_class import BY_FIX_CLASS, FOLLOW_ON
from .ruff_rules import RUFF_BUILT, ToolFault, check, fix_class, listing, ruff_version

CLEAN = "CLEAN"
OPTIMIZABLE = "OPTIMIZABLE"
REJECTED = "REJECTED"

FAMILIES = ("PERF", "SIM", "C4", "UP", "FURB", "PLR17", "C901")
FUNCTION = (
    "reads each statement for a published rewrite that makes the code faster, "
    "simpler, or current with Python's own forms and annotations"
)
DISCIPLINES = ("conventions", "maintainability", "performance-efficiency", "typing")
SCOPE = tuple(
    sorted(
        code
        for code, listed in listing().items()
        if code.startswith(FAMILIES) and not listed.removed
    )
)
HELD = hold(TOOL, SCOPE, DISCIPLINES)
RULES = HELD.rules
PREVIEW = tuple(code for code in RULES if listing()[code].preview)
STABLE = tuple(code for code in RULES if code not in PREVIEW)
CAN_RUN = tuple(f"{TOOL} {code}" for code in RULES)

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "ruff_version": RUFF_BUILT,
    "function": FUNCTION,
    "disciplines": " ".join(DISCIPLINES),
    "rule_families": ", ".join(FAMILIES),
    "scope": "each ruff rule in rule_families that python -m ruff rule --all lists "
    "and ruff has not removed",
    "rules": " ".join(RULES),
    "preview_rules": " ".join(PREVIEW),
    "selection": SELECTION,
    "can_run": str(len(CAN_RUN)),
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


def _ruff_findings(source: bytes, folder: Path, rules: tuple[str, ...]) -> list[Finding]:
    """Return each `Finding` of `rules` for `source` on stdin, run from `folder`, by line; none when `rules` is empty."""
    stable = tuple(code for code in rules if code in STABLE)
    preview = tuple(code for code in rules if code in PREVIEW)
    rows = check(source, folder, stable, preview=False) if stable else []
    if preview:
        rows += check(source, folder, preview, preview=True)
    return [
        Finding(row.code, row.name, row.line, fix_class(row.code))
        for row in sorted(rows, key=lambda row: row.line)
    ]


def findings(text: str, root: Path, to_run: Collection[str]) -> tuple[str, list[Finding]]:
    """Return the ruff version and each `Finding` of the `to_run` rules inside the input `text` names."""
    located = locate(text, root)
    if isinstance(located, str):
        raise ToolFault(f"{text}: {located}, after tier 2 accepted it")
    file, source, (first, last) = located
    rules = tuple(code for code in RULES if f"{TOOL} {code}" in to_run)
    found = [
        finding
        for finding in _ruff_findings(source, file.parent, rules)
        if first <= finding.line <= last
    ]
    return f"ruff {ruff_version()}", found


def _functions_verdict(text: str, root: Path) -> tuple[str, str]:
    """Return `CLEAN`, or `OPTIMIZABLE` with each `Finding` of the `selection` rules in the `locate` span."""
    version, found = findings(text, root, selection(text, root, CAN_RUN))
    if not found:
        return CLEAN, f"{version}: no rule on the list fires"
    rows = "; ".join(
        f"{item.code} {item.name} line {item.line} fix {item.fix}" for item in found
    )
    return OPTIMIZABLE, f"{version}: {rows}"


SIGIL = Sigil(
    name="CODE.OPTIMIZE",
    edition=1,
    owner=OWNER,
    disciplines=DISCIPLINES,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        CONTENT_TIER,
        {
            "runs": [
                "the selection: the rules of the card that coding_partition.select "
                "gives for the input's facts; no rule selected, no ruff run",
                "python -m ruff check --select with the selected rules that are not "
                "preview_rules, the file on standard input, from the folder of the file",
                "python -m ruff check --preview --select with the selected preview_rules, "
                "the same way, when the selection holds any",
                "for a symbol, only the findings inside its lines",
                "python -m ruff rule --all, for the fix class of each rule",
            ],
            "clean": "no rule on the list fires",
            "optimizable": ["rule id", "rule name", "line", "fix class"],
            "fix_classes": list(FOLLOW_ON),
            "preview": "the preview_rules run with --preview; every other rule runs "
            "with the preview setting the ruff settings beside the file give",
            "left": HELD.left,
            "left_because": LEFT_BECAUSE,
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
