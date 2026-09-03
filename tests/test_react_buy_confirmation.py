"""``buy_confirmation.js`` against ``buy_confirmation_surface.py``, run in
QJSEngine and drawn in QWebEngineView.

This dialog stands between the operator and a real order, so every check
here maps to a defect class named in the conversion brief: a shown figure
that is not the value the order carries, a non-finite number reaching the
bridge, a confirm control usable before its figures are, caller text read
as markup, a colour written in the trap Qt and a browser disagree on, and
a bag keyed by something a browser would move to the front.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import buy_confirmation_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    load_order,
    new_engine,
    runs_after,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "buy_confirmation.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body can write into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

SETTER = "acervatorSetBuyConfirmation"
API = "acervatorBuyConfirmation."

#: The merged pieces the page loads beside this module, needed at call time.
SHARED_MODULES = (WEB / "header_strip.js", WEB / "shared_widgets.js")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2

LONG_NAME = "z" * 200
MARKUP_SYMBOL = "A<b>&/USD"
MARKUP_REASON = "a <b>bold</b> & risky <script>alert(1)</script> reason"
OTHER_COLOUR = "#00ffcc"
SWAPPED_ALPHA = "#123a63ff"
UNKNOWN_NAME = "no-such-name"


# -- payloads, always through the real surface --------------------------


def raw_payload(
    symbol: str = "BONK/USD",
    reason: str = "Over target",
    cost_usd: float = 12.3456,
    price: float = 0.00001234,
    amount_asset: float = 1000000.5,
    holdings_before: float = 250.125,
    target_balance: float = 500.0,
    button: str | None = None,
) -> dict:
    """The surface's own payload for one request, never through the encoder."""
    model = surface.BuyConfirmationModel()
    return surface.build_view_model(
        model,
        symbol,
        reason,
        cost_usd,
        price,
        amount_asset,
        holdings_before,
        target_balance,
        button,
    )


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def state_payload(**kwargs: Any) -> dict:
    return as_json(raw_payload(**kwargs))


STATES: dict = {
    "plain": {},
    "empty": {
        "symbol": "",
        "reason": "",
        "cost_usd": 0.0,
        "price": 0.0,
        "amount_asset": 0.0,
        "holdings_before": 0.0,
        "target_balance": 0.0,
    },
    "zero_price": {
        "symbol": "ETH/USD",
        "reason": "Zero price",
        "cost_usd": 10.0,
        "price": 0.0,
        "amount_asset": 0.0,
        "holdings_before": 5.0,
        "target_balance": 100.0,
    },
    "negative": {
        "symbol": "SOL/USD",
        "reason": "Negative everything",
        "cost_usd": -5.5,
        "price": -0.25,
        "amount_asset": -3.0,
        "holdings_before": -7.5,
        "target_balance": -100.0,
    },
    "very_large": {
        "symbol": "XRP/USD",
        "reason": "Very large numbers",
        "cost_usd": 1e18,
        "price": 9.87654321e12,
        "amount_asset": 1.23456789e15,
        "holdings_before": 1e20,
        "target_balance": 1e21,
    },
    "markup": {
        "symbol": MARKUP_SYMBOL,
        "reason": MARKUP_REASON,
        "cost_usd": 1.0,
        "price": 1.0,
        "amount_asset": 1.0,
        "holdings_before": 1.0,
        "target_balance": 1.0,
    },
    "answered": {"symbol": "BONK/USD", "button": surface.YES},
}
STATE_NAMES = tuple(STATES)


def built(name: str, **overrides: Any) -> dict:
    return state_payload(**dict(STATES[name], **overrides))


# -- the QJSEngine runtime ------------------------------------------------


class JsRuntime(JsEngine):
    module_path = MODULE_PATH
    setter = SETTER

    def __init__(self, engine: Any, source: str) -> None:
        super().__init__(engine, source)
        for path in SHARED_MODULES:
            loaded = engine.evaluate(path.read_text(encoding="utf-8"), path.name)
            assert not loaded.isError(), path.name + " -> " + loaded.toString()

    def called(self, method: str, *args: Any) -> Any:
        parts = []
        for at, value in enumerate(args):
            name = "ARG" + str(at)
            self.bind_json(name, value)
            parts.append("JSON.parse(" + name + ")")
        return self.json(API + method + "(" + ", ".join(parts) + ")")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


