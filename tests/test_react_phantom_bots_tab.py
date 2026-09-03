"""The React Phantom Bots tab, against phantom_bots_tab_surface.py."""

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
from src.gui.main_tabs import phantom_bots_tab_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "phantom_bots_tab.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorPhantomBotsTab."
SETTER = "acervatorSetPhantomBotsTab"

#: SHARED_MODULES are the pieces the page loads beside this one.
SHARED_MODULES = (WEB / "table_cells.js", WEB / "header_strip.js")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 3
HOST_WIDTH_PX = 1200
HOST_HEIGHT_PX = 700

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
OTHER_COLOUR = "#00ffcc"
UNKNOWN_BOT = "no-such-bot"

PHANTOMS = [
    {
        "timeframe": "1h",
        "state": "RUNNING",
        "target_balance": 25.0,
        "total_trades": 4,
        "realized_pnl_exchange": 1.2345,
        "last_summary": {"bullish": 3, "bearish": 1, "confidence": 0.75},
    },
    {
        "timeframe": "4h",
        "state": "IDLE",
        "target_balance": 50.0,
        "total_trades": 0,
        "realized_pnl_exchange": -0.5,
        "last_summary": {"bullish": 1, "bearish": 2, "confidence": 0.3},
    },
    {
        "timeframe": "1d",
        "state": "HOLD",
        "target_balance": 100.0,
        "total_trades": 2,
        "realized_pnl_exchange": 0.0,
        "last_summary": {"bullish": 0, "bearish": 0, "confidence": 0.1},
    },
]

LOCKS = [
    {
        "source_tf": "1d",
        "source_bot": "bot-a",
        "locked_direction": "BULLISH",
        "candles_remaining": 3,
    },
    {
        "source_tf": "4h",
        "source_bot": "bot-b",
        "locked_direction": "BEARISH",
        "candles_remaining": 1,
    },
]


def bot(**rest: Any) -> dict:
    """One running bot the tab reads, from the values a request carries."""
    found = {
        "exchange_id": "coinbase",
        "enabled": True,
        "started": True,
        "timeframes": ["1m", "1h", "1d"],
        "locked": True,
        "lock_timeframe": "1d",
        "bot_id": "bot-a",
        "lock_candle_count": 4,
        "phantoms": PHANTOMS,
        "locks": LOCKS,
    }
    found.update(rest)
    return found


QUIET = {"phantoms": [], "locks": [], "locked": False}

STATES: dict = {
    "fresh": [{"reset": True}],
    "off": [
        {
            "reset": True,
            "bot": bot(enabled=False, started=False, timeframes=[], **QUIET),
        }
    ],
    "waiting": [{"reset": True, "bot": bot(started=False, **QUIET)}],
    "quiet": [{"reset": True, "bot": bot(**QUIET)}],
    "running": [{"reset": True, "bot": bot()}],
    "unknown": [
        {
            "reset": True,
            "bot": bot(
                phantoms=[],
                locks=[dict(LOCKS[1], source_bot=UNKNOWN_BOT)],
            ),
        }
    ],
    "toggled": [{"reset": True, "bot": bot()}, {"steps": [["enable", False]]}],
    "picked": [{"reset": True, "bot": bot()}, {"steps": [["timeframe", "5m", True]]}],
    "moved": [{"reset": True, "bot": bot()}, {"steps": [["lock", 9]]}],
}
STATE_NAMES = tuple(STATES)
DRAWN_STATES = ("off", "waiting", "quiet", "running", "unknown")


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def build(steps: list) -> dict:
    """One payload, each step driving the same tab in the order given."""
    found: dict = {}
    for step in steps:
        found = surface.view_model(step)
    return as_json(found)


def state_payload(name: str) -> dict:
    return build(STATES[name])


def token_payload() -> dict:
    return as_json(dss.view_model({}))


