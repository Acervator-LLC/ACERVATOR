"""The coding archetype must know what language it is looking at.

Every analyzer the archetype drives is a Python analyzer, and none of
them refuses a file that is not Python. Handed one JavaScript file,
ruff reported thousands of findings against JavaScript syntax and
vulture raised "unterminated string literal" on a `//` comment holding
an apostrophe. The verdict was a red gate for reasons that described
nothing in the file, and sixty-two JavaScript files in this tree were
ungateable that way.

These tests pin three things:

  1. detection answers the language of a file,
  2. a file whose language has no analyzer here is UNHANDLED, which is
     a third answer beside passed and failed and is never green,
  3. a `.py` file reaches exactly the analyzers it always reached --
     the identity that makes this change safe to land.
"""

from __future__ import annotations

import pytest

from dev_harness.harness.coding_archetype import (
    HANDLED_LANGUAGES,
    UNKNOWN_LANGUAGE,
    CodingArchetype,
    detect_language,
    main,
)
from dev_harness.harness.report import ArchetypeReport

PYTHON_ANALYZERS = ("ruff", "mypy", "pyright", "bandit", "vulture", "semgrep")

# The comment shape that made vulture read a JavaScript file as an
# unclosed Python string.
APOSTROPHE_COMMENT_JS = (
    "// Built from COMMA and SPACE so the pair is not the surface's own\n"
    "const parts = [];\n"
    "export function render() {\n"
    "  return parts.join(', ');\n"
    "}\n"
)


class TestSuffixDecides:
    def test_a_dot_py_file_is_python(self, tmp_path):
        assert detect_language(tmp_path / "mod.py") == "python"

    def test_a_dot_js_file_is_javascript(self, tmp_path):
        assert detect_language(tmp_path / "widget.js") == "javascript"

    @pytest.mark.parametrize("suffix", [".mjs", ".cjs", ".jsx"])
    def test_the_other_javascript_suffixes_are_javascript(self, suffix, tmp_path):
        assert detect_language(tmp_path / f"widget{suffix}") == "javascript"

    def test_a_suffix_is_read_case_insensitively(self, tmp_path):
        assert detect_language(tmp_path / "WIDGET.JS") == "javascript"

    def test_a_pyinstaller_spec_is_python(self, tmp_path):
        """A spec file is Python the build execs, and every analyzer
        read it before detection existed. Classing it as anything else
        would drop coverage this change is not allowed to drop."""
        assert detect_language(tmp_path / "Acervator_win.spec") == "python"

    def test_markdown_is_not_python(self, tmp_path):
        """The docs archetype owns markdown; this one carries no reader
        for it, and saying so is the point of the language field."""
        assert detect_language(tmp_path / "notes.md") == "markdown"


class TestContentDecidesWhenTheSuffixCannot:
    def test_a_node_shebang_names_javascript(self, tmp_path):
        script = tmp_path / "runner"
        script.write_text("#!/usr/bin/env node\nconsole.log(1);\n", encoding="utf-8")
        assert detect_language(script) == "javascript"

    def test_a_python_shebang_names_python(self, tmp_path):
        script = tmp_path / "runner"
        script.write_text("#!/usr/bin/env python3\nx = 1\n", encoding="utf-8")
        assert detect_language(script) == "python"

    def test_a_versioned_interpreter_is_the_same_interpreter(self, tmp_path):
        script = tmp_path / "runner"
        script.write_text("#!/usr/bin/python3.14\nx = 1\n", encoding="utf-8")
        assert detect_language(script) == "python"

    def test_a_shell_shebang_names_shell(self, tmp_path):
        script = tmp_path / "install"
        script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
        assert detect_language(script) == "shell"

    def test_a_file_neither_signal_places_is_unknown(self, tmp_path):
        """The safe direction. An unplaceable file is declined, not
        handed to a Python parser."""
        script = tmp_path / "runner"
        script.write_text("nothing here names a language\n", encoding="utf-8")
        assert detect_language(script) == UNKNOWN_LANGUAGE

    def test_an_undecodable_file_is_unknown_rather_than_an_exception(self, tmp_path):
        blob = tmp_path / "payload"
        blob.write_bytes(bytes(range(256)))
        assert detect_language(blob) == UNKNOWN_LANGUAGE

    def test_a_missing_file_is_unknown_rather_than_an_exception(self, tmp_path):
        assert detect_language(tmp_path / "absent") == UNKNOWN_LANGUAGE


def test_a_dot_py_suffix_outranks_a_contradicting_shebang(tmp_path):
    """Content may never divert a `.py` file away from the analyzers.

    If this fails, detection has become able to reclassify Python, and
    the Python path is no longer the path it was before detection
    existed -- every other guarantee here rests on this one.
    """
    module = tmp_path / "mod.py"
    module.write_text("#!/usr/bin/env node\nx = 1\n", encoding="utf-8")
    assert detect_language(module) == "python"
    assert detect_language(module) in HANDLED_LANGUAGES


