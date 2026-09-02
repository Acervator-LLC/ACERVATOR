"""Drives fleet_replay_panel.js from every state the Fleet Replay surface builds."""

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

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import fleet_replay_panel_surface as frp
from src.gui.main_tabs import simulator_tab_surface as sts
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "fleet_replay_panel.js"
MERGED_PATHS = (
    WEB / "design_tokens.js",
    WEB / "theme_engine.js",
    WEB / "shared_widgets.js",
    WEB / "header_strip.js",
)
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
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Read once at collection, so a swap in another worker meets no open file.
MERGED_SOURCES = tuple(
    (one.name, one.read_text(encoding="utf-8")) for one in MERGED_PATHS
)

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 400
READY_ROUNDS = 100
READY_STEP_MS = 100
VIEW_SIZE_PX = (1200, 900)
HOST_WIDTH_PX = 1100
HOST_HEIGHT_PX = 800

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

FLEET = [
    {"symbol": "BTC/USD", "target_balance": 1200.0, "exchange_id": "coinbase"},
    {"symbol": "ETH/USD", "target_balance": 800.5, "exchange_id": "coinbase"},
    {"symbol": "BTC/USD", "target_balance": 400.25, "exchange_id": "coinbase"},
]

BAR = [1_700_000_000_000, 10.0, 11.0, 9.0, 10.5, 100.0]

GATE_READING = {"scrum_armed": True, "fold_armed": False, "scrum_blockers": ["cash"]}


def spawned_controller(configs: list, candles_by_symbol: dict, smart_wires: Any) -> Any:
    """One replay controller holding a sim bot per config and a filled tape."""
    del smart_wires
    bots = [
        frp.BotSource(
            bot_id="bot-" + str(at),
            config=frp.BotConfigSource(symbol=frp.config_symbol(one)),
            stats=frp.StatsSource(realised_pnl=1.5, total_scrummed_usd=20.0),
            holdings=2.0,
            last_price=10.5,
            gate_state=dict(GATE_READING),
        )
        for at, one in enumerate(configs)
    ]
    tape = frp.TapeSource(
        rows_by_symbol={name: list(rows) for name, rows in candles_by_symbol.items()},
        balances={"USD": 500.0, "USDC": 25.0},
        trade_count=4,
        my_trades=[{"symbol": "BTC/USD"}],
    )
    return frp.ControllerSource(
        bots=bots,
        tape=tape,
        progress=frp.ProgressSource(total_candles=2),
        markers=[["BTC/USD", 1, 2.0]],
    )


def fresh_model(configs: Any = None, raises: Any = None) -> Any:
    """One panel wired to a stored fleet, a tablet registry and a loop."""
    return frp.FleetReplayPanelModel(
        loader=frp.FleetLoaderSource(
            configs=FLEET if configs is None else configs, raises=raises
        ),
        registry=frp.TabletRegistrySource(
            rows_by_asset={"BTC": [BAR, BAR], "ETH": [BAR]}
        ),
        controller_factory=spawned_controller,
        loop=object(),
    )


def started_model() -> Any:
    """One panel whose fleet is loaded and whose replay has been handed off."""
    model = fresh_model()
    model.load()
    model.start(now_ms=frp.MS_PER_DAY, ytd_start_ms=0)
    return model


def state_model(name: str) -> Any:
    """The panel in one named state, driven through its own steps."""
    if name == "idle":
        return fresh_model()
    if name == "refused":
        model = fresh_model(raises=RuntimeError("bot_state unreadable"))
        model.load()
        return model
    if name == "loaded":
        model = fresh_model()
        model.load()
        return model
    model = started_model()
    if name == "running":
        return model
    if name == "midway":
        model.controller.progress.candles_played = 1
        model.controller.progress.trades_fired = 3
        model.controller.progress.per_symbol_trade_count = {"BTC/USD": 3}
        model.refresh_progress(now_s=10.0)
        return model
    if name == "finished":
        model.controller.progress.candles_played = 2
        model.controller.progress.finished = True
        model.refresh_progress(now_s=10.0)
        return model
    if name == "stopped":
        model.stop()
        return model
    if name == "cleared":
        model.reset()
        return model
    if name == "drained":
        model.visual_refresh_tick()
        model.drain()
        return model
    if name == "empty":
        model.controller.progress.total_candles = 0
        model.refresh_progress(now_s=10.0)
        return model
    if name == "overrun":
        model.controller.progress.candles_played = 5
        model.refresh_progress(now_s=10.0)
        return model
    raise AssertionError(name)


STATES = (
    "idle",
    "refused",
    "loaded",
    "running",
    "midway",
    "finished",
    "stopped",
    "cleared",
    "drained",
    "empty",
    "overrun",
)


def state_payload(name: str) -> dict:
    """The whole payload one state hands the renderer."""
    return frp.build_view_model(state_model(name))


def token_payload() -> dict:
    return dss.build_view_model()


def theme_payload() -> dict:
    return tes.build_view_model()


class JsRuntime(JsEngine):
    """A QJSEngine holding fleet_replay_panel.js and the modules it reads."""

    module_path = MODULE_PATH
    setter = "acervatorSetFleetReplay"

    def __init__(self, engine: Any, source: str) -> None:
        engine.evaluate("var window = this;")
        for name, body in MERGED_SOURCES:
            loaded = engine.evaluate(body, name)
            assert not loaded.isError(), name + ": " + loaded.toString()
        super().__init__(engine, source)
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")
        self.bind_json("THEMES", theme_payload())
        self.run("acervatorSetThemes(JSON.parse(THEMES));")

    def answer(self, expression: str) -> Any:
        return self.json("acervatorFleetReplay." + expression)


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


def python_kinds(payload: Any) -> dict:
    """The JavaScript type of every payload value, by dotted path."""
    found: dict = {}

    def descend(path: str, value: Any) -> None:
        if isinstance(value, dict):
            walk(path, value)
            return
        if isinstance(value, (list, tuple)):
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


def pushed(js: JsRuntime, payload: Any) -> Any:
    """setPanel's own report for `payload`, never letting it raise."""
    return js.push(payload)


def fault_kinds(report: Any) -> list:
    return sorted({one["fault"] for one in report["faults"]})


#: HEADER_STYLE carries an eight-digit hex, so this fault stands in every state.
HEADER_COLOUR_FAULT = {
    "where": "header",
    "field": "style_sheet",
    "fault": "qt-colour",
    "detail": "AARRGGBB",
}


