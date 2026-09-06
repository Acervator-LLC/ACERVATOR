"""Drives `trading_tab.js` against `trading_tab_surface.py`."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import theme_engine_surface as tes
from src.gui.main_tabs import trading_tab_surface as tts
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "trading_tab.js"
MERGED_PATHS = (
    WEB / "design_tokens.js",
    WEB / "theme_engine.js",
    WEB / "shared_widgets.js",
    WEB / "table_cells.js",
    WEB / "status_log.js",
    WEB / "header_strip.js",
)
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: MODULE_TAIL is the closing line a whole module file ends with.
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

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2

#: HOST_WIDTH_PX is set because an unshown view reads ``clientWidth`` as zero.
HOST_WIDTH_PX = 1400
HOST_HEIGHT_PX = 900
VIEW_SIZE_PX = (1400, 900)

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

#: NAMED_VALUE is the bridge method the module asks on, not a painted value.
NAMED_VALUE = tts.METHOD

#: NAMED_SUB_KEYS holds every nested key name the module reads.
NAMED_SUB_KEYS = {
    "accent",
    "activity_pause_button.toggled",
    "api_pause_button.toggled",
    "layer.add_button.clicked",
    "layer.placeholder_add_button.clicked",
    "add_button",
    "align",
    "background",
    "block_count",
    "blocks",
    "border",
    "border_radius_px",
    "buffered",
    "cap",
    "card",
    "checkable",
    "checked",
    "children",
    "children_collapsible",
    "color",
    "corner_widget",
    "current_exchange",
    "current_index",
    "exchange_tabs",
    "placeholder_shown",
    "font_size_px",
    "handle_width_px",
    "header_row",
    "header_row_order",
    "hint",
    "hover_background",
    "is_empty",
    "key",
    "label",
    "layout",
    "log_view",
    "margins_px",
    "max_blocks",
    "maximum_height_px",
    "minimum_size_px",
    "minimum_width_px",
    "notify_relay",
    "order",
    "padding_px",
    "orientation",
    "outer_layout",
    "page_layout",
    "pages",
    "paused",
    "pause_buffer",
    "pause_button",
    "placeholder",
    "read_only",
    "sizes_px",
    "spacing_px",
    "status_log",
    "style_sheet",
    "tab_index",
    "tab_title",
    "text",
    "title",
    "tooltip",
    "wrap",
}

#: TOKEN_GROUP_NAMES holds the token groups the length rule reads, and no
#: value the tab paints.
TOKEN_GROUP_NAMES = {
    "spacing",
    "radii",
    "target_sizes",
    "table_columns",
    "focus",
    "type_scale",
}


def api_stats(errors: int = 0, age: float = 0.0) -> dict:
    """One health reading the watchdog is given, with its render errors and age."""
    return {
        "render_errors": errors,
        "last_render_error": "boom",
        "last_render_age_sec": age,
        "paused": False,
        "pause_buffer_size": 0,
        "document_blocks": 4,
    }


def fresh_payload(**extra: Any) -> dict:
    """`build_view_model` with buffers, panes and counters of its own."""
    return tts.build_view_model(**extra)


def paused_api() -> dict:
    """The API pane with two lines held behind a paused toggle."""
    buffer = tts.ApiPauseBuffer()
    pane = tts.ApiLogPane()
    pane.append("GET /products 200 12ms")
    buffer.toggle(True)
    buffer.hold("GET /ticker 200 8ms")
    buffer.hold("GET /fills 429 900ms")
    return tts.build_view_model(api_buffer=buffer, api_pane=pane)


def resumed_api() -> dict:
    """The API pane after a resume flushed its held lines and the marker."""
    buffer = tts.ApiPauseBuffer()
    pane = tts.ApiLogPane()
    pane.append("GET /products 200 12ms")
    buffer.toggle(True)
    buffer.hold("GET /ticker 200 8ms")
    buffer.hold("GET /fills 429 900ms")
    buffer.toggle(False, pane)
    return tts.build_view_model(api_buffer=buffer, api_pane=pane)


def busy_api(count: int) -> dict:
    """The API pane holding `count` blocks, more than one view can show."""
    pane = tts.ApiLogPane()
    for at in range(count):
        pane.append("api line " + str(at))
    return tts.build_view_model(api_pane=pane)


def watched() -> dict:
    """The tab after one watchdog tick wrote every line it can write."""
    counters = tts.WatchdogState()
    written = tts.watchdog_tick(
        counters,
        api_stats(errors=3, age=2000.0),
        now=1_000_000.0,
        running=2,
        bots_active=True,
    )
    assert len(written) == 3, written
    return tts.build_view_model(watchdog=counters)


STATES = {
    "fresh": fresh_payload,
    "stock": lambda: fresh_payload(layer="stock"),
    "activity_paused": lambda: fresh_payload(activity_paused=True),
    "api_paused": paused_api,
    "api_resumed": resumed_api,
    "watched": watched,
}
STATE_NAMES = tuple(sorted(STATES))


def bridge_payload(builder=None) -> dict:
    """One state through the bridge's own `json.dumps`."""
    found = (builder or fresh_payload)()
    return json.loads(json.dumps(found, ensure_ascii=True))


def state_payload(name: str) -> dict:
    return bridge_payload(STATES[name])


def token_payload() -> dict:
    """`dss.view_model` output through the bridge's `json.dumps`."""
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def walk_payload(node: Any, keys: set, values: set) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            walk_payload(value, keys, values)
        return
    if isinstance(node, list):
        for one in node:
            walk_payload(one, keys, values)
        return
    if isinstance(node, str):
        values.add(node)


#: NAME_LISTS holds each published list whose entries name a slot.
NAME_LISTS = ("children", "order", "header_row_order", "pages")
#: NAME_FIELDS holds each published field whose value names a rule.
NAME_FIELDS = ("align", "orientation")


def naming_values(node: Any, found: set) -> None:
    """Every published string that names a slot or a rule, not a caption value."""
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            if key in NAME_LISTS and isinstance(value, list):
                found.update(one for one in value if isinstance(one, str))
            if key in NAME_FIELDS and isinstance(value, str):
                found.add(value)
            naming_values(value, found)
        return
    if isinstance(node, list):
        for one in node:
            naming_values(one, found)


def named_slots() -> set:
    found: set = set()
    for name in STATE_NAMES:
        naming_values(state_payload(name), found)
    found.discard("")
    return found


def published() -> tuple:
    """Every key name and every string value, over every state."""
    keys: set = set()
    values: set = set()
    for name in STATE_NAMES:
        walk_payload(state_payload(name), keys, values)
    values.discard("")
    keys.discard("")
    return keys, values


def as_css(value: Any) -> set:
    if isinstance(value, str):
        return {value}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {str(value)}
    return set()


def token_values() -> set:
    """Every value the token and theme tables carry, in CSS spelling."""
    found: set = set()
    for value in dss.TOKENS.values():
        found |= as_css(value)
    for theme in tes.THEMES.values():
        for value in theme.values():
            found |= as_css(value)
    found.discard("")
    return found


