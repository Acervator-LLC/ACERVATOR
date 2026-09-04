"""The React side of the Launcher screen.

WHAT IS PROVED
==============
``src/gui/web/launcher.js`` draws the Launcher from the payload
``src/gui/main_tabs/launcher_surface.py`` serves: a heading, a prompt,
two mode cards side by side and a footer. It carries no wording, colour
or measurement of its own.

The work the module does for itself is reading Qt's style sheets. A Qt
sheet names a selector and may carry a ``:hover`` block; an inline style
holds neither, so the base declarations are painted inline and every
hover value is published as a custom property the page's own rule reads.

THE EIGHT-DIGIT COLOUR
======================
The launch button's hover fill is the card colour with a two-character
alpha appended. Qt reads eight hex digits as ``#AARRGGBB`` and a browser
reads them as ``#RRGGBBAA``, so the SAME string is a translucent card
colour in a browser and a fully transparent near-white under Qt. The
browser reading is the one the wording intends; the checks below pin it.

The Qt window this module replaces is NOT removed. The last section
builds ``LauncherWindow`` and counts its live Qt children.

HOW THE JAVASCRIPT IS RUN
=========================
Node is not installed and nothing here adds a JavaScript test runner.
``QJSEngine`` from ``PySide6.QtQml`` runs the module as plain JavaScript
and answers in JSON, through ``tests/fixtures/web_js_modules.py``.
"""

from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

pytest.importorskip("PySide6")

from src.core import desktop_bridge
from src.gui.main_tabs import launcher_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    load_order,
    new_engine,
    runs_after,
)

MODULE_NAME = "launcher.js"
MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / MODULE_NAME

MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every number the module writes, and what it is.
ALGORITHM_NUMBERS = {
    "0",  # the first entry of a pair, and the left margin
    "1",  # one step along a list: the second entry of a pair
    "2",  # the right margin
    "3",  # the bottom margin
    "100",  # a gradient stop is a share of the run; CSS wants a percentage
}

#: Words the module writes as markup: an HTML tag, a CSS property, or
#: the name it marks a rendered part with. Each also happens to be a
#: value the payload publishes, so the value check would report the
#: module for writing markup. The planted-value controls prove the check
#: still names real wording.
MARKUP_WORDS = {
    "button",  # the tag of the launch button, and the name of a press kind
    "card",  # the part name a card is marked with, and a press kind
    "color",  # the CSS property, and the key a card's colour arrives under
    "title",  # the key a card's heading arrives under
}

#: How many hex digits a colour with an alpha carries.
ALPHA_HEX_DIGITS = 8

