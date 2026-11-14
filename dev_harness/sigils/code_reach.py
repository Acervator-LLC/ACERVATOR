"""`SIGIL` is CODE.REACH on the `core` card; `reach_check` judges one input line."""

import json
import subprocess
import sys
from collections.abc import Collection, Sequence
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
    fault_file,
    locate,
)
from .coding_partition import SELECTION, selection
from .construct_rules import LEFT_BECAUSE, hold, house_rules
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
    tool_text,
)

REACHED = "REACHED"
UNREACHED = "UNREACHED"
REJECTED = "REJECTED"

VULTURE_BUILT = "2.16"
VULTURE_TIMEOUT_S = 120
WHOLE_TREE = "."
TREE_FILES = ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.py"]
NO_RULE = "vulture did not run: the selection holds no rule"

FUNCTION = (
    "reads each def, class, name and import for code that nothing in the tree "
    "reaches, which a maintainer must still read and keep"
)
DISCIPLINES = ("maintainability",)
VULTURE = hold("vulture", house_rules("vulture"), DISCIPLINES)
CAN_RUN = tuple(f"{VULTURE.tool} {rule}" for rule in VULTURE.rules)

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "vulture_version": VULTURE_BUILT,
    "function": FUNCTION,
    "disciplines": " ".join(DISCIPLINES),
    "scope": "each vulture rule a discipline houses or unplaced.json lists: "
    "dead-code, the one rule id every vulture item carries",
    "vulture_rules": " ".join(VULTURE.rules),
    "selection": SELECTION,
    "can_run": str(len(CAN_RUN)),
    "tree_files": "the .py files "
    + " ".join(TREE_FILES[1:])
    + " lists from the root of the target tree, else the whole tree outside git",
    "confidence_floor": "100",
    "fault_file": "the file the input line names: UNREACHED reads HOLD when it sits "
    "in application_source and an item reaches confidence_floor",
}


class ToolFault(Exception):
    """vulture failed, could not read a tree file, or printed an unreadable report."""


@dataclass(frozen=True)
class Finding:
    """One vulture item: its `kind`, `name`, `confidence` and first `line`."""

    kind: str
    name: str
    confidence: int
    line: int


def _tree_files(root: Path) -> list[str]:
    """Return the `TREE_FILES` paths under `root` that exist, or `WHOLE_TREE` when git lists none."""
    try:
        proc = subprocess.run(
            TREE_FILES,
            cwd=root,
            capture_output=True,
            timeout=VULTURE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [WHOLE_TREE]
    listed = tool_text(proc.stdout).split("\0") if proc.returncode == 0 else []
    files = [name for name in listed if name and (root / name).is_file()]
    return files or [WHOLE_TREE]


def _vulture_scan(root: Path) -> tuple[str, list[tuple[Path, Finding]]]:
    """Return the vulture version and each item's file and `Finding` over the `_tree_files` of `root`."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-P",
                "-c",
                (
                    "import json, sys, vulture; "
                    "scan = vulture.Vulture(); "
                    "scan.scavenge(json.load(sys.stdin)); "
                    "print(json.dumps({'version': vulture.__version__, "
                    "'exit_code': int(scan.exit_code), "
                    "'items': [[str(item.filename), item.typ, item.name, "
                    "item.confidence, item.first_lineno] "
                    "for item in scan.get_unused_code()]}))"
                ),
            ],
            input=json.dumps(_tree_files(root)).encode("utf-8"),
            cwd=root,
            capture_output=True,
            timeout=VULTURE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = f"vulture: {exc}"
        raise ToolFault(message) from exc
    if proc.returncode != 0:
        said = tool_text(proc.stderr or proc.stdout)
        message = f"vulture exited {proc.returncode}: {said}"
        raise ToolFault(message)
    try:
        report = json.loads(proc.stdout)
        if report["exit_code"]:
            said = tool_text(proc.stderr)
            message = f"vulture could not read a file in the tree: {said}"
            raise ToolFault(message)
        return report["version"], [
            (Path(path), Finding(kind, name, confidence, line))
            for path, kind, name, confidence, line in report["items"]
        ]
    except (ValueError, KeyError, TypeError) as exc:
        message = f"vulture printed an unreadable report: {exc!r}"
        raise ToolFault(message) from exc


def findings(text: str, root: Path, to_run: Collection[str]) -> tuple[str, list[Finding]]:
    """Return the vulture version and each item of the `to_run` rules inside the input `text` names."""
    located = locate(text, root)
    if isinstance(located, str):
        message = f"{text}: {located}, after tier 2 accepted it"
        raise ToolFault(message)
    file, _, (first, last) = located
    is_narrowed = bool(text.partition(SETTINGS["separator"])[1])
    if not any(name in to_run for name in CAN_RUN):
        return NO_RULE, []
    version, items = _vulture_scan(root)
    target = file.resolve()
    found = [
        finding
        for path, finding in items
        if path == target and (not is_narrowed or first <= finding.line <= last)
    ]
    return f"vulture {version}", found


def _functions_verdict(text: str, root: Path) -> Reading:
    """Return `REACHED`, or `UNREACHED` holding if an item of the `selection` rules hits `confidence_floor`."""
    version, found = findings(text, root, selection(text, root, CAN_RUN))
    if not found:
        return Reading(REACHED, f"{version}: no item in the file", holds=False)
    floor = int(SETTINGS["confidence_floor"])
    holds = any(finding.confidence >= floor for finding in found)
    rows = "; ".join(
        f"{item.kind} {item.name} confidence {item.confidence} line {item.line}"
        for item in found
    )
    return Reading(UNREACHED, f"{version}: {rows}", holds)


SIGIL = Sigil(
    name="CODE.REACH",
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
                "gives for the input's facts; no rule selected, no vulture run",
                (
                    "vulture's programmatic use as its README shows it, "
                    "Vulture().scavenge(<the tree_files>) then get_unused_code(), "
                    "in python -P -c from the root of the target tree"
                ),
                (
                    "only the items in the input file, so a name used in another "
                    "file of the tree is not called unused"
                ),
                "for a symbol, only the items inside its lines",
            ],
            "reached": "vulture reports no item in the file",
            "unreached": ["kind", "name", "confidence", "line"],
            "left": {VULTURE.tool: VULTURE.left},
            "left_because": LEFT_BECAUSE,
            "not_read": "a tool.vulture table in the tree's pyproject.toml, "
            "so no name, decorator or path it lists is ignored",
            "refuses": "vulture exits otherwise, cannot read a Python file "
            "in the tree, or prints a report this module cannot read",
        },
    ),
    outputs={
        REACHED: FlagRow(Flag.PASS),
        UNREACHED: FlagRow(Flag.FIX, holds_in_source=True),
    },
    refusal=REJECTED,
    follows={
        Flag.FIX: FLAGS[Flag.FIX]["follows"]
        + ", by quarantine first: the unreached code moves aside in one commit "
        "and is never deleted",
    },
    readers=READERS,
    data_type=data_type_fault,
    content=content_fault,
    functions=_functions_verdict,
    fault_file=fault_file,
)


def reach_check(
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
        print(f"vulture did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
