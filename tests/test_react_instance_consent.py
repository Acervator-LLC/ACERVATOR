"""instance_consent_dialog.js read back against instance_consent_surface, and the Qt dialog it stands beside.

The shipped Qt dialog is NOT replaced here. It is pinned: a test counts
the live Qt children the real dialog builds, so deleting one fails the
run. No test enters an event loop -- `exec()` blocks, and the dialog is
driven by pressing its buttons directly.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import instance_consent_surface as surface
from tests.fixtures.web_js_modules import (
    JsEngine,
    js_literals,
    new_engine,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "instance_consent_dialog.js"
HEADER_PATH = REPO_ROOT / "src" / "gui" / "web" / "header_strip.js"
MANIFEST_PATH = REPO_ROOT / "desktop" / "renderer" / "module_manifest.js"

#: MODULE_SOURCE is read at collection, before any test body writes the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}")
LONG_HEX = re.compile(r"#[0-9a-fA-F]{8}\b")

PLANTED_COLOUR = '\nvar planted = "#0b0b0b";\n'

DIALOG_SIZE = (640, 480)

#: One decision whose five lines are all different, so a swap would report.
DECISION = {
    "headline": "This fleet was last started somewhere else",
    "detail": "A different machine wrote the saved fleet four minutes ago.",
    "owner_line": "owner: workshop-desk, written 4 minutes ago",
    "this_machine_line": "this machine: kitchen-laptop",
    "consequence_line": "Starting 38 bots here trades a live exchange account.",
    "fleet_bot_count": 38,
    "consent_is_possible": True,
    "verdict": "foreign-owner",
}


def decision_object() -> SimpleNamespace:
    return SimpleNamespace(**DECISION)


def payload(**over: Any) -> dict:
    """One surface answer after the round trip through the bridge's JSON."""
    asked: dict = {"reset": True}
    asked.update(DECISION)
    asked.update(over)
    return json.loads(json.dumps(surface.view_model(asked), ensure_ascii=True))


@pytest.fixture()
def model() -> dict:
    return payload()


