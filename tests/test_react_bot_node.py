"""Drives bot_node.js from every card the locust surface builds."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import bot_node_surface as surface
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "bot_node.js"
MERGED_PATHS = (
    WEB / "design_tokens.js",
    WEB / "theme_engine.js",
    WEB / "shared_widgets.js",
)
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

MODULE_TAIL = "})(window);"
MODULE_READ_ATTEMPTS = 200
MODULE_READ_PAUSE_S = 0.01


def read_module() -> str:
    """Return MODULE_PATH text ending with MODULE_TAIL, retrying while not."""
    for _ in range(MODULE_READ_ATTEMPTS):
        found = MODULE_PATH.read_text(encoding="utf-8")
        if found.rstrip().endswith(MODULE_TAIL):
            return found
        time.sleep(MODULE_READ_PAUSE_S)
    raise AssertionError(MODULE_PATH.name + " never read back whole")


MODULE_SOURCE = read_module()
MODULE_LITERALS = js_literals(MODULE_SOURCE)
MERGED_SOURCES = tuple(
    (one.name, one.read_text(encoding="utf-8")) for one in MERGED_PATHS
)

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 400
READY_ROUNDS = 100
READY_STEP_MS = 100
VIEW_SIZE_PX = (600, 500)
HOST_WIDTH_PX = 400
HOST_HEIGHT_PX = 300

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

CARD_SIZE = (112, 98)
HAPPY_PHASE = 0.7
SPECK = (40.0, 30.0, -12.0, 8.0, 0.9, 2.5)
LONG_TEXT = "L" * 200
MARKUP_TEXT = '<img src="x.png" onerror="boom()">'
NEWLINE_TEXT = "line one\nline two"


def stats(**named: Any) -> dict:
    row = {
        "realised_pnl": 12.5,
        "total_trades": 7,
        "current_price": 50000.0,
        "trade_volume": 2_500_000.0,
    }
    row.update(named)
    return row


def data(**named: Any) -> dict:
    row = {
        "bot_id": "abcdef0123456789",
        "symbol": "BTC-USD",
        "state": "running",
        "mode": "scrumming",
        "stats": stats(),
    }
    row.update(named)
    return row


def card(**named: Any) -> dict:
    """One card state, as the surface is set up with it."""
    spec = {
        "width_px": CARD_SIZE[0],
        "height_px": CARD_SIZE[1],
        "phase": HAPPY_PHASE,
        "theme_key": "quantum",
        "trade_pulses": [],
        "particles": [],
        "antenna_drive": 0.0,
        "bot_data": data(),
    }
    spec.update(named)
    return spec


CARD_SPECS = {
    "running": card(),
    "idle": card(bot_data=data(state="idle")),
    "paused": card(bot_data=data(state="paused")),
    "error": card(bot_data=data(state="error")),
    "stopped": card(bot_data=data(state="stopped")),
    "cooldown": card(bot_data=data(state="cooldown")),
    "unknown_state": card(bot_data=data(state="melting")),
    "no_bot_data": card(bot_data={}),
    "one_ring": card(trade_pulses=[0.6]),
    "five_specks": card(particles=[SPECK] * 5),
    "a_loss": card(bot_data=data(stats=stats(realised_pnl=-480.25))),
    "no_price": card(bot_data=data(stats=stats(current_price=0))),
    "small_volume": card(bot_data=data(stats=stats(trade_volume=4.0))),
    "theme_matrix": card(theme_key="matrix"),
    "theme_nebula": card(theme_key="nebula"),
    "theme_ocean": card(theme_key="ocean"),
    "unknown_theme": card(theme_key="starfield"),
    "the_feelers_swaying": card(antenna_drive=1.0),
    "a_wide_card": card(width_px=300, height_px=98),
}

CARD_NAMES = sorted(CARD_SPECS)
DRAWN_NAMES = [one for one in CARD_NAMES if one != "no_bot_data"]

HIDDEN_FIELDS = (surface.MASK_FIELD_ID,)


def state_payload(name: str, hidden: Any = ()) -> dict:
    """The payload the surface answers for one named card."""
    return surface.view_model({"card": CARD_SPECS[name], "hidden": list(hidden)})


def token_payload() -> dict:
    """The design token payload the page applies before it draws."""
    return dss.build_view_model()


def theme_payload() -> dict:
    """The theme payload the page applies before it draws."""
    return tes.build_view_model()


class JsRuntime(JsEngine):
    """A QJSEngine holding bot_node.js and the modules it reads."""

    module_path = MODULE_PATH
    setter = "acervatorSetBotNode"

    def __init__(self, engine: Any, source: str) -> None:
        engine.evaluate("var window = this;")
        for name, body in MERGED_SOURCES:
            loaded = engine.evaluate(body, name)
            assert not loaded.isError(), name + ": " + loaded.toString()
        super().__init__(engine, source)
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")
        self.bind_json("THEMES", theme_payload())
        self.run("acervatorSetThemes(JSON.parse(THEMES));")

    def answer(self, expression: str) -> Any:
        return self.json("acervatorBotNode." + expression)


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


def python_kinds(payload: Any) -> dict:
    """The JavaScript type of every value of `payload`, by dotted path."""
    found: dict = {}

    def descend(path: str, value: Any) -> None:
        if isinstance(value, dict):
            walk(path, value)
            return
        if isinstance(value, (list, tuple)):
            for index, one in enumerate(value):
                inner = f"{path}.{index}"
                found[inner] = JS_TYPE_OF[type(one).__name__]
                descend(inner, one)

    def walk(prefix: str, node: dict) -> None:
        for name, value in node.items():
            path = f"{prefix}.{name}" if prefix else name
            found[path] = JS_TYPE_OF[type(value).__name__]
            descend(path, value)

    walk("", payload)
    return found


@pytest.mark.parametrize("name", CARD_NAMES)
def test_every_field_the_module_declares_is_in_the_payload(js: JsRuntime, name: str):
    payload = state_payload(name)
    js.push(payload)
    assert sorted(js.answer("declaredFields()")) == sorted(payload)


@pytest.mark.parametrize("name", CARD_NAMES)
def test_the_module_reports_no_fault_for_a_payload_the_surface_built(
    js: JsRuntime, name: str
):
    found = js.push(state_payload(name))
    assert found["faults"] == [], found["faults"]


@pytest.mark.parametrize("name", CARD_NAMES)
def test_the_declared_and_held_counts_match_in_every_state(js: JsRuntime, name: str):
    found = js.push(state_payload(name))
    assert found["declared"] == found["held"], (name, found)


def test_the_count_check_reports_a_call_the_module_cannot_read(js: JsRuntime):
    """The counts match above, so this payload proves they can differ."""
    payload = state_payload("running")
    payload["drawing_calls"] = payload["drawing_calls"] + [["draw_hexagon", [1, 2]]]
    found = js.push(payload)
    assert found["declared"]["calls"] == found["held"]["calls"] + 1
    assert [one["fault"] for one in found["faults"]] == ["unknown-op"]


@pytest.mark.parametrize("name", DRAWN_NAMES)
def test_every_drawing_call_is_drawn_or_named_for_the_canvas(js: JsRuntime, name: str):
    payload = state_payload(name)
    found = js.push(payload)
    drawn = found["drawn"]
    kinds = [one[0] for one in payload["drawing_calls"]]
    assert drawn["grounds"] == kinds.count("fill_rect")
    assert drawn["dots"] == kinds.count("draw_ellipse")
    assert drawn["words"] == kinds.count("draw_text")
    assert drawn["paths"] == kinds.count("draw_path")
    assert drawn["rules"] + drawn["slopes"] == kinds.count("draw_line")


def test_an_empty_card_draws_nothing_at_all(js: JsRuntime):
    found = js.push(state_payload("no_bot_data"))
    assert found["declared"]["calls"] == 0
    assert found["drawn"] == {
        "grounds": 0,
        "dots": 0,
        "rules": 0,
        "words": 0,
        "paths": 0,
        "slopes": 0,
    }
    assert js.push(state_payload("running"))["drawn"]["grounds"] == 1


@pytest.mark.parametrize("name", DRAWN_NAMES)
def test_css_draws_the_fills_the_flat_lines_and_the_text(js: JsRuntime, name: str):
    """CSS draws every call but the curves and the slanted leg bones."""
    js.push(state_payload(name))
    deferred = js.answer("deferredCount()")
    assert deferred == {"paths": 7, "slopes": 12}, (name, deferred)


def test_the_module_asks_the_bridge_by_the_method_the_surface_names(js: JsRuntime):
    assert js.answer("method") == surface.METHOD
    assert js.json("typeof acervatorLoadBotNode") == "function"
    assert js.json("acervatorLoadBotNode({}) === null") is False
    assert js.answer("loadError()") == "the preload bridge is not present"


def test_a_payload_that_is_not_an_object_is_refused(js: JsRuntime):
    found = js.json("acervatorSetBotNode(JSON.parse('[1,2,3]'))")
    assert found["declared"] is None
    assert [one["fault"] for one in found["faults"]] == ["not-an-object"]
    assert js.answer("isLoaded()") is False
    assert js.answer("card()") == {}


def payload_values(payload: Any, found: set) -> set:
    """Every string the payload carries as a value rather than as a key."""
    if isinstance(payload, dict):
        for value in payload.values():
            payload_values(value, found)
    elif isinstance(payload, (list, tuple)):
        for one in payload:
            payload_values(one, found)
    elif isinstance(payload, str):
        found.add(payload)
    return found


def payload_keys(payload: Any, found: set) -> set:
    """Every key name the payload carries, at every depth."""
    if isinstance(payload, dict):
        for name, value in payload.items():
            found.add(name)
            payload_keys(value, found)
    elif isinstance(payload, (list, tuple)):
        for one in payload:
            payload_keys(one, found)
    return found


SAMPLE = state_payload("running")

PUBLISHED_VALUES = payload_values(SAMPLE, set()) | payload_values(
    state_payload("theme_matrix"), set()
)
PUBLISHED_KEYS = payload_keys(SAMPLE, set())

#: A naming value tells the module what a call means; it paints nothing.
NAMING_VALUES = (
    {surface.METHOD, "", surface.ALIGN_CENTER, surface.RENDER_HINT}
    | set(surface.DRAW_CALL_NAMES)
    | set(surface.ROUTE_NAMES)
    | {
        surface.SOLID_PEN_STYLE,
        surface.NO_PEN_STYLE,
        surface.NO_BRUSH,
        surface.PEN_CAP_STYLE,
        surface.FONT_WEIGHT_BOLD,
        surface.FONT_WEIGHT_NORMAL,
    }
)

PAINTED_VALUES = PUBLISHED_VALUES - NAMING_VALUES - PUBLISHED_KEYS

TOKEN_VALUES = {
    str(one)
    for one in token_payload()["tokens"].values()
    if one is not None and str(one)
}


def test_the_module_writes_no_value_the_surface_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"bot_node.js writes the painted values {written}"


def test_the_painted_set_still_holds_the_words_and_colours_the_card_shows():
    """The painted set is empty, so the check above measures nothing."""
    for shown in (
        SAMPLE["card"]["bot_data"]["symbol"],
        SAMPLE["font"]["family"],
        SAMPLE["tooltip"]["price_dash"],
        SAMPLE["defaults"]["symbol"],
        SAMPLE["tooltip"]["millions_format"],
        SAMPLE["formats"]["step_refusal"],
    ):
        assert shown in PAINTED_VALUES, shown


def test_the_module_writes_no_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"bot_node.js writes the token values {written}"


def test_the_module_writes_no_number_and_no_colour():
    assert MODULE_LITERALS["numbers"] == [], MODULE_LITERALS["numbers"]
    assert HEX_COLOUR.findall(MODULE_SOURCE) == []


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], MODULE_LITERALS["slashes"]


def test_the_module_names_only_the_surface_keys_it_reads(js: JsRuntime):
    js.push(SAMPLE)
    allowed = set(js.answer("declaredNames()"))
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_KEYS
    assert not written - allowed, sorted(written - allowed)


SPELLED_OUT_LINES = {
    "colour": 'var spelled = "' + str(SAMPLE["font"]["family"]) + '";',
    "token_value": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "symbol": 'var spelled = "' + SAMPLE["card"]["bot_data"]["symbol"] + '";',
    "volume": 'var spelled = "' + SAMPLE["tooltip"]["millions_format"] + '";',
    "dash": 'var spelled = "' + SAMPLE["tooltip"]["price_dash"] + '";',
    "card_width": "var spelled = " + str(surface.MIN_WIDTH_PX) + ";",
    "font_size": "var spelled = " + str(surface.SYMBOL_FONT_SIZE_PT) + ";",
    "number": "var spelled = 12;",
    "regex": "var spelled = /ab+c/;",
    "hex_colour": 'var spelled = "#00c8ff";',
}


def caught_by_scan(source: str) -> set:
    """Which of the five checks report on `source`."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if found["numbers"]:
        caught.add("number")
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & PAINTED_VALUES:
        caught.add("painted_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(SPELLED_OUT_LINES))
def test_the_literal_scan_names_a_line_that_spells_a_value_out(kind: str):
    assert caught_by_scan(SPELLED_OUT_LINES[kind]), kind


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals("// #00c8ff\nvar kept = " + json.dumps("kept") + ";")
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_spelled_out_value_is_caught_in_the_module_file_itself():
    """One line at a time goes into the shipped file and comes back out."""
    original = read_module().encode("utf-8")
    before = hashlib.sha256(original).hexdigest()
    caught_each = {}
    hashes = {}
    try:
        for kind in sorted(SPELLED_OUT_LINES):
            swap_module(MODULE_PATH, original + SPELLED_OUT_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(MODULE_PATH, original)
            hashes[kind] = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
    finally:
        swap_module(MODULE_PATH, original)
    unrestored = sorted(kind for kind, found in hashes.items() if found != before)
    assert unrestored == [], unrestored
    missed = sorted(kind for kind, found in caught_each.items() if not found)
    assert missed == [], missed
    assert caught_by_scan(MODULE_PATH.read_text(encoding="utf-8")) == set()


@pytest.mark.parametrize("name", CARD_NAMES)
def test_the_two_sides_hold_the_same_value_for_every_field(js: JsRuntime, name: str):
    payload = state_payload(name)
    js.push(payload)
    for field in sorted(payload):
        assert js.json(f"acervatorBotNode.field({json.dumps(field)})") == payload[field]


@pytest.mark.parametrize("name", CARD_NAMES)
def test_the_two_sides_hold_the_same_type_for_every_value(js: JsRuntime, name: str):
    payload = state_payload(name)
    js.push(payload)
    assert js.answer("kinds()") == python_kinds(payload)


def test_the_type_comparison_can_tell_a_number_from_its_text(js: JsRuntime):
    payload = state_payload("running")
    payload["scale_divisor"] = str(payload["scale_divisor"])
    js.push(payload)
    assert js.answer("kinds()")["scale_divisor"] == "string"
    assert python_kinds(state_payload("running"))["scale_divisor"] == "number"


@pytest.mark.parametrize("name", CARD_NAMES)
def test_the_module_carries_the_tooltip_the_surface_wrote(js: JsRuntime, name: str):
    payload = state_payload(name)
    js.push(payload)
    assert js.answer("card()")["tooltip"] == payload["card"]["tooltip"]


def test_a_hidden_identifier_reaches_the_module_masked(js: JsRuntime):
    payload = state_payload("running", HIDDEN_FIELDS)
    js.push(payload)
    shown = [one[3] for one in payload["drawing_calls"] if one[0] == "draw_text"]
    assert shown[0] == "****"
    assert surface.TOOLTIP_BOT_MASK in js.answer("card()")["tooltip"]
    assert "BTC-USD" not in js.answer("card()")["tooltip"]


def test_a_colour_label_alone_is_never_an_identity_on_this_card(js: JsRuntime):
    """Every colour label of this card appears in more than one group."""
    js.push(SAMPLE)
    groups = js.answer("labelGroups()")
    alone = sorted(name for name, where in groups.items() if len(where) == 1)
    assert alone == [], alone
    assert len(groups) == 13
    assert sorted(groups["running"]) == sorted(
        ["states.nebula", "states.matrix", "states.quantum", "states.ocean"]
        + ["leg_colors.nebula", "leg_colors.matrix"]
        + ["leg_colors.quantum", "leg_colors.ocean"]
    )


def test_one_colour_is_read_by_its_group_and_its_label_together(js: JsRuntime):
    js.push(SAMPLE)
    first = js.answer('colourAt("states", "matrix", "running")')
    second = js.answer('colourAt("leg_colors", "matrix", "running")')
    assert first != second, first
    assert first == js.answer('colourAt("states", "matrix", "running")')


def test_the_theme_order_comes_from_the_list_and_not_from_the_table(js: JsRuntime):
    """A bag keyed by a number loses its order, so the list carries it."""
    payload = state_payload("running")
    numeric = ("30", "4", "100")
    payload["theme"]["keys"] = list(numeric)
    payload["theme"]["table"] = {
        name: payload["theme"]["table"]["quantum"] for name in numeric
    }
    js.push(payload)
    assert js.answer("themeOrder()") == list(numeric)
    assert js.json("Object.keys(acervatorBotNode.field('theme').table)") != list(
        numeric
    )


def test_the_colour_and_state_orders_come_from_their_own_lists(js: JsRuntime):
    js.push(SAMPLE)
    assert js.answer("colourOrder()") == list(surface.THEME_COLOR_NAMES)
    assert js.answer("stateOrder()") == list(surface.STATE_NAMES)
    assert js.answer("colourOrder()") != sorted(surface.THEME_COLOR_NAMES)


def flat_line(one: Any) -> bool:
    """True when one drawing call is a line CSS can draw without turning."""
    return one[0] == "draw_line" and (one[1][0] == one[2][0] or one[1][1] == one[2][1])


def indices_of(payload: dict, wanted: Any) -> list:
    """Every place in the programme the calls `wanted` names are written."""
    return [index for index, one in enumerate(payload["drawing_calls"]) if wanted(one)]


def test_the_drawn_parts_keep_the_order_the_surface_painted(js: JsRuntime):
    js.push(SAMPLE)
    drawn = js.answer("drawnParts()")
    places = [one["at"] for one in drawn]
    assert places == sorted(places), places
    assert len(set(places)) == len(places)


@pytest.mark.parametrize(
    "part,wanted",
    [
        ("ground", lambda one: one[0] == "fill_rect"),
        ("dot", lambda one: one[0] == "draw_ellipse"),
        ("words", lambda one: one[0] == "draw_text"),
        ("rule", flat_line),
    ],
)
def test_each_drawn_part_stands_where_its_own_call_stands(
    js: JsRuntime, part: str, wanted: Any
):
    js.push(SAMPLE)
    drawn = js.answer("drawnParts()")
    places = [one["at"] for one in drawn if one["part"] == part]
    assert places == indices_of(SAMPLE, wanted), part


def test_every_name_the_card_draws_is_its_own(js: JsRuntime):
    js.push(SAMPLE)
    written = js.answer("drawnKeys()")
    assert len(written) == len(set(written)), "two drawn parts answer to one name"


def test_the_name_check_reports_two_parts_drawn_from_one_call(js: JsRuntime):
    """Every name is its own above, so this proves the check can differ."""
    payload = state_payload("running")
    calls = payload["drawing_calls"]
    at = indices_of(payload, lambda one: one[0] == "draw_ellipse")[0]
    payload["drawing_calls"] = calls[: at + 1] + [calls[at]] + calls[at + 1 :]
    js.push(payload)
    written = js.answer("drawnKeys()")
    assert len(written) == len(set(written)) + 1


def test_a_reordered_programme_names_the_two_calls_that_moved(js: JsRuntime):
    js.push(SAMPLE)
    before = js.answer("drawnKeys()")
    payload = state_payload("running")
    calls = payload["drawing_calls"]
    first = indices_of(payload, lambda one: one[0] == "draw_ellipse")[0]
    last = indices_of(payload, lambda one: one[0] == "draw_ellipse")[-1]
    calls[first], calls[last] = calls[last], calls[first]
    js.push(payload)
    after = js.answer("drawnKeys()")
    assert sorted(after) == sorted(before), "a pure reorder invents no new name"
    moved = sorted(one for one in before if before.index(one) != after.index(one))
    assert len(moved) == 2, moved
    assert after.index(moved[0]) == before.index(moved[1])
    assert after.index(moved[1]) == before.index(moved[0])


def test_two_swapped_texts_are_named_by_their_own_labels(js: JsRuntime):
    payload = state_payload("running")
    texts = [one for one in payload["drawing_calls"] if one[0] == "draw_text"]
    texts[0][3], texts[1][3] = texts[1][3], texts[0][3]
    js.push(payload)
    found = dict(js.answer("labelOrder()"))
    assert found["symbol"] == surface.fmt_pnl(12.5)
    assert found["pnl"] == "BTC-USD"


def test_the_three_texts_answer_to_the_labels_the_surface_places(js: JsRuntime):
    js.push(SAMPLE)
    assert [one[0] for one in js.answer("labelOrder()")] == ["symbol", "pnl", "bot-id"]


def test_a_text_outside_every_published_box_is_named_as_unknown(js: JsRuntime):
    payload = state_payload("running")
    for one in payload["drawing_calls"]:
        if one[0] == "draw_text":
            one[1][1] = one[1][1] + 1.0
    found = js.push(payload)
    assert [one["fault"] for one in found["faults"]] == ["unknown-label"] * 3
    assert [one[0] for one in js.answer("labelOrder()")] == [None, None, None]


def test_a_symbol_carrying_an_image_tag_is_named_as_markup(js: JsRuntime):
    payload = surface.view_model(
        {"card": card(bot_data=data(symbol=MARKUP_TEXT)), "hidden": []}
    )
    found = js.push(payload)
    assert [one["fault"] for one in found["faults"]] == ["markup"]
    assert found["faults"][0]["detail"] == MARKUP_TEXT
    assert js.push(SAMPLE)["faults"] == []


def test_an_eight_digit_hex_where_a_colour_belongs_is_refused(js: JsRuntime):
    payload = state_payload("running")
    payload["theme"]["table"]["quantum"]["bg"] = "#80ff0000"
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "qt-colour"]
    assert [one["detail"] for one in named] == ["#80ff0000"]
    assert js.answer('colourAt("theme", "quantum", "bg")') is None
    assert js.answer('colourAt("theme", "nebula", "bg")') is not None


def test_a_colour_of_the_wrong_shape_is_refused(js: JsRuntime):
    payload = state_payload("running")
    payload["theme"]["table"]["ocean"]["bg"] = [1, 2, 3]
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "colour-shape"]
    assert [one["field"] for one in named] == ["bg"]


