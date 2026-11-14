"""`count` checks each tool's rule listing against the `HOUSE` folders; `main` prints it or `CARD`."""

import argparse
import ast
import configparser
import importlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable
from importlib import metadata
from pathlib import Path
from typing import Any
from unittest import mock

from dev_harness.harness import coding_archetype
from dev_harness.harness.report import REPO_ROOT

from .core import repository_root, tool_text

HOUSE = Path(__file__).resolve().parents[1] / "disciplines"
DISCIPLINES = (
    "security",
    "reliability",
    "performance-efficiency",
    "maintainability",
    "conventions",
    "typing",
)
RULES_FILE = "rules.json"
UNPLACED_FILE = "unplaced.json"

TOOL_TIMEOUT_S = 300
MYPY_BUILT = "2.1.0"
PYRIGHT_BUILT = "1.1.411"
VULTURE_RULE = "dead-code"
SEMGREP_PROBE = "probe.py"
RULE_ID_SHAPE = re.compile(r"[A-Z]{1,3}[0-9]{3}")
BANDIT_SELECTORS = frozenset(
    {"-t", "--tests", "-s", "--skip", "-p", "--profile", "-c", "--configfile"}
)
PYRIGHT_FLAGS = frozenset({"--outputjson"})

MYPY_OPTIONAL: dict[str, tuple[str, ...]] = {
    "type-arg": ("--disallow-any-generics",),
    "no-untyped-def": ("--disallow-untyped-defs", "--disallow-incomplete-defs"),
    "redundant-cast": ("--warn-redundant-casts",),
    "redundant-self": (),
    "comparison-overlap": ("--strict-equality",),
    "no-untyped-call": ("--disallow-untyped-calls",),
    "no-any-return": ("--warn-return-any",),
    "no-any-unimported": ("--disallow-any-unimported",),
    "unreachable": ("--warn-unreachable",),
    "deprecated": (),
    "redundant-expr": (),
    "possibly-undefined": (),
    "truthy-bool": (),
    "truthy-iterable": (),
    "ignore-without-code": (),
    "unused-awaitable": (),
    "unused-ignore": ("--warn-unused-ignores",),
    "explicit-override": (),
    "mutable-override": (),
    "unimported-reveal": (),
    "explicit-any": ("--disallow-any-explicit",),
    "exhaustive-match": (),
    "untyped-decorator": ("--disallow-untyped-decorators",),
}

PYRIGHT_STANDARD = frozenset(
    {
        "reportAbstractUsage",
        "reportArgumentType",
        "reportAssertAlwaysTrue",
        "reportAssertTypeFailure",
        "reportAssignmentType",
        "reportAttributeAccessIssue",
        "reportCallIssue",
        "reportFunctionMemberAccess",
        "reportGeneralTypeIssues",
        "reportIncompatibleMethodOverride",
        "reportIncompatibleVariableOverride",
        "reportInconsistentOverload",
        "reportIndexIssue",
        "reportInvalidStringEscapeSequence",
        "reportInvalidTypeArguments",
        "reportInvalidTypeForm",
        "reportInvalidTypeVarUse",
        "reportMissingImports",
        "reportMissingModuleSource",
        "reportNoOverloadImplementation",
        "reportOperatorIssue",
        "reportOptionalCall",
        "reportOptionalContextManager",
        "reportOptionalIterable",
        "reportOptionalMemberAccess",
        "reportOptionalOperand",
        "reportOptionalSubscript",
        "reportOverlappingOverload",
        "reportPossiblyUnboundVariable",
        "reportPrivateImportUsage",
        "reportRedeclaration",
        "reportReturnType",
        "reportSelfClsParameterName",
        "reportTypedDictNotRequiredAccess",
        "reportUnboundVariable",
        "reportUndefinedVariable",
        "reportUnhashable",
        "reportUnsupportedDunderAll",
        "reportUnusedCoroutine",
        "reportUnusedExcept",
        "reportUnusedExpression",
        "reportWildcardImportFromLibrary",
    }
)

