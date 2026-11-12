"""`SIGIL` is CODE.LOOP on the `core` card; `loop_check` judges one input line."""

import ast
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from importlib import metadata
from pathlib import Path

from .coding_input import (
    CONTENT_TIER,
    DATA_TYPE_TIER,
    INPUT_FORM,
    OWNER,
    READERS,
    SEPARATOR,
    data_type_fault,
    fault_file,
    locate,
)
from .core import (
    APPLICATION_SOURCE,
    FLAGS,
    Flag,
    FlagRow,
    Reading,
    Sigil,
    Verdict,
    in_application_source,
    judge,
    main,
    tool_text,
)

CLEAN = "CLEAN"
FINDINGS = "FINDINGS"
REJECTED = "REJECTED"

RUFF_BUILT = "0.16.0"
RUFF_TIMEOUT_S = 120
RULES = (
    "ASYNC110",
    "B035",
    "C416",
    "C419",
    "C420",
    "SIM911",
    "PERF102",
    "PERF402",
    "PLC0206",
    "PLE4703",
    "PLR1733",
    "PLR1736",
    "PLW0120",
    "UP028",
    "FURB122",
    "FURB129",
    "FURB140",
    "FURB142",
    "RUF006",
)
PREVIEW = ("PLE4703", "FURB140", "FURB142")
ERROR_CLASS = "PLE"
HOLDING = tuple(code for code in RULES if code.startswith(ERROR_CLASS))
FOLLOW_ON = {
    "always": "apply ruff's fix for that rule and read the file again",
    "sometimes": "the same, where ruff offers it for that line",
    "none": "a unit of work",
}
BY_FIX_CLASS = "; by fix class: " + "; ".join(
    f"{fix} -> {rule}" for fix, rule in FOLLOW_ON.items()
)
LOOP_NODES = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)
NO_LOOP = (
    "no for, async for, while, list, set or dictionary builder, "
    "or generator expression"
)
EXAMPLE = "## Example"
USE_INSTEAD = "Use instead:"

_BLOCK_RE = re.compile(r"```python\n(.*?)```", re.DOTALL)

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "ruff_version": RUFF_BUILT,
    "rules": " ".join(RULES),
    "preview_rules": " ".join(PREVIEW),
    "holding_rules": " ".join(HOLDING),
    "error_class": ERROR_CLASS,
    "fault_file": "the file the input line names: FINDINGS reads HOLD when it sits "
    "in application_source and one of holding_rules fires",
    "ruff_config": "the one ruff finds from the folder of the file",
}


class ToolFault(Exception):
    """`python -m ruff` did not run, or printed output this module cannot read."""


@dataclass(frozen=True)
class RulePage:
    """One rule's `name`, `fix` class, and published `faulty` and `corrected` forms."""

    name: str
    fix: str
    faulty: str
    corrected: str


@cache
def ruff_version() -> str:
    """Return the installed ruff version `python -P -m ruff` runs."""
    try:
        return metadata.version("ruff")
    except metadata.PackageNotFoundError as exc:
        message = f"ruff is not installed: {exc}"
        raise ToolFault(message) from exc


def _published_forms(explanation: str) -> tuple[str, str] | None:
    """Return the code under `EXAMPLE`, before and after `USE_INSTEAD`, or None."""
    example = explanation.partition(EXAMPLE)[2].split("\n## ", 1)[0]
    faulty, marker, corrected = example.partition(USE_INSTEAD)
    faulty_blocks = _BLOCK_RE.findall(faulty)
    corrected_blocks = _BLOCK_RE.findall(corrected)
    if not (marker and faulty_blocks and corrected_blocks):
        return None
    return "".join(faulty_blocks), "".join(corrected_blocks)


@cache
def rule_page(code: str) -> RulePage:
    """Return the `RulePage` that `python -m ruff rule <code>` prints as JSON."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-P",
                "-m",
                "ruff",
                "rule",
                code,
                "--output-format",
                "json",
            ],
            capture_output=True,
            timeout=RUFF_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = f"ruff rule {code}: {exc}"
        raise ToolFault(message) from exc
    if proc.returncode != 0:
        said = tool_text(proc.stderr or proc.stdout)
        message = f"ruff rule {code} exited {proc.returncode}: {said}"
        raise ToolFault(message)
    try:
        page = json.loads(proc.stdout)
        name = page["name"]
        fix = page["fix_availability"].lower()
        forms = _published_forms(page["explanation"])
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        message = f"ruff rule {code} printed an unreadable page: {exc!r}"
        raise ToolFault(message) from exc
    if fix not in FOLLOW_ON or forms is None:
        message = f"ruff rule {code} prints no fix class or no {EXAMPLE} form"
        raise ToolFault(message)
    return RulePage(name, fix, *forms)


def _ruff_findings(source: bytes, folder: Path) -> list[tuple[str, int]]:
    """Return each `RULES` code and line for `source` on stdin, run from `folder`."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-P",
                "-m",
                "ruff",
                "check",
                "--no-cache",
                "--preview",
                "--output-format",
                "json",
                "--select",
                ",".join(RULES),
                "-",
            ],
            input=source,
            cwd=folder,
            capture_output=True,
            timeout=RUFF_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = f"ruff check: {exc}"
        raise ToolFault(message) from exc
    if proc.returncode not in {0, 1}:
        said = tool_text(proc.stderr or proc.stdout)
        message = f"ruff check exited {proc.returncode}: {said}"
        raise ToolFault(message)
    try:
        return [
            (row["code"], row["location"]["row"])
            for row in json.loads(proc.stdout)
            if row["code"] in RULES
        ]
    except (ValueError, KeyError, TypeError) as exc:
        message = f"ruff check printed an unreadable finding: {exc!r}"
        raise ToolFault(message) from exc


