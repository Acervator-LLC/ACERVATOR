"""The React TradingView chart page, against the payload Python serves."""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss  # noqa: E402
from src.gui.main_tabs import theme_engine_surface as tes  # noqa: E402
from src.gui.main_tabs import tradingview_chart_surface as tvs  # noqa: E402
from tests.fixtures.web_js_modules import (  # noqa: E402
    HEX_COLOUR,
    JsEngine,
    js_literals,
    load_order,
    new_engine,
    runs_after,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "tradingview_chart.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

MODULE_TAIL = "})(window);"
MODULE_READ_ATTEMPTS = 200
MODULE_READ_PAUSE_S = 0.01


def read_module() -> str:
    """Return MODULE_PATH text ending with MODULE_TAIL, retrying while not."""
    for _ in range(MODULE_READ_ATTEMPTS):
        found = MODULE_PATH.read_text(encoding="utf-8")
        if found.rstrip().endswith(MODULE_TAIL):
            return found
        time.sleep(MODULE_READ_PAUSE_S)
    raise AssertionError(MODULE_PATH.name + " never read back whole")


MODULE_SOURCE = read_module()

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
HOST_WIDTH_PX = 1400
HOST_HEIGHT_PX = 800
VIEW_SIZE_PX = (1400, 900)

OTHER_SYMBOL = "SOL/USD"
UNKNOWN_THEME = "no-such-theme"


def bridge(params: dict) -> dict:
    """Run ``view_model`` and answer as the desktop bridge would."""
    return json.loads(json.dumps(tvs.view_model(params), ensure_ascii=True))


SCENARIOS = {
    "cyberpunk_dark": {"theme": "cyberpunk_dark"},
    "neon_light": {"theme": "neon_light"},
    "classic_terminal": {"theme": "classic_terminal"},
    "minimal_modern": {"theme": "minimal_modern"},
    "glass_metal": {"theme": "glass_metal"},
    "unknown_theme": {"theme": UNKNOWN_THEME},
    "other_symbol": {"symbol": OTHER_SYMBOL, "theme": "glass_metal"},
    "first_active": {"active": "1"},
    "last_active": {"active": "W"},
}

STATE_NAMES = sorted(SCENARIOS)


def scenario(name: str) -> dict:
    return bridge(SCENARIOS[name])


class JsRuntime(JsEngine):
    """The chart module in one engine, answering as JSON."""

    module_path = MODULE_PATH
    setter = "acervatorSetTradingViewChart"

    def api(self, name: str, *args: Any) -> Any:
        """Call one function on ``acervatorTradingViewChart`` with JSON arguments."""
        spelled = ", ".join(json.dumps(one) for one in args)
        return self.json("acervatorTradingViewChart." + name + "(" + spelled + ")")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


#: ANSWERED_BY maps a payload field to the module function that answers it.
ANSWERED_BY = {
    "accessible_name": ("field", ["accessible_name"]),
    "actions": ("actions", []),
    "active_timeframe": ("field", ["active_timeframe"]),
    "bollinger_series": ("bollingerSeries", []),
    "bridge_callback": ("field", ["bridge_callback"]),
    "bridge_object": ("field", ["bridge_object"]),
    "bus_topics": ("busTopics", []),
    "buttons": ("buttons", []),
    "button_skin": ("buttonSkin", []),
    "buy_side": ("field", ["buy_side"]),
    "calls": ("calls", []),
    "call_formats": ("callFormats", []),
    "call_order": ("callOrder", []),
    "candle_fields": ("candleFields", []),
    "candle_series": ("candleSeries", []),
    "colors": ("colours", []),
    "default_symbol": ("field", ["default_symbol"]),
    "default_theme": ("field", ["default_theme"]),
    "fallback_theme": ("field", ["fallback_theme"]),
    "grid_level_fields": ("gridLevelFields", []),
    "grid_line_skin": ("gridLineSkin", []),
    "html": ("field", ["html"]),
    "logger_name": ("field", ["logger_name"]),
    "marker_fields": ("markerFields", []),
    "marker_skin": ("markerSkin", []),
    "missing_webengine_warning": ("field", ["missing_webengine_warning"]),
    "page": ("page", []),
    "script_url": ("field", ["script_url"]),
    "sell_side": ("field", ["sell_side"]),
    "skin": ("skin", []),
    "symbol": ("field", ["symbol"]),
    "symbol_key": ("field", ["symbol_key"]),
    "theme": ("field", ["theme"]),
    "themes": ("themes", []),
    "theme_keys": ("themeKeys", []),
    "theme_order": ("themeOrder", []),
    "timers": ("timers", []),
    "timer_delays_ms": ("timerDelays", []),
    "time_scale": ("timeScale", []),
    "toolbar": ("toolbar", []),
    "volume_field": ("field", ["volume_field"]),
    "volume_series": ("volumeSeries", []),
    "watermark": ("watermark", []),
    "web_view": ("webView", []),
}


def read_back(js: JsRuntime, payload: dict) -> dict:
    """Every declared field, read back out of the module."""
    found = {name: js.api(fn, *args) for name, (fn, args) in ANSWERED_BY.items()}
    assert set(found) == set(payload), sorted(set(found) ^ set(payload))
    return found


@pytest.mark.parametrize("name", STATE_NAMES)
def test_every_value_of_the_payload_reaches_the_module_and_comes_back(
    name: str, js: JsRuntime
):
    payload = scenario(name)
    js.push(payload)
    assert read_back(js, payload) == payload


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_declared_and_held_counts_agree_for_a_payload_the_surface_built(
    name: str, js: JsRuntime
):
    answer = js.push(scenario(name))
    assert answer["declared"] == answer["held"], answer


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_module_reports_no_fault_for_a_payload_the_surface_built(
    name: str, js: JsRuntime
):
    answer = js.push(scenario(name))
    assert answer["faults"] == [], answer["faults"]


def test_a_dropped_field_moves_the_count_and_is_named_missing(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    whole = js.push(payload)
    payload.pop("call_order")
    holed = js.push(payload)
    assert holed["held"]["fields"] == whole["held"]["fields"] - 1
    named = [one for one in holed["faults"] if one["field"] == "call_order"]
    assert [one["fault"] for one in named] == ["missing"], holed["faults"]


def test_a_payload_that_is_not_an_object_is_named_rather_than_drawn(js: JsRuntime):
    answer = js.json("acervatorSetTradingViewChart(" + json.dumps(OTHER_SYMBOL) + ")")
    assert answer["declared"] is None
    assert answer["faults"][0]["fault"] == "not-an-object"
    assert js.json("acervatorTradingViewChart.isLoaded()") is False


def payload_key_names() -> set:
    """Every key the surface writes, at any depth, across every state."""
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                found.add(name)
                walk(value)
        elif isinstance(node, list):
            for one in node:
                walk(one)

    for name in STATE_NAMES:
        walk(scenario(name))
    return found


def surface_values() -> set:
    """Every string value the surface publishes, a payload key left out."""
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for one in node:
                walk(one)
        elif isinstance(node, str):
            found.add(node)

    for name in STATE_NAMES:
        walk(scenario(name))
    return {one for one in found if one} - payload_key_names()


SURFACE_VALUES = surface_values()
#: A theme name keys the theme bag, so the payload-key rule would let it pass.
THEME_NAMES = set(tvs.THEME_ORDER)
TOKEN_VALUES = {
    str(one)
    for one in json.loads(json.dumps(dss.view_model({}))).get("tokens", {}).values()
}


def caught_by_scan(source: str) -> set:
    """Which of the five checks report on ``source``."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & SURFACE_VALUES:
        caught.add("surface_value")
    if strings & THEME_NAMES:
        caught.add("theme_name")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["numbers"]:
        caught.add("number")
    if found["slashes"]:
        caught.add("regex")
    return caught


def test_the_module_spells_out_no_value_the_surface_owns():
    assert caught_by_scan(MODULE_SOURCE) == set(), sorted(
        set(js_literals(MODULE_SOURCE)["strings"])
        & (SURFACE_VALUES | TOKEN_VALUES | THEME_NAMES)
    )


SPELLED_OUT_LINES = {
    "colour": 'var spelled = "' + tvs.UP_COLOR + '";',
    "watermark_wash": "var spelled = "
    + json.dumps(tvs.CYBERPUNK_DARK["watermark"])
    + ";",
    "token_value": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "default_symbol": 'var spelled = "' + tvs.DEFAULT_SYMBOL + '";',
    "default_theme": 'var spelled = "' + tvs.DEFAULT_THEME + '";',
    "accessible_name": 'var spelled = "' + tvs.WIDGET_ACCESSIBLE_NAME + '";',
    "bridge_object": 'var spelled = "' + tvs.BRIDGE_OBJECT + '";',
    "bridge_callback": 'var spelled = "' + tvs.BRIDGE_CALLBACK + '";',
    "buy_side": 'var spelled = "' + tvs.BUY_SIDE + '";',
    "marker_shape": 'var spelled = "' + tvs.MARKER_SKIN["buy_shape"] + '";',
    "button_class": 'var spelled = "' + tvs.BUTTON_SKIN["class_name"] + '";',
    "handler": 'var spelled = "' + tvs.BUTTON_SKIN["handler"] + '";',
    "call_format": "var spelled = " + json.dumps(tvs.SET_CANDLES_FORMAT) + ";",
    "warning": "var spelled = " + json.dumps(tvs.MISSING_WEBENGINE_WARNING) + ";",
    "script_url": "var spelled = " + json.dumps(tvs.SCRIPT_URL) + ";",
    "font_size": "var spelled = " + str(tvs.WATERMARK["font_size_px"]) + ";",
    "gap": "var spelled = " + str(tvs.TOOLBAR["gap_px"]) + ";",
    "number": "var spelled = 12;",
    "regex": "var spelled = /ab+c/;",
}


@pytest.mark.parametrize("kind", sorted(SPELLED_OUT_LINES))
def test_the_literal_scan_names_a_line_that_spells_a_value_out(kind: str):
    caught = caught_by_scan(SPELLED_OUT_LINES[kind])
    assert caught, "the scan reported nothing on the " + kind + " line"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals("// " + tvs.UP_COLOR + "\nvar kept = 'kept';")
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_spelled_out_value_is_caught_in_the_module_file_itself():
    original = read_module().encode("utf-8")
    before = hashlib.sha256(original).hexdigest()
    caught_each: dict = {}
    hashes: dict = {}
    try:
        for kind in sorted(SPELLED_OUT_LINES):
            swap_module(MODULE_PATH, original + SPELLED_OUT_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(MODULE_PATH, original)
            hashes[kind] = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
    finally:
        swap_module(MODULE_PATH, original)
    unrestored = sorted(kind for kind, found in hashes.items() if found != before)
    assert not unrestored, "the file was not restored after: " + str(unrestored)
    unseen = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not unseen, "the scan saw nothing on these lines: " + str(unseen)
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_changed_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, line in sorted(SPELLED_OUT_LINES.items()):
        if kind == "regex":
            continue
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetTradingViewChart") == "function", kind


JS_KINDS = {
    str: "string",
    bool: "boolean",
    int: "number",
    float: "number",
    dict: "object",
    list: "object",
    type(None): "null",
}


def python_kinds(payload: dict) -> dict:
    """Every payload value's JavaScript type, by dotted path, as Python sees it."""
    found: dict = {}

    def walk(node: Any, prefix: str) -> None:
        if isinstance(node, dict):
            pairs = list(node.items())
        elif isinstance(node, list):
            pairs = [(str(at), one) for at, one in enumerate(node)]
        else:
            return
        for name, value in pairs:
            path = prefix + "." + name if prefix else name
            found[path] = JS_KINDS[type(value)]
            walk(value, path)

    walk(payload, "")
    return found


@pytest.mark.parametrize("name", STATE_NAMES)
def test_every_value_holds_the_same_type_on_both_sides(name: str, js: JsRuntime):
    payload = scenario(name)
    js.push(payload)
    assert js.json("acervatorTradingViewChart.kinds()") == python_kinds(payload)


def test_the_type_reading_would_report_a_string_written_where_a_number_was(
    js: JsRuntime,
):
    payload = scenario("cyberpunk_dark")
    payload["toolbar"]["gap_px"] = str(tvs.TOOLBAR["gap_px"])
    js.push(payload)
    read = js.json("acervatorTradingViewChart.kinds()")
    assert read["toolbar.gap_px"] == "string"
    assert python_kinds(scenario("cyberpunk_dark"))["toolbar.gap_px"] == "number"


BORDER_EDGES = 4
RADIUS_CORNERS = 4


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_drawing_programme_counts_what_css_paints(name: str, js: JsRuntime):
    payload = scenario(name)
    js.push(payload)
    drawn = len(payload["buttons"])
    assert js.api("programme") == {
        "fills": drawn + 1,
        "axisLines": drawn * BORDER_EDGES,
        "slopes": 0,
        "curves": drawn * RADIUS_CORNERS,
        "texts": drawn + 1,
    }


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_mount_holds_the_series_no_css_rule_draws(name: str, js: JsRuntime):
    payload = scenario(name)
    js.push(payload)
    bands = payload["bollinger_series"]["fields"]
    holds = js.api("mount")
    assert holds["slopes"] == len(bands)
    assert holds["fed"] == len(payload["calls"]) == 0
    assert holds["series"] == [
        "candle_series",
        "volume_series",
        "marker_skin",
        "grid_line_skin",
    ] + ["bollinger_series." + one for one in bands]


def test_the_programme_count_moves_when_a_button_leaves_the_toolbar(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    whole = js.push(payload)["programme"]
    payload["buttons"] = payload["buttons"][:-1]
    fewer = js.push(payload)["programme"]
    assert fewer["fills"] == whole["fills"] - 1
    assert fewer["curves"] == whole["curves"] - RADIUS_CORNERS


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_theme_bag_publishes_its_order_as_a_list(name: str, js: JsRuntime):
    payload = scenario(name)
    js.push(payload)
    assert js.api("themeOrder") == payload["theme_order"] == list(tvs.THEME_ORDER)
    assert sorted(js.api("themes")) == sorted(payload["theme_order"])


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_call_bag_publishes_its_order_as_a_list(name: str, js: JsRuntime):
    payload = scenario(name)
    js.push(payload)
    assert js.api("callOrder") == payload["call_order"] == list(tvs.CALL_ORDER)
    assert sorted(js.api("callFormats")) == sorted(payload["call_order"])


def test_the_colour_bag_publishes_its_nine_holes_as_a_list(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    js.push(payload)
    assert js.api("colourKeys") == payload["theme_keys"] + [payload["symbol_key"]]
    assert js.api("colourKeys") == list(payload["colors"])


def test_a_theme_the_order_never_names_is_reported_unordered(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    payload["theme_order"] = payload["theme_order"][:-1]
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "unordered"]
    assert [one["where"] for one in named] == ["theme:" + tvs.THEME_ORDER[-1]], faults


def test_a_repeated_theme_in_the_order_is_reported_and_drawn_once(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    payload["theme_order"] = list(tvs.THEME_ORDER) + [tvs.THEME_ORDER[0]]
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "repeated"]
    assert [one["detail"] for one in named] == [tvs.THEME_ORDER[0]], faults


def test_a_call_the_order_never_names_is_reported_unordered(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    payload["call_order"] = payload["call_order"][:-1]
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "unordered"]
    assert [one["field"] for one in named] == [tvs.CALL_ORDER[-1]], faults


def test_swapping_two_themes_values_moves_the_values_and_not_the_order(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    first, second = tvs.THEME_ORDER[0], tvs.THEME_ORDER[1]
    kept = payload["themes"][first]
    payload["themes"][first] = payload["themes"][second]
    payload["themes"][second] = kept
    js.push(payload)
    assert js.api("themeOrder") == list(tvs.THEME_ORDER)
    assert js.api("theme", first) == tvs.CHART_THEMES[second]


@pytest.mark.parametrize("name", STATE_NAMES)
def test_one_button_carries_the_active_timeframe_and_the_others_do_not(
    name: str, js: JsRuntime
):
    payload = scenario(name)
    js.push(payload)
    live = [one["value"] for one in js.api("buttons") if one["active"]]
    assert live == [payload["active_timeframe"]]


def test_a_second_active_button_is_reported(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    payload["buttons"][0]["active"] = True
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["field"] == "active"]
    assert named, faults


def test_an_active_timeframe_no_button_offers_is_reported_unlisted(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    payload["active_timeframe"] = UNKNOWN_THEME
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "unlisted"]
    assert [one["detail"] for one in named] == [UNKNOWN_THEME], faults


def test_a_repeated_button_value_is_reported_and_drawn_once(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    payload["buttons"] = payload["buttons"] + [dict(payload["buttons"][0])]
    answer = js.push(payload)
    assert js.api("buttonValues") == [one["value"] for one in tvs.TIMEFRAME_BUTTONS]
    named = [one for one in answer["faults"] if one["fault"] == "repeated"]
    assert [one["detail"] for one in named] == [tvs.TIMEFRAME_BUTTONS[0]["value"]]


def test_an_unknown_theme_falls_back_to_the_theme_the_surface_names(js: JsRuntime):
    payload = scenario("unknown_theme")
    js.push(payload)
    assert js.api("field", "theme") == UNKNOWN_THEME
    assert js.api("colours") == dict(
        tvs.CHART_THEMES[tvs.FALLBACK_THEME], symbol=tvs.DEFAULT_SYMBOL
    )


def test_a_colour_that_disagrees_with_its_theme_row_is_reported(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    payload["colors"]["bg"] = tvs.NEON_LIGHT["bg"]
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "disagrees"]
    assert [one["field"] for one in named] == ["bg"], faults


QT_COLOURS = {
    "eight_digit_hex": ("#7f00ff88", "AARRGGBB"),
    "byte_alpha_rgba": ("rgba(0, 255, 136, 128)", "rgba("),
}


@pytest.mark.parametrize("kind", sorted(QT_COLOURS))
def test_a_colour_qt_reads_one_way_and_css_another_is_refused(kind: str, js: JsRuntime):
    spelled, reason = QT_COLOURS[kind]
    payload = scenario("cyberpunk_dark")
    payload["colors"]["accent"] = spelled
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "qt-colour"]
    assert [one["detail"] for one in named] == [reason], faults


@pytest.mark.parametrize("name", STATE_NAMES)
def test_no_colour_the_surface_publishes_is_read_two_ways(name: str, js: JsRuntime):
    js.push(scenario(name))
    assert [one for one in js.api("faults") if one["fault"] == "qt-colour"] == []


@pytest.mark.parametrize("spelled", ["Infinity", "-Infinity", "NaN"])
def test_a_number_json_cannot_carry_is_reported(spelled: str, js: JsRuntime):
    js.bind_json("PAYLOAD", scenario("cyberpunk_dark"))
    faults = js.json(
        "(function () {"
        "  var model = JSON.parse(PAYLOAD);"
        "  model.toolbar.gap_px = " + spelled + ";"
        "  return acervatorSetTradingViewChart(model).faults; })()"
    )
    named = [one for one in faults if one["fault"] == "not-finite"]
    assert [one["detail"] for one in named] == [spelled], faults


MARKUP = '<img src="x" onerror="window.PWNED = true;">'
LONG_SYMBOL = "S" * 200
URL_SHAPED = tvs.SCRIPT_URL
PATH_SHAPED = "..\\..\\windows\\system32"

HOSTILE_VALUES = {
    "missing": None,
    "null": None,
    "number_for_text": len(tvs.DEFAULT_SYMBOL),
    "text_for_number": "three hundred",
    "nan": float("nan"),
    "inf": float("inf"),
    "minus_inf": float("-inf"),
    "big_number": 10**24,
    "long_text": LONG_SYMBOL,
    "markup": MARKUP,
    "newline": "BTC\nUSDT",
    "url_shaped": URL_SHAPED,
    "path_shaped": PATH_SHAPED,
}

HOSTILE_FIELDS = [
    ["symbol"],
    ["theme"],
    ["colors", "bg"],
    ["colors", "symbol"],
    ["active_timeframe"],
    ["buttons"],
    ["theme_order"],
    ["theme_keys"],
    ["themes"],
    ["toolbar", "gap_px"],
    ["button_skin", "padding_px"],
    ["watermark", "font_size_px"],
    ["call_order"],
    ["script_url"],
]


def put_at(payload: dict, path: list, value: Any) -> dict:
    """Set one dotted path inside ``payload`` and answer the payload."""
    here: Any = payload
    for step in path[:-1]:
        here = here[step]
    here[path[-1]] = value
    return payload


def hostile_payload(path: list, kind: str) -> dict:
    """A payload with one field made hostile."""
    payload = scenario("cyberpunk_dark")
    if kind == "missing":
        here: Any = payload
        for step in path[:-1]:
            here = here[step]
        here.pop(path[-1], None)
        return payload
    return put_at(payload, path, HOSTILE_VALUES[kind])


def hostile_json(js: JsRuntime, path: list, kind: str) -> dict:
    """Push a hostile payload, spelling a number JSON cannot carry in JavaScript."""
    payload = hostile_payload(path, "null" if kind in NOT_FINITE else kind)
    if kind not in NOT_FINITE:
        return js.push(payload)
    js.bind_json("PAYLOAD", payload)
    js.bind_json("PATH", path)
    return js.json(
        "(function () {"
        "  var model = JSON.parse(PAYLOAD);"
        "  var path = JSON.parse(PATH);"
        "  var here = model;"
        "  path.slice(0, -1).forEach(function (step) { here = here[step]; });"
        "  here[path[path.length - 1]] = " + NOT_FINITE[kind] + ";"
        "  return acervatorSetTradingViewChart(model); })()"
    )


NOT_FINITE = {"nan": "NaN", "inf": "Infinity", "minus_inf": "-Infinity"}


@pytest.mark.parametrize("kind", sorted(HOSTILE_VALUES))
@pytest.mark.parametrize("at", range(len(HOSTILE_FIELDS)))
def test_a_hostile_field_never_stops_the_module_reading_the_rest(
    at: int, kind: str, js: JsRuntime
):
    answer = hostile_json(js, HOSTILE_FIELDS[at], kind)
    assert js.json("acervatorTradingViewChart.isLoaded()") is True
    assert answer["held"]["fields"] >= len(ANSWERED_BY) - 1
    assert js.api("themeOrder") == list(tvs.THEME_ORDER) or HOSTILE_FIELDS[at] == [
        "theme_order"
    ]


@pytest.mark.parametrize("kind", sorted(HOSTILE_VALUES))
@pytest.mark.parametrize("at", range(len(HOSTILE_FIELDS)))
def test_a_hostile_field_never_costs_the_module_its_drawing_count(
    at: int, kind: str, js: JsRuntime
):
    hostile_json(js, HOSTILE_FIELDS[at], kind)
    drawn = js.api("programme")
    assert drawn["slopes"] == 0
    assert drawn["fills"] >= 1, (HOSTILE_FIELDS[at], kind, drawn)


def test_the_hostile_walk_would_see_a_scalar_where_a_bag_belongs(js: JsRuntime):
    payload = put_at(scenario("cyberpunk_dark"), ["themes"], LONG_SYMBOL)
    answer = js.push(payload)
    assert js.api("themes") == {}
    assert answer["held"]["themes"] == 0
    assert answer["declared"]["themes"] == len(tvs.THEME_ORDER)


def test_the_hostile_walk_would_see_a_scalar_where_a_list_belongs(js: JsRuntime):
    payload = put_at(scenario("cyberpunk_dark"), ["buttons"], LONG_SYMBOL)
    answer = js.push(payload)
    assert js.api("buttonValues") == []
    assert answer["programme"]["fills"] == 1


def test_a_null_inside_a_bag_never_stops_the_value_walk(js: JsRuntime):
    payload = put_at(scenario("cyberpunk_dark"), ["colors", "grid"], None)
    js.push(payload)
    read = js.json("acervatorTradingViewChart.kinds()")
    assert read["colors.grid"] == "null"
    assert read["colors.bg"] == "string"


def test_a_button_that_is_not_a_bag_is_named_and_leaves_the_toolbar(js: JsRuntime):
    payload = scenario("cyberpunk_dark")
    payload["buttons"][2] = None
    answer = js.push(payload)
    assert js.api("buttonValues") == [
        one["value"] for one in tvs.TIMEFRAME_BUTTONS if one["value"] != "15"
    ]
    named = [one for one in answer["faults"] if one["fault"] == "not-an-object"]
    assert [one["detail"] for one in named] == ["null"], answer["faults"]


def test_a_bridge_that_is_absent_is_named_rather_than_raising(js: JsRuntime):
    js.push(scenario("cyberpunk_dark"))
    assert js.json("acervatorTradingViewChart.loadError()") is None
    js.run("acervatorLoadTradingViewChart({})")
    assert js.json("acervatorTradingViewChart.loadError()") is not None
    assert js.json("acervatorTradingViewChart.asking()") is None


CHART_NEEDS = (
    "react.production.min.js",
    "react-dom.production.min.js",
    "design_tokens.js",
    "theme_engine.js",
    "shared_widgets.js",
)


def test_the_renderer_runs_the_chart_module_after_the_modules_it_uses():
    order = load_order()
    assert MODULE_PATH.name in order, str(order)
    at = order.index(MODULE_PATH.name)
    for needed in CHART_NEEDS:
        assert needed in order, needed + " never loads: " + str(order)
        assert order.index(needed) < at, needed


def test_the_order_check_would_see_a_module_it_uses_left_out():
    """The order check reports rather than passing when a name never loads."""
    assert CHART_NEEDS[0] not in [
        name for name in load_order() if name != CHART_NEEDS[0]
    ]


def test_the_chart_module_the_page_names_exists_on_disk():
    assert (WEB / MODULE_PATH.name).is_file()


def test_the_module_declares_no_network_call_of_its_own():
    for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "importScripts", "unpkg"):
        assert banned not in MODULE_SOURCE, banned


def test_the_module_never_spells_the_address_the_surface_carries():
    assert tvs.SCRIPT_URL not in MODULE_SOURCE
    assert tvs.CHART_HTML not in MODULE_SOURCE


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._view.resize(*VIEW_SIZE_PX)
        self._url = QUrl.fromLocalFile(str(INDEX_HTML))
        self._loop = QEventLoop
        self._timer = QTimer
        assert self.load_page(), INDEX_HTML.name + " did not load"
        self.wait_for_module()

    def load_page(self) -> bool:
        """Load the page once and answer whether Chromium reported success."""
        loop = self._loop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        self._view.loadFinished.connect(_loaded)
        self._view.load(self._url)
        self._timer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        self._view.loadFinished.disconnect(_loaded)
        return box.get("ok") is True

    def wait_for_module(self) -> None:
        """Load again until the page defines the chart setter, which a swap delays."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetTradingViewChart") == "function":
                return
            self.settle(READY_STEP_MS)
            self.load_page()
        raise AssertionError(
            "the page never defined the chart module: readyState "
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
    """The page, or a skip when Chromium is not installed with Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


#: STYLE_NAMES lists every computed property read off a drawn part.
STYLE_NAMES = [
    "position",
    "top",
    "right",
    "zIndex",
    "display",
    "columnGap",
    "boxSizing",
    "borderTopWidth",
    "borderTopStyle",
    "borderTopColor",
    "borderTopLeftRadius",
    "fontSize",
    "paddingTop",
    "paddingLeft",
    "backgroundColor",
    "color",
    "overflow",
]

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = " + json.dumps(str(HOST_WIDTH_PX) + "px") + ";"
    "window.HOST.style.height = " + json.dumps(str(HOST_HEIGHT_PX) + "px") + ";"
    "document.body.appendChild(window.HOST);"
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
    "window.SEEN = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.SEEN.push({ method: method, params: params });"
    "  return Promise.resolve(JSON.parse(window.PAYLOAD)); } };"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeStyle = function (tag, cssText, names) {"
    "  var probe = document.createElement(tag);"
    "  probe.style.cssText = cssText;"
    "  window.HOST.appendChild(probe);"
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
    "        text: own, html: el.innerHTML,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)


def token_payload() -> dict:
    """The design token payload as the bridge JSON round trip hands it over."""
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    """The theme payload as the bridge JSON round trip hands it over."""
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


def token_group(name: str) -> str:
    """The one group holding ``name``."""
    groups = token_payload()["groups"]
    found = [one for one in groups if name in groups[one]]
    assert len(found) == 1, (name, found)
    return found[0]


def moved_tokens(pairs: dict) -> dict:
    """The token payload with each named token's number moved."""
    tokens = token_payload()
    for name, value in pairs.items():
        tokens["groups"][token_group(name)][name] = value
        tokens["tokens"][name] = value
    return tokens


def give_tokens(browser: Browser, tokens: dict) -> int:
    """Push ``tokens`` into the page and apply them to the root element."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(tokens)) + ";")
    browser.js("window.THEMES = " + json.dumps(json.dumps(theme_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  if (typeof acervatorSetThemes === 'function') {"
        "    acervatorSetThemes(JSON.parse(window.THEMES)); }"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_chart(browser: Browser, payload: dict, tokens: dict = None) -> list:
    """Render one payload into the page host and return what READ_PARTS finds."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser, token_payload() if tokens is None else tokens)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetTradingViewChart(JSON.parse(window.PAYLOAD));"
        "acervatorTradingViewChart.renderChart(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def by_part(parts: list, name: str) -> list:
    """Every drawn element whose own ``data-part`` is ``name``."""
    return [one for one in parts if one["path"].split("/")[-1] == name]


#: NAMED_CHILDREN lists every part a check below reads off the document.
NAMED_CHILDREN = [
    "chart",
    "toolbar-row",
    "timeframe-button",
    "chart-mount",
    "watermark-text",
]


def test_every_part_a_check_reads_is_drawn_and_named(browser):
    parts = draw_chart(browser, scenario("cyberpunk_dark"))
    drawn = {one["path"].split("/")[-1] for one in parts}
    assert set(NAMED_CHILDREN) <= drawn, sorted(set(NAMED_CHILDREN) - drawn)


def named_counts(browser: Browser) -> list:
    return browser.parsed(
        "[window.HOST.querySelectorAll('*').length,"
        " window.HOST.querySelectorAll('[data-part]').length]"
    )


def test_every_element_the_chart_draws_carries_a_name(browser):
    draw_chart(browser, scenario("cyberpunk_dark"))
    counted = named_counts(browser)
    assert counted[0] == counted[1], counted


def test_the_name_count_would_see_an_element_carrying_no_name(browser):
    draw_chart(browser, scenario("cyberpunk_dark"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('div'));")
    counted = named_counts(browser)
    assert counted[0] == counted[1] + 1, counted


def probe(browser: Browser, tag: str, declaration: str) -> dict:
    """The computed style of a bare element carrying the whole declaration."""
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(tag)
        + ", "
        + json.dumps(declaration)
        + ", JSON.parse(window.STYLE_NAMES))"
    )


def toolbar_declaration(payload: dict) -> str:
    """The Qt page's whole toolbar rule, from the numbers the surface publishes."""
    return (
        "box-sizing: border-box; position: %(position)s; top: %(top_px)spx;"
        " right: %(right_px)spx; z-index: %(z_index)s; display: %(display)s;"
        " gap: %(gap_px)spx" % payload["toolbar"]
    )


def button_declaration(payload: dict, active: bool) -> str:
    """The Qt page's whole button rule, from the numbers the surface publishes."""
    skin = payload["button_skin"]
    colours = payload["colors"]
    return (
        "box-sizing: border-box; background: %(background)s; color: %(color)s;"
        " border: %(border_width_px)spx solid %(border_color)s;"
        " padding: %(pad_v)spx %(pad_h)spx; border-radius: %(radius_px)spx;"
        " cursor: %(cursor)s; font-size: %(font_size_px)spx"
        % {
            "background": colours["accent"] if active else colours["btn_bg"],
            "color": colours["bg"] if active else colours["text"],
            "border_color": colours["accent"] if active else colours["border"],
            "border_width_px": skin["border_width_px"],
            "pad_v": skin["padding_px"][0],
            "pad_h": skin["padding_px"][1],
            "radius_px": skin["radius_px"],
            "cursor": skin["cursor"],
            "font_size_px": skin["font_size_px"],
        }
    )


TOOLBAR_READ = [
    "boxSizing",
    "position",
    "top",
    "right",
    "zIndex",
    "display",
    "columnGap",
]
BUTTON_READ = [
    "boxSizing",
    "backgroundColor",
    "color",
    "borderTopWidth",
    "borderTopStyle",
    "borderTopColor",
    "borderTopLeftRadius",
    "fontSize",
    "paddingTop",
    "paddingLeft",
]


def only(style: dict, names: list) -> dict:
    return {name: style[name] for name in names}


def resting(parts: list) -> list:
    return [
        one
        for one in by_part(parts, "timeframe-button")
        if one["attrs"]["data-active"] == "false"
    ]


def live(parts: list) -> list:
    return [
        one
        for one in by_part(parts, "timeframe-button")
        if one["attrs"]["data-active"] == "true"
    ]


def test_the_toolbar_matches_the_probe_the_surface_declares(browser):
    payload = scenario("cyberpunk_dark")
    parts = draw_chart(browser, payload)
    drawn = by_part(parts, "toolbar-row")[0]["style"]
    wanted = probe(browser, "div", toolbar_declaration(payload))
    assert only(drawn, TOOLBAR_READ) == only(wanted, TOOLBAR_READ)


def test_the_toolbar_probe_reports_a_toolbar_placed_another_way(browser):
    payload = scenario("cyberpunk_dark")
    parts = draw_chart(browser, payload)
    drawn = by_part(parts, "toolbar-row")[0]["style"]
    payload["toolbar"]["top_px"] = payload["toolbar"]["top_px"] * 3
    wanted = probe(browser, "div", toolbar_declaration(payload))
    assert only(drawn, TOOLBAR_READ) != only(wanted, TOOLBAR_READ)


@pytest.mark.parametrize("name", STATE_NAMES)
def test_every_resting_button_matches_the_probe_the_surface_declares(
    name: str, browser
):
    payload = scenario(name)
    parts = draw_chart(browser, payload)
    wanted = probe(browser, "button", button_declaration(payload, False))
    assert len(resting(parts)) == len(payload["buttons"]) - 1
    for one in resting(parts):
        assert only(one["style"], BUTTON_READ) == only(wanted, BUTTON_READ), one


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_active_button_matches_the_probe_the_surface_declares(name: str, browser):
    payload = scenario(name)
    parts = draw_chart(browser, payload)
    wanted = probe(browser, "button", button_declaration(payload, True))
    assert len(live(parts)) == 1
    assert only(live(parts)[0]["style"], BUTTON_READ) == only(wanted, BUTTON_READ)


def test_the_button_probe_reports_a_button_painted_another_way(browser):
    payload = scenario("cyberpunk_dark")
    parts = draw_chart(browser, payload)
    wanted = probe(browser, "button", button_declaration(payload, True))
    assert only(resting(parts)[0]["style"], BUTTON_READ) != only(wanted, BUTTON_READ)


def test_the_border_the_page_computes_is_read_off_the_whole_declaration(browser):
    payload = scenario("cyberpunk_dark")
    parts = draw_chart(browser, payload)
    drawn = resting(parts)[0]["style"]["borderTopWidth"]
    wanted = probe(browser, "button", button_declaration(payload, False))
    assert drawn == wanted["borderTopWidth"]
    assert drawn.endswith("px")


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_chart_ground_and_ink_come_from_the_theme_it_was_built_with(
    name: str, browser
):
    payload = scenario(name)
    parts = draw_chart(browser, payload)
    drawn = by_part(parts, "chart")[0]["style"]
    wanted = probe(
        browser, "div", "background: %(bg)s; color: %(text)s" % payload["colors"]
    )
    assert drawn["backgroundColor"] == wanted["backgroundColor"]
    assert drawn["color"] == wanted["color"]


def test_the_chart_root_is_positioned_so_the_toolbar_sits_over_the_chart(browser):
    parts = draw_chart(browser, scenario("cyberpunk_dark"))
    assert by_part(parts, "chart")[0]["style"]["position"] == "relative"
    reached = browser.parsed(
        "(function () {"
        "  var bar = window.HOST.querySelector('[data-part=\"toolbar-row\"]');"
        "  var root = window.HOST.querySelector('[data-part=\"chart\"]');"
        "  return bar.offsetParent === root; })()"
    )
    assert reached is True


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_watermark_shows_the_symbol_the_chart_was_built_with(name: str, browser):
    payload = scenario(name)
    parts = draw_chart(browser, payload)
    mark = by_part(parts, "watermark-text")[0]
    assert mark["text"] == payload["colors"][payload["symbol_key"]]
    wanted = probe(
        browser,
        "span",
        "font-size: %spx; color: %s"
        % (payload["watermark"]["font_size_px"], payload["colors"]["watermark"]),
    )
    assert mark["style"]["fontSize"] == wanted["fontSize"]
    assert mark["style"]["color"] == wanted["color"]


def test_a_watermark_the_surface_switches_off_is_not_drawn(browser):
    payload = scenario("cyberpunk_dark")
    payload["watermark"]["visible"] = False
    parts = draw_chart(browser, payload)
    assert by_part(parts, "watermark-text") == []
    assert by_part(parts, "chart-mount") != []


def carriers_of(value: Any) -> list:
    """Every design token carrying ``value``, an alias left out."""
    payload = token_payload()
    aliased = set(payload.get("alias_targets", {}))
    return sorted(
        name
        for name, one in payload["tokens"].items()
        if name not in aliased and one is not None and str(one) == str(value)
    )


CHART_COLOURS = sorted(
    {
        one
        for name in STATE_NAMES
        for one in scenario(name)["colors"].values()
        if isinstance(one, str) and (one.startswith("#") or one.startswith("rgba"))
    }
)

CARRIED_COLOURS = sorted(one for one in CHART_COLOURS if carriers_of(one))


def test_the_chart_palette_has_carriers_the_refusal_has_to_step_over():
    assert len(CARRIED_COLOURS) > 1, CARRIED_COLOURS


def test_every_chart_colour_is_painted_from_the_theme_and_not_from_its_carrier(
    browser,
):
    draw_chart(browser, scenario("cyberpunk_dark"))
    refused = {}
    for value in CARRIED_COLOURS:
        refused[value] = {
            "carrier": browser.parsed(
                "acervatorTradingViewChart.variableFor(" + json.dumps(value) + ")"
            ),
            "painted": browser.parsed(
                "acervatorTradingViewChart.paint(" + json.dumps(value) + ")"
            ),
        }
    assert [one["painted"] for one in refused.values()] == CARRIED_COLOURS, refused
    assert all(
        one["carrier"] in carriers_of(value) for value, one in refused.items()
    ), refused


def test_the_colour_refusal_comes_from_the_declared_group_and_not_a_lost_lookup(
    browser,
):
    draw_chart(browser, scenario("cyberpunk_dark"))
    through = {
        value: browser.parsed(
            "acervatorTradingViewChart.variableInGroups("
            + json.dumps(value)
            + ', ["colors"])'
        )
        for value in CARRIED_COLOURS
    }
    assert all(one in carriers_of(value) for value, one in through.items()), through


LONE_SPACING = "SPACE_XXL"
SHARED_SPACING = "SPACE_S"
SHARED_RADIUS = "RADIUS_SM"
SPARE_NUMBER = 4242


def test_the_watermark_size_is_carried_by_a_token_that_does_not_mean_a_size(browser):
    payload = scenario("cyberpunk_dark")
    draw_chart(browser, payload)
    size = payload["watermark"]["font_size_px"]
    assert carriers_of(size) == [LONE_SPACING]
    assert (
        browser.parsed("acervatorTradingViewChart.typeSize(" + json.dumps(size) + ")")
        == str(size) + "px"
    )
    assert "var(--" in browser.parsed(
        "acervatorTradingViewChart.spacing(" + json.dumps(size) + ")"
    )


def test_the_toolbar_offset_is_carried_by_two_tokens_so_no_name_paints_it(browser):
    payload = scenario("cyberpunk_dark")
    draw_chart(browser, payload)
    offset = payload["toolbar"]["top_px"]
    assert carriers_of(offset) == sorted([SHARED_SPACING, SHARED_RADIUS])
    assert (
        browser.parsed("acervatorTradingViewChart.spacing(" + json.dumps(offset) + ")")
        == str(offset) + "px"
    )


def test_a_lone_spacing_token_does_paint_the_toolbar_offset(browser):
    payload = scenario("cyberpunk_dark")
    offset = payload["toolbar"]["top_px"]
    parts = draw_chart(
        browser, payload, tokens=moved_tokens({SHARED_RADIUS: SPARE_NUMBER})
    )
    written = browser.parsed(
        "acervatorTradingViewChart.spacing(" + json.dumps(offset) + ")"
    )
    assert SHARED_SPACING in written, written
    assert by_part(parts, "toolbar-row")[0]["style"]["top"] == str(offset) + "px"


def test_moving_that_token_moves_the_drawn_offset(browser):
    payload = scenario("cyberpunk_dark")
    offset = payload["toolbar"]["top_px"]
    draw_chart(browser, payload, tokens=moved_tokens({SHARED_RADIUS: SPARE_NUMBER}))
    give_tokens(
        browser,
        moved_tokens({SHARED_RADIUS: SPARE_NUMBER, SHARED_SPACING: offset * 3}),
    )
    parts = json.loads(browser.js(READ_PARTS))
    assert by_part(parts, "toolbar-row")[0]["style"]["top"] == str(offset * 3) + "px"


def test_a_rewritten_colour_token_never_moves_a_chart_colour(browser):
    payload = scenario("cyberpunk_dark")
    before = draw_chart(browser, payload)
    after = draw_chart(
        browser, payload, tokens=moved_tokens({"SUCCESS": tvs.NEON_LIGHT["accent"]})
    )
    assert [one["style"]["backgroundColor"] for one in after] == [
        one["style"]["backgroundColor"] for one in before
    ]


def press(browser: Browser, value: str) -> list:
    """Press the button carrying ``value`` and return what the bridge was asked."""
    browser.js(
        "window.HOST.querySelector('[data-value=" + json.dumps(value) + "]').click();"
    )
    return browser.parsed("window.SEEN")


@pytest.mark.parametrize("at", range(len(tvs.TIMEFRAME_BUTTONS)))
def test_each_timeframe_button_asks_the_surface_with_its_own_value(at: int, browser):
    payload = scenario("other_symbol")
    draw_chart(browser, payload)
    assert press(browser, tvs.TIMEFRAME_BUTTONS[at]["value"]) == [
        {
            "method": tvs.METHOD,
            "params": {
                "active": tvs.TIMEFRAME_BUTTONS[at]["value"],
                "symbol": payload["symbol"],
                "theme": payload["theme"],
            },
        }
    ]


def test_the_button_check_would_see_a_press_that_reached_nothing(browser):
    draw_chart(browser, scenario("cyberpunk_dark"))
    assert browser.parsed("window.SEEN") == []


def test_a_button_the_surface_switches_off_asks_nothing(browser):
    payload = scenario("cyberpunk_dark")
    payload["buttons"][0]["enabled"] = False
    draw_chart(browser, payload)
    assert press(browser, payload["buttons"][0]["value"]) == []
    assert press(browser, payload["buttons"][1]["value"]) != []


def test_pressing_a_button_redraws_the_chart_on_what_the_surface_answers(browser):
    draw_chart(browser, scenario("first_active"))
    browser.js(
        "window.PAYLOAD = " + json.dumps(json.dumps(scenario("last_active"))) + ";"
    )
    press(browser, tvs.TIMEFRAME_BUTTONS[-1]["value"])
    browser.settle(READY_STEP_MS)
    drawn = live(json.loads(browser.js(READ_PARTS)))
    assert [one["attrs"]["data-value"] for one in drawn] == [
        tvs.TIMEFRAME_BUTTONS[-1]["value"]
    ]


MARKUP_SLOTS = {
    "button_label": ("timeframe-button", ["buttons", 0, "label"]),
    "watermark_symbol": ("watermark-text", ["colors", "symbol"]),
}


@pytest.mark.parametrize("slot", sorted(MARKUP_SLOTS))
def test_markup_in_a_drawn_string_reaches_the_page_as_characters(slot: str, browser):
    part, path = MARKUP_SLOTS[slot]
    payload = put_at(scenario("cyberpunk_dark"), path, MARKUP)
    parts = draw_chart(browser, payload)
    drawn = [one for one in by_part(parts, part) if one["text"] == MARKUP]
    assert len(drawn) == 1, [one["text"] for one in by_part(parts, part)]
    assert "<img" not in drawn[0]["html"]
    assert browser.js("window.PWNED === true") is False
    assert browser.js("document.images.length") == 0


def test_the_markup_check_would_see_an_image_the_page_really_built(browser):
    draw_chart(browser, scenario("cyberpunk_dark"))
    browser.js("window.HOST.appendChild(document.createElement('img'));")
    assert browser.js("document.images.length") == 1


@pytest.mark.parametrize("slot", sorted(MARKUP_SLOTS))
def test_an_address_in_a_drawn_string_reaches_the_page_as_characters(
    slot: str, browser
):
    part, path = MARKUP_SLOTS[slot]
    payload = put_at(scenario("cyberpunk_dark"), path, URL_SHAPED)
    before = browser.js("document.scripts.length")
    parts = draw_chart(browser, payload)
    assert [one for one in by_part(parts, part) if one["text"] == URL_SHAPED]
    assert browser.js("document.scripts.length") == before
    assert browser.js("document.images.length") == 0


def test_the_page_never_carries_the_address_the_surface_publishes(browser):
    payload = scenario("cyberpunk_dark")
    draw_chart(browser, payload)
    assert payload["script_url"] in payload["html"]
    assert payload["script_url"] not in browser.js("window.HOST.innerHTML")
    assert browser.js("window.HOST.querySelectorAll('script, img, iframe').length") == 0


def test_the_page_opens_no_connection_while_the_chart_is_drawn(browser):
    draw_chart(browser, scenario("cyberpunk_dark"))
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_connection_check_would_see_a_page_that_reached_out(browser):
    draw_chart(browser, scenario("cyberpunk_dark"))
    browser.js(
        "var img = document.createElement('img');"
        "img.src = " + json.dumps(tvs.SCRIPT_URL) + ";"
        "window.HOST.appendChild(img);"
    )
    browser.settle(READY_STEP_MS)
    assert browser.parsed("window.VIOLATIONS") != []


DRAWN_HOSTILE_VALUES = sorted(set(HOSTILE_VALUES) - set(NOT_FINITE))


@pytest.mark.parametrize("at", range(len(HOSTILE_FIELDS)))
def test_one_hostile_field_never_costs_the_chart_its_other_parts(at: int, browser):
    for kind in DRAWN_HOSTILE_VALUES:
        parts = draw_chart(browser, hostile_payload(HOSTILE_FIELDS[at], kind))
        drawn = {one["path"].split("/")[-1] for one in parts}
        assert {"chart", "chart-mount"} <= drawn, (HOSTILE_FIELDS[at], kind, drawn)


def test_the_hostile_check_would_see_a_chart_that_lost_its_mount(browser):
    parts = draw_chart(browser, scenario("cyberpunk_dark"))
    assert "chart-mount" in {one["path"].split("/")[-1] for one in parts}
    browser.js(
        "acervatorTradingViewChart.forget();"
        "acervatorTradingViewChart.renderChart(window.HOST);"
    )
    after = json.loads(browser.js(READ_PARTS))
    assert "chart-mount" not in {one["path"].split("/")[-1] for one in after}


PAINTED_COUNTS = (
    "(function () {"
    "  var all = Array.prototype.slice.call(window.HOST.querySelectorAll('*'));"
    "  var found = { fills: 0, edges: 0, corners: 0, texts: 0, skews: 0 };"
    "  all.forEach(function (el) {"
    "    var style = getComputedStyle(el);"
    "    if (style.backgroundColor !== 'rgba(0, 0, 0, 0)') { found.fills += 1; }"
    "    if (parseFloat(style.borderTopWidth) > 0) { found.edges += 1; }"
    "    if (parseFloat(style.borderTopLeftRadius) > 0) { found.corners += 1; }"
    "    if (style.transform !== 'none') { found.skews += 1; }"
    "    var own = '';"
    "    Array.prototype.slice.call(el.childNodes).forEach(function (n) {"
    "      if (n.nodeType === Node.TEXT_NODE) { own += n.nodeValue; } });"
    "    if (own.trim().length) { found.texts += 1; }"
    "  });"
    "  found.canvases = window.HOST.querySelectorAll('canvas, svg').length;"
    "  return found; })()"
)

EDGES_PER_BOX = 4
CORNERS_PER_BOX = 4


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_published_programme_matches_what_the_page_really_painted(
    name: str, browser
):
    draw_chart(browser, scenario(name))
    painted = browser.parsed(PAINTED_COUNTS)
    published = browser.parsed("acervatorTradingViewChart.programme()")
    assert painted["fills"] == published["fills"], (painted, published)
    assert painted["edges"] * EDGES_PER_BOX == published["axisLines"]
    assert painted["corners"] * CORNERS_PER_BOX == published["curves"]
    assert painted["texts"] == published["texts"], (painted, published)


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_page_paints_no_sloped_line_and_the_mount_holds_three(name: str, browser):
    draw_chart(browser, scenario(name))
    painted = browser.parsed(PAINTED_COUNTS)
    assert painted["skews"] == 0, painted
    assert painted["canvases"] == 0, painted
    assert browser.parsed("acervatorTradingViewChart.programme()")["slopes"] == 0
    assert browser.parsed("acervatorTradingViewChart.mount()")["slopes"] == len(
        scenario(name)["bollinger_series"]["fields"]
    )


def test_the_paint_count_would_see_a_sloped_line_the_page_really_drew(browser):
    draw_chart(browser, scenario("cyberpunk_dark"))
    browser.js(
        "var sloped = document.createElement('div');"
        "sloped.style.transform = 'rotate(30deg)';"
        "window.HOST.firstChild.appendChild(sloped);"
    )
    assert browser.parsed(PAINTED_COUNTS)["skews"] == 1


def test_the_paint_count_would_see_a_fill_the_page_really_drew(browser):
    payload = scenario("cyberpunk_dark")
    draw_chart(browser, payload)
    before = browser.parsed(PAINTED_COUNTS)["fills"]
    browser.js(
        "var block = document.createElement('div');"
        "block.style.background = " + json.dumps(tvs.UP_COLOR) + ";"
        "window.HOST.firstChild.appendChild(block);"
    )
    assert browser.parsed(PAINTED_COUNTS)["fills"] == before + 1


DRAWN_BY_HOSTILE_SYMBOL = {
    "missing": None,
    "null": None,
    "number_for_text": str(HOSTILE_VALUES["number_for_text"]),
    "text_for_number": HOSTILE_VALUES["text_for_number"],
    "big_number": str(float(10**24)),
    "long_text": LONG_SYMBOL,
    "markup": MARKUP,
    "newline": HOSTILE_VALUES["newline"],
    "url_shaped": URL_SHAPED,
    "path_shaped": PATH_SHAPED,
}


@pytest.mark.parametrize("kind", sorted(DRAWN_BY_HOSTILE_SYMBOL))
def test_a_hostile_symbol_draws_as_the_characters_it_carries(kind: str, browser):
    payload = hostile_payload(["colors", "symbol"], kind)
    parts = draw_chart(browser, payload)
    marks = by_part(parts, "watermark-text")
    wanted = DRAWN_BY_HOSTILE_SYMBOL[kind]
    if wanted is None:
        assert marks[0]["text"] == "", marks[0]["text"]
    else:
        assert marks[0]["text"] == wanted, marks[0]["text"][:80]
    assert marks[0]["html"] == (
        marks[0]["text"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    assert browser.js("document.images.length") == 0


def test_the_hostile_symbol_check_would_see_a_symbol_drawn_as_markup(browser):
    payload = hostile_payload(["colors", "symbol"], "markup")
    parts = draw_chart(browser, payload)
    mark = by_part(parts, "watermark-text")[0]
    browser.js(
        "window.HOST.querySelector('[data-part=\"watermark-text\"]').innerHTML ="
        " " + json.dumps(MARKUP) + ";"
    )
    assert "<img" in browser.js(
        "window.HOST.querySelector('[data-part=\"watermark-text\"]').innerHTML"
    )
    assert "<img" not in mark["html"]
