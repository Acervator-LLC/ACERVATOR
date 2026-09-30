"""GUIArchetype — screen-quality archetype for PySide6 and React screens.

JavaScript:
  A `.js` target is graded by `js_screen`, published as the `gui-js`
  tool. It resolves the `element(...)` calls a renderer module makes and
  reports an unlabelled control (GUIJS001), an inert control (GUIJS002),
  a colour literal the design tokens already serve (GUIJS003) and
  absolute positioning (GUIJS004). ruff and bandit read Python only and
  do not run on a `.js` target; a module `js_screen.tokenize` cannot
  finish leaves `scanned` False. `eslint` runs beside `js_screen` on the
  same target, configured by `eslint.config.mjs` at the repo root.

CSS and HTML:
  A `.css` target is graded by `stylelint` and a `.html` target by
  `html-validate`, each configured by its own file at the repo root --
  `.stylelintrc.json` and `.htmlvalidate.json`. Both are npm packages
  installed under `node_modules/`; an absent package reports `missing`
  and leaves `scanned` False.

Design (in one paragraph):
  The archetype does two things: (1) STATIC AST analysis of PySide6
  widget/dialog code for accessibility + structure gotchas that
  no general-purpose linter catches (no accessibleName on interactive
  widgets, absolute pixel positioning instead of QLayout, child
  widgets constructed without a parent, missing docstrings on widget
  classes); (2) delegates to ruff + bandit for style + security on
  the same files, so we don't re-implement what those tools already
  do well.

  Why STATIC not runtime: automated WCAG-compliance testing of Qt
  desktop widgets is genuinely a gap in 2026 tooling. pytest-qt can
  drive widgets but does not check accessibility semantics itself.
  Rather than fabricate a runtime a11y tool, we make deterministic
  claims about STATIC properties (setAccessibleName was called on
  every button/lineedit; layout was used; children have parents),
  then defer runtime a11y verification to manual VoiceOver/Narrator.

  FALSIFICATION: this design is wrong if (a) the AST parser fails
  on syntactically valid Qt code that uses idioms it doesn't
  recognize (dynamic widget creation, factory patterns, decorators
  that hide widget classes), (b) accessibility properties are set
  via property assignment (widget.accessibleName = "X") rather than
  the setter (widget.setAccessibleName("X")) — the checker looks
  for the setter, (c) tests against the fixture pair fail to
  distinguish good from bad.
"""

# ruff: noqa: S603
from __future__ import annotations

import ast
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

from dev_harness.harness import js_screen, web_analyzers
from dev_harness.harness.coding_archetype import detect_language
from dev_harness.harness.report import (
    REPO_ROOT,
    ArchetypeReport,
    Finding,
    cli_exit,
    refuse_silent_failure,
    scan_rule_modules,
)

__all__ = [
    "HANDLED_LANGUAGES",
    "ArchetypeReport",
    "Finding",
    "GUIArchetype",
    "main",
]

# The languages this archetype carries a screen analyzer for. `ruff` and
# `bandit` read Python only, so a JavaScript target runs `gui-js` and
# `eslint`, a style sheet `stylelint`, and a page `html-validate`.
HANDLED_LANGUAGES: frozenset[str] = frozenset({"python", "javascript", "css", "html"})

# scaffolding and hallucination read any text; every other rule module
# parses Python.
_TEXT_RULE_MODULES: tuple[tuple[str, str], ...] = (
    ("scaffolding", "dev_harness.harness.rules.scaffolding"),
    ("hallucination", "dev_harness.harness.rules.hallucination"),
)


_QT_WIDGET_BASES: set[str] = {
    "QWidget",
    "QDialog",
    "QMainWindow",
    "QFrame",
    "QPushButton",
    "QLineEdit",
    "QTextEdit",
    "QLabel",
    "QCheckBox",
    "QRadioButton",
    "QComboBox",
    "QSpinBox",
    "QDoubleSpinBox",
    "QSlider",
    "QProgressBar",
    "QToolButton",
    "QTabWidget",
    "QListWidget",
    "QTreeWidget",
    "QTableWidget",
    "QGroupBox",
    "QScrollArea",
    "QDockWidget",
    # QObject and QThread are excluded: they paint nothing, so GUI001 and
    # GUI003 say nothing about them.
    "QWizard",
    "QWizardPage",
    "QTableView",
    "QListView",
    "QTreeView",
    "QColumnView",
    "QPlainTextEdit",
    "QTextBrowser",
    "QStackedWidget",
    "QSplitter",
    "QScrollBar",
    "QMenu",
    "QMenuBar",
    "QToolBar",
    "QStatusBar",
    "QAbstractButton",
    "QAbstractItemView",
    "QAbstractScrollArea",
    "QAbstractSpinBox",
    "QAbstractSlider",
}

_INTERACTIVE_QT_WIDGETS: set[str] = {
    "QPushButton",
    "QToolButton",
    "QLineEdit",
    "QTextEdit",
    "QCheckBox",
    "QRadioButton",
    "QComboBox",
    "QSpinBox",
    "QDoubleSpinBox",
    "QSlider",
    "QListWidget",
    "QTreeWidget",
    "QTableWidget",
}

_ACCESSIBLE_SETTER_METHODS: set[str] = {
    "setAccessibleName",
    "setAccessibleDescription",
    "setToolTip",
    "setWhatsThis",
}

# Signals a well-formed interactive widget typically has connected somewhere.
# When we see `self._foo.<one of these>.connect(...)`, we mark `_foo` as wired.
_INTERACTIVE_SIGNALS: set[str] = {
    "clicked",
    "pressed",
    "released",  # QPushButton / QToolButton
    "triggered",  # QAction / QToolButton menu
    "returnPressed",
    "editingFinished",  # QLineEdit
    "textChanged",
    "textEdited",  # QLineEdit / QTextEdit
    "valueChanged",
    "sliderMoved",  # QSpinBox / QSlider
    "currentIndexChanged",
    "currentTextChanged",  # QComboBox
    "activated",
    "highlighted",  # QComboBox
    "stateChanged",
    "toggled",  # QCheckBox / QRadioButton
    "itemClicked",
    "itemActivated",  # QListWidget / QTreeWidget
    "itemSelectionChanged",
}


def _class_bases(node: ast.ClassDef) -> list[str]:
    names: list[str] = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


def _is_qt_widget_class(
    node: ast.ClassDef, local_widgets: frozenset[str] = frozenset()
) -> bool:
    """True when this class is a Qt widget, directly or via a sibling.

    `local_widgets` holds the names of classes defined in the SAME module
    that already resolve to a Qt widget base (see
    `_local_widget_classes`). Passing it is optional so the default
    behaviour is byte-identical to the direct-base-only check that
    existed before.
    """
    return any(b in _QT_WIDGET_BASES or b in local_widgets for b in _class_bases(node))


def _local_widget_classes(tree: ast.AST) -> frozenset[str]:
    """Names of classes in this module that REACH a Qt widget base.

    v3.24.xx — CHANGE 2, second half. A project-local intermediate
    class hid every subclass under it. MEASURED in
    src/gui/competition_tab.py: `_Section(QGroupBox)` was graded, and
    its four subclasses -- `_IdentityPanel`, `_WalletPanel`,
    `_SupplyPanel`, `_LeaderboardPanel` -- were not graded by any GUI
    rule, because the analyzer only ever looked at a DIRECT base name.

    Resolution is a fixed-point closure over same-module classes only:
    a name is a widget once any of its bases is a known Qt base or a
    name already in the set. `seen` grows monotonically and is bounded
    by the class count, so the loop terminates; an inheritance cycle
    (impossible in Python, but cheap to survive) simply never adds.

    Cross-module bases are NOT resolved. That is a deliberate limit,
    not an oversight: it would need an import graph, and getting it
    wrong silently changes what is graded. Same-file resolution is
    decidable from the one AST already in hand.
    """
    bases_by_name: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases_by_name[node.name] = _class_bases(node)

    seen: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, bases in bases_by_name.items():
            if name in seen:
                continue
            if any(b in _QT_WIDGET_BASES or b in seen for b in bases):
                seen.add(name)
                changed = True
    return frozenset(seen)


