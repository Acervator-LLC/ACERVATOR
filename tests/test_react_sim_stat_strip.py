"""The React Simulator stat strip, against the surface that describes it."""

from __future__ import annotations

import contextlib
import hashlib
import json
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
from src.gui.main_tabs import sim_stat_strip_surface as sss
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "sim_stat_strip.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
THEMES_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
WIDGETS_PATH = REPO_ROOT / "src" / "gui" / "web" / "shared_widgets.js"
HEADER_PATH = REPO_ROOT / "src" / "gui" / "web" / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: One lock for the whole run, so no worker reads a swapped module.
LOCK_PATH = Path(tempfile.gettempdir()) / "acervator_sim_stat_strip_swap.lock"
LOCK_ATTEMPTS = 400_000


@contextlib.contextmanager
def module_held(attempts: int = LOCK_ATTEMPTS):
    """Holds LOCK_PATH so one worker at a time reads or swaps the module."""
    handle = None
    for _ in range(attempts):
        # Windows answers a file pending deletion with a permission error.
        try:
            handle = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except (FileExistsError, PermissionError):
            continue
    if handle is None:
        raise AssertionError(f"{LOCK_PATH} stayed taken for all {attempts} attempts")
    try:
        yield
    finally:
        os.close(handle)
        LOCK_PATH.unlink(missing_ok=True)


#: Read at collection, before any test body writes into the file.
with module_held():
    MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500
READY_ROUNDS = 100
READY_STEP_MS = 100
#: A worker swapping a page asset can cost one load, so open_page runs twice.
PAGE_ATTEMPTS = 2

#: Wide enough that a never-shown view does not read every width as zero.
HOST_WIDTH_CSS = "1400px"
#: Narrow enough that ten cells cannot fit, so the cut is measurable.
NARROW_WIDTH_CSS = "180px"

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

MONEY_TEXT = "$12,345.68"
COUNT_TEXT = "37"
OTHER_MONEY_TEXT = "$99,999.01"
UNKNOWN_FIELD = "NoSuchField"

FIELD_ORDER = tuple(sss.FIELDS)
SPENDABLE = FIELD_ORDER[0]
REALISED = FIELD_ORDER[1]
ERRORS = FIELD_ORDER[-1]

FILLED_VALUES = {
    SPENDABLE: MONEY_TEXT,
    REALISED: OTHER_MONEY_TEXT,
    ERRORS: COUNT_TEXT,
}

