"""The React Positions Held tab, against positions_held_surface.py."""

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

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import positions_held_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "positions_held.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorPositionsHeld."
SETTER = "acervatorSetPositionsHeld"

#: The merged modules the page loads beside this one, needed at call time.
SHARED_MODULES = (
    WEB / "shared_widgets.js",
    WEB / "table_cells.js",
    WEB / "header_strip.js",
)

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 3
HOST_WIDTH_PX = 1200
HOST_HEIGHT_PX = 700
PROBE_TEXT_REPEAT = 8

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
SWAPPED_ALPHA = "#123a63ff"
BYTE_ALPHA = "rgba(18, 58, 99, 128)"
OTHER_COLOUR = "#7c1fa2"
UNKNOWN_BOT = "no-such-bot"

BASE_CURRENCY = "BTC"
LOOP_NAME = "a-running-loop"


def position(pair: str, state: str, delta: float, **rest: Any) -> dict:
    """One open Extractor position, in the keys the tab surface reads."""
    found = {
        surface.PAIR_KEY: pair,
        surface.STATE_KEY: state,
        surface.TIER_KEY: 2,
        surface.ALT_UNITS_KEY: 1.25,
        surface.ENTRY_KEY: 140.5,
        surface.CURRENT_KEY: 120.25,
        surface.DELTA_KEY: delta,
        surface.CORRECTIONS_KEY: 1,
    }
    found.update(rest)
    return found


IN_FLIGHT = "in_flight"

THREE_POSITIONS = [
    position("SOL-BTC", surface.STATE_DRAWDOWN, -14.41),
    position("ADA-BTC", surface.STATE_BULLISH_EXIT, 21.43, tier=1, alt_units=400.0),
    position("LINK-BTC", IN_FLIGHT, 0.0, tier=3, corrections_fired=0),
]


def bot(positions: Any = None, **rest: Any) -> dict:
    """One Extractor bot the tab reads, in the readings the surface takes."""
    found = {
        "base_currency": BASE_CURRENCY,
        "chunk_size_usd": 250.0,
        "chunk_free_base": 0.004,
        "chunk_size_base": 0.0025,
        "extracted_total": 0.00031,
        "pool_color": surface.POOL_YELLOW,
        "positions": list(positions or []),
    }
    found.update(rest)
    return found


LOADED = {"reset": True, "bot": bot(THREE_POSITIONS)}
WITH_LOOP = dict(LOADED, manager={"async_loop": LOOP_NAME})
FIRE_YES = {"fire_pair": "ADA-BTC", "fire_answer": surface.YES_BUTTON_VALUE}
FIRE_NO = {"fire_pair": "ADA-BTC", "fire_answer": surface.NO_BUTTON_VALUE}

STATES: dict = {
    "fresh": [{"reset": True}],
    "empty": [{"reset": True, "bot": bot()}],
    "loaded": [LOADED],
    "unknown_pool": [{"reset": True, "bot": bot(THREE_POSITIONS, pool_color="mauve")}],
    "declined": [LOADED, FIRE_NO],
    "no_loop": [LOADED, FIRE_YES],
    "dispatched": [WITH_LOOP, FIRE_YES],
}
STATE_NAMES = tuple(STATES)
DRAWN_STATES = ("empty", "loaded", "unknown_pool", "dispatched")
BOX_STATES = ("declined", "no_loop", "dispatched")


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def at_dotted(node: Any, path: Any) -> Any:
    """The value ``path`` names, each step a bag key or a list place."""
    for step in path:
        node = node[step]
    return node


def build(steps: list) -> dict:
    """One payload, each step driving the same tab in the order given."""
    found: dict = {}
    for step in steps:
        found = surface.view_model(step)
    return as_json(found)


def state_payload(name: str) -> dict:
    return build(STATES[name])


def schedule_failed_payload() -> dict:
    """The fourth fire path, which the bridge handler offers no parameter for."""
    model = surface.PositionsHeldTabModel(
        bot=surface.BotSource(
            base_currency=BASE_CURRENCY,
            pool_color_name=surface.POOL_YELLOW,
            positions=THREE_POSITIONS,
        ),
        manager=surface.ManagerSource(LOOP_NAME),
        schedule=surface.ScheduleSink(raises=RuntimeError("no room on the loop")),
    )
    return as_json(
        surface.build_view_model(model, True, "ADA-BTC", surface.YES_BUTTON_VALUE)
    )


def token_payload() -> dict:
    return as_json(dss.view_model({}))


class JsRuntime(JsEngine):
    """A QJSEngine holding the tab module and the merged pieces beside it."""

    module_path = MODULE_PATH
    setter = SETTER

    def __init__(self, engine: Any, source: str) -> None:
        super().__init__(engine, source)
        for path in SHARED_MODULES:
            loaded = engine.evaluate(path.read_text(encoding="utf-8"), path.name)
            assert not loaded.isError(), path.name + " -> " + loaded.toString()

    def called(self, method: str, value: Any) -> Any:
        self.bind_json("ARG", value)
        return self.json(API + method + "(JSON.parse(ARG))")

    def called_two(self, method: str, first: Any, second: Any) -> Any:
        self.bind_json("ONE", first)
        self.bind_json("TWO", second)
        return self.json(API + method + "(JSON.parse(ONE), JSON.parse(TWO))")


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