def extra_faults(report: Any) -> list:
    """Every fault but the standing one the shipped header colour raises."""
    return [one for one in report["faults"] if one != HEADER_COLOUR_FAULT]


@pytest.mark.parametrize("state", STATES)
def test_every_top_level_field_answers_by_the_value_the_surface_sent(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    pushed(js, payload)
    for name in js.answer("declaredFields()"):
        found = js.json("acervatorFleetReplay.field(" + json.dumps(name) + ")")
        assert found == json.loads(json.dumps(payload[name])), (state, name)


def test_the_value_check_reports_a_field_that_moved(js: JsRuntime):
    payload = state_payload("loaded")
    payload["ytd_trade_count"] = 41
    pushed(js, payload)
    assert (
        js.answer("field('ytd_trade_count')")
        != state_payload("loaded")["ytd_trade_count"]
    )


NUMBER_FIELDS = (
    "ytd_trade_count",
    "connections_at_build",
    "gate_rows_drawn",
    "chart_cleared",
    "visual_refresh_every_n_candles",
)


@pytest.mark.parametrize("name", NUMBER_FIELDS)
def test_text_standing_where_a_number_belongs_is_named(js: JsRuntime, name: str):
    payload = state_payload("loaded")
    payload[name] = "seven"
    report = pushed(js, payload)
    named = [one for one in extra_faults(report) if one["field"] == name]
    assert [one["fault"] for one in named] == ["wrong-type"], report["faults"]


@pytest.mark.parametrize("state", STATES)
def test_every_nested_value_reaches_the_module(js: JsRuntime, state: str):
    payload = state_payload(state)
    pushed(js, payload)
    assert sorted(js.answer("kinds()")) == sorted(python_kinds(payload)), state


@pytest.mark.parametrize("state", STATES)
def test_both_sides_read_every_value_as_the_same_type(js: JsRuntime, state: str):
    payload = state_payload(state)
    pushed(js, payload)
    assert js.answer("kinds()") == python_kinds(payload), state


def test_the_type_reader_reports_a_type_that_changed(js: JsRuntime):
    payload = state_payload("loaded")
    payload["ytd_trade_count"] = str(payload["ytd_trade_count"])
    pushed(js, payload)
    assert js.answer("kinds()") != python_kinds(state_payload("loaded"))


@pytest.mark.parametrize("state", STATES)
def test_every_state_carries_only_the_header_colour_fault(js: JsRuntime, state: str):
    report = pushed(js, state_payload(state))
    assert report["faults"] == [HEADER_COLOUR_FAULT], (state, report["faults"])


@pytest.mark.parametrize("state", STATES)
def test_the_counts_agree_with_what_the_surface_declares(js: JsRuntime, state: str):
    payload = state_payload(state)
    report = pushed(js, payload)
    assert report["declared"] == report["held"], (state, report)
    assert report["held"]["rows"] == payload["fleet_table"]["row_count"], state
    assert report["held"]["fields"] == len(js.answer("declaredFields()")), state


def test_a_missing_field_lowers_the_held_count_and_not_the_declared(js: JsRuntime):
    payload = state_payload("loaded")
    del payload["pins"]
    report = pushed(js, payload)
    assert report["held"]["fields"] == report["declared"]["fields"] - 1
    assert "missing" in fault_kinds(report)


def test_a_dropped_button_lowers_the_held_button_count(js: JsRuntime):
    payload = state_payload("loaded")
    del payload["buttons"]["stop"]
    report = pushed(js, payload)
    assert report["held"]["buttons"] == report["declared"]["buttons"] - 1
    assert report["declared"]["buttons"] == 5


def test_a_payload_that_is_not_an_object_is_refused(js: JsRuntime):
    report = pushed(js, [])
    assert report["declared"] is None
    assert fault_kinds(report) == ["not-an-object"]
    assert js.answer("isLoaded()") is False


def test_the_module_asks_the_bridge_by_the_method_the_surface_names(js: JsRuntime):
    assert js.answer("method()") == frp.METHOD


def test_the_panel_root_is_named_for_the_space_its_parent_tab_leaves(js: JsRuntime):
    pushed(js, state_payload("loaded"))
    assert js.answer("drawnParts()")[0] == sts.MOUNT_FLEET_REPLAY
    assert sts.MOUNT_FLEET_REPLAY in sts.MOUNTS


def test_the_module_forgets_what_it_held(js: JsRuntime):
    pushed(js, state_payload("loaded"))
    js.run("acervatorFleetReplay.forget();")
    assert js.answer("isLoaded()") is False
    assert js.answer("tableRows()") == []
    assert js.answer("sent()") == []


def payload_values(payload: Any, found: set) -> set:
    if isinstance(payload, dict):
        for value in payload.values():
            payload_values(value, found)
    elif isinstance(payload, (list, tuple)):
        for one in payload:
            payload_values(one, found)
    elif isinstance(payload, str):
        found.add(payload)
    return found


def payload_keys(payload: Any, found: set) -> set:
    if isinstance(payload, dict):
        for name, value in payload.items():
            found.add(name)
            payload_keys(value, found)
    elif isinstance(payload, (list, tuple)):
        for one in payload:
            payload_keys(one, found)
    return found


SAMPLES = [state_payload(one) for one in ("drained", "midway", "refused")]

PUBLISHED_VALUES: set = set()
PUBLISHED_KEYS: set = set()
for one in SAMPLES:
    payload_values(one, PUBLISHED_VALUES)
    payload_keys(one, PUBLISHED_KEYS)

#: A naming value tells the module what a field means; it paints nothing.
NAMING_VALUES = {frp.METHOD, "", frp.EDIT_TRIGGERS, frp.HEADER_RESIZE_MODE}

PAINTED_VALUES = PUBLISHED_VALUES - NAMING_VALUES - PUBLISHED_KEYS

TOKEN_VALUES = {
    str(one)
    for one in token_payload()["tokens"].values()
    if one is not None and str(one)
}


def test_the_module_writes_no_value_the_surface_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"{MODULE_PATH.name} writes the painted values {written}"


def test_the_painted_set_still_holds_the_words_the_panel_shows():
    """The painted set is not empty, so the check above measures something."""
    for shown in (
        frp.TITLE_TEXT,
        frp.SUBTITLE_TEXT,
        frp.LOAD_BUTTON_TEXT,
        frp.START_BUTTON_TEXT,
        frp.FULL_EVAL_TEXT,
        frp.FLEET_GROUP_TITLE,
        frp.COLUMNS[0],
        frp.IDLE_PROGRESS_TEXT,
        frp.HEADER_STYLE,
        frp.STATUS_STYLE,
    ):
        assert shown in PAINTED_VALUES, shown


def test_the_module_writes_no_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"{MODULE_PATH.name} writes the token values {written}"


def test_the_module_writes_no_number_and_no_colour():
    assert MODULE_LITERALS["numbers"] == [], MODULE_LITERALS["numbers"]
    assert HEX_COLOUR.findall(MODULE_SOURCE) == []


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], MODULE_LITERALS["slashes"]


