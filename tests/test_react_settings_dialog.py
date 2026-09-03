"""The React Settings dialog, driven by pytest against its own surface."""

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
from src.gui.main_tabs import settings_dialog_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "settings_dialog.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorSettingsDialog."
SETTER = "acervatorSetSettingsDialog"

#: SHARED_MODULES names the pieces the page loads beside this module.
SHARED_MODULES = (WEB / "table_cells.js", WEB / "header_strip.js")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 3
HOST_WIDTH_PX = 1200
HOST_HEIGHT_PX = 900

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
HOVER_SHEET_FORMAT = "QLabel {{ color: {plain}; }} QLabel:hover {{ color: {hidden}; }}"
GRADIENT_SHEET = "color: qlineargradient(x1: 0, y1: 0);"

HUGE_WHOLE = 10**24
UNKNOWN_NAME = "no_such_control"

STATES: dict = {
    "crypto": {},
    "stock": {"wing": "stock"},
    "unnamed wing": {"wing": "phantom"},
    "stored": {
        "settings": {
            "username": "hal",
            "position_distance_pct": 12.5,
            "default_position_count": 40,
            "default_target_balance": 950.5,
            "accent_color": "#112233",
            "theme": "neon_light",
            "increment_style": "logarithmic",
            "profit_folding": {"active": False},
            "ai_monitor": {
                "api_key": "sk-ant-api03-x",
                "interval_hours": 6.5,
                "connect_phrase": "hello",
                "confirm_phrase": "there",
                "enabled": True,
                "auto_handshake": False,
                "log_feedback": True,
            },
        }
    },
    "configured": {
        "exchanges": [
            {"exchange_id": "coinbase", "display_name": "Coinbase"},
            {"exchange_id": "kraken", "display_name": "Kraken"},
        ]
    },
}
STATE_NAMES = tuple(STATES)


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def state_payload(name: str) -> dict:
    return as_json(surface.view_model(dict(STATES[name])))


def token_payload() -> dict:
    return as_json(dss.view_model({}))


class JsRuntime(JsEngine):
    """A QJSEngine running this module beside the pieces the page loads."""

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


