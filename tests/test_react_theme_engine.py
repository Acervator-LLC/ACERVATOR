"""Issue #128 Stage 3 unit 2 -- the React side of the theme engine.

WHAT IS PROVED
==============
``src/gui/web/theme_engine.js`` publishes the theme table that
``src/gui/main_tabs/theme_engine_surface.py`` serves, and carries no
theme value of its own. Two sources of truth for one skin is the defect
this unit exists to prevent, so the value agreement and the no-literals
scan are the two halves of the same claim.

A theme value that opens with the module's reference mark names a
design token. It is resolved through ``design_tokens.js``, never
copied, and a reference that reaches nothing is reported rather than
repaired.

HOW THE JAVASCRIPT IS RUN
=========================
Node is not installed and nothing here adds a JavaScript test runner.
Two engines already in the tree run the module instead. ``QJSEngine``
from ``PySide6.QtQml`` -- the engine ``tests/test_desktop_shell_assets.py``
already parses the shell with -- runs it as plain JavaScript and answers
in JSON. ``QWebEngineView`` loads the real ``desktop/renderer/index.html``
from disk, which is the only way to run the module under the page's own
content-security policy.

THE CONTROLS
============
Every count here has a planted opposite that must be named. A theme
added to one side alone is named by the reach check. A colour, a size,
a number and a real theme value planted in a copy of the source are each
named by the literal scan. A theme differing in one value only is what
proves the switch check can report. A network call from the loaded page
is refused with ``connect-src`` in the violation record, which a failed
name lookup could not produce.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    new_engine,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "theme_engine.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

JS_TIMEOUT_MS = 30_000

#: Python type -> the JavaScript type the same value has after the
#: bridge's ``json.dumps``. A value that changes shape in transit shows
#: as a disagreement between this map and ``acervatorThemes.types()``.
JS_TYPE_OF = {
    "str": "string",
    "int": "number",
    "float": "number",
    "tuple": "object",
    "list": "object",
    "NoneType": "null",
}

FIRST_THEME = tes.THEME_NAMES[0]
SECOND_THEME = tes.THEME_NAMES[1]
FIRST_FIELD = tes.FIELD_NAMES[2]


# -- the surface, as the bridge serialises it --------------------------


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON.

    ``src/core/desktop_bridge.py`` writes every response with
    ``json.dumps(..., ensure_ascii=True)``, so a tuple reaches the
    renderer as an array. Comparing the module against the raw Python
    dict would charge the module for that conversion.
    """
    return json.loads(json.dumps(tes.view_model(params), ensure_ascii=True))


def token_payload() -> dict:
    """The design-token surface's answer, for the reference resolver."""
    return json.loads(json.dumps(dss.view_model({}), ensure_ascii=True))


# -- the JavaScript engine ---------------------------------------------


#: A design-token table with the real module's three reader names.
#: ``token`` raises for a name it does not hold, so a caller that skipped
#: ``has`` fails loudly instead of resolving to undefined.
TABLE_STANDIN = (
    "window.acervatorTokens = (function () {"
    "  var bag = JSON.parse(TOKENS).tokens;"
    "  function owns(n) {"
    "    return Object.prototype.hasOwnProperty.call(bag, n); }"
    "  return {"
    "    has: owns,"
    "    names: function () { return Object.keys(bag); },"
    "    token: function (n) {"
    "      if (!owns(n)) { throw new Error('unheld token asked: ' + n); }"
    "      return bag[n]; } }; })();"
)


class JsRuntime(JsEngine):
    """A QJSEngine holding ``theme_engine.js`` and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetThemes"

    def give_tokens(self, payload: Any) -> None:
        """Put a design-token table on the page before the themes load."""
        self.bind_json("TOKENS", payload)
        self.run(TABLE_STANDIN)

    def load_real_tokens(self) -> None:
        """Run unit 1's own module, when it is on disk."""
        if not TOKENS_PATH.is_file():
            pytest.skip(
                "design_tokens.js is on fix-128-s3-design-tokens, not yet merged"
            )
        self.run(TOKENS_PATH.read_text(encoding="utf-8"))
        self.bind_json("TOKENS", token_payload())
        self.run("acervatorSetTokens(JSON.parse(TOKENS));")

    def theme_values(self, name: str) -> dict:
        self.bind_json("NAME", name)
        return self.json("acervatorThemes.theme(JSON.parse(NAME))")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_PATH.read_text(encoding="utf-8"))


def held_theme(name: str) -> dict:
    """One theme as the payload hands it to the module.

    The surface publishes for a browser, so its themes carry the alpha
    share CSS reads while tes.THEMES keeps the byte Qt reads. The
    module is answerable for what it was given, never for the Qt table.
    """
    return bridge_payload()["themes"][name]


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding the real surface's whole theme table."""
    js.push(bridge_payload())
    return js


