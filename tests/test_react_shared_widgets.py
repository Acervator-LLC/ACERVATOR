"""Issue #128 Stage 3 unit 3 -- the React side of the shared widgets.

WHAT IS PROVED
==============
``src/gui/web/shared_widgets.js`` draws the stat card and the bot table
that ``src/gui/main_tabs/widgets_package_surface.py`` describes, and
carries no skin value of its own. Two sources of truth for one card is
the defect this unit exists to prevent, so the value agreement, the
rendered read-back and the no-literals scan are three halves of one
claim.

A colour or a size carried by exactly one design token is painted as
that CSS variable, resolved through ``design_tokens.js``, never copied.
A value carried by more than one token is painted from the surface: a
text size bound to a spacing step holding the same number would move
whenever that spacing moved.

HOW THE JAVASCRIPT IS RUN
=========================
Node is not installed and nothing here adds a JavaScript test runner.
Two engines already in the tree run the module instead. ``QJSEngine``
from ``PySide6.QtQml`` -- the engine ``tests/test_desktop_shell_assets.py``
already parses the shell with -- runs it as plain JavaScript and answers
in JSON. ``QWebEngineView`` loads the real ``desktop/renderer/index.html``
from disk, which is the only way to draw the components with the vendored
React under the page's own content-security policy.

THE CONTROLS
============
Every count here has a planted opposite that must be named. A card
field, a preset and a column added to one side alone are each named by
the reach checks. A colour, a size, a number and a real skin value
planted in the module file itself are each caught by the literal scan,
and the file is restored byte for byte with its hash read back. One
changed value is what proves the rendered read-back can report, and a
token rewritten on the page is what proves the card resolves through the
token rather than copying it.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui import design_system as ds
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import theme_engine_surface as tes
from src.gui.main_tabs import widgets_package_surface as wps
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "shared_widgets.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
THEMES_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body can plant into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2
SETTLE_MS = 500
NETWORK_SETTLE_MS = 1500

#: Python type -> the JavaScript type the same value has after the
#: bridge's ``json.dumps``. A value that changes shape in transit shows
#: as a disagreement between this map and ``acervatorWidgets.types()``.
JS_TYPE_OF = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "tuple": "object",
    "list": "object",
    "NoneType": "null",
}

PRESET_NAMES = tuple(wps.PRESETS)
FIRST_PRESET = PRESET_NAMES[0]
SKINNED_PRESET = PRESET_NAMES[1]
FIRST_FIELD = wps.CARD_FIELDS[0]
SIZE_FIELD = "label_size"

#: CSS spells ``bold`` as 700 in a computed style.
COMPUTED_BOLD = "700"
NO_BACKGROUND = "rgba(0, 0, 0, 0)"
NO_BORDER = "none"


# -- the shipped column specs ------------------------------------------


def shipped_specs() -> dict:
    """The column setups the three bot tables ship, as bridge params.

    Imported from the widgets that own them rather than retyped, so a
    label or a width changed in the product changes this drive too.
    """
    from src.gui import stock_main_window as smw
    from src.gui.widgets import bot_status_table as bst
    from src.gui.widgets import extractor_bot_table as ebt

    found = {
        "scrumming": bst.SCRUMMING_COLUMNS,
        "extractor": ebt.EXTRACTOR_COLUMNS,
        "stock": smw.STOCK_COLUMNS,
    }
    return {
        name: {
            "labels": list(spec.labels),
            "tooltips": {str(k): v for k, v in spec.tooltips.items()},
            "fixed_widths": {str(k): v for k, v in spec.fixed_widths.items()},
            "accessible_name": spec.accessible_name,
        }
        for name, spec in found.items()
    }


SPECS = shipped_specs()
SPEC_NAMES = tuple(SPECS)
FIRST_SPEC = SPEC_NAMES[0]


# -- the surface, as the bridge serialises it --------------------------


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON.

    ``src/core/desktop_bridge.py`` writes every response with
    ``json.dumps(..., ensure_ascii=True)``, so a tuple reaches the
    renderer as an array. Comparing the module against the raw Python
    dict would charge the module for that conversion.
    """
    return json.loads(json.dumps(wps.view_model(params), ensure_ascii=True))


def token_payload() -> dict:
    """The design-token surface's answer, for the variable resolver."""
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


def theme_payload() -> dict:
    """The theme surface's answer, for the second resolver table."""
    return json.loads(json.dumps(tes.view_model({}), ensure_ascii=True))


def card_payload(preset: str) -> dict:
    """One preset's card, labelled so two cards never read the same."""
    return bridge_payload(preset=preset, label=preset)


def table_payload(spec_name: str) -> dict:
    """One shipped column setup, driven through the surface."""
    return bridge_payload(spec=SPECS[spec_name])


# -- the JavaScript engine ---------------------------------------------


class JsRuntime(JsEngine):
    """A QJSEngine holding ``shared_widgets.js`` and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetWidgets"

    def load_tokens(self) -> None:
        """Run unit 1's own module and give it the real token table."""
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def load_themes(self, name: str) -> None:
        """Run unit 2's own module and select one theme."""
        self.run(THEMES_PATH.read_text(encoding="utf-8"))
        self.bind_json("THEMES", theme_payload())
        self.bind_json("THEME_NAME", name)
        self.run("acervatorSetThemes(JSON.parse(THEMES));")
        self.run("acervatorThemes.select(JSON.parse(THEME_NAME));")

    def preset(self, name: str) -> Any:
        self.bind_json("NAME", name)
        return self.json("acervatorWidgets.preset(JSON.parse(NAME))")

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
    """The module holding the surface's default card and empty table."""
    js.push(bridge_payload())
    return js


# -- 1. everything the surface publishes reaches the module ------------

