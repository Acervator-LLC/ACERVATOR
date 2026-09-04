"""The React bot creation wizard, against bot_wizard_surface.py."""

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

from src.gui.main_tabs import bot_wizard_surface as surface
from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "bot_wizard.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorBotWizard."
SETTER = "acervatorSetBotWizard"

#: SHARED_MODULES are the pieces the page loads beside this one.
SHARED_MODULES = (WEB / "table_cells.js", WEB / "header_strip.js")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 3
HOST_WIDTH_PX = 1200
HOST_HEIGHT_PX = 800

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

EXCHANGES = [
    {"exchange_id": "coinbase", "display_name": "Coinbase"},
    {"exchange_id": "kraken", "display_name": "Kraken"},
]

MARKETS = {
    "coinbase": [
        {
            "symbol": "BTC/USDT",
            "base": "BTC",
            "quote": "USDT",
            "volume": 2.5e9,
            "volatility": 3.5,
        },
        {
            "symbol": "ETH/USDT",
            "base": "ETH",
            "quote": "USDT",
            "volume": 1.5e6,
            "volatility": 1.25,
        },
        {
            "symbol": "SOL/BTC",
            "base": "SOL",
            "quote": "BTC",
            "volume": 4.0e3,
            "volatility": 0.0,
        },
        {
            "symbol": "LINK/BTC",
            "base": "LINK",
            "quote": "BTC",
            "volume": 0.0,
            "volatility": 0.0,
        },
    ],
    "kraken": [
        {
            "symbol": "XRP/USDT",
            "base": "XRP",
            "quote": "USDT",
            "volume": 9.0e5,
            "volatility": 2.0,
        }
    ],
}

DESCRIPTIONS = {"BTC": "The first chain.", "ETH": "The second chain."}

TIMEFRAMES = {"coinbase": ["1m", "5m", "15m", "1h", "1d"], "kraken": ["1m", "1h"]}


def request(**rest: Any) -> dict:
    """One bot_wizard.state request, from the values a case names."""
    found = {
        "exchanges": EXCHANGES,
        "defaults": {},
        "markets": MARKETS,
        "timeframes": TIMEFRAMES,
        "descriptions": DESCRIPTIONS,
    }
    found.update(rest)
    return found


STATES: dict = {
    "mode": [request()],
    "asset": [request(walk=[["next"]])],
    "params": [request(walk=[["next"], ["next"]])],
    "phantom": [request(walk=[["next"], ["next"], ["next"]])],
    "extractor_pool": [request(mode="extractor", walk=[["next"]])],
    "extractor_params": [request(mode="extractor", walk=[["next"], ["next"]])],
    "typed": [
        request(
            numbers={"target_balance": 4321.5, "stack_count": 7},
            checks={"phantom_enable": True, "detonation_enabled": True},
            texts={"profit_route_bot_id": "bot-a"},
            combo_indexes={"base": 2},
            walk=[["next"], ["next"]],
        )
    ],
    "picked_alts": [
        request(
            mode="extractor",
            combo_indexes={"pool_base": 0},
            alt_checks={0: True},
            walk=[["next"]],
        )
    ],
    "refused": [
        request(
            checks={"phantom_enable": True},
            phantom_timeframes={"1h": True, "5m": True},
            exchange_id="coinbase",
            walk=[["next"], ["next"], ["next"], ["next", [False, "too many"], False]],
        )
    ],
    "cancelled": [request(walk=[["next"], ["cancel"]])],
    "finished": [request(mode="extractor", walk=[["next"], ["next"], ["finish"]])],
    "bare": [{"exchanges": [], "defaults": {}, "markets": {}}],
}

STATE_NAMES = sorted(STATES)


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def build(steps: list) -> dict:
    """One payload, each step driving the same wizard in the order given."""
    found: dict = {}
    for step in steps:
        found = surface.view_model(step)
    return as_json(found)


def state_payload(name: str) -> dict:
    return build(STATES[name])


def token_payload() -> dict:
    return as_json(dss.view_model({}))


class JsRuntime(JsEngine):
    """A QJSEngine holding the wizard and the merged pieces it calls."""

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


# The whole payload, both directions, both counts


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    """The surface publishes a field the module never declared."""
    payload = state_payload(state)
    js.push(payload)
    declared = set(declared_fields(js))
    missing = sorted(set(payload) - declared)
    assert missing == [], (state, missing)


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_module_declares_reaches_the_payload(js: JsRuntime, state: str):
    """The module declares a field the surface never publishes."""
    payload = state_payload(state)
    js.push(payload)
    extra = sorted(set(declared_fields(js)) - set(payload))
    assert extra == [], (state, extra)


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    """A field the module never declared is counted as declared."""
    payload = state_payload("mode")
    payload["a_field_nobody_declared"] = True
    js.push(payload)
    declared = set(declared_fields(js))
    assert "a_field_nobody_declared" not in declared