#: The Qt class of a launcher widget -> what it is on the screen.
QT_WIDGET_KINDS = {"ModeCard": "card", "QLabel": "label", "QPushButton": "button"}


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON."""
    return json.loads(json.dumps(surface.view_model(params), ensure_ascii=True))


def fresh_payload(**params: Any) -> dict:
    """One payload from a screen with no press recorded on it."""
    params.setdefault("reset", True)
    return bridge_payload(**params)


class JsRuntime(JsEngine):
    """A QJSEngine holding ``launcher.js`` and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetLauncher"

    def answer(self, call: str) -> Any:
        """One value the module's own namespace answers with."""
        return self.json("acervatorLauncher." + call)


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding a freshly opened Launcher."""
    js.push(fresh_payload())
    return js


# -- 1. the module answers the method the bridge serves -----------------


def test_the_module_asks_for_the_method_the_surface_answers(js: JsRuntime):
    """The module asked the bridge for a method no surface serves."""
    assert js.answer("method") == surface.METHOD


def test_the_bridge_serves_the_method_the_module_asks_for(js: JsRuntime):
    """The bridge lost the handler the module calls."""
    served = desktop_bridge.build_registry()
    assert js.answer("method") in served, sorted(served)


# -- 2. every field the module draws from reaches it --------------------


def test_every_field_the_module_declares_reaches_it_from_the_surface(
    loaded: JsRuntime,
):
    """A field the module draws from is in no payload the surface serves."""
    payload = fresh_payload()
    declared = loaded.answer("declaredFields()")
    assert declared, "the module declares no field at all"
    missing = sorted(name for name in declared if name not in payload)
    assert not missing, f"{len(missing)} declared fields never arrive: {missing}"
    assert loaded.answer("faults()") == []


def test_the_field_check_names_a_field_the_payload_never_carries(js: JsRuntime):
    """The field check passed because it looked at nothing."""
    payload = fresh_payload()
    dropped = js.answer("declaredFields()")[0]
    del payload[dropped]
    report = js.push(payload)
    named = [one["field"] for one in report["faults"]]
    assert named == [dropped], report["faults"]


def test_a_payload_that_is_not_an_object_is_refused(js: JsRuntime):
    """The module drew a screen from something that is not a payload."""
    report = js.push(0)
    assert report["held"] is None
    assert [one["fault"] for one in report["faults"]] == ["not-an-object"]
    assert js.answer("isLoaded()") is False


# -- 3. what the screen draws ------------------------------------------


def test_the_module_draws_the_two_cards_the_surface_names(loaded: JsRuntime):
    """A trading mode the surface offers reached no screen."""
    assert loaded.answer("cardNames()") == list(surface.CARD_ORDER)
    assert loaded.answer("screenOrder()") == list(surface.WINDOW_ORDER)


def test_every_card_draws_its_children_in_the_order_the_surface_names(
    loaded: JsRuntime,
):
    """A feature line was drawn above the title it belongs under."""
    for name in surface.CARD_ORDER:
        order = loaded.answer(f'cardChildOrder("{name}")')
        assert order[: len(surface.CARD_HEAD_ORDER)] == list(surface.CARD_HEAD_ORDER)
        assert order[-len(surface.CARD_TAIL_ORDER) :] == list(surface.CARD_TAIL_ORDER)
        features = loaded.answer(f'featureTexts("{name}")')
        assert len(order) == len(surface.CARD_HEAD_ORDER) + len(features) + len(
            surface.CARD_TAIL_ORDER
        ), (name, order)


def test_every_feature_line_the_surface_names_reaches_its_card(loaded: JsRuntime):
    """A selling point of one mode reached no card."""
    published = {
        surface.CRYPTO_CARD: surface.CRYPTO_FEATURES,
        surface.STOCKS_CARD: surface.STOCKS_FEATURES,
    }
    for name, features in published.items():
        assert features, name
        drawn = loaded.answer(f'featureTexts("{name}")')
        assert drawn == [surface.feature_text(one) for one in features], name


def test_the_two_cards_carry_different_colours(loaded: JsRuntime):
    """Two modes painted in one colour cannot be told apart."""
    crypto = loaded.answer(f'cardOf("{surface.CRYPTO_CARD}")')
    stocks = loaded.answer(f'cardOf("{surface.STOCKS_CARD}")')
    assert crypto["color"] == surface.CRYPTO_COLOR
    assert stocks["color"] == surface.STOCKS_COLOR
    assert crypto["color"] != stocks["color"]


# -- 4. the Qt style sheets a browser cannot read as they are -----------


def test_a_qt_selector_block_becomes_the_declarations_a_browser_reads(
    loaded: JsRuntime,
):
    """Qt names its own class in the sheet. A browser reads none of it,
    so the block's contents are what the card carries."""
    painted = loaded.answer(f'cardStyle("{surface.CRYPTO_CARD}")')
    assert painted, surface.CARD_STYLE_FORMAT
    assert surface.CARD_TYPE_NAME not in json.dumps(painted), painted
    assert painted["background"] == surface.CARD_BACKGROUND
    assert painted["borderRadius"], painted