# -- 1. every theme and every value reaches the JavaScript side --------


def test_the_module_holds_every_theme_the_surface_publishes(loaded: JsRuntime):
    """A theme the surface publishes that the module never holds is a
    skin the operator cannot select."""
    surface_names = sorted(tes.THEME_NAMES)
    module_names = sorted(loaded.json("acervatorThemes.names()"))
    missing = sorted(set(surface_names) - set(module_names))
    extra = sorted(set(module_names) - set(surface_names))
    assert not missing, (
        f"{len(missing)} of {len(surface_names)} surface themes never "
        f"reached the module: {missing}"
    )
    assert not extra, f"the module holds themes the surface has none of: {extra}"
    assert len(module_names) == len(surface_names) == len(set(surface_names))


def test_the_theme_reach_check_names_a_theme_only_the_surface_holds(js: JsRuntime):
    """The control on the surface side. Without it a module that dropped
    a theme would read as agreement."""
    payload = bridge_payload()
    del payload["themes"][FIRST_THEME]
    js.push(payload)
    missing = set(tes.THEME_NAMES) - set(js.json("acervatorThemes.names()"))
    assert missing == {
        FIRST_THEME
    }, f"the check did not name the dropped theme: {missing}"


def test_the_theme_reach_check_names_a_theme_only_the_module_holds(js: JsRuntime):
    """The control on the module side."""
    payload = bridge_payload()
    payload["themes"]["planted_only_in_js"] = dict(payload["themes"][FIRST_THEME])
    js.push(payload)
    extra = set(js.json("acervatorThemes.names()")) - set(tes.THEME_NAMES)
    assert extra == {
        "planted_only_in_js"
    }, f"the check did not name the planted theme: {extra}"


def test_every_theme_holds_every_field_the_surface_publishes(loaded: JsRuntime):
    """A field the surface publishes that a theme never carries is a
    value the screen has nothing to paint with."""
    expected = set(tes.FIELD_NAMES)
    for name in tes.THEME_NAMES:
        held = set(loaded.theme_values(name))
        missing = sorted(expected - held)
        extra = sorted(held - expected)
        assert not missing, f"{name} is missing {len(missing)} fields: {missing}"
        assert not extra, f"{name} holds fields the surface has none of: {extra}"
        assert len(held) == len(expected) == len(tes.FIELD_NAMES)


def test_the_field_reach_check_names_a_field_only_the_surface_holds(js: JsRuntime):
    """The control for the field count, on the surface side."""
    payload = bridge_payload()
    del payload["themes"][FIRST_THEME][FIRST_FIELD]
    js.push(payload)
    missing = set(tes.FIELD_NAMES) - set(js.theme_values(FIRST_THEME))
    assert missing == {
        FIRST_FIELD
    }, f"the check did not name the dropped field: {missing}"


def test_the_field_reach_check_names_a_field_only_the_module_holds(js: JsRuntime):
    """The control for the field count, on the module side."""
    payload = bridge_payload()
    payload["themes"][FIRST_THEME]["planted_only_in_js"] = "planted"
    js.push(payload)
    extra = set(js.theme_values(FIRST_THEME)) - set(tes.FIELD_NAMES)
    assert extra == {
        "planted_only_in_js"
    }, f"the check did not name the planted field: {extra}"


def test_the_module_holds_the_declared_field_and_theme_name_lists(loaded: JsRuntime):
    """The lists the surface publishes, carried across unchanged."""
    assert loaded.json("acervatorThemes.declaredNames()") == list(tes.THEME_NAMES)
    assert loaded.json("acervatorThemes.fieldNames()") == list(tes.FIELD_NAMES)


# -- 2. no theme value is written in the JavaScript --------------------


def theme_values() -> set:
    """Every value the five themes carry, and every style sheet."""
    found = {str(value) for theme in tes.THEMES.values() for value in theme.values()}
    found.update(str(sheet) for sheet in tes.STYLE_SHEETS.values())
    return found


@pytest.fixture(scope="module")
def module_source() -> str:
    return MODULE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def module_literals(module_source: str) -> dict:
    return js_literals(module_source)


def test_the_module_writes_no_number(module_literals: dict):
    """A text size, a corner rounding or a delay typed here is a second
    source of truth for a value the surface already owns."""
    assert not module_literals["numbers"], (
        "theme_engine.js holds numeric literals: " f"{module_literals['numbers']}"
    )


def test_the_module_writes_no_colour(module_source: str):
    """A colour typed here drifts from the surface the next time a theme
    changes, and nothing reports the drift."""
    found = HEX_COLOUR.findall(module_source)
    assert not found, f"theme_engine.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_theme_value(module_literals: dict):
    """A theme value spelled out as text: a colour, a font stack, a size,
    a display name or a whole style sheet."""
    written = sorted(set(module_literals["strings"]) & theme_values())
    assert not written, f"theme_engine.js spells out theme values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value(module_literals: dict):
    """The other table the module reads. A token value copied here would
    be a second source of truth for the same colour."""
    values = {str(value) for value in dss.TOKENS.values()}
    written = sorted(set(module_literals["strings"]) & values)
    assert not written, f"theme_engine.js spells out token values: {written}"


