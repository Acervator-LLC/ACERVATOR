"""Drives market_inspector.js from every state the surface builds."""

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
from src.gui.main_tabs import market_inspector_surface as mis
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "market_inspector.js"
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


def reading(**named: Any) -> mis.TimeframeState:
    return mis.TimeframeState(**named)


def signal_for(
    symbol: str,
    name: str,
    score: float,
    active: bool = False,
    direction: str = "long",
) -> mis.SignalState:
    """One market signal with a daily and a weekly reading."""
    return mis.SignalState(
        symbol=symbol,
        signal=name,
        score=score,
        direction=direction,
        per_tf={
            "1d": reading(bb_position=0.82, z_score=1.4, at_upper_extreme=True),
            "1w": reading(bb_position=0.11, z_score=-2.1, tightening=True),
        },
        is_active=active,
    )


BTC = signal_for("BTC", mis.SIGNAL_ENTRY_LONG_HIGH, 3.5)
ETH = signal_for("ETH", mis.SIGNAL_ENTRY_SHORT, 2.25, direction="short")
SOL = signal_for("SOL", mis.SIGNAL_WATCHLIST, 1.75)
ADA = signal_for("ADA", mis.SIGNAL_ENTRY_LONG, 1.0, active=True)

SCANNED = [BTC, ETH, SOL, ADA]
PAIRS = [mis.PairState(BTC, ETH, 0.812), mis.PairState(SOL, ADA, -0.443)]

FLEET = [{"symbol": "ADA/USD"}]


def screen_for(signals: Any, pairs: Any, **wiring: Any) -> Any:
    """One drawn screen over an analyzer holding `signals` and `pairs`."""
    model = mis.MarketInspectorScreenModel(
        inspector_source=mis.InspectorSource(signals, pairs), **wiring
    )
    return model


def drawn_screen(signals: Any, pairs: Any) -> Any:
    """One screen whose tables the analyzer has already filled."""
    model = screen_for(signals, pairs)
    model.render_signals()
    return model


def per_bot_for(symbol: str, signals: Any, pairs: Any) -> dict:
    """The per-bot view one bot's symbol builds from one analyzer."""
    model = mis.build_per_bot_model(
        mis.SymbolOnlyBot(symbol), mis.InspectorSource(signals, pairs)
    )
    return mis.per_bot_view(model)


class RaisingSource:
    """An analyzer that refuses every read the screen makes."""

    @property
    def last_signals(self) -> Any:
        raise RuntimeError("analyzer down")

    @property
    def last_pairs(self) -> Any:
        raise RuntimeError("analyzer down")

    def get_signal(self, symbol: Any) -> Any:
        raise RuntimeError("analyzer down")


def state_payload(name: str) -> dict:
    """The view model for one named state of the screen."""
    if name == "fresh":
        return mis.build_view_model(screen_for([], []))
    if name == "scanned":
        model = screen_for(SCANNED, PAIRS)
        model.update_active_symbols(FLEET)
        return mis.build_view_model(model)
    if name == "with_active":
        model = screen_for(SCANNED, PAIRS)
        model.update_active_symbols(FLEET)
        model.press_show_active(True)
        return mis.build_view_model(model)
    if name == "cached":
        model = screen_for(SCANNED, PAIRS)
        model.last_meta = {
            "source": mis.SOURCE_CACHE,
            "age_seconds": 4_000.0,
            "symbol_count": 42,
            "error": "rate limited",
        }
        model.render_signals()
        return mis.build_view_model(model)
    if name == "fetch_error":
        model = screen_for([], [])
        model.last_meta = {
            "source": mis.SOURCE_ERROR,
            "age_seconds": 0.0,
            "symbol_count": 0,
            "error": "venue refused",
        }
        model.render_signals()
        return mis.build_view_model(model)
    if name == "partial":
        model = screen_for(SCANNED, [])
        model.last_meta = {
            "source": mis.SOURCE_NETWORK_PARTIAL,
            "age_seconds": 0.0,
            "symbol_count": 3,
            "error": "two markets missing",
        }
        model.render_signals()
        return mis.build_view_model(model)
    if name == "unwired":
        model = screen_for(SCANNED, PAIRS)
        model.render_signals()
        model.start_fetch()
        return mis.build_view_model(model)
    if name == "fetching":
        model = screen_for(SCANNED, PAIRS, fetcher=None)
        model.set_exchange_source(lambda: {"coinbase": "wired"}, lambda one: one)
        model.render_signals()
        model.start_fetch(force=True)
        return mis.build_view_model(model)
    if name == "analyzer_gone":
        model = mis.MarketInspectorScreenModel(inspector_source=RaisingSource())
        model.status_label_text = mis.ANALYZER_UNAVAILABLE_TEXT
        model.calls.append([mis.ANALYZER_UNREACHABLE])
        return mis.build_view_model(model)
    if name == "per_bot_no_scan":
        return mis.build_view_model(screen_for([], []), per_bot_for("BTC/USD", [], []))
    if name == "per_bot_signal":
        return mis.build_view_model(
            drawn_screen(SCANNED, PAIRS), per_bot_for("ETH/USD", SCANNED, PAIRS)
        )
    if name == "per_bot_top":
        return mis.build_view_model(
            drawn_screen(SCANNED, PAIRS), per_bot_for("BTC/USD", SCANNED, PAIRS)
        )
    if name == "per_bot_unknown":
        return mis.build_view_model(
            drawn_screen(SCANNED, PAIRS), per_bot_for("XRP/USD", SCANNED, PAIRS)
        )
    raise AssertionError("no state named " + name)


STATE_NAMES = (
    "fresh",
    "scanned",
    "with_active",
    "cached",
    "fetch_error",
    "partial",
    "unwired",
    "fetching",
    "analyzer_gone",
    "per_bot_no_scan",
    "per_bot_signal",
    "per_bot_top",
    "per_bot_unknown",
)

PER_BOT_STATES = (
    "per_bot_no_scan",
    "per_bot_signal",
    "per_bot_top",
    "per_bot_unknown",
)


def token_payload() -> dict:
    """The design token payload the page applies before it draws."""
    return dss.build_view_model()


def theme_payload() -> dict:
    """The theme payload the page applies before it draws."""
    return tes.build_view_model()


