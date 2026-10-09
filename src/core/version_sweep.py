"""Release sweep driven by ``VersionSweep``.

``main`` runs every entry of the ``checks`` list in ``VersionSweep.run``, then
exits 1 when ``SweepResult.passed`` is False. Each ``Finding`` carries a
``Severity`` and a category, and ``passed`` counts only CRITICAL and HIGH.
A check that calls ``_no_subject`` lands in ``SweepResult.not_inspected`` and
never prints the pass mark. ``--report`` adds ``save_pdf_report`` beside the
``save_json_report`` output.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src._version import UNKNOWN_VERSION, resolve_version
from src.core.log_paths import get_reports_dir

logger = logging.getLogger("acervator.version_sweep")

ROOT = Path(__file__).resolve().parent.parent.parent


class Severity:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass
class Finding:
    severity: str
    category: str  # SECURITY | QUALITY | CONSISTENCY | DEPENDENCY | HYGIENE
    file: str
    line: int
    description: str
    suggestion: str = ""
    auto_fixable: bool = False


@dataclass
class SweepResult:
    version: str
    timestamp: str
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    lines_scanned: int = 0
    elapsed_sec: float = 0.0
    not_inspected: dict[str, str] = field(default_factory=dict)

    @property
    def critical(self):
        return [f for f in self.findings if f.severity == Severity.CRITICAL]

    @property
    def high(self):
        return [f for f in self.findings if f.severity == Severity.HIGH]

    @property
    def medium(self):
        return [f for f in self.findings if f.severity == Severity.MEDIUM]

    @property
    def low(self):
        return [f for f in self.findings if f.severity == Severity.LOW]

    @property
    def passed(self):
        return len(self.critical) == 0 and len(self.high) == 0


VERSION_LITERAL = re.compile(
    r"^\d+\.\d+(?:\.\d+){0,2}(?:[+-][0-9A-Za-z][0-9A-Za-z.]*)?$"
)

PYTHON_SUFFIXES = frozenset({".py", ".spec"})
SCRIPT_SUFFIXES = frozenset({".sh", ".ps1", ".bat", ".cmd"})

FROZEN_CONTENT_SUFFIX = "_FROZEN_AT"

_NAME_WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")

# A word that, standing beside `version`, makes the value somebody else's.
FOREIGN_VERSION_SUBJECTS = frozenset(
    {
        "api",
        "electron",
        "macos",
        "max",
        "min",
        "minimum",
        "node",
        "os",
        "osx",
        "platform",
        "protocol",
        "python",
        "qt",
        "required",
        "requires",
        "schema",
        "sdk",
        "supported",
        "system",
        "target",
        "windows",
    }
)

_SCRIPT_ASSIGNMENT = re.compile(
    r"^\s*(?:export\s+|set\s+)?\$?(?P<name>[A-Za-z_][A-Za-z0-9_:]*)\s*=\s*"
    r"[\"']?(?P<value>[0-9A-Za-z.+-]+)[\"']?\s*$"
)
_SCRIPT_OPTION = re.compile(
    r"--(?P<name>[A-Za-z][A-Za-z0-9_-]*)[=\s]+[\"']?(?P<value>[0-9A-Za-z.+-]+)"
)


@dataclass(frozen=True)
class ShadowLiteral:
    """A version string written down where the resolved version belongs."""

    line: int
    slot: str
    name: str
    value: str


def is_version_literal(value: object) -> bool:
    """Report whether a value is a version string such as ``1.2.3``."""
    return isinstance(value, str) and bool(VERSION_LITERAL.match(value))


def name_words(name: str) -> set[str]:
    """Split an identifier, key or option into lowercase words.

    Splits on separators and on camel-case boundaries, so
    ``LSMinimumSystemVersion`` yields ``ls minimum system version``.
    """
    return {word.lower() for word in _NAME_WORDS.findall(name)}


def names_a_version(name: str) -> bool:
    """Report whether a name denotes THIS application's version.

    ``version`` qualified by another subject states a requirement on
    something else — ``LSMinimumSystemVersion`` is the macOS a bundle
    needs, not the version Acervator reports.
    """
    words = name_words(name)
    return "version" in words and words.isdisjoint(FOREIGN_VERSION_SUBJECTS)


def is_bare_version_key(name: str) -> bool:
    """Report whether a mapping key is the unqualified word ``version``.

    A record stamps its own schema lineage under that key and nothing reads
    it back as the application's version. A key that qualifies the word —
    ``FileVersion``, ``ProductVersion``, ``app_version`` — names the
    application, so a literal there is a restatement.
    """
    return name.strip("-_ ").lower() == "version"


def is_frozen_content_name(name: str) -> bool:
    """Report whether a name records the release some content was cut from.

    ``generate_essay_ja.py`` pins ``_CONTENT_VERSION_FROZEN_AT``. That value
    is a true statement about a translated body, not a claim about this
    build, and the file warns at import when it differs from the running
    version.
    """
    return name.endswith(FROZEN_CONTENT_SUFFIX)


def defines_version_resolver(tree: ast.Module) -> bool:
    """Report whether a module defines ``resolve_version``.

    That module is the version authority. Its literals are the values the
    resolver itself returns when git and the baked stamp are both absent,
    so they restate nothing.
    """
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "resolve_version"
        for node in tree.body
    )


class _ShadowLiteralVisitor(ast.NodeVisitor):
    """Collect version literals occupying a slot the resolved version fills."""

    def __init__(self) -> None:
        self.found: list[ShadowLiteral] = []
        self._handlers = 0

    def _record(self, node: ast.AST, slot: str, name: str, value: str) -> None:
        """Add one literal, once. A name and its operand can both reach it."""
        line = getattr(node, "lineno", 0)
        if any(s.line == line and s.value == value for s in self.found):
            return
        self.found.append(ShadowLiteral(line, slot, name, value))

    @staticmethod
    def _literal(node: Optional[ast.AST]) -> Optional[str]:
        if isinstance(node, ast.Constant) and is_version_literal(node.value):
            return str(node.value)
        return None

    def _bind(self, target: ast.AST, value: ast.AST) -> None:
        name = getattr(target, "id", None) or getattr(target, "attr", None)
        if not name or not names_a_version(name) or is_frozen_content_name(name):
            return
        literal = self._literal(value)
        if literal:
            slot = "except fallback" if self._handlers else "assignment"
            self._record(value, slot, name, literal)
            return
        if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or):
            fallback = value.values[-1]
            literal = self._literal(fallback)
            if literal:
                self._record(fallback, "or fallback", name, literal)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._bind(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._bind(node.target, node.value)
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        for stmt in node.body:
            self.visit(stmt)
        for handler in node.handlers:
            self._handlers += 1
            for stmt in handler.body:
                self.visit(stmt)
            self._handlers -= 1
        for stmt in [*node.orelse, *node.finalbody]:
            self.visit(stmt)

    def _parameter_defaults(self, args: ast.arguments) -> None:
        positional = [*args.posonlyargs, *args.args]
        tail = positional[len(positional) - len(args.defaults) :]
        pairs = [*zip(tail, args.defaults), *zip(args.kwonlyargs, args.kw_defaults)]
        for arg, default in pairs:
            literal = self._literal(default)
            if literal and names_a_version(arg.arg):
                self._record(default, "parameter default", arg.arg, literal)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._parameter_defaults(node.args)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._parameter_defaults(node.args)
        self.generic_visit(node)

    def _lookup_default(self, node: ast.Call) -> None:
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "get":
            return
        if len(node.args) != 2:
            return
        key, fallback = node.args
        literal = self._literal(fallback)
        if (
            literal
            and isinstance(key, ast.Constant)
            and isinstance(key.value, str)
            and names_a_version(key.value)
        ):
            self._record(fallback, "lookup default", key.value, literal)

    def _keyword_defaults(self, node: ast.Call) -> None:
        option = next(
            (
                arg.value
                for arg in node.args
                if isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and names_a_version(arg.value)
            ),
            None,
        )
        for keyword in node.keywords:
            literal = self._literal(keyword.value)
            if not literal or keyword.arg is None:
                continue
            if names_a_version(keyword.arg):
                self._record(keyword.value, "keyword argument", keyword.arg, literal)
            elif keyword.arg == "default" and option:
                self._record(keyword.value, "option default", option, literal)

    def visit_Call(self, node: ast.Call) -> None:
        self._lookup_default(node)
        self._keyword_defaults(node)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            literal = self._literal(value)
            if (
                literal
                and names_a_version(key.value)
                and not is_bare_version_key(key.value)
            ):
                self._record(value, "mapping entry", key.value, literal)
        self.generic_visit(node)

    @staticmethod
    def _version_name_in(nodes: list[ast.expr]) -> Optional[str]:
        for node in nodes:
            for child in ast.walk(node):
                name = getattr(child, "id", None) or getattr(child, "attr", None)
                if isinstance(name, str) and names_a_version(name):
                    return name
        return None

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if isinstance(node.op, ast.Or):
            fallback = node.values[-1]
            literal = self._literal(fallback)
            name = self._version_name_in(node.values[:-1]) if literal else None
            if literal and name:
                self._record(fallback, "or fallback", name, literal)
        self.generic_visit(node)


def find_python_shadow_literals(source: str) -> list[ShadowLiteral]:
    """Return every version literal in Python source that shadows the version.

    Covers Python-syntax build inputs as well, so a PyInstaller ``.spec``
    is read the same way. Raises ``SyntaxError`` when the source does not
    parse, so a caller records the file instead of scoring it clean.
    """
    tree = ast.parse(source)
    if defines_version_resolver(tree):
        return []
    visitor = _ShadowLiteralVisitor()
    visitor.visit(tree)
    return visitor.found


def find_script_shadow_literals(source: str) -> list[ShadowLiteral]:
    """Return every version literal a shell or PowerShell script writes down."""
    found: list[ShadowLiteral] = []
    for line_no, raw in enumerate(source.splitlines(), 1):
        line = raw.split(" #", 1)[0]
        if line.lstrip().startswith("#"):
            continue
        assigned = _SCRIPT_ASSIGNMENT.match(line)
        if (
            assigned
            and names_a_version(assigned["name"])
            and not is_frozen_content_name(assigned["name"])
            and is_version_literal(assigned["value"])
        ):
            found.append(
                ShadowLiteral(
                    line_no, "assignment", assigned["name"], assigned["value"]
                )
            )
            continue
        for option in _SCRIPT_OPTION.finditer(line):
            if names_a_version(option["name"]) and is_version_literal(option["value"]):
                found.append(
                    ShadowLiteral(
                        line_no,
                        "option default",
                        f"--{option['name']}",
                        option["value"],
                    )
                )
    return found


class VersionSweep:

    SKIP_DIRS = {
        "__pycache__",
        ".git",
        "node_modules",
        "data",
        "reports",
        "logs",
        "cpp_version",
        "cloud",
        "dist",
        "build",
    }
    # Directories the version check does not enter. A literal in a test
    # tree, a document or the harness reaches no version-reporting surface.
    VERSION_SKIP_DIRS = {
        "tests",
        "docs",
        "docs-archive",
        "dev_harness",
        "harness_fixtures",
        "site-packages",
        ".venv",
        "venv",
    }
    SKIP_EXTS = {
        ".pyc",
        ".png",
        ".jpg",
        ".gif",
        ".mp4",
        ".pdf",
        ".zip",
        ".spec",
        ".json",
    }

    # Patterns that must NEVER appear in source
    SECRET_PATTERNS = [
        # Hard-coded credential fragments
        (r'api_key\s*=\s*["\'][A-Za-z0-9+/]{20,}["\']', "Possible hard-coded API key"),
        (
            r'api_secret\s*=\s*["\'][A-Za-z0-9+/]{20,}["\']',
            "Possible hard-coded API secret",
        ),
        (r'password\s*=\s*["\'][^"\']{6,}["\']', "Possible hard-coded password"),
        (r'token\s*=\s*["\'][A-Za-z0-9_\-\.]{20,}["\']', "Possible hard-coded token"),
        (r"AKIA[0-9A-Z]{16}", "Possible AWS access key ID"),
        (r"(?:=|:)\s*[A-Za-z0-9/+]{40}", "Possible AWS secret key (40-char base64)"),
        (
            r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
            "PEM private key header — verify this is format-handling, not embedded key",
        ),
    ]

    INSECURE_PATTERNS = [
        (r"\bpickle\.loads?\b", "pickle.load is unsafe with untrusted data"),
        (r"\beval\s*\(", "eval() executes arbitrary code"),
        (r"\bexec\s*\(", "exec() executes arbitrary code (check if intentional)"),
        (
            r"\bos\.system\s*\(",
            "os.system() is vulnerable to shell injection — use subprocess",
        ),
        (
            r"\bsubprocess\.call\s*\(.*shell\s*=\s*True",
            "subprocess with shell=True is vulnerable to injection",
        ),
        (
            r"\bsubprocess\.run\s*\(.*shell\s*=\s*True",
            "subprocess with shell=True is vulnerable to injection",
        ),
        (r"\bhashlib\.md5\b", "MD5 is cryptographically broken — use SHA-256+"),
        (r"\bhashlib\.sha1\b", "SHA-1 is cryptographically weak — use SHA-256+"),
        (
            r"\brandom\.random\b",
            "random.random() is not cryptographically secure; use secrets module for auth",
        ),
        (
            r"\bhttp://(?!localhost|127\.0\.0\.1)",
            "Plain HTTP in non-localhost URL — use HTTPS",
        ),
    ]

    DEBUG_PATTERNS = [
        (r"\bbreakpoint\(\)", "breakpoint() left in production code"),
        (r"\bpdb\.set_trace\(\)", "pdb.set_trace() left in production code"),
        (r'\bprint\s*\(\s*["\']DEBUG', "Debug print statement"),
        (r"# (?:TEMP|HACK|XXX|FIXME|BUG)\b", "Flagged comment requires attention"),
    ]

    def __init__(self, root: Path = ROOT, fix: bool = False):
        self.root = root
        self.fix = fix
        self.result = SweepResult(
            version=self._get_version(),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._skipped: list[tuple[str, str]] = []
        self._no_subject_reason: Optional[str] = None

    def _no_subject(self, reason: str) -> None:
        """Record ``reason`` for the check that found nothing to read.

        ``run`` copies it into ``SweepResult.not_inspected`` and prints NOT
        INSPECTED in place of the pass mark.
        """
        self._no_subject_reason = reason

    def _read_or_skip(self, path: Path) -> Optional[str]:
        """Read a file for scanning, recording failure in ``self._skipped``.

        Returns None when the read raises OSError.
        """
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            rel = str(path)
            try:
                rel = str(path.relative_to(self.root))
            except ValueError:
                pass
            self._skipped.append((rel, f"{type(exc).__name__}: {exc}"))
            logger.warning(
                "version_sweep: could not read %s (%s) — file is "
                "EXCLUDED from all checks",
                rel,
                exc,
            )
            return None

    @property
    def skipped_files(self) -> list[tuple[str, str]]:
        """Files excluded from the sweep, with the reason for each."""
        return list(self._skipped)

    def _get_version(self) -> str:
        """Return the version resolved for the tree under sweep.

        Derived from HEAD's own date and id, or from the value a build baked
        in. There is no literal left to scan for, so no parse can fail and
        leave ``check_version_consistency`` with nothing to compare against.
        """
        return resolve_version(self.root)

    def _py_files(self):
        for dirpath, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                if fname.endswith(".py"):
                    yield Path(dirpath) / fname

    def _all_files(self):
        for dirpath, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                ext = Path(fname).suffix.lower()
                if ext not in self.SKIP_EXTS:
                    yield Path(dirpath) / fname

    def _rel(self, p: Path) -> str:
        return str(p.relative_to(self.root))

    def _add(self, sev, cat, path, line, desc, suggestion="", auto_fixable=False):
        self.result.findings.append(
            Finding(
                severity=sev,
                category=cat,
                file=self._rel(path),
                line=line,
                description=desc,
                suggestion=suggestion,
                auto_fixable=auto_fixable,
            )
        )

    def check_syntax(self):
        """Every .py file must parse cleanly."""
        for path in self._py_files():
            self.result.files_scanned += 1
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                self.result.lines_scanned += source.count("\n")
                ast.parse(source)
            except SyntaxError as e:
                self._add(
                    Severity.CRITICAL,
                    "QUALITY",
                    path,
                    e.lineno or 0,
                    f"Syntax error: {e.msg}",
                    "Fix syntax before release.",
                )

    def _version_subject_files(self):
        """Yield every file that could restate the application's version.

        Subjects are discovered, so a file that starts carrying a literal
        is swept the day it lands. Anything under ``VERSION_SKIP_DIRS`` is
        out of scope: a literal there reaches no surface that reports a
        version.
        """
        skip = self.SKIP_DIRS | self.VERSION_SKIP_DIRS
        for dirpath, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in skip]
            for fname in files:
                suffix = Path(fname).suffix.lower()
                if suffix in PYTHON_SUFFIXES or suffix in SCRIPT_SUFFIXES:
                    yield Path(dirpath) / fname

    def _shadow_literals(self, path: Path, source: str) -> list[ShadowLiteral]:
        """Return the shadow literals in one subject, or [] when it cannot parse."""
        if path.suffix.lower() not in PYTHON_SUFFIXES:
            return find_script_shadow_literals(source)
        try:
            return find_python_shadow_literals(source)
        except SyntaxError as syn:
            self._skipped.append((self._rel(path), f"SyntaxError: {syn}"))
            logger.warning(
                "version_sweep: %s failed to parse (%s) — EXCLUDED "
                "from the version check",
                path,
                syn,
            )
            return []

    def check_version_consistency(self):
        """Flag every version literal that can shadow the resolved version.

        A literal counts when it occupies a slot the resolved version fills:
        bound to a version-named identifier, defaulting a version parameter,
        answering an absent version key or option, or keying a version-info
        field of a build spec. An unresolvable version scores HIGH on its
        own, because a check that cannot name the value it compares against
        reports nothing in language identical to a clean run.
        """
        canonical = self.result.version
        if canonical == UNKNOWN_VERSION:
            self._add(
                Severity.HIGH,
                "CONSISTENCY",
                self.root / "src" / "_version.py",
                0,
                "Version unresolvable — no git commit and no baked stamp",
                "Run it in a git checkout; a baked stamp exists only in a bundle.",
            )

        for path in self._version_subject_files():
            source = self._read_or_skip(path)
            if source is None:
                continue
            for shadow in self._shadow_literals(path, source):
                self._add(
                    Severity.HIGH,
                    "CONSISTENCY",
                    path,
                    shadow.line,
                    f"Version literal {shadow.value!r} in {shadow.slot} "
                    f"{shadow.name!r} shadows the resolved version {canonical!r}",
                    "Read src.__version__ rather than restating the version.",
                )

        self._check_doc_versions(canonical)

    def _check_doc_versions(self, canonical: str) -> None:
        """Flag a doc naming a release of the current line that is not current.

        The release line comes from the resolved version, so the check
        follows the project across a major bump instead of watching one
        hardcoded major forever.
        """
        release_line = canonical.split(".", 1)[0]
        stale_pattern = re.compile(rf"\b{re.escape(release_line)}\.\d+\.\d+\b")
        for dpath in (self.root / "AI_DEVELOPER_GUIDE.md", self.root / "CHANGELOG.md"):
            if not dpath.exists():
                continue
            text = dpath.read_text(encoding="utf-8", errors="replace")
            stale = sorted(
                {v for v in stale_pattern.findall(text) if not canonical.startswith(v)}
            )
            if stale:
                self._add(
                    Severity.MEDIUM,
                    "CONSISTENCY",
                    dpath,
                    0,
                    f"Stale version reference(s) found: {stale}",
                    f"Update all to {canonical}.",
                )

    def check_secrets(self):
        """No hard-coded credentials or key material in source."""
        for path in self._all_files():
            text = self._read_or_skip(path)
            if text is None:
                continue

            rel = self._rel(path)
            skip_for_secret = {"encryption.py", "usb_auth.py"}
            skip_dirs_secret = {
                "docs",
                "deploy/kiosk",
                "contracts",
                "sadp",
                ".session26_backups",
            }
            skip_ext_secret = {".md", ".sol", ".txt", ".bak", ".jsonl"}
            if any(s in rel for s in skip_for_secret):
                continue
            if any(
                f"/{d}/" in f"/{rel}" or rel.startswith(f"{d}/")
                for d in skip_dirs_secret
            ):
                continue
            if Path(rel).suffix in skip_ext_secret:
                continue

            for line_no, line in enumerate(text.splitlines(), 1):
                for pattern, desc in self.SECRET_PATTERNS:
                    if re.search(pattern, line, re.I):
                        # Skip comments and test fixtures
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            continue
                        if "test" in rel.lower() or "example" in rel.lower():
                            sev = Severity.LOW
                        elif "PEM" in desc or "private key header" in desc:
                            sev = Severity.MEDIUM  # Could be format handling code
                        else:
                            sev = Severity.HIGH  # Real credential pattern
                        self._add(
                            sev,
                            "SECURITY",
                            path,
                            line_no,
                            desc,
                            "Move to encrypted vault or environment variable.",
                        )

    def check_insecure_patterns(self):
        """Flag ``INSECURE_PATTERNS`` matches in the files it scans.

        ``_visual_files``, test fixtures and version_sweep.py are skipped.
        """
        for path in self._py_files():
            text = self._read_or_skip(path)
            if text is None:
                continue

            rel = self._rel(path)
            # _visual_files use random.random for animation and white noise.
            _visual_files = {
                "splash_screen.py",
                "render_trailer.py",
                "sound_engine.py",  # audio white-noise generator
            }
            if path.name in _visual_files:
                continue
            _norm_rel = rel.replace("\\", "/")
            if _norm_rel.startswith("tests/") and (
                "investigate_" in path.name
                or "fixture" in path.name
                or "_test" in path.name
            ):
                continue
            # Self-exemption: version_sweep.py contains these patterns as data strings
            if "version_sweep.py" in rel:
                continue

            for line_no, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "# nosec" in line or "# version-sweep:" in line.lower():
                    continue
                for pattern, desc in self.INSECURE_PATTERNS:
                    if re.search(pattern, line):
                        if "random.random" in pattern and (
                            "gen_from_anchors" in text or "sim" in rel.lower()
                        ):
                            continue
                        sev = (
                            Severity.HIGH
                            if any(
                                x in desc
                                for x in ("key", "secret", "private", "injection")
                            )
                            else Severity.MEDIUM
                        )
                        self._add(
                            sev,
                            "SECURITY",
                            path,
                            line_no,
                            desc,
                            "Review and replace with secure alternative.",
                        )

    def check_debug_leftovers(self):
        for path in self._py_files():
            text = self._read_or_skip(path)
            if text is None:
                continue
            # DEBUG_PATTERNS strings would match themselves here.
            if "version_sweep.py" in self._rel(path):
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                for pattern, desc in self.DEBUG_PATTERNS:
                    if re.search(pattern, line, re.I):
                        self._add(
                            Severity.MEDIUM,
                            "HYGIENE",
                            path,
                            line_no,
                            desc,
                            "Remove before release.",
                            auto_fixable=False,
                        )

    def check_unused_imports(self):
        """Flag obviously unused top-level imports."""
        for path in self._py_files():
            source = self._read_or_skip(path)
            if source is None:
                continue
            try:
                tree = ast.parse(source)
            except SyntaxError as _syn:
                # A file that does not parse is excluded from every AST check.
                self._skipped.append((str(path), f"SyntaxError: {_syn}"))
                logger.warning(
                    "version_sweep: %s failed to parse (%s) — EXCLUDED "
                    "from AST checks",
                    path,
                    _syn,
                )
                continue

            imported_names = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        name = alias.asname or alias.name.split(".")[0]
                        imported_names.append((name, node.lineno))
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        name = alias.asname or alias.name
                        imported_names.append((name, node.lineno))

            # Count usages (rough — excludes __all__, string references)
            for name, lineno in imported_names:
                if name.startswith("_"):
                    continue
                # Count occurrences outside the import line itself
                occurrences = len(re.findall(r"\b" + re.escape(name) + r"\b", source))
                # The import line itself counts as 1; also __all__ re-exports
                if occurrences <= 1 and "__all__" not in source:
                    self._add(
                        Severity.LOW,
                        "QUALITY",
                        path,
                        lineno,
                        f"Possibly unused import: '{name}'",
                        "Remove if confirmed unused.",
                        auto_fixable=True,
                    )

    def check_r6_two_paths(self):
        """Compare the ``gate_pairs`` patterns across ``sim_path`` and ``bat_path``.

        Reports through ``_no_subject`` when either path is absent.
        """
        sim_path = self.root / "src" / "gui" / "simulator.py"
        bat_path = self.root / "sadp" / "RAIntSimBat" / "RAIntSimBat.py"

        for required in (sim_path, bat_path):
            if not required.exists():
                self._no_subject(f"{self._rel(required)} absent")
                return

        sim_text = sim_path.read_text(encoding="utf-8", errors="replace")
        bat_text = bat_path.read_text(encoding="utf-8", errors="replace")

        gate_pairs = [
            ("MACD TAPER", r"MACD.*taper|macd.*taper", r"macd_taper|MACD TAPER"),
            ("VX CEILING", r"vip_at_ceiling|VX.*CEIL", r"VX.*ceil|_vip_ceil"),
            ("ICHIMOKU GATE", r"ichi_twist_bull|ICHIMOKU", r"ICHIMOKU|_ichi_"),
            ("CM SLINGSHOT SQUEEZE", r"squeeze_bull|SLINGSHOT", r"SLINGSHOT|_sq_bull"),
        ]

        for name, sim_pat, bat_pat in gate_pairs:
            in_sim = bool(re.search(sim_pat, sim_text, re.I))
            in_bat = bool(re.search(bat_pat, bat_text, re.I))
            if in_sim and not in_bat:
                self._add(
                    Severity.HIGH,
                    "CONSISTENCY",
                    bat_path,
                    0,
                    f"R6 VIOLATION: {name} gate in simulator.py but NOT in RAIntSimBat.py",
                    "Add matching gate to run_v3192 or document intentional exclusion.",
                )
            elif in_bat and not in_sim:
                self._add(
                    Severity.HIGH,
                    "CONSISTENCY",
                    sim_path,
                    0,
                    f"R6 VIOLATION: {name} gate in RAIntSimBat.py but NOT in simulator.py",
                    "Add matching gate to simulator.py confidence pipeline.",
                )

    def check_requirements(self):
        """Check that key imports have entries in requirements files."""
        req_file = self.root / "requirements.txt"
        req_opt = self.root / "requirements-optional.txt"
        reqs_text = ""
        if req_file.exists():
            reqs_text += req_file.read_text(encoding="utf-8").lower()
        if req_opt.exists():
            reqs_text += req_opt.read_text(encoding="utf-8").lower()

        # Core dependencies that must be declared
        required_packages = {
            "PySide6": "pyside6",
            "ccxt": "ccxt",
            "reportlab": "reportlab",
            "cryptography": "cryptography",
        }

        for import_name, pkg_name in required_packages.items():
            if pkg_name not in reqs_text:
                # Check if it's actually imported
                used = False
                for path in self._py_files():
                    _probe = self._read_or_skip(path)
                    if _probe is None:
                        continue
                    if import_name in _probe:
                        used = True
                        break
                if used:
                    self._add(
                        Severity.MEDIUM,
                        "DEPENDENCY",
                        (
                            req_file
                            if req_file.exists()
                            else self.root / "requirements.txt"
                        ),
                        0,
                        f"'{import_name}' used in source but not in requirements files",
                        f"Add '{pkg_name}' to requirements.txt or requirements-optional.txt",
                    )

    def check_file_hygiene(self):
        """Flag stale artifacts that shouldn't ship."""
        stale_patterns = [
            (r"\.pyc$", "Compiled .pyc file should not be committed"),
            (r"__pycache__", "pycache directory should not be committed"),
            (r"\.DS_Store", "macOS metadata file should not be committed"),
            (r"Thumbs\.db", "Windows thumbnail cache should not be committed"),
            (r"\.env$", "Environment file may contain secrets"),
        ]
        for dirpath, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in {".git"}]
            for fname in files:
                fpath = Path(dirpath) / fname
                rel = self._rel(fpath)
                for pattern, desc in stale_patterns:
                    if re.search(pattern, rel):
                        self._add(
                            Severity.LOW,
                            "HYGIENE",
                            fpath,
                            0,
                            desc,
                            "Add to .gitignore and remove.",
                        )

    def check_snapshot_consistency(self):
        """Compare the snapshot keys read in ``sim_path`` against those it sets.

        Returns without a finding when ``sim_path`` is absent.
        """
        sim_path = self.root / "src" / "gui" / "simulator.py"
        if not sim_path.exists():
            return

        import re

        text = sim_path.read_text(encoding="utf-8", errors="replace")

        snap_pat = r"snapshot\s*=\s*\{(.+?)\}\s*\n\s*# Landing"
        snap_m = re.search(snap_pat, text, re.S)
        if not snap_m:
            self._add(
                Severity.MEDIUM,
                "CONSISTENCY",
                sim_path,
                0,
                "Could not locate snapshot dict in _compute_ta_snapshot()",
                "Verify snapshot = { ... } block is present.",
            )
            return

        set_keys = set(re.findall(r'"([a-z][a-z0-9_]+)":', snap_m.group(1)))

        # Keys READ in confidence gate code (after snapshot is built)
        # Look for ta.get("key") and ta["key"] patterns
        read_keys = set()
        read_keys.update(re.findall(r'ta\.get\("([a-z][a-z0-9_]+)"', text))
        read_keys.update(re.findall(r'ta\["([a-z][a-z0-9_]+)"\]', text))

        # Exclude non-indicator keys that are legitimately outside the snapshot
        exclude = {
            "signals",
            "consensus",
            "confidence",
            "bb",
            "bb_position",
            "idx",
            "tightening",
        }
        read_keys -= exclude

        missing = read_keys - set_keys
        # Filter to only indicator-style keys (exclude API/JSON keys)
        indicator_missing = {
            k
            for k in missing
            if any(
                k.startswith(p)
                for p in (
                    "ichi_",
                    "vx_",
                    "macd_",
                    "srsi_",
                    "mkt_",
                    "bb_",
                    "ha_",
                    "vol_",
                    "sling_",
                    "adx_",
                    "st_",
                    "z_",
                    "er_",
                )
            )
        }

        for key in sorted(indicator_missing):
            self._add(
                Severity.HIGH,
                "CONSISTENCY",
                sim_path,
                0,
                f"ta[{key!r}] read in gates but NOT in snapshot — "
                "gate branch silently returns None, indicator disabled",
                f"Add {key!r} to snapshot dict with correct ichi_d.get() source.",
            )

    def check_todos(self):
        total = 0
        for path in self._py_files():
            text = self._read_or_skip(path)
            if text is None:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if re.search(r"#\s*(TODO|FIXME|HACK|STUB)\b", line, re.I):
                    total += 1
                    self._add(
                        Severity.LOW,
                        "HYGIENE",
                        path,
                        line_no,
                        f"Unresolved {re.search(r'(TODO|FIXME|HACK|STUB)', line, re.I).group(1)}",
                        "Resolve or promote to Risk Register.",
                    )
        if total > 0:
            self._add(
                Severity.INFO,
                "HYGIENE",
                self.root / "src",
                0,
                f"Total unresolved TODO/FIXME/HACK/STUB comments: {total}",
                "Review before release.",
            )

    def check_rule_registry(self):
        """Flag every ``CORE`` entry of ``registry_path`` that is not locked.

        Adds an INFO finding when ``registry_path`` is absent.
        """
        registry_path = self.root / "sadp" / "RULE_REGISTRY.json"
        if not registry_path.exists():
            self._add(
                Severity.INFO,
                "CONSISTENCY",
                registry_path,
                0,
                "sadp/RULE_REGISTRY.json not found — will be created on first RULE command",
                "Run: python src/core/rule_registry.py",
            )
            return

        try:
            import json as _json

            data = _json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception as e:
            self._add(
                Severity.MEDIUM,
                "CONSISTENCY",
                registry_path,
                0,
                f"sadp/RULE_REGISTRY.json could not be parsed: {e}",
                "Delete sadp/RULE_REGISTRY.json and re-run: python src/core/rule_registry.py",
            )
            return

        CORE = {"R1", "R5", "R10", "R11", "R12"}

        for rule_id, entry in data.items():
            state = entry.get("state", "UNKNOWN")

            if rule_id in CORE and state != "LOCKED":
                self._add(
                    Severity.HIGH,
                    "CONSISTENCY",
                    registry_path,
                    0,
                    f"CORE rule {rule_id} is {state} — expected LOCKED. "
                    f"CORE rules encode the accumulation algorithm invariants.",
                    f"Run: RULE LOCK {rule_id}",
                )

            elif state == "SUSPENDED":
                reason = entry.get("reason", "no reason given")
                expires = entry.get("expires", "")
                exp_note = f" (expires {expires})" if expires else ""
                self._add(
                    Severity.MEDIUM,
                    "CONSISTENCY",
                    registry_path,
                    0,
                    f"{rule_id} is SUSPENDED{exp_note}: {reason}",
                    f"Run RULE RESTORE {rule_id} when suspension purpose is met.",
                )

            elif state == "UNLOCKED":
                reason = entry.get("reason", "no reason given")
                self._add(
                    Severity.LOW,
                    "CONSISTENCY",
                    registry_path,
                    0,
                    f"{rule_id} is UNLOCKED: {reason}",
                    f"Run RULE LOCK {rule_id} when modification is complete.",
                )

    def check_complexity_hotspots(self):
        """Report the ``scan_root`` functions with the most ``BRANCH_PAT`` matches."""
        import re as _re
        import ast as _ast

        BRANCH_PAT = _re.compile(r"\b(if|elif|for|while|except|and|or|case)\b")
        src_root = self.root / "src"
        scan_root = src_root if src_root.exists() else self.root
        for path in sorted(scan_root.rglob("*.py")):
            if "__pycache__" in str(path):
                continue
            text = self._read_or_skip(path)
            if text is None:
                continue
            try:
                tree = _ast.parse(text)
            except SyntaxError as _syn:
                self._skipped.append((str(path), f"SyntaxError: {_syn}"))
                logger.warning(
                    "version_sweep: %s failed to parse (%s) — EXCLUDED "
                    "from AST checks",
                    path,
                    _syn,
                )
                continue
            lines = text.split("\n")
            for node in _ast.walk(tree):
                if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    continue
                end = getattr(node, "end_lineno", node.lineno)
                length = end - node.lineno
                fn_src = "\n".join(lines[node.lineno - 1 : end])
                cc = len(BRANCH_PAT.findall(fn_src)) + 1
                if cc > 50:
                    self._add(
                        Severity.LOW,
                        "COMPLEXITY",
                        path,
                        node.lineno,
                        f"{node.name}() CC={cc} (R31 review threshold: 50) — {length} lines",
                        "Document in TECH_DEBT.md. Do not add new branches.",
                    )

    def run(self) -> SweepResult:
        t0 = time.time()
        print(f"\n{'='*68}")
        print(f"  ACERVATOR VERSION SWEEP  v{self.result.version}")
        print(f"  {self.result.timestamp}")
        print(f"{'='*68}")

        checks = [
            ("Syntax", self.check_syntax),
            ("Version consistency", self.check_version_consistency),
            ("Security — secrets", self.check_secrets),
            ("Security — patterns", self.check_insecure_patterns),
            ("Debug leftovers", self.check_debug_leftovers),
            ("Unused imports", self.check_unused_imports),
            ("R6 two-path (R6)", self.check_r6_two_paths),
            ("Requirements", self.check_requirements),
            ("File hygiene", self.check_file_hygiene),
            ("TODO/FIXME count", self.check_todos),
            ("Snapshot key sync", self.check_snapshot_consistency),
            ("Rule registry", self.check_rule_registry),
            ("Complexity hotspots", self.check_complexity_hotspots),
            ("SADP annotations (R38)", self.check_sadp_annotations),
            ("R28 silent failures", self.check_r28_silent_failures),
            ("R29/R33 gates", self.check_r29_r33_gates),
            ("SADP dep graph", self.check_sadp_dependency_graph),
        ]

        for name, fn in checks:
            print(f"  Checking: {name}...", end=" ", flush=True)
            before = len(self.result.findings)
            self._no_subject_reason = None
            fn()
            reason = self._no_subject_reason
            after = len(self.result.findings)
            new_count = after - before
            if reason is not None:
                self.result.not_inspected[name] = reason
                print(f"NOT INSPECTED ({reason})")
            elif new_count == 0:
                print("✓")
            else:
                sevs = [f.severity for f in self.result.findings[before:after]]
                worst = (
                    Severity.CRITICAL
                    if Severity.CRITICAL in sevs
                    else (
                        Severity.HIGH
                        if Severity.HIGH in sevs
                        else (
                            Severity.MEDIUM if Severity.MEDIUM in sevs else Severity.LOW
                        )
                    )
                )
                sym = {"CRITICAL": "✗", "HIGH": "⚠", "MEDIUM": "~", "LOW": "·"}
                print(
                    f"{sym.get(worst,'?')} ({new_count} finding{'s' if new_count != 1 else ''})"
                )

        self.result.elapsed_sec = round(time.time() - t0, 2)
        return self.result

    def check_sadp_annotations(self):
        """Check the ``ann_pat`` annotations against ``MANDATORY``.

        Suspended entries are read from ``registry_path``.
        """
        import re as _re, json as _json

        registry_path = self.root / "sadp" / "RULE_REGISTRY.json"
        try:
            registry = (
                _json.loads(registry_path.read_text(encoding="utf-8"))
                if registry_path.exists()
                else {}
            )
        except Exception:
            registry = {}
        suspended = {
            rid for rid, v in registry.items() if v.get("state") == "SUSPENDED"
        }
        ann_pat = _re.compile(r"#\s*sadp:\s*((?:R\d+\s*)+)", _re.IGNORECASE)
        fn_pat = _re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")
        MANDATORY = [
            ("simulator.py", "_sim_scrumming_tick"),
            ("scrumming_bot.py", "tick"),
            ("token_ledger.py", "award"),
            ("merkle_log.py", "append"),
            ("competition_engine.py", "adjudicate"),
        ]
        mandatory_found = {f"{f}:{fn}": False for f, fn in MANDATORY}
        annotation_count = 0
        for py_file in self.root.rglob("*.py"):
            if any(skip in py_file.parts for skip in self.SKIP_DIRS):
                continue
            _txt = self._read_or_skip(py_file)
            if _txt is None:
                continue
            lines = _txt.splitlines()
            current_fn = None
            for lineno, line in enumerate(lines, 1):
                fn_m = fn_pat.match(line)
                if fn_m:
                    current_fn = fn_m.group(1)
                ann_m = ann_pat.search(line)
                if not ann_m:
                    continue
                annotation_count += 1
                fname = py_file.name
                if current_fn:
                    key = f"{fname}:{current_fn}"
                    if key in mandatory_found:
                        mandatory_found[key] = True
                for rid in ann_m.group(1).split():
                    rid = rid.strip().upper()
                    if not rid:
                        continue
                    if rid not in registry:
                        self._add(
                            Severity.MEDIUM,
                            "SADP",
                            py_file,
                            lineno,
                            f"sadp annotation references unknown rule {rid} "
                            f"in {py_file.name}:{current_fn or chr(63)}",
                            f"Add {rid} to sadp/RULE_REGISTRY.json or correct annotation.",
                        )
                    elif rid in suspended:
                        self._add(
                            Severity.HIGH,
                            "SADP",
                            py_file,
                            lineno,
                            f"sadp annotation references SUSPENDED rule {rid} "
                            f"in {py_file.name}:{current_fn or chr(63)}",
                            f"Run RULE RESTORE {rid} or update the annotation.",
                        )
                    else:
                        self._add(
                            Severity.INFO,
                            "SADP",
                            py_file,
                            lineno,
                            f"sadp: {py_file.name}:{current_fn or chr(63)} governed by {rid}",
                            "",
                        )
        for key, found in mandatory_found.items():
            if not found:
                fname, fnname = key.split(":", 1)
                self._add(
                    Severity.HIGH,
                    "SADP",
                    self.root / fname,
                    0,
                    f"R38: mandatory sadp annotation missing on {fname}:{fnname}.",
                    f"Add  # sadp: R[N]...  comment inside {fnname}().",
                )
        if annotation_count:
            self._add(
                Severity.INFO,
                "SADP",
                self.root / "sadp" / "RULE_REGISTRY.json",
                0,
                f"SADP annotations: {annotation_count} found, all validated.",
                "",
            )

    def check_r28_silent_failures(self):
        """Flag ``bare_except`` and ``swallow_pass`` matches under ``SCOPED``."""
        import re as _re

        SCOPED = {"trading", "competition"}
        bare_except = _re.compile(r"^\s*except\s*:")
        swallow_pass = _re.compile(r"^\s*except\s+Exception.*:\s*pass\s*$")
        swallow_cont = _re.compile(r"^\s*except\s+Exception.*:\s*continue\s*$")
        silent_get = _re.compile(r"\.get\(([^,)]+),\s*None\s*\)")
        fn_pat = _re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")
        for py_file in self.root.rglob("*.py"):
            if any(skip in py_file.parts for skip in self.SKIP_DIRS):
                continue
            parts = [p.lower() for p in py_file.parts]
            if not any(d in parts for d in SCOPED):
                continue
            _txt = self._read_or_skip(py_file)
            if _txt is None:
                continue
            lines = _txt.splitlines()
            fn_ctx = ""
            for lineno, line in enumerate(lines, 1):
                fm = fn_pat.match(line)
                if fm:
                    fn_ctx = fm.group(1)
                if bare_except.match(line):
                    self._add(
                        Severity.HIGH,
                        "SADP-R28",
                        py_file,
                        lineno,
                        f"R28: bare except: in {py_file.name}:{fn_ctx} silences all exceptions.",
                        "Replace with explicit exception type.",
                    )
                elif swallow_pass.match(line) or swallow_cont.match(line):
                    self._add(
                        Severity.MEDIUM,
                        "SADP-R28",
                        py_file,
                        lineno,
                        f"R28: exception swallowed silently in {py_file.name}:{fn_ctx}",
                        "Log or re-raise.",
                    )
                gate_ctx = any(
                    k in fn_ctx.lower() for k in ("confidence", "gate", "tick")
                )
                if gate_ctx:
                    for m in silent_get.finditer(line):
                        self._add(
                            Severity.MEDIUM,
                            "SADP-R28",
                            py_file,
                            lineno,
                            f"R28: .get({m.group(1)}, None) in gate context "
                            f"{py_file.name}:{fn_ctx}",
                            "Use explicit key or safe non-None default.",
                        )

    def check_r29_r33_gates(self):
        """Flag ``submit_pat`` functions whose body has no ``idem_marker``.

        A ``log_fn_pat`` function matching ``trunc_pat`` is reported too.
        """
        import re as _re

        SCOPED = {"trading", "competition"}
        submit_pat = _re.compile(
            r"def\s+(submit_order|place_order|award|record_trade|submit_result)\s*\("
        )
        idem_marker = _re.compile(
            r"event_id|client_order_id|_seen|idempotent|already_done|duplicate"
        )
        trunc_pat = _re.compile(r"open\([^,)]+,[^)]*['\x22]w['\x22]|truncate\(")
        log_fn_pat = _re.compile(
            r"def\s+(write_log|append_log|save_log|_write|_append|_save)\s*\("
        )
        for py_file in self.root.rglob("*.py"):
            if any(skip in py_file.parts for skip in self.SKIP_DIRS):
                continue
            parts = [p.lower() for p in py_file.parts]
            if not any(d in parts for d in SCOPED):
                continue
            _txt = self._read_or_skip(py_file)
            if _txt is None:
                continue
            lines = _txt.splitlines()
            in_fn = False
            fn_name = ""
            fn_start = 0
            fn_body = []
            for lineno, line in enumerate(lines, 1):
                sm = submit_pat.search(line)
                if sm:
                    in_fn = True
                    fn_name = sm.group(1)
                    fn_start = lineno
                    fn_body = [line]
                elif in_fn:
                    fn_body.append(line)
                    if lineno > fn_start and line and not line[0].isspace():
                        body = "\n".join(fn_body)
                        if not idem_marker.search(body):
                            self._add(
                                Severity.MEDIUM,
                                "SADP-R29",
                                py_file,
                                fn_start,
                                f"R29: {py_file.name}:{fn_name} lacks visible "
                                f"idempotency marker.",
                                "Add event_id / client_order_id / _seen dedup logic.",
                            )
                        in_fn = False
            in_log = False
            log_name = ""
            log_start = 0
            for lineno, line in enumerate(lines, 1):
                lm = log_fn_pat.search(line)
                if lm:
                    in_log = True
                    log_name = lm.group(1)
                    log_start = lineno
                if in_log and trunc_pat.search(line):
                    self._add(
                        Severity.HIGH,
                        "SADP-R33",
                        py_file,
                        lineno,
                        f"R33: {py_file.name}:{log_name} truncates or overwrites log.",
                        "Use append-only writes.",
                    )
                if in_log and lineno > log_start and line and not line[0].isspace():
                    in_log = False

    def check_sadp_dependency_graph(self):
        """Flag every ``reverse`` entry depending on a suspended rule.

        Reports through ``_no_subject`` when ``registry_path`` is absent or
        unreadable.
        """
        import json as _json

        registry_path = self.root / "sadp" / "RULE_REGISTRY.json"
        rel = self._rel(registry_path)
        if not registry_path.exists():
            self._no_subject(f"{rel} absent")
            return
        try:
            registry = _json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self._no_subject(f"{rel} unreadable: {type(exc).__name__}")
            return
        suspended = {
            rid for rid, v in registry.items() if v.get("state") == "SUSPENDED"
        }
        if not suspended:
            return
        reverse = {}
        for rule_id, entry in registry.items():
            for dep in entry.get("depends_on", []):
                reverse.setdefault(dep, []).append(rule_id)
        for sus in suspended:
            for dep_rule in reverse.get(sus, []):
                dep_state = registry.get(dep_rule, {}).get("state", "UNKNOWN")
                self._add(
                    Severity.MEDIUM,
                    "SADP-DEP",
                    registry_path,
                    0,
                    f"Dep graph: {sus} SUSPENDED -> {dep_rule} ({dep_state}) "
                    f"depends on it and may be partially undermined.",
                    f"RULE RESTORE {sus} or review {dep_rule} compliance.",
                )

    def print_report(self, result: SweepResult):
        sev_order = [
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.LOW,
            Severity.INFO,
        ]
        sev_colour = {
            Severity.CRITICAL: "\033[91m",
            Severity.HIGH: "\033[93m",
            Severity.MEDIUM: "\033[94m",
            Severity.LOW: "\033[37m",
            Severity.INFO: "\033[90m",
        }
        RESET = "\033[0m"

        print(f"\n{'='*68}")
        print(f"  SWEEP RESULTS — {result.version}")
        print(
            f"  Files: {result.files_scanned}  Lines: {result.lines_scanned:,}  "
            f"Time: {result.elapsed_sec}s"
        )
        print(
            f"  CRITICAL: {len(result.critical)}  HIGH: {len(result.high)}  "
            f"MEDIUM: {len(result.medium)}  LOW: {len(result.low)}"
        )

        if result.passed:
            print("\n  \033[92m✓ SWEEP PASSED — release gate cleared\033[0m")
        else:
            print(
                f"\n  \033[91m✗ SWEEP FAILED — {len(result.critical)} critical, "
                f"{len(result.high)} high findings must be resolved\033[0m"
            )

        print(f"{'='*68}")

        if result.not_inspected:
            print(f"\n  ── NOT INSPECTED ({len(result.not_inspected)}) ──")
            for check_name, reason in result.not_inspected.items():
                print(f"  {check_name}: {reason}")

        for sev in sev_order:
            items = [f for f in result.findings if f.severity == sev]
            if not items:
                continue
            col = sev_colour.get(sev, "")
            print(f"\n  {col}── {sev} ({len(items)}) ──{RESET}")
            for f in items:
                loc = f"{f.file}:{f.line}" if f.line else f.file
                print(f"  {col}[{f.severity[:3]}]{RESET} {f.category} | {loc}")
                print(f"       {f.description}")
                if f.suggestion:
                    print(f"       → {f.suggestion}")

        print()

    def save_json_report(
        self, result: SweepResult, reports_dir: Optional[Path] = None
    ) -> Path:
        """Write machine-readable results and return the file written.

        ``reports_dir`` defaults to ``log_paths.get_reports_dir()``
        (``~/.acervator_logs/reports/``). Sweep output is generated, so it
        never lands under the repo root. Callers pass an explicit
        directory to write elsewhere.
        """
        reports_dir = reports_dir or get_reports_dir()
        reports_dir.mkdir(parents=True, exist_ok=True)
        fname = f"sweep_v{result.version}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        out = reports_dir / fname
        data = {
            "version": result.version,
            "timestamp": result.timestamp,
            "elapsed_sec": result.elapsed_sec,
            "files_scanned": result.files_scanned,
            "lines_scanned": result.lines_scanned,
            "passed": result.passed,
            "not_inspected": dict(result.not_inspected),
            "summary": {
                "critical": len(result.critical),
                "high": len(result.high),
                "medium": len(result.medium),
                "low": len(result.low),
            },
            "findings": [
                {
                    "severity": f.severity,
                    "category": f.category,
                    "file": f.file,
                    "line": f.line,
                    "description": f.description,
                    "suggestion": f.suggestion,
                }
                for f in result.findings
            ],
        }
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return out

    def save_pdf_report(
        self, result: SweepResult, reports_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """Render a PDF sweep report, or None when reportlab is absent.

        Same destination rule as ``save_json_report``: generated output
        defaults to ``log_paths.get_reports_dir()``, never the repo tree.
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.colors import HexColor, white
            from reportlab.lib.units import mm
            from reportlab.platypus import (
                Flowable,
                SimpleDocTemplate,
                Paragraph,
                Table,
                TableStyle,
            )
        except ImportError:
            return None

        reports_dir = reports_dir or get_reports_dir()
        reports_dir.mkdir(parents=True, exist_ok=True)
        fname = f"acervator_sweep_v{result.version}_{time.strftime('%Y%m%d')}.pdf"
        out = reports_dir / fname

        DARK = HexColor("#0A0A14")
        CYAN = HexColor("#00CCAA")
        LIGHT = HexColor("#C8D8F0")
        GREY = HexColor("#667799")
        RED = HexColor("#FF4444")
        GOLD = HexColor("#FFB800")

        def S(name, **kw):
            return ParagraphStyle(name, **kw)

        SS = {
            "Title": S(
                "Title",
                fontName="Helvetica-Bold",
                fontSize=16,
                textColor=CYAN,
                spaceAfter=4,
            ),
            "Sub": S(
                "Sub", fontName="Helvetica", fontSize=9, textColor=GREY, spaceAfter=12
            ),
            "SH": S(
                "SH",
                fontName="Helvetica-Bold",
                fontSize=11,
                textColor=CYAN,
                spaceBefore=10,
                spaceAfter=4,
            ),
            "Body": S(
                "Body",
                fontName="Helvetica",
                fontSize=8,
                textColor=LIGHT,
                spaceAfter=3,
                leading=12,
            ),
        }

        MARGIN = 18 * mm
        W, H = A4
        usable_w = W - 2 * MARGIN

        def on_page(c, doc):
            c.saveState()
            c.setFillColor(DARK)
            c.rect(0, 0, W, H, fill=1, stroke=0)
            c.setFont("Helvetica", 6)
            c.setFillColor(GREY)
            c.drawString(
                MARGIN,
                8 * mm,
                f"Acervator v{result.version} — Security & Optimization Sweep",
            )
            c.drawRightString(W - MARGIN, 8 * mm, f"Page {doc.page}")
            c.restoreState()

        story: list[Flowable] = [
            Paragraph(
                f"Acervator v{result.version} — Version Sweep Report", SS["Title"]
            ),
            Paragraph(
                f"{result.timestamp}  ·  "
                f"{result.files_scanned} files  ·  {result.lines_scanned:,} lines  ·  "
                f"{result.elapsed_sec}s",
                SS["Sub"],
            ),
        ]

        # Summary table
        pass_str = "✓ PASSED" if result.passed else "✗ FAILED"
        pass_col = CYAN if result.passed else RED
        summary_data = [
            ["Result", "Critical", "High", "Medium", "Low"],
            [
                pass_str,
                str(len(result.critical)),
                str(len(result.high)),
                str(len(result.medium)),
                str(len(result.low)),
            ],
        ]
        st = Table(summary_data, colWidths=[usable_w * 0.4] + [usable_w * 0.15] * 4)
        st.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#151530")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), white),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("TEXTCOLOR", (0, 1), (0, 1), pass_col),
                    ("FONTNAME", (0, 1), (0, 1), "Helvetica-Bold"),
                    ("TEXTCOLOR", (1, 1), (-1, 1), LIGHT),
                    ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#2a2a5f")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#0C0C18")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(st)

        # Findings by severity
        sev_order = [
            ("CRITICAL", RED),
            ("HIGH", GOLD),
            ("MEDIUM", CYAN),
            ("LOW", GREY),
            ("INFO", GREY),
        ]

        for sev, col in sev_order:
            items = [f for f in result.findings if f.severity == sev]
            if not items:
                continue
            story.append(
                Paragraph(
                    f"{sev} — {len(items)} finding{'s' if len(items)!=1 else ''}",
                    SS["SH"],
                )
            )
            rows: list[list[Flowable | str]] = [
                ["Category", "File", "Line", "Description"]
            ]
            for f in items:
                rows.append(
                    [
                        Paragraph(f.category, SS["Body"]),
                        Paragraph(
                            f.file[-40:] if len(f.file) > 40 else f.file, SS["Body"]
                        ),
                        Paragraph(str(f.line) if f.line else "—", SS["Body"]),
                        Paragraph(f.description[:80], SS["Body"]),
                    ]
                )
            ft = Table(rows, colWidths=[60, 130, 30, usable_w - 230])
            ft.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#151530")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), white),
                        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 7),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [HexColor("#0C0C18"), HexColor("#0A0A14")],
                        ),
                        ("TEXTCOLOR", (0, 1), (-1, -1), LIGHT),
                        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#2a2a5f")),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(ft)

        doc = SimpleDocTemplate(
            str(out),
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=16 * mm,
        )
        doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
        return out


def _force_utf8_stdio() -> None:
    """Set stdout/stderr to UTF-8 for the CLI run.

    ``print_report`` writes U+2713 and box-drawing characters. On a cp1252
    console those raise UnicodeEncodeError mid-sweep, so the run aborts
    before any report is written.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Acervator version bump quality gate sweep"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Accepted for compatibility; no finding is applied",
    )
    parser.add_argument(
        "--report", action="store_true", help="Generate PDF report (requires reportlab)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Accepted for compatibility; the JSON report is always written",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        help="Report destination (default: ~/.acervator_logs/reports/)",
    )
    args = parser.parse_args()

    _force_utf8_stdio()

    sweep = VersionSweep(root=ROOT, fix=args.fix)
    result = sweep.run()
    sweep.print_report(result)

    json_path = sweep.save_json_report(result, reports_dir=args.reports_dir)
    print(f"  JSON report: {json_path}")

    if args.report:
        pdf_path = sweep.save_pdf_report(result, reports_dir=args.reports_dir)
        if pdf_path:
            print(f"  PDF report:  {pdf_path}")
        else:
            print("  PDF report:  reportlab not available")

    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