def test_the_module_hides_no_value_behind_a_regular_expression(module_literals: dict):
    """The scan above parses no regular expression, so a value inside one
    would pass unread. The module carries none."""
    assert not module_literals["slashes"], (
        "theme_engine.js holds a slash outside a comment, which the "
        f"literal scan cannot read: {module_literals['slashes']}"
    )


PLANTED_SOURCES = {
    "colour": 'var x = "#00ffcc";',
    "size": 'var x = "13px";',
    "number": "var x = 12;",
    "theme_value": 'var x = "' + tes.CYBERPUNK_DARK["accent_primary"] + '";',
    "display_name": 'var x = "' + tes.CYBERPUNK_DARK["display_name"] + '";',
    "token_value": 'var x = "' + dss.PRIMARY + '";',
    "regex": "var x = /ab+c/;",
}


def test_the_literal_scan_names_a_planted_colour():
    """The control for the colour check. A blind scan reports nothing on
    a file that spells a colour out."""
    planted = PLANTED_SOURCES["colour"]
    assert HEX_COLOUR.findall(planted) == ["#00ffcc"]
    assert "#00ffcc" in js_literals(planted)["strings"]


def test_the_literal_scan_names_a_planted_size():
    """The control for a size. A corner rounding or a text size is text,
    not a number, so the number check alone could not see one."""
    assert "13px" in js_literals(PLANTED_SOURCES["size"])["strings"]
    assert "13px" in theme_values()


def test_the_literal_scan_names_a_planted_number():
    """The control for the number check."""
    assert js_literals(PLANTED_SOURCES["number"])["numbers"] == ["12"]


def test_the_literal_scan_names_a_planted_theme_value():
    """The control for the theme-value check."""
    strings = set(js_literals(PLANTED_SOURCES["theme_value"])["strings"])
    assert strings & theme_values() == {tes.CYBERPUNK_DARK["accent_primary"]}


def test_the_literal_scan_names_a_planted_display_name():
    """The control for a theme's own name, which is one of its 34 values."""
    strings = set(js_literals(PLANTED_SOURCES["display_name"])["strings"])
    assert strings & theme_values() == {tes.CYBERPUNK_DARK["display_name"]}


def test_the_literal_scan_names_a_planted_token_value():
    """The control for the token-value check."""
    values = {str(value) for value in dss.TOKENS.values()}
    strings = set(js_literals(PLANTED_SOURCES["token_value"])["strings"])
    assert strings & values == {dss.PRIMARY}


def test_the_literal_scan_names_a_regular_expression():
    """The control for the slash check."""
    assert js_literals(PLANTED_SOURCES["regex"])["slashes"]


def test_the_literal_scan_reads_past_a_comment_holding_a_colour():
    """A scan that treated comments as code would report a false colour,
    and a scan that stopped at one would miss the code after it."""
    found = js_literals('// #00ffcc\nvar x = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


# -- 3. both sides agree, value for value, on every theme --------------


def test_every_value_of_every_theme_agrees_with_the_surface(loaded: JsRuntime):
    """The whole claim of this unit. A single disagreement means a screen
    skinned from the module does not match the surface."""
    expected = bridge_payload()["themes"]
    checked = 0
    for name, values in expected.items():
        actual = loaded.theme_values(name)
        differing = {
            field: (values[field], actual.get(field))
            for field in values
            if actual.get(field) != values[field]
        }
        assert (
            not differing
        ), f"{name}: {len(differing)} of {len(values)} values differ: {differing}"
        assert len(actual) == len(values)
        checked += len(values)
    assert checked == len(tes.THEME_NAMES) * len(tes.FIELD_NAMES)


def test_the_value_check_names_a_changed_value(js: JsRuntime):
    """The control. Two real payloads that differ by one value must not
    compare equal."""
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] += "0"
    js.push(payload)
    expected = bridge_payload()["themes"][FIRST_THEME]
    actual = js.theme_values(FIRST_THEME)
    differing = [f for f in expected if actual.get(f) != expected[f]]
    assert differing == [
        FIRST_FIELD
    ], f"the check did not name the changed value: {differing}"


def test_every_display_name_agrees_with_the_surface(loaded: JsRuntime):
    """The text the operator reads in the theme picker."""
    for name, display in tes.DISPLAY_NAMES.items():
        loaded.bind_json("NAME", name)
        assert loaded.json("acervatorThemes.displayName(JSON.parse(NAME))") == display