def test_the_module_names_only_the_surface_keys_it_reads(js: JsRuntime):
    pushed(js, SAMPLES[0])
    allowed = set(js.answer("declaredNames()"))
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_KEYS
    assert not written - allowed, sorted(written - allowed)


SPELLED_OUT_LINES = {
    "caption": 'var spelled = "' + frp.START_BUTTON_TEXT + '";',
    "column": 'var spelled = "' + frp.COLUMNS[0] + '";',
    "sheet": 'var spelled = "' + frp.STATUS_STYLE + '";',
    "colour": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "margin": "var spelled = " + str(frp.OUTER_MARGIN_PX) + ";",
    "delay": "var spelled = " + str(frp.PROGRESS_TIMER_MS) + ";",
    "number": "var spelled = 12;",
    "regex": "var spelled = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the five scans report on `source`."""
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
    assert caught_by_scan(SPELLED_OUT_LINES[kind]), kind


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals("// " + str(dss.PRIMARY) + '\nvar kept = "kept";')
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
    assert not unrestored, f"the file was not restored after: {unrestored}"
    unseen = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not unseen, f"the scan saw nothing on these lines in the file: {unseen}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_module_read_takes_only_a_file_that_ends_whole():
    assert read_module().rstrip().endswith(MODULE_TAIL)
    for kind, line in sorted(SPELLED_OUT_LINES.items()):
        assert not (MODULE_SOURCE + line).rstrip().endswith(MODULE_TAIL), kind


def test_the_changed_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, line in sorted(SPELLED_OUT_LINES.items()):
        if kind == "regex":
            continue
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetFleetReplay") == "function", kind


def test_the_fleet_rows_keep_the_order_the_surface_sent(js: JsRuntime):
    payload = state_payload("loaded")
    pushed(js, payload)
    assert js.answer("rowOrder()") == [["BTC/USD", 0], ["ETH/USD", 0], ["BTC/USD", 1]]


def test_the_order_check_names_a_reordered_pair_of_rows(js: JsRuntime):
    payload = state_payload("loaded")
    rows = payload["fleet_table"]["rows"]
    rows[0], rows[1] = rows[1], rows[0]
    pushed(js, payload)
    assert js.answer("rowOrder()") == [["ETH/USD", 0], ["BTC/USD", 0], ["BTC/USD", 1]]


def test_a_symbol_alone_is_not_an_identity_because_two_bots_share_one(js: JsRuntime):
    pushed(js, state_payload("loaded"))
    assert js.answer("collidingNames()") == ["BTC/USD"]
    assert [one[0] for one in js.answer("rowsNamed('BTC/USD')")] == [0, 1]


def test_the_collision_check_stays_quiet_when_no_symbol_repeats(js: JsRuntime):
    payload = state_payload("loaded")
    payload["fleet_table"]["rows"][2][0] = "SOL/USD"
    pushed(js, payload)
    assert js.answer("collidingNames()") == []


def test_a_swap_of_two_rows_values_is_named_against_the_pair_that_carries_it(
    js: JsRuntime,
):
    payload = state_payload("loaded")
    rows = payload["fleet_table"]["rows"]
    before = [list(one) for one in rows]
    rows[0][1], rows[2][1] = rows[2][1], rows[0][1]
    pushed(js, payload)
    after = js.answer("rowsNamed('BTC/USD')")
    assert [one[1][1] for one in after] == [before[2][1], before[0][1]]


def test_a_symbol_no_row_carries_answers_nothing(js: JsRuntime):
    pushed(js, state_payload("loaded"))
    assert js.answer("rowsNamed('DOGE/USD')") == []


def test_the_button_order_is_the_two_rows_the_panel_draws(js: JsRuntime):
    pushed(js, state_payload("loaded"))
    assert js.answer("buttonOrder()") == ["load", "fetch", "reset", "start", "stop"]


def test_the_stat_strip_order_is_the_list_the_surface_published(js: JsRuntime):
    payload = state_payload("drained")
    pushed(js, payload)
    assert list(payload["stat_fields"]) == payload["stat_field_names"]
    assert js.answer("statFieldNames()") == payload["stat_field_names"]


def test_a_reordered_stat_bag_is_named(js: JsRuntime):
    payload = state_payload("drained")
    names = payload["stat_field_names"]
    payload["stat_fields"] = {
        name: payload["stat_fields"][name] for name in reversed(names)
    }
    report = pushed(js, payload)
    assert "order-mismatch" in fault_kinds(report)


def test_the_call_sequence_keeps_the_order_the_panel_took(js: JsRuntime):
    payload = state_payload("finished")
    pushed(js, payload)
    taken = [one[0] for one in js.answer("calls()")]
    assert taken[:2] == ["load.start", "load.table"]
    assert taken[-1] == "progress.finished"
    assert taken == [one[0] for one in payload["calls"]]


def test_a_call_named_by_no_published_name_is_reported(js: JsRuntime):
    payload = state_payload("finished")
    payload["calls"][0][0] = "load.begin"
    report = pushed(js, payload)
    assert "unknown-name" in fault_kinds(report)


PRESSES = ("load", "fetch", "reset", "start", "stop")
TICKS = ("progress", "drain")


@pytest.mark.parametrize("name", PRESSES)
def test_each_button_hands_the_bridge_the_step_its_action_names(
    js: JsRuntime, name: str
):
    payload = state_payload("loaded")
    pushed(js, payload)
    js.run("acervatorFleetReplay.press(" + json.dumps(name) + ");")
    sent = js.answer("sent()")
    assert len(sent) == 1, sent
    action = sent[0]["action"]
    assert action == name + "_button.clicked", sent
    assert sent[0]["params"]["steps"] == [payload["actions"][action]], sent
    assert sent[0]["params"]["full_evaluation"] is False


@pytest.mark.parametrize("name", TICKS)
def test_each_timer_hands_the_bridge_the_step_its_action_names(
    js: JsRuntime, name: str
):
    payload = state_payload("running")
    pushed(js, payload)
    js.run("acervatorFleetReplay.tick(" + json.dumps(name) + ");")
    sent = js.answer("sent()")
    assert len(sent) == 1, sent
    action = sent[0]["action"]
    assert action == name + "_timer.timeout", sent
    assert sent[0]["params"]["steps"] == [payload["actions"][action]], sent


def test_a_name_no_action_carries_sends_nothing(js: JsRuntime):
    pushed(js, state_payload("loaded"))
    js.run("acervatorFleetReplay.press('rewind');")
    js.run("acervatorFleetReplay.tick('rewind');")
    assert js.answer("sent()") == []


def test_the_five_button_actions_and_two_timer_actions_are_all_published(
    js: JsRuntime,
):
    payload = state_payload("loaded")
    pushed(js, payload)
    assert sorted(js.answer("actionNames()")) == sorted(payload["actions"])
    assert payload["connections_at_build"] == len(PRESSES)


def test_an_action_the_surface_stopped_publishing_is_named(js: JsRuntime):
    payload = state_payload("loaded")
    del payload["actions"]["stop_button.clicked"]
    report = pushed(js, payload)
    assert "missing" in fault_kinds(report)


#: ENDLESS_VALUES holds the three numbers JSON has no word for.
ENDLESS_VALUES = {
    "nan": float("nan"),
    "inf": float("inf"),
    "minus_inf": float("-inf"),
}


def test_no_value_in_any_state_is_anything_but_plain_data(js: JsRuntime):
    for state in STATES:
        payload = state_payload(state)
        json.dumps(payload)
        report = pushed(js, payload)
        assert "not-plain-data" not in fault_kinds(report), state


def test_the_plain_data_walk_names_an_endless_number_a_page_could_hand_it(
    js: JsRuntime,
):
    js.bind_json("PAYLOAD", state_payload("loaded"))
    found = js.json(
        "(function () { var one = JSON.parse(PAYLOAD);"
        " one.numbers.candle_ms = Infinity;"
        " return acervatorSetFleetReplay(one).faults; })()"
    )
    named = [one for one in found if one["fault"] == "not-plain-data"]
    assert [one["where"] for one in named] == ["numbers.candle_ms"], found


@pytest.mark.parametrize("kind", sorted(ENDLESS_VALUES))
def test_an_endless_number_never_reaches_the_module_at_all(js: JsRuntime, kind: str):
    payload = state_payload("loaded")
    payload["numbers"]["candle_ms"] = ENDLESS_VALUES[kind]
    js.bind_json("PAYLOAD", payload)
    refused = js.run(
        "(function () { try { JSON.parse(PAYLOAD); return ''; }"
        " catch (err) { return err.name; } })()"
    ).toString()
    assert refused == "SyntaxError", (kind, refused)
    assert json.dumps(ENDLESS_VALUES[kind]) in ("NaN", "Infinity", "-Infinity")


def test_the_panel_publishes_no_bot_object_and_no_tape(js: JsRuntime):
    payload = state_payload("drained")
    for row in payload["bot_statuses"]:
        assert set(row) >= {"bot_id", "symbol", "stats"}
        assert isinstance(row["stats"], dict)
    pushed(js, payload)
    assert extra_faults({"faults": js.answer("faults()")}) == []


HOSTILE_FIELDS = (
    "fleet_table",
    "buttons",
    "header",
    "status",
    "progress",
    "actions",
    "calls",
    "pins",
    "stat_fields",
    "timers",
)

HOSTILE_VALUES = {
    "missing": None,
    "null": None,
    "number": 7,
    "text": "seven",
    "huge": 10**24,
    "long_name": "b" * 200,
    "markup": '<img src="x" width="500">',
    "newline": "one\ntwo",
}


def hostile_payload(field: str, kind: str) -> dict:
    payload = state_payload("loaded")
    if kind == "missing":
        payload.pop(field, None)
        return payload
    payload[field] = HOSTILE_VALUES[kind]
    return payload


@pytest.mark.parametrize("field", HOSTILE_FIELDS)
@pytest.mark.parametrize("kind", sorted(HOSTILE_VALUES))
def test_a_hostile_field_is_recorded_and_never_raises(
    js: JsRuntime, field: str, kind: str
):
    report = pushed(js, hostile_payload(field, kind))
    assert extra_faults(report), (field, kind)
    assert isinstance(report["held"]["fields"], int)


@pytest.mark.parametrize("field", HOSTILE_FIELDS)
def test_a_scalar_where_a_bag_or_a_list_belongs_is_named(js: JsRuntime, field: str):
    report = pushed(js, hostile_payload(field, "number"))
    named = [one for one in report["faults"] if one["field"] == field]
    assert named, (field, report["faults"])
    assert {"not-an-object", "not-a-list"} & {one["fault"] for one in named}, named


CELL_VALUES = {
    "number": 7,
    "huge": 10**24,
    "long_name": "b" * 200,
    "markup": '<img src="x" width="500">',
    "newline": "one\ntwo",
    "null": None,
}


@pytest.mark.parametrize("kind", sorted(CELL_VALUES))
def test_a_hostile_cell_value_is_recorded_by_its_row_and_column(
    js: JsRuntime, kind: str
):
    payload = state_payload("loaded")
    payload["fleet_table"]["rows"][1][0] = CELL_VALUES[kind]
    report = pushed(js, payload)
    quiet = kind in ("long_name", "newline", "null")
    assert bool(extra_faults(report)) is not quiet, (kind, report["faults"])


def test_a_row_that_is_not_a_list_is_named(js: JsRuntime):
    payload = state_payload("loaded")
    payload["fleet_table"]["rows"][0] = "BTC/USD"
    report = pushed(js, payload)
    assert "not-a-list" in fault_kinds(report)


def test_a_null_row_is_named(js: JsRuntime):
    payload = state_payload("loaded")
    payload["fleet_table"]["rows"][0] = None
    report = pushed(js, payload)
    assert "not-a-list" in fault_kinds(report)


def test_a_replay_of_zero_frames_draws_an_empty_table_and_no_fault(js: JsRuntime):
    payload = state_payload("empty")
    report = pushed(js, payload)
    assert extra_faults(report) == [], report["faults"]
    assert payload["progress"]["text"].startswith("Replay: 0/0 candles (0.0%)")


def test_a_position_past_the_last_frame_is_drawn_as_the_surface_wrote_it(
    js: JsRuntime,
):
    payload = state_payload("overrun")
    report = pushed(js, payload)
    assert extra_faults(report) == [], report["faults"]
    assert payload["progress"]["text"].startswith("Replay: 5/2 candles (250.0%)")


def test_a_row_count_larger_than_the_rows_is_named(js: JsRuntime):
    payload = state_payload("loaded")
    payload["fleet_table"]["row_count"] = 9
    report = pushed(js, payload)
    assert "count-mismatch" in fault_kinds(report)


def test_a_duplicate_symbol_is_answered_as_two_rows_not_one(js: JsRuntime):
    payload = state_payload("loaded")
    payload["fleet_table"]["rows"][1][0] = "BTC/USD"
    pushed(js, payload)
    assert len(js.answer("rowsNamed('BTC/USD')")) == 3


def test_the_header_border_colour_qt_and_css_read_differently_is_refused(
    js: JsRuntime,
):
    report = pushed(js, state_payload("loaded"))
    assert report["faults"] == [HEADER_COLOUR_FAULT]
    assert js.answer("qtColour('1px solid #00cccc44')") == "AARRGGBB"
    kept = js.answer("keptSheet(" + json.dumps(frp.HEADER_STYLE) + ")")
    assert [one.split(":")[0] for one in kept.split(";")] == [
        "background",
        "border-radius",
    ], kept


def test_a_six_digit_hex_inside_a_sheet_is_kept(js: JsRuntime):
    pushed(js, state_payload("loaded"))
    assert js.answer("qtColour('color:#00ffcc')") is None
    assert js.answer("styleOf('color:#00ffcc')") == {"color": "#00ffcc"}


def test_a_sheet_carrying_an_eight_digit_hex_is_named(js: JsRuntime):
    payload = state_payload("loaded")
    payload["status"]["style_sheet"] = "color:#00cccc44;"
    report = pushed(js, payload)
    assert "qt-colour" in fault_kinds(report)


def test_the_alpha_byte_is_scaled_by_the_ceiling_the_module_publishes(js: JsRuntime):
    pushed(js, state_payload("loaded"))
    scale = js.answer("alphaScale()")
    assert scale == 255
    written = js.answer("scaledAlpha('rgba(0,255,204,10)')")
    assert written == "rgba(0,255,204," + str(10 * (1 / scale)) + ")"


def test_an_alpha_already_written_as_a_fraction_is_left_alone(js: JsRuntime):
    pushed(js, state_payload("loaded"))
    kept = js.answer("keptSheet('background:rgba(0,255,204,0.5)')")
    assert kept == "background:rgba(0,255,204,0.5)"


MARK = '<img src="x" width="500">'
PLAIN = 'img src="x" width="500"'


def carrier_widths(qapp, name: str) -> list:
    """The width one carrier gives the marked text and the same characters."""
    assert qapp is not None
    from PySide6.QtWidgets import (
        QCheckBox,
        QGroupBox,
        QLabel,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
    )

    def label_width(body: str) -> int:
        return int(QLabel(body).sizeHint().width())

    def button_width(body: str) -> int:
        return int(QPushButton(body).sizeHint().width())

    def check_width(body: str) -> int:
        return int(QCheckBox(body).sizeHint().width())

    def group_width(body: str) -> int:
        return int(QGroupBox(body).minimumSizeHint().width())

    def item_width(body: str) -> int:
        table = QTableWidget(1, 1)
        table.setItem(0, 0, QTableWidgetItem(body))
        return int(table.sizeHintForColumn(0))

    def header_width(body: str) -> int:
        table = QTableWidget(1, 1)
        table.setHorizontalHeaderLabels([body])
        return int(table.horizontalHeader().sectionSizeHint(0))

    made = {
        "QLabel": label_width,
        "QPushButton": button_width,
        "QCheckBox": check_width,
        "QGroupBox": group_width,
        "QTableWidgetItem": item_width,
        "QHeaderView": header_width,
    }[name]
    return [made(MARK), made(PLAIN)]


READS_MARKUP = {
    "QLabel": True,
    "QPushButton": False,
    "QCheckBox": False,
    "QGroupBox": False,
    "QTableWidgetItem": False,
    "QHeaderView": False,
}


@pytest.mark.parametrize("carrier", sorted(READS_MARKUP))
def test_each_carrier_on_this_panel_is_measured_for_markup(qapp, carrier: str):
    marked, plain = carrier_widths(qapp, carrier)
    reads = marked > plain * 2
    assert reads is READS_MARKUP[carrier], (carrier, marked, plain)


def test_the_markup_measurement_tells_the_two_apart(qapp):
    marked, plain = carrier_widths(qapp, "QLabel")
    assert marked == 500 and plain < marked
    other, plain_other = carrier_widths(qapp, "QPushButton")
    assert other > plain_other


@pytest.mark.parametrize(
    "field", ("title", "subtitle", "status", "progress", "group-title")
)
def test_a_label_carrying_a_tag_is_named_as_markup(js: JsRuntime, field: str):
    payload = state_payload("loaded")
    if field == "title":
        payload["header"]["title"] = MARK
    elif field == "subtitle":
        payload["header"]["subtitle"] = MARK
    elif field == "group-title":
        payload["fleet_table"]["title"] = MARK
    else:
        payload[field]["text"] = MARK
    report = pushed(js, payload)
    named = [one for one in report["faults"] if one["fault"] == "markup"]
    assert [one["where"] for one in named] == [field], report["faults"]


def test_the_markup_check_stays_quiet_on_a_label_with_no_tag(js: JsRuntime):
    report = pushed(js, state_payload("loaded"))
    assert [one for one in report["faults"] if one["fault"] == "markup"] == []


def test_the_header_colour_fault_is_the_one_defect_the_surface_itself_carries(
    js: JsRuntime,
):
    """HEADER_STYLE is shipped source, so this is reported and not repaired."""
    report = pushed(js, state_payload("idle"))
    assert report["faults"] == [HEADER_COLOUR_FAULT]
    assert "#00cccc44" in frp.HEADER_STYLE


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
        """Spins until the page defines the module, which loadFinished does not promise."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetFleetReplay") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the module: readyState "
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
        return json.loads(
            self.js(
                "JSON.stringify((function () { var v = "
                + expression
                + "; return v === undefined ? null : v; })())"
            )
        )

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


STYLE_NAMES = [
    "color",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "whiteSpace",
    "overflow",
    "userSelect",
    "display",
    "flexDirection",
    "gap",
    "gridTemplateColumns",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderTopLeftRadius",
    "flexGrow",
]

EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "border-radius": ("borderTopLeftRadius",),
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
    "window.HOST = document.getElementById('fleet-replay-host');"
    "if (!window.HOST) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'fleet-replay-host';"
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
    "      found.push({ path: here, tag: el.tagName, attrs: attrs,"
    "        text: el.textContent, children: el.children.length,"
    "        disabled: el.disabled === true,"
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


def give_tokens(browser: Browser) -> int:
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw(browser: Browser, payload: dict) -> list:
    """Render `payload` into the host and return what READ_PARTS finds."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetFleetReplay(JSON.parse(window.PAYLOAD));"
        "acervatorFleetReplay.renderPanel(window.HOST);"
    )
    return read_parts(browser)


