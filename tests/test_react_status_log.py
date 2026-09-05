"""The React Activity Log, against the surface that describes it.

WHAT IS PROVED
==============
``src/gui/web/status_log.js`` draws the Activity Log that
``src/gui/main_tabs/status_log_surface.py`` describes, and carries no
colour, size or text of its own. The operator reads this pane to see what
the bots are doing, so the value agreement, the rendered read-back and
the no-literals scan are three halves of one claim.

A colour carried by exactly one non-alias design token is painted as that
CSS variable through ``shared_widgets.js``, never copied. The stamp
colour arrives as three channels rather than as a token name, so it is
painted as ``rgb`` from the surface's own numbers.

HOW THE JAVASCRIPT IS RUN
=========================
Node is not installed and nothing here adds a JavaScript test runner.
``QJSEngine`` from ``PySide6.QtQml`` runs the module as plain JavaScript
and answers in JSON. ``QWebEngineView`` loads the real
``desktop/renderer/index.html`` from disk, which is the only way to draw
the log with the vendored React under the page's own policy.

THE CONTROLS
============
Every count has a planted opposite that must be named. A colour, a size,
a stamp colour, a bullet and the placeholder planted in the module file
itself are each caught by the literal scan, and the file is restored byte
for byte with its hash read back. One changed value proves the rendered
read-back can report, and a token rewritten on the page proves the log
resolves through the token rather than copying it.
"""

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
from src.gui.main_tabs import status_log_surface as sls
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import swap_module

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "status_log.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
THEMES_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
WIDGETS_PATH = REPO_ROOT / "src" / "gui" / "web" / "shared_widgets.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body can plant into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
EVENT_DRAIN_ROUNDS = 20
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2

FIXED_CLOCK = 1000.0
LONG_LINE_CHARS = 200

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

HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")
STYLE_ATTR = re.compile(r'style="([^"]*)"')

TRADE_LINES = (
    sls.TRADE_PREFIX + " BTC-USD FILLED 0.5 at 64000",
    sls.TRADE_PREFIX + " ETH-USD PLACED 2.0",
    sls.TRADE_PREFIX + " SOL-USD SENT",
    sls.TRADE_PREFIX + " DOGE-USD CANCELLED",
)
WIRE_LINES = (
    sls.WIRE_FLOW_PREFIXES[0] + " BTC to ETH 12.00",
    sls.WIRE_FLOW_PREFIXES[1] + " 4.00 booked",
    sls.WIRE_STACK_PREFIX + " ADA depth 3",
)
PLAIN_LEVELS = ("info", "success", "warning", "error", "chatter")


def message_batch() -> list:
    """Every prefix and every level the surface colours differently."""
    batch = [{"message": one, "level": "info"} for one in TRADE_LINES]
    batch += [{"message": one, "level": "info"} for one in WIRE_LINES]
    batch += [{"message": "bot " + one, "level": one} for one in PLAIN_LEVELS]
    return batch


# -- the surface, as the bridge serialises it --------------------------


def fresh_model() -> sls.StatusLogModel:
    """A log of its own, on a clock that never moves."""
    return sls.StatusLogModel(clock=lambda: FIXED_CLOCK)


def serialised(model: Any) -> dict:
    """One surface answer after a round trip through the bridge's JSON.

    ``src/core/desktop_bridge.py`` writes every response with
    ``json.dumps(..., ensure_ascii=True)``, so a tuple reaches the
    renderer as an array.
    """
    return json.loads(json.dumps(model, ensure_ascii=True))


def built(messages=None, paused=None, toggle: bool = False, prepare=None) -> dict:
    model = fresh_model()
    if prepare is not None:
        prepare(model)
    return serialised(
        sls.build_view_model(model, messages, paused=paused, toggle=toggle)
    )


def hold_two(model: sls.StatusLogModel) -> None:
    model.pause()
    model.log("held first")
    model.log("held second")


#: One payload per state, built once so a stamp taken from the wall clock
#: cannot differ between two reads of the same state.
STATE_PAYLOADS = {
    "empty": built(),
    "mixed": built(message_batch()),
    "paused": built([{"message": "while paused"}], paused=True),
    "resumed": built([{"message": "after resume"}], paused=False, prepare=hold_two),
    "forced": built([{"message": "watchdog", "force": True}], paused=True),
}
STATE_NAMES = tuple(STATE_PAYLOADS)


def state_payload(name: str) -> dict:
    return serialised(STATE_PAYLOADS[name])


def token_payload() -> dict:
    """The design-token surface's answer, for the variable resolver."""
    return serialised(dss.view_model({}))


def theme_payload() -> dict:
    """The theme surface's answer, the resolver's second table."""
    return serialised(tes.view_model({}))


def payload_lines(payload: dict) -> list:
    return payload["document"]["lines"]


@pytest.fixture()
def pane():
    """The bridge's own log, put back after the test that used it."""
    prior = sls.PANE_MODEL
    sls.PANE_MODEL = None
    try:
        yield sls.pane_model()
    finally:
        sls.PANE_MODEL = prior


# -- the JavaScript engine ---------------------------------------------


def drain_events() -> None:
    """Let QJSEngine run its promise callbacks."""
    from PySide6.QtCore import QCoreApplication, QEventLoop

    for _ in range(EVENT_DRAIN_ROUNDS):
        QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents)


