"""live_status_tab.js drawn and read back against live_status_tab_surface."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui import design_system as ds
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import live_status_tab_surface as lst
from src.gui.main_tabs import theme_engine_surface as tes

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "live_status_tab.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
THEMES_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
WIDGETS_PATH = REPO_ROOT / "src" / "gui" / "web" / "shared_widgets.js"
HEADER_PATH = REPO_ROOT / "src" / "gui" / "web" / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: MODULE_SOURCE is read at collection, before any test body writes the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
EVENT_DRAIN_ROUNDS = 20
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500
READY_ROUNDS = 100
READY_STEP_MS = 100
HOST_WIDTH_PX = 900

FIXED_NOW = 1_700_000_000.0

#: Python type -> the JavaScript type the same value has after the
#: bridge's ``json.dumps``.
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

HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")

LAST_ERROR_TEXT = "venue refused the order"
LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'


# -- the surface, as the bridge serialises it --------------------------


def status_reading(**named: Any) -> dict:
    """The stats bag holding total_trades, current_price, uptime and last_error."""
    fields = {
        "total_trades": 12,
        "active_buys": 2,
        "active_sells": 3,
        "current_price": 0.00002345,
        "uptime": 3661.4,
        "last_error": LAST_ERROR_TEXT,
    }
    fields.update(named)
    return {"stats": fields}


def bot_spec(status: Any = None, **readings: Any) -> dict:
    """One bot, its status reading and the seven exchange readings."""
    stats = {
        "realised": 12.5,
        "avg_entry": 0.000123,
        "cost_basis": 456.789,
        "unrealised": -3.25,
        "fees": 1.5,
        "trade_count": 7,
        "fresh_ts": FIXED_NOW - 125.0,
    }
    stats.update(readings)
    return {"status": status_reading() if status is None else status, "stats": stats}


#: The driving states the surface publishes, each sent through the bridge.
STATES = {
    "empty": {},
    "filled": {"bot": bot_spec()},
    "refresh_pending": {"bot": bot_spec(fresh_ts=0.0)},
    "no_stats_object": {"bot": {"status": status_reading(), "stats": None}},
    "age_under_a_minute": {"bot": bot_spec(fresh_ts=FIXED_NOW - 30.0)},
    "zero_everywhere": {
        "bot": bot_spec(
            realised=0.0,
            avg_entry=0.0,
            cost_basis=0.0,
            unrealised=0.0,
            fees=0.0,
            trade_count=0,
            fresh_ts=FIXED_NOW - 10.0,
        )
    },
    "negative_everywhere": {
        "bot": bot_spec(realised=-12.5, cost_basis=-456.789, fees=-1.5)
    },
    "no_price_no_error": {
        "bot": bot_spec(status=status_reading(current_price=0, last_error=""))
    },
}
STATE_NAMES = tuple(STATES)


def bridge_payload(**params: Any) -> dict:
    """One view_model answer after the bridge's json.dumps, always asked with
    reset."""
    asked = {"reset": True, "now": FIXED_NOW}
    asked.update(params)
    return json.loads(json.dumps(lst.view_model(asked), ensure_ascii=True))


def state_payload(name: str) -> dict:
    return bridge_payload(**STATES[name])


def token_payload() -> dict:
    """The design system view_model, as the variable resolver reads it."""
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    """The theme view_model, the second table the resolver consults."""
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


ROW_LABEL, ROW_TEXT, ROW_STYLE, ROW_TOOLTIP, ROW_WRAP = range(5)


def labels_of(payload: dict) -> list:
    return [one[ROW_LABEL] for one in payload["rows"]]


def values_of(payload: dict) -> list:
    return [one[ROW_TEXT] for one in payload["rows"]]


# -- the JavaScript engine ---------------------------------------------


def drain_events() -> None:
    """Turn processEvents so a queued promise callback runs before the test
    reads."""
    from PySide6.QtCore import QCoreApplication, QEventLoop

    for _ in range(EVENT_DRAIN_ROUNDS):
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)


class JsRuntime:
    """A QJSEngine holding ``live_status_tab.js`` and a ``window`` global."""

    def __init__(self, engine: Any, source: str) -> None:
        self._engine = engine
        engine.evaluate("var window = this;")
        engine.evaluate(HEADER_PATH.read_text(encoding="utf-8"), HEADER_PATH.name)
        loaded = engine.evaluate(source, MODULE_PATH.name)
        if loaded.isError():
            raise AssertionError("live_status_tab.js did not run: " + loaded.toString())

    def engine_of(self) -> Any:
        """A second engine of the same kind, for a second module body."""
        return type(self._engine)()

    def run(self, script: str) -> Any:
        result = self._engine.evaluate(script)
        assert not result.isError(), script + " -> " + result.toString()
        return result

    def json(self, expression: str) -> Any:
        """Evaluate ``expression`` and bring its value back as Python."""
        text = self.run("JSON.stringify(" + expression + ")").toString()
        return None if text == "undefined" else json.loads(text)

    def bind_json(self, name: str, value: Any) -> None:
        """Bind value on the engine global as JSON text every caller parses
        back."""
        self._engine.globalObject().setProperty(name, json.dumps(value))

    def push(self, payload: Any) -> dict:
        self.bind_json("PAYLOAD", payload)
        return self.json("acervatorSetLiveStatus(JSON.parse(PAYLOAD))")

    def load_tokens(self) -> None:
        """Run the token module and give it the real table."""
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_themes(self, name: str) -> None:
        """Run the theme module and select one theme."""
        self.run(THEMES_PATH.read_text(encoding="utf-8"))
        self.bind_json("THEMES", theme_payload())
        self.bind_json("THEME_NAME", name)
        self.run("acervatorSetThemes(JSON.parse(THEMES));")
        self.run("acervatorThemes.select(JSON.parse(THEME_NAME));")

    def load_widgets(self) -> None:
        """Run the shared widgets module, which owns the one-carrier rule."""
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def named(self, reader: str, name: Any) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorLiveStatus." + reader + "(JSON.parse(NAME))")

    def variable_for(self, value: Any) -> Any:
        self.bind_json("VALUE", value)
        return self.json("acervatorLiveStatus.variableFor(JSON.parse(VALUE))")

    def style_of(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorLiveStatus.styleOf(JSON.parse(SHEET))")

    def declarations(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorLiveStatus.declarations(JSON.parse(SHEET))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    qtqml = pytest.importorskip("PySide6.QtQml")
    assert qapp is not None
    return JsRuntime(qtqml.QJSEngine(), MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding the surface's filled tab."""
    js.push(state_payload("filled"))
    return js


# -- 1. everything the surface publishes reaches the module ------------