class _GUIAnalyzer(ast.NodeVisitor):
    """AST walker that collects GUI-specific findings."""

    def __init__(
        self, source_path: str, local_widgets: frozenset[str] = frozenset()
    ) -> None:
        self.source_path = source_path
        self._local_widgets = local_widgets
        self.findings: list[Finding] = []
        self._current_class: ast.ClassDef | None = None
        # per-widget-class state
        self._class_calls_accessible: bool = False
        self._class_has_docstring: bool = False
        self._class_uses_layout: bool = False
        self._class_uses_setgeometry: list[int] = []
        self._interactive_instantiations_without_parent: list[tuple[str, int]] = []
        self._interactive_instantiations_with_parent: list[tuple[str, int]] = []
        # GUI005 signal-wiring tracking
        self._interactive_instances: dict[str, tuple[str, int]] = (
            {}
        )  # attr -> (widget_class, line)
        self._wired_instances: set[str] = (
            set()
        )  # attrs seen with .<signal>.connect(...)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if not _is_qt_widget_class(node, self._local_widgets):
            # Not a Qt widget class; still recurse to find nested classes
            self.generic_visit(node)
            return

        # entering a widget class - reset per-class state
        prev = (
            self._current_class,
            self._class_calls_accessible,
            self._class_has_docstring,
            self._class_uses_layout,
            self._class_uses_setgeometry,
            self._interactive_instantiations_without_parent,
            self._interactive_instantiations_with_parent,
            self._interactive_instances,
            self._wired_instances,
        )
        self._current_class = node
        self._class_calls_accessible = False
        self._class_has_docstring = ast.get_docstring(node) is not None
        self._class_uses_layout = False
        self._class_uses_setgeometry = []
        self._interactive_instantiations_without_parent = []
        self._interactive_instantiations_with_parent = []
        self._interactive_instances = {}
        self._wired_instances = set()

        self.generic_visit(node)

        # emit findings for this class
        cls_name = node.name
        line = node.lineno
        base_list = _class_bases(node)
        is_interactive_widget = any(
            b in _INTERACTIVE_QT_WIDGETS
            or b in _QT_WIDGET_BASES
            or b in self._local_widgets
            for b in base_list
        )

        if is_interactive_widget and not self._class_calls_accessible:
            self.findings.append(
                Finding(
                    tool="gui-static",
                    severity="high",
                    file=self.source_path,
                    line=line,
                    rule_id="GUI001",
                    message=(
                        f"Qt widget class {cls_name!r} does not call any of "
                        f"{sorted(_ACCESSIBLE_SETTER_METHODS)} on its widgets; "
                        "accessibility APIs (screen readers, keyboard navigation) "
                        "have no anchor to announce."
                    ),
                )
            )

        if not self._class_has_docstring:
            self.findings.append(
                Finding(
                    tool="gui-static",
                    severity="medium",
                    file=self.source_path,
                    line=line,
                    rule_id="GUI002",
                    message=f"Qt widget class {cls_name!r} has no docstring.",
                )
            )

        if self._class_uses_setgeometry and not self._class_uses_layout:
            for setg_line in self._class_uses_setgeometry:
                self.findings.append(
                    Finding(
                        tool="gui-static",
                        severity="high",
                        file=self.source_path,
                        line=setg_line,
                        rule_id="GUI003",
                        message=(
                            "setGeometry used without any QLayout — the widget "
                            "will not respond to resize / high-DPI / accessibility "
                            "scaling. Use QVBoxLayout / QHBoxLayout / QGridLayout."
                        ),
                    )
                )

        for widget_name, w_line in self._interactive_instantiations_without_parent:
            self.findings.append(
                Finding(
                    tool="gui-static",
                    severity="medium",
                    file=self.source_path,
                    line=w_line,
                    rule_id="GUI004",
                    message=(
                        f"Interactive widget {widget_name}(...) instantiated without "
                        "a parent argument; risks orphaned widget lifetime and "
                        "layout ambiguity."
                    ),
                )
            )

        # GUI005 — signal wiring. Any interactive instance (self._foo = QPushButton(...))
        # that never appears as `self._foo.<signal>.connect(...)` is inert.
        for attr, (widget_class, w_line) in self._interactive_instances.items():
            if attr not in self._wired_instances:
                self.findings.append(
                    Finding(
                        tool="gui-static",
                        severity="medium",
                        file=self.source_path,
                        line=w_line,
                        rule_id="GUI005",
                        message=(
                            f"Interactive widget self.{attr} ({widget_class}) has no "
                            f".<signal>.connect(...) anywhere in {cls_name!r}; widget "
                            "is functionally inert."
                        ),
                    )
                )

        # restore parent state
        (
            self._current_class,
            self._class_calls_accessible,
            self._class_has_docstring,
            self._class_uses_layout,
            self._class_uses_setgeometry,
            self._interactive_instantiations_without_parent,
            self._interactive_instantiations_with_parent,
            self._interactive_instances,
            self._wired_instances,
        ) = prev

    def visit_Assign(self, node: ast.Assign) -> None:
        """Track `self._foo = QPushButton(...)` for GUI005 wiring check."""
        if self._current_class is not None and len(node.targets) == 1:
            tgt = node.targets[0]
            if (
                isinstance(tgt, ast.Attribute)
                and isinstance(tgt.value, ast.Name)
                and tgt.value.id == "self"
                and isinstance(node.value, ast.Call)
            ):
                v = node.value.func
                callee = (
                    v.id
                    if isinstance(v, ast.Name)
                    else (v.attr if isinstance(v, ast.Attribute) else None)
                )
                if callee in _INTERACTIVE_QT_WIDGETS:
                    self._interactive_instances[tgt.attr] = (callee, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # accessible setter calls: <expr>.setAccessibleName(...)
        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method in _ACCESSIBLE_SETTER_METHODS:
                self._class_calls_accessible = True
            if method == "setLayout":
                self._class_uses_layout = True
            if method == "setGeometry":
                self._class_uses_setgeometry.append(node.lineno)
            # GUI005 wiring: `self._foo.<signal>.connect(...)`
            if (
                method == "connect"
                and isinstance(node.func.value, ast.Attribute)
                and node.func.value.attr in _INTERACTIVE_SIGNALS
            ):
                # walk down to `self.<attr>`
                receiver = node.func.value.value
                if (
                    isinstance(receiver, ast.Attribute)
                    and isinstance(receiver.value, ast.Name)
                    and receiver.value.id == "self"
                ):
                    self._wired_instances.add(receiver.attr)

        # widget instantiation: QPushButton(...) or QLineEdit(...)
        callee = None
        if isinstance(node.func, ast.Name):
            callee = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee = node.func.attr
        if callee in _INTERACTIVE_QT_WIDGETS:
            # Heuristic: does it have a parent argument?
            has_parent = bool(node.args) or any(
                kw.arg == "parent" for kw in node.keywords
            )
            entry = (callee, node.lineno)
            if has_parent:
                self._interactive_instantiations_with_parent.append(entry)
            else:
                self._interactive_instantiations_without_parent.append(entry)

        # constructor with layout: layout = QVBoxLayout() etc — also counts as layout usage
        if callee in (
            "QVBoxLayout",
            "QHBoxLayout",
            "QGridLayout",
            "QFormLayout",
            "QStackedLayout",
        ):
            self._class_uses_layout = True

        self.generic_visit(node)


# Qt getters that report what a widget was told to paint, not what it
# painted. Only calls match, so a local named `palette` is not a read.
_MODEL_COLOUR_READS: frozenset[str] = frozenset(
    {
        "background",
        "foreground",
        "brush",
        "palette",
        "styleSheet",
        "backgroundBrush",
        "foregroundBrush",
        "backgroundColor",
        "textColor",
        "textBackgroundColor",
        "penColor",
        "brushColor",
    }
)

# Any one of these in a test function disarms GUI006 for that function.
# Matched as a call target, an attribute, or a bare name.
_PIXEL_CONSTRUCTS: frozenset[str] = frozenset(
    {
        "grab",
        "grabWidget",
        "grabWindow",
        "render",
        "toImage",
        "pixelColor",
        "pixel",
        "QPixmap",
        "QImage",
        "QPainter",
        # tests/qt_pixel.py — the helper shipped with this change
        "render_widget",
        "sample_pixel",
        "sample_pixels",
        "assert_pixel_colour",
        "assert_pixel_color",
        "pixel_at",
    }
)


def _is_test_path(path: Path) -> bool:
    """True for a pytest module, by the same shape coding_archetype uses."""
    name = path.name
    return (
        name.startswith("test_") or name.endswith("_test.py") or "tests" in path.parts
    )


def _has_model_colour_read(node: ast.AST) -> bool:
    """True when a subtree CALLS a live-object model colour getter."""
    for n in ast.walk(node):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in _MODEL_COLOUR_READS
        ):
            return True
    return False


def _mentions_pixel_construct(node: ast.AST) -> bool:
    """True when a subtree names any rendered-pixel construct."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            if n.func.id in _PIXEL_CONSTRUCTS:
                return True
        elif isinstance(n, ast.Attribute):
            if n.attr in _PIXEL_CONSTRUCTS:
                return True
        elif isinstance(n, ast.Name) and n.id in _PIXEL_CONSTRUCTS:
            return True
    return False


def _names_in(node: ast.AST) -> set[str]:
    """Every bare name referenced in a subtree."""
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _tainted_locals(fn: ast.AST) -> set[str]:
    """Local names in `fn` that carry a live-object model colour value.

    Two bindings are resolved, because both appear in the real
    population: a nested helper whose body does the read
    (`def _col(row): return lst.item(row, C).foreground().color().name()`
    in tests/test_bot_swarm_list.py) and a plain assignment whose
    right-hand side does the read. Without this the four asserts in
    `test_outflow_pct_color_ramp` read only as hex literals and the
    rule would miss the exact shape it exists for.
    """
    tainted: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if n is not fn and _has_model_colour_read(n):
                tainted.add(n.name)
        elif isinstance(n, (ast.Assign, ast.AnnAssign)):
            value = n.value
            if value is None or not _has_model_colour_read(value):
                continue
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                for sub in ast.walk(t):
                    if isinstance(sub, ast.Name):
                        tainted.add(sub.id)
    return tainted


_SEGMENT_EDGES = ("top", "right", "bottom", "left")
_SEGMENT_CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")


_SEGMENT_DEFS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _segment_docstring_node(node: ast.AST) -> object:
    """The ``Constant`` node holding ``node``'s docstring, or None.

    Identity, never the cleaned text: ``ast.get_docstring`` re-indents, so a
    value comparison keeps the docstring in the literals a rule reads.
    """
    body = getattr(node, "body", None)
    if not body or not isinstance(body[0], ast.Expr):
        return None
    first = body[0].value
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first
    return None


def _segment_strings(node: ast.AST) -> list[str]:
    """Every string literal in ``node`` that is not its own docstring."""
    doc = _segment_docstring_node(node)
    found = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            if sub is doc:
                continue
            found.append(sub.value)
    return found


def _segment_writes_box(said: list[str]) -> bool:
    """Whether these literals declare a segment's own border box.

    A function that only tints a border colour is styling, not the box, so it
    is left to whichever function writes ``border:`` or ``border-radius``.
    """
    return any("border-radius" in one or "border: " in one for one in said)


def _segment_subjects(tree: ast.AST) -> list[ast.AST]:
    """Every function that names a segment and writes its own border box."""
    subjects = []
    for node in ast.walk(tree):
        if not isinstance(node, _SEGMENT_DEFS):
            continue
        doc = (ast.get_docstring(node) or "").lower()
        if "segment" not in node.name.lower() and "segment" not in doc:
            continue
        if _segment_writes_box(_segment_strings(node)):
            subjects.append(node)
    return subjects


def _segment_gap_faults(path: Path, tree: ast.AST) -> list[Finding]:
    """Every module-level spacing or gap constant a segmented group must keep at zero."""
    faults = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            name = target.id
            if not name.endswith("_PX"):
                continue
            if "SPACING" not in name and "GAP" not in name:
                continue
            value = node.value
            if isinstance(value, ast.Constant) and value.value == 0:
                continue
            faults.append(
                Finding(
                    tool="gui-static",
                    severity="high",
                    file=str(path),
                    line=node.lineno,
                    rule_id="GUI007",
                    message=(
                        f"{name} is not zero in a module that styles a segmented "
                        "group; a gap between two segments draws two borders where "
                        "the group must draw one. Set it to 0."
                    ),
                )
            )
    return faults


def _scan_segmented_group_skin(path: Path, tree: ast.AST) -> list[Finding]:
    """GUI007 — a segmented group must share its edges and round only its outer corners.

    A group whose segments each carry a full border, or each round more than
    one corner, or that keeps a non-zero gap between segments, is refused.
    """
    subjects = _segment_subjects(tree)
    if not subjects:
        return []
    findings: list[Finding] = []
    for node in subjects:
        said = _segment_strings(node)
        joined = " ".join(said)
        shared = any(f"border-{edge}: none" in joined for edge in _SEGMENT_EDGES)
        if not shared:
            findings.append(
                Finding(
                    tool="gui-static",
                    severity="high",
                    file=str(path),
                    line=node.lineno,
                    rule_id="GUI007",
                    message=(
                        f"{node.name} styles a segmented group and suppresses no "
                        "shared edge, so every segment carries a full border and "
                        "two lines draw between neighbours. Drop the shared edge "
                        "with border-<edge>: none."
                    ),
                )
            )
        for branch in ast.walk(node):
            if not isinstance(branch, ast.If):
                continue
            rounded = set()
            for sub in branch.body:
                for one in _segment_strings(sub):
                    for corner in _SEGMENT_CORNERS:
                        if f"border-{corner}-radius" in one:
                            rounded.add(corner)
            if len(rounded) > 1:
                findings.append(
                    Finding(
                        tool="gui-static",
                        severity="high",
                        file=str(path),
                        line=branch.lineno,
                        rule_id="GUI007",
                        message=(
                            f"{node.name} rounds {sorted(rounded)} in one branch, so "
                            "that segment rounds more than one corner and the group "
                            "is a strip with two rounded ends, not a square whose "
                            "outer corners each belong to one segment."
                        ),
                    )
                )
    findings.extend(_segment_gap_faults(path, tree))
    return findings


_STRETCH_SUFFIX = "_STRETCH"
_ORDER_SUFFIX = "_ORDER"


def _whole_number_lists(tree: ast.AST, suffix: str) -> dict:
    """Each module-level list of whole numbers whose name ends in ``suffix``."""
    found = {}
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or not target.id.endswith(suffix):
                continue
            if not isinstance(node.value, (ast.List, ast.Tuple)):
                continue
            held = [
                one.value
                for one in node.value.elts
                if isinstance(one, ast.Constant) and isinstance(one.value, int)
            ]
            if len(held) == len(node.value.elts) and held:
                found[target.id[: -len(suffix)]] = (node.lineno, target.id, held)
    return found


def _name_lists(tree: ast.AST, suffix: str) -> dict:
    """Each module-level list of plain names whose name ends in ``suffix``."""
    found = {}
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or not target.id.endswith(suffix):
                continue
            if not isinstance(node.value, (ast.List, ast.Tuple)):
                continue
            held = [
                one.value
                for one in node.value.elts
                if isinstance(one, ast.Constant) and isinstance(one.value, str)
            ]
            if len(held) == len(node.value.elts) and held:
                found[target.id[: -len(suffix)]] = held
    return found


def _scan_row_spare_width(path: Path, tree: ast.AST) -> list[Finding]:
    """GUI008 — a row's spare width is shared by its slots, never parked on one.

    A named `*_STRETCH` list of more than one slot that carries exactly one
    non-zero share is refused: that slot holds every spare pixel and every other
    slot falls to its floor.
    """
    shares = _whole_number_lists(tree, _STRETCH_SUFFIX)
    slots_by_prefix = _name_lists(tree, _ORDER_SUFFIX)
    findings: list[Finding] = []
    for source, (line, name, held) in shares.items():
        if len(held) < 2:
            continue
        sharing = [at for at, share in enumerate(held) if share > 0]
        if len(sharing) != 1:
            continue
        at = sharing[0]
        names = slots_by_prefix.get(source, [])
        slot = repr(names[at]) if at < len(names) else f"index {at}"
        findings.append(
            Finding(
                tool="gui-static",
                severity="high",
                file=str(path),
                line=line,
                rule_id="GUI008",
                message=(
                    f"{name} is {held}, so slot {slot} is the only one carrying a "
                    f"share of the row's spare width. Every other slot falls to "
                    f"its floor, and whatever that one slot cannot fill is drawn "
                    f"as empty background. Share the spare width across the slots "
                    f"that draw."
                ),
            )
        )
    return findings


def _scan_model_only_colour_asserts(path: Path, tree: ast.AST) -> list[Finding]:
    """GUI006 — a colour assertion on a live widget with no pixel check.

    Scope: TEST FILES ONLY. Production widget code does not assert its
    own colours, and restricting the rule keeps it from changing a
    single finding in src/.

    Severity is HIGH, and the choice is the whole design of the rule.
    coding_archetype documents the failure at its `_TEST_FILE_EXEMPT`
    definition: a gate that always fires is a gate nobody reads. The
    repo-wide population of colour/brush/palette/stylesheet assertions
    in tests/ is 25, and MEASURED, only 9 of them read a LIVE Qt
    object -- the shape where the model can disagree with the screen.
    The other 16 compare the return of a PURE colour-computing helper
    against a hex literal (`_compose_denom_row_text(...) ->
    "#a8a8c5"`, `_contrast("#ffffff", "#ff5577") < 4.5`). Those are
    correct unit tests of a pure function; there is no screen for them
    to be wrong about, and flagging them would triple the count with
    non-defects and earn the rule a standing waiver.

    So GUI006 fires on the live-object shape only, and because it then
    describes a real false-confidence defect rather than a style
    preference, it blocks.
    """
    if not _is_test_path(path):
        return []
    findings: list[Finding] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not fn.name.startswith("test"):
            continue
        if _mentions_pixel_construct(fn):
            continue
        tainted = _tainted_locals(fn)
        for node in ast.walk(fn):
            if not isinstance(node, ast.Assert):
                continue
            direct = _has_model_colour_read(node.test)
            indirect = bool(_names_in(node.test) & tainted)
            if not (direct or indirect):
                continue
            findings.append(
                Finding(
                    tool="gui-static",
                    severity="high",
                    file=str(path),
                    line=node.lineno,
                    rule_id="GUI006",
                    message=(
                        f"Test {fn.name!r} asserts a colour read off a live Qt "
                        "object (background/foreground/palette/styleSheet) and "
                        "never samples a rendered pixel. The getter reports what "
                        "the widget was TOLD to paint; a stylesheet rule for the "
                        "same element overrides it and the getter keeps returning "
                        "the old value, so this assertion can pass while the "
                        "screen shows a different colour. Render the widget and "
                        "sample the pixel (see tests/qt_pixel.py)."
                    ),
                )
            )
    return findings


_GROUND_RULE = "GUI010"

# The Web Content Accessibility Guidelines linearise each sRGB channel before
# weighting it; a plain channel average returns a different number.
_SRGB_KNEE = 0.04045
_SRGB_KNEE_DIVISOR = 12.92
_SRGB_GAMMA_OFFSET = 0.055
_SRGB_GAMMA_SCALE = 1.055
_SRGB_GAMMA_EXPONENT = 2.4
_LUMINANCE_WEIGHTS = (0.2126, 0.7152, 0.0722)

# Contrast ratio adds this to both luminances, so the ratio runs 1 to 21.
_CONTRAST_FLARE = 0.05

# Web Content Accessibility Guidelines, Contrast (Minimum) at level AA.
_CONTRAST_TEXT_MIN = 4.5
_CONTRAST_LARGE_TEXT_MIN = 3.0

# Large-scale text in Contrast (Minimum): 18 point, or 14 point bold.
_LARGE_TEXT_PX = 24.0
_LARGE_BOLD_TEXT_PX = 18.66

# CIE 1976 L*a*b*, D65 white point, and the just-noticeable difference Mahy,
# Van Eycken and Oosterlinck measured for delta E in it.
_D65_WHITE = (0.95047, 1.0, 1.08883)
_LAB_EPSILON = 216.0 / 24389.0
_LAB_KAPPA = 24389.0 / 27.0
_DELTA_E_JND = 2.3

# Angular separations the published harmonies stand at on the hue circle:
# analogous, triadic, split-complementary and complementary.
_HARMONY_SEPARATIONS = (30.0, 120.0, 150.0, 180.0)
_HARMONY_TOLERANCE_DEG = 1.0

#: The module whose named tokens are the declared palette every ground is
#: judged against. It is itself exempt, being the declaration.
_PALETTE_MODULE = "src/gui/design_system.py"

_HEX_COLOUR = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")

_CSS_DECLARATION = re.compile(
    r"(?<![-\w])(background-color|background|color|border(?:-[a-z]+)*)\s*:\s*([^;{}]+)"
)

_CSS_FONT_SIZE = re.compile(r"(?<![-\w])font-size\s*:\s*([0-9.]+)\s*(px|pt)")

_CSS_BOLD = re.compile(r"(?<![-\w])font-weight\s*:\s*(bold|[6-9]00)")

#: A name carrying one of these declares a ground, so its colours are read as
#: the grounds of one column.
_GROUND_NAME_MARKS = ("GROUND", "BACKGROUND", "_BG", "BG_")

#: A name carrying one of these holds what sits on a ground, not the ground, so
#: `TRANCHE_ROW_BORDER_BY_BG` maps borders and is not a set of grounds.
_SITTER_NAME_MARKS = ("BORDER", "OUTLINE", "TEXT", "FOREGROUND", "LINE", "EDGE")

_GROUND_SETTERS = frozenset({"setBackground"})
_MARK_SETTERS = frozenset({"setForeground"})

_COLOUR_WRAPPERS = frozenset({"QColor", "QBrush", "rgba", "_rgba"})


def _rgb_of(text: str) -> tuple[int, int, int] | None:
    """``text``'s first hex colour as three 0-255 channels, or None."""
    found = _HEX_COLOUR.search(text or "")
    if found is None:
        return None
    digits = found.group(0)[1:]
    if len(digits) in (3, 4):
        digits = "".join(ch * 2 for ch in digits[:3])
    digits = digits[:6]
    return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))


