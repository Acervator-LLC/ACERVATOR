"""`measure` reads each Coding Archetype rule's partition keys from its published examples and writes `KEYS_FILE`."""

import argparse
import ast
import importlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from dev_harness.harness import coding_archetype, report

from . import coding_house
from .core import tool_text
from .ruff_rules import _BLOCK_RE, _HEADING_RE, _example_section

KEYS_FILE = coding_house.HOUSE / "partition.json"
SIZES = ("statement", "scope", "module", "project")
KINDS = ("source", "test", "stub", "notebook")
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
IMPORTS = (ast.Import, ast.ImportFrom, ast.alias)
TOOL_TIMEOUT_S = 1800
RUFF_TARGET = "py314"
BANDIT_EXAMPLES = "bandit/examples"
SEMGREP_TESTS = "semgrep-rules"
SEMGREP_CONFIGS = ("p_python.yaml", "p_security-audit.yaml")
MYPY_DOCS = ("mypy_docs/error_code_list.rst", "mypy_docs/error_code_list2.rst")
MYPY_FLAGS = (
    "--show-error-codes",
    "--no-color-output",
    "--no-error-summary",
    "--follow-imports=silent",
    "--disallow-untyped-defs",
    "--disallow-incomplete-defs",
    "--warn-return-any",
    "--warn-unused-ignores",
    "--show-column-numbers",
    "--show-error-end",
)
FIXTURES = report.REPO_ROOT / "harness_fixtures" / "coding_archetype"
ALTERNATIVES = (
    frozenset({"asyncio", "anyio", "trio"}),
    frozenset({"typing", "typing_extensions"}),
    frozenset({"Crypto", "Cryptodome"}),
)
NODE_ALTERNATIVES = (
    frozenset({"FunctionDef", "AsyncFunctionDef"}),
    frozenset({"For", "AsyncFor"}),
    frozenset({"With", "AsyncWith"}),
    frozenset({"Try", "TryStar"}),
    frozenset({"Import", "ImportFrom"}),
)
BANDIT_NODES = {
    "Call": ("Call",),
    "Import": ("Import",),
    "ImportFrom": ("ImportFrom",),
    "Str": ("Constant",),
    "Bytes": ("Constant",),
    "FunctionDef": ("FunctionDef",),
    "ExceptHandler": ("ExceptHandler",),
    "Assert": ("Assert",),
}
PROJECT_TOOLS = frozenset({"mypy", "pyright", "vulture"})
PROJECT_RULES = frozenset(
    {"pylint R0801", "pylint E0013", "pylint E0014", "pylint E0015"}
)
PROJECT_RULES |= frozenset(f"hallucination H00{n}" for n in range(1, 9))

SOURCES: dict[str, str] = {
    "ruff": "python -m ruff rule --all --output-format json: the blocks of each page's "
    "'## Example' section above its 'Use instead' line, the first one read",
    "bandit": "git clone --depth 1 --branch 1.9.4 --filter=blob:none --sparse "
    "https://github.com/PyCQA/bandit.git bandit; git -C bandit sparse-checkout set examples",
    "semgrep": "git clone --depth 1 --filter=blob:none --sparse "
    "https://github.com/semgrep/semgrep-rules.git; git -C semgrep-rules sparse-checkout "
    "set python generic; the rules saved from https://semgrep.dev/c/p/python and "
    "https://semgrep.dev/c/p/security-audit as p_python.yaml and p_security-audit.yaml",
    "mypy": "the python blocks under each '.. _code-<code>:' section of "
    "docs/source/error_code_list.rst and error_code_list2.rst at "
    "https://github.com/python/mypy/tree/v2.1.0, saved under mypy_docs/",
    "rule modules": "harness_fixtures/coding_archetype/known_bad*.py, read by each module's scan",
}

GROUNDS: dict[str, str] = {
    "example": "each finding of the rule on its own published faulty example: the deepest "
    "node holding the finding's span and the nodes holding it, up to the nearest statement",
    "unparse": "the rule fires on its example and is silent on ast.unparse of the same AST, "
    "so it reads text the AST does not hold and fits any input holding that line",
    "strip": "the example with each import statement replaced by pass: [] when the rule "
    "still fires, else the modules whose single removal lowers its findings, checked by "
    "removing only them",
    "example+docs": "example, widened by the Python documentation: ast 'AsyncFunctionDef ... Has "
    "the same fields as FunctionDef.'; 'AsyncFor ... AsyncWith ... They have the same fields as For "
    "and With, respectively.'; 'TryStar ... The attributes are the same as for Try'; and the "
    'language reference 7.11, import_stmt: "import" module ... | "from" relative_module "import"',
    "alternatives": "strip, widened by a family's own documentation: asyncio, anyio and trio "
    "(flake8-async); typing and typing_extensions (typing_extensions); Crypto and "
    "Cryptodome (pycryptodome)",
    "kinds": "the example written as <name>.py, test_<name>.py, <name>.pyi and a one-cell "
    "<name>.ipynb: the kinds where the rule fires",
    "declared": "bandit's own @checks declaration: the node types the test reads; "
    "FunctionDef sits on a scope, every other node inside a statement",
    "blacklist": "bandit's blacklist data: the top-level package of each qualname; [] for "
    "B4xx, which bandit also checks on Call, where __import__ needs no import",
    "scope": "the tool's own scope: it reads the project to give a finding",
    "paths": "the semgrep rule's own languages and paths.include",
    "docs": "the tool's own documentation, quoted in the key's note",
}

Position = tuple[int, int]
Hit = tuple[str, str, Position, Position]
Keys = dict[str, Any]


