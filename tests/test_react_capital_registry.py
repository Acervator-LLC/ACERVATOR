"""The React Capital Registry table, against its surface, driven by pytest."""

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

from src.gui.main_tabs import capital_registry_surface as surface
from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    load_order,
    new_engine,
    runs_after,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "capital_registry.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorCapitalRegistry."
SETTER = "acervatorSetCapitalRegistry"

#: The merged pieces the page loads beside this module, needed at call time.
SHARED_MODULES = (WEB / "header_strip.js",)

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
KEPT_COLOUR = "#123a63"
HOVER_SHEET = "QLabel { color: %s; } QLabel:hover { color: %s; }"

PLAIN_TYPES = (str, int, float, bool, type(None))

MONEY_COLUMNS = (
    "Reserved USD",
    "Reserved Base",
    "Last Rate USD/Base",
    "Initial USD",
    "Profit Δ",
)


def bot(
    name: str,
    usd: Any = 100.0,
    base: Any = 0.5,
    rate: Any = 1000.0,
    exchange: str = "coinbase",
    currency: str = "BTC",
    mode: str = "scrumming",
) -> dict:
    """One reservation as the bridge hands it, its seven bot fields defaulted."""
    return {
        "bot_id": name,
        "exchange_id": exchange,
        "base_currency": currency,
        "reserved_usd": usd,
        "reserved_base": base,
        "bot_mode": mode,
        "last_rate_usd_per_base": rate,
    }


THREE = [bot("bot-0", 100.0), bot("bot-1", 101.0, 1.5), bot("bot-2", 102.0, 2.5)]
GROWN = [bot("bot-0", 137.55), bot("bot-1", 101.0, 1.5), bot("bot-2", 42.25, 2.5)]
TWINS = [bot("twin", 10.0), bot("twin", 30.0)]

STATES: dict = {
    "empty": [{"clear": True}],
    "one": [{"clear": True, "reservations": [bot("bot-0", 100.0)]}],
    "three": [{"clear": True, "reservations": THREE}],
    "grown": [{"clear": True, "reservations": THREE}, {"reservations": GROWN}],
    "cleared": [{"clear": True, "reservations": THREE}, {"clear": True}],
    "duplicate": [{"clear": True, "reservations": TWINS}],
    "absent": [{"clear": True, "reservations": THREE}, {}],
}
STATE_NAMES = tuple(sorted(STATES))
DRAWN_STATES = ("empty", "duplicate", "grown", "three")


@pytest.fixture(autouse=True)
def _forget_the_pane():
    """Empty the surface's own model so no test reads another's rows."""
    surface.build_view_model(surface.PANE_MODEL, None, clear=True)
    yield
    surface.build_view_model(surface.PANE_MODEL, None, clear=True)


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def build(steps: list) -> dict:
    """One payload, each step driving the same surface in the order given."""
    found: dict = {}
    for step in steps:
        found = surface.view_model(step)
    return as_json(found)


def state_payload(name: str) -> dict:
    return build(STATES[name])


def token_payload() -> dict:
    return as_json(dss.view_model({}))


def shown_values() -> set:
    """Every string the table paints as a cell, a header or a name."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        found |= set(payload["columns"])
        for row in payload["rows"]:
            found |= {one for one in row if isinstance(one, str)}
        found |= {payload["widget"]["accessible_name"]}
        found |= set(payload["column_tooltips"].values())
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
    return found


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


def named_words() -> set:
    """Every word the module may write, taken off the surface's own names."""
    payload = state_payload("three")
    return set(payload) | set(payload["widget"]) | {surface.METHOD}


NAMED_WORDS = named_words()
DATA_KEYS = published_keys() - NAMED_WORDS
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: A colour no design token carries, so the colour line names one kind only.
LONE_COLOUR = next(
    one for one in ("#123a63", "#7c1fa2", "#0b9e41") if one not in TOKEN_VALUES
)
#: A token value that is no colour, so the token line names one kind only.
LONE_TOKEN = next(one for one in sorted(TOKEN_VALUES) if not HEX_COLOUR.findall(one))

