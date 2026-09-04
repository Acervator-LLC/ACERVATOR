"""Proves the design module renders each token into a CSS
declaration and carries no value.
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

from src.gui.color_alpha import css_colours
from src.gui.main_tabs import design_system_surface as dss
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_system.js"
TOKENS_PATH = REPO_ROOT / "src" / "gui" / "web" / "design_tokens.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

JS_TIMEOUT_MS = 30_000

#: The module source read before any check writes into it.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")
TOKENS_SOURCE = TOKENS_PATH.read_text(encoding="utf-8")

#: The CSS unit each token group implies, paired against the surface group
#: list by name.
UNIT_BY_GROUP = {
    "colors": None,
    "aliases": None,
    "font_families": None,
    "shadows": None,
    "type_scale": "px",
    "spacing": "px",
    "radii": "px",
    "target_sizes": "px",
    "table_columns": "px",
    "focus": "px",
    "motion_ms": "ms",
    "weights": "",
    "line_heights": "",
}

#: A token name the surface does not carry, for the shadow colour.
ABSENT_COLOUR = "SHADOW_COLOUR"

#: The token a caller names for the shadow colour, carried by no other name.
SHADOW_COLOUR = "TEXT_ON_LIGHT"

SHADOW_CHANNELS = "0,0,0"


def published_order() -> list:
    """Every token name, in the order the surface's group lists publish."""
    found: list = []
    for group in dss.GROUP_NAMES:
        for name in dss.GROUP_MEMBERS[group]:
            if name not in found:
                found.append(name)
    return found


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON."""
    return json.loads(json.dumps(dss.view_model(params), ensure_ascii=True))


def js_number(value: float) -> str:
    """One number as JavaScript's ``String`` writes it, whole or not."""
    return repr(int(value)) if float(value).is_integer() else repr(value)


def expected_value(name: str, group: str, scale: int) -> Any:
    """The CSS text one token must render to, built from the surface value."""
    value = dss.TOKENS[name]
    unit = UNIT_BY_GROUP[group]
    if group == "shadows":
        offset, blur, alpha = value
        share = js_number(int(alpha, 16) * pow(scale, -1))
        return f"0px {offset}px {blur}px rgba({SHADOW_CHANNELS},{share})"
    if unit is None:
        if isinstance(value, str) and value.startswith("rgba("):
            body = value[len("rgba(") : -1].split(",")
            share = js_number(float(body[3]) * pow(scale, -1))
            return "rgba(" + ",".join(body[:3] + [share]) + ")"
        return value
    return f"{value}{unit}"


# -- the JavaScript engine ---------------------------------------------


class JsRuntime(JsEngine):
    """A QJSEngine holding the token table and the declaration module."""

    module_path = MODULE_PATH
    setter = "acervatorSetDesignSystem"

    def load(self, payload: dict, colour: Any = None) -> dict:
        """Push one payload into both modules and answer the counts."""
        self.bind_json("PAYLOAD", payload)
        self.bind_json("COLOUR", colour)
        self.run("acervatorSetTokens(JSON.parse(PAYLOAD));")
        return self.json(
            "acervatorSetDesignSystem(JSON.parse(PAYLOAD), JSON.parse(COLOUR))"
        )

    def ask(self, method: str, *args: Any) -> Any:
        """Call one published method with JSON arguments and answer it."""
        self.bind_json("ARGS", list(args))
        return self.json(
            "acervatorDesignSystem." + method + ".apply(null, JSON.parse(ARGS))"
        )


def both_modules() -> str:
    """The token table and the declaration module, in page order."""
    return TOKENS_SOURCE + "\n" + MODULE_SOURCE


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """Both modules, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), both_modules())


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding every token, with the shadow colour named."""
    js.load(bridge_payload(), SHADOW_COLOUR)
    return js


# -- 1. the module runs at all -----------------------------------------


def test_the_module_parses_on_its_own(qapp):
    """A file the page cannot parse takes every later script down with it."""
    assert qapp is not None
    engine = new_engine()
    engine.evaluate("var window = this;")
    result = engine.evaluate(MODULE_SOURCE, MODULE_PATH.name)
    assert not result.isError(), MODULE_PATH.name + " -> " + result.toString()


def test_the_parse_check_names_a_broken_module(qapp):
    """A parse check accepting an unclosed brace would report a pass on any broken
    module."""
    assert qapp is not None
    engine = new_engine()
    engine.evaluate("var window = this;")
    broken = MODULE_SOURCE + "\nfunction ( {"
    assert engine.evaluate(broken, MODULE_PATH.name).isError()


def test_the_module_publishes_its_whole_surface(js: JsRuntime):
    """A page reaches the declarations through these three names."""
    assert js.json("typeof window.acervatorDesignSystem") == "object"
    assert js.json("typeof window.acervatorSetDesignSystem") == "function"
    assert js.json("typeof window.acervatorLoadDesignSystem") == "function"
    assert js.json("acervatorDesignSystem.method") == dss.METHOD


def test_the_page_loads_the_module(loaded: JsRuntime):
    """The renderer page names the module, so the browser runs it."""
    listed = INDEX_HTML.read_text(encoding="utf-8")
    assert MODULE_PATH.name in listed
    assert listed.index(TOKENS_PATH.name) < listed.index(MODULE_PATH.name)


# -- 2. the whole payload, both counts, every state --------------------


def test_every_token_the_surface_publishes_renders_a_declaration(loaded: JsRuntime):
    """One declaration per token, none dropped and none invented."""
    names = loaded.ask("declarationNames")
    assert len(names) == len(dss.TOKEN_NAMES)
    assert sorted(names) == sorted(dss.TOKEN_NAMES)


def test_the_counts_are_filled_in_from_the_lists_they_count(loaded: JsRuntime):
    """A count left at its starting value would read as a full table of tokens."""
    counts = loaded.ask("counts")
    assert counts["groups"] == len(dss.GROUP_NAMES)
    assert counts["declared"] == len(dss.TOKEN_NAMES)
    assert counts["held"] == len(dss.TOKEN_NAMES)
    assert counts["faults"] == 0
    assert counts["refusals"] == 0
    assert counts["conversions"] == 0