class MeasureFault(Exception):
    """A published source or a tool run this module needs could not be read."""


@dataclass
class Example:
    """One published faulty example: file `stem`, `suffix`, `text`, and the `rules` it shows, empty for any."""

    stem: str
    suffix: str
    text: str
    rules: frozenset[str] = frozenset()
    folder: str = ""


@dataclass
class Reading:
    """One rule's `hits` per example stem, and its own-hit counts on each variant of its examples."""

    hits: dict[str, list[tuple[Position, Position]]] = field(default_factory=dict)
    unparsed: int = 0
    stripped: int = 0
    dropped: set[str] = field(default_factory=set)
    kept: int = -1
    kinds: set[str] = field(default_factory=set)


class Engine(Protocol):
    """A `tool` read on published examples: `examples` to write, and `scan` of a folder to `Hit` rows."""

    tool: str

    def examples(self, sources: Path) -> list[Example]:
        """Return the published faulty examples under `sources`."""
        ...

    def scan(self, folder: Path) -> list[Hit]:
        """Return each `Hit` the tool reports in `folder`: rule, file stem, start and end."""
        ...


def _run(argv: list[str], folder: Path, exits: Iterable[int] = (0, 1)) -> str:
    """Return the stdout of `argv` run in `folder`, or raise `MeasureFault`."""
    try:
        proc = subprocess.run(
            argv, cwd=folder, capture_output=True, timeout=TOOL_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = f"{argv[:4]}: {exc}"
        raise MeasureFault(message) from exc
    if proc.returncode not in set(exits):
        message = f"{argv[:4]} exited {proc.returncode}: {tool_text(proc.stderr)[:400]}"
        raise MeasureFault(message)
    return tool_text(proc.stdout)


def _executable(name: str) -> str:
    """Return the absolute path of `name` on PATH, or raise `MeasureFault`."""
    found = shutil.which(name)
    if found is None:
        message = f"{name} is not on PATH"
        raise MeasureFault(message)
    return found


def top_modules(node: ast.Import | ast.ImportFrom) -> list[str]:
    """Return the top-level package of each absolute module `node` imports."""
    if isinstance(node, ast.ImportFrom):
        return [node.module.split(".")[0]] if node.module and not node.level else []
    return [alias.name.split(".")[0] for alias in node.names]


def parsed(text: str) -> ast.Module | None:
    """Return the AST of `text`, or None when it does not parse."""
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return None


def deepest(tree: ast.AST, start: Position, end: Position) -> ast.AST:
    """Return the deepest positioned node of `tree` whose span holds `start` to `end`."""
    best: ast.AST = tree
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        end_line = getattr(node, "end_lineno", None)
        if line is None or end_line is None:
            continue
        span_start = (line, getattr(node, "col_offset", 0))
        span_end = (end_line, getattr(node, "end_col_offset", 0))
        if span_start <= start and span_end >= end:
            best = node
    return best


def path_to_statement(tree: ast.AST, start: Position, end: Position) -> list[ast.AST]:
    """Return the `deepest` node and the nodes holding it, up to and including the nearest statement."""
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    node: ast.AST | None = deepest(tree, start, end)
    path: list[ast.AST] = []
    while node is not None:
        path.append(node)
        if isinstance(node, (ast.stmt, ast.Module)):
            break
        node = parents.get(node)
    return path


def size_of(path: list[ast.AST]) -> str:
    """Return `statement`, `scope` or `module` for the node `path` a finding sits on."""
    last = path[-1] if path else None
    if last is None or isinstance(last, ast.Module):
        return "module"
    return "scope" if isinstance(last, SCOPES) else "statement"


def stripped(text: str, drop: Callable[[int, list[str]], bool]) -> str:
    """Return `text` with each import statement `drop` accepts, by walk index and modules, made pass.

    Each statement's columns become `pass` and spaces, so every other token keeps its line and column.
    """
    tree = ast.parse(text)
    lines = text.splitlines()
    statements = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    for index, node in enumerate(statements):
        if drop(index, top_modules(node)):
            first, last = node.lineno - 1, (node.end_lineno or node.lineno) - 1
            end = node.end_col_offset or len(lines[last])
            if first == last:
                width = end - node.col_offset
                lines[first] = (
                    lines[first][: node.col_offset]
                    + "pass".ljust(width)
                    + lines[first][end:]
                )
                continue
            lines[first] = lines[first][: node.col_offset] + "pass"
            for number in range(first + 1, last):
                lines[number] = ""
            lines[last] = " " * end + lines[last][end:]
    return "\n".join(lines) + "\n"


def imported(text: str) -> list[list[str]]:
    """Return the top modules of each import statement in `text`, in walk order."""
    tree = parsed(text)
    if tree is None:
        return []
    return [
        top_modules(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]


def notebook(text: str) -> str:
    """Return `text` as a one-cell `.ipynb` document."""
    cell: dict[str, Any] = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }
    document: dict[str, Any] = {
        "cells": [cell],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(document)


Variant = Callable[[Example], dict[str, str]]


def scan_variant(
    engine: Engine, examples: list[Example], make: Variant
) -> dict[str, dict[str, int]]:
    """Write each example as `make` names it, scan the folder, and count each rule's own hits per base stem."""
    with tempfile.TemporaryDirectory() as folder:
        owners: dict[str, Example] = {}
        for example in examples:
            for name, text in make(example).items():
                stem, _, suffix = name.rpartition("|")
                target = Path(folder) / example.folder / f"{stem}{suffix}"
                target.parent.mkdir(parents=True, exist_ok=True)
                body = notebook(text) if suffix == ".ipynb" else text
                target.write_text(body, encoding="utf-8", newline="\n")
                owners[stem.removeprefix("test_")] = example
        hits = engine.scan(Path(folder))
    counts: dict[str, dict[str, int]] = {}
    for rule, stem, _start, _end in hits:
        example = owners.get(stem)
        if example is not None and (not example.rules or rule in example.rules):
            per = counts.setdefault(rule, {})
            per[example.stem] = per.get(example.stem, 0) + 1
    return counts


def read_examples(engine: Engine, examples: list[Example]) -> dict[str, Reading]:
    """Return each rule's `Reading` over `examples`: base, unparse, strip and kind variants."""
    by_stem = {example.stem: example for example in examples}
    with tempfile.TemporaryDirectory() as folder:
        for example in examples:
            target = Path(folder) / example.folder / f"{example.stem}{example.suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(example.text, encoding="utf-8", newline="\n")
        base_hits = engine.scan(Path(folder))
    readings: dict[str, Reading] = {}
    for rule, stem, start, end in base_hits:
        example = by_stem.get(stem)
        if example is not None and (not example.rules or rule in example.rules):
            readings.setdefault(rule, Reading()).hits.setdefault(stem, []).append(
                (start, end)
            )
    fired = [
        e
        for e in examples
        if parsed(e.text) and any(e.stem in r.hits for r in readings.values())
    ]
    own = {e.stem: f"{e.stem}|{e.suffix}" for e in fired}

    def unparse(example: Example) -> dict[str, str]:
        return {own[example.stem]: ast.unparse(ast.parse(example.text)) + "\n"}

    def strip_all(example: Example) -> dict[str, str]:
        return {own[example.stem]: stripped(example.text, lambda _i, _m: True)}

    for rule, per in scan_variant(engine, fired, unparse).items():
        if rule in readings:
            readings[rule].unparsed = sum(per.values())
    for rule, per in scan_variant(engine, fired, strip_all).items():
        if rule in readings:
            readings[rule].stripped = sum(per.values())
    _read_single_drops(engine, fired, readings)
    _read_kinds(engine, fired, readings)
    return readings


def _read_single_drops(
    engine: Engine, fired: list[Example], readings: dict[str, Reading]
) -> None:
    """Record per rule the modules whose single import removal lowers its hits, then remove only those."""
    singles: dict[str, tuple[Example, list[str]]] = {}
    for example in fired:
        for index, modules in enumerate(imported(example.text)):
            singles[f"{example.stem}__s{index}"] = (example, modules)

    def single(example: Example) -> dict[str, str]:
        return {
            f"{stem}|{example.suffix}": stripped(
                example.text, lambda i, _m, at=int(stem.rpartition("__s")[2]): i == at
            )
            for stem, (owner, _modules) in singles.items()
            if owner is example
        }

    with tempfile.TemporaryDirectory() as folder:
        for example in fired:
            for name, text in single(example).items():
                stem, _, suffix = name.rpartition("|")
                target = Path(folder) / example.folder / f"{stem}{suffix}"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8", newline="\n")
        hits = engine.scan(Path(folder))
    counts: dict[tuple[str, str], int] = {}
    for rule, stem, _start, _end in hits:
        counts[(rule, stem)] = counts.get((rule, stem), 0) + 1
    for stem, (example, modules) in singles.items():
        for rule, reading in readings.items():
            base = len(reading.hits.get(example.stem, []))
            if base and counts.get((rule, stem), 0) < base:
                reading.dropped.update(modules)

    def keep(example: Example) -> dict[str, str]:
        modules: set[str] = set()
        for reading in readings.values():
            if example.stem in reading.hits:
                modules |= reading.dropped
        if not modules:
            return {}
        return {
            f"{example.stem}|{example.suffix}": stripped(
                example.text, lambda _i, found: bool(modules.intersection(found))
            )
        }

    kept = scan_variant(engine, fired, keep)
    for rule, reading in readings.items():
        if reading.dropped:
            reading.kept = sum(kept.get(rule, {}).values())


def _read_kinds(
    engine: Engine, fired: list[Example], readings: dict[str, Reading]
) -> None:
    """Record per rule each of `KINDS` whose variant of its examples it fires on."""
    variants: dict[str, Variant] = {
        "source": lambda e: {f"{e.stem}|.py": e.text},
        "test": lambda e: {f"test_{e.stem}|.py": e.text},
        "stub": lambda e: {f"{e.stem}|.pyi": e.text},
        "notebook": lambda e: {f"{e.stem}|.ipynb": e.text},
    }
    for kind, make in variants.items():
        for rule, per in scan_variant(engine, fired, make).items():
            if rule in readings and sum(per.values()):
                readings[rule].kinds.add(kind)


def _stem(path: Path) -> str:
    """Return the stem a scanned file reports, with the test kind's `test_` prefix removed."""
    return path.stem.removeprefix("test_")


class Ruff:
    """ruff's own rule pages, read with every stable rule and with the sigils' preview rules."""

    tool = "ruff"

    def __init__(self, preview: frozenset[str]) -> None:
        """Hold the `preview` rule codes, read with --preview as the sigils read them."""
        self.preview = preview

    def examples(self, sources: Path) -> list[Example]:
        """Return the faulty block of each rule page that publishes one."""
        printed = _run(
            [sys.executable, "-m", "ruff", "rule", "--all", "--output-format", "json"],
            sources,
            exits=(0,),
        )
        found: list[Example] = []
        for page in json.loads(printed):
            section = _example_section(page.get("explanation") or "")
            heading = _HEADING_RE.search(section)
            blocks = _BLOCK_RE.findall(
                section[: heading.start()] if heading else section
            )
            if blocks:
                suffix = ".pyi" if page.get("linter") == "flake8-pyi" else ".py"
                found.append(
                    Example(page["code"], suffix, blocks[0], frozenset({page["code"]}))
                )
        return found

    def scan(self, folder: Path) -> list[Hit]:
        """Return ruff's hits in `folder`."""
        base = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--no-cache",
            "--no-fix",
        ]
        base += ["--target-version", RUFF_TARGET, "--output-format", "json"]
        rows = json.loads(_run([*base, "--select", "ALL", "."], folder) or "[]")
        rows = [row for row in rows if row.get("code") not in self.preview]
        if self.preview:
            selected = ",".join(sorted(self.preview))
            rows += json.loads(
                _run([*base, "--preview", "--select", selected, "."], folder) or "[]"
            )
        return [
            (
                row["code"],
                _stem(Path(row["filename"])),
                (row["location"]["row"], row["location"]["column"] - 1),
                (row["end_location"]["row"], row["end_location"]["column"] - 1),
            )
            for row in rows
            if row.get("code") and row.get("location")
        ]


class Bandit:
    """bandit's own examples folder at the installed version, read with `bandit -r`."""

    tool = "bandit"

    def examples(self, sources: Path) -> list[Example]:
        """Return each `.py` file of bandit's examples folder."""
        folder = sources / BANDIT_EXAMPLES
        if not folder.is_dir():
            message = f"no {BANDIT_EXAMPLES} under {sources}"
            raise MeasureFault(message)
        return [
            Example(
                path.stem.replace("-", "_"),
                ".py",
                path.read_text(encoding="utf-8", errors="replace"),
            )
            for path in sorted(folder.glob("*.py"))
        ]

    def scan(self, folder: Path) -> list[Hit]:
        """Return bandit's hits in `folder`, each spanning its reported columns."""
        printed = _run(
            [sys.executable, "-m", "bandit", "-f", "json", "-q", "-r", "."], folder
        )
        hits: list[Hit] = []
        for row in json.loads(printed or "{}").get("results", []):
            lines = row.get("line_range") or [row["line_number"]]
            start = (row["line_number"], row.get("col_offset", 0))
            end = (lines[-1], row.get("end_col_offset", row.get("col_offset", 0)))
            hits.append((row["test_id"], _stem(Path(row["filename"])), start, end))
        return hits


class Semgrep:
    """semgrep-rules' test file beside each python rule, read with the two saved registry configs."""

    tool = "semgrep"

    def __init__(self, sources: Path, rules: Iterable[str]) -> None:
        """Hold the saved config paths under `sources` and the archetype's semgrep `rules`."""
        self.configs = [sources / name for name in SEMGREP_CONFIGS]
        self.rules = set(rules)

    def examples(self, sources: Path) -> list[Example]:
        """Return the python test file of each rule, kept under its own relative folder."""
        found: dict[str, Example] = {}
        for rule in sorted(self.rules):
            parts = rule.split(".")
            path = (sources / SEMGREP_TESTS).joinpath(*parts[:-1]).with_suffix(".py")
            if parts[0] != "python" or not path.is_file():
                continue
            stem = "__".join(parts[:-1]).replace("-", "_").replace(".", "_")
            if stem in found:
                found[stem].rules = found[stem].rules | {rule}
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            found[stem] = Example(
                stem, ".py", text, frozenset({rule}), "/".join(parts[:-2])
            )
        return list(found.values())

    def scan(self, folder: Path) -> list[Hit]:
        """Return semgrep's hits in `folder` under the saved configs."""
        argv = [_executable("semgrep"), "scan", "--json", "--quiet", "--metrics=off"]
        argv += ["--no-git-ignore", "--disable-version-check"]
        argv += [f"--config={config}" for config in self.configs]
        printed = _run([*argv, "."], folder)
        hits: list[Hit] = []
        for row in json.loads(printed or "{}").get("results", []):
            rule = self.registry_id(row["check_id"])
            if rule:
                start = (row["start"]["line"], row["start"]["col"] - 1)
                end = (row["end"]["line"], row["end"]["col"] - 1)
                hits.append((rule, _stem(Path(row["path"])), start, end))
        return hits

    def registry_id(self, check_id: str) -> str:
        """Return the rule in `rules` that `check_id` ends with, after the config path semgrep prefixes."""
        return next(
            (
                rule
                for rule in self.rules
                if check_id == rule or check_id.endswith(f".{rule}")
            ),
            "",
        )


_MYPY_ROW = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):(?P<end_line>\d+):(?P<end_col>\d+):"
    r"\s*error:.*\[(?P<code>[a-z-]+)\]\s*$"
)
_MYPY_SECTION = re.compile(r"^\.\. _code-(?P<code>[a-z-]+):\s*$", re.MULTILINE)
_RST_BLOCK = re.compile(
    r"^\.\. code-block:: python[ \t]*\n[ \t]*\n((?:(?:[ \t]+.*)?\n)+)", re.MULTILINE
)


