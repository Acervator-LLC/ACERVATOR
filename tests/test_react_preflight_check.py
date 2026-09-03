"""The React pre-flight check screen, against preflight_check_surface.py."""

from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import preflight_check_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    load_order,
    new_engine,
    runs_after,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "preflight_check.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorPreflightCheck."
SETTER = "acervatorSetPreflightCheck"

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
GRADIENT_SHEET = "QLabel { background: qlineargradient(x1:0, y1:0); }"

UNKNOWN_NAME = "no-such-name"
HUGE_WHOLE_NUMBER = 10**24

PAIR = "RAVE/USD"
EXCHANGE = "coinbase"

FULL_MARKET = {
    "active": True,
    "limits": {"amount": {"min": 0.01}, "cost": {"min": 1.0}},
    "precision": {"price": 1e-06, "amount": 1e-08},
}
INACTIVE_MARKET = dict(FULL_MARKET, active=False)
NO_ACTIVE_FLAG_MARKET = {
    "limits": {"amount": {"min": 0.01}, "cost": {"min": 1.0}},
    "precision": {"price": 1e-06, "amount": 1e-08},
}
TICKER_DOWN = RuntimeError("ticker endpoint is down")
UNREPORTED_ACTIVE_LINE = surface.ACTIVE_LINE_FORMAT.format(
    active_word=surface.ACTIVE_NOT_REPORTED
)

CONFIG = {
    "exchange_id": EXCHANGE,
    "target_asset": "RAVE",
    "base_currency": "USD",
    "target_balance": 500.0,
}
THIN_CONFIG = dict(CONFIG, target_balance=2.0)
MISSING_CONFIG = dict(CONFIG, target_asset="ZZZ")
EXTRACTOR_CONFIG = dict(CONFIG, mode="extractor")


class FakeExchange:
    """One ccxt exchange whose market list and ticker are steerable."""

    markets: dict = {}
    ticker_error: Any = None

    def __init__(self, config: dict) -> None:
        self.config = dict(config)

    def load_markets(self) -> dict:
        return dict(type(self).markets)

    def fetch_ticker(self, symbol: str) -> dict:
        if type(self).ticker_error is not None:
            raise type(self).ticker_error
        assert symbol
        return {"last": 0.0123}


class FakeCcxt:
    """Puts one steerable ccxt module in place and puts the old one back."""

    def __init__(self, market: dict, ticker_error: Any = None) -> None:
        self.market = market
        self.ticker_error = ticker_error
        self.before: Any = None
        self.had = False

    def __enter__(self) -> None:
        self.had = "ccxt" in sys.modules
        self.before = sys.modules.get("ccxt")
        module = types.ModuleType("ccxt")
        setattr(
            module,
            EXCHANGE,
            type(
                "SpecExchange",
                (FakeExchange,),
                {"markets": {PAIR: self.market}, "ticker_error": self.ticker_error},
            ),
        )
        sys.modules["ccxt"] = module

    def __exit__(self, kind: Any, value: Any, walked: Any) -> None:
        assert walked is None or kind is not None
        if self.had:
            sys.modules["ccxt"] = self.before
        else:
            sys.modules.pop("ccxt", None)


RAN = [{"reset": True}, {"config": CONFIG, "run": True}]
THIN_RAN = [{"reset": True}, {"config": THIN_CONFIG, "run": True}]

STATES: dict = {
    "fresh": (FULL_MARKET, None, [{"reset": True}]),
    "clean": (FULL_MARKET, None, RAN),
    "blocked": (
        FULL_MARKET,
        None,
        [{"reset": True}, {"config": MISSING_CONFIG, "run": True}],
    ),
    "warned": (INACTIVE_MARKET, None, THIN_RAN),
    "proceed": (
        INACTIVE_MARKET,
        None,
        [{"reset": True}, {"config": THIN_CONFIG, "run": True, "button": "yes"}],
    ),
    "closed": (
        INACTIVE_MARKET,
        None,
        [{"reset": True}, {"config": THIN_CONFIG, "run": True, "closed": True}],
    ),
    "skipped": (
        FULL_MARKET,
        None,
        [{"reset": True}, {"config": EXTRACTOR_CONFIG, "run": True}],
    ),
    "unreported": (NO_ACTIVE_FLAG_MARKET, None, RAN),
    "unread": (FULL_MARKET, TICKER_DOWN, RAN),
}
STATE_NAMES = tuple(STATES)
BOXED_STATES = ("blocked", "warned", "proceed", "closed")
CHECKED_STATES = (
    "clean",
    "blocked",
    "warned",
    "proceed",
    "closed",
    "unreported",
    "unread",
)


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def raw_payload(name: str) -> dict:
    """The payload as the surface returns it, never through the encoder."""
    market, ticker_error, steps = STATES[name]
    found: dict = {}
    with FakeCcxt(market, ticker_error):
        for step in steps:
            found = surface.view_model(step)
    return found


def build(name: str) -> dict:
    """One payload, each step driving the same screen in the order given."""
    return as_json(raw_payload(name))