class JsRuntime(JsEngine):
    """A QJSEngine holding market_inspector.js and the modules it reads."""

    module_path = MODULE_PATH
    setter = "acervatorSetMarketInspector"

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
        return self.json("acervatorMarketInspector." + expression)


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
    assert sorted(js.answer("declaredFields()")) == sorted(payload)


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_nested_field_reaches_the_module(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for where in ("colors", "per_bot", "marks", "elements", "per_bot_view"):
        assert sorted(js.answer(f"nestedNames({json.dumps(where)})")) == sorted(
            payload[where]
        ), where


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_loose_fields_answer_by_value(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.answer("methodName()") == payload["method"] == mis.METHOD
    assert js.answer("actions()") == payload["actions"]
    assert js.answer("timers()") == payload["timers"]
    assert js.answer("timerDelays()") == payload["timer_delays_ms"]
    assert js.answer("busTopics()") == payload["bus_topics"]
    assert js.answer("callNames()") == payload["call_names"]
    assert js.answer("calls()") == payload["calls"]
    assert js.answer("perBot()") == payload["per_bot_view"]


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
    assert found["held"]["signalCells"] == sum(
        len(row) for row in payload["signal_rows"]
    )
    assert found["held"]["pairCells"] == sum(len(row) for row in payload["pair_rows"])


def test_a_missing_field_lowers_the_held_count_and_not_the_declared(js: JsRuntime):
    payload = state_payload("scanned")
    del payload["signal_rows"]
    found = js.push(payload)
    assert found["held"]["fields"] == found["declared"]["fields"] - 1
    named = [one for one in found["faults"] if one["field"] == "signal_rows"]
    assert named, found["faults"]


def test_a_dropped_cell_lowers_the_held_cell_count(js: JsRuntime):
    payload = state_payload("scanned")
    payload["signal_rows"][0].pop()
    found = js.push(payload)
    assert found["held"]["signalCells"] == found["declared"]["signalCells"] - 1
    named = [one for one in found["faults"] if one["fault"] == "column-count"]
    assert named, found["faults"]


def test_an_unknown_per_bot_element_is_named_and_never_drawn(js: JsRuntime):
    payload = state_payload("per_bot_signal")
    payload["per_bot_view"]["order"].append(["divider"])
    found = js.push(payload)
    assert found["held"]["perBot"] == found["declared"]["perBot"] - 1
    named = [one for one in found["faults"] if one["fault"] == "unknown-element"]
    assert [one["detail"] for one in named] == ["divider"], found["faults"]


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
    payload = state_payload("scanned")
    payload["signals_max_height_px"] = str(payload["signals_max_height_px"])
    js.push(payload)
    assert js.answer("kinds()")["signals_max_height_px"] == "string"
    assert python_kinds(state_payload("scanned"))["signals_max_height_px"] == "number"


def test_a_payload_that_is_not_an_object_is_refused(js: JsRuntime):
    js.bind_json("PAYLOAD", ["not", "a", "screen"])
    found = js.json("acervatorSetMarketInspector(JSON.parse(PAYLOAD))")
    assert found["declared"] is None
    assert found["faults"][0]["fault"] == "not-an-object"
    assert js.answer("isLoaded()") is False


def test_the_module_forgets_what_it_held(js: JsRuntime):
    js.push(state_payload("scanned"))
    assert js.answer("isLoaded()") is True
    js.run("acervatorMarketInspector.forget()")
    assert js.answer("isLoaded()") is False
    assert js.answer("perBot()") == {}
    assert js.answer("signalOrder()") == []


def test_the_module_asks_the_bridge_by_the_method_the_surface_names(js: JsRuntime):
    assert js.answer("method") == mis.METHOD
    assert js.json("typeof acervatorLoadMarketInspector") == "function"
    assert js.json("acervatorLoadMarketInspector({}) === null") is False
    assert js.answer("loadError()") == "the preload bridge is not present"


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


SAMPLE = state_payload("scanned")

PUBLISHED_VALUES = payload_values(SAMPLE, set()) | payload_values(
    state_payload("per_bot_signal"), set()
)
PUBLISHED_KEYS = payload_keys(SAMPLE, set()) | payload_keys(
    state_payload("per_bot_signal"), set()
)

#: A naming value tells the module what a field means; it paints nothing.
NAMING_VALUES = {
    mis.METHOD,
    "",
    mis.SPLITTER_ORIENTATION,
    mis.TABLE_RESIZE_MODE,
    mis.LABEL_ELEMENT,
    mis.GROUP_ELEMENT,
    mis.STRETCH_ELEMENT,
}

PAINTED_VALUES = PUBLISHED_VALUES - NAMING_VALUES - PUBLISHED_KEYS

TOKEN_VALUES = {
    str(one)
    for one in token_payload()["tokens"].values()
    if one is not None and str(one)
}


def test_the_module_writes_no_value_the_surface_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"market_inspector.js writes the painted values {written}"


def test_the_painted_set_still_holds_the_words_and_colours_the_screen_shows():
    """The painted set is empty, so the check above measures nothing."""
    for shown in (
        SAMPLE["refresh_label"],
        SAMPLE["show_active_label"],
        SAMPLE["signals_group_title"],
        SAMPLE["pair_columns"][0],
        SAMPLE["status_initial_text"],
        SAMPLE["colors"]["entry_long_high"],
        SAMPLE["colors"]["other"],
        SAMPLE["per_bot"]["no_scan_headline"],
        SAMPLE["marks"]["strong_open"],
        SAMPLE["marks"]["strong_weight"],
    ):
        assert shown in PAINTED_VALUES, shown


def test_the_module_writes_no_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"market_inspector.js writes the token values {written}"


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
    "colour": 'var spelled = "' + mis.COLOR_ENTRY_LONG_HIGH + '";',
    "grey": 'var spelled = "' + mis.COLOR_OTHER + '";',
    "token_value": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "caption": 'var spelled = "' + mis.REFRESH_LABEL + '";',
    "column": 'var spelled = "' + mis.SIGNAL_COLUMNS[0] + '";',
    "weight": 'var spelled = "' + mis.STRONG_WEIGHT + '";',
    "max_height": "var spelled = " + str(mis.SIGNALS_MAX_HEIGHT_PX) + ";",
    "margin": "var spelled = " + str(mis.GROUP_MARGINS_PX[0]) + ";",
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
    found = js_literals("// " + mis.COLOR_ENTRY_LONG_HIGH + '\nvar kept = "kept";')
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
        assert runtime.json("typeof acervatorSetMarketInspector") == "function", kind


def test_a_label_alone_is_an_identity_here_because_no_group_shares_one(js: JsRuntime):
    payload = state_payload("scanned")
    js.push(payload)
    pairs = js.answer("labelPairs()")
    labels = [one[1] for one in pairs]
    assert len(pairs) == len(payload["signal_columns"]) + len(payload["pair_columns"])
    assert js.answer("labelCollisions()") == []
    assert len(set(labels)) == len(labels), sorted(labels)


def test_the_collision_check_names_a_label_two_groups_both_carry(js: JsRuntime):
    """No label collides, so the check above would pass whatever it read."""
    payload = state_payload("scanned")
    payload["pair_columns"][0] = payload["signal_columns"][0]
    js.push(payload)
    assert js.answer("labelCollisions()") == [payload["signal_columns"][0]]


@pytest.mark.parametrize("state", ("scanned", "with_active", "cached"))
def test_the_signal_rows_are_drawn_in_the_order_the_surface_sent(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    assert js.answer("signalOrder()") == [row[0][0] for row in payload["signal_rows"]]
    assert js.answer("pairOrder()") == [row[0][0] for row in payload["pair_rows"]]


def test_the_order_check_names_a_reordered_pair_of_rows(js: JsRuntime):
    payload = state_payload("scanned")
    rows = payload["signal_rows"]
    before = [row[0][0] for row in rows]
    rows[0], rows[-1] = rows[-1], rows[0]
    js.push(payload)
    after = js.answer("signalOrder()")
    assert after != before
    assert after[0] == before[-1] and after[-1] == before[0]


def test_a_swap_of_two_rows_values_is_named_by_row_name_not_by_position(
    js: JsRuntime,
):
    payload = state_payload("scanned")
    rows = payload["signal_rows"]
    column = payload["signal_columns"][2]
    first, second = rows[0][0][0], rows[1][0][0]
    rows[0][2], rows[1][2] = rows[1][2], rows[0][2]
    js.push(payload)
    assert js.answer("signalOrder()") == [row[0][0] for row in rows]
    moved = js.answer(f"signalRow({json.dumps(first)})")
    stayed = js.answer(f"signalRow({json.dumps(second)})")
    kept = state_payload("scanned")["signal_rows"]
    assert moved[column] == kept[1][2], "the swap did not reach the named row"
    assert stayed[column] == kept[0][2]


def test_a_row_read_by_a_name_no_row_carries_answers_nothing(js: JsRuntime):
    js.push(state_payload("scanned"))
    assert js.answer('signalRow("NOTHING")') is None
    assert js.answer(f"signalRow({json.dumps(SAMPLE['signal_rows'][0][0][0])})")


def test_a_duplicate_row_name_is_reported(js: JsRuntime):
    payload = state_payload("scanned")
    payload["signal_rows"][1][0][0] = payload["signal_rows"][0][0][0]
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "duplicate-name"]
    assert [one["detail"] for one in named] == [payload["signal_rows"][0][0][0]]


def test_no_duplicate_is_reported_when_the_names_differ(js: JsRuntime):
    """The duplicate check reports on every payload, so it names nothing."""
    found = js.push(state_payload("scanned"))
    named = [one for one in found["faults"] if one["fault"] == "duplicate-name"]
    assert named == []


@pytest.mark.parametrize("state", PER_BOT_STATES)
def test_the_per_bot_order_is_the_list_the_surface_published(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.answer("perBotOrder()") == payload["per_bot_view"]["order"]


def test_the_published_layout_defaults_match_a_real_qt_layout(qapp):
    """The surface publishes what a Qt layout takes when nothing sets it."""
    assert qapp is not None
    from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QVBoxLayout, QWidget

    host = QWidget()
    per_bot = QVBoxLayout(host)
    per_bot.setSpacing(mis.PER_BOT_SPACING_PX)
    assert tuple(per_bot.getContentsMargins()) == mis.PER_BOT_MARGINS_PX
    assert per_bot.spacing() == mis.PER_BOT_SPACING_PX

    box = QGroupBox(mis.HIGHER_GROUP_TITLE)
    card = QVBoxLayout(box)
    assert tuple(card.getContentsMargins()) == mis.GROUP_MARGINS_PX
    assert card.spacing() == mis.GROUP_SPACING_PX

    nested = QHBoxLayout()
    assert tuple(nested.getContentsMargins()) == mis.TOP_ROW_MARGINS_PX


def test_the_marked_text_is_built_from_the_pieces_the_surface_publishes():
    assert mis.NO_SCAN_TEXT == mis.marked_text(
        mis.NO_PIECE, mis.NO_SCAN_HEADLINE, mis.NO_SCAN_BREAKS, mis.NO_SCAN_BODY
    )
    assert mis.SIGNAL_LINE_FORMAT == mis.marked_text(
        mis.SIGNAL_LINE_LEAD,
        mis.SIGNAL_LINE_MARK,
        mis.NO_BREAKS,
        mis.SIGNAL_LINE_TAIL_FORMAT,
    )


def test_the_module_rebuilds_each_marked_label_from_its_pieces(js: JsRuntime):
    payload = state_payload("per_bot_signal")
    js.push(payload)
    for whole, lead, strong, breaks, tail in payload["per_bot_view"]["marks"]:
        marks = js.json(
            "acervatorMarketInspector.marksFor("
            + json.dumps(payload)
            + ", "
            + json.dumps(whole)
            + ")"
        )
        assert marks == {
            "lead": lead,
            "strong": strong,
            "breaks": breaks,
            "tail": tail,
        }


def test_a_mark_that_does_not_rebuild_its_own_text_is_named(js: JsRuntime):
    payload = state_payload("per_bot_signal")
    payload["per_bot_view"]["marks"][0][2] = "INVENTED"
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "mark-mismatch"]
    assert named, found["faults"]


def test_a_label_the_surface_left_unmarked_but_marked_up_is_named(js: JsRuntime):
    payload = state_payload("per_bot_signal")
    payload["per_bot_view"]["marks"] = []
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "markup"]
    assert named, found["faults"]


def test_an_eight_digit_hex_is_refused_and_named(js: JsRuntime):
    payload = state_payload("scanned")
    payload["colors"]["other"] = "#80ff3366"
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "qt-colour"]
    assert [one["detail"] for one in named] == ["#80ff3366"], found["faults"]
    assert js.answer('qtColour("#80ff3366")') == "AARRGGBB"
    assert js.answer('colour("#80ff3366")') is None