def test_the_counts_read_zero_before_any_payload_arrives(js: JsRuntime):
    """The opposite of the check above, in the unloaded state."""
    counts = js.ask("counts")
    assert counts == {
        "groups": 0,
        "declared": 0,
        "held": 0,
        "conversions": 0,
        "refusals": 0,
        "faults": 0,
    }
    assert js.ask("isLoaded") is False
    assert js.ask("declarationNames") == []


def test_a_declared_count_and_a_held_count_part_when_a_token_renders_nothing(
    js: JsRuntime,
):
    """A payload naming more tokens than it renders reads as a difference,
    never as a full table."""
    counts = js.load(bridge_payload(), ABSENT_COLOUR)
    assert counts["declared"] == len(dss.TOKEN_NAMES)
    assert counts["held"] == len(dss.TOKEN_NAMES) - len(dss.SHADOW_NAMES)
    assert counts["faults"] == len(dss.SHADOW_NAMES)


def test_a_shadow_refuses_when_no_token_carries_its_colour(js: JsRuntime):
    """The surface declares five shadow alphas and no shadow colour, so each shadow
    renders nothing."""
    js.load(bridge_payload())
    faults = js.ask("faults")
    named = sorted(f["name"] for f in faults)
    assert named == sorted(dss.SHADOW_NAMES)
    assert {f["fault"] for f in faults} == {"not-a-shadow"}
    for name in dss.SHADOW_NAMES:
        assert js.ask("declaration", name) is None


def test_naming_a_colour_afterwards_renders_the_shadows(js: JsRuntime):
    """The same payload with a colour named afterwards renders every shadow the
    refusal held back."""
    js.load(bridge_payload())
    counts = js.ask("resolve", SHADOW_COLOUR)
    assert counts["held"] == len(dss.TOKEN_NAMES)
    assert counts["faults"] == 0
    scale = js.ask("alphaScale")
    for name in dss.SHADOW_NAMES:
        assert js.ask("value", name) == expected_value(name, "shadows", scale)


def test_forgetting_returns_the_module_to_the_unloaded_state(loaded: JsRuntime):
    """A page that reloads its tokens must not read the old table."""
    loaded.run("acervatorDesignSystem.forget();")
    assert loaded.ask("isLoaded") is False
    assert loaded.ask("declarationNames") == []
    assert loaded.ask("declaration", "SPACE_M") is None


# -- 3. both sides agree, by value and by type -------------------------


def test_the_unit_table_and_the_surface_name_the_same_groups():
    """Both group lists are counted before pairing, so a group added to one side is
    named."""
    assert len(UNIT_BY_GROUP) == len(dss.GROUP_NAMES)
    assert sorted(UNIT_BY_GROUP) == sorted(dss.GROUP_NAMES)


def test_every_declaration_agrees_with_the_surface_value(loaded: JsRuntime):
    """The whole claim of this unit, token by token."""
    scale = loaded.ask("alphaScale")
    actual = loaded.ask("declarations")
    by_name = {row["name"]: row for row in actual}
    differing = {}
    for name in dss.TOKEN_NAMES:
        group = by_name[name]["group"]
        wanted = expected_value(name, group, scale)
        if by_name[name]["value"] != wanted:
            differing[name] = (wanted, by_name[name]["value"])
    assert not differing, f"{len(differing)} declarations differ: {differing}"
    assert len(by_name) == len(dss.TOKEN_NAMES)


def test_the_value_check_names_a_changed_payload_value(js: JsRuntime):
    """A module carrying its own copy of a value would answer the same whatever the
    payload said."""
    payload = bridge_payload()
    payload["tokens"]["SPACE_M"] = dss.SPACE_M + 1
    js.load(payload, SHADOW_COLOUR)
    scale = js.ask("alphaScale")
    assert js.ask("value", "SPACE_M") != expected_value("SPACE_M", "spacing", scale)
    assert js.ask("value", "SPACE_M") == f"{dss.SPACE_M + 1}px"


def test_every_rendered_value_arrives_as_text(loaded: JsRuntime):
    """A stylesheet reads text, so a value reaching it as a number changed shape in
    transit."""
    kinds = loaded.json(
        "acervatorDesignSystem.declarationNames().map(function (n) {"
        " return typeof acervatorDesignSystem.value(n); })"
    )
    assert set(kinds) == {"string"}
    assert len(kinds) == len(dss.TOKEN_NAMES)


def test_the_type_check_would_name_a_value_that_is_not_text(loaded: JsRuntime):
    """Forty three tokens are numbers in the raw table before this module renders
    them."""
    raw = loaded.json(
        "acervatorTokens.names().map(function (n) {"
        " return typeof acervatorTokens.token(n); })"
    )
    assert raw.count("number") == 43
    assert raw.count("object") == len(dss.SHADOW_NAMES)


def test_the_whole_declaration_text_names_the_token_and_its_value(
    loaded: JsRuntime,
):
    """A screen pastes this text into a stylesheet, so it must carry both
    halves and the custom-property mark."""
    for name in ("SPACE_M", "SURFACE_0", "MOTION_MEDIUM", "GLOW_PRIMARY"):
        text = loaded.ask("declaration", name)
        assert text == "--" + name + ": " + loaded.ask("value", name)


def test_a_reference_names_the_custom_property_and_not_the_bare_name(
    loaded: JsRuntime,
):
    """A reference written without the two dashes resolves to nothing and
    a screen falls back to the colour it inherits."""
    assert loaded.ask("cssReference", "SURFACE_0") == "var(--SURFACE_0)"
    assert loaded.ask("cssVariable", "SURFACE_0") == "--SURFACE_0"
    for row in loaded.ask("declarations"):
        assert row["reference"] == "var(--" + row["name"] + ")"
        assert row["variable"] == "--" + row["name"]


# -- 4. the colour sweep, as behaviour ---------------------------------


ALPHA_BYTE_TOKENS = (
    "GLOW_PRIMARY",
    "GLOW_SECONDARY",
    "SCRIM",
    "GLOW_PRIMARY_EDGE",
    "GLOW_PRIMARY_FAINT",
)


