"""The React stat card, against the surface that describes it."""

from __future__ import annotations

import contextlib
import hashlib
import inspect
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

from src.core.privacy_mask_registry import get_privacy_mask_registry, mask_or
from src.gui.main_tabs import dashboard_stat_card_surface as dcs
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "dashboard_stat_card.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
THEMES_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
WIDGETS_PATH = REPO_ROOT / "src" / "gui" / "web" / "shared_widgets.js"
HEADER_PATH = REPO_ROOT / "src" / "gui" / "web" / "header_strip.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: The file every swap below moves over the module, one per process.
SPARE_PATH = MODULE_PATH.with_name(f"dashboard_stat_card.scan_swap.{os.getpid()}.js")
#: One lock for the whole run, so no worker reads a swapped module.
LOCK_PATH = Path(tempfile.gettempdir()) / ("acervator_dashboard_stat_card_swap.lock")
LOCK_ATTEMPTS = 400_000


@contextlib.contextmanager
def module_held(attempts: int = LOCK_ATTEMPTS):
    """Holds LOCK_PATH so one worker at a time reads or swaps the module."""
    handle = None
    for _ in range(attempts):
        try:
            handle = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
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
#: Windows denies os.replace while another worker holds the module open.
SWAP_ATTEMPTS = 2000

#: Wide enough that a never-shown view does not read every width as zero.
HOST_WIDTH_CSS = "480px"

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

DOTTED_FIELD_ID = "counter.scrummed"
REFRESH_FIELD_ID = "counter.errors"
FIELD_IDS = (DOTTED_FIELD_ID, REFRESH_FIELD_ID)

LABEL_TEXT = "Scrummed"
MONEY_TEXT = "$12,345.68"
TOOLTIP_SUFFIX = "Click to open the error log."

MASK_SPELLING = inspect.signature(mask_or).parameters["mask"].default

