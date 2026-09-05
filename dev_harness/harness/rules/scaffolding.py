"""scaffolding.py — universal scaffolding detector.

Reference specification (Diataxis: reference). Consumed by
coding_archetype, gui_archetype, docs_archetype. Introduced 2026-08-01
as v3.23.90 in response to operator's directive:

    "Scaffolding-detection should be universal to all archetypes as
    should hallucination-detection but slop probably only applied to
    coding."

Detectors — each fires as a normalized Finding matching the
ArchetypeReport schema in tools.harness.coding_archetype:

    S001 (medium) — FALLBACK-STRING-BEFORE-VERIFICATION
        String literals inside setText/print/log calls that read as
        "operation failed" reports (e.g., "returned no X",
        "no results", "check console log for details", "unavailable")
        when the surrounding function may not have actually verified
        the operation completed. Real-world example: v3.23.85 shipped
        a "Fetch YTD returned no trades" message wired to a wall-clock
        timer that fired BEFORE the async fetch finished — the string
        was scaffolding, not diagnosis.

    S002 (high) — WALL-CLOCK COMPLETION TIMER
        A function that calls ``run_coroutine_threadsafe`` AND
        constructs a QTimer paired with a ``*_done`` slot AND does NOT
        call ``add_done_callback`` on the future. Real-world example:
        v3.23.85. The 15s wall-clock timer fired regardless of whether
        the coroutine had finished, so the panel read empty state and
        reported failure while the async fetch was still running.

    S003 (high) — REFERENCED-BUT-NOT-INITIALIZED
        A class method references ``self._foo`` where ``_foo`` is not
        assigned in ``__init__``. Real-world example: v3.23.87. A
        rename purge missed one callsite; the AttributeError got
        swallowed by a Qt slot's implicit try/except and the button
        silently did nothing.

    S004 (low) — PLACEHOLDER TEXT
        Comments / docstrings / markdown text matching
        {TODO, FIXME, XXX, "not yet wired", "not yet implemented",
        "Phase B+", "will land in v"}. Low severity because these
        are informational; useful for gauging how much scaffolding
        lives in a file even when the surrounding logic is correct.

FALSIFICATION — this rule module is wrong if:
  (a) any of the four detectors fires on a fixture with a
      DIFFERENT root cause than described (misclassification);
  (b) any of the four fails to fire on a fixture that reproduces
      the described defect exactly (recall miss);
  (c) the S003 AST walker misses attributes assigned in
      __init__ via ``setattr(self, "_foo", ...)`` (known gap:
      only literal attribute stores are tracked);
  (d) the S002 detector fires on a legitimate pattern where the
      wall-clock timer is UI-only (e.g., blinking cursor) and no
      completion semantics are involved (false positive).

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import ast
import re
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


_FALLBACK_PHRASES = (
    "returned no ",
    "no trades",
    "no results",
    "no data",
    "check console log",
    "check the console",
    "check the log",
    "unavailable",
    "no such",
    "not wired",
    "not yet available",
    "load failed",
)

# String literals inside these callables are the ones we flag.
_STATUS_CALL_NAMES = {
    "setText",
    "setPlainText",
    "setStatusTip",
    "info",
    "warning",
    "error",
    "debug",
    "log",
    "print",
}


_PLACEHOLDER_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bTODO\b",
        r"\bFIXME\b",
        r"\bXXX\b",
        r"not yet wired",
        r"not yet implemented",
        r"Phase\s+[A-Z]\+",
        r"will land in v",
        r"pending Phase",
    )
)


def _find_wallclock_completion_functions(tree: ast.AST) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        has_schedule = False
        has_done_timer = False
        has_add_done_callback = False
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                # run_coroutine_threadsafe(...)
                if _call_name_ends_with(sub, "run_coroutine_threadsafe"):
                    has_schedule = True
                # QTimer setInterval + connect to *_done slot
                if _call_name_ends_with(sub, "connect"):
                    arg_names = [_slot_name(a) for a in sub.args]
                    if any(n and n.endswith("_done") for n in arg_names):
                        has_done_timer = True
                if _call_name_ends_with(sub, "add_done_callback"):
                    has_add_done_callback = True
        if has_schedule and has_done_timer and not has_add_done_callback:
            hits.append((node.lineno, node.name))
    return hits


def _call_name_ends_with(call: ast.Call, needle: str) -> bool:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr == needle
    if isinstance(call.func, ast.Name):
        return call.func.id == needle
    return False


def _slot_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


# Attrs a stdlib or Qt base supplies, counted as known on any class extending it.
_INHERITED_ATTRS_BY_BASE: dict[str, frozenset[str]] = {
    "NodeVisitor": frozenset({"visit", "generic_visit"}),
    "NodeTransformer": frozenset({"visit", "generic_visit"}),
    "TestCase": frozenset(
        {
            "assertEqual",
            "assertNotEqual",
            "assertTrue",
            "assertFalse",
            "assertIsNone",
            "assertIsNotNone",
            "assertIs",
            "assertIsNot",
            "assertIn",
            "assertNotIn",
            "assertRaises",
            "assertAlmostEqual",
            "assertGreater",
            "assertLess",
            "assertGreaterEqual",
            "assertLessEqual",
            "assertRegex",
            "assertNotRegex",
            "assertDictEqual",
            "assertListEqual",
            "assertTupleEqual",
            "assertSetEqual",
            "setUp",
            "tearDown",
            "addCleanup",
            "skipTest",
            "fail",
            "id",
            "shortDescription",
        }
    ),
    # The "*" sentinel suppresses S003 for the whole class, not one attr.
    "QWidget": frozenset({"*"}),
    "QDialog": frozenset({"*"}),
    "QMainWindow": frozenset({"*"}),
    "QSplashScreen": frozenset({"*"}),
    "QFrame": frozenset({"*"}),
    "QLabel": frozenset({"*"}),
    "QPushButton": frozenset({"*"}),
    "QAbstractItemView": frozenset({"*"}),
    "QTableWidget": frozenset({"*"}),
    "QTreeWidget": frozenset({"*"}),
    "QComboBox": frozenset({"*"}),
    "QLineEdit": frozenset({"*"}),
    "QTextEdit": frozenset({"*"}),
    "QPlainTextEdit": frozenset({"*"}),
    "QWizardPage": frozenset({"*"}),
    "QWizard": frozenset({"*"}),
    "QScrollArea": frozenset({"*"}),
    "QGroupBox": frozenset({"*"}),
    "QTabWidget": frozenset({"*"}),
    "QCheckBox": frozenset({"*"}),
    "QRadioButton": frozenset({"*"}),
    "QSpinBox": frozenset({"*"}),
    "QDoubleSpinBox": frozenset({"*"}),
    "QDateTimeEdit": frozenset({"*"}),
    "QProgressBar": frozenset({"*"}),
    "QDockWidget": frozenset({"*"}),
    "QToolBar": frozenset({"*"}),
    "QMenu": frozenset({"*"}),
    "QMenuBar": frozenset({"*"}),
    "QStatusBar": frozenset({"*"}),
    "QThread": frozenset({"*"}),
    "QTimer": frozenset({"*"}),
    "QObject": frozenset({"*"}),
}


def _collect_alias_map(tree: ast.AST) -> dict[str, str]:
    """v3.23.88 — build ``{local_name: real_name}`` from imports so
    the base-class allowlist works through aliases.

    Handles both ``from X import Foo as _F`` (asname) and
    ``import X.Foo as _F``. Walks the WHOLE tree (v3.23.88 bugfix)
    because main.py's boot script imports Qt aliases inside the
    boot function, and the SplashScreen class defined in that same
    scope uses them as bases.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    # For "import a.b.c as x", real name = "c"
                    aliases[alias.asname] = alias.name.rsplit(".", 1)[-1]
    return aliases


