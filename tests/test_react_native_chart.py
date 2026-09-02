"""Drives `native_chart.js` against `native_chart_surface.py`."""

from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import native_chart_surface as ncs
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "native_chart.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: The closing line a whole module file ends with.
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
MODULE_LITERALS = js_literals(MODULE_SOURCE)

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500
READY_ROUNDS = 100
READY_STEP_MS = 100
#: LOAD_ATTEMPTS reloads the page once, since a worker can swap the module.
LOAD_ATTEMPTS = 3

PIXEL_SIZE = (900, 600)
HOST_WIDTH_PX = 900
HOST_HEIGHT_PX = 600
VIEW_SIZE_PX = (1000, 720)

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

BAR_COUNT = 30
FIRST_TIME_S = 1_700_000_000
BAR_STEP_S = 3600


def series(count: int = BAR_COUNT) -> list:
    """A rising series of `count` bars, each an hour after the last."""
    made = []
    for index in range(count):
        base = 10.0 + index
        made.append(
            ncs.Candle(
                FIRST_TIME_S + index * BAR_STEP_S,
                base,
                base + 1.0,
                base - 1.0,
                base + 0.5,
                5.0 + index,
            )
        )
    return made


def flat_series(price: float = 10.0, count: int = 4) -> list:
    """A series whose high equals its low on every bar."""
    return [
        ncs.Candle(FIRST_TIME_S + index * BAR_STEP_S, price, price, price, price, 1.0)
        for index in range(count)
    ]


def drive(name: str) -> ncs.ChartModel:
    """The surface's model, driven into one named state."""
    model = ncs.ChartModel("BTC-USD")
    if name == "empty":
        return model
    if name == "error":
        model.set_error("no feed")
        return model
    model.set_candles(series())
    model.set_source_label("coinbase")
    if name == "one bar":
        model.set_candles(series(1))
    if name == "flat":
        model.set_candles(flat_series())
    if name == "no volume":
        model.toggle_indicator("volume", False)
    if name == "marked":
        model.set_positions(
            [
                ncs.PositionMarker(12.0, "buy", "internal", 1, filled=False),
                ncs.PositionMarker(30.0, "sell", "orderbook", 2, filled=True),
            ]
        )
        model.set_tranche_floors([(15.0, "T1"), (25.0, "T2")])
        model.set_target_balance_lines(18.0, 34.0)
        model.set_markers(
            [{"ts": FIRST_TIME_S, "price": 12.0, "side": "buy", "role": "SCRUM"}]
        )
    return model


STATE_NAMES = ("empty", "error", "normal", "one bar", "flat", "no volume", "marked")


def state_payload(name: str) -> dict:
    """One state's payload, as the bridge would hand it to the page."""
    built = ncs.build_view_model(drive(name), *PIXEL_SIZE)
    return json.loads(json.dumps(built))


def bridge_payload() -> dict:
    return state_payload("normal")


def unsized_payload() -> dict:
    """A payload for a chart that has candles but no pixels yet."""
    return json.loads(json.dumps(ncs.build_view_model(drive("normal"))))


def token_payload() -> dict:
    return json.loads(json.dumps(dss.build_view_model()))


def strings_in(value: Any) -> set:
    """Every string value at every depth of `value`, empties left out."""
    found: set = set()
    if isinstance(value, str):
        if value:
            found.add(value)
    elif isinstance(value, dict):
        for inner in value.values():
            found |= strings_in(inner)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            found |= strings_in(inner)
    return found


def keys_in(value: Any) -> set:
    """Every dict key at every depth of `value`."""
    found: set = set()
    if isinstance(value, dict):
        for name, inner in value.items():
            found.add(name)
            found |= keys_in(inner)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            found |= keys_in(inner)
    return found


ALL_STATES = {name: state_payload(name) for name in STATE_NAMES}

#: PUBLISHED_VALUES holds every string the surface publishes in any state.
PUBLISHED_VALUES: set = set()
for _one in ALL_STATES.values():
    PUBLISHED_VALUES |= strings_in(_one)

PUBLISHED_KEYS: set = set()
for _one in ALL_STATES.values():
    PUBLISHED_KEYS |= keys_in(_one)

#: The method the module asks on is a name, not a value it paints.
NAMED_VALUE = ncs.METHOD

#: Values the chart actually shows, which the module must never spell out.
PAINTED_VALUES = PUBLISHED_VALUES - PUBLISHED_KEYS - {NAMED_VALUE}

TOKEN_VALUES = {str(one) for one in token_payload()["tokens"].values() if one != ""}

#: Keys the drawing reads, so the naming check is not vacuous.
LOAD_BEARING_KEYS = {
    "bodies",
    "body_x_px",
    "body_y_px",
    "candles",
    "colors_css",
    "grid",
    "metrics",
    "panes",
    "price_lines",
    "skin_css",
    "ticks",
    "time_axis",
    "wick_x_px",
    "y_px",
}