def qt_byte_payload() -> dict:
    """The payload as it would arrive carrying the alpha byte Qt reads.

    The surface publishes the share a browser reads, so the module's own
    conversion is driven here from a payload in the Qt form instead.
    """
    swapped = {
        css_colours(dss.TOKENS[name]): dss.TOKENS[name] for name in ALPHA_BYTE_TOKENS
    }

    def back(value: Any) -> Any:
        if isinstance(value, str):
            return swapped.get(value, value)
        if isinstance(value, dict):
            return {key: back(item) for key, item in value.items()}
        if isinstance(value, list):
            return [back(item) for item in value]
        return value

    return back(bridge_payload())


def test_every_alpha_byte_colour_is_converted_and_named(js: JsRuntime):
    """Each of the five conversions names the colour text that arrived and the text
    that renders."""
    js.load(qt_byte_payload(), SHADOW_COLOUR)
    changed = js.ask("conversions")
    assert [row["name"] for row in changed] == list(ALPHA_BYTE_TOKENS)
    for row in changed:
        assert row["from"] == dss.TOKENS[row["name"]]
        assert row["from"] != row["to"]
        assert row["to"].startswith("rgba(")


def test_the_real_payload_leaves_the_module_nothing_to_convert(loaded: JsRuntime):
    """The surface publishes the share, so no colour reaches the module in the
    form the check above drives."""
    assert loaded.ask("conversions") == []
    for name in ALPHA_BYTE_TOKENS:
        assert loaded.ask("value", name) == css_colours(dss.TOKENS[name])


def test_the_converted_alpha_is_the_byte_over_the_published_scale(
    loaded: JsRuntime,
):
    """The scale is read off the module and the share multiplied by its reciprocal."""
    scale = loaded.ask("alphaScale")
    assert scale == 255
    for name in ALPHA_BYTE_TOKENS:
        byte = float(dss.TOKENS[name][len("rgba(") : -1].split(",")[3])
        assert loaded.ask("value", name).endswith(str(byte * pow(scale, -1)) + ")")


def test_a_colour_already_in_the_browser_form_is_left_alone(loaded: JsRuntime):
    """Converting a colour whose share is one or less again would darken the tint
    each reload."""
    assert loaded.ask("cssColour", "rgba(1,2,3,0.25)") == "rgba(1,2,3,0.25)"
    assert loaded.ask("cssColour", "rgba(1,2,3,1)") == "rgba(1,2,3,1)"
    assert loaded.ask("cssColour", "#0a0a0f") == "#0a0a0f"


def test_no_declared_colour_carries_a_digit_count_the_engines_read_apart(
    loaded: JsRuntime,
):
    """Qt reads an eight-digit hex as alpha first and a browser as alpha last."""
    named = [
        row
        for row in loaded.ask("faults")
        if row["fault"] in ("hex-read-differently", "hex-dropped-by-both")
    ]
    assert named == []


def test_the_digit_count_check_names_a_split_hex_and_a_short_hex(js: JsRuntime):
    """Both hex forms must be named, or the empty answer above means nothing."""
    payload = bridge_payload()
    payload["tokens"]["SURFACE_0"] = "#ff112233"
    payload["tokens"]["SURFACE_1"] = "#11223"
    payload["tokens"]["SURFACE_2"] = "not-a-colour"
    js.load(payload, SHADOW_COLOUR)
    named = {row["name"]: row["fault"] for row in js.ask("faults")}
    assert named["SURFACE_0"] == "hex-read-differently"
    assert named["SURFACE_1"] == "hex-dropped-by-both"
    assert named["SURFACE_2"] == "not-a-colour"


def test_a_colour_the_engines_read_apart_is_named_and_left_as_it_arrived(
    js: JsRuntime,
):
    """Repairing an eight-digit colour would guess which engine the author meant,
    so the value stays."""
    payload = bridge_payload()
    payload["tokens"]["SURFACE_0"] = "#ff112233"
    js.load(payload, SHADOW_COLOUR)
    assert js.ask("value", "SURFACE_0") == "#ff112233"


THREE_EQUAL_CHANNEL = (
    "CARD_METRIC_LABEL",
    "TEXT_MAX",
    "TEXT_NEUTRAL",
    "TEXT_CONSOLE",
    "TEXT_INACTIVE",
    "TEXT_MUTED",
    "TEXT_PLACEHOLDER",
    "TEXT_ON_LIGHT",
    "BORDER_DISABLED",
    "SETTINGS_DISABLED_SURFACE",
    "SETTINGS_DISABLED_DEEP",
)


def test_the_three_equal_channel_colours_render_by_exact_text(loaded: JsRuntime):
    """A colour whose three channels are one byte hides a swap, so each value is
    compared exactly."""
    for name in THREE_EQUAL_CHANNEL:
        value = dss.TOKENS[name]
        digits = value[1:]
        widened = "".join(c * 2 for c in digits) if len(digits) == 3 else digits
        assert widened[0:2] == widened[2:4] == widened[4:6], name
        assert loaded.ask("value", name) == value


def test_the_three_equal_channel_list_names_every_such_colour():
    """A list that fell behind would leave a new same-channel colour missing from
    these names."""
    found = []
    for name in dss.COLOR_NAMES + dss.ALIAS_NAMES:
        value = dss.TOKENS[name]
        if not isinstance(value, str) or not value.startswith("#"):
            continue
        digits = value[1:]
        widened = "".join(c * 2 for c in digits) if len(digits) == 3 else digits
        if len(widened) >= 6 and widened[0:2] == widened[2:4] == widened[4:6]:
            found.append(name)
    assert sorted(found) == sorted(THREE_EQUAL_CHANNEL)


# -- 5. order and identity by name -------------------------------------


def test_the_declaration_order_is_the_order_the_surface_published(
    loaded: JsRuntime,
):
    """Order comes from the surface's own lists, never from walking a bag,
    so a rebuilt payload cannot reshuffle a screen."""
    assert loaded.ask("declarationNames") == published_order()


def test_every_group_publishes_its_members_as_a_list_in_order(loaded: JsRuntime):
    """A group read back as a bag loses the order the surface set."""
    assert loaded.ask("groupNames") == list(dss.GROUP_NAMES)
    for group in dss.GROUP_NAMES:
        assert loaded.ask("groupOrder", group) == list(dss.GROUP_MEMBERS[group])