def _linear_channel(value: int) -> float:
    """One sRGB channel linearised as the contrast definition linearises it."""
    scaled = value / 255.0
    if scaled <= _SRGB_KNEE:
        return scaled / _SRGB_KNEE_DIVISOR
    return ((scaled + _SRGB_GAMMA_OFFSET) / _SRGB_GAMMA_SCALE) ** _SRGB_GAMMA_EXPONENT


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """``rgb``'s relative luminance, the weighted sum of its linear channels."""
    parts = [_linear_channel(channel) for channel in rgb]
    return sum(w * p for w, p in zip(_LUMINANCE_WEIGHTS, parts))


def _contrast_ratio(one: tuple[int, int, int], other: tuple[int, int, int]) -> float:
    """The contrast ratio between two colours, from 1 to 21."""
    first = _relative_luminance(one)
    second = _relative_luminance(other)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + _CONTRAST_FLARE) / (darker + _CONTRAST_FLARE)


def _xyz(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """``rgb``'s CIE XYZ tristimulus values under the D65 white point."""
    red, green, blue = (_linear_channel(channel) for channel in rgb)
    return (
        0.4124564 * red + 0.3575761 * green + 0.1804375 * blue,
        0.2126729 * red + 0.7151522 * green + 0.0721750 * blue,
        0.0193339 * red + 0.1191920 * green + 0.9503041 * blue,
    )


def _lab_component(ratio: float) -> float:
    """One CIE 1976 L*a*b* component of a tristimulus ratio."""
    if ratio > _LAB_EPSILON:
        return ratio ** (1.0 / 3.0)
    return (_LAB_KAPPA * ratio + 16.0) / 116.0


def _lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """``rgb`` in CIE 1976 L*a*b*, the space distances are judged in."""
    x, y, z = _xyz(rgb)
    fx, fy, fz = (
        _lab_component(x / _D65_WHITE[0]),
        _lab_component(y / _D65_WHITE[1]),
        _lab_component(z / _D65_WHITE[2]),
    )
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def _delta_e(one: tuple[int, int, int], other: tuple[int, int, int]) -> float:
    """The CIE 1976 delta E between two colours, a perceptual distance."""
    first, second = _lab(one), _lab(other)
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def _hue_angle(rgb: tuple[int, int, int]) -> float:
    """``rgb``'s hue angle in degrees on the CIE 1976 L*a*b* hue circle."""
    _, a_star, b_star = _lab(rgb)
    return math.degrees(math.atan2(b_star, a_star)) % 360.0


def _chroma(rgb: tuple[int, int, int]) -> float:
    """``rgb``'s chroma, its distance from the neutral axis in L*a*b*."""
    _, a_star, b_star = _lab(rgb)
    return math.sqrt(a_star * a_star + b_star * b_star)


def _hue_separation(one: tuple[int, int, int], other: tuple[int, int, int]) -> float:
    """The shorter arc in degrees between two hue angles, 0 to 180."""
    gap = abs(_hue_angle(one) - _hue_angle(other)) % 360.0
    return min(gap, 360.0 - gap)


def _is_harmony_of(ground: tuple[int, int, int], token: tuple[int, int, int]) -> bool:
    """Whether ``ground`` stands at a published harmony separation from ``token``.

    Both carry chroma above the just-noticeable difference, since a hue angle is
    indeterminate for an achromatic colour, and lightness and chroma hold within
    that difference so only the hue is turned.
    """
    ground_chroma, token_chroma = _chroma(ground), _chroma(token)
    if ground_chroma <= _DELTA_E_JND or token_chroma <= _DELTA_E_JND:
        return False
    lit, _, _ = _lab(ground)
    token_lit, _, _ = _lab(token)
    if abs(lit - token_lit) > _DELTA_E_JND:
        return False
    if abs(ground_chroma - token_chroma) > _DELTA_E_JND:
        return False
    turn = _hue_separation(ground, token)
    return any(
        abs(turn - separation) <= _HARMONY_TOLERANCE_DEG
        for separation in _HARMONY_SEPARATIONS
    )


def _names_a_ground(name: str) -> bool:
    """Whether ``name`` names a ground and does not name what sits on one."""
    upper = name.upper()
    if any(mark in upper for mark in _SITTER_NAME_MARKS):
        return False
    return any(mark in upper for mark in _GROUND_NAME_MARKS)


def _module_hex_constants(tree: ast.AST) -> dict[str, str]:
    """Every module-level name in ``tree`` that resolves to a hex colour."""
    found: dict[str, str] = {}
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        text = _resolved_colour_text(node.value, found)
        if text is not None:
            found[target.id] = text
    return found


def _resolved_colour_text(node: ast.AST, known: dict[str, str]) -> str | None:
    """The hex colour ``node`` resolves to, from ``known`` or from the palette.

    A name the module does not declare is looked up as a palette token, so
    `ds.SURFACE_1` and a directly imported `SURFACE_1` both resolve.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value if _HEX_COLOUR.search(node.value) else None
    if isinstance(node, ast.Name):
        return known.get(node.id) or _declared_palette().get(node.id)
    if isinstance(node, ast.Attribute):
        return known.get(node.attr) or _declared_palette().get(node.attr)
    if isinstance(node, ast.Call):
        name = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        if name in _COLOUR_WRAPPERS and node.args:
            return _resolved_colour_text(node.args[0], known)
    return None


_PALETTE_CACHE: dict[str, dict[str, str]] = {}


def _declared_palette() -> dict[str, str]:
    """The palette module's named tokens, each mapped to its hex value."""
    held = _PALETTE_CACHE.get(_PALETTE_MODULE)
    if held is not None:
        return held
    # Set before parsing: `_module_hex_constants` reads this cache back, and an
    # unset entry would send it here again.
    _PALETTE_CACHE[_PALETTE_MODULE] = {}
    path = REPO_ROOT / _PALETTE_MODULE
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return {}
    tokens = _module_hex_constants(tree)
    _PALETTE_CACHE[_PALETTE_MODULE] = tokens
    return tokens


def _palette_token_for(ground: tuple[int, int, int]) -> str | None:
    """The palette token ``ground`` holds, or one it is a published harmony of."""
    for name, text in _declared_palette().items():
        token = _rgb_of(text)
        if token is not None and token == ground:
            return name
    for name, text in _declared_palette().items():
        token = _rgb_of(text)
        if token is not None and _is_harmony_of(ground, token):
            return name
    return None


def _nearest_palette_token(ground: tuple[int, int, int]) -> tuple[str, float]:
    """The palette token nearest ``ground`` by delta E, and that distance."""
    best, distance = "", float("inf")
    for name, text in _declared_palette().items():
        token = _rgb_of(text)
        if token is None:
            continue
        gap = _delta_e(ground, token)
        if gap < distance:
            best, distance = name, gap
    return (best, distance)


def _style_text(node: ast.AST, known: dict[str, str]) -> str | None:
    """``node``'s declaration text, with every resolvable colour written in."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if not isinstance(node, ast.JoinedStr):
        return None
    parts: list[str] = []
    for piece in node.values:
        if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
            parts.append(piece.value)
        elif isinstance(piece, ast.FormattedValue):
            parts.append(_resolved_colour_text(piece.value, known) or "\u0000")
        else:
            parts.append("\u0000")
    return "".join(parts)


#: Contrast (Minimum) exempts text in an inactive component, so a block on this
#: state is not read.
_INACTIVE_STATE = ":disabled"


def _declaration_blocks(text: str) -> list[tuple[str, str]]:
    """Each selector and its block in ``text``, or the whole of it when it has none.

    A style sheet naming several selectors pairs a ground with the colour in
    its own block; `QTabBar::tab:hover` never sits on `QTabWidget::pane`.
    """
    found = [
        (match.group(1), match.group(2))
        for match in re.finditer(r"([^{}]*)\{([^{}]*)\}", text)
    ]
    return found if found else [("", text)]


def _declared_colours(text: str) -> tuple[list[str], list[str]]:
    """The ground colours and the colours that sit on them in one declaration block.

    A `border` colour is left out: the guidelines measure a boundary against the
    adjacent colour, and one block names only the fill on one of its two sides.
    """
    grounds: list[str] = []
    sitters: list[str] = []
    for prop, value in _CSS_DECLARATION.findall(text):
        if _HEX_COLOUR.search(value) is None:
            continue
        if prop in ("background", "background-color"):
            grounds.append(value)
        elif prop == "color":
            sitters.append(value)
    return (grounds, sitters)


def _text_floor(text: str) -> float:
    """The contrast floor the text in one declaration block must reach."""
    found = _CSS_FONT_SIZE.search(text)
    if found is None:
        return _CONTRAST_TEXT_MIN
    size = float(found.group(1))
    pixels = size if found.group(2) == "px" else size * 96.0 / 72.0
    bold = _CSS_BOLD.search(text) is not None
    if pixels >= _LARGE_TEXT_PX or (bold and pixels >= _LARGE_BOLD_TEXT_PX):
        return _CONTRAST_LARGE_TEXT_MIN
    return _CONTRAST_TEXT_MIN


def _contrast_finding(
    path: Path,
    line: int,
    ground: tuple[int, int, int],
    sitter: tuple[int, int, int],
    floor: float,
) -> Finding:
    """One GUI010 finding for a ground that does not carry what sits on it."""
    ratio = _contrast_ratio(ground, sitter)
    return Finding(
        tool="gui-static",
        severity="high",
        file=str(path),
        line=line,
        rule_id=_GROUND_RULE,
        message=(
            f"ground #{'%02x%02x%02x' % ground} carries #"
            f"{'%02x%02x%02x' % sitter} at {ratio:.2f} to 1. The Web Content "
            f"Accessibility Guidelines set {floor:g} to 1 under Contrast "
            f"(Minimum) at level AA. Take a ground from {_PALETTE_MODULE} that "
            f"reaches it, or lighten the colour that sits on it."
        ),
    )


def _palette_finding(path: Path, line: int, ground: tuple[int, int, int]) -> Finding:
    """One GUI010 finding for a ground the declared palette does not hold."""
    name, gap = _nearest_palette_token(ground)
    near = f"{name} at delta E {gap:.1f}" if name else "no token"
    return Finding(
        tool="gui-static",
        severity="high",
        file=str(path),
        line=line,
        rule_id=_GROUND_RULE,
        message=(
            f"ground #{'%02x%02x%02x' % ground} is not a token in "
            f"{_PALETTE_MODULE} and stands at no published harmony separation "
            f"from one on the CIE 1976 L*a*b* hue circle. Nearest token: "
            f"{near}. Name a token instead of writing the hex value."
        ),
    )


def _set_finding(path: Path, line: int, name: str, count: int, gap: float) -> Finding:
    """One GUI010 finding for a column given more than one ground."""
    return Finding(
        tool="gui-static",
        severity="high",
        file=str(path),
        line=line,
        rule_id=_GROUND_RULE,
        message=(
            f"{name} gives one column {count} grounds, the nearest pair "
            f"{gap:.1f} apart by delta E in CIE 1976 L*a*b*. One column takes "
            f"ONE ground so every mark on it reads against the same colour. "
            f"Replace the set with a single token from {_PALETTE_MODULE}."
        ),
    )


def _distinct_grounds(
    colours: list[tuple[int, int, int]],
) -> tuple[list[tuple[int, int, int]], float]:
    """The colours in ``colours`` that differ perceptually, and the nearest gap."""
    kept: list[tuple[int, int, int]] = []
    nearest = float("inf")
    for colour in colours:
        gaps = [_delta_e(colour, held) for held in kept]
        if gaps:
            nearest = min(nearest, min(gaps))
        if all(gap > _DELTA_E_JND for gap in gaps):
            kept.append(colour)
    return (kept, 0.0 if nearest == float("inf") else nearest)


def _ground_set_faults(
    path: Path, tree: ast.AST, known: dict[str, str]
) -> list[Finding]:
    """Every ground-named collection in ``tree`` that carries several grounds."""
    faults: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if not _names_a_ground(target.id):
            continue
        held = node.value
        members: list[ast.AST] = []
        if isinstance(held, ast.Dict):
            members = [v for v in held.values if v is not None]
        elif isinstance(held, (ast.List, ast.Tuple, ast.Set)):
            members = list(held.elts)
        colours = []
        for member in members:
            text = _resolved_colour_text(member, known)
            rgb = _rgb_of(text) if text else None
            if rgb is not None:
                colours.append(rgb)
        kept, nearest = _distinct_grounds(colours)
        if len(kept) > 1:
            faults.append(
                _set_finding(path, node.lineno, target.id, len(kept), nearest)
            )
    return faults


def _named_ground_faults(
    path: Path, tree: ast.AST, known: dict[str, str]
) -> list[Finding]:
    """Every ground-named single colour in ``tree`` the palette does not hold."""
    faults: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if not _names_a_ground(target.id):
            continue
        text = _resolved_colour_text(node.value, known)
        ground = _rgb_of(text) if text else None
        if ground is not None and _palette_token_for(ground) is None:
            faults.append(_palette_finding(path, node.lineno, ground))
    return faults


def _style_ground_faults(
    path: Path, tree: ast.AST, known: dict[str, str]
) -> list[Finding]:
    """Every declaration block in ``tree`` whose ground fails what sits on it."""
    faults: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Constant, ast.JoinedStr)):
            continue
        text = _style_text(node, known)
        if not text or "background" not in text:
            continue
        for selector, block in _declaration_blocks(text):
            if _INACTIVE_STATE in selector.lower():
                continue
            grounds, sitters = _declared_colours(block)
            floor = _text_floor(block)
            for ground_text in grounds:
                ground = _rgb_of(ground_text)
                if ground is None:
                    continue
                for sitter_text in sitters:
                    sitter = _rgb_of(sitter_text)
                    if sitter is not None and _contrast_ratio(ground, sitter) < floor:
                        faults.append(
                            _contrast_finding(path, node.lineno, ground, sitter, floor)
                        )
    return faults


def _setter_colours(
    fn: ast.AST, names: frozenset[str], known: dict[str, str]
) -> list[tuple[int, tuple[int, int, int]]]:
    """Every colour ``fn`` hands one of ``names``, with the call's line."""
    local = dict(known)
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                text = _resolved_colour_text(node.value, local)
                if text is not None:
                    local[target.id] = text
    found: list[tuple[int, tuple[int, int, int]]] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in names or not node.args:
            continue
        text = _resolved_colour_text(node.args[0], local)
        rgb = _rgb_of(text) if text else None
        if rgb is not None:
            found.append((node.lineno, rgb))
    return found


def _cell_ground_faults(
    path: Path, tree: ast.AST, known: dict[str, str]
) -> list[Finding]:
    """Every function in ``tree`` whose cell grounds fail the palette or a mark."""
    faults: list[Finding] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        grounds = _setter_colours(fn, _GROUND_SETTERS, known)
        if not grounds:
            continue
        marks = _setter_colours(fn, _MARK_SETTERS, known)
        kept, nearest = _distinct_grounds([rgb for _, rgb in grounds])
        if len(kept) > 1:
            faults.append(
                _set_finding(path, grounds[0][0], fn.name, len(kept), nearest)
            )
        for line, ground in grounds:
            if _palette_token_for(ground) is None:
                faults.append(_palette_finding(path, line, ground))
            for _, mark in marks:
                if _contrast_ratio(ground, mark) < _CONTRAST_TEXT_MIN:
                    faults.append(
                        _contrast_finding(path, line, ground, mark, _CONTRAST_TEXT_MIN)
                    )
    return faults


def _scan_column_ground_colours(path: Path, tree: ast.AST) -> list[Finding]:
    """GUI010 — a column takes one ground, from the palette, that carries its marks.

    It reads three departures: a ground whose contrast with what sits on it
    misses the published floor, a ground the declared palette neither holds nor
    stands in a published harmony with, and a set giving one column several
    grounds.
    """
    if str(path).replace("\\", "/").endswith(_PALETTE_MODULE):
        return []
    known = _module_hex_constants(tree)
    findings = _style_ground_faults(path, tree, known)
    findings.extend(_cell_ground_faults(path, tree, known))
    findings.extend(_named_ground_faults(path, tree, known))
    findings.extend(_ground_set_faults(path, tree, known))
    return findings


def _run_gui_static(target: Path) -> list[Finding]:
    """Static-analysis pass for PySide6 quality gotchas."""
    findings: list[Finding] = []
    files_to_check: list[Path] = []
    if target.is_file() and target.suffix == ".py":
        files_to_check = [target]
    elif target.is_dir():
        files_to_check = list(target.rglob("*.py"))

    for f in files_to_check:
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src, filename=str(f))
        except SyntaxError as e:
            findings.append(
                Finding(
                    tool="gui-static",
                    severity="high",
                    file=str(f),
                    line=e.lineno or 0,
                    rule_id="SYNTAX",
                    message=f"cannot parse file: {e.msg}",
                )
            )
            continue
        analyzer = _GUIAnalyzer(str(f), _local_widget_classes(tree))
        analyzer.visit(tree)
        findings.extend(analyzer.findings)
        findings.extend(_scan_model_only_colour_asserts(f, tree))
        findings.extend(_scan_segmented_group_skin(f, tree))
        findings.extend(_scan_row_spare_width(f, tree))
        findings.extend(_scan_column_ground_colours(f, tree))
    return findings