def test_the_fourth_fire_path_reaches_the_module_the_same_way(js: JsRuntime):
    """A hand-off that raises is a state only the surface classes can drive."""
    payload = schedule_failed_payload()
    report = js.push(payload)
    assert payload["fire_outcome"] == surface.OUTCOME_SCHEDULE_FAILED
    assert sorted(set(payload) - set(declared_fields(js))) == []
    assert report["faults"] == []


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = state_payload("loaded")
    payload["only_on_the_surface"] = []
    js.push(payload)
    assert sorted(set(payload) - set(declared_fields(js))) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    payload = state_payload("loaded")
    assert payload.pop("pool_color_hex") is not None
    js.push(payload)
    assert sorted(set(declared_fields(js)) - set(payload)) == ["pool_color_hex"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = state_payload("loaded")
    payload["accessible_name"] = LONG_NAME
    js.push(payload)
    original = state_payload("loaded")
    differing = sorted(
        name for name in original if js.called("field", name) != original[name]
    )
    assert differing == ["accessible_name"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    table = payload["positions_table"]
    drawn = payload["summary_rows"]
    assert report["declared"] == {
        "fields": len(payload),
        "columns": table["column_count"],
        "cells": table["cell_column_count"],
        "rows": table["row_count"],
        "labels": len(payload["labels"]) + len(surface_row_formats()),
        "actions": len(payload["actions"]),
        "answers": 3,
        "outcomes": len(payload["outcomes"]),
    }, state
    assert report["held"] == dict(
        report["declared"],
        columns=len(table["columns"]),
        cells=len(table["rows"][0]) if table["rows"] else 0,
        rows=len(table["rows"]),
        labels=len(drawn),
    ), state


def surface_row_formats() -> list:
    """The three money row formats the summary builds its labels from."""
    return [
        surface.CHUNK_SIZE_ROW_FORMAT,
        surface.CHUNK_FREE_ROW_FORMAT,
        surface.EXTRACTED_ROW_FORMAT,
    ]


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("loaded")
    declared = len(payload)
    del payload["accessible_name"]
    report = js.push(payload)
    assert report["declared"]["fields"] == declared
    assert report["held"]["fields"] == declared - 1
    assert [one["field"] for one in report["faults"]] == ["accessible_name"]


DROPPED_ROWS = {
    "rows": ("positions_table", "rows"),
    "columns": ("positions_table", "columns"),
}


@pytest.mark.parametrize("counted", sorted(DROPPED_ROWS))
def test_a_dropped_row_shortens_the_held_count_not_the_declared_count(
    js: JsRuntime, counted: str
):
    payload = state_payload("loaded")
    at_dotted(payload, DROPPED_ROWS[counted]).pop()
    report = js.push(payload)
    assert report["declared"][counted] == report["held"][counted] + 1


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
    """A payload value that changes kind in transit reads right and paints wrong."""
    payload = state_payload(state)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json(API + "kinds()")
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
    payload = state_payload("loaded")
    payload["pool_color_hex"] = [payload["pool_color_hex"]]
    js.push(payload)
    expected = python_kinds(state_payload("loaded"))
    actual = js.json(API + "kinds()")
    named = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert named == ["pool_color_hex"]


def test_the_type_walk_names_a_scalar_where_a_table_row_belongs(js: JsRuntime):
    """A scalar where the payload lists a row must not read as that row."""
    payload = state_payload("loaded")
    payload["positions_table"]["rows"][1] = 7
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("positions_table.rows.1") == "number"
    assert "positions_table.rows.1.0" not in actual
    payload["positions_table"]["rows"][1] = [None, None]
    js.push(payload)
    assert js.json(API + "kinds()").get("positions_table.rows.1.0") == "null"


def test_the_type_walk_names_a_null_where_a_row_colour_list_belongs(js: JsRuntime):
    """A null where the payload lists a row's colours must not read as that list."""
    payload = state_payload("loaded")
    payload["positions_table"]["row_colors"][0] = None
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("positions_table.row_colors.0") == "null"
    assert "positions_table.row_colors.0.1" not in actual
    assert js.json(API + "rowColors(0)") == []


PLAIN_TYPES = (str, int, float, bool, type(None))


def not_plain_data(payload: Any) -> list:
    """Every dotted path in payload whose value is not plain data."""
    found: list = []

    def walk(path: str, value: Any) -> None:
        if isinstance(value, dict):
            for name, inner in value.items():
                walk(f"{path}.{name}" if path else str(name), inner)
            return
        if isinstance(value, (list, tuple)):
            for at, inner in enumerate(value):
                walk(f"{path}.{at}", inner)
            return
        if not isinstance(value, PLAIN_TYPES):
            found.append(path)

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_surface_publishes_no_live_object(state: str):
    """A live object is what the plain data walk on this payload must never find."""
    raw: dict = {}
    for step in STATES[state]:
        raw = surface.view_model(step)
    assert not_plain_data(raw) == [], f"{state} publishes {not_plain_data(raw)}"


def test_the_plain_data_walk_names_a_live_object_put_on_the_payload():
    raw = surface.view_model({"reset": True})
    raw["boxes"] = [{"icon": surface.PositionsHeldTabModel()}]
    assert not_plain_data(raw) == ["boxes.0.icon"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    js.push(state_payload("loaded"))
    js.run(
        SETTER
        + "(Object.assign("
        + API
        + "payload(), { pool_color: function () {} }));"
    )
    assert js.json(API + "notPlainData()") == [
        {"path": "pool_color", "kind": "function"}
    ]


def shown_values() -> set:
    """Every string the tab paints or shows as a tooltip, from every state."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        for row in payload["summary_rows"]:
            found |= {one for one in row if isinstance(one, str)}
        table = payload["positions_table"]
        found |= set(table["columns"])
        for row in table["rows"]:
            found |= {one for one in row if isinstance(one, str)}
        for box in payload["boxes"]:
            found |= {box["title"], box["text"]}
        found |= {payload["empty_label"]["text"], payload["footer_label"]["text"]}
        found |= {payload["pool_label"]["text"], payload["summary_group"]["title"]}
        found |= {payload["fire_button"]["text"]}
        found |= set(payload["fire_button"]["pairs"])
        found |= {one for one in [payload["fire_outcome"]] if isinstance(one, str)}
        for bag in ("labels", "texts", "titles", "formats", "colors", "pool_color_map"):
            found |= {one for one in payload[bag].values() if isinstance(one, str)}
        found |= set(payload["pool_names"]) | set(payload["state_names"])
        found |= {payload["pool_color"], payload["pool_color_hex"]}
    return {one for one in found if one}


def published_strings() -> set:
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, str):
            found.add(node)
        elif isinstance(node, dict):
            for key, value in node.items():
                found.add(str(key))
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for name in STATE_NAMES:
        walk(state_payload(name))
    return {one for one in found if one}


def token_values() -> set:
    found: set = set()
    for value in token_payload().values():
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, dict):
            found |= {one for one in value.values() if isinstance(one, str)}
    return {one for one in found if one}


SHOWN_VALUES = shown_values()
PUBLISHED_STRINGS = published_strings()
TOKEN_VALUES = token_values()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

BARE = state_payload("fresh")
WITH_BOX = state_payload("dispatched")

#: NAMED_WORDS lists every published string the module may write.
NAMED_WORDS = sorted(
    set(BARE)
    | set(BARE["actions"])
    | set(BARE["button_values"])
    | set(BARE["container"])
    | set(BARE["empty_label"])
    | set(BARE["footer_label"])
    | set(BARE["fire_button"])
    | set(BARE["formats"])
    | set(BARE["labels"])
    | set(BARE["pool_label"])
    | set(BARE["positions_table"])
    | set(BARE["summary_form"])
    | set(BARE["summary_group"])
    | set(WITH_BOX["boxes"][0])
    | {surface.METHOD}
)


def caught_by_scan(source: str) -> set:
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


def test_the_module_writes_no_number_colour_shown_value_or_token_value():
    """A literal typed here is a second source for a value the surface owns."""
    assert caught_by_scan(MODULE_SOURCE) == set(), (
        "positions_held.js writes values of its own: numbers "
        f"{MODULE_LITERALS['numbers']}, colours {HEX_COLOUR.findall(MODULE_SOURCE)}, "
        f"shown {sorted(set(MODULE_LITERALS['strings']) & SHOWN_VALUES)}, tokens "
        f"{sorted(set(MODULE_LITERALS['strings']) & TOKEN_VALUES)}, slashes "
        f"{MODULE_LITERALS['slashes']}"
    )


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert set(written) <= set(NAMED_WORDS), (
        "the module names published strings the list does not allow: "
        f"{sorted(set(written) - set(NAMED_WORDS))}"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_tab_shows():
    overlap = sorted(set(NAMED_WORDS) & SHOWN_VALUES)
    assert not overlap, f"these named words are values the tab shows: {overlap}"


WRITTEN_LINES: dict = {
    "colour": 'var written = "' + OTHER_COLOUR + '";',
    "drawdown_colour": 'var written = "' + surface.DRAWDOWN_COLOR + '";',
    "open_colour": 'var written = "' + surface.OPEN_STATE_COLOR + '";',
    "pool_row_label": 'var written = "' + surface.POOL_ROW_LABEL + '";',
    "group_title": 'var written = "' + surface.SUMMARY_GROUP_TITLE + '";',
    "empty_note": 'var written = "' + surface.EMPTY_TEXT + '";',
    "footer_note": 'var written = "' + surface.FOOTER_TEXT + '";',
    "button_words": 'var written = "' + surface.FIRE_BUTTON_TEXT + '";',
    "column_words": 'var written = "' + surface.COLUMNS[0] + '";',
    "pool_name": 'var written = "' + surface.POOL_GREEN + '";',
    "confirm_title": 'var written = "' + surface.CONFIRM_TITLE + '";',
    "yes_value": "var written = " + str(surface.YES_BUTTON_VALUE) + ";",
    "spacing": "var written = " + str(surface.CONTENT_SPACING_PX) + ";",
    "button_height": "var written = " + str(surface.FIRE_BUTTON_HEIGHT_PX) + ";",
    "number": "var written = 12;",
    "token_value": 'var written = "' + str(dss.PRIMARY) + '";',
    "regex": "var written = /ab+c/;",
}


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_line(kind: str):
    assert caught_by_scan(WRITTEN_LINES[kind]), f"the scan reported nothing on {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals("// " + OTHER_COLOUR + '\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_written_literal_is_caught_in_the_module_file_itself():
    """The original is read inside the swap so no other worker's copy is written."""
    original = MODULE_PATH.read_bytes()
    before = hashlib.sha256(original).hexdigest()
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
    for kind, line in sorted(WRITTEN_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof " + SETTER) == "function", kind


def payload_sheets(payload: dict) -> list:
    """The four style sheets the tab applies, from every place carrying one."""
    return [
        payload["pool_label"]["style_sheet"],
        payload["empty_label"]["style_sheet"],
        payload["footer_label"]["style_sheet"],
        payload["fire_button"]["style_sheet"],
    ]


def payload_bare_colours(payload: dict) -> list:
    """Every bare colour the payload carries, cell by cell and name by name."""
    found = list(payload["colors"].values()) + list(payload["pool_color_map"].values())
    found += [payload["pool_color_hex"], payload["pool_unknown_hex"]]
    for row in payload["positions_table"]["row_colors"]:
        found += [one for one in row if one is not None]
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_the_tab_carries_is_swept_for_the_alpha_order_fault(
    js: JsRuntime, state: str
):
    """Every published colour is swept for the eight-digit shape Qt reads first."""
    payload = state_payload(state)
    js.push(payload)
    swept = list(payload_bare_colours(payload))
    for sheet in payload_sheets(payload):
        swept += js.called("hexRuns", sheet)
    assert len(swept) > len(payload["colors"])
    assert [
        one
        for one in js.json(API + "faults()")
        if one["fault"] in ("swapped-alpha", "byte-alpha")
    ] == [], f"{state} carries a colour CSS would read as another colour"


SWEPT_BARE = {
    "the drawdown red": ("colors", "drawdown"),
    "the bullish exit amber": ("colors", "bullish_exit"),
    "the open green": ("colors", "open_state"),
    "the pool green": ("pool_color_map", surface.POOL_GREEN),
    "the pool amber": ("pool_color_map", surface.POOL_YELLOW),
    "the pool red": ("pool_color_map", surface.POOL_RED),
}


@pytest.mark.parametrize("case", sorted(SWEPT_BARE))
def test_the_alpha_sweep_names_one_bare_colour_written_with_eight_digits(
    js: JsRuntime, case: str
):
    bag, name = SWEPT_BARE[case]
    payload = state_payload("loaded")
    payload[bag][name] = SWAPPED_ALPHA
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA], case


def test_the_alpha_sweep_names_one_cell_colour_written_with_eight_digits(
    js: JsRuntime,
):
    """A cell publishes a bare colour where the pool row publishes a whole sheet."""
    payload = state_payload("loaded")
    payload["positions_table"]["row_colors"][1][1] = SWAPPED_ALPHA
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["where"] for one in swapped] == ["row:1"]


def swap_nth_colour(sheet: str, at: int, value: str) -> str:
    """``sheet`` with only its ``at``-th colour replaced by ``value``."""
    seen = {"n": -1}

    def pick(match: Any) -> str:
        seen["n"] += 1
        return value if seen["n"] == at else match.group(0)

    found = HEX_COLOUR.sub(pick, sheet)
    assert found != sheet, f"no colour sits at {at} of {sheet}"
    return found


SWEPT_SHEETS: dict = {
    "the pool row colour": (("pool_label", "style_sheet"), 0),
    "the empty note colour": (("empty_label", "style_sheet"), 0),
    "the footer colour": (("footer_label", "style_sheet"), 0),
    "the fire button ground": (("fire_button", "style_sheet"), 0),
    "the fire button hover ground": (("fire_button", "style_sheet"), 1),
}


@pytest.mark.parametrize("case", sorted(SWEPT_SHEETS))
def test_the_alpha_sweep_reads_a_colour_inside_one_style_sheet(
    js: JsRuntime, case: str
):
    """A colour inside a hover block is one no declaration walk would reach."""
    path, at = SWEPT_SHEETS[case]
    payload = state_payload("loaded")
    node = at_dotted(payload, path[:-1])
    node[path[-1]] = swap_nth_colour(node[path[-1]], at, SWAPPED_ALPHA)
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA], case


def test_the_declaration_walk_alone_never_reaches_the_hover_ground(js: JsRuntime):
    """The hover colour proves the sweep must split the raw sheet, not the walk."""
    payload = state_payload("loaded")
    sheet = payload["fire_button"]["style_sheet"]
    walked = js.called("paintedStyle", sheet)
    runs = js.called("hexRuns", sheet)
    assert len(runs) == 2, f"the raw sweep read {runs}"
    assert runs[1] not in json.dumps(walked), (
        "the declaration walk reached the hover ground, so the raw sweep is not "
        f"the only way to it: {walked}"
    )


def test_the_alpha_sweep_reads_an_rgba_alpha_qt_counted_in_whole_bytes(js: JsRuntime):
    payload = state_payload("loaded")
    payload["colors"]["drawdown"] = BYTE_ALPHA
    report = js.push(payload)
    byte = [one for one in report["faults"] if one["fault"] == "byte-alpha"]
    assert [one["detail"] for one in byte] == [BYTE_ALPHA]


@pytest.mark.parametrize("byte,wanted", ((0, 0.0), (255, 1.0), (128, 128 / 255)))
def test_the_alpha_fraction_answers_the_share_css_reads(
    js: JsRuntime, byte: int, wanted: float
):
    assert js.called("alphaFraction", byte) == pytest.approx(wanted)


def test_the_alpha_sweep_reads_a_gradient_no_browser_stylesheet_runs(js: JsRuntime):
    payload = state_payload("loaded")
    payload["empty_label"]["style_sheet"] = "background: qlineargradient(x1: 0);"
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"] if one["fault"] == "not-css"] == [
        "not-css"
    ]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_bag_the_surface_publishes_carries_a_key_a_browser_would_move(
    js: JsRuntime, state: str
):
    """A digit key is listed before every worded key, which loses the written order."""
    js.push(state_payload(state))
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "reordered-key"
    ] == []


