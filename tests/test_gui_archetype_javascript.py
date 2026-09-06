"""The GUI archetype grades a React renderer module.

Each rule is pinned with the pair that separates it: a module carrying
the defect and a module differing only in the property the rule reads.
"""

from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest

from dev_harness.harness import js_screen
from dev_harness.harness.gui_archetype import GUIArchetype, main

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "harness_fixtures" / "gui_archetype"
GOOD_SCREEN = FIX / "known_good_screen.js"
BAD_SCREEN = FIX / "known_bad_screen.js"
WEB = REPO / "src" / "gui" / "web"

MODULE_HEAD = '(function (global) {\n  "use strict";\n'
MODULE_TAIL = "})(window);\n"


def module(body: str) -> str:
    """Wrap `body` in the IIFE every renderer module under `WEB` uses."""
    return MODULE_HEAD + body + MODULE_TAIL


def rules(path: Path, source: str) -> collections.Counter:
    """Return {rule_id: count} for `source`, scanned as `path`."""
    return collections.Counter(f.rule_id for f in js_screen.scan(path, source))


def review(path: Path):
    """Return the archetype's report for one target."""
    return GUIArchetype().review(path)


class TestTheArchetypeReachesJavaScript:
    def test_a_renderer_module_is_scanned_rather_than_declined(self):
        report = review(GOOD_SCREEN)
        assert report.language == "javascript", report.language
        assert report.unhandled is False, report.why_not_green()
        assert report.scanned is True, report.why_not_green()

    def test_the_javascript_analyzer_reports_its_own_availability(self):
        report = review(GOOD_SCREEN)
        assert report.tool_availability.get("gui-js") == "ok", (
            "gui-js must report its status; without it a silent run is "
            f"indistinguishable from a clean one: {report.tool_availability}"
        )

    def test_the_python_only_analyzers_do_not_claim_to_have_read_javascript(self):
        report = review(GOOD_SCREEN)
        assert "ruff" not in report.tool_availability, (
            "ruff parses JavaScript as Python and reports every line as a "
            "syntax error at severity low, which made the verdict a false "
            f"green: {report.tool_availability}"
        )
        assert "bandit" not in report.tool_availability

    def test_a_file_type_with_no_screen_analyzer_is_still_declined(self, tmp_path):
        target = tmp_path / "notes.txt"
        target.write_text("plain text\n", encoding="utf-8")
        report = review(target)
        assert report.unhandled is True
        assert report.passed is False

    def test_a_python_widget_still_gets_the_pyside_analyzers(self):
        report = review(FIX / "known_good_widget.py")
        assert report.language == "python"
        assert report.tool_availability.get("gui-static") == "ok"
        assert report.tool_availability.get("ruff") == "ok"
        assert report.passed is True, report.why_not_green()

    def test_a_python_widget_with_defects_still_fails(self):
        assert review(FIX / "known_bad_widget.py").passed is False


class TestTheFixturePair:
    def test_the_known_good_screen_has_no_finding(self):
        report = review(GOOD_SCREEN)
        assert report.findings == [], [f.to_dict() for f in report.findings]
        assert report.passed is True, report.why_not_green()

    def test_the_known_bad_screen_fires_every_shipped_rule(self):
        report = review(BAD_SCREEN)
        fired = collections.Counter(f.rule_id for f in report.findings)
        assert fired == {
            "GUIJS001": 1,
            "GUIJS002": 1,
            "GUIJS003": 1,
            "GUIJS004": 1,
        }, fired
        assert report.passed is False

    @pytest.mark.parametrize(("fixture", "code"), [(GOOD_SCREEN, 0), (BAD_SCREEN, 1)])
    def test_the_command_line_exit_code_matches_the_verdict(
        self, fixture, code, capsys
    ):
        assert main([str(fixture)]) == code
        printed = json.loads(capsys.readouterr().out)
        assert printed["language"] == "javascript"
        assert printed["passed"] is (code == 0)