def read_parts(browser: Browser) -> list:
    return json.loads(browser.js(READ_PARTS))


def declarations_of(sheet: Any) -> list:
    """Each property and value of `sheet`, read in Python."""
    found: list = []
    if not isinstance(sheet, str):
        return found
    body = sheet
    if "{" in sheet:
        body = sheet.split("{", 1)[1].split("}", 1)[0]
    for one in body.split(";"):
        parts = one.split(":")
        prop = parts.pop(0).strip()
        if not parts or not prop:
            continue
        value = ":".join(parts).strip()
        if value:
            found.append((prop, value))
    return found


def scaled(value: str) -> str:
    """One Qt rgba value with its alpha byte turned into a CSS fraction."""
    head, tail = value.split("(", 1)
    fields = [one.strip() for one in tail.split(")")[0].split(",")]
    alpha = float(fields[3]) * (1 / 255)
    return head + "(" + ",".join(fields[:3] + [repr(alpha)]) + ")"


def usable(prop: str, value: str) -> str:
    if value.count("#") and len(value.split("#")[1].split(" ")[0]) == 8:
        return ""
    if value.startswith("rgba(") and "." not in value.split(",")[3]:
        return scaled(value)
    return value


def probe(browser: Browser, tag: str, sheet: Any) -> dict:
    """The computed values a bare `tag` takes from the whole of `sheet`."""
    names: list = []
    body: list = []
    for prop, value in declarations_of(sheet):
        kept = usable(prop, value)
        if not kept:
            continue
        names.extend(EXPANDED.get(prop, (prop,)))
        body.append(prop + ":" + kept)
    if not names:
        return {}
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(tag)
        + ", "
        + json.dumps(";".join(body))
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
    assert browser.js("typeof window.acervatorFleetReplay") == "object"
    assert browser.js("typeof window.acervatorLoadFleetReplay") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw(browser, state_payload("drained"))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


