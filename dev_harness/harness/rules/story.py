"""story.py — the Storyteller subtype of the Docs Archetype.

`is_story` gates DOC007 to DOC010 on a `mode: story` front-matter key.
`chronology_findings`, `voice_findings`, `plain_findings` and `honest_findings`
are the four rules `scan` runs. `unread_reasons` names what `scan` could not
read, and `MEDIAN_WORDS_CEILING`, `THE_OPENER_CEILING_PCT`,
`FIRST_PERSON_FLOOR_PCT` and `SENTENCES_PER_UNEXPLAINED_TERM` carry the measured
corpus rates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[3]

DEVELOPMENT_MAP: Path = REPO_ROOT / "docs" / "audits" / "2026-09-08_development_map.md"

# 81 blockquoted operator sentences plus 8 from his web-editor markdown commits.
OPERATOR_CORPUS_SENTENCES = 89
OPERATOR_CORPUS_WORDS = 1337

# His mean sentence. Median: his 11, the chronicle he deleted 14, docs/manual 16.
MEDIAN_WORDS_CEILING = 15

# His 5.6%, the chronicle he deleted 28.3%, docs/manual 27.6%.
THE_OPENER_CEILING_PCT = 10.0

# His 15.7%, the chronicle he deleted 2.0%, docs/manual 2.7%.
FIRST_PERSON_FLOOR_PCT = 5.0

# His unexplained terms run 6.2 per 100 sentences; the archived chronicle 27.3.
SENTENCES_PER_UNEXPLAINED_TERM = 10

MIN_SENTENCES_TO_READ_VOICE = 10

_FRONT_MATTER = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_MODE_STORY = re.compile(r"^[ \t]*mode[ \t]*:[ \t]*story[ \t]*$", re.M)

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_CODE_SHAPED = re.compile(
    r"\b(?:[a-z][a-z0-9]*_[a-z0-9_]+"
    r"|[A-Za-z][A-Za-z0-9]*\.[a-z][A-Za-z0-9_]*"
    r"|[A-Z][a-z]+[A-Z][A-Za-z]*)\b"
)
_GLOSS = re.compile(r"^\s*(?:\(|—|,\s*which\b|,\s*meaning\b|:\s)")
_FIRST_PERSON = re.compile(r"\b(I|my|me|we|our|us)\b")

_COMMIT_SHA = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")
_ISSUE_REF = re.compile(r"#\d+\b")
_REPO_PATH = re.compile(
    r"\b(?:src|tests|tools|docs|docs-archive|dev_harness|desktop|deploy|"
    r"harness_fixtures|\.github)/[A-Za-z0-9_\-./]+"
)
_THINNESS = re.compile(
    r"confidence[ \t]*:[ \t]*low"
    r"|no artefact|no artifact|the record is thin|not recorded|unrecorded",
    re.I,
)

_SKIP_PREFIXES = ("#", "|", "---", "***", "<", "!", "[")


@dataclass
class Finding:
    """One story-subtype result, shaped like every other rule module's Finding."""

    tool: str
    severity: str
    file: str
    line: int
    rule_id: str
    message: str


@dataclass
class Entry:
    """One dated heading of a story document, with the body under that heading."""

    line: int
    day: date
    heading: str
    body: str


def is_story(text: str) -> bool:
    """True when text opens with a front-matter block carrying `mode: story`."""
    match = _FRONT_MATTER.match(text)
    return bool(match) and bool(_MODE_STORY.search(match.group(1)))


def body_after_front_matter(text: str) -> tuple[str, int]:
    """Return text past its front matter and the line its body starts on."""
    match = _FRONT_MATTER.match(text)
    if not match:
        return text, 1
    return text[match.end() :], text[: match.end()].count("\n") + 1


def entries(text: str) -> list[Entry]:
    """Return every heading of text carrying an ISO date, in document order.

    An Entry takes the first date in its heading, and its body runs to the next
    dated heading.
    """
    body, offset = body_after_front_matter(text)
    lines = body.split("\n")
    heads: list[tuple[int, date, str]] = []
    for index, line in enumerate(lines):
        heading = _HEADING.match(line)
        if not heading:
            continue
        found = _ISO_DATE.search(heading.group(2))
        if not found:
            continue
        try:
            day = date.fromisoformat(found.group(1))
        except ValueError:
            continue
        heads.append((index, day, heading.group(2).strip()))
    out: list[Entry] = []
    for position, (index, day, heading) in enumerate(heads):
        end = heads[position + 1][0] if position + 1 < len(heads) else len(lines)
        out.append(
            Entry(
                line=index + offset,
                day=day,
                heading=heading,
                body="\n".join(lines[index + 1 : end]),
            )
        )
    return out


