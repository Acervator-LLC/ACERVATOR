"""``privacy_dot.js`` against ``privacy_dot_surface.py``, run in QJSEngine
and drawn in QWebEngineView."""

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

from src.core.privacy_mask_registry import ALL_FIELD_IDS, get_privacy_mask_registry
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import header_strip_surface as hss
from src.gui.main_tabs import privacy_dot_surface as pds
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "privacy_dot.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
THEMES_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
WIDGETS_PATH = REPO_ROOT / "src" / "gui" / "web" / "shared_widgets.js"
HEADER_PATH = REPO_ROOT / "src" / "gui" / "web" / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body can write into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2

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

MONEY_FIELD_ID = "counter.scrummed"

#: Each state: the mask to set, then the parameters the bridge is given.
STATES = {
    "revealed": (False, {}),
    "masked": (True, {}),
    "clicked_from_revealed": (False, {"clicks": 1}),
    "clicked_twice": (False, {"clicks": 2}),
    "refreshed_while_masked": (True, {"refresh": True}),
    "another_field": (False, {"field_id": MONEY_FIELD_ID}),
}
STATE_NAMES = tuple(STATES)


def bridge_payload(**params: Any) -> dict:
    return json.loads(json.dumps(pds.view_model(params), ensure_ascii=True))


def state_payload(name: str) -> dict:
    """One named state, with the registry set before the surface is asked."""
    masked, params = STATES[name]
    field_id = params.get("field_id", pds.DEFAULT_FIELD_ID)
    get_privacy_mask_registry().set_masked(field_id, masked)
    return bridge_payload(**params)


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


@pytest.fixture()
def registry():
    """The privacy registry, with every field's prior mask put back after."""
    live = get_privacy_mask_registry()
    prior = {field: live.is_masked(field) for field in ALL_FIELD_IDS}
    for field in ALL_FIELD_IDS:
        live.set_masked(field, False)
    try:
        yield live
    finally:
        for field, was in prior.items():
            live.set_masked(field, was)


class JsRuntime(JsEngine):

    module_path = MODULE_PATH
    setter = "acervatorSetDot"

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

    def load_header(self) -> None:
        """Run the strip module, which owns the dot span this one draws."""
        self.run(HEADER_PATH.read_text(encoding="utf-8"))

    def named(self, api: str, name: str) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorDot." + api + "(JSON.parse(NAME))")

    def variable_for(self, value: Any) -> Any:
        self.bind_json("VALUE", value)
        return self.json("acervatorWidgets.variableFor(JSON.parse(VALUE))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime, registry) -> JsRuntime:
    """The module holding the surface's revealed dot."""
    assert registry is not None
    js.load_header()
    js.push(state_payload("revealed"))
    return js


#: Every field the surface publishes, and the module call answering for it.
MODULE_READERS = {
    "actions": "acervatorDot.actions()",
    "bus_topics": "acervatorDot.busTopics()",
    "call_names": "acervatorDot.callNames()",
    "calls": "acervatorDot.calls()",
    "cursor_shape": "acervatorDot.cursorShape()",
    "field_id": "acervatorDot.fieldId()",
    "flat": "acervatorDot.flat()",
    "focus_policy": "acervatorDot.focusPolicy()",
    "glyphs": "acervatorDot.glyphs()",
    "masked": "acervatorDot.masked()",
    "method": "acervatorDot.methodName()",
    "states": "acervatorDot.states()",
    "style_sheet": "acervatorDot.styleSheet()",
    "text": "acervatorDot.text()",
    "timer_delays_ms": "acervatorDot.timerDelaysMs()",
    "timers": "acervatorDot.timers()",
    "tooltip": "acervatorDot.tooltip()",
}


def unreachable_fields(payload: dict) -> list:
    return sorted(set(payload) - set(MODULE_READERS))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, registry, state: str
):
    """A field the module never carries is a value that stops at the bridge."""
    assert registry is not None
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