def test_every_style_sheet_agrees_with_the_surface(loaded: JsRuntime):
    """The style-sheet text the surface builds reaches the module whole.
    The module carries no template of its own to build a second one."""
    for name, sheet in tes.STYLE_SHEETS.items():
        loaded.bind_json("NAME", name)
        actual = loaded.json("acervatorThemes.styleSheet(JSON.parse(NAME))")
        assert (
            actual == sheet
        ), f"{name}: style sheet differs by {len(sheet)} characters"


def test_every_value_arrives_as_the_type_the_surface_holds(loaded: JsRuntime):
    """A value that changes shape in transit reads correct and skins
    wrong -- a number where a colour belongs paints nothing."""
    for name, theme in tes.THEMES.items():
        expected = {f: JS_TYPE_OF[type(v).__name__] for f, v in theme.items()}
        loaded.bind_json("NAME", name)
        actual = loaded.json("acervatorThemes.types(JSON.parse(NAME))")
        differing = {
            f: (k, actual.get(f)) for f, k in expected.items() if actual.get(f) != k
        }
        assert (
            not differing
        ), f"{name}: {len(differing)} values changed type: {differing}"


def test_the_module_reports_only_what_it_was_given(js: JsRuntime):
    """Every value comes from the payload and none from the module. A
    payload of values the surface never held must come back unchanged."""
    invented = {f: "given-" + f for f in tes.FIELD_NAMES}
    js.push(
        {
            "theme_names": [FIRST_THEME],
            "field_names": list(tes.FIELD_NAMES),
            "themes": {FIRST_THEME: invented},
        }
    )
    actual = js.theme_values(FIRST_THEME)
    assert actual == invented
    assert not set(actual.values()) & theme_values()


# -- 4. switching themes changes what a screen would paint -------------


def test_nothing_is_painted_until_a_theme_is_selected(loaded: JsRuntime):
    """A payload asked for with no name selects no theme, so a screen
    draws nothing rather than a skin the operator never chose."""
    assert loaded.json("acervatorThemes.current()") is None
    assert loaded.json("acervatorThemes.painted()") == {}


def test_the_surface_current_theme_is_the_one_selected_on_arrival(js: JsRuntime):
    """A payload asked for by name arrives with that theme current, and
    the module selects it rather than deciding for itself."""
    payload = bridge_payload(name=SECOND_THEME)
    assert payload["current"] == SECOND_THEME
    js.push(payload)
    assert js.json("acervatorThemes.current()") == SECOND_THEME
    assert js.json("acervatorThemes.painted()") == payload["themes"][SECOND_THEME]


def test_switching_theme_changes_what_a_screen_would_paint(loaded: JsRuntime):
    """The operator picks a skin and the screen changes."""
    loaded.bind_json("FIRST", FIRST_THEME)
    loaded.bind_json("SECOND", SECOND_THEME)
    assert loaded.json("acervatorThemes.select(JSON.parse(FIRST))") == FIRST_THEME
    before = loaded.json("acervatorThemes.painted()")
    assert loaded.json("acervatorThemes.select(JSON.parse(SECOND))") == SECOND_THEME
    after = loaded.json("acervatorThemes.painted()")
    changed = [f for f in before if after.get(f) != before[f]]
    assert changed, "the two themes paint identically, so the check cannot report"
    assert before == held_theme(FIRST_THEME)
    assert after == held_theme(SECOND_THEME)


def test_switching_back_restores_every_value_exactly(loaded: JsRuntime):
    """Returning to a theme must give the screen the values it had, not
    a table the module rebuilt from something else."""
    loaded.bind_json("FIRST", FIRST_THEME)
    loaded.bind_json("SECOND", SECOND_THEME)
    loaded.run("acervatorThemes.select(JSON.parse(FIRST));")
    before = loaded.json("acervatorThemes.painted()")
    loaded.run("acervatorThemes.select(JSON.parse(SECOND));")
    loaded.run("acervatorThemes.select(JSON.parse(FIRST));")
    assert loaded.json("acervatorThemes.painted()") == before


def test_the_switch_check_reports_a_theme_differing_in_one_value_only(js: JsRuntime):
    """The control. Two themes alike but for one colour must still read
    as a change, or the check above passes on themes that never differ."""
    payload = bridge_payload()
    twin = dict(payload["themes"][FIRST_THEME])
    twin["name"] = "twin"
    twin[FIRST_FIELD] = twin[FIRST_FIELD] + "0"
    payload["themes"]["twin"] = twin
    payload["theme_names"].append("twin")
    js.push(payload)
    js.bind_json("FIRST", FIRST_THEME)
    js.run("acervatorThemes.select(JSON.parse(FIRST));")
    before = js.json("acervatorThemes.painted()")
    js.run("acervatorThemes.select('twin');")
    after = js.json("acervatorThemes.painted()")
    changed = sorted(f for f in before if after.get(f) != before[f])
    assert changed == sorted(["name", FIRST_FIELD]), f"the check named {changed}"


