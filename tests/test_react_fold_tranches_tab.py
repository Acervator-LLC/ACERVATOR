"""The React Fold Tranches tab, against fold_tranches_tab_surface.py."""

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
from src.gui.main_tabs import fold_chrome_surface as chrome
from src.gui.main_tabs import fold_tranches_tab_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "fold_tranches_tab.js"
CHROME_PATH = WEB / "fold_chrome.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorFoldTranchesTab."
CHROME_API = "acervatorFoldChrome."
SETTER = "acervatorSetFoldTranchesTab"
CHROME_SETTER = "acervatorSetFoldChrome"

#: The merged pieces the page loads beside this module, needed at call time.
SHARED_MODULES = (WEB / "table_cells.js", WEB / "header_strip.js", CHROME_PATH)

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

NOW = 1_000_000.0
UNKNOWN_BOT = "no-such-bot"


def tranche(
    usd: float, units: float, ref: float, made: float, manual: bool = False
) -> dict:
    """One stored fold tranche, in the keys the tab surface reads."""
    found = {
        surface.USD_KEY: usd,
        surface.UNITS_KEY: units,
        surface.REF_KEY: ref,
        surface.INITIAL_BUY_PRICE_KEY: ref,
        surface.CREATED_TS_KEY: made,
    }
    if manual:
        found[surface.OPERATOR_INITIATED_KEY] = True
    return found


THREE_TRANCHES = [
    tranche(10.0, 0.5, 20.0, NOW - 100.0),
    tranche(30.0, 1.5, 25.0, NOW - 500_000.0, manual=True),
    tranche(20.0, 1.0, 22.0, NOW - 90_000.0),
]

EXTRACTOR_ROWS = [
    {
        surface.EXTRACTOR_TRANCHE_ID_KEY: "tranche-a",
        surface.EXTRACTOR_CHILD_ID_KEY: "ext-a",
        surface.EXTRACTOR_OPENED_KEY: NOW - 200_000.0,
        surface.EXTRACTOR_UNITS_KEY: 0.25,
        surface.EXTRACTOR_MARK_KEY: 5.0,
        surface.EXTRACTOR_STATE_KEY: "open",
        surface.EXTRACTOR_PAIR_KEY: "PEPE-BTC",
        surface.EXTRACTOR_ARBITER_KEY: surface.ARBITER_PARENT,
    },
    {
        surface.EXTRACTOR_TRANCHE_ID_KEY: "tranche-b",
        surface.EXTRACTOR_CHILD_ID_KEY: UNKNOWN_BOT,
        surface.EXTRACTOR_OPENED_KEY: NOW - 3_000.0,
        surface.EXTRACTOR_UNITS_KEY: 0.75,
        surface.EXTRACTOR_MARK_KEY: None,
        surface.EXTRACTOR_STATE_KEY: "open",
        surface.EXTRACTOR_PAIR_KEY: "WIF-BTC",
        surface.EXTRACTOR_ARBITER_KEY: surface.ARBITER_SIBLING,
    },
]


def bot(tranches: Any = None, rows: Any = None, **rest: Any) -> dict:
    """One bot the tab reads, from the values a request carries."""
    found = {
        "symbol": "BTC-USD",
        "bot_id": "bot-a",
        "tranches": list(tranches or []),
        "extractor_rows": rows,
        "created": 8,
        "closed": 3,
        "discarded": 1,
        "malformed": 1,
        "wire_discarded": 2.0,
        "counters_reset_ts": NOW - 900_000.0,
        "cap_budget": 100.0,
        "cap_spent": 25.0,
        "holdings": 2.0,
        "price": 21.0,
        "parked": 12.5,
    }
    found.update(rest)
    return found


FULL = {"reset": True, "now": NOW, "otd": {"pct": 1.5, "factor": 0.985}}

STATES: dict = {
    "fresh": [{"reset": True, "now": NOW}],
    "empty": [dict(FULL, bot=bot())],
    "fold": [dict(FULL, bot=bot(THREE_TRANCHES))],
    "mixed": [dict(FULL, bot=bot(THREE_TRANCHES, EXTRACTOR_ROWS))],
    "sorted": [
        dict(FULL, bot=bot(THREE_TRANCHES, EXTRACTOR_ROWS)),
        {"order": surface.SORT_OLDEST_FIRST},
    ],
    "filtered": [
        dict(FULL, bot=bot(THREE_TRANCHES, EXTRACTOR_ROWS)),
        {"filter": "extractor"},
    ],
    "cleared": [
        dict(FULL, bot=bot(THREE_TRANCHES)),
        {"clear": "fold", "clear_answer": surface.YES_BUTTON_VALUE},
    ],
    "declined": [
        dict(FULL, bot=bot(THREE_TRANCHES)),
        {"clear": "fold", "clear_answer": surface.CANCEL_BUTTON_VALUE},
    ],
    "fired": [
        dict(FULL, bot=bot(THREE_TRANCHES), manager={"async_loop": "a loop"}),
        {"fire_index": 0, "fire_number": 1, "fire_answer": surface.YES_BUTTON_VALUE},
    ],
    "arbiter": [
        dict(FULL, bot=bot(THREE_TRANCHES, EXTRACTOR_ROWS)),
        {"arbiter": {"tranche_id": "tranche-a", "child_bot_id": UNKNOWN_BOT}},
    ],
}
STATE_NAMES = tuple(STATES)


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


def chrome_payload() -> dict:
    chrome.view_model({"reset": True})
    return as_json(chrome.view_model({"controls": True}))


def token_payload() -> dict:
    return as_json(dss.view_model({}))