#: Every field the surface publishes, and the module call that answers for it.
MODULE_READERS = {
    "accessible_name": "acervatorLiveStatus.accessibleName()",
    "actions": "acervatorLiveStatus.actions()",
    "attributes": "acervatorLiveStatus.attributes()",
    "bus_topics": "acervatorLiveStatus.busTopics()",
    "call_names": "acervatorLiveStatus.callNames()",
    "calls": "acervatorLiveStatus.calls()",
    "colors": "acervatorLiveStatus.colors()",
    "container": "acervatorLiveStatus.container()",
    "defaults": "acervatorLiveStatus.defaults()",
    "formats": "acervatorLiveStatus.formats()",
    "keys": "acervatorLiveStatus.keys()",
    "labels": "acervatorLiveStatus.labels()",
    "no_stats": "acervatorLiveStatus.noStats()",
    "row_count": "acervatorLiveStatus.rowCount()",
    "rows": "acervatorLiveStatus.rows()",
    "stats_form": "acervatorLiveStatus.statsForm()",
    "stats_group": "acervatorLiveStatus.statsGroup()",
    "stretch_shown": "acervatorLiveStatus.stretchShown()",
    "texts": "acervatorLiveStatus.texts()",
    "thresholds": "acervatorLiveStatus.thresholds()",
    "timer_delays_ms": "acervatorLiveStatus.timerDelaysMs()",
    "timers": "acervatorLiveStatus.timers()",
    "word_wrap": "acervatorLiveStatus.wordWrap()",
}


def unreachable_fields(payload: dict) -> list:
    """Every field of payload no entry of MODULE_READERS answers for."""
    return sorted(set(payload) - set(MODULE_READERS))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
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


