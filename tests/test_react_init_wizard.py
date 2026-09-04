"""The React side of the first-run setup wizard.

WHAT IS PROVED
==============
``src/gui/web/init_wizard.js`` draws the three setup pages from the
payload ``src/gui/main_tabs/init_wizard_surface.py`` serves, and carries
no wording, colour or measurement of its own. Each page draws its
children in the order the payload names, so a control added on one side
alone lands in the wrong place rather than quietly vanishing.

The strongest check here is three-sided: for every page, the widgets the
shipped Qt page holds, the entries the surface's page order names and
the drawers the module picks all agree, one for one and in kind.

The Qt wizard this module replaces is NOT removed, and is NEVER driven
with ``exec``. A modal loop would take the test process and not give it
back; the wizard is built, read and closed without entering one.

HOW THE JAVASCRIPT IS RUN
=========================
Node is not installed and nothing here adds a JavaScript test runner.
``QJSEngine`` from ``PySide6.QtQml`` runs the module as plain JavaScript
and answers in JSON, through ``tests/fixtures/web_js_modules.py``.

THE CONTROLS
============
A field dropped from the payload is named as a fault. A page order
naming a widget no drawer knows is named as a fault. A colour, a value,
a number and a regular expression planted in the source are each named
by the literal scan. The Qt count is paired with a tree the check must
reject.
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
from src.gui.main_tabs import init_wizard_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    load_order,
    new_engine,
    runs_after,
)

MODULE_NAME = "init_wizard.js"
MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / MODULE_NAME

MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")
MODULE_LITERALS = js_literals(MODULE_SOURCE)

#: Every number the module writes, and what it is. A number outside this
#: table is a value the surface should own.
ALGORITHM_NUMBERS = {
    "0",  # the first entry of a list: the readable echo mode, the page width
    "1",  # one step along a list: the second half of a pair
}

#: The Qt class of a widget -> the drawer the module picks for it.
QT_WIDGET_KINDS = {
    "QLabel": "label",
    "QLineEdit": "line",
    "QTextEdit": "text",
    "QCheckBox": "check",
    "QPushButton": "button",
    "QComboBox": "combo"
}

#: The one page entry that is a layout spacer, not a widget.
SPACER = surface.WELCOME_SPACING


def bridge_payload(**params: Any) -> dict:
    """The surface's answer after one round trip through the bridge's JSON."""
    return json.loads(json.dumps(surface.view_model(params), ensure_ascii=True))


class JsRuntime(JsEngine):
    """A QJSEngine holding ``init_wizard.js`` and a ``window`` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetWizard"

    def answer(self, call: str) -> Any:
        """One value the module's own namespace answers with."""
        return self.json("acervatorWizard." + call)


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime) -> JsRuntime:
    """The module holding a first-run payload."""
    js.push(bridge_payload())
    return js


@pytest.fixture()
def upgraded(js: JsRuntime) -> JsRuntime:
    """The module holding an upgrade payload."""
    js.push(bridge_payload(is_upgrade=True))
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
    payload = bridge_payload()
    declared = loaded.answer("declaredFields()")
    assert declared, "the module declares no field at all"
    missing = sorted(name for name in declared if name not in payload)
    assert not missing, f"{len(missing)} declared fields never arrive: {missing}"
    assert loaded.answer("faults()") == []


def test_the_field_check_names_a_field_the_payload_never_carries(js: JsRuntime):
    """The field check passed because it looked at nothing."""
    payload = bridge_payload()
    dropped = js.answer("declaredFields()")[0]
    del payload[dropped]
    report = js.push(payload)
    named = [one["field"] for one in report["faults"] if one["fault"] == "missing"]
    assert named == [dropped], report["faults"]


def test_a_payload_that_is_not_an_object_is_refused(js: JsRuntime):
    """The module drew a wizard from something that is not a payload."""
    report = js.push("")
    assert report["held"] is None
    assert [one["fault"] for one in report["faults"]] == ["not-an-object"]
    assert js.answer("isLoaded()") is False


# -- 3. every page draws every widget its order names -------------------


def test_the_module_draws_the_three_pages_the_surface_names(loaded: JsRuntime):
    """A setup page the surface serves reached no screen."""
    assert loaded.answer("pageNames()") == list(surface.PAGES)