#: Every field the surface publishes, and the module reader that answers
#: for it. A field with no reader is a value that stops at the bridge.
MODULE_READERS = {
    "card": "acervatorWidgets.card()",
    "table": "acervatorWidgets.table()",
    "presets": "acervatorWidgets.presets()",
    "card_fields": "acervatorWidgets.cardFields()",
    "card_defaults": "acervatorWidgets.cardDefaults()",
    "spec_fields": "acervatorWidgets.specFields()",
    "spec_defaults": "acervatorWidgets.specDefaults()",
    "exported_names": "acervatorWidgets.exportedNames()",
    "limits": "acervatorWidgets.limits()",
    "call_names": "acervatorWidgets.callNames()",
    "method": "acervatorWidgets.method",
    "actions": "acervatorWidgets.machinery().actions",
    "signals": "acervatorWidgets.machinery().signals",
    "timers": "acervatorWidgets.machinery().timers",
    "timer_delays_ms": "acervatorWidgets.machinery().timer_delays_ms",
    "bus_topics": "acervatorWidgets.machinery().bus_topics",
    "threads": "acervatorWidgets.machinery().threads",
}


def unreachable_fields(payload: dict) -> list:
    """Every field of ``payload`` no module reader answers for."""
    return sorted(set(payload) - set(MODULE_READERS))


def test_every_field_the_surface_publishes_reaches_the_module(js: JsRuntime):
    """The whole payload, field by field. A field the module never
    carries is a value that stops at the bridge, silently."""
    payload = bridge_payload(spec=SPECS[FIRST_SPEC], preset=SKINNED_PRESET)
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
        f"{len(differing)} of {len(payload)} published fields differ: "
        f"{sorted(differing)}"
    )
    assert len(MODULE_READERS) == len(payload)


def test_the_whole_payload_check_names_a_field_only_the_surface_holds():
    """The control, with a planted name. Without it a module that dropped
    a whole field would read as agreement."""
    payload = dict(bridge_payload())
    payload["planted_only_on_the_surface"] = []
    assert unreachable_fields(payload) == ["planted_only_on_the_surface"]


def test_the_module_holds_every_card_field_the_surface_publishes(loaded: JsRuntime):
    """A field the surface publishes that the card's skin never holds is
    a value the React card has nothing to paint with."""
    declared = sorted(wps.CARD_FIELDS)
    held = sorted(loaded.json("Object.keys(acervatorWidgets.skin())"))
    missing = sorted(set(declared) - set(held))
    extra = sorted(set(held) - set(declared))
    assert not missing, (
        f"{len(missing)} of {len(declared)} surface card fields never "
        f"reached the module: {missing}"
    )
    assert not extra, f"the module holds card fields the surface has none of: {extra}"
    assert len(held) == len(declared) == len(set(declared))


def test_the_card_field_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    """The control on the surface side. Without it a module that dropped
    a field would read as agreement."""
    payload = bridge_payload()
    del payload["card"]["skin"][FIRST_FIELD]
    js.push(payload)
    missing = set(wps.CARD_FIELDS) - set(
        js.json("Object.keys(acervatorWidgets.skin())")
    )
    assert missing == {
        FIRST_FIELD
    }, f"the check did not name the dropped field: {missing}"


def test_the_card_field_check_names_a_field_only_the_module_holds(js: JsRuntime):
    """The control on the module side, with a planted name."""
    payload = bridge_payload()
    payload["card"]["skin"]["planted_only_in_js"] = payload["card"]["skin"][FIRST_FIELD]
    js.push(payload)
    extra = set(js.json("Object.keys(acervatorWidgets.skin())")) - set(wps.CARD_FIELDS)
    assert extra == {
        "planted_only_in_js"
    }, f"the check did not name the planted field: {extra}"


def test_the_module_holds_every_card_style_the_surface_publishes(loaded: JsRuntime):
    """A preset the surface publishes that the module never holds is a
    skin a screen cannot draw."""
    declared = sorted(PRESET_NAMES)
    held = sorted(loaded.json("acervatorWidgets.presetNames()"))
    assert held == declared, f"presets differ: surface {declared}, module {held}"


def test_the_card_style_check_names_a_style_only_the_surface_holds(js: JsRuntime):
    """The control on the surface side."""
    payload = bridge_payload()
    del payload["presets"][FIRST_PRESET]
    js.push(payload)
    missing = set(PRESET_NAMES) - set(js.json("acervatorWidgets.presetNames()"))
    assert missing == {
        FIRST_PRESET
    }, f"the check did not name the dropped style: {missing}"


def test_the_card_style_check_names_a_style_only_the_module_holds(js: JsRuntime):
    """The control on the module side, with a planted name."""
    payload = bridge_payload()
    payload["presets"]["planted_only_in_js"] = dict(payload["presets"][FIRST_PRESET])
    js.push(payload)
    extra = set(js.json("acervatorWidgets.presetNames()")) - set(PRESET_NAMES)
    assert extra == {
        "planted_only_in_js"
    }, f"the check did not name the planted style: {extra}"


@pytest.mark.parametrize("spec_name", SPEC_NAMES)
def test_the_module_holds_every_column_the_surface_publishes(js: JsRuntime, spec_name):
    """A column the surface publishes that the module never holds is a
    header the operator would not see."""
    payload = table_payload(spec_name)
    js.push(payload)
    declared = payload["table"]["headers"]
    held = js.json("acervatorWidgets.headers()")
    assert held == declared, f"{spec_name}: headers differ: {declared} vs {held}"
    assert len(held) == len(SPECS[spec_name]["labels"])


def test_the_column_check_names_a_column_only_the_surface_holds(js: JsRuntime):
    """The control on the surface side."""
    payload = table_payload(FIRST_SPEC)
    dropped = payload["table"]["headers"].pop()
    js.push(payload)
    held = js.json("acervatorWidgets.headers()")
    assert len(held) == len(SPECS[FIRST_SPEC]["labels"]) - 1
    assert dropped not in held[len(held) - 1 :]


def test_the_column_check_names_a_column_only_the_module_holds(js: JsRuntime):
    """The control on the module side, with a planted header."""
    payload = table_payload(FIRST_SPEC)
    payload["table"]["headers"].append("planted_only_in_js")
    js.push(payload)
    held = js.json("acervatorWidgets.headers()")
    extra = set(held) - set(payload["table"]["spec"]["labels"])
    assert extra == {
        "planted_only_in_js"
    }, f"the check did not name the planted header: {extra}"