def test_the_bag_order_check_names_a_digit_key_put_into_a_published_bag(js: JsRuntime):
    payload = state_payload("loaded")
    payload["colors"]["0"] = payload["colors"]["drawdown"]
    report = js.push(payload)
    moved = [one for one in report["faults"] if one["fault"] == "reordered-key"]
    assert [one["detail"] for one in moved] == ["0"]


def test_every_order_the_tab_depends_on_arrives_as_a_list(js: JsRuntime):
    """A list keeps its order where a bag hands its keys back rearranged."""
    payload = state_payload("loaded")
    js.push(payload)
    assert js.json(API + "poolNames()") == payload["pool_names"]
    assert js.json(API + "outcomes()") == payload["outcomes"]
    assert js.json(API + "columnNames()") == payload["positions_table"]["columns"]
    assert js.json(API + "firePairs()") == payload["fire_button"]["pairs"]
    assert js.json(API + "actionNames()") == list(payload["actions"])


def test_the_action_check_names_a_wired_name_the_payload_never_declared(js: JsRuntime):
    payload = state_payload("loaded")
    payload["actions"]["no_such_signal"] = "nothing"
    report = js.push(payload)
    unknown = [one for one in report["faults"] if one["fault"] == "unknown-action"]
    assert [one["detail"] for one in unknown] == ["no_such_signal"]


def test_the_action_check_names_a_wired_name_the_payload_dropped(js: JsRuntime):
    payload = state_payload("loaded")
    dropped = list(payload["actions"])[0]
    del payload["actions"][dropped]
    report = js.push(payload)
    missing = [
        one
        for one in report["faults"]
        if one["fault"] == "missing" and one["field"] == "actions"
    ]
    assert [one["detail"] for one in missing] == [dropped]