PUBLISHED_KEYS, PUBLISHED_VALUES = published()
NAMING_VALUES = named_slots()
PAINTED_VALUES = PUBLISHED_VALUES - NAMING_VALUES - {NAMED_VALUE}
TOKEN_VALUES = token_values()
MODULE_LITERALS = js_literals(MODULE_SOURCE)


class JsRuntime(JsEngine):
    """A QJSEngine holding ``trading_tab.js``."""

    module_path = MODULE_PATH
    setter = "acervatorSetTrading"

    def bind_text(self, name: str, written: str) -> None:
        """Set the engine global `name` to `written`, unparsed."""
        self._engine.globalObject().setProperty(name, written)

    def push_written(self, payload: Any, *writes: str) -> dict:
        """Push `payload` after running each `writes` line against it, for
        values JSON cannot spell."""
        self.bind_json("PAYLOAD", payload)
        body = "var P = JSON.parse(PAYLOAD);" + "".join(writes)
        return self.json(
            "(function () { " + body + " return acervatorSetTrading(P); })()"
        )

    def load_merged(self) -> None:
        """Run every merged module and push the design tokens in."""
        for path in MERGED_PATHS:
            self.run(path.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def named(self, call: str, name: Any) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorTrading." + call + "(JSON.parse(NAME))")

    def at(self, call: str, first: Any, second: Any) -> Any:
        self.bind_json("FIRST", first)
        self.bind_json("SECOND", second)
        return self.json(
            "acervatorTrading." + call + "(JSON.parse(FIRST), JSON.parse(SECOND))"
        )


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """A `JsRuntime` holding `MODULE_SOURCE` in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def skinned(js: JsRuntime) -> JsRuntime:
    """The `js` runtime after the merged modules and tokens are in."""
    js.load_merged()
    return js


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    declared = js.json("acervatorTrading.declaredNames()")
    missing = sorted(set(payload) - set(declared))
    assert not missing, f"{len(missing)} published fields have no name: {missing}"
    extra = sorted(set(declared) - set(payload))
    assert not extra, f"the module declares fields the surface has none of: {extra}"
    assert len(declared) == len(payload)
    differing = {
        name: (payload[name], js.named("field", name))
        for name in declared
        if js.named("field", name) != payload[name]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields "
        f"differ: {sorted(differing)}"
    )


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = dict(bridge_payload())
    payload["planted_only_on_the_surface"] = []
    js.push(payload)
    declared = js.json("acervatorTrading.declaredNames()")
    assert sorted(set(payload) - set(declared)) == ["planted_only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_declares(js: JsRuntime):
    payload = dict(bridge_payload())
    dropped = payload.pop("layers")
    assert dropped is not None
    js.push(payload)
    declared = js.json("acervatorTrading.declaredNames()")
    assert sorted(set(declared) - set(payload)) == ["layers"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == report["held"]["fields"] == len(payload)
    assert report["declared"]["layers"] == report["held"]["layers"]
    assert report["held"]["layers"] == len(payload["layers"])
    assert report["declared"]["blocks"] == report["held"]["blocks"]
    assert report["held"]["blocks"] == len(payload["api_pane"]["log_view"]["blocks"])


def test_the_count_check_reports_a_stack_promising_more_layers_than_it_carries(
    js: JsRuntime,
):
    payload = bridge_payload()
    payload["trading_stack"]["pages"] = payload["trading_stack"]["pages"] + ["extra"]
    report = js.push(payload)
    assert report["declared"]["layers"] != report["held"]["layers"]


def test_the_block_count_check_reports_a_view_promising_more_blocks(js: JsRuntime):
    payload = bridge_payload(resumed_api)
    payload["api_pane"]["log_view"]["block_count"] = len(
        payload["api_pane"]["log_view"]["blocks"]
    ) + len(payload["api_pane"]["log_view"]["blocks"])
    report = js.push(payload)
    assert report["declared"]["blocks"] != report["held"]["blocks"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_only_faults_a_published_payload_raises_are_the_qt_card_colours(
    skinned: JsRuntime, state: str
):
    """A card sheet spells two colours the way Qt reads them, so the report
    names both rather than repaint them."""
    report = skinned.push(state_payload(state))
    other = [one for one in report["faults"] if one["fault"] != "qt-colour"]
    assert other == [], f"{state}: {other}"
    named = sorted(
        (one["where"], one["detail"])
        for one in report["faults"]
        if one["fault"] == "qt-colour"
    )
    assert named == [
        ("layer:crypto", "background"),
        ("layer:crypto", "border"),
        ("layer:stock", "background"),
        ("layer:stock", "border"),
    ], named


def test_the_qt_colour_check_is_quiet_on_a_card_sheet_css_reads_the_same(
    skinned: JsRuntime,
):
    payload = bridge_payload()
    for layer in payload["layers"]:
        layer["placeholder"]["card"]["style_sheet"] = payload["layers"][0][
            "placeholder"
        ]["add_button"]["style_sheet"]
    report = skinned.push(payload)
    assert [one for one in report["faults"] if one["fault"] == "qt-colour"] == []


def test_the_qt_colour_check_reads_nothing_without_the_sheet_reader(js: JsRuntime):
    report = js.push(bridge_payload())
    assert [one for one in report["faults"] if one["fault"] == "qt-colour"] == []


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "trading_tab.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"trading_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"trading_tab.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"trading_tab.js spells out token values: {written}"


def test_every_published_value_the_module_writes_names_a_slot_or_the_method():
    assert NAMED_VALUE in set(MODULE_LITERALS["strings"])
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_VALUES
    painted = sorted(written - NAMING_VALUES)
    assert not painted, f"the module writes the painted values {painted}"


def test_the_painted_set_still_holds_every_caption_and_colour_the_tab_shows():
    """The painted set is not empty, so the check above measures something."""
    payload = bridge_payload()
    for shown in (
        payload["activity_pane"]["label"]["text"],
        payload["api_pane"]["pause_button"]["text"],
        payload["layers"][0]["add_button"]["text"],
        payload["layers"][0]["accent"],
        payload["layers"][0]["placeholder"]["hint"]["text"],
    ):
        assert shown in PAINTED_VALUES, shown


def test_the_module_names_only_the_surface_key_names_it_must_read(js: JsRuntime):
    js.push(bridge_payload())
    allowed = set(js.json("acervatorTrading.declaredNames()")) | NAMED_SUB_KEYS
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_KEYS
    assert not written - allowed, f"the module names {sorted(written - allowed)} more"
    assert (
        not NAMED_SUB_KEYS - written
    ), f"the list allows {sorted(NAMED_SUB_KEYS - written)} the module never writes"


def test_the_module_asks_for_a_layer_page_under_the_name_the_surface_reads(
    js: JsRuntime,
):
    """A tab click sends a field name ``view_model`` never looks at."""
    asked = js.json("acervatorTrading.exchangeParam")
    assert asked == tts.EXCHANGE_PARAM, asked
    card = tts.layer_card("crypto", {"kraken": "Kraken", "coinbase": "Coinbase"})
    assert card["current_exchange"] == "kraken", card
    chosen = tts.build_view_model(
        exchanges=[
            {"exchange_id": "kraken", "display_name": "Kraken"},
            {"exchange_id": "coinbase", "display_name": "Coinbase"},
        ],
        current_exchange="coinbase",
    )
    assert chosen["layers"][0]["current_exchange"] == "coinbase", chosen["layers"][0]


def test_the_token_group_names_the_module_writes_are_no_value_it_paints():
    written = set(MODULE_LITERALS["strings"]) & TOKEN_GROUP_NAMES
    assert written == TOKEN_GROUP_NAMES, f"the module names only {sorted(written)}"
    assert not TOKEN_GROUP_NAMES & PUBLISHED_VALUES
    assert not TOKEN_GROUP_NAMES & TOKEN_VALUES


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "trading_tab.js holds a slash outside a comment, which the literal "
        f"scan cannot read: {MODULE_LITERALS['slashes']}"
    )


SAMPLE = bridge_payload()

SPELLED_OUT_LINES = {
    "colour": 'var spelled = "#00ffcc";',
    "token_value": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "accent": 'var spelled = "' + SAMPLE["layers"][0]["accent"] + '";',
    "caption": 'var spelled = "' + tts.ACTIVITY_PAUSE_TEXT + '";',
    "tab_title": 'var spelled = "' + tts.PLACEHOLDER_TAB_TITLE + '";',
    "marker": 'var spelled = "' + tts.resume_marker(2) + '";',
    "handle_width": "var spelled = " + str(tts.HANDLE_WIDTH_PX) + ";",
    "block_cap": "var spelled = " + str(tts.API_LOG_MAX_BLOCKS) + ";",
    "number": "var spelled = 12;",
    "regex": "var spelled = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the five checks report on ``source``."""
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
        assert runtime.json("typeof acervatorSetTrading") == "function", kind


def python_kinds(payload: dict) -> dict:
    """The JavaScript type of every value of ``payload``, by dotted path."""
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
    wanted = python_kinds(payload)
    found = js.json("acervatorTrading.kinds()")
    differing = {
        path: (kind, found.get(path))
        for path, kind in wanted.items()
        if found.get(path) != kind
    }
    assert not differing, f"{state}: {len(differing)} values changed type: {differing}"
    assert len(found) == len(wanted)


def test_the_type_check_names_a_value_that_changed_shape(js: JsRuntime):
    payload = bridge_payload()
    wanted = python_kinds(payload)
    payload["main_splitter"]["handle_width_px"] = "5"
    js.push(payload)
    found = js.json("acervatorTrading.kinds()")
    differing = [path for path, kind in wanted.items() if found.get(path) != kind]
    assert differing == ["main_splitter.handle_width_px"], differing


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_splitter_agrees_with_the_surface(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    names = js.json("acervatorTrading.splitterNames()")
    assert sorted(names) == sorted(
        [
            "main_splitter",
            "top_splitter",
            "bottom_splitter",
            "log_splitter",
        ]
    )
    for name in names:
        assert js.named("splitter", name) == payload[name], f"{state}: {name}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_layer_agrees_with_the_surface(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for card in payload["layers"]:
        assert js.named("layer", card["key"]) == card, f"{state}: {card['key']}"
    assert js.json("acervatorTrading.layers()") == payload["layers"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_both_log_panes_agree_with_the_surface(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    assert js.json("acervatorTrading.activityPane()") == payload["activity_pane"]
    assert js.json("acervatorTrading.apiPane()") == payload["api_pane"]
    assert js.json("acervatorTrading.logView()") == payload["api_pane"]["log_view"]
    assert (
        js.json("acervatorTrading.pauseBuffer()") == payload["api_pane"]["pause_buffer"]
    )
    assert js.json("acervatorTrading.watchdog()") == payload["watchdog"]


def test_the_splitter_check_names_a_splitter_read_from_the_wrong_place(js: JsRuntime):
    payload = bridge_payload()
    js.push(payload)
    assert js.named("splitter", "main_splitter") != js.named("splitter", "top_splitter")
    assert js.named("splitter", "not_a_splitter") is None


def test_a_reader_returns_nothing_for_an_inherited_javascript_name(js: JsRuntime):
    js.push(bridge_payload())
    for name in ("constructor", "toString", "hasOwnProperty", "__proto__"):
        assert js.named("field", name) is None, name
        assert js.named("action", name) is None, name
        assert js.named("layer", name) is None, name
        assert js.named("splitter", name) is None, name


def test_the_inherited_name_check_still_reads_a_real_field(js: JsRuntime):
    payload = bridge_payload()
    js.push(payload)
    assert js.named("field", "tab_title") == payload["tab_title"]
    assert (
        js.named("action", "activity_pause_button.toggled")
        == payload["actions"]["activity_pause_button.toggled"]
    )
    assert js.named("layer", "crypto")["label"] == payload["layers"][0]["label"]


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._view.resize(*VIEW_SIZE_PX)
        self.open_page()
        self.wait_for_module()

    def open_page(self) -> None:
        """Loads the renderer page and waits until its load finishes."""
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
        """Opens the page again while the module global stays absent."""
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.js("typeof window.acervatorSetTrading") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the trading module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
            + ", header "
            + str(self.js("typeof window.acervatorSetHeader"))
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
    "color",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "textAlign",
    "whiteSpace",
    "cursor",
    "display",
    "flexDirection",
    "gap",
    "minWidth",
    "minHeight",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderTopLeftRadius",
]

#: EXPANDED maps a Qt shorthand to the properties it settles into.
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
    "window.HOST = document.getElementById('trading-host');"
    "if (!window.HOST) {"
    "  window.HOST = document.createElement('div');"
    "  window.HOST.id = 'trading-host';"
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
    """Push `token_payload` into the page and apply it, since a disk-loaded
    view has no bridge."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_tab(browser: Browser, payload: dict) -> list:
    """Render `payload` into `window.HOST` and return what `READ_PARTS` finds."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetTrading(JSON.parse(window.PAYLOAD));"
        "acervatorTrading.renderTab(window.HOST);"
    )
    return read_parts(browser)


def read_parts(browser: Browser) -> list:
    """What `READ_PARTS` finds, without rendering again."""
    return json.loads(browser.js(READ_PARTS))


def declarations_of(sheet: Any) -> list:
    """Each property and value of `sheet`, read in Python rather than
    through the module."""
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


def by_slot(parts: list, name: str) -> list:
    return [one for one in parts if one["attrs"].get("data-slot") == name]


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorTrading") == "object"
    assert browser.js("typeof window.acervatorSetTrading") == "function"
    assert browser.js("typeof window.acervatorLoadTrading") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_tab(browser, bridge_payload())
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


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_drawn_tab_shows_every_caption_the_surface_published(
    browser: Browser, state: str
):
    payload = state_payload(state)
    parts = draw_tab(browser, payload)
    wanted = [
        payload["activity_pane"]["label"]["text"],
        payload["api_pane"]["label"]["text"],
        payload["activity_pane"]["pause_button"]["text"],
        payload["api_pane"]["pause_button"]["text"],
    ]
    drawn = [one["text"] for one in by_part(parts, "pane-label")] + [
        one["text"] for one in by_part(parts, "pause-button")
    ]
    assert drawn == wanted, f"{state}: drawn {drawn} against published {wanted}"


def test_the_caption_check_names_one_changed_caption(browser: Browser):
    payload = bridge_payload()
    before = [one["text"] for one in by_part(draw_tab(browser, payload), "pane-label")]
    payload["activity_pane"]["label"]["text"] = "changed-caption"
    after = [one["text"] for one in by_part(draw_tab(browser, payload), "pane-label")]
    assert before != after
    assert "changed-caption" in after


def test_the_drawn_tab_shows_both_layers_and_marks_the_one_on_show(browser: Browser):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    pages = by_part(parts, "page")
    assert [one["attrs"]["data-layer"] for one in pages] == [
        card["key"] for card in payload["layers"]
    ]
    shown = [one for one in pages if one["attrs"]["data-current"] == "true"]
    assert len(shown) == 1
    assert (
        shown[0]["attrs"]["data-layer"]
        == payload["trading_stack"]["pages"][payload["trading_stack"]["current_index"]]
    )


def test_the_layer_check_reads_the_stock_layer_as_the_one_on_show(browser: Browser):
    payload = state_payload("stock")
    parts = draw_tab(browser, payload)
    shown = [one for one in by_part(parts, "page") if one["attrs"]["data-current"]]
    marked = [one for one in shown if one["attrs"]["data-current"] == "true"]
    assert len(marked) == 1
    assert marked[0]["attrs"]["data-layer"] == "stock"


def test_the_drawn_tab_shows_each_empty_state_card_the_surface_published(
    browser: Browser,
):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    titles = [one["text"] for one in by_part(parts, "placeholder-title")]
    hints = [one["text"] for one in by_part(parts, "placeholder-hint")]
    adds = [one["text"] for one in by_part(parts, "placeholder-add")]
    assert titles == [
        card["placeholder"]["title"]["text"] for card in payload["layers"]
    ]
    assert hints == [card["placeholder"]["hint"]["text"] for card in payload["layers"]]
    assert adds == [
        card["placeholder"]["add_button"]["text"] for card in payload["layers"]
    ]


def test_the_drawn_corner_add_button_carries_the_caption_and_tooltip(
    browser: Browser,
):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    buttons = by_part(parts, "add-button")
    assert [one["text"] for one in buttons] == [
        card["add_button"]["text"] for card in payload["layers"]
    ]
    assert [one["attrs"].get("title") for one in buttons] == [
        card["add_button"]["tooltip"] for card in payload["layers"]
    ]


def test_every_drawn_child_a_check_reads_carries_a_name(browser: Browser):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    unnamed = [
        one["path"]
        for one in parts
        if not any(
            key in one["attrs"]
            for key in (
                "data-slot",
                "data-key",
                "data-layer",
                "data-index",
                "aria-label",
            )
        )
    ]
    assert not unnamed, f"{len(unnamed)} drawn parts carry no name: {unnamed}"


@pytest.mark.parametrize(
    "part,sheet_of",
    [
        ("pane-label", lambda p: p["activity_pane"]["label"]["style_sheet"]),
        (
            "placeholder-title",
            lambda p: p["layers"][0]["placeholder"]["title"]["style_sheet"],
        ),
        (
            "placeholder-hint",
            lambda p: p["layers"][0]["placeholder"]["hint"]["style_sheet"],
        ),
    ],
)
def test_a_drawn_part_matches_a_probe_styled_from_the_surface(
    browser: Browser, part: str, sheet_of
):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    drawn = by_part(parts, part)
    assert drawn, f"nothing was drawn for {part}"
    expected = probe(browser, "div", css_body(sheet_of(payload)))
    assert expected, f"the surface declared nothing for {part}"
    differing = {
        name: (value, drawn[0]["style"].get(name))
        for name, value in expected.items()
        if drawn[0]["style"].get(name) != value
    }
    assert not differing, f"{part}: {differing}"


def test_the_probe_check_names_one_changed_declaration(browser: Browser):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    drawn = by_part(parts, "placeholder-title")[0]
    sheet = payload["layers"][0]["placeholder"]["title"]["style_sheet"]
    changed = css_body(sheet).replace(str(dss.TEXT_INACTIVE), str(dss.ERROR))
    expected = probe(browser, "div", changed)
    assert drawn["style"]["color"] != expected["color"]


def test_the_drawn_pause_button_matches_a_probe_styled_from_its_own_sheet(
    browser: Browser,
):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    for slot in ("activity_pane", "api_pane"):
        drawn = [
            one
            for one in by_part(parts, "pause-button")
            if one["attrs"]["data-slot"] == slot
        ]
        assert len(drawn) == 1, slot
        sheet = payload[slot]["pause_button"]["style_sheet"]
        expected = probe(browser, "button", css_body(sheet.split("}")[0] + "}"))
        differing = {
            name: (value, drawn[0]["style"].get(name))
            for name, value in expected.items()
            if drawn[0]["style"].get(name) != value
        }
        assert not differing, f"{slot}: {differing}"


def test_the_drawn_card_carries_no_colour_the_browser_would_read_differently(
    browser: Browser,
):
    """The card draws neither its fill nor its border, rather than a colour
    Qt never paints."""
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    cards = by_part(parts, "placeholder-card")
    assert cards
    opaque = probe(browser, "div", "background: rgba(0,255,204,8)")
    for card in cards:
        assert card["style"]["backgroundColor"] != opaque["backgroundColor"]
        assert card["style"]["borderTopStyle"] == "none"


def test_the_card_check_reads_the_opaque_colour_a_copy_would_have_painted(
    browser: Browser,
):
    payload = bridge_payload()
    draw_tab(browser, payload)
    opaque = probe(browser, "div", "background: rgba(0,255,204,8)")
    assert opaque["backgroundColor"] == "rgb(0, 255, 204)"


def test_the_drawn_card_keeps_the_radius_the_surface_published(browser: Browser):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    card = by_part(parts, "placeholder-card")[0]
    expected = probe(browser, "div", "border-radius: 6px")
    assert card["style"]["borderTopLeftRadius"] == expected["borderTopLeftRadius"]


def test_the_drawn_api_log_shows_its_placeholder_while_it_holds_nothing(
    browser: Browser,
):
    payload = bridge_payload()
    assert payload["api_pane"]["log_view"]["is_empty"] is True
    parts = draw_tab(browser, payload)
    empty = one_part(parts, "api-placeholder")
    assert empty["text"] == payload["api_pane"]["log_view"]["placeholder"]
    assert not by_part(parts, "api-block")


def test_the_drawn_api_log_shows_every_block_the_surface_published(browser: Browser):
    payload = state_payload("api_resumed")
    assert payload["api_pane"]["log_view"]["is_empty"] is False
    parts = draw_tab(browser, payload)
    drawn = [one["text"] for one in by_part(parts, "api-block")]
    assert drawn == payload["api_pane"]["log_view"]["blocks"]
    assert not by_part(parts, "api-placeholder")


def test_the_drawn_api_log_refuses_to_wrap_where_the_surface_refuses(
    browser: Browser,
):
    payload = state_payload("api_resumed")
    assert payload["api_pane"]["log_view"]["wrap"] is False
    parts = draw_tab(browser, payload)
    view = one_part(parts, "api-log")
    assert view["style"]["whiteSpace"] == "pre"
    assert view["attrs"]["data-wrap"] == "false"


def test_the_wrap_check_reads_a_wrapping_view_as_wrapping(browser: Browser):
    payload = state_payload("api_resumed")
    payload["api_pane"]["log_view"]["wrap"] = True
    parts = draw_tab(browser, payload)
    view = one_part(parts, "api-log")
    assert view["style"]["whiteSpace"] == "pre-wrap"


def test_the_drawn_api_log_takes_the_focus_the_surface_published(browser: Browser):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    view = one_part(parts, "api-log")
    assert view["attrs"]["tabindex"] == str(
        payload["api_pane"]["log_view"]["tab_index"]
    )
    assert view["attrs"]["aria-readonly"] == "true"


def test_the_focus_check_reads_a_view_the_surface_keeps_out_of_tab_order(
    browser: Browser,
):
    payload = bridge_payload()
    payload["api_pane"]["log_view"]["tab_index"] = -1
    parts = draw_tab(browser, payload)
    assert one_part(parts, "api-log")["attrs"]["tabindex"] == "-1"


def changed_paths(before: list, after: list) -> set:
    """Every (part, property) whose computed value moved between reads."""
    assert len(before) == len(after), "the tab drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((at, key))
    return moved


def test_the_drawn_tab_follows_a_colour_token_and_nothing_else_moves(
    browser: Browser,
):
    payload = bridge_payload()
    before = draw_tab(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty('--PRIMARY', "
        + json.dumps(str(dss.ERROR))
        + ");"
    )
    after = read_parts(browser)
    moved = changed_paths(before, after)
    assert moved, "the token moved nothing at all"
    assert {key for _, key in moved} == {
        "color",
        "borderTopColor",
    }, f"an unset border colour is currentColor, so only these move: {moved}"
    names = {before[at]["attrs"]["data-part"] for at, _ in moved}
    assert names == {"pane-label"}, f"the token moved {sorted(names)}"


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(
    browser: Browser,
):
    payload = bridge_payload()
    before = draw_tab(browser, payload)
    assert changed_paths(before, read_parts(browser)) == set()


def test_the_length_rule_takes_a_token_only_from_a_group_that_means_a_length(
    skinned: JsRuntime,
):
    """A length borrows the radius token and refuses the display type size
    that carries the same number."""
    skinned.push(bridge_payload())
    assert skinned.named("variableFor", dss.RADIUS_CARD) == "RADIUS_CARD"
    assert skinned.named("length", dss.RADIUS_CARD) == (
        "calc(var(--RADIUS_CARD, 6) * 1px)"
    )
    assert skinned.named("variableFor", dss.TYPE_DISPLAY) == "TYPE_DISPLAY"
    assert skinned.named("length", dss.TYPE_DISPLAY) == "36px"
    assert skinned.named("fontSize", dss.TYPE_DISPLAY) == (
        "calc(var(--TYPE_DISPLAY, 36) * 1px)"
    )


def test_no_size_the_tab_publishes_borrows_a_token_that_means_another_thing(
    skinned: JsRuntime,
):
    payload = bridge_payload()
    skinned.push(payload)
    borrowed = {}
    for name in ("main_splitter", "top_splitter", "bottom_splitter", "log_splitter"):
        for size in payload[name]["sizes_px"] + [payload[name]["handle_width_px"]]:
            found = skinned.named("length", size)
            if not str(found).endswith("px") or found.startswith("calc("):
                borrowed[str(size)] = found
    assert not borrowed, f"a splitter size borrowed a token: {borrowed}"


HOVER_OVER = (
    "(function () {"
    "  var el = document.querySelector('[data-part=\"pause-button\"]');"
    "  el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));"
    "  return true; })()"
)
HOVER_OUT = (
    "(function () {"
    "  var el = document.querySelector('[data-part=\"pause-button\"]');"
    "  el.dispatchEvent(new MouseEvent('mouseout', { bubbles: true }));"
    "  return true; })()"
)


def test_the_pause_button_paints_its_hover_skin_while_the_pointer_is_over_it(
    browser: Browser,
):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    resting = by_part(parts, "pause-button")[0]
    assert browser.js(HOVER_OVER) is True
    hovered = by_part(read_parts(browser), "pause-button")[0]
    expected = probe(
        browser,
        "button",
        "background:" + payload["activity_pane"]["pause_button"]["hover_background"],
    )
    assert hovered["attrs"]["data-hovered"] == "true"
    assert hovered["style"]["backgroundColor"] == expected["backgroundColor"]
    assert hovered["style"]["backgroundColor"] != resting["style"]["backgroundColor"]


def test_the_hover_check_reads_the_resting_skin_again_once_the_pointer_leaves(
    browser: Browser,
):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    resting = by_part(parts, "pause-button")[0]["style"]["backgroundColor"]
    browser.js(HOVER_OVER)
    browser.js(HOVER_OUT)
    left = by_part(read_parts(browser), "pause-button")[0]
    assert left["attrs"]["data-hovered"] == "false"
    assert left["style"]["backgroundColor"] == resting


def test_the_checked_activity_button_paints_the_skin_its_sheet_names(
    browser: Browser,
):
    running = bridge_payload()
    paused = state_payload("activity_paused")
    assert paused["activity_pane"]["pause_button"]["checked"] is True
    before = by_part(draw_tab(browser, running), "pause-button")[0]
    after = by_part(draw_tab(browser, paused), "pause-button")[0]
    expected = probe(
        browser,
        "button",
        "background:"
        + paused["activity_pane"]["pause_button"]["checked_background"]
        + ";color:"
        + paused["activity_pane"]["pause_button"]["checked_color"],
    )
    assert after["style"]["backgroundColor"] == expected["backgroundColor"]
    assert after["style"]["color"] == expected["color"]
    assert after["style"]["backgroundColor"] != before["style"]["backgroundColor"]
    assert after["attrs"]["aria-pressed"] == "true"


def test_the_api_button_keeps_one_skin_because_its_sheet_names_no_checked_rule(
    browser: Browser,
):
    """A paused API log differs from a running one only in its caption."""
    running = bridge_payload()
    paused = bridge_payload(paused_api)
    assert paused["api_pane"]["pause_button"]["checked"] is True
    before = by_slot(draw_tab(browser, running), "api_pane")
    after = by_slot(draw_tab(browser, paused), "api_pane")
    resting = [one for one in before if one["attrs"]["data-part"] == "pause-button"][0]
    checked = [one for one in after if one["attrs"]["data-part"] == "pause-button"][0]
    assert checked["style"] == resting["style"]
    assert checked["text"] != resting["text"]


#: BUSY_LINES is more blocks than one view of the host height can show.
BUSY_LINES = 400
#: A scroll position is fractional while the extent it is read against is not.
SUBPIXEL = 1

READ_SCROLL = (
    "(function () {"
    "  var el = window.HOST.querySelector('[data-part=\"api-log\"]');"
    "  return [el.scrollTop, el.scrollHeight - el.clientHeight]; })()"
)

SCROLL_TO_TOP = (
    "(function () {"
    "  var el = window.HOST.querySelector('[data-part=\"api-log\"]');"
    "  el.scrollTop = 0;"
    "  el.dispatchEvent(new Event('scroll'));"
    "  return el.scrollTop; })()"
)


def test_the_api_log_follows_its_newest_block_while_the_reader_is_at_the_bottom(
    browser: Browser,
):
    draw_tab(browser, state_payload("api_resumed"))
    draw_tab(browser, bridge_payload(lambda: busy_api(BUSY_LINES)))
    at, most = browser.parsed(READ_SCROLL)
    assert most > 0, "the view never grew past its own height"
    assert most - at < SUBPIXEL, f"the view stopped at {at} of {most}"


def test_the_api_log_stays_where_the_reader_put_it_once_it_is_not_at_the_bottom(
    browser: Browser,
):
    draw_tab(browser, bridge_payload(lambda: busy_api(BUSY_LINES)))
    assert browser.parsed(SCROLL_TO_TOP) == 0
    draw_tab(browser, bridge_payload(lambda: busy_api(BUSY_LINES + BUSY_LINES)))
    at, most = browser.parsed(READ_SCROLL)
    assert most > 0
    assert at == 0, f"the view moved to {at} of {most} without being asked"


LOG_SPLITTER_PANES = (
    "window.HOST.querySelector("
    '  \'[data-part="splitter"][data-slot="log_splitter"]\')'
    ".querySelectorAll(':scope > [data-part=\"pane\"]')"
)

FIRST_PANE_WIDTH = (
    "(function () { var panes = " + LOG_SPLITTER_PANES + ";"
    "  return panes[0].getBoundingClientRect().width; })()"
)

DRAG_HANDLE = (
    "(function (pixels) {"
    "  var root = window.HOST.querySelector("
    '    \'[data-part="splitter"][data-slot="log_splitter"]\');'
    "  var handle = root.querySelector(':scope > [data-part=\"handle\"]');"
    "  var box = handle.getBoundingClientRect();"
    "  handle.dispatchEvent(new MouseEvent('mousedown',"
    "    { bubbles: true, clientX: box.left, clientY: box.top }));"
    "  document.dispatchEvent(new MouseEvent('mousemove',"
    "    { bubbles: true, clientX: box.left + pixels, clientY: box.top }));"
    "  document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));"
    "  return true; })"
)


def drag_handle(browser: Browser, pixels: int) -> tuple:
    """Drag the log splitter's handle `pixels` across and return the first
    pane's width before and after."""
    before = browser.parsed(FIRST_PANE_WIDTH)
    assert browser.js(DRAG_HANDLE + "(" + str(pixels) + ")") is True
    browser.settle(SETTLE_MS)
    return before, browser.parsed(FIRST_PANE_WIDTH)


def test_dragging_a_splitter_handle_moves_the_pane_beside_it(browser: Browser):
    draw_tab(browser, bridge_payload())
    before, after = drag_handle(browser, 120)
    assert after > before, f"the pane went from {before} to {after}"
    assert round(after - before) == 120, f"the pane moved {after - before}"


def test_the_drag_check_reads_an_untouched_splitter_as_untouched(browser: Browser):
    draw_tab(browser, bridge_payload())
    before = browser.parsed(FIRST_PANE_WIDTH)
    browser.settle(SETTLE_MS)
    assert browser.parsed(FIRST_PANE_WIDTH) == before


def test_a_splitter_that_may_not_collapse_keeps_its_pane_at_the_handle_width(
    browser: Browser,
):
    payload = bridge_payload()
    assert payload["log_splitter"]["children_collapsible"] is False
    draw_tab(browser, payload)
    before, after = drag_handle(browser, -100000)
    assert after < before
    assert round(after) == payload["log_splitter"]["handle_width_px"], after


def status_log_payload(messages: list) -> dict:
    """One `status_log` view model carrying `messages` in a pane of its own."""
    from src.gui.main_tabs import status_log_surface as sls

    found = sls.build_view_model(
        sls.StatusLogModel(), [{"message": one} for one in messages]
    )
    return json.loads(json.dumps(found, ensure_ascii=True))


LOG_MESSAGES = ["first line", "second line"]

READ_HOSTED_LOG = (
    "(function () {"
    "  var slot = window.HOST.querySelector('[data-part=\"status-log\"]');"
    "  var log = slot.querySelector('[data-part=\"log\"]');"
    "  if (!log) { return null; }"
    "  return Array.prototype.slice.call("
    "    log.querySelectorAll('[data-part=\"message\"]')"
    "  ).map(function (n) { return n.textContent; }); })()"
)


def test_the_tab_hosts_the_merged_activity_log_rather_than_drawing_its_own(
    browser: Browser,
):
    draw_tab(browser, bridge_payload())
    browser.js(
        "window.LOG = " + json.dumps(json.dumps(status_log_payload(LOG_MESSAGES))) + ";"
        "acervatorSetLog(JSON.parse(window.LOG));"
        "acervatorTrading.renderActivityLog(window.HOST);"
    )
    assert browser.parsed(READ_HOSTED_LOG) == LOG_MESSAGES


def test_the_hosting_check_finds_nothing_before_the_log_module_is_asked(
    browser: Browser,
):
    draw_tab(browser, bridge_payload())
    assert browser.parsed(READ_HOSTED_LOG) is None


#: Values JSON carries unchanged, written into one published caption.
HOSTILE_TEXTS = {
    "a true flag": True,
    "nothing at all": None,
    "a two hundred character caption": "X" * 200,
    "markup": "<script>alert(1)</script>",
    "an empty caption": "",
}

#: HOSTILE_AMOUNTS holds numbers where text belongs.
HOSTILE_AMOUNTS = {
    "a number where text belongs": 1.0,
    "a very large integer": 10**24,
}

HOSTILE_ALL = dict(HOSTILE_TEXTS)
HOSTILE_ALL.update(HOSTILE_AMOUNTS)

#: Values JSON cannot spell, written into the parsed payload instead.
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
def test_the_tab_holds_whatever_caption_the_surface_produced(js: JsRuntime, case: str):
    payload = bridge_payload()
    payload["activity_pane"]["label"]["text"] = HOSTILE_ALL[case]
    js.push(payload)
    shown = js.json("acervatorTrading.activityPane()")["label"]["text"]
    assert shown == HOSTILE_ALL[case] or float(shown) == float(HOSTILE_ALL[case])


@pytest.mark.parametrize("case", sorted(HOSTILE_ALL))
def test_the_drawn_tab_shows_a_hostile_caption_as_text_and_not_as_markup(
    browser: Browser, case: str
):
    payload = bridge_payload()
    payload["activity_pane"]["label"]["text"] = HOSTILE_ALL[case]
    parts = draw_tab(browser, payload)
    drawn = by_part(parts, "pane-label")[0]
    wanted = js_spelling(browser, HOSTILE_ALL[case])
    assert drawn["text"] == wanted, f"{case}: the tab shows {drawn['text']!r}"
    assert (
        browser.js(
            "window.HOST.querySelector('[data-part=\"pane-label\"]')"
            ".getElementsByTagName('*').length"
        )
        == 0
    )


@pytest.mark.parametrize("case", sorted(HOSTILE_NUMBERS))
def test_the_tab_holds_a_number_json_cannot_spell(js: JsRuntime, case: str):
    payload = bridge_payload()
    js.push_written(
        payload,
        "P.main_splitter.handle_width_px = " + HOSTILE_NUMBERS[case] + ";",
    )
    shown = js.named("splitter", "main_splitter")["handle_width_px"]
    assert shown is None or isinstance(shown, float), f"{case}: {shown!r}"


def test_this_surface_can_put_a_bare_not_a_number_on_the_bridge(js: JsRuntime):
    """Issue #257: a watchdog tick given a bad clock writes a float no
    frame can parse."""
    counters = tts.WatchdogState()
    counters.alert_sent_at = float("nan")
    written = json.dumps(tts.build_view_model(watchdog=counters))
    assert "NaN" in written
    js.bind_text("BROKEN", written)
    result = js.run(
        "(function () { try { JSON.parse(BROKEN); return 'parsed'; }"
        " catch (e) { return e.name; } })()"
    )
    assert result.toString() == "SyntaxError"


def test_no_bridge_parameter_can_put_a_bare_not_a_number_on_the_bridge():
    """No parameter the handler reads reaches a float, so the bridge cannot
    write that frame."""
    hostile = {
        "layer": float("nan"),
        "activity_paused": float("nan"),
        "api_paused": None,
        "api_lines": [float("nan"), float("inf")],
    }
    written = json.dumps(tts.view_model(hostile))
    assert "NaN" not in written
    assert "Infinity" not in written
    tts.API_LOG_PANE.clear()


def test_the_bridge_check_parses_a_whole_payload(js: JsRuntime):
    written = json.dumps(bridge_payload())
    assert "NaN" not in written
    js.bind_text("WHOLE", written)
    result = js.run(
        "(function () { try { JSON.parse(WHOLE); return 'parsed'; }"
        " catch (e) { return e.name; } })()"
    )
    assert result.toString() == "parsed"


@pytest.mark.parametrize("field", sorted(tts.build_view_model()))
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


@pytest.mark.parametrize("field", sorted(tts.build_view_model()))
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


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(bridge_payload())
    kinds = [one["fault"] for one in report["faults"]]
    assert "missing" not in kinds
    assert "null" not in kinds


#: HELD_TYPES names each place the surface publishes the same field twice,
#: so one copy holds the other's type.
HELD_TYPES = {
    "a splitter handle width that is text": (
        ["top_splitter", "handle_width_px"],
        "5",
        "splitter:top_splitter",
        "handle_width_px",
    ),
    "a splitter size list that is a number": (
        ["log_splitter", "sizes_px"],
        7,
        "splitter:log_splitter",
        "sizes_px",
    ),
    "a layer label that is a number": (
        ["layers", 1, "label"],
        3,
        "layer:stock",
        "label",
    ),
    "a layer placeholder that is text": (
        ["layers", 1, "placeholder"],
        "gone",
        "layer:stock",
        "placeholder",
    ),
    "an api caption that is a number": (
        ["api_pane", "pause_button", "text"],
        9,
        "pane:api_pane",
        "text",
    ),
    "an api font size that is text": (
        ["api_pane", "pause_button", "font_size_px"],
        "11",
        "pane:api_pane",
        "font_size_px",
    ),
}


def put(payload: dict, path: list, value: Any) -> None:
    node: Any = payload
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value


@pytest.mark.parametrize("case", sorted(HELD_TYPES))
def test_a_wrong_type_is_named_where_the_surface_publishes_the_field_twice(
    js: JsRuntime, case: str
):
    path, value, where, field = HELD_TYPES[case]
    payload = bridge_payload()
    put(payload, path, value)
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "wrong-type" and one["where"] == where
    ]
    assert named and named[0]["field"] == field, f"{case}: {report['faults']}"


def test_the_wrong_type_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    for name in STATE_NAMES:
        report = js.push(state_payload(name))
        named = [one for one in report["faults"] if one["fault"] == "wrong-type"]
        assert named == [], f"{name}: {named}"


def test_a_layer_the_stack_never_named_is_reported(js: JsRuntime):
    payload = bridge_payload()
    payload["layers"][1]["key"] = "unnamed"
    report = js.push(payload)
    assert {
        "where": "layer:unnamed",
        "field": "key",
        "fault": "unslotted",
        "detail": None,
    } in report["faults"]


def test_an_alias_the_stack_never_named_is_reported(js: JsRuntime):
    payload = bridge_payload()
    payload["alias_layer"] = "neither"
    report = js.push(payload)
    assert {
        "where": None,
        "field": "alias_layer",
        "fault": "unslotted",
        "detail": "neither",
    } in report["faults"]


def test_a_paused_buffer_the_button_disagrees_with_is_reported(js: JsRuntime):
    payload = bridge_payload(paused_api)
    payload["api_pane"]["pause_button"]["checked"] = False
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "disagrees" and one["field"] == "checked"
    ]
    assert len(named) == 1, report["faults"]


def test_a_log_view_whose_blocks_and_count_disagree_is_reported(js: JsRuntime):
    payload = bridge_payload(resumed_api)
    payload["api_pane"]["log_view"]["block_count"] = 0
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "disagrees" and one["field"] == "block_count"
    ]
    assert len(named) == 1, report["faults"]