def _base_names(
    cls: ast.ClassDef,
    aliases: dict[str, str] | None = None,
) -> list[str]:
    """Return the leaf names of every base class expression, with
    aliases resolved via the file-scope import map."""
    aliases = aliases or {}
    names: list[str] = []
    for b in cls.bases:
        if isinstance(b, ast.Name):
            raw = b.id
            names.append(aliases.get(raw, raw))
        elif isinstance(b, ast.Attribute):
            names.append(b.attr)
    return names


def _class_skips_s003(
    cls: ast.ClassDef,
    aliases: dict[str, str] | None = None,
    local_classes: set[str] | None = None,
) -> bool:
    """True when S003 cannot be evaluated soundly for this class.

    Two suppression cases:

    1. A base maps to the '*' wildcard (Qt-family — MRO is huge and
       not statically resolvable).

    2. v3.24.10 — a base is UNRESOLVABLE: not ``object``, not on the
       allowlist, and not defined in this same file. We cannot see
       what that base assigns in its ``__init__``, so claiming an
       attribute is uninitialized would be a guess.

       This was a real false-positive source. ``ScrummingBot``
       extends ``BotContainer`` (declared in bot_container.py), which
       assigns ``self.bot_id`` / ``self.config`` / ``self._bus`` via
       ``super().__init__()``. Every subclass method touching those
       fired S003 — 10 fresh false positives from one edit on
       2026-08-02. An allowlist would need every base in the
       codebase; requiring a visible hierarchy is sound instead.

       Trade-off: recall drops for subclasses of out-of-file bases.
       That is the correct direction — a rule that cries wolf gets
       ignored, and S003's whole value is that a hit means something.
    """
    local = local_classes or set()
    for name in _base_names(cls, aliases):
        allowed = _INHERITED_ATTRS_BY_BASE.get(name)
        if allowed is not None and "*" in allowed:
            return True
        if allowed is not None:
            continue  # known base with a known attr set
        if name in local:
            continue  # defined here; we can read its __init__
        if name in (
            "object",
            "ABC",
            "Protocol",
            "Generic",
            "Enum",
            "IntEnum",
            "StrEnum",
            "Exception",
            "BaseException",
            "NamedTuple",
            "TypedDict",
        ):
            continue  # assigns nothing interesting
        return True  # unresolvable base -> cannot judge
    return False


