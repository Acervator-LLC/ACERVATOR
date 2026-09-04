"""Drives the React API tester against its surface, every venue scripted."""

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

from src.gui.main_tabs import api_tester_tab_surface as surface
from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "api_tester_tab.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorApiTesterTab."
SETTER = "acervatorSetApiTesterTab"

#: The shared modules the page loads beside this api tester module.
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

PLAIN_PROBE = "probe"
MARKUP_PROBE = "<span></span>probe"

LONG_TEXT = "z" * 200
MARKUP_TEXT = "<img src='x'><b>bold</b>"
NEWLINE_TEXT = "one\ntwo"
SWAPPED_ALPHA = "#123a63ff"
OTHER_COLOUR = "#00ffcc"
HOVER_SHEET_FORMAT = "QLabel {{ color: {plain}; }} QLabel:hover {{ color: {hidden}; }}"
HUGE_COUNT = 10**24

EXCHANGES = ["coinbase", "kraken"]
STAMP = "01:02:03"


class Venue:
    """Every outward step this venue answers, from one script alone."""

    def __init__(self, **steps: Any) -> None:
        self.asked: list = []
        self.steps = steps

    def _answer(self, name: str, *args: Any) -> Any:
        self.asked.append(name)
        if name not in self.steps:
            message = "the script has no " + name
            raise RuntimeError(message)
        found = self.steps[name]
        return found(*args) if callable(found) else found

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args: self._answer(name, *args)


CLOCK = {"stamp": STAMP, "started": 1.0, "elapsed_ms": 7.0}

#: The three fields a scripted key lookup resolves, all fixed nonsense text.
VAULT_FIELDS = ("api_key", "api_secret", "passphrase")
VAULT_VALUE = "scripted"


def vault() -> dict:
    """One scripted key lookup: the same fixed word in every field."""
    return dict.fromkeys(VAULT_FIELDS, VAULT_VALUE)


class Answers:
    """A scripted step that answers one value however it is asked."""

    def __init__(self, found: Any) -> None:
        self.found = found
        self.taken: list = []

    def __call__(self, *asked: Any) -> Any:
        self.taken.append(len(asked))
        return self.found


def venue(**steps: Any) -> Venue:
    found = dict(CLOCK)
    found.update(steps)
    return Venue(**found)


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def screen(caller: Any = None) -> Any:
    return surface.build_model(caller=caller, exchange_ids=list(EXCHANGES))


def fresh_payload() -> dict:
    return as_json(surface.build_view_model(screen()))


def connected_payload() -> dict:
    model = screen(
        venue(
            stored_credentials=vault(),
            connect="session",
            market_count=412,
        )
    )
    model.do_connect()
    return as_json(surface.build_view_model(model))


def unread_markets_payload() -> dict:
    model = screen(
        venue(
            stored_credentials=vault(),
            connect="session",
        )
    )
    model.do_connect()
    return as_json(surface.build_view_model(model))


def nothing_open_payload() -> dict:
    model = screen(venue())
    model.do_disconnect()
    return as_json(surface.build_view_model(model))


def unknown_test_payload() -> dict:
    model = screen(venue())
    model.connected = True
    model.connector = "session"
    model.run_test("fetch_everything")
    return as_json(surface.build_view_model(model))


def ran_test_payload() -> dict:
    model = screen(venue(ticker={"bid": 1.0, "ask": 2.0}))
    model.connected = True
    model.connector = "session"
    model.run_test(surface.TEST_TICKER)
    return as_json(surface.build_view_model(model))


def probe_unread_payload() -> dict:
    model = screen(
        venue(
            tcp=True,
            handshake={"protocol": "TLSv1.3"},
            certifi_bundle="ca.pem",
            http=Answers({"headers": {}, "body": "{}"}),
        )
    )
    model.set_exchange("kraken")
    model.raw_http_probe()
    return as_json(surface.build_view_model(model))


def probe_green_payload() -> dict:
    model = screen(
        venue(
            tcp=True,
            handshake={"protocol": "TLSv1.3"},
            certifi_bundle="ca.pem",
            http=Answers({"headers": {}, "body": "{}", "status": 200}),
        )
    )
    model.set_exchange("kraken")
    model.raw_http_probe()
    return as_json(surface.build_view_model(model))


def probe_unreadable_payload() -> dict:
    model = screen(
        venue(
            tcp=True,
            handshake="not a mapping",
            certifi_bundle="ca.pem",
            http=Answers("not a mapping"),
        )
    )
    model.set_exchange("kraken")
    model.raw_http_probe()
    return as_json(surface.build_view_model(model))


def status_unmapped_payload() -> dict:
    model = screen(
        venue(http=Answers({"body": json.dumps({"status": {"indicator": 5}})}))
    )
    model.set_exchange("coinbase")
    model.check_exchange_status()
    return as_json(surface.build_view_model(model))


def status_green_payload() -> dict:
    body = json.dumps(
        {"status": {"indicator": "none", "description": "All Systems Go"}}
    )
    model = screen(venue(http=Answers({"body": body})))
    model.set_exchange("coinbase")
    model.check_exchange_status()
    return as_json(surface.build_view_model(model))


def manual_payload() -> dict:
    model = screen(venue())
    model.set_use_stored(False)
    model.set_manual_credentials(VAULT_VALUE, VAULT_VALUE, "")
    return as_json(surface.build_view_model(model))


STATES = {
    "fresh": fresh_payload,
    "connected": connected_payload,
    "unread_markets": unread_markets_payload,
    "nothing_open": nothing_open_payload,
    "unknown_test": unknown_test_payload,
    "ran_test": ran_test_payload,
    "probe_unread": probe_unread_payload,
    "probe_green": probe_green_payload,
    "probe_unreadable": probe_unreadable_payload,
    "status_unmapped": status_unmapped_payload,
    "status_green": status_green_payload,
    "manual": manual_payload,
}

STATE_NAMES = sorted(STATES)


def state_payload(name: str) -> dict:
    return STATES[name]()


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
    """A field the surface ships that the module never declared is invisible."""
    payload = state_payload(state)
    js.push(payload)
    declared = declared_fields(js)
    missing = sorted(set(payload) - set(declared))
    extra = sorted(set(declared) - set(payload))
    assert missing == [], f"{state}: the module declares none of {missing}"
    assert extra == [], f"{state}: the module declares {extra}, which no payload has"
    assert js.json(API + "payload()") == payload, state


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = fresh_payload()
    payload["a_field_the_module_never_declared"] = 1
    js.push(payload)
    assert "a_field_the_module_never_declared" not in declared_fields(js)
    assert sorted(set(payload) - set(declared_fields(js))) == [
        "a_field_the_module_never_declared"
    ]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = fresh_payload()
    js.push(payload)
    moved = dict(payload)
    moved["connection_title"] = "moved"
    assert js.json(API + "payload()") != moved


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    """Every count the module publishes is filled in, never left at zero."""
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(declared_fields(js))
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["buttons"] == len(payload["test_names"])
    assert report["held"]["buttons"] == len(payload["test_buttons"])
    assert report["declared"]["exchanges"] == len(payload["exchange_ids"])
    assert report["held"]["exchanges"] == len(payload["exchange_options"])
    assert report["declared"]["credentials"] == len(payload["credential_placeholders"])
    assert report["held"]["credentials"] == len(payload["credentials_filled"])
    assert report["declared"]["steps"] == len(payload["call_names"])
    assert report["held"]["steps"] == len(payload["calls"])
    assert report["declared"]["entries"] == payload["entry_count"]
    assert report["held"]["entries"] == len(payload["entries"])
    assert report["declared"]["buttons"] > 0, "the button count stayed at zero"
    assert report["declared"]["steps"] > 0, "the step count stayed at zero"


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = fresh_payload()
    whole = js.push(payload)
    del payload["connection_title"]
    short = js.push(payload)
    assert short["held"]["fields"] == whole["held"]["fields"] - 1
    assert short["declared"]["fields"] == whole["declared"]["fields"]