def test_a_hover_rule_becomes_a_custom_property_beside_the_base_style(
    loaded: JsRuntime,
):
    """An inline style holds no pseudo-state, so a hover value copied
    into one would paint on every card at rest."""
    prefix = loaded.answer("hoverPrefix")
    hover = loaded.answer(f'cardHover("{surface.CRYPTO_CARD}")')
    assert hover, "the card sheet carries no hover rule at all"
    painted = loaded.answer(f'cardStyle("{surface.CRYPTO_CARD}")')
    for name, value in hover.items():
        assert painted[prefix + name] == value, (name, painted)
        assert name not in painted, (name, painted)


def test_the_hover_check_names_a_hover_value_painted_at_rest(loaded: JsRuntime):
    """The hover check passed because the sheet named no hover rule."""
    hover = loaded.answer(f'cardHover("{surface.CRYPTO_CARD}")')
    painted = loaded.answer(f'cardStyle("{surface.CRYPTO_CARD}")')
    assert set(hover) & set(painted) == set(), (hover, painted)
    blinded = dict(painted)
    for name, value in hover.items():
        blinded[name] = value
    assert set(hover) & set(blinded) == set(hover), blinded


# -- 5. the eight-digit hover colour -----------------------------------


def test_the_button_hover_fill_is_read_red_first_not_alpha_first(
    loaded: JsRuntime,
):
    """Qt reads eight hex digits alpha first and a browser reads them red
    first, so one string is two colours. The browser reading keeps the
    card's own hue; Qt's reading throws it away."""
    hover = loaded.answer(f'buttonHover("{surface.CRYPTO_CARD}")')
    fill = hover["background"]
    assert fill == surface.hover_color(surface.CRYPTO_COLOR), fill
    digits = fill.lstrip("#")
    assert len(digits) == ALPHA_HEX_DIGITS, fill
    assert digits[:6].lower() == surface.CRYPTO_COLOR.lstrip("#").lower(), fill
    browser_alpha = int(digits[6:], 16)
    qt_alpha = int(digits[:2], 16)
    assert browser_alpha != qt_alpha, (
        "this colour no longer tells the two readings apart, so the "
        "check cannot fail"
    )
    assert 0 < browser_alpha < 255, browser_alpha


def test_the_hover_fill_keeps_the_card_colour_the_base_fill_uses(
    loaded: JsRuntime,
):
    """The positive control: the base fill is the same hue, opaque."""
    base = loaded.answer(f'buttonStyle("{surface.CRYPTO_CARD}")')
    assert base["background"] == surface.CRYPTO_COLOR, base
    assert base["color"] == surface.BUTTON_TEXT_COLOR, base


# -- 6. the background wash and the drop shadow ------------------------


def test_the_background_wash_carries_every_stop_the_surface_names(
    loaded: JsRuntime,
):
    """A colour of the background wash reached no screen."""
    wash = loaded.answer("backgroundWash()")
    assert wash, "the module draws no wash at all"
    for _, colour in surface.GRADIENT_STOPS:
        assert colour in wash, (colour, wash)
    assert wash.count(",") == len(surface.GRADIENT_STOPS), wash


def test_the_drop_shadow_is_painted_in_the_card_colour(loaded: JsRuntime):
    """The glow around a card is the card's own colour, not a default."""
    for name, colour in (
        (surface.CRYPTO_CARD, surface.CRYPTO_COLOR),
        (surface.STOCKS_CARD, surface.STOCKS_COLOR),
    ):
        shadow = loaded.answer(f'cardShadow("{name}")')
        assert shadow.endswith(colour), (name, shadow)
        assert str(surface.SHADOW_BLUR_RADIUS_PX) in shadow, (name, shadow)


def test_a_centred_line_is_centred_and_a_feature_line_is_not(
    loaded: JsRuntime,
):
    """Qt carries an alignment as a number; CSS carries it as a word."""
    centred = loaded.answer(f"alignmentWord({surface.ALIGN_CENTER_VALUE})")
    leading = loaded.answer(f"alignmentWord({surface.FEATURE_ALIGNMENT_VALUE})")
    assert centred != leading, (centred, leading)
    assert centred == "center"


# -- 7. the presses the screen records ---------------------------------


