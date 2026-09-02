"""The React Simulator tab, against the surface that describes it."""

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

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import simulator_tab_surface as sts
from src.simulator.fleet.bot_state_loader import load_bot_configs_from_state
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "simulator_tab.js"
TOKENS_PATH = WEB / "design_tokens.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
HEADER_PATH = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: The spare file every swap below moves over the module.
SPARE_PATH = MODULE_PATH.with_name(f"simulator_tab.scan_swap.{os.getpid()}.js")
#: One lock for the whole run, so no worker reads a swapped module.
LOCK_PATH = Path(tempfile.gettempdir()) / "acervator_simulator_tab_swap.lock"
LOCK_ATTEMPTS = 400_000
#: How many replace attempts one module swap makes on Windows.
SWAP_ATTEMPTS = 2000


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

#: Wide enough that a never-shown pane does not read every width as zero.
HOST_WIDTH_CSS = "1200px"
#: Tall enough that both splitter panes take a measurable height.
HOST_HEIGHT_CSS = "900px"

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

STORED_LOTS = [
    {"units": 4000.5, "price": 0.021},
    {"units": 7018.26, "price": 0.0195},
    {"not_a_lot": True},
]

STORED_FLEET = {
    "bots": {
        "04e1cafcd0f14b1e9c77": {
            "config": {
                "symbol": "CHIP/USD",
                "mode": "scrumming",
                "exchange_id": "coinbase",
                "target_balance": 250.0,
            },
            "scrumming_state": {
                "main_lots": STORED_LOTS,
                "anchor_target_balance": 250.0,
                "target_balance": 252.1391,
                "quote_to_usd": 1.0,
            },
            "stats": {
                "current_price": 0.0212,
                "position_value": 233.6,
                "total_trades": 363,
            },
        },
        "092428b2ab114c2d8e51": {
            "config": {
                "symbol": "SPK/USD",
                "mode": "scrumming",
                "exchange_id": "coinbase",
                "target_balance": 100.0,
            },
            "scrumming_state": {
                "main_lots": [{"units": 120.0}],
                "anchor_target_balance": 100.0,
                "target_balance": 101.5,
                "quote_to_usd": 1.0,
            },
            "stats": {
                "current_price": 0.0,
                "position_value": 0.0,
                "total_trades": 0,
            },
        },
    }
}


def stored_fleet_configs(fleet: Any = None) -> list:
    """The configs the real loader reads out of a stored bot_state file."""
    where = Path(tempfile.mkdtemp(prefix="simulator_tab_fleet_"))
    written = where / "bot_state.json"
    written.write_text(
        json.dumps(fleet if fleet is not None else STORED_FLEET), encoding="utf-8"
    )
    return load_bot_configs_from_state(path=written)


FLEET_CONFIGS = stored_fleet_configs()

PANEL = {
    "panel": {"statuses": [], "table": True, "bots": [], "gate": True},
    "chart": True,
    "nuclear": True,
    "build": True,
}
ACTIVITY_LINES = ["fleet load finished", "tick 1 of 40"]
PERFORMANCE_LINES = ["wall 0.004s", "rows 38"]

#: STATES holds every state of the tab the surface can be driven into.
STATES = {
    "bare": [],
    "built": [PANEL],
    "fleet": [PANEL, {"fleet": FLEET_CONFIGS}],
    "nuclear": [PANEL, {"mode": sts.NUCLEAR_KEY}],
    "looping": [PANEL, {"mode": sts.LOOPING_KEY}],
    "logged": [
        PANEL,
        {"activity": ACTIVITY_LINES, "performance": PERFORMANCE_LINES},
    ],
    "paused": [PANEL, {"pause": True}, {"activity": ACTIVITY_LINES}],
    "no_table": [
        {
            "panel": {"statuses": [], "table": False, "bots": [], "gate": True},
            "chart": True,
            "nuclear": True,
            "build": True,
        }
    ],
    "no_panel": [{"panel": None, "chart": True, "build": True}],
    "no_status_panel": [
        {
            "panel": {"statuses": [], "table": True, "bots": []},
            "chart": True,
            "nuclear": True,
            "build": True,
        }
    ],
    "refused": [
        {
            "panel": {
                "table": True,
                "bots": [],
                "gate": True,
                "error": {"type": "ValueError", "text": "a stored value refused"},
            },
            "chart": True,
            "nuclear": True,
            "build": True,
        },
        {"fleet": FLEET_CONFIGS},
    ],
    "wired": [
        PANEL,
        {
            "swarm": True,
            "topology": True,
            "connectors": True,
            "bot_manager": True,
            "async_loop": 1,
        },
    ],
    "charted": [PANEL, {"fleet": FLEET_CONFIGS}, {"chart_bot": "CHIP/USD"}],
}
STATE_NAMES = tuple(STATES)
FULL_STATE = "fleet"


def bridge_payload(calls: list) -> dict:
    """The surface answer for calls, after one round trip through JSON."""
    sts.view_model({"reset": True})
    payload = sts.view_model({})
    for one in calls:
        payload = sts.view_model(one)
    return json.loads(json.dumps(payload, ensure_ascii=True))


