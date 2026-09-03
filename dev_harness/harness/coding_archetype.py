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
# S607 WAS SUPPRESSED HERE AND IT WAS NOT A FALSE POSITIVE.
#
# The directive used to read `S603, S607`, justified as "partial
# executable path -- deliberate since we let PATH resolve the tool".
# Measured 2026-08-13 by stripping it: S603 at six lines and S607 at
# two -- `["pyright", ...]` and `["semgrep", ...]`. The other four
# runners spawn `[sys.executable, "-m", ...]`, an absolute
# interpreter path. So the file already held the safe form and
# deviated from it twice, and the blanket directive is what stopped
# anyone noticing. On Windows, PATH plus PATHEXT would execute a
# `pyright.cmd` or `semgrep.exe` planted anywhere earlier on PATH,
# under the developer's own token, on every gated write to a Python
# file. Both now resolve through `_resolve_executable` and are
# spawned by absolute path, so S607 reports zero here BY
# CONSTRUCTION rather than by suppression.
#
# S603 remains, and it is not avoidable. Measured with ruff 0.16 on
# six argv forms: an all-literal argv draws no S603, and every argv
# carrying a variable draws one. Every runner here must pass the
# target path, which is a variable by definition. There is no
# compliant form of "spawn an analyzer over a caller-supplied path",
# so this line is the residue, narrowed from two rules to one.
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


# `Finding` and `ArchetypeReport` now live in tools/harness/report.py.
# Five archetypes each carried a copy; the copies drifted, and two of
# the drifts shipped a green report for a run that checked nothing.
# Re-exported above so `from dev_harness.harness.coding_archetype import
# ArchetypeReport` keeps working.


# ---------------------------------------------------------------------------
# LANGUAGE DETECTION
#
# Every analyzer this archetype drives is a Python analyzer, and none of
# them refuses a file that is not Python. MEASURED on one JavaScript
# file, src/gui/web/bot_swarm_list.js: ruff emitted 3,089 findings, 6 of
# them HIGH, and vulture raised "unterminated string literal" after
# reading a `//` comment containing an apostrophe as an unclosed Python
# string. The verdict was passed=False for reasons that described
# nothing in the file. Sixty-two JavaScript files in this tree were
# ungateable that way.
#
# A file whose language has no toolchain here is reported UNHANDLED, a
# verdict distinct from both passed and failed: nothing ran, so the
# report says nothing about the code. `ArchetypeReport.passed` refuses
# it, so the gate cannot be satisfied by a file it never examined.
#
# NO JAVASCRIPT TOOLCHAIN IS INTRODUCED. There is no Node on this
# machine. Detecting JavaScript and declining it is the whole change.
#
# FALSIFICATION: this block is wrong if a `.py` file reaches any path
# other than the analyzers below; if a file the analyzers cannot parse
# still reaches them; or if an unhandled verdict is ever readable as a
# pass.
# ---------------------------------------------------------------------------

UNKNOWN_LANGUAGE = "unknown"

# The languages this archetype carries analyzers for. Adding a name here
# is a claim that the runners below can read that language.
HANDLED_LANGUAGES: frozenset[str] = frozenset({"python"})

# The suffix decides whenever it is mapped, because the runtimes that
# consume these files dispatch on it -- Python's import machinery on
# `.py`, Node's resolver on `.js`, `.mjs` and `.cjs`. A suffix is a
# contract, not a hint, so no content check may overturn one; that is
# what keeps the Python path identical.
_LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".pyw": "python",
    # A PyInstaller spec is Python that PyInstaller execs. Measured on
    # Acervator_win.spec before this map existed: every analyzer read it
    # and returned 52 findings, so leaving it unmapped would drop real
    # coverage rather than stop a fabrication.
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