class Mypy:
    """mypy's error code pages at the installed version, read with the archetype's mypy flags."""

    tool = "mypy"

    def examples(self, sources: Path) -> list[Example]:
        """Return each python block under each code's section of the two error code pages."""
        found: list[Example] = []
        for name in MYPY_DOCS:
            page = (sources / name).read_text(encoding="utf-8")
            sections = list(_MYPY_SECTION.finditer(page))
            for index, section in enumerate(sections):
                end = (
                    sections[index + 1].start()
                    if index + 1 < len(sections)
                    else len(page)
                )
                code = section.group("code")
                for number, block in enumerate(
                    _RST_BLOCK.findall(page[section.end() : end])
                ):
                    lines = [line for line in block.splitlines() if line.strip()]
                    indent = min(len(line) - len(line.lstrip()) for line in lines)
                    text = (
                        "\n".join(line[indent:] for line in block.splitlines()) + "\n"
                    )
                    stem = f"{code.replace('-', '_')}__b{number}"
                    if parsed(text) is not None:
                        found.append(Example(stem, ".py", text, frozenset({code})))
        return found

    def scan(self, folder: Path) -> list[Hit]:
        """Return mypy's error hits in `folder`, one module per file."""
        files = sorted(
            str(p.relative_to(folder))
            for p in folder.rglob("*")
            if p.suffix in {".py", ".pyi"}
        )
        if not files:
            return []
        with tempfile.TemporaryDirectory() as cache:
            argv = [
                sys.executable,
                "-m",
                "mypy",
                *MYPY_FLAGS,
                "--cache-dir",
                cache,
                *files,
            ]
            printed = _run(argv, folder, exits=(0, 1, 2))
        hits: list[Hit] = []
        for line in printed.splitlines():
            row = _MYPY_ROW.match(line)
            if row is not None:
                start = (int(row["line"]), int(row["col"]) - 1)
                end = (int(row["end_line"]), int(row["end_col"]))
                hits.append((row["code"], _stem(Path(row["file"])), start, end))
        return hits


