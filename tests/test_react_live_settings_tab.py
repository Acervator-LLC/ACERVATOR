"""The React Settings tab, against live_settings_tab_surface.py.

The Settings tab is the editable page the operator opens on Detail for a
running bot. Every value it draws comes from the ``live_settings_tab.state``
bridge method; the module here writes none of its own.
"""

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

from src.gui.color_alpha import css_rgba
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import live_settings_tab_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    load_order,
    new_engine,
    runs_after,
    swap_module,
)
from tests.test_live_settings_tab_surface_parity import BASE_BOT, BASE_CONFIG

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "live_settings_tab.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorLiveSettingsTab."
SETTER = "acervatorSetLiveSettingsTab"

#: The merged pieces the page loads beside this module, needed at call time.
SHARED_MODULES = (WEB / "shared_widgets.js", WEB / "header_strip.js")

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
OTHER_COLOUR = "#7c1fa2"
BYTE_ALPHA = "rgba(12, 34, 56, 204)"
GRADIENT_SHEET = "background: qlineargradient(x1:0, y1:0, x2:1, y2:0);"
UNKNOWN_NAME = "no-such-module.js"

SCRUM_SCOUT = {
    "pairs": [["AERO", "BTC", 1.5], ["AERO", "ETH", -2.0], ["AERO", "USD", 3.0]]
}
RATES = {"btc_usd": 60_000.0, "eth_usd": 3_000.0}


def a_bot(**rest: Any) -> dict:
    """One running bot the tab reads, in the keys the surface takes."""
    return dict(BASE_BOT, **rest)


def a_config(**rest: Any) -> dict:
    """One stored config, every field the tab reads present."""
    return dict(BASE_CONFIG, **rest)


def a_build(mode: str, config: dict | None = None, **bot: Any) -> dict:
    """One first call that builds the tab for a bot of `mode`."""
    return {
        "reset": True,
        "bot": a_bot(mode=mode, **bot),
        "config": config or a_config(),
        "scout": SCRUM_SCOUT,
        "rates": RATES,
        "build": True,
    }