def _content_fault(text: str, root: Path) -> str | None:
    """Return the tier 2 fault of `text`: `locate`'s, else `NO_LOOP`."""
    located = locate(text, root)
    if isinstance(located, str):
        return located
    _, source, (first, last) = located
    has_loop = any(
        isinstance(node, LOOP_NODES) and first <= node.lineno <= last
        for node in ast.walk(ast.parse(source))
    )
    return None if has_loop else NO_LOOP


def _functions_verdict(text: str, root: Path) -> Reading:
    """Return `CLEAN`, or `FINDINGS` holding when a `HOLDING` rule fires."""
    located = locate(text, root)
    if isinstance(located, str):
        message = f"{text}: {located}, after tier 2 accepted it"
        raise ToolFault(message)
    file, source, (first, last) = located
    is_narrowed = bool(text.partition(SETTINGS["separator"])[1])
    findings = [
        (code, line)
        for code, line in _ruff_findings(source, file.parent)
        if not is_narrowed or first <= line <= last
    ]
    version = f"ruff {ruff_version()}"
    if not findings:
        return Reading(CLEAN, f"{version}: no rule on the list fires", holds=False)
    pages = {code: rule_page(code) for code, _ in findings}
    rows = "; ".join(
        f"{code} {pages[code].name} line {line} fix {pages[code].fix}"
        for code, line in findings
    )
    forms = "".join(
        f"\n{code} faulty:\n{page.faulty}{code} corrected:\n{page.corrected}"
        for code, page in pages.items()
    )
    holds = any(code in HOLDING for code in pages)
    return Reading(FINDINGS, f"{version}: {rows}{forms}", holds)


SIGIL = Sigil(
    name="CODE.LOOP",
    edition=1,
    owner=OWNER,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        {
            **CONTENT_TIER,
            "narrowed": "Python's ast module finds a for, async for, while, list, "
            "set or dictionary builder, or generator expression in the input's lines",
            "narrowed_rejects": [NO_LOOP],
        },
        {
            "runs": [
                "python -m ruff check --preview --select with the rules, "
                "the file on standard input, from the folder of the file",
                "for a symbol, only the findings inside its lines",
                "python -m ruff rule <code> --output-format json, for each rule "
                "that fires: its name, fix class, and the code under Example, "
                "before and after Use instead",
            ],
            "clean": "no rule on the list fires",
            "findings": [
                "rule id",
                "rule name",
                "line",
                "fix class",
                "faulty form",
                "corrected form",
            ],
            "fix_classes": list(FOLLOW_ON),
            "preview": "the preview_rules fire only with --preview",
            "not_read": "a ruff setting matched on the file name, such as "
            "per-file-ignores, because the file reaches ruff on standard input",
            "refuses": "ruff exits otherwise, or prints a finding or a rule page "
            "this module cannot read",
        },
    ),
    outputs={
        CLEAN: FlagRow(Flag.PASS),
        FINDINGS: FlagRow(Flag.FIX, holds_in_source=True),
    },
    refusal=REJECTED,
    follows={
        flag: FLAGS[flag]["follows"] + BY_FIX_CLASS for flag in (Flag.HOLD, Flag.FIX)
    },
    readers=READERS,
    data_type=data_type_fault,
    content=_content_fault,
    functions=_functions_verdict,
    fault_file=fault_file,
)


def loop_check(
    text: str, root: Path, source: Sequence[str] = APPLICATION_SOURCE
) -> Verdict:
    """Return the `judge` verdict of `SIGIL` for one input line under `root`."""
    named = fault_file(text, root)
    in_source = named is not None and in_application_source(named, root, source)
    return judge(SIGIL, text, root, in_source=in_source)


def run(argv: list[str] | None = None) -> int:
    """Return `main` for `SIGIL`, or 1 with the `ToolFault` on stderr."""
    try:
        return main(SIGIL, argv)
    except ToolFault as exc:
        print(f"ruff did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