class RuleModules:
    """The archetype's own rule modules, read on its known-bad calibration bodies."""

    tool = "rule modules"

    def examples(self, _sources: Path) -> list[Example]:
        """Return each `known_bad*.py` under `FIXTURES`."""
        return [
            Example(path.stem, ".py", path.read_text(encoding="utf-8"))
            for path in sorted(FIXTURES.glob("known_bad*.py"))
        ]

    def scan(self, folder: Path) -> list[Hit]:
        """Return each rule module's hits on the files the archetype enumerates in `folder`."""
        hits: list[Hit] = []
        paths = report.rule_source_files(folder, (".py",))
        sources, _failures = report.read_rule_sources(paths)
        for _name, module_path in coding_archetype._PY_RULE_MODULES:
            module = importlib.import_module(module_path)
            for path, source in sources:
                lines = source.splitlines()
                for row in module.scan(path, source):
                    text = lines[row.line - 1] if 0 < row.line <= len(lines) else ""
                    start = (row.line, len(text) - len(text.lstrip()))
                    hits.append(
                        (
                            row.rule_id,
                            _stem(Path(row.file)),
                            start,
                            (row.line, len(text)),
                        )
                    )
        return hits


def _widen(modules: set[str]) -> tuple[list[str], str]:
    """Return `modules` with every `ALTERNATIVES` group they touch, and the ground naming it."""
    grown = set(modules)
    for group in ALTERNATIVES:
        if grown & group:
            grown |= group
    return sorted(grown), "alternatives" if grown != modules else "strip"


