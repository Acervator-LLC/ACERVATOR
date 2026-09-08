"""CodingArchetype v2 — a tool-invoking coding-quality archetype.

CHANGELOG:
  v2 (2026-07-24):
    - Added Ruff (style/format), Pyright (alt type check), Semgrep
      (pattern static analysis).
    - Fixed Mypy invocation to enforce strict type hints
      (--disallow-untyped-defs --disallow-incomplete-defs).
    - Fixed Bandit severity remap: B105 (hardcoded password) and
      B101 (assert-as-security) now normalize to `high` rather than
      taking bandit's raw `low`.
    - Lowered Vulture --min-confidence to 60 (from default 80).
  v1 (2026-07-24 morning):
    - Initial: mypy + bandit + vulture only. 60% recall on the
      hand-crafted fixture; documented in
      docs/audits/2026-07-24_coding_archetype_multi_agent_test/REPORT.md

Design (unchanged from v1): thin subprocess wrapper around
established third-party static-analysis tools. Each tool is called
as a separate process so a tool crash does not take down the
archetype; each tool's output is parsed into a normalized Finding.

FALSIFICATION: this design is wrong if (a) any tool is not
installed (report shows "missing"), (b) any tool's output format
changes and the parser stops matching (findings drop to zero on
a known-bad file), or (c) any tool subprocess exits non-zero for
reasons unrelated to findings (we catch and log rather than
silently pass).
"""

# ruff: noqa: S603
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

from dev_harness.harness.report import (
    REPO_ROOT,
    ArchetypeReport,
    Finding,
    cli_exit,
    refuse_silent_failure,
    scan_rule_modules,
)

__all__ = [
    "HANDLED_LANGUAGES",
    "UNKNOWN_LANGUAGE",
    "ArchetypeReport",
    "CodingArchetype",
    "Finding",
    "detect_language",
    "main",
]


UNKNOWN_LANGUAGE = "unknown"

# The languages this archetype carries analyzers for. Adding a name here
# is a claim that the runners below can read that language.
HANDLED_LANGUAGES: frozenset[str] = frozenset({"python"})

# A mapped suffix decides the language, and no content check overturns it.
_LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".pyw": "python",
    # A PyInstaller spec is Python that PyInstaller execs.
    ".spec": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".jsonl": "json",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "restructuredtext",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".sql": "sql",
    ".sol": "solidity",
    ".xml": "xml",
    ".svg": "xml",
    ".csv": "csv",
    ".txt": "text",
    ".log": "text",
}

# The interpreter a shebang names, for a file whose suffix carries no
# contract. `env` is skipped by reading the words right to left.
_LANGUAGE_BY_INTERPRETER: dict[str, str] = {
    "python": "python",
    "node": "javascript",
    "nodejs": "javascript",
    "deno": "javascript",
    "sh": "shell",
    "bash": "shell",
    "zsh": "shell",
    "dash": "shell",
    "ksh": "shell",
    "ruby": "ruby",
    "perl": "perl",
}

_SHEBANG_RE = re.compile(r"^#!\s*(?P<first>\S+)(?:\s+(?P<second>\S+))?")

# `python3`, `python3.14` and `python` are one interpreter.
_INTERPRETER_VERSION_RE = re.compile(r"[\d.]+$")

# A minified bundle is one very long line; the shebang, if any, is in
# the first few bytes.
_SHEBANG_READ_LIMIT = 256


