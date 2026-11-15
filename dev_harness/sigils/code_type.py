"""`SIGIL` is CODE.TYPE on the `core` card; `type_check` judges one input line."""

import ast
import json
import os
import platform
import subprocess
import sys
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from pathlib import Path

import mypy.errorcodes
import mypy.version
import pyright

from .coding_input import (
    CONTENT_TIER,
    DATA_TYPE_TIER,
    INPUT_FORM,
    OWNER,
    READERS,
    SEPARATOR,
    content_fault,
    data_type_fault,
    fault_file,
    locate,
)
from .coding_partition import SELECTION, selection
from .construct_rules import LEFT_BECAUSE, hold, house_rules
from .core import (
    APPLICATION_SOURCE,
    Flag,
    FlagRow,
    Sigil,
    Verdict,
    in_application_source,
    judge,
    main,
    tool_text,
)

SOUND = "SOUND"
UNSOUND = "UNSOUND"
REJECTED = "REJECTED"

MYPY_BUILT = "2.1.0"
PYRIGHT_BUILT = "1.1.411"
MYPY_TIMEOUT_S = 300
PYRIGHT_TIMEOUT_S = 120
MYPY_FINISHED = (0, 1)
PYRIGHT_FINISHED = (0, 1)
PYRIGHT_SEVERITIES = ("error", "warning")
NO_CODE = "no code"
NO_CHECKER = "no checker ran: the selection holds no rule of the card"
SOUND_MEANS = (
    f"mypy reports no error, pyright no {' or '.join(PYRIGHT_SEVERITIES)}, and no "
    "statement throws away a listed builtin's value, under a rule on the card"
)

OWN_TOOL = "code_type"
UNUSED_RESULT = "unused-builtin-result"
VALUE_ONLY_BUILTINS = frozenset(
    {
        "abs",
        "aiter",
        "ascii",
        "bin",
        "bool",
        "callable",
        "chr",
        "complex",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "globals",
        "hash",
        "hex",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "map",
        "object",
        "oct",
        "ord",
        "pow",
        "range",
        "repr",
        "reversed",
        "round",
        "slice",
        "str",
        "super",
        "zip",
    }
)
LEFT_OUT_BUILTINS: dict[str, tuple[str, ...]] = {
    "its page names an effect of its own": (
        "__import__",
        "breakpoint",
        "delattr",
        "eval",
        "exec",
        "help",
        "input",
        "open",
        "print",
        "setattr",
    ),
    "it advances an iterator": ("anext", "next"),
    "it iterates its argument, and iterating an iterator uses it up": (
        "all",
        "any",
        "bytearray",
        "bytes",
        "dict",
        "frozenset",
        "list",
        "max",
        "min",
        "set",
        "sorted",
        "sum",
        "tuple",
    ),
    "it reads an attribute, which runs a property's getter": (
        "classmethod",
        "dir",
        "getattr",
        "hasattr",
        "property",
        "staticmethod",
        "vars",
    ),
    "it raises an auditing event, which runs each audit hook": ("compile", "id"),
    "before Python 3.13 it refreshes the mapping an earlier call returned": ("locals",),
    "its buffer is released through __release_buffer__ when the view is freed": (
        "memoryview",
    ),
    "its three-argument form makes a class, which runs __init_subclass__": ("type",),
}
HANDLED_BODIES = (ast.Try, ast.TryStar, ast.With, ast.AsyncWith)
DEFERRED_BODIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

FUNCTION = (
    "reads each value against the type its annotation, assignment or call gives it, "
    "for a type fault that fails at run time, breaks the typing standard, or leaves "
    "implicit what Python's conventions ask to state, or for a builtin's value "
    "that no code reads"
)
DISCIPLINES = ("conventions", "reliability", "typing")
MYPY = hold("mypy", sorted(mypy.errorcodes.error_codes), DISCIPLINES)
PYRIGHT = hold("pyright", house_rules("pyright"), DISCIPLINES)
OWN = hold(OWN_TOOL, (UNUSED_RESULT,), DISCIPLINES)
CAN_RUN = tuple(
    f"{held.tool} {rule}" for held in (MYPY, PYRIGHT, OWN) for rule in held.rules
)

SETTINGS: dict[str, str] = {
    "separator": SEPARATOR,
    "mypy_version": MYPY_BUILT,
    "pyright_version": PYRIGHT_BUILT,
    "function": FUNCTION,
    "disciplines": " ".join(DISCIPLINES),
    "scope": "each code on mypy's own error code list, mypy.errorcodes.error_codes, "
    "and each pyright rule a discipline houses or unplaced.json lists: the rules "
    f"pyright reports as an {' or a '.join(PYRIGHT_SEVERITIES)} with no configuration; "
    f"and {UNUSED_RESULT}, the one rule this module runs itself",
    "mypy_rules": " ".join(MYPY.rules),
    "pyright_rules": " ".join(PYRIGHT.rules),
    "own_rules": " ".join(OWN.rules),
    "value_only_builtins": " ".join(sorted(VALUE_ONLY_BUILTINS)),
    "left_out_builtins": "; ".join(
        f"{' '.join(names)}: {reason}" for reason, names in LEFT_OUT_BUILTINS.items()
    ),
    "selection": SELECTION,
    "can_run": str(len(CAN_RUN)),
    "type_config": "the mypy and pyright settings each tool finds "
    "from the root of the target tree",
    "fault_file": "the file the input line names: HOLD when it sits "
    "in application_source",
}