def test_a_pause_button_whose_sheet_and_fields_disagree_is_reported(
    skinned: JsRuntime,
):
    payload = bridge_payload()
    payload["activity_pane"]["pause_button"]["color"] = str(dss.SUCCESS)
    report = skinned.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["fault"] == "disagrees" and one["field"] == "color"
    ]
    assert len(named) == 1, report["faults"]


def test_the_sheet_agreement_check_is_quiet_without_the_sheet_reader(js: JsRuntime):
    payload = bridge_payload()
    payload["activity_pane"]["pause_button"]["color"] = str(dss.SUCCESS)
    report = js.push(payload)
    assert report["faults"] == [] or all(
        one["fault"] != "disagrees" for one in report["faults"]
    ), "the plain engine read a sheet it has no reader for"


def test_a_layer_that_is_not_an_object_is_named(js: JsRuntime):
    payload = bridge_payload()
    payload["layers"][0] = "not a layer"
    report = js.push(payload)
    assert {
        "where": "layer:0",
        "field": None,
        "fault": "not-an-object",
        "detail": "string",
    } in report["faults"]


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    js.push(bridge_payload())
    report = js.push([])
    assert js.json("acervatorTrading.isLoaded()") is False
    assert report["declared"] is None
    assert js.json("acervatorTrading.layers()") == []


