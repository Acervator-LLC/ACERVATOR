"""The React Bot Swarm list, against bot_swarm_list_surface.py."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import bot_swarm_list_surface as surface
from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "bot_swarm_list.js"
TOKENS_PATH = WEB / "design_tokens.js"
CELLS_PATH = WEB / "table_cells.js"
HEADER_PATH = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 500
READY_ROUNDS = 100
READY_STEP_MS = 100

HOST_WIDTH_PX = 900
HOST_HEIGHT_PX = 400

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

#: JavaScript holds every number as a double, so a big integer arrives short.
BIGGEST_EXACT_INTEGER = 2**53

LONG_NAME = "z" * 200
MARKUP_NAME = "<img src='data:image/gif;base64,R0lGOD'><b>bold</b>"


def bot(bot_id: str, symbol: str, inflow: Any, outflow: Any, pct: Any) -> dict:
    return {
        "bot_id": bot_id,
        "symbol": symbol,
        "inflow_usd": inflow,
        "outflow_usd": outflow,
        "outflow_pct": pct,
    }


ONE_BOT = [bot("bot-a", "BTC-USD", 1000.5, 250.25, 40.0)]
THREE_BOTS = [
    bot("bot-a", "BTC-USD", 1000.5, 250.25, 40.0),
    bot("bot-b", "ETH-USD", 10.0, 0.0, 0.0),
    bot("bot-c", "SOL-USD", 5.0, 5.0, 100.0),
]
SWAPPED_BOTS = [THREE_BOTS[0], THREE_BOTS[2], THREE_BOTS[1]]
BAD_BOTS = [
    THREE_BOTS[0],
    bot("bot-bad", "DOGE-USD", "not a number", 1.0, 1.0),
    THREE_BOTS[2],
]

WIRES = [
    {"id": "w1", "source_id": "bot-a", "target_id": "bot-c", "phase": 0.3},
    {"id": "w2", "source_id": "bot-b", "target_id": "bot-z", "phase": 0.0},
]
#: NUMBERED_WIRES holds names that are digits, which a bag re-sorts crossing the bridge.
NUMBERED_WIRES = [
    {"id": "3", "source_id": "bot-a", "target_id": "bot-b", "phase": 0.1},
    {"id": "1", "source_id": "bot-b", "target_id": "bot-c", "phase": 0.2},
    {"id": "2", "source_id": "bot-a", "target_id": "bot-c", "phase": 0.4},
]


def build(*steps: dict) -> dict:
    """One payload, each step driving the same list and sheet in order."""
    model = surface.BotSwarmListModel()
    for step in steps:
        if "rows" in step:
            try:
                model.bot_list.set_bots(step["rows"])
            except ValueError:
                if not step.get("refuses"):
                    raise
        if "widths" in step:
            model.bot_list.set_column_widths(step["widths"])
        if "wires" in step:
            model.lane_canvas.set_wires(step["wires"])
        if "opacity" in step:
            model.lane_canvas.set_opacity_pct(step["opacity"])
        if step.get("paint"):
            model.lane_canvas.paint()
    return json.loads(json.dumps(surface.build_payload(model), ensure_ascii=True))


STATES: dict = {
    "empty": (),
    "one": ({"rows": ONE_BOT},),
    "many": ({"rows": THREE_BOTS},),
    "wired": ({"rows": THREE_BOTS}, {"wires": WIRES}, {"paint": True}),
    "numbered": ({"rows": THREE_BOTS}, {"wires": NUMBERED_WIRES}, {"paint": True}),
    "stale": ({"rows": THREE_BOTS}, {"rows": BAD_BOTS, "refuses": True}),
    "dimmed": (
        {"rows": THREE_BOTS},
        {"wires": WIRES},
        {"opacity": 40},
        {"paint": True},
    ),
    "no_wires": ({"rows": THREE_BOTS}, {"wires": []}, {"paint": True}),
}
STATE_NAMES = tuple(STATES)


def state_payload(name: str) -> dict:
    return build(*STATES[name])


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):
    """A QJSEngine holding ``bot_swarm_list.js`` and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetBotSwarmList"

    def raised(self, script: str) -> str:
        """The engine's error for ``script``, or an empty string."""
        result = self._engine.evaluate(script)
        return result.toString() if result.isError() else ""

    def load_tokens(self) -> None:
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_cells(self) -> None:
        self.run(CELLS_PATH.read_text(encoding="utf-8"))

    def load_header(self) -> None:
        self.run(HEADER_PATH.read_text(encoding="utf-8"))

    def called(self, method: str, value: Any) -> Any:
        self.bind_json("ARG", value)
        return self.json("acervatorSwarmList." + method + "(JSON.parse(ARG))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def skinned(js: JsRuntime) -> JsRuntime:
    """The js runtime with the token, cell and header modules already run."""
    js.load_tokens()
    js.load_cells()
    js.load_header()
    return js


def declared_fields(js: JsRuntime) -> list:
    return js.json("acervatorSwarmList.declaredFields()")


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
        "JSON.parse(NAMES).map(function (n) " "{ return acervatorSwarmList.field(n); })"
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
    payload = state_payload("many")
    payload["only_on_the_surface"] = []
    js.push(payload)
    assert sorted(set(payload) - set(declared_fields(js))) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    payload = state_payload("many")
    assert payload.pop("row_height") is not None
    js.push(payload)
    assert sorted(set(declared_fields(js)) - set(payload)) == ["row_height"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = state_payload("many")
    payload["row_height"] += 1
    js.push(payload)
    original = state_payload("many")
    differing = sorted(
        name for name in original if js.called("field", name) != original[name]
    )
    assert differing == ["row_height"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["rows"] == payload["row_count"]
    assert report["held"]["rows"] == len(payload["rows"])
    assert report["declared"]["columns"] == payload["total_cols"]
    assert report["held"]["columns"] == len(payload["column_headers"])
    assert report["declared"]["cells"] == payload["written_cell_count"]
    assert report["held"]["cells"] == payload["written_cell_count"]
    assert report["declared"]["wires"] == payload["wire_count"]
    assert report["held"]["wires"] == len(payload["wire_order"])


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("many")
    declared = len(payload)
    del payload["row_height"]
    report = js.push(payload)
    assert report["declared"]["fields"] == declared
    assert report["held"]["fields"] == declared - 1


def test_a_dropped_cell_shortens_the_held_cell_count(js: JsRuntime):
    payload = state_payload("many")
    payload["rows"][0][0] = None
    report = js.push(payload)
    assert report["declared"]["cells"] == payload["written_cell_count"]
    assert report["held"]["cells"] == payload["written_cell_count"] - 1


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_holds_every_row_the_surface_published(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.json("acervatorSwarmList.rows()") == payload["rows"]
    assert js.json("acervatorSwarmList.botIds()") == payload["bot_ids"]


def test_the_row_check_names_a_dropped_row(js: JsRuntime):
    payload = state_payload("many")
    dropped = payload["rows"].pop()
    js.push(payload)
    original = state_payload("many")["rows"]
    held = js.json("acervatorSwarmList.rows()")
    assert [one for one in original if one not in held] == [dropped]


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
    """A value that changes shape in transit reads correct and paints wrong."""
    payload = state_payload(state)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json("acervatorSwarmList.kinds()")
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
    payload = state_payload("many")
    payload["row_height"] = str(payload["row_height"])
    js.push(payload)
    expected = python_kinds(state_payload("many"))
    actual = js.json("acervatorSwarmList.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["row_height"], f"the check named {differing}"


def test_the_type_check_names_a_scalar_where_a_row_belongs(js: JsRuntime):
    """A scalar in place of a row list must not read as the list it replaced."""
    payload = state_payload("many")
    payload["rows"][1] = 7
    js.push(payload)
    expected = python_kinds(state_payload("many"))
    actual = js.json("acervatorSwarmList.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert "rows.1" in differing, f"the check named {differing}"


def test_the_type_check_names_a_null_where_a_cell_belongs(js: JsRuntime):
    payload = state_payload("many")
    payload["rows"][1][2] = None
    js.push(payload)
    expected = python_kinds(state_payload("many"))
    actual = js.json("acervatorSwarmList.kinds()")
    assert actual.get("rows.1.2") == "null"
    assert expected["rows.1.2"] == "object"


CELL_TYPE_CASES = {
    "kind": 7,
    "text": 7,
    "alignment": "132",
    "color": 7,
    "brush": 7,
}


@pytest.mark.parametrize("field", sorted(CELL_TYPE_CASES))
def test_a_cell_field_of_the_wrong_type_is_named(js: JsRuntime, field: str):
    payload = state_payload("one")
    payload["rows"][0][0][field] = CELL_TYPE_CASES[field]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "wrong-type"]
    assert {
        "where": "row:0/cell:0",
        "field": field,
        "fault": "wrong-type",
        "detail": "number" if isinstance(CELL_TYPE_CASES[field], int) else "string",
    } in named, f"the check named {named}"


@pytest.mark.parametrize("field", sorted(CELL_TYPE_CASES))
def test_a_cell_field_the_payload_omits_is_named(js: JsRuntime, field: str):
    payload = state_payload("one")
    del payload["rows"][0][0][field]
    report = js.push(payload)
    assert {
        "where": "row:0/cell:0",
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"]


@pytest.mark.parametrize("field", sorted(CELL_TYPE_CASES))
def test_a_cell_field_carrying_null_is_named(js: JsRuntime, field: str):
    payload = state_payload("one")
    payload["rows"][0][0][field] = None
    report = js.push(payload)
    assert {
        "where": "row:0/cell:0",
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_the_cell_bot_id_type_is_held_against_nothing_and_is_not_named(js: JsRuntime):
    """Every money cell publishes a null bot, so no default of that meaning exists."""
    payload = state_payload("one")
    payload["rows"][0][0]["bot_id"] = 7
    report = js.push(payload)
    named = [one for one in report["faults"] if one["field"] == "bot_id"]
    assert [one["fault"] for one in named] == ["stale-row"], f"the check named {named}"
    assert payload["rows"][0][1]["bot_id"] is None


@pytest.mark.parametrize("field", sorted(CELL_TYPE_CASES))
def test_the_cell_type_checks_are_quiet_on_every_whole_payload(
    js: JsRuntime, field: str
):
    for name in STATE_NAMES:
        report = js.push(state_payload(name))
        named = [
            one
            for one in report["faults"]
            if one["field"] == field and one["fault"] != "stale-row"
        ]
        assert named == [], f"{name}: the shipped payload names {named}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_shipped_payload_names_only_the_stale_rows(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    named = sorted({one["fault"] for one in report["faults"]})
    assert named in ([], ["stale-row"]), f"{state} names {report['faults']}"


def test_one_unreadable_value_leaves_the_earlier_fleet_on_the_later_rows():
    """The shipped list resizes first and fills after, so a refusal keeps old rows."""
    payload = state_payload("stale")
    assert payload["row_count"] == len(BAD_BOTS)
    assert payload["bot_ids"] == ["bot-a", "bot-bad"]
    shown = [row[surface.COL_TICKER]["text"] for row in payload["rows"]]
    assert shown == ["BTC-USD", "ETH-USD", "SOL-USD"], shown
    assert shown[1] != BAD_BOTS[1]["symbol"], "the refused bot reached the cell"


def test_the_module_names_the_stale_rows_rather_than_repairing_them(js: JsRuntime):
    """The list shows the previous fleet while the row list names the new one."""
    report = js.push(state_payload("stale"))
    assert js.json("acervatorSwarmList.staleRows()") == [1, 2]
    named = [one for one in report["faults"] if one["fault"] == "stale-row"]
    assert [one["where"] for one in named] == ["row:1", "row:2"], f"named {named}"
    assert [one["detail"] for one in named] == ["bot-b", "bot-c"]
    assert js.json("acervatorSwarmList.rowBotIds()") == ["bot-a", "bot-b", "bot-c"]
    assert js.json("acervatorSwarmList.botIds()") == ["bot-a", "bot-bad"]


def test_the_stale_row_check_is_quiet_on_a_fleet_that_wrote_every_row(js: JsRuntime):
    js.push(state_payload("many"))
    assert js.json("acervatorSwarmList.staleRows()") == []
    assert js.json("acervatorSwarmList.faults()") == []


def test_the_row_order_reaches_the_module_as_the_surface_wrote_it(js: JsRuntime):
    """A list keeps its order across the bridge where a bag may not."""
    payload = state_payload("many")
    js.push(payload)
    assert js.json("acervatorSwarmList.botIds()") == [
        one["bot_id"] for one in THREE_BOTS
    ]
    assert js.json("acervatorSwarmList.rowBotIds()") == [
        one["bot_id"] for one in THREE_BOTS
    ]


def test_the_row_order_check_names_a_reordered_fleet(js: JsRuntime):
    js.push(build({"rows": SWAPPED_BOTS}))
    held = js.json("acervatorSwarmList.rowBotIds()")
    original = [one["bot_id"] for one in THREE_BOTS]
    assert held != original, "the check cannot see a reordered fleet"
    differing = [at for at, name in enumerate(original) if held[at] != name]
    assert differing == [1, 2], f"the check named {differing}"


def test_the_row_identity_check_names_two_bots_whose_values_were_swapped(js: JsRuntime):
    """Two rows keep their position and trade every value, so position cannot report."""
    payload = state_payload("many")
    rows = payload["rows"]
    rows[1], rows[2] = rows[2], rows[1]
    js.push(payload)
    held = js.json("acervatorSwarmList.rowTexts()")
    original = state_payload("many")["rows"]
    by_name = {one["bot_id"]: one["texts"] for one in held}
    was = {
        row[surface.COL_TICKER]["bot_id"]: [
            None if cell is None else cell["text"] for cell in row
        ]
        for row in original
    }
    moved = sorted(name for name in was if by_name.get(name) != was[name])
    assert moved == [], "the two rows carried their own values with them"
    order = [one["bot_id"] for one in held]
    assert order == ["bot-a", "bot-c", "bot-b"], f"the check read {order}"
    assert order != [one["bot_id"] for one in THREE_BOTS]


def test_the_row_identity_check_names_a_value_moved_to_another_bot(js: JsRuntime):
    """A figure moved between two rows is named by the bot that now shows it."""
    payload = state_payload("many")
    rows = payload["rows"]
    at = surface.COL_INFLOW
    rows[1][at]["text"], rows[2][at]["text"] = rows[2][at]["text"], rows[1][at]["text"]
    js.push(payload)
    held = {
        one["bot_id"]: one["texts"] for one in js.json("acervatorSwarmList.rowTexts()")
    }
    was = {
        row[surface.COL_TICKER]["bot_id"]: row[at]["text"]
        for row in state_payload("many")["rows"]
    }
    moved = sorted(name for name, texts in held.items() if texts[at] != was[name])
    assert moved == ["bot-b", "bot-c"], f"the check named {moved}"


def test_the_row_identity_check_is_quiet_on_the_shipped_fleet(js: JsRuntime):
    js.push(state_payload("many"))
    held = {
        one["bot_id"]: one["texts"] for one in js.json("acervatorSwarmList.rowTexts()")
    }
    was = {
        row[surface.COL_TICKER]["bot_id"]: [
            None if cell is None else cell["text"] for cell in row
        ]
        for row in state_payload("many")["rows"]
    }
    assert sorted(name for name in was if held.get(name) != was[name]) == []


def test_the_surface_publishes_the_wire_order_as_a_list(js: JsRuntime):
    payload = state_payload("numbered")
    js.push(payload)
    assert js.json("acervatorSwarmList.wireOrder()") == ["3", "1", "2"]
    assert payload["wire_count"] == len(NUMBERED_WIRES)


def test_a_bag_keyed_by_a_number_like_wire_name_arrives_resorted(js: JsRuntime):
    """The lane bag alone cannot answer which wire the sheet drew first."""
    js.push(state_payload("numbered"))
    bagged = list(js.json("acervatorSwarmList.laneAssignments()"))
    assert bagged == ["1", "2", "3"], f"the bag arrived as {bagged}"
    assert bagged != js.json("acervatorSwarmList.wireOrder()")
    assert js.json("acervatorSwarmList.lanesInOrder()") == [
        js.json("acervatorSwarmList.laneAssignments()")[name]
        for name in ["3", "1", "2"]
    ]


def test_the_resort_check_reads_a_named_wire_bag_in_its_own_order(js: JsRuntime):
    """A bag keyed by a name that is not digits keeps the order it was written in."""
    js.push(state_payload("wired"))
    assert list(js.json("acervatorSwarmList.laneAssignments()")) == ["w1"]
    assert js.json("acervatorSwarmList.wireOrder()") == ["w1", "w2"]


def test_a_wire_with_no_lane_and_no_reason_is_named(js: JsRuntime):
    payload = state_payload("wired")
    payload["undrawable"] = []
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "unplaced"]
    assert [one["where"] for one in named] == ["wire:w2"], f"the check named {named}"


def test_the_unplaced_check_is_quiet_when_the_sheet_gave_a_reason(js: JsRuntime):
    report = js.push(state_payload("wired"))
    assert [one for one in report["faults"] if one["fault"] == "unplaced"] == []
    assert state_payload("wired")["undrawable"] == [["w2", surface.REASON_UNLISTED]]


@pytest.mark.parametrize("state", ["wired", "dimmed", "numbered"])
def test_the_module_draws_one_shape_for_each_drawing_call(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    shapes = js.json("acervatorSwarmList.shapes()")
    lines = [one for one in payload["calls"] if one[0] == surface.DRAW_LINE]
    dots = [one for one in payload["calls"] if one[0] == surface.DRAW_ELLIPSE]
    assert len(shapes) == len(lines) + len(dots)
    assert [one["tag"] for one in shapes].count("line") == len(lines)
    assert [one["tag"] for one in shapes].count("circle") == len(dots)


def test_the_shape_check_reads_a_shorter_call_list_as_fewer_shapes(js: JsRuntime):
    payload = state_payload("wired")
    full = len(js.push(payload) and js.json("acervatorSwarmList.shapes()"))
    payload["calls"] = payload["calls"][:-2]
    js.push(payload)
    assert len(js.json("acervatorSwarmList.shapes()")) < full


def test_a_call_the_surface_never_named_is_reported(js: JsRuntime):
    payload = state_payload("wired")
    payload["calls"][0] = ["painter.no_such_call"]
    report = js.push(payload)
    assert {
        "where": "call:0",
        "field": None,
        "fault": "unknown-call",
        "detail": "painter.no_such_call",
    } in report["faults"]


def test_the_call_check_is_quiet_on_every_call_the_sheet_makes(js: JsRuntime):
    for name in ("wired", "dimmed", "numbered", "no_wires"):
        report = js.push(state_payload(name))
        assert [one for one in report["faults"] if one["fault"] == "unknown-call"] == []


def test_an_empty_wire_set_makes_no_call_and_draws_no_shape(js: JsRuntime):
    payload = state_payload("no_wires")
    js.push(payload)
    assert payload["calls"] == []
    assert payload["branches"] == [surface.PAINT_NOTHING]
    assert js.json("acervatorSwarmList.shapes()") == []


def test_every_colour_the_surface_publishes_carries_six_hex_digits():
    """Qt reads eight digits as alpha first and CSS reads them alpha last."""
    every = {
        name: value
        for name, value in vars(surface).items()
        if isinstance(value, str) and HEX_COLOUR.fullmatch(value)
    }
    widths = {value: len(value.lstrip("#")) for value in every.values()}
    assert set(widths.values()) == {6}, f"the surface publishes {widths}"
    assert len(every) > 1, "the surface publishes no colour; the check cannot report"


@pytest.mark.parametrize(
    "field", ["success_color", "error_color", "pct_headroom_color"]
)
def test_an_eight_digit_colour_on_a_published_field_is_refused(
    js: JsRuntime, field: str
):
    payload = state_payload("many")
    swapped = payload[field] + "ff"
    payload[field] = swapped
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "hex-width",
        "detail": swapped,
    } in report["faults"]


def test_an_eight_digit_colour_on_a_cell_is_refused(js: JsRuntime):
    payload = state_payload("one")
    swapped = payload["rows"][0][surface.COL_INFLOW]["color"] + "ff"
    payload["rows"][0][surface.COL_INFLOW]["color"] = swapped
    report = js.push(payload)
    assert {
        "where": "row:0/cell:1",
        "field": "color",
        "fault": "hex-width",
        "detail": swapped,
    } in report["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_hex_width_check_is_quiet_on_every_whole_payload(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    assert [one for one in report["faults"] if one["fault"] == "hex-width"] == []


def test_a_cell_carrying_a_colour_it_never_paints_is_named(js: JsRuntime):
    """An unpainted cell keeps the unset colour, so any other value disagrees."""
    payload = state_payload("one")
    payload["rows"][0][surface.COL_TICKER]["color"] = payload["success_color"]
    report = js.push(payload)
    assert {
        "where": "row:0/cell:0",
        "field": "color",
        "fault": "brush-mismatch",
        "detail": payload["success_color"],
    } in report["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_brush_check_is_quiet_on_every_whole_payload(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    assert [one for one in report["faults"] if one["fault"] == "brush-mismatch"] == []


def carriers_of(value: Any) -> list:
    tokens = token_payload()
    aliases = tokens["alias_targets"]
    return sorted(
        name
        for name, held in tokens["tokens"].items()
        if str(held) == str(value) and name not in aliases
    )


#: The one token each list colour resolves through, and what it names.
COLOUR_CARRIERS = {
    surface.SUCCESS_COLOR: "SUCCESS",
    surface.ERROR_COLOR: "ERROR",
    surface.WARNING_COLOR: "WARNING",
    surface.PRIMARY_BRIGHT_COLOR: "PRIMARY_BRIGHT",
    surface.TEXT_MUTED_COLOR: "TEXT_MUTED",
}


@pytest.mark.parametrize("value", sorted(COLOUR_CARRIERS))
def test_every_colour_the_list_paints_resolves_to_one_token(
    skinned: JsRuntime, value: str
):
    name = skinned.called("variableFor", value)
    assert carriers_of(value) == [name], f"{value} is carried by {carriers_of(value)}"
    assert COLOUR_CARRIERS[value] == name


def test_the_unset_colour_is_never_resolved_because_its_one_name_means_something_else(
    skinned: JsRuntime,
):
    """A cell with no brush paints nothing, so TEXT_ON_LIGHT never reaches it."""
    assert carriers_of(surface.UNSET_COLOR) == ["TEXT_ON_LIGHT"]
    skinned.push(state_payload("many"))
    ticker = surface.COL_TICKER
    assert state_payload("many")["rows"][0][ticker]["color"] == surface.UNSET_COLOR
    assert state_payload("many")["rows"][0][ticker]["brush"] == surface.UNSET_BRUSH


def test_the_colour_resolver_reports_no_name_for_a_colour_no_token_carries(
    skinned: JsRuntime,
):
    assert skinned.called("variableFor", "#010203") is None


def test_the_colour_resolver_reports_no_name_with_the_cell_module_off_the_page(
    js: JsRuntime,
):
    js.load_tokens()
    assert js.json("typeof acervatorCells") == "undefined"
    assert js.called("colour", surface.SUCCESS_COLOR) == surface.SUCCESS_COLOR


def test_a_colour_is_painted_through_its_token_with_the_cell_module_on_the_page(
    skinned: JsRuntime,
):
    assert skinned.called("colour", surface.SUCCESS_COLOR) == (
        "var(--SUCCESS, " + surface.SUCCESS_COLOR + ")"
    )


#: Each size the list draws, beside every non-alias token name carrying it.
SIZE_CARRIERS = {
    "row_height": surface.ROW_HEIGHT,
    "ticker_col_width": surface.TICKER_COL_WIDTH,
    "outflow_pct_col_width": surface.OUTFLOW_PCT_COL_WIDTH,
    "lane_col_width": surface.LANE_COL_WIDTH,
    "lane_dot_radius": surface.LANE_DOT_RADIUS,
}


@pytest.mark.parametrize("field", sorted(SIZE_CARRIERS))
def test_no_size_the_list_draws_is_resolved_to_a_token(skinned: JsRuntime, field: str):
    """A size goes out as plain pixels because no name both carries it and means it."""
    value = SIZE_CARRIERS[field]
    assert skinned.called("length", value) == str(value) + "px"


def test_the_one_size_a_single_name_carries_is_refused_because_the_name_means_a_column(
    skinned: JsRuntime,
):
    """TABLE_COL_DETAIL_W names the bot table's detail column, not this % Out column."""
    assert carriers_of(surface.OUTFLOW_PCT_COL_WIDTH) == ["TABLE_COL_DETAIL_W"]
    assert skinned.called("length", surface.OUTFLOW_PCT_COL_WIDTH) == (
        str(surface.OUTFLOW_PCT_COL_WIDTH) + "px"
    )


def test_the_two_sizes_more_than_one_name_carries_are_refused_by_the_carrier_rule():
    assert len(carriers_of(surface.LANE_DOT_RADIUS)) > 1
    assert len(carriers_of(surface.LANE_COUNT)) > 1


def test_the_size_check_reads_a_resolvable_colour_as_resolvable(skinned: JsRuntime):
    """variableFor answers for a colour, so a plain pixel size is a refusal not a silence."""
    assert skinned.called("variableFor", surface.SUCCESS_COLOR) == "SUCCESS"
    assert skinned.called("variableFor", surface.ROW_HEIGHT) is None


def as_css(value: Any) -> set:
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


def list_values() -> set:
    """Every colour, figure, name and word the list and its sheet paint."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        found |= set(payload["column_headers"])
        for width in payload["column_widths_in_use"]:
            found |= as_css(width)
        for number in (
            payload["row_height"],
            payload["total_cols"],
            payload["lane_dot_radius"],
            payload["wire_pen_width_px"],
            payload["opacity_pct"],
        ):
            found |= as_css(number)
        for field in ("success_color", "error_color", "warning_color"):
            found.add(payload[field])
        for row in payload["rows"]:
            for cell in row:
                if cell is None:
                    continue
                found |= {str(cell["text"]), str(cell["color"])}
                found |= as_css(cell["alignment"])
        for line in payload["log_lines"]:
            found |= set(line)
    found.discard("")
    return found


def token_values() -> set:
    found: set = set()
    for value in token_payload()["tokens"].values():
        found |= as_css(value)
    found.discard("")
    return found


def published_strings() -> set:
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                found.add(key)
                walk(value)
            return
        if isinstance(node, list):
            for one in node:
                walk(one)
            return
        if isinstance(node, str):
            found.add(node)

    for name in STATE_NAMES:
        walk(state_payload(name))
    found.discard("")
    return found


LIST_VALUES = list_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every published string the module writes as a literal, each one a name.
NAMED_WORDS = sorted(
    {
        "actions",
        "all_drawn_info",
        "alignment",
        "alpha_scale",
        "alpha_unit",
        "alternating_row_colors",
        "amount_text_format",
        "base_end_color",
        "base_start_color",
        "begin_painter",
        "bot_id",
        "bot_id_role",
        "bot_swarm_list.state",
        "bot_id_role_value",
        "bot_ids",
        "branches",
        "bridge_actions",
        "brush",
        "bus_topics",
        "calls",
        "canvas_accessible_name",
        "canvas_base_kind",
        "canvas_kind",
        "canvas_style_sheet",
        "canvas_transparent_for_mouse",
        "cell_kind",
        "cell_text_selectable",
        "centred_alignment",
        "centred_alignment_value",
        "col_inflow",
        "col_lane_0",
        "col_lane_last",
        "col_outflow",
        "col_outflow_pct",
        "col_ticker",
        "color",
        "coloured_columns",
        "column_headers",
        "column_widths",
        "column_widths_in_use",
        "draw_ellipse",
        "draw_line",
        "edit_triggers",
        "end_painter",
        "error_color",
        "flow_col_width",
        "focus_policy",
        "focus_policy_value",
        "gradient_end_stop",
        "gradient_start_stop",
        "horizontal_scroll_policy",
        "inflow_color",
        "info_level",
        "kind",
        "lane_alignment_value",
        "lane_assignments",
        "lane_cell_text",
        "lane_col_width",
        "lane_column_x",
        "lane_columns",
        "lane_count",
        "lane_dot_radius",
        "lane_header_format",
        "list_accessible_name",
        "list_base_kind",
        "list_kind",
        "list_style_sheet",
        "log_lines",
        "logger_name",
        "method",
        "missing_amount",
        "missing_text",
        "no_coordinate",
        "no_pen_style",
        "no_row",
        "opacity_full_pct",
        "opacity_max_pct",
        "opacity_min_pct",
        "opacity_pct",
        "opacity_scale",
        "outflow_color",
        "outflow_pct_col_width",
        "paint_branches",
        "paint_nothing",
        "paint_skip",
        "paint_wire",
        "pct_committed_color",
        "pct_headroom_color",
        "pct_headroom_limit",
        "pct_near_cap_color",
        "pct_near_cap_limit",
        "pct_no_export_color",
        "pct_text_format",
        "phase_period",
        "primary_bright_color",
        "pulse_color",
        "pulse_half_width",
        "readout_columns",
        "reason_no_lane",
        "reason_unlisted",
        "render_hint",
        "render_hint_value",
        "resize_mode",
        "row_count",
        "row_height",
        "row_index_map",
        "row_keys",
        "row_y_centers",
        "rows",
        "selection_behavior",
        "set_brush",
        "set_brush_call",
        "set_gradient_pen",
        "set_opacity",
        "set_pen_style",
        "set_render_hint",
        "show_grid",
        "size_policy",
        "skin",
        "source_dot_color",
        "success_color",
        "target_dot_color",
        "text",
        "text_elide_mode",
        "text_muted_color",
        "ticker_col_width",
        "timer_delays_ms",
        "timers",
        "total_cols",
        "undrawable",
        "undrawable_reasons",
        "undrawable_wire_count",
        "undrawn_detail_format",
        "undrawn_detail_join",
        "undrawn_warning",
        "unset_brush",
        "unset_color",
        "vertical_header_visible",
        "warning_color",
        "warning_level",
        "wire_count",
        "wire_id_format",
        "wire_keys",
        "wire_order",
        "wire_pen_style",
        "wire_pen_width_px",
        "word_wrap",
        "written_cell_count",
    }
)


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a value the surface owns."""
    assert not MODULE_LITERALS[
        "numbers"
    ], f"bot_swarm_list.js holds numeric literals: {MODULE_LITERALS['numbers']}"


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"bot_swarm_list.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_list_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & LIST_VALUES)
    assert not written, f"bot_swarm_list.js spells out list values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"bot_swarm_list.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert written == NAMED_WORDS, (
        f"the module names {sorted(set(written) - set(NAMED_WORDS))} more and "
        f"{sorted(set(NAMED_WORDS) - set(written))} fewer published strings "
        "than the list allows"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_list_shows():
    overlap = sorted(set(NAMED_WORDS) & LIST_VALUES)
    assert not overlap, f"these named words are values the list paints: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "bot_swarm_list.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


PLANTED_LINES = {
    "colour": 'var written = "#00ffcc";',
    "inflow_colour": 'var written = "' + surface.INFLOW_COLOR + '";',
    "muted_colour": 'var written = "' + surface.TEXT_MUTED_COLOR + '";',
    "header": 'var written = "' + surface.COLUMN_HEADERS[0] + '";',
    "lane_header": 'var written = "' + surface.COLUMN_HEADERS[-1] + '";',
    "row_height": "var written = " + str(surface.ROW_HEIGHT) + ";",
    "lane_count": "var written = " + str(surface.LANE_COUNT) + ";",
    "alignment": "var written = " + str(surface.CENTRED_ALIGNMENT_VALUE) + ";",
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
    if strings & LIST_VALUES:
        caught.add("list_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_a_planted_line(kind: str):
    caught = caught_by_scan(PLANTED_LINES[kind])
    assert caught, f"the scan reported nothing on the planted {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


#: The file the swap below moves over the module, named for this unit.
SPARE_PATH = MODULE_PATH.with_name("bot_swarm_list.literal_scan.js")
SWAP_RETRIES = 20
SWAP_PAUSE_SEC = 0.05


def swap_module(content: bytes) -> None:
    """os.replace swaps the module file in one step, so no worker reads half."""
    SPARE_PATH.write_bytes(content)
    for attempt in range(SWAP_RETRIES):
        try:
            os.replace(SPARE_PATH, MODULE_PATH)
            return
        except PermissionError:
            if attempt == SWAP_RETRIES - 1:
                raise
            time.sleep(SWAP_PAUSE_SEC)


def test_each_planted_literal_is_caught_in_the_module_file_itself():
    original = MODULE_PATH.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    assert original.decode("utf-8") == MODULE_SOURCE
    caught_each = {}
    try:
        for kind in sorted(PLANTED_LINES):
            swap_module(original + PLANTED_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(original)
            after = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
            assert after == before, f"the file was not restored after the {kind} line"
    finally:
        swap_module(original)
        SPARE_PATH.unlink(missing_ok=True)
    quiet = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not quiet, f"the scan reported nothing on these lines in the file: {quiet}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_planted_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, line in sorted(PLANTED_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetBotSwarmList") == "function", kind


def as_javascript(value: Any) -> Any:
    if type(value) is int and abs(value) > BIGGEST_EXACT_INTEGER:
        return float(value)
    return json.loads(json.dumps(value))


HOSTILE_CELLS = {
    "text is a number": {"text": 1234.5},
    "text is a flag": {"text": True},
    "text is empty": {"text": ""},
    "text is 200 characters": {"text": LONG_NAME},
    "text holds markup": {"text": MARKUP_NAME},
    "text holds a newline": {"text": "first\nsecond"},
    "alignment is text": {"alignment": "132"},
    "alignment is huge": {"alignment": 10**24},
    "colour is a number": {"color": 7},
    "brush is unknown": {"brush": "NoSuchBrush"},
    "bot is a number": {"bot_id": 7},
    "bot is 200 characters": {"bot_id": LONG_NAME},
}


@pytest.mark.parametrize("case", sorted(HOSTILE_CELLS))
def test_a_hostile_cell_reaches_the_module_unchanged(js: JsRuntime, case: str):
    """The module carries the exact value the surface produced, repairing nothing."""
    payload = state_payload("one")
    payload["rows"][0][0].update(HOSTILE_CELLS[case])
    js.push(payload)
    held = js.json("acervatorSwarmList.cellAt(0, 0)")
    for name, value in HOSTILE_CELLS[case].items():
        assert held[name] == as_javascript(value), f"{case}/{name}"


def test_the_hostile_cell_check_reads_a_value_the_module_would_have_changed():
    assert as_javascript(10**24) != 10**24
    assert as_javascript("132") == "132"
    assert as_javascript(True) is True


HOSTILE_FIELDS = {
    "row_height is text": ("row_height", "30"),
    "total_cols is text": ("total_cols", "12"),
    "row_count disagrees": ("row_count", 99),
    "wire_count is text": ("wire_count", "1"),
    "bot_ids is a bag": ("bot_ids", {}),
    "column_headers is text": ("column_headers", "Ticker"),
    "calls is a bag": ("calls", {}),
    "rows is text": ("rows", "not rows"),
    "opacity_pct is huge": ("opacity_pct", 10**24),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_FIELDS))
def test_a_hostile_field_leaves_the_module_loaded_and_answering(
    js: JsRuntime, case: str
):
    """A module that threw here would answer nothing at all for the whole list."""
    field, value = HOSTILE_FIELDS[case]
    payload = state_payload("many")
    payload[field] = value
    js.push(payload)
    assert js.json("acervatorSwarmList.isLoaded()") is True
    assert js.called("field", field) == as_javascript(value)


NOT_A_NUMBER = {
    "not a number": float("nan"),
    "an infinity": float("inf"),
    "a negative infinity": float("-inf"),
}


@pytest.mark.parametrize("case", sorted(NOT_A_NUMBER))
def test_a_not_a_number_never_reaches_the_module_at_all(js: JsRuntime, case: str):
    """JSON.parse refuses NaN, so the frame is dropped before the module sees it."""
    payload = state_payload("one")
    payload["rows"][0][0]["alignment"] = NOT_A_NUMBER[case]
    js.bind_json("PAYLOAD", payload)
    raised = js.raised("acervatorSetBotSwarmList(JSON.parse(PAYLOAD))")
    assert raised, f"{case} parsed where the real page drops the frame"
    assert "JSON" in raised or "SyntaxError" in raised, raised


def test_a_real_number_in_the_same_field_parses(js: JsRuntime):
    payload = state_payload("one")
    payload["rows"][0][0]["alignment"] = 1.5
    js.bind_json("PAYLOAD", payload)
    assert js.raised("acervatorSetBotSwarmList(JSON.parse(PAYLOAD))") == ""
    assert js.json("acervatorSwarmList.cellAt(0, 0)")["alignment"] == 1.5


def test_a_very_large_alignment_loses_precision_crossing_the_bridge(js: JsRuntime):
    payload = state_payload("one")
    payload["rows"][0][0]["alignment"] = 10**24
    js.push(payload)
    held = js.json("acervatorSwarmList.cellAt(0, 0)")["alignment"]
    assert held == float(10**24)
    assert held != 10**24, "the bridge kept every digit"


def test_two_bots_sharing_one_name_collapse_in_the_row_lookup():
    """Reported and not repaired: the shipped map is keyed by bot, so one row wins."""
    twins = [
        bot("bot-a", "BTC-USD", 1.0, 0.0, 0.0),
        bot("bot-a", "ETH-USD", 2.0, 0.0, 0.0),
    ]
    payload = build({"rows": twins})
    assert payload["bot_ids"] == ["bot-a", "bot-a"]
    assert payload["row_index_map"] == {"bot-a": 1}
    assert payload["row_count"] == len(twins)


def test_a_duplicate_bot_name_still_draws_both_rows(js: JsRuntime):
    twins = [
        bot("bot-a", "BTC-USD", 1.0, 0.0, 0.0),
        bot("bot-a", "ETH-USD", 2.0, 0.0, 0.0),
    ]
    js.push(build({"rows": twins}))
    assert js.json("acervatorSwarmList.rowBotIds()") == ["bot-a", "bot-a"]
    assert js.json("acervatorSwarmList.staleRows()") == []
    assert [one["texts"][0] for one in js.json("acervatorSwarmList.rowTexts()")] == [
        "BTC-USD",
        "ETH-USD",
    ]


def test_a_two_hundred_character_bot_name_reaches_the_cell_whole(js: JsRuntime):
    payload = build({"rows": [bot("bot-a", LONG_NAME, 1.0, 0.0, 0.0)]})
    js.push(payload)
    assert js.json("acervatorSwarmList.cellAt(0, 0)")["text"] == LONG_NAME


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorSwarmList.isLoaded()") is False
        assert js.json("acervatorSwarmList.rows()") == []
        assert report["declared"] is None
        assert report["held"] is None
        assert [one["fault"] for one in report["faults"]] == ["not-an-object"]


def test_a_row_that_is_not_a_list_is_named(js: JsRuntime):
    payload = state_payload("many")
    payload["rows"][1] = "not a row"
    report = js.push(payload)
    assert {
        "where": "row:1",
        "field": None,
        "fault": "not-a-list",
        "detail": "string",
    } in report["faults"]


def test_a_cell_that_is_not_an_object_is_named(js: JsRuntime):
    payload = state_payload("many")
    payload["rows"][1][3] = "not a cell"
    report = js.push(payload)
    assert {
        "where": "row:1/cell:3",
        "field": None,
        "fault": "not-an-object",
        "detail": "string",
    } in report["faults"]


def test_a_row_shorter_than_the_column_count_is_named(js: JsRuntime):
    payload = state_payload("many")
    payload["rows"][2] = payload["rows"][2][:-1]
    report = js.push(payload)
    assert {
        "where": "row:2",
        "field": None,
        "fault": "short-row",
        "detail": payload["total_cols"] - 1,
    } in report["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_short_row_check_is_quiet_on_every_whole_payload(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    assert [one for one in report["faults"] if one["fault"] == "short-row"] == []


@pytest.mark.parametrize("field", ["rows", "bot_ids", "calls", "column_headers"])
def test_a_published_field_the_payload_omits_is_named(js: JsRuntime, field: str):
    payload = state_payload("many")
    del payload[field]
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"]


@pytest.mark.parametrize("field", ["rows", "bot_ids", "calls", "column_headers"])
def test_a_published_field_carrying_null_is_named(js: JsRuntime, field: str):
    payload = state_payload("many")
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_a_name_the_payload_never_carried_is_not_a_field(js: JsRuntime):
    """Every JavaScript object inherits names such as constructor and toString."""
    js.push(state_payload("many"))
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        assert js.called("field", inherited) is None
        assert js.called("action", inherited) is None


def test_the_inherited_name_check_still_reads_a_real_field(js: JsRuntime):
    js.push(state_payload("many"))
    assert js.called("field", "row_height") == surface.ROW_HEIGHT


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("many"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadBotSwarmList();")
    drain_events()
    assert js.json("window.CALLS") == [[surface.METHOD, "{}"]]
    assert js.json("acervatorSwarmList.isLoaded()") is True


def test_the_module_passes_a_caller_s_parameters_to_the_surface(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("many"))
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", {"reset": True})
    js.run("acervatorLoadBotSwarmList(JSON.parse(WANTED));")
    drain_events()
    assert js.json("window.CALLS") == [[surface.METHOD, '{"reset":true}']]


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("many"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadBotSwarmList(); acervatorLoadBotSwarmList();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("many"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadBotSwarmList();")
    drain_events()
    js.run("acervatorSwarmList.forget(); acervatorLoadBotSwarmList();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadBotSwarmList();")
    drain_events()
    assert js.json("acervatorSwarmList.isLoaded()") is False
    assert js.json("acervatorSwarmList.loadError()") == (
        "the preload bridge is not present"
    )


def test_a_refused_first_ask_is_not_remembered(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("many"))
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadBotSwarmList();"
    )
    drain_events()
    assert js.json("acervatorSwarmList.isLoaded()") is False
    js.run("acervatorLoadBotSwarmList();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorSwarmList.isLoaded()") is True


def test_the_bridge_handler_serves_the_same_fields_as_the_view_model(js: JsRuntime):
    """view_model keeps one list per process, so it is left reset."""
    try:
        served = json.loads(
            json.dumps(
                surface.view_model(
                    {"reset": True, "action": "set_bots", "rows": ONE_BOT}
                ),
                ensure_ascii=True,
            )
        )
        js.push(served)
        assert sorted(served) == sorted(declared_fields(js))
        assert js.json("acervatorSwarmList.isLoaded()") is True
    finally:
        surface.view_model({"reset": True})


class Browser:
    """A Browser drives the real renderer page in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
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
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetBotSwarmList") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the swarm list module: readyState "
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
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


STYLE_NAMES = [
    "color",
    "width",
    "height",
    "whiteSpace",
    "textOverflow",
    "overflow",
    "textAlign",
    "userSelect",
    "webkitUserSelect",
    "position",
    "pointerEvents",
    "borderCollapse",
]

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

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
    "      var own = '';"
    "      Array.prototype.slice.call(el.childNodes).forEach(function (n) {"
    "        if (n.nodeType === Node.TEXT_NODE) { own += n.nodeValue; } });"
    "      found.push({ path: here, tag: el.tagName, attrs: attrs,"
    "        text: own, whole: el.textContent,"
    "        scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)


def give_tokens(browser: Browser) -> int:
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_list(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetBotSwarmList(JSON.parse(window.PAYLOAD));"
        "acervatorSwarmList.renderList(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    return json.loads(browser.js(READ_PARTS))


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def probe_style(browser: Browser, css: str, names: list) -> dict:
    return browser.parsed(
        "window.probeStyle(" + json.dumps(css) + ", " + json.dumps(names) + ")"
    )


CELL_PATH = "swarm/list/row/cell"
HEADER_PATH_AT = "swarm/list/head-row/header"


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorSwarmList") == "object"
    assert browser.js("typeof window.acervatorSetBotSwarmList") == "function"
    assert browser.js("typeof window.acervatorLoadBotSwarmList") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_list(browser, state_payload("wired"))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_drawn_list_names_every_part_a_check_reads(browser: Browser):
    payload = state_payload("wired")
    parts = draw_list(browser, payload)
    paths = sorted({one["path"] for one in parts})
    assert paths == [
        "swarm",
        "swarm/list",
        "swarm/list/head-row",
        "swarm/list/head-row/header",
        "swarm/list/row",
        "swarm/list/row/cell",
        "swarm/sheet",
        "swarm/sheet/canvas",
        "swarm/sheet/canvas/dot",
        "swarm/sheet/canvas/wire",
    ], f"the list drew {paths}"
    root = only(parts, "swarm")
    assert root["attrs"]["data-declared-rows"] == str(payload["row_count"])
    assert root["attrs"]["data-held-rows"] == str(len(payload["rows"]))
    assert root["attrs"]["data-written-cells"] == str(payload["written_cell_count"])
    table = only(parts, "swarm/list")
    assert table["attrs"]["aria-label"] == payload["list_accessible_name"]
    assert table["attrs"]["data-elide"] == payload["text_elide_mode"]
    assert table["attrs"]["data-word-wrap"] == str(payload["word_wrap"]).lower()
    assert table["attrs"]["data-show-grid"] == str(payload["show_grid"]).lower()
    assert table["attrs"]["data-focus-policy"] == payload["focus_policy"]
    assert table["attrs"]["data-focus-policy-value"] == str(
        payload["focus_policy_value"]
    )
    assert table["attrs"]["data-selection-behavior"] == payload["selection_behavior"]
    assert table["attrs"]["data-edit-triggers"] == payload["edit_triggers"]
    assert (
        table["attrs"]["data-horizontal-scroll"] == payload["horizontal_scroll_policy"]
    )
    assert table["attrs"]["data-resize-mode"] == payload["resize_mode"]
    sheet = only(parts, "swarm/sheet")
    assert sheet["attrs"]["aria-label"] == payload["canvas_accessible_name"]
    assert sheet["attrs"]["data-wire-count"] == str(payload["wire_count"])
    assert sheet["attrs"]["data-undrawable"] == str(payload["undrawable_wire_count"])
    assert sheet["attrs"]["data-opacity-pct"] == str(payload["opacity_pct"])
    for one in at_path(parts, "swarm/list/row"):
        assert "data-row" in one["attrs"]
        assert "data-bot-id" in one["attrs"]
        assert "data-cell-bot-id" in one["attrs"]
        assert "data-stale" in one["attrs"]
    for one in at_path(parts, CELL_PATH):
        assert "data-column" in one["attrs"]
        assert "data-brush" in one["attrs"]
        assert "data-color" in one["attrs"]
        assert "data-alignment-value" in one["attrs"]


@pytest.mark.parametrize("state", ["empty", "one", "many", "wired", "stale"])
def test_the_drawn_list_shows_every_row_in_the_order_the_surface_published(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_list(browser, payload)
    drawn = at_path(parts, "swarm/list/row")
    assert len(drawn) == len(payload["rows"])
    assert [one["attrs"]["data-row"] for one in drawn] == [
        str(at) for at in range(len(payload["rows"]))
    ]
    shown = [one["text"] for one in at_path(parts, CELL_PATH)]
    written = [cell["text"] for row in payload["rows"] for cell in row if cell]
    assert shown == written


def test_the_drawn_row_order_check_names_a_reordered_fleet(browser: Browser):
    parts = draw_list(browser, build({"rows": SWAPPED_BOTS}))
    shown = [
        one["attrs"]["data-cell-bot-id"] for one in at_path(parts, "swarm/list/row")
    ]
    original = [one["bot_id"] for one in THREE_BOTS]
    assert shown != original, "the check cannot see a reordered fleet"
    assert shown == ["bot-a", "bot-c", "bot-b"]


def test_the_drawn_row_order_check_is_quiet_on_the_shipped_fleet(browser: Browser):
    parts = draw_list(browser, state_payload("many"))
    shown = [
        one["attrs"]["data-cell-bot-id"] for one in at_path(parts, "swarm/list/row")
    ]
    assert shown == [one["bot_id"] for one in THREE_BOTS]


def test_the_drawn_list_names_a_stale_row_by_the_bot_that_still_shows(browser: Browser):
    parts = draw_list(browser, state_payload("stale"))
    rows = at_path(parts, "swarm/list/row")
    assert [one["attrs"]["data-stale"] for one in rows] == ["false", "true", "true"]
    assert [one["attrs"]["data-cell-bot-id"] for one in rows] == [
        "bot-a",
        "bot-b",
        "bot-c",
    ]
    assert [one["attrs"].get("data-bot-id") for one in rows] == [
        "bot-a",
        "bot-bad",
        None,
    ]


def test_the_stale_check_reads_a_whole_fleet_as_not_stale(browser: Browser):
    parts = draw_list(browser, state_payload("many"))
    rows = at_path(parts, "swarm/list/row")
    assert [one["attrs"]["data-stale"] for one in rows] == ["false"] * len(rows)


@pytest.mark.parametrize("state", ["one", "many", "stale"])
def test_each_drawn_cell_paints_the_colour_the_surface_published(
    browser: Browser, state: str
):
    """Every value is compared against a probe, never a typed number."""
    payload = state_payload(state)
    parts = draw_list(browser, payload)
    drawn = at_path(parts, CELL_PATH)
    cells = [cell for row in payload["rows"] for cell in row]
    assert drawn, f"{state} drew no cell; the check cannot report"
    unpainted = probe_style(browser, "", ["color"])["color"]
    differing = {}
    for at, one in enumerate(drawn):
        cell = cells[at]
        if cell["brush"] == payload["unset_brush"]:
            expected = unpainted
        else:
            expected = probe_style(browser, "color:" + cell["color"], ["color"])[
                "color"
            ]
        if one["style"]["color"] != expected:
            differing[at] = (expected, one["style"]["color"])
    assert not differing, f"{state}: {len(differing)} cells paint wrong: {differing}"


def test_the_colour_check_names_one_changed_colour(browser: Browser):
    payload = state_payload("many")
    payload["rows"][0][surface.COL_INFLOW]["color"] = payload["warning_color"]
    parts = draw_list(browser, payload)
    drawn = at_path(parts, CELL_PATH)
    original = [cell for row in state_payload("many")["rows"] for cell in row]
    unpainted = probe_style(browser, "", ["color"])["color"]
    differing = []
    for at, one in enumerate(drawn):
        cell = original[at]
        expected = (
            unpainted
            if cell["brush"] == payload["unset_brush"]
            else probe_style(browser, "color:" + cell["color"], ["color"])["color"]
        )
        if one["style"]["color"] != expected:
            differing.append(at)
    assert differing == [surface.COL_INFLOW], f"the check named {differing}"


def test_an_unpainted_cell_takes_no_colour_of_its_own(browser: Browser):
    parts = draw_list(browser, state_payload("many"))
    drawn = at_path(parts, CELL_PATH)
    ticker = drawn[surface.COL_TICKER]
    inflow = drawn[surface.COL_INFLOW]
    assert ticker["attrs"]["data-brush"] == surface.UNSET_BRUSH
    assert inflow["attrs"]["data-brush"] == surface.SET_BRUSH
    assert ticker["style"]["color"] == probe_style(browser, "", ["color"])["color"]
    assert inflow["style"]["color"] != ticker["style"]["color"]


def test_each_drawn_cell_takes_the_width_the_surface_published(browser: Browser):
    payload = state_payload("many")
    parts = draw_list(browser, payload)
    widths = payload["column_widths_in_use"]
    headers = at_path(parts, HEADER_PATH_AT)
    assert len(headers) == len(widths)
    differing = {}
    for at, one in enumerate(headers):
        expected = probe_style(browser, "width:" + str(widths[at]) + "px", ["width"])
        if one["style"]["width"] != expected["width"]:
            differing[at] = (expected["width"], one["style"]["width"])
    assert not differing, f"{len(differing)} headers take a wrong width: {differing}"


def test_the_width_check_names_one_changed_width(browser: Browser):
    payload = state_payload("many")
    payload["column_widths_in_use"][0] += 40
    parts = draw_list(browser, payload)
    widths = state_payload("many")["column_widths_in_use"]
    headers = at_path(parts, HEADER_PATH_AT)
    differing = [
        at
        for at, one in enumerate(headers)
        if one["style"]["width"]
        != probe_style(browser, "width:" + str(widths[at]) + "px", ["width"])["width"]
    ]
    assert differing == [0], f"the check named {differing}"


def test_a_drawn_cell_clips_its_text_rather_than_wrapping_it(browser: Browser):
    """The shipped table elides right, and its rows are a fixed height."""
    payload = build({"rows": [bot("bot-a", LONG_NAME, 1.0, 0.0, 0.0)]})
    parts = draw_list(browser, payload)
    cell = at_path(parts, CELL_PATH)[surface.COL_TICKER]
    wanted = probe_style(
        browser,
        "overflow:hidden;white-space:nowrap;text-overflow:ellipsis",
        ["overflow", "whiteSpace", "textOverflow"],
    )
    assert cell["style"]["whiteSpace"] == wanted["whiteSpace"]
    assert cell["style"]["textOverflow"] == wanted["textOverflow"]
    assert cell["style"]["overflow"] == wanted["overflow"]
    assert cell["scrollWidth"] > cell["clientWidth"], "the long name fits in the cell"


def test_the_clipping_check_reads_a_short_name_as_fitting(browser: Browser):
    parts = draw_list(browser, state_payload("one"))
    cell = at_path(parts, CELL_PATH)[surface.COL_TICKER]
    assert cell["scrollWidth"] <= cell["clientWidth"]


def test_a_drawn_cell_refuses_a_drag_selection(browser: Browser):
    """The shipped table selects rows, so its cell text cannot be dragged over."""
    parts = draw_list(browser, state_payload("many"))
    wanted = probe_style(browser, "user-select:none", ["userSelect"])["userSelect"]
    for one in at_path(parts, CELL_PATH):
        picked = one["style"]["userSelect"] or one["style"]["webkitUserSelect"]
        assert picked == wanted, f"{one['attrs']['data-column']}: {one['style']}"


def test_the_selection_check_reads_a_selectable_probe_as_selectable(browser: Browser):
    draw_list(browser, state_payload("many"))
    allowed = probe_style(browser, "user-select:text", ["userSelect"])["userSelect"]
    refused = probe_style(browser, "user-select:none", ["userSelect"])["userSelect"]
    assert allowed != refused


def test_the_drawn_table_takes_the_tab_stop_its_focus_policy_names(browser: Browser):
    payload = state_payload("many")
    parts = draw_list(browser, payload)
    table = only(parts, "swarm/list")
    assert payload["focus_policy"] == surface.FOCUS_POLICY
    assert table["attrs"]["tabindex"] == "0"
    assert browser.js("window.HOST.querySelector('table').tabIndex") == 0


def test_the_tab_stop_check_reads_an_unknown_policy_as_no_tab_stop(browser: Browser):
    payload = state_payload("many")
    payload["focus_policy"] = "NoSuchFocus"
    parts = draw_list(browser, payload)
    assert "tabindex" not in only(parts, "swarm/list")["attrs"]


def test_the_lane_sheet_lets_a_click_through_to_the_list(browser: Browser):
    payload = state_payload("wired")
    parts = draw_list(browser, payload)
    sheet = only(parts, "swarm/sheet")
    wanted = probe_style(browser, "pointer-events:none", ["pointerEvents"])
    assert payload["canvas_transparent_for_mouse"] is True
    assert sheet["style"]["pointerEvents"] == wanted["pointerEvents"]


def test_the_click_through_check_reads_a_solid_probe_as_solid(browser: Browser):
    draw_list(browser, state_payload("wired"))
    solid = probe_style(browser, "pointer-events:auto", ["pointerEvents"])
    none = probe_style(browser, "pointer-events:none", ["pointerEvents"])
    assert solid["pointerEvents"] != none["pointerEvents"]


def test_each_drawn_wire_runs_between_the_two_coordinates_the_sheet_named(
    browser: Browser,
):
    payload = state_payload("wired")
    parts = draw_list(browser, payload)
    lines = at_path(parts, "swarm/sheet/canvas/wire")
    drawn = [one for one in payload["calls"] if one[0] == surface.DRAW_LINE]
    assert len(lines) == len(drawn)
    for at, one in enumerate(lines):
        points = drawn[at][1]
        assert [
            one["attrs"]["x1"],
            one["attrs"]["y1"],
            one["attrs"]["x2"],
            one["attrs"]["y2"],
        ] == [str(value) for value in points]


def test_the_wire_coordinate_check_names_a_moved_wire(browser: Browser):
    payload = state_payload("wired")
    for call in payload["calls"]:
        if call[0] == surface.DRAW_LINE:
            call[1][0] += 25
            call[1][2] += 25
    parts = draw_list(browser, payload)
    original = [
        one for one in state_payload("wired")["calls"] if one[0] == surface.DRAW_LINE
    ]
    lines = at_path(parts, "swarm/sheet/canvas/wire")
    differing = [
        at
        for at, one in enumerate(lines)
        if one["attrs"]["x1"] != str(original[at][1][0])
    ]
    assert differing == [0], f"the check named {differing}"


def test_each_drawn_dot_paints_the_colour_the_sheet_named(browser: Browser):
    payload = state_payload("wired")
    parts = draw_list(browser, payload)
    dots = at_path(parts, "swarm/sheet/canvas/dot")
    brushes = [one[1] for one in payload["calls"] if one[0] == surface.SET_BRUSH_CALL]
    assert len(dots) == len(brushes)
    unit = payload["alpha_unit"]
    for at, one in enumerate(dots):
        wanted = "rgba(%d, %d, %d, %s)" % (
            brushes[at][0],
            brushes[at][1],
            brushes[at][2],
            repr(brushes[at][3] * unit),
        )
        got = probe_style(browser, "color:" + one["attrs"]["fill"], ["color"])["color"]
        expected = probe_style(browser, "color:" + wanted, ["color"])["color"]
        assert got == expected, f"dot {at}: {one['attrs']['fill']} against {wanted}"


def test_the_dot_colour_check_names_a_changed_brush(browser: Browser):
    payload = state_payload("wired")
    for call in payload["calls"]:
        if call[0] == surface.SET_BRUSH_CALL:
            call[1] = [255, 0, 0, 255]
            break
    parts = draw_list(browser, payload)
    dots = at_path(parts, "swarm/sheet/canvas/dot")
    original = [
        one[1]
        for one in state_payload("wired")["calls"]
        if one[0] == surface.SET_BRUSH_CALL
    ]
    unit = payload["alpha_unit"]
    differing = []
    for at, one in enumerate(dots):
        wanted = "rgba(%d, %d, %d, %s)" % (
            original[at][0],
            original[at][1],
            original[at][2],
            repr(original[at][3] * unit),
        )
        got = probe_style(browser, "color:" + one["attrs"]["fill"], ["color"])["color"]
        expected = probe_style(browser, "color:" + wanted, ["color"])["color"]
        if got != expected:
            differing.append(at)
    assert differing == [0], f"the check named {differing}"


def test_the_sheet_dims_every_wire_by_the_opacity_the_slider_set(browser: Browser):
    payload = state_payload("dimmed")
    parts = draw_list(browser, payload)
    canvas = only(parts, "swarm/sheet/canvas")
    named = [one for one in payload["calls"] if one[0] == surface.SET_OPACITY]
    assert canvas["attrs"]["opacity"] == str(named[0][1])
    assert only(parts, "swarm/sheet")["attrs"]["data-opacity-pct"] == "40"


def test_the_opacity_check_reads_a_full_slider_as_full(browser: Browser):
    payload = state_payload("wired")
    parts = draw_list(browser, payload)
    assert only(parts, "swarm/sheet")["attrs"]["data-opacity-pct"] == str(
        surface.OPACITY_FULL_PCT
    )
    assert only(parts, "swarm/sheet/canvas")["attrs"]["opacity"] != "0.4"


def rewrite_token(browser: Browser, name: str, value: Any) -> None:
    browser.js(
        "document.documentElement.style.setProperty("
        + json.dumps("--" + name)
        + ", "
        + json.dumps(str(value))
        + ");"
    )


def changed_paths(before: list, after: list) -> set:
    assert len(before) == len(after), "the list drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add(
                    (one["path"] + "/" + one["attrs"].get("data-column", ""), key)
                )
    return moved


def test_the_drawn_list_follows_the_inflow_colour_token(browser: Browser):
    """The token is rewritten and only the inflow cells move."""
    payload = state_payload("many")
    before = draw_list(browser, payload)
    assert carriers_of(surface.INFLOW_COLOR) == ["SUCCESS"]
    rewrite_token(browser, "SUCCESS", dss.WARNING)
    moved = changed_paths(before, read_parts(browser))
    assert moved == {
        (CELL_PATH + "/" + str(surface.COL_INFLOW), "color")
    }, f"the token moved {sorted(moved)}"


def test_the_drawn_list_follows_the_export_share_colour_token(browser: Browser):
    payload = state_payload("many")
    before = draw_list(browser, payload)
    assert carriers_of(surface.PCT_COMMITTED_COLOR) == ["ERROR"]
    rewrite_token(browser, "ERROR", dss.WARNING)
    moved = changed_paths(before, read_parts(browser))
    assert moved == {
        (CELL_PATH + "/" + str(surface.COL_OUTFLOW), "color"),
        (CELL_PATH + "/" + str(surface.COL_OUTFLOW_PCT), "color"),
    }, f"the token moved {sorted(moved)}"


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(browser: Browser):
    before = draw_list(browser, state_payload("many"))
    assert changed_paths(before, read_parts(browser)) == set()


def test_the_ticker_cell_follows_no_token_because_it_paints_no_colour(browser: Browser):
    before = draw_list(browser, state_payload("many"))
    assert carriers_of(surface.UNSET_COLOR) == ["TEXT_ON_LIGHT"]
    rewrite_token(browser, "TEXT_ON_LIGHT", dss.WARNING)
    assert changed_paths(before, read_parts(browser)) == set()


def test_a_markup_bot_name_draws_as_text_and_loads_nothing(browser: Browser):
    """A bot name holding an image tag reaches the page as characters."""
    browser.js(WATCH_VIOLATIONS)
    payload = build({"rows": [bot("bot-a", MARKUP_NAME, 1.0, 0.0, 0.0)]})
    images_before = browser.js("document.images.length")
    parts = draw_list(browser, payload)
    browser.settle(SETTLE_MS)
    cell = at_path(parts, CELL_PATH)[surface.COL_TICKER]
    assert cell["text"] == MARKUP_NAME
    assert browser.js("document.images.length") == images_before
    assert browser.parsed("window.VIOLATIONS") == []
    assert (
        browser.js("window.HOST.querySelectorAll('img, b').length") == 0
    ), "the markup became elements"


def test_the_markup_check_reads_a_real_image_as_an_image(browser: Browser):
    """The image count would not move for any markup at all if it never moved."""
    draw_list(browser, state_payload("one"))
    before = browser.js("document.images.length")
    browser.js(
        "window.PROBE = document.createElement('img');"
        "window.PROBE.src = 'data:image/gif;base64,R0lGOD';"
        "document.body.appendChild(window.PROBE);"
    )
    assert browser.js("document.images.length") == before + 1
    browser.js("window.PROBE.remove();")


def test_a_markup_bot_id_reaches_the_attribute_as_characters(browser: Browser):
    payload = build({"rows": [bot(MARKUP_NAME, "BTC-USD", 1.0, 0.0, 0.0)]})
    parts = draw_list(browser, payload)
    row = only(parts, "swarm/list/row")
    assert row["attrs"]["data-bot-id"] == MARKUP_NAME
    assert browser.js("window.HOST.querySelectorAll('img, b').length") == 0


def test_a_hostile_payload_still_draws_a_list(browser: Browser):
    """A module that threw here would draw no list and no row at all."""
    payload = state_payload("many")
    payload["rows"][0][0]["text"] = 7
    payload["rows"][1][1]["color"] = None
    payload["column_headers"] = None
    payload["column_widths_in_use"] = "not widths"
    payload["text_elide_mode"] = None
    parts = draw_list(browser, payload)
    assert only(parts, "swarm")
    assert len(at_path(parts, "swarm/list/row")) == len(payload["rows"])
    assert at_path(parts, CELL_PATH)[0]["text"] == "7"


def test_an_empty_fleet_draws_a_table_with_no_row(browser: Browser):
    payload = state_payload("empty")
    parts = draw_list(browser, payload)
    assert at_path(parts, "swarm/list/row") == []
    assert len(at_path(parts, HEADER_PATH_AT)) == len(payload["column_headers"])
    assert only(parts, "swarm")["attrs"]["data-held-rows"] == "0"


def test_the_drawn_table_is_as_wide_as_its_columns_add_up_to(browser: Browser):
    """Every column is fixed, so the list takes exactly their sum."""
    payload = state_payload("many")
    parts = draw_list(browser, payload)
    across = sum(payload["column_widths_in_use"])
    wanted = probe_style(browser, "width:" + str(across) + "px", ["width"])["width"]
    assert only(parts, "swarm/list")["style"]["width"] == wanted
    assert browser.parsed("acervatorSwarmList.widthAcross()") == across


def test_the_table_width_check_names_one_widened_column(browser: Browser):
    payload = state_payload("many")
    payload["column_widths_in_use"][0] += 40
    parts = draw_list(browser, payload)
    was = sum(state_payload("many")["column_widths_in_use"])
    wanted = probe_style(browser, "width:" + str(was) + "px", ["width"])["width"]
    assert only(parts, "swarm/list")["style"]["width"] != wanted


def test_each_drawn_row_takes_the_row_height_the_surface_published(browser: Browser):
    payload = state_payload("many")
    parts = draw_list(browser, payload)
    wanted = probe_style(
        browser, "height:" + str(payload["row_height"]) + "px", ["height"]
    )
    rows = at_path(parts, "swarm/list/row")
    assert rows, "the list drew no row; the check cannot report"
    for one in rows:
        assert one["style"]["height"] == wanted["height"], one["attrs"]["data-row"]


def test_the_row_height_check_names_one_shortened_row(browser: Browser):
    payload = state_payload("many")
    was = payload["row_height"]
    payload["row_height"] = was - 10
    parts = draw_list(browser, payload)
    wanted = probe_style(browser, "height:" + str(was) + "px", ["height"])["height"]
    differing = [
        one["attrs"]["data-row"]
        for one in at_path(parts, "swarm/list/row")
        if one["style"]["height"] != wanted
    ]
    assert len(differing) == len(payload["rows"]), f"the check named {differing}"


def test_each_readout_cell_is_centred_and_each_lane_cell_is_not(browser: Browser):
    payload = state_payload("many")
    parts = draw_list(browser, payload)
    centred = probe_style(browser, "text-align:center", ["textAlign"])["textAlign"]
    plain = probe_style(browser, "", ["textAlign"])["textAlign"]
    assert centred != plain, "the two alignments read alike; the check cannot report"
    drawn = at_path(parts, CELL_PATH)[: payload["total_cols"]]
    for column, one in enumerate(drawn):
        wanted = centred if column in payload["readout_columns"] else plain
        assert one["style"]["textAlign"] == wanted, column


def test_the_alignment_check_names_a_cell_whose_alignment_changed(browser: Browser):
    payload = state_payload("many")
    payload["rows"][0][surface.COL_INFLOW]["alignment"] = payload[
        "lane_alignment_value"
    ]
    parts = draw_list(browser, payload)
    centred = probe_style(browser, "text-align:center", ["textAlign"])["textAlign"]
    drawn = at_path(parts, CELL_PATH)[: payload["total_cols"]]
    differing = [
        column
        for column in payload["readout_columns"]
        if drawn[column]["style"]["textAlign"] != centred
    ]
    assert differing == [surface.COL_INFLOW], f"the check named {differing}"


def test_each_wire_is_painted_through_the_gradient_the_sheet_named(browser: Browser):
    payload = state_payload("wired")
    parts = draw_list(browser, payload)
    lines = at_path(parts, "swarm/sheet/canvas/wire")
    assert lines, "the sheet drew no wire; the check cannot report"
    stops = [one for one in payload["calls"] if one[0] == surface.SET_GRADIENT_PEN]
    for at, one in enumerate(lines):
        name = one["attrs"]["stroke"]
        assert name.startswith("url(#"), name
        held = browser.parsed(
            "(function () {"
            "  var g = window.HOST.querySelector('#' + "
            + json.dumps(name)
            + ".slice(5, -1));"
            "  return Array.prototype.slice.call(g.children).map(function (s) {"
            "    return [s.getAttribute('offset'), s.getAttribute('stop-color')]; });"
            "})()"
        )
        assert [float(pair[0]) for pair in held] == [
            float(one[0]) for one in stops[at][3]
        ]
        assert one["attrs"]["stroke-width"] == str(stops[at][4])


def test_the_gradient_check_names_a_wire_whose_stops_changed(browser: Browser):
    payload = state_payload("wired")
    for call in payload["calls"]:
        if call[0] == surface.SET_GRADIENT_PEN:
            call[3] = call[3][:2]
            break
    parts = draw_list(browser, payload)
    original = [
        one
        for one in state_payload("wired")["calls"]
        if one[0] == surface.SET_GRADIENT_PEN
    ]
    name = at_path(parts, "swarm/sheet/canvas/wire")[0]["attrs"]["stroke"]
    held = browser.parsed(
        "window.HOST.querySelector('#' + "
        + json.dumps(name)
        + ".slice(5, -1)).children.length"
    )
    assert held != len(original[0][3]), "the check cannot see a shortened gradient"
    assert held == 2


def test_the_list_names_the_grid_the_shipped_table_paints_and_paints_no_line():
    """Reported and not fixed: Qt draws the grid in a palette colour no surface holds."""
    payload = state_payload("many")
    assert payload["show_grid"] is True
    assert payload["list_style_sheet"] == ""
    assert "grid" not in {name.split("_")[0] for name in payload if "color" in name}


def logger_state(logger: logging.Logger) -> tuple:
    return (logger.level, tuple(sorted(id(one) for one in logger.handlers)))


def test_drawing_the_list_attaches_nothing_to_the_root_logger(browser: Browser):
    root = logging.getLogger()
    before = logger_state(root)
    draw_list(browser, state_payload("wired"))
    assert (
        logger_state(root) == before
    ), f"the root logger moved from {before} to {logger_state(root)}"


def test_the_logger_snapshot_reports_a_handler_that_was_added():
    named = logging.getLogger("acervator.bot_swarm_list_unit")
    before = logger_state(named)
    handler = logging.NullHandler()
    named.addHandler(handler)
    try:
        assert logger_state(named) != before
    finally:
        named.removeHandler(handler)
    assert logger_state(named) == before


def page_refs() -> list:
    return re.findall(r'src="([^"]+)"', INDEX_HTML.read_text(encoding="utf-8"))


def test_the_page_names_the_swarm_list_module_among_its_assets():
    named = [ref for ref in page_refs() if ref.endswith("bot_swarm_list.js")]
    assert len(named) == 1, f"the page names {len(named)} swarm list modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


@pytest.mark.parametrize("earlier", ["table_cells.js", "header_strip.js"])
def test_the_page_loads_the_modules_this_one_paints_through_first(earlier: str):
    refs = page_refs()
    assert refs.index("../../src/gui/web/" + earlier) < refs.index(
        "../../src/gui/web/bot_swarm_list.js"
    )