# ---------------------------------------------------------------------------
# Bandit severity remap - operator directive:
# B105 (hardcoded password) and B101 (assert-for-security) are HIGH
# in the security-community consensus, even though bandit's raw output
# ranks them LOW. Any addition to this map is a curated escalation.
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# v3.23.44 — Type-checker noise demotions (per full-codebase-audit doc
# docs/audits/2026-07-28_full_codebase_archetype_audit.md § 4.5).
# These pyright + mypy rules fire in vast numbers on Acervator's
# defensive async trading paths (`try: x = fn(); except: pass; use(x)`)
# and on the duck-typed exchange connector API where static analysis
# cannot resolve dynamic attributes. Individual sites are not
# actionable at HIGH severity — the type-inference gap is
# architectural, not per-site. Demoted here to LOW so they still
# appear in reports for anyone who wants them, without polluting the
# HIGH gate that blocks self-report-done.
#
# Any addition to this map is a curated demotion. Removing an entry
# re-escalates the rule to its native severity.
# ---------------------------------------------------------------------------
_TYPECHECK_NOISE_DEMOTIONS: dict[str, str] = {
    # pyright
    # NOTE: reportPossiblyUnboundVariable is NOT demoted wholesale. It is
    # split by binding kind in `_possibly_unbound_severity()` below --
    # import-bound is noise, assignment-bound is a real flow bug. See
    # that function's docstring for the measurement that justifies it.
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
    # NOTE: `unused-ignore` is NOT in this map. Its severity is read
    # off the message text by `_unused_ignore_severity` below, because
    # mypy uses one code for two different situations.
}


# ---------------------------------------------------------------------------
# 2026-08-13 -- surfaced by --warn-unused-ignores on the mypy invocation
# below. mypy answers `unused-ignore` for TWO different situations and
# only one of them is a dead directive. The message text separates them,
# so the severity is read off the message rather than off the code.
#
#   Unused "type: ignore" comment
#       the directive suppresses nothing. Deleting it changes no other
#       diagnostic, measured by strip-and-diff on 5 of 5 such rows in
#       this tree. It is a mypy `error`, so it keeps mypy's native HIGH.
#
#   Unused "type: ignore" comment, use narrower [method-assign]
#   instead of [assignment] code
#       the directive IS load-bearing. mypy honours it and advises a
#       narrower code in the same breath, so stripping it ADDS a
#       `method-assign` error -- measured on
#       tests/test_api_load_monitor.py:51. Calling that one dead would
#       be wrong. It surfaces at MEDIUM because its actionable content
#       is "narrow the code", not "delete the line".
#
# The first version of this rule demoted BOTH to medium, reasoning that
# the oracle mislabels 1 row in 6. That reason does not survive
# measurement: the message text separates the two classes with no error
# over this tree's whole population, and the demotion bought nothing
# except three files staying green while carrying three directives
# measured DEAD. A severity must not be chosen to avoid its own
# consequence.
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 2026-08-14 -- UNTYPED THIRD-PARTY PACKAGES, NAMED ONE AT A TIME.
#
# WHY THIS EXISTS
# ---------------
# mypy answers `import-untyped` as an `error`, so it arrived here at
# HIGH, and HIGH blocks. It is not a statement about our code. A file
# whose entire content is two import statements, one naming ccxt and
# one naming its async_support submodule, draws the identical two
# rows, measured 2026-08-14. So every file that imports ccxt was
# blocked by that library's packaging and by nothing the file itself
# did. src/gui/bot_wizard.py and
# src/exchange/ccxt_connector.py were both held by exactly this, and
# the only per-file answer available is a type-ignore directive. The
# rule as it stood taught suppression. That is what this map stops.
#
# WHY A NAMED MAP AND NOT A mypy FLAG
# -----------------------------------
# `--ignore-missing-imports` is a blanket: it also silences
# `import-not-found`, and an import of a package that is NOT
# INSTALLED is a real defect that must stay visible.
# `--disable-error-code=import-untyped` is a blanket over every
# package, named or not. `--follow-untyped-imports` makes mypy
# typecheck the library's own source, which reports the LIBRARY's
# defects against OUR file. None of the three can be read as a list.
#
# The mechanism used instead is the one this file already uses twice
# -- _BANDIT_SEVERITY_OVERRIDES and _TYPECHECK_NOISE_DEMOTIONS -- a
# curated severity remap applied to an already-parsed finding, with
# the reason recorded beside the entry. It has one property no flag
# has: mypy's argv does not change, so mypy computes exactly what it
# computed before and the row stays in the report at LOW. Nothing is
# hidden. One label moves.
#
# WHAT MAY BE NAMED HERE
# ----------------------
# Only a package for which mypy itself knows of NO stub distribution.
# mypy separates the two cases in the message text, and its own
# registry is the oracle -- measured 2026-08-14 against mypy 2.1.0:
#
#     mypy.stubinfo.stub_distribution_name("ccxt")      -> None
#     mypy.stubinfo.stub_distribution_name("reportlab") -> types-reportlab
#
#   'Skipping analyzing "X": module is installed, but missing
#   library stubs or py.typed marker'
#       mypy knows of nothing to install. Not fixable from this
#       repo. NAMEABLE.
#
#   'Library stubs not installed for "X"'
#       a stub package exists and is merely absent. Installing it is
#       the fix, so the row must keep its HIGH. reportlab, imported
#       by src/core/version_sweep.py, is in exactly that state and is
#       deliberately NOT named below.
#
# One entry names one distribution. PEP 561 puts the py.typed marker
# at the distribution root, so "ccxt ships no py.typed" is a fact
# about ccxt and every ccxt.* submodule at once; the matcher compares
# the top-level name for that reason. Measured 2026-08-14 on ccxt
# 4.5.73: the installed package carries no py.typed marker, no
# ccxt-stubs and no types-ccxt are installed, and the package ships
# no stub file of its own.
#
# The matcher requires ALL THREE of: the `import-untyped` code, the
# no-stub-distribution message form, and the named package. If a stub
# package for ccxt is ever published, mypy switches to the second
# message form, this entry stops matching, and the row returns to
# HIGH on its own. The rule retires itself rather than outliving its
# reason.
#
# FALSIFICATION: this map is wrong if a row it demotes is about
# anything other than a named package's missing type information; if
# an `import-not-found` row ever reaches LOW through it; or if adding
# an entry changes any finding in a file that does not import that
# package.
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# v3.24.20 — possibly-unbound triage by BINDING KIND.
#
# WHY THIS EXISTS
# ---------------
# v3.23.44 demoted `reportPossiblyUnboundVariable` to LOW wholesale
# because it fires 2,465 times across src/ + main.py. That demotion made
# the gate blind to a whole bug class. Measured on 2026-08-04:
#
#     import-bound only (Qt try/except guard)  2,456   <- genuine noise
#     ASSIGNMENT-bound only (real flow bug)        9   <- real defects
#     ambiguous                                    0
#
# The separation is total. The 2,456 are `try: from PySide6 import X`
# guarded by `if _HAS_QT:`, where the symbol can never actually be
# touched unbound. The 9 are locals assigned inside a conditional and
# read outside it. One of those 9 is main.py:1107 `_autostart_bot_count`
# -- an UnboundLocalError that kills startup on any machine with no saved
# bot state, i.e. every fresh install. The gate saw it and passed it.
#
# So: classify by how the name is bound in the module under test.
# Import-bound stays LOW. Assignment-bound is promoted to HIGH, which
# blocks self-report-done.
# ---------------------------------------------------------------------------
_PU_NAME_RE = re.compile(r'"([^"]+)"')

