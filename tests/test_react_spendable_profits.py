"""``spendable_profits.js`` against ``spendable_profits_surface.py``."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.core.privacy_mask_registry import ALL_FIELD_IDS, get_privacy_mask_registry
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import spendable_profits_surface as surface
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    load_order,
    new_engine,
    runs_after,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "spendable_profits.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
THEMES_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
WIDGETS_PATH = REPO_ROOT / "src" / "gui" / "web" / "shared_widgets.js"
HEADER_PATH = REPO_ROOT / "src" / "gui" / "web" / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body can write into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2

#: Python type -> the JavaScript type the same value has after json.dumps.
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

HAPPY = {
    "spendable": 1234.56,
    "total_realised": 9876.54,
    "locked": 250.0,
    "mature": 42.5,
    "exchange_count": 3,
}

MASKED_FIELDS = tuple(surface.FIELD_ID_BY_KEY.values())

#: Each state: the fields to hide, then the request the bridge answers.
STATES = {
    "built": ((), {}),
    "happy": ((), {"profits": HAPPY}),
    "unknown": ((), {"profits": dict(HAPPY, spendable=None)}),
    "unreadable": ((), {"profits": dict(HAPPY, spendable="lots")}),
    "negative": ((), {"profits": dict(HAPPY, spendable=-500.25)}),
    "zero": (
        (),
        {
            "profits": {
                "spendable": 0,
                "total_realised": 0,
                "locked": 0,
                "mature": 0,
                "exchange_count": 0,
            }
        },
    ),
    "empty_payload": ((), {"profits": {}}),
    "masked": (MASKED_FIELDS, {"profits": HAPPY}),
    "one_masked": (("kpi.spendable",), {"profits": HAPPY}),
    "dots_refreshed": ((), {"profits": HAPPY, "refresh_dots": True}),
}
STATE_NAMES = tuple(STATES)


def bridge_payload(**params: Any) -> dict:
    """One surface answer, put through the bridge's own encoding."""
    return json.loads(json.dumps(surface.view_model(params), ensure_ascii=True))


def state_payload(name: str) -> dict:
    """One named state, with the registry set before the surface is asked."""
    hidden, params = STATES[name]
    live = get_privacy_mask_registry()
    for field_id in ALL_FIELD_IDS:
        live.set_masked(field_id, field_id in hidden)
    return bridge_payload(**params)


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


@pytest.fixture()
def registry():
    """The privacy registry, with every field's prior mask put back after."""
    live = get_privacy_mask_registry()
    prior = {field: live.is_masked(field) for field in ALL_FIELD_IDS}
    for field in ALL_FIELD_IDS:
        live.set_masked(field, False)
    try:
        yield live
    finally:
        for field, was in prior.items():
            live.set_masked(field, was)


class JsRuntime(JsEngine):

    module_path = MODULE_PATH
    setter = "acervatorSetProfits"

    def load_widgets(self) -> None:
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def load_tokens(self) -> None:
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_themes(self, name: str) -> None:
        self.run(THEMES_PATH.read_text(encoding="utf-8"))
        self.bind_json("THEMES", theme_payload())
        self.bind_json("THEME_NAME", name)
        self.run("acervatorSetThemes(JSON.parse(THEMES));")
        self.run("acervatorThemes.select(JSON.parse(THEME_NAME));")

    def load_header(self) -> None:
        """Run the strip module, which owns the dot span this one draws."""
        self.run(HEADER_PATH.read_text(encoding="utf-8"))

    def named(self, api: str, name: str) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorProfits." + api + "(JSON.parse(NAME))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime, registry) -> JsRuntime:
    """The module holding one measured payload."""
    assert registry is not None
    js.load_header()
    js.push(state_payload("happy"))
    return js


#: Every field the surface publishes, and the module call answering for it.
MODULE_READERS = {
    "actions": "acervatorProfits.actions()",
    "alpha_scale": "acervatorProfits.alphaScale()",
    "bus_topics": "acervatorProfits.busTopics()",
    "call_names": "acervatorProfits.callNames()",
    "calls": "acervatorProfits.calls()",
    "column_count": "acervatorProfits.columnCount()",
    "columns": "acervatorProfits.columns()",
    "field_ids": "acervatorProfits.fieldIds()",
    "frame": "acervatorProfits.frame()",
    "item_count": "acervatorProfits.itemCount()",
    "items": "acervatorProfits.items()",
    "layout": "acervatorProfits.layout()",
    "method": "acervatorProfits.methodName()",
    "order": "acervatorProfits.order()",
    "separator": "acervatorProfits.separator()",
    "timer_delays_ms": "acervatorProfits.timerDelaysMs()",
    "timers": "acervatorProfits.timers()",
}