#: STATES holds every state the surface publishes for the card.
STATES = {
    "default": {},
    "named": {"label": LABEL_TEXT, "value": MONEY_TEXT},
    "dotted": {"label": LABEL_TEXT, "value": MONEY_TEXT, "field_id": DOTTED_FIELD_ID},
    "masked": {"label": LABEL_TEXT, "value": MONEY_TEXT, "field_id": DOTTED_FIELD_ID},
    "clickable": {
        "label": LABEL_TEXT,
        "value": MONEY_TEXT,
        "clickable": True,
        "tooltip_suffix": TOOLTIP_SUFFIX,
    },
    "refreshed": {
        "label": LABEL_TEXT,
        "value": MONEY_TEXT,
        "field_id": REFRESH_FIELD_ID,
        "refresh_dot": True,
    },
    "dotted_clickable": {
        "label": LABEL_TEXT,
        "value": MONEY_TEXT,
        "field_id": DOTTED_FIELD_ID,
        "clickable": True,
        "tooltip_suffix": TOOLTIP_SUFFIX,
    },
}
STATE_NAMES = tuple(STATES)
MASKED_STATE = "masked"


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON."""
    return json.loads(json.dumps(dcs.view_model(params), ensure_ascii=True))


def state_payload(name: str, registry: Any = None) -> dict:
    """One named state, with the mask set for it when a registry is given."""
    if registry is not None:
        for field in FIELD_IDS:
            registry.set_masked(field, name == MASKED_STATE)
    return bridge_payload(**STATES[name])


def token_payload() -> dict:
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


@pytest.fixture()
def revealed():
    """Both card fields unmasked, with the prior state put back after."""
    registry = get_privacy_mask_registry()
    prior = {field: registry.is_masked(field) for field in FIELD_IDS}
    for field in FIELD_IDS:
        registry.set_masked(field, False)
    try:
        yield registry
    finally:
        for field, was in prior.items():
            registry.set_masked(field, was)


class JsRuntime(JsEngine):
    """A QJSEngine holding the stat-card module and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetStatCard"

    def push_mutated(self, payload: Any, mutation: str) -> dict:
        """Pushes payload after mutation runs on the parsed model."""
        self.bind_json("PAYLOAD", payload)
        return self.json(
            "(function () { var model = JSON.parse(PAYLOAD); "
            + mutation
            + " return acervatorSetStatCard(model); })()"
        )

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
        self.run(HEADER_PATH.read_text(encoding="utf-8"))

    def named(self, reader: str, name: str) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorStatCard." + reader + "(JSON.parse(NAME))")

    def variable_for(self, value: Any) -> Any:
        self.bind_json("VALUE", value)
        return self.json("acervatorStatCard.variableFor(JSON.parse(VALUE))")

    def style_of(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorStatCard.styleOf(JSON.parse(SHEET))")

    def declarations(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorStatCard.declarations(JSON.parse(SHEET))")


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


@pytest.fixture()
def loaded(js: JsRuntime, revealed) -> JsRuntime:
    js.push(state_payload("named", revealed))
    return js


# -- 1. everything the surface publishes reaches the module ------------

#: Every field the surface publishes, and the module call answering it.
MODULE_READERS = {
    "actions": "acervatorStatCard.actions()",
    "bus_topics": "acervatorStatCard.busTopics()",
    "call_names": "acervatorStatCard.callNames()",
    "clickable": "acervatorStatCard.clickable()",
    "clicks": "acervatorStatCard.clicks()",
    "dot": "acervatorStatCard.dot()",
    "frame": "acervatorStatCard.frame()",
    "items": "acervatorStatCard.items()",
    "label": "acervatorStatCard.caption()",
    "label_row_items": "acervatorStatCard.labelRowItems()",
    "layout": "acervatorStatCard.layout()",
    "method": "acervatorStatCard.methodName()",
    "privacy": "acervatorStatCard.privacy()",
    "signals": "acervatorStatCard.signals()",
    "timer_delays_ms": "acervatorStatCard.timerDelays()",
    "timers": "acervatorStatCard.timers()",
    "tooltip": "acervatorStatCard.tooltip()",
    "value": "acervatorStatCard.amount()",
}


def unanswered_fields(payload: dict) -> list:
    return sorted(set(payload) - set(MODULE_READERS))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, revealed, state: str
):
    payload = state_payload(state, revealed)
    js.push(payload)
    missing = unanswered_fields(payload)
    assert not missing, f"{len(missing)} published fields have no answer: {missing}"
    extra = sorted(set(MODULE_READERS) - set(payload))
    assert not extra, f"the module answers for fields the surface has none of: {extra}"
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
    payload = dict(bridge_payload())
    payload["only_on_the_surface"] = []
    assert unanswered_fields(payload) == ["only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_answers_for():
    payload = dict(bridge_payload())
    payload.pop("items")
    extra = sorted(set(MODULE_READERS) - set(payload))
    assert extra == ["items"], f"the check named {extra}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, revealed, state: str
):
    payload = state_payload(state, revealed)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["items"] == len(payload["items"])
    assert report["held"]["items"] == len(payload["items"])
    assert report["declared"]["labelRowItems"] == len(payload["label_row_items"])
    assert report["held"]["labelRowItems"] == len(payload["label_row_items"])


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(
    js: JsRuntime, revealed
):
    payload = state_payload("named", revealed)
    del payload["items"]
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(MODULE_READERS) - 1
    assert report["held"]["items"] == 0
    assert report["declared"]["items"] == 0


def test_an_item_the_card_cannot_draw_shortens_only_the_held_item_count(
    js: JsRuntime, revealed
):
    payload = state_payload("named", revealed)
    payload["items"].append({"kind": "widget", "role": "no_such_role"})
    report = js.push(payload)
    assert report["declared"]["items"] == report["held"]["items"] + 1


def test_the_module_names_the_fields_the_surface_declares(loaded: JsRuntime):
    assert sorted(loaded.json("acervatorStatCard.declaredFields()")) == sorted(
        bridge_payload()
    )


# -- 2. no value is written in the JavaScript --------------------------


def as_css(value: Any) -> set:
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


#: The payload paths whose values skin or fill the card.
SKIN_FIELDS = ("style_sheet", "text", "default_text", "tooltip")
SIZE_FIELDS = (
    "margins_px",
    "spacing_px",
    "label_row_margins_px",
    "label_row_spacing_px",
)


def declaration_values(sheet: str) -> set:
    found = set()
    for part in re.split(r"[;{}]", str(sheet)):
        head, sep, tail = part.partition(":")
        if sep and head.strip():
            found.add(tail.strip())
    found.discard("")
    return found


def card_values() -> set:
    """Every colour, size, money text and style sheet the card paints."""
    found: set = {
        LABEL_TEXT,
        MONEY_TEXT,
        TOOLTIP_SUFFIX,
        MASK_SPELLING,
        dcs.DOT_REVEALED_GLYPH,
        dcs.DOT_MASKED_GLYPH,
        dcs.DEFAULT_VALUE,
    }

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
        walk(bridge_payload(**STATES[name]))
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
        walk(bridge_payload(**STATES[name]))
    found.discard("")
    return found


SKIN_VALUES = card_values()
TOKEN_VALUES = token_values()
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every published string NAMED_WORDS allows the module to write.
NAMED_WORDS = sorted(
    {
        "actions",
        "align",
        "bus_topics",
        "call_names",
        "clickable",
        "clicks",
        "cursor",
        "dashboard_stat_card.state",
        "default_text",
        "dot",
        "dot_align",
        "field_id",
        "frame",
        "frame_shape",
        "hcenter|bottom",
        "hcenter|top",
        "is_clickable",
        "items",
        "kind",
        "label",
        "label_row",
        "label_row_items",
        "label_row_margins_px",
        "label_row_spacing_px",
        "layout",
        "margins_px",
        "masked",
        "method",
        "privacy",
        "property",
        "role",
        "signals",
        "spacing_px",
        "stretch",
        "style_sheet",
        "text",
        "timer_delays_ms",
        "timers",
        "tooltip",
        "value",
    }
)


def test_the_module_writes_no_number():
    assert not MODULE_LITERALS["numbers"], (
        "dashboard_stat_card.js holds numeric literals: "
        f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"dashboard_stat_card.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_card_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & SKIN_VALUES)
    assert not written, f"dashboard_stat_card.js spells out card values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"dashboard_stat_card.js spells out token values: {written}"


def test_the_module_names_only_the_surface_words_it_must_read():
    written = sorted(set(MODULE_LITERALS["strings"]) & PUBLISHED_STRINGS)
    assert written == NAMED_WORDS, (
        f"the module names {sorted(set(written) - set(NAMED_WORDS))} more and "
        f"{sorted(set(NAMED_WORDS) - set(written))} fewer published strings "
        "than the list allows"
    )


def test_every_named_word_is_a_name_and_not_a_value_the_card_shows():
    overlap = sorted(set(NAMED_WORDS) & SKIN_VALUES)
    assert not overlap, f"these named words are values the card paints: {overlap}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        "dashboard_stat_card.js holds a slash outside a comment, which the "
        f"scan cannot read: {MODULE_LITERALS['slashes']}"
    )


PLANTED_LINES = {
    "colour": 'var written = "#00ffcc";',
    "margin": "var written = " + str(dcs.OUTER_MARGINS_PX[0]) + ";",
    "size_text": 'var written = "' + str(dcs.OUTER_SPACING_PX) + 'px";',
    "number": "var written = 12;",
    "money_text": 'var written = "' + MONEY_TEXT + '";',
    "default_amount": 'var written = "' + dcs.DEFAULT_VALUE + '";',
    "label_sheet": 'var written = "' + dcs.LABEL_STYLE + '";',
    "value_sheet": 'var written = "' + dcs.VALUE_STYLE + '";',
    "dot_sheet": 'var written = "' + dcs.DOT_STYLE + '";',
    "glyph": 'var written = "' + dcs.DOT_REVEALED_GLYPH + '";',
    "mask": 'var written = "' + MASK_SPELLING + '";',
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


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_one_written_value(kind: str):
    caught = caught_by_scan(PLANTED_LINES[kind])
    assert caught, f"the scan reported nothing on the written {kind}"


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def swap_module(content: bytes, attempts: int = SWAP_ATTEMPTS) -> None:
    """Puts content over the module in one atomic os.replace."""
    for _ in range(attempts):
        try:
            SPARE_PATH.write_bytes(content)
            os.replace(SPARE_PATH, MODULE_PATH)
            return
        except OSError:
            continue
    raise AssertionError(
        "another worker held "
        + MODULE_PATH.name
        + f" open for all {attempts} attempts, so it was left as it was"
    )


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
        for kind in sorted(PLANTED_LINES):
            swap_module(original + PLANTED_LINES[kind].encode("utf-8"))
            caught_each[kind] = caught_by_scan(MODULE_PATH.read_text(encoding="utf-8"))
            swap_module(original)
            after = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
            assert after == before, f"the file was not restored after {kind}"
    finally:
        swap_module(original)
        SPARE_PATH.unlink(missing_ok=True)
    return caught_each, before


def test_the_written_file_is_still_a_module_the_page_can_run(bare: JsRuntime):
    for kind, line in sorted(PLANTED_LINES.items()):
        runtime = JsRuntime(bare.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetStatCard") == "function", kind


# -- 3. both sides agree, value for value and type for type ------------


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
    js: JsRuntime, revealed, state: str
):
    payload = state_payload(state, revealed)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json("acervatorStatCard.kinds()")
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


def test_the_type_check_names_one_value_that_changed_shape(js: JsRuntime, revealed):
    payload = state_payload("named", revealed)
    payload["layout"]["spacing_px"] = str(payload["layout"]["spacing_px"])
    js.push(payload)
    expected = python_kinds(state_payload("named", revealed))
    actual = js.json("acervatorStatCard.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["layout.spacing_px"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_amount_and_the_caption_agree_with_the_surface(
    js: JsRuntime, revealed, state: str
):
    payload = state_payload(state, revealed)
    js.push(payload)
    for field, reader in (("value", "amount"), ("label", "caption")):
        expected = payload[field]
        actual = js.json("acervatorStatCard." + reader + "()")
        differing = {
            name: (expected[name], actual.get(name))
            for name in expected
            if actual.get(name) != expected[name]
        }
        assert not differing, (
            f"{state}/{field}: {len(differing)} of {len(expected)} values "
            f"differ: {sorted(differing)}"
        )
        assert len(actual) == len(expected)


def test_the_amount_check_names_a_changed_money_text(js: JsRuntime, revealed):
    payload = state_payload("named", revealed)
    payload["value"]["text"] += "0"
    js.push(payload)
    expected = state_payload("named", revealed)["value"]
    actual = js.json("acervatorStatCard.amount()")
    differing = sorted(f for f in expected if actual.get(f) != expected[f])
    assert differing == ["text"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_privacy_dot_agrees_with_the_surface(js: JsRuntime, revealed, state: str):
    payload = state_payload(state, revealed)
    js.push(payload)
    assert js.json("acervatorStatCard.dot()") == payload["dot"]


def test_a_masked_amount_reaches_the_module_masked(js: JsRuntime, revealed):
    masked = state_payload(MASKED_STATE, revealed)
    js.push(masked)
    assert js.json("acervatorStatCard.amount()")["text"] == MASK_SPELLING
    assert js.json("acervatorStatCard.dot()")["text"] == dcs.DOT_MASKED_GLYPH


def test_the_mask_check_reads_the_money_text_when_nothing_is_masked(
    js: JsRuntime, revealed
):
    js.push(state_payload("dotted", revealed))
    assert js.json("acervatorStatCard.amount()")["text"] == MONEY_TEXT
    assert js.json("acervatorStatCard.dot()")["text"] == dcs.DOT_REVEALED_GLYPH


def test_the_module_reports_only_what_it_was_given(js: JsRuntime, revealed):
    payload = state_payload("named", revealed)
    invented = {
        "text": "given-text",
        "style_sheet": "",
        "default_text": "given-default",
    }
    payload["value"] = invented
    js.push(payload)
    assert js.json("acervatorStatCard.amount()") == invented
    assert not set(invented.values()) & SKIN_VALUES


# -- the values resolved through the token module ----------------------


def carriers_of(value: Any) -> list:
    tokens = token_payload()
    aliases = tokens["alias_targets"]
    return sorted(
        name
        for name, held in tokens["tokens"].items()
        if str(held) == str(value) and name not in aliases
    )


CARD_COLOURS = sorted(
    {
        value
        for value in card_values()
        if isinstance(value, str) and HEX_COLOUR.fullmatch(value)
    }
)


def test_every_colour_the_card_paints_resolves_to_one_token(js: JsRuntime, revealed):
    assert revealed is not None
    js.load_tokens()
    assert CARD_COLOURS, "the card paints no colour; the check cannot report"
    for colour in CARD_COLOURS:
        assert carriers_of(colour) == [
            js.variable_for(colour)
        ], f"{colour} is carried by {carriers_of(colour)}"


@pytest.mark.parametrize("field", sorted(SIZE_FIELDS))
def test_no_layout_number_the_card_uses_resolves_to_a_token(
    js: JsRuntime, revealed, field: str
):
    """Every margin and spacing the card publishes is carried by two tokens."""
    js.load_tokens()
    carried = state_payload("named", revealed)["layout"][field]
    for value in carried if isinstance(carried, list) else [carried]:
        assert len(carriers_of(value)) > 1, f"{value} -> {carriers_of(value)}"
        assert js.variable_for(value) is None


def test_a_value_no_token_carries_resolves_to_none(js: JsRuntime, revealed):
    assert revealed is not None
    js.load_tokens()
    assert js.variable_for("no-token-carries-this") is None


def test_the_resolver_reports_no_name_with_the_widget_module_off_the_page(
    bare: JsRuntime, revealed
):
    assert revealed is not None
    bare.load_tokens()
    assert bare.variable_for(str(dss.PRIMARY)) is None


# -- reading one Qt style sheet ----------------------------------------


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


def card_sheets(payload: dict) -> list:
    found = [
        payload["frame"]["style_sheet"],
        payload["label"]["style_sheet"],
        payload["value"]["style_sheet"],
    ]
    if payload["dot"] is not None:
        found.append(payload["dot"]["style_sheet"])
    return found


def test_the_module_reads_the_same_declarations_as_the_surface_wrote(
    js: JsRuntime, revealed
):
    payload = state_payload("dotted", revealed)
    for sheet in card_sheets(payload):
        expected = [
            {"property": name, "value": value}
            for name, value in python_declarations(base_body(sheet))
        ]
        assert js.declarations(sheet) == expected, f"declarations differ for {sheet}"


def test_the_declaration_check_names_a_changed_value(js: JsRuntime, revealed):
    sheet = state_payload("named", revealed)["label"]["style_sheet"]
    expected = [
        {"property": name, "value": value}
        for name, value in python_declarations(base_body(sheet))
    ]
    assert js.declarations(sheet + "letter-spacing: 1px;") != expected


def test_the_module_leaves_the_dot_hover_block_out_of_the_painted_style(
    js: JsRuntime, revealed
):
    dot = state_payload("dotted", revealed)["dot"]["style_sheet"]
    painted = js.style_of(dot)
    assert str(dss.PRIMARY_BRIGHT) in json.dumps(painted)
    assert str(dss.TEXT_MAX) not in json.dumps(painted)


def test_the_module_carries_the_dot_hover_rule_the_page_cannot_paint(
    js: JsRuntime, revealed
):
    js.bind_json("SHEET", state_payload("dotted", revealed)["dot"]["style_sheet"])
    rules = js.json("acervatorStatCard.stateRules(JSON.parse(SHEET))")
    assert len(rules) == 1, f"the module found {len(rules)} state rules"
    assert str(dss.TEXT_MAX) in rules[0]["body"]


def test_the_hover_check_finds_no_rule_in_the_amount_sheet(js: JsRuntime, revealed):
    js.bind_json("SHEET", state_payload("named", revealed)["value"]["style_sheet"])
    assert js.json("acervatorStatCard.stateRules(JSON.parse(SHEET))") == []


def test_every_sheet_the_card_carries_paints_through_css(js: JsRuntime, revealed):
    report = js.push(state_payload("dotted", revealed))
    named = [f for f in report["faults"] if f["fault"] == "not-css"]
    assert named == [], f"a declaration reached no style: {named}"


def test_a_qt_only_paint_is_named_and_reaches_no_style(js: JsRuntime, revealed):
    payload = state_payload("named", revealed)
    payload["value"]["style_sheet"] += "background: qlineargradient(x1: 0, y1: 0);"
    report = js.push(payload)
    assert {
        "where": "value",
        "field": "style_sheet",
        "fault": "not-css",
        "detail": "background",
    } in report["faults"]
    assert "background" not in js.style_of(payload["value"]["style_sheet"])


def test_the_module_paints_no_style_and_names_the_missing_sheet_source(
    bare: JsRuntime, revealed
):
    report = bare.push(state_payload("dotted", revealed))
    assert {
        "where": None,
        "field": "style_sheet",
        "fault": "no-sheet-source",
        "detail": None,
    } in report["faults"]
    assert bare.style_of(state_payload("named", revealed)["value"]["style_sheet"]) == {}


def test_the_sheet_source_check_is_quiet_with_the_header_module_loaded(
    js: JsRuntime, revealed
):
    report = js.push(state_payload("dotted", revealed))
    kinds = [f["fault"] for f in report["faults"]]
    assert "no-sheet-source" not in kinds


# -- 4. the card, drawn in the real page -------------------------------


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open_page()
        self.wait_for_module()

    def open_page(self) -> None:
        """Loads index.html from disk and waits for loadFinished."""
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
                if self.js("typeof window.acervatorSetStatCard") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the stat-card module: readyState "
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
    """The page, or a skip when Chromium is not installed with Qt."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


#: Every computed property read off every drawn part.
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
    "letterSpacing",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderTopLeftRadius",
    "cursor",
]

#: A Qt shorthand and the computed properties it settles into.
EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "background": ("backgroundColor",),
    "background-color": ("backgroundColor",),
    "border-radius": ("borderTopLeftRadius",),
    "font-size": ("fontSize",),
    "font-weight": ("fontWeight",),
    "letter-spacing": ("letterSpacing",),
    "color": ("color",),
}

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = " + json.dumps(HOST_WIDTH_CSS) + ";"
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
    "        room: el.scrollWidth, text: own,"
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


def draw_card(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetStatCard(JSON.parse(window.PAYLOAD));"
        "acervatorStatCard.renderCard(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    return json.loads(browser.js(READ_PARTS))


def draw_mutated(browser: Browser, payload: dict, mutation: str) -> list:
    """Draw ``payload`` after running ``mutation`` on the parsed object."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "(function () { var model = JSON.parse(window.PAYLOAD); "
        + mutation
        + " window.SHOWN = model.value.text;"
        " acervatorSetStatCard(model);"
        " acervatorStatCard.renderCard(window.HOST); })()"
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
    assert len(before) == len(after), "the card drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((one["path"], key))
    return moved


CARD = "card"
COLUMN = "card/column"
LABEL_ROW = "card/column/label-row"
LABEL = "card/column/label-row/label"
VALUE = "card/column/value"
DOT_SLOT = "card/column/dot-slot"
DOT = "card/column/dot-slot/privacy-dot"
STRETCH = "card/column/label-row/stretch"
#: The one style node paintRules writes the frame and hover rules into.
STATE_STYLE_ID = "acervator-stat-card-states"
DOT_CLASS = "acervator-stat-card-dot"
CARD_CLASS = "acervator-stat-card"
THEME_NAME = "cyberpunk_dark"


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser, revealed):
    assert revealed is not None
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorStatCard") == "object"
    assert browser.js("typeof window.acervatorSetStatCard") == "function"
    assert browser.js("typeof window.acervatorLoadStatCard") == "function"


def test_the_policy_refuses_a_network_call_from_the_loaded_page(
    browser: Browser, revealed
):
    assert revealed is not None
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


def test_the_module_makes_no_network_call_of_its_own(browser: Browser, revealed):
    browser.js(WATCH_VIOLATIONS)
    draw_card(browser, state_payload("dotted_clickable", revealed))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_drawn_card_names_every_child_a_check_reads(browser: Browser, revealed):
    """A child with no data-part reads as an empty path to at_path."""
    parts = draw_card(browser, state_payload("dotted", revealed))
    drawn = sorted({one["path"] for one in parts})
    assert drawn == sorted(
        [CARD, COLUMN, LABEL_ROW, LABEL, STRETCH, VALUE, DOT_SLOT, DOT]
    )
    assert len(at_path(parts, STRETCH)) == 2


def test_the_named_child_check_reports_a_child_the_card_does_not_draw(
    browser: Browser, revealed
):
    payload = state_payload("named", revealed)
    parts = draw_card(browser, payload)
    assert payload["dot"] is None
    assert at_path(parts, DOT) == []


def test_the_drawn_card_places_every_item_in_the_order_the_surface_names(
    browser: Browser, revealed
):
    payload = state_payload("dotted", revealed)
    parts = draw_card(browser, payload)
    roles = [
        one["attrs"]["data-role"]
        for one in parts
        if "data-role" in one["attrs"] and one["path"].count("/") == 2
    ]
    assert roles == [item["role"] for item in payload["items"]]


def test_the_item_order_check_names_a_swapped_pair(browser: Browser, revealed):
    payload = state_payload("dotted", revealed)
    items = payload["items"]
    items[0], items[1] = items[1], items[0]
    parts = draw_card(browser, payload)
    roles = [
        one["attrs"]["data-role"]
        for one in parts
        if "data-role" in one["attrs"] and one["path"].count("/") == 2
    ]
    assert roles == [item["role"] for item in items]
    assert roles != [
        item["role"] for item in state_payload("dotted", revealed)["items"]
    ]


def test_the_drawn_card_shows_the_money_figure_the_surface_published(
    browser: Browser, revealed
):
    payload = state_payload("dotted", revealed)
    parts = draw_card(browser, payload)
    assert only(parts, VALUE)["text"] == payload["value"]["text"]
    assert only(parts, LABEL)["text"] == payload["label"]["text"]
    assert only(parts, DOT)["text"] == payload["dot"]["text"]


def test_the_money_figure_check_names_one_changed_text(browser: Browser, revealed):
    payload = state_payload("named", revealed)
    payload["value"]["text"] += "0"
    parts = draw_card(browser, payload)
    original = state_payload("named", revealed)["value"]["text"]
    assert only(parts, VALUE)["text"] != original


def test_a_masked_amount_is_drawn_masked(browser: Browser, revealed):
    payload = state_payload(MASKED_STATE, revealed)
    parts = draw_card(browser, payload)
    assert only(parts, VALUE)["text"] == MASK_SPELLING
    assert only(parts, DOT)["attrs"]["data-masked"] == "true"
    assert only(parts, DOT)["text"] == dcs.DOT_MASKED_GLYPH


def test_the_mask_check_draws_the_money_text_when_nothing_is_masked(
    browser: Browser, revealed
):
    parts = draw_card(browser, state_payload("dotted", revealed))
    assert only(parts, VALUE)["text"] == MONEY_TEXT
    assert only(parts, DOT)["attrs"]["data-masked"] == "false"


def test_the_drawn_card_matches_the_surfaces_own_style_sheets(
    browser: Browser, revealed
):
    payload = state_payload("dotted", revealed)
    parts = draw_card(browser, payload)
    sheet_agrees(
        only(parts, LABEL),
        probe(browser, base_body(payload["label"]["style_sheet"])),
        "label",
    )
    sheet_agrees(
        only(parts, VALUE),
        probe(browser, base_body(payload["value"]["style_sheet"])),
        "value",
    )
    sheet_agrees(
        only(parts, DOT),
        probe(browser, base_body(payload["dot"]["style_sheet"])),
        "dot",
    )


def test_the_style_sheet_check_names_one_changed_colour(browser: Browser, revealed):
    payload = state_payload("named", revealed)
    original = payload["value"]["style_sheet"]
    payload["value"]["style_sheet"] = original.replace(str(dss.PRIMARY), str(dss.ERROR))
    parts = draw_card(browser, payload)
    drawn = only(parts, VALUE)
    expected = probe(browser, base_body(original))
    differing = sorted(
        name for name, value in expected.items() if drawn["style"].get(name) != value
    )
    assert differing == ["color"], f"the check named {differing}"


def test_the_drawn_layout_matches_the_margins_the_surface_publishes(
    browser: Browser, revealed
):
    payload = state_payload("dotted", revealed)
    parts = draw_card(browser, payload)
    column = only(parts, COLUMN)
    margins = payload["layout"]["margins_px"]
    assert column["style"]["paddingLeft"] == pixels(margins[0])
    assert column["style"]["paddingTop"] == pixels(margins[1])
    assert column["style"]["paddingRight"] == pixels(margins[2])
    assert column["style"]["paddingBottom"] == pixels(margins[3])
    assert column["style"]["rowGap"] == pixels(payload["layout"]["spacing_px"])
    row = only(parts, LABEL_ROW)
    assert row["style"]["columnGap"] == pixels(
        payload["layout"]["label_row_spacing_px"]
    )
    assert row["style"]["paddingLeft"] == pixels(
        payload["layout"]["label_row_margins_px"][0]
    )


def test_the_layout_check_names_one_changed_margin(browser: Browser, revealed):
    payload = state_payload("named", revealed)
    original = payload["layout"]["margins_px"][1]
    payload["layout"]["margins_px"][1] = original + original
    parts = draw_card(browser, payload)
    assert only(parts, COLUMN)["style"]["paddingTop"] == pixels(original + original)


def test_the_drawn_card_takes_the_alignment_the_surface_names(
    browser: Browser, revealed
):
    payload = state_payload("dotted", revealed)
    parts = draw_card(browser, payload)
    assert payload["label"]["align"] == "hcenter|bottom"
    assert only(parts, LABEL)["style"]["justifyContent"] == "flex-end"
    assert payload["value"]["align"] == "hcenter|top"
    assert only(parts, VALUE)["style"]["justifyContent"] == "flex-start"
    assert only(parts, DOT_SLOT)["style"]["alignItems"] == "center"


def test_the_alignment_check_names_the_other_word(browser: Browser, revealed):
    payload = state_payload("named", revealed)
    payload["label"]["align"] = payload["value"]["align"]
    parts = draw_card(browser, payload)
    assert only(parts, LABEL)["style"]["justifyContent"] == "flex-start"


def test_a_clickable_card_draws_the_pointer_cursor_the_surface_names(
    browser: Browser, revealed
):
    payload = state_payload("clickable", revealed)
    parts = draw_card(browser, payload)
    card = only(parts, CARD)
    assert card["attrs"]["data-clickable"] == "true"
    assert card["style"]["cursor"] == "pointer"
    assert card["attrs"]["title"] == payload["tooltip"]


def test_a_plain_card_draws_the_arrow_cursor(browser: Browser, revealed):
    parts = draw_card(browser, state_payload("named", revealed))
    card = only(parts, CARD)
    assert card["attrs"]["data-clickable"] == "false"
    assert card["style"]["cursor"] == "default"
    assert "title" not in card["attrs"]


def test_the_drawn_card_carries_the_frame_shape_and_the_click_count(
    browser: Browser, revealed
):
    payload = state_payload("dotted", revealed)
    parts = draw_card(browser, payload)
    card = only(parts, CARD)
    assert card["attrs"]["data-frame-shape"] == payload["frame"]["frame_shape"]
    assert card["attrs"]["data-clicks"] == str(payload["clicks"])
    assert card["attrs"]["data-field-id"] == payload["privacy"]["field_id"]
    assert card["attrs"]["data-declared-items"] == str(len(payload["items"]))
    assert card["attrs"]["data-held-items"] == str(len(payload["items"]))
    assert only(parts, VALUE)["attrs"]["data-default-text"] == (
        payload["value"]["default_text"]
    )
    assert only(parts, LABEL)["attrs"]["data-property"] == payload["label"]["property"]


def test_the_drawn_card_has_a_width_to_measure(browser: Browser, revealed):
    """A never-shown view reads every width as zero."""
    parts = draw_card(browser, state_payload("dotted", revealed))
    assert only(parts, CARD)["width"] > 0
    assert only(parts, VALUE)["width"] > 0


def test_the_drawn_card_follows_a_colour_token_and_nothing_else_moves(
    browser: Browser, revealed
):
    payload = state_payload("dotted", revealed)
    before = draw_card(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty('--PRIMARY', "
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


def test_the_drawn_caption_follows_its_own_colour_token(browser: Browser, revealed):
    payload = state_payload("dotted", revealed)
    before = draw_card(browser, payload)
    browser.js(
        "document.documentElement.style.setProperty('--MAIN_CAPTION', "
        + json.dumps(str(dss.ERROR))
        + ");"
    )
    moved = changed_paths(before, read_parts(browser))
    assert {path for path, _ in moved} == {
        LABEL
    }, f"the token moved {sorted({p for p, _ in moved})}"


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(
    browser: Browser, revealed
):
    before = draw_card(browser, state_payload("dotted", revealed))
    assert changed_paths(before, read_parts(browser)) == set()


def test_no_layout_number_follows_a_token_rewrite(browser: Browser, revealed):
    """Every margin the card publishes is carried by two tokens."""
    payload = state_payload("dotted", revealed)
    before = draw_card(browser, payload)
    for name in ("--SPACE_S", "--RADIUS_SM", "--SPACE_XS", "--SPACE_XXS"):
        browser.js(
            "document.documentElement.style.setProperty("
            + json.dumps(name)
            + ", '99');"
        )
    moved = changed_paths(before, read_parts(browser))
    assert moved == set(), f"a spacing token moved the card: {sorted(moved)}"


# -- 5. hostile payloads ------------------------------------------------

#: Every hostile amount, and the JavaScript that writes it onto model.value.
HOSTILE_AMOUNTS = {
    "a true flag": "model.value.text = true;",
    "not a number": "model.value.text = NaN;",
    "an infinity": "model.value.text = Infinity;",
    "a very large integer": "model.value.text = 1e24;",
    "a number where text belongs": "model.value.text = 12.5;",
    "nothing at all": "model.value.text = null;",
    "a list where text belongs": "model.value.text = [1, 2];",
}

#: Every hostile amount the surface itself accepts, as a call parameter.
SURFACE_ACCEPTS = {
    "text where a number belongs": "1234.5",
    "a two hundred letter string": "M" * 200,
    "markup": "<script>alert(1)</script>",
    "nothing at all": None,
}

#: Every hostile amount the surface refuses, and the type it names.
SURFACE_REFUSES = {
    "a true flag": True,
    "not a number": float("nan"),
    "an infinity": float("inf"),
    "a very large integer": 10**24,
    "a number where text belongs": 12.5,
}


@pytest.mark.parametrize("case", sorted(SURFACE_REFUSES))
def test_the_surface_refuses_a_money_amount_that_is_not_text(case: str):
    with pytest.raises(TypeError) as raised:
        dcs.view_model({"label": LABEL_TEXT, "value": SURFACE_REFUSES[case]})
    assert "value" in str(raised.value)
    assert type(SURFACE_REFUSES[case]).__name__ in str(raised.value)


@pytest.mark.parametrize("case", sorted(SURFACE_ACCEPTS))
def test_the_card_shows_whatever_money_text_the_surface_produced(
    js: JsRuntime, revealed, case: str
):
    assert revealed is not None
    payload = bridge_payload(label=LABEL_TEXT, value=SURFACE_ACCEPTS[case])
    js.push(payload)
    shown = js.json("acervatorStatCard.amount()")["text"]
    assert shown == payload["value"]["text"], f"{case}: the card shows {shown}"


def test_the_money_check_reads_a_different_text_for_a_different_amount(
    js: JsRuntime, revealed
):
    assert revealed is not None
    js.push(bridge_payload(value=MONEY_TEXT))
    one = js.json("acervatorStatCard.amount()")["text"]
    js.push(bridge_payload(value=MONEY_TEXT + "0"))
    assert js.json("acervatorStatCard.amount()")["text"] != one


@pytest.mark.parametrize("case", sorted(HOSTILE_AMOUNTS))
def test_a_hostile_amount_is_named_and_carried_as_it_arrived(
    js: JsRuntime, revealed, case: str
):
    payload = state_payload("named", revealed)
    report = js.push_mutated(payload, HOSTILE_AMOUNTS[case])
    named = [f for f in report["faults"] if f["field"] == "text"]
    assert named, f"{case}: the module named nothing"
    assert named[0]["where"] == "value"
    assert named[0]["fault"] in ("wrong-type", "null")


def test_the_hostile_amount_check_is_quiet_on_a_shipped_payload(
    js: JsRuntime, revealed
):
    report = js.push(state_payload("named", revealed))
    named = [f for f in report["faults"] if f["field"] == "text"]
    assert named == [], f"a shipped amount was named: {named}"


def test_a_not_a_number_amount_cannot_cross_the_bridge_as_json():
    """The bridge writes NaN, which JSON.parse refuses, so this amount
    never reaches the module on the real page."""
    payload = bridge_payload(label=LABEL_TEXT)
    payload["value"]["text"] = float("nan")
    written = json.dumps(payload)
    assert "NaN" in written
    with pytest.raises(json.JSONDecodeError):
        json.loads(written, parse_constant=_refuse_constant)


def _refuse_constant(name: str) -> Any:
    raise json.JSONDecodeError("JSON.parse refuses " + name, name, 0)


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_field_the_payload_omits_is_named_as_missing(
    js: JsRuntime, revealed, field: str
):
    payload = state_payload("named", revealed)
    del payload[field]
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "missing",
        "detail": None,
    } in report["faults"]
    assert report["held"]["fields"] == len(MODULE_READERS) - 1


@pytest.mark.parametrize("field", sorted(set(MODULE_READERS) - {"dot"}))
def test_a_field_carrying_null_is_named(js: JsRuntime, revealed, field: str):
    payload = state_payload("named", revealed)
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_a_null_dot_is_the_surfaces_own_answer_and_is_not_named(
    js: JsRuntime, revealed
):
    payload = state_payload("named", revealed)
    assert payload["dot"] is None
    report = js.push(payload)
    assert [f for f in report["faults"] if f["field"] == "dot"] == []


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime, revealed):
    report = js.push(state_payload("dotted", revealed))
    kinds = [f["fault"] for f in report["faults"]]
    assert "missing" not in kinds
    assert "null" not in kinds


def test_a_caption_that_is_a_number_raises_no_fault_and_is_carried_on(
    js: JsRuntime, revealed
):
    """The surface publishes no default for the caption, so the module
    has no type to hold it against."""
    payload = state_payload("named", revealed)
    report = js.push_mutated(payload, "model.label.text = 7;")
    assert js.json("acervatorStatCard.caption()")["text"] == 7
    assert js.json("acervatorStatCard.kinds()")["label.text"] == "number"
    assert [f for f in report["faults"] if f["where"] == "label"] == []


def test_a_dot_without_a_field_id_is_named(js: JsRuntime, revealed):
    payload = state_payload("dotted", revealed)
    payload["privacy"]["field_id"] = None
    report = js.push(payload)
    assert {
        "where": "privacy",
        "field": "field_id",
        "fault": "dot-mismatch",
        "detail": "missing",
    } in report["faults"]


def test_a_field_id_with_no_dot_beside_it_is_named(js: JsRuntime, revealed):
    payload = state_payload("dotted", revealed)
    payload["dot"] = None
    report = js.push(payload)
    assert {
        "where": "dot",
        "field": "field_id",
        "fault": "dot-mismatch",
        "detail": "null",
    } in report["faults"]


def test_the_dot_pairing_check_is_quiet_on_both_shipped_shapes(js: JsRuntime, revealed):
    for state in ("named", "dotted"):
        report = js.push(state_payload(state, revealed))
        named = [f for f in report["faults"] if f["fault"] == "dot-mismatch"]
        assert named == [], f"{state}: {named}"


def test_an_item_naming_a_role_the_card_cannot_draw_is_named(js: JsRuntime, revealed):
    payload = state_payload("named", revealed)
    payload["items"].append({"kind": "widget", "role": "no_such_role"})
    report = js.push(payload)
    assert {
        "where": "item:2",
        "field": "role",
        "fault": "unknown-role",
        "detail": "no_such_role",
    } in report["faults"]


def test_the_item_role_check_is_quiet_on_a_whole_payload(js: JsRuntime, revealed):
    report = js.push(state_payload("dotted", revealed))
    kinds = [f["fault"] for f in report["faults"]]
    assert "unknown-role" not in kinds


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(
    js: JsRuntime, revealed
):
    assert revealed is not None
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorStatCard.isLoaded()") is False
        assert js.json("acervatorStatCard.items()") == []
        assert report["declared"] is None
        assert report["held"] is None
        assert [f["fault"] for f in report["faults"]] == ["not-an-object"]


def test_a_name_the_payload_never_carried_is_not_an_item(js: JsRuntime, revealed):
    """An inherited name such as constructor is not a published item."""
    js.push(state_payload("dotted", revealed))
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        assert js.named("item", inherited) is None


def test_the_inherited_name_check_still_answers_for_a_real_item(
    js: JsRuntime, revealed
):
    payload = state_payload("dotted", revealed)
    js.push(payload)
    assert js.named("item", "value") == payload["items"][1]
    assert js.named("item", "dot") == payload["items"][2]


def test_a_two_hundred_letter_amount_is_drawn_whole(browser: Browser, revealed):
    assert revealed is not None
    payload = bridge_payload(label=LABEL_TEXT, value=SURFACE_ACCEPTS["markup"])
    parts = draw_card(browser, payload)
    assert only(parts, VALUE)["text"] == SURFACE_ACCEPTS["markup"]
    long_payload = bridge_payload(
        label=LABEL_TEXT, value=SURFACE_ACCEPTS["a two hundred letter string"]
    )
    long_parts = draw_card(browser, long_payload)
    assert (
        only(long_parts, VALUE)["text"]
        == SURFACE_ACCEPTS["a two hundred letter string"]
    )


def test_markup_in_a_money_amount_is_drawn_as_text_and_runs_nothing(
    browser: Browser, revealed
):
    assert revealed is not None
    browser.js("window.RAN = false;")
    payload = bridge_payload(label=LABEL_TEXT, value="<img src=x onerror='RAN=true'>")
    parts = draw_card(browser, payload)
    browser.settle(SETTLE_MS)
    assert only(parts, VALUE)["text"] == payload["value"]["text"]
    assert browser.js("window.RAN") is False
    assert browser.js("window.HOST.getElementsByTagName('img').length") == 0


@pytest.mark.parametrize("case", sorted(set(HOSTILE_AMOUNTS) - {"nothing at all"}))
def test_the_drawn_card_shows_a_hostile_amount_exactly_as_javascript_prints_it(
    browser: Browser, revealed, case: str
):
    """The drawn text is the page's own String of the same value."""
    parts = draw_mutated(
        browser, state_payload("named", revealed), HOSTILE_AMOUNTS[case]
    )
    assert only(parts, VALUE)["text"] == browser.js("String(window.SHOWN)")


def test_a_null_amount_draws_no_text_at_all(browser: Browser, revealed):
    parts = draw_mutated(
        browser, state_payload("named", revealed), HOSTILE_AMOUNTS["nothing at all"]
    )
    assert only(parts, VALUE)["text"] == ""
    assert browser.js("String(window.SHOWN)") == "null"


def test_the_hostile_amount_draw_check_reads_a_shipped_money_text(
    browser: Browser, revealed
):
    parts = draw_mutated(
        browser,
        state_payload("named", revealed),
        "model.value.text = model.value.text;",
    )
    assert only(parts, VALUE)["text"] == MONEY_TEXT
    assert browser.js("String(window.SHOWN)") == MONEY_TEXT


def test_a_hostile_payload_still_draws_a_card(browser: Browser, revealed):
    payload = state_payload("dotted", revealed)
    payload["label"]["style_sheet"] = 7
    payload["layout"]["margins_px"] = None
    payload["label_row_items"] = None
    parts = draw_card(browser, payload)
    assert only(parts, CARD)
    assert only(parts, VALUE)["text"] == payload["value"]["text"]
    assert only(parts, DOT)["text"] == payload["dot"]["text"]


# -- 6. the bridge ask --------------------------------------------------


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime, revealed):
    js.bind_json("PAYLOAD", state_payload("named", revealed))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadStatCard();")
    drain_events()
    assert js.json("window.CALLS") == [[dcs.METHOD, "{}"]]
    assert js.json("acervatorStatCard.isLoaded()") is True


def test_the_module_passes_a_callers_parameters_to_the_surface(js: JsRuntime, revealed):
    js.bind_json("PAYLOAD", state_payload("dotted", revealed))
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", {"field_id": DOTTED_FIELD_ID})
    js.run("acervatorLoadStatCard(JSON.parse(WANTED));")
    drain_events()
    assert js.json("window.CALLS") == [
        [dcs.METHOD, '{"field_id":"' + DOTTED_FIELD_ID + '"}']
    ]
    assert js.json("acervatorStatCard.privacy()")["field_id"] == DOTTED_FIELD_ID


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime, revealed):
    js.bind_json("PAYLOAD", state_payload("named", revealed))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadStatCard(); acervatorLoadStatCard(); acervatorLoadStatCard();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime, revealed):
    js.bind_json("PAYLOAD", state_payload("named", revealed))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadStatCard();")
    drain_events()
    js.run("acervatorStatCard.forget(); acervatorLoadStatCard();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(
    js: JsRuntime, revealed
):
    assert revealed is not None
    js.run("acervatorLoadStatCard();")
    drain_events()
    assert js.json("acervatorStatCard.isLoaded()") is False
    assert (
        js.json("acervatorStatCard.loadError()") == "the preload bridge is not present"
    )


def test_a_refused_ask_is_not_remembered(js: JsRuntime, revealed):
    """A backend that starts later is reached on the next ask."""
    js.bind_json("PAYLOAD", state_payload("named", revealed))
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadStatCard();"
    )
    drain_events()
    assert js.json("acervatorStatCard.isLoaded()") is False
    assert (
        js.json("acervatorStatCard.loadError()") == "the Python backend is not running"
    )
    js.run("acervatorLoadStatCard();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorStatCard.isLoaded()") is True


