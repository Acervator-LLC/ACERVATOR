"""TruthArchetype — resolves the checkable claims in a text against the tree.

`review` reads one Markdown or text target and reports `T001` through `T006`
for a citation, a count, a runtime claim or a proxy claim the tree contradicts.
`T000` records a claim this archetype identified and could not decide, so an
undecided claim is never silent.
"""

from __future__ import annotations

import ast
import bisect
import builtins
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from dev_harness.harness.report import (
    REPO_ROOT,
    ArchetypeReport,
    Finding,
    cli_exit,
)

__all__ = ["ArchetypeReport", "Finding", "TruthArchetype", "main"]


HANDLED_SUFFIXES: tuple[str, ...] = (".md", ".markdown", ".txt")

_SKIP_DIRS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)

_PY_SUFFIXES = (".py", ".pyi", ".pyw")
_FOREIGN_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")

# A workflow key, a settings key and a package field are names the tree carries
# outside any Python or JavaScript source.
_CONFIG_SUFFIXES = (".json", ".toml", ".yml", ".yaml", ".cfg", ".ini")

_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")

# An emitter pin name, an event topic and a settings key reach the tree only as
# a string constant, so a def/class index alone cannot see them.
_STRING_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'`(\[])")

# A bullet starts its own claim. Joining a list into one paragraph made the
# co-occurrence window for T006 span unrelated sentences.
_LIST_MARKER = re.compile(r"^(?:[-*+]\s|\d+[.)]\s)")

_FILE_EXTENSIONS = (
    "py|pyi|pyw|md|markdown|json|jsonl|toml|yaml|yml|txt|log|csv"
    "|js|jsx|mjs|cjs|ts|tsx|html|css|ini|cfg|sh|ps1|spec"
)
_PATH_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_/\\.:])"
    r"[A-Za-z0-9_][A-Za-z0-9_\-./\\]*\.(?:" + _FILE_EXTENSIONS + r")\b"
)

# A trailing hex character means the token is a colour, not a citation:
# `#141420` read as issue 141420 drew 36 findings on one inventory page.
_ISSUE_TOKEN = re.compile(r"(?<![A-Za-z0-9_/#])#(\d{1,4})(?![0-9a-fA-F])\b")
_ISSUE_WORD = re.compile(r"\bissues?\s+#?(\d{1,6})\b", re.IGNORECASE)

# A line carrying one of these already claims the path is gone, so T001 saying
# the same thing is agreement, not a finding.
_ABSENCE_MARKER = re.compile(
    r"\bdoes not exist\b|\bdo not exist\b|\bdeleted\b|\bgone\b|\bretired\b"
    r"|\bremoved\b|\bmissing\b|\bhallucinat|\bnever existed\b|\bno such\b"
    r"|\bdead\b|\bnot on disk\b|\bno longer\b",
    re.IGNORECASE,
)

_ISSUE_STATE = re.compile(
    r"#?(\d{1,6})\s*(?:is|was|remains|:|\(|—|--?)\s*(open|closed)\b",
    re.IGNORECASE,
)

_LINE_COUNT = re.compile(r"\b(\d[\d,]*)\s+lines\b", re.IGNORECASE)
_FILE_COUNT = re.compile(
    r"\b(\d[\d,]*)\s+(?:([A-Za-z.]+)\s+)?files\b",
    re.IGNORECASE,
)
_COUNT_CLAIM = re.compile(r"\b\d[\d,]*\s+[a-z][a-z_]{2,}s\b")

# A line citing line numbers can state a distance between them, which is not
# the length of any file.
_SPAN_CONTEXT = re.compile(
    r"\.[A-Za-z]{2,4}:\d|:\d+\s*-\s*\d+|\bapart\b|\bbetween\b|\bspan\b"
    r"|\bdistance\b|\blines? \d+\b",
    re.IGNORECASE,
)

