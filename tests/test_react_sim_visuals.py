"""Drives sim_visuals.js from every state_payload the surface builds."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import sim_visuals_surface as svs
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import HEX_COLOUR, JsEngine, js_literals, new_engine

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "sim_visuals.js"
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

SWAP_ATTEMPTS = 100
SWAP_PAUSE_S = 0.01


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

HOST_WIDTH_PX = 1200
HOST_HEIGHT_PX = 900
VIEW_SIZE_PX = (1200, 900)

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

SYMBOLS = ("BTC-USD", "ETH-USD", "SOL-USD")
BAR_COUNT = 12
FIRST_STAMP_MS = 1_700_000_000_000
STAMP_STEP_MS = 60_000


class Summary:
    """A voting summary shaped as the readout reads one."""

    def __init__(self, net, confidence, bullish, bearish) -> None:
        self.net_score = net
        self.consensus_confidence = confidence
        self.bullish_count = bullish
        self.bearish_count = bearish


def fed_chart(focus: str) -> svs.PriceVwapModel:
    """A chart carrying bars for every symbol, focused where asked."""
    chart = svs.PriceVwapModel()
    chart.set_symbols(list(SYMBOLS))
    for index in range(BAR_COUNT):
        for at, symbol in enumerate(SYMBOLS):
            base = 100.0 + at * 10.0 + index * 0.5
            chart.append_tick(
                symbol,
                base + 1.0,
                2.0 + index,
                FIRST_STAMP_MS + index * STAMP_STEP_MS,
                base,
                base + 2.0,
                base - 2.0,
            )
    chart.set_ytd_start(SYMBOLS[0], FIRST_STAMP_MS + 4 * STAMP_STEP_MS)
    chart.mark_trade(SYMBOLS[0], True)
    chart.mark_trade(SYMBOLS[1], False)
    chart.set_focus_symbol(focus)
    return chart


def read_pane(symbols=SYMBOLS, readings=None) -> svs.GatePanelModel:
    """A pane holding one row per symbol, each row given its reading."""
    pane = svs.GatePanelModel()
    pane.set_symbols(list(symbols))
    for symbol, reading in (readings or {}).items():
        row = pane.cell_for(symbol)
        if row is not None:
            row.update_gates(*reading)
    return pane


def written_votes(summaries=None) -> svs.VotingReadoutModel:
    """A readout with one row per symbol, written where a summary is given."""
    votes = svs.VotingReadoutModel()
    votes.set_bots(list(SYMBOLS))
    for symbol, summary in (summaries or {}).items():
        votes.update_bot_row(symbol, summary)
    return votes


ARMED = (True, False, ["TA-not-bullish", "CB-hard"], ["BB-above-lower"], "upper")
FOLDING = (False, True, ["delta<=0"], ["no-tranches-queued"], "lower")


def state_payload(name: str) -> dict:
    """The view model for one named state of the screen."""
    if name == "empty":
        return svs.build_view_model(width_px=HOST_WIDTH_PX, height_px=HOST_HEIGHT_PX)
    if name == "loaded":
        return svs.build_view_model(
            panel=read_pane(),
            chart=fed_chart(""),
            votes=written_votes(),
            width_px=HOST_WIDTH_PX,
            height_px=HOST_HEIGHT_PX,
        )
    if name == "scrum_armed":
        return svs.build_view_model(
            panel=read_pane(readings={one: ARMED for one in SYMBOLS}),
            chart=fed_chart(""),
            votes=written_votes(),
            width_px=HOST_WIDTH_PX,
            height_px=HOST_HEIGHT_PX,
        )
    if name == "fold_armed":
        return svs.build_view_model(
            panel=read_pane(readings={one: FOLDING for one in SYMBOLS}),
            chart=fed_chart(""),
            votes=written_votes(),
            width_px=HOST_WIDTH_PX,
            height_px=HOST_HEIGHT_PX,
        )
    if name == "focused":
        return svs.build_view_model(
            panel=read_pane(readings={SYMBOLS[0]: ARMED}),
            chart=fed_chart(SYMBOLS[0]),
            votes=written_votes(),
            width_px=HOST_WIDTH_PX,
            height_px=HOST_HEIGHT_PX,
        )
    if name == "voted":
        return svs.build_view_model(
            panel=read_pane(readings={one: ARMED for one in SYMBOLS}),
            chart=fed_chart(SYMBOLS[0]),
            votes=written_votes(
                {
                    SYMBOLS[0]: Summary(0.7, 0.9, 5, 1),
                    SYMBOLS[1]: Summary(-0.7, 0.8, 1, 5),
                    SYMBOLS[2]: Summary(0.0, 0.1, 2, 2),
                }
            ),
            width_px=HOST_WIDTH_PX,
            height_px=HOST_HEIGHT_PX,
        )
    if name == "expanded":
        expand = svs.ExpandModel()
        expand.open(SYMBOLS[0])
        return svs.build_view_model(
            panel=read_pane(readings={one: ARMED for one in SYMBOLS}),
            chart=fed_chart(SYMBOLS[0]),
            votes=written_votes({SYMBOLS[0]: Summary(0.7, 0.9, 5, 1)}),
            expand=expand,
            width_px=HOST_WIDTH_PX,
            height_px=HOST_HEIGHT_PX,
        )
    if name == "cleared":
        pane = read_pane(readings={one: ARMED for one in SYMBOLS})
        for symbol in SYMBOLS:
            pane.cell_for(symbol).clear_gates()
        chart = fed_chart(SYMBOLS[0])
        chart.clear_data()
        return svs.build_view_model(
            panel=pane,
            chart=chart,
            votes=written_votes(),
            width_px=HOST_WIDTH_PX,
            height_px=HOST_HEIGHT_PX,
        )
    raise AssertionError("no state named " + name)


STATE_NAMES = (
    "empty",
    "loaded",
    "scrum_armed",
    "fold_armed",
    "focused",
    "voted",
    "expanded",
    "cleared",
)


def token_payload() -> dict:
    """The design token payload the page applies before it draws."""
    return dss.build_view_model()


def theme_payload() -> dict:
    """The theme payload the page applies before it draws."""
    return tes.build_view_model()


class JsRuntime(JsEngine):
    """A QJSEngine holding sim_visuals.js and the modules it reads."""

    module_path = MODULE_PATH
    setter = "acervatorSetSimVisuals"

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
        return self.json("acervatorSimVisuals." + expression)


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


def python_kinds(payload: dict) -> dict:
    """The JavaScript type of every value of `payload`, by dotted path."""
    found: dict = {}

    def descend(path: str, value: Any) -> None:
        if isinstance(value, dict):
            walk(path, value)
            return
        if isinstance(value, (list, tuple)):
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
def test_every_top_level_field_reaches_the_module(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for name in js.answer("declaredFields()"):
        assert name in payload, f"{state} carries no {name}"
    assert sorted(js.answer("declaredFields()")) == sorted(payload)


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_five_panels_answer_by_value(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.answer("pane()") == payload["gate_panel"]
    assert js.answer("chrome()") == payload["gate_row"]
    assert js.answer("chart()") == payload["chart"]
    assert js.answer("votes()") == payload["votes"]
    assert js.answer("expand()") == payload["expand"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_loose_fields_answer_by_value(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.answer("methodName()") == payload["method"] == svs.METHOD
    assert js.answer("actions()") == payload["actions"]
    assert js.answer("timers()") == payload["timers"]
    assert js.answer("timerDelays()") == payload["timer_delays_ms"]
    assert js.answer("busTopics()") == payload["bus_topics"]
    assert js.answer("busEmits()") == payload["bus_emits"]
    assert js.answer("signals()") == payload["signals"]
    assert js.answer("callNames()") == payload["call_names"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_payload_carries_no_fault(js: JsRuntime, state: str):
    found = js.push(state_payload(state))
    assert found["faults"] == [], f"{state}: {found['faults']}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_counts_agree_with_what_the_surface_declares(js: JsRuntime, state: str):
    payload = state_payload(state)
    found = js.push(payload)
    assert found["declared"] == found["held"], f"{state}: {found}"
    assert found["held"]["fields"] == len(payload)
    assert found["held"]["columns"] == len(payload["votes"]["columns"])
    assert found["held"]["votes"] == len(payload["votes"]["rows"])
    assert found["held"]["ops"] == len(payload["chart"]["program"])


def test_a_missing_panel_is_named_and_the_counts_fall(js: JsRuntime):
    payload = state_payload("loaded")
    del payload["votes"]
    found = js.push(payload)
    named = [one for one in found["faults"] if one["field"] == "votes"]
    assert named, found["faults"]
    assert found["held"]["fields"] < found["declared"]["fields"]


def test_a_dropped_row_lowers_the_held_count_and_not_the_declared(js: JsRuntime):
    payload = state_payload("loaded")
    payload["gate_panel"]["items"] = [
        one for one in payload["gate_panel"]["items"] if one["kind"] != "row"
    ]
    found = js.push(payload)
    assert found["declared"]["rows"] == len(SYMBOLS)
    assert found["held"]["rows"] == 0
    assert found["declared"] != found["held"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_both_sides_read_every_value_as_the_same_type(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    wanted = python_kinds(payload)
    found = js.answer("kinds()")
    assert found == wanted, {
        path: (wanted.get(path), found.get(path))
        for path in set(wanted) ^ set(found)
        | {one for one in wanted if found.get(one) != wanted[one]}
    }


def test_the_type_reader_reports_a_type_that_changed(js: JsRuntime):
    """The type comparison passed because it compares nothing."""
    payload = state_payload("loaded")
    payload["gate_row"]["font_pt"] = str(payload["gate_row"]["font_pt"])
    js.push(payload)
    assert js.answer("kinds()")["gate_row.font_pt"] == "string"
    assert python_kinds(state_payload("loaded"))["gate_row.font_pt"] == "number"


def test_a_payload_that_is_not_an_object_is_refused(js: JsRuntime):
    js.bind_json("PAYLOAD", ["not", "a", "screen"])
    found = js.json("acervatorSetSimVisuals(JSON.parse(PAYLOAD))")
    assert found["declared"] is None
    assert found["faults"][0]["fault"] == "not-an-object"
    assert js.answer("isLoaded()") is False


def test_the_module_forgets_what_it_held(js: JsRuntime):
    js.push(state_payload("loaded"))
    assert js.answer("isLoaded()") is True
    js.run("acervatorSimVisuals.forget()")
    assert js.answer("isLoaded()") is False
    assert js.answer("pane()") == {}
    assert js.answer("rowOrder()") == []


def test_the_module_asks_the_bridge_by_the_method_the_surface_names(js: JsRuntime):
    assert js.answer("method") == svs.METHOD
    assert js.json("typeof acervatorLoadSimVisuals") == "function"
    assert js.json("acervatorLoadSimVisuals({}) === null") is False
    assert js.answer("loadError()") == "the preload bridge is not present"


def payload_strings(payload: Any, found: set) -> set:
    """Every string the payload carries, at every depth."""
    if isinstance(payload, dict):
        for name, value in payload.items():
            found.add(name)
            payload_strings(value, found)
    elif isinstance(payload, (list, tuple)):
        for one in payload:
            payload_strings(one, found)
    elif isinstance(payload, str):
        found.add(payload)
    return found


def payload_values(payload: Any, found: set) -> set:
    """Every string the payload carries as a value rather than as a key."""
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
    """Every key name the payload carries, at every depth."""
    if isinstance(payload, dict):
        for name, value in payload.items():
            found.add(name)
            payload_keys(value, found)
    elif isinstance(payload, (list, tuple)):
        for one in payload:
            payload_keys(one, found)
    return found


SAMPLE = state_payload("voted")

PUBLISHED_VALUES = payload_values(SAMPLE, set()) | payload_values(
    state_payload("focused"), set()
)
PUBLISHED_KEYS = payload_keys(SAMPLE, set())

#: A naming value tells the module what a field means; it paints nothing.
NAMING_VALUES = {
    svs.METHOD,
    "",
    svs.ALIGN_LABEL,
    svs.ALIGN_MARKER,
    svs.TEXT,
    svs.ELLIPSE,
    svs.NO_PEN,
    "empty",
    "row",
    "stretch",
    svs.VOTE_COLUMN_MODE,
    svs.VOTE_SYMBOL_COLUMN_MODE,
    svs.VOTE_EDIT_TRIGGERS,
    svs.VOTE_SELECTION_BEHAVIOUR,
    svs.CHART_SIZE_POLICY[0],
}

PAINTED_VALUES = PUBLISHED_VALUES - NAMING_VALUES - PUBLISHED_KEYS

TOKEN_VALUES = {
    str(one)
    for one in token_payload()["tokens"].values()
    if one is not None and str(one)
}


def test_the_module_writes_no_value_the_surface_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"sim_visuals.js writes the painted values {written}"


def test_the_painted_set_still_holds_the_captions_and_colours_the_screen_shows():
    """The painted set is empty, so the check above measures nothing."""
    for shown in (
        SAMPLE["gate_panel"]["empty_text"],
        SAMPLE["votes"]["columns"][0],
        SAMPLE["votes"]["placeholder"],
        SAMPLE["gate_row"]["label_colour"],
        SAMPLE["gate_row"]["light_colours"]["blocked"],
        SAMPLE["votes"]["alternate_row_colour"],
        SAMPLE["chart"]["accessible_name"],
    ):
        assert shown in PAINTED_VALUES, shown


def test_the_module_writes_no_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"sim_visuals.js writes the token values {written}"


def test_the_module_writes_no_number_and_no_colour():
    assert MODULE_LITERALS["numbers"] == [], MODULE_LITERALS["numbers"]
    assert HEX_COLOUR.findall(MODULE_SOURCE) == []


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], MODULE_LITERALS["slashes"]


def test_the_module_names_only_the_surface_keys_it_reads(js: JsRuntime):
    js.push(SAMPLE)
    allowed = set(js.answer("declaredNames()"))
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_KEYS
    assert not written - allowed, sorted(written - allowed)


SPELLED_OUT_LINES = {
    "colour": 'var spelled = "' + svs.GATE_LABEL_COLOUR + '";',
    "token_value": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "caption": 'var spelled = "' + svs.PANEL_EMPTY_TEXT + '";',
    "column": 'var spelled = "' + svs.VOTE_COLUMNS[0] + '";',
    "placeholder": 'var spelled = "' + svs.VOTE_PLACEHOLDER + '";',
    "led_size": "var spelled = " + str(svs.GATE_LED_PX) + ";",
    "row_height": "var spelled = " + str(svs.VOTE_ROW_HEIGHT_PX) + ";",
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
    assert caught_by_scan(SPELLED_OUT_LINES[kind]), kind


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals("// " + svs.GATE_LABEL_COLOUR + '\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


#: The file the swap below moves over the module, named for this unit.
SPARE_PATH = MODULE_PATH.with_name("sim_visuals.visual_swap.js")


def swap_module(content: bytes) -> None:
    """Replace MODULE_PATH with `content`, retrying a refused os.replace."""
    SPARE_PATH.write_bytes(content)
    for attempt in range(SWAP_ATTEMPTS):
        try:
            os.replace(SPARE_PATH, MODULE_PATH)
            return
        except PermissionError:
            if attempt + 1 == SWAP_ATTEMPTS:
                raise
            time.sleep(SWAP_PAUSE_S)


def test_each_spelled_out_value_is_caught_in_the_module_file_itself():
    original = read_module().encode("utf-8")
    before = hashlib.sha256(original).hexdigest()
    caught_each = {}
    hashes = {}
    try:
        for kind in sorted(SPELLED_OUT_LINES):
            swap_module(original + SPELLED_OUT_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(original)
            hashes[kind] = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
    finally:
        try:
            swap_module(original)
        finally:
            SPARE_PATH.unlink(missing_ok=True)
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
        assert runtime.json("typeof acervatorSetSimVisuals") == "function", kind


def declared_pairs() -> list:
    """Every bank and label pair, in the order the surface draws them."""
    return [[bank, label] for bank in svs.GATE_BANKS for label in svs.GATE_ORDER[bank]]


def test_a_label_alone_is_not_an_identity_and_the_pair_is():
    pairs = declared_pairs()
    labels = [label for _, label in pairs]
    assert len(pairs) == svs.GATE_COUNT == 19
    assert len(set(tuple(one) for one in pairs)) == svs.GATE_COUNT
    assert len(set(labels)) < svs.GATE_COUNT
    twice = sorted({one for one in labels if labels.count(one) > 1})
    assert twice == ["BB", "CB", "HTF", "LS", "OTD", "TA"], twice


@pytest.mark.parametrize("state", ("loaded", "scrum_armed", "fold_armed", "cleared"))
def test_every_row_carries_the_nineteen_lights_in_the_declared_order(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    for symbol in js.answer("rowOrder()"):
        lamps = js.json(f"acervatorSimVisuals.lampsFor({json.dumps(symbol)})")
        assert [[one["bank"], one["label"]] for one in lamps] == declared_pairs()


def test_the_order_check_names_a_row_whose_lights_were_reordered(js: JsRuntime):
    payload = state_payload("scrum_armed")
    lights = payload["gate_row"]["rows"][SYMBOLS[0]]["lights"]
    lights[0], lights[-1] = lights[-1], lights[0]
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "lamp-order"]
    assert len(named) == 2, found["faults"]
    assert named[0]["where"].startswith("gate_row." + SYMBOLS[0])


def test_the_order_check_also_names_the_label_the_program_expected(js: JsRuntime):
    payload = state_payload("scrum_armed")
    lights = payload["gate_row"]["rows"][SYMBOLS[0]]["lights"]
    lights[0], lights[-1] = lights[-1], lights[0]
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "lamp-label"]
    assert named, found["faults"]


def test_a_swapped_pair_of_light_states_is_named(js: JsRuntime):
    payload = state_payload("scrum_armed")
    lights = payload["gate_row"]["rows"][SYMBOLS[0]]["lights"]
    first = next(at for at, one in enumerate(lights) if one["state"] == "blocked")
    second = next(at for at, one in enumerate(lights) if one["state"] == "passed")
    lights[first]["state"], lights[second]["state"] = (
        lights[second]["state"],
        lights[first]["state"],
    )
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "lamp-colour"]
    assert len(named) == 2, found["faults"]
    assert {one["where"].rsplit(".", 1)[-1] for one in named} == {
        str(first),
        str(second),
    }


def test_the_state_check_holds_a_colour_the_surface_never_paints(js: JsRuntime):
    payload = state_payload("scrum_armed")
    payload["gate_row"]["rows"][SYMBOLS[0]]["lights"][0]["state"] = "invented"
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "unknown-kind"]
    assert named, found["faults"]


def test_the_light_colours_bag_names_one_colour_for_each_state(js: JsRuntime):
    payload = state_payload("scrum_armed")
    js.push(payload)
    byState = js.answer("chrome()")["light_colours"]
    assert byState == payload["gate_row"]["light_colours"]
    assert len(set(byState.values())) == len(byState)
    for symbol in SYMBOLS:
        for one in payload["gate_row"]["rows"][symbol]["lights"]:
            assert byState[one["state"]] == one["colour"]


def test_a_landing_strip_lights_its_own_bank_and_no_other(js: JsRuntime):
    js.push(state_payload("scrum_armed"))
    lamps = js.json(f"acervatorSimVisuals.lampsFor({json.dumps(SYMBOLS[0])})")
    overrides = [one for one in lamps if one["state"] == "override"]
    assert [one["bank"] for one in overrides] == [svs.GATE_SCRUM_BANK]
    assert overrides[0]["label"] == "LS"


def test_the_row_order_comes_from_the_list_and_not_from_the_bag(js: JsRuntime):
    """A bag keyed by a number loses its order, so the list carries it."""
    numeric = ("30", "4", "100")
    payload = svs.build_view_model(
        panel=read_pane(symbols=numeric),
        chart=svs.PriceVwapModel(),
        votes=svs.VotingReadoutModel(),
    )
    js.push(payload)
    assert js.answer("rowOrder()") == list(numeric)
    assert js.json("Object.keys(acervatorSimVisuals.chrome().rows)") != list(numeric)


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
            if self.js("typeof window.acervatorSetSimVisuals") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the module: readyState "
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


STYLE_NAMES = [
    "color",
    "backgroundColor",
    "fontSize",
    "fontFamily",
    "fontWeight",
    "whiteSpace",
    "overflow",
    "textOverflow",
    "userSelect",
    "display",
    "flexDirection",
    "gap",
    "minWidth",
    "minHeight",
    "width",
    "height",
    "position",
    "left",
    "top",
    "borderRadius",
    "justifyContent",
    "alignItems",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
]

EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "background": ("backgroundColor",),
    "background-color": ("backgroundColor",),
    "font-size": ("fontSize",),
    "font-family": ("fontFamily",),
    "color": ("color",),
}

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

PAGE_HELPERS = (
    "window.HOST = document.getElementById('sim-visuals-host');"
    "if (!window.HOST) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'sim-visuals-host';"
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
    "        hidden: el.hidden === true, text: own,"
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


def give_tokens(browser: Browser) -> int:
    """Push the tokens into the page and apply them to the document."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_screen(browser: Browser, payload: dict) -> list:
    """Render `payload` into window.HOST and return what READ_PARTS finds."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetSimVisuals(JSON.parse(window.PAYLOAD));"
        "acervatorSimVisuals.renderVisuals(window.HOST);"
    )
    return read_parts(browser)


def read_parts(browser: Browser) -> list:
    """What READ_PARTS finds, without rendering again."""
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


def probe(browser: Browser, tag: str, body: str) -> dict:
    """The computed values a bare `tag` takes from `body`."""
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


def css_body(sheet: Any) -> str:
    return ";".join(prop + ":" + value for prop, value in declarations_of(sheet))


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
    assert browser.js("typeof window.acervatorSimVisuals") == "object"
    assert browser.js("typeof window.acervatorSetSimVisuals") == "function"
    assert browser.js("typeof window.acervatorLoadSimVisuals") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_screen(browser, state_payload("voted"))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


COUNT_ELEMENTS = (
    "[window.HOST.querySelectorAll('*').length,"
    " window.HOST.querySelectorAll('[data-part]').length]"
)


def test_a_symbol_carrying_markup_is_drawn_as_text(browser: Browser):
    payload = svs.build_view_model(
        panel=read_pane(symbols=("<img src='http://example.invalid/a.png'>",)),
        chart=svs.PriceVwapModel(),
        votes=svs.VotingReadoutModel(),
    )
    browser.js(WATCH_VIOLATIONS)
    parts = draw_screen(browser, payload)
    label = one_part(parts, "pane-label")
    assert label["text"] == payload["gate_panel"]["items"][1]["symbol"]
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []
    assert browser.js("document.images.length") == 0


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_drawn_parts_carry_the_names_the_checks_read(browser: Browser, state: str):
    parts = draw_screen(browser, state_payload(state))
    named = {one["attrs"]["data-part"] for one in parts}
    assert {"visuals", "pane", "pane-scroll", "pane-host", "pane-empty"} <= named
    assert {"chart-mount", "vote-table", "vote-grid", "vote-head", "vote-body"} <= named
    assert "expand" in named
    every, carrying = browser.parsed(COUNT_ELEMENTS)
    assert every == carrying, f"{every - carrying} drawn elements carry no name"


def test_the_naming_check_reports_an_element_left_without_a_name(browser: Browser):
    """Every element was named because the count reads one list twice."""
    draw_screen(browser, state_payload("voted"))
    before = browser.parsed(COUNT_ELEMENTS)
    browser.js("window.HOST.appendChild(document.createElement('span'));")
    every, carrying = browser.parsed(COUNT_ELEMENTS)
    assert before[0] == before[1]
    assert every == carrying + 1


def test_one_row_is_drawn_for_each_symbol_the_pane_holds(browser: Browser):
    payload = state_payload("scrum_armed")
    parts = draw_screen(browser, payload)
    rows = by_part(parts, "pane-row")
    assert [one["attrs"]["data-symbol"] for one in rows] == list(SYMBOLS)
    for row in by_part(parts, "lamp-row"):
        assert row["attrs"]["data-lamps"] == str(svs.GATE_COUNT)


def test_every_light_carries_its_bank_label_and_state(browser: Browser):
    payload = state_payload("scrum_armed")
    parts = draw_screen(browser, payload)
    lamps = [
        one for one in by_part(parts, "lamp") if one["attrs"]["data-bank"] is not None
    ]
    assert len(lamps) == svs.GATE_COUNT * len(SYMBOLS)
    wanted = payload["gate_row"]["rows"][SYMBOLS[0]]["lights"]
    first = lamps[: svs.GATE_COUNT]
    assert [one["attrs"]["data-bank"] for one in first] == [
        one["bank"] for one in wanted
    ]
    assert [one["attrs"]["data-label"] for one in first] == [
        one["label"] for one in wanted
    ]
    assert [one["attrs"]["data-state"] for one in first] == [
        one["state"] for one in wanted
    ]


def as_rgb(value: str) -> str:
    """One `#rrggbb` as the `rgb()` the document reads back."""
    body = value.lstrip("#")
    if len(body) == 3:
        body = "".join(one * 2 for one in body)
    return "rgb({}, {}, {})".format(
        int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)
    )


def test_each_light_paints_the_colour_its_state_names(browser: Browser):
    payload = state_payload("scrum_armed")
    parts = draw_screen(browser, payload)
    byState = payload["gate_row"]["light_colours"]
    seen = set()
    for lamp in by_part(parts, "lamp"):
        state = lamp["attrs"]["data-state"]
        assert lamp["style"]["backgroundColor"] == as_rgb(byState[state]), lamp
        seen.add(state)
    assert len(seen) > 1, seen


def test_the_light_colour_check_would_see_a_repainted_light(browser: Browser):
    """Every light matched because they all paint the same colour."""
    payload = state_payload("scrum_armed")
    program = payload["gate_row"]["rows"][SYMBOLS[0]]["program"]
    repainted = next(one for one in program if one["op"] == svs.ELLIPSE)
    repainted["brush"] = svs.GATE_LABEL_COLOUR
    byState = payload["gate_row"]["light_colours"]
    assert svs.GATE_LABEL_COLOUR not in byState.values()
    parts = draw_screen(browser, payload)
    first = by_part(parts, "lamp")[0]
    assert first["style"]["backgroundColor"] == as_rgb(svs.GATE_LABEL_COLOUR)
    assert first["style"]["backgroundColor"] != as_rgb(
        byState[first["attrs"]["data-state"]]
    )


def test_the_pane_label_takes_the_style_the_surface_declares(browser: Browser):
    payload = state_payload("loaded")
    parts = draw_screen(browser, payload)
    label = by_part(parts, "pane-label")[0]
    wanted = probe(browser, "span", css_body(payload["gate_panel"]["label_style"]))
    assert wanted, "the probe read nothing from the label sheet"
    for name, value in wanted.items():
        assert label["style"][name] == value, name


def test_the_empty_caption_takes_the_style_the_surface_declares(browser: Browser):
    payload = state_payload("empty")
    parts = draw_screen(browser, payload)
    empty = one_part(parts, "pane-empty")
    assert empty["hidden"] is False
    assert empty["text"] == payload["gate_panel"]["empty_text"]
    wanted = probe(browser, "div", css_body(payload["gate_panel"]["empty_style"]))
    assert wanted
    for name, value in wanted.items():
        assert empty["style"][name] == value, name


def test_a_loaded_pane_hides_the_empty_caption(browser: Browser):
    parts = draw_screen(browser, state_payload("loaded"))
    assert one_part(parts, "pane-empty")["hidden"] is True


def test_the_vote_frame_takes_the_style_the_surface_declares(browser: Browser):
    payload = state_payload("voted")
    parts = draw_screen(browser, payload)
    frame = one_part(parts, "vote-table")
    wanted = probe(browser, "div", css_body(payload["votes"]["style_sheet"]))
    assert wanted
    for name, value in wanted.items():
        assert frame["style"][name] == value, name


def test_the_head_cells_take_the_state_rule_of_the_same_sheet(browser: Browser):
    payload = state_payload("voted")
    parts = draw_screen(browser, payload)
    heads = by_part(parts, "vote-head-cell")
    assert [one["text"] for one in heads] == list(payload["votes"]["columns"])
    body = payload["votes"]["style_sheet"].split("QHeaderView::section", 1)[1]
    wanted = probe(browser, "th", css_body(body))
    assert wanted
    for name, value in wanted.items():
        assert heads[0]["style"][name] == value, name


def test_the_rows_alternate_with_the_colour_the_surface_publishes(browser: Browser):
    payload = state_payload("voted")
    parts = draw_screen(browser, payload)
    rows = by_part(parts, "vote-row")
    assert len(rows) == len(SYMBOLS)
    alternate = as_rgb(payload["votes"]["alternate_row_colour"])
    assert rows[1]["style"]["backgroundColor"] == alternate
    assert rows[0]["style"]["backgroundColor"] != alternate


def test_the_alternate_row_check_sees_a_table_told_not_to_alternate(browser: Browser):
    """Both rows matched because the drawing ignores the flag."""
    payload = state_payload("voted")
    payload["votes"]["alternating_rows"] = False
    parts = draw_screen(browser, payload)
    alternate = as_rgb(payload["votes"]["alternate_row_colour"])
    for row in by_part(parts, "vote-row"):
        assert row["style"]["backgroundColor"] != alternate


def test_the_direction_cell_paints_the_colour_its_row_carries(browser: Browser):
    payload = state_payload("voted")
    parts = draw_screen(browser, payload)
    last = payload["votes"]["columns"][-1]
    painted = [
        one
        for one in by_part(parts, "vote-cell")
        if one["attrs"]["data-column"] == last
    ]
    assert len(painted) == len(SYMBOLS)
    for at, cell in enumerate(painted):
        assert cell["style"]["color"] == as_rgb(
            payload["votes"]["rows"][at]["direction_colour"]
        )


def test_the_neutral_direction_is_told_apart_by_its_text(browser: Browser):
    """A neutral cell has three equal channels, so a swap is invisible."""
    payload = state_payload("voted")
    parts = draw_screen(browser, payload)
    last = payload["votes"]["columns"][-1]
    texts = [
        one["text"]
        for one in by_part(parts, "vote-cell")
        if one["attrs"]["data-column"] == last
    ]
    assert texts == [svs.VOTE_BULL, svs.VOTE_BEAR, svs.VOTE_NEUTRAL]
    assert len(set(as_rgb(svs.VOTE_NEUTRAL_COLOUR).split())) < 4


def test_a_swapped_bull_and_bear_colour_is_seen(browser: Browser):
    """The channels are equal, so the swap could not be seen."""
    payload = state_payload("voted")
    rows = payload["votes"]["rows"]
    rows[0]["direction_colour"], rows[1]["direction_colour"] = (
        rows[1]["direction_colour"],
        rows[0]["direction_colour"],
    )
    parts = draw_screen(browser, payload)
    last = payload["votes"]["columns"][-1]
    painted = [
        one
        for one in by_part(parts, "vote-cell")
        if one["attrs"]["data-column"] == last
    ]
    assert painted[0]["style"]["color"] == as_rgb(svs.VOTE_BEAR_COLOUR)
    assert painted[1]["style"]["color"] == as_rgb(svs.VOTE_BULL_COLOUR)


def test_every_cell_is_cut_on_the_right_the_way_a_qt_cell_is(browser: Browser):
    parts = draw_screen(browser, state_payload("voted"))
    for cell in by_part(parts, "vote-cell") + by_part(parts, "pane-label"):
        assert cell["style"]["whiteSpace"] == "nowrap", cell
        assert cell["style"]["textOverflow"] == "ellipsis", cell
        assert cell["style"]["overflow"] == "hidden", cell


def test_a_label_cannot_be_dragged_over_the_way_a_qt_label_cannot(browser: Browser):
    parts = draw_screen(browser, state_payload("loaded"))
    assert by_part(parts, "pane-label")[0]["style"]["userSelect"] == "none"


def test_the_chart_is_left_as_a_named_host_for_its_own_unit(browser: Browser):
    payload = state_payload("focused")
    parts = draw_screen(browser, payload)
    mount = one_part(parts, "chart-mount")
    assert mount["attrs"]["data-slot"] == "sim-price-chart"
    assert mount["attrs"]["aria-label"] == payload["chart"]["accessible_name"]
    assert mount["attrs"]["data-focus"] == payload["chart"]["focus"]
    assert mount["attrs"]["data-ops"] == str(len(payload["chart"]["program"]))
    assert (
        mount["style"]["minHeight"] == str(payload["chart"]["minimum_height_px"]) + "px"
    )
    wanted = probe(browser, "div", css_body(payload["chart"]["style_sheet"]))
    for name, value in wanted.items():
        assert mount["style"][name] == value, name


def test_the_expand_frame_is_hidden_until_the_dialog_claims_a_widget(browser: Browser):
    closed = draw_screen(browser, state_payload("focused"))
    assert one_part(closed, "expand")["hidden"] is True
    opened = draw_screen(browser, state_payload("expanded"))
    frame = one_part(opened, "expand")
    assert frame["hidden"] is False
    assert frame["attrs"]["data-claim"] == svs.EXPAND_CLAIM_FIELD


def test_the_table_takes_focus_the_way_a_qt_table_does(browser: Browser):
    draw_screen(browser, state_payload("voted"))
    assert (
        browser.js("document.querySelector('[data-part=\"vote-table\"]').tabIndex") == 0
    )


def sheet_background() -> str:
    """The colour the vote sheet paints behind the table."""
    for prop, value in declarations_of(svs.VOTE_STYLE):
        if prop == "background":
            return value
    raise AssertionError("the vote sheet paints no background")


def sole_name_for(value: str) -> str:
    """The one CSS variable carrying `value`, an alias left out."""
    model = token_payload()
    carried = [
        name
        for name, held in model["tokens"].items()
        if model["alias_targets"].get(name) is None and str(held) == value
    ]
    assert len(carried) == 1, f"{len(carried)} names carry {value}: {carried}"
    return "--" + carried[0]


REWRITTEN = "#123456"


def test_the_sheet_background_is_the_one_value_a_variable_reaches(browser: Browser):
    payload = state_payload("voted")
    draw_screen(browser, payload)
    assert sheet_background() in payload["votes"]["style_sheet"]
    written = browser.parsed(
        "acervatorSimVisuals.styleOf(acervatorSimVisuals.votes().style_sheet)"
    )
    assert sole_name_for(sheet_background()) in written["background"], written


#: Every part whose own sheet paints the background the name below carries.
SHEET_BACKED_PARTS = {"pane-scroll", "chart-mount", "vote-table", "expand"}


def test_rewriting_that_name_moves_the_sheets_and_leaves_the_lights(browser: Browser):
    payload = state_payload("voted")
    before = draw_screen(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty("
        + json.dumps(sole_name_for(sheet_background()))
        + ", "
        + json.dumps(REWRITTEN)
        + ");"
    )
    after = read_parts(browser)
    moved = {
        one["attrs"]["data-part"]
        for one, was in zip(after, before)
        if one["style"]["backgroundColor"] != was["style"]["backgroundColor"]
    }
    assert moved == SHEET_BACKED_PARTS, moved
    assert one_part(after, "vote-table")["style"]["backgroundColor"] == as_rgb(
        REWRITTEN
    )


def test_every_part_that_moved_names_the_colour_in_its_own_sheet():
    """A part moved without its sheet naming the colour."""
    painted = sheet_background()
    for sheet in (
        svs.PANEL_SCROLL_STYLE,
        svs.CHART_STYLE,
        svs.VOTE_STYLE,
        svs.EXPAND_STYLE,
    ):
        assert painted in sheet, sheet
    assert painted not in str(svs.LIGHT_COLOURS_BY_STATE.values())
    assert painted != svs.VOTE_ALTERNATE_ROW_COLOUR


def test_the_module_borrows_no_token_for_a_light_it_paints(browser: Browser):
    """No token carries a light colour, so the refusal below is not a choice."""
    payload = state_payload("scrum_armed")
    draw_screen(browser, payload)
    blocked = payload["gate_row"]["light_colours"]["blocked"]
    assert browser.parsed(
        "acervatorSimVisuals.variableFor(" + json.dumps(blocked) + ")"
    ), "no single token carries the blocked colour"
    assert (
        browser.parsed("acervatorSimVisuals.colour(" + json.dumps(blocked) + ")")
        == blocked
    )


def test_the_module_borrows_no_token_for_a_margin_it_draws(browser: Browser):
    """No token carries this margin, so the refusal below is not a choice."""
    payload = state_payload("loaded")
    parts = draw_screen(browser, payload)
    inset = payload["gate_panel"]["host_margins_px"][0]
    assert browser.parsed(
        "acervatorSimVisuals.variableFor(" + json.dumps(inset) + ")"
    ), "no single token carries the host margin"
    assert one_part(parts, "pane-host")["style"]["paddingLeft"] == str(inset) + "px"


def test_the_module_borrows_no_token_for_a_point_size(browser: Browser):
    """A token group counts pixels, so a point size may not borrow one."""
    payload = state_payload("scrum_armed")
    draw_screen(browser, payload)
    written = browser.parsed(
        "acervatorSimVisuals.points(" + json.dumps(payload["gate_row"]["font_pt"]) + ")"
    )
    assert written == str(payload["gate_row"]["font_pt"]) + "pt"


def test_the_module_borrows_no_token_for_a_program_coordinate(browser: Browser):
    """A spacing step cannot mean a distance from the left of a row."""
    payload = state_payload("scrum_armed")
    draw_screen(browser, payload)
    box = payload["gate_row"]["rows"][SYMBOLS[0]]["program"][0]["rect"]
    written = browser.parsed("acervatorSimVisuals.pixels(" + json.dumps(box[0]) + ")")
    assert written == str(box[0]) + "px"


def test_an_eight_digit_hex_is_refused_and_named(js: JsRuntime):
    payload = state_payload("voted")
    payload["gate_row"]["label_colour"] = "#80ff3366"
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "qt-colour"]
    assert named, found["faults"]
    assert named[0]["detail"] == "#80ff3366"
    assert js.answer('qtColour("#80ff3366")') == "AARRGGBB"
    assert js.answer('colour("#80ff3366")') is None


def test_a_six_digit_hex_is_kept(js: JsRuntime):
    js.push(state_payload("voted"))
    assert js.answer("qtColour(" + json.dumps(svs.VOTE_BULL_COLOUR) + ")") is None
    assert svs.VOTE_BULL_COLOUR in str(
        js.answer("colour(" + json.dumps(svs.VOTE_BULL_COLOUR) + ")")
    )


def test_an_eight_digit_hex_inside_a_sheet_is_dropped_from_the_style(js: JsRuntime):
    payload = state_payload("voted")
    payload["gate_panel"]["empty_style"] = "color:#80ff3366;font-size:11px;"
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "qt-colour"]
    assert [one["detail"] for one in named] == ["color"]
    style = js.json(
        "acervatorSimVisuals.styleOf(acervatorSimVisuals.pane().empty_style)"
    )
    assert "color" not in style
    assert "fontSize" in style


def test_a_byte_alpha_rgba_is_refused_the_way_qt_writes_one(js: JsRuntime):
    js.push(state_payload("voted"))
    assert js.answer('qtColour("rgba(0, 229, 255, 18)")') == "rgba("
    assert js.answer('qtColour("rgba(0, 229, 255, 0.07)")') is None


HOSTILE_FIELDS = (
    ("gate_panel", "items"),
    ("gate_panel", "empty_text"),
    ("gate_panel", "label_min_width_px"),
    ("gate_row", "rows"),
    ("gate_row", "light_colours"),
    ("gate_row", "pitch_px"),
    ("chart", "program"),
    ("chart", "minimum_height_px"),
    ("votes", "rows"),
    ("votes", "columns"),
    ("votes", "row_height_px"),
    ("expand", "open"),
)

HOSTILE_VALUES = {
    "missing": None,
    "null": None,
    "number_for_text": 12,
    "text_for_number": "twelve",
    "nan": float("nan"),
    "inf": float("inf"),
    "huge": 10**24,
    "long_symbol": "S" * 200,
    "markup": "<img src='http://example.invalid/a.png'>",
}


def hostile_payload(panel: str, field: str, kind: str) -> dict:
    """One state with `panel.field` replaced by the named hostile value."""
    payload = state_payload("voted")
    if kind == "missing":
        del payload[panel][field]
        return payload
    payload[panel][field] = HOSTILE_VALUES[kind]
    return payload


@pytest.mark.parametrize("kind", sorted(HOSTILE_VALUES))
@pytest.mark.parametrize("panel,field", HOSTILE_FIELDS)
def test_a_hostile_value_is_recorded_and_never_raises(
    js: JsRuntime, panel: str, field: str, kind: str
):
    payload = hostile_payload(panel, field, kind)
    body = json.dumps(payload, allow_nan=True).replace("NaN", "null")
    body = body.replace("Infinity", "null")
    js._engine.globalObject().setProperty("PAYLOAD", body)
    found = js.json("acervatorSetSimVisuals(JSON.parse(PAYLOAD))")
    assert found is not None
    assert isinstance(found["faults"], list)
    assert js.answer("isLoaded()") is True


@pytest.mark.parametrize("panel,field", HOSTILE_FIELDS)
def test_a_missing_field_is_named_by_the_check_that_wants_it(
    js: JsRuntime, panel: str, field: str
):
    found = js.push(hostile_payload(panel, field, "missing"))
    named = [
        one
        for one in found["faults"]
        if one["field"] == field and one["fault"] == "missing"
    ]
    assert named, found["faults"]


@pytest.mark.parametrize("panel,field", HOSTILE_FIELDS)
def test_a_null_field_is_named_by_the_check_that_wants_it(
    js: JsRuntime, panel: str, field: str
):
    found = js.push(hostile_payload(panel, field, "null"))
    named = [
        one
        for one in found["faults"]
        if one["field"] == field and one["fault"] == "null"
    ]
    assert named, found["faults"]


@pytest.mark.parametrize(
    "panel,field",
    (
        ("gate_panel", "items"),
        ("gate_row", "rows"),
        ("votes", "rows"),
        ("chart", "program"),
    ),
)
def test_a_scalar_where_a_list_or_a_bag_belongs_is_named(
    js: JsRuntime, panel: str, field: str
):
    found = js.push(hostile_payload(panel, field, "number_for_text"))
    named = [
        one
        for one in found["faults"]
        if one["field"] == field and one["fault"] in ("not-a-list", "wrong-type")
    ]
    assert named or [
        one for one in found["faults"] if one["fault"] == "not-an-object"
    ], found["faults"]


def test_a_number_where_a_cell_belongs_is_named_against_the_placeholder(js: JsRuntime):
    payload = state_payload("voted")
    payload["votes"]["rows"][0]["cells"][0] = 12
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "wrong-type"]
    assert named, found["faults"]
    assert named[0]["detail"] == "number"


def test_a_number_where_a_symbol_belongs_is_named_against_the_focus(js: JsRuntime):
    payload = state_payload("voted")
    payload["gate_panel"]["symbols"][0] = 12
    found = js.push(payload)
    named = [
        one
        for one in found["faults"]
        if one["field"] == "symbols" and one["fault"] == "wrong-type"
    ]
    assert named, found["faults"]


def test_a_wrong_type_is_not_named_where_the_surface_names_no_default(js: JsRuntime):
    """A number field is held against something, so this reports nothing."""
    payload = state_payload("voted")
    payload["gate_row"]["pitch_px"] = "twelve"
    found = js.push(payload)
    named = [
        one
        for one in found["faults"]
        if one["field"] == "pitch_px" and one["fault"] == "wrong-type"
    ]
    assert named == []


INHERITED_NAMES = ("constructor", "toString", "hasOwnProperty", "__proto__")


@pytest.mark.parametrize("name", INHERITED_NAMES)
def test_a_symbol_named_after_a_javascript_member_is_refused(js: JsRuntime, name: str):
    payload = state_payload("loaded")
    payload["gate_panel"]["items"][1]["symbol"] = name
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "unknown-symbol"]
    assert [one["detail"] for one in named] == [name], found["faults"]
    assert js.json(f"acervatorSimVisuals.lampsFor({json.dumps(name)})") == []
    assert js.json(f"acervatorSimVisuals.programFor({json.dumps(name)})") == []


@pytest.mark.parametrize("name", INHERITED_NAMES)
def test_a_row_named_after_a_javascript_member_draws_no_light(
    browser: Browser, name: str
):
    payload = state_payload("loaded")
    payload["gate_panel"]["items"][1]["symbol"] = name
    parts = draw_screen(browser, payload)
    borrowed = [
        one for one in by_part(parts, "lamp-row") if one["attrs"]["data-symbol"] == name
    ]
    assert len(borrowed) == 1
    assert borrowed[0]["attrs"]["data-lamps"] == "0"


def test_an_align_word_named_after_a_javascript_member_paints_nothing(
    browser: Browser,
):
    payload = state_payload("scrum_armed")
    program = payload["gate_row"]["rows"][SYMBOLS[0]]["program"]
    captioned = next(one for one in program if one["op"] == svs.TEXT)
    captioned["align"] = "constructor"
    parts = draw_screen(browser, payload)
    drawn = by_part(parts, "lamp-label")[0]
    assert drawn["style"]["justifyContent"] == "normal", drawn["style"]
    assert drawn["text"] == captioned["text"]


def test_the_align_check_still_sees_the_word_the_surface_publishes(browser: Browser):
    """The alignment map is empty, so the check above proves nothing."""
    parts = draw_screen(browser, state_payload("scrum_armed"))
    assert by_part(parts, "lamp-label")[0]["style"]["justifyContent"] == "center"
    assert by_part(parts, "bank-marker")[0]["style"]["justifyContent"] == "flex-end"


def cells_of_first_row(parts: list) -> list:
    """The cells drawn under the first voting row, in document order."""
    found: list = []
    inside = False
    for one in parts:
        name = one["attrs"].get("data-part")
        if name == "vote-row":
            if inside:
                break
            inside = True
            continue
        if inside and name == "vote-cell":
            found.append(one)
    return found


#: What one hostile value draws in the first cell of the first voting row.
CELL_DRAWS = {
    "missing": "",
    "null": "",
    "number_for_text": "12",
    "text_for_number": "twelve",
    "nan": "",
    "inf": "",
    "huge": "1e+24",
    "long_symbol": "S" * 200,
    "markup": "<img src='http://example.invalid/a.png'>",
}


@pytest.mark.parametrize("kind", sorted(CELL_DRAWS))
def test_a_hostile_cell_value_draws_what_the_report_records(
    browser: Browser, kind: str
):
    payload = state_payload("voted")
    if kind == "missing":
        payload["votes"]["rows"][0]["cells"] = []
    elif kind in ("nan", "inf"):
        payload["votes"]["rows"][0]["cells"][0] = None
    else:
        payload["votes"]["rows"][0]["cells"][0] = HOSTILE_VALUES[kind]
    browser.js(WATCH_VIOLATIONS)
    parts = draw_screen(browser, payload)
    first = cells_of_first_row(parts)
    drawn = "" if not first else first[0]["text"]
    assert drawn == CELL_DRAWS[kind], (kind, drawn)
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []
    assert browser.js("document.images.length") == 0


def test_a_long_symbol_is_drawn_whole_into_the_document(browser: Browser):
    long_name = "S" * 200
    payload = svs.build_view_model(
        panel=read_pane(symbols=(long_name,)),
        chart=svs.PriceVwapModel(),
        votes=svs.VotingReadoutModel(),
    )
    parts = draw_screen(browser, payload)
    label = one_part(parts, "pane-label")
    assert label["text"] == long_name
    assert label["style"]["whiteSpace"] == "nowrap"


def test_a_numeric_symbol_still_paints_a_blank_voting_cell(js: JsRuntime):
    """The readout builds its first cell from text, so a number shows nothing."""
    votes = svs.VotingReadoutModel()
    votes.set_bots([12])
    payload = svs.build_view_model(
        panel=read_pane(symbols=(12,)),
        chart=svs.PriceVwapModel(),
        votes=votes,
    )
    js.push(payload)
    assert js.answer("voteRows()")[0]["cells"][0] == ""
    assert js.answer("rowOrder()") == ["12"]


def test_a_close_that_is_not_a_number_raises_before_the_payload_is_built():
    chart = svs.PriceVwapModel()
    chart.set_symbols(list(SYMBOLS))
    chart.append_tick(SYMBOLS[0], float("nan"), 1.0)
    chart.append_tick(SYMBOLS[0], float("nan"), 1.0)
    with pytest.raises(ValueError):
        svs.build_view_model(chart=chart)


def test_an_endless_close_raises_before_the_payload_is_built():
    """An endless close cancels to a value that is not a number."""
    chart = svs.PriceVwapModel()
    chart.set_symbols(list(SYMBOLS))
    chart.append_tick(SYMBOLS[0], float("inf"), 1.0)
    chart.append_tick(SYMBOLS[0], 1.0, 1.0)
    with pytest.raises(ValueError):
        svs.build_view_model(chart=chart)


def test_a_single_unplotted_close_leaves_no_stray_number_in_the_payload():
    """One bar plots, so this is the same case as the two above."""
    chart = svs.PriceVwapModel()
    chart.set_symbols(list(SYMBOLS))
    chart.append_tick(SYMBOLS[0], float("nan"), 1.0)
    body = json.dumps(svs.build_view_model(chart=chart), allow_nan=False)
    assert "NaN" not in body and "Infinity" not in body


def test_the_year_start_takes_an_infinity_and_the_two_caught_kinds():
    """set_ytd_start catches two error kinds and lets a third through."""
    chart = svs.PriceVwapModel()
    chart.set_symbols(list(SYMBOLS))
    chart.set_ytd_start(SYMBOLS[0], "not a stamp")
    assert svs.CHART_YTD_REFUSED in chart.calls
    with pytest.raises(OverflowError):
        chart.set_ytd_start(SYMBOLS[0], float("inf"))
