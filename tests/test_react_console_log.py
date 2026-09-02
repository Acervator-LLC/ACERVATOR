"""The React Console log body, against console_log_surface.py."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import console_log_surface as surface
from src.gui.main_tabs import console_tab_surface as parent
from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "console_log.js"
TOKENS_PATH = WEB / "design_tokens.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 500
READY_ROUNDS = 100
READY_STEP_MS = 100

#: A view never shown reads clientWidth as 0, so the host is sized.
HOST_WIDTH_PX = 600
HOST_HEIGHT_PX = 400

JS_TYPE_OF = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "tuple": "object",
    "list": "object",
    "dict": "object",
    "NoneType": "null",
}

MARKER = surface.HIGHLIGHT_MARKER

#: 200 characters in one word with no space, which a wrapping pane cannot break.
LONG_WORD = "z" * 200
#: The same length as one spaced line, which a pane can wrap at a space.
SPACED_LINE = " ".join(["word"] * 40)
MARKUP_LINE = "<img src='data:image/gif;base64,R0lGOD'><b>bold</b>"
NEWLINE_LINE = "first\nsecond"


def rec(level: Any, text: Any) -> dict:
    return {"level": level, "text": text}


LEVEL_RECORDS = [
    rec("DEBUG", "a debug message"),
    rec("INFO", "an info message"),
    rec("WARNING", "a warning message"),
    rec("ERROR", "an error message"),
    rec("CRITICAL", "a critical message"),
    rec("TRACE", "a level the map does not name"),
    rec("", "an empty level name"),
]

#: Each record's text says one colour and its level says another.
PRECEDENCE_RECORDS = [
    rec("ERROR", MARKER + " rsi 55"),
    rec("DEBUG", "before " + MARKER + " after"),
    rec("CRITICAL", MARKER),
    rec("INFO", MARKER.lower() + " in lower case"),
]

HELD_RECORDS = [rec("INFO", "held one"), rec("WARNING", "held two")]
FLOOD_RECORDS = [rec("INFO", "flood " + str(at)) for at in range(5)]

AT_CAP = 3
PAST_CAP = 2


def bridge_payload(*steps: dict, buffer_max: int = None) -> dict:
    """One payload from the surface, each step driving the same pause buffer in order."""
    cap = surface.BUFFER_MAX if buffer_max is None else buffer_max
    buffer = surface.ConsoleLogBuffer(cap)
    model = None
    for step in steps or ({},):
        model = surface.build_view_model(
            buffer,
            step.get("records") or [],
            paused=step.get("paused"),
            pane_empty=step.get("pane_empty", True),
            scroll_value=step.get("scroll_value", 0),
            scroll_max=step.get("scroll_max", 0),
        )
    return json.loads(json.dumps(model, ensure_ascii=True))


STATES = {
    "empty": {},
    "one": {"steps": ({"records": [rec("INFO", "a single message")]},)},
    "levels": {"steps": ({"records": LEVEL_RECORDS},)},
    "precedence": {"steps": ({"records": PRECEDENCE_RECORDS},)},
    "paused": {"steps": ({"paused": True}, {"records": HELD_RECORDS})},
    "at_cap": {
        "buffer_max": AT_CAP,
        "steps": ({"paused": True}, {"records": FLOOD_RECORDS[:AT_CAP]}),
    },
    "past_cap": {
        "buffer_max": PAST_CAP,
        "steps": ({"paused": True}, {"records": FLOOD_RECORDS}),
    },
    "resumed": {
        "buffer_max": PAST_CAP,
        "steps": (
            {"paused": True},
            {"records": FLOOD_RECORDS},
            {"paused": False},
        ),
    },
    "appended": {
        "steps": ({"records": HELD_RECORDS, "pane_empty": False},),
    },
    "long_line": {"steps": ({"records": [rec("INFO", LONG_WORD)]},)},
    "spaced_line": {"steps": ({"records": [rec("INFO", SPACED_LINE)]},)},
    "markup": {"steps": ({"records": [rec("ERROR", MARKUP_LINE)]},)},
    "followed": {
        "steps": ({"records": HELD_RECORDS, "scroll_value": 10, "scroll_max": 10},),
    },
}
STATE_NAMES = tuple(STATES)


def state_payload(name: str) -> dict:
    case = STATES[name]
    return bridge_payload(*case.get("steps", ()), buffer_max=case.get("buffer_max"))


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):
    """A QJSEngine holding ``console_log.js`` and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetConsoleLog"

    def raised(self, script: str) -> str:
        """The engine's error for ``script``, or an empty string."""
        result = self._engine.evaluate(script)
        return result.toString() if result.isError() else ""

    def load_tokens(self) -> None:
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_widgets(self) -> None:
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def named(self, method: str, name: str) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorConsoleLog." + method + "(JSON.parse(NAME))")

    def for_line(self, method: str, line: dict) -> Any:
        self.bind_json("LINE", line)
        return self.json("acervatorConsoleLog." + method + "(JSON.parse(LINE))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def skinned(js: JsRuntime) -> JsRuntime:
    """The module with the two modules it paints through already run."""
    js.load_tokens()
    js.load_widgets()
    return js


MODULE_READERS = {
    "buffer_max": "acervatorConsoleLog.bufferMax()",
    "buffered": "acervatorConsoleLog.buffered()",
    "default_level": "acervatorConsoleLog.defaultLevel()",
    "document": "acervatorConsoleLog.document()",
    "dropped": "acervatorConsoleLog.dropped()",
    "follow_tail": "acervatorConsoleLog.followTail()",
    "highlight_color": "acervatorConsoleLog.highlightColor()",
    "highlight_marker": "acervatorConsoleLog.highlightMarker()",
    "highlight_hex": "acervatorConsoleLog.highlightHex()",
    "level_colors": "acervatorConsoleLog.levelColors()",
    "level_order": "acervatorConsoleLog.levelOrder()",
    "level_hex": "acervatorConsoleLog.levelHex()",
    "paused": "acervatorConsoleLog.paused()",
}


def unreachable_fields(payload: dict) -> list:
    return sorted(set(payload) - set(MODULE_READERS))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    """A field with no answer is a value that stops at the bridge."""
    payload = state_payload(state)
    js.push(payload)
    missing = unreachable_fields(payload)
    assert not missing, f"{len(missing)} published fields have no answer: {missing}"
    extra = sorted(set(MODULE_READERS) - set(payload))
    assert not extra, f"the module answers for fields the surface has none of: {extra}"
    differing = {
        field: (payload[field], js.json(expression))
        for field, expression in MODULE_READERS.items()
        if js.json(expression) != payload[field]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields differ: "
        f"{sorted(differing)}"
    )
    assert len(MODULE_READERS) == len(payload)


def test_the_whole_payload_check_names_a_field_only_the_surface_holds():
    payload = dict(bridge_payload())
    payload["only_on_the_surface"] = []
    assert unreachable_fields(payload) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for():
    payload = dict(bridge_payload())
    dropped = payload.pop("level_order")
    assert dropped is not None
    assert sorted(set(MODULE_READERS) - set(payload)) == ["level_order"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = bridge_payload()
    payload["buffer_max"] += 1
    js.push(payload)
    original = bridge_payload()
    differing = sorted(
        field
        for field, expression in MODULE_READERS.items()
        if js.json(expression) != original[field]
    )
    assert differing == ["buffer_max"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["lines"] == len(payload["document"]["lines"])
    assert report["held"]["lines"] == len(payload["document"]["lines"])
    assert report["declared"]["levels"] == len(payload["level_order"])
    assert report["held"]["levels"] == len(payload["level_colors"])


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = bridge_payload()
    del payload["level_order"]
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(MODULE_READERS) - 1


def test_the_module_names_the_fields_the_surface_declares(js: JsRuntime):
    js.push(bridge_payload())
    assert sorted(js.json("acervatorConsoleLog.declaredFields()")) == sorted(
        bridge_payload()
    )


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_holds_every_line_the_surface_published(js: JsRuntime, state: str):
    """A line the surface produced that the module drops is a log line
    the operator would never read."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json("acervatorConsoleLog.lines()") == payload["document"]["lines"]
    assert js.json("acervatorConsoleLog.insertText()") == (
        payload["document"]["insert_text"]
    )


def test_the_line_check_names_a_dropped_line(js: JsRuntime):
    payload = state_payload("levels")
    dropped = payload["document"]["lines"].pop()
    js.push(payload)
    held = js.json("acervatorConsoleLog.lines()")
    original = state_payload("levels")["document"]["lines"]
    assert [one for one in original if one not in held] == [dropped]


PRECEDENCE_CASES = [
    ("ERROR", MARKER + " at the front"),
    ("DEBUG", "in the " + MARKER + " middle"),
    ("CRITICAL", "at the end " + MARKER),
    ("INFO", MARKER.lower()),
    ("WARNING", "no marker at all"),
    ("TRACE", "a level the map does not name"),
    ("TRACE", MARKER + " and a level the map does not name"),
    ("", "an empty level name"),
    ("", MARKER + " and an empty level name"),
    ("DEBUG", ""),
]


@pytest.mark.parametrize("level,text", PRECEDENCE_CASES)
def test_the_module_reproduces_the_surface_colour_precedence(
    js: JsRuntime, level: str, text: str
):
    """The marker beats the level on one side and not the other."""
    js.push(bridge_payload())
    line = surface.build_line(level, text).as_dict()
    assert js.for_line("tokenFor", line) == surface.line_token(line["level"], text)
    assert js.for_line("tripleFor", line) == list(
        surface.line_color(line["level"], text)
    )


def test_the_precedence_order_matters_on_both_sides(js: JsRuntime):
    """A marked line lands on the level's colour, which is the wrong way round."""
    js.push(bridge_payload())
    marked = surface.build_line("ERROR", MARKER + " rsi 55").as_dict()
    plain = surface.build_line("ERROR", "rsi 55").as_dict()
    assert marked["color"] == surface.HIGHLIGHT_COLOR
    assert plain["color"] == surface.LEVEL_COLORS["ERROR"]
    assert marked["color"] != plain["color"], "the two rules name one colour"
    assert js.for_line("tokenFor", marked) == surface.HIGHLIGHT_COLOR
    assert js.for_line("tokenFor", plain) == surface.LEVEL_COLORS["ERROR"]
    level_first = dict(marked, color=surface.LEVEL_COLORS["ERROR"])
    report = js.push(bridge_payload({"records": []}))
    assert report["faults"] == []
    js.push(bridge_payload())
    assert js.for_line("tokenFor", level_first) == surface.HIGHLIGHT_COLOR


def test_an_unknown_level_takes_the_default_level_colour(js: JsRuntime):
    js.push(bridge_payload())
    line = surface.build_line("TRACE", "a level the map does not name").as_dict()
    assert js.for_line("tokenFor", line) == surface.LEVEL_COLORS[surface.DEFAULT_LEVEL]
    assert js.json("acervatorConsoleLog.defaultLevel()") == surface.DEFAULT_LEVEL


@pytest.mark.parametrize("level", sorted(surface.LEVEL_COLORS))
def test_each_level_reaches_the_module_with_its_own_colour(js: JsRuntime, level: str):
    js.push(bridge_payload())
    assert js.named("levelHexOf", level) == surface.LEVEL_COLORS[level]
    assert js.named("levelColor", level) == list(
        surface.rgb(surface.LEVEL_COLORS[level])
    )


def test_the_level_check_reads_a_different_colour_for_a_different_level(js: JsRuntime):
    js.push(bridge_payload())
    assert js.named("levelHexOf", "ERROR") != js.named("levelHexOf", "DEBUG")
    assert js.named("levelHexOf", "no such level") is None


def test_the_level_order_reaches_the_module_as_the_surface_wrote_it(js: JsRuntime):
    """Issue 276: a list keeps its order across the bridge where a bag may not."""
    payload = bridge_payload()
    js.push(payload)
    assert js.json("acervatorConsoleLog.levelOrder()") == list(surface.LEVEL_COLORS)
    assert list(js.json("acervatorConsoleLog.levelColors()")) == payload["level_order"]
    assert list(js.json("acervatorConsoleLog.levelHex()")) == payload["level_order"]


def test_the_level_order_check_names_a_reordered_list(js: JsRuntime):
    payload = bridge_payload()
    payload["level_order"].reverse()
    js.push(payload)
    assert js.json("acervatorConsoleLog.levelOrder()") != list(surface.LEVEL_COLORS)


def test_a_line_painted_off_its_own_rule_is_named(js: JsRuntime):
    payload = state_payload("levels")
    payload["document"]["lines"][0]["color"] = surface.LEVEL_COLORS["ERROR"]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "token-mismatch"]
    assert named == [
        {
            "where": "line:0",
            "field": "color",
            "fault": "token-mismatch",
            "detail": surface.LEVEL_COLORS["DEBUG"],
        }
    ], f"the check named {named}"


def test_a_line_whose_channels_disagree_with_its_rule_is_named(js: JsRuntime):
    payload = state_payload("levels")
    payload["document"]["lines"][0]["r"] += 1
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "colour-mismatch"]
    assert [one["where"] for one in named] == ["line:0"], f"the check named {named}"


def test_the_colour_checks_are_quiet_on_every_whole_payload(js: JsRuntime):
    for name in STATE_NAMES:
        report = js.push(state_payload(name))
        named = [
            one
            for one in report["faults"]
            if one["fault"] in ("colour-mismatch", "token-mismatch", "hex-width")
        ]
        assert named == [], f"{name}: the shipped payload names {named}"


def test_every_colour_the_surface_publishes_carries_six_hex_digits():
    """Qt reads eight digits as alpha first and CSS reads them alpha last."""
    every = list(surface.LEVEL_COLORS.values()) + [
        surface.HIGHLIGHT_COLOR,
        surface.DROP_NOTICE_COLOR,
    ]
    widths = {value: len(value.lstrip("#")) for value in every}
    assert set(widths.values()) == {6}, f"the surface publishes {widths}"


def test_an_eight_digit_colour_is_refused(js: JsRuntime):
    payload = state_payload("one")
    swapped = payload["document"]["lines"][0]["color"] + "ff"
    payload["document"]["lines"][0]["color"] = swapped
    report = js.push(payload)
    assert {
        "where": "line:0",
        "field": "color",
        "fault": "hex-width",
        "detail": swapped,
    } in report["faults"]


def test_the_hex_width_check_is_quiet_on_a_six_digit_colour(js: JsRuntime):
    report = js.push(state_payload("one"))
    assert [one for one in report["faults"] if one["fault"] == "hex-width"] == []


def test_the_cap_holds_and_the_notice_counts_what_it_dropped(js: JsRuntime):
    payload = state_payload("past_cap")
    js.push(payload)
    assert js.json("acervatorConsoleLog.buffered()") == PAST_CAP
    assert js.json("acervatorConsoleLog.dropped()") == len(FLOOD_RECORDS) - PAST_CAP
    assert js.json("acervatorConsoleLog.bufferMax()") == PAST_CAP
    assert js.json("acervatorConsoleLog.lines()") == []


def test_the_resume_drains_the_survivors_in_order_and_then_the_notice(js: JsRuntime):
    payload = state_payload("resumed")
    js.push(payload)
    held = js.json("acervatorConsoleLog.lines()")
    kept = [one["text"] for one in FLOOD_RECORDS[:PAST_CAP]]
    assert [one["text"] for one in held[:PAST_CAP]] == kept
    assert len(held) == PAST_CAP + 1, f"the resume drained {held}"
    notice = held[-1]
    assert str(len(FLOOD_RECORDS) - PAST_CAP) in notice["text"]
    assert str(PAST_CAP) in notice["text"]
    assert notice["level"] == surface.DROP_NOTICE_LEVEL
    assert notice["color"] == surface.DROP_NOTICE_COLOR
    assert js.json("acervatorConsoleLog.dropped()") == 0
    assert js.json("acervatorConsoleLog.buffered()") == 0


def test_the_drop_notice_check_reads_a_different_count_for_a_different_flood(
    js: JsRuntime,
):
    """A shorter flood must not read the same notice as the long one."""
    short = bridge_payload(
        {"paused": True},
        {"records": FLOOD_RECORDS[: PAST_CAP + 1]},
        {"paused": False},
        buffer_max=PAST_CAP,
    )
    js.push(short)
    shorter = js.json("acervatorConsoleLog.lines()")[-1]["text"]
    js.push(state_payload("resumed"))
    assert shorter != js.json("acervatorConsoleLog.lines()")[-1]["text"]


def test_a_buffer_holding_more_than_its_own_cap_is_named(js: JsRuntime):
    payload = state_payload("past_cap")
    payload["buffered"] = payload["buffer_max"] + 1
    report = js.push(payload)
    assert {
        "where": None,
        "field": "buffered",
        "fault": "over-cap",
        "detail": payload["buffered"],
    } in report["faults"]


def test_the_over_cap_check_is_quiet_on_a_buffer_inside_its_cap(js: JsRuntime):
    report = js.push(state_payload("at_cap"))
    assert [one for one in report["faults"] if one["fault"] == "over-cap"] == []
    assert state_payload("at_cap")["buffered"] == AT_CAP


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_insert_text_agrees_with_the_lines_it_joins(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    named = [one for one in report["faults"] if one["fault"] == "disagrees"]
    assert named == [], f"{state}: the payload disagrees with itself: {named}"


def test_the_appended_state_leads_with_the_separator_the_pane_needs(js: JsRuntime):
    payload = state_payload("appended")
    js.push(payload)
    joined = "\n".join(one["text"] for one in payload["document"]["lines"])
    assert payload["document"]["insert_text"] == "\n" + joined
    assert js.json("acervatorConsoleLog.insertText()") == "\n" + joined


def test_an_insert_text_that_joins_to_nothing_is_named(js: JsRuntime):
    payload = state_payload("levels")
    payload["document"]["insert_text"] = "a text the lines do not join to"
    report = js.push(payload)
    joined = "\n".join(
        one["text"] for one in state_payload("levels")["document"]["lines"]
    )
    assert {
        "where": "document",
        "field": "insert_text",
        "fault": "disagrees",
        "detail": joined,
    } in report["faults"]


def as_css(value: Any) -> set:
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


def log_values() -> set:
    """Every colour, level name, marker and line text the log paints."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        found.add(payload["highlight_marker"])
        found.add(payload["highlight_hex"])
        found.add(payload["default_level"])
        found |= set(payload["level_hex"].values())
        found |= set(payload["level_order"])
        found.add(payload["document"]["insert_text"])
        for line in payload["document"]["lines"]:
            found |= {line["text"], line["level"], line["color"]}
        for number in (payload["buffer_max"], payload["buffered"], payload["dropped"]):
            found |= as_css(number)
    found.discard("")
    return found


def token_values() -> set:
    found: set = set()
    for value in dss.TOKENS.values():
        found |= as_css(value)
    found.discard("")
    return found


def published_strings() -> set:
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                found.add(key)
                walk(value)
            return
        if isinstance(node, list):
            for one in node:
                walk(one)
            return
        if isinstance(node, str):
            found.add(node)

    for name in STATE_NAMES:
        walk(state_payload(name))
    found.discard("")
    return found


LOG_VALUES = log_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every published string the module writes as a literal, each one a name.
NAMED_WORDS = sorted(
    {
        "b",
        "buffer_max",
        "buffered",
        "color",
        "default_level",
        "document",
        "dropped",
        "follow_tail",
        "g",
        "highlight_color",
        "highlight_marker",
        "highlight_hex",
        "insert_text",
        "level",
        "level_colors",
        "level_order",
        "level_hex",
        "lines",
        "paused",
        "r",
        "text",
    }
)


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a value the surface owns."""
    assert not MODULE_LITERALS[
        "numbers"
    ], f"console_log.js holds numeric literals: {MODULE_LITERALS['numbers']}"


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"console_log.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_log_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & LOG_VALUES)
    assert not written, f"console_log.js spells out log values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"console_log.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    """Every published string the module holds is listed rather than skipped."""
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert written == NAMED_WORDS, (
        f"the module names {sorted(set(written) - set(NAMED_WORDS))} more and "
        f"{sorted(set(NAMED_WORDS) - set(written))} fewer published strings "
        "than the list allows"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_log_shows():
    overlap = sorted(set(NAMED_WORDS) & LOG_VALUES)
    assert not overlap, f"these named words are values the log paints: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "console_log.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


PLANTED_LINES = {
    "colour": 'var planted = "#00ffcc";',
    "level_colour": 'var planted = "' + surface.LEVEL_COLORS["ERROR"] + '";',
    "notice_colour": 'var planted = "' + surface.DROP_NOTICE_COLOR + '";',
    "marker": 'var planted = "' + MARKER + '";',
    "default_level": 'var planted = "' + surface.DEFAULT_LEVEL + '";',
    "cap": "var planted = " + str(surface.BUFFER_MAX) + ";",
    "slack": "var planted = " + str(surface.SCROLL_SLACK) + ";",
    "number": "var planted = 12;",
    "token_value": 'var planted = "' + str(dss.PRIMARY) + '";',
    "regex": "var planted = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if found["numbers"]:
        caught.add("number")
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & LOG_VALUES:
        caught.add("log_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_a_planted_line(kind: str):
    caught = caught_by_scan(PLANTED_LINES[kind])
    assert caught, f"the scan reported nothing on the planted {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


#: The file the swap below moves over the module, named for this unit.
SPARE_PATH = MODULE_PATH.with_name("console_log.literal_scan.js")
SWAP_RETRIES = 20
SWAP_PAUSE_SEC = 0.05


def swap_module(content: bytes) -> None:
    """os.replace swaps the module file in one step, so no worker reads half."""
    SPARE_PATH.write_bytes(content)
    for attempt in range(SWAP_RETRIES):
        try:
            os.replace(SPARE_PATH, MODULE_PATH)
            return
        except PermissionError:
            if attempt == SWAP_RETRIES - 1:
                raise
            time.sleep(SWAP_PAUSE_SEC)


def test_each_planted_literal_is_caught_in_the_module_file_itself():
    original = MODULE_PATH.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    assert original.decode("utf-8") == MODULE_SOURCE
    caught_each = {}
    try:
        for kind in sorted(PLANTED_LINES):
            swap_module(original + PLANTED_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(original)
            after = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
            assert after == before, f"the file was not restored after the {kind} line"
    finally:
        swap_module(original)
        SPARE_PATH.unlink(missing_ok=True)
    quiet = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not quiet, f"the scan reported nothing on these lines in the file: {quiet}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_planted_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, line in sorted(PLANTED_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetConsoleLog") == "function", kind


def python_kinds(payload: dict) -> dict:
    found: dict = {}

    def descend(path: str, value: Any) -> None:
        if isinstance(value, dict):
            walk(path, value)
            return
        if isinstance(value, list):
            for at, one in enumerate(value):
                inner = f"{path}.{at}"
                found[inner] = JS_TYPE_OF[type(one).__name__]
                descend(inner, one)

    def walk(prefix: str, node: dict) -> None:
        for name, value in node.items():
            path = f"{prefix}.{name}" if prefix else name
            found[path] = JS_TYPE_OF[type(value).__name__]
            descend(path, value)

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_of_every_state_arrives_as_the_type_it_left_as(
    js: JsRuntime, state: str
):
    """A value that changes shape in transit reads correct and paints
    wrong: a number where a colour belongs paints nothing."""
    payload = state_payload(state)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json("acervatorConsoleLog.kinds()")
    differing = {
        path: (kind, actual.get(path))
        for path, kind in expected.items()
        if actual.get(path) != kind
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(expected)} values changed type: "
        f"{sorted(differing)}"
    )
    assert sorted(actual) == sorted(expected)


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    payload = bridge_payload()
    payload["buffer_max"] = str(payload["buffer_max"])
    js.push(payload)
    expected = python_kinds(bridge_payload())
    actual = js.json("acervatorConsoleLog.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["buffer_max"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_holds_every_line_field_against_a_published_default(
    js: JsRuntime, state: str
):
    """A field with no default behind it is named rather than skipped."""
    js.push(state_payload(state))
    template = js.json("acervatorConsoleLog.templates()")
    assert sorted(template) == sorted(js.json("acervatorConsoleLog.lineFields()"))
    absent = sorted(name for name, kind in template.items() if kind is None)
    assert not absent, f"{state}: these line fields are held against nothing: {absent}"


LINE_TYPE_CASES = {
    "text": 7,
    "level": 7,
    "color": 7,
    "r": "255",
    "g": "255",
    "b": "255",
}


@pytest.mark.parametrize("field", sorted(LINE_TYPE_CASES))
def test_a_line_field_of_the_wrong_type_is_named(js: JsRuntime, field: str):
    payload = state_payload("one")
    payload["document"]["lines"][0][field] = LINE_TYPE_CASES[field]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "wrong-type"]
    assert {
        "where": "line:0",
        "field": field,
        "fault": "wrong-type",
        "detail": "number" if isinstance(LINE_TYPE_CASES[field], int) else "string",
    } in named, f"the check named {named}"


@pytest.mark.parametrize("field", sorted(LINE_TYPE_CASES))
def test_a_line_field_the_payload_omits_is_named(js: JsRuntime, field: str):
    payload = state_payload("one")
    del payload["document"]["lines"][0][field]
    report = js.push(payload)
    assert {
        "where": "line:0",
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"]


@pytest.mark.parametrize("field", sorted(LINE_TYPE_CASES))
def test_a_line_field_carrying_null_is_named(js: JsRuntime, field: str):
    payload = state_payload("one")
    payload["document"]["lines"][0][field] = None
    report = js.push(payload)
    assert {
        "where": "line:0",
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_a_line_field_with_no_default_behind_it_is_named_rather_than_skipped(
    js: JsRuntime,
):
    """Losing the default level leaves five line fields held against nothing."""
    payload = state_payload("one")
    del payload["default_level"]
    report = js.push(payload)
    named = sorted(
        one["field"] for one in report["faults"] if one["fault"] == "no-template"
    )
    assert named == ["b", "color", "g", "level", "r"], f"the check named {named}"
    assert "text" not in named, "insert_text still holds the line text's type"


def test_the_type_checks_are_quiet_on_every_whole_payload(js: JsRuntime):
    for name in STATE_NAMES:
        report = js.push(state_payload(name))
        named = [
            one
            for one in report["faults"]
            if one["fault"] in ("wrong-type", "no-template", "missing", "null")
        ]
        assert named == [], f"{name}: the shipped payload names {named}"


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_published_field_the_payload_omits_is_named(js: JsRuntime, field: str):
    payload = bridge_payload()
    del payload[field]
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"]
    assert report["held"]["fields"] == len(MODULE_READERS) - 1


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_published_field_carrying_null_is_named(js: JsRuntime, field: str):
    payload = bridge_payload()
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorConsoleLog.isLoaded()") is False
        assert js.json("acervatorConsoleLog.lines()") == []
        assert report["declared"] is None
        assert report["held"] is None
        assert [one["fault"] for one in report["faults"]] == ["not-an-object"]


def test_lines_that_are_not_a_list_is_named(js: JsRuntime):
    payload = bridge_payload()
    payload["document"]["lines"] = "not a list"
    report = js.push(payload)
    assert {
        "where": "document",
        "field": "lines",
        "fault": "not-a-list",
        "detail": "string",
    } in report["faults"]


def test_a_line_that_is_not_an_object_is_named(js: JsRuntime):
    payload = state_payload("one")
    payload["document"]["lines"].append("not a line")
    report = js.push(payload)
    assert {
        "where": "line:1",
        "field": None,
        "fault": "not-an-object",
        "detail": "string",
    } in report["faults"]
    assert report["declared"]["lines"] == report["held"]["lines"] + 1


def test_a_level_the_order_names_with_no_colour_is_named(js: JsRuntime):
    payload = bridge_payload()
    payload["level_order"].append("no_such_level")
    report = js.push(payload)
    for table in ("level_colors", "level_hex"):
        assert {
            "where": table,
            "field": "no_such_level",
            "fault": "missing",
            "detail": None,
        } in report["faults"]
    assert report["declared"]["levels"] == report["held"]["levels"] + 1


def test_the_level_order_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(bridge_payload())
    assert [one for one in report["faults"] if one["where"] == "level_order"] == []
    assert report["faults"] == []


def test_a_name_the_payload_never_carried_is_not_a_level(js: JsRuntime):
    """Every JavaScript object inherits names such as constructor and toString."""
    js.push(bridge_payload())
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        assert js.named("levelColor", inherited) is None
        assert js.named("levelHexOf", inherited) is None


def test_the_inherited_name_check_still_reads_a_real_level(js: JsRuntime):
    js.push(bridge_payload())
    assert js.named("levelColor", surface.DEFAULT_LEVEL) is not None


HOSTILE_LINES = {
    "text is a number": {"text": 1234.5},
    "text is a flag": {"text": True},
    "level is a number": {"level": 7},
    "level is empty": {"level": ""},
    "level is unknown": {"level": "NO SUCH LEVEL"},
    "colour is a number": {"color": 7},
    "a channel is text": {"r": "255"},
    "a channel is huge": {"r": 10**24},
    "text is 200 characters": {"text": LONG_WORD},
    "text holds a newline": {"text": NEWLINE_LINE},
    "text holds markup": {"text": MARKUP_LINE},
}


#: JavaScript holds every number as a double, so a big integer arrives short.
BIGGEST_EXACT_INTEGER = 2**53


def as_javascript(value: Any) -> Any:
    if type(value) is int and abs(value) > BIGGEST_EXACT_INTEGER:
        return float(value)
    return json.loads(json.dumps(value))


@pytest.mark.parametrize("case", sorted(HOSTILE_LINES))
def test_a_hostile_line_reaches_the_module_unchanged(js: JsRuntime, case: str):
    """The module carries the exact value the surface produced, repairing nothing."""
    payload = state_payload("one")
    payload["document"]["lines"][0].update(HOSTILE_LINES[case])
    js.push(payload)
    held = js.json("acervatorConsoleLog.lines()")[0]
    for name, value in HOSTILE_LINES[case].items():
        assert held[name] == as_javascript(value), f"{case}/{name}"


def test_the_hostile_line_check_reads_a_value_the_module_would_have_changed():
    """A repaired value must not read the same as the value that was sent."""
    assert as_javascript(10**24) != 10**24
    assert as_javascript("255") == "255"
    assert as_javascript(True) is True


def test_a_very_large_channel_loses_precision_crossing_the_bridge(js: JsRuntime):
    """The bridge carries 10 to the 24th as a double and loses digits."""
    payload = state_payload("one")
    payload["document"]["lines"][0]["r"] = 10**24
    js.push(payload)
    held = js.json("acervatorConsoleLog.lines()")[0]["r"]
    assert held == float(10**24)
    assert held != 10**24, "the bridge kept every digit"


NOT_A_NUMBER = {
    "not a number": float("nan"),
    "an infinity": float("inf"),
    "a negative infinity": float("-inf"),
}


@pytest.mark.parametrize("case", sorted(NOT_A_NUMBER))
def test_a_not_a_number_never_reaches_the_module_at_all(js: JsRuntime, case: str):
    """JSON.parse refuses NaN, so the frame is dropped before the module sees it."""
    payload = state_payload("one")
    payload["document"]["lines"][0]["r"] = NOT_A_NUMBER[case]
    js.bind_json("PAYLOAD", payload)
    raised = js.raised("acervatorSetConsoleLog(JSON.parse(PAYLOAD))")
    assert raised, f"{case} parsed where the real page drops the frame"
    assert "JSON" in raised or "SyntaxError" in raised, raised


def test_a_real_number_in_the_same_field_parses(js: JsRuntime):
    payload = state_payload("one")
    payload["document"]["lines"][0]["r"] = 1.5
    js.bind_json("PAYLOAD", payload)
    assert js.raised("acervatorSetConsoleLog(JSON.parse(PAYLOAD))") == ""
    assert js.json("acervatorConsoleLog.lines()")[0]["r"] == 1.5


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadConsoleLog();")
    drain_events()
    assert js.json("window.CALLS") == [[surface.METHOD, "{}"]]
    assert js.json("acervatorConsoleLog.isLoaded()") is True


def test_the_module_passes_a_caller_s_parameters_to_the_surface(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", {"paused": True})
    js.run("acervatorLoadConsoleLog(JSON.parse(WANTED));")
    drain_events()
    assert js.json("window.CALLS") == [[surface.METHOD, '{"paused":true}']]


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadConsoleLog(); acervatorLoadConsoleLog();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadConsoleLog();")
    drain_events()
    js.run("acervatorConsoleLog.forget(); acervatorLoadConsoleLog();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadConsoleLog();")
    drain_events()
    assert js.json("acervatorConsoleLog.isLoaded()") is False
    assert js.json("acervatorConsoleLog.loadError()") == (
        "the preload bridge is not present"
    )


def test_a_refused_first_ask_is_not_remembered(js: JsRuntime):
    """A backend not running at page open must be reachable on the next ask."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadConsoleLog();"
    )
    drain_events()
    assert js.json("acervatorConsoleLog.isLoaded()") is False
    js.run("acervatorLoadConsoleLog();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorConsoleLog.isLoaded()") is True


def test_the_bridge_handler_serves_the_same_fields_as_the_view_model(js: JsRuntime):
    """view_model keeps one pause buffer per process, so it is left resumed."""
    try:
        served = json.loads(
            json.dumps(surface.view_model({"paused": False}), ensure_ascii=True)
        )
        js.push(served)
        assert sorted(served) == sorted(MODULE_READERS)
        assert js.json("acervatorConsoleLog.isLoaded()") is True
    finally:
        surface.view_model({"paused": False})


def carriers_of(value: Any) -> list:
    tokens = token_payload()
    aliases = tokens["alias_targets"]
    return sorted(
        name
        for name, held in tokens["tokens"].items()
        if str(held) == str(value) and name not in aliases
    )


LOG_COLOURS = sorted(
    set(surface.LEVEL_COLORS.values())
    | {surface.HIGHLIGHT_COLOR, surface.DROP_NOTICE_COLOR}
)

#: The one token each console colour resolves through, and the level it names.
COLOUR_CARRIERS = {
    surface.LEVEL_COLORS["DEBUG"]: "TEXT_MUTED",
    surface.LEVEL_COLORS["INFO"]: "TEXT_INACTIVE",
    surface.LEVEL_COLORS["WARNING"]: "WARNING",
    surface.LEVEL_COLORS["ERROR"]: "ERROR",
    surface.LEVEL_COLORS["CRITICAL"]: "MAIN_LOG_CRITICAL",
    surface.HIGHLIGHT_COLOR: "PRIMARY",
}


def test_every_colour_the_log_paints_resolves_to_one_token(skinned: JsRuntime):
    """A colour is painted through the one token that holds it."""
    assert LOG_COLOURS, "the log paints no colour; the check cannot report"
    for value in LOG_COLOURS:
        skinned.bind_json("VALUE", value)
        name = skinned.json("acervatorConsoleLog.variableFor(JSON.parse(VALUE))")
        assert carriers_of(value) == [
            name
        ], f"{value} is carried by {carriers_of(value)}"
        assert COLOUR_CARRIERS[value] == name


def test_the_colour_resolver_reports_no_name_for_a_colour_no_token_carries(
    skinned: JsRuntime,
):
    skinned.bind_json("VALUE", "#010203")
    assert skinned.json("acervatorConsoleLog.variableFor(JSON.parse(VALUE))") is None


def test_the_colour_resolver_reports_no_name_with_the_widget_module_off_the_page(
    js: JsRuntime,
):
    js.load_tokens()
    assert js.json("typeof acervatorWidgets") == "undefined"
    js.bind_json("VALUE", surface.HIGHLIGHT_COLOR)
    assert js.json("acervatorConsoleLog.colour(JSON.parse(VALUE))") == (
        surface.HIGHLIGHT_COLOR
    )


def test_the_colour_is_painted_through_its_token_with_the_widget_module_on_the_page(
    skinned: JsRuntime,
):
    skinned.bind_json("VALUE", surface.HIGHLIGHT_COLOR)
    assert skinned.json("acervatorConsoleLog.colour(JSON.parse(VALUE))") == (
        "var(--PRIMARY, " + surface.HIGHLIGHT_COLOR + ")"
    )


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"
        self.wait_for_module()

    def wait_for_module(self) -> None:
        """Spin until the page has run the console log module."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetConsoleLog") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the console log module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
        )

    def js(self, script: str) -> Any:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        box: dict = {}

        def _answered(value: Any) -> None:
            box.setdefault("v", value)
            loop.quit()

        self._view.page().runJavaScript(script, _answered)
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        assert "v" in box, "the browser never answered: " + script[:80]
        return box["v"]

    def parsed(self, expression: str) -> Any:
        return json.loads(self.js("JSON.stringify(" + expression + ")"))

    def settle(self, milliseconds: int) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def close(self) -> None:
        self._view.deleteLater()


@pytest.fixture()
def browser(qapp):
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


STYLE_NAMES = [
    "color",
    "whiteSpace",
    "userSelect",
    "webkitUserSelect",
    "display",
    "fontFamily",
    "fontSize",
]

#: The pane the parent tab draws around these lines sets the wrapping.
PANE_WRAP = "pre" if parent.LOG_PANE["wrap"] is False else "pre-wrap"

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.style.overflow = 'auto';"
    "document.body.appendChild(window.HOST);"
    "window.setWrap = function (value) {"
    "  window.HOST.style.whiteSpace = value; };"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeStyle = function (cssText, names) {"
    "  var probe = document.createElement('div');"
    "  probe.style.cssText = cssText;"
    "  document.body.appendChild(probe);"
    "  var found = window.readStyle(probe, names);"
    "  probe.remove();"
    "  return found; };"
)

READ_PARTS = (
    "(function () {"
    "  var names = JSON.parse(window.STYLE_NAMES);"
    "  var found = [];"
    "  var walk = function (el, path) {"
    "    var part = el.getAttribute('data-part');"
    "    var here = path;"
    "    if (part !== null) {"
    "      here = path ? path + '/' + part : part;"
    "      var attrs = {};"
    "      Array.prototype.slice.call(el.attributes).forEach(function (a) {"
    "        attrs[a.name] = a.value; });"
    "      var own = '';"
    "      Array.prototype.slice.call(el.childNodes).forEach(function (n) {"
    "        if (n.nodeType === Node.TEXT_NODE) { own += n.nodeValue; } });"
    "      found.push({ path: here, tag: el.tagName, attrs: attrs,"
    "        text: own, whole: el.textContent,"
    "        scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)


def give_tokens(browser: Browser) -> int:
    """Put the real token table on the page and write it into the CSS."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_log(browser: Browser, payload: dict, wrap: str = PANE_WRAP) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js("window.setWrap(" + json.dumps(wrap) + ");")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetConsoleLog(JSON.parse(window.PAYLOAD));"
        "acervatorConsoleLog.renderLog(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    return json.loads(browser.js(READ_PARTS))


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def probe_colour(browser: Browser, value: str) -> str:
    """The computed colour a bare element takes from the surface's own value."""
    return browser.parsed(
        "window.probeStyle("
        + json.dumps("color:" + value)
        + ", "
        + json.dumps(["color"])
        + ")"
    )["color"]


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorConsoleLog") == "object"
    assert browser.js("typeof window.acervatorSetConsoleLog") == "function"
    assert browser.js("typeof window.acervatorLoadConsoleLog") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_log(browser, state_payload("levels"))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_drawn_log_names_every_part_a_check_reads(browser: Browser):
    payload = state_payload("levels")
    parts = draw_log(browser, payload)
    paths = sorted({one["path"] for one in parts})
    assert paths == ["log", "log/line"], f"the log drew {paths}"
    for one in at_path(parts, "log/line"):
        assert "data-index" in one["attrs"]
        assert "data-level" in one["attrs"]
        assert "data-color" in one["attrs"]
    container = only(parts, "log")
    assert container["attrs"]["data-paused"] == str(payload["paused"]).lower()
    assert container["attrs"]["data-buffered"] == str(payload["buffered"])
    assert container["attrs"]["data-dropped"] == str(payload["dropped"])
    assert container["attrs"]["data-buffer-max"] == str(payload["buffer_max"])
    assert container["attrs"]["data-follow-tail"] == str(payload["follow_tail"]).lower()
    assert container["attrs"]["data-declared-lines"] == str(
        len(payload["document"]["lines"])
    )


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_drawn_log_shows_every_line_in_the_order_the_surface_published(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_log(browser, payload)
    drawn = at_path(parts, "log/line")
    lines = payload["document"]["lines"]
    assert [one["text"] for one in drawn] == [one["text"] for one in lines]
    assert [one["attrs"]["data-index"] for one in drawn] == [
        str(at) for at in range(len(lines))
    ]
    assert [one["attrs"]["data-level"] for one in drawn] == [
        one["level"] for one in lines
    ]


def test_the_line_order_check_names_a_reordered_payload(browser: Browser):
    payload = state_payload("levels")
    payload["document"]["lines"].reverse()
    parts = draw_log(browser, payload)
    shown = [one["text"] for one in at_path(parts, "log/line")]
    original = [one["text"] for one in state_payload("levels")["document"]["lines"]]
    assert shown != original, "the check cannot see a reordered payload"
    assert shown == list(reversed(original))
    differing = [at for at, line in enumerate(original) if shown[at] != line]
    assert differing, "the reversed payload drew in the original order"


def test_the_line_identity_check_names_two_swapped_texts(browser: Browser):
    payload = state_payload("levels")
    lines = payload["document"]["lines"]
    lines[1]["text"], lines[2]["text"] = lines[2]["text"], lines[1]["text"]
    parts = draw_log(browser, payload)
    shown = [one["text"] for one in at_path(parts, "log/line")]
    original = [one["text"] for one in state_payload("levels")["document"]["lines"]]
    differing = [at for at, line in enumerate(original) if shown[at] != line]
    assert differing == [1, 2], f"the check named {differing}"


def test_the_line_order_check_is_quiet_on_the_shipped_payload(browser: Browser):
    payload = state_payload("levels")
    parts = draw_log(browser, payload)
    shown = [one["text"] for one in at_path(parts, "log/line")]
    original = [one["text"] for one in payload["document"]["lines"]]
    assert [at for at, line in enumerate(original) if shown[at] != line] == []


def test_the_drawn_text_joins_with_the_newline_the_pane_inserts(browser: Browser):
    """Qt holds one document, so the whole text a drag selects is the joined lines."""
    payload = state_payload("levels")
    parts = draw_log(browser, payload)
    joined = "\n".join(one["text"] for one in payload["document"]["lines"])
    assert only(parts, "log")["whole"] == joined
    assert payload["document"]["insert_text"] == joined


@pytest.mark.parametrize("state", ["levels", "precedence", "resumed", "one"])
def test_each_drawn_line_paints_the_colour_the_surface_published(
    browser: Browser, state: str
):
    """Every value is compared against a probe, never a typed number."""
    payload = state_payload(state)
    parts = draw_log(browser, payload)
    drawn = at_path(parts, "log/line")
    lines = payload["document"]["lines"]
    assert drawn, f"{state} drew no line; the check cannot report"
    differing = {}
    for at, one in enumerate(drawn):
        expected = probe_colour(browser, lines[at]["color"])
        if one["style"]["color"] != expected:
            differing[at] = (expected, one["style"]["color"])
    assert not differing, f"{state}: {len(differing)} lines paint wrong: {differing}"


def test_the_colour_check_names_one_changed_colour(browser: Browser):
    payload = state_payload("levels")
    payload["document"]["lines"][0]["color"] = surface.LEVEL_COLORS["ERROR"]
    parts = draw_log(browser, payload)
    drawn = at_path(parts, "log/line")
    original = state_payload("levels")["document"]["lines"]
    differing = [
        at
        for at, one in enumerate(drawn)
        if one["style"]["color"] != probe_colour(browser, original[at]["color"])
    ]
    assert differing == [0], f"the check named {differing}"


def rewrite_token(browser: Browser, name: str, value: Any) -> None:
    browser.js(
        "document.documentElement.style.setProperty("
        + json.dumps("--" + name)
        + ", "
        + json.dumps(str(value))
        + ");"
    )


def changed_paths(before: list, after: list) -> set:
    assert len(before) == len(after), "the log drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((one["path"] + "/" + one["attrs"].get("data-index", ""), key))
    return moved


def test_the_drawn_log_follows_the_error_colour_token(browser: Browser):
    """The token is rewritten and only the error line moves."""
    payload = state_payload("levels")
    before = draw_log(browser, payload)
    assert carriers_of(surface.LEVEL_COLORS["ERROR"]) == ["ERROR"]
    at = [one["level"] for one in payload["document"]["lines"]].index("ERROR")
    rewrite_token(browser, "ERROR", dss.SUCCESS)
    moved = changed_paths(before, read_parts(browser))
    assert moved == {
        ("log/line/" + str(at), "color")
    }, f"the token moved {sorted(moved)}"


def test_the_drawn_log_follows_the_highlight_colour_token(browser: Browser):
    payload = state_payload("precedence")
    before = draw_log(browser, payload)
    assert carriers_of(surface.HIGHLIGHT_COLOR) == ["PRIMARY"]
    marked = [
        str(at)
        for at, one in enumerate(payload["document"]["lines"])
        if one["color"] == surface.HIGHLIGHT_COLOR
    ]
    assert len(marked) > 1, "only one line carries the marker; the check is weak"
    rewrite_token(browser, "PRIMARY", dss.SUCCESS)
    moved = changed_paths(before, read_parts(browser))
    assert moved == {
        ("log/line/" + at, "color") for at in marked
    }, f"the token moved {sorted(moved)}"


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(browser: Browser):
    before = draw_log(browser, state_payload("levels"))
    assert changed_paths(before, read_parts(browser)) == set()


def test_a_markup_line_draws_as_text_and_loads_nothing(browser: Browser):
    """A log message holding an image tag reaches the page as characters."""
    browser.js(WATCH_VIOLATIONS)
    images_before = browser.js("document.images.length")
    parts = draw_log(browser, state_payload("markup"))
    browser.settle(SETTLE_MS)
    line = only(parts, "log/line")
    assert line["text"] == MARKUP_LINE
    assert browser.js("document.images.length") == images_before
    assert browser.parsed("window.VIOLATIONS") == []
    assert (
        browser.js("window.HOST.querySelectorAll('img, b').length") == 0
    ), "the markup became elements"


def test_the_markup_check_reads_a_real_image_as_an_image(browser: Browser):
    """The image count would not move for any markup at all if it never moved."""
    draw_log(browser, state_payload("markup"))
    before = browser.js("document.images.length")
    browser.js(
        "window.PROBE = document.createElement('img');"
        "window.PROBE.src = 'data:image/gif;base64,R0lGOD';"
        "document.body.appendChild(window.PROBE);"
    )
    assert browser.js("document.images.length") == before + 1
    browser.js("window.PROBE.remove();")


def test_a_drawn_line_can_be_selected_by_a_drag(browser: Browser):
    """The Qt pane is read only and still selectable by mouse."""
    parts = draw_log(browser, state_payload("levels"))
    for one in [only(parts, "log")] + at_path(parts, "log/line"):
        picked = one["style"]["userSelect"] or one["style"]["webkitUserSelect"]
        assert picked != "none", f"{one['path']} refuses a drag: {one['style']}"


def test_the_selection_check_reads_a_refused_drag_as_refused(browser: Browser):
    draw_log(browser, state_payload("levels"))
    browser.js("window.HOST.firstChild.style.userSelect = 'none';")
    parts = read_parts(browser)
    assert only(parts, "log")["style"]["userSelect"] == "none"


def test_the_lines_take_their_wrapping_from_the_pane_around_them(browser: Browser):
    """The parent tab owns the pane's wrap, so these lines set none of their own."""
    parts = draw_log(browser, state_payload("long_line"), wrap=PANE_WRAP)
    assert PANE_WRAP == "pre"
    line = only(parts, "log/line")
    assert only(parts, "log")["style"]["whiteSpace"] == PANE_WRAP
    assert line["style"]["whiteSpace"] == PANE_WRAP
    assert only(parts, "log")["clientWidth"] > 0, "the host was never given a width"
    assert (
        only(parts, "log")["scrollWidth"] > only(parts, "log")["clientWidth"]
    ), "the 200 character line fits in the pane"


def test_the_wrap_check_reads_a_wrapping_pane_as_wrapping(browser: Browser):
    """A word with no space cannot break, so the spaced line proves the wrap."""
    parts = draw_log(browser, state_payload("spaced_line"), wrap="normal")
    assert only(parts, "log")["style"]["whiteSpace"] == "normal"
    assert only(parts, "log/line")["style"]["whiteSpace"] == "normal"
    assert only(parts, "log")["scrollWidth"] == only(parts, "log")["clientWidth"]
    wide = draw_log(browser, state_payload("spaced_line"), wrap=PANE_WRAP)
    assert only(wide, "log")["scrollWidth"] > only(wide, "log")["clientWidth"]


def test_a_line_holding_a_newline_draws_it_as_the_pane_shows_it(browser: Browser):
    """Reported and not repaired: the surface keeps one line, and the pane
    would show two blocks."""
    payload = state_payload("one")
    payload["document"]["lines"][0]["text"] = NEWLINE_LINE
    parts = draw_log(browser, payload)
    assert len(at_path(parts, "log/line")) == 1
    assert only(parts, "log/line")["text"] == NEWLINE_LINE


def test_a_hostile_payload_still_draws_a_log(browser: Browser):
    """A module that threw here would draw no log and no line at all."""
    payload = state_payload("levels")
    payload["document"]["lines"][0]["text"] = 7
    payload["document"]["lines"][1]["color"] = None
    payload["level_colors"] = None
    payload["highlight_marker"] = None
    payload["buffered"] = "many"
    parts = draw_log(browser, payload)
    assert only(parts, "log")
    assert len(at_path(parts, "log/line")) == len(payload["document"]["lines"])
    assert at_path(parts, "log/line")[0]["text"] == "7"


def logger_state(logger: logging.Logger) -> tuple:
    """One logger's level and the identity of every handler on it."""
    return (logger.level, tuple(sorted(id(one) for one in logger.handlers)))


def test_drawing_the_log_attaches_nothing_to_the_root_logger(browser: Browser):
    """Drawing the log leaves the root logger level and handlers exactly as they were."""
    root = logging.getLogger()
    before = logger_state(root)
    draw_log(browser, state_payload("levels"))
    assert (
        logger_state(root) == before
    ), f"the root logger moved from {before} to {logger_state(root)}"


def test_the_logger_snapshot_reports_a_handler_that_was_added():
    """Taken on a named logger so the root logger level and handlers stay untouched."""
    named = logging.getLogger("acervator.console_log_unit")
    before = logger_state(named)
    handler = logging.NullHandler()
    named.addHandler(handler)
    try:
        assert logger_state(named) != before
    finally:
        named.removeHandler(handler)
    assert logger_state(named) == before


def test_the_page_names_the_console_log_module_among_its_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("console_log.js")]
    assert len(named) == 1, f"the page names {len(named)} console log modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


def test_the_page_loads_the_widget_module_before_the_console_log_module():
    """The module resolves a colour to a token through shared_widgets.js."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    assert refs.index("../../src/gui/web/shared_widgets.js") < refs.index(
        "../../src/gui/web/console_log.js"
    )
