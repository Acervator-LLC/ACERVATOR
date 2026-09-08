"""One report contract shared by every archetype.

WHY THIS FILE EXISTS
====================
Five archetypes each carried their own copy of `Finding` and
`ArchetypeReport`. The copies drifted, and two of the drifts were
measured on 2026-08-13.

DRIFT 1 - a green report for a scan that never happened.
Every copy answered `passed` as "no critical and no high finding". An
early return that appended `target not found` to `errors` and returned
left the findings list EMPTY, so the property answered True and the CLI
exited 0. Measured against one confirmed-absent path:

    coding / ta / watchdog / gui / docs -> exit 0, passed=true,
                                           findings 0

An empty report was green by construction. Every caller therefore had to
range-check its own paths, a rule that has to be re-implemented in each
new tool and will eventually be forgotten. It had already sent one
mistyped fixture path through as a pass.

DRIFT 2 - a green report when the analyzers are gone.
The real `CodingArchetype` on the harness's own `known_bad.py` - the
fixture that MUST be red - answered passed=True with 0 findings when
ruff, mypy, bandit and vulture were all absent. `passed=True` could mean
"the file is clean" or "the linters are gone", and nothing in the report
separated them. A fresh clone reported everything green.

DRIFT 3 - `ta_archetype` never published `by_severity`, so the gate that
sums that key printed "0 findings" above "by tool: ruff=81".

DRIFT 4 - a green report with a non-empty `errors` array. Measured
2026-08-13 on an empty directory: exit 0, passed=True, 0 findings, and
`errors` holding "rules: source read failed: PermissionError". Every
`errors.append` in every archetype records a part of the run that did
not happen, so nothing in the report contradicted the green.

DRIFT 5 - a rule module that read nothing reported `ok`. Each archetype
handed the rule modules `target.read_text()`. On a directory that
raises, the caller substituted an empty string, the four modules scanned
"" and every one of them reported `ok`. Measured on a directory holding
one markdown file that cites a path which does not exist: the FILE
target reported hallucination H001 and the DIRECTORY target reported
nothing, green, with all rule statuses `ok`.

So `passed` now rests on four conditions, in this order:

    1. the target was actually scanned,
    2. every required analyzer reported `ok`,
    3. the run recorded no error,
    4. no finding is critical or high.

The first three are properties of the RUN. The fourth is a property of
the CODE. Only the fourth was ever checked, so a run that did nothing
was indistinguishable from a file with nothing wrong.

WHAT `scanned` MEANS
====================
`scanned` is False until an archetype has reached the point where its
analysis actually runs over the target. It is not "the target exists" --
`DocsArchetype` sets it only after enumerating at least one markdown
file, because a directory holding no markdown was also scanning nothing.

Setting it is the archetype's job, and the default is False, so a new
archetype that forgets to set it reports NOT green rather than silently
green. The failure mode points the safe way.

WHAT `ok` MEANS
===============
A tool status is OK when it is exactly the string `ok`. Anything else --
`missing`, `error`, or a free-form string like `unavailable: ...` -- is
an analyzer that did not deliver, and a run missing one of its analyzers
is not evidence about the file. `OPTIONAL_ANALYZERS` names the analyzers
whose absence is reported but tolerated; it is EMPTY, and adding a name
to it is a declaration that the coverage is optional.

FALSIFICATION
=============
This contract is wrong if: a report with `scanned=False` ever answers
`passed=True`; a report with `unhandled=True` ever answers
`passed=True`; a report carrying a tool status other than `ok` for a
required analyzer ever answers `passed=True`; `by_severity` sums to a
number other than `len(findings)`; or a target that WAS scanned with
every analyzer `ok` and no high finding answers anything but True.
`tests/test_archetype_report_contract.py` holds one case per sentence.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The working directory every analyzer subprocess is run from.
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

# Severities that block. Kept here so five archetypes cannot disagree
# about what "high" means.
BLOCKING_SEVERITIES: tuple[str, ...] = ("critical", "high")

# The one status string that means "this analyzer ran and delivered".
STATUS_OK = "ok"

# Analyzers whose absence is reported but does not void the report.
OPTIONAL_ANALYZERS: frozenset[str] = frozenset()


@dataclass
class Finding:
    """One normalized result from one analyzer."""

    tool: str
    severity: str  # critical | high | medium | low | info
    file: str
    line: int
    rule_id: str
    message: str

    def to_dict(self) -> dict:
        """Return the JSON view of this finding."""
        return {
            "tool": self.tool,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "rule_id": self.rule_id,
            "message": self.message,
        }


@dataclass
class ArchetypeReport:
    """One archetype's verdict on one target.

    `scanned` starts False. An archetype sets it True at the point its
    analysis begins running over the target, so an early return -- an
    absent path, an empty directory -- leaves it False and the report
    cannot be green.

    `unhandled` is the separate answer "this archetype carries no
    analyzer for this file type". It is never `passed`, because nothing
    ran, and it is not an entry in `errors` either, because nothing
    failed.
    """

    target: str
    findings: list[Finding] = field(default_factory=list)
    tool_availability: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    falsification: str = ""  # required - what would prove this report wrong
    scanned: bool = False
    # The language the archetype detected. Empty for a target whose
    # language it does not decide, such as a mixed directory.
    language: str = ""
    unhandled: bool = False

    def unavailable_required(self) -> list[str]:
        """Return the required analyzers that did not report `ok`.

        Anything that is not exactly `ok` counts, including a free-form
        status string, because a status nobody parses is a status nobody
        acted on.
        """
        return sorted(
            name
            for name, status in self.tool_availability.items()
            if status != STATUS_OK and name not in OPTIONAL_ANALYZERS
        )

    def blocking(self) -> list[Finding]:
        """Return the findings whose severity blocks."""
        return [f for f in self.findings if f.severity in BLOCKING_SEVERITIES]

    @property
    def passed(self) -> bool:
        """True only when the run happened, was complete, and was clean.

        Five conditions, and the first four are about the RUN: an
        unhandled file type, an unscanned target, a run with an absent
        analyzer, and a run that recorded an error are all NOT green,
        whatever the findings list says.

        `unhandled` blocks for the same reason `scanned` does. A file
        type this archetype carries no analyzer for was never examined,
        so answering True would make the verdict a rubber stamp for
        every such file rather than a statement about the code.

        `errors` blocks because every append to it names a part of the
        run that did not happen. Measured on an empty directory before
        this line existed: passed=True, 0 findings, and one error saying
        the rule sources could not be read. Reading `errors` here also
        means a future archetype that records a fault and forgets to set
        a status still fails closed.
        """
        if self.unhandled:
            return False
        if not self.scanned:
            return False
        if self.unavailable_required():
            return False
        if self.errors:
            return False
        return not self.blocking()

    def why_not_green(self) -> list[str]:
        """Return the reasons this report is not green, in verdict order.

        Empty when the report is green. Callers print this rather than
        re-deriving the conditions, so the CLI, the hook and the release
        gate cannot describe the same verdict differently.
        """
        reasons: list[str] = []
        if self.unhandled:
            reasons.append(
                f"no analyzer for {self.language or 'unknown'}: {self.target} "
                f"- this file type was NOT examined, which is not the same "
                f"as clean",
            )
        if not self.scanned:
            reasons.append(
                f"target was never scanned: {self.target} - an empty "
                f"report is not a clean one"
            )
        absent = self.unavailable_required()
        if absent:
            reasons.append(
                f"required analyzer(s) did not run: {', '.join(absent)} - "
                f"coverage is incomplete, so this run is not evidence"
            )
        if self.errors:
            reasons.append(
                f"{len(self.errors)} error(s) recorded during the run: "
                f"{'; '.join(self.errors)[:400]}"
            )
        blocking = self.blocking()
        if blocking:
            reasons.append(f"{len(blocking)} critical/high finding(s)")
        return reasons

    def by_tool(self) -> dict[str, int]:
        """Return {tool: finding count}."""
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.tool] = counts.get(f.tool, 0) + 1
        return counts

    def by_severity(self) -> dict[str, int]:
        """Return {severity: finding count}.

        Published by EVERY archetype. `.claude/hooks/archetype_gate.py`
        sums this key to print the finding count; the one archetype that
        omitted it made that line read 0 while the report carried 81.
        """
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts

    def to_dict(self) -> dict:
        """Return the JSON view consumed by the gate and the hooks."""
        return {
            "target": self.target,
            "passed": self.passed,
            "scanned": self.scanned,
            "language": self.language,
            "unhandled": self.unhandled,
            "unavailable_required": self.unavailable_required(),
            "why_not_green": self.why_not_green(),
            "tool_availability": self.tool_availability,
            "by_tool": self.by_tool(),
            "by_severity": self.by_severity(),
            "errors": self.errors,
            "falsification": self.falsification,
            "findings": [f.to_dict() for f in self.findings],
        }


def refuse_silent_failure(
    proc: subprocess.CompletedProcess,
    tool: str,
) -> None:
    """Raise when `tool` exited non-zero and printed nothing.

    Every analyzer this harness drives writes its findings to STDOUT, so
    every one of them has the same failure shape: a non-zero exit with
    empty stdout is a run that did not deliver, and it is byte-identical
    to a clean file at the line `if not proc.stdout.strip(): return
    findings, "ok"`.

    `_module_absent` only catches one cause of that shape, the literal
    stderr string "No module named X". MEASURED 2026-08-13 with ruff
    installed and working, one malformed `ruff.toml` beside the target:
    ruff exited 2 with 0 bytes of stdout and "Failed to load
    configuration" on stderr, and the archetype reported ruff `ok` with
    0 findings and passed=True -- on a fixture that draws 7 findings
    with a valid config. Absent was handled; installed-but-broken was
    not.

    Callers map the RuntimeError to `tool_availability[tool] = "error"`,
    which is not `ok`, so the report cannot be green.
    """
    if proc.returncode != 0 and not (proc.stdout or "").strip():
        detail = (proc.stderr or "").strip().replace("\n", " ")
        raise RuntimeError(
            f"{tool} exited {proc.returncode} without output: " f"{detail[:240]}"
        )


def rule_source_files(target: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Return the files the rule modules must scan for `target`.

    A FILE is returned as itself whatever its suffix, because an
    archetype pointed at one file judges that file. A DIRECTORY expands
    to the files under it carrying one of `suffixes`, which is the set
    the archetype is actually judging.
    """
    if target.is_dir():
        return [
            p
            for p in sorted(target.rglob("*"))
            if p.suffix in suffixes and p.is_file() and "__pycache__" not in p.parts
        ]
    return [target]


