"""The React header strip, against the surface that describes it.

WHAT IS PROVED
==============
``src/gui/web/header_strip.js`` draws the strip across the top of the
main window that ``src/gui/main_tabs/header_strip_surface.py`` describes,
and carries no colour, size or text of its own. The strip shows money,
so the value agreement, the rendered read-back and the no-literals scan
are three halves of one claim.

A value carried by exactly one non-alias design token is painted as that
CSS variable through ``shared_widgets.js``, never copied. A value carried
by more than one token is painted from the surface.

HOW THE JAVASCRIPT IS RUN
=========================
Node is not installed and nothing here adds a JavaScript test runner.
``QJSEngine`` from ``PySide6.QtQml`` runs the module as plain JavaScript
and answers in JSON. ``QWebEngineView`` loads the real
``desktop/renderer/index.html`` from disk, which is the only way to draw
the strip with the vendored React under the page's own policy.

THE CONTROLS
============
Every count has a planted opposite that must be named. A colour, a size,
a money text and a whole style sheet planted in the module file itself
are each caught by the literal scan, and the file is restored byte for
byte with its hash read back. One changed value proves the rendered
read-back can report, and a token rewritten on the page proves the strip
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

from src.core.privacy_mask_registry import get_privacy_mask_registry
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import header_strip_surface as hss
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "header_strip.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
THEMES_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
WIDGETS_PATH = REPO_ROOT / "src" / "gui" / "web" / "shared_widgets.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body can plant into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500
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

FIELD_IDS = tuple(column["field_id"] for column in hss.KPI_COLUMNS) + tuple(
    card["field_id"] for card in hss.COUNTER_CARDS
)

COLUMN_KEYS = tuple(column["key"] for column in hss.KPI_COLUMNS)
COUNTER_KEYS = tuple(card["key"] for card in hss.COUNTER_CARDS)

FILLED_STATS = {
    "total_scrummed_usd": 12345.678,
    "total_folded_usd": 987.65,
    "total_trades": 41,
    "running": 7,
    "total_errors_lifetime": 3,
    "total_realised_pnl": -12.5,
    "wallet_cash_usd": 500.25,
    "crypto_position_value_usd": 8100.5,
}

#: The states the surface publishes, each driven through the bridge.
STATES = {
    "default": {},
    "filled": {"stats": FILLED_STATS, "exchange_count": 3},
    "stock": {"stats": FILLED_STATS, "mode": "stock"},
    "isolated": {"stats": FILLED_STATS, "tab_name": hss.ISOLATED_TABS[0]},
    "negative": {"profits": {"spendable": -42.5, "exchange_count": 2}},
    "unknown_spendable": {"profits": {"spendable": None}},
}
STATE_NAMES = tuple(STATES)


# -- the surface, as the bridge serialises it --------------------------


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON.

    ``src/core/desktop_bridge.py`` writes every response with
    ``json.dumps(..., ensure_ascii=True)``, so a tuple reaches the
    renderer as an array.
    """
    return json.loads(json.dumps(hss.view_model(params), ensure_ascii=True))


def state_payload(name: str) -> dict:
    return bridge_payload(**STATES[name])


def token_payload() -> dict:
    """The design-token surface's answer, for the variable resolver."""
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    """The theme surface's answer, the resolver's second table."""
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


@pytest.fixture()
def revealed():
    """Every strip field unmasked, with the prior state put back after."""
    registry = get_privacy_mask_registry()
    prior = {field: registry.is_masked(field) for field in FIELD_IDS}
    for field in FIELD_IDS:
        registry.set_masked(field, False)
    try:
        yield registry
    finally:
        for field, was in prior.items():
            registry.set_masked(field, was)


# -- the JavaScript engine ---------------------------------------------


