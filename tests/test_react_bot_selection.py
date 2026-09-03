"""The React bot-table selection panel, against bot_selection_surface.py."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import bot_selection_surface as surface
from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "bot_selection.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")
MODULE_DIGEST = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()

API = "acervatorBotSelection."
SETTER = "acervatorSetBotSelection"

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 3
HOST_WIDTH_PX = 900
HOST_HEIGHT_PX = 500

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

LONG_NAME = "z" * 200
MARKUP_NAME = "<img src='x'><b>bold</b>"
NEWLINE_NAME = "one\ntwo"
HUGE_NUMBER = 10**24

FLEET = ["bot-alpha", "bot-beta", "bot-gamma"]
EVERY_ROW = [0, 1, 2]

#: One request per branch of both decisions the surface makes.
REQUESTS: dict = {
    "nothing_selected": {
        "action": surface.REANCHOR,
        "bot_id": "",
        "bot_ids": FLEET,
        "filled_rows": EVERY_ROW,
    },
    "already_on_the_bot": {
        "action": surface.REANCHOR,
        "bot_id": "bot-beta",
        "bot_ids": FLEET,
        "selected_bot_id": "bot-beta",
        "filled_rows": EVERY_ROW,
    },
    "the_bot_moved": {
        "action": surface.REANCHOR,
        "bot_id": "bot-gamma",
        "bot_ids": FLEET,
        "selected_bot_id": "bot-alpha",
        "filled_rows": EVERY_ROW,
    },
    "the_bot_left": {
        "action": surface.REANCHOR,
        "bot_id": "bot-delta",
        "bot_ids": FLEET,
        "selected_bot_id": "bot-alpha",
        "filled_rows": EVERY_ROW,
    },
    "the_row_was_skipped": {
        "action": surface.REANCHOR,
        "bot_id": "bot-gamma",
        "bot_ids": FLEET,
        "selected_bot_id": "bot-alpha",
        "filled_rows": [0, 1],
    },
    "detail_pressed": {
        "action": surface.SELECT_FOR_BOT,
        "bot_id": "bot-alpha",
        "bot_ids": FLEET,
        "filled_rows": EVERY_ROW,
    },
    "detail_on_a_lost_row": {
        "action": surface.SELECT_FOR_BOT,
        "bot_id": "bot-delta",
        "bot_ids": FLEET,
        "filled_rows": EVERY_ROW,
    },
    "an_action_with_no_name": {
        "action": "scroll",
        "bot_id": "bot-alpha",
        "bot_ids": FLEET,
        "filled_rows": EVERY_ROW,
    },
    "no_bots_at_all": {
        "action": surface.REANCHOR,
        "bot_id": "bot-alpha",
        "bot_ids": [],
        "selected_bot_id": "bot-beta",
        "filled_rows": [],
    },
}
STATE_NAMES = tuple(REQUESTS)

CHOSEN_STATE = "the_bot_moved"
DRAWN_STATE = "detail_pressed"


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def state_payload(name: str) -> dict:
    return as_json(surface.view_model(dict(REQUESTS[name])))


def token_payload() -> dict:
    return as_json(dss.view_model({}))


def js_text(value: Any) -> str:
    """One value spelled the way JavaScript String spells it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


#: The token module the panel resolves every colour and length through.
SHARED_MODULES = (WEB / "design_tokens.js",)


class JsRuntime(JsEngine):
    """A QJSEngine holding the module, its tokens and one raised answer."""

    module_path = MODULE_PATH
    setter = SETTER

    def __init__(self, engine: Any, source: str) -> None:
        super().__init__(engine, source)
        for path in SHARED_MODULES:
            loaded = engine.evaluate(path.read_text(encoding="utf-8"), path.name)
            assert not loaded.isError(), path.name + " -> " + loaded.toString()
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS))")

    def called(self, method: str, value: Any) -> Any:
        self.bind_json("ARG", value)
        return self.json(API + method + "(JSON.parse(ARG))")

    def pushed_with(self, payload: dict, statement: str) -> Any:
        """Set ``payload`` after ``statement`` has changed it inside the engine."""
        self.bind_json("PAYLOAD", payload)
        return self.json(
            SETTER
            + "((function () { var p = JSON.parse(PAYLOAD); "
            + statement
            + " return p; })())"
        )


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