# A count in the past tense describes a tree that is gone, so recounting the
# tree that exists now answers a different question.
_HISTORICAL_COUNT = re.compile(
    r"\bfell\b|\brose\b|\bgrew\b|\bshrank\b|\bwas\b|\bwere\b|\bhad\b"
    r"|\bused to\b|\bpreviously\b|\bformerly\b|\bbefore\b|\bonce\b"
    r"|\b(?:down|up|fallen|risen)\s+from\b|\bfrom\s+[\d,]+\s"
    r"|\btoday\b|\byesterday\b"
    r"|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
    re.IGNORECASE,
)

# The count and the path it describes sit close together in every true case
# measured; a wide gap means the two sat in different table cells.
_COUNT_SUBJECT_GAP = 60


# `runs`, `ran` and `draws` are left out on purpose: measured over 56 documents
# they matched descriptive prose 130 times and an observed run almost never.
_RUNTIME_CLAIM = re.compile(
    r"\brenders?\b|\brendered\b"
    r"|\b(?:is|are|was|were)\s+displayed\b"
    r"|\b(?:the operator|the user|he|she)\s+sees\b",
    re.IGNORECASE,
)
_RUNTIME_EVIDENCE = re.compile(
    r"\bscreenshot\b|\.png\b|\.jpg\b|\bpixel\b|\bgrab\(|\bQImage\b"
    r"|\.log\b|\bgate\.log\b|\blog line\b|\blog lines\b|\bconsole\b|\bstdout\b"
    r"|\bexit code\b|\bexit \d\b|\bpytest\b|\btraceback\b|\bcaptured\b"
    r"|\bobserved\b|\bmeasured\b|\bdriven\b|\brecording\b|\bframe\b"
    r"|\brun id\b|\bverified by\b|\bI ran\b|\bwe ran\b|\bwas run\b"
    r"|\bmeasurement\b",
    re.IGNORECASE,
)

# `the rendered page` and `an old render` name a thing, not an event.
_DETERMINER = re.compile(
    r"\b(?:a|an|the|that|this|one|old|new|each|its|their|his|her|every)\s+$",
    re.IGNORECASE,
)
_CLAIM_SOFTENER = re.compile(
    r"\bwill\b|\bwould\b|\bshould\b|\bmust\b|\bmay\b|\bcan\b|\bcould\b"
    r"|\bif\b|\bwhen\b|\bonce\b|\buntil\b|\bwhether\b"
    r"|\bnot\b|\bnever\b|\bno\b|\bnowhere\b|\bcannot\b|\bfails\b|\bfailed\b",
    re.IGNORECASE,
)

_COMPLETION_WORD = re.compile(
    r"\bconverted\b|\bcomplete\b|\bcompleted\b|\bdone\b|\bshipped\b"
    r"|\bfinished\b|\bimplemented\b|\bwired\b|\bworks\b|\bworking\b"
    r"|\bin place\b|\blanded\b|\binstalled\b",
    re.IGNORECASE,
)

# The five proxy families the truth-check skill measured: a name, a registry
# entry, a comparison, a count of code written, and a green.
_PROXY_EVIDENCE = re.compile(
    r"\bthe name\b|\bits name\b|\bthe file ?name\b|\bthe variant\b"
    r"|\bthe flag\b|\bthe label\b|\bthe executable\b"
    r"|\bmanifest\b|\bregistry\b|\bdeclared\b|\bdeclaration\b"
    r"|\bconfig entry\b|\bthe entry\b|\blockfile\b|\blisted in\b"
    r"|\bthe file exists\b|\bexists on disk\b"
    r"|\bparity test\b|\bcomparison\b|\btwo descriptions\b"
    r"|\bmodules written\b|\bfiles written\b|\blines written\b"
    r"|\btests? pass(?:es|ing)?\b|\bpassing tests?\b",
    re.IGNORECASE,
)
_GREEN_CLAIM = re.compile(
    r"\bpassed=True\b|\bpass(?:ed|es)\b|\bgreen\b|\bexit 0\b|\ball tests? pass",
    re.IGNORECASE,
)

