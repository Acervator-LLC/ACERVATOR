"""The React Bot Swarm tab shell, composing bot_swarm_list.js and
bot_swarm_settings_tab.js against their own surfaces."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.main_tabs import bot_swarm_list_surface as list_surface
from src.gui.main_tabs import bot_swarm_tab_surface as tab_surface
from tests.fixtures.web_js_modules import (
    HEX_COLOUR,
    JsEngine,
    js_literals,
    load_order,
    new_engine,
    runs_after,
    swap_module,
)

WEB = REPO_ROOT / "src" / "gui" / "web"
MODULE_PATH = WEB / "bot_swarm_tab.js"
LIST_MODULE = WEB / "bot_swarm_list.js"
TAB_MODULE = WEB / "bot_swarm_settings_tab.js"
INDEX_HTML = REPO_ROOT / "desktop" / "renderer" / "index.html"

#: Read at collection, before any test body writes into the file.
MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")

API = "acervatorBotSwarmTab."
SETTER = "acervatorSetBotSwarmTab"

#: Every piece the page loads beside this module, needed at call time.
CHILD_MODULES = (
    WEB / "table_cells.js",
    WEB / "header_strip.js",
    LIST_MODULE,
    TAB_MODULE,
)

JS_TIMEOUT_MS = 30_000
READY_ROUNDS = 100
READY_STEP_MS = 100
PAGE_ATTEMPTS = 3
SETTLE_ROUNDS = 40
SETTLE_STEP_MS = 50
HOST_WIDTH_PX = 900
HOST_HEIGHT_PX = 600

THREE_BOTS = [
    {
        "bot_id": "bot-a",
        "symbol": "BTC-USD",
        "inflow_usd": 1000.5,
        "outflow_usd": 250.25,
        "outflow_pct": 40.0,
    },
    {
        "bot_id": "bot-b",
        "symbol": "ETH-USD",
        "inflow_usd": 10.0,
        "outflow_usd": 0.0,
        "outflow_pct": 0.0,
    },
    {
        "bot_id": "bot-c",
        "symbol": "SOL-USD",
        "inflow_usd": 5.0,
        "outflow_usd": 5.0,
        "outflow_pct": 100.0,
    },
]


def as_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


def list_payload(rows: list = THREE_BOTS) -> dict:
    """A real ``bot_swarm_list.state`` payload, from the real surface."""
    model = list_surface.BotSwarmListModel()
    model.bot_list.set_bots(rows)
    return as_json(list_surface.build_payload(model))


def tab_payload(bot_id: str = "bot-a") -> dict:
    """A real ``bot_swarm_tab.state`` payload for one unwired bot."""
    return as_json(
        tab_surface.view_model(
            {"reset": True, "bot": {"bot_id": bot_id, "fleet": None}, "now_ts": 0.0}
        )
    )


class JsRuntime(JsEngine):
    """A QJSEngine running this module beside the two children it composes."""

    module_path = MODULE_PATH
    setter = SETTER

    def __init__(self, engine: Any, source: str, with_children: bool = True) -> None:
        super().__init__(engine, source)
        if with_children:
            for path in CHILD_MODULES:
                loaded = engine.evaluate(path.read_text(encoding="utf-8"), path.name)
                assert not loaded.isError(), path.name + " -> " + loaded.toString()

    def called(self, method: str, *args: Any) -> Any:
        names = []
        for at, value in enumerate(args):
            name = "ARG" + str(at)
            self.bind_json(name, value)
            names.append("JSON.parse(" + name + ")")
        return self.json(API + method + "(" + ", ".join(names) + ")")


@pytest.fixture()
def js(qapp) -> JsRuntime:
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE)


@pytest.fixture()
def js_alone(qapp) -> JsRuntime:
    """The shell with neither child module loaded, so its globals are absent."""
    assert qapp is not None
    return JsRuntime(new_engine(), MODULE_SOURCE, with_children=False)


def test_the_module_defines_its_globals(js: JsRuntime):
    assert js.json("typeof " + API.rstrip(".")) == "object"
    assert js.json("typeof " + SETTER) == "function"


def test_the_shell_reports_both_child_modules_loaded_when_both_are_present(
    js: JsRuntime,
):
    report = js.json(API + "report()")
    assert report == {"hasList": True, "hasTab": True, "selectedBotId": None}


def test_the_presence_check_would_see_a_shell_with_neither_child_loaded(
    js_alone: JsRuntime,
):
    """The positive control for the module-presence report above."""
    report = js_alone.json(API + "report()")
    assert report == {"hasList": False, "hasTab": False, "selectedBotId": None}


def test_set_shell_stores_each_held_value_by_its_own_name(js: JsRuntime):
    given = {
        "list": list_payload(),
        "tab": tab_payload(),
        "selected_bot_id": "bot-a",
    }
    js.bind_json("GIVEN", given)
    report = js.json(SETTER + "(JSON.parse(GIVEN))")
    assert report == {"hasList": True, "hasTab": True, "selectedBotId": "bot-a"}
    assert js.json(API + "listModel()") == given["list"]
    assert js.json(API + "tabModel()") == given["tab"]
    assert js.json(API + "selectedBotId()") == "bot-a"


def test_a_partial_set_leaves_the_values_it_was_not_given_untouched(js: JsRuntime):
    js.bind_json("FIRST", {"list": list_payload(), "selected_bot_id": "bot-a"})
    js.run(SETTER + "(JSON.parse(FIRST))")
    js.bind_json("SECOND", {"selected_bot_id": "bot-b"})
    js.run(SETTER + "(JSON.parse(SECOND))")
    assert js.json(API + "selectedBotId()") == "bot-b"
    assert js.json(API + "listModel()") == list_payload()


def test_forget_clears_every_value_a_set_call_stored(js: JsRuntime):
    js.bind_json(
        "GIVEN",
        {"list": list_payload(), "tab": tab_payload(), "selected_bot_id": "bot-a"},
    )
    js.run(SETTER + "(JSON.parse(GIVEN))")
    js.run(API + "forget()")
    assert js.json(API + "listModel()") is None
    assert js.json(API + "tabModel()") is None
    assert js.json(API + "selectedBotId()") is None


DOM_STUB = (
    "function stub(attrs, parent) {"
    "  return {"
    "    getAttribute: function (name) {"
    "      return Object.prototype.hasOwnProperty.call(attrs, name)"
    "        ? attrs[name] : null;"
    "    },"
    "    parentElement: parent || null"
    "  };"
    "}"
)


def test_bot_id_at_answers_nothing_for_no_node(js: JsRuntime):
    js.run(DOM_STUB)
    assert js.called("botIdAt") is None  # no argument -> falls through the loop


def test_bot_id_at_reads_the_attribute_on_the_node_itself(js: JsRuntime):
    js.run(DOM_STUB)
    script = "var leaf = stub({'data-bot-id': 'bot-a'}, null);" + API + "botIdAt(leaf)"
    assert js.run(script).toVariant() == "bot-a"


def test_bot_id_at_climbs_to_the_nearest_ancestor_that_carries_it(js: JsRuntime):
    js.run(DOM_STUB)
    script = (
        "var grand = stub({'data-bot-id': 'bot-c'}, null);"
        "var parent = stub({}, grand);"
        "var leaf = stub({}, parent);" + API + "botIdAt(leaf)"
    )
    assert js.run(script).toVariant() == "bot-c"


def test_bot_id_at_answers_nothing_for_a_chain_that_carries_the_attribute_nowhere(
    js: JsRuntime,
):
    js.run(DOM_STUB)
    script = (
        "var top = stub({}, null);"
        "var mid = stub({}, top);"
        "var leaf = stub({}, mid);" + API + "botIdAt(leaf)"
    )
    assert js.run(script).toVariant() is None


def test_the_module_writes_no_number():
    """A numeric literal typed here has no publisher to compare it against."""
    literals = js_literals(MODULE_SOURCE)
    assert not literals[
        "numbers"
    ], f"bot_swarm_tab.js holds numbers: {literals['numbers']}"


def test_the_module_writes_no_colour():
    found = HEX_COLOUR.findall(MODULE_SOURCE)
    assert not found, f"bot_swarm_tab.js holds colour literals: {found}"


def test_the_module_hides_no_value_behind_a_regular_expression():
    literals = js_literals(MODULE_SOURCE)
    assert not literals["slashes"], (
        "bot_swarm_tab.js holds a slash outside a comment, which the literal"
        f" scan cannot read: {literals['slashes']}"
    )


WRITTEN_LINES = {
    "colour": 'var written = "#00ffcc";',
    "number": "var written = 12;",
    "regex": "var written = /ab+c/;",
}


def caught_by_scan(source: str) -> set:
    literals = js_literals(source)
    found = set()
    if literals["numbers"]:
        found.add("number")
    if HEX_COLOUR.findall(source):
        found.add("colour")
    if literals["slashes"]:
        found.add("regex")
    return found


@pytest.mark.parametrize("kind", sorted(WRITTEN_LINES))
def test_the_literal_scan_names_one_written_line(kind: str):
    assert caught_by_scan(WRITTEN_LINES[kind]), f"the scan reported nothing on {kind}"


def test_each_written_literal_is_caught_in_the_module_file_itself():
    """The positive control: the file itself would report the fault it lacks."""
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
            assert after == before, f"the file was not restored after the {kind} line"
    finally:
        swap_module(MODULE_PATH, original)
    quiet = sorted(kind for kind, caught in caught_each.items() if not caught)
    assert not quiet, f"the scan reported nothing on these lines in the file: {quiet}"
    assert hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest() == before


def test_the_renderer_runs_this_module_after_react_and_both_children():
    order = load_order()
    assert runs_after(
        order,
        MODULE_PATH.name,
        "react.production.min.js",
        "react-dom.production.min.js",
        "bot_swarm_list.js",
        "bot_swarm_settings_tab.js",
    ), order


def test_the_order_reading_answers_no_for_the_two_the_other_way_round():
    swapped = [MODULE_PATH.name, "bot_swarm_list.js"]
    assert not runs_after(swapped, MODULE_PATH.name, "bot_swarm_list.js")
    assert not runs_after(["bot_swarm_list.js"], MODULE_PATH.name, "bot_swarm_list.js")


# ---------------------------------------------------------------------
# Rendered checks: real DOM composition and a real click selecting a bot.
# ---------------------------------------------------------------------


class Browser:
    """A Browser drives the real renderer page in a Chromium view."""

    def __init__(self) -> None:
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView()
        for _ in range(PAGE_ATTEMPTS):
            self.open_page()
            if self.module_ready():
                return
        raise AssertionError(
            "the page never defined the bot swarm tab shell in "
            + str(PAGE_ATTEMPTS)
            + " loads: readyState "
            + str(self.js("document.readyState"))
        )

    def open_page(self) -> None:
        from PySide6.QtCore import QEventLoop, QTimer, QUrl

        loop = QEventLoop()
        box: dict = {}

        def _loaded(ok: bool) -> None:
            box.setdefault("ok", ok)
            loop.quit()

        link = self._view.loadFinished.connect(_loaded)
        self._view.load(QUrl.fromLocalFile(str(INDEX_HTML)))
        QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
        loop.exec()
        self._view.loadFinished.disconnect(link)
        assert box.get("ok") is True, f"{INDEX_HTML.name} did not load: {box}"

    def module_ready(self) -> bool:
        for _ in range(READY_ROUNDS):
            if self.js("typeof window." + SETTER) == "function":
                return True
            self.settle(READY_STEP_MS)
        return False

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

    def wait_until(self, expression: str, rounds: int = SETTLE_ROUNDS) -> bool:
        for _ in range(rounds):
            if self.js(expression):
                return True
            self.settle(SETTLE_STEP_MS)
        return False

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
    "window.HOST.style.width = '" + str(HOST_WIDTH_PX) + "px';"
    "window.HOST.style.height = '" + str(HOST_HEIGHT_PX) + "px';"
    "document.body.appendChild(window.HOST);"
)


def draw_shell(browser: Browser, list_model: dict, tab_model: Any) -> None:
    browser.js(PAGE_HELPERS)
    browser.js("window.LIST_MODEL = " + json.dumps(json.dumps(list_model)) + ";")
    browser.js("window.TAB_MODEL = " + json.dumps(json.dumps(tab_model)) + ";")
    browser.js(
        API + "renderShell(window.HOST, JSON.parse(window.LIST_MODEL),"
        " JSON.parse(window.TAB_MODEL));"
    )


def test_the_shell_draws_the_list_panel_and_the_detail_panel_together(
    browser: Browser,
):
    draw_shell(browser, list_payload(), tab_payload())
    assert (
        browser.parsed("!!window.HOST.querySelector('[data-part=\"bot-swarm-shell\"]')")
        is True
    )
    rows = browser.parsed("window.HOST.querySelectorAll('[data-part=\"row\"]').length")
    assert rows == len(THREE_BOTS)
    assert (
        browser.parsed("!!window.HOST.querySelector('[data-part=\"bot-swarm-tab\"]')")
        is True
    )


def test_the_list_and_the_detail_panel_each_nest_under_their_own_region(
    browser: Browser,
):
    """The two children are composed in one tree, not stitched by ID lookup."""
    draw_shell(browser, list_payload(), tab_payload())
    assert (
        browser.parsed(
            "!!window.HOST.querySelector("
            '\'[data-part="bot-swarm-list-region"] [data-part="list"]\')'
        )
        is True
    )
    assert (
        browser.parsed(
            "!!window.HOST.querySelector("
            '\'[data-part="bot-swarm-detail-region"] [data-part="bot-swarm-tab"]\')'
        )
        is True
    )
    assert (
        browser.parsed(
            "!!window.HOST.querySelector("
            '\'[data-part="bot-swarm-list-region"] [data-part="bot-swarm-tab"]\')'
        )
        is False
    )


def test_a_row_click_marks_that_bot_selected_on_the_shell(browser: Browser):
    draw_shell(browser, list_payload(), None)
    browser.js(
        "window.HOST.querySelector("
        '\'[data-part="row"][data-bot-id="bot-b"]\').click();'
    )
    settled = browser.wait_until(
        "window.HOST.querySelector('[data-part=\"bot-swarm-shell\"]')"
        ".getAttribute('data-selected-bot-id') === 'bot-b'"
    )
    assert settled, browser.parsed(
        "window.HOST.querySelector('[data-part=\"bot-swarm-shell\"]')"
        ".getAttribute('data-selected-bot-id')"
    )


def test_a_click_inside_the_detail_region_selects_no_bot(browser: Browser):
    """The detail region carries no row, so a click there names nothing."""
    draw_shell(browser, list_payload(), tab_payload())
    browser.js(
        "window.HOST.querySelector('[data-part=\"bot-swarm-detail-region\"]').click();"
    )
    browser.settle(SETTLE_STEP_MS)
    assert (
        browser.parsed(
            "window.HOST.querySelector('[data-part=\"bot-swarm-shell\"]')"
            ".getAttribute('data-selected-bot-id')"
        )
        is None
    )


def test_the_click_selection_survives_a_bridgeless_lookup_without_raising(
    browser: Browser,
):
    """No `window.acervator` bridge is present in this harness; the shell must not throw."""
    draw_shell(browser, list_payload(), None)
    browser.js(
        "window.HOST.querySelector("
        '\'[data-part="row"][data-bot-id="bot-a"]\').click();'
    )
    browser.wait_until(
        "window.HOST.querySelector('[data-part=\"bot-swarm-shell\"]')"
        ".getAttribute('data-selected-bot-id') === 'bot-a'"
    )
    assert browser.parsed("document.readyState") == "complete"
    assert (
        browser.parsed("!!window.HOST.querySelector('[data-part=\"bot-swarm-shell\"]')")
        is True
    )