def test_a_six_digit_hex_is_kept(js: JsRuntime):
    js.push(state_payload("scanned"))
    written = json.dumps(mis.COLOR_ENTRY_LONG_HIGH)
    assert js.answer("qtColour(" + written + ")") is None
    assert mis.COLOR_ENTRY_LONG_HIGH in str(js.answer("colour(" + written + ")"))


def test_a_byte_alpha_rgba_is_refused_the_way_qt_writes_one(js: JsRuntime):
    js.push(state_payload("scanned"))
    assert js.answer('qtColour("rgba(0, 229, 255, 18)")') == "rgba("
    assert js.answer('qtColour("rgba(0, 229, 255, 0.07)")') is None


def test_an_eight_digit_hex_inside_a_sheet_is_dropped_from_the_style(js: JsRuntime):
    payload = state_payload("scanned")
    payload["status_style"] = "color:#80ff3366;font-size:11px;"
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "qt-colour"]
    assert [one["detail"] for one in named] == ["color"], found["faults"]
    style = js.json("acervatorMarketInspector.styleOf(" + json.dumps(payload) + ".x)")
    assert style == {}


def test_a_cell_colour_qt_reads_differently_is_named(js: JsRuntime):
    payload = state_payload("scanned")
    payload["signal_rows"][0][1][1] = "#80ff3366"
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "qt-colour"]
    assert named, found["faults"]
    assert named[0]["detail"] == "#80ff3366"


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
            if self.js("typeof window.acervatorSetMarketInspector") == "function":
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
    "fontFamily",
    "fontWeight",
    "whiteSpace",
    "overflow",
    "textOverflow",
    "userSelect",
    "display",
    "flexDirection",
    "gap",
    "maxHeight",
    "minWidth",
    "width",
    "height",
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
    "window.HOST = document.getElementById('market-inspector-host');"
    "if (!window.HOST) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'market-inspector-host';"
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
    "        whole: el.textContent,"
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
    """Push the tokens into the page and apply them to the document."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw(browser: Browser, payload: dict, drawer: str) -> list:
    """Render `payload` through `drawer` and return what READ_PARTS finds."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetMarketInspector(JSON.parse(window.PAYLOAD));"
        "acervatorMarketInspector." + drawer + "(window.HOST);"
    )
    return read_parts(browser)