def test_the_module_holds_the_declared_name_lists(loaded: JsRuntime):
    """The schema lists the surface publishes, carried across unchanged."""
    assert loaded.json("acervatorWidgets.cardFields()") == list(wps.CARD_FIELDS)
    assert loaded.json("acervatorWidgets.specFields()") == list(wps.SPEC_FIELDS)
    assert loaded.json("acervatorWidgets.exportedNames()") == list(wps.EXPORTED_NAMES)
    assert loaded.json("acervatorWidgets.callNames()") == list(wps.CALL_NAMES)
    assert loaded.json("acervatorWidgets.method") == wps.METHOD


def test_the_module_holds_every_limit_the_surface_publishes(loaded: JsRuntime):
    """The border width, the border kind and the amount's weight all
    reach the module rather than being written into it."""
    expected = bridge_payload()["limits"]
    assert loaded.json("acervatorWidgets.limits()") == expected


def test_the_module_holds_the_defaults_the_surface_publishes(loaded: JsRuntime):
    """The card and spec defaults, carried across unchanged."""
    expected = bridge_payload()
    assert loaded.json("acervatorWidgets.cardDefaults()") == expected["card_defaults"]
    assert loaded.json("acervatorWidgets.specDefaults()") == expected["spec_defaults"]


# -- 2. no skin value is written in the JavaScript ---------------------


