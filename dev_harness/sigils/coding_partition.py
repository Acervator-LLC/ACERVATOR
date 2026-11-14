"""`select` names the Coding Archetype rules an input can hold, by the keys in `KEYS_FILE`; `prove` checks a tree."""

import argparse
import ast
import json
import statistics
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any
from unittest import mock

from dev_harness.harness import coding_archetype, report

from . import coding_house
from .coding_input import _SCOPES, _scope, data_type_fault, locate
from .core import repository_root, tool_text
from .partition_measure import KEYS_FILE, KINDS, SIZES

TOOL_TIMEOUT_S = 1800
TEST_NAMES = ("test_*.py", "*_test.py")
PROOF_TREE = "src"
CONTROL_MODULE = "control_module_no_input_imports"
KEY_NAMES = ("reach", "nodes", "imports", "file")
RANK = {size: rank for rank, size in enumerate(SIZES)}

Finding = tuple[str, str, int]
Rules = dict[str, dict[str, Any]]
ScopeNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


@dataclass(frozen=True)
class Facts:
    """What an input holds before any rule runs: its `size`, file `kinds`, AST `nodes` and file `imports`."""

    size: str
    kinds: frozenset[str]
    nodes: frozenset[str]
    imports: frozenset[str]


@dataclass(frozen=True)
class Input:
    """One input: its `text` form, the `file` it reads, its line `span` and its `facts`."""

    text: str
    file: str
    span: tuple[int, int]
    facts: Facts


def file_kind(path: Path) -> str:
    """Return `stub`, `notebook`, `test` by pytest's default python_files `TEST_NAMES`, or `source`."""
    if path.suffix == ".pyi":
        return "stub"
    if path.suffix == ".ipynb":
        return "notebook"
    return "test" if any(fnmatch(path.name, name) for name in TEST_NAMES) else "source"


def imports_of(tree: ast.AST) -> frozenset[str]:
    """Return the top-level package of every absolute import statement in `tree`."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module.split(".")[0])
    return frozenset(found)


def nodes_of(node: ast.AST) -> frozenset[str]:
    """Return the type name of every node under and including `node`."""
    return frozenset(type(child).__name__ for child in ast.walk(node))


def _scopes(node: ast.AST, prefix: str) -> Iterator[tuple[ScopeNode, str]]:
    """Yield each def and class under `node` with its dotted name from `prefix`."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPES):
            name = f"{prefix}{child.name}"
            yield child, name
            yield from _scopes(child, f"{name}.")
        else:
            yield from _scopes(child, prefix)


def module_inputs(root: Path, relative: str) -> Iterator[Input]:
    """Yield the module input for the file `relative` under `root`, then each def and class in it."""
    path = root / relative
    source = path.read_bytes()
    tree = ast.parse(source)
    kinds = frozenset({file_kind(path)})
    imports = imports_of(tree)
    module = Facts("module", kinds, nodes_of(tree), imports)
    yield Input(relative, relative, (1, len(source.splitlines()) or 1), module)
    for scope, name in _scopes(tree, ""):
        first = min([scope.lineno, *(d.lineno for d in scope.decorator_list)])
        span = (first, scope.end_lineno or scope.lineno)
        yield Input(
            f"{relative}, in {name}",
            relative,
            span,
            Facts("scope", kinds, nodes_of(scope), imports),
        )


def project_facts(inputs: list[Input]) -> Facts:
    """Return the project input's facts: the union of its module inputs' facts."""
    modules = [item.facts for item in inputs if item.facts.size == "module"]
    return Facts(
        "project",
        frozenset().union(*(f.kinds for f in modules)),
        frozenset().union(*(f.nodes for f in modules)),
        frozenset().union(*(f.imports for f in modules)),
    )


def python_files(folder: Path) -> list[Path]:
    """Return every `.py` file under `folder`, outside `__pycache__`."""
    return sorted(p for p in folder.rglob("*.py") if "__pycache__" not in p.parts)