def _inherited_attrs(
    cls: ast.ClassDef,
    aliases: dict[str, str] | None = None,
) -> set[str]:
    """Union of allowlisted attrs across the class's declared bases."""
    out: set[str] = set()
    for name in _base_names(cls, aliases):
        allowed = _INHERITED_ATTRS_BY_BASE.get(name)
        if allowed and "*" not in allowed:
            out.update(allowed)
    return out


def _collect_init_attrs(cls: ast.ClassDef) -> set[str]:
    """Names that are legitimately "on self" without needing an
    __init__ assignment. Union of:
      * methods (def foo / async def foo inside the class body)
      * class-level attributes (foo = ... at class scope)
      * attributes assigned in __init__ (self.foo = ...)
    """
    attrs: set[str] = set()
    # (a) methods + (b) class-level attributes
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            attrs.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    attrs.add(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            attrs.add(node.target.id)
    # (c) attributes assigned in __init__
    for node in cls.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "__init__":
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign):
                for tgt in sub.targets:
                    _add_self_attr(tgt, attrs)
            elif isinstance(sub, (ast.AugAssign, ast.AnnAssign)):
                tgt = getattr(sub, "target", None)
                if tgt is not None:
                    _add_self_attr(tgt, attrs)
    return attrs


def _add_self_attr(target: ast.AST, attrs: set[str]) -> None:
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    ):
        attrs.add(target.attr)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            _add_self_attr(elt, attrs)


def _find_uninitialized_attrs(
    cls: ast.ClassDef,
    aliases: dict[str, str] | None = None,
    local_classes: dict[str, ast.ClassDef] | None = None,
) -> list[tuple[int, str]]:
    locals_map = local_classes or {}
    if _class_skips_s003(cls, aliases, set(locals_map)):
        return []
    init_attrs = _collect_init_attrs(cls) | _inherited_attrs(cls, aliases)
    # The depth cap stops a cyclic base declaration hanging the walk.
    _pending = list(_base_names(cls, aliases))
    _seen: set[str] = set()
    _depth = 0
    while _pending and _depth < 10:
        _depth += 1
        _next: list[str] = []
        for bname in _pending:
            if bname in _seen or bname not in locals_map:
                continue
            _seen.add(bname)
            base_cls = locals_map[bname]
            init_attrs |= _collect_init_attrs(base_cls)
            _next.extend(_base_names(base_cls, aliases))
        _pending = _next
    hits: list[tuple[int, str]] = []
    seen_missing: set[tuple[int, str]] = set()
    for node in cls.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name == "__init__":
            continue
        # An attr stored by any method counts as known, not only by __init__.
        method_stores: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign):
                for tgt in sub.targets:
                    _add_self_attr(tgt, method_stores)
            elif isinstance(sub, (ast.AnnAssign, ast.AugAssign)):
                tgt = getattr(sub, "target", None)
                if tgt is not None:
                    _add_self_attr(tgt, method_stores)
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Attribute)
                and isinstance(sub.value, ast.Name)
                and sub.value.id == "self"
                and isinstance(sub.ctx, ast.Load)
            ):
                attr = sub.attr
                if attr.startswith("__"):  # dunder / mangled
                    continue
                if attr in init_attrs:
                    continue
                if attr in method_stores:
                    continue
                key = (sub.lineno, attr)
                if key in seen_missing:
                    continue
                seen_missing.add(key)
                hits.append((sub.lineno, attr))
    return hits