def state_payload(name: str) -> dict:
    return build(name)


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
    payload = state_payload("warned")
    payload["only_on_the_surface"] = []
    js.push(payload)
    assert sorted(set(payload) - set(declared_fields(js))) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for(
    js: JsRuntime,
):
    payload = state_payload("warned")
    assert payload.pop("box_title") is not None
    js.push(payload)
    assert sorted(set(declared_fields(js)) - set(payload)) == ["box_title"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    original = state_payload("warned")
    payload = json.loads(json.dumps(original))
    payload["box_title"] = LONG_NAME
    js.push(payload)
    differing = sorted(
        name for name in original if js.called("field", name) != original[name]
    )
    assert differing == ["box_title"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    found = js.push(payload)
    assert found["declared"]["fields"] == len(payload)
    assert found["held"]["fields"] == len(payload)
    assert found["declared"]["steps"] == len(payload["call_names"])
    assert found["held"]["steps"] == len(payload["calls"])
    assert found["declared"]["result"] == len(payload["result_fields"])
    assert found["held"]["result"] == len(payload["result"])
    assert found["declared"]["buttons"] == len(payload["button_names"])
    assert found["held"]["buttons"] == len(payload["buttons"])
    assert found["declared"]["boxes"] == len(payload["boxes"])
    assert found["held"]["boxes"] == len(payload["box_widgets"])
    assert found["declared"]["outcomes"] == len(payload["outcomes"])
    assert found["held"]["outcomes"] == len(payload["creates_bot"])
    assert found["declared"]["children"] == len(payload["layout"]["order"])
    assert found["held"]["children"] == len(payload["layout"]["child_object_names"])
    assert found["held"]["lines"] == len(payload["box_body_lines"])


def test_the_two_layout_lists_are_counted_apart_rather_than_paired_by_place(
    js: JsRuntime,
):
    """Four children carry three Qt object names, so a placed pairing would drift."""
    payload = state_payload("warned")
    found = js.push(payload)
    assert found["declared"]["children"] == 4
    assert found["held"]["children"] == 3
    assert js.json(API + "faults()") == []
    for name in payload["layout"]["order"]:
        expected = payload["layout"]["child_object_names"].get(name)
        assert js.called("layoutObjectName", name) == expected, name


def test_the_layout_count_check_names_a_child_no_order_lists(js: JsRuntime):
    payload = state_payload("warned")
    payload["layout"]["child_object_names"][UNKNOWN_NAME] = LONG_NAME
    found = js.push(payload)
    assert [
        one["field"] for one in found["faults"] if one["fault"] == "unknown-name"
    ] == ["child_object_names"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_published_warning_count_matches_the_warnings_the_screen_draws(
    js: JsRuntime, state: str
):
    """A count the surface never filled would read zero beside a drawn warning."""
    payload = state_payload(state)
    found = js.push(payload)
    assert found["declared"]["warnings"] == found["held"]["warnings"]
    assert js.json(API + "faults()") == []
    assert payload["warning_count"] == len(payload["result"].get("warnings", []))


def test_the_warning_count_check_names_a_count_that_stayed_at_zero(js: JsRuntime):
    payload = state_payload("warned")
    assert payload["warning_count"] > 0
    payload["warning_count"] = 0
    found = js.push(payload)
    assert [one["field"] for one in found["faults"] if one["fault"] == "disagrees"] == [
        "warning_count"
    ]


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("warned")
    declared = len(payload)
    del payload["status_line"]
    found = js.push(payload)
    assert found["declared"]["fields"] == declared
    assert found["held"]["fields"] == declared - 1
    assert [one["field"] for one in found["faults"]] == ["status_line"]


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
    payload = state_payload("warned")
    payload["checked"] = str(payload["checked"])
    js.push(payload)
    expected = python_kinds(state_payload("warned"))
    actual = js.json(API + "kinds()")
    assert sorted(p for p, k in expected.items() if actual.get(p) != k) == ["checked"]


def test_the_type_walk_names_a_scalar_where_a_check_step_belongs(js: JsRuntime):
    """A scalar where the payload lists a step must not read as that step."""
    payload = state_payload("warned")
    payload["calls"][0] = 7
    js.push(payload)
    actual = js.json(API + "kinds()")
    assert actual.get("calls.0") == "number"
    assert "calls.0.0" not in actual


def test_the_type_walk_names_a_null_where_a_body_line_belongs(js: JsRuntime):
    payload = state_payload("warned")
    payload["box_body_lines"][0] = None
    js.push(payload)
    assert js.json(API + "kinds()").get("box_body_lines.0") == "null"


def test_the_type_walk_names_a_null_where_a_button_belongs(js: JsRuntime):
    payload = state_payload("warned")
    payload["buttons"]["ok"] = None
    js.push(payload)
    assert js.json(API + "kinds()").get("buttons.ok") == "null"


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
    raw = raw_payload(state)
    assert not_plain_data(raw) == [], f"{state} publishes {not_plain_data(raw)}"


def test_the_plain_data_walk_names_a_live_object_put_on_the_payload():
    raw = raw_payload("fresh")
    raw["calls"] = [[surface.PreflightModel()]]
    assert not_plain_data(raw) == ["calls.0.0"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(state_payload(state))
    assert js.json(API + "notPlainData()") == []


def test_the_plain_data_check_names_a_function_bound_into_the_payload(js: JsRuntime):
    js.push(state_payload("warned"))
    js.run(
        SETTER + "(Object.assign(" + API + "payload(), { box_title: function () {} }));"
    )
    assert js.json(API + "notPlainData()") == [
        {"path": "box_title", "kind": "function"}
    ]


def test_the_plain_data_check_names_a_function_inside_a_check_step(js: JsRuntime):
    """A scalar walk that never enters a nested list leaves notPlainData empty."""
    js.push(state_payload("warned"))
    js.run(
        "(function () { var p = " + API + "payload();"
        " p.calls[0][0] = function () {};"
        " " + SETTER + "(p); })()"
    )
    assert js.json(API + "notPlainData()") == [
        {"path": "calls.0.0", "kind": "function"}
    ]


def shown_values() -> set:
    """Every string the screen draws as characters, from every state."""
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        found |= set(payload["box_body_lines"])
        found |= set(payload["report_lines"])
        found |= {payload["box_title"], payload["status_line"]}
        found |= {one["text"] for one in payload["buttons"].values()}
        found |= set(payload["result"].get("warnings", []))
        found |= {one for one in payload["result"].values() if isinstance(one, str)}
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


SHOWN_VALUES = shown_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

BARE = state_payload("fresh")

#: NAMED_WORDS lists every published string the module may write.
NAMED_WORDS = sorted(
    set(BARE)
    | set(BARE["layout"])
    | set(BARE["layout"]["order"])
    | set(BARE["buttons"])
    | set(BARE["buttons"]["ok"])
    | set(BARE["failure_widget"])
    | set(BARE["boxes"])
    | set(BARE["result_fields"])
    | {surface.METHOD}
)


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a value the surface owns."""
    assert not MODULE_LITERALS["numbers"], (
        "preflight_check.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"preflight_check.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_screen_shows():
    written = sorted(set(MODULE_LITERALS["strings"]) & SHOWN_VALUES)
    assert not written, f"preflight_check.js spells out screen values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert set(written) <= set(NAMED_WORDS), (
        "the module names published strings the list does not allow: "
        f"{sorted(set(written) - set(NAMED_WORDS))}"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_screen_shows():
    overlap = sorted(set(NAMED_WORDS) & SHOWN_VALUES)
    assert not overlap, f"these named words are values the screen shows: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "preflight_check.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES: dict = {
    "colour": 'var written = "' + OTHER_COLOUR + '";',
    "title": 'var written = "' + surface.WARNING_TITLE + '";',
    "headline": 'var written = "' + surface.PASSED_HEADLINE + '";',
    "button_text": 'var written = "' + surface.YES_TEXT + '";',
    "active_word": 'var written = "' + UNREPORTED_ACTIVE_LINE + '";',
    "unread_price": 'var written = "' + surface.PRICE_UNREAD_LINE + '";',
    "warnings_headline": 'var written = "' + surface.WARNINGS_HEADLINE + '";',
    "timeout_ms": "var written = " + str(surface.REQUEST_TIMEOUT_MS) + ";",
    "spacing_px": "var written = " + str(surface.LAYOUT_SPACING_PX) + ";",
    "button_value": "var written = " + str(surface.YES_BUTTON_VALUE) + ";",
    "number": "var written = 12;",
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


BROKEN_MODULE_SOURCE = "(function (global) { var = ; })(window);"


def test_the_engine_the_page_uses_runs_this_module(js: JsRuntime):
    """The page runs this module through QJSEngine, so a syntax fault stops it."""
    assert js.json("typeof " + SETTER) == "function"
    assert js.json(API + "method") == surface.METHOD


def test_the_engine_check_reports_a_module_body_it_cannot_parse(js: JsRuntime):
    """A parser skipping nested bodies would pass every module unread."""
    engine = js.engine_of()
    engine.evaluate("var window = this;")
    broken = engine.evaluate(BROKEN_MODULE_SOURCE, MODULE_PATH.name)
    assert broken.isError(), "the engine accepted a broken module body"
    whole = engine.evaluate(MODULE_SOURCE, MODULE_PATH.name)
    assert not whole.isError(), whole.toString()


def payload_sheets(payload: dict) -> list:
    """Every style sheet the screen carries, from every place that holds one."""
    found = [payload[name]["style_sheet"] for name in payload["box_widgets"].values()]
    found += list(payload["skin"].values())
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_the_screen_carries_is_swept_for_the_alpha_order_fault(
    js: JsRuntime, state: str
):
    """Every published sheet is swept for the eight-digit shape Qt reads first."""
    payload = state_payload(state)
    js.push(payload)
    swept = payload_sheets(payload)
    assert len(swept) == len(payload["boxes"]) + len(payload["skin"])
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "swapped-alpha"
    ] == []


@pytest.mark.parametrize("box", ["failure_widget", "warning_widget"])
def test_the_alpha_sweep_names_one_colour_written_with_eight_digits(
    js: JsRuntime, box: str
):
    payload = state_payload("warned")
    payload[box]["style_sheet"] = SWAPPED_ALPHA
    found = js.push(payload)
    swapped = [one for one in found["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_one_skin_entry(js: JsRuntime):
    payload = state_payload("warned")
    payload["skin"]["box"] = surface.STYLE_SHEET + SWAPPED_ALPHA
    found = js.push(payload)
    swapped = [one for one in found["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_a_hover_block(js: JsRuntime):
    """A declaration walk that never enters a state block would stay quiet."""
    payload = state_payload("warned")
    payload["failure_widget"]["style_sheet"] = HOVER_SHEET_FORMAT.format(
        plain=OTHER_COLOUR, hidden=SWAPPED_ALPHA
    )
    found = js.push(payload)
    swapped = [one for one in found["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_base_declaration_walk_alone_never_reads_the_hover_block(js: JsRuntime):
    """The hover colour is caught because the whole sheet is split, not the base."""
    sheet = HOVER_SHEET_FORMAT.format(plain=OTHER_COLOUR, hidden=SWAPPED_ALPHA)
    js.push(state_payload("warned"))
    js.bind_json("SHEET", sheet)
    base = js.json("acervatorHeader.declarations(JSON.parse(SHEET))")
    whole = js.called("wholeSheet", sheet)
    assert [one["value"] for one in base] == [OTHER_COLOUR]
    assert SWAPPED_ALPHA in [one["value"] for one in whole]
    assert len(whole) > len(base)


def test_the_sheet_sweep_names_a_gradient_no_browser_stylesheet_runs(js: JsRuntime):
    payload = state_payload("warned")
    payload["warning_widget"]["style_sheet"] = GRADIENT_SHEET
    found = js.push(payload)
    assert [one["fault"] for one in found["faults"] if one["fault"] == "not-css"] == [
        "not-css"
    ]


def test_the_alpha_sweep_names_the_eight_digit_shape_and_no_other(js: JsRuntime):
    js.push(state_payload("warned"))
    assert js.called("isSwappedAlpha", SWAPPED_ALPHA) is True
    assert js.called("isSwappedAlpha", OTHER_COLOUR) is False
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
    "bag", ["buttons", "actions", "creates_bot", "outcome_levels", "skin", "timers"]
)
def test_the_bag_order_check_names_a_digit_key_put_into_a_published_bag(
    js: JsRuntime, bag: str
):
    payload = state_payload("warned")
    payload[bag]["0"] = LONG_NAME
    found = js.push(payload)
    moved = [one for one in found["faults"] if one["fault"] == "reordered-key"]
    assert [one["detail"] for one in moved] == ["0"]


ORDERED_PAIRS = (
    ("buttons", "button_names"),
    ("button_outcomes", "button_names"),
    ("button_answers", "button_names"),
    ("creates_bot", "outcomes"),
    ("outcome_levels", "outcomes"),
    ("box_closed_outcomes", "boxes"),
    ("box_widgets", "boxes"),
)


@pytest.mark.parametrize("pair", ORDERED_PAIRS, ids=lambda one: one[0])
def test_every_bag_is_read_through_the_order_list_the_surface_publishes(
    js: JsRuntime, pair: tuple
):
    """Reading a bag by its own key order would rest on the encoder, not the surface."""
    bag, order = pair
    payload = state_payload("warned")
    js.push(payload)
    assert sorted(payload[bag]) == sorted(payload[order])
    assert js.json(API + "list('" + order + "')") == payload[order]
    assert js.json(API + "faults()") == []


@pytest.mark.parametrize("pair", ORDERED_PAIRS, ids=lambda one: one[0])
def test_the_order_check_names_a_bag_that_lost_a_name_its_order_lists(
    js: JsRuntime, pair: tuple
):
    bag, order = pair
    payload = state_payload("warned")
    dropped = payload[order][0]
    del payload[bag][dropped]
    found = js.push(payload)
    assert [
        one["field"] for one in found["faults"] if one["fault"] == "short-list"
    ] == [bag]


@pytest.mark.parametrize("state", CHECKED_STATES)
def test_each_result_field_is_found_by_its_own_name(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for name in payload["result_fields"]:
        assert js.called("resultField", name) == payload["result"][name], name


def test_the_result_lookup_answers_nothing_for_a_name_no_field_carries(js: JsRuntime):
    js.push(state_payload("warned"))
    assert js.called("resultField", UNKNOWN_NAME) is None


@pytest.mark.parametrize("state", BOXED_STATES)
def test_each_button_the_open_box_offers_is_found_by_its_own_name(
    js: JsRuntime, state: str
):
    """A button list is the case where position alone is not an identity."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "boxButtons()") == payload["box_buttons"]
    for name in payload["box_buttons"]:
        assert js.called("buttonNamed", name) == payload["buttons"][name], name


def test_the_button_lookup_answers_nothing_for_a_button_no_box_offers(js: JsRuntime):
    js.push(state_payload("warned"))
    assert js.called("buttonNamed", UNKNOWN_NAME) is None


def test_a_repeated_button_name_is_reported_rather_than_drawn_twice(js: JsRuntime):
    payload = state_payload("warned")
    payload["box_buttons"].append(payload["box_buttons"][0])
    found = js.push(payload)
    assert [
        one["where"] for one in found["faults"] if one["fault"] == "duplicate-name"
    ] == ["row:2"]


def test_an_open_box_the_payload_never_listed_is_reported(js: JsRuntime):
    """An unlisted box would draw from an empty widget and say nothing."""
    payload = state_payload("warned")
    payload["box"] = UNKNOWN_NAME
    found = js.push(payload)
    assert [
        one["detail"] for one in found["faults"] if one["fault"] == "unknown-name"
    ] == [UNKNOWN_NAME]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_open_box_check_stays_quiet_on_every_box_the_surface_opens(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    assert payload["box"] in [""] + payload["boxes"], payload["box"]
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "unknown-name"
    ] == []


def test_a_button_the_payload_never_named_is_reported(js: JsRuntime):
    payload = state_payload("warned")
    payload["box_buttons"][0] = UNKNOWN_NAME
    found = js.push(payload)
    assert [
        one["detail"] for one in found["faults"] if one["fault"] == "unknown-name"
    ] == [UNKNOWN_NAME]


@pytest.mark.parametrize("state", CHECKED_STATES)
def test_every_step_the_check_ran_is_a_step_the_surface_names(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "calls()") == payload["calls"]
    assert js.json(API + "stepNames()") == [one[0] for one in payload["calls"]]
    assert set(one[0] for one in payload["calls"]) <= set(payload["call_names"])
    assert js.json(API + "faults()") == []


def test_the_step_check_names_a_step_the_surface_never_declared(js: JsRuntime):
    payload = state_payload("warned")
    payload["calls"].append([UNKNOWN_NAME])
    found = js.push(payload)
    assert [
        one["detail"] for one in found["faults"] if one["fault"] == "unknown-step"
    ] == [UNKNOWN_NAME]


def test_each_step_is_found_by_the_name_it_carries(js: JsRuntime):
    payload = state_payload("warned")
    js.push(payload)
    for one in payload["calls"]:
        assert js.called("stepNamed", one[0])[0] == one[0]
    assert js.called("stepNamed", UNKNOWN_NAME) is None


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_published_lines_rebuild_the_block_the_surface_wrote(
    js: JsRuntime, state: str
):
    """Two lists and one block must be the same words, whichever the screen draws."""
    payload = state_payload(state)
    js.push(payload)
    joined = js.json(API + "lineBreak()")
    assert joined.join(payload["report_lines"]) == payload["report"]
    assert joined.join(payload["box_body_lines"]) == payload["box_body"]
    assert js.json(API + "faults()") == []


def test_the_line_check_names_a_block_its_own_lines_no_longer_build(js: JsRuntime):
    payload = state_payload("warned")
    payload["box_body_lines"][0] = LONG_NAME
    found = js.push(payload)
    assert [one["field"] for one in found["faults"] if one["fault"] == "disagrees"] == [
        "box_body_lines"
    ]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_word_the_screen_draws_as_characters_carries_a_tag(
    js: JsRuntime, state: str
):
    js.push(state_payload(state))
    assert [one for one in js.json(API + "faults()") if one["fault"] == "markup"] == []


@pytest.mark.parametrize(
    "site", ["box_body_lines", "report_lines", "box_title", "status_line"]
)
def test_the_markup_report_names_a_tag_reaching_one_drawn_word(
    js: JsRuntime, site: str
):
    payload = state_payload("warned")
    if site in ("box_body_lines", "report_lines"):
        payload[site][0] = MARKUP_NAME
    else:
        payload[site] = MARKUP_NAME
    found = js.push(payload)
    assert [one["field"] for one in found["faults"] if one["fault"] == "markup"] == [
        site
    ]


def test_the_markup_report_names_a_tag_reaching_one_button_word(js: JsRuntime):
    payload = state_payload("warned")
    payload["buttons"]["yes"]["text"] = MARKUP_NAME
    found = js.push(payload)
    assert [one["field"] for one in found["faults"] if one["fault"] == "markup"] == [
        "buttons"
    ]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_state_the_surface_publishes_claims_a_check_that_never_ran(
    js: JsRuntime, state: str
):
    """A pass drawn where nothing was measured is the claim this screen must refuse."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json(API + "checkRan()") is payload["checked"]
    if not payload["checked"]:
        assert payload["result"] == {}
        assert payload["report"] == ""
        assert payload["box"] == ""
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "unchecked-claim"
    ] == []


@pytest.mark.parametrize("field", ["result", "report", "box"])
def test_the_claim_check_names_a_report_carried_with_no_check_behind_it(
    js: JsRuntime, field: str
):
    payload = state_payload("warned")
    payload["checked"] = False
    found = js.push(payload)
    named = [
        one["field"] for one in found["faults"] if one["fault"] == "unchecked-claim"
    ]
    assert field in named, named


def test_the_claim_check_stays_quiet_where_the_check_did_run(js: JsRuntime):
    payload = state_payload("warned")
    assert payload["checked"] is True
    found = js.push(payload)
    assert [one for one in found["faults"] if one["fault"] == "unchecked-claim"] == []


def test_the_screen_never_calls_an_unreported_market_active(js: JsRuntime):
    """The surface names the word and the module reads it, so no default is drawn."""
    payload = state_payload("warned")
    js.push(payload)
    assert js.called("resultField", "active_reported") is True
    assert js.called("resultField", "market_active") is False
    drawn = [
        one for one in payload["box_body_lines"] if one.startswith("Market active")
    ]
    assert drawn == ["Market active: " + surface.ACTIVE_NO]


HOSTILE_FIELDS: dict = {
    "result missing": ("result", None),
    "result is a list": ("result", []),
    "buttons is text": ("buttons", "a bag"),
    "box_buttons is a bag": ("box_buttons", {}),
    "layout is null": ("layout", None),
    "box_widgets is a list": ("box_widgets", []),
    "boxes is a number": ("boxes", 7),
    "box_body_lines is text": ("box_body_lines", "one"),
    "report_lines is a bag": ("report_lines", {}),
    "calls is a bag": ("calls", {}),
    "call_names is text": ("call_names", "one"),
    "outcomes is null": ("outcomes", None),
    "creates_bot is a list": ("creates_bot", []),
    "actions is a list": ("actions", []),
    "skin is a list": ("skin", []),
    "timers is null": ("timers", None),
    "box is a number": ("box", 7),
    "box_title is a number": ("box_title", 7),
    "status_line is nan": ("status_line", "nan"),
    "status_level is inf": ("status_level", "inf"),
    "answered is text": ("answered", "yes"),
    "checked is text": ("checked", "yes"),
    "outcome is unknown": ("outcome", UNKNOWN_NAME),
    "warning_count is text": ("warning_count", "two"),
    "method disagrees": ("method", UNKNOWN_NAME),
    "a check that did not run": ("checked", False),
    "a result nobody knows": ("result", {"success": None}),
    "a long name": ("box_title", LONG_NAME),
    "markup": ("box_title", MARKUP_NAME),
    "a newline": ("box_title", NEWLINE_NAME),
    "a huge whole number": ("warning_count", HUGE_WHOLE_NUMBER),
    "minus infinity": ("warning_count", "-inf"),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_FIELDS))
def test_a_hostile_field_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    """A payload the surface would never send must report, never raise."""
    name, value = HOSTILE_FIELDS[case]
    payload = state_payload("warned")
    payload[name] = value
    found = js.push(payload)
    assert isinstance(found["faults"], list), case
    assert js.json(API + "isLoaded()") is True, case
    assert isinstance(js.json(API + "kinds()"), dict), case
    assert isinstance(js.json(API + "notPlainData()"), list), case
    assert isinstance(js.json(API + "boxButtons()"), list), case
    assert isinstance(js.json(API + "bodyLines()"), list), case
    assert isinstance(js.json(API + "warnings()"), list), case
    assert isinstance(js.json(API + "resultNames()"), list), case
    assert isinstance(js.json(API + "stepNames()"), list), case


def test_a_result_whose_success_nobody_knows_is_never_read_as_a_pass(js: JsRuntime):
    """Unknown has to read as unknown, never as the pass a true would mean."""
    payload = state_payload("warned")
    payload["result"] = {"success": None}
    js.push(payload)
    assert js.called("resultField", "success") is None
    assert js.called("resultField", "market_active") is None


def test_the_unknown_result_check_reads_a_measured_pass_as_a_pass(js: JsRuntime):
    js.push(state_payload("warned"))
    assert js.called("resultField", "success") is True


HOSTILE_LINES: dict = {
    "a null line": None,
    "a number where text belongs": 7,
    "text where a number belongs": "one",
    "not a number": "nan",
    "infinity": "inf",
    "minus infinity": "-inf",
    "a huge whole number": HUGE_WHOLE_NUMBER,
    "a long name": LONG_NAME,
    "markup": MARKUP_NAME,
    "a newline": NEWLINE_NAME,
    "a bag line": {},
    "a list line": [],
}


@pytest.mark.parametrize("case", sorted(HOSTILE_LINES))
def test_a_hostile_body_line_is_reported_and_the_module_still_answers(
    js: JsRuntime, case: str
):
    payload = state_payload("warned")
    payload["box_body_lines"][0] = HOSTILE_LINES[case]
    found = js.push(payload)
    assert isinstance(found["faults"], list), case
    assert isinstance(js.json(API + "bodyLines()"), list), case
    assert isinstance(js.json(API + "kinds()"), dict), case


def test_the_hostile_sweep_would_have_seen_a_module_that_stopped_answering(
    js: JsRuntime,
):
    """A module that raised on one hostile value would answer nothing at all."""
    js.push(7)
    assert js.json(API + "bodyLines()") == []
    assert js.json(API + "boxButtons()") == []
    assert js.json(API + "warnings()") == []
    assert js.json(API + "isLoaded()") is False


#: An empty tag pair a rich-text widget swallows and a plain one lays out.
MARKUP_PROBE = "<span></span>wire"
PLAIN_PROBE = "wire"


def laid_out(widget: Any) -> int:
    """The width one widget asks for to lay its caller text out."""
    return int(widget.minimumSizeHint().width())


def a_label(text: str) -> Any:
    from PySide6.QtWidgets import QLabel

    return QLabel(text)


def a_message_box(text: str) -> Any:
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox()
    box.setText(text)
    return box


def a_button(text: str) -> Any:
    from PySide6.QtWidgets import QPushButton

    return QPushButton(text)


def a_wizard_box(text: str) -> Any:
    """The box the bot wizard raises, at the text format the surface publishes."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox()
    box.setTextFormat(Qt.TextFormat(surface.TEXT_FORMAT_VALUE))
    box.setText(text)
    return box


def test_the_box_the_wizard_raises_lays_a_markup_symbol_out_as_characters(qapp):
    """A symbol carrying tags must reach the operator whole, never as emphasis."""
    assert qapp is not None
    assert laid_out(a_wizard_box(MARKUP_PROBE)) > laid_out(
        a_wizard_box(PLAIN_PROBE)
    ), "the wizard box laid the markup out no wider, so it read the tags"


def test_the_markup_format_check_would_see_a_box_left_reading_rich_text(qapp):
    """A box at Qt's own default lays both texts out at the very same width."""
    assert qapp is not None
    assert laid_out(a_message_box(MARKUP_PROBE)) == laid_out(a_message_box(PLAIN_PROBE))


#: Each widget beside the call that reads the width it asks for.
SCREEN_WIDGETS = {"QPushButton": (a_button, laid_out)}
RICH_TEXT_WIDGETS = {
    "QLabel": (a_label, laid_out),
    "QMessageBox": (a_message_box, laid_out),
}
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
def test_the_widgets_this_screen_uses_that_do_read_markup_are_named(qapp, kind: str):
    """QLabel and QMessageBox lay MARKUP_PROBE out exactly as wide as PLAIN_PROBE."""
    assert qapp is not None
    build_widget, asked = RICH_TEXT_WIDGETS[kind]
    assert asked(build_widget(MARKUP_PROBE)) == asked(build_widget(PLAIN_PROBE))


@pytest.mark.parametrize("kind", sorted(EVERY_WIDGET))
def test_the_markup_measurement_reads_a_longer_text_as_a_wider_layout(qapp, kind: str):
    """A width that never moved would read every widget as one that reads markup."""
    assert qapp is not None
    build_widget, asked = EVERY_WIDGET[kind]
    assert asked(build_widget(PLAIN_PROBE * 8)) > asked(build_widget(PLAIN_PROBE))


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
            "the page never defined the pre-flight check module in "
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
    "paddingTop",
    "paddingLeft",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "window.HOST.setAttribute('data-part', 'preflight-check-page');"
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
    "        hidden: el.hidden, disabled: el.disabled === true,"
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


def draw_screen(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        SETTER + "(JSON.parse(window.PAYLOAD));" + API + "fill(window.HOST, null);"
    )
    return json.loads(browser.js(READ_PARTS))


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def with_part(parts: list, name: str) -> list:
    return [one for one in parts if one["path"].split("/")[-1] == name]


def test_the_screen_fills_the_named_space_the_wizard_left_for_it(browser: Browser):
    """The bot wizard names one space and this screen fills it."""
    parts = draw_screen(browser, state_payload("warned"))
    assert browser.parsed(API + "spacePart") == "preflight-check-page"
    assert at_path(parts, "preflight-check"), "the screen drew nothing into the space"


def test_every_child_the_page_draws_carries_its_own_name(browser: Browser):
    """A child with no name is a child no check can read."""
    draw_screen(browser, state_payload("warned"))
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named, f"{every - named} drawn children carry no data-part"
    assert named > 0


def test_the_named_child_check_would_see_one_unnamed_child(browser: Browser):
    draw_screen(browser, state_payload("warned"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    every, named = browser.parsed(COUNT_ELEMENTS)
    assert every == named + 1


@pytest.mark.parametrize("state", BOXED_STATES)
def test_every_body_line_the_surface_wrote_becomes_one_drawn_line_in_order(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_screen(browser, payload)
    drawn = with_part(parts, "body-line")
    assert [one["text"] for one in drawn] == payload["box_body_lines"]
    assert [one["attrs"]["data-index"] for one in drawn] == [
        str(at) for at in range(len(payload["box_body_lines"]))
    ]


def test_the_body_line_check_would_see_a_body_drawn_as_one_piece(browser: Browser):
    payload = state_payload("warned")
    payload["box_body_lines"] = []
    parts = draw_screen(browser, payload)
    assert with_part(parts, "body-line") == []
    assert with_part(parts, "box-body")[0]["attrs"]["data-count"] == "0"


@pytest.mark.parametrize("state", BOXED_STATES)
def test_every_button_the_open_box_offers_is_drawn_and_named(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_screen(browser, payload)
    drawn = with_part(parts, "box-button")
    assert [one["attrs"]["data-key"] for one in drawn] == payload["box_buttons"]
    for one in drawn:
        button = payload["buttons"][one["attrs"]["data-key"]]
        assert one["text"] == button["text"]
        assert one["attrs"]["data-value"] == str(button["value"])
        assert one["attrs"]["data-outcome"] == button["outcome"]
        assert one["disabled"] is (button["enabled"] is False)


def test_the_button_check_would_see_a_disabled_button(browser: Browser):
    payload = state_payload("warned")
    payload["buttons"]["no"]["enabled"] = False
    parts = draw_screen(browser, payload)
    drawn = {one["attrs"]["data-key"]: one for one in with_part(parts, "box-button")}
    assert drawn["no"]["disabled"] is True
    assert drawn["yes"]["disabled"] is False


def test_the_default_button_the_box_names_is_marked_on_the_button_that_carries_it(
    browser: Browser,
):
    payload = state_payload("warned")
    parts = draw_screen(browser, payload)
    drawn = {one["attrs"]["data-key"]: one for one in with_part(parts, "box-button")}
    fallback = payload["warning_widget"]["default_button_value"]
    marked = [
        name for name, one in drawn.items() if one["attrs"]["data-default"] == "true"
    ]
    assert marked == [
        name
        for name in payload["box_buttons"]
        if payload["buttons"][name]["value"] == fallback
    ]


def test_the_default_button_check_would_see_a_box_that_names_none(browser: Browser):
    payload = state_payload("blocked")
    parts = draw_screen(browser, payload)
    drawn = with_part(parts, "box-button")
    assert payload["failure_widget"]["default_button_value"] == 0
    assert [one for one in drawn if one["attrs"]["data-default"] == "true"] == []


def test_the_box_draws_its_children_in_the_order_the_layout_names(browser: Browser):
    """Each child is found by its own name, never by where it sits."""
    payload = state_payload("warned")
    parts = draw_screen(browser, payload)
    drawn = [
        one["path"].split("/")[-1]
        for one in parts
        if one["path"].startswith("preflight-check/preflight-box/")
        and one["path"].count("/") == 2
    ]
    assert drawn == [
        "box-title",
        "box-icon",
        "box-spacer",
        "box-body",
        "box-button-box",
    ]
    named = {
        "box-icon": "icon",
        "box-spacer": "spacer",
        "box-body": "text",
        "box-button-box": "button_box",
    }
    for part, child in named.items():
        one = with_part(parts, part)[0]
        expected = payload["layout"]["child_object_names"].get(child)
        assert one["attrs"].get("data-object-name") == expected, part


def test_the_child_order_check_would_see_a_layout_that_moved_one_child(
    browser: Browser,
):
    payload = state_payload("warned")
    payload["layout"]["order"] = list(reversed(payload["layout"]["order"]))
    parts = draw_screen(browser, payload)
    drawn = [
        one["path"].split("/")[-1]
        for one in parts
        if one["path"].startswith("preflight-check/preflight-box/")
        and one["path"].count("/") == 2
    ]
    assert drawn == [
        "box-title",
        "box-button-box",
        "box-body",
        "box-spacer",
        "box-icon",
    ]


def test_the_box_takes_the_padding_and_the_gap_the_layout_publishes(browser: Browser):
    """The applied value is read against a probe built from the whole declaration."""
    payload = state_payload("warned")
    parts = draw_screen(browser, payload)
    box = with_part(parts, "preflight-box")[0]
    margins = payload["layout"]["margins_px"]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps(
            {
                "paddingTop": str(margins[1]) + "px",
                "paddingLeft": str(margins[0]) + "px",
            }
        )
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert box["style"]["paddingTop"] == probe["paddingTop"]
    assert box["style"]["paddingLeft"] == probe["paddingLeft"]


def test_the_padding_check_would_see_a_box_taking_a_different_margin(
    browser: Browser,
):
    payload = state_payload("warned")
    parts = draw_screen(browser, payload)
    box = with_part(parts, "preflight-box")[0]
    probe = browser.parsed(
        "window.probeAssign("
        + json.dumps({"paddingTop": "0px"})
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert box["style"]["paddingTop"] != probe["paddingTop"]


def test_the_screen_declares_no_skin_so_the_box_takes_no_colour_of_its_own(
    browser: Browser,
):
    """The surface publishes an empty sheet for both boxes, and neither may paint."""
    payload = state_payload("warned")
    assert payload["skin"] == {}
    assert payload["warning_widget"]["style_sheet"] == ""
    parts = draw_screen(browser, payload)
    box = with_part(parts, "preflight-box")[0]
    plain = browser.parsed("window.probeAssign({}, JSON.parse(window.STYLE_NAMES))")
    assert box["style"]["color"] == plain["color"]
    assert box["style"]["backgroundColor"] == plain["backgroundColor"]


def test_the_unpainted_check_would_see_a_box_that_did_take_a_colour(
    browser: Browser,
):
    draw_screen(browser, state_payload("warned"))
    style = browser.parsed(API + "paintedStyle(" + json.dumps(OTHER_COLOUR) + ")")
    probe = browser.parsed(
        "window.probeAssign(" + json.dumps(style) + ", JSON.parse(window.STYLE_NAMES))"
    )
    plain = browser.parsed("window.probeAssign({}, JSON.parse(window.STYLE_NAMES))")
    assert probe["color"] != plain["color"]


def test_the_status_line_draws_the_words_and_the_level_the_surface_carries(
    browser: Browser,
):
    for state in CHECKED_STATES:
        payload = state_payload(state)
        parts = draw_screen(browser, payload)
        line = with_part(parts, "status-line")[0]
        assert line["text"] == payload["status_line"], state
        assert line["attrs"]["data-level"] == payload["status_level"], state
        assert line["hidden"] is (payload["status_line"] == ""), state


def test_the_status_line_is_hidden_where_the_surface_wrote_none(browser: Browser):
    payload = state_payload("fresh")
    assert payload["status_line"] == ""
    parts = draw_screen(browser, payload)
    assert with_part(parts, "status-line")[0]["hidden"] is True


def test_the_outcome_mark_carries_the_outcome_its_level_and_whether_it_makes_a_bot(
    browser: Browser,
):
    for state in STATE_NAMES:
        payload = state_payload(state)
        parts = draw_screen(browser, payload)
        mark = with_part(parts, "outcome-mark")[0]
        assert mark["attrs"]["data-outcome"] == payload["outcome"], state
        assert (
            mark["attrs"]["data-level"] == payload["outcome_levels"][payload["outcome"]]
        ), state
        assert (
            mark["attrs"]["data-creates-bot"]
            == str(payload["creates_bot"][payload["outcome"]]).lower()
        ), state
        assert mark["attrs"]["data-checked"] == str(payload["checked"]).lower(), state


def test_the_outcome_mark_check_would_see_two_states_that_ended_apart(
    browser: Browser,
):
    ended = set()
    for state in STATE_NAMES:
        parts = draw_screen(browser, state_payload(state))
        ended.add(with_part(parts, "outcome-mark")[0]["attrs"]["data-outcome"])
    assert len(ended) > 1, ended


def test_no_box_is_drawn_at_all_where_the_surface_opened_none(browser: Browser):
    """A screen drawing a box with nothing behind it would claim a check ran."""
    for state in ("fresh", "clean", "skipped"):
        payload = state_payload(state)
        assert payload["box"] == ""
        parts = draw_screen(browser, payload)
        assert with_part(parts, "preflight-box") == [], state
        assert with_part(parts, "box-button") == [], state


def test_the_no_box_check_would_see_a_box_the_surface_did_open(browser: Browser):
    parts = draw_screen(browser, state_payload("warned"))
    assert len(with_part(parts, "preflight-box")) == 1


def test_the_screen_refuses_markup_a_hostile_body_line_carries(browser: Browser):
    """React writes the tags as text, so no element reaches the document."""
    payload = state_payload("warned")
    payload["box_body_lines"][0] = MARKUP_NAME
    parts = draw_screen(browser, payload)
    drawn = with_part(parts, "body-line")[0]
    assert drawn["text"] == MARKUP_NAME
    assert "<img" not in drawn["html"]
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_screen_refuses_markup_a_hostile_button_word_carries(browser: Browser):
    payload = state_payload("warned")
    payload["buttons"]["yes"]["text"] = MARKUP_NAME
    parts = draw_screen(browser, payload)
    drawn = {one["attrs"]["data-key"]: one for one in with_part(parts, "box-button")}
    assert drawn["yes"]["text"] == MARKUP_NAME
    assert "<b>" not in drawn["yes"]["html"]


def test_the_markup_refusal_would_see_a_tag_the_page_did_run(browser: Browser):
    draw_screen(browser, state_payload("warned"))
    browser.js("window.HOST.firstChild.insertAdjacentHTML('beforeend', '<img>');")
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 1


def test_a_two_hundred_character_line_stretches_the_body_rather_than_clipping(
    browser: Browser,
):
    """A CSS block grows to fit where Qt clips, so the width is reported."""
    payload = state_payload("warned")
    payload["box_body_lines"][0] = LONG_NAME
    wide = with_part(draw_screen(browser, payload), "body-line")[0]
    narrow = with_part(draw_screen(browser, state_payload("warned")), "body-line")[0]
    assert wide["width"] >= narrow["width"]


def test_every_result_field_reaches_the_document_named_by_its_own_field(
    browser: Browser,
):
    payload = state_payload("warned")
    parts = draw_screen(browser, payload)
    drawn = with_part(parts, "result-field")
    assert [one["attrs"]["data-key"] for one in drawn] == payload["result_fields"]
    for one in drawn:
        name = one["attrs"]["data-key"]
        printed = browser.js(
            "String(JSON.parse(window.PAYLOAD).result[" + json.dumps(name) + "])"
        )
        assert one["attrs"]["data-value"] == printed, name


def test_the_result_field_check_would_see_a_state_that_holds_no_result(
    browser: Browser,
):
    payload = state_payload("fresh")
    assert payload["result"] == {}
    parts = draw_screen(browser, payload)
    drawn = with_part(parts, "result-field")
    assert [one["attrs"]["data-shown"] for one in drawn] == ["false"] * len(drawn)


def test_pressing_a_button_records_the_name_the_wizard_sends_back(browser: Browser):
    """The wizard answers with the button name, so the press must carry it."""
    draw_screen(browser, state_payload("warned"))
    browser.js("window.HOST.querySelector('[data-part=\"box-button\"]').click();")
    assert browser.parsed(API + "presses()") == ["yes"]


def test_the_press_check_would_see_a_button_nobody_pressed(browser: Browser):
    draw_screen(browser, state_payload("warned"))
    assert browser.parsed(API + "presses()") == []


def test_this_file_holds_no_carriage_return():
    """A file grew a Windows line ending the build machine reads as text."""
    for path in (MODULE_PATH, Path(__file__)):
        assert path.read_bytes().count(b"\r") == 0, path.name


def test_the_carriage_return_counter_can_report():
    """The carriage-return counter reports nothing whatever a file holds."""
    assert b"a\r\nb".count(b"\r") == 1
    assert b"a\nb".count(b"\r") == 0


READS_FIRST = ("header_strip.js", "table_cells.js")


def test_the_renderer_runs_this_module_after_the_pieces_it_reads():
    """`header_strip.js` and `table_cells.js` carry the style this draws with."""
    order = load_order()
    assert runs_after(order, MODULE_PATH.name, *READS_FIRST), order


def test_the_order_reading_answers_no_for_the_pieces_the_other_way_round():
    """The same reading of an order that runs this module first."""
    assert not runs_after([MODULE_PATH.name, *READS_FIRST], MODULE_PATH.name, *READS_FIRST)
    assert not runs_after(list(READS_FIRST), MODULE_PATH.name, *READS_FIRST)
