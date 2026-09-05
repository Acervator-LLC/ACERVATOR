"""Touch-set baseline and check — refuse a unit's red file before the edit.

A unit cannot be greener than the files it lands in. Four failure modes
each cost a full review round on 2026-08-13, and every one of them is
mechanically detectable BEFORE a human or an agent looks at the diff.
This module detects them.

  MODE 1  A RED FILE IN THE TOUCH SET. `src/gui/bot_wizard.py` entered a
          touch set already carrying 4 coding highs on the unmodified
          live tree. Three were unfixable inside the unit's authority, so
          the whole unit blocked on a file it did not need. Nothing asked
          before the first edit. `baseline` asks, and REFUSES.

  MODE 2  A SUPPRESSION ADDED AND UNREPORTED. A `# noqa: BLE001` landed
          in a NEW test file and survived the build's own gate, because
          an archetype keys `passed` on high/critical and an unused-noqa
          lands at MEDIUM. Worse, measured 2026-08-13: a single
          `# noqa: F401` REMOVES a 90%-confidence vulture HIGH from the
          report entirely, so `passed` cannot see its own blinding. Only
          counting directives catches it. `check` counts them per file
          and refuses an INCREASE — and because the incident happened in
          a file that did not exist at baseline, it also SWEEPS the
          island for files the pin never saw. Directives are MEASURED in
          every file, but the REFUSAL applies to code only: a directive
          written in prose in a `.md` file silences no checker, and this
          module refused its own documentation until that was fixed.

  MODE 3  AN ARCHETYPE EXITS 0 ON A PATH THAT DOES NOT EXIST. Measured
          2026-08-13 on all five archetypes — coding, ta, watchdog, gui
          and docs each return exit 0 AND `passed: true` for a target
          name that is absent from the tree, recording the reason only
          in `errors[]`, which the exit code discards. That is an oracle
          false negative in the harness itself: a verification that
          scanned nothing reports success. It bit the referee — a
          positive control run on a mistyped fixture path returned 0 and
          briefly read as a defect that did not exist. The archetypes
          may not be edited, so THIS module refuses a path that does not
          exist BEFORE it ever reads a verdict, and refuses every other
          way it has found of concluding "fine" having graded nothing.

  MODE 4  A LINE-ENDING KIND FLIP. Twice in one session an editor
          rewrote a CRLF file as LF. One was a 2,099-line test file;
          unnoticed, that is a 27,348-line diff hiding the real change.
          The repo has NO repo-wide ending — measured src/**/*.py LF 95 /
          CRLF 68, tests/*.py LF 149 / CRLF 51 — so the rule is per-file
          preservation, and it is MEASURED here, never assumed.

WHAT THIS MODULE IS NOT
=======================
It MEASURES and REFUSES. It fixes nothing, edits no file it inspects,
and writes nothing except the pin. It is not a replacement for the
archetypes and never reports a verdict an archetype did not produce:
every `passed` in a pin is the archetype's own `passed` property, read
through its published `to_dict()` contract.

WHERE THE ROUTING RULE COMES FROM
=================================
`.claude/hooks/archetype_gate.py:_pick_archetypes` already decides which
archetype grades which path for the PostToolUse gate. That function is
IMPORTED here, not copied, so the two can never drift. If it cannot be
loaded this module refuses to run rather than falling back to a private
mapping — a silent fallback would be exactly the reimplementation the
scope forbids.

The gate's rule routes `.py` to coding, plus gui when the source defines
a Qt-based class, plus ta when the file looks like indicator maths; and
`.md` to docs.

Reusing the gate's rule has a KNOWN COST, stated because hiding it would
defeat the purpose: the gate's `_QT_BASES` set omits `QWizard` and
`QWizardPage`, so `src/gui/bot_wizard.py` never reaches gui_archetype
and this module cannot see the 2 gui highs the MODE 1 incident recorded.
A private mapping here would paper over that gap instead of surfacing
it. Fixing the gate fixes this module for free.

READING `passed` ACROSS FIVE SHAPES
===================================
All five archetypes publish `passed`, `findings`, `errors`,
`tool_availability`, `by_tool` and `falsification`. Four also publish
`by_severity`. `ta_archetype.ArchetypeReport.to_dict` does NOT — its
key set is exactly the other four minus `by_severity`. So severity is
RECOUNTED here from the `findings` list for every archetype, never read
from `by_severity`. Trusting that key would silently score every ta
report as zero-of-everything.

`passed` is accepted only when it is a real `bool`. A truthy string is
not a verdict.

COST
====
Archetypes are invoked in-process through `review()` and run
concurrently, because each spends its wall time waiting on its own
subprocesses. Measured: a realistic two-file touch set
(scrumming_bot.py at 14,154 lines plus bot_live_settings.py at 4,494)
takes ~70s, of which coding_archetype is ~93%. Cost scales roughly
linearly with touch-set size. The DEFAULT IS COMPLETE — a default that
skips is the failure mode this module exists to remove. `--only`
narrows the module set for an interactive re-check; it records
`complete: false` plus the exact set in the pin, and a reduced pin makes
`check` FAIL unless `--accept-reduced` is passed, so a narrowed run can
never be mistaken for a complete pass at the exit-code surface.

EXIT CODES
==========
  0  every path measured, nothing fired
  1  a gate fired — red file, vanished path, added directive, flipped
     line ending, a tool that stopped running, a new file the pin never
     saw, or an archetype that could not be made to produce a verdict
  2  the run could not be made — a path missing or outside the root, an
     unusable or self-inconsistent pin, routing unavailable

FALSIFICATION
=============
This module is wrong if a path that does not exist reaches an archetype
verdict; if a file that is already red enters a pin; if an added
suppression, a flipped line-ending kind, a vanished path, a new red file
or a newly-missing lint tool returns 0 from `check`; if a pre-existing
directive count that did not change returns non-zero; if a comment that
merely DISCUSSES a suppression is counted as one; if it reports a
`passed` no archetype produced; or if it writes any byte outside the pin
file.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import io
import json
import os
import re
import sys
import tokenize
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import cast

REPO = Path(__file__).resolve().parents[1]

GATE_RELPATH = ".claude/hooks/archetype_gate.py"
ROUTING_CITATION = f"{GATE_RELPATH}:_pick_archetypes"

DEFAULT_PIN = "tools/.touchset_pin.json"

# A pin written at an earlier version is refused, never half-read.
PIN_VERSION = 2

# Directories never walked when sweeping for files the pin never saw.
SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "node_modules",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        ".deepeval",
    }
)

ISLAND_MANIFEST = ".island.json"

# Module name to the class exposing `review(Path) -> ArchetypeReport`.
ARCHETYPE_CLASSES: dict[str, str] = {
    "dev_harness.harness.coding_archetype": "CodingArchetype",
    "dev_harness.harness.gui_archetype": "GUIArchetype",
    "dev_harness.harness.ta_archetype": "TAArchetype",
    "dev_harness.harness.docs_archetype": "DocsArchetype",
    "dev_harness.harness.watchdog_archetype": "WatchdogArchetype",
}

WATCHDOG_MODULE = "dev_harness.harness.watchdog_archetype"

# Provenance labels. A pin must always say which authority put a module
# in the set, so this module never borrows the gate's standing.
FROM_GATE = ROUTING_CITATION

SEVERE = ("critical", "high")

DIRECTIVE_SET_LABEL = "brief-seven+nosemgrep+mypy2+pylint-skip-file"

# Longest form first: `re.match` alternation is ordered, so `ruff: noqa`
# must come before the bare `noqa` inside it.
DIRECTIVE_RE = re.compile(
    r"ruff:\s*noqa"
    r"|flake8:\s*noqa"
    r"|pylint:\s*disable"
    r"|pylint:\s*skip-file"
    r"|pyright:\s*ignore"
    r"|type:\s*ignore"
    r"|mypy:\s*disable-error-code"
    r"|mypy:\s*ignore-errors"
    r"|nosemgrep"
    r"|noqa"
    r"|nosec",
    re.IGNORECASE,
)

# Comment openers for the non-Python fallback scan.
MARKER_RE = re.compile(r"(?:<!--|/\*|//|--|#)[ \t]*")

SCAN_TOKENIZE = "tokenize-comment-pragmas"
SCAN_MARKERS = "marker-anchored-conservative"

DEFAULT_JOBS = 4

# Wall-clock ceiling for one archetype on one file. An archetype runs in a
# thread and a thread cannot be killed, so a timeout exits the process hard.
DEFAULT_TIMEOUT = 1800

# How many never-pinned files `check` will measure before refusing.
DEFAULT_NEW_FILE_LIMIT = 25

DETERMINED_UNKNOWN = "NONE"


class RoutingUnavailable(RuntimeError):
    """The gate's routing rule could not be loaded.

    Raised instead of falling back to a private mapping. A private copy
    would drift from the gate and would report a verdict under an
    authority this module does not have.
    """


class ArchetypeTimeout(RuntimeError):
    """An archetype exceeded its wall-clock ceiling.

    Carried out to `main`, which prints it and exits hard. The worker
    thread is still running and cannot be joined, so a clean return
    would hang at interpreter exit.
    """


def _say(line: str = "") -> None:
    """Write one line to stdout."""
    sys.stdout.write(line + "\n")


def _now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    """Return the SHA-256 of raw bytes, with no normalisation.

    Line endings are NOT normalised here, unlike `tools/island.py`. This
    hash is content identity for a pin, and a line-ending flip is
    exactly one of the changes the pin exists to notice.
    """
    return hashlib.sha256(data).hexdigest()


def git_head(root: Path) -> str | None:
    """Return the commit `root/.git` points at, by reading files only.

    No subprocess: this module invokes no external process at all, which
    is why it carries no `S`-family security findings and needs no
    suppression. Provenance only — nothing gates on it.
    """
    head = root / ".git" / "HEAD"
    try:
        text = head.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.startswith("ref:"):
        return text or None
    ref = text.partition("ref:")[2].strip()
    try:
        return (root / ".git" / ref).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def load_gate() -> ModuleType:
    """Import `.claude/hooks/archetype_gate.py` as a module object.

    The hook is not on any import path, so it is loaded from its file
    location. Import-time work in that module is limited to a stdout
    reconfigure and a path constant, so importing it has no side effect
    on the tree.
    """
    gate_path = REPO / Path(GATE_RELPATH)
    if not gate_path.is_file():
        message = f"no routing rule at {gate_path}"
        raise RoutingUnavailable(message)
    spec = importlib.util.spec_from_file_location(
        "touchset_archetype_gate",
        gate_path,
    )
    if spec is None or spec.loader is None:
        message = f"cannot build an import spec for {gate_path}"
        raise RoutingUnavailable(message)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        message = f"{gate_path} failed to import: {type(exc).__name__}: {exc}"
        raise RoutingUnavailable(message) from exc
    return module


def gate_router(gate: ModuleType) -> Callable[[Path, str], list[str]]:
    """Return the gate's `_pick_archetypes`, or refuse.

    The cast records what the hook's own signature already states —
    `_pick_archetypes(path: Path, source: str) -> list`. It asserts
    nothing about behaviour, and the `callable` guard above is what
    actually protects the call.
    """
    picker = getattr(gate, "_pick_archetypes", None)
    if not callable(picker):
        message = (
            f"{GATE_RELPATH} defines no callable _pick_archetypes; the "
            "routing rule this module reuses has moved or been renamed"
        )
        raise RoutingUnavailable(message)
    return cast("Callable[[Path, str], list[str]]", picker)


def _gate_suffixes(
    gate: ModuleType, name: str, fallback: tuple[str, ...]
) -> tuple[str, ...]:
    """Return a suffix tuple published by the gate, or a stated default."""
    value = getattr(gate, name, None)
    if isinstance(value, tuple) and all(isinstance(s, str) for s in value):
        return value
    return fallback


@dataclass(frozen=True)
class Routing:
    """The gate's routing rule plus the suffixes it recognises."""

    picker: Callable[[Path, str], list[str]]
    py_suffixes: tuple[str, ...]
    md_suffixes: tuple[str, ...]

    @property
    def routed_suffixes(self) -> frozenset[str]:
        """Return every suffix any archetype can be routed to."""
        return frozenset(self.py_suffixes) | frozenset(self.md_suffixes)

    def modules_for(self, path: Path, source: str) -> dict[str, str]:
        """Return {archetype module: provenance} for one path.

        The gate's own rule supplies the set.
        """
        modules: dict[str, str] = {}
        for module in self.picker(path, source):
            if module in ARCHETYPE_CLASSES:
                modules[module] = FROM_GATE
        return modules