class JsRuntime(JsEngine):
    """The chart module, running in QJSEngine."""

    module_path = MODULE_PATH
    setter = "acervatorSetChart"

    def named(self, call: str, *args) -> Any:
        written = ", ".join(json.dumps(one) for one in args)
        return self.json("acervatorChart." + call + "(" + written + ")")

    def bind_text(self, name: str, value: str) -> None:
        self._engine.globalObject().setProperty(name, value)

    def run_source(self, source: str, name: str) -> None:
        """Run a second module body in the same engine."""
        result = self._engine.evaluate(source, name)
        assert not result.isError(), name + ": " + result.toString()

    def push_written(self, payload: Any, script: str) -> Any:
        """Push `payload` after `script` has changed the parsed copy."""
        self.bind_json("PAYLOAD", payload)
        return self.json(
            "(function () { var P = JSON.parse(PAYLOAD); "
            + script
            + " return acervatorSetChart(P); })()"
        )


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def skinned(qapp) -> JsRuntime:
    """The chart module beside the token and widget modules it asks."""
    assert qapp is not None
    runtime = JsRuntime(new_engine(), MODULE_SOURCE)
    for name in ("design_tokens.js", "shared_widgets.js"):
        runtime.run_source((WEB / name).read_text(encoding="utf-8"), name)
    runtime.bind_json("TOKENS", token_payload())
    runtime.json("acervatorSetTokens(JSON.parse(TOKENS))")
    return runtime


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    payload = ALL_STATES[state]
    report = js.push(payload)
    assert report["held"]["fields"] == report["declared"]["fields"]
    assert set(js.json("acervatorChart.declaredNames()")) == set(payload)


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = bridge_payload()
    del payload["price_lines"]
    report = js.push(payload)
    assert report["held"]["fields"] == report["declared"]["fields"] - 1
    assert {
        "where": None,
        "field": "price_lines",
        "fault": "missing",
        "detail": None,
    } in report["faults"]


def test_the_whole_payload_check_names_a_field_only_the_module_declares(js: JsRuntime):
    declared = set(js.json("acervatorChart.declaredNames()"))
    assert "a_field_no_surface_publishes" not in declared
    assert declared - set(bridge_payload()) == set()


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_counts_the_bars_the_surface_counted(js: JsRuntime, state: str):
    payload = ALL_STATES[state]
    report = js.push(payload)
    if payload["candles"] is None:
        assert report["held"]["bars"] == 0
        return
    assert report["held"]["bars"] == report["declared"]["bars"]


def test_the_bar_count_check_reports_a_payload_promising_more_bars(js: JsRuntime):
    payload = bridge_payload()
    payload["candles"]["bodies"] = payload["candles"]["bodies"][:-1]
    report = js.push(payload)
    assert report["held"]["bars"] == report["declared"]["bars"] - 1


def test_the_tick_and_line_counts_reach_the_module(js: JsRuntime):
    payload = state_payload("marked")
    report = js.push(payload)
    assert report["held"]["ticks"] == len(payload["price_axis"]["grid"]["ticks"])
    assert report["held"]["lines"] == len(payload["price_lines"])
    assert report["held"]["lines"] > 1, "the marked state draws more than one line"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_a_published_payload_raises_no_fault(js: JsRuntime, state: str):
    report = js.push(ALL_STATES[state])
    assert report["faults"] == [], f"{state}: {report['faults']}"


def test_the_fault_check_reports_a_payload_that_is_not_an_object(js: JsRuntime):
    report = js.json("acervatorSetChart(null)")
    assert report["faults"] == [
        {"where": None, "field": None, "fault": "not-an-object", "detail": "null"}
    ]
    assert js.json("acervatorChart.isLoaded()") is False


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "native_chart.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"native_chart.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_chart_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"native_chart.js spells out chart values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"native_chart.js spells out token values: {written}"


def test_the_painted_set_still_holds_every_caption_the_chart_shows():
    """The painted set is not empty, so the check above measures something."""
    payload = bridge_payload()
    for shown in (
        payload["symbol"],
        payload["header_text"],
        payload["price_axis"]["last_price_label"],
        payload["candles"]["volume_axis_label"],
        payload["ohlc_row_css"][0][1],
    ):
        assert shown in PAINTED_VALUES, shown


def test_the_module_writes_the_bridge_method_it_asks_on():
    assert NAMED_VALUE in set(MODULE_LITERALS["strings"])


def test_the_module_names_the_keys_the_drawing_reads():
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_KEYS
    assert not LOAD_BEARING_KEYS - written, sorted(LOAD_BEARING_KEYS - written)


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "native_chart.js holds a slash outside a comment, which the literal "
        f"scan cannot read: {MODULE_LITERALS['slashes']}"
    )


SAMPLE = bridge_payload()