class JsRuntime(JsEngine):
    module_path = MODULE_PATH
    setter = "acervatorSetInstanceConsent"


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module in a fresh engine, with the style-sheet reader beside it."""
    assert qapp is not None
    engine = new_engine()
    engine.evaluate("var window = this;")
    loaded = engine.evaluate(HEADER_PATH.read_text(encoding="utf-8"), HEADER_PATH.name)
    assert not loaded.isError(), HEADER_PATH.name + " did not run: " + loaded.toString()
    return JsRuntime(engine, MODULE_SOURCE)


@pytest.fixture()
def loaded(js: JsRuntime, model: dict) -> JsRuntime:
    js.push(model)
    return js


def test_the_module_answers_the_bridge_method_the_surface_registers(js: JsRuntime):
    """The module would call a method the bridge does not route."""
    assert js.json("acervatorInstanceConsent.method") == surface.METHOD


def test_every_field_the_module_declares_is_one_the_surface_publishes(
    js: JsRuntime, model: dict
):
    """The module reads a field the surface never writes."""
    declared = set(js.json("acervatorInstanceConsent.declaredFields()"))
    assert declared, "the module declares no field, so the check proves nothing"
    missing = sorted(declared - set(model))
    assert (
        not missing
    ), f"the module reads fields the surface does not publish: {missing}"


def test_the_field_check_names_a_field_the_surface_dropped(js: JsRuntime, model: dict):
    """The check above compares two full sets, or means nothing."""
    declared = set(js.json("acervatorInstanceConsent.declaredFields()"))
    thinned = {name: value for name, value in model.items() if name != "skin"}
    assert sorted(declared - set(thinned)) == ["skin"]


def test_the_module_holds_the_buttons_the_surface_publishes(
    loaded: JsRuntime, model: dict
):
    """A button label, state or height drifted from the surface."""
    buttons = model["buttons"]
    assert set(buttons) == {"refuse", "consent"}, buttons
    assert loaded.json("acervatorInstanceConsent.buttons()") == buttons


def test_the_consent_button_carries_the_bot_count_the_decision_named(
    loaded: JsRuntime, model: dict
):
    """The operator must read the number he is authorising off the button itself."""
    assert model["button_bot_count"] == DECISION["fleet_bot_count"]
    assert str(DECISION["fleet_bot_count"]) in model["buttons"]["consent"]["text"]
    assert (
        loaded.json("acervatorInstanceConsent.botCount()")
        == DECISION["fleet_bot_count"]
    )


def test_the_module_names_no_fault_on_the_shipped_payload(loaded: JsRuntime):
    """The module read something the surface publishes as the wrong shape."""
    assert loaded.json("acervatorInstanceConsent.faults()") == []


def test_an_answer_that_is_not_the_refusal_is_named_as_an_unsafe_default(
    js: JsRuntime, model: dict
):
    """The empty fault list above is a reading, not a blind spot."""
    broken = json.loads(json.dumps(model))
    broken["closed_answer"] = True
    js.push(broken)
    faults = js.json("acervatorInstanceConsent.faults()")
    assert [one["field"] for one in faults] == ["closed_answer"], faults
    assert faults[0]["fault"] == "unsafe-default"


def test_a_button_with_no_label_is_named_as_a_fault(js: JsRuntime, model: dict):
    """A button the operator cannot read is not a button he can answer with."""
    broken = json.loads(json.dumps(model))
    broken["buttons"]["consent"]["text"] = None
    js.push(broken)
    faults = js.json("acervatorInstanceConsent.faults()")
    assert [one["where"] for one in faults] == ["consent"], faults


def test_the_module_reads_the_answer_the_surface_gives_and_decides_none(
    js: JsRuntime,
):
    """The answer belongs to the surface; the module only reads it back."""
    js.push(payload())
    assert js.json("acervatorInstanceConsent.answer()") is False
    js.push(payload(button="consent"))
    assert js.json("acervatorInstanceConsent.answer()") is True
    js.push(payload(reset=True, button="refuse"))
    assert js.json("acervatorInstanceConsent.answer()") is False


def test_a_closed_window_answers_no(js: JsRuntime):
    """Every way out that is not the ownership button leaves the fleet idle."""
    js.push(payload(closed=True))
    assert js.json("acervatorInstanceConsent.answer()") is False


def test_the_module_records_a_fault_when_the_bridge_is_absent(js: JsRuntime):
    """A page with no preload bridge must say so rather than answer for the operator."""
    js.run("acervatorLoadInstanceConsent({});")
    assert js.json("acervatorInstanceConsent.loadError()") is not None
    assert js.json("acervatorInstanceConsent.isLoaded()") is False


def test_a_press_re_sends_the_decision_the_dialog_was_raised_with(js: JsRuntime):
    """A button that dropped the facts would ask the surface about a blank decision."""
    js.bind_json("ASKED", DECISION)
    js.run("acervatorLoadInstanceConsent(JSON.parse(ASKED));")
    js.run("acervatorInstanceConsent.press('consent');")
    assert js.json("acervatorInstanceConsent.heldRequest()") == DECISION


# -- the skin, and which side reads which colour -----------------------


def test_the_module_paints_every_skin_role_from_the_published_channels(
    loaded: JsRuntime, model: dict
):
    """A colour the module invented would not follow the design tokens."""
    skin = model["skin"]
    assert skin, "the skin is empty, so the comparison proves nothing"
    for name, channels in skin.items():
        painted = loaded.json(
            f"acervatorInstanceConsent.colour(JSON.parse(PAYLOAD), '{name}')"
        )
        assert painted == "rgb(" + ",".join(str(one) for one in channels) + ")", name


def test_a_channel_swap_changes_the_colour_the_module_paints(
    loaded: JsRuntime, model: dict
):
    """The comparison above reads the channels, or a swap would pass."""
    swapped = json.loads(json.dumps(model))
    red, green, blue = swapped["skin"]["headline"]
    assert red != blue, "the fixture colour is symmetric, so a swap cannot report"
    swapped["skin"]["headline"] = [blue, green, red]
    loaded.bind_json("SWAPPED", swapped)
    assert loaded.json(
        "acervatorInstanceConsent.colour(JSON.parse(SWAPPED), 'headline')"
    ) != loaded.json("acervatorInstanceConsent.colour(JSON.parse(PAYLOAD), 'headline')")


def test_the_published_style_sheet_carries_no_eight_digit_hex(model: dict):
    """Qt reads eight digits as AARRGGBB and CSS as RRGGBBAA, so neither side guesses."""
    sheet = model["widget"]["style_sheet"]
    assert HEX_COLOUR.findall(sheet), "the sheet carries no colour at all"
    assert LONG_HEX.findall(sheet) == [], sheet


def test_the_published_style_sheet_carries_no_alpha_byte(model: dict):
    """Nothing in this dialog crosses to CSS with Qt's 0-255 alpha."""
    assert "rgba(" not in model["widget"]["style_sheet"]
    assert "rgba(" not in json.dumps(model)