def draw_screen(browser: Browser, payload: dict) -> list:
    return draw(browser, payload, "renderScreen")


def draw_per_bot(browser: Browser, payload: dict) -> list:
    return draw(browser, payload, "renderPerBot")


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
    """The computed values a bare `tag` takes from the whole of `body`."""
    names: list = []
    for prop, _ in declarations_of(body):
        names.extend(EXPANDED.get(prop, (prop,)))
    if not names:
        return {}
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(tag)
        + ", "
        + json.dumps(css_body(body))
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


def channels(value: str) -> list:
    """The three channel numbers of one `#rrggbb`."""
    body = value.lstrip("#")
    if len(body) == 3:
        body = "".join(one * 2 for one in body)
    return [int(body[at : at + 2], 16) for at in (0, 2, 4)]


def as_rgb(value: str) -> str:
    """One `#rrggbb` as the `rgb()` the document reads back."""
    body = value.lstrip("#")
    if len(body) == 3:
        body = "".join(one * 2 for one in body)
    return "rgb({}, {}, {})".format(
        int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)
    )


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorMarketInspector") == "object"
    assert browser.js("typeof window.acervatorSetMarketInspector") == "function"
    assert browser.js("typeof window.acervatorLoadMarketInspector") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_screen(browser, state_payload("scanned"))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_drawn_parts_carry_the_names_the_checks_read(browser: Browser, state: str):
    parts = draw_screen(browser, state_payload(state))
    named = {one["attrs"]["data-part"] for one in parts}
    assert {"screen", "split", "left-pane", "filter-row", "refresh-button"} <= named
    assert {"active-switch", "switch-box", "switch-text", "status-line"} <= named
    assert {"table-group", "group-legend", "group-body", "grid"} <= named
    assert {"grid-head", "head-row", "head-cell", "grid-body"} <= named
    assert {"left-stretch", "filter-stretch", "topology-slot"} <= named
    every, carrying = browser.parsed(COUNT_ELEMENTS)
    assert every == carrying, f"{every - carrying} drawn elements carry no name"


@pytest.mark.parametrize("state", PER_BOT_STATES)
def test_the_drawn_per_bot_parts_carry_the_names_the_checks_read(
    browser: Browser, state: str
):
    parts = draw_per_bot(browser, state_payload(state))
    named = {one["attrs"]["data-part"] for one in parts}
    assert {"per-bot", "per-bot-stretch"} <= named
    every, carrying = browser.parsed(COUNT_ELEMENTS)
    assert every == carrying, f"{every - carrying} drawn elements carry no name"


def test_the_naming_check_reports_an_element_left_without_a_name(browser: Browser):
    """Every element was named because the count reads one list twice."""
    draw_screen(browser, state_payload("scanned"))
    before = browser.parsed(COUNT_ELEMENTS)
    browser.js("window.HOST.appendChild(document.createElement('span'));")
    every, carrying = browser.parsed(COUNT_ELEMENTS)
    assert before[0] == before[1]
    assert every == carrying + 1


def test_one_grid_row_is_drawn_for_each_row_the_surface_sent(browser: Browser):
    payload = state_payload("scanned")
    parts = draw_screen(browser, payload)
    rows = [
        one
        for one in by_part(parts, "grid-row")
        if one["attrs"]["data-table"] == "signals"
    ]
    assert [one["attrs"]["data-name"] for one in rows] == [
        row[0][0] for row in payload["signal_rows"]
    ]
    pairs = [
        one
        for one in by_part(parts, "grid-row")
        if one["attrs"]["data-table"] == "pairs"
    ]
    assert len(pairs) == len(payload["pair_rows"])


def test_every_drawn_cell_carries_its_row_name_and_its_column(browser: Browser):
    payload = state_payload("scanned")
    parts = draw_screen(browser, payload)
    for at, row in enumerate(payload["signal_rows"]):
        name = row[0][0]
        drawn = [
            one
            for one in by_part(parts, "grid-cell")
            if one["attrs"]["data-name"] == name
            and one["attrs"]["data-table"] == "signals"
        ]
        assert [one["attrs"]["data-column"] for one in drawn] == list(
            payload["signal_columns"]
        ), name
        assert [one["text"] for one in drawn] == [cell[0] for cell in row], name


def test_a_reordered_pair_of_rows_is_seen_in_the_document_by_name(browser: Browser):
    payload = state_payload("scanned")
    before = [row[0][0] for row in payload["signal_rows"]]
    rows = payload["signal_rows"]
    rows[0], rows[-1] = rows[-1], rows[0]
    parts = draw_screen(browser, payload)
    drawn = [
        one["attrs"]["data-name"]
        for one in by_part(parts, "grid-row")
        if one["attrs"]["data-table"] == "signals"
    ]
    assert drawn[0] == before[-1] and drawn[-1] == before[0]
    assert drawn != before


def test_a_swapped_cell_value_is_seen_against_the_row_that_now_carries_it(
    browser: Browser,
):
    payload = state_payload("scanned")
    kept = state_payload("scanned")["signal_rows"]
    rows = payload["signal_rows"]
    first, second = rows[0][0][0], rows[1][0][0]
    rows[0][2], rows[1][2] = rows[1][2], rows[0][2]
    parts = draw_screen(browser, payload)
    column = payload["signal_columns"][2]

    def drawn_for(name: str) -> str:
        found = [
            one
            for one in by_part(parts, "grid-cell")
            if one["attrs"]["data-name"] == name
            and one["attrs"]["data-column"] == column
            and one["attrs"]["data-table"] == "signals"
        ]
        assert len(found) == 1, name
        return found[0]["text"]

    assert drawn_for(first) == kept[1][2][0]
    assert drawn_for(second) == kept[0][2][0]