def as_css(value: Any) -> set:
    """One published value, in every spelling a stylesheet could carry.

    A size crosses the bridge as a bare number and reaches CSS with a
    unit, so both spellings count as the same copied value.
    """
    printed = str(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {printed}
    return {printed, printed + "px"}


def skin_values() -> set:
    """Every value that skins a card or a table, as printed text.

    The schema NAME lists are left out on purpose: the surface publishes
    its own field names as values, so a module that reads a field by name
    would read as spelling a value out.
    """
    payload = bridge_payload(spec=SPECS[FIRST_SPEC])
    found: set = set()
    for skin in payload["presets"].values():
        for value in skin.values():
            if isinstance(value, list):
                for one in value:
                    found |= as_css(one)
            elif value is not None:
                found |= as_css(value)
    for value in payload["limits"].values():
        found |= as_css(value)
    card = payload["card"]
    found.add(str(card["frame_shape"]))
    found.add(card["label"]["style_sheet"])
    found.add(card["value"]["style_sheet"])
    found.add(card["value"]["default_text"])
    table = payload["table"]
    found.add(str(table["selection_behaviour"]))
    found.add(str(table["edit_triggers"]))
    found.update(str(one) for one in table["headers"])
    found.update(str(one) for one in table["resize_modes"])
    for width in payload["table"]["fixed_widths"].values():
        found |= as_css(width)
    found.discard("")
    return found


def other_module_values() -> set:
    """Every value the token and theme tables carry, in CSS spelling.

    The module resolves through both, so a value copied here from either
    would be a second source of truth for the same colour or size.
    """
    found: set = set()
    for value in dss.TOKENS.values():
        found |= as_css(value)
    for theme in tes.THEMES.values():
        for value in theme.values():
            found |= as_css(value)
    found.discard("")
    return found


SKIN_VALUES = skin_values()
TOKEN_VALUES = other_module_values()
MODULE_LITERALS = js_literals(MODULE_SOURCE)


def test_the_module_writes_no_number():
    """A text size, a padding, a corner rounding or a border width typed
    here is a second source of truth for a value the surface owns."""
    assert not MODULE_LITERALS["numbers"], (
        "shared_widgets.js holds numeric literals: " f"{MODULE_LITERALS['numbers']}"
    )


def test_the_module_writes_no_colour():
    """A colour typed here drifts from the surface the next time a card
    skin changes, and nothing reports the drift."""
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"shared_widgets.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_skin_value():
    """A skin value spelled out as text: a colour, a size, a padding, a
    header, a frame shape or a whole Qt style sheet."""
    written = sorted(set(MODULE_LITERALS["strings"]) & SKIN_VALUES)
    assert not written, f"shared_widgets.js spells out skin values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    """The table the module resolves through. A token value copied here
    would be a second source of truth for the same colour."""
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"shared_widgets.js spells out token values: {written}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    """The scan parses no regular expression, so a value inside one would
    pass unread. The module carries none."""
    assert not MODULE_LITERALS["slashes"], (
        "shared_widgets.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {MODULE_LITERALS['slashes']}"
    )


PLANTED_LINES = {
    "colour": 'var planted = "#00ffcc";',
    "size": 'var planted = "' + str(wps.DEFAULT_LABEL_SIZE_PX) + 'px";',
    "padding": 'var planted = "' + str(wps.DEFAULT_PADDING_PX[0]) + 'px";',
    "radius": "var planted = " + str(wps.DEFAULT_RADIUS_PX) + ";",
    "number": "var planted = 12;",
    "skin_value": 'var planted = "' + wps.STOCK_CARD["surface"] + '";',
    "card_name": 'var planted = "' + wps.STOCK_CARD["accessible_name"] + '";',
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


# -- 3. both sides agree, value for value ------------------------------


@pytest.mark.parametrize("preset", PRESET_NAMES)
def test_every_value_of_every_card_style_agrees_with_the_surface(
    js: JsRuntime, preset: str
):
    """The whole claim of this unit for the card. A single disagreement
    means a React card does not match the one Qt paints."""
    payload = card_payload(preset)
    js.push(payload)
    expected = payload["presets"][preset]
    actual = js.preset(preset)
    differing = {
        field: (expected[field], actual.get(field))
        for field in expected
        if actual.get(field) != expected[field]
    }
    assert (
        not differing
    ), f"{preset}: {len(differing)} of {len(expected)} values differ: {differing}"
    assert len(actual) == len(expected) == len(wps.CARD_FIELDS)
    assert js.json("acervatorWidgets.skin()") == expected


def test_the_card_style_value_check_names_a_changed_value(js: JsRuntime):
    """The control. Two real payloads differing by one value must not
    compare equal."""
    payload = card_payload(SKINNED_PRESET)
    payload["presets"][SKINNED_PRESET]["surface"] += "0"
    js.push(payload)
    expected = card_payload(SKINNED_PRESET)["presets"][SKINNED_PRESET]
    actual = js.preset(SKINNED_PRESET)
    differing = sorted(f for f in expected if actual.get(f) != expected[f])
    assert differing == ["surface"], f"the check named {differing}"


@pytest.mark.parametrize("spec_name", SPEC_NAMES)
def test_every_column_of_every_spec_agrees_with_the_surface(
    js: JsRuntime, spec_name: str
):
    """The whole claim of this unit for the table, on the three column
    setups the shipped bot tables carry."""
    payload = table_payload(spec_name)
    js.push(payload)
    expected = payload["table"]
    actual = js.json("acervatorWidgets.table()")
    differing = {
        field: (expected[field], actual.get(field))
        for field in expected
        if actual.get(field) != expected[field]
    }
    assert (
        not differing
    ), f"{spec_name}: {len(differing)} of {len(expected)} fields differ: {differing}"
    assert js.json("acervatorWidgets.declaredColumns()") == expected["column_count"]
    assert js.json("acervatorWidgets.heldColumns()") == len(expected["headers"])


def test_the_column_value_check_names_a_changed_header(js: JsRuntime):
    """The control. One header changed must read as one difference."""
    payload = table_payload(FIRST_SPEC)
    payload["table"]["headers"][0] += "0"
    js.push(payload)
    expected = table_payload(FIRST_SPEC)["table"]
    actual = js.json("acervatorWidgets.table()")
    differing = sorted(f for f in expected if actual.get(f) != expected[f])
    assert differing == ["headers"], f"the check named {differing}"


@pytest.mark.parametrize("preset", PRESET_NAMES)
def test_every_skin_value_arrives_as_the_type_the_surface_holds(
    js: JsRuntime, preset: str
):
    """A value that changes shape in transit reads correct and skins
    wrong: a number where a colour belongs paints nothing."""
    js.push(card_payload(preset))
    expected = {
        field: JS_TYPE_OF[type(value).__name__]
        for field, value in wps.PRESETS[preset].items()
    }
    js.bind_json("NAME", preset)
    actual = js.json("acervatorWidgets.types(JSON.parse(NAME))")
    differing = {
        f: (kind, actual.get(f))
        for f, kind in expected.items()
        if actual.get(f) != kind
    }
    assert not differing, f"{preset}: {len(differing)} values changed type: {differing}"


def test_the_module_reports_only_what_it_was_given(js: JsRuntime):
    """Every value comes from the payload and none from the module. A
    payload of values the surface never held comes back unchanged."""
    invented = {field: "given-" + field for field in wps.CARD_FIELDS}
    js.push(
        {
            "card_fields": list(wps.CARD_FIELDS),
            "card": {"skin": invented},
            "presets": {FIRST_PRESET: invented},
        }
    )
    assert js.json("acervatorWidgets.skin()") == invented
    assert not set(js.json("acervatorWidgets.skin()").values()) & SKIN_VALUES


def test_a_per_call_recolour_reaches_no_data_field_of_the_payload():
    """A card whose amount is recoloured for one call publishes that
    colour in its Qt style sheet and in no data field.

    The React card paints from the skin, so it cannot follow a per-call
    recolour. Reported here rather than repaired: the surface is not this
    unit's file.
    """
    asked = ds.SUCCESS
    payload = bridge_payload(
        preset=SKINNED_PRESET, set_value=wps.DEFAULT_VALUE, set_colour=asked
    )
    card = payload["card"]
    assert wps.VALUE_RECOLOURED in card["calls"]
    assert asked in card["value"]["style_sheet"]
    carried = sorted(field for field, value in card["skin"].items() if value == asked)
    assert not carried, f"the skin does carry the recolour, in {carried}"


def test_the_recolour_check_names_a_colour_a_data_field_does_carry():
    """The control for the check above. A walk that found nothing
    whatever the payload held would pass it on any card."""
    payload = bridge_payload(preset=SKINNED_PRESET)
    skin = payload["card"]["skin"]
    carried = sorted(field for field, value in skin.items() if value == skin["surface"])
    assert carried == ["surface"], f"the walk named {carried}"


def test_the_card_calls_reach_the_module_unchanged(js: JsRuntime):
    """The calls the shipped card makes, carried across so a screen can
    be read step by step."""
    payload = bridge_payload(preset=SKINNED_PRESET, set_value=wps.DEFAULT_VALUE)
    js.push(payload)
    assert js.json("acervatorWidgets.calls()") == payload["card"]["calls"]
    assert wps.FRAME_SKINNED in payload["card"]["calls"]


# -- the values resolved through the token and theme modules -----------


def test_every_card_colour_resolves_to_a_token_carrying_that_colour(js: JsRuntime):
    """A colour is painted through the one token that holds it, so a
    token changed in Python moves the card without touching this file."""
    js.load_tokens()
    tokens = token_payload()["tokens"]
    named = 0
    for preset, skin in wps.PRESETS.items():
        for field in ("label_color", "value_color", "surface", "border"):
            value = skin[field]
            if value is None:
                continue
            name = js.variable_for(value)
            assert name is not None, f"{preset}.{field} resolved to no token: {value}"
            assert tokens[name] == value, f"{name} carries {tokens[name]}, not {value}"
            named += 1
    assert named, "no card colour was resolved at all"


def test_a_number_carried_by_more_than_one_token_resolves_to_none(js: JsRuntime):
    """Binding a text size to a spacing step holding the same number
    would move the text whenever that spacing moved."""
    js.load_tokens()
    tokens = token_payload()["tokens"]
    aliases = token_payload()["alias_targets"]
    value = wps.DEFAULT_LABEL_SIZE_PX
    carriers = [
        name for name, held in tokens.items() if held == value and name not in aliases
    ]
    assert len(carriers) > 1, f"only {carriers} carry {value}; the check cannot report"
    assert js.variable_for(value) is None


def test_a_number_carried_by_one_token_resolves_to_that_token(js: JsRuntime):
    """The positive control for the check above. A number one token alone
    carries is painted through it."""
    js.load_tokens()
    tokens = token_payload()["tokens"]
    aliases = token_payload()["alias_targets"]
    value = wps.METRIC_CARD["radius"]
    carriers = [
        name for name, held in tokens.items() if held == value and name not in aliases
    ]
    assert carriers == ["RADIUS_CARD"], f"{value} is carried by {carriers}"
    assert js.variable_for(value) == "RADIUS_CARD"


def test_a_value_no_token_carries_resolves_to_none(js: JsRuntime):
    """The control for the resolver. A value off the table is painted
    from the surface rather than through a variable nothing answers."""
    js.load_tokens()
    assert js.variable_for("no-token-carries-this") is None


def test_the_resolver_answers_from_the_theme_when_no_token_carries_a_value(
    js: JsRuntime,
):
    """The second table. A value the token list has none of, that one
    field of the selected theme carries, is painted through that field."""
    js.load_tokens()
    js.load_themes(tes.THEME_NAMES[0])
    painted = js.json("acervatorThemes.painted()")
    tokens = token_payload()["tokens"]
    carried = {str(value) for value in tokens.values()}
    only_theme = sorted(
        field
        for field, value in painted.items()
        if isinstance(value, str)
        and str(value) not in carried
        and sum(1 for other in painted.values() if other == value) == 1
    )
    assert only_theme, "every theme value is also a token; the check cannot report"
    field = only_theme[0]
    assert js.variable_for(painted[field]) == field


def test_the_resolver_reports_no_name_with_neither_module_on_the_page(js: JsRuntime):
    """A page that never loaded the token module paints from the surface
    rather than through a variable nothing would answer."""
    assert js.variable_for(wps.STOCK_CARD["surface"]) is None


# -- 4. hostile payloads ------------------------------------------------


def test_a_card_style_the_payload_omits_is_named_as_missing(js: JsRuntime):
    """The surface sent a card with no skin at all."""
    payload = bridge_payload()
    del payload["card"]["skin"]
    report = js.push(payload)
    assert {
        "where": "card",
        "field": None,
        "fault": "missing",
        "detail": None,
    } in report["faults"]
    assert js.json("acervatorWidgets.skin()") == {}


def test_a_missing_card_style_shortens_the_held_count_not_the_declared_count(
    js: JsRuntime,
):
    """C72. The two counts are kept apart, so a payload that promises
    more fields than it carries reads as a difference."""
    payload = bridge_payload()
    del payload["card"]["skin"]
    report = js.push(payload)
    assert report["declared"]["fields"] == len(wps.CARD_FIELDS)
    assert report["held"]["fields"] == 0


def test_a_null_card_style_is_named_and_holds_nothing(js: JsRuntime):
    """A null is reported, not swapped for a skin of the module's own."""
    payload = bridge_payload()
    payload["presets"][FIRST_PRESET] = None
    report = js.push(payload)
    assert {
        "where": "preset:" + FIRST_PRESET,
        "field": None,
        "fault": "null",
        "detail": None,
    } in report["faults"]
    assert js.preset(FIRST_PRESET) is None


def test_a_colour_that_is_a_number_is_reported_by_type_and_raises_no_fault(
    js: JsRuntime,
):
    """The surface publishes no default for either colour, so the module
    has no type to hold the value against. It passes the number on and
    names the type it received."""
    payload = bridge_payload()
    payload["card"]["skin"]["label_color"] = 7
    js.push(payload)
    assert js.json("acervatorWidgets.skin()")["label_color"] == 7
    assert js.json("acervatorWidgets.types()")["label_color"] == "number"
    kinds = [f["fault"] for f in js.json("acervatorWidgets.faults()")]
    assert "wrong-type" not in kinds


def test_the_type_check_names_the_number_against_the_surface(js: JsRuntime):
    """The control for the check above, read against the surface's own
    types. A check blind to shape would report agreement here."""
    payload = bridge_payload()
    payload["card"]["skin"]["label_color"] = 7
    js.push(payload)
    expected = {
        field: JS_TYPE_OF[type(value).__name__]
        for field, value in wps.DEFAULT_CARD.items()
    }
    actual = js.json("acervatorWidgets.types()")
    differing = sorted(f for f, kind in expected.items() if actual.get(f) != kind)
    assert differing == ["label_color"]


def test_a_size_that_is_text_is_named_as_the_wrong_type(js: JsRuntime):
    """The surface's own default for a size is a number, so the module
    has a type to hold it against and reports the text."""
    payload = bridge_payload()
    payload["card"]["skin"][SIZE_FIELD] = "13px"
    report = js.push(payload)
    assert {
        "where": "card",
        "field": SIZE_FIELD,
        "fault": "wrong-type",
        "detail": "string",
    } in report["faults"]
    assert js.json("acervatorWidgets.skin()")[SIZE_FIELD] == "13px"


def test_a_padding_of_the_wrong_length_is_named(js: JsRuntime):
    """The surface publishes how many parts a padding has, so a padding
    of another length is reported rather than stretched to fit."""
    payload = bridge_payload()
    payload["card"]["skin"]["padding"] = payload["card"]["skin"]["padding"][:-1]
    report = js.push(payload)
    assert {
        "where": "card",
        "field": "padding",
        "fault": "padding-length",
        "detail": wps.PADDING_PARTS - 1,
    } in report["faults"]


def test_the_padding_length_check_is_quiet_on_a_padding_of_the_right_length(
    loaded: JsRuntime,
):
    """The negative control. Every shipped padding passes."""
    kinds = [f["fault"] for f in loaded.json("acervatorWidgets.faults()")]
    assert "padding-length" not in kinds


def test_a_column_spec_with_no_columns_holds_nothing_and_raises_no_fault(
    js: JsRuntime,
):
    """An empty table is what the shipped default carries, so it is a
    table with no columns, not a fault."""
    report = js.push(bridge_payload())
    assert report["declared"]["columns"] == 0
    assert report["held"]["columns"] == 0
    assert js.json("acervatorWidgets.headers()") == []
    assert [f["fault"] for f in report["faults"]] == []


def test_a_column_count_that_disagrees_with_the_headers_is_named(js: JsRuntime):
    """C72 for the table. A count that promises more columns than the
    headers carry reads as a difference, never as a full table."""
    payload = table_payload(FIRST_SPEC)
    payload["table"]["headers"].pop()
    report = js.push(payload)
    declared = payload["table"]["column_count"]
    assert {
        "where": "table",
        "field": "column_count",
        "fault": "column-count",
        "detail": {"declared": declared, "held": declared - 1},
    } in report["faults"]
    assert report["declared"]["columns"] == declared
    assert report["held"]["columns"] == declared - 1


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    """A bridge answering with a string or a number draws nothing."""
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorWidgets.isLoaded()") is False
        assert js.json("acervatorWidgets.presetNames()") == []
        assert report["declared"] is None
        assert report["held"] is None
        assert [f["fault"] for f in report["faults"]] == ["not-an-object"]


def test_a_name_the_payload_never_carried_is_not_a_card_style(js: JsRuntime):
    """Every JavaScript object inherits names like ``constructor``.
    Reading one as a preset would hand a screen a function where a skin
    belongs."""
    js.push(bridge_payload())
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        js.bind_json("NAME", inherited)
        kind = js.json("typeof acervatorWidgets.preset(JSON.parse(NAME))")
        assert kind == "undefined", f"preset({inherited}) returned a {kind}"
        assert js.json("acervatorWidgets.types(JSON.parse(NAME))") == {}


def test_the_inherited_name_check_still_reads_a_real_card_style(js: JsRuntime):
    """The control for the check above. A reader that answered nothing
    for every name would pass it while serving no skin."""
    js.push(bridge_payload())
    assert js.preset(FIRST_PRESET) == bridge_payload()["presets"][FIRST_PRESET]
    assert js.json("acervatorWidgets.types(JSON.parse(NAME))") != {}


# -- the bridge ask ----------------------------------------------------


BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    """The module reaches Python the one way the page allows: the preload
    bridge, naming the method the surface registers."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadWidgets();")
    drain_events()
    assert js.json("window.CALLS") == [[wps.METHOD, "{}"]]
    assert js.json("acervatorWidgets.isLoaded()") is True


def test_the_module_passes_a_caller_s_parameters_to_the_surface(js: JsRuntime):
    """A caller that wants one preset sends the name the surface reads."""
    js.bind_json("PAYLOAD", card_payload(SKINNED_PRESET))
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", {"preset": SKINNED_PRESET})
    js.run("acervatorLoadWidgets(JSON.parse(WANTED));")
    drain_events()
    assert js.json("window.CALLS") == [
        [wps.METHOD, '{"preset":"' + SKINNED_PRESET + '"}']
    ]
    assert (
        js.json("acervatorWidgets.skin()")
        == card_payload(SKINNED_PRESET)["presets"][SKINNED_PRESET]
    )


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    """Several panels on one page share one answer."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadWidgets(); acervatorLoadWidgets(); acervatorLoadWidgets();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    """The control for the check above. A counter that never incremented
    would report one call however many were made."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadWidgets();")
    drain_events()
    js.run("acervatorWidgets.forget(); acervatorLoadWidgets();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    """A page opened without the preload script must say so, not draw a
    half-skinned card."""
    js.run("acervatorLoadWidgets();")
    drain_events()
    assert js.json("acervatorWidgets.isLoaded()") is False
    assert (
        js.json("acervatorWidgets.loadError()") == "the preload bridge is not present"
    )


def test_a_refused_ask_is_not_remembered(js: JsRuntime):
    """A backend that was not running when the page opened must be
    reachable on the next ask, not left blank for the life of the page."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(
        "window.TRIES = 0;"
        "window.acervator = { call: function () {"
        "  window.TRIES += 1;"
        "  if (window.TRIES === 1) {"
        "    return Promise.reject(new Error('the Python backend is not running')); }"
        "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
        "acervatorLoadWidgets();"
    )
    drain_events()
    assert js.json("acervatorWidgets.isLoaded()") is False
    assert (
        js.json("acervatorWidgets.loadError()") == "the Python backend is not running"
    )
    js.run("acervatorLoadWidgets();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorWidgets.isLoaded()") is True