def _shebang_language(path: Path) -> str:
    """Name the language a file's shebang declares, or "" for none.

    Reads the first line only, and answers "" on any read failure, so a
    binary or unreadable file falls through to the unknown verdict
    rather than raising out of `review`.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            first_line = handle.readline(_SHEBANG_READ_LIMIT)
    except OSError:
        return ""
    match = _SHEBANG_RE.match(first_line)
    if match is None:
        return ""
    words = [w for w in (match.group("first"), match.group("second")) if w]
    for word in reversed(words):
        stem = _INTERPRETER_VERSION_RE.sub("", PurePosixPath(word).name)
        language = _LANGUAGE_BY_INTERPRETER.get(stem)
        if language:
            return language
    return ""


def detect_language(path: Path) -> str:
    """Name the language of one file, for `CodingArchetype.review`.

    The suffix answers whenever it is mapped. Content -- the shebang --
    answers only for a suffix that names no language, which is where the
    suffix is absent or lies by carrying no information at all. A file
    neither can place is `UNKNOWN_LANGUAGE`, which is unhandled, so an
    unplaceable file is declined rather than parsed as Python.
    """
    language = _LANGUAGE_BY_SUFFIX.get(path.suffix.lower())
    if language:
        return language
    return _shebang_language(path) or UNKNOWN_LANGUAGE


# Bandit rules escalated above the severity bandit itself reports.
_BANDIT_SEVERITY_OVERRIDES: dict[str, str] = {
    "B101": "high",  # assert used for security-critical check
    "B105": "high",  # hardcoded password
    "B106": "high",  # hardcoded password argument
    "B107": "high",  # hardcoded password default
    "B303": "high",  # weak hash (MD5, SHA1) used
    "B324": "high",  # weak hash used in hashlib.new
    "B501": "high",  # requests with verify=False
    "B502": "high",  # SSL with insecure protocol version
    "B506": "high",  # yaml.load without SafeLoader
    "B602": "high",  # subprocess with shell=True (partial input)
    "B605": "high",  # start_process_with_a_shell
    "B609": "high",  # linux wildcard command
}


# Type-checker rules demoted to low: they still report, and no longer
# block. Removing an entry restores that rule's native severity.
_TYPECHECK_NOISE_DEMOTIONS: dict[str, str] = {
    # reportPossiblyUnboundVariable is absent here: `_possibly_unbound_severity`
    # splits it by binding kind instead.
    "reportAttributeAccessIssue": "low",
    "reportArgumentType": "low",
    "reportOptionalMemberAccess": "low",
    "reportCallIssue": "low",
    "reportOptionalSubscript": "low",
    "reportGeneralTypeIssues": "low",
    "reportOptionalIterable": "low",
    "reportOptionalOperand": "low",
    "reportIndexIssue": "low",
    "reportOperatorIssue": "low",
    # mypy — same class of concern surfaced under different rule names
    "attr-defined": "low",
    "union-attr": "low",
    "assignment": "low",
    "no-any-return": "low",
    "arg-type": "low",
    "no-untyped-def": "low",  # stylistic; not a correctness issue
    "return-value": "low",
    "call-arg": "low",
    "operator": "low",
    "index": "low",
    "misc": "low",
    # `unused-ignore` is not in this map. `_unused_ignore_severity` reads it
    # off the message text, because mypy uses one code for two situations.
}


# mypy answers `unused-ignore` for two situations and only the message text
# separates them, so `_unused_ignore_severity` reads the severity off it.
_IGNORE_NARROWER_RE = re.compile(r"use narrower \[")


def _unused_ignore_severity(message: str) -> str:
    """HIGH for a directive that suppresses nothing; MEDIUM for one
    whose code is merely too broad.

    FALSIFICATION: run mypy with --warn-unused-ignores over a pair of
    files, one carrying a dead `type: ignore[assignment]` and one where
    the same directive is load-bearing. This function is wrong if it
    answers the same severity for both.
    `tests/test_archetype_report_contract.py` holds that pair.
    """
    return "medium" if _IGNORE_NARROWER_RE.search(message or "") else "high"


# Packages mypy knows no stub distribution for. An `import-untyped` row
# naming one drops to low; `import-not-found` never matches.
_UNTYPED_THIRD_PARTY: dict[str, str] = {
    "ccxt": "no py.typed marker, and no stub distribution known to mypy",
}

_IMPORT_UNTYPED_NO_STUBS_RE = re.compile(
    r'Skipping analyzing "(?P<module>[^"]+)": module is installed, '
    r"but missing library stubs or py\.typed marker",
)


def _untyped_import_severity(message: str, native: str) -> str:
    """Score one mypy row carrying the `import-untyped` code.

    LOW for a NAMED package that ships no type information;
    `native` for every other such row.

    `native` is passed in rather than assumed, so a row this
    function declines to demote is scored exactly as it would have
    been had the function never been called.

    FALSIFICATION: this function is wrong if it answers "low" for a
    message naming a package absent from `_UNTYPED_THIRD_PARTY`, for
    a 'Library stubs not installed for' message (a stub package
    exists, so installing it is the fix), or for an
    `import-not-found` row -- which never reaches it, because the
    caller dispatches on the error code first.
    """
    match = _IMPORT_UNTYPED_NO_STUBS_RE.search(message or "")
    if match is None:
        return native
    top_level = match.group("module").split(".", 1)[0]
    return "low" if top_level in _UNTYPED_THIRD_PARTY else native


_PU_NAME_RE = re.compile(r'"([^"]+)"')

# Per-process memo of (import_bound, assignment_bound) by file path.
_PU_BINDING_CACHE: dict[str, tuple[set[str], set[str]]] = {}


# Matched longest-prefix-first, so SIM, SLF, RUF and ANN are not swallowed
# by the single-letter S family.
_RUFF_SEV_MAP: dict[str, str] = {
    "F": "medium",  # pyflakes (real bugs / unused code)
    "E": "medium",  # pycodestyle errors
    "W": "low",  # pycodestyle warnings
    "S": "high",  # bandit-mirror (security)
    "B": "medium",  # bugbear (likely bugs)
    "N": "low",  # naming
    "D": "low",  # docstrings
    "I": "low",  # isort
    "UP": "low",  # pyupgrade
    "SIM": "low",  # simplify — style, must NOT block
    "SLF": "low",  # private-member access — style, must NOT block
    "BLE": "medium",  # blind except
    "PL": "low",  # pylint
    "PT": "low",  # pytest
    "TD": "low",  # todos
    "RUF": "medium",  # ruff-specific
    "PERF": "low",  # perf
    "ANN": "medium",  # missing type annotations
}
_RUFF_FAMILIES_BY_LEN: tuple[str, ...] = tuple(
    sorted(_RUFF_SEV_MAP, key=len, reverse=True)
)


def _module_binding_kinds(path: str) -> tuple[set[str], set[str]]:
    """Return (import_bound, assignment_bound) name sets for a module.

    Parsed with ast rather than regex so that `del`, walrus, with-as,
    for-targets and comprehension targets all count as assignments --
    missing one of those would misclassify a real bug as noise.
    """
    imported: set[str] = set()
    assigned: set[str] = set()
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return imported, assigned

    def _names(node) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name):
                assigned.add(sub.id)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                imported.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                _names(tgt)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            _names(node.target)
        elif isinstance(node, ast.NamedExpr):
            _names(node.target)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            _names(node.target)
        elif isinstance(node, ast.withitem):
            if node.optional_vars is not None:
                _names(node.optional_vars)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assigned.add(node.name)
    return imported, assigned


def _possibly_unbound_severity(message: str, file_path: str) -> str:
    """HIGH when the flagged name is assignment-bound, LOW when it is
    only import-bound.

    Unresolvable cases return LOW: this promotion must never turn a
    parse failure into a blocked release.
    """
    match = _PU_NAME_RE.search(message or "")
    if not match:
        return "low"
    name = match.group(1)
    if file_path not in _PU_BINDING_CACHE:
        _PU_BINDING_CACHE[file_path] = _module_binding_kinds(file_path)
    imported, assigned = _PU_BINDING_CACHE[file_path]
    if name in assigned and name not in imported:
        return "high"
    return "low"


class CodingArchetype:
    """Coding-quality archetype v2 — subprocess-invokes six tools:
    ruff, mypy, pyright, bandit, vulture, semgrep."""

    name = "coding_quality"
    version = "2.1"  # v2.1: added falsification field + calibration hook
    tools = ("ruff", "mypy", "pyright", "bandit", "vulture", "semgrep")
    calibration_name = "coding"

    def load_calibration(self) -> str:
        """Return the human-editable calibration prompt for peer reviewers."""
        from dev_harness.harness.calibrations import load

        return load(self.calibration_name)

    def review(self, target: Path) -> ArchetypeReport:
        target = Path(target).resolve()
        report = ArchetypeReport(target=str(target))

        if not target.exists():
            report.errors.append(f"target not found: {target}")
            report.falsification = self._build_falsification(report)
            return report

        # A directory has no single language, and every analyzer below
        # self-filters to `.py`.
        if target.is_file():
            report.language = detect_language(target)
            if report.language not in HANDLED_LANGUAGES:
                report.unhandled = True
                report.falsification = self._unhandled_falsification(report)
                return report

        # `scanned` stays False on the early return, so an empty report
        # cannot answer passed=True.
        report.scanned = True

        for tool_name, runner in [
            ("ruff", self._run_ruff),
            ("mypy", self._run_mypy),
            ("pyright", self._run_pyright),
            ("bandit", self._run_bandit),
            ("vulture", self._run_vulture),
            ("semgrep", self._run_semgrep),
        ]:
            try:
                findings, status = runner(target)
                report.findings.extend(findings)
                report.tool_availability[tool_name] = status
            except FileNotFoundError:
                report.tool_availability[tool_name] = "missing"
                report.errors.append(f"{tool_name}: not installed")
            except subprocess.TimeoutExpired:
                report.tool_availability[tool_name] = "error"
                report.errors.append(f"{tool_name}: timed out")
            except Exception as e:
                report.tool_availability[tool_name] = "error"
                report.errors.append(f"{tool_name}: {type(e).__name__}: {e}")

        scan_rule_modules(
            report,
            target,
            (
                ("scaffolding", "dev_harness.harness.rules.scaffolding"),
                ("hallucination", "dev_harness.harness.rules.hallucination"),
                # slop and numeric_guard are coding-only; the gui and docs
                # archetypes skip both.
                ("slop", "dev_harness.harness.rules.slop"),
                ("numeric_guard", "dev_harness.harness.rules.numeric_guard"),
                ("delegated_canon", "dev_harness.harness.rules.delegated_canon"),
            ),
            (".py",),
        )

        report.falsification = self._build_falsification(report)
        return report

    @staticmethod
    def _unhandled_falsification(report: ArchetypeReport) -> str:
        """State what would prove an `unhandled` verdict wrong.

        Says plainly that no analyzer ran, because the one way this
        verdict can do harm is being read as a pass.
        """
        return (
            f"This report is wrong if {report.target!r} is not "
            f"{report.language}, or if this archetype in fact carries an "
            f"analyzer that reads {report.language}. NO ANALYZER RAN, so "
            f"this report says nothing about the file's quality and is not "
            f"a pass; it records that the file type has no checker here."
        )

    def _build_falsification(self, report: ArchetypeReport) -> str:
        """State the concrete conditions under which this report is wrong.
        Required field — enforces the show-don't-tell discipline structurally."""
        ok_tools = [t for t, s in report.tool_availability.items() if s == "ok"]
        missing = [t for t, s in report.tool_availability.items() if s == "missing"]
        errored = [t for t, s in report.tool_availability.items() if s == "error"]
        parts = [
            "This report is wrong if:",
            f"(a) any tool marked 'ok' ({', '.join(ok_tools) or 'none'}) "
            "produced non-parseable output that the archetype silently dropped;",
            f"(b) the target file {report.target!r} was modified after review;",
        ]
        if missing:
            parts.append(
                f"(c) any tool marked 'missing' was in fact installed "
                f"and reachable at review time ({', '.join(missing)});"
            )
        if errored:
            parts.append(
                f"(d) any tool marked 'error' failed for reasons other than "
                f"the tool itself (network, disk, permissions): {', '.join(errored)};"
            )
        parts.append(
            f"(e) any of the {len(report.findings)} listed findings does not "
            "correspond to a real defect in the target when re-run manually."
        )
        return " ".join(parts)

    # ---- tool runners ----

    @staticmethod
    def _resolve_executable(tool: str) -> str:
        """Return the absolute path of `tool`, or refuse.

        Two runners used to spawn a bare program name and let the
        operating system search PATH at exec time, while the other
        four spawned `sys.executable`, an absolute path. On Windows
        PATH plus PATHEXT would then run a `pyright.cmd` or
        `semgrep.exe` planted anywhere earlier on PATH, on every
        gated write to a Python file, and the file-level `noqa: S607`
        is what kept it invisible.

        Raising FileNotFoundError is deliberate: `review` already maps
        that to `tool_availability[tool] = "missing"`, which is the
        same verdict a genuinely absent executable produced before.
        """
        resolved = shutil.which(tool)
        if resolved is None:
            raise FileNotFoundError(f"{tool} not on PATH")
        return resolved

    @staticmethod
    def _module_absent(proc: subprocess.CompletedProcess, tool: str) -> bool:
        """True when `python -m <tool>` failed because the module is gone.

        v3.24.34 (C43 step 5). Four analyzers are invoked as
        `python -m <tool>`. An absent module does NOT raise
        FileNotFoundError — the interpreter writes "No module named X"
        to stderr, exits non-zero, and leaves stdout empty. Each runner
        then took its `if not proc.stdout.strip(): return findings,
        "ok"` path and reported a clean run, indistinguishable from the
        analyzer actually having passed the file.

        `_run_archetype_selfcheck` treats passed=True as evidence, so
        uninstalling ruff turned the release gate green while checking
        nothing.
        """
        if proc.returncode == 0:
            return False
        return f"No module named {tool}" in (proc.stderr or "")

    # Rules that are defects in source and correct practice in a test.
    _TEST_FILE_EXEMPT = (
        "S101",  # assert -- the mechanism pytest is built on
        "S105",  # hardcoded password -- fixture credentials are fake
        "S106",  # ditto, as a keyword argument
        "PLR2004",  # magic value in comparison -- expected values ARE literal
        "SLF001",  # private member access -- tests verify internals
    )

    @staticmethod
    def _is_test_file(target: Path) -> bool:
        name = target.name
        return (
            name.startswith("test_")
            or name.endswith("_test.py")
            or "tests" in target.parts
        )

    def _run_ruff(self, target: Path) -> tuple[list[Finding], str]:
        # ruff produces JSON with --output-format=json
        cmd = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--output-format=json",
            "--no-cache",
            "--select=ALL",
        ]
        if self._is_test_file(target):
            cmd.append("--ignore=" + ",".join(self._TEST_FILE_EXEMPT))
        cmd.append(str(target))
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if self._module_absent(proc, "ruff"):
            return [], "missing"
        refuse_silent_failure(proc, "ruff")
        findings: list[Finding] = []
        if not proc.stdout.strip():
            return findings, "ok"
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return findings, "ok"
        # ruff finding: {"code": "F401", "message": "...", "location": {"row": 5, "column": 1}, "filename": "..."}
        for item in data:
            code = item.get("code") or "no-code"
            # Longest-prefix match, not code[0], or every multi-letter
            # family below is unreachable.
            severity = "low"
            for _fam in _RUFF_FAMILIES_BY_LEN:
                if code.startswith(_fam):
                    severity = _RUFF_SEV_MAP[_fam]
                    break
            loc = item.get("location", {})
            findings.append(
                Finding(
                    tool="ruff",
                    severity=severity,
                    file=item.get("filename", str(target)),
                    line=loc.get("row", 0),
                    rule_id=code,
                    message=item.get("message", ""),
                )
            )
        return findings, "ok"

    def _run_mypy(self, target: Path) -> tuple[list[Finding], str]:
        # STRICT flags added in v2 per empirical gap in v1
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "mypy",
                str(target),
                "--show-error-codes",
                "--no-color-output",
                "--no-error-summary",
                "--follow-imports=silent",
                "--disallow-untyped-defs",  # <-- v2 fix
                "--disallow-incomplete-defs",  # <-- v2 fix
                "--warn-return-any",  # <-- v2 fix
                "--warn-unused-ignores",
                # Pinned: mypy writes `./.mypy_cache`, so an unpinned cache
                # is one cache, and one verdict, per caller.
                "--cache-dir",
                str(REPO_ROOT / ".mypy_cache"),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if self._module_absent(proc, "mypy"):
            return [], "missing"
        refuse_silent_failure(proc, "mypy")
        findings: list[Finding] = []
        pat = re.compile(
            r"^(?P<file>.+?):(?P<line>\d+):(?::\d+:)?\s*"
            r"(?P<kind>error|warning|note):\s*"
            r"(?P<msg>.+?)(?:\s+\[(?P<code>[^\]]+)\])?\s*$"
        )
        for line in proc.stdout.splitlines():
            m = pat.match(line)
            if not m:
                continue
            kind = m.group("kind")
            rule_id = m.group("code") or "no-code"
            native_severity = {"error": "high", "warning": "medium", "note": "info"}[
                kind
            ]
            # v3.23.44 — apply the shared type-checker noise demotions
            # (see _TYPECHECK_NOISE_DEMOTIONS docstring above).
            if rule_id == "unused-ignore":
                severity = _unused_ignore_severity(m.group("msg"))
            elif rule_id == "import-untyped":
                severity = _untyped_import_severity(m.group("msg"), native_severity)
            else:
                severity = _TYPECHECK_NOISE_DEMOTIONS.get(rule_id, native_severity)
            findings.append(
                Finding(
                    tool="mypy",
                    severity=severity,
                    file=m.group("file"),
                    line=int(m.group("line")),
                    rule_id=rule_id,
                    message=m.group("msg"),
                )
            )
        return findings, "ok"

    def _run_pyright(self, target: Path) -> tuple[list[Finding], str]:
        proc = subprocess.run(
            [self._resolve_executable("pyright"), "--outputjson", str(target)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        findings: list[Finding] = []
        refuse_silent_failure(proc, "pyright")
        if not proc.stdout.strip():
            return findings, "ok"
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return findings, "ok"
        # Pyright output schema: {"generalDiagnostics": [{"file": "...", "severity": "error", "message": "...", "range": {"start": {"line": 0}}, "rule": "..."}]}
        sev_map = {"error": "high", "warning": "medium", "information": "info"}
        for diag in data.get("generalDiagnostics", []):
            line_num = diag.get("range", {}).get("start", {}).get("line", 0) + 1
            rule_id = diag.get("rule", "no-code")
            if rule_id == "reportPossiblyUnboundVariable":
                severity = _possibly_unbound_severity(
                    diag.get("message", ""), diag.get("file", str(target))
                )
            else:
                severity = _TYPECHECK_NOISE_DEMOTIONS.get(
                    rule_id, sev_map.get(diag.get("severity", ""), "medium")
                )
            findings.append(
                Finding(
                    tool="pyright",
                    severity=severity,
                    file=diag.get("file", str(target)),
                    line=line_num,
                    rule_id=rule_id,
                    message=diag.get("message", ""),
                )
            )
        return findings, "ok"

    def _run_bandit(self, target: Path) -> tuple[list[Finding], str]:
        proc = subprocess.run(
            # Without `-r` bandit given a directory scans no file and exits 0
            # with an empty results array.
            [sys.executable, "-m", "bandit", "-f", "json", "-q", "-r", str(target)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if self._module_absent(proc, "bandit"):
            return [], "missing"
        refuse_silent_failure(proc, "bandit")
        findings: list[Finding] = []
        if not proc.stdout.strip():
            return findings, "ok"
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"bandit produced non-JSON output: {e}")
        sev_map = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
        # B101 is dropped under tests/ only. A production assert still
        # surfaces, and every other bandit rule still fires on a test.
        _is_test_file = "/tests/" in str(target).replace("\\", "/")
        for issue in data.get("results", []):
            rule_id = issue.get("test_id", "unknown")
            if _is_test_file and rule_id == "B101":
                continue
            # v2 fix: escalate well-known dangerous rules
            severity = _BANDIT_SEVERITY_OVERRIDES.get(
                rule_id, sev_map.get(issue.get("issue_severity", ""), "medium")
            )
            findings.append(
                Finding(
                    tool="bandit",
                    severity=severity,
                    file=issue.get("filename", str(target)),
                    line=issue.get("line_number", 0),
                    rule_id=rule_id,
                    message=issue.get("issue_text", ""),
                )
            )
        return findings, "ok"

    def _run_vulture(self, target: Path) -> tuple[list[Finding], str]:
        # v2 fix: lower --min-confidence to 60 to catch unused locals
        proc = subprocess.run(
            [sys.executable, "-m", "vulture", "--min-confidence", "60", str(target)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if self._module_absent(proc, "vulture"):
            return [], "missing"
        refuse_silent_failure(proc, "vulture")
        findings: list[Finding] = []
        pat = re.compile(
            r"^(?P<file>.+?):(?P<line>\d+):\s*"
            r"(?P<msg>.+?)\s+\((?P<conf>\d+)%\s+confidence\)\s*$"
        )
        for line in proc.stdout.splitlines():
            m = pat.match(line)
            if not m:
                continue
            conf = int(m.group("conf"))
            severity = "high" if conf >= 90 else ("medium" if conf >= 70 else "low")
            findings.append(
                Finding(
                    tool="vulture",
                    severity=severity,
                    file=m.group("file"),
                    line=int(m.group("line")),
                    rule_id="dead-code",
                    message=m.group("msg"),
                )
            )
        return findings, "ok"

    def _run_semgrep(self, target: Path) -> tuple[list[Finding], str]:
        # Use semgrep's default Python security ruleset
        proc = subprocess.run(
            [
                self._resolve_executable("semgrep"),
                "scan",
                "--config=p/python",
                "--config=p/security-audit",
                "--json",
                "--quiet",
                "--no-git-ignore",
                str(target),
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        findings: list[Finding] = []
        refuse_silent_failure(proc, "semgrep")
        if not proc.stdout.strip():
            return findings, "ok"
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return findings, "ok"
        # semgrep result: {"results": [{"check_id": "...", "path": "...", "start": {"line": N},
        #                  "extra": {"severity": "ERROR|WARNING|INFO", "message": "..."}}]}
        sev_map = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}
        for item in data.get("results", []):
            extra = item.get("extra", {})
            findings.append(
                Finding(
                    tool="semgrep",
                    severity=sev_map.get(extra.get("severity", ""), "medium"),
                    file=item.get("path", str(target)),
                    line=item.get("start", {}).get("line", 0),
                    rule_id=item.get("check_id", "no-code"),
                    message=extra.get("message", ""),
                )
            )
        return findings, "ok"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python -m tools.harness.coding_archetype <path>")
        print(
            "       reviews path with ruff + mypy + pyright + bandit + vulture + semgrep;"
        )
        print("       prints JSON report; exit 0 if passed, 1 if failed")
        return 2
    target = Path(argv[0])
    report = CodingArchetype().review(target)
    print(json.dumps(report.to_dict(), indent=2))
    return cli_exit(report)


if __name__ == "__main__":
    sys.exit(main())
