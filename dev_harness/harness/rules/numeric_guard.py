"""numeric_guard.py — open numeric type guard detector.

Reference specification (Diataxis: reference). Consumed by
coding_archetype ONLY. Numeric admission is a code contract, not a
widget or a document concern, so gui_archetype and docs_archetype do
not call it.

Introduced 2026-08-10 under an explicit operator authorisation to add
one rule. The authorisation is limited to ADDING. No existing rule is
modified or weakened.

WHY THIS RULE EXISTS. `isinstance` admits subclasses. A guard written
as `isinstance(value, (int, float))` therefore admits `bool` and any
`float` subclass, and the value then reaches `float(value)` and is
booked. Four adversarial review rounds on one money path produced
eight distinct hostile input shapes, each closed one at a time. An
enumeration of bad inputs cannot close, because the set of subclasses
is unbounded. An exact type test closes it in one step.

Detectors — each fires as a normalized Finding matching the
ArchetypeReport schema in tools.harness.coding_archetype:

    NG001 (high) — OPEN NUMERIC TYPE GUARD ON A COERCED VALUE
        An `isinstance` test whose type argument is numeric-only
        (`int`, `float`, or both), which gates a return, a raise or
        an assignment, on a value that the same function also passes
        to `float()` at or after the guard. Recommend `type(x) is
        float` / `type(x) in (int, float)` instead.

WHAT IS DELIBERATELY NOT FLAGGED. Each exclusion is a false-positive
brake, chosen because a rule that cries wolf gets waived:

  * Any type argument that is not exactly `int`, `float` or both.
    `isinstance(x, bool)` is the correct way to REFUSE a flag.
    `(int, float, Decimal)` and `numbers.Number` are widened on
    purpose by their author.
  * An `isinstance` whose branch neither returns, raises nor assigns.
    A bare logging branch changes no state.
  * A value the function never passes to `float()`. Membership tests,
    dispatch tables and formatting choices are not amounts.
  * A function that already tests the same name with `type(x) is ...`
    or `type(x) in ...`. That IS the recommended fix, so the rule
    must clear once it lands.
  * Non-Python targets.

FALSIFICATION — this rule module is wrong if:
  (a) NG001 fires on a name whose `float()` call is on a branch that
      the guard cannot reach — line order is the only ordering test,
      and it does not model branches;
  (b) NG001 misses a guard where the coercion is `Decimal(x)` or a
      bare arithmetic operator instead of `float()` — only `float()`
      is treated as the coercion;
  (c) NG001 misses a guard whose value is a subscript or a call
      result — only plain names and dotted attributes are tracked;
  (d) NG001 misses a guard whose value is aliased before the
      coercion, as in `x = value` then `float(x)` — the guarded name
      and the coerced name must match exactly;
  (e) the exact-type suppression clears a function that tests
      `type(x)` for a DIFFERENT purpose than the guard;
  (f) NG001 fires on a file where `int` or `float` is shadowed by a
      local name — no shadowing analysis is done.

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Finding:
    tool: str
    severity: str
    file: str
    line: int
    rule_id: str
    message: str


# The only type names that make a guard "numeric-only". A tuple that
# holds anything else was widened deliberately and is left alone.
_NUMERIC_TYPE_NAMES = frozenset({"int", "float"})

# Statement kinds that make an `if` branch a GATE rather than a note.
_GATING_STATEMENTS = (
    ast.Return,
    ast.Raise,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
)

# Comparison operators that read as an exact type test.
_EXACT_TYPE_OPS = (ast.Is, ast.IsNot, ast.In, ast.NotIn, ast.Eq, ast.NotEq)

# Node kinds that open a new scope. Each is scanned on its own, so a
# finding names the function it lives in and not the whole module.
_NESTED_SCOPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
)


def _dotted(node: ast.AST) -> str | None:
    """Return ``a`` or ``a.b.c`` for a name or attribute chain, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else None
    return None


def _is_numeric_type_arg(node: ast.AST) -> bool:
    """True when the isinstance type argument is `int`, `float` or both."""
    if isinstance(node, ast.Name):
        return node.id in _NUMERIC_TYPE_NAMES
    if isinstance(node, ast.Tuple):
        if not node.elts:
            return False
        return all(
            isinstance(elt, ast.Name) and elt.id in _NUMERIC_TYPE_NAMES
            for elt in node.elts
        )
    return False


