"""The React Bot Swarm settings tab, against bot_swarm_tab_surface.py."""

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

from src.gui.main_tabs import bot_swarm_tab_surface as surface
from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "bot_swarm_settings_tab.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorBotSwarmSettingsTab."
SETTER = "acervatorSetBotSwarmSettingsTab"

#: The merged pieces the page loads beside this module, needed at call time.
SHARED_MODULES = (WEB / "table_cells.js", WEB / "header_strip.js")

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
HOVER_SHEET_FORMAT = "QLabel {{ color: {plain}; }} QLabel:hover {{ color: {hidden}; }}"

NOW = 1_000_000.0
MINE = "bot-a"
UNKNOWN_BOT = "no-such-bot"
HUGE_INT_DECIMAL = 10**400


def ledger(bot_id: str, **rest: Any) -> dict:
    """One stored wire ledger, in the keys the surface reads."""
    found = {
        surface.STORED_BOT_ID_KEY: bot_id,
        surface.STORED_ASSET_KEY: "BTC",
        surface.STORED_WIRED_IN_KEY: 12.0,
        surface.STORED_WIRED_OUT_KEY: 4.0,
        surface.STORED_STARTING_BALANCE_KEY: 100.0,
        surface.STORED_PROVENANCE_KEY: {surface.SEED_SOURCE: 100.0, "bot-c": 12.0},
        surface.STORED_MATURE_ALLOCATED_KEY: 1.0,
        surface.LEDGER_MATURE_TOTAL_FIELD: 7.0,
        surface.LEDGER_MATURE_AVAILABLE_FIELD: 6.0,
    }
    found.update(rest)
    return found


def wire(source: str, target: str, pct: Any) -> dict:
    """One stored wire row."""
    return {
        surface.STORED_SOURCE_KEY: source,
        surface.STORED_TARGET_KEY: target,
        surface.STORED_PCT_KEY: pct,
    }


def event(source: str, target: str, amount: Any, stamp: Any = NOW - 100.0) -> dict:
    """One stored wire event."""
    return {
        surface.TX_TIMESTAMP_FIELD: stamp,
        surface.TX_SOURCE_FIELD: source,
        surface.TX_TARGET_FIELD: target,
        surface.TX_AMOUNT_FIELD: amount,
        surface.TX_TYPE_FIELD: "fold",
    }


def credit(usd: Any = 2.0, stamp: Any = NOW - 300.0, ref: str = "r1") -> dict:
    """One parked wire credit."""
    return {
        surface.CREDIT_TS_KEY: stamp,
        surface.CREDIT_SOURCE_KEY: "bot-c",
        surface.CREDIT_USD_KEY: usd,
        surface.CREDIT_REF_KEY: ref,
    }


WIRED_FLEET = {
    "wires": [wire(MINE, "bot-b", 25.0), wire("bot-c", MINE, 10.0)],
    "ledgers": [
        ledger(MINE),
        ledger("bot-b", asset="ETH"),
        ledger("bot-c", asset="SOL"),
    ],
    "transactions": [
        event(MINE, "bot-b", 4.0),
        event("bot-c", MINE, 12.0, NOW - 90_000.0),
    ],
}

UNREADABLE_FLEET = {
    "wires": [wire(MINE, "bot-b", "25"), wire("bot-c", MINE, None)],
    "ledgers": [
        ledger(
            MINE,
            wired_in="12",
            wired_out=None,
            provenance={surface.SEED_SOURCE: 100.0, "bot-c": "twelve"},
        ),
        ledger("bot-b", asset="ETH"),
        ledger("bot-c", asset="SOL"),
    ],
    "transactions": [event(MINE, "bot-b", float("nan"))],
}

CAPPED_FLEET = {
    "wires": [wire(MINE, "bot-b", 25.0)],
    "ledgers": [ledger(MINE), ledger("bot-b", asset="ETH")],
    "transactions": [event(MINE, "bot-b", float(n), NOW - 100.0) for n in range(1, 26)],
}


def bot(fleet: Any, **rest: Any) -> dict:
    """One bot the tab reads, from the values a request carries."""
    found = {
        "bot_id": MINE,
        "fleet": fleet,
        "pending_credits": 3.0,
        "pending_ledger": [credit()],
    }
    found.update(rest)
    return found


STATES: dict = {
    "fresh": [{"reset": True}],
    "not_active": [{"reset": True, "bot": bot(None), "now_ts": NOW}],
    "empty": [
        {
            "reset": True,
            "bot": bot(
                {"wires": [], "ledgers": [], "transactions": []},
                bot_id=UNKNOWN_BOT,
                pending_credits=0,
                pending_ledger=[],
            ),
            "now_ts": NOW,
        }
    ],
    "wired": [{"reset": True, "bot": bot(WIRED_FLEET), "now_ts": NOW}],
    "unreadable": [
        {
            "reset": True,
            "bot": bot(
                UNREADABLE_FLEET, pending_credits="3", pending_ledger=[credit("2")]
            ),
            "now_ts": NOW,
        }
    ],
    "capped": [
        {"reset": True, "bot": bot(CAPPED_FLEET, pending_ledger=[]), "now_ts": NOW}
    ],
}
STATE_NAMES = tuple(STATES)
DRAWN_STATES = ("not_active", "empty", "wired", "unreadable", "capped")


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


def token_payload() -> dict:
    return as_json(dss.view_model({}))