LISTINGS: dict[str, str] = {
    "ruff": "the archetype's ruff command with --show-settings on --root: linter.rules.enabled",
    "mypy": "mypy.errorcodes.error_codes, less each optional check the archetype's "
    "flags leave off, by the flag "
    f"https://github.com/python/mypy/blob/v{MYPY_BUILT}/docs/source/error_code_list2.rst "
    "names for it",
    "pyright": "the standard column of the Diagnostic Settings Defaults table at "
    f"https://github.com/microsoft/pyright/blob/{PYRIGHT_BUILT}/docs/configuration.md, "
    "with no pyright configuration where the archetype runs",
    "bandit": "the tests python -m bandit --help lists, with no test selection in the archetype's command",
    "vulture": f"{VULTURE_RULE}, the one rule id the archetype gives every vulture row",
    "semgrep": "the rule ids semgrep --time reports for the archetype's configs on a one-line .py file",
    "pylint": "the messages pylint --list-msgs-enabled prints under the archetype's flags",
    "rule modules": "each rule id string in the modules coding_archetype._PY_RULE_MODULES names",
}

CARD: dict[str, object] = {
    "house": "coding",
    "edition": 1,
    "owner": "coding",
    "input": "--root: the tree whose ruff configuration the archetype reads; "
    "default: the repository holding the working folder",
    "disciplines": {name: f"dev_harness/disciplines/{name}" for name in DISCIPLINES},
    "files": {"placed": f"<discipline>/{RULES_FILE}", "unplaced": UNPLACED_FILE},
    "standard": "ISO/IEC 5055:2021, CWE lists from https://www.omg.org/spec/ASCQM/1.0/PDF; "
    "PEP 8, PEP 257, PEP 484 and https://typing.python.org/en/latest/spec/; "
    "PEP 20, https://docs.python.org/3.14/ and each framework's own documentation",
    "grounds": [
        "cwe: a CWE id the discipline's rules.json lists, or one the tool attaches to the rule",
        "term: a quote of the tool's own text naming an ISO/IEC 25010 characteristic",
        "pep: a quoted section of PEP 8, PEP 257 or PEP 484 that states the rule's check, "
        "or a PEP 20 line whose concern the rule's quoted text names",
        "spec: a quoted section of the typing specification that states the rule's check",
        "docs: a quoted section of the Python 3.14 documentation that states the failure, "
        "cost, idiom or type of the construct the rule detects",
        "framework: a quoted section of a framework's own documentation that states the same",
    ],
    "listings": LISTINGS,
    "outputs": ["per tool: run, placed, unplaced", "per discipline: placements"],
    "faults": {
        "missing": "a rule a tool runs that no rules.json and not unplaced.json holds",
        "stale": "a rule the files hold that no tool runs",
        "both": "a rule placed and also unplaced",
        "ungrounded": "a CWE ground its discipline does not list and the tool did not attach",
        "unread": "a tool whose listing could not be read",
    },
}

Reader = Callable[[list[str], Path], set[str]]


class ToolFault(Exception):
    """A listing in `LISTINGS` could not be read, and `count` reports the tool as unread."""


class _Recorded(Exception):
    """`_invocations` raises it once the patched `subprocess.run` has the archetype's argv."""