STATES: dict = {
    "fresh": [{"reset": True}],
    "scrumming": [a_build("scrumming")],
    "hot": [
        a_build(
            "scrumming",
            live_target=105.5,
            anchor_target=100.0,
            surplus=3.25,
            budget=10.0,
            consumed=2.0,
            tranches=[{"usd": 4.0}, {"usd": 12.0}],
        )
    ],
    "extractor": [
        a_build("extractor", a_config(extractor_alt_targets=["ETH/USD", "SOL/USD"]))
    ],
    "auto_scan": [a_build("extractor", a_config(extractor_alt_targets=[]))],
    "reset_applied": [
        a_build("scrumming", reset_applied=["soft", "hard"]),
        {"reset_breakers": True},
    ],
    "reset_nothing": [a_build("scrumming"), {"reset_breakers": True}],
    "reset_unsupported": [
        a_build("scrumming", has_reset=False),
        {"reset_breakers": True},
    ],
    "destruct_dispatched": [
        a_build("scrumming"),
        {"self_destruct": True, "typed": surface.SELF_DESTRUCT_PHRASE},
    ],
    "destruct_mismatch": [
        a_build("scrumming"),
        {"self_destruct": True, "typed": "not the phrase"},
    ],
    "destruct_unavailable": [
        a_build("scrumming", has_self_destruct=False),
        {"self_destruct": True},
    ],
    "edited": [a_build("scrumming"), {"changes": [["stack_mode", True]]}],
}
STATE_NAMES = tuple(STATES)
DRAWN_STATES = ("scrumming", "hot", "extractor", "auto_scan", "destruct_dispatched")


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def at_dotted(node: Any, path: Any) -> Any:
    """The value `path` names, each step a bag key or a list place."""
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
    payload = state_payload("scrumming")
    payload["only_on_the_surface"] = []
    js.push(payload)
    assert sorted(set(payload) - set(declared_fields(js))) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    payload = state_payload("scrumming")
    assert payload.pop("row_count") is not None
    js.push(payload)
    assert sorted(set(declared_fields(js)) - set(payload)) == ["row_count"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = state_payload("scrumming")
    payload["accessible_name"] = LONG_NAME
    js.push(payload)
    original = state_payload("scrumming")
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
    assert report["declared"] == {
        "fields": len(payload),
        "rows": payload["row_count"],
        "groups": len(payload["group_titles"]),
        "controls": len(payload["control_names"]),
        "actions": len(payload["actions"]),
    }, state
    assert report["held"] == dict(
        report["declared"],
        rows=len(payload["rows"]),
        groups=len(payload["groups"]),
        controls=len(payload["control_specs"]),
    ), state


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("scrumming")
    declared = len(payload)
    del payload["accessible_name"]
    report = js.push(payload)
    assert report["declared"]["fields"] == declared
    assert report["held"]["fields"] == declared - 1
    assert [one["field"] for one in report["faults"]] == ["accessible_name"]


def test_a_dropped_group_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("scrumming")
    before = js.push(payload)
    dropped = payload["groups"].pop()
    payload["rows"] = [row for row in payload["rows"] if row[0] != dropped[0]]
    payload["row_count"] = len(payload["rows"])
    after = js.push(payload)
    assert after["declared"]["groups"] == before["declared"]["groups"], dropped
    assert after["held"]["groups"] == before["held"]["groups"] - 1, dropped


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
    payload = state_payload("scrumming")
    payload["row_count"] = str(payload["row_count"])
    js.push(payload)
    expected = python_kinds(state_payload("scrumming"))
    actual = js.json(API + "kinds()")
    assert sorted(p for p, k in expected.items() if actual.get(p) != k) == ["row_count"]


def test_the_type_walk_names_a_scalar_where_a_settings_row_belongs(js: JsRuntime):
    """A scalar where the payload lists a row must not read as that row."""
    payload = state_payload("scrumming")
    payload["rows"][1] = 7
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("rows.1") == "number"
    assert "rows.1.0" not in actual
    payload["rows"][1] = [None, None, None]
    js.push(payload)
    assert js.json(API + "kinds()").get("rows.1.0") == "null"


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
    assert not_plain_data(raw) == [], state


def test_the_plain_data_walk_names_a_live_object_put_on_the_payload():
    payload = state_payload("scrumming")
    payload["container"]["live"] = object()
    assert not_plain_data(payload) == ["container.live"]


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == [], state


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    js.push(state_payload("scrumming"))
    js.run("PAYLOAD = JSON.parse(PAYLOAD);")
    js.run("PAYLOAD.container.live = function () { return 1; };")
    js.run(SETTER + "(PAYLOAD);")
    assert js.json(API + "notPlainData()") == [
        {"path": "container.live", "kind": "function"}
    ]


#: The spec keys whose value the tab paints; the rest name a control, not a word.
PAINTING_SPEC_KEYS = ("text", "suffix", "prefix", "placeholder", "special_value_text")


def shown_values() -> set:
    """Every string the tab paints or shows as a tooltip, from every state."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        found |= {payload["info_label"]["text"], payload["accessible_name"]}
        found |= {title for _, title in payload["groups"]}
        found |= {one for _, one, _ in payload["rows"] if isinstance(one, str)}
        found |= {one for one in payload["values"].values() if isinstance(one, str)}
        found |= set(payload["timeframe_items"]) | set(payload["timeframe_fallback"])
        for spec in payload["control_specs"]:
            found |= {
                spec[key]
                for key in PAINTING_SPEC_KEYS
                if isinstance(spec.get(key), str)
            }
            for item in spec.get("items") or []:
                found |= set(item) if isinstance(item, list) else {item}
        for line in ("compound_row", "surplus_row", "budget_row", "over_cap_row"):
            found |= {one for one in payload[line] if isinstance(one, str)}
        for line in payload["denom_rows"].values():
            found |= {one for one in line if isinstance(one, str)}
        found |= set(payload["alt_targets"]["pairs"])
        found |= {
            payload["alt_targets"]["empty_text"],
            payload["alt_targets"]["active_format"],
        }
        found |= {
            one for one in payload["reset_button"].values() if isinstance(one, str)
        }
        found |= {
            one for one in payload["danger_button"].values() if isinstance(one, str)
        }
        found |= {one for one in payload["tooltips"].values() if isinstance(one, str)}
        for box in payload["boxes"]:
            found |= {box["title"], box["text"]}
        for one in payload["prompts"]:
            found |= {piece for piece in one if isinstance(piece, str)}
        for bag in ("colors", "denom_labels", "read_only_labels", "texts", "titles"):
            found |= {one for one in payload[bag].values() if isinstance(one, str)}
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
BUILT = state_payload("hot")
WITH_BOX = state_payload("destruct_dispatched")


def spec_words(payload: dict) -> set:
    """Every key and every kind the control specs declare."""
    found: set = set()
    for spec in payload["control_specs"]:
        found |= set(spec)
        found.add(spec["kind"])
    return found


def plan_row_names(payload: dict) -> set:
    """Every row name that is not a control, which is what the plans carry."""
    return {row[2] for row in payload["rows"]} - set(payload["control_names"])


#: NAMED_WORDS lists every published string the module may write.
NAMED_WORDS = sorted(
    set(BARE)
    | set(BARE["container"])
    | set(BARE["forms"])
    | set(BARE["info_label"])
    | set(BARE["reset_button"])
    | set(BARE["danger_button"])
    | set(BARE["alt_targets"])
    | set(BARE["colors"])
    | set(BARE["timers"])
    | spec_words(BARE)
    | set(BUILT["denom_rows"])
    | plan_row_names(BUILT)
    | plan_row_names(state_payload("extractor"))
    | set(WITH_BOX["boxes"][0])
    | {surface.METHOD}
)

WRITTEN_LINES: dict = {
    "colour": 'var written = "' + OTHER_COLOUR + '";',
    "error_colour": 'var written = "' + surface.ERROR_COLOR + '";',
    "grey_colour": 'var written = "' + surface.GREY_COLOR + '";',
    "row_label": 'var written = "' + surface.COMPOUND_ROW_LABEL + '";',
    "group_title": 'var written = "' + surface.BREAKER_GROUP_TITLE + '";',
    "info_note": 'var written = "' + surface.INFO_TEXT + '";',
    "em_dash": 'var written = "' + surface.DENOM_PLACEHOLDER + '";',
    "button_words": 'var written = "' + surface.RESET_BUTTON_TEXT + '";',
    "phrase": 'var written = "' + surface.SELF_DESTRUCT_PHRASE + '";',
    "spacing": "var written = " + str(surface.CONTENT_SPACING_PX) + ";",
    "delay": "var written = " + str(surface.RESET_RESTORE_DELAY_MS) + ";",
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


def test_the_module_writes_no_number_colour_shown_value_or_token_value():
    """A literal typed here is a second source for a value the surface owns."""
    assert caught_by_scan(MODULE_SOURCE) == set(), (
        "live_settings_tab.js writes values of its own: numbers "
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
    """Every bare colour the payload carries, from every place holding one."""
    found = [one for one in payload["colors"].values() if isinstance(one, str)]
    for line in ("compound_row", "surplus_row", "budget_row", "over_cap_row"):
        found += [one for one in payload[line][1:] if isinstance(one, str)]
    for line in payload["denom_rows"].values():
        found += [one for one in line[1:] if isinstance(one, str)]
    return found


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_every_colour_the_tab_carries_is_swept_for_the_alpha_order_fault(
    js: JsRuntime, state: str
):
    """A colour no sweep reads is one the alpha-order fault can hide in."""
    payload = state_payload(state)
    js.push(payload)
    swept = [one["colour"] for one in js.json(API + "paintedColours()")]
    missed = [one for one in payload_colours(payload) if one not in swept]
    assert not missed, f"{state}: colours no sweep read: {missed}"


@pytest.mark.parametrize(
    "path",
    [("colors", "success"), ("compound_row", 1), ("denom_rows", "BTC", 1)],
    ids=["colour_bag", "read_only_row", "denom_row"],
)
def test_the_alpha_sweep_names_one_colour_written_with_eight_digits(
    js: JsRuntime, path: tuple
):
    payload = state_payload("hot")
    at_dotted(payload, path[:-1])[path[-1]] = SWAPPED_ALPHA
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["swapped-alpha"], report[
        "faults"
    ]
    assert [one["detail"] for one in report["faults"]] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_the_info_style_sheet(js: JsRuntime):
    payload = state_payload("hot")
    payload["info_label"]["style_sheet"] += " border-color: " + SWAPPED_ALPHA + ";"
    report = js.push(payload)
    assert [one["detail"] for one in report["faults"]] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_gradient_no_browser_stylesheet_runs(js: JsRuntime):
    payload = state_payload("hot")
    payload["info_label"]["style_sheet"] = GRADIENT_SHEET
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["not-css"], report["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_colour_the_settings_tab_publishes_carries_a_qt_alpha_byte(state: str):
    """CSS clamps an alpha above one, so a Qt byte reaching it paints solid."""
    payload = state_payload(state)
    rewritten = {
        one: css_rgba(one)
        for one in published_strings_of(payload)
        if css_rgba(one) != one
    }
    assert not rewritten, f"{state}: colours a browser would paint opaque: {rewritten}"


def published_strings_of(payload: Any) -> set:
    """Every string the payload carries, keys included."""
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

    walk(payload)
    return found


def test_the_alpha_byte_check_names_a_byte_alpha_put_into_the_payload():
    """Without a control the zero above is a claim about the instrument."""
    payload = state_payload("hot")
    payload["colors"]["success"] = BYTE_ALPHA
    rewritten = {
        one: css_rgba(one)
        for one in published_strings_of(payload)
        if css_rgba(one) != one
    }
    assert sorted(rewritten) == [BYTE_ALPHA]


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_no_bag_the_surface_publishes_carries_a_key_a_browser_would_move(
    js: JsRuntime, state: str
):
    """A digit key is listed first by a browser and the drawn order changes."""
    assert js.push(state_payload(state))["faults"] == [], state


def test_the_bag_order_check_names_a_digit_key_put_into_a_published_bag(js: JsRuntime):
    payload = state_payload("hot")
    payload["values"]["7"] = None
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["reordered-key"]
    assert [one["detail"] for one in report["faults"]] == ["7"]


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_every_wired_name_opens_with_a_control_a_button_or_a_timer(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    named = js.json(API + "wirableNames()")
    opened = sorted({one.split(".")[0] for one in payload["actions"]})
    assert set(opened) <= set(named), sorted(set(opened) - set(named))


def test_the_action_check_names_a_wired_name_the_payload_never_declared(js: JsRuntime):
    payload = state_payload("hot")
    payload["actions"]["no_such_control.valueChanged"] = "nothing"
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["unknown-action"]


def test_the_action_check_names_a_control_row_the_payload_wired_nothing_for(
    js: JsRuntime,
):
    payload = state_payload("hot")
    dropped = [one for one in payload["actions"] if one.startswith("vis.")]
    assert dropped, "the payload wired nothing for the visibility combo"
    for one in dropped:
        del payload["actions"][one]
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["missing"]
    assert [one["detail"] for one in report["faults"]] == ["vis"]


@pytest.mark.parametrize("state", DRAWN_STATES)
def test_every_row_the_payload_lists_is_one_the_module_can_draw(
    js: JsRuntime, state: str
):
    """A row with no way to draw it is an empty line the operator cannot use."""
    payload = state_payload(state)
    js.push(payload)
    drawable = js.json(API + "drawableNames()")
    undrawn = [row[2] for row in payload["rows"] if row[2] not in drawable]
    assert not undrawn, f"{state}: rows the module has no way to draw: {undrawn}"


def test_the_row_check_names_a_row_the_module_has_no_way_to_draw(js: JsRuntime):
    payload = state_payload("hot")
    payload["rows"].append([payload["groups"][0][0], None, "no_such_row"])
    payload["row_count"] = len(payload["rows"])
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["unnamed-row"]
    assert [one["detail"] for one in report["faults"]] == ["no_such_row"]


def test_the_row_check_names_two_rows_carrying_one_name(js: JsRuntime):
    payload = state_payload("hot")
    payload["rows"].append(list(payload["rows"][0]))
    payload["row_count"] = len(payload["rows"])
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["duplicate-name"]


def test_the_row_check_names_a_control_row_the_payload_seeded_no_value_for(
    js: JsRuntime,
):
    payload = state_payload("hot")
    assert payload["values"].pop("vis") is not None
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["unseeded-row"]
    assert [one["detail"] for one in report["faults"]] == ["vis"]


def test_the_group_check_names_a_title_the_payload_never_published(js: JsRuntime):
    payload = state_payload("hot")
    payload["groups"][0][1] = LONG_NAME
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["missing"]


def test_the_group_check_names_a_row_put_into_a_group_no_one_draws(js: JsRuntime):
    payload = state_payload("hot")
    payload["rows"][0][0] = "no_such_group"
    report = js.push(payload)
    assert [one["fault"] for one in report["faults"]] == ["unknown-group"]


HOSTILE_PLACES = {
    "group_title": (("groups", 0, 1), LONG_NAME),
    "row_label": (("rows", 0, 1), MARKUP_NAME),
    "compound_text": (("compound_row", 0), NEWLINE_NAME),
    "denom_text": (("denom_rows", "BTC", 0), MARKUP_NAME),
    "reset_words": (("reset_button", "current_text"), MARKUP_NAME),
    "info_text": (("info_label", "text"), NEWLINE_NAME),
}


@pytest.mark.parametrize("place", sorted(HOSTILE_PLACES))
def test_a_hostile_value_is_reported_and_the_module_still_answers(
    js: JsRuntime, place: str
):
    """A payload the tab cannot refuse must still leave the module answering."""
    path, value = HOSTILE_PLACES[place]
    payload = state_payload("hot")
    at_dotted(payload, path[:-1])[path[-1]] = value
    js.push(payload)
    assert js.json(API + "isLoaded()") is True, place
    assert js.json(API + "notPlainData()") == [], place
    assert len(js.json(API + "declaredNames()")) == len(BARE), place


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    js.push(None)
    assert js.json(API + "isLoaded()") is False
    assert js.json(API + "payload()") == {}


@pytest.mark.parametrize("field", ["rows", "groups", "values", "control_specs"])
def test_a_field_the_payload_nulls_is_reported_and_the_module_answers(
    js: JsRuntime, field: str
):
    """A nulled field is named first; what it starves reads after it, never instead."""
    payload = state_payload("hot")
    payload[field] = None
    report = js.push(payload)
    assert report["faults"][0]["field"] == field, report["faults"][:3]
    assert report["faults"][0]["fault"] in ("not-a-list", "not-a-bag")
    assert js.json(API + "isLoaded()") is True
    assert len(js.json(API + "declaredNames()")) == len(BARE)


def test_the_null_field_check_reports_nothing_when_the_field_is_whole(js: JsRuntime):
    assert js.push(state_payload("hot"))["faults"] == []


def test_the_module_reports_when_the_page_has_no_bridge_to_ask(js: JsRuntime):
    js.run("window.acervatorLoadLiveSettingsTab({});")
    assert js.json(API + "loadError()") == "the preload bridge is not present"


def test_the_module_is_registered_and_runs_after_its_shared_pieces():
    order = load_order()
    assert runs_after(
        order, MODULE_PATH.name, "shared_widgets.js", "header_strip.js"
    ), order


def test_the_load_order_check_reports_false_when_a_name_is_absent():
    assert (
        runs_after(["shared_widgets.js"], MODULE_PATH.name, "header_strip.js") is False
    )
    assert runs_after(load_order(), UNKNOWN_NAME, "header_strip.js") is False


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
            "the page never defined the live settings tab module in "
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
    "fontFamily",
    "whiteSpace",
    "gap",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.setAttribute('data-part', 'settings-page');"
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
    "window.namedPart = function (part, name) {"
    "  return window.HOST.querySelector("
    "    '[data-part=\"' + part + '\"][data-name=\"' + name + '\"]'); };"
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
    "        value: el.value === undefined ? null : String(el.value),"
    "        checked: el.checked === undefined ? null : el.checked,"
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
    "  onEdit: function (n, v) { window.PRESSED.push(['edit', n, v]); },"
    "  onPress: function (n) { window.PRESSED.push(['press', n]); } };"
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


def with_part(parts: list, name: str) -> list:
    return [one for one in parts if one["path"].split("/")[-1] == name]


def named(parts: list, part: str, name: str) -> dict:
    found = [
        one for one in with_part(parts, part) if one["attrs"].get("data-name") == name
    ]
    assert len(found) == 1, f"{part} named {name}: {len(found)} drawn"
    return found[0]


def test_the_tab_fills_the_named_space_the_window_left_for_it(browser: Browser):
    """The Live Bot Settings window names one space and this tab fills it."""
    parts = draw_tab(browser, state_payload("hot"))
    assert browser.parsed(API + "spacePart") == "settings-page"
    assert with_part(parts, "live-settings-tab"), "the tab drew nothing into the space"


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A drawn child with no data-part is one no check can read."""
    draw_tab(browser, state_payload("extractor"))
    every, drawn = browser.parsed(COUNT_ELEMENTS)
    assert every == drawn, f"{every - drawn} of {every} drawn children carry no name"


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    draw_tab(browser, state_payload("extractor"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('div'));")
    every, drawn = browser.parsed(COUNT_ELEMENTS)
    assert every == drawn + 1


def test_each_group_draws_the_title_the_surface_carries_and_only_its_own_rows(
    browser: Browser,
):
    payload = state_payload("extractor")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "settings-group")
    assert len(drawn) == len(payload["groups"])
    for one, (name, title) in zip(drawn, payload["groups"]):
        assert one["attrs"]["data-name"] == name
        assert named(parts, "group-title", name)["text"] == title
        mine = [row for row in payload["rows"] if row[0] == name]
        assert one["attrs"]["data-count"] == str(len(mine))


def test_each_settings_row_draws_the_label_the_surface_carries(browser: Browser):
    payload = state_payload("hot")
    parts = draw_tab(browser, payload)
    for group, row_label, name in payload["rows"]:
        drawn = named(parts, "row-label", name)
        assert drawn["text"] == ("" if row_label is None else row_label), name
        assert named(parts, "settings-row", name)["attrs"]["data-group"] == group


def test_each_combo_offers_the_items_the_surface_publishes_in_its_own_order(
    browser: Browser,
):
    payload = state_payload("hot")
    parts = draw_tab(browser, payload)
    for spec in payload["control_specs"]:
        if spec["kind"] not in ("combo_data", "combo_text"):
            continue
        if not any(row[2] == spec["name"] for row in payload["rows"]):
            continue
        offered = [
            one["text"]
            for one in with_part(parts, "combo-option")
            if one["attrs"]["data-name"] == spec["name"]
        ]
        items = spec.get("items") or payload["timeframe_items"]
        wanted = [one[0] if isinstance(one, list) else one for one in items]
        assert offered == wanted, spec["name"]


def test_each_combo_shows_the_item_the_published_index_names(browser: Browser):
    payload = state_payload("hot")
    parts = draw_tab(browser, payload)
    for name, at in payload["combo_index"].items():
        spec = next(one for one in payload["control_specs"] if one["name"] == name)
        items = spec.get("items") or payload["timeframe_items"]
        item = items[at]
        wanted = item[1] if isinstance(item, list) else item
        assert named(parts, "control", name)["value"] == str(wanted), name


def test_each_check_draws_its_own_words_and_the_state_the_surface_seeded(
    browser: Browser,
):
    payload = state_payload("hot")
    parts = draw_tab(browser, payload)
    for spec in payload["control_specs"]:
        if spec["kind"] != "check":
            continue
        if not any(row[2] == spec["name"] for row in payload["rows"]):
            continue
        assert named(parts, "check-text", spec["name"])["text"] == spec["text"]
        drawn = named(parts, "control", spec["name"])
        assert drawn["checked"] is (payload["values"][spec["name"]] is True), spec[
            "name"
        ]


def test_each_number_carries_the_bounds_and_the_step_the_surface_publishes(
    browser: Browser,
):
    payload = state_payload("hot")
    parts = draw_tab(browser, payload)
    for spec in payload["control_specs"]:
        if spec["kind"] not in ("double_spin", "spin"):
            continue
        if not any(row[2] == spec["name"] for row in payload["rows"]):
            continue
        drawn = named(parts, "control", spec["name"])
        low, high = spec["range"]
        assert float(drawn["attrs"]["min"]) == float(low), spec["name"]
        assert float(drawn["attrs"]["max"]) == float(high), spec["name"]
        assert float(drawn["value"]) == float(payload["values"][spec["name"]]), spec[
            "name"
        ]


def test_a_spin_at_its_lowest_value_prints_the_words_qt_prints_in_its_place(
    browser: Browser,
):
    """The despawn timer reads Off at zero rather than a bare number and a unit."""
    payload = state_payload("hot")
    spec = next(
        one for one in payload["control_specs"] if one.get("special_value_text")
    )
    payload["values"][spec["name"]] = spec["range"][0]
    parts = draw_tab(browser, payload)
    assert (
        named(parts, "value-suffix", spec["name"])["text"] == spec["special_value_text"]
    )


def test_a_spin_above_its_lowest_value_prints_its_own_unit(browser: Browser):
    payload = state_payload("hot")
    spec = next(
        one for one in payload["control_specs"] if one.get("special_value_text")
    )
    payload["values"][spec["name"]] = spec["range"][1]
    parts = draw_tab(browser, payload)
    assert named(parts, "value-suffix", spec["name"])["text"] == spec["suffix"]


def test_each_read_only_row_draws_the_text_and_takes_the_colour_the_surface_sends(
    browser: Browser,
):
    payload = state_payload("hot")
    parts = draw_tab(browser, payload)
    plan = {
        "live_lbl": "compound_row",
        "surplus_lbl": "surplus_row",
        "budget_lbl": "budget_row",
        "over_lbl": "over_cap_row",
    }
    for name, field in plan.items():
        if not any(row[2] == name for row in payload["rows"]):
            continue
        drawn = named(parts, "read-only-value", name)
        assert drawn["text"] == payload[field][0], name
        wanted = payload[field][1] if len(payload[field]) > 1 else None
        assert (
            drawn["attrs"]["data-styled"] == str(isinstance(wanted, str)).lower()
        ), name


def test_a_painted_read_only_row_matches_a_probe_built_from_its_own_colour(
    browser: Browser,
):
    payload = state_payload("hot")
    parts = draw_tab(browser, payload)
    drawn = named(parts, "read-only-value", "surplus_lbl")
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"color": payload["surplus_row"][1]})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert drawn["style"]["color"] == probe["color"]