@pytest.mark.parametrize("state", STATES)
def test_every_drawn_element_carries_a_name_the_checks_read(
    browser: Browser, state: str
):
    parts = draw(browser, state_payload(state))
    assert parts, state
    assert browser.parsed(COUNT_ELEMENTS)[0] == browser.parsed(COUNT_ELEMENTS)[1]
    named = {one["attrs"]["data-part"] for one in parts}
    assert named <= set(browser.parsed("acervatorFleetReplay.drawnParts()")), named


def test_the_naming_check_reports_an_element_left_without_a_name(browser: Browser):
    draw(browser, state_payload("loaded"))
    browser.js("window.HOST.firstChild.appendChild(document.createElement('span'));")
    counts = browser.parsed(COUNT_ELEMENTS)
    assert counts[0] == counts[1] + 1


@pytest.mark.parametrize("state", ("idle", "loaded", "midway", "finished", "drained"))
def test_one_row_is_drawn_for_each_row_the_surface_sent(browser: Browser, state: str):
    payload = state_payload(state)
    parts = draw(browser, payload)
    rows = by_part(parts, "body-row")
    assert len(rows) == payload["fleet_table"]["row_count"], state
    cells = by_part(parts, "body-cell")
    assert len(cells) == len(rows) * payload["fleet_table"]["column_count"], state


