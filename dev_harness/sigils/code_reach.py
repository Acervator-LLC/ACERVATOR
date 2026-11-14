"""`SIGIL` is CODE.REACH on the `core` card; `reach_check` judges one input line."""

import json
import subprocess
import sys
from collections.abc import Sequence
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

FUNCTION = (
    "reads each def, class, name and import for code that nothing in the tree "
    "reaches, which a maintainer must still read and keep"
)
DISCIPLINES = ("maintainability",)
VULTURE = hold("vulture", house_rules("vulture"), DISCIPLINES)

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "vulture_version": VULTURE_BUILT,
    "function": FUNCTION,
    "disciplines": " ".join(DISCIPLINES),
    "scope": "each vulture rule a discipline houses or unplaced.json lists: "
    "dead-code, the one rule id every vulture item carries",
    "vulture_rules": " ".join(VULTURE.rules),
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


def _vulture_scan(root: Path) -> tuple[str, list[tuple[Path, Finding]]]:
    """Return the vulture version and each item's file and `Finding` under `root`."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-P",
                "-c",
                (
                    "import json, vulture; "
                    "scan = vulture.Vulture(); "
                    "scan.scavenge(['.']); "
                    "print(json.dumps({'version': vulture.__version__, "
                    "'exit_code': int(scan.exit_code), "
                    "'items': [[str(item.filename), item.typ, item.name, "
                    "item.confidence, item.first_lineno] "
                    "for item in scan.get_unused_code()]}))"
                ),
            ],
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


def _functions_verdict(text: str, root: Path) -> Reading:
    """Return `REACHED`, or `UNREACHED` holding if an item hits `confidence_floor`."""
    located = locate(text, root)
    if isinstance(located, str):
        message = f"{text}: {located}, after tier 2 accepted it"
        raise ToolFault(message)
    file, _, (first, last) = located
    is_narrowed = bool(text.partition(SETTINGS["separator"])[1])
    version, items = _vulture_scan(root)
    target = file.resolve()
    findings = [
        finding
        for path, finding in items
        if VULTURE.rules
        and path == target
        and (not is_narrowed or first <= finding.line <= last)
    ]
    if not findings:
        return Reading(REACHED, f"vulture {version}: no item in the file", holds=False)
    floor = int(SETTINGS["confidence_floor"])
    holds = any(finding.confidence >= floor for finding in findings)
    rows = "; ".join(
        f"{item.kind} {item.name} confidence {item.confidence} line {item.line}"
        for item in findings
    )
    return Reading(UNREACHED, f"vulture {version}: {rows}", holds)


SIGIL = Sigil(
    name="CODE.REACH",
    edition=1,
    owner=OWNER,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        CONTENT_TIER,
        {
            "runs": [
                (
                    "vulture's programmatic use as its README shows it, "
                    "Vulture().scavenge(['.']) then get_unused_code(), "
                    "in python -P -c from the root of the target tree"
                ),
                (
                    "only the items in the input file, so a name used in another "
                    "file of the tree is not called unused"
                ),
                "only while vulture_rules holds dead-code",
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