class JsRuntime(JsEngine):
    """A QJSEngine holding the tab and the merged pieces it calls."""

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


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = state_payload("running")
    payload["only_on_the_surface"] = []
    js.push(payload)
    assert sorted(set(payload) - set(declared_fields(js))) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    payload = state_payload("running")
    assert payload.pop("stretch_shown") is not None
    js.push(payload)
    assert sorted(set(declared_fields(js)) - set(payload)) == ["stretch_shown"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = state_payload("running")
    payload["signal_count"] += 1
    js.push(payload)
    original = state_payload("running")
    differing = sorted(
        name for name in original if js.called("field", name) != original[name]
    )
    assert differing == ["signal_count"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    phantom = payload["phantom_table"]
    locks = payload["locks_table"]
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["timeframes"] == len(payload["timeframes"])
    assert report["held"]["timeframes"] == len(payload["timeframe_checks"])
    assert report["declared"]["phantoms"] == phantom["row_count"]
    assert report["held"]["phantoms"] == len(phantom["rows"])
    assert report["declared"]["locks"] == locks["row_count"]
    assert report["held"]["locks"] == len(locks["rows"])
    assert report["declared"]["columns"] == phantom["column_count"]
    assert report["held"]["columns"] == len(phantom["columns"])
    assert report["declared"]["lock_columns"] == locks["column_count"]
    assert report["held"]["lock_columns"] == len(locks["columns"])
    assert report["held"]["actions"] == len(payload["actions"])
    assert report["declared"]["tables"] == report["held"]["tables"]


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("running")
    declared = len(payload)
    del payload["accessible_name"]
    report = js.push(payload)
    assert report["declared"]["fields"] == declared
    assert report["held"]["fields"] == declared - 1
    assert [one["field"] for one in report["faults"]] == ["accessible_name"]


def test_a_dropped_phantom_row_shortens_the_held_row_count(js: JsRuntime):
    payload = state_payload("running")
    payload["phantom_table"]["rows"].pop()
    report = js.push(payload)
    assert report["declared"]["phantoms"] == len(
        state_payload("running")["phantom_table"]["rows"]
    )
    assert report["held"]["phantoms"] == report["declared"]["phantoms"] - 1


def test_a_dropped_timeframe_switch_shortens_the_held_timeframe_count(js: JsRuntime):
    payload = state_payload("running")
    payload["timeframe_checks"].pop()
    report = js.push(payload)
    assert report["declared"]["timeframes"] == len(payload["timeframes"])
    assert report["held"]["timeframes"] == report["declared"]["timeframes"] - 1


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
    payload = state_payload("running")
    payload["signal_count"] = str(payload["signal_count"])
    js.push(payload)
    expected = python_kinds(state_payload("running"))
    actual = js.json(API + "kinds()")
    assert sorted(p for p, k in expected.items() if actual.get(p) != k) == [
        "signal_count"
    ]


def test_the_type_walk_names_a_scalar_where_a_phantom_row_belongs(js: JsRuntime):
    """A scalar where the payload lists a row must not read as that row."""
    payload = state_payload("running")
    payload["phantom_table"]["rows"][1] = 7
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("phantom_table.rows.1") == "number"
    assert "phantom_table.rows.1.0" not in actual


def test_the_type_walk_names_a_null_where_a_phantom_cell_belongs(js: JsRuntime):
    payload = state_payload("running")
    payload["phantom_table"]["rows"][1][0] = None
    js.push(payload)
    assert js.json(API + "kinds()").get("phantom_table.rows.1.0") == "null"


def test_the_type_walk_names_a_scalar_where_a_timeframe_switch_belongs(js: JsRuntime):
    payload = state_payload("running")
    payload["timeframe_checks"][2] = 7
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("timeframe_checks.2") == "number"
    assert "timeframe_checks.2.0" not in actual


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
    """A live object on the payload is a value the renderer cannot serialise."""
    raw: dict = {}
    for step in STATES[state]:
        raw = surface.view_model(step)
    assert not_plain_data(raw) == [], f"{state} publishes {not_plain_data(raw)}"


def test_the_plain_data_walk_names_a_live_object_put_on_the_payload():
    raw = surface.view_model({"reset": True})
    raw["phantom_table"]["rows"] = [[surface.PhantomBotsTabModel()]]
    assert not_plain_data(raw) == ["phantom_table.rows.0.0"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    js.push(state_payload("running"))
    js.run(
        SETTER
        + "(Object.assign("
        + API
        + "payload(), { stretch_shown: function () {} }));"
    )
    assert js.json(API + "notPlainData()") == [
        {"path": "stretch_shown", "kind": "function"}
    ]


def shown_values() -> set:
    """Every string the tab paints or shows as a tooltip, from every state."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        for row in payload["summary_rows"]:
            found |= {one for one in row if isinstance(one, str)}
        for one in payload["timeframe_checks"]:
            found |= {item for item in one if isinstance(item, str)}
        for table in ("phantom_table", "locks_table"):
            found |= set(payload[table]["columns"])
            for row in payload[table]["rows"]:
                found |= {one for one in row if isinstance(one, str)}
        for group in ("colors", "texts", "formats", "labels", "empty_texts"):
            found |= {one for one in payload[group].values() if isinstance(one, str)}
        for note in ("info_label", "timeframe_hint", "empty_label", "enable_check"):
            found.add(payload[note]["text"])
        found |= {payload["lock_spin"]["row_label"], payload["lock_spin"]["tooltip"]}
        found |= {
            payload[group]["title"]
            for group in (
                "enable_group",
                "timeframe_group",
                "lock_group",
                "summary_group",
                "phantom_group",
                "locks_group",
            )
        }
        found |= set(payload["timeframes"])
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


def published_keys() -> set:
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
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

#: NAMED_WORDS holds every published string the module may write.
NAMED_WORDS = published_keys() | {surface.METHOD, "phantom", "locks"}


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a value the surface owns."""
    assert not MODULE_LITERALS["numbers"], (
        "phantom_bots_tab.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"phantom_bots_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_shows():
    written = sorted(set(MODULE_LITERALS["strings"]) & SHOWN_VALUES)
    assert not written, f"phantom_bots_tab.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"phantom_bots_tab.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = {one for one in MODULE_LITERALS["strings"] if one} & PUBLISHED_STRINGS
    assert written <= NAMED_WORDS, (
        "the module names published strings the list does not allow: "
        f"{sorted(written - NAMED_WORDS)}"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_tab_shows():
    overlap = sorted(NAMED_WORDS & SHOWN_VALUES)
    assert not overlap, f"these named words are values the tab shows: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "phantom_bots_tab.js holds a slash outside a comment, which the literal "
        f"scan cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES: dict = {
    "colour": 'var written = "' + OTHER_COLOUR + '";',
    "on_colour": 'var written = "' + surface.ON_COLOR + '";',
    "waiting_colour": 'var written = "' + surface.WAITING_COLOR + '";',
    "note_colour": 'var written = "' + surface.NOTE_COLOR + '";',
    "column": 'var written = "' + surface.PHANTOM_COLUMNS[0] + '";',
    "lock_column": 'var written = "' + surface.LOCK_COLUMNS[0] + '";',
    "summary_label": 'var written = "' + surface.ENABLED_ROW_LABEL + '";',
    "yes_word": 'var written = "' + surface.YES_TEXT + '";',
    "timeframe": 'var written = "' + surface.TIMEFRAMES[0] + '";',
    "empty_note": 'var written = "' + surface.EMPTY_NO_STATE_TEXT + '";',
    "unlocked": 'var written = "' + surface.UNLOCKED_TEXT + '";',
    "group_title": 'var written = "' + surface.ENABLE_GROUP_TITLE + '";',
    "lock_ceiling": "var written = " + str(surface.LOCK_MAX) + ";",
    "table_height": "var written = " + str(surface.PHANTOM_TABLE_MAX_HEIGHT_PX) + ";",
    "number": "var written = 12;",
    "token_value": 'var written = "' + str(dss.PRIMARY) + '";',
    "regex": "var written = /ab+c/;",
}


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


def payload_colours(payload: dict) -> list:
    """Every colour the tab publishes, from every place that carries one."""
    found = list(payload["colors"].values())
    for table in ("phantom_table", "locks_table"):
        for row in payload[table]["row_colors"]:
            found += [one for one in row if one is not None]
    for note in ("info_label", "timeframe_hint", "empty_label"):
        found.append(payload[note]["style_sheet"])
    found += [row[2] for row in payload["summary_rows"] if row[2]]
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_the_tab_carries_is_swept_for_the_alpha_order_fault(
    js: JsRuntime, state: str
):
    """Every published colour is swept for the eight-digit shape Qt reads first."""
    payload = state_payload(state)
    js.push(payload)
    swept = payload_colours(payload)
    assert len(swept) >= len(payload["colors"])
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "swapped-alpha"
    ] == [], f"{state} carries an eight-digit colour"


COLOUR_NAMES = ("on", "waiting", "off", "loss", "note", "this_bot")


@pytest.mark.parametrize("name", COLOUR_NAMES)
def test_the_alpha_sweep_names_one_colour_written_with_eight_digits(
    js: JsRuntime, name: str
):
    payload = state_payload("running")
    payload["colors"][name] = SWAPPED_ALPHA
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


@pytest.mark.parametrize("table", ("phantom_table", "locks_table"))
def test_the_alpha_sweep_reads_a_colour_inside_one_painted_cell(
    js: JsRuntime, table: str
):
    payload = state_payload("running")
    payload[table]["row_colors"][0][0] = SWAPPED_ALPHA
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


@pytest.mark.parametrize("note", ("info_label", "timeframe_hint", "empty_label"))
def test_the_alpha_sweep_reads_a_colour_inside_one_note_style_sheet(
    js: JsRuntime, note: str
):
    payload = state_payload("running")
    payload[note]["style_sheet"] = surface.INFO_STYLE_FORMAT.format(
        color_hex=SWAPPED_ALPHA
    )
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_one_status_row_style(js: JsRuntime):
    payload = state_payload("running")
    payload["summary_rows"][0][2] = surface.FLAG_STYLE_FORMAT.format(
        color_hex=SWAPPED_ALPHA
    )
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_bag_the_surface_publishes_carries_a_key_a_browser_would_move(
    js: JsRuntime, state: str
):
    """A digit key is listed before every worded key, which loses the written order."""
    js.push(state_payload(state))
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "reordered-key"
    ] == []


@pytest.mark.parametrize("name", ("actions", "colors", "texts", "labels"))
def test_the_bag_order_check_names_a_digit_key_put_into_a_published_bag(
    js: JsRuntime, name: str
):
    payload = state_payload("running")
    payload[name]["0"] = next(iter(payload[name].values()))
    report = js.push(payload)
    moved = [one for one in report["faults"] if one["fault"] == "reordered-key"]
    assert [one["detail"] for one in moved] == ["0"]


def test_the_three_settings_are_read_from_a_list_and_not_from_the_action_bag(
    js: JsRuntime,
):
    """Pairing three settings off a bag would rest on that bag's key order."""
    payload = state_payload("running")
    js.push(payload)
    assert js.json(API + "actionNames()") == list(payload["actions"])


def test_the_setting_check_names_a_wired_name_the_payload_never_declared(js: JsRuntime):
    payload = state_payload("running")
    payload["actions"]["no_such_signal"] = "nothing"
    report = js.push(payload)
    unknown = [one for one in report["faults"] if one["fault"] == "unknown-action"]
    assert [one["detail"] for one in unknown] == ["no_such_signal"]


def test_the_setting_check_names_a_wired_name_the_payload_dropped(js: JsRuntime):
    payload = state_payload("running")
    del payload["actions"]["lock_spin.valueChanged"]
    report = js.push(payload)
    missing = [
        one
        for one in report["faults"]
        if one["fault"] == "missing" and one["field"] == "actions"
    ]
    assert [one["detail"] for one in missing] == ["lock_spin.valueChanged"]


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_timeframe_switch_is_found_by_its_own_name(js: JsRuntime, state: str):
    """Eleven switches sit against eight served timeframes, so position lies."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "timeframeNames()") == payload["timeframes"]
    for name, checked, supported, tooltip in payload["timeframe_checks"]:
        found = js.called("timeframeNamed", name)
        assert found == {
            "name": name,
            "checked": checked,
            "supported": supported,
            "tooltip": tooltip,
        }, f"{state} switch {name}"


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_a_switch_is_greyed_by_name_and_never_by_its_place_in_the_served_list(
    js: JsRuntime, state: str
):
    """Eight served timeframes against eleven switches: the lists differ in length."""
    payload = state_payload(state)
    js.push(payload)
    served = payload["allowed_timeframes"]
    assert len(served) != len(payload["timeframes"])
    for name in payload["timeframes"]:
        assert js.called("isAllowed", name) == (name in served), name


def test_the_served_check_would_mislabel_two_switches_if_it_counted_places(
    js: JsRuntime,
):
    """Pairing by position greys 6h and 1d wrongly on a Coinbase bot."""
    payload = state_payload("running")
    js.push(payload)
    served = payload["allowed_timeframes"]
    named = payload["timeframes"]
    by_place = [
        at < len(served) and served[at] == name for at, name in enumerate(named)
    ]
    by_name = [js.called("isAllowed", name) for name in named]
    wrong = [named[at] for at in range(len(named)) if by_place[at] != by_name[at]]
    assert wrong == ["6h", "1d"], f"position pairing moved {wrong}"


def test_the_switch_check_names_a_greyed_flag_that_left_the_served_list(js: JsRuntime):
    payload = state_payload("running")
    payload["allowed_timeframes"] = payload["allowed_timeframes"][1:]
    report = js.push(payload)
    named = [
        one["where"] for one in report["faults"] if one["field"] == "allowed_timeframes"
    ]
    assert named == ["timeframe:1m"]


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_status_row_is_found_by_its_own_label(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert len(payload["summary_rows"]) == len(payload["labels"])
    for label, value, sheet in payload["summary_rows"]:
        assert js.called("summaryValue", label) == value, f"{state} row {label}"
        assert js.called("summarySheet", label) == sheet


def test_the_status_check_names_a_label_the_payload_stopped_drawing(js: JsRuntime):
    payload = state_payload("running")
    payload["summary_rows"].pop()
    report = js.push(payload)
    missing = [
        one
        for one in report["faults"]
        if one["fault"] == "missing" and one["field"] == "summary_rows"
    ]
    assert [one["detail"] for one in missing] == [payload["labels"]["lock_state_row"]]


@pytest.mark.parametrize("state", ("toggled", "picked", "moved"))
def test_each_edit_is_named_by_its_own_field_in_the_order_it_was_made(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "changedFields()") == [one[0] for one in payload["changes"]]


def test_the_edit_order_check_would_see_two_edits_swapped(js: JsRuntime):
    payload = state_payload("picked")
    payload["changes"].append(["enable_phantoms", False])
    js.push(payload)
    written = js.json(API + "changedFields()")
    assert written == ["phantom_timeframes", "enable_phantoms"]
    assert written != sorted(written)


def test_the_enable_switch_runs_its_own_handler_with_the_flag_it_moved_to(
    js: JsRuntime,
):
    payload = state_payload("running")
    js.push(payload)
    pressed = js.json(API + "pressEnable(false)")
    assert pressed["name"] == "phantom_enable.toggled"
    assert pressed["argument"] == [False]
    assert pressed["action"] == payload["actions"]["phantom_enable.toggled"]
    assert pressed["step"] == "enable"


@pytest.mark.parametrize("at", range(len(surface.TIMEFRAMES)))
def test_each_timeframe_switch_runs_its_own_handler_with_its_own_name(
    js: JsRuntime, at: int
):
    """Eleven switches share one handler, so only the argument tells them apart."""
    payload = state_payload("running")
    js.push(payload)
    name, _checked, supported, _tip = payload["timeframe_checks"][at]
    js.bind_json("TF", name)
    pressed = js.json(API + "pressTimeframe(JSON.parse(TF), true)")
    if not supported:
        assert pressed is None, f"{name} is greyed and must move nothing"
        return
    assert pressed["argument"] == [name, True]
    assert pressed["action"] == payload["actions"]["timeframe_check.toggled"]
    assert pressed["step"] == "timeframe"


def test_the_lock_number_runs_its_own_handler_with_the_number_it_moved_to(
    js: JsRuntime,
):
    payload = state_payload("running")
    js.push(payload)
    pressed = js.json(API + "pressLock(7)")
    assert pressed["argument"] == [7]
    assert pressed["action"] == payload["actions"]["lock_spin.valueChanged"]
    assert pressed["step"] == "lock"


def test_the_press_check_would_see_a_setting_that_answered_with_another_name(
    js: JsRuntime,
):
    js.push(state_payload("running"))
    js.json(API + "pressTimeframe('1m', true)")
    assert js.json(API + "pressed()")["argument"] != ["5m", True]


def test_each_setting_sends_the_step_its_own_model_method_names(js: JsRuntime):
    """The step is matched to the method the action bag names, never counted."""
    payload = state_payload("running")
    js.push(payload)
    found = {name: js.called("stepFor", name) for name in payload["actions"]}
    assert found == {
        "phantom_enable.toggled": "enable",
        "timeframe_check.toggled": "timeframe",
        "lock_spin.valueChanged": "lock",
    }
    assert set(found.values()) < set(payload["steps"])


def test_the_step_match_names_a_setting_whose_method_names_no_step(js: JsRuntime):
    payload = state_payload("running")
    payload["actions"]["lock_spin.valueChanged"] = "no_such_method"
    report = js.push(payload)
    assert [one["where"] for one in report["faults"] if one["field"] == "steps"] == [
        "setting:lock_spin.valueChanged"
    ]


@pytest.mark.parametrize("state", ("toggled", "picked", "moved"))
def test_each_move_reaches_the_surface_as_the_step_the_tab_took(state: str):
    """The tab records only the field that changed, which the payload carries."""
    payload = state_payload(state)
    assert len(payload["changes"]) == 1
    assert payload["changes"][0][0] in payload["fields"].values()


def test_a_switch_set_to_the_value_it_already_holds_records_nothing():
    """A positive answer is the run above; this one proves it can stay quiet."""
    surface.view_model({"reset": True, "bot": bot()})
    quiet = as_json(surface.view_model({"steps": [["enable", True]]}))
    assert quiet["changes"] == []


HOSTILE_VALUES: dict = {
    "null": None,
    "a number where text belongs": 7,
    "text where a number belongs": "seven",
    "nan": "nan",
    "inf": "inf",
    "minus inf": "-inf",
    "huge": 10**24,
    "a long name": LONG_NAME,
    "markup": MARKUP_NAME,
    "a newline": NEWLINE_NAME,
    "a bag": {},
    "a list": [],
}

ANSWERS = (
    "isLoaded()",
    "kinds()",
    "timeframeNames()",
    "summaryRows()",
    "changedFields()",
    "notPlainData()",
    "faults()",
)


def still_answers(js: JsRuntime, case: str) -> None:
    for one in ANSWERS:
        js.json(API + one)
    for kind in ("phantom", "locks"):
        js.bind_json("KIND", kind)
        assert isinstance(js.json(API + "rowsOf(JSON.parse(KIND))"), list), case
        assert isinstance(js.json(API + "columnsOf(JSON.parse(KIND))"), list), case


@pytest.mark.parametrize("name", sorted(state_payload("running")))
def test_a_field_the_payload_drops_or_nulls_is_reported_and_the_module_answers_on(
    js: JsRuntime, name: str
):
    """Each of the forty-nine fields, first missing and then null."""
    for value in (None,):
        payload = state_payload("running")
        del payload[name]
        report = js.push(payload)
        assert isinstance(report["faults"], list), name
        still_answers(js, name)
        payload = state_payload("running")
        payload[name] = value
        report = js.push(payload)
        assert isinstance(report["faults"], list), name
        still_answers(js, name)


def test_the_missing_field_sweep_names_every_field_it_removed(js: JsRuntime):
    """A sweep that reported nothing would be a sweep that saw nothing."""
    named = []
    for name in sorted(state_payload("running")):
        payload = state_payload("running")
        del payload[name]
        report = js.push(payload)
        if [one for one in report["faults"] if one["fault"] == "missing"]:
            named.append(name)
    assert sorted(named) == sorted(state_payload("running"))


HOSTILE_PLACES = {
    "a phantom cell": ("phantom_table", "rows"),
    "a lock cell": ("locks_table", "rows"),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_VALUES))
@pytest.mark.parametrize("place", sorted(HOSTILE_PLACES))
def test_a_hostile_cell_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str, place: str
):
    table, key = HOSTILE_PLACES[place]
    payload = state_payload("running")
    payload[table][key][0][0] = HOSTILE_VALUES[case]
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    still_answers(js, case)


@pytest.mark.parametrize("case", sorted(HOSTILE_VALUES))
def test_a_hostile_lock_number_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    payload = state_payload("running")
    payload["lock_spin"]["value"] = HOSTILE_VALUES[case]
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    still_answers(js, case)


@pytest.mark.parametrize("case", sorted(HOSTILE_VALUES))
def test_a_hostile_timeframe_switch_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    payload = state_payload("running")
    payload["timeframe_checks"][0] = HOSTILE_VALUES[case]
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    still_answers(js, case)
    assert js.called("timeframeNamed", LONG_NAME) is None


def test_a_scalar_where_a_whole_row_list_belongs_reads_as_no_row_at_all(js: JsRuntime):
    """A scalar slipping past a list walk is the hole every sweep must close."""
    payload = state_payload("running")
    payload["phantom_table"]["rows"][0] = 7
    js.push(payload)
    assert js.json(API + "cellsOf('phantom', 0)") == []
    assert js.json(API + "kinds()").get("phantom_table.rows.0") == "number"


def test_a_null_where_a_whole_row_list_belongs_reads_as_no_row_at_all(js: JsRuntime):
    payload = state_payload("running")
    payload["locks_table"]["rows"][0] = None
    js.push(payload)
    assert js.json(API + "cellsOf('locks', 0)") == []
    assert js.json(API + "kinds()").get("locks_table.rows.0") == "null"


def test_two_locks_naming_the_same_bot_are_both_kept_and_both_named(js: JsRuntime):
    """A duplicate name must not collapse two rows into one."""
    payload = state_payload("running")
    payload["locks_table"]["rows"][1][1] = payload["locks_table"]["rows"][0][1]
    js.push(payload)
    assert js.json(API + "rowsOf('locks')") == payload["locks_table"]["rows"]
    assert (
        js.json(API + "cellsOf('locks', 0)")[1]
        == js.json(API + "cellsOf('locks', 1)")[1]
    )


def test_two_switches_carrying_the_same_timeframe_are_reported(js: JsRuntime):
    payload = state_payload("running")
    payload["timeframe_checks"][1][0] = payload["timeframe_checks"][0][0]
    report = js.push(payload)
    assert [
        one["field"]
        for one in report["faults"]
        if one["fault"] == "disagrees" and one["field"] == "timeframe_checks"
    ] == ["timeframe_checks"]


@pytest.mark.parametrize("state", ("off", "waiting", "quiet"))
def test_a_bot_with_no_phantom_at_all_draws_one_note_and_neither_table(
    js: JsRuntime, state: str
):
    """Zero phantoms is the state the operator sees before the first tick."""
    payload = state_payload(state)
    js.push(payload)
    assert payload["phantom_table"]["row_count"] == 0
    assert payload["locks_table"]["row_count"] == 0
    assert payload["phantom_group"]["shown"] is False
    assert payload["locks_group"]["shown"] is False
    assert payload["empty_label"]["shown"] is True
    assert payload["empty_label"]["text"] in payload["empty_texts"].values()
    assert js.json(API + "faults()") == []


def test_a_lock_naming_a_bot_that_is_not_in_the_fleet_draws_the_raw_name(
    js: JsRuntime,
):
    """No lock row is dropped for an unknown bot; the tab shows the id as given."""
    payload = state_payload("unknown")
    js.push(payload)
    row = payload["locks_table"]["rows"][0]
    assert row[1] == UNKNOWN_BOT
    assert row[1] != surface.THIS_BOT_FORMAT.format(source_bot=UNKNOWN_BOT)
    assert payload["locks_table"]["row_colors"][0][1] is None
    assert js.json(API + "cellColour('locks', 0, 1)") is None
    assert js.json(API + "faults()") == []


def test_the_unknown_bot_check_would_see_this_bot_s_own_lock_painted(js: JsRuntime):
    payload = state_payload("running")
    js.push(payload)
    assert payload["locks_table"]["row_colors"][0][1] == payload["colors"]["this_bot"]
    assert js.json(API + "cellColour('locks', 0, 1)") is not None


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """A module that raised on one hostile value would answer nothing at all."""
    js.push(7)
    assert js.json(API + "rowsOf('phantom')") == []
    assert js.json(API + "timeframeNames()") == []
    assert js.json(API + "isLoaded()") is False


PROBE_W_PX = 400
PROBE_H_PX = 60

#: An empty tag pair a rich-text widget swallows and a plain one paints.
MARKUP_PROBE = "<span></span>1m"
PLAIN_PROBE = "1m"


def painted(widget: Any) -> bytes:
    """The pixels one widget paints, at a size every probe shares."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage

    widget.resize(QSize(PROBE_W_PX, PROBE_H_PX))
    image = QImage(PROBE_W_PX, PROBE_H_PX, QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    return bytes(image.constBits())


def a_label(text: str) -> Any:
    from PySide6.QtWidgets import QLabel

    return QLabel(text)


def a_check(text: str) -> Any:
    from PySide6.QtWidgets import QCheckBox

    return QCheckBox(text)


def a_group(text: str) -> Any:
    from PySide6.QtWidgets import QGroupBox

    return QGroupBox(text)


def a_cell(text: str) -> Any:
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    table = QTableWidget(1, 1)
    table.setItem(0, 0, QTableWidgetItem(text))
    return table


def a_header(text: str) -> Any:
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    table = QTableWidget(1, 1)
    table.setHorizontalHeaderItem(0, QTableWidgetItem(text))
    return table


def a_spin(text: str) -> Any:
    from PySide6.QtWidgets import QSpinBox

    widget = QSpinBox()
    widget.setPrefix(text)
    return widget


SCREEN_WIDGETS = {
    "QCheckBox": a_check,
    "QGroupBox": a_group,
    "QTableWidgetItem": a_cell,
    "QHeaderView": a_header,
    "QSpinBox": a_spin,
}

RICH_TEXT_WIDGETS = {"QLabel": a_label}


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_no_plain_widget_this_tab_uses_reads_its_caller_text_as_markup(qapp, kind: str):
    """A widget painting MARKUP_PROBE apart from PLAIN_PROBE never read its tags."""
    assert qapp is not None
    build_widget = SCREEN_WIDGETS[kind]
    assert painted(build_widget(MARKUP_PROBE)) != painted(
        build_widget(PLAIN_PROBE)
    ), f"{kind} painted the markup and the plain words the same"


@pytest.mark.parametrize("kind", sorted(RICH_TEXT_WIDGETS))
def test_the_one_widget_this_tab_uses_that_does_read_markup_is_named(qapp, kind: str):
    """QLabel paints MARKUP_PROBE exactly as PLAIN_PROBE, and it carries bot state."""
    assert qapp is not None
    build_widget = RICH_TEXT_WIDGETS[kind]
    assert painted(build_widget(MARKUP_PROBE)) == painted(build_widget(PLAIN_PROBE))


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_the_markup_measurement_reads_a_longer_text_as_a_different_painting(
    qapp, kind: str
):
    """A painting that never moved would read every widget as one that reads markup."""
    assert qapp is not None
    build_widget = SCREEN_WIDGETS[kind]
    assert painted(build_widget(PLAIN_PROBE * 8)) != painted(build_widget(PLAIN_PROBE))


def test_the_module_reports_markup_reaching_a_status_row_a_qlabel_paints(
    js: JsRuntime,
):
    """The lock row and the timeframe row are QLabels fed from stored bot state."""
    payload = state_payload("running")
    payload["summary_rows"][2][1] = MARKUP_NAME
    report = js.push(payload)
    assert [one["field"] for one in report["faults"] if one["fault"] == "markup"] == [
        "markup"
    ]


def test_the_markup_report_is_quiet_on_the_words_the_surface_really_sends(
    js: JsRuntime,
):
    js.push(state_payload("running"))
    assert [one for one in js.json(API + "faults()") if one["fault"] == "markup"] == []


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
            "the page never defined the phantom bots tab module in "
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
    "fontWeight",
    "fontSize",
    "fontStyle",
    "whiteSpace",
    "maxHeight",
    "overflowY",
    "tableLayout",
    "paddingTop",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.setAttribute('data-part', 'phantom-bots-page');"
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
    "        title: el.title, hidden: el.hidden, checked: el.checked === true,"
    "        disabled: el.disabled === true, value: el.value,"
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
    "  onEnable: function (n) { window.PRESSED.push(['enable', n]); },"
    "  onTimeframe: function (n) { window.PRESSED.push(['timeframe', n]); },"
    "  onLock: function (n) { window.PRESSED.push(['lock', n]); } };"
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


def test_the_tab_fills_the_named_space_the_window_left_for_it(browser: Browser):
    """The Live Bot Settings window names one space and this tab fills it."""
    parts = draw_tab(browser, state_payload("running"))
    assert browser.parsed(API + "spacePart") == "phantom-bots-page"
    assert at_path(parts, "phantom-bots-tab"), "the tab drew nothing into the space"


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A child with no name is a child no check can read."""
    draw_tab(browser, state_payload("running"))
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no data-part"
    assert named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    draw_tab(browser, state_payload("running"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_status_row_draws_the_label_and_value_the_surface_carries(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")
    assert len(drawn) == len(payload["summary_rows"])
    by_label = {one["attrs"]["data-key"]: one for one in drawn}
    for label, value, _sheet in payload["summary_rows"]:
        assert by_label[label]["text"] == value, f"{state} row {label}"


def test_each_painted_status_row_matches_a_probe_built_from_its_whole_style(
    browser: Browser,
):
    """The applied value is read against a probe built from the whole declaration."""
    payload = state_payload("running")
    parts = draw_tab(browser, payload)
    by_label = {
        one["attrs"]["data-key"]: one for one in with_part(parts, "summary-value")
    }
    for label, _value, sheet in payload["summary_rows"]:
        style = browser.parsed(API + "styleOf(" + json.dumps(sheet) + ")")
        probe = browser.parsed(
            "window.probeAssign("
            + json.dumps(style)
            + ", JSON.parse(window.STYLE_NAMES))"
        )
        found = by_label[label]["style"]
        for name in ("color", "fontWeight", "fontSize"):
            assert found[name] == probe[name], f"{label} drew {found} against {probe}"


def test_the_rendered_comparison_would_see_one_repainted_status_row(browser: Browser):
    parts = draw_tab(browser, state_payload("running"))
    drawn = with_part(parts, "summary-value")[0]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"color": OTHER_COLOUR})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert drawn["style"]["color"] != probe["color"]


def test_an_unstyled_status_row_takes_no_colour_at_all(browser: Browser):
    """The timeframes row carries an empty sheet and must be left unpainted."""
    payload = state_payload("running")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")
    quiet = [one for one in drawn if one["attrs"]["data-painted"] == "false"]
    assert quiet, "no status row was left unpainted"
    plain = browser.parsed("window.probeAssign({}, JSON.parse(window.STYLE_NAMES))")
    for one in quiet:
        assert one["style"]["color"] == plain["color"]


def test_the_unpainted_check_would_see_that_row_given_a_colour(browser: Browser):
    payload = state_payload("running")
    payload["summary_rows"][2][2] = surface.FLAG_STYLE_FORMAT.format(
        color_hex=OTHER_COLOUR
    )
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")
    assert [one for one in drawn if one["attrs"]["data-painted"] == "false"] == []


@pytest.mark.parametrize(
    "kind,table", (("phantom", "phantom_table"), ("locks", "locks_table"))
)
def test_every_column_the_surface_names_becomes_one_header_in_that_order(
    browser: Browser, kind: str, table: str
):
    payload = state_payload("running")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, kind + "-header-cell")
    assert [one["text"] for one in drawn] == payload[table]["columns"]


@pytest.mark.parametrize(
    "kind,table", (("phantom", "phantom_table"), ("locks", "locks_table"))
)
def test_every_cell_the_surface_fills_is_drawn_in_its_own_row_and_column(
    browser: Browser, kind: str, table: str
):
    payload = state_payload("running")
    parts = draw_tab(browser, payload)
    rows = with_part(parts, kind + "-row")
    assert len(rows) == payload[table]["row_count"]
    cells = with_part(parts, kind + "-cell")
    assert len(cells) == payload[table]["row_count"] * payload[table]["column_count"]
    assert [one["text"] for one in cells] == [
        text for row in payload[table]["rows"] for text in row
    ]


@pytest.mark.parametrize(
    "kind,table", (("phantom", "phantom_table"), ("locks", "locks_table"))
)
def test_each_painted_cell_takes_the_colour_the_surface_gave_that_cell(
    browser: Browser, kind: str, table: str
):
    payload = state_payload("running")
    parts = draw_tab(browser, payload)
    cells = with_part(parts, kind + "-cell")
    wanted = [one for row in payload[table]["row_colors"] for one in row]
    for at, one in enumerate(cells):
        assert one["attrs"]["data-painted"] == str(wanted[at] is not None).lower()
        if wanted[at] is None:
            continue
        probe = browser.parsed(
            "window.probeAssign("
            + json.dumps({"color": wanted[at]})
            + ", JSON.parse(window.STYLE_NAMES))"
        )
        assert one["style"]["color"] == probe["color"], f"cell {at}"


@pytest.mark.parametrize("kind", ("phantom", "locks"))
def test_an_unpainted_cell_takes_no_colour_even_though_a_colour_slot_exists(
    browser: Browser, kind: str
):
    """The surface sends a slot per cell, so painting on the slot paints them all."""
    parts = draw_tab(browser, state_payload("running"))
    cells = with_part(parts, kind + "-cell")
    quiet = [one for one in cells if one["attrs"]["data-painted"] == "false"]
    assert quiet, "every cell was painted"
    plain = browser.parsed("window.probeAssign({}, JSON.parse(window.STYLE_NAMES))")
    for one in quiet:
        assert one["style"]["color"] == plain["color"]


def test_the_unpainted_cell_check_would_see_every_cell_painted(browser: Browser):
    payload = state_payload("running")
    payload["no_cell_color"] = OTHER_COLOUR
    parts = draw_tab(browser, payload)
    cells = with_part(parts, "phantom-cell")
    assert [one for one in cells if one["attrs"]["data-painted"] == "false"] == []


@pytest.mark.parametrize(
    "kind,table", (("phantom", "phantom_table"), ("locks", "locks_table"))
)
def test_each_table_row_carries_the_number_qt_draws_down_its_own_left_edge(
    browser: Browser, kind: str, table: str
):
    """The surface says the vertical header shows, so the numbers are drawn."""
    payload = state_payload("running")
    parts = draw_tab(browser, payload)
    assert payload["table_rules"]["vertical_header_visible"] is True
    drawn = with_part(parts, kind + "-row-number")
    assert [one["text"] for one in drawn] == [
        str(at + 1) for at in range(payload[table]["row_count"])
    ]
    assert len(with_part(parts, kind + "-corner")) == 1


def test_the_row_number_gutter_goes_away_when_the_surface_hides_it(browser: Browser):
    payload = state_payload("running")
    payload["table_rules"]["vertical_header_visible"] = False
    parts = draw_tab(browser, payload)
    assert with_part(parts, "phantom-row-number") == []
    assert with_part(parts, "phantom-corner") == []


@pytest.mark.parametrize(
    "kind,table", (("phantom", "phantom_table"), ("locks", "locks_table"))
)
def test_each_table_is_held_to_the_ceiling_the_surface_gives_it(
    browser: Browser, kind: str, table: str
):
    """Qt clips at the ceiling; the box scrolls at the same one."""
    payload = state_payload("running")
    parts = draw_tab(browser, payload)
    box = with_part(parts, kind + "-table-box")[0]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps(
            {
                "maxHeight": str(payload[table]["max_height_px"]) + "px",
                "overflow": "auto",
            }
        )
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert box["style"]["maxHeight"] == probe["maxHeight"]
    assert box["style"]["overflowY"] == probe["overflowY"]


def test_the_ceiling_check_would_see_a_table_given_a_taller_one(browser: Browser):
    payload = state_payload("running")
    parts = draw_tab(browser, payload)
    taller = payload["phantom_table"]["max_height_px"] * 2
    box = with_part(parts, "phantom-table-box")[0]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"maxHeight": str(taller) + "px"})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert box["style"]["maxHeight"] != probe["maxHeight"]


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_group_is_shown_only_where_the_surface_shows_it(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    for kind, group in (("phantom", "phantom_group"), ("locks", "locks_group")):
        drawn = with_part(parts, kind + "-group")[0]
        assert drawn["hidden"] is not payload[group]["shown"], f"{state} {kind}"
    note = with_part(parts, "empty-note")[0]
    assert note["hidden"] is not payload["empty_label"]["shown"]


def test_the_shown_check_would_see_a_group_the_surface_hid_drawn_open(
    browser: Browser,
):
    payload = state_payload("quiet")
    payload["phantom_group"]["shown"] = True
    parts = draw_tab(browser, payload)
    assert with_part(parts, "phantom-group")[0]["hidden"] is False


@pytest.mark.parametrize("note", ("info-note", "timeframe-hint", "empty-note"))
def test_each_wrapped_note_keeps_the_line_break_its_own_words_carry(
    browser: Browser, note: str
):
    """CSS collapses a newline that a wrapped QLabel breaks on, unless told not to."""
    payload = state_payload("off")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, note)[0]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"whiteSpace": "pre-wrap"})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert drawn["attrs"]["data-word-wrap"] == "true"
    assert drawn["style"]["whiteSpace"] == probe["whiteSpace"]


def test_the_line_break_check_would_see_a_note_told_to_collapse_it(browser: Browser):
    parts = draw_tab(browser, state_payload("off"))
    drawn = with_part(parts, "info-note")[0]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"whiteSpace": "normal"})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert drawn["style"]["whiteSpace"] != probe["whiteSpace"]


def test_the_info_note_the_surface_sends_really_does_carry_a_line_break():
    assert "\n" in surface.INFO_TEXT


def test_the_enable_box_draws_the_state_the_surface_carries(browser: Browser):
    for state, wanted in (("running", True), ("off", False)):
        payload = state_payload(state)
        parts = draw_tab(browser, payload)
        drawn = with_part(parts, "enable-check")[0]
        assert drawn["checked"] is payload["enable_check"]["checked"]
        assert drawn["checked"] is wanted


def test_clicking_the_enable_box_runs_the_handler_with_the_flag_it_moved_to(
    browser: Browser,
):
    draw_tab(browser, state_payload("running"))
    browser.js("window.partNamed('enable-check').click();")
    assert browser.parsed("window.PRESSED") == [["enable", False]]
    assert browser.parsed(API + "pressed()")["step"] == "enable"


def test_every_timeframe_box_draws_its_own_name_state_and_grey(browser: Browser):
    payload = state_payload("running")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "timeframe-check")
    assert [one["attrs"]["data-key"] for one in drawn] == payload["timeframes"]
    for at, one in enumerate(drawn):
        name, checked, supported, tooltip = payload["timeframe_checks"][at]
        assert one["attrs"]["data-key"] == name
        assert one["checked"] is checked
        assert one["disabled"] is not supported
        assert one["title"] == tooltip


@pytest.mark.parametrize("at", range(len(surface.TIMEFRAMES)))
def test_clicking_one_timeframe_box_runs_the_handler_with_that_timeframe(
    browser: Browser, at: int
):
    payload = state_payload("running")
    draw_tab(browser, payload)
    name, checked, supported, _tip = payload["timeframe_checks"][at]
    browser.js("window.partsNamed('timeframe-check')[" + str(at) + "].click();")
    if not supported:
        assert browser.parsed("window.PRESSED") == [], f"{name} is greyed"
        return
    assert browser.parsed("window.PRESSED") == [["timeframe", [name, not checked]]]


def test_the_timeframe_check_would_see_a_box_answering_with_its_own_position(
    browser: Browser,
):
    payload = state_payload("running")
    draw_tab(browser, payload)
    browser.js("window.partsNamed('timeframe-check')[1].click();")
    assert browser.parsed("window.PRESSED")[0][1][0] != 1


def test_the_lock_box_draws_the_floor_the_ceiling_and_the_value_it_kept(
    browser: Browser,
):
    payload = state_payload("moved")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "lock-spin")[0]
    assert drawn["value"] == str(payload["lock_spin"]["value"])
    assert drawn["attrs"]["min"] == str(payload["lock_spin"]["minimum"])
    assert drawn["attrs"]["max"] == str(payload["lock_spin"]["maximum"])
    assert drawn["title"] == payload["lock_spin"]["tooltip"]


def test_typing_in_the_lock_box_runs_the_handler_with_the_number_typed(
    browser: Browser,
):
    draw_tab(browser, state_payload("running"))
    browser.js(
        "(function () { var el = window.partNamed('lock-spin');"
        " var setter = Object.getOwnPropertyDescriptor("
        "   window.HTMLInputElement.prototype, 'value').set;"
        " setter.call(el, '7');"
        " el.dispatchEvent(new Event('input', { bubbles: true })); })()"
    )
    assert browser.parsed("window.PRESSED") == [["lock", 7]]
    assert browser.parsed(API + "pressed()")["step"] == "lock"


def test_the_handler_check_would_see_a_press_nobody_made(browser: Browser):
    draw_tab(browser, state_payload("running"))
    assert browser.parsed("window.PRESSED") == []


def test_each_move_sends_one_step_the_surface_would_take(browser: Browser):
    """The step and its argument are what run_steps reads on the other side."""
    draw_tab(browser, state_payload("running"))
    browser.js("window.partNamed('enable-check').click();")
    sent = browser.parsed(API + "sent()")
    assert [one["params"]["steps"] for one in sent] == [[["enable", False]]]


def test_the_tab_refuses_markup_a_hostile_cell_carries(browser: Browser):
    """React writes the tags as text, so no element reaches the document."""
    payload = state_payload("running")
    payload["phantom_table"]["rows"][0][1] = MARKUP_NAME
    parts = draw_tab(browser, payload)
    drawn = [
        one
        for one in with_part(parts, "phantom-cell")
        if one["attrs"]["data-column"] == "1"
    ]
    assert drawn[0]["text"] == MARKUP_NAME
    assert "<img" not in drawn[0]["html"]
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_tab_refuses_markup_a_hostile_status_row_carries(browser: Browser):
    payload = state_payload("running")
    payload["summary_rows"][2][1] = MARKUP_NAME
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")[2]
    assert drawn["text"] == MARKUP_NAME
    assert "<img" not in drawn["html"]


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    draw_tab(browser, state_payload("running"))
    browser.js("window.HOST.firstChild.insertAdjacentHTML('beforeend', '<img>');")
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 1


def test_a_two_hundred_character_name_stretches_the_table_rather_than_clipping(
    browser: Browser,
):
    """A CSS table grows to fit where Qt clips, so the width is reported."""
    payload = state_payload("running")
    payload["locks_table"]["rows"][0][1] = LONG_NAME
    wide = with_part(draw_tab(browser, payload), "locks-table")[0]
    narrow = with_part(draw_tab(browser, state_payload("running")), "locks-table")[0]
    assert wide["width"] >= narrow["width"]


def test_a_two_hundred_character_name_does_not_widen_the_tab_itself(browser: Browser):
    """The table box scrolls, so the long name never pushes the window wide."""
    payload = state_payload("running")
    payload["locks_table"]["rows"][0][1] = LONG_NAME
    parts = draw_tab(browser, payload)
    tab = at_path(parts, "phantom-bots-tab")[0]
    assert tab["width"] <= HOST_WIDTH_PX


def test_a_newline_in_a_hostile_cell_is_written_as_text_and_not_as_two_rows(
    browser: Browser,
):
    payload = state_payload("running")
    payload["phantom_table"]["rows"][0][1] = NEWLINE_NAME
    parts = draw_tab(browser, payload)
    drawn = [
        one
        for one in with_part(parts, "phantom-cell")
        if one["attrs"]["data-column"] == "1"
    ]
    assert drawn[0]["text"] == NEWLINE_NAME
    assert len(with_part(parts, "phantom-row")) == payload["phantom_table"]["row_count"]


def test_the_tab_declares_its_own_spacing_and_leaves_the_form_to_the_host(
    browser: Browser,
):
    """The surface sets a spacing and no margin, and says the host builds the form."""
    payload = state_payload("running")
    parts = draw_tab(browser, payload)
    tab = at_path(parts, "phantom-bots-tab")[0]
    assert (
        tab["attrs"]["data-margins-set"]
        == str(payload["container"]["margins_set"]).lower()
    )
    group = with_part(parts, "summary-group")[0]
    assert (
        group["attrs"]["data-configured-by-host"]
        == str(payload["forms"]["configured_by_host"]).lower()
    )
    assert group["attrs"]["data-matched"] == str(payload["forms"]["configured"])


def test_the_stretch_the_shipped_tab_adds_is_drawn_only_once_it_is_built(
    browser: Browser,
):
    built = with_part(draw_tab(browser, state_payload("running")), "tab-stretch")
    bare = with_part(draw_tab(browser, state_payload("fresh")), "tab-stretch")
    assert len(built) == 1
    assert bare == []