def test_every_drawn_cell_carries_its_row_pair_and_its_column(browser: Browser):
    payload = state_payload("loaded")
    parts = draw(browser, payload)
    found = [
        (
            one["attrs"]["data-key"],
            one["attrs"]["data-nth"],
            one["attrs"]["data-column"],
        )
        for one in by_part(parts, "body-cell")
    ]
    assert found[:3] == [
        ("BTC/USD", "0", "Symbol"),
        ("BTC/USD", "0", "Target USD"),
        ("BTC/USD", "0", "Sim Trades"),
    ]
    assert ("BTC/USD", "1", "Symbol") in found


def test_a_reordered_pair_of_rows_is_seen_in_the_document_by_its_pair(
    browser: Browser,
):
    payload = state_payload("loaded")
    rows = payload["fleet_table"]["rows"]
    rows[0], rows[1] = rows[1], rows[0]
    parts = draw(browser, payload)
    found = [
        (one["attrs"]["data-key"], one["attrs"]["data-nth"])
        for one in by_part(parts, "body-row")
    ]
    assert found == [("ETH/USD", "0"), ("BTC/USD", "0"), ("BTC/USD", "1")]


def test_a_swapped_cell_value_is_seen_against_the_pair_that_now_carries_it(
    browser: Browser,
):
    payload = state_payload("loaded")
    rows = payload["fleet_table"]["rows"]
    rows[0][1], rows[2][1] = rows[2][1], rows[0][1]
    parts = draw(browser, payload)
    found = {
        (one["attrs"]["data-key"], one["attrs"]["data-nth"]): one["text"]
        for one in by_part(parts, "body-cell")
        if one["attrs"]["data-column"] == "Target USD"
    }
    assert found[("BTC/USD", "0")] == "$400.25"
    assert found[("BTC/USD", "1")] == "$1,200.00"


@pytest.mark.parametrize(
    "part,sheet_of",
    (
        ("header", lambda p: p["header"]["style_sheet"]),
        ("title", lambda p: p["header"]["title_style"]),
        ("subtitle", lambda p: p["header"]["subtitle_style"]),
        ("status", lambda p: p["status"]["style_sheet"]),
        ("progress", lambda p: p["progress"]["style_sheet"]),
    ),
)
def test_each_styled_part_takes_the_whole_declaration_the_surface_wrote(
    browser: Browser, part: str, sheet_of: Any
):
    payload = state_payload("loaded")
    parts = draw(browser, payload)
    wanted = probe(browser, "div", sheet_of(payload))
    assert wanted, part
    drawn = one_part(parts, part)["style"]
    for name, value in wanted.items():
        assert drawn[name] == value, (part, name, drawn[name], value)