def facts_of(text: str, root: Path) -> Facts | str:
    """Return the `Facts` of input `text` under `root`: a folder, a file, or a file and symbol; or the fault."""
    fault = data_type_fault(text)
    if fault:
        return fault
    folder = root / text.strip("/")
    if folder.is_dir() and folder.resolve().is_relative_to(root):
        files = python_files(folder)
        return project_facts(
            [
                i
                for p in files
                for i in module_inputs(root, p.relative_to(root).as_posix())
            ]
        )
    located = locate(text, root)
    if isinstance(located, str):
        return located
    file, source, _span = located
    tree = ast.parse(source)
    kinds = frozenset({file_kind(file)})
    _path, _sep, symbol = text.partition(", in ")
    if not symbol:
        return Facts("module", kinds, nodes_of(tree), imports_of(tree))
    scope = _scope(tree, symbol.split("."))
    return Facts("scope", kinds, nodes_of(scope or tree), imports_of(tree))


def binds(key: dict[str, Any]) -> bool:
    """Report whether `key` carries a grounded `value`; an `open` key binds nothing."""
    return "value" in key


def reach_of(keys: dict[str, Any]) -> str:
    """Return the rule's reach, the smallest of `SIZES` when its reach key is open."""
    return keys["reach"]["value"] if binds(keys["reach"]) else SIZES[0]


def left_out_by(keys: dict[str, Any], facts: Facts) -> list[str]:
    """Return each of `KEY_NAMES` whose grounded value `facts` does not meet."""
    out = []
    if RANK[reach_of(keys)] > RANK[facts.size]:
        out.append("reach")
    nodes = keys["nodes"].get("value")
    if nodes and not facts.nodes.intersection(nodes):
        out.append("nodes")
    imports = keys["imports"].get("value")
    if imports and not facts.imports.intersection(imports):
        out.append("imports")
    if binds(keys["file"]) and not facts.kinds.intersection(keys["file"]["value"]):
        out.append("file")
    return out


def runs(keys: dict[str, Any], facts: Facts) -> bool:
    """Apply the run rule: a rule runs on `facts` when no key in `left_out_by` leaves it out."""
    return not left_out_by(keys, facts)


def select(rules: Rules, facts: Facts) -> list[str]:
    """Return the rules whose keys `runs` accepts for `facts`."""
    return sorted(name for name, keys in rules.items() if runs(keys, facts))


def load(path: Path = KEYS_FILE) -> Rules:
    """Return the per-rule keys held in `path`."""
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    rules: Rules = data["rules"]
    return rules


def _patched_run(real: Any) -> Any:
    """Return `subprocess.run` with each call's timeout raised to `TOOL_TIMEOUT_S`."""

    def run(*args: Any, **kwargs: Any) -> Any:
        kwargs["timeout"] = TOOL_TIMEOUT_S
        return real(*args, **kwargs)

    return run


def _relative(file: str, root: Path) -> str:
    """Return `file` as a posix path relative to `root`."""
    path = Path(file)
    path = path if path.is_absolute() else report.REPO_ROOT / path
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def tool_findings(
    root: Path, tree: Path, rules: Rules
) -> tuple[list[Finding], dict[str, str]]:
    """Return every rule's findings over `tree` from the archetype's own calls, and each tool's status."""
    archetype = coding_archetype.CodingArchetype()
    found: list[Finding] = []
    status: dict[str, str] = {}
    with mock.patch.object(subprocess, "run", _patched_run(subprocess.run)):
        for name, runner in archetype._runners("python"):
            if name != "pylint":
                rows, status[name] = runner(tree)
                found += [
                    (f"{name} {row.rule_id}", _relative(row.file, root), row.line)
                    for row in rows
                ]
    found += _pylint_findings(root, tree, status)
    found += _preview_findings(root, tree, rules, status)
    scanned = report.ArchetypeReport(target=str(tree))
    report.scan_rule_modules(scanned, tree, coding_archetype._PY_RULE_MODULES, (".py",))
    status.update(scanned.tool_availability)
    tools = {name.split(" ")[1]: name.split(" ")[0] for name in rules}
    found += [
        (
            f"{tools.get(row.rule_id, row.tool)} {row.rule_id}",
            _relative(row.file, root),
            row.line,
        )
        for row in scanned.findings
    ]
    return found, status