def test_the_count_check_names_a_published_count_that_stayed_at_zero(js: JsRuntime):
    payload = fresh_payload()
    payload["entry_count"] = 0
    payload["entries"] = [{"stamp": STAMP}]
    js.push(payload)
    kinds = [one["fault"] for one in js.json(API + "faults()")]
    assert "disagrees" in kinds, kinds


def test_a_count_that_matches_its_list_raises_no_fault(js: JsRuntime):
    payload = connected_payload()
    js.push(payload)
    named = [one for one in js.json(API + "faults()") if one["field"] == "entry_count"]
    assert named == [], named
    assert payload["entry_count"] == len(payload["entries"]) > 0


def shown_values() -> set:
    """Every string the tab draws or paints, from the surface itself."""
    found = set()
    for name in dir(surface):
        if not name.isupper():
            continue
        value = getattr(surface, name)
        if isinstance(value, str) and len(value) > 1:
            found.add(value)
        elif isinstance(value, (tuple, list)):
            found.update(one for one in value if isinstance(one, str) and len(one) > 1)
        elif isinstance(value, dict):
            found.update(
                str(one)
                for one in value.values()
                if isinstance(one, str) and len(one) > 1
            )
    return found


def published_strings() -> set:
    """Every string any state's payload carries, at any depth."""
    found = set()

    def walk(value: Any) -> None:
        if isinstance(value, str):
            if len(value) > 1:
                found.add(value)
        elif isinstance(value, dict):
            for one in value.values():
                walk(one)
        elif isinstance(value, list):
            for one in value:
                walk(one)

    for name in STATE_NAMES:
        for value in state_payload(name).values():
            walk(value)
    return found


def token_values() -> set:
    payload = token_payload()
    found = set()
    for value in payload.values():
        if isinstance(value, str):
            found.add(value)
        elif isinstance(value, dict):
            found.update(str(one) for one in value.values())
    return {one for one in found if HEX_COLOUR.fullmatch(one)}


def module_strings() -> list:
    return js_literals(MODULE_SOURCE)["strings"]


def payload_names() -> set:
    return set(fresh_payload())


#: The route and the piece names the module must carry to read its payload.
MODULE_NAMES = {surface.METHOD} | set(surface.ENTRY_MARKS) | set(surface.ENTRY_SLOTS)


def test_every_name_the_module_carries_is_a_name_and_never_a_drawn_value():
    """A name the module writes must be a key, never a word on screen."""
    drawn = set(emitted_strings())
    assert MODULE_NAMES & drawn == set(), sorted(MODULE_NAMES & drawn)
    assert surface.METHOD in MODULE_NAMES
    assert len(MODULE_NAMES) > 10, sorted(MODULE_NAMES)


def test_the_module_writes_no_number():
    """A number written here is a layout figure the surface owns."""
    found = js_literals(MODULE_SOURCE)["numbers"]
    allowed = {"0", "1", "2", "3", "1.3"}
    written = sorted(set(found) - allowed)
    assert written == [], f"the module writes these numbers: {written}"


def written_colours(source: str) -> list:
    """Every colour written into a string literal of ``source``."""
    return [one for one in js_literals(source)["strings"] if HEX_COLOUR.search(one)]


def test_the_module_writes_no_colour():
    found = written_colours(MODULE_SOURCE)
    assert found == [], f"the module writes these colours: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_shows():
    written = sorted(set(module_strings()) & shown_values() - MODULE_NAMES)
    assert written == [], f"the module writes these shown values: {written}"


def test_no_string_in_the_module_equals_a_value_any_state_publishes():
    written = sorted(set(module_strings()) & published_strings() - MODULE_NAMES)
    assert written == [], f"the module writes these published values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(module_strings()) & token_values())
    assert written == [], f"the module writes these token values: {written}"


def test_every_named_word_is_a_name_and_not_a_value_the_tab_shows():
    """A payload key is a name; no key is also something drawn."""
    overlap = sorted(payload_names() & shown_values())
    assert overlap == [], overlap


def test_the_module_hides_no_value_behind_a_regular_expression():
    found = js_literals(MODULE_SOURCE)["slashes"]
    assert found == [], f"the module carries stray slashes: {found}"


WRITTEN_LINES = {
    "number": "var written = 12345;\n",
    "colour": 'var written = "#112233";\n',
    "shown": 'var written = "Exchange Status Page";\n',
    "slash": "var written = /a/;\n",
}


def caught_by_scan(source: str) -> set:
    """Which of the four written kinds a scan of ``source`` reports."""
    found = js_literals(source)
    caught = set()
    if set(found["numbers"]) - {"0", "1", "2", "3", "1.3"}:
        caught.add("number")
    if written_colours(source):
        caught.add("colour")
    if set(found["strings"]) & shown_values() - MODULE_NAMES:
        caught.add("shown")
    if found["slashes"]:
        caught.add("slash")
    return caught


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_line(kind: str):
    """Each written kind, added to a copy of the source, is reported."""
    assert caught_by_scan(MODULE_SOURCE + WRITTEN_LINES[kind]) == {kind}


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    assert caught_by_scan(MODULE_SOURCE + "// #112233\n") == set()


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_each_written_literal_is_caught_in_the_module_file_itself(kind: str):
    """The line is put into the shipped file, caught, and taken back out."""
    before = MODULE_PATH.read_bytes()
    before_hash = hashlib.sha256(before).hexdigest()
    try:
        swap_module(MODULE_PATH, before + WRITTEN_LINES[kind].encode("utf-8"))
        source = MODULE_PATH.read_text(encoding="utf-8")
        assert caught_by_scan(source) == {kind}
    finally:
        swap_module(MODULE_PATH, before)
    after = MODULE_PATH.read_bytes()
    assert (
        hashlib.sha256(after).hexdigest() == before_hash
    ), "the module was left edited"
    assert after == before


def test_the_written_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    """The restore put back a module the engine still runs."""
    assert js.json(API + "method") == surface.METHOD
    assert MODULE_PATH.read_text(encoding="utf-8") == MODULE_SOURCE


def python_kinds(payload: dict) -> dict:
    """Every path in one payload beside the JavaScript type it must arrive as."""
    found = {}

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                path = f"{prefix}.{name}" if prefix else name
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
    payload = state_payload(state)
    js.push(payload)
    wanted = python_kinds(payload)
    found = js.json(API + "kinds()")
    assert found == wanted, sorted(
        path for path in set(found) | set(wanted) if found.get(path) != wanted.get(path)
    )


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    payload = fresh_payload()
    js.push(payload)
    wanted = python_kinds(payload)
    wanted["probe_port"] = "string"
    found = js.json(API + "kinds()")
    assert found != wanted
    assert found["probe_port"] == "number"


def test_the_type_walk_names_a_scalar_where_a_button_row_belongs(js: JsRuntime):
    payload = fresh_payload()
    payload["test_buttons"][0] = 7
    js.push(payload)
    assert js.json(API + "kinds()")["test_buttons.0"] == "number"


def test_the_type_walk_names_a_null_where_a_button_cell_belongs(js: JsRuntime):
    payload = fresh_payload()
    payload["test_buttons"][0][0] = None
    js.push(payload)
    assert js.json(API + "kinds()")["test_buttons.0.0"] == "null"


def test_the_type_walk_names_a_null_where_an_entry_belongs(js: JsRuntime):
    payload = connected_payload()
    payload["entries"][0] = None
    js.push(payload)
    assert js.json(API + "kinds()")["entries.0"] == "null"


def test_the_type_walk_names_a_scalar_inside_a_bag(js: JsRuntime):
    payload = fresh_payload()
    payload["probe_hosts"]["kraken"] = 5
    js.push(payload)
    assert js.json(API + "kinds()")["probe_hosts.kraken"] == "number"