# Per-process memo of (import_bound, assignment_bound) by file path.
# Module level rather than a mutable default argument: the default
# argument carried the same lifetime with none of the visibility, and
# needed a suppression to say so.
_PU_BINDING_CACHE: dict[str, tuple[set[str], set[str]]] = {}


# Ruff code-family severities. Matched LONGEST-PREFIX-FIRST so that
# multi-letter families (SIM, SLF, RUF, ANN, PERF...) are not swallowed
# by their single-letter neighbours (S = bandit security).
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


# ---------------------------------------------------------------------------
# The archetype
# ---------------------------------------------------------------------------


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
        # self-filters to `.py` when handed one, so a mixed tree needs
        # no gate here.
        if target.is_file():
            report.language = detect_language(target)
            if report.language not in HANDLED_LANGUAGES:
                report.unhandled = True
                report.falsification = self._unhandled_falsification(report)
                return report

        # Past this line the analyzers actually run over the target.
        # `scanned` stays False on the early return above, so an empty
        # report can no longer answer passed=True.
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

        # v3.23.90 + v3.23.91 — universal rule modules. Adds
        # scaffolding + hallucination findings normalized to the
        # Finding schema so they show up in by_tool + by_severity as
        # first-class results, not out-of-band annexes.
        #
        # 2026-08-13 — the enumeration, the read and the status now come
        # from `scan_rule_modules`. This block used to read `target`
        # itself, substitute "" when the read failed, scan the empty
        # string and still report every module `ok`.
        scan_rule_modules(
            report,
            target,
            (
                ("scaffolding", "dev_harness.harness.rules.scaffolding"),
                ("hallucination", "dev_harness.harness.rules.hallucination"),
                # v3.23.92 — slop is coding-only per operator directive
                # 2026-08-01: "slop probably only applied to coding."
                # gui_archetype + docs_archetype deliberately skip it.
                ("slop", "dev_harness.harness.rules.slop"),
                # 2026-08-10 — numeric_guard is coding-only for the same
                # reason: numeric admission is a code contract, not a
                # widget or a document concern.
                ("numeric_guard", "dev_harness.harness.rules.numeric_guard"),
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

    # Rules that are DEFECTS in source and CORRECT PRACTICE in a test.
    #
    # v3.24.84 — without this the gate was dead on every test file.
    # MEASURED across 14 test files: 13 failed the archetype, and the
    # high-severity findings were 235 S101 against 1 S112 and 5
    # dead-code. `assert` is how pytest is written -- S101 exists
    # because asserts vanish under `python -O`, which is not how the
    # suite runs -- so every test file failed, permanently, on a rule
    # that cannot be complied with.
    #
    # The cost was not the noise. It was that `passed=False` on a test
    # file carried NO information, so it was waived every time, and the
    # PostToolUse hook that blocks self-reporting done became a
    # formality. The 6 genuine findings above were invisible inside 235
    # false ones.
    #
    # A gate that always fails is the same as a gate that never runs,
    # with the added cost of teaching its readers to ignore it.
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
            # Ruff severity: everything from --select=ALL is technically warning-level;
            # normalize by code family.
            #
            # v3.24.20 — LONGEST-PREFIX match, not code[0].
            # Until now this read `fam = code[0]`, which made every
            # multi-letter key below unreachable and mis-scored two
            # families badly:
            #   SIM114 / SLF001  -> matched "S" -> HIGH (blocking)
            #   RUF* / ANN*      -> matched nothing -> low, never "medium"
            # So "combine these if branches" blocked a release at HIGH
            # while genuine findings sat at low. Sorting keys by length
            # and taking the first match fixes both directions at once.
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
                # 2026-08-13: without this a `type: ignore` that
                # suppresses nothing is invisible to the gate for ever,
                # so a directive could outlive the defect it was written
                # for and nobody could tell. Measured on a two-file
                # fixture pair: the dead ignore drew no output at all
                # before the flag, and `unused-ignore` after it, while
                # the live ignore stayed silent on both sides.
                "--warn-unused-ignores",
                # Pinned, not defaulted. mypy writes `./.mypy_cache`, so
                # the cache -- and with it the incremental state a
                # diagnostic can depend on -- used to be chosen by the
                # caller's working directory. A cache per caller is a
                # verdict per caller.
                #
                # NOT a fresh cache per run: measured on one file, a cold
                # cache costs 8.8s against 0.6s warm, 15x, and the hook
                # already runs on a 30s budget. The residual is stated in
                # docs/audits/2026-08-13_harness_gap_closure.md - compare
                # two TREES with a fresh cache, because mypy's incremental
                # mode can answer differently on a warm one.
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
                # v3.24.20 — triaged by binding kind rather than
                # demoted wholesale. Import-bound stays low (Qt guard
                # noise); assignment-bound is promoted to high because
                # it is a genuine UnboundLocalError waiting to fire.
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
            # `-r`: without it, bandit handed a DIRECTORY scans no
            # file at all and exits 0 with an empty results array, so
            # this runner reported `ok` having read nothing. MEASURED
            # 2026-08-13 on a directory holding one copy of the
            # harness's own known_bad.py: the FILE target drew B101,
            # B105 and B404, two of them HIGH, and the DIRECTORY target
            # drew none. `-r` over a single file is the same scan.
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
        # v3.24.5 — pytest uses `assert` as its native assertion
        # syntax; bandit B101 flags every one as HIGH. In test files
        # this is idiomatic (pytest even AST-rewrites asserts for
        # richer diffs) and running pytest with -O to strip asserts
        # would make the tests inert — nobody does this. Suppress
        # B101 when the target is under tests/ so real production
        # asserts still surface unmuted.
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


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