def prose_lines(text: str, keep_quotes: bool) -> list[str]:
    """Return the lines of text outside fences, headings, tables and images.

    `keep_quotes` keeps blockquoted lines, which `unexplained_terms` reads and
    `prose_sentences` drops.
    """
    body, _ = body_after_front_matter(text)
    kept: list[str] = []
    in_fence = False
    for line in body.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        stripped = line.strip()
        if in_fence or not stripped or stripped.startswith(_SKIP_PREFIXES):
            continue
        if stripped.startswith(">"):
            if not keep_quotes:
                continue
            stripped = stripped.lstrip("> ").strip()
            if not stripped:
                continue
        kept.append(stripped)
    return kept


def prose_sentences(text: str) -> list[str]:
    """Return the authored sentences of text, blockquoted lines excluded."""
    joined = " ".join(prose_lines(text, keep_quotes=False))
    joined = _INLINE_CODE.sub(" CODE ", joined)
    joined = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", joined)
    joined = re.sub(r"[*_]{1,2}", "", joined)
    return [s.strip() for s in _SENTENCE_SPLIT.split(joined) if len(s.split()) >= 3]


def unexplained_terms(text: str) -> list[tuple[int, str]]:
    """Return each code-shaped term of text whose first use carries no gloss.

    A gloss is a parenthetical, an em-dash clause, `, which`, `, meaning` or a
    colon following that term on the same line.
    """
    body, offset = body_after_front_matter(text)
    first: dict[str, tuple[int, str]] = {}
    in_fence = False
    for index, line in enumerate(body.split("\n")):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        stripped = line.strip()
        if in_fence or not stripped or stripped.startswith(_SKIP_PREFIXES):
            continue
        for match in _INLINE_CODE.finditer(stripped):
            term = match.group(1).strip()
            if term and term not in first:
                first[term] = (index + offset, stripped[match.end() :])
        bare = _INLINE_CODE.sub(" ", stripped)
        for match in _CODE_SHAPED.finditer(bare):
            term = match.group(0)
            if term not in first:
                first[term] = (index + offset, bare[match.end() :])
    return sorted(
        (line, term) for term, (line, rest) in first.items() if not _GLOSS.match(rest)
    )


def map_low_confidence_dates(map_text: str) -> set[str]:
    """Return the ISO dates map_text marks low on the same line."""
    out: set[str] = set()
    for line in map_text.split("\n"):
        if re.search(r"\blow\b", line, re.I):
            out.update(_ISO_DATE.findall(line))
    return out


def unread_reasons(text: str) -> list[str]:
    """Return why the subtype could not read text, empty when it could."""
    reasons: list[str] = []
    if not entries(text):
        reasons.append("no dated entry")
    if len(prose_sentences(text)) < MIN_SENTENCES_TO_READ_VOICE:
        reasons.append(
            f"fewer than {MIN_SENTENCES_TO_READ_VOICE} authored prose sentences"
        )
    return reasons


def chronology_findings(path: Path, text: str) -> list[Finding]:
    """Return a DOC007 finding per entry of text dated before the entry above it."""
    out: list[Finding] = []
    previous: Entry | None = None
    for entry in entries(text):
        if previous is not None and entry.day < previous.day:
            out.append(
                Finding(
                    tool="story",
                    severity="high",
                    file=str(path),
                    line=entry.line,
                    rule_id="DOC007",
                    message=(
                        f"Entry dated {entry.day.isoformat()} follows the entry "
                        f"dated {previous.day.isoformat()} at line "
                        f"{previous.line}. A story runs forward."
                    ),
                )
            )
        if previous is None or entry.day >= previous.day:
            previous = entry
    return out