def state_payload(name: str) -> dict:
    return bridge_payload(STATES[name])


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):
    """A QJSEngine holding the Simulator module and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetSimulatorTab"

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
        return self.json("acervatorSimulatorTab." + answerer + "(JSON.parse(NAME))")

    def variable_for(self, value: Any) -> Any:
        self.bind_json("VALUE", value)
        return self.json("acervatorSimulatorTab.variableFor(JSON.parse(VALUE))")

    def in_groups(self, value: Any, groups: list) -> Any:
        self.bind_json("VALUE", value)
        self.bind_json("GROUPS", groups)
        return self.json(
            "acervatorSimulatorTab.variableInGroups("
            "JSON.parse(VALUE), JSON.parse(GROUPS))"
        )

    def declarations(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorSimulatorTab.declarations(JSON.parse(SHEET))")

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


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    declared = js.json("acervatorSimulatorTab.declaredNames()")
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
    declared = js.json("acervatorSimulatorTab.declaredNames()")
    assert sorted(set(payload) - set(declared)) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_declares(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload.pop("mounts")
    js.push(payload)
    declared = js.json("acervatorSimulatorTab.declaredNames()")
    assert sorted(set(declared) - set(payload)) == ["mounts"]


def test_the_field_value_check_names_one_changed_field(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["dialogs_shown"] = payload["dialogs_shown"] + 1
    js.push(payload)
    shipped = state_payload(FULL_STATE)
    differing = sorted(name for name in shipped if js.field(name) != shipped[name])
    assert differing == ["dialogs_shown"], f"the check named {differing}"


def drawn_mount_total(payload: dict) -> int:
    """How many of the seven mounts this payload lets the tab draw."""
    absent = 0
    if payload["table"]["mounted"] is not True:
        absent += 1
    for name in ("fleet_panel_set", "nuclear_panel_set", "gate_panel_set"):
        if payload["wiring"][name] is not True:
            absent += 1
    return len(payload["mounts"]) - absent


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["modes"] == len(payload["modes"]["rows"])
    assert report["held"]["modes"] == len(payload["modes"]["items"])
    assert report["declared"]["active_items"] == len(
        payload["pickers"]["active"]["items"]
    )
    assert report["held"]["active_items"] == report["declared"]["active_items"]
    assert report["declared"]["chart_items"] == len(
        payload["pickers"]["chart"]["items"]
    )
    assert report["held"]["chart_items"] == report["declared"]["chart_items"]
    assert report["declared"]["log_lines"] == len(payload["log"]["lines"])
    assert report["held"]["log_lines"] == report["declared"]["log_lines"]
    assert report["declared"]["mounts"] == len(payload["mounts"])
    assert report["held"]["mounts"] == drawn_mount_total(payload)
    assert report["declared"]["pages"] == payload["modes"]["page_total"]
    assert report["held"]["pages"] == report["declared"]["pages"]


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    whole = len(payload)
    del payload["mounts"]
    report = js.push(payload)
    assert report["declared"]["fields"] == whole
    assert report["held"]["fields"] == whole - 1


def test_a_log_line_the_pane_text_leaves_out_shortens_only_the_held_count(
    js: JsRuntime,
):
    payload = state_payload("logged")
    payload["log"]["text"] = "\n".join(payload["log"]["lines"][:-1])
    report = js.push(payload)
    assert report["declared"]["log_lines"] == report["held"]["log_lines"] + 1


def test_a_mount_the_payload_cannot_fill_shortens_only_the_held_mount_count(
    js: JsRuntime,
):
    payload = state_payload("no_table")
    report = js.push(payload)
    assert report["declared"]["mounts"] == report["held"]["mounts"] + 1


def as_css(value: Any) -> set:
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


SKIN_FIELDS = (
    "section_label_style",
    "mode_label_style",
    "mode_hint_style",
    "active_bot_label_style",
    "chart_pick_label_style",
    "expand_style",
    "pause_style",
    "log_style",
    "gate_unavailable_style",
    "indicator_style",
)
SIZE_FIELDS = (
    "outer_margins",
    "outer_spacing",
    "qt_unset_spacing",
    "qt_nested_margins",
    "splitter_minimum",
    "content_margins",
    "content_spacing",
    "fleet_page_margins",
    "fleet_page_spacing",
    "bot_area_margins",
    "bot_area_spacing",
    "active_bot_row_margins",
    "mode_row_margins",
    "chart_pick_row_margins",
    "indicator_wrap_margins",
    "indicator_inner_margins",
    "indicator_inner_spacing",
    "titled_margins",
    "titled_spacing",
    "titled_head_margins",
    "activity_wrap_margins",
    "activity_wrap_spacing",
    "gate_wrap_margins",
    "gate_wrap_spacing",
    "gate_host_margins",
    "scroll_minimum_height",
    "main_splitter_handle_width",
    "top_splitter_handle_width",
    "log_splitter_handle_width",
    "indicator_splitter_handle_width",
    "main_splitter_sizes",
    "top_splitter_sizes",
    "log_splitter_sizes",
    "indicator_splitter_sizes",
    "selector_min_width",
    "minimum_width",
)
WORD_FIELDS = (
    "mode_label",
    "active_bot_label",
    "chart_pick_label",
    "chart_title",
    "voting_title",
    "expand",
    "sim_log_title",
    "gate_title",
    "gate_unavailable",
    "fleet_panel_unavailable",
    "nuclear_panel_unavailable",
    "pause",
    "resume",
    "pause_button_text",
    "hint_text",
    "selector_tooltip",
    "tooltip",
    "all_bots",
    "chart_picker_empty",
    "text",
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
    for part in str(sheet).split(";"):
        head, sep, tail = part.partition(":")
        if sep and head.strip():
            found.add(tail.strip().rstrip("}"))
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
                if key in WORD_FIELDS and isinstance(value, str):
                    found.add(value)
                walk(value)
            return
        if isinstance(node, list):
            for one in node:
                walk(one)

    for name in STATE_NAMES:
        payload = state_payload(name)
        walk(payload)
        for row in payload["modes"]["rows"]:
            found.update(str(one) for one in row)
        for tip in payload["text"]["expand_tooltips"]:
            found.add(str(tip))
        for group in ("active", "chart"):
            for pair in payload["pickers"][group]["items"]:
                found.update(str(one) for one in pair)
        found.update(str(one) for one in payload["log"]["lines"])
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
        "simulator_tab.state",
        "sim-stat-strip",
        "bot-status-table",
        "fleet-replay",
        "nuclear-mode",
        "sim-price-chart",
        "indicator-voting-panel",
        "gate-status-panel",
        "mode_selector.currentIndexChanged",
        "chart_bot_picker.currentIndexChanged",
        "activity_pause_button.toggled",
        "chart_expand_button.clicked",
        "voting_expand_button.clicked",
        "vertical",
    }
)


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "simulator_tab.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"simulator_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & SKIN_VALUES)
    assert not written, f"simulator_tab.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"simulator_tab.js spells out token values: {written}"


def test_every_published_string_the_module_names_is_a_name_not_a_value():
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS
    unnamed = sorted(written - PUBLISHED_KEYS - set(NAMED_VALUES))
    assert not unnamed, f"the module writes published values: {unnamed}"


def test_every_named_value_is_a_name_and_not_a_value_the_tab_shows():
    overlap = sorted(set(NAMED_VALUES) & SKIN_VALUES)
    assert not overlap, f"these named values are painted on screen: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "simulator_tab.js holds a slash outside a comment, which the scan "
        f"cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES = {
    "colour": 'var written = "#00ffcc";',
    "margin": "var written = " + str(sts.INDICATOR_WRAP_MARGINS[0]) + ";",
    "size_text": 'var written = "' + str(sts.QT_UNSET_SPACING) + 'px";',
    "number": "var written = 12;",
    "mode_label": 'var written = "' + sts.MODE_LABEL_TEXT + '";',
    "log_title": 'var written = "' + sts.SIM_LOG_TITLE + '";',
    "expand_text": 'var written = "' + sts.EXPAND_TEXT + '";',
    "pause_text": 'var written = "' + sts.PAUSE_TEXT + '";',
    "gate_text": 'var written = "' + sts.GATE_UNAVAILABLE_TEXT + '";',
    "log_sheet": 'var written = "' + sts.LOG_STYLE + '";',
    "expand_sheet": 'var written = "' + sts.EXPAND_STYLE + '";',
    "tooltip": 'var written = "' + sts.ACTIVE_BOT_PICKER_TOOLTIP + '";',
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


def swap_module(content: bytes, attempts: int = SWAP_ATTEMPTS) -> None:
    """Puts content over the module through one atomic replace."""
    for _ in range(attempts):
        try:
            SPARE_PATH.write_bytes(content)
            os.replace(SPARE_PATH, MODULE_PATH)
            return
        except PermissionError:
            continue
        except OSError:
            continue
    raise AssertionError(
        "another worker held "
        + MODULE_PATH.name
        + f" open for all {attempts} attempts, so it was left as it was"
    )


def test_the_module_swap_leaves_the_file_whole_whether_or_not_it_is_held_open():
    """Windows denies a swap over an open module file where Linux allows it."""
    with module_held():
        original = MODULE_PATH.read_bytes()
        with MODULE_PATH.open("rb") as busy:
            assert busy.read(1), "the module file is empty"
            try:
                swap_module(original, attempts=3)
                denied = False
            except AssertionError:
                denied = True
        SPARE_PATH.unlink(missing_ok=True)
        assert MODULE_PATH.read_bytes() == original, f"denied {denied}"


def test_the_module_swap_reports_when_every_attempt_is_used_up():
    with module_held():
        original = MODULE_PATH.read_bytes()
        with pytest.raises(AssertionError) as raised:
            swap_module(original, attempts=0)
        SPARE_PATH.unlink(missing_ok=True)
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
            swap_module(original + WRITTEN_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(original)
            after = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
            assert after == before, f"the file was not restored after {kind}"
    finally:
        swap_module(original)
        SPARE_PATH.unlink(missing_ok=True)
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
        assert runtime.json("typeof acervatorSetSimulatorTab") == "function", kind


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
    actual = js.json("acervatorSimulatorTab.kinds()")
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
    payload["chrome"]["outer_spacing"] = str(payload["chrome"]["outer_spacing"])
    js.push(payload)
    expected = python_kinds(state_payload(FULL_STATE))
    actual = js.json("acervatorSimulatorTab.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["chrome.outer_spacing"], f"the check named {differing}"


def test_the_type_check_reads_a_scalar_where_a_bag_belongs(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["log"] = 7
    js.push(payload)
    actual = js.json("acervatorSimulatorTab.kinds()")
    assert actual["log"] == "number"
    assert "log.lines" not in actual


def test_the_type_check_reads_a_null_where_a_bag_belongs(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["pickers"] = None
    js.push(payload)
    actual = js.json("acervatorSimulatorTab.kinds()")
    assert actual["pickers"] == "null"
    assert "pickers.active" not in actual


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_dropdown_reaches_the_module_row_for_row(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.named("itemsOf", "modes") == payload["modes"]["items"]
    assert js.named("itemsOf", "active") == payload["pickers"]["active"]["items"]
    assert js.named("itemsOf", "chart") == payload["pickers"]["chart"]["items"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_log_pane_text_reaches_the_module_line_for_line(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.json("acervatorSimulatorTab.logLines()") == payload["log"]["lines"]


def test_the_log_line_check_reads_the_pane_text_and_not_the_line_list(js: JsRuntime):
    payload = state_payload("logged")
    payload["log"]["text"] = "one\ntwo\nthree"
    js.push(payload)
    assert js.json("acervatorSimulatorTab.logLines()") == ["one", "two", "three"]
    assert js.json("acervatorSimulatorTab.logLines()") != payload["log"]["lines"]


def carriers_of(value: Any) -> list:
    tokens = token_payload()
    aliases = tokens["alias_targets"]
    return sorted(
        name
        for name, held in tokens["tokens"].items()
        if str(held) == str(value) and name not in aliases
    )


RADIUS_CARRIER = "RADIUS_CARD"
SPACING_CARRIER = "SPACE_XXL"


def test_the_unset_layout_gap_is_carried_by_a_radius_token_alone(js: JsRuntime):
    js.load_tokens()
    gap = state_payload(FULL_STATE)["chrome"]["qt_unset_spacing"]
    assert carriers_of(gap) == [RADIUS_CARRIER]
    assert js.variable_for(gap) == RADIUS_CARRIER


def test_that_gap_borrows_no_token_because_a_radius_means_something_else(
    js: JsRuntime,
):
    js.load_tokens()
    gap = state_payload(FULL_STATE)["chrome"]["qt_unset_spacing"]
    assert js.json("acervatorSimulatorTab.spaceGroups()") == ["spacing"]
    assert js.in_groups(gap, ["spacing"]) is None
    assert js.json("acervatorSimulatorTab.length(" + json.dumps(gap) + ")") == (
        str(gap) + "px"
    )


def test_the_group_check_answers_for_a_number_the_spacing_group_carries(js: JsRuntime):
    js.load_tokens()
    carried = token_payload()["groups"]["spacing"][SPACING_CARRIER]
    assert carriers_of(carried) == [SPACING_CARRIER]
    assert js.in_groups(carried, ["spacing"]) == SPACING_CARRIER


SIZE_PATHS = (
    ("chrome", "outer_spacing"),
    ("chrome", "qt_unset_spacing"),
    ("chrome", "titled_spacing"),
    ("chrome", "bot_area_spacing"),
    ("chrome", "main_splitter_handle_width"),
    ("chrome", "indicator_splitter_handle_width"),
)


@pytest.mark.parametrize("path", SIZE_PATHS, ids=lambda p: p[1])
def test_no_size_this_tab_draws_borrows_a_token_from_another_group(
    js: JsRuntime, path: tuple
):
    js.load_tokens()
    value = state_payload(FULL_STATE)[path[0]][path[1]]
    assert js.in_groups(value, ["spacing"]) is None, f"{value} borrowed a token"


def test_a_value_no_token_carries_resolves_to_none(js: JsRuntime):
    js.load_tokens()
    assert js.variable_for("no-token-carries-this") is None


def test_the_resolver_reports_no_name_with_the_widget_module_off_the_page(
    bare: JsRuntime,
):
    bare.load_tokens()
    assert bare.variable_for(str(dss.PRIMARY)) is None


def tab_sheets(payload: dict) -> list:
    found = [payload["identity"]["section_label_style"]]
    found.append(payload["chrome"]["indicator_style"])
    for name in SKIN_FIELDS:
        if name in payload["text"]:
            found.append(payload["text"][name])
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
        "field": "text",
        "fault": "no-sheet-source",
        "detail": None,
    } in report["faults"]


def test_the_sheet_source_check_is_quiet_with_the_header_module_loaded(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    kinds = [f["fault"] for f in report["faults"]]
    assert "no-sheet-source" not in kinds


def test_no_sheet_this_tab_paints_carries_a_colour_css_reads_differently():
    """No sheet holds an eight-digit hex or a byte alpha."""
    for name in STATE_NAMES:
        for sheet in tab_sheets(state_payload(name)):
            assert not re.search(r"#[0-9a-fA-F]{8}\b", str(sheet)), sheet
            assert "rgba(" not in str(sheet), sheet


def test_the_colour_refusal_names_an_eight_digit_hex(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["text"]["log_style"] = "QPlainTextEdit{color:#80ff00cc;}"
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "qt-colour"]
    assert named, "the module named no eight-digit colour"
    assert named[0]["detail"] == "AARRGGBB"
    assert named[0]["where"] == "log_style"


def test_the_colour_refusal_names_a_byte_alpha(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["text"]["mode_label_style"] = "background:rgba(1,2,3,128);"
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
                if self.js("typeof window.acervatorSetSimulatorTab") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the Simulator module: readyState "
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
    "flexGrow",
    "flexBasis",
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
    "height",
    "minWidth",
    "minHeight",
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
    "window.HOST = document.getElementById('sim-host');"
    "if (window.HOST === null) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'sim-host';"
    "  document.body.appendChild(window.HOST); }"
    "window.HOST.style.width = " + json.dumps(HOST_WIDTH_CSS) + ";"
    "window.HOST.style.height = " + json.dumps(HOST_HEIGHT_CSS) + ";"
    "window.HOST.style.display = 'flex';"
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
    "        held: el.value === undefined ? null : el.value,"
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
        "acervatorSetSimulatorTab(JSON.parse(window.PAYLOAD));"
        "acervatorSimulatorTab.renderTab(window.HOST);"
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


TAB = "sim-tab"
STAT_STRIP = TAB + "/sim-stat-strip"
MAIN_SPLIT = TAB + "/main-splitter"
MAIN_HANDLE = MAIN_SPLIT + "/splitter-handle"
MAIN_PANE = MAIN_SPLIT + "/splitter-pane"
TOP_SPLIT = MAIN_PANE + "/top-splitter"
TOP_PANE = TOP_SPLIT + "/splitter-pane"
CONTENT = TOP_PANE + "/content"
MODE_ROW = CONTENT + "/mode-row"
MODE_LABEL = MODE_ROW + "/mode-label"
MODE_SELECTOR = MODE_ROW + "/mode-selector"
MODE_HINT = MODE_ROW + "/mode-hint"
STACK = CONTENT + "/stack"
FLEET_PAGE = STACK + "/fleet-page"
NUCLEAR_PAGE = STACK + "/nuclear-page"
BOT_AREA = FLEET_PAGE + "/bot-area"
ACTIVE_ROW = BOT_AREA + "/active-bot-row"
ACTIVE_LABEL = ACTIVE_ROW + "/active-bot-label"
ACTIVE_PICKER = ACTIVE_ROW + "/active-bot-picker"
BOT_TABLE = BOT_AREA + "/bot-status-table"
FLEET_REPLAY = FLEET_PAGE + "/fleet-replay"
NUCLEAR_MOUNT = NUCLEAR_PAGE + "/nuclear-mode"
INDICATOR_WRAP = TOP_PANE + "/indicator-wrap"
INDICATOR_BOX = INDICATOR_WRAP + "/indicator-container"
INDICATOR_SPLIT = INDICATOR_BOX + "/indicator-splitter"
INDICATOR_PANE = INDICATOR_SPLIT + "/splitter-pane"
TITLED_BOX = INDICATOR_PANE + "/titled-box"
TITLED_HEAD = TITLED_BOX + "/titled-head"
SECTION_LABEL = TITLED_HEAD + "/section-label"
EXPAND_BUTTON = TITLED_HEAD + "/expand-button"
CHART_PICK_ROW = TITLED_BOX + "/chart-pick-row"
CHART_PICK_LABEL = CHART_PICK_ROW + "/chart-pick-label"
CHART_PICKER = CHART_PICK_ROW + "/chart-bot-picker"
SCROLL = TITLED_BOX + "/scroll"
PRICE_CHART = SCROLL + "/sim-price-chart"
VOTING_PANEL = SCROLL + "/indicator-voting-panel"
LOG_SPLIT = MAIN_PANE + "/log-splitter"
LOG_PANE_BOX = LOG_SPLIT + "/splitter-pane"
ACTIVITY_WRAP = LOG_PANE_BOX + "/activity-wrap"
LOG_HEADER = ACTIVITY_WRAP + "/log-header"
LOG_TITLE = LOG_HEADER + "/section-label"
PAUSE_BUTTON = LOG_HEADER + "/pause-button"
LOG_PANE = ACTIVITY_WRAP + "/log-pane"
GATE_WRAP = LOG_PANE_BOX + "/gate-wrap"
GATE_HEADER = GATE_WRAP + "/gate-header"
GATE_TITLE = GATE_HEADER + "/section-label"
GATE_HOST = GATE_WRAP + "/gate-host"
GATE_PANEL = GATE_HOST + "/gate-status-panel"
GATE_UNAVAILABLE = GATE_HOST + "/gate-unavailable"

EXPECTED_PARTS = (
    TAB,
    STAT_STRIP,
    MAIN_SPLIT,
    MAIN_HANDLE,
    MAIN_PANE,
    TOP_SPLIT,
    TOP_PANE,
    CONTENT,
    MODE_ROW,
    MODE_LABEL,
    MODE_SELECTOR,
    MODE_HINT,
    STACK,
    FLEET_PAGE,
    NUCLEAR_PAGE,
    BOT_AREA,
    ACTIVE_ROW,
    ACTIVE_LABEL,
    ACTIVE_PICKER,
    BOT_TABLE,
    FLEET_REPLAY,
    NUCLEAR_MOUNT,
    INDICATOR_WRAP,
    INDICATOR_BOX,
    INDICATOR_SPLIT,
    INDICATOR_PANE,
    TITLED_BOX,
    TITLED_HEAD,
    SECTION_LABEL,
    EXPAND_BUTTON,
    CHART_PICK_ROW,
    CHART_PICK_LABEL,
    CHART_PICKER,
    SCROLL,
    PRICE_CHART,
    VOTING_PANEL,
    LOG_SPLIT,
    ACTIVITY_WRAP,
    LOG_HEADER,
    LOG_TITLE,
    PAUSE_BUTTON,
    LOG_PANE,
    GATE_WRAP,
    GATE_HEADER,
    GATE_TITLE,
    GATE_HOST,
    GATE_PANEL,
)

#: Each mount path another unit owns against its own slot name.
MOUNT_PARTS = {
    STAT_STRIP: "sim-stat-strip",
    BOT_TABLE: "bot-status-table",
    FLEET_REPLAY: "fleet-replay",
    NUCLEAR_MOUNT: "nuclear-mode",
    PRICE_CHART: "sim-price-chart",
    VOTING_PANEL: "indicator-voting-panel",
    GATE_PANEL: "gate-status-panel",
}


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    policy = browser.js(
        "document.querySelector('meta[http-equiv=\"Content-Security-Policy\"]')"
        ".getAttribute('content')"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorSimulatorTab") == "object"
    assert browser.js("typeof window.acervatorSetSimulatorTab") == "function"
    assert browser.js("typeof window.acervatorLoadSimulatorTab") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_tab(browser, state_payload(FULL_STATE))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_page_refuses_a_network_call_when_one_is_made(browser: Browser):
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


def test_the_drawn_tab_names_every_child_a_check_reads(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    drawn = {one["path"] for one in parts}
    missing = sorted(set(EXPECTED_PARTS) - drawn)
    assert not missing, f"{len(missing)} named children were not drawn: {missing}"


def test_the_named_child_check_reports_a_child_that_is_not_drawn(browser: Browser):
    parts = draw_tab(browser, state_payload("no_table"))
    drawn = {one["path"] for one in parts}
    assert BOT_TABLE not in drawn, "an unmounted table still drew its host"
    assert TAB in drawn


def test_each_mount_another_unit_owns_is_drawn_empty_and_named(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    for path, slot in MOUNT_PARTS.items():
        found = at_path(parts, path)
        assert found, f"{path} was not drawn"
        for one in found:
            assert one["attrs"]["data-slot"] == slot
            assert one["html"] == "", f"{path} is not an empty host"


def test_every_mount_the_surface_names_is_one_the_tab_draws(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    js.push(payload)
    assert sorted(js.json("acervatorSimulatorTab.mountNames()")) == sorted(
        payload["mounts"]
    )


def test_the_mount_check_names_a_mount_the_tab_does_not_draw(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["mounts"] = payload["mounts"] + ["no-such-mount"]
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "unplaced"]
    assert named, "the module named no unknown mount"
    assert named[0]["detail"] == "no-such-mount"


def test_the_mount_check_is_quiet_on_a_shipped_payload(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    named = [f for f in report["faults"] if f["fault"] == "unplaced"]
    assert named == [], f"a shipped mount was named: {named}"


def test_the_unavailable_line_is_drawn_where_no_fleet_panel_is_attached(
    browser: Browser,
):
    payload = state_payload("no_panel")
    parts = draw_tab(browser, payload)
    found = at_path(parts, FLEET_PAGE + "/fleet-unavailable")
    assert found, "the unavailable line was not drawn"
    assert found[0]["text"] == payload["text"]["fleet_panel_unavailable"]
    assert not at_path(parts, FLEET_REPLAY)


def test_the_unavailable_line_check_reads_a_page_that_has_its_panel(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    assert not at_path(parts, FLEET_PAGE + "/fleet-unavailable")
    assert at_path(parts, FLEET_REPLAY)


def test_the_status_line_is_drawn_where_no_panel_owns_the_host(browser: Browser):
    payload = state_payload("no_status_panel")
    parts = draw_tab(browser, payload)
    found = at_path(parts, GATE_UNAVAILABLE)
    assert found, "the status line was not drawn"
    assert found[0]["text"] == payload["text"]["gate_unavailable"]
    assert not at_path(parts, GATE_PANEL)


def test_the_drawn_mode_label_takes_the_skin_the_surface_declares(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = base_body(payload["text"]["mode_label_style"])
    sheet_agrees(only(parts, MODE_LABEL), probe(browser, body), MODE_LABEL)


def test_the_drawn_mode_hint_takes_the_skin_the_surface_declares(browser: Browser):
    payload = state_payload("nuclear")
    parts = draw_tab(browser, payload)
    body = base_body(payload["text"]["mode_hint_style"])
    sheet_agrees(only(parts, MODE_HINT), probe(browser, body), MODE_HINT)


def test_the_drawn_expand_button_takes_the_skin_the_surface_declares(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = base_body(payload["text"]["expand_style"])
    sheet_agrees(at_path(parts, EXPAND_BUTTON)[0], probe(browser, body), EXPAND_BUTTON)


def test_the_drawn_pause_button_takes_the_skin_the_surface_declares(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = base_body(payload["text"]["pause_style"])
    sheet_agrees(only(parts, PAUSE_BUTTON), probe(browser, body), PAUSE_BUTTON)


def test_the_drawn_log_pane_takes_the_skin_the_surface_declares(browser: Browser):
    payload = state_payload("logged")
    parts = draw_tab(browser, payload)
    body = base_body(payload["text"]["log_style"])
    sheet_agrees(only(parts, LOG_PANE), probe(browser, body), LOG_PANE)


def test_the_drawn_indicator_box_takes_the_skin_the_surface_declares(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = base_body(payload["chrome"]["indicator_style"])
    sheet_agrees(only(parts, INDICATOR_BOX), probe(browser, body), INDICATOR_BOX)


def test_the_drawn_section_label_takes_the_skin_the_surface_declares(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = base_body(payload["identity"]["section_label_style"])
    sheet_agrees(only(parts, LOG_TITLE), probe(browser, body), LOG_TITLE)


def test_the_skin_check_reports_a_probe_that_took_no_value(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    with pytest.raises(AssertionError) as raised:
        sheet_agrees(only(parts, MODE_LABEL), probe(browser, ""), MODE_LABEL)
    assert "compares nothing" in str(raised.value)


def test_the_skin_check_reports_a_drawn_value_the_surface_did_not_declare(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    body = base_body(payload["text"]["mode_label_style"])
    changed = probe(browser, body)
    key = sorted(changed)[0]
    changed[key] = "rgb(1, 2, 3)"
    with pytest.raises(AssertionError) as raised:
        sheet_agrees(only(parts, MODE_LABEL), changed, MODE_LABEL)
    assert key in str(raised.value)


def pixels(value: Any) -> str:
    return str(value) + "px"


def test_every_layout_gap_the_surface_publishes_is_the_one_drawn(browser: Browser):
    payload = state_payload(FULL_STATE)
    shape = payload["chrome"]
    parts = draw_tab(browser, payload)
    pairs = [
        (TAB, shape["outer_spacing"], shape["outer_margins"]),
        (CONTENT, shape["content_spacing"], shape["content_margins"]),
        (MODE_ROW, shape["qt_unset_spacing"], shape["mode_row_margins"]),
        (BOT_AREA, shape["bot_area_spacing"], shape["bot_area_margins"]),
        (ACTIVE_ROW, shape["qt_unset_spacing"], shape["active_bot_row_margins"]),
        (FLEET_PAGE, shape["fleet_page_spacing"], shape["fleet_page_margins"]),
        (INDICATOR_WRAP, shape["qt_unset_spacing"], shape["indicator_wrap_margins"]),
        (
            INDICATOR_BOX,
            shape["indicator_inner_spacing"],
            shape["indicator_inner_margins"],
        ),
        (ACTIVITY_WRAP, shape["activity_wrap_spacing"], shape["activity_wrap_margins"]),
        (LOG_HEADER, shape["qt_unset_spacing"], shape["qt_nested_margins"]),
        (GATE_WRAP, shape["gate_wrap_spacing"], shape["gate_wrap_margins"]),
        (GATE_HOST, shape["qt_unset_spacing"], shape["gate_host_margins"]),
    ]
    for path, gap, margins in pairs:
        drawn = at_path(parts, path)[0]
        assert drawn["style"]["rowGap"] == pixels(gap), path
        assert drawn["style"]["columnGap"] == pixels(gap), path
        for side, value in zip(
            ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"), margins
        ):
            assert drawn["style"][side] == pixels(value), f"{path}/{side}"


def test_the_titled_head_and_pick_row_take_the_gaps_the_surface_publishes(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    shape = payload["chrome"]
    parts = draw_tab(browser, payload)
    head = at_path(parts, TITLED_HEAD)[0]
    assert head["style"]["rowGap"] == pixels(shape["qt_unset_spacing"])
    box = at_path(parts, TITLED_BOX)[0]
    assert box["style"]["rowGap"] == pixels(shape["titled_spacing"])
    row = only(parts, CHART_PICK_ROW)
    assert row["style"]["rowGap"] == pixels(shape["qt_unset_spacing"])
    for side, value in zip(
        ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
        shape["chart_pick_row_margins"],
    ):
        assert row["style"][side] == pixels(value)


def test_the_layout_gap_check_reads_a_changed_gap(browser: Browser):
    payload = state_payload(FULL_STATE)
    was = payload["chrome"]["qt_unset_spacing"]
    payload["chrome"]["qt_unset_spacing"] = was + 7
    parts = draw_tab(browser, payload)
    drawn = only(parts, MODE_ROW)
    assert drawn["style"]["rowGap"] == pixels(was + 7)
    assert drawn["style"]["rowGap"] != pixels(was)


def rewrite_token(browser: Browser, name: str, value: Any) -> None:
    browser.js(
        "document.documentElement.style.setProperty("
        + json.dumps("--" + name)
        + ", "
        + json.dumps(str(value))
        + ");"
    )


def test_rewriting_the_radius_token_moves_no_value_this_tab_draws(browser: Browser):
    payload = state_payload(FULL_STATE)
    before = draw_tab(browser, payload)
    rewrite_token(browser, RADIUS_CARRIER, 999)
    after = read_parts(browser)
    assert len(before) == len(after)
    moved = [
        one["path"]
        for at, one in enumerate(before)
        if one["style"] != after[at]["style"]
    ]
    assert moved == [], f"parts followed a token they do not borrow: {moved}"


def test_that_token_rewrite_does_reach_the_page(browser: Browser):
    payload = state_payload(FULL_STATE)
    draw_tab(browser, payload)
    gap = payload["chrome"]["qt_unset_spacing"]
    body = "width: calc(var(--" + RADIUS_CARRIER + ", " + str(gap) + ") * 1px)"
    before = browser.parsed(
        "window.probeStyle(" + json.dumps(body) + ", " + json.dumps(["width"]) + ")"
    )
    assert before["width"] == pixels(gap)
    rewrite_token(browser, RADIUS_CARRIER, 999)
    after = browser.parsed(
        "window.probeStyle(" + json.dumps(body) + ", " + json.dumps(["width"]) + ")"
    )
    assert after["width"] == pixels(999)


LABELLED = (
    MODE_LABEL,
    MODE_HINT,
    ACTIVE_LABEL,
    CHART_PICK_LABEL,
    SECTION_LABEL,
    LOG_TITLE,
    GATE_TITLE,
)


def test_no_label_the_tab_draws_can_be_dragged_over(browser: Browser):
    payload = state_payload(FULL_STATE)
    assert payload["text"]["label_selectable"] is False
    parts = draw_tab(browser, payload)
    for path in LABELLED:
        found = at_path(parts, path)
        assert found, f"{path} was not drawn"
        for one in found:
            assert one["style"]["userSelect"] == "none", path


def test_the_drag_selection_check_reads_a_selectable_element(browser: Browser):
    browser.js(PAGE_HELPERS)
    found = browser.parsed('window.probeStyle("", ["userSelect"])')
    assert found["userSelect"] != "none"


def test_the_log_pane_can_be_dragged_over_because_a_read_only_pane_selects(
    browser: Browser,
):
    payload = state_payload("logged")
    assert payload["text"]["log_selectable"] is True
    parts = draw_tab(browser, payload)
    assert only(parts, LOG_PANE)["style"]["userSelect"] == "text"


def test_no_label_wraps_because_a_qt_label_clips_instead(browser: Browser):
    payload = state_payload(FULL_STATE)
    assert payload["text"]["label_word_wrap"] is False
    parts = draw_tab(browser, payload)
    for path in LABELLED:
        for one in at_path(parts, path):
            assert one["style"]["whiteSpace"] == "nowrap", path
            assert one["style"]["overflowX"] == "hidden", path


def test_the_wrap_check_reads_the_surfaces_own_flag(browser: Browser):
    payload = state_payload(FULL_STATE)
    payload["text"]["label_word_wrap"] = True
    parts = draw_tab(browser, payload)
    assert only(parts, MODE_LABEL)["style"]["whiteSpace"] == "pre-wrap"


def test_the_log_pane_wraps_because_qt_wraps_it_at_the_widget_width(browser: Browser):
    payload = state_payload("logged")
    assert payload["text"]["log_wraps_at_width"] is True
    parts = draw_tab(browser, payload)
    assert only(parts, LOG_PANE)["style"]["whiteSpace"] == "pre-wrap"


def test_the_scroll_box_scrolls_because_qt_puts_the_visual_in_a_scroll_area(
    browser: Browser,
):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    for one in at_path(parts, SCROLL):
        assert one["style"]["overflowY"] == "auto"
        assert one["style"]["overflowX"] == "hidden"


def test_the_scroll_box_takes_the_minimum_height_the_surface_publishes(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    least = payload["chrome"]["scroll_minimum_height"]
    for one in at_path(parts, SCROLL):
        assert one["style"]["minHeight"] == pixels(least)


def test_the_mode_row_does_not_scroll_because_qt_gives_it_no_scroll_area(
    browser: Browser,
):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    assert only(parts, MODE_ROW)["style"]["overflowY"] != "auto"


FOCUSABLE_PARTS = {
    "mode_selector": MODE_SELECTOR,
    "active_bot_picker": ACTIVE_PICKER,
    "chart_expand_button": EXPAND_BUTTON,
    "chart_bot_picker": CHART_PICKER,
    "voting_expand_button": EXPAND_BUTTON,
    "activity_pause_button": PAUSE_BUTTON,
    "log_pane": LOG_PANE,
}


def test_every_strong_focus_widget_qt_draws_takes_the_keyboard(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    tags = {"BUTTON", "SELECT", "TEXTAREA"}
    for name in payload["focus"]["order"]:
        found = at_path(parts, FOCUSABLE_PARTS[name])
        assert found, f"{name} was not drawn"
        for one in found:
            assert one["tag"] in tags, f"{name} is a {one['tag']}"


def test_no_label_the_tab_draws_takes_the_keyboard(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    for path in LABELLED:
        for one in at_path(parts, path):
            assert one["tag"] in {"SPAN", "DIV"}, f"{path} is a {one['tag']}"


def test_the_focus_order_follows_the_order_qt_adds_the_widgets(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    wanted = set(FOCUSABLE_PARTS.values())
    order = []
    for one in parts:
        if one["path"] not in wanted:
            continue
        if one["path"] == EXPAND_BUTTON:
            order.append(one["attrs"]["data-slot"])
            continue
        order.append(one["path"])
    assert order == [
        MODE_SELECTOR,
        ACTIVE_PICKER,
        "sim-price-chart",
        CHART_PICKER,
        "indicator-voting-panel",
        PAUSE_BUTTON,
        LOG_PANE,
    ], order


def test_the_focus_order_check_reads_the_order_the_surface_publishes(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    js.push(payload)
    assert js.json("acervatorSimulatorTab.focusOrder()") == payload["focus"]["order"]
    assert sorted(js.json("acervatorSimulatorTab.focusPolicies()")) == sorted(
        payload["focus"]["policies"]
    )


def test_the_expand_button_carries_the_hover_rule_qt_paints(browser: Browser):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    before = at_path(parts, EXPAND_BUTTON)[0]["style"]["backgroundColor"]
    browser.js(
        "(function () {"
        "  var one = window.HOST.querySelector('[data-part=\"expand-button\"]');"
        "  one.dispatchEvent(new MouseEvent('mouseover', { bubbles: true })); })()"
    )
    browser.settle(SETTLE_MS)
    after = read_parts(browser)
    hovered = at_path(after, EXPAND_BUTTON)[0]
    assert hovered["attrs"]["data-hovered"] == "true"
    assert hovered["style"]["backgroundColor"] != before


def test_the_hover_check_reads_an_unhovered_button(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    assert at_path(parts, EXPAND_BUTTON)[0]["attrs"]["data-hovered"] == "false"


def test_the_pause_button_carries_the_checked_rule_qt_paints(browser: Browser):
    running = draw_tab(browser, state_payload(FULL_STATE))
    before = only(running, PAUSE_BUTTON)["style"]["color"]
    parts = draw_tab(browser, state_payload("paused"))
    checked = only(parts, PAUSE_BUTTON)
    assert checked["attrs"]["data-checked"] == "true"
    assert checked["style"]["color"] != before


def test_the_checked_check_reads_an_unchecked_button(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    assert only(parts, PAUSE_BUTTON)["attrs"]["data-checked"] == "false"


def test_the_pause_button_shows_the_word_the_surface_publishes(browser: Browser):
    running = state_payload(FULL_STATE)
    parts = draw_tab(browser, running)
    assert only(parts, PAUSE_BUTTON)["text"] == running["text"]["pause"]
    paused = state_payload("paused")
    parts = draw_tab(browser, paused)
    assert only(parts, PAUSE_BUTTON)["text"] == paused["text"]["resume"]


def test_the_log_pane_holds_the_text_the_surface_wrote(browser: Browser):
    payload = state_payload("logged")
    parts = draw_tab(browser, payload)
    drawn = only(parts, LOG_PANE)
    assert drawn["held"] == payload["log"]["text"]
    assert drawn["attrs"]["data-count"] == str(len(payload["log"]["lines"]))


def test_the_log_pane_check_reads_a_pane_with_no_line_in_it(browser: Browser):
    parts = draw_tab(browser, state_payload(FULL_STATE))
    assert only(parts, LOG_PANE)["held"] == ""
    assert only(parts, LOG_PANE)["attrs"]["data-count"] == "0"


def test_a_held_activity_line_never_reaches_the_pane(browser: Browser):
    payload = state_payload("paused")
    assert payload["log"]["activity_paused"] is True
    parts = draw_tab(browser, payload)
    assert only(parts, LOG_PANE)["held"] == ""


def test_the_pause_button_holds_the_activity_stream_and_leaves_the_other_flag(
    js: JsRuntime,
):
    payload = state_payload("paused")
    js.push(payload)
    assert payload["log"]["activity_paused"] is True
    assert payload["log"]["performance_paused"] is False
    held = js.field("log")
    assert held["activity_paused"] is True
    assert held["performance_paused"] is False


def test_a_performance_line_reaches_the_pane_while_the_button_is_held(js: JsRuntime):
    payload = bridge_payload(
        [PANEL, {"pause": True}, {"performance": PERFORMANCE_LINES}]
    )
    js.push(payload)
    written = js.json("acervatorSimulatorTab.logLines()")
    assert len(written) == len(PERFORMANCE_LINES)
    assert written[0].startswith(payload["text"]["performance_prefix"])


def test_the_mode_dropdown_draws_one_row_per_mode_in_the_published_order(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    parts = draw_tab(browser, payload)
    drawn = [
        one["attrs"]["data-key"]
        for one in parts
        if one["path"] == MODE_SELECTOR + "/option"
    ]
    assert browser.parsed(
        "Array.prototype.slice.call("
        "window.HOST.querySelectorAll('[data-part=\"mode-selector\"] option')"
        ").map(function (o) { return o.textContent; })"
    ) == [row[0] for row in payload["modes"]["rows"]]
    assert drawn == []


def test_the_mode_dropdown_keeps_the_row_the_surface_selected(browser: Browser):
    payload = state_payload("nuclear")
    parts = draw_tab(browser, payload)
    assert only(parts, MODE_SELECTOR)["attrs"]["data-index"] == str(
        payload["modes"]["index"]
    )


def test_the_stack_shows_the_page_the_selected_mode_routes_to(browser: Browser):
    payload = state_payload("nuclear")
    parts = draw_tab(browser, payload)
    assert only(parts, NUCLEAR_PAGE)["attrs"]["data-current"] == "true"
    assert only(parts, FLEET_PAGE)["attrs"]["data-current"] == "false"


def test_the_stack_page_check_reads_the_other_mode(browser: Browser):
    parts = draw_tab(browser, state_payload("looping"))
    assert only(parts, FLEET_PAGE)["attrs"]["data-current"] == "true"
    assert only(parts, NUCLEAR_PAGE)["attrs"]["data-current"] == "false"


def test_the_stack_check_names_a_page_the_selected_mode_does_not_route_to(
    js: JsRuntime,
):
    payload = state_payload("nuclear")
    payload["modes"]["stack_index"] = payload["modes"]["fleet_page_index"]
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "disagrees"]
    assert named, "the module named no wrong page"
    assert named[0]["field"] == "stack_index"


def test_the_stack_check_is_quiet_on_a_shipped_payload(js: JsRuntime):
    report = js.push(state_payload("nuclear"))
    named = [f for f in report["faults"] if f["fault"] == "disagrees"]
    assert named == [], f"a shipped stack was named: {named}"


def test_the_active_bot_dropdown_draws_one_row_per_loaded_bot(browser: Browser):
    payload = state_payload("fleet")
    draw_tab(browser, payload)
    drawn = browser.parsed(
        "Array.prototype.slice.call("
        "window.HOST.querySelectorAll('[data-part=\"active-bot-picker\"] option')"
        ").map(function (o) { return o.textContent; })"
    )
    assert drawn == [pair[0] for pair in payload["pickers"]["active"]["items"]]
    assert len(drawn) == len(FLEET_CONFIGS) + 1


def test_the_active_bot_dropdown_check_reads_a_tab_with_no_fleet_loaded(
    browser: Browser,
):
    payload = state_payload("built")
    draw_tab(browser, payload)
    drawn = browser.parsed(
        "Array.prototype.slice.call("
        "window.HOST.querySelectorAll('[data-part=\"active-bot-picker\"] option')"
        ").map(function (o) { return o.textContent; })"
    )
    assert drawn == [payload["text"]["all_bots"]]


def click(browser: Browser, part: str) -> None:
    browser.js(
        "(function () {"
        "  var one = window.HOST.querySelector('[data-part=\"" + part + "\"]');"
        "  one.dispatchEvent(new MouseEvent('click', { bubbles: true })); })()"
    )


def test_a_click_on_an_expand_button_sends_the_action_the_surface_names(
    browser: Browser,
):
    draw_tab(browser, state_payload(FULL_STATE))
    click(browser, "expand-button")
    browser.settle(SETTLE_MS)
    sent = browser.parsed("acervatorSimulatorTab.sent()")
    assert [one["action"] for one in sent] == ["chart_expand_button.clicked"]


def test_a_click_on_the_pause_button_sends_the_action_the_surface_names(
    browser: Browser,
):
    draw_tab(browser, state_payload(FULL_STATE))
    click(browser, "pause-button")
    browser.settle(SETTLE_MS)
    sent = browser.parsed("acervatorSimulatorTab.sent()")
    assert [one["action"] for one in sent] == ["activity_pause_button.toggled"]
    assert sent[0]["params"]["pause"] is True


def test_the_click_check_reads_no_action_before_a_click(browser: Browser):
    draw_tab(browser, state_payload(FULL_STATE))
    assert browser.parsed("acervatorSimulatorTab.sent()") == []


def pick(browser: Browser, part: str, at: int) -> None:
    browser.js(
        "(function () {"
        "  var one = window.HOST.querySelector('[data-part=\"" + part + "\"]');"
        "  one.value = " + json.dumps(str(at)) + ";"
        "  one.dispatchEvent(new Event('change', { bubbles: true })); })()"
    )


def test_picking_a_mode_sends_the_key_that_row_carries(browser: Browser):
    payload = state_payload(FULL_STATE)
    draw_tab(browser, payload)
    pick(browser, "mode-selector", 2)
    browser.settle(SETTLE_MS)
    sent = browser.parsed("acervatorSimulatorTab.sent()")
    assert [one["action"] for one in sent] == ["mode_selector.currentIndexChanged"]
    assert sent[0]["params"]["mode"] == payload["modes"]["items"][2][1]


def test_picking_a_chart_bot_sends_the_symbol_that_row_carries(browser: Browser):
    payload = state_payload("fleet")
    draw_tab(browser, payload)
    pick(browser, "chart-bot-picker", 1)
    browser.settle(SETTLE_MS)
    sent = browser.parsed("acervatorSimulatorTab.sent()")
    assert [one["action"] for one in sent] == ["chart_bot_picker.currentIndexChanged"]
    assert sent[0]["params"]["chart_bot"] == (
        payload["pickers"]["chart"]["items"][1][1]
    )


def test_the_active_bot_dropdown_sends_nothing_because_qt_listens_to_nothing(
    browser: Browser,
):
    payload = state_payload("fleet")
    parts = draw_tab(browser, payload)
    assert "data-action" not in only(parts, ACTIVE_PICKER)["attrs"]
    pick(browser, "active-bot-picker", 1)
    browser.settle(SETTLE_MS)
    assert browser.parsed("acervatorSimulatorTab.sent()") == []


def test_the_dropdown_check_reads_a_dropdown_that_does_send(browser: Browser):
    payload = state_payload("fleet")
    draw_tab(browser, payload)
    pick(browser, "chart-bot-picker", 1)
    browser.settle(SETTLE_MS)
    assert browser.parsed("acervatorSimulatorTab.sent()") != []


def test_picking_a_row_moves_the_dropdown_the_way_qt_moves_it(browser: Browser):
    payload = state_payload("fleet")
    draw_tab(browser, payload)
    pick(browser, "active-bot-picker", 2)
    browser.settle(SETTLE_MS)
    parts = read_parts(browser)
    assert only(parts, ACTIVE_PICKER)["attrs"]["data-index"] == "2"


SPLIT_PATHS = {
    "main_splitter": (MAIN_SPLIT, "main-splitter"),
    "top_splitter": (TOP_SPLIT, "top-splitter"),
    "log_splitter": (LOG_SPLIT, "log-splitter"),
    "indicator_splitter": (INDICATOR_SPLIT, "indicator-splitter"),
}


@pytest.mark.parametrize("name", sorted(SPLIT_PATHS))
def test_every_splitter_takes_the_orientation_and_sizes_the_surface_publishes(
    browser: Browser, name: str
):
    payload = state_payload(FULL_STATE)
    shape = payload["chrome"]
    parts = draw_tab(browser, payload)
    path = SPLIT_PATHS[name][0]
    drawn = at_path(parts, path)[0]
    turned = shape[name + "_orientation"]
    assert drawn["attrs"]["data-orientation"] == turned
    assert drawn["style"]["flexDirection"] == (
        "column" if turned == "vertical" else "row"
    )
    panes = [
        one
        for one in parts
        if one["path"] == path + "/splitter-pane"
        and one["attrs"]["data-slot"] == SPLIT_PATHS[name][1]
    ]
    assert len(panes) == 2, f"{name} drew {len(panes)} panes"
    assert [one["style"]["flexGrow"] for one in panes] == [
        str(size) for size in shape[name + "_sizes"]
    ]


@pytest.mark.parametrize("name", sorted(SPLIT_PATHS))
def test_every_splitter_handle_takes_the_width_the_surface_publishes(
    browser: Browser, name: str
):
    payload = state_payload(FULL_STATE)
    shape = payload["chrome"]
    parts = draw_tab(browser, payload)
    path = SPLIT_PATHS[name][0]
    handles = [
        one
        for one in parts
        if one["path"] == path + "/splitter-handle"
        and one["attrs"]["data-slot"] == SPLIT_PATHS[name][1]
    ]
    assert len(handles) == 1, f"{name} drew {len(handles)} handles"
    wide = pixels(shape[name + "_handle_width"])
    turned = shape[name + "_orientation"]
    read = "height" if turned == "vertical" else "width"
    assert handles[0]["style"][read] == wide
    assert handles[0]["style"]["cursor"] == (
        "row-resize" if turned == "vertical" else "col-resize"
    )


def drag(browser: Browser, part: str, by_x: int, by_y: int) -> None:
    browser.js(
        "(function () {"
        '  var one = window.HOST.querySelector(\'[data-part="splitter-handle"]'
        '[data-slot="' + part + "\"]');"
        "  var box = one.getBoundingClientRect();"
        "  var x = box.left; var y = box.top;"
        "  one.dispatchEvent(new MouseEvent('mousedown', "
        "    { bubbles: true, clientX: x, clientY: y }));"
        "  document.dispatchEvent(new MouseEvent('mousemove', "
        "    { bubbles: true, clientX: x + "
        + str(by_x)
        + ", clientY: y + "
        + str(by_y)
        + " }));"
        "  document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));"
        "})()"
    )


def test_dragging_the_log_handle_moves_the_two_panes_it_sits_between(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    before = draw_tab(browser, payload)
    panes = [
        one
        for one in before
        if one["path"] == LOG_SPLIT + "/splitter-pane"
        and one["attrs"]["data-slot"] == "log-splitter"
    ]
    was = [one["width"] for one in panes]
    drag(browser, "log-splitter", 120, 0)
    browser.settle(SETTLE_MS)
    after = read_parts(browser)
    moved = [
        one["width"]
        for one in after
        if one["path"] == LOG_SPLIT + "/splitter-pane"
        and one["attrs"]["data-slot"] == "log-splitter"
    ]
    assert moved[0] > was[0], f"{was} did not widen to {moved}"
    assert moved[1] < was[1], f"{was} did not narrow to {moved}"


def test_the_drag_check_reads_a_tab_nobody_dragged(browser: Browser):
    payload = state_payload(FULL_STATE)
    before = draw_tab(browser, payload)
    browser.settle(SETTLE_MS)
    after = read_parts(browser)
    was = [
        one["width"] for one in before if one["path"] == LOG_SPLIT + "/splitter-pane"
    ]
    now = [one["width"] for one in after if one["path"] == LOG_SPLIT + "/splitter-pane"]
    assert was == now


def test_a_drag_past_the_end_leaves_both_panes_open_because_qt_refuses_a_collapse(
    browser: Browser,
):
    payload = state_payload(FULL_STATE)
    assert payload["chrome"]["log_splitter_collapsible"] is False
    draw_tab(browser, payload)
    drag(browser, "log-splitter", 9000, 0)
    browser.settle(SETTLE_MS)
    after = read_parts(browser)
    panes = [
        one["style"]["flexGrow"]
        for one in after
        if one["path"] == LOG_SPLIT + "/splitter-pane"
        and one["attrs"]["data-slot"] == "log-splitter"
    ]
    least = payload["chrome"]["splitter_minimum"]
    assert float(panes[1]) >= least, f"a pane collapsed to {panes[1]}"


HOSTILE_SYMBOLS = {
    "markup": "<img src=x onerror=window.RAN=true>",
    "a two hundred letter symbol": "M" * 200,
    "text where a number belongs": "1234.5",
    "a number where text belongs": 12.5,
    "a true flag": True,
    "nothing at all": None,
}


def hostile_fleet(symbol: Any) -> dict:
    """The stored fleet with the first bot's symbol replaced by `symbol`."""
    fleet = json.loads(json.dumps(STORED_FLEET))
    first = sorted(fleet["bots"])[0]
    fleet["bots"][first]["config"]["symbol"] = symbol
    return fleet