def test_the_module_reads_one_named_block_of_the_style_sheet(
    loaded: JsRuntime, model: dict
):
    """Merging every block into one soup would paint the headline as body text."""
    headline = loaded.json(
        "acervatorInstanceConsent.styleFor("
        "JSON.parse(PAYLOAD).widget.style_sheet, 'headline')"
    )
    detail = loaded.json(
        "acervatorInstanceConsent.styleFor("
        "JSON.parse(PAYLOAD).widget.style_sheet, 'detail')"
    )
    assert headline, "the headline block reached no CSS property"
    assert headline["color"] != detail["color"], (headline, detail)


def test_every_declaration_the_style_sheet_carries_reaches_a_css_property(
    loaded: JsRuntime, model: dict
):
    """A Qt-only paint would be dropped without a word."""
    assert loaded.json("acervatorInstanceConsent.faults()") == []
    blocks = loaded.json(
        "acervatorInstanceConsent.blocks(JSON.parse(PAYLOAD).widget.style_sheet)"
    )
    assert len(blocks) > 1, blocks


# -- the module carries no value of its own ----------------------------


def test_the_module_writes_no_colour_of_its_own():
    """A colour written into the module is a colour the tokens cannot change."""
    assert HEX_COLOUR.findall(MODULE_SOURCE) == []


def test_the_colour_scan_reads_the_module_file_and_can_report():
    """The scan above is empty because the module is clean, not because it is blind."""
    original = MODULE_PATH.read_bytes()
    try:
        swap_module(MODULE_PATH, original + PLANTED_COLOUR.encode("utf-8"))
        assert HEX_COLOUR.findall(MODULE_PATH.read_text(encoding="utf-8")) == [
            "#0b0b0b"
        ]
    finally:
        swap_module(MODULE_PATH, original)
    assert MODULE_PATH.read_bytes() == original


def test_no_string_in_the_module_is_a_line_the_dialog_shows(model: dict):
    """A sentence written into the module would not follow the guard decision."""
    written = set(js_literals(MODULE_SOURCE)["strings"])
    shown = {
        model["headline_text"],
        model["detail_text"],
        model["owner_text"],
        model["this_machine_text"],
        model["consequence_text"],
        model["buttons"]["refuse"]["text"],
        model["buttons"]["consent"]["text"],
        model["widget"]["window_title"],
    }
    carried = sorted(written & shown)
    assert not carried, f"the module writes lines the surface owns: {carried}"


def test_the_string_scan_finds_a_planted_line(model: dict):
    """The scan above is empty because the module is clean, not because it is blind."""
    planted = MODULE_SOURCE + '\nvar planted = "' + model["headline_text"] + '";\n'
    assert model["headline_text"] in js_literals(planted)["strings"]
    assert model["headline_text"] not in js_literals(MODULE_SOURCE)["strings"]


def test_the_renderer_manifest_names_the_module():
    """A module the manifest leaves out never runs on the page."""
    from tools import sync_renderer_modules

    named = sync_renderer_modules.manifest_entries(
        MANIFEST_PATH.read_text(encoding="utf-8")
    )
    assert MODULE_PATH.name in named