def test_the_painted_comparison_would_see_one_repainted_read_only_row(
    browser: Browser,
):
    payload = state_payload("hot")
    payload["surplus_row"][1] = OTHER_COLOUR
    parts = draw_tab(browser, payload)
    drawn = named(parts, "read-only-value", "surplus_lbl")
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"color": state_payload("hot")["surplus_row"][1]})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert drawn["style"]["color"] != probe["color"]


def test_a_control_seeded_with_nothing_draws_an_empty_box_and_not_the_word_null(
    browser: Browser,
):
    """An operator reading the word null would take it for a stored value."""
    payload = state_payload("hot")
    payload["values"]["max_entry_px"] = None
    parts = draw_tab(browser, payload)
    drawn = named(parts, "control", "max_entry_px")
    assert drawn["value"] == ""
    assert "null" not in drawn["whole"]


def test_the_empty_box_check_would_see_a_control_the_surface_did_seed(
    browser: Browser,
):
    parts = draw_tab(browser, state_payload("hot"))
    assert named(parts, "control", "max_entry_px")["value"] != ""


def test_a_cross_pair_row_the_surface_hides_is_drawn_hidden(browser: Browser):
    payload = state_payload("hot")
    payload["denom_visible"]["BTC"] = False
    parts = draw_tab(browser, payload)
    assert named(parts, "denom-value", "target_btc_lbl")["hidden"] is True
    assert named(parts, "denom-value", "target_eth_lbl")["hidden"] is False