class TestAnUnlabelledControl:
    BODY = """
  function element() { return global.React.createElement.apply(null, arguments); }
  function Field() {
    var fieldProps = { className: "row", value: "1" };
    fieldProps.onChange = function () { return null; };
    return element("input", fieldProps);
  }
  global.screen = Field;
"""

    def test_an_input_with_no_name_and_no_child_is_reported(self, tmp_path):
        found = rules(tmp_path / "m.js", module(self.BODY))
        assert found["GUIJS001"] == 1, found

    def test_the_same_input_with_an_aria_label_is_not_reported(self, tmp_path):
        named = self.BODY.replace(
            'var fieldProps = { className: "row", value: "1" };',
            'var fieldProps = { className: "row", value: "1" };\n'
            '    fieldProps["aria-label"] = "Amount";',
        )
        found = rules(tmp_path / "m.js", module(named))
        assert found["GUIJS001"] == 0, found


class TestAnInertControl:
    BODY = """
  function element() { return global.React.createElement.apply(null, arguments); }
  function Act() {
    var buttonProps = { className: "row", title: "Fire" };
    return element("button", buttonProps, "Go");
  }
  global.screen = Act;
"""

    def test_a_button_with_no_handler_is_reported(self, tmp_path):
        found = rules(tmp_path / "m.js", module(self.BODY))
        assert found["GUIJS002"] == 1, found

    def test_the_same_button_with_an_onclick_is_not_reported(self, tmp_path):
        wired = self.BODY.replace(
            'var buttonProps = { className: "row", title: "Fire" };',
            'var buttonProps = { className: "row", title: "Fire" };\n'
            "    buttonProps.onClick = function () { return null; };",
        )
        found = rules(tmp_path / "m.js", module(wired))
        assert found["GUIJS002"] == 0, found

    def test_a_data_action_attribute_is_not_a_handler(self, tmp_path):
        attributed = self.BODY.replace(
            'var buttonProps = { className: "row", title: "Fire" };',
            'var buttonProps = { className: "row", title: "Fire" };\n'
            '    buttonProps["data-action"] = "fire";',
        )
        found = rules(tmp_path / "m.js", module(attributed))
        assert found["GUIJS002"] == 1, (
            "data-action is written by the renderer modules and read by no "
            f"listener, so it does not wire the control: {found}"
        )


class TestAColourWrittenIntoAModule:
    def test_a_hex_colour_literal_is_reported(self, tmp_path):
        body = '  var style = { color: "#3366ff" };\n  global.style = style;\n'
        assert rules(tmp_path / "m.js", module(body))["GUIJS003"] == 1

    def test_a_colour_named_by_the_view_model_is_not_reported(self, tmp_path):
        body = "  var style = { color: model.accent };\n  global.style = style;\n"
        assert rules(tmp_path / "m.js", module(body))["GUIJS003"] == 0

    def test_an_issue_number_in_a_comment_is_not_read_as_a_colour(self, tmp_path):
        body = "  // React panel. Issue #128 units R4 and R6.\n  global.n = 1;\n"
        found = rules(tmp_path / "m.js", module(body))
        assert found["GUIJS003"] == 0, (
            "a hash token inside a comment is not a colour literal; the raw "
            f"text search over the shipped modules matches it and this must not: {found}"
        )


class TestAbsolutePositioning:
    def test_position_absolute_is_reported(self, tmp_path):
        body = '  var style = { position: "absolute", top: 4 };\n  global.s = style;\n'
        assert rules(tmp_path / "m.js", module(body))["GUIJS004"] == 1

    def test_position_relative_is_not_reported(self, tmp_path):
        body = '  var style = { position: "relative", top: 4 };\n  global.s = style;\n'
        assert rules(tmp_path / "m.js", module(body))["GUIJS004"] == 0

    def test_the_word_absolute_outside_a_position_key_is_not_reported(self, tmp_path):
        body = '  var mode = { rounding: "absolute" };\n  global.m = mode;\n'
        assert rules(tmp_path / "m.js", module(body))["GUIJS004"] == 0