_GEOMETRY_TOOL = "gui-geometry"

_GEOMETRY_RULE = "GUI009"

#: The screen each file draws, for the rule that renders and measures. A file
#: absent here is never rendered, so the rule reports nothing about it.
_GEOMETRY_SCREEN_FILES: dict[str, str] = {
    "src/gui/main_tabs/header_strip.py": "header_row",
    "src/gui/main_tabs/header_strip_surface.py": "header_row",
    "src/gui/web/header_strip.js": "header_row",
    "harness_fixtures/gui_archetype/known_good_rendered_row.js": "fixture_row_visible",
    "harness_fixtures/gui_archetype/known_bad_hidden_row.js": "fixture_row_hidden",
    "harness_fixtures/gui_archetype/known_bad_void_row.js": "fixture_row_void",
}

#: The variants a screen is built in, where it has fewer than both. The fixture
#: rows are pages and have no Qt half.
_GEOMETRY_SCREEN_VARIANTS: dict[str, tuple[str, ...]] = {
    "fixture_row_visible": ("react",),
    "fixture_row_hidden": ("react",),
    "fixture_row_void": ("react",),
}

#: The paths the reference tree is read from, so a fixture screen is comparable
#: against the same commit the product screens are.
_GEOMETRY_REFERENCE_PATHS: tuple[str, ...] = ("src", "harness_fixtures")

