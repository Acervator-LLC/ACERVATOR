"""Drives `bot_status_table.js` against `bot_status_table_surface.py`."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.core.privacy_mask_registry import get_privacy_mask_registry
from src.gui.main_tabs import bot_status_table_surface as bsts
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import swap_module

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "bot_status_table.js"
TOKENS_PATH = WEB / "design_tokens.js"
THEMES_PATH = WEB / "theme_engine.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
CELLS_PATH = WEB / "table_cells.js"
HEADER_PATH = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: MODULE_TAIL is the closing line a whole module file ends with.
MODULE_TAIL = "})(window);"

MODULE_READ_ATTEMPTS = 200
#: A pause between reads, so retrying does not hold MODULE_PATH open
#: against the os.replace in another worker.
MODULE_READ_PAUSE_S = 0.01


def read_module() -> str:
    """Return MODULE_PATH text ending with MODULE_TAIL, retrying while not."""
    for _ in range(MODULE_READ_ATTEMPTS):
        found = MODULE_PATH.read_text(encoding="utf-8")
        if found.rstrip().endswith(MODULE_TAIL):
            return found
        time.sleep(MODULE_READ_PAUSE_S)
    raise AssertionError(MODULE_PATH.name + " never read back whole")


#: MODULE_SOURCE is read at collection, before any test body writes.
MODULE_SOURCE = read_module()

JS_TIMEOUT_MS = 30_000
EVENT_DRAIN_ROUNDS = 20
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500
READY_ROUNDS = 100
READY_STEP_MS = 100

#: HOST_WIDTH_PX is set because an unshown view reads ``clientWidth`` as zero.
HOST_WIDTH_PX = 1400
VIEW_SIZE_PX = (1400, 900)

HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")

#: JS_TYPE_OF maps a Python type name to its type after ``json.dumps``.
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

PRIVACY_FIELDS = tuple(sorted(set(bsts.PRIVACY_FIELD_BY_COL.values())))

#: `NAMED_VALUE` is the bridge method the module asks on, not a
#: painted value.
NAMED_VALUE = bsts.METHOD

#: NAMED_SUB_KEYS holds the row, cell, button and header key names.
NAMED_SUB_KEYS = {
    "bot_id",
    "cell_clicked",
    "cells",
    "chart_url",
    "color",
    "detail",
    "detail_clicked",
    "enabled",
    "field_id",
    "fire",
    "fire_clicked",
    "glow",
    "glow_blur_radius",
    "glow_offset",
    "header_clicked",
    "height",
    "icon_asset",
    "icon_size",
    "path",
    "skipped",
    "style_sheet",
    "text",
    "tooltip",
    "underline",
}


# -- the bot statuses the surface is driven with -----------------------


def scrumming(bot_id: str, symbol: str, **extra: Any) -> dict:
    """One scrumming bot status, as the engine reports it."""
    found = {
        "bot_id": bot_id,
        "symbol": symbol,
        "mode": bsts.MODE_SCRUMMING,
        "state": "running",
        "exchange": "coinbase",
        "target_balance": 1000.0,
        "current_holdings": 0.02,
        "stats": {
            "total_trades": 12,
            "current_price": 60000.0,
            "position_value": 1200.0,
        },
    }
    found.update(extra)
    return found


#: FIRE_RECIPES holds one status per Fire path ``update_bots`` reaches.
FIRE_RECIPES = {
    "scrum_armed": {"armed_action": "scrum", "auto_fire": {"scrum_armed": True}},
    "scrum_override": {
        "armed_action": "scrum",
        "auto_fire": {"scrum_armed": False, "scrum_blockers": ["rsi", "bb"]},
    },
    "fold_ceiling": {
        "armed_action": "fold",
        "position_ceiling_enabled": True,
        "ceiling_ratio": 1.2,
        "position_ceiling_usd": 5000.0,
        "auto_fire": {"fold_armed": True},
    },
    "fold_armed": {"armed_action": "fold", "auto_fire": {"fold_armed": True}},
    "fold_override": {
        "armed_action": "fold",
        "auto_fire": {"fold_armed": False, "fold_blockers": ["htf"]},
    },
    "phase_fire": {"scrum_target_mode": "fire"},
    "phase_track": {"scrum_target_mode": "track"},
    "phase_search": {},
    "inactive": {"state": "stopped"},
}

PATH_STATUSES = [
    scrumming(name, "BTC/USD", **extra) for name, extra in sorted(FIRE_RECIPES.items())
]

TWO_BOTS = [
    scrumming("alpha-one", "BTC/USD", **FIRE_RECIPES["scrum_armed"]),
    scrumming("beta-two", "ETH/USD", state="paused", **FIRE_RECIPES["fold_armed"]),
]

THREE_BOTS = TWO_BOTS + [
    scrumming("gamma-three", "SOL/USD", **FIRE_RECIPES["phase_track"])
]

MIXED_STATUSES = [
    TWO_BOTS[0],
    {
        "bot_id": "delta-extractor",
        "symbol": "DOGE/USD",
        "mode": "extractor",
        "state": "running",
        "stats": {},
    },
    TWO_BOTS[1],
]

#: STATES holds each published state as a reset plus the calls a click makes.
STATES = {
    "empty": (),
    "one": ({"statuses": [TWO_BOTS[0]]},),
    "paths": ({"statuses": PATH_STATUSES},),
    "skipped": ({"statuses": MIXED_STATUSES},),
    "masked": ({"statuses": TWO_BOTS}, {"header_click": 0}),
    "selected": ({"statuses": TWO_BOTS}, {"detail": "beta-two"}),
    "fired": ({"statuses": TWO_BOTS}, {"fire": "alpha-one"}),
    "charted": ({"statuses": TWO_BOTS}, {"cell_click": [0, bsts.SYMBOL_COLUMN]}),
}
STATE_NAMES = tuple(STATES)


# -- the surface, as the bridge serialises it --------------------------


def bridge_payload(*calls: dict) -> dict:
    """Return `bsts.view_model` output after a reset and each `calls` entry,
    through `json.dumps`."""
    found = bsts.view_model({"reset": True})
    for params in calls:
        found = bsts.view_model(dict(params))
    return json.loads(json.dumps(found, ensure_ascii=True))


def state_payload(name: str) -> dict:
    return bridge_payload(*STATES[name])


def token_payload() -> dict:
    """Return `dss.view_model` output through the bridge's `json.dumps`."""
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    """Return `tes.view_model` output through the bridge's `json.dumps`."""
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