def test_the_label_bag_is_shorter_than_the_rows_every_drawn_state_carries(
    js: JsRuntime,
):
    """One published label is paired against four drawn rows, so pairing is by name."""
    payload = state_payload("loaded")
    js.push(payload)
    assert len(payload["labels"]) == 1
    assert len(payload["summary_rows"]) == 4
    published = js.json(API + "publishedLabels()")
    assert len(published) == 4
    assert published[0] == payload["labels"]["pool_row"]
    assert js.json(API + "faults()") == []


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_summary_row_is_found_by_its_own_label(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for name, value in payload["summary_rows"]:
        assert js.called("summaryValue", name) == value
        assert js.called("labelNamed", name) is not None


def test_only_the_pool_row_carries_a_whole_style_sheet(js: JsRuntime):
    """Three money rows publish no sheet at all, and the pool row publishes one."""
    payload = state_payload("loaded")
    js.push(payload)
    styled = [
        name
        for name, _value in payload["summary_rows"]
        if js.called("summaryStyleNamed", name) is not None
    ]
    assert styled == [payload["labels"]["pool_row"]]
    assert (
        js.called("summaryStyleNamed", payload["labels"]["pool_row"])
        == payload["pool_label"]["style_sheet"]
    )


def test_the_label_check_names_a_row_whose_label_the_payload_never_published(
    js: JsRuntime,
):
    payload = state_payload("loaded")
    payload["summary_rows"][2][0] = LONG_NAME
    report = js.push(payload)
    unnamed = [one for one in report["faults"] if one["fault"] == "unnamed-row"]
    assert [one["where"] for one in unnamed] == ["summary:2"]


def test_the_nine_column_names_are_counted_against_the_eight_cells_a_row_holds(
    js: JsRuntime,
):
    """The last column carries a button, so the two lists differ by one on purpose."""
    payload = state_payload("loaded")
    table = payload["positions_table"]
    js.push(payload)
    assert len(table["columns"]) == table["column_count"]
    assert table["fire_column"] == table["cell_column_count"]
    assert len(table["columns"]) == table["cell_column_count"] + 1
    for row in table["rows"]:
        assert len(row) == table["cell_column_count"]
    assert js.json(API + "faults()") == []


COUNT_FAULTS = {
    "a short row": (("positions_table", "rows", 0), "rows"),
    "a short colour row": (("positions_table", "row_colors", 1), "row_colors"),
    "a short pair list": (("fire_button", "pairs"), "pairs"),
}


@pytest.mark.parametrize("case", sorted(COUNT_FAULTS))
def test_the_count_check_names_a_row_shorter_than_the_columns_it_fills(
    js: JsRuntime, case: str
):
    path, field = COUNT_FAULTS[case]
    payload = state_payload("loaded")
    at_dotted(payload, path).pop()
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "short-list" and one["field"] == field
    ]
    assert named, f"{case} reported {report['faults']}"


@pytest.mark.parametrize("state", ("loaded", "dispatched"))
def test_each_table_row_is_named_by_the_pair_its_own_button_closes(
    js: JsRuntime, state: str
):
    """A row's place is not its name, because a Fire closes the pair it names."""
    payload = state_payload(state)
    js.push(payload)
    named = js.json(API + "rowIdentities()")
    assert len(named) == payload["positions_table"]["row_count"]
    assert [one["name"] for one in named] == payload["fire_button"]["pairs"]
    for one in named:
        assert (
            js.called("rowNamed", one["name"])
            == payload["positions_table"]["rows"][one["at"]]
        )


def test_a_position_keeps_its_own_pair_when_the_rows_arrive_reordered(js: JsRuntime):
    """Reordering renames no position, so each pair keeps its own row."""
    payload = state_payload("loaded")
    js.push(payload)
    first = js.json(API + "rowIdentities()")
    payload["positions_table"]["rows"].reverse()
    payload["positions_table"]["row_colors"].reverse()
    payload["fire_button"]["pairs"].reverse()
    js.push(payload)
    second = js.json(API + "rowIdentities()")
    assert sorted(one["name"] for one in first) == sorted(one["name"] for one in second)
    assert [one["name"] for one in first] != [one["name"] for one in second]


def test_the_identity_check_names_two_rows_holding_one_pair(js: JsRuntime):
    payload = state_payload("loaded")
    payload["fire_button"]["pairs"][1] = payload["fire_button"]["pairs"][0]
    report = js.push(payload)
    duplicate = [one for one in report["faults"] if one["fault"] == "duplicate-name"]
    assert [one["where"] for one in duplicate] == ["row:1"]


@pytest.mark.parametrize("at", (0, 1, 2))
def test_each_cell_is_read_by_its_own_column_name_and_not_by_its_place(
    js: JsRuntime, at: int
):
    payload = state_payload("loaded")
    table = payload["positions_table"]
    js.push(payload)
    for column, name in enumerate(table["columns"][: table["cell_column_count"]]):
        assert js.called_two("cellNamed", at, name) == table["rows"][at][column]
    assert js.json(API + "stateColumnName()") == table["columns"][table["state_column"]]
    assert js.json(API + "deltaColumnName()") == table["columns"][table["delta_column"]]


def test_the_cell_name_check_follows_a_column_name_that_moved(js: JsRuntime):
    """A read by place would answer the same cell after the column name moved."""
    payload = state_payload("loaded")
    table = payload["positions_table"]
    name = table["columns"][table["state_column"]]
    js.push(payload)
    before = js.called_two("cellNamed", 0, name)
    assert before == table["rows"][0][table["state_column"]]
    table["columns"].reverse()
    js.push(payload)
    after = js.called_two("cellNamed", 0, name)
    assert after != before, "the read stayed on the old place"
    assert after == table["rows"][0][table["columns"].index(name)]


def test_the_pool_colour_check_names_a_hex_the_published_map_never_gives(
    js: JsRuntime,
):
    payload = state_payload("loaded")
    payload["pool_color_hex"] = OTHER_COLOUR
    report = js.push(payload)
    assert [
        one["field"] for one in report["faults"] if one["fault"] == "disagrees"
    ] == ["pool_color_hex"]


def test_a_pool_name_the_map_has_none_of_takes_the_published_unknown_colour(
    js: JsRuntime,
):
    payload = state_payload("unknown_pool")
    report = js.push(payload)
    assert payload["pool_color_hex"] == payload["pool_unknown_hex"]
    assert report["faults"] == []


@pytest.mark.parametrize("name", ("yes", "no", "ok"))
def test_each_message_box_answer_carries_the_value_the_surface_publishes(
    js: JsRuntime, name: str
):
    payload = state_payload("dispatched")
    js.push(payload)
    assert js.called("buttonValue", name) == payload["button_values"][name]


@pytest.mark.parametrize("state", BOX_STATES)
def test_each_message_box_offers_the_answers_its_own_button_mask_names(
    js: JsRuntime, state: str
):
    """Only the box Qt built from Yes and No carries a second answer."""
    payload = state_payload(state)
    js.push(payload)
    offered = js.json(API + "boxes()")
    assert offered, f"{state} raised no box"
    for at, box in enumerate(payload["boxes"]):
        asks = box["buttons_value"] == payload["button_values"]["confirm_buttons"]
        names = js.json(API + "boxAnswers(" + API + "boxes()[" + str(at) + "])")
        assert names == (["yes", "no"] if asks else ["ok"]), f"{state} box {at}"


def test_the_answer_check_names_a_mask_that_offers_no_answer_at_all(js: JsRuntime):
    payload = state_payload("declined")
    payload["boxes"][0]["buttons_value"] = 0
    report = js.push(payload)
    assert [
        one["field"] for one in report["faults"] if one["fault"] == "short-list"
    ] == ["buttons_value"]


def test_the_answer_check_names_a_confirm_default_the_mask_never_offers(js: JsRuntime):
    payload = state_payload("loaded")
    payload["button_values"]["confirm_default"] = payload["button_values"]["ok"]
    report = js.push(payload)
    assert [
        one["field"] for one in report["faults"] if one["fault"] == "disagrees"
    ] == ["confirm_default"]


def test_the_box_check_names_a_title_the_payload_never_published(js: JsRuntime):
    payload = state_payload("declined")
    payload["boxes"][0]["title"] = LONG_NAME
    report = js.push(payload)
    unnamed = [one for one in report["faults"] if one["fault"] == "unnamed-row"]
    assert [one["where"] for one in unnamed] == ["box:0"]


def test_the_outcome_check_names_a_word_the_published_outcomes_have_none_of(
    js: JsRuntime,
):
    payload = state_payload("dispatched")
    payload["fire_outcome"] = LONG_NAME
    report = js.push(payload)
    assert [
        one["field"] for one in report["faults"] if one["fault"] == "disagrees"
    ] == ["fire_outcome"]