# -- 5. the components, drawn in the real page -------------------------


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
                if self.js("typeof window.acervatorWidgets") == "object":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined acervatorWidgets: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
            + ", tokens "
            + str(self.js("typeof window.acervatorTokens"))
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


WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)

HOST = (
    "window.HOST = document.createElement('div');"
    "document.body.appendChild(window.HOST);"
)

READ_CARD = (
    "(function () {"
    "  var frame = window.HOST.firstChild;"
    "  var caption = frame.querySelector('[data-card-part=\"label\"]');"
    "  var amount = frame.querySelector('[data-card-part=\"value\"]');"
    "  var f = getComputedStyle(frame);"
    "  var c = getComputedStyle(caption);"
    "  var a = getComputedStyle(amount);"
    "  return JSON.stringify({"
    "    aria: frame.getAttribute('aria-label'),"
    "    cardClass: frame.getAttribute('data-card-class'),"
    "    frameShape: frame.getAttribute('data-frame-shape'),"
    "    labelText: caption.textContent,"
    "    valueText: amount.textContent,"
    "    paddingLeft: f.paddingLeft, paddingTop: f.paddingTop,"
    "    paddingRight: f.paddingRight, paddingBottom: f.paddingBottom,"
    "    background: f.backgroundColor, borderStyle: f.borderTopStyle,"
    "    borderWidth: f.borderTopWidth, borderColor: f.borderTopColor,"
    "    radius: f.borderTopLeftRadius,"
    "    labelColor: c.color, labelSize: c.fontSize, spacing: c.marginBottom,"
    "    valueColor: a.color, valueSize: a.fontSize, valueWeight: a.fontWeight"
    "  }); })()"
)