def unreachable_fields(payload: dict) -> list:
    return sorted(set(payload) - set(MODULE_READERS))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, registry, state: str
):
    """A field the module never carries is a value that stops at the bridge."""
    assert registry is not None
    payload = state_payload(state)
    js.push(payload)
    missing = unreachable_fields(payload)
    assert not missing, f"{len(missing)} published fields have no reader: {missing}"
    extra = sorted(set(MODULE_READERS) - set(payload))
    assert not extra, f"the module reads fields the surface has none of: {extra}"
    differing = {
        field: (payload[field], js.json(reader))
        for field, reader in MODULE_READERS.items()
        if js.json(reader) != payload[field]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields "
        f"differ: {sorted(differing)}"
    )
    assert len(MODULE_READERS) == len(payload)


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(registry):
    """The surface side of the comparison, with one extra name."""
    assert registry is not None
    payload = dict(bridge_payload())
    payload["only_on_the_surface"] = []
    assert unreachable_fields(payload) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_reads(registry):
    """The module side of the comparison, with one field taken away."""
    assert registry is not None
    payload = dict(bridge_payload())
    dropped = payload.pop("columns")
    assert dropped is not None
    assert sorted(set(MODULE_READERS) - set(payload)) == ["columns"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_counts_declared_and_held_lists_apart(
    js: JsRuntime, registry, state: str
):
    """Both counts, against both lists, for every state."""
    assert registry is not None
    payload = state_payload(state)
    written = js.push(payload)
    assert written["declared"]["fields"] == len(MODULE_READERS)
    assert written["held"]["fields"] == len(payload)
    assert written["declared"]["columns"] == payload["column_count"]
    assert written["held"]["columns"] == len(payload["columns"])
    assert written["declared"]["items"] == payload["item_count"]
    assert written["held"]["items"] == len(payload["items"])
    assert written["declared"]["calls"] == len(payload["call_names"])
    assert written["held"]["calls"] == len(payload["calls"])
    assert written["faults"] == []


def test_a_shortened_column_list_is_named_against_its_own_count(
    js: JsRuntime, registry
):
    """The count comparison, driven with one column taken away."""
    assert registry is not None
    payload = state_payload("happy")
    payload["columns"] = payload["columns"][:-1]
    written = js.push(payload)
    named = [
        one
        for one in written["faults"]
        if one["fault"] == "count" and one["where"] is None
    ]
    assert [one["field"] for one in named] == ["column_count"], written["faults"]
    assert written["held"]["columns"] == written["declared"]["columns"] - 1


def test_a_shortened_item_list_is_named_against_its_own_count(js: JsRuntime, registry):
    """The same comparison for the outer row's items."""
    assert registry is not None
    payload = state_payload("happy")
    payload["items"] = payload["items"][:-1]
    written = js.push(payload)
    named = [one for one in written["faults"] if one["fault"] == "count"]
    assert [one["field"] for one in named] == ["item_count"], written["faults"]


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(
    js: JsRuntime, registry
):
    """The field counts, driven with one field gone."""
    assert registry is not None
    payload = bridge_payload()
    del payload["separator"]
    written = js.push(payload)
    assert written["declared"]["fields"] == len(MODULE_READERS)
    assert written["held"]["fields"] == len(MODULE_READERS) - 1


def test_the_module_names_the_fields_the_surface_declares(loaded: JsRuntime):
    """The module's own field list, against the payload it was given."""
    assert sorted(loaded.json("acervatorProfits.declaredFields()")) == sorted(
        bridge_payload()
    )


def test_the_module_names_the_column_fields_the_surface_declares(loaded: JsRuntime):
    """The module's column field list, against one published column."""
    published = sorted(bridge_payload()["columns"][0])
    assert sorted(loaded.json("acervatorProfits.columnFields()")) == published


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_columns_arrive_in_the_order_the_surface_publishes(
    js: JsRuntime, registry, state: str
):
    """Order and identity read by name, never by position."""
    assert registry is not None
    payload = state_payload(state)
    js.push(payload)
    drawn = [one["key"] for one in js.json("acervatorProfits.columns()")]
    assert drawn == payload["order"]
    assert drawn == list(surface.COLUMN_ORDER)
    for name in payload["order"]:
        found = js.named("column", name)
        assert found is not None, name
        assert found["key"] == name
        assert found["field_id"] == payload["field_ids"][name]


def test_a_reordered_column_list_is_named_by_the_name_that_moved(
    js: JsRuntime, registry
):
    """The order comparison, driven with two columns swapped."""
    assert registry is not None
    payload = state_payload("happy")
    columns = payload["columns"]
    columns[0], columns[1] = columns[1], columns[0]
    written = js.push(payload)
    named = [one for one in written["faults"] if one["fault"] == "order"]
    assert {one["field"] for one in named} == {
        surface.COLUMN_ORDER[0],
        surface.COLUMN_ORDER[1],
    }, written["faults"]


def test_a_column_the_order_never_names_is_reported(js: JsRuntime, registry):
    """An order entry naming no column would draw a hole in the strip."""
    assert registry is not None
    payload = state_payload("happy")
    payload["order"][2] = "invented"
    written = js.push(payload)
    named = [one for one in written["faults"] if one["fault"] == "unnamed-column"]
    assert [one["field"] for one in named] == ["invented"], written["faults"]


def test_a_dot_under_the_wrong_field_is_reported(js: JsRuntime, registry):
    """A dot hiding another column's field would mask the wrong amount."""
    assert registry is not None
    payload = state_payload("happy")
    payload["columns"][0]["dot"]["field_id"] = "kpi.exch"
    written = js.push(payload)
    named = [one for one in written["faults"] if one["fault"] == "field-id"]
    assert [one["where"] for one in named] == ["dot"], written["faults"]


def test_the_field_id_check_is_quiet_on_every_shipped_state(js: JsRuntime, registry):
    """The same check on each whole payload reports nothing."""
    assert registry is not None
    for state in STATE_NAMES:
        written = js.push(state_payload(state))
        named = [one for one in written["faults"] if one["fault"] == "field-id"]
        assert named == [], (state, named)


def test_an_item_naming_no_column_is_reported(js: JsRuntime, registry):
    """An item pointing at a name no column carries would draw nothing."""
    assert registry is not None
    payload = state_payload("happy")
    payload["items"][0]["column"] = "invented"
    written = js.push(payload)
    named = [one for one in written["faults"] if one["fault"] == "unnamed-column"]
    assert [one["where"] for one in named] == ["items"], written["faults"]


def test_an_item_kind_the_strip_cannot_draw_is_reported(js: JsRuntime, registry):
    """A kind the module draws nothing for would leave a silent hole."""
    assert registry is not None
    payload = state_payload("happy")
    payload["items"][1]["kind"] = "invented"
    written = js.push(payload)
    named = [one for one in written["faults"] if one["fault"] == "unknown-kind"]
    assert len(named) == 1, written["faults"]


def test_a_call_the_surface_never_declared_is_named(js: JsRuntime, registry):
    """A branch the strip took that call_names never published."""
    assert registry is not None
    payload = state_payload("happy")
    payload["calls"].append("invented_branch")
    written = js.push(payload)
    named = [one for one in written["faults"] if one["fault"] == "unnamed-call"]
    assert [one["field"] for one in named] == ["invented_branch"], written["faults"]


def test_the_call_check_is_quiet_on_every_shipped_state(js: JsRuntime, registry):
    """Every branch the surface takes is one it declared."""
    assert registry is not None
    for state in STATE_NAMES:
        written = js.push(state_payload(state))
        named = [one for one in written["faults"] if one["fault"] == "unnamed-call"]
        assert named == [], (state, named)


def test_the_module_reports_every_branch_the_surface_can_take(js: JsRuntime, registry):
    """A declared branch never seen would leave its rendering untried."""
    assert registry is not None
    seen: set = set()
    for state in STATE_NAMES:
        js.push(state_payload(state))
        seen.update(js.json("acervatorProfits.calls()"))
    wanted = {
        surface.UPDATE,
        surface.SPENDABLE_UNKNOWN,
        surface.SPENDABLE_UNREADABLE,
        surface.SPENDABLE_POSITIVE,
        surface.SPENDABLE_NEGATIVE,
        surface.DOTS_REFRESHED,
    }
    assert wanted <= seen, sorted(wanted - seen)


def python_kinds(payload: dict) -> dict:
    """Every value's Python type, by the same dotted path the module uses."""
    found: dict = {}

    def descend(path: str, value: Any) -> None:
        if isinstance(value, dict):
            walk(path, value)
            return
        if isinstance(value, list):
            for at, one in enumerate(value):
                inner = path + "." + str(at)
                found[inner] = JS_TYPE_OF[type(one).__name__]
                descend(inner, one)

    def walk(prefix: str, node: dict) -> None:
        for name, value in node.items():
            path = prefix + "." + name if prefix else name
            found[path] = JS_TYPE_OF[type(value).__name__]
            descend(path, value)

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_of_every_state_arrives_as_the_type_it_left_as(
    js: JsRuntime, registry, state: str
):
    """Both sides agree by value and by type, at every depth."""
    assert registry is not None
    payload = state_payload(state)
    js.push(payload)
    wanted = python_kinds(payload)
    found = js.json("acervatorProfits.kinds()")
    assert set(found) == set(wanted), sorted(set(wanted) ^ set(found))
    differing = {
        path: (kind, found[path])
        for path, kind in wanted.items()
        if found[path] != kind
    }
    assert not differing, f"{state}: {len(differing)} values changed type: {differing}"


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime, registry):
    """A type comparison that read nothing would pass on any payload."""
    assert registry is not None
    payload = state_payload("happy")
    payload["column_count"] = str(payload["column_count"])
    js.push(payload)
    found = js.json("acervatorProfits.kinds()")
    assert found["column_count"] == "string"
    assert python_kinds(bridge_payload())["column_count"] == "number"