def _pylint_findings(root: Path, tree: Path, status: dict[str, str]) -> list[Finding]:
    """Return a pylint finding at each module a duplicate-code row names beside another module."""
    argv = coding_house._invocations(tree)["pylint"]
    proc = subprocess.run(
        argv,
        cwd=report.REPO_ROOT,
        capture_output=True,
        timeout=TOOL_TIMEOUT_S,
        check=False,
    )
    rows = json.loads(tool_text(proc.stdout) or "[]")
    status["pylint"] = "ok" if isinstance(rows, list) else "error"
    names: dict[str, str] = {}
    for path in python_files(tree):
        for name in coding_archetype.CodingArchetype._pylint_module_names(path):
            names.setdefault(name, path.resolve().relative_to(root).as_posix())
    found: list[Finding] = []
    for row in rows:
        spans = coding_archetype._PYLINT_FRAGMENT.findall(row.get("message", ""))
        for module, start, _end in spans:
            if module in names and len(spans) > 1:
                found.append(
                    (
                        f"pylint {row.get('message-id', 'R0801')}",
                        names[module],
                        int(start) + 1,
                    )
                )
    return found


def _preview_findings(
    root: Path, tree: Path, rules: Rules, status: dict[str, str]
) -> list[Finding]:
    """Return the findings of the sigils' preview rules over `tree`, read with --preview as the sigils read them."""
    preview = sorted(
        name.split(" ")[1] for name, keys in rules.items() if keys.get("preview")
    )
    if not preview:
        return []
    argv = [sys.executable, "-m", "ruff", "check", "--output-format=json", "--no-cache"]
    argv += ["--preview", "--select", ",".join(preview), str(tree)]
    proc = subprocess.run(
        argv,
        cwd=report.REPO_ROOT,
        capture_output=True,
        timeout=TOOL_TIMEOUT_S,
        check=False,
    )
    rows = json.loads(tool_text(proc.stdout) or "[]")
    status["ruff preview"] = "ok" if isinstance(rows, list) else "error"
    return [
        (
            f"ruff {row['code']}",
            _relative(row["filename"], root),
            row["location"]["row"],
        )
        for row in rows
        if row.get("code") and row.get("location")
    ]


def tree_inputs(root: Path, tree: Path) -> list[Input]:
    """Return every module and scope input of the `.py` files under `tree`, and the project input last."""
    inputs = [
        i
        for p in python_files(tree)
        for i in module_inputs(root, p.relative_to(root).as_posix())
    ]
    project = Input(
        tree.relative_to(root).as_posix(), "", (0, 0), project_facts(inputs)
    )
    return [*inputs, project]


def _held(item: Input, finding: Finding, keys: dict[str, Any]) -> bool:
    """Report whether `finding` is one `item` must carry: the project holds all, else non-project rules in its span."""
    if item.facts.size == "project":
        return True
    in_span = finding[1] == item.file and item.span[0] <= finding[2] <= item.span[1]
    return in_span and reach_of(keys) != "project"


def _label(facts: Facts) -> str:
    """Return the table row an input counts under: its size, and its file kind for a module."""
    return f"module ({min(facts.kinds)})" if facts.size == "module" else facts.size


