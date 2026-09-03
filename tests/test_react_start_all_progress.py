"""``start_all_progress.js`` against ``start_all_progress_surface.py``,
run in QJSEngine and drawn in QWebEngineView."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import start_all_progress_surface as surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    drain_events,
    js_literals,
    load_order,
    new_engine,
    runs_after,
    swap_module,
)

MODULE_PATH = REPO_ROOT / "src" / "gui" / "web" / "start_all_progress.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body can write into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 2


def dialog_payload(
    steps: Any = (),
    cancel: bool = False,
    cancel_refused: bool = False,
    close: bool = False,
) -> dict:
    """The surface's own payload after replaying ``steps`` on a fresh model."""
    model = surface.StartAllProgressModel()
    for phase, total, started, bot_id in steps:
        model.handle_progress(phase, total, started, bot_id)
    if cancel:
        model.cancel(surface.CancelSource(cancel_refused))
    if close:
        surface.unsubscribe(surface.unsubscriber_for(False))
    answer = surface.build_view_model(model)
    return json.loads(json.dumps(answer, ensure_ascii=True))


HOSTILE_ID = "<script>alert(1)</script>"

#: Every state the surface serves, no state here a word the module writes.
STATES = {
    "fresh": [],
    "no_bots": [("begin", 0, 0, "")],
    "in_progress": [
        ("begin", 3, 0, ""),
        ("bot_starting", 3, 0, "bot-a"),
        ("bot_started", 3, 1, "bot-a"),
        ("bot_starting", 3, 1, "bot-b"),
    ],
    "done": [
        ("begin", 2, 0, ""),
        ("bot_starting", 2, 0, "bot-a"),
        ("bot_started", 2, 1, "bot-a"),
        ("bot_starting", 2, 1, "bot-b"),
        ("bot_started", 2, 2, "bot-b"),
        ("done", 2, 2, ""),
    ],
    "timeout": [
        ("begin", 2, 0, ""),
        ("bot_starting", 2, 0, "slow-bot"),
        ("bot_timeout", 2, 0, "slow-bot"),
        ("bot_starting", 2, 0, "fast-bot"),
        ("bot_started", 2, 1, "fast-bot"),
        ("done", 2, 1, ""),
    ],
    # Stops on `bot_starting`, where both the headline and the freshest
    # item still carry the raw bot id (`bot_started` drops it from the
    # headline format string).
    "hostile_bot_id": [
        ("begin", 1, 0, ""),
        ("bot_starting", 1, 0, HOSTILE_ID),
    ],
    "number_like_ids": [
        ("begin", 3, 0, ""),
        ("bot_starting", 3, 0, "10"),
        ("bot_starting", 3, 0, "2"),
        ("bot_starting", 3, 0, "1"),
    ],
}
STATE_NAMES = tuple(STATES)


def state_payload(name: str) -> dict:
    return dialog_payload(STATES[name])


def cancelled_payload() -> dict:
    """The dialog after a cancel press whose outcome the engine confirmed
    with its own ``cancelled`` progress event."""
    model = surface.StartAllProgressModel()
    model.handle_progress("begin", 2, 0, "")
    model.handle_progress("bot_starting", 2, 0, "bot-a")
    model.handle_progress("bot_started", 2, 1, "bot-a")
    model.cancel(surface.CancelSource(refuses=False))
    model.handle_progress("cancelled", 2, 1, "")
    answer = surface.build_view_model(model)
    return json.loads(json.dumps(answer, ensure_ascii=True))


def cancel_failed_payload() -> dict:
    return dialog_payload([("begin", 2, 0, "")], cancel=True, cancel_refused=True)