class TestUnhandledIsNotPassed:
    """The verdict surface a caller reads."""

    def test_an_unhandled_report_is_not_green(self):
        report = ArchetypeReport(
            target="widget.js",
            language="javascript",
            unhandled=True,
            tool_availability={"ruff": "ok"},
            scanned=True,
        )
        assert report.passed is False, (
            "an unhandled file type answered green; nothing examined it, "
            "so this would rubber-stamp every such file"
        )

    def test_a_scanned_python_report_is_still_green(self):
        """The control for the test above: the same report with
        `unhandled` cleared must pass, or the field proves nothing."""
        report = ArchetypeReport(
            target="mod.py",
            language="python",
            unhandled=False,
            tool_availability={"ruff": "ok"},
            scanned=True,
        )
        assert report.passed is True

    def test_an_unhandled_report_names_the_language_with_no_analyzer(self):
        report = ArchetypeReport(
            target="widget.js", language="javascript", unhandled=True
        )
        reasons = " ".join(report.why_not_green())
        assert "javascript" in reasons, reasons

    def test_the_report_publishes_unhandled_and_passed_as_separate_keys(self):
        """A caller must be able to tell "checked and clean" from "no
        checker for this file type"."""
        payload = ArchetypeReport(
            target="widget.js", language="javascript", unhandled=True
        ).to_dict()
        assert payload["unhandled"] is True
        assert payload["passed"] is False
        assert payload["language"] == "javascript"

    def test_a_clean_python_report_is_distinguishable_from_an_unhandled_one(self):
        payload = ArchetypeReport(
            target="mod.py",
            language="python",
            tool_availability={"ruff": "ok"},
            scanned=True,
        ).to_dict()
        assert payload["unhandled"] is False
        assert payload["passed"] is True

    def test_the_cli_exits_one_on_a_javascript_target(self, tmp_path, capsys):
        widget = tmp_path / "widget.js"
        widget.write_text(APOSTROPHE_COMMENT_JS, encoding="utf-8")
        assert main([str(widget)]) == 1
        assert "javascript" in capsys.readouterr().err


@pytest.fixture(scope="module")
def javascript_report(tmp_path_factory) -> ArchetypeReport:
    widget = tmp_path_factory.mktemp("js") / "widget.js"
    widget.write_text(APOSTROPHE_COMMENT_JS, encoding="utf-8")
    return CodingArchetype().review(widget)


@pytest.fixture(scope="module")
def python_report(tmp_path_factory) -> ArchetypeReport:
    module = tmp_path_factory.mktemp("py") / "mod.py"
    module.write_text('"""A clean module."""\n\nVALUE: int = 1\n', encoding="utf-8")
    return CodingArchetype().review(module)


class TestTheAnalyzersAreWithheldFromJavaScript:
    def test_a_python_file_reaches_every_python_analyzer(self, python_report):
        """The positive control. Without it, the emptiness asserted in
        the next test could mean the instrument reads nothing at all."""
        assert set(PYTHON_ANALYZERS) <= set(python_report.tool_availability), (
            f"a Python file reached only "
            f"{sorted(python_report.tool_availability)}; the assertion in "
            f"the next test would then be vacuous"
        )

    def test_a_javascript_file_reaches_none_of_them(self, javascript_report):
        reached = set(PYTHON_ANALYZERS) & set(javascript_report.tool_availability)
        assert not reached, (
            f"{sorted(reached)} ran over a JavaScript file; every one of "
            f"them parses its input as Python"
        )

    def test_a_javascript_file_yields_no_findings(self, javascript_report):
        assert javascript_report.findings == [], (
            "findings against a JavaScript file can only come from a "
            f"Python parser reading it: {javascript_report.findings[:3]}"
        )

    def test_the_apostrophe_comment_no_longer_crashes_a_tool(self, javascript_report):
        """The exact shape that raised "unterminated string literal"."""
        assert javascript_report.errors == [], javascript_report.errors

    def test_a_javascript_file_is_reported_unhandled(self, javascript_report):
        assert javascript_report.unhandled is True
        assert javascript_report.language == "javascript"
        assert javascript_report.passed is False

    def test_a_python_file_is_not_reported_unhandled(self, python_report):
        assert python_report.unhandled is False
        assert python_report.language == "python"

    def test_an_unhandled_report_states_that_nothing_ran(self, javascript_report):
        assert "NO ANALYZER RAN" in javascript_report.falsification


def test_a_directory_target_keeps_the_existing_path(tmp_path):
    """Detection is for files. Every analyzer here self-filters to
    `.py` when handed a directory, so a mixed tree is already correct
    and must not start reporting unhandled."""
    (tmp_path / "mod.py").write_text('"""Doc."""\n\nVALUE: int = 1\n', encoding="utf-8")
    (tmp_path / "widget.js").write_text(APOSTROPHE_COMMENT_JS, encoding="utf-8")
    report = CodingArchetype().review(tmp_path)
    assert report.unhandled is False
    assert report.scanned is True
    assert set(PYTHON_ANALYZERS) <= set(report.tool_availability)


def test_an_absent_target_is_not_reported_unhandled(tmp_path):
    """A path that does not exist is a different fault from a file type
    with no analyzer, and the report must not blur them."""
    report = CodingArchetype().review(tmp_path / "absent.js")
    assert report.unhandled is False
    assert report.passed is False
    assert any("not found" in e for e in report.errors), report.errors


def test_every_declared_handled_language_has_a_suffix_that_maps_to_it(tmp_path):
    """`HANDLED_LANGUAGES` is a claim that the runners read that
    language. A name in it that no file can ever carry would make the
    claim unreachable."""
    reachable = {detect_language(tmp_path / f"probe{s}") for s in (".py", ".pyi")}
    assert HANDLED_LANGUAGES <= reachable