def load_routing() -> Routing:
    """Load the gate's routing rule, or raise RoutingUnavailable."""
    gate = load_gate()
    return Routing(
        picker=gate_router(gate),
        py_suffixes=_gate_suffixes(gate, "_PY_SUFFIXES", (".py", ".pyw", ".pyi")),
        md_suffixes=_gate_suffixes(gate, "_MD_SUFFIXES", (".md", ".markdown")),
    )


def decode_text(data: bytes) -> tuple[str, bool]:
    """Return (text, decoded_faithfully) for raw file bytes.

    A UTF-16 file whose bytes really contain `# noqa` decodes to mojibake
    under a lossy UTF-8 read, tokenizing fails, and a naive line scan
    then finds NOTHING — an UNDER-count, which is the unsafe direction.
    So the encoding is chosen by BOM first, strict UTF-8 second, and
    latin-1 only as a last resort that cannot fail. The third case is
    reported, so a count is never read without knowing how it was taken.
    """
    for bom, encoding in (
        (b"\xef\xbb\xbf", "utf-8-sig"),
        (b"\xff\xfe\x00\x00", "utf-32"),
        (b"\x00\x00\xfe\xff", "utf-32"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
    ):
        if data.startswith(bom):
            try:
                return data.decode(encoding), True
            except (UnicodeDecodeError, LookupError):
                break
    try:
        return data.decode("utf-8"), True
    except UnicodeDecodeError:
        return data.decode("latin-1"), False


def eol_signature(data: bytes) -> tuple[str, dict[str, int]]:
    """Return the line-ending kind of raw bytes, and the raw counts.

    Read from bytes, so nothing in the reading path can translate an
    ending before it is measured.

    NONE means the file holds no line terminator at all, which is an
    ABSENCE OF EVIDENCE, not a kind — a one-line file that gains its
    required trailing newline has not flipped anything, and refusing
    that would tell a unit to undo a fix its linter demanded.

    MIXED carries its DOMINANT kind, as `MIXED(CRLF)`. Plain "MIXED"
    would be a bucket, not a kind: a mostly-CRLF file rewritten as
    mostly-LF stays inside a bare MIXED bucket with every single line
    changed. The editors that cause MODE 4 are exactly what create mixed
    files, so the bucket would open precisely when the failure happens.
    """
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    cr = data.count(b"\r") - crlf
    counts = {"crlf": crlf, "lf": lf, "cr": cr}
    present = [
        (name, count)
        for name, count in (("CRLF", crlf), ("LF", lf), ("CR", cr))
        if count > 0
    ]
    if not present:
        return DETERMINED_UNKNOWN, counts
    if len(present) == 1:
        return present[0][0], counts
    dominant = max(present, key=lambda item: (item[1], item[0]))[0]
    return f"MIXED({dominant})", counts


def is_determined(kind: str) -> bool:
    """Report whether a line-ending kind is evidence rather than absence."""
    return kind != DETERMINED_UNKNOWN


def _normalise_directive(text: str) -> str:
    """Return a directive spelling folded to one canonical key."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _pragma_in_comment(comment: str) -> list[str]:
    """Return the directives a single comment token actually declares.

    A directive is a PRAGMA, and a pragma sits at the START of a
    `#`-delimited segment: `# noqa: F401`, or the second segment of
    `# reason  # noqa: F401`. This is the same shape ruff itself
    recognises.

    Anchoring matters. Scanning the whole comment for the word counted
    `# we did NOT add a noqa here, the finding is real` as a suppression
    — so documenting a refusal to suppress tripped the gate — and
    counted this module's own explanatory comments against itself.
    """
    found: list[str] = []
    for segment in comment.split("#")[1:]:
        match = DIRECTIVE_RE.match(segment.lstrip())
        if match is not None:
            found.append(_normalise_directive(match.group(0)))
    return found


def _pragma_in_line(line: str) -> list[str]:
    """Return the directives one line of a non-Python file declares.

    Anchored to a comment opener (`#`, `//`, `--`, `<!--`, `/*`) for the
    same reason as the Python path. This CANNOT tell a comment from a
    string literal or a fenced code block, so it over-counts; it never
    under-counts a real pragma, because a real pragma always follows an
    opener. The method is recorded in the pin and printed.
    """
    found: list[str] = []
    for marker in MARKER_RE.finditer(line):
        match = DIRECTIVE_RE.match(line[marker.end() :])
        if match is not None:
            found.append(_normalise_directive(match.group(0)))
    return found


def _tally(spellings: Iterable[str]) -> tuple[int, dict[str, int]]:
    """Return (total, by spelling) for a stream of directive spellings."""
    by_kind: dict[str, int] = {}
    total = 0
    for key in spellings:
        by_kind[key] = by_kind.get(key, 0) + 1
        total += 1
    return total, by_kind


def count_directives(
    path: Path,
    data: bytes,
    py_suffixes: tuple[str, ...],
) -> tuple[int, dict[str, int], str]:
    """Return (total, by spelling, scan method) for one file.

    For Python the file is tokenized and only COMMENT tokens are read,
    so the same words inside a string literal or a docstring are not
    counted — including this module's own docstring, which names every
    directive it looks for.

    For anything else, and for Python this module cannot tokenize, the
    fallback is the marker-anchored line scan described in
    `_pragma_in_line`, which over-counts rather than under-counts.
    Over-counting is the safe direction here: baseline and check use the
    same method on the same file, and an inflated pin can only make a
    rise harder to trigger, never easier to miss.
    """
    text, faithful = decode_text(data)
    method = SCAN_MARKERS if not faithful else SCAN_TOKENIZE
    if path.suffix.lower() not in py_suffixes or not faithful:
        total, kinds = _tally(
            key for line in text.splitlines() for key in _pragma_in_line(line)
        )
        return total, kinds, SCAN_MARKERS
    comments: list[str] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                comments.append(token.string)
    except (tokenize.TokenError, SyntaxError, IndentationError, ValueError):
        total, kinds = _tally(
            key for line in text.splitlines() for key in _pragma_in_line(line)
        )
        return total, kinds, SCAN_MARKERS
    total, kinds = _tally(
        key for comment in comments for key in _pragma_in_comment(comment)
    )
    return total, kinds, method


@dataclass
class ArchetypeResult:
    """One archetype's own verdict on one file."""

    module: str
    provenance: str
    passed: bool
    by_severity: dict[str, int]
    errors: list[str]
    degraded: list[str]
    ran: bool
    failure: str = ""

    @property
    def high(self) -> int:
        """Return the count of critical plus high findings."""
        return sum(self.by_severity.get(name, 0) for name in SEVERE)

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serialisable view of this verdict."""
        return {
            "module": self.module,
            "provenance": self.provenance,
            "passed": self.passed,
            "high": self.high,
            "by_severity": self.by_severity,
            "errors": self.errors,
            "degraded": self.degraded,
            "ran": self.ran,
            "failure": self.failure,
        }


def _recount(findings: object) -> dict[str, int]:
    """Count findings by severity, straight from the findings list.

    Never reads `by_severity`. ta_archetype does not publish that key,
    and a missing key read as an empty dict scores a failing file as
    clean — `archetype_gate._summarize` does exactly that and prints
    "0 findings" one line above "by tool: ruff=81".
    """
    counts: dict[str, int] = {}
    if not isinstance(findings, list):
        return counts
    for item in findings:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "unknown")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def _degraded_tools(availability: object) -> list[str]:
    """Return the tools an archetype could not run."""
    if not isinstance(availability, dict):
        return []
    return sorted(
        str(name)
        for name, state in availability.items()
        if not str(state).startswith("ok")
    )


def run_archetype(
    module_name: str,
    provenance: str,
    target: Path,
) -> ArchetypeResult:
    """Run one archetype on one file and read ITS verdict.

    The archetype is imported and its `review()` called directly, so the
    `passed` recorded here is the archetype's own property read through
    its published `to_dict()` contract. Nothing is recomputed and no
    verdict is overridden.

    A failure to run is NOT a pass. It is recorded with `ran: False` and
    treated as red by the caller, because work the harness did not
    evaluate is not verified work. `SystemExit` is caught alongside
    `Exception` for the same reason: an archetype that calls `sys.exit`
    mid-review otherwise ends this process with no diagnostic at all.
    `KeyboardInterrupt` is deliberately NOT caught — an operator
    interrupt must not be laundered into a verdict.
    """
    unusable = ArchetypeResult(
        module=module_name,
        provenance=provenance,
        passed=False,
        by_severity={},
        errors=[],
        degraded=[],
        ran=False,
    )
    class_name = ARCHETYPE_CLASSES.get(module_name)
    if class_name is None:
        unusable.failure = f"no known entry class for {module_name}"
        return unusable
    try:
        module = importlib.import_module(module_name)
        archetype = getattr(module, class_name)()
        report = archetype.review(Path(target))
        payload = report.to_dict()
    except SystemExit as exc:
        unusable.failure = f"called sys.exit({exc.code}) during review"
        return unusable
    except Exception as exc:
        unusable.failure = f"{type(exc).__name__}: {exc}"
        return unusable
    if not isinstance(payload, dict):
        unusable.failure = f"{module_name} returned a non-object report"
        return unusable
    verdict = payload.get("passed")
    if not isinstance(verdict, bool):
        unusable.failure = (
            f"{module_name} reported passed={verdict!r}, which is not a "
            "bool; a truthy value is not a verdict"
        )
        return unusable
    raw_errors = payload.get("errors")
    return ArchetypeResult(
        module=module_name,
        provenance=provenance,
        passed=verdict,
        by_severity=_recount(payload.get("findings")),
        errors=[str(e) for e in raw_errors] if isinstance(raw_errors, list) else [],
        degraded=_degraded_tools(payload.get("tool_availability")),
        ran=True,
    )


@dataclass
class Entry:
    """Everything measured about one file in a touch set."""

    rel: str
    sha256: str
    size: int
    eol: str
    eol_counts: dict[str, int]
    directives_total: int
    directives_by_kind: dict[str, int]
    directive_scan: str
    is_code: bool = False
    routed: tuple[str, ...] = ()
    archetypes: dict[str, ArchetypeResult] = field(default_factory=dict)

    @property
    def nothing_measured(self) -> bool:
        """Report whether an archetype applied but none of them ran.

        This is MODE 3 one layer up: a filter that removes every
        applicable archetype leaves a file ungraded while every
        individual check it performs still says "fine".
        """
        return bool(self.routed) and not self.archetypes

    def red_reasons(self) -> list[str]:
        """Return every reason this file is not clean, as quotable text."""
        reasons: list[str] = []
        if self.nothing_measured:
            reasons.append(
                f"NOTHING MEASURED  {self.rel}: {len(self.routed)} archetype(s) "
                f"route to this path ({', '.join(sorted(self.routed))}) and "
                "none of them ran. A filter that grades nothing is not a pass.",
            )
        for module in sorted(self.archetypes):
            result = self.archetypes[module]
            if not result.ran:
                reasons.append(
                    f"{self.rel}: {module} COULD NOT RUN — {result.failure}. "
                    "A verdict the harness did not produce is not a pass.",
                )
            elif not result.passed:
                reasons.append(
                    f"{self.rel}: {module} passed=False "
                    f"({result.high} high/critical).",
                )
        return reasons

    def degraded_union(self) -> set[str]:
        """Return every tool any archetype on this file could not run."""
        return {tool for r in self.archetypes.values() for tool in r.degraded}

    def to_json(self) -> dict[str, object]:
        """Return a JSON-serialisable view of this entry."""
        return {
            "path": self.rel,
            "sha256": self.sha256,
            "size": self.size,
            "eol": self.eol,
            "eol_counts": self.eol_counts,
            "directives": {
                "total": self.directives_total,
                "by_kind": self.directives_by_kind,
                "scan": self.directive_scan,
                "gated": self.is_code,
            },
            "is_code": self.is_code,
            "routed": sorted(self.routed),
            "archetypes": {
                module: result.to_json()
                for module, result in sorted(self.archetypes.items())
            },
        }


def _submit_archetypes(
    target: Path,
    modules: dict[str, str],
    jobs: int,
    timeout: int,
) -> dict[str, ArchetypeResult]:
    """Run each archetype concurrently and collect its own verdict.

    The pool is shut down with `wait=False` so a wedged archetype cannot
    block the return. It is still running, which is why a timeout is
    raised out to `main` for a hard exit rather than returned.
    """
    pool = ThreadPoolExecutor(max_workers=max(1, jobs))
    try:
        futures = {
            module: pool.submit(run_archetype, module, provenance, target)
            for module, provenance in sorted(modules.items())
        }
        results: dict[str, ArchetypeResult] = {}
        for module, future in futures.items():
            try:
                results[module] = future.result(timeout=timeout)
            except TimeoutError:
                message = (
                    f"{module} exceeded {timeout}s on {target}. An archetype "
                    "runs in a thread and a thread cannot be killed, so this "
                    "process exits now rather than hanging with no verdict."
                )
                raise ArchetypeTimeout(message) from None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return results


def measure(
    root: Path,
    rel: str,
    routing: Routing,
    only: tuple[str, ...],
    jobs: int,
    timeout: int,
) -> Entry:
    """Measure one existing file completely.

    The caller has already proved the file exists. This never checks
    again and never invents a verdict for a path it cannot read.
    """
    target = root / rel
    data = target.read_bytes()
    eol, eol_counts = eol_signature(data)
    total, by_kind, scan = count_directives(target, data, routing.py_suffixes)
    source, _ = decode_text(data)
    routed = routing.modules_for(target, source)
    entry = Entry(
        rel=rel,
        sha256=sha256_bytes(data),
        size=len(data),
        eol=eol,
        eol_counts=eol_counts,
        directives_total=total,
        directives_by_kind=by_kind,
        directive_scan=scan,
        is_code=target.suffix.lower() in routing.py_suffixes,
        routed=tuple(sorted(routed)),
    )
    modules = {m: p for m, p in routed.items() if not only or m in only}
    if modules:
        entry.archetypes = _submit_archetypes(target, modules, jobs, timeout)
    return entry


@dataclass(frozen=True)
class PathProblem:
    """One reason a requested path cannot enter a touch set."""

    raw: str
    kind: str
    detail: str


def _typed_rel(root: Path, raw: str) -> str | None:
    """Return `raw` relative to `root` AS TYPED, without canonicalising.

    `Path.resolve()` returns the TRUE on-disk case on Windows, so the
    resolved path silently corrects `GREEN.PY` to `green.py` and a check
    made after resolving can never fire. The spelling the caller typed
    has to be kept back for the comparison.
    """
    typed = Path(raw)
    if typed.is_absolute():
        try:
            return typed.relative_to(root).as_posix()
        except ValueError:
            return None
    text = typed.as_posix()
    while text.startswith("./"):
        text = text[2:]
    return text


def resolve_paths(
    root: Path,
    raw_paths: Iterable[str],
) -> tuple[list[str], list[PathProblem]]:
    """Return the usable relative paths and every problem found.

    An ABSOLUTE path outside the root used to be pinned as-is. Because
    `Path(root) / "C:/live/x.py"` discards the left operand entirely,
    `check --against <island>` then re-measured the ORIGINAL file and
    reported OK while the island copy went red, ungraded. Every path is
    now required to land inside the root.
    """
    rels: list[str] = []
    problems: list[PathProblem] = []
    root_resolved = root.resolve()
    for raw in raw_paths:
        candidate = Path(raw)
        combined = candidate if candidate.is_absolute() else root / candidate
        try:
            rel = combined.resolve().relative_to(root_resolved).as_posix()
        except (OSError, ValueError):
            problems.append(
                PathProblem(
                    raw,
                    "OUTSIDE-ROOT",
                    f"resolves outside {root_resolved}; a touch set may only "
                    "name files inside the tree being measured",
                )
            )
            continue
        target = root / rel
        if target.is_dir():
            problems.append(
                PathProblem(
                    raw,
                    "NOT-A-FILE",
                    "is a directory, not a file",
                )
            )
            continue
        if not target.is_file():
            problems.append(PathProblem(raw, "MISSING", "no such file"))
            continue
        typed = _typed_rel(root, raw)
        if typed is not None and typed != rel and typed.lower() == rel.lower():
            problems.append(
                PathProblem(
                    raw,
                    "CASE-MISMATCH",
                    f"the file on disk is {rel}. This filesystem ignores case, so "
                    "the same command names nothing at all on a case-sensitive "
                    "host — and the install manifest includes a Mac Mini. "
                    "Refusing rather than silently correcting the spelling.",
                )
            )
            continue
        if rel not in rels:
            rels.append(rel)
    return rels, problems


def iter_routed_files(root: Path, suffixes: frozenset[str]) -> Iterator[Path]:
    """Yield every file under `root` that an archetype could route to.

    Skips caches, virtualenvs and any nested island, matching the same
    exclusions `tools/island.py` uses when it walks a tree.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in SKIP_DIR_NAMES:
                    continue
                if (entry / ISLAND_MANIFEST).is_file():
                    continue
                stack.append(entry)
            elif entry.suffix.lower() in suffixes:
                yield entry


def directory_eol_majority(
    directory: Path,
    suffix: str,
    exclude: set[str],
) -> tuple[str, dict[str, int]]:
    """Return the dominant line-ending kind for a directory, and the tally.

    The repo has no repo-wide ending, so a NEW file has no pinned kind to
    preserve. The measured rule is that it follows its own directory's
    majority — tools/*.py is LF 7 / CRLF 1, so a new tool takes LF.
    Returns an empty kind when there is nothing to measure against.
    """
    counts: dict[str, int] = {}
    try:
        entries = sorted(directory.iterdir())
    except OSError:
        return "", counts
    for entry in entries:
        if not entry.is_file() or entry.suffix.lower() != suffix:
            continue
        if entry.name in exclude:
            continue
        try:
            kind, _ = eol_signature(entry.read_bytes())
        except OSError:
            continue
        if not is_determined(kind):
            continue
        counts[kind] = counts.get(kind, 0) + 1
    if not counts:
        return "", counts
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0], counts