def declared_fields(js: JsRuntime) -> list:
    return js.json(API + "declaredNames()")


# -- 1. the module runs, and a broken one is still caught ----------------


def test_the_engine_the_page_uses_runs_this_module(js: JsRuntime):
    assert js.json("typeof " + SETTER) == "function"
    assert js.json(API + "method") == surface.METHOD


def test_the_engine_check_reports_a_module_body_it_cannot_parse(js: JsRuntime):
    engine = js.engine_of()
    engine.evaluate("var window = this;")
    broken = engine.evaluate("(function (global) { var = ; })(window);", MODULE_PATH.name)
    assert broken.isError(), "the engine accepted a broken module body"
    whole = engine.evaluate(MODULE_SOURCE, MODULE_PATH.name)
    assert not whole.isError(), whole.toString()


def test_the_module_is_registered_and_runs_after_its_shared_pieces():
    order = load_order()
    assert MODULE_PATH.name in order
    assert runs_after(
        order,
        MODULE_PATH.name,
        "header_strip.js",
        "shared_widgets.js",
        "design_tokens.js",
    )


def test_the_missing_dependency_check_would_see_the_module_absent():
    """`runs_after` reports false rather than crashing when a name is absent."""
    assert runs_after(["shared_widgets.js"], MODULE_PATH.name, "header_strip.js") is False
    assert runs_after(load_order(), UNKNOWN_NAME, "header_strip.js") is False


# -- 2. every declared field reaches the module ---------------------------


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(js: JsRuntime, state: str):
    payload = built(state)
    js.push(payload)
    named = declared_fields(js)
    missing = sorted(set(payload) - set(named))
    assert not missing, f"{len(missing)} published fields the module never names: {missing}"
    extra = sorted(set(named) - set(payload))
    assert not extra, f"the module names fields the surface has none of: {extra}"
    for name in named:
        assert js.called("field", name) == payload[name], name


def test_a_missing_field_is_reported_by_the_whole_payload_check(js: JsRuntime):
    payload = built("plain")
    del payload["reason_text"]
    found = js.push(payload)
    assert [
        one["field"] for one in found["faults"] if one["fault"] == "missing"
    ] == ["reason_text"]
    assert "reason_text" in declared_fields(js)


# -- 3. a figure shown is the figure the order carries --------------------


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_detail_row_value_is_a_substring_of_the_dialogs_own_details_text(
    js: JsRuntime, state: str
):
    """A value the module would draw must be the dialog's own, unreformatted."""
    payload = built(state)
    js.push(payload)
    for row in payload["detail_row_order"]:
        value = js.called("detailRowValue", row)
        assert value == payload["detail_row_values"][row], row
        if value:
            assert value in payload["details_text"], (row, value)


def test_the_row_order_and_the_label_and_value_bags_agree_in_count(js: JsRuntime):
    payload = built("plain")
    found = js.push(payload)
    assert found["declared"]["rows"] == len(payload["detail_row_order"])
    assert found["held"]["rows"] == len(payload["detail_row_values"])
    assert found["declared"]["rows"] == found["held"]["rows"]


def test_a_row_the_labels_bag_lost_is_reported(js: JsRuntime):
    payload = built("plain")
    dropped = payload["detail_row_order"][0]
    del payload["detail_row_labels"][dropped]
    found = js.push(payload)
    assert [
        one["field"] for one in found["faults"] if one["fault"] == "short-list"
    ] == ["detail_row_labels"]


def test_the_amount_row_carries_the_bases_symbol_not_a_recomputed_one(js: JsRuntime):
    """The browser must never re-derive the base currency from the symbol."""
    payload = state_payload(symbol="BONK/USD", amount_asset=7.0)
    js.push(payload)
    assert js.called("detailRowValue", "amount_asset") == payload["detail_row_values"][
        "amount_asset"
    ]
    assert "BONK" in js.called("detailRowValue", "amount_asset")