def test_the_whole_payload_check_names_a_field_only_the_surface_holds(registry):
    """The surface side of the comparison, with one extra name."""
    assert registry is not None
    payload = dict(bridge_payload())
    payload["only_on_the_surface"] = []
    assert unreachable_fields(payload) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_reads(registry):
    """The module side of the comparison, with one field taken away."""
    assert registry is not None
    payload = dict(bridge_payload())
    dropped = payload.pop("glyphs")
    assert dropped is not None
    assert sorted(set(MODULE_READERS) - set(payload)) == ["glyphs"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_counts_declared_and_held_fields_apart(
    js: JsRuntime, registry, state: str
):
    assert registry is not None
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["calls"] == len(payload["call_names"])
    assert report["held"]["calls"] == len(payload["calls"])


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(
    js: JsRuntime, registry
):
    """The counts above, driven with one field gone."""
    assert registry is not None
    payload = bridge_payload()
    del payload["glyphs"]
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(MODULE_READERS) - 1


def test_the_module_names_the_fields_the_surface_declares(loaded: JsRuntime):
    """The module's own field list, against the payload it was given."""
    assert sorted(loaded.json("acervatorDot.declaredFields()")) == sorted(
        bridge_payload()
    )


def test_a_click_lengthens_the_call_list_the_module_holds(js: JsRuntime, registry):
    assert registry is not None
    js.push(state_payload("revealed"))
    quiet = js.json("acervatorDot.calls()")
    js.push(state_payload("clicked_from_revealed"))
    after = js.json("acervatorDot.calls()")
    assert len(after) > len(quiet), f"{quiet} -> {after}"
    assert pds.CLICKED in after
    assert pds.CLICKED not in quiet


def declaration_values(sheet: str) -> set:
    """Every value written on the right of a colon in one Qt style sheet."""
    found = set()
    for part in re.split(r"[;{}]", str(sheet)):
        head, sep, tail = part.partition(":")
        if sep and head.strip():
            found.add(tail.strip())
    found.discard("")
    return found


def dot_values() -> set:
    found = {
        pds.REVEALED_GLYPH,
        pds.MASKED_GLYPH,
        pds.REVEALED_STATE,
        pds.MASKED_STATE,
        pds.DOT_STYLE,
    }
    found |= declaration_values(pds.DOT_STYLE)
    for field_id in (pds.DEFAULT_FIELD_ID, MONEY_FIELD_ID):
        for hidden in (True, False):
            found.add(pds.tooltip(field_id, hidden))
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

    for params in ({}, {"field_id": MONEY_FIELD_ID}, {"clicks": 0, "refresh": True}):
        walk(bridge_payload(**params))
    found |= dot_values()
    found.discard("")
    return found


SKIN_VALUES = dot_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every published string the module writes, each one a name.
NAMED_WORDS = sorted(
    {
        "actions",
        "bus_topics",
        "call_names",
        "calls",
        "clicked",
        "cursor_shape",
        "field_id",
        "flat",
        "focus_policy",
        "glyphs",
        "masked",
        "method",
        "privacy_dot.state",
        "revealed",
        "states",
        "style_sheet",
        "text",
        "timer_delays_ms",
        "timers",
        "tooltip",
    }
)

#: Every other string the module writes: CSS words, tags and fault words.
OWN_WORDS = sorted(
    {
        "",
        " span",
        ".",
        ":",
        "acervator-privacy-dot",
        "button",
        "clicks",
        "data-action",
        "data-cursor-shape",
        "data-flat",
        "data-focus-policy",
        "data-part",
        "dot",
        "dot-style",
        "function",
        "missing",
        "no-dot-span",
        "not-an-object",
        "null",
        "object",
        "pointer",
        "role",
        "span",
        "string",
        "style",
        "the preload bridge is not present",
        "unnamed-call",
        "use strict",
        "wrong-glyph",
        "wrong-tooltip",
        "wrong-type",
        "{",
        "}",
    }
)

#: The only number the module writes: one click per click of the dot.
OWN_NUMBERS = ["1"]


def test_the_module_writes_no_colour():
    """A colour typed here drifts from the surface the next time the
    dot's skin changes, and nothing reports the drift."""
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"privacy_dot.js holds colour literals: {found}"


def test_the_module_writes_only_the_numbers_it_declares():
    assert MODULE_LITERALS["numbers"] == OWN_NUMBERS, (
        "privacy_dot.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def sheet_numbers() -> set:
    """Every number the dot's own style sheet declares."""
    found: set = set()
    for value in declaration_values(pds.DOT_STYLE):
        found |= set(re.findall(r"\d+", value))
    return found


def test_no_number_the_module_writes_is_a_size_the_dot_paints():
    sizes = sheet_numbers()
    assert sizes, "the dot sheet declares no number; the check cannot report"
    assert not set(OWN_NUMBERS) & sizes, f"the module writes a size: {sizes}"


def test_no_string_in_the_module_equals_a_value_the_dot_paints():
    """A glyph, a tooltip, a colour or a whole Qt style sheet spelled out
    in the module."""
    written = sorted(set(MODULE_LITERALS["strings"]) & SKIN_VALUES)
    assert not written, f"privacy_dot.js spells out dot values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"privacy_dot.js spells out token values: {written}"


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


def test_every_named_word_is_a_name_and_not_a_value_the_dot_shows():
    """A word that is also a glyph, a colour or a tooltip does not belong
    on either list."""
    overlap = sorted((set(NAMED_WORDS) | set(OWN_WORDS)) & SKIN_VALUES)
    assert not overlap, f"these listed words are values the dot paints: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "privacy_dot.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


PLANTED_LINES = {
    "colour": 'var written = "' + str(dss.PRIMARY_BRIGHT) + '";',
    "hover_colour": 'var written = "' + str(dss.TEXT_MAX) + '";',
    "size": 'var written = "14px";',
    "number": "var written = 12;",
    "glyph": 'var written = "' + pds.MASKED_GLYPH + '";',
    "state_text": 'var written = "' + pds.MASKED_STATE + '";',
    "style_sheet": 'var written = "' + pds.DOT_STYLE + '";',
    "regex": "var written = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the checks above report on ``source``."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if [one for one in found["numbers"] if one not in OWN_NUMBERS]:
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
    loading it mid-scan still defines the dot module."""
    for kind, line in sorted(PLANTED_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetDot") == "function", kind


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
    js: JsRuntime, registry, state: str
):
    assert registry is not None
    payload = state_payload(state)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json("acervatorDot.kinds()")
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


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime, registry):
    """A payload with a text where a boolean belongs must read as exactly
    one difference."""
    assert registry is not None
    payload = bridge_payload()
    payload["masked"] = str(payload["masked"])
    js.push(payload)
    expected = python_kinds(bridge_payload())
    actual = js.json("acervatorDot.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["masked"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_glyph_and_the_tooltip_agree_with_the_surface(
    js: JsRuntime, registry, state: str
):
    assert registry is not None
    payload = state_payload(state)
    js.push(payload)
    assert js.json("acervatorDot.text()") == payload["text"]
    assert js.json("acervatorDot.tooltip()") == payload["tooltip"]
    assert js.json("acervatorDot.masked()") == payload["masked"]


def test_the_glyph_check_reads_a_different_glyph_in_the_other_state(
    js: JsRuntime, registry
):
    """Two real payloads, one masked and one not, must not read alike."""
    assert registry is not None
    js.push(state_payload("revealed"))
    shown = js.json("acervatorDot.text()")
    js.push(state_payload("masked"))
    assert js.json("acervatorDot.text()") != shown


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_names_no_fault_on_a_whole_payload(
    js: JsRuntime, registry, state: str
):
    """Every state the surface serves passes every check the module makes."""
    assert registry is not None
    js.load_header()
    report = js.push(state_payload(state))
    assert report["faults"] == [], f"{state}: {report['faults']}"


def test_the_module_reports_only_what_it_was_given(js: JsRuntime, registry):
    """Every value comes from the payload and none from the module."""
    assert registry is not None
    payload = bridge_payload()
    payload["glyphs"] = {"revealed": "given-revealed", "masked": "given-masked"}
    payload["text"] = "given-revealed"
    js.push(payload)
    assert js.json("acervatorDot.glyphs()") == payload["glyphs"]
    assert js.json("acervatorDot.text()") == "given-revealed"
    assert not set(payload["glyphs"].values()) & SKIN_VALUES


def carriers_of(value: Any) -> list:
    """Every non-alias design token carrying ``value``."""
    tokens = token_payload()
    aliases = tokens["alias_targets"]
    return sorted(
        name
        for name, held in tokens["tokens"].items()
        if str(held) == str(value) and name not in aliases
    )


DOT_COLOURS = sorted(
    {
        value
        for value in dot_values()
        if isinstance(value, str) and HEX_COLOUR.fullmatch(value)
    }
)


def test_every_colour_the_dot_paints_resolves_to_one_token(js: JsRuntime, registry):
    assert registry is not None
    js.load_tokens()
    js.load_widgets()
    assert DOT_COLOURS, "the dot paints no colour; the check cannot report"
    for colour in DOT_COLOURS:
        assert carriers_of(colour) == [
            js.variable_for(colour)
        ], f"{colour} is carried by {carriers_of(colour)}"


def test_the_dot_s_own_sizes_reach_no_token(js: JsRuntime, registry):
    assert registry is not None
    js.load_tokens()
    js.load_widgets()
    sizes = [one for one in declaration_values(pds.DOT_STYLE) if one.endswith("px")]
    assert sizes, "the dot sheet declares no size; the check cannot report"
    for size in sizes:
        assert js.variable_for(size) is None, f"{size} resolved to a token"


def test_a_value_no_token_carries_resolves_to_none(js: JsRuntime, registry):
    """A value off the table is painted from the surface rather than
    through a variable nothing answers."""
    assert registry is not None
    js.load_tokens()
    js.load_widgets()
    assert js.variable_for("no-token-carries-this") is None


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
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
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.js("typeof window.acervatorSetDot") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the dot module: readyState "
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


#: Every computed style property read off each drawn part.
STYLE_NAMES = [
    "color",
    "backgroundColor",
    "fontSize",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "cursor",
]

#: A Qt shorthand and the computed properties it settles into.
EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "background": ("backgroundColor",),
    "font-size": ("fontSize",),
    "color": ("color",),
}

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
    "        text: own, style: window.readStyle(el, names) });"
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


def draw_dot(browser: Browser, payload: dict) -> list:
    """Draw the dot into the page and read every named part back."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetDot(JSON.parse(window.PAYLOAD));"
        "acervatorDot.renderDot(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    """Read every drawn part again without redrawing."""
    return json.loads(browser.js(READ_PARTS))


def python_declarations(body: str) -> list:
    """Every ``property: value`` of one declaration body."""
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


def probe(browser: Browser, body: str) -> dict:
    """The computed values a bare element takes from the same declarations."""
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


def only(parts: list, path: str) -> dict:
    found = [one for one in parts if one["path"] == path]
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def colour_probe(browser: Browser, declared: str) -> str:
    """One declared colour, as the page computes it."""
    return browser.parsed(
        "window.probeStyle(" + json.dumps("color: " + declared) + ', ["color"])'
    )["color"]


def as_drawn(value: Any) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def changed_paths(before: list, after: list) -> set:
    """Every (path, property) whose computed value moved between reads."""
    assert len(before) == len(after), "the dot drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((one["path"], key))
    return moved


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser, registry):
    assert registry is not None
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorDot") == "object"
    assert browser.js("typeof window.acervatorSetDot") == "function"
    assert browser.js("typeof window.acervatorLoadDot") == "function"


def test_the_host_element_has_a_width_before_anything_is_drawn(
    browser: Browser, registry
):
    assert registry is not None
    browser.js(PAGE_HELPERS)
    assert browser.js(CLIENT_WIDTH) > 0


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_drawn_dot_shows_the_glyph_the_surface_published(
    browser: Browser, registry, state: str
):
    """What the operator reads off the screen, against what the surface
    produced, in every state."""
    assert registry is not None
    payload = state_payload(state)
    parts = draw_dot(browser, payload)
    span = only(parts, "dot/privacy-dot")
    assert span["text"] == payload["text"]
    assert span["attrs"]["title"] == payload["tooltip"]
    assert span["attrs"]["data-field-id"] == as_drawn(payload["field_id"])
    assert span["attrs"]["data-masked"] == as_drawn(payload["masked"])


def test_the_drawn_glyph_check_names_one_changed_glyph(browser: Browser, registry):
    """A read that returned the same glyph whatever was drawn would report
    agreement on a dot showing the wrong state."""
    assert registry is not None
    revealed = only(draw_dot(browser, state_payload("revealed")), "dot/privacy-dot")
    masked = only(draw_dot(browser, state_payload("masked")), "dot/privacy-dot")
    assert revealed["text"] != masked["text"]
    assert revealed["attrs"]["title"] != masked["attrs"]["title"]
    assert revealed["attrs"]["data-masked"] != masked["attrs"]["data-masked"]


def test_every_child_the_checks_read_carries_its_own_name(browser: Browser, registry):
    assert registry is not None
    parts = draw_dot(browser, state_payload("revealed"))
    assert [one["path"] for one in parts] == [
        "dot",
        "dot/dot-style",
        "dot/privacy-dot",
    ]


#: HOVER_RULE is narrowed to this class because the page carries others.
DOT_CLASS = "acervator-privacy-dot"

HOVER_RULE = (
    "(function () {"
    "  var found = [];"
    "  Array.prototype.slice.call(document.styleSheets).forEach(function (s) {"
    "    Array.prototype.slice.call(s.cssRules).forEach(function (r) {"
    "      if (r.selectorText && r.selectorText.indexOf('" + DOT_CLASS + "') >= 0) {"
    "        found.push({ selector: r.selectorText, color: r.style.color }); }"
    "    });"
    "  });"
    "  return JSON.stringify(found); })()"
)


def test_the_hover_scan_sees_a_rule_the_page_already_carries(browser: Browser):
    every = browser.parsed(
        "(function () {"
        "  var found = [];"
        "  Array.prototype.slice.call(document.styleSheets).forEach(function (s) {"
        "    Array.prototype.slice.call(s.cssRules).forEach(function (r) {"
        "      if (r.selectorText && r.selectorText.indexOf(':hover') >= 0) {"
        "        found.push(r.selectorText); } });"
        "  });"
        "  return JSON.stringify(found); })()"
    )
    assert every, "the page carries no hover rule at all"
    assert json.loads(browser.js(HOVER_RULE)) == []


def test_the_drawn_dot_paints_the_hover_colour_qt_paints(browser: Browser, registry):
    assert registry is not None
    payload = state_payload("revealed")
    draw_dot(browser, payload)
    rules = json.loads(browser.js(HOVER_RULE))
    assert len(rules) == 1, f"the page carries {len(rules)} hover rules: {rules}"
    assert rules[0]["color"] == colour_probe(browser, str(dss.TEXT_MAX))
    assert str(dss.TEXT_MAX) in payload["style_sheet"]


def test_the_hover_rule_names_the_colour_the_surface_published(
    browser: Browser, registry
):
    assert registry is not None
    payload = state_payload("revealed")
    payload["style_sheet"] = payload["style_sheet"].replace(
        str(dss.TEXT_MAX), str(dss.ERROR)
    )
    draw_dot(browser, payload)
    rules = json.loads(browser.js(HOVER_RULE))
    assert rules[0]["color"] == colour_probe(browser, str(dss.ERROR))
    assert rules[0]["color"] != colour_probe(browser, str(dss.TEXT_MAX))


def test_a_sheet_with_no_hover_block_writes_no_page_rule(browser: Browser, registry):
    """A sheet the surface publishes without a hover block leaves the page
    with no rule of the module's own."""
    assert registry is not None
    payload = state_payload("revealed")
    payload["style_sheet"] = base_body(payload["style_sheet"])
    parts = draw_dot(browser, payload)
    assert [one["path"] for one in parts] == ["dot", "dot/privacy-dot"]
    assert json.loads(browser.js(HOVER_RULE)) == []


def test_the_drawn_dot_is_the_button_the_operator_clicks(browser: Browser, registry):
    assert registry is not None
    host = only(draw_dot(browser, state_payload("revealed")), "dot")
    assert host["attrs"]["role"] == "button"
    assert host["style"]["cursor"] == "pointer"


def test_a_click_asks_the_surface_to_flip_the_mask(js: JsRuntime, registry):
    """The click sends the field and one click, which is what the Qt
    button does through the registry."""
    assert registry is not None
    js.load_header()
    js.push(state_payload("revealed"))
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorDot.clicked();")
    drain_events()
    called = js.json("window.CALLS")
    assert len(called) == 1, f"the click made {len(called)} calls"
    assert called[0][0] == pds.METHOD
    assert json.loads(called[0][1]) == {
        "field_id": pds.DEFAULT_FIELD_ID,
        "clicks": 1,
    }


def test_a_click_draws_the_state_the_surface_answered_with(js: JsRuntime, registry):
    assert registry is not None
    js.load_header()
    js.push(state_payload("revealed"))
    before = js.json("acervatorDot.text()")
    registry.set_masked(pds.DEFAULT_FIELD_ID, True)
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorDot.clicked();")
    drain_events()
    after = js.json("acervatorDot.text()")
    assert after != before, f"the click left the glyph at {after}"
    assert after == pds.MASKED_GLYPH


def test_a_click_with_no_bridge_reports_rather_than_raising(js: JsRuntime, registry):
    """A page opened without the preload script must say so, not lose the
    click without a word."""
    assert registry is not None
    js.load_header()
    js.push(state_payload("revealed"))
    js.run("acervatorDot.clicked();")
    drain_events()
    assert js.json("acervatorDot.loadError()") == "the preload bridge is not present"
    assert js.json("acervatorDot.text()") == state_payload("revealed")["text"]


def test_the_drawn_dot_matches_the_surface_s_own_style_sheet(
    browser: Browser, registry
):
    assert registry is not None
    payload = state_payload("revealed")
    parts = draw_dot(browser, payload)
    span = only(parts, "dot/privacy-dot")
    expected = probe(browser, base_body(payload["style_sheet"]))
    assert expected, "the probe took no value from the sheet"
    differing = {
        name: (value, span["style"].get(name))
        for name, value in expected.items()
        if span["style"].get(name) != value
    }
    assert not differing, (
        f"{len(differing)} of {len(expected)} declared values differ from "
        f"the surface's own: {differing}"
    )


def test_the_style_sheet_check_names_one_changed_colour(browser: Browser, registry):
    """A comparison that could not report would pass on a dot painted the
    wrong colour."""
    assert registry is not None
    payload = state_payload("revealed")
    original = payload["style_sheet"]
    payload["style_sheet"] = original.replace(str(dss.PRIMARY_BRIGHT), str(dss.ERROR))
    parts = draw_dot(browser, payload)
    span = only(parts, "dot/privacy-dot")
    expected = probe(browser, base_body(original))
    differing = sorted(
        name for name, value in expected.items() if span["style"].get(name) != value
    )
    assert differing == ["borderTopColor", "color"], f"the check named {differing}"


def test_the_drawn_dot_carries_the_qt_button_properties(browser: Browser, registry):
    assert registry is not None
    payload = state_payload("revealed")
    host = only(draw_dot(browser, payload), "dot")
    assert host["attrs"]["data-flat"] == as_drawn(payload["flat"])
    assert host["attrs"]["data-focus-policy"] == payload["focus_policy"]
    assert host["attrs"]["data-cursor-shape"] == payload["cursor_shape"]
    assert host["attrs"]["data-action"] == payload["actions"]["clicked"]
    assert host["style"]["cursor"] == "pointer"


def test_the_cursor_check_reads_the_default_cursor_for_another_shape(
    browser: Browser, registry
):
    assert registry is not None
    payload = state_payload("revealed")
    payload["cursor_shape"] = "ArrowCursor"
    host = only(draw_dot(browser, payload), "dot")
    assert host["style"]["cursor"] == "auto"


def test_the_module_names_only_the_cursor_shape_the_surface_publishes(
    loaded: JsRuntime,
):
    """The cursor map is written as object keys, which the literal scan
    cannot read, so it is named here instead."""
    assert loaded.json("acervatorDot.cursorNames()") == [pds.CURSOR_SHAPE]


def test_the_drawn_dot_follows_a_colour_token_and_nothing_else_moves(
    browser: Browser, registry
):
    assert registry is not None
    before = draw_dot(browser, state_payload("revealed"))
    browser.js(
        "document.documentElement.style.setProperty('--PRIMARY_BRIGHT', "
        + json.dumps(str(dss.ERROR))
        + ");"
    )
    moved = changed_paths(before, read_parts(browser))
    assert moved, "the token moved nothing at all"
    assert {key for _, key in moved} == {
        "color",
        "borderTopColor",
    }, f"an unset border colour is currentColor, so only these move: {moved}"
    assert {path for path, _ in moved} == {"dot/privacy-dot"}, f"moved {moved}"


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(
    browser: Browser, registry
):
    """A comparison that reported a difference on every read would pass
    the check above without proving anything."""
    assert registry is not None
    before = draw_dot(browser, state_payload("revealed"))
    assert changed_paths(before, read_parts(browser)) == set()


def test_a_token_the_dot_never_paints_moves_nothing(browser: Browser, registry):
    assert registry is not None
    before = draw_dot(browser, state_payload("revealed"))
    browser.js(
        "document.documentElement.style.setProperty('--STATE_MARKET', "
        + json.dumps(str(dss.ERROR))
        + ");"
    )
    assert changed_paths(before, read_parts(browser)) == set()


def test_the_glyph_span_comes_from_the_strip_module_and_not_a_copy(
    browser: Browser, registry
):
    assert registry is not None
    payload = state_payload("revealed")
    with_strip = [one["path"] for one in draw_dot(browser, payload)]
    assert with_strip == ["dot", "dot/dot-style", "dot/privacy-dot"]
    browser.js("window.acervatorHeader = undefined;")
    without_strip = [one["path"] for one in draw_dot(browser, payload)]
    assert without_strip == ["dot"], f"the page drew {without_strip}"


def test_the_module_names_a_page_that_never_loaded_the_strip(js: JsRuntime, registry):
    assert registry is not None
    report = js.push(state_payload("revealed"))
    assert {
        "where": None,
        "field": "text",
        "fault": "no-dot-span",
        "detail": None,
    } in report["faults"]


def test_the_missing_span_check_is_quiet_once_the_strip_is_loaded(
    js: JsRuntime, registry
):
    assert registry is not None
    js.load_header()
    report = js.push(state_payload("revealed"))
    assert [one for one in report["faults"] if one["fault"] == "no-dot-span"] == []


def money_texts(field_id: str) -> tuple:
    """The strip's own text for one field, masked and revealed."""
    live = get_privacy_mask_registry()
    stats = {"total_scrummed_usd": 987654.32}
    live.set_masked(field_id, False)
    shown = hss.view_model({"stats": stats})
    live.set_masked(field_id, True)
    hidden = hss.view_model({"stats": stats})
    cards = {card["field_id"]: card["text"] for card in shown["counters"]}
    masked_cards = {card["field_id"]: card["text"] for card in hidden["counters"]}
    return cards[field_id], masked_cards[field_id]


def leaked(parts: list, secret: str) -> list:
    """Every attribute or text node of the drawn dot carrying ``secret``."""
    found = []
    for one in parts:
        for name, value in one["attrs"].items():
            if secret in str(value):
                found.append(one["path"] + "@" + name)
        if secret in str(one["text"]):
            found.append(one["path"] + "#text")
    return sorted(found)


def test_no_amount_reaches_the_page_while_the_field_is_masked(
    browser: Browser, registry
):
    assert registry is not None
    shown, hidden = money_texts(MONEY_FIELD_ID)
    assert shown != hidden, "the strip masks nothing; the check cannot report"
    payload = bridge_payload(field_id=MONEY_FIELD_ID)
    assert payload["masked"] is True
    parts = draw_dot(browser, payload)
    assert leaked(parts, shown) == [], f"the dot carries the amount {shown}"


def test_the_leak_scan_names_an_amount_written_into_the_page(
    browser: Browser, registry
):
    assert registry is not None
    shown, _ = money_texts(MONEY_FIELD_ID)
    payload = bridge_payload(field_id=MONEY_FIELD_ID)
    payload["field_id"] = shown
    payload["tooltip"] = shown
    parts = draw_dot(browser, payload)
    assert leaked(parts, shown) == [
        "dot/privacy-dot@data-field-id",
        "dot/privacy-dot@title",
    ], f"the scan named {leaked(parts, shown)}"


@pytest.mark.parametrize("amount", [0.0, -1.5, 987654.32, 1e24])
def test_the_masked_dot_draws_the_same_glyph_whatever_the_amount_is(
    js: JsRuntime, registry, amount: float
):
    """The dot's payload carries no amount at all, so a hostile figure
    cannot change what the operator sees."""
    assert registry is not None
    registry.set_masked(MONEY_FIELD_ID, True)
    hss.view_model({"stats": {"total_scrummed_usd": amount}})
    payload = bridge_payload(field_id=MONEY_FIELD_ID)
    js.push(payload)
    assert js.json("acervatorDot.text()") == pds.MASKED_GLYPH
    assert str(amount) not in json.dumps(payload)


HOSTILE_VALUES = {
    "a true flag": True,
    "a number where text belongs": 7,
    "text where a number belongs": "1234.5",
    "a very large integer": 10**24,
    "two hundred characters": "x" * 200,
    "markup": "<script>alert(1)</script>",
    "nothing at all": None,
}

#: UNCARRIABLE holds the two floats `json.dumps` writes bare.
UNCARRIABLE = {"not a number": float("nan"), "an infinity": float("inf")}


@pytest.mark.parametrize("case", sorted(HOSTILE_VALUES))
def test_a_hostile_field_id_reaches_the_module_unchanged(
    js: JsRuntime, registry, case: str
):
    assert registry is not None
    js.push(bridge_payload(field_id=HOSTILE_VALUES[case]))
    assert js.json("acervatorDot.fieldId() === JSON.parse(PAYLOAD).field_id") is True


def test_the_field_id_check_names_a_changed_name(js: JsRuntime, registry):
    assert registry is not None
    js.push(bridge_payload())
    js.bind_json("PAYLOAD", bridge_payload(field_id=MONEY_FIELD_ID))
    assert js.json("acervatorDot.fieldId() === JSON.parse(PAYLOAD).field_id") is False


@pytest.mark.parametrize("case", sorted(HOSTILE_VALUES))
def test_a_hostile_glyph_is_drawn_as_the_text_it_is(
    browser: Browser, registry, case: str
):
    assert registry is not None
    payload = state_payload("revealed")
    payload["text"] = HOSTILE_VALUES[case]
    parts = draw_dot(browser, payload)
    span = only(parts, "dot/privacy-dot")
    wanted = browser.js(
        "(function () { var v = JSON.parse(window.PAYLOAD).text;"
        " return v === null ? '' : String(v); })()"
    )
    assert span["text"] == wanted
    assert browser.js("window.HOST.getElementsByTagName('script').length") == 0


@pytest.mark.parametrize("case", sorted(UNCARRIABLE))
def test_a_payload_the_bridge_cannot_write_never_reaches_the_module(
    js: JsRuntime, registry, case: str
):
    assert registry is not None
    js.push(state_payload("revealed"))
    before = js.json("acervatorDot.fieldId()")
    payload = pds.view_model({"field_id": UNCARRIABLE[case]})
    written = json.dumps(payload)
    assert case.split()[-1].lower() in written.lower() or "NaN" in written
    js.bind_json("BROKEN", payload)
    refused = js.json(
        "(function () { try { JSON.parse(BROKEN); return null; }"
        " catch (e) { return e.name; } })()"
    )
    assert refused is not None, "JSON.parse accepted the frame"
    assert js.json("acervatorDot.fieldId()") == before


def test_the_uncarriable_check_accepts_a_frame_the_bridge_can_write(
    js: JsRuntime, registry
):
    assert registry is not None
    js.bind_json("WHOLE", bridge_payload())
    refused = js.json(
        "(function () { try { JSON.parse(WHOLE); return null; }"
        " catch (e) { return e.name; } })()"
    )
    assert refused is None


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_field_the_payload_omits_is_named_as_missing(
    js: JsRuntime, registry, field: str
):
    """The surface sent a payload with one field gone."""
    assert registry is not None
    payload = bridge_payload()
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
def test_a_field_carrying_null_is_named(js: JsRuntime, registry, field: str):
    """A null is reported, not swapped for a value of the module's own."""
    assert registry is not None
    payload = bridge_payload()
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime, registry):
    assert registry is not None
    report = js.push(bridge_payload())
    kinds = [one["fault"] for one in report["faults"]]
    assert "missing" not in kinds
    assert "null" not in kinds


def test_a_glyph_that_is_a_number_is_named_against_its_own_default(
    js: JsRuntime, registry
):
    assert registry is not None
    payload = bridge_payload()
    payload["text"] = 7
    report = js.push(payload)
    assert {
        "where": None,
        "field": "text",
        "fault": "wrong-type",
        "detail": "number",
    } in report["faults"]
    assert js.json("acervatorDot.text()") == 7


def test_a_tooltip_that_is_a_number_is_named_against_its_own_default(
    js: JsRuntime, registry
):
    assert registry is not None
    payload = bridge_payload()
    payload["tooltip"] = 7
    report = js.push(payload)
    assert {
        "where": None,
        "field": "tooltip",
        "fault": "wrong-type",
        "detail": "number",
    } in report["faults"]


def test_a_style_sheet_that_is_a_number_raises_no_wrong_type(js: JsRuntime, registry):
    assert registry is not None
    payload = bridge_payload()
    payload["style_sheet"] = 7
    js.push(payload)
    assert js.json("acervatorDot.styleSheet()") == 7
    assert js.json("acervatorDot.kinds()")["style_sheet"] == "number"
    named = [
        one["field"]
        for one in js.json("acervatorDot.faults()")
        if one["fault"] == "wrong-type"
    ]
    assert "style_sheet" not in named


def test_the_wrong_type_check_is_quiet_on_a_whole_payload(js: JsRuntime, registry):
    assert registry is not None
    report = js.push(bridge_payload())
    assert "wrong-type" not in [one["fault"] for one in report["faults"]]


def test_a_glyph_that_disagrees_with_the_mask_is_named(js: JsRuntime, registry):
    """The one fault that matters most: a masked field painting the
    revealed glyph would show a hidden amount as shown."""
    assert registry is not None
    payload = bridge_payload()
    payload["masked"] = True
    report = js.push(payload)
    assert {
        "where": None,
        "field": "text",
        "fault": "wrong-glyph",
        "detail": "string",
    } in report["faults"]
    assert js.json("acervatorDot.text()") == payload["text"]


def test_a_tooltip_that_names_the_other_state_is_named(js: JsRuntime, registry):
    """A tooltip reading REVEALED under a masked dot tells the operator
    the wrong thing about his own money."""
    assert registry is not None
    payload = bridge_payload()
    payload["masked"] = True
    payload["text"] = payload["glyphs"]["masked"]
    report = js.push(payload)
    assert {
        "where": None,
        "field": "tooltip",
        "fault": "wrong-tooltip",
        "detail": payload["tooltip"],
    } in report["faults"]


def test_the_glyph_and_tooltip_checks_are_quiet_on_both_shipped_states(
    js: JsRuntime, registry
):
    """The other side of the two checks above, in both mask states."""
    assert registry is not None
    for state in ("revealed", "masked"):
        report = js.push(state_payload(state))
        kinds = [one["fault"] for one in report["faults"]]
        assert "wrong-glyph" not in kinds, state
        assert "wrong-tooltip" not in kinds, state


def test_a_call_the_surface_never_declared_is_named(js: JsRuntime, registry):
    """A branch the dot recorded that ``call_names`` does not list is a
    path nothing on the page can explain."""
    assert registry is not None
    payload = bridge_payload()
    payload["calls"].append("undeclared_branch")
    report = js.push(payload)
    assert {
        "where": "calls",
        "field": "undeclared_branch",
        "fault": "unnamed-call",
        "detail": None,
    } in report["faults"]


def test_the_call_check_is_quiet_on_every_shipped_state(js: JsRuntime, registry):
    assert registry is not None
    for state in STATE_NAMES:
        report = js.push(state_payload(state))
        named = [one for one in report["faults"] if one["fault"] == "unnamed-call"]
        assert named == [], f"{state}: {named}"


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(
    js: JsRuntime, registry
):
    """A bridge answering with a string or a number draws nothing."""
    assert registry is not None
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorDot.isLoaded()") is False
        assert js.json("acervatorDot.glyphs()") == {}
        assert report["declared"] is None
        assert report["held"] is None
        assert [one["fault"] for one in report["faults"]] == ["not-an-object"]


def test_a_name_the_payload_never_carried_is_not_a_glyph(js: JsRuntime, registry):
    assert registry is not None
    js.push(bridge_payload())
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        assert js.named("glyph", inherited) is None
        assert js.named("state", inherited) is None
        assert js.named("action", inherited) is None


def test_the_inherited_name_check_still_reads_a_real_glyph(js: JsRuntime, registry):
    """A lookup that answered nothing for every name would pass the check
    above while serving no glyph at all."""
    assert registry is not None
    payload = bridge_payload()
    js.push(payload)
    assert js.named("glyph", "masked") == payload["glyphs"]["masked"]
    assert js.named("state", "revealed") == payload["states"]["revealed"]
    assert js.named("action", "clicked") == payload["actions"]["clicked"]


def test_a_hostile_payload_still_draws_a_dot(browser: Browser, registry):
    assert registry is not None
    payload = state_payload("revealed")
    payload["text"] = 7
    payload["tooltip"] = None
    payload["style_sheet"] = 7
    payload["cursor_shape"] = None
    parts = draw_dot(browser, payload)
    assert only(parts, "dot")
    assert only(parts, "dot/privacy-dot")["text"] == "7"


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime, registry):
    """The module reaches Python the one way the page allows: the preload
    bridge, naming the method the surface registers."""
    assert registry is not None
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadDot();")
    drain_events()
    assert js.json("window.CALLS") == [[pds.METHOD, "{}"]]
    assert js.json("acervatorDot.isLoaded()") is True


def test_the_module_passes_a_caller_s_parameters_to_the_surface(
    js: JsRuntime, registry
):
    """A caller that wants another field's dot sends the name the surface
    reads."""
    assert registry is not None
    js.bind_json("PAYLOAD", bridge_payload(field_id=MONEY_FIELD_ID))
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", {"field_id": MONEY_FIELD_ID})
    js.run("acervatorLoadDot(JSON.parse(WANTED));")
    drain_events()
    assert js.json("window.CALLS") == [
        [pds.METHOD, '{"field_id":"' + MONEY_FIELD_ID + '"}']
    ]
    assert js.json("acervatorDot.fieldId()") == MONEY_FIELD_ID


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime, registry):
    """Several dots on one page share one answer."""
    assert registry is not None
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadDot(); acervatorLoadDot(); acervatorLoadDot();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime, registry):
    """A counter that never incremented would report one call however
    many were made."""
    assert registry is not None
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadDot();")
    drain_events()
    js.run("acervatorDot.forget(); acervatorLoadDot();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(
    js: JsRuntime, registry
):
    """A page opened without the preload script must say so, not draw a
    dot with no state behind it."""
    assert registry is not None
    js.run("acervatorLoadDot();")
    drain_events()
    assert js.json("acervatorDot.isLoaded()") is False
    assert js.json("acervatorDot.loadError()") == "the preload bridge is not present"


def test_a_refused_ask_is_not_remembered(js: JsRuntime, registry):
    assert registry is not None
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadDot();"
    )
    drain_events()
    assert js.json("acervatorDot.isLoaded()") is False
    assert js.json("acervatorDot.loadError()") == "the Python backend is not running"
    js.run("acervatorLoadDot();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorDot.isLoaded()") is True


def test_the_page_names_the_dot_module_among_its_assets():
    """The renderer loads the module that ships with the repo, not a
    second copy under ``desktop``."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("privacy_dot.js")]
    assert len(named) == 1, f"the page names {len(named)} dot modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


def test_the_page_loads_the_dot_module_after_the_strip_it_draws_with():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    assert refs.index("../../src/gui/web/header_strip.js") < refs.index(
        "../../src/gui/web/privacy_dot.js"
    )