def test_the_whole_payload_check_names_a_field_only_the_surface_holds():
    payload = dict(state_payload("filled"))
    payload["planted_only_on_the_surface"] = []
    assert unreachable_fields(payload) == ["planted_only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_reads():
    payload = dict(state_payload("filled"))
    dropped = payload.pop("rows")
    assert dropped is not None
    extra = sorted(set(MODULE_READERS) - set(payload))
    assert extra == ["rows"], f"the check named {extra}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["rows"] == payload["row_count"]
    assert report["held"]["rows"] == len(payload["rows"])
    assert report["declared"]["cells"] == report["held"]["cells"]


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("filled")
    del payload["rows"]
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(MODULE_READERS) - 1
    assert report["held"]["rows"] == 0


def test_a_row_short_of_a_cell_shortens_the_held_cell_count(js: JsRuntime):
    payload = state_payload("filled")
    payload["rows"][0] = payload["rows"][0][:-1]
    report = js.push(payload)
    assert report["held"]["cells"] == report["declared"]["cells"] - 1


def test_the_module_holds_every_row_the_surface_publishes(loaded: JsRuntime):
    declared = labels_of(state_payload("filled"))
    assert loaded.json("acervatorLiveStatus.rowLabels()") == declared


def test_the_row_check_names_a_row_only_the_surface_holds(js: JsRuntime):
    payload = state_payload("filled")
    dropped = payload["rows"].pop()
    js.push(payload)
    held = js.json("acervatorLiveStatus.rowLabels()")
    missing = sorted(set(labels_of(state_payload("filled"))) - set(held))
    assert missing == [dropped[ROW_LABEL]], f"the check named {missing}"


def test_the_module_names_the_fields_the_surface_declares(loaded: JsRuntime):
    assert sorted(loaded.json("acervatorLiveStatus.declaredFields()")) == sorted(
        state_payload("filled")
    )


def test_the_module_names_the_five_cells_the_surface_writes_per_row(
    loaded: JsRuntime,
):
    cells = loaded.json("acervatorLiveStatus.rowCells()")
    assert cells == ["label", "text", "style_sheet", "tooltip", "word_wrap"]
    assert len(cells) == len(state_payload("filled")["rows"][0])


# -- 2. no value is written in the JavaScript --------------------------


def js_literals(source: str) -> dict:
    """Every string literal, number literal and stray slash in source."""
    quotes = "'\"`"
    digits = "0123456789"
    ident = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")
    numeric = set(digits + ".xXoObBeE_abcdefABCDEF")
    strings: list = []
    numbers: list = []
    slashes: list = []
    index = 0
    end = len(source)
    while index < end:
        char = source[index]
        if char == "/" and source.startswith("//", index):
            stop = source.find("\n", index)
            index = end if stop < 0 else stop + 1
            continue
        if char == "/" and source.startswith("/*", index):
            stop = source.find("*/", index + 2)
            index = end if stop < 0 else stop + 2
            continue
        if char == "/":
            slashes.append(source[max(index - 20, 0) : index + 20])
            index += 1
            continue
        if char in quotes:
            cursor = index + 1
            body: list = []
            while cursor < end and source[cursor] != char:
                if source[cursor] == "\\":
                    body.append(source[cursor : cursor + 2])
                    cursor += 2
                    continue
                body.append(source[cursor])
                cursor += 1
            strings.append("".join(body))
            index = cursor + 1
            continue
        if char in digits and (index == 0 or source[index - 1] not in ident):
            cursor = index
            while cursor < end and source[cursor] in numeric:
                cursor += 1
            numbers.append(source[index:cursor])
            index = cursor
            continue
        index += 1
    return {"strings": strings, "numbers": numbers, "slashes": slashes}


def as_css(value: Any) -> set:
    """One published value, in every spelling a stylesheet could carry."""
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


def declaration_values(sheet: str) -> set:
    """Every value written on the right of a colon in one Qt style sheet."""
    found = set()
    for part in re.split(r"[;{}]", str(sheet)):
        head, sep, tail = part.partition(":")
        if sep and head.strip():
            found.add(tail.strip())
    found.discard("")
    return found


def tab_values() -> set:
    """Every colour, size, money text and style sheet the tab paints."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        for one in payload["rows"]:
            found.add(one[ROW_LABEL])
            found.add(one[ROW_TEXT])
            found.add(one[ROW_STYLE])
            found.add(one[ROW_TOOLTIP])
            found |= declaration_values(one[ROW_STYLE])
        for value in payload["labels"].values():
            found.add(value)
        for value in payload["texts"].values():
            found.add(value)
        for value in payload["colors"].values():
            found.add(value)
        for value in payload["formats"].values():
            found.add(value)
        found.add(payload["stats_group"]["title"])
        found |= as_css(payload["container"]["spacing_px"])
    found.discard("")
    return found


def token_values() -> set:
    """Every value the token and theme tables carry, in CSS spelling."""
    found: set = set()
    for value in dss.TOKENS.values():
        found |= as_css(value)
    for theme in tes.THEMES.values():
        for value in theme.values():
            found |= as_css(value)
    found.discard("")
    return found


def published_strings() -> set:
    """Every string state_payload publishes, keys and values alike."""
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


SKIN_VALUES = tab_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every surface word the module writes as a text literal.
#: Each is a payload field, a row cell or a sub-field name.
NAMED_WORDS = sorted(
    {
        "accessible_name",
        "actions",
        "attributes",
        "bus_topics",
        "call_names",
        "calls",
        "colors",
        "configured",
        "configured_by_host",
        "container",
        "defaults",
        "field_grows",
        "formats",
        "horizontal_spacing_px",
        "keys",
        "labels",
        "margins_px",
        "margins_set",
        "no_price",
        "no_stats",
        "no_style",
        "no_tooltip",
        "other_rows",
        "row_count",
        "rows",
        "rows_wrap",
        "shown",
        "spacing_px",
        "stats_form",
        "stats_group",
        "stretch_shown",
        "texts",
        "thresholds",
        "timer_delays_ms",
        "timers",
        "title",
        "vertical_spacing_px",
        "word_wrap",
    }
)


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "live_status_tab.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"live_status_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & SKIN_VALUES)
    assert not written, f"live_status_tab.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"live_status_tab.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert written == NAMED_WORDS, (
        f"the module names {sorted(set(written) - set(NAMED_WORDS))} more and "
        f"{sorted(set(NAMED_WORDS) - set(written))} fewer published strings "
        "than the list allows"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_tab_shows():
    overlap = sorted(set(NAMED_WORDS) & SKIN_VALUES)
    assert not overlap, f"these named words are values the tab paints: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "live_status_tab.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


FILLED = state_payload("filled")

PLANTED_LINES = {
    "colour": 'var planted = "' + str(ds.SUCCESS) + '";',
    "another_colour": 'var planted = "#00ffcc";',
    "size": 'var planted = "' + str(FILLED["container"]["spacing_px"]) + 'px";',
    "spacing": "var planted = " + str(FILLED["container"]["spacing_px"]) + ";",
    "number": "var planted = 12;",
    "money_text": 'var planted = "' + FILLED["rows"][0][ROW_TEXT] + '";',
    "row_label": 'var planted = "' + FILLED["labels"]["realised"] + '";',
    "pending_text": 'var planted = "' + FILLED["texts"]["pending"] + '";',
    "style_sheet": 'var planted = "' + FILLED["rows"][0][ROW_STYLE] + '";',
    "money_format": 'var planted = "' + FILLED["formats"]["realised_value"] + '";',
    "group_title": 'var planted = "' + FILLED["stats_group"]["title"] + '";',
    "token_value": 'var planted = "' + str(dss.PRIMARY) + '";',
    "regex": "var planted = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the five checks above report on ``source``."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if found["numbers"]:
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


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_a_planted_line(kind: str):
    caught = caught_by_scan(PLANTED_LINES[kind])
    assert caught, f"the scan reported nothing on the planted {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


#: The file the swap below moves over the module, named for this unit.
SPARE_PATH = MODULE_PATH.with_name("live_status_tab.plant_scan.js")


#: Attempts allowed before a swap gives up on a Chromium file share.
SWAP_ATTEMPTS = 2000

#: How many attempts each swap of this run actually needed.
SWAP_TRIES: list = []


def swap_module(content: bytes) -> None:
    """Move content over MODULE_PATH with os.replace, retrying while Chromium
    holds it."""
    SPARE_PATH.write_bytes(content)
    for attempt in range(SWAP_ATTEMPTS):
        try:
            os.replace(SPARE_PATH, MODULE_PATH)
        except PermissionError:
            continue
        SWAP_TRIES.append(attempt + 1)
        return
    raise AssertionError(
        f"the module could not be swapped in {SWAP_ATTEMPTS} attempts; "
        f"{SPARE_PATH.name} is still on disk"
    )


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
            assert after == before, f"the file was not restored after the {kind} plant"
    finally:
        swap_module(original)
        SPARE_PATH.unlink(missing_ok=True)
    blind = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not blind, f"the scan reported nothing on these plants in the file: {blind}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_planted_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, line in sorted(PLANTED_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetLiveStatus") == "function", kind


# -- 3. both sides agree, value for value and type for type ------------


def python_kinds(payload: dict) -> dict:
    """The JavaScript type of every value of ``payload``, by dotted path."""
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
    payload = state_payload(state)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json("acervatorLiveStatus.kinds()")
    differing = {
        path: (kind, actual.get(path))
        for path, kind in expected.items()
        if actual.get(path) != kind
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(expected)} values changed "
        f"type: {sorted(differing)}"
    )
    assert sorted(actual) == sorted(expected)


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    payload = state_payload("filled")
    payload["container"]["spacing_px"] = str(payload["container"]["spacing_px"])
    js.push(payload)
    expected = python_kinds(state_payload("filled"))
    actual = js.json("acervatorLiveStatus.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["container.spacing_px"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_row_agrees_with_the_surface_cell_for_cell(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    names = js.json("acervatorLiveStatus.rowCells()")
    for one in payload["rows"]:
        actual = js.named("row", one[ROW_LABEL])
        expected = dict(zip(names, one))
        differing = {
            field: (expected[field], actual.get(field))
            for field in expected
            if actual.get(field) != expected[field]
        }
        assert not differing, (
            f"{state}/{one[ROW_LABEL]}: {len(differing)} of {len(expected)} "
            f"values differ: {sorted(differing)}"
        )
        assert len(actual) == len(expected)


def test_the_row_value_check_names_a_changed_value(js: JsRuntime):
    payload = state_payload("filled")
    payload["rows"][0][ROW_TEXT] += "0"
    js.push(payload)
    names = js.json("acervatorLiveStatus.rowCells()")
    expected = dict(zip(names, state_payload("filled")["rows"][0]))
    actual = js.named("row", expected["label"])
    differing = sorted(f for f in expected if actual.get(f) != expected[f])
    assert differing == ["text"], f"the check named {differing}"


def test_the_module_reports_only_what_it_was_given(js: JsRuntime):
    payload = state_payload("filled")
    invented = ["given-label", "given-text", "", "given-tip", True]
    payload["rows"] = [invented]
    payload["row_count"] = len(payload["rows"])
    js.push(payload)
    assert js.json("acervatorLiveStatus.rows()") == [invented]
    assert not set(invented[:2]) & SKIN_VALUES


def test_the_module_reads_no_inherited_javascript_name_as_a_row(loaded: JsRuntime):
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        assert loaded.named("row", inherited) is None
        assert loaded.named("labelFor", inherited) is None


def test_the_inherited_name_check_still_reads_a_real_row(loaded: JsRuntime):
    payload = state_payload("filled")
    names = payload["labels"]
    assert loaded.named("labelFor", "realised") == names["realised"]
    assert (
        loaded.named("row", names["realised"])["text"] == payload["rows"][0][ROW_TEXT]
    )


# -- the values resolved through the token module ----------------------


def carriers_of(value: Any) -> list:
    """Every non-alias design token carrying ``value``."""
    tokens = token_payload()
    aliases = tokens["alias_targets"]
    return sorted(
        name
        for name, held in tokens["tokens"].items()
        if str(held) == str(value) and name not in aliases
    )


TAB_COLOURS = sorted(
    {
        value
        for value in tab_values()
        if isinstance(value, str) and HEX_COLOUR.fullmatch(value)
    }
)


def test_every_colour_the_tab_paints_resolves_to_one_token(js: JsRuntime):
    js.load_tokens()
    js.load_widgets()
    assert TAB_COLOURS, "the tab paints no colour; the check cannot report"
    for colour in TAB_COLOURS:
        assert carriers_of(colour) == [
            js.variable_for(colour)
        ], f"{colour} is carried by {carriers_of(colour)}"


def test_the_row_gap_is_painted_from_the_surface_and_not_through_a_token(
    js: JsRuntime,
):
    js.load_tokens()
    js.load_widgets()
    gap = state_payload("filled")["container"]["spacing_px"]
    assert carriers_of(gap) == ["RADIUS_CARD"], f"{gap} -> {carriers_of(gap)}"
    assert "RADIUS_CARD" not in MODULE_SOURCE


def test_a_value_no_token_carries_resolves_to_none(js: JsRuntime):
    js.load_tokens()
    js.load_widgets()
    assert js.variable_for("no-token-carries-this") is None


def test_the_resolver_reports_no_name_with_the_widget_module_off_the_page(
    js: JsRuntime,
):
    js.load_tokens()
    assert js.variable_for(str(ds.SUCCESS)) is None


# -- reading one Qt style sheet ----------------------------------------


def python_declarations(body: str) -> list:
    """Every ``property: value`` of one declaration body."""
    found = []
    for part in str(body).split(";"):
        head, sep, tail = part.partition(":")
        if sep and head.strip() and tail.strip():
            found.append((head.strip(), tail.strip()))
    return found


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


def test_the_module_reads_the_same_declarations_as_the_surface_wrote(js: JsRuntime):
    payload = state_payload("filled")
    sheets = [one[ROW_STYLE] for one in payload["rows"]]
    assert any(sheets), "no row carries a style sheet; the check cannot report"
    for sheet in sheets:
        expected = [
            {"property": name, "value": value}
            for name, value in python_declarations(base_body(sheet))
        ]
        assert js.declarations(sheet) == expected, f"declarations differ for {sheet}"


def test_the_declaration_reader_names_a_changed_value(js: JsRuntime):
    sheet = state_payload("filled")["rows"][0][ROW_STYLE]
    expected = [
        {"property": name, "value": value}
        for name, value in python_declarations(base_body(sheet))
    ]
    assert js.declarations(sheet + "letter-spacing: 1px;") != expected


def test_every_declaration_the_rows_carry_reaches_a_css_property(js: JsRuntime):
    named: list = []
    for name in STATE_NAMES:
        for at, one in enumerate(state_payload(name)["rows"]):
            js.bind_json("SHEET", one[ROW_STYLE])
            found = js.json("acervatorLiveStatus.unpaintable(JSON.parse(SHEET))")
            named.extend((name, at, property_name) for property_name in found)
    assert not named, f"these declarations reach no CSS property: {named}"


def test_the_unpaintable_check_names_a_qt_only_paint(js: JsRuntime):
    sheet = "background: qlineargradient(x1: 0, y1: 0, stop: 0 #000000);"
    js.bind_json("SHEET", sheet)
    found = js.json("acervatorLiveStatus.unpaintable(JSON.parse(SHEET))")
    assert found == ["background"], f"the check named {found}"


def test_a_qt_only_paint_in_a_row_is_named_as_a_fault(js: JsRuntime):
    payload = state_payload("filled")
    payload["rows"][0][ROW_STYLE] = "background: qlineargradient(stop: 0 #000000);"
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "not-css"]
    assert named == [
        {
            "where": "row:0",
            "field": "style_sheet",
            "fault": "not-css",
            "detail": "background",
        }
    ], f"the check named {named}"


def test_the_qt_only_check_is_quiet_on_every_shipped_state(js: JsRuntime):
    for name in STATE_NAMES:
        report = js.push(state_payload(name))
        named = [one["fault"] for one in report["faults"]]
        assert "not-css" not in named, f"{name} raised {named}"


def test_the_module_paints_no_row_style_without_the_sheet_reader(js: JsRuntime):
    bare = JsRuntime.__new__(JsRuntime)
    engine = js.engine_of()
    engine.evaluate("var window = this;")
    engine.evaluate(MODULE_SOURCE, MODULE_PATH.name)
    bare._engine = engine
    assert bare.json("typeof acervatorSetLiveStatus") == "function"
    assert bare.style_of(state_payload("filled")["rows"][0][ROW_STYLE]) == {}
    assert bare.declarations(state_payload("filled")["rows"][0][ROW_STYLE]) == []


def test_the_sheet_reader_check_paints_a_style_with_the_reader_loaded(js: JsRuntime):
    js.load_tokens()
    js.load_widgets()
    painted = js.style_of(state_payload("filled")["rows"][0][ROW_STYLE])
    assert str(ds.SUCCESS) in painted["color"]


# -- 4. the tab, drawn in the real page ---------------------------------


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

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
        """Spin until the page defines acervatorSetLiveStatus, which
        loadFinished can precede."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetLiveStatus") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the tab module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
            + ", header "
            + str(self.js("typeof window.acervatorHeader"))
            + ", widgets "
            + str(self.js("typeof window.acervatorSetWidgets"))
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