def touches_import(tree: ast.AST, start: Position, end: Position) -> bool:
    """Report whether an import statement of `tree` overlaps the span `start` to `end`."""
    return any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and (node.lineno, node.col_offset) <= end
        and (node.end_lineno or node.lineno, node.end_col_offset or 0) >= start
        for node in ast.walk(tree)
    )


def _imports_key(reading: Reading, paths: list[list[ast.AST]], on_import: bool) -> Keys:
    """Return the imports key: [] when the stripped example still fires, else the modules it needs."""
    if on_import or any(isinstance(node, IMPORTS) for path in paths for node in path):
        return {
            "open": "the finding sits on an import statement, so removing imports removes the subject"
        }
    if reading.stripped > 0:
        return {"value": [], "ground": "strip"}
    if reading.dropped and reading.kept == 0:
        value, ground = _widen(reading.dropped)
        return {"value": value, "ground": ground}
    return {
        "open": "removing every import stopped the finding, and removing the modules each single "
        "removal named did not"
    }


def keys_from(reading: Reading, examples: dict[str, Example], tool: str) -> Keys:
    """Return the four keys one rule's `reading` grounds, with `open` naming each key it cannot."""
    keys: Keys = {}
    paths: list[list[ast.AST]] = []
    on_import = False
    for stem, spans in reading.hits.items():
        tree = parsed(examples[stem].text)
        if tree is not None:
            paths += [path_to_statement(tree, start, end) for start, end in spans]
            on_import = on_import or any(
                touches_import(tree, start, end) for start, end in spans
            )
    count = sum(len(spans) for spans in reading.hits.values())
    stem, spans = next(iter(reading.hits.items()))
    keys["example"] = (
        f"{tool} {stem}: {count} finding(s), first at {spans[0][0][0]}:{spans[0][0][1] + 1}"
    )
    if not paths:
        reason = "its published example does not parse as Python"
        keys.update(
            reach={"open": reason}, nodes={"open": reason}, imports={"open": reason}
        )
    elif reading.unparsed == 0:
        keys["reach"] = {"value": "statement", "ground": "unparse"}
        keys["nodes"] = {
            "open": "the rule reads text the AST does not hold (ground: unparse)"
        }
    else:
        sizes = {size_of(path) for path in paths}
        keys["reach"] = {"value": max(sizes, key=SIZES.index), "ground": "example"}
        names = {type(node).__name__ for path in paths for node in path}
        widened = set(names)
        for group in NODE_ALTERNATIVES:
            if widened & group:
                widened |= group
        ground = "example+docs" if widened != names else "example"
        keys["nodes"] = {"value": sorted(widened), "ground": ground}
    if "imports" not in keys:
        keys["imports"] = _imports_key(reading, paths, on_import)
    keys["file"] = {"value": sorted(reading.kinds, key=KINDS.index), "ground": "kinds"}
    return keys


