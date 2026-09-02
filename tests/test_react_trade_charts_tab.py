"""The React Asset Charts tab, against the payload Python serves."""

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
from src.gui.main_tabs import trade_charts_tab_surface as tcs  # noqa: E402
from tests.fixtures.web_js_modules import (  # noqa: E402
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "trade_charts_tab.js"
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

#: HOST_WIDTH_PX is set because an unshown view reads ``clientWidth`` as zero.
HOST_WIDTH_PX = 1400
VIEW_SIZE_PX = (1400, 900)


FIXED_NOW = 1_700_000_000.0
FIXED_STAMP = "2026-01-01T00:00:00"
FIXED_TICKS = [10.0, 10.25, 20.0, 20.5, 30.0, 30.75, 40.0, 41.0]

ALPHA = "alpha"
BETA = "beta"
GAMMA = "gamma"

CANDLE_ROWS = [
    [1, 10.0, 12.0, 9.0, 11.0, 100.0],
    [2, 11.0, 13.0, 10.5, 12.5, 120.0],
]

#: A Nuclear scenario feeds candle records, not the rows a fetch answers with.
CANDLE_RECORDS = [
    {"time": 1, "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 100.0},
    {
        "time": 2,
        "open": 11.0,
        "high": 13.0,
        "low": 10.5,
        "close": 12.5,
        "volume": 120.0,
    },
]

BOT_READINGS = {
    "_anchor_target_balance": 1000.0,
    "_target_balance": 1200.0,
    "cycle_growth_cap_usd": 100.0,
    "_fold_cycle_cap_consumed": 50.0,
    "_current_holdings": 4.0,
    "_quote_to_usd": 1.0,
    "_last_gate_state": {
        "scrum_armed": True,
        "fold_armed": False,
        "scrum_blockers": [],
        "fold_blockers": ["cooldown"],
    },
    "_main_lots": [
        {"initial_buy_price": 0.5, "units": 2.0},
        {"initial_buy_price": 30.0, "units": 1.0},
    ],
}


def status(bot_id: str, symbol: str, price: float, state: str = "running") -> dict:
    """One bot status the tab reads a panel out of."""
    return {
        "bot_id": bot_id,
        "symbol": symbol,
        "state": state,
        "exchange": "coinbase",
        "stats": {"current_price": price},
    }


def bridge(steps: list) -> dict:
    """Run every step through ``view_model`` and answer as the bridge would."""
    answer: dict = {}
    for step in steps:
        answer = tcs.view_model(step)
    return json.loads(json.dumps(answer, ensure_ascii=True))


def scenario(name: str) -> dict:
    """The payload one named scenario of the tab produces."""
    return bridge(SCENARIOS[name])


SCENARIOS = {
    "empty": [{"reset": True}],
    "two_bots": [
        {
            "reset": True,
            "statuses": [
                status(ALPHA, "BTC/USD", 1.5),
                status(BETA, "ETH/USD", 2.5, state="idle"),
            ],
        }
    ],
    "no_price": [{"reset": True, "statuses": [status(ALPHA, "BTC/USD", 0.0)]}],
    "overlays": [
        {
            "reset": True,
            "bots": {ALPHA: BOT_READINGS},
            "trades": [[{"bot_id": ALPHA, "symbol": "BTC/USD"}, FIXED_STAMP]],
            "statuses": [status(ALPHA, "BTC/USD", 40.0)],
        }
    ],
    "no_bot": [
        {"reset": True, "bots": {}, "statuses": [status(ALPHA, "BTC/USD", 40.0)]}
    ],
    "followed": [
        {"reset": True, "statuses": [status(ALPHA, "BTC/USD", 1.5)]},
        {"statuses": [status(ALPHA, "SOL/USD", 3.5)]},
    ],
    "fetch_candles": [
        {
            "reset": True,
            "now": FIXED_NOW,
            "ticks": FIXED_TICKS,
            "answers": [[CANDLE_ROWS, "Coinbase OHLCV"]],
            "statuses": [status(ALPHA, "BTC/USD", 1.5)],
            "fetch": True,
        }
    ],
    "fetch_empty": [
        {
            "reset": True,
            "now": FIXED_NOW,
            "ticks": FIXED_TICKS,
            "answers": [[[], "FAILED: No sources available"]],
            "statuses": [status(ALPHA, "BTC/USD", 1.5)],
            "fetch": True,
        }
    ],
    "fetch_throttled": [
        {
            "reset": True,
            "now": FIXED_NOW,
            "ticks": FIXED_TICKS,
            "answers": [[CANDLE_ROWS, "Coinbase OHLCV"]],
            "statuses": [status(ALPHA, "BTC/USD", 1.5)],
            "fetch": True,
        },
        {"fetch": True},
    ],
    "timeframe_changed": [
        {"reset": True, "statuses": [status(ALPHA, "BTC/USD", 1.5)]},
        {"timeframe_change": [ALPHA, "1h"]},
    ],
    "timeframe_unknown": [
        {"reset": True, "statuses": [status(ALPHA, "BTC/USD", 1.5)]},
        {"timeframe_change": [GAMMA, "4h"]},
    ],
    "dropped": [
        {
            "reset": True,
            "statuses": [
                status(ALPHA, "BTC/USD", 1.5),
                status(BETA, "ETH/USD", 2.5),
            ],
        },
        {"statuses": [status(ALPHA, "BTC/USD", 1.5)]},
    ],
    "nuclear": [
        {
            "reset": True,
            "synthetic": [[GAMMA, "DOGE/USD", CANDLE_RECORDS, "spike", 0.0]],
        }
    ],
    "extractor_filtered": [
        {
            "reset": True,
            "statuses": [
                status(ALPHA, "BTC/USD", 1.5),
                dict(status(BETA, "*/USDC", 2.5), mode="extractor"),
            ],
        }
    ],
    "wildcard": [
        {"reset": True, "statuses": [status(ALPHA, "*/USDC", 1.5)]},
    ],
    "blank_id": [
        {"reset": True, "statuses": [status("", "BTC/USD", 1.5)]},
    ],
}

STATE_NAMES = sorted(SCENARIOS)


class JsRuntime(JsEngine):
    """The charts module in one engine, answering as JSON."""

    module_path = MODULE_PATH
    setter = "acervatorSetCharts"

    def api(self, name: str, *args: Any) -> Any:
        """Call one function on ``acervatorCharts`` with JSON arguments."""
        spelled = ", ".join(json.dumps(one) for one in args)
        return self.json("acervatorCharts." + name + "(" + spelled + ")")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


#: ANSWERED_BY maps a payload field to the module function that answers it.
ANSWERED_BY = {
    "accessible_name": ("field", ["accessible_name"]),
    "container": ("container", []),
    "scroll": ("scroll", []),
    "content": ("content", []),
    "panel_order": ("panelOrder", []),
    "panel_count": ("field", ["panel_count"]),
    "dropped": ("dropped", []),
    "trade_log": ("tradeLog", []),
    "logs": ("logs", []),
    "signals": ("signals", []),
    "signal_names": ("signalNames", []),
    "throttled_signals": ("throttledSignals", []),
    "panel_defaults": ("panelDefaults", []),
    "nuclear_defaults": ("nuclearDefaults", []),
    "fetch": ("fetchSettings", []),
    "filters": ("filters", []),
    "outcomes": ("outcomes", []),
    "formats": ("formats", []),
    "floor_format_switch": ("field", ["floor_format_switch"]),
    "empty_source": ("field", ["empty_source"]),
    "bot_id_log_length": ("field", ["bot_id_log_length"]),
    "candle_close_index": ("field", ["candle_close_index"]),
    "keys": ("keys", []),
    "attributes": ("attributes", []),
    "defaults": ("defaults", []),
    "signal_settings": ("signalSettings", []),
    "actions": ("actions", []),
    "timers": ("timers", []),
    "timer_delays_ms": ("timerDelays", []),
    "bus_topics": ("busTopics", []),
    "call_names": ("callNames", []),
    "calls": ("calls", []),
}


def read_back(js: JsRuntime, payload: dict) -> dict:
    """Every declared field, read back out of the module."""
    found = {}
    for field, (name, args) in ANSWERED_BY.items():
        found[field] = js.api(name, *args)
    found["panels"] = {bot_id: js.api("panel", bot_id) for bot_id in js.api("panelIds")}
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
def test_the_module_reports_no_fault_for_a_payload_the_surface_built(
    name: str, js: JsRuntime
):
    answer = js.push(scenario(name))
    assert answer["faults"] == [], answer["faults"]


@pytest.mark.parametrize("name", STATE_NAMES)
def test_the_declared_and_held_counts_agree_for_a_payload_the_surface_built(
    name: str, js: JsRuntime
):
    answer = js.push(scenario(name))
    assert answer["declared"] == answer["held"], answer


def test_a_dropped_field_is_reported_missing_and_moves_the_field_count(js: JsRuntime):
    payload = scenario("two_bots")
    whole = js.push(payload)
    payload.pop("panel_count")
    holed = js.push(payload)
    assert holed["held"]["fields"] == whole["held"]["fields"] - 1
    assert {"field": "panel_count", "fault": "missing"}.items() <= dict(
        holed["faults"][0]
    ).items(), holed["faults"]


def test_a_panel_the_order_never_names_is_reported_unordered(js: JsRuntime):
    payload = scenario("two_bots")
    payload["panel_order"] = [ALPHA]
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "unordered"]
    assert [one["where"] for one in named] == ["panel:" + BETA], faults


def test_an_ordered_bot_with_no_panel_is_reported_unmounted(js: JsRuntime):
    payload = scenario("two_bots")
    payload["panel_order"] = [ALPHA, BETA, GAMMA]
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "unmounted"]
    assert [one["where"] for one in named] == ["panel:" + GAMMA], faults


