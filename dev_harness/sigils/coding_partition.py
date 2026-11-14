"""`select` names the Coding Archetype rules an input can hold, by the keys in `KEYS_FILE`; `prove` checks a tree."""

import argparse
import ast
import importlib
import json
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from fnmatch import fnmatch
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

from dev_harness.harness import coding_archetype, report

from . import coding_house
from .coding_input import _SCOPES, OWNER, _scope, data_type_fault, locate
from .core import discipline_fault, repository_root, tool_text
from .partition_measure import KEYS_FILE, KINDS, SIZES

TOOL_TIMEOUT_S = 1800
TEST_NAMES = ("test_*.py", "*_test.py")
PROOF_TREE = "src"
CONTROL_MODULE = "control_module_no_input_imports"
KEY_NAMES = ("reach", "nodes", "imports", "file")
RANK = {size: rank for rank, size in enumerate(SIZES)}
TOOL_SCOPE = "scope"
SELECTION = (
    "for each input, only the rules the card can run that coding_partition.select "
    "gives for the input's facts, by the keys in dev_harness/disciplines/partition.json"
)
FILE_CALLS = (
    "locate",
    "_ruff_findings",
    "_mypy_findings",
    "_pyright_findings",
    "_bandit_findings",
    "_semgrep_findings",
)
TREE_CALLS = ("_vulture_scan",)
PROOF_WORKERS = 3
FILES_PER_WORKER = 2

Finding = tuple[str, str, int]
Rules = dict[str, dict[str, Any]]
ScopeNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


class FactsFault(Exception):
    """`facts_of` refused an input that a sigil's tier 2 accepted."""


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


def reach_fits(keys: dict[str, Any], facts: Facts) -> bool:
    """Report whether the rule's reach is no larger than `facts.size`; a `TOOL_SCOPE` reach fits every input."""
    if keys["reach"].get("ground") == TOOL_SCOPE:
        return True
    return RANK[reach_of(keys)] <= RANK[facts.size]


def left_out_by(keys: dict[str, Any], facts: Facts) -> list[str]:
    """Return each of `KEY_NAMES` whose grounded value `facts` does not meet."""
    out = []
    if not reach_fits(keys, facts):
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


def select(rules: Rules, facts: Facts, among: Iterable[str] | None = None) -> list[str]:
    """Return the rules, of `among` when given, that `runs` accepts for `facts`; a rule `rules` lacks runs."""
    names = rules if among is None else among
    return sorted(
        name for name in names if name not in rules or runs(rules[name], facts)
    )


def load(path: Path = KEYS_FILE) -> Rules:
    """Return the per-rule keys held in `path`."""
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    rules: Rules = data["rules"]
    return rules


@cache
def keys() -> Rules:
    """Return `load` of `KEYS_FILE`, read once per process."""
    return load()


def selection(text: str, root: Path, held: Iterable[str]) -> list[str]:
    """Return the `held` rules that `select` gives over `keys` for the `facts_of` input `text` under `root`."""
    facts = facts_of(text, root)
    if isinstance(facts, str):
        message = f"{text}: {facts}"
        raise FactsFault(message)
    return select(keys(), facts, held)


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
    """Report whether `item` must carry `finding`: the project holds all, else rules whose reach fits, in its span."""
    if item.facts.size == "project":
        return True
    in_span = finding[1] == item.file and item.span[0] <= finding[2] <= item.span[1]
    return in_span and reach_fits(keys, item.facts)


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


def _spread(counts: list[int]) -> dict[str, float]:
    """Return the lowest, median and highest of `counts`."""
    return {
        "lowest": min(counts),
        "median": statistics.median(counts),
        "highest": max(counts),
    }