#: The windows the screen is built at. 1600 is wider than the header row's own
#: natural width, so spare width the row does not fill reads as void; 900 is
#: narrower than it, so a caption or an amount that no longer fits reads as
#: overflow. One window alone sees one of the two and never the other.
_GEOMETRY_WINDOWS: tuple[tuple[int, int], ...] = ((1600, 700), (900, 700))

_GEOMETRY_WINDOW_W = _GEOMETRY_WINDOWS[0][0]
_GEOMETRY_WINDOW_H = _GEOMETRY_WINDOWS[0][1]

_GEOMETRY_VARIANTS: tuple[str, ...] = ("qt", "react")

#: The two committed states of the header row this rule is calibrated on. The
#: pair is the fixture: one file cannot hold a row, so the rule is proved by
#: reading the bad state against the good one and the good state against itself.
_GEOMETRY_CALIBRATION_BAD = "91dcad3e"
_GEOMETRY_CALIBRATION_GOOD = "2ffe9682"

#: The squash merge on `current` carrying the reference header row in `src` and
#: `harness_fixtures`, which every clone reaches.
_GEOMETRY_REFERENCE_COMMIT = "c10325d3caae7e668669641556abad462a312d81"

#: The scripts the React header page loads, in load order.
_HEADER_ROW_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "design_tokens.js",
    "theme_engine.js",
    "shared_widgets.js",
    "privacy_dot.js",
    "spendable_profits.js",
    "dashboard_stat_card.js",
    "header_strip.js",
)

#: The element the React page draws the header row into.
_HEADER_ROW_ROOT_ID = "acervator-header-row-root"

#: The page ground, so no sheet of its own adds width to a slot.
_HEADER_ROW_PAGE_STYLE = (
    "*{margin:0;padding:0;box-sizing:border-box}"
    "html,body{height:100%;overflow:hidden}"
    f"#{_HEADER_ROW_ROOT_ID}{{width:100%}}"
)

#: `acervator.call` answered over a queue the driver drains, so the page draws
#: the figures `desktop_bridge` serves instead of values written into it.
_HEADER_ROW_HOST_SCRIPT = """(function (g) {
  "use strict";
  var next = 1;
  g.__acervatorAsked = [];
  g.__acervatorWaiting = {};
  g.acervator = {
    call: function (method, params) {
      var id = next++;
      g.__acervatorAsked.push({ id: id, method: method, params: params });
      return new Promise(function (resolve, reject) {
        g.__acervatorWaiting[id] = { resolve: resolve, reject: reject };
      });
    }
  };
  g.__acervatorAnswer = function (id, payload) {
    var waiting = g.__acervatorWaiting[id];
    delete g.__acervatorWaiting[id];
    if (waiting) { waiting.resolve(payload); }
    return Object.keys(g.__acervatorWaiting).length;
  };
  g.__acervatorTake = function () {
    var taken = g.__acervatorAsked;
    g.__acervatorAsked = [];
    return taken;
  };
})(window);"""

#: The row the React page draws, every slot inside it, and the ancestor chain
#: each was measured through, as one reading. `offsetHeight` and the computed
#: height are both carried: an element under a hidden ancestor answers 0 from
#: `getBoundingClientRect` and `offsetHeight` while the computed height still
#: answers the value the sheet specified, so either one read alone is wrong.
_HEADER_ROW_READ_JS = """(function () {
  var row = document.querySelector('[data-part="top-row"]');
  if (!row) {
    return JSON.stringify({
      "row": null, "slots": [], "rendered": false,
      "unrendered": "no element carries data-part=\\"top-row\\"", "ancestors": []
    });
  }
  function overflow(node) {
    var over = 0;
    var all = node.querySelectorAll("*");
    for (var at = 0; at < all.length; at++) {
      over += Math.max(0, all[at].scrollWidth - all[at].clientWidth);
    }
    return over;
  }
  function named(node) {
    return node.tagName.toLowerCase() +
      (node.id ? "#" + node.id : "") +
      (node.getAttribute("data-part") ? "[" + node.getAttribute("data-part") + "]" : "");
  }
  var chain = [];
  var unrendered = "";
  var walk = row;
  while (walk && walk !== document.documentElement) {
    var style = window.getComputedStyle(walk);
    var step = {
      "element": named(walk),
      "offset_h": walk.offsetHeight,
      "offset_w": walk.offsetWidth,
      "display": style.display,
      "visibility": style.visibility,
      "computed_h": style.height
    };
    if (!unrendered && (step.display === "none" || step.visibility === "hidden" ||
                        step.offset_h === 0 || step.offset_w === 0)) {
      unrendered = step.element + " draws nothing: display " + step.display +
        ", visibility " + step.visibility + ", offset " + step.offset_w + "x" +
        step.offset_h + ", computed height " + step.computed_h;
    }
    chain.push(step);
    walk = walk.parentElement;
  }
  var box = row.getBoundingClientRect();
  var rowStyle = window.getComputedStyle(row);
  var declaredGap = parseFloat(rowStyle.columnGap);
  if (isNaN(declaredGap)) { declaredGap = 0; }
  var slots = [];
  var edges = [];
  for (var at = 0; at < row.children.length; at++) {
    var node = row.children[at];
    var seen = node.getBoundingClientRect();
    edges.push({ "left": seen.left, "right": seen.right });
    slots.push({
      "slot": node.getAttribute("data-slot") || ("child[" + at + "]"),
      "x": Math.round(seen.left - box.left),
      "w": Math.round(seen.width),
      "h": Math.round(seen.height),
      "offset_h": node.offsetHeight,
      "computed_h": window.getComputedStyle(node).height,
      "overflow_px": overflow(node)
    });
  }
  // The voids are summed from the unrounded edges and rounded once, so half a
  // pixel of layout rounding on each of eight boundaries is not read as a void.
  edges.sort(function (a, b) { return a.left - b.left; });
  var head = 0;
  var gap = 0;
  var tail = 0;
  if (edges.length > 0) {
    head = Math.max(0, edges[0].left - box.left);
    tail = Math.max(0, box.right - edges[edges.length - 1].right);
    for (var step = 1; step < edges.length; step++) {
      gap += Math.max(0, edges[step].left - edges[step - 1].right - declaredGap);
    }
  }
  return JSON.stringify({
    "row": { "w": Math.round(box.width), "h": Math.round(box.height) },
    "slots": slots,
    "voids": {
      "head_px": Math.round(head),
      "gap_px": Math.round(gap),
      "tail_px": Math.round(tail)
    },
    "rendered": unrendered === "",
    "unrendered": unrendered,
    "ancestors": chain
  });
})()"""


class _GeometryStub:
    """Answers every call the header row makes on a collaborator it has none of.

    A reference commit builds the row against window methods that commit had,
    so the driver names none of them and this answers whatever is asked.
    """

    def __getattr__(self, name: str) -> "_GeometryStub":
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return _GeometryStub()

    def __call__(self, *_args: object, **_kwargs: object) -> None:
        return None


class _GeometrySettings:
    """The settings store the header row reads its stored asset class from."""

    def get(self, _key: str, default: object = None) -> object:
        return default

    def set(self, _key: str, _value: object) -> None:
        return None


def _qt_text_overflow_px(widget: object) -> int:
    """The width the text inside `widget` asks for beyond the room it has.

    `sizeHint` is read, never the drawn string `ElidingLabel` has already
    shortened to the room it has.
    """
    over = 0
    seen = [widget]
    while seen:
        each = seen.pop()
        reader = getattr(each, "text", None)
        if callable(reader) and hasattr(each, "sizeHint"):
            try:
                wants = each.sizeHint().width()
            except (RuntimeError, TypeError):
                wants = 0
            over += max(0, wants - each.width())
        for child in each.children():
            if hasattr(child, "width"):
                seen.append(child)
    return over


def _react_reading(drawn: dict, spacing: int) -> dict:
    """One page reading, with the void widths and the ancestor verdict filled in.

    The page sums its own voids off the unrounded edges, so `_row_voids` answers
    only where the page returned none.
    """
    row = drawn.get("row") or {"w": 0, "h": 0}
    slots = drawn.get("slots") or []
    rendered = bool(drawn.get("rendered"))
    said = str(drawn.get("unrendered") or "")
    return {
        "variant": "react",
        "row": row,
        "slots": slots,
        "voids": drawn.get("voids") or _row_voids(int(row.get("w", 0)), slots, spacing),
        "rendered": rendered,
        "unrendered": "" if rendered else (said or "the page returned no reading"),
        "ancestors": drawn.get("ancestors") or [],
    }


def _qt_ancestor_chain(widget: object) -> list[dict]:
    """Each widget from `widget` up to its window, and whether it draws anything.

    `isVisible` already answers False under a hidden ancestor, so a reading
    taken through this chain cannot report a size for a row nobody sees.
    """
    chain: list[dict] = []
    walk = widget
    while walk is not None:
        shown = bool(walk.isVisible())
        wide, tall = walk.width(), walk.height()
        step = {
            "element": type(walk).__name__,
            "offset_h": tall,
            "offset_w": wide,
            "display": "shown" if shown else "hidden",
            "visibility": "visible" if shown else "hidden",
            "computed_h": f"{walk.sizeHint().height()}px",
            "unrendered": "",
        }
        if not shown or wide == 0 or tall == 0:
            step["unrendered"] = (
                f"{step['element']} draws nothing: {step['display']}, "
                f"size {wide}x{tall}, size hint height {step['computed_h']}"
            )
        chain.append(step)
        walk = walk.parentWidget()
    return chain


def _row_voids(row_w: int, slots: list[dict], spacing: int) -> dict:
    """The empty width the row carries, at its head, between its slots and at its tail."""
    if not slots:
        return {"head_px": 0, "gap_px": 0, "tail_px": 0}
    ordered = sorted(slots, key=lambda one: one["x"])
    gap = 0
    for before, after in zip(ordered, ordered[1:]):
        gap += max(0, after["x"] - (before["x"] + before["w"]) - spacing)
    last = ordered[-1]
    return {
        "head_px": max(0, ordered[0]["x"]),
        "gap_px": gap,
        "tail_px": max(0, row_w - (last["x"] + last["w"])),
    }