class JsRuntime(JsEngine):
    """A QJSEngine holding ``header_strip.js`` and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetHeader"

    def load_tokens(self) -> None:
        """Run unit 1's module and give it the real token table."""
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_themes(self, name: str) -> None:
        """Run unit 2's module and select one theme."""
        self.run(THEMES_PATH.read_text(encoding="utf-8"))
        self.bind_json("THEMES", theme_payload())
        self.bind_json("THEME_NAME", name)
        self.run("acervatorSetThemes(JSON.parse(THEMES));")
        self.run("acervatorThemes.select(JSON.parse(THEME_NAME));")

    def load_widgets(self) -> None:
        """Run unit 3's module, which owns the one-carrier rule."""
        self.run(WIDGETS_PATH.read_text(encoding="utf-8"))

    def named(self, reader: str, name: str) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorHeader." + reader + "(JSON.parse(NAME))")

    def variable_for(self, value: Any) -> Any:
        self.bind_json("VALUE", value)
        return self.json("acervatorHeader.variableFor(JSON.parse(VALUE))")

    def style_of(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorHeader.styleOf(JSON.parse(SHEET))")

    def declarations(self, sheet: Any) -> Any:
        self.bind_json("SHEET", sheet)
        return self.json("acervatorHeader.declarations(JSON.parse(SHEET))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime, revealed) -> JsRuntime:
    """The module holding the surface's default strip."""
    assert revealed is not None
    js.push(bridge_payload())
    return js


# -- 1. everything the surface publishes reaches the module ------------

#: Every field the surface publishes, and the module reader that answers
#: for it. A field with no reader is a value that stops at the bridge.
MODULE_READERS = {
    "actions": "acervatorHeader.actions()",
    "card_label_property": "acervatorHeader.cardLabelProperty()",
    "card_label_row": "acervatorHeader.cardLabelRow()",
    "card_label_style": "acervatorHeader.cardLabelStyle()",
    "card_layout": "acervatorHeader.cardLayout()",
    "card_value_property": "acervatorHeader.cardValueProperty()",
    "card_value_style": "acervatorHeader.cardValueStyle()",
    "central_layout": "acervatorHeader.centralLayout()",
    "counters": "acervatorHeader.counters()",
    "hidden_card": "acervatorHeader.hiddenCard()",
    "isolated_tabs": "acervatorHeader.isolatedTabs()",
    "mode_button": "acervatorHeader.modeButton()",
    "spendable": "acervatorHeader.spendable()",
    "top_row": "acervatorHeader.topRow()",
    "top_row_order": "acervatorHeader.topRowOrder()",
    "visible": "acervatorHeader.visible()",
}


def unreachable_fields(payload: dict) -> list:
    """Every field of ``payload`` no module reader answers for."""
    return sorted(set(payload) - set(MODULE_READERS))


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(
    js: JsRuntime, revealed, state: str
):
    """The whole payload, field by field, in both directions. A field the
    module never carries is a value that stops at the bridge."""
    assert revealed is not None
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
    """The control on the surface side, with a planted name. Without it a
    module that dropped a whole field would read as agreement."""
    payload = dict(bridge_payload())
    payload["planted_only_on_the_surface"] = []
    assert unreachable_fields(payload) == ["planted_only_on_the_surface"]


def test_the_whole_payload_check_names_a_field_only_the_module_reads():
    """The control on the module side. A reader with no published field
    behind it must be named."""
    payload = dict(bridge_payload())
    dropped = payload.pop("counters")
    assert dropped is not None
    extra = sorted(set(MODULE_READERS) - set(payload))
    assert extra == ["counters"], f"the check named {extra}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_reports_the_declared_and_held_counts_apart(
    js: JsRuntime, revealed, state: str
):
    """C72. Fields, slots and counters are each counted twice, so a
    payload that promises more than it carries reads as a difference."""
    assert revealed is not None
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(payload)
    assert report["declared"]["slots"] == len(payload["top_row_order"])
    assert report["held"]["slots"] == len(payload["top_row_order"])
    assert report["declared"]["counters"] == len(payload["counters"])
    assert report["held"]["counters"] == len(payload["counters"])


def test_a_missing_field_shortens_the_held_count_not_the_declared_count(
    js: JsRuntime, revealed
):
    """The control for the counts above."""
    assert revealed is not None
    payload = bridge_payload()
    del payload["counters"]
    report = js.push(payload)
    assert report["declared"]["fields"] == len(MODULE_READERS)
    assert report["held"]["fields"] == len(MODULE_READERS) - 1
    assert report["held"]["counters"] == 0
    assert report["declared"]["counters"] == len(COUNTER_KEYS)


def test_the_module_holds_every_kpi_column_the_surface_publishes(loaded: JsRuntime):
    """A column the surface publishes that the module never holds is a
    money figure the operator would not see."""
    declared = list(COLUMN_KEYS)
    held = [column["key"] for column in loaded.json("acervatorHeader.columns()")]
    assert held == declared, f"columns differ: surface {declared}, module {held}"


def test_the_kpi_column_check_names_a_column_only_the_surface_holds(
    js: JsRuntime, revealed
):
    """The control on the surface side."""
    assert revealed is not None
    payload = bridge_payload()
    dropped = payload["spendable"]["columns"].pop()
    js.push(payload)
    held = [column["key"] for column in js.json("acervatorHeader.columns()")]
    missing = sorted(set(COLUMN_KEYS) - set(held))
    assert missing == [dropped["key"]], f"the check named {missing}"


def test_the_module_holds_every_counter_the_surface_publishes(loaded: JsRuntime):
    """A counter card the surface publishes that the module never holds
    is a total the operator would not see."""
    held = [card["key"] for card in loaded.json("acervatorHeader.counters()")]
    assert held == list(COUNTER_KEYS)


def test_the_counter_check_names_a_counter_only_the_module_holds(
    js: JsRuntime, revealed
):
    """The control on the module side, with a planted card."""
    assert revealed is not None
    payload = bridge_payload()
    planted = dict(payload["counters"][0])
    planted["key"] = "planted_only_in_js"
    payload["counters"].append(planted)
    js.push(payload)
    held = [card["key"] for card in js.json("acervatorHeader.counters()")]
    extra = sorted(set(held) - set(COUNTER_KEYS))
    assert extra == ["planted_only_in_js"], f"the check named {extra}"


def test_the_module_names_the_fields_the_surface_declares(loaded: JsRuntime):
    """The module's own field list, against the payload it was given."""
    assert sorted(loaded.json("acervatorHeader.declaredFields()")) == sorted(
        bridge_payload()
    )


# -- 2. no value is written in the JavaScript --------------------------


def as_css(value: Any) -> set:
    """One published value, in every spelling a stylesheet could carry."""
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


#: The payload paths whose values skin or fill the strip. A value copied
#: from one into the module would be a second source of truth.
SKIN_FIELDS = (
    "style_sheet",
    "label_style",
    "initial_style",
    "card_label_style",
    "card_value_style",
    "text",
    "initial_text",
    "label",
    "tooltip",
    "label_tooltip",
    "window_title",
    "color",
)
SIZE_FIELDS = (
    "margins_px",
    "spacing_px",
    "child_stretch",
    "column_spacing_px",
    "column_margins_px",
    "column_spacing",
    "minimum_width_px",
)


def declaration_values(sheet: str) -> set:
    """Every value written on the right of a colon in one Qt style sheet."""
    found = set()
    for part in re.split(r"[;{}]", str(sheet)):
        head, sep, tail = part.partition(":")
        if sep and head.strip():
            found.add(tail.strip())
    found.discard("")
    return found


def strip_values() -> set:
    """Every colour, size, money text and style sheet the strip paints."""
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


SKIN_VALUES = strip_values()
TOKEN_VALUES = token_values()

#: The two mask markers the dot paints. A module spelling one out would
#: hold a second source of truth for whether an amount is hidden.
GLYPH_VALUES = {hss.DOT_REVEALED_GLYPH, hss.DOT_MASKED_GLYPH}
PUBLISHED_STRINGS = published_strings()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Names the module may write as a literal: field names, the slots of
#: ``top_row_order`` and the two compound alignment words.
NAMED_WORDS = sorted(
    {
        "actions",
        "card_label_property",
        "card_label_row",
        "card_label_style",
        "card_layout",
        "card_value_property",
        "card_value_style",
        "central_layout",
        "checked",
        "child_stretch",
        "clickable",
        "column_margins_px",
        "column_spacing",
        "column_spacing_px",
        "columns",
        "counters",
        "cursor",
        "dot",
        "dot_align",
        "errors.clicked",
        "field_id",
        "format",
        "frame_shape",
        "hcenter|bottom",
        "hcenter|top",
        "hidden_card",
        "initial_style",
        "initial_text",
        "isolated_tabs",
        "key",
        "label",
        "label_align",
        "label_style",
        "label_tooltip",
        "layout",
        "margins_px",
        "masked",
        "minimum_width_px",
        "mode",
        "mode_button",
        "mode_button.clicked",
        "order",
        "separator",
        "separator_align",
        "source_key",
        "spacing_px",
        "spendable",
        "stretch",
        "style_sheet",
        "text",
        "tooltip",
        "top_row",
        "top_row_order",
        "value_align",
        "visible",
        "window_title",
    }
)


def test_the_module_writes_no_number():
    """A text size, a margin, a corner rounding or a stretch factor typed
    here is a second source of truth for a value the surface owns."""
    assert not MODULE_LITERALS["numbers"], (
        "header_strip.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    """A colour typed here drifts from the surface the next time the
    strip's skin changes, and nothing reports the drift."""
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"header_strip.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_strip_paints():
    """A colour, a size, a money text, a tooltip or a whole Qt style
    sheet spelled out in the module."""
    written = sorted(set(MODULE_LITERALS["strings"]) & SKIN_VALUES)
    assert not written, f"header_strip.js spells out strip values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    """The table the module resolves through. A token value copied here
    would be a second source of truth for the same colour."""
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"header_strip.js spells out token values: {written}"


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


def test_every_named_word_is_a_name_and_not_a_value_the_strip_shows():
    """The control for the list above. A word that is also a colour, a
    size or a text the strip paints does not belong on it."""
    overlap = sorted(set(NAMED_WORDS) & SKIN_VALUES)
    assert not overlap, f"these named words are values the strip paints: {overlap}"


def test_no_string_in_the_module_equals_a_mask_glyph():
    """A glyph written here would say hidden or shown without the payload."""
    written = sorted(set(MODULE_LITERALS["strings"]) & GLYPH_VALUES)
    assert not written, f"header_strip.js spells out mask glyphs: {written}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    """The scan parses no regular expression, so a value inside one would
    pass unread. The module carries none."""
    assert not MODULE_LITERALS["slashes"], (
        "header_strip.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


PLANTED_LINES = {
    "colour": 'var planted = "#00ffcc";',
    "size": 'var planted = "' + str(hss.CARD_LAYOUT["spacing_px"]) + 'px";',
    "margin": "var planted = " + str(hss.CENTRAL_LAYOUT["margins_px"][0]) + ";",
    "number": "var planted = 12;",
    "money_text": 'var planted = "' + hss.COUNTER_CARDS[0]["initial_text"] + '";',
    "empty_marker": 'var planted = "' + hss.EMPTY_TEXT + '";',
    "style_sheet": 'var planted = "' + hss.CARD_LABEL_STYLE + '";',
    "value_style": 'var planted = "' + hss.VALUE_STYLE_HIGHLIGHT + '";',
    "glyph": 'var planted = "' + hss.DOT_REVEALED_GLYPH + '";',
    "token_value": 'var planted = "' + str(dss.PRIMARY) + '";',
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
    if strings & SKIN_VALUES:
        caught.add("skin_value")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if strings & GLYPH_VALUES:
        caught.add("glyph")
    if found["slashes"]:
        caught.add("regex")
    return caught


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_a_planted_line(kind: str):
    """The controls for the five checks above, one plant at a time. A
    blind scan reports nothing on a line that spells a value out."""
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
    either the scan is blind or the file was left changed.
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
    blind = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not blind, f"the scan reported nothing on these plants in the file: {blind}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_planted_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    """Every plant leaves the file valid JavaScript, so a page loading it
    mid-scan still defines the strip module."""
    for kind, line in sorted(PLANTED_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetHeader") == "function", kind


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
    js: JsRuntime, revealed, state: str
):
    """A value that changes shape in transit reads correct and paints
    wrong: a number where a colour belongs paints nothing."""
    assert revealed is not None
    payload = state_payload(state)
    js.push(payload)
    expected = python_kinds(payload)
    actual = js.json("acervatorHeader.kinds()")
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
    """The control. A payload with one text where a number belongs must
    read as exactly one difference."""
    assert revealed is not None
    payload = bridge_payload()
    payload["central_layout"]["spacing_px"] = str(
        payload["central_layout"]["spacing_px"]
    )
    js.push(payload)
    expected = python_kinds(bridge_payload())
    actual = js.json("acervatorHeader.kinds()")
    differing = sorted(p for p, k in expected.items() if actual.get(p) != k)
    assert differing == ["central_layout.spacing_px"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_kpi_column_agrees_with_the_surface(js: JsRuntime, revealed, state: str):
    """The whole claim of this unit for the money panel. A single
    disagreement means the React strip shows a different figure."""
    assert revealed is not None
    payload = state_payload(state)
    js.push(payload)
    for expected in payload["spendable"]["columns"]:
        actual = js.named("column", expected["key"])
        differing = {
            field: (expected[field], actual.get(field))
            for field in expected
            if actual.get(field) != expected[field]
        }
        assert not differing, (
            f"{state}/{expected['key']}: {len(differing)} of "
            f"{len(expected)} values differ: {sorted(differing)}"
        )
        assert len(actual) == len(expected)


def test_the_kpi_column_value_check_names_a_changed_value(js: JsRuntime, revealed):
    """The control. Two real payloads differing by one value must not
    compare equal."""
    assert revealed is not None
    payload = bridge_payload()
    payload["spendable"]["columns"][0]["text"] += "0"
    js.push(payload)
    expected = bridge_payload()["spendable"]["columns"][0]
    actual = js.named("column", expected["key"])
    differing = sorted(f for f in expected if actual.get(f) != expected[f])
    assert differing == ["text"], f"the check named {differing}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_counter_card_agrees_with_the_surface(
    js: JsRuntime, revealed, state: str
):
    """The whole claim of this unit for the five totals."""
    assert revealed is not None
    payload = state_payload(state)
    js.push(payload)
    for expected in payload["counters"]:
        actual = js.named("counter", expected["key"])
        differing = {
            field: (expected[field], actual.get(field))
            for field in expected
            if actual.get(field) != expected[field]
        }
        assert not differing, (
            f"{state}/{expected['key']}: {len(differing)} of "
            f"{len(expected)} values differ: {sorted(differing)}"
        )


def test_the_counter_value_check_names_a_changed_value(js: JsRuntime, revealed):
    """The control for the counter comparison."""
    assert revealed is not None
    payload = bridge_payload()
    payload["counters"][0]["text"] += "0"
    js.push(payload)
    expected = bridge_payload()["counters"][0]
    actual = js.named("counter", expected["key"])
    differing = sorted(f for f in expected if actual.get(f) != expected[f])
    assert differing == ["text"], f"the check named {differing}"


def test_a_masked_value_reaches_the_module_masked(js: JsRuntime, revealed):
    """The privacy mask is the surface's own work. The module carries
    whatever text arrives, masked or not."""
    for field in FIELD_IDS:
        revealed.set_masked(field, True)
    payload = bridge_payload(stats=FILLED_STATS)
    js.push(payload)
    shown = [card["text"] for card in js.json("acervatorHeader.counters()")]
    assert shown == [card["text"] for card in payload["counters"]]
    assert len(set(shown)) == 1, f"the masked cards do not read alike: {shown}"


def test_the_mask_check_reads_a_different_text_when_nothing_is_masked(
    js: JsRuntime, revealed
):
    """The control for the check above. A reader blind to the text would
    report the same list whether or not the mask was on."""
    assert revealed is not None
    js.push(bridge_payload(stats=FILLED_STATS))
    shown = [card["text"] for card in js.json("acervatorHeader.counters()")]
    assert len(set(shown)) > 1, f"the revealed cards all read alike: {shown}"


def test_the_module_reports_only_what_it_was_given(js: JsRuntime, revealed):
    """Every value comes from the payload and none from the module. A
    payload of texts the surface never held comes back unchanged."""
    assert revealed is not None
    payload = bridge_payload()
    invented = {"key": "given", "text": "given-text", "initial_text": "given-initial"}
    payload["counters"] = [invented]
    payload["top_row_order"] = ["given"]
    js.push(payload)
    assert js.json("acervatorHeader.counters()") == [invented]
    assert not set(invented.values()) & SKIN_VALUES


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


STRIP_COLOURS = sorted(
    {
        value
        for value in strip_values()
        if isinstance(value, str) and HEX_COLOUR.fullmatch(value)
    }
)


def test_every_colour_the_strip_paints_resolves_to_one_token(js: JsRuntime, revealed):
    """A colour is painted through the one token that holds it, so a
    token changed in Python moves the strip without touching the file."""
    assert revealed is not None
    js.load_tokens()
    js.load_widgets()
    assert STRIP_COLOURS, "the strip paints no colour; the check cannot report"
    for colour in STRIP_COLOURS:
        assert carriers_of(colour) == [
            js.variable_for(colour)
        ], f"{colour} is carried by {carriers_of(colour)}"


def test_a_margin_carried_by_more_than_one_token_resolves_to_none(
    js: JsRuntime, revealed
):
    """C77. Binding a strip margin to a token that shares its number with
    another would move the strip whenever either moved."""
    assert revealed is not None
    js.load_tokens()
    js.load_widgets()
    value = bridge_payload()["central_layout"]["margins_px"][1]
    assert len(carriers_of(value)) > 1, f"only {carriers_of(value)} carry {value}"
    assert js.variable_for(value) is None


def test_a_margin_carried_by_one_token_resolves_to_that_token(js: JsRuntime, revealed):
    """The positive control for the check above."""
    assert revealed is not None
    js.load_tokens()
    js.load_widgets()
    value = bridge_payload()["central_layout"]["margins_px"][0]
    assert carriers_of(value) == ["RADIUS_CARD"], f"{value} -> {carriers_of(value)}"
    assert js.variable_for(value) == "RADIUS_CARD"


def test_a_value_no_token_carries_resolves_to_none(js: JsRuntime, revealed):
    """The control for the resolver. A value off the table is painted
    from the surface rather than through a variable nothing answers."""
    assert revealed is not None
    js.load_tokens()
    js.load_widgets()
    assert js.variable_for("no-token-carries-this") is None


def test_the_resolver_reports_no_name_with_the_widget_module_off_the_page(
    js: JsRuntime, revealed
):
    """A page that never loaded the shared widgets paints every value
    from the surface rather than through a variable nothing answers."""
    assert revealed is not None
    js.load_tokens()
    assert js.variable_for(str(dss.PRIMARY)) is None


# -- reading one Qt style sheet ----------------------------------------


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


def test_the_module_reads_the_same_declarations_as_the_surface_wrote(
    js: JsRuntime, revealed
):
    """Every base declaration of every sheet the strip carries."""
    assert revealed is not None
    payload = bridge_payload(stats=FILLED_STATS)
    sheets = [
        payload["spendable"]["style_sheet"],
        payload["spendable"]["separator"]["style_sheet"],
        payload["spendable"]["columns"][0]["style_sheet"],
        payload["spendable"]["columns"][0]["label_style"],
        payload["spendable"]["columns"][0]["dot"]["style_sheet"],
        payload["card_label_style"],
        payload["card_value_style"],
        payload["mode_button"]["style_sheet"],
    ]
    for sheet in sheets:
        expected = [
            {"property": name, "value": value}
            for name, value in python_declarations(base_body(sheet))
        ]
        assert js.declarations(sheet) == expected, f"declarations differ for {sheet}"


def test_the_declaration_reader_names_a_changed_value(js: JsRuntime, revealed):
    """The control. A reader that returned the same list whatever it was
    given would agree with any sheet."""
    assert revealed is not None
    sheet = bridge_payload()["card_label_style"]
    expected = [
        {"property": name, "value": value}
        for name, value in python_declarations(base_body(sheet))
    ]
    assert js.declarations(sheet + "letter-spacing: 1px;") != expected


def test_the_module_leaves_a_hover_block_out_of_the_painted_style(
    js: JsRuntime, revealed
):
    """Qt paints a hover colour the page cannot apply inline. The base
    colour is painted and the hover rule is carried apart."""
    assert revealed is not None
    dot = bridge_payload()["counters"][0]["dot"]["style_sheet"]
    painted = js.style_of(dot)
    assert str(dss.PRIMARY_BRIGHT) in painted["color"]
    assert str(dss.TEXT_MAX) not in json.dumps(painted)


def test_the_module_carries_the_hover_rule_the_page_cannot_paint(
    js: JsRuntime, revealed
):
    """The hover block reaches the module rather than stopping at the
    bridge, so nothing the surface published is lost."""
    assert revealed is not None
    js.bind_json("SHEET", bridge_payload()["counters"][0]["dot"]["style_sheet"])
    rules = js.json("acervatorHeader.stateRules(JSON.parse(SHEET))")
    assert len(rules) == 1, f"the module found {len(rules)} state rules"
    assert str(dss.TEXT_MAX) in rules[0]["body"]


def test_the_hover_check_finds_no_rule_in_a_sheet_that_has_none(
    js: JsRuntime, revealed
):
    """The control. A reader that reported a rule for every sheet would
    pass the check above on a sheet with no hover block."""
    assert revealed is not None
    js.bind_json("SHEET", bridge_payload()["card_label_style"])
    assert js.json("acervatorHeader.stateRules(JSON.parse(SHEET))") == []


def test_a_qt_only_paint_is_named_and_reaches_no_style(js: JsRuntime, revealed):
    """The spendable panel's gradient is a Qt paint function no
    stylesheet runs. It is reported, not translated."""
    assert revealed is not None
    payload = bridge_payload()
    report = js.push(payload)
    assert {
        "where": "spendable",
        "field": "style_sheet",
        "fault": "not-css",
        "detail": "background",
    } in report["faults"]
    assert "background" not in js.style_of(payload["spendable"]["style_sheet"])


def test_the_qt_only_check_is_quiet_on_a_sheet_that_paints_a_plain_colour(
    js: JsRuntime, revealed
):
    """The negative control. Every other sheet the strip carries paints
    through CSS and raises no fault."""
    assert revealed is not None
    report = js.push(bridge_payload())
    named = [f for f in report["faults"] if f["fault"] == "not-css"]
    assert [f["where"] for f in named] == ["spendable"], f"named {named}"


# -- 4. the strip, drawn in the real page ------------------------------


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
                if self.js("typeof window.acervatorSetHeader") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the strip module: readyState "
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
    "marginLeft",
    "marginTop",
    "marginRight",
    "marginBottom",
    "color",
    "backgroundColor",
    "fontSize",
    "fontWeight",
    "letterSpacing",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopColor",
    "borderTopLeftRadius",
    "minWidth",
    "cursor",
]

#: A Qt shorthand and the computed properties it settles into.
EXPANDED = {
    "border": ("borderTopStyle", "borderTopWidth", "borderTopColor"),
    "padding": ("paddingLeft", "paddingTop", "paddingRight", "paddingBottom"),
    "margin": ("marginLeft", "marginTop", "marginRight", "marginBottom"),
    "background": ("backgroundColor",),
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


def draw_strip(browser: Browser, payload: dict) -> list:
    """Draw the strip into the page and read every part back."""
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetHeader(JSON.parse(window.PAYLOAD));"
        "acervatorHeader.renderStrip(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def read_parts(browser: Browser) -> list:
    """Read every drawn part again without redrawing."""
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
    """One layout number as a computed CSS length."""
    return str(value) + "px"


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


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser, revealed):
    """``script-src 'self'`` admits the module. A policy that refused it
    would leave the page with no strip API at all."""
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorHeader") == "object"
    assert browser.js("typeof window.acervatorSetHeader") == "function"
    assert browser.js("typeof window.acervatorLoadHeader") == "function"


def test_the_policy_refuses_a_network_call_from_the_loaded_page(
    browser: Browser, revealed
):
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


def test_the_module_makes_no_network_call_of_its_own(browser: Browser, revealed):
    """Drawing the strip raises no policy violation, so nothing in the
    module reaches for the network."""
    browser.js(WATCH_VIOLATIONS)
    draw_strip(browser, bridge_payload(stats=FILLED_STATS))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


def test_the_drawn_strip_places_every_slot_in_the_order_the_surface_names(
    browser: Browser,
    revealed,
):
    """The operator reads the strip left to right. A slot out of place is
    a figure under the wrong caption."""
    payload = bridge_payload(stats=FILLED_STATS)
    parts = draw_strip(browser, payload)
    slots = [one["attrs"]["data-slot"] for one in parts if "data-slot" in one["attrs"]]
    assert slots == payload["top_row_order"], f"the strip drew {slots}"


def test_the_slot_order_check_names_a_swapped_pair(browser: Browser, revealed):
    """The control. A read keyed on position rather than on the drawn
    attribute would report the same list after a swap."""
    payload = bridge_payload(stats=FILLED_STATS)
    order = payload["top_row_order"]
    order[1], order[2] = order[2], order[1]
    parts = draw_strip(browser, payload)
    slots = [one["attrs"]["data-slot"] for one in parts if "data-slot" in one["attrs"]]
    assert slots == order
    assert slots != bridge_payload()["top_row_order"]


def test_the_drawn_strip_shows_every_money_figure_the_surface_published(
    browser: Browser,
    revealed,
):
    """The whole claim of this unit. Every text the operator reads off
    the strip, against the text the surface produced."""
    payload = bridge_payload(stats=FILLED_STATS, exchange_count=3)
    parts = draw_strip(browser, payload)
    for column in payload["spendable"]["columns"]:
        where = "strip/top-row/spendable/kpi-column"
        drawn = [
            one
            for one in at_path(parts, where)
            if one["attrs"].get("data-key") == column["key"]
        ]
        assert len(drawn) == 1, f"{column['key']} drew {len(drawn)} columns"
        labels = at_path(parts, where + "/kpi-label")
        values = at_path(parts, where + "/kpi-value")
        assert column["label"] in [one["text"] for one in labels]
        assert column["text"] in [one["text"] for one in values]
    shown = [
        one["text"] for one in at_path(parts, "strip/top-row/counter/counter-value")
    ]
    assert shown == [card["text"] for card in payload["counters"]]


def test_the_money_figure_check_names_one_changed_text(browser: Browser, revealed):
    """The control. A read that returned the same text whatever was drawn
    would report agreement on a changed figure."""
    payload = bridge_payload(stats=FILLED_STATS)
    payload["counters"][0]["text"] += "0"
    parts = draw_strip(browser, payload)
    shown = [
        one["text"] for one in at_path(parts, "strip/top-row/counter/counter-value")
    ]
    original = [card["text"] for card in bridge_payload(stats=FILLED_STATS)["counters"]]
    differing = [at for at, one in enumerate(original) if shown[at] != one]
    assert differing == [0], f"the check named {differing}"


def test_the_drawn_kpi_values_match_the_surface_s_own_style_sheets(
    browser: Browser, revealed
):
    """Every colour, size and weight the money panel paints, against a
    bare element styled from the same declarations."""
    payload = bridge_payload(stats=FILLED_STATS)
    parts = draw_strip(browser, payload)
    values = at_path(parts, "strip/top-row/spendable/kpi-column/kpi-value")
    labels = at_path(parts, "strip/top-row/spendable/kpi-column/kpi-label")
    assert len(values) == len(payload["spendable"]["columns"])
    for at, column in enumerate(payload["spendable"]["columns"]):
        sheet_agrees(
            values[at],
            probe(browser, base_body(column["style_sheet"])),
            "value " + column["key"],
        )
        sheet_agrees(
            labels[at],
            probe(browser, base_body(column["label_style"])),
            "label " + column["key"],
        )


def test_the_style_sheet_check_names_one_changed_colour(browser: Browser, revealed):
    """The control. A comparison blind to the drawn colour would report
    agreement on a value painted the wrong colour."""
    payload = bridge_payload(stats=FILLED_STATS)
    original = payload["spendable"]["columns"][0]["style_sheet"]
    payload["spendable"]["columns"][0]["style_sheet"] = original.replace(
        str(dss.SUCCESS), str(dss.ERROR)
    )
    parts = draw_strip(browser, payload)
    drawn = at_path(parts, "strip/top-row/spendable/kpi-column/kpi-value")[0]
    expected = probe(browser, base_body(original))
    differing = sorted(
        name for name, value in expected.items() if drawn["style"].get(name) != value
    )
    assert differing == ["color"], f"the check named {differing}"


def test_the_drawn_counter_cards_match_the_surface_s_own_style_sheets(
    browser: Browser,
    revealed,
):
    """The five totals, against bare elements styled from the same
    declarations the surface published for them."""
    payload = bridge_payload(stats=FILLED_STATS)
    parts = draw_strip(browser, payload)
    label_style = probe(browser, base_body(payload["card_label_style"]))
    value_style = probe(browser, base_body(payload["card_value_style"]))
    for drawn in at_path(parts, "strip/top-row/counter/label-row/counter-label"):
        sheet_agrees(drawn, label_style, "counter label")
    for drawn in at_path(parts, "strip/top-row/counter/counter-value"):
        sheet_agrees(drawn, value_style, "counter value")


def test_the_drawn_dots_match_the_surface_s_own_style_sheet(browser: Browser, revealed):
    """The privacy dot under every value, and the hover colour Qt paints
    that no inline style can carry."""
    payload = bridge_payload(stats=FILLED_STATS)
    parts = draw_strip(browser, payload)
    dots = [one for one in parts if one["path"].endswith("privacy-dot")]
    assert len(dots) == len(FIELD_IDS), f"the strip drew {len(dots)} dots"
    base = probe(browser, base_body(payload["counters"][0]["dot"]["style_sheet"]))
    for drawn in dots:
        sheet_agrees(drawn, base, "dot " + str(drawn["attrs"].get("data-field-id")))
        assert drawn["text"] == payload["counters"][0]["dot"]["text"]


def test_the_drawn_layout_matches_the_margins_the_surface_publishes(
    browser: Browser, revealed
):
    """The strip's own spacing, read off the drawn document."""
    payload = bridge_payload(stats=FILLED_STATS)
    parts = draw_strip(browser, payload)
    strip = only(parts, "strip")
    margins = payload["central_layout"]["margins_px"]
    assert strip["style"]["paddingLeft"] == pixels(margins[0])
    assert strip["style"]["paddingTop"] == pixels(margins[1])
    assert strip["style"]["paddingRight"] == pixels(margins[2])
    assert strip["style"]["paddingBottom"] == pixels(margins[3])
    assert strip["style"]["rowGap"] == pixels(payload["central_layout"]["spacing_px"])
    panel = only(parts, "strip/top-row/spendable")
    inner = payload["spendable"]["layout"]["margins_px"]
    assert panel["style"]["paddingTop"] == pixels(inner[1])
    assert panel["style"]["columnGap"] == pixels(
        payload["spendable"]["layout"]["column_spacing_px"]
    )
    assert panel["style"]["flexGrow"] == str(payload["top_row"]["child_stretch"][0])


def test_the_layout_check_names_one_changed_margin(browser: Browser, revealed):
    """The control. A read that returned the same length whatever was
    drawn would report agreement on a changed margin."""
    payload = bridge_payload()
    original = payload["central_layout"]["margins_px"][1]
    payload["central_layout"]["margins_px"][1] = original + original
    parts = draw_strip(browser, payload)
    assert only(parts, "strip")["style"]["paddingTop"] == pixels(original + original)


def test_the_drawn_strip_follows_a_colour_token_and_nothing_else_moves(
    browser: Browser,
    revealed,
):
    """What proves the strip resolves through the token module rather
    than copying it: the token is rewritten and only its values move."""
    payload = bridge_payload(stats=FILLED_STATS)
    before = draw_strip(browser, payload)
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
    assert {path for path, _ in moved} == {
        "strip/top-row/spendable/kpi-column/kpi-label",
        "strip/top-row/counter/counter-value",
        "strip/hidden-card",
        "strip/hidden-card/counter-label",
        "strip/hidden-card/counter-value",
    }, f"the token moved {sorted({p for p, _ in moved})}"


def test_the_drawn_strip_follows_a_size_token_and_nothing_else_moves(
    browser: Browser,
    revealed,
):
    """A size takes a different path through CSS than a colour, so it
    needs its own check: a token holds a bare number."""
    payload = bridge_payload(stats=FILLED_STATS)
    before = draw_strip(browser, payload)
    moved_to = dss.RADIUS_LG
    assert moved_to != payload["central_layout"]["margins_px"][0]
    browser.js(
        "document.documentElement.style.setProperty('--RADIUS_CARD', "
        + json.dumps(str(moved_to))
        + ");"
    )
    after = read_parts(browser)
    moved = changed_paths(before, after)
    assert {key for _, key in moved} == {
        "paddingLeft",
        "paddingRight",
        "paddingTop",
        "paddingBottom",
    }, f"the token moved {moved}"
    assert {path for path, _ in moved} == {
        "strip",
        "strip/top-row/spendable",
    }, f"the token moved {sorted({p for p, _ in moved})}"
    assert only(after, "strip")["style"]["paddingLeft"] == pixels(moved_to)


def test_the_token_check_reports_nothing_when_no_token_is_rewritten(
    browser: Browser, revealed
):
    """The control for the two checks above. A comparison that reported a
    difference on every read would pass them without proving anything."""
    payload = bridge_payload(stats=FILLED_STATS)
    before = draw_strip(browser, payload)
    assert changed_paths(before, read_parts(browser)) == set()


def changed_paths(before: list, after: list) -> set:
    """Every (path, property) whose computed value moved between reads."""
    assert len(before) == len(after), "the strip drew a different number of parts"
    moved = set()
    for at, one in enumerate(before):
        other = after[at]
        assert one["path"] == other["path"]
        for key, value in one["style"].items():
            if other["style"].get(key) != value:
                moved.add((one["path"], key))
    return moved


def test_the_spendable_gradient_reaches_no_pixel_on_the_page(
    browser: Browser, revealed
):
    """Reported, not repaired. Qt fills the money panel with a gradient
    the page cannot run, so the React panel draws no background."""
    payload = bridge_payload()
    parts = draw_strip(browser, payload)
    panel = only(parts, "strip/top-row/spendable")
    assert panel["style"]["backgroundColor"] == "rgba(0, 0, 0, 0)"
    assert "qlineargradient" in payload["spendable"]["style_sheet"]


def test_the_spendable_border_matches_a_probe_styled_from_the_surface(
    browser: Browser,
    revealed,
):
    """R1 and C21. Chromium snaps a border to whole device pixels, so the
    declared width is compared against a probe, never a typed number."""
    payload = bridge_payload()
    parts = draw_strip(browser, payload)
    panel = only(parts, "strip/top-row/spendable")
    expected = probe(browser, base_body(payload["spendable"]["style_sheet"]))
    assert expected["borderTopWidth"] != "0px", "the probe drew no border"
    sheet_agrees(panel, expected, "spendable frame")


def test_the_hidden_card_is_drawn_and_hidden(browser: Browser, revealed):
    """The Qt strip hides the P/L card but still sets its text. So does
    the React strip: the value is present and not shown."""
    payload = bridge_payload(stats=FILLED_STATS)
    parts = draw_strip(browser, payload)
    card = only(parts, "strip/hidden-card")
    assert card["hidden"] is True
    assert only(parts, "strip/hidden-card/counter-value")["text"] == (
        payload["hidden_card"]["text"]
    )
    assert only(parts, "strip/hidden-card/counter-label")["text"] == (
        payload["hidden_card"]["label"]
    )


def test_the_hidden_card_check_reads_a_shown_card_as_shown(browser: Browser, revealed):
    """The control. A read that returned hidden for every element would
    pass the check above on a card that was fully visible."""
    payload = bridge_payload()
    payload["hidden_card"]["visible"] = True
    parts = draw_strip(browser, payload)
    assert only(parts, "strip/hidden-card")["hidden"] is False


def test_an_isolated_tab_hides_the_whole_strip(browser: Browser, revealed):
    """The Simulator and Paper Trader tabs hide the strip. The missing
    strip is what marks them apart from the Trading tab."""
    payload = bridge_payload(tab_name=hss.ISOLATED_TABS[0])
    assert payload["visible"] is False
    parts = draw_strip(browser, payload)
    assert only(parts, "strip")["hidden"] is True


def test_the_isolated_tab_check_reads_the_trading_tab_as_shown(
    browser: Browser, revealed
):
    """The control for the check above."""
    parts = draw_strip(browser, bridge_payload())
    assert only(parts, "strip")["hidden"] is False


def test_the_mode_button_draws_the_wing_the_surface_names(browser: Browser, revealed):
    """The button the operator clicks to change trading layer."""
    payload = bridge_payload(mode="stock")
    parts = draw_strip(browser, payload)
    button = only(parts, "strip/top-row/mode-button")
    assert button["tag"] == "BUTTON"
    assert button["text"] == payload["mode_button"]["text"]
    assert button["attrs"]["data-mode"] == payload["mode_button"]["mode"]
    assert (
        button["attrs"]["aria-pressed"]
        == str(payload["mode_button"]["checked"]).lower()
    )
    assert button["attrs"]["title"] == payload["mode_button"]["tooltip"]
    assert (
        button["attrs"]["data-window-title"] == payload["mode_button"]["window_title"]
    )
    assert button["attrs"]["data-action"] == payload["actions"]["mode_button.clicked"]
    assert button["style"]["minWidth"] == pixels(
        payload["mode_button"]["minimum_width_px"]
    )
    sheet_agrees(
        button, probe(browser, base_body(payload["mode_button"]["style_sheet"])), "mode"
    )


def test_the_mode_button_check_names_the_other_wing(browser: Browser, revealed):
    """The control. Two real payloads differing by the wing must not
    read alike."""
    crypto = only(draw_strip(browser, bridge_payload()), "strip/top-row/mode-button")
    stock = only(
        draw_strip(browser, bridge_payload(mode="stock")), "strip/top-row/mode-button"
    )
    assert crypto["text"] != stock["text"]
    assert crypto["style"]["color"] != stock["style"]["color"]


def test_the_clickable_counter_carries_the_action_the_surface_names(
    browser: Browser, revealed
):
    """The Errors card opens the error log. The action is the surface's
    own name for it, carried onto the drawn card."""
    payload = bridge_payload()
    parts = draw_strip(browser, payload)
    cards = at_path(parts, "strip/top-row/counter")
    clickable = [one for one in cards if one["attrs"].get("data-clickable") == "true"]
    assert len(clickable) == 1
    assert clickable[0]["attrs"]["data-key"] == "errors"
    assert clickable[0]["attrs"]["data-action"] == payload["actions"]["errors.clicked"]
    assert clickable[0]["style"]["cursor"] == "pointer"
    plain = [one for one in cards if one["attrs"].get("data-clickable") == "false"]
    assert len(plain) == len(COUNTER_KEYS) - 1
    assert {one["style"]["cursor"] for one in plain} == {"default"}


# -- 5. hostile payloads -----------------------------------------------

HOSTILE_MONEY = {
    "a true flag": True,
    "not a number": float("nan"),
    "an infinity": float("inf"),
    "a very large integer": 10**24,
    "text where a number belongs": "1234.5",
    "nothing at all": None,
}


@pytest.mark.parametrize("case", sorted(HOSTILE_MONEY))
def test_the_strip_shows_whatever_money_text_the_surface_produced(
    js: JsRuntime, revealed, case: str
):
    """The React strip formats no money. It shows the exact text the
    surface produced, whatever that text is."""
    assert revealed is not None
    stats = dict(FILLED_STATS)
    stats["total_scrummed_usd"] = HOSTILE_MONEY[case]
    payload = bridge_payload(stats=stats)
    js.push(payload)
    shown = js.named("counter", "scrummed")["text"]
    assert shown == payload["counters"][0]["text"], f"{case}: strip shows {shown}"


def test_the_money_check_reads_a_different_text_for_a_different_amount(
    js: JsRuntime, revealed
):
    """The control for the table above. A reader that answered the same
    text for every amount would pass every row of it."""
    assert revealed is not None
    stats = dict(FILLED_STATS)
    stats["total_scrummed_usd"] = 1.0
    js.push(bridge_payload(stats=stats))
    one = js.named("counter", "scrummed")["text"]
    stats["total_scrummed_usd"] = 2.0
    js.push(bridge_payload(stats=stats))
    assert js.named("counter", "scrummed")["text"] != one


@pytest.mark.parametrize("field", sorted(MODULE_READERS))
def test_a_field_the_payload_omits_is_named_as_missing(
    js: JsRuntime, revealed, field: str
):
    """The surface sent a payload with one field gone."""
    assert revealed is not None
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
def test_a_field_carrying_null_is_named_and_draws_nothing(
    js: JsRuntime, revealed, field: str
):
    """A null is reported, not swapped for a value of the module's own."""
    assert revealed is not None
    payload = bridge_payload()
    payload[field] = None
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "null",
        "detail": None,
    } in report["faults"]


def test_the_missing_field_check_is_quiet_on_a_whole_payload(js: JsRuntime, revealed):
    """The negative control for the two checks above. Every shipped
    payload passes."""
    assert revealed is not None
    report = js.push(bridge_payload())
    kinds = [f["fault"] for f in report["faults"]]
    assert "missing" not in kinds
    assert "null" not in kinds


def test_a_money_text_that_is_a_number_is_named_against_its_own_default(
    js: JsRuntime, revealed
):
    """The surface publishes ``initial_text`` as a string, so the module
    has a type to hold the counter's text against."""
    assert revealed is not None
    payload = bridge_payload()
    payload["counters"][0]["text"] = 12.5
    report = js.push(payload)
    assert {
        "where": "counter:scrummed",
        "field": "text",
        "fault": "wrong-type",
        "detail": "number",
    } in report["faults"]
    assert js.named("counter", "scrummed")["text"] == 12.5


def test_a_kpi_style_that_is_a_number_is_named_against_its_own_default(
    js: JsRuntime, revealed
):
    """The surface publishes ``initial_style`` as a string, so the module
    has a type to hold the column's style sheet against."""
    assert revealed is not None
    payload = bridge_payload()
    payload["spendable"]["columns"][0]["style_sheet"] = 7
    report = js.push(payload)
    assert {
        "where": "column:spendable",
        "field": "style_sheet",
        "fault": "wrong-type",
        "detail": "number",
    } in report["faults"]


def test_a_mode_button_text_that_is_a_number_raises_no_fault(js: JsRuntime, revealed):
    """The surface publishes no default for the mode button, so the
    module has no type to hold its text against. It carries the number
    on and names the type it received."""
    assert revealed is not None
    payload = bridge_payload()
    payload["mode_button"]["text"] = 7
    js.push(payload)
    assert js.json("acervatorHeader.modeButton()")["text"] == 7
    assert js.json("acervatorHeader.kinds()")["mode_button.text"] == "number"
    named = [f["field"] for f in js.json("acervatorHeader.faults()")]
    assert "text" not in named


def test_the_wrong_type_check_is_quiet_on_a_whole_payload(js: JsRuntime, revealed):
    """The negative control. Every shipped text passes."""
    assert revealed is not None
    report = js.push(bridge_payload(stats=FILLED_STATS))
    kinds = [f["fault"] for f in report["faults"]]
    assert "wrong-type" not in kinds


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(
    js: JsRuntime, revealed
):
    """A bridge answering with a string or a number draws nothing."""
    assert revealed is not None
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorHeader.isLoaded()") is False
        assert js.json("acervatorHeader.counters()") == []
        assert report["declared"] is None
        assert report["held"] is None
        assert [f["fault"] for f in report["faults"]] == ["not-an-object"]


def test_a_name_the_payload_never_carried_is_not_a_counter(js: JsRuntime, revealed):
    """Every JavaScript object inherits names like ``constructor``.
    Reading one as a counter would hand the strip a function where a
    money figure belongs."""
    assert revealed is not None
    js.push(bridge_payload())
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        assert js.named("counter", inherited) is None
        assert js.named("column", inherited) is None


def test_the_inherited_name_check_still_reads_a_real_counter(js: JsRuntime, revealed):
    """The control. A reader that answered nothing for every name would
    pass the check above while serving no card."""
    assert revealed is not None
    js.push(bridge_payload())
    assert js.named("counter", "scrummed") == bridge_payload()["counters"][0]
    assert js.named("column", "spendable") is not None


def test_a_slot_naming_no_counter_is_named_and_draws_nothing(js: JsRuntime, revealed):
    """A strip order naming a card the payload does not carry."""
    assert revealed is not None
    payload = bridge_payload()
    payload["top_row_order"].append("no_such_counter")
    report = js.push(payload)
    assert {
        "where": "top_row_order",
        "field": "no_such_counter",
        "fault": "missing",
        "detail": None,
    } in report["faults"]
    assert report["declared"]["slots"] == report["held"]["slots"] + 1


def test_a_counter_in_no_slot_is_named(js: JsRuntime, revealed):
    """A card the payload carries that the strip order never places."""
    assert revealed is not None
    payload = bridge_payload()
    payload["counters"][0]["key"] = "unplaced"
    report = js.push(payload)
    assert {
        "where": "counter:unplaced",
        "field": "key",
        "fault": "unslotted",
        "detail": None,
    } in report["faults"]


def test_a_short_stretch_list_is_named(js: JsRuntime, revealed):
    """C72. The strip order and the stretch list are counted apart, so a
    payload promising more slots than it weights reads as a difference."""
    assert revealed is not None
    payload = bridge_payload()
    payload["top_row"]["child_stretch"].pop()
    report = js.push(payload)
    assert {
        "where": "top_row",
        "field": "child_stretch",
        "fault": "short-list",
        "detail": len(payload["top_row"]["child_stretch"]),
    } in report["faults"]


def test_the_short_list_check_is_quiet_on_a_whole_payload(js: JsRuntime, revealed):
    """The negative control. Every shipped stretch list passes."""
    assert revealed is not None
    report = js.push(bridge_payload())
    kinds = [f["fault"] for f in report["faults"]]
    assert "short-list" not in kinds
    assert "unslotted" not in kinds


def test_a_hostile_payload_still_draws_a_strip(browser: Browser, revealed):
    """Every field the payload keeps is still drawn. A module that threw
    on a hostile value would leave the operator with a blank strip."""
    payload = bridge_payload(stats=FILLED_STATS)
    payload["mode_button"]["text"] = 7
    payload["counters"][0]["text"] = None
    payload["spendable"]["columns"][0]["style_sheet"] = 7
    payload["card_label_row"]["order"] = None
    parts = draw_strip(browser, payload)
    assert only(parts, "strip")
    assert len(at_path(parts, "strip/top-row/counter")) == len(COUNTER_KEYS)
    assert only(parts, "strip/top-row/mode-button")["text"] == "7"


# -- 6. the bridge ask --------------------------------------------------


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime, revealed):
    """The module reaches Python the one way the page allows: the preload
    bridge, naming the method the surface registers."""
    assert revealed is not None
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadHeader();")
    drain_events()
    assert js.json("window.CALLS") == [[hss.METHOD, "{}"]]
    assert js.json("acervatorHeader.isLoaded()") is True