def compare(
    rules: Rules, inputs: list[Input], findings: list[Finding]
) -> dict[str, Any]:
    """Compare per input the findings of its selected rules with the findings of every rule it must carry."""
    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        by_file.setdefault(finding[1], []).append(finding)
    lost: list[dict[str, Any]] = []
    run_counts: dict[str, list[int]] = {}
    partitioned: dict[str, set[str]] = {key: set() for key in KEY_NAMES}
    for item in inputs:
        selected = set()
        for name, keys in rules.items():
            out = left_out_by(keys, item.facts)
            for key in out:
                partitioned[key].add(name)
            if not out:
                selected.add(name)
        run_counts.setdefault(_label(item.facts), []).append(len(selected))
        pool = findings if item.facts.size == "project" else by_file.get(item.file, [])
        for finding in pool:
            if finding[0] not in selected and _held(item, finding, rules[finding[0]]):
                lost.append(
                    {
                        "input": item.text,
                        "rule": finding[0],
                        "file": finding[1],
                        "line": finding[2],
                        "left out by": left_out_by(rules[finding[0]], item.facts),
                    }
                )
    return {"lost": lost, "runs": run_counts, "partitioned": partitioned}


def coverage(rules: Rules) -> dict[str, dict[str, int]]:
    """Return per key how many rules carry a grounded value and how many carry `open`."""
    return {
        key: {
            "grounded": sum(binds(keys[key]) for keys in rules.values()),
            "open": sum(not binds(keys[key]) for keys in rules.values()),
        }
        for key in KEY_NAMES
    }


def table(compared: dict[str, Any], rules: Rules) -> dict[str, Any]:
    """Return the rules run per input kind, and per key the rules it left out of at least one input."""
    runs_table = {
        label: {
            "inputs": len(counts),
            "lowest": min(counts),
            "median": statistics.median(counts),
            "highest": max(counts),
        }
        for label, counts in sorted(compared["runs"].items())
    }
    return {
        "rules": len(rules),
        "coverage": coverage(rules),
        "partitioned": {
            key: len(names) for key, names in compared["partitioned"].items()
        },
        "runs": runs_table,
    }


def _findings(
    root: Path, tree: Path, rules: Rules, saved: Path | None
) -> tuple[list[Finding], dict[str, str]]:
    """Return the tool findings over `tree`, read from `saved` when it exists, else run and saved there."""
    if saved is not None and saved.is_file():
        data = json.loads(saved.read_text(encoding="utf-8"))
        return [(str(r), str(f), int(n)) for r, f, n in data["findings"]], data[
            "status"
        ]
    found, status = tool_findings(root, tree, rules)
    if saved is not None:
        saved.write_text(
            json.dumps({"status": status, "findings": found}), encoding="utf-8"
        )
    return found, status


def prove(root: Path, keys_path: Path, saved: Path | None) -> dict[str, Any]:
    """Return the proof over `PROOF_TREE`: findings per tool, the table, and every lost finding."""
    rules = load(keys_path)
    tree = root / PROOF_TREE
    findings, status = _findings(root, tree, rules, saved)
    inputs = tree_inputs(root, tree)
    counted = [f for f in findings if f[0] in rules]
    compared = compare(rules, inputs, counted)
    outside: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    for rule, _file, _line in findings:
        if rule in rules:
            by_tool[rule.split(" ")[0]] = by_tool.get(rule.split(" ")[0], 0) + 1
        else:
            outside[rule] = outside.get(rule, 0) + 1
    return {
        "tree": PROOF_TREE,
        "status": status,
        "inputs": {
            "module": sum(i.facts.size == "module" for i in inputs),
            "scope": sum(i.facts.size == "scope" for i in inputs),
            "project": 1,
        },
        "findings": by_tool,
        "findings outside the rules": outside,
        "rules with a finding": len({f[0] for f in counted}),
        "table": table(compared, rules),
        "lost": compared["lost"],
    }


def broken_copy(keys_path: Path, rule: str, target: Path) -> None:
    """Write to `target` a copy of `keys_path` whose `rule` needs `CONTROL_MODULE`, which no input imports."""
    data = json.loads(keys_path.read_text(encoding="utf-8"))
    data["rules"][rule]["imports"] = {"value": [CONTROL_MODULE], "ground": "control"}
    target.write_text(json.dumps(data), encoding="utf-8")