# --- the whole payload, both directions -----------------------------------


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    """A value the surface publishes never reaches the module."""
    payload = state_payload(state)
    js.push(payload)
    named = set(declared_fields(js))
    assert sorted(set(payload) - named) == [], sorted(set(payload) - named)
    assert sorted(named - set(payload)) == [], sorted(named - set(payload))
    assert js.json(API + "payload()") == payload


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = state_payload("crypto")
    payload["a field nobody declared"] = 1
    js.push(payload)
    assert sorted(set(payload) - set(declared_fields(js))) == [
        "a field nobody declared"
    ]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    payload = state_payload("crypto")
    del payload["banner"]
    js.push(payload)
    assert sorted(set(declared_fields(js)) - set(payload)) == ["banner"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = state_payload("crypto")
    js.push(payload)
    moved = dict(payload)
    moved["window_title"] = LONG_NAME
    assert js.json(API + "payload()") != moved
    js.push(moved)
    assert js.json(API + "payload()") == moved


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    """The two counts are reported apart so a short payload is visible."""
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(declared_fields(js))
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["tabs"] == len(payload["tabs"])
    assert report["held"]["tabs"] == len(payload["layout"])
    assert report["declared"]["controls"] == len(payload["control_specs"])
    assert report["held"]["controls"] == len(payload["values"])
    assert report["declared"]["connections"] == payload["connections"]["run_time"]
    assert report["held"]["connections"] == len(payload["connect_order"])
    assert report["faults"] == [], report["faults"]


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("crypto")
    whole = js.push(payload)["held"]["fields"]
    del payload["tooltips"]
    short = js.push(payload)
    assert short["held"]["fields"] == whole - 1
    assert short["declared"]["fields"] == len(declared_fields(js))


def test_a_dropped_tab_shortens_the_held_tab_count(js: JsRuntime):
    payload = state_payload("crypto")
    whole = js.push(payload)["held"]["tabs"]
    del payload["layout"][payload["tabs"][0]]
    short = js.push(payload)
    assert short["held"]["tabs"] == whole - 1
    assert short["declared"]["tabs"] == len(payload["tabs"])


def test_the_published_connection_count_is_filled_in(js: JsRuntime):
    """A count published as zero beside a list that is not empty is reported."""
    payload = state_payload("crypto")
    assert payload["connections"]["run_time"] > 0
    assert js.push(payload)["faults"] == []


def test_the_connection_count_check_names_a_count_left_at_zero(js: JsRuntime):
    payload = state_payload("crypto")
    payload["connections"]["run_time"] = 0
    named = [one for one in js.push(payload)["faults"] if one["field"] == "connections"]
    assert [one["fault"] for one in named] == ["disagrees", "never-filled"], named


def python_kinds(payload: dict) -> dict:
    found: dict = {}

    def walk(prefix: str, node: Any) -> None:
        for name, value in node.items():
            path = f"{prefix}.{name}" if prefix else str(name)
            found[path] = JS_TYPE_OF[type(value).__name__]
            descend(path, value)

    def descend(path: str, value: Any) -> None:
        if isinstance(value, dict):
            walk(path, value)
        elif isinstance(value, list):
            for index, one in enumerate(value):
                inner = f"{path}.{index}"
                found[inner] = JS_TYPE_OF[type(one).__name__]
                descend(inner, one)

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_of_every_state_arrives_as_the_type_it_left_as(
    js: JsRuntime, state: str
):
    """One value changed shape between the surface and the module."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "kinds()") == python_kinds(payload)


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    payload = state_payload("crypto")
    js.push(payload)
    mine = python_kinds(payload)
    mine["wing"] = JS_TYPE_OF["int"]
    assert js.json(API + "kinds()") != mine


def test_the_type_walk_names_a_scalar_where_a_row_belongs(js: JsRuntime):
    payload = state_payload("crypto")
    payload["rows"][0] = 7
    js.push(payload)
    assert js.json(API + "kinds()")["rows.0"] == "number"


def test_the_type_walk_names_a_null_where_a_connection_belongs(js: JsRuntime):
    payload = state_payload("crypto")
    payload["connect_order"][0] = None
    js.push(payload)
    assert js.json(API + "kinds()")["connect_order.0"] == "null"


def test_the_type_walk_names_a_null_inside_one_control_spec(js: JsRuntime):
    payload = state_payload("crypto")
    payload["control_specs"][0]["label"] = None
    js.push(payload)
    assert js.json(API + "kinds()")["control_specs.0.label"] == "null"


PLAIN_TYPES = (str, int, float, bool, type(None))


def not_plain_data(payload: Any) -> list:
    found: list = []

    def walk(path: str, node: Any) -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                inner = f"{path}.{name}" if path else str(name)
                walk(inner, value)
            return
        if isinstance(node, list):
            for index, value in enumerate(node):
                walk(f"{path}.{index}", value)
            return
        if not isinstance(node, PLAIN_TYPES):
            found.append({"path": path, "kind": type(node).__name__})

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_surface_publishes_no_live_object(state: str):
    """A live object on the payload would carry the dialog over the bridge."""
    assert not_plain_data(surface.view_model(dict(STATES[state]))) == []


def test_the_plain_data_walk_names_a_live_object_put_on_the_payload():
    payload = surface.view_model({})
    payload["values"]["a live object"] = surface.SettingsSource()
    assert [one["path"] for one in not_plain_data(payload)] == ["values.a live object"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    js.push(state_payload("crypto"))
    js.run("acervatorSettingsDialog.payload();")
    js.run(
        SETTER
        + "(Object.assign(JSON.parse(PAYLOAD), { texts: { one: function () {} } }));"
    )
    assert js.json(API + "notPlainData()") == [
        {"path": "texts.one", "kind": "function"}
    ]


def test_the_plain_data_check_names_a_function_inside_a_row(js: JsRuntime):
    js.push(state_payload("crypto"))
    js.run(
        SETTER + "(Object.assign(JSON.parse(PAYLOAD), { rows: [[function () {}]] }));"
    )
    assert js.json(API + "notPlainData()") == [{"path": "rows.0.0", "kind": "function"}]


# --- no value literal in the module ---------------------------------------


def shown_values() -> set:
    """Every string the dialog draws as characters, from every state."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        found |= {payload["window_title"]}
        found |= set(payload["tabs"])
        for drawn in payload["painted"].values():
            found |= {one[1] for one in drawn if isinstance(one[1], str)}
        for titles in payload["groups"].values():
            found |= set(titles)
        found |= {one for one in payload["texts"].values() if isinstance(one, str)}
        found |= {one for one in payload["values"].values() if isinstance(one, str)}
        found |= {one for one in payload["buttons"].values() if isinstance(one, str)}
        found |= {one for one in payload["headings"].values() if isinstance(one, str)}
        found |= {one[2] for one in payload["rows"] if isinstance(one[2], str)}
        found |= {one[0] for one in payload["exchange_items"]}
        found |= {one[0] for one in payload["ta_rows"]}
        found |= {one[2] for one in payload["ta_rows"]}
        found |= {one[0] for one in payload["phantom_timeframes"]}
        found |= {one[0] for one in payload["sound_test_buttons"]}
        found |= set(payload["listed_exchanges"])
        found |= {payload["banner"]["lead"], payload["banner"]["tail"]}
        found |= {one for one in payload["tooltips"].values() if isinstance(one, str)}
        for spec in payload["control_specs"]:
            found |= {
                spec[key]
                for key in ("label", "text", "placeholder", "tooltip")
                if isinstance(spec.get(key), str)
            }
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

BARE = state_payload("stock")

#: NAMED_WORDS lists every published string the module may write.
NAMED_WORDS = sorted(
    set(BARE)
    | set(BARE["banner"])
    | set(BARE["banner"]["marks"])
    | set(BARE["banner"]["alpha"])
    | set(BARE["banner"]["colour_marks"])
    | set(BARE["buttons"])
    | set(BARE["headings"])
    | set(BARE["connections"])
    | set(BARE["bus"])
    | set(BARE["timers"])
    | set(BARE["spacing"])
    | {key for spec in BARE["control_specs"] for key in spec}
    | {spec["kind"] for spec in BARE["control_specs"]}
    | {spec["echo"] for spec in BARE["control_specs"] if "echo" in spec}
    | {one[0] for one in BARE["painted"][BARE["tabs"][0]]}
    | {
        surface.METHOD,
        surface.COLUMN,
        surface.FORM,
        surface.ROW,
        surface.SCROLL,
        surface.GROUP,
        surface.CONTROL,
        surface.LABEL,
        surface.TEXT,
        surface.BUTTON,
        surface.STRETCH,
        surface.BANNER,
        surface.TA_ROWS,
        surface.TF_ROW,
        surface.SOUND_ROW,
        surface.ADD_GROUP_BY_WING,
        surface.LINE,
        surface.TEXT_AREA,
        surface.COMBO_TEXT,
        surface.COMBO_DATA,
        surface.CHECK,
        surface.RADIO,
        surface.SPIN,
        surface.DOUBLE_SPIN,
        surface.SLIDER,
        surface.LIST,
        "method",
        "built",
        "started",
    }
)


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a surface value."""
    assert not MODULE_LITERALS["numbers"], (
        "settings_dialog.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"settings_dialog.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_dialog_shows():
    written = sorted(set(MODULE_LITERALS["strings"]) & SHOWN_VALUES)
    assert not written, f"settings_dialog.js spells out dialog values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"settings_dialog.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert set(written) <= set(NAMED_WORDS), (
        "the module names published strings the list does not allow: "
        f"{sorted(set(written) - set(NAMED_WORDS))}"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_dialog_shows():
    overlap = sorted(set(NAMED_WORDS) & SHOWN_VALUES)
    assert not overlap, f"these named words are values the dialog shows: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "settings_dialog.js holds a slash outside a comment, which the literal "
        f"scan cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES: dict = {
    "colour": 'var written = "' + OTHER_COLOUR + '";',
    "tint": 'var written = "' + surface.BANNER_TINT + '";',
    "banner_lead": 'var written = "' + surface.STOCK_BANNER_LEAD + '";',
    "group_title": 'var written = "' + surface.FONT_GROUP_TITLE + '";',
    "tab_title": 'var written = "' + surface.SOUND_TAB + '";',
    "button_words": 'var written = "' + surface.TEST_BUTTON_TEXT + '";',
    "heading": 'var written = "' + surface.TA_HEADING + '";',
    "preview": 'var written = "' + surface.FONT_PREVIEW_TEXT + '";',
    "timeframe": 'var written = "' + surface.PHANTOM_TIMEFRAMES[0] + '";',
    "alpha_scale": "var written = " + str(surface.ALPHA_SCALE) + ";",
    "spacing_px": "var written = " + str(surface.SMS_CONTENT_SPACING_PX) + ";",
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


def payload_sheets(payload: dict) -> list:
    """Every rule the dialog publishes, from each place that carries one."""
    found = list(payload["styles"].values())
    found.append(payload["banner"]["style_sheet"])
    found.append(payload["banner"]["tint"])
    found.append(payload["buttons"]["save_style"])
    found.append(payload["buttons"]["ai_test_style"])
    found.append(payload["headings"]["sms_gateway_style"])
    found.append(payload["headings"]["ai_info_style"])
    return [one for one in found if one]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_the_dialog_carries_is_swept_for_the_alpha_order_fault(
    js: JsRuntime, state: str
):
    """A colour written with eight hex digits reads apart on the two sides."""
    payload = state_payload(state)
    js.push(payload)
    assert payload_sheets(payload), "no rule reached the sweep"
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "swapped-alpha"
    ] == []


SHEET_SITES = ("api_feedback", "font_preview", "ai_status", "ai_hash")


@pytest.mark.parametrize("name", SHEET_SITES)
def test_the_alpha_sweep_names_one_colour_written_with_eight_digits(
    js: JsRuntime, name: str
):
    payload = state_payload("crypto")
    payload["styles"][name] = surface.FEEDBACK_STYLE_FORMAT.format(color=SWAPPED_ALPHA)
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["where"] for one in named] == [name], named


def test_the_alpha_sweep_reads_a_colour_inside_a_hover_block(js: JsRuntime):
    """A colour Qt paints on hover sits where a base walk never looks."""
    payload = state_payload("crypto")
    payload["styles"]["api_feedback"] = HOVER_SHEET_FORMAT.format(
        plain=OTHER_COLOUR, hidden=SWAPPED_ALPHA
    )
    named = [
        one for one in js.push(payload)["faults"] if one["fault"] == "swapped-alpha"
    ]
    assert [one["detail"] for one in named] == [SWAPPED_ALPHA], named


def test_the_base_declaration_walk_alone_never_reads_the_hover_block(js: JsRuntime):
    """Without the state blocks the sweep answers nothing on the same rule."""
    sheet = HOVER_SHEET_FORMAT.format(plain=OTHER_COLOUR, hidden=SWAPPED_ALPHA)
    js.bind_json("SHEET", sheet)
    base = js.json("acervatorHeader.declarations(JSON.parse(SHEET))")
    assert [one["value"] for one in base] == [OTHER_COLOUR], base
    whole = js.called("wholeSheet", sheet)
    assert sorted(one["value"] for one in whole) == sorted(
        [OTHER_COLOUR, SWAPPED_ALPHA]
    ), whole


def test_the_alpha_sweep_names_the_eight_digit_shape_and_no_other(js: JsRuntime):
    assert js.called("isSwappedAlpha", SWAPPED_ALPHA) is True
    assert js.called("isSwappedAlpha", OTHER_COLOUR) is False
    assert js.called("isSwappedAlpha", surface.BANNER_TINT) is False


def test_the_colour_reader_reads_a_whole_rule_and_not_one_block(js: JsRuntime):
    """Every colour of a rule is read, base block and hover block alike."""
    sheet = HOVER_SHEET_FORMAT.format(plain=OTHER_COLOUR, hidden=SWAPPED_ALPHA)
    assert js.called("coloursIn", sheet) == [OTHER_COLOUR, SWAPPED_ALPHA]
    assert js.called("coloursIn", surface.STOCK_BANNER_STYLE) == [surface.BANNER_TINT]


def test_a_rule_qt_alone_can_paint_is_reported(js: JsRuntime):
    payload = state_payload("crypto")
    payload["styles"]["api_feedback"] = GRADIENT_SHEET
    named = [one for one in js.push(payload)["faults"] if one["fault"] == "not-css"]
    assert [one["where"] for one in named] == ["api_feedback"], named


def test_the_gradient_check_stays_quiet_on_a_rule_a_browser_can_paint(js: JsRuntime):
    payload = state_payload("crypto")
    payload["styles"]["api_feedback"] = surface.feedback_style(surface.ERROR_LEVEL)
    assert [
        one for one in js.push(payload)["faults"] if one["fault"] == "not-css"
    ] == []


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_bag_the_surface_publishes_carries_a_key_a_browser_would_move(
    js: JsRuntime, state: str
):
    """A digit key is listed before every worded key of the same bag."""
    js.push(state_payload(state))
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "reordered-key"
    ] == []


@pytest.mark.parametrize("name", ["texts", "values", "styles", "tooltips"])
def test_the_bag_order_check_names_a_digit_key_put_into_a_published_bag(
    js: JsRuntime, name: str
):
    payload = state_payload("crypto")
    payload[name]["7"] = payload["window_title"]
    named = [
        one for one in js.push(payload)["faults"] if one["fault"] == "reordered-key"
    ]
    assert [one["detail"] for one in named] == ["7"], named


def test_the_connections_are_read_from_a_list_and_not_from_a_bag(js: JsRuntime):
    """A bag keyed by signal cannot hold two connections in their run order."""
    payload = state_payload("crypto")
    js.push(payload)
    assert js.json(API + "handlersOn(" + json.dumps("sound_volume") + ")") == [
        "update_volume_label",
        "sfx_volume_changed",
    ]
    assert js.json(API + "connectSignals()") == [
        one[0] for one in payload["connect_order"]
    ]


def test_the_connection_order_check_would_see_the_two_swapped(js: JsRuntime):
    payload = state_payload("crypto")
    volume = [one for one in payload["connect_order"] if one[0].startswith("sound_")]
    rest = [one for one in payload["connect_order"] if not one[0].startswith("sound_")]
    payload["connect_order"] = rest + list(reversed(volume))
    js.push(payload)
    assert js.json(API + "handlersOn(" + json.dumps("sound_volume") + ")") == [
        "sfx_volume_changed",
        "update_volume_label",
    ]


def test_a_repeated_signal_is_reported_rather_than_wired_twice(js: JsRuntime):
    payload = state_payload("crypto")
    payload["connect_order"].append(list(payload["connect_order"][0]))
    payload["connections"]["run_time"] += 1
    named = [
        one for one in js.push(payload)["faults"] if one["fault"] == "duplicate-name"
    ]
    assert [one["field"] for one in named] == ["connect_order"], named


def test_every_control_is_found_by_its_own_name(js: JsRuntime):
    payload = state_payload("stored")
    js.push(payload)
    for spec in payload["control_specs"]:
        name = spec["name"]
        assert js.called("specFor", name)["name"] == name
        assert js.called("valueOf", name) == payload["values"][name], name
        assert js.called("enabledOf", name) == payload["enabled"][name], name


def test_the_control_lookup_answers_nothing_for_a_name_no_spec_carries(js: JsRuntime):
    js.push(state_payload("crypto"))
    assert js.called("specFor", UNKNOWN_NAME) is None
    assert js.called("valueOf", UNKNOWN_NAME) is None


def test_every_labelled_row_is_found_by_the_control_it_names(js: JsRuntime):
    payload = state_payload("crypto")
    js.push(payload)
    for tab, group, words, name in payload["rows"]:
        assert js.called("rowLabel", name) == words, name
        assert js.called("rowFor", name) == [tab, group, words, name], name


def test_the_row_lookup_answers_nothing_for_a_control_with_no_label(js: JsRuntime):
    js.push(state_payload("crypto"))
    assert js.called("rowLabel", "aggressive") is None
    assert js.called("rowFor", UNKNOWN_NAME) is None


def test_every_text_row_the_surface_names_is_drawn_with_a_label(js: JsRuntime):
    """Four labelled text rows, and the row list names all four."""
    payload = state_payload("crypto")
    js.push(payload)
    named = js.json(API + "textRowNames()")
    assert named == [one[3] for one in payload["text_rows"]]
    for name in named:
        assert js.called("rowLabel", name) is not None, name


def test_the_text_row_check_would_see_one_row_the_list_never_named(js: JsRuntime):
    payload = state_payload("crypto")
    payload["rows"] = [one for one in payload["rows"] if one[3] != "font_preview"]
    named = [one for one in js.push(payload)["faults"] if one["field"] == "text_rows"]
    assert [one["detail"] for one in named] == ["font_preview"], named


def test_every_indicator_row_is_found_by_its_own_label(js: JsRuntime):
    payload = state_payload("crypto")
    js.push(payload)
    for words, position, printed in payload["ta_rows"]:
        assert js.called("taRowNamed", words) == [words, position, printed], words


def test_every_timeframe_is_found_by_its_own_name(js: JsRuntime):
    payload = state_payload("crypto")
    js.push(payload)
    assert js.json(API + "timeframeNames()") == [
        one[0] for one in payload["phantom_timeframes"]
    ]
    for name, ticked in payload["phantom_timeframes"]:
        assert js.called("timeframeTicked", name) is ticked, name


def test_the_timeframe_lookup_answers_nothing_for_one_nobody_ships(js: JsRuntime):
    js.push(state_payload("crypto"))
    assert js.called("timeframeTicked", UNKNOWN_NAME) is None


def test_every_button_is_found_by_the_words_it_draws(js: JsRuntime):
    payload = state_payload("stock")
    js.push(payload)
    for words, name in payload["button_names"]:
        assert js.called("nameForButton", words) == name, words
    assert js.called("nameForButton", UNKNOWN_NAME) is None


def test_every_exchange_item_is_found_by_its_own_id(js: JsRuntime):
    payload = state_payload("crypto")
    js.push(payload)
    for words, eid in payload["exchange_items"]:
        assert js.called("exchangeItemNamed", eid) == [words, eid], eid
    assert js.called("exchangeItemNamed", UNKNOWN_NAME) is None


def test_every_step_the_dialog_ran_is_a_step_the_surface_names(js: JsRuntime):
    payload = state_payload("crypto")
    js.push(payload)
    named = set(payload["call_names"])
    assert {one[0] for one in payload["calls"]} <= named
    assert js.json(API + "faults()") == []


def test_the_step_check_names_a_step_the_surface_never_declared(js: JsRuntime):
    payload = state_payload("crypto")
    payload["calls"].append(["a step nobody declared"])
    named = [
        one for one in js.push(payload)["faults"] if one["fault"] == "unknown-step"
    ]
    assert [one["detail"] for one in named] == ["a step nobody declared"], named


def test_a_tab_with_no_layout_is_reported(js: JsRuntime):
    payload = state_payload("crypto")
    payload["tabs"].append("A tab nobody laid out")
    named = [one for one in js.push(payload)["faults"] if one["fault"] == "missing"]
    assert sorted(one["field"] for one in named) == ["groups", "layout", "painted"]


def test_a_layout_for_a_tab_nobody_shows_is_reported(js: JsRuntime):
    payload = state_payload("crypto")
    payload["layout"]["A tab nobody shows"] = payload["layout"][payload["tabs"][0]]
    named = [
        one for one in js.push(payload)["faults"] if one["fault"] == "unknown-name"
    ]
    assert [one["detail"] for one in named] == ["A tab nobody shows"], named


# --- the banner's pieces ---------------------------------------------------


def test_the_banner_is_published_as_pieces_and_as_the_line_they_build(js: JsRuntime):
    payload = state_payload("stock")
    js.push(payload)
    assert js.json(API + "rebuiltBanner()") == payload["banner"]["text"]
    assert js.json(API + "bannerPieces()") == [
        payload["banner"]["lead"],
        payload["banner"]["tail"],
    ]
    assert js.json(API + "faults()") == []


def test_the_banner_check_names_a_piece_that_no_longer_builds_the_line(js: JsRuntime):
    payload = state_payload("stock")
    payload["banner"]["lead"] = LONG_NAME
    named = [one for one in js.push(payload)["faults"] if one["fault"] == "disagrees"]
    assert "banner" in [one["field"] for one in named], named


def test_the_banner_check_names_a_piece_carrying_a_tag(js: JsRuntime):
    payload = state_payload("stock")
    payload["banner"]["pieces"][0] = MARKUP_NAME
    named = [one for one in js.push(payload)["faults"] if one["fault"] == "markup"]
    assert [one["field"] for one in named] == ["pieces"], named


def test_the_banner_colour_is_built_from_the_published_scale(js: JsRuntime):
    """The whole-number alpha becomes a fraction by the published reciprocal."""
    payload = state_payload("stock")
    js.push(payload)
    alpha = payload["banner"]["alpha"]
    marks = payload["banner"]["colour_marks"]
    parts = [str(one) for one in payload["banner"]["rgb"]]
    parts.append(str(alpha["edge"] * alpha["reciprocal"]))
    assert js.called("bannerColour", alpha["edge"]) == (
        marks["open"] + marks["join"].join(parts) + marks["close"]
    )


def test_the_banner_colour_check_would_see_the_scale_left_out(js: JsRuntime):
    payload = state_payload("stock")
    js.push(payload)
    alpha = payload["banner"]["alpha"]
    written = js.called("bannerColour", alpha["edge"])
    assert (
        str(alpha["edge"])
        not in written.split(payload["banner"]["colour_marks"]["join"])[-1]
    )
    assert str(alpha["edge"] * alpha["reciprocal"]) in written


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_word_the_dialog_draws_as_characters_carries_a_tag(
    js: JsRuntime, state: str
):
    """Only the banner line carries markup, and it is drawn from its pieces."""
    js.push(state_payload(state))
    assert [one for one in js.json(API + "faults()") if one["fault"] == "markup"] == []


MARKUP_SITES = ("texts", "values", "buttons")


@pytest.mark.parametrize("site", MARKUP_SITES)
def test_the_markup_report_names_a_tag_reaching_one_drawn_word(
    js: JsRuntime, site: str
):
    payload = state_payload("crypto")
    if site == "texts":
        payload[site]["vol_label"] = MARKUP_NAME
    elif site == "values":
        payload[site]["username"] = MARKUP_NAME
    else:
        payload[site]["cancel"] = MARKUP_NAME
    named = [one for one in js.push(payload)["faults"] if one["fault"] == "markup"]
    assert [one["field"] for one in named] == [site], named


# --- hostile payloads ------------------------------------------------------


HOSTILE_FIELDS: dict = {
    "banner missing": ("banner", None),
    "banner is a list": ("banner", []),
    "buttons is text": ("buttons", "words"),
    "button_names is a bag": ("button_names", {}),
    "connect_order is a bag": ("connect_order", {}),
    "connections is null": ("connections", None),
    "control_specs is a bag": ("control_specs", {}),
    "enabled is a list": ("enabled", []),
    "groups is a list": ("groups", []),
    "headings is null": ("headings", None),
    "layout is a list": ("layout", []),
    "minimum_size is a number": ("minimum_size", 7),
    "painted is a list": ("painted", []),
    "phantom_timeframes is a bag": ("phantom_timeframes", {}),
    "rows is text": ("rows", "rows"),
    "spacing is a list": ("spacing", []),
    "styles is a list": ("styles", []),
    "ta_rows is a bag": ("ta_rows", {}),
    "tabs is a bag": ("tabs", {}),
    "text_rows is a bag": ("text_rows", {}),
    "texts is text": ("texts", "words"),
    "tooltips is a list": ("tooltips", []),
    "values is a list": ("values", []),
    "visible is null": ("visible", None),
    "window_title is a number": ("window_title", 7),
    "wing is a number": ("wing", 7),
    "accepted is text": ("accepted", "yes"),
    "window_title is not a number": ("window_title", "nan"),
    "window_title is infinity": ("window_title", "inf"),
    "window_title is minus infinity": ("window_title", "-inf"),
    "window_title is a huge whole number": ("window_title", HUGE_WHOLE),
    "window_title is two hundred long": ("window_title", LONG_NAME),
    "window_title carries markup": ("window_title", MARKUP_NAME),
    "window_title carries a newline": ("window_title", NEWLINE_NAME),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_FIELDS))
def test_a_hostile_field_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """A payload the surface would never send must report, never raise."""
    name, value = HOSTILE_FIELDS[case]
    payload = state_payload("stock")
    payload[name] = value
    payload = as_json(payload)
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    assert isinstance(js.json(API + "kinds()"), dict), case
    assert isinstance(js.json(API + "notPlainData()"), list), case
    assert isinstance(js.json(API + "tabNames()"), list), case
    assert isinstance(js.json(API + "specNames()"), list), case
    assert isinstance(js.json(API + "rowNames()"), list), case
    assert isinstance(js.json(API + "connectOrder()"), list), case
    assert isinstance(js.json(API + "bannerPieces()"), list), case
    assert isinstance(js.json(API + "bannerStyle()"), dict), case
    assert isinstance(js.called("specFor", "username"), (dict, type(None))), case


HOSTILE_SETTINGS: dict = {
    "a value below the smallest the control holds": ("default_positions", -1),
    "a value above the largest the control holds": ("default_positions", HUGE_WHOLE),
    "a value the control has no place for": ("theme_combo", HUGE_WHOLE),
    "a number where text belongs": ("username", 7),
    "text where a number belongs": ("default_positions", "many"),
    "not a number": ("pos_distance", "nan"),
    "infinity": ("pos_distance", "inf"),
    "minus infinity": ("pos_distance", "-inf"),
    "a null value": ("username", None),
    "a two hundred character value": ("username", LONG_NAME),
    "a value carrying markup": ("username", MARKUP_NAME),
    "a value carrying a newline": ("username", NEWLINE_NAME),
    "a setting the dialog does not know": (UNKNOWN_NAME, 1),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_SETTINGS))
def test_a_hostile_setting_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """One unusable seeded value never stops the other seventy-four."""
    name, value = HOSTILE_SETTINGS[case]
    payload = state_payload("crypto")
    payload["values"][name] = value
    payload = as_json(payload)
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    assert len(js.json(API + "specNames()")) == len(payload["control_specs"]), case
    answered = js.called("valueOf", name)
    given = payload["values"][name]
    if isinstance(given, (int, float)) and not isinstance(given, bool):
        assert float(answered) == float(given), case
    else:
        assert answered == given, case


def test_a_setting_outside_its_own_range_is_reported(js: JsRuntime):
    payload = state_payload("crypto")
    payload["values"]["default_positions"] = -1
    named = [
        one for one in js.push(payload)["faults"] if one["fault"] == "out-of-range"
    ]
    assert [one["detail"] for one in named] == ["default_positions"], named


def test_the_range_check_stays_quiet_on_a_value_inside_its_range(js: JsRuntime):
    payload = state_payload("crypto")
    low, high = surface.spec_for("default_positions")["range"]
    payload["values"]["default_positions"] = high
    assert [
        one for one in js.push(payload)["faults"] if one["fault"] == "out-of-range"
    ] == []
    assert low < high


def test_a_setting_the_dialog_does_not_know_is_reported(js: JsRuntime):
    payload = state_payload("crypto")
    payload["visible"][UNKNOWN_NAME] = True
    named = [
        one for one in js.push(payload)["faults"] if one["fault"] == "unknown-name"
    ]
    assert [one["detail"] for one in named] == [UNKNOWN_NAME], named


def test_a_control_named_twice_is_reported(js: JsRuntime):
    payload = state_payload("crypto")
    payload["control_specs"].append(dict(payload["control_specs"][0]))
    named = [
        one for one in js.push(payload)["faults"] if one["fault"] == "duplicate-name"
    ]
    assert [one["field"] for one in named] == ["control_specs"], named


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """A module that raised on one hostile value would answer nothing at all."""
    js.push(7)
    assert js.json(API + "tabNames()") == []
    assert js.json(API + "specNames()") == []
    assert js.json(API + "connectOrder()") == []
    assert js.json(API + "isLoaded()") is False


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_dialog_wires_no_timer_thread_or_topic_at_all(js: JsRuntime, state: str):
    """This dialog reads settings and starts nothing of its own."""
    js.push(state_payload(state))
    assert js.json(API + "busTopics()") == {"subscribes": [], "emits": []}
    assert js.called("runners", "timers") == {"built": [], "started": []}
    assert js.called("runners", "threads") == {"built": [], "started": []}


def test_the_wiring_check_would_see_one_timer_the_surface_declared(js: JsRuntime):
    payload = state_payload("crypto")
    payload["timers"]["built"] = ["a timer nobody wanted"]
    js.push(payload)
    assert js.called("runners", "timers")["built"] == ["a timer nobody wanted"]


# --- the markup rule, measured by asked width ------------------------------

#: An empty tag pair a rich-text widget swallows and a plain one lays out.
MARKUP_PROBE = "<span></span>setting"
PLAIN_PROBE = "setting"


def laid_out(widget: Any) -> int:
    """The width one widget asks for to lay its caller text out."""
    return int(widget.minimumSizeHint().width())


def a_label(text: str) -> Any:
    from PySide6.QtWidgets import QLabel

    return QLabel(text)


def a_group(text: str) -> Any:
    from PySide6.QtWidgets import QGroupBox

    return QGroupBox(text)


def a_button(text: str) -> Any:
    from PySide6.QtWidgets import QPushButton

    return QPushButton(text)


def a_check(text: str) -> Any:
    from PySide6.QtWidgets import QCheckBox

    return QCheckBox(text)


def a_radio(text: str) -> Any:
    from PySide6.QtWidgets import QRadioButton

    return QRadioButton(text)


def a_list_item(text: str) -> Any:
    from PySide6.QtWidgets import QListWidget

    built = QListWidget()
    built.addItem(text)
    return built


def list_width(widget: Any) -> int:
    """The width one list row asks for to lay its own words out."""
    return int(widget.sizeHintForColumn(0))


def a_combo(text: str) -> Any:
    from PySide6.QtWidgets import QComboBox

    built = QComboBox()
    built.addItem(text)
    return built


def combo_width(widget: Any) -> int:
    """The width one dropdown asks for to lay its own item out."""
    return int(widget.sizeHint().width())


def a_line(text: str) -> Any:
    from PySide6.QtWidgets import QLineEdit

    return QLineEdit(text)


def line_width(widget: Any) -> int:
    """The width one text field asks for to lay its own words out."""
    return int(
        widget.fontMetrics().boundingRect(widget.text()).width()
        + widget.minimumSizeHint().width()
    )


#: Each widget this dialog draws, beside the call reading the width it asks for.
SCREEN_WIDGETS = {
    "QGroupBox": (a_group, laid_out),
    "QPushButton": (a_button, laid_out),
    "QCheckBox": (a_check, laid_out),
    "QRadioButton": (a_radio, laid_out),
    "QListWidgetItem": (a_list_item, list_width),
    "QComboBox": (a_combo, combo_width),
    "QLineEdit": (a_line, line_width),
}
RICH_TEXT_WIDGETS = {"QLabel": (a_label, laid_out)}
EVERY_WIDGET = dict(SCREEN_WIDGETS, **RICH_TEXT_WIDGETS)


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_no_plain_widget_this_dialog_uses_reads_its_caller_text_as_markup(
    qapp, kind: str
):
    """A widget laying MARKUP_PROBE out wider than PLAIN_PROBE never read its tags."""
    assert qapp is not None
    build_widget, asked = SCREEN_WIDGETS[kind]
    assert asked(build_widget(MARKUP_PROBE)) > asked(
        build_widget(PLAIN_PROBE)
    ), f"{kind} laid the markup out no wider than the plain words"


@pytest.mark.parametrize("kind", sorted(RICH_TEXT_WIDGETS))
def test_the_one_widget_this_dialog_uses_that_does_read_markup_is_named(
    qapp, kind: str
):
    """QLabel lays MARKUP_PROBE out exactly as wide as PLAIN_PROBE."""
    assert qapp is not None
    build_widget, asked = RICH_TEXT_WIDGETS[kind]
    assert asked(build_widget(MARKUP_PROBE)) == asked(build_widget(PLAIN_PROBE))


@pytest.mark.parametrize("kind", sorted(EVERY_WIDGET))
def test_the_markup_measurement_reads_a_longer_text_as_a_wider_layout(qapp, kind: str):
    """A width that never moved would read every widget as one that reads markup."""
    assert qapp is not None
    build_widget, asked = EVERY_WIDGET[kind]
    assert asked(build_widget(PLAIN_PROBE * 8)) > asked(build_widget(PLAIN_PROBE))


def as_characters(text: str) -> Any:
    """One label laying the same words out with its tags shown as characters."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    built = QLabel(text)
    built.setTextFormat(Qt.TextFormat.PlainText)
    return built


def test_the_shipped_banner_draws_its_line_into_the_widget_that_reads_markup(qapp):
    """The banner is a QLabel, so its tags are emphasis and not words."""
    assert qapp is not None
    marked = laid_out(a_label(surface.STOCK_BANNER_TEXT))
    literal = laid_out(as_characters(surface.STOCK_BANNER_TEXT))
    assert marked > 0 and literal > 0
    assert marked < literal, (marked, literal)


def test_the_banner_width_check_reads_two_widths_that_can_differ(qapp):
    """A label reading the tags and one showing them lay one line out apart."""
    assert qapp is not None
    plain = surface.STOCK_BANNER_LEAD + surface.STOCK_BANNER_TAIL
    assert laid_out(as_characters(plain)) < laid_out(
        as_characters(surface.STOCK_BANNER_TEXT)
    )


# --- the page ---------------------------------------------------------------


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
            "the page never defined the settings dialog module in "
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
    "borderTopColor",
    "borderTopWidth",
    "borderTopStyle",
    "fontWeight",
    "fontSize",
    "paddingTop",
    "borderTopLeftRadius",
    "whiteSpace",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.setAttribute('data-part', 'settings-dialog-page');"
    "document.body.appendChild(window.HOST);"
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
    "        title: el.title, hidden: el.hidden, value: el.value,"
    "        checked: el.checked === true,"
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


def draw_dialog(browser: Browser, payload: dict, tab: Any = None) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    browser.js(
        "acervatorSetTokens(JSON.parse(window.TOKENS));"
        "acervatorTokens.apply(document.documentElement);"
    )
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js("window.TAB = " + json.dumps(json.dumps(tab)) + ";")
    browser.js(
        SETTER
        + "(JSON.parse(window.PAYLOAD));"
        + API
        + "fill(window.HOST, null, JSON.parse(window.TAB));"
    )
    return json.loads(browser.js(READ_PARTS))


def with_part(parts: list, name: str) -> list:
    return [one for one in parts if one["path"].split("/")[-1] == name]


def named(parts: list, part: str, key: str) -> dict:
    found = [one for one in with_part(parts, part) if one["attrs"].get(key) is not None]
    return {one["attrs"][key]: one for one in found}


def test_the_dialog_fills_the_named_space_the_renderer_left(browser: Browser):
    """The renderer names one space and this window fills it."""
    parts = draw_dialog(browser, state_payload("crypto"))
    assert browser.parsed(API + "spacePart") == "settings-dialog-page"
    assert with_part(parts, "settings-dialog"), "the dialog drew nothing into the space"


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A child with no name is a child no check can read."""
    draw_dialog(browser, state_payload("stock"))
    every, all_named = browser.parsed(COUNT_ELEMENTS)
    assert every == all_named, f"{every - all_named} drawn children carry no data-part"
    assert all_named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    draw_dialog(browser, state_payload("crypto"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, all_named = browser.parsed(COUNT_ELEMENTS)
    assert every == all_named + 1


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_tab_the_surface_names_becomes_one_button_in_that_order(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_dialog(browser, payload)
    drawn = with_part(parts, "tab-button")
    assert [one["whole"] for one in drawn] == payload["tabs"], drawn
    pages = with_part(parts, "tab-page")
    assert [one["attrs"]["data-tab"] for one in pages] == payload["tabs"], pages


@pytest.mark.parametrize("state", STATE_NAMES)
def test_each_control_draws_the_value_the_surface_seeded_it_with(
    browser: Browser, state: str
):
    """One widget drew a value the surface never seeded."""
    payload = state_payload(state)
    parts = draw_dialog(browser, payload)
    by_name = named(parts, "control", "data-name")
    for spec in payload["control_specs"]:
        name = spec["name"]
        if spec["kind"] == "list":
            continue
        seeded = payload["values"][name]
        drawn = by_name[name]
        if spec["kind"] in ("check", "radio"):
            assert drawn["checked"] is seeded, name
            continue
        if isinstance(seeded, (int, float)):
            assert float(drawn["value"]) == float(seeded), name
            continue
        assert drawn["value"] == str(seeded), name


def test_the_seeded_value_check_would_see_one_control_left_blank(browser: Browser):
    payload = state_payload("stored")
    payload["values"]["username"] = ""
    parts = draw_dialog(browser, payload)
    drawn = named(parts, "control", "data-name")["username"]
    assert drawn["value"] == ""
    assert state_payload("stored")["values"]["username"] != ""


def test_each_labelled_row_draws_the_words_the_row_list_carries(browser: Browser):
    payload = state_payload("crypto")
    parts = draw_dialog(browser, payload)
    drawn = named(parts, "row-label", "data-name")
    for _tab, _group, words, name in payload["rows"]:
        assert drawn[name]["whole"] == words, name


def test_the_preview_row_draws_its_label_beside_the_preview_words(browser: Browser):
    """The Font Settings preview is one labelled row, on both sides alike."""
    payload = state_payload("crypto")
    parts = draw_dialog(browser, payload)
    words = named(parts, "row-label", "data-name")["font_preview"]["whole"]
    drawn = named(parts, "named-text", "data-name")["font_preview"]
    assert words == surface.TEXT_ROW_LABELS["font_preview"]
    assert drawn["whole"] == payload["texts"]["font_preview"]


def test_the_banner_draws_its_emphasis_as_an_element_and_not_as_tags(
    browser: Browser,
):
    payload = state_payload("stock")
    parts = draw_dialog(browser, payload, tab=payload["tabs"][1])
    lead = with_part(parts, "banner-lead")[0]
    tail = with_part(parts, "banner-tail")[0]
    assert lead["tag"] == "STRONG", lead
    assert lead["whole"] == payload["banner"]["lead"], lead
    assert tail["whole"] == payload["banner"]["tail"], tail
    assert lead["style"]["fontWeight"] != tail["style"]["fontWeight"], (lead, tail)
    assert "<" not in lead["html"], lead["html"]


def test_the_emphasis_check_would_see_a_line_drawn_without_it(browser: Browser):
    payload = state_payload("stock")
    payload["banner"]["marks"]["strong_weight"] = "normal"
    parts = draw_dialog(browser, payload, tab=payload["tabs"][1])
    lead = with_part(parts, "banner-lead")[0]
    tail = with_part(parts, "banner-tail")[0]
    assert lead["style"]["fontWeight"] == tail["style"]["fontWeight"], (lead, tail)


def test_the_banner_is_hidden_on_the_wing_that_does_not_draw_it(browser: Browser):
    parts = draw_dialog(browser, state_payload("crypto"))
    drawn = with_part(parts, "banner")[0]
    assert drawn["hidden"] is True
    assert drawn["attrs"]["data-shown"] == "false"


def test_the_banner_colours_match_a_probe_built_from_the_whole_rule(
    browser: Browser,
):
    """The applied colours are read against a probe built from the whole rule."""
    payload = state_payload("stock")
    parts = draw_dialog(browser, payload, tab=payload["tabs"][1])
    style = browser.parsed(API + "bannerStyle()")
    probe = browser.parsed(
        "window.probeAssign(" + json.dumps(style) + ", JSON.parse(window.STYLE_NAMES))"
    )
    drawn = with_part(parts, "banner")[0]["style"]
    for name in ("color", "backgroundColor", "borderTopColor", "borderTopWidth"):
        assert drawn[name] == probe[name], f"{name}: {drawn} against {probe}"


def test_the_banner_colour_comparison_would_see_one_repainted_edge(browser: Browser):
    payload = state_payload("stock")
    parts = draw_dialog(browser, payload, tab=payload["tabs"][1])
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"borderTopColor": OTHER_COLOUR, "borderTopStyle": "solid"})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    drawn = with_part(parts, "banner")[0]["style"]
    assert drawn["borderTopColor"] != probe["borderTopColor"]


def test_the_banner_edge_is_drawn_translucent_and_not_opaque(browser: Browser):
    """An eight-digit colour would have reached the browser fully opaque."""
    payload = state_payload("stock")
    parts = draw_dialog(browser, payload, tab=payload["tabs"][1])
    drawn = with_part(parts, "banner")[0]["style"]
    opaque = browser.parsed(
        "window.probeAssign("
        + json.dumps({"borderTopColor": surface.BANNER_TINT, "borderTopStyle": "solid"})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert drawn["borderTopColor"] != opaque["borderTopColor"], drawn
    assert drawn["color"] == opaque["borderTopColor"], drawn


def test_each_painted_text_row_matches_a_probe_built_from_its_whole_rule(
    browser: Browser,
):
    payload = state_payload("crypto")
    parts = draw_dialog(browser, payload)
    drawn = named(parts, "named-text", "data-name")
    painted = [one for one in drawn.values() if one["attrs"]["data-painted"] == "true"]
    assert painted, "no text row was painted at all"
    for one in painted:
        sheet = payload["styles"][one["attrs"]["data-name"]]
        style = browser.parsed(API + "paintedStyle(" + json.dumps(sheet) + ")")
        probe = browser.parsed(
            "window.probeAssign("
            + json.dumps(style)
            + ", JSON.parse(window.STYLE_NAMES))"
        )
        assert one["style"]["color"] == probe["color"], (one, probe)
        assert one["style"]["fontWeight"] == probe["fontWeight"], (one, probe)


def test_an_unpainted_text_row_takes_no_colour_at_all(browser: Browser):
    payload = state_payload("crypto")
    parts = draw_dialog(browser, payload)
    drawn = named(parts, "named-text", "data-name")
    unpainted = [
        one for one in drawn.values() if one["attrs"]["data-painted"] == "false"
    ]
    assert unpainted, "no text row was left unpainted"
    plain = browser.parsed("window.probeAssign({}, JSON.parse(window.STYLE_NAMES))")
    for one in unpainted:
        assert one["style"]["color"] == plain["color"], one


def test_the_unpainted_check_would_see_every_text_row_painted(browser: Browser):
    payload = state_payload("crypto")
    painted = surface.FEEDBACK_STYLE_FORMAT.format(color=OTHER_COLOUR)
    for name in list(payload["texts"]):
        payload["styles"][name] = painted
    parts = draw_dialog(browser, payload)
    drawn = named(parts, "named-text", "data-name")
    assert [
        one for one in drawn.values() if one["attrs"]["data-painted"] == "false"
    ] == []


def test_every_indicator_row_draws_its_label_position_and_figure(browser: Browser):
    payload = state_payload("crypto")
    parts = draw_dialog(browser, payload, tab=payload["tabs"][4])
    drawn = named(parts, "ta-row", "data-name")
    assert len(drawn) == len(payload["ta_rows"])
    for words, position, printed in payload["ta_rows"]:
        row = drawn[words]
        assert row["attrs"]["data-index"] == str(position), words
        assert printed in row["whole"], words


def test_every_timeframe_draws_the_tick_the_surface_carries(browser: Browser):
    payload = state_payload("crypto")
    parts = draw_dialog(browser, payload, tab=payload["tabs"][5])
    drawn = named(parts, "tf-box", "data-name")
    assert len(drawn) == len(payload["phantom_timeframes"])
    for name, ticked in payload["phantom_timeframes"]:
        assert drawn[name]["checked"] is ticked, name


def test_the_timeframe_tick_check_would_see_every_box_ticked(browser: Browser):
    payload = state_payload("crypto")
    payload["phantom_timeframes"] = [
        [name, True] for name, _ticked in payload["phantom_timeframes"]
    ]
    parts = draw_dialog(browser, payload, tab=payload["tabs"][5])
    drawn = named(parts, "tf-box", "data-name")
    assert [one for one in drawn.values() if one["checked"] is False] == []


def test_the_stock_wing_greys_the_buttons_the_surface_names(browser: Browser):
    payload = state_payload("stock")
    parts = draw_dialog(browser, payload, tab=payload["tabs"][1])
    drawn = named(parts, "button", "data-name")
    greyed = sorted(
        name for name, one in drawn.items() if one["attrs"]["data-enabled"] == "false"
    )
    assert greyed == sorted(
        name for name in drawn if payload["enabled"].get(name) is False
    ), greyed
    assert "test_btn" in greyed and "add_btn" in greyed, greyed


def test_the_greyed_button_check_would_see_every_button_live(browser: Browser):
    payload = state_payload("crypto")
    parts = draw_dialog(browser, payload, tab=payload["tabs"][1])
    drawn = named(parts, "button", "data-name")
    assert [
        one for one in drawn.values() if one["attrs"]["data-enabled"] == "false"
    ] == []


def test_a_two_hundred_character_value_stretches_its_row_rather_than_clipping(
    browser: Browser,
):
    payload = state_payload("crypto")
    payload["values"]["username"] = LONG_NAME
    wide = draw_dialog(browser, payload)
    narrow = draw_dialog(browser, state_payload("crypto"))
    long_row = named(wide, "form-row", "data-name")["username"]
    short_row = named(narrow, "form-row", "data-name")["username"]
    assert long_row["width"] >= short_row["width"], (long_row, short_row)


def test_a_value_carrying_markup_is_drawn_as_characters(browser: Browser):
    payload = state_payload("crypto")
    payload["texts"]["vol_label"] = MARKUP_NAME
    parts = draw_dialog(browser, payload, tab=payload["tabs"][8])
    drawn = named(parts, "named-text", "data-name")["vol_label"]
    assert drawn["whole"] == MARKUP_NAME, drawn
    assert "<img" not in drawn["html"], drawn["html"]


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    draw_dialog(browser, state_payload("crypto"))
    browser.js(
        "window.HOST.firstChild.insertAdjacentHTML('beforeend',"
        ' \'<span data-part="named-text"><img src="x"></span>\');'
    )
    grown = json.loads(browser.js(READ_PARTS))
    assert [one for one in with_part(grown, "named-text") if "<img" in one["html"]]


def test_a_setting_the_dialog_does_not_know_draws_nothing_and_stops_nothing(
    browser: Browser,
):
    payload = state_payload("crypto")
    payload["values"][UNKNOWN_NAME] = 1
    parts = draw_dialog(browser, payload)
    assert with_part(parts, "settings-dialog"), "the dialog drew nothing"
    assert named(parts, "control", "data-name").get(UNKNOWN_NAME) is None
    assert len(named(parts, "control", "data-name")) > 0


def test_a_setting_outside_its_range_still_draws_the_value_it_was_given(
    browser: Browser,
):
    """An unusable figure is drawn as it is, never turned into a plausible one."""
    payload = state_payload("crypto")
    payload["values"]["default_positions"] = -1
    parts = draw_dialog(browser, payload, tab=payload["tabs"][2])
    drawn = named(parts, "control", "data-name")["default_positions"]
    assert drawn["value"] == "-1", drawn
    assert drawn["attrs"]["data-low"] == str(
        surface.spec_for("default_positions")["range"][0]
    )


def test_the_asked_spacing_reaches_the_document_rather_than_a_typed_number(
    browser: Browser,
):
    """The surface owns every spacing and the module writes none."""
    payload = state_payload("crypto")
    parts = draw_dialog(browser, payload, tab=payload["tabs"][9])
    groups = named(parts, "group", "data-key")
    for title, spacing in payload["spacing"]["group_form"].items():
        if title in groups:
            assert groups[title]["attrs"]["data-spacing"] == str(spacing), title
            assert groups[title]["attrs"]["data-margins"] == ".".join(
                str(one) for one in payload["spacing"]["group_margins"][title]
            ), title


def test_the_scrolling_tabs_are_the_ones_the_surface_names(browser: Browser):
    payload = state_payload("crypto")
    parts = draw_dialog(browser, payload)
    scrolling = sorted(
        one["attrs"]["data-tab"]
        for one in parts
        if one["attrs"].get("data-scrolls") == "true"
    )
    assert scrolling == sorted(payload["scrolling_tabs"]), scrolling


def test_the_scrolling_check_would_see_a_tab_that_scrolls_nothing(browser: Browser):
    payload = state_payload("crypto")
    payload["scrolling_tabs"] = []
    parts = draw_dialog(browser, payload)
    scrolling = [one for one in parts if one["attrs"].get("data-scrolls") == "true"]
    assert scrolling != [], "no tab drew a scrolling block at all"


def test_the_tab_that_hides_its_sideways_bar_is_the_one_the_surface_names(
    browser: Browser,
):
    payload = state_payload("crypto")
    parts = draw_dialog(browser, payload)
    barless = sorted(
        one["attrs"]["data-tab"]
        for one in parts
        if one["attrs"].get("data-horizontal-bar") == "false"
    )
    assert barless == sorted(payload["spacing"]["no_horizontal_bar"]), barless


def test_this_file_holds_no_carriage_return():
    """A file grew a Windows line ending the build machine reads as text."""
    for path in (MODULE_PATH, Path(__file__)):
        assert path.read_bytes().count(b"\r") == 0, path.name


def test_the_carriage_return_counter_can_report():
    """The carriage-return counter reports nothing whatever a file holds."""
    assert b"a\r\nb".count(b"\r") == 1
    assert b"a\nb".count(b"\r") == 0


def test_the_page_loads_this_module_after_the_pieces_it_reads():
    """A module loaded before header_strip.js would draw no style at all."""
    lines = INDEX_HTML.read_text(encoding="utf-8").splitlines()
    names = [line for line in lines if MODULE_PATH.name in line]
    assert len(names) == 1, names
    order = [
        index
        for index, line in enumerate(lines)
        if any(
            one in line
            for one in (MODULE_PATH.name, "header_strip.js", "table_cells.js")
        )
    ]
    assert len(order) == 3
    assert lines[order[-1]].find(MODULE_PATH.name) >= 0
