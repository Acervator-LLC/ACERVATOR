"""slop.py — coding-only slop detector.

Reference specification (Diataxis: reference). Consumed by
coding_archetype ONLY (per operator directive 2026-08-01: "slop
probably only applied to coding"). Introduced 2026-08-01 as v3.23.92
alongside the scaffolding + hallucination rules.

Detectors — each fires as a normalized Finding matching the
ArchetypeReport schema in tools.harness.coding_archetype:

    SL001 (medium) — DUPLICATE TRY/EXCEPT/PASS BLOCKS
        The same try/except/pass shape (exception type + body
        signature) appearing 3+ times in the file. Signals
        defensive-scaffolding buildup where the same "swallow
        anything" pattern got copy-pasted instead of factored into
        a helper. Common in Acervator's boot script.

    SL002 (low) — OVER-LONG FUNCTION
        A function definition spanning >200 lines. Rough proxy for
        over-engineered / monolithic responsibility. Not a bug per
        se — many trading loops legitimately need this — but a
        long-standing candidate for splitting.

    SL003 (low) — FILE TOO BIG
        Module spanning >3000 lines. Split candidate. Fires ONCE
        per file so the finding count stays bounded.

FALSIFICATION — this rule module is wrong if:
  (a) SL001 collapses two try/except blocks that differ in body
      but happen to have the same exception type (false positive
      on legitimate cross-cutting defensive layers);
  (b) SL002 misses a function that's split across cooperating
      inner functions — we don't attempt cross-function span
      analysis;
  (c) SL003 fires on a generated file (e.g., pydantic-generated
      schema) — no known-generated-file allowlist implemented.

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


# --------------------------------------------------------------------- #
# SL001 — duplicate try/except/pass                                     #
# --------------------------------------------------------------------- #

# Threshold: 3+ occurrences of the same (exception_type, body_shape)
# pair signals slop. 2 occurrences is normal (paired invariant).
_TRY_DUPE_THRESHOLD = 3


def _try_except_pass_shape(node: ast.Try) -> tuple[str, ...] | None:
    """Return a canonical (exc_type, body_signature) tuple if the
    try/except is a pure ``try: X except Y: pass`` — else None.

    Body signature is the AST type names of the try-body statements
    (e.g., ('Expr', 'Assign')) — this normalises whitespace + variable
    names + specific method arguments while distinguishing legitimately
    different flows.
    """
    if len(node.handlers) != 1:
        return None
    handler = node.handlers[0]
    if not (len(handler.body) == 1
            and isinstance(handler.body[0], ast.Pass)):
        return None
    # Exception type name
    exc_name = "Exception"
    if handler.type is not None:
        if isinstance(handler.type, ast.Name):
            exc_name = handler.type.id
        elif isinstance(handler.type, ast.Attribute):
            exc_name = handler.type.attr
    body_shape = tuple(type(s).__name__ for s in node.body)
    return (exc_name, *body_shape)


def _find_duplicate_try_except(
    tree: ast.AST,
) -> list[tuple[int, str, int]]:
    """Return (line, exc_name, count) for shapes that recur ≥ threshold."""
    by_shape: dict[tuple[str, ...], list[int]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        shape = _try_except_pass_shape(node)
        if shape is None:
            continue
        by_shape.setdefault(shape, []).append(node.lineno)
    hits: list[tuple[int, str, int]] = []
    for shape, lines in by_shape.items():
        if len(lines) >= _TRY_DUPE_THRESHOLD:
            # Emit ONE finding at the first occurrence to keep the
            # signal-to-noise ratio sane. The count is in the msg.
            first = min(lines)
            exc = shape[0]
            hits.append((first, exc, len(lines)))
    return hits


# --------------------------------------------------------------------- #
# SL002 — over-long function                                            #
# --------------------------------------------------------------------- #

_LONG_FUNC_THRESHOLD = 200


def _find_long_functions(tree: ast.AST) -> list[tuple[int, str, int]]:
    hits: list[tuple[int, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = getattr(node, "end_lineno", None)
        if end is None:
            continue
        span = end - node.lineno + 1
        if span > _LONG_FUNC_THRESHOLD:
            hits.append((node.lineno, node.name, span))
    return hits


# --------------------------------------------------------------------- #
# SL003 — file too big                                                  #
# --------------------------------------------------------------------- #

_BIG_FILE_THRESHOLD = 3000


def _file_too_big(source: str) -> int | None:
    lines = source.count("\n") + 1
    return lines if lines > _BIG_FILE_THRESHOLD else None


# --------------------------------------------------------------------- #
# Public entry — called by coding_archetype only                       #
# --------------------------------------------------------------------- #


def scan(target: Path, source: str) -> list[Any]:
    """Return a list of Finding-shaped objects. Returns [] for
    non-Python targets (slop is coding-only per operator directive)."""
    if target.suffix.lower() != ".py":
        return []
    findings: list[Any] = []
    try:
        tree = ast.parse(source, filename=str(target))
    except SyntaxError:
        return findings

    for line, exc, count in _find_duplicate_try_except(tree):
        findings.append(Finding(
            tool="slop", severity="medium",
            file=str(target), line=line, rule_id="SL001",
            message=(
                f"try/except/{exc} with pass body repeats {count}× "
                "in this file. Factor into a helper or use "
                "contextlib.suppress().")))

    for line, name, span in _find_long_functions(tree):
        findings.append(Finding(
            tool="slop", severity="low",
            file=str(target), line=line, rule_id="SL002",
            message=(
                f"function {name!r} spans {span} lines "
                f"(>{_LONG_FUNC_THRESHOLD}). Split candidate.")))

    big = _file_too_big(source)
    if big is not None:
        findings.append(Finding(
            tool="slop", severity="low",
            file=str(target), line=1, rule_id="SL003",
            message=(
                f"file spans {big} lines (>{_BIG_FILE_THRESHOLD}). "
                "Split candidate.")))

    return findings


__all__ = ["Finding", "scan"]