def unfired(tool: str) -> Keys:
    """Return the keys of a rule whose published example draws no finding of its own."""
    reason = f"no published {tool} example of this rule draws a finding of its own"
    return {key: {"open": reason} for key in ("reach", "nodes", "imports", "file")}


def measured(engine: Engine, sources: Path, rules: Iterable[str]) -> dict[str, Keys]:
    """Return the keys `engine` grounds for each of `rules` from its published examples."""
    examples = engine.examples(sources)
    by_stem = {example.stem: example for example in examples}
    readings = read_examples(engine, examples)
    return {
        rule: (
            keys_from(readings[rule], by_stem, engine.tool)
            if rule in readings and readings[rule].hits
            else unfired(engine.tool)
        )
        for rule in rules
    }


def bandit_declared(keys: dict[str, Keys]) -> None:
    """Set each bandit test's nodes and reach from its @checks declaration, and blacklist imports."""
    manager = importlib.import_module("bandit.core.extension_loader").MANAGER
    for plugin in manager.plugins:
        test = getattr(plugin.plugin, "_test_id", "")
        checks = list(getattr(plugin.plugin, "_checks", []))
        if test in keys:
            _declare(keys[test], checks)
    listed: dict[str, tuple[set[str], set[str]]] = {}
    for node_name, entries in manager.blacklist.items():
        for entry in entries:
            nodes, qualnames = listed.setdefault(entry["id"], (set(), set()))
            nodes.add(node_name)
            qualnames.update(entry.get("qualnames", []))
    for test, (nodes, qualnames) in listed.items():
        if test not in keys:
            continue
        _declare(keys[test], sorted(nodes))
        if test.startswith("B4") or any("." not in name for name in qualnames):
            keys[test]["imports"] = {"value": [], "ground": "blacklist"}
        else:
            packages = sorted({name.split(".")[0] for name in qualnames})
            keys[test]["imports"] = {"value": packages, "ground": "blacklist"}


def _declare(keys: Keys, checks: list[str]) -> None:
    """Set `keys` nodes and reach from bandit node names `checks`; `File` reads text."""
    if "File" in checks:
        keys["reach"] = {"value": "statement", "ground": "declared"}
        keys["nodes"] = {
            "open": "bandit declares it checks File: it reads the file's text"
        }
        return
    names = sorted(
        {name for check in checks for name in BANDIT_NODES.get(check, (check,))}
    )
    size = "scope" if "FunctionDef" in checks else "statement"
    keys["reach"] = {"value": size, "ground": "declared"}
    keys["nodes"] = {"value": names, "ground": "declared"}


def semgrep_generic(sources: Path, rules: Iterable[str]) -> dict[str, Keys]:
    """Return the keys of each generic-language semgrep rule from its own languages and paths."""
    yaml = importlib.import_module("yaml")
    declared: dict[str, dict[str, Any]] = {}
    for name in SEMGREP_CONFIGS:
        document = yaml.safe_load((sources / name).read_text(encoding="utf-8"))
        declared.update({rule["id"]: rule for rule in document["rules"]})
    keys: dict[str, Keys] = {}
    for rule in rules:
        entry = declared.get(rule, {})
        if "generic" not in entry.get("languages", []):
            continue
        include = entry.get("paths", {}).get("include", [])
        text = "generic language: it reads text, not a Python AST"
        keys[rule] = {
            "reach": {"value": "statement", "ground": "paths"},
            "nodes": {"open": text},
            "imports": {"value": [], "ground": "paths"},
            "example": f"semgrep paths.include {include}",
        }
        if all(
            pattern.startswith("*.") and not pattern.endswith((".py", ".pyi"))
            for pattern in include
        ):
            keys[rule]["file"] = {"value": [], "ground": "paths"}
        else:
            keys[rule]["file"] = {
                "open": f"paths.include {include} names folders whose files of any kind it reads"
            }
    return keys


PYRIGHT_KEYS: Keys = {
    "reach": {"value": "project", "ground": "scope"},
    "nodes": {"open": "pyright publishes no faulty example per rule"},
    "imports": {"open": "pyright publishes no faulty example per rule"},
    "file": {
        "value": ["source", "test", "stub"],
        "ground": "docs",
        "note": "pyright docs/configuration.md, include: 'Paths of directories or files that "
        "should be considered part of the project'; the command line reads .py and .pyi",
    },
}

VULTURE_KEYS: Keys = {
    "reach": {"value": "project", "ground": "scope"},
    "nodes": {"open": "one rule id, dead-code, covers every kind vulture reports"},
    "imports": {
        "value": [],
        "ground": "docs",
        "note": "vulture README: 'Vulture finds unused code in Python programs'; no library",
    },
    "file": {
        "value": ["source", "test"],
        "ground": "docs",
        "note": "vulture README: 'vulture myscript.py' or 'vulture mypackage/' reads .py files",
    },
}