# `passes the key on` is not a verdict. A green claim needs a thing that judges.
_CHECK_SUBJECT = re.compile(
    r"\bgate\b|\btests?\b|\bcheck(?:s)?\b|\bsuite\b|\bcontrol\b|\barchetype\b"
    r"|\bCI\b|\blint\b|\bpytest\b|\bblack\b|\bflake8\b"
    r"|\bfixture\b|\bassertion\b",
    re.IGNORECASE,
)
_RED_EVIDENCE = re.compile(
    r"\bred\b|\bfails\b|\bfailed\b|\bfailing\b|\bexit 1\b|\bexit 2\b"
    r"|\bknown_bad\b|\bpassed=False\b|\bdid not pass\b|\bpositive control\b"
    r"|\bcontrol\b|\bwent red\b|\bnot green\b",
    re.IGNORECASE,
)

_PY_RESERVED = frozenset(dir(builtins))

_GH_LIST_LIMIT = 1000

# A merged pull request is not open, and T003 compares against open or closed.
_STATE_ALIASES = {"MERGED": "CLOSED"}


@dataclass
class _Sentence:
    """One prose sentence with the source line its first character sits on."""

    line: int
    text: str


@dataclass
class _TreeIndex:
    """Names defined and names mentioned across the repository sources."""

    definitions: set[str] = field(default_factory=set)
    python_names: set[str] = field(default_factory=set)
    string_names: set[str] = field(default_factory=set)
    foreign_names: set[str] = field(default_factory=set)
    python_files: int = 0
    parse_failures: int = 0

    def mentions(self, name: str) -> bool:
        """True when `name` occurs anywhere outside `definitions`."""
        return (
            name in self.python_names
            or name in self.string_names
            or name in self.foreign_names
        )


def _fenced_lines(text: str) -> set[int]:
    """Return the 1-based line numbers of fence markers and fenced content."""
    inside: set[int] = set()
    in_fence = False
    for lineno, raw in enumerate(text.split("\n"), start=1):
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            inside.add(lineno)
            continue
        if in_fence:
            inside.add(lineno)
    return inside


def _prose_sentences(text: str) -> list[_Sentence]:
    """Return the prose sentences outside fences, tables and block quotes."""
    fenced = _fenced_lines(text)
    out: list[_Sentence] = []
    block: list[tuple[int, str]] = []

    def flush() -> None:
        if not block:
            return
        joined = ""
        offsets: list[int] = []
        lines: list[int] = []
        for lineno, body in block:
            offsets.append(len(joined))
            lines.append(lineno)
            joined += body + " "
        joined = joined.rstrip()
        start = 0
        pieces: list[tuple[int, str]] = []
        for match in _SENTENCE_BREAK.finditer(joined):
            pieces.append((start, joined[start : match.start()]))
            start = match.end()
        if joined[start:].strip():
            pieces.append((start, joined[start:]))
        for offset, piece in pieces:
            index = bisect.bisect_right(offsets, offset) - 1
            out.append(_Sentence(line=lines[max(index, 0)], text=piece.strip()))
        block.clear()

    for lineno, raw in enumerate(text.split("\n"), start=1):
        stripped = raw.strip()
        if lineno in fenced or not stripped:
            flush()
            continue
        if stripped.startswith(("|", ">", "#")) or _LIST_MARKER.match(stripped):
            flush()
            if stripped.startswith(("|", ">", "#")):
                continue
        block.append((lineno, _INLINE_CODE_RE.sub(" ", stripped)))
    flush()
    return out


def _iter_sources(root: Path) -> Iterator[Path]:
    """Yield every file under `root`, skipping the `_SKIP_DIRS` names."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def _collect_python(tree: ast.AST, index: _TreeIndex) -> None:
    """Add every definition name and every bound name in `tree` to `index`."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            index.definitions.add(node.name)
            index.python_names.add(node.name)
            args = getattr(node, "args", None)
            if args is not None:
                for group in (args.args, args.posonlyargs, args.kwonlyargs):
                    index.python_names.update(a.arg for a in group)
        elif isinstance(node, ast.Name):
            index.python_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            index.python_names.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            index.python_names.update((node.module or "").split("."))
        elif isinstance(node, ast.alias):
            index.python_names.add((node.asname or node.name).split(".")[0])
            index.python_names.add(node.name.split(".")[-1])
        elif isinstance(node, ast.keyword) and node.arg:
            index.python_names.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            index.string_names.update(_STRING_NAME_RE.findall(node.value))