def test_the_order_check_names_a_reversed_group(js: JsRuntime):
    """A check comparing sets rather than order would pass on a reversed group of
    names."""
    payload = bridge_payload()
    payload["group_members"]["shadows"] = list(reversed(dss.SHADOW_NAMES))
    js.load(payload, SHADOW_COLOUR)
    assert js.ask("groupOrder", "shadows") == list(reversed(dss.SHADOW_NAMES))
    assert js.ask("groupOrder", "shadows") != list(dss.SHADOW_NAMES)


def test_a_number_like_token_name_keeps_its_published_position(js: JsRuntime):
    """A bag walk puts a number-like name first, so this position proves the
    order came from the list."""
    payload = bridge_payload()
    payload["group_members"]["spacing"] = ["SPACE_XS", "7", "SPACE_S"]
    payload["tokens"]["7"] = dss.SPACE_XS
    payload["token_names"] = list(dss.TOKEN_NAMES) + ["7"]
    js.load(payload, SHADOW_COLOUR)
    names = js.ask("declarationNames")
    assert names[0] != "7", f"a number-like name reached the front: {names[:4]}"
    assert names.index("7") == names.index("SPACE_XS") + 1
    assert js.ask("value", "7") == f"{dss.SPACE_XS}px"


def test_a_token_that_renders_nothing_keeps_its_place_in_the_order(js: JsRuntime):
    """A name is published in order whether or not it renders, never walked."""
    js.load(bridge_payload())
    names = js.ask("declarationNames")
    assert names == published_order()
    assert len(names) == len(dss.TOKEN_NAMES)
    for name in dss.SHADOW_NAMES:
        assert name in names
        assert js.ask("value", name) is None


def test_a_token_is_reached_by_name_and_not_by_position(loaded: JsRuntime):
    """Each row carries its own name, so pairing two lists by index cannot misread
    a value."""
    rows = loaded.ask("declarations")
    for row in rows:
        assert row["value"] == loaded.ask("value", row["name"])
        assert row["group"] == loaded.ask("groupOf", row["name"])
    assert len({row["name"] for row in rows}) == len(rows)


def test_each_read_answers_a_fresh_list_rather_than_the_one_it_holds(
    loaded: JsRuntime,
):
    """A caller handed the module's own list could reorder every screen, so
    each declaration list is fresh."""
    assert loaded.json(
        "(function () {"
        "  var first = acervatorDesignSystem.declarationNames();"
        "  first.length = 0;"
        "  return acervatorDesignSystem.declarationNames().length; })()"
    ) == len(dss.TOKEN_NAMES)
    assert (
        loaded.json(
            "(function () {"
            "  var first = acervatorDesignSystem.declarations();"
            "  first[0].value = 'changed';"
            "  return acervatorDesignSystem.declarations()[0].value; })()"
        )
        != "changed"
    )
    assert loaded.json(
        "(function () {"
        "  acervatorDesignSystem.groupOrder('shadows').length = 0;"
        "  return acervatorDesignSystem.groupOrder('shadows').length; })()"
    ) == len(dss.SHADOW_NAMES)


# -- 6. resolving a value back to a token name -------------------------


#: Every rendered value that more than one non-alias name carries, measured
#: after the unit is added.
SHARED_VALUES = {
    "10px": ["TYPE_CAPTION", "SPACE_CARD_TIGHT"],
    "12px": ["SPACE_CARD_PAD", "RADIUS_MD"],
    "16px": ["TYPE_CARD_VALUE", "SPACE_M", "RADIUS_LG"],
    "2px": ["SPACE_XXS", "FOCUS_RING_WIDTH", "FOCUS_RING_OFFSET"],
    "24px": ["SPACE_L", "TARGET_MIN"],
    "32px": ["SPACE_XL", "TARGET_COMFORTABLE"],
    "4px": ["SPACE_XS", "RADIUS_XS"],
    "8px": ["SPACE_S", "RADIUS_SM"],
}


def test_a_value_several_names_carry_resolves_to_none_of_them(loaded: JsRuntime):
    """A corner radius is not a layout gap, so naming either carrier would skin a
    screen wrong."""
    refused = {}
    for wanted, carriers in SHARED_VALUES.items():
        assert loaded.ask("tokenNameFor", wanted, "length") is None, wanted
        refused[wanted] = carriers
    assert len(refused) == len(SHARED_VALUES)
    reasons = loaded.ask("refusals")
    named = {row["value"]: row["carriers"] for row in reasons}
    for wanted, carriers in refused.items():
        assert named[wanted] == carriers, wanted
        assert all(row["reason"] == "several-names-carry-it" for row in reasons)


def test_a_value_exactly_one_name_of_the_same_kind_carries_resolves(
    loaded: JsRuntime,
):
    """A refusal for every value would resolve nothing at all while passing the
    check above."""
    assert loaded.ask("tokenNameFor", "48px", "length") == "SPACE_XXL"
    assert loaded.ask("tokenNameFor", "9999px", "length") == "RADIUS_FULL"
    assert loaded.ask("tokenNameFor", dss.PRIMARY, "colour") == "PRIMARY"
    assert loaded.ask("refusals") == []


def test_a_value_carried_by_a_name_of_another_kind_is_refused(loaded: JsRuntime):
    """A column width is not a pane height, so the one carrier must mean the same
    kind."""
    assert loaded.ask("tokenNameFor", "48px", "time") is None
    assert loaded.ask("refusals") == [
        {
            "value": "48px",
            "reason": "a-name-of-another-kind",
            "carriers": ["SPACE_XXL"],
        }
    ]


def test_a_value_no_name_carries_is_refused_and_named(loaded: JsRuntime):
    """A token nothing carries answers nothing, and says which names it
    looked at rather than guessing the nearest."""
    assert loaded.ask("tokenNameFor", "1234px", "length") is None
    assert loaded.ask("refusals") == [
        {"value": "1234px", "reason": "no-name-carries-it", "carriers": []}
    ]


def test_a_second_name_never_wins_the_resolution(loaded: JsRuntime):
    """Resolving to an alias would hide which token a screen really paints its
    colour from."""
    for alias, target in dss.ALIAS_TARGETS.items():
        assert loaded.ask("tokenNameFor", dss.TOKENS[alias], "colour") == target
        assert alias not in loaded.ask("carriersOf", dss.TOKENS[alias])