def pylint_keys(rule: str) -> Keys:
    """Return the keys of one pylint message the archetype's call enables, from pylint --list-msgs."""
    texts = {
        "R0801": "Indicates that a set of similar lines has been detected among multiple file.",
        "E0001": "Used when a syntax error is raised for a module.",
        "F0001": "Used when an error occurred preventing the analysis of a module",
        "F0002": "Used when an unexpected error occurred while building the Astroid representation.",
        "F0010": "Used when an exception occurred while building the Astroid representation",
        "F0011": "Used when an exception occurred while parsing a pylint configuration file.",
        "E0011": "Used when an unknown inline option is encountered.",
        "W0012": "Used when an unknown value is encountered for an option.",
        "R0022": "Used when a value for an option that is now deleted from pylint is encountered.",
        "E0013": "Used when a bad value is used in 'load-plugins'.",
        "E0014": "Used when we detect a setting in the top level of a toml configuration",
        "E0015": "Used when we detect an option that we do not recognize.",
    }
    note = f"pylint --list-msgs: '{texts[rule]}'"
    size = {
        "R0801": "project",
        "E0013": "project",
        "E0014": "project",
        "E0015": "project",
        "F0011": "project",
        "E0011": "statement",
        "W0012": "statement",
        "R0022": "statement",
    }
    reach = size.get(rule, "module")
    return {
        "reach": {"value": reach, "ground": "docs", "note": note},
        "nodes": {
            "open": "pylint reads lines, options or a failed parse, not one AST node"
        },
        "imports": {"value": [], "ground": "docs", "note": note},
        "file": {
            "value": ["source", "test"],
            "ground": "scope",
            "note": "the archetype's pylint call passes the *.py files of the target's folder",
        },
    }


TEXT_READ = "it reads comment, docstring or line text, which the AST does not hold"
PY_KINDS = ["source", "test"]
RULE_MODULE_DOCS: dict[str, tuple[str, list[str] | str, list[str], list[str], str]] = {
    "S001": (
        "statement",
        ["Call"],
        [],
        PY_KINDS,
        "FALLBACK-STRING-BEFORE-VERIFICATION: "
        "String literals inside setText/print/log calls",
    ),
    "S002": (
        "scope",
        ["AsyncFunctionDef", "FunctionDef"],
        ["asyncio"],
        PY_KINDS,
        "WALL-CLOCK COMPLETION TIMER: A function that calls run_coroutine_threadsafe",
    ),
    "S003": (
        "scope",
        ["ClassDef"],
        [],
        PY_KINDS,
        "REFERENCED-BUT-NOT-INITIALIZED: A class method "
        "references self._foo where _foo is not assigned in __init__.",
    ),
    "S004": (
        "statement",
        TEXT_READ,
        [],
        PY_KINDS,
        "PLACEHOLDER TEXT: Comments / docstrings / markdown text",
    ),
    "H001": (
        "statement",
        TEXT_READ,
        [],
        PY_KINDS,
        "DEAD PATH REFERENCE: Comments, docstrings, or markdown text",
    ),
    "H002": (
        "statement",
        TEXT_READ,
        [],
        PY_KINDS,
        "DEAD ARCHITECTURE REFERENCE: Mentions of retired subsystems",
    ),
    "H003": (
        "statement",
        ["Import", "ImportFrom"],
        [],
        PY_KINDS,
        "IMPORT OF LOCAL MODULE THAT DOESN'T EXIST",
    ),
    "H004": (
        "statement",
        TEXT_READ,
        [],
        PY_KINDS,
        "CITATION PAST THE END OF THE FILE IT NAMES: Prose citing",
    ),
    "H005": (
        "statement",
        "Python joins the split string literals into one AST constant",
        [],
        PY_KINDS,
        "A DOTTED NAME SPLIT ACROSS STRING LITERALS: Python joins the pieces",
    ),
    "H006": (
        "statement",
        TEXT_READ,
        [],
        [],
        "CITATION ANCHORED TO A LINE NUMBER: Markdown citing",
    ),
    "H007": (
        "statement",
        TEXT_READ,
        [],
        [],
        "CITED MODULE NAME THAT RESOLVES TO NO FILE: "
        "a bare module name a markdown page cites",
    ),
    "H008": (
        "statement",
        TEXT_READ,
        [],
        PY_KINDS,
        "A DECLARED-ABSENT PATH THAT IS PRESENT ON DISK",
    ),
    "SL001": (
        "module",
        ["Try", "TryStar"],
        [],
        PY_KINDS,
        "DUPLICATE TRY/EXCEPT/PASS BLOCKS: " "appearing 3+ times in the file.",
    ),
    "SL002": (
        "scope",
        ["AsyncFunctionDef", "FunctionDef"],
        [],
        PY_KINDS,
        "OVER-LONG FUNCTION: A function definition spanning >200 lines.",
    ),
    "SL003": (
        "module",
        "it reads the module's line count",
        [],
        PY_KINDS,
        "FILE TOO BIG: Module spanning >3000 lines.",
    ),
    "NG001": (
        "scope",
        ["Call"],
        [],
        PY_KINDS,
        "OPEN NUMERIC TYPE GUARD ON A COERCED VALUE: An "
        "`isinstance` test ... on a value that the same function also passes to `float()`",
    ),
}


def rule_module_docs(rule: str, tool: str) -> Keys:
    """Return the keys `RULE_MODULE_DOCS` grounds for one rule module rule, quoting its module docstring."""
    reach, nodes, imports, kinds, quote = RULE_MODULE_DOCS[rule]
    note = f"{tool}.py docstring, {rule}: '{quote}'"
    scope_note = "report.rule_source_files expands a folder to its .py files"
    if not kinds:
        scope_note = "hallucination.py, in scan: this check runs on .md and .markdown files alone"
    return {
        "reach": {"value": reach, "ground": "docs", "note": note},
        "nodes": (
            {"open": nodes}
            if isinstance(nodes, str)
            else {"value": nodes, "ground": "docs", "note": note}
        ),
        "imports": {"value": imports, "ground": "docs", "note": note},
        "file": {"value": kinds, "ground": "scope", "note": scope_note},
        "example": f"no finding on {FIXTURES.name}/known_bad*.py; keys from its module docstring",
    }