def _header_row_qt_geometry(width: int, height: int) -> dict:
    """Build the real Qt header row offscreen and read every slot's geometry."""
    from PySide6.QtWidgets import (
        QApplication,
        QMainWindow,
        QSizePolicy,
        QWidget,
    )

    from src.gui.main_tabs import header_strip_surface as surface
    from src.gui.main_tabs.header_strip import HeaderStripMixin

    class _Host(HeaderStripMixin, QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self._status_log = _GeometryStub()
            self._settings = _GeometrySettings()
            self.setAccessibleName("Header row geometry window")
            self.setAccessibleDescription(
                "The header row built offscreen so each slot can be read."
            )

        def __getattr__(self, name: str) -> object:
            if name.startswith("__") and name.endswith("__"):
                raise AttributeError(name)
            return _GeometryStub()

    app = QApplication.instance() or QApplication([])
    host = _Host()
    central = host._build_header_strip()
    # The window gives the row the height its own widgets ask for only while
    # something else takes the rest, as the tab widget does in main_window.
    filler = QWidget()
    filler.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    central.addWidget(filler)
    host.resize(width, height)
    host.show()
    app.processEvents()

    row = host._header_strip_container
    layout = row.layout()
    order = list(getattr(surface, "TOP_ROW_ORDER", []))
    slots: list[dict] = []
    at = 0
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        if widget is None:
            continue
        geometry = widget.geometry()
        slots.append(
            {
                "slot": order[at] if at < len(order) else f"child[{at}]",
                "x": geometry.x(),
                "w": geometry.width(),
                "h": geometry.height(),
                "offset_h": geometry.height(),
                "computed_h": f"{widget.sizeHint().height()}px",
                "overflow_px": _qt_text_overflow_px(widget),
            }
        )
        at += 1
    chain = _qt_ancestor_chain(row)
    unrendered = next((one["unrendered"] for one in chain if one["unrendered"]), "")
    reading = {
        "variant": "qt",
        "row": {"w": row.width(), "h": row.height()},
        "slots": slots,
        "voids": _row_voids(row.width(), slots, layout.spacing()),
        "rendered": unrendered == "",
        "unrendered": unrendered,
        "ancestors": chain,
    }
    host.close()
    host.deleteLater()
    app.processEvents()
    return reading


def _header_row_react_geometry(width: int, height: int) -> dict:
    """Load the real React header page offscreen and read every slot's geometry."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])

    from src.core.desktop_bridge import build_registry, dispatch
    from src.gui.main_tabs import header_strip_surface as surface
    from src.gui.react_history_panel import page_html

    registry = build_registry(None)
    body = (
        "<style>"
        + _HEADER_ROW_PAGE_STYLE
        + "</style>"
        + f'<div id="{_HEADER_ROW_ROOT_ID}"></div>'
    )
    view = QWebEngineView()
    view.resize(width, height)
    view.show()
    loop = QEventLoop()
    view.loadFinished.connect(lambda _ok: loop.quit())
    view.setHtml(
        page_html((), _HEADER_ROW_ASSETS, body, None, (_HEADER_ROW_HOST_SCRIPT,))
    )
    QTimer.singleShot(_GEOMETRY_PAGE_TIMEOUT_MS, loop.quit)
    loop.exec()

    held: dict = {}

    def _run(script: str) -> object:
        held.clear()

        def _got(value: object) -> None:
            held["value"] = value
            loop.quit()

        view.page().runJavaScript(script, _got)
        QTimer.singleShot(_GEOMETRY_PAGE_TIMEOUT_MS, loop.quit)
        loop.exec()
        return held.get("value")

    model = dispatch(surface.METHOD, {}, registry)
    _run(
        "window.acervatorHeader.renderStrip("
        f'document.getElementById("{_HEADER_ROW_ROOT_ID}"), '
        + json.dumps(model)
        + ") !== null"
    )
    # The cards and the spendable strip fetch their own models, so the page is
    # not drawn until every ask the queue holds has been answered.
    for _ in range(_GEOMETRY_PAGE_DRAIN_ROUNDS):
        asked = _run("JSON.stringify(window.__acervatorTake())")
        pending = json.loads(asked) if isinstance(asked, str) else []
        if not pending:
            break
        for one in pending:
            answer = dispatch(one["method"], one.get("params") or {}, registry)
            _run(
                f"window.__acervatorAnswer({int(one['id'])}, "
                + json.dumps(answer)
                + ")"
            )

    read = _run(_HEADER_ROW_READ_JS)
    drawn = json.loads(read) if isinstance(read, str) else {}
    reading = _react_reading(drawn, int(surface.TOP_ROW.get("spacing_px", 0)))
    view.close()
    view.deleteLater()
    app.processEvents()
    return reading


#: The element the fixture pair draws its row into.
_FIXTURE_ROW_ROOT_ID = "acervator-fixture-row-root"

#: The tree `emit_geometry` was pointed at, so a fixture is read from the same
#: commit as the modules beside it.
_GEOMETRY_TREE: Path = REPO_ROOT


def _fixture_row_geometry(module: str, width: int, height: int) -> dict:
    """Load one fixture row module offscreen and read the row it draws."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    source = (_GEOMETRY_TREE / "harness_fixtures" / "gui_archetype" / module).read_text(
        encoding="utf-8"
    )
    page = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
        "*{margin:0;padding:0;box-sizing:border-box}html,body{height:100%}"
        "</style></head><body>"
        f'<div id="{_FIXTURE_ROW_ROOT_ID}"></div>'
        "<script>" + source + "</script><script>window.acervatorFixtureRow.draw("
        f'document.getElementById("{_FIXTURE_ROW_ROOT_ID}"));'
        "</script></body></html>"
    )
    view = QWebEngineView()
    view.resize(width, height)
    view.show()
    loop = QEventLoop()
    view.loadFinished.connect(lambda _ok: loop.quit())
    view.setHtml(page)
    QTimer.singleShot(_GEOMETRY_PAGE_TIMEOUT_MS, loop.quit)
    loop.exec()

    held: dict = {}

    def _got(value: object) -> None:
        held["value"] = value
        loop.quit()

    view.page().runJavaScript(_HEADER_ROW_READ_JS, _got)
    QTimer.singleShot(_GEOMETRY_PAGE_TIMEOUT_MS, loop.quit)
    loop.exec()
    read = held.get("value")
    drawn = json.loads(read) if isinstance(read, str) else {}
    reading = _react_reading(drawn, 0)
    view.close()
    view.deleteLater()
    app.processEvents()
    return reading


def _fixture_row_visible_geometry(width: int, height: int) -> dict:
    """Read the fixture row whose holder draws."""
    return _fixture_row_geometry("known_good_rendered_row.js", width, height)


def _fixture_row_hidden_geometry(width: int, height: int) -> dict:
    """Read the fixture row whose holder is set to display none."""
    return _fixture_row_geometry("known_bad_hidden_row.js", width, height)


def _fixture_row_void_geometry(width: int, height: int) -> dict:
    """Read the fixture row whose slots fill only part of its width."""
    return _fixture_row_geometry("known_bad_void_row.js", width, height)


#: How long one page load or one page reading may take.
_GEOMETRY_PAGE_TIMEOUT_MS = 20000

#: How many rounds of asks the driver answers before it stops draining.
_GEOMETRY_PAGE_DRAIN_ROUNDS = 12

_GEOMETRY_BUILDERS: dict[tuple[str, str], Callable[[int, int], dict]] = {
    ("header_row", "qt"): _header_row_qt_geometry,
    ("header_row", "react"): _header_row_react_geometry,
    ("fixture_row_visible", "react"): _fixture_row_visible_geometry,
    ("fixture_row_hidden", "react"): _fixture_row_hidden_geometry,
    ("fixture_row_void", "react"): _fixture_row_void_geometry,
}


def emit_geometry(
    screen: str, variant: str, width: int, height: int, tree: Path | None = None
) -> int:
    """Print one screen's geometry, in one variant, as JSON on stdout.

    The rule runs this in a subprocess per tree and per variant, since two trees
    cannot both supply `src` to one interpreter.
    """
    global _GEOMETRY_TREE
    if tree is not None:
        _GEOMETRY_TREE = tree
    builder = _GEOMETRY_BUILDERS.get((screen, variant))
    if builder is None:
        print(json.dumps({"error": f"no builder for {screen}/{variant}"}))
        return 2
    print(json.dumps(builder(width, height)))
    return 0


def _git_executable() -> str:
    """The absolute path to git, so no lookup happens inside a subprocess call."""
    found = shutil.which("git")
    if not found:
        raise RuntimeError("git is not on PATH, so no reference tree can be read")
    return found


def _extract_reference_member(
    held: tarfile.TarFile, member: tarfile.TarInfo, root: Path
) -> None:
    """Write one archive member under `root`, refusing a link or an escaping path."""
    if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
        return
    where = (root / member.name).resolve()
    if not str(where).startswith(str(root.resolve())):
        return
    held.extract(member, root, filter="data")


def _geometry_reference_tree(commit: str) -> Path:
    """Extract `src` from `commit` into a scratch directory and return its root."""
    git = _git_executable()
    sha = subprocess.run(
        [git, "-C", str(REPO_ROOT), "rev-parse", commit],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout.strip()
    root = Path(tempfile.gettempdir()) / f"acervator_geometry_{sha[:12]}"
    if all((root / one).is_dir() for one in _GEOMETRY_REFERENCE_PATHS):
        return root
    root.mkdir(parents=True, exist_ok=True)
    bundle = root / "src.tar"
    with bundle.open("wb") as sink:
        subprocess.run(
            [git, "-C", str(REPO_ROOT), "archive", sha, *_GEOMETRY_REFERENCE_PATHS],
            stdout=sink,
            timeout=300,
            check=True,
        )
    with tarfile.open(bundle) as held:
        for member in held.getmembers():
            _extract_reference_member(held, member, root)
    bundle.unlink()
    return root


def _geometry_reading(
    tree: Path, screen: str, variant: str, width: int, height: int
) -> dict:
    """Run one geometry emitter in `tree` and return what it printed.

    The child's home is a scratch directory, so nothing it imports can read or
    write the runtime tree the running platform keeps its state in.
    """
    scratch = Path(tempfile.mkdtemp(prefix="acervator_geometry_home_"))
    env = dict(os.environ)
    for name in ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA"):
        env[name] = str(scratch)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["ACERVATOR_VARIANT"] = variant
    env["PYTHONPATH"] = str(tree)
    # The child imports the tree it measures, and must leave no bytecode in it.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "dev_harness.harness.gui_archetype",
            "--emit-geometry",
            screen,
            "--variant",
            variant,
            "--tree",
            str(tree),
            "--width",
            str(width),
            "--height",
            str(height),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
        timeout=300,
    )
    shutil.rmtree(scratch, ignore_errors=True)
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        raise RuntimeError(
            f"{screen}/{variant} in {tree} printed nothing, exit {proc.returncode}: "
            f"{(proc.stderr or '')[-400:]}"
        )
    return json.loads(line[-1])


def _slots_by_name(reading: dict) -> dict[str, dict]:
    return {one["slot"]: one for one in reading.get("slots", [])}


def _geometry_finding(path: Path, message: str, severity: str = "high") -> Finding:
    return Finding(
        tool=_GEOMETRY_TOOL,
        severity=severity,
        file=str(path),
        line=0,
        rule_id=_GEOMETRY_RULE,
        message=message,
    )


def _resized_slots(
    path: Path, where: str, was: dict, now: dict, allowed: frozenset[str]
) -> list[Finding]:
    """A slot whose size moved between the two trees and was not named as the target."""
    findings: list[Finding] = []
    before, after = _slots_by_name(was), _slots_by_name(now)
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name), after.get(name)
        if old is None:
            findings.append(
                _geometry_finding(
                    path,
                    f"{where}: slot {name!r} is drawn here and was not in the "
                    f"reference row",
                )
            )
            continue
        if new is None:
            findings.append(
                _geometry_finding(
                    path,
                    f"{where}: slot {name!r} was in the reference row and is "
                    f"not drawn here",
                )
            )
            continue
        if (old["w"], old["h"]) == (new["w"], new["h"]):
            continue
        if name in allowed:
            continue
        findings.append(
            _geometry_finding(
                path,
                f"{where}: slot {name!r} changed size with nothing asking it "
                f"to -- {old['w']}x{old['h']} in the reference, "
                f"{new['w']}x{new['h']} here",
            )
        )
    return findings


def _new_voids(path: Path, where: str, was: dict, now: dict) -> list[Finding]:
    """Empty width the row carries here and did not carry in the reference."""
    findings: list[Finding] = []
    before = was.get("voids") or {}
    after = now.get("voids") or {}
    for edge in ("head_px", "gap_px", "tail_px"):
        grew = int(after.get(edge, 0)) - int(before.get(edge, 0))
        if grew <= 0:
            continue
        findings.append(
            _geometry_finding(
                path,
                f"{where}: the row carries {grew} px more empty space at its "
                f"{edge[:-3]} than the reference row -- "
                f"{before.get(edge, 0)} px there, {after.get(edge, 0)} px here",
            )
        )
    return findings