@pytest.mark.parametrize("case", sorted(HOSTILE_SYMBOLS))
def test_the_tab_shows_whatever_symbol_the_stored_fleet_carried(
    js: JsRuntime, case: str
):
    configs = stored_fleet_configs(hostile_fleet(HOSTILE_SYMBOLS[case]))
    payload = bridge_payload([PANEL, {"fleet": configs}])
    js.push(payload)
    held = js.field("pickers")["active"]["items"]
    assert held == payload["pickers"]["active"]["items"], case


def test_markup_in_a_dropdown_row_is_drawn_as_text_and_runs_nothing(browser: Browser):
    configs = stored_fleet_configs(hostile_fleet(HOSTILE_SYMBOLS["markup"]))
    payload = bridge_payload([PANEL, {"fleet": configs}])
    browser.js("window.RAN = false;")
    draw_tab(browser, payload)
    drawn = browser.parsed(
        "Array.prototype.slice.call("
        "window.HOST.querySelectorAll('[data-part=\"active-bot-picker\"] option')"
        ").map(function (o) { return o.innerHTML; })"
    )
    assert any("&lt;img" in one for one in drawn), drawn
    assert browser.js("window.RAN") is False
    assert browser.parsed("document.querySelectorAll('img').length") == 0


def test_the_markup_check_reads_a_page_that_does_hold_an_image(browser: Browser):
    browser.js(
        "(function () { var img = document.createElement('img');"
        "  img.id = 'sim-probe-image';"
        "  document.body.appendChild(img); })()"
    )
    assert browser.parsed("document.querySelectorAll('img').length") == 1
    browser.js("document.getElementById('sim-probe-image').remove();")
    assert browser.parsed("document.querySelectorAll('img').length") == 0