@pytest.fixture()
def revealed():
    """Unmask every `PRIVACY_FIELDS` entry in the registry and put the prior
    state back after."""
    registry = get_privacy_mask_registry()
    prior = {field: registry.is_masked(field) for field in PRIVACY_FIELDS}
    for field in PRIVACY_FIELDS:
        registry.set_masked(field, False)
    try:
        yield registry
    finally:
        for field, was in prior.items():
            registry.set_masked(field, was)


# -- what the surface publishes, split into names and painted values ---


def walk_payload(node: Any, keys: set, values: set) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            walk_payload(value, keys, values)
        return
    if isinstance(node, list):
        for one in node:
            walk_payload(one, keys, values)
        return
    if isinstance(node, str):
        values.add(node)


def published() -> tuple:
    """Every key name and every string value, over every state."""
    keys: set = set()
    values: set = set()
    for name in STATE_NAMES:
        walk_payload(state_payload(name), keys, values)
    values.discard("")
    keys.discard("")
    return keys, values


def as_css(value: Any) -> set:
    """One token value in every spelling a stylesheet could carry."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {str(value)}
    return set()


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


PUBLISHED_KEYS, PUBLISHED_VALUES = published()
#: PAINTED_VALUES is every published string the table paints, less NAMED_VALUE.
PAINTED_VALUES = PUBLISHED_VALUES - {NAMED_VALUE}
TOKEN_VALUES = token_values()


# -- the JavaScript engine ---------------------------------------------


def js_literals(source: str) -> dict:
    """Return every string, number and stray slash in `source`, tracking
    comments and quotes."""
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


MODULE_LITERALS = js_literals(MODULE_SOURCE)


def drain_events() -> None:
    """Turn the event loop `EVENT_DRAIN_ROUNDS` times so callbacks run."""
    from PySide6.QtCore import QCoreApplication, QEventLoop

    for _ in range(EVENT_DRAIN_ROUNDS):
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)


class JsRuntime:
    """A QJSEngine holding ``bot_status_table.js`` and a ``window`` global."""

    def __init__(self, engine: Any, source: str) -> None:
        self._engine = engine
        engine.evaluate("var window = this;")
        loaded = engine.evaluate(source, MODULE_PATH.name)
        if loaded.isError():
            raise AssertionError(
                MODULE_PATH.name + " did not run: " + loaded.toString()
            )

    def engine_of(self) -> Any:
        """Return a second engine of the same type as `_engine`."""
        return type(self._engine)()

    def run(self, script: str) -> Any:
        result = self._engine.evaluate(script)
        assert not result.isError(), script[:120] + " -> " + result.toString()
        return result

    def json(self, expression: str) -> Any:
        """Evaluate ``expression`` and bring its value back as Python."""
        text = self.run("JSON.stringify(" + expression + ")").toString()
        return None if text == "undefined" else json.loads(text)

    def bind_json(self, name: str, value: Any) -> None:
        """Bind `value` on the engine global `name` as JSON text for a
        caller to parse."""
        self._engine.globalObject().setProperty(name, json.dumps(value))

    def bind_text(self, name: str, written: str) -> None:
        """Set the engine global `name` to `written`, unparsed."""
        self._engine.globalObject().setProperty(name, written)

    def push(self, payload: Any) -> dict:
        self.bind_json("PAYLOAD", payload)
        return self.json("acervatorSetBotTable(JSON.parse(PAYLOAD))")

    def push_written(self, payload: Any, *writes: str) -> dict:
        """Push `payload` after running each `writes` line against it, for
        values JSON cannot spell."""
        self.bind_json("PAYLOAD", payload)
        body = "var P = JSON.parse(PAYLOAD);" + "".join(writes)
        return self.json(
            "(function () { " + body + " return acervatorSetBotTable(P); })()"
        )

    def load_cells(self) -> None:
        """Run the merged modules and push `token_payload` into the engine."""
        for path in (TOKENS_PATH, THEMES_PATH, WIDGETS_PATH, CELLS_PATH, HEADER_PATH):
            self.run(path.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def named(self, call: str, name: Any) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorBotTable." + call + "(JSON.parse(NAME))")

    def at(self, call: str, first: Any, second: Any) -> Any:
        self.bind_json("FIRST", first)
        self.bind_json("SECOND", second)
        return self.json(
            "acervatorBotTable." + call + "(JSON.parse(FIRST), JSON.parse(SECOND))"
        )


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """Return a `JsRuntime` holding `MODULE_SOURCE` in a fresh engine."""
    qtqml = pytest.importorskip("PySide6.QtQml")
    assert qapp is not None
    return JsRuntime(qtqml.QJSEngine(), MODULE_SOURCE)


@pytest.fixture()
def skinned(js: JsRuntime, revealed) -> JsRuntime:
    """Return the `js` runtime after `load_cells` runs the merged modules."""
    assert revealed is not None
    js.load_cells()
    return js


# -- 1. everything the surface publishes reaches the module ------------


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, revealed, state: str
):
    assert revealed is not None
    payload = state_payload(state)
    js.push(payload)
    declared = js.json("acervatorBotTable.declaredNames()")
    missing = sorted(set(payload) - set(declared))
    assert (
        not missing
    ), f"{len(missing)} published fields have no declared name: {missing}"
    extra = sorted(set(declared) - set(payload))
    assert not extra, f"the module declares fields the surface has none of: {extra}"
    assert len(declared) == len(payload)
    differing = {
        name: (payload[name], js.named("field", name))
        for name in declared
        if js.named("field", name) != payload[name]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields "
        f"differ: {sorted(differing)}"
    )


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(
    js: JsRuntime, revealed
):
    assert revealed is not None
    payload = dict(bridge_payload())
    payload["planted_only_on_the_surface"] = []
    js.push(payload)
    declared = js.json("acervatorBotTable.declaredNames()")
    assert sorted(set(payload) - set(declared)) == ["planted_only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_declares(
    js: JsRuntime, revealed
):
    assert revealed is not None
    payload = dict(bridge_payload())
    dropped = payload.pop("rows")
    assert dropped is not None
    js.push(payload)
    declared = js.json("acervatorBotTable.declaredNames()")
    assert sorted(set(declared) - set(payload)) == ["rows"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, revealed, state: str
):
    assert revealed is not None
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == report["held"]["fields"] == len(payload)
    assert report["declared"]["rows"] == report["held"]["rows"] == len(payload["rows"])
    assert report["declared"]["columns"] == report["held"]["columns"]
    assert report["held"]["columns"] == len(payload["columns"])


def test_the_count_check_reports_a_payload_promising_more_rows_than_it_carries(
    js: JsRuntime, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    payload["row_count"] = len(payload["rows"]) + len(payload["rows"])
    report = js.push(payload)
    assert report["declared"]["rows"] != report["held"]["rows"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_raises_no_fault_on_a_payload_the_surface_produced(
    js: JsRuntime, revealed, state: str
):
    assert revealed is not None
    report = js.push(state_payload(state))
    assert report["faults"] == [], f"{state}: {report['faults']}"


# -- 2. no value literal in the JavaScript -----------------------------


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "bot_status_table.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"bot_status_table.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_table_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"bot_status_table.js spells out table values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"bot_status_table.js spells out token values: {written}"


def test_the_one_published_value_the_module_writes_is_the_bridge_method():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_VALUES)
    assert written == [NAMED_VALUE], f"the module writes the values {written}"


def test_the_module_names_only_the_surface_key_names_it_must_read(
    js: JsRuntime, revealed
):
    assert revealed is not None
    js.push(bridge_payload())
    allowed = set(js.json("acervatorBotTable.declaredNames()")) | NAMED_SUB_KEYS
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_KEYS
    assert not written - allowed, f"the module names {sorted(written - allowed)} more"
    assert (
        not NAMED_SUB_KEYS - written
    ), f"the list allows {sorted(NAMED_SUB_KEYS - written)} the module never writes"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "bot_status_table.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


def test_the_alignment_map_covers_exactly_the_word_the_surface_publishes(
    js: JsRuntime, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    js.push(payload)
    words = js.json("acervatorBotTable.alignmentWords()")
    assert words == [payload["alignment"]], f"the module aligns by {words}"


def sample_cell_text(payload: dict) -> str:
    """The Target text of the first row, which is money the table shows."""
    return payload["rows"][0]["cells"][bsts.AMMO_COLUMN]["text"]


SAMPLE_PAYLOAD = bridge_payload({"statuses": TWO_BOTS})

SPELLED_OUT_LINES = {
    "colour": 'var spelled = "#00ffcc";',
    "state_colour": 'var spelled = "' + bsts.STATE_COLORS["running"] + '";',
    "token_value": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "fire_style": 'var spelled = "'
    + bsts.FIRE_STYLES[bsts.FIRE_PATH_SCRUM_SOLID].replace('"', "")
    + '";',
    "glyph": 'var spelled = "' + bsts.REVEALED_GLYPH + '";',
    "money_text": 'var spelled = "' + sample_cell_text(SAMPLE_PAYLOAD) + '";',
    "detail_label": 'var spelled = "' + bsts.DETAIL_LABEL + '";',
    "separator": 'var spelled = "' + bsts.BLOCKERS_SEPARATOR + '";',
    "button_height": "var spelled = " + str(bsts.BUTTON_HEIGHT_PX) + ";",
    "number": "var spelled = 12;",
    "regex": "var spelled = /ab+c/;",
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
    if strings & PAINTED_VALUES:
        caught.add("painted_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(SPELLED_OUT_LINES))
def test_the_literal_scan_names_a_line_that_spells_a_value_out(kind: str):
    caught = caught_by_scan(SPELLED_OUT_LINES[kind])
    assert caught, f"the scan reported nothing on the {kind} line"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_spelled_out_value_is_caught_in_the_module_file_itself():
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
    assert not unrestored, f"the file was not restored after these lines: {unrestored}"
    unseen = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not unseen, f"the scan saw nothing on these lines in the file: {unseen}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_module_read_takes_only_a_file_that_ends_whole():
    assert read_module().rstrip().endswith(MODULE_TAIL)
    for kind, line in sorted(SPELLED_OUT_LINES.items()):
        changed = MODULE_SOURCE + line
        assert not changed.rstrip().endswith(MODULE_TAIL), kind


def test_the_changed_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, line in sorted(SPELLED_OUT_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetBotTable") == "function", kind


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
    js: JsRuntime, revealed, state: str
):
    assert revealed is not None
    payload = state_payload(state)
    js.push(payload)
    wanted = python_kinds(payload)
    found = js.json("acervatorBotTable.kinds()")
    differing = {
        path: (kind, found.get(path))
        for path, kind in wanted.items()
        if found.get(path) != kind
    }
    assert not differing, f"{state}: {len(differing)} values changed type: {differing}"
    assert len(found) == len(wanted)


def test_the_type_check_names_a_value_that_changed_shape(js: JsRuntime, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    wanted = python_kinds(payload)
    payload["rows"][0]["cells"][bsts.AMMO_COLUMN]["text"] = 12.5
    js.push(payload)
    found = js.json("acervatorBotTable.kinds()")
    differing = [path for path, kind in wanted.items() if found.get(path) != kind]
    assert differing == [f"rows.0.cells.{bsts.AMMO_COLUMN}.text"], differing


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_cell_of_every_column_agrees_with_the_surface(
    js: JsRuntime, revealed, state: str
):
    assert revealed is not None
    payload = state_payload(state)
    js.push(payload)
    differing = {}
    for at, row in enumerate(payload["rows"]):
        for column, found in enumerate(row["cells"]):
            held = js.at("cellAt", at, column)
            if held != found:
                differing[f"{at}.{column}"] = (found, held)
    assert not differing, f"{state}: {len(differing)} cells differ: {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_row_s_buttons_agree_with_the_surface(
    js: JsRuntime, revealed, state: str
):
    assert revealed is not None
    payload = state_payload(state)
    js.push(payload)
    for at, row in enumerate(payload["rows"]):
        assert js.named("fire", at) == row["fire"], f"{state}: row {at} fire"
        assert js.named("detail", at) == row["detail"], f"{state}: row {at} detail"


def test_the_cell_check_names_a_column_the_module_read_from_the_wrong_place(
    js: JsRuntime, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    js.push(payload)
    first = js.at("cellAt", 0, 0)
    other = js.at("cellAt", 0, bsts.AMMO_COLUMN)
    assert first != other, "two different columns answered the same cell"


def test_a_reader_returns_nothing_for_an_inherited_javascript_name(
    js: JsRuntime, revealed
):
    assert revealed is not None
    js.push(bridge_payload({"statuses": TWO_BOTS}))
    for name in ("constructor", "toString", "hasOwnProperty", "__proto__"):
        assert js.named("field", name) is None, name
        assert js.named("action", name) is None, name
        assert js.named("stateColour", name) is None, name
        assert js.named("fireStyle", name) is None, name


def test_the_inherited_name_check_still_reads_a_real_field(js: JsRuntime, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    js.push(payload)
    assert js.named("field", "row_count") == payload["row_count"]
    assert js.named("action", "fire_clicked") == payload["actions"]["fire_clicked"]
    assert js.named("stateColour", "running") == payload["state_colors"]["running"]


# -- 4. the table, drawn in the real page ------------------------------


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

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
        """Spin until the page defines `acervatorSetBotTable`, which
        `loadFinished` does not guarantee."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetBotTable") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the table module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
            + ", cells "
            + str(self.js("typeof window.acervatorSetCells"))
            + ", header "
            + str(self.js("typeof window.acervatorSetHeader"))
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