def _run(argv: list[str], folder: Path) -> str:
    """Return the stdout of `argv` run in `folder`, or raise `ToolFault`."""
    try:
        proc = subprocess.run(
            argv, cwd=folder, capture_output=True, timeout=TOOL_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        message = f"{argv[:3]}: {exc}"
        raise ToolFault(message) from exc
    if proc.returncode != 0:
        message = f"{argv[:3]} exited {proc.returncode}: {tool_text(proc.stderr)[:300]}"
        raise ToolFault(message)
    return tool_text(proc.stdout)


def _invocations(target: Path) -> dict[str, list[str]]:
    """Return the argv each Python runner of `coding_archetype` builds for `target`, running none."""
    argvs: dict[str, list[str]] = {}
    tool = [""]

    def record(argv: list[str], *_args: object, **_kwargs: object) -> None:
        argvs[tool[0]] = [str(part) for part in argv]
        raise _Recorded

    archetype = coding_archetype.CodingArchetype()
    with mock.patch.object(subprocess, "run", record):
        for name, runner in archetype._runners("python"):
            tool[0] = name
            try:
                runner(target)
            except (_Recorded, FileNotFoundError):
                continue
    return argvs


def _has_config(section: str, files: tuple[Path, ...]) -> bool:
    """Report whether `REPO_ROOT` pyproject.toml holds `section`, or any of `files` exists."""
    pyproject = REPO_ROOT / "pyproject.toml"
    if pyproject.is_file():
        table: Any = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        for key in section.split("."):
            table = table.get(key, {}) if isinstance(table, dict) else {}
        if table:
            return True
    return any(path.is_file() for path in files)


def _ruff(argv: list[str], root: Path) -> set[str]:
    """Return the codes `linter.rules.enabled` lists for `root` under the archetype's ruff flags."""
    flags = [part for part in argv[:-1] if not part.startswith("--output-format")]
    printed = _run([*flags, "--show-settings", str(root)], root)
    block = printed.partition("linter.rules.enabled = [")[2].partition("]")[0]
    codes = set(re.findall(r"\(([A-Z]+[0-9]+)\)", block))
    if not codes:
        message = "ruff --show-settings printed no linter.rules.enabled"
        raise ToolFault(message)
    return codes


def _mypy(argv: list[str], _root: Path) -> set[str]:
    """Return each mypy error code whose check the archetype's flags leave on, by `MYPY_OPTIONAL`."""
    installed = metadata.version("mypy")
    if installed != MYPY_BUILT:
        message = f"mypy {installed} installed; MYPY_OPTIONAL was read at {MYPY_BUILT}"
        raise ToolFault(message)
    home = Path.home()
    files = (
        REPO_ROOT / "mypy.ini",
        REPO_ROOT / ".mypy.ini",
        home / ".mypy.ini",
        home / ".config" / "mypy" / "config",
    )
    setup = configparser.ConfigParser()
    setup.read(REPO_ROOT / "setup.cfg", encoding="utf-8")
    if _has_config("tool.mypy", files) or setup.has_section("mypy"):
        message = "a mypy configuration is present where the archetype runs mypy"
        raise ToolFault(message)
    codes: dict[str, object] = importlib.import_module("mypy.errorcodes").error_codes
    unknown = sorted(set(MYPY_OPTIONAL) - set(codes))
    if unknown:
        message = f"mypy lists no code {unknown}"
        raise ToolFault(message)
    named = {
        argv[i + 1] for i, part in enumerate(argv[:-1]) if part == "--enable-error-code"
    }
    flags = set(argv)
    return {
        code
        for code in codes
        if code not in MYPY_OPTIONAL
        or code in named
        or flags.intersection(MYPY_OPTIONAL[code])
    }


def _pyright(argv: list[str], _root: Path) -> set[str]:
    """Return `PYRIGHT_STANDARD` when the installed pyright and its configuration match it."""
    installed = metadata.version("pyright")
    if installed != PYRIGHT_BUILT:
        message = f"pyright {installed} installed; PYRIGHT_STANDARD was read at {PYRIGHT_BUILT}"
        raise ToolFault(message)
    extra = [part for part in argv[1:-1] if part not in PYRIGHT_FLAGS]
    if extra or _has_config("tool.pyright", (REPO_ROOT / "pyrightconfig.json",)):
        message = f"pyright runs with flags {extra} or a configuration PYRIGHT_STANDARD does not read"
        raise ToolFault(message)
    return set(PYRIGHT_STANDARD)


def _bandit(argv: list[str], root: Path) -> set[str]:
    """Return the test ids bandit --help lists, when the archetype's argv selects no tests."""
    if BANDIT_SELECTORS.intersection(argv):
        message = f"the archetype selects bandit tests: {argv}"
        raise ToolFault(message)
    printed = _run([*argv[:3], "--help"], root)
    listing = printed.partition("discovered and loaded:")[2]
    return set(re.findall(r"^\s+(B[0-9]{3})\s", listing, re.MULTILINE))


def _vulture(argv: list[str], root: Path) -> set[str]:
    """Return {`VULTURE_RULE`} once vulture prints its version."""
    _run([*argv[:3], "--version"], root)
    return {VULTURE_RULE}


def _semgrep(argv: list[str], _root: Path) -> set[str]:
    """Return the rule ids semgrep --time reports for the archetype's configs on `SEMGREP_PROBE`."""
    configs = [part for part in argv if part.startswith("--config")]
    with tempfile.TemporaryDirectory() as folder:
        Path(folder, SEMGREP_PROBE).write_text("x = 1\n", encoding="utf-8")
        printed = _run(
            [
                argv[0],
                "scan",
                *configs,
                "--json",
                "--time",
                "--quiet",
                "--metrics=off",
                "--no-git-ignore",
                ".",
            ],
            Path(folder),
        )
    try:
        report = json.loads(printed)
        if report["errors"] or report["paths"]["scanned"] != [SEMGREP_PROBE]:
            message = f"semgrep did not read {SEMGREP_PROBE}: {report['errors']}"
            raise ToolFault(message)
        rules = report["time"]["rules"]
        return {rule if isinstance(rule, str) else rule["id"] for rule in rules}
    except (ValueError, KeyError, TypeError) as exc:
        message = f"semgrep printed an unreadable report: {exc!r}"
        raise ToolFault(message) from exc


def _pylint(argv: list[str], root: Path) -> set[str]:
    """Return the message ids pylint --list-msgs-enabled prints under the archetype's flags."""
    flags = [
        part
        for part in argv[3:]
        if part.startswith("--") and "output-format" not in part
    ]
    printed = _run([*argv[:3], *flags, "--list-msgs-enabled"], root)
    enabled = printed.partition("Enabled messages:")[2].partition("Disabled messages:")[
        0
    ]
    return set(re.findall(r"\(([A-Z][0-9]{4})\)", enabled))


READERS: dict[str, Reader] = {
    "ruff": _ruff,
    "mypy": _mypy,
    "pyright": _pyright,
    "bandit": _bandit,
    "vulture": _vulture,
    "semgrep": _semgrep,
    "pylint": _pylint,
}


def _rule_ids(module: str) -> set[str]:
    """Return each `RULE_ID_SHAPE` string in `module` that is not a docstring."""
    spec = importlib.util.find_spec(module)
    if spec is None or spec.origin is None:
        message = f"no module {module}"
        raise ToolFault(message)
    tree = ast.parse(Path(spec.origin).read_bytes())
    documented = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, documented)
        and ast.get_docstring(node, clean=False) is not None
        and isinstance(node.body[0], ast.Expr)
    }
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and RULE_ID_SHAPE.fullmatch(node.value)
    }