# -- the module drawn by the real page ---------------------------------

INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"
JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100


class Page:
    """The renderer page, loaded from disk in the Chromium view the shell embeds."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open()
        self.wait_for_module()

    def open(self) -> None:
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

    def settle(self, milliseconds: int) -> None:
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        loop.exec()

    def wait_for_module(self) -> None:
        for _ in range(READY_ROUNDS):
            if self.js("typeof window.acervatorSetInstanceConsent") == "function":
                return
            self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the module: readyState "
            + str(self.js("document.readyState"))
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
        assert "v" in box, "the page never answered: " + script[:80]
        return box["v"]

    def parsed(self, expression: str) -> Any:
        found = self.js("JSON.stringify(" + expression + ")")
        assert isinstance(found, str), (
            "the page answered nothing for " + expression + "; it drew no such element"
        )
        return json.loads(found)

    def close(self) -> None:
        self._view.deleteLater()


@pytest.fixture()
def page(qapp, model: dict):
    """The page with the dialog drawn into a host node, or a skip with no Chromium."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    found = Page()
    found.js("window.PAYLOAD = " + json.dumps(json.dumps(model)) + ";")
    found.js(
        "window.HOST = document.createElement('div');"
        "document.body.appendChild(window.HOST);"
        "window.acervatorSetInstanceConsent(JSON.parse(window.PAYLOAD));"
        "window.acervatorInstanceConsent.renderDialog(window.HOST,"
        " JSON.parse(window.PAYLOAD));"
    )
    yield found
    found.close()


def test_the_page_draws_every_line_of_the_decision(page: Page, model: dict):
    """The module publishes components the page never actually drew."""
    drawn = page.parsed(
        "['headline', 'detail', 'consequence'].map(function (name) {"
        " return window.HOST.querySelector('[data-part=\"' + name + '\"]').textContent; })"
    )
    assert drawn == [
        model["headline_text"],
        model["detail_text"],
        model["consequence_text"],
    ], drawn


def test_the_page_draws_both_facts_inside_the_facts_frame(page: Page, model: dict):
    """The two machine names must be on screen together, or the comparison is a memory test."""
    drawn = page.parsed(
        "Array.prototype.map.call("
        'window.HOST.querySelectorAll(\'[data-part="facts"] [data-part="fact"]\'),'
        " function (one) { return one.textContent; })"
    )
    assert drawn == [model["owner_text"], model["this_machine_text"]], drawn


def test_the_page_paints_the_headline_the_colour_the_skin_names(
    page: Page, model: dict
):
    """The colour is read back computed off the element the page really built."""
    painted = page.js(
        "getComputedStyle(window.HOST.querySelector('[data-part=\"headline\"]')).color"
    )
    channels = model["skin"]["headline"]
    assert painted == "rgb(" + ", ".join(str(one) for one in channels) + ")", painted


def test_the_headline_and_the_body_are_drawn_in_different_colours(page: Page):
    """The reading above is the headline's own, not one colour on every line."""
    painted = page.parsed(
        "['headline', 'detail'].map(function (name) {"
        " return getComputedStyle(window.HOST.querySelector("
        "'[data-part=\"' + name + '\"]')).color; })"
    )
    assert painted[0] != painted[1], painted


def test_a_blocked_consent_button_is_drawn_disabled_and_says_why(qapp):
    """The dialog never offers a choice it would refuse to honour."""
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    blocked = payload(consent_is_possible=False)
    found = Page()
    try:
        found.js("window.PAYLOAD = " + json.dumps(json.dumps(blocked)) + ";")
        found.js(
            "window.HOST = document.createElement('div');"
            "document.body.appendChild(window.HOST);"
            "window.acervatorInstanceConsent.renderDialog(window.HOST,"
            " JSON.parse(window.PAYLOAD));"
        )
        drawn = found.parsed(
            "(function () {"
            " var one = window.HOST.querySelector('[data-name=\"consent\"]');"
            " return [one.disabled, one.title]; })()"
        )
    finally:
        found.close()
    assert drawn == [True, blocked["buttons"]["consent"]["tool_tip"]], drawn
    assert blocked["buttons"]["consent"][
        "tool_tip"
    ], "the blocked button gives no reason"


