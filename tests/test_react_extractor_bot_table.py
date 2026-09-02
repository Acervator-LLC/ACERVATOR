"""The React Extractor bot table, against extractor_bot_table_surface.py."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import extractor_bot_table_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "extractor_bot_table.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorExtractorTable."
SETTER = "acervatorSetExtractorTable"

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 500
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 3

HOST_WIDTH_PX = 900
HOST_HEIGHT_PX = 400
PICTURE_SIZE = (240, 40)

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
#: An empty tag pair a rich-text widget swallows and a plain one paints.
MARKUP_PROBE = "<span></span>ext"
PLAIN_PROBE = "ext"

CELL_PATH = "table/body/row/cell"
HEADER_PATH = "table/head/head-row/header"
ROW_PATH = "table/body/row"


def status(
    bot_id: str,
    state: str = "running",
    base: str = "BTC",
    chunk_usd: Any = 100.0,
    free_base: Any = 0.25,
    size_base: Any = 1.0,
    pool: str = "yellow",
    trades: Any = 7,
) -> dict:
    """One Extractor fleet status: its bot_id, its state and its chunk figures."""
    return {
        "bot_id": bot_id,
        "state": state,
        "chunk_size_usd": chunk_usd,
        "chunk_free_base": free_base,
        "chunk_size_base": size_base,
        "n_positions_open": 2,
        "n_positions_drawdown": 1,
        "pool_color": pool,
        "base_currency": base,
        "symbol": base + "-USD",
        "stats": {"total_trades": trades},
    }


ONE_BOT = [status("ext-a")]
THREE_BOTS = [
    status("ext-a"),
    status("ext-b", "paused", "ETH", 50.0, 0.0, 2.0, "red"),
    status("ext-c", "idle", "SOL", 0.0, 0.0, 0.0, "green", 0),
]
SWAPPED_BOTS = [THREE_BOTS[0], THREE_BOTS[2], THREE_BOTS[1]]
BAD_BOTS = [THREE_BOTS[0], status("ext-b", chunk_usd="abc"), THREE_BOTS[2]]
NEGATIVE_BOTS = [status("ext-neg", chunk_usd=-100.0, free_base=-0.5)]


def build(*steps: dict) -> dict:
    """One payload, each step driving the same table in the order given."""
    model = surface.ExtractorBotTableModel()
    for step in steps:
        if "bots" in step:
            try:
                model.update_bots(step["bots"])
            except ValueError:
                if not step.get("refuses"):
                    raise
        if "detail" in step:
            model._on_detail(step["detail"])
    return json.loads(json.dumps(surface.build_payload(model), ensure_ascii=True))


STATES: dict = {
    "empty": (),
    "one": ({"bots": ONE_BOT},),
    "many": ({"bots": THREE_BOTS},),
    "selected": ({"bots": THREE_BOTS}, {"detail": "ext-b"}),
    "refused": ({"bots": BAD_BOTS, "refuses": True},),
    "stale": ({"bots": THREE_BOTS}, {"bots": BAD_BOTS, "refuses": True}),
}
STATE_NAMES = tuple(STATES)


def state_payload(name: str) -> dict:
    return build(*STATES[name])


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):
    """A QJSEngine holding the module, with a setter and one raised answer."""

    module_path = MODULE_PATH
    setter = SETTER

    def raised(self, script: str) -> str:
        """The engine's error for ``script``, or an empty string."""
        result = self._engine.evaluate(script)
        return result.toString() if result.isError() else ""

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
    payload = state_payload("many")
    payload["only_on_the_surface"] = []
    js.push(payload)
    assert sorted(set(payload) - set(declared_fields(js))) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    payload = state_payload("many")
    assert payload.pop("button_height") is not None
    js.push(payload)
    assert sorted(set(declared_fields(js)) - set(payload)) == ["button_height"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = state_payload("many")
    payload["button_height"] += 1
    js.push(payload)
    original = state_payload("many")
    differing = sorted(
        name for name in original if js.called("field", name) != original[name]
    )
    assert differing == ["button_height"], f"the check named {differing}"


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
    assert report["declared"]["columns"] == payload["column_count"]
    assert report["held"]["columns"] == len(payload["column_labels"])
    assert report["declared"]["drawn"] == payload["built_row_count"]
    assert report["held"]["drawn"] == len([r for r in payload["rows"] if r is not None])
    assert report["declared"]["buttons"] == len(payload["button_columns"])
    assert report["held"]["buttons"] == len(payload["buttons"])


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("many")
    declared = len(payload)
    del payload["button_height"]
    report = js.push(payload)
    assert report["declared"]["fields"] == declared
    assert report["held"]["fields"] == declared - 1


def test_a_dropped_row_shortens_the_held_row_count(js: JsRuntime):
    payload = state_payload("many")
    payload["rows"].pop()
    report = js.push(payload)
    assert report["declared"]["rows"] == len(THREE_BOTS)
    assert report["held"]["rows"] == len(THREE_BOTS) - 1


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
    payload = state_payload("many")
    payload["button_height"] = str(payload["button_height"])
    js.push(payload)
    expected = python_kinds(state_payload("many"))
    actual = js.json(API + "kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["button_height"], f"the check named {differing}"


def test_the_type_check_names_a_scalar_where_a_row_belongs(js: JsRuntime):
    """A scalar where the payload lists a row must not read as that row."""
    payload = state_payload("many")
    payload["rows"][1] = 7
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("rows.1") == "number"
    assert python_kinds(state_payload("many"))["rows.1"] == "object"


def test_the_type_check_names_a_null_where_a_cell_belongs(js: JsRuntime):
    payload = state_payload("many")
    payload["rows"][1]["texts"][0] = None
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("rows.1.texts.0") == "null"
    assert python_kinds(state_payload("many"))["rows.1.texts.0"] == "string"


def test_the_type_walk_reads_a_null_row_the_refusal_left_behind(js: JsRuntime):
    """A refused rewrite leaves a null row, which the walk must not step past."""
    payload = state_payload("refused")
    assert [at for at, row in enumerate(payload["rows"]) if row is None] == [1, 2]
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual["rows.1"] == "null"
    assert actual["rows.2"] == "null"
    assert "rows.1.texts" not in actual


PLAIN_TYPES = (str, int, float, bool, type(None))


def not_plain_data(payload: Any) -> list:
    """Every dotted path in ``payload`` whose value is not plain data."""
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
    """A live object on the payload is a widget the renderer cannot serialise."""
    model = surface.ExtractorBotTableModel()
    for step in STATES[state]:
        if "bots" in step:
            try:
                model.update_bots(step["bots"])
            except ValueError:
                if not step.get("refuses"):
                    raise
        if "detail" in step:
            model._on_detail(step["detail"])
    raw = surface.build_payload(model)
    assert not_plain_data(raw) == [], f"{state} publishes {not_plain_data(raw)}"


def test_the_plain_data_walk_names_a_live_object_put_on_the_payload():
    raw = surface.build_payload(surface.ExtractorBotTableModel())
    raw["rows"] = [{"bot_id": surface.ExtractorBotTableModel()}]
    assert not_plain_data(raw) == ["rows.0.bot_id"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    js.push(state_payload("one"))
    js.run(
        "acervatorSetExtractorTable((function () {"
        "  var p = " + API + "payload();"
        "  p.skin = { drawn: function () { return null; } };"
        "  return p; })());"
    )
    assert js.json(API + "notPlainData()") == [
        {"path": "skin.drawn", "kind": "function"}
    ]


BOT_KEYED = ("bot_id", "bot_ids", "selected_bot_id", "detail_calls")


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_bag_the_surface_publishes_is_keyed_by_a_bot_name(state: str):
    """A bag keyed by a bot is where row order is lost, so no bag may be."""
    payload = state_payload(state)
    names = {one for one in payload["bot_ids"] if one}
    carriers: list = []

    def walk(path: str, value: Any) -> None:
        if isinstance(value, dict):
            if names & set(value):
                carriers.append(path)
            for name, inner in value.items():
                walk(f"{path}.{name}" if path else str(name), inner)
            return
        if isinstance(value, list):
            for at, inner in enumerate(value):
                walk(f"{path}.{at}", inner)

    walk("", payload)
    assert carriers == [], f"{state} keys these bags by a bot name: {carriers}"


def test_the_bot_keyed_bag_check_names_a_bag_that_is_keyed_by_a_bot():
    payload = state_payload("many")
    payload["skin"] = {payload["bot_ids"][0]: "a"}
    names = set(payload["bot_ids"])
    assert names & set(payload["skin"])


@pytest.mark.parametrize("field", sorted(BOT_KEYED))
def test_the_surface_publishes_the_bot_order_as_a_list_or_one_name(field: str):
    payload = state_payload("selected")
    held = payload[field] if field in payload else payload["rows"][0][field]
    assert isinstance(held, (list, str)), f"{field} crosses the bridge as {type(held)}"


COLUMN_KEYED_BAGS = ("buttons", "column_fixed_widths", "column_tooltips")


@pytest.mark.parametrize("field", COLUMN_KEYED_BAGS)
def test_a_column_keyed_bag_loses_the_order_the_surface_wrote(
    js: JsRuntime, field: str
):
    """JavaScript re-sorts an integer-like key, so no bag may carry an order."""
    payload = state_payload("many")
    written = list(reversed(list(payload[field])))
    payload[field] = {name: payload[field][name] for name in written}
    assert list(payload[field]) == written
    js.push(payload)
    read = js.called("bagKeys", field)
    assert read != written, "the bag kept the order the surface wrote"
    assert read == sorted(written, key=int)


@pytest.mark.parametrize("field", COLUMN_KEYED_BAGS)
def test_the_bag_order_check_reads_the_shipped_bag_as_already_sorted(
    js: JsRuntime, field: str
):
    payload = state_payload("many")
    js.push(payload)
    assert js.called("bagKeys", field) == sorted(payload[field], key=int)


def test_the_module_takes_the_column_order_from_a_list_and_not_from_a_bag(
    js: JsRuntime,
):
    payload = state_payload("many")
    payload["buttons"] = {
        name: payload["buttons"][name] for name in reversed(list(payload["buttons"]))
    }
    payload["button_columns"] = list(reversed(payload["button_columns"]))
    js.push(payload)
    assert js.json(API + "buttonColumns()") == payload["button_columns"]
    assert js.json(API + "columns()") == list(range(payload["column_count"]))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_holds_every_row_the_surface_published(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "rows()") == payload["rows"]
    assert js.json(API + "botIds()") == payload["bot_ids"]


def test_the_row_order_reaches_the_module_as_the_surface_wrote_it(js: JsRuntime):
    js.push(state_payload("many"))
    wanted = [one["bot_id"] for one in THREE_BOTS]
    assert js.json(API + "rowBotIds()") == wanted
    assert js.json(API + "botIds()") == wanted


def test_the_row_order_check_names_a_reordered_fleet(js: JsRuntime):
    js.push(build({"bots": SWAPPED_BOTS}))
    held = js.json(API + "rowBotIds()")
    original = [one["bot_id"] for one in THREE_BOTS]
    assert held != original, "the check cannot see a reordered fleet"
    assert [at for at, name in enumerate(original) if held[at] != name] == [1, 2]


def texts_by_bot(js: JsRuntime) -> dict:
    return {one["bot_id"]: one["texts"] for one in js.json(API + "rowTexts()")}


def published_texts_by_bot(payload: dict) -> dict:
    return {row["bot_id"]: row["texts"] for row in payload["rows"] if row}


def test_the_row_identity_check_names_two_bots_whose_values_were_swapped(js: JsRuntime):
    """Two rows keep their position and trade every value, so position cannot report."""
    payload = state_payload("many")
    rows = payload["rows"]
    rows[1], rows[2] = rows[2], rows[1]
    js.push(payload)
    was = published_texts_by_bot(state_payload("many"))
    held = texts_by_bot(js)
    assert sorted(name for name in was if held.get(name) != was[name]) == []
    order = [one["bot_id"] for one in js.json(API + "rowTexts()")]
    assert order == ["ext-a", "ext-c", "ext-b"], f"the check read {order}"


def test_the_row_identity_check_names_a_value_moved_to_another_bot(js: JsRuntime):
    """A figure moved between two rows is named by the bot that now shows it."""
    payload = state_payload("many")
    at = surface.COL_POOL
    rows = payload["rows"]
    rows[1]["texts"][at], rows[2]["texts"][at] = (
        rows[2]["texts"][at],
        rows[1]["texts"][at],
    )
    js.push(payload)
    was = published_texts_by_bot(state_payload("many"))
    held = texts_by_bot(js)
    moved = sorted(name for name, texts in held.items() if texts[at] != was[name][at])
    assert moved == ["ext-b", "ext-c"], f"the check named {moved}"


def test_the_row_identity_check_is_quiet_on_the_shipped_fleet(js: JsRuntime):
    js.push(state_payload("many"))
    was = published_texts_by_bot(state_payload("many"))
    held = texts_by_bot(js)
    assert sorted(name for name in was if held.get(name) != was[name]) == []


def test_the_highlight_follows_the_bot_and_not_the_row_number(js: JsRuntime):
    """The selected row moves with its bot when the fleet is reordered."""
    picked = build({"bots": THREE_BOTS}, {"detail": "ext-b"})
    assert picked["selected_row"] == 1
    js.push(picked)
    assert js.json(API + "selectedRowBotId()") == "ext-b"
    moved = build({"bots": THREE_BOTS}, {"detail": "ext-b"}, {"bots": SWAPPED_BOTS})
    assert moved["selected_row"] == 2, "the highlight stayed on the row number"
    js.push(moved)
    assert js.json(API + "selectedRowBotId()") == "ext-b"
    assert js.json(API + "selectedBotId()") == "ext-b"


def test_the_highlight_check_reads_a_bot_that_left_the_fleet_as_cleared(js: JsRuntime):
    gone = build({"bots": THREE_BOTS}, {"detail": "ext-b"}, {"bots": ONE_BOT})
    js.push(gone)
    assert gone["select_path"] == surface.SELECT_PATH_CLEARED
    assert js.json(API + "selectedBotId()") == surface.NO_BOT
    assert js.json(API + "selectedRowBotId()") is None


def surface_values() -> set:
    """Every colour, figure, word and label the table paints."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        found |= set(payload["column_labels"])
        found |= {str(one) for one in payload["column_fixed_widths"].values()}
        found |= {str(payload[one]) for one in ("button_height", "alignment_value")}
        found |= set(payload["state_colors"].values())
        found |= set(payload["pool_colors"].values())
        found |= {
            payload[one]
            for one in (
                "state_fallback_color",
                "pool_fallback_color",
                "unset_color",
                "fire_label",
                "detail_label",
                "mode_text",
                "no_value_text",
                "unknown_state_text",
            )
        }
        for row in payload["rows"]:
            if row is None:
                continue
            found |= {str(one) for one in row["texts"]}
            found |= set(row["colors"])
            found |= set(row["tooltips"])
    found.discard("")
    return found


def token_values() -> set:
    found = {str(value) for value in token_payload()["tokens"].values()}
    found.discard("")
    return found


def published_strings() -> set:
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                found.add(str(key))
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


SURFACE_VALUES = surface_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every published string the module writes as a literal, each one a name.
NAMED_WORDS = sorted(
    set(surface.build_payload(surface.ExtractorBotTableModel()))
    | set(surface.row_values(status("ext-a")))
    | set(surface.buttons()["6"])
    | {surface.METHOD, "detail.clicked"}
)


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a value the surface owns."""
    assert not MODULE_LITERALS["numbers"], (
        "extractor_bot_table.js holds numeric literals: "
        f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"extractor_bot_table.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_table_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & SURFACE_VALUES)
    assert not written, f"extractor_bot_table.js spells out table values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"extractor_bot_table.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert set(written) <= set(NAMED_WORDS), (
        "the module names published strings the list does not allow: "
        f"{sorted(set(written) - set(NAMED_WORDS))}"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_table_shows():
    overlap = sorted(set(NAMED_WORDS) & SURFACE_VALUES)
    assert not overlap, f"these named words are values the table paints: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "extractor_bot_table.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES = {
    "colour": 'var written = "#00ffcc";',
    "state_colour": 'var written = "' + surface.STATE_COLORS["running"] + '";',
    "pool_colour": 'var written = "' + surface.POOL_COLORS["red"] + '";',
    "header": 'var written = "' + surface.COLUMN_LABELS[0] + '";',
    "fire_label": 'var written = "' + surface.FIRE_LABEL + '";',
    "mode_word": 'var written = "' + surface.MODE_TEXT + '";',
    "no_value": 'var written = "' + surface.NO_VALUE_TEXT + '";',
    "button_height": "var written = " + str(surface.BUTTON_HEIGHT) + ";",
    "alignment": "var written = " + str(surface.ALIGNMENT_VALUE) + ";",
    "fire_width": "var written = " + str(surface.COLUMN_FIXED_WIDTHS[6]) + ";",
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
    if strings & SURFACE_VALUES:
        caught.add("surface_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_line(kind: str):
    assert caught_by_scan(WRITTEN_LINES[kind]), f"the scan reported nothing on {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
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


def as_javascript(value: Any) -> Any:
    if type(value) is int and abs(value) > BIGGEST_EXACT_INTEGER:
        return float(value)
    return json.loads(json.dumps(value))


HOSTILE_FIELDS = {
    "row_count is text": ("row_count", "3"),
    "row_count disagrees": ("row_count", 99),
    "column_count is text": ("column_count", "8"),
    "button_height is text": ("button_height", "22"),
    "bot_ids is a bag": ("bot_ids", {}),
    "column_labels is text": ("column_labels", "Bot ID"),
    "column_labels is null": ("column_labels", None),
    "rows is text": ("rows", "not rows"),
    "buttons is a list": ("buttons", []),
    "state_colors is a list": ("state_colors", []),
    "selected_row is huge": ("selected_row", 10**24),
    "selected_row is past the last row": ("selected_row", 99),
    "current_row is past the last row": ("current_row", 99),
    "selected_bot_id is a number": ("selected_bot_id", 7),
    "table_style_sheet is a number": ("table_style_sheet", 7),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_FIELDS))
def test_a_hostile_field_leaves_the_module_loaded_and_answering(
    js: JsRuntime, case: str
):
    """A module that threw here would answer nothing for any field the payload holds."""
    field, value = HOSTILE_FIELDS[case]
    payload = state_payload("many")
    payload[field] = value
    js.push(payload)
    assert js.json(API + "isLoaded()") is True
    assert js.called("field", field) == as_javascript(value)


CELL_KEY_OF = {
    "texts": "text",
    "types": "type",
    "colors": "color",
    "brushes": "brush",
    "tooltips": "tooltip",
    "icons": "icon",
    "alignments": "alignment",
}

HOSTILE_CELLS = {
    "text is a number": ("texts", 1234.5),
    "text is a flag": ("texts", True),
    "text is empty": ("texts", ""),
    "text is 200 characters": ("texts", LONG_NAME),
    "text holds markup": ("texts", MARKUP_NAME),
    "text holds a newline": ("texts", "first\nsecond"),
    "text is null": ("texts", None),
    "colour is a number": ("colors", 7),
    "colour carries an alpha": ("colors", "#11223344"),
    "brush is unknown": ("brushes", "NoSuchBrush"),
    "type is text": ("types", "0"),
    "type is huge": ("types", 10**24),
    "tooltip is a number": ("tooltips", 7),
    "icon is text": ("icons", "yes"),
    "alignment is text": ("alignments", "132"),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_CELLS))
def test_a_hostile_cell_reaches_the_module_unchanged(js: JsRuntime, case: str):
    """The module carries the exact value the surface produced, repairing nothing."""
    field, value = HOSTILE_CELLS[case]
    payload = state_payload("one")
    payload["rows"][0][field][surface.COL_BOT_ID] = value
    js.push(payload)
    held = js.json(API + "cellAt(0, " + str(surface.COL_BOT_ID) + ")")
    assert held[CELL_KEY_OF[field]] == as_javascript(value)


def test_the_hostile_cell_check_reads_a_value_the_module_would_have_changed():
    assert as_javascript(10**24) != 10**24
    assert as_javascript("132") == "132"
    assert as_javascript(True) is True


def test_a_colour_carrying_an_alpha_is_refused_and_named(js: JsRuntime):
    """Qt reads eight hex digits as alpha first and CSS reads it last."""
    payload = state_payload("one")
    payload["state_colors"]["running"] = "#11223344"
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert named == [
        {
            "where": "state_colors",
            "field": "running",
            "fault": "swapped-alpha",
            "detail": "#11223344",
        }
    ], f"the check named {named}"


def test_the_alpha_check_is_quiet_on_every_colour_the_surface_publishes(js: JsRuntime):
    for name in STATE_NAMES:
        report = js.push(state_payload(name))
        named = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
        assert named == [], f"{name}: the shipped payload names {named}"


def test_the_surface_publishes_no_colour_carrying_an_alpha(js: JsRuntime):
    """No published colour carries alpha, so none is ever scaled to a fraction."""
    js.push(state_payload("many"))
    for value in SURFACE_VALUES:
        if value.startswith("#"):
            assert js.called("isSwappedAlpha", value) is False, value
    assert js.called("isSwappedAlpha", "#11223344") is True


NOT_A_NUMBER = {
    "not a number": float("nan"),
    "an infinity": float("inf"),
    "a negative infinity": float("-inf"),
}


@pytest.mark.parametrize("case", sorted(NOT_A_NUMBER))
def test_a_not_a_number_never_reaches_the_module_at_all(js: JsRuntime, case: str):
    """JSON.parse refuses NaN, so the frame is dropped before the module sees it."""
    payload = state_payload("one")
    payload["rows"][0]["free_usd"] = NOT_A_NUMBER[case]
    js.bind_json("PAYLOAD", payload)
    raised = js.raised(SETTER + "(JSON.parse(PAYLOAD))")
    assert raised, f"{case} parsed where the real page drops the frame"
    assert "JSON" in raised or "SyntaxError" in raised, raised


def test_a_real_number_in_the_same_field_parses(js: JsRuntime):
    payload = state_payload("one")
    payload["rows"][0]["free_usd"] = 1.5
    js.bind_json("PAYLOAD", payload)
    assert js.raised(SETTER + "(JSON.parse(PAYLOAD))") == ""
    assert js.json(API + "row(0)")["free_usd"] == 1.5


def test_a_very_large_figure_loses_precision_crossing_the_bridge(js: JsRuntime):
    payload = state_payload("one")
    payload["rows"][0]["free_usd"] = 10**24
    js.push(payload)
    held = js.json(API + "row(0)")["free_usd"]
    assert held == float(10**24)
    assert held != 10**24, "the bridge kept every digit"


def test_a_selection_past_the_last_row_is_named_and_draws_no_row(js: JsRuntime):
    payload = state_payload("many")
    payload["selected_row"] = 99
    payload["current_row"] = 99
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "disagrees"]
    assert {
        "where": None,
        "field": "selected_row",
        "fault": "disagrees",
        "detail": len(payload["rows"]),
    } in named, f"the check named {named}"
    assert js.json(API + "selectedRowBotId()") is None


def test_the_selection_check_is_quiet_on_a_selection_inside_the_fleet(js: JsRuntime):
    report = js.push(state_payload("selected"))
    named = [one for one in report["faults"] if one["field"] == "selected_row"]
    assert named == [], f"the shipped payload names {named}"


def test_a_negative_pool_draws_the_dashes_a_table_with_no_pool_shows():
    """Reported and not repaired: a negative pool reads exactly like no pool."""
    payload = build({"bots": NEGATIVE_BOTS})
    row = payload["rows"][0]
    assert row["texts"][surface.COL_POOL] == surface.NO_VALUE_TEXT
    assert row["texts"][surface.COL_LIQUID] == surface.NO_VALUE_TEXT
    assert row["chunk_size_usd"] < 0
    assert row["free_usd"] > 0, "the negative pool priced its free base as a gain"


def test_a_negative_pool_still_draws_every_cell(js: JsRuntime):
    js.push(build({"bots": NEGATIVE_BOTS}))
    assert js.json(API + "isLoaded()") is True
    assert len(js.json(API + "rowTexts()")[0]["texts"]) == surface.COLUMN_COUNT


def test_a_two_hundred_character_bot_name_reaches_the_cell_whole(js: JsRuntime):
    js.push(build({"bots": [status(LONG_NAME)]}))
    held = js.json(API + "cellAt(0, " + str(surface.COL_BOT_ID) + ")")
    assert held["text"] == LONG_NAME


def test_two_bots_sharing_one_name_each_keep_their_own_row(js: JsRuntime):
    twins = [status("ext-a", base="BTC"), status("ext-a", base="ETH")]
    payload = build({"bots": twins})
    js.push(payload)
    assert js.json(API + "rowBotIds()") == ["ext-a", "ext-a"]
    shown = [one["texts"][surface.COL_SYMBOL] for one in js.json(API + "rowTexts()")]
    assert shown == ["BTC", "ETH"]


def test_a_duplicate_bot_name_puts_the_highlight_on_the_first_row_that_matches():
    """Reported and not repaired: the row lookup answers the first bot of that name."""
    twins = [status("ext-a", base="BTC"), status("ext-a", base="ETH")]
    payload = build({"bots": twins}, {"detail": "ext-a"})
    assert payload["selected_row"] == 0
    assert payload["detail_path"] == surface.DETAIL_PATH_SELECTED


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json(API + "isLoaded()") is False
        assert js.json(API + "rows()") == []
        assert report["declared"] is None
        assert [one["fault"] for one in report["faults"]] == ["not-an-object"]


def test_a_row_that_is_not_an_object_is_named(js: JsRuntime):
    payload = state_payload("many")
    payload["rows"][1] = "not a row"
    report = js.push(payload)
    assert {
        "where": "row:1",
        "field": None,
        "fault": "not-an-object",
        "detail": "string",
    } in report["faults"]


def test_a_short_row_list_is_named(js: JsRuntime):
    payload = state_payload("many")
    payload["rows"][0]["texts"].pop()
    report = js.push(payload)
    assert {
        "where": "row:0",
        "field": "texts",
        "fault": "short-list",
        "detail": surface.COLUMN_COUNT - 1,
    } in report["faults"]


PUBLISHED_FIELDS = sorted(state_payload("many"))


@pytest.mark.parametrize("field", PUBLISHED_FIELDS)
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
    assert js.json(API + "isLoaded()") is True


@pytest.mark.parametrize("field", PUBLISHED_FIELDS)
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
    assert js.json(API + "isLoaded()") is True


#: A refusal drops the bot it stopped on, so FAULTS_OF names one fault.
FAULTS_OF = {
    "empty": [],
    "one": [],
    "many": [],
    "selected": [],
    "refused": ["disagrees"],
    "stale": ["disagrees", "mismatch"],
}


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_shipped_payload_names_only_the_faults_the_refusal_leaves(
    js: JsRuntime, state: str
):
    report = js.push(state_payload(state))
    named = sorted({one["fault"] for one in report["faults"]})
    assert named == FAULTS_OF[state], f"{state} names {report['faults']}"


def test_the_refused_rewrite_leaves_the_earlier_paint_and_a_short_bot_list():
    """Reported and not repaired: a refusal keeps the old row and drops its bot."""
    payload = state_payload("stale")
    assert payload["row_count"] == len(BAD_BOTS)
    assert payload["bot_ids"] == ["ext-a", "ext-b"]
    assert payload["rows"][2]["bot_id"] == "ext-c"
    assert payload["built_row_count"] == len(BAD_BOTS)


def test_the_button_check_names_a_button_the_row_changed(js: JsRuntime):
    payload = state_payload("many")
    payload["rows"][0]["buttons"]["6"]["enabled"] = True
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "mismatch"]
    assert {
        "where": "row:0-button:6",
        "field": "enabled",
        "fault": "mismatch",
        "detail": {"declared": False, "held": True},
    } in named, f"the check named {named}"


def test_the_button_check_is_quiet_on_every_shipped_row(js: JsRuntime):
    for name in STATE_NAMES:
        report = js.push(state_payload(name))
        named = [one for one in report["faults"] if "button" in str(one["where"])]
        assert named == [], f"{name}: the shipped payload names {named}"


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    js.bind_json("SERVED", state_payload("one"))
    js.run(
        "window.ASKED = [];"
        "window.acervator = { call: function (m, p) {"
        "  window.ASKED.push([m, p]);"
        "  return Promise.resolve(JSON.parse(SERVED)); } };"
    )
    js.run("acervatorLoadExtractorTable({ reset: true });")
    drain_events()
    assert js.json("window.ASKED") == [[surface.METHOD, {"reset": True}]]
    assert js.json(API + "isLoaded()") is True


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("SERVED", state_payload("one"))
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  return Promise.resolve(JSON.parse(SERVED)); } };"
    )
    js.run("acervatorLoadExtractorTable(); acervatorLoadExtractorTable();")
    drain_events()
    assert js.json("window.TRIES") == 1


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadExtractorTable();")
    drain_events()
    assert js.json(API + "loadError()") == "the preload bridge is not present"
    assert js.json(API + "isLoaded()") is False


