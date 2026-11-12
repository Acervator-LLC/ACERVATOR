"""`SIGIL` is CODE.SECURE on the `core` card; `secure_check` judges one input line."""

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from importlib import metadata
from pathlib import Path

from .code_optimize import SETTINGS as OPTIMIZE_SETTINGS
from .code_optimize import SIGIL as OPTIMIZE
from .code_optimize import _locate
from .core import (
    APPLICATION_SOURCE,
    Flag,
    FlagRow,
    Reading,
    Sigil,
    Verdict,
    in_application_source,
    judge,
    main,
)

CLEAN = "CLEAN"
WEAK = "WEAK"
REJECTED = "REJECTED"

BANDIT_BUILT = "1.9.4"
SEMGREP_BUILT = "1.171.0"
BANDIT_TIMEOUT_S = 120
SEMGREP_TIMEOUT_S = 180
BANDIT_FINISHED = (0, 1)
SEMGREP_FINISHED = (0,)
BANDIT_STDIN = "<stdin>"
NO_CWE = "no CWE"
SEVERITIES = ("low", "medium", "high")
BANDIT_SEVERITY = {"LOW": "low", "MEDIUM": "medium", "HIGH": "high"}
SEMGREP_SEVERITY = {"INFO": "low", "WARNING": "medium", "ERROR": "high"}

_CWE_RE = re.compile(r"CWE-(\d+)")

SETTINGS: dict[str, str] = {
    "separator": OPTIMIZE_SETTINGS["separator"],
    "bandit_version": BANDIT_BUILT,
    "semgrep_version": SEMGREP_BUILT,
    "severity_floor": "medium",
    "fault_file": "the file the input line names: WEAK reads HOLD when it sits "
    "in application_source and a finding reaches severity_floor",
}


class ToolFault(Exception):
    """bandit or semgrep did not finish, or printed a report this module cannot read."""


@dataclass(frozen=True)
class Finding:
    """One finding: the `tool`, its `rule` id, `cwe` id, `severity` and `line`."""

    tool: str
    rule: str
    cwe: str
    severity: str
    line: int


def _said(output: bytes) -> str:
    """Return `output` decoded and stripped."""
    return output.decode("utf-8", "replace").strip()


@cache
def bandit_version() -> str:
    """Return the installed bandit version `python -P -m bandit` runs."""
    return metadata.version("bandit")


def _semgrep_cwe(cwe: object) -> str:
    """Return each CWE id in a semgrep `cwe` entry, joined, or `NO_CWE`."""
    texts = [cwe] if isinstance(cwe, str) else cwe if isinstance(cwe, list) else []
    ids = [f"CWE-{number}" for text in texts for number in _CWE_RE.findall(str(text))]
    return ", ".join(dict.fromkeys(ids)) or NO_CWE


def _bandit_findings(source: bytes) -> list[Finding]:
    """Return each bandit `Finding` for `source`, read on stdin by default tests."""
    try:
        proc = subprocess.run(
            [sys.executable, "-P", "-m", "bandit", "-f", "json", "-q", "-"],
            input=source,
            capture_output=True,
            timeout=BANDIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = f"bandit: {exc}"
        raise ToolFault(message) from exc
    if proc.returncode not in BANDIT_FINISHED:
        said = _said(proc.stderr or proc.stdout)
        message = f"bandit exited {proc.returncode}: {said}"
        raise ToolFault(message)
    try:
        report = json.loads(proc.stdout)
        if report["errors"] or BANDIT_STDIN not in report["metrics"]:
            message = f"bandit did not read the file: {report['errors']}"
            raise ToolFault(message)
        return [
            Finding(
                "bandit",
                row["test_id"],
                f"CWE-{row['issue_cwe']['id']}" if row["issue_cwe"]["id"] else NO_CWE,
                BANDIT_SEVERITY[row["issue_severity"]],
                row["line_number"],
            )
            for row in report["results"]
        ]
    except (ValueError, KeyError, TypeError) as exc:
        message = f"bandit printed an unreadable report: {exc!r}"
        raise ToolFault(message) from exc


def _semgrep_findings(name: str, source: bytes) -> tuple[str, list[Finding]]:
    """Return the semgrep version and each `Finding` for `source` copied as `name`."""
    with tempfile.TemporaryDirectory() as folder:
        Path(folder, name).write_bytes(source)
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-P",
                    "-c",
                    "from semgrep.console_scripts.entrypoint import main; main()",
                    "scan",
                    "--config=p/python",
                    "--config=p/security-audit",
                    "--json",
                    "--quiet",
                    "--no-git-ignore",
                    ".",
                ],
                cwd=folder,
                capture_output=True,
                timeout=SEMGREP_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            message = f"semgrep: {exc}"
            raise ToolFault(message) from exc
    if proc.returncode not in SEMGREP_FINISHED:
        said = _said(proc.stderr or proc.stdout)
        message = f"semgrep exited {proc.returncode}: {said}"
        raise ToolFault(message)
    try:
        report = json.loads(proc.stdout)
        if report["errors"]:
            message = f"semgrep reported errors: {report['errors']}"
            raise ToolFault(message)
        if report["paths"]["scanned"] != [name]:
            message = f"semgrep scanned {report['paths']['scanned']}, not {name}"
            raise ToolFault(message)
        return report["version"], [
            Finding(
                "semgrep",
                row["check_id"],
                _semgrep_cwe(row["extra"].get("metadata", {}).get("cwe")),
                SEMGREP_SEVERITY[row["extra"]["severity"]],
                row["start"]["line"],
            )
            for row in report["results"]
        ]
    except (ValueError, KeyError, TypeError) as exc:
        message = f"semgrep printed an unreadable report: {exc!r}"
        raise ToolFault(message) from exc


