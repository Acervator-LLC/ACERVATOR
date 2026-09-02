"""Report every comment window breaking the length, sentence, noun or naming rule."""

from __future__ import annotations

import re
import sys
from pathlib import Path

MAX_WORDS = 20
BLOCK_LOOK = 12

BANNED = {
    "gate",
    "gates",
    "plant",
    "plants",
    "planted",
    "blind",
    "fires",
    "holder",
    "holders",
    "reader",
    "readers",
    "harness",
    "island",
    "islands",
    "ratchet",
    "seam",
    "seams",
    "sibling",
    "siblings",
    "honest",
    "control",
    "controls",
}

KEYWORDS = {
    "a",
    "an",
    "and",
    "as",
    "assert",
    "class",
    "def",
    "else",
    "false",
    "for",
    "from",
    "function",
    "if",
    "import",
    "in",
    "is",
    "it",
    "new",
    "not",
    "null",
    "of",
    "one",
    "or",
    "return",
    "so",
    "that",
    "the",
    "this",
    "to",
    "true",
    "typeof",
    "undefined",
    "var",
    "which",
    "while",
}

WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
SENTENCE_END = re.compile(r"[.!?]")
CAMEL_SPLIT = re.compile(r"_|(?<=[a-z0-9])(?=[A-Z])")

LINE_COMMENT = "//"


def words_of(text: str) -> list:
    """Every identifier-shaped word of one string."""
    return WORD.findall(text)


def name_pieces(text: str) -> set:
    """Every word and every camel or snake piece of one block, lowercased."""
    found: set = set()
    for word in words_of(text):
        found.add(word.lower())
        for piece in CAMEL_SPLIT.split(word):
            if piece:
                found.add(piece.lower())
    return found


def sentence_count(text: str) -> int:
    """How many sentences one text holds, an unpunctuated text counting as one."""
    stripped = text.strip()
    if not stripped:
        return 0
    marks = len(SENTENCE_END.findall(stripped))
    return marks if marks else 1


def js_windows(lines: list) -> list:
    """Every run of adjacent slash comment lines, and where the run ends."""
    found = []
    body: list = []
    start = 0
    for at, line in enumerate(lines):
        if line.strip().startswith(LINE_COMMENT):
            if not body:
                start = at
            body.append(line.strip()[len(LINE_COMMENT) :].strip())
            continue
        if body:
            found.append((start, at, " ".join(body)))
            body = []
    if body:
        found.append((start, len(lines), " ".join(body)))
    return found


def py_windows(lines: list) -> list:
    """Every run of adjacent hash lines and every docstring, each one window."""
    found = []
    body: list = []
    start = 0
    inside = ""
    doc: list = []
    doc_start = 0
    for at, line in enumerate(lines):
        stripped = line.strip()
        if inside:
            doc.append(stripped)
            if inside in stripped:
                found.append((doc_start, at + 1, " ".join(doc).replace(inside, " ")))
                inside = ""
                doc = []
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            mark = stripped[:3]
            rest = stripped[3:]
            if mark in rest:
                found.append((at, at + 1, rest.split(mark)[0]))
                continue
            inside = mark
            doc = [rest]
            doc_start = at
            continue
        if stripped.startswith("#"):
            if not body:
                start = at
            body.append(stripped.lstrip("#:").strip())
            continue
        if body:
            found.append((start, at, " ".join(body)))
            body = []
    if body:
        found.append((start, len(lines), " ".join(body)))
    return found


def block_text(lines: list, end: int) -> str:
    """The code under one window, every comment line blanked out first."""
    kept = []
    for line in lines[end:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        kept.append(line)
        if len(kept) >= BLOCK_LOOK:
            break
    return " ".join(kept)


def faults_of(path: Path) -> list:
    """Every rule one path breaks, as a line number, a kind and a detail."""
    lines = path.read_text(encoding="utf-8").splitlines()
    windows = js_windows(lines) if path.suffix == ".js" else py_windows(lines)
    whole = name_pieces(" ".join(lines)) - KEYWORDS
    found = []
    for start, end, body in windows:
        if not body.strip():
            continue
        spelled = words_of(body)
        if len(spelled) > MAX_WORDS:
            found.append((start + 1, "long", str(len(spelled)) + " words"))
        if sentence_count(body) != 1:
            found.append((start + 1, "sentences", str(sentence_count(body))))
        banned = sorted({one.lower() for one in spelled} & BANNED)
        if banned:
            found.append((start + 1, "banned", ", ".join(banned)))
        named = {one.lower() for one in spelled} - KEYWORDS
        reach = whole if start == 0 else name_pieces(block_text(lines, end)) - KEYWORDS
        if named and not (named & reach):
            found.append((start + 1, "names-nothing", body[:60]))
    return found


def main(argv: list) -> int:
    """Print one line for every fault in every file named, and count them."""
    total = 0
    windows = 0
    for one in argv:
        path = Path(one)
        lines = path.read_text(encoding="utf-8").splitlines()
        windows += len(js_windows(lines) if path.suffix == ".js" else py_windows(lines))
        for line, kind, detail in faults_of(path):
            total += 1
            print(path.name + ":" + str(line) + " " + kind + " -- " + detail)
    print(
        str(windows) + " windows in " + str(len(argv)) + " files, faults: " + str(total)
    )
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