#: Every computed property read off every drawn part.
STYLE_NAMES = [
    "display",
    "flexDirection",
    "gridTemplateColumns",
    "rowGap",
    "columnGap",
    "flexGrow",
    "flexBasis",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "marginLeft",
    "marginTop",
    "marginRight",
    "marginBottom",
    "color",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "whiteSpace",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
]

#: A Qt shorthand and the computed properties it settles into.
EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "margin": ("marginLeft", "marginTop", "marginRight", "marginBottom"),
    "background": ("backgroundColor",),
    "font-size": ("fontSize",),
    "font-weight": ("fontWeight",),
    "color": ("color",),
}

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

#: A view never shown reads clientWidth as 0, so the host is given a width.
PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = " + json.dumps(str(HOST_WIDTH_PX) + "px") + ";"
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
    "        hidden: el.hidden, text: own,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)

TAB_PATH = "tab"
GROUP_PATH = "tab/stats-group"
TITLE_PATH = "tab/stats-group/group-title"
FORM_PATH = "tab/stats-group/form"
ROW_PATH = "tab/stats-group/form/row"
ROW_LABEL_PATH = "tab/stats-group/form/row/row-label"
ROW_VALUE_PATH = "tab/stats-group/form/row/row-value"
STRETCH_PATH = "tab/stretch"


