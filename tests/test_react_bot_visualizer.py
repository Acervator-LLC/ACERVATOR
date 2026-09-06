"""The React Bot Swarm tab, against the surface that describes it."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import bot_swarm_list_surface as bsls
from src.gui.main_tabs import bot_visualizer_surface as bvs
from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "bot_visualizer.js"
TOKENS_PATH = WEB / "design_tokens.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
HEADER_PATH = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: One lock for the whole run, so no worker reads a swapped module.
LOCK_PATH = Path(tempfile.gettempdir()) / "acervator_bot_visualizer_swap.lock"
LOCK_ATTEMPTS = 400_000


@contextlib.contextmanager
def module_held(attempts: int = LOCK_ATTEMPTS):
    """Takes LOCK_PATH so one worker at a time swaps the module."""
    handle = None
    for _ in range(attempts):
        try:
            handle = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            continue
        except PermissionError:
            continue
    if handle is None:
        raise AssertionError(f"{LOCK_PATH} stayed taken for all {attempts} attempts")
    try:
        yield
    finally:
        os.close(handle)
        LOCK_PATH.unlink(missing_ok=True)


with module_held():
    MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500
READY_ROUNDS = 100
READY_STEP_MS = 100
#: How many times open_page reloads the page for the module.
PAGE_ATTEMPTS = 2

#: Wide enough that a never-shown view does not read every width as zero.
HOST_WIDTH_CSS = "1200px"

#: Each Python type name against the JavaScript type the bridge gives it.
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
    {
        "bot_id": "bot-alpha",
        "symbol": "BTC",
        "exchange": "coinbase",
        "stats": {"ytd_folded_usd": 120.5, "ytd_scrummed_usd": 40.25},
    },
    {
        "bot_id": "bot-bravo",
        "symbol": "ETH",
        "exchange": "kraken",
        "stats": {"ytd_folded_usd": 60.0, "ytd_scrummed_usd": 10.0},
    },
    {
        "bot_id": "bot-charlie",
        "symbol": "SOL",
        "exchange": "kraken",
        "stats": {"ytd_folded_usd": 5.0, "ytd_scrummed_usd": 1.0},
    },
]

SIM_RUN_A = "sim-a"
SIM_RUN_B = "sim-b"
PAPER_RUN = "paper-a"
LIVE_RUN = "bot-alpha"

LOAD_FLEET = {"action": "update_bots", "bot_statuses": FLEET}
REGISTER_SIM_A = {
    "action": "register_sim",
    "run_id": SIM_RUN_A,
    "label": "S-A",
    "cfg": {"asset": "BTC/USDT", "timeframe": "1h", "capital": 400, "candle_total": 50},
}
REGISTER_SIM_B = {
    "action": "register_sim",
    "run_id": SIM_RUN_B,
    "label": "S-B",
    "cfg": {"asset": "ETH/USDT", "timeframe": "4h", "capital": 800, "candle_total": 20},
}
REGISTER_PAPER = {
    "action": "register_paper",
    "run_id": PAPER_RUN,
    "cfg": {"pair": "SOL/USDT", "source": "CoinGecko", "capital": 250},
}
REGISTER_LIVE = {
    "action": "register_live",
    "run_id": LIVE_RUN,
    "label": "L-A",
    "cfg": {"pair": "BTC/USD", "timeframe": "5m", "capital": 1000},
}

#: STATES holds every state of the tab the surface can be driven into.
STATES = {
    "empty": [],
    "fleet": [LOAD_FLEET],
    "wired": [
        LOAD_FLEET,
        {
            "action": "wire_created",
            "event": {
                "source_id": "bot-alpha",
                "target_id": "bot-bravo",
                "pct": 25,
            },
        },
        LOAD_FLEET,
    ],
    "sim_running": [
        REGISTER_SIM_A,
        REGISTER_SIM_B,
        {
            "action": "update_sim",
            "run_id": SIM_RUN_A,
            "pnl": 12.5,
            "trades": 3,
            "candle_idx": 25,
        },
    ],
    "sim_stopped": [
        REGISTER_SIM_A,
        {"action": "stop_sim", "run_id": SIM_RUN_A, "pnl": -4.25, "trades": 7},
    ],
    "paper_running": [
        REGISTER_PAPER,
        {"action": "update_paper", "run_id": PAPER_RUN, "pnl": 3.0, "price": 140.5},
    ],
    "live_registered": [LOAD_FLEET, REGISTER_LIVE],
    "masked": [LOAD_FLEET, {"action": "set_masked", "masked": True}, LOAD_FLEET],
    "grid_view": [LOAD_FLEET, {"action": "set_view_mode", "mode": "grid"}],
    "filtered": [LOAD_FLEET, {"action": "set_exchange", "exchange": "kraken"}],
    "themed": [LOAD_FLEET, {"action": "set_theme", "theme_key": "matrix"}],
    "loud": [LOAD_FLEET, {"action": "set_opacity", "pct": 40}],
}
STATE_NAMES = tuple(STATES)
FULL_STATE = "sim_running"


def bridge_payload(calls: list) -> dict:
    """The surface answer for calls, after one round trip through JSON."""
    bvs.view_model({"reset": True})
    payload = bvs.view_model({})
    for one in calls:
        payload = bvs.view_model(one)
    return json.loads(json.dumps(payload, ensure_ascii=True))


def state_payload(name: str) -> dict:
    return bridge_payload(STATES[name])


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):
    """A QJSEngine holding the swarm module and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetBotSwarm"

    def push_mutated(self, payload: Any, mutation: str) -> dict:
        """Pushes one payload after a mutation runs on the parsed model."""
        self.bind_json("PAYLOAD", payload)
        return self.json(
            "(function () { var model = JSON.parse(PAYLOAD); "
            + mutation
            + " return acervatorSetBotSwarm(model); })()"
        )

    def load_tokens(self) -> None:
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_widgets(self) -> None:
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def load_header(self) -> None:
        self.run(HEADER_PATH.read_text(encoding="utf-8"))

    def named(self, answerer: str, name: str) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorBotSwarm." + answerer + "(JSON.parse(NAME))")

    def variable_for(self, value: Any) -> Any:
        self.bind_json("VALUE", value)
        return self.json("acervatorBotSwarm.variableFor(JSON.parse(VALUE))")

    def declarations(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorBotSwarm.declarations(JSON.parse(SHEET))")

    def field(self, name: str) -> Any:
        return self.named("field", name)


@pytest.fixture()
def bare(qapp) -> JsRuntime:
    """A JsRuntime holding the module with no shared module beside it."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def js(bare: JsRuntime) -> JsRuntime:
    bare.load_widgets()
    bare.load_header()
    return bare


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    js.push(state_payload(FULL_STATE))
    return js


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    declared = js.json("acervatorBotSwarm.declaredNames()")
    missing = sorted(set(payload) - set(declared))
    assert not missing, f"{len(missing)} published fields have no answer: {missing}"
    extra = sorted(set(declared) - set(payload))
    assert not extra, f"the module declares fields the surface has none of: {extra}"
    differing = sorted(name for name in payload if js.field(name) != payload[name])
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields "
        f"differ: {differing}"
    )
    assert len(declared) == len(payload)


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["only_on_the_surface"] = []
    js.push(payload)
    declared = js.json("acervatorBotSwarm.declaredNames()")
    assert sorted(set(payload) - set(declared)) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_declares(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload.pop("wires")
    js.push(payload)
    declared = js.json("acervatorBotSwarm.declaredNames()")
    assert sorted(set(declared) - set(payload)) == ["wires"]


def test_the_field_value_check_names_one_changed_field(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["header_title"] = payload["header_title"] + "!"
    js.push(payload)
    shipped = state_payload(FULL_STATE)
    differing = sorted(name for name in shipped if js.field(name) != shipped[name])
    assert differing == ["header_title"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    rows = sum(len(payload[name]) for name in ("live_rows", "sim_rows", "paper_rows"))
    ordered = sum(
        len(payload[name])
        for name in ("live_row_order", "sim_row_order", "paper_row_order")
    )
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["rows"] == rows
    assert report["held"]["rows"] == ordered
    assert report["declared"]["bots"] == len(payload["bot_ids"])
    assert report["held"]["bots"] == len(payload["grid_cells"])
    assert report["declared"]["cells"] == len(payload["column_widths"]) * ordered
    assert report["held"]["cells"] == report["declared"]["cells"]


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    whole = len(payload)
    del payload["wires"]
    report = js.push(payload)
    assert report["declared"]["fields"] == whole
    assert report["held"]["fields"] == whole - 1


def test_a_row_the_order_leaves_out_shortens_only_the_held_row_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["sim_row_order"] = payload["sim_row_order"][:1]
    report = js.push(payload)
    assert report["declared"]["rows"] == report["held"]["rows"] + 1


def test_a_column_a_row_lacks_shortens_only_the_held_cell_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    del payload["sim_rows"][SIM_RUN_A]["feed_lbl"]
    report = js.push(payload)
    assert report["declared"]["cells"] == report["held"]["cells"] + 1


def as_css(value: Any) -> set:
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


SKIN_FIELDS = (
    "style_sheet",
    "text",
    "tooltip",
    "heading_text",
    "description_text",
    "heading_style_sheet",
    "summary_style_sheet",
    "summary_title",
)
SIZE_FIELDS = (
    "outer_margins",
    "outer_spacing",
    "viz_margins",
    "viz_spacing",
    "inner_spacing",
    "layer_margins",
    "layer_spacing",
    "layer_list_margins",
    "layer_list_spacing",
    "summary_margins",
    "summary_spacing",
    "header_spacing",
    "layer_header_spacing",
    "nested_margins",
    "grid_margins",
    "grid_spacing",
    "row_margins",
    "row_spacing",
    "margins",
    "spacing",
    "width",
    "opacity_slider_width_px",
)


def python_declarations(body: str) -> list:
    found = []
    for part in str(body).split(";"):
        head, sep, tail = part.partition(":")
        if sep and head.strip() and tail.strip():
            found.append((head.strip(), tail.strip()))
    return found


def base_body(sheet: str) -> str:
    """The declarations of every block whose selector names no state."""
    bodies = []
    for chunk in str(sheet).split("}"):
        selector, sep, body = chunk.partition("{")
        if not sep:
            if selector.strip():
                bodies.append(chunk)
            continue
        if ":" not in selector:
            bodies.append(body)
    return ";".join(bodies)


def declaration_values(sheet: str) -> set:
    found = set()
    for part in str(base_body(sheet) or sheet).split(";"):
        head, sep, tail = part.partition(":")
        if sep and head.strip():
            found.add(tail.strip())
    found.discard("")
    return found


def tab_values() -> set:
    """Every word, colour, size and sheet the tab paints on screen."""
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in SKIN_FIELDS and isinstance(value, str):
                    found.add(value)
                    found.update(declaration_values(value))
                if key in SIZE_FIELDS:
                    for one in value if isinstance(value, list) else [value]:
                        found.update(as_css(one))
                walk(value)
            return
        if isinstance(node, list):
            for one in node:
                walk(one)

    for name in STATE_NAMES:
        payload = state_payload(name)
        walk(payload)
        for key in (
            "header_title",
            "header_hint",
            "empty_text",
            "privacy_glyph",
            "privacy_mode_text",
            "exchange_caption",
            "theme_caption",
            "view_caption",
            "wires_caption",
            "privacy_dot_tooltip",
            "privacy_mode_tooltip",
            "exchange_tooltip",
            "view_tooltip",
            "opacity_tooltip",
            "revealed_glyph",
            "masked_glyph",
            "mask_text",
            "dot_text",
            "missing_text",
        ):
            found.add(str(payload[key]))
        for key in ("tab_titles", "view_labels"):
            found.update(str(one) for one in payload[key])
        for lines in (payload["sim_summary"], payload["paper_summary"]):
            found.update(str(one) for one in lines.values())
        for sent in payload["rows_sent"]:
            for row in sent:
                found.update(str(one) for one in row.values())
    found.discard("")
    return found


def token_values() -> set:
    found: set = set()
    for value in token_payload()["tokens"].values():
        found |= as_css(value)
    found.discard("")
    return found


def published_strings() -> set:
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                found.add(key)
                walk(value)
            return
        if isinstance(node, list):
            for one in node:
                walk(one)
            return
        if isinstance(node, str):
            found.add(node)

    for name in STATE_NAMES:
        walk(state_payload(name))
    found.discard("")
    return found


def published_keys() -> set:
    found: set = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                found.add(key)
                walk(value)
            return
        if isinstance(node, list):
            for one in node:
                walk(one)

    for name in STATE_NAMES:
        walk(state_payload(name))
    return found


SKIN_VALUES = tab_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
PUBLISHED_KEYS = published_keys()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Published values the module may write because each names a thing.
NAMED_VALUES = sorted(
    {
        "QLabel",
        "QPushButton",
        "QTabWidget",
        "live",
        "sim",
        "paper",
        "list",
        "grid",
        "text",
        "width",
        "kind",
        "wires",
        "bot_visualizer.state",
    }
)


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "bot_visualizer.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"bot_visualizer.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & SKIN_VALUES)
    assert not written, f"bot_visualizer.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"bot_visualizer.js spells out token values: {written}"


def test_every_published_string_the_module_names_is_a_name_not_a_value():
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS
    unnamed = sorted(written - PUBLISHED_KEYS - set(NAMED_VALUES))
    assert not unnamed, f"the module writes published values: {unnamed}"


def test_every_named_value_is_a_name_and_not_a_value_the_tab_shows():
    overlap = sorted(set(NAMED_VALUES) & SKIN_VALUES)
    assert not overlap, f"these named values are painted on screen: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "bot_visualizer.js holds a slash outside a comment, which the scan "
        f"cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES = {
    "colour": 'var written = "#00ffcc";',
    "margin": "var written = " + str(bvs.LAYER_MARGINS[0]) + ";",
    "size_text": 'var written = "' + str(bvs.GRID_SPACING) + 'px";',
    "number": "var written = 12;",
    "header_text": 'var written = "' + bvs.HEADER_TITLE + '";',
    "hint_text": 'var written = "' + bvs.HEADER_HINT + '";',
    "empty_text": 'var written = "' + bvs.EMPTY_TEXT + '";',
    "glyph": 'var written = "' + bvs.REVEALED_GLYPH + '";',
    "mask": 'var written = "' + bvs.MASK_TEXT + '";',
    "tab_sheet": 'var written = "' + bvs.TAB_STYLE_SHEET + '";',
    "dot_sheet": 'var written = "' + bvs.PRIVACY_DOT_STYLE_SHEET + '";',
    "heading": 'var written = "' + bvs.SIM_HEADING_TEXT + '";',
    "button_text": 'var written = "' + bvs.SIM_RUN_ALL_TEXT + '";',
    "tooltip": 'var written = "' + bvs.EXCHANGE_TOOLTIP + '";',
    "token_value": 'var written = "' + str(dss.PRIMARY) + '";',
    "regex": "var written = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which scans report on one written source line."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if found["numbers"]:
        caught.add("number")
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & SKIN_VALUES:
        caught.add("skin_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_value(kind: str):
    caught = caught_by_scan(WRITTEN_LINES[kind])
    assert caught, f"the scan reported nothing on the written {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_the_module_swap_leaves_the_file_whole_whether_or_not_it_is_held_open():
    """Windows denies a replace over an open file where Linux allows it."""
    with module_held():
        original = MODULE_PATH.read_bytes()
        with MODULE_PATH.open("rb") as busy:
            assert busy.read(1), "the module file is empty"
            try:
                swap_module(MODULE_PATH, original, attempts=3)
                denied = False
            except AssertionError:
                denied = True
        assert MODULE_PATH.read_bytes() == original, f"denied {denied}"


def test_the_module_swap_reports_when_every_attempt_is_used_up():
    with module_held():
        original = MODULE_PATH.read_bytes()
        with pytest.raises(AssertionError) as raised:
            swap_module(MODULE_PATH, original, attempts=0)
        assert MODULE_PATH.name in str(raised.value)
        assert MODULE_PATH.read_bytes() == original


def test_the_module_lock_refuses_a_second_taker():
    with module_held():
        with pytest.raises(AssertionError) as raised:
            with module_held(attempts=1):
                raise AssertionError("the second taker was let in")
        assert LOCK_PATH.name in str(raised.value)
    assert not LOCK_PATH.exists()


def scan_each_written_value() -> tuple:
    """Appends each written line to the module and scans it back."""
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
            assert after == before, f"the file was not restored after {kind}"
    finally:
        swap_module(MODULE_PATH, original)
    return caught_each, before


def test_each_written_value_is_caught_in_the_module_file_itself():
    with module_held():
        caught_each, before = scan_each_written_value()
    unseen = sorted(k for k, caught in caught_each.items() if not caught)
    assert not unseen, f"the scan reported nothing on these lines: {unseen}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_written_file_is_still_a_module_the_page_can_run(bare: JsRuntime):
    for kind, line in sorted(WRITTEN_LINES.items()):
        runtime = JsRuntime(bare.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetBotSwarm") == "function", kind


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
    payload = state_payload(state)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json("acervatorBotSwarm.kinds()")
    differing = {
        path: (kind, actual.get(path))
        for path, kind in expected.items()
        if actual.get(path) != kind
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(expected)} values changed "
        f"type: {sorted(differing)}"
    )
    assert sorted(actual) == sorted(expected)


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["grid_spacing"] = str(payload["grid_spacing"])
    js.push(payload)
    expected = python_kinds(state_payload(FULL_STATE))
    actual = js.json("acervatorBotSwarm.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["grid_spacing"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_layers_row_order_and_rows_reach_the_module(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for layer, rows, order in (
        ("live", "live_rows", "live_row_order"),
        ("sim", "sim_rows", "sim_row_order"),
        ("paper", "paper_rows", "paper_row_order"),
    ):
        assert js.named("rowOrder", layer) == payload[order], f"{state}/{layer}"
        assert js.named("rowsOf", layer) == payload[rows], f"{state}/{layer}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_summary_order_reaches_the_module_for_both_layers(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    for layer in ("sim", "paper"):
        chrome = payload["layer_chrome"][layer]
        assert js.named("summaryOf", layer) == {
            "order": chrome["summary_order"],
            "title": chrome["summary_title"],
        }


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_dense_list_rows_reach_the_module(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    sent = payload["rows_sent"]
    expected = sent[-1] if sent else []
    assert js.json("acervatorBotSwarm.listRows()") == expected


def test_the_list_row_check_reads_the_latest_load_and_not_the_first(js: JsRuntime):
    payload = state_payload("fleet")
    payload["rows_sent"] = [[], payload["rows_sent"][-1]]
    js.push(payload)
    assert js.json("acervatorBotSwarm.listRows()") == payload["rows_sent"][-1]
    assert js.json("acervatorBotSwarm.listRows()") != []


def carriers_of(value: Any) -> list:
    tokens = token_payload()
    aliases = tokens["alias_targets"]
    return sorted(
        name
        for name, held in tokens["tokens"].items()
        if str(held) == str(value) and name not in aliases
    )


CARRIED_WIDTH_NAME = "TABLE_COL_DETAIL_W"


def test_the_one_column_width_a_single_token_carries_resolves_to_it(js: JsRuntime):
    js.load_tokens()
    width = state_payload(FULL_STATE)["column_widths"]["feed"]
    assert carriers_of(width) == [CARRIED_WIDTH_NAME]
    assert js.variable_for(width) == CARRIED_WIDTH_NAME


@pytest.mark.parametrize("field", ["viz_spacing", "layer_spacing", "grid_spacing"])
def test_no_layout_gap_the_tab_uses_borrows_a_token_from_another_group(
    js: JsRuntime, field: str
):
    """A gap borrows only from spacing, so a radius carrying six is refused."""
    js.load_tokens()
    value = state_payload(FULL_STATE)[field]
    assert js.json("acervatorBotSwarm.spaceGroups()") == ["spacing"]
    js.bind_json("VALUE", value)
    js.bind_json("GROUPS", ["spacing"])
    borrowed = js.json(
        "acervatorBotSwarm.variableInGroups(JSON.parse(VALUE), JSON.parse(GROUPS))"
    )
    assert borrowed is None, f"{value} borrowed {borrowed}"
    assert js.json("acervatorBotSwarm.length(JSON.parse(VALUE))") == str(value) + "px"


def test_the_gap_group_check_reads_a_number_the_spacing_group_does_carry(
    js: JsRuntime,
):
    """Proves variableInGroups answers when a spacing token carries the number."""
    js.load_tokens()
    carried = token_payload()["groups"]["spacing"]["SPACE_XXL"]
    assert carriers_of(carried) == ["SPACE_XXL"]
    js.bind_json("VALUE", carried)
    js.bind_json("GROUPS", ["spacing"])
    assert (
        js.json(
            "acervatorBotSwarm.variableInGroups(JSON.parse(VALUE), JSON.parse(GROUPS))"
        )
        == "SPACE_XXL"
    )


def test_a_value_no_token_carries_resolves_to_none(js: JsRuntime):
    js.load_tokens()
    assert js.variable_for("no-token-carries-this") is None


def test_the_resolver_reports_no_name_with_the_widget_module_off_the_page(
    bare: JsRuntime,
):
    bare.load_tokens()
    assert bare.variable_for(str(dss.PRIMARY)) is None


def tab_sheets(payload: dict) -> list:
    found = [
        payload["empty_style_sheet"],
        payload["privacy_dot_style_sheet"],
        payload["privacy_mode_style_sheet"],
        payload["description_style_sheet"],
        payload["scroll_style_sheet"],
        payload["swarm_list_style_sheet"],
        payload["summary_label_style_sheet"],
    ]
    for layer in ("sim", "paper"):
        chrome = payload["layer_chrome"][layer]
        found.append(chrome["heading_style_sheet"])
        for button in chrome["buttons"]:
            found.append(button["style_sheet"])
    for handle in payload["sim_rows"].values():
        found.append(handle["widget"]["style_sheet"])
        found.append(handle["id_lbl"]["style_sheet"])
    return found


def test_the_module_reads_the_same_declarations_as_the_surface_wrote(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    for sheet in tab_sheets(payload):
        expected = [
            {"property": name, "value": value}
            for name, value in python_declarations(base_body(sheet))
        ]
        assert js.declarations(sheet) == expected, f"declarations differ for {sheet}"


def test_the_module_names_a_sheet_it_cannot_read(bare: JsRuntime):
    report = bare.push(state_payload(FULL_STATE))
    assert {
        "where": None,
        "field": "style_sheet",
        "fault": "no-sheet-source",
        "detail": None,
    } in report["faults"]


def test_the_sheet_source_check_is_quiet_with_the_header_module_loaded(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    kinds = [f["fault"] for f in report["faults"]]
    assert "no-sheet-source" not in kinds


def test_the_module_names_the_absent_theme_name_source(js: JsRuntime):
    """The theme picker shows a theme key until visualizer_themes lands."""
    report = js.push(state_payload(FULL_STATE))
    assert {
        "where": None,
        "field": "theme_keys",
        "fault": "no-theme-source",
        "detail": None,
    } in report["faults"]
    assert js.named("themeLabel", "matrix") == "matrix"


def test_the_theme_name_source_check_is_quiet_once_a_namer_is_present(js: JsRuntime):
    js.run(
        "window.acervatorVisualizerThemes = { themeDisplayName: "
        "function (key) { return key.toUpperCase(); } };"
    )
    report = js.push(state_payload(FULL_STATE))
    kinds = [f["fault"] for f in report["faults"]]
    assert "no-theme-source" not in kinds
    assert js.named("themeLabel", "matrix") == "MATRIX"


def test_no_sheet_this_tab_paints_carries_a_colour_css_reads_differently():
    """No sheet holds an eight-digit hex or a byte alpha."""
    for name in STATE_NAMES:
        for sheet in tab_sheets(state_payload(name)):
            assert not re.search(r"#[0-9a-fA-F]{8}\b", str(sheet)), sheet
            assert "rgba(" not in str(sheet), sheet


def test_the_colour_refusal_names_an_eight_digit_hex(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["privacy_dot_style_sheet"] = "QLabel{color:#80ff00cc;}"
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "qt-colour"]
    assert named, "the module named no eight-digit colour"
    assert named[0]["detail"] == "AARRGGBB"


def test_the_colour_refusal_names_a_byte_alpha(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["swarm_list_style_sheet"] = "background:rgba(1,2,3,128);"
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "qt-colour"]
    assert named, "the module named no byte alpha"
    assert named[0]["detail"] == "rgba("


def test_the_colour_refusal_is_quiet_on_a_shipped_payload(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    named = [f for f in report["faults"] if f["fault"] == "qt-colour"]
    assert named == [], f"a shipped colour was refused: {named}"


def test_a_refused_colour_is_left_out_of_the_style_the_module_paints(js: JsRuntime):
    kept = js.named("keptSheet", "QLabel{color:#80ff00cc;background:#101010;}")
    assert "#80ff00cc" not in kept
    assert "#101010" in kept


class Browser:
    """The renderer page loaded from disk into a Chromium view."""

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
                if self.js("typeof window.acervatorSetBotSwarm") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the swarm module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
            + ", tokens "
            + str(self.js("typeof window.acervatorSetTokens"))
            + ", header "
            + str(self.js("typeof window.acervatorHeader"))
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
    """A Browser page, or a skip where Chromium ships with no Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


STYLE_NAMES = [
    "display",
    "flexDirection",
    "alignItems",
    "justifyContent",
    "flexGrow",
    "rowGap",
    "columnGap",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "color",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "fontFamily",
    "whiteSpace",
    "overflowX",
    "overflowY",
    "userSelect",
    "cursor",
    "textAlign",
    "width",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderTopLeftRadius",
]

#: EXPANDED holds each Qt shorthand against the computed names it settles into.
EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "background": ("backgroundColor",),
    "background-color": ("backgroundColor",),
    "border-radius": ("borderTopLeftRadius",),
    "font-size": ("fontSize",),
    "font-weight": ("fontWeight",),
    "font-family": ("fontFamily",),
    "color": ("color",),
}

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