def test_a_colour_of_no_number_at_all_is_refused(js: JsRuntime):
    payload = state_payload("running")
    payload["theme"]["table"]["ocean"]["bg"] = [1, 2, 3, None]
    found = js.push(payload)
    assert [one["fault"] for one in found["faults"]] == ["not-finite"]


def test_a_missing_alpha_divisor_is_named_and_paints_nothing(js: JsRuntime):
    payload = state_payload("running")
    payload["theme"]["opaque_alpha"] = 0
    found = js.push(payload)
    kinds = {one["fault"] for one in found["faults"]}
    assert "no-alpha-divisor" in kinds
    assert js.answer('colourAt("theme", "quantum", "bg")') is None


def test_the_module_builds_one_css_colour_from_the_four_qt_bytes(js: JsRuntime):
    js.push(SAMPLE)
    written = js.answer('colourAt("theme", "quantum", "particle")')
    red, green, blue, alpha = surface.THEME_COLORS["quantum"]["particle"]
    assert written == (
        f"rgba({red},{green},{blue},calc({alpha} / {surface.OPAQUE_ALPHA}))"
    )


def test_a_missing_group_is_named_rather_than_drawn(js: JsRuntime):
    payload = state_payload("running")
    del payload["pens"]["cap_style"]
    payload["font"]["family"] = None
    found = js.push(payload)
    named = {(one["where"], one["field"], one["fault"]) for one in found["faults"]}
    assert ("pens", "cap_style", "missing") in named
    assert ("font", "family", "null") in named


