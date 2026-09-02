"""``notification_spool.js`` against ``notification_spool_surface.py``,
run in QJSEngine and drawn in QWebEngineView."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import notification_spool_surface as nss
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "notification_spool.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
THEMES_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
WIDGETS_PATH = REPO_ROOT / "src" / "gui" / "web" / "shared_widgets.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body can write into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100

#: Python type -> the JavaScript type the same value has after the
#: bridge's ``json.dumps``.
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

LEVEL_NAMES = tuple(nss.LEVEL_COLORS)

#: The states the surface serves, no message here a word the module writes.
STATES = {
    "empty": [],
    "one_info": [{"message": "venue reachable", "level": "info"}],
    "every_level": [
        {"message": "event on " + name, "level": name} for name in LEVEL_NAMES
    ],
    "unnamed_level": [{"message": "event of no level", "level": "chatter"}],
    "default_level": [{"message": "event with no level named"}],
    "many": [{"message": "event " + str(at), "level": "market"} for at in range(5)],
}
STATE_NAMES = tuple(STATES)


def spool_payload(messages: Any = None) -> dict:
    model = nss.NotificationSpoolModel()
    answer = nss.build_view_model(model, list(messages or []))
    return json.loads(json.dumps(answer, ensure_ascii=True))


def state_payload(name: str) -> dict:
    return spool_payload(STATES[name])


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):

    module_path = MODULE_PATH
    setter = "acervatorSetSpool"

    def load_tokens(self) -> None:
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_themes(self, name: str) -> None:
        self.run(THEMES_PATH.read_text(encoding="utf-8"))
        self.bind_json("THEMES", theme_payload())
        self.bind_json("THEME_NAME", name)
        self.run("acervatorSetThemes(JSON.parse(THEMES));")
        self.run("acervatorThemes.select(JSON.parse(THEME_NAME));")

    def load_widgets(self) -> None:
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def named(self, api: str, name: Any) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorSpool." + api + "(JSON.parse(NAME))")

    def variable_for(self, value: Any) -> Any:
        self.bind_json("VALUE", value)
        return self.json("acervatorWidgets.variableFor(JSON.parse(VALUE))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding one line of each level."""
    js.push(state_payload("every_level"))
    return js


#: Every field the surface publishes, and the module call answering for it.
MODULE_READERS = {
    "default_level_color": "acervatorSpool.defaultLevelColour()",
    "document": "acervatorSpool.document()",
    "document_blocks": "acervatorSpool.documentBlocks()",
    "level_colors": "acervatorSpool.levelColours()",
    "timestamp_color": "acervatorSpool.timestampColour()",
    "widget": "acervatorSpool.widget()",
}


def unreachable_fields(payload: dict) -> list:
    return sorted(set(payload) - set(MODULE_READERS))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    """A field the module never carries is a value that stops at the bridge."""
    payload = state_payload(state)
    js.push(payload)
    missing = unreachable_fields(payload)
    assert not missing, f"{len(missing)} published fields have no reader: {missing}"
    extra = sorted(set(MODULE_READERS) - set(payload))
    assert not extra, f"the module reads fields the surface has none of: {extra}"
    differing = {
        field: (payload[field], js.json(reader))
        for field, reader in MODULE_READERS.items()
        if js.json(reader) != payload[field]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields "
        f"differ: {sorted(differing)}"
    )
    assert len(MODULE_READERS) == len(payload)


