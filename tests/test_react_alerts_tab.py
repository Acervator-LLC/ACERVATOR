"""Drives `alerts_tab.js` against `alerts_tab_surface.py`.

WHAT IS PROVED
==============
The renderer module draws the Notifications and Alerts tab from the
`alerts_tab.state` payload and holds no value of its own: no colour, no
title, no button word and no action name. Each button asks the bridge on
the action the surface bound to it, read in the order the surface
published its buttons.

The bridge boundary is checked here too. `build_view_model` writes every
style sheet with Qt's alpha byte because a real widget paints from that
same dict; `view_model` publishes through `src.gui.color_alpha`, so the
share a browser reads leaves the surface and the renderer scales nothing.

FALSIFICATION
=============
Wrong if the page reported a press the module never made, when
`test_the_page_asks_no_action_before_a_press` would have nothing to say.
That control reads the dispatch list before any button is pressed and
requires it empty, and every press test requires it to grow.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.gui.color_alpha import css_alpha, rgba
from src.gui.main_tabs import alerts_tab_surface as surface
from src.gui.main_tabs import design_system_surface as dss
from src.gui.main_tabs import theme_engine_surface as tes
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    load_order,
    new_engine,
    runs_after,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "alerts_tab.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: MODULE_TAIL is the closing line a whole module file ends with.
MODULE_TAIL = "})(window);"

MODULE_READ_ATTEMPTS = 200
MODULE_READ_PAUSE_S = 0.01


def read_module() -> str:
    """Return MODULE_PATH text ending with MODULE_TAIL, retrying while not."""
    for _ in range(MODULE_READ_ATTEMPTS):
        found = MODULE_PATH.read_text(encoding="utf-8")
        if found.rstrip().endswith(MODULE_TAIL):
            return found
        time.sleep(MODULE_READ_PAUSE_S)
    raise AssertionError(MODULE_PATH.name + " never read back whole")


MODULE_SOURCE = read_module()
MODULE_LITERALS = js_literals(MODULE_SOURCE)

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 300
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2
VIEW_SIZE_PX = (1400, 900)
HOST_WIDTH_PX = 1200
HOST_HEIGHT_PX = 800

#: The bridge method the module asks on, not a value it paints.
NAMED_METHOD = surface.METHOD

#: Stamped when this file is read, so every message stays inside the run.
MESSAGE_STAMP = time.time()

MANAGER_SPEC: dict = {
    "config": {
        "telegram_configured": True,
        "sms_configured": False,
        "rules": {
            "trade_filled": {
                "priority": "high",
                "channels": ["IN_APP", "TELEGRAM"],
            },
            "risk_breach": {"priority": "critical", "channels": ["SOUND"]},
        },
    },
    "history": [
        {
            "timestamp": MESSAGE_STAMP,
            "priority": "critical",
            "title": "Drawdown",
            "message": "the ceiling was reached",
            "channels_sent": ["IN_APP"],
            "acknowledged": False,
        },
        {
            "timestamp": MESSAGE_STAMP,
            "priority": "low",
            "title": "Filled",
            "message": "a scrum completed",
            "channels_sent": ["IN_APP", "TELEGRAM"],
            "acknowledged": True,
        },
    ],
    "unread": 2,
}

#: The three fields the left pane lays out, in the order it lays them out.
FIELD_KEYS = ("token", "chat_id", "phone")

#: What the operator typed, one entry for each of FIELD_KEYS.
TYPED_FIELDS = ("a-bot-credential", "42", "+1234567890")

STATE_PARAMS: dict = {
    "empty": {"reset": True},
    "painted": {"reset": True, "manager": MANAGER_SPEC, "action": "refresh"},
    "typed": {
        "reset": True,
        "manager": MANAGER_SPEC,
        "fields": dict(zip(FIELD_KEYS, TYPED_FIELDS)),
        "action": "refresh",
    },
}
STATE_NAMES = tuple(sorted(STATE_PARAMS))

#: The three buttons, in the order the surface publishes them.
TEST_BUTTON_AT = 0
SAVE_BUTTON_AT = 1
ACK_BUTTON_AT = 2


def state_payload(name: str) -> dict:
    """The whole view model for one named state, as the bridge sends it."""
    return json.loads(
        json.dumps(surface.view_model(dict(STATE_PARAMS[name])), ensure_ascii=True)
    )


def walk_payload(node: Any, keys: set, values: set) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            walk_payload(value, keys, values)
        return
    if isinstance(node, list):
        for one in node:
            walk_payload(one, keys, values)
        return
    if isinstance(node, str):
        values.add(node)


def published() -> tuple:
    """Every key name and every string value, over every state."""
    keys: set = set()
    values: set = set()
    for name in STATE_NAMES:
        walk_payload(state_payload(name), keys, values)
    values.discard("")
    keys.discard("")
    return keys, values


def as_css(value: Any) -> set:
    """One token value in every spelling a style sheet could carry."""
    if isinstance(value, str):
        return {value}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {str(value)}
    return set()


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


PUBLISHED_KEYS, PUBLISHED_VALUES = published()

#: Every string that is both a key name and a painted value; the literal
#: scan cannot tell those two readings apart.
AMBIGUOUS = PUBLISHED_KEYS & PUBLISHED_VALUES

PAINTED_VALUES = PUBLISHED_VALUES - AMBIGUOUS - {NAMED_METHOD}
TOKEN_VALUES = token_values()


class JsRuntime(JsEngine):
    """A QJSEngine holding `alerts_tab.js` and a `window` global."""

    module_path = MODULE_PATH
    setter = "acervatorSetAlertsTab"

    def named(self, call: str, *args: Any) -> Any:
        """Call one module method with JSON arguments and read its answer."""
        self.bind_json("ARGS", list(args))
        return self.json(
            "acervatorAlertsTab." + call + ".apply(null, JSON.parse(ARGS))"
        )


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


# -- 1. the module holds what the surface published ---------------------


def test_the_module_publishes_the_bridge_method_the_surface_answers(js: JsRuntime):
    assert js.json("acervatorAlertsTab.method") == surface.METHOD


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_raises_no_fault_on_a_payload_the_surface_produced(
    js: JsRuntime, state: str
):
    report = js.push(state_payload(state))
    assert report["faults"] == [], f"{state}: {report['faults']}"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_module_holds_every_field_it_reads(js: JsRuntime, state: str):
    report = js.push(state_payload(state))
    assert report["held"]["fields"] == report["declared"]["fields"]
    assert report["held"]["nested"] == report["declared"]["nested"]


def test_the_fault_list_reports_a_field_the_payload_left_out(js: JsRuntime):
    payload = state_payload("painted")
    del payload["button_texts"]
    report = js.push(payload)
    assert {
        "where": None,
        "field": "button_texts",
        "fault": "missing",
        "detail": None,
    } in report["faults"]


def test_the_fault_list_reports_a_nested_field_the_payload_left_out(js: JsRuntime):
    payload = state_payload("painted")
    del payload["styles"]["group_box"]
    report = js.push(payload)
    assert {
        "where": "styles",
        "field": "group_box",
        "fault": "missing",
        "detail": None,
    } in report["faults"]


def test_the_module_refuses_a_payload_that_is_not_an_object(js: JsRuntime):
    report = js.push([])
    assert report["faults"] == [
        {"where": None, "field": None, "fault": "not-an-object", "detail": "object"}
    ]
    assert js.json("acervatorAlertsTab.isLoaded()") is False


def test_the_module_counts_the_rows_the_surface_filled(js: JsRuntime):
    payload = state_payload("painted")
    report = js.push(payload)
    assert report["held"]["rows"] == len(payload["rules_rows"]) + len(
        payload["history_rows"]
    )
    assert report["held"]["buttons"] == len(payload["button_names"])


def test_the_module_reads_each_action_off_the_button_the_surface_bound_it_to(
    js: JsRuntime,
):
    payload = state_payload("painted")
    js.push(payload)
    bound = list(payload["actions"].values())
    for index, action in enumerate(bound):
        assert js.named("actionFor", index) == action


# -- 2. the module writes no value of its own ---------------------------


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"alerts_tab.js holds colour literals: {found}"


def test_no_string_in_the_module_equals_a_value_the_tab_paints():
    written = sorted(set(MODULE_LITERALS["strings"]) & PAINTED_VALUES)
    assert not written, f"alerts_tab.js spells out tab values: {written}"


def test_no_string_in_the_module_equals_a_design_token_value():
    written = sorted(set(MODULE_LITERALS["strings"]) & TOKEN_VALUES)
    assert not written, f"alerts_tab.js spells out token values: {written}"


def test_the_module_names_none_of_the_actions_it_dispatches():
    written = sorted(set(MODULE_LITERALS["strings"]) & set(surface.ACTIONS.values()))
    assert not written, f"alerts_tab.js spells out its own actions: {written}"


def test_the_module_writes_the_bridge_method_once():
    assert MODULE_LITERALS["strings"].count(NAMED_METHOD) == 1


def test_the_module_writes_no_measurement_the_surface_owns():
    """Every number this file writes reaches a published list, not a screen.

    A bare scan cannot tell an index into a published list from a size the
    surface owns, so the sizes, limits and Qt enum values are named here
    and the module must write none of them.
    """
    payload = state_payload("painted")
    owned = {
        str(payload[name])
        for name in (
            "message_max_chars",
            "history_limit",
            "splitter_handle_width",
            "content_spacing",
            "alignment_value",
            "edit_triggers_default_value",
            "rules_column_count",
            "history_column_count",
        )
    }
    owned |= {str(one) for one in payload["splitter_sizes"]}
    written = sorted(set(MODULE_LITERALS["numbers"]) & owned)
    assert not written, f"alerts_tab.js spells out surface measurements: {written}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    assert not MODULE_LITERALS["slashes"], (
        f"alerts_tab.js holds a slash outside a comment: "
        f"{MODULE_LITERALS['slashes']}"
    )


# -- 3. the colour boundary --------------------------------------------


#: A Qt alpha byte, well above the share a browser reads.
BYTE_ALPHA = 200


def test_the_bridge_keeps_the_qt_byte_out_of_the_published_payload():
    """`view_model` publishes the share; `build_view_model` keeps the byte."""
    tinted = f"color: {rgba(surface.ds.WARNING, BYTE_ALPHA)};"
    surface.view_model({"reset": True})
    surface.TAB_MODEL.unread_style = tinted
    published_style = surface.view_model({})["unread_style"]
    qt_style = surface.build_view_model(surface.TAB_MODEL)["unread_style"]
    assert qt_style == tinted, (
        "the Qt side must keep the alpha byte it paints from, but it carries "
        f"{qt_style}"
    )
    assert published_style != qt_style, (
        "the bridge published the Qt byte, which a browser paints opaque: "
        f"{published_style}"
    )
    assert (
        str(css_alpha(BYTE_ALPHA)) in published_style
    ), f"the published share is not {css_alpha(BYTE_ALPHA)}: {published_style}"


def test_no_colour_the_alerts_tab_paints_carries_transparency_today():
    carried = sorted(
        value
        for value in PUBLISHED_VALUES
        if "rgba(" in value or (value.startswith("#") and len(value) > 7)
    )
    assert not carried, f"the alerts tab now publishes transparency: {carried}"


# -- 4. the page draws what the surface published -----------------------


PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = " + json.dumps(str(HOST_WIDTH_PX) + "px") + ";"
    "window.HOST.style.height = " + json.dumps(str(HOST_HEIGHT_PX) + "px") + ";"
    "document.body.appendChild(window.HOST);"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
    "  return found; };"
    "window.probeColour = function (value) {"
    "  var probe = document.createElement('div');"
    "  probe.style.color = value;"
    "  document.body.appendChild(probe);"
    "  var found = getComputedStyle(probe).color;"
    "  probe.remove();"
    "  return found; };"
    "window.partsOf = function (name) {"
    "  return Array.prototype.slice.call("
    "    window.HOST.querySelectorAll('[data-part=\"' + name + '\"]')); };"
)

WATCH_VIOLATIONS = (
    "window.VIOLATIONS = [];"
    "document.addEventListener('securitypolicyviolation', function (e) {"
    "  window.VIOLATIONS.push(e.violatedDirective + ' ' + e.blockedURI); });"
)


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self._view.resize(*VIEW_SIZE_PX)
        self.open_page()
        self.wait_for_module()
        self.js(WATCH_VIOLATIONS)
        self.js(PAGE_HELPERS)

    def open_page(self) -> None:
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
        for attempt in range(PAGE_ATTEMPTS):
            if attempt:
                self.open_page()
            for _ in range(READY_ROUNDS):
                if self.js("typeof window.acervatorSetAlertsTab") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the alerts tab module: readyState "
            + str(self.js("document.readyState"))
            + ", scripts "
            + str(self.js("document.scripts.length"))
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

    def draw(self, payload: dict) -> None:
        self.js("window.acervatorAlertsTab.forget();")
        self.js("window.PAYLOAD = " + json.dumps(payload) + ";")
        self.js("window.acervatorSetAlertsTab(window.PAYLOAD);")
        self.js("window.acervatorAlertsTab.renderTab(window.HOST, window.PAYLOAD);")

    def press(self, index: int) -> None:
        self.js(f"window.partsOf('alerts-button')[{index}].click();")

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


@pytest.mark.slow
def test_the_page_draws_one_tab_named_the_way_the_surface_names_it(browser: Browser):
    payload = state_payload("painted")
    browser.draw(payload)
    names = browser.parsed(
        "window.partsOf('alerts-tab').map(function (el) {"
        "  return el.getAttribute('aria-label'); })"
    )
    assert names == [payload["accessible_name"]]


@pytest.mark.slow
def test_the_page_draws_one_group_for_each_title_the_surface_published(
    browser: Browser,
):
    payload = state_payload("painted")
    browser.draw(payload)
    titles = browser.parsed(
        "window.partsOf('alerts-group-title').map(function (el) {"
        "  return el.textContent; })"
    )
    assert titles == payload["group_titles"]


@pytest.mark.slow
def test_the_page_draws_the_status_and_unread_lines_the_surface_wrote(
    browser: Browser,
):
    payload = state_payload("painted")
    browser.draw(payload)
    status = browser.parsed("window.partsOf('alerts-status')[0].textContent")
    unread = browser.parsed("window.partsOf('alerts-unread')[0].textContent")
    assert status == payload["status_text"]
    assert unread == payload["unread_text"]


@pytest.mark.slow
def test_the_page_paints_the_unread_line_the_colour_the_surface_published(
    browser: Browser,
):
    payload = state_payload("painted")
    browser.draw(payload)
    painted = browser.parsed(
        "window.readStyle(window.partsOf('alerts-unread')[0], ['color'])"
    )
    wanted = browser.js("window.probeColour(" + json.dumps(surface.ds.WARNING) + ")")
    assert payload["unread_style"] == surface.UNREAD_WARNING_STYLE
    assert painted["color"] == wanted, (
        f"the unread line paints {painted['color']} and the surface asked for "
        f"{wanted}"
    )


@pytest.mark.slow
def test_the_page_draws_the_three_fields_the_surface_labelled(browser: Browser):
    payload = state_payload("painted")
    browser.draw(payload)
    words = browser.parsed(
        "window.partsOf('alerts-field-label').map(function (el) {"
        "  return el.textContent; })"
    )
    hints = browser.parsed(
        "window.partsOf('alerts-field-input').map(function (el) {"
        "  return el.placeholder; })"
    )
    assert words == payload["row_labels"][: len(words)]
    assert hints == payload["placeholders"]


@pytest.mark.slow
def test_the_page_hides_only_the_field_the_surface_set_to_hide_its_text(
    browser: Browser,
):
    payload = state_payload("painted")
    browser.draw(payload)
    types = browser.parsed(
        "window.partsOf('alerts-field-input').map(function (el) {"
        "  return el.type; })"
    )
    hidden = payload["echo_modes"][1]
    wanted = [
        node["echo_mode"] == hidden
        for node in payload["widgets"]
        if "echo_mode" in node
    ]
    assert [one == "password" for one in types] == wanted
    assert any(wanted), "no field on this tab conceals what is typed into it"


@pytest.mark.slow
def test_the_page_shows_what_the_operator_typed_back_in_each_field(
    browser: Browser,
):
    payload = state_payload("typed")
    browser.draw(payload)
    written = browser.parsed(
        "window.partsOf('alerts-field-input').map(function (el) {"
        "  return el.value; })"
    )
    assert written == [payload[name] for name in FIELD_KEYS]
    assert written == list(TYPED_FIELDS), "the tab lost what was typed into it"


@pytest.mark.slow
def test_the_page_draws_the_three_buttons_the_surface_named(browser: Browser):
    payload = state_payload("painted")
    browser.draw(payload)
    words = browser.parsed(
        "window.partsOf('alerts-button').map(function (el) {"
        "  return el.textContent; })"
    )
    assert words == payload["button_texts"]


@pytest.mark.slow
def test_the_page_asks_no_action_before_a_press(browser: Browser):
    browser.draw(state_payload("painted"))
    assert browser.parsed("window.acervatorAlertsTab.calls()") == []


@pytest.mark.slow
@pytest.mark.parametrize("index", [TEST_BUTTON_AT, SAVE_BUTTON_AT, ACK_BUTTON_AT])
def test_a_press_asks_the_bridge_on_the_action_the_surface_bound(
    browser: Browser, index: int
):
    payload = state_payload("painted")
    browser.draw(payload)
    browser.press(index)
    made = browser.parsed("window.acervatorAlertsTab.calls()")
    assert made == [{"action": list(payload["actions"].values())[index]}]


@pytest.mark.slow
def test_the_page_draws_the_routing_table_the_surface_filled(browser: Browser):
    payload = state_payload("painted")
    browser.draw(payload)
    heads = browser.parsed(
        "Array.prototype.slice.call("
        "  window.HOST.querySelectorAll("
        '    \'[data-part="alerts-rules-table"] [data-part="alerts-head-cell"]\'))'
        "  .map(function (el) { return el.textContent; })"
    )
    cells = browser.parsed(
        "Array.prototype.slice.call("
        "  window.HOST.querySelectorAll("
        '    \'[data-part="alerts-rules-table"] [data-part="alerts-cell"]\'))'
        "  .map(function (el) { return el.textContent; })"
    )
    assert payload["rules_rows"], "the driven events reached no row"
    assert heads == payload["rules_columns"]
    assert cells == [cell["text"] for row in payload["rules_rows"] for cell in row]


@pytest.mark.slow
def test_the_page_draws_the_history_table_the_surface_filled(browser: Browser):
    payload = state_payload("painted")
    browser.draw(payload)
    cells = browser.parsed(
        "Array.prototype.slice.call("
        "  window.HOST.querySelectorAll("
        '    \'[data-part="alerts-history-table"] [data-part="alerts-cell"]\'))'
        "  .map(function (el) { return el.textContent; })"
    )
    assert payload["history_rows"], "the driven messages reached no row"
    assert cells == [cell["text"] for row in payload["history_rows"] for cell in row]


@pytest.mark.slow
def test_the_page_paints_a_priority_cell_the_colour_the_surface_gave_it(
    browser: Browser,
):
    payload = state_payload("painted")
    browser.draw(payload)
    column = payload["priority_column"]
    painted = browser.parsed(
        "window.readStyle("
        "  window.HOST.querySelectorAll("
        '    \'[data-part="alerts-history-table"] [data-part="alerts-row"]\')[1]'
        "    .querySelectorAll('[data-part=\"alerts-cell\"]')[" + str(column) + "],"
        "  ['color'])"
    )
    wanted_value = payload["history_rows"][0][column]["color"]
    wanted = browser.js("window.probeColour(" + json.dumps(wanted_value) + ")")
    assert painted["color"] == wanted, (
        f"the priority cell paints {painted['color']} for a colour of "
        f"{wanted_value}"
    )


@pytest.mark.slow
def test_the_page_leaves_the_empty_tab_with_no_row(browser: Browser):
    browser.draw(state_payload("empty"))
    assert browser.parsed("window.partsOf('alerts-cell').length") == 0
    assert browser.parsed("window.partsOf('alerts-button').length") == 3


@pytest.mark.slow
def test_the_page_breaks_no_content_security_rule_drawing_the_tab(browser: Browser):
    browser.draw(state_payload("painted"))
    assert browser.parsed("window.VIOLATIONS") == []


# -- 5. the renderer runs the module ------------------------------------


def test_the_manifest_names_the_module_after_the_helpers_it_calls():
    order = load_order()
    assert runs_after(
        order, MODULE_PATH.name, "shared_widgets.js", "header_strip.js"
    ), f"alerts_tab.js does not run after the helpers it calls: {order}"