READ_TABLE = (
    "(function () {"
    "  var table = window.HOST.firstChild;"
    "  var cells = Array.prototype.slice.call(table.querySelectorAll('th'));"
    "  return JSON.stringify({"
    "    aria: table.getAttribute('aria-label'),"
    "    tableClass: table.getAttribute('data-table-class'),"
    "    declared: table.getAttribute('data-declared-columns'),"
    "    held: table.getAttribute('data-held-columns'),"
    "    alternating: table.getAttribute('data-alternating-rows'),"
    "    selection: table.getAttribute('data-selection-behaviour'),"
    "    editTriggers: table.getAttribute('data-edit-triggers'),"
    "    verticalHeader: table.getAttribute('data-vertical-header-visible'),"
    "    headers: cells.map(function (c) { return c.textContent; }),"
    "    modes: cells.map(function (c) {"
    "      return c.getAttribute('data-resize-mode'); }),"
    "    titles: cells.map(function (c) { return c.getAttribute('title'); }),"
    # A table redistributes its columns, so a cell's used width is a
    # layout fact. What the cell ASKED for is resolved on a plain element
    # instead, which still runs the var() and calc() the component wrote.
    "    widths: cells.map(function (c) {"
    "      if (!c.style.width) { return null; }"
    "      var probe = document.createElement('div');"
    "      probe.style.width = c.style.width;"
    "      document.body.appendChild(probe);"
    "      var asked = getComputedStyle(probe).width;"
    "      probe.remove();"
    "      return asked; })"
    "  }); })()"
)