@pytest.mark.parametrize("case", sorted(HOSTILE_ALL))
def test_one_bad_caption_costs_the_rest_of_the_tab_nothing(browser: Browser, case: str):
    payload = bridge_payload()
    whole = draw_tab(browser, payload)
    payload["activity_pane"]["label"]["text"] = HOSTILE_ALL[case]
    spoilt = draw_tab(browser, payload)
    assert len(spoilt) == len(whole), f"{case}: the tab lost parts"
    assert [one["text"] for one in by_part(spoilt, "placeholder-title")] == [
        one["text"] for one in by_part(whole, "placeholder-title")
    ], f"{case}: an empty-state card changed"
    assert by_part(spoilt, "api-log")[0]["text"] == by_part(whole, "api-log")[0]["text"]


def test_the_neighbour_check_names_a_part_that_did_change(browser: Browser):
    payload = bridge_payload()
    whole = draw_tab(browser, payload)
    payload["layers"][0]["placeholder"]["title"]["text"] = "changed-title"
    spoilt = draw_tab(browser, payload)
    assert [one["text"] for one in by_part(spoilt, "placeholder-title")] != [
        one["text"] for one in by_part(whole, "placeholder-title")
    ]


def test_a_hostile_payload_still_draws_a_tab(browser: Browser):
    payload = bridge_payload()
    for name in ("actions", "trading_stack", "watchdog", "container"):
        payload[name] = None
    parts = draw_tab(browser, payload)
    assert by_part(parts, "tab")
    assert len(by_part(parts, "page")) == len(payload["layers"])
    assert by_part(parts, "api-log")