def table(compared: dict[str, Any], rules: Rules) -> dict[str, Any]:
    """Return the rules run per input kind, and per key the rules it left out of at least one input."""
    runs_table = {
        label: {"inputs": len(counts), **_spread(counts)}
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


def coding_sigils() -> list[ModuleType]:
    """Return each module beside this one whose `SIGIL` the `OWNER` archetype owns."""
    found = []
    for path in sorted(Path(__file__).parent.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        module = importlib.import_module(f"{__package__}.{path.stem}")
        if getattr(getattr(module, "SIGIL", None), "owner", None) == OWNER:
            found.append(module)
    return found


def _cache_tool_calls() -> None:
    """Hold each `FILE_CALLS` and `TREE_CALLS` function of every `coding_sigils` module in `cache`."""
    for module in coding_sigils():
        for name in (*FILE_CALLS, *TREE_CALLS):
            call = getattr(module, name, None)
            if call is not None:
                setattr(module, name, cache(call))


def _clear_file_calls(sigils: list[ModuleType]) -> None:
    """Empty the cache of each `FILE_CALLS` function of `sigils`, once one file's inputs are read."""
    for module in sigils:
        for name in FILE_CALLS:
            clear = getattr(getattr(module, name, None), "cache_clear", None)
            if clear is not None:
                clear()


def tracked_files(root: Path, tree: str) -> list[str]:
    """Return each `.py` file under `tree` that git tracks in `root`, as a posix path, largest first."""
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--", f"{tree}/*.py"],
        cwd=root,
        capture_output=True,
        timeout=TOOL_TIMEOUT_S,
        check=True,
    )
    names = [name for name in tool_text(proc.stdout).split("\0") if name]
    return sorted(names, key=lambda name: (-(root / name).stat().st_size, name))


def prove_file(
    root: Path, relative: str, keys_path: Path, names: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Return a row per input of `relative` and per `names` sigil whose tier 2 accepts it: rules run, findings both ways."""
    rules = load(keys_path)
    sigils = [m for m in coding_sigils() if m.SIGIL.name in names]
    faults = (*{m.ToolFault for m in sigils}, FactsFault, OSError, subprocess.SubprocessError)
    rows: list[dict[str, Any]] = []
    for text in dict.fromkeys(item.text for item in module_inputs(root, relative)):
        facts = facts_of(text, root)
        if isinstance(facts, str):
            rows.append({"input": text, "fault": facts})
            continue
        for module in sigils:
            sigil = module.SIGIL
            if sigil.data_type(text) or sigil.content(text, root):
                continue
            selected = select(rules, facts, module.CAN_RUN)
            try:
                chosen = [str(f) for f in module.findings(text, root, selected)[1]]
                every = [str(f) for f in module.findings(text, root, module.CAN_RUN)[1]]
            except faults as exc:
                rows.append({"input": text, "sigil": sigil.name, "fault": repr(exc)})
                continue
            rows.append(
                {
                    "input": text,
                    "sigil": sigil.name,
                    "size": facts.size,
                    "runs": len(selected),
                    "with selection": len(chosen),
                    "with every rule": len(every),
                    "equal": chosen == every,
                    "lost": sorted((Counter(every) - Counter(chosen)).elements()),
                    "added": sorted((Counter(chosen) - Counter(every)).elements()),
                }
            )
    _clear_file_calls(sigils)
    return rows


def _summary(sigils: list[ModuleType], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return per sigil and input size the inputs, rules run before and after, and findings both ways."""
    summary: dict[str, Any] = {}
    for module in sigils:
        name = module.SIGIL.name
        mine = [row for row in rows if row.get("sigil") == name and "size" in row]
        sizes: dict[str, Any] = {}
        for size in ("module", "scope"):
            sized = [row for row in mine if row["size"] == size]
            if not sized:
                continue
            sizes[size] = {
                "inputs": len(sized),
                "before": len(module.CAN_RUN),
                "after": _spread([row["runs"] for row in sized]),
                "findings with selection": sum(row["with selection"] for row in sized),
                "findings with every rule": sum(row["with every rule"] for row in sized),
            }
        summary[name] = {"can run": len(module.CAN_RUN), **sizes}
    return summary


def _saved_rows(saved: Path | None) -> dict[str, list[dict[str, Any]]]:
    """Return the rows `saved` holds per file, one JSON line per file, or none when it is absent."""
    if saved is None or not saved.is_file():
        return {}
    lines = saved.read_text(encoding="utf-8").splitlines()
    return {entry["file"]: entry["rows"] for entry in map(json.loads, lines) if entry}


def prove_sigils(
    root: Path,
    keys_path: Path,
    control: str | None = None,
    saved: Path | None = None,
    only: str | None = None,
    workers: int = PROOF_WORKERS,
) -> dict[str, Any]:
    """Return the proof that each coding sigil's findings on `PROOF_TREE` equal with and without the selection."""
    sigils = coding_sigils()
    missing = [m.SIGIL.name for m in sigils if not hasattr(m, "CAN_RUN")]
    blocked = {m.SIGIL.name: discipline_fault(m.SIGIL) for m in sigils}
    sigils = [m for m in sigils if m.SIGIL.name not in missing and not blocked[m.SIGIL.name]]
    if control:
        sigils = [m for m in sigils if control in m.CAN_RUN]
    if only:
        sigils = [m for m in sigils if m.SIGIL.name == only]
    names = tuple(m.SIGIL.name for m in sigils)
    files = tracked_files(root, PROOF_TREE)
    done = _saved_rows(saved)
    with tempfile.TemporaryDirectory() as folder:
        used = keys_path
        if control:
            used = Path(folder, "partition_control.json")
            broken_copy(keys_path, control, used)
        todo = [f for f in files if f not in done]
        batch = workers * FILES_PER_WORKER
        for start in range(0, len(todo), batch):
            with ProcessPoolExecutor(
                max_workers=workers, initializer=_cache_tool_calls
            ) as pool:
                jobs = [
                    (f, pool.submit(prove_file, root, f, used, names))
                    for f in todo[start : start + batch]
                ]
                for file, job in jobs:
                    done[file] = job.result()
                    print(f"{len(done)}/{len(files)} {file}", file=sys.stderr, flush=True)
                    if saved is not None:
                        with saved.open("a", encoding="utf-8") as out:
                            out.write(json.dumps({"file": file, "rows": done[file]}) + "\n")
    rows = [row for file in files for row in done.get(file, [])]
    return {
        "tree": PROOF_TREE,
        "files": len(files),
        "control": control,
        "sigils without CAN_RUN": missing,
        "sigils refused by a discipline": {k: v for k, v in blocked.items() if v},
        "inputs": {
            size: len({row["input"] for row in rows if row.get("size") == size})
            for size in ("module", "scope")
        },
        "sigils": _summary(sigils, rows),
        "differ": [row for row in rows if "size" in row and not row["equal"]],
        "faults": [row for row in rows if "fault" in row],
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
    "an open key binds nothing, and a reach grounded on the tool's own scope fits every input, "
    "because that tool reads the project whatever the input",
    "selection": f"each coding sigil runs {SELECTION}",
    "proof": f"every .py file of {PROOF_TREE}/ as a module input, every def and class in it as a scope "
    "input, and the folder as the project input: no finding of a rule the input must carry is left "
    "out by the selection, read once from the archetype's own calls",
    "sigil proof": f"every tracked .py file of {PROOF_TREE}/ as a module input and every def and class "
    "in it as a scope input: each coding sigil whose tier 2 accepts the input gives the same findings "
    "with the selection as with every rule it can run",
    "keys": str(KEYS_FILE.relative_to(report.REPO_ROOT)).replace("\\", "/"),
}


def main(argv: list[str] | None = None) -> int:
    """Print `CARD`, one input's facts and rules, or a proof; exit 1 on a fault, a lost or a changed finding."""
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
        "--sigils",
        action="store_true",
        help=f"prove the selection at each coding sigil's own findings on {PROOF_TREE}/",
    )
    parser.add_argument(
        "--sigil", help="with --sigils, prove only the sigil named, such as CODE.TYPE"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=PROOF_WORKERS,
        help=f"with --sigils, the worker processes; default {PROOF_WORKERS}",
    )
    parser.add_argument(
        "--keys", type=Path, default=KEYS_FILE, help="the keys file to read"
    )
    parser.add_argument(
        "--findings",
        type=Path,
        help="a file the proof saves its tool findings, or the sigil proof its rows, to, "
        "or reads them from",
    )
    parser.add_argument(
        "--control",
        help="'<tool> <rule>': prove on a copy of the keys where it needs a module no input imports",
    )
    args = parser.parse_args(argv)
    if args.card or (args.input is None and not args.prove and not args.sigils):
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
    if args.sigils:
        proved = prove_sigils(
            root, args.keys, args.control, args.findings, args.sigil, args.workers
        )
        print(json.dumps(proved, indent=2))
        failed = proved["differ"] or proved["faults"] or proved["sigils without CAN_RUN"]
        return 1 if failed else 0
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