def test_each_button_draws_the_words_and_the_delay_the_surface_publishes(
    browser: Browser,
):
    """The restore delay is read as a published value, never as elapsed time."""
    payload = state_payload("reset_applied")
    parts = draw_tab(browser, payload)
    reset = named(parts, "row-button", "cb_reset_all_btn")
    assert reset["text"] == payload["reset_button"]["current_text"]
    assert reset["attrs"]["data-delay-ms"] == str(
        payload["reset_button"]["restore_delay_ms"]
    )
    danger = named(parts, "row-button", "self_destruct_btn")
    assert danger["text"] == payload["danger_button"]["text"]
    assert named(parts, "danger-hint", "self_destruct_btn") is not None


def test_pressing_one_button_runs_the_handler_with_its_own_name(browser: Browser):
    draw_tab(browser, state_payload("hot"))
    browser.js("window.namedPart('row-button', 'self_destruct_btn').click();")
    assert browser.parsed("window.PRESSED") == [["press", "self_destruct_btn"]]


def test_the_press_check_would_see_a_press_nobody_made(browser: Browser):
    draw_tab(browser, state_payload("hot"))
    assert browser.parsed("window.PRESSED") == []


def test_changing_one_check_runs_the_handler_with_that_control_and_value(
    browser: Browser,
):
    draw_tab(browser, state_payload("hot"))
    browser.js("window.namedPart('control', 'stack_mode').click();")
    assert browser.parsed("window.PRESSED") == [["edit", "stack_mode", True]]
    assert browser.parsed(API + "edited()")["field"] == "stack_mode"


