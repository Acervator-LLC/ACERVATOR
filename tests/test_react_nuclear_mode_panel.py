"""What ``src/gui/web/nuclear_mode_panel.js`` draws from the Nuclear surface."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.gui.main_tabs import design_system_surface as dts
from src.gui.main_tabs import nuclear_mode_panel_surface as nmp
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "nuclear_mode_panel.js"
TOKENS_PATH = WEB / "design_tokens.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
HEADER_PATH = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

LOCK_PATH = Path(tempfile.gettempdir()) / "acervator_nuclear_panel_swap.lock"
LOCK_ATTEMPTS = 400_000

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2
TICK_SETTLE_MS = 1800
HOST_WIDTH_CSS = "1200px"

EIGHT_DIGIT = re.compile(r"#[0-9a-fA-F]{8}\b")

#: The header border written back to front, the shape Qt and CSS disagree on.
SWAPPED_BORDER_HEX = "#ffcc4444"
RGBA_CALL = re.compile(r"rgba\(([^)]*)\)")
ALPHA_SCALE = 255
FIELD_COUNT = 4


@contextlib.contextmanager
def module_held(attempts: int = LOCK_ATTEMPTS):
    """Takes LOCK_PATH so one worker at a time swaps the module."""
    handle = None
    for _ in range(attempts):
        try:
            handle = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            continue
        except PermissionError:
            continue
    if handle is None:
        raise AssertionError(f"{LOCK_PATH} stayed taken for all {attempts} attempts")
    try:
        yield
    finally:
        os.close(handle)
        LOCK_PATH.unlink(missing_ok=True)


with module_held():
    MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

BOTS = [{"symbol": "BTC/USD"}, {"symbol": "ETH/USD"}, {"symbol": "BTC/USD"}]
WIRES = [{"from": "BTC/USD"}, {"from": "ETH/USD"}]
LOOP = object()

SNAPSHOT = {
    "running": True,
    "uptime_seconds": 91.25,
    "fleet_size": 3,
    "symbols": 2,
    "wires_loaded": 2,
    "current_cycle": 4,
    "cycles_completed": 3,
    "noise_pct": 0.175,
    "load_multiplier": 1.5,
    "cooling": False,
    "load_sensed": True,
    "total_candles": 12000,
    "total_trades": 41,
    "total_exceptions": 0,
    "failed_cycles": 0,
    "last_error": "TimeoutError: tablet read stalled",
}


def fleet_world(**extra) -> nmp.PanelWorld:
    return nmp.PanelWorld(bot_configs=BOTS, smart_wires=WIRES, **extra)


def fresh_model() -> nmp.PanelModel:
    return nmp.PanelModel(fleet_world())


def empty_model() -> nmp.PanelModel:
    return nmp.PanelModel(nmp.PanelWorld())


def refused_model() -> nmp.PanelModel:
    return nmp.PanelModel(
        nmp.PanelWorld(loader_error=RuntimeError("bot_state.json is locked"))
    )


def running_model() -> nmp.PanelModel:
    model = nmp.PanelModel(fleet_world(loop=LOOP, snapshots=[SNAPSHOT]))
    model.start()
    return model


def filled_model() -> nmp.PanelModel:
    model = running_model()
    model.refresh_status()
    return model


def stopped_model() -> nmp.PanelModel:
    model = filled_model()
    model.stop()
    return model


STATES = {
    "fresh": fresh_model,
    "empty": empty_model,
    "refused": refused_model,
    "running": running_model,
    "filled": filled_model,
    "stopped": stopped_model,
}
STATE_NAMES = tuple(STATES)
FULL_STATE = "filled"


def payload_of(model: nmp.PanelModel) -> dict:
    """The bridge answer for one driven model, after a JSON round trip."""
    payload = nmp.view_model({})
    payload["screen"] = model.build()
    return json.loads(json.dumps(payload, ensure_ascii=True))


def state_payload(name: str) -> dict:
    return payload_of(STATES[name]())


def token_payload() -> dict:
    return json.loads(json.dumps(dts.view_model({}), ensure_ascii=True))


def screen_of(payload: dict) -> dict:
    return payload["screen"]


def base_declarations(sheet: str) -> list:
    """Every property and value found in one sheet's stateless bodies."""
    bodies = []
    for chunk in str(sheet).split("}"):
        parts = chunk.split("{")
        if len(parts) > 1:
            if ":" not in parts[0].strip():
                bodies.append("{".join(parts[1:]))
        elif chunk.strip():
            bodies.append(chunk)
    found = []
    for one in ";".join(bodies).split(";"):
        head, _, tail = one.partition(":")
        if head.strip() and tail.strip():
            found.append((head.strip(), tail.strip()))
    return found


def fraction_alpha(value: str) -> str:
    """One Qt rgba rewritten so its alpha byte reads as a CSS fraction."""
    found = RGBA_CALL.search(value)
    if not found:
        return value
    fields = [one.strip() for one in found.group(1).split(",")]
    if len(fields) != FIELD_COUNT or "." in fields[3] or "%" in fields[3]:
        return value
    fields[3] = repr(int(fields[3]) / ALPHA_SCALE)
    return value.replace(found.group(0), "rgba(" + ",".join(fields) + ")")