def test_the_signal_cell_paints_the_colour_the_surface_sent(browser: Browser):
    payload = state_payload("scanned")
    parts = draw_screen(browser, payload)
    column = payload["signal_columns"][1]
    seen = set()
    for row in payload["signal_rows"]:
        name = row[0][0]
        cell = [
            one
            for one in by_part(parts, "grid-cell")
            if one["attrs"]["data-name"] == name
            and one["attrs"]["data-column"] == column
        ][0]
        assert cell["style"]["color"] == as_rgb(row[1][1]), name
        seen.add(row[1][1])
    assert len(seen) > 1, seen


def test_a_swap_of_two_signal_colours_is_seen_on_unequal_channels(browser: Browser):
    """The channels were equal, so the swap could not have been seen."""
    payload = state_payload("scanned")
    rows = payload["signal_rows"]
    rows[0][1][1], rows[1][1][1] = rows[1][1][1], rows[0][1][1]
    parts = draw_screen(browser, payload)
    column = payload["signal_columns"][1]
    drawn = [
        one
        for one in by_part(parts, "grid-cell")
        if one["attrs"]["data-column"] == column
    ]
    assert drawn[0]["style"]["color"] == as_rgb(mis.COLOR_ENTRY_SHORT)
    assert drawn[1]["style"]["color"] == as_rgb(mis.COLOR_ENTRY_LONG_HIGH)
    assert len(set(channels(mis.COLOR_ENTRY_LONG_HIGH))) > 1


def test_the_grey_signal_colour_is_told_apart_by_its_text(browser: Browser):
    """Grey has three equal channels, so a swap inside it is invisible."""
    assert len(set(channels(mis.COLOR_OTHER))) == 1
    payload = state_payload("scanned")
    payload["signal_rows"][0][1] = ["INVENTED", mis.COLOR_OTHER]
    parts = draw_screen(browser, payload)
    column = payload["signal_columns"][1]
    drawn = [
        one
        for one in by_part(parts, "grid-cell")
        if one["attrs"]["data-column"] == column
    ][0]
    assert drawn["text"] == "INVENTED"
    assert drawn["style"]["color"] == as_rgb(mis.COLOR_OTHER)


def test_every_cell_is_cut_on_the_right_the_way_a_qt_cell_is(browser: Browser):
    parts = draw_screen(browser, state_payload("scanned"))
    for cell in by_part(parts, "grid-cell") + by_part(parts, "head-cell"):
        assert cell["style"]["whiteSpace"] == "nowrap", cell
        assert cell["style"]["textOverflow"] == "ellipsis", cell
        assert cell["style"]["overflow"] == "hidden", cell


def test_a_label_cannot_be_dragged_over_the_way_a_qt_label_cannot(browser: Browser):
    parts = draw_screen(browser, state_payload("scanned"))
    assert one_part(parts, "status-line")["style"]["userSelect"] == "none"
    assert one_part(parts, "switch-text")["style"]["userSelect"] == "none"


def test_a_label_the_surface_does_not_wrap_holds_one_flow(browser: Browser):
    parts = draw_screen(browser, state_payload("scanned"))
    assert one_part(parts, "status-line")["style"]["whiteSpace"] == "pre"


def test_the_no_scan_label_wraps_because_the_surface_says_it_does(browser: Browser):
    payload = state_payload("per_bot_no_scan")
    assert payload["per_bot"]["no_scan_word_wrap"] is True
    parts = draw_per_bot(browser, payload)
    assert one_part(parts, "per-bot-label")["style"]["whiteSpace"] == "pre-wrap"


def test_the_table_takes_focus_the_way_a_qt_table_does(browser: Browser):
    draw_screen(browser, state_payload("scanned"))
    assert (
        browser.js("document.querySelector('[data-part=\"group-body\"]').tabIndex") == 0
    )


def test_the_refresh_button_is_disabled_while_a_fetch_is_pending(browser: Browser):
    payload = state_payload("fetching")
    assert payload["refresh_enabled"] is False
    parts = draw_screen(browser, payload)
    assert browser.js(
        "document.querySelector('[data-part=\"refresh-button\"]').disabled"
    )
    assert one_part(parts, "refresh-button")["text"] == payload["refresh_label"]


def test_the_refresh_button_is_live_when_no_fetch_is_pending(browser: Browser):
    """The button is disabled whatever the payload says."""
    payload = state_payload("scanned")
    assert payload["refresh_enabled"] is True
    draw_screen(browser, payload)
    assert (
        browser.js("document.querySelector('[data-part=\"refresh-button\"]').disabled")
        is False
    )


def test_the_switch_carries_the_state_the_surface_sent(browser: Browser):
    off = state_payload("scanned")
    draw_screen(browser, off)
    assert (
        browser.js("document.querySelector('[data-part=\"switch-box\"]').checked")
        is False
    )
    on = state_payload("with_active")
    assert on["show_active_checked"] is True
    draw_screen(browser, on)
    assert browser.js("document.querySelector('[data-part=\"switch-box\"]').checked")


def test_the_status_line_takes_the_style_the_surface_declares(browser: Browser):
    payload = state_payload("scanned")
    parts = draw_screen(browser, payload)
    line = one_part(parts, "status-line")
    wanted = probe(browser, "span", payload["status_style"])
    assert wanted, "the probe read nothing from the status sheet"
    for name, value in wanted.items():
        assert line["style"][name] == value, name


def test_the_no_scan_label_takes_the_whole_style_the_surface_declares(
    browser: Browser,
):
    payload = state_payload("per_bot_no_scan")
    parts = draw_per_bot(browser, payload)
    drawn = one_part(parts, "per-bot-label")
    wanted = probe(browser, "div", payload["per_bot"]["no_scan_style"])
    assert sorted(wanted) == [
        "color",
        "paddingBottom",
        "paddingLeft",
        "paddingRight",
        "paddingTop",
    ], sorted(wanted)
    for name, value in wanted.items():
        assert drawn["style"][name] == value, name


def test_the_signal_line_takes_the_style_its_own_row_carries(browser: Browser):
    payload = state_payload("per_bot_signal")
    card = payload["per_bot_view"]["order"][0]
    line = card[2][0]
    parts = draw_per_bot(browser, payload)
    drawn = by_part(parts, "per-bot-label")[0]
    wanted = probe(browser, "div", line[2])
    assert sorted(wanted) == ["color", "fontSize"], sorted(wanted)
    for name, value in wanted.items():
        assert drawn["style"][name] == value, name


