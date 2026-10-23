"""restore_set.py — a restore that stores a choice it never tests.

`SAVED_NAMES` and `RESTORE_TOKENS` decide that a mapping holds a saved
document, `names_a_choice` reads a key's last word against `CHOICE_WORDS`,
`UNREFUSING_CONVERSION` names the conversion `str`, and
`membership_tested_names` collects the `in` tests a function carries. `scan`
reports RS001 for a `str()` read of a choice key that no `in` test in the same
function reaches.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FALSIFICATION = (
    "This rule module is wrong if: (a) it fires on a read whose stored value "
    "an `in` test in the same function does reach, including a test written "
    "against a named constant and one written against a literal tuple, set, "
    "list or dict; (b) it fires on a mapping that holds a configuration, a "
    "keyword set or a request, because only SAVED_NAMES and a GENERIC_NAMES "
    "mapping inside a RESTORE_TOKENS function count as a saved document; "
    "(c) it fires on a key whose last word names a quantity, a timestamp or "
    "a free string; (d) it stays quiet on a `str()` read of a choice key in a "
    "restore that carries no `in` test at all. Known gaps: a read stored "
    "without `str()` is not seen, so a bare assignment of the same value is "
    "missed; a value tested by a chain of `==` comparisons is reported, "
    "because one equality is not a closed set; a value aliased to a second "
    "name before the `in` test is reported, because the tested name must "
    "match the assigned name exactly; and a read whose key is built at run "
    "time is invisible, because the key must be a string constant."
)


@dataclass
class Finding:
    """One `restore_set` result, shaped like every rule module's `Finding`."""

    tool: str
    severity: str
    file: str
    line: int
    rule_id: str
    message: str


#: Mapping names that hold a saved document wherever they appear.
SAVED_NAMES = frozenset(
    {
        "saved",
        "record",
        "stored",
        "persisted",
        "snapshot",
        "state",
        "document",
        "doc",
        "payload",
        "restored",
    }
)

#: Mapping names that hold a saved document only inside a restore function.
GENERIC_NAMES = frozenset({"data", "raw", "blob", "mapping", "entry"})

#: Function-name words naming a restore, which qualify a GENERIC_NAMES mapping.
RESTORE_TOKENS = frozenset(
    {
        "import",
        "restore",
        "load",
        "loads",
        "rehydrate",
        "deserialize",
        "record",
        "saved",
        "state",
        "snapshot",
    }
)

#: Key tail words naming a choice from a fixed set, never a quantity.
CHOICE_WORDS = frozenset(
    {
        "mode",
        "side",
        "kind",
        "state",
        "status",
        "type",
        "direction",
        "phase",
        "stage",
        "variant",
    }
)

#: The one conversion that refuses nothing: it succeeds on every JSON value.
UNREFUSING_CONVERSION = "str"

#: Method names that take a value out of a mapping by key.
MAPPING_READS = frozenset({"get", "pop"})

#: Comparison operators that read a value against a whole set at once.
SET_OPS = (ast.In, ast.NotIn)

_CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+")

#: Node kinds that open a new scope, so a finding names its own function.
_NESTED_SCOPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
)


def name_word_list(name: str) -> list[str]:
    """Return the lower-case words of `name`, in source order."""
    words: list[str] = []
    for part in name.replace("-", "_").split("_"):
        words.extend(w.lower() for w in _CAMEL.findall(part))
    return words


def name_words(name: str) -> set[str]:
    """Return the lower-case words of `name` as a set."""
    return set(name_word_list(name))