def test_the_module_passes_a_caller_s_parameters_to_the_surface(
    js: JsRuntime, revealed
):
    """A caller that wants the stock wing sends the name the surface
    reads."""
    assert revealed is not None
    js.bind_json("PAYLOAD", bridge_payload(mode="stock"))
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", {"mode": "stock"})
    js.run("acervatorLoadHeader(JSON.parse(WANTED));")
    drain_events()
    assert js.json("window.CALLS") == [[hss.METHOD, '{"mode":"stock"}']]
    assert js.json("acervatorHeader.modeButton()")["mode"] == "stock"


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime, revealed):
    """Several panels on one page share one answer."""
    assert revealed is not None
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadHeader(); acervatorLoadHeader(); acervatorLoadHeader();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime, revealed):
    """The control for the check above. A counter that never incremented
    would report one call however many were made."""
    assert revealed is not None
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadHeader();")
    drain_events()
    js.run("acervatorHeader.forget(); acervatorLoadHeader();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(
    js: JsRuntime, revealed
):
    """A page opened without the preload script must say so, not draw a
    strip with no figures on it."""
    assert revealed is not None
    js.run("acervatorLoadHeader();")
    drain_events()
    assert js.json("acervatorHeader.isLoaded()") is False
    assert js.json("acervatorHeader.loadError()") == "the preload bridge is not present"


def test_a_refused_ask_is_not_remembered(js: JsRuntime, revealed):
    """A backend that was not running when the page opened must be
    reachable on the next ask, not left blank for the life of the page."""
    assert revealed is not None
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadHeader();"
    )
    drain_events()
    assert js.json("acervatorHeader.isLoaded()") is False
    assert js.json("acervatorHeader.loadError()") == "the Python backend is not running"
    js.run("acervatorLoadHeader();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorHeader.isLoaded()") is True


def test_the_page_names_the_strip_module_among_its_assets():
    """The renderer loads the module that ships with the repo, not a
    second copy under ``desktop``."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    refs = re.findall(r'src="([^"]+)"', html)
    named = [ref for ref in refs if ref.endswith("header_strip.js")]
    assert len(named) == 1, f"the page names {len(named)} strip modules"
    assert (INDEX_HTML.parent / named[0]).resolve() == MODULE_PATH