def declaration_values(sheet: str) -> set:
    """Every value written on the right of a colon in one Qt style sheet."""
    found = set()
    for part in str(sheet).replace("{", ";").replace("}", ";").split(";"):
        head, sep, tail = part.partition(":")
        if sep and head.strip():
            found.add(tail.strip())
    found.discard("")
    return found


def skin_values() -> set:
    """Every value the strip paints or shows, which the module must not hold."""
    found = {
        surface.EMPTY_TEXT,
        surface.MONEY_PREFIX,
        surface.MONEY_FORMAT,
        surface.SEPARATOR_TEXT,
        surface.FRAME_STYLE,
        surface.DOT_STYLE,
        surface.SEPARATOR_STYLE,
        surface.LABEL_STYLE,
        surface.SPENDABLE_LABEL_STYLE,
        surface.VALUE_STYLE_DEFAULT,
        surface.VALUE_STYLE_HIGHLIGHT,
        surface.VALUE_STYLE_MUTED,
        surface.VALUE_STYLE_NEGATIVE,
        surface.SPENDABLE_TOOLTIP,
        surface.SPENDABLE_UNKNOWN_TOOLTIP,
        surface.UNREADABLE_TOOLTIP,
        surface.DOT_REVEALED_GLYPH,
        surface.DOT_MASKED_GLYPH,
        surface.DOT_REVEALED_STATE,
        surface.DOT_MASKED_STATE,
    }
    for column in surface.COLUMNS:
        found.add(column["label"])
    for sheet in (surface.FRAME_STYLE, surface.DOT_STYLE, surface.SEPARATOR_STYLE):
        found |= declaration_values(sheet)
    found.discard("")
    return found


def token_values() -> set:
    """Every value the token and theme tables carry, in CSS spelling."""
    found: set = set()
    for value in dss.TOKENS.values():
        found.add(str(value))
        found.add(str(value) + "px")
    for theme in tes.THEMES.values():
        for value in theme.values():
            found.add(str(value))
    found.discard("")
    return found


def published_strings() -> set:
    """Every string the surface publishes, at any depth, plus its skin."""
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

    for params in ({}, {"profits": HAPPY}, {"profits": HAPPY, "refresh_dots": True}):
        walk(bridge_payload(**params))
    found |= skin_values()
    found.discard("")
    return found


MODULE_LITERALS = js_literals(MODULE_SOURCE)
SKIN_VALUES = skin_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()

#: The published words the module is allowed to name, being keys and states.
NAMED_WORDS = sorted(
    {
        "actions",
        "align",
        "alpha_scale",
        "bus_topics",
        "call_names",
        "calls",
        "column",
        "column_count",
        "column_margins_px",
        "column_spacing_px",
        "columns",
        "default",
        "dot",
        "dot_align",
        "field_id",
        "field_ids",
        "frame",
        "frame_shape",
        "hcenter",
        "vcenter",
        "initial_style",
        "initial_text",
        "item_count",
        "items",
        "kind",
        "key",
        "label",
        "label_style",
        "label_tooltip",
        "layout",
        "margins_px",
        "method",
        "order",
        "px",
        "separator",
        "separator_gap_px",
        "source_key",
        "spacing",
        "spacing_px",
        "stretch",
        "style_sheet",
        "text",
        "timer_delays_ms",
        "timers",
        "tooltip",
        "trailing_stretch",
        "vcenter",
        surface.METHOD,
    }
)

#: The numbers the module writes for its own structure, carrying no value.
OWN_NUMBERS = {"0", "1", "4", "100", "1", "0"}