#: STYLE_NAMES lists every computed property read off a drawn part.
STYLE_NAMES = [
    "color",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "textAlign",
    "textDecorationLine",
    "boxShadow",
    "height",
    "width",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
]

#: EXPANDED maps a Qt shorthand to the properties it settles into.
EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "background": ("backgroundColor",),
    "background-color": ("backgroundColor",),
    "font-size": ("fontSize",),
    "font-weight": ("fontWeight",),
    "color": ("color",),
}

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = " + json.dumps(str(HOST_WIDTH_PX) + "px") + ";"
    "document.body.appendChild(window.HOST);"
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
    "        disabled: el.disabled === true, text: own,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)


def give_tokens(browser: Browser) -> int:
    """Push `token_payload` into the page and apply it, since a disk-loaded
    view has no bridge."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_table(browser: Browser, payload: dict) -> list:
    """Render `payload` into `window.HOST` and return what `READ_PARTS` finds."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetBotTable(JSON.parse(window.PAYLOAD));"
        "acervatorBotTable.renderTable(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    """Return what `READ_PARTS` finds, without rendering again."""
    return json.loads(browser.js(READ_PARTS))


def declarations_of(sheet: Any) -> list:
    """Return each property and value of `sheet`, read in Python rather than
    through the module."""
    found: list = []
    if not isinstance(sheet, str):
        return found
    for one in sheet.split(";"):
        parts = one.split(":")
        prop = parts.pop(0).strip()
        if not parts or not prop:
            continue
        value = ":".join(parts).strip()
        if value:
            found.append((prop, value))
    return found


def base_body(sheet: Any) -> str:
    return ";".join(prop + ":" + value for prop, value in declarations_of(sheet))


def probe(browser: Browser, tag: str, body: str) -> dict:
    """Return the computed values a bare `tag` takes from `body`."""
    names: list = []
    for prop, _ in declarations_of(body):
        names.extend(EXPANDED.get(prop, (prop,)))
    if not names:
        return {}
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(tag)
        + ", "
        + json.dumps(body)
        + ", "
        + json.dumps(sorted(set(names)))
        + ")"
    )


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def grouped_rows(parts: list) -> list:
    """Group each row of `parts` with the cells drawn after it, in document
    order."""
    found: list = []
    for one in parts:
        part = one["attrs"].get("data-part")
        if part == "row":
            found.append({"row": one, "cells": []})
            continue
        if part == "cell" and found:
            found[-1]["cells"].append(one)
    return found


def drawn_rows(parts: list) -> list:
    return [one["row"] for one in grouped_rows(parts)]


def drawn_cells(parts: list, at: int) -> list:
    return grouped_rows(parts)[at]["cells"]


def row_identity(parts: list) -> list:
    """Each drawn row's bot id beside the text of every cell it draws."""
    return [
        {
            "bot_id": one["row"]["attrs"].get("data-bot-id"),
            "texts": [cell["text"] for cell in one["cells"]],
        }
        for one in grouped_rows(parts)
    ]