class JsRuntime(JsEngine):
    """A QJSEngine holding the tab, the chrome and the merged pieces."""

    module_path = MODULE_PATH
    setter = SETTER

    def __init__(self, engine: Any, source: str) -> None:
        super().__init__(engine, source)
        for path in SHARED_MODULES:
            loaded = engine.evaluate(path.read_text(encoding="utf-8"), path.name)
            assert not loaded.isError(), path.name + " -> " + loaded.toString()
        self.bind_json("CHROME", chrome_payload())
        self.run(CHROME_SETTER + "(JSON.parse(CHROME));")

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
    payload = state_payload("mixed")
    payload["only_on_the_surface"] = []
    js.push(payload)
    assert sorted(set(payload) - set(declared_fields(js))) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    payload = state_payload("mixed")
    assert payload.pop("border_px") is not None
    js.push(payload)
    assert sorted(set(declared_fields(js)) - set(payload)) == ["border_px"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = state_payload("mixed")
    payload["border_px"] += 1
    js.push(payload)
    original = state_payload("mixed")
    differing = sorted(
        name for name in original if js.called("field", name) != original[name]
    )
    assert differing == ["border_px"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    table = payload["table"]
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["rows"] == table["row_count"]
    assert report["held"]["rows"] == len(table["rows"])
    assert report["declared"]["columns"] == table["column_count"]
    assert report["held"]["columns"] == len(table["columns"])
    assert report["declared"]["fold"] == table["fold_row_count"]
    assert report["declared"]["extractor"] == table["extractor_row_count"]
    assert report["held"]["actions"] == len(payload["actions"])


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("mixed")
    declared = len(payload)
    del payload["clear_reason"]
    report = js.push(payload)
    assert report["declared"]["fields"] == declared
    assert report["held"]["fields"] == declared - 1
    assert [one["field"] for one in report["faults"]] == ["clear_reason"]


def test_a_dropped_row_shortens_the_held_row_count(js: JsRuntime):
    payload = state_payload("mixed")
    payload["table"]["rows"].pop()
    report = js.push(payload)
    assert report["declared"]["rows"] == len(state_payload("mixed")["table"]["rows"])
    assert report["held"]["rows"] == report["declared"]["rows"] - 1


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
    payload = state_payload("mixed")
    payload["border_px"] = str(payload["border_px"])
    js.push(payload)
    expected = python_kinds(state_payload("mixed"))
    actual = js.json(API + "kinds()")
    assert sorted(p for p, k in expected.items() if actual.get(p) != k) == ["border_px"]


def test_the_type_walk_names_a_scalar_where_a_row_belongs(js: JsRuntime):
    """A scalar where the payload lists a row must not read as that row."""
    payload = state_payload("mixed")
    payload["table"]["rows"][1] = 7
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("table.rows.1") == "number"
    assert "table.rows.1.0" not in actual


def test_the_type_walk_names_a_null_where_a_cell_belongs(js: JsRuntime):
    payload = state_payload("mixed")
    payload["table"]["rows"][1][0] = None
    js.push(payload)
    assert js.json(API + "kinds()").get("table.rows.1.0") == "null"


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
    raw["table"]["rows"] = [[surface.FoldTranchesTabModel()]]
    assert not_plain_data(raw) == ["table.rows.0.0"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    js.push(state_payload("fold"))
    js.run(
        SETTER + "(Object.assign(" + API + "payload(), { border_px: function () {} }));"
    )
    assert js.json(API + "notPlainData()") == [
        {"path": "border_px", "kind": "function"}
    ]


def shown_values() -> set:
    """Every string the tab paints or shows as a tooltip, from every state."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        for row in payload["health_rows"]:
            found |= {one for one in row if isinstance(one, str)}
        for row in payload["table"]["rows"]:
            found |= {one for one in row if isinstance(one, str)}
        for one in payload["buttons"]:
            found |= {item for item in one if isinstance(item, str)}
        for box in payload["boxes"]:
            found |= {
                box[key] for key in ("title", "text") if isinstance(box.get(key), str)
            }
        found |= {payload["empty_label"]["text"]}
        found |= set(payload["table"]["columns"])
        found |= set(payload["table"]["column_tooltips"])
        found |= set(payload["health_labels"])
        found |= set(payload["health_tooltips"])
        found |= set(payload["button_tooltips"])
        found |= set(payload["colors"].values())
        found |= set(payload["texts"].values())
        found |= set(payload["titles"].values())
        found |= set(payload["formats"].values())
        found |= set(payload["settled"])
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

#: NAMED_WORDS lists every published string the module may write.
NAMED_WORDS = sorted(
    set(BARE)
    | set(BARE["table"])
    | set(BARE["actions"])
    | set(BARE["button_values"])
    | set(BARE["container"])
    | set(BARE["health_group"])
    | set(BARE["empty_label"])
    | set(BARE["arbiter_button"])
    | set(BARE["fire_button"])
    | set(BARE["despawn"])
    | set(BARE["sources"])
    | set(BARE["boxes"][0] if BARE["boxes"] else {})
    | set(chrome_payload()["labels"])
    | {surface.METHOD, "icon", "title", "text", "buttons_value", "default_button_value"}
)


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a value the surface owns."""
    assert not MODULE_LITERALS["numbers"], (
        "fold_tranches_tab.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"fold_tranches_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_shows():
    written = sorted(set(MODULE_LITERALS["strings"]) & SHOWN_VALUES)
    assert not written, f"fold_tranches_tab.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"fold_tranches_tab.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert set(written) <= set(NAMED_WORDS), (
        "the module names published strings the list does not allow: "
        f"{sorted(set(written) - set(NAMED_WORDS))}"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_tab_shows():
    overlap = sorted(set(NAMED_WORDS) & SHOWN_VALUES)
    assert not overlap, f"these named words are values the tab shows: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "fold_tranches_tab.js holds a slash outside a comment, which the literal "
        f"scan cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES: dict = {
    "colour": 'var written = "' + OTHER_COLOUR + '";',
    "fold_fill": 'var written = "' + surface.FOLD_TRANCHE_BG_HEX + '";',
    "extractor_fill": 'var written = "' + surface.EXTRACTOR_TRANCHE_BG_HEX + '";',
    "status_ok": 'var written = "' + surface.STATUS_OK_HEX + '";',
    "column": 'var written = "' + surface.COLUMNS[0] + '";',
    "health_label": 'var written = "' + surface.OPEN_COUNT_ROW + '";',
    "empty_note": 'var written = "' + surface.EMPTY_TEXT + '";',
    "em_dash": 'var written = "' + surface.EM_DASH + '";',
    "extractor_word": 'var written = "' + surface.EXTRACTOR_ROW_NUMBER + '";',
    "row_height": "var written = " + str(surface.TRANCHE_ROW_HEIGHT_PX) + ";",
    "yes_value": "var written = " + str(surface.YES_BUTTON_VALUE) + ";",
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
    found += list(payload["border_by_background"])
    found += list(payload["border_by_background"].values())
    for row in payload["table"]["row_colors"]:
        found += list(row)
    found += [one for one in payload["table"]["row_backgrounds"]]
    found += [one for one in payload["table"]["row_borders"] if one is not None]
    found += [one for one in payload["health_colors"] if one is not None]
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
    ] == []


COLOUR_NAMES = (
    "fold_bg",
    "fold_fg",
    "extractor_bg",
    "extractor_fg",
    "fold_border",
    "extractor_border",
    "source_manual",
    "over_allotment",
    "ratio_red",
    "ratio_amber",
    "ratio_green",
    "status_ok",
    "status_wait",
    "danger_surface",
    "danger_border",
    "danger_text",
    "disabled_text",
    "disabled_border",
    "fire_hover",
    "fire_off_surface",
    "fire_off_text",
)


@pytest.mark.parametrize("name", COLOUR_NAMES)
def test_the_alpha_sweep_names_one_colour_written_with_eight_digits(
    js: JsRuntime, name: str
):
    payload = state_payload("mixed")
    payload["colors"][name] = SWAPPED_ALPHA
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_one_painted_cell(js: JsRuntime):
    payload = state_payload("mixed")
    payload["table"]["row_colors"][0][0] = SWAPPED_ALPHA
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_a_button_style_sheet(js: JsRuntime):
    payload = state_payload("mixed")
    payload["button_style"] = payload["button_style"].replace(
        surface.DANGER_SURFACE_HEX, SWAPPED_ALPHA
    )
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_one_health_row_style(js: JsRuntime):
    payload = state_payload("mixed")
    payload["health_colors"][1] = surface.PARKED_USD_STYLE_FORMAT.format(
        colour=SWAPPED_ALPHA
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


def test_the_bag_order_check_names_a_digit_key_put_into_a_published_bag(js: JsRuntime):
    payload = state_payload("mixed")
    payload["titles"]["0"] = payload["titles"]["clear_fold"]
    report = js.push(payload)
    moved = [one for one in report["faults"] if one["fault"] == "reordered-key"]
    assert [one["detail"] for one in moved] == ["0"]


def test_the_wired_names_are_read_from_a_list_and_not_from_the_action_bag(
    js: JsRuntime,
):
    """Pairing three Clear buttons off a bag would rest on that bag's key order."""
    payload = state_payload("mixed")
    js.push(payload)
    assert js.json(API + "actionNames()") == list(payload["actions"])
    assert js.json(API + "clearActionNames()") == list(payload["actions"])[:3]


def test_the_action_check_names_a_wired_name_the_payload_never_declared(js: JsRuntime):
    payload = state_payload("mixed")
    payload["actions"]["no_such_signal"] = "nothing"
    report = js.push(payload)
    unknown = [one for one in report["faults"] if one["fault"] == "unknown-action"]
    assert [one["detail"] for one in unknown] == ["no_such_signal"]


def test_the_action_check_names_a_wired_name_the_payload_dropped(js: JsRuntime):
    payload = state_payload("mixed")
    del payload["actions"]["fire_button.clicked"]
    report = js.push(payload)
    missing = [
        one
        for one in report["faults"]
        if one["fault"] == "missing" and one["field"] == "actions"
    ]
    assert [one["detail"] for one in missing] == ["fire_button.clicked"]


@pytest.mark.parametrize("state", ["fold", "mixed", "sorted"])
def test_each_row_is_named_by_what_identifies_it_and_not_by_where_it_sits(
    js: JsRuntime, state: str
):
    """A tranche list is the case where position alone is not an identity."""
    payload = state_payload(state)
    js.push(payload)
    named = js.json(API + "rowIdentities()")
    table = payload["table"]
    assert len(named) == table["row_count"]
    folds = [one for one in named if one["extractor"] is False]
    assert [one["name"] for one in folds] == [
        str(number) for number in payload["fire_button"]["numbers"]
    ]
    extractors = [one for one in named if one["extractor"] is True]
    assert [one["name"] for one in extractors] == [
        one[0] for one in payload["arbiter_button"]["identities"]
    ]


def test_the_row_identity_travels_with_the_row_when_the_order_changes(js: JsRuntime):
    """Sorting renumbers no tranche, so each queue number keeps its own row."""
    queued = state_payload("mixed")
    js.push(queued)
    by_queue = js.json(API + "rowIdentities()")
    ordered = state_payload("sorted")
    js.push(ordered)
    by_age = js.json(API + "rowIdentities()")
    assert sorted(one["name"] for one in by_queue) == sorted(
        one["name"] for one in by_age
    )
    assert [one["name"] for one in by_queue] != [one["name"] for one in by_age]


def test_the_identity_check_names_a_row_whose_queue_number_moved(js: JsRuntime):
    payload = state_payload("mixed")
    payload["fire_button"]["numbers"][0] = 99
    report = js.push(payload)
    moved = [one for one in report["faults"] if one["fault"] == "disagrees"]
    assert [one["where"] for one in moved] == ["row:0"]


def test_each_extractor_row_names_itself_rather_than_being_counted_into_place(
    js: JsRuntime,
):
    payload = state_payload("mixed")
    js.push(payload)
    assert js.json(API + "extractorRowIndexes()") == [
        3,
        4,
    ], "the extractor rows are the two after the three fold rows"
    assert js.called("isExtractorRow", 0) is False
    assert js.called("isExtractorRow", 3) is True


def test_the_extractor_check_names_a_row_count_that_disagrees(js: JsRuntime):
    payload = state_payload("mixed")
    payload["table"]["extractor_row_count"] += 1
    report = js.push(payload)
    assert [
        one["field"] for one in report["faults"] if one["fault"] == "disagrees"
    ] == ["extractor_row_count"]


def test_the_two_despawn_rows_are_the_two_the_panel_chrome_names(js: JsRuntime):
    """Fourteen labels share thirteen tooltips, so the pair is found by name."""
    payload = state_payload("mixed")
    js.push(payload)
    assert len(payload["health_labels"]) == len(payload["health_tooltips"]) + 1
    named = chrome_payload()["labels"]
    assert js.json(API + "despawnLabelPair()") == [
        named["timer_row"],
        named["preview_row"],
    ]
    assert js.json(API + "faults()") == []


@pytest.mark.parametrize(
    "at", range(len(surface.view_model({"reset": True})["health_labels"]))
)
def test_each_health_label_carries_the_tooltip_the_shipped_tab_gives_it(
    js: JsRuntime, at: int
):
    payload = state_payload("mixed")
    js.push(payload)
    labels = payload["health_labels"]
    tips = payload["health_tooltips"]
    shared = tips.index(payload["despawn"]["tooltip"])
    wanted = tips[at] if at <= shared else tips[shared if at == shared + 1 else at - 1]
    assert js.called("healthTooltip", labels[at]) == wanted


def test_the_tooltip_pairing_names_a_tooltip_list_that_lost_an_entry(js: JsRuntime):
    payload = state_payload("mixed")
    payload["health_tooltips"].pop()
    report = js.push(payload)
    assert [
        one["fault"] for one in report["faults"] if one["fault"] == "unpaired-tooltip"
    ] == ["unpaired-tooltip"]


def test_the_tooltip_pairing_reports_a_page_that_never_loaded_the_panel_chrome(
    js: JsRuntime,
):
    js.run("window." + CHROME_API.rstrip(".") + " = undefined;")
    report = js.push(state_payload("mixed"))
    assert [
        one["fault"] for one in report["faults"] if one["fault"] == "no-chrome"
    ] == ["no-chrome"]


@pytest.mark.parametrize("state", ["fold", "mixed", "cleared"])
def test_each_health_row_is_found_by_its_own_label(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for label, value in payload["health_rows"]:
        assert js.called("healthValue", label) == value


CLEAR_KINDS = ("clear_button.clicked", "wire_button.clicked", "counters_button.clicked")


@pytest.mark.parametrize("at", range(len(CLEAR_KINDS)))
def test_each_clear_button_runs_its_own_handler_with_its_own_name(
    js: JsRuntime, at: int
):
    """Three buttons share one style, so only the argument tells them apart."""
    payload = state_payload("fold")
    js.push(payload)
    js.bind_json("NAME", CLEAR_KINDS[at])
    pressed = js.json(API + "press(JSON.parse(NAME), JSON.parse(NAME))")
    assert pressed["name"] == CLEAR_KINDS[at]
    assert pressed["argument"] == CLEAR_KINDS[at]
    assert pressed["action"] == payload["actions"][CLEAR_KINDS[at]]


def test_the_press_check_would_see_a_button_that_answered_with_another_name(
    js: JsRuntime,
):
    payload = state_payload("fold")
    js.push(payload)
    js.run(API + "press('" + CLEAR_KINDS[0] + "', '" + CLEAR_KINDS[2] + "');")
    assert js.json(API + "pressed()")["argument"] != CLEAR_KINDS[0]


def test_the_fire_button_answers_with_the_queue_number_of_its_own_row(js: JsRuntime):
    payload = state_payload("mixed")
    js.push(payload)
    for at in js.json(API + "foldRowIndexes()"):
        assert js.called("fireNumberFor", at) == payload["fire_button"]["numbers"][at]


def test_the_arbiter_button_answers_with_the_identity_of_its_own_row(js: JsRuntime):
    payload = state_payload("mixed")
    js.push(payload)
    for offset, at in enumerate(js.json(API + "extractorRowIndexes()")):
        assert (
            js.called("identityFor", at)
            == payload["arbiter_button"]["identities"][offset]
        )


def test_no_fold_row_answers_with_an_extractor_identity(js: JsRuntime):
    js.push(state_payload("mixed"))
    for at in js.json(API + "foldRowIndexes()"):
        assert js.called("identityFor", at) is None
    for at in js.json(API + "extractorRowIndexes()"):
        assert js.called("fireNumberFor", at) is None


@pytest.mark.parametrize("name", ("yes", "no", "cancel", "ok"))
def test_each_message_box_answer_carries_the_value_the_surface_publishes(
    js: JsRuntime, name: str
):
    payload = state_payload("cleared")
    js.push(payload)
    assert js.called("answerValue", name) == payload["button_values"][name]


@pytest.mark.parametrize("state", ["cleared", "declined", "fired", "arbiter"])
def test_each_message_box_offers_only_the_answers_its_own_value_names(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    offered = js.json(API + "boxes()")
    assert offered, f"{state} raised no box"
    for at, box in enumerate(payload["boxes"]):
        names = js.json(API + "boxAnswers(" + API + "boxes()[" + str(at) + "])")
        wanted = [
            name
            for name in ("yes", "no", "cancel", "ok")
            if box["buttons_value"] & payload["button_values"][name]
            == payload["button_values"][name]
        ]
        assert names == wanted, f"{state} box {at} offered {names} against {wanted}"


def test_the_answer_check_names_a_box_offering_nothing_at_all(js: JsRuntime):
    payload = state_payload("cleared")
    payload["boxes"][0]["buttons_value"] = 0
    report = js.push(payload)
    assert [
        one["where"]
        for one in report["faults"]
        if one["fault"] == "short-list" and one["field"] == "boxes"
    ] == ["box:0"]


HOSTILE_FIELDS: dict = {
    "health_rows missing": ("health_rows", None),
    "health_rows is a bag": ("health_rows", {}),
    "health_colors is text": ("health_colors", "#123a63"),
    "health_labels is null": ("health_labels", None),
    "health_tooltips is a bag": ("health_tooltips", {}),
    "buttons is a bag": ("buttons", {}),
    "buttons hold a fourth": ("buttons", [["a", True]] * 4),
    "button_tooltips is short": ("button_tooltips", []),
    "button_style is a number": ("button_style", 7),
    "table is a list": ("table", []),
    "boxes is text": ("boxes", "a box"),
    "outcome is a number": ("outcome", 7),
    "border_px is text": ("border_px", "2"),
    "border_px is nan": ("border_px", "nan"),
    "border_px is inf": ("border_px", "inf"),
    "border_px is minus inf": ("border_px", "-inf"),
    "border_px is huge": ("border_px", 10**24),
    "no_cell_color is text": ("no_cell_color", "#123a63"),
    "extractor_row_number is null": ("extractor_row_number", None),
    "actions is a list": ("actions", []),
    "colors is null": ("colors", None),
    "fire_button is a list": ("fire_button", []),
    "arbiter_button is text": ("arbiter_button", "an arbiter"),
    "emitted is a bag": ("emitted", {}),
    "settled is text": ("settled", "a line"),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_FIELDS))
def test_a_hostile_field_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """A payload the surface would never send must report, never raise."""
    name, value = HOSTILE_FIELDS[case]
    payload = state_payload("mixed")
    payload[name] = value
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    assert isinstance(js.json(API + "kinds()"), dict), case
    assert isinstance(js.json(API + "rowIdentities()"), list), case
    assert isinstance(js.json(API + "healthTooltipMap()"), dict), case
    assert isinstance(js.json(API + "boxes()"), list), case


HOSTILE_ROWS: dict = {
    "a short row": ["1", "2m"],
    "a null cell": None,
    "a number where text belongs": [7] * 11,
    "text where a number belongs": ["one"] * 11,
    "a long name": [LONG_NAME] * 11,
    "markup": [MARKUP_NAME] * 11,
    "a newline": [NEWLINE_NAME] * 11,
    "a scalar row": 7,
    "a bag row": {},
}


@pytest.mark.parametrize("case", sorted(HOSTILE_ROWS))
def test_a_hostile_row_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    payload = state_payload("mixed")
    payload["table"]["rows"][0] = HOSTILE_ROWS[case]
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert isinstance(js.json(API + "rows()"), list), case
    assert isinstance(js.json(API + "rowIdentities()"), list), case
    assert isinstance(js.json(API + "kinds()"), dict), case


def test_a_bot_holding_no_tranche_at_all_draws_the_empty_note_and_no_table(
    js: JsRuntime,
):
    """Zero tranches is the state the operator sees before the first SCRUM."""
    payload = state_payload("empty")
    js.push(payload)
    assert payload["table"]["shown"] is False
    assert payload["empty_label"]["shown"] is True
    assert payload["table"]["rows"] == []
    assert js.json(API + "rowIdentities()") == []
    assert js.json(API + "faults()") == []


def test_a_tranche_naming_a_bot_that_is_not_in_the_fleet_is_refused_and_reported(
    js: JsRuntime,
):
    """The Arbiter writes nothing when the registry has no such child."""
    payload = state_payload("arbiter")
    js.push(payload)
    assert payload["outcome"] == surface.OUTCOME_NO_REGISTRY
    assert payload["arbiter_button"]["written"] == []
    assert payload["boxes"][-1]["title"] == payload["titles"]["arbiter_refused"]
    assert UNKNOWN_BOT not in payload["boxes"][-1]["text"]
    assert js.json(API + "faults()") == []


def test_a_duplicate_queue_number_is_reported_rather_than_drawn_twice(js: JsRuntime):
    payload = state_payload("fold")
    payload["fire_button"]["numbers"][1] = payload["fire_button"]["numbers"][0]
    report = js.push(payload)
    assert [
        one["where"] for one in report["faults"] if one["fault"] == "disagrees"
    ] == ["row:1"]


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """A module that raised on one hostile value would answer nothing at all."""
    js.push(7)
    assert js.json(API + "rows()") == []
    assert js.json(API + "rowIdentities()") == []
    assert js.json(API + "isLoaded()") is False


def test_a_rebuild_that_empties_the_table_leaves_a_stale_hidden_row_list(js: JsRuntime):
    """The surface keeps the old hide flags, which the module reports."""
    payload = state_payload("cleared")
    report = js.push(payload)
    assert payload["table"]["rows"] == []
    assert payload["table"]["hidden_rows"] != []
    assert [
        one["field"] for one in report["faults"] if one["fault"] == "short-list"
    ] == ["hidden_rows"]


PROBE_W_PX = 400
PROBE_H_PX = 60

#: An empty tag pair a rich-text widget swallows and a plain one paints.
MARKUP_PROBE = "<span></span>fire"
PLAIN_PROBE = "fire"


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


def a_button(text: str) -> Any:
    from PySide6.QtWidgets import QPushButton

    return QPushButton(text)


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


def a_message(text: str) -> Any:
    from PySide6.QtWidgets import QMessageBox

    widget = QMessageBox()
    widget.setText(text)
    return widget


def as_plain_text(widget: Any) -> Any:
    """The same widget told to print its text rather than read it as markup."""
    from PySide6.QtCore import Qt

    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


SCREEN_WIDGETS = {
    "QPushButton": a_button,
    "QGroupBox": a_group,
    "QTableWidgetItem": a_cell,
    "QHeaderView": a_header,
}

RICH_TEXT_WIDGETS = {"QLabel": a_label, "QMessageBox": a_message}


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_no_plain_widget_this_tab_uses_reads_its_caller_text_as_markup(qapp, kind: str):
    """A widget painting MARKUP_PROBE apart from PLAIN_PROBE never read its tags."""
    assert qapp is not None
    build_widget = SCREEN_WIDGETS[kind]
    assert painted(build_widget(MARKUP_PROBE)) != painted(
        build_widget(PLAIN_PROBE)
    ), f"{kind} painted the markup and the plain words the same"


@pytest.mark.parametrize("kind", sorted(RICH_TEXT_WIDGETS))
def test_the_two_widgets_this_tab_uses_that_do_read_markup_are_named(qapp, kind: str):
    """QLabel and QMessageBox swallow the tags MARKUP_PROBE carries, so the same
    string forced to PlainText -- which prints them -- paints differently."""
    assert qapp is not None
    build_widget = RICH_TEXT_WIDGETS[kind]
    assert painted(build_widget(MARKUP_PROBE)) != painted(
        as_plain_text(build_widget(MARKUP_PROBE))
    ), f"{kind} painted the tags the same whether it read them or printed them"


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_the_markup_measurement_reads_a_longer_text_as_a_different_painting(
    qapp, kind: str
):
    """A painting that never moved would read every widget as one that reads markup."""
    assert qapp is not None
    build_widget = SCREEN_WIDGETS[kind]
    assert painted(build_widget(PLAIN_PROBE * 8)) != painted(build_widget(PLAIN_PROBE))


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
            "the page never defined the fold tranches tab module in "
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
    "fontWeight",
    "fontSize",
    "height",
    "whiteSpace",
    "textOverflow",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.setAttribute('data-part', 'fold-tranches-page');"
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
    "  onClear: function (n) { window.PRESSED.push(['clear', n]); },"
    "  onFire: function (n) { window.PRESSED.push(['fire', n]); },"
    "  onArbiter: function (n) { window.PRESSED.push(['arbiter', n]); },"
    "  onAnswer: function (n) { window.PRESSED.push(['answer', n]); },"
    "  onPick: function (n) { window.PRESSED.push(['pick', n]); },"
    "  onType: function (n) { window.PRESSED.push(['type', n]); } };"
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
    browser.js("window.CHROME = " + json.dumps(json.dumps(chrome_payload())) + ";")
    browser.js(CHROME_SETTER + "(JSON.parse(window.CHROME));")
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
    parts = draw_tab(browser, state_payload("mixed"))
    assert browser.parsed(API + "spacePart") == "fold-tranches-page"
    assert at_path(parts, "fold-tranches-tab"), "the tab drew nothing into the space"


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A child with no name is a child no check can read."""
    draw_tab(browser, state_payload("mixed"))
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no data-part"
    assert named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    draw_tab(browser, state_payload("mixed"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


@pytest.mark.parametrize("state", ["fold", "mixed", "empty", "cleared"])
def test_each_health_row_draws_the_label_and_value_the_surface_carries(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "health-value")
    assert len(drawn) == len(payload["health_rows"])
    by_label = {one["attrs"]["data-key"]: one for one in drawn}
    for label, value in payload["health_rows"]:
        printed = browser.js(
            "String(JSON.parse(" + json.dumps(json.dumps(value)) + "))"
        )
        assert by_label[label]["text"] == printed, f"{state} row {label}"


def test_each_painted_health_row_matches_a_probe_built_from_its_whole_style(
    browser: Browser,
):
    """The applied value is read against a probe built from the whole declaration."""
    payload = state_payload("mixed")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "health-value")
    by_label = {one["attrs"]["data-key"]: one for one in drawn}
    for at, (label, _value) in enumerate(payload["health_rows"]):
        sheet = payload["health_colors"][at]
        style = browser.parsed(API + "paintedStyle(" + json.dumps(sheet) + ")")
        probe = browser.parsed(
            "window.probeAssign("
            + json.dumps(style)
            + ", JSON.parse(window.STYLE_NAMES))"
        )
        found = by_label[label]["style"]
        assert found["color"] == probe["color"], f"{label} drew {found} against {probe}"
        assert found["fontWeight"] == probe["fontWeight"]
        assert found["fontSize"] == probe["fontSize"]


def test_the_rendered_comparison_would_see_one_repainted_health_row(browser: Browser):
    parts = draw_tab(browser, state_payload("mixed"))
    drawn = with_part(parts, "health-value")[0]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"color": OTHER_COLOUR})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert drawn["style"]["color"] != probe["color"]


def test_an_unpainted_health_row_takes_no_colour_at_all(browser: Browser):
    """The surface publishes a sentinel for no colour, and it must not paint."""
    payload = state_payload("mixed")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "health-value")
    unpainted = [one for one in drawn if one["attrs"]["data-painted"] == "false"]
    assert unpainted, "no health row was left unpainted"
    plain = browser.parsed("window.probeAssign({}, JSON.parse(window.STYLE_NAMES))")
    for one in unpainted:
        assert one["style"]["color"] == plain["color"]


def test_the_unpainted_check_would_see_a_row_painted_black(browser: Browser):
    payload = state_payload("mixed")
    payload["no_cell_color"] = OTHER_COLOUR
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "health-value")
    assert [one for one in drawn if one["attrs"]["data-painted"] == "false"] == []


@pytest.mark.parametrize("state", ["fold", "mixed", "sorted"])
def test_each_table_row_paints_the_fill_and_edge_the_surface_carries(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "tranche-row")
    table = payload["table"]
    assert len(drawn) == table["row_count"]
    for at, one in enumerate(drawn):
        assert one["attrs"]["data-fill"] == table["row_backgrounds"][at]
        assert one["attrs"]["data-border"] == str(table["row_borders"][at])
        wanted = browser.parsed(
            "window.probeAssign("
            + json.dumps(
                {
                    "background": table["row_backgrounds"][at],
                    "borderStyle": "solid",
                    "borderWidth": str(payload["border_px"]) + "px",
                    "borderColor": table["row_borders"][at],
                }
            )
            + ", JSON.parse(window.STYLE_NAMES))"
        )
        assert one["style"]["borderTopWidth"] == wanted["borderTopWidth"]
        assert one["style"]["borderTopStyle"] == wanted["borderTopStyle"]


def test_every_column_the_surface_names_becomes_one_header_in_that_order(
    browser: Browser,
):
    payload = state_payload("mixed")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "header-cell")
    assert [one["text"] for one in drawn] == payload["table"]["columns"]
    assert [one["title"] for one in drawn] == payload["table"]["column_tooltips"]


def test_each_fold_row_carries_a_fire_button_naming_its_own_queue_number(
    browser: Browser,
):
    payload = state_payload("mixed")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "fire-button")
    assert [one["attrs"]["data-number"] for one in drawn] == [
        str(number) for number in payload["fire_button"]["numbers"]
    ]
    assert {one["title"] for one in drawn} == {payload["fire_button"]["tooltip"]}


def test_pressing_one_fire_button_runs_the_handler_with_that_row_s_queue_number(
    browser: Browser,
):
    """The argument must be the queue number, never the row's place in the list."""
    payload = state_payload("sorted")
    draw_tab(browser, payload)
    wanted = payload["fire_button"]["numbers"][1]
    browser.js("window.partsNamed('fire-button')[1].click();")
    assert browser.parsed("window.PRESSED") == [["fire", wanted]]
    assert browser.parsed(API + "pressed()")["argument"] == wanted


def test_the_fire_check_would_see_a_button_answering_with_its_own_position(
    browser: Browser,
):
    payload = state_payload("sorted")
    draw_tab(browser, payload)
    browser.js("window.partsNamed('fire-button')[1].click();")
    assert browser.parsed("window.PRESSED")[0][1] != 1


def test_each_extractor_row_carries_an_arbiter_button_naming_its_own_tranche(
    browser: Browser,
):
    payload = state_payload("mixed")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "arbiter-button")
    assert [one["attrs"]["data-tranche-id"] for one in drawn] == [
        one[0] for one in payload["arbiter_button"]["identities"]
    ]
    assert [one["attrs"]["data-child-bot-id"] for one in drawn] == [
        one[1] for one in payload["arbiter_button"]["identities"]
    ]


def test_pressing_one_arbiter_button_runs_the_handler_with_that_tranche_identity(
    browser: Browser,
):
    payload = state_payload("mixed")
    draw_tab(browser, payload)
    wanted = payload["arbiter_button"]["identities"][1]
    browser.js("window.partsNamed('arbiter-button')[1].click();")
    assert browser.parsed("window.PRESSED") == [["arbiter", wanted]]


def test_each_arbiter_button_shows_the_word_its_own_row_stores(browser: Browser):
    payload = state_payload("mixed")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "arbiter-button")
    column = payload["table"]["arbiter_column"]
    wanted = [
        payload["table"]["rows"][at][column]
        for at in range(len(payload["table"]["rows"]))
        if payload["table"]["rows"][at][0] == payload["extractor_row_number"]
    ]
    assert [one["text"] for one in drawn] == wanted


@pytest.mark.parametrize("at", (0, 1, 2))
def test_pressing_one_clear_button_runs_the_handler_with_its_own_wired_name(
    browser: Browser, at: int
):
    payload = state_payload("fold")
    draw_tab(browser, payload)
    browser.js("window.partsNamed('clear-button')[" + str(at) + "].click();")
    assert browser.parsed("window.PRESSED") == [["clear", CLEAR_KINDS[at]]]


def test_a_clear_button_the_surface_disables_is_drawn_disabled(browser: Browser):
    payload = state_payload("empty")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "clear-button")
    assert [one["attrs"]["data-enabled"] for one in drawn] == [
        str(bool(one[1])).lower() for one in payload["buttons"]
    ]


def test_pressing_one_message_box_answer_runs_the_handler_with_that_value(
    browser: Browser,
):
    payload = state_payload("cleared")
    draw_tab(browser, payload)
    browser.js("window.partsNamed('box-button')[0].click();")
    pressed = browser.parsed("window.PRESSED")
    assert pressed[0][0] == "answer"
    assert pressed[0][1] in payload["button_values"].values()


def test_the_order_picker_and_filter_box_are_drawn_by_the_panel_chrome(
    browser: Browser,
):
    """The tab leaves one space and fold_chrome.js draws both pieces into it."""
    parts = draw_tab(browser, state_payload("mixed"))
    space = with_part(parts, "row-controls-space")
    assert space, "the tab drew no space for the row pieces"
    assert space[0]["attrs"]["data-matched"] == "true"
    assert space[0]["attrs"]["data-fills"] == chrome.METHOD
    assert with_part(parts, "sort-combo"), "the chrome drew no order picker"
    assert with_part(parts, "filter-edit"), "the chrome drew no filter box"


def test_picking_an_order_inside_the_tab_runs_the_handler_with_that_order(
    browser: Browser,
):
    payload = state_payload("mixed")
    draw_tab(browser, payload)
    wanted = payload["row_controls"]["orders"][3]
    browser.js(
        "(function () { var el = window.partNamed('sort-combo');"
        " el.value = " + json.dumps(wanted) + ";"
        " el.dispatchEvent(new Event('change', { bubbles: true })); })()"
    )
    assert browser.parsed("window.PRESSED") == [["pick", wanted]]


def test_typing_in_the_filter_box_inside_the_tab_runs_the_handler_with_that_text(
    browser: Browser,
):
    draw_tab(browser, state_payload("mixed"))
    browser.js(
        "(function () { var el = window.partNamed('filter-edit');"
        " var setter = Object.getOwnPropertyDescriptor("
        "   window.HTMLInputElement.prototype, 'value').set;"
        " setter.call(el, 'extractor');"
        " el.dispatchEvent(new Event('input', { bubbles: true })); })()"
    )
    assert browser.parsed("window.PRESSED") == [["type", "extractor"]]


def test_the_handler_check_would_see_a_press_nobody_made(browser: Browser):
    draw_tab(browser, state_payload("mixed"))
    assert browser.parsed("window.PRESSED") == []


def test_a_hidden_row_is_drawn_hidden_rather_than_dropped(browser: Browser):
    """Hiding a row keeps every button on the tranche it belongs to."""
    payload = state_payload("filtered")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "tranche-row")
    assert len(drawn) == payload["table"]["row_count"]
    assert [one["attrs"]["data-hidden"] for one in drawn] == [
        str(bool(flag)).lower() for flag in payload["table"]["hidden_rows"]
    ]


def test_the_empty_note_is_shown_only_where_the_surface_shows_it(browser: Browser):
    shown = with_part(draw_tab(browser, state_payload("empty")), "empty-note")[0]
    quiet = with_part(draw_tab(browser, state_payload("mixed")), "empty-note")[0]
    assert shown["hidden"] is False
    assert quiet["hidden"] is True
    assert shown["text"] == state_payload("empty")["empty_label"]["text"]


def test_the_tab_refuses_markup_a_hostile_cell_carries(browser: Browser):
    """React writes the tags as text, so no element reaches the document."""
    payload = state_payload("mixed")
    payload["table"]["rows"][0][1] = MARKUP_NAME
    parts = draw_tab(browser, payload)
    drawn = [
        one
        for one in with_part(parts, "tranche-cell")
        if one["attrs"]["data-column"] == "1"
    ]
    assert drawn[0]["text"] == MARKUP_NAME
    assert "<img" not in drawn[0]["html"]
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_tab_refuses_markup_a_hostile_message_box_carries(browser: Browser):
    payload = state_payload("cleared")
    payload["boxes"][0]["text"] = MARKUP_NAME
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "box-text")[0]
    assert drawn["text"] == MARKUP_NAME
    assert "<img" not in drawn["html"]


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    draw_tab(browser, state_payload("mixed"))
    browser.js("window.HOST.firstChild.insertAdjacentHTML('beforeend', '<img>');")
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 1


def test_a_two_hundred_character_cell_stretches_the_table_rather_than_clipping(
    browser: Browser,
):
    """A CSS table grows to fit where Qt clips, so the width is reported."""
    payload = state_payload("mixed")
    payload["table"]["rows"][0][8] = LONG_NAME
    wide = with_part(draw_tab(browser, payload), "tranche-table")[0]
    narrow = with_part(draw_tab(browser, state_payload("mixed")), "tranche-table")[0]
    assert wide["width"] >= narrow["width"]


def test_the_counters_reset_row_carries_a_raw_stamp_the_surface_never_formats(
    js: JsRuntime,
):
    """The surface publishes the seconds and the format apart, so no date is drawn."""
    payload = state_payload("mixed")
    js.push(payload)
    label = payload["health_labels"][12]
    value = js.called("healthValue", label)
    assert isinstance(value, (int, float)), "the row already carries text"
    assert not isinstance(value, bool)
    assert payload["formats"]["counters_reset_time"], "the format is published"
    assert str(value) not in payload["formats"]["counters_reset_time"]


def test_the_tab_declares_its_own_spacing_and_leaves_the_form_to_the_host(
    browser: Browser,
):
    """The surface sets a spacing and no margin, and says the host builds the form."""
    payload = state_payload("mixed")
    parts = draw_tab(browser, payload)
    tab = at_path(parts, "fold-tranches-tab")[0]
    assert (
        tab["attrs"]["data-margins-set"]
        == str(payload["container"]["margins_set"]).lower()
    )
    group = with_part(parts, "health-group")[0]
    assert (
        group["attrs"]["data-configured-by-host"]
        == str(payload["health_group"]["configured_by_host"]).lower()
    )