def not_plain_data(payload: Any) -> list:
    """Every path whose value is not a string, number, flag, list, bag or null."""
    found = []

    def walk(prefix: str, node: Any) -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                check(f"{prefix}.{name}" if prefix else name, value)
        elif isinstance(node, list):
            for at, value in enumerate(node):
                check(f"{prefix}.{at}", value)

    def check(path: str, value: Any) -> None:
        if not isinstance(value, (str, int, float, bool, list, dict, type(None))):
            found.append(path)
        walk(path, value)

    walk("", payload)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_surface_publishes_no_live_object(state: str):
    """A connector or a response object on the payload makes it unencodable."""
    payload = surface.build_view_model(screen())
    assert not_plain_data(payload) == []
    live = STATES[state]()
    assert not_plain_data(live) == []
    assert json.dumps(live)


def test_the_live_object_walk_names_a_connector_put_on_the_payload():
    payload = surface.build_view_model(screen())
    payload["connector"] = object()
    assert not_plain_data(payload) == ["connector"]


def test_the_live_object_walk_names_a_response_inside_an_entry():
    payload = surface.build_view_model(screen())
    payload["entries"] = [{"stamp": STAMP, "answer": object()}]
    assert not_plain_data(payload) == ["entries.0.answer"]


def test_a_model_that_holds_a_connector_publishes_only_whether_it_holds_one():
    """The connector never crosses the bridge, only the flag that it is held."""
    model = screen(
        venue(
            stored_credentials=vault(),
            connect="session",
            market_count=1,
        )
    )
    model.do_connect()
    payload = surface.build_view_model(model)
    assert model.connector == "session"
    assert payload["connector_held"] is True
    assert "connector" not in payload
    assert not_plain_data(payload) == []


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    js.push(fresh_payload())
    js.run("acervatorApiTesterTab.payload();")
    js.run(
        "var HELD = " + SETTER + "; var P = JSON.parse(PAYLOAD);"
        " P.live = function () { return 1; }; HELD(P);"
    )
    assert js.json(API + "notPlainData()") == [{"path": "live", "kind": "function"}]


ORDERED_BAGS = (
    ("actions", "actions_order"),
    ("entry_marks", "entry_mark_order"),
    ("entry_slots", "entry_slot_order"),
    ("level_colors", "level_color_order"),
    ("probe_endpoint_table", "probe_endpoint_table_order"),
    ("probe_hosts", "probe_host_order"),
    ("status_page_urls", "status_page_order"),
)


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_bag_ships_its_key_order_as_a_list(js: JsRuntime, state: str):
    """A bag alone loses its order, so each ships its keys beside it."""
    payload = state_payload(state)
    js.push(payload)
    for name, order in ORDERED_BAGS:
        assert js.json(API + f'list("{order}")') == js.json(API + f'bagKeys("{name}")')
        assert payload[order] == list(payload[name]), name


def test_the_bag_order_check_names_an_order_list_that_lost_a_key(js: JsRuntime):
    payload = fresh_payload()
    payload["probe_host_order"] = payload["probe_host_order"][1:]
    js.push(payload)
    kinds = [
        one["fault"]
        for one in js.json(API + "faults()")
        if one["field"] == "probe_host_order"
    ]
    assert "short-list" in kinds, kinds


def test_the_bag_order_check_names_an_order_list_whose_keys_moved(js: JsRuntime):
    payload = fresh_payload()
    order = payload["probe_host_order"]
    payload["probe_host_order"] = [order[1], order[0]] + order[2:]
    js.push(payload)
    kinds = [
        one["fault"]
        for one in js.json(API + "faults()")
        if one["field"] == "probe_host_order"
    ]
    assert "disagrees" in kinds, kinds


def test_a_bag_order_that_matches_raises_no_fault(js: JsRuntime):
    js.push(fresh_payload())
    named = [
        one for one in js.json(API + "faults()") if one["field"] == "probe_host_order"
    ]
    assert named == [], named


def test_no_bag_carries_a_key_a_browser_would_move_to_the_front(js: JsRuntime):
    js.push(fresh_payload())
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "reordered-key"
    ] == []