def css_declarations(sheet: str) -> list:
    """The declarations a browser may paint, with each alpha byte scaled."""
    return [
        (prop, fraction_alpha(value))
        for prop, value in base_declarations(sheet)
        if not EIGHT_DIGIT.search(value)
    ]


def css_body(sheet: str) -> str:
    return ";".join(prop + ":" + value for prop, value in css_declarations(sheet))


def painted_values() -> set:
    """Every painted string the states publish, found by walking each node."""
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
            return
        if isinstance(node, list):
            for value in node:
                walk(value)
            return
        if isinstance(node, str) and node:
            found.add(node)

    for name in STATE_NAMES:
        walk(screen_of(state_payload(name)))
    return found


def published_keys() -> set:
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                found.add(name)
                walk(value)
            return
        if isinstance(node, list):
            for value in node:
                walk(value)

    for name in STATE_NAMES:
        walk(state_payload(name))
    return found


SKIN_VALUES = painted_values()
PUBLISHED_KEYS = published_keys()
#: Every published string that is a look on screen rather than a field name.
LOOKS = SKIN_VALUES - PUBLISHED_KEYS
TOKEN_VALUES = {
    str(one)
    for one in json.dumps(token_payload()).split('"')
    if HEX_COLOUR.fullmatch(str(one))
}
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Values the module may write because each names a thing, not a look.
NAMED_VALUES = sorted(
    {
        "nuclear_mode_panel.state",
        "reload_button_clicked",
        "start_button_clicked",
        "stop_button_clicked",
        "refresh_timer_tick",
        "AlignLeft",
    }
)


class JsRuntime(JsEngine):
    """One engine running the panel module at MODULE_PATH, with its setter."""

    module_path = MODULE_PATH
    setter = "acervatorSetNuclearPanel"

    def load_widgets(self) -> None:
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def load_header(self) -> None:
        self.run(HEADER_PATH.read_text(encoding="utf-8"))

    def load_tokens(self) -> None:
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def answer(self, name: str) -> Any:
        return self.json("acervatorNuclearPanel." + name + "()")

    def of(self, name: str, value: Any) -> Any:
        self.bind_json("ARG", value)
        return self.json("acervatorNuclearPanel." + name + "(JSON.parse(ARG))")