def test_the_after_this_buy_row_is_the_surfaces_own_arithmetic(js: JsRuntime):
    for state in ("plain", "negative", "very_large", "zero_price"):
        payload = built(state)
        js.push(payload)
        assert js.called("detailRowValue", "after_usd") == payload["detail_row_values"][
            "after_usd"
        ]


def test_the_reason_text_the_module_answers_is_the_dialogs_own(js: JsRuntime):
    for state in STATE_NAMES:
        payload = built(state)
        js.push(payload)
        assert js.json(API + "reasonText()") == payload["reason_text"]


# -- 4. non-finite numbers are reported, never painted --------------------


def test_the_bridge_never_writes_a_bare_nan_or_infinity():
    """`desktop_bridge.encode_frame` sanitises every response, this one included."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    line = json.dumps(
        {
            "id": 1,
            "method": surface.METHOD,
            "params": {
                "reset": True,
                "symbol": "BONK/USD",
                "reason": "over target",
                "cost_usd": float("nan"),
                "price": 1.0,
                "amount_asset": 1.0,
                "holdings_before": 1.0,
                "target_balance": 1.0,
            },
        }
    )
    frame = desktop_bridge.encode_frame(desktop_bridge.handle_line(line, registry))
    # A bare NaN/Infinity has no JSON spelling; a frame carrying one would
    # raise here, and the frontend's own parser would refuse the whole line.
    decoded = json.loads(frame.decode("utf-8"))
    assert decoded["ok"] is True
    # cost_usd never leaves the surface as a raw number; it is folded into
    # a formatted string, so the sanitiser has nothing non-finite to erase.
    assert "nan" in decoded["result"]["detail_row_values"]["cost_usd"].lower()


def test_the_numeric_check_names_a_non_finite_timeout(js: JsRuntime):
    payload = built("plain")
    js.bind_json("PAYLOAD", payload)
    js.run(SETTER + "(Object.assign(JSON.parse(PAYLOAD), { timeout_sec: 0 / 0 }));")
    faults = js.json(API + "faults()")
    assert [one["field"] for one in faults if one["fault"] == "non-finite"] == [
        "timeout_sec"
    ]


def test_the_numeric_check_stays_quiet_on_every_state(js: JsRuntime):
    for state in STATE_NAMES:
        js.push(built(state))
        assert [
            one for one in js.json(API + "faults()") if one["fault"] == "non-finite"
        ] == []


# -- 5. the confirm control is unusable before its figures are ------------


def test_the_screen_draws_nothing_for_a_payload_that_has_not_arrived(js: JsRuntime):
    """`Screen` returns null before `setScreen` ever ran, matching a pending load."""
    assert js.json(API + "isLoaded()") is False
    assert js.json(API + "reasonText()") is None


def test_a_payload_that_is_not_an_object_is_reported_not_thrown(js: JsRuntime):
    found = js.push(7)
    assert found["faults"][0]["fault"] == "not-an-object"
    assert js.json(API + "isLoaded()") is False


# -- 6. caller text is drawn as characters, never as markup ----------------


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_word_this_screen_draws_carries_an_unescaped_tag_fault(js: JsRuntime, state: str):
    payload = built(state)
    js.push(payload)
    markup = [one for one in js.json(API + "faults()") if one["fault"] == "markup"]
    if state == "markup":
        fields = sorted(one["field"] for one in markup)
        assert "reason_text" in fields
        assert "detail_row_values" in fields
    else:
        assert markup == []


def test_the_details_text_field_itself_is_never_swept_for_markup(js: JsRuntime):
    """`details_text` is Qt rich text this screen never draws as characters."""
    payload = built("markup")
    js.push(payload)
    faults = js.json(API + "faults()")
    assert not any(one["field"] == "details_text" for one in faults)
    assert "<b>" in payload["details_text"]


# -- 7. the colour trap: Qt's eight-digit alpha byte -----------------------


def test_the_alpha_sweep_names_the_eight_digit_shape_and_no_other(js: JsRuntime):
    js.push(built("plain"))
    assert js.called("isSwappedAlpha", SWAPPED_ALPHA) is True
    assert js.called("isSwappedAlpha", OTHER_COLOUR) is False
    assert js.called("isSwappedAlpha", None) is False


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_sheet_the_surface_ships_carries_the_swapped_alpha_shape(js: JsRuntime, state: str):
    js.push(built(state))
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "swapped-alpha"
    ] == []


def test_the_alpha_sweep_names_a_colour_written_with_eight_digits(js: JsRuntime):
    payload = built("plain")
    payload["reason_label"]["style_sheet"] = "color: " + SWAPPED_ALPHA + ";"
    found = js.push(payload)
    swapped = [one for one in found["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_the_alpha_sweep_reads_a_colour_inside_a_button_sheet(js: JsRuntime):
    payload = built("plain")
    payload["buttons"]["yes"]["style_sheet"] = "background-color: " + SWAPPED_ALPHA + ";"
    found = js.push(payload)
    swapped = [one for one in found["faults"] if one["fault"] == "swapped-alpha"]
    assert [one["detail"] for one in swapped] == [SWAPPED_ALPHA]


def test_no_colour_this_screen_ships_needs_the_rgba_alpha_fraction():
    """`rgba()` is not called by this surface; every colour here is opaque."""
    for token in (surface.YES_SURFACE, surface.NO_SURFACE, surface.REASON_COLOR):
        assert "rgba(" not in surface.STYLE_SHEET
        assert len(token.lstrip("#")) in (3, 6)


# -- 8. no bag is keyed by something a browser would move ------------------


def test_the_reordered_key_check_names_a_digit_key_and_no_other(js: JsRuntime):
    js.push(built("plain"))
    assert js.called("isReorderedKey", "0") is True
    assert js.called("isReorderedKey", "yes") is False
    assert js.called("isReorderedKey", "") is False


@pytest.mark.parametrize("state", STATE_NAMES)
def test_no_bag_the_surface_publishes_carries_a_key_a_browser_would_move(
    js: JsRuntime, state: str
):
    js.push(built(state))
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "reordered-key"
    ] == []


def test_the_bag_order_check_names_a_digit_key_put_into_a_published_bag(js: JsRuntime):
    payload = built("plain")
    payload["buttons"]["0"] = {"text": "x", "enabled": True, "style_sheet": ""}
    found = js.push(payload)
    moved = [one for one in found["faults"] if one["fault"] == "reordered-key"]
    assert [one["detail"] for one in moved] == ["0"]


# -- 9. every answer the payload carries is one of the four ----------------


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_published_answer_is_one_of_the_four(js: JsRuntime, state: str):
    js.push(built(state))
    assert [
        one for one in js.json(API + "faults()") if one["fault"] == "unknown-name"
    ] == []


def test_the_answer_check_names_a_result_value_outside_the_four(js: JsRuntime):
    payload = built("plain")
    payload["result_value"] = UNKNOWN_NAME
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "unknown-name"]
    assert [one["field"] for one in named] == ["result_value"]


# -- 10. the literal scan: the module holds no value of its own -----------


def test_the_module_writes_no_number():
    found = js_literals(MODULE_SOURCE)
    assert not found["numbers"], f"buy_confirmation.js holds numeric literals: {found['numbers']}"


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"buy_confirmation.js holds colour literals: {found}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    found = js_literals(MODULE_SOURCE)
    assert not found["slashes"], (
        "buy_confirmation.js holds a slash outside a comment, unread by the scan: "
        f"{found['slashes']}"
    )


def shown_values() -> set:
    found: set = set()
    for state in STATE_NAMES:
        payload = built(state)
        found |= {payload["reason_text"]}
        found |= set(payload["detail_row_values"].values())
        found |= {one["text"] for one in payload["buttons"].values()}
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

    for state in STATE_NAMES:
        walk(built(state))
    return {one for one in found if one}


SHOWN_VALUES = shown_values()
MODULE_LITERALS = js_literals(MODULE_SOURCE)
BARE = built("plain")

#: Every published word the module may legitimately write: field names,
#: bag keys and the four answers, never a value the screen draws.
NAMED_WORDS = sorted(
    set(BARE)
    | set(BARE["widget"])
    | set(BARE["layout"])
    | set(BARE["layout"]["order"])
    | set(BARE["button_row"])
    | set(BARE["buttons"])
    | set(BARE["buttons"]["yes"])
    | set(BARE["reason_label"])
    | set(BARE["details_label"])
    | set(BARE["separator"])
    | set(BARE["answers"])
    | set(BARE["detail_row_order"])
    | {surface.METHOD}
)


def test_no_string_in_the_module_equals_a_value_the_screen_shows():
    written = sorted(set(MODULE_LITERALS["strings"]) & SHOWN_VALUES)
    assert not written, f"buy_confirmation.js spells out screen values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & published_strings())
    assert set(written) <= set(NAMED_WORDS), (
        "the module names published strings the list does not allow: "
        f"{sorted(set(written) - set(NAMED_WORDS))}"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_screen_shows():
    overlap = sorted(set(NAMED_WORDS) & SHOWN_VALUES)
    assert not overlap, f"these named words are values the screen shows: {overlap}"


WRITTEN_LINES: dict = {
    "colour": 'var written = "' + OTHER_COLOUR + '";',
    "reason_shown": 'var written = "' + built("plain")["reason_text"] + '";',
    "button_text": 'var written = "' + surface.YES_TEXT + '";',
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


def test_each_written_literal_is_caught_in_the_module_file_itself():
    """The original is read inside the swap so no other worker's copy is written."""
    import hashlib

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