def test_the_reordered_key_check_names_a_digit_key_put_into_a_bag(js: JsRuntime):
    payload = fresh_payload()
    payload["probe_hosts"]["12"] = "api.twelve.com"
    payload["probe_host_order"] = list(payload["probe_hosts"])
    js.push(payload)
    assert [
        one["detail"]
        for one in js.json(API + "faults()")
        if one["fault"] == "reordered-key"
    ] == ["12"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_each_test_button_is_found_by_the_call_it_names(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for row in payload["test_buttons"]:
        assert js.called("testButtonNamed", row[1]) == row, row
    assert js.json(API + "testNames()") == payload["test_names"]


def test_the_button_lookup_answers_nothing_for_a_call_no_button_names(js: JsRuntime):
    js.push(fresh_payload())
    assert js.called("testButtonNamed", "fetch_everything") is None


@pytest.mark.parametrize("state", STATE_NAMES)
def test_each_exchange_option_is_found_by_the_id_it_carries(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for row in payload["exchange_options"]:
        assert js.called("exchangeOptionNamed", row[1]) == row, row
    assert js.json(API + "exchangeNames()") == payload["exchange_ids"]


def test_the_exchange_lookup_answers_nothing_for_an_id_no_option_carries(js: JsRuntime):
    js.push(fresh_payload())
    assert js.called("exchangeOptionNamed", "no-such-venue") is None


def test_each_credential_box_is_found_by_its_own_placeholder(js: JsRuntime):
    payload = manual_payload()
    js.push(payload)
    for at, name in enumerate(payload["credential_placeholders"]):
        assert (
            js.called("credentialFilledNamed", name)
            == payload["credentials_filled"][at]
        )


def test_a_repeated_button_name_is_reported_rather_than_drawn_twice(js: JsRuntime):
    payload = fresh_payload()
    payload["test_buttons"][1][1] = payload["test_buttons"][0][1]
    js.push(payload)
    assert [
        one["detail"]
        for one in js.json(API + "faults()")
        if one["fault"] == "duplicate-name" and one["field"] == "test_buttons"
    ] == [payload["test_buttons"][0][1]]


def test_a_repeated_endpoint_address_is_reported(js: JsRuntime):
    payload = probe_green_payload()
    payload["probe_endpoints"][1][1] = payload["probe_endpoints"][0][1]
    js.push(payload)
    assert [
        one["detail"]
        for one in js.json(API + "faults()")
        if one["fault"] == "duplicate-name" and one["field"] == "probe_endpoints"
    ] == [payload["probe_endpoints"][0][1]]


def test_a_repeated_credential_placeholder_is_reported(js: JsRuntime):
    payload = fresh_payload()
    payload["credential_placeholders"][2] = payload["credential_placeholders"][0]
    js.push(payload)
    assert [
        one["fault"]
        for one in js.json(API + "faults()")
        if one["field"] == "credential_placeholders"
    ] == ["duplicate-name"]


def test_a_real_payload_reports_no_repeated_name(js: JsRuntime):
    js.push(probe_green_payload())
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "duplicate-name"
    ] == []


def test_each_probe_endpoint_is_found_by_its_own_address(js: JsRuntime):
    payload = probe_green_payload()
    js.push(payload)
    for row in payload["probe_endpoints"]:
        assert js.called("endpointNamed", row[1]) == row
    assert js.json(API + "endpointUrls()") == [
        row[1] for row in payload["probe_endpoints"]
    ]


def test_each_probe_header_is_found_by_its_own_name(js: JsRuntime):
    payload = fresh_payload()
    js.push(payload)
    for name, value in payload["probe_headers"]:
        assert js.called_two("headerNamed", "probe_headers", name) == value
    assert js.called("headerNames", "probe_headers") == [
        row[0] for row in payload["probe_headers"]
    ]


def test_every_step_the_screen_took_is_a_step_the_surface_names(js: JsRuntime):
    payload = probe_green_payload()
    js.push(payload)
    assert js.json(API + "calls()") == payload["calls"]
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "unknown-step"
    ] == []
    assert len(payload["calls"]) > 0


def test_the_step_check_names_a_step_the_surface_never_declared(js: JsRuntime):
    payload = probe_green_payload()
    payload["calls"].append(["probe.invented"])
    payload["call_count"] = len(payload["calls"])
    js.push(payload)
    assert [
        one["detail"]
        for one in js.json(API + "faults()")
        if one["fault"] == "unknown-step"
    ] == ["probe.invented"]


PAIRS = (
    ("exchange_options", "exchange_ids"),
    ("credential_placeholders", "credentials_filled"),
    ("test_buttons", "test_names"),
)


@pytest.mark.parametrize("state", STATE_NAMES)
def test_each_paired_list_is_the_same_length_as_the_list_it_pairs_with(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    for left, right in PAIRS:
        assert len(payload[left]) == len(payload[right]), f"{state}: {left}"
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "short-list"
    ] == []


@pytest.mark.parametrize("left,right", PAIRS)
def test_the_pair_check_names_a_list_shorter_than_the_one_it_pairs_with(
    js: JsRuntime, left: str, right: str
):
    payload = fresh_payload()
    payload[right] = payload[right][1:]
    js.push(payload)
    assert [
        one["field"]
        for one in js.json(API + "faults()")
        if one["fault"] == "short-list" and one["field"] == left
    ] == [left]


@pytest.mark.parametrize(
    "name,width",
    [
        ("exchange_options", 2),
        ("test_buttons", 3),
        ("probe_headers", 2),
        ("status_headers", 2),
    ],
)
def test_a_row_of_the_wrong_width_is_reported_rather_than_unpacked(
    js: JsRuntime, name: str, width: int
):
    payload = fresh_payload()
    payload[name][0] = payload[name][0][: width - 1]
    js.push(payload)
    assert [
        one["fault"]
        for one in js.json(API + "faults()")
        if one["field"] == name and one["fault"] == "short-list"
    ] == ["short-list"]


def test_a_row_of_the_right_width_raises_no_row_fault(js: JsRuntime):
    js.push(fresh_payload())
    assert [
        one
        for one in js.json(API + "faults()")
        if one["field"] == "test_buttons" and one["fault"] == "short-list"
    ] == []


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_log_line_is_published_as_pieces_and_as_the_line_they_build(
    js: JsRuntime, state: str
):
    """The marked-up line is rebuilt from the pieces the surface publishes."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "rebuiltLineFormat()") == payload["entry_html_format"]
    for at, one in enumerate(payload["entries"]):
        assert js.called("rebuiltEntryLine", at) == one["html"], at


def test_the_line_check_names_a_piece_that_no_longer_builds_the_line(js: JsRuntime):
    payload = connected_payload()
    payload["entry_marks"]["strong_open"] = "<em>"
    js.push(payload)
    assert [
        one["field"]
        for one in js.json(API + "faults()")
        if one["fault"] == "disagrees" and one["field"] == "entry_html_format"
    ] == ["entry_html_format"]


def test_the_line_check_names_a_missing_piece(js: JsRuntime):
    payload = connected_payload()
    del payload["entry_marks"]["line_break"]
    js.push(payload)
    assert [
        one["detail"]
        for one in js.json(API + "faults()")
        if one["fault"] == "missing" and one["field"] == "entry_marks"
    ] == ["line_break"]


def test_the_surface_composes_the_line_from_the_pieces_it_publishes():
    """The shipped constant is the pieces joined, not a hand-written string."""
    assert surface.ENTRY_HTML_FORMAT == surface.entry_line_format()
    for piece in surface.ENTRY_MARKS.values():
        assert piece in surface.ENTRY_HTML_FORMAT or piece in (
            surface.ENTRY_MARKS["strong_weight"],
            surface.ENTRY_MARKS["detail_wrap"],
        ), piece


def test_the_piece_composition_would_see_one_changed_piece():
    marks = dict(surface.ENTRY_MARKS)
    try:
        surface.ENTRY_MARKS["strong_open"] = "<em>"
        assert surface.entry_line_format() != surface.ENTRY_HTML_FORMAT
    finally:
        surface.ENTRY_MARKS.clear()
        surface.ENTRY_MARKS.update(marks)
    assert surface.entry_line_format() == surface.ENTRY_HTML_FORMAT


def test_a_connect_that_read_no_market_count_never_shows_a_measured_zero():
    """An unread count reads as the mark, not as zero markets."""
    payload = unread_markets_payload()
    mark = surface.UNREADABLE_MARK
    assert mark in payload["status_text"], payload["status_text"]
    assert "0 markets" not in payload["status_text"], payload["status_text"]
    detail = payload["entries"][-1]["detail"]
    assert detail.splitlines()[0].endswith(mark), detail


def test_a_connect_that_read_a_market_count_still_shows_the_figure():
    """A count that was read must still print, or the mark means nothing."""
    payload = connected_payload()
    assert "412" in payload["status_text"], payload["status_text"]
    assert surface.UNREADABLE_MARK not in payload["status_text"]


def test_the_connect_line_never_claims_an_authentication_it_did_not_take():
    """Nothing on this screen checks auth before Fetch Balances is pressed."""
    for name in ("connected", "unread_markets"):
        detail = state_payload(name)["entries"][-1]["detail"]
        assert "Auth: OK" not in detail, detail
        assert "not checked" in detail, detail


def test_a_disconnect_that_closed_nothing_does_not_report_a_close():
    """No session was open, so nothing may say a connection was closed."""
    payload = nothing_open_payload()
    last = payload["entries"][-1]
    assert last["title"] == surface.NOTHING_OPEN_TITLE, last
    assert last["detail"] != surface.DISCONNECTED_DETAIL
    assert [row[0] for row in payload["calls"] if row[0].startswith("disconnect")] == [
        surface.DISCONNECT_NOTHING_OPEN
    ]


def test_a_disconnect_that_did_close_still_reports_the_close():
    model = screen(venue(disconnect=None))
    model.connector = "session"
    model.connected = True
    model.do_disconnect()
    payload = as_json(surface.build_view_model(model))
    assert payload["entries"][-1]["title"] == surface.DISCONNECTED_TITLE
    assert [surface.DISCONNECT_CLOSED, True] in payload["calls"]


def test_a_call_that_did_not_run_never_reports_a_pass():
    """A name no arm answers reached no venue, so it must not read as OK."""
    payload = unknown_test_payload()
    last = payload["entries"][-1]
    assert last["level"] == surface.LEVEL_WARNING, last
    assert last["level"] != surface.LEVEL_SUCCESS
    assert "OK" not in last["title"], last["title"]
    assert last["title"] == surface.TEST_UNKNOWN_FORMAT.format(test="fetch_everything")
    assert [surface.TEST_UNKNOWN, "fetch_everything"] in payload["calls"]


def test_a_call_that_did_run_still_reports_a_pass():
    """A headline that always said NOT RUN would pass the check above."""
    payload = ran_test_payload()
    last = payload["entries"][-1]
    assert last["level"] == surface.LEVEL_SUCCESS, last
    assert last["title"] == surface.TEST_OK_FORMAT.format(test=surface.TEST_TICKER)
    assert [surface.TEST_RAN, surface.TEST_TICKER] in payload["calls"]


def answered_requests(payload: dict) -> list:
    """Every entry reporting one answered request, the sweep header apart."""
    return [
        one
        for one in payload["entries"]
        if one["title"].startswith("HTTP ")
        and one["title"] != payload["http_probes_title"]
    ]


def test_a_request_whose_status_was_never_read_does_not_report_a_pass():
    payload = probe_unread_payload()
    marked = answered_requests(payload)
    assert marked, [one["title"] for one in payload["entries"]]
    for one in marked:
        assert surface.UNREADABLE_MARK in one["title"], one["title"]
        assert one["level"] == surface.LEVEL_WARNING, one
        assert one["level"] != surface.LEVEL_SUCCESS
        assert surface.UNREAD_STATUS_NOTE in one["detail"], one["detail"]


def test_a_request_whose_status_was_read_still_reports_a_pass():
    payload = probe_green_payload()
    marked = answered_requests(payload)
    assert marked, [one["title"] for one in payload["entries"]]
    for one in marked:
        assert one["level"] == surface.LEVEL_SUCCESS, one
        assert surface.UNREADABLE_MARK not in one["title"]
        assert surface.UNREAD_STATUS_NOTE not in one["detail"]


def test_an_answer_that_is_not_a_mapping_stops_nothing_and_claims_nothing():
    payload = probe_unreadable_payload()
    unreadable = [
        one for one in payload["entries"] if one["title"].startswith("UNREADABLE")
    ]
    assert unreadable, [one["title"] for one in payload["entries"]]
    for one in unreadable:
        assert one["level"] == surface.LEVEL_WARNING
    assert [
        row for row in payload["calls"] if row[0] == surface.PROBE_GREEN
    ], "the probe never reached its own summary"


def test_an_unmapped_status_word_is_not_painted_as_an_outage():
    payload = status_unmapped_payload()
    last = payload["entries"][-1]
    assert last["level"] == surface.LEVEL_WARNING, last
    assert last["level"] != surface.LEVEL_ERROR
    assert last["title"] != surface.STATUS_CHECK_FAILED_TITLE


def test_a_green_status_word_is_still_painted_green():
    payload = status_green_payload()
    last = payload["entries"][-1]
    assert last["level"] == surface.LEVEL_SUCCESS, last


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_entry_drawn_green_carries_the_unreadable_mark(js: JsRuntime, state: str):
    """A green line whose own words say nothing was read is an overclaim."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "overclaims()") == [], state


def test_the_overclaim_check_names_a_green_line_carrying_the_mark(js: JsRuntime):
    payload = connected_payload()
    payload["entries"][-1]["level"] = payload["level_success"]
    payload["entries"][-1]["title"] = "HTTP " + payload["unreadable_mark"]
    payload["entries"][-1]["color"] = payload["level_colors"][payload["level_success"]]
    js.push(payload)
    assert js.json(API + "overclaims()") != []
    assert [
        one["fault"] for one in js.json(API + "faults()") if one["fault"] == "overclaim"
    ] == ["overclaim"]


def emitted_strings() -> list:
    """Every title, detail and status line the states above put on screen."""
    found = []
    for name in STATE_NAMES:
        payload = state_payload(name)
        found.append(payload["status_text"])
        found.append(payload["headline"])
        for one in payload["entries"]:
            found.append(one["title"])
            found.append(one["detail"])
    return [one for one in found if one]


def test_every_string_this_screen_emits_is_reachable_for_reading():
    """The audit reads real emitted text, not a list typed out beside it."""
    found = emitted_strings()
    assert len(found) > 40, len(found)
    assert any("CONNECTED" in one for one in found)
    assert any("HTTP" in one for one in found)


def test_no_string_this_screen_emits_claims_a_pass_it_did_not_measure():
    """A green line and the words OK or Auth OK never meet an unread value."""
    banned = ("Auth: OK",)
    carried = [one for one in emitted_strings() for word in banned if word in one]
    assert carried == [], carried


HOSTILE_VALUES = {
    "missing": None,
    "null": None,
    "number_for_text": 7,
    "text_for_number": "twelve",
    "nan": float("nan"),
    "inf": float("inf"),
    "minus_inf": float("-inf"),
    "huge": HUGE_COUNT,
    "long": LONG_TEXT,
    "markup": MARKUP_TEXT,
    "newline": NEWLINE_TEXT,
}

HOSTILE_FIELDS = (
    "connection_title",
    "status_text",
    "headline",
    "symbol",
    "entry_count",
    "entries_logged",
    "entry_limit",
    "probe_port",
    "exchange_id",
    "test_buttons",
    "entries",
    "level_colors",
    "calls",
    "credentials_filled",
)

#: Each hostile kind as the JavaScript source that puts it on a payload.
JS_HOSTILE = {
    "missing": None,
    "null": "null",
    "number_for_text": "7",
    "text_for_number": '"twelve"',
    "nan": "NaN",
    "inf": "Infinity",
    "minus_inf": "-Infinity",
    "huge": "1e24",
    "long": json.dumps(LONG_TEXT),
    "markup": json.dumps(MARKUP_TEXT),
    "newline": json.dumps(NEWLINE_TEXT),
    "call_not_run": json.dumps(surface.TEST_UNKNOWN_FORMAT.format(test="x")),
    "result_unknown": json.dumps(surface.UNREADABLE_MARK),
    "body_not_text": json.dumps(surface.UNREADABLE_BODY_FORMAT.format(kind="bytes")),
}

HOSTILE_KINDS = sorted(JS_HOSTILE)


def broken_payload(js: JsRuntime, payload: dict, name: str, kind: str) -> Any:
    """Push ``payload`` with ``name`` set to the hostile ``kind``, in JS."""
    js.bind_json("HOSTILE", payload)
    if kind == "missing":
        return js.json(
            SETTER + "((function () { var P = JSON.parse(HOSTILE);"
            ' delete P["' + name + '"]; return P; })())'
        )
    return js.json(
        SETTER + "((function () { var P = JSON.parse(HOSTILE);"
        ' P["' + name + '"] = ' + JS_HOSTILE[kind] + "; return P; })())"
    )


@pytest.mark.parametrize("kind", HOSTILE_KINDS)
@pytest.mark.parametrize("name", HOSTILE_FIELDS)
def test_a_hostile_field_is_reported_and_the_module_still_answers(
    js: JsRuntime, name: str, kind: str
):
    """Every hostile value is admitted, reported, and never stops the screen."""
    report = broken_payload(js, connected_payload(), name, kind)
    assert report is not None, f"{name}/{kind} stopped the module"
    assert js.json(API + "isLoaded()") is True
    assert isinstance(js.json(API + "faults()"), list)
    assert js.json(API + "declaredNames()") == declared_fields(js)
    assert isinstance(js.json(API + "kinds()"), dict)
    assert js.json(API + "notPlainData()") == []


@pytest.mark.parametrize("kind", HOSTILE_KINDS)
def test_every_hostile_kind_reaches_the_module_as_the_value_it_names(
    js: JsRuntime, kind: str
):
    """A kind that arrived as text would make the whole sweep prove nothing."""
    broken_payload(js, connected_payload(), "probe_port", kind)
    wanted = {
        "missing": None,
        "null": "null",
        "number_for_text": "number",
        "text_for_number": "string",
        "nan": "number",
        "inf": "number",
        "minus_inf": "number",
        "huge": "number",
        "long": "string",
        "markup": "string",
        "newline": "string",
        "call_not_run": "string",
        "result_unknown": "string",
        "body_not_text": "string",
    }[kind]
    found = js.json(API + "kinds()").get("probe_port")
    assert found == wanted, f"{kind} arrived as {found}"


@pytest.mark.parametrize("kind", HOSTILE_KINDS)
def test_a_hostile_entry_is_reported_and_the_module_still_answers(
    js: JsRuntime, kind: str
):
    """Every hostile kind, put where one response-log entry belongs."""
    payload = connected_payload()
    js.bind_json("HOSTILE", payload)
    setter = (
        SETTER + "((function () { var P = JSON.parse(HOSTILE);"
        " P.entries[0] = "
        + ("undefined" if kind == "missing" else JS_HOSTILE[kind])
        + "; return P; })())"
    )
    assert js.json(setter) is not None, kind
    assert js.json(API + "isLoaded()") is True
    assert isinstance(js.json(API + "entries()"), list)


def test_a_scalar_where_a_bag_belongs_is_reported_not_walked(js: JsRuntime):
    payload = fresh_payload()
    payload["probe_hosts"] = 5
    js.push(payload)
    assert [
        one["field"] for one in js.json(API + "faults()") if one["fault"] == "not-a-bag"
    ] == ["probe_hosts"]


def test_a_scalar_where_a_list_belongs_is_reported_not_walked(js: JsRuntime):
    payload = fresh_payload()
    payload["test_buttons"] = 5
    js.push(payload)
    assert "test_buttons" in [
        one["field"]
        for one in js.json(API + "faults()")
        if one["fault"] == "not-a-list"
    ]


def test_a_null_where_a_bag_belongs_is_reported_not_walked(js: JsRuntime):
    payload = fresh_payload()
    payload["level_colors"] = None
    js.push(payload)
    assert "level_colors" in [
        one["field"] for one in js.json(API + "faults()") if one["fault"] == "not-a-bag"
    ]


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """A module that raised on a hostile payload answers nothing at all."""
    js.push(fresh_payload())
    result = js._engine.evaluate("acervatorApiTesterTab.noSuchMethod()")
    assert result.isError(), "a missing method answered instead of raising"


def test_a_payload_that_is_not_an_object_is_reported_and_never_drawn(js: JsRuntime):
    assert js.json(SETTER + "(7)")["faults"][0]["fault"] == "not-an-object"
    assert js.json(API + "isLoaded()") is False
    assert js.json(API + "payload()") == {}


def test_a_run_count_the_caller_asks_for_is_bounded_by_the_surface():
    """The response log ships whole every call, so its length is bounded."""
    model = screen(venue())
    for _ in range(surface.ENTRY_LIMIT + 25):
        model.log("t", "d")
    payload = surface.build_view_model(model)
    assert len(payload["entries"]) == surface.ENTRY_LIMIT
    assert payload["entry_count"] == surface.ENTRY_LIMIT
    assert payload["entries_logged"] == surface.ENTRY_LIMIT + 25
    assert len(payload["calls"]) <= surface.CALL_LIMIT


def test_the_bound_check_would_see_a_log_that_grew_without_limit():
    model = screen(venue())
    for _ in range(10):
        model.log("t", "d")
    payload = surface.build_view_model(model)
    assert len(payload["entries"]) == 10 < surface.ENTRY_LIMIT
    assert payload["entries_logged"] == 10


def test_a_huge_call_name_runs_nothing_and_grows_the_log_by_two_lines():
    """A caller asking for 10**24 reaches no arm, so nothing repeats."""
    model = screen(venue())
    model.connected = True
    model.connector = "session"
    surface._PANE_MODEL = model
    try:
        payload = surface.view_model({"test": HUGE_COUNT})
    finally:
        surface._PANE_MODEL = None
    assert payload["entries"][-1]["level"] == surface.LEVEL_WARNING
    assert len(payload["entries"]) == 2
    assert len(payload["entries"]) <= surface.ENTRY_LIMIT
    assert [surface.TEST_UNKNOWN, HUGE_COUNT] in payload["calls"]


def test_a_huge_call_name_while_disconnected_is_refused_outright():
    """The screen refuses before it reads the name at all."""
    model = screen(venue())
    surface._PANE_MODEL = model
    try:
        payload = surface.view_model({"test": HUGE_COUNT})
    finally:
        surface._PANE_MODEL = None
    assert payload["entries"][-1]["title"] == surface.NOT_CONNECTED_TITLE
    assert payload["entries"][-1]["level"] == surface.LEVEL_ERROR
    assert len(payload["entries"]) == 1


def test_a_body_that_is_not_text_is_named_rather_than_read():
    assert surface.body_text(None) == surface.UNREADABLE_BODY_FORMAT.format(
        kind="NoneType"
    )
    assert surface.body_text(7) == surface.UNREADABLE_BODY_FORMAT.format(kind="int")
    assert surface.body_text("plain") == "plain"


def test_a_holding_no_reading_admits_is_marked_rather_than_dropped():
    found = surface.positive_only({"BTC": "twelve", "ETH": 2.0, "SOL": 0.0, "X": ""})
    assert found == {"BTC": surface.UNREADABLE_MARK, "ETH": 2.0}


def test_a_candle_row_with_no_close_is_marked_rather_than_raising():
    assert surface.close_of([[1, 2]], 0) == surface.UNREADABLE_MARK
    assert surface.close_of([[1, 2, 3, 4, 5]], 0) == 5
    assert surface.close_of([], 0) == surface.NO_CLOSE


def test_a_market_row_that_is_not_a_mapping_is_counted_out_not_raised():
    found = surface.markets_summary({"A/B": {"type": "spot"}, "C/D": 7})
    assert found["total"] == 2
    assert found["spot"] == 1


def payload_colours(payload: dict) -> list:
    found = []
    for name in (
        "status_color",
        "status_idle_color",
        "status_connecting_color",
        "status_connected_color",
        "status_failed_color",
        "status_disconnected_color",
        "diagnostics_color",
        "default_level_color",
        "timestamp_color",
        "detail_color",
        "headline_color",
    ):
        found.append(payload[name])
    found.extend(payload["level_colors"].values())
    found.extend(one["color"] for one in payload["entries"])
    return [one for one in found if one]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_the_screen_carries_is_swept_for_the_alpha_order_fault(
    js: JsRuntime, state: str
):
    """Qt reads eight hex digits alpha-first, so no colour may carry eight."""
    payload = state_payload(state)
    js.push(payload)
    for one in payload_colours(payload):
        assert js.called("isSwappedAlpha", one) is False, one
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "swapped-alpha"
    ] == []