def _isinstance_calls_in_test(test: ast.AST) -> list[ast.Call]:
    """Return every isinstance call in an `if` test.

    Looks through `not` and through `and` / `or` chains so a negated
    guard reads the same as a positive one.
    """
    found: list[ast.Call] = []
    stack: list[ast.AST] = [test]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            stack.append(node.operand)
        elif isinstance(node, ast.BoolOp):
            stack.extend(node.values)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
        ):
            found.append(node)
    return found


def _own_nodes(scope: ast.AST) -> list[ast.AST]:
    """Return the nodes of one scope, without descending into nested scopes.

    A nested `def`, `class` or `lambda` is its own scope and is scanned
    separately. Keeping the scopes apart is what lets a finding name
    the function it lives in.
    """
    own: list[ast.AST] = []
    stack: list[ast.AST] = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        if isinstance(node, _NESTED_SCOPES):
            continue
        own.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return own


def _branch_gates(node: ast.If) -> bool:
    """True when either branch returns, raises or assigns."""
    return any(isinstance(sub, _GATING_STATEMENTS) for sub in _own_nodes(node))


def _float_coercions(nodes: list[ast.AST]) -> dict[str, list[int]]:
    """Map each name passed to `float()` to the lines where that happens."""
    coerced: dict[str, list[int]] = {}
    for sub in nodes:
        if not (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "float"
            and len(sub.args) == 1
        ):
            continue
        name = _dotted(sub.args[0])
        if name:
            coerced.setdefault(name, []).append(sub.lineno)
    return coerced


def _exact_type_tested(nodes: list[ast.AST]) -> set[str]:
    """Names the scope already tests with `type(x) is ...` or `type(x) in ...`."""
    tested: set[str] = set()
    for sub in nodes:
        if not isinstance(sub, ast.Compare):
            continue
        left = sub.left
        if not (
            isinstance(left, ast.Call)
            and isinstance(left.func, ast.Name)
            and left.func.id == "type"
            and len(left.args) == 1
        ):
            continue
        if not all(isinstance(op, _EXACT_TYPE_OPS) for op in sub.ops):
            continue
        name = _dotted(left.args[0])
        if name:
            tested.add(name)
    return tested


def _scan_scope(scope: ast.AST) -> list[tuple[int, str, str]]:
    """Return (line, guarded_name, scope_name) for every open guard here."""
    nodes = _own_nodes(scope)
    coerced = _float_coercions(nodes)
    if not coerced:
        return []
    exact = _exact_type_tested(nodes)
    scope_name = getattr(scope, "name", "<module>")
    hits: list[tuple[int, str, str]] = []
    for node in nodes:
        if not isinstance(node, ast.If):
            continue
        if not _branch_gates(node):
            continue
        for call in _isinstance_calls_in_test(node.test):
            if len(call.args) != 2:
                continue
            if not _is_numeric_type_arg(call.args[1]):
                continue
            name = _dotted(call.args[0])
            if not name or name in exact:
                continue
            later = [ln for ln in coerced.get(name, []) if ln >= call.lineno]
            if later:
                hits.append((call.lineno, name, scope_name))
    return hits


def scan(target: Path, source: str) -> list[Any]:
    """Return a list of Finding-shaped objects. Returns [] for non-Python."""
    if target.suffix.lower() != ".py":
        return []
    try:
        tree = ast.parse(source, filename=str(target))
    except SyntaxError:
        return []

    scopes: list[ast.AST] = [tree]
    scopes.extend(node for node in ast.walk(tree) if isinstance(node, _NESTED_SCOPES))

    seen: set[tuple[int, str]] = set()
    findings: list[Any] = []
    for scope in scopes:
        for line, name, scope_name in _scan_scope(scope):
            key = (line, name)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                Finding(
                    tool="numeric_guard",
                    severity="high",
                    file=str(target),
                    line=line,
                    rule_id="NG001",
                    message=(
                        f"isinstance guard on {name!r} in {scope_name!r} admits "
                        "subclasses, so bool and any float subclass pass it, and "
                        f"{name!r} is then coerced with float(). Use an exact "
                        f"test: type({name}) is float, or "
                        f"type({name}) in (int, float)."
                    ),
                )
            )
    return findings


__all__ = ["Finding", "scan"]