def test_the_two_group_boxes_take_the_margins_the_surface_publishes(browser: Browser):
    payload = state_payload("scanned")
    parts = draw_screen(browser, payload)
    for group in by_part(parts, "table-group"):
        for at, side in enumerate(
            ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom")
        ):
            assert group["style"][side] == str(payload["group_margins_px"][at]) + "px"
        assert group["style"]["gap"] == str(payload["group_spacing_px"]) + "px"


def test_the_table_body_takes_the_height_ceiling_the_surface_publishes(
    browser: Browser,
):
    payload = state_payload("scanned")
    parts = draw_screen(browser, payload)
    heights = {
        one["attrs"]["data-table"]: one["style"]["maxHeight"]
        for one in by_part(parts, "group-body")
    }
    assert heights["signals"] == str(payload["signals_max_height_px"]) + "px"
    assert heights["pairs"] == str(payload["pairs_max_height_px"]) + "px"


def test_the_per_bot_view_takes_the_margins_and_spacing_it_publishes(browser: Browser):
    payload = state_payload("per_bot_signal")
    parts = draw_per_bot(browser, payload)
    view = one_part(parts, "per-bot")
    for at, side in enumerate(
        ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom")
    ):
        assert (
            view["style"][side] == str(payload["per_bot_view"]["margins_px"][at]) + "px"
        )
    assert view["style"]["gap"] == str(payload["per_bot_view"]["spacing_px"]) + "px"


def sole_name_for(value: Any) -> str:
    """The one CSS variable carrying `value`, an alias left out."""
    model = token_payload()
    carried = [
        name
        for name, held in model["tokens"].items()
        if model["alias_targets"].get(name) is None and str(held) == str(value)
    ]
    assert len(carried) == 1, f"{len(carried)} names carry {value}: {carried}"
    return "--" + carried[0]


def carriers_for(value: Any) -> list:
    """Every non-alias token name carrying `value`."""
    model = token_payload()
    return [
        name
        for name, held in model["tokens"].items()
        if model["alias_targets"].get(name) is None and str(held) == str(value)
    ]


LENGTHS_ON_THE_SCREEN = (
    "signals_max_height_px",
    "pairs_max_height_px",
    "left_spacing_px",
    "top_row_spacing_px",
    "per_bot_spacing_px",
    "group_spacing_px",
)

#: The one token group whose name means what every length here measures.
LENGTH_GROUPS = ["spacing"]


def read_length(browser: Browser, value: Any) -> tuple:
    """What the module writes for one length, and the token name it took."""
    written = browser.parsed(
        "acervatorMarketInspector.length(" + json.dumps(value) + ")"
    )
    name = browser.parsed(
        "acervatorMarketInspector.variableInGroups("
        + json.dumps(value)
        + ", "
        + json.dumps(LENGTH_GROUPS)
        + ")"
    )
    return written, name


@pytest.mark.parametrize("field", LENGTHS_ON_THE_SCREEN)
def test_no_length_on_this_screen_borrows_a_token(browser: Browser, field: str):
    payload = state_payload("scanned")
    draw_screen(browser, payload)
    written, name = read_length(browser, payload[field])
    assert name is None, f"{field} borrowed {name}"
    assert written == str(payload[field]) + "px", field


def test_the_length_rule_borrows_a_token_that_does_mean_the_same_thing(
    browser: Browser,
):
    """No length borrowed a token, so the rule above proves nothing."""
    draw_screen(browser, state_payload("scanned"))
    model = token_payload()
    lone = [
        model["tokens"][name]
        for name in model["groups"]["spacing"]
        if len(carriers_for(model["tokens"][name])) == 1
    ]
    assert lone, "no spacing token carries a value of its own"
    written, name = read_length(browser, lone[0])
    assert name is not None
    assert written.startswith("calc(var(--" + name), written


#: Every length whose value one token carries under a name meaning something else.
BORROWED_UNDER_ANOTHER_NAME = {
    6: "RADIUS_CARD",
    11: "TYPE_SMALL",
}


@pytest.mark.parametrize("value,name", sorted(BORROWED_UNDER_ANOTHER_NAME.items()))
def test_a_length_a_token_carries_under_another_meaning_is_refused(
    browser: Browser, value: int, name: str
):
    draw_screen(browser, state_payload("scanned"))
    assert carriers_for(value) == [name], carriers_for(value)
    written, taken = read_length(browser, value)
    assert taken is None, f"{value} borrowed {taken}"
    assert written == str(value) + "px"


#: Every signal colour one token carries, under a name meaning something else.
COLOURS_A_TOKEN_CARRIES = ("entry_long_high", "entry_short_high", "other", "active")


@pytest.mark.parametrize("name", COLOURS_A_TOKEN_CARRIES)
def test_the_module_borrows_no_token_for_a_signal_colour(browser: Browser, name: str):
    """A token carries each of these, so the refusal is a choice."""
    payload = state_payload("scanned")
    draw_screen(browser, payload)
    value = payload["colors"][name]
    assert len(carriers_for(value)) == 1, carriers_for(value)
    assert (
        browser.parsed(
            "acervatorMarketInspector.variableFor(" + json.dumps(value) + ")"
        )
        == carriers_for(value)[0]
    )
    assert (
        browser.parsed("acervatorMarketInspector.colour(" + json.dumps(value) + ")")
        == value
    )


def test_a_signal_colour_no_token_carries_is_painted_the_same_way(browser: Browser):
    """Every colour had a token, so the check above measures one case."""
    payload = state_payload("scanned")
    draw_screen(browser, payload)
    value = payload["colors"]["watchlist"]
    assert carriers_for(value) == []
    assert (
        browser.parsed("acervatorMarketInspector.colour(" + json.dumps(value) + ")")
        == value
    )


