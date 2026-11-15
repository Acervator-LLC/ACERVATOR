"""`SIGIL` is CODE.DEBUG.PYTHON on the `core` card; `run` prints one row per input line."""

import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dev_harness.harness.report import BLOCKING_SEVERITIES

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
from .construct_rules import RULES_FILE, UNPLACED_FILE, places, unplaced
from .core import Flag, FlagRow, Reading, Sigil, main, tool_text

NAME = "CODE.DEBUG.PYTHON"
EDITION = 1
SOUND = "SOUND"
UNSOUND = "UNSOUND"
REJECTED = "REJECTED"

DISCIPLINE = "python"
UNPLACED = "unplaced"
UNHOUSED = "unhoused"
UNHOUSED_REASON = f"neither {DISCIPLINE}/{RULES_FILE} nor {UNPLACED_FILE} lists it"
DISCIPLINES = (DISCIPLINE,)

HARNESS_ROOT = Path(__file__).resolve().parents[2]
ARCHETYPE = "dev_harness.harness.coding_archetype"
ARCHETYPE_TIMEOUT_S = 300
ARCHETYPE_FINISHED = (0, 1)

FINDING_FIELDS = (
    "sigil",
    "discipline",
    "characteristics",
    "reason",
    "tool",
    "rule",
    "severity",
    "path",
    "line",
    "message",
)
CANON: dict[str, str] = {
    "ruff": "https://docs.astral.sh/ruff/rules/",
    "mypy": "https://github.com/python/mypy/blob/v2.1.0/docs/source/"
    "error_code_list.rst and error_code_list2.rst",
    "pyright": "https://github.com/microsoft/pyright/blob/1.1.411/"
    "docs/configuration.md",
    "bandit": "https://bandit.readthedocs.io/en/latest/plugins/index.html",
    "vulture": "https://github.com/jendrikseipp/vulture/blob/v2.16/README.md",
    "semgrep": "https://semgrep.dev/r",
    "pylint": "https://pylint.readthedocs.io/en/stable/user_guide/messages/"
    "messages_overview.html",
    "rule modules": "dev_harness/harness/rules/<module>.py for scaffolding, "
    "hallucination, slop, numeric_guard, delegated_canon and restore_set",
}
FUNCTION = (
    "runs the canonized testing the Coding Archetype runs on one Python file, "
    "and binds each finding to the Python discipline"
)
SOUND_MEANS = (
    "every analyzer of the run reports ok, and no finding inside the input's lines "
    f"has the severity {' or '.join(BLOCKING_SEVERITIES)}"
)

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "function": FUNCTION,
    "disciplines": " ".join(DISCIPLINES),
    "language": "Python",
    "canon": "; ".join(f"{tool}: {page}" for tool, page in CANON.items()),
    "decision": "none: the archetype's report gives every output",
    "test_vectors": "harness_fixtures/sigil_code_debug_python/known_good.txt and "
    "harness_fixtures/sigil_code_debug_python/known_bad.txt",
    "function_set": f"python -m {ARCHETYPE} <file>, run from the repository that "
    "holds this module: every analyzer it runs, none added and none dropped",
    "blocking_severities": " ".join(BLOCKING_SEVERITIES),
    "finding_fields": " ".join(FINDING_FIELDS),
    "bindings": f"{DISCIPLINE}: the characteristics {DISCIPLINE}/{RULES_FILE} gives "
    f"the tool and rule; {UNPLACED}: the reason {UNPLACED_FILE} gives; "
    f"{UNHOUSED}: {UNHOUSED_REASON}",
    "fault_file": "the file the input line names: HOLD when it sits in "
    "application_source",
}


class ToolFault(Exception):
    """`ARCHETYPE` did not finish, or printed a report `run_fault` refuses."""


def run_fault(report: object, file: Path, code: int) -> str | None:
    """Return why `report` from exit `code` is no complete run on `file`, or None."""
    if not isinstance(report, dict):
        return "the report is no JSON object"
    if Path(str(report.get("target", ""))) != file.resolve():
        return f"the report's target {report.get('target')} is not the input's file"
    if not report.get("scanned") or report.get("unhandled"):
        return "the archetype scanned nothing"
    if not report.get("tool_availability"):
        return "the report names no analyzer"
    if report.get("unavailable_required"):
        return f"analyzers did not report ok: {report['unavailable_required']}"
    if report.get("errors"):
        return f"the run recorded errors: {report['errors']}"
    if (code == 0) != bool(report.get("passed")):
        return f"exit {code} disagrees with passed={report.get('passed')}"
    return None