def test_the_whole_payload_check_names_a_field_only_the_module_declares(
    js: JsRuntime,
):
    """A field the payload dropped still reports as held."""
    payload = state_payload("mode")
    del payload["skin"]
    found = js.push(payload)
    kinds = [one["fault"] for one in found["faults"] if one["field"] == "skin"]
    assert "missing" in kinds, found["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    """A count the module reports is one number for two different things."""
    payload = state_payload(state)
    found = js.push(payload)
    assert found["declared"] == found["held"], (state, found)
    assert found["declared"]["fields"] == len(payload), state
    assert found["declared"]["pages"] == len(payload["pages"]["names"]), state
    assert found["declared"]["groups"] == len(payload["groups"]["rows"]), state
    assert found["declared"]["timeframes"] == len(
        payload["phantom_page"]["timeframes"]
    ), state


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    """A dropped field shortens both counts, so the two never disagree."""
    payload = state_payload("mode")
    del payload["layout"]
    found = js.push(payload)
    assert found["declared"]["fields"] > found["held"]["fields"], found


def test_a_dropped_group_shortens_the_held_group_count(js: JsRuntime):
    """A group the payload stopped naming still counts as held."""
    payload = state_payload("params")
    del payload["groups"]["titles"]["cb_group"]
    found = js.push(payload)
    assert found["declared"]["groups"] > found["held"]["groups"], found


def test_a_dropped_timeframe_shortens_the_held_timeframe_count(js: JsRuntime):
    """A timeframe the payload stopped naming still counts as held."""
    payload = state_payload("phantom")
    del payload["phantom_page"]["checked"]["1h"]
    found = js.push(payload)
    assert found["declared"]["timeframes"] > found["held"]["timeframes"], found


def test_an_unplaced_field_shortens_the_held_row_count(js: JsRuntime):
    """A field nobody laid out still counts as a placed row."""
    payload = state_payload("params")
    payload["groups"]["rows"]["cb_group"] = []
    found = js.push(payload)
    assert found["declared"]["rows"] > found["held"]["rows"], found


# Both sides agree by value and by type


def python_kinds(payload: dict) -> dict:
    """The type of every value in the payload, by its dotted path."""
    found: dict = {}

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                path = f"{prefix}.{name}" if prefix else str(name)
                found[path] = JS_TYPE_OF[type(value).__name__]
                walk(path, value)
        elif isinstance(node, list):
            for at, value in enumerate(node):
                path = f"{prefix}.{at}"
                found[path] = JS_TYPE_OF[type(value).__name__]
                walk(path, value)

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_of_every_state_arrives_as_the_type_it_left_as(
    js: JsRuntime, state: str
):
    """A value changes shape between the surface and the module."""
    payload = state_payload(state)
    js.push(payload)
    mine = python_kinds(payload)
    theirs = js.json(API + "kinds()")
    assert theirs == mine, state


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_of_every_state_arrives_with_the_value_it_left_with(
    js: JsRuntime, state: str
):
    """A value changes between the surface and the module."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "payload()") == payload, state


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    """A changed shape reaches the module unreported."""
    payload = state_payload("mode")
    mine = python_kinds(payload)
    payload["values"]["numbers"]["stack_count"] = "3"
    js.push(payload)
    theirs = js.json(API + "kinds()")
    assert theirs["values.numbers.stack_count"] == "string"
    assert mine["values.numbers.stack_count"] == "number"


def test_the_type_walk_names_a_scalar_where_a_group_row_list_belongs(js: JsRuntime):
    """A scalar where a list belongs slips past the type walk."""
    payload = state_payload("params")
    payload["groups"]["rows"]["cb_group"] = 5
    js.push(payload)
    theirs = js.json(API + "kinds()")
    assert theirs["groups.rows.cb_group"] == "number", theirs["groups.rows.cb_group"]


def test_the_type_walk_names_a_null_where_a_group_row_list_belongs(js: JsRuntime):
    """A null where a list belongs slips past the type walk."""
    payload = state_payload("params")
    payload["groups"]["rows"]["cb_group"] = None
    js.push(payload)
    assert js.json(API + "kinds()")["groups.rows.cb_group"] == "null"


def test_the_type_walk_names_a_scalar_where_an_alt_row_belongs(js: JsRuntime):
    """A scalar where an alt row belongs slips past the type walk."""
    payload = state_payload("picked_alts")
    payload["pool_page"]["alt_items"][0] = 7
    js.push(payload)
    assert js.json(API + "kinds()")["pool_page.alt_items.0"] == "number"


def not_plain_data(payload: Any) -> list:
    """Every path whose value is not a string, number, flag, list, bag or null."""
    found: list = []

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                path = f"{prefix}.{name}" if prefix else str(name)
                if type(value).__name__ not in JS_TYPE_OF:
                    found.append(path)
                walk(path, value)
        elif isinstance(node, list):
            for at, value in enumerate(node):
                path = f"{prefix}.{at}"
                if type(value).__name__ not in JS_TYPE_OF:
                    found.append(path)
                walk(path, value)

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_surface_publishes_no_live_object(state: str):
    """The surface hands a live object to the renderer."""
    payload = surface.view_model(STATES[state][-1])
    assert not_plain_data(payload) == [], state


def test_the_plain_data_check_names_a_live_object_put_on_the_payload():
    """A live object on the payload reads as plain data."""
    payload = surface.view_model(STATES["mode"][-1])
    payload["window"]["live"] = surface.BotWizardModel()
    assert not_plain_data(payload) == ["window.live"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    """The module holds a value the renderer cannot serialise."""
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == [], state


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    """A function bound onto the model reads as plain data."""
    js.push(state_payload("mode"))
    js.run(API + "payload();")
    js.run("acervatorBotWizard.bag('window').live = function () { return 1; };")
    found = js.json(API + "notPlainData()")
    assert found == [{"path": "window.live", "kind": "function"}], found


# No value literal in the JavaScript


def shown_values() -> set:
    """Every string the wizard paints or shows as hover text, every state."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        pages = payload["pages"]
        found |= set(pages["titles"].values())
        found |= set(pages["subtitles"].values())
        found |= set(payload["groups"]["titles"].values())
        fields = payload["fields"]
        for group in (
            "row_labels",
            "check_texts",
            "radio_texts",
            "button_texts",
            "label_texts",
            "tool_tips",
            "placeholders",
        ):
            found |= {one for one in fields[group].values() if isinstance(one, str)}
        for items in fields["combos"].values():
            found |= {one[0] for one in items if isinstance(one[0], str)}
        for spec in fields["numbers"].values():
            found |= {
                spec[key]
                for key in ("prefix", "suffix")
                if isinstance(spec.get(key), str)
            }
        asset = payload["asset_page"]
        pool = payload["pool_page"]
        found.add(asset["status"])
        found.add(asset["info_tool_tip"])
        found.add(pool["status"])
        found |= {one[0] for one in asset["target_items"]}
        found |= {one[0] for one in pool["alt_items"]}
        found |= {one[0] for one in asset["exchange_items"]}
        found |= set(payload["phantom_page"]["timeframes"])
        found |= {one for one in payload["phantom_page"]["tool_tips"].values() if one}
        found |= set(payload["walk"]["steps"])
        found.add(payload["window"]["title"])
        found.add(payload["window"]["accessible_name"])
        found.add(payload["window"]["accessible_description"])
        for box in (asset["info_box"], payload["phantom_page"]["warning_box"]):
            if box:
                found |= {one for one in box if isinstance(one, str)}
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
TOKEN_VALUES = token_values()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: NAMED_WORDS holds every published key the module may write, less any word painted.
NAMED_WORDS = (published_keys() | {surface.METHOD}) - SHOWN_VALUES


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a value the surface owns."""
    assert not MODULE_LITERALS["numbers"], (
        "bot_wizard.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    """A colour typed here is a second source for a colour the surface owns."""
    carried = HEX_COLOUR.findall(MODULE_SOURCE)
    assert carried == [], carried


def test_no_string_in_the_module_equals_a_value_the_wizard_shows():
    """A string the module writes is a value the operator reads on the screen."""
    shared = sorted(set(MODULE_LITERALS["strings"]) & SHOWN_VALUES)
    assert shared == [], shared


def test_no_string_in_the_module_equals_a_design_token_value():
    """A string the module writes is a design token value."""
    shared = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert shared == [], shared


def test_every_named_word_is_a_name_and_not_a_value_the_wizard_shows():
    """A word the module is allowed to write is a value the wizard paints."""
    assert sorted(NAMED_WORDS & SHOWN_VALUES) == []


def test_the_module_hides_no_value_behind_a_regular_expression():
    """A slash outside a comment could hide a value the scan never reads."""
    assert MODULE_LITERALS["slashes"] == [], MODULE_LITERALS["slashes"]


WRITTEN_KINDS = ("number", "colour", "shown", "token")


def written_line(kind: str) -> str:
    """One line carrying a value of ``kind``, for the file to be scanned with."""
    if kind == "shown":
        return "\nvar WRITTEN = " + json.dumps(sorted(SHOWN_VALUES)[0]) + ";\n"
    if kind == "token":
        return "\nvar WRITTEN = " + json.dumps(sorted(TOKEN_VALUES)[0]) + ";\n"
    if kind == "colour":
        return '\nvar WRITTEN_COLOUR = "#abcdef";\n'
    return "\nvar WRITTEN_NUMBER = 12345;\n"


def caught_by_scan(source: str) -> set:
    """Every value the scan reports for one source body."""
    found = js_literals(source)
    caught = set(found["numbers"]) | set(found["strings"])
    caught |= set(HEX_COLOUR.findall(source))
    return caught


@pytest.mark.parametrize("kind", sorted(WRITTEN_KINDS))
def test_the_literal_scan_names_one_written_line(kind: str):
    """The scan reads past a value written into a module body."""
    line = written_line(kind)
    caught = caught_by_scan(MODULE_SOURCE + line)
    assert caught - caught_by_scan(MODULE_SOURCE), kind


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    """The scan reports a colour that only a comment carries."""
    body = MODULE_SOURCE + "\n// " + SWAPPED_ALPHA + "\n"
    assert not set(js_literals(body)["strings"]) & {SWAPPED_ALPHA}


@pytest.mark.parametrize("kind", sorted(WRITTEN_KINDS))
def test_each_written_literal_is_caught_in_the_module_file_itself(kind: str):
    """A value written into the shipped file is not caught by the real scan."""
    original = MODULE_PATH.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    line = written_line(kind)
    try:
        swap_module(MODULE_PATH, original + line.encode("utf-8"))
        source = MODULE_PATH.read_text(encoding="utf-8")
        caught = caught_by_scan(source)
    finally:
        swap_module(MODULE_PATH, original)
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before
    assert caught - caught_by_scan(MODULE_SOURCE), kind


def test_the_written_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    """The restored module no longer runs, so the scan above proved nothing."""
    assert js.json(API + "method") == surface.METHOD
    assert MODULE_PATH.read_text(encoding="utf-8") == MODULE_SOURCE


# Colours, including the sub-blocks a base walk skips


def payload_colours(payload: dict) -> list:
    """Every colour the payload carries, sheets included."""
    found = [payload["info_button_color"]]
    found += list(payload["skin"].values())
    found += HEX_COLOUR.findall(payload["asset_page"]["info_button_style"])
    found += [payload["icon"]["text_color"]]
    return [one for one in found if isinstance(one, str)]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_the_wizard_carries_is_swept_for_the_alpha_order_fault(
    js: JsRuntime, state: str
):
    """A colour the wizard carries is never swept for the alpha-order fault."""
    payload = state_payload(state)
    found = js.push(payload)
    swapped = [one for one in found["faults"] if one["fault"] == "swapped-alpha"]
    assert swapped == [], (state, swapped)
    assert payload_colours(payload), state


def test_the_alpha_sweep_names_one_colour_written_with_eight_digits(js: JsRuntime):
    """A colour written with eight hex digits is swept without report."""
    payload = state_payload("mode")
    payload["skin"]["info_button"] = SWAPPED_ALPHA
    found = js.push(payload)
    swapped = [one for one in found["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["field"] for one in swapped] == ["info_button"], found["faults"]


def test_the_alpha_sweep_reads_a_colour_inside_the_info_button_sheet(js: JsRuntime):
    """A colour inside a style sheet is never read by the sweep."""
    payload = state_payload("mode")
    payload["asset_page"]["info_button_style"] = "color: " + SWAPPED_ALPHA + ";"
    found = js.push(payload)
    swapped = [one for one in found["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["field"] for one in swapped] == ["color"], found["faults"]


def test_the_alpha_sweep_reads_a_colour_inside_a_hover_sub_block(js: JsRuntime):
    """A colour inside a hover sub-block is never entered by the sweep."""
    payload = state_payload("mode")
    payload["asset_page"]["info_button_style"] = (
        "color: "
        + OTHER_COLOUR
        + "; } QPushButton:hover { color: "
        + SWAPPED_ALPHA
        + ";"
    )
    found = js.push(payload)
    swapped = [one for one in found["faults"] if one["fault"] == "swapped-alpha"]
    assert len(swapped) == 1, found["faults"]
    assert swapped[0]["detail"] == SWAPPED_ALPHA, swapped


def test_the_alpha_sweep_reads_a_colour_inside_a_disabled_sub_block(js: JsRuntime):
    """A colour inside a disabled sub-block is never entered by the sweep."""
    payload = state_payload("mode")
    payload["asset_page"]["info_button_style"] = (
        "color: "
        + OTHER_COLOUR
        + "; } QPushButton:disabled { border-color: "
        + SWAPPED_ALPHA
        + ";"
    )
    found = js.push(payload)
    swapped = [one for one in found["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["field"] for one in swapped] == ["border-color"], found["faults"]


def test_the_sub_block_sweep_is_quiet_on_a_healthy_hover_colour(js: JsRuntime):
    """The sub-block sweep reports every colour it reads, healthy or not."""
    payload = state_payload("mode")
    payload["asset_page"]["info_button_style"] = (
        "color: "
        + OTHER_COLOUR
        + "; } QPushButton:hover { color: "
        + OTHER_COLOUR
        + ";"
    )
    found = js.push(payload)
    swapped = [one for one in found["faults"] if one["fault"] == "swapped-alpha"]
    assert swapped == [], found["faults"]


def test_the_sub_block_walk_reaches_more_declarations_than_the_base_walk(js: JsRuntime):
    """The sub-block walk reads the same declarations as the base walk."""
    js.push(state_payload("mode"))
    sheet = json.dumps("color: a; } X:hover { color: b; }")
    base = js.json(API + "declarations(" + sheet + ").length")
    swept = js.json(API + "sweptDeclarations(" + sheet + ").length")
    assert swept > base, (base, swept)


def test_no_declared_colour_has_three_equal_channels():
    """A colour whose channels are equal hides a channel swap."""
    for name, value in surface.SKIN.items():
        channels = [value[at : at + 2] for at in (1, 3, 5)]
        assert len(set(channels)) > 1, (name, value)


# Bag order and identity by name


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_bag_the_surface_publishes_carries_a_key_a_browser_would_move(
    js: JsRuntime, state: str
):
    """A digit-first key a browser lists first reaches a published bag."""
    found = js.push(state_payload(state))
    moved = [one for one in found["faults"] if one["fault"] == "reordered-key"]
    assert moved == [], (state, moved)


def test_the_bag_order_check_names_a_digit_key_put_into_a_published_bag(js: JsRuntime):
    """A digit-first key put into a bag is not reported."""
    payload = state_payload("mode")
    payload["skin"]["1_first"] = OTHER_COLOUR
    found = js.push(payload)
    moved = [one for one in found["faults"] if one["fault"] == "reordered-key"]
    assert [one["field"] for one in moved] == ["1_first"], found["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_page_order_is_read_from_a_list_and_never_from_a_bag(
    js: JsRuntime, state: str
):
    """The page order is read from a bag whose key order a browser may move."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "pageNames()") == payload["pages"]["names"], state


def test_the_page_order_check_would_see_the_pages_read_in_another_order(
    js: JsRuntime,
):
    """The page order is the same whatever list the payload carries."""
    payload = state_payload("mode")
    payload["pages"]["names"] = list(reversed(payload["pages"]["names"]))
    js.push(payload)
    assert js.json(API + "pageNames()") == payload["pages"]["names"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_group_is_read_by_its_own_name_and_not_by_its_place(
    js: JsRuntime, state: str
):
    """A group's rows are read by position rather than by the group's name."""
    payload = state_payload(state)
    js.push(payload)
    for name, rows in payload["groups"]["rows"].items():
        assert js.json(API + "groupRows(" + json.dumps(name) + ")") == rows, name


def test_the_group_reader_would_mislabel_two_groups_if_it_counted_places(
    js: JsRuntime,
):
    """The group rows survive two groups whose rows were swapped by name."""
    payload = state_payload("params")
    rows = payload["groups"]["rows"]
    rows["cb_group"], rows["risk_group"] = rows["risk_group"], rows["cb_group"]
    js.push(payload)
    assert js.json(API + 'groupRows("cb_group")') == rows["cb_group"]
    assert js.json(API + 'groupRows("risk_group")') == rows["risk_group"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_timeframe_is_found_by_its_own_name(js: JsRuntime, state: str):
    """A phantom timeframe is read by its place in the served list."""
    payload = state_payload(state)
    js.push(payload)
    for name in payload["phantom_page"]["timeframes"]:
        quoted = json.dumps(name)
        assert (
            js.json(API + "timeframeChecked(" + quoted + ")")
            is payload["phantom_page"]["checked"][name]
        ), name
        assert (
            js.json(API + "timeframeEnabled(" + quoted + ")")
            is payload["phantom_page"]["enabled"][name]
        ), name


def test_the_timeframe_check_would_see_two_timeframes_swapped_by_name(js: JsRuntime):
    """The timeframe check would answer the same for two swapped names."""
    payload = state_payload("phantom")
    payload["phantom_page"]["enabled"]["1h"] = False
    payload["phantom_page"]["enabled"]["1d"] = True
    js.push(payload)
    assert js.json(API + 'timeframeEnabled("1h")') is False
    assert js.json(API + 'timeframeEnabled("1d")') is True


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_is_read_by_its_own_name_with_its_own_kind(
    js: JsRuntime, state: str
):
    """A field's kind is read from a place rather than from its own name."""
    payload = state_payload(state)
    js.push(payload)
    for kind in ("numbers", "checks", "radios", "combos", "texts"):
        for name in payload["fields"][kind]:
            found = js.json(API + "fieldKind(" + json.dumps(name) + ")")
            assert found == kind, (name, found, kind)


def test_the_field_kind_reader_names_no_kind_for_a_field_nobody_declared(
    js: JsRuntime,
):
    """The field kind is answered for a name no field carries."""
    js.push(state_payload("mode"))
    assert js.json(API + 'fieldKind("no_such_field")') is None


# The layout the payload publishes covers every field


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_reaches_one_group_or_one_page_exactly_once(
    js: JsRuntime, state: str
):
    """A field the payload carries reaches no row, or reaches two."""
    found = js.push(state_payload(state))
    stray = [
        one
        for one in found["faults"]
        if one["fault"] in ("unplaced", "duplicate") and one["field"] == "rows"
    ]
    assert stray == [], (state, stray)


def test_the_placement_check_names_a_field_no_row_lays_out(js: JsRuntime):
    """A field nobody laid out passes the placement check."""
    payload = state_payload("params")
    payload["groups"]["rows"]["cb_group"] = []
    found = js.push(payload)
    unplaced = [one for one in found["faults"] if one["fault"] == "unplaced"]
    assert len(unplaced) == 6, found["faults"]


def test_the_placement_check_names_a_field_two_rows_lay_out(js: JsRuntime):
    """A field laid out twice passes the placement check."""
    payload = state_payload("params")
    payload["groups"]["rows"]["risk_group"].append("cb_soft_pct")
    found = js.push(payload)
    twice = [one for one in found["faults"] if one["fault"] == "duplicate"]
    assert [one["where"] for one in twice] == ["field:cb_soft_pct"], found["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_group_a_page_names_is_a_group_the_payload_lays_out(
    js: JsRuntime, state: str
):
    """A page names a group the payload never lays out."""
    found = js.push(state_payload(state))
    unknown = [
        one
        for one in found["faults"]
        if one["fault"] == "unknown-action" and one["where"].startswith("page:")
    ]
    assert unknown == [], (state, unknown)


def test_the_group_name_check_names_a_group_no_page_lays_out(js: JsRuntime):
    """A page naming a group nobody lays out passes the check."""
    payload = state_payload("params")
    payload["pages"]["groups"]["params"].append("no_such_group")
    found = js.push(payload)
    unknown = [one for one in found["faults"] if one["fault"] == "unknown-action"]
    assert [one["field"] for one in unknown] == ["no_such_group"], found["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_page_the_module_reads_is_a_page_the_payload_names(
    js: JsRuntime, state: str
):
    """The module reads a page name the payload never names."""
    payload = state_payload(state)
    found = js.push(payload)
    missing = [
        one
        for one in found["faults"]
        if one["field"] == "names" and one["fault"] == "missing"
    ]
    assert missing == [], (state, missing)
    assert sorted(js.json(API + "pageNamesRead()")) == sorted(
        payload["pages"]["names"]
    ), state


def test_the_page_name_check_names_a_page_the_payload_stopped_naming(js: JsRuntime):
    """A page the payload stopped naming still reads as present."""
    payload = state_payload("mode")
    payload["pages"]["names"] = [
        one for one in payload["pages"]["names"] if one != "folding"
    ]
    found = js.push(payload)
    missing = [
        one
        for one in found["faults"]
        if one["field"] == "names" and one["fault"] == "missing"
    ]
    assert [one["where"] for one in missing] == ["page:folding"], found["faults"]


# Every value the payload holds pairs with a field it declares


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_declared_field_carries_a_value_and_no_value_is_orphaned(
    js: JsRuntime, state: str
):
    """A value reaches the payload for a field it never declared."""
    found = js.push(state_payload(state))
    stray = [
        one
        for one in found["faults"]
        if one["where"].startswith("field:")
        and one["fault"] in ("missing", "unknown-action")
    ]
    assert stray == [], (state, stray)


def test_the_value_check_names_a_field_whose_value_the_payload_dropped(js: JsRuntime):
    """A field whose value went missing still reads as carried."""
    payload = state_payload("mode")
    del payload["values"]["numbers"]["stack_count"]
    found = js.push(payload)
    missing = [one for one in found["faults"] if one["where"] == "field:stack_count"]
    assert [one["fault"] for one in missing] == ["missing"], found["faults"]


def test_the_value_check_names_a_value_no_field_declares(js: JsRuntime):
    """A value for a field nobody declared reads as declared."""
    payload = state_payload("mode")
    payload["values"]["numbers"]["no_such_number"] = 1.0
    found = js.push(payload)
    unknown = [one for one in found["faults"] if one["where"] == "field:no_such_number"]
    assert [one["fault"] for one in unknown] == ["unknown-action"], found["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_number_sits_inside_its_own_lowest_and_highest_value(
    js: JsRuntime, state: str
):
    """A number outside its own range reaches the screen unreported."""
    found = js.push(state_payload(state))
    outside = [one for one in found["faults"] if one["fault"] == "out-of-range"]
    assert outside == [], (state, outside)


def test_the_range_check_names_a_number_above_its_own_highest_value(js: JsRuntime):
    """A number above its own ceiling passes the range check."""
    payload = state_payload("mode")
    payload["values"]["numbers"]["stack_count"] = 999.0
    found = js.push(payload)
    outside = [one for one in found["faults"] if one["fault"] == "out-of-range"]
    assert [one["where"] for one in outside] == ["field:stack_count"], found["faults"]


def test_the_range_check_names_a_number_below_its_own_lowest_value(js: JsRuntime):
    """A number below its own floor passes the range check."""
    payload = state_payload("mode")
    payload["values"]["numbers"]["target_balance"] = -1.0
    found = js.push(payload)
    outside = [one for one in found["faults"] if one["fault"] == "out-of-range"]
    assert [one["where"] for one in outside] == ["field:target_balance"], found[
        "faults"
    ]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_number_sits_on_a_step_its_own_field_can_reach(js: JsRuntime, state: str):
    """A number the field's own step cannot reach is drawn unreported."""
    found = js.push(state_payload(state))
    off = [one for one in found["faults"] if one["fault"] == "off-step"]
    assert off == [], (state, off)


def test_the_step_check_names_a_number_between_two_steps(js: JsRuntime):
    """A number sitting between two steps passes the step check."""
    payload = state_payload("mode")
    payload["values"]["numbers"]["trading_fee"] = 0.62
    found = js.push(payload)
    off = [one for one in found["faults"] if one["fault"] == "off-step"]
    assert [one["where"] for one in off] == ["field:trading_fee"], found["faults"]


# Markup, measured by the width a widget asks for


def text_width(widget: Any) -> int:
    """The width one widget's own text needs in the font it will paint with."""
    from PySide6.QtGui import QFontMetrics

    return QFontMetrics(widget.font()).horizontalAdvance(widget.text())


def a_label(body: str) -> Any:
    from PySide6.QtWidgets import QLabel

    return QLabel(body)


def a_message_box(body: str) -> Any:
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox()
    box.setText(body)
    return box


def a_button(body: str) -> Any:
    from PySide6.QtWidgets import QPushButton

    return QPushButton(body)


def a_check(body: str) -> Any:
    from PySide6.QtWidgets import QCheckBox

    return QCheckBox(body)


def a_radio(body: str) -> Any:
    from PySide6.QtWidgets import QRadioButton

    return QRadioButton(body)


def a_group(body: str) -> Any:
    from PySide6.QtWidgets import QGroupBox

    return QGroupBox(body)


def a_combo(body: str) -> Any:
    from PySide6.QtWidgets import QComboBox

    combo = QComboBox()
    combo.addItem(body)
    return combo


def a_line(body: str) -> Any:
    from PySide6.QtWidgets import QLineEdit

    return QLineEdit(body)


def a_spin(body: str) -> Any:
    from PySide6.QtWidgets import QSpinBox

    spin = QSpinBox()
    spin.setPrefix(body)
    return spin


PLAIN_WIDGETS = {
    "QPushButton": a_button,
    "QCheckBox": a_check,
    "QRadioButton": a_radio,
    "QComboBox": a_combo,
    "QSpinBox": a_spin,
}

#: A QLineEdit asks one width whatever text it holds, so its painting is measured.
PAINTED_WIDGETS = {"QLineEdit": a_line}

RICH_WIDGETS = {"QLabel": a_label, "QMessageBox": a_message_box}

MARKED = "one <b>two</b> three"
UNMARKED = "one bbtwobb three"

#: EATEN is what a rich-text painter shows once it swallows the two tags.
EATEN = "one two three"


def asked_width(widget: Any) -> int:
    """The width one widget asks for, which is what its own painting needs."""
    from PySide6.QtWidgets import QComboBox, QMessageBox

    if isinstance(widget, QMessageBox):
        return widget.sizeHint().width()
    if isinstance(widget, QComboBox):
        return widget.sizeHint().width()
    return widget.sizeHint().width()


@pytest.mark.parametrize("kind", sorted(PLAIN_WIDGETS))
def test_no_plain_widget_this_wizard_uses_reads_its_caller_text_as_markup(
    qapp, kind: str
):
    """A widget this wizard uses reads its caller text as rich text."""
    assert qapp is not None
    marked = asked_width(PLAIN_WIDGETS[kind](MARKED))
    unmarked = asked_width(PLAIN_WIDGETS[kind](UNMARKED))
    assert marked > unmarked, (kind, marked, unmarked)


@pytest.mark.parametrize("kind", sorted(RICH_WIDGETS))
def test_the_widgets_this_wizard_uses_that_do_read_markup_are_named(qapp, kind: str):
    """A widget named as reading markup does not read it."""
    assert qapp is not None
    marked = asked_width(RICH_WIDGETS[kind](MARKED))
    unmarked = asked_width(RICH_WIDGETS[kind](UNMARKED))
    assert marked < unmarked, (kind, marked, unmarked)


def test_the_markup_measurement_reads_a_longer_text_as_a_different_painting(qapp):
    """The width measurement answers the same for two different texts."""
    assert qapp is not None
    short = asked_width(a_button(UNMARKED))
    long_one = asked_width(a_button(UNMARKED + UNMARKED))
    assert long_one > short, (short, long_one)


def test_a_marked_label_asks_for_less_width_than_the_characters_it_holds(qapp):
    """A rich-text label asks for the width every character it holds needs."""
    assert qapp is not None
    assert asked_width(a_label(MARKED)) < text_width(a_label(MARKED))


@pytest.mark.parametrize(
    "text_name",
    ["extractor_description", "scrumming_description"],
)
def test_the_wizard_descriptions_are_drawn_as_characters_by_qt_today(
    qapp, text_name: str
):
    """Qt reads one of the wizard's own descriptions as rich text."""
    from PySide6.QtCore import Qt

    assert qapp is not None
    body = surface.LABEL_TEXTS[text_name]
    auto = a_label(body)
    plain = a_label(body)
    plain.setTextFormat(Qt.TextFormat.PlainText)
    assert auto.sizeHint().width() == plain.sizeHint().width(), text_name


def test_the_description_measurement_would_see_the_same_words_read_as_markup(qapp):
    """The description measurement cannot tell rich text from plain text."""
    from PySide6.QtCore import Qt

    assert qapp is not None
    body = surface.LABEL_TEXTS["extractor_description"]
    plain = a_label(body)
    plain.setTextFormat(Qt.TextFormat.PlainText)
    rich = a_label(body)
    rich.setTextFormat(Qt.TextFormat.RichText)
    assert rich.sizeHint().width() < plain.sizeHint().width()


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_every_caller_text_carrying_a_mark(
    js: JsRuntime, state: str
):
    """Text carrying a mark a rich-text painter would eat is not reported."""
    payload = state_payload(state)
    found = js.push(payload)
    marked = {one["field"] for one in found["faults"] if one["fault"] == "markup"}
    assert marked == {"extractor_description", "extractor", "ext_scan_top_n"}, marked


def test_the_markup_report_names_a_tag_a_hostile_description_carries(js: JsRuntime):
    """Markup arriving in an asset description is not reported."""
    payload = state_payload("mode")
    payload["fields"]["label_texts"]["alt_list_heading"] = MARKUP_NAME
    found = js.push(payload)
    marked = {one["field"] for one in found["faults"] if one["fault"] == "markup"}
    assert "alt_list_heading" in marked, found["faults"]


def test_the_markup_report_is_quiet_on_a_line_carrying_no_mark(js: JsRuntime):
    """The markup report names text that carries no mark at all."""
    payload = state_payload("mode")
    payload["fields"]["label_texts"]["alt_list_heading"] = UNMARKED
    found = js.push(payload)
    marked = {one["field"] for one in found["faults"] if one["fault"] == "markup"}
    assert "alt_list_heading" not in marked, found["faults"]


# Hostile payloads


HOSTILE_NUMBERS = {
    "ten_to_the_twenty_four": 10**24,
    "below_the_floor": -1.0,
    "above_the_ceiling": 10**9,
    "off_the_step": 0.62,
    "text_where_a_number_belongs": "12.7",
    "nothing_where_a_number_belongs": None,
}

#: JSON carries no name for these three numbers, so none crosses the bridge.
UNSERIALISABLE = {
    "not_a_number": float("nan"),
    "plus_infinity": float("inf"),
    "minus_infinity": float("-inf"),
}

HOSTILE_TEXTS = {
    "a_number_where_text_belongs": 12,
    "a_long_name": LONG_NAME,
    "markup": MARKUP_NAME,
    "a_newline": NEWLINE_NAME,
    "nothing": None,
}

TOP_FIELDS = sorted(surface.build_view_model(EXCHANGES, {}, MARKETS))


def still_answers(js: JsRuntime, case: str) -> None:
    """The module still answers for its own method and payload."""
    assert js.json(API + "method") == surface.METHOD, case
    assert isinstance(js.json(API + "payload()"), dict), case
    assert isinstance(js.json(API + "faults()"), list), case


@pytest.mark.parametrize("name", TOP_FIELDS)
def test_a_field_the_payload_drops_is_reported_and_the_module_answers_on(
    js: JsRuntime, name: str
):
    """A dropped field stops the module answering at all."""
    payload = state_payload("params")
    del payload[name]
    found = js.push(payload)
    still_answers(js, name)
    assert any(one["field"] == name for one in found["faults"]), (name, found["faults"])


@pytest.mark.parametrize("name", TOP_FIELDS)
def test_a_field_the_payload_nulls_is_reported_and_the_module_answers_on(
    js: JsRuntime, name: str
):
    """A nulled field stops the module answering at all."""
    payload = state_payload("params")
    payload[name] = None
    js.push(payload)
    still_answers(js, name)


def test_the_missing_field_sweep_names_every_field_it_removed(js: JsRuntime):
    """The sweep above removes nothing, so its green says nothing."""
    payload = state_payload("params")
    for name in TOP_FIELDS:
        short = dict(payload)
        del short[name]
        assert name not in short, name
    assert len(TOP_FIELDS) == len(payload), (len(TOP_FIELDS), len(payload))


@pytest.mark.parametrize("case", sorted(HOSTILE_NUMBERS))
def test_a_hostile_number_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """A hostile number stops the module answering at all."""
    payload = state_payload("params")
    payload["values"]["numbers"]["trading_fee"] = HOSTILE_NUMBERS[case]
    js.push(as_json(payload) if case != "not_a_number" else payload)
    still_answers(js, case)


@pytest.mark.parametrize("case", sorted(HOSTILE_TEXTS))
def test_a_hostile_row_label_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """A hostile row label stops the module answering at all."""
    payload = state_payload("params")
    payload["fields"]["row_labels"]["trading_fee"] = HOSTILE_TEXTS[case]
    js.push(payload)
    still_answers(js, case)
    assert js.json(API + 'rowLabel("trading_fee")') == HOSTILE_TEXTS[case], case


def test_a_scalar_where_the_whole_group_row_list_belongs_draws_no_row_at_all(
    js: JsRuntime,
):
    """A scalar where a row list belongs stops the module answering."""
    payload = state_payload("params")
    payload["groups"]["rows"]["cb_group"] = 5
    js.push(payload)
    still_answers(js, "scalar")
    assert js.json(API + 'groupRows("cb_group")') == []


def test_a_null_where_the_whole_group_row_list_belongs_draws_no_row_at_all(
    js: JsRuntime,
):
    """A null where a row list belongs stops the module answering."""
    payload = state_payload("params")
    payload["groups"]["rows"]["cb_group"] = None
    js.push(payload)
    still_answers(js, "null")
    assert js.json(API + 'groupRows("cb_group")') == []


def test_a_scalar_where_the_whole_alt_list_belongs_draws_no_alt_at_all(js: JsRuntime):
    """A scalar where the alt list belongs stops the module answering."""
    payload = state_payload("picked_alts")
    payload["pool_page"]["alt_items"] = 5
    js.push(payload)
    still_answers(js, "scalar")
    assert js.json(API + "altItems()") == []


def test_a_scalar_where_the_whole_timeframe_list_belongs_draws_none_at_all(
    js: JsRuntime,
):
    """A scalar where the timeframe list belongs stops the module answering."""
    payload = state_payload("phantom")
    payload["phantom_page"]["timeframes"] = 5
    js.push(payload)
    still_answers(js, "scalar")
    assert js.json(API + "timeframeNames()") == []


def test_two_alts_naming_the_same_pair_are_both_kept_and_reported(js: JsRuntime):
    """Two alts naming one pair are silently merged into one row."""
    payload = state_payload("picked_alts")
    first = payload["pool_page"]["alt_items"][0]
    payload["pool_page"]["alt_items"] = [first, list(first)]
    payload["pool_page"]["alt_checked"] = [True, False]
    found = js.push(payload)
    assert len(js.json(API + "altItems()")) == 2
    twice = [one for one in found["faults"] if one["fault"] == "duplicate"]
    assert [one["where"] for one in twice] == ["alt:" + first[1]], found["faults"]


def test_an_alt_carrying_no_symbol_at_all_is_reported(js: JsRuntime):
    """An alt with no symbol reaches the pool config unreported."""
    payload = state_payload("picked_alts")
    payload["pool_page"]["alt_items"][0] = ["a label", ""]
    found = js.push(payload)
    unnamed = [one for one in found["faults"] if one["fault"] == "unnamed"]
    assert [one["field"] for one in unnamed] == ["alt_items"], found["faults"]


def test_the_alt_checks_report_a_tick_list_shorter_than_the_alt_list(js: JsRuntime):
    """A tick list shorter than the alt list pairs a tick with the wrong pair."""
    payload = state_payload("picked_alts")
    payload["pool_page"]["alt_checked"] = []
    found = js.push(payload)
    short = [one for one in found["faults"] if one["fault"] == "short-list"]
    assert [one["field"] for one in short] == ["alt_checked"], found["faults"]


def test_the_alt_tick_reader_answers_false_past_the_end_of_the_tick_list(
    js: JsRuntime,
):
    """A tick read past the end of the list answers something other than false."""
    payload = state_payload("picked_alts")
    payload["pool_page"]["alt_checked"] = []
    js.push(payload)
    assert js.json(API + "altChecked()") == []


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """The still-answering check passes on a module that answers nothing."""
    js.push(state_payload("mode"))
    js.run(API + "forget();")
    assert js.json(API + "payload()") == {}
    assert js.json(API + "isLoaded()") is False


def test_a_payload_that_is_not_an_object_at_all_is_reported(js: JsRuntime):
    """A payload that is not an object stops the module answering."""
    found = js.json(SETTER + "(5)")
    assert found["faults"][0]["fault"] == "not-an-object", found
    assert js.json(API + "isLoaded()") is False


# The rendered page


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
            "the page never defined the bot wizard module in "
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
    "whiteSpace",
    "borderTopWidth",
    "borderTopStyle",
    "borderTopColor",
    "borderTopLeftRadius",
    "paddingTop",
    "marginLeft",
    "maxWidth",
    "minWidth",
    "minHeight",
    "display",
    "flexDirection",
    "columnGap",
    "rowGap",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.setAttribute('data-part', 'bot-wizard-page');"
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
    "        min: el.min, max: el.max, step: el.step,"
    "        options: el.tagName === 'SELECT' ?"
    "          Array.prototype.map.call(el.options, function (o) {"
    "            return o.textContent; }) : null,"
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
    "  onNumber: function (n, v) { window.PRESSED.push(['number', n, v]); },"
    "  onFlag: function (n, v) { window.PRESSED.push(['flag', n, v]); },"
    "  onIndex: function (n, v) { window.PRESSED.push(['index', n, v]); },"
    "  onText: function (n, v) { window.PRESSED.push(['text', n, v]); },"
    "  onAlt: function (n, v) { window.PRESSED.push(['alt', n, v]); },"
    "  onTimeframe: function (n, v) { window.PRESSED.push(['timeframe', n, v]); },"
    "  onTarget: function (n) { window.PRESSED.push(['target', n]); },"
    "  onVenue: function (p, n) { window.PRESSED.push(['venue', p, n]); },"
    "  onInfo: function () { window.PRESSED.push(['info']); },"
    "  onSelectAll: function () { window.PRESSED.push(['select_all']); },"
    "  onClearAll: function () { window.PRESSED.push(['clear_all']); },"
    "  onWalk: function (n) { window.PRESSED.push(['walk', n]); } };"
)


def draw_wizard(browser: Browser, payload: dict) -> list:
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


def named(parts: list, part: str, name: str) -> list:
    return [
        one for one in with_part(parts, part) if one["attrs"].get("data-name") == name
    ]


def test_the_wizard_fills_the_named_space_the_window_left_for_it(browser: Browser):
    """The main window names one space and this wizard fills it."""
    parts = draw_wizard(browser, state_payload("mode"))
    assert browser.parsed(API + "spacePart") == "bot-wizard-page"
    assert at_path(parts, "bot-wizard"), "the wizard drew nothing into the space"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_child_the_page_draws_carries_its_own_name(browser: Browser, state: str):
    """A child is drawn that no check can name."""
    draw_wizard(browser, state_payload(state))
    every, parted = browser.parsed(COUNT_ELEMENTS)
    assert every == parted, (state, every, parted)


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    """The named-child check counts an unnamed child as named."""
    draw_wizard(browser, state_payload("mode"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('div'));")
    every, parted = browser.parsed(COUNT_ELEMENTS)
    assert every == parted + 1, (every, parted)


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_page_the_wizard_draws_is_the_page_the_surface_says_it_is_on(
    browser: Browser, state: str
):
    """The drawn page is not the page the surface says the wizard is on."""
    payload = state_payload(state)
    parts = draw_wizard(browser, payload)
    body = with_part(parts, "page-body")
    here = payload["pages"]["current"]
    assert [one["attrs"]["data-page"] for one in body] == [here], state


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_page_title_and_subtitle_are_the_words_the_surface_carries(
    browser: Browser, state: str
):
    """A page's own wording is not what the page draws."""
    payload = state_payload(state)
    parts = draw_wizard(browser, payload)
    here = payload["pages"]["current"]
    wanted = payload["pages"]["titles"][here]
    assert with_part(parts, "page-title")[0]["whole"] == wanted, state


def test_the_parameter_page_draws_the_subtitle_the_picked_mode_gives_it(
    browser: Browser,
):
    """The parameter page draws its stock subtitle whatever mode is picked."""
    payload = state_payload("extractor_params")
    parts = draw_wizard(browser, payload)
    drawn = with_part(parts, "page-subtitle")[0]["whole"]
    assert drawn == payload["groups"]["params_subtitle"]
    assert drawn == payload["groups"]["params_subtitle_extractor"]


def test_the_subtitle_check_would_see_the_scrumming_wording_instead(browser: Browser):
    """The subtitle check cannot tell the two modes' wording apart."""
    payload = state_payload("params")
    drawn = with_part(draw_wizard(browser, payload), "page-subtitle")[0]["whole"]
    assert drawn == payload["groups"]["params_subtitle_scrumming"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_page_reaches_the_rail_in_the_order_the_surface_names_them(
    browser: Browser, state: str
):
    """The page rail draws the pages in an order the surface never named."""
    payload = state_payload(state)
    parts = draw_wizard(browser, payload)
    stops = with_part(parts, "page-rail-stop")
    assert [one["attrs"]["data-name"] for one in stops] == payload["pages"]["names"]
    assert [one["whole"] for one in stops] == [
        payload["pages"]["titles"][one] for one in payload["pages"]["names"]
    ], state


def test_the_rail_marks_the_page_the_wizard_is_on_and_no_other(browser: Browser):
    """The rail marks a page other than the one the wizard is on."""
    payload = state_payload("phantom")
    parts = draw_wizard(browser, payload)
    stops = with_part(parts, "page-rail-stop")
    current = [
        one["attrs"]["data-name"]
        for one in stops
        if one["attrs"]["data-current"] == "true"
    ]
    assert current == [payload["pages"]["current"]], current


def test_every_group_the_parameter_page_names_is_drawn_in_that_order(
    browser: Browser,
):
    """The parameter page draws its groups in an order the surface never named."""
    payload = state_payload("params")
    parts = draw_wizard(browser, payload)
    groups = with_part(parts, "field-group")
    assert [one["attrs"]["data-group"] for one in groups] == payload["pages"]["groups"][
        "params"
    ]


def test_every_group_carries_the_title_the_surface_gives_it(browser: Browser):
    """A group draws a title the surface never gave it."""
    payload = state_payload("params")
    parts = draw_wizard(browser, payload)
    for one in with_part(parts, "field-group-title"):
        name = one["attrs"]["data-name"]
        assert one["whole"] == payload["groups"]["titles"][name], name


def test_a_group_the_surface_hides_is_drawn_hidden(browser: Browser):
    """A group the surface hides is drawn open."""
    payload = state_payload("params")
    parts = draw_wizard(browser, payload)
    for one in with_part(parts, "field-group"):
        name = one["attrs"]["data-group"]
        shown = payload["groups"]["visible"].get(name, True)
        assert one["attrs"]["data-shown"] == str(shown).lower(), name
        assert one["hidden"] is (not shown), name


def test_the_hidden_group_check_would_see_a_hidden_group_drawn_open(browser: Browser):
    """The hidden-group check cannot tell a hidden group from an open one."""
    payload = state_payload("extractor_params")
    parts = draw_wizard(browser, payload)
    hidden = [
        one["attrs"]["data-group"]
        for one in with_part(parts, "field-group")
        if one["hidden"]
    ]
    assert hidden == payload["groups"]["scrum"], hidden


def test_every_row_of_every_group_is_drawn_in_the_order_the_surface_names(
    browser: Browser,
):
    """A group's rows are drawn in an order the surface never named."""
    payload = state_payload("params")
    parts = draw_wizard(browser, payload)
    for name, rows in payload["groups"]["rows"].items():
        if name not in payload["pages"]["groups"]["params"]:
            continue
        drawn = [
            one["attrs"]["data-name"]
            for one in parts
            if one["attrs"].get("data-part") == "field-row"
            and ("field-group/" + name) not in one["path"]
        ]
        assert set(rows) <= set(drawn), (name, sorted(set(rows) - set(drawn)))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_number_field_draws_its_own_floor_ceiling_and_value(
    browser: Browser, state: str
):
    """A number field draws a floor or ceiling that is not its own."""
    payload = state_payload(state)
    parts = draw_wizard(browser, payload)
    for one in with_part(parts, "field"):
        name = one["attrs"]["data-name"]
        if one["attrs"].get("data-kind") not in ("double", "int"):
            continue
        spec = payload["fields"]["numbers"][name]
        assert float(one["min"]) == spec["minimum"], name
        assert float(one["max"]) == spec["maximum"], name
        assert float(one["value"]) == payload["values"]["numbers"][name], name


def test_the_number_field_check_would_see_a_ceiling_from_another_field(
    browser: Browser,
):
    """The number check reads the same ceiling whatever the surface declares."""
    payload = state_payload("params")
    payload["fields"]["numbers"]["trading_fee"]["maximum"] = 9.0
    parts = draw_wizard(browser, payload)
    drawn = named(parts, "field", "trading_fee")
    assert drawn and float(drawn[0]["max"]) == 9.0, drawn


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_check_box_draws_the_state_the_surface_carries(
    browser: Browser, state: str
):
    """A check box draws a state other than the one the surface carries."""
    payload = state_payload(state)
    parts = draw_wizard(browser, payload)
    for one in with_part(parts, "field"):
        kind = one["attrs"].get("data-kind")
        if kind not in ("checks", "radios"):
            continue
        name = one["attrs"]["data-name"]
        assert one["checked"] is payload["values"][kind][name], name


def test_the_check_box_check_would_see_a_box_ticked_the_surface_cleared(
    browser: Browser,
):
    """The check-box check reads the same state whatever the surface carries."""
    payload = state_payload("params")
    payload["values"]["checks"]["aggressive"] = True
    parts = draw_wizard(browser, payload)
    drawn = named(parts, "field", "aggressive")
    assert drawn and drawn[0]["checked"] is True, drawn


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_drop_down_draws_its_own_entries_in_their_own_order(
    browser: Browser, state: str
):
    """A drop-down draws entries in an order the surface never named."""
    payload = state_payload(state)
    parts = draw_wizard(browser, payload)
    for one in with_part(parts, "field"):
        if one["attrs"].get("data-kind") != "combos":
            continue
        name = one["attrs"]["data-name"]
        if name == payload["timeframes"]["ta_combo"]:
            wanted = [two[0] for two in payload["timeframes"]["ta_items"]]
        else:
            wanted = [two[0] for two in payload["fields"]["combos"][name]]
        assert one["options"] == wanted, name


def test_the_timeframe_drop_down_draws_the_list_the_venue_serves(browser: Browser):
    """The timeframe drop-down draws the wizard's own list, not the venue's."""
    payload = state_payload("params")
    parts = draw_wizard(browser, payload)
    drawn = named(parts, "field", payload["timeframes"]["ta_combo"])
    assert drawn[0]["options"] == [one[0] for one in payload["timeframes"]["ta_items"]]
    assert drawn[0]["options"] != payload["timeframes"]["ta"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_row_label_is_the_wording_the_surface_gives_that_row(
    browser: Browser, state: str
):
    """A row draws a label the surface gave another row."""
    payload = state_payload(state)
    parts = draw_wizard(browser, payload)
    for one in with_part(parts, "field-row-label"):
        name = one["attrs"]["data-name"]
        assert one["whole"] == payload["fields"]["row_labels"][name], name


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_check_word_is_the_wording_the_surface_gives_that_box(
    browser: Browser, state: str
):
    """A box draws wording the surface gave another box."""
    payload = state_payload(state)
    parts = draw_wizard(browser, payload)
    for one in with_part(parts, "field-check-text"):
        name = one["attrs"]["data-name"]
        wanted = payload["fields"]["check_texts"].get(
            name, payload["fields"]["radio_texts"].get(name)
        )
        assert one["whole"] == wanted, name


def test_the_wording_check_would_see_two_boxes_given_each_other_s_words(
    browser: Browser,
):
    """The wording check cannot tell two boxes' wording apart."""
    payload = state_payload("params")
    words = payload["fields"]["check_texts"]
    words["aggressive"], words["stack_mode"] = words["stack_mode"], words["aggressive"]
    parts = draw_wizard(browser, payload)
    drawn = named(parts, "field-check-text", "aggressive")
    assert drawn[0]["whole"] == words["aggressive"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_hover_line_is_the_wording_the_surface_gives_that_field(
    browser: Browser, state: str
):
    """A field shows hover text the surface gave another field."""
    payload = state_payload(state)
    parts = draw_wizard(browser, payload)
    tips = payload["fields"]["tool_tips"]
    for one in with_part(parts, "field"):
        name = one["attrs"].get("data-name")
        if name in tips:
            assert one["title"] == tips[name], name


def test_every_number_prefix_and_suffix_is_drawn_as_its_own_element(browser: Browser):
    """A prefix or suffix is drawn inside the number rather than beside it."""
    payload = state_payload("params")
    parts = draw_wizard(browser, payload)
    for one in with_part(parts, "field-prefix"):
        name = one["attrs"]["data-name"]
        assert one["whole"] == payload["fields"]["numbers"][name]["prefix"], name
    for one in with_part(parts, "field-suffix"):
        name = one["attrs"]["data-name"]
        assert one["whole"] == payload["fields"]["numbers"][name]["suffix"], name


def test_the_prefix_check_finds_the_dollar_mark_the_surface_declares(
    browser: Browser,
):
    """The prefix check finds no prefix at all, so its green says nothing."""
    payload = state_payload("params")
    parts = draw_wizard(browser, payload)
    drawn = named(parts, "field-prefix", "target_balance")
    assert drawn, "no prefix was drawn for the target balance"
    assert drawn[0]["whole"] == payload["fields"]["numbers"]["target_balance"]["prefix"]


# The asset, pool and phantom pages


def test_the_asset_page_draws_the_venue_list_the_surface_carries(browser: Browser):
    """The venue drop-down draws entries the surface never carried."""
    payload = state_payload("asset")
    parts = draw_wizard(browser, payload)
    drawn = named(parts, "field", "exchange")
    assert drawn[0]["options"] == [
        one[0] for one in payload["asset_page"]["exchange_items"]
    ]
    assert drawn[0]["attrs"]["data-index"] == str(
        payload["asset_page"]["exchange_index"]
    )


def test_the_venue_check_would_see_the_pool_page_venue_list_instead(
    browser: Browser,
):
    """The venue check reads the same list on both pages."""
    payload = state_payload("extractor_pool")
    parts = draw_wizard(browser, payload)
    drawn = named(parts, "field", "exchange")
    assert drawn[0]["options"] == [
        one[0] for one in payload["pool_page"]["exchange_items"]
    ]


def test_the_asset_page_draws_every_pair_the_surface_kept(browser: Browser):
    """The pair drop-down draws pairs the surface never kept."""
    payload = state_payload("asset")
    parts = draw_wizard(browser, payload)
    drawn = with_part(parts, "target-combo")
    assert drawn[0]["options"] == [
        one[0] for one in payload["asset_page"]["target_items"]
    ]


def test_the_asset_page_draws_the_status_line_the_surface_carries(browser: Browser):
    """The asset page draws a status line the surface never carried."""
    payload = state_payload("asset")
    parts = draw_wizard(browser, payload)
    drawn = with_part(parts, "page-status")
    assert [one["whole"] for one in drawn] == [payload["asset_page"]["status"]]


def test_the_pair_icon_carries_the_hue_the_surface_measured(browser: Browser):
    """The pair mark carries a hue the surface never measured."""
    payload = state_payload("asset")
    parts = draw_wizard(browser, payload)
    drawn = with_part(parts, "target-icon")
    at = payload["asset_page"]["target_index"]
    assert drawn[0]["attrs"]["data-value"] == str(
        payload["asset_page"]["target_hues"][at]
    )


def test_the_hue_check_would_see_the_hue_of_another_pair(browser: Browser):
    """The hue check reads the same hue whatever pair is picked."""
    payload = state_payload("asset")
    payload["asset_page"]["target_hues"][0] = 7
    parts = draw_wizard(browser, payload)
    assert with_part(parts, "target-icon")[0]["attrs"]["data-value"] == "7"


def test_the_info_button_draws_its_own_wording_and_hover_line(browser: Browser):
    """The info button draws wording the surface never gave it."""
    payload = state_payload("asset")
    parts = draw_wizard(browser, payload)
    drawn = with_part(parts, "info-button")
    assert drawn[0]["whole"] == payload["fields"]["button_texts"]["info"]
    assert drawn[0]["title"] == payload["asset_page"]["info_tool_tip"]


def test_the_info_button_takes_the_colour_its_own_whole_sheet_declares(
    browser: Browser,
):
    """The info button takes a colour its own sheet never declared."""
    payload = state_payload("asset")
    parts = draw_wizard(browser, payload)
    drawn = with_part(parts, "info-button")[0]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps(
            browser.parsed(
                API
                + "styleOf("
                + json.dumps(payload["asset_page"]["info_button_style"])
                + ")"
            )
        )
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    for name in ("color", "borderTopWidth", "borderTopColor", "borderTopLeftRadius"):
        assert drawn["style"][name] == probe[name], name


def test_the_button_colour_check_would_see_a_button_given_another_colour(
    browser: Browser,
):
    """The button colour check reads the same colour whatever the sheet says."""
    payload = state_payload("asset")
    payload["asset_page"]["info_button_style"] = "color: " + OTHER_COLOUR + ";"
    parts = draw_wizard(browser, payload)
    drawn = with_part(parts, "info-button")[0]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"color": OTHER_COLOUR})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert drawn["style"]["color"] == probe["color"]


def test_the_pool_page_draws_every_alt_with_its_own_tick(browser: Browser):
    """An alt is drawn with a tick that belongs to another alt."""
    payload = state_payload("picked_alts")
    parts = draw_wizard(browser, payload)
    rows = with_part(parts, "alt-row")
    assert [one["attrs"]["data-name"] for one in rows] == [
        one[1] for one in payload["pool_page"]["alt_items"]
    ]
    assert [one["attrs"]["data-checked"] for one in rows] == [
        str(one).lower() for one in payload["pool_page"]["alt_checked"]
    ]


def test_the_alt_tick_check_would_see_a_tick_on_the_wrong_alt(browser: Browser):
    """The alt tick check reads the same tick for every alt."""
    payload = state_payload("picked_alts")
    ticks = payload["pool_page"]["alt_checked"]
    payload["pool_page"]["alt_checked"] = [not one for one in ticks]
    parts = draw_wizard(browser, payload)
    rows = with_part(parts, "alt-row")
    assert [one["attrs"]["data-checked"] for one in rows] == [
        str(one).lower() for one in payload["pool_page"]["alt_checked"]
    ]


def test_the_pool_page_draws_the_two_buttons_with_their_own_wording(
    browser: Browser,
):
    """A pool button draws wording the surface gave the other one."""
    payload = state_payload("extractor_pool")
    parts = draw_wizard(browser, payload)
    words = payload["fields"]["button_texts"]
    assert with_part(parts, "select-all")[0]["whole"] == words["select_all"]
    assert with_part(parts, "clear-all")[0]["whole"] == words["clear_all"]


def test_every_phantom_timeframe_draws_its_own_name_state_and_grey(
    browser: Browser,
):
    """A timeframe box draws a state or grey that belongs to another."""
    payload = state_payload("phantom")
    parts = draw_wizard(browser, payload)
    rows = with_part(parts, "timeframe-row")
    assert [one["attrs"]["data-name"] for one in rows] == payload["phantom_page"][
        "timeframes"
    ]
    for one in rows:
        name = one["attrs"]["data-name"]
        assert (
            one["attrs"]["data-checked"]
            == str(payload["phantom_page"]["checked"][name]).lower()
        ), name
        assert (
            one["attrs"]["data-enabled"]
            == str(payload["phantom_page"]["enabled"][name]).lower()
        ), name


def test_a_timeframe_the_venue_does_not_offer_is_drawn_greyed(browser: Browser):
    """A timeframe the venue does not offer is drawn ready to tick."""
    payload = state_payload("phantom")
    parts = draw_wizard(browser, payload)
    greyed = [
        one["attrs"]["data-name"]
        for one in with_part(parts, "timeframe-check")
        if one["disabled"]
    ]
    offered = set(payload["timeframes"]["offered"]["coinbase"])
    assert greyed == [
        one for one in payload["phantom_page"]["timeframes"] if one not in offered
    ], greyed


def test_the_grey_check_would_see_every_timeframe_offered(browser: Browser):
    """The grey check reads every timeframe as greyed whatever the venue offers."""
    payload = state_payload("phantom")
    for name in payload["phantom_page"]["enabled"]:
        payload["phantom_page"]["enabled"][name] = True
    parts = draw_wizard(browser, payload)
    greyed = [one for one in with_part(parts, "timeframe-check") if one["disabled"]]
    assert greyed == [], greyed


def test_the_refusal_warning_is_drawn_line_by_line(browser: Browser):
    """The call-budget warning is drawn as one run-together line."""
    payload = state_payload("refused")
    parts = draw_wizard(browser, payload)
    assert payload["phantom_page"]["warning_box"], "the case refused nothing"
    lines = payload["phantom_page"]["warning_box"]
    assert with_part(parts, "warning-title")[0]["whole"] == lines[0]
    assert with_part(parts, "warning-text")[0]["whole"] == lines[1]
    assert with_part(parts, "warning-informative")[0]["whole"] == lines[2]


def test_a_page_with_no_refusal_draws_no_warning_at_all(browser: Browser):
    """A page that refused nothing still draws a warning."""
    parts = draw_wizard(browser, state_payload("phantom"))
    assert with_part(parts, "warning-box") == []


def test_the_warning_check_would_see_a_warning_that_was_never_raised(
    browser: Browser,
):
    """The warning check cannot see a warning that was drawn."""
    payload = state_payload("phantom")
    payload["phantom_page"]["warning_box"] = ["a", "b", "c"]
    parts = draw_wizard(browser, payload)
    assert with_part(parts, "warning-box"), "no warning was drawn"


def test_the_mode_page_draws_a_description_beside_each_mode(browser: Browser):
    """A mode draws the description the surface gave the other mode."""
    payload = state_payload("mode")
    parts = draw_wizard(browser, payload)
    notes = with_part(parts, "mode-note")
    assert [one["attrs"]["data-name"] for one in notes] == [
        one + "_description" for one in payload["modes"]["names"]
    ]
    for one in notes:
        name = one["attrs"]["data-name"]
        assert one["whole"] == payload["fields"]["label_texts"][name], name


def test_each_wrapped_note_keeps_the_line_break_its_own_words_carry(
    browser: Browser,
):
    """A wrapped note is told to collapse the line breaks its words carry."""
    payload = state_payload("mode")
    parts = draw_wizard(browser, payload)
    for one in with_part(parts, "mode-note"):
        name = one["attrs"]["data-name"]
        wrapped = name in payload["layout"]["word_wrapped_labels"]
        assert one["attrs"]["data-word-wrap"] == str(wrapped).lower(), name
        assert one["style"]["whiteSpace"] == ("pre-wrap" if wrapped else "nowrap"), name


def test_the_line_break_check_would_see_a_note_told_to_collapse_it(browser: Browser):
    """The line-break check reads the same setting whatever the surface says."""
    payload = state_payload("mode")
    payload["layout"]["word_wrapped_labels"] = []
    parts = draw_wizard(browser, payload)
    for one in with_part(parts, "mode-note"):
        assert one["style"]["whiteSpace"] == "nowrap"


# Every move reaches the surface as the step the wizard took


def test_typing_in_a_number_runs_its_own_handler_with_the_number_typed(
    browser: Browser,
):
    """A number runs a handler with a value nobody typed."""
    draw_wizard(browser, state_payload("params"))
    browser.js(
        "(function () { var el = window.HOST.querySelector("
        '  \'[data-part="field"][data-name="trading_fee"]\');'
        " var setter = Object.getOwnPropertyDescriptor("
        "   window.HTMLInputElement.prototype, 'value').set;"
        " setter.call(el, '1.25');"
        " el.dispatchEvent(new Event('input', { bubbles: true })); })()"
    )
    assert browser.parsed("window.PRESSED") == [["number", "trading_fee", 1.25]]


def test_clicking_a_check_box_runs_its_own_handler_with_the_flag_it_moved_to(
    browser: Browser,
):
    """A box runs a handler with a flag it never moved to."""
    draw_wizard(browser, state_payload("params"))
    browser.js(
        "window.HOST.querySelector("
        '  \'[data-part="field"][data-name="aggressive"]\').click();'
    )
    assert browser.parsed("window.PRESSED") == [["flag", "aggressive", True]]


def test_picking_a_drop_down_entry_runs_its_own_handler_with_that_place(
    browser: Browser,
):
    """A drop-down runs a handler with a place nobody picked."""
    draw_wizard(browser, state_payload("params"))
    browser.js(
        "(function () { var el = window.HOST.querySelector("
        '  \'[data-part="field"][data-name="visibility"]\');'
        " var setter = Object.getOwnPropertyDescriptor("
        "   window.HTMLSelectElement.prototype, 'value').set;"
        " setter.call(el, '1');"
        " el.dispatchEvent(new Event('change', { bubbles: true })); })()"
    )
    assert browser.parsed("window.PRESSED") == [["index", "visibility", 1]]


def test_typing_in_a_text_field_runs_its_own_handler_with_the_text_typed(
    browser: Browser,
):
    """A text field runs a handler with text nobody typed."""
    draw_wizard(browser, state_payload("params"))
    browser.js(
        "(function () { var el = window.HOST.querySelector("
        '  \'[data-part="field"][data-name="profit_route_bot_id"]\');'
        " var setter = Object.getOwnPropertyDescriptor("
        "   window.HTMLInputElement.prototype, 'value').set;"
        " setter.call(el, 'bot-z');"
        " el.dispatchEvent(new Event('input', { bubbles: true })); })()"
    )
    assert browser.parsed("window.PRESSED") == [
        ["text", "profit_route_bot_id", "bot-z"]
    ]


def test_ticking_one_alt_runs_its_own_handler_with_that_alt_s_place(
    browser: Browser,
):
    """An alt runs a handler with a place that belongs to another alt."""
    draw_wizard(browser, state_payload("extractor_pool"))
    browser.js(
        "window.HOST.querySelectorAll(" "  '[data-part=\"alt-check\"]')[0].click();"
    )
    assert browser.parsed("window.PRESSED") == [["alt", 0, True]]


def test_ticking_one_timeframe_runs_its_own_handler_with_that_timeframe(
    browser: Browser,
):
    """A timeframe runs a handler naming another timeframe."""
    payload = state_payload("phantom")
    draw_wizard(browser, payload)
    browser.js(
        "window.HOST.querySelector("
        '  \'[data-part="timeframe-check"][data-name="1h"]\').click();'
    )
    assert browser.parsed("window.PRESSED") == [["timeframe", "1h", True]]


def test_the_timeframe_press_check_would_see_a_box_answering_with_its_place(
    browser: Browser,
):
    """The timeframe press check cannot tell a name from a place."""
    draw_wizard(browser, state_payload("phantom"))
    browser.js(
        "window.HOST.querySelector("
        '  \'[data-part="timeframe-check"][data-name="1d"]\').click();'
    )
    assert browser.parsed("window.PRESSED") == [["timeframe", "1d", True]]


def test_pressing_a_walk_button_runs_its_own_handler_with_that_step(
    browser: Browser,
):
    """A walk button runs a handler naming another step."""
    payload = state_payload("params")
    draw_wizard(browser, payload)
    for name in payload["walk"]["steps"]:
        browser.js("window.PRESSED = [];")
        browser.js(
            "window.HOST.querySelector("
            '  \'[data-part="walk-step"][data-step="' + name + "\"]').click();"
        )
        assert browser.parsed("window.PRESSED") == [["walk", name]], name


def test_pressing_the_two_pool_buttons_runs_their_own_handlers(browser: Browser):
    """A pool button runs the other button's handler."""
    draw_wizard(browser, state_payload("extractor_pool"))
    browser.js("window.HOST.querySelector('[data-part=\"select-all\"]').click();")
    browser.js("window.HOST.querySelector('[data-part=\"clear-all\"]').click();")
    assert browser.parsed("window.PRESSED") == [["select_all"], ["clear_all"]]


def test_pressing_the_info_button_runs_its_own_handler(browser: Browser):
    """The info button runs no handler at all."""
    draw_wizard(browser, state_payload("asset"))
    browser.js("window.HOST.querySelector('[data-part=\"info-button\"]').click();")
    assert browser.parsed("window.PRESSED") == [["info"]]


def test_picking_a_venue_runs_its_own_handler_with_that_place(browser: Browser):
    """The venue drop-down runs a handler with a place nobody picked."""
    draw_wizard(browser, state_payload("asset"))
    browser.js(
        "(function () { var el = window.HOST.querySelector("
        '  \'[data-part="field"][data-name="exchange"]\');'
        " var setter = Object.getOwnPropertyDescriptor("
        "   window.HTMLSelectElement.prototype, 'value').set;"
        " setter.call(el, '1');"
        " el.dispatchEvent(new Event('change', { bubbles: true })); })()"
    )
    assert browser.parsed("window.PRESSED") == [["venue", "asset_page", 1]]


def test_the_handler_check_would_see_a_press_nobody_made(browser: Browser):
    """The handler check counts a press nobody made."""
    draw_wizard(browser, state_payload("params"))
    assert browser.parsed("window.PRESSED") == []


@pytest.mark.parametrize("state", ["params", "phantom", "extractor_pool"])
def test_each_move_sends_one_step_the_surface_would_take(js: JsRuntime, state: str):
    """A move sends a step name the surface never takes."""
    js.push(state_payload(state))
    js.run(API + 'pressNumber("trading_fee", 1.25)')
    sent = js.json(API + "sent()")
    assert sent[-1]["step"] == {"numbers": {"trading_fee": 1.25}}, sent
    assert "numbers" in surface.STEP_NAMES


def test_every_step_name_a_press_sends_is_one_the_surface_reads(js: JsRuntime):
    """A press sends a step name the surface never reads."""
    js.push(state_payload("params"))
    for call in (
        'pressNumber("trading_fee", 1.0)',
        'pressFlag("aggressive", true)',
        'pressIndex("visibility", 1)',
        'pressText("profit_route_bot_id", "b")',
        "pressAlt(0, true)",
        'pressTimeframe("1h", true)',
        "pressTarget(0)",
        'pressVenue("asset_page", 1)',
        'pressButton("select_all")',
        'pressWalk("next")',
    ):
        js.run(API + call)
    for one in js.json(API + "sent()"):
        for name in one["step"]:
            assert name in surface.STEP_NAMES, (name, one)


def test_the_step_name_check_would_see_a_step_the_surface_never_reads(js: JsRuntime):
    """The step-name check counts any name at all as a name the surface reads."""
    assert "no_such_step" not in surface.STEP_NAMES


# A long, marked or broken value on the drawn page


def test_a_two_hundred_character_label_stretches_the_row_rather_than_clipping(
    browser: Browser,
):
    """A very long label is clipped rather than drawn whole."""
    payload = state_payload("params")
    payload["fields"]["row_labels"]["trading_fee"] = LONG_NAME
    parts = draw_wizard(browser, payload)
    drawn = named(parts, "field-row-label", "trading_fee")
    assert drawn[0]["whole"] == LONG_NAME
    assert drawn[0]["width"] > 0


def test_a_two_hundred_character_label_does_not_widen_the_wizard_itself(
    browser: Browser,
):
    """A very long label pushes the whole wizard wider than its space."""
    payload = state_payload("params")
    payload["fields"]["row_labels"]["trading_fee"] = LONG_NAME
    draw_wizard(browser, payload)
    inner = browser.parsed("window.HOST.firstChild.getBoundingClientRect().width")
    outer = browser.parsed("window.HOST.getBoundingClientRect().width")
    assert inner <= outer, (inner, outer)


def test_the_wizard_refuses_markup_a_hostile_label_carries(browser: Browser):
    """A tag in a label is run by the page rather than drawn as characters."""
    payload = state_payload("params")
    payload["fields"]["row_labels"]["trading_fee"] = MARKUP_NAME
    parts = draw_wizard(browser, payload)
    drawn = named(parts, "field-row-label", "trading_fee")
    assert drawn[0]["whole"] == MARKUP_NAME
    assert "<b>" not in drawn[0]["html"], drawn[0]["html"]
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    """The markup refusal cannot see a tag the page really ran."""
    draw_wizard(browser, state_payload("params"))
    browser.js("window.HOST.firstChild.insertAdjacentHTML('beforeend', '<img>');")
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 1


def test_a_newline_in_a_label_is_written_as_text_and_not_as_two_rows(
    browser: Browser,
):
    """A line break in a label splits the row into two."""
    payload = state_payload("params")
    payload["fields"]["row_labels"]["trading_fee"] = NEWLINE_NAME
    parts = draw_wizard(browser, payload)
    assert len(named(parts, "field-row-label", "trading_fee")) == 1
    assert named(parts, "field-row-label", "trading_fee")[0]["whole"] == NEWLINE_NAME


def test_a_number_the_step_cannot_reach_is_drawn_with_its_own_step(
    browser: Browser,
):
    """A number off its own step is drawn without the step that refuses it."""
    payload = state_payload("params")
    payload["values"]["numbers"]["trading_fee"] = 0.62
    parts = draw_wizard(browser, payload)
    drawn = named(parts, "field", "trading_fee")
    assert float(drawn[0]["value"]) == 0.62
    assert (
        float(drawn[0]["step"]) == payload["fields"]["numbers"]["trading_fee"]["step"]
    )
    assert (
        browser.parsed(
            "window.HOST.querySelector("
            '  \'[data-part="field"][data-name="trading_fee"]\').validity.stepMismatch'
        )
        is True
    )


def test_a_number_inside_its_own_step_draws_no_step_complaint(browser: Browser):
    """The step measurement reads every number as off its own step."""
    payload = state_payload("params")
    payload["values"]["numbers"]["trading_fee"] = 0.6
    draw_wizard(browser, payload)
    assert (
        browser.parsed(
            "window.HOST.querySelector("
            '  \'[data-part="field"][data-name="trading_fee"]\').validity.stepMismatch'
        )
        is False
    )


def test_a_number_outside_its_own_range_is_drawn_with_its_own_floor_and_ceiling(
    browser: Browser,
):
    """A number outside its range is drawn without the range that refuses it."""
    payload = state_payload("params")
    payload["values"]["numbers"]["trading_fee"] = 99.0
    parts = draw_wizard(browser, payload)
    drawn = named(parts, "field", "trading_fee")
    assert float(drawn[0]["value"]) == 99.0
    assert (
        browser.parsed(
            "window.HOST.querySelector("
            '  \'[data-part="field"][data-name="trading_fee"]\').validity.rangeOverflow'
        )
        is True
    )


def test_a_duplicate_alt_name_draws_two_rows_and_not_one(browser: Browser):
    """Two alts naming one pair are merged into one drawn row."""
    payload = state_payload("picked_alts")
    first = payload["pool_page"]["alt_items"][0]
    payload["pool_page"]["alt_items"] = [first, list(first)]
    payload["pool_page"]["alt_checked"] = [True, False]
    parts = draw_wizard(browser, payload)
    rows = with_part(parts, "alt-row")
    assert len(rows) == 2, rows
    assert [one["attrs"]["data-checked"] for one in rows] == ["true", "false"]


def test_a_bare_payload_with_no_venue_still_draws_the_wizard(browser: Browser):
    """A wizard opened with no venue at all draws nothing."""
    parts = draw_wizard(browser, state_payload("bare"))
    assert at_path(parts, "bot-wizard"), "nothing was drawn"
    assert with_part(parts, "page-rail-stop"), "no page rail was drawn"


# The layout numbers this host measured


def test_the_wizard_declares_its_own_spacing_and_leaves_the_form_to_the_host(
    browser: Browser,
):
    """The wizard declares a spacing the surface never gave it."""
    payload = state_payload("params")
    parts = draw_wizard(browser, payload)
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps(
            {
                "display": "flex",
                "flexDirection": "column",
                "gap": str(payload["layout"]["groups_spacing_px"]) + "px",
            }
        )
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    drawn = at_path(parts, "bot-wizard")[0]
    assert drawn["style"]["rowGap"] == probe["rowGap"]
    assert drawn["style"]["flexDirection"] == probe["flexDirection"]


def test_the_spacing_check_would_see_a_wizard_given_another_spacing(
    browser: Browser,
):
    """The spacing check reads the same gap whatever the surface declares."""
    payload = state_payload("params")
    payload["layout"]["groups_spacing_px"] = 40
    parts = draw_wizard(browser, payload)
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"display": "flex", "flexDirection": "column", "gap": "40px"})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert at_path(parts, "bot-wizard")[0]["style"]["rowGap"] == probe["rowGap"]


def test_the_alt_list_is_held_to_the_height_the_surface_gives_it(browser: Browser):
    """The alt list takes a height the surface never gave it."""
    payload = state_payload("extractor_pool")
    parts = draw_wizard(browser, payload)
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps(
            {
                "minHeight": str(payload["pool_page"]["alt_list_minimum_height_px"])
                + "px"
            }
        )
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert with_part(parts, "alt-list")[0]["style"]["minHeight"] == probe["minHeight"]


def test_the_alt_height_check_would_see_a_list_given_a_taller_one(browser: Browser):
    """The alt height check reads the same height whatever the surface says."""
    payload = state_payload("extractor_pool")
    payload["pool_page"]["alt_list_minimum_height_px"] = 640
    parts = draw_wizard(browser, payload)
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"minHeight": "640px"})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert with_part(parts, "alt-list")[0]["style"]["minHeight"] == probe["minHeight"]


def test_the_pair_drop_down_is_held_to_the_width_the_surface_gives_it(
    browser: Browser,
):
    """The pair drop-down takes a width the surface never gave it."""
    payload = state_payload("asset")
    parts = draw_wizard(browser, payload)
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps(
            {"minWidth": str(payload["asset_page"]["target_minimum_width_px"]) + "px"}
        )
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert with_part(parts, "target-combo")[0]["style"]["minWidth"] == probe["minWidth"]


def test_the_alt_list_carries_the_name_a_screen_reader_reads(browser: Browser):
    """The alt list carries no name a screen narrator can announce."""
    payload = state_payload("extractor_pool")
    parts = draw_wizard(browser, payload)
    assert (
        with_part(parts, "alt-list")[0]["attrs"]["aria-label"]
        == payload["pool_page"]["alt_list_accessible_name"]
    )


def test_the_wizard_carries_the_name_and_description_the_surface_gives_it(
    browser: Browser,
):
    """The wizard carries no accessible name at all."""
    payload = state_payload("mode")
    parts = draw_wizard(browser, payload)
    drawn = at_path(parts, "bot-wizard")[0]
    assert drawn["attrs"]["aria-label"] == payload["window"]["accessible_name"]
    assert (
        drawn["attrs"]["aria-description"]
        == payload["window"]["accessible_description"]
    )


def test_the_wizard_draws_the_window_title_the_surface_carries(browser: Browser):
    """The wizard draws a title the surface never carried."""
    payload = state_payload("mode")
    parts = draw_wizard(browser, payload)
    assert with_part(parts, "wizard-title")[0]["whole"] == payload["window"]["title"]


@pytest.mark.parametrize("case", sorted(UNSERIALISABLE))
def test_a_number_json_cannot_name_never_crosses_the_bridge_at_all(case: str):
    """A number JSON cannot name crosses the bridge and reaches the screen."""
    payload = state_payload("params")
    payload["values"]["numbers"]["trading_fee"] = UNSERIALISABLE[case]
    with pytest.raises(ValueError):
        json.loads(json.dumps(payload), parse_constant=_refuse_constant)


def _refuse_constant(name: str) -> Any:
    raise ValueError(name)


def test_the_bridge_check_still_carries_a_number_json_can_name():
    """The bridge check refuses every number, so its refusal says nothing."""
    payload = state_payload("params")
    payload["values"]["numbers"]["trading_fee"] = 1.25
    found = json.loads(json.dumps(payload), parse_constant=_refuse_constant)
    assert found["values"]["numbers"]["trading_fee"] == 1.25


@pytest.mark.parametrize("kind", sorted(PAINTED_WIDGETS))
def test_no_measured_widget_this_wizard_uses_reads_its_caller_text_as_markup(
    qapp, kind: str
):
    """A widget this wizard uses paints its caller text as rich text."""
    assert qapp is not None
    marked = text_width(PAINTED_WIDGETS[kind](MARKED))
    eaten = text_width(PAINTED_WIDGETS[kind](EATEN))
    assert marked > eaten, (kind, marked, eaten)


def test_the_text_width_measurement_reads_a_longer_text_as_a_wider_one(qapp):
    """The text-width measurement answers the same for two lengths of text."""
    assert qapp is not None
    assert text_width(a_line(EATEN + EATEN)) > text_width(a_line(EATEN))


def test_each_mode_note_carries_the_muted_flag_the_surface_names_it_with(
    browser: Browser,
):
    """A note carries a muted flag the surface never gave it."""
    payload = state_payload("mode")
    parts = draw_wizard(browser, payload)
    for one in with_part(parts, "mode-note"):
        name = one["attrs"]["data-name"]
        muted = name in payload["layout"]["muted_labels"]
        assert one["attrs"]["data-muted"] == str(muted).lower(), name


def test_the_muted_flag_check_would_see_a_note_the_surface_left_plain(
    browser: Browser,
):
    """The muted-flag check reads the same flag whatever the surface names."""
    payload = state_payload("mode")
    payload["layout"]["muted_labels"] = []
    parts = draw_wizard(browser, payload)
    flags = {one["attrs"]["data-muted"] for one in with_part(parts, "mode-note")}
    assert flags == {"false"}, flags


def test_a_muted_note_takes_no_colour_of_the_module_s_own(browser: Browser):
    """A muted note is dimmed by a colour the module wrote for itself."""
    payload = state_payload("mode")
    parts = draw_wizard(browser, payload)
    plain = browser.parsed("window.probeAssign({}, JSON.parse(window.STYLE_NAMES))")
    for one in with_part(parts, "mode-note"):
        assert one["style"]["color"] == plain["color"], one["attrs"]["data-name"]


def test_the_note_colour_check_would_see_a_note_given_a_colour(browser: Browser):
    """The note colour check reads every note as taking the page colour."""
    draw_wizard(browser, state_payload("mode"))
    browser.js(
        "window.HOST.querySelector('[data-part=\"mode-note\"]').style.color = "
        + json.dumps(OTHER_COLOUR)
        + ";"
    )
    parts = json.loads(browser.js(READ_PARTS))
    plain = browser.parsed("window.probeAssign({}, JSON.parse(window.STYLE_NAMES))")
    painted_one = [
        one
        for one in with_part(parts, "mode-note")
        if one["style"]["color"] != plain["color"]
    ]
    assert len(painted_one) == 1, painted_one