def surface_identity(payload: dict) -> list:
    """Return each `payload` row `bot_id` with its cell texts, a button
    column reading empty."""
    found = []
    for row in payload["rows"]:
        texts = ["" if cell is None else str(cell["text"]) for cell in row["cells"]]
        found.append({"bot_id": row["bot_id"], "texts": texts})
    return found


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser, revealed):
    assert revealed is not None
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorBotTable") == "object"
    assert browser.js("typeof window.acervatorSetBotTable") == "function"
    assert browser.js("typeof window.acervatorLoadBotTable") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser, revealed):
    assert revealed is not None
    browser.js(WATCH_VIOLATIONS)
    payload = bridge_payload({"statuses": THREE_BOTS})
    assert payload["icon_download"] is False
    draw_table(browser, payload)
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_network_check_names_a_refused_connection(browser: Browser, revealed):
    assert revealed is not None
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


def test_the_drawn_table_shows_every_header_the_surface_published(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    parts = draw_table(browser, payload)
    headers = [one for one in parts if one["attrs"].get("data-part") == "header"]
    assert [one["text"] for one in headers] == [
        found["text"] for found in payload["headers"]
    ]
    assert [one["attrs"].get("data-field-id") for one in headers] == [
        found["field_id"] for found in payload["headers"]
    ]
    assert len(headers) == payload["column_count"]


def test_the_drawn_table_shows_every_cell_the_surface_published(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    parts = draw_table(browser, payload)
    assert row_identity(parts) == surface_identity(payload)


def test_the_drawn_cell_check_names_one_changed_money_text(browser: Browser, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    before = row_identity(draw_table(browser, payload))
    payload["rows"][0]["cells"][bsts.AMMO_COLUMN]["text"] = "changed-ammo"
    after = row_identity(draw_table(browser, payload))
    assert before != after
    assert "changed-ammo" in after[0]["texts"]


def test_every_drawn_child_a_check_reads_carries_a_name(browser: Browser, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    parts = draw_table(browser, payload)
    unnamed = [
        one["path"]
        for one in parts
        if not any(
            key in one["attrs"]
            for key in ("data-column", "data-row", "data-bot-id", "aria-label")
        )
        and one["attrs"].get("data-part") not in ("table", "head-row")
    ]
    assert not unnamed, f"{len(unnamed)} drawn parts carry no name: {unnamed}"


def test_every_drawn_cell_colour_matches_a_probe_styled_from_the_surface(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    parts = draw_table(browser, payload)
    checked = 0
    differing = {}
    for at, _ in enumerate(drawn_rows(parts)):
        for column, cell in enumerate(payload["rows"][at]["cells"]):
            if cell is None or not cell["color"]:
                continue
            drawn = drawn_cells(parts, at)[column]
            expected = probe(browser, "td", "color:" + cell["color"])
            checked += 1
            if drawn["style"]["color"] != expected["color"]:
                differing[f"{at}.{column}"] = (
                    expected["color"],
                    drawn["style"]["color"],
                )
    assert checked, "no drawn cell carried a colour, so nothing was compared"
    assert (
        not differing
    ), f"{len(differing)} of {checked} cell colours differ: {differing}"


def test_the_drawn_fire_button_matches_a_probe_styled_from_its_own_sheet(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": PATH_STATUSES})
    parts = draw_table(browser, payload)
    buttons = [one for one in parts if one["attrs"].get("data-part") == "fire-button"]
    assert len(buttons) == len(payload["rows"])
    differing = {}
    for drawn in buttons:
        path = drawn["attrs"]["data-path"]
        sheet = payload["fire_styles"][path]
        expected = probe(browser, "button", base_body(sheet))
        for name, value in expected.items():
            if drawn["style"].get(name) != value:
                differing[path + "." + name] = (value, drawn["style"].get(name))
    assert not differing, f"{len(differing)} Fire style values differ: {differing}"


def test_the_fire_style_check_names_one_changed_colour(browser: Browser, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": PATH_STATUSES})
    path = payload["rows"][0]["fire"]["path"]
    sheet = payload["fire_styles"][path]
    parts = draw_table(browser, payload)
    drawn = [one for one in parts if one["attrs"].get("data-path") == path][0]
    expected = probe(browser, "button", base_body(sheet).replace("bold", "normal"))
    assert drawn["style"]["fontWeight"] != expected["fontWeight"]


def test_the_drawn_fire_button_is_enabled_exactly_where_the_surface_says(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": PATH_STATUSES})
    parts = draw_table(browser, payload)
    buttons = [one for one in parts if one["attrs"].get("data-part") == "fire-button"]
    drawn = [not one["disabled"] for one in buttons]
    wanted = [row["fire"]["enabled"] for row in payload["rows"]]
    assert drawn == wanted, f"drawn {drawn} against published {wanted}"
    assert True in wanted and False in wanted, "the states did not cover both"


def test_the_armed_fire_button_carries_the_glow_the_surface_published(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": PATH_STATUSES})
    parts = draw_table(browser, payload)
    buttons = [one for one in parts if one["attrs"].get("data-part") == "fire-button"]
    glowing = {
        one["attrs"]["data-path"]: one["style"]["boxShadow"]
        for one in buttons
        if one["attrs"].get("data-glow")
    }
    wanted = {
        row["fire"]["path"]
        for row in payload["rows"]
        if row["fire"] and row["fire"]["glow"]
    }
    assert set(glowing) == wanted, f"drawn {sorted(glowing)} against {sorted(wanted)}"
    assert wanted, "no published state glowed, so nothing was compared"
    for path, shadow in glowing.items():
        assert shadow != "none", f"{path} declared a glow and drew none"


def test_the_glow_check_reads_no_shadow_on_a_path_that_declares_none(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": PATH_STATUSES})
    parts = draw_table(browser, payload)
    quiet = [
        one
        for one in parts
        if one["attrs"].get("data-part") == "fire-button"
        and not one["attrs"].get("data-glow")
    ]
    assert quiet, "every published state glowed"
    assert all(one["style"]["boxShadow"] == "none" for one in quiet)


def changed_paths(before: list, after: list) -> set:
    """Every (path, property) whose computed value moved between reads."""
    assert len(before) == len(after), "the table drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((at, key))
    return moved


def drawn_cell_places(parts: list, places: set) -> set:
    """The (row, column) each named part sits at, buttons and rows apart."""
    found = set()
    for at in places:
        one = parts[at]
        column = one["attrs"].get("data-column")
        assert column is not None, f"{one['path']} is not a cell"
        row = [
            other for other in parts[:at] if other["attrs"].get("data-part") == "row"
        ][-1]
        found.add((int(row["attrs"]["data-row"]), int(column)))
    return found


def cells_carrying(payload: dict, colour: str) -> set:
    """Every (row, column) whose published cell colour is ``colour``."""
    found = set()
    for at, row in enumerate(payload["rows"]):
        for column, cell in enumerate(row["cells"]):
            if cell is not None and cell["color"] == colour:
                found.add((at, column))
    return found


def test_the_drawn_table_follows_a_colour_token_and_nothing_else_moves(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    carried = bsts.STATE_COLORS["running"]
    wanted = cells_carrying(payload, carried)
    assert wanted, "no published cell carried the running colour"
    before = draw_table(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty('--SUCCESS', "
        + json.dumps(str(dss.ERROR))
        + ");"
    )
    after = read_parts(browser)
    moved = changed_paths(before, after)
    assert moved, "the token moved nothing at all"
    assert {key for _, key in moved} == {
        "color",
        "borderTopColor",
    }, f"an unset border colour is currentColor, so only these move: {moved}"
    assert drawn_cell_places(before, {at for at, _ in moved}) == wanted


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    before = draw_table(browser, payload)
    assert changed_paths(before, read_parts(browser)) == set()


def test_no_fire_style_the_surface_publishes_names_a_qt_only_paint(
    skinned: JsRuntime,
):
    report = skinned.push(bridge_payload({"statuses": PATH_STATUSES}))
    named = [one for one in report["faults"] if one["fault"] == "not-css"]
    assert named == [], f"the table publishes a Qt-only paint: {named}"


def test_the_qt_only_check_names_an_added_gradient(skinned: JsRuntime):
    payload = bridge_payload({"statuses": TWO_BOTS})
    path = payload["rows"][0]["fire"]["path"]
    payload["fire_styles"][path] = "background: qlineargradient(x1:0, y1:0);"
    report = skinned.push(payload)
    assert {
        "where": "fire_styles",
        "field": path,
        "fault": "not-css",
        "detail": "background",
    } in report["faults"]


def test_the_qt_only_check_reads_nothing_without_the_sheet_reader(
    js: JsRuntime, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    path = payload["rows"][0]["fire"]["path"]
    payload["fire_styles"][path] = "background: qlineargradient(x1:0, y1:0);"
    report = js.push(payload)
    assert [one for one in report["faults"] if one["fault"] == "not-css"] == []


# -- 5. row order and row identity -------------------------------------


def test_the_drawn_rows_keep_the_order_the_surface_published(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    parts = draw_table(browser, payload)
    drawn = [row["attrs"].get("data-bot-id") for row in drawn_rows(parts)]
    assert drawn == [row["bot_id"] for row in payload["rows"]]
    assert len(set(drawn)) == len(drawn), "the states did not use distinct bots"


def test_the_row_order_check_names_a_reordered_list(browser: Browser, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    before = row_identity(draw_table(browser, payload))
    payload["rows"] = list(reversed(payload["rows"]))
    after = row_identity(draw_table(browser, payload))
    assert after != before
    assert [one["bot_id"] for one in after] == list(
        reversed([one["bot_id"] for one in before])
    )


def test_the_row_identity_check_names_two_bots_values_swapped(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    before = row_identity(draw_table(browser, payload))
    first = payload["rows"][0]["cells"]
    second = payload["rows"][1]["cells"]
    payload["rows"][0]["cells"] = second
    payload["rows"][1]["cells"] = first
    after = row_identity(draw_table(browser, payload))
    assert after != before, "swapping two bots' cells changed nothing"
    assert [one["bot_id"] for one in after] == [one["bot_id"] for one in before]
    assert after[0]["texts"] == before[1]["texts"]
    assert after[1]["texts"] == before[0]["texts"]


def test_a_skipped_row_is_drawn_empty_and_named(browser: Browser, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": MIXED_STATUSES})
    assert payload["skipped_rows"], "no row was skipped"
    parts = draw_table(browser, payload)
    rows = drawn_rows(parts)
    assert len(rows) == len(payload["rows"])
    for at in payload["skipped_rows"]:
        assert rows[at]["attrs"]["data-skipped"] == "true"
        assert all(one["text"] == "" for one in drawn_cells(parts, at))


def test_the_skipped_row_check_reads_a_filled_row_as_filled(browser: Browser, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": MIXED_STATUSES})
    parts = draw_table(browser, payload)
    rows = drawn_rows(parts)
    filled = [at for at, _ in enumerate(rows) if at not in payload["skipped_rows"]]
    assert filled
    for at in filled:
        assert rows[at]["attrs"]["data-skipped"] == "false"
        assert any(one["text"] for one in drawn_cells(parts, at))


def test_the_drawn_table_marks_the_row_the_surface_selected(browser: Browser, revealed):
    assert revealed is not None
    payload = state_payload("selected")
    assert payload["has_selection"] is True
    parts = draw_table(browser, payload)
    rows = drawn_rows(parts)
    marked = [row for row in rows if row["attrs"]["data-selected"] == "true"]
    assert len(marked) == 1
    assert marked[0]["attrs"]["data-bot-id"] == payload["selected_bot_id"]


def test_the_selection_check_reads_an_unselected_table_as_unselected(
    browser: Browser, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    assert payload["has_selection"] is False
    parts = draw_table(browser, payload)
    assert all(row["attrs"]["data-selected"] == "false" for row in drawn_rows(parts))


# -- 6. hostile payloads -----------------------------------------------

#: Values JSON carries unchanged, written into one cell's text.
HOSTILE_TEXTS = {
    "a true flag": True,
    "nothing at all": None,
    "a two hundred character symbol": "X" * 200,
    "markup": "<script>alert(1)</script>",
    "an empty text": "",
}

#: HOSTILE_AMOUNTS holds numbers where text belongs, each a double.
HOSTILE_AMOUNTS = {
    "a number where text belongs": 1.0,
    "a very large integer": 10**24,
}

#: Every hostile value, for the checks that read the OTHER rows.
HOSTILE_ALL = dict(HOSTILE_TEXTS)
HOSTILE_ALL.update(HOSTILE_AMOUNTS)

#: Values JSON cannot spell, written into the parsed payload instead.
HOSTILE_NUMBERS = {
    "not a number": "NaN",
    "an infinity": "Infinity",
    "a negative infinity": "-Infinity",
}


@pytest.mark.parametrize("case", sorted(HOSTILE_TEXTS))
def test_the_table_shows_whatever_cell_text_the_surface_produced(
    js: JsRuntime, revealed, case: str
):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    payload["rows"][0]["cells"][bsts.AMMO_COLUMN]["text"] = HOSTILE_TEXTS[case]
    js.push(payload)
    shown = js.at("cellAt", 0, bsts.AMMO_COLUMN)["text"]
    assert shown == HOSTILE_TEXTS[case], f"{case}: the table holds {shown!r}"


@pytest.mark.parametrize("case", sorted(HOSTILE_AMOUNTS))
def test_the_table_shows_whatever_amount_the_surface_put_in_a_text_cell(
    js: JsRuntime, revealed, case: str
):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    payload["rows"][0]["cells"][bsts.AMMO_COLUMN]["text"] = HOSTILE_AMOUNTS[case]
    js.push(payload)
    shown = js.at("cellAt", 0, bsts.AMMO_COLUMN)["text"]
    assert float(shown) == float(HOSTILE_AMOUNTS[case]), f"{case}: holds {shown!r}"


@pytest.mark.parametrize("case", sorted(HOSTILE_NUMBERS))
def test_the_table_holds_a_number_json_cannot_spell(js: JsRuntime, revealed, case: str):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    js.push_written(
        payload,
        "P.rows[0].cells["
        + str(bsts.AMMO_COLUMN)
        + "].text = "
        + HOSTILE_NUMBERS[case]
        + ";",
    )
    shown = js.at("cellAt", 0, bsts.AMMO_COLUMN)["text"]
    assert shown is None or isinstance(shown, float), f"{case}: {shown!r}"


def test_the_bridge_cannot_carry_a_not_a_number_at_all(js: JsRuntime, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    payload["rows"][0]["cells"][bsts.AMMO_COLUMN]["text"] = float("nan")
    written = json.dumps(payload)
    assert "NaN" in written
    js.bind_text("BROKEN", written)
    result = js.run(
        "(function () { try { JSON.parse(BROKEN); return 'parsed'; }"
        " catch (e) { return e.name; } })()"
    )
    assert result.toString() == "SyntaxError"


def test_the_bridge_check_parses_the_same_payload_without_the_bad_value(
    js: JsRuntime, revealed
):
    assert revealed is not None
    written = json.dumps(bridge_payload({"statuses": TWO_BOTS}))
    assert "NaN" not in written
    js.bind_text("WHOLE", written)
    result = js.run(
        "(function () { try { JSON.parse(WHOLE); return 'parsed'; }"
        " catch (e) { return e.name; } })()"
    )
    assert result.toString() == "parsed"


@pytest.mark.parametrize("field", sorted(bsts.view_model({"reset": True})))
def test_a_field_the_payload_omits_is_named_as_missing(
    js: JsRuntime, revealed, field: str
):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    del payload[field]
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"]
    assert report["held"]["fields"] == report["declared"]["fields"] - 1


@pytest.mark.parametrize("field", sorted(bsts.view_model({"reset": True})))
def test_a_field_carrying_null_is_named(js: JsRuntime, revealed, field: str):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime, revealed):
    assert revealed is not None
    report = js.push(bridge_payload({"statuses": TWO_BOTS}))
    kinds = [one["fault"] for one in report["faults"]]
    assert "missing" not in kinds
    assert "null" not in kinds


HELD_TYPES = {
    "a cell text that is a number": (
        ["rows", 0, "cells", bsts.AMMO_COLUMN, "text"],
        12.5,
        "row:0/cell:" + str(bsts.AMMO_COLUMN),
        "text",
    ),
    "a mode colour that is a number": (
        ["rows", 0, "cells", bsts.MODE_COLUMN, "color"],
        7,
        "row:0/cell:" + str(bsts.MODE_COLUMN),
        "color",
    ),
    "a fire label that is a number": (
        ["rows", 0, "fire", "text"],
        3,
        "row:0/fire",
        "text",
    ),
    "a fire height that is text": (
        ["rows", 0, "fire", "height"],
        "22",
        "row:0/fire",
        "height",
    ),
    "a detail style that is a number": (
        ["rows", 0, "detail", "style_sheet"],
        9,
        "row:0/detail",
        "style_sheet",
    ),
    "a header text that is a number": (
        ["headers", 0, "text"],
        5,
        "header:0",
        "text",
    ),
}


def put(payload: dict, path: list, value: Any) -> None:
    node: Any = payload
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value


@pytest.mark.parametrize("case", sorted(HELD_TYPES))
def test_a_wrong_type_is_named_where_the_surface_publishes_a_default(
    js: JsRuntime, revealed, case: str
):
    assert revealed is not None
    path, value, where, field = HELD_TYPES[case]
    payload = bridge_payload({"statuses": TWO_BOTS})
    put(payload, path, value)
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "wrong-type" and one["where"] == where
    ]
    assert named and named[0]["field"] == field, f"{case}: {report['faults']}"


def test_the_wrong_type_check_is_quiet_on_a_whole_payload(js: JsRuntime, revealed):
    assert revealed is not None
    report = js.push(bridge_payload({"statuses": PATH_STATUSES}))
    named = [one for one in report["faults"] if one["fault"] == "wrong-type"]
    assert named == []


def test_a_fire_path_the_surface_never_published_is_named(js: JsRuntime, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    payload["rows"][0]["fire"]["path"] = "planted_path"
    report = js.push(payload)
    assert {
        "where": "row:0/fire",
        "field": "path",
        "fault": "unknown-path",
        "detail": "planted_path",
    } in report["faults"]


def test_a_fire_style_that_is_not_its_path_s_own_is_named(js: JsRuntime, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    payload["rows"][0]["fire"]["style_sheet"] = payload["detail_style"]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "style-mismatch"]
    assert len(named) == 1 and named[0]["where"] == "row:0/fire"


def test_a_row_that_is_not_an_object_is_named_and_draws_nothing(
    js: JsRuntime, revealed
):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    payload["rows"][0] = "not a row"
    report = js.push(payload)
    assert {
        "where": "row:0",
        "field": None,
        "fault": "not-an-object",
        "detail": "string",
    } in report["faults"]


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(
    js: JsRuntime, revealed
):
    assert revealed is not None
    js.push(bridge_payload({"statuses": TWO_BOTS}))
    report = js.push([])
    assert js.json("acervatorBotTable.isLoaded()") is False
    assert report["declared"] is None
    assert js.json("acervatorBotTable.rows()") == []


def test_a_row_with_no_bot_id_is_drawn_and_named(browser: Browser, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    payload["rows"][1]["bot_id"] = ""
    parts = draw_table(browser, payload)
    rows = drawn_rows(parts)
    assert len(rows) == len(payload["rows"])
    assert rows[1]["attrs"].get("data-bot-id") == ""
    assert any(one["text"] for one in drawn_cells(parts, 1))


@pytest.mark.parametrize("case", sorted(HOSTILE_ALL))
def test_one_bad_row_costs_the_other_rows_nothing(
    browser: Browser, revealed, case: str
):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    whole = row_identity(draw_table(browser, payload))
    payload["rows"][1]["cells"][bsts.AMMO_COLUMN]["text"] = HOSTILE_ALL[case]
    spoilt = row_identity(draw_table(browser, payload))
    assert len(spoilt) == len(whole), f"{case}: the table lost rows"
    assert spoilt[0] == whole[0], f"{case}: the first row changed"
    assert spoilt[2] == whole[2], f"{case}: the third row changed"


def test_the_neighbour_check_names_a_row_that_did_change(browser: Browser, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    whole = row_identity(draw_table(browser, payload))
    payload["rows"][0]["cells"][bsts.AMMO_COLUMN]["text"] = "changed-neighbour"
    spoilt = row_identity(draw_table(browser, payload))
    assert spoilt[0] != whole[0]


def test_a_hostile_payload_still_draws_a_table(browser: Browser, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": THREE_BOTS})
    for name in ("state_colors", "fire_styles", "column_tooltips", "actions"):
        payload[name] = None
    parts = draw_table(browser, payload)
    assert len(drawn_rows(parts)) == len(payload["rows"])
    assert row_identity(parts) == surface_identity(payload)


# -- 7. the bridge ask --------------------------------------------------

FAKE_BRIDGE = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, params]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)

REFUSING_BRIDGE = (
    "window.REFUSALS = 0;"
    "window.acervator = { call: function () {"
    "  window.REFUSALS = window.REFUSALS + 1;"
    "  return Promise.reject(new Error('refused')); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime, revealed):
    assert revealed is not None
    payload = bridge_payload({"statuses": TWO_BOTS})
    js.bind_json("PAYLOAD", payload)
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadBotTable();")
    drain_events()
    assert js.json("window.CALLS") == [[payload["method"], {}]]
    assert js.json("acervatorBotTable.isLoaded()") is True


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime, revealed):
    assert revealed is not None
    js.bind_json("PAYLOAD", bridge_payload({"statuses": TWO_BOTS}))
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadBotTable(); acervatorLoadBotTable();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime, revealed):
    assert revealed is not None
    js.bind_json("PAYLOAD", bridge_payload({"statuses": TWO_BOTS}))
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadBotTable();")
    drain_events()
    js.run("acervatorBotTable.forget(); acervatorLoadBotTable();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_a_refused_first_ask_is_not_remembered(js: JsRuntime, revealed):
    assert revealed is not None
    js.run(REFUSING_BRIDGE)
    js.run("acervatorLoadBotTable();")
    drain_events()
    assert js.json("acervatorBotTable.loadError()") == "refused"
    js.run("acervatorLoadBotTable();")
    drain_events()
    assert js.json("window.REFUSALS") == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(
    js: JsRuntime, revealed
):
    assert revealed is not None
    js.run("acervatorLoadBotTable();")
    drain_events()
    assert js.json("acervatorBotTable.loadError()") == (
        "the preload bridge is not present"
    )


# -- 8. the page --------------------------------------------------------


def test_the_page_names_the_table_module_among_its_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("bot_status_table.js")]
    assert named, "index.html names no bot status table module"
    resolved = (INDEX_HTML.parent / named[0]).resolve()
    assert resolved == MODULE_PATH.resolve()


def test_the_page_loads_the_table_module_after_the_modules_it_uses():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = [ref for ref in re.findall(r'src="([^"]+)"', html)]
    at = [i for i, ref in enumerate(refs) if ref.endswith("bot_status_table.js")][0]
    for needed in ("table_cells.js", "header_strip.js", "react.production.min.js"):
        before = [i for i, ref in enumerate(refs) if ref.endswith(needed)]
        assert before and before[0] < at, needed + " is not loaded first"


def test_the_module_reuses_the_cell_and_sheet_rules_rather_than_copying_them(
    skinned: JsRuntime,
):
    payload = bridge_payload({"statuses": TWO_BOTS})
    skinned.push(payload)
    carried = bsts.STATE_COLORS["running"]
    skinned.bind_json("VALUE", carried)
    mine = skinned.json("acervatorBotTable.colour(JSON.parse(VALUE))")
    theirs = skinned.json("acervatorCells.colour(JSON.parse(VALUE))")
    assert mine == theirs and mine != carried, f"{mine} against {theirs}"
    sheet = payload["fire_styles"][payload["rows"][0]["fire"]["path"]]
    skinned.bind_json("SHEET", sheet)
    assert skinned.json("acervatorBotTable.styleOf(JSON.parse(SHEET))") == skinned.json(
        "acervatorHeader.styleOf(JSON.parse(SHEET))"
    )


def test_the_resolver_answers_the_plain_value_with_the_cell_module_absent(
    js: JsRuntime, revealed
):
    assert revealed is not None
    carried = bsts.STATE_COLORS["running"]
    js.bind_json("VALUE", carried)
    assert js.json("acervatorBotTable.colour(JSON.parse(VALUE))") == carried
    assert js.json("acervatorBotTable.variableFor(JSON.parse(VALUE))") is None