def test_the_alt_targets_line_reads_the_pair_count_the_surface_published(
    browser: Browser,
):
    payload = state_payload("extractor")
    parts = draw_tab(browser, payload)
    count = len(payload["alt_targets"]["pairs"])
    assert str(count) in named(parts, "alt-targets-line", "alt_info_lbl")["text"]
    assert named(parts, "alt-targets-line", "alt_list_lbl")["text"] == payload[
        "alt_targets"
    ]["join"].join(payload["alt_targets"]["pairs"])


def test_an_empty_alt_targets_list_reads_the_auto_scan_line(browser: Browser):
    payload = state_payload("auto_scan")
    parts = draw_tab(browser, payload)
    assert (
        named(parts, "alt-targets-line", "alt_info_lbl")["text"]
        == payload["alt_targets"]["empty_text"]
    )


def test_each_message_box_draws_the_title_and_the_text_the_surface_carries(
    browser: Browser,
):
    payload = state_payload("destruct_dispatched")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "message-box")
    assert len(drawn) == len(payload["boxes"])
    for one, box in zip(drawn, payload["boxes"]):
        assert one["attrs"]["data-icon"] == box["icon"]
        assert box["title"] in one["whole"]
        assert box["text"] in one["whole"]


def test_each_prompt_draws_the_title_and_the_question_the_surface_carries(
    browser: Browser,
):
    payload = state_payload("destruct_dispatched")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "prompt")
    assert len(drawn) == len(payload["prompts"])
    for one, prompt in zip(drawn, payload["prompts"]):
        assert prompt[0] in one["whole"]
        assert prompt[1] in one["whole"]


def test_the_tab_refuses_markup_a_hostile_row_label_carries(browser: Browser):
    payload = state_payload("hot")
    payload["rows"][0][1] = MARKUP_NAME
    parts = draw_tab(browser, payload)
    drawn = named(parts, "row-label", payload["rows"][0][2])
    assert drawn["text"] == MARKUP_NAME
    assert "<b>" not in drawn["html"]


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    draw_tab(browser, state_payload("hot"))
    browser.js("window.HOST.firstChild.innerHTML += " + json.dumps(MARKUP_NAME) + ";")
    assert "<b>" in browser.js("window.HOST.firstChild.innerHTML")


def test_the_tab_declares_its_own_spacing_and_leaves_the_form_to_the_host(
    browser: Browser,
):
    payload = state_payload("hot")
    parts = draw_tab(browser, payload)
    tab = with_part(parts, "live-settings-tab")[0]
    assert tab["attrs"]["data-configured-by-host"] == json.dumps(
        payload["forms"]["configured_by_host"]
    )
    assert tab["attrs"]["data-margins-set"] == json.dumps(
        payload["container"]["margins_set"]
    )
    assert tab["style"]["gap"] == str(payload["container"]["spacing_px"]) + "px"