def _find_fallback_strings(tree: ast.AST) -> list[tuple[int, str, str]]:
    hits: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name not in _STATUS_CALL_NAMES:
            continue
        for arg in node.args:
            text = _extract_string(arg)
            if not text:
                continue
            low = text.lower()
            for phrase in _FALLBACK_PHRASES:
                if phrase in low:
                    hits.append((node.lineno, name, phrase))
                    break
    return hits


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _extract_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
        return "".join(parts) if parts else None
    return None


def _find_placeholder_text(source: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(source.splitlines(), start=1):
        for pat in _PLACEHOLDER_PATTERNS:
            m = pat.search(line)
            if m:
                hits.append((i, m.group(0)))
                break
    return hits


def scan(target: Path, source: str) -> list[Any]:
    """Return a list of Finding-shaped dicts. Callers convert to their
    own Finding class if needed.

    Returns [] when the file type is out of scope for all detectors.
    """
    suffix = target.suffix.lower()
    findings: list[Any] = []

    # AST-based detectors — Python only
    if suffix == ".py":
        try:
            tree = ast.parse(source, filename=str(target))
        except SyntaxError:
            tree = None
        if tree is not None:
            for line, name, phrase in _find_fallback_strings(tree):
                findings.append(
                    Finding(
                        tool="scaffolding",
                        severity="medium",
                        file=str(target),
                        line=line,
                        rule_id="S001",
                        message=(
                            f"fallback string '{phrase}' passed to "
                            f"{name}(...) — verify the operation was "
                            "actually attempted before reporting failure "
                            "(v3.23.85 defect pattern)."
                        ),
                    )
                )
            for line, fn in _find_wallclock_completion_functions(tree):
                findings.append(
                    Finding(
                        tool="scaffolding",
                        severity="high",
                        file=str(target),
                        line=line,
                        rule_id="S002",
                        message=(
                            f"function {fn!r} schedules an async task "
                            "via run_coroutine_threadsafe AND wires a "
                            "wall-clock QTimer to a *_done slot but "
                            "does not add_done_callback on the future. "
                            "The timer will fire before the coroutine "
                            "completes (v3.23.85 defect pattern)."
                        ),
                    )
                )
            aliases = _collect_alias_map(tree)
            local_classes: dict[str, ast.ClassDef] = {
                n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
            }
            for cls in ast.walk(tree):
                if not isinstance(cls, ast.ClassDef):
                    continue
                for line, attr in _find_uninitialized_attrs(
                    cls, aliases, local_classes
                ):
                    findings.append(
                        Finding(
                            tool="scaffolding",
                            severity="high",
                            file=str(target),
                            line=line,
                            rule_id="S003",
                            message=(
                                f"self.{attr} referenced in {cls.name} "
                                "method but not assigned in __init__. "
                                "AttributeError may be silently swallowed "
                                "by Qt slot try/except (v3.23.87 defect "
                                "pattern)."
                            ),
                        )
                    )

    # Text-scan detectors — Python + Markdown
    if suffix in (".py", ".md", ".markdown"):
        for line, token in _find_placeholder_text(source):
            findings.append(
                Finding(
                    tool="scaffolding",
                    severity="low",
                    file=str(target),
                    line=line,
                    rule_id="S004",
                    message=f"placeholder token '{token}' — scaffolding marker.",
                )
            )

    return findings


__all__ = ["Finding", "scan"]