def test_a_fresh_screen_has_recorded_no_press(js: JsRuntime):
    """The screen opened with a mode already chosen."""
    js.push(fresh_payload())
    assert js.answer("pressCalls()") == list(surface.NO_PRESSES)
    for name in surface.CARD_ORDER:
        assert js.answer(f'cardOf("{name}")')["clicks"] == surface.FIRST_CLICK_COUNT


def test_pressing_a_card_records_the_mode_it_opens(js: JsRuntime):
    """The positive control: a press does reach the screen."""
    js.push(bridge_payload(reset=True, presses=[[surface.CARD_PRESS, 0]]))
    calls = js.answer("pressCalls()")
    assert [one[0] for one in calls] == [
        surface.PRESS_CARD,
        surface.CARD_CLICKED,
        surface.CRYPTO_SELECTED,
    ], calls
    assert js.answer(f'cardOf("{surface.CRYPTO_CARD}")')["clicks"] == 1


# -- 8. the module carries no value of its own -------------------------


#: A value this short is punctuation, not a product value.
SHORTEST_VALUE = 2


def surface_text() -> tuple:
    """Every value the surface publishes, and every key it publishes under."""
    values: set = set()
    keys: set = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for name, one in value.items():
                keys.add(str(name))
                walk(one)
            return
        if isinstance(value, (list, tuple)):
            for one in value:
                walk(one)
            return
        if isinstance(value, bool) or value is None:
            return
        as_text = str(value)
        if len(as_text) >= SHORTEST_VALUE:
            values.add(as_text)

    walk(surface.build_view_model(surface.LauncherModel()))
    return values, keys


PUBLISHED_VALUES, PUBLISHED_KEYS = surface_text()
SURFACE_VALUES = PUBLISHED_VALUES - PUBLISHED_KEYS - MARKUP_WORDS


def test_the_module_writes_no_colour():
    """A colour spelled in the module is a second skin for one screen."""
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"{MODULE_NAME} holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_surface_publishes():
    """A value spelled in the module is a second source of truth."""
    written = sorted(set(MODULE_LITERALS["strings"]) & SURFACE_VALUES)
    assert not written, f"{MODULE_NAME} spells out surface values: {written}"