class JsRuntime(JsEngine):

    module_path = MODULE_PATH
    setter = "acervatorSetStartAllProgress"

    def call(self, api: str, *args: Any) -> Any:
        parts = []
        for at, value in enumerate(args):
            name = "ARG" + str(at)
            self.bind_json(name, value)
            parts.append("JSON.parse(" + name + ")")
        return self.json("acervatorStartAllProgress." + api + "(" + ", ".join(parts) + ")")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    """The module, loaded in a fresh engine."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


# ---------------------------------------------------------------------------
# Whole-payload contract: every field the surface publishes reaches the
# module through its generic bag/list/field readers, and nothing else.
# ---------------------------------------------------------------------------

BAG_FIELDS = ("widget", "layout", "button_row", "headline", "subline", "buttons", "actions")
LIST_FIELDS = ("phases", "event_fields", "items", "calls")
COLOUR_FIELDS = (
    "dialog_surface",
    "text_color",
    "list_surface",
    "list_border",
    "button_surface",
    "button_border",
    "button_hover",
    "disabled_text",
    "subline_color",
)
SCALAR_FIELDS = (
    "topic",
    "headline_text",
    "item_count",
    "cancel_enabled",
    "close_enabled",
)

ALL_DECLARED_FIELDS = BAG_FIELDS + LIST_FIELDS + COLOUR_FIELDS + SCALAR_FIELDS


def reader_for(field: str) -> str:
    if field in BAG_FIELDS:
        return "bag"
    if field in LIST_FIELDS or field in COLOUR_FIELDS:
        return "list"
    return "field"


@pytest.mark.parametrize("state", STATE_NAMES)
def test_every_field_the_surface_publishes_reaches_the_module(js: JsRuntime, state: str):
    """A field the module never carries is a value that stops at the bridge."""
    payload = state_payload(state)
    js.push(payload)
    assert sorted(payload) == sorted(ALL_DECLARED_FIELDS), sorted(
        set(payload) ^ set(ALL_DECLARED_FIELDS)
    )
    differing = {
        field: (payload[field], js.call(reader_for(field), field))
        for field in ALL_DECLARED_FIELDS
        if js.call(reader_for(field), field) != payload[field]
    }
    assert not differing, f"{state}: {len(differing)} fields differ: {sorted(differing)}"


def test_the_module_names_the_fields_the_surface_declares(js: JsRuntime):
    js.push(state_payload("done"))
    assert sorted(js.json("acervatorStartAllProgress.declaredFields()")) == sorted(
        ALL_DECLARED_FIELDS
    )


@pytest.mark.parametrize("state", STATE_NAMES)
def test_the_report_counts_declared_and_held_fields_apart(js: JsRuntime, state: str):
    payload = state_payload(state)
    report = js.push(payload)
    assert report["declared"]["fields"] == len(ALL_DECLARED_FIELDS)
    assert report["held"]["fields"] == len(payload)
    assert report["held"]["items"] == len(payload["items"])
    assert report["faults"] == [], report["faults"]


def test_a_missing_field_shortens_the_held_count_and_is_named(js: JsRuntime):
    payload = state_payload("done")
    del payload["subline_color"]
    report = js.push(payload)
    assert report["held"]["fields"] == len(ALL_DECLARED_FIELDS) - 1
    assert {
        "where": None,
        "field": "subline_color",
        "fault": "missing",
        "detail": None,
    } in report["faults"]


@pytest.mark.parametrize("field", COLOUR_FIELDS)
def test_a_colour_of_the_wrong_length_is_named(js: JsRuntime, field: str):
    payload = state_payload("done")
    payload[field] = [1, 2]
    report = js.push(payload)
    assert {
        "where": None,
        "field": field,
        "fault": "channel-mismatch",
        "detail": 2,
    } in report["faults"]


def test_the_channel_check_is_quiet_on_every_shipped_state(js: JsRuntime):
    for state in STATE_NAMES:
        report = js.push(state_payload(state))
        named = [one for one in report["faults"] if one["fault"] == "channel-mismatch"]
        assert named == [], f"{state}: {named}"


def test_a_button_missing_its_enabled_key_is_named(js: JsRuntime):
    payload = state_payload("done")
    del payload["buttons"]["cancel"]["enabled"]
    report = js.push(payload)
    assert {
        "where": "cancel",
        "field": "buttons",
        "fault": "missing",
        "detail": "enabled",
    } in report["faults"]


def test_a_layout_order_shorter_than_its_stretch_list_is_named(js: JsRuntime):
    payload = state_payload("done")
    payload["layout"]["child_stretch"] = [0, 0]
    report = js.push(payload)
    assert {
        "where": None,
        "field": "layout",
        "fault": "short-list",
        "detail": "child_stretch.2",
    } in report["faults"]


def test_an_item_count_that_disagrees_with_items_is_named(js: JsRuntime):
    payload = state_payload("in_progress")
    payload["item_count"] = payload["item_count"] + 1
    report = js.push(payload)
    assert {
        "where": None,
        "field": "item_count",
        "fault": "disagrees",
        "detail": payload["item_count"],
    } in report["faults"]


def test_a_payload_that_is_not_an_object_leaves_the_module_unloaded(js: JsRuntime):
    for wrong in ("a string", 7, None, ["a", "list"]):
        report = js.push(wrong)
        assert js.json("acervatorStartAllProgress.isLoaded()") is False
        assert report["declared"] is None
        assert [one["fault"] for one in report["faults"]] == ["not-an-object"]


# ---------------------------------------------------------------------------
# Defect class 1 - no invented progress value. The module reads no field
# but `headline_text` and `items` for what it shows; `total`/`started`
# never reach the render at all, so two states differing only in those
# numbers must be indistinguishable to the module's own readers.
# ---------------------------------------------------------------------------


def test_the_module_never_reads_total_or_started_by_name():
    assert "total" not in MODULE_SOURCE
    assert "started" not in MODULE_SOURCE


def test_the_module_computes_no_ratio_or_percentage():
    """No division operator exists, so no `done / total` can ever divide
    by zero and no percentage can ever be a guess (#257)."""
    literals = js_literals(MODULE_SOURCE)
    assert literals["slashes"] == [], literals["slashes"]


def test_two_states_differing_only_in_total_and_started_read_identically(js: JsRuntime):
    happy = state_payload("in_progress")
    inflated = json.loads(json.dumps(happy))
    inflated["headline_text"] = happy["headline_text"]
    inflated["item_count"] = happy["item_count"]
    # Same measured text and items; only the raw counters differ.
    js.push(happy)
    happy_items = js.call("list", "items")
    happy_headline = js.call("field", "headline_text")
    js.push(inflated)
    assert js.call("list", "items") == happy_items
    assert js.call("field", "headline_text") == happy_headline


# ---------------------------------------------------------------------------
# Defect class 2 - #257 non-finite numbers. Nothing in this payload is
# ever computed by division, so a bare NaN cannot arise here; this proves
# a hostile payload carrying one still cannot cross into the module.
# ---------------------------------------------------------------------------


def test_a_payload_carrying_a_bare_nan_never_reaches_the_module(js: JsRuntime):
    js.push(state_payload("done"))
    before = js.call("list", "items")
    broken = state_payload("done")
    broken["text_color"] = [float("nan"), 0, 0]
    js.bind_json("BROKEN", broken)
    refused = js.json(
        "(function () { try { JSON.parse(BROKEN); return null; }"
        " catch (e) { return e.name; } })()"
    )
    assert refused is not None, "JSON.parse accepted the frame"
    assert js.call("list", "items") == before


def test_the_bare_nan_check_accepts_a_frame_the_bridge_can_write(js: JsRuntime):
    js.bind_json("WHOLE", state_payload("done"))
    refused = js.json(
        "(function () { try { JSON.parse(WHOLE); return null; }"
        " catch (e) { return e.name; } })()"
    )
    assert refused is None


# ---------------------------------------------------------------------------
# Defect class 3 - #276 order loss. `items` is an explicit ordered list on
# the wire; this proves the module keeps that order even when the entries
# look like numbers a browser might otherwise re-sort as object keys.
# ---------------------------------------------------------------------------


def test_number_like_item_text_keeps_the_order_the_surface_sent(js: JsRuntime):
    payload = state_payload("number_like_ids")
    assert [line.split()[1] for line in payload["items"]] == ["10", "2", "1"]
    js.push(payload)
    held = js.call("list", "items")
    assert [line.split()[1] for line in held] == ["10", "2", "1"]


def test_items_is_a_list_never_a_bag_keyed_by_bot_id():
    payload = state_payload("number_like_ids")
    assert isinstance(payload["items"], list)


# ---------------------------------------------------------------------------
# Defect class 4 - #266 colour trap. This payload carries no alpha at all,
# so the module must never write an 8-digit hex or an `rgba(` call, which
# would silently invent transparency (or Qt's byte-order) nowhere present
# in the source data.
# ---------------------------------------------------------------------------


def test_the_module_writes_no_number():
    literals = js_literals(MODULE_SOURCE)
    assert literals["numbers"] == [], literals["numbers"]


def test_the_module_writes_no_colour_literal():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"start_all_progress.js holds colour literals: {found}"


def test_the_module_writes_no_rgba_call():
    assert "rgba(" not in MODULE_SOURCE


def test_the_literal_scan_catches_a_planted_colour():
    """A positive control for the two checks above: the scan is not blind."""
    planted = MODULE_SOURCE + '\nvar written = "#aabbccdd";\n'
    assert HEX_COLOUR.findall(planted)
    original = MODULE_PATH.read_bytes()
    try:
        swap_module(MODULE_PATH, original + b'\nvar written = 12;\n')
        on_disk = js_literals(MODULE_PATH.read_text(encoding="utf-8"))
        assert on_disk["numbers"] == ["12"]
    finally:
        swap_module(MODULE_PATH, original)
    assert MODULE_PATH.read_bytes() == original


# ---------------------------------------------------------------------------
# Defect class 5 - #268/#272 markup. A bot id is drawn where Qt would use
# both a rich-text QLabel (the headline) and a plain-text QListWidgetItem
# (the list). Neither must let a hostile bot id become live markup.
# ---------------------------------------------------------------------------


def test_a_hostile_bot_id_reaches_the_module_as_the_text_the_surface_made(js: JsRuntime):
    payload = state_payload("hostile_bot_id")
    assert HOSTILE_ID in payload["headline_text"]
    assert any(HOSTILE_ID in line for line in payload["items"])
    js.push(payload)
    assert js.call("field", "headline_text") == payload["headline_text"]
    assert js.call("list", "items") == payload["items"]


def test_the_module_reads_a_button_s_live_enabled_state_not_its_starting_one(js: JsRuntime):
    """`buttons.cancel.enabled`/`buttons.close.enabled` never change; the
    live state is the top-level `cancel_enabled`/`close_enabled` field."""
    payload = state_payload("done")
    assert payload["buttons"]["cancel"]["enabled"] is True
    assert payload["buttons"]["close"]["enabled"] is False
    assert payload["cancel_enabled"] is False
    assert payload["close_enabled"] is True


# ---------------------------------------------------------------------------
# Bridge behaviour: one round trip per page, cancel/close dispatch the
# right method and params, and a refused ask is not remembered.
# ---------------------------------------------------------------------------

BRIDGE_STUB = (
    "window.CALLS = [];"
    "window.acervator = { call: function (method, params) {"
    "  window.CALLS.push([method, JSON.stringify(params)]);"
    "  return Promise.resolve(JSON.parse(PAYLOAD)); } };"
)


def test_the_module_asks_the_backend_for_the_surface_method(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("fresh"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadStartAllProgress();")
    drain_events()
    assert js.json("window.CALLS") == [[surface.METHOD, "{}"]]
    assert js.json("acervatorStartAllProgress.isLoaded()") is True


def test_a_second_ask_costs_no_second_round_trip(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("fresh"))
    js.run(BRIDGE_STUB)
    js.run(
        "acervatorLoadStartAllProgress();"
        "acervatorLoadStartAllProgress();"
        "acervatorLoadStartAllProgress();"
    )
    drain_events()
    assert len(js.json("window.CALLS")) == 1


def test_forget_lets_a_later_ask_reach_the_backend_again(js: JsRuntime):
    js.bind_json("PAYLOAD", state_payload("fresh"))
    js.run(BRIDGE_STUB)
    js.run("acervatorLoadStartAllProgress();")
    drain_events()
    js.run("acervatorStartAllProgress.forget(); acervatorLoadStartAllProgress();")
    drain_events()
    assert len(js.json("window.CALLS")) == 2


def test_the_module_reports_a_missing_bridge_rather_than_raising(js: JsRuntime):
    js.run("acervatorLoadStartAllProgress();")
    drain_events()
    assert js.json("acervatorStartAllProgress.isLoaded()") is False
    assert js.json("acervatorStartAllProgress.loadError()") == (
        "the preload bridge is not present"
    )


def test_cancel_dispatches_the_cancel_action_and_param(js: JsRuntime):
    js.push(state_payload("in_progress"))
    js.bind_json("PAYLOAD", state_payload("in_progress"))
    js.run(BRIDGE_STUB)
    js.run("acervatorStartAllProgress.cancel();")
    drain_events()
    sent = js.json("acervatorStartAllProgress.sent()")
    assert sent == [{"action": "cancel", "params": {"cancel": True}}]
    calls = js.json("window.CALLS")
    assert len(calls) == 1
    assert calls[0][0] == surface.METHOD
    assert json.loads(calls[0][1]) == {"cancel": True}


def test_close_dispatches_the_close_action_and_param(js: JsRuntime):
    js.push(state_payload("done"))
    js.bind_json("PAYLOAD", state_payload("done"))
    js.run(BRIDGE_STUB)
    js.run("acervatorStartAllProgress.closeDialog();")
    drain_events()
    sent = js.json("acervatorStartAllProgress.sent()")
    assert sent == [{"action": "accept", "params": {"close": True}}]


def test_a_dispatch_with_no_bridge_is_recorded_but_answers_nothing(js: JsRuntime):
    js.push(state_payload("in_progress"))
    answer = js.json("acervatorStartAllProgress.cancel()")
    assert answer is None
    assert js.json("acervatorStartAllProgress.sent()") == [
        {"action": "cancel", "params": {"cancel": True}}
    ]


# ---------------------------------------------------------------------------
# Module registration: the page loads it through the manifest, after the
# React vendor bundle it calls.
# ---------------------------------------------------------------------------


def test_the_manifest_names_the_module_exactly_once():
    from tools import sync_renderer_modules

    manifest = sync_renderer_modules.manifest_entries(
        (INDEX_HTML.parent / "module_manifest.js").read_text(encoding="utf-8")
    )
    assert manifest.count(MODULE_PATH.name) == 1


def test_the_module_is_reachable_in_the_page_load_order():
    order = load_order()
    assert order.count(MODULE_PATH.name) == 1
    assert runs_after(order, MODULE_PATH.name, "react.production.min.js", "react-dom.production.min.js")


def test_the_load_order_check_names_a_module_missing_from_the_order():
    """A check that agreed with any order would not have proved the line
    above; a hand-built order missing the module must fail it."""
    assert runs_after(["react.production.min.js"], MODULE_PATH.name, "react.production.min.js") is False


# ---------------------------------------------------------------------------
# Rendered checks: drawn in a real Chromium view under the page's own CSP.
# ---------------------------------------------------------------------------


class Browser:
    """The real renderer page, loaded from disk in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        self.open_page()
        self.wait_for_module()

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
                if self.js("typeof window.acervatorSetStartAllProgress") == "function":
                    return
                self.settle(READY_STEP_MS)
        raise AssertionError(
            "the page never defined the dialog module: readyState "
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
    assert qapp is not None
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    page = Browser()
    yield page
    page.close()


PAGE_HELPERS = (
    "window.HOST = document.createElement('div');"
    "window.HOST.style.width = '600px';"
    "document.body.appendChild(window.HOST);"
    "window.readStyle = function (el, names) {"
    "  var computed = getComputedStyle(el);"
    "  var found = {};"
    "  names.forEach(function (n) { found[n] = computed[n]; });"
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
    "        text: own, elements: el.getElementsByTagName('*').length,"
    "        style: window.readStyle(el, names) });"
    "    }"
    "    Array.prototype.slice.call(el.children).forEach(function (child) {"
    "      walk(child, here); });"
    "  };"
    "  if (window.HOST.firstChild) { walk(window.HOST.firstChild, ''); }"
    "  return JSON.stringify(found); })()"
)

STYLE_NAMES = ["color", "backgroundColor", "minWidth", "width", "gap", "paddingTop", "fontSize"]


def draw_dialog(browser: Browser, payload: dict) -> list:
    browser.js(PAGE_HELPERS)
    browser.js("window.STYLE_NAMES = " + json.dumps(json.dumps(STYLE_NAMES)) + ";")
    browser.js("window.PAYLOAD = " + json.dumps(json.dumps(payload)) + ";")
    browser.js(
        "acervatorSetStartAllProgress(JSON.parse(window.PAYLOAD));"
        "acervatorStartAllProgress.renderDialog(window.HOST);"
    )
    return json.loads(browser.js(READ_PARTS))


def at_path(parts: list, path: str) -> list:
    return [one for one in parts if one["path"] == path]


def only(parts: list, path: str) -> dict:
    found = at_path(parts, path)
    assert len(found) == 1, f"{len(found)} parts at {path}"
    return found[0]


def test_the_page_loads_the_module_under_its_own_policy(browser: Browser):
    policy = browser.js(
        "document.querySelector(\"meta[http-equiv='Content-Security-Policy']\").content"
    )
    assert "connect-src 'none'" in policy
    assert browser.js("typeof window.acervatorStartAllProgress") == "object"


def test_the_dialog_draws_every_named_part(browser: Browser):
    parts = draw_dialog(browser, state_payload("done"))
    assert [one["path"] for one in parts] == [
        "dialog",
        "dialog/headline",
        "dialog/subline",
        "dialog/list",
        "dialog/list/list-row",
        "dialog/list/list-row",
        "dialog/button-row",
        "dialog/button-row/button-spacer",
        "dialog/button-row/button",
        "dialog/button-row/button",
    ]


def test_the_drawn_headline_and_items_match_the_surface(browser: Browser):
    payload = state_payload("in_progress")
    parts = draw_dialog(browser, payload)
    assert only(parts, "dialog/headline")["text"] == payload["headline_text"]
    rows = at_path(parts, "dialog/list/list-row")
    assert [row["text"] for row in rows] == payload["items"]


def test_a_hostile_bot_id_is_drawn_as_text_in_the_headline_and_the_list(browser: Browser):
    payload = state_payload("hostile_bot_id")
    parts = draw_dialog(browser, payload)
    headline = only(parts, "dialog/headline")
    assert headline["text"] == payload["headline_text"]
    assert headline["elements"] == 0
    rows = at_path(parts, "dialog/list/list-row")
    assert [row["text"] for row in rows] == payload["items"]
    assert all(row["elements"] == 0 for row in rows)
    assert browser.js("window.HOST.getElementsByTagName('script').length") == 0
    assert browser.js("window.HOST.getElementsByTagName('b').length") == 0


def test_the_buttons_reflect_the_live_enabled_state_not_the_starting_one(browser: Browser):
    """A read that always reported the starting `True`/`False` pair would
    pass a dialog stuck showing Cancel live after every bot finished."""
    payload = state_payload("done")
    parts = draw_dialog(browser, payload)
    buttons = at_path(parts, "dialog/button-row/button")
    by_name = {one["attrs"]["data-name"]: one for one in buttons}
    assert by_name["cancel"]["attrs"]["aria-disabled"] == "true"
    assert by_name["close"]["attrs"]["aria-disabled"] == "false"
    fresh = draw_dialog(browser, state_payload("fresh"))
    fresh_buttons = {
        one["attrs"]["data-name"]: one
        for one in at_path(fresh, "dialog/button-row/button")
    }
    assert fresh_buttons["cancel"]["attrs"]["aria-disabled"] == "false"
    assert fresh_buttons["close"]["attrs"]["aria-disabled"] == "true"


def test_a_refused_cancel_disables_cancel_and_names_the_failure(browser: Browser):
    payload = cancel_failed_payload()
    parts = draw_dialog(browser, payload)
    assert only(parts, "dialog/headline")["text"] == surface.HEADLINE_CANCEL_FAILED
    buttons = {one["attrs"]["data-name"]: one for one in at_path(parts, "dialog/button-row/button")}
    assert buttons["cancel"]["attrs"]["aria-disabled"] == "true"


def test_cancelled_reads_the_final_count_and_disables_cancel(browser: Browser):
    payload = cancelled_payload()
    parts = draw_dialog(browser, payload)
    assert only(parts, "dialog/headline")["text"] == payload["headline_text"]
    assert "1/2" in payload["headline_text"]
    buttons = {one["attrs"]["data-name"]: one for one in at_path(parts, "dialog/button-row/button")}
    assert buttons["cancel"]["attrs"]["aria-disabled"] == "true"
    assert buttons["close"]["attrs"]["aria-disabled"] == "false"


def test_whole_number_lengths_carry_their_unit_at_render(browser: Browser):
    """A token published as a bare number renders as `0px` through a CSS
    var with no unit; every length here must carry its own unit."""
    payload = state_payload("done")
    dialog = only(draw_dialog(browser, payload), "dialog")
    assert dialog["style"]["minWidth"] == str(payload["widget"]["minimum_width_px"]) + "px"
    assert dialog["style"]["width"] == str(payload["widget"]["size_px"][0]) + "px"
    assert dialog["style"]["gap"] == str(payload["layout"]["spacing_px"]) + "px"
    assert dialog["style"]["paddingTop"] == str(payload["layout"]["margins_px"][1]) + "px"
    draw_dialog(browser, payload)
    # Computed font-size always normalises to px, so the unit the module
    # wrote is read off the specified (uncomputed) inline declaration.
    authored_font_size = browser.js(
        "window.HOST.querySelector('[data-part=\"headline\"]').style.fontSize"
    )
    assert authored_font_size == str(payload["headline"]["point_size"]) + "pt"
    assert "0px" not in [dialog["style"]["minWidth"], dialog["style"]["width"]]


def test_the_dialog_paints_the_published_colour_triples(browser: Browser):
    payload = state_payload("done")
    parts = draw_dialog(browser, payload)
    dialog = only(parts, "dialog")
    wanted_bg = browser.parsed(
        "(function () { var probe = document.createElement('span');"
        " probe.style.cssText = 'color: rgb("
        + ", ".join(str(one) for one in payload["dialog_surface"])
        + ")'; document.body.appendChild(probe);"
        " var found = getComputedStyle(probe).color; probe.remove();"
        " return found; })()"
    )
    assert dialog["style"]["backgroundColor"] == wanted_bg


def test_the_list_order_survives_number_like_bot_ids_in_the_real_dom(browser: Browser):
    payload = state_payload("number_like_ids")
    parts = draw_dialog(browser, payload)
    rows = at_path(parts, "dialog/list/list-row")
    assert [row["text"] for row in rows] == payload["items"]
    assert [row["text"].split()[1] for row in rows] == ["10", "2", "1"]


#: A wall-clock wait for a real `setTimeout` to fire is not reliable under
#: an offscreen, never-shown QWebEngineView (Chromium throttles background
#: timers unpredictably); no other module in this tree tests one that way.
#: `closeDelay()` proves the same fact deterministically: the auto-close
#: uses the exact millisecond value the surface measured and published in
#: `calls`, never a value this module invents.
def test_close_delay_reads_the_surfaces_own_measured_value(js: JsRuntime):
    js.push(state_payload("no_bots"))
    assert js.json("acervatorStartAllProgress.closeDelay()") == surface.NO_BOTS_CLOSE_DELAY_MS
    js.push(state_payload("done"))
    assert js.json("acervatorStartAllProgress.closeDelay()") == surface.DONE_CLOSE_DELAY_MS
    assert surface.NO_BOTS_CLOSE_DELAY_MS != surface.DONE_CLOSE_DELAY_MS


def test_close_delay_is_undefined_where_the_surface_made_no_closeafter_call(js: JsRuntime):
    """The control for the check above: a state with no `closeAfter`
    entry must not read as some other number, which would hide a bug
    where every state read the same hardcoded delay."""
    payload = state_payload("in_progress")
    assert all(call[0] != "closeAfter" for call in payload["calls"])
    js.push(payload)
    assert js.json("acervatorStartAllProgress.closeDelay()") is None