WRITTEN_LINES = {
    "number": "var written = 7;\n",
    "colour": 'var written = "' + LONE_COLOUR + '";\n',
    "shown_value": 'var written = "' + sorted(SHOWN_VALUES)[0] + '";\n',
    "token_value": 'var written = "' + LONE_TOKEN + '";\n',
    "regex": "var written = /abc/;\n",
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


class JsRuntime(JsEngine):
    """A QJSEngine holding the table module and the merged pieces beside it."""

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


def declared_fields(runtime: JsRuntime) -> list:
    return runtime.json(API + "declaredNames()")


def python_kinds(payload: dict) -> dict:
    found: dict = {}

    def descend(path: str, value: Any) -> None:
        if isinstance(value, dict):
            walk(path, value)
            return
        if isinstance(value, (list, tuple)):
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
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    """A field exists on one side and nowhere on the other."""
    payload = state_payload(state)
    js.push(payload)
    named = set(declared_fields(js))
    assert set(payload) - named == set(), state
    assert named - set(payload) == set(), state
    for name in sorted(named):
        assert js.json(API + "field(" + json.dumps(name) + ")") == payload[name], name


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    """A field the module never declared would pass unnoticed."""
    payload = state_payload("three")
    payload["only_on_the_surface"] = []
    js.push(payload)
    assert set(payload) - set(declared_fields(js)) == {"only_on_the_surface"}


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    """A field the surface stopped sending would pass unnoticed."""
    payload = state_payload("three")
    payload.pop("row_count")
    js.push(payload)
    assert set(declared_fields(js)) - set(payload) == {"row_count"}


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    """A value that changed on one side only would pass unnoticed."""
    payload = state_payload("three")
    payload["row_count"] = payload["row_count"] + 1
    js.push(payload)
    changed = [
        name
        for name in declared_fields(js)
        if js.json(API + "field(" + json.dumps(name) + ")")
        != state_payload("three")[name]
    ]
    assert changed == ["row_count"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    """A published count disagrees with the list it counts."""
    report = js.push(state_payload(state))
    assert report["declared"] == report["held"], state
    assert report["faults"] == [], state


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_published_count_is_filled_in_by_the_path_that_publishes_it(state: str):
    """A count published beside a list never got filled in."""
    payload = state_payload(state)
    assert payload["row_count"] == len(payload["rows"])
    assert payload["widget"]["column_count"] == len(payload["columns"])
    assert sorted(payload["initial_usd_bots"]) == sorted(payload["initial_usd_by_bot"])


def test_the_count_reading_would_see_a_row_count_left_at_zero(js: JsRuntime):
    """A count left at zero beside three rows would pass unnoticed."""
    payload = state_payload("three")
    payload["row_count"] = 0
    report = js.push(payload)
    assert report["declared"]["rows"] != report["held"]["rows"]
    assert [one["fault"] for one in report["faults"]] == ["disagrees"]


def test_a_dropped_row_shortens_the_held_row_count(js: JsRuntime):
    """The held count is read off the published number, not off the rows."""
    payload = state_payload("three")
    payload["rows"].pop()
    report = js.push(payload)
    assert report["held"]["rows"] == report["declared"]["rows"] - 1


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    """A missing field is counted as present."""
    payload = state_payload("three")
    payload.pop("text_color")
    report = js.push(payload)
    assert report["held"]["fields"] == report["declared"]["fields"] - 1
    assert ("text_color", "missing") in [
        (one["field"], one["fault"]) for one in report["faults"]
    ]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_nine_columns_and_the_nine_cells_of_every_row_agree(state: str):
    """A row carries fewer cells than the table has columns."""
    payload = state_payload(state)
    assert len(payload["columns"]) == payload["widget"]["column_count"]
    for at, row in enumerate(payload["rows"]):
        assert len(row) == len(payload["columns"]), (at, row)


def test_the_column_and_cell_reading_would_see_a_short_row(js: JsRuntime):
    """A row one cell short of the columns would pass unnoticed."""
    payload = state_payload("three")
    payload["rows"][1].pop()
    report = js.push(payload)
    assert ("row:1", "short-row") in [
        (one["where"], one["fault"]) for one in report["faults"]
    ]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_two_bags_the_screen_declares_none_of_stay_empty(state: str):
    """A tooltip or a width appeared that the panel never set."""
    payload = state_payload(state)
    assert payload["column_tooltips"] == {}
    assert payload["column_widths_px"] == {}


def test_the_module_writes_no_number_colour_shown_value_or_token_value():
    """A value written into the module is one that would never follow the surface."""
    assert caught_by_scan(MODULE_SOURCE) == set()


def test_the_module_names_only_the_surface_words_it_must_read():
    """The module reads a published string that is not a name."""
    assert set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS <= NAMED_WORDS


def test_every_named_word_is_a_name_and_not_a_value_the_table_shows():
    """The allowlist would let a painted value through."""
    assert NAMED_WORDS & SHOWN_VALUES == set()


def test_the_allowlist_holds_no_bot_name_the_payload_happened_to_carry():
    """A bot name read as a name would let the module write a drawn value."""
    assert NAMED_WORDS & DATA_KEYS == set()
    assert DATA_KEYS & SHOWN_VALUES, DATA_KEYS


def test_the_module_hides_no_value_behind_a_regular_expression():
    """A value inside a regular expression would escape the literal scan."""
    assert MODULE_LITERALS["slashes"] == []


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_line(kind: str):
    """The scan reports nothing on a line carrying a value."""
    assert caught_by_scan(WRITTEN_LINES[kind]) == {kind}


def test_the_scan_reads_a_string_only_in_code_and_a_colour_wherever_it_sits():
    """A value inside a comment is read the same way as one inside code."""
    shown = sorted(SHOWN_VALUES)[0]
    assert caught_by_scan("// " + shown + "\n") == set()
    assert caught_by_scan('var a = "' + shown + '";\n') == {"shown_value"}
    assert caught_by_scan("// " + LONE_COLOUR + "\n") == {"colour"}


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


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_of_every_state_arrives_as_the_type_it_left_as(
    js: JsRuntime, state: str
):
    """A value reaches the module as a different type than it left as."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "kinds()") == python_kinds(payload), state


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    """A row_count turned into text would pass unnoticed."""
    payload = state_payload("three")
    payload["row_count"] = str(payload["row_count"])
    js.push(payload)
    read = js.json(API + "kinds()")
    wanted = python_kinds(state_payload("three"))
    assert [name for name in wanted if read.get(name) != wanted[name]] == ["row_count"]


def test_the_type_walk_names_a_scalar_where_a_row_belongs(js: JsRuntime):
    """A scalar sitting where a row belongs would be walked as a row."""
    payload = state_payload("three")
    payload["rows"][1] = 7
    js.push(payload)
    read = js.json(API + "kinds()")
    assert read["rows.1"] == "number"
    assert "rows.1.0" not in read


def test_the_type_walk_names_a_null_where_a_cell_belongs(js: JsRuntime):
    """A null sitting where a cell belongs would be walked as text."""
    payload = state_payload("three")
    payload["rows"][1][0] = None
    js.push(payload)
    assert js.json(API + "kinds()")["rows.1.0"] == "null"


def test_the_type_walk_names_a_null_where_a_colour_channel_belongs(js: JsRuntime):
    """A null channel would be read as a colour."""
    payload = state_payload("three")
    payload["row_color"][1] = None
    js.push(payload)
    assert js.json(API + "kinds()")["row_color.1"] == "null"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_surface_publishes_no_live_object(state: str):
    """A live object on the payload is a value the renderer cannot serialise."""
    raw: dict = {}
    for step in STATES[state]:
        raw = surface.view_model(step)
    assert not_plain_data(raw) == [], f"{state} publishes {not_plain_data(raw)}"


def test_the_plain_data_walk_names_a_live_object_put_on_the_payload():
    """A live object put on the payload would pass unnoticed."""
    raw = surface.view_model({"clear": True, "reservations": THREE})
    raw["rows"][0][0] = surface.CapitalRegistryModel()
    assert not_plain_data(raw) == ["rows.0.0"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    """The module read a value a JSON payload can never carry."""
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    """A function bound onto the payload would pass unnoticed."""
    js.push(state_payload("three"))
    js.run(
        SETTER + "(Object.assign(" + API + "payload(), { row_count: function () {} }));"
    )
    assert js.json(API + "notPlainData()") == [
        {"path": "row_count", "kind": "function"}
    ]


def test_the_plain_data_check_names_a_function_inside_one_row(js: JsRuntime):
    """A function inside a row would escape a walk that stops at the top."""
    js.push(state_payload("three"))
    js.run(
        "var found = "
        + API
        + "payload(); found.rows[0][0] = function () {}; "
        + SETTER
        + "(found);"
    )
    assert js.json(API + "notPlainData()") == [{"path": "rows.0.0", "kind": "function"}]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_order_the_table_depends_on_arrives_as_a_list(state: str):
    """An order the table depends on arrives only as a bag."""
    payload = state_payload(state)
    assert isinstance(payload["initial_usd_bots"], list)
    assert isinstance(payload["columns"], list)
    assert isinstance(payload["rows"], list)


def test_the_recorded_bot_order_is_read_from_a_list_and_not_from_the_bag(js: JsRuntime):
    """Pairing rests on the bag's key order, which a browser moves."""
    payload = state_payload("three")
    js.push(payload)
    assert js.json(API + "botNames()") == payload["initial_usd_bots"]


def test_a_digit_bot_name_keeps_its_place_in_the_published_order(js: JsRuntime):
    """A digit-named bot is moved to the front of a bag by the browser."""
    payload = build(
        [{"clear": True, "reservations": [bot("alpha", 1.0), bot("38", 2.0)]}]
    )
    js.push(payload)
    assert payload["initial_usd_bots"] == ["alpha", "38"]
    assert js.json(API + "botNames()") == ["alpha", "38"]
    assert js.json("Object.keys(" + API + "bag('initial_usd_by_bot'))") == [
        "38",
        "alpha",
    ]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_bag_the_surface_publishes_carries_a_key_a_browser_would_move(
    js: JsRuntime, state: str
):
    """A digit key is listed before every worded key, which loses the order."""
    js.push(state_payload(state))
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "reordered-key"
    ] == []


def test_the_bag_order_check_names_a_digit_key_put_into_a_published_bag(js: JsRuntime):
    """A digit key inside a published bag would pass unnoticed."""
    payload = state_payload("three")
    payload["initial_usd_by_bot"]["0"] = 1.0
    payload["initial_usd_bots"].append("0")
    report = js.push(payload)
    moved = [one for one in report["faults"] if one["fault"] == "reordered-key"]
    assert [one["detail"] for one in moved] == ["0"]


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_row_is_named_by_the_bot_it_reports_and_not_by_where_it_sits(
    js: JsRuntime, state: str
):
    """A row is read by its place rather than by the bot it reports."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "rowIdentities()") == [row[0] for row in payload["rows"]]


def test_a_row_keeps_its_own_bot_when_the_rows_arrive_reordered(js: JsRuntime):
    """A row's name is read off its place, so reordering renames it."""
    payload = state_payload("three")
    js.push(payload)
    forward = js.json(API + "rowIdentities()")
    payload["rows"].reverse()
    js.push(payload)
    backward = js.json(API + "rowIdentities()")
    assert sorted(forward) == sorted(backward)
    assert forward != backward


def test_the_identity_check_names_a_row_naming_no_recorded_bot(js: JsRuntime):
    """A row about a bot with no starting figure would pass unnoticed."""
    payload = state_payload("three")
    payload["rows"][1][0] = "no-such-bot"
    report = js.push(payload)
    assert ("row:1", "no-bot-name") in [
        (one["where"], one["fault"]) for one in report["faults"]
    ]


def test_two_rows_on_one_bot_are_both_drawn_and_both_named(js: JsRuntime):
    """A repeated bot loses one of its rows."""
    payload = state_payload("duplicate")
    js.push(payload)
    assert js.json(API + "rowIdentities()") == ["twin", "twin"]
    assert payload["initial_usd_bots"] == ["twin"]


def payload_colour_lists(payload: dict) -> list:
    """Every colour the surface publishes, as its three channels."""
    return [payload["row_color"], payload["alt_row_color"], payload["text_color"]]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_the_table_carries_is_swept_for_the_alpha_order_fault(
    js: JsRuntime, state: str
):
    """Every published colour is swept for the eight-digit shape Qt reads first."""
    payload = state_payload(state)
    swept = payload_colour_lists(payload)
    assert len(swept) == 3, swept
    report = js.push(payload)
    assert [one for one in report["faults"] if one["fault"] == "swapped-alpha"] == []


@pytest.mark.parametrize("name", ("row_color", "alt_row_color", "text_color"))
def test_the_alpha_sweep_names_one_colour_written_with_eight_digits(
    js: JsRuntime, name: str
):
    """A colour Qt reads alpha-first would be painted red-first."""
    payload = state_payload("three")
    payload[name] = SWAPPED_ALPHA
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_one_painted_cell(js: JsRuntime):
    """A colour inside a cell would escape a sweep of the colour fields alone."""
    payload = state_payload("three")
    payload["rows"][1][2] = SWAPPED_ALPHA
    report = js.push(payload)
    assert ("rows.1.2", SWAPPED_ALPHA) in [
        (one["where"], one["detail"])
        for one in report["faults"]
        if one["fault"] == "swapped-alpha"
    ]


def test_the_alpha_sweep_reads_a_colour_inside_a_hover_block(js: JsRuntime):
    """A colour inside a hover block is a colour a declaration walk never enters."""
    payload = state_payload("three")
    payload["column_tooltips"]["Bot ID"] = HOVER_SHEET % (KEPT_COLOUR, SWAPPED_ALPHA)
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_declaration_walk_alone_never_reaches_the_hover_block(js: JsRuntime):
    """The raw sweep is needless because the declaration walk already reaches it."""
    js.push(state_payload("three"))
    sheet = HOVER_SHEET % (KEPT_COLOUR, SWAPPED_ALPHA)
    js.bind_json("SHEET", sheet)
    read = js.json("acervatorHeader.declarations(JSON.parse(SHEET))")
    assert SWAPPED_ALPHA not in [one["value"] for one in read]
    assert js.called("hexRuns", sheet) == [KEPT_COLOUR, SWAPPED_ALPHA]


def test_the_alpha_sweep_names_the_eight_digit_shape_and_no_other(js: JsRuntime):
    """A six-digit colour is named as though Qt read an alpha off it."""
    payload = state_payload("three")
    payload["column_tooltips"]["Bot ID"] = KEPT_COLOUR
    report = js.push(payload)
    assert [one for one in report["faults"] if one["fault"] == "swapped-alpha"] == []
    assert js.called("isSwappedAlpha", KEPT_COLOUR) is False
    assert js.called("isSwappedAlpha", SWAPPED_ALPHA) is True


def test_a_short_colour_is_reported_rather_than_painted(js: JsRuntime):
    """A colour missing a channel would be painted as though it were whole."""
    payload = state_payload("three")
    payload["text_color"] = payload["text_color"][:2]
    report = js.push(payload)
    assert ("text_color", "short-colour") in [
        (one["field"], one["fault"]) for one in report["faults"]
    ]
    assert js.json(API + "textColour()") is None


def test_the_colour_is_composed_from_the_whole_channel_list(js: JsRuntime):
    """A colour is composed from fewer channels than the surface published."""
    payload = state_payload("three")
    js.push(payload)
    assert js.json(API + "channelNames()") == ["red", "green", "blue"]
    for name, reader in (
        ("row_color", "rowColour"),
        ("alt_row_color", "altRowColour"),
        ("text_color", "textColour"),
    ):
        wanted = "rgb(" + ", ".join(str(one) for one in payload[name]) + ")"
        assert js.json(API + reader + "()") == wanted, name


def test_the_alternate_ground_is_taken_only_while_the_widget_asks_for_it(
    js: JsRuntime,
):
    """Painting on the colour alone paints every other row whatever the flag says."""
    payload = state_payload("three")
    js.push(payload)
    assert js.json(API + "isAlternating()") is True
    assert [js.called("alternateAt", at) for at in range(3)] == [False, True, False]
    payload["widget"]["alternating_row_colors"] = False
    js.push(payload)
    assert [js.called("alternateAt", at) for at in range(3)] == [False, False, False]


def test_the_alternate_ground_reading_would_see_a_row_painted_on_the_colour_alone(
    js: JsRuntime,
):
    """The alternate colour is still published while the flag is off."""
    payload = state_payload("three")
    payload["widget"]["alternating_row_colors"] = False
    js.push(payload)
    assert js.json(API + "altRowColour()") is not None
    assert js.json(API + "groundAt(1)") == js.json(API + "rowColour()")


HOSTILE_FIELDS: dict = {
    "columns missing": ("columns", None),
    "columns is a bag": ("columns", {}),
    "rows is text": ("rows", "one"),
    "rows is a number": ("rows", 7),
    "row_count is text": ("row_count", "three"),
    "row_count is nan": ("row_count", "nan"),
    "row_count is inf": ("row_count", "inf"),
    "row_count is minus inf": ("row_count", "-inf"),
    "row_count is huge": ("row_count", 10**24),
    "row_count is negative": ("row_count", -1),
    "widget missing": ("widget", None),
    "widget is a list": ("widget", []),
    "row_color is text": ("row_color", KEPT_COLOUR),
    "row_color is null": ("row_color", None),
    "text_color is a bag": ("text_color", {}),
    "initial_usd_by_bot is a list": ("initial_usd_by_bot", []),
    "initial_usd_bots is a bag": ("initial_usd_bots", {}),
    "column_tooltips is a list": ("column_tooltips", []),
}

HOSTILE_ROWS: dict = {
    "a short row": ["one", "two"],
    "a null row": None,
    "a scalar row": 7,
    "a bag row": {},
    "a number where text belongs": [7] * 9,
    "text where a number belongs": ["one"] * 9,
    "a nan amount": ["bot-1", "e", "b", "nan", "0", "m", "0", "0", "0"],
    "an infinite amount": ["bot-1", "e", "b", "inf", "0", "m", "0", "0", "0"],
    "a minus infinite amount": ["bot-1", "e", "b", "-inf", "0", "m", "0", "0", "0"],
    "a huge amount": ["bot-1", "e", "b", str(10**24), "0", "m", "0", "0", "0"],
    "a negative amount": ["bot-1", "e", "b", "$-5.00", "0", "m", "0", "0", "$-5.00"],
    "an amount that does not reconcile": [
        "bot-1",
        "e",
        "b",
        "$1.00",
        "5.000000",
        "m",
        "$1000.0000",
        "$1.00",
        "$+0.00",
    ],
    "a long name": [LONG_NAME] * 9,
    "markup": [MARKUP_NAME] * 9,
    "a newline": [NEWLINE_NAME] * 9,
}

ANSWERS = (
    "isLoaded()",
    "kinds()",
    "notPlainData()",
    "faults()",
    "columns()",
    "rows()",
    "rowIdentities()",
    "botNames()",
    "rowColour()",
    "altRowColour()",
    "textColour()",
)


def still_answers(runtime: JsRuntime, case: str) -> None:
    for one in ANSWERS:
        runtime.json(API + one)
    assert isinstance(runtime.json(API + "faults()"), list), case
    assert isinstance(runtime.json(API + "kinds()"), dict), case
    assert isinstance(runtime.json(API + "rowIdentities()"), list), case


@pytest.mark.parametrize("case", sorted(HOSTILE_FIELDS))
def test_a_hostile_field_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """A payload the surface would never send must report, never raise."""
    name, value = HOSTILE_FIELDS[case]
    payload = state_payload("three")
    payload[name] = value
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    still_answers(js, case)


@pytest.mark.parametrize("case", sorted(HOSTILE_ROWS))
def test_a_hostile_row_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """One bad row must not lose the rest of the table."""
    payload = state_payload("three")
    payload["rows"][1] = HOSTILE_ROWS[case]
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert len(js.json(API + "rows()")) == 3, case
    still_answers(js, case)


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """A module that raised on a hostile value would answer no rows at all."""
    js.push(7)
    assert js.json(API + "rows()") == []
    assert js.json(API + "rowIdentities()") == []
    assert js.json(API + "isLoaded()") is False


def test_a_zero_row_payload_draws_a_table_with_no_row(js: JsRuntime):
    """An empty registry drew a row of its own."""
    report = js.push(state_payload("empty"))
    assert report["held"]["rows"] == 0
    assert js.json(API + "rows()") == []
    assert js.json(API + "columns()") == list(surface.COLUMNS)


def test_an_eight_digit_token_is_split_the_way_qt_reads_it():
    """Qt reads an eight-digit token alpha-first, so the leading pair is not red."""
    from PySide6.QtGui import QColor

    for token in ("#80112233", "#aabbccdd", "#00ff0000"):
        painted = QColor(token)
        assert surface.rgb(token) == (
            painted.red(),
            painted.green(),
            painted.blue(),
        ), token


def test_the_token_split_still_reads_a_three_and_a_six_digit_token():
    """The eight-digit repair broke the tokens the panel actually ships."""
    from PySide6.QtGui import QColor

    for token in ("#abc", "#123456", "#ffffff", "#f7f7f7", "#000000"):
        painted = QColor(token)
        assert surface.rgb(token) == (
            painted.red(),
            painted.green(),
            painted.blue(),
        ), token


def test_a_reservation_the_grid_refuses_records_no_starting_figure():
    """A refused amount became the figure a later Profit Delta measured against."""
    model = surface.CapitalRegistryModel()
    with pytest.raises(ValueError):
        surface.build_view_model(model, [bot("bot-1", "20.0")])
    assert model.initial_usd_by_bot == {}
    found = surface.build_view_model(model, [bot("bot-1", 100.0)])
    assert found["rows"][0][7] == "$100.00"
    assert found["rows"][0][8] == "$+0.00"


def test_a_reservation_the_grid_draws_does_record_its_starting_figure():
    """The starting figure stopped being recorded at all."""
    model = surface.CapitalRegistryModel()
    surface.build_view_model(model, [bot("bot-1", 20.0)])
    assert model.initial_usd_by_bot == {"bot-1": 20.0}
    found = surface.build_view_model(model, [bot("bot-1", 100.0)])
    assert found["rows"][0][7] == "$20.00"
    assert found["rows"][0][8] == "$+80.00"


def test_the_refusal_the_screen_makes_on_an_unreadable_amount_still_stands():
    """An unreadable amount was quietly drawn as a number the operator can read."""
    model = surface.CapitalRegistryModel()
    for amount in (None, "abc", "20.0"):
        with pytest.raises((TypeError, ValueError)):
            surface.build_view_model(model, [bot("bot-1", amount)])


STYLE_NAMES = [
    "color",
    "background-color",
    "white-space",
    "text-overflow",
    "overflow",
    "table-layout",
    "border-collapse",
    "text-align",
    "width",
]

PAGE_HELPERS = """
window.HOST = (function () {
  var found = document.querySelector('[data-part="capital-registry-page"]');
  if (!found) {
    found = document.createElement('div');
    found.setAttribute('data-part', 'capital-registry-page');
    found.style.width = '%dpx';
    found.style.height = '%dpx';
    document.body.appendChild(found);
  }
  return found;
})();
window.readStyle = function (el, names) {
  var got = window.getComputedStyle(el);
  var out = {};
  names.forEach(function (n) { out[n] = got.getPropertyValue(n); });
  return out;
};
window.probeAssign = function (style, names) {
  var probe = document.createElement('div');
  Object.keys(style).forEach(function (k) { probe.style[k] = style[k]; });
  document.body.appendChild(probe);
  var out = window.readStyle(probe, names);
  probe.parentNode.removeChild(probe);
  return out;
};
window.partsNamed = function (name) {
  return Array.prototype.slice.call(
    window.HOST.querySelectorAll('[data-part="' + name + '"]')
  );
};
""" % (
    HOST_WIDTH_PX,
    HOST_HEIGHT_PX,
)

READ_PARTS = """
JSON.stringify((function () {
  var names = JSON.parse(window.STYLE_NAMES);
  var found = [];
  function walk(node, path) {
    if (!node || node.nodeType !== 1) { return; }
    var own = node.getAttribute('data-part');
    var here = own ? (path ? path + '/' + own : own) : path;
    if (own) {
      var attrs = {};
      Array.prototype.slice.call(node.attributes).forEach(function (a) {
        attrs[a.name] = a.value;
      });
      var text = '';
      Array.prototype.slice.call(node.childNodes).forEach(function (c) {
        if (c.nodeType === 3) { text += c.nodeValue; }
      });
      found.push({
        path: here,
        tag: node.tagName.toLowerCase(),
        attrs: attrs,
        text: text,
        whole: node.textContent,
        html: node.innerHTML,
        title: node.getAttribute('title'),
        width: node.getBoundingClientRect().width,
        style: window.readStyle(node, names)
      });
    }
    Array.prototype.slice.call(node.children).forEach(function (c) {
      walk(c, here);
    });
  }
  Array.prototype.slice.call(window.HOST.children).forEach(function (c) {
    walk(c, '');
  });
  return found;
})())
"""

COUNT_ELEMENTS = (
    "[window.HOST.querySelectorAll('*').length,"
    " window.HOST.querySelectorAll('[data-part]').length]"
)


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
            "the page never defined the capital registry module in "
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
        return json.loads(
            self.js(
                "JSON.stringify((function () { var v = "
                + expression
                + "; return v === undefined ? null : v; })())"
            )
        )

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


def draw_table(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    browser.js(
        "acervatorSetTokens(JSON.parse(window.TOKENS));"
        "acervatorTokens.apply(document.documentElement);"
    )
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        SETTER + "(JSON.parse(window.PAYLOAD));" + API + "fill(window.HOST, null);"
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


def test_the_table_fills_the_named_space_the_window_left_for_it(browser: Browser):
    """The window names one space and this table fills it."""
    parts = draw_table(browser, state_payload("three"))
    assert browser.parsed(API + "spacePart") == "capital-registry-page"
    assert at_path(parts, "capital-registry-tab"), "the table drew nothing"


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A child with no name is a child no check can read."""
    draw_table(browser, state_payload("three"))
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no data-part"
    assert named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    """An unnamed child would pass unnoticed."""
    draw_table(browser, state_payload("three"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_the_drawn_cells_carry_the_words_the_surface_sent(browser: Browser, state: str):
    """A cell drew something other than the text the surface sent."""
    payload = state_payload(state)
    parts = draw_table(browser, payload)
    drawn = with_part(parts, "registry-cell")
    wanted = [str(cell) for row in payload["rows"] for cell in row]
    assert [one["text"] for one in drawn] == wanted, state


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_each_drawn_cell_names_its_own_column_and_its_own_bot(
    browser: Browser, state: str
):
    """A cell is found by its place rather than by its column's own name."""
    payload = state_payload(state)
    parts = draw_table(browser, payload)
    drawn = with_part(parts, "registry-cell")
    wanted = [name for row in payload["rows"] for name in payload["columns"]]
    assert [one["attrs"]["data-column"] for one in drawn] == wanted, state
    for one in drawn:
        assert (
            one["attrs"]["data-name"]
            == payload["rows"][int(one["attrs"]["data-row"])][0]
        )


def test_every_money_column_is_found_by_its_own_name(browser: Browser):
    """A money column is read off a place the surface never promised."""
    payload = state_payload("three")
    parts = draw_table(browser, payload)
    drawn = with_part(parts, "registry-cell")
    for name in MONEY_COLUMNS:
        assert name in payload["columns"], name
        cells = [one for one in drawn if one["attrs"]["data-column"] == name]
        assert len(cells) == len(payload["rows"]), name


def test_the_drawn_ground_matches_a_probe_built_from_the_whole_channel_list(
    browser: Browser,
):
    """The drawn ground is compared against a typed colour, not the published one."""
    payload = state_payload("three")
    parts = draw_table(browser, payload)
    rows = with_part(parts, "registry-row")
    plain = probe_for(browser, {"backgroundColor": browser.parsed(API + "rowColour()")})
    alternate = probe_for(
        browser, {"backgroundColor": browser.parsed(API + "altRowColour()")}
    )
    for at, one in enumerate(rows):
        wanted = alternate if at % 2 else plain
        assert one["style"]["background-color"] == wanted["background-color"], at


def test_the_rendered_comparison_would_see_one_repainted_row(browser: Browser):
    """A row painted with another colour would pass unnoticed."""
    payload = state_payload("three")
    parts = draw_table(browser, payload)
    rows = with_part(parts, "registry-row")
    other = probe_for(browser, {"backgroundColor": KEPT_COLOUR})
    assert rows[0]["style"]["background-color"] != other["background-color"]


def test_the_drawn_text_colour_matches_a_probe_built_from_the_whole_channel_list(
    browser: Browser,
):
    """A cell drew its text in a colour the surface never published."""
    payload = state_payload("three")
    parts = draw_table(browser, payload)
    wanted = probe_for(browser, {"color": browser.parsed(API + "textColour()")})
    for one in with_part(parts, "registry-cell"):
        assert one["style"]["color"] == wanted["color"]


def test_no_row_takes_the_alternate_ground_while_the_flag_is_off(browser: Browser):
    """Painting on the alternate colour alone ignores the widget's own flag."""
    payload = state_payload("three")
    payload["widget"]["alternating_row_colors"] = False
    parts = draw_table(browser, payload)
    rows = with_part(parts, "registry-row")
    plain = probe_for(browser, {"backgroundColor": browser.parsed(API + "rowColour()")})
    assert [one["attrs"]["data-alternate"] for one in rows] == ["false"] * 3
    for one in rows:
        assert one["style"]["background-color"] == plain["background-color"]


def test_the_flag_reading_would_see_a_row_on_the_alternate_ground(browser: Browser):
    """The alternate ground is never taken, so the flag proves nothing."""
    parts = draw_table(browser, state_payload("three"))
    rows = with_part(parts, "registry-row")
    assert [one["attrs"]["data-alternate"] for one in rows] == [
        "false",
        "true",
        "false",
    ]


def test_the_table_declares_no_column_width_and_says_the_host_supplies_it(
    browser: Browser,
):
    """A width the surface never declared was drawn as though it had."""
    payload = state_payload("three")
    parts = draw_table(browser, payload)
    heads = with_part(parts, "header-cell")
    assert payload["column_widths_px"] == {}
    assert [one["attrs"]["data-width-set"] for one in heads] == ["false"] * 9
    assert all(one["width"] > 0 for one in heads), heads


def test_the_width_reading_would_see_a_width_the_surface_declared(browser: Browser):
    """A declared width would be reported as though the host had supplied it."""
    payload = state_payload("three")
    payload["column_widths_px"][payload["columns"][0]] = 321
    parts = draw_table(browser, payload)
    heads = with_part(parts, "header-cell")
    assert heads[0]["attrs"]["data-width-set"] == "true"
    assert heads[1]["attrs"]["data-width-set"] == "false"


def test_the_table_refuses_markup_a_hostile_cell_carries(browser: Browser):
    """React writes the tags as text, so no element reaches the document."""
    payload = state_payload("three")
    payload["rows"][1][1] = MARKUP_NAME
    parts = draw_table(browser, payload)
    drawn = [
        one
        for one in with_part(parts, "registry-cell")
        if one["attrs"]["data-row"] == "1"
    ]
    assert drawn[1]["text"] == MARKUP_NAME
    assert "<img" not in drawn[1]["html"]
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    """A tag the page ran would pass unnoticed."""
    draw_table(browser, state_payload("three"))
    browser.js("window.HOST.firstChild.insertAdjacentHTML('beforeend', '<img>');")
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 1


def test_the_renderer_runs_this_module_after_header_strip():
    """`header_strip.js` carries the declaration this module reads."""
    assert runs_after(load_order(), MODULE_PATH.name, "header_strip.js"), load_order()


def test_the_order_reading_answers_no_for_the_two_the_other_way_round():
    """The same reading of an order that runs this module first."""
    swapped = [MODULE_PATH.name, "header_strip.js"]
    assert not runs_after(swapped, MODULE_PATH.name, "header_strip.js")
    assert not runs_after(["header_strip.js"], MODULE_PATH.name, "header_strip.js")


#: An empty tag pair a rich-text widget swallows and a plain one lays out.
MARKUP_PROBE = "<span></span>bot"
PLAIN_PROBE = "bot"
PROBE_TEXT_REPEAT = 8


def a_cell(words: str) -> int:
    """The width one table column asks for to lay its own cell out."""
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    table = QTableWidget(1, 1)
    table.setItem(0, 0, QTableWidgetItem(words))
    return int(table.sizeHintForColumn(0))


def a_header(words: str) -> int:
    """The width one header section asks for to lay its own words out."""
    from PySide6.QtWidgets import QTableWidget

    table = QTableWidget(0, 1)
    table.setHorizontalHeaderLabels([words])
    return int(table.horizontalHeader().sectionSizeHint(0))


def a_label(words: str) -> int:
    """The width one label asks for to lay its caller text out."""
    from PySide6.QtWidgets import QLabel

    return int(QLabel(words).minimumSizeHint().width())


SCREEN_WIDGETS = {"QTableWidgetItem": a_cell, "QHeaderView": a_header}
RICH_TEXT_WIDGETS = {"QLabel": a_label}
EVERY_WIDGET = dict(SCREEN_WIDGETS, **RICH_TEXT_WIDGETS)


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_no_widget_this_table_uses_reads_its_caller_text_as_markup(qapp, kind: str):
    """A widget laying MARKUP_PROBE out wider than PLAIN_PROBE never read its tags."""
    assert qapp is not None
    asked = SCREEN_WIDGETS[kind]
    assert asked(MARKUP_PROBE) > asked(
        PLAIN_PROBE
    ), f"{kind} laid the markup out no wider than the plain words"


@pytest.mark.parametrize("kind", sorted(RICH_TEXT_WIDGETS))
def test_the_one_widget_that_does_read_markup_is_named(qapp, kind: str):
    """QLabel lays MARKUP_PROBE out exactly as wide as PLAIN_PROBE."""
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


def test_this_file_holds_no_carriage_return():
    """A file grew a Windows line ending the build machine reads as text."""
    for path in (MODULE_PATH, Path(__file__)):
        assert path.read_bytes().count(b"\r") == 0, path.name


def test_the_carriage_return_counter_can_report():
    """The carriage-return counter reports nothing whatever a file holds."""
    assert b"a\r\nb".count(b"\r") == 1
    assert b"a\nb".count(b"\r") == 0