def test_every_number_the_module_writes_is_an_algorithm_constant():
    """A number outside the drawing arithmetic is a value the surface owns."""
    stray = sorted(set(MODULE_LITERALS["numbers"]) - ALGORITHM_NUMBERS)
    assert not stray, f"{MODULE_NAME} holds unexplained numbers: {stray}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    """A slash the scan cannot read could hide any value at all."""
    assert not MODULE_LITERALS["slashes"], MODULE_LITERALS["slashes"]


PLANTED_LINES = {
    "colour": 'var spelled = "' + surface.CRYPTO_COLOR + '";',
    "heading": 'var spelled = "' + surface.HEADING_TEXT + '";',
    "feature": 'var spelled = "' + surface.CRYPTO_FEATURES[0] + '";',
    "measurement": "var spelled = " + str(surface.CARD_WIDTH_PX) + ";",
    "number": "var spelled = 4913;",
    "regex": "var spelled = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    """Which of the four checks report on `source`."""
    found = js_literals(source)
    caught = set()
    if HEX_COLOUR.findall(source):
        caught.add("colour")
    if set(found["strings"]) & SURFACE_VALUES:
        caught.add("value")
    if set(found["numbers"]) - ALGORITHM_NUMBERS:
        caught.add("number")
    if found["slashes"]:
        caught.add("slash")
    return caught


@pytest.mark.parametrize("kind", sorted(PLANTED_LINES))
def test_the_literal_scan_names_a_line_that_spells_a_value_out(kind: str):
    """The controls for the four scan checks."""
    assert caught_by_scan(PLANTED_LINES[kind]), kind


def test_the_value_set_still_holds_the_wording_a_screen_shows():
    """The value check passed because its set was emptied by the trims."""
    assert SURFACE_VALUES, "the surface publishes no value the module could spell"
    assert surface.HEADING_TEXT in SURFACE_VALUES
    assert surface.CRYPTO_TITLE in SURFACE_VALUES
    assert surface.CRYPTO_COLOR in SURFACE_VALUES
    assert MARKUP_WORDS <= PUBLISHED_VALUES | PUBLISHED_KEYS, sorted(MARKUP_WORDS)


# -- 9. the renderer runs the module -----------------------------------


def test_the_renderer_runs_the_module_after_react():
    """A module the page never runs draws nothing, whatever it holds."""
    order = load_order()
    assert MODULE_NAME in order, order
    assert runs_after(order, MODULE_NAME, "module_loader.js"), order


# -- 10. the Qt window this module replaces is still there --------------
#
# React does not replace a widget until the operational logs verify it.
# `LauncherWindow` is a screen, not plumbing: it builds two `ModeCard`
# frames of labels and a button, and paints its own gradient. Nothing in
# the product constructs it, so this count is the only thing standing
# between it and a quiet deletion.

#: Class name -> how many the shipped window holds. Two cards, each with
#: an icon, a title, a subtitle, six feature lines and a launch button,
#: under a heading, a prompt and a footer.
SHIPPED_CHILDREN = {
    "ModeCard": 2,
    "QLabel": 3 + 2 * (3 + len(surface.CRYPTO_FEATURES)),
    "QPushButton": 2,
}


def live_children(window: Any) -> dict:
    """How many of each counted class `window` holds right now."""
    from PySide6.QtWidgets import QWidget

    seen = collections.Counter(
        one.metaObject().className() for one in window.findChildren(QWidget)
    )
    return {name: seen.get(name, 0) for name in SHIPPED_CHILDREN}


@pytest.fixture()
def shipped_window():
    """The real Qt launcher window, built and never shown."""
    from src.gui import launcher as shipped
    from tests.qt_pixel import ensure_app

    ensure_app()
    window = shipped.LauncherWindow()
    try:
        yield window
    finally:
        window.close()
        window.deleteLater()


def test_the_shipped_qt_window_still_holds_every_widget_it_built(
    shipped_window: Any,
):
    """A Qt widget was deleted before its React replacement was verified."""
    assert live_children(shipped_window) == SHIPPED_CHILDREN


def test_every_qt_widget_the_window_holds_is_one_the_surface_describes(
    shipped_window: Any,
):
    """A control on the Qt screen that reaches no payload is a control
    the React screen cannot draw."""
    from PySide6.QtWidgets import QWidget

    seen = collections.Counter(
        one.metaObject().className()
        for one in shipped_window.findChildren(QWidget)
        if one.metaObject().className() in QT_WIDGET_KINDS
    )
    assert set(seen) == set(QT_WIDGET_KINDS), sorted(seen)
    assert seen["ModeCard"] == len(surface.CARD_ORDER)
    assert seen["QPushButton"] == len(surface.CARD_ORDER)


def test_the_shipped_qt_window_still_paints_its_gradient(shipped_window: Any):
    """A tree that holds its widgets but paints nothing is not preserved.

    The colour is read off the composited image, never off a style sheet:
    a widget reports the colour it was TOLD to paint whether it painted
    it or not.
    """
    from tests.qt_pixel import render_widget

    image = render_widget(
        shipped_window, size=(surface.WINDOW_WIDTH_PX, surface.WINDOW_HEIGHT_PX)
    )
    down = [1, image.height() // 2, image.height() - 2]
    painted = [image.pixelColor(2, y).name() for y in down]
    assert len(set(painted)) > 1, f"the window painted one flat colour: {painted}"


def test_the_child_count_check_names_a_missing_widget(shipped_window: Any):
    """The count check passed because it compared two empty tables."""
    assert SHIPPED_CHILDREN, "no class is counted, so nothing can be missed"
    blinded = live_children(shipped_window)
    blinded["ModeCard"] -= 1
    assert blinded != SHIPPED_CHILDREN, blinded