@pytest.mark.parametrize("state", ("declined", "no_loop", "dispatched"))
def test_each_fire_path_publishes_the_outcome_the_surface_names_for_it(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    assert payload["fire_outcome"] in payload["outcomes"]
    assert report["faults"] == []


@pytest.mark.parametrize("dropped", (True, False))
@pytest.mark.parametrize("name", sorted(BARE))
def test_a_field_the_payload_drops_or_nulls_is_reported_and_the_module_answers(
    js: JsRuntime, name: str, dropped: bool
):
    """A payload the surface would never send must report, never raise."""
    payload = state_payload("loaded")
    if dropped:
        del payload[name]
    else:
        payload[name] = None
    report = js.push(payload)
    assert isinstance(report["faults"], list), name
    if dropped:
        assert [
            one
            for one in report["faults"]
            if one["fault"] == "missing" and one["field"] == name
        ], name
    assert js.json(API + "isLoaded()") is True, name
    assert isinstance(js.json(API + "rowIdentities()"), list), name
    assert isinstance(js.json(API + "drawnLabels()"), list), name
    assert isinstance(js.json(API + "boxes()"), list), name
    assert isinstance(js.json(API + "kinds()"), dict), name
    assert isinstance(js.json(API + "sheets()"), list), name
    assert isinstance(js.json(API + "cellColours()"), list), name


HOSTILE_VALUES: dict = {
    "a number where text belongs": ("pool_color", 7),
    "text where a number belongs": ("pool_color_hex", ["a colour"]),
    "nan": ("accessible_name", "nan"),
    "inf": ("accessible_name", "inf"),
    "minus inf": ("accessible_name", "-inf"),
    "a huge integer": ("accessible_name", 10**24),
    "a two hundred character pool name": ("pool_color", LONG_NAME),
    "markup in the pool name": ("pool_color", MARKUP_NAME),
    "a newline in the pool name": ("pool_color", NEWLINE_NAME),
    "summary rows is a bag": ("summary_rows", {}),
    "the table is a list": ("positions_table", []),
    "the fire button is text": ("fire_button", "a button"),
    "boxes is text": ("boxes", "a box"),
    "labels is a list": ("labels", []),
    "formats is a list": ("formats", []),
    "button values is a list": ("button_values", []),
    "actions is a list": ("actions", []),
    "colors is a list": ("colors", []),
    "the pool map is a list": ("pool_color_map", []),
    "the empty label is a number": ("empty_label", 7),
    "the footer label is a number": ("footer_label", 7),
    "the pool label is a list": ("pool_label", []),
    "titles is a list": ("titles", []),
    "outcomes is a bag": ("outcomes", {}),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_VALUES))
def test_a_hostile_value_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    name, value = HOSTILE_VALUES[case]
    payload = state_payload("loaded")
    payload[name] = value
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    assert isinstance(js.json(API + "kinds()"), dict), case
    assert isinstance(js.json(API + "rowIdentities()"), list), case
    assert isinstance(js.json(API + "drawnLabels()"), list), case
    assert isinstance(js.json(API + "sheets()"), list), case
    assert isinstance(js.json(API + "cellColours()"), list), case
    assert isinstance(js.json(API + "publishedLabels()"), list), case


HOSTILE_CELLS: dict = {
    "a null cell": None,
    "a bag cell": {},
    "a list cell": [],
    "a number where text belongs": 7,
    "a two hundred character cell": LONG_NAME,
    "markup": MARKUP_NAME,
    "a newline": NEWLINE_NAME,
    "an empty cell": "",
}


@pytest.mark.parametrize("case", sorted(HOSTILE_CELLS))
def test_a_hostile_table_cell_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    payload = state_payload("loaded")
    payload["positions_table"]["rows"][0][0] = HOSTILE_CELLS[case]
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    named = js.json(API + "rowIdentities()")
    assert len(named) == len(payload["positions_table"]["rows"]), case
    assert isinstance(js.json(API + "kinds()"), dict), case


HOSTILE_ROWS: dict = {
    "a null row": None,
    "a scalar row": 7,
    "a bag row": {},
    "a text row": LONG_NAME,
}


@pytest.mark.parametrize("case", sorted(HOSTILE_ROWS))
def test_a_hostile_table_row_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """A scalar or a null slipping past the row walk is the hole this looks for."""
    payload = state_payload("loaded")
    payload["positions_table"]["rows"][1] = HOSTILE_ROWS[case]
    report = js.push(payload)
    assert [
        one for one in report["faults"] if one["where"] == "row:1"
    ], f"{case} reported nothing on row 1"
    assert js.json(API + "rowCells(1)") == [], case
    assert isinstance(js.json(API + "kinds()"), dict), case


@pytest.mark.parametrize("case", sorted(HOSTILE_ROWS))
def test_a_hostile_row_colour_list_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    payload = state_payload("loaded")
    payload["positions_table"]["row_colors"][1] = HOSTILE_ROWS[case]
    report = js.push(payload)
    assert [one for one in report["faults"] if one["where"] == "row:1"], case
    assert js.json(API + "rowColors(1)") == [], case
    assert isinstance(js.json(API + "cellColours()"), list), case


HOSTILE_SUMMARY: dict = {
    "a null row": None,
    "a scalar row": 7,
    "a short row": [surface.POOL_ROW_LABEL],
    "a number where a label belongs": [7, 7],
    "a two hundred character label": [LONG_NAME, LONG_NAME],
    "markup": [MARKUP_NAME, MARKUP_NAME],
    "a newline": [NEWLINE_NAME, NEWLINE_NAME],
}


@pytest.mark.parametrize("case", sorted(HOSTILE_SUMMARY))
def test_a_hostile_summary_row_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    payload = state_payload("loaded")
    payload["summary_rows"][1] = HOSTILE_SUMMARY[case]
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert len(js.json(API + "drawnLabels()")) == len(payload["summary_rows"]), case
    assert isinstance(js.json(API + "kinds()"), dict), case


def test_a_bot_holding_no_position_draws_the_empty_note_and_no_table(js: JsRuntime):
    """Zero positions is the state the operator sees while the pool is all base."""
    payload = state_payload("empty")
    report = js.push(payload)
    assert payload["positions_table"]["shown"] is False
    assert payload["empty_label"]["shown"] is True
    assert payload["positions_table"]["rows"] == []
    assert payload["fire_button"]["pairs"] == []
    assert js.json(API + "rowIdentities()") == []
    assert report["faults"] == []


def test_a_position_holding_a_negative_quantity_draws_its_own_negative_units(
    js: JsRuntime,
):
    """A negative quantity is drawn as it stands, and the surface repairs nothing."""
    held = [dict(THREE_POSITIONS[0], alt_units=-0.5)]
    payload = build([{"reset": True, "bot": bot(held)}])
    report = js.push(payload)
    table = payload["positions_table"]
    assert table["rows"][0][3] == surface.ALT_UNITS_FORMAT.format(alt_units=-0.5)
    assert js.called_two("cellNamed", 0, table["columns"][3]).startswith("-")
    assert report["faults"] == []


def test_a_position_naming_a_bot_the_fleet_has_none_of_changes_no_drawn_row(
    js: JsRuntime,
):
    """The position record stores no bot id, so an unknown one reaches no row."""
    named = [dict(one) for one in THREE_POSITIONS]
    named[0]["bot_id"] = UNKNOWN_BOT
    payload = build([{"reset": True, "bot": bot(named)}])
    js.push(payload)
    assert payload["positions_table"]["rows"] == (
        state_payload("loaded")["positions_table"]["rows"]
    )
    assert UNKNOWN_BOT not in json.dumps(payload)
    assert js.json(API + "faults()") == []


HOSTILE_READINGS: dict = {
    "nan alt units": ("alt_units", float("nan")),
    "inf alt units": ("alt_units", float("inf")),
    "minus inf alt units": ("alt_units", float("-inf")),
    "a huge entry price": ("entry_usd", 10.0**24),
    "a huge delta": ("delta_pct_usd_approx", 10.0**24),
    "a negative quantity": ("alt_units", -0.5),
    "a two hundred character pair": ("pair", LONG_NAME),
    "markup in the pair": ("pair", MARKUP_NAME),
    "a newline in the pair": ("pair", NEWLINE_NAME),
    "a number where the state belongs": ("state", 7),
    "text where a tier belongs": ("tier", "3"),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_READINGS))