def test_the_alpha_sweep_names_one_colour_written_with_eight_digits(js: JsRuntime):
    payload = fresh_payload()
    payload["status_color"] = SWAPPED_ALPHA
    payload["status_style"] = payload["status_style_format"].format(color=SWAPPED_ALPHA)
    js.push(payload)
    assert [
        one["detail"]
        for one in js.json(API + "faults()")
        if one["fault"] == "swapped-alpha"
    ] == [SWAPPED_ALPHA, SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_one_entry(js: JsRuntime):
    payload = connected_payload()
    payload["entries"][0]["color"] = SWAPPED_ALPHA
    js.push(payload)
    assert SWAPPED_ALPHA in [
        one["detail"]
        for one in js.json(API + "faults()")
        if one["fault"] == "swapped-alpha"
    ]


def test_the_alpha_sweep_reads_a_colour_inside_a_hover_block(js: JsRuntime):
    payload = fresh_payload()
    payload["status_style"] = HOVER_SHEET_FORMAT.format(
        plain=OTHER_COLOUR, hidden=SWAPPED_ALPHA
    )
    js.push(payload)
    assert SWAPPED_ALPHA in [
        one["detail"]
        for one in js.json(API + "faults()")
        if one["fault"] == "swapped-alpha"
    ]


def test_the_base_declaration_walk_alone_never_reads_the_hover_block(js: JsRuntime):
    """The sweep must read state blocks, or the check above proves nothing."""
    sheet = HOVER_SHEET_FORMAT.format(plain=OTHER_COLOUR, hidden=SWAPPED_ALPHA)
    js.push(fresh_payload())
    base = js.called("wholeSheet", sheet)
    assert any(one["value"] == SWAPPED_ALPHA for one in base), base
    assert any(one["value"] == OTHER_COLOUR for one in base), base


def test_the_alpha_sweep_names_the_eight_digit_shape_and_no_other(js: JsRuntime):
    js.push(fresh_payload())
    assert js.called("isSwappedAlpha", "#00ff88") is False
    assert js.called("isSwappedAlpha", "#888") is False
    assert js.called("isSwappedAlpha", SWAPPED_ALPHA) is True
    assert js.called("isSwappedAlpha", None) is False


def test_a_qt_only_gradient_is_reported_rather_than_painted(js: JsRuntime):
    payload = fresh_payload()
    payload["status_style"] = "background: qlineargradient(x1:0, y1:0);"
    js.push(payload)
    assert [
        one["fault"] for one in js.json(API + "faults()") if one["fault"] == "not-css"
    ] == ["not-css"]


def test_a_real_sheet_reports_no_qt_only_declaration(js: JsRuntime):
    js.push(connected_payload())
    assert [one for one in js.json(API + "faults()") if one["fault"] == "not-css"] == []


def test_a_static_label_carrying_a_tag_is_reported(js: JsRuntime):
    payload = fresh_payload()
    payload["connection_title"] = MARKUP_TEXT
    js.push(payload)
    assert [
        one["field"] for one in js.json(API + "faults()") if one["fault"] == "markup"
    ] == ["connection_title"]


def test_a_venue_answer_carrying_a_tag_is_reported_and_still_drawn(js: JsRuntime):
    payload = connected_payload()
    payload["entries"][0]["detail"] = MARKUP_TEXT
    js.push(payload)
    assert "detail" in [
        one["field"] for one in js.json(API + "faults()") if one["fault"] == "markup"
    ]


def test_a_real_payload_carries_no_markup_in_any_drawn_word(js: JsRuntime):
    js.push(connected_payload())
    assert [one for one in js.json(API + "faults()") if one["fault"] == "markup"] == []


def laid_out(widget: Any) -> int:
    """The width one widget asks for to lay its caller text out."""
    return int(widget.minimumSizeHint().width())


def a_label(text: str) -> Any:
    from PySide6.QtWidgets import QLabel

    return QLabel(text)


def a_button(text: str) -> Any:
    from PySide6.QtWidgets import QPushButton

    return QPushButton(text)


def a_group(text: str) -> Any:
    from PySide6.QtWidgets import QGroupBox

    return QGroupBox(text)


def a_check(text: str) -> Any:
    from PySide6.QtWidgets import QCheckBox

    return QCheckBox(text)


def a_combo(text: str) -> Any:
    from PySide6.QtWidgets import QComboBox

    box = QComboBox()
    box.addItem(text)
    return box


#: Each widget this screen builds beside the call reading its asked width.
SCREEN_WIDGETS = {
    "QPushButton": (a_button, laid_out),
    "QGroupBox": (a_group, laid_out),
    "QCheckBox": (a_check, laid_out),
    "QComboBox": (a_combo, laid_out),
}
RICH_TEXT_WIDGETS = {"QLabel": (a_label, laid_out)}
EVERY_WIDGET = dict(SCREEN_WIDGETS, **RICH_TEXT_WIDGETS)


@pytest.mark.parametrize("kind", sorted(SCREEN_WIDGETS))
def test_no_plain_widget_this_screen_uses_reads_its_caller_text_as_markup(
    qapp, kind: str
):
    """A widget laying MARKUP_PROBE out wider than PLAIN_PROBE never read its tags."""
    assert qapp is not None
    build_widget, asked = SCREEN_WIDGETS[kind]
    assert asked(build_widget(MARKUP_PROBE)) > asked(
        build_widget(PLAIN_PROBE)
    ), f"{kind} laid the markup out no wider than the plain words"


@pytest.mark.parametrize("kind", sorted(RICH_TEXT_WIDGETS))
def test_the_one_widget_this_screen_uses_that_does_read_markup_is_named(
    qapp, kind: str
):
    """QLabel lays MARKUP_PROBE out exactly as wide as PLAIN_PROBE."""
    assert qapp is not None
    build_widget, asked = RICH_TEXT_WIDGETS[kind]
    assert asked(build_widget(MARKUP_PROBE)) == asked(build_widget(PLAIN_PROBE))


@pytest.mark.parametrize("kind", sorted(EVERY_WIDGET))
def test_the_markup_measurement_reads_a_longer_text_as_a_wider_layout(qapp, kind: str):
    """A width that never moved would read every widget as one reading markup."""
    assert qapp is not None
    build_widget, asked = EVERY_WIDGET[kind]
    assert asked(build_widget(PLAIN_PROBE * 8)) > asked(build_widget(PLAIN_PROBE))


def test_the_line_edit_asks_the_same_width_whatever_it_holds(qapp):
    """A QLineEdit width is no instrument, so the symbol box is measured apart."""
    from PySide6.QtWidgets import QLineEdit

    assert qapp is not None
    short = QLineEdit(PLAIN_PROBE)
    long_one = QLineEdit(PLAIN_PROBE * 8)
    assert laid_out(short) == laid_out(long_one)


def test_the_symbol_text_is_measured_by_the_width_its_letters_need(qapp):
    """The symbol box asks one width, so its text is measured by the font."""
    from PySide6.QtWidgets import QLineEdit

    assert qapp is not None
    metrics = QLineEdit().fontMetrics()
    assert metrics.horizontalAdvance(PLAIN_PROBE * 8) > metrics.horizontalAdvance(
        PLAIN_PROBE
    )
    assert metrics.horizontalAdvance(MARKUP_PROBE) > metrics.horizontalAdvance(
        PLAIN_PROBE
    )


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
            "the page never defined the api tester module in "
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
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.setAttribute('data-part', 'api-tester-page');"
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
    "window.pageColour = function (names) {"
    "  return window.readStyle(document.body, names); };"
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


def with_part(parts: list, name: str) -> list:
    return [one for one in parts if one["path"].split("/")[-1] == name]


def test_the_screen_fills_the_named_space_the_page_left_for_it(browser: Browser):
    parts = draw_tab(browser, connected_payload())
    assert browser.parsed(API + "spacePart") == "api-tester-page"
    assert with_part(parts, "api-tester-tab"), "the screen drew nothing into the space"


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A child with no name is a child no check can read."""
    draw_tab(browser, connected_payload())
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no data-part"
    assert named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    draw_tab(browser, connected_payload())
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


@pytest.mark.parametrize("state", ["fresh", "connected", "probe_green"])
def test_each_test_button_draws_the_label_and_call_the_surface_carries(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "test-button")
    assert len(drawn) == len(payload["test_buttons"])
    by_call = {one["attrs"]["data-key"]: one for one in drawn}
    for label, call, tip in payload["test_buttons"]:
        assert by_call[call]["text"] == label, call
        assert by_call[call]["title"] == tip, call


def test_each_exchange_option_draws_the_name_and_id_the_surface_carries(
    browser: Browser,
):
    payload = connected_payload()
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "exchange-option")
    assert len(drawn) == len(payload["exchange_options"])
    by_id = {one["attrs"]["data-key"]: one for one in drawn}
    for shown, found in payload["exchange_options"]:
        assert by_id[found]["text"] == shown, found


def test_each_credential_box_draws_its_placeholder_and_carries_no_value(
    browser: Browser,
):
    """What is typed never crosses the bridge, so no box may draw a value."""
    payload = manual_payload()
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "credential-box")
    assert len(drawn) == len(payload["credential_placeholders"])
    for at, one in enumerate(drawn):
        assert one["attrs"]["placeholder"] == payload["credential_placeholders"][at]
        assert one["attrs"]["type"] == "password"
        assert one["text"] == ""
        assert VAULT_VALUE not in json.dumps(one), one["attrs"]
    assert VAULT_VALUE not in json.dumps(payload), "a typed key crossed the bridge"
    assert payload["credentials_filled"][0] is True


@pytest.mark.parametrize("state", ["connected", "probe_unread", "unknown_test"])
def test_each_log_entry_draws_the_title_and_detail_the_surface_carries(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "log-entry")
    assert len(drawn) == len(payload["entries"])
    titles = [one["text"] for one in with_part(parts, "entry-title")]
    details = [one["text"] for one in with_part(parts, "entry-detail")]
    assert titles == [one["title"] for one in payload["entries"]]
    assert details == [one["detail"] for one in payload["entries"]]


def test_a_venue_answer_carrying_a_tag_is_drawn_as_characters(browser: Browser):
    """An API body is caller text, so its tags are letters and not formatting."""
    payload = connected_payload()
    payload["entries"][0]["detail"] = MARKUP_TEXT
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "entry-detail")[0]
    assert drawn["text"] == MARKUP_TEXT
    assert "<img" not in drawn["html"], drawn["html"]
    assert drawn["html"].count("&lt;") == MARKUP_TEXT.count("<")


def test_the_markup_check_would_see_a_tag_that_became_an_element(browser: Browser):
    payload = connected_payload()
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "entry-detail")[0]
    browser.js(
        "window.partNamed = window.HOST.querySelector('[data-part=\"entry-detail\"]');"
        "window.partNamed.innerHTML = '<img src=\"x\">';"
    )
    assert "<img" in browser.js(
        "window.HOST.querySelector('[data-part=\"entry-detail\"]').innerHTML"
    )
    assert drawn["text"]


def test_the_status_line_is_painted_from_a_probe_built_from_its_whole_style(
    browser: Browser,
):
    """The applied value is read against a probe built from the whole declaration."""
    payload = connected_payload()
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "connection-status")[0]
    style = browser.parsed(
        API + "paintedStyle(" + json.dumps(payload["status_style"]) + ")"
    )
    probe = browser.parsed(
        "window.probeAssign(" + json.dumps(style) + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert drawn["style"]["color"] == probe["color"], f"{drawn['style']} vs {probe}"


def test_a_painted_colour_resolves_to_its_token_and_not_the_page_colour(
    browser: Browser,
):
    """A colour that fell back would read as the page colour, not as its own."""
    payload = connected_payload()
    parts = draw_tab(browser, payload)
    page = browser.parsed("window.pageColour(JSON.parse(window.STYLE_NAMES))")
    for name in ("connection-status", "entry-title"):
        drawn = with_part(parts, name)[0]
        assert drawn["style"]["color"] != page["color"], f"{name} took the page colour"
        assert drawn["style"]["color"].startswith("rgb"), drawn["style"]["color"]


def test_the_rendered_comparison_would_see_one_repainted_line(browser: Browser):
    parts = draw_tab(browser, connected_payload())
    drawn = with_part(parts, "connection-status")[0]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"color": OTHER_COLOUR})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert drawn["style"]["color"] != probe["color"]


def test_each_entry_title_is_painted_the_colour_its_level_names(browser: Browser):
    payload = probe_unread_payload()
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "entry-title")
    assert len(drawn) == len(payload["entries"])
    for at, one in enumerate(payload["entries"]):
        probe = browser.parsed(
            "window.probeAssign("
            + json.dumps({"color": payload["level_colors"][one["level"]]})
            + ", JSON.parse(window.STYLE_NAMES))"
        )
        assert drawn[at]["style"]["color"] == probe["color"], one["title"]


def test_the_manual_row_is_hidden_while_the_stored_keys_are_used(browser: Browser):
    parts = draw_tab(browser, fresh_payload())
    row = with_part(parts, "manual-row")[0]
    assert row["hidden"] is True
    assert row["attrs"]["data-shown"] == "false"


def test_the_manual_row_is_shown_when_the_boxes_are_asked_for(browser: Browser):
    parts = draw_tab(browser, manual_payload())
    row = with_part(parts, "manual-row")[0]
    assert row["hidden"] is False
    assert row["attrs"]["data-shown"] == "true"


def test_the_empty_log_draws_the_placeholder_the_surface_names(browser: Browser):
    payload = fresh_payload()
    parts = draw_tab(browser, payload)
    assert with_part(parts, "log-entry") == []
    assert (
        with_part(parts, "log-placeholder")[0]["text"] == payload["result_placeholder"]
    )


def test_a_filled_log_draws_no_placeholder(browser: Browser):
    parts = draw_tab(browser, connected_payload())
    assert with_part(parts, "log-placeholder") == []
    assert with_part(parts, "log-entry")


def test_every_step_the_screen_took_is_drawn_and_hidden(browser: Browser):
    payload = probe_green_payload()
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "tab-step")
    assert len(drawn) == len(payload["calls"])
    assert [one["attrs"]["data-key"] for one in drawn] == [
        row[0] for row in payload["calls"]
    ]


#: Each shown field beside the drawn part that carries it.
SHOWN_FIELDS = (
    ("connection_title", "connection-title"),
    ("exchange_label", "exchange-label"),
    ("use_stored_label", "use-stored-label"),
    ("connect_label", "connect-button"),
    ("disconnect_label", "disconnect-button"),
    ("status_text", "connection-status"),
    ("operations_title", "operations-title"),
    ("response_title", "response-title"),
    ("headline", "response-headline"),
    ("diagnostics_label", "diagnostics-label"),
    ("raw_probe_label", "raw-probe-button"),
    ("status_page_label", "status-page-button"),
)


@pytest.mark.parametrize("state", ["connected", "probe_unread"])
def test_every_field_this_screen_shows_reaches_the_element_that_draws_it(
    browser: Browser, state: str
):
    """A field written but never read is a field nothing on screen depends on."""
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    for name, part in SHOWN_FIELDS:
        drawn = with_part(parts, part)
        assert drawn, f"{part} drew nothing"
        assert drawn[0]["text"] == payload[name], f"{state}: {name}"


def test_the_shown_field_check_would_see_one_element_drawing_other_words(
    browser: Browser,
):
    payload = connected_payload()
    parts = draw_tab(browser, payload)
    drawn = with_part(parts, "connection-title")[0]
    assert drawn["text"] != payload["response_title"]
    assert drawn["text"] == payload["connection_title"]


def test_no_word_the_page_draws_is_a_word_the_module_invented(browser: Browser):
    """Every drawn text traces to a value the payload carries."""
    payload = connected_payload()
    parts = draw_tab(browser, payload)
    carried = json.dumps(payload)
    invented = [
        one["path"]
        for one in parts
        if one["text"].strip() and json.dumps(one["text"])[1:-1] not in carried
    ]
    assert invented == [], f"these drawn words are in no payload value: {invented}"


def test_the_invented_word_check_would_see_one_word_no_payload_carries(
    browser: Browser,
):
    payload = connected_payload()
    draw_tab(browser, payload)
    browser.js(
        "window.HOST.querySelector('[data-part=\"response-title\"]')"
        ".textContent = 'a-word-no-payload-carries';"
    )
    parts = json.loads(browser.js(READ_PARTS))
    carried = json.dumps(payload)
    invented = [
        one["path"]
        for one in parts
        if one["text"].strip() and json.dumps(one["text"])[1:-1] not in carried
    ]
    assert len(invented) == 1, invented


def test_this_host_can_run_the_rendered_checks_at_all():
    """A host with no Chromium skips every rendered check, and says so."""
    pytest.importorskip("PySide6.QtWebEngineWidgets")


#: Each control that draws its own name, beside the parameter the surface
#: reads for it. The name is what a caller sends back, so an empty one
#: leaves the control with no way to say which value it carries.
NAMED_CONTROLS = (
    ("exchange-select", "exchange_id", "kraken"),
    ("use-stored", "use_stored", False),
    ("symbol-box", "symbol", "ETH-USD"),
)


@pytest.mark.parametrize("part,param,sent", NAMED_CONTROLS)
def test_each_named_control_draws_the_parameter_the_surface_reads(
    browser: Browser, part: str, param: str, sent: Any
):
    parts = draw_tab(browser, connected_payload())
    drawn = with_part(parts, part)
    assert len(drawn) == 1, f"{part} drew {len(drawn)} elements"
    assert drawn[0]["attrs"]["data-name"] == param, (
        f"{part} draws data-name "
        f"{drawn[0]['attrs'].get('data-name')!r}, not {param!r}"
    )


@pytest.mark.parametrize("part,param,sent", NAMED_CONTROLS)
def test_the_surface_answers_every_parameter_a_named_control_draws(
    part: str, param: str, sent: Any
):
    """The drawn name is one the handler acts on, not a word with no reader."""
    surface.view_model({"reset": True})
    try:
        before = surface.view_model({})[param]
        after = surface.view_model({param: sent})[param]
    finally:
        surface.view_model({"reset": True})
    assert before != after, f"{param} was already {sent!r} before it was sent"
    assert after == sent, f"the surface answered {after!r} for {param}={sent!r}"


def test_the_named_control_check_would_see_a_name_the_surface_never_reads(
    browser: Browser,
):
    """The positive control: the read sees a wrong name, so a pass means wiring."""
    draw_tab(browser, connected_payload())
    browser.js(
        "window.HOST.querySelector('[data-part=\"symbol-box\"]')"
        ".setAttribute('data-name', 'no_such_parameter');"
    )
    parts = json.loads(browser.js(READ_PARTS))
    drawn = with_part(parts, "symbol-box")[0]
    assert drawn["attrs"]["data-name"] == "no_such_parameter"