def rules_run(root: Path) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Return the rule ids each tool runs under `root`, and each unread tool's `ToolFault` text."""
    argvs = _invocations(Path(__file__).resolve())
    run: dict[str, set[str]] = {}
    unread: dict[str, str] = {}
    names = [
        name for name, _runner in coding_archetype.CodingArchetype()._runners("python")
    ]
    for tool in names:
        reader = READERS.get(tool)
        if reader is None:
            unread[tool] = "no reader in READERS"
        elif tool not in argvs:
            unread[tool] = "the archetype built no command for it here"
        else:
            try:
                run[tool] = reader(argvs[tool], root)
            except ToolFault as exc:
                unread[tool] = str(exc)
    for tool, module in coding_archetype._PY_RULE_MODULES:
        try:
            run[tool] = _rule_ids(module)
        except (ToolFault, OSError, SyntaxError) as exc:
            unread[tool] = str(exc)
    return run, unread


def _load(path: Path) -> dict[str, Any]:
    """Return the JSON object at `path`."""
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


Placements = dict[str, dict[tuple[str, str], list[dict[str, str]]]]


def house(folder: Path = HOUSE) -> tuple[Placements, set[tuple[str, str]]]:
    """Return each discipline's `Placements` by (tool, rule), and the unplaced (tool, rule) pairs."""
    placed: Placements = {}
    for name in DISCIPLINES:
        data = _load(folder / name / RULES_FILE)
        placed[name] = {
            (row["tool"], row["rule"]): row["grounds"] for row in data["rules"]
        }
    unplaced = {
        (row["tool"], row["rule"]) for row in _load(folder / UNPLACED_FILE)["rules"]
    }
    return placed, unplaced