def test_a_hostile_position_reading_draws_a_row_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """Each hostile reading is drawn as the surface formats it, and repaired here."""
    name, value = HOSTILE_READINGS[case]
    held = [dict(THREE_POSITIONS[0], **{name: value})]
    payload = build([{"reset": True, "bot": bot(held)}])
    report = js.push(payload)
    table = payload["positions_table"]
    assert len(table["rows"]) == 1, case
    assert len(table["rows"][0]) == table["cell_column_count"], case
    assert report["faults"] == [], f"{case} reported {report['faults']}"
    assert table["rows"][0] == surface.row_cells(held[0]), case
    named = js.json(API + "rowIdentities()")
    assert named[0]["name"] == payload["fire_button"]["pairs"][0], case


@pytest.mark.parametrize("name", sorted(THREE_POSITIONS[0]))
def test_a_position_missing_one_reading_draws_the_default_the_surface_publishes(
    js: JsRuntime, name: str
):
    """A missing reading is drawn from the surface's own default, never left out."""
    held = [{key: one for key, one in THREE_POSITIONS[0].items() if key != name}]
    payload = build([{"reset": True, "bot": bot(held)}])
    report = js.push(payload)
    table = payload["positions_table"]
    assert len(table["rows"][0]) == table["cell_column_count"], name
    assert report["faults"] == [], f"{name} reported {report['faults']}"


#: The six readings the shipped surface reads as numbers, and the two as words.
NUMBER_READINGS = (
    surface.TIER_KEY,
    surface.ALT_UNITS_KEY,
    surface.ENTRY_KEY,
    surface.CURRENT_KEY,
    surface.DELTA_KEY,
    surface.CORRECTIONS_KEY,
)
WORD_READINGS = (surface.PAIR_KEY, surface.STATE_KEY)


@pytest.mark.parametrize("name", NUMBER_READINGS)
def test_a_null_number_reading_stops_the_shipped_surface_before_any_row(name: str):
    """A null where a number belongs raises in the surface, and is not repaired."""
    held = [dict(THREE_POSITIONS[0], **{name: None})]
    with pytest.raises(TypeError):
        build([{"reset": True, "bot": bot(held)}])


@pytest.mark.parametrize("name", WORD_READINGS)
def test_a_null_word_reading_draws_the_row_the_surface_formats_from_it(
    js: JsRuntime, name: str
):
    held = [dict(THREE_POSITIONS[0], **{name: None})]
    payload = build([{"reset": True, "bot": bot(held)}])
    report = js.push(payload)
    assert payload["positions_table"]["rows"][0] == surface.row_cells(held[0])
    assert report["faults"] == [], f"{name} reported {report['faults']}"


def test_two_positions_on_one_pair_are_both_drawn_and_named_the_same(js: JsRuntime):
    """A duplicate pair leaves two Fire buttons that close the same position."""
    held = [THREE_POSITIONS[0], dict(THREE_POSITIONS[0], tier=3)]
    payload = build([{"reset": True, "bot": bot(held)}])
    report = js.push(payload)
    assert payload["fire_button"]["pairs"] == [
        THREE_POSITIONS[0]["pair"],
        THREE_POSITIONS[0]["pair"],
    ]
    duplicate = [one for one in report["faults"] if one["fault"] == "duplicate-name"]
    assert [one["where"] for one in duplicate] == ["row:1"]


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """A module that raised on one hostile value would answer no row and no label."""
    js.push(7)
    assert js.json(API + "tableRows()") == []
    assert js.json(API + "rowIdentities()") == []
    assert js.json(API + "drawnLabels()") == []
    assert js.json(API + "cellColours()") == []
    assert js.json(API + "isLoaded()") is False


def test_every_published_count_is_filled_in_by_the_path_that_publishes_it(
    js: JsRuntime,
):
    """A count nobody fills reads zero forever, which the loaded state would show."""
    payload = state_payload("loaded")
    table = payload["positions_table"]
    js.push(payload)
    assert table["row_count"] == len(table["rows"]) == 3
    assert len(payload["fire_button"]["pairs"]) == table["row_count"]
    assert len(table["row_colors"]) == table["row_count"]
    assert len(payload["summary_rows"]) == 4
    assert len(payload["call_names"]) == len(surface.CALL_NAMES)
    assert len(payload["calls"]) > 0
    assert payload["timers"] == {} and payload["timer_delays_ms"] == []
    assert payload["bus_topics"] == []


def test_the_count_reading_would_see_a_row_count_left_at_zero(js: JsRuntime):
    payload = state_payload("loaded")
    payload["positions_table"]["row_count"] = 0
    report = js.push(payload)
    assert [
        one["field"] for one in report["faults"] if one["fault"] == "disagrees"
    ] == ["row_count"]


#: An empty tag pair a rich-text widget swallows and a plain one lays out.
MARKUP_PROBE = "<span></span>fire"
PLAIN_PROBE = "fire"


def a_label(text: str) -> int:
    from PySide6.QtWidgets import QLabel

    return int(QLabel(text).minimumSizeHint().width())


def a_message(text: str) -> int:
    from PySide6.QtWidgets import QMessageBox

    widget = QMessageBox()
    widget.setText(text)
    return int(widget.minimumSizeHint().width())


def a_button(text: str) -> int:
    from PySide6.QtWidgets import QPushButton

    return int(QPushButton(text).minimumSizeHint().width())


def a_group(text: str) -> int:
    from PySide6.QtWidgets import QGroupBox

    return int(QGroupBox(text).minimumSizeHint().width())


def a_cell(text: str) -> int:
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    table = QTableWidget(1, 1)
    table.setItem(0, 0, QTableWidgetItem(text))
    return int(table.sizeHintForColumn(0))


def a_header(text: str) -> int:
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    table = QTableWidget(1, 1)
    table.setHorizontalHeaderItem(0, QTableWidgetItem(text))
    return int(table.horizontalHeader().sectionSizeHint(0))


SCREEN_WIDGETS = {
    "QPushButton": a_button,
    "QGroupBox": a_group,
    "QTableWidgetItem": a_cell,
    "QHeaderView": a_header,
}
RICH_TEXT_WIDGETS = {"QLabel": a_label, "QMessageBox": a_message}
EVERY_WIDGET = dict(SCREEN_WIDGETS, **RICH_TEXT_WIDGETS)


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_no_plain_widget_this_tab_uses_reads_its_caller_text_as_markup(qapp, kind: str):
    """A widget asking for a wider MARKUP_PROBE than PLAIN_PROBE never read its tags."""
    assert qapp is not None
    asked = SCREEN_WIDGETS[kind]
    assert asked(MARKUP_PROBE) > asked(
        PLAIN_PROBE
    ), f"{kind} asked for no more width for the markup than for the plain words"


@pytest.mark.parametrize("kind", sorted(RICH_TEXT_WIDGETS))
def test_the_two_widgets_this_tab_uses_that_do_read_markup_are_named(qapp, kind: str):
    """QLabel and QMessageBox ask for MARKUP_PROBE exactly as wide as PLAIN_PROBE."""
    assert qapp is not None
    asked = RICH_TEXT_WIDGETS[kind]
    assert asked(MARKUP_PROBE) == asked(PLAIN_PROBE)