def caught_by_scan(source: str) -> set:
    """Which of the checks below report on ``source``."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if [one for one in found["numbers"] if one not in OWN_NUMBERS]:
        caught.add("number")
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & SKIN_VALUES:
        caught.add("skin_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


def test_the_module_writes_no_colour_of_its_own():
    """A colour spelled out would not follow the surface or a token."""
    assert HEX_COLOUR.findall(MODULE_SOURCE) == []


def test_the_module_writes_no_value_the_strip_paints_or_shows():
    written = sorted(set(MODULE_LITERALS["strings"]) & SKIN_VALUES)
    assert not written, f"spendable_profits.js spells out skin values: {written}"


def test_the_module_writes_no_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"spendable_profits.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    """Every published string the module holds, listed rather than skipped."""
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert written == NAMED_WORDS, (
        f"the module names {sorted(set(written) - set(NAMED_WORDS))} more and "
        f"{sorted(set(NAMED_WORDS) - set(written))} fewer published strings "
        "than the list allows"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_strip_shows():
    overlap = sorted(set(NAMED_WORDS) & SKIN_VALUES)
    assert not overlap, f"these listed words are values the strip paints: {overlap}"


def test_the_module_writes_no_number_outside_its_own_list():
    written = sorted(
        {one for one in MODULE_LITERALS["numbers"] if one not in OWN_NUMBERS}
    )
    assert not written, f"spendable_profits.js writes these numbers: {written}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "spendable_profits.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


PLANTED_LINES = {
    "colour": 'var written = "' + str(dss.PRIMARY_BRIGHT) + '";',
    "hover_colour": 'var written = "' + str(dss.TEXT_MAX) + '";',
    "size": 'var written = "16px";',
    "number": "var written = 12;",
    "empty_marker": 'var written = "' + surface.EMPTY_TEXT + '";',
    "money_prefix": 'var written = "' + surface.MONEY_PREFIX + '";',
    "label": 'var written = "' + surface.COLUMNS[0]["label"] + '";',
    "tooltip": 'var written = "' + surface.UNREADABLE_TOOLTIP + '";',
    "frame_style": 'var written = "' + surface.FRAME_STYLE + '";',
    "regex": "var written = /ab+c/;",
}


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_one_written_value(kind: str):
    caught = caught_by_scan(PLANTED_LINES[kind])
    assert caught, f"the scan reported nothing on the written {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals("// #00ffcc\nvar kept = 'kept';")
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def module_lock():
    """A lock file every worker must take before it writes the module."""
    from filelock import FileLock

    return FileLock(str(MODULE_PATH) + ".lock")


def test_each_written_value_is_caught_in_the_module_file_itself():
    """Every value put in the shipped file is caught and then removed."""
    caught_each = {}
    with module_lock():
        original = MODULE_PATH.read_bytes()
        before = hashlib.sha256(original).hexdigest()
        assert original.decode("utf-8") == MODULE_SOURCE
        try:
            for kind in sorted(PLANTED_LINES):
                swap_module(MODULE_PATH, original + PLANTED_LINES[kind].encode("utf-8"))
                caught_each[kind] = caught_by_scan(
                    MODULE_PATH.read_text(encoding="utf-8")
                )
                swap_module(MODULE_PATH, original)
                after = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
                assert after == before, f"the file was not restored after {kind}"
        finally:
            swap_module(MODULE_PATH, original)
        assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before
    quiet = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not quiet, f"the scan reported nothing on these lines in the file: {quiet}"


def test_the_written_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    """Every appended line leaves the file valid JavaScript."""
    for kind, line in sorted(PLANTED_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetProfits") == "function", kind


def test_the_shipped_module_parses_in_the_engine_the_page_uses(js: JsRuntime):
    """A module the engine refuses would define nothing on the page."""
    assert js.json("typeof acervatorSetProfits") == "function"
    assert js.json("typeof acervatorLoadProfits") == "function"
    assert js.json("acervatorProfits.method") == surface.METHOD


def carriers_of(value: Any) -> list:
    """Every token whose value the widgets module says carries ``value``."""
    return [
        name
        for name, held in dss.TOKENS.items()
        if str(held) == str(value) or str(held) + "px" == str(value)
    ]


def test_every_colour_the_strip_paints_resolves_to_one_token(js: JsRuntime, registry):
    """A colour carried by no token would never follow a theme change."""
    assert registry is not None
    js.load_widgets()
    js.load_tokens()
    js.push(state_payload("happy"))
    for sheet in (surface.SEPARATOR_STYLE, surface.LABEL_STYLE):
        for value in declaration_values(sheet):
            if not value.startswith("#"):
                continue
            js.bind_json("VALUE", value)
            name = js.json("acervatorProfits.variableFor(JSON.parse(VALUE))")
            assert name is not None, value
            assert name in carriers_of(value), (value, name)


def test_a_value_no_token_carries_resolves_to_none(js: JsRuntime, registry):
    """The token lookup answers for anything, so it proves nothing."""
    assert registry is not None
    js.load_widgets()
    js.load_tokens()
    js.bind_json("VALUE", "#123456")
    assert js.json("acervatorProfits.variableFor(JSON.parse(VALUE))") is None


def test_the_module_reads_the_alpha_scale_the_surface_publishes(
    js: JsRuntime, registry
):
    """A scale read from nowhere would paint every panel the wrong depth."""
    assert registry is not None
    js.push(state_payload("happy"))
    assert js.json("acervatorProfits.alphaScale()") == surface.ALPHA_SCALE
    js.bind_json("SHEET", surface.FRAME_STYLE)
    drawn = js.json("acervatorProfits.styleOf(JSON.parse(SHEET))")
    wanted = str(80 * pow(surface.ALPHA_SCALE, -1))
    assert wanted in drawn["border"], drawn


def test_the_alpha_check_reads_a_different_depth_on_another_scale(
    js: JsRuntime, registry
):
    """A scale check that never divided would pass on any published scale."""
    assert registry is not None
    payload = state_payload("happy")
    payload["alpha_scale"] = surface.ALPHA_SCALE * 2
    js.push(payload)
    js.bind_json("SHEET", surface.FRAME_STYLE)
    drawn = js.json("acervatorProfits.styleOf(JSON.parse(SHEET))")
    wanted = str(80 * pow(surface.ALPHA_SCALE, -1))
    assert wanted not in drawn["border"], drawn


def test_the_hover_colour_is_read_out_of_the_dot_s_own_sub_block(
    js: JsRuntime, registry
):
    """A walk over base declarations alone would never enter :hover."""
    assert registry is not None
    js.push(state_payload("happy"))
    js.bind_json("SHEET", surface.DOT_STYLE)
    rules = js.json("acervatorProfits.stateRules(JSON.parse(SHEET))")
    assert len(rules) == 1, rules
    css = js.json("acervatorProfits.hoverCss(JSON.parse(SHEET))")
    assert str(dss.TEXT_MAX) in css, css
    base = js.json("acervatorProfits.declarations(JSON.parse(SHEET))")
    assert str(dss.TEXT_MAX) not in json.dumps(base), base


def test_a_sheet_with_no_sub_block_writes_no_page_rule(js: JsRuntime, registry):
    """The hover scan answers for any sheet, so it proves nothing."""
    assert registry is not None
    js.push(state_payload("happy"))
    js.bind_json("SHEET", surface.SEPARATOR_STYLE)
    assert js.json("acervatorProfits.hoverCss(JSON.parse(SHEET))") == ""


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open_page()
        self.wait_for_module()

    def open_page(self) -> None:
        """Loads the renderer page and waits until its load finishes."""
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
                if self.js("typeof window.acervatorSetProfits") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the strip module: readyState "
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


#: Every computed style property read off each drawn part.
STYLE_NAMES = [
    "color",
    "backgroundImage",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "letterSpacing",
    "marginLeft",
    "marginRight",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderRadius",
    "display",
    "flexDirection",
]

#: A Qt shorthand and the expanded border and padding names it settles into.
EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "border-radius": ("borderRadius",),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "margin": ("marginLeft", "marginRight"),
    "background": ("backgroundImage", "backgroundColor"),
    "font-size": ("fontSize",),
    "font-weight": ("fontWeight",),
    "letter-spacing": ("letterSpacing",),
    "color": ("color",),
}

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '900px';"
    "document.body.appendChild(window.HOST);"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeStyle = function (cssText, names) {"
    "  var probe = document.createElement('span');"
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
    "  var seen = {};"
    "  var walk = function (el, path) {"
    "    var part = el.getAttribute('data-part');"
    "    var here = path;"
    "    if (part !== null) {"
    "      here = path ? path + '/' + part : part;"
    "      seen[here] = (seen[here] || 0) + 1;"
    "      var at = here + '#' + String(seen[here]);"
    "      var attrs = {};"
    "      Array.prototype.slice.call(el.attributes).forEach(function (a) {"
    "        attrs[a.name] = a.value; });"
    "      var own = '';"
    "      Array.prototype.slice.call(el.childNodes).forEach(function (n) {"
    "        if (n.nodeType === Node.TEXT_NODE) { own += n.nodeValue; } });"
    "      found.push({ path: at, tag: el.tagName, attrs: attrs,"
    "        text: own, style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)

ALL_ELEMENTS = "window.HOST.querySelectorAll('*').length"
PART_ELEMENTS = "window.HOST.querySelectorAll('[data-part]').length"


def give_tokens(browser: Browser) -> int:
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_strip(browser: Browser, payload: dict) -> list:
    """Draw the strip into the page and read every named part back."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetProfits(JSON.parse(window.PAYLOAD));"
        "acervatorProfits.renderStrip(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def python_declarations(body: str) -> list:
    """Every ``property: value`` of one declaration body."""
    found = []
    depth = 0
    carried = ""
    for letter in str(body):
        if letter == "(":
            depth += 1
        if letter == ")":
            depth -= 1
        if letter == ";" and depth == 0:
            found.append(carried)
            carried = ""
            continue
        carried += letter
    found.append(carried)
    written = []
    for part in found:
        head, sep, tail = part.partition(":")
        if sep and head.strip() and tail.strip():
            written.append((head.strip(), tail.strip()))
    return written