#: STATES holds every state the surface publishes for the strip.
STATES = {
    "fresh": {},
    "filled": {"values": dict(FILLED_VALUES)},
    "every_field": {"values": {name: COUNT_TEXT for name in FIELD_ORDER}},
    "blanked": {"values": {SPENDABLE: ""}},
    "cleared": {"clear": True},
    "cleared_then_filled": {"clear": True, "values": dict(FILLED_VALUES)},
    "unknown_field": {"values": {UNKNOWN_FIELD: MONEY_TEXT}},
}
STATE_NAMES = tuple(STATES)


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON."""
    return json.loads(json.dumps(sss.view_model(params), ensure_ascii=True))


def state_payload(name: str) -> dict:
    return bridge_payload(**STATES[name])


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


class JsRuntime(JsEngine):
    """A QJSEngine holding the strip module and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetSimStrip"

    def push_mutated(self, payload: Any, mutation: str) -> dict:
        """Pushes payload after mutation runs on the parsed model."""
        self.bind_json("PAYLOAD", payload)
        return self.json(
            "(function () { var model = JSON.parse(PAYLOAD); "
            + mutation
            + " return acervatorSetSimStrip(model); })()"
        )

    def load_tokens(self) -> None:
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_widgets(self) -> None:
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def load_header(self) -> None:
        self.run(HEADER_PATH.read_text(encoding="utf-8"))

    def named(self, method: str, name: str) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorSimStrip." + method + "(JSON.parse(NAME))")

    def style_of(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorSimStrip.styleOf(JSON.parse(SHEET))")

    def declarations_of(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorSimStrip.declarations(JSON.parse(SHEET))")

    def state_rules_of(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorSimStrip.stateRules(JSON.parse(SHEET))")


@pytest.fixture()
def bare(qapp) -> JsRuntime:
    """The module alone, with neither shared module beside it."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def js(bare: JsRuntime) -> JsRuntime:
    """Runs load_widgets and load_header beside the module."""
    bare.load_widgets()
    bare.load_header()
    return bare


#: Every field the surface publishes, and the module call answering it.
MODULE_READERS = {
    "actions": "acervatorSimStrip.actions()",
    "bus_topics": "acervatorSimStrip.busTopics()",
    "call_names": "acervatorSimStrip.callNames()",
    "cells": "acervatorSimStrip.cells()",
    "items": "acervatorSimStrip.items()",
    "layout": "acervatorSimStrip.layout()",
    "method": "acervatorSimStrip.methodName()",
    "order": "acervatorSimStrip.order()",
    "placeholder": "acervatorSimStrip.placeholder()",
    "timer_delays_ms": "acervatorSimStrip.timerDelays()",
    "timers": "acervatorSimStrip.timers()",
    "widget": "acervatorSimStrip.widget()",
}


def unanswered_fields(payload: dict) -> list:
    return sorted(set(payload) - set(MODULE_READERS))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    js.push(payload)
    missing = unanswered_fields(payload)
    assert not missing, f"{len(missing)} published fields have no answer: {missing}"
    extra = sorted(set(MODULE_READERS) - set(payload))
    assert not extra, f"the module answers for fields the surface has none of: {extra}"
    differing = {
        name: (payload[name], js.json(call))
        for name, call in MODULE_READERS.items()
        if js.json(call) != payload[name]
    }
    assert not differing, (
        f"{state}: {len(differing)} of {len(payload)} published fields "
        f"differ: {sorted(differing)}"
    )
    assert len(MODULE_READERS) == len(payload)


def test_the_whole_payload_check_names_a_field_only_the_surface_holds():
    payload = dict(bridge_payload())
    payload["only_on_the_surface"] = []
    assert unanswered_fields(payload) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for():
    payload = dict(bridge_payload())
    payload.pop("cells")
    extra = sorted(set(MODULE_READERS) - set(payload))
    assert extra == ["cells"], f"the check named {extra}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, state: str
):
    payload = state_payload(state)
    found = js.push(payload)
    assert found["declared"]["fields"] == len(MODULE_READERS)
    assert found["held"]["fields"] == len(payload)
    assert found["declared"]["cells"] == len(payload["order"])
    assert found["held"]["cells"] == len(payload["order"])
    assert found["declared"]["items"] == len(payload["items"])
    assert found["held"]["items"] == len(payload["items"])


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    payload = state_payload("filled")
    del payload["cells"]
    found = js.push(payload)
    assert found["declared"]["fields"] == len(MODULE_READERS)
    assert found["held"]["fields"] == len(MODULE_READERS) - 1
    assert found["declared"]["cells"] == len(FIELD_ORDER)
    assert found["held"]["cells"] == 0


def test_an_item_the_strip_cannot_draw_shortens_only_the_held_item_count(
    js: JsRuntime,
):
    payload = state_payload("filled")
    payload["items"].append({"kind": "widget", "field": SPENDABLE})
    found = js.push(payload)
    assert found["declared"]["items"] == found["held"]["items"] + 1


def test_the_module_names_the_fields_the_surface_declares(js: JsRuntime):
    js.push(state_payload("fresh"))
    assert sorted(js.json("acervatorSimStrip.declaredFields()")) == sorted(
        bridge_payload()
    )


def as_css(value: Any) -> set:
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


#: The payload paths whose values skin or fill the strip.
SKIN_FIELDS = ("style_sheet", "label_style", "text", "label", "placeholder")
SIZE_FIELDS = ("margins_px", "spacing_px", "cell_margins_px", "cell_spacing_px")


def declaration_values(sheet: str) -> set:
    found = set()
    for part in re.split(r"[;{}]", str(sheet)):
        head, sep, tail = part.partition(":")
        if sep and head.strip():
            found.add(tail.strip())
    found.discard("")
    return found


def strip_values() -> set:
    """Every colour, size, caption and style sheet the strip paints."""
    found: set = {
        MONEY_TEXT,
        OTHER_MONEY_TEXT,
        COUNT_TEXT,
        sss.PLACEHOLDER_TEXT,
        sss.LABEL_SUFFIX,
    }
    found |= set(FIELD_ORDER)

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


SKIN_VALUES = strip_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every published string NAMED_WORDS allows the module to write.
NAMED_WORDS = sorted(
    {
        "accessible_name",
        "actions",
        "bus_topics",
        "call_names",
        "cell",
        "cell_margins_px",
        "cell_spacing_px",
        "cells",
        "field",
        "frame_shape",
        "items",
        "kind",
        "label",
        "label_style",
        "layout",
        "margins_px",
        "method",
        "object_name",
        "order",
        "placeholder",
        "sim_stat_strip.state",
        "spacing_px",
        "stretch",
        "style_sheet",
        "text",
        "timer_delays_ms",
        "timers",
        "widget",
    }
)


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "sim_stat_strip.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"sim_stat_strip.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_strip_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & SKIN_VALUES)
    assert not written, f"sim_stat_strip.js spells out strip values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"sim_stat_strip.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert written == NAMED_WORDS, (
        f"the module names {sorted(set(written) - set(NAMED_WORDS))} more and "
        f"{sorted(set(NAMED_WORDS) - set(written))} fewer published strings "
        "than the list allows"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_strip_shows():
    overlap = sorted(set(NAMED_WORDS) & SKIN_VALUES)
    assert not overlap, f"these named words are values the strip paints: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "sim_stat_strip.js holds a slash outside a comment, which the "
        f"scan cannot read: {MODULE_LITERALS['slashes']}"
    )


WRITTEN_LINES = {
    "colour": 'var written = "' + sss.LABEL_COLOUR + '";',
    "margin": "var written = " + str(sss.STRIP_MARGINS_PX[0]) + ";",
    "size_text": 'var written = "' + str(sss.CELL_SPACING_PX) + 'px";',
    "number": "var written = 12;",
    "money_text": 'var written = "' + MONEY_TEXT + '";',
    "placeholder": 'var written = "' + sss.PLACEHOLDER_TEXT + '";',
    "label_sheet": 'var written = "' + sss.LABEL_STYLE + '";',
    "value_sheet": 'var written = "' + sss.VALUE_STYLE + '";',
    "caption": 'var written = "' + sss.label_text(SPENDABLE) + '";',
    "token_value": 'var written = "' + str(dss.PRIMARY) + '";',
    "regex": "var written = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the five scans above report on ``source``."""
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
    found = js_literals("// " + sss.LABEL_COLOUR + '\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_the_module_swap_leaves_the_file_whole_whether_or_not_it_is_held_open():
    """Windows denies os.replace over a held file and Linux allows it."""
    with module_held():
        swap_leaves_the_file_whole()


def swap_leaves_the_file_whole() -> None:
    """Swaps the module while this process holds it open for reading."""
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


def test_each_written_value_is_caught_in_the_module_file_itself():
    with module_held():
        caught_each, before = scan_each_written_value()
    unseen = sorted(k for k, caught in caught_each.items() if not caught)
    assert not unseen, f"the scan reported nothing on these lines: {unseen}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def scan_each_written_value() -> tuple:
    """Appends each written line to the module and scans the file back."""
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


def test_the_written_file_is_still_a_module_the_page_can_run(bare: JsRuntime):
    for kind, line in sorted(WRITTEN_LINES.items()):
        runtime = JsRuntime(bare.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetSimStrip") == "function", kind


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
    actual = js.json("acervatorSimStrip.kinds()")
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
    payload = state_payload("filled")
    payload["layout"]["spacing_px"] = str(payload["layout"]["spacing_px"])
    js.push(payload)
    expected = python_kinds(state_payload("filled"))
    actual = js.json("acervatorSimStrip.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["layout.spacing_px"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_cell_agrees_with_the_surface(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    for at, expected in enumerate(payload["cells"]):
        actual = js.named("cell", expected["field"])
        differing = {
            name: (expected[name], actual.get(name))
            for name in expected
            if actual.get(name) != expected[name]
        }
        assert not differing, f"{state}/{at}: {sorted(differing)}"
        assert len(actual) == len(expected)


def test_the_cell_check_names_a_changed_value_text(js: JsRuntime):
    payload = state_payload("filled")
    payload["cells"][0]["text"] += "0"
    js.push(payload)
    expected = state_payload("filled")["cells"][0]
    actual = js.named("cell", expected["field"])
    differing = sorted(f for f in expected if actual.get(f) != expected[f])
    assert differing == ["text"], f"the check named {differing}"


def test_the_module_reports_only_what_it_was_given(js: JsRuntime):
    payload = state_payload("filled")
    invented = {
        "field": SPENDABLE,
        "accessible_name": "given-name",
        "frame_shape": "given-shape",
        "label": "given-label",
        "label_style": "",
        "text": "given-text",
        "style_sheet": "",
    }
    payload["cells"][0] = invented
    js.push(payload)
    assert js.named("cell", SPENDABLE) == invented
    drawn = {invented[name] for name in ("accessible_name", "frame_shape", "label")}
    drawn.add(invented["text"])
    assert not drawn & SKIN_VALUES


@pytest.mark.parametrize("state", STATE_NAMES)
def test_an_unset_field_carries_the_published_placeholder(js: JsRuntime, state: str):
    payload = state_payload(state)
    js.push(payload)
    written = set(STATES[state].get("values") or {})
    for name in FIELD_ORDER:
        if name in written and STATES[state]["values"][name]:
            continue
        assert js.named("cell", name)["text"] == payload["placeholder"], name


def test_the_placeholder_check_reads_a_written_value_as_written(js: JsRuntime):
    js.push(state_payload("filled"))
    assert js.named("cell", SPENDABLE)["text"] == MONEY_TEXT
    assert js.json("acervatorSimStrip.placeholder()") == sss.PLACEHOLDER_TEXT


def carriers_of(value: Any) -> list:
    tokens = token_payload()
    aliases = tokens["alias_targets"]
    return sorted(
        name
        for name, held in tokens["tokens"].items()
        if str(held) == str(value) and name not in aliases
    )


STRIP_COLOURS = sorted(
    {
        value
        for value in strip_values()
        if isinstance(value, str) and HEX_COLOUR.fullmatch(value)
    }
)


def test_the_strip_paints_the_two_colours_the_surface_declares():
    assert STRIP_COLOURS == sorted({sss.LABEL_COLOUR, sss.VALUE_COLOUR})


def test_only_the_value_colour_is_carried_by_one_token():
    assert carriers_of(sss.VALUE_COLOUR) == ["TEXT_MAX"]
    assert carriers_of(sss.LABEL_COLOUR) == []


def test_no_layout_number_resolves_through_a_token_whose_name_means_a_radius():
    """Six is carried only by RADIUS_CARD, which is not a margin."""
    layout = state_payload("fresh")["layout"]
    numbers = set(layout["margins_px"]) | set(layout["cell_margins_px"])
    numbers |= {layout["spacing_px"], layout["cell_spacing_px"]}
    single = {one: carriers_of(one) for one in numbers if len(carriers_of(one)) == 1}
    assert single == {sss.STRIP_MARGINS_PX[0]: ["RADIUS_CARD"]}, single


def test_the_carrier_check_reports_a_value_no_token_carries():
    assert carriers_of("no-token-carries-this") == []


def python_declarations(body: str) -> list:
    found = []
    for part in str(body).split(";"):
        head, sep, tail = part.partition(":")
        if sep and head.strip() and tail.strip():
            found.append((head.strip(), tail.strip()))
    return found


def strip_sheets(payload: dict) -> list:
    found = []
    for one in payload["cells"]:
        found.append(one["label_style"])
        found.append(one["style_sheet"])
    return found


def test_the_module_reads_the_same_declarations_as_the_surface_wrote(js: JsRuntime):
    payload = state_payload("filled")
    for sheet in strip_sheets(payload):
        expected = [
            {"property": name, "value": value}
            for name, value in python_declarations(sheet)
        ]
        assert js.declarations_of(sheet) == expected, f"declarations differ for {sheet}"


def test_the_declaration_check_names_a_changed_value(js: JsRuntime):
    sheet = state_payload("filled")["cells"][0]["label_style"]
    expected = [
        {"property": name, "value": value} for name, value in python_declarations(sheet)
    ]
    assert js.declarations_of(sheet + "letter-spacing: 1px;") != expected


def test_neither_skin_declares_a_state_rule_the_page_would_have_to_paint(
    js: JsRuntime,
):
    """A Qt hover block would need a class rule, and the strip has none."""
    for sheet in strip_sheets(state_payload("filled")):
        assert js.state_rules_of(sheet) == []


def test_the_state_rule_check_finds_a_hover_block_when_one_is_written(js: JsRuntime):
    sheet = state_payload("fresh")["cells"][0]["label_style"]
    rules = js.state_rules_of("QLabel{" + sheet + "}QLabel:hover{" + sheet + "}")
    assert len(rules) == 1, f"the check found {len(rules)} state rules"


def test_every_sheet_the_strip_carries_paints_through_css(js: JsRuntime):
    found = js.push(state_payload("filled"))
    named = [f for f in found["faults"] if f["fault"] == "not-css"]
    assert named == [], f"a declaration reached no style: {named}"


def test_a_qt_only_paint_is_named_and_reaches_no_style(js: JsRuntime):
    payload = state_payload("filled")
    payload["cells"][0]["style_sheet"] += "background: qlineargradient(x1: 0, y1: 0);"
    found = js.push(payload)
    assert {
        "where": "cell:0",
        "field": "style_sheet",
        "fault": "not-css",
        "detail": "background",
    } in found["faults"]
    assert "background" not in js.style_of(payload["cells"][0]["style_sheet"])


def test_the_module_paints_no_style_and_names_the_missing_sheet_source(
    bare: JsRuntime,
):
    found = bare.push(state_payload("filled"))
    assert {
        "where": None,
        "field": "style_sheet",
        "fault": "no-sheet-source",
        "detail": None,
    } in found["faults"]
    assert bare.style_of(state_payload("fresh")["cells"][0]["style_sheet"]) == {}


def test_the_sheet_source_check_is_quiet_with_the_header_module_loaded(js: JsRuntime):
    found = js.push(state_payload("filled"))
    kinds = [f["fault"] for f in found["faults"]]
    assert "no-sheet-source" not in kinds


EIGHT_DIGIT = re.compile(r"#[0-9a-fA-F]{8}\b")


def eight_digit_colours(payload: dict) -> list:
    return sorted(set(EIGHT_DIGIT.findall(json.dumps(payload))))


def test_no_colour_the_surface_publishes_is_eight_digits_wide():
    """Qt reads eight hex digits as AARRGGBB and CSS as RRGGBBAA."""
    for name in STATE_NAMES:
        found = eight_digit_colours(state_payload(name))
        assert found == [], f"{name} publishes {found}"


def test_the_eight_digit_scan_reports_one_when_the_payload_carries_it():
    payload = state_payload("fresh")
    payload["cells"][0]["style_sheet"] = "color: #ff112233;"
    assert eight_digit_colours(payload) == ["#ff112233"]


def floats_in(payload: Any, path: str = "") -> list:
    found: list = []
    if isinstance(payload, bool):
        return found
    if isinstance(payload, float):
        return [path]
    if isinstance(payload, dict):
        for name, value in payload.items():
            found.extend(floats_in(value, f"{path}.{name}"))
        return found
    if isinstance(payload, list):
        for at, value in enumerate(payload):
            found.extend(floats_in(value, f"{path}.{at}"))
    return found


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_surface_publishes_no_floating_point_value_at_all(state: str):
    """A bare NaN or Infinity can only reach the page inside a float."""
    assert floats_in(state_payload(state)) == []


def test_the_float_scan_names_one_the_payload_carries():
    payload = state_payload("fresh")
    payload["layout"]["spacing_px"] = float("nan")
    assert floats_in(payload) == [".layout.spacing_px"]


@pytest.mark.parametrize("case", ["nan", "inf", "ninf"])
def test_a_not_a_number_parameter_is_refused_before_it_reaches_the_payload(case: str):
    wanted = {"nan": float("nan"), "inf": float("inf"), "ninf": float("-inf")}[case]
    with pytest.raises(TypeError) as raised:
        sss.view_model({"values": {SPENDABLE: wanted}})
    assert "float" in str(raised.value)


def test_the_json_writer_would_have_written_the_bare_word():
    """The bridge writes NaN, which JSON.parse refuses on the real page."""
    assert "NaN" in json.dumps({"spacing_px": float("nan")})
    assert "Infinity" in json.dumps({"spacing_px": float("inf")})


class Browser:
    """Browser loads the real renderer page from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open_page()
        self.wait_for_module()

    def open_page(self) -> None:
        """open_page loads index.html and waits for the page to finish."""
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
        """Spins for the module, opening the page again once it is absent."""
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.js("typeof window.acervatorSetSimStrip") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the strip module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
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
    """The page, or a skip when Chromium is not installed with Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


#: STYLE_NAMES lists every computed property read off a drawn part.
STYLE_NAMES = [
    "display",
    "flexDirection",
    "flexGrow",
    "flexShrink",
    "columnGap",
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "color",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "whiteSpace",
    "overflowX",
    "userSelect",
    "webkitUserSelect",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
]

#: EXPANDED maps a Qt shorthand to the computed properties it settles into.
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


def page_helpers(width_css: str) -> str:
    return (
        "if (window.HOST) { window.HOST.remove(); }"
        "window.HOST = document.createElement('div');"
        "window.HOST.style.width = " + json.dumps(width_css) + ";"
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
    "        width: el.clientWidth, height: el.clientHeight,"
    "        room: el.scrollWidth, left: el.getBoundingClientRect().left,"
    "        text: own,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)


def give_tokens(browser: Browser) -> int:
    """Puts the real token table on the page and into its CSS."""
    browser.js("window.TOKENS = " + json.dumps(json.dumps(token_payload())) + ";")
    written = browser.parsed(
        "(function () {"
        "  acervatorSetTokens(JSON.parse(window.TOKENS));"
        "  return acervatorTokens.apply(document.documentElement); })()"
    )
    assert written, "no design token reached the page's stylesheet"
    return len(written)


def draw_strip(
    browser: Browser, payload: dict, width_css: str = HOST_WIDTH_CSS
) -> list:
    browser.js(page_helpers(width_css))
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetSimStrip(JSON.parse(window.PAYLOAD));"
        "acervatorSimStrip.renderStrip(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    return json.loads(browser.js(READ_PARTS))


def draw_mutated(browser: Browser, payload: dict, mutation: str) -> list:
    """Draw ``payload`` after running ``mutation`` on the parsed object."""
    browser.js(page_helpers(HOST_WIDTH_CSS))
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "(function () { var model = JSON.parse(window.PAYLOAD); "
        + mutation
        + " window.SHOWN = model.cells[0].text;"
        " acervatorSetSimStrip(model);"
        " acervatorSimStrip.renderStrip(window.HOST); })()"
    )
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


def pixels(value: Any) -> str:
    return str(value) + "px"


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


def changed_paths(before: list, after: list) -> set:
    assert len(before) == len(after), "the strip drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((one["path"], key))
    return moved


STRIP = "strip"
CELL = "strip/cell"
CAPTION = "strip/cell/caption"
VALUE = "strip/cell/value"
STRETCH = "strip/stretch"
THEME_NAME = "cyberpunk_dark"


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorSimStrip") == "object"
    assert browser.js("typeof window.acervatorSetSimStrip") == "function"
    assert browser.js("typeof window.acervatorLoadSimStrip") == "function"


def test_the_policy_refuses_a_network_call_from_the_loaded_page(browser: Browser):
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
    browser.js(WATCH_VIOLATIONS)
    draw_strip(browser, state_payload("filled"))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_drawn_strip_names_every_child_a_check_reads(browser: Browser):
    parts = draw_strip(browser, state_payload("filled"))
    drawn = sorted({one["path"] for one in parts})
    assert drawn == sorted([STRIP, CELL, CAPTION, VALUE, STRETCH])
    assert len(at_path(parts, CELL)) == len(FIELD_ORDER)
    assert len(at_path(parts, STRETCH)) == 1


def test_the_named_child_check_reports_a_child_the_strip_does_not_draw(
    browser: Browser,
):
    payload = state_payload("filled")
    payload["layout"]["trailing_stretch"] = False
    payload["items"] = [one for one in payload["items"] if one["kind"] != "stretch"]
    parts = draw_strip(browser, payload)
    assert at_path(parts, STRETCH) == []
    assert len(at_path(parts, CELL)) == len(FIELD_ORDER)


def test_the_drawn_strip_carries_the_names_the_surface_publishes(browser: Browser):
    payload = state_payload("filled")
    parts = draw_strip(browser, payload)
    strip = only(parts, STRIP)
    assert strip["attrs"]["id"] == payload["widget"]["object_name"]
    assert strip["attrs"]["aria-label"] == payload["widget"]["accessible_name"]
    assert strip["attrs"]["data-declared-cells"] == str(len(payload["order"]))
    assert strip["attrs"]["data-held-cells"] == str(len(payload["order"]))
    first = at_path(parts, CELL)[0]
    assert first["attrs"]["aria-label"] == payload["cells"][0]["accessible_name"]
    assert first["attrs"]["data-frame-shape"] == payload["cells"][0]["frame_shape"]
    assert first["attrs"]["data-field"] == payload["cells"][0]["field"]


def drawn_fields(parts: list) -> list:
    return [one["attrs"]["data-field"] for one in at_path(parts, CELL)]


def drawn_texts(parts: list) -> list:
    return [one["text"] for one in at_path(parts, VALUE)]


def test_the_drawn_strip_places_the_ten_cells_in_the_published_order(
    browser: Browser,
):
    payload = state_payload("filled")
    parts = draw_strip(browser, payload)
    assert drawn_fields(parts) == payload["order"]
    assert drawn_fields(parts) == [one["field"] for one in payload["cells"]]


def test_the_cell_order_check_names_a_reordered_strip(browser: Browser):
    payload = state_payload("filled")
    items = payload["items"]
    items[0], items[1] = items[1], items[0]
    parts = draw_strip(browser, payload)
    assert drawn_fields(parts) != state_payload("filled")["order"]
    assert drawn_fields(parts)[:2] == [FIELD_ORDER[1], FIELD_ORDER[0]]


def test_the_module_names_a_published_order_the_cells_do_not_follow(js: JsRuntime):
    payload = state_payload("filled")
    payload["order"][0], payload["order"][1] = payload["order"][1], payload["order"][0]
    found = js.push(payload)
    named = [f for f in found["faults"] if f["fault"] == "order-mismatch"]
    assert len(named) == 2, f"the module named {named}"
    assert named[0]["where"] == "order.0"


def test_the_order_check_is_quiet_on_a_shipped_payload(js: JsRuntime):
    found = js.push(state_payload("filled"))
    named = [f for f in found["faults"] if f["fault"] == "order-mismatch"]
    assert named == [], f"a shipped order was named: {named}"


def test_the_drawn_strip_shows_each_field_its_own_value(browser: Browser):
    payload = state_payload("filled")
    parts = draw_strip(browser, payload)
    assert drawn_texts(parts) == [one["text"] for one in payload["cells"]]
    captions = [one["text"] for one in at_path(parts, CAPTION)]
    assert captions == [one["label"] for one in payload["cells"]]


def test_the_value_check_names_two_swapped_cell_values(browser: Browser):
    payload = state_payload("filled")
    cells = payload["cells"]
    cells[0]["text"], cells[1]["text"] = cells[1]["text"], cells[0]["text"]
    parts = draw_strip(browser, payload)
    shipped = [one["text"] for one in state_payload("filled")["cells"]]
    drawn = drawn_texts(parts)
    assert drawn != shipped
    differing = [at for at, one in enumerate(drawn) if one != shipped[at]]
    assert differing == [0, 1], f"the check named {differing}"


def test_the_drawn_strip_matches_the_surfaces_own_style_sheets(browser: Browser):
    payload = state_payload("filled")
    parts = draw_strip(browser, payload)
    for at, one in enumerate(payload["cells"]):
        sheet_agrees(
            at_path(parts, CAPTION)[at],
            probe(browser, one["label_style"]),
            f"caption {at}",
        )
        sheet_agrees(
            at_path(parts, VALUE)[at],
            probe(browser, one["style_sheet"]),
            f"value {at}",
        )


def test_the_style_sheet_check_names_one_swapped_colour_channel(browser: Browser):
    """The caption colour has three unequal channels, so a swap shows."""
    payload = state_payload("filled")
    original = payload["cells"][0]["label_style"]
    swapped = original.replace(sss.LABEL_COLOUR, channel_swapped(sss.LABEL_COLOUR))
    payload["cells"][0]["label_style"] = swapped
    parts = draw_strip(browser, payload)
    drawn = at_path(parts, CAPTION)[0]
    expected = probe(browser, original)
    differing = sorted(
        name for name, value in expected.items() if drawn["style"].get(name) != value
    )
    assert differing == ["color"], f"the check named {differing}"


def channel_swapped(colour: str) -> str:
    """The same colour with its red and blue channels exchanged."""
    body = colour.lstrip("#")
    assert len(body) == 6, colour
    return "#" + body[4:6] + body[2:4] + body[0:2]


def test_the_channel_swap_changes_the_caption_colour_and_not_the_value_colour():
    """A colour whose channels are all equal cannot show a swap."""
    assert channel_swapped(sss.LABEL_COLOUR) != sss.LABEL_COLOUR
    assert channel_swapped(sss.VALUE_COLOUR) == sss.VALUE_COLOUR


def test_the_drawn_layout_matches_the_margins_the_surface_publishes(browser: Browser):
    payload = state_payload("filled")
    parts = draw_strip(browser, payload)
    strip = only(parts, STRIP)
    margins = payload["layout"]["margins_px"]
    assert strip["style"]["paddingLeft"] == pixels(margins[0])
    assert strip["style"]["paddingTop"] == pixels(margins[1])
    assert strip["style"]["paddingRight"] == pixels(margins[2])
    assert strip["style"]["paddingBottom"] == pixels(margins[3])
    assert strip["style"]["columnGap"] == pixels(payload["layout"]["spacing_px"])
    cell = at_path(parts, CELL)[0]
    inner = payload["layout"]["cell_margins_px"]
    assert cell["style"]["paddingLeft"] == pixels(inner[0])
    assert cell["style"]["paddingTop"] == pixels(inner[1])
    assert cell["style"]["columnGap"] == pixels(payload["layout"]["cell_spacing_px"])


def test_the_layout_check_names_one_changed_margin(browser: Browser):
    payload = state_payload("filled")
    original = payload["layout"]["margins_px"][1]
    payload["layout"]["margins_px"][1] = original + original
    parts = draw_strip(browser, payload)
    assert only(parts, STRIP)["style"]["paddingTop"] == pixels(original + original)


def test_the_drawn_strip_lays_its_cells_out_left_to_right(browser: Browser):
    payload = state_payload("filled")
    parts = draw_strip(browser, payload)
    lefts = [one["left"] for one in at_path(parts, CELL)]
    assert lefts == sorted(lefts), f"the cells are not in one row: {lefts}"
    assert len(set(lefts)) == len(FIELD_ORDER)
    assert only(parts, STRIP)["style"]["flexDirection"] == "row"


def test_the_trailing_spacer_takes_the_room_the_cells_leave(browser: Browser):
    parts = draw_strip(browser, state_payload("filled"))
    assert only(parts, STRETCH)["width"] > 0
    assert only(parts, STRETCH)["style"]["flexGrow"] != "0"


def test_the_spacer_check_reads_a_cell_as_not_growing(browser: Browser):
    parts = draw_strip(browser, state_payload("filled"))
    assert at_path(parts, CELL)[0]["style"]["flexGrow"] == "0"
    assert at_path(parts, CELL)[0]["style"]["flexShrink"] == "0"


def test_a_long_value_is_cut_and_never_wrapped(browser: Browser):
    """A Qt QLabel never wraps, so the React value cuts at the cell edge."""
    payload = bridge_payload(values={SPENDABLE: "M" * 200})
    parts = draw_strip(browser, payload, width_css=NARROW_WIDTH_CSS)
    long_value = at_path(parts, VALUE)[0]
    short_value = at_path(parts, VALUE)[1]
    assert long_value["text"] == "M" * 200
    assert long_value["style"]["whiteSpace"] == "nowrap"
    assert long_value["height"] == short_value["height"], "the value wrapped"


def test_the_cut_check_reads_a_short_value_as_unwrapped(browser: Browser):
    parts = draw_strip(browser, state_payload("filled"), width_css=NARROW_WIDTH_CSS)
    value = at_path(parts, VALUE)[0]
    assert value["room"] == value["width"], "the short value was cut"


def test_the_drawn_text_cannot_be_dragged_over(browser: Browser):
    """Qt QLabel text is not selectable, so the React text refuses a drag."""
    parts = draw_strip(browser, state_payload("filled"))
    for path in (CAPTION, VALUE):
        style = at_path(parts, path)[0]["style"]
        assert (style.get("userSelect") or style.get("webkitUserSelect")) == "none"


def test_the_selection_check_reads_the_page_default_as_selectable(browser: Browser):
    browser.js(page_helpers(HOST_WIDTH_CSS))
    found = browser.parsed(
        "window.probeStyle('color: red', ['userSelect', 'webkitUserSelect'])"
    )
    assert (found.get("userSelect") or found.get("webkitUserSelect")) != "none"


def test_the_drawn_strip_has_a_width_to_measure(browser: Browser):
    """A never-shown view reads every width as zero."""
    parts = draw_strip(browser, state_payload("filled"))
    assert only(parts, STRIP)["width"] > 0
    assert at_path(parts, VALUE)[0]["width"] > 0


def test_nothing_on_the_strip_takes_keyboard_focus(browser: Browser):
    """A Qt QLabel and a plain QWidget are both NoFocus."""
    draw_strip(browser, state_payload("filled"))
    assert browser.js("window.HOST.querySelectorAll('[tabindex]').length") == 0
    assert browser.js("window.HOST.querySelectorAll('button, input, a').length") == 0


def test_the_focus_check_would_report_a_focusable_child(browser: Browser):
    browser.js(page_helpers(HOST_WIDTH_CSS))
    browser.js("window.HOST.innerHTML = '<button>x</button>';")
    assert browser.js("window.HOST.querySelectorAll('button, input, a').length") == 1


def test_the_drawn_value_follows_its_own_colour_token_and_nothing_else_moves(
    browser: Browser,
):
    payload = state_payload("filled")
    before = draw_strip(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty('--TEXT_MAX', "
        + json.dumps(str(dss.ERROR))
        + ");"
    )
    moved = changed_paths(before, read_parts(browser))
    assert moved, "the token moved nothing at all"
    assert {path for path, _ in moved} == {
        VALUE
    }, f"the token moved {sorted({p for p, _ in moved})}"
    assert {key for _, key in moved} == {
        "color",
        "borderTopColor",
    }, f"an unset border colour is currentColor, so only these move: {moved}"


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(browser: Browser):
    before = draw_strip(browser, state_payload("filled"))
    assert changed_paths(before, read_parts(browser)) == set()


def test_no_layout_number_follows_a_token_rewrite(browser: Browser):
    """One margin is carried by RADIUS_CARD alone, which means a radius."""
    before = draw_strip(browser, state_payload("filled"))
    for name in ("--RADIUS_CARD", "--SPACE_XS", "--SPACE_S", "--TYPE_SMALL"):
        browser.js(
            "document.documentElement.style.setProperty("
            + json.dumps(name)
            + ", '99');"
        )
    moved = changed_paths(before, read_parts(browser))
    assert moved == set(), f"a spacing token moved the strip: {sorted(moved)}"


def give_theme(browser: Browser, name: str) -> str:
    """Puts the theme table on the page and selects one theme."""
    browser.js("window.THEMES = " + json.dumps(json.dumps(theme_payload())) + ";")
    browser.js("acervatorSetThemes(JSON.parse(window.THEMES));")
    browser.js("acervatorThemes.select(" + json.dumps(name) + ");")
    return browser.js("acervatorThemes.current()")


def test_a_selected_theme_changes_nothing_the_strip_paints(browser: Browser):
    """Both cell skins declare their own colour, which a QSS theme cannot win."""
    payload = state_payload("filled")
    before = draw_strip(browser, payload)
    assert give_theme(browser, THEME_NAME) == THEME_NAME
    after = draw_strip(browser, payload)
    assert changed_paths(before, after) == set()


def test_the_theme_check_reads_a_theme_that_was_actually_selected(browser: Browser):
    draw_strip(browser, state_payload("filled"))
    assert browser.parsed("acervatorThemes.current()") is None
    assert give_theme(browser, THEME_NAME) == THEME_NAME
    assert browser.parsed("acervatorThemes.current()") == THEME_NAME


#: Every hostile value the surface itself accepts, as a call parameter.
SURFACE_ACCEPTS = {
    "text where a number belongs": "1234.5",
    "a two hundred letter string": "M" * 200,
    "markup": "<script>alert(1)</script>",
    "nothing at all": None,
    "an empty text": "",
}

#: Every hostile value the surface refuses, and the type it names.
SURFACE_REFUSES = {
    "a true flag": True,
    "not a number": float("nan"),
    "an infinity": float("inf"),
    "a very large integer": 10**24,
    "a number where text belongs": 12.5,
    "a list where text belongs": [1, 2],
}

#: Every hostile value, and the JavaScript that writes it onto one cell.
HOSTILE_VALUES = {
    "a true flag": "model.cells[0].text = true;",
    "not a number": "model.cells[0].text = NaN;",
    "an infinity": "model.cells[0].text = Infinity;",
    "a very large integer": "model.cells[0].text = 1e24;",
    "a number where text belongs": "model.cells[0].text = 12.5;",
    "nothing at all": "model.cells[0].text = null;",
    "a list where text belongs": "model.cells[0].text = [1, 2];",
}


@pytest.mark.parametrize("case", sorted(SURFACE_REFUSES))
def test_the_surface_refuses_a_value_that_is_not_text(case: str):
    with pytest.raises(TypeError) as raised:
        sss.view_model({"values": {SPENDABLE: SURFACE_REFUSES[case]}})
    assert type(SURFACE_REFUSES[case]).__name__ in str(raised.value)


@pytest.mark.parametrize("case", sorted(SURFACE_ACCEPTS))
def test_the_strip_shows_whatever_text_the_surface_produced(js: JsRuntime, case: str):
    payload = bridge_payload(values={SPENDABLE: SURFACE_ACCEPTS[case]})
    js.push(payload)
    shown = js.named("cell", SPENDABLE)["text"]
    assert shown == payload["cells"][0]["text"], f"{case}: the strip shows {shown}"


def test_the_shown_text_check_reads_a_different_value_as_different(js: JsRuntime):
    js.push(bridge_payload(values={SPENDABLE: MONEY_TEXT}))
    one = js.named("cell", SPENDABLE)["text"]
    js.push(bridge_payload(values={SPENDABLE: MONEY_TEXT + "0"}))
    assert js.named("cell", SPENDABLE)["text"] != one


@pytest.mark.parametrize("case", sorted(HOSTILE_VALUES))
def test_a_hostile_value_is_named_and_carried_as_it_arrived(js: JsRuntime, case: str):
    payload = state_payload("filled")
    found = js.push_mutated(payload, HOSTILE_VALUES[case])
    named = [f for f in found["faults"] if f["field"] == "text"]
    assert named, f"{case}: the module named nothing"
    assert named[0]["where"] == "cell:0"
    assert named[0]["fault"] in ("wrong-type", "null")


def test_the_hostile_value_check_is_quiet_on_a_shipped_payload(js: JsRuntime):
    found = js.push(state_payload("filled"))
    named = [f for f in found["faults"] if f["field"] == "text"]
    assert named == [], f"a shipped value was named: {named}"


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_field_the_payload_omits_is_named_as_missing(js: JsRuntime, field: str):
    payload = state_payload("filled")
    del payload[field]
    found = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "missing",
        "detail": None,
    } in found["faults"]
    assert found["held"]["fields"] == len(MODULE_READERS) - 1


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_field_carrying_null_is_named(js: JsRuntime, field: str):
    payload = state_payload("filled")
    payload[field] = None
    found = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in found["faults"]


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    found = js.push(state_payload("filled"))
    kinds = [f["fault"] for f in found["faults"]]
    assert "missing" not in kinds
    assert "null" not in kinds


@pytest.mark.parametrize("name", sorted(["accessible_name", "frame_shape", "label"]))
def test_a_cell_field_the_payload_omits_is_named_as_missing(js: JsRuntime, name: str):
    payload = state_payload("filled")
    del payload["cells"][0][name]
    found = js.push(payload)
    assert {
        "where": "cell:0",
        "field": name,
        "fault": "missing",
        "detail": None,
    } in found["faults"]


def test_a_cell_that_is_not_an_object_is_named(js: JsRuntime):
    payload = state_payload("filled")
    payload["cells"][0] = 7
    found = js.push(payload)
    assert {
        "where": "cell:0",
        "field": "cells",
        "fault": "wrong-type",
        "detail": "number",
    } in found["faults"]


def test_an_item_naming_a_kind_the_strip_cannot_draw_is_named(js: JsRuntime):
    payload = state_payload("filled")
    payload["items"].append({"kind": "widget"})
    found = js.push(payload)
    assert {
        "where": "item:11",
        "field": "kind",
        "fault": "unknown-kind",
        "detail": "widget",
    } in found["faults"]


def test_an_item_naming_a_field_no_cell_carries_is_named(js: JsRuntime):
    payload = state_payload("filled")
    payload["items"][0]["field"] = UNKNOWN_FIELD
    found = js.push(payload)
    assert {
        "where": "item:0",
        "field": "field",
        "fault": "unknown-field",
        "detail": "string",
    } in found["faults"]


def test_the_item_check_is_quiet_on_a_whole_payload(js: JsRuntime):
    found = js.push(state_payload("filled"))
    kinds = [f["fault"] for f in found["faults"]]
    assert "unknown-kind" not in kinds
    assert "unknown-field" not in kinds


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    for wrong in ("a string", 7, None, ["a", "list"]):
        found = js.push(wrong)
        assert js.json("acervatorSimStrip.isLoaded()") is False
        assert js.json("acervatorSimStrip.cells()") == []
        assert found["declared"] is None
        assert found["held"] is None
        assert [f["fault"] for f in found["faults"]] == ["not-an-object"]


def test_a_name_the_payload_never_carried_is_not_a_cell(js: JsRuntime):
    """An inherited name such as constructor is not a published field."""
    js.push(state_payload("filled"))
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        assert js.named("cell", inherited) is None


def test_the_inherited_name_check_still_answers_for_a_real_field(js: JsRuntime):
    payload = state_payload("filled")
    js.push(payload)
    assert js.named("cell", SPENDABLE) == payload["cells"][0]


def test_a_two_hundred_letter_value_is_drawn_whole(browser: Browser):
    long_value = SURFACE_ACCEPTS["a two hundred letter string"]
    payload = bridge_payload(values={SPENDABLE: long_value})
    parts = draw_strip(browser, payload)
    assert at_path(parts, VALUE)[0]["text"] == long_value


def test_markup_in_a_value_is_drawn_as_text_and_runs_nothing(browser: Browser):
    """Qt renders caller text as markup and this page refuses to."""
    browser.js("window.RAN = false;")
    payload = bridge_payload(values={SPENDABLE: "<img src=x onerror='RAN=true'>"})
    parts = draw_strip(browser, payload)
    browser.settle(SETTLE_MS)
    assert at_path(parts, VALUE)[0]["text"] == payload["cells"][0]["text"]
    assert browser.js("window.RAN") is False
    assert browser.js("window.HOST.getElementsByTagName('img').length") == 0


def test_the_markup_check_reads_a_plain_value_as_plain(browser: Browser):
    browser.js("window.RAN = false;")
    parts = draw_strip(browser, bridge_payload(values={SPENDABLE: MONEY_TEXT}))
    assert at_path(parts, VALUE)[0]["text"] == MONEY_TEXT
    assert browser.js("window.HOST.getElementsByTagName('img').length") == 0


@pytest.mark.parametrize("case", sorted(set(HOSTILE_VALUES) - {"nothing at all"}))
def test_the_drawn_strip_shows_a_hostile_value_as_javascript_prints_it(
    browser: Browser, case: str
):
    """The drawn text is the page's own String of the same value."""
    parts = draw_mutated(browser, state_payload("filled"), HOSTILE_VALUES[case])
    assert at_path(parts, VALUE)[0]["text"] == browser.js("String(window.SHOWN)")


def test_a_null_value_draws_no_text_at_all(browser: Browser):
    parts = draw_mutated(
        browser, state_payload("filled"), HOSTILE_VALUES["nothing at all"]
    )
    assert at_path(parts, VALUE)[0]["text"] == ""
    assert browser.js("String(window.SHOWN)") == "null"


def test_the_hostile_draw_check_reads_a_shipped_value(browser: Browser):
    parts = draw_mutated(
        browser, state_payload("filled"), "model.cells[0].text = model.cells[0].text;"
    )
    assert at_path(parts, VALUE)[0]["text"] == MONEY_TEXT
    assert browser.js("String(window.SHOWN)") == MONEY_TEXT


def test_a_hostile_payload_still_draws_a_strip(browser: Browser):
    payload = state_payload("filled")
    payload["cells"][0]["label_style"] = 7
    payload["layout"]["margins_px"] = None
    payload["widget"] = None
    parts = draw_strip(browser, payload)
    assert only(parts, STRIP)
    assert len(at_path(parts, CELL)) == len(FIELD_ORDER)
    assert at_path(parts, VALUE)[0]["text"] == payload["cells"][0]["text"]


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("fresh"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadSimStrip();")
    drain_events()
    assert js.json("window.CALLS") == [[sss.METHOD, "{}"]]
    assert js.json("acervatorSimStrip.isLoaded()") is True


def test_the_module_passes_a_callers_parameters_to_the_surface(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("cleared"))
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", {"clear": True})
    js.run("acervatorLoadSimStrip(JSON.parse(WANTED));")
    drain_events()
    assert js.json("window.CALLS") == [[sss.METHOD, '{"clear":true}']]
    assert js.json("acervatorSimStrip.callNames()") == list(sss.CALL_NAMES)


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("fresh"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadSimStrip(); acervatorLoadSimStrip(); acervatorLoadSimStrip();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("fresh"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadSimStrip();")
    drain_events()
    js.run("acervatorSimStrip.forget(); acervatorLoadSimStrip();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadSimStrip();")
    drain_events()
    assert js.json("acervatorSimStrip.isLoaded()") is False
    assert (
        js.json("acervatorSimStrip.loadError()") == "the preload bridge is not present"
    )


def test_a_refused_ask_is_not_remembered(js: JsRuntime):
    """A backend that starts later is reached on the next ask."""
    js.bind_json("PAYLOAD", state_payload("fresh"))
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadSimStrip();"
    )
    drain_events()
    assert js.json("acervatorSimStrip.isLoaded()") is False
    assert (
        js.json("acervatorSimStrip.loadError()") == "the Python backend is not running"
    )
    js.run("acervatorLoadSimStrip();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorSimStrip.isLoaded()") is True


def test_the_page_names_the_strip_module_among_its_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("sim_stat_strip.js")]
    assert len(named) == 1, f"the page names {len(named)} strip modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


def test_the_page_loads_the_strip_after_the_module_it_resolves_through():
    """The module asks acervatorHeader for the Qt sheet grammar at draw time."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    order = {Path(ref).name: at for at, ref in enumerate(refs)}
    assert order["sim_stat_strip.js"] > order["header_strip.js"]
