"""`measure` names the `CONSTRUCTS` each ruff rule's published faulty finding sits on; `main` writes `SCOPE_FILE`.

The example, the ruff run over it and the finding's node come from `partition_measure`; `owners` adds the climb.
"""

import argparse
import ast
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .code_collection import _is_collection
from .code_flow import FLOW_NODES
from .code_import import IMPORT_NODES
from .code_loop import LOOP_NODES
from .code_variable import BINDING_NODES
from .construct_rules import SCOPE_FILE, TOOL
from .partition_measure import (
    KEYS_FILE,
    Example,
    MeasureFault,
    Ruff,
    parsed,
    path_to_statement,
    read_examples,
)
from .ruff_rules import ToolFault, rule_page

OWNED_SLOTS = frozenset(
    {
        "targets",
        "target",
        "optional_vars",
        "names",
        "body",
        "orelse",
        "finalbody",
        "handlers",
        "cases",
        "items",
    }
)
HEADERS = ((ast.For, "iter"), (ast.AsyncFor, "iter"), (ast.While, "test"))
HOLDERS = (ast.stmt, ast.withitem, ast.excepthandler)
BOUNDARY = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda, ast.Module)
TEXT_GROUND = "unparse"
SOURCE_KIND = "source"
IMPORT_OPEN = "the finding sits on an import statement"
NO_FINDING = "its published faulty example raises no finding of its own"
TEXT_READ = f"{KEYS_FILE.name}: it reads text the AST does not hold (ground: {TEXT_GROUND})"
NO_SOURCE = f"{KEYS_FILE.name}: it fires on {{kinds}} files, and a sigil reads a {SOURCE_KIND} .py file"
OUTSIDE = "the climb from its finding stops on {node}, inside no construct"
NO_FORMS = "ruff_rules.rule_page refuses it, so a FINDINGS row cannot carry both forms: {fault}"
CONSTRUCTS: dict[str, Callable[[ast.AST], bool]] = {
    "collection": lambda node: isinstance(node, ast.expr) and _is_collection(node),
    "flow": lambda node: isinstance(node, FLOW_NODES),
    "import": lambda node: isinstance(node, IMPORT_NODES),
    "loop": lambda node: isinstance(node, LOOP_NODES),
    "variable": lambda node: isinstance(node, BINDING_NODES),
}

CARD: dict[str, object] = {
    "house": "coding",
    "edition": 1,
    "owner": "coding",
    "constructs": sorted(CONSTRUCTS),
    "construct_nodes": "each sigil's own tier 2 test: code_collection._is_collection, "
    "code_flow.FLOW_NODES, code_import.IMPORT_NODES, code_loop.LOOP_NODES, "
    "code_variable.BINDING_NODES",
    "climb": "from the deepest node holding the finding, as partition_measure.path_to_statement "
    "finds it, through each parent to the first node a construct names; a statement, with item "
    "or except handler entered by a field outside " + ", ".join(sorted(OWNED_SLOTS)) + ", or a "
    "def, class, lambda or module reached first, holds the finding inside no construct; a for "
    "header and a while test belong to their loop",
    "keys": f"{KEYS_FILE.name}: a rule whose imports key opens on '{IMPORT_OPEN}' sits on the "
    f"import construct; a rule whose reach ground is {TEXT_GROUND}, or whose file kinds lack "
    f"{SOURCE_KIND}, sits on none; its preview flag carries over",
    "forms": "a rule on a construct whose page ruff_rules.rule_page cannot read carries no_forms",
    "source": "python -m ruff rule --all --output-format json, read by partition_measure.Ruff",
    "output": str(SCOPE_FILE.name),
    "command": "python -m dev_harness.sigils.construct_scope",
}


def _slot(parent: ast.AST, child: ast.AST) -> str:
    """Return the field of `parent` holding `child`, else an empty string."""
    for name, value in ast.iter_fields(parent):
        if value is child or (isinstance(value, list) and any(item is child for item in value)):
            return name
    return ""


def _chain(tree: ast.Module, start: tuple[int, int], end: tuple[int, int]) -> list[ast.AST]:
    """Return `path_to_statement` for the span, extended by each parent up to `tree`."""
    parents = {
        child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)
    }
    chain = path_to_statement(tree, start, end)
    while chain[-1] in parents:
        chain.append(parents[chain[-1]])
    return chain


def owners(chain: list[ast.AST]) -> tuple[frozenset[str], ast.AST]:
    """Return the `CONSTRUCTS` holding the first node of `chain`, and the node the climb stops on."""
    previous: ast.AST | None = None
    for node in chain:
        if previous is not None:
            slot = _slot(node, previous)
            header = any(isinstance(node, kind) and slot == field for kind, field in HEADERS)
            holder = isinstance(node, HOLDERS) and not isinstance(node, ast.Expr)
            if holder and not header and slot not in OWNED_SLOTS:
                return frozenset(), node
        found = frozenset(name for name, holds in CONSTRUCTS.items() if holds(node))
        if found or isinstance(node, BOUNDARY):
            return found, node
        previous = node
    return frozenset(), chain[-1]