def test_a_refused_first_ask_is_not_remembered(js: JsRuntime):
    js.bind_json("SERVED", state_payload("one"))
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) { return Promise.reject(new Error('no')); }"
        "  return Promise.resolve(JSON.parse(SERVED)); } };"
    )
    js.run("acervatorLoadExtractorTable();")
    drain_events()
    assert js.json(API + "isLoaded()") is False
    js.run("acervatorLoadExtractorTable();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json(API + "isLoaded()") is True


def test_the_bridge_handler_serves_the_same_fields_as_the_module_names(js: JsRuntime):
    """view_model keeps one table per process, so it is left reset."""
    try:
        served = json.loads(
            json.dumps(
                surface.view_model(
                    {"reset": True, "action": "update_bots", "bot_statuses": ONE_BOT}
                ),
                ensure_ascii=True,
            )
        )
        js.push(served)
        assert sorted(served) == sorted(declared_fields(js))
        assert js.json(API + "isLoaded()") is True
    finally:
        surface.view_model({"reset": True})


def picture_of(widget) -> Any:
    """One render of ``widget`` at PICTURE_SIZE, as a QImage."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImage

    widget.resize(*PICTURE_SIZE)
    image = QImage(QSize(*PICTURE_SIZE), QImage.Format.Format_ARGB32)
    image.fill(0)
    widget.render(image)
    return image


def picture_digest(widget) -> str:
    return hashlib.sha256(bytes(picture_of(widget).constBits())).hexdigest()


def a_label(text: str) -> Any:
    from PySide6.QtWidgets import QLabel

    return QLabel(text)


def a_button(text: str) -> Any:
    from PySide6.QtWidgets import QPushButton

    return QPushButton(text)


def a_cell(text: str) -> Any:
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    table = QTableWidget(1, 1)
    table.setItem(0, 0, QTableWidgetItem(text))
    table.horizontalHeader().hide()
    table.verticalHeader().hide()
    return table


def a_header(text: str) -> Any:
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    table = QTableWidget(1, 1)
    table.setHorizontalHeaderItem(0, QTableWidgetItem(text))
    table.verticalHeader().hide()
    return table


SCREEN_WIDGETS = {
    "QTableWidgetItem": a_cell,
    "QPushButton": a_button,
    "QHeaderView": a_header,
}


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_no_widget_this_screen_uses_reads_its_caller_text_as_markup(qapp, kind: str):
    """An empty tag pair the widget paints proves the text stayed characters."""
    assert qapp is not None
    make = SCREEN_WIDGETS[kind]
    assert picture_digest(make(MARKUP_PROBE)) != picture_digest(
        make(PLAIN_PROBE)
    ), f"{kind} painted one picture for both, so it swallowed the tags"


def test_the_markup_measurement_reads_a_label_as_a_widget_that_does(qapp):
    """QLabel swallows the tag pair, so the measurement can report a markup widget."""
    assert qapp is not None
    assert picture_digest(a_label(MARKUP_PROBE)) == picture_digest(a_label(PLAIN_PROBE))


def test_the_markup_measurement_refuses_a_render_that_paints_one_colour(qapp):
    from tests.fixtures.surface_pictures import colour_count

    assert qapp is not None
    assert colour_count(picture_of(a_cell(PLAIN_PROBE))) > 1


def test_the_published_column_widths_clear_the_least_a_column_can_be(qapp):
    """A width under the host's minimum is not the width the screen shows."""
    from PySide6.QtWidgets import QTableWidget

    assert qapp is not None
    table = QTableWidget(1, 1)
    least = table.horizontalHeader().minimumSectionSize()
    published = state_payload("many")["column_fixed_widths"]
    short = {name: width for name, width in published.items() if width < least}
    assert not short, f"these widths draw at {least} instead: {short}"


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
            "the page never defined the extractor table module in "
            + str(PAGE_ATTEMPTS)
            + " loads: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
        )

    def open_page(self) -> None:
        """Loads the renderer page and waits until its load finishes."""
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
        """Whether the page defined the module setter inside its own budget."""
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
    "width",
    "height",
    "whiteSpace",
    "textOverflow",
    "overflow",
    "textAlign",
    "tableLayout",
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
    "window.probeTag = function (tag, cssText, names) {"
    "  var probe = document.createElement(tag);"
    "  probe.style.cssText = cssText;"
    "  document.body.appendChild(probe);"
    "  var found = window.readStyle(probe, names);"
    "  probe.remove();"
    "  return found; };"
    "window.probeStyle = function (cssText, names) {"
    "  return window.probeTag('div', cssText, names); };"
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