class JsRuntime:
    """A QJSEngine holding ``status_log.js`` and a ``window`` global."""

    def __init__(self, engine: Any, source: str) -> None:
        self._engine = engine
        engine.evaluate("var window = this;")
        loaded = engine.evaluate(source, MODULE_PATH.name)
        if loaded.isError():
            raise AssertionError("status_log.js did not run: " + loaded.toString())

    def engine_of(self) -> Any:
        """A second engine of the same kind, for a second module body."""
        return type(self._engine)()

    def run(self, script: str) -> Any:
        result = self._engine.evaluate(script)
        assert not result.isError(), script + " -> " + result.toString()
        return result

    def json(self, expression: str) -> Any:
        """Evaluate ``expression`` and bring its value back as Python."""
        text = self.run("JSON.stringify(" + expression + ")").toString()
        return None if text == "undefined" else json.loads(text)

    def bind_json(self, name: str, value: Any) -> None:
        """Bind ``value`` as JSON TEXT. Every reader parses it back."""
        self._engine.globalObject().setProperty(name, json.dumps(value))

    def push(self, payload: Any) -> dict:
        self.bind_json("PAYLOAD", payload)
        return self.json("acervatorSetLog(JSON.parse(PAYLOAD))")

    def push_mutated(self, payload: Any, mutation: str) -> dict:
        """Push ``payload`` after running ``mutation`` over it as ``P``.

        A not-a-number and an infinity have no JSON spelling the page can
        parse, so they are written onto the payload in JavaScript.
        """
        self.bind_json("PAYLOAD", payload)
        return self.json(
            "(function () { var P = JSON.parse(PAYLOAD); "
            + mutation
            + " return acervatorSetLog(P); })()"
        )

    def load_tokens(self) -> None:
        """Run the design-token module and give it the real table."""
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_themes(self, name: str) -> None:
        """Run the theme module and select one theme."""
        self.run(THEMES_PATH.read_text(encoding="utf-8"))
        self.bind_json("THEMES", theme_payload())
        self.bind_json("THEME_NAME", name)
        self.run("acervatorSetThemes(JSON.parse(THEMES));")
        self.run("acervatorThemes.select(JSON.parse(THEME_NAME));")

    def load_widgets(self) -> None:
        """Run the shared-widget module, which owns the one-carrier rule."""
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def named(self, reader: str, name: Any) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorLog." + reader + "(JSON.parse(NAME))")

    def variable_for(self, value: Any) -> Any:
        self.bind_json("VALUE", value)
        return self.json("acervatorLog.variableFor(JSON.parse(VALUE))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    qtqml = pytest.importorskip("PySide6.QtQml")
    assert qapp is not None
    return JsRuntime(qtqml.QJSEngine(), MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding the surface's mixed log."""
    js.push(state_payload("mixed"))
    return js


# -- 1. everything the surface publishes reaches the module ------------

#: Every field the surface publishes, and the module reader that answers
#: for it. A field with no reader is a value that stops at the bridge.
MODULE_READERS = {
    "buffer_cap": "acervatorLog.bufferCap()",
    "buffered": "acervatorLog.buffered()",
    "default_level_color": "acervatorLog.defaultLevelColor()",
    "document": "acervatorLog.document()",
    "document_blocks": "acervatorLog.documentBlocks()",
    "health": "acervatorLog.health()",
    "level_colors": "acervatorLog.levelColors()",
    "paused": "acervatorLog.paused()",
    "resume_marker_color": "acervatorLog.resumeMarkerColor()",
    "stage_colors": "acervatorLog.stageColors()",
    "stage_default_color": "acervatorLog.stageDefaultColor()",
    "timestamp_color": "acervatorLog.timestampColor()",
    "widget": "acervatorLog.widget()",
    "wire_flow_color": "acervatorLog.wireFlowColor()",
    "wire_stack_color": "acervatorLog.wireStackColor()",
}


def unreachable_fields(payload: dict) -> list:
    """Every field of ``payload`` no module reader answers for."""
    return sorted(set(payload) - set(MODULE_READERS))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    """The whole payload, field by field, in both directions. A field the
    module never carries is a value that stops at the bridge."""
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
    """The control on the surface side. Without it a module that dropped
    a whole field would read as agreement."""
    payload = state_payload("mixed")
    payload["only_on_the_surface"] = []
    assert unreachable_fields(payload) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_reads():
    """The control on the module side. A reader with no published field
    behind it must be named."""
    payload = state_payload("mixed")
    dropped = payload.pop("level_colors")
    assert dropped is not None
    assert sorted(set(MODULE_READERS) - set(payload)) == ["level_colors"]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_holds_every_line_the_surface_painted(js: JsRuntime, state: str):
    """A line the surface painted that the module never holds is a
    message the operator would not read."""
    payload = state_payload(state)
    js.push(payload)
    assert js.json("acervatorLog.lines()") == payload_lines(payload)


def test_the_line_check_names_a_line_only_the_surface_holds(js: JsRuntime):
    """The control. A reader blind to the batch would report the same
    list whatever it was given."""
    payload = state_payload("mixed")
    dropped = payload_lines(payload).pop()
    js.push(payload)
    held = js.json("acervatorLog.lines()")
    assert len(held) == len(payload_lines(state_payload("mixed"))) - 1
    assert dropped["message"] not in [line["message"] for line in held]


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    """C72. Fields, lines and document blocks are each counted twice, so
    a payload promising more than it carries reads as a difference."""
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["lines"] == len(payload_lines(payload))
    assert report["held"]["lines"] == len(payload_lines(payload))
    assert report["declared"]["blocks"] == payload["document_blocks"]
    assert report["held"]["blocks"] == payload["health"]["document_blocks"]


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    """The control for the counts above."""
    payload = state_payload("mixed")
    del payload["level_colors"]
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(MODULE_READERS) - 1


def test_a_line_that_is_not_an_object_shortens_the_held_line_count(js: JsRuntime):
    """The control for the line counts. A batch carrying a text where a
    line belongs must read as one fewer line held than declared."""
    payload = state_payload("mixed")
    payload_lines(payload).append("not a line")
    report = js.push(payload)
    assert report["declared"]["lines"] == report["held"]["lines"] + 1


def test_the_module_names_the_fields_the_surface_declares(loaded: JsRuntime):
    """The module's own field list, against the payload it was given."""
    assert sorted(loaded.json("acervatorLog.declaredFields()")) == sorted(
        state_payload("mixed")
    )


def test_the_module_holds_every_kind_the_surface_paints(js: JsRuntime):
    """Every colouring rule the pane has, exercised at least once."""
    kinds = set()
    for state in STATE_NAMES:
        js.push(state_payload(state))
        kinds |= {line["kind"] for line in js.json("acervatorLog.lines()")}
    assert kinds == {
        sls.KIND_TRADE,
        sls.KIND_WIRE_FLOW,
        sls.KIND_WIRE_STACK,
        sls.KIND_PLAIN,
        sls.KIND_RESUME,
    }, f"the states drew {sorted(kinds)}"


# -- 2. no value is written in the JavaScript --------------------------


def js_literals(source: str) -> dict:
    """Every string and number literal in ``source``, and every stray slash.

    Walks the text once, tracking line comments, block comments and the
    three quote styles. A regular-expression literal could hide a value
    from a scan that does not parse it, so any ``/`` in code that opens
    no comment is reported rather than parsed.
    """
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
    """One published value, in every spelling a stylesheet could carry."""
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


def log_values() -> set:
    """Every colour, size and text the operator reads off the log.

    The line ``html`` is left out on purpose: the React log never runs
    it, so a word inside it is not a value this module could copy. Every
    colour it holds reaches this set through the line's ``color`` field,
    and the colour scan below reads the whole module for a hex anyway.
    """
    found: set = set()
    for name in STATE_NAMES:
        payload = state_payload(name)
        widget = payload["widget"]
        found |= as_css(widget["maximum_height_px"])
        found.add(widget["placeholder_text"])
        found.add(widget["accessible_name"])
        for field in (
            "timestamp_color",
            "default_level_color",
            "stage_default_color",
            "wire_flow_color",
            "wire_stack_color",
            "resume_marker_color",
        ):
            found.add(", ".join(str(one) for one in payload[field]))
        for table in ("level_colors", "stage_colors"):
            for triple in payload[table].values():
                found.add(", ".join(str(one) for one in triple))
        for line in payload_lines(payload):
            found.add(line["color"])
            found.add(line["message"])
            found.add(line["stamp"])
            found.add(line["bullet"])
            if line["font_size_px"] is not None:
                found |= as_css(line["font_size_px"])
    found.discard("")
    return found


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
    found.discard("")
    return found


LOG_VALUES = log_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Field and kind names the module writes as text literals. None is a colour,
#: a size or a text the log shows.
NAMED_WORDS = sorted(
    {
        "accessible_name",
        "b",
        "bold",
        "buffer_cap",
        "buffered",
        "bullet",
        "color",
        "default_level_color",
        "document",
        "document_blocks",
        "font_size_px",
        "g",
        "health",
        "italic",
        "kind",
        "last_render_age_sec",
        "last_render_error",
        "level",
        "level_colors",
        "lines",
        "maximum_block_count",
        "maximum_height_px",
        "message",
        "pause_buffer_size",
        "paused",
        "placeholder_text",
        "plain",
        "r",
        "read_only",
        "render_errors",
        "resume",
        "resume_marker_color",
        "stage_colors",
        "stage_default_color",
        "stamp",
        "timestamp_color",
        "total_renders",
        "trade",
        "widget",
        "wire_flow",
        "wire_flow_color",
        "wire_stack",
        "wire_stack_color",
    }
)


def test_the_module_writes_no_number():
    """A text size, a maximum height, a block cap or a channel typed here
    is a second source of truth for a value the surface owns."""
    assert not MODULE_LITERALS[
        "numbers"
    ], f"status_log.js holds numeric literals: {MODULE_LITERALS['numbers']}"


def test_the_module_writes_no_colour():
    """A colour typed here drifts from the surface the next time the
    log's skin changes, and nothing reports the drift."""
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"status_log.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_log_shows():
    """A colour, a size, a message, a stamp, a bullet or the placeholder
    spelled out in the module."""
    written = sorted(set(MODULE_LITERALS["strings"]) & LOG_VALUES)
    assert not written, f"status_log.js spells out log values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    """The table the module resolves through. A token value copied here
    would be a second source of truth for the same colour."""
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"status_log.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    """Every published string the module does hold, listed. The scan
    above passes by excluding these, so they are named rather than
    silently skipped."""
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert written == NAMED_WORDS, (
        f"the module names {sorted(set(written) - set(NAMED_WORDS))} more and "
        f"{sorted(set(NAMED_WORDS) - set(written))} fewer published strings "
        "than the list allows"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_log_shows():
    """The control for the list above. A word that is also a colour, a
    size or a text the log paints does not belong on it."""
    overlap = sorted(set(NAMED_WORDS) & LOG_VALUES)
    assert not overlap, f"these named words are values the log shows: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    """The scan parses no regular expression, so a value inside one would
    pass unread. The module carries none."""
    assert not MODULE_LITERALS["slashes"], (
        "status_log.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


MIXED_LINES = payload_lines(STATE_PAYLOADS["mixed"])
WIRE_LINE = [one for one in MIXED_LINES if one["kind"] == sls.KIND_WIRE_FLOW][0]

PLANTED_LINES = {
    "colour": 'var planted = "' + MIXED_LINES[0]["color"] + '";',
    "hex": 'var planted = "#00ffcc";',
    "font_size": 'var planted = "' + str(MIXED_LINES[0]["font_size_px"]) + 'px";',
    "number": "var planted = 12;",
    "maximum_height": ('var planted = "' + str(sls.MAX_HEIGHT_PX) + 'px";'),
    "placeholder": 'var planted = "' + sls.PLACEHOLDER_TEXT + '";',
    "accessible_name": 'var planted = "' + sls.ACCESSIBLE_NAME + '";',
    "bullet": 'var planted = "' + WIRE_LINE["bullet"] + '";',
    "stamp_colour": (
        'var planted = "'
        + ", ".join(str(one) for one in STATE_PAYLOADS["mixed"]["timestamp_color"])
        + '";'
    ),
    "message": 'var planted = "' + MIXED_LINES[0]["message"] + '";',
    "token_value": 'var planted = "' + str(dss.TEXT_HIGH) + '";',
    "regex": "var planted = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the five checks above report on ``source``."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if found["numbers"]:
        caught.add("number")
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & LOG_VALUES:
        caught.add("log_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_a_planted_line(kind: str):
    """The controls for the five checks above, one plant at a time. A
    scan that reported nothing would pass a line spelling a value out."""
    caught = caught_by_scan(PLANTED_LINES[kind])
    assert caught, f"the scan reported nothing on the planted {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    """A scan that treated comments as code would report a false colour,
    and one that stopped at a comment would miss the code after it."""
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_planted_literal_is_caught_in_the_module_file_itself():
    """The scan run against the shipped file, one plant at a time.

    Each plant is appended to the real file, caught, and the file put
    back byte for byte with its hash read again. A failure here means
    either the scan reported nothing or the file was left changed.
    """
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
    silent = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert (
        not silent
    ), f"the scan reported nothing on these plants in the file: {silent}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_planted_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    """Every plant leaves the file valid JavaScript, so a page loading it
    mid-scan still defines the log module."""
    for kind, line in sorted(PLANTED_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetLog") == "function", kind


# -- 3. both sides agree, value for value and type for type ------------


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
    """A value that changes shape in transit reads correct and paints
    wrong: a number where a colour belongs paints nothing."""
    payload = state_payload(state)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json("acervatorLog.kinds()")
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
    """The control. A payload with one text where a number belongs must
    read as exactly one difference."""
    payload = state_payload("mixed")
    payload["buffer_cap"] = str(payload["buffer_cap"])
    js.push(payload)
    expected = python_kinds(state_payload("mixed"))
    actual = js.json("acervatorLog.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["buffer_cap"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_line_agrees_with_the_surface_field_for_field(js: JsRuntime, state: str):
    """The whole claim of this unit. A single disagreement means the
    React log shows a different line from the one the pane painted."""
    payload = state_payload(state)
    js.push(payload)
    for at, expected in enumerate(payload_lines(payload)):
        actual = js.named("lineAt", at)
        differing = {
            field: (expected[field], actual.get(field))
            for field in expected
            if actual.get(field) != expected[field]
        }
        assert not differing, (
            f"{state}/line {at}: {len(differing)} of {len(expected)} "
            f"values differ: {sorted(differing)}"
        )
        assert len(actual) == len(expected)


def test_the_line_value_check_names_a_changed_value(js: JsRuntime):
    """The control. Two real payloads differing by one value must not
    compare equal."""
    payload = state_payload("mixed")
    payload_lines(payload)[0]["message"] += "!"
    js.push(payload)
    expected = payload_lines(state_payload("mixed"))[0]
    actual = js.named("lineAt", 0)
    differing = sorted(f for f in expected if actual.get(f) != expected[f])
    assert differing == ["message"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_colour_table_agrees_with_the_surface(js: JsRuntime, state: str):
    """The five tables the pane colours a line from."""
    payload = state_payload(state)
    js.push(payload)
    for name, triple in payload["level_colors"].items():
        assert js.named("levelColor", name) == triple
    for name, triple in payload["stage_colors"].items():
        assert js.named("stageColor", name) == triple
    assert js.json("acervatorLog.defaultLevelColor()") == payload["default_level_color"]
    assert js.json("acervatorLog.stageDefaultColor()") == payload["stage_default_color"]
    assert js.json("acervatorLog.timestampColor()") == payload["timestamp_color"]


def test_the_colour_table_check_names_a_changed_channel(js: JsRuntime):
    """The control. A reader blind to the table would answer the same
    triple whatever was published."""
    payload = state_payload("mixed")
    payload["level_colors"]["info"] = [1, 2, 3]
    js.push(payload)
    assert js.named("levelColor", "info") == [1, 2, 3]
    assert (
        js.named("levelColor", "info") != state_payload("mixed")["level_colors"]["info"]
    )


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_line_colour_matches_the_table_its_kind_names(js: JsRuntime, state: str):
    """The surface publishes each line's colour twice: as a hex on the
    line and as three channels in the table its kind names."""
    report = js.push(state_payload(state))
    named = [one for one in report["faults"] if one["fault"] == "colour-mismatch"]
    assert not named, f"{state}: the module named {named}"


def test_the_colour_agreement_check_names_one_recoloured_line(js: JsRuntime):
    """The control. A check that compared a value to itself would report
    nothing on a line painted a colour its own table never names."""
    payload = state_payload("mixed")
    first = payload_lines(payload)[0]
    first["r"] = first["r"] + 1
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "colour-mismatch"]
    assert [one["where"] for one in named] == ["line:0"], f"the module named {named}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_two_counts_the_surface_publishes_twice_agree(js: JsRuntime, state: str):
    """``paused``, ``buffered`` and ``document_blocks`` are each
    published on the payload and again under ``health``."""
    report = js.push(state_payload(state))
    named = [one for one in report["faults"] if one["fault"] == "disagrees"]
    assert not named, f"{state}: the module named {named}"


def test_the_twice_published_check_names_one_disagreement(js: JsRuntime):
    """The control for the check above."""
    payload = state_payload("mixed")
    payload["health"]["pause_buffer_size"] = payload["buffered"] + 1
    report = js.push(payload)
    named = [one for one in report["faults"] if one["fault"] == "disagrees"]
    assert [one["field"] for one in named] == ["buffered"], f"the module named {named}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_a_whole_payload_raises_no_fault_at_all(js: JsRuntime, state: str):
    """The negative control for every fault the module can report."""
    report = js.push(state_payload(state))
    assert report["faults"] == [], f"{state}: {report['faults']}"


def test_a_name_the_payload_never_carried_is_not_a_colour(loaded: JsRuntime):
    """Every JavaScript object inherits names like ``constructor``.
    Reading one as a colour would hand the log a function where three
    channels belong."""
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        assert loaded.named("levelColor", inherited) is None
        assert loaded.named("stageColor", inherited) is None


def test_the_inherited_name_check_still_reads_a_real_colour(loaded: JsRuntime):
    """The control. A reader that answered nothing for every name would
    pass the check above while serving no colour."""
    payload = state_payload("mixed")
    assert loaded.named("levelColor", "info") == payload["level_colors"]["info"]
    assert loaded.named("stageColor", "FILLED") == payload["stage_colors"]["FILLED"]


def test_the_module_reports_only_what_it_was_given(js: JsRuntime):
    """Every value comes from the payload and none from the module. A
    batch of lines the surface never painted comes back unchanged."""
    payload = state_payload("mixed")
    invented = {"message": "given-message", "stamp": "given-stamp", "kind": "given"}
    payload["document"]["lines"] = [invented]
    js.push(payload)
    assert js.json("acervatorLog.lines()") == [invented]
    assert not set(invented.values()) & LOG_VALUES


# -- the values resolved through the token module ----------------------


def carriers_of(value: Any) -> list:
    """Every non-alias design token carrying ``value``."""
    tokens = token_payload()
    aliases = tokens["alias_targets"]
    return sorted(
        name
        for name, held in tokens["tokens"].items()
        if str(held) == str(value) and name not in aliases
    )


LOG_COLOURS = sorted({line["color"] for line in MIXED_LINES})
LOG_FONT_SIZES = sorted(
    {line["font_size_px"] for line in MIXED_LINES if line["font_size_px"] is not None}
)


def test_every_colour_the_log_paints_resolves_to_one_token(js: JsRuntime):
    """A colour is painted through the one token that holds it, so a
    token changed in Python moves the log without touching the file."""
    js.load_tokens()
    js.load_widgets()
    assert LOG_COLOURS, "the log paints no colour; the check cannot report"
    for colour in LOG_COLOURS:
        assert carriers_of(colour) == [
            js.variable_for(colour)
        ], f"{colour} is carried by {carriers_of(colour)}"


def test_a_font_size_carried_by_more_than_one_token_resolves_to_none(js: JsRuntime):
    """C77. Binding the wire font size to a token that shares its number
    with another would move the log whenever either moved."""
    js.load_tokens()
    js.load_widgets()
    value = sls.WIRE_FONT_SIZE_PX
    assert len(carriers_of(value)) > 1, f"only {carriers_of(value)} carry {value}"
    assert js.variable_for(value) is None


def test_a_font_size_no_token_carries_resolves_to_none(js: JsRuntime):
    """The trade font size and the pane's maximum height are carried by
    no token at all, so both are painted from the surface."""
    js.load_tokens()
    js.load_widgets()
    for value in (sls.TRADE_FONT_SIZE_PX, sls.MAX_HEIGHT_PX):
        assert carriers_of(value) == [], f"{value} -> {carriers_of(value)}"
        assert js.variable_for(value) is None


def test_the_stamp_colour_reaches_the_page_as_three_channels(js: JsRuntime):
    """The surface publishes the stamp colour as a triple and no token
    carries a triple, so the stamp is painted as ``rgb`` and follows no
    token rewrite."""
    js.load_tokens()
    js.load_widgets()
    payload = state_payload("mixed")
    js.push(payload)
    printed = ", ".join(str(one) for one in payload["timestamp_color"])
    assert js.variable_for(printed) is None
    assert js.json("acervatorLog.rgbOf(acervatorLog.timestampColor())") == (
        "rgb(" + printed + ")"
    )


def test_a_value_no_token_carries_resolves_to_none(js: JsRuntime):
    """The control for the resolver. A value off the table is painted
    from the surface rather than through a variable nothing answers."""
    js.load_tokens()
    js.load_widgets()
    assert js.variable_for("no-token-carries-this") is None


def test_the_resolver_reports_no_name_with_the_widget_module_off_the_page(
    js: JsRuntime,
):
    """A page that never loaded the shared widgets paints every value
    from the surface rather than through a variable nothing answers."""
    js.load_tokens()
    assert js.variable_for(str(dss.PRIMARY)) is None


def test_a_colour_resolves_through_the_theme_when_no_token_carries_it(js: JsRuntime):
    """The resolver's second table. A theme field carrying a value alone
    names it when the token table does not."""
    js.load_tokens()
    js.load_themes(theme_payload()["theme_names"][0])
    js.load_widgets()
    painted = js.json("acervatorThemes.painted()")
    alone = sorted(
        name
        for name, value in painted.items()
        if isinstance(value, str)
        and not carriers_of(value)
        and sum(1 for one in painted.values() if one == value) == 1
    )
    assert alone, "no theme field carries a value alone; the check cannot report"
    assert js.variable_for(painted[alone[0]]) == alone[0]


# -- 4. the log, drawn in the real page --------------------------------


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
                if self.js("typeof window.acervatorSetLog") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the log module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
            + ", tokens "
            + str(self.js("typeof window.acervatorSetTokens"))
            + ", widgets "
            + str(self.js("typeof window.acervatorSetWidgets"))
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


#: Every computed property read off every drawn part.
STYLE_NAMES = [
    "color",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "fontStyle",
    "whiteSpace",
    "overflowWrap",
    "maxHeight",
    "overflowY",
    "borderTopColor",
]

#: A Qt shorthand and the computed properties it settles into.
EXPANDED = {
    "color": ("color",),
    "font-size": ("fontSize",),
    "font-weight": ("fontWeight",),
    "font-style": ("fontStyle",),
}

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

#: The width the host element is given. The view is never shown, so its own
#: width is zero and every line would wrap at one character.
HOST_WIDTH_PX = 900

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = " + json.dumps(str(HOST_WIDTH_PX) + "px") + ";"
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
    "        text: own, full: el.textContent,"
    "        children: el.children.length,"
    "        width: el.getBoundingClientRect().width,"
    "        height: el.getBoundingClientRect().height,"
    "        scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)


def give_tokens(browser: Browser) -> int:
    """Put the real token table on the page and write it into the CSS.

    ``boot.js`` asks the preload bridge for the tokens, and a view loaded
    straight from disk has no bridge, so the page would otherwise resolve
    every variable to its fallback.
    """
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_log(browser: Browser, payload: dict) -> list:
    """Draw the log into the page and read every part back."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetLog(JSON.parse(window.PAYLOAD));"
        "acervatorLog.renderLog(window.HOST);"
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


def line_declarations(line: dict) -> dict:
    """The stamp and body declarations the surface wrote for one line.

    The Qt pane paints from the ``style`` attributes inside the line's
    published ``html``, which is where the surface's own colour, size,
    weight and slant are written.
    """
    found = STYLE_ATTR.findall(line["html"])
    assert len(found) == 2, f"the surface wrote {len(found)} style attributes"
    return {"stamp": found[0], "body": found[1]}


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


def js_text(value: Any) -> str:
    """One published value, spelled as JavaScript's ``String`` writes it.

    A boolean is the only shape the two languages spell apart, and every
    attribute the module writes goes through ``String``.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


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
        f"{where}: {len(differing)} of {len(expected)} declared values "
        f"differ from the surface's own: {differing}"
    )


def changed_paths(before: list, after: list) -> set:
    """Every (path, property) whose computed value moved between reads."""
    assert len(before) == len(after), "the log drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((one["path"], key))
    return moved


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    """``script-src 'self'`` admits the module. A policy that refused it
    would leave the page with no log API at all."""
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorLog") == "object"
    assert browser.js("typeof window.acervatorSetLog") == "function"
    assert browser.js("typeof window.acervatorLoadLog") == "function"


def test_the_policy_refuses_a_network_call_from_the_loaded_page(browser: Browser):
    """The control for the check above. It names the directive that
    refused, which a failed address lookup could not produce."""
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


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    """Drawing the log raises no policy violation, so nothing in the
    module reaches for the network."""
    browser.js(WATCH_VIOLATIONS)
    draw_log(browser, state_payload("mixed"))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_drawn_log_shows_every_message_the_surface_painted(browser: Browser):
    """The whole claim of this unit. Every word the operator reads off
    the log, against the text the surface produced."""
    payload = state_payload("mixed")
    parts = draw_log(browser, payload)
    shown = [one["text"] for one in at_path(parts, "log/line/body/message")]
    assert shown == [line["message"] for line in payload_lines(payload)]
    stamps = [one["text"] for one in at_path(parts, "log/line/stamp")]
    assert stamps == [line["stamp"] for line in payload_lines(payload)]
    bullets = [one["text"] for one in at_path(parts, "log/line/body/bullet")]
    assert bullets == [line["bullet"] for line in payload_lines(payload)]


def test_the_message_check_names_one_changed_line(browser: Browser):
    """The control. A read that returned the same text whatever was drawn
    would report agreement on a changed message."""
    payload = state_payload("mixed")
    payload_lines(payload)[0]["message"] += "!"
    parts = draw_log(browser, payload)
    shown = [one["text"] for one in at_path(parts, "log/line/body/message")]
    original = [line["message"] for line in payload_lines(state_payload("mixed"))]
    differing = [at for at, one in enumerate(original) if shown[at] != one]
    assert differing == [0], f"the check named {differing}"


def test_every_drawn_line_carries_the_kind_and_level_the_surface_named(
    browser: Browser,
):
    """The operator's eye reads a trade line apart from chatter by its
    colour; the kind is what carries that apart on the page."""
    payload = state_payload("mixed")
    parts = draw_log(browser, payload)
    drawn = at_path(parts, "log/line")
    assert len(drawn) == len(payload_lines(payload))
    for at, line in enumerate(payload_lines(payload)):
        assert drawn[at]["attrs"]["data-kind"] == line["kind"]
        assert drawn[at]["attrs"]["data-level"] == js_text(line["level"])
        assert drawn[at]["attrs"]["data-index"] == str(at)


def test_the_drawn_line_bodies_match_the_surface_s_own_declarations(browser: Browser):
    """R1 and C21. Every colour, size, weight and slant the log paints,
    against a bare element styled from the same declarations."""
    payload = state_payload("mixed")
    parts = draw_log(browser, payload)
    bodies = at_path(parts, "log/line/body")
    assert len(bodies) == len(payload_lines(payload))
    for at, line in enumerate(payload_lines(payload)):
        expected = probe(browser, line_declarations(line)["body"])
        assert expected, f"line {at} declared nothing; the check cannot report"
        sheet_agrees(bodies[at], expected, f"line {at} body")


def test_the_declaration_check_names_one_changed_colour(browser: Browser):
    """The control. A comparison blind to the drawn colour would report
    agreement on a line painted the wrong colour."""
    payload = state_payload("mixed")
    first = payload_lines(payload)[0]
    original = dict(first)
    first["color"] = str(dss.MAIN_BADGE_MAGENTA)
    parts = draw_log(browser, payload)
    drawn = at_path(parts, "log/line/body")[0]
    expected = probe(browser, line_declarations(original)["body"])
    differing = sorted(
        name for name, value in expected.items() if drawn["style"].get(name) != value
    )
    assert differing == ["color"], f"the check named {differing}"


def test_the_drawn_stamps_match_the_surface_s_own_declaration(browser: Browser):
    """The timestamp colour, against a bare element styled from the
    declaration the surface wrote for it."""
    payload = state_payload("mixed")
    parts = draw_log(browser, payload)
    stamps = at_path(parts, "log/line/stamp")
    expected = probe(browser, line_declarations(payload_lines(payload)[0])["stamp"])
    assert expected, "the surface declared no stamp colour"
    for at, drawn in enumerate(stamps):
        sheet_agrees(drawn, expected, f"line {at} stamp")


def test_the_stamp_colour_check_names_one_changed_channel(browser: Browser):
    """The control, and the answer to C6: the shipped stamp colour has
    three equal channels, so a channel swap is invisible. One channel
    moved on its own must be seen."""
    payload = state_payload("mixed")
    original = payload["timestamp_color"]
    assert len(set(original)) == 1, f"the stamp colour is {original}"
    payload["timestamp_color"] = [original[0], original[1], original[2] // 2]
    parts = draw_log(browser, payload)
    drawn = at_path(parts, "log/line/stamp")[0]
    expected = probe(browser, line_declarations(payload_lines(payload)[0])["stamp"])
    assert (
        drawn["style"]["color"] != expected["color"]
    ), "the drawn stamp did not move when one channel did: " + str(drawn["style"])


def test_the_drawn_log_carries_the_widget_the_surface_describes(browser: Browser):
    """The pane's accessible name, its read-only state, its block cap and
    its maximum height, read off the drawn document."""
    payload = state_payload("mixed")
    parts = draw_log(browser, payload)
    log = only(parts, "log")
    widget = payload["widget"]
    assert log["attrs"]["aria-label"] == widget["accessible_name"]
    assert log["attrs"]["aria-readonly"] == js_text(widget["read_only"])
    assert log["attrs"]["data-read-only"] == js_text(widget["read_only"])
    assert log["attrs"]["data-maximum-block-count"] == js_text(
        widget["maximum_block_count"]
    )
    assert log["style"]["maxHeight"] == str(widget["maximum_height_px"]) + "px"


def test_the_widget_check_names_a_changed_maximum_height(browser: Browser):
    """The control. A read that returned the same length whatever was
    drawn would report agreement on a changed height."""
    payload = state_payload("mixed")
    original = payload["widget"]["maximum_height_px"]
    payload["widget"]["maximum_height_px"] = original + original
    parts = draw_log(browser, payload)
    assert only(parts, "log")["style"]["maxHeight"] == str(original + original) + "px"


def test_the_drawn_log_carries_the_pause_state_and_the_counts(browser: Browser):
    """What the Activity-Log watchdog reads: the pause, the held count,
    the cap and the render counters."""
    payload = state_payload("paused")
    parts = draw_log(browser, payload)
    log = only(parts, "log")
    assert log["attrs"]["data-paused"] == js_text(payload["paused"])
    assert log["attrs"]["data-buffered"] == js_text(payload["buffered"])
    assert log["attrs"]["data-buffer-cap"] == js_text(payload["buffer_cap"])
    assert log["attrs"]["data-document-blocks"] == js_text(payload["document_blocks"])
    assert log["attrs"]["data-total-renders"] == js_text(
        payload["health"]["total_renders"]
    )
    assert log["attrs"]["data-render-errors"] == js_text(
        payload["health"]["render_errors"]
    )
    assert log["attrs"]["data-pause-buffer-size"] == js_text(
        payload["health"]["pause_buffer_size"]
    )


def test_the_pause_state_check_reads_a_running_log_as_running(browser: Browser):
    """The control. A read that returned paused for every log would pass
    the check above on a log that was never paused."""
    payload = state_payload("mixed")
    parts = draw_log(browser, payload)
    assert only(parts, "log")["attrs"]["data-paused"] == js_text(payload["paused"])
    assert payload["paused"] is False


def test_an_empty_batch_draws_the_placeholder_the_surface_names(browser: Browser):
    """A log with nothing in it shows the pane's own placeholder rather
    than an empty box the operator cannot name."""
    payload = state_payload("empty")
    parts = draw_log(browser, payload)
    assert payload_lines(payload) == []
    assert (
        only(parts, "log/placeholder")["text"] == payload["widget"]["placeholder_text"]
    )
    assert at_path(parts, "log/line") == []


def test_the_placeholder_check_reads_a_filled_log_as_filled(browser: Browser):
    """The control. A log with lines draws no placeholder."""
    parts = draw_log(browser, state_payload("mixed"))
    assert at_path(parts, "log/placeholder") == []
    assert at_path(parts, "log/line")


def test_the_resume_notice_is_drawn_in_the_order_the_pane_painted_it(browser: Browser):
    """The held lines, then the notice naming how many were held, then
    what arrived after. Out of order the operator reads a false history."""
    payload = state_payload("resumed")
    parts = draw_log(browser, payload)
    kinds = [one["attrs"]["data-kind"] for one in at_path(parts, "log/line")]
    assert kinds == [line["kind"] for line in payload_lines(payload)]
    assert sls.KIND_RESUME in kinds
    notice = [
        one
        for one in at_path(parts, "log/line")
        if one["attrs"]["data-kind"] == sls.KIND_RESUME
    ]
    assert len(notice) == 1
    assert notice[0]["attrs"]["data-stamp"] == sls.RESUME_STAMP


def test_the_resume_notice_is_drawn_slanted_and_the_others_are_not(browser: Browser):
    """The pane slants the notice so it reads apart from a bot message.
    The control is every other line in the same draw."""
    payload = state_payload("resumed")
    parts = draw_log(browser, payload)
    bodies = at_path(parts, "log/line/body")
    slanted = [one for one in bodies if one["attrs"]["data-italic"] == "true"]
    assert len(slanted) == 1
    assert slanted[0]["style"]["fontStyle"] == "italic"
    plain = [one for one in bodies if one["attrs"]["data-italic"] == "false"]
    assert plain, "no upright line to compare against"
    assert {one["style"]["fontStyle"] for one in plain} == {"normal"}


def test_a_trade_line_is_drawn_heavier_than_a_chatter_line(browser: Browser):
    """The operator picks a fill out of the log by its weight and size.
    Both come from the surface, and a plain line is the control."""
    payload = state_payload("mixed")
    parts = draw_log(browser, payload)
    bodies = at_path(parts, "log/line/body")
    heavy = [one for one in bodies if one["attrs"]["data-bold"] == "true"]
    light = [one for one in bodies if one["attrs"]["data-bold"] == "false"]
    assert heavy and light
    assert {one["style"]["fontWeight"] for one in light} == {"400"}
    assert "400" not in {one["style"]["fontWeight"] for one in heavy}
    sizes = {one["style"]["fontSize"] for one in heavy}
    assert sizes == {str(one) + "px" for one in LOG_FONT_SIZES}, f"the log drew {sizes}"


def test_the_drawn_log_follows_a_colour_token_and_nothing_else_moves(browser: Browser):
    """What proves the log resolves through the token module rather than
    copying it: the token is rewritten and only its lines move."""
    payload = state_payload("mixed")
    before = draw_log(browser, payload)
    carried = [
        at
        for at, line in enumerate(payload_lines(payload))
        if line["color"] == str(dss.PRIMARY)
    ]
    assert carried, "no line paints PRIMARY; the check cannot report"
    browser.js(
        "document.documentElement.style.setProperty('--PRIMARY', "
        + json.dumps(str(dss.MAIN_BADGE_MAGENTA))
        + ");"
    )
    after = read_parts(browser)
    moved = changed_paths(before, after)
    assert moved, "the token moved nothing at all"
    assert {key for _, key in moved} == {
        "color",
        "borderTopColor",
    }, f"an unset border colour is currentColor, so only these move: {moved}"
    assert {path for path, _ in moved} == {
        "log/line/body",
        "log/line/body/bullet",
        "log/line/body/message",
    }, f"the token moved {sorted({p for p, _ in moved})}"


def test_the_token_rewrite_moves_only_the_lines_that_carry_it(browser: Browser):
    """The other half of the check above, counted line by line: a line
    painted another colour must not move when this token does."""
    payload = state_payload("mixed")
    before = draw_log(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty('--PRIMARY', "
        + json.dumps(str(dss.MAIN_BADGE_MAGENTA))
        + ");"
    )
    after = read_parts(browser)
    carried = {line["color"] == str(dss.PRIMARY) for line in payload_lines(payload)}
    assert carried == {True, False}, "the state paints one colour only"
    for at, line in enumerate(payload_lines(payload)):
        was = at_path(before, "log/line/body")[at]["style"]["color"]
        now = at_path(after, "log/line/body")[at]["style"]["color"]
        if line["color"] == str(dss.PRIMARY):
            assert now != was, f"line {at} carries PRIMARY and did not move"
        else:
            assert now == was, f"line {at} does not carry PRIMARY and moved"


def test_the_stamp_does_not_follow_the_token_rewrite(browser: Browser):
    """The stamp colour arrives as three channels, which no token
    carries, so it is painted from the surface and never moves."""
    payload = state_payload("mixed")
    before = draw_log(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty('--CARD_METRIC_LABEL', "
        + json.dumps(str(dss.MAIN_BADGE_MAGENTA))
        + ");"
    )
    after = read_parts(browser)
    assert changed_paths(before, after) == set()


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(browser: Browser):
    """The control for the three checks above. A comparison that reported
    a difference on every read would pass them without proving
    anything."""
    before = draw_log(browser, state_payload("mixed"))
    assert changed_paths(before, read_parts(browser)) == set()


# -- 5. hostile payloads -----------------------------------------------

MARKUP_MESSAGE = '<b onclick="x()">bold</b><script>window.OWNED = true;</script>'
NEWLINE_MESSAGE = "first half\nsecond half"
LONG_MESSAGE = "L" * LONG_LINE_CHARS

#: One hostile value per row, written onto the first line of the batch,
#: and the module reader that answers for what the log then shows.
HOSTILE_LINE_VALUES = {
    "a message that is markup": ("message", MARKUP_MESSAGE),
    "a message holding a newline": ("message", NEWLINE_MESSAGE),
    "a message of 200 characters": ("message", LONG_MESSAGE),
    "a message that is a number": ("message", 12.5),
    "a message that is nothing": ("message", None),
    "a colour that is a number": ("color", 7),
    "a colour that is nothing": ("color", None),
    "a font size that is text": ("font_size_px", "14px"),
    "a stamp that is a number": ("stamp", 7),
    "a level that is a number": ("level", 7),
    "a bullet that is a number": ("bullet", 7),
    "a kind the surface never names": ("kind", "invented"),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_LINE_VALUES))
def test_the_module_carries_a_hostile_line_value_unchanged(js: JsRuntime, case: str):
    """The React log invents nothing. Whatever the surface sent for a
    line reaches the module exactly as it arrived."""
    field, value = HOSTILE_LINE_VALUES[case]
    payload = state_payload("mixed")
    payload_lines(payload)[0][field] = value
    js.push(payload)
    assert js.named("lineAt", 0)[field] == value
    assert js.json("acervatorLog.isLoaded()") is True


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_field_the_payload_omits_is_named_as_missing(js: JsRuntime, field: str):
    """The surface sent a payload with one field gone."""
    payload = state_payload("mixed")
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
def test_a_field_carrying_null_is_named_and_draws_nothing(js: JsRuntime, field: str):
    """A null is reported, not swapped for a value of the module's own."""
    payload = state_payload("mixed")
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]
    assert js.json(MODULE_READERS[field]) in (None, {}, [])


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    """The negative control for the two checks above."""
    report = js.push(state_payload("mixed"))
    kinds = [one["fault"] for one in report["faults"]]
    assert "missing" not in kinds
    assert "null" not in kinds


@pytest.mark.parametrize("channel", ("r", "g", "b"))
def test_a_channel_that_is_text_is_named_against_its_own_default(
    js: JsRuntime, channel: str
):
    """The surface publishes ``default_level_color`` as three numbers, so
    the module has a type to hold every line's channel against."""
    payload = state_payload("mixed")
    payload_lines(payload)[0][channel] = str(payload_lines(payload)[0][channel])
    report = js.push(payload)
    assert {
        "where": "line:0",
        "field": channel,
        "fault": "wrong-type",
        "detail": "string",
    } in report["faults"]


def test_a_channel_that_is_missing_is_named(js: JsRuntime):
    """A line the surface sent without a channel on it."""
    payload = state_payload("mixed")
    del payload_lines(payload)[0]["r"]
    report = js.push(payload)
    assert {
        "where": "line:0",
        "field": "r",
        "fault": "missing",
        "detail": None,
    } in report["faults"]


def test_a_message_that_is_a_number_raises_no_fault(js: JsRuntime):
    """The surface publishes no default for a message, so the module has
    no type to hold it against. It carries the number on and names the
    type it received."""
    payload = state_payload("mixed")
    payload_lines(payload)[0]["message"] = 12.5
    js.push(payload)
    assert js.named("lineAt", 0)["message"] == 12.5
    assert js.json("acervatorLog.kinds()")["document.lines.0.message"] == "number"
    named = [one["field"] for one in js.json("acervatorLog.faults()")]
    assert "message" not in named


def test_a_kind_the_surface_never_names_is_reported(js: JsRuntime):
    """A kind naming no colour table is named rather than drawn in a
    colour the module chose."""
    payload = state_payload("mixed")
    payload_lines(payload)[0]["kind"] = "invented"
    report = js.push(payload)
    assert {
        "where": "line:0",
        "field": "kind",
        "fault": "unknown-kind",
        "detail": "string",
    } in report["faults"]


def test_a_line_bold_and_slanted_at_once_is_reported(js: JsRuntime):
    """The pane never paints both, so the drawn tag carries only one.
    The module names the line rather than dropping the slant in
    silence."""
    payload = state_payload("mixed")
    payload_lines(payload)[0]["bold"] = True
    payload_lines(payload)[0]["italic"] = True
    report = js.push(payload)
    assert {
        "where": "line:0",
        "field": "bold",
        "fault": "both-emphasis",
        "detail": None,
    } in report["faults"]


def test_the_surface_never_paints_a_line_bold_and_slanted_at_once(js: JsRuntime):
    """The negative control for the check above, over every state."""
    for state in STATE_NAMES:
        for line in payload_lines(state_payload(state)):
            assert not (line["bold"] and line["italic"]), line


def test_a_batch_that_is_not_a_list_is_named(js: JsRuntime):
    """A document carrying a text where the batch belongs."""
    payload = state_payload("mixed")
    payload["document"]["lines"] = "not a list"
    report = js.push(payload)
    assert {
        "where": "document",
        "field": "lines",
        "fault": "not-a-list",
        "detail": "string",
    } in report["faults"]
    assert js.json("acervatorLog.lines()") == []


def test_a_line_that_is_not_an_object_is_named(js: JsRuntime):
    """A batch carrying a number where a line belongs."""
    payload = state_payload("mixed")
    payload["document"]["lines"] = [7]
    report = js.push(payload)
    assert {
        "where": "line:0",
        "field": None,
        "fault": "not-an-object",
        "detail": "number",
    } in report["faults"]


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    """A bridge answering with a string or a number draws nothing."""
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorLog.isLoaded()") is False
        assert js.json("acervatorLog.lines()") == []
        assert report["declared"] is None
        assert report["held"] is None
        assert [one["fault"] for one in report["faults"]] == ["not-an-object"]


NUMERIC_HOSTILES = {
    "a not-a-number font size": "P.document.lines[0].font_size_px = Number.NaN;",
    "an infinite font size": "P.document.lines[0].font_size_px = Infinity;",
    "a very large font size": "P.document.lines[0].font_size_px = 1e24;",
    "a not-a-number channel": "P.document.lines[0].r = Number.NaN;",
    "a very large channel": "P.document.lines[0].r = 1e24;",
}


@pytest.mark.parametrize("case", sorted(NUMERIC_HOSTILES))
def test_the_module_stays_loaded_on_a_number_json_cannot_spell(
    js: JsRuntime, case: str
):
    """A not-a-number and an infinity have no JSON spelling, so they are
    written onto the payload in JavaScript. The module carries them and
    reports rather than raising."""
    report = js.push_mutated(state_payload("mixed"), NUMERIC_HOSTILES[case])
    assert js.json("acervatorLog.isLoaded()") is True
    assert report["held"]["lines"] == report["declared"]["lines"]


def test_a_not_a_number_channel_is_named_as_a_colour_mismatch(js: JsRuntime):
    """C32. A not-a-number never equals itself, so the module compares
    the printed triple rather than the numbers."""
    report = js.push_mutated(
        state_payload("mixed"), "P.document.lines[0].r = Number.NaN;"
    )
    named = [one for one in report["faults"] if one["fault"] == "colour-mismatch"]
    assert [one["where"] for one in named] == ["line:0"], f"the module named {named}"


def test_a_hostile_payload_still_draws_a_log(browser: Browser):
    """Every line the payload keeps is still drawn. A module that threw
    on a hostile value would leave the operator with a blank pane."""
    payload = state_payload("mixed")
    lines = payload_lines(payload)
    lines[0]["message"] = None
    lines[1]["color"] = 7
    lines[2]["font_size_px"] = "14px"
    lines[3]["kind"] = "invented"
    parts = draw_log(browser, payload)
    assert only(parts, "log")
    assert len(at_path(parts, "log/line")) == len(lines)
    assert at_path(parts, "log/line/body/message")[0]["text"] == ""


def test_markup_in_a_message_is_drawn_as_text_and_never_run(browser: Browser):
    """A bot message carrying markup must read as the characters the
    surface sent. A log that ran it would let a message rewrite the
    page."""
    payload = state_payload("mixed")
    payload_lines(payload)[0]["message"] = MARKUP_MESSAGE
    browser.js("window.OWNED = false;")
    parts = draw_log(browser, payload)
    drawn = at_path(parts, "log/line/body/message")[0]
    assert drawn["text"] == MARKUP_MESSAGE
    assert drawn["children"] == 0, "the markup became elements on the page"
    browser.settle(SETTLE_MS)
    assert browser.js("window.OWNED") is False


def test_the_markup_check_reports_a_page_that_did_run_the_markup(browser: Browser):
    """The control. The same message written into the page as markup
    leaves elements behind and sets the flag, which is what the check
    above proves does not happen."""
    browser.js("window.OWNED = false;")
    browser.js(
        "window.PROBE_HOST = document.createElement('div');"
        "document.body.appendChild(window.PROBE_HOST);"
        "window.PROBE_HOST.innerHTML = " + json.dumps(MARKUP_MESSAGE) + ";"
    )
    assert browser.js("window.PROBE_HOST.children.length") > 0
    assert browser.js("window.PROBE_HOST.textContent") != MARKUP_MESSAGE


def test_a_message_holding_a_newline_is_carried_whole(browser: Browser):
    """The characters the surface sent reach the page. What the browser
    then does with the newline is read off the drawn line."""
    payload = state_payload("mixed")
    payload_lines(payload)[0]["message"] = NEWLINE_MESSAGE
    parts = draw_log(browser, payload)
    drawn = at_path(parts, "log/line/body/message")[0]
    assert drawn["text"] == NEWLINE_MESSAGE
    assert drawn["style"]["whiteSpace"] == "normal"


def test_a_long_message_reaches_the_page_whole_and_is_never_cut(browser: Browser):
    """A 200-character line arrives entire. The log shortens nothing."""
    payload = state_payload("mixed")
    payload_lines(payload)[0]["message"] = LONG_MESSAGE
    parts = draw_log(browser, payload)
    drawn = at_path(parts, "log/line/body/message")[0]
    assert drawn["text"] == LONG_MESSAGE
    assert len(drawn["text"]) == LONG_LINE_CHARS


def test_a_long_message_with_no_space_in_it_overflows_the_pane(browser: Browser):
    """200 characters with nothing to break on run wider than the pane.
    The log sets no breaking rule, so the pane scrolls sideways."""
    payload = state_payload("mixed")
    payload_lines(payload)[0]["message"] = LONG_MESSAGE
    parts = draw_log(browser, payload)
    log = only(parts, "log")
    assert log["scrollWidth"] > log["clientWidth"], (
        "the pane did not run wider than itself: "
        f"{log['scrollWidth']} against {log['clientWidth']}"
    )
    assert at_path(parts, "log/line/body/message")[0]["style"]["overflowWrap"] == (
        "normal"
    )


def test_a_long_message_that_has_spaces_wraps_instead_of_overflowing(
    browser: Browser,
):
    """The control for the check above, and the other half of the answer:
    the same length broken by spaces wraps and the pane stays its own
    width."""
    payload = state_payload("mixed")
    spaced = " ".join(["word"] * (LONG_LINE_CHARS // len("word ")))
    assert len(spaced) > LONG_LINE_CHARS // 2
    payload_lines(payload)[0]["message"] = spaced
    parts = draw_log(browser, payload)
    log = only(parts, "log")
    assert log["scrollWidth"] == log["clientWidth"], (
        "a spaced line still ran wide: "
        f"{log['scrollWidth']} against {log['clientWidth']}"
    )
    assert at_path(parts, "log/line/body/message")[0]["text"] == spaced


def test_the_overflow_check_reads_the_shipped_batch_as_fitting(browser: Browser):
    """The negative control. Every message the surface ships fits the
    pane's width, so the overflow read means something."""
    parts = draw_log(browser, state_payload("mixed"))
    log = only(parts, "log")
    assert log["scrollWidth"] == log["clientWidth"], log


# -- 6. the bridge ask --------------------------------------------------


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    """The module reaches Python the one way the page allows: the preload
    bridge, naming the method the surface registers."""
    js.bind_json("PAYLOAD", state_payload("mixed"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadLog();")
    drain_events()
    assert js.json("window.CALLS") == [[sls.METHOD, "{}"]]
    assert js.json("acervatorLog.isLoaded()") is True


def test_the_module_passes_a_caller_s_parameters_to_the_surface(js: JsRuntime):
    """A caller that wants the pane paused sends the word the surface
    reads."""
    js.bind_json("PAYLOAD", state_payload("paused"))
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", {"paused": True})
    js.run("acervatorLoadLog(JSON.parse(WANTED));")
    drain_events()
    assert js.json("window.CALLS") == [[sls.METHOD, '{"paused":true}']]
    assert js.json("acervatorLog.paused()") is True


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    """Several panels on one page share one answer."""
    js.bind_json("PAYLOAD", state_payload("mixed"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadLog(); acervatorLoadLog(); acervatorLoadLog();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    """The control for the check above. A counter that never incremented
    would report one call however many were made."""
    js.bind_json("PAYLOAD", state_payload("mixed"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadLog();")
    drain_events()
    js.run("acervatorLog.forget(); acervatorLoadLog();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    """A page opened without the preload script must say so, not draw an
    empty pane the operator reads as a quiet fleet."""
    js.run("acervatorLoadLog();")
    drain_events()
    assert js.json("acervatorLog.isLoaded()") is False
    assert js.json("acervatorLog.loadError()") == "the preload bridge is not present"


def test_a_refused_ask_is_not_remembered(js: JsRuntime):
    """A backend that was not running when the page opened must be
    reachable on the next ask, not left blank for the life of the page."""
    js.bind_json("PAYLOAD", state_payload("mixed"))
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadLog();"
    )
    drain_events()
    assert js.json("acervatorLog.isLoaded()") is False
    assert js.json("acervatorLog.loadError()") == "the Python backend is not running"
    js.run("acervatorLoadLog();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorLog.isLoaded()") is True


def test_the_bridge_serves_the_method_the_module_names(pane, js: JsRuntime):
    """The name the module asks for is the one the bridge registers, and
    the answer it gives is a payload the module holds whole."""
    assert pane is sls.pane_model()
    served = serialised(sls.view_model({"messages": [{"message": "from the bridge"}]}))
    js.push(served)
    assert js.json("acervatorLog.lines()") == payload_lines(served)
    assert [line["message"] for line in payload_lines(served)] == ["from the bridge"]


def test_the_page_names_the_log_module_among_its_assets():
    """The renderer loads the module that ships with the repo, not a
    second copy under ``desktop``."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("status_log.js")]
    assert len(named) == 1, f"the page names {len(named)} log modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


def test_the_page_loads_the_log_module_after_the_modules_it_uses():
    """The module resolves a colour through ``shared_widgets.js``, which
    reads ``design_tokens.js`` and ``theme_engine.js``. A page loading it
    first would paint every colour from the surface."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    order = [Path(ref).name for ref in refs]
    for needed in ("design_tokens.js", "theme_engine.js", "shared_widgets.js"):
        assert order.index(needed) < order.index("status_log.js"), order