class JsRuntime(JsEngine):
    """A QJSEngine running this module beside the pieces the page loads."""

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

    def called_two(self, method: str, first: Any, second: Any) -> Any:
        self.bind_json("ARG", first)
        self.bind_json("ARG2", second)
        return self.json(API + method + "(JSON.parse(ARG), JSON.parse(ARG2))")


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
    payload = state_payload("wired")
    payload["only_on_the_surface"] = []
    js.push(payload)
    assert sorted(set(payload) - set(declared_fields(js))) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    payload = state_payload("wired")
    assert payload.pop("tab_label") is not None
    js.push(payload)
    assert sorted(set(declared_fields(js)) - set(payload)) == ["tab_label"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = state_payload("wired")
    payload["accessible_name"] = LONG_NAME
    js.push(payload)
    original = state_payload("wired")
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
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["steps"] == len(payload["call_names"])
    assert report["held"]["steps"] == len(payload["calls"])
    assert report["declared"]["summary"] == len(payload["summary_group"]["styles"])
    assert report["held"]["summary"] == len(payload["summary_group"]["rows"])
    assert report["declared"]["provenance"] == len(
        payload["provenance_group"]["styles"]
    )
    assert report["held"]["provenance"] == len(payload["provenance_group"]["rows"])
    for name in js.json(API + "tableNames()"):
        assert report["declared"]["columns"][name] == len(payload[name]["headers"])
        assert report["held"]["rows"][name] == len(payload[name]["rows"])


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("wired")
    declared = len(payload)
    del payload["accessible_name"]
    report = js.push(payload)
    assert report["declared"]["fields"] == declared
    assert report["held"]["fields"] == declared - 1
    assert [one["field"] for one in report["faults"]] == ["accessible_name"]


def test_a_dropped_wire_row_shortens_the_held_row_count(js: JsRuntime):
    payload = state_payload("wired")
    payload["outbound_table"]["rows"].pop()
    report = js.push(payload)
    assert report["held"]["rows"]["outbound_table"] == 0
    assert [
        one["field"] for one in report["faults"] if one["fault"] == "disagrees"
    ] == ["outbound_table"]


def test_the_published_wire_count_is_filled_in_for_both_wire_tables(js: JsRuntime):
    """A count the surface never fills would report zero beside a drawn row."""
    payload = state_payload("wired")
    js.push(payload)
    for name in ("outbound_table", "inbound_table"):
        assert payload[name]["count"] == len(payload[name]["rows"])
        assert payload[name]["count"] > 0, name
    assert js.json(API + "faults()") == []


def test_the_wire_count_check_names_a_count_that_stayed_at_zero(js: JsRuntime):
    payload = state_payload("wired")
    payload["outbound_table"]["count"] = 0
    report = js.push(payload)
    assert [
        one["detail"] for one in report["faults"] if one["fault"] == "disagrees"
    ] == [0]


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
    payload = state_payload("wired")
    payload["active"] = str(payload["active"])
    js.push(payload)
    expected = python_kinds(state_payload("wired"))
    actual = js.json(API + "kinds()")
    assert sorted(p for p, k in expected.items() if actual.get(p) != k) == ["active"]


def test_the_type_walk_names_a_scalar_where_a_wire_row_belongs(js: JsRuntime):
    """A scalar where the payload lists a row must not read as that row."""
    payload = state_payload("wired")
    payload["outbound_table"]["rows"][0] = 7
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("outbound_table.rows.0") == "number"
    assert "outbound_table.rows.0.0" not in actual


def test_the_type_walk_names_a_null_where_a_wire_cell_belongs(js: JsRuntime):
    payload = state_payload("wired")
    payload["outbound_table"]["rows"][0][0] = None
    js.push(payload)
    assert js.json(API + "kinds()").get("outbound_table.rows.0.0") == "null"


def test_the_type_walk_names_a_null_where_a_breakdown_entry_belongs(js: JsRuntime):
    payload = state_payload("wired")
    payload["provenance_group"]["breakdown"][0] = None
    js.push(payload)
    assert js.json(API + "kinds()").get("provenance_group.breakdown.0") == "null"


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
    raw["outbound_table"]["rows"] = [[surface.BotSwarmTabModel()]]
    assert not_plain_data(raw) == ["outbound_table.rows.0.0"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    js.push(state_payload("wired"))
    js.run(
        SETTER + "(Object.assign(" + API + "payload(), { tab_label: function () {} }));"
    )
    assert js.json(API + "notPlainData()") == [
        {"path": "tab_label", "kind": "function"}
    ]


def test_the_plain_data_check_names_a_function_inside_a_wire_row(js: JsRuntime):
    """A scalar walk that never enters a list would report nothing here."""
    js.push(state_payload("wired"))
    js.run(
        "(function () { var p = " + API + "payload();"
        " p.outbound_table.rows[0][0] = function () {};"
        " " + SETTER + "(p); })()"
    )
    assert js.json(API + "notPlainData()") == [
        {"path": "outbound_table.rows.0.0", "kind": "function"}
    ]


def shown_values() -> set:
    """Every string the tab draws as characters, from every state."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        for group in ("summary_group", "provenance_group"):
            for row in payload[group]["rows"]:
                found |= {one for one in row if isinstance(one, str)}
            found |= {payload[group]["title"]}
        for table in (
            "outbound_table",
            "inbound_table",
            "pending_table",
            "transactions_table",
        ):
            found |= set(payload[table]["headers"])
            found |= {payload[table]["title"]}
            for row in payload[table]["rows"]:
                found |= {one for one in row if isinstance(one, str)}
        for entry in payload["provenance_group"]["breakdown"]:
            found |= {one for one in entry if isinstance(one, str)}
        found |= {payload["empty_label"]["text"]}
        found |= {
            payload["not_active_label"][key] for key in ("lead", "strong", "tail")
        }
        found |= set(payload["labels"].values())
        found |= set(payload["titles"].values())
        found |= {one for one in payload["texts"].values() if isinstance(one, str)}
        found |= set(payload["colours"].values())
        found |= {one for one in payload["formats"].values() if isinstance(one, str)}
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
    | set(BARE["container"])
    | set(BARE["not_active_label"])
    | set(BARE["empty_label"])
    | set(BARE["summary_group"])
    | set(BARE["provenance_group"])
    | set(BARE["outbound_table"])
    | set(BARE["inbound_table"])
    | set(BARE["pending_table"])
    | set(BARE["transactions_table"])
    | set(BARE["tables"])
    | set(BARE["marks"])
    | {surface.METHOD, "provenance", "out_direction", "in_direction", "provenance_join"}
)


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a value the surface owns."""
    assert not MODULE_LITERALS["numbers"], (
        "bot_swarm_settings_tab.js holds numeric literals: "
        f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"bot_swarm_settings_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_shows():
    written = sorted(set(MODULE_LITERALS["strings"]) & SHOWN_VALUES)
    assert not written, f"bot_swarm_settings_tab.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"bot_swarm_settings_tab.js spells out token values: {written}"


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
        "bot_swarm_settings_tab.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES: dict = {
    "colour": 'var written = "' + OTHER_COLOUR + '";',
    "success": 'var written = "' + surface.WIRED_IN_COLOUR + '";',
    "amber": 'var written = "' + surface.WIRED_OUT_COLOUR + '";',
    "inactive": 'var written = "' + surface.INACTIVE_COLOUR + '";',
    "header": 'var written = "' + surface.OUTBOUND_HEADERS[0] + '";',
    "row_label": 'var written = "' + surface.WIRED_IN_ROW_LABEL + '";',
    "group_title": 'var written = "' + surface.SUMMARY_GROUP_TITLE + '";',
    "empty_note": 'var written = "' + surface.EMPTY_TEXT + '";',
    "em_dash": 'var written = "' + surface.NO_VALUE + '";',
    "direction": 'var written = "' + surface.OUT_DIRECTION_TEXT + '";',
    "money_format": 'var written = "' + surface.MONEY_FORMAT + '";',
    "spacing_px": "var written = " + str(surface.CONTENT_SPACING_PX) + ";",
    "limit": "var written = " + str(surface.TRANSACTIONS_SHOWN_LIMIT) + ";",
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
    found = list(payload["colours"].values())
    found += [one for one in payload["transactions_table"]["direction_colours"]]
    found += list(payload["summary_group"]["styles"])
    found += list(payload["provenance_group"]["styles"])
    found += [payload["not_active_label"]["style_sheet"]]
    found += [payload["empty_label"]["style_sheet"]]
    found += list(payload["styles"].values())
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_the_tab_carries_is_swept_for_the_alpha_order_fault(
    js: JsRuntime, state: str
):
    """Every published colour is swept for the eight-digit shape Qt reads first."""
    payload = state_payload(state)
    js.push(payload)
    swept = payload_colours(payload)
    assert len(swept) >= len(payload["colours"])
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "swapped-alpha"
    ] == []


COLOUR_NAMES = (
    "wired_in",
    "wired_out",
    "net_positive",
    "net_negative",
    "pending",
    "inactive",
    "mature_available",
    "out_direction",
    "in_direction",
)


@pytest.mark.parametrize("name", COLOUR_NAMES)
def test_the_alpha_sweep_names_one_colour_written_with_eight_digits(
    js: JsRuntime, name: str
):
    payload = state_payload("wired")
    payload["colours"][name] = SWAPPED_ALPHA
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_one_summary_row_style(js: JsRuntime):
    payload = state_payload("wired")
    payload["summary_group"]["styles"][2] = surface.BOLD_COLOUR_STYLE_FORMAT.format(
        colour=SWAPPED_ALPHA
    )
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_one_direction_cell(js: JsRuntime):
    payload = state_payload("wired")
    payload["transactions_table"]["direction_colours"][0] = SWAPPED_ALPHA
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_a_hover_block(js: JsRuntime):
    """A declaration walk that never enters a state block would stay quiet."""
    payload = state_payload("wired")
    payload["not_active_label"]["style_sheet"] = HOVER_SHEET_FORMAT.format(
        plain=OTHER_COLOUR, hidden=SWAPPED_ALPHA
    )
    report = js.push(payload)
    swapped = [one for one in report["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_base_declaration_walk_alone_never_reads_the_hover_block(js: JsRuntime):
    """The hover colour is caught because the whole sheet is split, not the base."""
    sheet = HOVER_SHEET_FORMAT.format(plain=OTHER_COLOUR, hidden=SWAPPED_ALPHA)
    js.push(state_payload("wired"))
    js.bind_json("SHEET", sheet)
    base = js.json("acervatorHeader.declarations(JSON.parse(SHEET))")
    whole = js.called("wholeSheet", sheet)
    assert [one["value"] for one in base] == [OTHER_COLOUR]
    assert SWAPPED_ALPHA in [one["value"] for one in whole]
    assert len(whole) > len(base)


def test_the_alpha_sweep_names_the_eight_digit_shape_and_no_other(js: JsRuntime):
    js.push(state_payload("wired"))
    assert js.called("isSwappedAlpha", SWAPPED_ALPHA) is True
    assert js.called("isSwappedAlpha", OTHER_COLOUR) is False
    assert js.called("isSwappedAlpha", surface.WIRED_IN_COLOUR) is False
    assert js.called("isSwappedAlpha", None) is False


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_bag_the_surface_publishes_carries_a_key_a_browser_would_move(
    js: JsRuntime, state: str
):
    """A digit key is listed before every worded key, which loses the written order."""
    js.push(state_payload(state))
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "reordered-key"
    ] == []


@pytest.mark.parametrize(
    "bag", ["labels", "texts", "titles", "formats", "colours", "thresholds", "marks"]
)
def test_the_bag_order_check_names_a_digit_key_put_into_a_published_bag(
    js: JsRuntime, bag: str
):
    payload = state_payload("wired")
    payload[bag]["0"] = list(payload[bag].values())[0]
    report = js.push(payload)
    moved = [one for one in report["faults"] if one["fault"] == "reordered-key"]
    assert [one["detail"] for one in moved] == ["0"]


def test_the_four_wire_tables_are_read_from_a_list_and_not_from_a_bag(js: JsRuntime):
    """Pairing four tables off a bag would rest on that bag's key order."""
    js.push(state_payload("wired"))
    assert js.json(API + "tableNames()") == [
        "outbound_table",
        "inbound_table",
        "pending_table",
        "transactions_table",
    ]


@pytest.mark.parametrize("state", ["wired", "unreadable"])
def test_each_summary_row_is_found_by_its_own_label(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for label, value in payload["summary_group"]["rows"]:
        assert js.called("summaryValue", label) == value


@pytest.mark.parametrize("state", ["wired", "unreadable"])
def test_each_provenance_row_is_found_by_its_own_label(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for label, value in payload["provenance_group"]["rows"]:
        assert js.called("provenanceValue", label) == value


def test_the_row_lookup_answers_nothing_for_a_label_no_row_carries(js: JsRuntime):
    js.push(state_payload("wired"))
    assert js.called("summaryValue", UNKNOWN_BOT) is None
    assert js.called("provenanceValue", UNKNOWN_BOT) is None


@pytest.mark.parametrize("table", ["outbound_table", "inbound_table"])
def test_each_wire_row_is_found_by_the_bot_its_first_cell_names(
    js: JsRuntime, table: str
):
    """A wire list is the case where position alone is not an identity."""
    payload = state_payload("wired")
    js.push(payload)
    named = js.called("wireNames", table)
    assert named == [row[0] for row in payload[table]["rows"]]
    for row in payload[table]["rows"]:
        assert js.called_two("wireRowNamed", table, row[0]) == row


def test_the_wire_lookup_answers_nothing_for_a_bot_that_is_not_wired(js: JsRuntime):
    js.push(state_payload("wired"))
    assert js.called_two("wireRowNamed", "outbound_table", UNKNOWN_BOT) is None


def test_a_repeated_wire_name_is_reported_rather_than_drawn_twice(js: JsRuntime):
    payload = state_payload("wired")
    payload["outbound_table"]["rows"].append(list(payload["outbound_table"]["rows"][0]))
    payload["outbound_table"]["count"] += 1
    report = js.push(payload)
    assert [
        one["where"] for one in report["faults"] if one["fault"] == "duplicate-name"
    ] == ["row:1"]


def test_a_repeated_age_in_the_event_table_is_not_read_as_a_repeated_name(
    js: JsRuntime,
):
    """The event table's first cell is an age, which repeats without fault."""
    payload = state_payload("capped")
    ages = [row[0] for row in payload["transactions_table"]["rows"]]
    assert len(set(ages)) < len(ages), ages
    js.push(payload)
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "duplicate-name"
    ] == []


def test_every_step_the_tab_ran_is_a_step_the_surface_names(js: JsRuntime):
    for state in DRAWN_STATES:
        payload = state_payload(state)
        js.push(payload)
        assert js.json(API + "calls()") == payload["calls"]
        assert set(payload["calls"]) <= set(payload["call_names"])
        assert js.json(API + "faults()") == []


def test_the_step_check_names_a_step_the_surface_never_declared(js: JsRuntime):
    payload = state_payload("wired")
    payload["calls"].append(UNKNOWN_BOT)
    report = js.push(payload)
    assert [
        one["detail"] for one in report["faults"] if one["fault"] == "unknown-step"
    ] == [UNKNOWN_BOT]


def test_the_breakdown_names_each_funder_apart_from_the_line_it_joins(js: JsRuntime):
    """A joined line alone cannot answer which funder a figure belongs to."""
    payload = state_payload("wired")
    js.push(payload)
    entries = payload["provenance_group"]["breakdown"]
    assert entries, "the wired state carries no breakdown"
    assert js.json(API + "breakdownSources()") == [one[0] for one in entries]
    for source, drawn in entries:
        assert js.called("breakdownFor", source) == drawn
    assert (
        js.json(API + "breakdownLine()") == payload["provenance_group"]["rows"][-1][1]
    )


def test_the_breakdown_lookup_answers_nothing_for_a_funder_it_has_none_of(
    js: JsRuntime,
):
    js.push(state_payload("wired"))
    assert js.called("breakdownFor", UNKNOWN_BOT) is None


def test_the_breakdown_check_names_a_line_that_no_longer_matches_its_entries(
    js: JsRuntime,
):
    payload = state_payload("wired")
    payload["provenance_group"]["breakdown"][0][1] = LONG_NAME
    report = js.push(payload)
    assert [
        one["field"] for one in report["faults"] if one["fault"] == "disagrees"
    ] == ["breakdown"]


def test_the_breakdown_check_names_a_funder_listed_twice(js: JsRuntime):
    payload = state_payload("wired")
    payload["provenance_group"]["breakdown"].append(
        list(payload["provenance_group"]["breakdown"][0])
    )
    report = js.push(payload)
    assert [
        one["fault"] for one in report["faults"] if one["fault"] == "duplicate-name"
    ] == ["duplicate-name"]


def test_the_breakdown_order_never_rests_on_the_stored_bag_order():
    """Equal amounts are ordered by funder name, not by the order stored."""
    first = surface.provenance_entries({"38": 5.0, surface.SEED_SOURCE: 5.0, "b": 5.0})
    second = surface.provenance_entries({"b": 5.0, "38": 5.0, surface.SEED_SOURCE: 5.0})
    assert [one[0] for one in first] == [one[0] for one in second]
    assert [one[0] for one in first] == ["38", surface.SEED_SOURCE, "b"]


def test_the_breakdown_order_check_would_see_an_order_that_moved():
    """A larger amount is drawn before a smaller one whatever the bag order."""
    entries = surface.provenance_entries({"small": 1.0, "large": 9.0})
    assert [one[0] for one in entries] == ["large", "small"]


def test_a_funder_whose_amount_no_reading_admits_draws_as_unreadable():
    """The shipped tab stopped on this value rather than drawing the mark."""
    entries = surface.provenance_entries({surface.SEED_SOURCE: 5.0, "bad": "twelve"})
    assert [one[0] for one in entries] == [surface.SEED_SOURCE, "bad"]
    assert entries[1][1] == surface.PROVENANCE_REFUSED_FORMAT.format(
        source="bad", value=surface.NO_VALUE
    )


@pytest.mark.parametrize(
    "value", [None, "twelve", float("nan"), float("inf"), float("-inf"), True]
)
def test_every_unreadable_funder_amount_draws_the_mark_and_never_stops(value: Any):
    entries = surface.provenance_entries({"bad": value})
    assert entries == [["bad", "bad: " + surface.NO_VALUE]], value


def test_the_unreadable_funder_check_reads_a_real_amount_as_a_figure():
    entries = surface.provenance_entries({"good": 12.0})
    assert surface.NO_VALUE not in entries[0][1], entries


def test_the_not_active_line_is_published_as_pieces_and_as_the_line_they_build(
    js: JsRuntime,
):
    """Markup written by the surface must reach the screen as emphasis."""
    payload = state_payload("not_active")
    js.push(payload)
    note = payload["not_active_label"]
    assert js.json(API + "markPieces()") == note["marks"]
    assert js.json(API + "rebuiltNotActive()") == note["text"]
    assert surface.STRONG_OPEN_TAG in note["text"]
    for piece in ("lead", "strong", "tail"):
        assert surface.STRONG_OPEN_TAG not in note[piece]
        assert surface.LINE_BREAK_TAG not in note[piece]


def test_the_mark_check_names_a_piece_that_no_longer_builds_the_line(js: JsRuntime):
    payload = state_payload("not_active")
    payload["not_active_label"]["strong"] = LONG_NAME
    payload["not_active_label"]["marks"][1] = LONG_NAME
    report = js.push(payload)
    assert [
        one["detail"] for one in report["faults"] if one["fault"] == "disagrees"
    ] == ["text"]


def test_the_mark_check_names_a_list_that_disagrees_with_the_named_pieces(
    js: JsRuntime,
):
    payload = state_payload("not_active")
    payload["not_active_label"]["marks"][3] = LONG_NAME
    report = js.push(payload)
    named = [one["detail"] for one in report["faults"] if one["fault"] == "disagrees"]
    assert named == ["tail"]


def test_the_mark_check_names_a_piece_list_that_lost_an_entry(js: JsRuntime):
    payload = state_payload("not_active")
    payload["not_active_label"]["marks"].pop()
    report = js.push(payload)
    assert [
        one["field"] for one in report["faults"] if one["fault"] == "short-list"
    ] == ["marks"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_word_the_tab_draws_as_characters_carries_a_tag(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert [one for one in js.json(API + "faults()") if one["fault"] == "markup"] == []


@pytest.mark.parametrize(
    "site",
    [
        "summary_group",
        "provenance_group",
        "outbound_table",
        "empty_label",
        "not_active_label",
    ],
)
def test_the_markup_report_names_a_tag_reaching_one_drawn_word(
    js: JsRuntime, site: str
):
    payload = state_payload("wired")
    if site in ("summary_group", "provenance_group"):
        payload[site]["rows"][0][1] = MARKUP_NAME
    elif site == "outbound_table":
        payload[site]["rows"][0][0] = MARKUP_NAME
    elif site == "empty_label":
        payload[site]["text"] = MARKUP_NAME
    else:
        payload[site]["strong"] = MARKUP_NAME
    report = js.push(payload)
    assert [one["field"] for one in report["faults"] if one["fault"] == "markup"] == [
        site
    ]


HOSTILE_FIELDS: dict = {
    "summary_group missing": ("summary_group", None),
    "summary_group is a list": ("summary_group", []),
    "provenance_group is text": ("provenance_group", "a group"),
    "outbound_table is a list": ("outbound_table", []),
    "inbound_table is a number": ("inbound_table", 7),
    "pending_table is null": ("pending_table", None),
    "transactions_table is text": ("transactions_table", "events"),
    "not_active_label is a list": ("not_active_label", []),
    "empty_label is a number": ("empty_label", 7),
    "marks is a list": ("marks", []),
    "colours is null": ("colours", None),
    "labels is a list": ("labels", []),
    "texts is text": ("texts", "words"),
    "calls is a bag": ("calls", {}),
    "call_names is text": ("call_names", "one"),
    "tables is a list": ("tables", []),
    "container is null": ("container", None),
    "active is text": ("active", "yes"),
    "tab_label is a number": ("tab_label", 7),
    "accessible_name is nan": ("accessible_name", "nan"),
    "method disagrees": ("method", UNKNOWN_BOT),
    "styles is a list": ("styles", []),
    "thresholds is null": ("thresholds", None),
    "actions is a list": ("actions", []),
    "signals is a bag": ("signals", {}),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_FIELDS))
def test_a_hostile_field_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """A payload the surface would never send must report, never raise."""
    name, value = HOSTILE_FIELDS[case]
    payload = state_payload("wired")
    payload[name] = value
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    assert isinstance(js.json(API + "kinds()"), dict), case
    assert isinstance(js.json(API + "notPlainData()"), list), case
    assert isinstance(js.json(API + "summaryRows()"), list), case
    assert isinstance(js.json(API + "provenanceRows()"), list), case
    assert isinstance(js.json(API + "breakdown()"), list), case
    assert isinstance(js.json(API + "markPieces()"), list), case
    assert isinstance(js.called("wireNames", "outbound_table"), list), case


HOSTILE_CELLS: dict = {
    "a short row": ["one"],
    "a null cell": None,
    "a number where text belongs": [7, 7, 7],
    "text where a number belongs": ["one", "two", "three"],
    "not a number": ["nan", "nan", "nan"],
    "infinity": ["inf", "inf", "inf"],
    "minus infinity": ["-inf", "-inf", "-inf"],
    "a huge whole number": [10**24, 10**24, 10**24],
    "a long name": [LONG_NAME] * 3,
    "markup": [MARKUP_NAME] * 3,
    "a newline": [NEWLINE_NAME] * 3,
    "a scalar row": 7,
    "a bag row": {},
    "a duplicate name": None,
}


@pytest.mark.parametrize("case", sorted(HOSTILE_CELLS))
def test_a_hostile_wire_row_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    payload = state_payload("wired")
    if case == "a duplicate name":
        payload["outbound_table"]["rows"].append(
            list(payload["outbound_table"]["rows"][0])
        )
        payload["outbound_table"]["count"] += 1
    else:
        payload["outbound_table"]["rows"][0] = HOSTILE_CELLS[case]
    report = js.push(payload)
    assert isinstance(report["faults"], list), case
    assert isinstance(js.called("tableRows", "outbound_table"), list), case
    assert isinstance(js.called("wireNames", "outbound_table"), list), case
    assert isinstance(js.json(API + "kinds()"), dict), case


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """A module that raised on one hostile value would answer nothing at all."""
    js.push(7)
    assert js.called("tableRows", "outbound_table") == []
    assert js.json(API + "summaryRows()") == []
    assert js.json(API + "breakdown()") == []
    assert js.json(API + "isLoaded()") is False


def test_a_bot_with_no_wire_activity_at_all_draws_the_empty_note(js: JsRuntime):
    """Zero wires is the state the operator sees before the first swarm event."""
    payload = state_payload("empty")
    js.push(payload)
    assert payload["empty_label"]["shown"] is True
    assert payload["outbound_table"]["rows"] == []
    assert payload["inbound_table"]["rows"] == []
    assert js.called("wireNames", "outbound_table") == []
    assert js.json(API + "faults()") == []


def test_a_bot_that_is_not_in_the_fleet_reads_every_summary_figure_as_zero(
    js: JsRuntime,
):
    """The tab draws for a bot the restored fleet has no ledger for."""
    payload = state_payload("empty")
    js.push(payload)
    assert payload["provenance_group"]["shown"] is False
    assert payload["summary_group"]["shown"] is True
    zero = surface.MONEY_FORMAT.format(value=0.0)
    assert js.called("summaryValue", payload["labels"]["wired_in"]) == zero
    assert js.json(API + "faults()") == []


def test_the_missing_bot_check_would_see_a_bot_the_fleet_does_hold(js: JsRuntime):
    payload = state_payload("wired")
    js.push(payload)
    assert payload["provenance_group"]["shown"] is True
    zero = surface.MONEY_FORMAT.format(value=0.0)
    assert js.called("summaryValue", payload["labels"]["wired_in"]) != zero


def test_every_unreadable_stored_value_draws_the_mark_the_surface_names(
    js: JsRuntime,
):
    """Unreadable has to read as unreadable, never as a plausible figure."""
    payload = state_payload("unreadable")
    js.push(payload)
    marked = [
        row for row in payload["summary_group"]["rows"] if row[1] == surface.NO_VALUE
    ]
    assert len(marked) >= 3, payload["summary_group"]["rows"]
    outbound = payload["outbound_table"]["rows"]
    assert outbound and outbound[0][1] == surface.NO_VALUE, outbound
    assert js.json(API + "faults()") == []


def test_the_unreadable_check_reads_a_readable_state_as_figures(js: JsRuntime):
    payload = state_payload("wired")
    js.push(payload)
    marked = [
        row for row in payload["summary_group"]["rows"] if row[1] == surface.NO_VALUE
    ]
    assert marked == []
    assert payload["outbound_table"]["rows"][0][1] != surface.NO_VALUE


def test_the_event_table_shows_no_more_rows_than_the_surface_allows(js: JsRuntime):
    payload = state_payload("capped")
    js.push(payload)
    limit = payload["thresholds"]["transactions_limit"]
    assert len(payload["transactions_table"]["rows"]) == limit
    assert len(CAPPED_FLEET["transactions"]) > limit
    assert js.json(API + "faults()") == []


#: An empty tag pair a rich-text widget swallows and a plain one lays out.
MARKUP_PROBE = "<span></span>wire"
PLAIN_PROBE = "wire"


def laid_out(widget: Any) -> int:
    """The width one widget asks for to lay its caller text out."""
    return int(widget.minimumSizeHint().width())


def column_width(table: Any) -> int:
    """The width one table column asks for to lay its own cell out."""
    return int(table.sizeHintForColumn(0))


def header_width(table: Any) -> int:
    """The width one header section asks for to lay its own words out."""
    return int(table.horizontalHeader().sectionSizeHint(0))


def a_label(text: str) -> Any:
    from PySide6.QtWidgets import QLabel

    return QLabel(text)


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


#: Each widget beside the call that reads the width it asks for.
SCREEN_WIDGETS = {
    "QGroupBox": (a_group, laid_out),
    "QTableWidgetItem": (a_cell, column_width),
    "QHeaderView": (a_header, header_width),
}
RICH_TEXT_WIDGETS = {"QLabel": (a_label, laid_out)}
EVERY_WIDGET = dict(SCREEN_WIDGETS, **RICH_TEXT_WIDGETS)


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_no_plain_widget_this_tab_uses_reads_its_caller_text_as_markup(qapp, kind: str):
    """A widget laying MARKUP_PROBE out wider than PLAIN_PROBE never read its tags."""
    assert qapp is not None
    build_widget, asked = SCREEN_WIDGETS[kind]
    assert asked(build_widget(MARKUP_PROBE)) > asked(
        build_widget(PLAIN_PROBE)
    ), f"{kind} laid the markup out no wider than the plain words"


@pytest.mark.parametrize("kind", sorted(RICH_TEXT_WIDGETS))
def test_the_one_widget_this_tab_uses_that_does_read_markup_is_named(qapp, kind: str):
    """QLabel lays MARKUP_PROBE out exactly as wide as PLAIN_PROBE."""
    assert qapp is not None
    build_widget, asked = RICH_TEXT_WIDGETS[kind]
    assert asked(build_widget(MARKUP_PROBE)) == asked(build_widget(PLAIN_PROBE))


@pytest.mark.parametrize("kind", sorted(EVERY_WIDGET))
def test_the_markup_measurement_reads_a_longer_text_as_a_wider_layout(qapp, kind: str):
    """A width that never moved would read every widget as one that reads markup."""
    assert qapp is not None
    build_widget, asked = EVERY_WIDGET[kind]
    assert asked(build_widget(PLAIN_PROBE * 8)) > asked(build_widget(PLAIN_PROBE))


def test_the_shipped_tab_draws_its_marked_line_into_the_widget_that_reads_markup(
    qapp,
):
    """The not-active line is a QLabel, so its tags are emphasis and not words."""
    assert qapp is not None
    marked = laid_out(a_label(surface.NOT_ACTIVE_TEXT))
    plain = laid_out(a_label(surface.NOT_ACTIVE_STRONG + surface.NOT_ACTIVE_TAIL))
    assert marked > 0 and plain > 0
    assert laid_out(a_label(surface.NOT_ACTIVE_TEXT)) == marked


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
            "the page never defined the bot swarm settings tab module in "
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
    "fontStyle",
    "paddingTop",
    "whiteSpace",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.setAttribute('data-part', 'bot-swarm-page');"
    "document.body.appendChild(window.HOST);"
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


def draw_tab(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    browser.js(
        "acervatorSetTokens(JSON.parse(window.TOKENS));"
        "acervatorTokens.apply(document.documentElement);"
    )
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        SETTER + "(JSON.parse(window.PAYLOAD));" + API + "fill(window.HOST, null);"
    )
    return json.loads(browser.js(READ_PARTS))


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def with_part(parts: list, name: str) -> list:
    return [one for one in parts if one["path"].split("/")[-1] == name]


def test_the_tab_fills_the_named_space_the_window_left_for_it(browser: Browser):
    """The Live Bot Settings window names one space and this tab fills it."""
    parts = draw_tab(browser, state_payload("wired"))
    assert browser.parsed(API + "spacePart") == "bot-swarm-page"
    assert at_path(parts, "bot-swarm-tab"), "the tab drew nothing into the space"


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A child with no name is a child no check can read."""
    draw_tab(browser, state_payload("wired"))
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no data-part"
    assert named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    draw_tab(browser, state_payload("wired"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


@pytest.mark.parametrize("state", ["wired", "unreadable", "empty"])
def test_each_summary_row_draws_the_label_and_value_the_surface_carries(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")
    assert len(drawn) == len(payload["summary_group"]["rows"])
    by_label = {one["attrs"]["data-key"]: one for one in drawn}
    for label, value in payload["summary_group"]["rows"]:
        assert by_label[label]["text"] == value, f"{state} row {label}"


@pytest.mark.parametrize("state", ["wired", "unreadable"])
def test_each_provenance_row_draws_the_label_and_value_the_surface_carries(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "provenance-value")
    assert len(drawn) == len(payload["provenance_group"]["rows"])
    by_label = {one["attrs"]["data-key"]: one for one in drawn}
    for label, value in payload["provenance_group"]["rows"]:
        assert by_label[label]["whole"] == value, f"{state} row {label}"


def test_each_painted_summary_row_matches_a_probe_built_from_its_whole_style(
    browser: Browser,
):
    """The applied value is read against a probe built from the whole declaration."""
    payload = state_payload("wired")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")
    by_label = {one["attrs"]["data-key"]: one for one in drawn}
    for at, (label, _value) in enumerate(payload["summary_group"]["rows"]):
        sheet = payload["summary_group"]["styles"][at]
        style = browser.parsed(API + "paintedStyle(" + json.dumps(sheet) + ")")
        probe = browser.parsed(
            "window.probeAssign("
            + json.dumps(style)
            + ", JSON.parse(window.STYLE_NAMES))"
        )
        found = by_label[label]["style"]
        assert found["color"] == probe["color"], f"{label} drew {found} against {probe}"
        assert found["fontWeight"] == probe["fontWeight"]


def test_the_rendered_comparison_would_see_one_repainted_summary_row(
    browser: Browser,
):
    parts = draw_tab(browser, state_payload("wired"))
    drawn = with_part(parts, "summary-value")[2]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"color": OTHER_COLOUR})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert drawn["style"]["color"] != probe["color"]


def test_an_unpainted_summary_row_takes_no_colour_at_all(browser: Browser):
    """The surface publishes an empty sheet for no colour, and it must not paint."""
    payload = state_payload("wired")
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")
    unpainted = [one for one in drawn if one["attrs"]["data-painted"] == "false"]
    assert unpainted, "no summary row was left unpainted"
    plain = browser.parsed("window.probeAssign({}, JSON.parse(window.STYLE_NAMES))")
    for one in unpainted:
        assert one["style"]["color"] == plain["color"]


def test_the_unpainted_check_would_see_every_summary_row_painted(browser: Browser):
    payload = state_payload("wired")
    payload["summary_group"]["styles"] = [
        surface.PLAIN_COLOUR_STYLE_FORMAT.format(colour=OTHER_COLOUR)
        for _ in payload["summary_group"]["styles"]
    ]
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")
    assert [one for one in drawn if one["attrs"]["data-painted"] == "false"] == []


def test_the_not_active_line_draws_its_emphasis_as_an_element_not_as_tags(
    browser: Browser,
):
    """A surface that means bold draws bold, and the tags reach nobody."""
    payload = state_payload("not_active")
    parts = draw_tab(browser, payload)
    note = with_part(parts, "not-active-note")[0]
    strong = with_part(parts, "mark-strong")[0]
    assert note["hidden"] is False
    assert strong["text"] == payload["not_active_label"]["strong"]
    assert surface.STRONG_OPEN_TAG not in note["whole"]
    assert surface.LINE_BREAK_TAG not in note["whole"]
    assert browser.parsed("window.HOST.querySelectorAll('b').length") == 0
    weight = browser.parsed(
        "window.probeAssign("
        + json.dumps({"fontWeight": payload["marks"]["strong_weight"]})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert strong["style"]["fontWeight"] == weight["fontWeight"]


def test_the_emphasis_check_would_see_a_line_drawn_without_it(browser: Browser):
    parts = draw_tab(browser, state_payload("wired"))
    note = with_part(parts, "not-active-note")[0]
    assert note["hidden"] is True
    lead = with_part(parts, "mark-lead")[0]
    assert lead["text"] == state_payload("wired")["not_active_label"]["lead"]


def test_the_not_active_line_is_hidden_where_the_surface_hides_it(browser: Browser):
    shown = with_part(draw_tab(browser, state_payload("not_active")), "not-active-note")
    quiet = with_part(draw_tab(browser, state_payload("wired")), "not-active-note")
    assert shown[0]["hidden"] is False
    assert quiet[0]["hidden"] is True


def test_the_empty_note_is_shown_only_where_the_surface_shows_it(browser: Browser):
    shown = with_part(draw_tab(browser, state_payload("empty")), "empty-note")[0]
    quiet = with_part(draw_tab(browser, state_payload("wired")), "empty-note")[0]
    assert shown["hidden"] is False
    assert quiet["hidden"] is True
    assert shown["text"] == state_payload("empty")["empty_label"]["text"]


@pytest.mark.parametrize(
    "table",
    ["outbound_table", "inbound_table", "pending_table", "transactions_table"],
)
def test_every_column_the_surface_names_becomes_one_header_in_that_order(
    browser: Browser, table: str
):
    payload = state_payload("wired")
    parts = draw_tab(browser, payload)
    drawn = [
        one
        for one in with_part(parts, "header-cell")
        if one["attrs"]["data-table"] == table
    ]
    assert [one["text"] for one in drawn] == payload[table]["headers"]
    assert [one["attrs"]["data-column"] for one in drawn] == [
        str(at) for at in range(len(payload[table]["headers"]))
    ]


@pytest.mark.parametrize(
    "table",
    ["outbound_table", "inbound_table", "pending_table", "transactions_table"],
)
def test_each_wire_row_draws_every_cell_the_surface_carries(
    browser: Browser, table: str
):
    payload = state_payload("wired")
    parts = draw_tab(browser, payload)
    drawn = [
        one
        for one in with_part(parts, "wire-row")
        if one["attrs"]["data-table"] == table
    ]
    assert len(drawn) == len(payload[table]["rows"])
    for at, row in enumerate(payload[table]["rows"]):
        assert drawn[at]["attrs"]["data-name"] == str(row[0])
        assert drawn[at]["whole"] == "".join(str(cell) for cell in row)


def test_the_direction_cell_is_painted_the_colour_its_own_row_carries(
    browser: Browser,
):
    """The painted cell is found by the word it carries, never by its column."""
    payload = state_payload("wired")
    parts = draw_tab(browser, payload)
    painted = [
        one
        for one in with_part(parts, "wire-cell")
        if one["attrs"]["data-painted"] == "true"
    ]
    assert len(painted) == len(payload["transactions_table"]["rows"])
    for at, one in enumerate(painted):
        probe = browser.parsed(
            "window.probeAssign("
            + json.dumps(
                {"color": payload["transactions_table"]["direction_colours"][at]}
            )
            + ", JSON.parse(window.STYLE_NAMES))"
        )
        assert one["style"]["color"] == probe["color"]


def test_the_direction_check_would_see_a_cell_nobody_painted(browser: Browser):
    payload = state_payload("wired")
    payload["texts"]["out_direction"] = UNKNOWN_BOT
    payload["texts"]["in_direction"] = LONG_NAME
    parts = draw_tab(browser, payload)
    assert [
        one
        for one in with_part(parts, "wire-cell")
        if one["attrs"]["data-painted"] == "true"
    ] == []


def test_the_breakdown_draws_one_element_per_funder_naming_that_funder(
    browser: Browser,
):
    """A joined line drawn alone would name no funder any check could read."""
    payload = state_payload("wired")
    parts = draw_tab(browser, payload)
    entries = with_part(parts, "breakdown-entry")
    published = payload["provenance_group"]["breakdown"]
    assert [one["attrs"]["data-key"] for one in entries] == [
        one[0] for one in published
    ]
    assert [one["text"] for one in entries] == [one[1] for one in published]
    row = [
        one
        for one in with_part(parts, "provenance-value")
        if one["attrs"]["data-key"] == payload["labels"]["provenance"]
    ][0]
    assert row["whole"] == payload["provenance_group"]["rows"][-1][1]


def test_the_breakdown_check_would_see_a_row_drawn_as_one_piece(browser: Browser):
    payload = state_payload("wired")
    payload["provenance_group"]["breakdown"] = []
    parts = draw_tab(browser, payload)
    assert with_part(parts, "breakdown-entry") == []
    row = [
        one
        for one in with_part(parts, "provenance-value")
        if one["attrs"]["data-key"] == payload["labels"]["provenance"]
    ][0]
    assert row["text"] == payload["provenance_group"]["rows"][-1][1]


def test_the_tab_refuses_markup_a_hostile_cell_carries(browser: Browser):
    """React writes the tags as text, so no element reaches the document."""
    payload = state_payload("wired")
    payload["outbound_table"]["rows"][0][0] = MARKUP_NAME
    parts = draw_tab(browser, payload)
    drawn = [
        one
        for one in with_part(parts, "wire-cell")
        if one["attrs"]["data-column"] == "0"
    ]
    assert drawn[0]["text"] == MARKUP_NAME
    assert "<img" not in drawn[0]["html"]
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_tab_refuses_markup_a_hostile_summary_value_carries(browser: Browser):
    payload = state_payload("wired")
    payload["summary_group"]["rows"][0][1] = MARKUP_NAME
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "summary-value")[0]
    assert drawn["text"] == MARKUP_NAME
    assert "<img" not in drawn["html"]


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    draw_tab(browser, state_payload("wired"))
    browser.js("window.HOST.firstChild.insertAdjacentHTML('beforeend', '<img>');")
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 1


def test_a_two_hundred_character_cell_stretches_the_table_rather_than_clipping(
    browser: Browser,
):
    """A CSS table grows to fit where Qt clips, so the width is reported."""
    payload = state_payload("wired")
    payload["outbound_table"]["rows"][0][0] = LONG_NAME
    wide = [
        one
        for one in with_part(draw_tab(browser, payload), "wire-cell")
        if one["attrs"]["data-column"] == "0"
    ][0]
    narrow = [
        one
        for one in with_part(draw_tab(browser, state_payload("wired")), "wire-cell")
        if one["attrs"]["data-column"] == "0"
    ][0]
    assert wide["width"] >= narrow["width"]


def test_the_tab_declares_its_own_spacing_and_leaves_the_form_to_the_host(
    browser: Browser,
):
    """The surface sets a spacing and no margin, and says the host builds the form."""
    payload = state_payload("wired")
    parts = draw_tab(browser, payload)
    tab = at_path(parts, "bot-swarm-tab")[0]
    assert (
        tab["attrs"]["data-margins-set"]
        == str(payload["container"]["margins_set"]).lower()
    )
    group = with_part(parts, "summary-group")[0]
    assert (
        group["attrs"]["data-configured-by-host"]
        == str(payload["summary_group"]["configured_by_host"]).lower()
    )


def test_the_asked_table_height_reaches_the_document_rather_than_a_typed_number(
    browser: Browser,
):
    """The surface owns both heights and the module writes neither."""
    payload = state_payload("wired")
    parts = draw_tab(browser, payload)
    by_table = {
        one["attrs"]["data-table"]: one for one in with_part(parts, "wire-table")
    }
    assert by_table["outbound_table"]["attrs"]["data-max-height"] == str(
        payload["tables"]["wire_max_height_px"]
    )
    assert by_table["transactions_table"]["attrs"]["data-max-height"] == str(
        payload["tables"]["transactions_max_height_px"]
    )


def test_the_tab_draws_more_labelled_rows_than_the_label_bag_names(js: JsRuntime):
    """Twelve labelled rows against eleven names, so no pairing runs by place."""
    payload = state_payload("wired")
    js.push(payload)
    drawn = payload["summary_group"]["rows"] + payload["provenance_group"]["rows"]
    assert len(drawn) == 12
    assert len(payload["labels"]) == 11
    unnamed = [row[0] for row in drawn if row[0] not in set(payload["labels"].values())]
    assert unnamed == [
        payload["formats"]["mature_total_row"].format(
            pct=payload["provenance_group"]["mature_growth_pct"]
        )
    ], unnamed
    for label, value in drawn:
        assert (
            js.called("summaryValue", label) == value
            or js.called("provenanceValue", label) == value
        ), label


def test_the_two_list_count_would_see_a_label_bag_that_named_every_row(js: JsRuntime):
    payload = state_payload("wired")
    js.push(payload)
    named = set(payload["labels"].values())
    assert payload["labels"]["wired_in"] in named
    assert len(named & {row[0] for row in payload["summary_group"]["rows"]}) == 6


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_tab_wires_no_button_timer_thread_or_topic_at_all(
    js: JsRuntime, state: str
):
    """This tab reads state and offers the operator nothing to press."""
    payload = state_payload(state)
    js.push(payload)
    for name in ("timers", "actions"):
        assert js.called("bagKeys", name) == [], name
    for name in ("timer_delays_ms", "bus_topics", "bus_emits", "threads", "signals"):
        assert js.called("list", name) == [], name


def test_the_wiring_check_would_see_one_action_the_surface_declared(js: JsRuntime):
    payload = state_payload("wired")
    payload["actions"]["clear_button.clicked"] = "on_clear"
    js.push(payload)
    assert js.called("bagKeys", "actions") == ["clear_button.clicked"]


def test_this_file_holds_no_carriage_return():
    """A file grew a Windows line ending the build machine reads as text."""
    for path in (MODULE_PATH, Path(__file__)):
        assert path.read_bytes().count(b"\r") == 0, path.name


def test_the_carriage_return_counter_can_report():
    """The carriage-return counter reports nothing whatever a file holds."""
    assert b"a\r\nb".count(b"\r") == 1
    assert b"a\nb".count(b"\r") == 0


def test_the_page_loads_this_module_after_the_pieces_it_reads():
    """A module loaded before header_strip.js would draw no style at all."""
    lines = INDEX_HTML.read_text(encoding="utf-8").splitlines()
    names = [line for line in lines if MODULE_PATH.name in line]
    assert len(names) == 1, names
    order = [
        at
        for at, line in enumerate(lines)
        if any(
            one in line
            for one in (MODULE_PATH.name, "header_strip.js", "table_cells.js")
        )
    ]
    assert len(order) == 3
    assert lines[order[-1]].find(MODULE_PATH.name) >= 0