def test_markup_in_a_log_line_is_drawn_as_text_and_runs_nothing(browser: Browser):
    payload = bridge_payload([PANEL, {"activity": [HOSTILE_SYMBOLS["markup"]]}])
    browser.js("window.RAN = false;")
    parts = draw_tab(browser, payload)
    drawn = only(parts, LOG_PANE)
    assert drawn["held"] == HOSTILE_SYMBOLS["markup"]
    assert drawn["children"] == 0
    assert browser.js("window.RAN") is False
    assert browser.parsed("document.querySelectorAll('img').length") == 0


def test_a_two_hundred_letter_symbol_is_drawn_whole_and_never_wrapped(
    browser: Browser,
):
    configs = stored_fleet_configs(
        hostile_fleet(HOSTILE_SYMBOLS["a two hundred letter symbol"])
    )
    payload = bridge_payload([PANEL, {"fleet": configs}])
    draw_tab(browser, payload)
    drawn = browser.parsed(
        "Array.prototype.slice.call("
        "window.HOST.querySelectorAll('[data-part=\"active-bot-picker\"] option')"
        ").map(function (o) { return o.textContent; })"
    )
    assert any(len(one) > 200 for one in drawn), [len(one) for one in drawn]


HOSTILE_FIELDS = ("chrome", "text", "modes", "pickers", "log", "mounts")


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
def test_a_field_that_is_a_scalar_where_a_bag_belongs_raises_no_error(
    js: JsRuntime, field: str
):
    payload = state_payload(FULL_STATE)
    payload[field] = 7
    report = js.push(payload)
    assert report["held"] is not None
    assert js.field(field) == 7


