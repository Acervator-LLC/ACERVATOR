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
import mypy.version
import pyright

from .code_optimize import SETTINGS as OPTIMIZE_SETTINGS
from .code_optimize import SIGIL as OPTIMIZE
from .code_optimize import _locate
from .core import (
    APPLICATION_SOURCE,
    Flag,
    FlagRow,
    Sigil,
    Verdict,
    in_application_source,
    judge,
    main,
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

SETTINGS: dict[str, str] = {
    "separator": OPTIMIZE_SETTINGS["separator"],
    "mypy_version": MYPY_BUILT,
    "pyright_version": PYRIGHT_BUILT,
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


def _said(output: str | bytes) -> str:
    """Return `output` decoded and stripped."""
    if isinstance(output, bytes):
        output = output.decode("utf-8", "replace")
    return output.strip()


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
        raise ToolFault(f"mypy exited {status}: {_said(stderr or stdout)}")
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
        raise ToolFault(
            f"pyright exited {proc.returncode}: {_said(proc.stderr or proc.stdout)}"
        )
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
    """Return `SOUND`, or `UNSOUND` with each `Finding` inside the `_locate` span."""
    located = _locate(text, root)
    if isinstance(located, str):
        raise ToolFault(f"{text}: {located}, after tier 2 accepted it")
    file, _, (first, last) = located
    path, separator, _ = text.partition(SETTINGS["separator"])
    is_narrowed = bool(separator)
    pyright_ran, pyright_found = _pyright_findings(path, root, file)
    findings = [
        finding
        for finding in [*_mypy_findings(path, root, file), *pyright_found]
        if not is_narrowed or first <= finding.line <= last
    ]
    versions = f"mypy {mypy.version.__version__}, pyright {pyright_ran}"
    if not findings:
        return SOUND, f"{versions}: neither tool reports an error"
    rows = "; ".join(f"{item.tool} {item.code} line {item.line}" for item in findings)
    return UNSOUND, f"{versions}: {rows}"


def _fault_file(text: str, root: Path) -> Path | None:
    """Return the file `text` names under `root`, or None when tier 1 refuses it."""
    if OPTIMIZE.data_type(text):
        return None
    path = text.partition(SETTINGS["separator"])[0]
    return root.joinpath(*path.split("/"))


SIGIL = Sigil(
    name="CODE.TYPE",
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
                    "mypy, through mypy.api.run from the root of the target tree, "
                    "with --output json and the null device as its cache folder"
                ),
                (
                    "pyright, through pyright.run from the root of the target tree, "
                    "with --outputjson"
                ),
                "for a symbol, only the errors inside its lines",
            ],
            "sound": "neither tool reports an error",
            "unsound": ["tool", "error code", "line"],
            "trusts": "a plugin or interpreter the tree's own mypy or pyright "
            "settings name runs as code",
        },
    ),
    outputs={
        SOUND: FlagRow(Flag.PASS),
        UNSOUND: FlagRow(Flag.FIX, holds_in_source=True),
    },
    refusal=REJECTED,
    follows={},
    readers=OPTIMIZE.readers,
    data_type=OPTIMIZE.data_type,
    content=OPTIMIZE.content,
    functions=_functions_verdict,
    fault_file=_fault_file,
)


def type_check(
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
        print(f"mypy or pyright did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
