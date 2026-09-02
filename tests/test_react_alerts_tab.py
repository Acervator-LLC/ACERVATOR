"""Drives `alerts_tab.js` against `alerts_tab_surface.py`."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import alerts_tab_surface as sfc
from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import JsEngine, js_literals, new_engine

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "alerts_tab.js"
TOKENS_PATH = WEB / "design_tokens.js"
THEMES_PATH = WEB / "theme_engine.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
HEADER_PATH = WEB / "header_strip.js"
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

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 300
READY_STEP_MS = 100
HOST_WIDTH_PX = 1400
VIEW_SIZE_PX = (1400, 900)

HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")

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


RULES = {
    "trade_filled": {"priority": "high", "channels": ["IN_APP", "TELEGRAM"]},
    "bot_stalled": {"priority": "low", "channels": ["SOUND"]},
    "fold_complete": {"priority": "critical", "channels": []},
}

HISTORY = [
    {
        "timestamp": 1.0,
        "priority": "critical",
        "title": "Fold",
        "message": "bought the dip back",
        "channels_sent": ["IN_APP"],
        "acknowledged": True,
    },
    {
        "timestamp": 2.0,
        "priority": "medium",
        "title": "Scrum",
        "message": "sold the excess",
        "channels_sent": ["TELEGRAM", "SOUND"],
        "acknowledged": False,
    },
]

FULL_MANAGER = {
    "config": {"telegram_configured": True, "sms_configured": True, "rules": RULES},
    "unread": 2,
    "history": HISTORY,
}

QUIET_MANAGER = {
    "config": {"telegram_configured": False, "sms_configured": False, "rules": {}},
    "unread": 0,
    "history": [],
}

SENT_BOT_KEY = "bot-key"
SENT_CHAT = "chat-id"
SENT_PHONE = "+15550000000"

#: Each STATES entry names the request that drives the surface into it.
STATES = {
    "painted": {"reset": True, "manager": FULL_MANAGER, "action": "refresh"},
    "quiet": {"reset": True, "manager": QUIET_MANAGER, "action": "refresh"},
    "fresh": {"reset": True, "manager": FULL_MANAGER},
    "no_manager": {"reset": True, "action": "refresh"},
    "telegram_missing": {
        "reset": True,
        "manager": FULL_MANAGER,
        "action": "test_telegram",
    },
    "telegram_sent": {
        "reset": True,
        "manager": FULL_MANAGER,
        "fields": {"token": SENT_BOT_KEY, "chat_id": SENT_CHAT},
        "action": "test_telegram",
    },
    "saved": {
        "reset": True,
        "manager": FULL_MANAGER,
        "fields": {"token": SENT_BOT_KEY, "chat_id": SENT_CHAT, "phone": SENT_PHONE},
        "action": "save_config",
    },
    "acknowledged": {
        "reset": True,
        "manager": FULL_MANAGER,
        "action": "acknowledge_all",
    },
}

STATE_NAMES = sorted(STATES)


def state_payload(name: str) -> dict:
    """Return the surface's answer for `name`, through the bridge's dumps."""
    return json.loads(json.dumps(sfc.view_model(dict(STATES[name])), ensure_ascii=True))


def painted_payload() -> dict:
    return state_payload("painted")


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def walk_payload(node: Any, keys: set, values: set) -> None:
    """Sort every key name and every string value of `node` into two sets."""
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


def published() -> tuple:
    """Every key name and every string value, over every state."""
    keys: set = set()
    values: set = set()
    for name in STATE_NAMES:
        walk_payload(state_payload(name), keys, values)
    values.discard("")
    keys.discard("")
    return keys, values


#: Each field whose strings the tab shows or paints.
CONTENT_FIELDS = (
    "styles",
    "cell_colors",
    "priority_colors",
    "priority_fallback_color",
    "group_titles",
    "row_labels",
    "placeholders",
    "button_texts",
    "rules_columns",
    "history_columns",
    "status_text",
    "status_style",
    "unread_text",
    "unread_style",
    "telegram_status_text",
    "telegram_status_style",
    "sms_status_text",
    "sms_status_style",
    "tab_style_sheet",
)

#: Each widget key whose text or style the tab shows.
CONTENT_NODE_KEYS = ("text", "title", "style_sheet", "placeholder", "row_label")

#: Each cell value the tab shows or paints, its alignment word apart.
CONTENT_CELL_KEYS = ("text", "color")


def content_values() -> set:
    """Every string the tab shows, from each content field and each widget."""
    keys: set = set()
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        for field in CONTENT_FIELDS:
            walk_payload(payload[field], keys, found)
        for node in payload["widgets"]:
            for key in CONTENT_NODE_KEYS:
                walk_payload(node.get(key), keys, found)
        for field in ("rules_rows", "history_rows"):
            for row in payload[field]:
                for cell in row:
                    for key in CONTENT_CELL_KEYS:
                        walk_payload(cell.get(key), keys, found)
    found.discard("")
    return found


PUBLISHED_KEYS, PUBLISHED_VALUES = published()
CONTENT_VALUES = content_values()
TOKEN_VALUES = {str(one) for one in dss.TOKENS.values() if str(one)}

#: The bridge method is the one published value the module asks on.
NAMED_VALUE = sfc.METHOD

#: Each ENUM_WORDS entry is a Qt word the module translates into CSS.
ENUM_WORDS = {
    sfc.ALIGNMENT,
    sfc.LABEL_ALIGNMENT,
    sfc.FORM_LABEL_ALIGNMENT,
    sfc.ECHO_NORMAL,
    sfc.ECHO_HIDDEN,
    sfc.CELL_ELIDE,
    sfc.SCROLL_BAR_POLICY,
    sfc.SPLITTER_ORIENTATION,
    sfc.TEXT_FORMAT,
} | set(sfc.EDIT_TRIGGERS_DEFAULT)

#: Each addressed widget, whose live field or row list the module reads.
ADDRESSED_NAMES = {
    "status_label",
    "unread_label",
    "telegram_status",
    "sms_status",
    "token_input",
    "chat_input",
    "phone_input",
    "rules_table",
    "history_table",
}

#: Each coincident word the module writes that a published value equals.
COINCIDENT = {" ", ", ", "left", "tab", "channels", "stretch"}


class JsRuntime(JsEngine):
    module_path = MODULE_PATH
    setter = "acervatorSetAlerts"

    def call(self, name: str) -> Any:
        return self.json("acervatorAlerts." + name + "()")

    def named(self, call: str, name: Any) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorAlerts." + call + "(JSON.parse(NAME))")

    def push_written(self, payload: Any, *writes: str) -> dict:
        """Push `payload` after running each `writes` line against it, for
        values JSON cannot spell."""
        self.bind_json("PAYLOAD", payload)
        body = "var P = JSON.parse(PAYLOAD);" + "".join(writes)
        return self.json(
            "(function () { " + body + " return acervatorSetAlerts(P); })()"
        )

    def load_skin(self) -> None:
        """Run the merged modules and push `token_payload` into the engine."""
        for path in (TOKENS_PATH, THEMES_PATH, WIDGETS_PATH, HEADER_PATH):
            self.run(path.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """A `JsRuntime` holding `MODULE_SOURCE` in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def skinned(js: JsRuntime) -> JsRuntime:
    """The `js` runtime after `load_skin` runs the merged modules."""
    js.load_skin()
    return js


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    declared = js.call("declaredNames")
    missing = sorted(set(payload) - set(declared))
    assert not missing, f"{len(missing)} published fields have no name: {missing}"
    extra = sorted(set(declared) - set(payload))
    assert not extra, f"the module names fields the surface has none of: {extra}"
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
    payload = painted_payload()
    payload["planted_only_on_the_surface"] = []
    js.push(payload)
    declared = js.call("declaredNames")
    assert sorted(set(payload) - set(declared)) == ["planted_only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_names(js: JsRuntime):
    payload = painted_payload()
    dropped = payload.pop("history_rows")
    assert dropped is not None
    js.push(payload)
    declared = js.call("declaredNames")
    assert sorted(set(declared) - set(payload)) == ["history_rows"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_named_and_held_counts_apart(js: JsRuntime, state: str):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == report["held"]["fields"] == len(payload)
    assert report["declared"]["nodes"] == report["held"]["nodes"]
    assert report["held"]["nodes"] == len(payload["widgets"])
    for side in ("rules", "history"):
        columns = side + "_columns"
        cells = side + "_cells"
        assert report["declared"][columns] == report["held"][columns]
        assert report["declared"][cells] == report["held"][cells]
    assert report["held"]["rules_cells"] == sum(
        len(row) for row in payload["rules_rows"]
    )
    assert report["held"]["history_cells"] == sum(
        len(row) for row in payload["history_rows"]
    )


def test_the_count_check_reports_a_row_narrower_than_the_column_count(js: JsRuntime):
    payload = painted_payload()
    payload["history_rows"][0].pop()
    report = js.push(payload)
    assert report["declared"]["history_cells"] != report["held"]["history_cells"]


def test_the_count_check_reports_a_table_promising_more_columns_than_it_names(
    js: JsRuntime,
):
    payload = painted_payload()
    payload["rules_column_count"] = len(payload["rules_columns"]) + 1
    report = js.push(payload)
    assert report["declared"]["rules_columns"] != report["held"]["rules_columns"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_raises_no_fault_on_a_payload_the_surface_produced(
    skinned: JsRuntime, state: str
):
    report = skinned.push(state_payload(state))
    assert report["faults"] == [], f"{state}: {report['faults']}"


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "alerts_tab.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"alerts_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & CONTENT_VALUES)
    assert not written, f"alerts_tab.js spells out tab content: {written}"


def test_the_only_other_published_values_the_module_writes_are_named():
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_VALUES
    allowed = {NAMED_VALUE} | ENUM_WORDS | ADDRESSED_NAMES | COINCIDENT
    assert not written - allowed, f"the module writes {sorted(written - allowed)} more"
    assert NAMED_VALUE in written
    assert ENUM_WORDS <= written
    assert ADDRESSED_NAMES <= written


def test_every_coincident_word_is_a_key_or_a_css_word_and_not_tab_content():
    assert not COINCIDENT & CONTENT_VALUES, "a coincident word is tab content"
    assert COINCIDENT <= PUBLISHED_VALUES
    assert {" ", ", "} == {sfc.EVENT_SPACE, sfc.CHANNEL_JOIN}
    assert {"left", "tab"} <= set(sfc.WIDGET_NAMES)
    assert "channels" in sfc.RULE_CHANNELS_KEY
    assert sfc.WIDGET_KINDS["left_stretch"] == "stretch"
    assert {"channels", "stretch"} <= PUBLISHED_KEYS


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"alerts_tab.js spells out token values: {written}"


def test_the_module_names_only_the_surface_key_names_it_must_read(js: JsRuntime):
    js.push(painted_payload())
    allowed = set(js.call("declaredNames")) | PUBLISHED_KEYS
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_KEYS
    assert not written - allowed, f"the module names {sorted(written - allowed)} more"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "alerts_tab.js holds a slash outside a comment, which the literal "
        f"scan cannot read: {MODULE_LITERALS['slashes']}"
    )


def test_every_enumeration_word_the_module_maps_is_the_surface_s_own(js: JsRuntime):
    js.push(painted_payload())
    words = set(js.call("alignWords")) | set(js.call("echoWords"))
    words.update(js.call("readingWords").values())
    unpublished = sorted(words - ENUM_WORDS)
    assert not unpublished, f"the module maps words the surface never wrote: {words}"
    assert set(js.call("editWords")) == set(sfc.EDIT_TRIGGERS_DEFAULT)


def test_every_node_the_module_addresses_is_a_widget_the_surface_publishes(
    js: JsRuntime,
):
    payload = painted_payload()
    js.push(payload)
    addressed = js.call("addressedNames")
    unknown = sorted(set(addressed) - set(payload["widget_names"]))
    assert not unknown, f"the module addresses nodes the tab has none of: {unknown}"
    assert len(addressed) == len(set(addressed))


SPELLED_OUT_LINES = {
    "colour": 'var spelled = "#00ffcc";',
    "cell_colour": 'var spelled = "' + sfc.CELL_YES_COLOR + '";',
    "token_value": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "status_text": 'var spelled = "' + sfc.STATUS_TEXT + '";',
    "button_text": 'var spelled = "' + sfc.SAVE_BUTTON_TEXT + '";',
    "column_title": 'var spelled = "' + sfc.HISTORY_COLUMNS[0] + '";',
    "placeholder": 'var spelled = "' + sfc.PHONE_PLACEHOLDER + '";',
    "style_sheet": 'var spelled = "' + sfc.SMS_STATUS_STYLE + '";',
    "handle_width": "var spelled = " + str(sfc.SPLITTER_HANDLE_WIDTH) + ";",
    "number": "var spelled = 12;",
    "regex": "var spelled = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the five checks above report on `source`."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if found["numbers"]:
        caught.add("number")
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & CONTENT_VALUES:
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


#: One spare file per process, so no worker renames another's file.
SPARE_PATH = MODULE_PATH.with_name("alerts_tab.scan_swap." + str(os.getpid()) + ".js")


def swap_module(content: bytes) -> None:
    """Replace `MODULE_PATH` with `content` through `os.replace`, retrying
    `SWAP_ATTEMPTS` times on `PermissionError`."""
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
        assert runtime.json("typeof acervatorSetAlerts") == "function", kind


def python_kinds(value: Any, prefix: str = "") -> dict:
    """Every value's JavaScript type, by dotted path, read in Python."""
    found = {}
    if isinstance(value, dict):
        for name, one in value.items():
            path = prefix + "." + name if prefix else name
            found[path] = JS_TYPE_OF[type(one).__name__]
            found.update(python_kinds(one, path))
    elif isinstance(value, (list, tuple)):
        for at, one in enumerate(value):
            path = prefix + "." + str(at)
            found[path] = JS_TYPE_OF[type(one).__name__]
            found.update(python_kinds(one, path))
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_of_every_state_arrives_as_the_type_it_left_as(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    wanted = python_kinds(payload)
    found = js.call("kinds")
    assert set(wanted) == set(found), sorted(set(wanted) ^ set(found))
    differing = {
        name: (wanted[name], found[name])
        for name in wanted
        if wanted[name] != found[name]
    }
    assert not differing, f"{state}: {len(differing)} values changed type: {differing}"


def test_the_type_check_names_a_value_that_changed_shape(js: JsRuntime):
    payload = painted_payload()
    payload["content_spacing"] = str(payload["content_spacing"])
    js.push(payload)
    assert js.call("kinds")["content_spacing"] == "string"
    assert python_kinds(painted_payload())["content_spacing"] == "number"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_row_of_every_state_agrees_with_the_surface(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for node, field in (
        ("rules_table", "rules_rows"),
        ("history_table", "history_rows"),
    ):
        assert js.named("rows", node) == payload[field], f"{state}: {node}"


def test_the_row_check_names_a_table_read_from_the_wrong_field(js: JsRuntime):
    payload = painted_payload()
    payload["history_rows"] = payload["rules_rows"]
    js.push(payload)
    assert js.named("rows", "history_table") != state_payload("painted")["history_rows"]


def test_a_reader_returns_nothing_for_an_inherited_javascript_name(js: JsRuntime):
    js.push(painted_payload())
    assert js.named("field", "constructor") is None
    assert js.named("node", "toString") is None


def test_the_inherited_name_check_still_reads_a_real_field(js: JsRuntime):
    payload = painted_payload()
    js.push(payload)
    assert js.named("field", "status_text") == payload["status_text"]


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
        """Spin until the page defines `acervatorSetAlerts`, which
        `loadFinished` does not guarantee."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetAlerts") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the alerts module: readyState "
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
    "fontWeight",
    "textAlign",
    "whiteSpace",
    "userSelect",
    "textOverflow",
    "overflowX",
    "overflowY",
    "rowGap",
    "columnGap",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderTopLeftRadius",
]

EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "border-radius": ("borderTopLeftRadius",),
    "gap": ("rowGap", "columnGap"),
    "padding-left": ("paddingLeft",),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "background": ("backgroundColor",),
    "background-color": ("backgroundColor",),
    "font-size": ("fontSize",),
    "font-weight": ("fontWeight",),
    "color": ("color",),
}

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
    "        disabled: el.disabled === true, value: el.value, text: own,"
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
    thrown = browser.js(
        "(function () { try {"
        "  acervatorSetAlerts(JSON.parse(window.PAYLOAD));"
        "  acervatorAlerts.renderTab(window.HOST);"
        "  return ''; } catch (e) { return String(e); } })()"
    )
    assert thrown == "", "the tab did not draw: " + str(thrown)
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    return json.loads(browser.js(READ_PARTS))


def declarations_of(sheet: Any) -> list:
    """Each property and value of a sheet's braceless body, read in Python."""
    found: list = []
    if not isinstance(sheet, str):
        return found
    body = sheet
    if "{" in sheet:
        body = ""
        for chunk in sheet.split("}"):
            parts = chunk.split("{")
            if len(parts) < 2 or ":" in parts[0]:
                continue
            body = body + ";" + parts[1]
    for one in body.split(";"):
        parts = one.split(":")
        prop = parts.pop(0).strip()
        if not parts or not prop:
            continue
        value = ":".join(parts).strip()
        if value:
            found.append((prop, value))
    return found


def base_body(sheet: Any) -> str:
    return ";".join(prop + ":" + value for prop, value in declarations_of(sheet))


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


def parts_named(parts: list, part: str) -> list:
    return [one for one in parts if one["attrs"].get("data-part") == part]


def part_for(parts: list, part: str, name: str) -> dict:
    found = [
        one for one in parts_named(parts, part) if one["attrs"].get("data-name") == name
    ]
    assert len(found) == 1, f"{len(found)} parts named {part}/{name}"
    return found[0]


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorAlerts") == "object"


def test_the_drawn_tab_shows_every_label_the_surface_published(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    for node, field in (
        ("status_label", "status_text"),
        ("unread_label", "unread_text"),
        ("telegram_status", "telegram_status_text"),
        ("sms_status", "sms_status_text"),
    ):
        assert part_for(parts, "label", node)["text"] == payload[field]


def test_the_drawn_tab_shows_every_cell_the_surface_published(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    drawn = [one["text"] for one in parts_named(parts, "cell")]
    wanted: list = []
    for field in ("rules_rows", "history_rows"):
        for row in payload[field]:
            wanted.extend(
                "" if cell["text"] is None else str(cell["text"]) for cell in row
            )
    assert drawn == wanted


def test_the_drawn_cell_check_names_one_changed_cell(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    drawn = [one["text"] for one in parts_named(parts, "cell")]
    payload["history_rows"][0][2]["text"] = payload["history_rows"][0][2]["text"] + "!"
    changed = [one["text"] for one in draw_tab(browser, payload)]
    assert drawn != changed


def test_the_drawn_tab_shows_every_header_the_surface_published(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    drawn = [one["text"] for one in parts_named(parts, "header-cell")]
    assert drawn == list(payload["rules_columns"]) + list(payload["history_columns"])


def test_the_drawn_inputs_carry_what_the_surface_typed(browser: Browser):
    payload = state_payload("saved")
    parts = draw_tab(browser, payload)
    for node, field in (
        ("token_input", "token"),
        ("chat_input", "chat_id"),
        ("phone_input", "phone"),
    ):
        drawn = part_for(parts, "input", node)
        assert drawn["value"] == payload[field]
        assert drawn["attrs"]["placeholder"] in payload["placeholders"]


def test_the_hidden_field_is_the_one_the_surface_hides(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    hidden = [
        one["attrs"]["data-name"]
        for one in parts_named(parts, "input")
        if one["attrs"]["type"] != "text"
    ]
    assert hidden == ["token_input"]
    assert payload["echo_modes"] == [sfc.ECHO_NORMAL, sfc.ECHO_HIDDEN]


def test_every_drawn_child_a_check_reads_carries_a_name(browser: Browser):
    parts = draw_tab(browser, painted_payload())
    unnamed = [
        one["path"]
        for one in parts
        if one["attrs"].get("data-name") is None
        and one["attrs"].get("data-row") is None
        and one["attrs"].get("data-column") is None
        and one["attrs"].get("data-index") is None
    ]
    assert not unnamed, f"{len(unnamed)} drawn parts carry no name: {unnamed}"
    seen = [
        (one["attrs"].get("data-part"), one["attrs"].get("data-name"))
        for one in parts
        if one["attrs"].get("data-name") is not None
    ]
    assert len(seen) == len(set(seen)), "two drawn parts answer to one name"


def test_every_drawn_label_colour_matches_a_probe_styled_from_the_surface(
    browser: Browser,
):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    checked = 0
    differing = {}
    for node, field in (
        ("status_label", "status_style"),
        ("unread_label", "unread_style"),
        ("sms_status", "sms_status_style"),
    ):
        expected = probe(browser, "div", base_body(payload[field]))
        drawn = part_for(parts, "label", node)
        for name, value in expected.items():
            checked += 1
            if drawn["style"].get(name) != value:
                differing[node + "." + name] = (value, drawn["style"].get(name))
    assert checked, "no drawn label carried a style, so nothing was compared"
    assert (
        not differing
    ), f"{len(differing)} of {checked} label values differ: {differing}"


def test_the_label_style_check_names_one_changed_weight(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    drawn = part_for(parts, "label", "status_label")
    expected = probe(
        browser, "div", base_body(payload["status_style"]).replace("bold", "normal")
    )
    assert drawn["style"]["fontWeight"] != expected["fontWeight"]


def test_every_drawn_button_matches_a_probe_styled_from_its_own_sheet(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    sheets = {
        node["name"]: node["style_sheet"]
        for node in payload["widgets"]
        if node["name"] in payload["button_names"]
    }
    differing = {}
    for name, sheet in sheets.items():
        expected = probe(browser, "button", base_body(sheet))
        drawn = part_for(parts, "button", name)
        for prop, value in expected.items():
            if drawn["style"].get(prop) != value:
                differing[name + "." + prop] = (value, drawn["style"].get(prop))
    assert len(sheets) == len(payload["button_names"])
    assert not differing, f"{len(differing)} button values differ: {differing}"


def test_the_button_style_check_names_one_changed_colour(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    drawn = part_for(parts, "button", "ack_button")
    sheet = payload["styles"]["ack_button"].replace(str(dss.WARNING), str(dss.ERROR))
    expected = probe(browser, "button", base_body(sheet))
    assert drawn["style"]["color"] != expected["color"]


def test_every_drawn_cell_colour_matches_a_probe_styled_from_the_surface(
    browser: Browser,
):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    cells = parts_named(parts, "cell")
    published = []
    for field in ("rules_rows", "history_rows"):
        for row in payload[field]:
            published.extend(row)
    assert len(cells) == len(published)
    checked = 0
    differing = {}
    for at, cell in enumerate(published):
        if not cell["color"]:
            continue
        expected = probe(browser, "td", "color:" + cell["color"])
        checked += 1
        if cells[at]["style"]["color"] != expected["color"]:
            differing[str(at)] = (expected["color"], cells[at]["style"]["color"])
    assert checked, "no published cell carried a colour, so nothing was compared"
    assert (
        not differing
    ), f"{len(differing)} of {checked} cell colours differ: {differing}"


def test_the_drawn_group_matches_a_probe_styled_from_its_own_sheet(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    expected = probe(browser, "fieldset", base_body(payload["styles"]["group_box"]))
    differing = {}
    for one in parts_named(parts, "group"):
        for prop, value in expected.items():
            if one["style"].get(prop) != value:
                differing[one["attrs"]["data-name"] + "." + prop] = (
                    value,
                    one["style"].get(prop),
                )
    assert len(parts_named(parts, "group")) == len(payload["group_titles"])
    assert not differing, f"{len(differing)} group values differ: {differing}"


def test_the_drawn_gaps_match_a_probe_styled_from_the_published_spacings(
    browser: Browser,
):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    for part, name, field in (
        ("tab", "tab", "content_spacing"),
        ("pane", "left", "pane_spacing"),
        ("form", "telegram_group", "form_spacing"),
    ):
        expected = probe(browser, "div", "gap:" + str(payload[field]) + "px")
        drawn = part_for(parts, part, name)
        assert drawn["style"]["rowGap"] == expected["rowGap"], part
        assert drawn["style"]["columnGap"] == expected["columnGap"], part


def test_the_gap_check_names_a_spacing_read_from_the_wrong_field(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    other = probe(browser, "div", "gap:" + str(payload["content_spacing"]) + "px")
    assert part_for(parts, "pane", "left")["style"]["rowGap"] != other["rowGap"]


def test_the_drawn_tab_paints_the_margins_the_surface_published(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    sides = ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom")
    for at, side in enumerate(sides):
        expected = probe(
            browser, "div", "padding-left:" + str(payload["content_margins"][at]) + "px"
        )
        assert part_for(parts, "tab", "tab")["style"][side] == expected["paddingLeft"]


def test_no_drawn_text_can_be_selected_where_the_surface_forbids_it(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    assert payload["text_selectable"] is False
    for part in ("label", "cell", "header-cell", "button", "form-label"):
        found = parts_named(parts, part)
        assert found, part
        for one in found:
            assert one["style"]["userSelect"] == "none", one["path"]


def test_the_selection_check_reads_a_probe_that_allows_selection(browser: Browser):
    draw_tab(browser, painted_payload())
    allowed = browser.parsed(
        "window.probeStyle('div', 'user-select:text', ['userSelect'])"
    )
    assert allowed["userSelect"] != "none"


def test_the_drawn_cells_clip_the_way_the_surface_publishes(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    assert payload["cell_elide"] == sfc.CELL_ELIDE
    for one in parts_named(parts, "cell"):
        assert one["style"]["textOverflow"] == "ellipsis"
    for one in parts_named(parts, "label"):
        assert one["style"]["whiteSpace"] == "nowrap"


def test_the_history_body_scrolls_and_the_newest_row_stays_at_the_top(
    browser: Browser,
):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    scroll = [
        one
        for one in parts_named(parts, "table-scroll")
        if one["attrs"]["data-name"] == "history_table"
    ][0]
    assert payload["scroll_bar_policy"] == sfc.SCROLL_BAR_POLICY
    assert scroll["style"]["overflowY"] == "auto"
    assert (
        browser.js(
            'window.HOST.querySelector(\'[data-part="table-scroll"]'
            '[data-name="history_table"]\').scrollTop'
        )
        == 0
    )
    first = [one["text"] for one in parts_named(parts, "cell")][
        len(payload["rules_rows"]) * payload["rules_column_count"]
    ]
    assert first == payload["history_rows"][0][0]["text"]


def test_the_drawn_tab_follows_a_colour_token_and_nothing_else_moves(browser: Browser):
    payload = painted_payload()
    before = draw_tab(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty('--WARNING', "
        + json.dumps(str(dss.ERROR))
        + ");"
    )
    after = read_parts(browser)
    moved = changed_paths(before, after)
    assert moved, "the token moved nothing at all"
    names = {name for _, name in moved}
    assert names <= {
        "color",
        "borderTopColor",
    }, f"an unexpected property moved: {moved}"
    followed = {before[at]["attrs"].get("data-name") for at, _ in moved}
    assert "unread_label" in followed
    assert "ack_button" in followed


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(browser: Browser):
    before = draw_tab(browser, painted_payload())
    assert changed_paths(before, read_parts(browser)) == set()


def changed_paths(before: list, after: list) -> set:
    """Every (index, property) whose computed value moved between reads."""
    assert len(before) == len(after), "the tab drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((at, key))
    return moved


def drawn_history(parts: list, payload: dict) -> list:
    """Each drawn history row's cell texts, in document order."""
    cells = [one["text"] for one in parts_named(parts, "cell")]
    start = len(payload["rules_rows"]) * payload["rules_column_count"]
    wide = payload["history_column_count"]
    rows = []
    at = start
    while at < len(cells):
        rows.append(cells[at : at + wide])
        at += wide
    return rows


def surface_history(payload: dict) -> list:
    return [
        ["" if cell["text"] is None else str(cell["text"]) for cell in row]
        for row in payload["history_rows"]
    ]


def test_the_drawn_alerts_keep_the_order_the_surface_published(browser: Browser):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    assert drawn_history(parts, payload) == surface_history(payload)


def test_the_order_check_names_a_reordered_list(browser: Browser):
    payload = painted_payload()
    drawn = drawn_history(draw_tab(browser, payload), payload)
    payload["history_rows"].reverse()
    assert drawn_history(draw_tab(browser, payload), payload) != drawn
    assert drawn_history(draw_tab(browser, payload), payload) == surface_history(
        payload
    )


def test_the_identity_check_names_two_alerts_texts_swapped(browser: Browser):
    payload = painted_payload()
    drawn = drawn_history(draw_tab(browser, payload), payload)
    first = payload["history_rows"][0]
    second = payload["history_rows"][1]
    for column in range(payload["history_column_count"]):
        first[column]["text"], second[column]["text"] = (
            second[column]["text"],
            first[column]["text"],
        )
    swapped = drawn_history(draw_tab(browser, payload), payload)
    assert swapped != drawn
    assert sorted(sorted(row) for row in swapped) == sorted(
        sorted(row) for row in drawn
    )
    assert swapped == surface_history(payload)


def test_the_module_reports_the_row_texts_the_surface_published(js: JsRuntime):
    payload = painted_payload()
    js.push(payload)
    assert js.named("rowTexts", "history_table") == [
        [cell["text"] for cell in row] for row in payload["history_rows"]
    ]


def test_a_field_the_payload_omits_is_named_as_missing(js: JsRuntime):
    payload = painted_payload()
    payload.pop("status_text")
    report = js.push(payload)
    assert {
        "where": None,
        "field": "status_text",
        "fault": "missing",
        "detail": None,
    } in report["faults"]


@pytest.mark.parametrize("field", ["rules_rows", "styles", "widgets", "actions"])
def test_a_field_carrying_null_is_named(js: JsRuntime, field: str):
    payload = painted_payload()
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_the_one_field_the_surface_publishes_as_null_is_not_named(js: JsRuntime):
    payload = painted_payload()
    assert payload["telegram_test_priority"] is None
    report = js.push(payload)
    assert [
        one for one in report["faults"] if one["field"] == "telegram_test_priority"
    ] == []


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(painted_payload())
    assert [
        one for one in report["faults"] if one["fault"] in ("missing", "null")
    ] == []


@pytest.mark.parametrize(
    "field",
    sorted(
        {one for one in sfc.build_view_model(sfc.AlertsTabModel())}
        & {
            "status_text",
            "unread_text",
            "telegram_status_text",
            "sms_status_text",
            "status_style",
            "unread_style",
            "telegram_status_style",
            "sms_status_style",
            "test_path",
            "save_path",
            "ack_path",
            "refresh_path",
        }
    ),
)
def test_a_wrong_type_is_named_where_the_surface_publishes_a_default(
    js: JsRuntime, field: str
):
    payload = painted_payload()
    payload[field] = len(payload)
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "wrong-type",
        "detail": "number",
    } in report["faults"]


def test_the_wrong_type_check_covers_exactly_the_fields_with_a_published_default(
    js: JsRuntime,
):
    js.push(painted_payload())
    assert sorted(js.call("peeredNames")) == [
        "ack_path",
        "refresh_path",
        "save_path",
        "sms_status_style",
        "sms_status_text",
        "status_style",
        "status_text",
        "telegram_status_style",
        "telegram_status_text",
        "test_path",
        "unread_style",
        "unread_text",
    ]


def test_the_wrong_type_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(painted_payload())
    assert [one for one in report["faults"] if one["fault"] == "wrong-type"] == []


def test_a_sheet_css_would_read_as_another_colour_is_named(skinned: JsRuntime):
    payload = painted_payload()
    payload["styles"]["ack_button"] = "color: #80ff0000;"
    report = skinned.push(payload)
    assert {
        "where": "styles",
        "field": "ack_button",
        "fault": "qt-colour",
        "detail": "color",
    } in report["faults"]


def test_a_byte_alpha_css_would_read_as_opaque_is_named(skinned: JsRuntime):
    payload = painted_payload()
    payload["styles"]["ack_button"] = "background: rgba(255, 0, 0, 128);"
    report = skinned.push(payload)
    assert [one for one in report["faults"] if one["fault"] == "qt-colour"] != []


def test_no_colour_the_surface_publishes_is_read_as_another_colour(skinned: JsRuntime):
    report = skinned.push(painted_payload())
    named = [one for one in report["faults"] if one["fault"] == "qt-colour"]
    assert named == [], f"the tab publishes a colour CSS reads apart: {named}"


def test_the_qt_colour_check_reads_nothing_without_the_sheet_reader(js: JsRuntime):
    payload = painted_payload()
    payload["styles"]["ack_button"] = "color: #80ff0000;"
    report = js.push(payload)
    assert [one for one in report["faults"] if one["fault"] == "qt-colour"] == []


def test_a_label_text_carrying_markup_is_named_and_shown_as_written(browser: Browser):
    payload = painted_payload()
    payload["status_text"] = "<b>Notifications</b>"
    parts = draw_tab(browser, payload)
    assert part_for(parts, "label", "status_label")["text"] == payload["status_text"]
    named = browser.parsed("acervatorAlerts.faults()")
    assert {
        "where": "node:status_label",
        "field": "status_text",
        "fault": "markup",
        "detail": payload["text_format"],
    } in named


def test_the_markup_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(painted_payload())
    assert [one for one in report["faults"] if one["fault"] == "markup"] == []


def test_a_button_running_an_action_the_surface_never_named_is_named(js: JsRuntime):
    payload = painted_payload()
    for node in payload["widgets"]:
        if node["name"] == "ack_button":
            node["action"] = "an_action_the_surface_never_named"
    report = js.push(payload)
    assert {
        "where": "node:ack_button",
        "field": "action",
        "fault": "unslotted",
        "detail": "an_action_the_surface_never_named",
    } in report["faults"]


def test_a_short_splitter_size_list_is_named(js: JsRuntime):
    payload = painted_payload()
    payload["splitter_sizes"] = payload["splitter_sizes"][:1]
    report = js.push(payload)
    assert [one for one in report["faults"] if one["fault"] == "short-list"] != []


def test_more_history_rows_than_the_published_limit_is_named(js: JsRuntime):
    payload = painted_payload()
    row = payload["history_rows"][0]
    payload["history_rows"] = [row for _ in range(payload["history_limit"] + 1)]
    report = js.push(payload)
    assert [one for one in report["faults"] if one["fault"] == "over-limit"] != []


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    report = js.push([])
    assert report["declared"] is None
    assert js.json("acervatorAlerts.isLoaded()") is False
    assert report["faults"] == [
        {"where": None, "field": None, "fault": "not-an-object", "detail": "object"}
    ]


LONG_TEXT = "n" * 200
HOSTILE_CELL_TEXTS = {
    "missing": None,
    "null": None,
    "number_where_text_belongs": 3,
    "huge": 10**24,
    "long": LONG_TEXT,
    "newline": "one\ntwo",
    "markup": "<img src=x>",
}


#: What the drawn cell reads for each hostile value above.
SHOWN_CELL_TEXTS = {
    "missing": "",
    "null": "",
    "number_where_text_belongs": "3",
    "huge": "1e+24",
    "long": LONG_TEXT,
    "newline": HOSTILE_CELL_TEXTS["newline"],
    "markup": HOSTILE_CELL_TEXTS["markup"],
}


@pytest.mark.parametrize("kind", sorted(HOSTILE_CELL_TEXTS))
def test_the_tab_shows_whatever_cell_text_the_surface_produced(
    browser: Browser, kind: str
):
    payload = painted_payload()
    cell = payload["history_rows"][0][2]
    if kind == "missing":
        cell.pop("text")
    else:
        cell["text"] = HOSTILE_CELL_TEXTS[kind]
    parts = draw_tab(browser, payload)
    shown = parts_named(parts, "cell")[
        len(payload["rules_rows"]) * payload["rules_column_count"] + 2
    ]["text"]
    assert shown == SHOWN_CELL_TEXTS[kind], f"{kind}: the tab shows {shown!r}"


@pytest.mark.parametrize("field", ["status_text", "unread_text", "sms_status_text"])
def test_the_tab_shows_whatever_label_text_the_surface_produced(
    browser: Browser, field: str
):
    payload = painted_payload()
    payload[field] = LONG_TEXT
    parts = draw_tab(browser, payload)
    node = {
        "status_text": "status_label",
        "unread_text": "unread_label",
        "sms_status_text": "sms_status",
    }[field]
    assert part_for(parts, "label", node)["text"] == LONG_TEXT


@pytest.mark.parametrize("field", ["status_text", "rules_rows", "widgets", "actions"])
def test_a_hostile_field_still_draws_a_tab(browser: Browser, field: str):
    payload = painted_payload()
    payload[field] = None
    parts = draw_tab(browser, payload)
    assert parts_named(parts, "tab"), f"{field}: nothing drew at all"


def test_a_row_that_is_not_a_list_is_named_and_draws_nothing(js: JsRuntime):
    payload = painted_payload()
    payload["history_rows"][0] = "not a row"
    report = js.push(payload)
    assert {
        "where": "row:history_table",
        "field": "0",
        "fault": "not-an-object",
        "detail": "string",
    } in report["faults"]


def test_one_bad_row_costs_the_other_rows_nothing(browser: Browser):
    payload = painted_payload()
    before = drawn_history(draw_tab(browser, payload), payload)
    payload["history_rows"][0] = []
    after = drawn_history(draw_tab(browser, payload), payload)
    assert after[1:] == before[1:], "a bad row changed its neighbour"


def test_the_neighbour_check_names_a_row_that_did_change(browser: Browser):
    payload = painted_payload()
    before = drawn_history(draw_tab(browser, payload), payload)
    payload["history_rows"][1][0]["text"] = "moved"
    after = drawn_history(draw_tab(browser, payload), payload)
    assert after[1:] != before[1:]


@pytest.mark.parametrize("case", ["nan", "inf"])
def test_the_tab_holds_a_number_json_cannot_spell(js: JsRuntime, case: str):
    payload = painted_payload()
    written = {
        "nan": "P.history_rows[0][1].text = 0/0;",
        "inf": "P.content_spacing = 1/0;",
    }
    report = js.push_written(payload, written[case])
    assert report["held"]["fields"] == len(payload)
    assert js.call("kinds")["content_spacing"] == "number"


def test_the_bridge_cannot_carry_a_not_a_number_at_all(js: JsRuntime):
    payload = painted_payload()
    payload["history_rows"][0][1]["text"] = math.nan
    js.bind_json("PAYLOAD", payload)
    thrown = js.json(
        "(function () { try { JSON.parse(PAYLOAD); return ''; }"
        " catch (e) { return String(e.name); } })()"
    )
    assert thrown, "JSON.parse accepted a bare NaN, so #257 does not apply here"


def test_the_bridge_check_parses_the_same_payload_without_the_bad_value(js: JsRuntime):
    payload = painted_payload()
    js.bind_json("PAYLOAD", payload)
    thrown = js.json(
        "(function () { try { JSON.parse(PAYLOAD); return ''; }"
        " catch (e) { return String(e.name); } })()"
    )
    assert thrown == ""


@pytest.mark.parametrize(
    "spec",
    [
        {"priority": math.nan},
        {"title": math.inf},
        {"title": -math.inf},
    ],
    ids=["priority_nan", "title_inf", "title_negative_inf"],
)
def test_the_surface_emits_a_number_the_bridge_frame_cannot_carry(spec: dict):
    record = {
        "timestamp": 1.0,
        "priority": "low",
        "title": "t",
        "message": "m",
        "channels_sent": [],
        "acknowledged": True,
    }
    record.update(spec)
    answer = sfc.view_model(
        {
            "reset": True,
            "manager": {"config": {"rules": {}}, "unread": 0, "history": [record]},
            "action": "refresh",
        }
    )
    written = json.dumps(answer["history_rows"])
    assert "NaN" in written or "Infinity" in written, written[:200]


def test_the_surface_emits_a_frame_json_can_carry_without_the_bad_value():
    answer = sfc.view_model(dict(STATES["painted"]))
    json.loads(json.dumps(answer))


SELECT_CELL = (
    'window.HOST.querySelector(\'[data-part="table"][data-name="{table}"] '
    '[data-part="cell"][data-row="{row}"][data-column="{column}"]\')'
)


def draw_with_actions(browser: Browser, payload: dict) -> list:
    """Draw `payload` with a handler that records every action it is given."""
    parts = draw_tab(browser, payload)
    browser.js(
        "window.FIRED = [];"
        "acervatorAlerts.renderTab(window.HOST, JSON.parse(window.PAYLOAD),"
        "  function (name, typed) { window.FIRED.push([name, typed]); });"
    )
    return parts


def fire(browser: Browser, target: str, kind: str, detail: str = "{}") -> None:
    """Dispatch one bubbling `kind` event on the element `target` names."""
    browser.js(
        "(function () { var el = "
        + target
        + "; var one = Object.assign({ bubbles: true }, "
        + detail
        + ");"
        " el.dispatchEvent(new "
        + ("KeyboardEvent" if kind.startswith("key") else "MouseEvent")
        + "('"
        + kind
        + "', one)); })()"
    )


def test_a_click_reports_the_action_the_surface_names_for_that_button(
    browser: Browser,
):
    payload = painted_payload()
    draw_with_actions(browser, payload)
    for name, action in (
        ("test_button", "test_telegram"),
        ("save_button", "save_config"),
        ("ack_button", "acknowledge_all"),
    ):
        browser.js(
            'window.HOST.querySelector(\'[data-part="button"]'
            '[data-name="' + name + "\"]').click();"
        )
        assert payload["actions"][name + ".clicked"] == action
    fired = [one[0] for one in browser.parsed("window.FIRED")]
    assert fired == ["test_telegram", "save_config", "acknowledge_all"]


def test_the_click_check_reports_nothing_when_no_button_is_clicked(browser: Browser):
    draw_with_actions(browser, painted_payload())
    assert browser.parsed("window.FIRED") == []


def test_what_the_operator_types_reaches_the_click_report(browser: Browser):
    draw_with_actions(browser, painted_payload())
    browser.js(
        "(function () { var el = window.HOST.querySelector("
        '\'[data-part="input"][data-name="phone_input"]\');'
        " var setter = Object.getOwnPropertyDescriptor("
        "   window.HTMLInputElement.prototype, 'value').set;"
        " setter.call(el, 'typed-number');"
        " el.dispatchEvent(new Event('input', { bubbles: true })); })()"
    )
    browser.js(
        'window.HOST.querySelector(\'[data-part="button"]'
        '[data-name="save_button"]\').click();'
    )
    assert browser.parsed("window.FIRED") == [
        ["save_config", {"phone": "typed-number"}]
    ]


def test_the_save_button_takes_the_hover_paint_the_surface_publishes(browser: Browser):
    payload = painted_payload()
    draw_tab(browser, payload)
    target = (
        'window.HOST.querySelector(\'[data-part="button"]'
        '[data-name="save_button"]\')'
    )
    before = browser.parsed("window.readStyle(" + target + ", ['backgroundColor'])")
    fire(browser, target, "mouseover")
    after = browser.parsed("window.readStyle(" + target + ", ['backgroundColor'])")
    hover = payload["styles"]["save_button"].split("QPushButton:hover")[1]
    expected = probe(browser, "button", base_body(hover))
    assert after["backgroundColor"] == expected["backgroundColor"]
    assert after["backgroundColor"] != before["backgroundColor"]


def test_a_button_the_surface_gives_no_hover_paint_does_not_move(browser: Browser):
    payload = painted_payload()
    draw_tab(browser, payload)
    assert "QPushButton:hover" not in payload["styles"]["ack_button"]
    target = (
        'window.HOST.querySelector(\'[data-part="button"]' '[data-name="ack_button"]\')'
    )
    before = browser.parsed("window.readStyle(" + target + ", ['backgroundColor'])")
    fire(browser, target, "mouseover")
    after = browser.parsed("window.readStyle(" + target + ", ['backgroundColor'])")
    assert after == before


def test_the_routing_cells_open_an_editor_and_the_history_cells_do_not(
    browser: Browser,
):
    payload = painted_payload()
    draw_tab(browser, payload)
    assert payload["edit_triggers_default"] and not payload["edit_triggers_none"]
    for table, wanted in (("rules_table", "true"), ("history_table", "false")):
        target = SELECT_CELL.format(table=table, row=0, column=0)
        fire(browser, target, "dblclick")
        assert browser.js("String(" + target + ".isContentEditable)") == wanted, table
        assert browser.js(target + ".getAttribute('data-editable')") == wanted


def test_a_typed_key_opens_the_editor_the_surface_names_a_trigger_for(
    browser: Browser,
):
    payload = painted_payload()
    draw_tab(browser, payload)
    target = SELECT_CELL.format(table="rules_table", row=0, column=0)
    fire(browser, target, "keydown", "{ key: 'F2' }")
    assert browser.js("String(" + target + ".isContentEditable)") == "true"
    fire(browser, target, "keydown", "{ key: 'Escape' }")
    assert browser.js("String(" + target + ".isContentEditable)") == "false"


def test_an_arrow_key_moves_the_cell_the_table_would_edit(browser: Browser):
    payload = painted_payload()
    draw_tab(browser, payload)
    first = SELECT_CELL.format(table="history_table", row=0, column=0)
    fire(browser, first, "mousedown")
    assert browser.js(first + ".getAttribute('tabindex')") == "0"
    fire(browser, first, "keydown", "{ key: 'ArrowRight' }")
    next_cell = SELECT_CELL.format(table="history_table", row=0, column=1)
    assert browser.js(next_cell + ".getAttribute('tabindex')") == "0"
    assert browser.js(first + ".getAttribute('tabindex')") == "-1"


def test_an_arrow_key_stops_at_the_edge_of_the_table(browser: Browser):
    payload = painted_payload()
    draw_tab(browser, payload)
    first = SELECT_CELL.format(table="history_table", row=0, column=0)
    fire(browser, first, "mousedown")
    fire(browser, first, "keydown", "{ key: 'ArrowLeft' }")
    assert browser.js(first + ".getAttribute('tabindex')") == "0"


def test_a_click_selects_one_cell_and_the_next_click_moves_the_selection(
    browser: Browser,
):
    payload = painted_payload()
    draw_tab(browser, payload)
    first = SELECT_CELL.format(table="history_table", row=0, column=0)
    second = SELECT_CELL.format(table="history_table", row=1, column=2)
    fire(browser, first, "mousedown")
    assert browser.js(first + ".getAttribute('data-selected')") == "true"
    fire(browser, second, "mousedown")
    assert browser.js(second + ".getAttribute('data-selected')") == "true"
    assert browser.js(first + ".getAttribute('data-selected')") == "false"
    assert payload["selection_mode"] == sfc.SELECTION_MODE
    assert payload["selection_behavior"] == sfc.SELECTION_BEHAVIOR


def test_a_held_control_key_keeps_the_cell_already_selected(browser: Browser):
    payload = painted_payload()
    draw_tab(browser, payload)
    first = SELECT_CELL.format(table="history_table", row=0, column=0)
    second = SELECT_CELL.format(table="history_table", row=1, column=2)
    fire(browser, first, "mousedown")
    fire(browser, second, "mousedown", "{ ctrlKey: true }")
    assert browser.js(first + ".getAttribute('data-selected')") == "true"
    assert browser.js(second + ".getAttribute('data-selected')") == "true"


def test_the_focus_order_follows_the_order_the_surface_builds_in(browser: Browser):
    payload = painted_payload()
    draw_tab(browser, payload)
    order = browser.parsed(
        "(function () { var found = [];"
        " Array.prototype.slice.call(window.HOST.querySelectorAll("
        "   'input, button')).forEach(function (el) {"
        "   found.push(el.getAttribute('data-name')); });"
        " return found; })()"
    )
    wanted = [
        node["name"]
        for node in payload["widgets"]
        if node["kind"] in ("QLineEdit", "QPushButton")
    ]
    assert order == wanted


def test_the_splitter_panes_start_at_the_widths_the_surface_published(
    browser: Browser,
):
    payload = painted_payload()
    parts = draw_tab(browser, payload)
    panes = parts_named(parts, "splitter-pane")
    assert len(panes) == len(payload["splitter_sizes"])
    grown = browser.parsed(
        "(function () { var found = [];"
        " Array.prototype.slice.call(window.HOST.querySelectorAll("
        "   '[data-part=\"splitter-pane\"]')).forEach(function (el) {"
        "   found.push(getComputedStyle(el).flexGrow); });"
        " return found; })()"
    )
    assert grown == [str(one) for one in payload["splitter_sizes"]]


def test_the_splitter_handle_is_as_wide_as_the_surface_published(browser: Browser):
    payload = painted_payload()
    draw_tab(browser, payload)
    expected = probe(
        browser, "div", "width:" + str(payload["splitter_handle_width"]) + "px"
    )
    drawn = browser.parsed(
        "window.readStyle(window.HOST.querySelector('[data-part=\"handle\"]'),"
        " ['width'])"
    )
    assert drawn["width"] == expected["width"]


def test_the_tab_draws_with_text_where_a_number_belongs(browser: Browser):
    payload = painted_payload()
    payload["content_spacing"] = str(payload["content_spacing"])
    payload["splitter_handle_width"] = str(payload["splitter_handle_width"])
    parts = draw_tab(browser, payload)
    expected = probe(browser, "div", "gap:" + payload["content_spacing"] + "px")
    assert part_for(parts, "tab", "tab")["style"]["rowGap"] == expected["rowGap"]


def test_the_tab_draws_with_a_number_json_cannot_spell_in_a_length(browser: Browser):
    payload = painted_payload()
    before = draw_tab(browser, payload)
    browser.js(
        "(function () { var P = JSON.parse(window.PAYLOAD);"
        " P.content_spacing = 0/0;"
        " P.history_rows[0][1].text = 1/0;"
        " acervatorSetAlerts(P);"
        " acervatorAlerts.renderTab(window.HOST, P); })()"
    )
    parts = read_parts(browser)
    assert parts_named(parts, "tab"), "the tab drew nothing at all"
    kept = part_for(before, "tab", "tab")["style"]["rowGap"]
    assert part_for(parts, "tab", "tab")["style"]["rowGap"] == kept
    shown = [one["text"] for one in parts_named(parts, "cell")][
        len(payload["rules_rows"]) * payload["rules_column_count"] + 1
    ]
    assert shown == "Infinity"


def test_a_payload_missing_the_widget_tree_still_draws_a_tab(browser: Browser):
    payload = painted_payload()
    payload.pop("widgets")
    parts = draw_tab(browser, payload)
    assert parts_named(parts, "tab")
    assert not parts_named(parts, "table")