@pytest.mark.parametrize("field", HOSTILE_FIELDS)
def test_a_field_that_is_text_where_a_bag_belongs_raises_no_error(
    js: JsRuntime, field: str
):
    payload = state_payload(FULL_STATE)
    payload[field] = "not a bag"
    report = js.push(payload)
    assert report["held"] is not None
    assert js.field(field) == "not a bag"


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    named = [f for f in report["faults"] if f["fault"] in ("missing", "null")]
    assert named == [], f"a whole payload was named: {named}"


def test_a_dropdown_row_that_is_not_a_pair_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["pickers"]["active"]["items"] = ["not a pair"]
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "wrong-type"]
    assert named, "the module named no broken row"
    assert named[0]["where"] == "active"


def test_a_dropdown_row_whose_label_is_a_bag_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["pickers"]["chart"]["items"] = [[{"a": 1}, "x"]]
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "wrong-type"]
    assert named, "the module named no wrong-typed label"
    assert named[0]["where"] == "chart"


def test_a_dropdown_index_past_the_last_row_is_named(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    payload["pickers"]["chart"]["index"] = len(payload["pickers"]["chart"]["items"])
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "unplaced"]
    assert named, "the module named no index past the last row"
    assert named[0]["field"] == "index"


def test_the_dropdown_checks_are_quiet_on_a_shipped_payload(js: JsRuntime):
    report = js.push(state_payload(FULL_STATE))
    named = [f for f in report["faults"] if f["fault"] in ("wrong-type", "unplaced")]
    assert named == [], f"a shipped dropdown was named: {named}"