def build_tree_index(root: Path) -> _TreeIndex:
    """Return the definition and name index for every source under `root`."""
    index = _TreeIndex()
    for path in _iter_sources(root):
        suffix = path.suffix.lower()
        if suffix in _PY_SUFFIXES:
            index.python_names.add(path.stem)
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
                _collect_python(ast.parse(source, filename=str(path)), index)
            except (OSError, SyntaxError, ValueError, RecursionError):
                index.parse_failures += 1
                continue
            index.python_files += 1
        elif suffix in _FOREIGN_SUFFIXES:
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            index.foreign_names.update(_IDENT_RE.findall(source))
        elif suffix in _CONFIG_SUFFIXES:
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            index.string_names.update(_STRING_NAME_RE.findall(source))
    return index


class TruthArchetype:
    """Resolves a text's claims against the tree, and names the undecidable.

    `review` runs the six analyzers named in `tools` over one Markdown or text
    target.
    """

    name = "claim_truth"
    version = "1.0"
    tools = (
        "paths",
        "symbols",
        "issues",
        "counts",
        "runtime_claims",
        "proxy_claims",
    )

    def __init__(self, root: Path | None = None) -> None:
        """Bind the tree `root` every claim is resolved against."""
        self.root = Path(root or REPO_ROOT).resolve()
        self._index: _TreeIndex | None = None
        self._top_level: set[str] | None = None

    def index(self) -> _TreeIndex:
        """Return the tree index, building it on first use."""
        if self._index is None:
            self._index = build_tree_index(self.root)
        return self._index

    def top_level(self) -> set[str]:
        """Return the names of the entries directly under the repository root."""
        if self._top_level is None:
            try:
                self._top_level = {p.name for p in self.root.iterdir()}
            except OSError:
                self._top_level = set()
        return self._top_level

    def review(self, target: Path) -> ArchetypeReport:
        """Return the claim report for one text file or one directory."""
        target = Path(target).resolve()
        report = ArchetypeReport(target=str(target))
        if not target.exists():
            report.errors.append(f"target not found: {target}")
            report.falsification = self._falsification(report, None)
            return report
        if target.is_file() and target.suffix.lower() not in HANDLED_SUFFIXES:
            report.language = target.suffix.lower().lstrip(".") or "unknown"
            report.unhandled = True
            report.falsification = self._unhandled_falsification(report)
            return report

        files = self._enumerate(target)
        if not files:
            report.errors.append(f"no markdown/text files at: {target}")
            report.falsification = self._falsification(report, None)
            return report
        report.scanned = True

        for tool_name, runner in (
            ("paths", self._run_paths),
            ("symbols", self._run_symbols),
            ("issues", self._run_issues),
            ("counts", self._run_counts),
            ("runtime_claims", self._run_runtime_claims),
            ("proxy_claims", self._run_proxy_claims),
        ):
            try:
                findings, status = runner(files)
                report.findings.extend(findings)
                report.tool_availability[tool_name] = status
            except subprocess.TimeoutExpired:
                report.tool_availability[tool_name] = "error"
                report.errors.append(f"{tool_name}: timed out")
            except Exception as exc:
                report.tool_availability[tool_name] = "error"
                report.errors.append(f"{tool_name}: {type(exc).__name__}: {exc}")

        report.falsification = self._falsification(report, self._index)
        return report

    def _enumerate(self, target: Path) -> list[Path]:
        if target.is_file():
            return [target]
        found = [
            path
            for path in _iter_sources(target)
            if path.suffix.lower() in HANDLED_SUFFIXES
        ]
        return sorted(found)

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _undecided(path: Path, line: int, rule: str, message: str) -> Finding:
        return Finding(
            tool="truth",
            severity="info",
            file=str(path),
            line=line,
            rule_id="T000",
            message=f"UNDECIDED ({rule}): {message}",
        )

    def _resolve_path(self, raw: str) -> Path | None:
        norm = raw.replace("\\", "/").strip().rstrip(".,;:)]}")
        if "/" not in norm or "://" in norm or norm.startswith(("/", "~", ".")):
            return None
        head = norm.split("/", 1)[0]
        if head not in self.top_level():
            return None
        candidate = (self.root / norm).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            return None
        return candidate

    def _run_paths(self, files: list[Path]) -> tuple[list[Finding], str]:
        findings: list[Finding] = []
        for path in files:
            seen: set[tuple[int, str]] = set()
            for lineno, raw in enumerate(self._read(path).split("\n"), start=1):
                says_absent = bool(_ABSENCE_MARKER.search(raw))
                for match in _PATH_TOKEN.finditer(raw):
                    token = match.group(0)
                    resolved = self._resolve_path(token)
                    if resolved is None or resolved.exists():
                        continue
                    key = (lineno, token)
                    if key in seen:
                        continue
                    seen.add(key)
                    if says_absent:
                        findings.append(
                            self._undecided(
                                path,
                                lineno,
                                "T001",
                                f"{token!r} is absent and the line already says "
                                f"so, which is agreement rather than a finding.",
                            )
                        )
                        continue
                    findings.append(
                        Finding(
                            tool="truth",
                            severity="high",
                            file=str(path),
                            line=lineno,
                            rule_id="T001",
                            message=(
                                f"cited path {token!r} does not exist under "
                                f"{self.root.name}. Any claim resting on it "
                                f"cannot be true as written."
                            ),
                        )
                    )
        return findings, "ok"

    def _symbol_candidates(self, text: str) -> list[tuple[int, str]]:
        """Return (line, name) for every inline span shaped like a definition."""
        out: list[tuple[int, str]] = []
        for lineno, raw in enumerate(text.split("\n"), start=1):
            for match in _INLINE_CODE_RE.finditer(raw):
                span = match.group(1).strip().removesuffix("()")
                if not span or any(c in span for c in "/\\ "):
                    continue
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*", span):
                    continue
                name = span.split(".")[-1]
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                    continue
                if name in _PY_RESERVED or name.isupper():
                    continue
                snake = "_" in name and name.lower() == name
                camel = bool(re.fullmatch(r"[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*", name))
                if snake or camel:
                    out.append((lineno, name))
        return out

    def _run_symbols(self, files: list[Path]) -> tuple[list[Finding], str]:
        index = self.index()
        if index.python_files == 0:
            return [], "error: no python source indexed"
        findings: list[Finding] = []
        for path in files:
            seen: set[str] = set()
            for lineno, name in self._symbol_candidates(self._read(path)):
                if name in index.definitions or name in seen:
                    continue
                seen.add(name)
                if index.mentions(name):
                    findings.append(
                        self._undecided(
                            path,
                            lineno,
                            "T002",
                            f"{name!r} has no def or class in the tree and does "
                            f"occur as a name. An alias, an attribute, a pin "
                            f"name and a foreign symbol are not told apart here.",
                        )
                    )
                    continue
                findings.append(
                    Finding(
                        tool="truth",
                        severity="high",
                        file=str(path),
                        line=lineno,
                        rule_id="T002",
                        message=(
                            f"cited symbol {name!r} has no def or class in the "
                            f"tree, and occurs in no Python name, no string "
                            f"constant and no JavaScript name. Four instruments "
                            f"agree it does not exist."
                        ),
                    )
                )
        return findings, "ok"

    def _issue_states(self) -> tuple[dict[int, str], str, bool]:
        """Return `states`, an explanation for an empty one, and truncation.

        `truncated` is True when the listing reached `limit`.
        """
        binary = shutil.which("gh")
        if binary is None:
            return {}, "gh is not on PATH", False
        states: dict[int, str] = {}
        truncated = False
        for kind in ("issue", "pr"):
            rows, reason = self._gh_list(binary, kind)
            if reason:
                return {}, reason, False
            states.update({int(r["number"]): str(r["state"]).upper() for r in rows})
            truncated = truncated or len(rows) >= _GH_LIST_LIMIT
        return states, "", truncated

    def _gh_list(self, binary: str, kind: str) -> tuple[list[dict], str]:
        """Return the `gh <kind> list` rows, or an explanation for none.

        Issues and pull requests share one number space in this repository, so
        `_issue_states` unions both.
        """
        proc = subprocess.run(  # noqa: S603
            [
                binary,
                kind,
                "list",
                "--state",
                "all",
                "--limit",
                str(_GH_LIST_LIMIT),
                "--json",
                "number,state",
            ],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip().replace("\n", " ")[:200]
            return [], f"gh {kind} list exited {proc.returncode}: {detail}"
        try:
            return json.loads(proc.stdout or "[]"), ""
        except json.JSONDecodeError as exc:
            return [], f"gh {kind} list output did not parse: {exc}"

    def _cited_issues(self, files: list[Path]) -> list[tuple[Path, int, int, str]]:
        """Return (file, line, number, line text) for every issue citation."""
        cited: list[tuple[Path, int, int, str]] = []
        for path in files:
            for lineno, raw in enumerate(self._read(path).split("\n"), start=1):
                numbers = {int(m.group(1)) for m in _ISSUE_TOKEN.finditer(raw)}
                numbers |= {int(m.group(1)) for m in _ISSUE_WORD.finditer(raw)}
                cited.extend((path, lineno, number, raw) for number in sorted(numbers))
        return cited

    def _run_issues(self, files: list[Path]) -> tuple[list[Finding], str]:
        cited = self._cited_issues(files)
        if not cited:
            return [], "ok"
        states, reason, truncated = self._issue_states()
        if not states:
            return [
                self._undecided(
                    cited[0][0],
                    cited[0][1],
                    "T003",
                    f"{len(cited)} issue citation(s) stayed unresolved: {reason}.",
                )
            ], f"unavailable: {reason}"

        findings: list[Finding] = []
        reported: set[tuple[str, int]] = set()
        for path, lineno, number, raw in cited:
            state = states.get(number)
            if state is None:
                if truncated:
                    findings.append(
                        self._undecided(
                            path,
                            lineno,
                            "T003",
                            f"issue {number} is absent from a truncated listing, "
                            f"so its absence is a fact about the listing.",
                        )
                    )
                    continue
                key = (str(path), number)
                if key in reported:
                    continue
                reported.add(key)
                findings.append(
                    Finding(
                        tool="truth",
                        severity="high",
                        file=str(path),
                        line=lineno,
                        rule_id="T003",
                        message=(
                            f"cited issue {number} does not exist in this "
                            f"repository. The listing holds {len(states)} "
                            f"issue and pull-request numbers."
                        ),
                    )
                )
                continue
            for match in _ISSUE_STATE.finditer(raw):
                if int(match.group(1)) != number:
                    continue
                claimed = match.group(2).upper()
                actual = _STATE_ALIASES.get(state, state)
                if claimed != actual:
                    findings.append(
                        Finding(
                            tool="truth",
                            severity="high",
                            file=str(path),
                            line=lineno,
                            rule_id="T003",
                            message=(
                                f"number {number} is stated as "
                                f"{claimed.lower()} and the repository reports "
                                f"it {state.lower()}."
                            ),
                        )
                    )
        return findings, "ok"

    def _single_path(self, raw: str, span: tuple[int, int]) -> tuple[Path | None, int]:
        """Return the one path within `_COUNT_SUBJECT_GAP` of `span`."""
        resolved = []
        for match in _PATH_TOKEN.finditer(raw):
            gap = max(span[0] - match.end(), match.start() - span[1], 0)
            found = self._resolve_path(match.group(0))
            if found is not None and gap <= _COUNT_SUBJECT_GAP:
                resolved.append(found)
        unique = sorted({str(p) for p in resolved})
        return (Path(unique[0]), 1) if len(unique) == 1 else (None, len(unique))

    def _check_line_count(
        self, path: Path, lineno: int, raw: str, stated: int, span: tuple[int, int]
    ) -> tuple[Finding, bool]:
        cited, how_many = self._single_path(raw, span)
        if cited is None:
            return (
                self._undecided(
                    path,
                    lineno,
                    "T004",
                    f"a claim of {stated} lines names {how_many} resolvable "
                    f"paths, so the count has no single subject.",
                ),
                False,
            )
        if not cited.is_file():
            return (
                self._undecided(
                    path,
                    lineno,
                    "T004",
                    f"a claim of {stated} lines names {cited.name}, which is not "
                    f"a file on disk.",
                ),
                False,
            )
        actual = len(cited.read_text(encoding="utf-8", errors="replace").splitlines())
        if actual == stated:
            return (
                self._undecided(
                    path,
                    lineno,
                    "T004",
                    f"{cited.name} holds {actual} lines, matching the stated "
                    f"count.",
                ),
                True,
            )
        return (
            Finding(
                tool="truth",
                severity="high",
                file=str(path),
                line=lineno,
                rule_id="T004",
                message=(
                    f"stated {stated} lines for {cited.name}; recounted now it "
                    f"holds {actual}."
                ),
            ),
            True,
        )

    def _run_counts(self, files: list[Path]) -> tuple[list[Finding], str]:
        findings: list[Finding] = []
        for path in files:
            text = self._read(path)
            claims = len(_COUNT_CLAIM.findall(text))
            recounted = 0
            for lineno, raw in enumerate(text.split("\n"), start=1):
                for match in _FILE_COUNT.finditer(raw):
                    findings.append(
                        self._undecided(
                            path,
                            lineno,
                            "T004",
                            f"a claim of {match.group(1)} files: recounting a "
                            f"directory answered a different question than the "
                            f"sentence asked in every case measured.",
                        )
                    )
                if not _LINE_COUNT.search(raw):
                    continue
                if _HISTORICAL_COUNT.search(raw):
                    findings.append(
                        self._undecided(
                            path,
                            lineno,
                            "T004",
                            "the count is stated in the past tense, and the tree "
                            "it described is gone.",
                        )
                    )
                    continue
                if _SPAN_CONTEXT.search(raw):
                    findings.append(
                        self._undecided(
                            path,
                            lineno,
                            "T004",
                            "the line cites line numbers, so the count may name "
                            "a span rather than the length of a file.",
                        )
                    )
                    continue
                checked = [
                    self._check_line_count(
                        path,
                        lineno,
                        raw,
                        int(m.group(1).replace(",", "")),
                        m.span(),
                    )
                    for m in _LINE_COUNT.finditer(raw)
                ]
                recounted += sum(1 for _, done in checked if done)
                findings.extend(f for f, _ in checked if f.rule_id == "T004")
            if claims > recounted:
                findings.append(
                    self._undecided(
                        path,
                        1,
                        "T004",
                        f"{claims} count claim(s) read, {recounted} recomputed "
                        f"against the tree. The rest state a number whose "
                        f"subject this instrument cannot resolve to a path.",
                    )
                )
        return findings, "ok"

    def _run_runtime_claims(self, files: list[Path]) -> tuple[list[Finding], str]:
        findings: list[Finding] = []
        for path in files:
            for sentence in _prose_sentences(self._read(path)):
                verbs = [
                    m
                    for m in _RUNTIME_CLAIM.finditer(sentence.text)
                    if not _DETERMINER.search(sentence.text[: m.start()])
                ]
                if not verbs:
                    continue
                if _CLAIM_SOFTENER.search(sentence.text):
                    continue
                if _RUNTIME_EVIDENCE.search(sentence.text):
                    continue
                findings.append(
                    Finding(
                        tool="truth",
                        severity="medium",
                        file=str(path),
                        line=sentence.line,
                        rule_id="T005",
                        message=(
                            "a claim about what the running program does, with "
                            "no observation named in the same sentence. Name how "
                            f"it was seen. Sentence: {sentence.text[:160]!r}"
                        ),
                    )
                )
        return findings, "ok"

    def _run_proxy_claims(self, files: list[Path]) -> tuple[list[Finding], str]:
        findings: list[Finding] = []
        for path in files:
            text = self._read(path)
            sentences = _prose_sentences(text)
            for sentence in sentences:
                if not _COMPLETION_WORD.search(sentence.text):
                    continue
                if not _PROXY_EVIDENCE.search(sentence.text):
                    continue
                if _RUNTIME_EVIDENCE.search(sentence.text):
                    continue
                findings.append(
                    Finding(
                        tool="truth",
                        severity="medium",
                        file=str(path),
                        line=sentence.line,
                        rule_id="T006",
                        message=(
                            "a completion claim whose only stated evidence is a "
                            "name, a registry entry, a comparison or a count. "
                            f"Sentence: {sentence.text[:160]!r}"
                        ),
                    )
                )
            green = [
                s
                for s in sentences
                if _GREEN_CLAIM.search(s.text) and _CHECK_SUBJECT.search(s.text)
            ]
            if green and not _RED_EVIDENCE.search(text):
                findings.append(
                    Finding(
                        tool="truth",
                        severity="high",
                        file=str(path),
                        line=green[0].line,
                        rule_id="T006",
                        message=(
                            f"{len(green)} claim(s) of a pass, and nothing in "
                            "this text names a failing observation. A green from "
                            "an instrument whose red was never seen is not "
                            "evidence."
                        ),
                    )
                )
        return findings, "ok"

    def _unhandled_falsification(self, report: ArchetypeReport) -> str:
        return (
            f"This report is wrong if a claim-resolving analyzer for "
            f"{report.language!r} exists in this archetype. NO ANALYZER RAN on "
            f"{report.target!r}: this archetype reads "
            f"{', '.join(HANDLED_SUFFIXES)} only, and a refusal is not the same "
            f"answer as clean."
        )

    def _falsification(self, report: ArchetypeReport, index: _TreeIndex | None) -> str:
        undecided = sum(1 for f in report.findings if f.rule_id == "T000")
        parts = [
            "This truth report is wrong if:",
            "(a) a claim it resolved was resolved against a stale tree — every "
            f"path, symbol and count was read from {str(self.root)!r} at review "
            "time, and an edit after that voids the verdict;",
            "(b) T001 named a path that exists only under a different case. A "
            "line already calling the path gone is recorded as T000, so a wrong "
            "path beside those words is reported as agreement;",
            "(c) T002 named a symbol bound by a runtime import, a getattr or a "
            "generated name — the index reads definitions, not dynamic binding;",
            "(d) T003 read a listing gh truncated, or a listing for a repository "
            "other than the one the claim is about;",
            "(e) T004 recounted a subject other than the one the sentence meant. "
            "It reads only a line count whose path sits within "
            f"{_COUNT_SUBJECT_GAP} characters of the number, and it decides "
            "nothing about a count of files, a count of tests, or any number "
            "whose subject is not one path;",
            "(f) T005 fired on a sentence whose observation was named in the "
            "sentence before it, or stayed silent on a runtime claim phrased "
            "outside its verb list. It decides whether an observation is NAMED, "
            "never whether the claim is true, and never what the named method "
            "could not see. `runs`, `ran` and `draws` are outside the list "
            "because they matched descriptive prose far more often than an "
            "observed run;",
            "(g) T006 fired where the proof sits elsewhere in the document, or "
            "stayed silent on a proxy claim written without a completion word. "
            "It decides co-occurrence, never intent, and a bare negative such as "
            "'no tokens are missing' is beyond it;",
            f"(h) any of the {undecided} T000 record(s) is in fact decidable by "
            "an instrument this archetype could carry.",
        ]
        if index is not None:
            parts.append(
                f"Index: {index.python_files} python file(s) parsed, "
                f"{index.parse_failures} unparseable and therefore invisible to "
                f"T002, {len(index.definitions)} def/class names, "
                f"{len(index.python_names)} python names, "
                f"{len(index.string_names)} string-constant names, "
                f"{len(index.foreign_names)} foreign names."
            )
        return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    """Print the JSON report for one path and return the archetype exit code."""
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python -m dev_harness.harness.truth_archetype <path>")
        print("       resolves the claims in a markdown/text file against the tree")
        return 2
    report = TruthArchetype().review(Path(argv[0]))
    print(json.dumps(report.to_dict(), indent=2))
    return cli_exit(report)


if __name__ == "__main__":
    sys.exit(main())
