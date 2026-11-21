"""TruthArchetype — resolves the checkable claims in a text against the tree.

`review` reads one Markdown or text target and reports `T001` through `T007`
for a citation, a count, a runtime claim, a proxy claim or a subject outside
the item, where the tree contradicts what the text says.
`T000` records a claim this archetype identified and could not decide, so an
undecided claim is never silent.
`T008` reports a machine path or an asset name in public text, and `T009`
reports each hollow part of a `test-statement` block and a `record_*.md` that
plans runs without one.
"""

from __future__ import annotations

import ast
import bisect
import builtins
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dev_harness.harness.report import (
    REPO_ROOT,
    ArchetypeReport,
    Finding,
    cli_exit,
)
from dev_harness.harness.rules.hallucination import _excluded_top_level

__all__ = ["ArchetypeReport", "Finding", "TruthArchetype", "main"]


HANDLED_SUFFIXES: tuple[str, ...] = (".md", ".markdown", ".txt")

_SKIP_DIRS = frozenset(
    {
        ".claude",
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

# The manual's page names and its multi-word headings are the product's own
# subject names, and `_run_scope` decides each occurrence against the item.
_MANUAL_PARTS = ("docs", "manual")

_MANUAL_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*$")

_TITLE_PHRASE = re.compile(
    r"[A-Z][a-z]+(?:\s+(?:of|and|for|to|in)\s+[A-Z][a-z]+|\s+[A-Z][a-z]+)*"
)

_CONNECTOR = frozenset({"of", "and", "for", "to", "in"})

# A determiner, a pronoun, a counter and a month open a sentence far more often
# than they name a subject.
_LEAD_WORD = frozenset(
    {
        "A",
        "All",
        "An",
        "And",
        "Both",
        "But",
        "Each",
        "Eight",
        "Every",
        "Five",
        "For",
        "Four",
        "From",
        "Here",
        "His",
        "How",
        "I",
        "If",
        "In",
        "It",
        "Its",
        "Nine",
        "No",
        "None",
        "Not",
        "Nothing",
        "Now",
        "On",
        "One",
        "Only",
        "Or",
        "Our",
        "Seven",
        "She",
        "Six",
        "So",
        "Some",
        "Ten",
        "That",
        "The",
        "Their",
        "Then",
        "There",
        "These",
        "They",
        "This",
        "Those",
        "Three",
        "To",
        "Today",
        "Two",
        "We",
        "What",
        "When",
        "Where",
        "Which",
        "Who",
        "Why",
        "With",
        "Without",
        "You",
        "Your",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    }
)

_QUOTED_SPAN = re.compile('"[^"]*"|“[^”]*”')
_LINK_SPAN = re.compile(r"\[[^\]]*\]\([^)]*\)")
_EMPHASIS_MARK = re.compile(r"[*_]{1,3}")

# `in place of` reads as `instead of`, and is the one `_COMPLETION_WORD` match
# that claims no completion.
_NOT_COMPLETION = re.compile(r"\bin place of\b", re.IGNORECASE)

# Without a completion word the sentence must predicate a state of the subject:
# naming a neighbour in a list is not a claim about it.
_SUBJECT_PREDICATE = re.compile(
    r"^(?:\s+(?!that\b|which\b|who\b|whose\b|where\b|when\b)[a-z][a-z-]*){0,3}"
    r"\s+(?P<verb>is|are|was|were|has|have|holds"
    r"|carries|renders|draws|shows|reports|works|runs|exists|sits|lives"
    r"|answers|reads|writes|fires|emits|remains|stays|became|becomes)\b"
    r"\s*(?P<complement>[A-Za-z']+)?"
)

_COPULA = frozenset({"is", "are", "was", "were", "remains", "stays"})

# `is the shortest path` identifies the subject; `is wired` states about it.
_IDENTITY_LEAD = frozenset(
    {
        "a",
        "an",
        "another",
        "the",
        "one",
        "its",
        "his",
        "her",
        "their",
        "our",
        "my",
        "your",
        "this",
        "that",
        "these",
        "those",
        "what",
        "where",
        "why",
        "how",
        "which",
    }
)

# `a Simulator` names one of a class; `the Simulator` names the product's own.
_INDEFINITE = re.compile(r"\b(?:a|an)\s+$", re.IGNORECASE)

# A completion word binds to the subject sharing its clause, never across one.
_CLAUSE_BREAK = re.compile(r";|—|--")

# A sentence putting the subject outside the item is the rule working.
_OUT_OF_SCOPE = re.compile(
    r"\bnot part of\b|\bout of scope\b|\bnot in scope\b|\bnot this item\b"
    r"|\bbelongs to\b|\bowned by\b|\bfolds? into\b|\bnot the item\b"
    r"|\banother item\b|\bdifferent item\b|\bnot built\b|\bunbuilt\b"
    r"|\bnever built\b|\bnot converted\b|\bno such screen\b|\bcannot open\b",
    re.IGNORECASE,
)

_PY_RESERVED = frozenset(dir(builtins))

_GH_LIST_LIMIT = 1000

# A merged pull request is not open, and T003 compares against open or closed.
_STATE_ALIASES = {"MERGED": "CLOSED"}

_UNRESOLVED_NUMBER = re.compile(
    r"Could not resolve to an issue or pull request", re.IGNORECASE
)

_MACHINE_PATH = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]|/Users/[a-z]|/home/[a-z]")
_EXPORT_DIR = ("artifacts", "evidence-input", "transactions")
_ASSET_COLUMN = "Asset"


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


def _iter_sources(root: Path, ignored: frozenset[str] = frozenset()) -> Iterator[Path]:
    """Yield each file under `root`, skipping `_SKIP_DIRS` and top-level `ignored`."""
    for dirpath, dirnames, filenames in os.walk(root):
        skip = _SKIP_DIRS | ignored if dirpath == str(root) else _SKIP_DIRS
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            if name not in skip:
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
    """Return a name index of each source under `root` outside `_excluded_top_level`."""
    index = _TreeIndex()
    for path in _iter_sources(root, _excluded_top_level(root)):
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


def _strip_lead(phrase: str) -> str:
    """Return `phrase` without the `_LEAD_WORD` entries that open it."""
    words = phrase.split()
    while words and words[0] in _LEAD_WORD:
        words.pop(0)
    return " ".join(words)


def _is_titled(phrase: str) -> bool:
    """True when every word of `phrase` outside `_CONNECTOR` is capitalised."""
    return all(
        word[:1].isupper() for word in phrase.split() if word.lower() not in _CONNECTOR
    )


def _predicates_state(tail: str) -> bool:
    """True when `tail` states something of the subject rather than naming it."""
    match = _SUBJECT_PREDICATE.match(tail)
    if match is None:
        return False
    complement = (match.group("complement") or "").lower()
    if not complement:
        return False
    if match.group("verb") not in _COPULA:
        return True
    return complement not in _IDENTITY_LEAD


def _clause_at(text: str, position: int) -> str:
    """Return the `_CLAUSE_BREAK` clause of `text` that holds `position`."""
    start = 0
    for match in _CLAUSE_BREAK.finditer(text):
        if match.start() > position:
            return text[start : match.start()]
        start = match.end()
    return text[start:]


def _plain_sentence(text: str) -> str:
    """Return `text` without its `_LINK_SPAN`, `_QUOTED_SPAN` and emphasis marks."""
    body = _LINK_SPAN.sub(" ", text)
    body = _QUOTED_SPAN.sub(" ", body)
    return _EMPHASIS_MARK.sub("", body)


def _claims_completion(text: str) -> bool:
    """True on a `_COMPLETION_WORD` outside a `_NOT_COMPLETION` span.

    A `_CLAIM_SOFTENER` anywhere in `text` leaves the claim conditional.
    """
    if not _COMPLETION_WORD.search(text) or _CLAIM_SOFTENER.search(text):
        return False
    return bool(_COMPLETION_WORD.search(_NOT_COMPLETION.sub(" ", text)))


def manual_subject_names(manual: Path) -> set[str]:
    """Return the manual's page names and its multi-word heading phrases.

    These are the subject names `_run_scope` looks for in a document.
    """
    names: set[str] = set()
    stems: set[str] = set()
    headings: list[str] = []
    if not manual.is_dir():
        return names
    for path in sorted(manual.rglob("*.md")):
        stem = re.sub(r"^\d+[-_]", "", path.stem)
        if not any(ch.isdigit() for ch in stem):
            words = [w for w in re.split(r"[-_]+", stem) if w]
            if words:
                stems.add(" ".join(w.capitalize() for w in words))
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in source.split("\n"):
            heading = _MANUAL_HEADING.match(raw)
            if heading is None:
                continue
            plain = _INLINE_CODE_RE.sub(" ", heading.group(1))
            headings.append(plain)
            for run in _TITLE_PHRASE.finditer(plain):
                phrase = _strip_lead(run.group(0))
                if " " in phrase:
                    names.add(phrase)
    blob = "\n".join(headings)
    names.update(stem for stem in stems if phrase_present(stem, blob))
    return {name for name in names if len(name) > 2}


def subject_pattern(names: set[str]) -> re.Pattern[str] | None:
    """Return one alternation over `names`, longest first, or None when empty."""
    if not names:
        return None
    ordered = sorted(names, key=lambda name: (-len(name), name))
    body = "|".join(re.escape(name).replace(r"\ ", r"\s+") for name in ordered)
    return re.compile(rf"\b(?:{body})\b", re.IGNORECASE)


def code_text(text: str) -> str:
    """Return the content of `text`'s fenced blocks and inline code spans."""
    parts: list[str] = []
    in_fence = False
    for raw in text.split("\n"):
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            parts.append(raw)
            continue
        parts.extend(span.group(1) for span in _INLINE_CODE_RE.finditer(raw))
    return "\n".join(parts)


def phrase_present(phrase: str, text: str) -> bool:
    """True when `text` carries `phrase`, whatever joins its words."""
    joined = r"[^A-Za-z0-9]+".join(re.escape(word) for word in phrase.split())
    return bool(
        re.search(rf"(?<![A-Za-z0-9]){joined}(?![A-Za-z0-9])", text, re.IGNORECASE)
    )


_STATEMENT_TAG = "test-statement"
_STATEMENT_FENCE = re.compile(r"^\s*(?P<mark>`{3,}|~{3,})(?P<info>.*)$")
_STATEMENT_PARTS = (
    "question",
    "arms",
    "unit",
    "measure",
    "inputs",
    "runs",
    "expected",
    "pass",
    "harm",
    "interim",
    "adversarial",
)
_STATEMENT_TESTS = ("exact sign", "fisher exact")
_INPUT_RULES = ("all", "seeded draw")
_INTERIM_READS = ("voids", "single arm rate")
_ADVERSARIAL_QUESTIONS = (
    "what makes this result wrong",
    "what does the measure miss",
    "what is the cheapest way to pass without the behaviour",
    "does any input sit at a ceiling or a floor",
)
_CALIBRATION_SIDES = {"known_good": "pass", "known_bad": "fail"}
_MIN_ARMS = 2
_ALPHA_CEILING = 0.1
_POWER_TOLERANCE = 0.01
_PREVIEW_NAMES = 8

# Measured on this host: 1.96 s at 1000 sign pairs, 2.71 s at 500 Fisher per arm.
_MAX_SIGN_PAIRS = 1000
_MAX_FISHER_PER_ARM = 500

_RECORD_PREFIX = "record_"
_PLANNED_COUNT = re.compile(
    r"\b(?P<count>\d[\d,]*|one|two|three|four|five|six|seven|eight|nine|ten"
    r"|eleven|twelve|twenty|thirty|forty|fifty|sixty|hundred)"
    r"\s+(?:(?:more|further|additional|extra|new|paired|agent|planned)\s+)?"
    r"(?P<noun>runs?|rounds?)\b",
    re.IGNORECASE,
)
_COUNT_LABEL = re.compile(
    r"\b(?:step|round|task|level|version|experiment|block|comment|item|part"
    r"|row|phase|stage|question|issue|unit)\s+$",
    re.IGNORECASE,
)
_SINGLE_COUNT = frozenset({"one", "1"})
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_DIGIT = re.compile(r"\d")

# The MT19937 constants CPython's _randommodule.c uses for random.Random.
_MT_SIZE = 624
_MT_SHIFT = 397
_MT_WORD_BITS = 32
_MT_WORD = 0xFFFFFFFF
_MT_UPPER = 0x80000000
_MT_LOWER = 0x7FFFFFFF
_MT_TWIST = 0x9908B0DF
_MT_TEMPER_B = 0x9D2C5680
_MT_TEMPER_C = 0xEFC60000
_MT_ROOT_SEED = 19650218
_MT_INIT_MULT = 1812433253
_MT_KEY_MULT = 1664525
_MT_MIX_MULT = 1566083941

# The set-size terms of Random.sample in CPython's random.py.
_SAMPLE_SET_BASE = 21
_SAMPLE_SMALL_SIZE = 5

_Field = tuple[Callable[[Any], bool], str]
_Check = Callable[[Any, dict[str, Any], Path], list[str]]


class _SeededDraw:
    """The `random.Random(seed)` generator, rebuilt from CPython's MT19937 code.

    `sample` returns what `random.Random(seed).sample` returns on CPython 3.14.
    """

    def __init__(self, seed: int) -> None:
        """Seed `_state` from the 32-bit words of `abs(seed)`, as `init_by_array`."""
        rest = abs(seed)
        key = [rest & _MT_WORD]
        while rest >> _MT_WORD_BITS:
            rest >>= _MT_WORD_BITS
            key.append(rest & _MT_WORD)
        state = [0] * _MT_SIZE
        state[0] = _MT_ROOT_SEED
        for at in range(1, _MT_SIZE):
            prior = state[at - 1]
            state[at] = (_MT_INIT_MULT * (prior ^ (prior >> 30)) + at) & _MT_WORD
        at, slot = 1, 0
        for _ in range(max(_MT_SIZE, len(key))):
            prior = state[at - 1]
            mixed = (state[at] ^ ((prior ^ (prior >> 30)) * _MT_KEY_MULT)) + key[slot]
            state[at] = (mixed + slot) & _MT_WORD
            at, slot = at + 1, slot + 1
            if at >= _MT_SIZE:
                state[0], at = state[-1], 1
            if slot >= len(key):
                slot = 0
        for _ in range(_MT_SIZE - 1):
            prior = state[at - 1]
            mixed = state[at] ^ ((prior ^ (prior >> 30)) * _MT_MIX_MULT)
            state[at] = (mixed - at) & _MT_WORD
            at += 1
            if at >= _MT_SIZE:
                state[0], at = state[-1], 1
        state[0] = _MT_UPPER
        self._state = state
        self._index = _MT_SIZE

    def _word(self) -> int:
        """Return the next tempered word, regenerating `_state` every `_MT_SIZE`."""
        state = self._state
        if self._index >= _MT_SIZE:
            for at in range(_MT_SIZE):
                upper = state[at] & _MT_UPPER
                mixed = upper | (state[(at + 1) % _MT_SIZE] & _MT_LOWER)
                twist = _MT_TWIST if mixed & 1 else 0
                state[at] = state[(at + _MT_SHIFT) % _MT_SIZE] ^ (mixed >> 1) ^ twist
            self._index = 0
        value = state[self._index]
        self._index += 1
        value ^= value >> 11
        value ^= (value << 7) & _MT_TEMPER_B
        value ^= (value << 15) & _MT_TEMPER_C
        return value ^ (value >> 18)

    def _bits(self, width: int) -> int:
        """Return `width` bits from `_word`, low word first, as `getrandbits`."""
        if width <= _MT_WORD_BITS:
            return self._word() >> (_MT_WORD_BITS - width) if width else 0
        value, shift = 0, 0
        while width > 0:
            part = self._word()
            if width < _MT_WORD_BITS:
                part >>= _MT_WORD_BITS - width
            value |= part << shift
            shift, width = shift + _MT_WORD_BITS, width - _MT_WORD_BITS
        return value

    def _below(self, limit: int) -> int:
        """Return a value below `limit` by rejection, as `Random._randbelow`."""
        width = limit.bit_length()
        value = self._bits(width)
        while value >= limit:
            value = self._bits(width)
        return value

    def sample(self, names: list[str], size: int) -> list[str]:
        """Return `size` entries of `names` in the order `Random.sample` picks them."""
        total = len(names)
        setsize = _SAMPLE_SET_BASE
        if size > _SAMPLE_SMALL_SIZE:
            setsize += 4 ** math.ceil(math.log(size * 3, 4))
        drawn: list[str] = []
        if total <= setsize:
            pool = list(names)
            for at in range(size):
                pick = self._below(total - at)
                drawn.append(pool[pick])
                pool[pick] = pool[total - at - 1]
            return drawn
        taken: set[int] = set()
        for _ in range(size):
            pick = self._below(total)
            while pick in taken:
                pick = self._below(total)
            taken.add(pick)
            drawn.append(names[pick])
        return drawn


def seeded_sample(seed: int, names: list[str], size: int) -> list[str]:
    """Return the list `random.Random(seed).sample(names, size)` returns."""
    return _SeededDraw(seed).sample(names, size)


def _binomial_pmf(trials: int, rate: float) -> list[float]:
    """Return the chance of each pass count from 0 to `trials` at pass `rate`."""
    if rate <= 0:
        return [1.0] + [0.0] * trials
    if rate >= 1:
        return [0.0] * trials + [1.0]
    log_rate, log_rest = math.log(rate), math.log1p(-rate)
    whole = math.lgamma(trials + 1)
    return [
        math.exp(
            whole
            - math.lgamma(count + 1)
            - math.lgamma(trials - count + 1)
            + count * log_rate
            + (trials - count) * log_rest
        )
        for count in range(trials + 1)
    ]


def _sign_threshold(discordant: int, alpha: float) -> int | None:
    """Return the fewest second-arm wins in `discordant` pairs reading p below `alpha`.

    The p is the exact two-sided sign test's, and None means no split reaches it.
    """
    tail = 0
    need: int | None = None
    for low in range(discordant):
        if 2 * low >= discordant:
            break
        tail += math.comb(discordant, low)
        if 2 * tail / 2**discordant >= alpha:
            break
        need = discordant - low
    return need


def _sign_power(
    pairs: int, first_rate: float, second_rate: float, alpha: float
) -> float:
    """Return the chance the exact sign test over `pairs` reads p below `alpha`.

    Only pairs whose arms differ count, and the second arm must lead.
    """
    only_second = second_rate * (1 - first_rate)
    only_first = first_rate * (1 - second_rate)
    split = only_second + only_first
    if split <= 0:
        return 0.0
    discordant_chance = _binomial_pmf(pairs, split)
    second_share = only_second / split
    chance = 0.0
    for discordant in range(1, pairs + 1):
        need = _sign_threshold(discordant, alpha)
        if need is not None and discordant_chance[discordant] > 0:
            wins = _binomial_pmf(discordant, second_share)
            chance += discordant_chance[discordant] * math.fsum(wins[need:])
    return chance


def _fisher_power(
    per_arm: int, first_rate: float, second_rate: float, alpha: float
) -> float:
    """Return the chance Fisher's exact two-sided test reads p below `alpha`.

    Two groups of `per_arm` are compared, and the second arm must lead.
    """
    first = _binomial_pmf(per_arm, first_rate)
    second = _binomial_pmf(per_arm, second_rate)
    chance = 0.0
    for column in range(2 * per_arm + 1):
        low, high = max(0, column - per_arm), min(per_arm, column)
        weights = {
            count: math.comb(per_arm, count) * math.comb(per_arm, column - count)
            for count in range(low, high + 1)
        }
        total = math.comb(2 * per_arm, column)
        at_most: dict[int, int] = {}
        running = 0
        for weight in sorted(weights.values()):
            running += weight
            at_most[weight] = running
        for first_pass, weight in weights.items():
            second_pass = column - first_pass
            if second_pass > first_pass and at_most[weight] / total < alpha:
                chance += first[first_pass] * second[second_pass]
    return chance


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Return `pairs` as a dict, raising `ValueError` when a key repeats."""
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            message = f"the key {key!r} appears twice in one object"
            raise ValueError(message)
        seen[key] = value
    return seen


def _finite_float(raw: str) -> float:
    """Return `raw` as a float, raising `ValueError` when it is not finite."""
    value = float(raw)
    if not math.isfinite(value):
        message = f"{raw} is not a finite number"
        raise ValueError(message)
    return value


def _refused_constant(raw: str) -> float:
    """Raise `ValueError` for the `NaN` and `Infinity` names `json.loads` accepts."""
    message = f"{raw} is not a number"
    raise ValueError(message)


def _strict_json(text: str) -> object:
    """Return `text` parsed by `json.loads`.

    `_unique_object`, `_finite_float` and `_refused_constant` raise on repeats.
    """
    parsed: object = json.loads(
        text,
        object_pairs_hook=_unique_object,
        parse_float=_finite_float,
        parse_constant=_refused_constant,
    )
    return parsed


def _is_text(value: object) -> bool:
    """Return True when `value` is a JSON string."""
    return type(value) is str


def _is_count(value: object) -> bool:
    """Return True when `value` is a JSON whole number and not a boolean."""
    return type(value) is int


def _is_number(value: object) -> bool:
    """Return True when `value` is a JSON number and not a boolean."""
    return type(value) in {int, float}


def _is_list(value: object) -> bool:
    """Return True when `value` is a JSON list."""
    return type(value) is list


def _is_text_list(value: object) -> bool:
    """Return True when `value` is a JSON list of strings."""
    return isinstance(value, list) and all(type(item) is str for item in value)


_TEXT: _Field = (_is_text, "a string")
_COUNT: _Field = (_is_count, "a whole number")
_NUMBER: _Field = (_is_number, "a number")
_LIST: _Field = (_is_list, "a list")
_TEXT_LIST: _Field = (_is_text_list, "a list of strings")
_VERDICT_FIELDS: dict[str, _Field] = {
    "test": _TEXT,
    "group": _TEXT,
    "alpha": _NUMBER,
    "leading_arm": _TEXT,
}
_PART_FIELDS: dict[str, tuple[dict[str, _Field], dict[str, _Field]]] = {
    "measure": ({"reading": _TEXT, "checks": _TEXT_LIST, "calibration": _TEXT}, {}),
    "expected": ({"source": _TEXT, "statement": _TEXT}, {}),
    "pass": (_VERDICT_FIELDS, {}),
    "harm": (_VERDICT_FIELDS, {}),
    "interim": ({"reads": _TEXT_LIST}, {"stop_if_single_arm_rate_above": _NUMBER}),
}
_RUNS_FIELDS: dict[str, _Field] = {
    "rounds": _COUNT,
    "per_round": _COUNT,
    "total": _COUNT,
    "alpha": _NUMBER,
    "power": _LIST,
}
_EVIDENCE_FIELDS: dict[str, _Field] = {
    "question": _TEXT,
    "answer": _TEXT,
    "evidence": _TEXT,
}


def _object_faults(
    where: str,
    value: object,
    fields: dict[str, _Field],
    optional: dict[str, _Field] | None = None,
) -> list[str]:
    """Return the missing, unknown and mistyped keys of `value` against `fields`."""
    if not isinstance(value, dict):
        return [f"{where} is not an object"]
    allowed = {**(optional or {}), **fields}
    faults = [f"{where} has no key {key!r}" for key in fields if key not in value]
    for key, item in value.items():
        if key not in allowed:
            faults.append(f"{where} holds the unknown key {key!r}")
        elif not allowed[key][0](item):
            faults.append(f"{where}.{key} is not {allowed[key][1]}")
    return faults


def _inputs_fields(value: object) -> tuple[dict[str, _Field], dict[str, _Field]]:
    """Return the required and the optional `inputs` keys for the rule it names."""
    fields: dict[str, _Field] = {
        "rule": _TEXT,
        "population": _TEXT,
        "items": _TEXT_LIST,
    }
    drawn: dict[str, _Field] = {"seed": _COUNT, "size": _COUNT}
    rule = value.get("rule") if isinstance(value, dict) else None
    if rule == "seeded draw":
        return {**fields, **drawn}, {}
    if rule == "all":
        return fields, {}
    return fields, drawn


def _power_fields(entry: object) -> tuple[dict[str, _Field], dict[str, _Field]]:
    """Return the required and the optional keys of a power `entry` for its test."""
    fields: dict[str, _Field] = {
        "test": _TEXT,
        "first_rate": _NUMBER,
        "second_rate": _NUMBER,
        "power": _NUMBER,
    }
    test = entry.get("test") if isinstance(entry, dict) else None
    if test == "exact sign":
        return {**fields, "pairs": _COUNT}, {}
    if test == "fisher exact":
        return {**fields, "per_arm": _COUNT}, {}
    return fields, {"pairs": _COUNT, "per_arm": _COUNT}


def _runs_shape(value: object) -> list[str]:
    """Return what is wrong with the JSON form of `runs` and of its power entries."""
    faults = _object_faults("runs", value, _RUNS_FIELDS)
    if faults or not isinstance(value, dict):
        return faults
    for number, entry in enumerate(value["power"], start=1):
        where = f"runs power entry {number}"
        faults += _object_faults(where, entry, *_power_fields(entry))
    return faults


def _adversarial_shape(value: object) -> list[str]:
    """Return what is wrong with the JSON form of `adversarial` and of each entry."""
    if not isinstance(value, list):
        return ["adversarial is not a list"]
    faults: list[str] = []
    for number, entry in enumerate(value, start=1):
        where = f"adversarial entry {number}"
        faults += _object_faults(where, entry, _EVIDENCE_FIELDS)
    return faults


def _part_shape(part: str, value: object) -> list[str]:
    """Return what is wrong with the JSON form of `value` as the statement `part`."""
    if part in {"question", "unit"}:
        return [] if _is_text(value) else [f"{part} is not a string"]
    if part == "arms":
        if not isinstance(value, dict):
            return ["arms is not an object"]
        return [
            f"the condition of arm {name!r} is not a string"
            for name, condition in value.items()
            if not _is_text(condition)
        ]
    if part == "inputs":
        return _object_faults(part, value, *_inputs_fields(value))
    if part == "runs":
        return _runs_shape(value)
    if part == "adversarial":
        return _adversarial_shape(value)
    return _object_faults(part, value, *_PART_FIELDS[part])


def _inside(root: Path, raw: str) -> Path | None:
    """Return `raw` resolved under `root`, or None for an empty or absolute path.

    None also answers `root` itself and a path that resolves outside `root`.
    """
    text = raw.strip().replace("\\", "/")
    if not text or text.startswith(("/", "~")) or _DRIVE_PREFIX.match(text):
        return None
    found = (root / text).resolve()
    if found == root or not found.is_relative_to(root):
        return None
    return found


def _present(root: Path, raw: str) -> bool:
    """Return True when `raw` names a file or a folder `_inside` finds under `root`."""
    found = _inside(root, raw)
    return found is not None and found.exists()


def _preview(names: list[str]) -> str:
    """Return `names` as a list, cut after `_PREVIEW_NAMES` entries."""
    shown = ", ".join(repr(name) for name in names[:_PREVIEW_NAMES])
    rest = len(names) - _PREVIEW_NAMES
    return f"[{shown}, and {rest} more]" if rest > 0 else f"[{shown}]"


def _question_faults(question: str, sound: dict[str, Any], _root: Path) -> list[str]:
    """Return the faults of `question`: no closing question mark, or an arm unnamed."""
    faults: list[str] = []
    if not question.rstrip().endswith("?"):
        faults.append("it does not end in a question mark")
    faults += [
        f"it does not name the arm {name!r}"
        for name in sound.get("arms", {})
        if name.strip() and not phrase_present(name, question)
    ]
    return faults


def _arms_faults(
    arms: dict[str, str], _sound: dict[str, Any], _root: Path
) -> list[str]:
    """Return the faults of `arms`: under `_MIN_ARMS`, an empty name or condition."""
    faults: list[str] = []
    if len(arms) < _MIN_ARMS:
        faults.append(f"it lists {len(arms)} arm(s); a test compares two or more")
    faults += ["an arm name is empty" for name in arms if not name.strip()]
    faults += [
        f"the arm {name!r} has an empty condition"
        for name, condition in arms.items()
        if not condition.strip()
    ]
    return faults


def _unit_faults(unit: str, _sound: dict[str, Any], _root: Path) -> list[str]:
    """Return a fault when `unit` is empty."""
    return [] if unit.strip() else ["it is empty"]


def _calibration_entry_faults(entry: object, root: Path) -> list[str]:
    """Return the faults of one calibration `entry` against `_CALIBRATION_SIDES`."""
    if not isinstance(entry, dict) or set(entry) != set(_CALIBRATION_SIDES):
        return ["it is not an object of exactly known_good and known_bad"]
    faults: list[str] = []
    for side, result in _CALIBRATION_SIDES.items():
        reading = entry[side]
        if not isinstance(reading, dict) or set(reading) != {"input", "result"}:
            faults.append(f"{side} is not an object of exactly input and result")
            continue
        if reading["result"] != result:
            faults.append(f"{side} records {reading['result']!r}, not {result!r}")
        if not _is_text(reading["input"]) or not _present(root, reading["input"]):
            faults.append(f"the {side} input {reading['input']!r} does not exist")
    return faults


def _calibration_faults(raw: str, checks: dict[str, Path], root: Path) -> list[str]:
    """Return the faults of the calibration file `raw` for each of `checks`."""
    found = _inside(root, raw)
    if found is None or not found.is_file():
        return [f"the calibration file {raw!r} does not exist under {root.name}"]
    try:
        table = _strict_json(found.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, RecursionError) as exc:
        return [f"the calibration file {raw!r} does not parse: {exc}"]
    if not isinstance(table, dict):
        return [f"the calibration file {raw!r} is not one JSON object"]
    entries = {_inside(root, key): entry for key, entry in table.items()}
    faults: list[str] = []
    for check, place in checks.items():
        if place not in entries:
            faults.append(f"the calibration file holds no entry for {check!r}")
            continue
        faults += [
            f"the calibration of {check!r}: {fault}"
            for fault in _calibration_entry_faults(entries[place], root)
        ]
    return faults


def _measure_faults(
    measure: dict[str, Any], _sound: dict[str, Any], root: Path
) -> list[str]:
    """Return the faults of `measure`: its reading, its checks and its calibration."""
    faults: list[str] = []
    if not measure["reading"].strip():
        faults.append("the reading is empty")
    if not measure["checks"]:
        faults.append("it names no check")
    resolved: dict[str, Path] = {}
    for check in measure["checks"]:
        place = _inside(root, check)
        if place is None or not place.exists():
            faults.append(f"the check {check!r} does not exist under {root.name}")
        else:
            resolved[check] = place
    return faults + _calibration_faults(measure["calibration"], resolved, root)


def _draw_faults(inputs: dict[str, Any], names: list[str]) -> list[str]:
    """Return a fault when the `inputs` items differ from `seeded_sample` of `names`."""
    seed, size = inputs["seed"], inputs["size"]
    if not 1 <= size <= len(names):
        return [f"the size {size} is outside 1 to {len(names)}, the subfolder count"]
    drawn = seeded_sample(seed, names, size)
    if inputs["items"] == drawn:
        return []
    fault = (
        f"the items differ from random.Random({seed}).sample of the {len(names)} "
        f"sorted subfolder names, size {size}, which draws {_preview(drawn)}"
    )
    return [fault]


def _inputs_faults(
    inputs: dict[str, Any], _sound: dict[str, Any], root: Path
) -> list[str]:
    """Return the faults of `inputs`: its rule, its items and its population."""
    faults: list[str] = []
    rule, items, population = inputs["rule"], inputs["items"], inputs["population"]
    if rule not in _INPUT_RULES:
        faults.append(f"the rule {rule!r} is neither 'all' nor 'seeded draw'")
    if not items:
        faults.append("it lists no item")
    folder = _inside(root, population)
    if folder is None or not folder.is_dir():
        faults.append(
            f"the population {population!r} is not a folder under {root.name}"
        )
        return faults
    names = sorted(entry.name for entry in folder.iterdir() if entry.is_dir())
    if rule == "all" and items != names:
        faults.append(
            f"the items differ from the {len(names)} sorted subfolder names of "
            f"{population!r}, {_preview(names)}"
        )
    if rule == "seeded draw":
        faults += _draw_faults(inputs, names)
    faults += [
        f"the item {item!r} does not exist in {population!r}"
        for item in items
        if not _present(folder, item)
    ]
    return faults


def _power_faults(entry: dict[str, Any], alpha: float) -> list[str]:
    """Return the faults of one power `entry`, recomputed at `alpha`."""
    test = entry["test"]
    if test not in _STATEMENT_TESTS:
        return [f"the test {test!r} is neither 'exact sign' nor 'fisher exact'"]
    key, ceiling, power = (
        ("pairs", _MAX_SIGN_PAIRS, _sign_power)
        if test == "exact sign"
        else ("per_arm", _MAX_FISHER_PER_ARM, _fisher_power)
    )
    faults: list[str] = []
    if not 1 <= entry[key] <= ceiling:
        faults.append(
            f"{key} {entry[key]} is outside 1 to {ceiling}, which T009 recomputes"
        )
    faults += [
        f"{rate} {entry[rate]} is not a rate from 0 to 1"
        for rate in ("first_rate", "second_rate")
        if not 0 <= entry[rate] <= 1
    ]
    if faults or not 0 < alpha <= _ALPHA_CEILING:
        return faults
    recomputed = power(entry[key], entry["first_rate"], entry["second_rate"], alpha)
    if abs(entry["power"] - recomputed) > _POWER_TOLERANCE:
        faults.append(
            f"it states power {entry['power']} for {test} at {key} {entry[key]}, "
            f"rates {entry['first_rate']} and {entry['second_rate']}, alpha {alpha}, "
            f"and recomputed it is {recomputed:.4f}"
        )
    return faults


def _runs_against_pass(
    runs: dict[str, Any], verdict: dict[str, Any] | None
) -> list[str]:
    """Return a fault when the power in `runs` and the `verdict` differ.

    They differ on `alpha`, or when no power entry uses the `verdict` test.
    """
    if verdict is None or not 0 < verdict["alpha"] <= _ALPHA_CEILING:
        return []
    faults: list[str] = []
    if runs["alpha"] != verdict["alpha"]:
        faults.append(
            f"alpha {runs['alpha']} differs from the pass alpha {verdict['alpha']}"
        )
    tests = {entry["test"] for entry in runs["power"]}
    if verdict["test"] in _STATEMENT_TESTS and tests and verdict["test"] not in tests:
        faults.append(f"no power entry uses the pass test {verdict['test']!r}")
    return faults


def _runs_faults(runs: dict[str, Any], sound: dict[str, Any], _root: Path) -> list[str]:
    """Return the faults of `runs`: its counts, its alpha, and each power recomputed."""
    faults = [
        f"{key} is {runs[key]}, and it is 1 or more"
        for key in ("rounds", "per_round", "total")
        if runs[key] < 1
    ]
    product = runs["rounds"] * runs["per_round"]
    if runs["total"] != product:
        faults.append(
            f"total {runs['total']} differs from rounds {runs['rounds']} times "
            f"per_round {runs['per_round']}, which is {product}"
        )
    alpha = runs["alpha"]
    if not 0 < alpha <= _ALPHA_CEILING:
        faults.append(f"alpha {alpha} is not above 0 and at most {_ALPHA_CEILING}")
    faults += _runs_against_pass(runs, sound.get("pass"))
    if not runs["power"]:
        faults.append("it holds no power entry, so nothing derives the count")
    for number, entry in enumerate(runs["power"], start=1):
        faults += [f"power entry {number}: {f}" for f in _power_faults(entry, alpha)]
    return faults


def _expected_faults(
    expected: dict[str, Any], _sound: dict[str, Any], root: Path
) -> list[str]:
    """Return the faults of `expected`: its source and its statement."""
    faults: list[str] = []
    if not _present(root, expected["source"]):
        faults.append(
            f"the source {expected['source']!r} does not exist under {root.name}"
        )
    if not _DIGIT.search(expected["statement"]):
        faults.append("the statement holds no number")
    return faults


def _verdict_faults(
    verdict: dict[str, Any], sound: dict[str, Any], _root: Path
) -> list[str]:
    """Return the faults of a `pass` or `harm` reading: test, group, alpha and arm."""
    faults: list[str] = []
    if verdict["test"] not in _STATEMENT_TESTS:
        faults.append(
            f"the test {verdict['test']!r} is neither 'exact sign' nor 'fisher exact'"
        )
    if not verdict["group"].strip():
        faults.append("the group is empty")
    if not 0 < verdict["alpha"] <= _ALPHA_CEILING:
        faults.append(
            f"alpha {verdict['alpha']} is not above 0 and at most {_ALPHA_CEILING}"
        )
    arms = sound.get("arms")
    if arms is not None and verdict["leading_arm"] not in arms:
        faults.append(
            f"the leading arm {verdict['leading_arm']!r} is not one of the arms "
            f"{sorted(arms)}"
        )
    return faults


def _interim_faults(
    interim: dict[str, Any], _sound: dict[str, Any], _root: Path
) -> list[str]:
    """Return the faults of `interim`: its reads and its stop rate."""
    faults = [
        f"it reads {read!r}, and before the last round it reads only 'voids' and "
        f"'single arm rate'"
        for read in interim["reads"]
        if read not in _INTERIM_READS
    ]
    stop = interim.get("stop_if_single_arm_rate_above")
    if stop is not None and not 0 <= stop <= 1:
        faults.append(f"stop_if_single_arm_rate_above {stop} is not a rate from 0 to 1")
    return faults


def _adversarial_faults(
    answers: list[dict[str, Any]], _sound: dict[str, Any], root: Path
) -> list[str]:
    """Return the faults of `answers` against `_ADVERSARIAL_QUESTIONS`, in order."""
    if len(answers) != len(_ADVERSARIAL_QUESTIONS):
        fault = (
            f"it holds {len(answers)} question(s), and it holds exactly these four, "
            f"in order: {list(_ADVERSARIAL_QUESTIONS)}"
        )
        return [fault]
    faults: list[str] = []
    pairs = zip(answers, _ADVERSARIAL_QUESTIONS, strict=True)
    for number, (entry, asked) in enumerate(pairs, start=1):
        if entry["question"].strip() != asked:
            faults.append(
                f"question {number} reads {entry['question']!r}, not {asked!r}"
            )
        if not entry["answer"].strip():
            faults.append(f"the answer to question {number} is empty")
        if not _present(root, entry["evidence"]):
            faults.append(
                f"the evidence {entry['evidence']!r} of question {number} does not "
                f"exist under {root.name}"
            )
    return faults


_PART_CHECKS: dict[str, _Check] = {
    "question": _question_faults,
    "arms": _arms_faults,
    "unit": _unit_faults,
    "measure": _measure_faults,
    "inputs": _inputs_faults,
    "runs": _runs_faults,
    "expected": _expected_faults,
    "pass": _verdict_faults,
    "harm": _verdict_faults,
    "interim": _interim_faults,
    "adversarial": _adversarial_faults,
}


def _verdict_pair_faults(sound: dict[str, Any]) -> list[str]:
    """Return a fault when `pass` and `harm` in `sound` share a leading arm."""
    gain, harm = sound.get("pass"), sound.get("harm")
    if gain is None or harm is None or gain["leading_arm"] != harm["leading_arm"]:
        return []
    return [f"pass and harm both name {gain['leading_arm']!r} as the leading arm"]


def _block_faults(body: str, root: Path) -> list[tuple[str, str]]:
    """Return (part, fault) for each check that `body`, one statement block, fails."""
    try:
        statement = _strict_json(body)
    except (ValueError, RecursionError) as exc:
        return [("JSON", f"the block does not parse: {exc}")]
    if not isinstance(statement, dict):
        return [("JSON", "the block is not one JSON object")]
    faults = [
        ("JSON", f"the required key {key!r} is missing")
        for key in _STATEMENT_PARTS
        if key not in statement
    ]
    faults += [
        ("JSON", f"the key {key!r} is not a part of a test statement")
        for key in statement
        if key not in _STATEMENT_PARTS
    ]
    sound: dict[str, Any] = {}
    for part in _STATEMENT_PARTS:
        if part not in statement:
            continue
        shape = _part_shape(part, statement[part])
        faults += [("JSON", fault) for fault in shape]
        if not shape:
            sound[part] = statement[part]
    for part, value in sound.items():
        faults += [(part, fault) for fault in _PART_CHECKS[part](value, sound, root)]
    faults += [("pass, harm", fault) for fault in _verdict_pair_faults(sound)]
    return faults


def statement_blocks(text: str) -> list[tuple[int, str]]:
    """Return the opening line and the body of each `_STATEMENT_TAG` block in `text`.

    A block opens on a fence whose info string starts with `_STATEMENT_TAG`.
    """
    lines = text.split("\n")
    blocks: list[tuple[int, str]] = []
    at = 0
    while at < len(lines):
        opening = _STATEMENT_FENCE.match(lines[at])
        if opening is None or (
            opening.group("mark").startswith("`") and "`" in opening.group("info")
        ):
            at += 1
            continue
        mark = opening.group("mark")
        closing = re.compile(rf"^\s*{re.escape(mark[0])}{{{len(mark)},}}\s*$")
        end = at + 1
        while end < len(lines) and not closing.match(lines[end]):
            end += 1
        if opening.group("info").split()[:1] == [_STATEMENT_TAG]:
            blocks.append((at + 1, "\n".join(lines[at + 1 : end])))
        at = end + 1
    return blocks


def _part_line(opening: int, body: str, part: str) -> int:
    """Return the file line of the first key `part` names in `body`, else `opening`."""
    key = "harm" if part == "pass, harm" else part
    pattern = re.compile(rf'"{re.escape(key)}"\s*:')
    for offset, raw in enumerate(body.split("\n"), start=1):
        if pattern.search(raw):
            return opening + offset
    return opening


def _counts_runs(found: re.Match[str], line: str) -> bool:
    """Return True when a `_PLANNED_COUNT` match counts runs or rounds in `line`.

    A number after a `_COUNT_LABEL` word, or one disagreeing with its noun, is a label.
    """
    single = found.group("count").lower() in _SINGLE_COUNT
    plural = found.group("noun").lower().endswith("s")
    return single != plural and not _COUNT_LABEL.search(line[: found.start()])


def _planned_count(text: str) -> tuple[int, str] | None:
    """Return the line and words of the first planned count in plain prose of `text`.

    Lines `_fenced_lines` names, block quotes and `_QUOTED_SPAN` text are skipped.
    """
    fenced = _fenced_lines(text)
    for lineno, raw in enumerate(text.split("\n"), start=1):
        if lineno in fenced or raw.lstrip().startswith(">"):
            continue
        plain = _QUOTED_SPAN.sub(" ", raw)
        for found in _PLANNED_COUNT.finditer(plain):
            if _counts_runs(found, plain):
                return lineno, found.group(0)
    return None


def _statement_finding(path: Path, line: int, message: str) -> Finding:
    """Return one high `T009` finding on `path` at `line`."""
    return Finding(
        tool="truth",
        severity="high",
        file=str(path),
        line=line,
        rule_id="T009",
        message=f"test-statement {message}",
    )


def statement_findings(path: Path, text: str, root: Path) -> list[Finding]:
    """Return a `T009` finding for each failing part of each block in `text`.

    A `record_*.md` path naming a `_PLANNED_COUNT` with no block draws one more.
    """
    blocks = statement_blocks(text)
    findings = [
        _statement_finding(
            path, _part_line(line, body, part), f"part {part!r}: {fault}"
        )
        for line, body in blocks
        for part, fault in _block_faults(body, root)
    ]
    is_record = path.name.startswith(_RECORD_PREFIX) and path.suffix.lower() == ".md"
    planned = _planned_count(text) if is_record and not blocks else None
    if planned is not None:
        line, words = planned
        findings.append(
            _statement_finding(
                path,
                line,
                f"block missing: {path.name} names {words!r} and holds no fenced "
                f"block marked {_STATEMENT_TAG}",
            )
        )
    return findings


class TruthArchetype:
    """Resolves a text's claims against the tree, and names the undecidable.

    `review` runs the nine analyzers named in `tools` over one Markdown or text
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
        "scope",
        "public_text",
        "test_statements",
    )

    def __init__(self, root: Path | None = None, item: int | None = None) -> None:
        """Bind the tree `root` every claim is resolved against.

        `item` is the issue number `_run_scope` grounds a subject against, and
        None leaves that number to be read from the document's own citation.
        """
        self.root = Path(root or REPO_ROOT).resolve()
        self._index: _TreeIndex | None = None
        self._top_level: set[str] | None = None
        self._item = item
        self._subjects: re.Pattern[str] | None = None
        self._subjects_built = False
        self._views: dict[int, tuple[dict[str, str], str]] = {}

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
            ("scope", self._run_scope),
            ("public_text", self._run_public_text),
            ("test_statements", self._run_test_statements),
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

    def _export_names(self) -> set[str]:
        """Return the `_ASSET_COLUMN` values of the newest CSV under `_EXPORT_DIR`."""
        exports = list(self.root.joinpath(*_EXPORT_DIR).glob("*.csv"))
        if not exports:
            return set()
        newest = max(exports, key=lambda path: path.stat().st_mtime)
        with newest.open(encoding="utf-8", errors="replace", newline="") as handle:
            sheet = list(csv.reader(handle))
        top = next((at for at, cells in enumerate(sheet) if _ASSET_COLUMN in cells), None)
        if top is None:
            return set()
        column = sheet[top].index(_ASSET_COLUMN)
        cells = (row[column].strip() for row in sheet[top + 1 :] if len(row) > column)
        return {cell for cell in cells if cell}

    def _run_public_text(self, files: list[Path]) -> tuple[list[Finding], str]:
        """Report `T008` for a `_MACHINE_PATH` or an `_export_names` value in `files`."""
        names = self._export_names()
        pattern = None
        if names:
            words = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
            pattern = re.compile(rf"(?<![A-Za-z0-9])(?:{words})(?![A-Za-z0-9])")
        findings: list[Finding] = []
        for path in files:
            if pattern is None:
                findings.append(self._undecided(path, 1, "T008", "no export to read asset names from."))
            for line, text in enumerate(self._read(path).splitlines(), 1):
                for found in (_MACHINE_PATH.search(text), pattern.search(text) if pattern else None):
                    if found:
                        findings.append(
                            Finding(
                                tool="truth",
                                severity="high",
                                file=str(path),
                                line=line,
                                rule_id="T008",
                                message=f"public text carries {found.group(0)!r}; reword it before posting.",
                            )
                        )
        return findings, "ok"

    def _run_test_statements(self, files: list[Path]) -> tuple[list[Finding], str]:
        """Report `T009` from `statement_findings` for each file in `files`."""
        findings: list[Finding] = []
        for path in files:
            findings.extend(statement_findings(path, self._read(path), self.root))
        return findings, "ok"

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

    def _state_of(
        self, number: int, states: dict[int, str], *, truncated: bool
    ) -> tuple[str | None, str]:
        """Return `number`'s state from `states` or `_gh_issue_view`, and why none."""
        if number in states or not truncated:
            return states.get(number), ""
        row, reason = self._gh_issue_view(number)
        if _UNRESOLVED_NUMBER.search(reason):
            return None, ""
        if reason:
            return None, reason
        state = row.get("state", "").upper()
        if not state:
            return None, f"gh issue view {number} returned no state"
        return state, ""

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
            state, why = self._state_of(number, states, truncated=truncated)
            if why:
                findings.append(
                    self._undecided(
                        path,
                        lineno,
                        "T003",
                        f"issue {number} is absent from a truncated listing, "
                        f"and gh issue view could not decide it: {why}.",
                    )
                )
                continue
            if state is None:
                key = (str(path), number)
                if key in reported:
                    continue
                reported.add(key)
                source = (
                    "gh issue view could not resolve it."
                    if truncated
                    else f"The listing holds {len(states)} issue and "
                    f"pull-request numbers."
                )
                findings.append(
                    Finding(
                        tool="truth",
                        severity="high",
                        file=str(path),
                        line=lineno,
                        rule_id="T003",
                        message=(
                            f"cited issue {number} does not exist in this "
                            f"repository. {source}"
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

    def subjects(self) -> re.Pattern[str] | None:
        """Return the manual's subject alternation, building it on first use."""
        if not self._subjects_built:
            manual = self.root.joinpath(*_MANUAL_PARTS)
            self._subjects = subject_pattern(manual_subject_names(manual))
            self._subjects_built = True
        return self._subjects

    def _falsification_of_scope(self) -> str:
        return (
            "(i) T007 read the wrong item, or a subject name the manual does "
            "not carry. It looks only for a name the manual gives a page or a "
            "multi-word heading, and it decides that name against the item "
            "text alone. A quotation, a link label, a table, a fence and a "
            "sentence placing the subject outside the item are all skipped, "
            "and so is a state claim about a subject the same document anchors "
            "to code, so a subject raised only in those ways is invisible to "
            "it. A completion claim is reported whether or not the document "
            "anchors the subject."
        )

    @staticmethod
    def _falsification_of_statements() -> str:
        return (
            f"(j) T009 read a block whose fence opens with {_STATEMENT_TAG} and "
            "decided its parts by form and arithmetic alone. It recomputes each "
            "count, power and seeded draw and finds each path under the root, and "
            "it never reads whether a check, a calibration input or an evidence "
            "file holds what the block says of it, nor whether the block describes "
            "the record that holds it. A block marked any other way is not read, "
            "and a record plans runs, for it, only where digits or a number word "
            "stand before runs or rounds as a count, not after a label such as "
            "step or round, outside fences, block quotes and quoted spans."
        )

    def _gh_issue_view(self, number: int) -> tuple[dict[str, str], str]:
        """Return the `gh issue view` row for `number`, or why there is none."""
        if number in self._views:
            return self._views[number]
        binary = shutil.which("gh")
        if binary is None:
            return {}, "gh is not on PATH"
        proc = subprocess.run(  # noqa: S603
            [
                binary,
                "issue",
                "view",
                str(number),
                "--json",
                "number,title,body,state",
            ],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )
        view: tuple[dict[str, str], str]
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip().replace("\n", " ")[:200]
            view = {}, f"gh issue view {number} exited {proc.returncode}: {detail}"
        else:
            try:
                row = json.loads(proc.stdout or "{}")
                view = {key: str(value or "") for key, value in row.items()}, ""
            except json.JSONDecodeError as exc:
                view = {}, f"gh issue view {number} output did not parse: {exc}"
        self._views[number] = view
        return view

    def _gh_issue_body(self, number: int) -> tuple[str, str]:
        """Return one issue's title and body, or an explanation for neither."""
        row, reason = self._gh_issue_view(number)
        if reason:
            return "", reason
        return f"{row.get('title', '')}\n{row.get('body', '')}", ""

    def _resolve_item(self, files: list[Path]) -> tuple[int | None, str, str]:
        """Return the item number, its text, and the reason there is neither.

        An explicit `item` wins; otherwise the one issue number the document
        cites that the repository listing carries is used, and no other.
        """
        if self._item is not None:
            text, reason = self._gh_issue_body(self._item)
            return (None, "", reason) if reason else (self._item, text, "")
        cited = sorted({number for _, _, number, _ in self._cited_issues(files)})
        if not cited:
            return None, "", "no item was given and the text cites no issue number"
        states, why, _ = self._issue_states()
        if not states:
            return None, "", f"the cited number(s) could not be checked: {why}"
        live = [number for number in cited if number in states]
        if len(live) != 1:
            return (
                None,
                "",
                (
                    f"{len(live)} of the {len(cited)} cited number(s) exist here "
                    f"({live}), so no single item can be chosen"
                ),
            )
        text, reason = self._gh_issue_body(live[0])
        return (None, "", reason) if reason else (live[0], text, "")

    def _subject_hits(
        self, path: Path, pattern: re.Pattern[str], item_text: str
    ) -> dict[str, list[tuple[int, str, bool, bool, str]]]:
        """Return every subject occurrence the item text does not carry.

        A state claim about a subject this document anchors to code is left
        out; a completion claim is kept whatever the document anchors.
        """
        source = self._read(path)
        code = code_text(source)
        hits: dict[str, list[tuple[int, str, bool, bool, str]]] = {}
        for sentence in _prose_sentences(source):
            plain = _plain_sentence(sentence.text)
            excluded = bool(_OUT_OF_SCOPE.search(plain))
            softened = bool(_CLAIM_SOFTENER.search(plain))
            for match in pattern.finditer(plain):
                display = " ".join(match.group(0).split())
                if not _is_titled(display) or display.lower() in item_text:
                    continue
                if _INDEFINITE.search(plain[: match.start()]):
                    continue
                claims = _claims_completion(_clause_at(plain, match.start()))
                if not claims and (
                    softened
                    or not _predicates_state(plain[match.end() :])
                    or phrase_present(display, code)
                ):
                    continue
                row = (sentence.line, sentence.text, excluded, claims, display)
                hits.setdefault(display.lower(), []).append(row)
        return hits

    def _run_scope(self, files: list[Path]) -> tuple[list[Finding], str]:
        number, item_text, reason = self._resolve_item(files)
        if number is None:
            return [
                self._undecided(
                    files[0],
                    1,
                    "T007",
                    f"the scope rule did not run: {reason}. No subject was "
                    f"decided here, and that silence is not a pass.",
                )
            ], f"unavailable: {reason}"
        pattern = self.subjects()
        if pattern is None:
            manual = "/".join(_MANUAL_PARTS)
            return [
                self._undecided(
                    files[0],
                    1,
                    "T007",
                    f"the scope rule did not run: {manual} carries no page to "
                    f"read a subject name from.",
                )
            ], f"unavailable: no manual under {manual}"

        haystack = item_text.lower()
        findings: list[Finding] = []
        for path in files:
            for rows in self._subject_hits(path, pattern, haystack).values():
                live = [row for row in rows if not row[2]]
                if not live:
                    continue
                claimed = next((row for row in live if row[3]), None)
                line, text, _, _, display = claimed or live[0]
                findings.append(
                    Finding(
                        tool="truth",
                        severity="high" if claimed else "medium",
                        file=str(path),
                        line=line,
                        rule_id="T007",
                        message=(
                            f"{display!r} is a subject item {number} does not "
                            f"name. "
                            + (
                                "The sentence claims completion about it, so "
                                "this is high."
                                if claimed
                                else "No completion is claimed about it, so "
                                "this is medium."
                            )
                            + f" Sentence: {text[:160]!r}"
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
            "generated name — the index reads definitions, not dynamic binding. "
            "The index leaves out only the top-level names .gitignore lists "
            "bare, so a copy of a cited name kept in any other ignored file "
            "still reads as a mention;",
            "(d) T003 read a listing for a repository other than the one the "
            "claim is about. A number absent from a truncated listing is looked "
            "up alone with gh issue view, and a lookup that fails for any reason "
            "but an unresolved number stays T000;",
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
            "an instrument this archetype could carry;",
            self._falsification_of_scope(),
            self._falsification_of_statements(),
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
        print("       [--item <issue number>]")
        print("       resolves the claims in a markdown/text file against the tree")
        return 2
    item: int | None = None
    if "--item" in argv:
        position = argv.index("--item")
        if position + 1 >= len(argv) or not argv[position + 1].isdigit():
            print("--item needs an issue number", file=sys.stderr)
            return 2
        item = int(argv[position + 1])
        argv = argv[:position] + argv[position + 2 :]
    if not argv:
        print("no path given", file=sys.stderr)
        return 2
    report = TruthArchetype(item=item).review(Path(argv[0]))
    print(json.dumps(report.to_dict(), indent=2))
    return cli_exit(report)


if __name__ == "__main__":
    sys.exit(main())