def base_body(sheet: str) -> str:
    """The declarations of every block whose selector names no state."""
    bodies = []
    for chunk in str(sheet).split("}"):
        selector, sep, body = chunk.partition("{")
        if not sep:
            if selector.strip():
                bodies.append(chunk)
            continue
        if ":" not in selector:
            bodies.append(body)
    return ";".join(bodies)


def probe(browser: Browser, body: str) -> dict:
    """The computed values a bare element takes from the same declarations."""
    names: list = []
    for prop, _ in python_declarations(body):
        names.extend(EXPANDED.get(prop, (prop,)))
    if not names:
        return {}
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(body)
        + ", "
        + json.dumps(sorted(set(names)))
        + ")"
    )


def only(parts: list, path: str) -> dict:
    found = [one for one in parts if one["path"] == path]
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser, registry):
    """The page's own policy refused the module's script."""
    assert registry is not None
    assert browser.js("typeof window.acervatorSetProfits") == "function"
    assert browser.js("typeof window.acervatorProfits.Strip") == "function"


def test_the_host_element_has_a_width_before_anything_is_drawn(
    browser: Browser, registry
):
    """A host of zero width would lay every part out at zero."""
    assert registry is not None
    browser.js(PAGE_HELPERS)
    assert browser.js("window.HOST.clientWidth") > 0


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_drawn_strip_shows_the_amount_the_surface_published(
    browser: Browser, registry, state: str
):
    """A drawn amount apart from the published one is a number invented."""
    assert registry is not None
    payload = state_payload(state)
    parts = draw_strip(browser, payload)
    for at, column in enumerate(payload["columns"]):
        cell = only(parts, "frame/column/column-value#" + str(at + 1))
        assert cell["text"] == column["text"], (state, column["key"])
        caption = only(parts, "frame/column/column-label#" + str(at + 1))
        assert caption["text"] == column["label"]