def give_tokens(browser: Browser) -> int:
    """Put token_payload on the page and write each token into the
    documentElement style."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_tab(browser: Browser, payload: dict) -> list:
    """Draw the tab into the page and read every part back."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetLiveStatus(JSON.parse(window.PAYLOAD));"
        "acervatorLiveStatus.renderTab(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    """Read every drawn part again without redrawing."""
    return json.loads(browser.js(READ_PARTS))


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


def plain_probe(browser: Browser) -> dict:
    """What probeStyle computes for an element with no cssText at all."""
    return browser.parsed(
        "window.probeStyle(" + json.dumps("") + ", " + json.dumps(STYLE_NAMES) + ")"
    )


def pixels(value: Any) -> str:
    """One value as the px length getComputedStyle reports."""
    return str(value) + "px"


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def by_key(parts: list, path: str) -> dict:
    """Every part at ``path``, keyed on the row label it was drawn with."""
    return {one["attrs"].get("data-key"): one for one in at_path(parts, path)}


def sheet_agrees(drawn: dict, expected: dict, where: str) -> None:
    differing = {
        name: (value, drawn["style"].get(name))
        for name, value in expected.items()
        if drawn["style"].get(name) != value
    }
    assert not differing, (
        f"{where}: {len(differing)} of {len(expected)} declared values "
        f"differ from the surface's own: {differing}"
    )


def changed_parts(before: list, after: list) -> set:
    """Every (key, property) whose computed value moved between reads."""
    assert len(before) == len(after), "the tab drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        name = one["attrs"].get("data-key", one["path"])
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((name, key))
    return moved


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorLiveStatus") == "object"
    assert browser.js("typeof window.acervatorSetLiveStatus") == "function"
    assert browser.js("typeof window.acervatorLoadLiveStatus") == "function"


def test_the_policy_refuses_a_network_call_from_the_loaded_page(browser: Browser):
    browser.js(
        WATCH_VIOLATIONS + "window.PROBE = 'pending';"
        "fetch('https://example.invalid/x')"
        "  .then(function () { window.PROBE = 'allowed'; })"
        "  .catch(function (e) { window.PROBE = 'refused: ' + e.name; });"
    )
    browser.settle(NETWORK_SETTLE_MS)
    assert browser.js("window.PROBE") == "refused: TypeError"
    violations = browser.parsed("window.VIOLATIONS")
    assert any(v.startswith("connect-src") for v in violations), violations


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_tab(browser, state_payload("filled"))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_every_child_a_check_reads_carries_a_name(browser: Browser):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    drawn = sorted({one["path"] for one in parts})
    assert drawn == sorted(
        {
            TAB_PATH,
            GROUP_PATH,
            TITLE_PATH,
            FORM_PATH,
            ROW_PATH,
            ROW_LABEL_PATH,
            ROW_VALUE_PATH,
            STRETCH_PATH,
        }
    ), f"the tab drew {drawn}"
    named = (
        at_path(parts, ROW_PATH)
        + at_path(parts, ROW_LABEL_PATH)
        + at_path(parts, ROW_VALUE_PATH)
    )
    assert len(named) == len(payload["rows"]) * 3
    for one in named:
        assert one["attrs"].get("data-key"), f"a row part carries no name: {one}"


def test_the_named_child_check_reports_a_part_that_lost_its_name(browser: Browser):
    payload = state_payload("filled")
    payload["rows"][0][ROW_LABEL] = None
    parts = draw_tab(browser, payload)
    unnamed = [
        one for one in at_path(parts, ROW_PATH) if not one["attrs"].get("data-key")
    ]
    assert len(unnamed) == 1, f"the check named {len(unnamed)} unnamed rows"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_drawn_tab_shows_every_money_figure_the_surface_published(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    labels = by_key(parts, ROW_LABEL_PATH)
    values = by_key(parts, ROW_VALUE_PATH)
    assert len(values) == len(payload["rows"])
    for one in payload["rows"]:
        assert values[one[ROW_LABEL]]["text"] == one[ROW_TEXT]
        assert labels[one[ROW_LABEL]]["text"] == one[ROW_LABEL]


def test_markup_in_a_money_text_draws_as_text_and_builds_no_element(
    browser: Browser,
):
    payload = state_payload("filled")
    payload["rows"][0][ROW_TEXT] = MARKUP_TEXT
    parts = draw_tab(browser, payload)
    drawn = by_key(parts, ROW_VALUE_PATH)[payload["rows"][0][ROW_LABEL]]
    assert drawn["text"] == MARKUP_TEXT
    assert (
        browser.js("window.HOST.getElementsByTagName(" + json.dumps("b") + ").length")
        == 0
    )


def test_the_markup_check_counts_an_element_the_page_really_built(
    browser: Browser,
):
    draw_tab(browser, state_payload("filled"))
    assert (
        browser.js(
            "(function () {"
            "  var made = document.createElement('b');"
            "  window.HOST.appendChild(made);"
            "  var found = window.HOST.getElementsByTagName('b').length;"
            "  made.remove();"
            "  return found; })()"
        )
        == 1
    )


def test_the_money_figure_check_names_one_changed_text(browser: Browser):
    payload = state_payload("filled")
    payload["rows"][0][ROW_TEXT] += "0"
    parts = draw_tab(browser, payload)
    shown = [one["text"] for one in at_path(parts, ROW_VALUE_PATH)]
    original = values_of(state_payload("filled"))
    differing = [at for at, one in enumerate(original) if shown[at] != one]
    assert differing == [0], f"the check named {differing}"


def test_the_drawn_tooltip_is_the_note_the_surface_wrote(browser: Browser):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    values = by_key(parts, ROW_VALUE_PATH)
    for one in payload["rows"]:
        drawn = values[one[ROW_LABEL]]["attrs"].get("title")
        assert drawn == (one[ROW_TOOLTIP] or None), one[ROW_LABEL]
    assert any(one[ROW_TOOLTIP] for one in payload["rows"])


def test_the_drawn_row_values_match_the_surface_s_own_style_sheets(browser: Browser):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    values = by_key(parts, ROW_VALUE_PATH)
    styled = [one for one in payload["rows"] if one[ROW_STYLE]]
    assert styled, "no row carries a style sheet; the check cannot report"
    for one in styled:
        sheet_agrees(
            values[one[ROW_LABEL]],
            probe(browser, base_body(one[ROW_STYLE])),
            "value " + one[ROW_LABEL],
        )


def test_the_style_sheet_check_names_one_changed_colour(browser: Browser):
    payload = state_payload("filled")
    original = payload["rows"][0][ROW_STYLE]
    payload["rows"][0][ROW_STYLE] = original.replace(str(ds.SUCCESS), str(ds.ERROR))
    parts = draw_tab(browser, payload)
    drawn = by_key(parts, ROW_VALUE_PATH)[payload["rows"][0][ROW_LABEL]]
    expected = probe(browser, base_body(original))
    differing = sorted(
        name for name, value in expected.items() if drawn["style"].get(name) != value
    )
    assert differing == ["color"], f"the check named {differing}"


def test_a_row_with_no_style_sheet_takes_no_colour_of_the_module_s_own(
    browser: Browser,
):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    plain = plain_probe(browser)
    values = by_key(parts, ROW_VALUE_PATH)
    bare = [one for one in payload["rows"] if not one[ROW_STYLE]]
    assert bare, "every row carries a style sheet; the check cannot report"
    for one in bare:
        drawn = values[one[ROW_LABEL]]["style"]
        for name in ("color", "backgroundColor", "fontSize", "fontWeight"):
            assert drawn[name] == plain[name], f"{one[ROW_LABEL]} {name}"


def test_the_drawn_form_carries_the_spacing_the_qt_host_sets(browser: Browser):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    form = only(parts, FORM_PATH)["style"]
    held = payload["stats_form"]
    assert form["columnGap"] == pixels(held["horizontal_spacing_px"])
    assert form["rowGap"] == pixels(held["vertical_spacing_px"])
    sides = ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom")
    for at, side in enumerate(sides):
        assert form[side] == pixels(held["margins_px"][at]), side


def test_the_form_spacing_check_names_one_changed_number(browser: Browser):
    payload = state_payload("filled")
    original = payload["stats_form"]["horizontal_spacing_px"]
    payload["stats_form"]["horizontal_spacing_px"] = original + original
    parts = draw_tab(browser, payload)
    assert only(parts, FORM_PATH)["style"]["columnGap"] == pixels(original + original)


def test_the_drawn_form_lines_every_label_up_in_one_column(browser: Browser):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    form = only(parts, FORM_PATH)["style"]
    assert form["display"] == "grid"
    assert len(form["gridTemplateColumns"].split()) == 2, form["gridTemplateColumns"]
    lefts = browser.parsed(
        "Array.prototype.slice.call("
        "  window.HOST.querySelectorAll('[data-part=\"row-label\"]')"
        ").map(function (el) { return el.getBoundingClientRect().left; })"
    )
    assert len(lefts) == len(payload["rows"])
    assert len(set(lefts)) == 1, f"the labels start at {sorted(set(lefts))}"


def test_the_column_check_reads_ragged_labels_as_ragged(browser: Browser):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    assert only(parts, FORM_PATH)["style"]["display"] == "grid"
    ragged = browser.parsed(
        "(function () {"
        "  var form = window.HOST.querySelector('[data-part=\"form\"]');"
        "  form.style.display = 'block';"
        "  var found = Array.prototype.slice.call("
        "    window.HOST.querySelectorAll('[data-part=\"row-value\"]')"
        "  ).map(function (el) { return el.getBoundingClientRect().left; });"
        "  form.style.display = 'grid';"
        "  return found; })()"
    )
    assert len(set(ragged)) > 1, f"every value still starts at {sorted(set(ragged))}"


def test_the_drawn_value_column_takes_the_width_left_over(browser: Browser):
    payload = state_payload("filled")
    assert payload["stats_form"]["field_grows"] is True
    parts = draw_tab(browser, payload)
    assert only(parts, FORM_PATH)["attrs"]["data-field-grows"] == "true"
    widths = browser.parsed(
        "(function () {"
        "  var form = window.HOST.querySelector('[data-part=\"form\"]');"
        "  var label = window.HOST.querySelector('[data-part=\"row-label\"]');"
        "  var value = window.HOST.querySelector('[data-part=\"row-value\"]');"
        "  return [form.getBoundingClientRect().width,"
        "          label.getBoundingClientRect().width,"
        "          value.getBoundingClientRect().width]; })()"
    )
    form_width, label_width, value_width = widths
    gap = payload["stats_form"]["horizontal_spacing_px"]
    margins = payload["stats_form"]["margins_px"]
    inner = form_width - margins[0] - margins[2]
    assert value_width == pytest.approx(inner - label_width - gap, abs=1.0), widths


def test_the_growing_column_check_reads_a_natural_column_apart(browser: Browser):
    payload = state_payload("filled")
    payload["stats_form"]["field_grows"] = False
    parts = draw_tab(browser, payload)
    assert only(parts, FORM_PATH)["attrs"]["data-field-grows"] == "false"
    width = browser.js(
        "window.HOST.querySelector('[data-part=\"row-value\"]')"
        ".getBoundingClientRect().width"
    )
    assert width < HOST_WIDTH_PX / 2, width


def test_the_drawn_labels_stay_on_one_line_as_the_host_asks(browser: Browser):
    payload = state_payload("filled")
    assert payload["stats_form"]["rows_wrap"] is False
    parts = draw_tab(browser, payload)
    assert only(parts, FORM_PATH)["attrs"]["data-rows-wrap"] == "false"
    for one in at_path(parts, ROW_LABEL_PATH):
        assert one["style"]["whiteSpace"] == "nowrap", one["attrs"].get("data-key")


def test_the_one_line_label_check_reads_a_wrapping_label_apart(browser: Browser):
    payload = state_payload("filled")
    payload["stats_form"]["rows_wrap"] = True
    parts = draw_tab(browser, payload)
    wrapped = {one["style"]["whiteSpace"] for one in at_path(parts, ROW_LABEL_PATH)}
    assert wrapped == {"normal"}, wrapped


#: Long enough to overrun any pane, and spaced so it can wrap.
OVERLONG_TEXT = ("venue refused the order " * 40).strip()


def form_overruns_host(browser: Browser, wraps: bool) -> list:
    """Draw one overlong value and report the form and host widths."""
    payload = state_payload("filled")
    payload["rows"][0][ROW_TEXT] = OVERLONG_TEXT
    payload["rows"][0][ROW_WRAP] = wraps
    draw_tab(browser, payload)
    return browser.parsed(
        "(function () {"
        "  var form = window.HOST.querySelector('[data-part=\"form\"]');"
        "  return [form.scrollWidth, window.HOST.clientWidth]; })()"
    )


def test_a_wrapping_value_never_runs_off_the_pane_sideways(browser: Browser):
    form_width, host_width = form_overruns_host(browser, True)
    assert form_width <= host_width, (form_width, host_width)


def test_a_value_that_does_not_wrap_runs_off_the_pane_as_qt_lets_it(
    browser: Browser,
):
    form_width, host_width = form_overruns_host(browser, False)
    assert form_width > host_width, (form_width, host_width)


def test_the_drawn_word_wrap_follows_the_flag_the_surface_published(browser: Browser):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    values = by_key(parts, ROW_VALUE_PATH)
    wrapped = {one[ROW_LABEL] for one in payload["rows"] if one[ROW_WRAP]}
    assert wrapped == {payload["labels"]["last_error"]}, f"wrapping {wrapped}"
    for one in payload["rows"]:
        want = "normal" if one[ROW_WRAP] else "nowrap"
        assert values[one[ROW_LABEL]]["style"]["whiteSpace"] == want, one[ROW_LABEL]


def test_the_drawn_layout_matches_the_gap_the_surface_publishes(browser: Browser):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    tab = only(parts, TAB_PATH)
    assert tab["style"]["rowGap"] == pixels(payload["container"]["spacing_px"])
    assert (
        tab["attrs"]["data-margins-set"]
        == str(payload["container"]["margins_set"]).lower()
    )
    for side in ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"):
        assert tab["style"][side] == pixels(0), side


def test_the_layout_check_names_one_changed_gap(browser: Browser):
    payload = state_payload("filled")
    original = payload["container"]["spacing_px"]
    payload["container"]["spacing_px"] = original + original
    parts = draw_tab(browser, payload)
    assert only(parts, TAB_PATH)["style"]["rowGap"] == pixels(original + original)


def test_the_drawn_group_carries_the_title_the_surface_published(browser: Browser):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    group = only(parts, GROUP_PATH)
    assert group["hidden"] is False
    assert group["attrs"]["aria-label"] == payload["stats_group"]["title"]
    assert only(parts, TITLE_PATH)["text"] == payload["stats_group"]["title"]
    form = only(parts, FORM_PATH)
    assert form["attrs"]["data-declared-rows"] == str(payload["row_count"])
    assert form["attrs"]["data-held-rows"] == str(len(payload["rows"]))


def test_an_unbuilt_tab_hides_the_group_and_the_stretch(browser: Browser):
    payload = state_payload("empty")
    assert payload["stats_group"]["shown"] is False
    parts = draw_tab(browser, payload)
    assert only(parts, GROUP_PATH)["hidden"] is True
    assert only(parts, STRETCH_PATH)["hidden"] is True
    assert at_path(parts, ROW_PATH) == []


def test_the_hidden_group_check_reads_a_built_tab_as_shown(browser: Browser):
    parts = draw_tab(browser, state_payload("filled"))
    assert only(parts, GROUP_PATH)["hidden"] is False
    assert only(parts, STRETCH_PATH)["hidden"] is False


def test_the_drawn_tab_follows_a_colour_token_and_nothing_else_moves(
    browser: Browser,
):
    payload = state_payload("filled")
    before = draw_tab(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty('--SUCCESS', "
        + json.dumps(str(ds.ERROR))
        + ");"
    )
    moved = changed_parts(before, read_parts(browser))
    assert moved, "the token moved nothing at all"
    assert {key for _, key in moved} == {
        "color",
        "borderTopColor",
    }, f"an unset border colour is currentColor, so only these move: {moved}"
    assert {name for name, _ in moved} == {
        payload["labels"]["realised"]
    }, f"the token moved {sorted({n for n, _ in moved})}"


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(browser: Browser):
    before = draw_tab(browser, state_payload("filled"))
    assert changed_parts(before, read_parts(browser)) == set()


def test_a_token_no_row_carries_moves_nothing_on_the_drawn_tab(browser: Browser):
    before = draw_tab(browser, state_payload("filled"))
    browser.js(
        "document.documentElement.style.setProperty('--PRIMARY', "
        + json.dumps(str(ds.ERROR))
        + ");"
    )
    assert changed_parts(before, read_parts(browser)) == set()


# -- 5. row order and row identity --------------------------------------


def test_the_drawn_tab_places_every_row_in_the_order_the_surface_names(
    browser: Browser,
):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, ROW_PATH)]
    assert drawn == labels_of(payload), f"the tab drew {drawn}"


def test_the_row_order_check_names_a_reordered_list(browser: Browser):
    payload = state_payload("filled")
    rows = payload["rows"]
    rows[1], rows[2] = rows[2], rows[1]
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, ROW_PATH)]
    assert drawn == labels_of(payload)
    assert drawn != labels_of(state_payload("filled"))


def test_the_row_identity_check_names_two_swapped_values(browser: Browser):
    payload = state_payload("filled")
    rows = payload["rows"]
    rows[0][ROW_TEXT], rows[1][ROW_TEXT] = rows[1][ROW_TEXT], rows[0][ROW_TEXT]
    parts = draw_tab(browser, payload)
    values = by_key(parts, ROW_VALUE_PATH)
    shipped = state_payload("filled")
    differing = sorted(
        one[ROW_LABEL]
        for one in shipped["rows"]
        if values[one[ROW_LABEL]]["text"] != one[ROW_TEXT]
    )
    assert differing == sorted(
        [shipped["rows"][0][ROW_LABEL], shipped["rows"][1][ROW_LABEL]]
    ), f"the check named {differing}"


def test_the_row_identity_check_is_quiet_on_the_shipped_order(browser: Browser):
    shipped = state_payload("filled")
    parts = draw_tab(browser, shipped)
    values = by_key(parts, ROW_VALUE_PATH)
    differing = [
        one[ROW_LABEL]
        for one in shipped["rows"]
        if values[one[ROW_LABEL]]["text"] != one[ROW_TEXT]
    ]
    assert differing == []


def test_two_rows_under_one_label_are_both_drawn(browser: Browser):
    payload = state_payload("filled")
    payload["rows"][1][ROW_LABEL] = payload["rows"][0][ROW_LABEL]
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, ROW_PATH)]
    assert len(drawn) == len(payload["rows"])
    assert drawn.count(payload["rows"][0][ROW_LABEL]) == 2


# -- 6. hostile payloads -------------------------------------------------

HOSTILE_MONEY = {
    "a true flag": True,
    "not a number": math.nan,
    "an infinity": math.inf,
    "a very large integer": 10**24,
    "text where a number belongs": "1234.5",
    "nothing at all": None,
}


@pytest.mark.parametrize("case", sorted(HOSTILE_MONEY))
def test_the_tab_shows_whatever_money_text_the_surface_produced(
    js: JsRuntime, case: str
):
    payload = bridge_payload(bot=bot_spec(realised=HOSTILE_MONEY[case]))
    js.push(payload)
    label = payload["labels"]["realised"]
    shown = js.named("row", label)["text"]
    assert shown == payload["rows"][0][ROW_TEXT], f"{case}: the tab shows {shown}"


def test_the_money_check_reads_a_different_text_for_a_different_amount(js: JsRuntime):
    label = state_payload("filled")["labels"]["realised"]
    js.push(bridge_payload(bot=bot_spec(realised=1.0)))
    one = js.named("row", label)["text"]
    js.push(bridge_payload(bot=bot_spec(realised=2.0)))
    assert js.named("row", label)["text"] != one


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_field_the_payload_omits_is_named_as_missing(js: JsRuntime, field: str):
    payload = state_payload("filled")
    del payload[field]
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"]
    assert report["held"]["fields"] == len(MODULE_READERS) - 1


@pytest.mark.parametrize("field", sorted(set(MODULE_READERS) - {"no_stats"}))
def test_a_field_carrying_null_is_named(js: JsRuntime, field: str):
    payload = state_payload("filled")
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_the_field_the_surface_publishes_as_null_raises_no_fault(js: JsRuntime):
    payload = state_payload("filled")
    assert payload["no_stats"] is None
    report = js.push(payload)
    named = [one["field"] for one in report["faults"] if one["fault"] == "null"]
    assert named == [], f"the check named {named}"
    assert js.json("acervatorLiveStatus.noStats()") is None


def test_the_missing_field_check_is_quiet_on_every_shipped_state(js: JsRuntime):
    for name in STATE_NAMES:
        report = js.push(state_payload(name))
        kinds = [one["fault"] for one in report["faults"]]
        assert "missing" not in kinds, f"{name} raised {kinds}"
        assert "null" not in kinds, f"{name} raised {kinds}"


@pytest.mark.parametrize(
    "cell,at",
    [("text", ROW_TEXT), ("style_sheet", ROW_STYLE), ("tooltip", ROW_TOOLTIP)],
)
def test_a_row_text_that_is_a_number_is_named_against_its_own_default(
    js: JsRuntime, cell: str, at: int
):
    payload = state_payload("filled")
    payload["rows"][0][at] = 12.5
    report = js.push(payload)
    assert {
        "where": "row:0",
        "field": cell,
        "fault": "wrong-type",
        "detail": "number",
    } in report["faults"]


def test_a_row_word_wrap_that_is_a_number_is_named_against_its_own_default(
    js: JsRuntime,
):
    payload = state_payload("filled")
    payload["rows"][0][ROW_WRAP] = 1
    report = js.push(payload)
    assert {
        "where": "row:0",
        "field": "word_wrap",
        "fault": "wrong-type",
        "detail": "number",
    } in report["faults"]


def test_a_row_label_that_is_a_number_raises_no_wrong_type_fault(js: JsRuntime):
    payload = state_payload("filled")
    payload["rows"][0][ROW_LABEL] = 7
    js.push(payload)
    named = [
        one
        for one in js.json("acervatorLiveStatus.faults()")
        if one["fault"] == "wrong-type"
    ]
    assert named == [], f"the check named {named}"
    assert js.json("acervatorLiveStatus.kinds()")["rows.0.0"] == "number"


def test_a_row_label_the_surface_never_published_is_named(js: JsRuntime):
    payload = state_payload("filled")
    payload["rows"][0][ROW_LABEL] = LONG_TEXT
    report = js.push(payload)
    assert {
        "where": "row:0",
        "field": "label",
        "fault": "unnamed",
        "detail": LONG_TEXT,
    } in report["faults"]


def test_the_unnamed_label_check_is_quiet_on_every_shipped_state(js: JsRuntime):
    for name in STATE_NAMES:
        report = js.push(state_payload(name))
        kinds = [one["fault"] for one in report["faults"]]
        assert "unnamed" not in kinds, f"{name} raised {kinds}"


def test_a_row_count_that_disagrees_with_the_rows_is_named(js: JsRuntime):
    payload = state_payload("filled")
    payload["rows"].pop()
    report = js.push(payload)
    assert {
        "where": "rows",
        "field": "row_count",
        "fault": "short-list",
        "detail": len(payload["rows"]),
    } in report["faults"]


def test_the_row_count_check_is_quiet_on_every_shipped_state(js: JsRuntime):
    for name in STATE_NAMES:
        report = js.push(state_payload(name))
        kinds = [one["fault"] for one in report["faults"]]
        assert "short-list" not in kinds, f"{name} raised {kinds}"


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorLiveStatus.isLoaded()") is False
        assert js.json("acervatorLiveStatus.rows()") == []
        assert report["declared"] is None
        assert report["held"] is None
        assert [one["fault"] for one in report["faults"]] == ["not-an-object"]


#: One row of the shipped payload, replaced by something it is not.
BAD_ROWS = {
    "nothing at all": None,
    "a number": 7,
    "a text": "not a row",
    "an empty list": [],
    "a short list": ["Uptime:", "9s"],
    "a bag": {"label": "Uptime:"},
    "markup": [MARKUP_TEXT, MARKUP_TEXT, "", "", False],
    "a two hundred character label": [LONG_TEXT, LONG_TEXT, "", "", False],
}


@pytest.mark.parametrize("case", sorted(BAD_ROWS))
def test_one_bad_row_costs_the_other_rows_nothing(browser: Browser, case: str):
    payload = state_payload("filled")
    shipped = len(payload["rows"])
    payload["rows"][2] = BAD_ROWS[case]
    parts = draw_tab(browser, payload)
    drawn = at_path(parts, ROW_PATH)
    kept = [one for one in payload["rows"] if isinstance(one, list)]
    assert len(drawn) == len(kept), f"{case}: {len(drawn)} of {shipped} rows drawn"
    assert only(parts, GROUP_PATH)["hidden"] is False


def test_the_surviving_row_check_counts_every_row_of_a_whole_payload(
    browser: Browser,
):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    assert len(at_path(parts, ROW_PATH)) == len(payload["rows"])


@pytest.mark.parametrize("case", sorted(BAD_ROWS))
def test_one_bad_row_is_named_rather_than_drawn_silently(js: JsRuntime, case: str):
    payload = state_payload("filled")
    payload["rows"][2] = BAD_ROWS[case]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["where"] == "row:2"]
    assert named, f"{case} raised no fault: {report['faults']}"


# -- 7. the bridge ask ---------------------------------------------------


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("filled"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadLiveStatus();")
    drain_events()
    assert js.json("window.CALLS") == [[lst.METHOD, "{}"]]
    assert js.json("acervatorLiveStatus.isLoaded()") is True


def test_the_module_passes_a_caller_s_parameters_to_the_surface(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("empty"))
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", {"reset": True})
    js.run("acervatorLoadLiveStatus(JSON.parse(WANTED));")
    drain_events()
    assert js.json("window.CALLS") == [[lst.METHOD, '{"reset":true}']]


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("filled"))
    js.run(BRIDGE_STUB)
    js.run(
        "acervatorLoadLiveStatus();"
        "acervatorLoadLiveStatus();"
        "acervatorLoadLiveStatus();"
    )
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("filled"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadLiveStatus();")
    drain_events()
    js.run("acervatorLiveStatus.forget(); acervatorLoadLiveStatus();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadLiveStatus();")
    drain_events()
    assert js.json("acervatorLiveStatus.isLoaded()") is False
    assert (
        js.json("acervatorLiveStatus.loadError()")
        == "the preload bridge is not present"
    )


def test_a_refused_ask_is_not_remembered(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("filled"))
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadLiveStatus();"
    )
    drain_events()
    assert js.json("acervatorLiveStatus.isLoaded()") is False
    assert (
        js.json("acervatorLiveStatus.loadError()")
        == "the Python backend is not running"
    )
    js.run("acervatorLoadLiveStatus();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorLiveStatus.isLoaded()") is True


def test_the_page_names_the_tab_module_among_its_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("live_status_tab.js")]
    assert len(named) == 1, f"the page names {len(named)} tab modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


def test_the_page_loads_the_sheet_reader_before_the_tab_module():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    assert refs.index("../../src/gui/web/header_strip.js") < refs.index(
        "../../src/gui/web/live_status_tab.js"
    )


# -- 8. what the bridge can and cannot carry -----------------------------


def strict_parse(text: str) -> Any:
    """Parse ``text`` the way ``JSON.parse`` does, refusing NaN."""

    def refuse(name: str) -> Any:
        raise ValueError("the frame carries " + name)

    return json.loads(text, parse_constant=refuse)


@pytest.mark.parametrize("case", sorted(HOSTILE_MONEY))
def test_no_state_of_this_surface_writes_a_frame_json_parse_would_refuse(case: str):
    model = lst.view_model(
        {"reset": True, "now": FIXED_NOW, "bot": bot_spec(realised=HOSTILE_MONEY[case])}
    )
    frame = json.dumps(model, ensure_ascii=True)
    assert strict_parse(frame) == json.loads(frame)


def test_the_frame_check_refuses_a_frame_carrying_a_not_a_number():
    with pytest.raises(ValueError):
        strict_parse(json.dumps({"realised": math.nan}))
    with pytest.raises(ValueError):
        strict_parse(json.dumps({"realised": math.inf}))


def test_a_not_a_number_reaches_the_tab_as_the_text_the_surface_wrote(js: JsRuntime):
    payload = bridge_payload(bot=bot_spec(realised=math.nan))
    js.push(payload)
    row = js.named("row", payload["labels"]["realised"])
    assert row["text"] == payload["rows"][0][ROW_TEXT]
    assert str(ds.ERROR) in row["style_sheet"]
    assert "nan" in row["text"]


def test_a_true_flag_reaches_the_tab_as_a_dollar_of_money(js: JsRuntime):
    payload = bridge_payload(bot=bot_spec(realised=True))
    js.push(payload)
    row = js.named("row", payload["labels"]["realised"])
    assert row["text"] == payload["rows"][0][ROW_TEXT]
    assert row["text"] == "$+1.0000"