def voice_findings(path: Path, text: str) -> list[Finding]:
    """Return a DOC008 finding per voice count of text outside the corpus band.

    Median sentence length, sentences opening with `The` and sentences carrying a
    first-person pronoun are the three counts.
    """
    sentences = prose_sentences(text)
    if len(sentences) < MIN_SENTENCES_TO_READ_VOICE:
        return []
    lengths = sorted(len(s.split()) for s in sentences)
    median = lengths[len(lengths) // 2]
    openers = 100.0 * sum(1 for s in sentences if s.startswith("The ")) / len(sentences)
    person = 100.0 * sum(1 for s in sentences if _FIRST_PERSON.search(s)) / len(
        sentences
    )
    corpus = (
        f"operator corpus {OPERATOR_CORPUS_SENTENCES} sentences, "
        f"{OPERATOR_CORPUS_WORDS} words"
    )
    out: list[Finding] = []
    if median > MEDIAN_WORDS_CEILING:
        out.append(
            Finding(
                tool="story",
                severity="high",
                file=str(path),
                line=1,
                rule_id="DOC008",
                message=(
                    f"Median sentence runs {median} words, over the "
                    f"{MEDIAN_WORDS_CEILING}-word ceiling ({corpus}: median 11, "
                    f"mean 15.02; docs/manual median 16)."
                ),
            )
        )
    if openers > THE_OPENER_CEILING_PCT:
        out.append(
            Finding(
                tool="story",
                severity="high",
                file=str(path),
                line=1,
                rule_id="DOC008",
                message=(
                    f"{openers:.1f}% of sentences open with 'The', over the "
                    f"{THE_OPENER_CEILING_PCT:.0f}% ceiling ({corpus}: 5.6%; "
                    f"the chronicle he deleted 28.3%; docs/manual 27.6%)."
                ),
            )
        )
    if person < FIRST_PERSON_FLOOR_PCT:
        out.append(
            Finding(
                tool="story",
                severity="high",
                file=str(path),
                line=1,
                rule_id="DOC008",
                message=(
                    f"{person:.1f}% of sentences carry I, me, my, we, our or us, "
                    f"under the {FIRST_PERSON_FLOOR_PCT:.0f}% floor ({corpus}: "
                    f"15.7%; the chronicle he deleted 2.0%; docs/manual 2.7%)."
                ),
            )
        )
    return out


def plain_findings(path: Path, text: str) -> list[Finding]:
    """Return a DOC009 finding per unexplained term when text is over its ceiling."""
    sentences = prose_sentences(text)
    if len(sentences) < MIN_SENTENCES_TO_READ_VOICE:
        return []
    terms = unexplained_terms(text)
    ceiling = max(1, len(sentences) // SENTENCES_PER_UNEXPLAINED_TERM)
    if len(terms) <= ceiling:
        return []
    return [
        Finding(
            tool="story",
            severity="high",
            file=str(path),
            line=line,
            rule_id="DOC009",
            message=(
                f"{term!r} is used and never explained. The page carries "
                f"{len(terms)} unexplained terms over {len(sentences)} "
                f"sentences; the ceiling is {ceiling}, one per "
                f"{SENTENCES_PER_UNEXPLAINED_TERM} sentences."
            ),
        )
        for line, term in terms
    ]


def honest_findings(path: Path, text: str, map_text: str = "") -> list[Finding]:
    """Return a DOC010 finding per dated entry of text with no artefact behind it.

    An Entry escapes by naming a commit, an issue number or a repo path, or by
    declaring the record thin; map_text adds the dates it marks low.
    """
    thin_dates = map_low_confidence_dates(map_text)
    out: list[Finding] = []
    for entry in entries(text):
        declared_thin = bool(_THINNESS.search(entry.body))
        has_artefact = bool(
            _COMMIT_SHA.search(entry.body)
            or _ISSUE_REF.search(entry.body)
            or _REPO_PATH.search(entry.body)
        )
        if not has_artefact and not declared_thin:
            out.append(
                Finding(
                    tool="story",
                    severity="high",
                    file=str(path),
                    line=entry.line,
                    rule_id="DOC010",
                    message=(
                        f"Entry {entry.heading!r} names a date and no artefact. "
                        f"Cite a commit, an issue number or a repo path, or say "
                        f"the record is thin."
                    ),
                )
            )
        elif entry.day.isoformat() in thin_dates and not declared_thin:
            out.append(
                Finding(
                    tool="story",
                    severity="high",
                    file=str(path),
                    line=entry.line,
                    rule_id="DOC010",
                    message=(
                        f"Entry {entry.heading!r} is told plainly, and "
                        f"{DEVELOPMENT_MAP.name} marks {entry.day.isoformat()} "
                        f"low confidence. Say the record is thin."
                    ),
                )
            )
    return out


def read_development_map() -> str:
    """Return DEVELOPMENT_MAP's text, empty when it is not on disk."""
    try:
        return DEVELOPMENT_MAP.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def scan(path: Path, src: str) -> list[Finding]:
    """Return every DOC007 to DOC010 finding for src, empty when src is no story."""
    if not is_story(src):
        return []
    map_text = read_development_map()
    return (
        chronology_findings(path, src)
        + voice_findings(path, src)
        + plain_findings(path, src)
        + honest_findings(path, src, map_text)
    )
