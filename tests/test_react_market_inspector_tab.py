"""Drives `market_inspector_tab.js` against `market_inspector_tab_surface.py`."""

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
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import market_inspector_tab_surface as mits
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import HEX_COLOUR, js_literals, swap_module

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "market_inspector_tab.js"
TOKENS_PATH = WEB / "design_tokens.js"
THEMES_PATH = WEB / "theme_engine.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
HEADER_PATH = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: MODULE_TAIL is the closing line a whole module file ends with.
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


#: MODULE_SOURCE is read at collection, before any test body writes.
MODULE_SOURCE = read_module()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

JS_TIMEOUT_MS = 30_000
EVENT_DRAIN_ROUNDS = 20
READY_ROUNDS = 100
READY_STEP_MS = 100

#: HOST_WIDTH_PX is set because an unshown view reads ``clientWidth`` as zero.
HOST_WIDTH_PX = 1400
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
NAMED_VALUE = mits.METHOD

#: NAMED_SUB_KEYS holds every nested key name the module reads.
NAMED_SUB_KEYS = {
    "bot_attribute",
    "color",
    "detail_format",
    "error_separator",
    "function",
    "headline",
    "headline_breaks",
    "headline_text",
    "headline_weight",
    "label_class",
    "margins_set",
    "module",
    "name",
    "no_message",
    "no_style",
    "no_view",
    "no_word_wrap",
    "padding_px",
    "spacing_set",
    "stretch",
    "style_format",
    "text_format",
    "warning_format",
}

#: The bags whose nested names the module declares.
BAG_NAMES = ("delegate", "fallback", "logger", "texts", "defaults")


STATE_PARAMS: dict = {
    "empty": {"reset": True},
    "delegated": {"reset": True, "view": {"kind": "per-bot"}, "build": True},
    "failed": {"reset": True, "error": {"type": "ImportError", "text": "no module"}},
}
STATE_NAMES = tuple(sorted(STATE_PARAMS))


def state_payload(name: str) -> dict:
    """The whole view model for one named state."""
    return mits.view_model(dict(STATE_PARAMS[name]))


def failed_payload(error_type: str = "ImportError", error_text: Any = "no module"):
    """The view model one named error drives, with no view built."""
    return mits.view_model(
        {"reset": True, "error": {"type": error_type, "text": error_text}}
    )


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
    """One token value in every spelling a stylesheet could carry."""
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

#: AMBIGUOUS is every string that is both a key name and a painted value,
#: which the scan cannot tell apart.
AMBIGUOUS = PUBLISHED_KEYS & PUBLISHED_VALUES

#: PAINTED_VALUES is every published string the tab paints and no key names.
PAINTED_VALUES = PUBLISHED_VALUES - AMBIGUOUS - {NAMED_VALUE}
TOKEN_VALUES = token_values()


def drain_events() -> None:
    """Turn the event loop `EVENT_DRAIN_ROUNDS` times so callbacks run."""
    from PySide6.QtCore import QCoreApplication, QEventLoop

    for _ in range(EVENT_DRAIN_ROUNDS):
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)