class ToolFault(Exception):
    """mypy or pyright did not finish, or printed output `_findings` cannot read."""


@dataclass(frozen=True)
class Finding:
    """One finding: the `tool`, its error `code` and its `line`."""

    tool: str
    code: str
    line: int


def _same_file(reported: Path, file: Path) -> bool:
    """Report whether the `reported` path and `file` resolve to one path."""
    return reported.resolve() == file.resolve()


def _code_flags(disabled: tuple[str, ...]) -> list[str]:
    """Return mypy's --disable-error-code for each `disabled` code, and --enable-error-code for each sub code it would hide."""
    kept = [
        code
        for code, item in mypy.errorcodes.error_codes.items()
        if item.sub_code_of is not None
        and item.sub_code_of.code in disabled
        and code not in disabled
    ]
    return [
        *(flag for code in disabled for flag in ("--disable-error-code", code)),
        *(flag for code in kept for flag in ("--enable-error-code", code)),
    ]


def _mypy_findings(
    path: str, root: Path, file: Path, disabled: tuple[str, ...]
) -> list[Finding]:
    """Return each mypy error in `file`, run on `path` from `root` with no cache and no `disabled` code run."""
    argv = [sys.executable, "-P", "-m", "mypy", "--output", "json", "--cache-dir", os.devnull]
    try:
        proc = subprocess.run(
            [*argv, *_code_flags(disabled), path],
            cwd=root,
            capture_output=True,
            timeout=MYPY_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolFault(f"mypy: {exc}") from exc
    if proc.returncode not in MYPY_FINISHED:
        said = tool_text(proc.stderr or proc.stdout)
        raise ToolFault(f"mypy exited {proc.returncode}: {said}")
    try:
        lines = tool_text(proc.stdout).splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
        return [
            Finding("mypy", row["code"] or NO_CODE, row["line"])
            for row in rows
            if row["severity"] == "error" and _same_file(root / row["file"], file)
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolFault(f"mypy printed an unreadable row: {exc}") from exc


def _pyright_findings(path: str, root: Path, file: Path) -> tuple[str, list[Finding]]:
    """Return the pyright version and each pyright row in `file` at a `PYRIGHT_SEVERITIES` level, run from `root`."""
    try:
        proc = pyright.run(
            "--outputjson",
            path,
            cwd=root,
            capture_output=True,
            timeout=PYRIGHT_TIMEOUT_S,
            check=False,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise ToolFault(f"pyright: {exc}") from exc
    if proc.returncode not in PYRIGHT_FINISHED:
        said = tool_text(proc.stderr or proc.stdout)
        raise ToolFault(f"pyright exited {proc.returncode}: {said}")
    try:
        report = json.loads(proc.stdout)
        if report["summary"]["filesAnalyzed"] < 1:
            raise ToolFault(f"pyright analyzed no file for {path}")
        return report["version"], [
            Finding(
                "pyright",
                diagnostic.get("rule") or NO_CODE,
                diagnostic["range"]["start"]["line"] + 1,
            )
            for diagnostic in report["generalDiagnostics"]
            if diagnostic["severity"] in PYRIGHT_SEVERITIES
            and _same_file(Path(diagnostic["file"]), file)
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolFault(f"pyright printed an unreadable report: {exc}") from exc


def _bound_names(tree: ast.Module) -> frozenset[str] | None:
    """Return each name `tree` binds, or None when a star import can bind any name."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.alias):
            if node.name == "*":
                return None
            names.add(node.asname or node.name.partition(".")[0])
        elif isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(name := getattr(node, "name", None), str):
            names.add(name)
        elif isinstance(rest := getattr(node, "rest", None), str):
            names.add(rest)
    return frozenset(names)


def _in_handled_body(node: ast.stmt, parents: dict[ast.AST, ast.AST]) -> bool:
    """Report whether `node` sits in a `HANDLED_BODIES` body before any `DEFERRED_BODIES` parent."""
    child: ast.AST = node
    parent = parents.get(child)
    while parent is not None and not isinstance(parent, DEFERRED_BODIES):
        if isinstance(parent, HANDLED_BODIES) and any(child is s for s in parent.body):
            return True
        child, parent = parent, parents.get(parent)
    return False


def _unused_builtin_results(source: bytes) -> tuple[int, ...]:
    """Return the line of each statement throwing away a `VALUE_ONLY_BUILTINS` call's value, outside a try body or with suite."""
    tree = ast.parse(source)
    bound = _bound_names(tree)
    if bound is None:
        return ()
    names = VALUE_ONLY_BUILTINS - bound
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    return tuple(
        sorted(
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id in names
            and not _in_handled_body(node, parents)
        )
    )


def findings(text: str, root: Path, to_run: Collection[str]) -> tuple[str, list[Finding]]:
    """Return the checkers run and each `Finding` of the `to_run` rules inside the input `text` names."""
    located = locate(text, root)
    if isinstance(located, str):
        raise ToolFault(f"{text}: {located}, after tier 2 accepted it")
    file, source, (first, last) = located
    path, separator, _ = text.partition(SETTINGS["separator"])
    is_narrowed = bool(separator)
    ran: list[str] = []
    errors: list[Finding] = []
    mypy_run = [rule for rule in MYPY.rules if f"{MYPY.tool} {rule}" in to_run]
    if mypy_run:
        disabled = tuple(rule for rule in MYPY.rules if rule not in mypy_run)
        ran.append(f"mypy {mypy.version.__version__}")
        errors += _mypy_findings(path, root, file, disabled)
    if any(f"{PYRIGHT.tool} {rule}" in to_run for rule in PYRIGHT.rules):
        version, found = _pyright_findings(path, root, file)
        ran.append(f"pyright {version}")
        errors += found
    if f"{OWN.tool} {UNUSED_RESULT}" in to_run:
        ran.append(f"{OWN.tool} on Python {platform.python_version()}")
        errors += [
            Finding(OWN.tool, UNUSED_RESULT, line)
            for line in _unused_builtin_results(source)
        ]
    kept = [
        finding
        for finding in errors
        if f"{finding.tool} {finding.code}" in to_run
        and (not is_narrowed or first <= finding.line <= last)
    ]
    return ", ".join(ran) or NO_CHECKER, kept


def _functions_verdict(text: str, root: Path) -> tuple[str, str]:
    """Return `SOUND`, or `UNSOUND` with each `Finding` of the `selection` rules inside the `locate` span."""
    versions, found = findings(text, root, selection(text, root, CAN_RUN))
    if not found:
        return SOUND, f"{versions}: {SOUND_MEANS}"
    rows = "; ".join(f"{item.tool} {item.code} line {item.line}" for item in found)
    return UNSOUND, f"{versions}: {rows}"


SIGIL = Sigil(
    name="CODE.TYPE",
    edition=1,
    owner=OWNER,
    disciplines=DISCIPLINES,
    input_form=INPUT_FORM,
    settings=SETTINGS,
    tiers=(
        DATA_TYPE_TIER,
        CONTENT_TIER,
        {
            "runs": [
                "the selection: the rules of the card that coding_partition.select "
                "gives for the input's facts",
                (
                    "mypy, as python -P -m mypy from the root of the target tree, "
                    "with --output json, the null device as its cache folder, and "
                    "--disable-error-code for each mypy rule of the card the selection "
                    "leaves out, when the selection holds a mypy rule; a selected sub "
                    "code of a left-out code gets --enable-error-code"
                ),
                (
                    "pyright, through pyright.run from the root of the target tree, "
                    "with --outputjson, when the selection holds a pyright rule"
                ),
                (
                    f"{UNUSED_RESULT}, when the selection holds it: Python's ast module "
                    "parses the file, and each expression statement whose whole value is "
                    "a call to a value_only_builtins name the module never binds is a "
                    "finding, unless it sits in a try body or a with suite"
                ),
                "only the mypy errors, and the pyright rows at "
                f"{' or '.join(PYRIGHT_SEVERITIES)}, under the selected rules",
                "for a symbol, only the findings inside its lines",
            ],
            "sound": SOUND_MEANS,
            "unsound": ["tool", "error code", "line"],
            "left": {
                MYPY.tool: MYPY.left,
                PYRIGHT.tool: PYRIGHT.left,
                OWN.tool: OWN.left,
            },
            "left_because": LEFT_BECAUSE,
            "not_held": "an error under a code outside the scope, or with no code, "
            "moves no verdict",
            "trusts": "a plugin or interpreter the tree's own mypy or pyright "
            "settings name runs as code",
            "imports": "each tool resolves them from the root of the target tree "
            "and the installed packages it finds, never from the tree's own "
            "list of files to check",
        },
    ),
    outputs={
        SOUND: FlagRow(Flag.PASS),
        UNSOUND: FlagRow(Flag.FIX, holds_in_source=True),
    },
    refusal=REJECTED,
    follows={},
    readers=READERS,
    data_type=data_type_fault,
    content=content_fault,
    functions=_functions_verdict,
    fault_file=fault_file,
)


def type_check(
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
        print(f"mypy or pyright did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