COUNT_ELEMENTS = (
    "[window.HOST.querySelectorAll('*').length,"
    " window.HOST.querySelectorAll('[data-part]').length]"
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


def draw_table(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        SETTER + "(JSON.parse(window.PAYLOAD));" + API + "renderTable(window.HOST);"
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
    return probe_tag(browser, "div", css, names)


def probe_tag(browser: Browser, tag: str, css: str, names: list) -> dict:
    """The style a bare ``tag`` computes from one whole CSS declaration."""
    return browser.parsed(
        "window.probeTag("
        + json.dumps(tag)
        + ", "
        + json.dumps(css)
        + ", "
        + json.dumps(names)
        + ")"
    )


def cell_at(parts: list, row: int, column: int) -> dict:
    return at_path(parts, CELL_PATH)[row * surface.COLUMN_COUNT + column]


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window." + API[:-1]) == "object"
    assert browser.js("typeof window.acervatorLoadExtractorTable") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_table(browser, state_payload("many"))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_drawn_table_names_every_child_a_check_reads(browser: Browser):
    payload = state_payload("selected")
    parts = draw_table(browser, payload)
    paths = sorted({one["path"] for one in parts})
    assert paths == [
        "table",
        "table/body",
        "table/body/row",
        "table/body/row/cell",
        "table/body/row/cell/detail-button",
        "table/body/row/cell/fire-button",
        "table/head",
        "table/head/head-row",
        "table/head/head-row/header",
    ], f"the table drew {paths}"
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no name"


def test_the_child_name_check_reads_an_unnamed_child_as_unnamed(browser: Browser):
    draw_table(browser, state_payload("one"))
    browser.js("window.HOST.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


def test_the_drawn_table_carries_the_numbers_the_space_it_fills_declares(
    browser: Browser,
):
    """The exchange screen names these six on the space, so the table answers them."""
    payload = state_payload("selected")
    parts = draw_table(browser, payload)
    table = only(parts, "table")
    assert table["attrs"]["data-kind"] == payload["table_kind"]
    assert table["attrs"]["data-rows"] == str(payload["row_count"])
    assert table["attrs"]["data-drawn"] == str(payload["built_row_count"])
    assert table["attrs"]["data-held"] == str(len(payload["bot_ids"]))
    assert table["attrs"]["data-selected"] == payload["selected_bot_id"]
    assert table["attrs"]["data-index"] == str(payload["current_row"])
    assert table["attrs"]["data-columns"] == str(payload["column_count"])


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_drawn_table_shows_every_row_in_the_order_the_surface_published(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_table(browser, payload)
    drawn = at_path(parts, ROW_PATH)
    assert len(drawn) == len(payload["rows"])
    assert [one["attrs"]["data-row"] for one in drawn] == [
        str(at) for at in range(len(payload["rows"]))
    ]
    assert [one["attrs"].get("data-bot-id") for one in drawn] == [
        None if row is None else row["bot_id"] for row in payload["rows"]
    ]


def test_the_drawn_row_order_check_names_a_reordered_fleet(browser: Browser):
    parts = draw_table(browser, build({"bots": SWAPPED_BOTS}))
    drawn = [one["attrs"]["data-bot-id"] for one in at_path(parts, ROW_PATH)]
    original = [one["bot_id"] for one in THREE_BOTS]
    assert drawn != original, "the check cannot see a reordered fleet"
    assert drawn == ["ext-a", "ext-c", "ext-b"]


def test_the_drawn_row_identity_check_names_two_bots_that_traded_values(
    browser: Browser,
):
    """Two rows keep their position and trade every value, so position cannot report."""
    payload = state_payload("many")
    payload["rows"][1], payload["rows"][2] = payload["rows"][2], payload["rows"][1]
    parts = draw_table(browser, payload)
    was = published_texts_by_bot(state_payload("many"))
    drawn = {
        one["attrs"]["data-bot-id"]: [
            cell_at(parts, at, column)["text"]
            for column in range(surface.COLUMN_COUNT)
            if column not in payload["button_columns"]
        ]
        for at, one in enumerate(at_path(parts, ROW_PATH))
    }
    for name, texts in drawn.items():
        wanted = [
            was[name][column]
            for column in range(surface.COLUMN_COUNT)
            if column not in payload["button_columns"]
        ]
        assert texts == wanted, f"{name} drew {texts}"
    order = [one["attrs"]["data-bot-id"] for one in at_path(parts, ROW_PATH)]
    assert order == ["ext-a", "ext-c", "ext-b"], f"the check read {order}"


def test_the_drawn_row_identity_check_names_a_value_moved_to_another_bot(
    browser: Browser,
):
    payload = state_payload("many")
    at = surface.COL_POOL
    rows = payload["rows"]
    rows[1]["texts"][at], rows[2]["texts"][at] = (
        rows[2]["texts"][at],
        rows[1]["texts"][at],
    )
    parts = draw_table(browser, payload)
    was = published_texts_by_bot(state_payload("many"))
    moved = sorted(
        one["attrs"]["data-bot-id"]
        for row, one in enumerate(at_path(parts, ROW_PATH))
        if cell_at(parts, row, at)["text"] != was[one["attrs"]["data-bot-id"]][at]
    )
    assert moved == ["ext-b", "ext-c"], f"the check named {moved}"


def test_the_drawn_highlight_sits_on_the_bot_and_not_on_the_row_number(
    browser: Browser,
):
    payload = build({"bots": THREE_BOTS}, {"detail": "ext-b"}, {"bots": SWAPPED_BOTS})
    parts = draw_table(browser, payload)
    picked = [
        one["attrs"]["data-bot-id"]
        for one in at_path(parts, ROW_PATH)
        if one["attrs"]["data-selected"] == "true"
    ]
    assert picked == ["ext-b"], f"the highlight drew on {picked}"
    assert only(parts, "table")["attrs"]["data-selected"] == "ext-b"


def test_the_drawn_highlight_check_reads_a_table_with_no_selection_as_none(
    browser: Browser,
):
    parts = draw_table(browser, state_payload("many"))
    picked = [
        one["attrs"]["data-bot-id"]
        for one in at_path(parts, ROW_PATH)
        if one["attrs"]["data-selected"] == "true"
    ]
    assert picked == []


def test_a_selection_past_the_last_row_draws_no_highlight(browser: Browser):
    payload = state_payload("many")
    payload["selected_row"] = 99
    parts = draw_table(browser, payload)
    assert all(
        one["attrs"]["data-selected"] == "false" for one in at_path(parts, ROW_PATH)
    )
    assert len(at_path(parts, ROW_PATH)) == len(payload["rows"])


@pytest.mark.parametrize("state", ["one", "many", "selected"])
def test_each_painted_cell_takes_the_colour_the_surface_published(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_table(browser, payload)
    for at, row in enumerate(payload["rows"]):
        for column in payload["coloured_columns"]:
            wanted = probe_style(browser, "color: " + row["colors"][column], ["color"])[
                "color"
            ]
            drawn = cell_at(parts, at, column)["style"]["color"]
            assert drawn == wanted, f"row {at} column {column} drew {drawn}"


def test_the_colour_check_names_one_changed_colour(browser: Browser):
    payload = state_payload("many")
    column = surface.COL_MODE
    payload["rows"][0]["colors"][column] = payload["pool_colors"]["red"]
    parts = draw_table(browser, payload)
    original = state_payload("many")
    wanted = probe_style(
        browser, "color: " + original["rows"][0]["colors"][column], ["color"]
    )["color"]
    assert cell_at(parts, 0, column)["style"]["color"] != wanted


def test_an_unpainted_cell_takes_the_colour_it_inherits_and_none_of_its_own(
    browser: Browser,
):
    payload = state_payload("many")
    parts = draw_table(browser, payload)
    inherited = only(parts, "table")["style"]["color"]
    painted = cell_at(parts, 0, surface.COL_MODE)["style"]["color"]
    assert painted != inherited, "the painted cell paints what it inherits"
    for column in range(surface.COLUMN_COUNT):
        if column in payload["coloured_columns"]:
            continue
        assert cell_at(parts, 0, column)["style"]["color"] == inherited


def carriers_of(value: str) -> list:
    """Every design token name whose value is exactly ``value``."""
    served = token_payload()
    aliased = set(served.get("alias_targets") or {})
    return sorted(
        name
        for name, held in served["tokens"].items()
        if name not in aliased and str(held) == value
    )


COLOUR_CARRIERS = {
    "running": "SUCCESS",
    "paused": "WARNING",
    "error": "ERROR",
    "cooldown": "WARNING_STRONG",
    "stopped": "TEXT_MUTED",
    "starting": "STATE_STARTING",
}


@pytest.mark.parametrize("state", sorted(COLOUR_CARRIERS))
def test_each_state_colour_resolves_to_the_token_of_its_own_name(state: str):
    value = state_payload("many")["state_colors"][state]
    assert carriers_of(value) == [COLOUR_CARRIERS[state]], f"{state} is {value}"


def test_the_idle_state_colour_resolves_to_no_token_at_all():
    """CARD_METRIC_LABEL is written three digits wide and the cell is written six."""
    value = state_payload("many")["state_colors"]["idle"]
    assert carriers_of(value) == []
    assert carriers_of(dss.CARD_METRIC_LABEL) == ["CARD_METRIC_LABEL"]
    assert surface.long_hex(dss.CARD_METRIC_LABEL) == value != dss.CARD_METRIC_LABEL


def test_the_carrier_check_reads_a_colour_no_token_holds_as_unresolved():
    assert carriers_of("#123457") == []


def rewrite_token(browser: Browser, name: str, value: Any) -> None:
    browser.js(
        "(function () {"
        "  var served = JSON.parse(window.TOKENS);"
        "  served.tokens[" + json.dumps(name) + "] = " + json.dumps(value) + ";"
        "  window.TOKENS = JSON.stringify(served);"
        "  acervatorSetTokens(served);"
        "  acervatorTokens.apply(document.documentElement); })()"
    )


def changed_paths(before: list, after: list) -> set:
    return {
        one["path"]
        for at, one in enumerate(after)
        if one["style"] != before[at]["style"]
    }


def test_the_drawn_table_follows_the_state_colour_token(browser: Browser):
    before = draw_table(browser, state_payload("many"))
    rewrite_token(browser, "SUCCESS", dss.PRIMARY)
    assert changed_paths(before, read_parts(browser)) == {CELL_PATH}


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(browser: Browser):
    before = draw_table(browser, state_payload("many"))
    assert changed_paths(before, read_parts(browser)) == set()


def test_the_idle_cell_follows_no_token_because_its_colour_carries_no_name(
    browser: Browser,
):
    before = draw_table(browser, build({"bots": [THREE_BOTS[2]]}))
    rewrite_token(browser, "CARD_METRIC_LABEL", dss.PRIMARY)
    assert changed_paths(before, read_parts(browser)) == set()


def test_each_fixed_column_takes_the_width_the_surface_published(browser: Browser):
    payload = state_payload("many")
    parts = draw_table(browser, payload)
    for name, width in payload["column_fixed_widths"].items():
        wanted = probe_style(browser, "width: " + str(width) + "px", ["width"])["width"]
        drawn = at_path(parts, HEADER_PATH)[int(name)]["style"]["width"]
        assert drawn == wanted, f"column {name} drew {drawn}"


def test_the_width_check_names_one_changed_width(browser: Browser):
    payload = state_payload("many")
    name = str(surface.COL_FIRE)
    payload["column_fixed_widths"][name] = payload["column_fixed_widths"][name] + 40
    parts = draw_table(browser, payload)
    original = state_payload("many")["column_fixed_widths"][name]
    wanted = probe_style(browser, "width: " + str(original) + "px", ["width"])["width"]
    assert at_path(parts, HEADER_PATH)[int(name)]["style"]["width"] != wanted


def test_the_table_lays_its_columns_out_fixed_so_a_long_name_cannot_widen_it(
    browser: Browser,
):
    """A CSS table grows to fit unless the layout is fixed, and Qt clips."""
    short = draw_table(browser, state_payload("one"))
    long_name = draw_table(browser, build({"bots": [status(LONG_NAME)]}))
    assert only(short, "table")["style"]["tableLayout"] == "fixed"
    assert (
        only(long_name, "table")["clientWidth"] == only(short, "table")["clientWidth"]
    )
    cell = cell_at(long_name, 0, surface.COL_BOT_ID)
    assert cell["scrollWidth"] > cell["clientWidth"], "the long name did not clip"
    assert cell["whole"] == LONG_NAME, "the long name was trimmed"


def test_the_clipping_check_reads_a_short_name_as_fitting(browser: Browser):
    parts = draw_table(browser, state_payload("one"))
    cell = cell_at(parts, 0, surface.COL_BOT_ID)
    assert cell["scrollWidth"] <= cell["clientWidth"]


def test_every_cell_is_aligned_the_way_the_surface_named(browser: Browser):
    payload = state_payload("many")
    parts = draw_table(browser, payload)
    wanted = probe_style(browser, "text-align: center", ["textAlign"])["textAlign"]
    for column in range(surface.COLUMN_COUNT):
        cell = cell_at(parts, 0, column)
        assert cell["style"]["textAlign"] == wanted
        assert cell["attrs"]["data-alignment"] == payload["alignment"]
        assert cell["attrs"]["data-alignment-value"] == str(payload["alignment_value"])


def test_the_alignment_check_reads_an_unknown_word_as_no_alignment(browser: Browser):
    payload = state_payload("many")
    payload["alignment"] = "AlignNowhere"
    parts = draw_table(browser, payload)
    wanted = probe_style(browser, "text-align: center", ["textAlign"])["textAlign"]
    assert cell_at(parts, 0, 0)["style"]["textAlign"] != wanted


def test_each_row_draws_the_two_buttons_the_surface_published(browser: Browser):
    payload = state_payload("many")
    parts = draw_table(browser, payload)
    fire = at_path(parts, "table/body/row/cell/fire-button")
    detail = at_path(parts, "table/body/row/cell/detail-button")
    assert len(fire) == len(payload["rows"])
    assert len(detail) == len(payload["rows"])
    assert [one["text"] for one in fire] == [payload["fire_label"]] * len(fire)
    assert [one["text"] for one in detail] == [payload["detail_label"]] * len(detail)
    assert [one["attrs"]["data-bot-id"] for one in detail] == payload["bot_ids"]
    assert [one["attrs"].get("data-action") for one in detail] == [
        payload["actions"]["detail.clicked"]
    ] * len(detail)


def test_the_fire_button_is_drawn_disabled_and_out_of_the_tab_order(browser: Browser):
    payload = state_payload("one")
    parts = draw_table(browser, payload)
    fire = only(parts, "table/body/row/cell/fire-button")
    detail = only(parts, "table/body/row/cell/detail-button")
    assert "disabled" in fire["attrs"]
    assert fire["attrs"]["tabindex"] == "-1"
    assert "disabled" not in detail["attrs"]
    assert "tabindex" not in detail["attrs"]
    assert fire["attrs"]["data-focus-policy"] == payload["fire_focus_policy"]


def test_each_button_takes_the_height_its_style_sheet_and_the_surface_named(
    browser: Browser,
):
    payload = state_payload("one")
    parts = draw_table(browser, payload)
    fire = only(parts, "table/body/row/cell/fire-button")
    whole = payload["fire_style_sheet"] + " height: " + str(payload["button_height"])
    wanted = probe_tag(browser, "button", whole + "px", ["height", "color"])
    assert fire["style"]["height"] == wanted["height"]
    assert fire["style"]["color"] == wanted["color"]


def test_the_button_style_check_names_one_changed_declaration(browser: Browser):
    payload = state_payload("one")
    payload["rows"][0]["buttons"]["6"]["height"] = payload["button_height"] + 20
    parts = draw_table(browser, payload)
    whole = "height: " + str(state_payload("one")["button_height"]) + "px"
    wanted = probe_tag(browser, "button", whole, ["height"])["height"]
    assert only(parts, "table/body/row/cell/fire-button")["style"]["height"] != wanted


def test_an_empty_fleet_draws_a_head_and_no_row(browser: Browser):
    payload = state_payload("empty")
    parts = draw_table(browser, payload)
    assert at_path(parts, ROW_PATH) == []
    assert len(at_path(parts, HEADER_PATH)) == len(payload["column_labels"])
    assert only(parts, "table")["attrs"]["data-rows"] == "0"


def test_each_header_shows_the_label_and_the_tooltip_the_surface_published(
    browser: Browser,
):
    payload = state_payload("many")
    parts = draw_table(browser, payload)
    drawn = at_path(parts, HEADER_PATH)
    assert [one["text"] for one in drawn] == payload["column_labels"]
    assert [one["attrs"].get("title") for one in drawn] == [
        payload["column_tooltips"][str(at)] or None
        for at in range(surface.COLUMN_COUNT)
    ]


def test_a_refused_row_draws_its_cells_empty_and_names_itself(browser: Browser):
    payload = state_payload("refused")
    parts = draw_table(browser, payload)
    built = [one["attrs"]["data-built"] for one in at_path(parts, ROW_PATH)]
    assert built == ["true", "false", "false"]
    assert cell_at(parts, 1, surface.COL_BOT_ID)["text"] == ""
    assert cell_at(parts, 0, surface.COL_BOT_ID)["text"] == "ext-a"


def test_a_markup_bot_name_draws_as_text_and_loads_nothing(browser: Browser):
    """A bot name holding an image tag reaches the page as characters."""
    browser.js(WATCH_VIOLATIONS)
    before = browser.js("document.images.length")
    parts = draw_table(browser, build({"bots": [status(MARKUP_NAME)]}))
    browser.settle(SETTLE_MS)
    assert cell_at(parts, 0, surface.COL_BOT_ID)["text"] == MARKUP_NAME
    assert browser.js("document.images.length") == before
    assert browser.parsed("window.VIOLATIONS") == []
    assert browser.js("window.HOST.querySelectorAll('img, b').length") == 0


def test_the_markup_check_reads_a_real_image_as_an_image(browser: Browser):
    draw_table(browser, state_payload("one"))
    before = browser.js("document.images.length")
    browser.js(
        "window.PROBE = document.createElement('img');"
        "window.PROBE.src = 'data:image/gif;base64,R0lGOD';"
        "document.body.appendChild(window.PROBE);"
    )
    assert browser.js("document.images.length") == before + 1
    browser.js("window.PROBE.remove();")


def test_a_markup_bot_name_reaches_the_attribute_as_characters(browser: Browser):
    parts = draw_table(browser, build({"bots": [status(MARKUP_NAME)]}))
    assert only(parts, ROW_PATH)["attrs"]["data-bot-id"] == MARKUP_NAME
    assert browser.js("window.HOST.querySelectorAll('img, b').length") == 0


def test_a_newline_in_a_cell_draws_on_one_line(browser: Browser):
    payload = state_payload("one")
    payload["rows"][0]["texts"][surface.COL_BOT_ID] = "first\nsecond"
    parts = draw_table(browser, payload)
    cell = cell_at(parts, 0, surface.COL_BOT_ID)
    assert cell["whole"] == "first\nsecond"
    assert cell["style"]["whiteSpace"] == "nowrap"


def test_a_hostile_payload_still_draws_a_table(browser: Browser):
    """A module that threw here would draw no table and no row at all."""
    payload = state_payload("many")
    payload["rows"][0]["texts"][0] = 7
    payload["rows"][1]["colors"][surface.COL_MODE] = None
    payload["column_tooltips"] = None
    payload["selected_row"] = 99
    parts = draw_table(browser, payload)
    assert only(parts, "table")
    assert len(at_path(parts, ROW_PATH)) == len(payload["rows"])
    assert cell_at(parts, 0, 0)["text"] == "7"


def test_the_table_fills_the_named_empty_space_the_exchange_screen_leaves(
    browser: Browser,
):
    """The exchange screen draws an empty space and the table draws inside it."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js(
        "window.SPACE = document.createElement('div');"
        "window.SPACE.setAttribute('data-part', " + json.dumps("extractor-table") + ");"
        "window.HOST.appendChild(window.SPACE);"
    )
    browser.js(
        "window.PAYLOAD = " + json.dumps(json.dumps(state_payload("many"))) + ";"
    )
    filled = browser.js(
        "(function () {" + SETTER + "(JSON.parse(window.PAYLOAD));"
        "  return " + API + "fill(window.HOST) === window.SPACE; })()"
    )
    assert filled is True
    assert (
        browser.js("window.SPACE.querySelectorAll('[data-part=\"row\"]').length") == 3
    )


def test_the_space_check_reads_a_page_with_no_such_space_as_unfilled(browser: Browser):
    browser.js(PAGE_HELPERS)
    give_tokens(browser)
    browser.js(
        "window.PAYLOAD = " + json.dumps(json.dumps(state_payload("many"))) + ";"
    )
    filled = browser.js(
        "(function () {" + SETTER + "(JSON.parse(window.PAYLOAD));"
        "  return " + API + "fill(window.HOST) === null; })()"
    )
    assert filled is True


def logger_state(logger: logging.Logger) -> tuple:
    return (logger.level, tuple(sorted(id(one) for one in logger.handlers)))


def test_drawing_the_table_attaches_nothing_to_the_root_logger(browser: Browser):
    root = logging.getLogger()
    before = logger_state(root)
    draw_table(browser, state_payload("many"))
    assert logger_state(root) == before, f"the root logger moved from {before}"


def test_the_logger_snapshot_reports_a_handler_that_was_added():
    named = logging.getLogger("acervator.extractor_bot_table_unit")
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


def test_the_page_names_the_extractor_table_module_among_its_assets():
    named = [ref for ref in page_refs() if ref.endswith("extractor_bot_table.js")]
    assert len(named) == 1, f"the page names {len(named)} extractor table modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


@pytest.mark.parametrize("earlier", ["table_cells.js", "header_strip.js"])
def test_the_page_loads_the_modules_this_one_paints_through_first(earlier: str):
    refs = page_refs()
    assert refs.index("../../src/gui/web/" + earlier) < refs.index(
        "../../src/gui/web/extractor_bot_table.js"
    )