class TestWhatTheAnalyzerDeclines:
    BODY = """
  function element() { return global.React.createElement.apply(null, arguments); }
  function Act(props) {
    return element("button", props.buttonProps, "Go");
  }
  global.screen = Act;
"""

    def test_a_control_whose_props_are_unreadable_draws_no_finding(self, tmp_path):
        found = rules(tmp_path / "m.js", module(self.BODY))
        assert found == {}, (
            "props reached through an expression are not resolved, and a rule "
            f"that fired on one would be guessing: {found}"
        )

    def test_a_props_variable_with_no_object_initialiser_is_declined(self, tmp_path):
        body = """
  function element() { return global.React.createElement.apply(null, arguments); }
  function Act() {
    var buttonProps = partProps("act");
    buttonProps.title = "Fire";
    return element("button", buttonProps, "Go");
  }
  global.screen = Act;
"""
        calls = js_screen.element_calls(js_screen.tokenize(module(body)))
        buttons = [c for c in calls if c.tag == "button"]
        assert buttons and buttons[0].props_resolved is False, calls
        assert rules(tmp_path / "m.js", module(body)) == {}

    def test_the_same_props_variable_with_an_object_initialiser_is_resolved(
        self, tmp_path
    ):
        body = """
  function element() { return global.React.createElement.apply(null, arguments); }
  function Act() {
    var buttonProps = { className: "row" };
    buttonProps.title = "Fire";
    return element("button", buttonProps, "Go");
  }
  global.screen = Act;
"""
        found = rules(tmp_path / "m.js", module(body))
        assert found["GUIJS002"] == 1, (
            "with the initialiser visible the analyzer must grade the control; "
            f"a pair that declines both ways would prove nothing: {found}"
        )


class TestASourceTheAnalyzerCannotRead:
    UNFINISHED = {
        "string cut by a newline": 'var a = "abc;\n',
        "string cut by the end of the source": 'var a = "abc',
        "template cut by the end of the source": "var a = `abc",
        "block comment cut by the end of the source": "/* abc",
        "regular expression cut by a newline": "var a = /abc\n",
        "regular expression cut by the end of the source": "var a = /abc",
    }

    @pytest.mark.parametrize("source", list(UNFINISHED.values()), ids=list(UNFINISHED))
    def test_an_unfinished_construct_stops_the_tokenizer(self, source):
        with pytest.raises(js_screen.JsParseError):
            js_screen.tokenize(source)

    @pytest.mark.parametrize("source", list(UNFINISHED.values()), ids=list(UNFINISHED))
    def test_an_unfinished_construct_is_an_error_and_not_a_pass(self, source, tmp_path):
        target = tmp_path / "broken.js"
        target.write_text(source, encoding="utf-8")
        report = review(target)
        assert report.scanned is False
        assert report.tool_availability.get("gui-js") == "error"
        assert report.passed is False, report.why_not_green()

    def test_a_readable_module_at_the_same_path_is_green(self, tmp_path):
        target = tmp_path / "broken.js"
        target.write_text(module("  global.n = 1;\n"), encoding="utf-8")
        report = review(target)
        assert report.scanned is True
        assert report.passed is True, report.why_not_green()


class TestTheTokenizerOverTheShippedModules:
    @pytest.fixture(scope="class")
    def shipped(self):
        found = [p for p in sorted(WEB.rglob("*.js")) if "vendor" not in p.parts]
        assert found, f"no renderer module found under {WEB}"
        return found

    def test_every_shipped_module_tokenizes(self, shipped):
        failed = []
        for path in shipped:
            try:
                js_screen.tokenize(path.read_text(encoding="utf-8"))
            except js_screen.JsParseError as exc:
                failed.append(f"{path.name}: {exc}")
        assert failed == [], failed

    def test_the_analyzer_resolves_a_control_in_the_shipped_modules(self, shipped):
        resolved = 0
        for path in shipped:
            for call in js_screen.element_calls(
                js_screen.tokenize(path.read_text(encoding="utf-8"))
            ):
                if call.tag in js_screen.INTERACTIVE_TAGS and call.props_resolved:
                    resolved += 1
        assert resolved > 50, (
            "the analyzer must reach the real screens; a low count means it "
            f"reads a shape the modules do not use: resolved={resolved}"
        )