class JsRuntime:
    """A QJSEngine holding ``market_inspector_tab.js`` and a ``window`` global."""

    def __init__(self, engine: Any, source: str) -> None:
        self._engine = engine
        engine.evaluate("var window = this;")
        loaded = engine.evaluate(source, MODULE_PATH.name)
        if loaded.isError():
            raise AssertionError(
                MODULE_PATH.name + " did not run: " + loaded.toString()
            )

    def engine_of(self) -> Any:
        """Return a second engine of the same type as `_engine`."""
        return type(self._engine)()

    def run(self, script: str) -> Any:
        result = self._engine.evaluate(script)
        assert not result.isError(), script[:120] + " -> " + result.toString()
        return result

    def json(self, expression: str) -> Any:
        """Evaluate ``expression`` and bring its value back as Python."""
        text = self.run("JSON.stringify(" + expression + ")").toString()
        return None if text == "undefined" else json.loads(text)

    def bind_json(self, name: str, value: Any) -> None:
        self._engine.globalObject().setProperty(name, json.dumps(value))

    def bind_text(self, name: str, written: str) -> None:
        self._engine.globalObject().setProperty(name, written)

    def push(self, payload: Any) -> dict:
        self.bind_json("PAYLOAD", payload)
        return self.json("acervatorSetInspectorTab(JSON.parse(PAYLOAD))")

    def push_written(self, payload: Any, *writes: str) -> dict:
        """Push `payload` after running each `writes` line, for values JSON
        cannot spell."""
        self.bind_json("PAYLOAD", payload)
        body = "var P = JSON.parse(PAYLOAD);" + "".join(writes)
        return self.json(
            "(function () { " + body + " return acervatorSetInspectorTab(P); })()"
        )

    def load_skins(self) -> None:
        """Run the merged modules and push the tokens into the engine."""
        for path in (TOKENS_PATH, THEMES_PATH, WIDGETS_PATH, HEADER_PATH):
            self.run(path.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def named(self, call: str, name: Any) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorInspectorTab." + call + "(JSON.parse(NAME))")


def token_payload() -> dict:
    from src.gui.main_tabs import design_system_surface

    return design_system_surface.view_model({})


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """Return a `JsRuntime` holding `MODULE_SOURCE` in a fresh engine."""
    qtqml = pytest.importorskip("PySide6.QtQml")
    assert qapp is not None
    return JsRuntime(qtqml.QJSEngine(), MODULE_SOURCE)


@pytest.fixture()
def skinned(js: JsRuntime) -> JsRuntime:
    """Return the `js` runtime after the merged token modules have run."""
    js.load_skins()
    return js


# -- 1. everything the surface publishes reaches the module ------------


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    declared = js.json("acervatorInspectorTab.declaredNames()")
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
    assert not differing, f"{state}: these fields differ: {sorted(differing)}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_nested_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    for where in BAG_NAMES:
        declared = js.named("nestedNames", where)
        assert sorted(declared) == sorted(payload[where]), where
        assert js.named("bag", where) == payload[where], where


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    payload = state_payload("failed")
    payload["invented_field"] = "invented"
    js.push(payload)
    declared = js.json("acervatorInspectorTab.declaredNames()")
    assert sorted(set(payload) - set(declared)) == ["invented_field"]


def test_the_whole_payload_check_names_a_field_only_the_module_declares(js: JsRuntime):
    payload = state_payload("failed")
    del payload["message"]
    js.push(payload)
    declared = js.json("acervatorInspectorTab.declaredNames()")
    assert sorted(set(declared) - set(payload)) == ["message"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(payload)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["nested"] == sum(
        len(payload[where]) for where in BAG_NAMES
    )
    assert report["held"]["nested"] == report["declared"]["nested"]
    assert report["held"]["parts"] == len(payload["order"])
    assert report["declared"]["parts"] == len(payload["call_names"])


def test_the_count_check_reports_a_payload_carrying_less_than_it_declares(
    js: JsRuntime,
):
    payload = state_payload("failed")
    del payload["fallback"]["headline_text"]
    report = js.push(payload)
    assert report["held"]["nested"] == report["declared"]["nested"] - 1
    assert {
        "where": "fallback",
        "field": "headline_text",
        "fault": "missing",
        "detail": None,
    } in report["faults"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_raises_no_fault_on_a_payload_the_surface_produced(
    js: JsRuntime, state: str
):
    report = js.push(state_payload(state))
    assert report["faults"] == [], f"{state}: {report['faults']}"


def test_the_fault_list_reports_a_missing_top_level_field(js: JsRuntime):
    payload = state_payload("empty")
    del payload["word_wrap"]
    report = js.push(payload)
    assert {
        "where": None,
        "field": "word_wrap",
        "fault": "missing",
        "detail": None,
    } in report["faults"]


# -- 2. the module writes no value of its own --------------------------


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "market_inspector_tab.js holds numeric literals: "
        f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"market_inspector_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"market_inspector_tab.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"market_inspector_tab.js spells out token values: {written}"


def test_exactly_one_published_string_is_both_a_key_name_and_a_value():
    assert AMBIGUOUS == {"stretch"}, f"the ambiguous strings are now {AMBIGUOUS}"


def test_the_module_writes_the_bridge_method_and_one_ambiguous_key_name(
    js: JsRuntime,
):
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_VALUES)
    assert written == ["stretch"], f"the module writes the values {written}"
    js.push(state_payload("failed"))
    assert "stretch" in js.named("nestedNames", "fallback")
    assert MODULE_LITERALS["strings"].count(NAMED_VALUE) == 1


def test_the_module_names_only_the_surface_key_names_it_must_read(js: JsRuntime):
    js.push(state_payload("failed"))
    allowed = set(js.json("acervatorInspectorTab.declaredNames()")) | NAMED_SUB_KEYS
    written = set(MODULE_LITERALS["strings"]) & PUBLISHED_KEYS
    assert not written - allowed, f"the module names {sorted(written - allowed)} more"
    assert (
        not NAMED_SUB_KEYS - written
    ), f"the list allows {sorted(NAMED_SUB_KEYS - written)} the module never writes"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "market_inspector_tab.js holds a slash outside a comment: "
        f"{MODULE_LITERALS['slashes']}"
    )


SPELLED_OUT_LINES = {
    "colour": 'var spelled = "#00ffcc";',
    "fallback_colour": 'var spelled = "' + mits.FALLBACK_COLOR + '";',
    "token_value": 'var spelled = "' + str(dss.PRIMARY) + '";',
    "headline": 'var spelled = "' + mits.FALLBACK_HEADLINE_TEXT + '";',
    "label_class": 'var spelled = "' + mits.FALLBACK_LABEL_CLASS + '";',
    "weight": 'var spelled = "' + mits.FALLBACK_HEADLINE_WEIGHT + '";',
    "style_sheet": 'var spelled = "' + mits.fallback_style().replace('"', "") + '";',
    "detail_format": 'var spelled = "' + mits.FALLBACK_DETAIL_FORMAT + '";',
    "padding": "var spelled = " + str(mits.FALLBACK_PADDING_PX) + ";",
    "breaks": "var spelled = " + str(mits.FALLBACK_HEADLINE_BREAKS) + ";",
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
        assert runtime.json("typeof acervatorSetInspectorTab") == "function", kind


# -- 3. both sides agree, value for value and type for type ------------


def python_kinds(payload: dict) -> dict:
    """The JavaScript type of every value of ``payload``, by dotted path."""
    found: dict = {}

    def descend(path: str, value: Any) -> None:
        found[path] = JS_TYPE_OF[type(value).__name__]
        if isinstance(value, dict):
            for key, inner in value.items():
                descend(path + "." + key if path else key, inner)

    for key, value in payload.items():
        descend(key, value)
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_value_of_every_state_arrives_as_the_type_it_left_as(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    theirs = js.json("acervatorInspectorTab.kinds()")
    mine = python_kinds(payload)
    differing = {
        path: (mine[path], theirs.get(path))
        for path in sorted(theirs)
        if theirs[path] != mine.get(path)
    }
    assert not differing, f"{state}: these changed shape: {differing}"
    assert theirs, f"{state}: the type check read nothing"


def test_the_type_check_names_a_value_that_changed_shape(js: JsRuntime):
    payload = state_payload("failed")
    payload["word_wrap"] = "true"
    js.push(payload)
    assert js.json("acervatorInspectorTab.kinds()")["word_wrap"] == "string"
    assert python_kinds(state_payload("failed"))["word_wrap"] == "boolean"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_reader_answers_the_value_the_surface_published(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    pairs = {
        "accessibleName": "accessible_name",
        "delegated": "delegated",
        "viewHeld": "view",
        "message": "message",
        "detail": "detail",
        "errorType": "error_type",
        "errorText": "error_text",
        "wordWrap": "word_wrap",
        "styleSheet": "style_sheet",
        "order": "order",
        "warnings": "warnings",
        "calls": "calls",
        "callNames": "call_names",
        "errorTypes": "error_types",
        "busTopics": "bus_topics",
        "timerDelays": "timer_delays_ms",
        "actions": "actions",
        "timers": "timers",
    }
    differing = {
        call: (js.json("acervatorInspectorTab." + call + "()"), payload[field])
        for call, field in pairs.items()
        if js.json("acervatorInspectorTab." + call + "()") != payload[field]
    }
    assert not differing, f"{state}: these readers disagree: {differing}"


def test_the_reader_check_names_one_changed_message(js: JsRuntime):
    payload = state_payload("failed")
    payload["message"] = payload["message"] + "-changed"
    js.push(payload)
    assert (
        js.json("acervatorInspectorTab.message()") != state_payload("failed")["message"]
    )


def test_a_reader_returns_nothing_for_an_inherited_javascript_name(js: JsRuntime):
    js.push(state_payload("failed"))
    assert js.named("field", "constructor") is None
    assert js.named("field", "toString") is None


def test_the_inherited_name_check_still_reads_a_real_field(js: JsRuntime):
    payload = state_payload("failed")
    js.push(payload)
    assert js.named("field", "message") == payload["message"]


# -- 4. the page draws what the surface published ----------------------


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
        """Spin until the page defines `acervatorSetInspectorTab`, which
        `loadFinished` does not guarantee."""
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetInspectorTab") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the tab module: readyState "
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
    "whiteSpace",
    "flexGrow",
    "flexDirection",
    "display",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
]

#: EXPANDED maps a Qt shorthand to the properties it settles into.
EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
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
    "      found.push({ path: here, tag: el.tagName, attrs: attrs, text: own,"
    "        html: el.innerHTML, whole: el.textContent,"
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
    """Push the tokens into the page and apply them, since a disk-loaded view
    has no bridge."""
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
        "acervatorSetInspectorTab(JSON.parse(window.PAYLOAD));"
        "acervatorInspectorTab.renderTab(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    """Return what `READ_PARTS` finds, without rendering again."""
    return json.loads(browser.js(READ_PARTS))


def declarations_of(sheet: Any) -> list:
    """Return each property and value of `sheet`, read in Python rather than
    through the module."""
    found: list = []
    if not isinstance(sheet, str):
        return found
    for one in sheet.split(";"):
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
    """Return the computed values a bare `tag` takes from `body`."""
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


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    assert browser.js("typeof window.acervatorInspectorTab") == "object"
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_tab(browser, state_payload("failed"))
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_network_check_names_a_refused_connection(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    browser.js("var i = new Image(); i.src = 'http://127.0.0.1/x.png';")
    browser.settle(READY_STEP_MS)
    assert browser.parsed("window.VIOLATIONS") != []


def test_the_failed_tab_draws_the_message_above_the_spacer(browser: Browser):
    payload = failed_payload()
    parts = draw_tab(browser, payload)
    paths = [one["path"] for one in parts]
    assert paths == [
        "tab",
        "tab/fallback",
        "tab/fallback/message",
        "tab/fallback/message/headline",
        "tab/fallback/message/detail",
        "tab/fallback/spacer",
    ], paths
    assert payload["order"] == [
        payload["fallback"]["label_class"],
        payload["fallback"]["stretch"],
    ]


def test_the_drawn_tab_shows_the_headline_and_the_named_failure(browser: Browser):
    payload = failed_payload("ImportError", "no module named market_inspector")
    parts = draw_tab(browser, payload)
    headline = only(parts, "tab/fallback/message/headline")
    detail = only(parts, "tab/fallback/message/detail")
    assert headline["text"] == payload["fallback"]["headline_text"]
    assert detail["text"] == payload["detail"]
    assert payload["error_type"] in detail["text"]
    assert payload["error_text"] in detail["text"]


def test_the_drawn_text_check_names_one_changed_failure(browser: Browser):
    first = draw_tab(browser, failed_payload("ImportError", "no module"))
    second = draw_tab(browser, failed_payload("ValueError", "a different failure"))
    assert (
        only(first, "tab/fallback/message/detail")["text"]
        != only(second, "tab/fallback/message/detail")["text"]
    )


def test_the_delegated_tab_draws_the_view_slot_and_no_message(browser: Browser):
    payload = state_payload("delegated")
    assert payload["delegated"] is True
    parts = draw_tab(browser, payload)
    paths = [one["path"] for one in parts]
    assert paths == ["tab", "tab/view"], paths
    assert only(parts, "tab/view")["whole"] == ""


def test_the_unbuilt_tab_draws_the_shell_and_nothing_in_it(browser: Browser):
    payload = state_payload("empty")
    assert payload["order"] == []
    parts = draw_tab(browser, payload)
    assert [one["path"] for one in parts] == ["tab", "tab/fallback"]
    assert only(parts, "tab/fallback")["whole"] == ""


def test_every_drawn_child_a_check_reads_carries_a_name(browser: Browser):
    parts = draw_tab(browser, failed_payload())
    unnamed = browser.parsed(
        "(function () {"
        "  var found = [];"
        "  var walk = function (el) {"
        "    if (el.getAttribute('data-part') === null) {"
        "      found.push(el.tagName); }"
        "    Array.prototype.slice.call(el.children).forEach(walk); };"
        "  if (window.HOST.firstChild) { walk(window.HOST.firstChild); }"
        "  return found; })()"
    )
    assert unnamed == [], f"these drawn elements carry no name: {unnamed}"
    assert len(parts) == len({one["path"] for one in parts})


def test_the_name_check_reports_a_child_drawn_without_one(browser: Browser):
    draw_tab(browser, failed_payload())
    unnamed = browser.parsed(
        "(function () {"
        "  var extra = document.createElement('div');"
        "  window.HOST.firstChild.appendChild(extra);"
        "  var found = [];"
        "  var walk = function (el) {"
        "    if (el.getAttribute('data-part') === null) {"
        "      found.push(el.tagName); }"
        "    Array.prototype.slice.call(el.children).forEach(walk); };"
        "  walk(window.HOST.firstChild);"
        "  extra.remove();"
        "  return found; })()"
    )
    assert unnamed == ["DIV"]


def test_the_drawn_message_matches_a_probe_styled_from_the_surface_sheet(
    browser: Browser,
):
    payload = failed_payload()
    parts = draw_tab(browser, payload)
    drawn = only(parts, "tab/fallback/message")
    expected = probe(browser, "div", base_body(payload["style_sheet"]))
    assert expected, "the surface published no style to compare against"
    differing = {
        name: (drawn["style"][name], value)
        for name, value in expected.items()
        if drawn["style"].get(name) != value
    }
    assert not differing, f"the drawn message differs: {differing}"


def test_the_probe_comparison_names_a_changed_colour(browser: Browser):
    payload = failed_payload()
    parts = draw_tab(browser, payload)
    drawn = only(parts, "tab/fallback/message")
    other = payload["style_sheet"].replace(payload["fallback"]["color"], str(dss.ERROR))
    expected = probe(browser, "div", base_body(other))
    assert drawn["style"]["color"] != expected["color"]


def test_the_drawn_headline_carries_the_weight_the_surface_published(
    browser: Browser,
):
    payload = failed_payload()
    parts = draw_tab(browser, payload)
    drawn = only(parts, "tab/fallback/message/headline")
    expected = probe(
        browser, "strong", "font-weight:" + payload["fallback"]["headline_weight"]
    )
    assert drawn["style"]["fontWeight"] == expected["fontWeight"]


def test_the_weight_comparison_names_an_unbolded_headline(browser: Browser):
    payload = failed_payload()
    parts = draw_tab(browser, payload)
    drawn = only(parts, "tab/fallback/message/headline")
    expected = probe(browser, "span", "font-weight:normal")
    assert drawn["style"]["fontWeight"] != expected["fontWeight"]


def changed_paths(before: list, after: list) -> set:
    """Every (path, property) whose computed value moved between reads."""
    assert len(before) == len(after), "the tab drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((one["path"], key))
    return moved


def test_the_drawn_tab_follows_the_amber_token_and_nothing_else_moves(
    browser: Browser,
):
    payload = failed_payload()
    before = draw_tab(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty('--FOLD_RATIO_AMBER', "
        + json.dumps(str(dss.ERROR))
        + ");"
    )
    after = read_parts(browser)
    moved = changed_paths(before, after)
    assert moved, "the token moved nothing at all"
    assert {path for path, _ in moved} == {
        "tab/fallback/message",
        "tab/fallback/message/headline",
        "tab/fallback/message/detail",
    }, f"the colour reached parts it should not: {sorted(moved)}"
    assert {key for _, key in moved} == {
        "color",
        "borderTopColor",
    }, f"an unset border colour is currentColor, so only these move: {sorted(moved)}"


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(
    browser: Browser,
):
    before = draw_tab(browser, failed_payload())
    assert changed_paths(before, read_parts(browser)) == set()


def test_the_message_colour_is_painted_through_the_one_token_that_carries_it(
    skinned: JsRuntime,
):
    payload = failed_payload()
    skinned.push(payload)
    style = skinned.json("acervatorInspectorTab.messageStyle(JSON.parse(PAYLOAD))")
    assert "FOLD_RATIO_AMBER" in style["color"], style["color"]
    assert payload["fallback"]["color"] in style["color"]


def test_the_colour_falls_back_to_the_surface_value_with_no_token_module(
    js: JsRuntime,
):
    payload = failed_payload()
    js.push(payload)
    assert js.named("colour", payload["fallback"]["color"]) == (
        payload["fallback"]["color"]
    )
    assert js.named("variableFor", payload["fallback"]["color"]) is None


def test_the_padding_number_resolves_to_no_token_at_all(skinned: JsRuntime):
    """Two token names carry the padding number, so the length keeps it."""
    payload = failed_payload()
    skinned.push(payload)
    carried = str(payload["fallback"]["padding_px"])
    holders = sorted(n for n, v in dss.TOKENS.items() if str(v) == carried)
    assert len(holders) > 1, f"only {holders} carries {carried}"
    assert skinned.named("variableFor", payload["fallback"]["padding_px"]) is None
    assert (
        skinned.json("acervatorInspectorTab.paddingLength(JSON.parse(PAYLOAD))")
        == carried + "px"
    )


def test_the_length_rule_refuses_a_token_from_a_group_that_means_something_else(
    skinned: JsRuntime,
):
    """One name carries this motion duration, and no length may borrow it."""
    named = {
        name: value
        for name, value in dss.GROUPS["motion_ms"].items()
        if sum(1 for v in dss.TOKENS.values() if str(v) == str(value)) == 1
    }
    assert named, "no motion duration is carried by exactly one name"
    name, value = sorted(named.items())[0]
    skinned.bind_json("VALUE", value)
    assert skinned.json("acervatorInspectorTab.variableFor(JSON.parse(VALUE))") == name
    assert (
        skinned.json("acervatorInspectorTab.variableInGroups(JSON.parse(VALUE), []) ")
        is None
    )
    assert skinned.json("acervatorInspectorTab.length(JSON.parse(VALUE))") == (
        str(value) + "px"
    )


# -- 5. the Qt tab, line by line ---------------------------------------


def test_the_surface_headline_pieces_compose_the_shipped_rich_text(qapp):
    """Qt's own parser reads the shipped markup back to the plain words and
    the blank run the pieces declare."""
    from PySide6.QtGui import QTextDocument

    assert qapp is not None
    doc = QTextDocument()
    doc.setHtml(mits.FALLBACK_HEADLINE)
    plain = doc.toPlainText()
    assert plain.startswith(mits.FALLBACK_HEADLINE_TEXT)
    assert plain.count("\n") == mits.FALLBACK_HEADLINE_BREAKS
    assert mits.fallback_text("ValueError", "boom") == (
        mits.FALLBACK_HEADLINE + mits.fallback_detail("ValueError", "boom")
    )


def test_the_composition_check_names_a_headline_that_drifted(qapp):
    from PySide6.QtGui import QTextDocument

    assert qapp is not None
    doc = QTextDocument()
    doc.setHtml("<b>Something else.</b><br>")
    plain = doc.toPlainText()
    assert not plain.startswith(mits.FALLBACK_HEADLINE_TEXT)
    assert plain.count("\n") != mits.FALLBACK_HEADLINE_BREAKS


def test_the_shipped_label_reads_an_error_message_as_rich_text(qapp):
    """QLabel renders the error text as markup, so its tags never show."""
    from PySide6.QtGui import QTextDocument
    from PySide6.QtWidgets import QLabel

    assert qapp is not None
    hostile = "<b>BOLD</b>&amp;"
    shown = mits.fallback_text("RuntimeError", hostile)
    label = QLabel(shown)
    doc = QTextDocument()
    doc.setHtml(label.text())
    plain = doc.toPlainText()
    assert "<b>" not in plain, "Qt kept the tag, so nothing was interpreted"
    assert "BOLD" in plain and "&amp;" not in plain and "&" in plain


def test_the_module_draws_an_error_message_carrying_tags_as_its_own_words(
    browser: Browser,
):
    hostile = "<b>BOLD</b>&amp;"
    payload = failed_payload("RuntimeError", hostile)
    parts = draw_tab(browser, payload)
    detail = only(parts, "tab/fallback/message/detail")
    assert hostile in detail["text"], f"the tab shows {detail['text']!r}"
    assert detail["children"] == 0, "the tag was drawn as an element"
    assert "<b>" in detail["html"].replace("&lt;", "<").replace("&gt;", ">")


def test_the_module_names_an_error_text_that_carries_a_tag(js: JsRuntime):
    report = js.push(failed_payload("RuntimeError", "<b>BOLD</b>"))
    assert {
        "where": None,
        "field": "error_text",
        "fault": "markup",
        "detail": "<",
    } in report["faults"]


def test_the_markup_check_is_quiet_on_an_error_text_with_no_tag(js: JsRuntime):
    report = js.push(failed_payload("RuntimeError", "no module named x"))
    assert [one for one in report["faults"] if one["fault"] == "markup"] == []


def test_the_wrapping_mode_follows_the_word_wrap_the_surface_published(
    browser: Browser,
):
    payload = failed_payload()
    assert payload["word_wrap"] is True
    parts = draw_tab(browser, payload)
    assert only(parts, "tab/fallback/message")["style"]["whiteSpace"] == "pre-wrap"


def test_the_wrapping_mode_check_names_a_tab_that_wraps_nothing(browser: Browser):
    payload = failed_payload()
    payload["word_wrap"] = False
    parts = draw_tab(browser, payload)
    assert only(parts, "tab/fallback/message")["style"]["whiteSpace"] == "pre"


def test_the_blank_run_between_headline_and_failure_is_the_published_count(
    browser: Browser,
):
    payload = failed_payload()
    parts = draw_tab(browser, payload)
    message = only(parts, "tab/fallback/message")
    assert message["text"] == "\n" * payload["fallback"]["headline_breaks"]


def test_the_blank_run_check_names_a_different_count(js: JsRuntime):
    js.bind_json("COUNT", mits.FALLBACK_HEADLINE_BREAKS + 1)
    assert js.json("acervatorInspectorTab.breakText(JSON.parse(COUNT))") != (
        "\n" * mits.FALLBACK_HEADLINE_BREAKS
    )


def test_the_shipped_tab_declares_no_hover_or_pressed_paint(skinned: JsRuntime):
    """The Qt sheet carries one base block, so there is no state paint to
    convert and no click to wire."""
    payload = failed_payload()
    skinned.push(payload)
    skinned.bind_json("SHEET", payload["style_sheet"])
    assert skinned.json("acervatorInspectorTab.stateRules(JSON.parse(SHEET))") == []
    assert len(
        skinned.json("acervatorInspectorTab.declarations(JSON.parse(SHEET))")
    ) == len(declarations_of(payload["style_sheet"]))
    assert payload["actions"] == {}
    assert payload["timers"] == {}
    assert payload["bus_topics"] == []


def test_the_state_rule_reader_finds_a_hover_block_when_one_is_written(
    skinned: JsRuntime,
):
    skinned.bind_json("SHEET", "QLabel { color: red; } QLabel:hover { color: blue; }")
    found = skinned.json("acervatorInspectorTab.stateRules(JSON.parse(SHEET))")
    assert len(found) == 1


def test_the_drawn_tab_takes_no_focus_and_offers_no_control(browser: Browser):
    """The shipped tab holds one label and a stretch, neither focusable."""
    draw_tab(browser, failed_payload())
    found = browser.parsed(
        "(function () {"
        "  var sel = 'a,button,input,select,textarea,[tabindex],[contenteditable]';"
        "  return Array.prototype.slice.call("
        "    window.HOST.querySelectorAll(sel)).map(function (el) {"
        "      return el.tagName; }); })()"
    )
    assert found == [], f"the tab drew focusable elements: {found}"


def test_the_focus_check_reports_an_element_that_would_take_focus(browser: Browser):
    draw_tab(browser, failed_payload())
    found = browser.parsed(
        "(function () {"
        "  var b = document.createElement('button');"
        "  window.HOST.firstChild.appendChild(b);"
        "  var sel = 'a,button,input,select,textarea,[tabindex],[contenteditable]';"
        "  var seen = Array.prototype.slice.call("
        "    window.HOST.querySelectorAll(sel)).map(function (el) {"
        "      return el.tagName; });"
        "  b.remove();"
        "  return seen; })()"
    )
    assert found == ["BUTTON"]


# -- 6. hostile payloads -----------------------------------------------

#: Values JSON carries unchanged, written as the failure's own text.
HOSTILE_TEXTS = {
    "nothing at all": None,
    "a true flag": True,
    "a two hundred character message": "X" * 200,
    "markup": "<script>alert(1)</script>",
    "an empty text": "",
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


@pytest.mark.parametrize("case", sorted(HOSTILE_ALL))
def test_the_tab_shows_whatever_failure_text_the_surface_produced(
    browser: Browser, case: str
):
    payload = failed_payload("ValueError", HOSTILE_ALL[case])
    parts = draw_tab(browser, payload)
    detail = only(parts, "tab/fallback/message/detail")
    assert detail["text"] == payload["detail"], f"{case}: shows {detail['text']!r}"
    assert str(HOSTILE_ALL[case]) in detail["text"], case


@pytest.mark.parametrize("case", sorted(HOSTILE_ALL))
def test_one_hostile_failure_costs_the_headline_and_the_spacer_nothing(
    browser: Browser, case: str
):
    whole = draw_tab(browser, failed_payload("ValueError", "plain"))
    spoilt = draw_tab(browser, failed_payload("ValueError", HOSTILE_ALL[case]))
    assert [one["path"] for one in spoilt] == [one["path"] for one in whole], case
    assert (
        only(spoilt, "tab/fallback/message/headline")["text"]
        == only(whole, "tab/fallback/message/headline")["text"]
    ), case


def test_the_neighbour_check_names_a_headline_that_did_change(browser: Browser):
    whole = draw_tab(browser, failed_payload())
    payload = failed_payload()
    payload["fallback"]["headline_text"] = "changed headline"
    spoilt = draw_tab(browser, payload)
    assert (
        only(spoilt, "tab/fallback/message/headline")["text"]
        != only(whole, "tab/fallback/message/headline")["text"]
    )


@pytest.mark.parametrize("case", sorted(HOSTILE_NUMBERS))
def test_the_tab_holds_a_number_json_cannot_spell(js: JsRuntime, case: str):
    report = js.push_written(
        failed_payload(), "P.fallback.headline_breaks = " + HOSTILE_NUMBERS[case] + ";"
    )
    assert report["faults"] != [] or report["held"]["fields"] > 0
    drawn = js.json(
        "acervatorInspectorTab.breakText("
        "acervatorInspectorTab.bag('fallback').headline_breaks)"
    )
    assert drawn == "" or isinstance(drawn, str), f"{case}: {drawn!r}"


@pytest.mark.parametrize("field", sorted(mits.view_model({"reset": True})))
def test_the_tab_still_draws_with_one_field_missing(browser: Browser, field: str):
    payload = failed_payload()
    del payload[field]
    parts = draw_tab(browser, payload)
    assert at_path(parts, "tab"), f"the tab drew nothing without {field}"


@pytest.mark.parametrize("field", sorted(mits.view_model({"reset": True})))
def test_the_module_names_every_field_the_payload_drops(js: JsRuntime, field: str):
    payload = failed_payload()
    del payload[field]
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"], f"{field} went unnamed"


@pytest.mark.parametrize("field", sorted(mits.view_model({"reset": True})))
def test_the_module_names_every_field_the_payload_nulls(js: JsRuntime, field: str):
    payload = failed_payload()
    payload[field] = None
    report = js.push(payload)
    if field == "view":
        assert [one for one in report["faults"] if one["field"] == "view"] == []
        return
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"], f"{field} went unnamed"


WRONG_TYPES = {
    "accessible_name": 1.0,
    "message": 1.0,
    "detail": 1.0,
    "error_text": 1.0,
    "style_sheet": 1.0,
    "error_type": 1.0,
    "word_wrap": "yes",
}


@pytest.mark.parametrize("field", sorted(WRONG_TYPES))
def test_the_module_names_a_wrong_type_where_a_default_holds_it(
    js: JsRuntime, field: str
):
    payload = failed_payload()
    payload[field] = WRONG_TYPES[field]
    report = js.push(payload)
    named = [
        one
        for one in report["faults"]
        if one["field"] == field and one["fault"] == "wrong-type"
    ]
    assert named, f"{field} carried a {type(WRONG_TYPES[field]).__name__} unnamed"


def test_the_wrong_type_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(failed_payload())
    assert [one for one in report["faults"] if one["fault"] == "wrong-type"] == []


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    js.push(failed_payload())
    report = js.push([])
    assert js.json("acervatorInspectorTab.isLoaded()") is False
    assert report["declared"] is None
    assert js.json("acervatorInspectorTab.order()") == []
    assert report["faults"] == [
        {"where": None, "field": None, "fault": "not-an-object", "detail": "object"}
    ]


def test_a_hostile_payload_still_draws_the_tab(browser: Browser):
    payload = failed_payload()
    for name in ("fallback", "order", "style_sheet", "detail"):
        payload[name] = None
    parts = draw_tab(browser, payload)
    assert [one["path"] for one in parts] == ["tab", "tab/fallback"]


def test_the_bridge_cannot_carry_a_not_a_number_at_all(js: JsRuntime):
    """The #257 path, measured on this surface: the view echo publishes a
    bare NaN that JSON.parse refuses."""
    payload = mits.view_model({"reset": True, "view": float("nan"), "build": True})
    written = json.dumps(payload)
    assert "NaN" in written
    js.bind_text("BROKEN", written)
    result = js.run(
        "(function () { try { JSON.parse(BROKEN); return 'parsed'; }"
        " catch (e) { return e.name; } })()"
    )
    assert result.toString() == "SyntaxError"


def test_the_bridge_check_parses_the_same_payload_with_a_finite_view(js: JsRuntime):
    written = json.dumps(mits.view_model({"reset": True, "view": 1.0, "build": True}))
    assert "NaN" not in written
    js.bind_text("WHOLE", written)
    result = js.run(
        "(function () { try { JSON.parse(WHOLE); return 'parsed'; }"
        " catch (e) { return e.name; } })()"
    )
    assert result.toString() == "parsed"


def test_the_failure_path_of_the_surface_cannot_publish_a_bare_number_word():
    """Every failure text reaches the payload through a format, so the
    fallback screen carries no value JSON refuses."""
    for value in (float("nan"), float("inf"), float("-inf")):
        payload = mits.view_model(
            {"reset": True, "error": {"type": "ValueError", "text": value}}
        )
        written = json.dumps(payload)
        assert "NaN" not in written and "Infinity" not in written, value


# -- 7. the bridge ask --------------------------------------------------

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
    js.bind_json("PAYLOAD", failed_payload())
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadInspectorTab();")
    drain_events()
    assert js.json("window.CALLS") == [[mits.METHOD, {}]]
    assert js.json("acervatorInspectorTab.isLoaded()") is True


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", failed_payload())
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadInspectorTab(); acervatorLoadInspectorTab();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", failed_payload())
    js.run(FAKE_BRIDGE)
    js.run("acervatorLoadInspectorTab();")
    drain_events()
    js.run("acervatorInspectorTab.forget(); acervatorLoadInspectorTab();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_a_refused_first_ask_is_not_remembered(js: JsRuntime):
    js.run(REFUSING_BRIDGE)
    js.run("acervatorLoadInspectorTab();")
    drain_events()
    assert js.json("acervatorInspectorTab.loadError()") == "refused"
    js.run("acervatorLoadInspectorTab();")
    drain_events()
    assert js.json("window.REFUSALS") == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadInspectorTab();")
    drain_events()
    assert js.json("acervatorInspectorTab.loadError()") == (
        "the preload bridge is not present"
    )


# -- 8. the page --------------------------------------------------------


def test_the_page_names_the_tab_module_among_its_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("market_inspector_tab.js")]
    assert named, "index.html names no market inspector tab module"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH.resolve()


def test_the_page_loads_the_tab_module_after_the_modules_it_uses():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    at = [i for i, ref in enumerate(refs) if ref.endswith("market_inspector_tab.js")][0]
    for needed in (
        "design_tokens.js",
        "shared_widgets.js",
        "header_strip.js",
        "react.production.min.js",
        "react-dom.production.min.js",
    ):
        before = [i for i, ref in enumerate(refs) if ref.endswith(needed)]
        assert before and before[0] < at, needed + " is not loaded first"


def test_the_module_reuses_the_sheet_rule_rather_than_copying_it(skinned: JsRuntime):
    payload = failed_payload()
    skinned.push(payload)
    skinned.bind_json("SHEET", payload["style_sheet"])
    assert skinned.json(
        "acervatorInspectorTab.styleOf(JSON.parse(SHEET))"
    ) == skinned.json("acervatorHeader.styleOf(JSON.parse(SHEET))")
    skinned.bind_json("VALUE", payload["fallback"]["color"])
    assert skinned.json(
        "acervatorInspectorTab.variableFor(JSON.parse(VALUE))"
    ) == skinned.json("acervatorWidgets.variableFor(JSON.parse(VALUE))")


def test_the_sheet_rule_answers_an_empty_style_with_the_header_module_absent(
    js: JsRuntime,
):
    payload = failed_payload()
    js.bind_json("SHEET", payload["style_sheet"])
    assert js.json("acervatorInspectorTab.styleOf(JSON.parse(SHEET))") == {}
    assert js.json("acervatorInspectorTab.declarations(JSON.parse(SHEET))") == []