def archetype_report(file: Path) -> dict[str, Any]:
    """Return the report `ARCHETYPE` prints for `file`, run from `HARNESS_ROOT`."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", ARCHETYPE, str(file)],
            cwd=HARNESS_ROOT,
            capture_output=True,
            timeout=ARCHETYPE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = f"{ARCHETYPE}: {exc}"
        raise ToolFault(message) from exc
    if proc.returncode not in ARCHETYPE_FINISHED:
        message = f"{ARCHETYPE} exited {proc.returncode}: "
        raise ToolFault(message + tool_text(proc.stderr or proc.stdout))
    try:
        report = json.loads(tool_text(proc.stdout))
    except ValueError as exc:
        message = f"{ARCHETYPE} printed no JSON: {exc}"
        raise ToolFault(message) from exc
    fault = run_fault(report, file, proc.returncode)
    if fault:
        raise ToolFault(fault)
    return dict(report)


def bind(item: Mapping[str, Any], path: str) -> dict[str, object]:
    """Return the archetype finding `item` in `FINDING_FIELDS` order, bound by tool and rule."""
    tool, rule = str(item["tool"]), str(item["rule_id"])
    housed = [found for name, found in places(tool, rule) if name == DISCIPLINE]
    reason = unplaced(tool).get(rule)
    if housed:
        discipline, reason = DISCIPLINE, ""
    elif reason is not None:
        discipline = UNPLACED
    else:
        discipline, reason = UNHOUSED, UNHOUSED_REASON
    return {
        "sigil": f"{NAME}@{EDITION}",
        "discipline": discipline,
        "characteristics": housed,
        "reason": reason,
        "tool": tool,
        "rule": rule,
        "severity": str(item["severity"]),
        "path": path,
        "line": int(item["line"]),
        "message": str(item["message"]),
    }


def _order(item: Mapping[str, Any]) -> tuple[int, str, str, str, str]:
    """Return the line, tool, rule, severity and message that sort a finding `item`."""
    return (
        int(item["line"]),
        str(item["tool"]),
        str(item["rule_id"]),
        str(item["severity"]),
        str(item["message"]),
    )


def _finding_file(item: Mapping[str, Any]) -> Path:
    """Return the file a finding `item` names, a relative one under `HARNESS_ROOT`."""
    named = Path(str(item["file"]))
    return (named if named.is_absolute() else HARNESS_ROOT / named).resolve()


def findings(text: str, root: Path) -> tuple[str, list[dict[str, object]]]:
    """Return the analyzers run and each `bind` row inside the lines `text` names."""
    located = locate(text, root)
    if isinstance(located, str):
        message = f"{text}: {located}, after tier 2 accepted it"
        raise ToolFault(message)
    file, _source, (first, last) = located
    path, separator, _ = text.partition(SEPARATOR)
    report = archetype_report(file)
    kept = []
    for item in report["findings"]:
        if _finding_file(item) != file.resolve():
            message = f"a finding names {item['file']}, not the input's file"
            raise ToolFault(message)
        if not separator or first <= int(item["line"]) <= last:
            kept.append(item)
    kept.sort(key=_order)
    rows = [bind(item, path) for item in kept]
    analyzers = sorted(report["tool_availability"])
    return f"{len(analyzers)} analyzers ok: {', '.join(analyzers)}", rows


def _functions_verdict(text: str, root: Path) -> Reading:
    """Return `SOUND`, or `UNSOUND` when a `findings` row has a blocking severity."""
    analyzers, rows = findings(text, root)
    blocking = sum(row["severity"] in BLOCKING_SEVERITIES for row in rows)
    unhoused = sum(row["discipline"] == UNHOUSED for row in rows)
    named = " or ".join(BLOCKING_SEVERITIES)
    return Reading(
        UNSOUND if blocking else SOUND,
        f"{analyzers}; {len(rows)} findings, {blocking} {named}",
        holds=True,
        detail={"findings": rows, "unhoused": unhoused},
    )


SIGIL = Sigil(
    name=NAME,
    edition=EDITION,
    owner=OWNER,
    disciplines=DISCIPLINES,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        CONTENT_TIER,
        {
            "runs": [
                f"python -m {ARCHETYPE} on the file the input names, from the root "
                "of the repository that holds this module, as one subprocess",
                "the JSON report it prints; the run stops when the report's target "
                "is another file, nothing was scanned, an analyzer did not report "
                "ok, the run recorded an error, or the exit code disagrees with "
                "passed",
                "each finding of the report, bound by its tool and rule as the "
                "bindings setting states",
                "for a symbol, only the findings inside its lines",
            ],
            "sound": SOUND_MEANS,
            "unsound": list(FINDING_FIELDS),
            "analyzers": "each analyzer the report's tool_availability names",
            "unhoused": "the row counts the findings bound unhoused",
        },
    ),
    outputs={
        SOUND: FlagRow(Flag.PASS),
        UNSOUND: FlagRow(Flag.FIX, holds_in_source=True),
    },
    refusal=REJECTED,
    follows={},
    readers=READERS,
    data_type=data_type_fault,
    content=content_fault,
    functions=_functions_verdict,
    fault_file=fault_file,
)


def run(argv: list[str] | None = None) -> int:
    """Return `main` for `SIGIL`, or 1 with the `ToolFault` on stderr."""
    try:
        return main(SIGIL, argv)
    except ToolFault as exc:
        print(f"the Coding Archetype did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