def show(text: str, root: Path, rules: Rules) -> dict[str, Any] | str:
    """Return the facts of input `text` and the rules the run rule selects for it, or its fault."""
    facts = facts_of(text, root)
    if isinstance(facts, str):
        return facts
    by_tool: dict[str, list[str]] = {}
    selected = select(rules, facts)
    for name in selected:
        tool, _sep, rule = name.partition(" ")
        by_tool.setdefault(tool, []).append(rule)
    return {
        "input": text,
        "facts": {
            "size": facts.size,
            "file kind": sorted(facts.kinds, key=KINDS.index),
            "nodes": sorted(facts.nodes),
            "imports": sorted(facts.imports),
        },
        "rules run": len(selected),
        "of": len(rules),
        "by tool": {
            tool: {"count": len(names), "rules": names}
            for tool, names in sorted(by_tool.items())
        },
    }


CARD: dict[str, object] = {
    "house": "coding",
    "edition": 1,
    "owner": "coding",
    "inputs": {
        "scope": "<path>, in <symbol>: one def, async def or class",
        "module": "<path>: one Python file",
        "project": "<folder>: every .py file under it",
    },
    "facts": {
        "size": "scope, module or project, by the input's form",
        "file kind": f"stub (.pyi), notebook (.ipynb), test (pytest's python_files {' '.join(TEST_NAMES)}), else source",
        "nodes": "the AST node type names the input holds",
        "imports": "the top-level packages its file imports",
    },
    "run rule": "a rule runs when its reach is no larger than the input, the input's file kind is one "
    "it names, the input holds one node type it names, and the file imports one module it names; "
    "an open key binds nothing",
    "proof": f"every .py file of {PROOF_TREE}/ as a module input, every def and class in it as a scope "
    "input, and the folder as the project input: no finding of a rule the input must carry is left "
    "out by the selection, read once from the archetype's own calls",
    "keys": str(KEYS_FILE.relative_to(report.REPO_ROOT)).replace("\\", "/"),
}


def main(argv: list[str] | None = None) -> int:
    """Print `CARD`, one input's facts and rules, or the proof; exit 1 on a fault or a lost finding."""
    parser = argparse.ArgumentParser(
        description="Select the Coding Archetype rules an input can hold."
    )
    parser.add_argument(
        "input", nargs="?", help="<path>, <path>, in <symbol>, or a folder"
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="the target tree; default: the repository holding the working folder",
    )
    parser.add_argument("--card", action="store_true", help="print the card as JSON")
    parser.add_argument(
        "--prove", action="store_true", help=f"prove the run rule on {PROOF_TREE}/"
    )
    parser.add_argument(
        "--keys", type=Path, default=KEYS_FILE, help="the keys file to read"
    )
    parser.add_argument(
        "--findings",
        type=Path,
        help="a file the proof saves its tool findings to, or reads them from",
    )
    parser.add_argument(
        "--control",
        help="'<tool> <rule>': prove on a copy of the keys where it needs a module no input imports",
    )
    args = parser.parse_args(argv)
    if args.card or (args.input is None and not args.prove):
        print(json.dumps(CARD, indent=2))
        return 0
    root = args.root if args.root is not None else repository_root(Path.cwd())
    if root is None or not root.is_dir():
        print(
            "--root is not a folder, and no folder holding .git was found",
            file=sys.stderr,
        )
        return 1
    root = root.resolve()
    if not args.prove:
        shown = show(args.input, root, load(args.keys))
        print(json.dumps(shown, indent=2) if isinstance(shown, dict) else shown)
        return 1 if isinstance(shown, str) else 0
    keys_path = args.keys
    if args.control:
        keys_path = Path(args.findings or args.keys).with_name("partition_control.json")
        broken_copy(args.keys, args.control, keys_path)
    result = prove(root, keys_path, args.findings)
    print(json.dumps(result, indent=2))
    return 1 if result["lost"] else 0


if __name__ == "__main__":
    sys.exit(main())