def dotted_name(node: ast.AST) -> str:
    """Return the dotted source name of `node`, empty when it has none."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def scope_nodes(scope: ast.AST) -> list[ast.AST]:
    """Return every node of `scope`, nested function and class bodies left out."""
    out: list[ast.AST] = []
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        out.append(node)
        if isinstance(node, _NESTED_SCOPES):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return out


def mapping_read(node: ast.AST) -> tuple[str, str] | None:
    """Return `(mapping, key)` when `node` reads a mapping by a constant key.

    `mapping_read` covers a subscript and a `MAPPING_READS` call, and the
    mapping it returns is the last segment of the holder's `dotted_name`.
    """
    holder: ast.AST | None = None
    key: ast.AST | None = None
    if isinstance(node, ast.Subscript):
        holder, key = node.value, node.slice
    elif (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in MAPPING_READS
        and node.args
    ):
        holder, key = node.func.value, node.args[0]
    if holder is None or key is None:
        return None
    if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
        return None
    name = dotted_name(holder)
    if not name:
        return None
    return (name.rsplit(".", 1)[-1], key.value)


def names_a_choice(key: str) -> bool:
    """True when the last word of `key` is one of `CHOICE_WORDS`."""
    words = name_word_list(key)
    return bool(words) and words[-1] in CHOICE_WORDS


def holds_saved_document(mapping: str, function: str) -> bool:
    """True when `mapping` read inside `function` holds a saved document."""
    words = name_words(mapping)
    if words & SAVED_NAMES:
        return True
    return bool(words & GENERIC_NAMES) and bool(name_words(function) & RESTORE_TOKENS)


def unrefusing_read(node: ast.AST, function: str) -> tuple[str, str] | None:
    """Return `(mapping, key)` when `node` is `str()` over a saved choice read."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
        return None
    if node.func.id != UNREFUSING_CONVERSION or len(node.args) != 1:
        return None
    read = mapping_read(node.args[0])
    if read is None:
        return None
    mapping, key = read
    if not names_a_choice(key):
        return None
    if not holds_saved_document(mapping, function):
        return None
    return (mapping, key)


def membership_tested_names(nodes: list[ast.AST]) -> set[str]:
    """Return every dotted name that a `SET_OPS` comparison in `nodes` tests."""
    tested: set[str] = set()
    for node in nodes:
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, SET_OPS) for op in node.ops):
            continue
        name = dotted_name(node.left)
        if name:
            tested.add(name)
    return tested


def assigned_names(nodes: list[ast.AST]) -> dict[int, str]:
    """Return `{id(value): target}` for each single-name assignment in `nodes`."""
    out: dict[int, str] = {}
    for node in nodes:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                out[id(node.value)] = target.id
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            out[id(node.value)] = node.target.id
    return out


def _finding(target: Path, node: ast.AST, message: str) -> Finding:
    """Return one RS001 `Finding` for `node` at `target`, severity high."""
    return Finding(
        tool="restore_set",
        severity="high",
        file=str(target),
        line=getattr(node, "lineno", 1),
        rule_id="RS001",
        message=message,
    )


def scan(target: Path, source: str) -> list[Any]:
    """Return every RS001 finding for `source`, empty on a non-`.py` target."""
    if target.suffix.lower() != ".py":
        return []
    try:
        tree = ast.parse(source, filename=str(target))
    except SyntaxError:
        return []
    findings: list[Any] = []
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        nodes = scope_nodes(scope)
        tested = membership_tested_names(nodes)
        assigned = assigned_names(nodes)
        for node in nodes:
            read = unrefusing_read(node, scope.name)
            if read is None:
                continue
            mapping, key = read
            holder = assigned.get(id(node))
            if holder is not None and holder in tested:
                continue
            findings.append(
                _finding(
                    target,
                    node,
                    f"{scope.name}() reads {key!r} out of the saved document "
                    f"{mapping!r} and stores it through str(), which refuses "
                    f"nothing. The key's last word names a choice from a fixed "
                    f"set, and no 'in' test in this function checks the value "
                    f"against one. Test the stored value against its legal set "
                    f"and fall back to a value the program can act on.",
                )
            )
    return findings


__all__ = ["FALSIFICATION", "Finding", "scan"]
