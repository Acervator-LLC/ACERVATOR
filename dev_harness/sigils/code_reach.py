"""`SIGIL` is CODE.REACH on the `core` card; `reach_check` judges one input line."""

import json
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .code_optimize import SETTINGS as OPTIMIZE_SETTINGS
from .code_optimize import SIGIL as OPTIMIZE
from .code_optimize import _locate
from .code_secure import _fault_file, _said
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

REACHED = "REACHED"
UNREACHED = "UNREACHED"
REJECTED = "REJECTED"

VULTURE_BUILT = "2.16"
VULTURE_TIMEOUT_S = 120

SETTINGS: dict[str, str] = {
    "separator": OPTIMIZE_SETTINGS["separator"],
    "vulture_version": VULTURE_BUILT,
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
        said = _said(proc.stderr or proc.stdout)
        message = f"vulture exited {proc.returncode}: {said}"
        raise ToolFault(message)
    try:
        report = json.loads(proc.stdout)
        if report["exit_code"]:
            message = f"vulture could not read a file in the tree: {_said(proc.stderr)}"
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
    located = _locate(text, root)
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
        if path == target and (not is_narrowed or first <= finding.line <= last)
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
    owner="coding",
    input_form=OPTIMIZE.input_form,
    settings=SETTINGS,
    tiers=(
        OPTIMIZE.tiers[0],
        OPTIMIZE.tiers[1],
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
                "for a symbol, only the items inside its lines",
            ],
            "reached": "vulture reports no item in the file",
            "unreached": ["kind", "name", "confidence", "line"],
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
    readers=OPTIMIZE.readers,
    data_type=OPTIMIZE.data_type,
    content=OPTIMIZE.content,
    functions=_functions_verdict,
    fault_file=_fault_file,
)


def reach_check(
    text: str, root: Path, source: Sequence[str] = APPLICATION_SOURCE
) -> Verdict:
    """Return the `judge` verdict of `SIGIL` for one input line under `root`."""
    named = _fault_file(text, root)
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