def test_every_second_name_renders_what_the_name_it_copies_renders(
    loaded: JsRuntime,
):
    """A second name that drifted from its target would skin two screens
    differently from one declared colour."""
    for alias, target in dss.ALIAS_TARGETS.items():
        assert loaded.ask("aliasAgrees", alias) is True
        assert loaded.ask("aliasTarget", alias) == target
        assert loaded.ask("value", alias) == loaded.ask("value", target)


def test_the_agreement_check_names_a_second_name_that_drifted(js: JsRuntime):
    """A check answering true for everything would pass on an alias whose target no
    longer matches."""
    payload = bridge_payload()
    payload["tokens"]["BG"] = "#123456"
    js.load(payload, SHADOW_COLOUR)
    assert js.ask("aliasAgrees", "BG") is False
    assert js.ask("aliasAgrees", "CARD") is True


def test_the_shared_value_list_names_every_value_two_names_carry():
    """A list that fell behind the surface would leave a new collision among these
    carriers unrefused."""
    carriers: dict = {}
    scale = 255
    for group in dss.GROUP_NAMES:
        for name in dss.GROUP_MEMBERS[group]:
            if name in dss.ALIAS_TARGETS:
                continue
            if UNIT_BY_GROUP[group] is None:
                continue
            carriers.setdefault(expected_value(name, group, scale), []).append(name)
    shared = {value: names for value, names in carriers.items() if len(names) > 1}
    assert shared == SHARED_VALUES
    assert len(carriers) > len(shared)


# -- 7. no value literal in the JavaScript -----------------------------


TOKEN_VALUES = {str(value) for value in dss.TOKENS.values()}

WRITTEN_LINES = {
    "colour": '\nvar written = "#00ffcc";\n',
    "font_stack": '\nvar written = "' + dss.FONT_FAMILY_UI + '";\n',
    "rgba_value": '\nvar written = "' + dss.GLOW_PRIMARY + '";\n',
    "regular_expression": "\nvar written = /ab+c/;\n",
}


def caught_by_scan(source: str) -> set:
    """Which of the four scans report something on ``source``."""
    found = js_literals(source)
    strings = set(found["strings"])
    caught = set()
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if strings & TOKEN_VALUES:
        caught.add("token_value")
    if found["slashes"]:
        caught.add("regular_expression")
    return caught


def test_no_string_in_the_module_equals_a_token_value():
    """A token value spelled out as text would be a second source of truth
    for one skin."""
    written = sorted(set(js_literals(MODULE_SOURCE)["strings"]) & TOKEN_VALUES)
    assert not written, f"{MODULE_PATH.name} spells out token values: {written}"