def test_a_tab_with_no_layers_still_draws_its_log_panes(browser: Browser):
    payload = bridge_payload()
    payload["layers"] = []
    parts = draw_tab(browser, payload)
    assert not by_part(parts, "page")
    assert by_part(parts, "api-log")
    assert len(by_part(parts, "pane-label")) == 2


FAKE_BRIDGE = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, params]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)

REFUSING_BRIDGE = (
    "window.REFUSALS = 0;"
    "window.acervator = { call: function () {"
    "  window.REFUSALS = window.REFUSALS + 1;"
    "  return Promise.reject(new Error('refused')); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    payload = bridge_payload()
    js.bind_json("PAYLOAD", payload)
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadTrading();")
    drain()
    assert js.json("window.CALLS") == [[tts.METHOD, {}]]
    assert js.json("acervatorTrading.isLoaded()") is True


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadTrading(); acervatorLoadTrading();")
    drain()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadTrading();")
    drain()
    js.run("acervatorTrading.forget(); acervatorLoadTrading();")
    drain()
    assert len(js.json("window.CALLS")) == 2


def test_a_refused_first_ask_is_not_remembered(js: JsRuntime):
    js.run(REFUSING_BRIDGE)
    js.run("acervatorLoadTrading();")
    drain()
    assert js.json("acervatorTrading.loadError()") == "refused"
    js.run("acervatorLoadTrading();")
    drain()
    assert js.json("window.REFUSALS") == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadTrading();")
    drain()
    assert js.json("acervatorTrading.loadError()") == (
        "the preload bridge is not present"
    )


def drain() -> None:
    from tests.fixtures.web_js_modules import drain_events

    drain_events()


def test_the_page_names_the_trading_module_among_its_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("trading_tab.js")]
    assert named, "index.html names no trading tab module"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH.resolve()