def say_reduced(only: tuple[str, ...]) -> None:
    """Print the reduced-coverage banner whenever `--only` narrowed the set.

    Printed on the strength of `only` alone. Keying it on the pin's
    `complete` flag let a pin claiming `complete: true` alongside a
    narrowing `only` list suppress its own warning.
    """
    if not only:
        return
    skipped = sorted(set(ARCHETYPE_CLASSES) - set(only))
    _say("")
    _say("REDUCED COVERAGE: --only narrowed the archetype set.")
    _say(f"  measured: {', '.join(sorted(only))}")
    _say(f"  NEVER MEASURED: {', '.join(skipped)}")
    _say("  This pin is not complete. The default run is.")


def pin_digest(payload: dict[str, object]) -> str:
    """Return the SHA-256 of a pin's canonical body, ignoring `digest`.

    This is an INTEGRITY check, not a signature. It catches a truncated,
    corrupted or casually hand-edited pin — the routes by which a pin
    was made to report `entries: []`, or a directive total of 999, or a
    `complete: true` beside a narrowing `only`, and still read as clean.
    Anyone who can edit the pin can recompute the digest; this is not a
    defence against a determined forger and is not offered as one.
    """
    body = {k: v for k, v in sorted(payload.items()) if k != "digest"}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_pin(
    pin_path: Path,
    root: Path,
    entries: list[Entry],
    only: tuple[str, ...],
) -> None:
    """Write the machine-readable pin. The only file this module writes."""
    payload: dict[str, object] = {
        "tool": "tools.touchset",
        "pin_version": PIN_VERSION,
        "created": _now(),
        "root": str(root),
        "git_head": git_head(root),
        "routing_rule": ROUTING_CITATION,
        "directive_set": DIRECTIVE_SET_LABEL,
        "complete": not only,
        "only": sorted(only),
        "entries": [entry.to_json() for entry in entries],
    }
    payload["digest"] = pin_digest(payload)
    pin_path.parent.mkdir(parents=True, exist_ok=True)
    pin_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_pin(pin_path: Path) -> tuple[dict[str, object] | None, str]:
    """Return (pin, refusal). Exactly one of the two is meaningful.

    Every structural guarantee `check` later relies on is established
    here, because each one is a way of concluding "fine" having compared
    nothing.
    """
    try:
        data = json.loads(pin_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"{pin_path} is not readable JSON: {exc}"
    if not isinstance(data, dict):
        return None, f"{pin_path} is not a touchset pin object"
    if data.get("pin_version") != PIN_VERSION:
        return None, (
            f"{pin_path} is pin_version {data.get('pin_version')!r}; this "
            f"module writes and reads {PIN_VERSION}. An older pin lacks the "
            "content hashes and degraded-tool records this comparison needs, "
            "so it cannot be compared like-for-like. Re-run baseline."
        )
    recorded = data.get("digest")
    if not isinstance(recorded, str) or recorded != pin_digest(data):
        return None, (
            f"{pin_path} fails its own integrity digest. It has been "
            "truncated, corrupted or edited since it was written, so what it "
            "records is not what was measured."
        )
    entries = data.get("entries")
    if not isinstance(entries, list):
        return None, f"{pin_path} carries no entries list"
    if not entries:
        return None, (
            f"{pin_path} pins ZERO files. Comparing an island against an "
            "empty pin measures nothing and would report OK, which is the "
            "exact failure this module exists to remove."
        )
    only = data.get("only")
    only_list = [str(m) for m in only] if isinstance(only, list) else []
    if bool(data.get("complete", True)) is bool(only_list):
        return None, (
            f"{pin_path} is self-inconsistent: complete="
            f"{data.get('complete')!r} beside only={only_list!r}. A complete "
            "pin narrows nothing and a narrowed pin is not complete. A pin "
            "that claims both suppresses its own reduced-coverage warning."
        )
    return data, ""


def pin_degraded_union(entries: list[dict[str, object]]) -> set[str]:
    """Return every tool that was already unavailable when the pin was made.

    Used as the baseline for a file or an archetype the pin has no
    per-module record for, so a tool that was missing on the whole
    machine at baseline is not blamed on the unit.
    """
    tools: set[str] = set()
    for entry in entries:
        archetypes = entry.get("archetypes")
        if not isinstance(archetypes, dict):
            continue
        for record in archetypes.values():
            if not isinstance(record, dict):
                continue
            degraded = record.get("degraded")
            if isinstance(degraded, list):
                tools.update(str(t) for t in degraded)
    return tools


def _say_entry(entry: Entry, prefix: str = "") -> None:
    """Print the one-file summary line and its per-archetype detail."""
    _say(f"  {prefix}{entry.rel}")
    _say(
        f"      line endings {entry.eol}   "
        f"forbidden directives {entry.directives_total} "
        f"({entry.directive_scan})",
    )
    if entry.directives_by_kind:
        spelled = ", ".join(
            f"{kind}={count}"
            for kind, count in sorted(entry.directives_by_kind.items())
        )
        gated = "" if entry.is_code else "  RECORDED, NOT GATED (not code)"
        _say(f"      directives: {spelled}{gated}")
    if not entry.routed:
        _say("      no archetype routes to this path — NOT GRADED")
        _say("      (line endings and directives are still compared)")
        return
    if not entry.archetypes:
        _say(f"      routed to {', '.join(sorted(entry.routed))} — NONE RAN")
        return
    for module in sorted(entry.archetypes):
        result = entry.archetypes[module]
        if not result.ran:
            _say(f"      {module}: DID NOT RUN — {result.failure}")
            continue
        state = "passed=True " if result.passed else "passed=FALSE"
        _say(f"      {module}: {state}  high={result.high}")
        if result.degraded:
            _say(f"          reduced tools: {', '.join(result.degraded)}")


def _say_counts(entries: list[Entry]) -> None:
    """Print how many files were graded and how many were not.

    "All N file(s) green" was printed over files no archetype had
    graded. Green is a verdict word and no archetype had produced one.
    """
    graded = sum(1 for e in entries if e.archetypes)
    ungraded = len(entries) - graded
    _say(f"{graded} file(s) graded by an archetype, {ungraded} not graded.")
    if ungraded:
        _say("  A file no archetype routes to is still line-ending and")
        _say("  directive protected, but it carries NO archetype verdict.")


def _refuse_paths(problems: list[PathProblem]) -> int:
    """Print the unusable-path refusal and return its exit code."""
    _say(f"REFUSED: {len(problems)} path(s) cannot enter a touch set.")
    _say("")
    for problem in problems:
        _say(f"  {problem.kind}  {problem.raw}")
        _say(f"      {problem.detail}")
    _say("")
    _say("Measured 2026-08-13: coding, ta, watchdog, gui and docs all")
    _say("exit 0 AND report passed=true on a path that does not exist.")
    _say("A verification that scanned nothing is not a pass, so this")
    _say("refuses before any archetype runs. Fix the path and re-run.")
    _say("Nothing was measured and no pin was written.")
    return 2


def baseline(
    root: Path,
    raw_paths: list[str],
    pin_path: Path,
    only: tuple[str, ...],
    jobs: int,
    timeout: int,
) -> int:
    """Measure a touch set, refuse a bad one, and pin a good one."""
    try:
        routing = load_routing()
    except RoutingUnavailable as exc:
        _say(f"REFUSED: {exc}")
        _say("This module reuses the gate's routing rather than copying it,")
        _say("so with no rule to reuse it measures nothing. Nothing written.")
        return 2

    rels, problems = resolve_paths(root, raw_paths)
    if problems:
        return _refuse_paths(problems)

    _say(f"Touch set: {len(rels)} file(s) under {root}")
    _say(f"Routing rule: {ROUTING_CITATION}")
    _say(f"Directive set: {DIRECTIVE_SET_LABEL}")
    say_reduced(only)
    _say("")

    entries = [measure(root, rel, routing, only, jobs, timeout) for rel in rels]
    for entry in entries:
        _say_entry(entry)

    reasons = [reason for entry in entries for reason in entry.red_reasons()]
    if reasons:
        _say("")
        _say(f"REFUSED: {len(reasons)} archetype verdict(s) are already red")
        _say("on the UNMODIFIED tree, before this unit edits anything.")
        _say("")
        for reason in reasons:
            _say(f"  {reason}")
        _say("")
        _say("A unit cannot be greener than the files it lands in. Either")
        _say("DROP the file from the touch set, or fix the red first as its")
        _say("own unit. No pin was written.")
        return 1

    write_pin(pin_path, root, entries, only)
    _say("")
    _say_counts(entries)
    pre_existing = sum(e.directives_total for e in entries)
    if pre_existing:
        _say("")
        _say(f"NOTE: {pre_existing} forbidden directive(s) already present.")
        _say("  Those are recorded as pre-existing and are not this unit's")
        _say("  to clear. This is only true if the baseline was taken BEFORE")
        _say("  the first edit — nothing here can prove that it was.")
    _say("")
    _say(f"Pin written: {pin_path}")
    return 0


def _pinned_directives(pinned: dict[str, object]) -> tuple[int, dict[str, int]]:
    """Return the directive total and per-spelling counts a pin recorded."""
    recorded = pinned.get("directives")
    if not isinstance(recorded, dict):
        return 0, {}
    raw_total = recorded.get("total")
    total = raw_total if isinstance(raw_total, int) else 0
    raw_kinds = recorded.get("by_kind")
    kinds = (
        {str(k): v for k, v in raw_kinds.items() if isinstance(v, int)}
        if isinstance(raw_kinds, dict)
        else {}
    )
    return total, kinds


def _compare_directives(
    rel: str,
    pinned: dict[str, object],
    entry: Entry,
) -> list[str]:
    """Return a failure line if any directive spelling rose.

    Compared PER SPELLING, not on the total alone. Dropping one
    `# noqa: F401` while adding one `# pylint: disable=invalid-name`
    holds the total at 1 and silences a different checker.

    GATED ON CODE FILES ONLY. A directive silences a checker; ruff,
    mypy, pyright, bandit, vulture, semgrep and pylint read Python, not
    Markdown. A `# noqa` written in prose in a `.md` file suppresses
    nothing, so refusing it is signal about the writing and none about
    the code. Counts are still MEASURED and recorded for every file —
    only the refusal is limited.

    Found by running this tool against its own documentation: the
    sentence describing the MODE 2 incident quotes `# noqa: BLE001`, and
    a markdown heading marker made the quote read as a pragma.
    """
    if not entry.is_code:
        return []
    before, before_kinds = _pinned_directives(pinned)
    risen = sorted(
        f"{kind} {before_kinds.get(kind, 0)} -> {count}"
        for kind, count in entry.directives_by_kind.items()
        if count > before_kinds.get(kind, 0)
    )
    if not risen:
        return []
    return [
        f"SUPPRESSION ADDED  {rel}: forbidden directives {before} -> "
        f"{entry.directives_total} ({'; '.join(risen)}). A pre-existing count "
        "is not this unit's to clear; an INCREASE is always this unit's doing.",
    ]


def _compare_eol(rel: str, pinned: dict[str, object], entry: Entry) -> list[str]:
    """Return a failure line if the line-ending kind flipped.

    Fires only when BOTH sides are determined kinds. A file with no
    terminator at all measures NONE, which is an absence of evidence:
    a one-line file that gains its required trailing newline has not
    flipped anything, and refusing it would tell a unit to undo a fix
    its linter demanded.
    """
    before = str(pinned.get("eol") or DETERMINED_UNKNOWN)
    if before == entry.eol:
        return []
    if not is_determined(before) or not is_determined(entry.eol):
        return []
    return [
        f"LINE ENDING FLIPPED  {rel}: {before} -> {entry.eol}. The repo has "
        "no repo-wide ending, so each file keeps its own kind. Rewrite the "
        f'file as {before} — read AND write with newline="".',
    ]


def _pinned_degraded(pinned: dict[str, object]) -> dict[str, set[str]]:
    """Return {archetype module: tools it could not run} from a pin entry."""
    archetypes = pinned.get("archetypes")
    if not isinstance(archetypes, dict):
        return {}
    out: dict[str, set[str]] = {}
    for module, record in archetypes.items():
        if not isinstance(record, dict):
            continue
        degraded = record.get("degraded")
        out[str(module)] = (
            {str(t) for t in degraded} if isinstance(degraded, list) else set()
        )
    return out


def _compare_degraded(
    rel: str,
    pinned: dict[str, object],
    entry: Entry,
    machine: set[str],
) -> list[str]:
    """Return a failure line for every tool that stopped running.

    Measured 2026-08-13 in a bare interpreter: the REAL CodingArchetype
    on the harness's own `known_bad.py` fixture — the file that must be
    red — reports `passed: True` with 0 findings when ruff, mypy, bandit
    and vulture are all absent. So `passed=True` can mean "nothing was
    scanned", and forwarding it unchecked reproduces MODE 3 one layer
    above where this module places its defence. The pin already recorded
    this; not comparing it was the gap.
    """
    per_module = _pinned_degraded(pinned)
    lines: list[str] = []
    for module in sorted(entry.archetypes):
        before = per_module.get(module, machine)
        added = sorted(set(entry.archetypes[module].degraded) - before)
        if added:
            lines.append(
                f"TOOL STOPPED RUNNING  {rel}: {module} could not run "
                f"{', '.join(added)}, which it ran at baseline. An archetype "
                "reports passed=True when its tools are absent, so this "
                "verdict is a scan that did not happen.",
            )
    return lines


def _new_file_reasons(
    entry: Entry,
    island: Path,
    exclude: set[str],
) -> list[str]:
    """Return every reason a never-pinned file may not land.

    A new file has no pinned counterpart, so the comparison is against
    the only defensible baselines: zero suppressions, and its own
    directory's measured line-ending majority.
    """
    reasons = list(entry.red_reasons())
    if entry.is_code and entry.directives_total:
        spelled = ", ".join(
            f"{k}={v}" for k, v in sorted(entry.directives_by_kind.items())
        )
        reasons.append(
            f"SUPPRESSION IN A NEW FILE  {entry.rel}: "
            f"{entry.directives_total} forbidden directive(s) ({spelled}). A "
            "file the pin never saw starts at zero, so every one of these is "
            "this unit's doing. This is the MODE 2 incident exactly: the "
            "`# noqa: BLE001` landed in a NEW test file.",
        )
    if not is_determined(entry.eol):
        return reasons
    directory = (island / entry.rel).parent
    suffix = Path(entry.rel).suffix.lower()
    majority, counts = directory_eol_majority(directory, suffix, exclude)
    if majority and majority != entry.eol:
        tally = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        reasons.append(
            f"NEW FILE LINE ENDING  {entry.rel}: {entry.eol}, but its "
            f"directory measures {tally} for *{suffix}. A new file follows "
            "its directory's measured majority; the repo has no repo-wide "
            "ending to fall back on.",
        )
    return reasons


def _find_new_files(
    island: Path,
    baseline_root: Path,
    pinned: set[str],
    routing: Routing,
) -> list[str]:
    """Return every routed file on the island the pin and baseline lack."""
    found: list[str] = []
    for path in iter_routed_files(island, routing.routed_suffixes):
        rel = path.relative_to(island).as_posix()
        if rel in pinned or (baseline_root / rel).exists():
            continue
        found.append(rel)
    return sorted(found)


def _sweep_new_files(
    island: Path,
    baseline_root: Path,
    pinned: set[str],
    routing: Routing,
    machine: set[str],
    jobs: int,
    timeout: int,
    limit: int,
) -> tuple[list[str], list[str]]:
    """Measure files the pin never saw. Returns (failures, notes).

    MODE 2 happened in a file that did not exist when the touch set was
    chosen, so a pin-scoped comparison could never have caught it: the
    file cannot be pinned before it exists, and iterating the pin never
    reaches it afterwards. Every guarantee this module offers — archetype
    verdict, suppression count, line-ending kind — was blind to a new
    file until this sweep existed.
    """
    rels = _find_new_files(island, baseline_root, pinned, routing)
    if not rels:
        return [], []
    if len(rels) > limit:
        return [
            f"TOO MANY NEW FILES  {len(rels)} routed file(s) on {island} are "
            f"absent from both the pin and {baseline_root}, over the limit of "
            f"{limit}. Refusing rather than measuring an unbounded set. "
            "Narrow the island, or raise --new-file-limit deliberately.",
        ], []
    exclude = {Path(rel).name for rel in rels}
    notes = [
        f"{len(rels)} file(s) on the island that the pin never saw, measured "
        f"as this unit's own work: {', '.join(rels)}",
    ]
    failures: list[str] = []
    for rel in rels:
        entry = measure(island, rel, routing, (), jobs, timeout)
        _say_entry(entry, prefix="NEW  ")
        failures.extend(_new_file_reasons(entry, island, exclude))
        failures.extend(_compare_degraded(rel, {}, entry, machine))
    return failures, notes


@dataclass
class CheckOptions:
    """Everything `check` needs beyond the pin and the island."""

    jobs: int = DEFAULT_JOBS
    timeout: int = DEFAULT_TIMEOUT
    new_file_limit: int = DEFAULT_NEW_FILE_LIMIT
    accept_reduced: bool = False
    baseline_root: Path | None = None


def _check_one_pinned(
    pinned: dict[str, object],
    against: Path,
    routing: Routing,
    only: tuple[str, ...],
    machine: set[str],
    options: CheckOptions,
) -> tuple[list[str], list[str], bool]:
    """Compare one pinned file. Returns (failures, notes, unchanged)."""
    rel = str(pinned.get("path") or "")
    if not rel:
        return ["PIN DAMAGED  an entry carries no path."], [], False
    if (against / rel).is_dir():
        return (
            [
                f"PATH REPLACED  {rel}: pinned as a file, but {against / rel} is "
                "now a directory. Nothing can be graded, and every archetype "
                "returns 0 on a path it cannot read.",
            ],
            [],
            False,
        )
    if not (against / rel).is_file():
        return (
            [
                f"PATH VANISHED  {rel}: pinned, but absent from {against}. Every "
                "archetype exits 0 on a path that does not exist, so this is "
                "refused before any verdict is read.",
            ],
            [],
            False,
        )
    entry = measure(against, rel, routing, only, options.jobs, options.timeout)
    _say_entry(entry)
    failures = list(entry.red_reasons())
    failures.extend(_compare_directives(rel, pinned, entry))
    failures.extend(_compare_eol(rel, pinned, entry))
    failures.extend(_compare_degraded(rel, pinned, entry, machine))
    notes: list[str] = []
    before_eol = str(pinned.get("eol") or DETERMINED_UNKNOWN)
    if before_eol != entry.eol:
        notes.append(
            f"{rel}: line endings {before_eol} -> {entry.eol}. One side has "
            "no terminator at all, so this is not read as a flip.",
        )
    return failures, notes, str(pinned.get("sha256") or "") == entry.sha256


def _resolve_baseline_root(
    pin: dict[str, object],
    options: CheckOptions,
) -> tuple[Path | None, str]:
    """Return the tree the pin was taken from, or a refusal."""
    if options.baseline_root is not None:
        root = options.baseline_root
    else:
        raw = pin.get("root")
        if not isinstance(raw, str) or not raw:
            return (
                None,
                "the pin records no root, so a new file cannot be told from an old one",
            )
        root = Path(raw)
    if not root.is_dir():
        return None, (
            f"the pin's baseline root {root} is not available, so a file the "
            "pin never saw cannot be told from a file that was simply not in "
            "the touch set. Pass --baseline-root, or re-run baseline. This "
            "refuses rather than skipping the sweep, because skipping it is "
            "how the MODE 2 suppression got through."
        )
    return root, ""


def _check_setup(
    pin_path: Path,
    against: Path,
    options: CheckOptions,
) -> tuple[dict[str, object], Routing, Path] | int:
    """Validate everything `check` needs, or return an exit code."""
    pin, refusal = load_pin(pin_path)
    if pin is None:
        _say(f"REFUSED: {refusal}")
        _say("Comparing against an unusable pin would compare against zero,")
        _say("which is the mistake this command exists to prevent.")
        return 2
    if not against.is_dir():
        _say(f"REFUSED: --against {against} is not a directory.")
        return 2
    try:
        routing = load_routing()
    except RoutingUnavailable as exc:
        _say(f"REFUSED: {exc}")
        return 2
    baseline_root, root_refusal = _resolve_baseline_root(pin, options)
    if baseline_root is None:
        _say(f"REFUSED: {root_refusal}")
        return 2
    return pin, routing, baseline_root


def _say_check_result(
    failures: list[str],
    notes: list[str],
    count: int,
    reduced: bool,
) -> int:
    """Print the verdict of a check run and return its exit code."""
    _say("")
    for note in notes:
        _say(f"NOTE: {note}")
    if notes:
        _say("")
    if failures:
        _say(f"REFUSED: {len(failures)} check(s) fired against the pin.")
        _say("")
        for line in failures:
            _say(f"  {line}")
        _say("")
        _say("Compared to the PIN, never to zero. Nothing was changed.")
        return 1
    if reduced:
        _say("REFUSED: this pin is REDUCED — --only narrowed its archetype")
        _say("set, so a pass here is not a pass over the archetypes that")
        _say("were never run. Re-run baseline without --only, or pass")
        _say("--accept-reduced to record that a partial result was accepted.")
        return 1
    _say(f"OK: {count} file(s) match the pin, and no file the pin never saw")
    _say("    carries a suppression, a red verdict or a foreign line ending.")
    return 0


def check(pin_path: Path, against: Path, options: CheckOptions) -> int:
    """Re-measure a pinned touch set inside an island and compare."""
    prepared = _check_setup(pin_path, against, options)
    if isinstance(prepared, int):
        return prepared
    pin, routing, baseline_root = prepared

    raw_only = pin.get("only")
    only = tuple(str(m) for m in raw_only) if isinstance(raw_only, list) else ()
    entries_raw = pin.get("entries")
    pinned_entries = (
        [e for e in entries_raw if isinstance(e, dict)]
        if isinstance(entries_raw, list)
        else []
    )
    machine = pin_degraded_union(pinned_entries)

    _say(f"Pin:      {pin_path}")
    _say(f"Against:  {against}")
    _say(f"Baseline: {baseline_root}")
    _say(f"Files:    {len(pinned_entries)}")
    say_reduced(only)
    _say("")

    failures: list[str] = []
    notes: list[str] = []
    unchanged = 0
    for pinned in pinned_entries:
        fired, said, same = _check_one_pinned(
            pinned,
            against,
            routing,
            only,
            machine,
            options,
        )
        failures.extend(fired)
        notes.extend(said)
        unchanged += int(same)

    swept, sweep_notes = _sweep_new_files(
        against,
        baseline_root,
        {str(e.get("path") or "") for e in pinned_entries},
        routing,
        machine,
        options.jobs,
        options.timeout,
        options.new_file_limit,
    )
    failures.extend(swept)
    notes.extend(sweep_notes)

    if unchanged == len(pinned_entries) and pinned_entries:
        notes.append(
            f"not one of the {unchanged} pinned file(s) differs from the pin "
            "by a single byte. Either nothing has been edited yet, or this "
            "was pointed at the tree the pin was taken from.",
        )
    return _say_check_result(
        failures,
        notes,
        len(pinned_entries),
        reduced=bool(only) and not options.accept_reduced,
    )


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the two subcommands."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.touchset",
        description=(
            "Baseline a touch set before the first edit, and check an "
            "island against that baseline."
        ),
    )
    subs = parser.add_subparsers(dest="command", required=True)

    base = subs.add_parser(
        "baseline",
        help="measure a touch set and write a pin",
    )
    base.add_argument("paths", nargs="+")
    base.add_argument("--pin", default=DEFAULT_PIN)
    base.add_argument(
        "--root",
        default=None,
        help="tree the paths are relative to (default: the repo)",
    )
    base.add_argument(
        "--only",
        nargs="+",
        default=[],
        choices=sorted(ARCHETYPE_CLASSES),
        help="narrow the archetype set; records reduced coverage in the pin",
    )
    base.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    base.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)

    chk = subs.add_parser("check", help="compare an island against a pin")
    chk.add_argument("--pin", required=True)
    chk.add_argument("--against", required=True)
    chk.add_argument(
        "--baseline-root",
        default=None,
        help="tree the pin was taken from (default: the pin's own record)",
    )
    chk.add_argument("--jobs", type=int, default=DEFAULT_JOBS)
    chk.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    chk.add_argument(
        "--new-file-limit",
        type=int,
        default=DEFAULT_NEW_FILE_LIMIT,
    )
    chk.add_argument(
        "--accept-reduced",
        action="store_true",
        help="accept a --only pin as a pass, recording that it is partial",
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    """Dispatch a parsed command line."""
    if args.command == "baseline":
        root = Path(args.root).resolve() if args.root else REPO
        return baseline(
            root=root,
            raw_paths=list(args.paths),
            pin_path=Path(args.pin),
            only=tuple(args.only),
            jobs=args.jobs,
            timeout=args.timeout,
        )
    return check(
        pin_path=Path(args.pin),
        against=Path(args.against).resolve(),
        options=CheckOptions(
            jobs=args.jobs,
            timeout=args.timeout,
            new_file_limit=args.new_file_limit,
            accept_reduced=args.accept_reduced,
            baseline_root=(
                Path(args.baseline_root).resolve() if args.baseline_root else None
            ),
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return an exit code."""
    args = build_parser().parse_args(argv)
    if REPO not in [Path(p) for p in sys.path]:
        sys.path.insert(0, str(REPO))
    try:
        return _run(args)
    except ArchetypeTimeout as exc:
        _say("")
        _say(f"REFUSED: {exc}")
        _say("Nothing was written. Re-run, or raise --timeout deliberately.")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)


if __name__ == "__main__":
    raise SystemExit(main())