def ungrounded(folder: Path = HOUSE) -> list[str]:
    """Return each ground in a `RULES_FILE` with no quote, or a CWE it neither lists nor the tool attached."""
    faults = []
    for name in DISCIPLINES:
        data = _load(folder / name / RULES_FILE)
        listed = set(data["cwe"])
        for row in data["rules"]:
            for ground in row["grounds"]:
                cwe = ground.get("cwe")
                if cwe and cwe not in listed and ground.get("attached") != row["tool"]:
                    faults.append(f"{name}: {row['tool']} {row['rule']} {cwe}")
                if not ground.get("attached") and not ground.get("quote"):
                    faults.append(f"{name}: {row['tool']} {row['rule']} has no quote")
    return faults


def count(root: Path, folder: Path = HOUSE) -> dict[str, Any]:
    """Return the per-tool and per-discipline counts for `root`, and every fault `CARD` names."""
    run, unread = rules_run(root)
    placed, unplaced = house(folder)
    housed = {key for rows in placed.values() for key in rows}
    pairs = {(tool, rule) for tool, rules in run.items() for rule in rules}
    held = housed | unplaced
    tools = {
        tool: {
            "run": len(rules),
            "placed": len({(tool, rule) for rule in rules} & housed),
            "unplaced": len({(tool, rule) for rule in rules} & unplaced),
        }
        for tool, rules in run.items()
    }
    faults = {
        "missing": sorted(f"{t} {r}" for t, r in pairs - held),
        "stale": sorted(f"{t} {r}" for t, r in held - pairs if t in run),
        "both": sorted(f"{t} {r}" for t, r in housed & unplaced),
        "ungrounded": ungrounded(folder),
        "unread": unread,
    }
    return {
        "root": str(root),
        "tools": tools,
        "totals": {
            "run": len(pairs),
            "placed": len(pairs & housed),
            "unplaced": len(pairs & unplaced),
        },
        "disciplines": {name: len(rows) for name, rows in placed.items()},
        "faults": faults,
    }


def main(argv: list[str] | None = None) -> int:
    """Print `CARD` with --card, else the `count` for --root; exit 1 on any fault."""
    parser = argparse.ArgumentParser(
        description="Count the Coding Archetype's rules by tool and by discipline."
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="the tree the archetype reads; default: the repository holding the working folder",
    )
    parser.add_argument("--card", action="store_true", help="print the card as JSON")
    args = parser.parse_args(argv)
    if args.card:
        print(json.dumps(CARD, indent=2))
        return 0
    root = args.root if args.root is not None else repository_root(Path.cwd())
    if root is None or not root.is_dir():
        print(
            "--root is not a folder, and no folder holding .git was found",
            file=sys.stderr,
        )
        return 1
    result = count(root.resolve())
    print(json.dumps(result, indent=2))
    return 1 if any(result["faults"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