def test_the_consent_button_is_drawn_reachable_when_consent_is_possible(page: Page):
    """The disabled reading above is a state, not the only state."""
    assert (
        page.parsed("window.HOST.querySelector('[data-name=\"consent\"]').disabled")
        is False
    )


# -- the Qt dialog is preserved, and counted ---------------------------


def qt_dialog():
    """The shipped Qt dialog, built from one decision. Never shown, never exec'd."""
    from tests.qt_pixel import ensure_app

    ensure_app()
    from src.gui import instance_consent_dialog as shipped

    return shipped.InstanceConsentDialog(decision_object())


def live_children(widget) -> dict:
    """Every live Qt child of `widget`, counted by the Qt class it is."""
    from PySide6.QtWidgets import QWidget

    found: dict = {}
    for child in widget.findChildren(QWidget):
        for owner in type(child).__mro__:
            if owner.__name__.startswith("Q"):
                found[owner.__name__] = found.get(owner.__name__, 0) + 1
                break
    return found


#: MEASURED off the shipped dialog: five labels, the facts frame, two buttons.
SHIPPED_CHILDREN = {"QLabel": 5, "QFrame": 1, "QPushButton": 2}


def test_the_shipped_dialog_still_builds_every_qt_child_it_shipped_with():
    """A Qt widget was deleted before its React replacement was verified."""
    dialog = qt_dialog()
    counted = live_children(dialog)
    held = {name: counted.get(name, 0) for name in SHIPPED_CHILDREN}
    assert held == SHIPPED_CHILDREN, counted


def test_the_child_counter_reports_a_widget_that_is_not_there():
    """The count above is a pin because the counter can come up short."""
    from PySide6.QtWidgets import QWidget

    from tests.qt_pixel import ensure_app

    ensure_app()
    assert live_children(QWidget()) == {}
    assert live_children(qt_dialog()) != {}


def test_the_refuse_button_answers_no_without_entering_an_event_loop():
    """`exec()` blocks; the answer is read by pressing the button directly."""
    dialog = qt_dialog()
    dialog._refuse_button.click()
    assert dialog.consented is False


def test_the_consent_button_is_the_only_way_to_a_yes():
    """The refusal above is a reading, not a dialog that can only say no."""
    dialog = qt_dialog()
    dialog._consent_button.click()
    assert dialog.consented is True


def test_the_dialog_paints_the_surface_background_colour():
    """Read off the composited pixels, never off a style sheet."""
    from PySide6.QtCore import QPoint

    from tests.qt_pixel import pixel_at, render_widget

    dialog = qt_dialog()
    image = render_widget(dialog, size=DIALOG_SIZE)
    painted = pixel_at(image, QPoint(DIALOG_SIZE[0] - 4, DIALOG_SIZE[1] - 4))
    wanted = "#" + "".join(f"{one:02x}" for one in surface.rgb(surface.SKIN["surface"]))
    assert painted == wanted, f"the dialog painted {painted}, not {wanted}"


def test_the_background_pixel_check_reports_a_different_skin():
    """The pixel above is the surface token, and another token reads apart."""
    from PySide6.QtCore import QPoint

    from tests.qt_pixel import pixel_at, render_widget

    dialog = qt_dialog()
    image = render_widget(dialog, size=DIALOG_SIZE)
    painted = pixel_at(image, QPoint(DIALOG_SIZE[0] - 4, DIALOG_SIZE[1] - 4))
    other = "#" + "".join(
        f"{one:02x}" for one in surface.rgb(surface.SKIN["facts_surface"])
    )
    assert painted != other, "two skin tokens read the same, so the pixel cannot report"


def test_the_channels_the_renderer_paints_are_the_channels_qt_paints(model: dict):
    """One colour, two readings: the renderer's triple and the widget's token."""
    for name, token in surface.SKIN.items():
        assert model["skin"][name] == list(surface.rgb(token)), name