def all_rules(root: Path) -> tuple[dict[str, set[str]], frozenset[str]]:
    """Return the rules each tool runs under `root`, per `coding_house`, and the sigils' preview rules."""
    run, unread = coding_house.rules_run(root)
    sigils, sigil_unread = coding_house.sigil_rules(root, run)
    if unread or sigil_unread:
        message = f"coding_house could not read {sorted({**unread, **sigil_unread})}"
        raise MeasureFault(message)
    preview = frozenset(
        rule for _tools, only in sigils.values() for _tool, rule in only
    )
    return run, preview


def measure(root: Path, sources: Path) -> dict[str, Keys]:
    """Return the four keys of every rule `all_rules` names, each with its ground or its open reason."""
    run, preview = all_rules(root)
    keys: dict[str, Keys] = {}
    ruff = measured(Ruff(preview), sources, run["ruff"] | preview)
    keys.update({f"ruff {rule}": value for rule, value in ruff.items()})
    for rule in preview:
        keys[f"ruff {rule}"]["preview"] = True
    bandit = measured(Bandit(), sources, run["bandit"])
    bandit_declared(bandit)
    keys.update({f"bandit {rule}": value for rule, value in bandit.items()})
    generic = semgrep_generic(sources, run["semgrep"])
    python = measured(
        Semgrep(sources, run["semgrep"] - set(generic)),
        sources,
        run["semgrep"] - set(generic),
    )
    keys.update(
        {f"semgrep {rule}": value for rule, value in {**python, **generic}.items()}
    )
    keys.update(
        {
            f"mypy {rule}": value
            for rule, value in measured(Mypy(), sources, run["mypy"]).items()
        }
    )
    keys.update({f"pyright {rule}": dict(PYRIGHT_KEYS) for rule in run["pyright"]})
    keys.update({f"vulture {rule}": dict(VULTURE_KEYS) for rule in run["vulture"]})
    keys.update({f"pylint {rule}": pylint_keys(rule) for rule in run["pylint"]})
    modules = {tool for tool, _path in coding_archetype._PY_RULE_MODULES}
    module_rules = {rule: tool for tool in modules for rule in run[tool]}
    for rule, value in measured(RuleModules(), sources, module_rules).items():
        tool = module_rules[rule]
        fired = "value" in value["file"]
        keys[f"{tool} {rule}"] = (
            value
            if fired or rule not in RULE_MODULE_DOCS
            else rule_module_docs(rule, tool)
        )
    for name, value in keys.items():
        if name.split(" ")[0] in PROJECT_TOOLS or name in PROJECT_RULES:
            value["reach"] = {"value": "project", "ground": "scope"}
    return keys


def open_lost(keys: dict[str, Keys], proof: Path) -> int:
    """Open each key a proof's lost finding names, citing the input that held it; return the keys opened."""
    lost = json.loads(proof.read_text(encoding="utf-8")).get("lost", [])
    held: dict[tuple[str, str], str] = {}
    for row in sorted(lost, key=lambda row: ", in " not in row["input"]):
        for key in row["left out by"]:
            held.setdefault((row["rule"], key), row["input"])
    for (rule, key), where in held.items():
        keys[rule][key] = {
            "open": f"{where} holds a finding of this rule that the measured value left out"
        }
    return len(held)


CARD: dict[str, object] = {
    "house": "coding",
    "edition": 1,
    "owner": "coding",
    "keys": {
        "reach": "the smallest input a finding of the rule fits inside, of "
        + ", ".join(SIZES),
        "nodes": "the AST node types an input must hold one of for the rule to have a subject",
        "imports": "the top-level modules an input's file must import one of; [] for none",
        "file": "the file kinds the rule reads, of " + ", ".join(KINDS),
    },
    "open": "a key the measurement cannot ground carries open and its reason, and binds nothing; "
    "--proof opens each key that a proof on src/ shows leaving out a real finding, naming the input",
    "grounds": GROUNDS,
    "sources": SOURCES,
    "output": str(KEYS_FILE.relative_to(report.REPO_ROOT)).replace("\\", "/"),
}


def write(keys: dict[str, Keys], target: Path = KEYS_FILE) -> None:
    """Write `CARD` and `keys` to `target`, one rule per line, sorted by tool and rule."""
    rows = [
        f"  {json.dumps(name)}: {json.dumps(keys[name], sort_keys=True)}"
        for name in sorted(keys)
    ]
    body = '{\n "card": ' + json.dumps(CARD, sort_keys=True) + ',\n "rules": {\n'
    target.write_text(
        body + ",\n".join(rows) + "\n }\n}\n", encoding="utf-8", newline="\n"
    )


def main(argv: list[str] | None = None) -> int:
    """Print `CARD` with --card, else measure the keys from --sources and write `KEYS_FILE`."""
    parser = argparse.ArgumentParser(
        description="Measure the Coding Archetype's partition keys."
    )
    parser.add_argument("--card", action="store_true", help="print the card as JSON")
    parser.add_argument(
        "--sources", type=Path, help="the folder holding the published sources"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=report.REPO_ROOT,
        help="the tree the archetype reads",
    )
    parser.add_argument(
        "--proof",
        type=Path,
        help="a coding_partition --prove output whose lost findings open keys",
    )
    args = parser.parse_args(argv)
    if args.card or args.sources is None:
        print(json.dumps(CARD, indent=2))
        return 0
    try:
        keys = measure(args.root.resolve(), args.sources.resolve())
    except MeasureFault as exc:
        print(f"not measured: {exc}", file=sys.stderr)
        return 1
    opened = open_lost(keys, args.proof) if args.proof else 0
    write(keys)
    print(
        json.dumps(
            {"rules": len(keys), "opened by the proof": opened, "file": CARD["output"]}
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