def test_rewriting_a_token_that_holds_a_signal_colour_moves_nothing(browser: Browser):
    payload = state_payload("scanned")
    before = draw_screen(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty("
        + json.dumps(sole_name_for(payload["colors"]["entry_long_high"]))
        + ", '#123456');"
    )
    after = read_parts(browser)
    moved = [
        one["attrs"]["data-part"]
        for one, was in zip(after, before)
        if one["style"]["color"] != was["style"]["color"]
    ]
    assert moved == [], moved


def test_the_rewrite_check_would_see_a_colour_that_did_move(browser: Browser):
    """Nothing moved because this check compares one list with itself."""
    payload = state_payload("scanned")
    before = draw_screen(browser, payload)
    browser.js(
        "document.querySelector('[data-part=\"status-line\"]')"
        ".style.color = '#123456';"
    )
    after = read_parts(browser)
    moved = [
        one["attrs"]["data-part"]
        for one, was in zip(after, before)
        if one["style"]["color"] != was["style"]["color"]
    ]
    assert moved == ["status-line"], moved


IMAGE_TAG = "<img src='http://example.invalid/a.png'>"


def test_a_qt_label_parses_an_image_tag_this_screen_refuses(qapp):
    """Measured here: Qt reserves a broken-image box for the same text."""
    assert qapp is not None
    from PySide6.QtWidgets import QLabel

    tagged = QLabel(IMAGE_TAG)
    lettered = QLabel(IMAGE_TAG.replace("<", "&lt;").replace(">", "&gt;"))
    assert tagged.sizeHint().width() < lettered.sizeHint().width() / 4, (
        tagged.sizeHint().width(),
        lettered.sizeHint().width(),
    )
    assert tagged.wordWrap() is False


def test_a_bot_symbol_carrying_an_image_tag_is_drawn_as_characters(browser: Browser):
    payload = state_payload("scanned")
    payload["signal_rows"][0][0][0] = IMAGE_TAG
    browser.js(WATCH_VIOLATIONS)
    parts = draw_screen(browser, payload)
    drawn = [
        one
        for one in by_part(parts, "grid-cell")
        if one["attrs"]["data-column"] == payload["signal_columns"][0]
    ][0]
    assert drawn["text"] == IMAGE_TAG
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []
    assert browser.js("document.images.length") == 0


def test_a_per_bot_card_title_carrying_an_image_tag_is_drawn_as_characters(
    browser: Browser,
):
    payload = state_payload("per_bot_signal")
    payload["per_bot_view"]["order"][0][1] = IMAGE_TAG
    browser.js(WATCH_VIOLATIONS)
    parts = draw_per_bot(browser, payload)
    assert by_part(parts, "card-legend")[0]["text"] == IMAGE_TAG
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []
    assert browser.js("document.images.length") == 0


def test_a_label_carrying_an_image_tag_is_reported_as_markup(js: JsRuntime):
    payload = state_payload("per_bot_signal")
    payload["per_bot_view"]["order"][0][1] = IMAGE_TAG
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "markup"]
    assert named, found["faults"]
    assert named[0]["detail"] == "<"


def test_the_markup_check_stays_quiet_on_a_symbol_with_no_tag(js: JsRuntime):
    """The markup check reports on every text, so it names nothing."""
    found = js.push(state_payload("per_bot_signal"))
    named = [one for one in found["faults"] if one["fault"] == "markup"]
    assert named == []


def test_the_marked_label_draws_its_emphasis_as_an_element(browser: Browser):
    payload = state_payload("per_bot_no_scan")
    parts = draw_per_bot(browser, payload)
    assert (
        one_part(parts, "mark-strong")["text"] == payload["per_bot"]["no_scan_headline"]
    )
    assert one_part(parts, "mark-lead")["text"] == payload["marks"]["no_piece"]
    assert payload["per_bot"]["no_scan_body"] in one_part(parts, "mark-tail")["text"]
    assert one_part(parts, "per-bot-label")["whole"].count("<") == 0


def test_the_emphasis_is_drawn_at_the_weight_the_surface_names(browser: Browser):
    payload = state_payload("per_bot_no_scan")
    parts = draw_per_bot(browser, payload)
    wanted = browser.parsed(
        "window.probeStyle('strong', 'font-weight: "
        + payload["marks"]["strong_weight"]
        + "', ['fontWeight'])"
    )
    assert one_part(parts, "mark-strong")["style"]["fontWeight"] == wanted["fontWeight"]


HOSTILE_FIELDS = (
    "signal_rows",
    "pair_rows",
    "signal_columns",
    "status_text",
    "signals_max_height_px",
    "group_margins_px",
    "colors",
    "per_bot_view",
    "table_alternating_rows",
    "splitter_stretch",
)

HOSTILE_VALUES = {
    "missing": None,
    "null": None,
    "number_for_text": 12,
    "text_for_number": "twelve",
    "nan": float("nan"),
    "inf": float("inf"),
    "negative_inf": float("-inf"),
    "huge": 10**24,
    "long_name": "S" * 200,
    "markup": IMAGE_TAG,
    "duplicate_name": None,
}


def hostile_payload(field: str, kind: str) -> dict:
    """One state with `field` replaced by the named hostile value."""
    payload = state_payload("per_bot_signal")
    if kind == "missing":
        del payload[field]
        return payload
    if kind == "duplicate_name":
        payload["signal_rows"][1][0][0] = payload["signal_rows"][0][0][0]
        return payload
    payload[field] = HOSTILE_VALUES[kind]
    return payload


def pushed(js: JsRuntime, payload: dict) -> Any:
    """Push a payload that may carry a value JSON cannot write."""
    body = json.dumps(payload, allow_nan=True)
    body = body.replace("NaN", "null").replace("-Infinity", "null")
    body = body.replace("Infinity", "null")
    js.bind_json("PAYLOAD", body)
    return js.json("acervatorSetMarketInspector(JSON.parse(JSON.parse(PAYLOAD)))")


@pytest.mark.parametrize("kind", sorted(HOSTILE_VALUES))
@pytest.mark.parametrize("field", HOSTILE_FIELDS)
def test_a_hostile_value_is_recorded_and_never_raises(
    js: JsRuntime, field: str, kind: str
):
    found = pushed(js, hostile_payload(field, kind))
    assert found is not None
    assert isinstance(found["faults"], list)
    assert js.answer("isLoaded()") is True


@pytest.mark.parametrize("field", HOSTILE_FIELDS)
def test_a_missing_field_is_named_by_the_check_that_wants_it(js: JsRuntime, field: str):
    found = js.push(hostile_payload(field, "missing"))
    named = [
        one
        for one in found["faults"]
        if one["field"] == field and one["fault"] == "missing"
    ]
    assert named, found["faults"]


@pytest.mark.parametrize("field", HOSTILE_FIELDS)
def test_a_null_field_is_named_by_the_check_that_wants_it(js: JsRuntime, field: str):
    found = js.push(hostile_payload(field, "null"))
    named = [
        one
        for one in found["faults"]
        if one["field"] == field and one["fault"] == "null"
    ]
    assert named, found["faults"]


@pytest.mark.parametrize(
    "field",
    (
        "signal_rows",
        "pair_rows",
        "signal_columns",
        "group_margins_px",
        "splitter_stretch",
    ),
)
def test_a_scalar_where_a_list_belongs_is_named(js: JsRuntime, field: str):
    found = js.push(hostile_payload(field, "number_for_text"))
    named = [
        one
        for one in found["faults"]
        if one["field"] == field and one["fault"] == "not-a-list"
    ]
    assert named, found["faults"]