@pytest.mark.parametrize("kind", sorted(EVERY_WIDGET))
def test_the_markup_measurement_reads_a_longer_text_as_a_wider_asked_width(
    qapp, kind: str
):
    """A width that never moved would read every widget as one that reads markup."""
    assert qapp is not None
    asked = EVERY_WIDGET[kind]
    assert asked(PLAIN_PROBE * PROBE_TEXT_REPEAT) > asked(PLAIN_PROBE)


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
            "the page never defined the positions held module in "
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
    "color",
    "backgroundColor",
    "borderTopWidth",
    "borderTopColor",
    "borderTopStyle",
    "borderTopLeftRadius",
    "paddingTop",
    "fontWeight",
    "fontSize",
    "fontFamily",
    "whiteSpace",
    "textAlign",
    "height",
    "gap",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.setAttribute('data-part', 'positions-held-page');"
    "document.body.appendChild(window.HOST);"
    "window.PRESSED = [];"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeAssign = function (style, names) {"
    "  var probe = document.createElement('div');"
    "  Object.keys(style).forEach(function (n) { probe.style[n] = style[n]; });"
    "  document.body.appendChild(probe);"
    "  var found = window.readStyle(probe, names);"
    "  probe.remove();"
    "  return found; };"
    "window.partNamed = function (name) {"
    "  return window.HOST.querySelector('[data-part=\"' + name + '\"]'); };"
    "window.partsNamed = function (name) {"
    "  return Array.prototype.slice.call("
    "    window.HOST.querySelectorAll('[data-part=\"' + name + '\"]')); };"
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
    "        text: own, whole: el.textContent, html: el.innerHTML,"
    "        title: el.title, hidden: el.hidden,"
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

WIRE_HANDLERS = (
    "window.HANDLERS = {"
    "  onFire: function (n) { window.PRESSED.push(['fire', n]); },"
    "  onAnswer: function (n) { window.PRESSED.push(['answer', n]); } };"
)


def draw_tab(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js(WIRE_HANDLERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    browser.js(
        "acervatorSetTokens(JSON.parse(window.TOKENS));"
        "acervatorTokens.apply(document.documentElement);"
    )
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        SETTER
        + "(JSON.parse(window.PAYLOAD));"
        + API
        + "fill(window.HOST, null, window.HANDLERS);"
    )
    return json.loads(browser.js(READ_PARTS))


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def with_part(parts: list, name: str) -> list:
    return [one for one in parts if one["path"].split("/")[-1] == name]


def probe_for(browser: Browser, style: dict) -> dict:
    return browser.parsed(
        "window.probeAssign(" + json.dumps(style) + ", JSON.parse(window.STYLE_NAMES))"
    )


def test_the_tab_fills_the_named_space_the_window_left_for_it(browser: Browser):
    """The Live Bot Settings window names one space and this tab fills it."""
    parts = draw_tab(browser, state_payload("loaded"))
    assert browser.parsed(API + "spacePart") == "positions-held-page"
    assert at_path(parts, "positions-held-tab"), "the tab drew nothing into the space"


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A drawn child with no data-part is one no check can read."""
    draw_tab(browser, state_payload("dispatched"))
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no data-part"
    assert named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    draw_tab(browser, state_payload("dispatched"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_summary_row_draws_the_label_and_value_the_surface_carries(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")
    assert len(drawn) == len(payload["summary_rows"])
    by_label = {one["attrs"]["data-key"]: one for one in drawn}
    labels = {
        one["attrs"]["data-key"]: one for one in with_part(parts, "summary-label")
    }
    for name, value in payload["summary_rows"]:
        assert by_label[name]["text"] == value, f"{state} row {name}"
        assert labels[name]["text"] == name


def test_the_pool_row_matches_a_probe_built_from_its_whole_declaration(
    browser: Browser,
):
    """The applied value is read against a probe built from the whole declaration."""
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    name = payload["labels"]["pool_row"]
    drawn = {one["attrs"]["data-key"]: one for one in with_part(parts, "summary-value")}
    sheet = payload["pool_label"]["style_sheet"]
    probe = probe_for(
        browser, browser.parsed(API + "paintedStyle(" + json.dumps(sheet) + ")")
    )
    found = drawn[name]["style"]
    assert found["color"] == probe["color"], f"the pool row drew {found}"
    assert found["fontSize"] == probe["fontSize"]
    assert drawn[name]["attrs"]["data-styled"] == "true"


def test_the_rendered_comparison_would_see_one_repainted_pool_row(browser: Browser):
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    name = payload["labels"]["pool_row"]
    drawn = {one["attrs"]["data-key"]: one for one in with_part(parts, "summary-value")}
    probe = probe_for(browser, {"color": OTHER_COLOUR})
    assert drawn[name]["style"]["color"] != probe["color"]


def test_the_three_money_rows_take_no_colour_at_all(browser: Browser):
    """The pool row alone publishes a sheet, so the money rows must stay unpainted."""
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    unpainted = [
        one
        for one in with_part(parts, "summary-value")
        if one["attrs"]["data-styled"] == "false"
    ]
    assert len(unpainted) == 3
    plain = probe_for(browser, {})
    for one in unpainted:
        assert one["style"]["color"] == plain["color"]


def test_the_unpainted_check_would_see_a_row_the_surface_painted(browser: Browser):
    payload = state_payload("loaded")
    payload["labels"]["pool_row"] = payload["summary_rows"][1][0]
    parts = draw_tab(browser, payload)
    styled = [
        one
        for one in with_part(parts, "summary-value")
        if one["attrs"]["data-styled"] == "true"
    ]
    assert [one["attrs"]["data-key"] for one in styled] == [
        payload["summary_rows"][1][0]
    ]


def test_the_table_draws_one_head_cell_for_each_published_column_name(
    browser: Browser,
):
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "head-cell")
    assert [one["text"] for one in drawn] == payload["positions_table"]["columns"]
    assert [one["attrs"]["data-column"] for one in drawn] == [
        str(at) for at in range(payload["positions_table"]["column_count"])
    ]


def test_each_position_row_draws_its_eight_cells_under_the_columns_naming_them(
    browser: Browser,
):
    payload = state_payload("loaded")
    table = payload["positions_table"]
    parts = draw_tab(browser, payload)
    rows = with_part(parts, "position-row")
    assert [one["attrs"]["data-name"] for one in rows] == payload["fire_button"][
        "pairs"
    ]
    cells = with_part(parts, "position-cell")
    assert len(cells) == len(rows) * table["column_count"]
    for at, pair in enumerate(payload["fire_button"]["pairs"]):
        own = cells[at * table["column_count"] : (at + 1) * table["column_count"]]
        assert [one["attrs"]["data-key"] for one in own] == table["columns"]
        for column, one in enumerate(own[: table["cell_column_count"]]):
            assert one["text"] == table["rows"][at][column], f"{pair} {column}"


def test_the_state_and_delta_cells_paint_the_bare_colours_the_surface_publishes(
    browser: Browser,
):
    """A cell publishes a bare colour, so the probe is built from that colour alone."""
    payload = state_payload("loaded")
    table = payload["positions_table"]
    parts = draw_tab(browser, payload)
    cells = with_part(parts, "position-cell")
    painted = [one for one in cells if one["attrs"]["data-painted"] == "true"]
    wanted = [one for row in table["row_colors"] for one in row if one is not None]
    assert [one["attrs"]["data-value"] for one in painted] == wanted
    for one in painted:
        probe = probe_for(browser, {"color": one["attrs"]["data-value"]})
        assert one["style"]["color"] == probe["color"], one["attrs"]["data-key"]


def test_a_cell_the_surface_leaves_unpainted_takes_the_plain_colour(browser: Browser):
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    plain = [
        one
        for one in with_part(parts, "position-cell")
        if one["attrs"]["data-painted"] == "false"
    ]
    assert plain
    ground = probe_for(browser, {})
    assert plain[0]["style"]["color"] == ground["color"]


def test_the_cell_paint_check_would_see_a_colour_the_surface_never_sent(
    browser: Browser,
):
    parts = draw_tab(browser, state_payload("loaded"))
    painted = [
        one
        for one in with_part(parts, "position-cell")
        if one["attrs"]["data-painted"] == "true"
    ][0]
    probe = probe_for(browser, {"color": OTHER_COLOUR})
    assert painted["style"]["color"] != probe["color"]


def test_each_position_row_carries_a_fire_button_naming_its_own_pair(
    browser: Browser,
):
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "fire-button")
    assert [one["attrs"]["data-name"] for one in drawn] == payload["fire_button"][
        "pairs"
    ]
    assert {one["text"] for one in drawn} == {payload["fire_button"]["text"]}
    assert {one["attrs"]["data-action"] for one in drawn} == set(
        payload["actions"].values()
    )


def test_the_fire_button_asks_for_the_height_and_the_sheet_the_surface_publishes(
    browser: Browser,
):
    """The border and the radius are read against a whole-declaration probe."""
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "fire-button")[0]
    style = browser.parsed(
        API + "paintedStyle(" + json.dumps(payload["fire_button"]["style_sheet"]) + ")"
    )
    style["height"] = str(payload["fire_button"]["fixed_height_px"]) + "px"
    probe = probe_for(browser, style)
    assert drawn["style"]["backgroundColor"] == probe["backgroundColor"]
    assert drawn["style"]["borderTopWidth"] == probe["borderTopWidth"]
    assert drawn["style"]["borderTopStyle"] == probe["borderTopStyle"]
    assert drawn["style"]["borderTopLeftRadius"] == probe["borderTopLeftRadius"]
    assert drawn["style"]["paddingTop"] == probe["paddingTop"]
    assert drawn["style"]["fontWeight"] == probe["fontWeight"]
    assert drawn["style"]["height"] == probe["height"]


@pytest.mark.parametrize("at", (0, 1, 2))
def test_pressing_one_fire_button_runs_the_handler_with_that_row_s_own_pair(
    browser: Browser, at: int
):
    """The argument must be the pair, never the row's place in the list."""
    payload = state_payload("loaded")
    draw_tab(browser, payload)
    wanted = payload["fire_button"]["pairs"][at]
    browser.js("window.partsNamed('fire-button')[" + str(at) + "].click();")
    assert browser.parsed("window.PRESSED") == [["fire", wanted]]
    assert browser.parsed(API + "pressed()")["argument"] == wanted
    assert (
        browser.parsed(API + "pressed()")["action"]
        == list(payload["actions"].values())[0]
    )


def test_the_fire_check_would_see_a_button_answering_with_its_own_position(
    browser: Browser,
):
    draw_tab(browser, state_payload("loaded"))
    browser.js("window.partsNamed('fire-button')[1].click();")
    assert browser.parsed("window.PRESSED")[0][1] != 1


def test_the_handler_check_would_see_a_press_nobody_made(browser: Browser):
    draw_tab(browser, state_payload("loaded"))
    assert browser.parsed("window.PRESSED") == []


@pytest.mark.parametrize("state", BOX_STATES)
def test_each_message_box_draws_its_title_text_and_the_answers_it_offers(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "message-box")
    assert len(drawn) == len(payload["boxes"])
    for at, box in enumerate(payload["boxes"]):
        assert drawn[at]["attrs"]["data-icon"] == box["icon"]
        assert drawn[at]["attrs"]["data-key"] == box["title"]
        assert drawn[at]["attrs"]["data-default"] == str(box["default_button_value"])
    assert with_part(parts, "box-text")[0]["text"] == payload["boxes"][0]["text"]


def test_the_confirm_box_marks_no_as_the_answer_qt_opened_it_on(browser: Browser):
    payload = state_payload("declined")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "box-button")
    assert [one["attrs"]["data-name"] for one in drawn] == ["yes", "no"]
    assert [one["attrs"]["data-default"] for one in drawn] == ["false", "true"]


@pytest.mark.parametrize("at", (0, 1))
def test_pressing_one_confirm_answer_runs_the_handler_with_that_button_value(
    browser: Browser, at: int
):
    payload = state_payload("declined")
    draw_tab(browser, payload)
    browser.js("window.partsNamed('box-button')[" + str(at) + "].click();")
    wanted = payload["button_values"][["yes", "no"][at]]
    assert browser.parsed("window.PRESSED") == [["answer", wanted]]


def test_pressing_the_only_answer_a_warning_box_offers_runs_the_handler(
    browser: Browser,
):
    payload = state_payload("no_loop")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "box-button")
    assert [one["attrs"]["data-name"] for one in drawn] == ["yes", "no", "ok"]
    browser.js("window.partsNamed('box-button')[2].click();")
    assert browser.parsed("window.PRESSED") == [
        ["answer", payload["button_values"]["ok"]]
    ]