def test_the_style_comparison_would_see_a_value_that_moved(browser: Browser):
    payload = state_payload("loaded")
    parts = draw(browser, payload)
    wanted = probe(browser, "div", payload["status"]["style_sheet"])
    moved = probe(browser, "div", "color:#123456;font-size:11px;")
    assert wanted["color"] != moved["color"]
    assert one_part(parts, "status")["style"]["color"] == wanted["color"]


def test_the_header_takes_the_background_qt_paints_at_a_byte_alpha(browser: Browser):
    payload = state_payload("loaded")
    parts = draw(browser, payload)
    drawn = one_part(parts, "header")["style"]["backgroundColor"]
    wanted = probe(browser, "div", payload["header"]["style_sheet"])
    assert drawn == wanted["backgroundColor"]
    assert drawn != "rgb(0, 255, 204)", drawn


def test_the_header_border_is_not_drawn_because_css_reads_that_colour_differently(
    browser: Browser,
):
    parts = draw(browser, state_payload("loaded"))
    drawn = one_part(parts, "header")["style"]
    assert drawn["borderTopStyle"] == "none"
    assert drawn["borderTopWidth"] == "0px"


BORROWED_COLOURS = {
    "#00ffcc": "PRIMARY",
    "#888": "CARD_METRIC_LABEL",
    "#7fb3ff": "MAIN_BADGE_TEXT",
}


@pytest.mark.parametrize("value,name", sorted(BORROWED_COLOURS.items()))
def test_no_colour_on_this_panel_borrows_the_one_token_that_carries_it(
    browser: Browser, value: str, name: str
):
    draw(browser, state_payload("loaded"))
    assert browser.parsed(
        "acervatorWidgets.variableFor(" + json.dumps(value) + ")"
    ) == (name)
    written = browser.parsed(
        "acervatorFleetReplay.styleOf(" + json.dumps("color:" + value) + ")"
    )
    assert written == {"color": value}, written


def test_the_token_lookup_would_have_named_a_carrier_for_each(browser: Browser):
    """The refusal above is a choice, because one token carries each value."""
    draw(browser, state_payload("loaded"))
    for value, name in BORROWED_COLOURS.items():
        found = browser.parsed(
            "acervatorWidgets.variableFor(" + json.dumps(value) + ")"
        )
        assert found == name, (value, found)


def test_the_outer_box_takes_the_only_layout_numbers_the_surface_publishes(
    browser: Browser,
):
    payload = state_payload("loaded")
    parts = draw(browser, payload)
    panel = one_part(parts, "fleet-replay")["style"]
    margin = str(payload["outer"]["margin_px"]) + "px"
    assert panel["paddingLeft"] == margin
    assert panel["paddingTop"] == margin
    assert panel["gap"] == str(payload["outer"]["spacing_px"]) + "px"


def test_a_label_the_surface_wraps_holds_more_than_one_flow(browser: Browser):
    parts = draw(browser, state_payload("loaded"))
    assert one_part(parts, "subtitle")["style"]["whiteSpace"] == "normal"
    assert one_part(parts, "status")["style"]["whiteSpace"] == "nowrap"


def test_no_label_can_be_dragged_over_the_way_a_qt_label_cannot(browser: Browser):
    parts = draw(browser, state_payload("loaded"))
    for name in ("title", "subtitle", "status", "progress"):
        assert one_part(parts, name)["style"]["userSelect"] == "none", name


def test_the_table_sizes_each_column_the_way_resize_to_contents_does(
    browser: Browser,
):
    payload = state_payload("loaded")
    parts = draw(browser, payload)
    assert one_part(parts, "fleet-table")["attrs"]["data-resize-mode"] == (
        payload["fleet_table"]["header_resize_mode"]
    )
    head = one_part(parts, "head-row")["style"]["gridTemplateColumns"]
    assert len(head.split(" ")) == payload["fleet_table"]["column_count"]


def test_the_last_column_stretches_because_the_surface_says_it_does(
    browser: Browser,
):
    payload = state_payload("loaded")
    parts = draw(browser, payload)
    assert payload["fleet_table"]["stretch_last_section"] is True
    head = one_part(parts, "head-row")
    widths = [
        float(one) for one in head["style"]["gridTemplateColumns"].split("px")[:-1]
    ]
    assert widths[-1] > widths[0], widths


def test_the_alternating_row_flag_is_published_with_no_colour_behind_it(
    browser: Browser,
):
    payload = state_payload("loaded")
    parts = draw(browser, payload)
    assert payload["fleet_table"]["alternating_row_colors"] is True
    assert one_part(parts, "fleet-table")["attrs"]["data-alternating"] == "true"
    grounds = {one["style"]["backgroundColor"] for one in by_part(parts, "body-row")}
    assert len(grounds) == 1, grounds


BUTTON_STATES = (
    ("idle", "start", True),
    ("idle", "stop", True),
    ("loaded", "start", False),
    ("running", "stop", False),
    ("running", "start", True),
)


@pytest.mark.parametrize("state,name,off", BUTTON_STATES)
def test_a_button_the_surface_disabled_is_drawn_disabled(
    browser: Browser, state: str, name: str, off: bool
):
    payload = state_payload(state)
    parts = draw(browser, payload)
    drawn = [
        one for one in by_part(parts, "button") if one["attrs"]["data-key"] == name
    ]
    assert len(drawn) == 1, (state, name)
    assert drawn[0]["disabled"] is off, (state, name, payload["buttons"][name])
    assert drawn[0]["attrs"]["data-enabled"] == json.dumps(not off)


def test_a_button_press_in_the_page_reaches_the_module_with_its_step(
    browser: Browser,
):
    payload = state_payload("loaded")
    draw(browser, payload)
    browser.js(
        'window.HOST.querySelector(\'[data-part="button"][data-key="load"]\').click();'
    )
    sent = browser.parsed("acervatorFleetReplay.sent()")
    assert [one["action"] for one in sent] == ["load_button.clicked"]
    assert sent[0]["params"]["steps"] == ["load"]


def test_the_switch_press_in_the_page_changes_what_the_next_step_carries(
    browser: Browser,
):
    payload = state_payload("loaded")
    draw(browser, payload)
    assert browser.parsed("acervatorFleetReplay.fullEvaluation()") is False
    browser.js("window.HOST.querySelector('[data-part=\"switch\"]').click();")
    assert browser.parsed("acervatorFleetReplay.fullEvaluation()") is True
    assert (
        browser.parsed(
            "window.HOST.querySelector('[data-part=\"switch\"]')"
            ".getAttribute('data-checked')"
        )
        == "true"
    )
    browser.js(
        'window.HOST.querySelector(\'[data-part="button"][data-key="start"]\').click();'
    )
    sent = browser.parsed("acervatorFleetReplay.sent()")
    assert sent[-1]["params"]["full_evaluation"] is True