def test_a_candle_count_that_disagrees_with_the_candles_is_reported(js: JsRuntime):
    payload = scenario("fetch_candles")
    payload["panels"][ALPHA]["panel"]["candle_count"] = len(CANDLE_ROWS) + 1
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "disagrees"]
    assert [one["field"] for one in named] == ["candle_count"], faults


def test_a_layout_slot_count_that_disagrees_with_the_panels_is_reported(js: JsRuntime):
    payload = scenario("two_bots")
    payload["content"]["layout_slots"] = payload["content"]["layout_slots"] + 1
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["field"] == "layout_slots"]
    assert len(named) == 1, faults


def test_a_timeframe_outside_the_published_list_is_reported(js: JsRuntime):
    payload = scenario("two_bots")
    payload["panels"][ALPHA]["panel"]["timeframe"] = "3s"
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "unlisted"]
    assert [one["detail"] for one in named] == ["3s"], faults


def test_a_payload_that_is_not_an_object_is_reported_and_holds_nothing(js: JsRuntime):
    answer = js.push([])
    assert answer["declared"] is None
    assert answer["faults"] == [
        {"where": None, "field": None, "fault": "not-an-object", "detail": "object"}
    ]
    assert js.json("acervatorCharts.isLoaded()") is False


def python_kinds(node: Any, prefix: str, found: dict) -> dict:
    """Every value's JavaScript type, by the same dotted path the module uses."""
    if isinstance(node, dict):
        pairs = list(node.items())
    elif isinstance(node, list):
        pairs = [(str(at), one) for at, one in enumerate(node)]
    else:
        return found
    for name, value in pairs:
        path = prefix + "." + name if prefix else name
        found[path] = js_kind(value)
        python_kinds(value, path, found)
    return found