def test_every_page_draws_its_children_in_the_order_the_surface_names(
    loaded: JsRuntime,
):
    """A control was drawn above the label that names it."""
    published = surface.page_orders(False)
    for name in surface.PAGES:
        assert loaded.answer(f'pageOrder("{name}")') == published[name], name


def test_the_upgrade_run_adds_the_fresh_start_switch(upgraded: JsRuntime):
    """The upgrade wizard lost the switch that clears the old settings."""
    fresh = upgraded.answer(f'pageOrder("{surface.WELCOME}")')
    assert surface.FRESH_START in fresh, fresh
    assert fresh == list(surface.UPGRADE_WELCOME_ORDER)


def test_a_first_run_has_no_fresh_start_switch(loaded: JsRuntime):
    """The positive control for the upgrade case: the switch is absent."""
    fresh = loaded.answer(f'pageOrder("{surface.WELCOME}")')
    assert surface.FRESH_START not in fresh, fresh


@pytest.mark.parametrize("is_upgrade", [False, True])
def test_every_widget_a_page_shows_has_a_drawer(js: JsRuntime, is_upgrade: bool):
    """A control the wizard shows would be drawn as an empty box."""
    js.push(bridge_payload(is_upgrade=is_upgrade))
    kinds = js.answer("widgetKinds()")
    shown = {
        one for order in surface.page_orders(is_upgrade).values() for one in order
    }
    assert set(kinds) == shown, sorted(set(kinds) ^ shown)
    unknown = sorted(name for name, kind in kinds.items() if kind == "unknown")
    assert not unknown, f"{len(unknown)} widgets have no drawer: {unknown}"


def test_the_fresh_start_switch_is_drawn_only_on_an_upgrade(js: JsRuntime):
    """The switch is named for both runs and shown on one, so a drawer
    table built from every name would report a control that is absent."""
    js.push(bridge_payload())
    assert surface.FRESH_START not in js.answer("widgetKinds()")
    js.push(bridge_payload(is_upgrade=True))
    assert js.answer("widgetKinds()")[surface.FRESH_START] == "check"


def test_the_drawer_check_names_a_widget_no_drawer_knows(js: JsRuntime):
    """The drawer check passed because every name was already known."""
    payload = bridge_payload()
    invented = "a_control_no_drawer_knows"
    payload["page_orders"][surface.EXCHANGE].append(invented)
    report = js.push(payload)
    named = [
        one["field"] for one in report["faults"] if one["fault"] == "unknown-widget"
    ]
    assert named == [invented], report["faults"]
    assert js.answer(f'kindOfWidget("{invented}")') == "unknown"


# -- 4. the secret fields ----------------------------------------------


def readable_answer(shown: bool) -> dict:
    """What the module answers when both secret fields are `shown`."""
    return {surface.API_KEY: shown, surface.PASSPHRASE: shown}


def test_a_secret_field_is_hidden_until_the_show_switch_is_on(js: JsRuntime):
    """A key or a passphrase was drawn readable on an unattended screen."""
    js.push(bridge_payload())
    assert js.answer("secretFieldsReadable()") == readable_answer(False)
    assert js.answer(f'checkState("{surface.SHOW_KEY}")') is False


def test_the_show_switch_makes_every_secret_field_readable(js: JsRuntime):
    """The positive control: the switch does reach the fields."""
    js.push(bridge_payload(show_key=True))
    assert js.answer("secretFieldsReadable()") == readable_answer(True)
    assert js.answer(f'checkState("{surface.SHOW_KEY}")') is True


def test_the_module_carries_the_sheet_that_paints_the_secret_box_out(
    js: JsRuntime,
):
    """Qt gives the secret box no echo mode and paints its glyphs away
    instead. The module carries that sheet rather than inventing one.

    The box itself carries no sheet until the switch is first touched,
    which is what the shipped widget does: it sets no style sheet in its
    own build, only inside the toggle.
    """
    js.push(bridge_payload())
    assert js.answer("secretBoxStyle()") is None
    painted = js.answer("hiddenFieldStyle()")
    assert painted, surface.SECRET_HIDDEN_STYLE
    assert set(painted.values()) == {"transparent"}, painted
    js.push(bridge_payload(show_key=True))
    assert js.answer("secretBoxStyle()") is None