HOSTILE_CARDS = {
    "a_missing_symbol": card(bot_data=data(symbol=None)),
    "a_number_where_a_symbol_belongs": card(bot_data=data(symbol=42)),
    "a_two_hundred_character_symbol": card(bot_data=data(symbol=LONG_TEXT)),
    "markup_in_the_symbol": card(bot_data=data(symbol=MARKUP_TEXT)),
    "a_newline_in_the_symbol": card(bot_data=data(symbol=NEWLINE_TEXT)),
    "a_duplicate_name": card(bot_data=data(symbol="abcdef01")),
    "an_empty_symbol": card(bot_data=data(symbol="")),
    "a_two_hundred_character_bot_id": card(bot_data=data(bot_id=LONG_TEXT)),
    "no_stats_at_all": card(bot_data=data(stats={})),
    "a_profit_at_not_a_number": card(bot_data=data(stats=stats(realised_pnl=math.nan))),
    "a_profit_at_infinity": card(bot_data=data(stats=stats(realised_pnl=math.inf))),
    "a_profit_at_minus_infinity": card(
        bot_data=data(stats=stats(realised_pnl=-math.inf))
    ),
    "a_thousand_million_million_profit": card(
        bot_data=data(stats=stats(realised_pnl=10**24))
    ),
    "a_ring_at_not_a_number": card(trade_pulses=[math.nan]),
    "a_speck_at_not_a_number": card(particles=[(math.nan, 30.0, 1.0, 1.0, 0.5, 2.0)]),
    "a_card_of_no_size": card(width_px=0, height_px=0),
}

