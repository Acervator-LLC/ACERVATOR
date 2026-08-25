"""Pin tests for tools/harness/gui_archetype.py.

Verifies:
  - Module + public surface (GUIArchetype, GUI001-GUI005 rules)
  - passed=True on known_good_widget.py; passed=False on known_bad_widget.py
  - All 6 ground-truth defects (G1-G6) surface correctly
  - falsification populated
  - calibration loads
  - AST analyzer signal-wiring tracking correctness (GUI005 edge cases)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tools.harness.gui_archetype import (
    GUIArchetype,
    _GUIAnalyzer,
    _INTERACTIVE_QT_WIDGETS,
    _INTERACTIVE_SIGNALS,
    _ACCESSIBLE_SETTER_METHODS,
    _QT_WIDGET_BASES,
)

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "docs" / "audits" / "2026-07-24_gui_docs_archetypes" / "gui_fixtures"


class TestSurface:
    def test_archetype_class_exists(self):
        arch = GUIArchetype()
        assert arch.name == "gui_quality"
        assert arch.version.startswith("1.")
        assert arch.calibration_name == "gui"

    def test_interactive_widget_set_populated(self):
        assert "QPushButton" in _INTERACTIVE_QT_WIDGETS
        assert "QLineEdit" in _INTERACTIVE_QT_WIDGETS
        assert "QComboBox" in _INTERACTIVE_QT_WIDGETS

    def test_accessible_setter_methods_populated(self):
        assert "setAccessibleName" in _ACCESSIBLE_SETTER_METHODS
        assert "setAccessibleDescription" in _ACCESSIBLE_SETTER_METHODS

    def test_interactive_signals_populated(self):
        for sig in (
            "clicked",
            "returnPressed",
            "textChanged",
            "valueChanged",
            "toggled",
            "triggered",
        ):
            assert sig in _INTERACTIVE_SIGNALS, f"missing signal: {sig}"

    def test_qt_widget_bases_include_qwidget(self):
        assert "QWidget" in _QT_WIDGET_BASES
        assert "QDialog" in _QT_WIDGET_BASES


class TestFixturesExist:
    def test_known_good_widget(self):
        assert (FIX / "known_good_widget.py").is_file()

    def test_known_bad_widget(self):
        assert (FIX / "known_bad_widget.py").is_file()


class TestReviewGates:
    def test_known_good_passes(self):
        report = GUIArchetype().review(FIX / "known_good_widget.py")
        assert report.passed is True
        # gui-static should produce zero findings on the clean fixture
        gui_findings = [f for f in report.findings if f.tool == "gui-static"]
        assert gui_findings == [], (
            f"gui-static should be silent on known_good, got: "
            f"{[(f.rule_id, f.message) for f in gui_findings]}"
        )

    def test_known_bad_fails(self):
        report = GUIArchetype().review(FIX / "known_bad_widget.py")
        assert report.passed is False


class TestGroundTruthRecall:
    """All 6 labeled defects (G1-G6) in known_bad_widget.py must fire."""

    @pytest.fixture(scope="class")
    def report(self):
        return GUIArchetype().review(FIX / "known_bad_widget.py")

    def test_G1_no_accessible_name(self, report):
        hits = [f for f in report.findings if f.rule_id == "GUI001"]
        assert hits, "G1 (no accessible name) not caught by GUI001"
        assert hits[0].severity == "high"

    def test_G2_missing_docstring(self, report):
        hits = [f for f in report.findings if f.rule_id == "GUI002"]
        assert hits, "G2 (missing docstring) not caught by GUI002"

    def test_G3_absolute_positioning(self, report):
        hits = [f for f in report.findings if f.rule_id == "GUI003"]
        assert hits, "G3 (absolute positioning) not caught by GUI003"
        assert all(f.severity == "high" for f in hits)

    def test_G4_child_widget_no_parent(self, report):
        hits = [f for f in report.findings if f.rule_id == "GUI004"]
        assert hits, "G4 (child widget without parent) not caught by GUI004"

    def test_G5_hardcoded_password_high(self, report):
        # bandit B105 or ruff S105 remapped to high
        hits = [f for f in report.findings if f.rule_id in ("B105", "S105")]
        assert hits, "G5 (hardcoded password) not caught"
        assert any(f.severity == "high" for f in hits)

    def test_G6_signal_wiring(self, report):
        hits = [f for f in report.findings if f.rule_id == "GUI005"]
        # Bad fixture has TWO unwired interactive widgets (input + submit)
        assert (
            len(hits) == 2
        ), f"G6 (signal wiring) expected 2 GUI005 findings, got {len(hits)}"


class TestFalsification:
    def test_falsification_populated(self):
        report = GUIArchetype().review(FIX / "known_bad_widget.py")
        assert report.falsification
        assert (
            "gui-static" in report.falsification.lower()
            or "accessibility" in report.falsification.lower()
        )


class TestCalibration:
    def test_load_calibration(self):
        text = GUIArchetype().load_calibration()
        assert "wcag" in text.lower() or "pyside6" in text.lower()


class TestAnalyzerEdgeCases:
    """GUI005 correctness: instantiations must be tracked AS assignments to
    self.<attr>, and only wired if a matching .<signal>.connect(...) exists
    that receives from self.<attr>."""

    def _analyze(self, source: str) -> list:
        tree = ast.parse(source)
        analyzer = _GUIAnalyzer("<test>")
        analyzer.visit(tree)
        return analyzer.findings

    def test_wired_button_produces_no_gui005(self):
        source = """
from PySide6.QtWidgets import QWidget, QPushButton

class W(QWidget):
    '''A widget with proper wiring.'''
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("W")
        self._btn = QPushButton("Go", self)
        self._btn.setAccessibleName("Go")
        self._btn.clicked.connect(self._on_click)
        from PySide6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(self)
        layout.addWidget(self._btn)
    def _on_click(self): pass
"""
        findings = self._analyze(source)
        gui005 = [f for f in findings if f.rule_id == "GUI005"]
        assert gui005 == [], f"wired button should not GUI005: {gui005}"

    def test_unwired_button_fires_gui005(self):
        source = """
from PySide6.QtWidgets import QWidget, QPushButton, QVBoxLayout

class W(QWidget):
    '''Unwired button.'''
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("W")
        self._btn = QPushButton("Go", self)
        self._btn.setAccessibleName("Go")
        layout = QVBoxLayout(self)
        layout.addWidget(self._btn)
"""
        findings = self._analyze(source)
        gui005 = [f for f in findings if f.rule_id == "GUI005"]
        assert len(gui005) == 1
        assert "_btn" in gui005[0].message

    def test_signal_wiring_only_counts_matching_receiver(self):
        """.clicked.connect on a LOCAL button doesn't count for self._btn."""
        source = """
from PySide6.QtWidgets import QWidget, QPushButton, QVBoxLayout

class W(QWidget):
    '''Local button wired; self._btn not.'''
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("W")
        local = QPushButton("Other", self)
        local.clicked.connect(self._x)   # NOT wiring self._btn
        self._btn = QPushButton("Mine", self)
        self._btn.setAccessibleName("Mine")
        layout = QVBoxLayout(self)
        layout.addWidget(self._btn)
    def _x(self): pass
"""
        findings = self._analyze(source)
        gui005 = [f for f in findings if f.rule_id == "GUI005"]
        assert len(gui005) == 1
        assert "_btn" in gui005[0].message