def test_a_theme_the_module_does_not_hold_changes_nothing(loaded: JsRuntime):
    """A name off the table leaves the screen on the skin it had."""
    loaded.bind_json("FIRST", FIRST_THEME)
    loaded.run("acervatorThemes.select(JSON.parse(FIRST));")
    assert loaded.json("acervatorThemes.select('no_such_theme')") is None
    assert loaded.json("acervatorThemes.current()") == FIRST_THEME
    assert loaded.json("acervatorThemes.painted()") == held_theme(FIRST_THEME)


# -- the design tokens -------------------------------------------------


def reference(name: str) -> str:
    """A theme value naming a design token, written the module's way."""
    return "token:" + name


def test_the_module_publishes_the_reference_mark_it_reads(js: JsRuntime):
    """The one place the mark is written. A test that spelled its own
    copy would pass while the module read a different one."""
    assert js.json("acervatorThemes.referenceMark") == "token:"


def test_a_theme_value_naming_a_token_resolves_through_the_token_module(js: JsRuntime):
    """A theme that names a token gets the token's value, not a copy."""
    js.give_tokens(token_payload())
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] = reference("PRIMARY")
    js.push(payload)
    assert js.theme_values(FIRST_THEME)[FIRST_FIELD] == dss.PRIMARY
    assert js.json("acervatorThemes.faults()") == []


def test_the_reference_check_reports_an_unresolved_value(js: JsRuntime):
    """The control. Without a token table the same reference must not
    read as a resolved value."""
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] = reference("PRIMARY")
    js.push(payload)
    assert js.theme_values(FIRST_THEME)[FIRST_FIELD] == reference("PRIMARY")
    assert {
        "theme": FIRST_THEME,
        "field": FIRST_FIELD,
        "fault": "no-token-table",
        "target": "PRIMARY",
    } in js.json("acervatorThemes.faults()")


def test_the_module_names_the_token_carrying_each_theme_value(js: JsRuntime):
    """What lets a screen paint from a CSS variable instead of a colour.
    Measured on the real tables, not on an invented pair."""
    js.give_tokens(token_payload())
    js.push(bridge_payload())
    js.bind_json("NAME", FIRST_THEME)
    named = js.json("acervatorThemes.tokenNames(JSON.parse(NAME))")
    assert named, "no theme value matched any design token"
    for field, token_name in named.items():
        assert tes.THEMES[FIRST_THEME][field] == str(dss.TOKENS[token_name])


def test_the_token_naming_check_reports_a_value_no_token_carries(js: JsRuntime):
    """The control. A field carrying a value no token holds must not be
    named, or the check above would name every field whatever it held."""
    js.give_tokens(token_payload())
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] = "no-token-carries-this"
    js.push(payload)
    js.bind_json("NAME", FIRST_THEME)
    js.bind_json("FIELD", FIRST_FIELD)
    kind = js.json(
        "typeof acervatorThemes.tokenNameFor(JSON.parse(NAME), JSON.parse(FIELD))"
    )
    assert kind == "undefined"


def test_the_real_token_module_resolves_a_theme_reference(js: JsRuntime):
    """Unit 1's own module, driven rather than stood in for. Skips until
    ``design_tokens.js`` is merged."""
    js.load_real_tokens()
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] = reference("PRIMARY")
    js.push(payload)
    assert js.theme_values(FIRST_THEME)[FIRST_FIELD] == dss.PRIMARY


def test_resolving_again_answers_a_token_table_that_arrived_late(js: JsRuntime):
    """A page that loads the themes before the tokens must not hold a
    reference nothing answered for the life of the page."""
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] = reference("PRIMARY")
    js.push(payload)
    assert js.theme_values(FIRST_THEME)[FIRST_FIELD] == reference("PRIMARY")
    js.give_tokens(token_payload())
    js.run("acervatorThemes.resolve();")
    assert js.theme_values(FIRST_THEME)[FIRST_FIELD] == dss.PRIMARY
    assert js.json("acervatorThemes.faults()") == []


# -- 5. hostile payloads -----------------------------------------------


def test_a_declared_theme_the_payload_omits_is_named_as_missing(js: JsRuntime):
    """The surface promised the name and sent no theme."""
    payload = bridge_payload()
    del payload["themes"][FIRST_THEME]
    report = js.push(payload)
    assert {
        "theme": FIRST_THEME,
        "field": None,
        "fault": "missing",
        "target": None,
    } in report["faults"]
    js.bind_json("NAME", FIRST_THEME)
    assert js.json("acervatorThemes.has(JSON.parse(NAME))") is False
    assert js.theme_values(FIRST_THEME) == {}