@pytest.fixture()
def bare(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def js(bare: JsRuntime) -> JsRuntime:
    bare.load_widgets()
    bare.load_header()
    return bare


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    declared = set(js.answer("declaredNames"))
    missing = sorted(set(payload) - declared)
    assert not missing, f"{len(missing)} published fields have no answer: {missing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_names_no_field_the_surface_leaves_out(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.answer("heldNames") == js.answer("declaredNames")


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_declared_and_held_counts_agree_in_every_state(js: JsRuntime, state: str):
    found = js.push(state_payload(state))
    assert found["declared"] == found["held"], found


def test_the_counts_part_when_the_payload_drops_a_bag(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    screen_of(payload).pop("status_card")
    found = js.push(payload)
    assert found["held"]["screen"] < found["declared"]["screen"]
    assert ("screen", "status_card", "missing") in fault_rows(js)


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_counts_every_status_row_the_surface_lays_out(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    found = js.push(payload)
    laid = screen_of(payload)["status_card"]
    assert found["cells"] == len(laid["cells"]) + 1
    assert found["status_fields"] == len(payload["status_fields"])


def fault_rows(js: JsRuntime) -> set:
    return {(one["where"], one["field"], one["fault"]) for one in js.answer("faults")}


def swapped_border_payload() -> dict:
    """One payload whose header border is written as eight hex digits."""
    payload = state_payload("fresh")
    card = screen_of(payload)["header_card"]
    card["style"] = card["style"].replace(nmp.HEADER_CARD_BORDER, SWAPPED_BORDER_HEX)
    return payload


def test_the_surface_publishes_no_border_qt_reads_back_to_front():
    sheet = screen_of(state_payload("fresh"))["header_card"]["style"]
    assert EIGHT_DIGIT.findall(sheet) == []
    assert nmp.HEADER_CARD_BORDER in sheet


def test_the_module_names_no_colour_fault_on_the_shipped_border(js: JsRuntime):
    js.push(state_payload("fresh"))
    assert [one for one in js.answer("faults") if one["fault"] == "qt-colour"] == []


def test_the_refusal_returns_when_the_border_carries_eight_digits(js: JsRuntime):
    js.push(swapped_border_payload())
    named = [one for one in js.answer("faults") if one["fault"] == "qt-colour"]
    assert named == [
        {
            "where": "header_card",
            "field": "border",
            "fault": "qt-colour",
            "detail": "1px solid " + SWAPPED_BORDER_HEX,
        }
    ], named


def test_the_border_reaches_the_page_and_a_swapped_one_does_not(js: JsRuntime):
    sheet = screen_of(state_payload("fresh"))["header_card"]["style"]
    written = "1px solid " + nmp.HEADER_CARD_BORDER
    assert js.of("styleOf", sheet)["border"] == fraction_alpha(written)
    swapped = screen_of(swapped_border_payload())["header_card"]["style"]
    assert "border" not in js.of("styleOf", swapped)


def test_the_alpha_scale_the_module_publishes_is_the_widest_qt_byte(js: JsRuntime):
    assert js.answer("alphaScale") == ALPHA_SCALE


def test_the_header_alpha_byte_is_repainted_as_the_fraction_css_reads(js: JsRuntime):
    js.push(state_payload("fresh"))
    rewritten = [
        one for one in js.answer("alphaRewrites") if one["property"] == "background"
    ]
    assert len(rewritten) == 1, rewritten
    one = rewritten[0]
    assert one["where"] == "header_card"
    assert one["written"] == "rgba(255,200,80,8)"
    assert one["painted"] == fraction_alpha(one["written"])


def test_a_fractional_alpha_is_left_exactly_as_the_surface_wrote_it(js: JsRuntime):
    payload = state_payload("fresh")
    card = screen_of(payload)["header_card"]
    card["style"] = card["style"].replace("80,8)", "80,0.5)")
    js.push(payload)
    assert [
        one for one in js.answer("alphaRewrites") if one["property"] == "background"
    ] == []


def test_the_module_writes_the_alpha_the_surface_meant(js: JsRuntime):
    js.push(state_payload("fresh"))
    painted = [
        one for one in js.answer("alphaRewrites") if one["property"] == "background"
    ][0]["painted"]
    assert float(RGBA_CALL.search(painted).group(1).split(",")[3]) == 8 / ALPHA_SCALE


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_publishes_the_order_of_every_bag_it_draws(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    screen = screen_of(payload)
    found = js.answer("orders")
    assert found["layout"] == screen["layout"]["order"]
    assert found["fleet_card"] == screen["fleet_card"]["order"]
    assert found["config_card"] == screen["config_card"]["order"]
    assert found["status_card"] == [
        one["key"] for one in screen["status_card"]["cells"]
    ] + [screen["status_card"]["last_exception"]["key"]]


def test_the_buttons_bag_publishes_no_order_so_the_module_names_one(js: JsRuntime):
    payload = state_payload("fresh")
    assert "order" not in screen_of(payload)["buttons"]
    js.push(payload)
    assert js.answer("orders")["buttons"] == ["start", "stop"]


def test_a_reordered_card_list_moves_the_published_order(js: JsRuntime):
    payload = state_payload("fresh")
    screen_of(payload)["config_card"]["order"] = ["noise", "max_cycles"]
    js.push(payload)
    assert js.answer("orders")["config_card"] == ["noise", "max_cycles"]


def test_a_repeated_status_key_is_named_rather_than_drawn_twice(js: JsRuntime):
    payload = state_payload("fresh")
    card = screen_of(payload)["status_card"]
    card["cells"].append(dict(card["cells"][0]))
    js.push(payload)
    assert ("cells", "key", "repeated-key") in fault_rows(js)


def test_no_status_key_repeats_in_the_surface_the_panel_serves(js: JsRuntime):
    js.push(state_payload("fresh"))
    assert ("cells", "key", "repeated-key") not in fault_rows(js)


def live_values(node: Any, path: str = "") -> list:
    """Every path whose value is not a string, number, boolean or None."""
    if isinstance(node, dict):
        found: list = []
        for name, value in node.items():
            found.extend(live_values(value, path + "." + str(name)))
        return found
    if isinstance(node, list):
        found = []
        for at, value in enumerate(node):
            found.extend(live_values(value, path + "." + str(at)))
        return found
    return [] if isinstance(node, (str, int, float, bool, type(None))) else [path]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_surface_publishes_no_object_of_its_own(state: str):
    payload = nmp.view_model({})
    payload["screen"] = STATES[state]().build()
    assert live_values(payload) == []


def test_the_plain_data_walk_names_one_object_the_payload_carries():
    payload = nmp.view_model({})
    payload["screen"]["header_card"]["title"] = nmp.PanelWorld()
    assert live_values(payload) == [".screen.header_card.title"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_the_module_reads_is_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    kinds = js.answer("kinds")
    allowed = {"string", "number", "boolean", "object", "null"}
    strange = sorted(name for name, kind in kinds.items() if kind not in allowed)
    assert not strange, f"{len(strange)} values are not plain data: {strange}"


def test_the_kind_walk_reaches_the_leaves_and_not_only_the_bags(js: JsRuntime):
    js.push(state_payload("filled"))
    kinds = js.answer("kinds")
    assert kinds["screen.status_card.values.running"] == "string"
    assert kinds["screen.timer.interval_ms"] == "number"
    assert kinds["screen.buttons.start.enabled"] == "boolean"


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], MODULE_LITERALS["numbers"]


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"nuclear_mode_panel.js holds colour literals: {found}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], MODULE_LITERALS["slashes"]


def test_no_string_in_the_module_equals_a_value_the_panel_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & LOOKS - set(NAMED_VALUES))
    assert not written, f"the module spells out panel values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"the module spells out token values: {written}"


def test_every_named_value_the_module_writes_is_a_name_and_not_a_look():
    shown = sorted(one for one in NAMED_VALUES if one in LOOKS)
    assert shown == ["AlignLeft"], shown


WRITTEN_LINES = {
    "colour": 'var written = "' + nmp.TEAL + '";',
    "title": 'var written = "' + nmp.TITLE + '";',
    "spacing": "var written = " + str(nmp.OUTER_SPACING_PX) + ";",
    "suffix": 'var written = "' + nmp.CYCLE_SUFFIX + '";',
    "special": 'var written = "' + nmp.UNLIMITED_TEXT + '";',
    "slash": "var written = /a/;",
}


@pytest.mark.parametrize("case", sorted(WRITTEN_LINES))
def test_the_literal_scan_catches_one_value_written_into_the_real_module(case: str):
    """One value at a time goes into the shipped module and comes back out."""
    with module_held():
        original = MODULE_PATH.read_bytes()
        before = hashlib.sha256(original).hexdigest()
        changed = original + ("\n" + WRITTEN_LINES[case] + "\n").encode("utf-8")
        swap_module(MODULE_PATH, changed)
        try:
            source = MODULE_PATH.read_text(encoding="utf-8")
            found = js_literals(source)
            caught = (
                bool(found["numbers"])
                or bool(HEX_COLOUR.findall(source))
                or bool(found["slashes"])
                or bool(set(found["strings"]) & LOOKS - set(NAMED_VALUES))
            )
        finally:
            swap_module(MODULE_PATH, original)
    assert caught, f"the scan did not see the {case} value written in"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("given", [None, [], "screen", 4, True])
def test_a_payload_that_is_not_an_object_draws_nothing(js: JsRuntime, given: Any):
    js.bind_json("PAYLOAD", given)
    found = js.json("acervatorSetNuclearPanel(JSON.parse(PAYLOAD))")
    assert found["held"] is None
    assert found["faults"][0]["fault"] == "not-an-object"
    assert js.answer("isLoaded") is False


def test_a_payload_that_is_an_object_is_held(js: JsRuntime):
    js.push(state_payload("fresh"))
    assert js.answer("isLoaded") is True


def test_the_load_call_names_the_missing_bridge(js: JsRuntime):
    js.run("acervatorLoadNuclearPanel({});")
    assert js.answer("loadError") == "the preload bridge is not present"


DROP = object()

HOSTILE = {
    "missing_timer": ("screen.timer", DROP),
    "null_timer": ("screen.timer", None),
    "text_interval": ("screen.timer.interval_ms", "soon"),
    "number_title": ("screen.header_card.title.text", 12),
    "huge_value": ("screen.config_card.cycle_candles.value", 10**24),
    "long_name": ("screen.fleet_card.detail.text", "n" * 200),
    "markup": ("screen.status_card.values.last_error", "<img src=x onerror=1>"),
    "newline": ("screen.status_card.values.symbols", "two\nrows"),
    "zero_loops": ("screen.config_card.max_cycles.value", 0),
    "past_the_end": ("screen.status_card.values.current_cycle", "9999"),
    "text_checked": ("screen.config_card.noise.checked", "yes"),
    "null_cells": ("screen.status_card.cells", None),
    "scalar_cells": ("screen.status_card.cells", 3),
    "null_in_cells": ("screen.status_card.cells.0", None),
    "scalar_in_cells": ("screen.status_card.cells.0", 7),
    "null_order": ("screen.config_card.order", None),
    "null_buttons": ("screen.buttons.start", None),
    "repeated_name": ("screen.config_card.order.1", "cycle_candles"),
}

NOT_A_NUMBER = {
    "nan_value": float("nan"),
    "inf_value": float("inf"),
    "minus_inf_value": float("-inf"),
}


def put(payload: dict, path: str, value: Any) -> dict:
    """Writes value at a dotted path, or drops the field for the DROP mark."""
    node: Any = payload
    names = path.split(".")
    for name in names[:-1]:
        node = node[int(name)] if isinstance(node, list) else node[name]
    last = names[-1]
    if isinstance(node, list):
        node[int(last)] = value
    elif value is DROP:
        node.pop(last, None)
    else:
        node[last] = value
    return payload


def hostile_payload(case: str) -> dict:
    """The full payload with one field made hostile, back through JSON."""
    path, value = HOSTILE[case]
    payload = put(state_payload(FULL_STATE), path, value)
    return json.loads(json.dumps(payload))


@pytest.mark.parametrize("case", sorted(HOSTILE))
def test_a_hostile_value_is_reported_and_never_raises(js: JsRuntime, case: str):
    found = js.push(hostile_payload(case))
    assert isinstance(found["faults"], int)
    assert isinstance(js.answer("orders")["layout"], list)
    assert isinstance(js.answer("kinds"), dict)


@pytest.mark.parametrize(
    "case,where,field,kind",
    [
        ("missing_timer", "screen", "timer", "missing"),
        ("null_timer", "screen", "timer", "null"),
        ("text_interval", "timer", "interval_ms", "not-finite"),
        ("text_checked", "noise", "checked", "wrong-type"),
        ("null_order", "config_card", "order", "null"),
        ("null_buttons", "buttons", "start", "not-an-object"),
        ("null_cells", "status_card", "cells", "null"),
    ],
)
def test_a_hostile_value_is_named_by_the_fault_it_earns(
    js: JsRuntime, case: str, where: str, field: str, kind: str
):
    js.push(hostile_payload(case))
    rows = fault_rows(js)
    assert (where, field, kind) in rows, sorted(rows)


@pytest.mark.parametrize("case", ["huge_value", "zero_loops", "past_the_end"])
def test_a_number_at_the_edge_earns_no_fault_of_its_own(js: JsRuntime, case: str):
    js.push(hostile_payload(case))
    assert [one for one in fault_rows(js) if one[2] == "not-finite"] == []


def test_a_repeated_name_in_a_card_order_draws_that_row_twice(js: JsRuntime):
    """The surface owns its order, so a repeated row is drawn and not refused."""
    whole = js.push(state_payload(FULL_STATE))
    found = js.push(hostile_payload("repeated_name"))
    assert found["rows"] == whole["rows"]
    assert js.answer("orders")["config_card"].count("cycle_candles") == 2


@pytest.mark.parametrize("case", sorted(NOT_A_NUMBER))
def test_a_bare_not_a_number_stops_the_payload_at_the_page_parser(
    js: JsRuntime, case: str
):
    """The bridge writes NaN or Infinity, which JSON.parse refuses outright."""
    payload = put(
        state_payload(FULL_STATE),
        "screen.config_card.cycle_candles.value",
        NOT_A_NUMBER[case],
    )
    js.bind_json("PAYLOAD", payload)
    refused = js.run(
        "(function () { try { JSON.parse(PAYLOAD); return null; }"
        " catch (e) { return e.name; } })()"
    )
    assert refused.toString() == "SyntaxError"


def test_the_page_parser_takes_the_same_payload_without_the_bare_word(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload(FULL_STATE))
    taken = js.run("typeof JSON.parse(PAYLOAD)")
    assert taken.toString() == "object"


@pytest.mark.parametrize("case", ["null_in_cells", "scalar_in_cells"])
def test_a_cell_that_is_not_an_object_is_dropped_before_the_grid(
    js: JsRuntime, case: str
):
    whole = js.push(state_payload(FULL_STATE))
    found = js.push(hostile_payload(case))
    assert found["cells"] == whole["cells"] - 1


def test_a_scalar_where_a_cell_list_belongs_draws_only_the_wide_row(js: JsRuntime):
    found = js.push(hostile_payload("scalar_cells"))
    assert found["cells"] == 1


#: Two tags of one length whose declared widths are digit permutations. A widget
#: that prints them draws the same characters either way, whatever the host's
#: fonts; only one that reads them takes the width each asks for.
IMAGE_WIDTH_PX = 129
WIDE_IMAGE_WIDTH_PX = 921
GIF_SOURCE = "data:image/gif;base64,R0lGODlhAQABAAAAACw="
MARKUP_TEXT = '<img src="%s" width="%d">' % (GIF_SOURCE, IMAGE_WIDTH_PX)
WIDE_MARKUP_TEXT = '<img src="%s" width="%d">' % (GIF_SOURCE, WIDE_IMAGE_WIDTH_PX)


def widget_width(kind: str, wording: str) -> int:
    from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton

    made = {"label": QLabel, "button": QPushButton, "check": QCheckBox}[kind](wording)
    width = made.sizeHint().width()
    made.deleteLater()
    return width


def test_a_qlabel_draws_the_image_the_tag_names_at_the_width_it_asks_for(qapp):
    """The QLabel takes each tag's own width, so its caller text is markup."""
    assert qapp is not None
    assert widget_width("label", MARKUP_TEXT) == IMAGE_WIDTH_PX
    assert widget_width("label", WIDE_MARKUP_TEXT) == WIDE_IMAGE_WIDTH_PX


def plain_label_width(wording: str) -> int:
    """The width a QLabel gives `wording` when told to print it, not read it."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    made = QLabel(wording)
    made.setTextFormat(Qt.TextFormat.PlainText)
    width = made.sizeHint().width()
    made.deleteLater()
    return width


def test_the_same_qlabel_draws_characters_when_the_format_is_plain(qapp):
    """Under PlainText the label prints the tag, so the width it declares moves
    the label not at all."""
    assert qapp is not None
    drawn = plain_label_width(MARKUP_TEXT)
    assert drawn == plain_label_width(
        WIDE_MARKUP_TEXT
    ), f"the plain label took the declared width: {drawn}"
    assert drawn > IMAGE_WIDTH_PX, f"the plain label drew too little: {drawn}"


@pytest.mark.parametrize("kind", ["button", "check"])
def test_a_shipped_button_or_tick_box_never_draws_the_image(kind: str, qapp):
    assert qapp is not None
    drawn = widget_width(kind, MARKUP_TEXT)
    assert drawn == widget_width(
        kind, WIDE_MARKUP_TEXT
    ), f"{kind} took the declared width: {drawn}"
    assert drawn > IMAGE_WIDTH_PX, f"{kind} drew too little: {drawn}"


class Browser:
    """Browser loads the real renderer page from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open_page()
        self.wait_for_module()

    def open_page(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl

        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        connection = self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        self._view.loadFinished.disconnect(connection)
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"

    def wait_for_module(self) -> None:
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.js("typeof window.acervatorSetNuclearPanel") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the panel module: readyState "
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
    """The page, or a skip when Chromium is not installed with Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


STYLE_NAMES = [
    "display",
    "flexDirection",
    "gap",
    "columnGap",
    "rowGap",
    "gridTemplateColumns",
    "gridRowStart",
    "gridColumnStart",
    "gridColumnEnd",
    "justifySelf",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "color",
    "background",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "whiteSpace",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderTopLeftRadius",
]

EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "border-radius": ("borderTopLeftRadius",),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "background": ("backgroundColor",),
    "font-size": ("fontSize",),
    "font-weight": ("fontWeight",),
    "color": ("color",),
}

PAGE_HELPERS = (
    "if (window.HOST) { window.HOST.remove(); }"
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + HOST_WIDTH_CSS + "';"
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
    "    var here = path ? path + '>' + part : part;"
    "    var attrs = {};"
    "    Array.prototype.slice.call(el.attributes).forEach(function (a) {"
    "      attrs[a.name] = a.value; });"
    "    var own = '';"
    "    Array.prototype.slice.call(el.childNodes).forEach(function (n) {"
    "      if (n.nodeType === Node.TEXT_NODE) { own += n.nodeValue; } });"
    "    found.push({ path: here, tag: el.tagName, attrs: attrs,"
    "      width: el.clientWidth, text: own, html: el.innerHTML,"
    "      style: window.readStyle(el, names) });"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)


def draw_panel(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    browser.js(
        "acervatorSetTokens(JSON.parse(window.TOKENS));"
        "acervatorTokens.apply(document.documentElement);"
    )
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetNuclearPanel(JSON.parse(window.PAYLOAD));"
        "acervatorNuclearPanel.renderPanel(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def named(parts: list, path: str, attr: str) -> list:
    return [one["attrs"].get(attr) for one in at_path(parts, path)]


def probe(browser: Browser, sheet: str) -> dict:
    names: list = []
    for prop, _ in css_declarations(sheet):
        names.extend(EXPANDED.get(prop, (prop,)))
    if not names:
        return {}
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(css_body(sheet))
        + ", "
        + json.dumps(sorted(set(names)))
        + ")"
    )


def sheet_agrees(drawn: dict, expected: dict, where: str) -> None:
    assert expected, f"{where}: the probe took no value, so this compares nothing"
    differing = {
        name: (value, drawn["style"].get(name))
        for name, value in expected.items()
        if drawn["style"].get(name) != value
    }
    assert not differing, (
        f"{where}: {len(differing)} of {len(expected)} declared values differ "
        f"from the surface's own: {differing}"
    )


PANEL = "panel"
HEADER = "panel>header-card"
CONFIG = "panel>config-card"
STATUS = "panel>status-card"


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorNuclearPanel") == "object"


def test_the_drawn_panel_names_every_child_a_check_reads(browser: Browser):
    draw_panel(browser, state_payload(FULL_STATE))
    every = browser.js("window.HOST.querySelectorAll('*').length")
    named_count = browser.js("window.HOST.querySelectorAll('[data-part]').length")
    assert every == named_count, f"{every - named_count} children carry no name"
    assert every > 0


def test_the_cards_are_drawn_in_the_order_the_surface_publishes(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_panel(browser, payload)
    drawn = [one["path"].split(">")[1] for one in parts if one["path"].count(">") == 1]
    assert drawn == [
        "header-card",
        "fleet-card",
        "config-card",
        "buttons",
        "status-card",
        "panel-stretch",
    ], drawn


def test_the_run_settings_are_drawn_in_the_order_the_config_card_names(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_panel(browser, payload)
    drawn = named(parts, CONFIG + ">form>field", "data-name")
    assert drawn == screen_of(payload)["config_card"]["order"], drawn


def test_the_status_rows_are_drawn_under_the_keys_the_surface_names(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_panel(browser, payload)
    card = screen_of(payload)["status_card"]
    wanted = [one["key"] for one in card["cells"]] + [card["last_exception"]["key"]]
    assert named(parts, STATUS + ">grid>cell-label", "data-key") == wanted
    assert named(parts, STATUS + ">grid>cell-value", "data-key") == wanted


def test_the_two_run_buttons_are_drawn_before_the_row_stretches(browser: Browser):
    parts = draw_panel(browser, state_payload(FULL_STATE))
    assert named(parts, "panel>buttons>button", "data-name") == ["start", "stop"]
    assert len(at_path(parts, "panel>buttons-stretch")) == 0
    assert len(at_path(parts, "panel>buttons>buttons-stretch")) == 1


@pytest.mark.parametrize(
    "path,where",
    [
        (HEADER, "header_card"),
        ("panel>fleet-card", "fleet_card"),
        (CONFIG, "config_card"),
        (STATUS, "status_card"),
    ],
)
def test_each_card_paints_the_declarations_the_surface_wrote(
    browser: Browser, path: str, where: str
):
    payload = state_payload(FULL_STATE)
    parts = draw_panel(browser, payload)
    sheet = screen_of(payload)[where]["style"]
    sheet_agrees(only(parts, path), probe(browser, sheet), where)


def test_the_header_card_paints_the_faint_gold_border_qt_paints(browser: Browser):
    parts = draw_panel(browser, state_payload(FULL_STATE))
    wanted = browser.parsed(
        "window.probeStyle("
        + json.dumps("border:" + fraction_alpha("1px solid " + nmp.HEADER_CARD_BORDER))
        + ', ["borderTopColor", "borderTopStyle"])'
    )
    drawn = only(parts, HEADER)["style"]
    assert drawn["borderTopStyle"] == wanted["borderTopStyle"] == "solid"
    assert drawn["borderTopColor"] == wanted["borderTopColor"]
    assert wanted["borderTopColor"] != "rgb(255, 204, 68)"


def test_the_header_card_paints_the_faint_gold_qt_paints(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_panel(browser, payload)
    wanted = browser.parsed(
        "window.probeStyle("
        + json.dumps("background:" + fraction_alpha("rgba(255,200,80,8)"))
        + ', ["backgroundColor"])'
    )
    assert only(parts, HEADER)["style"]["backgroundColor"] == wanted["backgroundColor"]
    assert wanted["backgroundColor"] != "rgb(255, 200, 80)"


def test_the_status_grid_takes_its_columns_from_the_published_stretch(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_panel(browser, payload)
    stretch = screen_of(payload)["status_card"]["column_stretch"]
    drawn = only(parts, STATUS + ">grid")["style"]["gridTemplateColumns"]
    assert len(drawn.split(" ")) == len(stretch), drawn


def test_the_wide_exception_row_spans_the_columns_the_surface_asked_for(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_panel(browser, payload)
    wide = screen_of(payload)["status_card"]["last_exception"]
    drawn = [
        one
        for one in at_path(parts, STATUS + ">grid>cell-value")
        if one["attrs"]["data-key"] == wide["key"]
    ]
    assert drawn[0]["attrs"]["data-span"] == str(wide["column_span"])


def test_a_status_value_carrying_markup_draws_as_characters(browser: Browser):
    payload = state_payload(FULL_STATE)
    screen_of(payload)["status_card"]["values"]["last_exception"] = MARKUP_TEXT
    parts = draw_panel(browser, payload)
    drawn = [
        one
        for one in at_path(parts, STATUS + ">grid>cell-value")
        if one["attrs"]["data-key"] == "last_exception"
    ][0]
    assert drawn["text"] == MARKUP_TEXT
    assert "<img" not in drawn["html"]
    assert browser.js("window.HOST.querySelectorAll('img').length") == 0


def test_the_image_scan_would_see_an_image_the_page_did_make(browser: Browser):
    draw_panel(browser, state_payload(FULL_STATE))
    browser.js("window.HOST.appendChild(document.createElement('img'));")
    assert browser.js("window.HOST.querySelectorAll('img').length") == 1


def test_a_status_value_carrying_a_newline_keeps_both_lines(browser: Browser):
    payload = state_payload(FULL_STATE)
    screen_of(payload)["status_card"]["values"]["last_exception"] = "one\ntwo"
    parts = draw_panel(browser, payload)
    drawn = [
        one
        for one in at_path(parts, STATUS + ">grid>cell-value")
        if one["attrs"]["data-key"] == "last_exception"
    ][0]
    assert drawn["style"]["whiteSpace"] == "pre-wrap"
    assert drawn["text"] == "one\ntwo"


CLICK = (
    "(function (name) {"
    "  var one = window.HOST.querySelector("
    "    '[data-part=\"button\"][data-name=\"' + name + '\"]');"
    "  one.click();"
    "  return JSON.stringify(acervatorNuclearPanel.sent()); })"
)


def clicked(browser: Browser, name: str) -> list:
    return json.loads(browser.js(CLICK + "(" + json.dumps(name) + ")"))


@pytest.mark.parametrize(
    "state,name,action",
    [
        ("fresh", "reload_button", "reload_button_clicked"),
        ("fresh", "start", "start_button_clicked"),
        ("running", "stop", "stop_button_clicked"),
    ],
)
def test_each_button_sends_the_action_the_surface_wired_to_it(
    browser: Browser, state: str, name: str, action: str
):
    draw_panel(browser, state_payload(state))
    sent = clicked(browser, name)
    assert [one["action"] for one in sent] == [action], sent


def test_a_disabled_button_sends_nothing_when_it_is_clicked(browser: Browser):
    draw_panel(browser, state_payload("running"))
    assert clicked(browser, "start") == []


def test_start_carries_the_four_run_settings_the_config_card_holds(
    browser: Browser,
):
    payload = state_payload("fresh")
    draw_panel(browser, payload)
    sent = clicked(browser, "start")
    card = screen_of(payload)["config_card"]
    assert sent[0]["params"] == {
        "cycle_candles": card["cycle_candles"]["value"],
        "max_cycles": card["max_cycles"]["value"],
        "noise": card["noise"]["checked"],
        "load_oscillation": card["load_oscillation"]["checked"],
    }, sent


TYPE_IN = (
    "(function (name, value) {"
    "  var one = window.HOST.querySelector("
    "    '[data-part=\"input\"][data-name=\"' + name + '\"]');"
    "  var setter = Object.getOwnPropertyDescriptor("
    "    window.HTMLInputElement.prototype, 'value').set;"
    "  setter.call(one, value);"
    "  one.dispatchEvent(new Event('input', { bubbles: true }));"
    "  return one.value; })"
)

TOGGLE = (
    "(function (name) {"
    "  var one = window.HOST.querySelector("
    "    '[data-part=\"input\"][data-name=\"' + name + '\"]');"
    "  one.click();"
    "  return one.checked; })"
)


def test_typing_a_cycle_length_reaches_the_settings_start_sends(browser: Browser):
    draw_panel(browser, state_payload("fresh"))
    browser.js(TYPE_IN + '("cycle_candles", "4500")')
    sent = clicked(browser, "start")
    assert sent[0]["params"]["cycle_candles"] == 4500, sent


def test_unticking_the_noise_box_reaches_the_settings_start_sends(browser: Browser):
    draw_panel(browser, state_payload("fresh"))
    assert browser.js(TOGGLE + '("noise")') is False
    sent = clicked(browser, "start")
    assert sent[0]["params"]["noise"] is False, sent


def test_the_max_cycles_box_shows_the_special_text_at_its_floor(browser: Browser):
    payload = state_payload("fresh")
    parts = draw_panel(browser, payload)
    card = screen_of(payload)["config_card"]["max_cycles"]
    drawn = [
        one
        for one in at_path(parts, CONFIG + ">form>field>input")
        if one["attrs"]["data-name"] == "max_cycles"
    ][0]
    assert drawn["attrs"]["value"] == card["special_value_text"]
    assert drawn["attrs"]["type"] == "text"


def test_the_max_cycles_box_counts_again_above_its_floor(browser: Browser):
    payload = state_payload("fresh")
    screen_of(payload)["config_card"]["max_cycles"]["value"] = 12
    parts = draw_panel(browser, payload)
    drawn = [
        one
        for one in at_path(parts, CONFIG + ">form>field>input")
        if one["attrs"]["data-name"] == "max_cycles"
    ][0]
    assert drawn["attrs"]["type"] == "number"
    assert drawn["attrs"]["value"] == "12"


def test_a_running_panel_sends_the_refresh_action_on_its_own_interval(
    browser: Browser,
):
    draw_panel(browser, state_payload("running"))
    browser.settle(TICK_SETTLE_MS)
    sent = browser.parsed("acervatorNuclearPanel.sent()")
    ticks = [one for one in sent if one["action"] == "refresh_timer_tick"]
    assert ticks, sent
    assert ticks[0]["params"] == {}


def test_a_stopped_panel_sends_no_refresh_action_at_all(browser: Browser):
    draw_panel(browser, state_payload("stopped"))
    browser.settle(TICK_SETTLE_MS)
    sent = browser.parsed("acervatorNuclearPanel.sent()")
    assert [one for one in sent if one["action"] == "refresh_timer_tick"] == []


#: Every panel colour one token carries, beside the token's own name.
CARRIED = {
    "#00ffcc": "PRIMARY",
    "#0a0a14": "SURFACE_CONSOLE_HEADER",
    "#1a1a3a": "MAIN_TOGGLE_SURFACE",
    "#222250": "MAIN_TOGGLE_HOVER",
    "#3a1a1a": "MAIN_TOGGLE_CHECKED",
    "#88c0ff": "MAIN_LOG_NAME",
    "#ffcc44": "STATE_PENDING",
}


def test_the_token_table_answers_only_seven_of_this_panel_s_declarations(
    js: JsRuntime,
):
    js.load_tokens()
    js.push(state_payload("fresh"))
    found = js.answer("tokenNames")
    resolved = {name: token for name, token in found.items() if token is not None}
    assert resolved == CARRIED, resolved
    assert len(found) > len(CARRIED), found


def test_the_token_lookup_answers_a_value_the_token_table_does_carry(js: JsRuntime):
    js.load_tokens()
    js.bind_json("VALUE", str(dts.PRIMARY))
    assert js.json("acervatorWidgets.variableFor(JSON.parse(VALUE))") is not None