def _row(spans: list[tuple[tuple[int, int], tuple[int, int]]], example: Example) -> dict[str, Any]:
    """Return the constructs `spans` climb to in `example`, each with the node and position it rests on."""
    tree = parsed(example.text)
    if tree is None:
        return {"none": "its published example does not parse as Python"}
    found: dict[str, str] = {}
    stops: list[str] = []
    for start, end in spans:
        names, node = owners(_chain(tree, start, end))
        at = f"{type(node).__name__}, from the finding at {start[0]}:{start[1] + 1}"
        for name in names:
            found.setdefault(name, at)
        stops.append(at)
    if found:
        return {"constructs": dict(sorted(found.items()))}
    return {"none": OUTSIDE.format(node=stops[0])}


def _keys() -> dict[str, dict[str, Any]]:
    """Return each `TOOL` rule's `KEYS_FILE` row, by rule code."""
    rows = json.loads(KEYS_FILE.read_text(encoding="utf-8"))["rules"]
    prefix = f"{TOOL} "
    return {name.removeprefix(prefix): row for name, row in rows.items() if name.startswith(prefix)}


def _forms_fault(code: str) -> str | None:
    """Return `NO_FORMS` for `code` when `rule_page` raises `ToolFault`, else None."""
    try:
        rule_page(code)
    except ToolFault as exc:
        return NO_FORMS.format(fault=exc)
    return None


def measure(sources: Path) -> dict[str, dict[str, Any]]:
    """Return each `KEYS_FILE` ruff rule's constructs, or the text naming why it sits on none."""
    keys = _keys()
    preview = frozenset(code for code, row in keys.items() if row.get("preview"))
    engine = Ruff(preview)
    examples = {example.stem: example for example in engine.examples(sources)}
    readings = read_examples(engine, list(examples.values()))
    rules: dict[str, dict[str, Any]] = {}
    for code, key in sorted(keys.items()):
        reading = readings.get(code)
        kinds = key.get("file", {}).get("value", [SOURCE_KIND])
        if key.get("reach", {}).get("ground") == TEXT_GROUND:
            row: dict[str, Any] = {"none": TEXT_READ}
        elif SOURCE_KIND not in kinds:
            row = {"none": NO_SOURCE.format(kinds=", ".join(kinds) or "no")}
        elif reading is None or not reading.hits:
            row = {"none": NO_FINDING}
        else:
            stem, spans = next(iter(reading.hits.items()))
            row = _row(spans, examples[stem])
        if str(key.get("imports", {}).get("open", "")).startswith(IMPORT_OPEN):
            row.pop("none", None)
            row.setdefault("constructs", {})["import"] = f"{KEYS_FILE.name}: {IMPORT_OPEN}"
            row["constructs"] = dict(sorted(row["constructs"].items()))
        fault = _forms_fault(code) if "constructs" in row else None
        if fault:
            row["no_forms"] = fault
        if code in preview:
            row["preview"] = True
        rules[code] = row
    return rules


def write(rules: dict[str, dict[str, Any]], target: Path = SCOPE_FILE) -> None:
    """Write `CARD` and `rules` to `target`, one rule per line, sorted by code."""
    rows = [f"  {json.dumps(code)}: {json.dumps(rules[code], sort_keys=True)}" for code in sorted(rules)]
    body = '{\n "card": ' + json.dumps(CARD, sort_keys=True) + ',\n "rules": {\n'
    target.write_text(body + ",\n".join(rows) + "\n }\n}\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    """Print `CARD` with --card, else measure every ruff rule's constructs and write `SCOPE_FILE`."""
    parser = argparse.ArgumentParser(description="Measure each ruff rule's construct scope.")
    parser.add_argument("--card", action="store_true", help="print the card as JSON")
    args = parser.parse_args(argv)
    if args.card:
        print(json.dumps(CARD, indent=2))
        return 0
    try:
        with tempfile.TemporaryDirectory() as folder:
            rules = measure(Path(folder))
    except (MeasureFault, ToolFault) as exc:
        print(f"not measured: {exc}", file=sys.stderr)
        return 1
    write(rules)
    counts = {
        name: sum(name in row.get("constructs", {}) for row in rules.values())
        for name in sorted(CONSTRUCTS)
    }
    no_forms = sorted(code for code, row in rules.items() if "no_forms" in row)
    print(json.dumps({"rules": len(rules), "constructs": counts, "no_forms": no_forms, "file": CARD["output"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