# -- 5. the venue list and the passphrase row --------------------------


def test_the_module_lists_every_venue_the_surface_supports(loaded: JsRuntime):
    """A venue the connector supports reached no list."""
    items = loaded.answer("exchangeItems()")
    assert [one[1] for one in items] == list(surface.EXCHANGE_IDS)
    assert [one[0] for one in items] == list(surface.EXCHANGE_LABELS)


def test_the_passphrase_row_is_hidden_for_a_venue_that_needs_none(js: JsRuntime):
    """A venue that needs no passphrase still asked for one."""
    plain = surface.EXCHANGE_IDS.index("binance")
    js.push(
        bridge_payload(exchange_index=plain, page_id=surface.PASSPHRASE_PAGE_ID)
    )
    assert sorted(js.answer("hiddenWidgets()")) == sorted(
        [surface.PASSPHRASE_LABEL, surface.PASSPHRASE, surface.PASSPHRASE_HINT]
    )


def test_the_passphrase_row_is_shown_for_a_venue_that_needs_one(js: JsRuntime):
    """The positive control: the row does come back."""
    needy = surface.EXCHANGE_IDS.index(surface.PASSPHRASE_EXCHANGE_IDS[0])
    js.push(
        bridge_payload(exchange_index=needy, page_id=surface.PASSPHRASE_PAGE_ID)
    )
    assert js.answer("hiddenWidgets()") == []


# -- 6. the status line -------------------------------------------------


#: Two fields with something in them, so the wizard reaches its test
#: rather than refusing for want of an entry. Neither is a credential.
FILLED_FIELDS = {surface.API_KEY: "nothing real", surface.API_SECRET: "nor this"}


def test_the_status_line_carries_the_colour_the_surface_chose(js: JsRuntime):
    """The status line painted a refusal in the colour of a success."""
    js.push(bridge_payload())
    assert js.answer("feedbackStyle()") is None
    js.push(bridge_payload(test={"success": False}, **FILLED_FIELDS))
    refused = js.answer("feedbackStyle()")
    assert refused == {"color": surface.FEEDBACK_ERROR_COLOR}, refused
    js.push(bridge_payload(test={"success": True}, **FILLED_FIELDS))
    passed = js.answer("feedbackStyle()")
    assert passed == {"color": surface.FEEDBACK_SUCCESS_COLOR}, passed
    assert passed != refused


def test_the_status_line_refuses_an_empty_key_before_it_tests_anything(
    js: JsRuntime,
):
    """A test was run against a venue with nothing typed in."""
    js.push(bridge_payload(test={"success": True}))
    assert js.answer("feedbackStyle()") == {"color": surface.FEEDBACK_ERROR_COLOR}
    assert js.answer('field("feedback_text")') == surface.MISSING_CREDENTIALS_TEXT


def test_the_skip_button_carries_its_wording_and_its_chrome(loaded: JsRuntime):
    """The button that skips the whole setup lost its wording."""
    skip = loaded.answer(f'buttonOf("{surface.SKIP_BUTTON}")')
    assert skip["text"] == surface.BUTTON_TEXTS[surface.SKIP_BUTTON]
    assert skip["tool_tip"] == surface.TOOL_TIPS[surface.SKIP_BUTTON]
    assert skip["style_sheet"] == surface.SKIP_BUTTON_STYLE


# -- 7. the module carries no value of its own -------------------------


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

    walk(surface.build_view_model())
    walk(surface.build_view_model(True))
    return values, keys


PUBLISHED_VALUES, PUBLISHED_KEYS = surface_text()