def test_a_log_line_that_is_a_number_is_named(js: JsRuntime):
    payload = state_payload("logged")
    payload["log"]["lines"][0] = 12
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "wrong-type"]
    assert named, "the module named no wrong-typed log line"
    assert named[0]["where"] == "log"


def test_a_log_line_that_is_null_is_named(js: JsRuntime):
    payload = state_payload("logged")
    payload["log"]["lines"][0] = None
    report = js.push(payload)
    named = [f for f in report["faults"] if f["fault"] == "null" and f["where"]]
    assert named, "the module named no null log line"


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    report = js.push(5)
    assert report["declared"] is None
    assert report["held"] is None
    assert report["faults"][0]["fault"] == "not-an-object"
    assert js.json("acervatorSimulatorTab.isLoaded()") is False


def test_a_payload_that_is_null_leaves_the_module_unloaded(js: JsRuntime):
    report = js.push(None)
    assert report["faults"][0]["fault"] == "not-an-object"
    assert report["faults"][0]["detail"] == "null"
    assert js.json("acervatorSimulatorTab.isLoaded()") is False


def test_a_stored_flag_reads_as_a_dollar_and_a_trade_and_a_unit(js: JsRuntime):
    """A stored True reaches the row as one dollar, one trade and one unit."""
    fleet = json.loads(json.dumps(STORED_FLEET))
    first = sorted(fleet["bots"])[0]
    fleet["bots"][first]["scrumming_state"]["main_lots"] = [{"units": True}]
    fleet["bots"][first]["stats"]["current_price"] = True
    fleet["bots"][first]["stats"]["total_trades"] = True
    configs = stored_fleet_configs(fleet)
    payload = bridge_payload([PANEL, {"fleet": configs}])
    js.push(payload)
    row = [one for one in js.field("table")["rows"] if one["bot_id"] == first]
    assert row, "the bot never reached the table"
    assert row[0]["current_holdings"] == 1.0
    assert row[0]["stats"]["current_price"] == 1.0
    assert row[0]["stats"]["total_trades"] == 1


