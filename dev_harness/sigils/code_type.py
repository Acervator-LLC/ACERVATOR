"""`SIGIL` is CODE.TYPE on the `core` card; `type_check` judges one input line."""

import contextlib
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import mypy.api
import mypy.errorcodes
import mypy.version
import pyright

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
    Flag,
    FlagRow,
    Sigil,
    Verdict,
    in_application_source,
    judge,
    main,
    tool_text,
)

SOUND = "SOUND"
UNSOUND = "UNSOUND"
REJECTED = "REJECTED"

MYPY_BUILT = "2.1.0"
PYRIGHT_BUILT = "1.1.411"
PYRIGHT_TIMEOUT_S = 120
MYPY_FINISHED = (0, 1)
PYRIGHT_FINISHED = (0, 1)
NO_CODE = "no code"

FUNCTION = (
    "reads each value against the type its annotation, assignment or call gives it, "
    "for a type fault that fails at run time, breaks the typing standard, or leaves "
    "implicit what Python's conventions ask to state"
)
DISCIPLINES = ("conventions", "reliability", "typing")
MYPY = hold("mypy", sorted(mypy.errorcodes.error_codes), DISCIPLINES)
PYRIGHT = hold("pyright", house_rules("pyright"), DISCIPLINES)
HELD = {held.tool: frozenset(held.rules) for held in (MYPY, PYRIGHT)}

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "mypy_version": MYPY_BUILT,
    "pyright_version": PYRIGHT_BUILT,
    "function": FUNCTION,
    "disciplines": " ".join(DISCIPLINES),
    "scope": "each code on mypy's own error code list, mypy.errorcodes.error_codes, "
    "and each pyright rule a discipline houses or unplaced.json lists: the rules "
    "pyright reports as an error with no configuration",
    "mypy_rules": " ".join(MYPY.rules),
    "pyright_rules": " ".join(PYRIGHT.rules),
    "type_config": "the mypy and pyright settings each tool finds "
    "from the root of the target tree",
    "fault_file": "the file the input line names: HOLD when it sits "
    "in application_source",
}


class ToolFault(Exception):
    """mypy or pyright did not finish, or printed output `_findings` cannot read."""


@dataclass(frozen=True)
class Finding:
    """One error: the `tool`, its error `code` and its `line`."""

    tool: str
    code: str
    line: int


def _same_file(reported: Path, file: Path) -> bool:
    """Report whether the `reported` path and `file` resolve to one path."""
    return reported.resolve() == file.resolve()


def _mypy_findings(path: str, root: Path, file: Path) -> list[Finding]:
    """Return each mypy error in `file`, run on `path` from `root` with no cache."""
    with contextlib.chdir(root):
        stdout, stderr, status = mypy.api.run(
            ["--output", "json", "--cache-dir", os.devnull, path]
        )
    if status not in MYPY_FINISHED:
        raise ToolFault(f"mypy exited {status}: {tool_text(stderr or stdout)}")
    try:
        rows = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        return [
            Finding("mypy", row["code"] or NO_CODE, row["line"])
            for row in rows
            if row["severity"] == "error" and _same_file(root / row["file"], file)
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolFault(f"mypy printed an unreadable row: {exc}") from exc


def _pyright_findings(path: str, root: Path, file: Path) -> tuple[str, list[Finding]]:
    """Return the pyright version and each pyright error in `file`, run from `root`."""
    try:
        proc = pyright.run(
            "--outputjson",
            path,
            cwd=root,
            capture_output=True,
            timeout=PYRIGHT_TIMEOUT_S,
            check=False,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise ToolFault(f"pyright: {exc}") from exc
    if proc.returncode not in PYRIGHT_FINISHED:
        said = tool_text(proc.stderr or proc.stdout)
        raise ToolFault(f"pyright exited {proc.returncode}: {said}")
    try:
        report = json.loads(proc.stdout)
        if report["summary"]["filesAnalyzed"] < 1:
            raise ToolFault(f"pyright analyzed no file for {path}")
        return report["version"], [
            Finding(
                "pyright",
                diagnostic.get("rule") or NO_CODE,
                diagnostic["range"]["start"]["line"] + 1,
            )
            for diagnostic in report["generalDiagnostics"]
            if diagnostic["severity"] == "error"
            and _same_file(Path(diagnostic["file"]), file)
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolFault(f"pyright printed an unreadable report: {exc}") from exc


def _functions_verdict(text: str, root: Path) -> tuple[str, str]:
    """Return `SOUND`, or `UNSOUND` with each `HELD` `Finding` inside the `locate` span."""
    located = locate(text, root)
    if isinstance(located, str):
        raise ToolFault(f"{text}: {located}, after tier 2 accepted it")
    file, _, (first, last) = located
    path, separator, _ = text.partition(SETTINGS["separator"])
    is_narrowed = bool(separator)
    pyright_ran, pyright_found = _pyright_findings(path, root, file)
    findings = [
        finding
        for finding in [*_mypy_findings(path, root, file), *pyright_found]
        if finding.code in HELD[finding.tool]
        and (not is_narrowed or first <= finding.line <= last)
    ]
    versions = f"mypy {mypy.version.__version__}, pyright {pyright_ran}"
    if not findings:
        return SOUND, f"{versions}: neither tool reports an error under a rule on the card"
    rows = "; ".join(f"{item.tool} {item.code} line {item.line}" for item in findings)
    return UNSOUND, f"{versions}: {rows}"


SIGIL = Sigil(
    name="CODE.TYPE",
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
                    "mypy, through mypy.api.run from the root of the target tree, "
                    "with --output json and the null device as its cache folder"
                ),
                (
                    "pyright, through pyright.run from the root of the target tree, "
                    "with --outputjson"
                ),
                "only the errors under mypy_rules and pyright_rules",
                "for a symbol, only the errors inside its lines",
            ],
            "sound": "neither tool reports an error under a rule on the card",
            "unsound": ["tool", "error code", "line"],
            "left": {MYPY.tool: MYPY.left, PYRIGHT.tool: PYRIGHT.left},
            "left_because": LEFT_BECAUSE,
            "not_held": "an error under a code outside the scope, or with no code, "
            "moves no verdict",
            "trusts": "a plugin or interpreter the tree's own mypy or pyright "
            "settings name runs as code",
            "imports": "each tool resolves them from the root of the target tree "
            "and the installed packages it finds, never from the tree's own "
            "list of files to check",
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


def type_check(
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
        print(f"mypy or pyright did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