@pytest.mark.parametrize("field", ("colors", "per_bot_view"))
def test_a_scalar_where_a_bag_belongs_is_named(js: JsRuntime, field: str):
    found = js.push(hostile_payload(field, "number_for_text"))
    named = [
        one
        for one in found["faults"]
        if one["field"] == field and one["fault"] == "not-an-object"
    ]
    assert named, found["faults"]


def test_a_scalar_inside_the_per_bot_order_is_named(js: JsRuntime):
    payload = state_payload("per_bot_signal")
    payload["per_bot_view"]["order"][0] = 12
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "not-a-list"]
    assert named, found["faults"]


def test_a_null_inside_the_per_bot_order_is_named(js: JsRuntime):
    payload = state_payload("per_bot_signal")
    payload["per_bot_view"]["order"][0] = None
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "not-a-list"]
    assert named, found["faults"]


def test_a_scalar_standing_for_a_whole_table_row_is_named(js: JsRuntime):
    payload = state_payload("scanned")
    payload["signal_rows"][0] = 12
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "not-a-list"]
    assert named, found["faults"]
    assert js.answer("signalOrder()")[0] is None


def test_a_cell_that_is_not_a_pair_is_named(js: JsRuntime):
    payload = state_payload("scanned")
    payload["signal_rows"][0][0] = "BTC"
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "cell-shape"]
    assert named, found["faults"]


def test_a_number_where_a_cell_text_belongs_is_named_against_the_placeholder(
    js: JsRuntime,
):
    payload = state_payload("scanned")
    payload["signal_rows"][0][0][0] = 12
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "wrong-type"]
    assert named, found["faults"]
    assert named[0]["detail"] == "number"


def test_a_wrong_type_is_not_named_where_the_surface_names_no_default(js: JsRuntime):
    """A number field is held against something, so this reports nothing."""
    payload = state_payload("scanned")
    payload["adopt_signal_name"] = 12
    found = js.push(payload)
    named = [
        one
        for one in found["faults"]
        if one["field"] == "adopt_signal_name" and one["fault"] == "wrong-type"
    ]
    assert named == []


#: What one hostile value draws in the first cell of the first signal row.
CELL_DRAWS = {
    "missing": "",
    "null": "",
    "number_for_text": "12",
    "text_for_number": "twelve",
    "nan": "",
    "inf": "",
    "negative_inf": "",
    "huge": "1e+24",
    "long_name": "S" * 200,
    "markup": IMAGE_TAG,
}


@pytest.mark.parametrize("kind", sorted(CELL_DRAWS))
def test_a_hostile_cell_value_draws_what_the_report_records(
    browser: Browser, kind: str
):
    payload = state_payload("scanned")
    payload["signal_rows"] = payload["signal_rows"][:1]
    if kind == "missing":
        payload["signal_rows"][0] = []
    elif kind in ("nan", "inf", "negative_inf", "null"):
        payload["signal_rows"][0][0][0] = None
    else:
        payload["signal_rows"][0][0][0] = HOSTILE_VALUES[kind]
    browser.js(WATCH_VIOLATIONS)
    parts = draw_screen(browser, payload)
    drawn = [
        one
        for one in by_part(parts, "grid-cell")
        if one["attrs"]["data-column"] == payload["signal_columns"][0]
        and one["attrs"]["data-table"] == "signals"
    ]
    found = "" if not drawn else drawn[0]["text"]
    assert found == CELL_DRAWS[kind], (kind, found)
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []
    assert browser.js("document.images.length") == 0


def test_a_two_hundred_character_name_is_drawn_whole_and_cut_on_the_right(
    browser: Browser,
):
    long_name = "S" * 200
    payload = state_payload("scanned")
    payload["signal_rows"][0][0][0] = long_name
    parts = draw_screen(browser, payload)
    drawn = [
        one
        for one in by_part(parts, "grid-cell")
        if one["attrs"]["data-column"] == payload["signal_columns"][0]
    ][0]
    assert drawn["text"] == long_name
    assert drawn["style"]["textOverflow"] == "ellipsis"


def test_a_scheduled_fetch_writes_a_connector_the_bridge_cannot_carry():
    """The surface publishes the connectors it handed the scheduler."""
    model = mis.MarketInspectorScreenModel()
    model.set_exchange_source(lambda: {"coinbase": object()}, lambda one: one)
    model.start_fetch()
    assert model.scheduled, "the screen scheduled nothing to publish"
    with pytest.raises(TypeError):
        json.dumps(mis.build_view_model(model))


def test_the_bridge_screen_reaches_no_scheduler_so_that_field_stays_empty():
    """The refusal above needs a wired screen, which the bridge never has."""
    payload = mis.view_model({"reset": True})
    assert payload["exchange_source_wired"] is False
    assert payload["scheduled"] == []
    assert json.dumps(payload)


def test_the_alternating_row_flag_is_published_with_no_colour_behind_it(
    browser: Browser,
):
    """Qt takes the second row colour from the palette, which is unpublished."""
    payload = state_payload("scanned")
    assert payload["table_alternating_rows"] is True
    assert "alternate" not in json.dumps(payload)
    parts = draw_screen(browser, payload)
    rows = [
        one
        for one in by_part(parts, "grid-row")
        if one["attrs"]["data-table"] == "signals"
    ]
    assert [one["attrs"]["data-alternating"] for one in rows] == ["true"] * len(rows)
    assert len({one["style"]["backgroundColor"] for one in rows}) == 1


INHERITED_NAMES = ("constructor", "toString", "hasOwnProperty", "__proto__")


@pytest.mark.parametrize("name", INHERITED_NAMES)
def test_a_row_named_after_a_javascript_member_is_read_by_that_name(
    js: JsRuntime, name: str
):
    payload = state_payload("scanned")
    payload["signal_rows"][0][0][0] = name
    js.push(payload)
    assert js.answer("signalOrder()")[0] == name
    found = js.answer(f"signalRow({json.dumps(name)})")
    assert found[payload["signal_columns"][0]] == [name, ""]


@pytest.mark.parametrize("name", INHERITED_NAMES)
def test_a_row_read_by_an_inherited_name_no_row_carries_answers_nothing(
    js: JsRuntime, name: str
):
    js.push(state_payload("scanned"))
    assert js.answer(f"signalRow({json.dumps(name)})") is None


def test_an_element_named_after_a_javascript_member_is_refused(js: JsRuntime):
    payload = state_payload("per_bot_signal")
    payload["per_bot_view"]["order"][0] = ["constructor", "x", []]
    found = js.push(payload)
    named = [one for one in found["faults"] if one["fault"] == "unknown-element"]
    assert [one["detail"] for one in named] == ["constructor"], found["faults"]