def test_a_bad_stored_reading_costs_every_bot_its_row_and_the_module_says_so(
    js: JsRuntime,
):
    fleet = json.loads(json.dumps(STORED_FLEET))
    first = sorted(fleet["bots"])[0]
    fleet["bots"][first]["stats"]["current_price"] = "not-a-number"
    configs = stored_fleet_configs(fleet)
    payload = bridge_payload([PANEL, {"fleet": configs}])
    js.push(payload)
    assert js.field("table")["rows"] == []
    refused = [one for one in payload["calls"] if one[0] == "fleet.area_refused"]
    assert refused, f"the surface named no refusal: {payload['calls']}"
    assert len(payload["pickers"]["active"]["items"]) == 1


def test_the_refusal_check_reads_a_fleet_every_reading_survives(js: JsRuntime):
    payload = state_payload("fleet")
    js.push(payload)
    assert len(js.field("table")["rows"]) == len(FLEET_CONFIGS)
    refused = [one for one in payload["calls"] if one[0] == "fleet.area_refused"]
    assert refused == []


def _refuse_constant(name: str) -> Any:
    raise json.JSONDecodeError("JSON.parse refuses " + name, name, 0)


NON_FINITE_ROUTES = {
    "a stored price that is an infinity": ("current_price", "1e999", "Infinity"),
    "a stored price that is not a number": ("current_price", "NaN", "NaN"),
    "a stored holding that is an infinity": ("position_value", "1e999", "Infinity"),
}