def js_kind(value: Any) -> str:
    """The ``typeof`` answer one JSON value reaches on the other side."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return "object"


@pytest.mark.parametrize("name", STATE_NAMES)
def test_every_value_carries_the_same_type_on_both_sides(name: str, js: JsRuntime):
    payload = scenario(name)
    js.push(payload)
    assert js.json("acervatorCharts.kinds()") == python_kinds(payload, "", {})


def test_the_type_walk_reports_a_type_that_moved(js: JsRuntime):
    payload = scenario("two_bots")
    js.push(payload)
    mine = python_kinds(payload, "", {})
    assert mine["panel_count"] == "number"
    mine["panel_count"] = "string"
    assert js.json("acervatorCharts.kinds()") != mine


def test_a_wrong_type_is_named_against_the_default_the_surface_publishes(
    js: JsRuntime,
):
    payload = scenario("no_price")
    least = payload["panels"][ALPHA]["panel"]["minimum_height_px"]
    payload["panels"][ALPHA]["panel"]["minimum_height_px"] = str(least)
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "wrong-type"]
    assert [one["field"] for one in named] == ["minimum_height_px"], faults


def test_a_wrong_type_is_named_against_the_peer_panel(js: JsRuntime):
    payload = scenario("two_bots")
    payload["panels"][BETA]["symbol"] = len("ETH/USD")
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "wrong-type"]
    assert [one["field"] for one in named] == ["symbol"], faults


def test_a_null_a_peer_panel_fills_is_named_rather_than_passed_over(js: JsRuntime):
    payload = scenario("two_bots")
    payload["panels"][ALPHA]["symbol"] = None
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "null"]
    assert [one["where"] for one in named] == ["panel:" + ALPHA], faults


def test_a_null_no_peer_panel_fills_is_left_alone(js: JsRuntime):
    payload = scenario("two_bots")
    for bot_id in (ALPHA, BETA):
        payload["panels"][bot_id]["symbol"] = None
    faults = js.push(payload)["faults"]
    assert [one for one in faults if one["fault"] == "null"] == [], faults


def test_a_content_bag_that_is_not_a_bag_is_named_against_the_container(
    js: JsRuntime,
):
    payload = scenario("two_bots")
    payload["content"] = len("content")
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["where"] == "content"]
    assert sorted(one["field"] for one in named) == ["margins_px", "spacing_px"], faults


def test_a_defaults_bag_that_is_not_a_bag_is_named_against_the_nuclear_one(
    js: JsRuntime,
):
    payload = scenario("two_bots")
    payload["panel_defaults"] = len("panel_defaults")
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["where"] == "panel_defaults"]
    assert sorted(one["field"] for one in named) == [
        "minimum_height_px",
        "timeframe",
    ], faults


def test_the_two_bag_checks_are_quiet_on_a_payload_the_surface_built(js: JsRuntime):
    faults = js.push(scenario("two_bots"))["faults"]
    where = {one["where"] for one in faults}
    assert not ({"content", "panel_defaults"} & where), faults


#: NAMED_TYPES lists the fields a default or a peer holds a wrong type against.
NAMED_TYPES = {
    "panel.timeframe",
    "panel.chart_timeframe",
    "panel.minimum_height_px",
    "symbol",
    "exchange_id",
    "last_fetch",
    "panel",
    "panel.built_with",
    "panel.label",
    "panel.candles",
    "panel.candle_count",
    "panel.error_text",
    "panel.source",
    "panel.markers",
    "panel.floors",
    "panel.chart_repaints",
    "panel.panel_repaints",
    "panel.parent_cleared",
    "panel.deleted",
    "panel.timeframe_connected",
    "panel.calls",
}


def test_only_one_panel_names_a_wrong_type_when_it_is_the_only_panel(js: JsRuntime):
    """A single panel is its own peer, so only the defaults can name a type."""
    payload = scenario("no_price")
    payload["panels"][ALPHA]["panel"]["timeframe"] = len("1h")
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "wrong-type"]
    assert [one["field"] for one in named] == ["timeframe"], faults
    assert "panel.timeframe" in NAMED_TYPES


def payload_key_names() -> set:
    """Every object key a real payload carries, which the module must name."""
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            found.update(node)
            for value in node.values():
                walk(value)
            return
        if isinstance(node, list):
            for one in node:
                walk(one)

    for name in STATE_NAMES:
        walk(scenario(name))
    return found


#: NAMED_WORDS lists the Qt enum names the module recognises to pick a CSS word.
NAMED_WORDS = {tcs.SCROLL_HORIZONTAL_POLICY}


def surface_values() -> set:
    """Every string the surface publishes that is not a payload key or a name."""
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
            return
        if isinstance(node, list):
            for one in node:
                walk(one)
            return
        if isinstance(node, str):
            found.add(node)

    for name in STATE_NAMES:
        walk(scenario(name))
    return {one for one in found if one} - payload_key_names() - NAMED_WORDS


SURFACE_VALUES = surface_values()
TOKEN_VALUES = {
    str(one)
    for one in json.loads(json.dumps(dss.view_model({}))).get("tokens", {}).values()
}


def caught_by_scan(source: str) -> set:
    """Which of the four checks report on ``source``."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & SURFACE_VALUES:
        caught.add("surface_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["numbers"]:
        caught.add("number")
    if found["slashes"]:
        caught.add("regex")
    return caught


def test_the_module_spells_out_no_value_the_surface_owns():
    assert caught_by_scan(MODULE_SOURCE) == set(), sorted(
        set(js_literals(MODULE_SOURCE)["strings"]) & (SURFACE_VALUES | TOKEN_VALUES)
    )


def test_the_module_recognises_exactly_the_qt_names_the_scan_lets_through(
    js: JsRuntime,
):
    """A word left off the value list has to be a name the module maps."""
    assert set(js.json("acervatorCharts.policyNames()")) == NAMED_WORDS


def test_no_qt_name_the_scan_lets_through_is_a_value_the_tab_shows(js: JsRuntime):
    """A name that is also a drawn value would slip past the scan unnamed."""
    shown: set = set()
    for name in STATE_NAMES:
        payload = scenario(name)
        for info in payload["panels"].values():
            drawn = info["panel"]
            shown.update(
                str(drawn[field])
                for field in ("label", "source", "error_text", "built_with")
            )
    assert js is not None
    assert not (NAMED_WORDS & shown), sorted(NAMED_WORDS & shown)


SPELLED_OUT_LINES = {
    "colour": 'var spelled = "#00ffcc";',
    "token_value": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "panel_timeframe": 'var spelled = "' + tcs.PANEL_TIMEFRAME + '";',
    "nuclear_exchange": 'var spelled = "' + tcs.NUCLEAR_EXCHANGE_ID + '";',
    "accessible_name": 'var spelled = "' + tcs.ACCESSIBLE_NAME + '";',
    "awaiting_format": "var spelled = "
    + json.dumps(tcs.AWAITING_FORMAT, ensure_ascii=False)
    + ";",
    "follow_log": "var spelled = "
    + json.dumps(tcs.FOLLOW_LOG_FORMAT, ensure_ascii=False)
    + ";",
    "wildcard": 'var spelled = "' + tcs.WILDCARD + '";',
    "extractor": 'var spelled = "' + tcs.EXTRACTOR_MODE + '";',
    "price_format": "var spelled = "
    + json.dumps(tcs.PRICE_LABEL_FORMAT, ensure_ascii=False)
    + ";",
    "minimum_height": "var spelled = " + str(tcs.PANEL_MINIMUM_HEIGHT_PX) + ";",
    "throttle": "var spelled = " + str(tcs.FETCH_THROTTLE_S) + ";",
    "number": "var spelled = 12;",
    "regex": "var spelled = /ab+c/;",
}


@pytest.mark.parametrize("kind", sorted(SPELLED_OUT_LINES))
def test_the_literal_scan_names_a_line_that_spells_a_value_out(kind: str):
    caught = caught_by_scan(SPELLED_OUT_LINES[kind])
    assert caught, "the scan reported nothing on the " + kind + " line"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals("// #00ffcc\nvar kept = 'kept';")
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
    assert not unrestored, "the file was not restored after: " + str(unrestored)
    unseen = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not unseen, "the scan saw nothing on these lines: " + str(unseen)
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_module_read_takes_only_a_file_that_ends_whole():
    assert read_module().rstrip().endswith(MODULE_TAIL)
    for kind, line in sorted(SPELLED_OUT_LINES.items()):
        assert not (MODULE_SOURCE + line).rstrip().endswith(MODULE_TAIL), kind


def test_the_changed_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, line in sorted(SPELLED_OUT_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetCharts") == "function", kind


def test_the_surface_publishes_no_colour_at_all():
    """Nothing on this tab is painted, so no eight-digit hex can arrive."""
    for name in STATE_NAMES:
        spelled = json.dumps(scenario(name))
        assert not HEX_COLOUR.findall(spelled), name


@pytest.mark.parametrize(
    "value,reason",
    [
        ("#80ff0000", "AARRGGBB"),
        ("rgba(255, 0, 0, 128)", "rgba("),
    ],
)
def test_a_colour_css_would_read_differently_is_refused(
    value: str, reason: str, js: JsRuntime
):
    payload = scenario("two_bots")
    payload["panels"][ALPHA]["panel"]["source"] = value
    faults = js.push(payload)["faults"]
    named = [one for one in faults if one["fault"] == "qt-colour"]
    assert [one["detail"] for one in named] == [reason], faults


@pytest.mark.parametrize("value", ["#80ff00", "rgba(255, 0, 0, 0.5)"])
def test_a_colour_css_reads_the_same_way_is_not_refused(value: str, js: JsRuntime):
    payload = scenario("two_bots")
    payload["panels"][ALPHA]["panel"]["source"] = value
    faults = js.push(payload)["faults"]
    assert [one for one in faults if one["fault"] == "qt-colour"] == [], faults


NON_FINITE_PARAMS = {
    "infinite_anchor": {
        "reset": True,
        "bots": {
            ALPHA: {"_anchor_target_balance": float("inf"), "_current_holdings": 1.0}
        },
        "statuses": [status(ALPHA, "BTC/USD", 1.5)],
    },
    "not_a_number_anchor": {
        "reset": True,
        "bots": {
            ALPHA: {
                "_anchor_target_balance": float("inf"),
                "_current_holdings": float("inf"),
            }
        },
        "statuses": [status(ALPHA, "BTC/USD", 1.5)],
    },
    "infinite_floor": {
        "reset": True,
        "bots": {ALPHA: {"_main_lots": [{"initial_buy_price": float("inf")}]}},
        "statuses": [status(ALPHA, "BTC/USD", 1.5)],
    },
    "infinite_candle": {
        "reset": True,
        "synthetic": [
            [
                GAMMA,
                "DOGE/USD",
                [{"open": float("inf"), "high": 1.0, "low": 1.0, "close": 1.0}],
                "",
                0.0,
            ]
        ],
    },
    "infinite_clock": {
        "reset": True,
        "now": float("inf"),
        "answers": [[[], ""]],
        "statuses": [status(ALPHA, "BTC/USD", 1.5)],
        "fetch": True,
    },
}


@pytest.mark.parametrize("name", sorted(NON_FINITE_PARAMS))
def test_the_surface_writes_a_number_json_parse_refuses(name: str):
    """Issue #257 here: view_model writes a number the renderer drops on the floor."""
    answer = tcs.view_model(NON_FINITE_PARAMS[name])
    spelled = json.dumps(answer, ensure_ascii=True)
    assert "Infinity" in spelled or "NaN" in spelled, name


@pytest.mark.parametrize("name", sorted(NON_FINITE_PARAMS))
def test_the_engine_refuses_the_frame_the_surface_wrote(name: str, js: JsRuntime):
    """A bad frame never reaches the module, so no module test can see this."""
    spelled = json.dumps(tcs.view_model(NON_FINITE_PARAMS[name]), ensure_ascii=True)
    js.bind_json("BADFRAME", spelled)
    refused = js.json(
        "(function () {"
        "  try { JSON.parse(JSON.parse(BADFRAME)); return null; }"
        "  catch (e) { return String(e.name); } })()"
    )
    assert refused is not None, name


def test_a_finite_frame_the_same_way_is_accepted(js: JsRuntime):
    """A finite frame proves the refusal above is the numbers and not the wrapper."""
    spelled = json.dumps(scenario("two_bots"), ensure_ascii=True)
    js.bind_json("GOODFRAME", spelled)
    refused = js.json(
        "(function () {"
        "  try { JSON.parse(JSON.parse(GOODFRAME)); return null; }"
        "  catch (e) { return String(e.name); } })()"
    )
    assert refused is None


@pytest.mark.parametrize("spelled", ["Infinity", "-Infinity", "NaN"])
def test_the_module_reports_a_number_that_is_not_finite(spelled: str, js: JsRuntime):
    """A payload handed straight to the module, which the bridge cannot deliver."""
    payload = scenario("two_bots")
    js.push(payload)
    js.bind_json("BOTID", ALPHA)
    faults = js.json(
        "(function () {"
        "  var model = JSON.parse(PAYLOAD);"
        "  model.panels[JSON.parse(BOTID)].panel.tb_anchor = " + spelled + ";"
        "  return acervatorSetCharts(model).faults; })()"
    )
    named = [one for one in faults if one["fault"] == "not-finite"]
    assert [one["detail"] for one in named] == [spelled], faults


def test_a_finite_number_in_the_same_place_is_not_reported(js: JsRuntime):
    payload = scenario("overlays")
    faults = js.push(payload)["faults"]
    assert payload["panels"][ALPHA]["panel"]["tb_anchor"] is not None
    assert [one for one in faults if one["fault"] == "not-finite"] == [], faults


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
        """Load again until the page defines ``acervatorSetCharts``, which a swap can delay."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetCharts") == "function":
                return
            self.settle(READY_STEP_MS)
            self.load_page()
        raise AssertionError(
            "the page never defined the charts module: readyState "
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


#: STYLE_NAMES lists every computed property read off a drawn part.
STYLE_NAMES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "rowGap",
    "display",
    "flexDirection",
    "overflowX",
    "overflowY",
    "minHeight",
    "maxHeight",
    "whiteSpace",
    "textOverflow",
    "userSelect",
    "height",
]

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
    """``dss.view_model`` output through the bridge's ``json.dumps``."""
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    """``tes.view_model`` output through the bridge's ``json.dumps``."""
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


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


def draw_tab(browser: Browser, payload: dict, tokens: dict = None) -> list:
    """Render ``payload`` into ``window.HOST`` and return what READ_PARTS finds."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser, token_payload() if tokens is None else tokens)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetCharts(JSON.parse(window.PAYLOAD));"
        "acervatorCharts.renderTab(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    """What READ_PARTS finds now, without drawing the tab again."""
    return json.loads(browser.js(READ_PARTS))


def rewrite_tokens(browser: Browser, tokens: dict) -> int:
    """Put a changed token table on the root element, leaving the tab drawn."""
    return give_tokens(browser, tokens)


def by_part(parts: list, name: str) -> list:
    """Every drawn element whose own ``data-part`` is ``name``."""
    return [one for one in parts if one["path"].split("/")[-1] == name]


#: NAMED_CHILDREN lists every part a check below reads off the document.
NAMED_CHILDREN = [
    "tab",
    "scroll",
    "content",
    "chart-panel",
    "panel-header",
    "panel-toolbar",
    "timeframe",
    "panel-source",
    "chart-mount",
    "stretch",
]


def test_every_part_a_check_reads_is_drawn_and_named(browser):
    parts = draw_tab(browser, scenario("two_bots"))
    drawn = {one["path"].split("/")[-1] for one in parts}
    assert set(NAMED_CHILDREN) <= drawn, sorted(set(NAMED_CHILDREN) - drawn)


def test_the_empty_column_is_named_when_no_bot_has_a_panel(browser):
    parts = draw_tab(browser, scenario("empty"))
    assert len(by_part(parts, "empty-column")) == 1
    assert by_part(parts, "chart-panel") == []


def test_the_empty_column_is_gone_once_a_bot_has_a_panel(browser):
    parts = draw_tab(browser, scenario("two_bots"))
    assert by_part(parts, "empty-column") == []
    assert len(by_part(parts, "chart-panel")) == 2


def test_the_tab_margins_match_the_probe_the_surface_declares(browser):
    payload = scenario("two_bots")
    parts = draw_tab(browser, payload)
    tab = by_part(parts, "tab")[0]
    sides = payload["container"]["margins_px"]
    css = (
        "padding-left:" + str(sides[0]) + "px;"
        "padding-top:" + str(sides[1]) + "px;"
        "padding-right:" + str(sides[2]) + "px;"
        "padding-bottom:" + str(sides[3]) + "px"
    )
    wanted = browser.parsed(
        "window.probeStyle('div', "
        + json.dumps(css)
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    for side in ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"):
        assert tab["style"][side] == wanted[side], side


def test_the_content_gap_matches_the_probe_the_surface_declares(browser):
    payload = scenario("two_bots")
    parts = draw_tab(browser, payload)
    content = by_part(parts, "content")[0]
    css = "row-gap:" + str(payload["content"]["spacing_px"]) + "px"
    wanted = browser.parsed(
        "window.probeStyle('div', "
        + json.dumps(css)
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert content["style"]["rowGap"] == wanted["rowGap"]


def test_the_margin_probe_reports_a_margin_that_does_not_match(browser):
    payload = scenario("two_bots")
    parts = draw_tab(browser, payload)
    tab = by_part(parts, "tab")[0]
    moved = payload["container"]["margins_px"][0] + 1
    wanted = browser.parsed(
        "window.probeStyle('div', "
        + json.dumps("padding-left:" + str(moved) + "px")
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert tab["style"]["paddingLeft"] != wanted["paddingLeft"]


def test_the_panel_minimum_height_matches_the_probe_the_surface_declares(browser):
    payload = scenario("two_bots")
    parts = draw_tab(browser, payload)
    panel = by_part(parts, "chart-panel")[0]
    least = payload["panels"][ALPHA]["panel"]["minimum_height_px"]
    wanted = browser.parsed(
        "window.probeStyle('div', "
        + json.dumps("min-height:" + str(least) + "px")
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert panel["style"]["minHeight"] == wanted["minHeight"]


def test_the_nuclear_panel_carries_the_maximum_height_the_surface_declares(browser):
    payload = scenario("nuclear")
    parts = draw_tab(browser, payload)
    panel = by_part(parts, "chart-panel")[0]
    most = payload["panels"][GAMMA]["panel"]["maximum_height_px"]
    wanted = browser.parsed(
        "window.probeStyle('div', "
        + json.dumps("max-height:" + str(most) + "px")
        + ", JSON.parse(window.STYLE_NAMES))"
    )
    assert panel["style"]["maxHeight"] == wanted["maxHeight"]


def test_the_scroll_region_hides_the_bar_the_surface_switches_off(browser):
    payload = scenario("two_bots")
    parts = draw_tab(browser, payload)
    scroll = by_part(parts, "scroll")[0]
    assert payload["scroll"]["horizontal_policy"] == tcs.SCROLL_HORIZONTAL_POLICY
    assert scroll["style"]["overflowX"] == "hidden"
    assert scroll["style"]["overflowY"] == "auto"


def test_the_scroll_region_shows_the_bar_when_the_policy_is_something_else(browser):
    payload = scenario("two_bots")
    payload["scroll"]["horizontal_policy"] = "ScrollBarAsNeeded"
    parts = draw_tab(browser, payload)
    assert by_part(parts, "scroll")[0]["style"]["overflowX"] == "auto"


def test_the_scroll_region_takes_keyboard_focus_as_the_qt_area_does(browser):
    draw_tab(browser, scenario("two_bots"))
    reached = browser.js(
        "(function () {"
        "  var el = window.HOST.querySelector('[data-part=\"scroll\"]');"
        "  el.focus();"
        "  return document.activeElement === el; })()"
    )
    assert reached is True


def test_the_header_and_the_source_are_not_selectable_as_in_qt(browser):
    parts = draw_tab(browser, scenario("two_bots"))
    for name in ("panel-header", "panel-source"):
        drawn = by_part(parts, name)[0]
        assert drawn["style"]["userSelect"] == "none", name


def test_a_long_symbol_is_clipped_rather_than_wrapped(browser):
    payload = bridge(
        [{"reset": True, "statuses": [status(ALPHA, "B" * 200 + "/USD", 1.5)]}]
    )
    parts = draw_tab(browser, payload)
    header = by_part(parts, "panel-header")[0]
    assert header["style"]["whiteSpace"] == "nowrap"
    assert header["style"]["textOverflow"] == "ellipsis"
    assert header["style"]["overflowX"] == "hidden"


#: SPACE_XXL is the one spacing token no second token repeats.
LONE_SPACING_NAME = "SPACE_XXL"
SHARED_SPACING_NAME = "SPACE_S"


def token_group(name: str) -> str:
    """The group one token name sits in."""
    groups = token_payload()["groups"]
    for group, bag in groups.items():
        if isinstance(bag, dict) and name in bag:
            return group
    raise AssertionError(name + " sits in no token group")


def moved_tokens(name: str, value: int) -> dict:
    """The token payload with one token's number moved."""
    tokens = token_payload()
    tokens["groups"][token_group(name)][name] = value
    tokens["tokens"][name] = value
    return tokens


def test_only_one_spacing_token_carries_the_lone_number():
    tokens = token_payload()["tokens"]
    lone = tokens[LONE_SPACING_NAME]
    carriers = [one for one, value in tokens.items() if value == lone]
    assert carriers == [LONE_SPACING_NAME], carriers
    shared = tokens[SHARED_SPACING_NAME]
    assert len([one for one, value in tokens.items() if value == shared]) > 1


def test_a_margin_one_token_carries_is_painted_through_that_token(browser):
    payload = scenario("two_bots")
    lone = token_payload()["tokens"][LONE_SPACING_NAME]
    payload["container"]["margins_px"] = [lone, lone, lone, lone]
    draw_tab(browser, payload)
    written = browser.js(
        "window.HOST.querySelector('[data-part=\"tab\"]').style.paddingLeft"
    )
    assert LONE_SPACING_NAME in written, written


def test_a_margin_two_tokens_carry_is_painted_as_a_plain_length(browser):
    payload = scenario("two_bots")
    draw_tab(browser, payload)
    written = browser.js(
        "window.HOST.querySelector('[data-part=\"tab\"]').style.paddingLeft"
    )
    assert SHARED_SPACING_NAME not in written, written
    assert written == str(payload["container"]["margins_px"][0]) + "px"


def test_moving_the_lone_token_moves_only_the_margin_that_borrowed_it(browser):
    payload = scenario("two_bots")
    lone = token_payload()["tokens"][LONE_SPACING_NAME]
    payload["container"]["margins_px"] = [lone, lone, lone, lone]
    before = draw_tab(browser, payload)
    tab_before = by_part(before, "tab")[0]["style"]["paddingLeft"]
    gap_before = by_part(before, "content")[0]["style"]["rowGap"]

    rewrite_tokens(browser, moved_tokens(LONE_SPACING_NAME, lone * 2))
    after = read_parts(browser)
    tab_after = by_part(after, "tab")[0]["style"]["paddingLeft"]
    gap_after = by_part(after, "content")[0]["style"]["rowGap"]

    assert tab_after == str(lone * 2) + "px", tab_after
    assert tab_after != tab_before, tab_before
    assert gap_after == gap_before, gap_before


def test_moving_a_token_two_names_carry_moves_nothing_on_the_tab(browser):
    payload = scenario("two_bots")
    shared = token_payload()["tokens"][SHARED_SPACING_NAME]
    before = draw_tab(browser, payload)
    rewrite_tokens(browser, moved_tokens(SHARED_SPACING_NAME, shared * 3))
    after = read_parts(browser)
    assert [one["style"] for one in after] == [one["style"] for one in before]


def drawn_bots(parts: list) -> list:
    """The bot id of each drawn panel, in the order the column holds them."""
    return [one["attrs"]["data-bot"] for one in by_part(parts, "chart-panel")]


def drawn_symbols(parts: list) -> list:
    """The symbol each drawn panel carries, in column order."""
    return [one["attrs"]["data-symbol"] for one in by_part(parts, "chart-panel")]


def test_the_column_draws_one_panel_per_bot_in_the_order_the_surface_names(browser):
    payload = scenario("two_bots")
    parts = draw_tab(browser, payload)
    assert drawn_bots(parts) == payload["panel_order"] == [ALPHA, BETA]


def test_reordering_the_two_bots_reorders_the_column(browser):
    payload = scenario("two_bots")
    payload["panel_order"] = [BETA, ALPHA]
    parts = draw_tab(browser, payload)
    assert drawn_bots(parts) == [BETA, ALPHA]


def test_swapping_the_two_bots_values_moves_the_values_and_not_the_order(browser):
    payload = scenario("two_bots")
    first = payload["panels"][ALPHA]
    second = payload["panels"][BETA]
    payload["panels"] = {ALPHA: second, BETA: first}
    parts = draw_tab(browser, payload)
    assert drawn_bots(parts) == [ALPHA, BETA]
    assert drawn_symbols(parts) == ["ETH/USD", "BTC/USD"]


def test_each_panel_carries_the_index_the_column_mounted_it_at(browser):
    payload = scenario("two_bots")
    parts = draw_tab(browser, payload)
    at = [one["attrs"]["data-index"] for one in by_part(parts, "chart-panel")]
    assert at == ["0", "1"]


def test_a_dropped_bot_leaves_the_column_and_stays_in_the_dropped_list(browser):
    payload = scenario("dropped")
    parts = draw_tab(browser, payload)
    assert drawn_bots(parts) == [ALPHA]
    assert payload["dropped"] == [BETA]


def test_the_column_mounts_the_slot_count_the_surface_declares(browser):
    payload = scenario("two_bots")
    parts = draw_tab(browser, payload)
    content = by_part(parts, "content")[0]
    assert content["attrs"]["data-mounted"] == str(len(payload["panel_order"]))
    assert content["attrs"]["data-layout-slots"] == str(
        payload["content"]["layout_slots"]
    )
    assert len(by_part(parts, "stretch")) == payload["content"]["stretch_slots"]


def test_each_panel_header_shows_the_label_the_surface_wrote(browser):
    payload = scenario("two_bots")
    parts = draw_tab(browser, payload)
    shown = [one["text"] for one in by_part(parts, "panel-header")]
    assert shown == [
        payload["panels"][ALPHA]["panel"]["label"],
        payload["panels"][BETA]["panel"]["label"],
    ]


def test_a_panel_with_no_price_keeps_the_symbol_it_was_built_with(browser):
    payload = scenario("no_price")
    parts = draw_tab(browser, payload)
    assert by_part(parts, "panel-header")[0]["text"] == "BTC/USD"


def test_the_timeframe_control_offers_every_timeframe_the_surface_lists(browser):
    payload = scenario("two_bots")
    draw_tab(browser, payload)
    offered = browser.parsed(
        "Array.prototype.slice.call("
        "  window.HOST.querySelectorAll('[data-part=\"timeframe\"] option')"
        ").map(function (one) { return one.value; })"
    )
    assert offered == payload["panel_defaults"]["timeframe_options"] * 2


def test_the_timeframe_control_sits_where_the_panel_says_it_sits(browser):
    payload = scenario("two_bots")
    draw_tab(browser, payload)
    chosen = browser.parsed(
        "Array.prototype.slice.call("
        "  window.HOST.querySelectorAll('[data-part=\"timeframe\"]')"
        ").map(function (one) { return one.value; })"
    )
    assert chosen == [
        payload["panels"][ALPHA]["panel"]["timeframe"],
        payload["panels"][BETA]["panel"]["timeframe"],
    ]


def test_the_timeframe_control_names_the_action_the_surface_declares(browser):
    payload = scenario("two_bots")
    parts = draw_tab(browser, payload)
    named = by_part(parts, "timeframe")[0]["attrs"]["data-action"]
    assert named == payload["actions"]["panel.chart.timeframe_changed"]


def test_the_timeframe_control_can_take_keyboard_focus(browser):
    draw_tab(browser, scenario("two_bots"))
    reached = browser.js(
        "(function () {"
        "  var el = window.HOST.querySelector('[data-part=\"timeframe\"]');"
        "  el.focus();"
        "  return document.activeElement === el; })()"
    )
    assert reached is True


def test_the_chart_mount_carries_what_the_tab_fed_the_chart(browser):
    payload = scenario("overlays")
    parts = draw_tab(browser, payload)
    mount = by_part(parts, "chart-mount")[0]
    panel = payload["panels"][ALPHA]["panel"]
    assert mount["attrs"]["data-slot"] == "native_chart"
    assert mount["attrs"]["data-floor-count"] == str(len(panel["floors"]))
    assert mount["attrs"]["data-marker-count"] == str(len(panel["markers"]))
    assert float(mount["attrs"]["data-tb-anchor"]) == panel["tb_anchor"]
    assert mount["attrs"]["data-candle-count"] == str(panel["candle_count"])


def test_the_chart_mount_shows_the_error_line_the_fetch_wrote(browser):
    payload = scenario("fetch_empty")
    parts = draw_tab(browser, payload)
    shown = by_part(parts, "panel-error")[0]["text"]
    assert shown == payload["panels"][ALPHA]["panel"]["error_text"]


def test_no_error_line_is_drawn_when_the_fetch_wrote_none(browser):
    payload = scenario("fetch_candles")
    parts = draw_tab(browser, payload)
    assert payload["panels"][ALPHA]["panel"]["error_text"] == ""
    assert by_part(parts, "panel-error") == []


def test_the_panel_source_shows_where_the_candles_came_from(browser):
    payload = scenario("fetch_candles")
    parts = draw_tab(browser, payload)
    assert by_part(parts, "panel-source")[0]["text"] == "Coinbase OHLCV"


def test_a_followed_symbol_shows_the_awaiting_line_on_the_new_pair(browser):
    payload = scenario("followed")
    parts = draw_tab(browser, payload)
    assert by_part(parts, "panel-error")[0]["text"] == tcs.awaiting_text("SOL/USD")


MARKUP = '<img src="x" onerror="window.PWNED = true;">'

MARKUP_SLOTS = {
    "label": ("panel-header", ["panels", ALPHA, "panel", "label"]),
    "source": ("panel-source", ["panels", ALPHA, "panel", "source"]),
    "error_text": ("panel-error", ["panels", ALPHA, "panel", "error_text"]),
}


def put_at(payload: dict, path: list, value: Any) -> dict:
    """Set one dotted path inside ``payload`` and answer the payload."""
    here: Any = payload
    for step in path[:-1]:
        here = here[step]
    here[path[-1]] = value
    return payload


@pytest.mark.parametrize("field", sorted(MARKUP_SLOTS))
def test_markup_in_a_drawn_string_reaches_the_page_as_text(field: str, browser):
    part, path = MARKUP_SLOTS[field]
    payload = put_at(scenario("fetch_empty"), path, MARKUP)
    parts = draw_tab(browser, payload)
    drawn = by_part(parts, part)[0]
    assert drawn["text"] == MARKUP
    assert "<img" not in drawn["html"]
    assert browser.js("window.PWNED === true") is False
    assert browser.js("document.images.length") == 0


def test_the_markup_check_would_see_an_image_the_page_really_built(browser):
    draw_tab(browser, scenario("two_bots"))
    browser.js("window.HOST.appendChild(document.createElement('img'));")
    assert browser.js("document.images.length") == 1


LONG_SYMBOL = "S" * 200
HOSTILE_VALUES = {
    "missing": None,
    "null": None,
    "number_for_text": len("BTC/USD"),
    "text_for_number": "three hundred",
    "big_number": 10**24,
    "long_text": LONG_SYMBOL,
    "markup": MARKUP,
}

#: ORDER_FIELD is the one field that decides which panels the column mounts.
ORDER_FIELD = ["panel_order"]

HOSTILE_FIELDS = [
    ["panels", ALPHA, "symbol"],
    ["panels", ALPHA, "panel", "label"],
    ["panels", ALPHA, "panel", "source"],
    ["panels", ALPHA, "panel", "error_text"],
    ["panels", ALPHA, "panel", "timeframe"],
    ["panels", ALPHA, "panel", "minimum_height_px"],
    ["panels", ALPHA, "panel", "candle_count"],
    ["panels", ALPHA, "panel", "floors"],
    ["panels", ALPHA, "last_fetch"],
    ORDER_FIELD,
    ["content"],
    ["panel_defaults"],
]


def hostile_payload(path: list, kind: str) -> dict:
    """A two-bot payload with one field made hostile."""
    payload = scenario("two_bots")
    if kind == "missing":
        here: Any = payload
        for step in path[:-1]:
            here = here[step]
        here.pop(path[-1], None)
        return payload
    return put_at(payload, path, HOSTILE_VALUES[kind])


@pytest.mark.parametrize("kind", sorted(HOSTILE_VALUES))
@pytest.mark.parametrize("at", range(len(HOSTILE_FIELDS)))
def test_a_hostile_field_never_stops_the_module_reading_the_rest(
    at: int, kind: str, js: JsRuntime
):
    payload = hostile_payload(HOSTILE_FIELDS[at], kind)
    answer = js.push(payload)
    assert answer["held"]["fields"] >= len(ANSWERED_BY) - 1
    assert js.json("acervatorCharts.isLoaded()") is True
    assert js.api("panelIds") == [ALPHA, BETA]


@pytest.mark.parametrize("kind", sorted(HOSTILE_VALUES))
@pytest.mark.parametrize("at", range(len(HOSTILE_FIELDS)))
def test_one_hostile_panel_never_costs_the_other_panel_its_place(
    at: int, kind: str, browser
):
    payload = hostile_payload(HOSTILE_FIELDS[at], kind)
    parts = draw_tab(browser, payload)
    if HOSTILE_FIELDS[at] == ORDER_FIELD:
        return
    assert BETA in drawn_bots(parts), (HOSTILE_FIELDS[at], kind, drawn_bots(parts))


def test_the_second_panel_check_would_see_a_column_that_lost_it(browser):
    payload = scenario("two_bots")
    payload["panel_order"] = [ALPHA]
    parts = draw_tab(browser, payload)
    assert BETA not in drawn_bots(parts)


def test_a_hostile_panel_order_draws_no_panel_and_reports_it(js: JsRuntime):
    payload = scenario("two_bots")
    payload["panel_order"] = LONG_SYMBOL
    answer = js.push(payload)
    assert js.api("mountedIds") == []
    named = [one for one in answer["faults"] if one["fault"] == "unordered"]
    assert [one["where"] for one in named] == ["panel:" + ALPHA, "panel:" + BETA]


def test_a_repeated_bot_in_the_order_is_reported_and_drawn_once(js: JsRuntime):
    payload = scenario("two_bots")
    payload["panel_order"] = [ALPHA, ALPHA, BETA]
    answer = js.push(payload)
    assert js.api("mountedIds") == [ALPHA, BETA]
    named = [one for one in answer["faults"] if one["fault"] == "repeated"]
    assert [one["detail"] for one in named] == [ALPHA], answer["faults"]


def test_a_big_number_reaches_the_page_as_the_surface_spelled_it(browser):
    payload = put_at(
        scenario("two_bots"), ["panels", ALPHA, "panel", "candle_count"], 10**24
    )
    parts = draw_tab(browser, payload)
    mount = by_part(parts, "chart-mount")[0]
    assert mount["attrs"]["data-candle-count"] == str(float(10**24))


def test_a_bridge_that_is_absent_is_named_rather_than_raising(js: JsRuntime):
    js.push(scenario("two_bots"))
    assert js.json("acervatorCharts.loadError()") is None
    js.run("acervatorLoadCharts({})")
    assert js.json("acervatorCharts.loadError()") is not None


def test_the_page_names_the_charts_module_after_the_modules_it_uses():
    html = INDEX_HTML.read_text(encoding="utf-8")
    at = html.index(MODULE_PATH.name)
    for needed in ("react.production.min.js", "design_tokens.js", "shared_widgets.js"):
        assert html.index(needed) < at, needed


def test_the_charts_module_the_page_names_exists_on_disk():
    assert (WEB / MODULE_PATH.name).is_file()


def test_the_page_opens_no_connection_while_the_tab_is_drawn(browser):
    browser.js(
        "window.VIOLATIONS = [];"
        "document.addEventListener('securitypolicyviolation', function (e) {"
        "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
    )
    draw_tab(browser, scenario("overlays"))
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_module_declares_no_network_call_of_its_own():
    for banned in ("fetch(", "XMLHttpRequest", "WebSocket", "importScripts"):
        assert banned not in MODULE_SOURCE, banned