def rgb_text(colour: str) -> str:
    """Chromium's own spelling of a hex colour in a computed style."""
    body = colour.lstrip("#")
    if len(body) == 3:
        body = "".join(one * 2 for one in body)
    parts = [int(body[at : at + 2], 16) for at in (0, 2, 4)]
    return "rgb({}, {}, {})".format(*parts)


def pixels(value: Any) -> str:
    """One layout number as a computed CSS length."""
    return str(value) + "px"


def js_bool(value: bool) -> str:
    """One true or false as JavaScript prints it into an attribute."""
    return "true" if value else "false"


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


def draw_card(browser: Browser, payload: dict) -> dict:
    """Draw one card into the page and read the applied values back."""
    browser.js(HOST)
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetWidgets(JSON.parse(window.PAYLOAD));"
        "acervatorWidgets.renderCard(window.HOST);"
    )
    return json.loads(browser.js(READ_CARD))


def draw_table(browser: Browser, payload: dict) -> dict:
    """Draw one table into the page and read the applied values back."""
    browser.js(HOST)
    give_tokens(browser)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetWidgets(JSON.parse(window.PAYLOAD));"
        "acervatorWidgets.renderTable(window.HOST);"
    )
    return json.loads(browser.js(READ_TABLE))


def probe_border_width(browser: Browser, payload: dict) -> str:
    """How this browser draws the surface's own border width.

    Chromium snaps a border to whole device pixels, so one CSS pixel
    reads back as 0.8 on a 125 per cent display. The probe is styled
    straight from the payload and never through the module, so the
    comparison states a product fact on any host.
    """
    limits = payload["limits"]
    return browser.js(
        "(function () {"
        "  var probe = document.createElement('div');"
        "  probe.style.borderStyle = " + json.dumps(limits["border_kind"]) + ";"
        "  probe.style.borderWidth = "
        + json.dumps(pixels(limits["border_width_px"]))
        + ";"
        "  document.body.appendChild(probe);"
        "  var drawn = getComputedStyle(probe).borderTopWidth;"
        "  probe.remove();"
        "  return drawn; })()"
    )


def described_card(payload: dict, border_width: str) -> dict:
    """What the surface's payload says the drawn card should show."""
    card = payload["card"]
    skin = card["skin"]
    limits = payload["limits"]
    described = {
        "aria": card["accessible_name"] or None,
        "cardClass": card["class_name"],
        "frameShape": card["frame_shape"],
        "labelText": card["label"]["text"],
        "valueText": card["value"]["text"],
        "paddingLeft": pixels(skin["padding"][0]),
        "paddingTop": pixels(skin["padding"][1]),
        "paddingRight": pixels(skin["padding"][2]),
        "paddingBottom": pixels(skin["padding"][3]),
        "labelColor": rgb_text(skin["label_color"]),
        "labelSize": pixels(skin["label_size"]),
        "spacing": pixels(skin["spacing"]),
        "valueColor": rgb_text(skin["value_color"]),
        "valueSize": pixels(skin["value_size"]),
        "valueWeight": COMPUTED_BOLD,
    }
    if skin["surface"] is None:
        described["background"] = NO_BACKGROUND
        described["borderStyle"] = NO_BORDER
        return described
    described["background"] = rgb_text(skin["surface"])
    described["borderStyle"] = limits["border_kind"]
    described["borderWidth"] = border_width
    described["borderColor"] = rgb_text(skin["border"])
    described["radius"] = pixels(skin["radius"])
    return described


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    """``script-src 'self'`` admits the module. A policy that refused it
    would leave the page with no widget API at all."""
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorWidgets") == "object"
    assert browser.js("typeof window.acervatorSetWidgets") == "function"
    assert browser.js("typeof window.acervatorLoadWidgets") == "function"


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
    """Drawing both components raises no policy violation, so nothing in
    the module reaches for the network."""
    browser.js(WATCH_VIOLATIONS)
    draw_card(browser, card_payload(SKINNED_PRESET))
    draw_table(browser, table_payload(FIRST_SPEC))
    browser.settle(SETTLE_MS)
    assert browser.parsed("window.VIOLATIONS") == []