HOSTILE_NAMES = sorted(HOSTILE_CARDS)


def bridged(payload: Any) -> Any:
    """`payload` with every number JSON cannot write replaced by nothing."""
    if isinstance(payload, dict):
        return {name: bridged(one) for name, one in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [bridged(one) for one in payload]
    if isinstance(payload, float) and not math.isfinite(payload):
        return None
    return payload


def surface_answer(name: str) -> Any:
    """The payload for one hostile card, or the refusal the surface raises."""
    try:
        return bridged(surface.view_model({"card": HOSTILE_CARDS[name], "hidden": []}))
    except (ValueError, TypeError, AttributeError) as exc:
        return type(exc).__name__


HOSTILE_ANSWERS = {name: surface_answer(name) for name in HOSTILE_NAMES}
DRAWN_HOSTILE = [
    name for name in HOSTILE_NAMES if isinstance(HOSTILE_ANSWERS[name], dict)
]

#: REFUSED_HOSTILE names what the surface refuses to paint, measured here.
REFUSED_HOSTILE = {"a_ring_at_not_a_number": "ValueError"}

#: The fault each hostile card earns in the module, measured on this host.
HOSTILE_FAULTS = {
    "markup_in_the_symbol": {"markup"},
    "a_speck_at_not_a_number": {"not-finite"},
}


def test_the_surface_refuses_the_cards_it_cannot_paint():
    refused = {
        name: HOSTILE_ANSWERS[name]
        for name in HOSTILE_NAMES
        if not isinstance(HOSTILE_ANSWERS[name], dict)
    }
    assert refused == REFUSED_HOSTILE, refused


@pytest.mark.parametrize("name", DRAWN_HOSTILE)
def test_a_hostile_card_draws_without_the_module_throwing(js: JsRuntime, name: str):
    found = js.push(HOSTILE_ANSWERS[name])
    assert found["declared"]["calls"] == found["held"]["calls"], name
    assert isinstance(found["drawn"]["dots"], int)


@pytest.mark.parametrize("name", DRAWN_HOSTILE)
def test_a_hostile_card_names_only_the_faults_it_earns(js: JsRuntime, name: str):
    found = js.push(HOSTILE_ANSWERS[name])
    earned = HOSTILE_FAULTS.get(name, set())
    assert {one["fault"] for one in found["faults"]} == earned, found["faults"]


def test_a_number_javascript_cannot_read_leaves_the_bridge_frame_unreadable(
    js: JsRuntime,
):
    """The frame encoder writes NaN, which JSON.parse refuses outright."""
    raw = surface.view_model(
        {"card": HOSTILE_CARDS["a_speck_at_not_a_number"], "hidden": []}
    )
    written = json.dumps({"id": 1, "ok": True, "result": raw})
    assert "NaN" in written
    js.bind_json("FRAME", written)
    js.bind_json("KEPT", json.dumps(bridged(raw)))
    reads = (
        "(function (text) { try { JSON.parse(text); }"
        " catch (err) { return err.name; } return null; })"
    )
    assert js.json(reads + "(JSON.parse(FRAME))") == "SyntaxError"
    assert js.json(reads + "(JSON.parse(KEPT))") is None


def test_a_scalar_where_a_list_belongs_is_named_rather_than_walked(js: JsRuntime):
    payload = state_payload("running")
    payload["drawing_calls"] = payload["drawing_calls"] + [7, None, "words"]
    found = js.push(payload)
    assert [one["fault"] for one in found["faults"]] == ["not-a-list"] * 3
    assert [one["detail"] for one in found["faults"]] == ["number", "null", "string"]


def test_a_scalar_where_a_bag_belongs_is_named_rather_than_walked(js: JsRuntime):
    payload = state_payload("running")
    payload["theme"] = 7
    payload["states"] = None
    found = js.push(payload)
    kinds = {(one["field"], one["fault"]) for one in found["faults"]}
    assert ("theme", "not-an-object") in kinds
    assert ("states", "not-an-object") in kinds
    assert js.answer("themeOrder()") == []


def test_a_card_of_no_size_draws_a_ground_of_no_size(js: JsRuntime):
    js.push(HOSTILE_ANSWERS["a_card_of_no_size"])
    assert js.answer("card()")["width_px"] == 0
    assert js.answer("drawnKeys()")[0].endswith("0,0,0,0")


class Browser:
    """Browser opens the real renderer page in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._view.resize(*VIEW_SIZE_PX)
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
        """Spins until the page defines the module, which loadFinished does not."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetBotNode") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the module: readyState "
            + str(self.js("document.readyState"))
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
    """The page, or a skip when Chromium is not installed with Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


STYLE_NAMES = [
    "position",
    "left",
    "top",
    "width",
    "height",
    "minWidth",
    "minHeight",
    "backgroundColor",
    "backgroundImage",
    "borderRadius",
    "boxSizing",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "color",
    "fontFamily",
    "fontSize",
    "fontWeight",
    "display",
    "justifyContent",
    "alignItems",
    "whiteSpace",
    "overflow",
    "textOverflow",
    "userSelect",
]

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

PAGE_HELPERS = (
    "window.HOST = document.getElementById('bot-node-host');"
    "if (!window.HOST) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'bot-node-host';"
    "  document.body.appendChild(window.HOST); }"
    "window.HOST.style.width = " + json.dumps(str(HOST_WIDTH_PX) + "px") + ";"
    "window.HOST.style.height = " + json.dumps(str(HOST_HEIGHT_PX) + "px") + ";"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeStyle = function (tag, cssText, names) {"
    "  var probe = document.createElement(tag);"
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
    "        text: own,"
    "        width: el.getBoundingClientRect().width,"
    "        height: el.getBoundingClientRect().height,"
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


def give_tokens(browser: Browser) -> int:
    """Push the tokens into the page and apply them to the document."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_screen(browser: Browser, payload: dict) -> list:
    """Render `payload` into window.HOST and return what READ_PARTS finds."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetBotNode(JSON.parse(window.PAYLOAD));"
        "acervatorBotNode.renderCard(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def by_part(parts: list, name: str) -> list:
    return [one for one in parts if one["attrs"].get("data-part") == name]


def one_part(parts: list, name: str) -> dict:
    found = by_part(parts, name)
    assert len(found) == 1, f"{len(found)} parts named {name}"
    return found[0]


def probe(browser: Browser, body: str, names: list) -> dict:
    """The computed values a bare div takes from the whole declaration."""
    return browser.parsed(
        "window.probeStyle("
        + json.dumps("div")
        + ", "
        + json.dumps(body)
        + ", "
        + json.dumps(sorted(set(names)))
        + ")"
    )


def css_colour(value: list) -> str:
    """The CSS text the four Qt bytes of `value` mean."""
    red, green, blue, alpha = value
    return f"rgba({red},{green},{blue},calc({alpha} / {surface.OPAQUE_ALPHA}))"


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorBotNode") == "object"
    assert browser.js("typeof window.acervatorSetBotNode") == "function"
    assert browser.js("typeof window.acervatorLoadBotNode") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_screen(browser, SAMPLE)
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_every_element_the_card_draws_carries_a_name(browser: Browser):
    draw_screen(browser, SAMPLE)
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} elements carry no data-part"
    assert every > 0


def test_the_name_count_can_report_an_element_without_one(browser: Browser):
    """The counts match above, so this payload proves they can differ."""
    draw_screen(browser, SAMPLE)
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


def test_the_card_draws_one_part_of_each_kind_it_declares(browser: Browser):
    parts = draw_screen(browser, SAMPLE)
    found = {one["attrs"]["data-part"] for one in parts}
    assert found == {"card", "ground", "dot", "rule", "words", "body"}


def test_the_ground_matches_the_fill_the_surface_wrote(browser: Browser):
    parts = draw_screen(browser, SAMPLE)
    ground = one_part(parts, "ground")
    fill = next(one for one in SAMPLE["drawing_calls"] if one[0] == "fill_rect")
    body = (
        "position:absolute;"
        f"left:{fill[1][0]}px;top:{fill[1][1]}px;"
        f"width:{fill[1][2]}px;height:{fill[1][3]}px;"
        f"background-color:{css_colour(fill[2])}"
    )
    wanted = probe(browser, body, STYLE_NAMES)
    for name in ("position", "left", "top", "width", "height", "backgroundColor"):
        assert ground["style"][name] == wanted[name], name


def test_the_symbol_text_matches_the_font_and_box_the_surface_wrote(browser: Browser):
    parts = draw_screen(browser, SAMPLE)
    words = [one for one in by_part(parts, "words")]
    symbol = next(one for one in words if one["attrs"]["data-label"] == "symbol")
    labels = SAMPLE["labels"]
    font = SAMPLE["font"]
    colours = SAMPLE["theme"]["colors"]
    body = (
        "position:absolute;"
        f"left:{labels['left_px']}px;top:{labels['symbol_top_px']}px;"
        f"width:{SAMPLE['card']['width_px']}px;"
        f"height:{labels['symbol_height_px']}px;"
        "display:flex;justify-content:center;align-items:center;"
        "white-space:nowrap;overflow:hidden;text-overflow:clip;user-select:none;"
        f"color:{css_colour(colours['text'])};"
        f"font-family:{font['family']};"
        f"font-size:{font['symbol_size_pt']}pt;"
        f"font-weight:{font['bold_value']}"
    )
    wanted = probe(browser, body, STYLE_NAMES)
    for name in STYLE_NAMES:
        if name in ("backgroundImage", "borderRadius", "boxSizing"):
            continue
        assert symbol["style"][name] == wanted[name], name
    assert symbol["text"] == SAMPLE["card"]["bot_data"]["symbol"]


def test_a_probe_missing_one_declaration_reads_a_different_value(browser: Browser):
    """The whole declaration is given above, so a short one differs."""
    parts = draw_screen(browser, SAMPLE)
    symbol = next(
        one for one in by_part(parts, "words") if one["attrs"]["data-label"] == "symbol"
    )
    short = probe(browser, "position:absolute;width:112px", ["width", "fontSize"])
    assert short["fontSize"] != symbol["style"]["fontSize"]


def test_one_ellipse_is_widened_by_the_pen_qt_straddles_its_edge_with(
    browser: Browser,
):
    parts = draw_screen(browser, SAMPLE)
    calls = SAMPLE["drawing_calls"]
    at = max(index for index, one in enumerate(calls) if one[0] == "draw_ellipse")
    iris = next(
        one for one in by_part(parts, "dot") if one["attrs"]["data-at"] == str(at)
    )
    _, centre, rx, ry = calls[at]
    pen = next(
        one for one in reversed(calls[:at]) if one[0] == "set_pen" and one[3] != "NoPen"
    )
    edge = pen[2]
    half = SAMPLE["pens"]["half_width_ratio"]
    body = (
        "position:absolute;box-sizing:border-box;"
        f"left:{centre[0] - rx - edge * half}px;"
        f"top:{centre[1] - ry - edge * half}px;"
        f"width:{rx + rx + edge}px;height:{ry + ry + edge}px;"
        "border-radius:50%;"
        f"border:{edge}px solid {css_colour(pen[1])}"
    )
    wanted = probe(browser, body, STYLE_NAMES)
    for name in ("left", "top", "width", "height", "borderTopWidth", "borderTopColor"):
        assert iris["style"][name] == wanted[name], name


def test_one_flat_line_is_lengthened_by_the_square_cap_qt_uses(browser: Browser):
    parts = draw_screen(browser, SAMPLE)
    calls = SAMPLE["drawing_calls"]
    at = next(
        index
        for index, one in enumerate(calls)
        if one[0] == "draw_line" and one[1][1] == one[2][1]
    )
    rule = next(
        one for one in by_part(parts, "rule") if one["attrs"]["data-at"] == str(at)
    )
    _, first, last = calls[at]
    pen = next(one for one in reversed(calls[:at]) if one[0] == "set_pen")
    edge = pen[2]
    half = SAMPLE["pens"]["half_width_ratio"]
    body = (
        "position:absolute;"
        f"left:{min(first[0], last[0]) - edge * half}px;"
        f"top:{first[1] - edge * half}px;"
        f"width:{abs(last[0] - first[0]) + edge}px;height:{edge}px;"
        f"background-color:{css_colour(pen[1])}"
    )
    wanted = probe(browser, body, STYLE_NAMES)
    for name in ("left", "top", "width", "height", "backgroundColor"):
        assert rule["style"][name] == wanted[name], name


def test_rewriting_a_design_token_moves_nothing_on_this_card(browser: Browser):
    """No card size resolves to a token, so a rewritten token moves nothing."""
    before = draw_screen(browser, SAMPLE)
    browser.js(
        "document.documentElement.style.setProperty('--acv-radius-card', '99px');"
        "document.documentElement.style.setProperty('--acv-type-small', '99px');"
    )
    browser.settle(SETTLE_MS)
    after = json.loads(browser.js(READ_PARTS))
    assert [one["style"] for one in after] == [one["style"] for one in before]


def test_the_token_rewrite_moves_an_element_that_asks_for_the_token(browser: Browser):
    """The rewrite above moved nothing, so this proves the rewrite lands."""
    browser.js(
        "document.documentElement.style.setProperty('--acv-radius-card', '99px');"
        "window.PROBE = document.createElement('div');"
        "window.PROBE.style.cssText = 'width: var(--acv-radius-card)';"
        "document.body.appendChild(window.PROBE);"
    )
    found = browser.js("getComputedStyle(window.PROBE).width")
    browser.js("window.PROBE.remove();")
    assert found == "99px"


TOKEN_REFUSALS = {
    "min_width_px": surface.MIN_WIDTH_PX,
    "min_height_px": surface.MIN_HEIGHT_PX,
    "symbol_height_px": surface.SYMBOL_RECT_HEIGHT_PX,
    "bot_id_height_px": surface.BOT_ID_RECT_HEIGHT_PX,
    "pnl_bottom_px": surface.PNL_RECT_BOTTOM_PX,
    "bracket_length_px": surface.BRACKET_LENGTH_PX,
    "bracket_pen_width_px": surface.BRACKET_PEN_WIDTH_PX,
    "thorax_pen_width_px": surface.THORAX_PEN_WIDTH_PX,
    "hind_pen_width_px": surface.HIND_LEG_PEN_WIDTH_PX,
    "symbol_size_pt": surface.SYMBOL_FONT_SIZE_PT,
    "bot_id_size_pt": surface.BOT_ID_FONT_SIZE_PT,
}


@pytest.mark.parametrize("name", sorted(TOKEN_REFUSALS))
def test_no_card_size_is_painted_through_a_design_token(js: JsRuntime, name: str):
    js.push(SAMPLE)
    written = js.json(f"acervatorBotNode.pixels({TOKEN_REFUSALS[name]})")
    assert written == f"{TOKEN_REFUSALS[name]}px", name


def test_the_token_lookup_would_answer_for_a_value_one_token_carries(js: JsRuntime):
    """The sizes refuse above, so this proves the lookup is not silent."""
    js.push(SAMPLE)
    assert js.json(f"acervatorBotNode.variableFor({dss.RADIUS_CARD})") is not None
    assert js.json(f"acervatorBotNode.variableFor({surface.MIN_WIDTH_PX})") is None


def test_an_image_tag_in_the_symbol_draws_as_characters(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    payload = surface.view_model(
        {"card": card(bot_data=data(symbol=MARKUP_TEXT)), "hidden": []}
    )
    parts = draw_screen(browser, payload)
    symbol = next(
        one for one in by_part(parts, "words") if one["attrs"]["data-label"] == "symbol"
    )
    browser.settle(SETTLE_MS)
    assert symbol["text"] == MARKUP_TEXT
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0
    assert browser.parsed("window.HOST.innerHTML.indexOf('<img')") == -1
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_image_check_would_see_an_image_the_page_did_make(browser: Browser):
    """No image is created above, so this proves the count can see one."""
    draw_screen(browser, SAMPLE)
    browser.js("window.HOST.firstChild.appendChild(document.createElement('img'));")
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 1


def test_a_two_hundred_character_symbol_is_clipped_and_never_stretches(
    browser: Browser,
):
    payload = surface.view_model(
        {"card": card(bot_data=data(symbol=LONG_TEXT)), "hidden": []}
    )
    parts = draw_screen(browser, payload)
    symbol = next(
        one for one in by_part(parts, "words") if one["attrs"]["data-label"] == "symbol"
    )
    assert symbol["width"] == float(payload["card"]["width_px"])
    assert symbol["style"]["overflow"] == "hidden"
    assert symbol["text"] == LONG_TEXT


def test_the_card_never_grows_past_the_width_the_surface_gives_it(browser: Browser):
    parts = draw_screen(browser, SAMPLE)
    root = one_part(parts, "card")
    assert root["width"] == float(SAMPLE["card"]["width_px"])
    assert root["height"] == float(SAMPLE["card"]["height_px"])
    assert root["style"]["minWidth"] == f"{surface.MIN_WIDTH_PX}px"


def test_the_body_mount_names_the_curves_and_slants_it_keeps(browser: Browser):
    parts = draw_screen(browser, SAMPLE)
    mounts = by_part(parts, "body")
    assert sum(int(one["attrs"]["data-paths"]) for one in mounts) == 7
    assert sum(int(one["attrs"]["data-slopes"]) for one in mounts) == 12
    assert all(one["attrs"]["data-slot"] == "body" for one in mounts)


def test_the_tooltip_reaches_the_card_as_a_title(browser: Browser):
    parts = draw_screen(browser, SAMPLE)
    root = one_part(parts, "card")
    assert root["attrs"]["title"] == SAMPLE["card"]["tooltip"]


@pytest.mark.parametrize("name", ["running", "idle", "a_loss", "theme_matrix"])
def test_the_drawn_card_carries_the_same_counts_the_module_reports(
    browser: Browser, name: str
):
    payload = state_payload(name)
    parts = draw_screen(browser, payload)
    kinds = [one[0] for one in payload["drawing_calls"]]
    assert len(by_part(parts, "dot")) == kinds.count("draw_ellipse")
    assert len(by_part(parts, "words")) == kinds.count("draw_text")
    assert len(by_part(parts, "ground")) == kinds.count("fill_rect")