def test_a_missing_theme_shortens_the_held_count_not_the_declared_count(js: JsRuntime):
    """C72. The two counts are kept apart so a payload that promises more
    than it carries reads as a difference, never as a full table."""
    payload = bridge_payload()
    del payload["themes"][FIRST_THEME]
    report = js.push(payload)
    assert report["declared"] == len(tes.THEME_NAMES)
    assert report["held"] == len(tes.THEME_NAMES) - 1


def test_a_null_theme_is_named_and_holds_nothing(js: JsRuntime):
    """A null is reported, not swapped for a skin of the module's own."""
    payload = bridge_payload()
    payload["themes"][FIRST_THEME] = None
    report = js.push(payload)
    assert {
        "theme": FIRST_THEME,
        "field": None,
        "fault": "null",
        "target": None,
    } in report["faults"]
    assert report["declared"] == len(tes.THEME_NAMES)
    assert report["held"] == len(tes.THEME_NAMES) - 1
    assert js.theme_values(FIRST_THEME) == {}


def test_a_number_where_a_colour_belongs_is_reported_not_repaired(js: JsRuntime):
    """The module holds no idea of what type a value should be, so it
    passes the number on and names the type it received."""
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] = 7
    js.push(payload)
    assert js.theme_values(FIRST_THEME)[FIRST_FIELD] == 7
    js.bind_json("NAME", FIRST_THEME)
    assert js.json("acervatorThemes.types(JSON.parse(NAME))")[FIRST_FIELD] == "number"


def test_the_type_check_names_the_number_against_the_surface(js: JsRuntime):
    """The control for the check above, read against the surface's own
    types. A check blind to shape would report agreement here."""
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] = 7
    js.push(payload)
    expected = {
        f: JS_TYPE_OF[type(v).__name__] for f, v in tes.THEMES[FIRST_THEME].items()
    }
    js.bind_json("NAME", FIRST_THEME)
    actual = js.json("acervatorThemes.types(JSON.parse(NAME))")
    differing = sorted(f for f, k in expected.items() if actual.get(f) != k)
    assert differing == [FIRST_FIELD]


def test_a_null_value_is_named_and_left_as_it_arrived(js: JsRuntime):
    """A value sent as null is reported and kept, not filled in."""
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] = None
    report = js.push(payload)
    assert {
        "theme": FIRST_THEME,
        "field": FIRST_FIELD,
        "fault": "null",
        "target": None,
    } in report["faults"]
    assert js.theme_values(FIRST_THEME)[FIRST_FIELD] is None


def test_a_value_naming_a_token_that_does_not_exist_is_named(js: JsRuntime):
    """A reference the token table cannot answer stays as it arrived and
    is reported, so a blank colour is never invented for it."""
    js.give_tokens(token_payload())
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] = reference("NO_SUCH_TOKEN")
    report = js.push(payload)
    assert {
        "theme": FIRST_THEME,
        "field": FIRST_FIELD,
        "fault": "unresolved-reference",
        "target": "NO_SUCH_TOKEN",
    } in report["faults"]
    assert js.theme_values(FIRST_THEME)[FIRST_FIELD] == reference("NO_SUCH_TOKEN")


def test_a_value_naming_itself_is_named_and_does_not_hang(js: JsRuntime):
    """A field pointing at its own name ends the walk instead of
    following it for ever."""
    js.give_tokens(token_payload())
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] = reference(FIRST_FIELD)
    report = js.push(payload)
    assert {
        "theme": FIRST_THEME,
        "field": FIRST_FIELD,
        "fault": "reference-cycle",
        "target": FIRST_FIELD,
    } in report["faults"]
    assert js.theme_values(FIRST_THEME)[FIRST_FIELD] == reference(FIRST_FIELD)


def test_two_values_naming_each_other_are_named_and_do_not_hang(js: JsRuntime):
    """The control for the check above. A guard that only compared a name
    with itself would follow a two-step ring for ever."""
    js.give_tokens(token_payload())
    payload = bridge_payload()
    other = tes.FIELD_NAMES[3]
    payload["themes"][FIRST_THEME][FIRST_FIELD] = reference(other)
    payload["themes"][FIRST_THEME][other] = reference(FIRST_FIELD)
    report = js.push(payload)
    cycles = [f for f in report["faults"] if f["fault"] == "reference-cycle"]
    assert sorted(f["field"] for f in cycles) == sorted([FIRST_FIELD, other])


def test_a_theme_that_is_not_a_table_is_named_and_holds_nothing(js: JsRuntime):
    """A theme sent as text or a number draws nothing rather than a table
    of undefined values."""
    payload = bridge_payload()
    payload["themes"][FIRST_THEME] = "a string"
    report = js.push(payload)
    assert {
        "theme": FIRST_THEME,
        "field": None,
        "fault": "not-a-table",
        "target": None,
    } in report["faults"]
    assert report["held"] == len(tes.THEME_NAMES) - 1


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    """A bridge answering with a string or a number draws nothing."""
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorThemes.isLoaded()") is False
        assert js.json("acervatorThemes.names()") == []
        assert report["declared"] is None
        assert report["held"] is None
        assert report["faults"] == [
            {"theme": "themes", "field": None, "fault": "not-an-object", "target": None}
        ]