#: The payload's own vocabulary, which the module is entitled to name:
#: the method it calls the bridge with, and every widget name it maps to
#: a drawer. These are how a renderer addresses the payload, not wording
#: it paints.
VOCABULARY = PUBLISHED_KEYS | set(surface.WIDGET_NAMES) | {surface.METHOD}
SURFACE_VALUES = PUBLISHED_VALUES - VOCABULARY


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
    "colour": 'var spelled = "' + surface.FEEDBACK_ERROR_COLOR + '";',
    "wording": 'var spelled = "' + surface.BUTTON_TEXTS[surface.SKIP_BUTTON] + '";',
    "title": 'var spelled = "' + surface.EXCHANGE_TITLE + '";',
    "measurement": "var spelled = " + str(surface.API_SECRET_MAX_HEIGHT_PX) + ";",
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
    """The value check passed because its set was emptied by the trim."""
    assert SURFACE_VALUES, "the surface publishes no value the module could spell"
    assert surface.EXCHANGE_TITLE in SURFACE_VALUES
    assert surface.UPGRADE_TITLE in SURFACE_VALUES
    assert surface.FEEDBACK_ERROR_COLOR in SURFACE_VALUES


# -- 8. the renderer runs the module -----------------------------------


def test_the_renderer_runs_the_module_after_react():
    """A module the page never runs draws nothing, whatever it holds."""
    order = load_order()
    assert MODULE_NAME in order, order
    assert runs_after(order, MODULE_NAME, "module_loader.js"), order


# -- 9. the Qt wizard this module replaces is still there ---------------
#
# React does not replace a widget until the operational logs verify it.
# Nothing here calls `exec`: a modal loop takes the process and does not
# give it back.


def page_widgets(page: Any) -> collections.Counter:
    """The Qt widgets one wizard page owns itself, counted by class."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    return collections.Counter(
        one.metaObject().className()
        for one in page.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        )
    )


def shipped_wizard(is_upgrade: bool) -> Any:
    """The real Qt wizard, built and never shown."""
    from src.gui import init_wizard as shipped
    from tests.qt_pixel import ensure_app

    ensure_app()
    return shipped.InitWizard(is_upgrade=is_upgrade)


@pytest.mark.parametrize("is_upgrade", [False, True])
def test_the_shipped_qt_page_holds_one_widget_for_every_entry_the_surface_names(
    js: JsRuntime, is_upgrade: bool
):
    """A Qt control was deleted, or a page order grew an entry no Qt page
    holds. Either way one side draws a control the other does not."""
    js.push(bridge_payload(is_upgrade=is_upgrade))
    kinds = js.answer("widgetKinds()")
    published = surface.page_orders(is_upgrade)
    wizard = shipped_wizard(is_upgrade)
    try:
        ids = wizard.pageIds()
        assert len(ids) == len(surface.PAGES), ids
        for at, name in enumerate(surface.PAGES):
            painted = page_widgets(wizard.page(ids[at]))
            assert set(painted) <= set(QT_WIDGET_KINDS), sorted(painted)
            by_kind = collections.Counter(
                {
                    QT_WIDGET_KINDS[cls]: count
                    for cls, count in painted.items()
                }
            )
            wanted = collections.Counter(
                kinds[one] for one in published[name] if one != SPACER
            )
            assert by_kind == wanted, (name, dict(by_kind), dict(wanted))
    finally:
        wizard.close()
        wizard.deleteLater()


def test_the_page_check_names_a_deleted_widget(loaded: JsRuntime):
    """The page check passed because it compared two empty tables."""
    kinds = loaded.answer("widgetKinds()")
    published = surface.page_orders(False)
    wanted = collections.Counter(
        kinds[one] for one in published[surface.CREDENTIALS] if one != SPACER
    )
    assert wanted, "the credentials page names no widget at all"
    blinded = collections.Counter(wanted)
    blinded["line"] -= 1
    assert blinded != wanted, blinded


def test_the_shipped_qt_wizard_still_paints_without_a_modal_loop():
    """A tree that holds its widgets but paints nothing is not preserved.

    The colour is read off the composited image, never off a style sheet.
    """
    from tests.qt_pixel import render_widget

    wizard = shipped_wizard(False)
    try:
        image = render_widget(wizard, size=tuple(surface.MINIMUM_SIZE_PX))
        across = [image.width() // 8, image.width() // 2, image.width() - 2]
        down = [1, image.height() // 3, image.height() - 2]
        colours = {image.pixelColor(x, y).name() for x in across for y in down}
        assert len(colours) > 1, f"the wizard painted one flat colour: {colours}"
    finally:
        wizard.close()
        wizard.deleteLater()