PAGE_HELPERS = (
    "window.HOST = document.getElementById('swarm-host');"
    "if (window.HOST === null) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'swarm-host';"
    "  document.body.appendChild(window.HOST); }"
    "window.HOST.style.width = " + json.dumps(HOST_WIDTH_CSS) + ";"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeStyle = function (cssText, names) {"
    "  var probe = document.createElement('div');"
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
    "        width: el.clientWidth, height: el.clientHeight,"
    "        room: el.scrollWidth, text: own, html: el.innerHTML,"
    "        children: el.children.length,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
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


def draw_tab(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetBotSwarm(JSON.parse(window.PAYLOAD));"
        "acervatorBotSwarm.renderTab(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    return json.loads(browser.js(READ_PARTS))


def probe(browser: Browser, body: str) -> dict:
    """The computed values a bare element takes from one declaration body."""
    names: list = []
    for prop, _ in python_declarations(body):
        names.extend(EXPANDED.get(prop, (prop,)))
    if not names:
        return {}
    return browser.parsed(
        "window.probeStyle("
        + json.dumps(body)
        + ", "
        + json.dumps(sorted(set(names)))
        + ")"
    )


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def sheet_agrees(drawn: dict, expected: dict, where: str) -> None:
    assert expected, f"{where}: the probe took no value, so this compares nothing"
    differing = {
        name: (value, drawn["style"].get(name))
        for name, value in expected.items()
        if drawn["style"].get(name) != value
    }
    assert not differing, (
        f"{where}: {len(differing)} of {len(expected)} declared values "
        f"differ from the surface's own: {differing}"
    )


TAB = "tab"
TAB_BAR = "tab/tab-bar"
TAB_BUTTON = "tab/tab-bar/tab-button"
TAB_BODY = "tab/tab-body"
SWARM_PANE = "tab/tab-body/swarm-pane"
HEADER_ROW = SWARM_PANE + "/header-row"
HEADER_TITLE = HEADER_ROW + "/header-title"
HEADER_HINT = HEADER_ROW + "/header-hint"
PRIVACY_DOT = HEADER_ROW + "/privacy-dot"
PRIVACY_MODE = HEADER_ROW + "/privacy-mode"
EXCHANGE_SELECT = HEADER_ROW + "/exchange-select"
THEME_SELECT = HEADER_ROW + "/theme-select"
VIEW_SELECT = HEADER_ROW + "/view-select"
OPACITY_SLIDER = HEADER_ROW + "/opacity-slider"
INNER_ROW = SWARM_PANE + "/inner-row"
VIEW_STACK = INNER_ROW + "/view-stack"
LIST_PAGE = VIEW_STACK + "/list-page"
LIST_MOUNT = LIST_PAGE + "/bot-swarm-list"
LIST_SWARM = LIST_MOUNT + "/swarm"
LIST_TABLE = LIST_SWARM + "/list"
LIST_HEAD_ROW = LIST_TABLE + "/head-row"
LIST_HEADER = LIST_HEAD_ROW + "/header"
LIST_ROW = LIST_TABLE + "/row"
LIST_CELL = LIST_ROW + "/cell"
LANE_SHEET = LIST_SWARM + "/sheet"
TICKER_COLUMN = str(bsls.COL_TICKER)
GRID_PAGE = VIEW_STACK + "/grid-page"
LOCUST = GRID_PAGE + "/locust"
EMPTY = GRID_PAGE + "/empty"
WIRE_CANVAS = GRID_PAGE + "/wire-canvas"
LANE_CANVAS = LIST_PAGE + "/lane-canvas"
QUICK_ROUTING = INNER_ROW + "/quick-routing"
LIVE_ROWS = SWARM_PANE + "/live-rows"
SIM_PANE = "tab/tab-body/layer-pane"
SIM_HEADER = SIM_PANE + "/layer-header"
SIM_HEADING = SIM_HEADER + "/layer-heading"
SIM_BUTTON = SIM_HEADER + "/layer-button"
SIM_DESCRIPTION = SIM_PANE + "/layer-description"
SIM_SCROLL = SIM_PANE + "/layer-scroll"
SIM_LIST = SIM_SCROLL + "/layer-list"
SWARM_ROW = SIM_LIST + "/swarm-row"
SWARM_CELL = SWARM_ROW + "/swarm-cell"
SUMMARY = SIM_PANE + "/summary"
SUMMARY_LINE = SUMMARY + "/summary-line"

EXPECTED_PARTS = (
    TAB,
    TAB_BAR,
    TAB_BUTTON,
    TAB_BODY,
    SWARM_PANE,
    HEADER_ROW,
    HEADER_TITLE,
    HEADER_HINT,
    PRIVACY_DOT,
    PRIVACY_MODE,
    EXCHANGE_SELECT,
    THEME_SELECT,
    VIEW_SELECT,
    OPACITY_SLIDER,
    INNER_ROW,
    VIEW_STACK,
    LIST_PAGE,
    LIST_MOUNT,
    LIST_SWARM,
    LIST_TABLE,
    LIST_HEAD_ROW,
    LIST_HEADER,
    LIST_ROW,
    LIST_CELL,
    LANE_SHEET,
    GRID_PAGE,
    LOCUST,
    WIRE_CANVAS,
    LANE_CANVAS,
    QUICK_ROUTING,
    LIVE_ROWS,
    SIM_PANE,
    SIM_HEADER,
    SIM_HEADING,
    SIM_BUTTON,
    SIM_DESCRIPTION,
    SIM_SCROLL,
    SIM_LIST,
    SWARM_ROW,
    SWARM_CELL,
    SUMMARY,
    SUMMARY_LINE,
)

#: Each mount path another unit owns against its own slot name.
MOUNT_PARTS = {
    LIST_MOUNT: "bot-swarm-list",
    LOCUST: "locust",
    WIRE_CANVAS: "wire-canvas",
    QUICK_ROUTING: "quick-routing",
}


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    policy = browser.js(
        "document.querySelector('meta[http-equiv=\"Content-Security-Policy\"]')"
        ".getAttribute('content')"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorBotSwarm") == "object"
    assert browser.js("typeof window.acervatorSetBotSwarm") == "function"
    assert browser.js("typeof window.acervatorLoadBotSwarm") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_tab(browser, state_payload(FULL_STATE))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_page_refuses_a_network_call_when_one_is_made(browser: Browser):
    """Proves the named-child check reports a child the tab does not draw."""
    browser.js(WATCH_VIOLATIONS)
    browser.js(
        "window.PROBE = null;"
        "try { fetch('https://example.invalid/x')"
        "  .then(function () { window.PROBE = 'allowed'; })"
        "  .catch(function (e) { window.PROBE = 'refused: ' + e.name; }); }"
        "catch (e) { window.PROBE = 'refused: ' + e.name; }"
    )
    browser.settle(NETWORK_SETTLE_MS)
    assert str(browser.js("window.PROBE")).startswith("refused")


def drawn_state(browser: Browser) -> list:
    payload = state_payload(FULL_STATE)
    payload["sim_row_order"] = payload["sim_row_order"]
    return draw_tab(browser, payload)


def test_the_drawn_tab_names_every_child_a_check_reads(browser: Browser):
    payload = state_payload(FULL_STATE)
    payload["bot_ids"] = state_payload("fleet")["bot_ids"]
    payload["grid_cells"] = state_payload("fleet")["grid_cells"]
    payload["rows_sent"] = state_payload("fleet")["rows_sent"]
    payload["swarm_list"] = state_payload("fleet")["swarm_list"]
    payload["live_rows"] = state_payload("live_registered")["live_rows"]
    payload["live_row_order"] = state_payload("live_registered")["live_row_order"]
    parts = draw_tab(browser, payload)
    drawn = {one["path"] for one in parts}
    missing = sorted(set(EXPECTED_PARTS) - drawn)
    assert not missing, f"{len(missing)} named children were not drawn: {missing}"


def test_the_named_child_check_reports_a_child_that_is_not_drawn(browser: Browser):
    parts = draw_tab(browser, state_payload("empty"))
    drawn = {one["path"] for one in parts}
    assert LIST_ROW not in drawn, "an empty fleet still drew a list row"
    assert TAB in drawn


def test_each_mount_another_unit_owns_is_drawn_empty_and_named(browser: Browser):
    payload = state_payload(FULL_STATE)
    payload["bot_ids"] = state_payload("fleet")["bot_ids"]
    payload["grid_cells"] = state_payload("fleet")["grid_cells"]
    parts = draw_tab(browser, payload)
    for path, slot in MOUNT_PARTS.items():
        found = at_path(parts, path)
        assert found, f"{path} was not drawn"
        for one in found:
            assert one["attrs"]["data-slot"] == slot
            if path is not LIST_MOUNT:
                assert one["html"] == "", f"{path} is not an empty host"


def test_the_empty_message_is_drawn_only_when_no_bot_is_placed(browser: Browser):
    parts = draw_tab(browser, state_payload("empty"))
    assert at_path(parts, EMPTY), "the empty message was not drawn"
    parts = draw_tab(browser, state_payload("fleet"))
    assert not at_path(parts, EMPTY), "the empty message was drawn beside bots"


def test_the_drawn_privacy_dot_takes_the_skin_the_surface_declares(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = base_body(payload["privacy_dot_style_sheet"])
    sheet_agrees(only(parts, PRIVACY_DOT), probe(browser, body), PRIVACY_DOT)


def test_the_drawn_privacy_button_takes_the_skin_the_surface_declares(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = base_body(payload["privacy_mode_style_sheet"])
    sheet_agrees(only(parts, PRIVACY_MODE), probe(browser, body), PRIVACY_MODE)


def test_the_drawn_layer_heading_takes_the_skin_the_surface_declares(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = base_body(payload["layer_chrome"]["sim"]["heading_style_sheet"])
    sheet_agrees(at_path(parts, SIM_HEADING)[0], probe(browser, body), SIM_HEADING)


def test_the_drawn_description_takes_the_skin_the_surface_declares(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = base_body(payload["description_style_sheet"])
    sheet_agrees(
        at_path(parts, SIM_DESCRIPTION)[0], probe(browser, body), SIM_DESCRIPTION
    )


def test_the_drawn_swarm_row_takes_the_frame_skin_the_surface_declares(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    handle = payload["sim_rows"][payload["sim_row_order"][0]]
    body = base_body(handle["widget"]["style_sheet"])
    sheet_agrees(at_path(parts, SWARM_ROW)[0], probe(browser, body), SWARM_ROW)


def test_the_drawn_cell_takes_the_skin_its_own_column_declares(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    handle = payload["sim_rows"][payload["sim_row_order"][0]]
    cells = [
        one
        for one in at_path(parts, SWARM_CELL)
        if one["attrs"]["data-column"] == "id_lbl"
    ]
    assert cells, "no identifier cell was drawn"
    body = base_body(handle["id_lbl"]["style_sheet"])
    sheet_agrees(cells[0], probe(browser, body), SWARM_CELL)


def test_the_skin_check_reports_a_probe_that_took_no_value(browser: Browser):
    """Proves sheet_agrees refuses a probe that took no declared value."""
    parts = draw_tab(browser, state_payload(FULL_STATE))
    with pytest.raises(AssertionError) as raised:
        sheet_agrees(only(parts, PRIVACY_DOT), probe(browser, ""), PRIVACY_DOT)
    assert "compares nothing" in str(raised.value)


def test_the_skin_check_reports_a_drawn_value_the_surface_did_not_declare(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = base_body(payload["privacy_dot_style_sheet"])
    changed = probe(browser, body)
    key = sorted(changed)[0]
    changed[key] = "rgb(1, 2, 3)"
    with pytest.raises(AssertionError) as raised:
        sheet_agrees(only(parts, PRIVACY_DOT), changed, PRIVACY_DOT)
    assert key in str(raised.value)


def pixels(value: Any) -> str:
    return str(value) + "px"


def test_every_layout_gap_the_surface_publishes_is_the_one_drawn(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    pairs = [
        (TAB, payload["outer_spacing"], payload["outer_margins"]),
        (SWARM_PANE, payload["viz_spacing"], payload["viz_margins"]),
        (HEADER_ROW, payload["header_spacing"], payload["nested_margins"]),
        (INNER_ROW, payload["inner_spacing"], payload["nested_margins"]),
        (SIM_PANE, payload["layer_spacing"], payload["layer_margins"]),
        (SIM_LIST, payload["layer_list_spacing"], payload["layer_list_margins"]),
        (SUMMARY, payload["summary_spacing"], payload["summary_margins"]),
        (SIM_HEADER, payload["layer_header_spacing"], payload["nested_margins"]),
    ]
    for path, gap, margins in pairs:
        drawn = at_path(parts, path)[0]
        assert drawn["style"]["rowGap"] == pixels(gap), path
        assert drawn["style"]["columnGap"] == pixels(gap), path
        for side, value in zip(
            ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"), margins
        ):
            assert drawn["style"][side] == pixels(value), f"{path}/{side}"


def test_the_layout_gap_check_reads_a_changed_gap(browser: Browser):
    payload = state_payload(FULL_STATE)
    was = payload["layer_spacing"]
    payload["layer_spacing"] = was + 7
    parts = draw_tab(browser, payload)
    drawn = at_path(parts, SIM_PANE)[0]
    assert drawn["style"]["rowGap"] == pixels(was + 7)
    assert drawn["style"]["rowGap"] != pixels(was)


def test_the_grid_takes_the_margins_and_gap_the_surface_publishes(browser: Browser):
    payload = state_payload("fleet")
    parts = draw_tab(browser, payload)
    drawn = only(parts, GRID_PAGE)
    assert drawn["style"]["rowGap"] == pixels(payload["grid_spacing"])
    for side, value in zip(
        ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
        payload["grid_margins"],
    ):
        assert drawn["style"][side] == pixels(value)


def token_width_of(browser: Browser, parts: list) -> str:
    cells = [
        one
        for one in at_path(parts, SWARM_CELL)
        if one["attrs"]["data-column"] == "feed_lbl"
    ]
    assert cells, "no feed cell was drawn"
    assert browser is not None
    return cells[0]["style"]["width"]


def rewrite_token(browser: Browser, name: str, value: Any) -> None:
    browser.js(
        "document.documentElement.style.setProperty("
        + json.dumps("--" + name)
        + ", "
        + json.dumps(str(value))
        + ");"
    )


def test_the_feed_column_width_follows_the_token_that_carries_it(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    width = payload["column_widths"]["feed"]
    assert token_width_of(browser, parts) == pixels(width)
    rewrite_token(browser, CARRIED_WIDTH_NAME, width + 33)
    after = read_parts(browser)
    assert token_width_of(browser, after) == pixels(width + 33)


def test_rewriting_that_token_moves_no_other_drawn_value(browser: Browser):
    payload = state_payload(FULL_STATE)
    before = draw_tab(browser, payload)
    width = payload["column_widths"]["feed"]
    rewrite_token(browser, CARRIED_WIDTH_NAME, width + 33)
    after = read_parts(browser)
    assert len(before) == len(after)
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for name, value in one["style"].items():
            if other["style"].get(name) != value:
                moved.add((one["path"], one["attrs"].get("data-column"), name))
    carried = {name for name, held in payload["column_widths"].items() if held == width}
    assert len(carried) > 1, f"only {carried} carries {width}"
    assert moved == {
        (SWARM_CELL, name + "_lbl", "width") for name in ("feed", "status")
    }, f"{sorted(moved)}"


def test_rewriting_a_token_no_drawn_value_borrows_moves_nothing(browser: Browser):
    """Proves an unborrowed token rewrite moves no drawn part."""
    payload = state_payload(FULL_STATE)
    before = draw_tab(browser, payload)
    rewrite_token(browser, "SPACE_XL", 999)
    after = read_parts(browser)
    moved = [
        one["path"]
        for at, one in enumerate(before)
        if one["style"] != after[at]["style"]
    ]
    assert moved == [], f"parts followed a token they do not borrow: {moved}"


def test_no_label_the_tab_draws_can_be_dragged_over(browser: Browser):
    """Every drawn label refuses a drag selection as a Qt label does."""
    parts = draw_tab(browser, state_payload(FULL_STATE))
    labelled = (
        HEADER_TITLE,
        HEADER_HINT,
        PRIVACY_DOT,
        SIM_HEADING,
        SIM_DESCRIPTION,
        SWARM_CELL,
        SUMMARY_LINE,
    )
    for path in labelled:
        found = at_path(parts, path)
        assert found, f"{path} was not drawn"
        for one in found:
            assert one["style"]["userSelect"] == "none", path


def test_the_drag_selection_check_reads_a_selectable_element(browser: Browser):
    """Proves the userSelect probe reads a selectable element too."""
    browser.js(PAGE_HELPERS)
    found = browser.parsed('window.probeStyle("", ["userSelect"])')
    assert found["userSelect"] != "none"


def test_no_row_column_wraps_because_a_qt_label_clips_instead(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    for one in at_path(parts, SWARM_CELL):
        assert one["style"]["whiteSpace"] == "nowrap", one["attrs"]["data-column"]
        assert one["style"]["overflowX"] == "hidden"


def test_the_description_wraps_because_qt_sets_word_wrap_there(browser: Browser):
    payload = state_payload(FULL_STATE)
    assert payload["description_word_wrap"] is True
    assert payload["label_word_wrap"] is False
    parts = draw_tab(browser, payload)
    assert at_path(parts, SIM_DESCRIPTION)[0]["style"]["whiteSpace"] == "normal"


def test_the_wrap_check_reads_the_surfaces_own_flag(browser: Browser):
    payload = state_payload(FULL_STATE)
    payload["description_word_wrap"] = False
    parts = draw_tab(browser, payload)
    assert at_path(parts, SIM_DESCRIPTION)[0]["style"]["whiteSpace"] == "nowrap"


def test_the_privacy_dot_carries_the_pointing_cursor_qt_gives_it(browser: Browser):
    payload = state_payload(FULL_STATE)
    assert payload["dot_cursor"] == "PointingHandCursor"
    parts = draw_tab(browser, payload)
    assert only(parts, PRIVACY_DOT)["style"]["cursor"] == "pointer"


def test_the_cursor_check_reads_a_part_with_no_cursor_rule(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    assert only(parts, HEADER_TITLE)["style"]["cursor"] != "pointer"


def test_the_layer_rows_scroll_because_qt_puts_them_in_a_scroll_area(
    browser: Browser,
):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    drawn = at_path(parts, SIM_SCROLL)[0]
    assert drawn["style"]["overflowY"] == "auto"


def test_the_grid_does_not_scroll_because_qt_gives_it_no_scroll_area(
    browser: Browser,
):
    parts = draw_tab(browser, state_payload("fleet"))
    assert only(parts, GRID_PAGE)["style"]["overflowY"] != "auto"


FOCUSABLE = (
    TAB_BUTTON,
    PRIVACY_MODE,
    EXCHANGE_SELECT,
    THEME_SELECT,
    VIEW_SELECT,
    OPACITY_SLIDER,
    SIM_BUTTON,
)


def test_every_strong_focus_widget_qt_draws_takes_the_keyboard(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    tags = {"BUTTON", "SELECT", "INPUT"}
    for path in FOCUSABLE:
        found = at_path(parts, path)
        assert found, f"{path} was not drawn"
        for one in found:
            assert one["tag"] in tags, f"{path} is a {one['tag']}"


def test_no_label_the_tab_draws_takes_the_keyboard(browser: Browser):
    """No drawn label is a button because a Qt label takes no focus."""
    parts = draw_tab(browser, state_payload(FULL_STATE))
    for path in (HEADER_TITLE, HEADER_HINT, SWARM_CELL, SUMMARY_LINE):
        for one in at_path(parts, path):
            assert one["tag"] in {"SPAN", "DIV"}, f"{path} is a {one['tag']}"


def test_the_focus_order_follows_the_order_qt_adds_the_widgets(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    order = [one["path"] for one in parts if one["path"] in set(FOCUSABLE)]
    inside = [one for one in order if one != TAB_BUTTON and one != SIM_BUTTON]
    assert inside == [
        PRIVACY_MODE,
        EXCHANGE_SELECT,
        THEME_SELECT,
        VIEW_SELECT,
        OPACITY_SLIDER,
    ], inside


def test_the_tab_button_carries_the_hover_rule_qt_paints(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    before = at_path(parts, TAB_BUTTON)[1]["style"]["color"]
    browser.js(
        "(function () {"
        "  var nodes = window.HOST.querySelectorAll('[data-part=\"tab-button\"]');"
        "  var one = nodes[1];"
        "  var e = new MouseEvent('mouseover', { bubbles: true });"
        "  one.dispatchEvent(e); })()"
    )
    browser.settle(SETTLE_MS)
    after = read_parts(browser)
    hovered = at_path(after, TAB_BUTTON)[1]
    assert hovered["attrs"]["data-hovered"] == "true"
    assert hovered["style"]["color"] != before


def test_the_layer_button_carries_the_hover_rule_qt_paints(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    before = at_path(parts, SIM_BUTTON)[0]["style"]["backgroundColor"]
    browser.js(
        "(function () {"
        "  var one = window.HOST.querySelector('[data-part=\"layer-button\"]');"
        "  one.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })); })()"
    )
    browser.settle(SETTLE_MS)
    after = read_parts(browser)
    hovered = at_path(after, SIM_BUTTON)[0]
    assert hovered["attrs"]["data-hovered"] == "true"
    assert hovered["style"]["backgroundColor"] != before


def test_the_hover_check_reads_an_unhovered_button(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    assert at_path(parts, SIM_BUTTON)[0]["attrs"]["data-hovered"] == "false"


def test_a_click_on_the_dot_sends_the_action_the_surface_names(browser: Browser):
    draw_tab(browser, state_payload(FULL_STATE))
    browser.js(
        "(function () {"
        "  var one = window.HOST.querySelector('[data-part=\"privacy-dot\"]');"
        "  one.dispatchEvent(new MouseEvent('click', { bubbles: true })); })()"
    )
    browser.settle(SETTLE_MS)
    sent = browser.parsed("acervatorBotSwarm.sent()")
    assert [one["action"] for one in sent] == ["set_masked"]


def test_a_click_on_the_privacy_button_sends_the_action_the_surface_names(
    browser: Browser,
):
    draw_tab(browser, state_payload(FULL_STATE))
    browser.js(
        "(function () {"
        "  var one = window.HOST.querySelector('[data-part=\"privacy-mode\"]');"
        "  one.dispatchEvent(new MouseEvent('click', { bubbles: true })); })()"
    )
    browser.settle(SETTLE_MS)
    sent = browser.parsed("acervatorBotSwarm.sent()")
    assert [one["action"] for one in sent] == ["toggle_privacy_mode"]


def test_the_click_check_reads_no_action_before_a_click(browser: Browser):
    draw_tab(browser, state_payload(FULL_STATE))
    assert browser.parsed("acervatorBotSwarm.sent()") == []


def test_clicking_a_tab_button_shows_that_pane_and_hides_the_others(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    assert only(parts, SWARM_PANE)["attrs"]["data-current"] == "true"
    browser.js(
        "(function () {"
        "  var nodes = window.HOST.querySelectorAll('[data-part=\"tab-button\"]');"
        "  nodes[1].dispatchEvent(new MouseEvent('click', { bubbles: true })); })()"
    )
    browser.settle(SETTLE_MS)
    after = read_parts(browser)
    assert only(after, SWARM_PANE)["attrs"]["data-current"] == "false"
    assert at_path(after, SIM_PANE)[0]["attrs"]["data-current"] == "true"


def test_the_tab_click_check_reads_the_starting_tab(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    assert at_path(parts, SIM_PANE)[0]["attrs"]["data-current"] == "false"


def test_the_grid_draws_one_locust_per_bot_in_the_order_the_fleet_gives(
    browser: Browser,
):
    payload = state_payload("fleet")
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, LOCUST)]
    assert drawn == payload["bot_ids"], f"the grid drew {drawn}"


def test_the_grid_order_check_names_a_reordered_fleet(browser: Browser):
    payload = state_payload("fleet")
    shipped = list(payload["bot_ids"])
    payload["bot_ids"] = list(reversed(shipped))
    payload["grid_cells"] = [
        [bot, cell[1], cell[2]]
        for bot, cell in zip(payload["bot_ids"], payload["grid_cells"])
    ]
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, LOCUST)]
    assert drawn != shipped, "the check did not see the reorder"
    assert drawn == list(reversed(shipped))


def test_the_grid_places_each_bot_in_the_row_and_column_the_surface_gives(
    browser: Browser,
):
    payload = state_payload("fleet")
    parts = draw_tab(browser, payload)
    placed = {
        one["attrs"]["data-key"]: (
            one["attrs"]["data-row"],
            one["attrs"]["data-column"],
        )
        for one in at_path(parts, LOCUST)
    }
    expected = {
        cell[0]: (str(cell[1] + 1), str(cell[2] + 1)) for cell in payload["grid_cells"]
    }
    assert placed == expected


def test_the_grid_place_check_names_a_moved_bot(browser: Browser):
    payload = state_payload("fleet")
    payload["grid_cells"][1] = [payload["grid_cells"][1][0], 5, 5]
    parts = draw_tab(browser, payload)
    moved = [
        one
        for one in at_path(parts, LOCUST)
        if one["attrs"]["data-row"] == "6" and one["attrs"]["data-column"] == "6"
    ]
    assert len(moved) == 1, "the check did not see the moved bot"


def reversed_list(payload: dict) -> dict:
    """``payload`` with the list module's rows and bot ids back to front."""
    held = payload["swarm_list"]
    held["rows"] = list(reversed(held["rows"]))
    held["bot_ids"] = list(reversed(held["bot_ids"]))
    return payload


def test_the_dense_list_draws_one_row_per_bot_in_the_order_the_fleet_gives(
    browser: Browser,
):
    payload = state_payload("fleet")
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-bot-id"] for one in at_path(parts, LIST_ROW)]
    assert drawn == [row["bot_id"] for row in payload["rows_sent"][-1]]


def test_the_list_order_check_names_a_reordered_list(browser: Browser):
    payload = state_payload("fleet")
    shipped = [row["bot_id"] for row in payload["rows_sent"][-1]]
    parts = draw_tab(browser, reversed_list(payload))
    drawn = [one["attrs"]["data-bot-id"] for one in at_path(parts, LIST_ROW)]
    assert drawn != shipped
    assert drawn == list(reversed(shipped))


def js_text(value: Any) -> str:
    """How JavaScript prints one value the bridge carried across."""
    if isinstance(value, bool) or not isinstance(value, float):
        return str(value)
    return str(int(value)) if value.is_integer() else str(value)


def cells_at(parts: list, path: str, key: str) -> dict:
    """Every drawn cell of one row, by the column it names."""
    return {
        one["attrs"]["data-column"]: one["text"]
        for one in at_path(parts, path)
        if one["attrs"]["data-key"] == key
    }


def cells_by_row(parts: list, columns: int) -> list:
    """Every drawn list cell's text, cut into one list per row."""
    drawn = [one["text"] for one in at_path(parts, LIST_CELL)]
    return [drawn[at : at + columns] for at in range(0, len(drawn), columns)]


def written_cells(payload: dict) -> list:
    """The cell text the list surface wrote, one list per row."""
    return [
        ["" if one is None else one["text"] for one in row]
        for row in payload["swarm_list"]["rows"]
    ]


def test_the_list_cells_carry_the_values_the_surface_wrote_for_that_bot(
    browser: Browser,
):
    payload = state_payload("fleet")
    parts = draw_tab(browser, payload)
    drawn = cells_by_row(parts, payload["swarm_list"]["total_cols"])
    assert drawn == written_cells(payload), f"drawn {drawn}"


def test_the_list_value_check_names_two_bots_whose_values_were_swapped(
    browser: Browser,
):
    payload = state_payload("fleet")
    was = cells_by_row(draw_tab(browser, payload), payload["swarm_list"]["total_cols"])
    rows = payload["swarm_list"]["rows"]
    at = bsls.COL_INFLOW
    rows[0][at]["text"], rows[1][at]["text"] = (
        rows[1][at]["text"],
        rows[0][at]["text"],
    )
    now = cells_by_row(draw_tab(browser, payload), payload["swarm_list"]["total_cols"])
    moved = sorted(index for index in range(len(was)) if was[index] != now[index])
    assert moved == [0, 1], f"moved {moved}"
    assert len(was) == len(now), "the swap moved a row as well as its values"


def test_the_layer_rows_are_drawn_in_the_order_the_surface_publishes(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, SWARM_ROW)]
    assert drawn == payload["sim_row_order"]


def test_the_layer_row_order_check_names_a_reordered_layer(browser: Browser):
    payload = state_payload(FULL_STATE)
    shipped = list(payload["sim_row_order"])
    payload["sim_row_order"] = list(reversed(shipped))
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, SWARM_ROW)]
    assert drawn != shipped
    assert drawn == list(reversed(shipped))


def test_a_numeric_run_id_keeps_its_place_because_the_order_is_a_list(
    browser: Browser,
):
    """A JSON parse sorts numeric row keys where the published order keeps them."""
    bvs.view_model({"reset": True})
    for run_id in ("3", "1", "2"):
        bvs.view_model(
            {"action": "register_sim", "run_id": run_id, "label": run_id, "cfg": {}}
        )
    payload = json.loads(json.dumps(bvs.view_model({}), ensure_ascii=True))
    assert payload["sim_row_order"] == ["3", "1", "2"]
    parts = draw_tab(browser, payload)
    drawn = [one["attrs"]["data-key"] for one in at_path(parts, SWARM_ROW)]
    assert drawn == ["3", "1", "2"], f"the rows were drawn {drawn}"


def test_the_numeric_key_order_check_reads_the_reordered_object(browser: Browser):
    """Proves rowsOf alone gives the sorted order the drawn rows avoid."""
    bvs.view_model({"reset": True})
    for run_id in ("3", "1", "2"):
        bvs.view_model(
            {"action": "register_sim", "run_id": run_id, "label": run_id, "cfg": {}}
        )
    payload = json.loads(json.dumps(bvs.view_model({}), ensure_ascii=True))
    draw_tab(browser, payload)
    keys = browser.parsed("Object.keys(acervatorBotSwarm.rowsOf('sim'))")
    assert keys == ["1", "2", "3"], f"the object read as {keys}"
    assert keys != payload["sim_row_order"]


def test_a_row_the_order_names_but_the_layer_lacks_is_reported(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["sim_row_order"].append("no-such-run")
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "unplaced"]
    assert named, "the module named no unplaced row"
    assert named[0]["detail"] == "no-such-run"


def test_a_row_the_layer_holds_but_the_order_leaves_out_is_reported(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["sim_row_order"] = payload["sim_row_order"][:1]
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "unplaced"]
    assert named, "the module named no unplaced row"


def test_the_unplaced_row_check_is_quiet_on_a_shipped_payload(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    named = [f for f in report["faults"] if f["fault"] == "unplaced"]
    assert named == [], f"a shipped row was named unplaced: {named}"


def test_the_summary_lines_are_drawn_in_the_order_qt_adds_them(browser: Browser):
    payload = state_payload("paper_running")
    order = payload["layer_chrome"]["paper"]["summary_order"]
    assert order == ["total", "pnl", "active"]
    assert list(payload["paper_summary"]) != order
    parts = draw_tab(browser, payload)
    panes = [
        one
        for one in parts
        if one["path"] == SUMMARY and one["attrs"]["data-layer"] == "paper"
    ]
    assert panes, "the paper summary was not drawn"
    drawn = [
        one["attrs"]["data-column"]
        for one in parts
        if one["path"] == SUMMARY_LINE and one["attrs"]["data-layer"] == "paper"
    ]
    assert drawn == order, f"the summary drew {drawn}"


def test_the_summary_order_check_reads_the_published_order(browser: Browser):
    payload = state_payload("paper_running")
    payload["layer_chrome"]["paper"]["summary_order"] = ["pnl", "active", "total"]
    parts = draw_tab(browser, payload)
    drawn = [
        one["attrs"]["data-column"]
        for one in parts
        if one["path"] == SUMMARY_LINE and one["attrs"]["data-layer"] == "paper"
    ]
    assert drawn == ["pnl", "active", "total"]


@pytest.mark.parametrize("at", [0, 1])
def test_every_swarm_cell_carries_the_text_its_own_column_holds(
    browser: Browser, at: int
):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    run_id = payload["sim_row_order"][at]
    handle = payload["sim_rows"][run_id]
    drawn = cells_at(parts, SWARM_CELL, run_id)
    expected = {
        name: str(handle[name]["text"])
        for name in handle
        if isinstance(handle[name], dict) and "text" in handle[name]
    }
    differing = {k: (v, drawn.get(k)) for k, v in expected.items() if drawn.get(k) != v}
    assert not differing, f"{len(differing)} cells differ: {differing}"
    assert len(drawn) == len(payload["column_widths"])


def test_the_cell_text_check_names_one_changed_column(browser: Browser):
    payload = state_payload(FULL_STATE)
    run_id = payload["sim_row_order"][0]
    payload["sim_rows"][run_id]["id_lbl"]["text"] = "CHANGED"
    parts = draw_tab(browser, payload)
    drawn = [
        one["text"]
        for one in at_path(parts, SWARM_CELL)
        if one["attrs"]["data-column"] == "id_lbl"
    ]
    assert drawn[0] == "CHANGED"


HOSTILE_LABELS = {
    "markup": "<img src=x onerror=alert(1)>",
    "a two hundred letter symbol": "M" * 200,
    "text where a number belongs": "1234.5",
    "nothing at all": None,
    "a number where text belongs": 12.5,
    "a true flag": True,
}

#: Every hostile call the surface itself refuses, and the error it raises.
SURFACE_REFUSES = {
    "a capital that is text": (
        {
            "action": "register_sim",
            "run_id": "x",
            "label": "x",
            "cfg": {"capital": "a"},
        },
        ValueError,
    ),
    "a fleet load that is a number": (
        {"action": "update_bots", "bot_statuses": 5},
        TypeError,
    ),
    "an opacity that is text": ({"action": "set_opacity", "pct": "loud"}, ValueError),
    "an animation step that is text": ({"action": "animate", "dt": "fast"}, ValueError),
    "a year to date total that is text": (
        {
            "action": "update_bots",
            "bot_statuses": [
                {"bot_id": "b", "stats": {"ytd_folded_usd": "not-a-number"}}
            ],
        },
        ValueError,
    ),
}


@pytest.mark.parametrize("case", sorted(SURFACE_REFUSES))
def test_the_surface_refuses_a_hostile_call_before_the_module_sees_it(case: str):
    params, raises = SURFACE_REFUSES[case]
    bvs.view_model({"reset": True})
    with pytest.raises(raises):
        bvs.view_model(params)


@pytest.mark.parametrize("case", sorted(HOSTILE_LABELS))
def test_the_tab_shows_whatever_label_the_surface_carried(js: JsRuntime, case: str):
    bvs.view_model({"reset": True})
    bvs.view_model(
        {
            "action": "register_sim",
            "run_id": "hostile",
            "label": HOSTILE_LABELS[case],
            "cfg": {},
        }
    )
    payload = json.loads(json.dumps(bvs.view_model({}), ensure_ascii=True))
    js.push(payload)
    held = js.named("rowsOf", "sim")["hostile"]["id_lbl"]["text"]
    assert held == payload["sim_rows"]["hostile"]["id_lbl"]["text"]


def test_markup_in_a_label_is_drawn_as_text_and_runs_nothing(browser: Browser):
    bvs.view_model({"reset": True})
    bvs.view_model(
        {
            "action": "register_sim",
            "run_id": "hostile",
            "label": HOSTILE_LABELS["markup"],
            "cfg": {},
        }
    )
    payload = json.loads(json.dumps(bvs.view_model({}), ensure_ascii=True))
    browser.js("window.RAN = false;")
    parts = draw_tab(browser, payload)
    drawn = [
        one
        for one in at_path(parts, SWARM_CELL)
        if one["attrs"]["data-column"] == "id_lbl"
    ]
    assert drawn[0]["text"] == HOSTILE_LABELS["markup"]
    assert "<img" not in drawn[0]["html"]
    assert drawn[0]["children"] == 0
    assert browser.js("window.RAN") is False
    assert browser.parsed("document.querySelectorAll('img').length") == 0


def test_the_markup_check_reads_a_page_that_does_hold_an_image(browser: Browser):
    """Proves the image count is not always zero on this page."""
    browser.js(
        "(function () { var img = document.createElement('img');"
        "  img.id = 'swarm-probe-image';"
        "  document.body.appendChild(img); })()"
    )
    assert browser.parsed("document.querySelectorAll('img').length") == 1
    browser.js("document.getElementById('swarm-probe-image').remove();")
    assert browser.parsed("document.querySelectorAll('img').length") == 0


def test_a_two_hundred_letter_symbol_is_drawn_whole_and_never_wrapped(
    browser: Browser,
):
    bvs.view_model({"reset": True})
    bvs.view_model(
        {
            "action": "update_bots",
            "bot_statuses": [{"bot_id": "b1", "symbol": "M" * 200}],
        }
    )
    payload = json.loads(json.dumps(bvs.view_model({}), ensure_ascii=True))
    parts = draw_tab(browser, payload)
    drawn = [
        one
        for one in at_path(parts, LIST_CELL)
        if one["attrs"]["data-column"] == TICKER_COLUMN
    ]
    assert drawn[0]["text"] == "M" * 200
    assert drawn[0]["style"]["whiteSpace"] == "nowrap"


HOSTILE_FIELDS = ("bot_ids", "grid_cells", "sim_rows", "sim_row_order", "rows_sent")


@pytest.mark.parametrize("field", HOSTILE_FIELDS)
def test_a_field_the_payload_omits_is_named_as_missing(js: JsRuntime, field: str):
    payload = state_payload(FULL_STATE)
    del payload[field]
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"]


@pytest.mark.parametrize("field", HOSTILE_FIELDS)
def test_a_field_carrying_null_is_named(js: JsRuntime, field: str):
    payload = state_payload(FULL_STATE)
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


@pytest.mark.parametrize("field", HOSTILE_FIELDS)
def test_a_field_that_is_a_scalar_where_a_bag_belongs_draws_nothing_and_raises_no_error(
    js: JsRuntime, field: str
):
    payload = state_payload(FULL_STATE)
    payload[field] = 7
    report = js.push(payload)
    assert report["held"] is not None
    assert js.field(field) == 7


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    named = [f for f in report["faults"] if f["fault"] in ("missing", "null")]
    assert named == [], f"a whole payload was named: {named}"


def test_a_cell_text_that_is_a_bag_is_named_and_the_row_still_draws(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    run_id = payload["sim_row_order"][0]
    payload["sim_rows"][run_id]["id_lbl"]["text"] = {"a": 1}
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "wrong-type"]
    assert named, "the module named no wrong-typed cell"
    assert named[0]["field"] == "id_lbl"


def test_a_cell_text_that_is_null_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    run_id = payload["sim_row_order"][0]
    payload["sim_rows"][run_id]["id_lbl"]["text"] = None
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "null" and f["where"]]
    assert named, "the module named no null cell"


def test_the_cell_type_check_is_quiet_on_a_shipped_row(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    named = [f for f in report["faults"] if f["fault"] == "wrong-type"]
    assert named == [], f"a shipped cell was named: {named}"


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    report = js.push(5)
    assert report["declared"] is None
    assert report["held"] is None
    assert report["faults"][0]["fault"] == "not-an-object"
    assert js.json("acervatorBotSwarm.isLoaded()") is False


def test_a_bad_bot_costs_the_other_bots_their_row_in_the_list_and_the_module_says_so(
    js: JsRuntime,
):
    """A filed defect: the grid keeps every bot and rows_sent does not."""
    bvs.view_model({"reset": True})
    bvs.view_model({"action": "update_bots", "bot_statuses": FLEET[:2]})
    broken = [
        dict(FLEET[0]),
        {"bot_id": "bot-bravo", "stats": {"ytd_folded_usd": "not-a-number"}},
        dict(FLEET[2]),
    ]
    with pytest.raises(ValueError):
        bvs.view_model({"action": "update_bots", "bot_statuses": broken})
    payload = json.loads(json.dumps(bvs.view_model({}), ensure_ascii=True))
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "disagrees"]
    assert named, "the module did not name the shortfall"
    assert report["declared"]["bots"] == len(payload["bot_ids"])
    assert len(payload["rows_sent"][-1]) < len(payload["bot_ids"])


def test_the_list_shortfall_check_is_quiet_on_a_whole_fleet_load(js: JsRuntime):
    report = js.push(state_payload("fleet"))
    named = [f for f in report["faults"] if f["fault"] == "disagrees"]
    assert named == [], f"a whole fleet load was named: {named}"


def _refuse_constant(name: str) -> Any:
    raise json.JSONDecodeError("JSON.parse refuses " + name, name, 0)


NON_FINITE_ROUTES = {
    "a profit that is not a number": (
        [REGISTER_SIM_A, {"action": "update_sim", "run_id": SIM_RUN_A, "pnl": "nan"}],
        "NaN",
    ),
    "a profit that is an infinity": (
        [REGISTER_SIM_A, {"action": "update_sim", "run_id": SIM_RUN_A, "pnl": "inf"}],
        "Infinity",
    ),
    "a wire share read from 1e999": (
        [
            {
                "action": "wire_created",
                "event": {"source_id": "a", "target_id": "b", "pct": "inf"},
            }
        ],
        "Infinity",
    ),
    "an animation step that is an infinity": (
        [
            {
                "action": "wire_created",
                "event": {"source_id": "a", "target_id": "b", "pct": 10},
            },
            {"action": "animate", "dt": "inf"},
        ],
        "Infinity",
    ),
}


def non_finite_payload(calls: list) -> dict:
    """Runs calls with the marked floats made real, without any JSON step."""
    bvs.view_model({"reset": True})
    payload = bvs.view_model({})
    for one in calls:
        params = json.loads(json.dumps(one))
        for name in ("pnl", "dt"):
            if params.get(name) in ("nan", "inf"):
                params[name] = float(params[name])
        event = params.get("event")
        if isinstance(event, dict) and event.get("pct") == "inf":
            event["pct"] = json.loads("1e999")
        payload = bvs.view_model(params)
    return payload


@pytest.mark.parametrize("case", sorted(NON_FINITE_ROUTES))
def test_the_surface_can_emit_a_value_json_parse_refuses(case: str):
    """The bridge writes a bare word the renderer JSON parser refuses."""
    calls, token = NON_FINITE_ROUTES[case]
    payload = non_finite_payload(calls)
    written = json.dumps(payload)
    assert token in written, f"{case}: the payload holds no {token}"
    with pytest.raises(json.JSONDecodeError):
        json.loads(written, parse_constant=_refuse_constant)


def test_the_non_finite_check_is_quiet_on_every_shipped_state():
    """No shipped state of this tab writes NaN or Infinity."""
    for name in STATE_NAMES:
        written = json.dumps(state_payload(name))
        assert "NaN" not in written, name
        assert "Infinity" not in written, name


def test_a_renderer_parameter_can_reach_the_infinity_the_bridge_writes():
    """Loading 1e999 gives an infinity the wire pct carries."""
    assert math.isinf(json.loads("1e999"))
    bvs.view_model({"reset": True})
    payload = bvs.view_model(
        {
            "action": "wire_created",
            "event": {
                "source_id": "a",
                "target_id": "b",
                "pct": json.loads("1e999"),
            },
        }
    )
    assert math.isinf(payload["wires"][0]["pct"])
    assert "Infinity" in json.dumps(payload)


def test_a_shipped_wire_share_stays_a_number_the_bridge_can_write():
    payload = state_payload("wired")
    assert payload["wires"][0]["pct"] == 25
    assert "Infinity" not in json.dumps(payload)


#: Every label on this tab whose text a caller supplies.
CALLER_TEXT_LABELS = (
    "id_lbl",
    "context_lbl",
    "mode_lbl",
    "feed_lbl",
    "cap_lbl",
    "status_lbl",
    "metric_lbl",
)


@pytest.mark.parametrize("column", CALLER_TEXT_LABELS)
def test_every_column_a_caller_writes_into_is_drawn_as_text(
    browser: Browser, column: str
):
    payload = state_payload(FULL_STATE)
    run_id = payload["sim_row_order"][0]
    payload["sim_rows"][run_id][column]["text"] = HOSTILE_LABELS["markup"]
    parts = draw_tab(browser, payload)
    drawn = [
        one
        for one in at_path(parts, SWARM_CELL)
        if one["attrs"]["data-column"] == column
    ]
    assert drawn[0]["text"] == HOSTILE_LABELS["markup"]
    assert drawn[0]["children"] == 0


def test_the_symbol_a_caller_writes_into_the_list_is_drawn_as_text(browser: Browser):
    payload = state_payload("fleet")
    ticker = payload["swarm_list"]["rows"][0][bsls.COL_TICKER]
    ticker["text"] = HOSTILE_LABELS["markup"]
    parts = draw_tab(browser, payload)
    drawn = [
        one
        for one in at_path(parts, LIST_CELL)
        if one["attrs"]["data-column"] == TICKER_COLUMN
    ]
    assert drawn[0]["text"] == HOSTILE_LABELS["markup"]
    assert drawn[0]["children"] == 0


BRIDGE_STUB = (
    "window.TRIES = 0;"
    "window.acervator = { call: function (method, params) {"
    "  window.TRIES = window.TRIES + 1;"
    "  window.ASKED = { method: method, params: params };"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload(FULL_STATE))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadBotSwarm();")
    drain_events()
    assert js.json("window.ASKED.method") == bvs.METHOD
    assert js.json("acervatorBotSwarm.isLoaded()") is True


def test_the_module_passes_a_callers_parameters_to_the_surface(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload(FULL_STATE))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadBotSwarm({ reset: true });")
    drain_events()
    assert js.json("window.ASKED.params") == {"reset": True}


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload(FULL_STATE))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadBotSwarm(); acervatorLoadBotSwarm();")
    drain_events()
    assert js.json("window.TRIES") == 1


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadBotSwarm();")
    drain_events()
    assert js.json("acervatorBotSwarm.isLoaded()") is False
    assert js.json("acervatorBotSwarm.loadError()") == (
        "the preload bridge is not present"
    )


def test_a_refused_ask_is_not_remembered(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload(FULL_STATE))
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES = window.TRIES + 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadBotSwarm();"
    )
    drain_events()
    assert js.json("acervatorBotSwarm.isLoaded()") is False
    assert js.json("acervatorBotSwarm.loadError()") == (
        "the Python backend is not running"
    )
    js.run("acervatorLoadBotSwarm();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorBotSwarm.isLoaded()") is True


def test_forgetting_the_model_clears_every_answer(js: JsRuntime):
    js.push(state_payload(FULL_STATE))
    assert js.json("acervatorBotSwarm.isLoaded()") is True
    js.run("acervatorBotSwarm.forget();")
    assert js.json("acervatorBotSwarm.isLoaded()") is False
    assert js.json("acervatorBotSwarm.declaredNames()").__len__() > 0
    assert js.json("acervatorBotSwarm.rowOrder('sim')") == []


def test_the_page_names_the_swarm_module_among_its_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("bot_visualizer.js")]
    assert len(named) == 1, f"the page names {len(named)} swarm modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


def test_the_page_loads_the_swarm_after_the_modules_it_resolves_through():
    """The module asks acervatorHeader and acervatorWidgets while drawing."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    order = {Path(ref).name: at for at, ref in enumerate(refs)}
    assert order["bot_visualizer.js"] > order["header_strip.js"]
    assert order["bot_visualizer.js"] > order["shared_widgets.js"]
    assert order["bot_visualizer.js"] > order["design_tokens.js"]