def _new_overflow(path: Path, where: str, was: dict, now: dict) -> list[Finding]:
    """Text that wants more width than its slot has, where the reference fitted."""
    findings: list[Finding] = []
    before, after = _slots_by_name(was), _slots_by_name(now)
    for name in sorted(after):
        old = before.get(name)
        if old is None:
            continue
        grew = int(after[name].get("overflow_px", 0)) - int(old.get("overflow_px", 0))
        if grew <= 0:
            continue
        findings.append(
            _geometry_finding(
                path,
                f"{where}: the text in slot {name!r} wants {grew} px more room "
                f"than the reference needed, so it no longer fits its slot",
            )
        )
    return findings


def _unrendered(path: Path, where: str, now: dict) -> list[Finding]:
    """The reading was taken through an ancestor that drew nothing, or a slot that did.

    A hidden ancestor makes every size read 0 while the computed height still
    answers what the sheet specified, so two hidden rows compare equal and a
    drift check alone would answer green on a screen nobody can see.
    """
    findings: list[Finding] = []
    if not now.get("rendered", False):
        findings.append(
            _geometry_finding(
                path,
                f"{where}: the row was measured through something that drew "
                f"nothing, so no size below it is a reading -- "
                f"{now.get('unrendered') or 'no cause recorded'}",
            )
        )
    for one in now.get("slots", []):
        drawn = int(one.get("offset_h", one.get("h", 0)) or 0)
        if drawn > 0:
            continue
        findings.append(
            _geometry_finding(
                path,
                f"{where}: slot {one['slot']!r} drew nothing -- offset height 0 "
                f"against a computed height of {one.get('computed_h', 'unknown')}",
            )
        )
    return findings


def _row_empty_background(path: Path, where: str, now: dict) -> list[Finding]:
    """GUI008 read off the laid-out row: empty background anywhere in it.

    The void is the defect and no reference is needed for it, so this fires on
    the row as drawn rather than on a share list a reader can miss.
    """
    findings: list[Finding] = []
    voids = now.get("voids") or {}
    if not now.get("rendered", False):
        return findings
    for edge, told in (
        ("head_px", "before its first slot"),
        ("gap_px", "between its slots"),
        ("tail_px", "after its last slot"),
    ):
        empty = int(voids.get(edge, 0))
        if empty <= 0:
            continue
        findings.append(
            Finding(
                tool=_GEOMETRY_TOOL,
                severity="high",
                file=str(path),
                line=0,
                rule_id="GUI008",
                message=(
                    f"{where}: the row draws {empty} px of empty background "
                    f"{told}. Share that width across the slots that draw."
                ),
            )
        )
    return findings


def _variant_gap(qt: dict, react: dict) -> dict[str, tuple[int, int]]:
    """Per slot, how far the React page's size sits from the Qt screen's."""
    on_qt, on_page = _slots_by_name(qt), _slots_by_name(react)
    return {
        name: (
            on_page[name]["w"] - on_qt[name]["w"],
            on_page[name]["h"] - on_qt[name]["h"],
        )
        for name in set(on_qt) & set(on_page)
    }


def _variant_mismatch(
    path: Path,
    qt: dict,
    react: dict,
    reference_gap: dict[str, tuple[int, int]],
    at: str,
) -> list[Finding]:
    """Every slot the React page draws at a size the Qt screen does not.

    The Qt screen is the reference. A gap the reference commit already carried
    is reported at medium, so the rule can tell a regression from a standing
    difference; a gap that is new blocks.
    """
    findings: list[Finding] = []
    on_qt, on_page = _slots_by_name(qt), _slots_by_name(react)
    for name in sorted(set(on_qt) | set(on_page)):
        here, there = on_qt.get(name), on_page.get(name)
        if here is None or there is None:
            findings.append(
                _geometry_finding(
                    path,
                    f"at {at}: slot {name!r} is drawn by "
                    f"{'the Qt screen' if there is None else 'the React page'} "
                    f"and not by the other",
                )
            )
            continue
        gap = (there["w"] - here["w"], there["h"] - here["h"])
        if gap == (0, 0):
            continue
        stood = reference_gap.get(name)
        severity = "medium" if stood == gap else "high"
        findings.append(
            _geometry_finding(
                path,
                f"at {at}: the React page draws slot {name!r} at "
                f"{there['w']}x{there['h']} where the Qt screen draws "
                f"{here['w']}x{here['h']}"
                + ("" if severity == "high" else " -- the reference row already did"),
                severity,
            )
        )
    return findings


def scan_geometry_drift(
    target: Path,
    against: str,
    reshaped: frozenset[str],
    report: ArchetypeReport,
) -> None:
    """Render `target`'s screen in both variants and grade what moved.

    Records nothing when no screen names `target`, so `tool_availability`
    stays silent on every file this rule cannot build.
    """
    try:
        relative = target.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return
    screen = _GEOMETRY_SCREEN_FILES.get(relative)
    if screen is None:
        return

    variants = _GEOMETRY_SCREEN_VARIANTS.get(screen, _GEOMETRY_VARIANTS)
    try:
        reference = _geometry_reference_tree(against)
        readings = {
            (tree_name, variant, width, height): _geometry_reading(
                tree, screen, variant, width, height
            )
            for tree_name, tree in (("now", REPO_ROOT), ("was", reference))
            for variant in variants
            for width, height in _GEOMETRY_WINDOWS
        }
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
        tarfile.TarError,
    ) as exc:
        report.tool_availability[_GEOMETRY_TOOL] = f"error: {type(exc).__name__}: {exc}"
        report.errors.append(f"{_GEOMETRY_TOOL}: {type(exc).__name__}: {exc}")
        return

    for width, height in _GEOMETRY_WINDOWS:
        at = f"{width}x{height}"
        for variant in variants:
            was = readings[("was", variant, width, height)]
            now = readings[("now", variant, width, height)]
            where = f"{variant} at {at}"
            report.findings.extend(_unrendered(target, where, now))
            report.findings.extend(_row_empty_background(target, where, now))
            report.findings.extend(_resized_slots(target, where, was, now, reshaped))
            report.findings.extend(_new_voids(target, where, was, now))
            report.findings.extend(_new_overflow(target, where, was, now))
        if "qt" in variants and "react" in variants:
            report.findings.extend(
                _variant_mismatch(
                    target,
                    readings[("now", "qt", width, height)],
                    readings[("now", "react", width, height)],
                    _variant_gap(
                        readings[("was", "qt", width, height)],
                        readings[("was", "react", width, height)],
                    ),
                    at,
                )
            )
    report.tool_availability[_GEOMETRY_TOOL] = "ok"


_BANDIT_SEVERITY_OVERRIDES: dict[str, str] = {
    "B101": "high",
    "B105": "high",
    "B106": "high",
    "B107": "high",
    "B303": "high",
    "B324": "high",
    "B501": "high",
    "B502": "high",
    "B506": "high",
    "B602": "high",
    "B605": "high",
    "B609": "high",
}