# -- 11. the bridge round trip: load, then answer --------------------------


FAKE_BRIDGE = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.parse(JSON.stringify(params))]);"
    "  return Promise.resolve(JSON.parse(RESPONSE)); } };"
)


def test_load_sends_a_reset_with_the_seven_request_fields(js: JsRuntime):
    js.bind_json("RESPONSE", built("plain"))
    js.run(FAKE_BRIDGE)
    fields = {
        "symbol": "BONK/USD",
        "reason": "Over target",
        "cost_usd": 1.0,
        "price": 2.0,
        "amount_asset": 3.0,
        "holdings_before": 4.0,
        "target_balance": 5.0,
    }
    js.bind_json("FIELDS", fields)
    js.run(API + "load(null, JSON.parse(FIELDS));")
    drain_events()
    calls = js.json("window.CALLS")
    assert len(calls) == 1
    assert calls[0][0] == surface.METHOD
    sent = dict(calls[0][1])
    assert sent.pop("reset") is True
    assert sent == fields
    assert js.json(API + "isLoaded()") is True


def test_press_resubmits_the_loaded_request_with_no_reset(js: JsRuntime):
    js.bind_json("RESPONSE", built("plain"))
    js.run(FAKE_BRIDGE)
    fields = {
        "symbol": "BONK/USD",
        "reason": "Over target",
        "cost_usd": 1.0,
        "price": 2.0,
        "amount_asset": 3.0,
        "holdings_before": 4.0,
        "target_balance": 5.0,
    }
    js.bind_json("FIELDS", fields)
    js.run(API + "load(null, JSON.parse(FIELDS));")
    drain_events()
    js.run(API + "press('yes');")
    drain_events()
    calls = js.json("window.CALLS")
    assert len(calls) == 2
    sent = dict(calls[1][1])
    assert "reset" not in sent
    assert sent.pop("button") == "yes"
    assert sent == fields
    assert js.json(API + "presses()") == ["yes"]