def test_the_whole_payload_check_names_a_field_only_the_surface_holds():
    """The surface side of the comparison, with one extra name."""
    payload = dict(spool_payload())
    payload["only_on_the_surface"] = []
    assert unreachable_fields(payload) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_reads():
    """The module side of the comparison, with one field taken away."""
    payload = dict(spool_payload())
    dropped = payload.pop("level_colors")
    assert dropped is not None
    assert sorted(set(MODULE_READERS) - set(payload)) == ["level_colors"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_counts_declared_blocks_and_held_lines_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["blocks"] == payload["document_blocks"]
    assert report["held"]["lines"] == len(payload["document"]["lines"])


def test_an_empty_document_reports_one_block_and_no_line(js: JsRuntime):
    report = js.push(state_payload("empty"))
    assert report["declared"]["blocks"] == 1
    assert report["held"]["lines"] == 0


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    """The counts above, driven with one field gone."""
    payload = spool_payload()
    del payload["level_colors"]
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(MODULE_READERS) - 1


def test_the_module_names_the_fields_the_surface_declares(loaded: JsRuntime):
    """The module's own field list, against the payload it was given."""
    assert sorted(loaded.json("acervatorSpool.declaredFields()")) == sorted(
        spool_payload()
    )


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_holds_every_line_the_surface_published(js: JsRuntime, state: str):
    """A line the surface publishes that the module never holds is a
    notification the operator would not see."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json("acervatorSpool.lines()") == payload["document"]["lines"]


def test_the_line_check_names_a_line_only_the_surface_holds(js: JsRuntime):
    """A comparison that could not report would agree with any list."""
    payload = state_payload("many")
    dropped = payload["document"]["lines"].pop()
    js.push(payload)
    held = js.json("acervatorSpool.lines()")
    assert dropped not in held
    assert len(held) == len(state_payload("many")["document"]["lines"]) - 1


def spool_values() -> set:
    found: set = {
        str(nss.MAX_HEIGHT_PX),
        str(nss.MAX_HEIGHT_PX) + "px",
        str(nss.MAX_BLOCKS),
        nss.PLACEHOLDER_TEXT,
        nss.ACCESSIBLE_NAME,
        nss.TIMESTAMP_COLOR,
        nss.DEFAULT_LEVEL_COLOR,
    }
    found |= {str(one) for one in nss.LEVEL_COLORS.values()}
    for name in STATE_NAMES:
        for line in state_payload(name)["document"]["lines"]:
            found |= {str(line["stamp"]), str(line["message"]), str(line["color"])}
            found.add(line["html"])
    found.discard("")
    return found


def token_values() -> set:
    """Every value the token and theme tables carry, in CSS spelling."""
    found: set = set()
    for value in dss.TOKENS.values():
        found.add(str(value))
        found.add(str(value) + "px")
    for theme in tes.THEMES.values():
        for value in theme.values():
            found.add(str(value))
    found.discard("")
    return found


def published_strings() -> set:
    """Every string the surface publishes, at any depth."""
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
    found.add(nss.METHOD)
    found.discard("")
    return found


SKIN_VALUES = spool_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every published string the module writes, each one a name.
NAMED_WORDS = sorted(
    {
        "accessible_name",
        "b",
        "color",
        "default_level_color",
        "document",
        "document_blocks",
        "g",
        "level",
        "level_colors",
        "lines",
        "maximum_block_count",
        "maximum_height_px",
        "message",
        "notification_spool.lines",
        "placeholder_text",
        "r",
        "read_only",
        "stamp",
        "timestamp_color",
        "widget",
    }
)

#: Every other string the module writes: CSS words, tags and fault words.
OWN_WORDS = sorted(
    {
        "",
        " ",
        ")",
        ", ",
        ".",
        "acervator-notification-line",
        "acervator-notification-spool",
        "anywhere",
        "aria-label",
        "auto",
        "channel-mismatch",
        "data-document-blocks",
        "data-level",
        "data-maximum-block-count",
        "data-part",
        "data-read-only",
        "div",
        "function",
        "line",
        "line:",
        "missing",
        "not-an-object",
        "null",
        "number",
        "object",
        "placeholder",
        "px",
        "rgb(",
        "short-list",
        "span",
        "spool",
        "the preload bridge is not present",
        "unnamed-level",
        "use strict",
        "var(--",
    }
)


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "notification_spool.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    """A colour typed here drifts from the surface the next time a level
    changes colour, and nothing reports the drift."""
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"notification_spool.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_pane_paints():
    """A colour, a height, a message or a whole line of HTML spelled out
    in the module."""
    written = sorted(set(MODULE_LITERALS["strings"]) & SKIN_VALUES)
    assert not written, f"notification_spool.js spells out pane values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"notification_spool.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    """Every published string the module holds, listed rather than
    silently skipped by the scans above."""
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert written == NAMED_WORDS, (
        f"the module names {sorted(set(written) - set(NAMED_WORDS))} more and "
        f"{sorted(set(NAMED_WORDS) - set(written))} fewer published strings "
        "than the list allows"
    )


def test_every_string_the_module_writes_is_listed():
    """Nothing the module spells out escapes both lists, so a value added
    later cannot arrive unnamed."""
    written = sorted(set(MODULE_LITERALS["strings"]))
    assert written == sorted(set(NAMED_WORDS) | set(OWN_WORDS))


def test_every_listed_word_is_a_name_and_not_a_value_the_pane_shows():
    """A word that is also a colour, a height or a message does not
    belong on either list."""
    overlap = sorted((set(NAMED_WORDS) | set(OWN_WORDS)) & SKIN_VALUES)
    assert not overlap, f"these listed words are values the pane paints: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "notification_spool.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


PLANTED_LINES = {
    "level_colour": 'var written = "' + str(nss.LEVEL_COLORS["warning"]) + '";',
    "stamp_colour": 'var written = "' + str(nss.TIMESTAMP_COLOR) + '";',
    "height": 'var written = "' + str(nss.MAX_HEIGHT_PX) + 'px";',
    "number": "var written = 12;",
    "placeholder": 'var written = "' + nss.PLACEHOLDER_TEXT + '";',
    "accessible_name": 'var written = "' + nss.ACCESSIBLE_NAME + '";',
    "token_value": 'var written = "' + str(dss.PRIMARY) + '";',
    "regex": "var written = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the checks above report on ``source``."""
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


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_one_written_value(kind: str):
    caught = caught_by_scan(PLANTED_LINES[kind])
    assert caught, f"the scan reported nothing on the written {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_written_value_is_caught_in_the_module_file_itself():
    original = MODULE_PATH.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    assert original.decode("utf-8") == MODULE_SOURCE
    caught_each = {}
    try:
        for kind in sorted(PLANTED_LINES):
            swap_module(MODULE_PATH, original + PLANTED_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(MODULE_PATH, original)
            after = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
            assert after == before, f"the file was not restored after the {kind} line"
    finally:
        swap_module(MODULE_PATH, original)
    quiet = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not quiet, f"the scan reported nothing on these lines in the file: {quiet}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_written_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    """Every appended line leaves the file valid JavaScript, so a page
    loading it mid-scan still defines the pane module."""
    for kind, line in sorted(PLANTED_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetSpool") == "function", kind


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
    expected = python_kinds(payload)
    actual = js.json("acervatorSpool.kinds()")
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
    """A payload with a text where a number belongs must read as exactly
    one difference."""
    payload = state_payload("one_info")
    payload["widget"]["maximum_height_px"] = str(payload["widget"]["maximum_height_px"])
    js.push(payload)
    expected = python_kinds(state_payload("one_info"))
    actual = js.json("acervatorSpool.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["widget.maximum_height_px"], f"the check named {differing}"


@pytest.mark.parametrize("level", LEVEL_NAMES)
def test_every_level_colour_agrees_with_the_surface(js: JsRuntime, level: str):
    """A level painted in another level's colour tells the operator an
    error is a success."""
    payload = state_payload("every_level")
    js.push(payload)
    assert js.named("levelColour", level) == payload["level_colors"][level]


def test_the_level_colour_check_names_a_changed_channel(js: JsRuntime):
    payload = state_payload("every_level")
    payload["level_colors"]["error"][0] += 1
    js.push(payload)
    assert (
        js.named("levelColour", "error")
        != state_payload("every_level")["level_colors"]["error"]
    )


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_names_no_fault_on_a_whole_payload(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    named = [one["fault"] for one in report["faults"]]
    if state == "unnamed_level":
        assert named == ["unnamed-level"], report["faults"]
        return
    assert report["faults"] == [], f"{state}: {report['faults']}"


def test_a_level_the_colour_table_does_not_name_is_reported(js: JsRuntime):
    payload = state_payload("unnamed_level")
    report = js.push(payload)
    assert {
        "where": "line:0",
        "field": "level",
        "fault": "unnamed-level",
        "detail": "chatter",
    } in report["faults"]
    assert payload["document"]["lines"][0]["color"] == nss.DEFAULT_LEVEL_COLOR


def test_a_line_painted_in_another_level_s_colour_is_named(js: JsRuntime):
    payload = state_payload("every_level")
    line = payload["document"]["lines"][0]
    line["r"], line["g"], line["b"] = payload["level_colors"]["error"]
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "channel-mismatch"]
    assert named, report["faults"]
    assert {one["field"] for one in named} <= {"r", "g", "b"}
    assert {one["where"] for one in named} == {"line:0"}


def test_the_channel_check_is_quiet_on_every_shipped_line(js: JsRuntime):
    for state in STATE_NAMES:
        report = js.push(state_payload(state))
        named = [one for one in report["faults"] if one["fault"] == "channel-mismatch"]
        assert named == [], f"{state}: {named}"


def test_the_module_reports_only_what_it_was_given(js: JsRuntime):
    """Every value comes from the payload and none from the module."""
    payload = state_payload("one_info")
    payload["widget"]["placeholder_text"] = "given placeholder"
    payload["widget"]["accessible_name"] = "given name"
    js.push(payload)
    assert js.json("acervatorSpool.widget()") == payload["widget"]
    assert not {"given placeholder", "given name"} & SKIN_VALUES


def carriers_of(value: Any) -> list:
    """Every non-alias design token carrying ``value``."""
    tokens = token_payload()
    aliases = tokens["alias_targets"]
    return sorted(
        name
        for name, held in tokens["tokens"].items()
        if str(held) == str(value) and name not in aliases
    )


PANE_COLOURS = sorted(
    {str(one) for one in nss.LEVEL_COLORS.values()} | {str(nss.DEFAULT_LEVEL_COLOR)}
)


def test_every_message_colour_resolves_to_one_token(js: JsRuntime):
    js.load_tokens()
    js.load_widgets()
    assert PANE_COLOURS, "the pane paints no colour; the check cannot report"
    for colour in PANE_COLOURS:
        assert carriers_of(colour) == [
            js.variable_for(colour)
        ], f"{colour} is carried by {carriers_of(colour)}"


def test_the_pane_height_is_painted_from_the_surface_and_not_from_a_token(
    js: JsRuntime,
):
    js.load_tokens()
    js.load_widgets()
    carriers = carriers_of(nss.MAX_HEIGHT_PX)
    assert carriers == ["MOTION_SHORT"], f"{nss.MAX_HEIGHT_PX} -> {carriers}"
    assert js.variable_for(nss.MAX_HEIGHT_PX) == "MOTION_SHORT"
    assert "MOTION_SHORT" not in MODULE_SOURCE


def test_a_value_no_token_carries_resolves_to_none(js: JsRuntime):
    """A value off the table is painted from the surface rather than
    through a variable nothing answers."""
    js.load_tokens()
    js.load_widgets()
    assert js.variable_for("no-token-carries-this") is None


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
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
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetSpool") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the pane module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
            + ", tokens "
            + str(self.js("typeof window.acervatorSetTokens"))
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


#: Every computed style property read off each drawn part.
STYLE_NAMES = [
    "color",
    "maxHeight",
    "display",
    "backgroundColor",
    "overflowY",
    "overflowWrap",
]

#: CROWDED holds enough lines that the pane must scroll to the newest.
CROWDED = [
    {"message": "event number " + str(at), "level": "market"} for at in range(40)
]

PANE_SCROLL = (
    "(function () { var pane = window.HOST.firstChild;"
    "  return JSON.stringify({ top: pane.scrollTop,"
    "    height: pane.scrollHeight, seen: pane.clientHeight }); })()"
)

#: HOST is given a width because an unshown view reads `clientWidth` as 0.
PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '400px';"
    "document.body.appendChild(window.HOST);"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeStyle = function (cssText, names) {"
    "  var probe = document.createElement('span');"
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
    "        text: own, elements: el.getElementsByTagName('*').length,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)

CLIENT_WIDTH = "window.HOST.clientWidth"


def give_tokens(browser: Browser) -> int:
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_spool(browser: Browser, payload: dict) -> list:
    """Draw the pane into the page and read every named part back."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetSpool(JSON.parse(window.PAYLOAD));"
        "acervatorSpool.renderSpool(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    """Read every drawn part again without redrawing."""
    return json.loads(browser.js(READ_PARTS))


def probe(browser: Browser, body: str, names: list) -> dict:
    return browser.parsed(
        "window.probeStyle(" + json.dumps(body) + ", " + json.dumps(names) + ")"
    )


def colour_probe(browser: Browser, declared: str) -> str:
    """One declared colour, as the page computes it."""
    return probe(browser, "color: " + declared, ["color"])["color"]


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def changed_paths(before: list, after: list) -> set:
    """Every (path, property) whose computed value moved between reads."""
    assert len(before) == len(after), "the pane drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((one["path"], key))
    return moved


def rgb_of(channels: list) -> str:
    """One published triple, spelled as CSS spells it."""
    return "rgb(" + ", ".join(str(one) for one in channels) + ")"


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorSpool") == "object"
    assert browser.js("typeof window.acervatorSetSpool") == "function"
    assert browser.js("typeof window.acervatorLoadSpool") == "function"


def test_the_host_element_has_a_width_before_anything_is_drawn(browser: Browser):
    browser.js(PAGE_HELPERS)
    assert browser.js(CLIENT_WIDTH) > 0


def test_every_child_the_checks_read_carries_its_own_name(browser: Browser):
    parts = draw_spool(browser, state_payload("one_info"))
    assert [one["path"] for one in parts] == [
        "spool",
        "spool/line",
        "spool/line/stamp",
        "spool/line/message",
    ]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_drawn_pane_shows_every_line_the_surface_published(
    browser: Browser, state: str
):
    """What the operator reads off the screen, against what the surface
    produced, in every state."""
    payload = state_payload(state)
    parts = draw_spool(browser, payload)
    lines = payload["document"]["lines"]
    assert len(at_path(parts, "spool/line")) == len(lines)
    stamps = [one["text"] for one in at_path(parts, "spool/line/stamp")]
    messages = [one["text"] for one in at_path(parts, "spool/line/message")]
    assert stamps == [one["stamp"] for one in lines]
    assert messages == [one["message"] for one in lines]


def test_the_line_text_check_names_one_changed_message(browser: Browser):
    """A read that returned the same text whatever was drawn would report
    agreement on a changed notification."""
    payload = state_payload("many")
    payload["document"]["lines"][0]["message"] += " and more"
    parts = draw_spool(browser, payload)
    shown = [one["text"] for one in at_path(parts, "spool/line/message")]
    original = [one["message"] for one in state_payload("many")["document"]["lines"]]
    differing = [at for at, one in enumerate(original) if shown[at] != one]
    assert differing == [0], f"the check named {differing}"


def test_the_drawn_message_takes_the_colour_the_surface_published(browser: Browser):
    payload = state_payload("every_level")
    parts = draw_spool(browser, payload)
    messages = at_path(parts, "spool/line/message")
    lines = payload["document"]["lines"]
    assert len(messages) == len(lines)
    for at, line in enumerate(lines):
        wanted = colour_probe(browser, line["color"])
        assert messages[at]["style"]["color"] == wanted, (
            f"{line['level']} drew {messages[at]['style']['color']}, "
            f"the surface's own value computes to {wanted}"
        )


def test_the_message_colour_check_names_one_changed_colour(browser: Browser):
    """A comparison that could not report would pass on a warning painted
    in the error colour."""
    payload = state_payload("every_level")
    original = payload["document"]["lines"][0]["color"]
    payload["document"]["lines"][0]["color"] = str(nss.LEVEL_COLORS["error"])
    parts = draw_spool(browser, payload)
    drawn = at_path(parts, "spool/line/message")[0]["style"]["color"]
    assert drawn != colour_probe(browser, original)
    assert drawn == colour_probe(browser, str(nss.LEVEL_COLORS["error"]))


def test_the_drawn_stamp_takes_the_channels_the_surface_published(browser: Browser):
    payload = state_payload("one_info")
    parts = draw_spool(browser, payload)
    stamp = only(parts, "spool/line/stamp")
    wanted = colour_probe(browser, rgb_of(payload["timestamp_color"]))
    assert stamp["style"]["color"] == wanted


def test_the_stamp_reads_its_channels_in_the_order_the_surface_wrote_them(
    browser: Browser,
):
    payload = state_payload("one_info")
    payload["timestamp_color"] = [1, 2, 3]
    parts = draw_spool(browser, payload)
    assert only(parts, "spool/line/stamp")["style"]["color"] == "rgb(1, 2, 3)"


def test_the_drawn_pane_takes_the_height_the_surface_published(browser: Browser):
    """The pane is capped so the notification list never pushes the rest
    of the tab off the screen."""
    payload = state_payload("many")
    pane = only(draw_spool(browser, payload), "spool")
    assert pane["style"]["maxHeight"] == str(payload["widget"]["maximum_height_px"]) + (
        "px"
    )
    assert pane["attrs"]["aria-label"] == payload["widget"]["accessible_name"]
    assert (
        pane["attrs"]["data-read-only"] == str(payload["widget"]["read_only"]).lower()
    )
    assert pane["attrs"]["data-maximum-block-count"] == str(
        payload["widget"]["maximum_block_count"]
    )
    assert pane["attrs"]["data-document-blocks"] == str(payload["document_blocks"])


def test_the_height_check_names_a_changed_height(browser: Browser):
    """A read that returned the same length whatever was drawn would
    report agreement on a pane twice the size."""
    payload = state_payload("many")
    payload["widget"]["maximum_height_px"] *= 2
    pane = only(draw_spool(browser, payload), "spool")
    assert pane["style"]["maxHeight"] == str(nss.MAX_HEIGHT_PX * 2) + "px"


def test_the_pane_scrolls_where_qt_scrolls(browser: Browser):
    payload = spool_payload(CROWDED)
    pane = only(draw_spool(browser, payload), "spool")
    assert pane["style"]["overflowY"] == "auto"
    seen = json.loads(browser.js(PANE_SCROLL))
    assert seen["height"] > seen["seen"], f"the pane did not overflow: {seen}"


def test_the_pane_jumps_to_the_newest_line_after_a_draw(browser: Browser):
    payload = spool_payload(CROWDED)
    draw_spool(browser, payload)
    seen = json.loads(browser.js(PANE_SCROLL))
    assert seen["top"] > 0, f"the pane stayed at the top: {seen}"
    assert seen["top"] == seen["height"] - seen["seen"], seen


def test_the_scroll_check_reads_a_short_pane_as_unscrolled(browser: Browser):
    draw_spool(browser, state_payload("one_info"))
    seen = json.loads(browser.js(PANE_SCROLL))
    assert seen["top"] == 0, seen
    assert seen["height"] <= seen["seen"], seen


def test_a_long_message_wraps_where_qt_wraps_it(browser: Browser):
    payload = spool_payload([{"message": "x" * 200, "level": "info"}])
    parts = draw_spool(browser, payload)
    assert only(parts, "spool/line")["style"]["overflowWrap"] == "anywhere"
    width = browser.js("window.HOST.querySelector('[data-part=\"line\"]').scrollWidth")
    assert width <= browser.js(CLIENT_WIDTH), f"the line ran {width} wide"


def test_the_wrap_check_reads_a_wider_line_as_wider(browser: Browser):
    payload = spool_payload([{"message": "x" * 200, "level": "info"}])
    draw_spool(browser, payload)
    ran = browser.js(
        "(function () { var line ="
        "  window.HOST.querySelector('[data-part=\"line\"]');"
        "  line.style.overflowWrap = 'normal';"
        "  line.style.whiteSpace = 'pre';"
        "  return line.scrollWidth; })()"
    )
    assert ran > browser.js(CLIENT_WIDTH), f"the unwrapped line drew {ran} wide"


def test_an_empty_pane_draws_the_placeholder_the_surface_published(browser: Browser):
    payload = state_payload("empty")
    parts = draw_spool(browser, payload)
    assert only(parts, "spool/placeholder")["text"] == (
        payload["widget"]["placeholder_text"]
    )
    assert at_path(parts, "spool/line") == []


def test_the_placeholder_check_reads_a_filled_pane_as_filled(browser: Browser):
    parts = draw_spool(browser, state_payload("one_info"))
    assert at_path(parts, "spool/placeholder") == []
    assert len(at_path(parts, "spool/line")) == 1


def test_the_drawn_pane_follows_a_level_token_and_nothing_else_moves(browser: Browser):
    payload = state_payload("every_level")
    before = draw_spool(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty('--WARNING', "
        + json.dumps(str(dss.ERROR))
        + ");"
    )
    moved = changed_paths(before, read_parts(browser))
    assert moved, "the token moved nothing at all"
    assert {key for _, key in moved} == {"color"}
    assert {path for path, _ in moved} == {"spool/line/message"}
    after = at_path(read_parts(browser), "spool/line/message")
    warning_at = [one["level"] for one in payload["document"]["lines"]].index("warning")
    assert after[warning_at]["style"]["color"] == colour_probe(browser, str(dss.ERROR))


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(browser: Browser):
    """A comparison that reported a difference on every read would pass
    the check above without proving anything."""
    before = draw_spool(browser, state_payload("every_level"))
    assert changed_paths(before, read_parts(browser)) == set()


def test_the_stamp_colour_follows_no_token_at_all(browser: Browser):
    assert carriers_of(nss.TIMESTAMP_COLOR) == ["TEXT_PLACEHOLDER"]
    before = draw_spool(browser, state_payload("one_info"))
    browser.js(
        "document.documentElement.style.setProperty('--TEXT_PLACEHOLDER', "
        + json.dumps(str(dss.ERROR))
        + ");"
    )
    assert changed_paths(before, read_parts(browser)) == set()


HOSTILE_MESSAGES = {
    "a true flag": True,
    "a number where text belongs": 7,
    "text where a number belongs": "1234.5",
    "a very large integer": 10**24,
    "not a number": float("nan"),
    "an infinity": float("inf"),
    "two hundred characters": "x" * 200,
    "markup": "<script>alert(1)</script>",
    "bold markup": "<b>louder</b>",
    "nothing at all": None,
}


@pytest.mark.parametrize("case", sorted(HOSTILE_MESSAGES))
def test_a_hostile_message_is_drawn_as_the_text_it_is(browser: Browser, case: str):
    payload = spool_payload([{"message": HOSTILE_MESSAGES[case], "level": "info"}])
    parts = draw_spool(browser, payload)
    drawn = only(parts, "spool/line/message")
    assert drawn["text"] == payload["document"]["lines"][0]["message"]
    assert drawn["elements"] == 0, f"{case} drew {drawn['elements']} elements"
    assert browser.js("window.HOST.getElementsByTagName('script').length") == 0
    assert browser.js("window.HOST.getElementsByTagName('b').length") == 0


def test_the_markup_check_counts_the_elements_a_page_would_grow(browser: Browser):
    """A count that answered zero for every element would pass every row
    of the table above."""
    parts = draw_spool(browser, state_payload("one_info"))
    assert only(parts, "spool")["elements"] > 0
    assert (
        browser.js(
            "(function () { var probe = document.createElement('div');"
            " probe.innerHTML = '<b>x</b>';"
            " return probe.getElementsByTagName('b').length; })()"
        )
        == 1
    )


@pytest.mark.parametrize("case", sorted(HOSTILE_MESSAGES))
def test_a_hostile_message_reaches_the_module_as_the_text_the_surface_made(
    js: JsRuntime, case: str
):
    payload = spool_payload([{"message": HOSTILE_MESSAGES[case], "level": "info"}])
    written = json.dumps(payload)
    assert "NaN" not in written and "Infinity" not in written
    js.push(payload)
    assert js.json("acervatorSpool.lines()") == payload["document"]["lines"]


def test_a_payload_carrying_a_bare_nan_never_reaches_the_module(js: JsRuntime):
    js.push(state_payload("one_info"))
    before = js.json("acervatorSpool.lines()")
    broken = state_payload("one_info")
    broken["timestamp_color"] = [float("nan"), 0, 0]
    js.bind_json("BROKEN", broken)
    refused = js.json(
        "(function () { try { JSON.parse(BROKEN); return null; }"
        " catch (e) { return e.name; } })()"
    )
    assert refused is not None, "JSON.parse accepted the frame"
    assert js.json("acervatorSpool.lines()") == before


def test_the_bare_nan_check_accepts_a_frame_the_bridge_can_write(js: JsRuntime):
    js.bind_json("WHOLE", state_payload("one_info"))
    refused = js.json(
        "(function () { try { JSON.parse(WHOLE); return null; }"
        " catch (e) { return e.name; } })()"
    )
    assert refused is None


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_field_the_payload_omits_is_named_as_missing(js: JsRuntime, field: str):
    """The surface sent a payload with one field gone."""
    payload = state_payload("one_info")
    del payload[field]
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"]
    assert report["held"]["fields"] == len(MODULE_READERS) - 1


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_field_carrying_null_is_named(js: JsRuntime, field: str):
    """A null is reported, not swapped for a value of the module's own."""
    payload = state_payload("one_info")
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(state_payload("one_info"))
    kinds = [one["fault"] for one in report["faults"]]
    assert "missing" not in kinds
    assert "null" not in kinds


@pytest.mark.parametrize(
    "field", ["timestamp_color", "default_level_color", "level_colors"]
)
def test_a_colour_that_is_not_three_channels_is_named(js: JsRuntime, field: str):
    payload = state_payload("one_info")
    if field == "level_colors":
        payload[field]["info"] = [1, 2]
        where, named = "level_colors", "info"
    else:
        payload[field] = [1, 2]
        where, named = None, field
    report = js.push(payload)
    assert {
        "where": where,
        "field": named,
        "fault": "short-list",
        "detail": 2,
    } in report["faults"]


def test_a_colour_that_is_a_text_is_named_with_the_type_it_arrived_as(js: JsRuntime):
    """A hex string where three channels belong."""
    payload = state_payload("one_info")
    payload["timestamp_color"] = str(nss.TIMESTAMP_COLOR)
    report = js.push(payload)
    assert {
        "where": None,
        "field": "timestamp_color",
        "fault": "short-list",
        "detail": "string",
    } in report["faults"]


def test_the_short_list_check_is_quiet_on_every_shipped_state(js: JsRuntime):
    for state in STATE_NAMES:
        report = js.push(state_payload(state))
        named = [one for one in report["faults"] if one["fault"] == "short-list"]
        assert named == [], f"{state}: {named}"


def test_a_line_that_is_not_an_object_is_named_and_draws_nothing(
    browser: Browser, js: JsRuntime
):
    """A document carrying a number where a line belongs."""
    payload = state_payload("one_info")
    payload["document"]["lines"].append(7)
    report = js.push(payload)
    assert {
        "where": "line:1",
        "field": None,
        "fault": "not-an-object",
        "detail": "number",
    } in report["faults"]
    parts = draw_spool(browser, payload)
    assert len(at_path(parts, "spool/line")) == 1


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    """A bridge answering with a string or a number draws nothing."""
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorSpool.isLoaded()") is False
        assert js.json("acervatorSpool.lines()") == []
        assert report["declared"] is None
        assert report["held"] is None
        assert [one["fault"] for one in report["faults"]] == ["not-an-object"]


def test_a_name_the_payload_never_carried_is_not_a_level_colour(js: JsRuntime):
    js.push(state_payload("every_level"))
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        assert js.named("levelColour", inherited) is None


def test_the_inherited_name_check_still_reads_a_real_level_colour(js: JsRuntime):
    """A lookup that answered nothing for every name would pass the check
    above while serving no colour at all."""
    payload = state_payload("every_level")
    js.push(payload)
    assert js.named("levelColour", "error") == payload["level_colors"]["error"]


def test_a_hostile_payload_still_draws_a_pane(browser: Browser):
    payload = state_payload("many")
    payload["timestamp_color"] = None
    payload["widget"]["maximum_height_px"] = None
    payload["document"]["lines"][0]["color"] = 7
    payload["document"]["lines"][1]["message"] = None
    parts = draw_spool(browser, payload)
    assert only(parts, "spool")
    assert len(at_path(parts, "spool/line")) == len(payload["document"]["lines"])
    assert at_path(parts, "spool/line/message")[1]["text"] == ""


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    """The module reaches Python the one way the page allows: the preload
    bridge, naming the method the surface registers."""
    js.bind_json("PAYLOAD", state_payload("one_info"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadSpool();")
    drain_events()
    assert js.json("window.CALLS") == [[nss.METHOD, "{}"]]
    assert js.json("acervatorSpool.isLoaded()") is True


def test_the_module_passes_a_caller_s_messages_to_the_surface(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("one_info"))
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", {"messages": [{"message": "venue down", "level": "error"}]})
    js.run("acervatorLoadSpool(JSON.parse(WANTED));")
    drain_events()
    called = js.json("window.CALLS")
    assert called[0][0] == nss.METHOD
    assert json.loads(called[0][1]) == {
        "messages": [{"message": "venue down", "level": "error"}]
    }


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    """Several panels on one page share one answer."""
    js.bind_json("PAYLOAD", state_payload("one_info"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadSpool(); acervatorLoadSpool(); acervatorLoadSpool();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    """A counter that never incremented would report one call however
    many were made."""
    js.bind_json("PAYLOAD", state_payload("one_info"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadSpool();")
    drain_events()
    js.run("acervatorSpool.forget(); acervatorLoadSpool();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadSpool();")
    drain_events()
    assert js.json("acervatorSpool.isLoaded()") is False
    assert js.json("acervatorSpool.loadError()") == "the preload bridge is not present"


def test_a_refused_ask_is_not_remembered(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("one_info"))
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadSpool();"
    )
    drain_events()
    assert js.json("acervatorSpool.isLoaded()") is False
    assert js.json("acervatorSpool.loadError()") == "the Python backend is not running"
    js.run("acervatorLoadSpool();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorSpool.isLoaded()") is True


def test_the_page_names_the_pane_module_among_its_assets():
    """The renderer loads the module that ships with the repo, not a
    second copy under ``desktop``."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("notification_spool.js")]
    assert len(named) == 1, f"the page names {len(named)} pane modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


def test_the_page_loads_the_pane_module_after_the_widgets_it_resolves_through():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    assert refs.index("../../src/gui/web/shared_widgets.js") < refs.index(
        "../../src/gui/web/notification_spool.js"
    )