def test_the_drawn_amount_check_names_one_changed_amount(browser: Browser, registry):
    """A drawn-text check that read nothing would pass on any payload."""
    assert registry is not None
    payload = state_payload("happy")
    payload["columns"][0]["text"] = "moved"
    parts = draw_strip(browser, payload)
    cell = only(parts, "frame/column/column-value#1")
    assert cell["text"] == "moved"
    assert cell["text"] != bridge_payload(profits=HAPPY)["columns"][0]["text"]


def test_every_element_the_strip_draws_carries_its_own_name(browser: Browser, registry):
    """An element with no name would be read by none of the checks here."""
    assert registry is not None
    draw_strip(browser, state_payload("happy"))
    every = browser.js(ALL_ELEMENTS)
    named = browser.js(PART_ELEMENTS)
    assert every == named, f"{every - named} drawn elements carry no name"
    assert every > 0


def test_the_name_check_would_see_one_element_left_unnamed(browser: Browser, registry):
    """The element counts move apart when one unnamed element is added."""
    assert registry is not None
    draw_strip(browser, state_payload("happy"))
    before = browser.js(ALL_ELEMENTS)
    browser.js("window.HOST.appendChild(document.createElement('i'));")
    assert browser.js(ALL_ELEMENTS) == before + 1
    assert browser.js(PART_ELEMENTS) == before


def test_the_drawn_frame_matches_its_own_whole_declaration(browser: Browser, registry):
    """The frame's rendered chrome, against a probe built from its own sheet."""
    assert registry is not None
    payload = state_payload("happy")
    parts = draw_strip(browser, payload)
    body = base_body(payload["frame"]["style_sheet"])
    wanted = probe(browser, translated(browser, body))
    drawn = only(parts, "frame#1")["style"]
    for name, value in wanted.items():
        assert drawn[name] == value, (name, drawn[name], value)
    assert "borderTopWidth" in wanted


def translated(browser: Browser, body: str) -> str:
    """One Qt declaration body with its colours put on the CSS scale."""
    browser.js("window.BODY = " + json.dumps(json.dumps(body)) + ";")
    return browser.js(
        "acervatorProfits.withGradients(JSON.parse(window.BODY), "
        + str(surface.ALPHA_SCALE)
        + ")"
    )


def test_the_frame_border_is_the_width_the_declaration_computes_to(
    browser: Browser, registry
):
    """A typed border width would disagree with what this host computes."""
    assert registry is not None
    payload = state_payload("happy")
    parts = draw_strip(browser, payload)
    body = base_body(payload["frame"]["style_sheet"])
    wanted = probe(browser, translated(browser, body))["borderTopWidth"]
    assert only(parts, "frame#1")["style"]["borderTopWidth"] == wanted
    assert wanted.endswith("px")


def test_the_frame_probe_reports_a_border_that_was_changed(browser: Browser, registry):
    """A probe that answered the same for any sheet would prove nothing."""
    assert registry is not None
    payload = state_payload("happy")
    draw_strip(browser, payload)
    body = base_body(payload["frame"]["style_sheet"])
    mine = probe(browser, translated(browser, body))
    other = probe(browser, translated(browser, body).replace("1px", "7px"))
    assert mine["borderTopWidth"] != other["borderTopWidth"]


def test_the_frame_paints_the_gradient_the_surface_declares(browser: Browser, registry):
    """A dropped gradient would leave the panel with no ground of its own."""
    assert registry is not None
    payload = state_payload("happy")
    parts = draw_strip(browser, payload)
    drawn = only(parts, "frame#1")["style"]["backgroundImage"]
    assert drawn.startswith("linear-gradient"), drawn
    assert drawn.count("rgba") == 2, drawn


def test_the_gradient_check_reads_no_gradient_from_a_plain_sheet(
    browser: Browser, registry
):
    """A background probe that always answered would prove nothing."""
    assert registry is not None
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    found = browser.parsed("window.probeStyle('color: red', [\"backgroundImage\"])")
    assert found["backgroundImage"] == "none"


@pytest.mark.parametrize("path", ["column-label", "column-value"])
def test_each_drawn_cell_matches_its_own_whole_declaration(
    browser: Browser, registry, path: str
):
    """A cell painted from any sheet but its own published one differs."""
    assert registry is not None
    payload = state_payload("happy")
    parts = draw_strip(browser, payload)
    key = "label_style" if path == "column-label" else "style_sheet"
    for at, column in enumerate(payload["columns"]):
        body = base_body(column[key])
        wanted = probe(browser, translated(browser, body))
        drawn = only(parts, "frame/column/" + path + "#" + str(at + 1))
        for name, value in wanted.items():
            assert drawn["style"][name] == value, (column["key"], name)


def test_the_cell_check_names_one_changed_colour(browser: Browser, registry):
    """A cell comparison that read nothing would pass on any sheet."""
    assert registry is not None
    payload = state_payload("happy")
    payload["columns"][0]["style_sheet"] = "color: #ff00ff; font-size: 16px;"
    parts = draw_strip(browser, payload)
    drawn = only(parts, "frame/column/column-value#1")["style"]["color"]
    wanted = probe(browser, "color: #ff00ff")["color"]
    assert drawn == wanted
    assert drawn != probe(browser, "color: " + str(dss.SUCCESS))["color"]


def test_the_drawn_dot_paints_the_hover_colour_qt_paints(browser: Browser, registry):
    """A colour inside a :hover sub-block reaches the page as a rule."""
    assert registry is not None
    payload = state_payload("happy")
    draw_strip(browser, payload)
    sheets = browser.parsed(
        "Array.prototype.slice.call("
        "  window.HOST.querySelectorAll('style')"
        ").map(function (el) { return el.textContent; })"
    )
    assert sheets, "the strip wrote no page rule at all"
    wanted = str(dss.TEXT_MAX)
    assert any(wanted in one for one in sheets), sheets
    assert any(":hover" in one for one in sheets), sheets