def test_the_page_loads_the_trading_module_after_the_modules_it_uses():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    at = [i for i, ref in enumerate(refs) if ref.endswith("trading_tab.js")][0]
    for needed in (
        "design_tokens.js",
        "shared_widgets.js",
        "status_log.js",
        "header_strip.js",
        "react.production.min.js",
    ):
        before = [i for i, ref in enumerate(refs) if ref.endswith(needed)]
        assert before and before[0] < at, needed + " is not loaded first"


def test_the_module_reuses_the_sheet_reader_rather_than_copying_it(
    skinned: JsRuntime,
):
    payload = bridge_payload()
    skinned.push(payload)
    sheet = payload["activity_pane"]["label"]["style_sheet"]
    skinned.bind_json("SHEET", sheet)
    assert skinned.json("acervatorTrading.declarations(JSON.parse(SHEET))") == (
        skinned.json("acervatorHeader.declarations(JSON.parse(SHEET))")
    )
    assert skinned.json("acervatorTrading.styleOf(JSON.parse(SHEET))") == (
        skinned.json("acervatorHeader.styleOf(JSON.parse(SHEET))")
    )


def test_the_sheet_reader_answers_nothing_with_the_header_module_absent(
    js: JsRuntime,
):
    payload = bridge_payload()
    js.bind_json("SHEET", payload["activity_pane"]["label"]["style_sheet"])
    assert js.json("acervatorTrading.declarations(JSON.parse(SHEET))") == []
    assert js.json("acervatorTrading.styleOf(JSON.parse(SHEET))") == {}


def test_the_module_reuses_the_one_carrier_rule_rather_than_copying_it(
    skinned: JsRuntime,
):
    skinned.push(bridge_payload())
    carried = str(dss.PRIMARY)
    skinned.bind_json("VALUE", carried)
    mine = skinned.json("acervatorTrading.variableFor(JSON.parse(VALUE))")
    theirs = skinned.json("acervatorWidgets.variableFor(JSON.parse(VALUE))")
    assert mine == theirs and mine is not None, f"{mine} against {theirs}"


def test_the_resolver_answers_the_plain_value_with_the_widget_module_absent(
    js: JsRuntime,
):
    carried = str(dss.PRIMARY)
    js.bind_json("VALUE", carried)
    assert js.json("acervatorTrading.variableFor(JSON.parse(VALUE))") is None
    assert js.json("acervatorTrading.colour(JSON.parse(VALUE))") == carried
