"""`check` runs ruff on one file; `listing`, `fix_class` and `rule_page` read rule pages."""

import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import NamedTuple

from .core import tool_text

RUFF_BUILT = "0.16.0"
RUFF_TIMEOUT_S = 120
TOOL_EXITS = frozenset({0})
CHECK_EXITS = frozenset({0, 1})
FIX_CLASSES = {"Always": "always", "Sometimes": "sometimes", "None": "none"}
REMOVED = "Removed"
EXAMPLE = "## Example"
SECTION = "\n## "
USE_INSTEAD = "Use instead"
FORM_FENCES = ("python", "py", "pyi", "toml")

_BLOCK_RE = re.compile(rf"```(?:{'|'.join(FORM_FENCES)})\n(.*?)```", re.DOTALL)
_HEADING_RE = re.compile(rf"^{re.escape(USE_INSTEAD)}.*$", re.MULTILINE)


class ToolFault(Exception):
    """`python -m ruff` did not run, or printed output this module cannot read."""


class Diagnostic(NamedTuple):
    """One `check` finding: rule `code`, rule `name` and `line`."""

    code: str
    name: str
    line: int


class Listed(NamedTuple):
    """One rule `listing` reads: its `fix` class, and whether it is a `preview` or `removed` rule."""

    fix: str
    preview: bool
    removed: bool


@dataclass(frozen=True)
class RulePage:
    """One rule's `name`, `fix` class, and published `faulty` and `corrected` forms."""

    name: str
    fix: str
    faulty: str
    corrected: str


def _ruff(
    label: str,
    args: Sequence[str],
    *,
    exits: frozenset[int] = TOOL_EXITS,
    source: bytes | None = None,
    folder: Path | None = None,
) -> bytes:
    """Return ruff's stdout for `args`, or raise `ToolFault` naming `label`."""
    try:
        proc = subprocess.run(
            [sys.executable, "-P", "-m", "ruff", *args],
            input=source,
            cwd=folder,
            capture_output=True,
            timeout=RUFF_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = f"{label}: {exc}"
        raise ToolFault(message) from exc
    if proc.returncode not in exits:
        said = tool_text(proc.stderr or proc.stdout)
        message = f"{label} exited {proc.returncode}: {said}"
        raise ToolFault(message)
    return proc.stdout


@cache
def ruff_version() -> str:
    """Return the version `python -m ruff --version` prints, or raise `ToolFault`."""
    printed = tool_text(_ruff("ruff --version", ["--version"]))
    words = printed.split()
    if len(words) != 2 or words[0] != "ruff":
        message = f"ruff --version printed no version: {printed}"
        raise ToolFault(message)
    return words[1]


@cache
def listing() -> dict[str, Listed]:
    """Return each rule code's `Listed` row from `python -m ruff rule --all`."""
    printed = _ruff("ruff rule --all", ["rule", "--all", "--output-format", "json"])
    try:
        return {
            rule["code"]: Listed(
                FIX_CLASSES[rule["fix_availability"]],
                bool(rule["preview"]),
                REMOVED in rule["status"],
            )
            for rule in json.loads(printed)
        }
    except (ValueError, KeyError, TypeError) as exc:
        message = f"ruff rule --all printed an unreadable rule: {exc!r}"
        raise ToolFault(message) from exc


def fix_class(code: str) -> str:
    """Return rule `code`'s fix class from `listing`, or raise `ToolFault`."""
    try:
        return listing()[code].fix
    except KeyError as exc:
        message = f"ruff rule --all lists no rule {code}"
        raise ToolFault(message) from exc


def _example_section(explanation: str) -> str:
    """Return the `EXAMPLE` section, else the first one with a `USE_INSTEAD` line."""
    if EXAMPLE in explanation:
        return explanation.partition(EXAMPLE)[2].split(SECTION, 1)[0]
    sections = explanation.split(SECTION)
    return next((section for section in sections if _HEADING_RE.search(section)), "")


def _published_forms(example: str) -> tuple[str, str] | None:
    """Return `example` blocks above and below its first `USE_INSTEAD` line, or None."""
    heading = _HEADING_RE.search(example)
    if heading is None:
        return None
    faulty_blocks = _BLOCK_RE.findall(example[: heading.start()])
    corrected_blocks = _BLOCK_RE.findall(example[heading.end() :])
    if not (faulty_blocks and corrected_blocks):
        return None
    return "".join(faulty_blocks), "".join(corrected_blocks)


@cache
def rule_page(code: str) -> RulePage:
    """Return the `RulePage` that `python -m ruff rule <code>` prints as JSON."""
    printed = _ruff(f"ruff rule {code}", ["rule", code, "--output-format", "json"])
    try:
        page = json.loads(printed)
        name = page["name"]
        fix = FIX_CLASSES.get(page["fix_availability"])
        forms = _published_forms(_example_section(page["explanation"]))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        message = f"ruff rule {code} printed an unreadable page: {exc!r}"
        raise ToolFault(message) from exc
    if fix is None or forms is None:
        message = f"ruff rule {code} prints no fix class or no {EXAMPLE} form"
        raise ToolFault(message)
    return RulePage(name, fix, *forms)


def check(
    source: bytes, folder: Path, selectors: Sequence[str], *, preview: bool
) -> list[Diagnostic]:
    """Return each `Diagnostic` of `selectors` for `source` on stdin, from `folder`."""
    printed = _ruff(
        "ruff check",
        [
            "check",
            "--no-cache",
            "--no-fix",
            *(["--preview"] if preview else []),
            "--output-format",
            "json",
            "--select",
            ",".join(selectors),
            "-",
        ],
        exits=CHECK_EXITS,
        source=source,
        folder=folder,
    )
    selected = tuple(selectors)
    try:
        return [
            Diagnostic(row["code"], row["name"], row["location"]["row"])
            for row in json.loads(printed)
            if isinstance(row["code"], str) and row["code"].startswith(selected)
        ]
    except (ValueError, KeyError, TypeError) as exc:
        message = f"ruff check printed an unreadable finding: {exc!r}"
        raise ToolFault(message) from exc