def test_a_press_with_no_open_request_costs_no_bridge_call(js: JsRuntime):
    js.bind_json("RESPONSE", built("plain"))
    js.run(FAKE_BRIDGE)
    js.run(API + "press('yes');")
    drain_events()
    assert js.json("window.CALLS") == []
    assert js.json(API + "presses()") == ["yes"]


def test_a_refused_load_is_reported_and_leaves_no_request_remembered(js: JsRuntime):
    js.run(
        "window.acervator = { call: function () {"
        "  return Promise.reject(new Error('refused')); } };"
    )
    js.run(API + "load(null, { symbol: 'A/B' });")
    drain_events()
    assert js.json(API + "loadError()") == "refused"
    assert js.json(API + "isLoaded()") is False


def test_forget_clears_the_remembered_request_and_the_presses(js: JsRuntime):
    js.bind_json("RESPONSE", built("plain"))
    js.run(FAKE_BRIDGE)
    js.run(API + "load(null, { symbol: 'A/B' }); " + API + "press('no');")
    drain_events()
    js.run(API + "forget();")
    assert js.json(API + "isLoaded()") is False
    assert js.json(API + "presses()") == []


# -- 12. types survive the trip, and nothing not-plain reaches the module --

JS_TYPE_OF = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "dict": "object",
    "list": "object",
    "NoneType": "null",
}


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
def test_every_value_of_every_state_arrives_as_the_type_it_left_as(js: JsRuntime, state: str):
    payload = built(state)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json(API + "kinds()")
    differing = {
        path: (kind, actual.get(path))
        for path, kind in expected.items()
        if actual.get(path) != kind
    }
    assert not differing, f"{state}: {len(differing)} values changed type: {sorted(differing)}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reads_no_value_that_is_not_plain_data(js: JsRuntime, state: str):
    js.push(built(state))
    assert js.json(API + "notPlainData()") == []