def test_a_disabled_button_sends_nothing_when_it_is_pressed(browser: Browser):
    draw(browser, state_payload("idle"))
    browser.js(
        'window.HOST.querySelector(\'[data-part="button"][data-key="start"]\').click();'
    )
    assert browser.parsed("acervatorFleetReplay.sent()") == []


def test_the_panel_draws_into_the_slot_its_parent_tab_leaves(browser: Browser):
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js(
        "window.HOST.innerHTML = '';"
        "window.SLOT = document.createElement('div');"
        "window.SLOT.setAttribute('data-slot', "
        + json.dumps(sts.MOUNT_FLEET_REPLAY)
        + ");"
        "window.HOST.appendChild(window.SLOT);"
    )
    browser.js(
        "window.PAYLOAD = " + json.dumps(json.dumps(state_payload("loaded"))) + ";"
        "acervatorSetFleetReplay(JSON.parse(window.PAYLOAD));"
        "acervatorFleetReplay.renderPanel(window.SLOT);"
    )
    found = browser.parsed(
        "window.HOST.querySelector('[data-slot]')"
        ".firstChild.getAttribute('data-part')"
    )
    assert found == sts.MOUNT_FLEET_REPLAY
    assert browser.parsed("window.HOST.querySelectorAll('[data-part]').length") > 1


def test_the_panel_carries_the_accessible_name_and_the_host_kind(browser: Browser):
    payload = state_payload("loaded")
    parts = draw(browser, payload)
    panel = one_part(parts, "fleet-replay")["attrs"]
    assert panel["aria-label"] == payload["accessible_name"]
    assert panel["data-host-kind"] == payload["gate_host_kind"]


@pytest.mark.parametrize("state", ("running", "finished"))
def test_the_running_timers_are_drawn_as_the_surface_reports_them(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw(browser, payload)
    drawn = one_part(parts, "fleet-replay")["attrs"]["data-timers"]
    running = sorted(name for name, on in payload["timers_running"].items() if on)
    assert sorted(one for one in drawn.split(",") if one) == running


HOSTILE_ON_THE_PAGE = ("markup", "long_name", "newline", "number", "huge")

#: What each hostile cell draws, where the page does not spell it as Python does.
DRAWN_AS = {"huge": "1e+24"}


@pytest.mark.parametrize("kind", HOSTILE_ON_THE_PAGE)
def test_a_hostile_cell_is_drawn_as_characters_and_never_as_an_element(
    browser: Browser, kind: str
):
    payload = state_payload("loaded")
    payload["fleet_table"]["rows"][0][0] = CELL_VALUES[kind]
    parts = draw(browser, payload)
    cell = [
        one
        for one in by_part(parts, "body-cell")
        if one["attrs"]["data-column"] == "Symbol"
    ][0]
    assert cell["children"] == 0, kind
    wanted = DRAWN_AS.get(kind, str(CELL_VALUES[kind]))
    assert cell["text"] == wanted, (kind, cell["text"])


def test_a_two_hundred_character_symbol_is_drawn_whole_and_cut_on_the_right(
    browser: Browser,
):
    payload = state_payload("loaded")
    payload["fleet_table"]["rows"][0][0] = CELL_VALUES["long_name"]
    parts = draw(browser, payload)
    cell = [
        one
        for one in by_part(parts, "body-cell")
        if one["attrs"]["data-column"] == "Symbol"
    ][0]
    assert cell["text"] == CELL_VALUES["long_name"]
    assert cell["style"]["overflow"] == "hidden"


def test_a_label_carrying_a_tag_is_drawn_as_characters(browser: Browser):
    payload = state_payload("loaded")
    payload["status"]["text"] = MARK
    parts = draw(browser, payload)
    status = one_part(parts, "status")
    assert status["children"] == 0
    assert status["text"] == MARK
    assert browser.parsed("window.HOST.querySelectorAll('img').length") == 0


def test_the_shipped_panel_writes_no_drawing_programme_of_its_own(qapp):
    assert qapp is not None
    from PySide6.QtWidgets import QWidget

    from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

    assert FleetReplayPanel.paintEvent is QWidget.paintEvent


def test_the_paint_check_names_a_widget_on_this_tab_that_does_paint(qapp):
    """The panel paints nothing, so the check above needs a widget that does."""
    assert qapp is not None
    from PySide6.QtWidgets import QWidget

    from src.gui.simulator_tab.fleet.sim_visuals import GateLightsCell

    assert GateLightsCell.paintEvent is not QWidget.paintEvent


NESTED_LAYOUTS = ("header_inner", "load_row", "group_inner", "run_row")


def panel_layouts(qapp) -> dict:
    """Every layout the shipped panel builds, with its margins and spacing."""
    assert qapp is not None
    from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

    panel = FleetReplayPanel()
    outer = panel.layout()

    def numbers(layout: Any) -> list:
        edges = layout.contentsMargins()
        return [
            edges.left(),
            edges.top(),
            edges.right(),
            edges.bottom(),
            layout.spacing(),
        ]

    return {
        "outer": numbers(outer),
        "header_inner": numbers(outer.itemAt(0).widget().layout()),
        "load_row": numbers(outer.itemAt(1).layout()),
        "group_inner": numbers(outer.itemAt(2).widget().layout()),
        "run_row": numbers(outer.itemAt(4).layout()),
    }


def test_the_surface_publishes_the_outer_layout_the_shipped_panel_builds(qapp):
    found = panel_layouts(qapp)["outer"]
    assert found == [frp.OUTER_MARGIN_PX] * 4 + [frp.OUTER_SPACING_PX]


@pytest.mark.parametrize("name", NESTED_LAYOUTS)
def test_no_nested_layout_number_reaches_the_payload(qapp, name: str):
    """Each nested layout takes a Qt default the surface never publishes."""
    found = panel_layouts(qapp)[name]
    payload = state_payload("loaded")
    numbers = set(payload["numbers"].values()) | set(payload["outer"].values())
    assert found[0] not in numbers or found[0] == 0, (name, found)


def test_the_nested_layouts_take_numbers_this_host_can_be_read_for(qapp):
    """The gap above is real, so the measured numbers are recorded here."""
    found = panel_layouts(qapp)
    assert found["header_inner"][:4] == found["group_inner"][:4]
    assert found["load_row"][:4] == [0, 0, 0, 0]
    assert found["run_row"] == found["load_row"]