def test_the_module_holds_no_hex_colour():
    """A colour written here would paint a screen the surface never asked
    for."""
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"{MODULE_PATH.name} holds hex colours: {found}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    """The scan above parses no regular expression, so a value inside one
    would pass unread."""
    slashes = js_literals(MODULE_SOURCE)["slashes"]
    assert not slashes, f"{MODULE_PATH.name} holds a slash outside a comment: {slashes}"


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_scan_names_one_written_line(kind: str):
    """The opposite for each scan, one written value at a time."""
    caught = caught_by_scan(MODULE_SOURCE + WRITTEN_LINES[kind])
    assert caught, f"the scan reported nothing on the {kind} line"
    assert not caught_by_scan(MODULE_SOURCE)


def test_the_scan_reads_past_a_comment_holding_a_colour():
    """A scan treating a comment as code would report a colour the module only names."""
    found = js_literals('// #00ffcc\nvar kept = "kept";')
    assert found["strings"] == ["kept"]
    assert not found["numbers"]


def test_each_written_value_is_caught_in_the_module_file_itself():
    """The original is read inside the swap, and the restore is proved by digest
    after each line."""
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
            assert after == before, f"the file was not put back after {kind}"
    finally:
        swap_module(MODULE_PATH, original)
    quiet = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not quiet, f"the scan reported nothing on these lines in the file: {quiet}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before
    assert MODULE_PATH.read_text(encoding="utf-8") == MODULE_SOURCE
    assert not list(MODULE_PATH.parent.glob(MODULE_PATH.stem + ".swap.*.tmp"))


def test_the_written_file_is_still_a_module_the_page_can_run(js: JsRuntime):
    """A written line that broke the parse would leave the scan reporting on an
    unloadable module."""
    for kind, line in sorted(WRITTEN_LINES.items()):
        runtime = JsRuntime(js.engine_of(), MODULE_SOURCE + line)
        assert runtime.json("typeof acervatorSetDesignSystem") == "function", kind


def test_no_line_in_the_module_runs_past_the_column_limit():
    """Neither the formatter nor the linter reads a long comment, so this counts
    the columns."""
    long_lines = [
        (number, len(line))
        for number, line in enumerate(MODULE_SOURCE.splitlines(), 1)
        if len(line) > 88
    ]
    assert not long_lines, f"{MODULE_PATH.name} runs past 88 columns: {long_lines}"


# -- 8. a hostile payload, each field damaged in turn -------------------


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    """A bridge answering with a word must not be read one letter at a
    time as a list of groups."""
    for wrong in ("a string", 7, None, ["a", "list"], True):
        counts = js.load(wrong, SHADOW_COLOUR)
        assert counts["declared"] == 0
        assert js.ask("isLoaded") is False
        assert js.ask("faults") == [
            {"name": "group_members", "fault": "not-an-object", "detail": None}
        ]


def test_a_group_list_sent_as_a_word_is_not_read_one_letter_at_a_time(
    js: JsRuntime,
):
    """A word where a list belongs would otherwise publish one group per
    letter and render nothing under any of them."""
    payload = bridge_payload()
    payload["group_names"] = "colors"
    js.load(payload, SHADOW_COLOUR)
    assert js.ask("groupNames") == []
    assert js.ask("declarationNames") == []
    assert js.ask("counts")["groups"] == 0


def test_a_group_member_list_sent_as_a_word_is_named_not_walked(js: JsRuntime):
    """The same one level down, where the letters would each become a
    token name."""
    payload = bridge_payload()
    payload["group_members"]["shadows"] = "SHADOW_0"
    js.load(payload, SHADOW_COLOUR)
    assert js.ask("groupOrder", "shadows") == []
    assert {"name": "shadows", "fault": "not-a-list", "detail": "group_members"} in (
        js.ask("faults")
    )
    assert js.ask("declaration", "S") is None


def test_a_scalar_and_a_null_inside_a_list_are_named_not_rendered(js: JsRuntime):
    """A number or a null where a token name belongs must be named, never rendered."""
    payload = bridge_payload()
    payload["group_members"]["shadows"] = [7, None, "SHADOW_0"]
    js.load(payload, SHADOW_COLOUR)
    named = {row["name"]: row["fault"] for row in js.ask("faults")}
    assert named["7"] == "not-text"
    assert named["null"] == "not-text"
    assert js.ask("value", "SHADOW_0") is not None
    assert js.ask("value", "7") is None


HOSTILE_FIELDS = ("group_names", "group_members", "alias_targets")


def test_each_field_missing_leaves_the_module_reporting_rather_than_raising(
    js: JsRuntime,
):
    """A field the surface stops sending must not stop the whole screen."""
    for field in HOSTILE_FIELDS:
        payload = bridge_payload()
        del payload[field]
        counts = js.load(payload, SHADOW_COLOUR)
        assert js.ask("isLoaded") is True
        if field == "alias_targets":
            assert counts["declared"] == len(dss.TOKEN_NAMES)
        else:
            assert counts["declared"] == 0


def test_each_field_null_leaves_the_module_reporting_rather_than_raising(
    js: JsRuntime,
):
    """The opposite shape of the same fault."""
    for field in HOSTILE_FIELDS:
        payload = bridge_payload()
        payload[field] = None
        js.load(payload, SHADOW_COLOUR)
        assert js.ask("isLoaded") is True
        assert isinstance(js.ask("faults"), list)


def test_a_group_the_module_has_no_kind_for_is_named_not_guessed(js: JsRuntime):
    """A group the surface adds must not render under a guessed unit."""
    payload = bridge_payload()
    payload["group_names"] = list(dss.GROUP_NAMES) + ["elevations"]
    payload["group_members"]["elevations"] = ["SPACE_M"]
    js.load(payload, SHADOW_COLOUR)
    assert js.ask("value", "SPACE_M") == "16px"
    payload["group_members"]["elevations"] = ["ELEVATION_1"]
    js.load(payload, SHADOW_COLOUR)
    named = {row["name"]: row["fault"] for row in js.ask("faults")}
    assert named["ELEVATION_1"] == "unknown-kind"


def test_a_duplicate_group_member_renders_once(js: JsRuntime):
    """A name in two groups would otherwise render twice, and the second
    kind would decide what a screen paints."""
    payload = bridge_payload()
    payload["group_members"]["radii"] = list(dss.RADIUS_NAMES) + ["SPACE_M"]
    js.load(payload, SHADOW_COLOUR)
    names = js.ask("declarationNames")
    assert names.count("SPACE_M") == 1
    assert js.ask("groupOf", "SPACE_M") == "spacing"


HOSTILE_TOKEN_VALUES = {
    "SPACE_M": "sixteen",
    "FONT_FAMILY_UI": 7,
    "MOTION_MEDIUM": 10**24,
    "TYPE_BODY": None,
    "SURFACE_0": "not-a-colour",
    "SHADOW_1": "not-a-shadow",
}


def test_every_damaged_token_value_is_named_and_renders_nothing(js: JsRuntime):
    """Six damaged token values, each of a different shape, must each be named and
    render nothing."""
    payload = bridge_payload()
    payload["tokens"].update(HOSTILE_TOKEN_VALUES)
    js.load(payload, SHADOW_COLOUR)
    named = {row["name"]: row["fault"] for row in js.ask("faults")}
    assert named["SPACE_M"] == "not-a-number"
    assert named["FONT_FAMILY_UI"] == "not-text"
    assert named["MOTION_MEDIUM"] == "not-a-plain-number"
    assert named["TYPE_BODY"] == "not-a-number"
    assert named["SURFACE_0"] == "not-a-colour"
    assert named["SHADOW_1"] == "not-a-shadow"
    for name in HOSTILE_TOKEN_VALUES:
        if name == "SURFACE_0":
            continue
        assert js.ask("value", name) is None, name


def test_a_damaged_value_shortens_the_held_count_only(js: JsRuntime):
    """The opposite of the counts check, on a payload carrying six faults."""
    payload = bridge_payload()
    payload["tokens"].update(HOSTILE_TOKEN_VALUES)
    counts = js.load(payload, SHADOW_COLOUR)
    assert counts["declared"] == len(dss.TOKEN_NAMES)
    assert counts["held"] == len(dss.TOKEN_NAMES) - len(HOSTILE_TOKEN_VALUES) + 1
    assert counts["faults"] == len(HOSTILE_TOKEN_VALUES)


def test_a_number_that_is_not_a_number_renders_nothing(js: JsRuntime):
    """NaN and both infinities reach the module through a page rather than
    through the bridge, and each must render nothing."""
    js.load(bridge_payload(), SHADOW_COLOUR)
    for expression in ("NaN", "Infinity", "-Infinity"):
        js.run(
            "acervatorSetTokens((function () {"
            "  var m = JSON.parse(PAYLOAD); m.tokens.SPACE_M = " + expression + ";"
            "  return m; })());"
        )
        js.run("acervatorSetDesignSystem(JSON.parse(PAYLOAD), JSON.parse(COLOUR));")
        assert js.ask("value", "SPACE_M") is None, expression


def test_the_bridge_cannot_carry_a_number_that_is_not_a_number():
    """A NaN reaches the page through the bridge as text no parser accepts."""
    assert json.dumps(float("nan")) == "NaN"
    assert json.dumps(float("inf")) == "Infinity"


def test_a_very_long_token_name_is_carried_rather_than_cut(js: JsRuntime):
    """A name of two hundred characters must reach the fault record whole and uncut."""
    long_name = "T" * 200
    payload = bridge_payload()
    payload["group_members"]["spacing"] = list(dss.SPACE_NAMES) + [long_name]
    js.load(payload, SHADOW_COLOUR)
    named = {row["name"]: row["fault"] for row in js.ask("faults")}
    assert named[long_name] == "no-value"
    assert len(long_name) == 200


def test_markup_and_a_newline_in_a_token_name_are_carried_as_text(js: JsRuntime):
    """A name is never treated as markup, so nothing it holds can reach a
    page as an element."""
    payload = bridge_payload()
    odd = ["<script>alert(1)</script>", "a\nb"]
    payload["group_members"]["spacing"] = list(dss.SPACE_NAMES) + odd
    js.load(payload, SHADOW_COLOUR)
    named = {row["name"]: row["fault"] for row in js.ask("faults")}
    for name in odd:
        assert named[name] == "no-value"
    assert js.ask("declaration", odd[0]) is None


def test_a_name_no_token_carries_is_named_rather_than_rendered_empty(
    js: JsRuntime,
):
    """A group naming a token the table does not hold must say so, not render an
    empty declaration."""
    payload = bridge_payload()
    payload["group_members"]["spacing"] = list(dss.SPACE_NAMES) + ["SPACE_HUGE"]
    js.load(payload, SHADOW_COLOUR)
    named = {row["name"]: row["fault"] for row in js.ask("faults")}
    assert named["SPACE_HUGE"] == "no-value"
    assert js.ask("declaration", "SPACE_HUGE") is None


def test_a_name_every_object_inherits_is_not_a_token(loaded: JsRuntime):
    """Reading an inherited name as a token would hand a screen a function
    where a colour belongs."""
    for inherited in ("constructor", "toString", "hasOwnProperty", "valueOf"):
        assert loaded.json(
            "typeof acervatorDesignSystem.value('" + inherited + "')"
        ) == ("undefined")
        assert loaded.ask("groupOrder", inherited) == []
        assert loaded.ask("aliasTarget", inherited) is None


def test_the_inherited_name_check_still_reads_a_real_token(loaded: JsRuntime):
    """A read answering nothing for every name would serve no declaration at all."""
    assert loaded.ask("value", "SURFACE_0") == dss.SURFACE_0
    assert loaded.ask("groupOrder", "shadows") == list(dss.SHADOW_NAMES)
    assert loaded.ask("aliasTarget", "BG") == "SURFACE_0"


def test_the_module_reports_rather_than_raises_without_a_token_table(qapp):
    """A page that runs this module and not the token table must say so."""
    assert qapp is not None
    alone = JsRuntime(new_engine(), MODULE_SOURCE)
    alone.bind_json("PAYLOAD", bridge_payload())
    alone.bind_json("COLOUR", SHADOW_COLOUR)
    counts = alone.json(
        "acervatorSetDesignSystem(JSON.parse(PAYLOAD), JSON.parse(COLOUR))"
    )
    assert counts["declared"] == 0
    assert alone.json("acervatorDesignSystem.faults()") == [
        {"name": "group_names", "fault": "no-token-table", "detail": None}
    ]


# -- 9. what Chromium computes from the declarations -------------------


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

    def load(self, payload: dict, colour: str) -> Any:
        """Push one payload into both modules inside the page."""
        self.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
        self.js("window.COLOUR = " + json.dumps(colour) + ";")
        return json.loads(
            self.js(
                "JSON.stringify((function () {"
                "  var m = JSON.parse(window.PAYLOAD);"
                "  acervatorSetTokens(m);"
                "  return acervatorSetDesignSystem(m, window.COLOUR); })())"
            )
        )

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


#: Reads one whole declaration back off a probe element, typing no value here.
READ_DECLARATION = """
(function (rows) {
  var host = document.createElement('div');
  host.setAttribute('data-part', 'probe-host');
  document.body.appendChild(host);
  var out = {};
  rows.forEach(function (row) {
    var kid = document.createElement('div');
    kid.setAttribute('data-part', 'probe-' + row.name);
    host.appendChild(kid);
    kid.style.setProperty(row.variable, row.value);
    kid.style.setProperty(row.property, row.reference);
    out[row.name] = getComputedStyle(kid)[row.read_as];
  });
  var marked = host.querySelectorAll('[data-part]').length;
  var every = host.querySelectorAll('*').length;
  host.remove();
  return JSON.stringify({ read: out, marked: marked, every: every });
})(JSON.parse(window.ROWS))
"""

#: One token of each kind, with the CSS property a screen paints it into.
RENDERED_CASES = (
    ("SPACE_M", "padding", "paddingTop"),
    ("RADIUS_MD", "border-radius", "borderTopLeftRadius"),
    ("TYPE_BODY", "font-size", "fontSize"),
    ("MOTION_MEDIUM", "transition-duration", "transitionDuration"),
    ("WEIGHT_BOLD", "font-weight", "fontWeight"),
    ("SURFACE_0", "color", "color"),
    ("GLOW_PRIMARY", "color", "color"),
    ("SCRIM", "color", "color"),
    ("SHADOW_2", "box-shadow", "boxShadow"),
)


def rendered_rows(rows: list) -> list:
    """Pair each declaration with the property it is painted into, by name."""
    by_name = {row["name"]: row for row in rows}
    found = []
    for name, prop, read_as in RENDERED_CASES:
        row = dict(by_name[name])
        row["property"] = prop
        row["read_as"] = read_as
        found.append(row)
    return found


def test_the_rendered_cases_and_the_surface_name_the_same_tokens():
    """Both lists are counted before pairing, so a case naming a dropped token is
    named here."""
    named = [name for name, _, _ in RENDERED_CASES]
    assert len(named) == len(set(named))
    assert set(named) <= set(dss.TOKEN_NAMES)


def test_every_kind_of_declaration_computes_in_the_browser(browser: Browser):
    """Each declaration is set on a probe through its own custom property and read
    back computed."""
    payload = bridge_payload()
    counts = browser.load(payload, SHADOW_COLOUR)
    assert counts["held"] == len(dss.TOKEN_NAMES)
    rows = rendered_rows(
        json.loads(browser.js("JSON.stringify(acervatorDesignSystem.declarations())"))
    )
    browser.js("window.ROWS = " + json.dumps(json.dumps(rows)) + ";")
    found = json.loads(browser.js(READ_DECLARATION))
    read = found["read"]
    assert read["SPACE_M"] == "16px"
    assert read["RADIUS_MD"] == "12px"
    assert read["TYPE_BODY"] == "13px"
    assert read["MOTION_MEDIUM"] == "0.25s"
    assert read["WEIGHT_BOLD"] == "700"
    assert read["SURFACE_0"] == "rgb(10, 10, 15)"
    assert read["GLOW_PRIMARY"] == "rgba(0, 255, 204, 0.2)"
    assert read["SCRIM"] == "rgba(0, 0, 0, 0.533)"
    assert read["SHADOW_2"] == "rgba(0, 0, 0, 0.314) 0px 2px 4px 0px"


def test_the_raw_surface_value_computes_to_nothing_in_the_browser(
    browser: Browser,
):
    """The same tokens written as the surface holds them paint no size and no tint."""
    rows = []
    for name, prop, read_as in RENDERED_CASES:
        if name == "SHADOW_2":
            continue
        rows.append(
            {
                "name": name,
                "variable": "--" + name,
                "reference": "var(--" + name + ")",
                "value": str(dss.TOKENS[name]),
                "property": prop,
                "read_as": read_as,
            }
        )
    browser.js("window.ROWS = " + json.dumps(json.dumps(rows)) + ";")
    read = json.loads(browser.js(READ_DECLARATION))["read"]
    assert read["SPACE_M"] == "0px"
    assert read["RADIUS_MD"] == "0px"
    assert read["MOTION_MEDIUM"] == "0s"
    assert read["GLOW_PRIMARY"] == "rgb(0, 255, 204)"
    assert read["SCRIM"] == "rgb(0, 0, 0)"
    assert read["TYPE_BODY"] != "13px"


def test_a_reference_resolves_to_its_own_token_and_not_to_the_page(
    browser: Browser,
):
    """A reference written without the two dashes falls back to the colour the page
    inherits."""
    browser.load(bridge_payload(), SHADOW_COLOUR)
    found = json.loads(
        browser.js(
            "JSON.stringify((function () {"
            "  var host = document.createElement('div');"
            "  host.setAttribute('data-part', 'resolve-host');"
            "  document.body.appendChild(host);"
            "  host.style.color = 'rgb(1, 2, 3)';"
            "  var row = acervatorDesignSystem.declarations()"
            "    .filter(function (r) { return r.name === 'SURFACE_0'; })[0];"
            "  var right = document.createElement('div');"
            "  right.setAttribute('data-part', 'right');"
            "  host.appendChild(right);"
            "  right.style.setProperty(row.variable, row.value);"
            "  right.style.color = row.reference;"
            "  var wrong = document.createElement('div');"
            "  wrong.setAttribute('data-part', 'wrong');"
            "  host.appendChild(wrong);"
            "  wrong.style.setProperty(row.variable, row.value);"
            "  wrong.style.color = 'var(' + row.name + ')';"
            "  var out = {"
            "    right: getComputedStyle(right).color,"
            "    wrong: getComputedStyle(wrong).color,"
            "    page: getComputedStyle(host).color };"
            "  host.remove();"
            "  return out; })())"
        )
    )
    assert found["page"] == "rgb(1, 2, 3)"
    assert found["right"] == "rgb(10, 10, 15)"
    assert found["wrong"] == found["page"]
    assert found["right"] != found["page"]


def test_every_element_the_probe_puts_on_the_page_is_marked(browser: Browser):
    """Each element carries a name, so nothing reaches the page unnamed."""
    browser.load(bridge_payload(), SHADOW_COLOUR)
    rows = rendered_rows(
        json.loads(browser.js("JSON.stringify(acervatorDesignSystem.declarations())"))
    )
    browser.js("window.ROWS = " + json.dumps(json.dumps(rows)) + ";")
    found = json.loads(browser.js(READ_DECLARATION))
    assert found["every"] == found["marked"] == len(RENDERED_CASES)


def test_the_marking_check_names_an_unmarked_element(browser: Browser):
    """A count reading the same for both would pass on a page full of unnamed
    elements."""
    found = json.loads(
        browser.js(
            "JSON.stringify((function () {"
            "  var host = document.createElement('div');"
            "  document.body.appendChild(host);"
            "  host.appendChild(document.createElement('span'));"
            "  var kid = document.createElement('span');"
            "  kid.setAttribute('data-part', 'named');"
            "  host.appendChild(kid);"
            "  var out = { every: host.querySelectorAll('*').length,"
            "    marked: host.querySelectorAll('[data-part]').length };"
            "  host.remove(); return out; })())"
        )
    )
    assert found["every"] == 2
    assert found["marked"] == 1


def test_the_module_adds_no_element_to_the_page(browser: Browser):
    """This module writes style and draws nothing, so the element count is
    the same after the whole module has run."""
    before = browser.js("document.querySelectorAll('*').length")
    browser.load(bridge_payload(), SHADOW_COLOUR)
    browser.js("acervatorDesignSystem.apply(document.documentElement);")
    assert browser.js("document.querySelectorAll('*').length") == before


def test_every_declaration_lands_on_the_page_as_a_custom_property(
    browser: Browser,
):
    """Each value is taken back off the rendered document, never off the object
    that wrote it."""
    browser.load(bridge_payload(), SHADOW_COLOUR)
    written = json.loads(
        browser.js(
            "JSON.stringify(acervatorDesignSystem.apply(document.documentElement))"
        )
    )
    assert written == published_order()
    read_back = json.loads(
        browser.js(
            "JSON.stringify((function () {"
            "  var style = getComputedStyle(document.documentElement);"
            "  var out = {};"
            "  acervatorDesignSystem.declarationNames().forEach(function (n) {"
            "    out[n] = style.getPropertyValue('--' + n).trim(); });"
            "  return out; })())"
        )
    )
    expected = json.loads(
        browser.js(
            "JSON.stringify((function () {"
            "  var out = {};"
            "  acervatorDesignSystem.declarationNames().forEach(function (n) {"
            "    out[n] = acervatorDesignSystem.value(n); });"
            "  return out; })())"
        )
    )
    differing = {
        name: (value, read_back.get(name))
        for name, value in expected.items()
        if read_back.get(name) != value
    }
    assert not differing, f"{len(differing)} declarations reached no stylesheet"


def test_the_page_makes_no_network_call_while_the_module_runs(browser: Browser):
    """Driving the whole module raises no policy violation, so nothing in
    it reaches for the network."""
    browser.js(
        "window.VIOLATIONS = [];"
        "document.addEventListener('securitypolicyviolation', function (e) {"
        "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
    )
    browser.load(bridge_payload(), SHADOW_COLOUR)
    browser.js("acervatorDesignSystem.apply(document.documentElement);")
    assert json.loads(browser.js("JSON.stringify(window.VIOLATIONS)")) == []