SPELLED_OUT_LINES = {
    "colour": 'var spelled = "#00ffcc";',
    "token_value": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "css_colour": 'var spelled = "' + SAMPLE["skin_css"]["up_fill"] + '";',
    "symbol": 'var spelled = "' + SAMPLE["symbol"] + '";',
    "price_label": 'var spelled = "' + SAMPLE["price_axis"]["last_price_label"] + '";',
    "background": 'var spelled = "' + SAMPLE["background_css"] + '";',
    "margin": "var spelled = " + str(ncs.LEFT_MARGIN_PX) + ";",
    "grip": "var spelled = " + str(ncs.RESIZE_GRIP_PX) + ";",
    "number": "var spelled = 12;",
    "regex": "var spelled = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the five checks report on `source`."""
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
        assert not (MODULE_SOURCE + line).rstrip().endswith(MODULE_TAIL), kind


def test_the_changed_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, line in sorted(SPELLED_OUT_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetChart") == "function", kind


def python_kinds(payload: dict) -> dict:
    """The JavaScript type of every value of `payload`, by dotted path."""
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
    payload = ALL_STATES[state]
    js.push(payload)
    wanted = python_kinds(payload)
    found = js.json("acervatorChart.kinds()")
    differing = {
        path: (kind, found.get(path))
        for path, kind in wanted.items()
        if found.get(path) != kind
    }
    assert not differing, f"{state}: {len(differing)} values changed type: {differing}"


def test_the_type_check_names_a_value_that_changed_shape(js: JsRuntime):
    payload = bridge_payload()
    js.push_written(payload, "P.candle_count = String(P.candle_count);")
    found = js.json("acervatorChart.kinds()")
    assert found["candle_count"] == "string"
    assert python_kinds(payload)["candle_count"] == "number"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_pane_bound_agrees_with_the_surface(js: JsRuntime, state: str):
    payload = ALL_STATES[state]
    js.push(payload)
    wanted = payload["panes"] or {}
    assert js.json("acervatorChart.panes()") == wanted


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_candle_body_agrees_with_the_surface(js: JsRuntime, state: str):
    payload = ALL_STATES[state]
    js.push(payload)
    wanted = (payload["candles"] or {}).get("bodies", [])
    assert js.json("acervatorChart.bodies()") == wanted


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_price_line_agrees_with_the_surface(js: JsRuntime, state: str):
    payload = ALL_STATES[state]
    js.push(payload)
    assert js.json("acervatorChart.priceLines()") == (payload["price_lines"] or [])


def test_the_agreement_check_names_a_body_read_from_the_wrong_place(js: JsRuntime):
    payload = bridge_payload()
    js.push_written(payload, "P.candles.bodies[0].body_y_px = P.panes.price_top_px;")
    found = js.json("acervatorChart.bodies()")
    assert found[0]["body_y_px"] != payload["candles"]["bodies"][0]["body_y_px"]


def test_a_reader_returns_nothing_for_an_inherited_javascript_name(js: JsRuntime):
    js.push(bridge_payload())
    assert js.named("field", "toString") is None
    assert js.named("field", "constructor") is None


def test_the_inherited_name_check_still_reads_a_real_field(js: JsRuntime):
    js.push(bridge_payload())
    assert js.named("field", "symbol") == bridge_payload()["symbol"]


def test_the_module_reads_the_bars_in_the_order_the_surface_published(js: JsRuntime):
    payload = bridge_payload()
    js.push(payload)
    wanted = [one["index"] for one in payload["candles"]["bodies"]]
    assert js.json("acervatorChart.barOrder()") == wanted
    assert wanted == sorted(wanted), "the surface published its bars out of order"


def test_a_reordered_series_is_named_by_the_bar_check(js: JsRuntime):
    payload = bridge_payload()
    report = js.push_written(
        payload,
        "var b = P.candles.bodies; var one = b[0]; b[0] = b[1]; b[1] = one;",
    )
    named = [one for one in report["faults"] if one["fault"] == "out-of-order"]
    assert len(named) == 2, report["faults"]
    assert {one["where"] for one in named} == {"body:0", "body:1"}
    assert {one["detail"] for one in named} == {0, 1}


def test_two_swapped_bar_values_are_named_by_the_identity_check(js: JsRuntime):
    payload = bridge_payload()
    js.push(payload)
    wanted = js.json("acervatorChart.barIdentity()")
    js.push_written(
        payload,
        "var b = P.candles.bodies;"
        "var keep = b[3].close; b[3].close = b[7].close; b[7].close = keep;",
    )
    found = js.json("acervatorChart.barIdentity()")
    moved = [at for at, row in enumerate(found) if row != wanted[at]]
    assert moved == [3, 7], f"the identity check named {moved}"


def test_the_identity_check_is_quiet_on_a_series_nothing_moved(js: JsRuntime):
    payload = bridge_payload()
    js.push(payload)
    first = js.json("acervatorChart.barIdentity()")
    js.push(payload)
    assert js.json("acervatorChart.barIdentity()") == first


def test_the_surface_publishes_its_bars_as_a_list_and_not_as_a_bag(js: JsRuntime):
    """Issue #276: a bag keyed by a number is re-sorted crossing the bridge,
    so the bars travel as a list."""
    payload = bridge_payload()
    assert isinstance(payload["candles"]["bodies"], list)
    js.push(payload)
    assert js.json("acervatorChart.barOrder()") == [
        one["index"] for one in payload["candles"]["bodies"]
    ]


def test_a_bag_keyed_by_a_number_loses_the_order_it_was_written_in(js: JsRuntime):
    """The same bars in a bag come back sorted, whatever order they left in."""
    bodies = bridge_payload()["candles"]["bodies"]
    written = list(reversed(range(len(bodies))))
    js.bind_json("BAG", {str(at): at for at in written})
    read_back = js.json("Object.keys(JSON.parse(BAG)).map(Number)")
    assert read_back != written
    assert read_back == sorted(written)


def test_the_bar_order_check_is_quiet_on_a_published_series(js: JsRuntime):
    report = js.push(bridge_payload())
    assert [one for one in report["faults"] if one["fault"] == "out-of-order"] == []


def test_every_colour_the_surface_publishes_is_one_css_reads_the_same(js: JsRuntime):
    js.push(bridge_payload())
    for name, value in bridge_payload()["skin_css"].items():
        assert js.named("qtColour", value) is None, f"{name} is {value}"


def test_the_colour_check_names_an_alpha_counted_in_bytes(js: JsRuntime):
    js.push(bridge_payload())
    assert js.named("qtColour", "rgba(38, 166, 154, 220)") == "rgba("


def test_the_colour_check_names_an_eight_digit_hex(js: JsRuntime):
    js.push(bridge_payload())
    assert js.named("qtColour", "#dc26a69a") == "AARRGGBB"


def test_a_swapped_skin_colour_raises_a_fault_naming_it(js: JsRuntime):
    payload = bridge_payload()
    report = js.push_written(payload, 'P.skin_css.up_fill = "rgba(38, 166, 154, 220)";')
    assert {
        "where": "skin_css",
        "field": "up_fill",
        "fault": "qt-colour",
        "detail": "rgba(",
    } in report["faults"]


def test_a_swapped_price_line_colour_raises_a_fault_naming_it(js: JsRuntime):
    payload = bridge_payload()
    report = js.push_written(payload, 'P.price_lines[0].color_css = "#dc26a69a";')
    assert {
        "where": "line:0",
        "field": "color_css",
        "fault": "qt-colour",
        "detail": "AARRGGBB",
    } in report["faults"]


def test_the_python_side_writes_the_alpha_as_a_fraction():
    """Qt counts an alpha byte; CSS counts a fraction of one."""
    assert ncs.css_color((38, 166, 154, 220)) == "rgba(38, 166, 154, 0.8627)"
    assert ncs.css_color((38, 166, 154, 255)) == "rgba(38, 166, 154, 1.0)"
    assert ncs.css_color((0, 0, 0, 0)) == "rgba(0, 0, 0, 0.0)"


#: Every field the surface fills in every state, so a null is a fault.
ALWAYS_FILLED = [
    name
    for name in sorted(bridge_payload())
    if all(ALL_STATES[state].get(name) is not None for state in STATE_NAMES)
]


@pytest.mark.parametrize("field", sorted(bridge_payload()))
def test_a_field_the_payload_omits_is_named_as_missing(js: JsRuntime, field: str):
    payload = bridge_payload()
    del payload[field]
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"]
    assert report["held"]["fields"] == report["declared"]["fields"] - 1


@pytest.mark.parametrize("field", ALWAYS_FILLED)
def test_a_field_carrying_null_is_named(js: JsRuntime, field: str):
    payload = bridge_payload()
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_a_state_field_carrying_null_is_the_surface_naming_its_state(js: JsRuntime):
    """The eight state fields are null in every state but their own."""
    report = js.push(state_payload("empty"))
    assert [one for one in report["faults"] if one["fault"] == "null"] == []
    assert set(js.json("acervatorChart.stateNames()")) <= set(bridge_payload())


BAG_NAMES = ["actions", "fire_armed_state", "flags", "metrics", "skin", "skin_css"]
LIST_NAMES = ["header_parts", "markers", "positions", "sub_panes", "timeframes"]

#: Each SCALARS row is a value and the JavaScript type name it reports as.
SCALARS = {
    "a number": (7, "number"),
    "text": ("gone", "string"),
    "a true flag": (True, "boolean"),
    "nothing at all": (None, "null"),
}


@pytest.mark.parametrize("field", BAG_NAMES)
@pytest.mark.parametrize("case", sorted(SCALARS))
def test_a_bag_replaced_by_a_scalar_is_named(js: JsRuntime, field: str, case: str):
    value, kind = SCALARS[case]
    payload = bridge_payload()
    payload[field] = value
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "not-an-object",
        "detail": kind,
    } in report["faults"]


@pytest.mark.parametrize("field", LIST_NAMES)
@pytest.mark.parametrize("case", sorted(SCALARS))
def test_a_list_replaced_by_a_scalar_is_named(js: JsRuntime, field: str, case: str):
    value, kind = SCALARS[case]
    payload = bridge_payload()
    payload[field] = value
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "not-a-list",
        "detail": kind,
    } in report["faults"]