def _functions_verdict(text: str, root: Path) -> Reading:
    """Return `CLEAN`, or `WEAK` holding when a finding reaches `severity_floor`."""
    located = _locate(text, root)
    if isinstance(located, str):
        message = f"{text}: {located}, after tier 2 accepted it"
        raise ToolFault(message)
    file, source, (first, last) = located
    is_narrowed = bool(text.partition(SETTINGS["separator"])[1])
    semgrep_ran, semgrep_found = _semgrep_findings(file.name, source)
    findings = [
        finding
        for finding in [*_bandit_findings(source), *semgrep_found]
        if not is_narrowed or first <= finding.line <= last
    ]
    versions = f"bandit {bandit_version()}, semgrep {semgrep_ran}"
    if not findings:
        return Reading(
            CLEAN, f"{versions}: neither tool reports a finding", holds=False
        )
    floor = SEVERITIES.index(SETTINGS["severity_floor"])
    holds = any(SEVERITIES.index(finding.severity) >= floor for finding in findings)
    rows = "; ".join(
        f"{item.tool} {item.rule} {item.cwe} {item.severity} line {item.line}"
        for item in findings
    )
    return Reading(WEAK, f"{versions}: {rows}", holds)


def _fault_file(text: str, root: Path) -> Path | None:
    """Return the file `text` names under `root`, or None when tier 1 refuses it."""
    if OPTIMIZE.data_type(text):
        return None
    path = text.partition(SETTINGS["separator"])[0]
    return root.joinpath(*path.split("/"))


SIGIL = Sigil(
    name="CODE.SECURE",
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
                    "bandit, as python -P -m bandit -f json -q -, "
                    "with the file's bytes on stdin and bandit's default tests"
                ),
                (
                    "semgrep, through semgrep.console_scripts.entrypoint, "
                    "as semgrep scan --config=p/python --config=p/security-audit "
                    "--json --quiet --no-git-ignore ., in an empty temporary folder "
                    "holding a copy of the file under its own name"
                ),
                "for a symbol, only the findings inside its lines",
            ],
            "clean": "neither tool reports a finding",
            "weak": ["tool", "rule id", "CWE id", "severity", "line"],
            "cwe": "the CWE id each tool reports for its own finding, else no CWE",
            "severity": {"bandit": BANDIT_SEVERITY, "semgrep": SEMGREP_SEVERITY},
            "fetches": "semgrep downloads both rule sets from its registry on each run",
            "refuses": "a tool that exits otherwise, reports an error, "
            "or did not read the file",
        },
    ),
    outputs={
        CLEAN: FlagRow(Flag.PASS),
        WEAK: FlagRow(Flag.FIX, holds_in_source=True),
    },
    refusal=REJECTED,
    follows={},
    readers=OPTIMIZE.readers,
    data_type=OPTIMIZE.data_type,
    content=OPTIMIZE.content,
    functions=_functions_verdict,
    fault_file=_fault_file,
)


def secure_check(
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
        print(f"bandit or semgrep did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