def test_the_empty_note_the_table_and_the_footer_show_where_the_surface_shows_them(
    browser: Browser,
):
    empty = draw_tab(browser, state_payload("empty"))
    loaded = draw_tab(browser, state_payload("loaded"))
    assert with_part(empty, "empty-note")[0]["hidden"] is False
    assert with_part(empty, "positions-table")[0]["hidden"] is True
    assert with_part(empty, "footer-note")[0]["hidden"] is True
    assert with_part(loaded, "empty-note")[0]["hidden"] is True
    assert with_part(loaded, "positions-table")[0]["hidden"] is False
    assert with_part(loaded, "footer-note")[0]["hidden"] is False
    assert (
        with_part(empty, "empty-note")[0]["text"]
        == state_payload("empty")["empty_label"]["text"]
    )


def test_the_tab_refuses_the_markup_the_pool_line_carries(browser: Browser):
    """Qt paints the pool name in bold, and React writes the tags as characters."""
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    name = payload["labels"]["pool_row"]
    drawn = {one["attrs"]["data-key"]: one for one in with_part(parts, "summary-value")}
    assert drawn[name]["text"] == payload["pool_label"]["text"]
    assert "<b>" not in drawn[name]["html"]
    assert browser.parsed("window.HOST.querySelectorAll('b').length") == 0


def test_the_tab_refuses_markup_a_hostile_cell_carries(browser: Browser):
    payload = state_payload("loaded")
    payload["positions_table"]["rows"][0][0] = MARKUP_NAME
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "position-cell")[0]
    assert drawn["text"] == MARKUP_NAME
    assert "<img" not in drawn["html"]
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    draw_tab(browser, state_payload("loaded"))
    browser.js("window.HOST.firstChild.insertAdjacentHTML('beforeend', '<img>');")
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 1


def test_a_two_hundred_character_cell_widens_the_column_rather_than_clipping(
    browser: Browser,
):
    """A CSS table grows to fit where Qt clips, so the width is reported."""
    payload = state_payload("loaded")
    payload["positions_table"]["rows"][0][0] = LONG_NAME
    wide = with_part(draw_tab(browser, payload), "position-cell")[0]
    narrow = with_part(draw_tab(browser, state_payload("loaded")), "position-cell")[0]
    assert wide["width"] > narrow["width"]


def test_the_table_carries_the_qt_behaviours_the_surface_declares_for_it(
    browser: Browser,
):
    """No side header, no editing and one selected row are declared, not drawn twice."""
    payload = state_payload("loaded")
    table = payload["positions_table"]
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "positions-table")[0]
    assert (
        drawn["attrs"]["data-side-head"]
        == str(table["vertical_header_visible"]).lower()
    )
    assert drawn["attrs"]["data-edit-triggers"] == table["edit_triggers"]
    assert drawn["attrs"]["data-selection"] == table["selection_behavior"]
    assert drawn["attrs"]["data-resize-mode"] == table["header_resize_mode"]
    assert drawn["attrs"]["data-alignment"] == table["cell_alignment"]
    assert (
        drawn["attrs"]["data-alternating"]
        == str(table["alternating_row_colors"]).lower()
    )
    assert browser.parsed("window.HOST.querySelectorAll('input').length") == 0


def test_the_tab_declares_its_own_spacing_and_leaves_the_form_to_the_host(
    browser: Browser,
):
    """The surface sets a spacing and no margin, and says the host builds the form."""
    payload = state_payload("loaded")
    parts = draw_tab(browser, payload)
    tab = at_path(parts, "positions-held-tab")[0]
    assert (
        tab["attrs"]["data-margins-set"]
        == str(payload["container"]["margins_set"]).lower()
    )
    probe = probe_for(browser, {"gap": str(payload["container"]["spacing_px"]) + "px"})
    assert tab["style"]["gap"] == probe["gap"]
    group = with_part(parts, "summary-group")[0]
    assert (
        group["attrs"]["data-configured-by-host"]
        == str(payload["summary_form"]["configured_by_host"]).lower()
    )
    assert (
        group["attrs"]["data-matched"]
        == str(payload["summary_form"]["configured"]).lower()
    )


def test_the_outcome_line_carries_what_the_fire_path_reported(browser: Browser):
    for state in BOX_STATES:
        payload = state_payload(state)
        parts = draw_tab(browser, payload)
        assert with_part(parts, "outcome")[0]["text"] == payload["fire_outcome"]