def test_a_name_the_payload_never_carried_is_not_a_theme(js: JsRuntime):
    """Every JavaScript object inherits names like ``constructor`` and
    ``toString``. Reading one as a theme would hand a screen a function
    where a colour belongs."""
    js.push(bridge_payload())
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        js.bind_json("NAME", inherited)
        assert js.json("acervatorThemes.has(JSON.parse(NAME))") is False
        assert js.json("acervatorThemes.theme(JSON.parse(NAME))") == {}
        assert js.json("acervatorThemes.tokenNames(JSON.parse(NAME))") == {}
        assert js.json("acervatorThemes.select(JSON.parse(NAME))") is None
        # The TYPE, not the value. JSON.stringify turns a function into
        # `undefined`, the same answer an absent name gives, so a value
        # comparison cannot tell a leaked method from a real miss.
        for reader in ("displayName", "styleSheet"):
            kind = js.json("typeof acervatorThemes." + reader + "(JSON.parse(NAME))")
            assert kind == "undefined", f"{reader}({inherited}) returned a {kind}"


def test_an_inherited_field_name_is_not_a_theme_value(js: JsRuntime):
    """The same inside one theme."""
    js.push(bridge_payload())
    js.bind_json("NAME", FIRST_THEME)
    for inherited in ("constructor", "toString", "valueOf"):
        js.bind_json("FIELD", inherited)
        kind = js.json(
            "typeof acervatorThemes.value(JSON.parse(NAME), JSON.parse(FIELD))"
        )
        assert kind == "undefined", f"value({inherited}) returned a {kind}"


def test_the_inherited_name_check_still_reads_a_real_theme(js: JsRuntime):
    """The control for the two checks above. A reader that answered
    nothing for every name would pass them while serving no theme."""
    js.push(bridge_payload())
    js.bind_json("NAME", FIRST_THEME)
    js.bind_json("FIELD", FIRST_FIELD)
    assert (
        js.json("acervatorThemes.displayName(JSON.parse(NAME))")
        == tes.DISPLAY_NAMES[FIRST_THEME]
    )
    assert js.json("acervatorThemes.value(JSON.parse(NAME), JSON.parse(FIELD))") == (
        tes.THEMES[FIRST_THEME][FIRST_FIELD]
    )
    assert js.json("acervatorThemes.select(JSON.parse(NAME))") == FIRST_THEME


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
    js.run("acervatorLoadThemes();")
    drain_events()
    assert js.json("window.CALLS") == [[tes.METHOD, "{}"]]
    assert js.json("acervatorThemes.isLoaded()") is True
    assert len(js.json("acervatorThemes.names()")) == len(tes.THEME_NAMES)