class GUIArchetype:
    """Screen-quality archetype for both surfaces the application draws.

    A `.py` target runs the `gui-static` AST analyzer with ruff and
    bandit; a `.js` target runs `js_screen` as `gui-js`.
    """

    name = "gui_quality"
    version = "1.3"
    tools = (
        "gui-static",
        "ruff",
        "bandit",
        "gui-js",
        "eslint",
        "stylelint",
        "html-validate",
        _GEOMETRY_TOOL,
    )
    calibration_name = "gui"

    def __init__(
        self,
        against: str | None = None,
        reshaped: frozenset[str] | None = None,
    ) -> None:
        """Hold the reference commit and the slots this change was asked to reshape.

        `against` defaults to `_GEOMETRY_REFERENCE_COMMIT`, the recorded row.
        `reshaped` names the slots whose new size is wanted; every other slot
        is frozen.
        """
        self.geometry_against = against
        self.geometry_reshaped = reshaped if reshaped is not None else frozenset()

    def geometry_reference(self) -> str:
        """The commit the geometry rule holds the current tree against."""
        return self.geometry_against or _GEOMETRY_REFERENCE_COMMIT

    def load_calibration(self) -> str:
        from dev_harness.harness.calibrations import load

        return load(self.calibration_name)

    def review(self, target: Path) -> ArchetypeReport:
        target = Path(target).resolve()
        report = ArchetypeReport(target=str(target))

        if not target.exists():
            report.errors.append(f"target not found: {target}")
            report.falsification = self._build_falsification(report)
            return report

        if target.is_file():
            report.language = detect_language(target)
            if report.language == "javascript":
                return self._review_javascript(target, report)
            if report.language == "css":
                return self._review_css(target, report)
            if report.language == "html":
                return self._review_html(target, report)
            if report.language not in HANDLED_LANGUAGES:
                report.unhandled = True
                report.falsification = self._unhandled_falsification(report)
                return report

        # `scanned` stays False on the early return, so an empty report
        # cannot answer passed=True.
        report.scanned = True

        # Static AST pass (always available; no subprocess dependency)
        try:
            report.findings.extend(_run_gui_static(target))
            report.tool_availability["gui-static"] = "ok"
        except Exception as e:
            report.tool_availability["gui-static"] = "error"
            report.errors.append(f"gui-static: {type(e).__name__}: {e}")

        # Ruff pass
        for tool_name, runner in [
            ("ruff", self._run_ruff),
            ("bandit", self._run_bandit),
        ]:
            try:
                findings, status = runner(target)
                report.findings.extend(findings)
                report.tool_availability[tool_name] = status
            except FileNotFoundError:
                report.tool_availability[tool_name] = "missing"
                report.errors.append(f"{tool_name}: not installed")
            except subprocess.TimeoutExpired:
                report.tool_availability[tool_name] = "error"
                report.errors.append(f"{tool_name}: timed out")
            except Exception as e:
                report.tool_availability[tool_name] = "error"
                report.errors.append(f"{tool_name}: {type(e).__name__}: {e}")

        scan_rule_modules(
            report,
            target,
            (
                ("scaffolding", "dev_harness.harness.rules.scaffolding"),
                ("hallucination", "dev_harness.harness.rules.hallucination"),
            ),
            (".py",),
        )

        scan_geometry_drift(
            target,
            self.geometry_reference(),
            self.geometry_reshaped,
            report,
        )

        report.falsification = self._build_falsification(report)
        return report

    def _review_javascript(
        self, target: Path, report: ArchetypeReport
    ) -> ArchetypeReport:
        """Grade one JavaScript renderer module with `js_screen`.

        `ruff` and `bandit` read Python only and are not run here; a
        source `js_screen.tokenize` cannot finish leaves `scanned` False.
        """
        try:
            source = target.read_text(encoding="utf-8", errors="replace")
            for rf in js_screen.scan(target, source):
                report.findings.append(
                    Finding(
                        tool=rf.tool,
                        severity=rf.severity,
                        file=rf.file,
                        line=rf.line,
                        rule_id=rf.rule_id,
                        message=rf.message,
                    )
                )
            report.scanned = True
            report.tool_availability["gui-js"] = "ok"
        except js_screen.JsParseError as e:
            report.tool_availability["gui-js"] = "error"
            report.errors.append(f"gui-js: {target.name} did not tokenize: {e}")
        except OSError as e:
            report.tool_availability["gui-js"] = "error"
            report.errors.append(f"gui-js: {type(e).__name__}: {e}")

        self._run_web_tool(report, "eslint", web_analyzers.run_eslint, target)

        scan_rule_modules(report, target, _TEXT_RULE_MODULES, (".js",))
        scan_geometry_drift(
            target,
            self.geometry_reference(),
            self.geometry_reshaped,
            report,
        )
        report.falsification = self._javascript_falsification(report)
        return report

    def _review_css(self, target: Path, report: ArchetypeReport) -> ArchetypeReport:
        """Grade one style sheet with stylelint.

        `gui-static`, `ruff` and `bandit` read Python only and do not run.
        """
        self._run_web_tool(report, "stylelint", web_analyzers.run_stylelint, target)
        scan_rule_modules(report, target, _TEXT_RULE_MODULES, (".css",))
        report.falsification = self._web_falsification(report, "stylelint")
        return report

    def _review_html(self, target: Path, report: ArchetypeReport) -> ArchetypeReport:
        """Grade one page with html-validate.

        `gui-static`, `ruff` and `bandit` read Python only and do not run.
        """
        self._run_web_tool(
            report, "html-validate", web_analyzers.run_html_validate, target
        )
        scan_rule_modules(report, target, _TEXT_RULE_MODULES, (".html", ".htm"))
        report.falsification = self._web_falsification(report, "html-validate")
        return report

    @staticmethod
    def _run_web_tool(
        report: ArchetypeReport,
        tool_name: str,
        runner: Callable[[Path], tuple[list[Finding], str]],
        target: Path,
    ) -> None:
        """Record one web analyzer's findings and status on `report`.

        `scanned` is set only when `runner` returned, so an absent
        analyzer leaves an empty report that cannot answer passed=True.
        """
        try:
            findings, status = runner(target)
            report.findings.extend(findings)
            report.tool_availability[tool_name] = status
            report.scanned = True
        except FileNotFoundError as e:
            report.tool_availability[tool_name] = "missing"
            report.errors.append(f"{tool_name}: not installed: {e}")
        except subprocess.TimeoutExpired:
            report.tool_availability[tool_name] = "error"
            report.errors.append(f"{tool_name}: timed out")
        except Exception as e:
            report.tool_availability[tool_name] = "error"
            report.errors.append(f"{tool_name}: {type(e).__name__}: {e}")

    @staticmethod
    def _web_falsification(report: ArchetypeReport, tool: str) -> str:
        """State what would prove a `stylelint` or `html-validate` report wrong."""
        return (
            f"This report is wrong if: (a) {tool} read a configuration other "
            f"than the one at the repo root, so a different rule set graded "
            f"{report.target!r}; (b) the defect in this file is expressed in a "
            f"language {tool} does not read -- the JavaScript a page loads, or "
            f"the markup a style sheet targets -- none of which was examined "
            f"here; (c) a selector or element this file declares is dead "
            f"because nothing references it, which no rule here measures; "
            f"(d) any of the {len(report.findings)} listed findings is not a "
            f"real defect when a human reads the file."
        )

    @staticmethod
    def _javascript_falsification(report: ArchetypeReport) -> str:
        """State what would prove a `gui-js` report wrong."""
        return (
            f"This JavaScript report is wrong if: (a) {report.target!r} builds a "
            "control through a path js_screen.element_calls does not resolve -- a "
            "tag or props argument that is not a string literal, a module-level "
            "string constant, or an object variable with a literal initialiser in "
            "the same function -- in which case NO rule graded that control; "
            "(b) a control this names as unlabelled or inert is reached by a "
            "delegated listener registered outside the module, which js_screen "
            "does not follow; (b2) eslint read eslint.config.mjs at the repo "
            "root, so a rule that config does not enable found nothing here; "
            "(c) ruff, bandit, mypy and the other Python "
            "analyzers would have found a defect here, none of which read "
            "JavaScript and none of which ran; (d) any of the "
            f"{len(report.findings)} listed findings is a false positive when a "
            "human reads the module."
        )

    @staticmethod
    def _unhandled_falsification(report: ArchetypeReport) -> str:
        """State what would prove an `unhandled` GUI verdict wrong."""
        return (
            f"This report is wrong if {report.target!r} is not "
            f"{report.language}, or if this archetype in fact carries an "
            f"analyzer that reads {report.language}. NO ANALYZER RAN, so "
            f"this report says nothing about the file's quality and is not "
            f"a pass; it records that the file type has no checker here."
        )

    def _build_falsification(self, report: ArchetypeReport) -> str:
        """State the concrete conditions under which this GUI report is wrong."""
        ok_tools = [t for t, s in report.tool_availability.items() if s == "ok"]
        missing = [t for t, s in report.tool_availability.items() if s == "missing"]
        parts = [
            "This GUI report is wrong if:",
            f"(a) any tool marked 'ok' ({', '.join(ok_tools) or 'none'}) "
            "produced non-parseable output that the archetype silently dropped;",
            f"(b) the target widget file {report.target!r} was modified after review;",
            "(c) the AST-based accessibility check missed a setAccessibleName / "
            "setAccessibleDescription / setToolTip / setWhatsThis call reachable at runtime "
            "(e.g., inherited from a base widget or set via a helper method);",
            "(d) a QLayout is installed via a code path the AST didn't recognize "
            "(e.g., dynamic layout composition via setattr);",
            "(d2) a widget class inherits from a Qt widget this archetype does "
            "not name in _QT_WIDGET_BASES and does not reach one through a "
            "SAME-MODULE base, in which case no GUI rule graded it at all "
            "(cross-module local base classes are NOT resolved);",
            "(d3) GUI006 named a test that does verify a rendered pixel by a "
            "route _PIXEL_CONSTRUCTS does not list, or stayed silent on a test "
            "that reads a live colour through a helper defined outside the "
            "test function;",
        ]
        if _GEOMETRY_TOOL in report.tool_availability:
            parts.append(
                f"(d4) the {_GEOMETRY_TOOL} reading is wrong if a slot's size "
                f"moved for a reason outside the tree it was held against -- a "
                f"font this host has and the reference run did not, a window "
                f"other than "
                f"{' and '.join(f'{w}x{h}' for w, h in _GEOMETRY_WINDOWS)}, or a "
                f"module outside "
                f"{', '.join(sorted(_GEOMETRY_SCREEN_FILES))} that the row's "
                f"width also depends on; it discriminates "
                f"{_GEOMETRY_CALIBRATION_BAD} from "
                f"{_GEOMETRY_CALIBRATION_GOOD} on the header row, and a run "
                f"where it no longer does is a blind rule;"
            )
        if missing:
            parts.append(
                f"(e) any tool marked 'missing' was in fact installed and "
                f"reachable at review time ({', '.join(missing)});"
            )
        parts.append(
            f"(f) any of the {len(report.findings)} listed findings is a "
            "false positive when a human inspects the widget in a running Qt app."
        )
        return " ".join(parts)

    @staticmethod
    def _module_absent(proc: subprocess.CompletedProcess, tool: str) -> bool:
        """True when `python -m <tool>` failed because the module is gone.

        v3.24.34 (C43 follow-on). `python -m <tool>` on an absent module
        does NOT raise FileNotFoundError — the interpreter writes "No
        module named X" to stderr, exits non-zero, and leaves stdout
        EMPTY. Both runners below then took their
        `if not proc.stdout.strip(): return findings, "ok"` path and
        reported a clean run, so uninstalling ruff turned this archetype
        green while it checked nothing.

        NOTE: this is the third copy of this check (see
        coding_archetype._module_absent and the vale/proselint guards in
        docs_archetype). Consolidating them into one shared helper is
        docketed — it is a cross-module refactor and does not belong in
        the middle of this cascade.
        """
        if proc.returncode == 0:
            return False
        return f"No module named {tool}" in (proc.stderr or "")

    # Rules that are defects in source and correct practice in a test.
    _TEST_FILE_EXEMPT = (
        "S101",  # assert -- the mechanism pytest is built on
        "S105",  # hardcoded password -- fixture credentials are fake
        "S106",  # ditto, as a keyword argument
        "PLR2004",  # magic value in comparison -- expected values ARE literal
        "SLF001",  # private member access -- tests verify internals
    )

    @staticmethod
    def _is_test_file(target: Path) -> bool:
        name = target.name
        return (
            name.startswith("test_")
            or name.endswith("_test.py")
            or "tests" in target.parts
        )

    def _run_ruff(self, target: Path) -> tuple[list[Finding], str]:
        # Use a curated GUI-relevant selection (not --select=ALL which produces noise)
        cmd = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--output-format=json",
            "--no-cache",
            "--select=F,E,W,B,S,ANN,D",
        ]
        if self._is_test_file(target):
            cmd.append("--ignore=" + ",".join(self._TEST_FILE_EXEMPT))
        cmd.append(str(target))
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if self._module_absent(proc, "ruff"):
            return [], "missing"
        refuse_silent_failure(proc, "ruff")
        findings: list[Finding] = []
        if not proc.stdout.strip():
            return findings, "ok"
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return findings, "ok"
        for item in data:
            code = item.get("code") or "no-code"
            fam = code[0] if code and code[0].isalpha() else "?"
            sev_map = {
                "F": "medium",
                "E": "medium",
                "W": "low",
                "S": "high",
                "B": "medium",
                "ANN": "medium",
                "D": "low",
            }
            severity = sev_map.get(fam if fam != "A" else "ANN", "low")
            if code.startswith("ANN"):
                severity = "medium"
            elif code.startswith("D"):
                severity = "low"
            loc = item.get("location", {})
            findings.append(
                Finding(
                    tool="ruff",
                    severity=severity,
                    file=item.get("filename", str(target)),
                    line=loc.get("row", 0),
                    rule_id=code,
                    message=item.get("message", ""),
                )
            )
        return findings, "ok"

    def _run_bandit(self, target: Path) -> tuple[list[Finding], str]:
        proc = subprocess.run(
            # Without `-r` bandit given a directory scans no file and exits 0
            # with an empty results array.
            [sys.executable, "-m", "bandit", "-f", "json", "-q", "-r", str(target)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if self._module_absent(proc, "bandit"):
            return [], "missing"
        refuse_silent_failure(proc, "bandit")
        findings: list[Finding] = []
        if not proc.stdout.strip():
            return findings, "ok"
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"bandit produced non-JSON output: {e}")
        sev_map = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
        # B101 is dropped under tests/ only. Every other bandit rule still
        # fires there, and a production assert still surfaces.
        _in_tests = "/tests/" in str(target).replace("\\", "/")
        for issue in data.get("results", []):
            rule_id = issue.get("test_id", "unknown")
            if _in_tests and rule_id == "B101":
                continue
            severity = _BANDIT_SEVERITY_OVERRIDES.get(
                rule_id, sev_map.get(issue.get("issue_severity", ""), "medium")
            )
            findings.append(
                Finding(
                    tool="bandit",
                    severity=severity,
                    file=issue.get("filename", str(target)),
                    line=issue.get("line_number", 0),
                    rule_id=rule_id,
                    message=issue.get("issue_text", ""),
                )
            )
        return findings, "ok"


def _flag(argv: list[str], name: str, fallback: str = "") -> str:
    """The value written after `name` on the command line, or `fallback`."""
    if name not in argv:
        return fallback
    at = argv.index(name) + 1
    return argv[at] if at < len(argv) else fallback


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python -m dev_harness.harness.gui_archetype <path>")
        print("       .py  reviews PySide6 GUI code with gui-static + ruff + bandit")
        print("       .js  reviews a React renderer module with gui-js")
        print("       --against <commit>   the reference the geometry rule reads")
        print("       --reshaped <slots>   comma-separated slots allowed to resize")
        return 2
    if "--emit-geometry" in argv:
        tree = _flag(argv, "--tree")
        if tree:
            sys.path.insert(0, tree)
        return emit_geometry(
            _flag(argv, "--emit-geometry"),
            _flag(argv, "--variant", "qt"),
            int(_flag(argv, "--width", str(_GEOMETRY_WINDOW_W))),
            int(_flag(argv, "--height", str(_GEOMETRY_WINDOW_H))),
            Path(tree) if tree else None,
        )
    target = Path(argv[0])
    named = _flag(argv, "--reshaped")
    archetype = GUIArchetype(
        against=_flag(argv, "--against") or None,
        reshaped=frozenset(one for one in named.split(",") if one),
    )
    report = archetype.review(target)
    print(json.dumps(report.to_dict(), indent=2))
    return cli_exit(report)


if __name__ == "__main__":
    sys.exit(main())