@pytest.mark.parametrize("preset", PRESET_NAMES)
def test_the_drawn_card_matches_what_the_surface_describes(
    browser: Browser, preset: str
):
    """The values read back off the rendered document, against the
    payload that produced them."""
    payload = card_payload(preset)
    drawn = draw_card(browser, payload)
    described = described_card(payload, probe_border_width(browser, payload))
    differing = {
        field: (value, drawn.get(field))
        for field, value in described.items()
        if drawn.get(field) != value
    }
    assert not differing, (
        f"{preset}: {len(differing)} of {len(described)} drawn values "
        f"differ: {differing}"
    )


def test_the_border_width_probe_draws_a_border_this_browser_can_see(browser: Browser):
    """The control for the probe. A probe reading zero would agree with a
    card that drew no border at all."""
    drawn = probe_border_width(browser, bridge_payload())
    assert drawn != "0px", "the probe drew no border, so it can prove nothing"


def test_the_drawn_card_check_names_one_changed_value(browser: Browser):
    """The control. A read that returned the same text whatever was drawn
    would report agreement on a changed colour."""
    payload = card_payload(SKINNED_PRESET)
    payload["card"]["skin"]["label_color"] = dss.CARD_METRIC_LABEL
    drawn = draw_card(browser, payload)
    described = described_card(
        card_payload(SKINNED_PRESET), probe_border_width(browser, payload)
    )
    differing = sorted(f for f, v in described.items() if drawn.get(f) != v)
    assert differing == ["labelColor"], f"the check named {differing}"
    assert drawn["labelColor"] == rgb_text(dss.CARD_METRIC_LABEL)


def test_the_drawn_card_follows_the_token_it_is_painted_through(browser: Browser):
    """What proves the card resolves through the token module rather than
    copying it: the token is rewritten on the page and the card moves."""
    payload = card_payload(SKINNED_PRESET)
    before = draw_card(browser, payload)
    assert before["background"] == rgb_text(payload["card"]["skin"]["surface"])
    browser.js(
        "document.documentElement.style.setProperty('--CARD_STOCK_SURFACE', "
        + json.dumps(dss.CARD_METRIC_SURFACE)
        + ");"
    )
    after = json.loads(browser.js(READ_CARD))
    changed = sorted(f for f in before if after.get(f) != before[f])
    assert changed == ["background"], f"the token moved {changed}"
    assert after["background"] == rgb_text(dss.CARD_METRIC_SURFACE)


def test_the_drawn_card_follows_the_token_behind_a_size(browser: Browser):
    """A size is scaled to pixels rather than read as one, so it takes a
    different path through CSS than a colour and needs its own control.

    A token holds a bare number. A card whose corner rounding did not
    reach the stylesheet would draw a square corner and still agree with
    a check that only read colours.
    """
    payload = card_payload("metric")
    before = draw_card(browser, payload)
    assert before["radius"] == pixels(payload["card"]["skin"]["radius"])
    moved = dss.RADIUS_LG
    assert moved != payload["card"]["skin"]["radius"]
    browser.js(
        "document.documentElement.style.setProperty('--RADIUS_CARD', "
        + json.dumps(str(moved))
        + ");"
    )
    after = json.loads(browser.js(READ_CARD))
    changed = sorted(f for f in before if after.get(f) != before[f])
    assert changed == ["radius"], f"the token moved {changed}"
    assert after["radius"] == pixels(moved)


def test_a_card_with_no_surface_paints_no_frame(browser: Browser):
    """The default skin writes no frame rule in Qt, so the React card
    draws no background and no border either."""
    drawn = draw_card(browser, card_payload(FIRST_PRESET))
    assert bridge_payload()["card"]["frame_style_sheet"] == wps.NO_FRAME_STYLE
    assert drawn["background"] == NO_BACKGROUND
    assert drawn["borderStyle"] == NO_BORDER


@pytest.mark.parametrize("spec_name", SPEC_NAMES)
def test_the_drawn_table_matches_what_the_surface_describes(
    browser: Browser, spec_name: str
):
    """Every header, resize mode, tooltip and fixed width read back off
    the rendered document."""
    payload = table_payload(spec_name)
    drawn = draw_table(browser, payload)
    table = payload["table"]
    assert drawn["headers"] == table["headers"]
    assert drawn["modes"] == table["resize_modes"]
    assert drawn["titles"] == [tip or None for tip in table["tooltips"]]
    assert drawn["declared"] == str(table["column_count"])
    assert drawn["held"] == str(len(table["headers"]))
    assert drawn["tableClass"] == table["class_name"]
    assert drawn["aria"] == (table["accessible_name"] or None)
    assert drawn["alternating"] == js_bool(table["alternating_row_colours"])
    assert drawn["selection"] == table["selection_behaviour"]
    assert drawn["editTriggers"] == table["edit_triggers"]
    assert drawn["verticalHeader"] == js_bool(table["vertical_header_visible"])
    for at, width in table["fixed_widths"].items():
        assert drawn["widths"][int(at)] == pixels(width)


def test_the_drawn_table_check_names_one_changed_header(browser: Browser):
    """The control. One header changed must read as one difference."""
    payload = table_payload(FIRST_SPEC)
    payload["table"]["headers"][0] += "0"
    drawn = draw_table(browser, payload)
    original = table_payload(FIRST_SPEC)["table"]["headers"]
    differing = [at for at, one in enumerate(original) if drawn["headers"][at] != one]
    assert differing == [0], f"the check named {differing}"


def test_a_table_that_promises_more_columns_than_it_carries_shows_both_counts(
    browser: Browser,
):
    """C72 on the rendered page. The declared count and the held count
    are separate attributes, so a short table cannot read as a full one."""
    payload = table_payload(FIRST_SPEC)
    declared = payload["table"]["column_count"]
    payload["table"]["headers"].pop()
    drawn = draw_table(browser, payload)
    assert drawn["declared"] == str(declared)
    assert drawn["held"] == str(declared - 1)
    assert len(drawn["headers"]) == declared - 1