def test_the_shape_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(bridge_payload())
    kinds = {one["fault"] for one in report["faults"]}
    assert "not-an-object" not in kinds
    assert "not-a-list" not in kinds


def test_a_value_the_surface_publishes_twice_is_named_when_the_copies_differ(
    js: JsRuntime,
):
    payload = bridge_payload()
    report = js.push_written(payload, "P.resize_grip_px = P.resize_grip_px + 1;")
    assert {
        "where": "metrics",
        "field": "resize_grip_px",
        "fault": "disagrees",
        "detail": payload["resize_grip_px"] + 1,
    } in report["faults"]


def test_a_value_the_surface_publishes_twice_is_named_when_one_copy_is_text(
    js: JsRuntime,
):
    payload = bridge_payload()
    report = js.push_written(payload, "P.resize_grip_px = String(P.resize_grip_px);")
    assert {
        "where": "metrics",
        "field": "resize_grip_px",
        "fault": "wrong-type",
        "detail": "string",
    } in report["faults"]


def test_the_held_twice_check_is_quiet_when_both_copies_agree(js: JsRuntime):
    report = js.push(bridge_payload())
    assert [one for one in report["faults"] if one["fault"] == "disagrees"] == []


def test_the_surface_gives_one_name_to_two_different_heights():
    """Reported, not repaired: `minimum_height_px` names the floor and the
    current height."""
    quiet = state_payload("normal")
    assert quiet["minimum_height_px"] == quiet["metrics"]["minimum_height_px"]
    moved = state_payload("no volume")
    assert moved["minimum_height_px"] != moved["metrics"]["minimum_height_px"]
    assert moved["minimum_height_px"] == moved["natural_height_px"]


def test_a_radius_borrows_a_radius_token_and_an_inset_does_not(skinned: JsRuntime):
    """The one-carrier rule alone would hand a card radius to an inset."""
    skinned.push(bridge_payload())
    assert skinned.named("variableFor", dss.RADIUS_CARD) == "RADIUS_CARD"
    assert skinned.named("length", "badge_radius_px", dss.RADIUS_CARD) == (
        "calc(var(--RADIUS_CARD, 6) * 1px)"
    )
    assert skinned.named("length", "sub_label_inset_px", dss.RADIUS_CARD) == "6px"


def test_no_length_the_chart_publishes_borrows_a_token_that_means_another_thing(
    skinned: JsRuntime,
):
    payload = bridge_payload()
    skinned.push(payload)
    borrowed = {}
    for name, value in payload["metrics"].items():
        if not name.endswith("_px") or not isinstance(value, (int, float)):
            continue
        found = skinned.named("length", name, value)
        if str(found).startswith("calc("):
            borrowed[name] = found
    assert not borrowed, f"a chart length borrowed a token: {borrowed}"