def test_the_module_asks_for_one_theme_by_name(js: JsRuntime):
    """A caller that already knows which skin it wants sends the name the
    surface reads, so the answer arrives with that theme current."""
    js.bind_json("PAYLOAD", bridge_payload(name=SECOND_THEME))
    js.run(BRIDGE_STUB)
    js.bind_json("WANTED", SECOND_THEME)
    js.run("acervatorLoadThemes(JSON.parse(WANTED));")
    drain_events()
    assert js.json("window.CALLS") == [[tes.METHOD, '{"name":"' + SECOND_THEME + '"}']]
    assert js.json("acervatorThemes.current()") == SECOND_THEME


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    """Several panels on one page share one answer."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadThemes(); acervatorLoadThemes(); acervatorLoadThemes();")
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_the_ask_counter_reports_a_second_round_trip(js: JsRuntime):
    """The control for the check above. A counter that never incremented
    would report one call however many were made."""
    js.bind_json("PAYLOAD", bridge_payload())
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadThemes();")
    drain_events()
    js.run("acervatorThemes.forget(); acervatorLoadThemes();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    """A page opened without the preload script must say so, not draw a
    half-skinned screen."""
    js.run("acervatorLoadThemes();")
    drain_events()
    assert js.json("acervatorThemes.isLoaded()") is False
    assert js.json("acervatorThemes.loadError()") == "the preload bridge is not present"


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
        "acervatorLoadThemes();"
    )
    drain_events()
    assert js.json("acervatorThemes.isLoaded()") is False
    assert js.json("acervatorThemes.loadError()") == "the Python backend is not running"
    js.run("acervatorLoadThemes();")
    drain_events()
    assert js.json("window.TRIES") == 2
    assert js.json("acervatorThemes.isLoaded()") is True
    assert len(js.json("acervatorThemes.names()")) == len(tes.THEME_NAMES)


# -- the module under the page's own policy ----------------------------


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


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    """``script-src 'self'`` admits the module. A policy that refused it
    would leave the page with no theme API at all."""
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorThemes") == "object"
    assert browser.js("typeof window.acervatorSetThemes") == "function"
    assert browser.js("typeof window.acervatorLoadThemes") == "function"


def test_the_policy_refuses_a_network_call_from_the_loaded_page(browser: Browser):
    """The control for the check above. It names the directive that
    refused, which a failed address lookup could not produce."""
    browser.js(
        WATCH_VIOLATIONS + "window.PROBE = 'pending';"
        "fetch('https://example.invalid/x')"
        "  .then(function () { window.PROBE = 'allowed'; })"
        "  .catch(function (e) { window.PROBE = 'refused: ' + e.name; });"
    )
    browser.settle(1500)
    assert browser.js("window.PROBE") == "refused: TypeError"
    violations = json.loads(browser.js("JSON.stringify(window.VIOLATIONS)"))
    assert any(v.startswith("connect-src") for v in violations), violations


def test_the_module_makes_no_network_call_of_its_own(browser: Browser):
    """Driving the whole module raises no policy violation, so nothing in
    it reaches for the network."""
    browser.js(WATCH_VIOLATIONS)
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(bridge_payload())) + ";")
    browser.js(
        "acervatorSetThemes(JSON.parse(window.PAYLOAD));"
        "acervatorThemes.select(" + json.dumps(FIRST_THEME) + ");"
        "acervatorThemes.apply(document.documentElement);"
    )
    browser.settle(500)
    assert json.loads(browser.js("JSON.stringify(window.VIOLATIONS)")) == []


def test_every_value_of_the_selected_theme_lands_as_a_css_variable(browser: Browser):
    """What a stylesheet actually reads. The value is taken back off the
    rendered document, not off the object that wrote it."""
    expected = bridge_payload()["themes"][FIRST_THEME]
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(bridge_payload())) + ";")
    written = json.loads(
        browser.js(
            "JSON.stringify((function () {"
            "  acervatorSetThemes(JSON.parse(window.PAYLOAD));"
            "  acervatorThemes.select(" + json.dumps(FIRST_THEME) + ");"
            "  return acervatorThemes.apply(document.documentElement); })())"
        )
    )
    assert sorted(written) == sorted(expected)
    read_back = json.loads(
        browser.js(
            "JSON.stringify((function () {"
            "  var style = getComputedStyle(document.documentElement);"
            "  var out = {};"
            "  " + json.dumps(sorted(expected)) + ".forEach(function (n) {"
            "    out[n] = style.getPropertyValue('--' + n).trim(); });"
            "  return out; })())"
        )
    )
    differing = {
        f: (v, read_back.get(f)) for f, v in expected.items() if read_back.get(f) != v
    }
    assert not differing, f"{len(differing)} values reached no stylesheet: {differing}"


def test_the_css_variable_check_names_a_changed_value(browser: Browser):
    """The control. A read that returned the same text whatever was
    written would report agreement on a changed colour."""
    payload = bridge_payload()
    payload["themes"][FIRST_THEME][FIRST_FIELD] += "0"
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetThemes(JSON.parse(window.PAYLOAD));"
        "acervatorThemes.select(" + json.dumps(FIRST_THEME) + ");"
        "acervatorThemes.apply(document.documentElement);"
    )
    read_back = browser.js(
        "getComputedStyle(document.documentElement)"
        ".getPropertyValue('--" + FIRST_FIELD + "').trim()"
    )
    assert read_back == payload["themes"][FIRST_THEME][FIRST_FIELD]
    assert read_back != tes.THEMES[FIRST_THEME][FIRST_FIELD]


def test_switching_theme_repaints_every_css_variable_that_differs(browser: Browser):
    """The switch, measured where it lands: the rendered document."""
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(bridge_payload())) + ";")
    browser.js("acervatorSetThemes(JSON.parse(window.PAYLOAD));")
    reader = (
        "(function (n) {"
        "  acervatorThemes.select(n);"
        "  acervatorThemes.apply(document.documentElement);"
        "  var style = getComputedStyle(document.documentElement);"
        "  var out = {};"
        "  acervatorThemes.fieldNames().forEach(function (f) {"
        "    out[f] = style.getPropertyValue('--' + f).trim(); });"
        "  return JSON.stringify(out); })"
    )
    first = json.loads(browser.js(reader + "(" + json.dumps(FIRST_THEME) + ")"))
    second = json.loads(browser.js(reader + "(" + json.dumps(SECOND_THEME) + ")"))
    back = json.loads(browser.js(reader + "(" + json.dumps(FIRST_THEME) + ")"))
    changed = [f for f in first if second.get(f) != first[f]]
    assert changed, "the two themes painted the same page"
    assert back == first, "switching back did not restore the page"
    assert first == bridge_payload()["themes"][FIRST_THEME]