def test_the_hover_rule_check_would_see_a_sheet_with_no_sub_block(
    browser: Browser, registry
):
    """A payload whose dot sheet names no state writes no page rule."""
    assert registry is not None
    payload = state_payload("happy")
    for column in payload["columns"]:
        column["dot"]["style_sheet"] = surface.SEPARATOR_STYLE
    draw_strip(browser, payload)
    sheets = browser.parsed(
        "Array.prototype.slice.call("
        "  window.HOST.querySelectorAll('style')"
        ").map(function (el) { return el.textContent; })"
    )
    assert sheets == [], sheets


def test_the_drawn_strip_lays_its_items_out_in_the_published_order(
    browser: Browser, registry
):
    """A part order read by name, never by position in the document."""
    assert registry is not None
    payload = state_payload("happy")
    parts = draw_strip(browser, payload)
    drawn = [
        one["attrs"]["data-key"]
        for one in parts
        if one["attrs"].get("data-part") == "column"
    ]
    assert drawn == payload["order"]


def test_the_drawn_strip_carries_the_field_id_under_every_column(
    browser: Browser, registry
):
    """A column drawn under another field's name would mask the wrong cell."""
    assert registry is not None
    payload = state_payload("happy")
    parts = draw_strip(browser, payload)
    for one in parts:
        if one["attrs"].get("data-part") != "column":
            continue
        name = one["attrs"]["data-key"]
        assert one["attrs"]["data-field-id"] == payload["field_ids"][name]


def test_no_amount_reaches_the_page_while_the_field_is_masked(
    browser: Browser, registry
):
    """A masked amount drawn anywhere in the page is money leaked."""
    assert registry is not None
    payload = state_payload("masked")
    parts = draw_strip(browser, payload)
    written = json.dumps(parts)
    for amount in ("1234.56", "9876.54", "1,234.56", "9,876.54"):
        assert amount not in written, amount


def test_the_leak_scan_names_an_amount_written_into_the_page(
    browser: Browser, registry
):
    """The same scan over a revealed strip finds the amounts it hides."""
    assert registry is not None
    parts = draw_strip(browser, state_payload("happy"))
    assert "1,234.56" in json.dumps(parts)


MARKUP_PROBE = "<span></span>1m"
PLAIN_PROBE = "1m"


def asked_width(widget: Any) -> int:
    """The width one widget asks for, which is what its layout is given."""
    return int(widget.sizeHint().width())


def a_label(text: str) -> Any:
    from PySide6.QtWidgets import QLabel

    return QLabel(text)


def a_button(text: str) -> Any:
    from PySide6.QtWidgets import QPushButton

    return QPushButton(text)


SCREEN_WIDGETS = {"QPushButton": a_button}
RICH_TEXT_WIDGETS = {"QLabel": a_label}


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_no_plain_widget_this_strip_uses_reads_its_caller_text_as_markup(
    qapp, kind: str
):
    """A widget asking a wider layout for the tags never read them."""
    assert qapp is not None
    build = SCREEN_WIDGETS[kind]
    assert asked_width(build(MARKUP_PROBE)) != asked_width(
        build(PLAIN_PROBE)
    ), f"{kind} asked the same width for the markup and the plain words"


@pytest.mark.parametrize("kind", sorted(RICH_TEXT_WIDGETS))
def test_the_one_widget_this_strip_uses_that_does_read_markup_is_named(qapp, kind: str):
    """QLabel asks for MARKUP_PROBE exactly what it asks for PLAIN_PROBE."""
    assert qapp is not None
    build = RICH_TEXT_WIDGETS[kind]
    assert asked_width(build(MARKUP_PROBE)) == asked_width(build(PLAIN_PROBE))


@pytest.mark.parametrize("kind", sorted(RICH_TEXT_WIDGETS))
def test_the_asked_width_moves_when_the_plain_words_grow(qapp, kind: str):
    """A width that never moved would read every widget as one reading markup."""
    assert qapp is not None
    build = RICH_TEXT_WIDGETS[kind]
    assert asked_width(build(PLAIN_PROBE * 8)) != asked_width(build(PLAIN_PROBE))


HOSTILE_AMOUNTS = {
    "missing": {},
    "null_amount": {"spendable": None},
    "text_where_a_number_belongs": {"spendable": "lots"},
    "number_where_text_belongs": {"exchange_count": 3},
    "text_where_a_count_belongs": {"exchange_count": "three"},
    "not_a_number": {"spendable": math.nan},
    "infinity": {"spendable": math.inf},
    "negative_infinity": {"spendable": -math.inf},
    "a_thousand_million_million": {"spendable": 10**24},
    "two_hundred_characters": {"exchange_count": "N" * 200},
    "markup": {"exchange_count": "<b>9</b>"},
    "newline": {"exchange_count": "one\ntwo"},
    "duplicate_name": {"spendable": 1.0, "Spendable": 2.0},
    "a_negative_amount": {"spendable": -12.5, "locked": -1.0},
    "an_amount_that_does_not_reconcile": {
        "spendable": 1.0,
        "locked": 2.0,
        "mature": 900.0,
    },
    "a_flag_where_a_number_belongs": {"spendable": True},
}


@pytest.mark.parametrize("case", sorted(HOSTILE_AMOUNTS))
def test_a_hostile_amount_still_answers_a_whole_payload(
    js: JsRuntime, registry, case: str
):
    """A payload the strip cannot read must still draw every column."""
    assert registry is not None
    payload = bridge_payload(profits=dict(HAPPY, **HOSTILE_AMOUNTS[case]))
    written = js.push(payload)
    assert written["held"]["columns"] == len(surface.COLUMNS), case
    assert written["faults"] == [], (case, written["faults"])


@pytest.mark.parametrize("case", sorted(HOSTILE_AMOUNTS))
def test_a_hostile_amount_never_reaches_a_drawn_cell_as_text(registry, case: str):
    """No caller word reaches a cell, because every cell text is the surface's."""
    assert registry is not None
    payload = bridge_payload(profits=dict(HAPPY, **HOSTILE_AMOUNTS[case]))
    for column in payload["columns"]:
        assert "<" not in column["text"], (case, column["key"])
        assert "\n" not in column["text"], (case, column["key"])
        assert len(column["text"]) < 40, (case, column["text"][:60])