def test_the_token_rule_reads_nothing_without_the_widget_module(js: JsRuntime):
    js.push(bridge_payload())
    assert js.named("variableFor", dss.RADIUS_CARD) is None
    assert js.named("length", "badge_radius_px", dss.RADIUS_CARD) == "6px"


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._view.resize(*VIEW_SIZE_PX)
        for attempt in range(LOAD_ATTEMPTS):
            self.load_page()
            if self.module_ready():
                return
            assert attempt + 1 < LOAD_ATTEMPTS, (
                "the page never defined the chart module: readyState "
                + str(self.js("document.readyState"))
                + ", scripts "
                + str(self.js("document.scripts.length"))
            )

    def load_page(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl

        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        self._view.loadFinished.disconnect(_loaded)
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"

    def module_ready(self) -> bool:
        """Whether the page defines `acervatorSetChart`, which
        `loadFinished` does not promise."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetChart") == "function":
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
    "backgroundImage",
    "position",
    "left",
    "top",
    "width",
    "height",
    "whiteSpace",
    "overflow",
    "pointerEvents",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderLeftStyle",
    "borderLeftWidth",
    "borderLeftColor",
    "borderTopLeftRadius",
    "paddingLeft",
]

PAGE_HELPERS = (
    "window.HOST = document.getElementById('chart-host');"
    "if (!window.HOST) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'chart-host';"
    "  document.body.appendChild(window.HOST); }"
    "window.HOST.style.width = " + json.dumps(str(HOST_WIDTH_PX) + "px") + ";"
    "window.HOST.style.height = " + json.dumps(str(HOST_HEIGHT_PX) + "px") + ";"
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
    "        text: own,"
    "        width: el.getBoundingClientRect().width,"
    "        height: el.getBoundingClientRect().height,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)


def give_tokens(browser: Browser) -> int:
    """Push the design tokens into the page, since a disk-loaded view has
    no bridge."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_chart(browser: Browser, payload: dict) -> list:
    """Render `payload` into `window.HOST` and return what READ_PARTS finds."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetChart(JSON.parse(window.PAYLOAD));"
        "acervatorChart.renderChart(window.HOST);"
    )
    return read_parts(browser)


def read_parts(browser: Browser) -> list:
    return json.loads(browser.js(READ_PARTS))


def draw_into_fresh_host(browser: Browser, written: str) -> str:
    """Draw a payload whose first body sits at `written` and return its row."""
    return browser.js(
        "(function () { var P = JSON.parse(window.PAYLOAD);"
        "  P.candles.bodies[0].body_y_px = " + written + ";"
        "  var host = document.createElement('div');"
        "  document.body.appendChild(host);"
        "  acervatorSetChart(P);"
        "  acervatorChart.renderChart(host);"
        "  var body = host.querySelector('[data-part=\"body\"]');"
        "  var row = getComputedStyle(body).top;"
        "  host.remove();"
        "  return row; })()"
    )


def probe(browser: Browser, tag: str, body: str, names: list) -> dict:
    """The computed values a bare `tag` takes from `body`."""
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(tag)
        + ", "
        + json.dumps(body)
        + ", "
        + json.dumps(sorted(set(names)))
        + ")"
    )


def by_part(parts: list, name: str) -> list:
    return [one for one in parts if one["attrs"].get("data-part") == name]


def one_part(parts: list, name: str) -> dict:
    found = by_part(parts, name)
    assert len(found) == 1, f"{len(found)} parts named {name}"
    return found[0]


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorChart") == "object"
    assert browser.js("typeof window.acervatorSetChart") == "function"
    assert browser.js("typeof window.acervatorLoadChart") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_chart(browser, bridge_payload())
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_network_check_names_a_refused_connection(browser: Browser):
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


def test_the_drawn_chart_shows_one_body_and_one_wick_for_every_bar(browser: Browser):
    payload = bridge_payload()
    parts = draw_chart(browser, payload)
    wanted = len(payload["candles"]["bodies"])
    assert len(by_part(parts, "candle")) == wanted
    assert len(by_part(parts, "body")) == wanted
    assert len(by_part(parts, "wick")) == wanted


def test_the_body_count_check_reads_a_shorter_series_as_shorter(browser: Browser):
    payload = bridge_payload()
    payload["candles"]["bodies"] = payload["candles"]["bodies"][:5]
    parts = draw_chart(browser, payload)
    assert len(by_part(parts, "body")) == 5


def test_the_drawn_chart_shows_one_bar_for_every_volume_the_surface_published(
    browser: Browser,
):
    payload = bridge_payload()
    parts = draw_chart(browser, payload)
    wanted = [
        one for one in payload["candles"]["bodies"] if one["volume_height_px"] > 0
    ]
    assert len(by_part(parts, "volume-bar")) == len(wanted)


def test_the_drawn_chart_draws_no_volume_bar_when_the_strip_is_off(browser: Browser):
    payload = state_payload("no volume")
    assert payload["panes"]["volume_height_px"] == 0
    parts = draw_chart(browser, payload)
    assert not by_part(parts, "volume-bar")
    assert not by_part(parts, "volume-divider")


def test_the_drawn_chart_shows_every_grid_and_time_label_the_surface_published(
    browser: Browser,
):
    payload = bridge_payload()
    parts = draw_chart(browser, payload)
    wanted = [
        one["label"] for one in payload["price_axis"]["grid"]["ticks"] if one["on_pane"]
    ]
    assert [one["text"] for one in by_part(parts, "grid-label")] == wanted
    times = [
        one["label"]
        for one in payload["time_axis"]["ticks"]
        if one["on_pane"] and one["label"]
    ]
    assert [one["text"] for one in by_part(parts, "time-label")] == times


def test_the_label_check_reads_one_changed_label(browser: Browser):
    payload = bridge_payload()
    payload["price_axis"]["grid"]["ticks"][0]["label"] = "MOVED"
    parts = draw_chart(browser, payload)
    assert by_part(parts, "grid-label")[0]["text"] == "MOVED"


def test_the_drawn_chart_shows_the_header_and_the_ohlc_row(browser: Browser):
    payload = bridge_payload()
    parts = draw_chart(browser, payload)
    assert one_part(parts, "symbol")["text"] == payload["symbol"]
    assert one_part(parts, "header-text")["text"] == payload["header_text"]
    assert [one["text"] for one in by_part(parts, "ohlc-value")] == [
        row[1] for row in payload["ohlc_row_css"]
    ]


def test_the_drawn_chart_shows_its_message_and_no_candle_when_it_holds_none(
    browser: Browser,
):
    payload = state_payload("empty")
    parts = draw_chart(browser, payload)
    assert one_part(parts, "empty")["text"] == payload["empty"]["message"]
    assert not by_part(parts, "candle")
    assert not by_part(parts, "price-pane")


def test_the_error_state_shows_the_error_beside_the_header(browser: Browser):
    payload = state_payload("error")
    parts = draw_chart(browser, payload)
    assert one_part(parts, "header-error")["text"] == payload["error_text"]
    assert one_part(parts, "empty")["text"] == payload["error_text"]


def part_counts(parts: list) -> dict:
    found: dict = {}
    for one in parts:
        name = one["attrs"].get("data-part")
        found[name] = found.get(name, 0) + 1
    return found


def test_every_drawn_child_a_check_reads_carries_a_name(browser: Browser):
    payload = state_payload("marked")
    parts = draw_chart(browser, payload)
    counts = part_counts(parts)
    unnamed = [one["path"] for one in parts if one["attrs"].get("data-part") is None]
    assert not unnamed, f"{len(unnamed)} drawn parts carry no name: {unnamed}"
    crowded = [
        one["attrs"]["data-part"]
        for one in parts
        if counts[one["attrs"]["data-part"]] > 1 and "data-index" not in one["attrs"]
    ]
    assert not crowded, f"these repeated parts carry no index: {sorted(set(crowded))}"


def test_the_naming_check_reads_a_part_stripped_of_its_index(browser: Browser):
    payload = state_payload("marked")
    draw_chart(browser, payload)
    browser.js(
        "window.HOST.querySelector('[data-part=\"body\"]').removeAttribute('data-index');"
    )
    parts = read_parts(browser)
    counts = part_counts(parts)
    crowded = [
        one["attrs"]["data-part"]
        for one in parts
        if counts[one["attrs"]["data-part"]] > 1 and "data-index" not in one["attrs"]
    ]
    assert crowded == ["body"], crowded


def drawn_program(payload: dict) -> dict:
    """How many of each part the surface's own numbers ask CSS to draw."""
    bodies = payload["candles"]["bodies"]
    ticks = [one for one in payload["price_axis"]["grid"]["ticks"] if one["on_pane"]]
    times = [one for one in payload["time_axis"]["ticks"] if one["on_pane"]]
    named = [one for one in times if one["label"]]
    bars = [one for one in bodies if one["volume_height_px"] > 0]
    lines = [one for one in payload["price_lines"] if one["on_pane"]]
    rows = payload["ohlc_row_css"]
    strip = bool(payload["panes"]["volume_height_px"])
    return {
        "body": len(bodies),
        "wick": len(bodies),
        "volume-bar": len(bars) if strip else 0,
        "grid-line": len(ticks),
        "time-line": len(times),
        "volume-divider": 1 if strip else 0,
        "price-line": len(lines),
        "grid-label": len(ticks),
        "time-label": len(named),
        "volume-label": 1 if strip else 0,
        "price-badge": len(lines),
        "ohlc-value": len(rows),
        "ohlc-label": len([one for one in rows if one[0]]),
        "symbol": 1,
        "header-text": 1,
        "grip-dash": len(payload["metrics"]["grip_dash_offsets_px"]),
        "overlay-mount": 1,
    }


def test_the_drawn_chart_holds_one_element_for_every_thing_css_can_draw(
    browser: Browser,
):
    payload = bridge_payload()
    counts = part_counts(draw_chart(browser, payload))
    wanted = drawn_program(payload)
    differing = {
        name: (count, counts.get(name, 0))
        for name, count in wanted.items()
        if counts.get(name, 0) != count
    }
    assert not differing, differing


def test_the_program_check_reads_a_series_one_bar_shorter(browser: Browser):
    payload = bridge_payload()
    payload["candles"]["bodies"] = payload["candles"]["bodies"][:-1]
    counts = part_counts(draw_chart(browser, payload))
    assert counts["body"] == len(bridge_payload()["candles"]["bodies"]) - 1


def test_the_chart_leaves_one_mount_for_what_css_cannot_draw(browser: Browser):
    payload = bridge_payload()
    parts = draw_chart(browser, payload)
    mount = one_part(parts, "overlay-mount")
    assert mount["attrs"]["aria-label"] == browser.js("acervatorChart.mountLabel")
    assert mount["style"]["pointerEvents"] == "none"
    assert mount["width"] == payload["panes"]["chart_width_px"]


COLOUR_NAMES = ["backgroundColor", "borderTopColor"]
BOX_NAMES = ["left", "top", "width", "height"]


def test_a_drawn_candle_body_matches_a_probe_styled_from_the_surface(
    browser: Browser,
):
    payload = bridge_payload()
    parts = draw_chart(browser, payload)
    body = payload["candles"]["bodies"][0]
    drawn = by_part(parts, "body")[0]
    expected = probe(
        browser,
        "div",
        "position:absolute;"
        + "left:"
        + str(body["body_x_px"])
        + "px;"
        + "top:"
        + str(body["body_y_px"])
        + "px;"
        + "width:"
        + str(body["body_width_px"])
        + "px;"
        + "height:"
        + str(body["body_height_px"])
        + "px;"
        + "background-color:"
        + body["colors_css"]["fill"]
        + ";"
        + "border:"
        + str(payload["metrics"]["candle_border_width_px"])
        + "px "
        + payload["metrics"]["solid_line_style"]
        + " "
        + body["colors_css"]["border"]
        + ";"
        + "box-sizing:border-box",
        BOX_NAMES + ["backgroundColor", "borderTopColor", "borderTopWidth"],
    )
    differing = {
        name: (value, drawn["style"].get(name))
        for name, value in expected.items()
        if drawn["style"].get(name) != value
    }
    assert not differing, differing


def test_the_probe_check_names_one_changed_declaration(browser: Browser):
    payload = bridge_payload()
    parts = draw_chart(browser, payload)
    body = payload["candles"]["bodies"][0]
    drawn = by_part(parts, "body")[0]
    moved = probe(
        browser,
        "div",
        "position:absolute;background-color:" + body["colors_css"]["border"],
        ["backgroundColor"],
    )
    assert drawn["style"]["backgroundColor"] != moved["backgroundColor"]


def test_a_drawn_grid_line_matches_a_probe_styled_from_the_surface(browser: Browser):
    payload = bridge_payload()
    parts = draw_chart(browser, payload)
    tick = [one for one in payload["price_axis"]["grid"]["ticks"] if one["on_pane"]][0]
    drawn = by_part(parts, "grid-line")[0]
    expected = probe(
        browser,
        "div",
        "border-top:"
        + str(payload["metrics"]["grid_line_width_px"])
        + "px "
        + payload["metrics"]["grid_line_style"]
        + " "
        + tick["color_css"],
        ["borderTopStyle", "borderTopWidth", "borderTopColor"],
    )
    for name, value in expected.items():
        assert drawn["style"][name] == value, name


def test_the_drawn_ground_is_the_gradient_the_surface_published(browser: Browser):
    payload = bridge_payload()
    parts = draw_chart(browser, payload)
    chart = one_part(parts, "chart")
    expected = probe(
        browser, "div", "background:" + payload["background_css"], ["backgroundImage"]
    )
    assert chart["style"]["backgroundImage"] == expected["backgroundImage"]
    assert expected["backgroundImage"] != "none"


def test_a_drawn_candle_sits_where_the_surface_put_it(browser: Browser):
    payload = bridge_payload()
    parts = draw_chart(browser, payload)
    drawn = by_part(parts, "body")
    for at, body in enumerate(payload["candles"]["bodies"]):
        assert drawn[at]["attrs"]["data-index"] == str(at)
        assert (
            drawn[at]["style"]["left"]
            == probe(
                browser,
                "div",
                "position:absolute;left:" + str(body["body_x_px"]) + "px",
                ["left"],
            )["left"]
        )


def test_a_reordered_series_moves_the_drawn_candles(browser: Browser):
    payload = bridge_payload()
    before = draw_chart(browser, payload)
    payload["candles"]["bodies"].reverse()
    after = draw_chart(browser, payload)
    moved = [
        at
        for at, one in enumerate(by_part(before, "body"))
        if one["style"]["top"] != by_part(after, "body")[at]["style"]["top"]
    ]
    assert moved, "reversing the series moved no drawn candle"


def test_two_swapped_bar_values_move_the_drawn_candles(browser: Browser):
    payload = bridge_payload()
    before = draw_chart(browser, payload)
    bodies = payload["candles"]["bodies"]
    bodies[3]["body_y_px"], bodies[7]["body_y_px"] = (
        bodies[7]["body_y_px"],
        bodies[3]["body_y_px"],
    )
    after = draw_chart(browser, payload)
    moved = [
        at
        for at, one in enumerate(by_part(before, "body"))
        if one["style"]["top"] != by_part(after, "body")[at]["style"]["top"]
    ]
    assert moved == [3, 7], moved


def test_no_token_the_page_rewrites_moves_a_drawn_part(browser: Browser):
    """The chart paints its own palette, so no token reaches a pixel of it."""
    payload = bridge_payload()
    before = draw_chart(browser, payload)
    names = browser.parsed("acervatorTokens.declaredNames()")
    browser.js(
        "JSON.parse(" + json.dumps(json.dumps(names)) + ").forEach(function (n) {"
        "  document.documentElement.style.setProperty('--' + n, 'magenta'); });"
    )
    after = read_parts(browser)
    moved = [
        (one["path"], key)
        for at, one in enumerate(before)
        for key, value in one["style"].items()
        if after[at]["style"].get(key) != value
    ]
    assert not moved, f"a token moved {moved}"


def test_the_token_check_would_report_a_part_that_did_borrow_one(browser: Browser):
    """A probe borrowing a token moves under the same rewrite."""
    draw_chart(browser, bridge_payload())
    browser.js("document.documentElement.style.setProperty('--PRIMARY', 'magenta');")
    found = probe(browser, "div", "color:var(--PRIMARY, black)", ["color"])
    assert found["color"] == "rgb(255, 0, 255)"


#: HOSTILE_TEXTS holds values JSON carries into the symbol unchanged.
HOSTILE_TEXTS = {
    "a true flag": True,
    "nothing at all": None,
    "a two hundred character symbol": "X" * 200,
    "markup": "<script>alert(1)</script>",
    "an image tag": '<img src="x" onerror="window.OWNED = true">',
    "an empty symbol": "",
}

#: Numbers written where text belongs.
HOSTILE_AMOUNTS = {
    "a number where text belongs": 1.0,
    "a very large integer": 10**24,
}

HOSTILE_ALL = dict(HOSTILE_TEXTS)
HOSTILE_ALL.update(HOSTILE_AMOUNTS)

#: HOSTILE_NUMBERS holds values JSON cannot spell, written after parsing.
HOSTILE_NUMBERS = {
    "not a number": "NaN",
    "an infinity": "Infinity",
    "a negative infinity": "-Infinity",
}


def js_spelling(browser: Browser, value: Any) -> str:
    """How the page writes one published value out as the text it draws."""
    if value is None:
        return ""
    return browser.js("String(JSON.parse(" + json.dumps(json.dumps(value)) + "))")


@pytest.mark.parametrize("case", sorted(HOSTILE_ALL))
def test_the_chart_holds_whatever_symbol_the_surface_produced(js: JsRuntime, case: str):
    payload = bridge_payload()
    payload["symbol"] = HOSTILE_ALL[case]
    js.push(payload)
    shown = js.named("field", "symbol")
    assert shown == HOSTILE_ALL[case] or float(shown) == float(HOSTILE_ALL[case])


@pytest.mark.parametrize("case", sorted(HOSTILE_ALL))
def test_the_drawn_chart_shows_a_hostile_symbol_as_text_and_not_as_markup(
    browser: Browser, case: str
):
    payload = bridge_payload()
    payload["symbol"] = HOSTILE_ALL[case]
    browser.js("window.OWNED = false;")
    parts = draw_chart(browser, payload)
    drawn = one_part(parts, "symbol")
    assert drawn["text"] == js_spelling(browser, HOSTILE_ALL[case])
    assert (
        browser.js(
            "window.HOST.querySelector('[data-part=\"symbol\"]')"
            ".getElementsByTagName('*').length"
        )
        == 0
    )
    assert browser.js("window.OWNED") is False


@pytest.mark.parametrize("case", sorted(HOSTILE_NUMBERS))
def test_the_chart_holds_a_number_json_cannot_spell(js: JsRuntime, case: str):
    payload = bridge_payload()
    js.push_written(
        payload,
        "P.candles.bodies[0].body_y_px = " + HOSTILE_NUMBERS[case] + ";",
    )
    shown = js.json("acervatorChart.bodies()")[0]["body_y_px"]
    assert shown is None or isinstance(shown, float), f"{case}: {shown!r}"


@pytest.mark.parametrize("case", sorted(HOSTILE_NUMBERS))
def test_a_price_the_browser_cannot_read_drops_the_body_to_the_pane_top(
    browser: Browser, case: str
):
    """The browser refuses the row, so the body falls to where it would
    sit with no row written at all."""
    payload = bridge_payload()
    draw_chart(browser, payload)
    drawn = draw_into_fresh_host(browser, HOSTILE_NUMBERS[case])
    assert drawn == "0px", f"{case} drew the body at {drawn}"


def test_the_row_check_reads_a_price_the_browser_can_read(browser: Browser):
    payload = bridge_payload()
    draw_chart(browser, payload)
    wanted = str(payload["candles"]["bodies"][0]["body_y_px"])
    drawn = draw_into_fresh_host(browser, wanted)
    assert drawn != "0px"
    assert drawn.endswith("px")


def test_a_price_the_browser_cannot_read_holds_the_row_a_redraw_already_wrote(
    browser: Browser,
):
    """Reported, not repaired: the browser refuses the new row and keeps
    the one the last frame wrote."""
    payload = bridge_payload()
    parts = draw_chart(browser, payload)
    resting = by_part(parts, "body")[0]["style"]["top"]
    browser.js(
        "(function () { var P = JSON.parse(window.PAYLOAD);"
        "  P.candles.bodies[0].body_y_px = NaN;"
        "  acervatorSetChart(P); acervatorChart.renderChart(window.HOST); })()"
    )
    drawn = by_part(read_parts(browser), "body")[0]["style"]["top"]
    assert drawn == resting


def test_the_bridge_check_parses_a_whole_payload(js: JsRuntime):
    written = json.dumps(bridge_payload())
    assert "NaN" not in written
    js.bind_text("WHOLE", written)
    result = js.run(
        "(function () { try { JSON.parse(WHOLE); return 'parsed'; }"
        " catch (e) { return e.name; } })()"
    )
    assert result.toString() == "parsed"


@pytest.mark.parametrize("count", [0, 1])
def test_the_surface_and_the_module_agree_on_a_series_of_that_length(
    js: JsRuntime, count: int
):
    model = ncs.ChartModel("BTC-USD")
    if count:
        model.set_candles(series(count))
    payload = json.loads(json.dumps(ncs.build_view_model(model, *PIXEL_SIZE)))
    report = js.push(payload)
    assert report["faults"] == []
    assert report["held"]["bars"] == count


def test_a_flat_series_never_divides_by_a_zero_price_range():
    """Issue reported, not repaired: a flat series pads its own span."""
    payload = ncs.build_view_model(drive("flat"), *PIXEL_SIZE)
    assert payload["price_axis"]["span"] > 0
    assert all(math.isfinite(one["body_y_px"]) for one in payload["candles"]["bodies"])


def test_a_flat_negative_series_gives_the_price_axis_a_negative_span():
    """Reported, not repaired: the pad is negative, so high falls below low."""
    model = ncs.ChartModel("BTC-USD")
    model.set_candles(flat_series(-5.0))
    payload = ncs.build_view_model(model, *PIXEL_SIZE)
    assert payload["price_axis"]["span"] < 0
    assert payload["price_axis"]["high"] < payload["price_axis"]["low"]
    assert payload["price_axis"]["grid"]["ticks"] == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_price_the_axis_cannot_place_raises_inside_the_surface(value: float):
    """Reported, not repaired: the bridge handler raises on such a bar."""
    model = ncs.ChartModel("BTC-USD")
    model.set_candles(
        [
            ncs.Candle(FIRST_TIME_S + at * BAR_STEP_S, value, value, value, value, 1.0)
            for at in range(4)
        ]
    )
    with pytest.raises(ValueError):
        ncs.build_view_model(model, *PIXEL_SIZE)


def test_a_huge_price_still_produces_a_payload_json_can_spell():
    model = ncs.ChartModel("BTC-USD")
    big = float(10**24)
    model.set_candles(
        [
            ncs.Candle(FIRST_TIME_S + at * BAR_STEP_S, big, big, big, big, 1.0)
            for at in range(4)
        ]
    )
    written = json.dumps(ncs.build_view_model(model, *PIXEL_SIZE))
    assert "NaN" not in written
    assert "Infinity" not in written


def test_a_chart_with_no_pixels_yet_publishes_no_pane(js: JsRuntime):
    payload = unsized_payload()
    report = js.push(payload)
    assert report["faults"] == []
    assert payload["panes"] is None
    assert js.json("acervatorChart.panes()") == {}