def declared_fields(js: JsRuntime) -> list:
    return js.json(API + "declaredNames()")


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    """A field with no answer is a value that stops at the bridge."""
    payload = state_payload(state)
    js.push(payload)
    named = declared_fields(js)
    missing = sorted(set(payload) - set(named))
    assert (
        not missing
    ), f"{len(missing)} published fields the module never names: {missing}"
    extra = sorted(set(named) - set(payload))
    assert not extra, f"the module names fields the surface has none of: {extra}"
    js.bind_json("NAMES", named)
    answered = js.json(
        "JSON.parse(NAMES).map(function (n) { return " + API + "field(n); })"
    )
    differing = {
        name: (payload[name], answered[at])
        for at, name in enumerate(named)
        if answered[at] != payload[name]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields differ: "
        f"{sorted(differing)}"
    )


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_selection_rule_the_surface_publishes_is_answered(
    js: JsRuntime, state: str
):
    """A selection rule with no answer is a value that stops at the bridge."""
    payload = state_payload(state)
    js.push(payload)
    named = js.json(API + "selectionNames()")
    assert sorted(named) == sorted(payload["selection"]), named
    for name in named:
        assert js.called("selectionRule", name) == payload["selection"][name], name


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_plan_value_the_surface_publishes_is_answered(js: JsRuntime, state: str):
    """A plan value with no answer is a decision the panel never draws."""
    payload = state_payload(state)
    js.push(payload)
    named = js.json(API + "planNames()")
    assert sorted(named) == sorted(payload["plan"]), named
    for name in named:
        assert js.called("planField", name) == payload["plan"][name], name


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    """The payload check would miss a field the module never names."""
    payload = state_payload(CHOSEN_STATE)
    payload["extra_field"] = 1
    js.push(payload)
    assert "extra_field" not in declared_fields(js)


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    """The payload check would miss one value changed on its way in."""
    payload = state_payload(CHOSEN_STATE)
    payload["bot_ids"] = ["bot-other"]
    js.push(payload)
    assert js.json(API + "field('bot_ids')") == ["bot-other"]
    assert js.json(API + "field('bot_ids')") != state_payload(CHOSEN_STATE)["bot_ids"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_the_held_counts_apart(
    js: JsRuntime, state: str
):
    """A count that reads the same both ways cannot report a short payload."""
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["held"]["bots"] == len(payload["bot_ids"])
    assert report["held"]["filled"] == len(payload["filled_rows"])
    assert report["held"]["reads"] == len(payload["plan"]["reads"])
    assert report["held"]["calls"] == len(payload["plan"]["calls"])


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    """A short payload would read as a full one if one count served both."""
    payload = state_payload(CHOSEN_STATE)
    full = js.push(payload)
    del payload["filled_rows"]
    short = js.push(payload)
    assert short["declared"]["fields"] == full["declared"]["fields"]
    assert short["held"]["fields"] == full["held"]["fields"] - 1


def test_a_dropped_call_shortens_the_held_call_count(js: JsRuntime):
    """A dropped call would read as a full plan if the count were fixed."""
    payload = state_payload(CHOSEN_STATE)
    full = js.push(payload)
    payload["plan"]["calls"] = payload["plan"]["calls"][:-1]
    short = js.push(payload)
    assert short["held"]["calls"] == full["held"]["calls"] - 1


def python_kinds(payload: dict) -> dict:
    """The JavaScript type of every value in one payload, by dotted path."""
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
    """A number arriving as text draws a row the surface never chose."""
    payload = state_payload(state)
    js.push(payload)
    wanted = python_kinds(payload)
    answered = js.json(API + "kinds()")
    assert set(answered) == set(wanted), sorted(set(answered) ^ set(wanted))
    differing = {
        path: (wanted[path], answered[path])
        for path in wanted
        if answered[path] != wanted[path]
    }
    assert not differing, f"{state}: {len(differing)} values changed type: {differing}"


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    """The type check would miss a row number arriving as text."""
    payload = state_payload(CHOSEN_STATE)
    payload["plan"]["target_row"] = str(payload["plan"]["target_row"])
    js.push(payload)
    assert js.json(API + "kinds()")["plan.target_row"] == "string"


def test_the_type_walk_names_a_scalar_where_a_call_belongs(js: JsRuntime):
    """A scalar among the calls must be seen, not stepped over."""
    payload = state_payload(CHOSEN_STATE)
    payload["plan"]["calls"] = [7]
    js.push(payload)
    assert js.json(API + "kinds()")["plan.calls.0"] == "number"


def test_the_type_walk_names_a_null_where_a_bot_name_belongs(js: JsRuntime):
    """A null among the fleet must be seen, not stepped over."""
    payload = state_payload(CHOSEN_STATE)
    payload["bot_ids"] = [None]
    js.push(payload)
    assert js.json(API + "kinds()")["bot_ids.0"] == "null"


def not_plain_data(payload: Any) -> list:
    """Every path in one payload whose value is not plain data."""
    found: list = []

    def descend(path: str, value: Any) -> None:
        if isinstance(value, dict):
            walk(path, value)
            return
        if isinstance(value, list):
            for at, one in enumerate(value):
                check(f"{path}.{at}", one)
                descend(f"{path}.{at}", one)

    def check(path: str, value: Any) -> None:
        if type(value).__name__ not in JS_TYPE_OF:
            found.append(path)

    def walk(prefix: str, node: dict) -> None:
        for name, value in node.items():
            path = f"{prefix}.{name}" if prefix else name
            check(path, value)
            descend(path, value)

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_surface_publishes_no_live_object(state: str):
    """A live object on the payload cannot cross the bridge as data."""
    raw = surface.view_model(dict(REQUESTS[state]))
    assert not_plain_data(raw) == []


def test_the_plain_data_walk_names_a_live_object_put_on_the_payload():
    """The plain-data walk would miss a live object among the calls."""
    raw = surface.view_model(dict(REQUESTS[CHOSEN_STATE]))
    raw["plan"]["calls"] = [object()]
    assert not_plain_data(raw) == ["plan.calls.0"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    """A function reaching the panel would draw something no payload sent."""
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    """The plain-data check would miss a function among the calls."""
    js.pushed_with(
        state_payload(CHOSEN_STATE), "p.plan.calls = [function () { return 1; }];"
    )
    assert js.json(API + "notPlainData()") == [
        {"path": "plan.calls.0", "kind": "function"}
    ]


def shown_values() -> set:
    """Every string every state draws, taken from the payload values."""
    found: set = set()

    def descend(value: Any) -> None:
        if isinstance(value, dict):
            for one in value.values():
                descend(one)
            return
        if isinstance(value, list):
            for one in value:
                descend(one)
            return
        if isinstance(value, str):
            found.add(value)

    for name in STATE_NAMES:
        descend(state_payload(name))
    return {one for one in found if one}


def published_words() -> set:
    """Every key and every string value the surface publishes."""
    found: set = set(shown_values())

    def descend(value: Any) -> None:
        if isinstance(value, dict):
            for name, one in value.items():
                found.add(name)
                descend(one)
            return
        if isinstance(value, list):
            for one in value:
                descend(one)

    for name in STATE_NAMES:
        descend(state_payload(name))
    return found


def token_values() -> set:
    """Every design token value, as the string a stylesheet would carry."""
    return {str(one) for one in token_payload()["tokens"].values() if one is not None}


SHOWN_VALUES = shown_values()
TOKEN_VALUES = token_values()
PUBLISHED_WORDS = published_words()

#: The only surface words the module may name, because it reads them.
NAMED_WORDS = set(surface.SELECTION) | {
    "selection",
    "bot_ids",
    "filled_rows",
    "plan",
    "action",
    "target_row",
    "block_signals",
    "reads",
    "calls",
}


def test_the_module_writes_no_number():
    """A number written here is a second source for a surface value."""
    found = js_literals(MODULE_SOURCE)["numbers"]
    assert found == [], f"the module writes {len(found)} numbers: {found[:10]}"


def test_the_module_writes_no_colour():
    """A colour written here is a second skin for one screen."""
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert found == [], f"the module writes {len(found)} colours: {found[:10]}"


def test_no_string_in_the_module_equals_a_value_the_panel_shows():
    """A drawn value spelled here would not follow the surface."""
    found = set(js_literals(MODULE_SOURCE)["strings"]) & SHOWN_VALUES
    assert not found, f"the module spells {len(found)} drawn values: {sorted(found)}"


def test_no_string_in_the_module_equals_a_design_token_value():
    """A token value spelled here would not follow the skin."""
    found = set(js_literals(MODULE_SOURCE)["strings"]) & TOKEN_VALUES
    assert not found, f"the module spells {len(found)} token values: {sorted(found)}"


def test_the_module_names_only_the_surface_words_it_must_read():
    """A surface word beyond the payload keys is a decision copied here."""
    found = set(js_literals(MODULE_SOURCE)["strings"]) & PUBLISHED_WORDS
    assert found <= NAMED_WORDS, f"words beyond the keys: {sorted(found - NAMED_WORDS)}"


def test_every_named_word_is_a_key_and_not_a_value_the_panel_shows():
    """A named word that is also a drawn value would hide a spelled value."""
    assert not (NAMED_WORDS & SHOWN_VALUES)


def test_the_module_names_no_table_call_of_its_own():
    """A table call spelled here would run whatever the plan omitted."""
    strings = set(js_literals(MODULE_SOURCE)["strings"])
    for word in (
        surface.CLEAR_SELECTION,
        surface.SET_CURRENT_CELL,
        surface.SELECT_ROW,
        surface.READ_SELECTED_BOT_ID,
        surface.READ_ANCHOR_ITEM,
        surface.REANCHOR,
        surface.SELECT_FOR_BOT,
    ):
        assert word not in strings, word


def test_the_module_hides_no_value_behind_a_regular_expression():
    """A slash outside a comment could carry a value no scan reads."""
    found = js_literals(MODULE_SOURCE)["slashes"]
    assert found == [], f"{len(found)} stray slashes: {found[:3]}"


def test_the_module_carries_no_style_rule_a_declaration_walk_would_miss():
    """A colour inside a hover or disabled rule is never walked."""
    for marker in (":hover", ":disabled", ":focus", "::", "@media", "!important"):
        assert marker not in MODULE_SOURCE, marker


WRITTEN_LINES = {
    "colour": 'var written = "#123456";',
    "number": "var written = 12;",
    "shown_value": 'var written = "' + sorted(SHOWN_VALUES)[0] + '";',
    "token_value": 'var written = "' + sorted(TOKEN_VALUES)[0] + '";',
    "regex": "var written = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Every kind of written value one scan of ``source`` reports."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if found["numbers"]:
        caught.add("number")
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & SHOWN_VALUES:
        caught.add("shown_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_line(kind: str):
    """The scan would report nothing on a value written into the module."""
    assert caught_by_scan(WRITTEN_LINES[kind]), f"the scan reported nothing on {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    """A colour inside a comment must not count as a written value."""
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_written_literal_is_caught_in_the_module_file_itself():
    """The original is read inside the swap so no other worker's copy lands."""
    original = MODULE_PATH.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    assert before == MODULE_DIGEST, "the module changed between collection and now"
    assert original.decode("utf-8") == MODULE_SOURCE
    caught_each = {}
    try:
        for kind in sorted(WRITTEN_LINES):
            swap_module(MODULE_PATH, original + WRITTEN_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(MODULE_PATH, original)
            after = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
            assert after == before, f"the file was not restored after the {kind} line"
    finally:
        swap_module(MODULE_PATH, original)
    quiet = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not quiet, f"the scan reported nothing on these lines in the file: {quiet}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_written_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    """A written line must leave the module something QJSEngine still runs."""
    for kind, line in sorted(WRITTEN_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof " + SETTER) == "function", kind


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_the_panel_paints_is_swept_for_the_alpha_order_fault(
    js: JsRuntime, state: str
):
    """Eight hex digits read alpha-first in Qt and red-first in a page."""
    js.push(state_payload(state))
    carried = js.json(API + "colourTokens()")
    assert carried, "the panel names no colour at all"
    for one in carried:
        assert js.called("isSwappedAlpha", one["value"]) is False, one


def test_the_alpha_sweep_names_a_colour_written_with_eight_digits(js: JsRuntime):
    """The alpha sweep would miss a colour carrying eight hex digits."""
    js.push(state_payload(CHOSEN_STATE))
    assert js.called("isSwappedAlpha", "#123a63ff") is True
    assert js.called("isSwappedAlpha", "#123a63") is False


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_colour_the_panel_paints_hides_a_channel_swap(js: JsRuntime, state: str):
    """Three equal channels make a red-and-blue swap invisible."""
    js.push(state_payload(state))
    for one in js.json(API + "colourTokens()"):
        assert js.called("isEqualChannels", one["value"]) is False, one


def test_the_equal_channel_sweep_names_a_grey(js: JsRuntime):
    """The channel sweep would miss a colour whose channels are equal."""
    js.push(state_payload(CHOSEN_STATE))
    assert js.called("isEqualChannels", "#404040") is True
    assert js.called("isEqualChannels", "#444") is True
    assert js.called("isEqualChannels", "#404041") is False


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_the_panel_paints_resolves_through_its_token_name(
    js: JsRuntime, state: str
):
    """A colour that skips its token name would not follow the skin."""
    js.push(state_payload(state))
    tokens = token_payload()["tokens"]
    for one in js.json(API + "colourTokens()"):
        drawn = js.called("colour", one["name"])
        assert drawn.startswith("var(--" + one["name"]), drawn
        assert str(tokens[one["name"]]) in drawn, drawn


def test_the_token_resolution_check_names_a_colour_with_no_token(js: JsRuntime):
    """A name no token carries must answer nothing, not a bare value."""
    js.push(state_payload(CHOSEN_STATE))
    assert js.called("colour", "NO_SUCH_TOKEN") is None


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_bag_the_surface_publishes_keeps_a_worded_key(js: JsRuntime, state: str):
    """A key made of digits is moved to the front by every browser."""
    payload = state_payload(state)
    js.push(payload)
    for name in ("selection", "plan"):
        for key in js.called("bagKeys", name):
            assert js.called("isReorderedKey", key) is False, (name, key)


def test_the_bag_order_check_names_a_digit_key(js: JsRuntime):
    """The bag-order check would miss a digit key put into a bag."""
    js.push(state_payload(CHOSEN_STATE))
    assert js.called("isReorderedKey", "12") is True
    assert js.called("isReorderedKey", "row12") is False


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_fleet_reaches_the_module_in_the_order_the_surface_listed_it(
    js: JsRuntime, state: str
):
    """A fleet read out of order pairs a bot with another bot's row."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "botNames()") == payload["bot_ids"]
    rows = js.json(API + "rows()")
    assert [one["bot"] for one in rows] == payload["bot_ids"]
    assert [one["row"] for one in rows] == list(range(len(payload["bot_ids"])))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_fleet_and_the_filled_rows_are_counted_apart(js: JsRuntime, state: str):
    """Two lists of different lengths must never be paired by position."""
    payload = state_payload(state)
    report = js.push(payload)
    assert report["held"]["bots"] == len(payload["bot_ids"])
    assert report["held"]["filled"] == len(payload["filled_rows"])
    for row in range(len(payload["bot_ids"])):
        assert js.called("rowFilled", row) == (row in payload["filled_rows"]), row


def test_a_filled_row_naming_no_bot_is_reported_rather_than_drawn(js: JsRuntime):
    """A row number past the fleet would pair with a bot that is not there."""
    payload = state_payload(CHOSEN_STATE)
    payload["filled_rows"] = payload["filled_rows"] + [9]
    report = js.push(payload)
    assert js.json(API + "orphanRows()") == [9]
    kinds = [one["fault"] for one in report["faults"]]
    assert "beyond-the-fleet" in kinds, report["faults"]


def test_the_orphan_row_check_stays_quiet_on_a_fleet_that_matches(js: JsRuntime):
    """The orphan check would report on every healthy payload if it were loose."""
    js.push(state_payload(CHOSEN_STATE))
    assert js.json(API + "orphanRows()") == []
    assert [one["fault"] for one in js.json(API + "faults()")] == []


@pytest.mark.parametrize("state", STATE_NAMES)
def test_each_call_is_read_back_by_its_own_name_and_not_by_its_place(
    js: JsRuntime, state: str
):
    """A call read by place runs the wrong method when one call is dropped."""
    payload = state_payload(state)
    js.push(payload)
    steps = js.json(API + "callSteps()")
    assert [one["name"] for one in steps] == [
        call[0] for call in payload["plan"]["calls"]
    ]
    for at, call in enumerate(payload["plan"]["calls"]):
        assert steps[at]["args"] == call[1:], (at, call)


@pytest.mark.parametrize("state", STATE_NAMES)
def test_each_read_is_named_with_the_arguments_it_carries(js: JsRuntime, state: str):
    """A read with no arguments would look like a read of another row."""
    payload = state_payload(state)
    js.push(payload)
    steps = js.json(API + "readSteps()")
    assert [one["name"] for one in steps] == [
        one[0] for one in payload["plan"]["reads"]
    ]
    for at, one in enumerate(payload["plan"]["reads"]):
        assert steps[at]["args"] == one[1:], (at, one)


def test_the_call_name_check_names_a_call_whose_name_moved(js: JsRuntime):
    """The call check would miss a name taken from the wrong place."""
    payload = state_payload(CHOSEN_STATE)
    payload["plan"]["calls"] = [["selectRow", "clearSelection"]]
    js.push(payload)
    steps = js.json(API + "callSteps()")
    assert steps[0]["name"] == "selectRow"
    assert steps[0]["args"] == ["clearSelection"]


def test_the_chosen_row_is_reported_when_it_names_no_bot(js: JsRuntime):
    """A chosen row past the fleet would highlight a row that is not there."""
    payload = state_payload(CHOSEN_STATE)
    payload["plan"]["target_row"] = 9
    report = js.push(payload)
    assert "chosen-row-absent" in [one["fault"] for one in report["faults"]]


def test_the_chosen_row_is_reported_when_its_row_carries_no_item(js: JsRuntime):
    """A chosen row the render skipped would read as a selectable row."""
    payload = state_payload(CHOSEN_STATE)
    payload["filled_rows"] = [0]
    report = js.push(payload)
    assert "chosen-row-unfilled" in [one["fault"] for one in report["faults"]]


def test_the_chosen_row_check_stays_quiet_on_a_row_the_surface_chose(js: JsRuntime):
    """The chosen-row check would report on every healthy plan if it were loose."""
    report = js.push(state_payload(CHOSEN_STATE))
    kinds = [one["fault"] for one in report["faults"]]
    assert "chosen-row-absent" not in kinds
    assert "chosen-row-unfilled" not in kinds


HOSTILE_FIELDS: dict = {
    "selection missing": ("selection", None),
    "selection is a list": ("selection", []),
    "plan is a list": ("plan", []),
    "plan is null": ("plan", None),
    "bot_ids is text": ("bot_ids", "bot-alpha"),
    "bot_ids is a bag": ("bot_ids", {}),
    "bot_ids is null": ("bot_ids", None),
    "bot_ids is huge": ("bot_ids", HUGE_NUMBER),
    "filled_rows is text": ("filled_rows", "0"),
    "filled_rows is a bag": ("filled_rows", {}),
    "filled_rows is null": ("filled_rows", None),
    "filled_rows is huge": ("filled_rows", HUGE_NUMBER),
    "filled_rows holds text": ("filled_rows", ["0"]),
    "filled_rows holds a null": ("filled_rows", [None]),
    "filled_rows holds a flag": ("filled_rows", [True]),
    "filled_rows holds a huge row": ("filled_rows", [HUGE_NUMBER]),
    "filled_rows repeats a row": ("filled_rows", [1, 1]),
    "a long bot name": ("bot_ids", [LONG_NAME]),
    "markup as a bot name": ("bot_ids", [MARKUP_NAME]),
    "a newline in a bot name": ("bot_ids", [NEWLINE_NAME]),
    "a repeated bot name": ("bot_ids", ["bot-alpha", "bot-alpha"]),
    "a number as a bot name": ("bot_ids", [7]),
    "no bots at all": ("bot_ids", []),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_FIELDS))
def test_a_hostile_field_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """A payload the surface would never send must report, never raise."""
    name, value = HOSTILE_FIELDS[case]
    payload = state_payload(CHOSEN_STATE)
    payload[name] = value
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    assert isinstance(js.json(API + "kinds()"), dict), case
    assert isinstance(js.json(API + "rows()"), list), case
    assert isinstance(js.json(API + "orphanRows()"), list), case
    assert isinstance(js.json(API + "callSteps()"), list), case


HOSTILE_PLAN_FIELDS: dict = {
    "action is a number": ("action", 7),
    "action is null": ("action", None),
    "target_row is text": ("target_row", "1"),
    "target_row is a flag": ("target_row", True),
    "target_row is huge": ("target_row", HUGE_NUMBER),
    "block_signals is text": ("block_signals", "yes"),
    "reads is a bag": ("reads", {}),
    "reads is null": ("reads", None),
    "reads holds a scalar": ("reads", [7]),
    "calls is text": ("calls", "clearSelection"),
    "calls is null": ("calls", None),
    "calls holds a null": ("calls", [None]),
    "calls holds a bag": ("calls", [{}]),
    "calls holds an empty call": ("calls", [[]]),
    "markup as a call name": ("calls", [[MARKUP_NAME]]),
    "a long call name": ("calls", [[LONG_NAME]]),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_PLAN_FIELDS))
def test_a_hostile_plan_value_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """A plan the surface would never send must report, never raise."""
    name, value = HOSTILE_PLAN_FIELDS[case]
    payload = state_payload(CHOSEN_STATE)
    payload["plan"][name] = value
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    assert isinstance(js.json(API + "callSteps()"), list), case
    assert isinstance(js.json(API + "readSteps()"), list), case


HOSTILE_NUMBERS = {
    "nan": "Number.NaN",
    "inf": "Number.POSITIVE_INFINITY",
    "minus inf": "Number.NEGATIVE_INFINITY",
}


@pytest.mark.parametrize("case", sorted(HOSTILE_NUMBERS))
def test_a_row_number_with_no_json_spelling_is_reported(js: JsRuntime, case: str):
    """A row number JSON cannot write must not name a row."""
    js.pushed_with(
        state_payload(CHOSEN_STATE),
        "p.filled_rows = [" + HOSTILE_NUMBERS[case] + "];",
    )
    assert js.json(API + "orphanRows()") != [], case
    assert [one["filled"] for one in js.json(API + "rows()")] == [False] * len(FLEET)
    assert "not-a-row" in [one["fault"] for one in js.json(API + "faults()")], case


@pytest.mark.parametrize("case", sorted(HOSTILE_NUMBERS))
def test_a_chosen_row_with_no_json_spelling_is_reported(js: JsRuntime, case: str):
    """A chosen row JSON cannot write must not read as a real row."""
    js.pushed_with(
        state_payload(CHOSEN_STATE),
        "p.plan.target_row = " + HOSTILE_NUMBERS[case] + ";",
    )
    assert "chosen-row-absent" in [one["fault"] for one in js.json(API + "faults()")]


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """A module that raised on one hostile value would answer nothing at all."""
    js.push(state_payload(CHOSEN_STATE))
    assert js.json(API + "rows()") != []
    js.json(SETTER + "(7)")
    assert js.json(API + "isLoaded()") is False
    assert js.json(API + "rows()") == []
    assert js.json(API + "callSteps()") == []


@pytest.mark.parametrize("given", ["7", "'text'", "null", "[]", "undefined"])
def test_a_payload_that_is_not_an_object_is_refused_whole(js: JsRuntime, given: str):
    """A payload that is not an object must draw nothing, not part of a plan."""
    report = js.json(SETTER + "(" + given + ")")
    assert report["held"] is None, given
    assert [one["fault"] for one in report["faults"]] == ["not-an-object"], given


def test_a_selection_naming_a_bot_the_fleet_does_not_list_chooses_no_row(
    js: JsRuntime,
):
    """A bot that left the fleet must clear rather than keep a stale row."""
    payload = state_payload("the_bot_left")
    js.push(payload)
    assert js.json(API + "chosenRow()") is None
    assert [one["chosen"] for one in js.json(API + "rows()")] == [False] * len(FLEET)


def test_a_fleet_with_no_bots_draws_no_row_and_still_answers(js: JsRuntime):
    """An empty fleet must answer an empty list, not raise."""
    js.push(state_payload("no_bots_at_all"))
    assert js.json(API + "rows()") == []
    assert js.json(API + "botNames()") == []
    assert js.json(API + "chosenRow()") is None


class Browser:
    """A Browser drives the real renderer page in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        for _ in range(PAGE_ATTEMPTS):
            self.open_page()
            if self.module_ready():
                return
        raise AssertionError(
            "the page never defined the selection module in "
            + str(PAGE_ATTEMPTS)
            + " loads: readyState "
            + str(self.js("document.readyState"))
        )

    def open_page(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl

        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        link = self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        self._view.loadFinished.disconnect(link)
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"

    def module_ready(self) -> bool:
        for _ in range(READY_ROUNDS):
            if self.js("typeof window." + SETTER) == "function":
                return True
            self.settle(READY_STEP_MS)
        return False

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
    "backgroundColor",
    "color",
    "borderTopColor",
    "borderTopWidth",
    "borderTopStyle",
    "minHeight",
    "fontWeight",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "document.body.appendChild(window.HOST);"
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
    "      found.push({ path: here, tag: el.tagName, attrs: attrs,"
    "        text: el.textContent, html: el.innerHTML,"
    "        width: el.getBoundingClientRect().width,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)

COUNT_ELEMENTS = (
    "[window.HOST.querySelectorAll('*').length,"
    " window.HOST.querySelectorAll('[data-part]').length]"
)


def draw_panel(browser: Browser, payload: dict) -> list:
    """Apply the tokens, set ``payload`` and read every named element back."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    browser.js(
        "acervatorSetTokens(JSON.parse(window.TOKENS));"
        "acervatorTokens.apply(document.documentElement);"
    )
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        SETTER + "(JSON.parse(window.PAYLOAD));" + API + "renderPanel(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def parts_named(parts: list, part: str) -> list:
    """Every drawn element whose own name ends in ``part``."""
    return [one for one in parts if one["path"].split("/")[-1] == part]


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A child with no name is a child no check can read."""
    draw_panel(browser, state_payload(DRAWN_STATE))
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no data-part"
    assert named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    """The named-child check would miss a child drawn with no name."""
    draw_panel(browser, state_payload(DRAWN_STATE))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_is_drawn_on_the_page(
    browser: Browser, state: str
):
    """A published field nothing draws is a value the operator never sees."""
    payload = state_payload(state)
    parts = draw_panel(browser, payload)
    panel = parts_named(parts, "bot-selection")[0]
    assert panel["attrs"]["data-bot-count"] == str(len(payload["bot_ids"]))
    assert panel["attrs"]["data-filled-count"] == str(len(payload["filled_rows"]))
    assert panel["attrs"]["data-read-count"] == str(len(payload["plan"]["reads"]))
    assert panel["attrs"]["data-call-count"] == str(len(payload["plan"]["calls"]))
    assert len(parts_named(parts, "selection-rule")) == len(payload["selection"])
    assert len(parts_named(parts, "selection-row")) == len(payload["bot_ids"])
    assert len(parts_named(parts, "selection-read")) == len(payload["plan"]["reads"])
    assert len(parts_named(parts, "selection-call")) == len(payload["plan"]["calls"])


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_selection_rule_is_drawn_with_the_value_the_surface_sent(
    browser: Browser, state: str
):
    """A rule drawn with another rule's value would describe the wrong decision."""
    payload = state_payload(state)
    parts = draw_panel(browser, payload)
    drawn = {
        one["attrs"]["data-name"]: one for one in parts_named(parts, "selection-rule")
    }
    assert sorted(drawn) == sorted(payload["selection"])
    for name, value in payload["selection"].items():
        assert drawn[name]["attrs"]["data-value"] == js_text(value), name
        assert drawn[name]["text"] == js_text(value), name


@pytest.mark.parametrize("state", STATE_NAMES)
def test_each_row_draws_the_bot_its_own_row_number_names(browser: Browser, state: str):
    """A row drawn against another row's bot is the misroute this repairs."""
    payload = state_payload(state)
    parts = draw_panel(browser, payload)
    for one in parts_named(parts, "selection-row"):
        row = int(one["attrs"]["data-row"])
        assert one["attrs"]["data-bot"] == payload["bot_ids"][row], one
        assert one["text"] == payload["bot_ids"][row], one


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_chosen_row_is_the_only_row_drawn_as_chosen(browser: Browser, state: str):
    """Two chosen rows would leave the operator's eye on the wrong bot."""
    payload = state_payload(state)
    parts = draw_panel(browser, payload)
    chosen = [
        int(one["attrs"]["data-row"])
        for one in parts_named(parts, "selection-row")
        if one["attrs"]["data-chosen"] == "true"
    ]
    wanted = (
        [] if payload["plan"]["target_row"] is None else [payload["plan"]["target_row"]]
    )
    assert chosen == wanted, (state, chosen, wanted)


@pytest.mark.parametrize("state", STATE_NAMES)
def test_each_call_is_drawn_with_its_name_apart_from_its_arguments(
    browser: Browser, state: str
):
    """A name and its arguments joined into one string would be caller markup."""
    payload = state_payload(state)
    parts = draw_panel(browser, payload)
    for at, call in enumerate(payload["plan"]["calls"]):
        drawn = [
            one
            for one in parts_named(parts, "selection-call")
            if one["attrs"]["data-index"] == str(at)
        ]
        assert len(drawn) == 1, (at, call)
        assert drawn[0]["attrs"]["data-name"] == call[0]
        args = [
            one
            for one in parts
            if one["path"] == "bot-selection/selection-call/step-argument"
            and one["attrs"]["data-index"] in [str(n) for n in range(len(call) - 1)]
        ]
        assert len(args) >= len(call) - 1


def test_a_chosen_row_paints_the_colours_its_tokens_carry(browser: Browser):
    """A colour that falls back to the page ink would follow no skin."""
    payload = state_payload(CHOSEN_STATE)
    parts = draw_panel(browser, payload)
    chosen = [
        one
        for one in parts_named(parts, "selection-row")
        if one["attrs"]["data-chosen"] == "true"
    ]
    assert len(chosen) == 1, parts
    tokens = token_payload()["tokens"]
    whole = (
        "background: var(--MENU_ITEM_SELECTED, "
        + str(tokens["MENU_ITEM_SELECTED"])
        + "); color: var(--TEXT_HIGH, "
        + str(tokens["TEXT_HIGH"])
        + "); border-style: solid; border-width: var(--FOCUS_RING_WIDTH) * 1px;"
        " border-color: var(--PRIMARY, " + str(tokens["PRIMARY"]) + ");"
    )
    probe = browser.parsed(
        "window.probeStyle(" + json.dumps(whole) + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert chosen[0]["style"]["backgroundColor"] == probe["backgroundColor"]
    assert chosen[0]["style"]["color"] == probe["color"]
    assert chosen[0]["style"]["borderTopColor"] == probe["borderTopColor"]


def test_a_chosen_row_resolves_its_colours_through_the_token_and_not_the_fallback(
    browser: Browser,
):
    """A var written without both dashes falls back and paints the page ink."""
    payload = state_payload(CHOSEN_STATE)
    parts = draw_panel(browser, payload)
    chosen = [
        one
        for one in parts_named(parts, "selection-row")
        if one["attrs"]["data-chosen"] == "true"
    ][0]
    named = browser.parsed(
        "window.probeStyle('background: var(--MENU_ITEM_SELECTED);"
        " color: var(--TEXT_HIGH);', JSON.parse(window.STYLE_NAMES))"
    )
    inherited = browser.parsed(
        "window.probeStyle('background: var(--NO_SUCH_TOKEN);"
        " color: var(--NO_SUCH_TOKEN);', JSON.parse(window.STYLE_NAMES))"
    )
    assert chosen["style"]["backgroundColor"] == named["backgroundColor"]
    assert chosen["style"]["color"] == named["color"]
    assert named["backgroundColor"] != inherited["backgroundColor"]


def test_the_rendered_comparison_would_see_one_repainted_row(browser: Browser):
    """The rendered comparison would miss a row painted another colour."""
    payload = state_payload(CHOSEN_STATE)
    parts = draw_panel(browser, payload)
    chosen = [
        one
        for one in parts_named(parts, "selection-row")
        if one["attrs"]["data-chosen"] == "true"
    ][0]
    browser.js(
        "window.HOST.querySelector('[data-chosen=\"true\"]')"
        ".style.backgroundColor = 'rgb(1, 2, 3)';"
    )
    again = json.loads(browser.js(READ_PARTS))
    repainted = [
        one
        for one in parts_named(again, "selection-row")
        if one["attrs"]["data-chosen"] == "true"
    ][0]
    assert repainted["style"]["backgroundColor"] != chosen["style"]["backgroundColor"]


def test_a_row_the_render_skipped_is_painted_apart_from_a_row_that_can_be_chosen(
    browser: Browser,
):
    """A row carrying no item must not read as a row the operator can pick."""
    payload = state_payload("the_row_was_skipped")
    parts = draw_panel(browser, payload)
    rows = {
        one["attrs"]["data-row"]: one for one in parts_named(parts, "selection-row")
    }
    skipped = rows["2"]
    ordinary = rows["0"]
    assert skipped["attrs"]["data-filled"] == "false"
    assert ordinary["attrs"]["data-filled"] == "true"
    assert (
        skipped["style"]["backgroundColor"] != ordinary["style"]["backgroundColor"]
    ), parts


def test_the_panel_refuses_markup_a_hostile_bot_name_carries(browser: Browser):
    """Markup in a bot name must be drawn as characters, never run."""
    payload = state_payload(CHOSEN_STATE)
    payload["bot_ids"] = [MARKUP_NAME]
    payload["filled_rows"] = [0]
    payload["plan"]["target_row"] = 0
    parts = draw_panel(browser, payload)
    row = parts_named(parts, "selection-row")[0]
    assert row["text"] == MARKUP_NAME
    assert "<img" not in row["html"]
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    """The markup check would miss a tag the page really built."""
    draw_panel(browser, state_payload(CHOSEN_STATE))
    browser.js("window.HOST.firstChild.innerHTML += " + json.dumps(MARKUP_NAME) + ";")
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 1


def test_a_two_hundred_character_bot_name_stretches_the_row_rather_than_clipping(
    browser: Browser,
):
    """A clipped name hides which bot a row names, which is the misroute."""
    payload = state_payload(CHOSEN_STATE)
    payload["bot_ids"] = [LONG_NAME]
    payload["filled_rows"] = [0]
    payload["plan"]["target_row"] = 0
    long_parts = draw_panel(browser, payload)
    long_row = parts_named(long_parts, "selection-row")[0]
    assert long_row["text"] == LONG_NAME
    measured = browser.parsed(
        "(function () {"
        "  var probe = document.createElement('span');"
        "  probe.style.whiteSpace = 'pre';"
        "  probe.textContent = " + json.dumps(LONG_NAME) + ";"
        "  document.body.appendChild(probe);"
        "  var w = probe.getBoundingClientRect().width;"
        "  probe.remove();"
        "  return w; })()"
    )
    short = browser.parsed(
        "(function () {"
        "  var probe = document.createElement('span');"
        "  probe.style.whiteSpace = 'pre';"
        "  probe.textContent = " + json.dumps(FLEET[0]) + ";"
        "  document.body.appendChild(probe);"
        "  var w = probe.getBoundingClientRect().width;"
        "  probe.remove();"
        "  return w; })()"
    )
    assert measured > short, (measured, short)


def test_a_newline_in_a_bot_name_reaches_the_row_whole(browser: Browser):
    """A name cut at its newline names a bot the fleet never listed."""
    payload = state_payload(CHOSEN_STATE)
    payload["bot_ids"] = [NEWLINE_NAME]
    payload["filled_rows"] = [0]
    payload["plan"]["target_row"] = 0
    parts = draw_panel(browser, payload)
    assert parts_named(parts, "selection-row")[0]["text"] == NEWLINE_NAME


def test_two_bots_of_the_same_name_are_drawn_as_two_rows(browser: Browser):
    """One row for two bots would hide the second from the operator."""
    payload = state_payload(CHOSEN_STATE)
    payload["bot_ids"] = ["bot-alpha", "bot-alpha"]
    payload["filled_rows"] = [0, 1]
    payload["plan"]["target_row"] = 0
    parts = draw_panel(browser, payload)
    rows = parts_named(parts, "selection-row")
    assert [one["attrs"]["data-row"] for one in rows] == ["0", "1"]
    assert [one["attrs"]["data-bot"] for one in rows] == ["bot-alpha", "bot-alpha"]


def test_a_fleet_of_no_bots_draws_the_panel_with_no_row(browser: Browser):
    """An empty fleet must still draw the panel, not an empty page."""
    parts = draw_panel(browser, state_payload("no_bots_at_all"))
    assert parts_named(parts, "selection-row") == []
    assert parts_named(parts, "bot-selection")[0]["attrs"]["data-bot-count"] == "0"


def test_the_fault_count_the_panel_draws_is_the_count_it_measured(browser: Browser):
    """A count wired to nothing would draw zero on a payload full of faults."""
    healthy = draw_panel(browser, state_payload(CHOSEN_STATE))
    assert parts_named(healthy, "bot-selection")[0]["attrs"]["data-fault-count"] == "0"
    payload = state_payload(CHOSEN_STATE)
    payload["filled_rows"] = payload["filled_rows"] + [9]
    parts = draw_panel(browser, payload)
    drawn = parts_named(parts, "bot-selection")[0]["attrs"]["data-fault-count"]
    assert int(drawn) > 0, drawn
    assert len(parts_named(parts, "selection-orphan")) == 1, parts


def test_the_panel_names_no_chosen_row_when_the_surface_chose_none(browser: Browser):
    """A drawn zero would read as row zero when no row was chosen at all."""
    chosen = draw_panel(browser, state_payload(CHOSEN_STATE))
    assert "data-target-row" in parts_named(chosen, "bot-selection")[0]["attrs"]
    parts = draw_panel(browser, state_payload("the_bot_left"))
    panel = parts_named(parts, "bot-selection")[0]["attrs"]
    assert "data-target-row" not in panel, panel
    assert [
        one["attrs"]["data-chosen"] for one in parts_named(parts, "selection-row")
    ] == ["false"] * len(FLEET)


def test_a_row_border_matches_a_probe_built_from_the_whole_declaration(
    browser: Browser,
):
    """A typed width would pass on one host and fail on the next."""
    parts = draw_panel(browser, state_payload(CHOSEN_STATE))
    row = parts_named(parts, "selection-row")[0]
    tokens = token_payload()["tokens"]
    whole = (
        "border-style: solid; border-width: "
        + str(tokens["FOCUS_RING_WIDTH"])
        + "px; min-height: "
        + str(tokens["TARGET_COMFORTABLE"])
        + "px;"
    )
    probe = browser.parsed(
        "window.probeStyle(" + json.dumps(whole) + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert row["style"]["borderTopWidth"] == probe["borderTopWidth"]
    assert row["style"]["borderTopStyle"] == probe["borderTopStyle"]
    assert row["style"]["minHeight"] == probe["minHeight"]


def test_the_whole_declaration_probe_would_see_a_border_of_another_width(
    browser: Browser,
):
    """The width comparison would miss a border drawn at another width."""
    parts = draw_panel(browser, state_payload(CHOSEN_STATE))
    row = parts_named(parts, "selection-row")[0]
    tokens = token_payload()["tokens"]
    other = (
        "border-style: solid; border-width: "
        + str(tokens["FOCUS_RING_OFFSET"] + tokens["FOCUS_RING_WIDTH"])
        + "px;"
    )
    probe = browser.parsed(
        "window.probeStyle(" + json.dumps(other) + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert row["style"]["borderTopWidth"] != probe["borderTopWidth"]


def test_the_step_name_is_drawn_heavier_than_the_values_beside_it(browser: Browser):
    """A name joined to its values as one string would carry its own markup."""
    parts = draw_panel(browser, state_payload(CHOSEN_STATE))
    names = parts_named(parts, "step-name")
    values = parts_named(parts, "step-argument")
    assert names and values, parts
    tokens = token_payload()["tokens"]
    assert names[0]["style"]["fontWeight"] == str(tokens["WEIGHT_BOLD"])
    assert values[0]["style"]["fontWeight"] == str(tokens["WEIGHT_REGULAR"])
    assert names[0]["style"]["color"] != values[0]["style"]["color"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_row_number_the_surface_publishes_reaches_a_drawn_element(
    browser: Browser, state: str
):
    """A published row number nothing draws is a value the operator never sees."""
    payload = state_payload(state)
    parts = draw_panel(browser, payload)
    marked = [
        int(one["attrs"]["data-row"])
        for one in parts_named(parts, "selection-row")
        if one["attrs"]["data-filled"] == "true"
    ]
    orphans = [
        int(one["attrs"]["data-row"]) for one in parts_named(parts, "selection-orphan")
    ]
    assert sorted(marked + orphans) == sorted(payload["filled_rows"]), (
        state,
        marked,
        orphans,
    )


def test_the_drawn_row_check_would_see_a_row_number_nothing_draws(browser: Browser):
    """The drawn-row check would miss a row number the panel left out."""
    payload = state_payload(CHOSEN_STATE)
    payload["filled_rows"] = payload["filled_rows"] + [9]
    parts = draw_panel(browser, payload)
    marked = [
        int(one["attrs"]["data-row"])
        for one in parts_named(parts, "selection-row")
        if one["attrs"]["data-filled"] == "true"
    ]
    orphans = [
        int(one["attrs"]["data-row"]) for one in parts_named(parts, "selection-orphan")
    ]
    assert orphans == [9]
    assert sorted(marked + orphans) == sorted(payload["filled_rows"])
    selector = json.dumps("[data-part=selection-orphan]")
    browser.js("window.HOST.querySelector(" + selector + ").remove();")
    again = json.loads(browser.js(READ_PARTS))
    assert parts_named(again, "selection-orphan") == []