def test_the_page_names_the_stat_card_module_among_its_assets():
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("dashboard_stat_card.js")]
    assert len(named) == 1, f"the page names {len(named)} stat-card modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH


def test_the_page_loads_the_stat_card_after_the_modules_it_resolves_through():
    """The module asks acervatorHeader and acervatorWidgets at draw time."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    order = {Path(ref).name: at for at, ref in enumerate(refs)}
    assert order["dashboard_stat_card.js"] > order["header_strip.js"]
    assert order["dashboard_stat_card.js"] > order["shared_widgets.js"]


def give_theme(browser: Browser, name: str) -> str:
    """Puts the theme table on the page and selects one theme."""
    browser.js("window.THEMES = " + json.dumps(json.dumps(theme_payload())) + ";")
    browser.js("acervatorSetThemes(JSON.parse(window.THEMES));")
    browser.js("acervatorThemes.select(" + json.dumps(name) + ");")
    return browser.js("acervatorThemes.current()")


def injected_rules(browser: Browser) -> list:
    """Every selector and declaration paintRules wrote into the page."""
    return browser.parsed(
        "(function () {"
        "  var node = document.getElementById(" + json.dumps(STATE_STYLE_ID) + ");"
        "  if (node === null) { return []; }"
        "  return Array.prototype.slice.call(node.sheet.cssRules).map("
        "    function (rule) {"
        "      return { selector: rule.selectorText, body: rule.style.cssText }; });"
        " })()"
    )


def test_the_drawn_dot_carries_the_hover_rule_qt_paints(browser: Browser, revealed):
    """The Qt dot brightens on hover, so the React dot gets the same rule."""
    payload = state_payload("dotted", revealed)
    draw_card(browser, payload)
    hover = [
        one
        for one in injected_rules(browser)
        if DOT_CLASS in str(one["selector"]) and ":hover" in str(one["selector"])
    ]
    assert len(hover) == 1, f"the page holds {len(hover)} dot hover rules"
    expected = probe(browser, hover[0]["body"])
    assert expected["color"] == probe(browser, "color: " + str(dss.TEXT_MAX))["color"]
    assert browser.js(
        "document.querySelectorAll(" + json.dumps("." + DOT_CLASS) + ").length"
    )


def test_the_hover_rule_check_reports_a_sheet_that_declares_no_hover(
    browser: Browser, revealed
):
    payload = state_payload("dotted", revealed)
    payload["dot"]["style_sheet"] = payload["value"]["style_sheet"]
    draw_card(browser, payload)
    hover = [one for one in injected_rules(browser) if ":hover" in str(one["selector"])]
    assert hover == [], f"the page holds {hover}"


def test_a_card_with_no_dot_injects_no_hover_rule(browser: Browser, revealed):
    draw_card(browser, state_payload("named", revealed))
    assert injected_rules(browser) == []


def test_the_drawn_card_takes_the_frame_skin_the_selected_theme_paints(
    browser: Browser, revealed
):
    """Qt paints QFrame[frameShape] from the theme, so the React card does."""
    payload = state_payload("dotted", revealed)
    draw_card(browser, payload)
    plain = only(parts_now(browser), CARD)["style"]["backgroundColor"]
    assert give_theme(browser, THEME_NAME) == THEME_NAME
    parts = draw_card(browser, payload)
    frame = [
        one
        for one in injected_rules(browser)
        if str(one["selector"]) == "." + CARD_CLASS
    ]
    assert len(frame) == 1, f"the page holds {len(frame)} frame rules"
    card = only(parts, CARD)
    sheet_agrees(card, probe(browser, frame[0]["body"]), "themed frame")
    assert card["style"]["backgroundColor"] != plain


def test_an_unthemed_card_paints_no_frame_skin(browser: Browser, revealed):
    """The Qt card with no theme applied paints no QSS frame either."""
    parts = draw_card(browser, state_payload("dotted", revealed))
    assert browser.parsed("acervatorThemes.current()") is None
    assert only(parts, CARD)["style"]["backgroundColor"] == "rgba(0, 0, 0, 0)"
    assert only(parts, CARD)["style"]["borderTopStyle"] == "none"


def test_the_frame_skin_the_theme_paints_carries_a_border_and_a_background(
    browser: Browser, revealed
):
    """The theme frame rule declares a background and a border."""
    assert revealed is not None
    give_theme(browser, THEME_NAME)
    draw_card(browser, state_payload("dotted", revealed))
    frame = [
        one
        for one in injected_rules(browser)
        if str(one["selector"]) == "." + CARD_CLASS
    ]
    declared = python_declarations(frame[0]["body"])
    named = sorted(name for name, _ in declared)
    assert "background-color" in named, named
    assert any(name.startswith("border") for name in named), named


def parts_now(browser: Browser) -> list:
    return read_parts(browser)


def test_a_long_money_text_is_cut_and_never_wrapped(browser: Browser, revealed):
    """A Qt QLabel never wraps, so the React amount cuts at the card edge."""
    assert revealed is not None
    short = only(draw_card(browser, bridge_payload(value=MONEY_TEXT)), VALUE)
    long_value = SURFACE_ACCEPTS["a two hundred letter string"]
    wide = only(draw_card(browser, bridge_payload(value=long_value)), VALUE)
    assert wide["text"] == long_value
    assert wide["height"] == short["height"], "the long amount wrapped onto a line"
    assert wide["room"] > wide["width"], "the long amount was not cut"


def test_the_cut_check_reads_a_short_amount_as_uncut(browser: Browser, revealed):
    assert revealed is not None
    short = only(draw_card(browser, bridge_payload(value=MONEY_TEXT)), VALUE)
    assert short["room"] == short["width"], "the short amount was cut"
