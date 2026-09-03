"""Checks each comment and docstring on this branch for words, sentences and columns."""

from __future__ import annotations

import ast
import io
import re
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GIT = shutil.which("git") or "git"

MAX_WORDS = 20
MAX_COLUMNS = 88
MIN_SHARED = 3
BLOCK_LINES = 25

BANNED = (
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
)

WORD = re.compile(r"[A-Za-z][A-Za-z'`_-]*")
SENTENCE_END = re.compile(r"[.!?](?=\s)|[.!?]$")
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CAMEL = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")

PY_SUFFIX = ".py"
JS_SUFFIX = ".js"

#: A directive a tool reads, which carries no prose to check.
MACHINE_MARK = "pragma:"


def branch_files() -> list:
    """Every file this branch adds or changes, asked of git each run."""
    found: set = set()
    base = subprocess.run(
        [GIT, "merge-base", "HEAD", "origin/current"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if base:
        committed = subprocess.run(
            [GIT, "diff", "--name-only", base, "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
        found.update(line.strip() for line in committed.stdout.splitlines())
    working = subprocess.run(
        [GIT, "status", "--porcelain", "--untracked-files=all"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    for line in working.stdout.splitlines():
        name = line[3:].strip().strip('"')
        if " -> " in name:
            name = name.split(" -> ")[-1]
        found.add(name)
    return sorted(name for name in found if name)


def words_of(text: str) -> list:
    """Every word of a comment, hyphens and apostrophes kept whole."""
    return WORD.findall(text)


def sentence_count(text: str) -> int:
    """How many sentences one comment holds, an ending mark each."""
    body = text.strip()
    if not body:
        return 0
    return max(len(SENTENCE_END.findall(body)), 1)


def block_words(lines: list, start: int, stop: int) -> set:
    """Every word the code under a comment names, split on case and score."""
    found: set = set()
    for line in lines[start:stop]:
        for name in IDENTIFIER.findall(line):
            for part in CAMEL.findall(name) + name.split("_"):
                if len(part) >= MIN_SHARED:
                    found.add(part.lower())
    return found


def faults_in_text(text: str, where: str, names: set) -> list:
    """Every rule one comment breaks, named with where it was found."""
    found: list = []
    body = " ".join(text.split())
    spoken = words_of(body)
    if len(spoken) > MAX_WORDS:
        found.append(f"{where}: {len(spoken)} words, over {MAX_WORDS}")
    if sentence_count(body) != 1:
        found.append(f"{where}: {sentence_count(body)} sentences, not 1")
    banned = sorted({w.lower() for w in spoken} & set(BANNED))
    if banned:
        found.append(f"{where}: banned word {banned}")
    shared = {w.lower() for w in spoken if len(w) >= MIN_SHARED} & names
    if not shared and spoken:
        found.append(f"{where}: names nothing in the block")
    return found


def python_comments(source: str) -> list:
    """Every real Python comment, so a hash inside a string is not one."""
    found = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                whole = not token.line[: token.start[1]].strip()
                found.append((token.start[0], token.string[1:], whole))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return found
    return found


def script_comments(source: str) -> list:
    """Every JavaScript line comment, quotes skipped so a slash inside stays."""
    found = []
    quotes = "'\"`"
    index = 0
    end = len(source)
    line = 1
    column = 0
    while index < end:
        char = source[index]
        if char == "\n":
            line += 1
            column = 0
            index += 1
            continue
        if source.startswith("/*", index):
            stop = source.find("*/", index + 2)
            stop = end if stop < 0 else stop + 2
            line += source.count("\n", index, stop)
            index = stop
            continue
        if source.startswith("//", index):
            stop = source.find("\n", index)
            stop = end if stop < 0 else stop
            found.append((line, source[index + 2 : stop], column == 0))
            index = stop
            continue
        if char in quotes:
            cursor = index + 1
            while cursor < end and source[cursor] != char:
                cursor += 2 if source[cursor] == "\\" else 1
            line += source.count("\n", index, cursor)
            index = cursor + 1
            continue
        column += 0 if char in " \t" and column == 0 else 1
        index += 1
    return found


def comment_windows(source: str, mark: str) -> list:
    """Every run of comment lines, a run ending at code or a blank line."""
    lines = source.splitlines()
    comments = script_comments(source) if mark == "//" else python_comments(source)
    windows = []
    run: list = []
    start = 0
    end = 0
    for number, text, whole in comments:
        joins = whole and run and number == end + 1 and lines[number - 2].strip()
        if joins:
            end = number
            run.append(text)
            continue
        if run:
            windows.append((start, end, "\n".join(run)))
            run = []
        if not whole:
            windows.append((number, number, text))
            continue
        start = number
        end = number
        run = [text]
    if run:
        windows.append((start, end, "\n".join(run)))
    return windows


def docstrings(source: str) -> list:
    """Every real docstring, found by parsing rather than by matching quotes."""
    found: list = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return found
    holders = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        text = ast.get_docstring(node, clean=False)
        if text is None:
            continue
        first = node.body[0]
        found.append((first.lineno, getattr(first, "end_lineno", first.lineno), text))
    return found


def check_file(path: Path) -> list:
    """Every fault one file holds, comments, docstrings and long lines."""
    name = path.name
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    found: list = []
    for number, line in enumerate(lines, 1):
        if len(line) > MAX_COLUMNS:
            found.append(f"{name}:{number}: {len(line)} columns, over {MAX_COLUMNS}")
    mark = "//" if path.suffix == JS_SUFFIX else "#"
    for number, end, text in comment_windows(source, mark):
        body = text.strip()
        if not body or body.startswith("!") or body.startswith(MACHINE_MARK):
            continue
        names = block_words(lines, end, end + BLOCK_LINES)
        found.extend(faults_in_text(text, f"{name}:{number}", names))
    if path.suffix == PY_SUFFIX:
        for number, end, text in docstrings(source):
            names = block_words(lines, max(number - 2, 0), number - 1)
            names |= block_words(lines, end, end + BLOCK_LINES)
            found.extend(faults_in_text(text, f"{name}:{number}", names))
    return found


SELF_CASES = {
    "too many words": (
        "# one two three four five six seven eight nine ten eleven twelve"
        " thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
        " twenty alpha\ndef alpha():\n    pass\n"
    ),
    "two sentences": "# Alpha runs. Beta runs.\ndef alpha():\n    pass\n",
    "banned noun": "# The gate for alpha.\ndef alpha():\n    pass\n",
    "names nothing": "# Nothing whatsoever here.\ndef alpha():\n    pass\n",
    "long line": "# Alpha " + "x" * 90 + "\ndef alpha():\n    pass\n",
}

CLEAN_CASE = '"""Return alpha doubled."""\n\n\ndef alpha(value):\n    return value\n'

WINDOW_CASES = {
    "a blank line ends a window": (
        "# Alpha runs.\n\n# Beta runs.\ndef alpha():\n    pass\n"
    ),
    "code ends a window": (
        "# Alpha runs.\ndef alpha():\n    pass\n# Beta runs.\ndef beta():\n    pass\n"
    ),
    "a trailing comment stays apart": (
        "# Alpha runs.\ndef alpha():\n    pass  # Beta runs.\n"
    ),
    "two runs with no blank line join": ("# Alpha runs\n# again.\ndef alpha():\n"),
}

#: How many windows each case above must produce, paired by name.
WINDOW_COUNTS = {
    "a blank line ends a window": 2,
    "code ends a window": 2,
    "a trailing comment stays apart": 2,
    "two runs with no blank line join": 1,
}


def selfcheck(scratch: Path) -> int:
    """Show the checker reporting one fault of each kind and staying quiet."""
    failures = 0
    for label, body in sorted(SELF_CASES.items()):
        probe = scratch / "case.py"
        probe.write_text(body, encoding="utf-8")
        found = check_file(probe)
        print(f"  {label:20s} -> {len(found)} fault(s): {found}")
        if not found:
            print(f"    REPORTED NOTHING on {label}")
            failures += 1
    probe = scratch / "case.py"
    probe.write_text(CLEAN_CASE, encoding="utf-8")
    found = check_file(probe)
    print(f"  {'a clean docstring':20s} -> {len(found)} fault(s): {found}")
    if found:
        print("    REPORTED A FAULT ON A CLEAN DOCSTRING")
        failures += 1
    if sorted(WINDOW_CASES) != sorted(WINDOW_COUNTS):
        print("    THE TWO WINDOW TABLES NAME DIFFERENT CASES")
        failures += 1
    for label, body in sorted(WINDOW_CASES.items()):
        windows = comment_windows(body, "#")
        print(f"  {label:34s} -> {len(windows)} window(s): {windows}")
        if len(windows) != WINDOW_COUNTS[label]:
            print(f"    WRONG WINDOW COUNT on {label}")
            failures += 1
    probe.unlink(missing_ok=True)
    return failures


def main() -> int:
    scratch = Path(__file__).resolve().parent
    if "--selfcheck" in sys.argv:
        print("-- the checker reporting on one fault of each kind --")
        return selfcheck(scratch)
    names = branch_files()
    print(f"git named {len(names)} changed file(s)")
    if "--list" in sys.argv:
        for name in names:
            print("  " + name)
        return 0
    checked = 0
    faults = []
    for name in names:
        path = REPO / name
        if not path.exists() or path.suffix not in (PY_SUFFIX, JS_SUFFIX):
            continue
        checked += 1
        found = check_file(path)
        if found:
            faults.extend(found)
    print(f"checked {checked} file(s), {len(faults)} fault(s)")
    for line in faults:
        print("  " + line)
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
