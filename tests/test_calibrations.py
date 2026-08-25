"""Pin tests for tools/harness/calibrations/__init__.py.

Verifies the calibration loader public API and that all three shipped
calibrations are present + non-empty + non-trivial.
"""

from __future__ import annotations

import pytest

from tools.harness import calibrations


class TestApi:
    def test_available_lists_shipped_three(self):
        avail = calibrations.available()
        assert set(avail) == {"coding", "gui", "docs"}, avail

    def test_available_is_sorted(self):
        avail = calibrations.available()
        assert avail == sorted(avail)


class TestLoad:
    def test_load_coding_returns_content(self):
        text = calibrations.load("coding")
        assert isinstance(text, str)
        assert len(text) > 500
        assert "coding" in text.lower()

    def test_load_gui_returns_content(self):
        text = calibrations.load("gui")
        assert isinstance(text, str)
        assert len(text) > 500
        # GUI cal should reference PySide6 or WCAG
        low = text.lower()
        assert "pyside6" in low or "wcag" in low or "accessibility" in low

    def test_load_docs_returns_content(self):
        text = calibrations.load("docs")
        assert isinstance(text, str)
        assert len(text) > 500
        low = text.lower()
        assert "diataxis" in low or "google" in low or "microsoft" in low

    def test_load_missing_raises_filenotfound(self):
        with pytest.raises(FileNotFoundError) as ei:
            calibrations.load("does_not_exist")
        # Error message must be helpful — list what IS available
        msg = str(ei.value)
        assert "does_not_exist" in msg
        assert "coding" in msg or "gui" in msg or "docs" in msg


class TestContent:
    """The shipped calibrations must include the anchors archetypes
    depend on. If a calibration is rewritten to drop these anchors,
    the peer-review prompt shape becomes ambiguous."""

    def test_all_calibrations_include_severity_section(self):
        for name in calibrations.available():
            text = calibrations.load(name)
            assert "severity" in text.lower(), f"{name}.md missing severity conventions"

    def test_all_calibrations_include_output_shape(self):
        for name in calibrations.available():
            text = calibrations.load(name)
            assert "json" in text.lower(), f"{name}.md missing output-shape section"

    def test_all_calibrations_note_500_word_cap(self):
        for name in calibrations.available():
            text = calibrations.load(name)
            assert (
                "500 words" in text.lower() or "500-word" in text.lower()
            ), f"{name}.md missing 500-word cap for peer reviewers"