# -- 13. the browser: rendered checks --------------------------------------


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

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
                if self.js("typeof window." + SETTER) == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the buy confirmation module: readyState "
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
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


HOST_SETUP = (
    "window.HOST = document.createElement('div');"
    "window.HOST.setAttribute('data-part', 'buy-confirmation-page');"
    "document.body.appendChild(window.HOST);"
)


def draw(browser: Browser, payload: dict) -> None:
    browser.js(HOST_SETUP)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(API + "renderScreen(window.HOST, JSON.parse(window.PAYLOAD));")


def test_the_screen_fills_the_named_space_the_host_page_left_for_it(browser: Browser):
    browser.js(HOST_SETUP)
    browser.js(
        "window.acervator = { call: function (m, p) { return Promise.resolve("
        "JSON.parse(window.RESPONSE)); } };"
    )
    browser.js("window.RESPONSE = " + json.dumps(json.dumps(built("plain"))) + ";")
    browser.js(API + "fill(window.HOST, { symbol: 'BONK/USD' });")
    for _ in range(READY_ROUNDS):
        if browser.js("window.HOST.querySelectorAll('button').length") > 0:
            break
        browser.settle(READY_STEP_MS)
    parts = browser.parsed(
        "Array.prototype.map.call(window.HOST.querySelectorAll('[data-part]'),"
        " function (e) { return e.getAttribute('data-part'); })"
    )
    assert "buy-confirmation" in parts
    assert parts.count("confirm-button") == 3


def test_nothing_is_rendered_before_the_payload_arrives(browser: Browser):
    """No button exists to press before `setScreen` has ever run."""
    browser.js(HOST_SETUP)
    browser.js(API + "renderScreen(window.HOST, null);")
    assert browser.js("window.HOST.querySelectorAll('button').length") == 0
    assert browser.js("window.HOST.children.length") == 0


def test_a_partial_state_still_reflects_the_surfaces_own_enabled_flags(browser: Browser):
    """The rendered `disabled` attribute must track the payload, not a guess."""
    payload = built("empty")
    payload["buttons"]["yes"]["enabled"] = False
    draw(browser, payload)
    disabled = browser.parsed(
        "Array.prototype.map.call(window.HOST.querySelectorAll('button'),"
        " function (b) { return b.disabled; })"
    )
    assert disabled == [True, False, False]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_button_reflects_the_payloads_own_enabled_flag(browser: Browser, state: str):
    payload = built(state)
    draw(browser, payload)
    order = payload["button_row"]["order"]
    disabled = browser.parsed(
        "Array.prototype.map.call(window.HOST.querySelectorAll('button'),"
        " function (b) { return b.disabled; })"
    )
    assert disabled == [payload["buttons"][name]["enabled"] is False for name in order]