def read_rule_sources(
    paths: list[Path],
) -> tuple[list[tuple[Path, str]], list[str]]:
    """Return [(path, text)] for the readable paths, and the failures.

    The failure list is what the caller turns into a non-`ok` status. A
    source the rule modules could not read is coverage they did not
    provide, and calling that `ok` is the same lie as calling an
    analyzer that never ran `ok`.
    """
    sources: list[tuple[Path, str]] = []
    failures: list[str] = []
    for path in paths:
        try:
            sources.append((path, path.read_text(encoding="utf-8", errors="replace")))
        except (OSError, ValueError, UnicodeError) as exc:
            failures.append(f"{path}: {type(exc).__name__}: {exc}")
    return sources, failures


def scan_rule_modules(
    report: ArchetypeReport,
    target: Path,
    modules: tuple[tuple[str, str], ...],
    suffixes: tuple[str, ...],
    files: list[Path] | None = None,
) -> None:
    """Run each rule module over every source `target` covers.

    `modules` is ((status_name, import_path), ...). `files` overrides the
    enumeration for an archetype that has already built the list --
    DocsArchetype passes the markdown files it enumerated.

    A module's status is `ok` ONLY when at least one source was read and
    every read succeeded. That is the whole point: a rule module that
    scanned nothing must not report the same word as one that scanned
    the file and found it clean.
    """
    paths = files if files is not None else rule_source_files(target, suffixes)
    sources, failures = read_rule_sources(paths)
    for detail in failures:
        report.errors.append(f"rules: source read failed: {detail}")
    if not sources:
        report.errors.append(f"rules: no source to scan at: {target}")
    status = STATUS_OK if sources and not failures else "error"
    for rule_name, module_path in modules:
        try:
            mod = __import__(module_path, fromlist=["scan"])
            for path, src in sources:
                for rf in mod.scan(path, src):
                    report.findings.append(
                        Finding(
                            tool=rf.tool,
                            severity=rf.severity,
                            file=rf.file,
                            line=rf.line,
                            rule_id=rf.rule_id,
                            message=rf.message,
                        )
                    )
            report.tool_availability[rule_name] = status
        except Exception as exc:
            report.tool_availability[rule_name] = "error"
            report.errors.append(f"{rule_name}: {type(exc).__name__}: {exc}")


def cli_exit(report: ArchetypeReport) -> int:
    """Return the process exit code for `report`, printing why if red.

    One function so five CLIs cannot disagree about what exit 1 means.
    The reasons go to stderr, because stdout carries the JSON report and
    a caller pipes it into a parser.
    """
    if report.passed:
        return 0
    if not report.scanned:
        sys.stderr.write(
            f"[archetype] NOTHING RAN: {len(report.tool_availability)} "
            f"analyzers reported on {report.target}. Exit 1 here is an "
            f"absent or unreadable target, not a rule finding.\n"
        )
    for reason in report.why_not_green():
        sys.stderr.write(f"[archetype] not green: {reason}\n")
    return 1
