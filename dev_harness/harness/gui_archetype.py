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
import subprocess
import sys
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
    return findings


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
    )
    calibration_name = "gui"

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


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python -m dev_harness.harness.gui_archetype <path>")
        print("       .py  reviews PySide6 GUI code with gui-static + ruff + bandit")
        print("       .js  reviews a React renderer module with gui-js")
        return 2
    target = Path(argv[0])
    report = GUIArchetype().review(target)
    print(json.dumps(report.to_dict(), indent=2))
    return cli_exit(report)


if __name__ == "__main__":
    sys.exit(main())