def test_a_hostile_symbol_and_reason_render_as_characters_not_elements(browser: Browser):
    payload = built("markup")
    draw(browser, payload)
    assert browser.js("window.HOST.querySelectorAll('script').length") == 0
    assert browser.js("window.HOST.querySelectorAll('img').length") == 0
    labels = browser.parsed(
        "Array.prototype.map.call(window.HOST.querySelectorAll('b'),"
        " function (e) { return e.textContent; })"
    )
    assert sorted(labels) == sorted(payload["detail_row_labels"].values())
    reason_text = browser.js(
        "window.HOST.querySelector('[data-part=\"reason-banner\"]').textContent"
    )
    assert reason_text == payload["reason_text"]
    symbol_value = browser.js(
        "window.HOST.querySelector('[data-key=\"symbol\"] [data-part=\"detail-value\"]')"
        ".textContent"
    )
    assert symbol_value == payload["detail_row_values"]["symbol"]
    assert "<" in symbol_value


def test_every_rendered_detail_value_equals_the_payloads_own_row(browser: Browser):
    """A value read off the DOM must be the exact figure the surface published."""
    payload = built("plain")
    draw(browser, payload)
    for row in payload["detail_row_order"]:
        rendered = browser.js(
            "window.HOST.querySelector('[data-key=\""
            + row
            + "\"] [data-part=\"detail-value\"]').textContent"
        )
        assert rendered == payload["detail_row_values"][row], row


def test_no_rendered_length_is_a_bare_whole_number(browser: Browser):
    """A token published bare would paint `0px` through `var()`; every length
    drawn here must carry a real CSS unit instead."""
    payload = built("plain")
    draw(browser, payload)
    lengths = browser.parsed(
        "(function () {"
        "  var found = [];"
        "  window.HOST.querySelectorAll('[data-part]').forEach(function (e) {"
        "    var style = getComputedStyle(e);"
        "    ['paddingTop', 'paddingLeft', 'gap', 'minWidth'].forEach(function (n) {"
        "      var v = e.style[n];"
        "      if (v) { found.push(v); }"
        "    });"
        "  });"
        "  return found; })()"
    )
    for one in lengths:
        assert one != "0", lengths
        assert not one.isdigit(), lengths


def test_clicking_yes_re_asks_the_bridge_and_redraws_the_accepted_state(browser: Browser):
    browser.js(HOST_SETUP)
    first = built("plain")
    second = built("plain", button="yes")
    assert first["accepted"] is False
    assert second["accepted"] is True
    browser.js(
        "window.RESPONSES = [" + json.dumps(json.dumps(first)) + ", "
        + json.dumps(json.dumps(second)) + "];"
        "window.CALLS = [];"
        "window.acervator = { call: function (m, p) {"
        "  window.CALLS.push(p);"
        "  return Promise.resolve(JSON.parse(window.RESPONSES[window.CALLS.length - 1])); } };"
    )
    browser.js(API + "load(window.HOST, { symbol: 'BONK/USD' });")
    for _ in range(READY_ROUNDS):
        if browser.js("window.HOST.querySelectorAll('button').length") > 0:
            break
        browser.settle(READY_STEP_MS)
    assert browser.js("window.HOST.firstElementChild.getAttribute('data-accepted')") == "false"
    browser.js(
        "window.HOST.querySelector('[data-answer=\"yes\"]').dispatchEvent("
        "new MouseEvent('click', { bubbles: true }));"
    )
    for _ in range(READY_ROUNDS):
        if browser.js("window.HOST.firstElementChild.getAttribute('data-accepted')") == "true":
            break
        browser.settle(READY_STEP_MS)
    assert browser.js("window.HOST.firstElementChild.getAttribute('data-accepted')") == "true"
    assert browser.js("window.HOST.firstElementChild.getAttribute('data-result-value')") == "yes"
    assert browser.js("window.CALLS.length") == 2
    second_params = browser.parsed("window.CALLS[1]")
    assert second_params["button"] == "yes"
    assert "reset" not in second_params
    assert second_params["symbol"] == "BONK/USD"
