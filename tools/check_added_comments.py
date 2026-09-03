"""Judge every comment a branch adds against the repository's comment rule."""

from __future__ import annotations

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

from tools.gate import _git

WORD_CAP = 20
SENTENCE_CAP = 1

BANNED_WORDS = (
    "gate",
    "plant",
    "planted",
    "blind",
    "fires",
    "holder",
    "reader",
    "harness",
    "island",
    "ratchet",
    "seam",
    "sibling",
    "honest",
    "control",
)

BASE_REF = "origin/current"

PYTHON_SUFFIX = ".py"
JS_SUFFIX = ".js"
CHECKED_SUFFIXES = (PYTHON_SUFFIX, JS_SUFFIX)

RENAME_ARROW = " -> "
STATUS_NAME_AT = 3

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")
WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

COMMENT_KIND = "comment"
DOCSTRING_KIND = "docstring"


def changed_files(root: Path) -> list:
    """Every file this branch adds or changes, discovered from git alone."""
    found: set = set()
    for line in _git("status", "--porcelain").splitlines():
        name = line[STATUS_NAME_AT:].strip().strip('"')
        if RENAME_ARROW in name:
            name = name.split(RENAME_ARROW)[-1]
        found.add(name)
    for line in _git("diff", "--name-only", "--diff-filter=d", BASE_REF).splitlines():
        found.add(line.strip())
    return sorted(
        one
        for one in found
        if one.endswith(CHECKED_SUFFIXES) and (root / one).is_file()
    )


def added_lines(name: str, root: Path) -> set:
    """The line numbers this branch added to one file."""
    diff = _git("diff", "-U0", BASE_REF, "--", name)
    if not diff.strip():
        text = (root / name).read_text(encoding="utf-8", errors="replace")
        return set(range(1, len(text.splitlines()) + 1))
    found: set = set()
    at = 0
    for line in diff.splitlines():
        head = HUNK.match(line)
        if head:
            at = int(head.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            found.add(at)
            at += 1
        elif not line.startswith("-") and not line.startswith("\\"):
            at += 1
    return found


def comment_blocks(source: str) -> list:
    """Every run of neighbouring `#` lines, joined into one comment."""
    found = []
    block: list = []
    previous = None
    start = 0
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        text = token.string.lstrip("#").strip()
        if previous is not None and token.start[0] == previous + 1 and block:
            block.append(text)
        else:
            if block:
                found.append((COMMENT_KIND, start, " ".join(block)))
            block = [text]
            start = token.start[0]
        previous = token.start[0]
    if block:
        found.append((COMMENT_KIND, start, " ".join(block)))
    return found


def docstrings(source: str) -> list:
    """Every module, class and function docstring, with the line it starts on."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        text = ast.get_docstring(node, clean=True)
        if text:
            found.append((DOCSTRING_KIND, node.body[0].lineno, text))
    return found


def python_comments(source: str) -> list:
    """Every comment and docstring one module carries."""
    return comment_blocks(source) + docstrings(source)


def js_comments(source: str) -> list:
    """Every run of neighbouring `//` lines, joined into one comment."""
    found = []
    block: list = []
    start = 0
    for number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//"):
            if not block:
                start = number
            block.append(stripped.lstrip("/").strip())
            continue
        if block:
            found.append((COMMENT_KIND, start, " ".join(block)))
            block = []
    if block:
        found.append((COMMENT_KIND, start, " ".join(block)))
    return found


def sentences(text: str) -> int:
    """How many sentences one comment carries."""
    body = " ".join(text.split())
    if not body:
        return 0
    return max(1, len(SENTENCE_END.findall(body)))


def words(text: str) -> int:
    """How many words one comment carries."""
    return len(WORD.findall(text))


def banned(text: str) -> list:
    """Every banned word one comment carries."""
    lowered = {one.lower() for one in WORD.findall(text)}
    return sorted(one for one in BANNED_WORDS if one in lowered)


def breaks(text: str) -> list:
    """Every way one comment breaks the rule."""
    found = []
    count = sentences(text)
    if count > SENTENCE_CAP:
        found.append(f"{count} sentences, cap {SENTENCE_CAP}")
    length = words(text)
    if length > WORD_CAP:
        found.append(f"{length} words, cap {WORD_CAP}")
    carried = banned(text)
    if carried:
        found.append("banned: " + ", ".join(carried))
    return found


def check(root: Path) -> list:
    """Every added comment that breaks the rule, across the whole branch."""
    reported = []
    for name in changed_files(root):
        source = (root / name).read_text(encoding="utf-8", errors="replace")
        lines = added_lines(name, root)
        if not lines:
            continue
        read = python_comments if name.endswith(PYTHON_SUFFIX) else js_comments
        try:
            carried = read(source)
        except (SyntaxError, tokenize.TokenError) as bad:
            reported.append((name, 0, "unreadable", str(bad)))
            continue
        for kind, at, text in carried:
            span = set(range(at, at + text.count("\n") + 2))
            if span & lines:
                reported.extend((name, at, kind, one) for one in breaks(text))
    return sorted(reported)


def main() -> int:
    """Print every break and answer 1 when the branch carries one."""
    root = Path(_git("rev-parse", "--show-toplevel"))
    names = changed_files(root)
    print(f"[added-comments] {len(names)} changed file(s) discovered from git")
    reported = check(root)
    for name, at, kind, reason in reported:
        print(f"{name}:{at} [{kind}] {reason}")
    print(f"[added-comments] {len(reported)} break(s)")
    return 1 if reported else 0


if __name__ == "__main__":
    sys.exit(main())