def non_finite_payload(where: str, written: str) -> dict:
    """Runs a fleet load whose stored reading is a value JSON writes bare."""
    fleet = json.loads(json.dumps(STORED_FLEET))
    first = sorted(fleet["bots"])[0]
    fleet["bots"][first]["stats"][where] = json.loads(written)
    configs = stored_fleet_configs(fleet)
    sts.view_model({"reset": True})
    sts.view_model(PANEL)
    return sts.view_model({"fleet": configs})


@pytest.mark.parametrize("case", sorted(NON_FINITE_ROUTES))
def test_the_surface_can_emit_a_value_json_parse_refuses(case: str):
    """The bridge writes a bare word the renderer JSON parser refuses."""
    where, written, token = NON_FINITE_ROUTES[case]
    payload = non_finite_payload(where, written)
    printed = json.dumps(payload)
    assert token in printed, f"{case}: the payload holds no {token}"
    with pytest.raises(json.JSONDecodeError):
        json.loads(printed, parse_constant=_refuse_constant)


def test_the_non_finite_check_is_quiet_on_every_shipped_state():
    """No shipped state of this tab writes NaN or Infinity."""
    for name in STATE_NAMES:
        printed = json.dumps(state_payload(name))
        assert "NaN" not in printed, name
        assert "Infinity" not in printed, name


def test_a_renderer_parameter_can_reach_the_infinity_the_bridge_writes():
    """Loading 1e999 gives an infinity the stored price carries."""
    assert math.isinf(json.loads("1e999"))
    payload = non_finite_payload("current_price", "1e999")
    prices = [one["stats"]["current_price"] for one in payload["table"]["rows"]]
    assert any(math.isinf(one) for one in prices), prices


def test_a_shipped_stored_reading_stays_a_number_the_bridge_can_write():
    payload = state_payload("fleet")
    prices = [one["stats"]["current_price"] for one in payload["table"]["rows"]]
    assert all(math.isfinite(one) for one in prices), prices
    assert "Infinity" not in json.dumps(payload)


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
    js.run("acervatorLoadSimulatorTab();")
    drain_events()
    assert js.json("window.ASKED.method") == sts.METHOD
    assert js.json("acervatorSimulatorTab.isLoaded()") is True


def test_the_module_passes_a_callers_parameters_to_the_surface(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload(FULL_STATE))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadSimulatorTab({ reset: true });")
    drain_events()
    assert js.json("window.ASKED.params") == {"reset": True}


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload(FULL_STATE))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadSimulatorTab(); acervatorLoadSimulatorTab();")
    drain_events()
    assert js.json("window.TRIES") == 1


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadSimulatorTab();")
    drain_events()
    assert js.json("acervatorSimulatorTab.isLoaded()") is False
    assert js.json("acervatorSimulatorTab.loadError()") == (
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
        "acervatorLoadSimulatorTab();"
    )
    drain_events()
    assert js.json("acervatorSimulatorTab.isLoaded()") is False
    assert js.json("acervatorSimulatorTab.loadError()") == (
        "the Python backend is not running"
    )
    js.run("acervatorLoadSimulatorTab();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorSimulatorTab.isLoaded()") is True


def test_forgetting_the_model_clears_every_answer(js: JsRuntime):
    js.push(state_payload(FULL_STATE))
    assert js.json("acervatorSimulatorTab.isLoaded()") is True
    js.run("acervatorSimulatorTab.forget();")
    assert js.json("acervatorSimulatorTab.isLoaded()") is False
    assert len(js.json("acervatorSimulatorTab.declaredNames()")) > 0
    assert js.named("itemsOf", "chart") == []


def test_every_action_the_module_sends_is_one_the_surface_names(js: JsRuntime):
    payload = state_payload(FULL_STATE)
    js.push(payload)
    sending = {
        "mode_selector.currentIndexChanged",
        "chart_bot_picker.currentIndexChanged",
        "activity_pause_button.toggled",
        "chart_expand_button.clicked",
        "voting_expand_button.clicked",
    }
    named = set(js.json("acervatorSimulatorTab.actions()"))
    assert sending <= named, f"the surface names none of {sorted(sending - named)}"


def test_the_page_names_the_simulator_module_among_its_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("simulator_tab.js")]
    assert len(named) == 1, f"the page names {len(named)} Simulator modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


def test_the_page_loads_the_simulator_after_the_modules_it_resolves_through():
    """The module asks acervatorHeader and acervatorWidgets while drawing."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    order = {Path(ref).name: at for at, ref in enumerate(refs)}
    assert order["simulator_tab.js"] > order["header_strip.js"]
    assert order["simulator_tab.js"] > order["shared_widgets.js"]
    assert order["simulator_tab.js"] > order["design_tokens.js"]
