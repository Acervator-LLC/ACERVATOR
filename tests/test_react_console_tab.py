"""The React Console tab, against console_tab_surface.py."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import console_tab_surface as surface
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import swap_module

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "console_tab.js"
TOKENS_PATH = WEB / "design_tokens.js"
THEMES_PATH = WEB / "theme_engine.js"
WIDGETS_PATH = WEB / "shared_widgets.js"
HEADER_PATH = WEB / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
EVENT_DRAIN_ROUNDS = 20
SETTLE_MS = 500
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2

#: A view never shown reads clientWidth as 0, so the host is sized.
HOST_WIDTH_PX = 600
HOST_HEIGHT_PX = 400

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

HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")

RECORDS = [
    {
        "name": "acervator.trading",
        "level": "INFO",
        "message": "scrum filled",
        "created": 1.0,
    },
    {
        "name": "acervator.risk",
        "level": "WARNING",
        "message": "fold armed",
        "created": 2.0,
    },
    {
        "name": "acervator.exchange",
        "level": "ERROR",
        "message": "order refused",
        "created": 3.0,
    },
]
SIGNAL_LINES = ["rsi · 30 · 28.4", "bb_pos · 0.20 · 0.15"]

#: 200 characters with no space, the case a wrapping pane cannot break.
LONG_WORD = "z" * 200
LONG_RECORD = {"name": "a.b", "level": "INFO", "message": LONG_WORD, "created": 4.0}
MARKUP_WORD = "<script>window.MARKUP_RAN = true;</script>"
NEWLINE_RECORD = {
    "name": "a.b",
    "level": "INFO",
    "message": "first\nsecond",
    "created": 5.0,
}

LEDGER_COUNTS = {
    "seq": 11,
    "drain_ticks": 22,
    "read": 33,
    "rendered": 44,
    "slice_dropped": 55,
    "markers": 66,
    "health_ticks_seen": 77,
}

CAPPED_BLOCKS = 2


def bridge_payload(*steps: dict, max_blocks: int = None, ledger: dict = None) -> dict:
    """One payload from the surface, with each step driving the same two panes in order."""
    cap = surface.PANE_MAX_BLOCKS if max_blocks is None else max_blocks
    log_pane = surface.ConsolePane(cap)
    signal_pane = surface.ConsolePane(cap)
    counters = surface.SignalLedger()
    for name, value in (ledger or {}).items():
        setattr(counters, name, value)
    model = None
    for step in steps or ({},):
        model = surface.build_view_model(log_pane, signal_pane, counters, **step)
    return json.loads(json.dumps(model, ensure_ascii=True))


STATES = {
    "empty": {},
    "filled": {"steps": ({"records": RECORDS, "signal_lines": SIGNAL_LINES},)},
    "cleared": {"steps": ({"records": RECORDS}, {"clear_log": True})},
    "capped": {"max_blocks": CAPPED_BLOCKS, "steps": ({"records": RECORDS},)},
    "long_line": {"steps": ({"records": [LONG_RECORD], "signal_lines": [LONG_WORD]},)},
    "counted": {"ledger": LEDGER_COUNTS, "steps": ({"records": RECORDS[:1]},)},
}
STATE_NAMES = tuple(STATES)


def state_payload(name: str) -> dict:
    case = STATES[name]
    return bridge_payload(
        *case.get("steps", ()),
        max_blocks=case.get("max_blocks"),
        ledger=case.get("ledger"),
    )


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


def drain_events() -> None:
    """Turn the event loop so a queued promise continuation runs."""
    from PySide6.QtCore import QCoreApplication, QEventLoop

    for _ in range(EVENT_DRAIN_ROUNDS):
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)


class JsRuntime:
    """A QJSEngine holding ``console_tab.js`` and a ``window`` global."""

    def __init__(self, engine: Any, source: str) -> None:
        self._engine = engine
        engine.evaluate("var window = this;")
        loaded = engine.evaluate(source, MODULE_PATH.name)
        if loaded.isError():
            raise AssertionError(
                MODULE_PATH.name + " did not run: " + loaded.toString()
            )

    def engine_of(self) -> Any:
        return type(self._engine)()

    def run(self, script: str) -> Any:
        result = self._engine.evaluate(script)
        assert not result.isError(), script[:120] + " -> " + result.toString()
        return result

    def raised(self, script: str) -> str:
        """The engine's error for ``script``, or an empty string."""
        result = self._engine.evaluate(script)
        return result.toString() if result.isError() else ""

    def json(self, expression: str) -> Any:
        text = self.run("JSON.stringify(" + expression + ")").toString()
        return None if text == "undefined" else json.loads(text)

    def bind_json(self, name: str, value: Any) -> None:
        """Bind value as JSON text that every caller parses back."""
        self._engine.globalObject().setProperty(name, json.dumps(value))

    def push(self, payload: Any) -> dict:
        self.bind_json("PAYLOAD", payload)
        return self.json("acervatorSetConsole(JSON.parse(PAYLOAD))")

    def load_tokens(self) -> None:
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_themes(self) -> None:
        self.run(THEMES_PATH.read_text(encoding="utf-8"))
        self.bind_json("THEMES", theme_payload())
        self.run("acervatorSetThemes(JSON.parse(THEMES));")

    def load_widgets(self) -> None:
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def load_header(self) -> None:
        self.run(HEADER_PATH.read_text(encoding="utf-8"))

    def named(self, method: str, name: str) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorConsole." + method + "(JSON.parse(NAME))")

    def style_of(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorConsole.styleOf(JSON.parse(SHEET))")

    def declarations(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorConsole.declarations(JSON.parse(SHEET))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    qtqml = pytest.importorskip("PySide6.QtQml")
    assert qapp is not None
    return JsRuntime(qtqml.QJSEngine(), MODULE_SOURCE)


@pytest.fixture()
def skinned(js: JsRuntime) -> JsRuntime:
    """The module with the four modules it paints through already run."""
    js.load_tokens()
    js.load_themes()
    js.load_widgets()
    js.load_header()
    return js


@pytest.fixture()
def loaded(skinned: JsRuntime) -> JsRuntime:
    skinned.push(bridge_payload())
    return skinned


MODULE_READERS = {
    "actions": "acervatorConsole.actions()",
    "clear_button": "acervatorConsole.clearButton()",
    "container": "acervatorConsole.container()",
    "control_bar": "acervatorConsole.controlBar()",
    "control_bar_order": "acervatorConsole.controlBarOrder()",
    "ledger": "acervatorConsole.ledger()",
    "log_handler": "acervatorConsole.logHandler()",
    "log_pane": "acervatorConsole.logPane()",
    "pause_button": "acervatorConsole.pauseButton()",
    "pause_indicator": "acervatorConsole.pauseIndicator()",
    "signal_box": "acervatorConsole.signalBox()",
    "signal_header": "acervatorConsole.signalHeader()",
    "signal_pane": "acervatorConsole.signalPane()",
    "splitter": "acervatorConsole.splitter()",
    "tab_title": "acervatorConsole.tabTitle()",
    "timers": "acervatorConsole.timers()",
}


def unreachable_fields(payload: dict) -> list:
    return sorted(set(payload) - set(MODULE_READERS))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    """A field with no answer is a value that stops at the bridge."""
    payload = state_payload(state)
    js.push(payload)
    missing = unreachable_fields(payload)
    assert not missing, f"{len(missing)} published fields have no answer: {missing}"
    extra = sorted(set(MODULE_READERS) - set(payload))
    assert not extra, f"the module answers for fields the surface has none of: {extra}"
    differing = {
        field: (payload[field], js.json(expression))
        for field, expression in MODULE_READERS.items()
        if js.json(expression) != payload[field]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields differ: "
        f"{sorted(differing)}"
    )
    assert len(MODULE_READERS) == len(payload)


def test_the_whole_payload_check_names_a_field_only_the_surface_holds():
    payload = dict(bridge_payload())
    payload["only_on_the_surface"] = []
    assert unreachable_fields(payload) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for():
    payload = dict(bridge_payload())
    dropped = payload.pop("ledger")
    assert dropped is not None
    assert sorted(set(MODULE_READERS) - set(payload)) == ["ledger"]


def test_the_whole_payload_check_names_one_changed_value(js: JsRuntime):
    payload = bridge_payload()
    payload["tab_title"] += "!"
    js.push(payload)
    original = bridge_payload()
    differing = sorted(
        field
        for field, expression in MODULE_READERS.items()
        if js.json(expression) != original[field]
    )
    assert differing == ["tab_title"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    """C72 counts fields, control_bar_order, splitter children and blocks twice."""
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["controls"] == len(payload["control_bar_order"])
    assert report["held"]["controls"] == len(payload["control_bar_order"])
    assert report["declared"]["panes"] == len(payload["splitter"]["children"])
    assert report["held"]["panes"] == len(payload["splitter"]["children"])
    assert report["declared"]["log_blocks"] == payload["log_pane"]["block_count"]
    assert report["held"]["log_blocks"] == len(payload["log_pane"]["blocks"])
    assert report["declared"]["signal_blocks"] == payload["signal_pane"]["block_count"]
    assert report["held"]["signal_blocks"] == len(payload["signal_pane"]["blocks"])


def test_an_empty_pane_declares_one_block_and_holds_none(js: JsRuntime):
    """The Qt pane counts an empty document as one block, and the module holds zero beside it."""
    report = js.push(state_payload("empty"))
    assert report["declared"]["log_blocks"] == 1
    assert report["held"]["log_blocks"] == 0


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = bridge_payload()
    del payload["ledger"]
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(MODULE_READERS) - 1


def test_the_module_names_the_fields_the_surface_declares(loaded: JsRuntime):
    assert sorted(loaded.json("acervatorConsole.declaredFields()")) == sorted(
        bridge_payload()
    )


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_holds_every_log_block_the_surface_published(
    js: JsRuntime, state: str
):
    """A line the surface produced that the module drops is a log line
    the operator would never read."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json("acervatorConsole.logBlocks()") == payload["log_pane"]["blocks"]
    assert (
        js.json("acervatorConsole.signalBlocks()") == payload["signal_pane"]["blocks"]
    )


def test_the_log_block_check_names_a_dropped_line(js: JsRuntime):
    payload = state_payload("filled")
    dropped = payload["log_pane"]["blocks"].pop()
    js.push(payload)
    held = js.json("acervatorConsole.logBlocks()")
    original = state_payload("filled")["log_pane"]["blocks"]
    assert sorted(set(original) - set(held)) == [dropped]


def test_the_cap_drops_the_oldest_blocks_and_keeps_the_newest(js: JsRuntime):
    """C8 is why the newest blocks are named and not merely counted."""
    payload = state_payload("capped")
    js.push(payload)
    held = js.json("acervatorConsole.logBlocks()")
    every = state_payload("filled")["log_pane"]["blocks"]
    assert len(held) == CAPPED_BLOCKS
    assert held == every[-CAPPED_BLOCKS:], f"the cap kept {held}"


def js_literals(source: str) -> dict:
    """Every string literal, number literal and stray slash in source."""
    quotes = "'\"`"
    digits = "0123456789"
    ident = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$")
    numeric = set(digits + ".xXoObBeE_abcdefABCDEF")
    strings: list = []
    numbers: list = []
    slashes: list = []
    index = 0
    end = len(source)
    while index < end:
        char = source[index]
        if char == "/" and source.startswith("//", index):
            stop = source.find("\n", index)
            index = end if stop < 0 else stop + 1
            continue
        if char == "/" and source.startswith("/*", index):
            stop = source.find("*/", index + 2)
            index = end if stop < 0 else stop + 2
            continue
        if char == "/":
            slashes.append(source[max(index - 20, 0) : index + 20])
            index += 1
            continue
        if char in quotes:
            cursor = index + 1
            body: list = []
            while cursor < end and source[cursor] != char:
                if source[cursor] == "\\":
                    body.append(source[cursor : cursor + 2])
                    cursor += 2
                    continue
                body.append(source[cursor])
                cursor += 1
            strings.append("".join(body))
            index = cursor + 1
            continue
        if char in digits and (index == 0 or source[index - 1] not in ident):
            cursor = index
            while cursor < end and source[cursor] in numeric:
                cursor += 1
            numbers.append(source[index:cursor])
            index = cursor
            continue
        index += 1
    return {"strings": strings, "numbers": numbers, "slashes": slashes}


def as_css(value: Any) -> set:
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


#: The payload paths whose values skin or fill the tab.
SKIN_FIELDS = (
    "style_sheet",
    "text",
    "background",
    "color",
    "border",
    "border_top",
    "border_bottom",
    "hover_background",
    "checked_background",
    "checked_color",
    "checked_border_color",
    "font_family",
    "tab_title",
    "format",
    "datefmt",
)
SIZE_FIELDS = (
    "margins_px",
    "spacing_px",
    "child_stretch",
    "padding_px",
    "stretch",
    "max_blocks",
    "block_count",
    "font_size_px",
    "font_point_size",
    "interval_ms",
    "handler_level",
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
    """Every value right of a colon in one sheet's base_body blocks."""
    found = set()
    for part in re.split(r"[;{}]", base_body(sheet)):
        head, sep, tail = part.partition(":")
        if sep and head.strip():
            found.add(tail.strip())
    found.discard("")
    return found


def console_values() -> set:
    """Every colour, size, text and style sheet the tab paints."""
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
        walk(state_payload(name))
    found.discard("")
    return found


def token_values() -> set:
    found: set = set()
    for value in dss.TOKENS.values():
        found |= as_css(value)
    for theme in tes.THEMES.values():
        for value in theme.values():
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


SKIN_VALUES = console_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every published string the module writes as a literal, each one a name.
NAMED_WORDS = sorted(
    {
        "actions",
        "background",
        "block_count",
        "blocks",
        "border",
        "border_bottom",
        "border_top",
        "center_on_scroll",
        "checkable",
        "checked",
        "checked_background",
        "checked_border_color",
        "checked_color",
        "child_stretch",
        "children",
        "clear_button",
        "clear_button.clicked",
        "color",
        "container",
        "control_bar",
        "control_bar_order",
        "datefmt",
        "font_family",
        "font_point_size",
        "font_size_px",
        "format",
        "handler_level",
        "hover_background",
        "interval_ms",
        "is_empty",
        "ledger",
        "log_handler",
        "log_pane",
        "loggers",
        "margins_px",
        "max_blocks",
        "orientation",
        "padding_px",
        "pause_button",
        "pause_button.clicked",
        "pause_indicator",
        "read_only",
        "running",
        "signal_box",
        "signal_header",
        "signal_pane",
        "block_colors",
        "spacing_px",
        "splitter",
        "stretch",
        "style_sheet",
        "tab_title",
        "text",
        "timers",
        "vertical",
        "wrap",
    }
)


def test_the_module_writes_no_number():
    """A numeric literal typed here is a second source for a value the surface owns."""
    assert not MODULE_LITERALS[
        "numbers"
    ], f"console_tab.js holds numeric literals: {MODULE_LITERALS['numbers']}"


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"console_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & SKIN_VALUES)
    assert not written, f"console_tab.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"console_tab.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    """Every published string the module holds is listed rather than skipped."""
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert written == NAMED_WORDS, (
        f"the module names {sorted(set(written) - set(NAMED_WORDS))} more and "
        f"{sorted(set(NAMED_WORDS) - set(written))} fewer published strings "
        "than the list allows"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_tab_shows():
    overlap = sorted(set(NAMED_WORDS) & SKIN_VALUES)
    assert not overlap, f"these named words are values the tab paints: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "console_tab.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


PLANTED_LINES = {
    "colour": 'var planted = "#00ffcc";',
    "pane_colour": 'var planted = "' + str(dss.TEXT_LOG_MINT) + '";',
    "size": 'var planted = "' + str(surface.CONTROL_FONT_PX) + 'px";',
    "margin": "var planted = " + str(surface.CONTROL_BAR["margins_px"][0]) + ";",
    "number": "var planted = 12;",
    "cap": "var planted = " + str(surface.PANE_MAX_BLOCKS) + ";",
    "button_text": 'var planted = "' + surface.CLEAR_BUTTON_TEXT + '";',
    "header_text": 'var planted = "' + surface.SIGNAL_HEADER_TEXT + '";',
    "style_sheet": 'var planted = "' + surface.SIGNAL_PANE_STYLE + '";',
    "log_format": 'var planted = "' + surface.LOG_FORMAT + '";',
    "font": 'var planted = "' + surface.PANE_FONT_FAMILY + '";',
    "token_value": 'var planted = "' + str(dss.PRIMARY) + '";',
    "regex": "var planted = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
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
def test_the_literal_scan_names_a_planted_line(kind: str):
    caught = caught_by_scan(PLANTED_LINES[kind])
    assert caught, f"the scan reported nothing on the planted {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_planted_literal_is_caught_in_the_module_file_itself():
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
            assert after == before, f"the file was not restored after the {kind} plant"
    finally:
        swap_module(MODULE_PATH, original)
    quiet = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not quiet, f"the scan reported nothing on these plants in the file: {quiet}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_planted_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    for kind, line in sorted(PLANTED_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetConsole") == "function", kind


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
    """A value that changes shape in transit reads correct and paints
    wrong: a number where a colour belongs paints nothing."""
    payload = state_payload(state)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json("acervatorConsole.kinds()")
    differing = {
        path: (kind, actual.get(path))
        for path, kind in expected.items()
        if actual.get(path) != kind
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(expected)} values changed type: "
        f"{sorted(differing)}"
    )
    assert sorted(actual) == sorted(expected)


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime):
    payload = bridge_payload()
    payload["log_pane"]["max_blocks"] = str(payload["log_pane"]["max_blocks"])
    js.push(payload)
    expected = python_kinds(bridge_payload())
    actual = js.json("acervatorConsole.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["log_pane.max_blocks"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_timer_agrees_with_the_surface(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for name, expected in payload["timers"].items():
        assert js.named("timer", name) == expected, f"{state}/{name}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_ledger_counter_agrees_with_the_surface(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for name, expected in payload["ledger"].items():
        assert js.named("counter", name) == expected, f"{state}/{name}"


def test_the_ledger_check_reads_a_different_number_for_a_different_count(js: JsRuntime):
    """The counted state and the empty state must not read alike."""
    js.push(state_payload("counted"))
    counted = js.json("acervatorConsole.ledger()")
    js.push(state_payload("empty"))
    assert counted != js.json("acervatorConsole.ledger()")
    assert counted == LEDGER_COUNTS


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_action_agrees_with_the_surface(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for name, expected in payload["actions"].items():
        assert js.named("action", name) == expected, f"{state}/{name}"


def test_the_module_reports_only_what_it_was_given(js: JsRuntime):
    """A payload of texts the surface never held comes back unchanged."""
    payload = bridge_payload()
    payload["tab_title"] = "given-title"
    payload["ledger"] = {"given": 7}
    js.push(payload)
    assert js.json("acervatorConsole.tabTitle()") == "given-title"
    assert js.json("acervatorConsole.ledger()") == {"given": 7}


SKINNED_FIELDS = (
    "control_bar",
    "pause_button",
    "pause_indicator",
    "clear_button",
    "signal_header",
    "log_pane",
    "signal_pane",
)


def test_the_module_reads_the_same_declarations_as_the_surface_wrote(
    skinned: JsRuntime,
):
    payload = bridge_payload()
    for name in SKINNED_FIELDS:
        sheet = payload[name]["style_sheet"]
        expected = [
            {"property": prop, "value": value}
            for prop, value in python_declarations(base_body(sheet))
        ]
        assert expected, f"{name} declares nothing; the check cannot report"
        assert (
            skinned.declarations(sheet) == expected
        ), f"declarations differ for {name}"


def test_the_declaration_check_names_a_changed_sheet(skinned: JsRuntime):
    sheet = bridge_payload()["signal_header"]["style_sheet"]
    expected = [
        {"property": prop, "value": value}
        for prop, value in python_declarations(base_body(sheet))
    ]
    assert skinned.declarations(sheet + "letter-spacing:1px;") != expected


def test_the_shipped_payload_repeats_its_own_sheet_in_every_discrete_field(
    skinned: JsRuntime,
):
    report = skinned.push(bridge_payload())
    named = [f for f in report["faults"] if f["fault"] in ("disagrees", "wrong-type")]
    assert named == [], f"the shipped payload disagrees with itself: {named}"


def test_the_sheet_agreement_check_covers_every_skinned_element(skinned: JsRuntime):
    """C30: a check reading no element would report zero faults on any payload."""
    payload = bridge_payload()
    pairs = skinned.json("acervatorConsole.skinPairs()")
    covered = {}
    for name in SKINNED_FIELDS:
        body = base_body(payload[name]["style_sheet"])
        written = {prop for prop, _ in python_declarations(body)}
        covered[name] = sorted(
            pair["field"] for pair in pairs if pair["property"] in written
        )
    empty = sorted(name for name, fields in covered.items() if not fields)
    assert not empty, f"these elements are held against no declaration: {empty}"
    assert covered == {
        "clear_button": ["background", "border", "color", "font_family"],
        "control_bar": ["background", "border_bottom"],
        "log_pane": ["background", "border", "color"],
        "pause_button": ["background", "border", "color", "font_family"],
        "pause_indicator": ["color", "font_family"],
        "signal_header": ["background", "border_top", "color", "font_family"],
        "signal_pane": ["background", "border", "color", "font_family"],
    }, f"the sheets cover {covered}"


@pytest.mark.parametrize("name", SKINNED_FIELDS)
def test_a_skin_field_that_disagrees_with_its_own_sheet_is_named(
    skinned: JsRuntime, name: str
):
    payload = bridge_payload()
    pairs = skinned.json("acervatorConsole.skinPairs()")
    body = base_body(payload[name]["style_sheet"])
    written = {prop for prop, _ in python_declarations(body)}
    field = next(p["field"] for p in pairs if p["property"] in written)
    payload[name][field] = payload[name][field] + "0"
    report = skinned.push(payload)
    named = [
        f for f in report["faults"] if f["where"] == name and f["fault"] == "disagrees"
    ]
    assert [f["field"] for f in named] == [field], f"the check named {named}"


@pytest.mark.parametrize("name", SKINNED_FIELDS)
def test_a_skin_field_that_is_a_number_is_named_against_its_own_sheet(
    skinned: JsRuntime, name: str
):
    """The sheet publishes the type, so a number where a colour belongs is named."""
    payload = bridge_payload()
    pairs = skinned.json("acervatorConsole.skinPairs()")
    written = {
        prop for prop, _ in python_declarations(base_body(payload[name]["style_sheet"]))
    }
    field = next(p["field"] for p in pairs if p["property"] in written)
    payload[name][field] = 7
    report = skinned.push(payload)
    assert {
        "where": name,
        "field": field,
        "fault": "wrong-type",
        "detail": "number",
    } in report["faults"]


def test_a_skin_field_with_no_declaration_behind_it_raises_no_fault(skinned: JsRuntime):
    """The log pane sheet writes no font-family, so font_family is held against nothing."""
    payload = bridge_payload()
    written = {
        prop
        for prop, _ in python_declarations(
            base_body(payload["log_pane"]["style_sheet"])
        )
    }
    assert "font-family" not in written
    payload["log_pane"]["font_family"] = 7
    report = skinned.push(payload)
    named = [f for f in report["faults"] if f["where"] == "log_pane"]
    assert named == [], f"the check named {named}"
    assert skinned.json("acervatorConsole.logPane()")["font_family"] == 7


def test_the_checked_and_hover_rules_reach_no_style_and_are_carried_apart(
    skinned: JsRuntime,
):
    """Qt repaints the Pause button amber when checked and no inline style carries that rule."""
    payload = bridge_payload()
    sheet = payload["pause_button"]["style_sheet"]
    painted = skinned.style_of(sheet)
    assert str(dss.MAIN_TOGGLE_CHECKED_AMBER) not in json.dumps(painted)
    assert str(dss.MAIN_BUTTON_HOVER) not in json.dumps(painted)
    skinned.bind_json("SHEET", sheet)
    rules = skinned.json("acervatorConsole.stateRules(JSON.parse(SHEET))")
    assert len(rules) == 2, f"the module found {len(rules)} state rules"
    assert str(dss.MAIN_TOGGLE_CHECKED_AMBER) in json.dumps(rules)


def test_the_state_rule_check_finds_none_in_a_sheet_that_has_none(skinned: JsRuntime):
    skinned.bind_json("SHEET", bridge_payload()["log_pane"]["style_sheet"])
    assert skinned.json("acervatorConsole.stateRules(JSON.parse(SHEET))") == []


def carriers_of(value: Any) -> list:
    tokens = token_payload()
    aliases = tokens["alias_targets"]
    return sorted(
        name
        for name, held in tokens["tokens"].items()
        if str(held) == str(value) and name not in aliases
    )


CONSOLE_COLOURS = sorted(
    {
        value
        for value in console_values()
        if isinstance(value, str) and HEX_COLOUR.fullmatch(value)
    }
)


def test_every_colour_the_tab_paints_resolves_to_one_token(skinned: JsRuntime):
    """A colour is painted through the one token that holds it."""
    assert CONSOLE_COLOURS, "the tab paints no colour; the check cannot report"
    for colour in CONSOLE_COLOURS:
        skinned.bind_json("VALUE", colour)
        name = skinned.json("acervatorWidgets.variableFor(JSON.parse(VALUE))")
        assert carriers_of(colour) == [
            name
        ], f"{colour} is carried by {carriers_of(colour)}"


def test_no_console_length_is_painted_through_a_token(skinned: JsRuntime):
    """C77: only the margin 6 has one carrier, RADIUS_CARD, which is a corner radius."""
    payload = bridge_payload()
    lengths = sorted(
        {
            payload["container"]["spacing_px"],
            payload["control_bar"]["spacing_px"],
            payload["signal_header"]["padding_px"],
            payload["log_pane"]["padding_px"],
            payload["log_pane"]["max_blocks"],
        }
        | set(payload["control_bar"]["margins_px"])
        | set(payload["pause_button"]["padding_px"])
    )
    single = {
        value: carriers_of(value) for value in lengths if len(carriers_of(value)) == 1
    }
    assert single == {6: ["RADIUS_CARD"]}, f"one token carries {single}"
    for value in lengths:
        assert skinned.json("acervatorConsole.pixels(" + json.dumps(value) + ")") == (
            str(value) + "px"
        )


def test_the_colour_resolver_reports_no_name_with_the_widget_module_off_the_page(
    js: JsRuntime,
):
    js.load_tokens()
    assert js.json("typeof acervatorWidgets") == "undefined"
    assert js.style_of(bridge_payload()["log_pane"]["style_sheet"]) == {}


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
        """Opens the page again while the module global stays absent."""
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.js("typeof window.acervatorSetConsole") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the console module: readyState "
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
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


STYLE_NAMES = [
    "display",
    "flexDirection",
    "flexGrow",
    "rowGap",
    "columnGap",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "color",
    "backgroundColor",
    "fontFamily",
    "fontSize",
    "whiteSpace",
    "overflowX",
    "overflowY",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderBottomStyle",
    "borderBottomWidth",
    "borderBottomColor",
]

EXPANDED = {
    "background": ("backgroundColor",),
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "border-top": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "border-bottom": ("borderBottomStyle", "borderBottomWidth", "borderBottomColor"),
    "color": ("color",),
    "font-family": ("fontFamily",),
    "font-size": ("fontSize",),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
}

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "document.body.appendChild(window.HOST);"
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
    "        hidden: el.hidden, text: own,"
    "        scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,"
    "        scrollHeight: el.scrollHeight, clientHeight: el.clientHeight,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)


def give_tokens(browser: Browser) -> int:
    """Put the real token table on the page and write it into the CSS."""
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
        "acervatorSetConsole(JSON.parse(window.PAYLOAD));"
        "acervatorConsole.renderTab(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    return json.loads(browser.js(READ_PARTS))


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


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def sheet_agrees(drawn: dict, expected: dict, where: str) -> None:
    differing = {
        name: (value, drawn["style"].get(name))
        for name, value in expected.items()
        if drawn["style"].get(name) != value
    }
    assert not differing, (
        f"{where}: {len(differing)} of {len(expected)} declared values differ "
        f"from the surface's own: {differing}"
    )


def pixels(value: Any) -> str:
    return str(value) + "px"


SKINNED_PATHS = {
    "control_bar": "tab/control-bar",
    "pause_button": "tab/control-bar/pause-button",
    "pause_indicator": "tab/control-bar/pause-indicator",
    "clear_button": "tab/control-bar/clear-button",
    "signal_header": "tab/splitter/signal-box/signal-header",
    "log_pane": "tab/splitter/log-pane",
    "signal_pane": "tab/splitter/signal-box/signal-pane",
}


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorConsole") == "object"
    assert browser.js("typeof window.acervatorSetConsole") == "function"
    assert browser.js("typeof window.acervatorLoadConsole") == "function"


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    browser.js(WATCH_VIOLATIONS)
    draw_tab(browser, state_payload("filled"))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_drawn_tab_names_every_part_a_check_reads(browser: Browser):
    """C81: every drawn part carries attrs a check reads, so no child reads as empty."""
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    paths = sorted({one["path"] for one in parts})
    assert paths == sorted(
        {
            "tab",
            "tab/control-bar",
            "tab/control-bar/pause-button",
            "tab/control-bar/pause-indicator",
            "tab/control-bar/stretch",
            "tab/control-bar/clear-button",
            "tab/splitter",
            "tab/splitter/log-pane",
            "tab/splitter/log-pane/block",
            "tab/splitter/signal-box",
            "tab/splitter/signal-box/signal-header",
            "tab/splitter/signal-box/signal-pane",
            "tab/splitter/signal-box/signal-pane/block",
            "tab/machinery",
            "tab/machinery/timer",
            "tab/machinery/counter",
            "tab/machinery/log-handler",
            "tab/machinery/log-handler/logger",
        }
    ), f"the tab drew {paths}"
    for one in at_path(parts, "tab/splitter/log-pane/block"):
        assert "data-index" in one["attrs"]
    for one in at_path(parts, "tab/machinery/timer"):
        assert one["attrs"]["data-timer"] in payload["timers"]
    for one in at_path(parts, "tab/machinery/counter"):
        assert one["attrs"]["data-counter"] in payload["ledger"]
    for one in at_path(parts, "tab/machinery/log-handler/logger"):
        assert "data-logger" in one["attrs"]


def test_the_drawn_tab_places_every_control_in_the_order_the_surface_names(
    browser: Browser,
):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    slots = [
        one["attrs"]["data-slot"]
        for one in parts
        if one["path"].startswith("tab/control-bar/")
    ]
    assert slots == payload["control_bar_order"], f"the bar drew {slots}"


def test_the_control_order_check_names_a_swapped_pair(browser: Browser):
    payload = bridge_payload()
    order = payload["control_bar_order"]
    order[0], order[1] = order[1], order[0]
    parts = draw_tab(browser, payload)
    slots = [
        one["attrs"]["data-slot"]
        for one in parts
        if one["path"].startswith("tab/control-bar/")
    ]
    assert slots == order
    assert slots != bridge_payload()["control_bar_order"]


def test_the_drawn_log_pane_shows_every_line_the_surface_published(browser: Browser):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    drawn = at_path(parts, "tab/splitter/log-pane/block")
    assert [one["text"] for one in drawn] == payload["log_pane"]["blocks"]
    assert [one["attrs"]["data-index"] for one in drawn] == [
        str(at) for at in range(len(payload["log_pane"]["blocks"]))
    ]
    signals = at_path(parts, "tab/splitter/signal-box/signal-pane/block")
    assert [one["text"] for one in signals] == payload["signal_pane"]["blocks"]


def test_the_log_line_check_names_one_changed_line(browser: Browser):
    payload = state_payload("filled")
    payload["log_pane"]["blocks"][1] += "!"
    parts = draw_tab(browser, payload)
    shown = [one["text"] for one in at_path(parts, "tab/splitter/log-pane/block")]
    original = state_payload("filled")["log_pane"]["blocks"]
    differing = [at for at, line in enumerate(original) if shown[at] != line]
    assert differing == [1], f"the check named {differing}"


def test_the_drawn_signal_header_shows_the_text_the_surface_published(browser: Browser):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    assert only(parts, SKINNED_PATHS["signal_header"])["text"] == (
        payload["signal_header"]["text"]
    )


def test_the_drawn_buttons_show_the_text_the_surface_published(browser: Browser):
    payload = bridge_payload()
    parts = draw_tab(browser, payload)
    pause = only(parts, SKINNED_PATHS["pause_button"])
    clear = only(parts, SKINNED_PATHS["clear_button"])
    assert pause["text"] == payload["pause_button"]["text"]
    assert clear["text"] == payload["clear_button"]["text"]
    assert pause["tag"] == "BUTTON"
    assert pause["attrs"]["data-action"] == payload["actions"]["pause_button.clicked"]
    assert clear["attrs"]["data-action"] == payload["actions"]["clear_button.clicked"]
    assert (
        pause["attrs"]["aria-pressed"]
        == str(payload["pause_button"]["checked"]).lower()
    )
    assert (
        pause["attrs"]["data-checkable"]
        == str(payload["pause_button"]["checkable"]).lower()
    )
    assert (
        clear["attrs"]["data-checkable"]
        == str(payload["clear_button"]["checkable"]).lower()
    )


@pytest.mark.parametrize("name", SKINNED_FIELDS)
def test_the_drawn_element_matches_the_surface_s_own_style_sheet(
    browser: Browser, name: str
):
    """R1 and C21 mean every value is compared against a probe, never a typed number."""
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    expected = probe(browser, base_body(payload[name]["style_sheet"]))
    assert expected, f"{name} declares nothing; the check cannot report"
    sheet_agrees(only(parts, SKINNED_PATHS[name]), expected, name)


def test_the_style_sheet_check_names_one_changed_colour(browser: Browser):
    payload = bridge_payload()
    original = payload["signal_header"]["style_sheet"]
    payload["signal_header"]["style_sheet"] = original.replace(
        str(dss.PRIMARY), str(dss.ERROR)
    )
    parts = draw_tab(browser, payload)
    drawn = only(parts, SKINNED_PATHS["signal_header"])
    expected = probe(browser, base_body(original))
    differing = sorted(
        name for name, value in expected.items() if drawn["style"].get(name) != value
    )
    assert differing == ["color"], f"the check named {differing}"


def test_the_drawn_layout_matches_the_margins_the_surface_publishes(browser: Browser):
    payload = state_payload("filled")
    parts = draw_tab(browser, payload)
    bar = only(parts, "tab/control-bar")
    margins = payload["control_bar"]["margins_px"]
    assert bar["style"]["paddingLeft"] == pixels(margins[0])
    assert bar["style"]["paddingTop"] == pixels(margins[1])
    assert bar["style"]["paddingRight"] == pixels(margins[2])
    assert bar["style"]["paddingBottom"] == pixels(margins[3])
    assert bar["style"]["columnGap"] == pixels(payload["control_bar"]["spacing_px"])
    splitter = only(parts, "tab/splitter")
    assert splitter["style"]["flexDirection"] == "column"
    assert splitter["attrs"]["data-orientation"] == payload["splitter"]["orientation"]
    assert only(parts, "tab/splitter/log-pane")["style"]["flexGrow"] == str(
        payload["splitter"]["stretch"][0]
    )
    assert only(parts, "tab/splitter/signal-box")["style"]["flexGrow"] == str(
        payload["splitter"]["stretch"][1]
    )


def test_the_layout_check_names_one_changed_margin(browser: Browser):
    payload = bridge_payload()
    original = payload["control_bar"]["margins_px"][1]
    payload["control_bar"]["margins_px"][1] = original + original
    parts = draw_tab(browser, payload)
    assert only(parts, "tab/control-bar")["style"]["paddingTop"] == pixels(
        original + original
    )


def changed_paths(before: list, after: list) -> set:
    assert len(before) == len(after), "the tab drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((one["path"], key))
    return moved


def rewrite_token(browser: Browser, name: str, value: Any) -> None:
    browser.js(
        "document.documentElement.style.setProperty("
        + json.dumps("--" + name)
        + ", "
        + json.dumps(str(value))
        + ");"
    )


def test_the_drawn_tab_follows_the_signal_header_colour_token(browser: Browser):
    """The token is rewritten and only the signal-header part moves."""
    before = draw_tab(browser, state_payload("filled"))
    assert carriers_of(dss.PRIMARY) == ["PRIMARY"]
    rewrite_token(browser, "PRIMARY", dss.ERROR)
    moved = changed_paths(before, read_parts(browser))
    assert moved == {
        (SKINNED_PATHS["signal_header"], "color"),
        (SKINNED_PATHS["signal_header"], "borderBottomColor"),
    }, f"the token moved {sorted(moved)}"


def test_the_drawn_tab_follows_the_signal_header_background_token(browser: Browser):
    before = draw_tab(browser, state_payload("filled"))
    assert carriers_of(dss.SURFACE_CONSOLE_HEADER) == ["SURFACE_CONSOLE_HEADER"]
    rewrite_token(browser, "SURFACE_CONSOLE_HEADER", dss.ERROR)
    moved = changed_paths(before, read_parts(browser))
    assert moved == {
        (SKINNED_PATHS["signal_header"], "backgroundColor")
    }, f"the token moved {sorted(moved)}"


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(browser: Browser):
    before = draw_tab(browser, state_payload("filled"))
    assert changed_paths(before, read_parts(browser)) == set()


def test_the_machinery_is_drawn_and_hidden(browser: Browser):
    """The timers, counters and log handler reach the page as data the operator never sees."""
    payload = state_payload("counted")
    parts = draw_tab(browser, payload)
    assert only(parts, "tab/machinery")["hidden"] is True
    timers = {
        one["attrs"]["data-timer"]: (
            one["attrs"]["data-interval-ms"],
            one["attrs"]["data-running"],
        )
        for one in at_path(parts, "tab/machinery/timer")
    }
    assert timers == {
        name: (str(one["interval_ms"]), str(one["running"]).lower())
        for name, one in payload["timers"].items()
    }
    counters = {
        one["attrs"]["data-counter"]: one["attrs"]["data-value"]
        for one in at_path(parts, "tab/machinery/counter")
    }
    assert counters == {name: str(value) for name, value in payload["ledger"].items()}


def test_the_machinery_check_reads_a_shown_element_as_shown(browser: Browser):
    parts = draw_tab(browser, bridge_payload())
    assert only(parts, "tab")["hidden"] is False


def logger_state(logger: logging.Logger) -> tuple:
    """C75: one logger's level and the identity of every handler on it."""
    return (logger.level, tuple(sorted(id(one) for one in logger.handlers)))


def test_driving_the_module_attaches_nothing_to_the_root_logger(browser: Browser):
    """Drawing the tab leaves the root logger level and handlers exactly as they were."""
    root = logging.getLogger()
    before = logger_state(root)
    draw_tab(browser, state_payload("filled"))
    assert (
        logger_state(root) == before
    ), f"the root logger moved from {before} to {logger_state(root)}"


def test_the_logger_snapshot_reports_a_handler_that_was_added():
    """Taken on a named logger so the root logger level and handlers stay untouched."""
    named = logging.getLogger("acervator.console_tab_unit")
    before = logger_state(named)
    handler = logging.NullHandler()
    named.addHandler(handler)
    try:
        assert logger_state(named) != before
    finally:
        named.removeHandler(handler)
    assert logger_state(named) == before


def test_the_surface_publishes_the_root_logger_and_the_handler_level(browser: Browser):
    """The surface lists the root logger in ``loggers`` and publishes ``handler_level``."""
    payload = bridge_payload()
    assert payload["log_handler"]["loggers"] == ["", "acervator"]
    assert payload["log_handler"]["handler_level"] == logging.DEBUG
    parts = draw_tab(browser, payload)
    handler = only(parts, "tab/machinery/log-handler")
    assert handler["attrs"]["data-handler-level"] == str(logging.DEBUG)
    assert handler["attrs"]["data-format"] == payload["log_handler"]["format"]
    named = [
        one["attrs"]["data-logger"]
        for one in at_path(parts, "tab/machinery/log-handler/logger")
    ]
    assert named == payload["log_handler"]["loggers"]
    assert "" in named, "the surface no longer names the root logger"


def test_a_long_line_overflows_the_log_pane_rather_than_wrapping(browser: Browser):
    """Reported and not repaired: wrap is false, so the pane scrolls sideways."""
    parts = draw_tab(browser, state_payload("long_line"))
    pane = only(parts, "tab/splitter/log-pane")
    block = only(parts, "tab/splitter/log-pane/block")
    assert pane["style"]["whiteSpace"] == "pre"
    assert pane["style"]["overflowX"] == "auto"
    assert block["text"].endswith(LONG_WORD)
    assert pane["clientWidth"] > 0, "the host was never given a width"
    assert (
        pane["scrollWidth"] > pane["clientWidth"]
    ), f"the 200 character line fits in {pane['clientWidth']} pixels"


def test_a_short_line_does_not_overflow_the_log_pane(browser: Browser):
    parts = draw_tab(browser, state_payload("filled"))
    pane = only(parts, "tab/splitter/log-pane")
    assert pane["scrollWidth"] == pane["clientWidth"]


def test_the_signal_pane_sets_no_wrap_because_the_surface_publishes_none(
    browser: Browser,
):
    """Reported and not repaired: the signal pane keeps the browser wrapping."""
    payload = state_payload("long_line")
    assert "wrap" not in payload["signal_pane"]
    parts = draw_tab(browser, payload)
    pane = only(parts, "tab/splitter/signal-box/signal-pane")
    assert pane["style"]["whiteSpace"] == "normal"
    assert pane["scrollWidth"] > pane["clientWidth"]


def test_the_signal_header_loses_its_leading_spaces_on_the_page(browser: Browser):
    """Reported and not repaired: the browser collapses the two leading spaces."""
    payload = bridge_payload()
    assert payload["signal_header"]["text"].startswith("  ")
    parts = draw_tab(browser, payload)
    header = only(parts, SKINNED_PATHS["signal_header"])
    assert header["text"] == payload["signal_header"]["text"]
    assert header["style"]["whiteSpace"] == "normal"


def test_a_markup_line_is_shown_as_text_and_runs_nothing(browser: Browser):
    """A log message holding a script tag reaches the page as text."""
    payload = bridge_payload({"records": [dict(LONG_RECORD, message=MARKUP_WORD)]})
    scripts_before = browser.js("document.scripts.length")
    parts = draw_tab(browser, payload)
    block = only(parts, "tab/splitter/log-pane/block")
    assert block["text"].endswith(MARKUP_WORD)
    assert browser.js("document.scripts.length") == scripts_before
    assert browser.js("typeof window.MARKUP_RAN") == "undefined"


def test_a_record_holding_a_newline_becomes_two_blocks(js: JsRuntime):
    """The surface splits a record on its newline, so one message the
    operator sends becomes two lines in the pane."""
    payload = bridge_payload({"records": [NEWLINE_RECORD]})
    js.push(payload)
    blocks = js.json("acervatorConsole.logBlocks()")
    assert len(blocks) == 2, f"the pane holds {blocks}"
    assert blocks[1] == "second"


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
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
    assert report["held"]["fields"] == len(MODULE_READERS) - 1


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
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


def test_the_missing_and_null_checks_are_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(bridge_payload())
    kinds = [one["fault"] for one in report["faults"]]
    assert "missing" not in kinds
    assert "null" not in kinds


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorConsole.isLoaded()") is False
        assert js.json("acervatorConsole.logBlocks()") == []
        assert report["declared"] is None
        assert report["held"] is None
        assert [one["fault"] for one in report["faults"]] == ["not-an-object"]


def test_a_name_the_payload_never_carried_is_not_a_timer_or_a_counter(js: JsRuntime):
    """Every JavaScript object inherits names such as constructor, valueOf and toString."""
    js.push(bridge_payload())
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        assert js.named("timer", inherited) is None
        assert js.named("counter", inherited) is None
        assert js.named("action", inherited) is None


def test_the_inherited_name_check_still_reads_a_real_timer(js: JsRuntime):
    payload = bridge_payload()
    js.push(payload)
    assert js.named("timer", "drain") == payload["timers"]["drain"]
    assert js.named("counter", "seq") == payload["ledger"]["seq"]


def test_a_pane_text_that_disagrees_with_its_own_blocks_is_named(js: JsRuntime):
    payload = state_payload("filled")
    payload["log_pane"]["text"] = "a text the blocks do not join to"
    report = js.push(payload)
    assert [one for one in report["faults"] if one["fault"] == "disagrees"] == [
        {
            "where": "log_pane",
            "field": "text",
            "fault": "disagrees",
            "detail": "\n".join(state_payload("filled")["log_pane"]["blocks"]),
        }
    ]


def test_a_block_count_that_disagrees_with_its_own_blocks_is_named(js: JsRuntime):
    payload = state_payload("filled")
    payload["log_pane"]["block_count"] = "3"
    report = js.push(payload)
    assert {
        "where": "log_pane",
        "field": "block_count",
        "fault": "disagrees",
        "detail": len(payload["log_pane"]["blocks"]),
    } in report["faults"]


def test_an_is_empty_that_disagrees_with_its_own_blocks_is_named(js: JsRuntime):
    payload = state_payload("filled")
    payload["log_pane"]["is_empty"] = True
    report = js.push(payload)
    assert {
        "where": "log_pane",
        "field": "is_empty",
        "fault": "disagrees",
        "detail": False,
    } in report["faults"]


def test_more_blocks_than_the_published_cap_is_named(js: JsRuntime):
    payload = state_payload("filled")
    payload["log_pane"]["max_blocks"] = len(payload["log_pane"]["blocks"]) - 1
    report = js.push(payload)
    assert {
        "where": "log_pane",
        "field": "blocks",
        "fault": "over-cap",
        "detail": len(payload["log_pane"]["blocks"]),
    } in report["faults"]


def test_the_over_cap_check_is_quiet_on_a_pane_inside_its_cap(js: JsRuntime):
    report = js.push(state_payload("filled"))
    assert [one for one in report["faults"] if one["fault"] == "over-cap"] == []


def test_the_published_cap_does_not_follow_the_pane_the_surface_built(js: JsRuntime):
    """Reported and not repaired: build_view_model merges the module constant max_blocks."""
    payload = state_payload("capped")
    assert payload["log_pane"]["max_blocks"] == surface.PANE_MAX_BLOCKS
    assert len(payload["log_pane"]["blocks"]) == CAPPED_BLOCKS
    report = js.push(payload)
    assert [one for one in report["faults"] if one["fault"] == "over-cap"] == []


def test_blocks_that_are_not_a_list_is_named(js: JsRuntime):
    payload = bridge_payload()
    payload["signal_pane"]["blocks"] = "not a list"
    report = js.push(payload)
    assert {
        "where": "signal_pane",
        "field": "blocks",
        "fault": "not-a-list",
        "detail": "string",
    } in report["faults"]


def test_a_control_slot_naming_no_field_is_named(js: JsRuntime):
    payload = bridge_payload()
    payload["control_bar_order"].append("no_such_control")
    report = js.push(payload)
    assert {
        "where": "control_bar_order",
        "field": "no_such_control",
        "fault": "missing",
        "detail": None,
    } in report["faults"]
    assert report["declared"]["controls"] == report["held"]["controls"] + 1


def test_a_splitter_child_naming_no_field_is_named(js: JsRuntime):
    payload = bridge_payload()
    payload["splitter"]["children"].append("no_such_pane")
    report = js.push(payload)
    assert {
        "where": "children",
        "field": "no_such_pane",
        "fault": "missing",
        "detail": None,
    } in report["faults"]
    assert report["declared"]["panes"] == report["held"]["panes"] + 1


def test_a_short_stretch_list_is_named(js: JsRuntime):
    """C72 counts the order and the child_stretch weights apart."""
    payload = bridge_payload()
    payload["control_bar"]["child_stretch"].pop()
    report = js.push(payload)
    assert {
        "where": "control_bar",
        "field": "child_stretch",
        "fault": "short-list",
        "detail": len(payload["control_bar"]["child_stretch"]),
    } in report["faults"]


def test_the_short_list_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    report = js.push(bridge_payload())
    assert [one for one in report["faults"] if one["fault"] == "short-list"] == []


HOSTILE_NUMBERS = {
    "text where a number belongs": "1234.5",
    "a true flag": True,
    "nothing at all": None,
}


@pytest.mark.parametrize("case", sorted(HOSTILE_NUMBERS))
def test_a_hostile_timer_interval_reaches_the_module_unchanged(
    js: JsRuntime, case: str
):
    """The tab carries the exact interval_ms the surface produced, formatting nothing."""
    payload = bridge_payload()
    payload["timers"]["drain"]["interval_ms"] = HOSTILE_NUMBERS[case]
    js.push(payload)
    assert js.named("timer", "drain")["interval_ms"] == HOSTILE_NUMBERS[case]


def test_a_very_large_integer_loses_precision_crossing_the_bridge(js: JsRuntime):
    """C31: the bridge carries 10 to the 24th as a double and loses digits."""
    payload = bridge_payload()
    payload["timers"]["drain"]["interval_ms"] = 10**24
    js.push(payload)
    held = js.named("timer", "drain")["interval_ms"]
    assert held == float(10**24)
    assert held != 10**24, "the bridge kept every digit; C31 does not apply here"


def test_the_timer_check_reads_a_different_value_for_a_different_interval(
    js: JsRuntime,
):
    payload = bridge_payload()
    payload["timers"]["drain"]["interval_ms"] = 1
    js.push(payload)
    assert js.named("timer", "drain")["interval_ms"] == 1
    assert (
        js.named("timer", "drain")["interval_ms"]
        != bridge_payload()["timers"]["drain"]["interval_ms"]
    )


NOT_A_NUMBER = {
    "not a number": float("nan"),
    "an infinity": float("inf"),
    "a negative infinity": float("-inf"),
}


@pytest.mark.parametrize("case", sorted(NOT_A_NUMBER))
def test_a_not_a_number_never_reaches_the_module_at_all(js: JsRuntime, case: str):
    """Issue 257: JSON.parse refuses NaN, so the frame is dropped before the module sees it."""
    payload = bridge_payload()
    payload["ledger"]["seq"] = NOT_A_NUMBER[case]
    js.bind_json("PAYLOAD", payload)
    raised = js.raised("acervatorSetConsole(JSON.parse(PAYLOAD))")
    assert raised, f"{case} parsed where the real page drops the frame"
    assert "JSON" in raised or "SyntaxError" in raised, raised


def test_a_real_number_in_the_same_field_parses(js: JsRuntime):
    payload = bridge_payload()
    payload["ledger"]["seq"] = 1.5
    js.bind_json("PAYLOAD", payload)
    assert js.raised("acervatorSetConsole(JSON.parse(PAYLOAD))") == ""
    assert js.named("counter", "seq") == 1.5


def test_a_hostile_payload_still_draws_a_tab(browser: Browser):
    """A module that threw here would draw no tab and no log-pane block at all."""
    payload = state_payload("filled")
    payload["pause_button"]["text"] = 7
    payload["signal_header"]["color"] = None
    payload["log_pane"]["style_sheet"] = 7
    payload["control_bar"]["margins_px"] = None
    payload["timers"] = None
    parts = draw_tab(browser, payload)
    assert only(parts, "tab")
    assert only(parts, SKINNED_PATHS["pause_button"])["text"] == "7"
    assert len(at_path(parts, "tab/splitter/log-pane/block")) == len(
        payload["log_pane"]["blocks"]
    )
    assert at_path(parts, "tab/machinery/timer") == []


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadConsole();")
    drain_events()
    assert js.json("window.CALLS") == [[surface.METHOD, "{}"]]
    assert js.json("acervatorConsole.isLoaded()") is True


def test_the_module_passes_a_caller_s_parameters_to_the_surface(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload({"clear_log": True}))
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", {"clear": True})
    js.run("acervatorLoadConsole(JSON.parse(WANTED));")
    drain_events()
    assert js.json("window.CALLS") == [[surface.METHOD, '{"clear":true}']]


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadConsole(); acervatorLoadConsole(); acervatorLoadConsole();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadConsole();")
    drain_events()
    js.run("acervatorConsole.forget(); acervatorLoadConsole();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadConsole();")
    drain_events()
    assert js.json("acervatorConsole.isLoaded()") is False
    assert (
        js.json("acervatorConsole.loadError()") == "the preload bridge is not present"
    )


def test_a_refused_first_ask_is_not_remembered(js: JsRuntime):
    """A backend not running at page open must be reachable on the next ask."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadConsole();"
    )
    drain_events()
    assert js.json("acervatorConsole.isLoaded()") is False
    assert (
        js.json("acervatorConsole.loadError()") == "the Python backend is not running"
    )
    js.run("acervatorLoadConsole();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorConsole.isLoaded()") is True


def test_the_bridge_handler_serves_the_same_fields_as_the_view_model(js: JsRuntime):
    """view_model keeps one pane per process, so the panes are left empty again."""
    try:
        served = json.loads(
            json.dumps(surface.view_model({"clear": True}), ensure_ascii=True)
        )
        js.push(served)
        assert sorted(served) == sorted(MODULE_READERS)
        assert js.json("acervatorConsole.isLoaded()") is True
    finally:
        surface.view_model({"clear": True})


def test_the_page_names_the_console_module_among_its_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("console_tab.js")]
    assert len(named) == 1, f"the page names {len(named)} console modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


def test_the_page_loads_the_header_module_before_the_console_module():
    """The console module reads Qt style sheets through header_strip.js,
    so the page must run that file first."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    assert refs.index("../../src/gui/web/header_strip.js") < refs.index(
        "../../src/gui/web/console_tab.js"
    )