def test_the_hostile_text_check_would_see_a_word_reaching_a_cell(registry):
    """The same check on a cell holding caller text reports it."""
    assert registry is not None
    payload = bridge_payload(profits=HAPPY)
    payload["columns"][4]["text"] = "<b>9</b>"
    assert "<" in payload["columns"][4]["text"]


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_field_the_payload_omits_is_named_as_missing(
    js: JsRuntime, registry, field: str
):
    assert registry is not None
    payload = bridge_payload(profits=HAPPY)
    del payload[field]
    written = js.push(payload)
    named = [
        one
        for one in written["faults"]
        if one["field"] == field and one["fault"] == "missing"
    ]
    assert named, (field, written["faults"])


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_field_carrying_null_is_named(js: JsRuntime, registry, field: str):
    assert registry is not None
    payload = bridge_payload(profits=HAPPY)
    payload[field] = None
    written = js.push(payload)
    named = [
        one
        for one in written["faults"]
        if one["field"] == field and one["fault"] == "null"
    ]
    assert named, (field, written["faults"])


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime, registry):
    assert registry is not None
    written = js.push(bridge_payload(profits=HAPPY))
    assert written["faults"] == []


@pytest.mark.parametrize("scalar", [1, "text", True])
def test_a_scalar_where_a_list_belongs_leaves_the_walk_standing(
    js: JsRuntime, registry, scalar: Any
):
    """A scalar slipping past a list walk is the hole twenty units found."""
    assert registry is not None
    payload = bridge_payload(profits=HAPPY)
    payload["columns"] = scalar
    written = js.push(payload)
    assert written["held"]["columns"] == 0
    assert js.json("acervatorProfits.columns()") == []


@pytest.mark.parametrize("scalar", [1, "text", True])
def test_a_scalar_where_a_bag_belongs_leaves_the_walk_standing(
    js: JsRuntime, registry, scalar: Any
):
    assert registry is not None
    payload = bridge_payload(profits=HAPPY)
    payload["layout"] = scalar
    written = js.push(payload)
    assert written["faults"] != []
    assert js.json("acervatorProfits.layout()") == {}


def test_a_scalar_inside_the_column_list_is_named(js: JsRuntime, registry):
    """A column that is a number would carry no key for the pairing."""
    assert registry is not None
    payload = bridge_payload(profits=HAPPY)
    payload["columns"][2] = 7
    written = js.push(payload)
    named = [one for one in written["faults"] if one["fault"] == "not-an-object"]
    assert [one["where"] for one in named] == ["columns"], written["faults"]


def test_a_scalar_inside_the_item_list_is_named(js: JsRuntime, registry):
    assert registry is not None
    payload = bridge_payload(profits=HAPPY)
    payload["items"][3] = 7
    written = js.push(payload)
    named = [one for one in written["faults"] if one["fault"] == "not-an-object"]
    assert [one["where"] for one in named] == ["items"], written["faults"]


def test_the_scalar_checks_are_quiet_on_a_whole_payload(js: JsRuntime, registry):
    assert registry is not None
    written = js.push(bridge_payload(profits=HAPPY))
    named = [one for one in written["faults"] if one["fault"] == "not-an-object"]
    assert named == []


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(
    js: JsRuntime, registry
):
    assert registry is not None
    js.push(bridge_payload(profits=HAPPY))
    assert js.json("acervatorProfits.isLoaded()") is True
    js.push([1, 2, 3])
    assert js.json("acervatorProfits.isLoaded()") is False
    assert js.json("acervatorProfits.columns()") == []


def test_markup_reaching_a_drawn_value_is_named(js: JsRuntime, registry):
    """A QLabel reads its caller text as markup, so a tag must be reported."""
    assert registry is not None
    payload = bridge_payload(profits=HAPPY)
    payload["columns"][0]["text"] = "<b>1</b>"
    written = js.push(payload)
    named = [one for one in written["faults"] if one["fault"] == "markup"]
    assert [one["field"] for one in named] == ["text"], written["faults"]


def test_the_markup_check_is_quiet_on_every_shipped_state(js: JsRuntime, registry):
    assert registry is not None
    for state in STATE_NAMES:
        written = js.push(state_payload(state))
        named = [one for one in written["faults"] if one["fault"] == "markup"]
        assert named == [], (state, named)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime, registry):
    """A module asking another method would answer with another screen."""
    assert registry is not None
    js.run(
        "var ASKED = [];"
        "window.acervator = { call: function (name, params) {"
        "  ASKED.push([name, params]);"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
    )
    js.bind_json("PAYLOAD", bridge_payload(profits=HAPPY))
    js.run("acervatorLoadProfits({});")
    assert js.json("ASKED[0][0]") == surface.METHOD


def test_the_module_reports_a_missing_bridge_rather_than_raising(
    js: JsRuntime, registry
):
    assert registry is not None
    js.run("acervatorLoadProfits({});")
    assert js.json("acervatorProfits.loadError()") is not None
    assert js.json("acervatorProfits.isLoaded()") is False


def test_the_renderer_runs_the_strip_module_after_the_header_it_draws_with():
    """The dot span comes from `header_strip.js`, which runs first."""
    assert runs_after(load_order(), MODULE_PATH.name, HEADER_PATH.name), load_order()


def test_the_order_reading_answers_no_for_the_two_the_other_way_round():
    """The same reading of an order that runs the strip first."""
    swapped = [MODULE_PATH.name, HEADER_PATH.name]
    assert not runs_after(swapped, MODULE_PATH.name, HEADER_PATH.name)
    assert not runs_after([HEADER_PATH.name], MODULE_PATH.name, HEADER_PATH.name)


def test_the_module_file_is_written_with_one_line_ending(registry):
    """A module in CRLF would differ from every other one on the page."""
    assert registry is not None
    body = MODULE_PATH.read_bytes()
    assert b"\r\n" not in body
    assert body.endswith(b"\n")
    assert os.linesep is not None
